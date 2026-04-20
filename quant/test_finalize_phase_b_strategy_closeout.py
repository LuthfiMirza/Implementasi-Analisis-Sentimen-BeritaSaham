"""Tests for formal Phase B strategy closeout after v9."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from quant.finalize_phase_b_strategy_closeout import finalize_phase_b_strategy_closeout


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class FinalizePhaseBStrategyCloseoutTestCase(unittest.TestCase):
    def _write_full_context(self, output_dir: Path) -> None:
        _write_json(
            output_dir / "project_roadmap_status.json",
            {
                "latest_execution_status": {
                    "phase_b_status": "phase_b_needs_redesign_before_continue",
                    "phase_c_decision": "phase_c_no_go_yet",
                    "recommended_next_action": "redesign_baseline_v2_again",
                }
            },
        )
        _write_json(
            output_dir / "baseline_root_cause_postmortem.json",
            {
                "recommended_primary_direction": "revisit_eligibility_and_sample_guardrails",
                "recommended_secondary_direction_1": "revisit_ticker_universe_segmentation",
                "recommended_secondary_direction_2": "revisit_fast_anchor_with_better_quality_gate",
                "what_to_stop": [
                    "item5",
                    "item6",
                    "item7",
                    "item8",
                    "entry_relaxation_only",
                    "volume_relaxed_entry",
                    "exit_hold_only_redesign",
                ],
                "what_has_been_proven_not_to_work": [
                    "entry_relaxation_only",
                    "exit_hold_only_redesign",
                    "reactivating_phase_b_items_5_to_8",
                ],
                "what_is_still_explorable": [
                    "eligibility_gate_review",
                    "universe_segmentation",
                    "sample_sufficiency_redesign",
                ],
                "key_findings": [
                    "Masalah utama ada pada mismatch guardrail dan bukan pada coding belum selesai."
                ],
                "current_primary_bottleneck": {
                    "data": "not_primary",
                    "eligibility_rule": "primary",
                    "universe_ticker": "secondary",
                },
            },
        )
        _write_json(
            output_dir / "baseline_next_experiment_plan.json",
            {
                "recommended_primary_direction": "revisit_eligibility_and_sample_guardrails",
                "what_to_stop": [
                    "item5",
                    "item6",
                    "item7",
                    "item8",
                    "entry_relaxation_only",
                    "volume_relaxed_entry",
                    "exit_hold_only_redesign",
                ],
                "what_not_to_change": [
                    "Jangan ubah baseline aktif.",
                    "Jangan lanjut ke Phase C.",
                    "Jangan hidupkan lagi item 5-8.",
                ],
                "success_criteria": ["Harus menjelaskan mismatch guardrail dan coverage sample."],
            },
        )
        _write_json(
            output_dir / "baseline_v2_go_no_go.json",
            {
                "decision": "baseline_v2_no_go_redesign_again",
                "candidate_id": "baseline_v2_hold3_with_trend_guard",
                "recommended_next_action": "redesign_baseline_v2_again",
            },
        )
        _write_json(
            output_dir / "baseline_v3_signal_rule_go_no_go.json",
            {
                "best_rule": "baseline_v3_ema20_trend_guard",
                "decision": "no_go",
                "recommended_next_action": "drop_rule_from_redesign_shortlist",
            },
        )
        _write_json(
            output_dir / "baseline_v4_quality_gate_go_no_go.json",
            {
                "best_candidate_id": "baseline_v4_quality_gate_guard",
                "decision": "no_go",
                "recommended_next_action": "redesign_quality_gate_or_shift_to_exit_hold_hypothesis",
            },
        )
        _write_json(
            output_dir / "baseline_v4_quality_gate_v2_go_no_go.json",
            {
                "best_candidate_id": "baseline_v4_quality_gate_v2_anchor_micro_confirm",
                "decision": "no_go",
                "recommended_next_action": "redesign_quality_gate_or_shift_to_exit_hold_hypothesis",
            },
        )
        _write_json(
            output_dir / "baseline_v5_exit_hold_go_no_go.json",
            {
                "best_candidate_id": "baseline_v5_hold4_extension",
                "decision": "no_go",
                "recommended_next_action": "exit_hold_not_enough_keep_anchor_but_reassess_root_cause",
            },
        )
        _write_json(
            output_dir / "baseline_v6_next_experiment_governance.json",
            {
                "recommended_guardrail_mode": "move_to_segment_aware_guardrail",
                "segments_safe_to_test_next": [
                    "volatility_segment=mixed_volatility",
                    "sentiment_segment=sentiment_poor",
                    "liquidity_segment=thin_sparse",
                    "news_segment=mid_news",
                ],
                "what_not_to_do": [
                    "item5",
                    "item6",
                    "item7",
                    "item8",
                    "entry_relaxation_only",
                ],
            },
        )
        _write_json(
            output_dir / "baseline_v7_segment_aware_go_no_go.json",
            {
                "best_candidate_id": "baseline_v3_ema20_trend_guard",
                "tested_segment": "sentiment_segment=sentiment_poor",
                "decision": "keep_experimental_for_segment_review",
                "global_promotion_allowed": False,
                "recommended_next_action": "keep_candidate_for_segment_review_only_on_sentiment_segment_sentiment_poor",
            },
        )
        _write_json(
            output_dir / "baseline_v8_segment_only_validation_go_no_go.json",
            {
                "candidate_id": "baseline_v3_ema20_trend_guard",
                "primary_segment": "sentiment_segment=sentiment_poor",
                "decision": "promote_to_segment_only_validation",
                "global_promotion_allowed": False,
                "recommended_next_action": "promote_candidate_to_segment_only_validation_on_primary_segment_without_global_promotion",
            },
        )
        _write_json(
            output_dir / "baseline_v9_segment_oos_go_no_go.json",
            {
                "candidate_id": "baseline_v3_ema20_trend_guard",
                "primary_segment": "sentiment_segment=sentiment_poor",
                "decision": "no_go_even_for_segment",
                "oos_stability_ok": False,
                "ticker_consistency_ok": False,
                "outlier_bias_ok": True,
                "global_promotion_allowed": False,
                "recommended_next_action": "drop_candidate_from_primary_segment_even_for_experimental_use",
                "primary_total_trades_sum": 11,
                "primary_active_ticker_count": 5,
                "primary_trade_weighted_average_return": -2.4934,
                "primary_mean_average_return_active": -2.6448,
                "supporting_segments_failed": [
                    "volatility_segment=mixed_volatility",
                    "liquidity_segment=thin_sparse",
                    "news_segment=mid_news",
                ],
            },
        )

    def test_closeout_still_runs_when_some_artifacts_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "output"
            output_dir.mkdir()
            _write_json(
                output_dir / "project_roadmap_status.json",
                {"latest_execution_status": {"phase_c_decision": "phase_c_no_go_yet"}},
            )
            _write_json(
                output_dir / "baseline_v9_segment_oos_go_no_go.json",
                {
                    "candidate_id": "baseline_v3_ema20_trend_guard",
                    "primary_segment": "sentiment_segment=sentiment_poor",
                    "decision": "no_go_even_for_segment",
                    "global_promotion_allowed": False,
                    "recommended_next_action": "drop_candidate_from_primary_segment_even_for_experimental_use",
                    "primary_total_trades_sum": 11,
                    "primary_active_ticker_count": 5,
                },
            )

            result = finalize_phase_b_strategy_closeout(output_dir=output_dir)

            self.assertTrue((output_dir / "phase_b_final_closeout.json").exists())
            self.assertTrue((output_dir / "project_after_phase_b_decision.json").exists())
            self.assertIn("artifacts", result)

    def test_final_closeout_and_project_decision_artifacts_are_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "output"
            output_dir.mkdir()
            self._write_full_context(output_dir)

            finalize_phase_b_strategy_closeout(output_dir=output_dir)

            required = [
                output_dir / "phase_b_final_closeout.json",
                output_dir / "phase_b_final_closeout.txt",
                output_dir / "phase_b_strategy_status_matrix.csv",
                output_dir / "project_after_phase_b_decision.json",
                output_dir / "project_after_phase_b_decision.txt",
            ]
            for path in required:
                self.assertTrue(path.exists(), f"Missing artifact: {path}")

    def test_v9_no_go_closes_last_candidate_and_keeps_phase_c_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "output"
            output_dir.mkdir()
            self._write_full_context(output_dir)

            result = finalize_phase_b_strategy_closeout(output_dir=output_dir)

            closeout = result["phase_b_final_closeout"]
            project = result["project_after_phase_b_decision"]

            self.assertEqual("phase_b_closed_with_learnings_no_candidate", closeout["phase_b_final_status"])
            self.assertTrue(closeout["phase_b_failed_as_strategy"])
            self.assertEqual([], closeout["candidate_survivors"])
            self.assertEqual(
                "stop_and_collect_more_data_then_redesign_framework",
                closeout["recommended_primary_next_step"],
            )
            self.assertFalse(closeout["can_continue_to_phase_c"])
            self.assertFalse(project["can_continue_to_phase_c"])
            self.assertFalse(project["can_continue_strategy_experiments_now"])
            self.assertIn("Phase C tetap tidak boleh dibuka.", closeout["decisive_statement"])

    def test_status_matrix_marks_final_candidate_as_not_surviving_after_v9(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "output"
            output_dir.mkdir()
            self._write_full_context(output_dir)

            finalize_phase_b_strategy_closeout(output_dir=output_dir)

            with (output_dir / "phase_b_strategy_status_matrix.csv").open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

            v8_row = next(row for row in rows if row["artifact_id"] == "baseline_v8_segment_only_validation_go_no_go")
            v9_row = next(row for row in rows if row["artifact_id"] == "baseline_v9_segment_oos_go_no_go")

            self.assertEqual("True", v8_row["survivor_signal"])
            self.assertEqual("False", v8_row["final_survivor_after_v9"])
            self.assertEqual("False", v9_row["survivor_signal"])
            self.assertEqual("False", v9_row["final_survivor_after_v9"])


if __name__ == "__main__":
    unittest.main()
