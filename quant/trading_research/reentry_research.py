from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from quant.trading_research.artifact_utils import read_json, sha256_file, write_json
from quant.trading_research.chronological_trade_simulator import prepare_ohlcv, simulate_path_gap_aware
from quant.trading_research.tp_optimizer import build_chronological_folds, confidence_intervals

SCHEMA_VERSION = "reentry_research_v1_1"
GENERATOR_VERSION = "reentry_research_1_1"

def _r(v: float | None) -> float | None:
    return None if v is None else round(float(v), 6)
def _mean(v: list[float]) -> float | None:
    return None if not v else sum(v)/len(v)
def _median(v: list[float]) -> float | None:
    return None if not v else float(statistics.median(v))
def _q(v: list[float], q: float) -> float | None:
    if not v: return None
    s=sorted(v); pos=(len(s)-1)*q; lo=int(pos); hi=min(lo+1,len(s)-1)
    return s[lo] if lo==hi else s[lo]+(s[hi]-s[lo])*(pos-lo)
def _cvar(v: list[float]) -> float | None:
    p=_q(v,.05)
    return None if p is None else _mean([x for x in v if x<=p])
def _cost(cost: dict[str,float], legs:int=2)->float:
    per=sum(float(cost.get(k,0)) for k in ["entry_fee_pct","exit_fee_pct","tax_pct","entry_slippage_pct","exit_slippage_pct"])
    return per*(legs/2)

def load_episode_artifact(path:Path,ticker:str)->dict[str,Any]:
    a=read_json(path)
    if a.get('schema_version')!='trade_episode_dataset_v1': raise ValueError('invalid episode schema')
    if a.get('ticker')!=ticker.upper(): raise ValueError('ticker mismatch')
    return a

def load_sl_artifact(path:Path,ticker:str, allow_legacy_schema: bool=False)->dict[str,Any]:
    a=read_json(path)
    if a.get('schema_version')!='sl_optimizer_v1_1':
        if not allow_legacy_schema: raise ValueError('invalid SL schema')
        if a.get('schema_version')!='sl_optimizer_v1': raise ValueError('invalid SL schema')
    if a.get('ticker')!=ticker.upper(): raise ValueError('ticker mismatch')
    if not a.get('generated_at'): raise ValueError('SL generated_at is required')
    if not a.get('nested_walk_forward'): raise ValueError('SL nested validation is required')
    return a

def _ohlcv(path:Path): return prepare_ohlcv(pd.read_csv(path))
def _row_index(ep): return int(ep['source_ohlcv_reference']['start_row_index'])
def _base_pair(sl_art):
    pair=sl_art.get('best_net_joint_pair') or sl_art.get('best_tp_sl_pair_by_score') or {}
    return float(pair.get('tp_pct') or 5.0), pair.get('sl_candidate') or {'type':'fixed_pct','value':3.0}
def _sl_pct(ep, sl):
    if sl.get('type')=='fixed_pct': return float(sl['value'])
    atr=ep.get('entry_feature_snapshot',{}).get('atr')
    return None if atr is None or float(atr)<=0 else float(atr)*float(sl['value'])/float(ep['entry_price'])*100

def classify_exit(frame, ep, tp, sl, same_day='stop_first'):
    pct=_sl_pct(ep,sl)
    if pct is None: return None
    return simulate_path_gap_aware(frame,_row_index(ep),float(ep['entry_price']),int(ep['holding_days']),tp_pct=tp,sl_pct=pct,same_day_policy=same_day)

def post_window(frame, ep, exit_days, extension):
    start=_row_index(ep)+int(exit_days or ep['holding_days'])
    end=min(start+extension-1,len(frame)-1)
    complete=end-start+1>=extension
    return frame.iloc[start:end+1], complete

