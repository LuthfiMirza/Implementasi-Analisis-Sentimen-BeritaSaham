"""Tests for Phase B priority backfill execution runner."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.run_phase_b_data_extension_ingest_audit import run_phase_b_data_extension_ingest_audit
from quant.run_phase_b_data_extension_ingest_rejection_analysis import (
    run_phase_b_data_extension_ingest_rejection_analysis,
)
from quant.run_phase_b_data_extension_pipeline_root_cause import (
    run_phase_b_data_extension_pipeline_root_cause,
)
from quant.run_phase_b_priority_backfill_execution import run_phase_b_priority_backfill_execution
from quant.test_run_phase_b_data_extension_ingest_audit import (
    RunPhaseBDataExtensionIngestAuditTestCase,
)


def _write_text(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class RunPhaseBPriorityBackfillExecutionTestCase(unittest.TestCase):
    def _mock_code_paths(self, root: Path) -> dict[str, Path]:
        fetch_content = """<?php
class FetchStockHistoryCommand {
    protected function resolveYahooRange(int $days): string {
        // Fix history-range cap so requests above 90 days can actually extend beyond the old 3mo window.
        if ($days <= 180) { return '6mo'; }
        if ($days <= 365) { return '1y'; }
        return 'max';
    }
}
"""
        export_content = """<?php
class ExportPhaseARealDataCommand {
    public function handle(): void {
        StockPrice::query();
        $metadataPath = 'ticker_metadata.csv';
        $this->writeCsv($tickerPath, []);
        $this->writeCsv($metadataPath, []);
    }
}
"""
        update_content = """<?php
class UpdateStockSnapshotsCommand {
    public function handle(): void {
        $date = Carbon::now()->subDays(1);
        $delta = random_int(-50, 50);
        StockPrice::updateOrCreate([]);
    }
}
"""
        routes_content = """<?php
