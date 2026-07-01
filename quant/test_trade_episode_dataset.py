from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.trading_research.artifact_utils import write_json
from quant.trading_research.chronological_trade_simulator import prepare_ohlcv, simulate_path
from quant.trading_research.trade_episode_dataset import build_trade_episode_dataset, main as episode_main
from quant.trading_research.tp_optimizer import build_tp_optimizer_artifact, TPOptimizerConfig, validate_tp_optimizer_artifact
from quant.trading_research.walk_forward_event_dataset import SCHEMA_VERSION


def _ohlcv(days: int = 40) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-01", periods=days)
    return pd.DataFrame({"date": dates, "open": [100 + i for i in range(days)], "high": [102 + i for i in range(days)], "low": [98 + i for i in range(days)], "close": [101 + i for i in range(days)], "volume": [1000] * days})


def _event(date: str, idx: int) -> dict:
    return {"entry_date": date, "entry_price": 100.0, "holding_days": 20, "highest_price": 110.0, "lowest_price": 95.0, "exit_price": 103.0, "return_pct": 3.0, "mfe_pct": 10.0, "mae_pct": -5.0, "drawdown_pct": -5.0, "recovery_pct": 8.0, "atr": 1.0, "rsi": 50.0, "macd": 0.0, "adx": 20.0, "vwap": 100.0, "volume_ratio": 1.0, "market_regime": "bull", "news_sentiment": 0.0, "prediction_probability": 0.7, "prediction_variant": "synthetic", "trade_outcome": "win"}


def _artifact(dates: list[str], ticker: str = "BUMI") -> dict:
    events = [_event(date, i) for i, date in enumerate(dates)]
    return {"schema_version": SCHEMA_VERSION, "artifact_type": "walk_forward_event_dataset", "ticker": ticker, "generated_at": "2026-07-01T00:00:00+00:00", "config": {"holding_days": 20}, "events": events, "quality": {"event_count": len(events), "status": "research_dataset"}}


