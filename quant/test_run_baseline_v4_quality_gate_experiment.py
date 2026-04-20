"""Tests for baseline v4 quality-gate experiment."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.bootstrap_sample_data import bootstrap_sample_dataset
from quant.run_baseline_v2_candidate_validation import _feature_frame
from quant.run_baseline_v4_quality_gate_experiment import (
    GO_NO_GO_DECISIONS,
    _evaluate_signal_variant,
    run_baseline_v4_quality_gate_experiment,
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


class RunBaselineV4QualityGateExperimentTestCase(unittest.TestCase):
    """Validate v4 quality-gate experiment outputs and guardrails."""

    def test_real_experiment_runs_and_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir = root / "data"
            output_dir = root / "output"
            output_dir.mkdir()

            bootstrap_sample_dataset(data_dir=data_dir, rows=140)
            _write_baseline(output_dir / "phase_a_baseline_final.json")
            _write_metadata(data_dir / "ticker_metadata.csv")
            _write_v4_context(output_dir)

            result = run_baseline_v4_quality_gate_experiment(
                output_dir=output_dir,
                data_dir=data_dir,
                baseline_config=output_dir / "phase_a_baseline_final.json",
                metadata_file=data_dir / "ticker_metadata.csv",
                hold_period=3,
                min_trades=5,
                scaffold_only=False,
            )

            required = [
                output_dir / "baseline_v4_quality_gate_results.csv",
                output_dir / "baseline_v4_quality_gate_summary.json",
                output_dir / "baseline_v4_quality_gate_report.txt",
                output_dir / "baseline_v4_quality_gate_go_no_go.json",
            ]
            for path in required:
                self.assertTrue(path.exists(), f"Missing artifact: {path}")

            results_df = pd.read_csv(output_dir / "baseline_v4_quality_gate_results.csv")
            self.assertIn("baseline_reference", set(results_df["variant_id"]))
            self.assertIn("baseline_v3_ema20_trend_guard", set(results_df["variant_id"]))
            self.assertIn("baseline_v4_quality_gate_guard", set(results_df["variant_id"]))

            summary = json.loads((output_dir / "baseline_v4_quality_gate_summary.json").read_text(encoding="utf-8"))
            self.assertIn("reference_summary", summary)
            self.assertIn("v3_control_summary", summary)
            self.assertIn("best_v4_candidate_summary", summary)

            go_no_go = json.loads((output_dir / "baseline_v4_quality_gate_go_no_go.json").read_text(encoding="utf-8"))
            self.assertIn(go_no_go["decision"], GO_NO_GO_DECISIONS)
            self.assertIn("best_candidate_id", go_no_go)
            self.assertIn("recommended_next_action", go_no_go)

            self.assertFalse(result["results_df"].empty)

    def test_quality_gate_filters_weak_anchor_signals(self) -> None:
        frame = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=40, freq="D"),
                "open": [100.0 + (index * 0.2) for index in range(40)],
                "high": [100.8 + (index * 0.2) for index in range(40)],
                "low": [99.8 + (index * 0.2) for index in range(40)],
                "close": [100.1 + (index * 0.2) + (0.02 if index % 2 == 0 else 0.7) for index in range(40)],
                "volume": [1_000_000 + (index * 1000) for index in range(40)],
            }
        )
        feature_frame = _feature_frame(frame=frame, threshold=1.5)

        v3_metrics = _evaluate_signal_variant(
            feature_frame=feature_frame,
            config={
                "comparison_role": "v3_control",
                "candidate_id": "baseline_v3_ema20_trend_guard",
                "entry_rule": "close_gt_ema20_and_bullish_candle",
                "entry_anchor_rule": "close_gt_ema20_and_bullish_candle",
                "quality_gate_id": "none",
            },
            threshold=1.5,
            hold_period=3,
            min_trades=5,
            profit_buffer_pct=0.0,
        )
        v4_metrics = _evaluate_signal_variant(
            feature_frame=feature_frame,
            config={
                "comparison_role": "v4_candidate",
                "candidate_id": "baseline_v4_quality_gate_guard",
                "entry_rule": "v4_quality_gate_guard",
                "entry_anchor_rule": "close_gt_ema20_and_bullish_candle",
                "quality_gate_id": "body_strength_floor",
                "min_body_to_range_ratio": 0.55,
                "min_close_vs_open_pct": 0.35,
                "min_range_pct": 0.80,
                "min_close_vs_anchor_pct": 0.0,
            },
            threshold=1.5,
            hold_period=3,
            min_trades=5,
            profit_buffer_pct=0.0,
        )

        self.assertLessEqual(v4_metrics["signal_count"], v3_metrics["signal_count"])
        self.assertGreater(v3_metrics["signal_count"], 0)


if __name__ == "__main__":
    unittest.main()
