"""Diagnose and attempt minimal XAMPP/MySQL recovery for Laravel Phase B backfill prerequisites."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.phase_a_transition_utils import dedupe, read_json_object, safe_dict  # noqa: E402


RECOVERY_JSON_OUTPUT = "phase_b_mysql_xampp_recovery.json"
RECOVERY_TEXT_OUTPUT = "phase_b_mysql_xampp_recovery.txt"
RECOVERY_TRACE_OUTPUT = "phase_b_mysql_xampp_recovery_trace.csv"
RECOVERY_FIX_STATUS_OUTPUT = "phase_b_mysql_xampp_recovery_fix_status.json"
DASHBOARD_READINESS_OUTPUT = "phase_b_dashboard_db_readiness.json"

TRACE_COLUMNS = [
    "check_id",
    "stage",
    "status",
    "expected_state",
    "observed_state",
    "evidence",
]


class PhaseBMySqlXamppRecoveryCliError(ValueError):
    """Friendly CLI error for XAMPP/MySQL recovery diagnosis."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_str(value: object, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _safe_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _write_text(path: Path, lines: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Sequence[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _load_required_json(output_dir: Path, filename: str) -> Dict[str, object]:
    payload, warnings = read_json_object(Path(output_dir) / filename, filename)
    if payload is None:
        raise PhaseBMySqlXamppRecoveryCliError(
            f"Required artifact missing or invalid: {filename} ({'; '.join(warnings) if warnings else 'unknown'})"
        )
    return safe_dict(payload)


