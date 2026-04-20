"""Tests for the baseline v8 segment-only validation runner."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.run_baseline_v6_guardrail_review import run_baseline_v6_guardrail_review
from quant.run_baseline_v7_segment_aware_experiment import run_baseline_v7_segment_aware_experiment
from quant.run_baseline_v8_segment_only_validation import (
    GO_NO_GO_OUTPUT,
    REPORT_OUTPUT,
    RESULT_OUTPUT,
    SUMMARY_OUTPUT,
    run_baseline_v8_segment_only_validation,
)
from quant.test_run_baseline_v6_guardrail_review import RunBaselineV6GuardrailReviewTestCase


class RunBaselineV8SegmentOnlyValidationTestCase(unittest.TestCase):
    def _prepare_with_v7(self, root: Path) -> Path:
        helper = RunBaselineV6GuardrailReviewTestCase()
        data_dir, output_dir, metadata_file = helper._prepare_fixture(root)
        run_baseline_v6_guardrail_review(
            data_dir=data_dir,
            output_dir=output_dir,
            metadata_file=metadata_file,
        )
        run_baseline_v7_segment_aware_experiment(output_dir=output_dir)
        return output_dir

    def test_v8_promotes_to_segment_only_validation_when_primary_and_supporting_segments_hold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = self._prepare_with_v7(Path(tmp_dir))

            result = run_baseline_v8_segment_only_validation(output_dir=output_dir)

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
            self.assertEqual("promote_to_segment_only_validation", go_no_go["decision"])
            self.assertTrue(go_no_go["segment_stability_ok"])
            self.assertFalse(go_no_go["global_promotion_allowed"])

            governance = json.loads((output_dir / "baseline_v6_next_experiment_governance.json").read_text(encoding="utf-8"))
            results_df = pd.read_csv(output_dir / RESULT_OUTPUT)
            self.assertEqual(len(governance["segments_safe_to_test_next"]), len(results_df))
            self.assertEqual(1, int((results_df["segment_role"] == "primary").sum()))
            self.assertTrue(results_df["support_check_passed"].fillna(False).all())
            self.assertIn("artifacts", result)

    def test_v8_stays_experimental_when_primary_holds_but_one_supporting_segment_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = self._prepare_with_v7(Path(tmp_dir))

            v7_results_path = output_dir / "baseline_v7_segment_aware_results.csv"
            v7_results = pd.read_csv(v7_results_path)
            mask = (
                v7_results["candidate_id"].astype(str).eq("baseline_v3_ema20_trend_guard")
                & v7_results["tested_segment"].astype(str).eq("liquidity_segment=thin_sparse")
            )
            v7_results.loc[mask, "segment_support_ok"] = False
            v7_results.loc[mask, "decision"] = "no_go"
            v7_results.loc[mask, "mean_average_return_eligible"] = -0.25
            v7_results.to_csv(v7_results_path, index=False)

            run_baseline_v8_segment_only_validation(output_dir=output_dir)

            go_no_go = json.loads((output_dir / GO_NO_GO_OUTPUT).read_text(encoding="utf-8"))
            self.assertEqual("stay_keep_experimental_for_segment_review", go_no_go["decision"])
            self.assertFalse(go_no_go["segment_stability_ok"])
            self.assertIn("liquidity_segment=thin_sparse", go_no_go["supporting_segments_failed"])

    def test_v8_returns_no_go_when_primary_segment_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = self._prepare_with_v7(Path(tmp_dir))

            v7_results_path = output_dir / "baseline_v7_segment_aware_results.csv"
            v7_results = pd.read_csv(v7_results_path)
            mask = (
                v7_results["candidate_id"].astype(str).eq("baseline_v3_ema20_trend_guard")
                & v7_results["tested_segment"].astype(str).eq("sentiment_segment=sentiment_poor")
            )
            v7_results.loc[mask, "segment_support_ok"] = False
            v7_results.loc[mask, "decision"] = "no_go"
            v7_results.loc[mask, "mean_average_return_eligible"] = -1.0
            v7_results.to_csv(v7_results_path, index=False)

            run_baseline_v8_segment_only_validation(output_dir=output_dir)

            go_no_go = json.loads((output_dir / GO_NO_GO_OUTPUT).read_text(encoding="utf-8"))
            self.assertEqual("no_go", go_no_go["decision"])
            self.assertFalse(go_no_go["segment_stability_ok"])
            self.assertFalse(go_no_go["primary_segment_support_ok"])
            self.assertFalse(go_no_go["global_promotion_allowed"])


if __name__ == "__main__":
    unittest.main()
