"""Tests for Phase B batch-1 completion check."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.run_phase_b_batch1_completion_check import run_phase_b_batch1_completion_check
from quant.run_phase_b_post_backfill_batch_verification import run_phase_b_post_backfill_batch_verification
from quant.test_run_phase_b_data_extension_ingest_audit import (
    RunPhaseBDataExtensionIngestAuditTestCase,
)


class RunPhaseBBatch1CompletionCheckTestCase(unittest.TestCase):
    def _prepare_fixture(self, root: Path) -> tuple[Path, Path, Path, RunPhaseBDataExtensionIngestAuditTestCase]:
        helper = RunPhaseBDataExtensionIngestAuditTestCase()
        data_dir, output_dir, metadata_file = helper._prepare_fixture(root=root, scenario="baseline", include_metadata=True)
        run_phase_b_post_backfill_batch_verification(
            data_dir=data_dir,
            output_dir=output_dir,
            metadata_file=metadata_file,
        )
        return data_dir, output_dir, metadata_file, helper

    def test_main_artifacts_are_generated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir, output_dir, metadata_file, _ = self._prepare_fixture(Path(tmp_dir))
            result = run_phase_b_batch1_completion_check(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
            )

            for name in [
                "phase_b_article_day_recovery_status.json",
                "phase_b_article_day_recovery_status.txt",
                "phase_b_segmentation_refresh_status.json",
                "phase_b_segmentation_refresh_status.txt",
                "phase_b_batch1_completion_decision.json",
            ]:
                self.assertTrue((output_dir / name).exists(), f"Missing artifact: {name}")

            self.assertIn("phase_b_batch1_completion_decision", result)

    def test_batch_1_stays_not_complete_when_article_day_is_still_below_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir, output_dir, metadata_file, helper = self._prepare_fixture(root)

            updated_article_days_map = {
                "AAA": {2, 6},
                "BBB": {3},
                "CCC": {4},
                "DDD": {5},
                "EEE": set(),
                "FFF": {7},
            }
            for ticker in updated_article_days_map:
                helper._write_price_csv(data_dir / f"{ticker}.csv", history_rows=118, article_days=updated_article_days_map[ticker])
            metadata = pd.read_csv(metadata_file)
            metadata["rows_1d"] = 118
            metadata["date_end"] = "2026-10-20"
            metadata["sentiment_days_with_articles"] = [len(updated_article_days_map[ticker]) for ticker in metadata["ticker"]]
            metadata["sentiment_article_count_total"] = metadata["sentiment_days_with_articles"]
            metadata.to_csv(metadata_file, index=False)

            result = run_phase_b_batch1_completion_check(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
            )

            decision = result["phase_b_batch1_completion_decision"]
            self.assertTrue(result["phase_b_segmentation_refresh_status"]["segmentation_refresh_completed"])
            self.assertEqual("batch_1_started_but_not_complete", decision["batch_1_status"])
            self.assertFalse(decision["batch_1_completed"])
            self.assertFalse(decision["checkpoint_material_reached"])

    def test_batch_1_complete_when_article_day_target_and_segmentation_sync_are_met(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir, output_dir, metadata_file, helper = self._prepare_fixture(root)

            updated_article_days_map = {
                "AAA": {2, 6, 12},
                "BBB": {3, 10, 14},
                "CCC": {4, 11, 15},
                "DDD": {5, 12, 16},
                "EEE": {13, 17, 21},
                "FFF": {8, 18, 22},
            }
            for ticker in updated_article_days_map:
                helper._write_price_csv(data_dir / f"{ticker}.csv", history_rows=78, article_days=updated_article_days_map[ticker])
            metadata = pd.read_csv(metadata_file)
            metadata["rows_1d"] = 78
            metadata["date_end"] = "2026-08-31"
            metadata["sentiment_days_with_articles"] = [len(updated_article_days_map[ticker]) for ticker in metadata["ticker"]]
            metadata["sentiment_article_count_total"] = metadata["sentiment_days_with_articles"]
            metadata.to_csv(metadata_file, index=False)

            result = run_phase_b_batch1_completion_check(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
            )

            decision = result["phase_b_batch1_completion_decision"]
            self.assertTrue(result["phase_b_segmentation_refresh_status"]["segmentation_refresh_completed"])
            self.assertEqual("batch_1_complete_but_checkpoint_not_material", decision["batch_1_status"])
            self.assertTrue(decision["batch_1_completed"])
            self.assertFalse(decision["checkpoint_material_reached"])
            self.assertFalse(decision["recheck_readiness_gate_allowed"])

if __name__ == "__main__":
    unittest.main()
