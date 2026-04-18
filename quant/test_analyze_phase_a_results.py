"""Smoke tests for Phase A result analysis."""

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.analyze_phase_a_results import analyze_phase_a_results
from quant.bootstrap_sample_data import bootstrap_sample_dataset
from quant.evaluate_phase_a_real_data import evaluate_folder


class AnalyzePhaseAResultsTestCase(unittest.TestCase):
    """Validate analysis export flow on evaluator outputs."""

    def test_analysis_exports_summary_recommendations_and_classification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir = root / "data"
            eval_output_dir = root / "eval-output"
            analysis_output_dir = root / "analysis-output"

            bootstrap_sample_dataset(data_dir=data_dir, rows=140)
            evaluate_folder(
                folder_path=data_dir,
                output_dir=eval_output_dir,
                evaluate_strict=True,
            )

            metadata_df = pd.DataFrame(
                {
                    "ticker": ["BBCA", "BMRI", "TLKM"],
                    "category": ["bank", "bank", "telco"],
                    "market_cap_group": ["big_cap", "big_cap", "big_cap"],
                    "sector": ["finance", "finance", "telecom"],
                    "beta_group": ["medium", "high", "medium"],
                }
            )
            metadata_path = root / "ticker_metadata.csv"
            metadata_df.to_csv(metadata_path, index=False)

            artifacts = analyze_phase_a_results(
                summary_file=eval_output_dir / "phase_a_summary.csv",
                aggregate_file=eval_output_dir / "phase_a_aggregate_summary.csv",
                skipped_file=eval_output_dir / "phase_a_skipped.csv",
                metadata_file=metadata_path,
                output_dir=analysis_output_dir,
            )

            self.assertFalse(artifacts["classification_df"].empty)
            self.assertIn("classification", artifacts["classification_df"].columns)
            self.assertTrue((analysis_output_dir / "phase_a_analysis_summary.csv").exists())
            self.assertTrue((analysis_output_dir / "phase_a_ticker_classification.csv").exists())
            self.assertTrue((analysis_output_dir / "phase_a_recommendations.txt").exists())
            self.assertTrue((analysis_output_dir / "phase_a_group_analysis.csv").exists())


if __name__ == "__main__":
    unittest.main()
