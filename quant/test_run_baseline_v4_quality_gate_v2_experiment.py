"""Tests for baseline v4 quality-gate experiment v2."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.bootstrap_sample_data import bootstrap_sample_dataset
from quant.run_baseline_v4_quality_gate_experiment import GO_NO_GO_DECISIONS
from quant.run_baseline_v4_quality_gate_v2_experiment import (
    run_baseline_v4_quality_gate_v2_experiment,
)


def _write_baseline(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "default_volume_spike_threshold": 1.5,
                "strict_mode_default": False,
                "adaptive_threshold_enabled": False,
                "group_threshold_overrides": [],
                "min_trades_floor": 5,
                "baseline_status": "provisional",
                "readiness_status": "partially_ready",
            }
        ),
        encoding="utf-8",
    )


def _write_metadata(path: Path) -> None:
    pd.DataFrame(
        {
            "ticker": ["BBCA", "BMRI", "TLKM"],
            "sector": ["finance", "finance", "telco"],
            "category": ["bank", "bank", "telco"],
            "market_cap_group": ["large", "large", "large"],
        }
    ).to_csv(path, index=False)


def _write_v4_context(output_dir: Path) -> None:
    (output_dir / "baseline_v4_next_experiment.json").write_text(
        json.dumps(
            {
                "recommended_v4_direction": "candidate_a_fast_anchor_quality_gate",
                "experiment_id": "baseline_v4_quality_gate_guard",
                "expected_success_signal": "eligible_ticker_count >= 3 and mean_average_return improves materially",
                "expected_failure_signal": "coverage < 3 or mean_average_return <= 0",
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "baseline_v4_redesign_plan.json").write_text(
        json.dumps({"recommended_v4_direction": "candidate_a_fast_anchor_quality_gate"}),
        encoding="utf-8",
    )
    (output_dir / "baseline_v3_signal_rule_go_no_go.json").write_text(
        json.dumps(
            {
                "best_rule": "baseline_v3_ema20_trend_guard",
                "decision": "no_go",
                "coverage_improved": True,
                "quality_preserved": False,
                "eligible_ticker_count": 8,
                "baseline_reference_rule": {
                    "candidate_id": "baseline_v2_hold3_with_trend_guard",
                    "entry_rule": "close_gt_ema50_and_bullish_candle",
                    "eligible_ticker_count": 1,
                    "total_trades_sum": 10,
                    "mean_average_return": 4.24329,
                },
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "baseline_v3_signal_rule_summary.json").write_text(
        json.dumps(
            {
                "best_v3_rule": {
                    "candidate_id": "baseline_v3_ema20_trend_guard",
                    "eligible_ticker_count": 8,
                    "total_trades_sum": 56,
                    "mean_average_return": -0.01014,
                    "trade_retention_vs_baseline": 5.6,
                    "coverage_gain_vs_old_rule": 7,
                }
            }
        ),
        encoding="utf-8",
    )


class RunBaselineV4QualityGateV2ExperimentTestCase(unittest.TestCase):
    def test_real_experiment_runs_and_writes_v2_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir = root / "data"
            output_dir = root / "output"
            output_dir.mkdir()

            bootstrap_sample_dataset(data_dir=data_dir, rows=140)
            _write_baseline(output_dir / "phase_a_baseline_final.json")
            _write_metadata(data_dir / "ticker_metadata.csv")
            _write_v4_context(output_dir)

            result = run_baseline_v4_quality_gate_v2_experiment(
                output_dir=output_dir,
                data_dir=data_dir,
                baseline_config=output_dir / "phase_a_baseline_final.json",
                metadata_file=data_dir / "ticker_metadata.csv",
                hold_period=3,
                min_trades=5,
                scaffold_only=False,
            )

            required = [
                output_dir / "baseline_v4_quality_gate_v2_results.csv",
                output_dir / "baseline_v4_quality_gate_v2_summary.json",
                output_dir / "baseline_v4_quality_gate_v2_report.txt",
                output_dir / "baseline_v4_quality_gate_v2_go_no_go.json",
            ]
            for path in required:
                self.assertTrue(path.exists(), f"Missing artifact: {path}")

            results_df = pd.read_csv(output_dir / "baseline_v4_quality_gate_v2_results.csv")
            self.assertIn("baseline_reference", set(results_df["variant_id"]))
            self.assertIn("baseline_v3_ema20_trend_guard", set(results_df["variant_id"]))
            self.assertIn("baseline_v4_quality_gate_v2_body_relaxed", set(results_df["variant_id"]))

            go_no_go = json.loads((output_dir / "baseline_v4_quality_gate_v2_go_no_go.json").read_text(encoding="utf-8"))
            self.assertIn(go_no_go["decision"], GO_NO_GO_DECISIONS)
            self.assertEqual("baseline_v4_quality_gate_guard_v2", go_no_go["experiment_id"])
            self.assertIn("recommended_next_action", go_no_go)

            self.assertFalse(result["results_df"].empty)


if __name__ == "__main__":
    unittest.main()
