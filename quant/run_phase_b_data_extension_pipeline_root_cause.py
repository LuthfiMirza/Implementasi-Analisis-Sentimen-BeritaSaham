"""Trace the Phase B data-extension pipeline and classify why ingest made no material progress."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.phase_a_transition_utils import dedupe, read_json_object, safe_dict  # noqa: E402


ROOT_CAUSE_JSON_OUTPUT = "phase_b_data_extension_pipeline_root_cause.json"
ROOT_CAUSE_TEXT_OUTPUT = "phase_b_data_extension_pipeline_root_cause.txt"
PIPELINE_TRACE_OUTPUT = "phase_b_data_extension_pipeline_trace.csv"
FIX_STATUS_OUTPUT = "phase_b_data_extension_pipeline_fix_status.json"
NEXT_INGEST_REQUIREMENTS_OUTPUT = "phase_b_next_ingest_requirements.json"

ROOT_CAUSE_CLASSES = {
    "pipeline_bug_confirmed",
    "pipeline_config_misaligned",
    "source_data_not_extended_yet",
    "ingest_completed_but_snapshot_not_advanced",
    "mixed_root_cause",
}
TRACE_COLUMNS = [
    "step_id",
    "stage",
    "owner",
    "owner_file",
    "is_primary_path",
    "status",
    "evidence",
]


class PhaseBPipelineRootCauseCliError(ValueError):
    """Friendly CLI error for pipeline root-cause tracing."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


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
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _load_required_json(output_dir: Path, filename: str) -> Dict[str, object]:
    payload, warnings = read_json_object(Path(output_dir) / filename, filename)
    if payload is None:
        warning_text = "; ".join(warnings) if warnings else "unknown error"
        raise PhaseBPipelineRootCauseCliError(f"Required artifact missing or invalid: {filename} ({warning_text})")
    return safe_dict(payload)


def _load_optional_json(output_dir: Path, filename: str) -> Tuple[Dict[str, object], List[str], bool]:
    payload, warnings = read_json_object(Path(output_dir) / filename, filename)
    return safe_dict(payload), list(warnings), payload is not None


def _load_required_csv(output_dir: Path, filename: str) -> pd.DataFrame:
    path = Path(output_dir) / filename
    if not path.exists():
        raise PhaseBPipelineRootCauseCliError(f"Required artifact not found: {path}")
    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        raise PhaseBPipelineRootCauseCliError(f"Failed to read {path}: {exc}") from exc
    if frame.empty:
        raise PhaseBPipelineRootCauseCliError(f"{path} is empty.")
    return frame


def _read_optional_text(path: Optional[Path]) -> Tuple[str, List[str], bool]:
    if path is None:
        return "", [], False
    target = Path(path)
    if not target.exists():
        return "", [f"Code path not found: {target}"], False
    try:
        return target.read_text(encoding="utf-8"), [], True
    except Exception as exc:
        return "", [f"Failed to read code path {target}: {exc}"], False


def _inspect_fetch_command(path: Optional[Path]) -> Tuple[Dict[str, object], List[str]]:
    text, warnings, available = _read_optional_text(path)
    if not available:
        return {
            "available": False,
            "supports_extended_ranges": False,
            "legacy_three_month_cap_detected": False,
            "local_code_fix_applied": False,
            "has_history_option_contract": False,
            "status": "missing",
            "evidence": "fetch command file unavailable",
        }, warnings

    supports_extended_ranges = all(token in text for token in ["6mo", "1y", "2y", "max"])
    legacy_three_month_cap_detected = "days >= 90 ? '3mo'" in text or "default 90 (3mo)" in text
    local_code_fix_applied = "Fix history-range cap" in text or (
        "resolveYahooRange" in text and supports_extended_ranges and not legacy_three_month_cap_detected
    )
    has_history_option_contract = "Jumlah hari historis" in text and "--days=90" in text

    if legacy_three_month_cap_detected:
        status = "legacy_cap_detected"
        evidence = "Fetch command still caps requests at 3mo for days>90."
    elif supports_extended_ranges:
        status = "extended_range_supported"
        evidence = "Fetch command supports 6mo/1y/2y/max backfill windows."
    else:
        status = "range_support_unclear"
        evidence = "Fetch command exists but extended Yahoo range support is not explicit."

    return {
        "available": True,
        "supports_extended_ranges": supports_extended_ranges,
        "legacy_three_month_cap_detected": legacy_three_month_cap_detected,
        "local_code_fix_applied": local_code_fix_applied,
        "has_history_option_contract": has_history_option_contract,
        "status": status,
        "evidence": evidence,
    }, warnings


