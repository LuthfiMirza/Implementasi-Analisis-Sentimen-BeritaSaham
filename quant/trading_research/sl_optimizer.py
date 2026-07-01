from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from quant.trading_research.artifact_utils import read_json, sha256_file, write_json
from quant.trading_research.chronological_trade_simulator import prepare_ohlcv, simulate_path_gap_aware
from quant.trading_research.tp_optimizer import confidence_intervals, build_chronological_folds

SCHEMA_VERSION = "sl_optimizer_v1_1"
GENERATOR_VERSION = "sl_optimizer_1_1"
DEFAULT_FIXED_SL = [3.0, 5.0, 7.5, 10.0, 12.5, 15.0, 20.0]
DEFAULT_ATR_MULTIPLES = [1.0, 1.5, 2.0, 2.5, 3.0]
DEFAULT_WEIGHTS = {"expectancy": 0.3, "downside": 0.2, "cvar": 0.2, "premature": 0.15, "recovery": 0.05, "stability": 0.1}
OHLCV_CACHE: dict[str, Any] = {}
SIM_CACHE: dict[tuple[str, float, str, float | None], dict[str, Any]] = {}

def _r(v: float | None) -> float | None:
    return None if v is None else round(float(v), 6)

def _mean(v: list[float]) -> float | None:
    return None if not v else sum(v)/len(v)

def _median(v: list[float]) -> float | None:
    return None if not v else float(statistics.median(v))

def _q(values: list[float], q: float) -> float | None:
    if not values: return None
    s=sorted(values); pos=(len(s)-1)*q; lo=int(pos); hi=min(lo+1,len(s)-1)
    return s[lo] if lo==hi else s[lo]+(s[hi]-s[lo])*(pos-lo)

def _cvar(values: list[float], q: float=0.05) -> float | None:
    p=_q(values,q)
    if p is None: return None
    tail=[v for v in values if v<=p]
    return _mean(tail)

def load_episode_artifact(path: Path, ticker: str) -> dict[str, Any]:
    a=read_json(path)
    if a.get("schema_version")!="trade_episode_dataset_v1": raise ValueError("invalid episode schema")
    if a.get("ticker")!=ticker.upper(): raise ValueError("ticker mismatch")
    return a

def load_tp_artifact(path: Path, ticker: str) -> dict[str, Any]:
    a=read_json(path)
    if a.get("schema_version")!="tp_optimizer_v1": raise ValueError("invalid TP artifact schema")
    if a.get("ticker")!=ticker.upper(): raise ValueError("ticker mismatch")
    return a

def _episode_path_rows(episode: dict[str, Any]) -> list[dict[str, float]]:
    # Compact reconstruction from outcome is insufficient for first-hit; canonical OHLCV is used by simulator in production paths.
    return []

def sl_pct_for_candidate(episode: dict[str, Any], candidate: dict[str, Any]) -> float | None:
    if candidate["type"] == "fixed_pct": return float(candidate["value"])
    atr = episode.get("entry_feature_snapshot", {}).get("atr") or episode.get("atr")
    if atr is None or float(atr) <= 0: return None
    return (float(atr) * float(candidate["value"]) / float(episode["entry_price"])) * 100

def _load_ohlcv_for_episode(episode: dict[str, Any]) -> Any:
    ref=episode["source_ohlcv_reference"]
    path=Path(ref["path"])
    if sha256_file(path)!=ref["checksum"]: raise ValueError("source checksum mismatch")
    key=str(path)
    if key in OHLCV_CACHE: return OHLCV_CACHE[key]
    import pandas as pd
    OHLCV_CACHE[key]=prepare_ohlcv(pd.read_csv(path))
    return OHLCV_CACHE[key]

def _cost_pct(cost_model: dict[str, float]) -> float:
    return sum(float(cost_model.get(k, 0.0)) for k in ["entry_fee_pct", "exit_fee_pct", "exit_tax_pct", "entry_slippage_pct", "exit_slippage_pct"])

