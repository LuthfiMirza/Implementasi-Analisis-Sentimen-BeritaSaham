"""Tests for the measured Phase B item 5 threshold sweep."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.bootstrap_sample_data import bootstrap_sample_dataset
from quant.run_phase_b_item5_threshold_sweep import (
    determine_item5_go_no_go,
    run_phase_b_item5_threshold_sweep,
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


class RunPhaseBItem5ThresholdSweepTestCase(unittest.TestCase):
    """Validate the item-5 sweep outputs and go/no-go decision rules."""

    def test_threshold_sweep_runs_and_writes_outputs(self) -> None:
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
                }
            ).to_csv(metadata_path, index=False)

            result = run_phase_b_item5_threshold_sweep(
                data_dir=data_dir,
                output_dir=output_dir,
                baseline_config=baseline_path,
                metadata_file=metadata_path,
            )

            self.assertFalse(result["results_df"].empty)
            self.assertFalse(result["best_by_ticker_df"].empty)
            self.assertFalse(result["global_summary_df"].empty)
            self.assertTrue((output_dir / "phase_b_item5_threshold_sweep_results.csv").exists())
            self.assertTrue((output_dir / "phase_b_item5_best_by_ticker.csv").exists())
            self.assertTrue((output_dir / "phase_b_item5_global_summary.csv").exists())
            self.assertTrue((output_dir / "phase_b_item5_go_no_go.json").exists())
            self.assertTrue((output_dir / "phase_b_item5_decision.json").exists())
            self.assertTrue((output_dir / "phase_b_item5_recommendations.txt").exists())

    def test_threshold_sweep_still_runs_without_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir = root / "data"
            output_dir = root / "output"
            baseline_path = root / "phase_a_baseline_final.json"

            bootstrap_sample_dataset(data_dir=data_dir, rows=140)
            _write_baseline(baseline_path)

            result = run_phase_b_item5_threshold_sweep(
                data_dir=data_dir,
                output_dir=output_dir,
                baseline_config=baseline_path,
                metadata_file=None,
            )

            self.assertFalse(result["results_df"].empty)
            self.assertTrue((output_dir / "phase_b_item5_go_no_go.json").exists())

    def test_go_no_go_can_return_no_go_when_results_are_broadly_worse(self) -> None:
        best_by_ticker_df = pd.DataFrame(
            [
                {"ticker": "AAA", "outcome": "worsen", "decision_confidence": "strong"},
                {"ticker": "BBB", "outcome": "worsen", "decision_confidence": "moderate"},
                {"ticker": "CCC", "outcome": "neutral", "decision_confidence": "low"},
            ]
        )
        global_summary_df = pd.DataFrame(
            [
                {
                    "threshold": 1.0,
                    "mean_score": -1.25,
                    "delta_average_return_mean": -0.12,
                    "delta_win_rate_mean": -2.5,
                    "trade_retention_mean_pct": 100.0,
                    "selected_as_global_best": True,
                }
            ]
        )

        decision = determine_item5_go_no_go(
            best_by_ticker_df=best_by_ticker_df,
            global_summary_df=global_summary_df,
            best_by_group_df=None,
        )

        self.assertEqual("no_go", decision["decision"])
        self.assertEqual("stop", decision["next_action"])
        self.assertEqual("failed", decision["item5_experiment_status"])

    def test_go_no_go_can_return_promote_for_subset_when_only_subset_is_strong(self) -> None:
        best_by_ticker_df = pd.DataFrame(
            [
                {"ticker": "AAA", "outcome": "improve", "decision_confidence": "strong"},
                {"ticker": "BBB", "outcome": "improve", "decision_confidence": "moderate"},
                {"ticker": "CCC", "outcome": "worsen", "decision_confidence": "strong"},
                {"ticker": "DDD", "outcome": "neutral", "decision_confidence": "low"},
            ]
        )
        global_summary_df = pd.DataFrame(
            [
                {
                    "threshold": 1.0,
                    "mean_score": 0.1,
                    "delta_average_return_mean": -0.01,
                    "delta_win_rate_mean": 0.2,
                    "trade_retention_mean_pct": 92.0,
                    "selected_as_global_best": True,
                }
            ]
        )
        best_by_group_df = pd.DataFrame(
            [
                {
                    "group_field": "sector",
                    "group_value": "finance",
                    "recommended_for_subset": True,
                }
            ]
        )

        decision = determine_item5_go_no_go(
            best_by_ticker_df=best_by_ticker_df,
            global_summary_df=global_summary_df,
            best_by_group_df=best_by_group_df,
        )

        self.assertEqual("promote_for_subset", decision["decision"])
        self.assertEqual("promote_subset", decision["next_action"])
        self.assertEqual("promising", decision["item5_experiment_status"])
        self.assertIn("sector=finance", decision["recommended_groups"])


if __name__ == "__main__":
    unittest.main()
