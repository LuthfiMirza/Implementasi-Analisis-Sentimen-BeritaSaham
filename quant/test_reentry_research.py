from __future__ import annotations
import copy, json, tempfile, unittest
from pathlib import Path
import pandas as pd
from quant.trading_research.artifact_utils import write_json
from quant.trading_research.trade_episode_dataset import build_trade_episode_dataset
from quant.trading_research.reentry_research import build_reentry_artifact, validate_reentry_artifact, candidate_eval, main
from quant.trading_research.walk_forward_event_dataset import SCHEMA_VERSION

def _ohlcv(days=120):
    dates=pd.bdate_range('2024-01-01',periods=days); base=[100+i*.3 for i in range(days)]
    return pd.DataFrame({'date':dates,'open':base,'high':[v+5 for v in base],'low':[v-5 for v in base],'close':[v+1 for v in base],'volume':[1000]*days})
def _event(d,i):
    return {'entry_date':d,'entry_price':100.0,'holding_days':20,'highest_price':110.0,'lowest_price':95.0,'exit_price':103.0,'return_pct':3.0,'mfe_pct':10.0,'mae_pct':-5.0,'drawdown_pct':-5.0,'recovery_pct':8.0,'atr':2.0,'rsi':50.0,'macd':0.0,'adx':20.0,'vwap':100.0,'volume_ratio':1.0,'market_regime':'bull','news_sentiment':0.0,'prediction_probability':0.7,'prediction_variant':'syn','trade_outcome':'win'}
def _event_art(dates,t='BUMI'):
    return {'schema_version':SCHEMA_VERSION,'artifact_type':'walk_forward_event_dataset','ticker':t,'generated_at':'x','config':{'holding_days':20},'events':[_event(d,i) for i,d in enumerate(dates)],'quality':{'event_count':len(dates),'status':'research_dataset'}}
def _sl_art(t='BUMI'):
    return {'schema_version':'sl_optimizer_v1_1','artifact_type':'sl_optimizer','ticker':t,'generated_at':'x','nested_walk_forward':{'outer_folds':[{}]},'quality':{'usable_for_decision':False},'best_net_joint_pair':{'tp_pct':5.0,'sl_candidate':{'type':'fixed_pct','value':3.0}}}
def _fixtures(root,t='BUMI'):
    dates=pd.bdate_range('2024-01-01',periods=50).strftime('%Y-%m-%d').tolist(); ev=root/'events.json'; oh=root/'ohlcv.csv'; sl=root/'sl.json'; out=root/'episodes'
    write_json(_event_art(dates,t),ev,overwrite=True); _ohlcv().to_csv(oh,index=False); write_json(_sl_art(t),sl,overwrite=True); build_trade_episode_dataset(ev,oh,out,horizon_days=10,overwrite=True)
    return out/f'{t}_trade_episodes_v1.json', sl, oh