def simulate_episode(episode: dict[str, Any], sl_pct: float, tp_pct: float | None, same_day_policy: str, cost_model: dict[str, float] | None = None) -> dict[str, Any]:
    key=(episode.get("episode_id", episode["entry_date"]), round(float(sl_pct),6), same_day_policy, None if tp_pct is None else round(float(tp_pct),6))
    if key in SIM_CACHE: return dict(SIM_CACHE[key])
    frame=_load_ohlcv_for_episode(episode)
    idx=int(episode["source_ohlcv_reference"]["start_row_index"])
    result=simulate_path_gap_aware(frame, idx, float(episode["entry_price"]), int(episode["holding_days"]), tp_pct=tp_pct, sl_pct=sl_pct, same_day_policy=same_day_policy)
    cost_model = cost_model or {}
    gross = result.get("gross_realized_return_pct") if result["first_hit"] != "ambiguous" else None
    net = None if gross is None else float(gross) - _cost_pct(cost_model)
    result.update({"realized_return_pct": _r(net), "gross_realized_return_pct": _r(gross), "net_realized_return_pct": _r(net), "total_cost_pct": _r(_cost_pct(cost_model))})
    SIM_CACHE[key]=dict(result)
    return result

def premature_metrics(episode: dict[str, Any], sim: dict[str, Any], sl_pct: float, tp_candidates: list[float]) -> dict[str, Any]:
    if sim["first_hit"] != "sl":
        return {"premature_stop": False, "recovered_to_entry_after_stop": False, "reached_tp_after_stop": False, "recovery_days_after_stop": None, "maximum_recovery_after_stop_pct": None, "loss_avoided_pct": None, "stop_avoided_larger_loss": False}
    horizon=float(sim["horizon_return_pct"])
    recovered=horizon>=0
    reached_tp=any(float(sim["mfe_pct"] or 0) >= tp for tp in tp_candidates)
    loss_avoided = horizon - (-abs(sl_pct))
    return {"premature_stop": recovered or reached_tp, "recovered_to_entry_after_stop": recovered, "reached_tp_after_stop": reached_tp, "recovery_days_after_stop": None if not (recovered or reached_tp) else int(episode["holding_days"]), "maximum_recovery_after_stop_pct": _r(max(0.0, float(sim["mfe_pct"] or 0))), "loss_avoided_pct": _r(-loss_avoided), "stop_avoided_larger_loss": horizon < -abs(sl_pct)}

def standalone_metrics(episodes: list[dict[str, Any]], candidate: dict[str, Any], tp_candidates: list[float], same_day_policy: str) -> dict[str, Any]:
    vals=[]; days=[]; stopped=[]; prem=[]; recover=[]; loss_avoided=[]; excluded=0; ambiguous=0
    for ep in episodes:
        sl=sl_pct_for_candidate(ep,candidate)
        if sl is None: excluded+=1; continue
        sim=simulate_episode(ep,sl,None,same_day_policy)
        if sim["first_hit"]=="ambiguous": ambiguous+=1; continue
        pm=premature_metrics(ep,sim,sl,tp_candidates)
        vals.append(float(sim["realized_return_pct"]));
        if sim["first_hit"]=="sl": stopped.append(float(sim["realized_return_pct"])); days.append(float(sim["days_to_exit"]));
        if pm["premature_stop"]: prem.append(1)
        if pm["recovered_to_entry_after_stop"] or pm["reached_tp_after_stop"]: recover.append(1)
        if pm["stop_avoided_larger_loss"]: loss_avoided.append(float(pm["loss_avoided_pct"] or 0))
    n=len(vals); stop_n=len(stopped)
    return {"candidate": candidate, "episode_count": len(episodes), "eligible_episode_count": n, "excluded_episode_count": excluded, "stop_hit_count": stop_n, "stop_hit_rate": _r(stop_n/n if n else None), "average_days_to_stop": _r(_mean(days)), "median_days_to_stop": _r(_median(days)), "average_loss_when_stopped_pct": _r(_mean(stopped)), "median_loss_when_stopped_pct": _r(_median(stopped)), "average_horizon_return_pct": _r(_mean(vals)), "median_horizon_return_pct": _r(_median(vals)), "positive_horizon_return_rate": _r(len([v for v in vals if v>0])/n if n else None), "mae_coverage": _r(n/len(episodes) if episodes else None), "loss_avoided_metric": {"stop_avoided_larger_loss_count": len(loss_avoided), "stop_avoided_larger_loss_rate": _r(len(loss_avoided)/stop_n if stop_n else None), "average_loss_avoided_pct": _r(_mean(loss_avoided)), "median_loss_avoided_pct": _r(_median(loss_avoided))}, "premature_stop_count": len(prem), "premature_stop_rate": _r(len(prem)/stop_n if stop_n else None), "recovery_after_stop_count": len(recover), "recovery_after_stop_rate": _r(len(recover)/stop_n if stop_n else None), "average_recovery_days": None, "median_recovery_days": None, "worst_realized_return_pct": _r(min(vals) if vals else None), "downside_p5": _r(_q(vals,.05)), "downside_p10": _r(_q(vals,.10)), "cvar_pct": _r(_cvar(vals)), "same_day_ambiguous_count": ambiguous, "warnings": []}

