"""Tests for Phase B data-extension ingest rejection analysis runner."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.run_phase_b_data_extension_ingest_audit import run_phase_b_data_extension_ingest_audit
from quant.run_phase_b_data_extension_ingest_rejection_analysis import (
    run_phase_b_data_extension_ingest_rejection_analysis,
)
from quant.test_run_phase_b_data_extension_ingest_audit import (
    RunPhaseBDataExtensionIngestAuditTestCase,
)


class RunPhaseBDataExtensionIngestRejectionAnalysisTestCase(unittest.TestCase):
    def _prepare_with_ingest(self, root: Path, scenario: str = "baseline", include_metadata: bool = True) -> tuple[Path, Path, Path]:
        helper = RunPhaseBDataExtensionIngestAuditTestCase()
        data_dir, output_dir, metadata_file = helper._prepare_fixture(root=root, scenario=scenario, include_metadata=include_metadata)
        run_phase_b_data_extension_ingest_audit(
            data_dir=data_dir,
            output_dir=output_dir,
            metadata_file=metadata_file,
        )
        return data_dir, output_dir, metadata_file

    def test_main_artifacts_are_generated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir, output_dir, metadata_file = self._prepare_with_ingest(Path(tmp_dir))
            result = run_phase_b_data_extension_ingest_rejection_analysis(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
            )

            for name in [
                "phase_b_data_extension_ingest_rejection_analysis.json",
                "phase_b_data_extension_ingest_rejection_analysis.txt",
                "phase_b_data_extension_ingest_priority_checklist.csv",
                "phase_b_data_extension_ingest_ticker_diagnostics.csv",
                "phase_b_data_extension_ingest_go_no_go.json",
            ]:
                self.assertTrue((output_dir / name).exists(), f"Missing artifact: {name}")

            self.assertIn("phase_b_data_extension_ingest_go_no_go", result)

    def test_rejected_snapshot_keeps_decision_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir, output_dir, metadata_file = self._prepare_with_ingest(Path(tmp_dir), scenario="baseline")
            result = run_phase_b_data_extension_ingest_rejection_analysis(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
            )

            payload = result["phase_b_data_extension_ingest_go_no_go"]
            self.assertEqual("ingest_rejected_no_material_progress", payload["decision"])
            self.assertFalse(payload["material_progress_detected"])
            self.assertEqual("history_effective_not_increasing", payload["highest_blocking_issue"])

    def test_valid_progress_can_be_accepted_but_batch_not_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir, output_dir, metadata_file = self._prepare_with_ingest(Path(tmp_dir), scenario="valid_ingest")

            matrix_path = output_dir / "phase_b_data_extension_ingest_matrix.csv"
            frame = pd.read_csv(matrix_path)
            frame.loc[frame["ticker"].astype(str).eq("AAA"), "metadata_ready"] = False
            frame.to_csv(matrix_path, index=False)

            acceptance_path = output_dir / "phase_b_ingest_acceptance_decision.json"
            acceptance = json.loads(acceptance_path.read_text(encoding="utf-8"))
            acceptance["batch_acceptance_status"] = "accepted_with_warnings"
            acceptance["accepted_tickers"] = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
            acceptance["rejected_tickers"] = []
            acceptance["tickers_with_warnings"] = ["AAA"]
            acceptance_path.write_text(json.dumps(acceptance, indent=2), encoding="utf-8")

            result = run_phase_b_data_extension_ingest_rejection_analysis(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
            )
            payload = result["phase_b_data_extension_ingest_go_no_go"]
            self.assertEqual("ingest_accepted_but_batch_not_complete", payload["decision"])
            self.assertTrue(payload["material_progress_detected"])
            self.assertFalse(payload["metadata_refresh_valid"])

    def test_batch_1_complete_is_reported_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir, output_dir, metadata_file = self._prepare_with_ingest(Path(tmp_dir), scenario="valid_ingest")
            result = run_phase_b_data_extension_ingest_rejection_analysis(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
            )
            payload = result["phase_b_data_extension_ingest_go_no_go"]
            self.assertEqual("ingest_accepted_batch_1_complete", payload["decision"])
            self.assertTrue(payload["material_progress_detected"])
            self.assertTrue(payload["batch_1_closure_progress_valid"])

    def test_script_runs_with_limited_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir, output_dir, metadata_file = self._prepare_with_ingest(Path(tmp_dir), include_metadata=False)
            result = run_phase_b_data_extension_ingest_rejection_analysis(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
            )
            self.assertTrue((output_dir / "phase_b_data_extension_ingest_ticker_diagnostics.csv").exists())
            self.assertTrue(any("ticker_metadata.csv unavailable" in item for item in result["phase_b_data_extension_ingest_go_no_go"]["limitations"]))


if __name__ == "__main__":
    unittest.main()
