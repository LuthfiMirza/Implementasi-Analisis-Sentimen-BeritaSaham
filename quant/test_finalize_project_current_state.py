"""Tests for final project current-state freeze artifacts."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from quant.finalize_project_current_state import finalize_project_current_state


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


class FinalizeProjectCurrentStateTestCase(unittest.TestCase):
    """Validate project current-state artifacts and transition update."""

    def test_finalize_project_current_state_writes_expected_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "output"
            output_dir.mkdir()

            _write_json(
                output_dir / "project_roadmap_status.json",
                {
                    "latest_execution_status": {
                        "phase_b_status": "phase_b_needs_redesign_before_continue",
                        "phase_c_decision": "phase_c_no_go_yet",
                    },
                    "phase_a_final_status": {"status": "blocked"},
                },
            )
            _write_json(
                output_dir / "phase_b_go_no_go_next_phase.json",
                {
                    "phase_b_status": "phase_b_needs_redesign_before_continue",
                    "phase_c_decision": "phase_c_no_go_yet",
                },
            )
            _write_json(
                output_dir / "phase_b_final_closeout.json",
                {
                    "phase_b_final_status": "phase_b_closed_with_learnings_no_candidate",
                    "recommended_primary_next_step": "stop_and_collect_more_data_then_redesign_framework",
                    "can_continue_strategy_experiments_now": False,
                },
            )
            _write_json(
                output_dir / "project_after_phase_b_decision.json",
                {
                    "phase_b_final_status": "phase_b_closed_with_learnings_no_candidate",
                    "phase_c_decision": "phase_c_no_go_yet",
                    "recommended_primary_next_step": "stop_and_collect_more_data_then_redesign_framework",
                    "can_continue_strategy_experiments_now": False,
                },
            )
            _write_json(
                output_dir / "phase_b_retest_readiness_gate.json",
                {"final_decision": "belum_boleh_retest"},
            )
            _write_json(output_dir / "phase_a_baseline_final.json", {"baseline_status": "provisional"})
            _write_json(
                output_dir / "baseline_v2_go_no_go.json",
                {"baseline_v2_candidate_selected": "baseline_v2_hold3_with_trend_guard"},
            )
            _write_json(
                output_dir / "baseline_v2_validation_go_no_go.json",
                {"candidate_id": "baseline_v2_hold3_with_trend_guard", "decision": "keep_candidate_experimental"},
            )
            _write_json(
                output_dir / "baseline_v2_subset_go_no_go.json",
                {
                    "candidate_id": "baseline_v2_hold3_with_trend_guard",
                    "recommended_tickers": ["BMRI", "GOTO", "BBCA", "BBRI"],
                    "recommended_groups": ["sector:perbankan"],
                },
            )
            _write_json(
                output_dir / "baseline_v2_watchlist_go_no_go.json",
                {
                    "candidate_id": "baseline_v2_hold3_with_trend_guard",
                    "recommended_tickers": ["GOTO", "BMRI"],
                    "recommended_groups": ["sector:perbankan"],
                },
            )
            _write_json(
                output_dir / "baseline_v2_watchlist_monitoring_decision.json",
                {
                    "decision": "keep_candidate_experimental",
                    "candidate_id": "baseline_v2_hold3_with_trend_guard",
                    "still_experimental": True,
                    "stable_subset_found": False,
                    "can_promote_for_subset": False,
                    "can_reject_candidate": False,
                    "next_action": "keep_candidate_experimental_for_watchlist_subset",
                    "recommended_tickers": ["GOTO", "BMRI", "BBCA", "BBRI"],
                    "recommended_groups": ["sector:perbankan"],
                },
            )
            _write_json(
                output_dir / "phase_a_to_phase_b_transition.json",
                {"phase_b_entry_mode": "limited_experiment"},
            )
            (output_dir / "phase_a_to_phase_b_transition_report.txt").write_text(
                "Phase A To Phase B Transition\n=============================\n",
                encoding="utf-8",
            )

            result = finalize_project_current_state(output_dir=output_dir)

            required = [
                output_dir / "project_current_state_summary.json",
                output_dir / "project_current_state_summary.txt",
                output_dir / "project_current_state.json",
                output_dir / "project_current_state.txt",
                output_dir / "project_freeze_status.json",
            ]
            for path in required:
                self.assertTrue(path.exists(), f"Missing artifact: {path}")

            payload = json.loads((output_dir / "project_current_state_summary.json").read_text(encoding="utf-8"))
            self.assertEqual("frozen_waiting_data_extension_and_framework_redesign", payload["project_state"])
            self.assertTrue(payload["active_operational_baseline"]["use_for_operations"])
            self.assertFalse(payload["phase_b"]["retry_ready"])
            self.assertFalse(payload["phase_c"]["can_start"])

            transition = json.loads((output_dir / "phase_a_to_phase_b_transition.json").read_text(encoding="utf-8"))
            self.assertIn("project_current_state_status", transition)
            self.assertIn("project_current_state_next_action", transition)
            self.assertIn("project_operational_baseline", transition)
            self.assertIn("project_phase_c_status", transition)

            self.assertIn("payload", result)


if __name__ == "__main__":
    unittest.main()