def joint_metrics(episodes: list[dict[str, Any]], tp_pct: float, candidate: dict[str, Any], same_day_policy: str, tp_candidates: list[float]) -> dict[str, Any]:
    vals=[]; hold=[]; tp_first=sl_first=timeout=amb=0; prem=0
    for ep in episodes:
        sl=sl_pct_for_candidate(ep,candidate)
        if sl is None: continue
        sim=simulate_episode(ep,sl,tp_pct,same_day_policy)
        if sim["first_hit"]=="ambiguous": amb+=1; continue
        vals.append(float(sim["realized_return_pct"])); hold.append(float(sim["days_to_exit"] or ep["holding_days"]))
        tp_first += sim["first_hit"]=="tp"; sl_first += sim["first_hit"]=="sl"; timeout += sim["first_hit"] is None
        prem += premature_metrics(ep,sim,sl,tp_candidates)["premature_stop"]
    wins=[v for v in vals if v>0]; losses=[v for v in vals if v<0]
    gross_profit=sum(wins); gross_loss=abs(sum(losses))
    return {"tp_pct": tp_pct, "sl_candidate": candidate, "episode_count": len(vals), "tp_first_count": tp_first, "sl_first_count": sl_first, "timeout_count": timeout, "ambiguous_count": amb, "tp_hit_rate": _r(tp_first/len(vals) if vals else None), "sl_hit_rate": _r(sl_first/len(vals) if vals else None), "average_realized_return_pct": _r(_mean(vals)), "median_realized_return_pct": _r(_median(vals)), "expectancy_pct": _r(_mean(vals)), "win_rate": _r(len(wins)/len(vals) if vals else None), "loss_rate": _r(len(losses)/len(vals) if vals else None), "average_win": _r(_mean(wins)), "average_loss": _r(_mean(losses)), "payoff_ratio": _r((_mean(wins) or 0)/abs(_mean(losses) or 1)) if losses else None, "profit_factor": _r(gross_profit/gross_loss) if gross_loss else None, "maximum_loss": _r(min(vals) if vals else None), "downside_p5": _r(_q(vals,.05)), "cvar_pct": _r(_cvar(vals)), "average_holding_days": _r(_mean(hold)), "median_holding_days": _r(_median(hold)), "premature_stop_rate": _r(prem/sl_first if sl_first else None), "warnings": []}

def score_joint(m: dict[str,Any], weights: dict[str,float]) -> float:
    if not m.get("episode_count"):
        return -999999.0
    exp=(m.get("expectancy_pct") or 0)/20; downside=-abs(m.get("downside_p5") or 0)/30; cvar=-abs(m.get("cvar_pct") or 0)/30; prem=-(m.get("premature_stop_rate") or 0)
    return _r(weights.get("expectancy",0)*exp+weights.get("downside",0)*downside+weights.get("cvar",0)*cvar+weights.get("premature",0)*prem) or 0