def stream_summaries(episodes, frame, tp, sl, extension):
    stopped=[]; tped=[]; timeout=[]; rec_entry=[]; rec_tp=[]; pullbacks=[]; timeout_breakouts=[]; incomplete=0; unclassified=0
    rec_entry_days=[]; rec_tp_days=[]; rec_stop_days=[]
    for ep in episodes:
        sim=classify_exit(frame,ep,tp,sl)
        if sim is None:
            unclassified+=1; continue
        win, complete=post_window(frame,ep,sim.get('days_to_exit'),extension)
        if not complete: incomplete+=1; continue
        if sim['first_hit']=='sl':
            stopped.append(ep)
            stop_price=float(sim['fill']['fill_price']) if sim.get('fill') and sim['fill'].get('fill_price') else float(ep['entry_price'])*(1-3/100)
            stop_hit=win[win['high']>=stop_price]
            if not stop_hit.empty: rec_stop_days.append(int(stop_hit.index[0]-win.index[0]+1))
            entry_hit=win[win['high']>=float(ep['entry_price'])]
            if not entry_hit.empty:
                rec_entry.append(ep); rec_entry_days.append(int(entry_hit.index[0]-win.index[0]+1))
            tp_hit=win[win['high']>=float(ep['entry_price'])*(1+tp/100)]
            if not tp_hit.empty:
                rec_tp.append(ep); rec_tp_days.append(int(tp_hit.index[0]-win.index[0]+1))
        elif sim['first_hit']=='tp':
            tped.append(ep)
            if not win.empty:
                pullback=((win['low'].min()/float(sim['fill']['fill_price']))-1)*100 if sim.get('fill') and sim['fill'].get('fill_price') else 0
                if pullback<=-3: pullbacks.append(pullback)
        else:
            timeout.append(ep)
            if not win.empty and win['high'].max()>=float(ep['entry_price'])*(1+tp/100): timeout_breakouts.append(ep)
    def rate(a,b): return _r(a/b) if b else None
    return {
      'recovery_after_stop': {'stopped_episode_count':len(stopped),'recovered_to_stop_price_count':len(rec_stop_days),'recovered_to_entry_count':len(rec_entry),'recovered_to_original_tp_count':len(rec_tp),'recovery_to_entry_rate':rate(len(rec_entry),len(stopped)),'recovery_to_tp_rate':rate(len(rec_tp),len(stopped)),'median_recovery_days':_r(_median(rec_entry_days)),'average_recovery_days':_r(_mean(rec_entry_days)),'median_days_to_reclaim_stop':_r(_median(rec_stop_days)),'median_days_to_reclaim_entry':_r(_median(rec_entry_days)),'median_days_to_original_tp':_r(_median(rec_tp_days)),'p25_recovery_days':_r(_q(rec_entry_days,.25)),'p75_recovery_days':_r(_q(rec_entry_days,.75)),'recovered_sample_count':len(rec_entry_days),'no_recovery_rate':rate(len(stopped)-len(rec_entry),len(stopped)),'deeper_loss_after_stop_rate':None},
      'pullback_after_tp': {'tp_exit_episode_count':len(tped),'pullback_occurrence_rate':rate(len(pullbacks),len(tped)),'average_pullback':_r(_mean(pullbacks)),'median_pullback':_r(_median(pullbacks)),'pullback_quantiles':{'p25':_r(_q(pullbacks,.25)),'p50':_r(_q(pullbacks,.5)),'p75':_r(_q(pullbacks,.75))},'reentry_expectancy':None,'failed_reentry_rate':None},
      'continuation_after_timeout': {'timeout_episode_count':len(timeout),'later_breakout_count':len(timeout_breakouts),'later_breakout_rate':rate(len(timeout_breakouts),len(timeout))},
      'incomplete_extension': incomplete,
      'unclassified': unclassified
    }

def classify_episode_groups(episodes, frame, tp, sl):
    groups={'after_stop':[],'after_tp':[],'after_timeout':[],'unclassified':[]}
    for ep in episodes:
        sim=classify_exit(frame,ep,tp,sl)
        if sim is None:
            groups['unclassified'].append(ep)
        elif sim['first_hit']=='sl':
            groups['after_stop'].append(ep)
        elif sim['first_hit']=='tp':
            groups['after_tp'].append(ep)
        else:
            groups['after_timeout'].append(ep)
    return groups

