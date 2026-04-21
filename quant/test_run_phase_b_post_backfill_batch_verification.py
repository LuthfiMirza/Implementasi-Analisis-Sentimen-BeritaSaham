"""Tests for Phase B post-backfill batch verification runner."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.run_phase_b_post_backfill_batch_verification import run_phase_b_post_backfill_batch_verification
from quant.test_run_phase_b_data_extension_ingest_audit import (
    RunPhaseBDataExtensionIngestAuditTestCase,
)


class RunPhaseBPostBackfillBatchVerificationTestCase(unittest.TestCase):
    def _prepare_fixture(self, root: Path) -> tuple[Path, Path, Path, RunPhaseBDataExtensionIngestAuditTestCase]:
        helper = RunPhaseBDataExtensionIngestAuditTestCase()
        data_dir, output_dir, metadata_file = helper._prepare_fixture(root=root, scenario="baseline", include_metadata=True)
        return data_dir, output_dir, metadata_file, helper

    def test_main_artifacts_are_generated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir, output_dir, metadata_file, _ = self._prepare_fixture(Path(tmp_dir))
            result = run_phase_b_post_backfill_batch_verification(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
            )

            for name in [
                "phase_b_post_backfill_ingest_audit.json",
                "phase_b_post_backfill_ingest_audit.txt",
                "phase_b_post_backfill_progress_update.json",
                "phase_b_post_backfill_progress_update.txt",
                "phase_b_post_backfill_batch1_decision.json",
            ]:
                self.assertTrue((output_dir / name).exists(), f"Missing artifact: {name}")

            self.assertIn("phase_b_post_backfill_batch1_decision", result)

    def test_batch_1_stays_not_started_when_snapshot_is_static(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir, output_dir, metadata_file, _ = self._prepare_fixture(Path(tmp_dir))
            result = run_phase_b_post_backfill_batch_verification(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
            )

            decision = result["phase_b_post_backfill_batch1_decision"]
            self.assertEqual("batch_1_not_started_snapshot_still_static", decision["batch_1_status"])
            self.assertFalse(decision["batch_1_officially_started"])
            self.assertFalse(decision["batch_1_completed"])
            self.assertFalse(decision["checkpoint_material_reached"])
            self.assertFalse(decision["recheck_readiness_gate_allowed"])

    def test_batch_1_started_but_not_complete_when_history_moves_without_article_day_recovery(self) -> None:
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
                helper._write_price_csv(data_dir / f"{ticker}.csv", history_rows=78, article_days=updated_article_days_map[ticker])
            metadata = pd.read_csv(metadata_file)
            metadata["rows_1d"] = 78
            metadata["date_end"] = "2026-08-31"
            metadata.to_csv(metadata_file, index=False)
            segmentation_path = output_dir / "baseline_v6_universe_segmentation.csv"
            segmentation = pd.read_csv(segmentation_path)
            segmentation["rows"] = 78
            segmentation["history_rows"] = 78
            segmentation["date_end"] = "2026-08-31"
            segmentation.to_csv(segmentation_path, index=False)

            result = run_phase_b_post_backfill_batch_verification(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
            )

            decision = result["phase_b_post_backfill_batch1_decision"]
            self.assertEqual("batch_1_started_but_not_complete", decision["batch_1_status"])
            self.assertTrue(decision["batch_1_officially_started"])
            self.assertFalse(decision["batch_1_completed"])
            self.assertFalse(decision["checkpoint_material_reached"])
            self.assertFalse(decision["recheck_readiness_gate_allowed"])

    def test_batch_1_complete_but_checkpoint_not_material_when_history_closes_before_checkpoint(self) -> None:
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
            segmentation_path = output_dir / "baseline_v6_universe_segmentation.csv"
            segmentation = pd.read_csv(segmentation_path)
            segmentation["rows"] = 78
            segmentation["history_rows"] = 78
            segmentation["date_end"] = "2026-08-31"
            segmentation["article_days"] = [len(updated_article_days_map[ticker]) for ticker in segmentation["ticker"]]
            segmentation["article_count_total"] = segmentation["article_days"]
            segmentation["news_count_total"] = segmentation["article_days"]
            segmentation["news_density_pct"] = [round(100.0 * value / 78, 4) for value in segmentation["article_days"]]
            segmentation.to_csv(segmentation_path, index=False)

            result = run_phase_b_post_backfill_batch_verification(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
            )

            decision = result["phase_b_post_backfill_batch1_decision"]
            self.assertEqual("batch_1_complete_but_checkpoint_not_material", decision["batch_1_status"])
            self.assertTrue(decision["batch_1_officially_started"])
            self.assertTrue(decision["batch_1_completed"])
            self.assertFalse(decision["checkpoint_material_reached"])
            self.assertFalse(decision["recheck_readiness_gate_allowed"])

    def test_checkpoint_material_reached_allows_recheck(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir, output_dir, metadata_file, helper = self._prepare_fixture(root)

            updated_article_days_map = {
                "AAA": {2, 6, 10},
                "BBB": {3, 7, 11},
                "CCC": {4, 8, 12},
                "DDD": {5, 9, 13},
                "EEE": {18, 22, 26},
                "FFF": {19, 23, 27},
            }
            for ticker in updated_article_days_map:
                helper._write_price_csv(data_dir / f"{ticker}.csv", history_rows=99, article_days=updated_article_days_map[ticker])
            metadata = pd.read_csv(metadata_file)
            metadata["rows_1d"] = 99
            metadata["date_end"] = "2026-09-30"
            metadata["sentiment_days_with_articles"] = [len(updated_article_days_map[ticker]) for ticker in metadata["ticker"]]
            metadata["sentiment_article_count_total"] = metadata["sentiment_days_with_articles"]
            metadata.to_csv(metadata_file, index=False)
            segmentation_path = output_dir / "baseline_v6_universe_segmentation.csv"
            segmentation = pd.read_csv(segmentation_path)
            segmentation["rows"] = 99
            segmentation["history_rows"] = 99
            segmentation["date_end"] = "2026-09-30"
            segmentation["article_days"] = [len(updated_article_days_map[ticker]) for ticker in segmentation["ticker"]]
            segmentation["article_count_total"] = segmentation["article_days"]
            segmentation["news_count_total"] = segmentation["article_days"]
            segmentation["news_density_pct"] = [round(100.0 * value / 99, 4) for value in segmentation["article_days"]]
            segmentation.to_csv(segmentation_path, index=False)

            result = run_phase_b_post_backfill_batch_verification(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
            )

            decision = result["phase_b_post_backfill_batch1_decision"]
            self.assertEqual("batch_1_complete_and_checkpoint_material_reached", decision["batch_1_status"])
            self.assertTrue(decision["batch_1_officially_started"])
            self.assertTrue(decision["batch_1_completed"])
            self.assertTrue(decision["checkpoint_material_reached"])
            self.assertTrue(decision["recheck_readiness_gate_allowed"])
            self.assertEqual([], decision["remaining_blockers"])


if __name__ == "__main__":
    unittest.main()
