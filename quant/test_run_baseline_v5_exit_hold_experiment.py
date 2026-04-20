"""Tests for baseline v5 exit/hold redesign."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.bootstrap_sample_data import bootstrap_sample_dataset
from quant.run_baseline_v2_candidate_validation import _feature_frame
from quant.run_baseline_v5_exit_hold_experiment import (
    GO_NO_GO_DECISIONS,
    _backtest_exit_variant,
    _prepare_v4_anchor_signal,
    run_baseline_v5_exit_hold_experiment,
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


def _write_context(output_dir: Path) -> None:
    (output_dir / "baseline_v4_redesign_plan.json").write_text(
        json.dumps(
            {
                "decision_summary": {
                    "primary_conclusion": "Jangan lanjutkan redesign dengan entry relaxation only.",
                    "secondary_conclusion": "Uji quality gate setelah fast trend anchor sebelum menambah pelonggaran entry baru.",
                    "third_conclusion": "Uji exit/hold redesign sebagai prioritas kedua bila quality gate tidak cukup.",
                }
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "baseline_v4_quality_gate_summary.json").write_text(
        json.dumps(
            {
                "best_v4_candidate_summary": {
                    "candidate_id": "baseline_v4_quality_gate_guard",
                    "eligible_ticker_count": 2,
                    "total_trades_sum": 34,
                    "mean_average_return": 7.41434,
                }
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "baseline_v4_quality_gate_go_no_go.json").write_text(
        json.dumps(
            {
                "decision": "no_go",
                "eligible_ticker_count": 2,
                "total_trades_sum": 34,
                "mean_average_return": 7.41434,
                "quality_preserved": True,
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "baseline_v4_quality_gate_v2_summary.json").write_text(
        json.dumps(
            {
                "best_v4_candidate_summary": {
                    "candidate_id": "baseline_v4_quality_gate_v2_anchor_micro_confirm",
                    "eligible_ticker_count": 0,
                    "total_trades_sum": 15,
                    "mean_average_return": -0.75068,
                }
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "baseline_v4_quality_gate_v2_go_no_go.json").write_text(
        json.dumps(
            {
                "decision": "no_go",
                "eligible_ticker_count": 0,
                "total_trades_sum": 15,
                "mean_average_return": -0.75068,
                "quality_preserved": False,
                "trade_support_ok": False,
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "project_roadmap_status.json").write_text(
        json.dumps(
            {
                "latest_execution_status": {
                    "phase_a_status": "closed_with_notes",
                    "phase_b_status": "phase_b_needs_redesign_before_continue",
                    "phase_c_decision": "phase_c_no_go_yet",
                }
            }
        ),
        encoding="utf-8",
    )


class RunBaselineV5ExitHoldExperimentTestCase(unittest.TestCase):
    def test_real_experiment_runs_and_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir = root / "data"
            output_dir = root / "output"
            output_dir.mkdir()

            bootstrap_sample_dataset(data_dir=data_dir, rows=180)
            _write_baseline(output_dir / "phase_a_baseline_final.json")
            _write_metadata(data_dir / "ticker_metadata.csv")
            _write_context(output_dir)

            result = run_baseline_v5_exit_hold_experiment(
                output_dir=output_dir,
                data_dir=data_dir,
                baseline_config=output_dir / "phase_a_baseline_final.json",
                metadata_file=data_dir / "ticker_metadata.csv",
                min_trades=5,
            )

            required = [
                output_dir / "baseline_v5_redesign_plan.json",
                output_dir / "baseline_v5_exit_hold_results.csv",
                output_dir / "baseline_v5_exit_hold_summary.json",
                output_dir / "baseline_v5_exit_hold_report.txt",
                output_dir / "baseline_v5_exit_hold_go_no_go.json",
            ]
            for path in required:
                self.assertTrue(path.exists(), f"Missing artifact: {path}")

            results_df = pd.read_csv(output_dir / "baseline_v5_exit_hold_results.csv")
            self.assertIn("baseline_reference", set(results_df["variant_id"]))
            self.assertIn("baseline_v3_ema20_trend_guard", set(results_df["variant_id"]))
            self.assertIn("baseline_v4_quality_gate_guard", set(results_df["variant_id"]))
            self.assertIn("baseline_v5_hold5_stop3_take6", set(results_df["variant_id"]))

            go_no_go = json.loads((output_dir / "baseline_v5_exit_hold_go_no_go.json").read_text(encoding="utf-8"))
            self.assertIn(go_no_go["decision"], GO_NO_GO_DECISIONS)
            self.assertIn("supports_exit_hold_hypothesis", go_no_go)
            self.assertFalse(result["results_df"].empty)

    def test_take_profit_can_exit_early_before_max_hold(self) -> None:
        frame = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=30, freq="D"),
                "open": [100.0] * 30,
                "high": [100.5] * 30,
                "low": [99.5] * 30,
                "close": [100.4] * 30,
                "volume": [1_000_000] * 30,
            }
        )
        frame.loc[20:, "open"] = [100.0, 101.0, 102.0, 103.0, 104.0, 104.5, 105.0, 105.0, 105.0, 105.0]
        frame.loc[20:, "high"] = [101.0, 102.0, 103.0, 107.0, 107.0, 107.0, 107.0, 107.0, 107.0, 107.0]
        frame.loc[20:, "low"] = [99.5, 100.5, 101.5, 102.5, 103.5, 104.0, 104.5, 104.5, 104.5, 104.5]
        frame.loc[20:, "close"] = [100.8, 101.8, 102.8, 106.2, 106.0, 105.8, 105.6, 105.4, 105.2, 105.0]

        feature_frame = _feature_frame(frame=frame, threshold=1.5)
        signal_frame = _prepare_v4_anchor_signal(feature_frame=feature_frame, signal_column="signal_test")
        signal_frame["signal_test"] = False
        signal_frame.loc[22, "signal_test"] = True

        backtest = _backtest_exit_variant(
            frame=signal_frame,
            signal_column="signal_test",
            max_hold_period=5,
            stop_loss_pct=0.0,
            take_profit_pct=3.0,
            ema20_fail_exit=False,
            allow_overlap=False,
        )

        self.assertEqual(1, backtest["total_trades"])
        trade = backtest["trades"].iloc[0]
        self.assertEqual("take_profit", trade["exit_reason"])
        self.assertLess(pd.Timestamp(trade["exit_date"]), pd.Timestamp(signal_frame.loc[27, "date"]))


if __name__ == "__main__":
    unittest.main()