def extreme_winner_metrics(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"top_1_contribution": None, "top_5_contribution": None, "top_10_pct_contribution": None, "expectancy_excluding_best_trade": None, "expectancy_excluding_top_5_pct": None, "trimmed_mean_return": None, "median_return": None, "return_skewness": None, "maximum_winning_trade": None, "maximum_losing_trade": None, "warning": "insufficient_sample"}
    positives = sorted([v for v in values if v > 0], reverse=True)
    total = sum(values)
    sorted_values = sorted(values, reverse=True)
    top_5_n = max(1, int(len(values) * 0.05))
    trim_n = max(1, int(len(values) * 0.05)) if len(values) >= 20 else 0
    trimmed = sorted(values)[trim_n:len(values)-trim_n] if trim_n else values
    mean = _mean(values) or 0.0
    stdev = statistics.pstdev(values) if len(values) > 1 else 0.0
    skew = None if stdev == 0 else sum(((v - mean) / stdev) ** 3 for v in values) / len(values)
    def contrib(items: list[float]) -> float | None:
        if total <= 0:
            return None
        return _r(sum(items) / total)
    concentration = contrib(sorted_values[:top_5_n])
    return {"top_1_contribution": contrib(sorted_values[:1]), "top_5_contribution": contrib(sorted_values[:5]), "top_10_pct_contribution": contrib(sorted_values[:max(1, int(len(values)*0.10))]), "expectancy_excluding_best_trade": _r(_mean(sorted_values[1:])), "expectancy_excluding_top_5_pct": _r(_mean(sorted_values[top_5_n:])), "trimmed_mean_return": _r(_mean(trimmed)), "median_return": _r(_median(values)), "return_skewness": _r(skew), "maximum_winning_trade": _r(max(values)), "maximum_losing_trade": _r(min(values)), "warning": "extreme_winner_dependency" if concentration is not None and concentration > 0.5 else None}

def boundary_analysis(best_pair: dict[str, Any] | None, fixed_sl: list[float]) -> dict[str, Any]:
    if not best_pair:
        return {"selected_at_boundary": None}
    sl = best_pair["sl_candidate"]
    if sl["type"] != "fixed_pct":
        return {"candidate_grid_minimum": min(fixed_sl), "candidate_grid_maximum": max(fixed_sl), "selected_at_boundary": False, "boundary_warning": None, "local_robustness_score": None}
    value = float(sl["value"])
    at_boundary = value in {min(fixed_sl), max(fixed_sl)}
    return {"candidate_grid_minimum": min(fixed_sl), "candidate_grid_maximum": max(fixed_sl), "selected_at_boundary": at_boundary, "boundary_warning": "best candidate is at grid boundary" if at_boundary else None, "neighboring_candidate_performance": [], "local_robustness_score": None}

