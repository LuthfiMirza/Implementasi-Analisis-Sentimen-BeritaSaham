"""Tests for the baseline v7 segment-aware experiment."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.run_baseline_v6_guardrail_review import run_baseline_v6_guardrail_review
from quant.run_baseline_v7_segment_aware_experiment import (
    GO_NO_GO_OUTPUT,
    REPORT_OUTPUT,
    RESULT_OUTPUT,
    SUMMARY_OUTPUT,
    run_baseline_v7_segment_aware_experiment,
)
from quant.test_run_baseline_v6_guardrail_review import RunBaselineV6GuardrailReviewTestCase


class RunBaselineV7SegmentAwareExperimentTestCase(unittest.TestCase):
    def _prepare_with_v6(self, root: Path) -> tuple[Path, Path, Path]:
        helper = RunBaselineV6GuardrailReviewTestCase()
        data_dir, output_dir, metadata_file = helper._prepare_fixture(root)
        run_baseline_v6_guardrail_review(
            data_dir=data_dir,
            output_dir=output_dir,
            metadata_file=metadata_file,
        )
        return data_dir, output_dir, metadata_file

    def test_segment_aware_runner_generates_outputs_and_keeps_global_promotion_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            _, output_dir, _ = self._prepare_with_v6(root)

            result = run_baseline_v7_segment_aware_experiment(output_dir=output_dir)

            required = [
                output_dir / RESULT_OUTPUT,
                output_dir / SUMMARY_OUTPUT,
                output_dir / REPORT_OUTPUT,
                output_dir / GO_NO_GO_OUTPUT,
            ]
            for path in required:
                self.assertTrue(path.exists(), f"Missing artifact: {path}")

            go_no_go = json.loads((output_dir / GO_NO_GO_OUTPUT).read_text(encoding="utf-8"))
            self.assertEqual("keep_experimental_for_segment_review", go_no_go["decision"])
            self.assertEqual("baseline_v3_ema20_trend_guard", go_no_go["best_candidate_id"])
            self.assertFalse(go_no_go["global_promotion_allowed"])

            governance = json.loads((output_dir / "baseline_v6_next_experiment_governance.json").read_text(encoding="utf-8"))
            safe_segments = set(governance["segments_safe_to_test_next"])
            results_df = pd.read_csv(output_dir / RESULT_OUTPUT)
            self.assertFalse(results_df.empty)
            self.assertEqual(safe_segments, set(results_df["tested_segment"]))
            self.assertEqual(
                {"keep_experimental_for_segment_review", "no_go"},
                set(results_df["decision"]),
            )
            self.assertTrue((results_df["global_promotion_allowed"] == False).all())  # noqa: E712

            summary = json.loads((output_dir / SUMMARY_OUTPUT).read_text(encoding="utf-8"))
            self.assertEqual(len(safe_segments), len(summary["tested_safe_segments"]))
            self.assertIn("candidate_summaries", summary)
            self.assertIn("artifacts", result)

    def test_segment_aware_runner_returns_no_go_when_safe_segments_lose_support(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            _, output_dir, _ = self._prepare_with_v6(root)

            v3_results_path = output_dir / "baseline_v3_signal_rule_results.csv"
            v3_results = pd.read_csv(v3_results_path)
            mask = v3_results["rule_id"].astype(str).eq("baseline_v3_ema20_trend_guard")
            v3_results.loc[mask, "average_return"] = -4.0
            v3_results.loc[mask, "score"] = -8.0
            v3_results.to_csv(v3_results_path, index=False)

            run_baseline_v7_segment_aware_experiment(output_dir=output_dir)

            go_no_go = json.loads((output_dir / GO_NO_GO_OUTPUT).read_text(encoding="utf-8"))
            self.assertEqual("no_go", go_no_go["decision"])
            self.assertFalse(go_no_go["segment_support_ok"])
            self.assertFalse(go_no_go["global_promotion_allowed"])


if __name__ == "__main__":
    unittest.main()