def _inspect_routes_schedule(path: Optional[Path]) -> Tuple[Dict[str, object], List[str]]:
    text, warnings, available = _read_optional_text(path)
    if not available:
        return {
            "available": False,
            "scheduled_history_fetch_count": 0,
            "scheduled_days_one_count": 0,
            "status": "missing",
            "evidence": "routes schedule file unavailable",
        }, warnings

    scheduled_fetch_count = text.count("stocks:fetch-history")
    scheduled_days_one_count = text.count("stocks:fetch-history --days=1")
    if scheduled_fetch_count == 0:
        status = "not_scheduled_here"
        evidence = "No fetch-history schedule entry found in routes console."
    elif scheduled_days_one_count == scheduled_fetch_count:
        status = "daily_refresh_only"
        evidence = "All scheduled fetch-history jobs use --days=1 and do not establish a bulk backfill path."
    else:
        status = "mixed_schedule"
        evidence = "Schedule includes fetch-history and at least one non-trivial window."

    return {
        "available": True,
        "scheduled_history_fetch_count": scheduled_fetch_count,
        "scheduled_days_one_count": scheduled_days_one_count,
        "status": status,
        "evidence": evidence,
    }, warnings


def _inspect_update_snapshots(path: Optional[Path]) -> Tuple[Dict[str, object], List[str]]:
    text, warnings, available = _read_optional_text(path)
    if not available:
        return {
            "available": False,
            "status": "missing",
            "evidence": "update snapshots command unavailable",
        }, warnings

    demo_style = "random_int" in text and "subDays" in text and "updateOrCreate" in text
    return {
        "available": True,
        "status": "demo_snapshot_only" if demo_style else "custom_or_unknown",
        "evidence": "Command generates simple daily demo snapshots and is not the bulk history extension path."
        if demo_style
        else "Command exists but does not clearly expose a dedicated bulk history extension flow.",
    }, warnings


def _inspect_export_command(path: Optional[Path]) -> Tuple[Dict[str, object], List[str]]:
    text, warnings, available = _read_optional_text(path)
    if not available:
        return {
            "available": False,
            "writes_data_csv": False,
            "writes_metadata": False,
            "reads_stock_prices": False,
            "status": "missing",
            "evidence": "phase-a export command unavailable",
        }, warnings

    writes_data_csv = "writeCsv($tickerPath" in text
    writes_metadata = "ticker_metadata.csv" in text and "writeCsv($metadataPath" in text
    reads_stock_prices = "StockPrice::query()" in text
    status = "working_export_path" if writes_data_csv and writes_metadata and reads_stock_prices else "partial_export_path"
    evidence = "Export command rewrites data/*.csv and ticker_metadata.csv from stock_prices." if status == "working_export_path" else "Export command path exists but expected stock_prices -> CSV flow is incomplete."
    return {
        "available": True,
        "writes_data_csv": writes_data_csv,
        "writes_metadata": writes_metadata,
        "reads_stock_prices": reads_stock_prices,
        "status": status,
        "evidence": evidence,
    }, warnings


def _inspect_segmentation_runner(path: Optional[Path]) -> Tuple[Dict[str, object], List[str]]:
    text, warnings, available = _read_optional_text(path)
    if not available:
        return {
            "available": False,
            "writes_segmentation": False,
            "status": "missing",
            "evidence": "segmentation runner unavailable",
        }, warnings

    writes_segmentation = 'SEGMENTATION_CSV_OUTPUT = "baseline_v6_universe_segmentation.csv"' in text
    return {
        "available": True,
        "writes_segmentation": writes_segmentation,
        "status": "working_segmentation_path" if writes_segmentation else "segmentation_path_unclear",
        "evidence": "Universe segmentation artifact is owned by baseline_v6 guardrail review runner."
        if writes_segmentation
        else "Segmentation runner exists but ownership of baseline_v6_universe_segmentation.csv is not explicit.",
    }, warnings


