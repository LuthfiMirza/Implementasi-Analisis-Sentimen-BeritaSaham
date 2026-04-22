"""Tests for roadmap audit, Phase A finalization, and Phase B/C planning."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from quant.audit_project_roadmap import (
    RepoInspector,
    audit_project_roadmap,
    build_phase_a_blockers,
    build_phase_a_final_status,
    build_phase_b_execution_plan,
    build_roadmap_items,
)


class AuditProjectRoadmapTestCase(unittest.TestCase):
    """Coverage for roadmap auditing and planning artifacts."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.project_root = Path(__file__).resolve().parent.parent
        cls.inspector = RepoInspector(root=cls.project_root)

    def test_audit_project_roadmap_exports_required_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "audit-output"
            output_dir.mkdir(parents=True, exist_ok=True)

            (output_dir / "phase_a_baseline_final.json").write_text(
                json.dumps(
                    {
                        "baseline_status": "draft",
                        "readiness_status": "partially_ready",
                        "strict_mode_decision_code": "strict_default_not_available",
                    }
                ),
                encoding="utf-8",
            )
            (output_dir / "phase_a_closeout_status.json").write_text(
                json.dumps(
                    {
                        "status": "blocked",
                        "reason": "Close-out diblokir oleh inspeksi runtime.",
                        "blocking_items": [
                            "Gagal membaca backfill historis OJK: SQLSTATE[HY000] [2002] Operation not permitted",
                            "Baseline Phase A masih draft dan belum layak dijadikan baseline operasional.",
                        ],
                        "notes": [],
                        "ojk_backfill": {"error": "SQLSTATE[HY000] [2002] Operation not permitted"},
                        "macro_regulatory_signal": {"error": "SQLSTATE[HY000] [2002] Operation not permitted"},
                    }
                ),
                encoding="utf-8",
            )
            (output_dir / "phase_b_postmortem.json").write_text(
                json.dumps({"phase_b_status": "phase_b_closed_with_learnings_no_candidate"}),
                encoding="utf-8",
            )
            (output_dir / "phase_b_go_no_go_next_phase.json").write_text(
                json.dumps(
                    {
                        "phase_c_decision": "phase_c_no_go_yet",
                        "root_problem_class": "foundation_and_signal_usability",
                        "recommended_next_action": "stop_and_collect_more_data_then_redesign_framework",
                    }
                ),
                encoding="utf-8",
            )
            (output_dir / "phase_b_final_closeout.json").write_text(
                json.dumps(
                    {
                        "phase_b_final_status": "phase_b_closed_with_learnings_no_candidate",
                        "recommended_primary_next_step": "stop_and_collect_more_data_then_redesign_framework",
                        "can_continue_strategy_experiments_now": False,
                    }
                ),
                encoding="utf-8",
            )
            (output_dir / "project_after_phase_b_decision.json").write_text(
                json.dumps(
                    {
                        "phase_b_final_status": "phase_b_closed_with_learnings_no_candidate",
                        "phase_c_decision": "phase_c_no_go_yet",
                        "recommended_primary_next_step": "stop_and_collect_more_data_then_redesign_framework",
                        "can_continue_strategy_experiments_now": False,
                    }
                ),
                encoding="utf-8",
            )
            (output_dir / "phase_b_retest_readiness_gate.json").write_text(
                json.dumps({"final_decision": "belum_boleh_retest"}),
                encoding="utf-8",
            )
            (output_dir / "baseline_redesign_go_no_go.json").write_text(
                json.dumps({"decision": "improved_but_keep_experimental", "next_action": "revise_baseline_further"}),
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
                        "recommended_next_action": "drop_rule_from_redesign_shortlist",
                    }
                ),
                encoding="utf-8",
            )
            (output_dir / "baseline_v2_go_no_go.json").write_text(
                json.dumps({"decision": "baseline_v2_candidate_ready", "next_action": "validate_baseline_v2_candidate"}),
                encoding="utf-8",
            )
            (output_dir / "baseline_v2_validation_go_no_go.json").write_text(
                json.dumps(
                    {
                        "decision": "keep_candidate_experimental",
                        "recommended_next_action": "keep_candidate_experimental_and_continue_validation",
                    }
                ),
                encoding="utf-8",
            )
            (output_dir / "baseline_v2_subset_go_no_go.json").write_text(
                json.dumps(
                    {
                        "decision": "keep_candidate_experimental",
                        "next_action": "keep_candidate_experimental_for_watchlist_subset",
                    }
                ),
                encoding="utf-8",
            )
            (output_dir / "phase_a_to_phase_b_transition.json").write_text(
                json.dumps(
                    {
                        "baseline_v2_subset_next_action": "keep_candidate_experimental_for_watchlist_subset",
                    }
                ),
                encoding="utf-8",
            )

            result = audit_project_roadmap(
                project_root=self.project_root,
                output_dir=output_dir,
            )

            required_files = [
                "project_roadmap_status.json",
                "project_roadmap_status.txt",
                "project_phase_gap_analysis.csv",
                "phase_a_final_status.json",
                "phase_a_final_summary.txt",
                "phase_a_minimum_blockers.csv",
                "phase_a_minimum_next_steps.txt",
                "phase_b_execution_plan.json",
                "phase_b_execution_plan.txt",
                "phase_c_backlog.json",
                "phase_c_backlog.txt",
            ]
            for file_name in required_files:
                self.assertTrue((output_dir / file_name).exists(), file_name)

            payload = json.loads((output_dir / "project_roadmap_status.json").read_text())
            item_lookup = {item["item_number"]: item["status"] for item in payload["items"]}

            self.assertEqual(12, len(payload["items"]))
            self.assertEqual("done", item_lookup[1])
            self.assertEqual("done", item_lookup[4])
            self.assertEqual("partial", item_lookup[5])
            self.assertEqual("partial", item_lookup[8])
            self.assertEqual("not_started", item_lookup[9])
            self.assertEqual("blocked", result["final_status"]["status"])
            self.assertEqual(
                "phase_b_closed_with_learnings_no_candidate",
                payload["latest_execution_status"]["phase_b_status"],
            )
            self.assertEqual(
                "keep_candidate_experimental",
                payload["latest_execution_status"]["baseline_v2_subset_status"],
            )
            self.assertEqual(
                "no_go",
                payload["latest_execution_status"]["baseline_v3_signal_rule_status"],
            )
            self.assertEqual(
                "baseline_v3_ema20_trend_guard",
                payload["latest_execution_status"]["baseline_v3_signal_rule_best_rule"],
            )
            self.assertEqual(
                "stop_and_collect_more_data_then_redesign_framework",
                payload["latest_execution_status"]["current_track"],
            )

            roadmap_txt = (output_dir / "project_roadmap_status.txt").read_text(encoding="utf-8")
            self.assertIn("Status terkini strategi:", roadmap_txt)
            self.assertIn(
                "Baseline v3 signal rule status: no_go",
                roadmap_txt,
            )
            self.assertIn(
                "Baseline v3 signal rule best rule: baseline_v3_ema20_trend_guard",
                roadmap_txt,
            )
            self.assertIn(
                "Current track: stop_and_collect_more_data_then_redesign_framework",
                roadmap_txt,
            )
            self.assertIn(
                "Retest readiness status: belum_boleh_retest",
                roadmap_txt,
            )

    def test_phase_a_final_status_treats_neutral_only_macro_as_note_when_moderation_is_ready(self) -> None:
        roadmap_items = [
            {
                "phase": "phase_a",
                "item_number": 1,
                "item_name": "Volume spike detection",
                "status": "done",
                "evidence": [],
                "key_files": [],
                "remaining_gap": "",
                "recommended_next_action": "",
            },
            {
                "phase": "phase_a",
                "item_number": 2,
                "item_name": "EMA50 trend filter",
                "status": "done",
                "evidence": [],
                "key_files": [],
                "remaining_gap": "",
                "recommended_next_action": "",
            },
            {
                "phase": "phase_a",
                "item_number": 3,
                "item_name": "OJK backfill",
                "status": "done",
                "evidence": [],
                "key_files": [],
                "remaining_gap": "",
                "recommended_next_action": "",
            },
            {
                "phase": "phase_a",
                "item_number": 4,
                "item_name": "Macro integration",
                "status": "done",
                "evidence": [],
                "key_files": [],
                "remaining_gap": "",
                "recommended_next_action": "",
            },
        ]
        baseline_payload = {
            "baseline_status": "final",
            "readiness_status": "ready",
            "strict_mode_decision_code": "strict_default_no",
        }
        closeout_payload = {
            "status": "closed_with_notes",
            "reason": "Phase A siap dengan catatan.",
            "blocking_items": [],
            "notes": [],
            "ojk_backfill": {
                "ready": True,
                "neutral_only": True,
            },
            "macro_regulatory_signal": {
                "ready": True,
                "neutral_only_handled": True,
            },
        }

        status = build_phase_a_final_status(
            roadmap_items=roadmap_items,
            baseline_payload=baseline_payload,
            closeout_payload=closeout_payload,
            inspector=self.inspector,
        )

        self.assertEqual("closed_with_notes", status["status"])
        self.assertEqual("note", status["macro_ojk_neutral_only_current_classification"])
        self.assertFalse(status["ui_manual_verification_blocker"])
        self.assertTrue(status["ready_to_start_phase_b"])

    def test_phase_a_final_status_filters_stale_baseline_blockers_from_old_closeout(self) -> None:
        roadmap_items = [
            {
                "phase": "phase_a",
                "item_number": 1,
                "item_name": "Volume spike detection",
                "status": "done",
                "evidence": [],
                "key_files": [],
                "remaining_gap": "",
                "recommended_next_action": "",
            },
            {
                "phase": "phase_a",
                "item_number": 2,
                "item_name": "EMA50 trend filter",
                "status": "done",
                "evidence": [],
                "key_files": [],
                "remaining_gap": "",
                "recommended_next_action": "",
            },
            {
                "phase": "phase_a",
                "item_number": 3,
                "item_name": "OJK backfill",
                "status": "done",
                "evidence": [],
                "key_files": [],
                "remaining_gap": "",
                "recommended_next_action": "",
            },
            {
                "phase": "phase_a",
                "item_number": 4,
                "item_name": "Macro integration",
                "status": "done",
                "evidence": [],
                "key_files": [],
                "remaining_gap": "",
                "recommended_next_action": "",
            },
        ]
        baseline_payload = {
            "baseline_status": "provisional",
            "readiness_status": "partially_ready",
            "strict_mode_decision_code": "strict_default_no",
        }
        closeout_payload = {
            "status": "blocked",
            "reason": "Close-out diblokir oleh inspeksi runtime.",
            "blocking_items": [
                "Gagal membaca backfill historis OJK: SQLSTATE[HY000] [2002] Operation not permitted",
                "Baseline Phase A masih draft dan belum layak dijadikan baseline operasional.",
                "Strict mode belum final karena masih subset-only atau belum terdefinisi.",
            ],
            "notes": [],
            "ojk_backfill": {"error": "SQLSTATE[HY000] [2002] Operation not permitted"},
            "macro_regulatory_signal": {"error": "SQLSTATE[HY000] [2002] Operation not permitted"},
        }

        status = build_phase_a_final_status(
            roadmap_items=roadmap_items,
            baseline_payload=baseline_payload,
            closeout_payload=closeout_payload,
            inspector=self.inspector,
        )

        self.assertEqual("blocked", status["status"])
        self.assertEqual(
            ["Gagal membaca backfill historis OJK: SQLSTATE[HY000] [2002] Operation not permitted"],
            status["blocking_items"],
        )

    def test_phase_a_blockers_and_phase_b_plan_are_prioritized(self) -> None:
        roadmap_items = build_roadmap_items(
            inspector=self.inspector,
            output_dir=self.project_root / "output",
            baseline_payload=None,
            closeout_payload=None,
        )
        final_status = {
            "status": "blocked",
            "baseline_status": "draft",
            "readiness_status": "partially_ready",
            "baseline_usable_now": False,
            "baseline_final_now": False,
            "strict_mode_final_now": False,
            "core_phase_a_items_done": True,
            "macro_ojk_neutral_only_current_classification": "unknown_runtime",
            "ready_to_start_phase_b": False,
            "ready_to_start_phase_b_reason": "Phase A belum cukup stabil.",
            "closeout_artifact_available": False,
            "blocking_items": [
                "Baseline final masih draft.",
            ],
            "notes": [],
        }
        closeout_payload = {
            "blocking_items": [
                "Gagal membaca backfill historis OJK: SQLSTATE[HY000] [2002] Operation not permitted",
            ]
        }

        blockers_df, next_steps = build_phase_a_blockers(
            final_status=final_status,
            baseline_payload=None,
            closeout_payload=closeout_payload,
        )
        plan = build_phase_b_execution_plan(
            roadmap_items=roadmap_items,
            final_status=final_status,
        )

        self.assertFalse(blockers_df.empty)
        self.assertIn("phase_a_real_baseline_not_frozen", blockers_df["blocker_code"].tolist())
        self.assertIn(
            "phase_a_runtime_closeout_not_validated",
            blockers_df["blocker_code"].tolist(),
        )
        self.assertGreaterEqual(len(next_steps), 2)
        self.assertEqual("phase_b_closed_waiting_data_extension_and_framework_redesign", plan["gate_status"])
        self.assertEqual("baseline_trade_design_redesign_audit", plan["execution_order"][0]["step_code"])
        self.assertEqual(0, plan["execution_order"][0]["item_number"])
        self.assertEqual("phase_b_items_5_to_8_parking_rule", plan["execution_order"][-1]["step_code"])


if __name__ == "__main__":
    unittest.main()
