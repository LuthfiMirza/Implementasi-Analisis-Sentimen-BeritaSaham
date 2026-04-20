"""Tests for Phase B XAMPP/MySQL recovery runner."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from quant.run_phase_b_mysql_xampp_recovery import run_phase_b_mysql_xampp_recovery


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class RunPhaseBMySqlXamppRecoveryTestCase(unittest.TestCase):
    def _prepare_fixture(self, root: Path) -> Path:
        output_dir = root / "output"
        output_dir.mkdir()
        _write_json(
            output_dir / "phase_b_laravel_db_connectivity_diagnosis.json",
            {
                "db_connectivity_restored": False,
                "root_cause_class": "mysql_service_down",
            },
        )
        _write_json(output_dir / "phase_b_laravel_db_fix_status.json", {"service_issue_external": True})
        _write_json(output_dir / "phase_b_backfill_prerequisite_status.json", {"backfill_prerequisite_ready": False})
        return output_dir

    def test_main_artifacts_are_generated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            output_dir = self._prepare_fixture(root)

            def fake_run(command, cwd):
                text = " ".join(command)
                if "xampp status" in text:
                    return {"command": text, "returncode": 0, "stdout": "MySQL is not running.", "stderr": "", "combined_output": "MySQL is not running.", "succeeded": True}
                if "mysql.server status" in text:
                    return {"command": text, "returncode": 1, "stdout": "ERROR! MariaDB is not running", "stderr": "", "combined_output": "ERROR! MariaDB is not running", "succeeded": False}
                if "lsof" in text:
                    return {"command": text, "returncode": 1, "stdout": "", "stderr": "", "combined_output": "", "succeeded": False}
                if '"config_cache_exists"' in text:
                    return {"command": text, "returncode": 0, "stdout": '{"host":"127.0.0.1","port":"3306","database":"sentimena_dashboard","username":"root","socket":""}', "stderr": "", "combined_output": '{"host":"127.0.0.1","port":"3306","database":"sentimena_dashboard","username":"root","socket":""}', "succeeded": True}
                if 'DB::select' in text:
                    return {"command": text, "returncode": 1, "stdout": '{"ok": false, "message": "Connection refused"}', "stderr": "", "combined_output": '{"ok": false, "message": "Connection refused"}', "succeeded": False}
                if "curl -I" in text:
                    return {"command": text, "returncode": 7, "stdout": "", "stderr": "", "combined_output": "curl: (7) Failed to connect", "succeeded": False}
                if "mysqladmin ping" in text or "SHOW DATABASES" in text:
                    return {"command": text, "returncode": 1, "stdout": "", "stderr": "", "combined_output": "mysql port not listening", "succeeded": False}
                if "startmysql" in text:
                    return {"command": text, "returncode": 2, "stdout": "You need to be root to perform this action.", "stderr": "", "combined_output": "You need to be root to perform this action.", "succeeded": False}
                return {"command": text, "returncode": 0, "stdout": "", "stderr": "", "combined_output": "", "succeeded": True}

            import quant.run_phase_b_mysql_xampp_recovery as module

            original = module._run
            module._run = fake_run
            try:
                result = run_phase_b_mysql_xampp_recovery(
                    data_dir=root / "data",
                    output_dir=output_dir,
                    metadata_file=root / "data/ticker_metadata.csv",
                )
            finally:
                module._run = original

            for name in [
                "phase_b_mysql_xampp_recovery.json",
                "phase_b_mysql_xampp_recovery.txt",
                "phase_b_mysql_xampp_recovery_trace.csv",
                "phase_b_mysql_xampp_recovery_fix_status.json",
                "phase_b_dashboard_db_readiness.json",
            ]:
                self.assertTrue((output_dir / name).exists(), f"Missing artifact: {name}")

            self.assertIn("phase_b_mysql_xampp_recovery", result)

    def test_service_down_keeps_restored_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            output_dir = self._prepare_fixture(root)

            def fake_run(command, cwd):
                text = " ".join(command)
                if "xampp status" in text:
                    return {"command": text, "returncode": 0, "stdout": "MySQL is not running.", "stderr": "", "combined_output": "MySQL is not running.", "succeeded": True}
                if "mysql.server status" in text:
                    return {"command": text, "returncode": 1, "stdout": "ERROR! MariaDB is not running", "stderr": "", "combined_output": "ERROR! MariaDB is not running", "succeeded": False}
                if "lsof" in text:
                    return {"command": text, "returncode": 1, "stdout": "", "stderr": "", "combined_output": "", "succeeded": False}
                if '"config_cache_exists"' in text:
                    return {"command": text, "returncode": 0, "stdout": '{"host":"127.0.0.1","port":"3306","database":"sentimena_dashboard","username":"root","socket":""}', "stderr": "", "combined_output": '{"host":"127.0.0.1","port":"3306","database":"sentimena_dashboard","username":"root","socket":""}', "succeeded": True}
                if 'DB::select' in text:
                    return {"command": text, "returncode": 1, "stdout": '{"ok": false, "message": "Connection refused"}', "stderr": "", "combined_output": '{"ok": false, "message": "Connection refused"}', "succeeded": False}
                if "curl -I" in text:
                    return {"command": text, "returncode": 7, "stdout": "", "stderr": "", "combined_output": "curl: (7) Failed to connect", "succeeded": False}
                if "mysqladmin ping" in text or "SHOW DATABASES" in text:
                    return {"command": text, "returncode": 1, "stdout": "", "stderr": "", "combined_output": "mysql port not listening", "succeeded": False}
                if "startmysql" in text:
                    return {"command": text, "returncode": 2, "stdout": "You need to be root to perform this action.", "stderr": "", "combined_output": "You need to be root to perform this action.", "succeeded": False}
                return {"command": text, "returncode": 0, "stdout": "", "stderr": "", "combined_output": "", "succeeded": True}

            import quant.run_phase_b_mysql_xampp_recovery as module

            original = module._run
            module._run = fake_run
            try:
                result = run_phase_b_mysql_xampp_recovery(
                    data_dir=root / "data",
                    output_dir=output_dir,
                    metadata_file=root / "data/ticker_metadata.csv",
                )
            finally:
                module._run = original

            payload = result["phase_b_mysql_xampp_recovery"]
            self.assertFalse(payload["db_connectivity_restored"])
            self.assertFalse(payload["xampp_mysql_running"])
            self.assertEqual("xampp_mysql_not_running", payload["highest_blocking_issue"])

    def test_service_up_and_query_working_marks_restored_true(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            output_dir = self._prepare_fixture(root)

            def fake_run(command, cwd):
                text = " ".join(command)
                if "xampp status" in text or "mysql.server status" in text:
                    return {"command": text, "returncode": 0, "stdout": "MySQL is running.", "stderr": "", "combined_output": "MySQL is running.", "succeeded": True}
                if "lsof" in text:
                    return {"command": text, "returncode": 0, "stdout": "mysqld 123 root 10u IPv4 0x 0t0 TCP 127.0.0.1:3306 (LISTEN)", "stderr": "", "combined_output": "mysqld ... 127.0.0.1:3306 (LISTEN)", "succeeded": True}
                if '"config_cache_exists"' in text:
                    return {"command": text, "returncode": 0, "stdout": '{"host":"127.0.0.1","port":"3306","database":"sentimena_dashboard","username":"root","socket":""}', "stderr": "", "combined_output": '{"host":"127.0.0.1","port":"3306","database":"sentimena_dashboard","username":"root","socket":""}', "succeeded": True}
                if 'DB::select' in text:
                    return {"command": text, "returncode": 0, "stdout": '{"ok": true}', "stderr": "", "combined_output": '{"ok": true}', "succeeded": True}
                if "curl -I" in text:
                    return {"command": text, "returncode": 0, "stdout": "HTTP/1.1 302 Found", "stderr": "", "combined_output": "HTTP/1.1 302 Found", "succeeded": True}
                if "mysqladmin ping" in text:
                    return {"command": text, "returncode": 0, "stdout": "mysqld is alive", "stderr": "", "combined_output": "mysqld is alive", "succeeded": True}
                if "SHOW DATABASES" in text:
                    return {"command": text, "returncode": 0, "stdout": "sentimena_dashboard\n", "stderr": "", "combined_output": "sentimena_dashboard", "succeeded": True}
                return {"command": text, "returncode": 0, "stdout": "", "stderr": "", "combined_output": "", "succeeded": True}

            import quant.run_phase_b_mysql_xampp_recovery as module

            original = module._run
            module._run = fake_run
            try:
                result = run_phase_b_mysql_xampp_recovery(
                    data_dir=root / "data",
                    output_dir=output_dir,
                    metadata_file=root / "data/ticker_metadata.csv",
                )
            finally:
                module._run = original

            payload = result["phase_b_mysql_xampp_recovery"]
            self.assertTrue(payload["db_connectivity_restored"])
            self.assertTrue(payload["xampp_mysql_running"])
            self.assertTrue(payload["mysql_port_3306_listening"])
            self.assertTrue(payload["database_sentimena_dashboard_exists"])
            self.assertTrue(payload["laravel_can_query_db"])


if __name__ == "__main__":
    unittest.main()
