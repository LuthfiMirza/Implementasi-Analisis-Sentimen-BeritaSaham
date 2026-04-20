"""Diagnose Laravel MySQL connectivity for Phase B backfill prerequisites."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.phase_a_transition_utils import dedupe, read_json_object, safe_dict  # noqa: E402


DIAGNOSIS_JSON_OUTPUT = "phase_b_laravel_db_connectivity_diagnosis.json"
DIAGNOSIS_TEXT_OUTPUT = "phase_b_laravel_db_connectivity_diagnosis.txt"
TRACE_CSV_OUTPUT = "phase_b_laravel_db_connectivity_trace.csv"
FIX_STATUS_OUTPUT = "phase_b_laravel_db_fix_status.json"
PREREQ_STATUS_OUTPUT = "phase_b_backfill_prerequisite_status.json"

ROOT_CAUSE_CLASSES = {
    "mysql_service_down",
    "host_port_misaligned",
    "credentials_invalid",
    "config_cache_stale",
    "database_missing",
    "php_driver_missing",
    "mixed_root_cause",
}
TRACE_COLUMNS = [
    "check_id",
    "stage",
    "status",
    "expected_state",
    "observed_state",
    "evidence",
]


class PhaseBLaravelDbConnectivityDiagnosisCliError(ValueError):
    """Friendly CLI error for Laravel DB connectivity diagnosis."""


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


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


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
        raise PhaseBLaravelDbConnectivityDiagnosisCliError(
            f"Required artifact missing or invalid: {filename} ({'; '.join(warnings) if warnings else 'unknown'})"
        )
    return safe_dict(payload)


def _parse_env(path: Path) -> Tuple[Dict[str, str], List[str]]:
    warnings: List[str] = []
    env_values: Dict[str, str] = {}
    if not path.exists():
        warnings.append(f".env not found: {path}")
        return env_values, warnings

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env_values[key.strip()] = value.strip().strip('"').strip("'")
    return env_values, warnings


def _default_command_executor(command: Sequence[str], cwd: Path) -> Dict[str, object]:
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


def _build_probe_commands(php_binary: str) -> Dict[str, List[str]]:
    config_probe = (
        'require "vendor/autoload.php"; '
        '$app = require "bootstrap/app.php"; '
        '$app->make(Illuminate\\Contracts\\Console\\Kernel::class)->bootstrap(); '
        'echo json_encode(['
        '"default"=>config("database.default"),'
        '"host"=>config("database.connections.mysql.host"),'
        '"port"=>config("database.connections.mysql.port"),'
        '"database"=>config("database.connections.mysql.database"),'
        '"username"=>config("database.connections.mysql.username"),'
        '"socket"=>config("database.connections.mysql.unix_socket"),'
        '"config_cache_exists"=>file_exists(base_path("bootstrap/cache/config.php"))'
        '], JSON_PRETTY_PRINT);'
    )
    db_probe = (
        'require "vendor/autoload.php"; '
        '$app = require "bootstrap/app.php"; '
        '$app->make(Illuminate\\Contracts\\Console\\Kernel::class)->bootstrap(); '
        'try { DB::connection()->getPdo(); '
        'echo json_encode(["ok"=>true,"driver"=>config("database.default")], JSON_PRETTY_PRINT); '
        '} catch (Throwable $e) { '
        'echo json_encode(["ok"=>false,"class"=>get_class($e),"message"=>$e->getMessage()], JSON_PRETTY_PRINT); '
        'exit(1); }'
    )
    extensions_probe = 'echo json_encode(["pdo_mysql"=>extension_loaded("pdo_mysql"),"mysqli"=>extension_loaded("mysqli")], JSON_PRETTY_PRINT);'
    return {
        "artisan_env": [php_binary, "artisan", "env"],
        "laravel_config_probe": [php_binary, "-r", config_probe],
        "artisan_db_probe": [php_binary, "-r", db_probe],
        "php_extensions_probe": [php_binary, "-r", extensions_probe],
    }


def _decode_json_output(result: Dict[str, object]) -> Dict[str, object]:
    text = _safe_str(result.get("stdout")) or _safe_str(result.get("combined_output"))
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return safe_dict(payload)


def _extract_backfill_attempts(output_dir: Path) -> Dict[str, object]:
    payload = _load_required_json(output_dir, "phase_b_priority_backfill_execution.json")
    return {
        "fetch_command": safe_dict(payload.get("fetch_command")),
        "export_command": safe_dict(payload.get("export_command")),
        "batch_1_status": _safe_str(payload.get("batch_1_status")),
        "recommended_next_action": _safe_str(payload.get("recommended_next_action")),
    }


def _connection_error_class(message: str) -> Tuple[str, bool, bool]:
    text = message.lower()
    if "could not find driver" in text:
        return "php_driver_missing", False, False
    if "connection refused" in text:
        return "mysql_service_down", False, False
    if "operation not permitted" in text:
        return "mysql_service_down", False, False
    if "access denied" in text:
        return "credentials_invalid", True, False
    if "unknown database" in text:
        return "database_missing", True, False
    if "php_network_getaddresses" in text or "name or service not known" in text:
        return "host_port_misaligned", False, False
    if "no such file or directory" in text and "mysql" in text:
        return "host_port_misaligned", False, False
    return "mixed_root_cause", False, False


def run_phase_b_laravel_db_connectivity_diagnosis(
    *,
    data_dir: Path,
    output_dir: Path,
    metadata_file: Optional[Path] = None,
    command_executor=None,
) -> Dict[str, object]:
    del data_dir, metadata_file
    project_root = Path(__file__).resolve().parent.parent
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    priority_backfill = _extract_backfill_attempts(output_dir)
    pipeline_root_cause = _load_required_json(output_dir, "phase_b_data_extension_pipeline_root_cause.json")
    _load_required_json(output_dir, "phase_b_data_extension_pipeline_fix_status.json")
    _load_required_json(output_dir, "phase_b_recheck_readiness_status.json")

    env_values, env_warnings = _parse_env(project_root / ".env")
    php_binary = shutil.which("php")
    if php_binary is None:
        raise PhaseBLaravelDbConnectivityDiagnosisCliError("PHP binary not available; cannot probe Laravel DB connectivity.")

    executor = command_executor or _default_command_executor
    probe_commands = _build_probe_commands(php_binary)
    artisan_env_result = executor(probe_commands["artisan_env"], project_root)
    config_probe_result = executor(probe_commands["laravel_config_probe"], project_root)
    db_probe_result = executor(probe_commands["artisan_db_probe"], project_root)
    ext_probe_result = executor(probe_commands["php_extensions_probe"], project_root)

    laravel_config = _decode_json_output(config_probe_result)
    ext_probe = _decode_json_output(ext_probe_result)
    db_probe = _decode_json_output(db_probe_result)

    env_host = _safe_str(env_values.get("DB_HOST"))
    env_port = _safe_str(env_values.get("DB_PORT"))
    env_database = _safe_str(env_values.get("DB_DATABASE"))
    env_username = _safe_str(env_values.get("DB_USERNAME"))
    env_socket = _safe_str(env_values.get("DB_SOCKET"))

    laravel_env_valid = all([_safe_str(env_values.get("DB_CONNECTION")) == "mysql", env_host, env_port, env_database, env_username])
    resolved_host = _safe_str(laravel_config.get("host"))
    resolved_port = _safe_str(laravel_config.get("port"))
    resolved_database = _safe_str(laravel_config.get("database"))
    resolved_username = _safe_str(laravel_config.get("username"))
    resolved_socket = _safe_str(laravel_config.get("socket"))
    config_cache_exists = _safe_bool(laravel_config.get("config_cache_exists"))
    laravel_config_cache_stale = bool(
        config_cache_exists
        and (
            resolved_host != env_host
            or resolved_port != env_port
            or resolved_database != env_database
            or resolved_username != env_username
            or resolved_socket != env_socket
        )
    )

    pdo_mysql_available = _safe_bool(ext_probe.get("pdo_mysql"))
    mysqli_available = _safe_bool(ext_probe.get("mysqli"))
    db_probe_message = _safe_str(db_probe.get("message")) or _safe_str(db_probe_result.get("combined_output"))
    root_cause_class, mysql_service_reachable, credentials_validated = _connection_error_class(db_probe_message)
    artisan_db_access_working = _safe_bool(db_probe.get("ok")) and _safe_bool(db_probe_result.get("succeeded"))
    if artisan_db_access_working:
        mysql_service_reachable = True
        credentials_validated = True
        root_cause_class = "mixed_root_cause" if laravel_config_cache_stale else "mixed_root_cause"

    if not pdo_mysql_available:
        root_cause_class = "php_driver_missing"
        mysql_service_reachable = False
        credentials_validated = False
    elif laravel_config_cache_stale:
        root_cause_class = "config_cache_stale"
    elif root_cause_class not in ROOT_CAUSE_CLASSES:
        root_cause_class = "mixed_root_cause"

    fetch_result = safe_dict(priority_backfill.get("fetch_command"))
    export_result = safe_dict(priority_backfill.get("export_command"))
    fetch_failed_connection_refused = "connection refused" in _safe_str(fetch_result.get("combined_output")).lower()
    export_failed_connection_refused = "connection refused" in _safe_str(export_result.get("combined_output")).lower()
    if fetch_failed_connection_refused or export_failed_connection_refused:
        mysql_service_reachable = False
        artisan_db_access_working = False
        credentials_validated = False
        if root_cause_class == "mixed_root_cause":
            root_cause_class = "mysql_service_down"

    db_connectivity_restored = bool(artisan_db_access_working and mysql_service_reachable and credentials_validated)
    backfill_prerequisite_ready = bool(
        db_connectivity_restored
        and not laravel_config_cache_stale
        and pdo_mysql_available
    )

    if not pdo_mysql_available:
        highest_blocking_issue = "pdo_mysql_missing"
        recommended_next_action = "enable_php_pdo_mysql_extension_then_rerun_laravel_db_connectivity_diagnosis"
    elif laravel_config_cache_stale:
        highest_blocking_issue = "laravel_config_cache_stale"
        recommended_next_action = "clear_laravel_config_cache_then_verify_db_connection_and_retry_backfill_prerequisites"
    elif not mysql_service_reachable:
        highest_blocking_issue = "mysql_service_unreachable"
        recommended_next_action = "start_or_restore_local_mysql_service_for_sentimena_dashboard_then_rerun_db_connectivity_diagnosis"
    elif not credentials_validated:
        highest_blocking_issue = "mysql_credentials_or_database_invalid"
        recommended_next_action = "correct_db_credentials_or_create_target_database_then_rerun_db_connectivity_diagnosis"
    elif not artisan_db_access_working:
        highest_blocking_issue = "laravel_artisan_db_probe_failed"
        recommended_next_action = "inspect_laravel_database_bootstrap_then_rerun_db_connectivity_diagnosis"
    else:
        highest_blocking_issue = "none"
        recommended_next_action = "rerun_priority_backfill_execution_now_that_db_prerequisite_is_ready"

    db_trace_observed = _safe_str(db_probe_message)
    if not artisan_db_access_working and (fetch_failed_connection_refused or export_failed_connection_refused):
        db_trace_observed = "Operational artisan commands hit MySQL connection refused before backfill/export could start."

    trace_rows = [
        {
            "check_id": "env_file",
            "stage": "configuration",
            "status": "valid" if laravel_env_valid else "invalid",
            "expected_state": "DB env variables resolved for mysql",
            "observed_state": f"connection={_safe_str(env_values.get('DB_CONNECTION'))}, host={env_host}, port={env_port}, database={env_database}, username={env_username}, socket={'set' if env_socket else 'empty'}",
            "evidence": "Parsed from .env without reading password value.",
        },
        {
            "check_id": "laravel_config_resolution",
            "stage": "configuration",
            "status": "stale" if laravel_config_cache_stale else "aligned",
            "expected_state": "Resolved Laravel DB config matches .env",
            "observed_state": f"resolved_host={resolved_host}, resolved_port={resolved_port}, resolved_database={resolved_database}, resolved_username={resolved_username}, config_cache_exists={str(config_cache_exists).lower()}",
            "evidence": "Resolved via Laravel bootstrap, not by raw file parsing.",
        },
        {
            "check_id": "php_mysql_driver",
            "stage": "runtime",
            "status": "available" if pdo_mysql_available else "missing",
            "expected_state": "pdo_mysql available",
            "observed_state": f"pdo_mysql={str(pdo_mysql_available).lower()}, mysqli={str(mysqli_available).lower()}",
            "evidence": "Derived from php extension probe.",
        },
        {
            "check_id": "artisan_db_probe",
            "stage": "database",
            "status": "working" if artisan_db_access_working else "failed",
            "expected_state": "Laravel bootstrap can open PDO connection",
            "observed_state": db_trace_observed[:240],
            "evidence": _safe_str(db_probe.get("class")) or _safe_str(db_probe_result.get("command")),
        },
        {
            "check_id": "priority_backfill_fetch",
            "stage": "backfill",
            "status": "working" if _safe_bool(fetch_result.get("succeeded")) else "failed",
            "expected_state": "stocks:fetch-history can access DB and begin backfill",
            "observed_state": _safe_str(fetch_result.get("combined_output"))[:240],
            "evidence": _safe_str(fetch_result.get("command")),
        },
        {
            "check_id": "priority_backfill_export",
            "stage": "backfill",
            "status": "working" if _safe_bool(export_result.get("succeeded")) else "failed",
            "expected_state": "phase-a:export-real-data can read DB and regenerate snapshot",
            "observed_state": _safe_str(export_result.get("combined_output"))[:240],
            "evidence": _safe_str(export_result.get("command")),
        },
    ]

    diagnosis_payload = {
        "generated_at": _now_iso(),
        "db_connectivity_restored": db_connectivity_restored,
        "root_cause_class": root_cause_class,
        "mysql_service_reachable": mysql_service_reachable,
        "laravel_env_valid": laravel_env_valid,
        "laravel_config_cache_stale": laravel_config_cache_stale,
        "credentials_validated": credentials_validated,
        "artisan_db_access_working": artisan_db_access_working,
        "backfill_prerequisite_ready": backfill_prerequisite_ready,
        "highest_blocking_issue": highest_blocking_issue,
        "recommended_next_action": recommended_next_action,
        "resolved_db_target": {
            "default_connection": _safe_str(laravel_config.get("default")),
            "host": resolved_host,
            "port": resolved_port,
            "database": resolved_database,
            "username": resolved_username,
            "socket_configured": bool(resolved_socket),
        },
        "previous_backfill_status": {
            "batch_1_status": _safe_str(priority_backfill.get("batch_1_status")),
            "fetch_succeeded": _safe_bool(fetch_result.get("succeeded")),
            "export_succeeded": _safe_bool(export_result.get("succeeded")),
        },
        "decisive_statement": (
            "MySQL service tidak reachable, sehingga Laravel artisan tidak bisa memulai backfill."
            if not mysql_service_reachable
            else "Koneksi DB sudah pulih dan prerequisite backfill sekarang siap."
        ),
        "limitations": dedupe(env_warnings),
    }

    fix_status_payload = {
        "generated_at": _now_iso(),
        "local_fix_applied": False,
        "config_issue_fixable_from_repo": bool(laravel_config_cache_stale),
        "driver_issue_fixable_from_repo": False,
        "service_issue_external": not mysql_service_reachable,
        "verification": {
            "artisan_env_command_ok": _safe_bool(artisan_env_result.get("succeeded")),
            "config_probe_ok": bool(laravel_config),
            "artisan_db_probe_ok": artisan_db_access_working,
        },
        "recommended_next_action": recommended_next_action,
    }

    prereq_payload = {
        "generated_at": _now_iso(),
        "db_connectivity_restored": db_connectivity_restored,
        "backfill_prerequisite_ready": backfill_prerequisite_ready,
        "required_before_backfill": [
            "Laravel artisan must complete a direct DB probe without connection error",
            "stocks:fetch-history must be able to read active stocks from the database",
            "phase-a:export-real-data must be able to read stock_prices and rewrite data/*.csv",
        ],
        "recommended_next_action": recommended_next_action,
    }

    _write_json(output_dir / DIAGNOSIS_JSON_OUTPUT, diagnosis_payload)
    _write_json(output_dir / FIX_STATUS_OUTPUT, fix_status_payload)
    _write_json(output_dir / PREREQ_STATUS_OUTPUT, prereq_payload)
    _write_csv(output_dir / TRACE_CSV_OUTPUT, TRACE_COLUMNS, trace_rows)

    text_lines = [
        f"DB connectivity restored: {str(db_connectivity_restored).lower()}",
        f"Root cause class: {root_cause_class}",
        f"MySQL service reachable: {str(mysql_service_reachable).lower()}",
        f"Laravel env valid: {str(laravel_env_valid).lower()}",
        f"Laravel config cache stale: {str(laravel_config_cache_stale).lower()}",
        f"Credentials validated: {str(credentials_validated).lower()}",
        f"Artisan DB access working: {str(artisan_db_access_working).lower()}",
        f"Backfill prerequisite ready: {str(backfill_prerequisite_ready).lower()}",
        f"Highest blocking issue: {highest_blocking_issue}",
        f"Recommended next action: {recommended_next_action}",
    ]
    _write_text(output_dir / DIAGNOSIS_TEXT_OUTPUT, text_lines)

    return {
        "phase_b_laravel_db_connectivity_diagnosis": diagnosis_payload,
        "phase_b_laravel_db_fix_status": fix_status_payload,
        "phase_b_backfill_prerequisite_status": prereq_payload,
        "phase_b_laravel_db_connectivity_trace": trace_rows,
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
        run_phase_b_laravel_db_connectivity_diagnosis(
            data_dir=Path(args.data_dir),
            output_dir=Path(args.output_dir),
            metadata_file=Path(args.metadata_file) if args.metadata_file else None,
        )
    except PhaseBLaravelDbConnectivityDiagnosisCliError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
