"""Tests for baseline redesign v4 planning artifacts."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.generate_baseline_v4_redesign_plan import generate_baseline_v4_redesign_plan
from quant.run_baseline_v4_quality_gate_experiment import run_baseline_v4_quality_gate_experiment


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


class GenerateBaselineV4RedesignPlanTestCase(unittest.TestCase):
    """Validate v4 redesign planning outputs and fallback behavior."""

    def test_plan_generator_writes_required_outputs_with_full_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "output"
            output_dir.mkdir()

            _write_json(
                output_dir / "project_current_state.json",
                {
                    "phase_a_runtime_status": "runtime_blocked_mysql",
                    "phase_a_closeout_status": "blocked",
                    "current_project_mode": "phase_a_runtime_fix_required",
                    "final_decision": "cannot_decide_until_runtime_fixed",
                },
            )
            _write_json(
                output_dir / "baseline_v2_go_no_go.json",
                {
                    "decision": "baseline_v2_no_go_redesign_again",
                    "baseline_v2_candidate_selected": "baseline_v2_hold3_with_trend_guard",
                    "phase_a_runtime_status": "runtime_ok",
                    "phase_a_closeout_status": "closed_with_notes",
                },
            )
            _write_json(
                output_dir / "baseline_v2_validation.json",
                {
                    "validation_status": "invalid",
                    "next_action": "redesign_baseline_v2_again",
                    "eligible_ticker_count": 1,
                    "min_eligible_tickers_required": 3,
                    "total_trades_sum": 10,
                    "minimum_trade_sample_required": 15,
                    "score": -12.49,
                },
            )
            _write_json(
                output_dir / "baseline_v2_best_candidate.json",
                {
                    "candidate_id": "baseline_v2_hold3_with_trend_guard",
                    "selected_candidate": {
                        "candidate_id": "baseline_v2_hold3_with_trend_guard",
                    },
                },
            )
            _write_json(
                output_dir / "baseline_v3_signal_rule_go_no_go.json",
                {
                    "best_rule": "baseline_v3_ema20_trend_guard",
                    "decision": "no_go",
                    "coverage_improved": True,
                    "quality_preserved": False,
                    "eligible_ticker_count": 8,
                    "recommended_next_action": "drop_rule_from_redesign_shortlist",
                    "baseline_reference_rule": {
                        "candidate_id": "baseline_v2_hold3_with_trend_guard",
                        "entry_rule": "close_gt_ema50_and_bullish_candle",
                        "eligible_ticker_count": 1,
                        "total_trades_sum": 10,
                        "mean_average_return": 4.24329,
                    },
                },
            )
            _write_json(
                output_dir / "baseline_v3_signal_rule_summary.json",
                {
                    "best_v3_rule": {
                        "candidate_id": "baseline_v3_ema20_trend_guard",
                        "eligible_ticker_count": 8,
                        "total_trades_sum": 56,
                        "mean_average_return": -0.01014,
                        "trade_retention_vs_baseline": 5.6,
                        "coverage_gain_vs_old_rule": 7,
                    }
                },
            )
            _write_json(
                output_dir / "project_roadmap_status.json",
                {
                    "latest_execution_status": {
                        "phase_b_status": "phase_b_needs_redesign_before_continue",
                        "phase_c_decision": "phase_c_no_go_yet",
                    }
                },
            )

            result = generate_baseline_v4_redesign_plan(output_dir=output_dir)

            required = [
                output_dir / "baseline_v4_redesign_plan.json",
                output_dir / "baseline_v4_redesign_plan.txt",
                output_dir / "baseline_v4_hypothesis_matrix.csv",
                output_dir / "baseline_v4_next_experiment.json",
            ]
            for path in required:
                self.assertTrue(path.exists(), f"Missing artifact: {path}")

            plan = json.loads((output_dir / "baseline_v4_redesign_plan.json").read_text(encoding="utf-8"))
            self.assertEqual("candidate_a_fast_anchor_quality_gate", plan["recommended_v4_direction"])
            self.assertIn("entry relaxation only", plan["decision_summary"]["primary_conclusion"].lower())
            self.assertIn("why_v3_failed", plan)
            self.assertEqual("baseline_v2_redesign_required", plan["state_snapshot"]["current_project_mode"])
            self.assertEqual("baseline_v2_no_go_redesign_again", plan["state_snapshot"]["final_decision"])
            self.assertEqual("closed_with_notes", plan["state_snapshot"]["phase_a_closeout_status"])

            matrix_df = pd.read_csv(output_dir / "baseline_v4_hypothesis_matrix.csv")
            self.assertEqual(3, len(matrix_df))
            self.assertTrue(matrix_df["should_test_next"].astype(str).str.lower().eq("true").any())

            next_experiment = json.loads((output_dir / "baseline_v4_next_experiment.json").read_text(encoding="utf-8"))
            self.assertEqual("baseline_v4_quality_gate_guard", next_experiment["experiment_id"])
            self.assertIn("do_not_change", next_experiment)

            self.assertFalse(result["matrix_df"].empty)

    def test_plan_generator_survives_missing_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "output"
            output_dir.mkdir()

            result = generate_baseline_v4_redesign_plan(output_dir=output_dir)

            self.assertTrue((output_dir / "baseline_v4_redesign_plan.json").exists())
            self.assertTrue((output_dir / "baseline_v4_hypothesis_matrix.csv").exists())
            self.assertTrue(result["plan"]["warnings"])

    def test_quality_gate_scaffold_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "output"
            output_dir.mkdir()

            result = run_baseline_v4_quality_gate_experiment(
                output_dir=output_dir,
                hold_period=3,
                min_trades=5,
                scaffold_only=True,
            )

            self.assertTrue((output_dir / "baseline_v4_quality_gate_candidate_matrix.csv").exists())
            self.assertTrue((output_dir / "baseline_v4_quality_gate_experiment_scaffold.json").exists())
            self.assertTrue((output_dir / "baseline_v4_quality_gate_experiment_scaffold.txt").exists())
            self.assertIn("baseline_v4_quality_gate_guard", set(result["matrix_df"]["candidate_id"]))


if __name__ == "__main__":
    unittest.main()