Schedule::command('stocks:fetch-history --days=1');
Schedule::command('stocks:fetch-history --days=1');
"""
        segmentation_content = 'SEGMENTATION_CSV_OUTPUT = "baseline_v6_universe_segmentation.csv"'
        return {
            "fetch_command_file": _write_text(root / "app/Console/Commands/FetchStockHistoryCommand.php", fetch_content),
            "export_command_file": _write_text(root / "app/Console/Commands/ExportPhaseARealDataCommand.php", export_content),
            "update_snapshots_file": _write_text(root / "app/Console/Commands/UpdateStockSnapshotsCommand.php", update_content),
            "routes_console_file": _write_text(root / "routes/console.php", routes_content),
            "segmentation_runner_file": _write_text(root / "quant/run_baseline_v6_guardrail_review.py", segmentation_content),
        }

    def _prepare_pipeline_context(self, root: Path) -> tuple[Path, Path, Path, RunPhaseBDataExtensionIngestAuditTestCase]:
        helper = RunPhaseBDataExtensionIngestAuditTestCase()
        data_dir, output_dir, metadata_file = helper._prepare_fixture(root=root, scenario="baseline", include_metadata=True)
        run_phase_b_data_extension_ingest_audit(
            data_dir=data_dir,
            output_dir=output_dir,
            metadata_file=metadata_file,
        )
        run_phase_b_data_extension_ingest_rejection_analysis(
            data_dir=data_dir,
            output_dir=output_dir,
            metadata_file=metadata_file,
        )
        run_phase_b_data_extension_pipeline_root_cause(
            data_dir=data_dir,
            output_dir=output_dir,
            metadata_file=metadata_file,
            **self._mock_code_paths(root / "codepaths"),
        )
        return data_dir, output_dir, metadata_file, helper

    def test_main_artifacts_are_generated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir, output_dir, metadata_file, _ = self._prepare_pipeline_context(Path(tmp_dir))

            def executor(command: list[str], cwd: Path) -> dict[str, object]:
                return {"command": " ".join(command), "returncode": 1, "stdout": "", "stderr": "connection refused", "combined_output": "connection refused", "succeeded": False}

            result = run_phase_b_priority_backfill_execution(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
                command_executor=executor,
            )

            for name in [
                "phase_b_priority_backfill_execution.json",
                "phase_b_priority_backfill_execution.txt",
                "phase_b_priority_backfill_row_advance.csv",
                "phase_b_priority_backfill_batch1_status.json",
                "phase_b_priority_backfill_next_steps.json",
            ]:
                self.assertTrue((output_dir / name).exists(), f"Missing artifact: {name}")

            self.assertIn("phase_b_priority_backfill_execution", result)

    def test_static_snapshot_keeps_batch_1_not_started(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir, output_dir, metadata_file, _ = self._prepare_pipeline_context(Path(tmp_dir))

            def executor(command: list[str], cwd: Path) -> dict[str, object]:
                return {"command": " ".join(command), "returncode": 1, "stdout": "", "stderr": "connection refused", "combined_output": "connection refused", "succeeded": False}

            result = run_phase_b_priority_backfill_execution(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
                command_executor=executor,
            )

            payload = result["phase_b_priority_backfill_batch1_status"]
            self.assertEqual("batch_1_not_started_snapshot_still_static", payload["batch_1_status"])
            self.assertFalse(payload["row_advance_detected"])
            self.assertFalse(payload["batch_1_officially_started"])

    def test_partial_row_advance_marks_batch_started_but_not_material(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir, output_dir, metadata_file, helper = self._prepare_pipeline_context(root)

            def executor(command: list[str], cwd: Path) -> dict[str, object]:
                if "phase-a:export-real-data" in command:
                    helper._write_price_csv(data_dir / "AAA.csv", history_rows=64, article_days={2, 6})
                    metadata = pd.read_csv(metadata_file)
                    metadata.loc[metadata["ticker"].astype(str).eq("AAA"), "rows_1d"] = 64
                    metadata.to_csv(metadata_file, index=False)
                    segmentation_path = output_dir / "baseline_v6_universe_segmentation.csv"
                    segmentation = pd.read_csv(segmentation_path)
                    segmentation.loc[segmentation["ticker"].astype(str).eq("AAA"), ["rows", "history_rows"]] = 64
                    segmentation.to_csv(segmentation_path, index=False)
                return {"command": " ".join(command), "returncode": 0, "stdout": "ok", "stderr": "", "combined_output": "ok", "succeeded": True}

            result = run_phase_b_priority_backfill_execution(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
                command_executor=executor,
            )

            payload = result["phase_b_priority_backfill_batch1_status"]
            self.assertEqual("batch_1_started_but_not_material_yet", payload["batch_1_status"])
            self.assertTrue(payload["row_advance_detected"])
            self.assertTrue(payload["batch_1_officially_started"])
            self.assertFalse(payload["batch_1_material_progress_detected"])

    def test_batch_1_complete_is_reported_when_targets_are_reached(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir, output_dir, metadata_file, helper = self._prepare_pipeline_context(root)

            updated_article_days_map = {
                "AAA": {2, 6, 12},
                "BBB": {3, 10, 14},
                "CCC": {4, 11, 15},
                "DDD": {5, 12, 16},
                "EEE": {13, 17, 21},
                "FFF": {8, 18, 22},
            }

            def executor(command: list[str], cwd: Path) -> dict[str, object]:
                if "phase-a:export-real-data" in command:
                    for ticker in ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]:
                        helper._write_price_csv(data_dir / f"{ticker}.csv", history_rows=78, article_days=updated_article_days_map[ticker])
                    metadata = pd.read_csv(metadata_file)
                    metadata["rows_1d"] = 78
                    metadata["sentiment_days_with_articles"] = [len(updated_article_days_map[ticker]) for ticker in metadata["ticker"]]
                    metadata["sentiment_article_count_total"] = metadata["sentiment_days_with_articles"]
                    metadata.to_csv(metadata_file, index=False)
                    segmentation_path = output_dir / "baseline_v6_universe_segmentation.csv"
                    segmentation = pd.read_csv(segmentation_path)
                    segmentation["rows"] = 78
                    segmentation["history_rows"] = 78
                    segmentation["article_count_total"] = [len(updated_article_days_map[ticker]) for ticker in segmentation["ticker"]]
                    segmentation["news_count_total"] = segmentation["article_count_total"]
                    segmentation["article_days"] = segmentation["article_count_total"]
                    segmentation["news_density_pct"] = [round(100.0 * value / 78, 4) for value in segmentation["article_days"]]
                    segmentation.to_csv(segmentation_path, index=False)
                return {"command": " ".join(command), "returncode": 0, "stdout": "ok", "stderr": "", "combined_output": "ok", "succeeded": True}

            result = run_phase_b_priority_backfill_execution(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
                command_executor=executor,
            )

            payload = result["phase_b_priority_backfill_batch1_status"]
            self.assertEqual("batch_1_complete_ready_for_batch_2", payload["batch_1_status"])
            self.assertTrue(payload["batch_1_officially_started"])
            self.assertTrue(payload["batch_1_material_progress_detected"])
            self.assertTrue(payload["usable_oos_windows_advanced"])
            self.assertTrue(payload["primary_article_day_recovery_advanced"])


if __name__ == "__main__":
    unittest.main()