class TradeEpisodeDatasetTestCase(unittest.TestCase):
    def test_continuous_buy_sequence_one_signal_transition_episode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir); events = root / "events.json"; ohlcv = root / "ohlcv.csv"
            dates = pd.bdate_range("2024-01-01", periods=5).strftime("%Y-%m-%d").tolist()
            write_json(_artifact(dates), events, overwrite=True); _ohlcv(30).to_csv(ohlcv, index=False)
            artifact = build_trade_episode_dataset(events, ohlcv, horizon_days=5, primary_policy="signal_transition")
            self.assertEqual(1, artifact["episode_summary"]["signal_transition_episode_count"])

    def test_one_position_policy_ignores_active_trade(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir); events = root / "events.json"; ohlcv = root / "ohlcv.csv"
            dates = pd.bdate_range("2024-01-01", periods=25).strftime("%Y-%m-%d").tolist()
            write_json(_artifact(dates), events, overwrite=True); _ohlcv(60).to_csv(ohlcv, index=False)
            artifact = build_trade_episode_dataset(events, ohlcv, horizon_days=10)
            self.assertLess(artifact["episode_summary"]["one_position_episode_count"], len(dates))
            self.assertFalse(artifact["quality"]["primary_policy_has_concurrent_position"])

    def test_fixed_spacing_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir); events = root / "events.json"; ohlcv = root / "ohlcv.csv"
            dates = pd.bdate_range("2024-01-01", periods=20).strftime("%Y-%m-%d").tolist()
            write_json(_artifact(dates), events, overwrite=True); _ohlcv(50).to_csv(ohlcv, index=False)
            artifact = build_trade_episode_dataset(events, ohlcv, horizon_days=5, primary_policy="fixed_spacing", fixed_spacing_days=5)
            self.assertEqual(4, artifact["episode_summary"]["fixed_spacing_episode_count"])

    def test_next_day_entry_uses_next_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir); events = root / "events.json"; ohlcv = root / "ohlcv.csv"
            write_json(_artifact(["2024-01-01"]), events, overwrite=True); _ohlcv(10).to_csv(ohlcv, index=False)
            artifact = build_trade_episode_dataset(events, ohlcv, horizon_days=5)
            self.assertEqual("2024-01-02", artifact["episodes"][0]["entry_date"])
            self.assertEqual(101.0, artifact["episodes"][0]["entry_price"])

    def test_incomplete_horizon_exclusion_and_deterministic_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir); events = root / "events.json"; ohlcv = root / "ohlcv.csv"
            write_json(_artifact(["2024-01-10"]), events, overwrite=True); _ohlcv(10).to_csv(ohlcv, index=False)
            first = build_trade_episode_dataset(events, ohlcv, horizon_days=20)
            second = build_trade_episode_dataset(events, ohlcv, horizon_days=20)
            self.assertEqual(1, first["exclusions"]["insufficient_future_ohlcv"])
            self.assertEqual(first["episodes"], second["episodes"])

    def test_path_simulator_first_hits_and_same_day_policy(self) -> None:
        frame = prepare_ohlcv(pd.DataFrame({"date": ["2024-01-01", "2024-01-02", "2024-01-03"], "open": [100, 100, 100], "high": [101, 112, 120], "low": [99, 98, 80], "close": [100, 110, 90], "volume": [1, 1, 1]}))
        self.assertEqual("tp", simulate_path(frame, 0, 100, 3, tp_pct=10, sl_pct=15)["first_hit"])
        self.assertEqual("sl", simulate_path(frame, 0, 100, 3, tp_pct=30, sl_pct=15)["first_hit"])
        self.assertEqual("sl", simulate_path(frame, 0, 100, 3, tp_pct=10, sl_pct=2, same_day_policy="stop_first")["first_hit"])
        self.assertEqual("ambiguous", simulate_path(frame, 0, 100, 3, tp_pct=10, sl_pct=2, same_day_policy="ambiguous_exclude")["first_hit"])

    def test_cluster_count_not_effective_sample_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir); events = root / "events.json"; ohlcv = root / "ohlcv.csv"
            dates = pd.bdate_range("2024-01-01", periods=5).strftime("%Y-%m-%d").tolist()
            write_json(_artifact(dates), events, overwrite=True); _ohlcv(30).to_csv(ohlcv, index=False)
            artifact = build_trade_episode_dataset(events, ohlcv, horizon_days=5)
            self.assertIn("not effective sample size", artifact["observation_summary"]["note"])
            self.assertIn("independence_proxy", artifact["episode_summary"])

    def test_tp_artifact_from_episode_schema_valid_and_not_usable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir); events = root / "events.json"; ohlcv = root / "ohlcv.csv"; out = root / "episodes"
            dates = pd.bdate_range("2024-01-01", periods=25).strftime("%Y-%m-%d").tolist()
            write_json(_artifact(dates), events, overwrite=True); _ohlcv(60).to_csv(ohlcv, index=False)
            episode_artifact = build_trade_episode_dataset(events, ohlcv, out, horizon_days=10)
            episode_path = out / "BUMI_trade_episodes_v1.json"
            tp = build_tp_optimizer_artifact(episode_path, "BUMI", TPOptimizerConfig(candidates=[5.0, 10.0], minimum_sample_size=30, minimum_effective_sample_size=30))
            validate_tp_optimizer_artifact(tp, episode_path)
            self.assertIsNone(tp["selected"])
            self.assertFalse(tp["quality"]["usable_for_decision"])

    def test_cli_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir); events = root / "events.json"; ohlcv = root / "ohlcv.csv"
            write_json(_artifact(["2024-01-01"]), events, overwrite=True); _ohlcv(10).to_csv(ohlcv, index=False)
            self.assertEqual(0, episode_main(["--events", str(events), "--ohlcv", str(ohlcv), "--output-dir", str(root), "--horizon-days", "5", "--overwrite"]))
            self.assertTrue((root / "BUMI_trade_episodes_v1.json").exists())

if __name__ == "__main__":
    unittest.main()
