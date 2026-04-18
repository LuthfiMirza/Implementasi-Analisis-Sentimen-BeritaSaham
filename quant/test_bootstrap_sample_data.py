"""Smoke tests for sample-data bootstrap and validation helpers."""

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.bootstrap_sample_data import bootstrap_sample_dataset
from quant.evaluate_phase_a_real_data import evaluate_folder
from quant.validate_price_data import validate_folder


class BootstrapSampleDataTestCase(unittest.TestCase):
    """End-to-end coverage for bootstrap, validator, and evaluator."""

    def test_bootstrap_sample_data_creates_expected_csv_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir = Path(tmp_dir) / "data"

            created_files = bootstrap_sample_dataset(data_dir=data_dir, rows=130)

            self.assertEqual(
                {path.name for path in created_files},
                {"BBCA.csv", "BMRI.csv", "TLKM.csv"},
            )

            for path in created_files:
                frame = pd.read_csv(path)
                self.assertEqual(list(frame.columns), ["date", "open", "high", "low", "close", "volume"])
                self.assertGreaterEqual(len(frame), 120)
                parsed_dates = pd.to_datetime(frame["date"])
                self.assertTrue((parsed_dates.dt.dayofweek < 5).all())

    def test_validator_and_evaluator_run_end_to_end_on_bootstrapped_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir = Path(tmp_dir) / "data"
            output_dir = Path(tmp_dir) / "output"
            bootstrap_sample_dataset(data_dir=data_dir, rows=140)

            validation_df = validate_folder(data_dir, output_dir=output_dir)
            self.assertEqual(int((validation_df["status"] == "valid").sum()), 3)
            self.assertEqual(int((validation_df["status"] == "invalid").sum()), 0)
            self.assertTrue((output_dir / "data_validation_summary.csv").exists())

            summary_df, skipped_df, aggregate_df = evaluate_folder(
                folder_path=data_dir,
                output_dir=output_dir,
                evaluate_strict=True,
            )

            self.assertFalse(summary_df.empty)
            self.assertTrue(skipped_df.empty)
            self.assertFalse(aggregate_df.empty)
            self.assertTrue((output_dir / "phase_a_summary.csv").exists())


if __name__ == "__main__":
    unittest.main()