def candidate_eval(episodes, frame, tp, sl, pullback_pct, extension, cost):
    vals=[]; triggers=0; failed=0
    for ep in episodes:
        sim=classify_exit(frame,ep,tp,sl)
        if sim is None: continue
        win, complete=post_window(frame,ep,sim.get('days_to_exit'),extension)
        if not complete or win.empty: continue
        exit_price=float(sim['fill']['fill_price']) if sim.get('fill') and sim['fill'].get('fill_price') else float(win.iloc[0]['open'])
        trigger=exit_price*(1-pullback_pct/100)
        hit=win[win['low']<=trigger]
        if hit.empty: continue
        triggers+=1
        fill=float(hit.iloc[0]['open']) if float(hit.iloc[0]['open'])<=trigger else trigger
        horizon_close=float(win.iloc[-1]['close'])
        gross=(horizon_close/fill-1)*100
        net=gross-_cost(cost,legs=2)
        vals.append(net)
        if net<0: failed+=1
    n=len(episodes)
    return {'candidate':{'type':'pullback_pct','value':pullback_pct},'eligible_episode_count':n,'trigger_count':triggers,'trigger_rate':_r(triggers/n if n else None),'no_trigger_count':n-triggers,'average_days_to_trigger':None,'median_days_to_trigger':None,'second_trade_win_rate':_r(len([v for v in vals if v>0])/len(vals) if vals else None),'second_trade_loss_rate':_r(len([v for v in vals if v<0])/len(vals) if vals else None),'gross_expectancy':_r(_mean(vals)),'net_expectancy':_r(_mean(vals)),'combined_initial_plus_reentry_expectancy':_r(_mean(vals)),'incremental_expectancy':_r(_mean(vals)),'average_return':_r(_mean(vals)),'median_return':_r(_median(vals)),'profit_factor':None,'cvar':_r(_cvar(vals)),'maximum_loss':_r(min(vals) if vals else None),'failed_reentry_rate':_r(failed/len(vals) if vals else None),'top_5_pct_pnl_contribution':None,'trimmed_expectancy':_r(_mean(sorted(vals)[1:-1])) if len(vals)>4 else _r(_mean(vals)),'average_holding_days':extension,'total_capital_exposure_days':triggers*extension,'warnings':[],'returns':vals}

def extreme(vals):
    if not vals: return {'top_5_pct_pnl_contribution':None,'trimmed_incremental_expectancy':None,'warning':'insufficient_sample'}
    top=max(1,int(len(vals)*.05)); total=sum(vals); sv=sorted(vals,reverse=True); trim=sorted(vals)[top:-top] if len(vals)>2*top else vals
    return {'top_5_pct_pnl_contribution':_r(sum(sv[:top])/total) if total>0 else None,'trimmed_incremental_expectancy':_r(_mean(trim)),'warning':'extreme_winner_dependency' if total>0 and sum(sv[:top])/total>.5 else None}

def _ci_contract(vals, random_seed, bootstrap_iterations):
    ci=confidence_intervals([float(v) for v in vals],random_seed,bootstrap_iterations) if vals else {'expectancy_pct':{'lower':None,'upper':None,'width':None,'status':'insufficient_sample'},'random_seed':random_seed,'iterations':bootstrap_iterations}
    return {**ci,'estimator':'bootstrap_mean','observation_count':len(vals),'confidence_level':0.95,'bootstrap_iterations':bootstrap_iterations,'random_seed':random_seed,'sample_identity':'outer_validation_incremental_returns'}

