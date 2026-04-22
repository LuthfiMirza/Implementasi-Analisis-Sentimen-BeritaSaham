"""Execute priority backfill and verify whether Phase B batch-1 has started moving materially."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import pandas as pd

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.phase_a_transition_utils import dedupe, read_json_object, safe_dict  # noqa: E402
from quant.run_phase_b_data_extension_execution_plan import _usable_oos_windows  # noqa: E402
from quant.run_phase_b_data_extension_ingest_audit import run_phase_b_data_extension_ingest_audit  # noqa: E402
from quant.run_phase_b_data_extension_ingest_rejection_analysis import (  # noqa: E402
    run_phase_b_data_extension_ingest_rejection_analysis,
)
from quant.run_phase_b_data_extension_progress_update import run_phase_b_data_extension_progress_update  # noqa: E402


BACKFILL_EXECUTION_JSON_OUTPUT = "phase_b_priority_backfill_execution.json"
BACKFILL_EXECUTION_TEXT_OUTPUT = "phase_b_priority_backfill_execution.txt"
ROW_ADVANCE_CSV_OUTPUT = "phase_b_priority_backfill_row_advance.csv"
BATCH_STATUS_JSON_OUTPUT = "phase_b_priority_backfill_batch1_status.json"
NEXT_STEPS_JSON_OUTPUT = "phase_b_priority_backfill_next_steps.json"

BATCH_1_STATUSES = {
    "batch_1_not_started_snapshot_still_static",
    "batch_1_started_but_not_material_yet",
    "batch_1_material_progress_detected",
    "batch_1_priority_targets_closed_but_progress_gate_pending",
    "batch_1_operationally_complete_ready_for_batch_2",
}
ROW_ADVANCE_COLUMNS = [
    "ticker",
    "rows_before",
    "rows_after",
    "rows_delta",
    "new_unique_dates_count",
    "non_duplicate_row_advance_detected",
    "date_end_before",
    "date_end_after",
    "date_end_advanced",
    "usable_oos_windows_before",
    "usable_oos_windows_after",
    "usable_oos_windows_delta",
    "article_days_before",
    "article_days_after",
    "article_days_delta",
    "news_count_total_before",
    "news_count_total_after",
    "news_count_total_delta",
    "ticker_status",
]


class PhaseBPriorityBackfillExecutionCliError(ValueError):
    """Friendly CLI error for priority backfill execution."""


CommandExecutor = Callable[[Sequence[str], Path], Dict[str, object]]


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


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


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
        raise PhaseBPriorityBackfillExecutionCliError(
            f"Required artifact missing or invalid: {filename} ({'; '.join(warnings) if warnings else 'unknown'})"
        )
    return safe_dict(payload)


def _load_optional_json(output_dir: Path, filename: str) -> Tuple[Dict[str, object], List[str], bool]:
    payload, warnings = read_json_object(Path(output_dir) / filename, filename)
    return safe_dict(payload), list(warnings), payload is not None


def _load_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except Exception as exc:
        raise PhaseBPriorityBackfillExecutionCliError(f"Failed to read {path}: {exc}") from exc


def _load_methodology(output_dir: Path) -> Dict[str, int]:
    payload, _, _ = _load_optional_json(output_dir, "baseline_v9_segment_oos_summary.json")
    methodology = safe_dict(payload.get("methodology"))
    return {
        "warmup_bars": max(1, _safe_int(methodology.get("warmup_bars"), 21)),
        "fold_size_bars": max(1, _safe_int(methodology.get("fold_size_bars"), 12)),
    }


def _priority_tickers(output_dir: Path) -> List[str]:
    go_no_go = _load_required_json(output_dir, "phase_b_data_extension_ingest_go_no_go.json")
    tickers = [_safe_str(item).upper() for item in list(go_no_go.get("rejected_tickers") or []) if _safe_str(item)]
    if tickers:
        return tickers
    execution_plan = _load_required_json(output_dir, "phase_b_data_extension_execution_plan.json")
    return [_safe_str(item).upper() for item in list(execution_plan.get("priority_tickers") or []) if _safe_str(item)]


def _snapshot_for_ticker(path: Path, methodology: Dict[str, int]) -> Dict[str, object]:
    if not path.exists():
        return {
            "exists": False,
            "rows": 0,
            "dates": set(),
            "date_end": "",
            "article_days": 0,
            "news_count_total": 0,
            "usable_oos_windows": 0,
        }

    frame = _load_csv(path)
    if frame.empty:
        return {
            "exists": True,
            "rows": 0,
            "dates": set(),
            "date_end": "",
            "article_days": 0,
            "news_count_total": 0,
            "usable_oos_windows": 0,
        }

    dates = (
        pd.to_datetime(frame["date"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("").tolist()
        if "date" in frame.columns
        else []
    )
    news_series = (
        pd.to_numeric(frame.get("sentiment_news_count_1d"), errors="coerce").fillna(0.0)
        if "sentiment_news_count_1d" in frame.columns
        else pd.Series([0.0] * len(frame))
    )
    return {
        "exists": True,
        "rows": int(len(frame)),
        "dates": {item for item in dates if item},
        "date_end": _safe_str(dates[-1] if dates else ""),
        "article_days": int((news_series > 0).sum()),
        "news_count_total": int(float(news_series.sum())),
        "usable_oos_windows": _usable_oos_windows(
            int(len(frame)),
            _safe_int(methodology.get("warmup_bars"), 21),
            _safe_int(methodology.get("fold_size_bars"), 12),
        ),
    }


def _snapshot_map(data_dir: Path, tickers: Sequence[str], methodology: Dict[str, int]) -> Dict[str, Dict[str, object]]:
    return {
        ticker: _snapshot_for_ticker(Path(data_dir) / f"{ticker}.csv", methodology)
        for ticker in tickers
    }


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


def _build_command_runner() -> CommandExecutor:
    php_binary = shutil.which("php")
    if php_binary is None:
        raise PhaseBPriorityBackfillExecutionCliError("PHP binary not available; cannot run artisan backfill/export commands.")

    def _runner(command: Sequence[str], cwd: Path) -> Dict[str, object]:
        full_command = [php_binary, *command[1:]] if command and command[0] == "php" else list(command)
        return _default_command_executor(full_command, cwd)

    return _runner


def _row_advance_rows(
    tickers: Sequence[str],
    before: Dict[str, Dict[str, object]],
    after: Dict[str, Dict[str, object]],
) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for ticker in tickers:
        baseline = before.get(ticker, {})
        current = after.get(ticker, {})
        before_dates = set(baseline.get("dates") or set())
        after_dates = set(current.get("dates") or set())
        new_unique_dates_count = int(len(after_dates - before_dates))
        rows_delta = _safe_int(current.get("rows")) - _safe_int(baseline.get("rows"))
        windows_delta = _safe_int(current.get("usable_oos_windows")) - _safe_int(baseline.get("usable_oos_windows"))
        article_days_delta = _safe_int(current.get("article_days")) - _safe_int(baseline.get("article_days"))
        news_total_delta = _safe_int(current.get("news_count_total")) - _safe_int(baseline.get("news_count_total"))
        date_end_before = _safe_str(baseline.get("date_end"))
        date_end_after = _safe_str(current.get("date_end"))
        date_end_advanced = bool(date_end_after and date_end_before and date_end_after > date_end_before)
        non_duplicate_row_advance_detected = bool(rows_delta > 0 or new_unique_dates_count > 0)

        if non_duplicate_row_advance_detected and (windows_delta > 0 or article_days_delta > 0):
            ticker_status = "advanced_with_support"
        elif non_duplicate_row_advance_detected or date_end_advanced:
            ticker_status = "advanced_not_material"
        else:
            ticker_status = "static"

        rows.append(
            {
                "ticker": ticker,
                "rows_before": _safe_int(baseline.get("rows")),
                "rows_after": _safe_int(current.get("rows")),
                "rows_delta": rows_delta,
                "new_unique_dates_count": new_unique_dates_count,
                "non_duplicate_row_advance_detected": non_duplicate_row_advance_detected,
                "date_end_before": date_end_before,
                "date_end_after": date_end_after,
                "date_end_advanced": date_end_advanced,
                "usable_oos_windows_before": _safe_int(baseline.get("usable_oos_windows")),
                "usable_oos_windows_after": _safe_int(current.get("usable_oos_windows")),
                "usable_oos_windows_delta": windows_delta,
                "article_days_before": _safe_int(baseline.get("article_days")),
                "article_days_after": _safe_int(current.get("article_days")),
                "article_days_delta": article_days_delta,
                "news_count_total_before": _safe_int(baseline.get("news_count_total")),
                "news_count_total_after": _safe_int(current.get("news_count_total")),
                "news_count_total_delta": news_total_delta,
                "ticker_status": ticker_status,
            }
        )
    return rows


def _rerun_local_artifacts(data_dir: Path, output_dir: Path, metadata_file: Optional[Path]) -> Tuple[Dict[str, object], Dict[str, object]]:
    progress = run_phase_b_data_extension_progress_update(
        data_dir=data_dir,
        output_dir=output_dir,
        metadata_file=metadata_file,
    )["phase_b_data_extension_progress_update"]
    run_phase_b_data_extension_ingest_audit(
        data_dir=data_dir,
        output_dir=output_dir,
        metadata_file=metadata_file,
    )
    go_no_go = run_phase_b_data_extension_ingest_rejection_analysis(
        data_dir=data_dir,
        output_dir=output_dir,
        metadata_file=metadata_file,
    )["phase_b_data_extension_ingest_go_no_go"]
    return progress, go_no_go


def _batch_1_status(
    *,
    row_rows: Sequence[Dict[str, object]],
    refreshed_progress: Dict[str, object],
    refreshed_go_no_go: Dict[str, object],
    fetch_result: Dict[str, object],
    export_result: Dict[str, object],
) -> Tuple[str, bool, bool, bool, bool, bool, bool, bool, str]:
    row_advance_detected = any(_safe_bool(row.get("non_duplicate_row_advance_detected")) for row in row_rows)
    date_end_advanced = any(_safe_bool(row.get("date_end_advanced")) for row in row_rows)
    per_ticker_windows_advanced = any(_safe_int(row.get("usable_oos_windows_delta")) > 0 for row in row_rows)
    per_ticker_article_day_advanced = any(_safe_int(row.get("article_days_delta")) > 0 for row in row_rows)
    history_min_delta = _safe_float(
        safe_dict(refreshed_progress.get("progress_since_baseline_v9", {}))
        .get("min_history_bars_per_ticker", {})
        .get("delta")
    )
    usable_windows_delta = _safe_float(
        safe_dict(refreshed_progress.get("progress_since_baseline_v9", {}))
        .get("usable_oos_windows_per_ticker", {})
        .get("delta")
    )
    article_day_delta = _safe_float(
        safe_dict(refreshed_progress.get("progress_since_baseline_v9", {}))
        .get("primary_segment_article_days_median", {})
        .get("delta")
    )

    usable_oos_windows_advanced = usable_windows_delta > 0 or per_ticker_windows_advanced
    primary_article_day_recovery_advanced = article_day_delta > 0 or per_ticker_article_day_advanced
    batch_1_priority_targets_closed = _safe_bool(refreshed_go_no_go.get("batch_1_closure_progress_valid"))
    highest_completed_batch = _safe_str(refreshed_progress.get("highest_completed_batch"))
    batch_1_operationally_complete = highest_completed_batch in {"batch_1", "batch_2", "batch_3"} or (
        _safe_bool(refreshed_progress.get("current_batch_completed"))
        and _safe_str(refreshed_progress.get("current_batch")) == "batch_1"
    )
    batch_1_officially_started = row_advance_detected or date_end_advanced or history_min_delta > 0
    batch_1_material_progress_detected = bool(history_min_delta > 0 and primary_article_day_recovery_advanced)

    if batch_1_operationally_complete:
        status = "batch_1_operationally_complete_ready_for_batch_2"
    elif batch_1_priority_targets_closed:
        status = "batch_1_priority_targets_closed_but_progress_gate_pending"
    elif batch_1_material_progress_detected:
        status = "batch_1_material_progress_detected"
    elif batch_1_officially_started:
        status = "batch_1_started_but_not_material_yet"
    else:
        status = "batch_1_not_started_snapshot_still_static"

    if status not in BATCH_1_STATUSES:
        raise PhaseBPriorityBackfillExecutionCliError(f"Unexpected batch_1_status: {status}")

    if not _safe_bool(fetch_result.get("succeeded")) and "connection refused" in _safe_str(fetch_result.get("combined_output")).lower():
        recommended_next_action = "restore_laravel_mysql_connectivity_then_rerun_priority_backfill_and_export_before_rechecking_progress"
    elif not _safe_bool(fetch_result.get("succeeded")):
        recommended_next_action = "inspect_fetch_history_command_failure_then_retry_priority_backfill"
    elif not _safe_bool(export_result.get("succeeded")):
        recommended_next_action = "inspect_phase_a_export_failure_then_rerun_snapshot_export_before_progress_refresh"
    elif batch_1_operationally_complete:
        recommended_next_action = "freeze_batch_1_snapshot_and_prepare_batch_2_extension_without_reopening_strategy_track"
    elif batch_1_priority_targets_closed:
        recommended_next_action = "reconcile_progress_gate_semantics_before_advancing_batch_2"
    elif batch_1_material_progress_detected:
        recommended_next_action = "continue_priority_backfill_until_batch_1_targets_close_and_do_not_rerun_readiness_gate_yet"
    elif batch_1_officially_started:
        recommended_next_action = "continue_priority_backfill_until_history_and_primary_article_day_recovery_both_move_materially"
    else:
        recommended_next_action = "backfill_again_only_after_confirming_db_source_and_export_pipeline_are_available"

    return (
        status,
        row_advance_detected,
        date_end_advanced,
        usable_oos_windows_advanced,
        primary_article_day_recovery_advanced,
        batch_1_officially_started,
        batch_1_material_progress_detected,
        batch_1_priority_targets_closed,
        batch_1_operationally_complete,
        recommended_next_action,
    )


def run_phase_b_priority_backfill_execution(
    *,
    data_dir: Path,
    output_dir: Path,
    metadata_file: Optional[Path] = None,
    days: int = 180,
    command_executor: Optional[CommandExecutor] = None,
) -> Dict[str, object]:
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    project_root = Path(__file__).resolve().parent.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    pipeline_root_cause = _load_required_json(output_dir, "phase_b_data_extension_pipeline_root_cause.json")
    _load_required_json(output_dir, "phase_b_data_extension_pipeline_fix_status.json")
    _load_required_json(output_dir, "phase_b_next_ingest_requirements.json")
    _load_required_json(output_dir, "phase_b_data_extension_progress_update.json")
    _load_required_json(output_dir, "phase_b_data_extension_execution_plan.json")
    limitations: List[str] = []
    for filename in [
        "phase_b_recheck_trigger.json",
        "phase_b_recheck_readiness_status.json",
        "phase_b_retest_readiness_gate.json",
        "phase_b_data_extension_progress_tracker_refreshed.csv",
        "baseline_v6_universe_segmentation.csv",
    ]:
        _, warnings, _ = _load_optional_json(output_dir, filename) if filename.endswith(".json") else ({}, [], Path(output_dir / filename).exists())
        limitations.extend(warnings)

    tickers = _priority_tickers(output_dir)
    methodology = _load_methodology(output_dir)
    before_snapshot = _snapshot_map(data_dir, tickers, methodology)

    executor = command_executor or _build_command_runner()
    fetch_command = ["php", "artisan", "stocks:fetch-history", f"--days={max(1, int(days))}"]
    export_command = [
        "php",
        "artisan",
        "phase-a:export-real-data",
        "--data-dir=data",
        "--metadata-file=data/ticker_metadata.csv",
        "--include-sentiment-series",
    ]

    try:
        fetch_result = executor(fetch_command, project_root)
    except Exception as exc:
        fetch_result = {
            "command": " ".join(fetch_command),
            "returncode": 1,
            "stdout": "",
            "stderr": str(exc),
            "combined_output": str(exc),
            "succeeded": False,
        }
    try:
        export_result = executor(export_command, project_root)
    except Exception as exc:
        export_result = {
            "command": " ".join(export_command),
            "returncode": 1,
            "stdout": "",
            "stderr": str(exc),
            "combined_output": str(exc),
            "succeeded": False,
        }

    refreshed_progress, refreshed_go_no_go = _rerun_local_artifacts(
        data_dir=data_dir,
        output_dir=output_dir,
        metadata_file=metadata_file,
    )

    after_snapshot = _snapshot_map(data_dir, tickers, methodology)
    row_rows = _row_advance_rows(tickers, before_snapshot, after_snapshot)
    (
        batch_1_status,
        row_advance_detected,
        date_end_advanced,
        usable_oos_windows_advanced,
        primary_article_day_recovery_advanced,
        batch_1_officially_started,
        batch_1_material_progress_detected,
        batch_1_priority_targets_closed,
        batch_1_operationally_complete,
        recommended_next_action,
    ) = _batch_1_status(
        row_rows=row_rows,
        refreshed_progress=refreshed_progress,
        refreshed_go_no_go=refreshed_go_no_go,
        fetch_result=fetch_result,
        export_result=export_result,
    )

    execution_payload = {
        "generated_at": _now_iso(),
        "backfill_execution_attempted": True,
        "priority_tickers_processed": tickers,
        "fetch_command": fetch_result,
        "export_command": export_result,
        "row_advance_detected": row_advance_detected,
        "date_end_advanced": date_end_advanced,
        "usable_oos_windows_advanced": usable_oos_windows_advanced,
        "primary_article_day_recovery_advanced": primary_article_day_recovery_advanced,
        "batch_1_status": batch_1_status,
        "batch_1_officially_started": batch_1_officially_started,
        "batch_1_material_progress_detected": batch_1_material_progress_detected,
        "batch_1_priority_targets_closed": batch_1_priority_targets_closed,
        "batch_1_operationally_complete": batch_1_operationally_complete,
        "ready_for_batch_2": batch_1_operationally_complete,
        "recommended_next_action": recommended_next_action,
        "source_of_truth_root_cause": {
            "root_cause_class": _safe_str(pipeline_root_cause.get("root_cause_class")),
            "highest_blocking_step": _safe_str(pipeline_root_cause.get("highest_blocking_step")),
        },
        "limitations": dedupe(limitations),
    }

    batch_status_payload = {
        "generated_at": _now_iso(),
        "backfill_execution_attempted": True,
        "priority_tickers_processed": tickers,
        "row_advance_detected": row_advance_detected,
        "date_end_advanced": date_end_advanced,
        "usable_oos_windows_advanced": usable_oos_windows_advanced,
        "primary_article_day_recovery_advanced": primary_article_day_recovery_advanced,
        "batch_1_status": batch_1_status,
        "batch_1_officially_started": batch_1_officially_started,
        "batch_1_material_progress_detected": batch_1_material_progress_detected,
        "batch_1_priority_targets_closed": batch_1_priority_targets_closed,
        "batch_1_operationally_complete": batch_1_operationally_complete,
        "ready_for_batch_2": batch_1_operationally_complete,
        "recommended_next_action": recommended_next_action,
    }

    next_steps_payload = {
        "generated_at": _now_iso(),
        "batch_1_status": batch_1_status,
        "blocking_execution_issue": (
            "laravel_db_unreachable"
            if "connection refused" in _safe_str(fetch_result.get("combined_output")).lower()
            or "connection refused" in _safe_str(export_result.get("combined_output")).lower()
            else "snapshot_not_advanced"
        ),
        "required_before_next_recheck": [
            "priority ticker CSV row count must increase materially from current baseline",
            "date_end and/or unique date coverage must advance beyond the static snapshot horizon",
            "primary segment article-day coverage must move above the current baseline",
            "readiness gate must remain frozen until batch progress is above checkpoint material",
        ],
        "recommended_next_action": recommended_next_action,
    }

    _write_json(output_dir / BACKFILL_EXECUTION_JSON_OUTPUT, execution_payload)
    _write_json(output_dir / BATCH_STATUS_JSON_OUTPUT, batch_status_payload)
    _write_json(output_dir / NEXT_STEPS_JSON_OUTPUT, next_steps_payload)
    _write_csv(output_dir / ROW_ADVANCE_CSV_OUTPUT, ROW_ADVANCE_COLUMNS, row_rows)

    lines = [
        f"Backfill attempted: true",
        f"Fetch command succeeded: {str(_safe_bool(fetch_result.get('succeeded'))).lower()}",
        f"Export command succeeded: {str(_safe_bool(export_result.get('succeeded'))).lower()}",
        f"Row advance detected: {str(row_advance_detected).lower()}",
        f"Date end advanced: {str(date_end_advanced).lower()}",
        f"Usable OOS windows advanced: {str(usable_oos_windows_advanced).lower()}",
        f"Primary article-day recovery advanced: {str(primary_article_day_recovery_advanced).lower()}",
        f"Batch-1 status: {batch_1_status}",
        f"Recommended next action: {recommended_next_action}",
    ]
    if batch_1_status == "batch_1_not_started_snapshot_still_static":
        lines.append("Backfill prioritas sudah dijalankan, tetapi snapshot tetap statis sehingga batch-1 belum mulai bergerak.")
    elif batch_1_status == "batch_1_started_but_not_material_yet":
        lines.append("Row advance terdeteksi pada sebagian ticker prioritas, tetapi belum cukup untuk checkpoint material.")
    elif batch_1_status == "batch_1_material_progress_detected":
        lines.append("Batch-1 resmi mulai bergerak karena history minimum dan article-day primary sudah naik dari baseline.")
    elif batch_1_status == "batch_1_priority_targets_closed_but_progress_gate_pending":
        lines.append("Target prioritas batch-1 sudah tertutup, tetapi progress artifact resmi belum mengizinkan advance ke batch-2.")
    else:
        lines.append("Batch-1 selesai dan siap ditutup untuk lanjut ke batch-2 tanpa membuka gate retest.")
    if not _safe_bool(fetch_result.get("succeeded")):
        lines.append("Gate readiness tetap tidak boleh diulang sampai progres batch melampaui checkpoint material.")
    _write_text(output_dir / BACKFILL_EXECUTION_TEXT_OUTPUT, lines)

    return {
        "phase_b_priority_backfill_execution": execution_payload,
        "phase_b_priority_backfill_batch1_status": batch_status_payload,
        "phase_b_priority_backfill_next_steps": next_steps_payload,
        "phase_b_priority_backfill_row_advance": row_rows,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data", help="Directory containing exported ticker snapshots.")
    parser.add_argument("--output-dir", default="output", help="Directory containing Phase B artifacts.")
    parser.add_argument("--metadata-file", default="data/ticker_metadata.csv", help="Metadata CSV path.")
    parser.add_argument("--days", default=180, type=int, help="Backfill horizon for stocks:fetch-history.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        run_phase_b_priority_backfill_execution(
            data_dir=Path(args.data_dir),
            output_dir=Path(args.output_dir),
            metadata_file=Path(args.metadata_file) if args.metadata_file else None,
            days=args.days,
        )
    except PhaseBPriorityBackfillExecutionCliError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