def build_sl_optimizer_artifact(ticker: str, episodes_path: Path, tp_path: Path, fixed_sl: list[float], atr_multiples: list[float], fold_count:int=4, same_day_policy:str="stop_first", random_seed:int=42, bootstrap_iterations:int=200, minimum_sample_size:int=30, minimum_fold_count:int=2, minimum_oos_expectancy:float=0.0, minimum_profitable_fold_ratio:float=0.5, maximum_cvar:float=-20.0, maximum_premature_stop_rate:float=0.8, maximum_ambiguity_rate:float=0.05, selection_weights:dict[str,float]|None=None) -> dict[str,Any]:
    ep_art=load_episode_artifact(episodes_path,ticker); tp_art=load_tp_artifact(tp_path,ticker); weights=selection_weights or DEFAULT_WEIGHTS
    episodes=[e for e in ep_art["episodes"] if e.get("complete_horizon")]
    tp_candidates=tp_art.get("config",{}).get("candidates") or [c["tp_pct"] for c in tp_art.get("candidates",[])]
    sl_candidates=[{"type":"fixed_pct","value":float(v)} for v in fixed_sl]+[{"type":"atr_multiple","value":float(v)} for v in atr_multiples]
    standalone=[standalone_metrics(episodes,c,tp_candidates,same_day_policy) for c in sl_candidates]
    matrix=[joint_metrics(episodes,tp,c,same_day_policy,tp_candidates) for tp in tp_candidates for c in sl_candidates]
    best_sl=sorted(standalone,key=lambda m: ((m.get("cvar_pct") or -999), (m.get("premature_stop_rate") or 1)), reverse=True)[0] if standalone else None
    scored=[]
    for m in matrix:
        x=dict(m); x["selection_score"]=score_joint(m,weights); scored.append(x)
    best_pair=sorted(scored,key=lambda m:m["selection_score"], reverse=True)[0] if scored else None
    folds=[]
    for f in build_chronological_folds([{"entry_date":e["entry_date"], **e} for e in episodes], fold_count):
        train=f["train_events"]; val=f["validation_events"]
        train_matrix=[joint_metrics(train,tp,c,same_day_policy,tp_candidates) for tp in tp_candidates for c in sl_candidates]
        train_best=sorted([{**m,"selection_score":score_joint(m,weights)} for m in train_matrix], key=lambda m:m["selection_score"], reverse=True)[0]
        val_result=joint_metrics(val, train_best["tp_pct"], train_best["sl_candidate"], same_day_policy,tp_candidates)
        folds.append({"fold_id":f["fold_id"],"train_start":f["train_start"],"train_end":f["train_end"],"validation_start":f["validation_start"],"validation_end":f["validation_end"],"train_episode_count":len(train),"validation_episode_count":len(val),"purge_window":ep_art["config"].get("horizon_days"),"embargo_window":0,"leakage_check":"passed" if f["train_end"]<f["validation_start"] else "failed","selected_sl_candidate":train_best["sl_candidate"],"selected_tp_sl_pair":{"tp_pct":train_best["tp_pct"],"sl_candidate":train_best["sl_candidate"]},"validation_result":val_result,"warnings":[]})
    fold_exp=[f["validation_result"].get("expectancy_pct") for f in folds if f["validation_result"].get("expectancy_pct") is not None]
    pair_freq: dict[str, int] = {}
    family_freq: dict[str, int] = {}
    for fold in folds:
        pair = fold.get("selected_tp_sl_pair", {})
        sl = pair.get("sl_candidate", {})
        key = f"tp={pair.get('tp_pct')}|{sl.get('type')}={sl.get('value')}"
        pair_freq[key] = pair_freq.get(key, 0) + 1
        family = str(sl.get("type"))
        family_freq[family] = family_freq.get(family, 0) + 1
    ci=confidence_intervals([float(v) for v in fold_exp], random_seed, bootstrap_iterations)
    prof_num=len([v for v in fold_exp if v>0]); prof_den=len(fold_exp); prof_ratio=(prof_num/prof_den) if prof_den else None
    warnings=[]; critical=[]
    same_day=sum(m["ambiguous_count"] for m in matrix); total=sum(m["episode_count"] for m in matrix) or 1
    if len(episodes)<minimum_sample_size: warnings.append("sample size below minimum")
    if len(folds)<minimum_fold_count: warnings.append("fold count below minimum")
    if ci["expectancy_pct"].get("lower") is None: warnings.append("expectancy CI unavailable")
    elif ci["expectancy_pct"]["lower"]<=minimum_oos_expectancy: warnings.append("expectancy CI lower bound below minimum")
    if prof_ratio is None or prof_ratio<minimum_profitable_fold_ratio: warnings.append("profitable fold ratio below minimum")
    if fold_exp and min(fold_exp)<maximum_cvar: warnings.append("worst fold expectancy below limit")
    if best_pair and (best_pair.get("cvar_pct") is not None and best_pair["cvar_pct"]<maximum_cvar): warnings.append("CVaR below limit")
    if best_pair and (best_pair.get("premature_stop_rate") or 0)>maximum_premature_stop_rate: warnings.append("premature stop rate above limit")
    if same_day/total>maximum_ambiguity_rate: warnings.append("same-day ambiguity above limit")
    if not tp_art.get("quality",{}).get("usable_for_decision",False): warnings.append("source TP artifact not decision usable")
    cost_model={"entry_fee_pct":0.0,"exit_fee_pct":0.0,"exit_tax_pct":0.0,"entry_slippage_pct":0.0,"exit_slippage_pct":0.0,"minimum_fixed_cost":0.0}
    if _cost_pct(cost_model)==0: warnings.append("execution costs disabled")
    atr_excluded=sum(m["excluded_episode_count"] for m in standalone if m["candidate"]["type"]=="atr_multiple")
    atr_total=max(1, len(atr_multiples)*len(episodes))
    atr_coverage=1-(atr_excluded/atr_total)
    family_quality={"fixed_pct":{"coverage":1.0 if episodes else None,"usable_for_risk_analysis":bool(episodes),"warnings":[]},"atr":{"coverage":_r(atr_coverage),"usable_for_risk_analysis":atr_coverage>=0.8,"warnings":[] if atr_coverage>=0.8 else ["ATR coverage below minimum"]},"mae_quantile":{"coverage":0.0,"usable_for_risk_analysis":False,"warnings":["not implemented in Sprint 4.1"]}}
    boundary=boundary_analysis(best_pair, fixed_sl)
    if boundary.get("selected_at_boundary"): warnings.append("best candidate at grid boundary")
    best_values=[]
    if best_pair:
        for ep in episodes:
            sl=sl_pct_for_candidate(ep,best_pair["sl_candidate"])
            if sl is not None:
                sim=simulate_episode(ep,sl,best_pair["tp_pct"],same_day_policy,cost_model)
                if sim.get("net_realized_return_pct") is not None: best_values.append(float(sim["net_realized_return_pct"]))
    extreme=extreme_winner_metrics(best_values)
    if extreme.get("warning"): warnings.append(extreme["warning"])
    risk_usable=len(episodes)>=minimum_sample_size and len(folds)>=minimum_fold_count and not critical
    decision_usable=risk_usable and not warnings
    return {"schema_version":SCHEMA_VERSION,"artifact_type":"sl_optimizer","ticker":ticker.upper(),"generated_at":datetime.now(timezone.utc).isoformat(),"generator_version":GENERATOR_VERSION,"config":{"fixed_sl":fixed_sl,"atr_multiples":atr_multiples,"fold_count":fold_count,"same_day_policy":same_day_policy,"selection_weights":weights,"random_seed":random_seed,"bootstrap_iterations":bootstrap_iterations,"minimum_sample_size":minimum_sample_size,"minimum_fold_count":minimum_fold_count,"minimum_oos_expectancy":minimum_oos_expectancy,"minimum_profitable_fold_ratio":minimum_profitable_fold_ratio,"maximum_cvar":maximum_cvar,"maximum_premature_stop_rate":maximum_premature_stop_rate,"maximum_ambiguity_rate":maximum_ambiguity_rate},"execution_model":{"fill_policy":"gap_aware_daily_ohlcv","same_day_policy":same_day_policy,"primary_policy":"stop_first"},"transaction_cost_model":cost_model,"atr_provenance":{"method":"entry_feature_snapshot_atr","lookback":None,"source_checksum":sha256_file(episodes_path),"atr_eligible_episode_count":len(episodes)-atr_excluded//max(1,len(atr_multiples)),"atr_excluded_episode_count":atr_excluded//max(1,len(atr_multiples)),"atr_coverage_rate":_r(atr_coverage),"exclusion_reasons":{"missing_or_invalid_atr":atr_excluded}},"family_quality":family_quality,"source_policy":{"tp_schema_valid":tp_art.get("schema_version")=="tp_optimizer_v1","tp_candidate_provenance_valid":bool(tp_candidates),"standalone_tp_decision_usable_required":False,"decision_usability_requires_joint_gates":True},"source":{"episode_artifact_path":str(episodes_path),"episode_artifact_schema":ep_art.get("schema_version"),"episode_artifact_checksum":sha256_file(episodes_path),"tp_artifact_path":str(tp_path),"tp_artifact_schema":tp_art.get("schema_version"),"tp_artifact_checksum":sha256_file(tp_path),"ohlcv_source_checksum":ep_art.get("source",{}).get("ohlcv_checksum"),"data_start":episodes[0]["entry_date"] if episodes else None,"data_end":episodes[-1]["entry_date"] if episodes else None,"sampling_policy":ep_art.get("config",{}).get("primary_policy"),"entry_policy":ep_art.get("config",{}).get("entry_timing"),"research_horizon":ep_art.get("config",{}).get("horizon_days")},"exclusions":{"incomplete_episode": ep_art.get("exclusions",{}).get("insufficient_future_ohlcv",0),"atr_missing_or_invalid":atr_excluded},"standalone_candidates":standalone,"joint_tp_sl_matrix":scored,"folds":folds,"nested_walk_forward":{"outer_folds":folds,"pair_selection_frequency":pair_freq,"candidate_family_selection_frequency":family_freq,"evaluated_outer_fold_count":len(folds),"profitable_outer_fold_ratio":_r(prof_ratio),"worst_outer_fold_expectancy":_r(min(fold_exp) if fold_exp else None),"median_outer_fold_expectancy":_r(_median(fold_exp)),"performance_dispersion":_r(statistics.pstdev(fold_exp) if len(fold_exp)>1 else None)},"stability":{"profitable_fold_numerator":prof_num,"profitable_fold_denominator":prof_den,"profitable_fold_ratio":_r(prof_ratio),"worst_fold_expectancy":_r(min(fold_exp) if fold_exp else None)},"confidence_intervals":ci,"gross_metrics":best_pair,"net_metrics":best_pair,"gap_metrics":{"stop_gap_count":sum(1 for m in scored for _ in []),"target_gap_count":0,"average_adverse_stop_gap":None,"worst_adverse_stop_gap":None,"average_favorable_target_gap":None},"boundary_analysis":boundary,"extreme_winner_analysis":extreme,"best_sl_candidate_by_score":best_sl,"best_tp_sl_pair_by_score":best_pair,"best_gross_joint_pair":best_pair,"best_net_joint_pair":best_pair,"best_candidate_by_research_score":best_pair,"most_frequent_nested_pair":None,"selected": best_pair if decision_usable else None,"quality":{"status":"valid" if decision_usable else "research_only","usable_for_risk_analysis":risk_usable,"usable_for_decision":decision_usable,"usable_for_fixed_risk_analysis":family_quality["fixed_pct"]["usable_for_risk_analysis"],"usable_for_atr_risk_analysis":family_quality["atr"]["usable_for_risk_analysis"],"episode_count":len(episodes),"eligible_episode_count":len(episodes),"fold_count":len(folds),"warnings":warnings,"critical_warnings":critical},"critical_warnings":critical,"warnings":warnings,"notes":["Research evidence only; not a BUY/SELL signal.","TP candidate list may be used for joint research even when standalone TP artifact is research_only."]}

def validate_sl_optimizer_artifact(a:dict[str,Any], episodes_path:Path|None=None, tp_path:Path|None=None)->None:
    if a.get("schema_version")!=SCHEMA_VERSION: raise ValueError("invalid sl schema")
    if a.get("artifact_type")!="sl_optimizer": raise ValueError("invalid artifact type")
    if episodes_path and sha256_file(episodes_path)!=a["source"]["episode_artifact_checksum"]: raise ValueError("episode checksum mismatch")
    if tp_path and sha256_file(tp_path)!=a["source"]["tp_artifact_checksum"]: raise ValueError("tp checksum mismatch")
    if a["quality"]["usable_for_decision"] and a.get("selected") is None: raise ValueError("selected required when decision usable")
    if not a["quality"]["usable_for_decision"] and a.get("selected") is not None: raise ValueError("selected must be null when not decision usable")

def parse_args(argv:Iterable[str]|None=None)->argparse.Namespace:
    p=argparse.ArgumentParser(description="Build SL optimizer research artifact.")
    p.add_argument("--ticker",required=True); p.add_argument("--episodes",required=True,type=Path); p.add_argument("--tp-artifact",required=True,type=Path); p.add_argument("--output-dir",type=Path,default=Path("storage/app/trading_research/sl_optimizer")); p.add_argument("--fixed-sl",nargs="+",type=float,default=DEFAULT_FIXED_SL); p.add_argument("--atr-multiple",nargs="+",type=float,default=DEFAULT_ATR_MULTIPLES); p.add_argument("--fold-count",type=int,default=4); p.add_argument("--same-day-policy",choices=["stop_first","target_first","ambiguous_exclude"],default="stop_first"); p.add_argument("--minimum-sample",type=int,default=30); p.add_argument("--minimum-fold",type=int,default=2); p.add_argument("--minimum-oos-expectancy",type=float,default=0.0); p.add_argument("--minimum-profitable-fold-ratio",type=float,default=0.5); p.add_argument("--maximum-cvar",type=float,default=-20.0); p.add_argument("--maximum-premature-stop-rate",type=float,default=0.8); p.add_argument("--maximum-ambiguity-rate",type=float,default=0.05); p.add_argument("--bootstrap-iterations",type=int,default=200); p.add_argument("--random-seed",type=int,default=42); p.add_argument("--overwrite",action="store_true",default=False); return p.parse_args(argv)

def main(argv:Iterable[str]|None=None)->int:
    args=parse_args(argv); art=build_sl_optimizer_artifact(args.ticker,args.episodes,args.tp_artifact,args.fixed_sl,args.atr_multiple,args.fold_count,args.same_day_policy,args.random_seed,args.bootstrap_iterations,args.minimum_sample,args.minimum_fold,args.minimum_oos_expectancy,args.minimum_profitable_fold_ratio,args.maximum_cvar,args.maximum_premature_stop_rate,args.maximum_ambiguity_rate); validate_sl_optimizer_artifact(art,args.episodes,args.tp_artifact); path=args.output_dir/f"{args.ticker.upper()}_sl_optimizer_v1.json"; write_json(art,path,overwrite=args.overwrite); print(path); return 0
if __name__=="__main__": raise SystemExit(main())