def _priority_tickers(go_no_go: Dict[str, object], diagnostics_df: pd.DataFrame) -> List[str]:
    rejected = [_safe_str(item).upper() for item in list(go_no_go.get("rejected_tickers") or []) if _safe_str(item)]
    if rejected:
        return rejected
    if "ticker" not in diagnostics_df.columns:
        return []
    return diagnostics_df["ticker"].astype(str).str.upper().drop_duplicates().tolist()


def _snapshot_summary(data_dir: Path, tickers: Sequence[str]) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []
    for ticker in tickers:
        target = Path(data_dir) / f"{ticker}.csv"
        if not target.exists():
            rows.append(
                {
                    "ticker": ticker,
                    "file_exists": False,
                    "rows": 0,
                    "date_start": "",
                    "date_end": "",
                    "article_days": 0,
                    "article_total": 0,
                }
            )
            continue
        frame = pd.read_csv(target)
        date_start = _safe_str(frame["date"].iloc[0]) if not frame.empty and "date" in frame.columns else ""
        date_end = _safe_str(frame["date"].iloc[-1]) if not frame.empty and "date" in frame.columns else ""
        article_series = (
            pd.to_numeric(frame.get("sentiment_news_count_1d"), errors="coerce").fillna(0.0)
            if "sentiment_news_count_1d" in frame.columns
            else pd.Series([0.0] * len(frame))
        )
        rows.append(
            {
                "ticker": ticker,
                "file_exists": True,
                "rows": int(len(frame)),
                "date_start": date_start,
                "date_end": date_end,
                "article_days": int((article_series > 0).sum()),
                "article_total": int(float(article_series.sum())),
            }
        )
    return pd.DataFrame(rows)


def _current_material_progress(rejection_analysis: Dict[str, object], progress_update: Dict[str, object]) -> Tuple[bool, bool]:
    material_progress_detected = _safe_bool(rejection_analysis.get("material_progress_detected"))
    snapshot_advanced_confirmed = _safe_bool(progress_update.get("progress_since_baseline_v9", {}).get("history_extension_progress_detected"))
    if not snapshot_advanced_confirmed:
        snapshot_advanced_confirmed = material_progress_detected and _safe_bool(rejection_analysis.get("history_progress_valid"))
    return material_progress_detected, snapshot_advanced_confirmed


def _batch_targets(execution_plan: Dict[str, object], batch_id: str) -> Dict[str, object]:
    direct = safe_dict(execution_plan.get("current_batch_targets"))
    if direct:
        return direct
    for item in list(execution_plan.get("execution_batches") or []):
        candidate = safe_dict(item)
        if _safe_str(candidate.get("batch_id")) == batch_id:
            return safe_dict(candidate.get("targets"))
    return {}


