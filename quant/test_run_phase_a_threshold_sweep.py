"""Smoke tests for the Phase A threshold sweep runner."""

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.bootstrap_sample_data import bootstrap_sample_dataset
from quant.run_phase_a_threshold_sweep import run_phase_a_threshold_sweep


class RunPhaseAThresholdSweepTestCase(unittest.TestCase):
    """Validate core exports from the threshold sweep experiment."""

    def test_threshold_sweep_exports_outputs_without_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir = root / "data"
            output_dir = root / "output"

            bootstrap_sample_dataset(data_dir=data_dir, rows=140)
            artifacts = run_phase_a_threshold_sweep(
                data_dir=data_dir,
                output_dir=output_dir,
                thresholds=[1.5, 2.0, 2.5, 3.0],
                strict=True,
                min_trades=2,
            )

            self.assertFalse(artifacts["results_df"].empty)
            self.assertFalse(artifacts["best_by_ticker_df"].empty)
            self.assertFalse(artifacts["global_summary_df"].empty)
            self.assertTrue((output_dir / "phase_a_threshold_sweep_results.csv").exists())
            self.assertTrue((output_dir / "phase_a_threshold_best_by_ticker.csv").exists())
            self.assertTrue((output_dir / "phase_a_threshold_global_summary.csv").exists())
            self.assertTrue((output_dir / "phase_a_threshold_recommendations.txt").exists())
            self.assertTrue((output_dir / "phase_a_threshold_decision.json").exists())
            self.assertFalse((output_dir / "phase_a_threshold_group_summary.csv").exists())
            self.assertFalse((output_dir / "phase_a_threshold_best_by_group.csv").exists())

            decision_payload = json.loads(
                (output_dir / "phase_a_threshold_decision.json").read_text(encoding="utf-8")
            )
            self.assertIn("default_threshold_decision", decision_payload)
            self.assertIn("readiness", decision_payload)

    def test_threshold_sweep_exports_group_outputs_with_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir = root / "data"
            output_dir = root / "output"
            metadata_path = root / "ticker_metadata.csv"

            bootstrap_sample_dataset(data_dir=data_dir, rows=140)
            pd.DataFrame(
                {
                    "ticker": ["BBCA", "BMRI", "TLKM"],
                    "category": ["bank", "bank", "telco"],
                    "market_cap_group": ["big_cap", "big_cap", "big_cap"],
                    "sector": ["finance", "finance", "telecom"],
                    "beta_group": ["medium", "high", "medium"],
                }
            ).to_csv(metadata_path, index=False)

            artifacts = run_phase_a_threshold_sweep(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_path,
                thresholds=[1.5, 2.0, 2.5, 3.0],
                min_trades=2,
            )

            self.assertTrue((output_dir / "phase_a_threshold_group_summary.csv").exists())
            self.assertTrue((output_dir / "phase_a_threshold_best_by_group.csv").exists())
            self.assertFalse(artifacts["group_summary_df"].empty)
            self.assertFalse(artifacts["best_by_group_df"].empty)


if __name__ == "__main__":
    unittest.main()
