"""Smoke tests for the Phase A tuning decision layer."""

import json
import tempfile
import unittest
from pathlib import Path

from quant.analyze_phase_a_results import analyze_phase_a_results
from quant.bootstrap_sample_data import bootstrap_sample_dataset
from quant.decide_phase_a_tuning import decide_phase_a_tuning
from quant.evaluate_phase_a_real_data import evaluate_folder


class DecidePhaseATuningTestCase(unittest.TestCase):
    """Validate decision exports on top of analyzer artifacts."""

    def test_decision_layer_exports_outputs_without_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir = root / "data"
            eval_output_dir = root / "eval-output"
            analysis_output_dir = root / "analysis-output"
            decision_output_dir = root / "decision-output"

            bootstrap_sample_dataset(data_dir=data_dir, rows=140)
            evaluate_folder(
                folder_path=data_dir,
                output_dir=eval_output_dir,
                evaluate_strict=True,
            )
            analyze_phase_a_results(
                summary_file=eval_output_dir / "phase_a_summary.csv",
                aggregate_file=eval_output_dir / "phase_a_aggregate_summary.csv",
                skipped_file=eval_output_dir / "phase_a_skipped.csv",
                output_dir=analysis_output_dir,
            )

            artifacts = decide_phase_a_tuning(
                recommendations_file=analysis_output_dir / "phase_a_recommendations.txt",
                classification_file=analysis_output_dir / "phase_a_ticker_classification.csv",
                analysis_summary_file=analysis_output_dir / "phase_a_analysis_summary.csv",
                group_analysis_file=analysis_output_dir / "phase_a_group_analysis.csv",
                summary_file=eval_output_dir / "phase_a_summary.csv",
                output_dir=decision_output_dir,
            )

            self.assertTrue((decision_output_dir / "phase_a_tuning_decision.json").exists())
            self.assertTrue((decision_output_dir / "phase_a_tuning_plan.txt").exists())
            self.assertTrue((decision_output_dir / "phase_a_ticker_actions.csv").exists())
            self.assertTrue((decision_output_dir / "phase_a_next_experiments.csv").exists())
            self.assertFalse(artifacts["ticker_actions_df"].empty)
            self.assertFalse(artifacts["next_experiments_df"].empty)
            self.assertIn("status", artifacts["readiness"])

            decision_payload = json.loads(
                (decision_output_dir / "phase_a_tuning_decision.json").read_text(encoding="utf-8")
            )
            self.assertIn("default_threshold_decision", decision_payload)
            self.assertIn("ready_for_phase_b", decision_payload)


if __name__ == "__main__":
    unittest.main()