class ReentryResearchTestCase(unittest.TestCase):
    def test_valid_sources_and_artifact(self):
        with tempfile.TemporaryDirectory() as d:
            ep,sl,oh=_fixtures(Path(d)); art=build_reentry_artifact('BUMI',ep,sl,oh,extension_days=20)
            validate_reentry_artifact(art,ep,sl); self.assertEqual('reentry_research_v1_1',art['schema_version'])
    def test_ticker_mismatch_and_checksum(self):
        with tempfile.TemporaryDirectory() as d:
            ep,sl,oh=_fixtures(Path(d));
            with self.assertRaisesRegex(ValueError,'ticker mismatch'): build_reentry_artifact('DEWA',ep,sl,oh)
            art=build_reentry_artifact('BUMI',ep,sl,oh); art['source']['sl_artifact_checksum']='bad'
            with self.assertRaisesRegex(ValueError,'sl checksum mismatch'): validate_reentry_artifact(art,ep,sl)
    def test_after_stop_tp_timeout_streams_exist(self):
        with tempfile.TemporaryDirectory() as d:
            ep,sl,oh=_fixtures(Path(d)); art=build_reentry_artifact('BUMI',ep,sl,oh,extension_days=20)
            self.assertIn('stopped_episode_count',art['recovery_after_stop']); self.assertIn('tp_exit_episode_count',art['pullback_after_tp']); self.assertIn('timeout_episode_count',art['continuation_after_timeout'])
    def test_cost_profiles_and_incremental_value(self):
        with tempfile.TemporaryDirectory() as d:
            ep,sl,oh=_fixtures(Path(d)); episodes=json.loads(ep.read_text())['episodes'][:3]; frame=pd.read_csv(oh)
            from quant.trading_research.chronological_trade_simulator import prepare_ohlcv
            m0=candidate_eval(episodes,prepare_ohlcv(frame),5.0,{'type':'fixed_pct','value':3.0},3,20,{'entry_fee_pct':0,'exit_fee_pct':0,'tax_pct':0,'entry_slippage_pct':0,'exit_slippage_pct':0})
            m1=candidate_eval(episodes,prepare_ohlcv(frame),5.0,{'type':'fixed_pct','value':3.0},3,20,{'entry_fee_pct':1,'exit_fee_pct':1,'tax_pct':0,'entry_slippage_pct':0,'exit_slippage_pct':0})
            self.assertLessEqual(m1['incremental_expectancy'] or -999, m0['incremental_expectancy'] or 999)
    def test_nested_walk_forward_and_quality_selected_null(self):
        with tempfile.TemporaryDirectory() as d:
            ep,sl,oh=_fixtures(Path(d)); art=build_reentry_artifact('BUMI',ep,sl,oh,extension_days=20,fold_count=3)
            self.assertTrue(art['nested_walk_forward']['outer_folds']); self.assertIsNone(art['selected']); self.assertFalse(art['quality']['usable_for_decision'])
    def test_cli_output(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); ep,sl,oh=_fixtures(root); code=main(['--ticker','BUMI','--episodes',str(ep),'--sl-artifact',str(sl),'--ohlcv',str(oh),'--output-dir',str(root/'reentry'),'--extension-days','20','--overwrite'])
            self.assertEqual(0,code); self.assertTrue((root/'reentry'/'BUMI_reentry_research_v1_1.json').exists())
    def test_stale_sl_schema_rejected_by_default(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); ep,sl,oh=_fixtures(root); stale=_sl_art(); stale['schema_version']='sl_optimizer_v1'; write_json(stale,sl,overwrite=True)
            with self.assertRaisesRegex(ValueError,'invalid SL schema'): build_reentry_artifact('BUMI',ep,sl,oh)
    def test_unclassified_reason_reconciliation_validator(self):
        with tempfile.TemporaryDirectory() as d:
            ep,sl,oh=_fixtures(Path(d)); art=build_reentry_artifact('BUMI',ep,sl,oh,extension_days=20)
            total=sum(art['episode_accounting']['unclassified_reasons'].values())
            self.assertEqual(total,art['episode_accounting']['unclassified_count'])
            bad=copy.deepcopy(art); bad['episode_accounting']['unclassified_reasons']['other']+=1
            with self.assertRaisesRegex(ValueError,'unclassified reasons mismatch'): validate_reentry_artifact(bad,ep,sl)
    def test_top_level_summary_and_stream_owned_ci(self):
        with tempfile.TemporaryDirectory() as d:
            ep,sl,oh=_fixtures(Path(d)); art=build_reentry_artifact('BUMI',ep,sl,oh,extension_days=20)
            self.assertEqual({},art['confidence_intervals'])
            self.assertIn('after_stop',art['summary']['stream_statuses'])
            for stream,metric in art['stream_accounting'].items():
                self.assertEqual(metric['ci_sample_count'],metric['expectancy_ci']['observation_count'],stream)
                self.assertEqual('outer_validation_incremental_returns',metric['expectancy_ci']['sample_identity'])
            bad=copy.deepcopy(art); bad['confidence_intervals']={'expectancy_pct':{'lower':0,'upper':1}}
            with self.assertRaisesRegex(ValueError,'top-level CI'): validate_reentry_artifact(bad,ep,sl)
    def test_atr_configured_but_not_evaluated_when_unavailable(self):
        with tempfile.TemporaryDirectory() as d:
            ep,sl,oh=_fixtures(Path(d)); art=build_reentry_artifact('BUMI',ep,sl,oh,extension_days=20)
            atr=art['family_quality']['atr_pullback']
            self.assertEqual('implemented_but_unavailable',atr['implementation_status'])
            self.assertGreater(len(atr['configured_candidates']),0)
            self.assertEqual([],atr['evaluated_candidates'])
            self.assertEqual(0,atr['evaluated_candidate_count'])
            self.assertFalse(atr['usable_for_reentry_research'])
            bad=copy.deepcopy(art); bad['family_quality']['atr_pullback']['evaluated_candidate_count']=1
            with self.assertRaisesRegex(ValueError,'ATR zero coverage'): validate_reentry_artifact(bad,ep,sl)
    def test_stream_metrics_not_global_copy(self):
        with tempfile.TemporaryDirectory() as d:
            ep,sl,oh=_fixtures(Path(d)); art=build_reentry_artifact('BUMI',ep,sl,oh,extension_days=20)
            self.assertNotIn('incremental_expectancy',art['summary'])
            self.assertIn('stream_validation_metrics',art['nested_walk_forward']['outer_folds'][0])
            streams=art['nested_walk_forward']['outer_folds'][0]['stream_validation_metrics']
            self.assertEqual({'after_stop','after_tp','after_timeout'},set(streams))
    def test_unclassified_rate_warning_disables_research(self):
        with tempfile.TemporaryDirectory() as d:
            ep,sl,oh=_fixtures(Path(d)); art=build_reentry_artifact('BUMI',ep,sl,oh,extension_days=20,maximum_unclassified_rate=0.0)
            if art['episode_accounting']['unclassified_count']>0:
                self.assertIn('unclassified rate above maximum',art['warnings'])
                self.assertFalse(art['quality']['usable_for_reentry_research'])
if __name__=='__main__': unittest.main()
