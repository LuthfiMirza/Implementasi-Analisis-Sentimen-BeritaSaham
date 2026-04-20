"""Tests for the baseline v9 segment OOS validation runner."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from quant.run_baseline_v6_guardrail_review import run_baseline_v6_guardrail_review
from quant.run_baseline_v7_segment_aware_experiment import run_baseline_v7_segment_aware_experiment
from quant.run_baseline_v8_segment_only_validation import run_baseline_v8_segment_only_validation
from quant.run_baseline_v9_segment_oos_validation import (
    GO_NO_GO_OUTPUT,
    REPORT_OUTPUT,
    RESULT_OUTPUT,
    SUMMARY_OUTPUT,
    _determine_go_no_go,
    run_baseline_v9_segment_oos_validation,
)
from quant.test_run_baseline_v6_guardrail_review import RunBaselineV6GuardrailReviewTestCase


class RunBaselineV9SegmentOosValidationTestCase(unittest.TestCase):
    def _prepare_with_v8(self, root: Path) -> tuple[Path, Path, Path]:
        helper = RunBaselineV6GuardrailReviewTestCase()
        data_dir, output_dir, metadata_file = helper._prepare_fixture(root)
        run_baseline_v6_guardrail_review(
            data_dir=data_dir,
            output_dir=output_dir,
            metadata_file=metadata_file,
        )
        run_baseline_v7_segment_aware_experiment(output_dir=output_dir)
        run_baseline_v8_segment_only_validation(output_dir=output_dir)
        (output_dir / "phase_a_final_status.json").write_text(
            json.dumps({"status": "closed_with_notes"}),
            encoding="utf-8",
        )
        (output_dir / "phase_b_final_status.json").write_text(
            json.dumps({"phase_b_status": "phase_b_needs_redesign_before_continue"}),
            encoding="utf-8",
        )
        return data_dir, output_dir, metadata_file

    def test_v9_runner_generates_outputs_and_keeps_global_promotion_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir, output_dir, metadata_file = self._prepare_with_v8(root)

            result = run_baseline_v9_segment_oos_validation(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
                baseline_config=None,
            )

            required = [
                output_dir / RESULT_OUTPUT,
                output_dir / SUMMARY_OUTPUT,
                output_dir / REPORT_OUTPUT,
                output_dir / GO_NO_GO_OUTPUT,
            ]
            for path in required:
                self.assertTrue(path.exists(), f"Missing artifact: {path}")

            go_no_go = json.loads((output_dir / GO_NO_GO_OUTPUT).read_text(encoding="utf-8"))
            self.assertEqual("baseline_v3_ema20_trend_guard", go_no_go["candidate_id"])
            self.assertEqual("sentiment_segment=sentiment_poor", go_no_go["primary_segment"])
            self.assertIn(
                go_no_go["decision"],
                {
                    "stay_promote_to_segment_only_validation",
                    "keep_experimental_for_segment_only_use",
                    "no_go_even_for_segment",
                },
            )
            self.assertFalse(go_no_go["global_promotion_allowed"])

            summary = json.loads((output_dir / SUMMARY_OUTPUT).read_text(encoding="utf-8"))
            self.assertEqual("anchored_walk_forward_oos", summary["methodology"]["validation_mode"])
            self.assertIn("decision", summary)
            self.assertIn("artifacts", result)

    def test_decision_stays_promoted_when_primary_and_supporting_oos_are_clean(self) -> None:
        primary = {
            "tested_segment": "sentiment_segment=sentiment_poor",
            "primary_viable": True,
            "oos_stability_ok": True,
            "ticker_consistency_ok": True,
            "outlier_bias_ok": True,
            "candidate_total_trades": 18,
            "active_ticker_count": 4,
            "trade_weighted_average_return": 1.8,
            "mean_average_return_active": 1.2,
        }
        supporting = [
            {"tested_segment": "volatility_segment=mixed_volatility", "robustness_check_passed": True},
            {"tested_segment": "liquidity_segment=thin_sparse", "robustness_check_passed": True},
            {"tested_segment": "news_segment=mid_news", "robustness_check_passed": True},
        ]

        result = _determine_go_no_go(
            candidate_id="baseline_v3_ema20_trend_guard",
            primary_summary=primary,
            supporting_summaries=supporting,
        )

        self.assertEqual("stay_promote_to_segment_only_validation", result["decision"])
        self.assertTrue(result["oos_stability_ok"])
        self.assertTrue(result["ticker_consistency_ok"])
        self.assertTrue(result["outlier_bias_ok"])
        self.assertFalse(result["global_promotion_allowed"])

    def test_decision_keeps_experimental_when_primary_viable_but_supporting_is_mixed(self) -> None:
        primary = {
            "tested_segment": "sentiment_segment=sentiment_poor",
            "primary_viable": True,
            "oos_stability_ok": True,
            "ticker_consistency_ok": False,
            "outlier_bias_ok": True,
            "candidate_total_trades": 11,
            "active_ticker_count": 3,
            "trade_weighted_average_return": 0.7,
            "mean_average_return_active": 0.5,
        }
        supporting = [
            {"tested_segment": "volatility_segment=mixed_volatility", "robustness_check_passed": True},
            {"tested_segment": "liquidity_segment=thin_sparse", "robustness_check_passed": False},
        ]

        result = _determine_go_no_go(
            candidate_id="baseline_v3_ema20_trend_guard",
            primary_summary=primary,
            supporting_summaries=supporting,
        )

        self.assertEqual("keep_experimental_for_segment_only_use", result["decision"])
        self.assertIn("liquidity_segment=thin_sparse", result["supporting_segments_failed"])
        self.assertFalse(result["global_promotion_allowed"])

    def test_decision_is_no_go_when_primary_oos_viability_fails(self) -> None:
        primary = {
            "tested_segment": "sentiment_segment=sentiment_poor",
            "primary_viable": False,
            "oos_stability_ok": False,
            "ticker_consistency_ok": False,
            "outlier_bias_ok": True,
            "candidate_total_trades": 9,
            "active_ticker_count": 2,
            "trade_weighted_average_return": -1.4,
            "mean_average_return_active": -0.8,
        }

        result = _determine_go_no_go(
            candidate_id="baseline_v3_ema20_trend_guard",
            primary_summary=primary,
            supporting_summaries=[],
        )

        self.assertEqual("no_go_even_for_segment", result["decision"])
        self.assertFalse(result["oos_stability_ok"])
        self.assertFalse(result["ticker_consistency_ok"])
        self.assertTrue(result["outlier_bias_ok"])
        self.assertFalse(result["global_promotion_allowed"])


if __name__ == "__main__":
    unittest.main()
