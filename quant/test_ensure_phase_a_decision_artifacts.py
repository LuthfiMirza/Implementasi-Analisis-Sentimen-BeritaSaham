"""Tests for ensuring Phase A decision artifacts."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from quant.bootstrap_sample_data import bootstrap_sample_dataset
from quant.ensure_phase_a_decision_artifacts import ensure_phase_a_decision_artifacts


class EnsurePhaseADecisionArtifactsTestCase(unittest.TestCase):
    """Validate decision-artifact orchestration and blocker reporting."""

    def test_reports_blockers_when_artifacts_and_data_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            output_dir = root / "output"

            result = ensure_phase_a_decision_artifacts(
                output_dir=output_dir,
                data_dir=root / "missing-data",
                build_missing=False,
            )

            payload = result["status_payload"]
            self.assertFalse(payload["threshold_decision_valid"])
            self.assertFalse(payload["tuning_decision_valid"])
            self.assertFalse(payload["all_required_decisions_ready"])
            self.assertTrue(payload["blockers"])
            self.assertTrue((output_dir / "phase_a_decision_artifact_status.json").exists())
            self.assertTrue((output_dir / "phase_a_decision_artifact_report.txt").exists())

    def test_builds_threshold_and_tuning_artifacts_when_inputs_are_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir = root / "data"
            output_dir = root / "output"

            bootstrap_sample_dataset(data_dir=data_dir, rows=140)

            result = ensure_phase_a_decision_artifacts(
                output_dir=output_dir,
                data_dir=data_dir,
                min_trades=2,
                build_missing=True,
            )

            payload = result["status_payload"]
            self.assertTrue(payload["threshold_decision_valid"])
            self.assertTrue(payload["tuning_decision_valid"])
            self.assertTrue(payload["all_required_decisions_ready"])
            self.assertTrue((output_dir / "phase_a_threshold_decision.json").exists())
            self.assertTrue((output_dir / "phase_a_tuning_decision.json").exists())


if __name__ == "__main__":
    unittest.main()