def _build_trace_rows(
    *,
    fetch_info: Dict[str, object],
    routes_info: Dict[str, object],
    update_info: Dict[str, object],
    export_info: Dict[str, object],
    segmentation_info: Dict[str, object],
    metadata_refresh_working: bool,
    segmentation_refresh_working: bool,
    snapshot_advanced_confirmed: bool,
) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = [
        {
            "step_id": "fetch_history_command",
            "stage": "fetch",
            "owner": "FetchStockHistoryCommand",
            "owner_file": "app/Console/Commands/FetchStockHistoryCommand.php",
            "is_primary_path": True,
            "status": _safe_str(fetch_info.get("status")),
            "evidence": _safe_str(fetch_info.get("evidence")),
        },
        {
            "step_id": "scheduled_history_fetch",
            "stage": "orchestration",
            "owner": "routes_console_schedule",
            "owner_file": "routes/console.php",
            "is_primary_path": True,
            "status": _safe_str(routes_info.get("status")),
            "evidence": _safe_str(routes_info.get("evidence")),
        },
        {
            "step_id": "update_snapshots_command",
            "stage": "fetch",
            "owner": "UpdateStockSnapshotsCommand",
            "owner_file": "app/Console/Commands/UpdateStockSnapshotsCommand.php",
            "is_primary_path": False,
            "status": _safe_str(update_info.get("status")),
            "evidence": _safe_str(update_info.get("evidence")),
        },
        {
            "step_id": "export_phase_a_real_data",
            "stage": "export",
            "owner": "ExportPhaseARealDataCommand",
            "owner_file": "app/Console/Commands/ExportPhaseARealDataCommand.php",
            "is_primary_path": True,
            "status": _safe_str(export_info.get("status")),
            "evidence": _safe_str(export_info.get("evidence")),
        },
        {
            "step_id": "metadata_refresh",
            "stage": "metadata",
            "owner": "phase-a:export-real-data",
            "owner_file": "app/Console/Commands/ExportPhaseARealDataCommand.php",
            "is_primary_path": True,
            "status": "working" if metadata_refresh_working else "not_working",
            "evidence": "Metadata refresh stayed synchronized with exported snapshot."
            if metadata_refresh_working
            else "Metadata refresh is not synchronized with latest snapshot.",
        },
        {
            "step_id": "segmentation_refresh",
            "stage": "segmentation",
            "owner": "run_baseline_v6_guardrail_review",
            "owner_file": "quant/run_baseline_v6_guardrail_review.py",
            "is_primary_path": False,
            "status": "working" if segmentation_refresh_working else _safe_str(segmentation_info.get("status")),
            "evidence": "Segmentation refresh is aligned with metadata/current CSV snapshot."
            if segmentation_refresh_working
            else _safe_str(segmentation_info.get("evidence")),
        },
        {
            "step_id": "snapshot_progress",
            "stage": "ingest",
            "owner": "phase_b_data_extension_progress_update",
            "owner_file": "quant/run_phase_b_data_extension_progress_update.py",
            "is_primary_path": True,
            "status": "advanced" if snapshot_advanced_confirmed else "not_advanced",
            "evidence": "Snapshot advanced materially from baseline." if snapshot_advanced_confirmed else "No material snapshot advance detected after ingest.",
        },
    ]
    return rows


def _determine_root_cause(
    *,
    fetch_info: Dict[str, object],
    routes_info: Dict[str, object],
    material_progress_detected: bool,
    snapshot_advanced_confirmed: bool,
    metadata_refresh_working: bool,
    segmentation_refresh_working: bool,
) -> Tuple[str, bool, bool, bool, str]:
    pipeline_bug_confirmed = _safe_bool(fetch_info.get("legacy_three_month_cap_detected")) or _safe_bool(fetch_info.get("local_code_fix_applied"))
    config_misalignment_confirmed = _safe_str(routes_info.get("status")) == "daily_refresh_only"
    source_data_extended_confirmed = material_progress_detected and snapshot_advanced_confirmed

    if pipeline_bug_confirmed and (config_misalignment_confirmed or not snapshot_advanced_confirmed):
        root_cause_class = "mixed_root_cause"
    elif pipeline_bug_confirmed:
        root_cause_class = "pipeline_bug_confirmed"
    elif config_misalignment_confirmed:
        root_cause_class = "pipeline_config_misaligned"
    elif not source_data_extended_confirmed:
        root_cause_class = "source_data_not_extended_yet"
    elif not snapshot_advanced_confirmed:
        root_cause_class = "ingest_completed_but_snapshot_not_advanced"
    else:
        root_cause_class = "mixed_root_cause"

    if not snapshot_advanced_confirmed:
        highest_blocking_step = "fetch_update_snapshot_stage"
    elif not metadata_refresh_working:
        highest_blocking_step = "metadata_refresh_stage"
    elif not segmentation_refresh_working:
        highest_blocking_step = "segmentation_refresh_stage"
    else:
        highest_blocking_step = "external_source_extension_stage"

    if pipeline_bug_confirmed and _safe_bool(fetch_info.get("local_code_fix_applied")):
        recommended_next_action = (
            "rerun_bulk_history_fetch_with_extended_days_then_export_phase_a_real_data_then_refresh_segmentation_and_repeat_ingest_audit"
        )
    elif config_misalignment_confirmed:
        recommended_next_action = "run_bulk_history_fetch_for_priority_tickers_before_exporting_or_rechecking_progress"
    else:
        recommended_next_action = "confirm_source_bars_exist_and_only_then_repeat_export_and_ingest_audit"

    return (
        root_cause_class,
        pipeline_bug_confirmed,
        config_misalignment_confirmed,
        source_data_extended_confirmed,
        highest_blocking_step,
        recommended_next_action,
    )