def _parse_env(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    values: Dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _run(command: Sequence[str], cwd: Path) -> Dict[str, object]:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    combined = "\n".join(
        part.strip()
        for part in [completed.stdout, completed.stderr]
        if part and part.strip()
    ).strip()
    return {
        "command": " ".join(command),
        "returncode": int(completed.returncode),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "combined_output": combined,
        "succeeded": completed.returncode == 0,
    }


def _decode_json(result: Dict[str, object]) -> Dict[str, object]:
    text = _safe_str(result.get("stdout")) or _safe_str(result.get("combined_output"))
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return safe_dict(payload)


def run_phase_b_mysql_xampp_recovery(
    *,
    data_dir: Path,
    output_dir: Path,
    metadata_file: Optional[Path] = None,
) -> Dict[str, object]:
    del data_dir, metadata_file
    project_root = Path(__file__).resolve().parent.parent
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    _load_required_json(output_dir, "phase_b_laravel_db_connectivity_diagnosis.json")
    _load_required_json(output_dir, "phase_b_laravel_db_fix_status.json")
    _load_required_json(output_dir, "phase_b_backfill_prerequisite_status.json")

    env_values = _parse_env(project_root / ".env")
    php_binary = shutil.which("php")
    if php_binary is None:
        raise PhaseBMySqlXamppRecoveryCliError("PHP binary not available.")

    xampp_binary = "/Applications/XAMPP/xamppfiles/xampp"
    mysql_server = "/Applications/XAMPP/xamppfiles/bin/mysql.server"
    mysql_binary = "/Applications/XAMPP/xamppfiles/bin/mysql"

    config_probe_cmd = [
        php_binary,
        "-r",
        (
            'require "vendor/autoload.php"; '
            '$app = require "bootstrap/app.php"; '
            '$app->make(Illuminate\\Contracts\\Console\\Kernel::class)->bootstrap(); '
            'echo json_encode(["default"=>config("database.default"),"host"=>config("database.connections.mysql.host"),"port"=>config("database.connections.mysql.port"),"database"=>config("database.connections.mysql.database"),"username"=>config("database.connections.mysql.username"),"socket"=>config("database.connections.mysql.unix_socket"),"config_cache_exists"=>file_exists(base_path("bootstrap/cache/config.php"))], JSON_PRETTY_PRINT);'
        ),
    ]
    db_probe_cmd = [
        php_binary,
        "-r",
        (
            'require "vendor/autoload.php"; '
            '$app = require "bootstrap/app.php"; '
            '$app->make(Illuminate\\Contracts\\Console\\Kernel::class)->bootstrap(); '
            'try { DB::select("select 1 as ok"); echo json_encode(["ok"=>true], JSON_PRETTY_PRINT); } '
            'catch (Throwable $e) { echo json_encode(["ok"=>false,"class"=>get_class($e),"message"=>$e->getMessage()], JSON_PRETTY_PRINT); exit(1); }'
        ),
    ]
    dashboard_probe_cmd = ["curl", "-I", "-sS", "http://127.0.0.1:8000/dashboard"]
    xampp_status_cmd = [xampp_binary, "status"]
    mysql_server_status_cmd = [mysql_server, "status"]
    port_probe_cmd = ["lsof", "-nP", "-iTCP:3306", "-sTCP:LISTEN"]
    mysql_ping_cmd = ["/Applications/XAMPP/xamppfiles/bin/mysqladmin", "ping", "-h", "127.0.0.1", "-P", "3306", "-u", _safe_str(env_values.get("DB_USERNAME"), "root")]
    if _safe_str(env_values.get("DB_PASSWORD")):
        mysql_ping_cmd.append(f"-p{_safe_str(env_values.get('DB_PASSWORD'))}")
    list_db_cmd = [mysql_binary, "-h", "127.0.0.1", "-P", "3306", "-u", _safe_str(env_values.get("DB_USERNAME"), "root"), "-N", "-e", "SHOW DATABASES LIKE 'sentimena_dashboard';"]
    if _safe_str(env_values.get("DB_PASSWORD")):
        list_db_cmd.insert(-2, f"-p{_safe_str(env_values.get('DB_PASSWORD'))}")
    start_mysql_cmd = [xampp_binary, "startmysql"]

    xampp_status = _run(xampp_status_cmd, project_root)
    mysql_server_status = _run(mysql_server_status_cmd, project_root)
    port_probe = _run(port_probe_cmd, project_root)
    config_probe = _run(config_probe_cmd, project_root)
    db_probe = _run(db_probe_cmd, project_root)
    dashboard_probe = _run(dashboard_probe_cmd, project_root)

    xampp_mysql_running_reported = "mysql is running" in _safe_str(xampp_status.get("combined_output")).lower()
    mysql_port_3306_listening = _safe_bool(port_probe.get("succeeded")) and bool(_safe_str(port_probe.get("combined_output")))

    start_attempt = None
    if not xampp_mysql_running_reported:
        start_attempt = _run(start_mysql_cmd, project_root)
        xampp_status_after = _run(xampp_status_cmd, project_root)
        mysql_server_status_after = _run(mysql_server_status_cmd, project_root)
        port_probe_after = _run(port_probe_cmd, project_root)
        xampp_mysql_running_reported = "mysql is running" in _safe_str(xampp_status_after.get("combined_output")).lower()
        mysql_port_3306_listening = _safe_bool(port_probe_after.get("succeeded")) and bool(_safe_str(port_probe_after.get("combined_output")))
    else:
        xampp_status_after = xampp_status
        mysql_server_status_after = mysql_server_status
        port_probe_after = port_probe

    mysql_ping = _run(mysql_ping_cmd, project_root)

    config_payload = _decode_json(config_probe)
    db_probe_payload = _decode_json(db_probe)
    mysql_endpoint_alive = _safe_bool(mysql_ping.get("succeeded")) or "alive" in _safe_str(mysql_ping.get("combined_output")).lower()
    laravel_can_query_db = _safe_bool(db_probe_payload.get("ok")) and _safe_bool(db_probe.get("succeeded"))
    mysql_port_3306_listening = bool(mysql_port_3306_listening or mysql_endpoint_alive or laravel_can_query_db)
    list_db = _run(list_db_cmd, project_root) if mysql_port_3306_listening else {
        "command": " ".join(list_db_cmd),
        "returncode": 1,
        "stdout": "",
        "stderr": "",
        "combined_output": "mysql port not listening",
        "succeeded": False,
    }
    database_sentimena_dashboard_exists = bool(
        _safe_str(list_db.get("stdout")).strip() == "sentimena_dashboard"
        or (laravel_can_query_db and _safe_str(config_payload.get("database")) == "sentimena_dashboard")
    )
    dashboard_db_ready = False
    if _safe_bool(dashboard_probe.get("succeeded")):
        header_text = _safe_str(dashboard_probe.get("combined_output")).lower()
        dashboard_db_ready = "500" not in header_text and "failed to connect" not in header_text
    xampp_mysql_running = bool(xampp_mysql_running_reported or mysql_endpoint_alive or laravel_can_query_db)
    xampp_status_stale = bool(not xampp_mysql_running_reported and (mysql_endpoint_alive or laravel_can_query_db))
    db_connectivity_restored = bool(xampp_mysql_running and mysql_port_3306_listening and laravel_can_query_db and database_sentimena_dashboard_exists)

    if not xampp_mysql_running:
        highest_blocking_issue = "xampp_mysql_not_running"
        recommended_next_action = "start_xampp_mysql_as_root_or_via_xampp_manager_then_rerun_recovery_diagnosis"
    elif not mysql_port_3306_listening:
        highest_blocking_issue = "mysql_port_not_listening"
        recommended_next_action = "fix_mariadb_listener_on_port_3306_then_rerun_recovery_diagnosis"
    elif not database_sentimena_dashboard_exists:
        highest_blocking_issue = "database_missing"
        recommended_next_action = "create_or_restore_sentimena_dashboard_database_then_rerun_recovery_diagnosis"
    elif not laravel_can_query_db:
        highest_blocking_issue = "laravel_db_query_failed"
        recommended_next_action = "resolve_laravel_db_query_failure_then_rerun_recovery_diagnosis"
    elif not dashboard_db_ready:
        highest_blocking_issue = "dashboard_db_dependency_failed"
        recommended_next_action = "verify_dashboard_runtime_after_db_recovery_and_fix_remaining_http_runtime_issue"
    else:
        highest_blocking_issue = "none"
        recommended_next_action = "db_ready_for_backfill_but_keep_retest_gate_closed_until_backfill_progress_is_verified"

    recovery_payload = {
        "generated_at": _now_iso(),
        "xampp_mysql_running": xampp_mysql_running,
        "mysql_port_3306_listening": mysql_port_3306_listening,
        "database_sentimena_dashboard_exists": database_sentimena_dashboard_exists,
        "laravel_can_query_db": laravel_can_query_db,
        "dashboard_db_ready": dashboard_db_ready,
        "db_connectivity_restored": db_connectivity_restored,
        "highest_blocking_issue": highest_blocking_issue,
        "recommended_next_action": recommended_next_action,
        "service_status": {
            "xampp_status_reported_running": xampp_mysql_running_reported,
            "xampp_status_stale": xampp_status_stale,
            "mysql_endpoint_alive": mysql_endpoint_alive,
            "xampp_status_before": _safe_str(xampp_status.get("combined_output")),
            "xampp_status_after": _safe_str(xampp_status_after.get("combined_output")),
            "mysql_server_status_before": _safe_str(mysql_server_status.get("combined_output")),
            "mysql_server_status_after": _safe_str(mysql_server_status_after.get("combined_output")),
            "start_attempt": safe_dict(start_attempt) if isinstance(start_attempt, dict) else None,
        },
        "resolved_db_target": {
            "host": _safe_str(config_payload.get("host")),
            "port": _safe_str(config_payload.get("port")),
            "database": _safe_str(config_payload.get("database")),
            "username": _safe_str(config_payload.get("username")),
            "socket": _safe_str(config_payload.get("socket")),
        },
        "decisive_statement": (
            "XAMPP MySQL belum running, sehingga Laravel dashboard dan artisan sama-sama gagal mengakses DB."
            if not db_connectivity_restored
            else "Laravel sudah bisa query DB dan dashboard readiness sekarang pulih."
        ),
    }

    fix_status_payload = {
        "generated_at": _now_iso(),
        "recovery_attempted": True,
        "start_command_executed": safe_dict(start_attempt) if isinstance(start_attempt, dict) else None,
        "manual_root_required": bool(start_attempt and "need to be root" in _safe_str(start_attempt.get("combined_output")).lower()),
        "external_operational_blocker_still_active": not db_connectivity_restored,
        "xampp_status_stale": xampp_status_stale,
        "recommended_next_action": recommended_next_action,
    }

    dashboard_readiness_payload = {
        "generated_at": _now_iso(),
        "laravel_can_query_db": laravel_can_query_db,
        "dashboard_db_ready": dashboard_db_ready,
        "db_connectivity_restored": db_connectivity_restored,
        "highest_blocking_issue": highest_blocking_issue,
        "recommended_next_action": recommended_next_action,
    }

    trace_rows = [
        {
            "check_id": "xampp_status",
            "stage": "service",
            "status": "running" if xampp_mysql_running else "not_running",
            "expected_state": "XAMPP MySQL running",
            "observed_state": _safe_str(xampp_status_after.get("combined_output"))[:240],
            "evidence": _safe_str(xampp_status_after.get("command")),
        },
        {
            "check_id": "port_3306",
            "stage": "service",
            "status": "listening" if mysql_port_3306_listening else "not_listening",
            "expected_state": "Port 3306 has a listening MySQL process",
            "observed_state": (_safe_str(port_probe_after.get("combined_output")) or _safe_str(mysql_ping.get("combined_output")))[:240],
            "evidence": _safe_str(port_probe_after.get("command")) or _safe_str(mysql_ping.get("command")),
        },
        {
            "check_id": "database_presence",
            "stage": "database",
            "status": "present" if database_sentimena_dashboard_exists else "missing_or_unreachable",
            "expected_state": "sentimena_dashboard exists",
            "observed_state": _safe_str(list_db.get("combined_output"))[:240],
            "evidence": _safe_str(list_db.get("command")),
        },
        {
            "check_id": "laravel_db_probe",
            "stage": "laravel",
            "status": "working" if laravel_can_query_db else "failed",
            "expected_state": "Laravel artisan can run DB query",
            "observed_state": _safe_str(db_probe.get("combined_output"))[:240],
            "evidence": _safe_str(db_probe.get("command")),
        },
        {
            "check_id": "dashboard_probe",
            "stage": "http",
            "status": "ready" if dashboard_db_ready else "failed",
            "expected_state": "Dashboard responds without DB runtime failure",
            "observed_state": _safe_str(dashboard_probe.get("combined_output"))[:240],
            "evidence": _safe_str(dashboard_probe.get("command")),
        },
    ]

    _write_json(output_dir / RECOVERY_JSON_OUTPUT, recovery_payload)
    _write_json(output_dir / RECOVERY_FIX_STATUS_OUTPUT, fix_status_payload)
    _write_json(output_dir / DASHBOARD_READINESS_OUTPUT, dashboard_readiness_payload)
    _write_csv(output_dir / RECOVERY_TRACE_OUTPUT, TRACE_COLUMNS, trace_rows)

    text_lines = [
        f"XAMPP MySQL running: {str(xampp_mysql_running).lower()}",
        f"MySQL port 3306 listening: {str(mysql_port_3306_listening).lower()}",
        f"Database sentimena_dashboard exists: {str(database_sentimena_dashboard_exists).lower()}",
        f"Laravel can query DB: {str(laravel_can_query_db).lower()}",
        f"Dashboard DB ready: {str(dashboard_db_ready).lower()}",
        f"DB connectivity restored: {str(db_connectivity_restored).lower()}",
        f"Highest blocking issue: {highest_blocking_issue}",
        f"Recommended next action: {recommended_next_action}",
    ]
    _write_text(output_dir / RECOVERY_TEXT_OUTPUT, text_lines)

    return {
        "phase_b_mysql_xampp_recovery": recovery_payload,
        "phase_b_mysql_xampp_recovery_fix_status": fix_status_payload,
        "phase_b_dashboard_db_readiness": dashboard_readiness_payload,
        "phase_b_mysql_xampp_recovery_trace": trace_rows,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data", help="Unused compatibility argument.")
    parser.add_argument("--output-dir", default="output", help="Directory containing Phase B artifacts.")
    parser.add_argument("--metadata-file", default="data/ticker_metadata.csv", help="Unused compatibility argument.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        run_phase_b_mysql_xampp_recovery(
            data_dir=Path(args.data_dir),
            output_dir=Path(args.output_dir),
            metadata_file=Path(args.metadata_file) if args.metadata_file else None,
        )
    except PhaseBMySqlXamppRecoveryCliError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
