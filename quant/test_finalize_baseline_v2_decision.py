"""Tests for final baseline v2 strategic decision artifacts."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from quant.finalize_baseline_v2_decision import DECISION_VALUES, finalize_baseline_v2_decision


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


class FinalizeBaselineV2DecisionTestCase(unittest.TestCase):
    def test_finalize_decision_blocks_when_runtime_not_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "output"
            output_dir.mkdir()

            _write_json(
                output_dir / "phase_a_closeout_status.json",
                {
                    "status": "blocked",
                    "closeout_status": "blocked",
                    "runtime_status": "runtime_blocked_mysql",
                    "blocking_items": ["Gagal membaca backfill historis OJK"],
                    "blocker_reasons": ["mysql_connectivity_failed"],
                    "next_action": "Periksa MySQL.",
                },
            )
            _write_json(
                output_dir / "phase_a_runtime_diagnostics.json",
                {
                    "runtime_status": "runtime_blocked_mysql",
                    "blocker_reason": "mysql_connectivity_failed",
                    "next_action": "Periksa MySQL.",
                },
            )
            _write_json(output_dir / "baseline_redesign_go_no_go.json", {"decision": "improved_but_keep_experimental"})
            _write_json(
                output_dir / "baseline_v2_best_candidate.json",
                {"candidate_id": "baseline_v2_hold3_with_trend_guard"},
            )
            _write_json(output_dir / "baseline_v2_validation.json", {"validation_status": "weak", "next_action": "keep_experimental"})
            _write_json(output_dir / "baseline_v2_validation_go_no_go.json", {"decision": "keep_candidate_experimental"})
            _write_json(output_dir / "project_roadmap_status.json", {"latest_execution_status": {}})
            _write_json(output_dir / "phase_a_to_phase_b_transition.json", {})
            _write_json(output_dir / "phase_b_go_no_go_next_phase.json", {})

            result = finalize_baseline_v2_decision(output_dir=output_dir)

            self.assertEqual("cannot_decide_until_runtime_fixed", result["decision_payload"]["decision"])
            self.assertFalse(result["decision_payload"]["can_continue_after_redesign"])
            self.assertTrue((output_dir / "baseline_v2_go_no_go.json").exists())
            self.assertTrue((output_dir / "project_current_state.json").exists())
            self.assertTrue((output_dir / "project_current_state.txt").exists())

    def test_finalize_decision_approves_when_closeout_and_validation_are_strong(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "output"
            output_dir.mkdir()

            _write_json(
                output_dir / "phase_a_closeout_status.json",
                {
                    "status": "closed_with_notes",
                    "closeout_status": "closed_with_notes",
                    "runtime_status": "runtime_ok",
                    "blocking_items": [],
                    "blocker_reasons": [],
                },
            )
            _write_json(
                output_dir / "phase_a_runtime_diagnostics.json",
                {
                    "runtime_status": "runtime_ok",
                    "blocker_reason": None,
                    "next_action": "none",
                },
            )
            _write_json(output_dir / "baseline_redesign_go_no_go.json", {"decision": "promote_new_baseline_eval_design"})
            _write_json(
                output_dir / "baseline_v2_best_candidate.json",
                {"candidate_id": "baseline_v2_hold3_with_trend_guard"},
            )
            _write_json(
                output_dir / "baseline_v2_validation.json",
                {
                    "validation_status": "promotable",
                    "next_action": "promote_baseline_v2_and_prepare_phase_b_retry",
                },
            )
            _write_json(
                output_dir / "baseline_v2_validation_go_no_go.json",
                {
                    "decision": "promote_candidate_and_prepare_phase_b_retry",
                    "validation_status": "promotable",
                    "candidate_id": "baseline_v2_hold3_with_trend_guard",
                },
            )
            _write_json(
                output_dir / "project_roadmap_status.json",
                {"latest_execution_status": {"phase_b_status": "phase_b_needs_redesign_before_continue"}},
            )
            _write_json(output_dir / "phase_a_to_phase_b_transition.json", {"phase_b_retry_readiness_after_candidate_validation": "ready_for_retry_gate"})
            _write_json(output_dir / "phase_b_go_no_go_next_phase.json", {"phase_b_status": "phase_b_needs_redesign_before_continue"})

            result = finalize_baseline_v2_decision(output_dir=output_dir)

            self.assertIn(result["decision_payload"]["decision"], DECISION_VALUES)
            self.assertEqual("phase_a_closed_with_notes_and_baseline_v2_approved", result["decision_payload"]["decision"])
            self.assertTrue(result["decision_payload"]["can_continue_after_redesign"])


if __name__ == "__main__":
    unittest.main()
