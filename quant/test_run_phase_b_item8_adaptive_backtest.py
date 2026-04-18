"""Tests for Phase B item 8 adaptive backtests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.bootstrap_sample_data import bootstrap_sample_dataset
from quant.run_phase_b_item8_adaptive_backtest import (
    determine_item8_go_no_go,
    run_phase_b_item8_adaptive_backtest,
    select_best_config_per_ticker,
)


def _write_baseline(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "default_volume_spike_threshold": 2.0,
                "strict_mode_default": False,
                "adaptive_threshold_enabled": False,
                "group_threshold_overrides": [],
                "min_trades_floor": 8,
                "readiness_status": "partially_ready",
                "baseline_status": "provisional",
            }
        ),
        encoding="utf-8",
    )


class RunPhaseBItem8AdaptiveBacktestTestCase(unittest.TestCase):
    """Validate adaptive backtest outputs and selection behavior."""

    def test_adaptive_backtest_runs_and_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir = root / "data"
            output_dir = root / "output"
            baseline_path = root / "phase_a_baseline_final.json"
            metadata_path = root / "ticker_metadata.csv"

            bootstrap_sample_dataset(data_dir=data_dir, rows=140)
            _write_baseline(baseline_path)
            pd.DataFrame(
                {
                    "ticker": ["BBCA", "BMRI", "TLKM"],
                    "sector": ["finance", "finance", "telco"],
                    "category": ["bank", "bank", "telco"],
                    "market_cap_group": ["large", "large", "large"],
                }
            ).to_csv(metadata_path, index=False)

            result = run_phase_b_item8_adaptive_backtest(
                data_dir=data_dir,
                output_dir=output_dir,
                baseline_config=baseline_path,
                metadata_file=metadata_path,
                min_trades=4,
            )

            self.assertFalse(result["results_df"].empty)
            self.assertFalse(result["best_by_ticker_df"].empty)
            self.assertTrue((output_dir / "phase_b_item8_adaptive_results.csv").exists())
            self.assertTrue((output_dir / "phase_b_item8_best_config_per_ticker.csv").exists())
            self.assertTrue((output_dir / "phase_b_item8_group_recommendations.csv").exists())
            self.assertTrue((output_dir / "phase_b_item8_global_summary.json").exists())
            self.assertTrue((output_dir / "phase_b_item8_recommendations.txt").exists())
            self.assertTrue((output_dir / "phase_b_item8_go_no_go.json").exists())

    def test_adaptive_backtest_still_runs_without_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir = root / "data"
            output_dir = root / "output"
            baseline_path = root / "phase_a_baseline_final.json"

            bootstrap_sample_dataset(data_dir=data_dir, rows=140)
            _write_baseline(baseline_path)

            result = run_phase_b_item8_adaptive_backtest(
                data_dir=data_dir,
                output_dir=output_dir,
                baseline_config=baseline_path,
                metadata_file=None,
                min_trades=4,
            )

            self.assertFalse(result["results_df"].empty)
            self.assertFalse((output_dir / "phase_b_item8_go_no_go.json").stat().st_size == 0)
            self.assertFalse((output_dir / "phase_b_item8_group_recommendations.csv").exists())

    def test_low_trade_candidate_is_not_selected_when_eligible_option_exists(self) -> None:
        results_df = pd.DataFrame(
            [
                {
                    "ticker": "AAA",
                    "config_id": "threshold_1.5_strict_false",
                    "volume_spike_threshold": 1.5,
                    "strict_mode": False,
                    "baseline_threshold": 2.0,
                    "baseline_strict_mode": False,
                    "baseline_total_trades": 12,
                    "total_trades": 9,
                    "delta_total_trades": -3,
                    "trade_retention_pct": 75.0,
                    "baseline_win_rate": 50.0,
                    "win_rate": 58.0,
                    "delta_win_rate": 8.0,
                    "baseline_average_return": 1.0,
                    "average_return": 1.4,
                    "delta_average_return": 0.4,
                    "baseline_max_drawdown": 4.0,
                    "max_drawdown": 3.5,
                    "delta_max_drawdown": -0.5,
                    "eligible_by_min_trades": True,
                    "score": 7.0,
                    "outcome": "improve",
                    "category": None,
                    "market_cap_group": None,
                    "sector": None,
                    "beta_group": None,
                },
                {
                    "ticker": "AAA",
                    "config_id": "threshold_2.5_strict_true",
                    "volume_spike_threshold": 2.5,
                    "strict_mode": True,
                    "baseline_threshold": 2.0,
                    "baseline_strict_mode": False,
                    "baseline_total_trades": 12,
                    "total_trades": 2,
                    "delta_total_trades": -10,
                    "trade_retention_pct": 16.7,
                    "baseline_win_rate": 50.0,
                    "win_rate": 100.0,
                    "delta_win_rate": 50.0,
                    "baseline_average_return": 1.0,
                    "average_return": 4.0,
                    "delta_average_return": 3.0,
                    "baseline_max_drawdown": 4.0,
                    "max_drawdown": 1.0,
                    "delta_max_drawdown": -3.0,
                    "eligible_by_min_trades": False,
                    "score": 30.0,
                    "outcome": "neutral",
                    "category": None,
                    "market_cap_group": None,
                    "sector": None,
                    "beta_group": None,
                },
            ]
        )

        selected = select_best_config_per_ticker(results_df=results_df, min_trades=8)
        self.assertEqual("threshold_1.5_strict_false", selected.iloc[0]["config_id"])
        self.assertTrue(bool(selected.iloc[0]["usable_recommendation"]))

    def test_go_no_go_json_can_recommend_ticker_specific_promotion(self) -> None:
        best_by_ticker_df = pd.DataFrame(
            [
                {
                    "ticker": "AAA",
                    "usable_recommendation": True,
                    "decision_confidence": "strong",
                    "trade_floor_override": False,
                    "outcome": "improve",
                    "total_trades": 12,
                    "score": 4.0,
                },
                {
                    "ticker": "BBB",
                    "usable_recommendation": False,
                    "decision_confidence": "moderate",
                    "trade_floor_override": False,
                    "outcome": "neutral",
                    "total_trades": 10,
                    "score": 0.3,
                },
                {
                    "ticker": "CCC",
                    "usable_recommendation": False,
                    "decision_confidence": "low",
                    "trade_floor_override": True,
                    "outcome": "worsen",
                    "total_trades": 1,
                    "score": -10.0,
                },
            ]
        )

        decision = determine_item8_go_no_go(best_by_ticker_df=best_by_ticker_df, group_recommendations_df=None)
        self.assertEqual("promote_ticker_specific", decision["decision"])
        self.assertTrue(decision["promote_ticker_specific"])
        self.assertEqual(["AAA"], decision["recommended_tickers"])


if __name__ == "__main__":
    unittest.main()
