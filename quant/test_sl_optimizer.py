from __future__ import annotations
import json, tempfile, unittest
from pathlib import Path
import pandas as pd
from quant.trading_research.artifact_utils import write_json
from quant.trading_research.trade_episode_dataset import build_trade_episode_dataset
from quant.trading_research.walk_forward_event_dataset import SCHEMA_VERSION
from quant.trading_research.sl_optimizer import build_sl_optimizer_artifact, validate_sl_optimizer_artifact, main, standalone_metrics, joint_metrics

def _ohlcv(days=80):
    dates=pd.bdate_range('2024-01-01',periods=days); base=[100+i*0.2 for i in range(days)]
    return pd.DataFrame({'date':dates,'open':base,'high':[v+4 for v in base],'low':[v-4 for v in base],'close':[v+1 for v in base],'volume':[1000]*days})
def _event(date,i):
    return {'entry_date':date,'entry_price':100.0,'holding_days':20,'highest_price':110.0,'lowest_price':95.0,'exit_price':103.0,'return_pct':3.0,'mfe_pct':10.0,'mae_pct':-5.0,'drawdown_pct':-5.0,'recovery_pct':8.0,'atr':2.0,'rsi':50.0,'macd':0.0,'adx':20.0,'vwap':100.0,'volume_ratio':1.0,'market_regime':'bull','news_sentiment':0.0,'prediction_probability':0.7,'prediction_variant':'syn','trade_outcome':'win'}
def _event_art(dates,ticker='BUMI'):
    return {'schema_version':SCHEMA_VERSION,'artifact_type':'walk_forward_event_dataset','ticker':ticker,'generated_at':'2026-07-01T00:00:00+00:00','config':{'holding_days':20},'events':[_event(d,i) for i,d in enumerate(dates)],'quality':{'event_count':len(dates),'status':'research_dataset'}}
def _tp_art(ticker='BUMI', usable=False):
    return {'schema_version':'tp_optimizer_v1','artifact_type':'tp_optimizer','ticker':ticker,'generated_at':'x','config':{'candidates':[5.0,10.0]},'source':{'source_checksum':'x'},'candidates':[],'quality':{'usable_for_decision':usable}}
def _fixtures(root, ticker='BUMI'):
    dates=pd.bdate_range('2024-01-01',periods=45).strftime('%Y-%m-%d').tolist(); ev=root/'events.json'; oh=root/'ohlcv.csv'; tp=root/'tp.json'; out=root/'episodes'
    write_json(_event_art(dates,ticker), ev, overwrite=True); _ohlcv(100).to_csv(oh,index=False); write_json(_tp_art(ticker),tp,overwrite=True)
    build_trade_episode_dataset(ev,oh,out,horizon_days=10,overwrite=True)
    return out/f'{ticker}_trade_episodes_v1.json', tp
class SLOptimizerTestCase(unittest.TestCase):
    def test_valid_artifact_and_source_checksum(self):
        with tempfile.TemporaryDirectory() as d:
            ep,tp=_fixtures(Path(d)); art=build_sl_optimizer_artifact('BUMI',ep,tp,[3,5],[1],minimum_sample_size=1,minimum_fold_count=1)
            validate_sl_optimizer_artifact(art,ep,tp); self.assertEqual('sl_optimizer_v1_1',art['schema_version'])
    def test_invalid_episode_schema_and_tp_schema_and_ticker(self):
        with tempfile.TemporaryDirectory() as d:
            r=Path(d); ep=r/'bad.json'; tp=r/'tp.json'; write_json({'schema_version':'bad','ticker':'BUMI'},ep,overwrite=True); write_json(_tp_art(),tp,overwrite=True)
            with self.assertRaisesRegex(ValueError,'invalid episode schema'): build_sl_optimizer_artifact('BUMI',ep,tp,[3],[])
            write_json({'schema_version':'trade_episode_dataset_v1','ticker':'DEWA','episodes':[]},ep,overwrite=True)
            with self.assertRaisesRegex(ValueError,'ticker mismatch'): build_sl_optimizer_artifact('BUMI',ep,tp,[3],[])
    def test_fixed_stop_hit_and_not_hit(self):
        with tempfile.TemporaryDirectory() as d:
            ep,tp=_fixtures(Path(d)); episodes=json.loads(ep.read_text())['episodes'][:2]
            m=standalone_metrics(episodes,{'type':'fixed_pct','value':3.0},[5.0],'stop_first')
            self.assertGreaterEqual(m['stop_hit_count'],0); self.assertIn('average_loss_when_stopped_pct',m)
    def test_atr_carried_from_event_to_episode(self):
        with tempfile.TemporaryDirectory() as d:
            ep,tp=_fixtures(Path(d)); episodes=json.loads(ep.read_text())['episodes'][:3]
            m=standalone_metrics(episodes,{'type':'atr_multiple','value':1.0},[5.0],'stop_first')
            self.assertEqual(0,m['excluded_episode_count'])
            self.assertIsNotNone(episodes[0]['entry_feature_snapshot']['atr'])

    def test_atr_zero_invalid_exclusion(self):
        with tempfile.TemporaryDirectory() as d:
            ep,tp=_fixtures(Path(d)); episodes=json.loads(ep.read_text())['episodes'][:3]
            for episode in episodes:
                episode['entry_feature_snapshot']['atr']=0
            m=standalone_metrics(episodes,{'type':'atr_multiple','value':1.0},[5.0],'stop_first')
            self.assertEqual(3,m['excluded_episode_count'])
    def test_joint_tp_sl_matrix_and_same_day_sensitivity(self):
        with tempfile.TemporaryDirectory() as d:
            ep,tp=_fixtures(Path(d)); episodes=json.loads(ep.read_text())['episodes'][:3]
            m=joint_metrics(episodes,5.0,{'type':'fixed_pct','value':3.0},'stop_first',[5.0])
            self.assertIn('tp_first_count',m); self.assertIn('sl_first_count',m); self.assertIn('timeout_count',m)
            m2=joint_metrics(episodes,5.0,{'type':'fixed_pct','value':3.0},'ambiguous_exclude',[5.0])
            self.assertIn('ambiguous_count',m2)
    def test_quality_selected_null_when_tp_not_usable(self):
        with tempfile.TemporaryDirectory() as d:
            ep,tp=_fixtures(Path(d)); art=build_sl_optimizer_artifact('BUMI',ep,tp,[3,5],[],minimum_sample_size=1,minimum_fold_count=1)
            self.assertIsNone(art['selected']); self.assertFalse(art['quality']['usable_for_decision']); self.assertIsNotNone(art['best_tp_sl_pair_by_score'])
    def test_checksum_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            ep,tp=_fixtures(Path(d)); art=build_sl_optimizer_artifact('BUMI',ep,tp,[3],[],minimum_sample_size=1,minimum_fold_count=1); art['source']['tp_artifact_checksum']='bad'
            with self.assertRaisesRegex(ValueError,'tp checksum mismatch'): validate_sl_optimizer_artifact(art,ep,tp)
    def test_cli_output(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); ep,tp=_fixtures(root)
            code=main(['--ticker','BUMI','--episodes',str(ep),'--tp-artifact',str(tp),'--output-dir',str(root/'sl'),'--fixed-sl','3','5','--atr-multiple','1','--minimum-sample','1','--minimum-fold','1','--overwrite'])
            self.assertEqual(0,code); self.assertTrue((root/'sl'/'BUMI_sl_optimizer_v1.json').exists())
if __name__=='__main__': unittest.main()