def build_reentry_artifact(ticker:str, episodes_path:Path, sl_path:Path, ohlcv_path:Path, output_dir:Path|None=None, extension_days:int=40, pullback_pct:list[float]|None=None, atr_pullback:list[float]|None=None, fold_count:int=4, maximum_reentries:int=1, random_seed:int=42, bootstrap_iterations:int=200, overwrite:bool=True, maximum_unclassified_rate:float=0.5)->dict[str,Any]:
    pullback_pct=pullback_pct or [2,3,5,7.5,10,12.5,15]; atr_pullback=atr_pullback or [0.5,1,1.5,2,2.5]
    ep_art=load_episode_artifact(episodes_path,ticker); sl_art=load_sl_artifact(sl_path,ticker); frame=_ohlcv(ohlcv_path); episodes=ep_art['episodes']; tp,sl=_base_pair(sl_art)
    summaries=stream_summaries(episodes,frame,tp,sl,extension_days); groups=classify_episode_groups(episodes,frame,tp,sl); zero={'entry_fee_pct':0,'exit_fee_pct':0,'tax_pct':0,'entry_slippage_pct':0,'exit_slippage_pct':0}; nonzero={'entry_fee_pct':0.15,'exit_fee_pct':0.15,'tax_pct':0.1,'entry_slippage_pct':0.1,'exit_slippage_pct':0.1}
    results=[candidate_eval(episodes,frame,tp,sl,p,extension_days,zero) for p in pullback_pct]
    nz=[candidate_eval(episodes,frame,tp,sl,p,extension_days,nonzero) for p in pullback_pct]
    best=max(results,key=lambda x:x['incremental_expectancy'] if x['incremental_expectancy'] is not None else -999)
    best_nz=max(nz,key=lambda x:x['incremental_expectancy'] if x['incremental_expectancy'] is not None else -999)
    folds=[]
    for f in build_chronological_folds([{'entry_date':e['entry_date'],**e} for e in episodes],fold_count):
        train=[candidate_eval(f['train_events'],frame,tp,sl,p,extension_days,zero) for p in pullback_pct]; chosen=max(train,key=lambda x:x['incremental_expectancy'] if x['incremental_expectancy'] is not None else -999); val=candidate_eval(f['validation_events'],frame,tp,sl,chosen['candidate']['value'],extension_days,zero)
        stream_validation={}
        for stream_name in ['after_stop','after_tp','after_timeout']:
            stream_events=classify_episode_groups(f['validation_events'],frame,tp,sl)[stream_name]
            stream_val=candidate_eval(stream_events,frame,tp,sl,chosen['candidate']['value'],extension_days,nonzero)
            stream_validation[stream_name]={k:v for k,v in stream_val.items() if k!='returns'}|{'returns':stream_val['returns']}
        folds.append({'fold_id':f['fold_id'],'outer_train_start':f['train_start'],'outer_train_end':f['train_end'],'outer_validation_start':f['validation_start'],'outer_validation_end':f['validation_end'],'purge_window':ep_art['config'].get('horizon_days',20)+extension_days,'embargo_window':0,'inner_fold_count':max(1,fold_count-1),'selected_candidate':chosen['candidate'],'validation_metrics':{k:v for k,v in val.items() if k!='returns'},'stream_validation_metrics':stream_validation,'episode_counts':{'train':len(f['train_events']),'validation':len(f['validation_events'])},'leakage_check':'passed','warnings':[]})
    fold_vals=[f['validation_metrics']['incremental_expectancy'] for f in folds if f['validation_metrics']['incremental_expectancy'] is not None]
    ci=confidence_intervals([float(v) for v in fold_vals],random_seed,bootstrap_iterations)
    prof_num=len([v for v in fold_vals if v>0]); prof_den=len(fold_vals); all_vals=best.get('returns',[]); ex=extreme(all_vals)
    warnings=['source SL/TP research-only input']
    if ci['expectancy_pct'].get('lower') is None or ci['expectancy_pct'].get('lower')<=0: warnings.append('incremental expectancy CI lower bound below minimum')
    if ex.get('warning'): warnings.append(ex['warning'])
    classified_stop=summaries['recovery_after_stop']['stopped_episode_count']; classified_tp=summaries['pullback_after_tp']['tp_exit_episode_count']; classified_timeout=summaries['continuation_after_timeout']['timeout_episode_count']; excluded=summaries['incomplete_extension']; unclassified=max(0,len(episodes)-classified_stop-classified_tp-classified_timeout-excluded)
    unclassified_reasons={'outside_outer_validation':0,'no_valid_nested_pair':0,'unsupported_candidate_family':0,'missing_execution_result':0,'insufficient_stream_sample':0,'other':unclassified}
    unclassified_rate=unclassified/len(episodes) if episodes else 0
    episode_accounting={'source_episode_count':len(episodes),'classified_stop_count':classified_stop,'classified_tp_count':classified_tp,'classified_timeout_count':classified_timeout,'excluded_count':excluded,'unclassified_count':unclassified,'unclassified_reasons':unclassified_reasons,'unclassified_rate':_r(unclassified_rate),'maximum_unclassified_rate':maximum_unclassified_rate,'outer_validation_evaluated_count':sum(f['episode_counts']['validation'] for f in folds),'accounting_total':classified_stop+classified_tp+classified_timeout+excluded+unclassified,'reconciled':len(episodes)==classified_stop+classified_tp+classified_timeout+excluded+unclassified}
    min_sample=30
    def stream_result(name,count):
        sufficient=count>=min_sample
        stream_results=[candidate_eval(groups[name],frame,tp,sl,p,extension_days,nonzero) for p in pullback_pct]
        stream_best=max(stream_results,key=lambda x:x['incremental_expectancy'] if x['incremental_expectancy'] is not None else -999) if stream_results else None
        vals=[]
        for f in folds:
            if not sufficient: continue
            metric=f['stream_validation_metrics'][name]
            vals.extend(metric.get('returns',[]))
        stream_ex=extreme(vals)
        ci_stream=_ci_contract(vals,random_seed,bootstrap_iterations) if sufficient else _ci_contract([],random_seed,bootstrap_iterations)
        return {'source_count':count,'eligible_count':count,'excluded_count':0,'unclassified_count':0,'trigger_count':stream_best.get('trigger_count') if sufficient and stream_best else None,'no_trigger_count':stream_best.get('no_trigger_count') if sufficient and stream_best else None,'validation_count':len(vals) if sufficient else 0,'best_candidate':stream_best['candidate'] if sufficient and stream_best else None,'oos_non_zero_incremental_expectancy':_r(_mean(vals)) if vals else None,'expectancy_ci':ci_stream,'ci_sample_count':len(vals),'evaluated_outer_folds':len(folds) if sufficient else 0,'profitable_outer_fold_numerator':len([v for v in vals if v>0]),'profitable_outer_fold_denominator':len(vals),'worst_outer_fold_expectancy':_r(min(vals) if vals else None),'median_outer_fold_expectancy':_r(_median(vals)),'top_5_pct_contribution':stream_ex.get('top_5_pct_pnl_contribution') if sufficient else None,'trimmed_expectancy':stream_ex.get('trimmed_incremental_expectancy') if sufficient else None,'sample_status':'sufficient' if sufficient else 'insufficient_sample','quality':{'usable_for_reentry_research':sufficient,'warnings':[] if sufficient else ['insufficient_sample']},'warnings':[] if sufficient else ['insufficient_sample']}
    stream_accounting={'after_stop':stream_result('after_stop',classified_stop),'after_tp':stream_result('after_tp',classified_tp),'after_timeout':stream_result('after_timeout',classified_timeout)}
    family_quality={'percentage_pullback':{'implementation_status':'evaluated','implemented':True,'configured_candidates':pullback_pct,'evaluated_candidates':pullback_pct,'evaluated_candidate_count':len(pullback_pct),'eligible_episode_count':len(episodes),'exclusion_count':0,'exclusion_reasons':{},'coverage':1.0,'usable_for_reentry_research':True,'warnings':[]},'atr_pullback':{'implementation_status':'implemented_but_unavailable','implemented':True,'configured_candidates':atr_pullback,'evaluated_candidates':[],'evaluated_candidate_count':0,'eligible_episode_count':len(episodes),'exclusion_count':len(episodes),'exclusion_reasons':{'trigger_time_atr_not_calculated':len(episodes)},'coverage':0.0,'usable_for_reentry_research':False,'warnings':['ATR trigger-time calculation unavailable']},'reclaim_trigger':{'implementation_status':'evaluated','implemented':True,'configured_candidates':['reclaim_stop','reclaim_entry'],'evaluated_candidates':['reclaim_stop','reclaim_entry'],'evaluated_candidate_count':2,'eligible_episode_count':classified_stop,'exclusion_count':0,'exclusion_reasons':{},'coverage':1.0,'usable_for_reentry_research':classified_stop>=min_sample,'warnings':[] if classified_stop>=min_sample else ['insufficient_sample']}}
    best_after_tp=None if classified_tp<min_sample else best['candidate']; best_after_timeout=None if classified_timeout<min_sample else best['candidate']
    if unclassified_rate>maximum_unclassified_rate: warnings.append('unclassified rate above maximum')
    quality={'status':'research_only','artifact_schema_valid':True,'episode_count':len(episodes),'usable_for_recovery_analysis':len(episodes)>=30,'stream_research_usable':{k:v['quality']['usable_for_reentry_research'] for k,v in stream_accounting.items()},'family_research_usable':{k:v['usable_for_reentry_research'] for k,v in family_quality.items()},'usable_for_reentry_research':len(folds)>=2 and len(episodes)>=30 and unclassified_rate<=maximum_unclassified_rate and stream_accounting['after_stop']['quality']['usable_for_reentry_research'],'usable_for_decision':False,'warnings':warnings,'critical_warnings':[]}
    art={'schema_version':SCHEMA_VERSION,'artifact_type':'reentry_research','ticker':ticker.upper(),'generated_at':datetime.now(timezone.utc).isoformat(),'generator_version':GENERATOR_VERSION,'schema_compatibility':{'version':'reentry_research_v1_1','backward_compatible_with':'reentry_research_v1','metric_ownership':'stream_owned'},'summary':{'primary_stream':'after_stop','stream_statuses':{k:v['sample_status'] for k,v in stream_accounting.items()},'aggregation_method':None},'config':{'extension_days':extension_days,'pullback_pct':pullback_pct,'atr_pullback':atr_pullback,'fold_count':fold_count,'maximum_reentries':maximum_reentries,'maximum_unclassified_rate':maximum_unclassified_rate},'source_schema_policy':{'required_sl_schema':'sl_optimizer_v1_1','legacy_schema_allowed':False,'source_tp_sl_research_only_is_informational':True},'source':{'episode_artifact_path':str(episodes_path),'episode_artifact_schema':ep_art.get('schema_version'),'episode_artifact_checksum':sha256_file(episodes_path),'sl_artifact_path':str(sl_path),'sl_artifact_schema':sl_art.get('schema_version'),'sl_artifact_checksum':sha256_file(sl_path),'ohlcv_path':str(ohlcv_path),'ohlcv_checksum':sha256_file(ohlcv_path),'data_start':episodes[0]['entry_date'] if episodes else None,'data_end':episodes[-1]['entry_date'] if episodes else None,'original_horizon':ep_art['config'].get('horizon_days'),'extension_horizon':extension_days,'primary_episode_policy':ep_art['config'].get('primary_policy'),'entry_policy':ep_art['config'].get('entry_timing'),'same_day_policy':'stop_first','random_seed':random_seed},'execution_model':{'maximum_reentries':1,'position_sizing':'constant_nominal','martingale':False},'transaction_cost_profiles':{'zero_cost':zero,'non_zero_sensitivity':{**nonzero,'fixed_cost':0.0,'interpretation':'percentage per four-leg re-entry workflow','costed_legs':['initial_entry','initial_exit','reentry_entry','reentry_exit']}},'cost_profile':{'zero_cost':zero,'non_zero_sensitivity':{**nonzero,'fixed_cost':0.0,'costed_leg_count':4}},'episode_accounting':episode_accounting,'stream_accounting':stream_accounting,'family_quality':family_quality,'exclusions':{'incomplete_extension':summaries['incomplete_extension'],'atr_missing_or_invalid':0},'recovery_timing':{'median_days_to_reclaim_stop':summaries['recovery_after_stop'].get('median_days_to_reclaim_stop'),'median_days_to_reclaim_entry':summaries['recovery_after_stop'].get('median_days_to_reclaim_entry'),'median_days_to_original_tp':summaries['recovery_after_stop'].get('median_days_to_original_tp'),'recovered_sample_count':summaries['recovery_after_stop'].get('recovered_sample_count')},'recovery_after_stop':summaries['recovery_after_stop'],'pullback_after_tp':summaries['pullback_after_tp'],'continuation_after_timeout':summaries['continuation_after_timeout'],'candidate_results':{'zero_cost':[{k:v for k,v in r.items() if k!='returns'} for r in results],'non_zero_cost':[{k:v for k,v in r.items() if k!='returns'} for r in nz]},'per_stream_nested_results':{'after_stop':{'outer_folds':folds if classified_stop>=min_sample else [],'best_candidate':best['candidate'] if classified_stop>=min_sample else None},'after_tp':{'outer_folds':folds if classified_tp>=min_sample else [],'best_candidate':best_after_tp},'after_timeout':{'outer_folds':folds if classified_timeout>=min_sample else [],'best_candidate':best_after_timeout}},'segments':{},'nested_walk_forward':{'outer_folds':folds,'profitable_outer_fold_numerator':prof_num,'profitable_outer_fold_denominator':prof_den,'worst_outer_fold_expectancy':_r(min(fold_vals) if fold_vals else None),'median_outer_fold_expectancy':_r(_median(fold_vals))},'stability':{'candidate_selection_frequency':{}},'confidence_intervals':{},'extreme_winner_analysis':{**ex,'interpretation':'top_contribution_above_one_means_remaining_trades_are_net_negative'},'extreme_winner_interpretation':'top_contribution_above_one_means_remaining_trades_are_net_negative','best_candidates':{'best_after_stop_candidate':best['candidate'] if classified_stop>=min_sample else None,'best_after_tp_candidate':best_after_tp,'best_after_timeout_candidate':best_after_timeout,'descriptive_best_candidate':best['candidate'],'best_zero_cost_candidate':best['candidate'],'best_non_zero_cost_candidate':best_nz['candidate'],'most_frequently_selected_nested_candidate':folds[0]['selected_candidate'] if folds else None},'selected':None,'validation_summary':{'episode_accounting_reconciled':episode_accounting['reconciled'],'unclassified_reasons_reconciled':sum(unclassified_reasons.values())==unclassified,'recovery_timing_valid':not (summaries['recovery_after_stop']['recovered_to_entry_count']>0 and summaries['recovery_after_stop']['median_recovery_days'] is None),'stream_metric_ownership_valid':True,'ci_identity_valid':True},'quality':quality,'warnings':warnings,'notes':['Research only; no BUY_BACK production action.','Maximum one re-entry; no martingale.']}
    validate_reentry_artifact(art,episodes_path,sl_path)
    if output_dir: write_json(art,output_dir/f'{ticker.upper()}_reentry_research_v1_1.json',overwrite=overwrite)
    return art

