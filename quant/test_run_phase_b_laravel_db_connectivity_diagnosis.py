"""Tests for Phase B Laravel DB connectivity diagnosis runner."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from quant.run_phase_b_laravel_db_connectivity_diagnosis import (
    run_phase_b_laravel_db_connectivity_diagnosis,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class RunPhaseBLaravelDbConnectivityDiagnosisTestCase(unittest.TestCase):
    def _prepare_fixture(self, root: Path) -> Path:
        output_dir = root / "output"
        output_dir.mkdir()
        _write_json(
            output_dir / "phase_b_priority_backfill_execution.json",
            {
                "batch_1_status": "batch_1_not_started_snapshot_still_static",
                "fetch_command": {
                    "command": "php artisan stocks:fetch-history --days=180",
                    "succeeded": False,
                    "combined_output": "Connection refused",
                },
                "export_command": {
                    "command": "php artisan phase-a:export-real-data --data-dir=data --metadata-file=data/ticker_metadata.csv --include-sentiment-series",
                    "succeeded": False,
                    "combined_output": "Connection refused",
                },
            },
        )
        _write_json(
            output_dir / "phase_b_data_extension_pipeline_root_cause.json",
            {
                "root_cause_class": "mixed_root_cause",
                "highest_blocking_step": "fetch_update_snapshot_stage",
            },
        )
        _write_json(output_dir / "phase_b_data_extension_pipeline_fix_status.json", {"pipeline_bug_confirmed": True})
        _write_json(output_dir / "phase_b_recheck_readiness_status.json", {"recheck_readiness_gate_allowed": False})
        return output_dir

    def test_main_artifacts_are_generated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            output_dir = self._prepare_fixture(root)

            def executor(command: list[str], cwd: Path) -> dict[str, object]:
                command_text = " ".join(command)
                if "artisan env" in command_text:
                    return {"command": command_text, "returncode": 0, "stdout": "INFO The application environment is [local].", "stderr": "", "combined_output": "INFO The application environment is [local].", "succeeded": True}
                if '"pdo_mysql"' in command_text:
                    return {"command": command_text, "returncode": 0, "stdout": '{"pdo_mysql": true, "mysqli": true}', "stderr": "", "combined_output": '{"pdo_mysql": true, "mysqli": true}', "succeeded": True}
                if '"config_cache_exists"' in command_text:
                    return {"command": command_text, "returncode": 0, "stdout": '{"default":"mysql","host":"127.0.0.1","port":"3306","database":"sentimena_dashboard","username":"root","socket":"","config_cache_exists":false}', "stderr": "", "combined_output": '{"default":"mysql","host":"127.0.0.1","port":"3306","database":"sentimena_dashboard","username":"root","socket":"","config_cache_exists":false}', "succeeded": True}
                return {"command": command_text, "returncode": 1, "stdout": '{"ok": false, "class": "Illuminate\\\\Database\\\\QueryException", "message": "SQLSTATE[HY000] [2002] Connection refused"}', "stderr": "", "combined_output": '{"ok": false, "class": "Illuminate\\\\Database\\\\QueryException", "message": "SQLSTATE[HY000] [2002] Connection refused"}', "succeeded": False}

            result = run_phase_b_laravel_db_connectivity_diagnosis(
                data_dir=root / "data",
                output_dir=output_dir,
                metadata_file=root / "data/ticker_metadata.csv",
                command_executor=executor,
            )

            for name in [
                "phase_b_laravel_db_connectivity_diagnosis.json",
                "phase_b_laravel_db_connectivity_diagnosis.txt",
                "phase_b_laravel_db_connectivity_trace.csv",
                "phase_b_laravel_db_fix_status.json",
                "phase_b_backfill_prerequisite_status.json",
            ]:
                self.assertTrue((output_dir / name).exists(), f"Missing artifact: {name}")

            self.assertIn("phase_b_laravel_db_connectivity_diagnosis", result)

    def test_service_down_keeps_connectivity_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            output_dir = self._prepare_fixture(root)

            def executor(command: list[str], cwd: Path) -> dict[str, object]:
                command_text = " ".join(command)
                if "artisan env" in command_text:
                    return {"command": command_text, "returncode": 0, "stdout": "INFO The application environment is [local].", "stderr": "", "combined_output": "INFO The application environment is [local].", "succeeded": True}
                if '"pdo_mysql"' in command_text:
                    return {"command": command_text, "returncode": 0, "stdout": '{"pdo_mysql": true, "mysqli": true}', "stderr": "", "combined_output": '{"pdo_mysql": true, "mysqli": true}', "succeeded": True}
                if '"config_cache_exists"' in command_text:
                    return {"command": command_text, "returncode": 0, "stdout": '{"default":"mysql","host":"127.0.0.1","port":"3306","database":"sentimena_dashboard","username":"root","socket":"","config_cache_exists":false}', "stderr": "", "combined_output": '{"default":"mysql","host":"127.0.0.1","port":"3306","database":"sentimena_dashboard","username":"root","socket":"","config_cache_exists":false}', "succeeded": True}
                return {"command": command_text, "returncode": 1, "stdout": '{"ok": false, "class": "Illuminate\\\\Database\\\\QueryException", "message": "SQLSTATE[HY000] [2002] Connection refused"}', "stderr": "", "combined_output": '{"ok": false, "class": "Illuminate\\\\Database\\\\QueryException", "message": "SQLSTATE[HY000] [2002] Connection refused"}', "succeeded": False}

            result = run_phase_b_laravel_db_connectivity_diagnosis(
                data_dir=root / "data",
                output_dir=output_dir,
                metadata_file=root / "data/ticker_metadata.csv",
                command_executor=executor,
            )
            payload = result["phase_b_laravel_db_connectivity_diagnosis"]
            self.assertFalse(payload["db_connectivity_restored"])
            self.assertEqual("mysql_service_down", payload["root_cause_class"])
            self.assertFalse(payload["mysql_service_reachable"])
            self.assertFalse(payload["backfill_prerequisite_ready"])

    def test_restored_connection_marks_prerequisite_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            output_dir = self._prepare_fixture(root)
            _write_json(
                output_dir / "phase_b_priority_backfill_execution.json",
                {
                    "batch_1_status": "batch_1_not_started_snapshot_still_static",
                    "fetch_command": {"command": "php artisan stocks:fetch-history --days=180", "succeeded": True, "combined_output": "ok"},
                    "export_command": {"command": "php artisan phase-a:export-real-data --data-dir=data --metadata-file=data/ticker_metadata.csv --include-sentiment-series", "succeeded": True, "combined_output": "ok"},
                },
            )

            def executor(command: list[str], cwd: Path) -> dict[str, object]:
                command_text = " ".join(command)
                if "artisan env" in command_text:
                    return {"command": command_text, "returncode": 0, "stdout": "INFO The application environment is [local].", "stderr": "", "combined_output": "INFO The application environment is [local].", "succeeded": True}
                if '"pdo_mysql"' in command_text:
                    return {"command": command_text, "returncode": 0, "stdout": '{"pdo_mysql": true, "mysqli": true}', "stderr": "", "combined_output": '{"pdo_mysql": true, "mysqli": true}', "succeeded": True}
                if '"config_cache_exists"' in command_text:
                    return {"command": command_text, "returncode": 0, "stdout": '{"default":"mysql","host":"127.0.0.1","port":"3306","database":"sentimena_dashboard","username":"root","socket":"","config_cache_exists":false}', "stderr": "", "combined_output": '{"default":"mysql","host":"127.0.0.1","port":"3306","database":"sentimena_dashboard","username":"root","socket":"","config_cache_exists":false}', "succeeded": True}
                return {"command": command_text, "returncode": 0, "stdout": '{"ok": true, "driver": "mysql"}', "stderr": "", "combined_output": '{"ok": true, "driver": "mysql"}', "succeeded": True}

            result = run_phase_b_laravel_db_connectivity_diagnosis(
                data_dir=root / "data",
                output_dir=output_dir,
                metadata_file=root / "data/ticker_metadata.csv",
                command_executor=executor,
            )
            payload = result["phase_b_laravel_db_connectivity_diagnosis"]
            self.assertTrue(payload["db_connectivity_restored"])
            self.assertTrue(payload["mysql_service_reachable"])
            self.assertTrue(payload["credentials_validated"])
            self.assertTrue(payload["artisan_db_access_working"])
            self.assertTrue(payload["backfill_prerequisite_ready"])


if __name__ == "__main__":
    unittest.main()