def run_phase_b_data_extension_pipeline_root_cause(
    *,
    data_dir: Path,
    output_dir: Path,
    metadata_file: Optional[Path] = None,
    fetch_command_file: Optional[Path] = None,
    export_command_file: Optional[Path] = None,
    update_snapshots_file: Optional[Path] = None,
    routes_console_file: Optional[Path] = None,
    segmentation_runner_file: Optional[Path] = None,
) -> Dict[str, object]:
    output_dir = Path(output_dir)
    data_dir = Path(data_dir)

    go_no_go = _load_required_json(output_dir, "phase_b_data_extension_ingest_go_no_go.json")
    rejection_analysis = _load_required_json(output_dir, "phase_b_data_extension_ingest_rejection_analysis.json")
    progress_update = _load_required_json(output_dir, "phase_b_data_extension_progress_update.json")
    execution_plan = _load_required_json(output_dir, "phase_b_data_extension_execution_plan.json")
    diagnostics_df = _load_required_csv(output_dir, "phase_b_data_extension_ingest_ticker_diagnostics.csv")
    checklist_df = _load_required_csv(output_dir, "phase_b_data_extension_ingest_priority_checklist.csv")

    limitations: List[str] = []
    for optional_name in [
        "phase_b_retest_readiness_gate.json",
        "phase_b_retest_next_requirements.json",
        "phase_b_data_extension_audit.json",
        "framework_redesign_scope.json",
    ]:
        _, warnings, _ = _load_optional_json(output_dir, optional_name)
        limitations.extend(warnings)

    root = _repo_root()
    fetch_command_file = Path(fetch_command_file or root / "app/Console/Commands/FetchStockHistoryCommand.php")
    export_command_file = Path(export_command_file or root / "app/Console/Commands/ExportPhaseARealDataCommand.php")
    update_snapshots_file = Path(update_snapshots_file or root / "app/Console/Commands/UpdateStockSnapshotsCommand.php")
    routes_console_file = Path(routes_console_file or root / "routes/console.php")
    segmentation_runner_file = Path(segmentation_runner_file or root / "quant/run_baseline_v6_guardrail_review.py")

    fetch_info, fetch_warnings = _inspect_fetch_command(fetch_command_file)
    routes_info, route_warnings = _inspect_routes_schedule(routes_console_file)
    update_info, update_warnings = _inspect_update_snapshots(update_snapshots_file)
    export_info, export_warnings = _inspect_export_command(export_command_file)
    segmentation_info, segmentation_warnings = _inspect_segmentation_runner(segmentation_runner_file)
    limitations.extend(fetch_warnings + route_warnings + update_warnings + export_warnings + segmentation_warnings)

    metadata_refresh_working = _safe_bool(go_no_go.get("metadata_refresh_valid"))
    segmentation_refresh_working = _safe_bool(go_no_go.get("segmentation_refresh_valid"))
    material_progress_detected, snapshot_advanced_confirmed = _current_material_progress(rejection_analysis, progress_update)
    priority_tickers = _priority_tickers(go_no_go, diagnostics_df)
    snapshots_df = _snapshot_summary(data_dir, priority_tickers)

    (
        root_cause_class,
        pipeline_bug_confirmed,
        config_misalignment_confirmed,
        source_data_extended_confirmed,
        highest_blocking_step,
        recommended_next_action,
    ) = _determine_root_cause(
        fetch_info=fetch_info,
        routes_info=routes_info,
        material_progress_detected=material_progress_detected,
        snapshot_advanced_confirmed=snapshot_advanced_confirmed,
        metadata_refresh_working=metadata_refresh_working,
        segmentation_refresh_working=segmentation_refresh_working,
    )

    if root_cause_class not in ROOT_CAUSE_CLASSES:
        raise PhaseBPipelineRootCauseCliError(f"Unexpected root cause class: {root_cause_class}")

    trace_rows = _build_trace_rows(
        fetch_info=fetch_info,
        routes_info=routes_info,
        update_info=update_info,
        export_info=export_info,
        segmentation_info=segmentation_info,
        metadata_refresh_working=metadata_refresh_working,
        segmentation_refresh_working=segmentation_refresh_working,
        snapshot_advanced_confirmed=snapshot_advanced_confirmed,
    )

    snapshot_date_range = ""
    if not snapshots_df.empty:
        starts = [item for item in snapshots_df["date_start"].astype(str).tolist() if item]
        ends = [item for item in snapshots_df["date_end"].astype(str).tolist() if item]
        if starts and ends:
            snapshot_date_range = f"{min(starts)}..{max(ends)}"

    root_cause_payload = {
        "generated_at": _now_iso(),
        "root_cause_class": root_cause_class,
        "pipeline_bug_confirmed": pipeline_bug_confirmed,
        "config_misalignment_confirmed": config_misalignment_confirmed,
        "source_data_extended_confirmed": source_data_extended_confirmed,
        "snapshot_advanced_confirmed": snapshot_advanced_confirmed,
        "metadata_refresh_working": metadata_refresh_working,
        "segmentation_refresh_working": segmentation_refresh_working,
        "highest_blocking_step": highest_blocking_step,
        "recommended_next_action": recommended_next_action,
        "priority_tickers": priority_tickers,
        "material_progress_detected": material_progress_detected,
        "snapshot_date_range": snapshot_date_range,
        "symptom_alignment": {
            "decision": _safe_str(go_no_go.get("decision")),
            "history_progress_valid": _safe_bool(go_no_go.get("history_progress_valid")),
            "primary_article_day_recovery_valid": _safe_bool(go_no_go.get("primary_article_day_recovery_valid")),
            "batch_1_closure_progress_valid": _safe_bool(go_no_go.get("batch_1_closure_progress_valid")),
            "current_batch": _safe_str(progress_update.get("current_batch")),
            "current_batch_completed": _safe_bool(progress_update.get("current_batch_completed")),
        },
        "decisive_statement": (
            "Pipeline fetch/export chain is aligned only through metadata refresh; the snapshot itself has not advanced materially."
            if snapshot_advanced_confirmed is False
            else "Snapshot has advanced, so remaining blockers are downstream synchronization issues."
        ),
        "limitations": dedupe(limitations),
    }

    fix_status_payload = {
        "generated_at": _now_iso(),
        "pipeline_bug_confirmed": pipeline_bug_confirmed,
        "local_code_fix_applied": _safe_bool(fetch_info.get("local_code_fix_applied")),
        "extended_range_support_detected": _safe_bool(fetch_info.get("supports_extended_ranges")),
        "legacy_three_month_cap_detected": _safe_bool(fetch_info.get("legacy_three_month_cap_detected")),
        "config_misalignment_confirmed": config_misalignment_confirmed,
        "fix_target_file": str(fetch_command_file),
        "verification_evidence": _safe_str(fetch_info.get("evidence")),
        "recommended_verification": "run_fetch_history_with_days_180_plus_then_export_phase_a_real_data_and_check_row_growth_per_priority_ticker",
    }

    current_batch_id = _safe_str(progress_update.get("current_batch"), "batch_1")
    batch_targets = _batch_targets(execution_plan, current_batch_id)
    target_min_history = _safe_float(batch_targets.get("min_history_bars_per_ticker"))
    next_requirements_payload = {
        "generated_at": _now_iso(),
        "root_cause_class": root_cause_class,
        "minimum_operational_requirements": [
            "fetch date window must extend beyond the current snapshot horizon for priority tickers",
            "export phase-a real data only after stock_prices rows actually increase",
            "metadata and segmentation refresh must be rerun against the advanced snapshot",
            "ingest progress is valid only when both history rows and primary article-day coverage increase materially",
        ],
        "required_fetch_command": "php artisan stocks:fetch-history --days=180",
        "required_export_command": "php artisan phase-a:export-real-data --data-dir=data --metadata-file=data/ticker_metadata.csv --include-sentiment-series",
        "required_validation_checks": [
            "priority ticker CSV row count must increase versus baseline",
            "date_end for priority tickers must move forward or the window length must expand materially",
            "primary segment article-day coverage must increase from the previous ingest baseline",
            "progress update and ingest audit must be rerun only after the snapshot changes",
        ],
        "batch_1_minimum_targets": {
            "min_history_bars_per_ticker": target_min_history,
            "usable_oos_windows_per_ticker": _safe_float(batch_targets.get("usable_oos_windows_per_ticker")),
            "primary_segment_total_articles": _safe_float(batch_targets.get("primary_segment_total_articles")),
            "primary_segment_article_days_median": _safe_float(batch_targets.get("primary_segment_article_days_median")),
        },
        "recommended_next_action": recommended_next_action,
    }

    trace_path = output_dir / PIPELINE_TRACE_OUTPUT
    trace_extra_rows = trace_rows + [
        {
            "step_id": f"priority_ticker::{row['ticker']}",
            "stage": "snapshot",
            "owner": row["ticker"],
            "owner_file": str((Path(data_dir) / f"{row['ticker']}.csv").name),
            "is_primary_path": True,
            "status": "snapshot_static" if _safe_int(row["rows"]) > 0 else "snapshot_missing",
            "evidence": f"rows={row['rows']} date_end={row['date_end']} article_days={row['article_days']} article_total={row['article_total']}",
        }
        for row in snapshots_df.to_dict(orient="records")
    ]

    _write_json(output_dir / ROOT_CAUSE_JSON_OUTPUT, root_cause_payload)
    _write_json(output_dir / FIX_STATUS_OUTPUT, fix_status_payload)
    _write_json(output_dir / NEXT_INGEST_REQUIREMENTS_OUTPUT, next_requirements_payload)
    _write_csv(trace_path, TRACE_COLUMNS, trace_extra_rows)

    summary_lines = [
        f"Root cause class: {root_cause_class}",
        f"Pipeline bug confirmed: {str(pipeline_bug_confirmed).lower()}",
        f"Config misalignment confirmed: {str(config_misalignment_confirmed).lower()}",
        f"Source data extended confirmed: {str(source_data_extended_confirmed).lower()}",
        f"Snapshot advanced confirmed: {str(snapshot_advanced_confirmed).lower()}",
        f"Metadata refresh working: {str(metadata_refresh_working).lower()}",
        f"Segmentation refresh working: {str(segmentation_refresh_working).lower()}",
        f"Highest blocking step: {highest_blocking_step}",
        f"Recommended next action: {recommended_next_action}",
    ]
    if pipeline_bug_confirmed and _safe_bool(fetch_info.get("local_code_fix_applied")):
        summary_lines.append("Local fetch-history range fix is present; next ingest still needs a real snapshot extension before progress can count.")
    if not snapshot_advanced_confirmed:
        summary_lines.append("Metadata and segmentation are synchronized, so the blocker sits before export/segmentation.")
    if config_misalignment_confirmed:
        summary_lines.append("Scheduled fetch jobs are daily refresh only and do not replace a deliberate bulk history extension run.")
    _write_text(output_dir / ROOT_CAUSE_TEXT_OUTPUT, summary_lines)

    return {
        "phase_b_data_extension_pipeline_root_cause": root_cause_payload,
        "phase_b_data_extension_pipeline_fix_status": fix_status_payload,
        "phase_b_next_ingest_requirements": next_requirements_payload,
        "phase_b_data_extension_pipeline_trace": trace_extra_rows,
        "phase_b_data_extension_ingest_priority_checklist_rows": checklist_df.to_dict(orient="records"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data", help="Directory containing per-ticker CSV snapshots.")
    parser.add_argument("--output-dir", default="output", help="Directory containing Phase B governance artifacts.")
    parser.add_argument("--metadata-file", default="data/ticker_metadata.csv", help="Unused compatibility argument.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        run_phase_b_data_extension_pipeline_root_cause(
            data_dir=Path(args.data_dir),
            output_dir=Path(args.output_dir),
            metadata_file=Path(args.metadata_file) if args.metadata_file else None,
        )
    except PhaseBPipelineRootCauseCliError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