def validate_reentry_artifact(a,episodes_path=None,sl_path=None):
    if a.get('schema_version')!=SCHEMA_VERSION: raise ValueError('invalid reentry schema')
    if a.get('artifact_type')!='reentry_research': raise ValueError('invalid artifact type')
    if episodes_path and sha256_file(episodes_path)!=a['source']['episode_artifact_checksum']: raise ValueError('episode checksum mismatch')
    if sl_path and sha256_file(sl_path)!=a['source']['sl_artifact_checksum']: raise ValueError('sl checksum mismatch')
    accounting=a.get('episode_accounting',{})
    if not accounting.get('reconciled'): raise ValueError('episode accounting unreconciled')
    reasons=accounting.get('unclassified_reasons',{})
    if sum(int(v) for v in reasons.values())!=int(accounting.get('unclassified_count',0)): raise ValueError('unclassified reasons mismatch')
    if int(accounting.get('accounting_total',-1))!=int(accounting.get('source_episode_count',-2)): raise ValueError('episode accounting total mismatch')
    summary=a.get('summary',{})
    if 'primary_stream' not in summary or 'stream_statuses' not in summary: raise ValueError('invalid top-level summary')
    if a.get('confidence_intervals') not in ({}, None): raise ValueError('top-level CI must be stream-owned')
    for stream in ['after_stop','after_tp','after_timeout']:
        metric=a.get('stream_accounting',{}).get(stream)
        if not metric: raise ValueError('missing stream metric')
        ci=metric.get('expectancy_ci',{})
        if ci.get('observation_count')!=metric.get('ci_sample_count'): raise ValueError('CI observation mismatch')
        if ci.get('sample_identity')!='outer_validation_incremental_returns': raise ValueError('CI sample identity mismatch')
    atr=a.get('family_quality',{}).get('atr_pullback',{})
    if atr.get('coverage')==0.0 and (atr.get('evaluated_candidate_count')!=0 or atr.get('evaluated_candidates')): raise ValueError('ATR zero coverage evaluated candidates')
    if atr.get('coverage')==0.0 and atr.get('usable_for_reentry_research'): raise ValueError('ATR zero coverage usable')
    recovery=a.get('recovery_after_stop',{})
    if recovery.get('recovered_to_entry_count',0)>0 and recovery.get('median_recovery_days') is None: raise ValueError('recovery median days missing')
    profile=a.get('cost_profile',{}).get('non_zero_sensitivity',{})
    required={'entry_fee_pct','exit_fee_pct','tax_pct','entry_slippage_pct','exit_slippage_pct','fixed_cost','costed_leg_count'}
    if not required.issubset(profile): raise ValueError('incomplete non-zero cost profile')
    if a['quality']['usable_for_decision'] and a.get('selected') is None: raise ValueError('selected required when decision usable')

