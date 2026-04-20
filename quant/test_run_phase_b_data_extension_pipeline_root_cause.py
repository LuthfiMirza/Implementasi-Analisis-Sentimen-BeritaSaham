"""Tests for Phase B data-extension pipeline root-cause runner."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from quant.run_phase_b_data_extension_ingest_audit import run_phase_b_data_extension_ingest_audit
from quant.run_phase_b_data_extension_ingest_rejection_analysis import (
    run_phase_b_data_extension_ingest_rejection_analysis,
)
from quant.run_phase_b_data_extension_pipeline_root_cause import (
    run_phase_b_data_extension_pipeline_root_cause,
)
from quant.test_run_phase_b_data_extension_ingest_audit import (
    RunPhaseBDataExtensionIngestAuditTestCase,
)


def _write_text(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class RunPhaseBDataExtensionPipelineRootCauseTestCase(unittest.TestCase):
    def _prepare_with_rejection_analysis(
        self,
        root: Path,
        *,
        scenario: str = "baseline",
        include_metadata: bool = True,
    ) -> tuple[Path, Path, Path]:
        helper = RunPhaseBDataExtensionIngestAuditTestCase()
        data_dir, output_dir, metadata_file = helper._prepare_fixture(root=root, scenario=scenario, include_metadata=include_metadata)
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
        return data_dir, output_dir, metadata_file

    def _mock_code_paths(self, root: Path, *, fixed_fetch: bool) -> dict[str, Path]:
        fetch_content = """<?php
class FetchStockHistoryCommand {
    protected $signature = 'stocks:fetch-history {--days=90 : Jumlah hari historis yang diinginkan untuk backfill harga 1D}';
    protected function resolveYahooRange(int $days): string {
        %s
    }
}
""" % (
            "// Fix history-range cap so requests above 90 days can actually extend beyond the old 3mo window.\n        if ($days <= 180) { return '6mo'; }\n        if ($days <= 365) { return '1y'; }\n        if ($days <= 730) { return '2y'; }\n        return 'max';"
            if fixed_fetch
            else "return $days >= 90 ? '3mo' : ($days >= 60 ? '2mo' : '1mo');"
        )
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

    def test_main_artifacts_are_generated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir, output_dir, metadata_file = self._prepare_with_rejection_analysis(root)
            result = run_phase_b_data_extension_pipeline_root_cause(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
                **self._mock_code_paths(root, fixed_fetch=True),
            )

            for name in [
                "phase_b_data_extension_pipeline_root_cause.json",
                "phase_b_data_extension_pipeline_root_cause.txt",
                "phase_b_data_extension_pipeline_trace.csv",
                "phase_b_data_extension_pipeline_fix_status.json",
                "phase_b_next_ingest_requirements.json",
            ]:
                self.assertTrue((output_dir / name).exists(), f"Missing artifact: {name}")

            self.assertIn("phase_b_data_extension_pipeline_root_cause", result)

    def test_root_cause_is_mixed_when_snapshot_static_and_fetch_path_is_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir, output_dir, metadata_file = self._prepare_with_rejection_analysis(root)
            result = run_phase_b_data_extension_pipeline_root_cause(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
                **self._mock_code_paths(root, fixed_fetch=False),
            )
            payload = result["phase_b_data_extension_pipeline_root_cause"]
            self.assertEqual("mixed_root_cause", payload["root_cause_class"])
            self.assertTrue(payload["config_misalignment_confirmed"])
            self.assertFalse(payload["snapshot_advanced_confirmed"])
            self.assertEqual("fetch_update_snapshot_stage", payload["highest_blocking_step"])

    def test_fix_status_changes_when_extended_range_support_is_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir, output_dir, metadata_file = self._prepare_with_rejection_analysis(root)

            buggy = run_phase_b_data_extension_pipeline_root_cause(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
                **self._mock_code_paths(root / "buggy", fixed_fetch=False),
            )
            fixed = run_phase_b_data_extension_pipeline_root_cause(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
                **self._mock_code_paths(root / "fixed", fixed_fetch=True),
            )

            buggy_fix = buggy["phase_b_data_extension_pipeline_fix_status"]
            fixed_fix = fixed["phase_b_data_extension_pipeline_fix_status"]
            self.assertFalse(buggy_fix["local_code_fix_applied"])
            self.assertTrue(fixed_fix["local_code_fix_applied"])
            self.assertTrue(fixed_fix["extended_range_support_detected"])

    def test_script_runs_with_limited_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir, output_dir, metadata_file = self._prepare_with_rejection_analysis(root, include_metadata=False)
            result = run_phase_b_data_extension_pipeline_root_cause(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
                **self._mock_code_paths(root, fixed_fetch=True),
            )
            self.assertTrue((output_dir / "phase_b_data_extension_pipeline_trace.csv").exists())
            self.assertIn(
                result["phase_b_data_extension_pipeline_root_cause"]["root_cause_class"],
                {"mixed_root_cause", "pipeline_config_misaligned", "source_data_not_extended_yet", "pipeline_bug_confirmed", "ingest_completed_but_snapshot_not_advanced"},
            )


if __name__ == "__main__":
    unittest.main()
