"""Tests for Phase B primary article coverage push runner."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.run_phase_b_batch1_completion_check import run_phase_b_batch1_completion_check
from quant.run_phase_b_post_backfill_batch_verification import run_phase_b_post_backfill_batch_verification
from quant.run_phase_b_primary_article_coverage_push import run_phase_b_primary_article_coverage_push
from quant.test_run_phase_b_data_extension_ingest_audit import (
    RunPhaseBDataExtensionIngestAuditTestCase,
)


class RunPhaseBPrimaryArticleCoveragePushTestCase(unittest.TestCase):
    def _prepare_fixture(self, root: Path) -> tuple[Path, Path, Path, RunPhaseBDataExtensionIngestAuditTestCase]:
        helper = RunPhaseBDataExtensionIngestAuditTestCase()
        data_dir, output_dir, metadata_file = helper._prepare_fixture(root=root, scenario="baseline", include_metadata=True)
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
        run_phase_b_post_backfill_batch_verification(
            data_dir=data_dir,
            output_dir=output_dir,
            metadata_file=metadata_file,
        )
        run_phase_b_batch1_completion_check(
            data_dir=data_dir,
            output_dir=output_dir,
            metadata_file=metadata_file,
        )
        return data_dir, output_dir, metadata_file, helper

    def test_main_artifacts_are_generated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir, output_dir, metadata_file, _ = self._prepare_fixture(Path(tmp_dir))

            def coverage_probe(tickers, cwd):
                return {ticker: {"article_count_total": 0, "article_days": 0, "high_quality_count": 0, "by_provider": {}} for ticker in tickers}

            result = run_phase_b_primary_article_coverage_push(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
                priority_tickers=["AAA", "BBB", "CCC"],
                providers=["gnews"],
                command_executor=lambda command, cwd: {"command": " ".join(command), "returncode": 0, "stdout": "", "stderr": "", "combined_output": "AAA: raw 0, saved 0, updated 0", "succeeded": True},
                coverage_probe=coverage_probe,
            )

            for name in [
                "phase_b_primary_article_coverage_push.json",
                "phase_b_primary_article_coverage_push.txt",
                "phase_b_primary_article_coverage_ticker_breakdown.csv",
                "phase_b_batch1_after_article_push.json",
                "phase_b_batch1_after_article_push.txt",
            ]:
                self.assertTrue((output_dir / name).exists(), f"Missing artifact: {name}")

            self.assertIn("phase_b_batch1_after_article_push", result)

    def test_batch_remains_not_complete_when_article_push_is_insufficient(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir, output_dir, metadata_file, _ = self._prepare_fixture(Path(tmp_dir))

            def coverage_probe(tickers, cwd):
                return {ticker: {"article_count_total": 1, "article_days": 1, "high_quality_count": 1, "by_provider": {"mock": 1}} for ticker in tickers}

            result = run_phase_b_primary_article_coverage_push(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
                priority_tickers=["AAA", "BBB", "CCC"],
                providers=["gnews"],
                command_executor=lambda command, cwd: {"command": " ".join(command), "returncode": 0, "stdout": "", "stderr": "", "combined_output": "AAA: raw 0, saved 0, updated 0", "succeeded": True},
                coverage_probe=coverage_probe,
            )

            payload = result["phase_b_batch1_after_article_push"]
            self.assertEqual("batch_1_started_but_not_complete", payload["batch_1_status"])
            self.assertFalse(payload["batch_1_completed"])
            self.assertFalse(payload["checkpoint_material_reached"])
            self.assertFalse(payload["recheck_readiness_gate_allowed"])

    def test_batch_becomes_complete_when_article_push_closes_batch_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir, output_dir, metadata_file, helper = self._prepare_fixture(root)

            def after_fetch_hook(data_dir: Path, output_dir: Path, metadata_file: Path) -> None:
                updated_article_days_map = {
                    "AAA": {2, 6, 12},
                    "BBB": {3, 10, 14},
                    "CCC": {4, 11, 15},
                    "DDD": {5, 12, 16},
                    "EEE": {13, 17, 21},
                    "FFF": {8, 18, 22},
                }
                for ticker in updated_article_days_map:
                    helper._write_price_csv(data_dir / f"{ticker}.csv", history_rows=118, article_days=updated_article_days_map[ticker])
                metadata = pd.read_csv(metadata_file)
                metadata["rows_1d"] = 118
                metadata["date_end"] = "2026-10-20"
                metadata["sentiment_days_with_articles"] = [len(updated_article_days_map[ticker]) for ticker in metadata["ticker"]]
                metadata["sentiment_article_count_total"] = metadata["sentiment_days_with_articles"]
                metadata.to_csv(metadata_file, index=False)

            def coverage_probe(tickers, cwd):
                return {ticker: {"article_count_total": 3, "article_days": 3, "high_quality_count": 3, "by_provider": {"mock": 3}} for ticker in tickers}

            result = run_phase_b_primary_article_coverage_push(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
                priority_tickers=["AAA", "BBB", "CCC"],
                providers=["gnews"],
                command_executor=lambda command, cwd: {"command": " ".join(command), "returncode": 0, "stdout": "", "stderr": "", "combined_output": "AAA: raw 3, saved 3, updated 0", "succeeded": True},
                coverage_probe=coverage_probe,
                after_fetch_hook=after_fetch_hook,
            )

            payload = result["phase_b_batch1_after_article_push"]
            self.assertEqual("batch_1_complete_but_checkpoint_not_material", payload["batch_1_status"])
            self.assertTrue(payload["batch_1_completed"])
            self.assertFalse(payload["checkpoint_material_reached"])
            self.assertFalse(payload["recheck_readiness_gate_allowed"])


if __name__ == "__main__":
    unittest.main()