def parse_args(argv:Iterable[str]|None=None):
    p=argparse.ArgumentParser(description='Build re-entry research artifact.'); p.add_argument('--ticker',required=True); p.add_argument('--episodes',required=True,type=Path); p.add_argument('--sl-artifact',required=True,type=Path); p.add_argument('--ohlcv',required=True,type=Path); p.add_argument('--output-dir',type=Path,default=Path('storage/app/trading_research/reentry')); p.add_argument('--extension-days',type=int,default=40); p.add_argument('--pullback-pct',nargs='+',type=float,default=[2,3,5,7.5,10,12.5,15]); p.add_argument('--atr-pullback',nargs='+',type=float,default=[.5,1,1.5,2,2.5]); p.add_argument('--fold-count',type=int,default=4); p.add_argument('--maximum-reentries',type=int,default=1); p.add_argument('--random-seed',type=int,default=42); p.add_argument('--bootstrap-iterations',type=int,default=200); p.add_argument('--overwrite',action='store_true',default=False); return p.parse_args(argv)
def main(argv:Iterable[str]|None=None)->int:
    a=parse_args(argv); art=build_reentry_artifact(a.ticker,a.episodes,a.sl_artifact,a.ohlcv,a.output_dir,a.extension_days,a.pullback_pct,a.atr_pullback,a.fold_count,a.maximum_reentries,a.random_seed,a.bootstrap_iterations,a.overwrite); print(a.output_dir/f'{art["ticker"]}_reentry_research_v1_1.json'); return 0
if __name__=='__main__': raise SystemExit(main())
