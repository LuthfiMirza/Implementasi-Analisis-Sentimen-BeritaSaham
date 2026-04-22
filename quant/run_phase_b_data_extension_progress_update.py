"""Refresh Phase B data-extension progress against the approved execution plan."""

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
from quant.run_phase_b_data_extension_execution_plan import (  # noqa: E402
    _build_progress_tracker,
    _merge_ticker_context,
    _methodology,
    _primary_segment,
    _primary_trade_lookup,
    _safe_segments,
    _load_artifacts as _load_execution_artifacts,
    _load_metadata_or_prices,
    _load_segmentation,
    _load_v9_results,
)


PROGRESS_UPDATE_JSON_OUTPUT = "phase_b_data_extension_progress_update.json"
PROGRESS_UPDATE_TEXT_OUTPUT = "phase_b_data_extension_progress_update.txt"
PROGRESS_REFRESHED_CSV_OUTPUT = "phase_b_data_extension_progress_tracker_refreshed.csv"
BATCH_STATUS_MATRIX_OUTPUT = "phase_b_batch_status_matrix.csv"
RECHECK_STATUS_OUTPUT = "phase_b_recheck_readiness_status.json"

TRACKED_PLAN_ARTIFACTS = [
    ("phase_b_data_extension_execution_plan", "phase_b_data_extension_execution_plan.json"),
    ("phase_b_recheck_trigger", "phase_b_recheck_trigger.json"),
    ("phase_b_data_extension_progress_tracker", "phase_b_data_extension_progress_tracker.csv"),
]

PROGRESS_COLUMNS = [
    "tracker_id",
    "tracker_scope",
    "metric_name",
    "unit",
    "baseline_value",
    "current_value",
    "delta_from_baseline",
    "target_value",
    "gap_to_target",
    "progress_pct",
    "batch_1_target",
    "batch_1_status",
    "batch_2_target",
    "batch_2_status",
    "batch_3_target",
    "batch_3_status",
    "status",
    "recheck_blocking",
    "note",
]

BATCH_MATRIX_COLUMNS = [
    "row_type",
    "subject_id",
    "metric_name",
    "current_snapshot",
    "batch_1_target",
    "batch_1_status",
    "batch_2_target",
    "batch_2_status",
    "batch_3_target",
    "batch_3_status",
    "blocking_note",
]


class PhaseBDataExtensionProgressUpdateCliError(ValueError):
    """Friendly CLI error for data-extension progress refresh."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_str(value: object) -> str:
    return str(value or "").strip()


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


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


def _load_optional_json(output_dir: Path, filename: str) -> Tuple[Dict[str, object], List[str], bool]:
    payload, warnings = read_json_object(Path(output_dir) / filename, filename)
    return safe_dict(payload), list(warnings), payload is not None


def _load_plan_artifacts(output_dir: Path) -> Tuple[Dict[str, Dict[str, object]], Dict[str, bool], List[str]]:
    artifacts: Dict[str, Dict[str, object]] = {}
    availability: Dict[str, bool] = {}
    warnings: List[str] = []
    for artifact_id, filename in TRACKED_PLAN_ARTIFACTS:
        if filename.endswith(".csv"):
            path = Path(output_dir) / filename
            availability[artifact_id] = path.exists()
            if not path.exists():
                warnings.append(f"{filename} not found: {path}.")
                artifacts[artifact_id] = {}
            else:
                artifacts[artifact_id] = {"path": str(path)}
            continue
        payload, item_warnings, available = _load_optional_json(output_dir=output_dir, filename=filename)
        artifacts[artifact_id] = payload
        availability[artifact_id] = available
        warnings.extend(item_warnings)
    return artifacts, availability, dedupe(warnings)


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _write_text(path: Path, lines: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: Sequence[Dict[str, object]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _read_baseline_tracker(path: Path) -> Tuple[Dict[str, Dict[str, object]], List[str]]:
    if not path.exists():
        return {}, [f"Baseline tracker not found: {path}."]
    try:
        with path.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    except Exception as exc:
        return {}, [f"Failed to read baseline tracker {path}: {exc}."]
    return {str(row.get("metric_name")): row for row in rows}, []


def _metadata_segmentation_refreshed(
    metadata_df: pd.DataFrame,
    segmentation_df: pd.DataFrame,
) -> bool:
    if metadata_df.empty or segmentation_df.empty:
        return False
    metadata_rows = (
        metadata_df[["ticker", "history_rows"]]
        .dropna(subset=["ticker"])
        .assign(ticker=lambda df: df["ticker"].astype(str).str.upper())
    )
    segmentation_rows = (
        segmentation_df[["ticker", "history_rows"]]
        .dropna(subset=["ticker"])
        .assign(ticker=lambda df: df["ticker"].astype(str).str.upper())
    )
    merged = metadata_rows.merge(segmentation_rows, on="ticker", how="inner", suffixes=("_meta", "_seg"))
    if merged.empty:
        return False
    return bool((pd.to_numeric(merged["history_rows_meta"], errors="coerce").fillna(-1).astype(int) == pd.to_numeric(merged["history_rows_seg"], errors="coerce").fillna(-2).astype(int)).all())


def _batch_metric_status(current_value: float, target_value: object, metric_name: str) -> str:
    if target_value in {"", None}:
        return "n/a"
    target = _safe_float(target_value)
    if metric_name == "no_single_fold_trade_share":
        return "done" if current_value <= target else "pending"
    return "done" if current_value >= target else "pending"


def _refresh_progress_rows(
    progress_tracker: Sequence[Dict[str, object]],
    baseline_lookup: Dict[str, Dict[str, object]],
) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for row in progress_tracker:
        metric_name = _safe_str(row.get("metric_name"))
        baseline_row = safe_dict(baseline_lookup.get(metric_name))
        baseline_value = _safe_float(baseline_row.get("current_value"), _safe_float(row.get("current_value")))
        current_value = _safe_float(row.get("current_value"))
        delta = round(current_value - baseline_value, 4)
        refreshed = dict(row)
        refreshed["baseline_value"] = baseline_value
        refreshed["delta_from_baseline"] = delta
        for batch_id in ["batch_1", "batch_2", "batch_3"]:
            target_field = f"{batch_id}_target"
            status_field = f"{batch_id}_status"
            refreshed[status_field] = _batch_metric_status(
                current_value=current_value,
                target_value=refreshed.get(target_field),
                metric_name=metric_name,
            )
        rows.append(refreshed)
    return rows


def _batch_targets(execution_plan: Dict[str, object]) -> Dict[str, Dict[str, object]]:
    targets: Dict[str, Dict[str, object]] = {}
    for item in list(execution_plan.get("execution_batches") or []):
        batch = safe_dict(item)
        batch_id = _safe_str(batch.get("batch_id"))
        if not batch_id:
            continue
        targets[batch_id] = safe_dict(batch.get("operational_targets")) or safe_dict(batch.get("targets"))
    return targets


def _tracker_lookup(rows: Sequence[Dict[str, object]]) -> Dict[str, Dict[str, object]]:
    return {str(row.get("metric_name")): dict(row) for row in rows}


def _batch_completed(batch_id: str, batch_targets: Dict[str, Dict[str, object]], tracker_lookup: Dict[str, Dict[str, object]]) -> bool:
    required = safe_dict(batch_targets.get(batch_id))
    if not required:
        return False
    metric_map = {
        "min_history_bars_per_ticker": "min_history_bars_per_ticker",
        "additional_bars_from_v9_baseline": "additional_bars_from_v9_baseline",
        "usable_oos_windows_per_ticker": "usable_oos_windows_per_ticker",
        "primary_segment_total_articles": "primary_segment_total_articles",
        "primary_segment_article_days_median": "primary_segment_article_days_median",
    }
    for source_metric, tracker_metric in metric_map.items():
        target = required.get(source_metric)
        row = safe_dict(tracker_lookup.get(tracker_metric))
        if _batch_metric_status(_safe_float(row.get("current_value")), target, tracker_metric) != "done":
            return False
    return True


def _resolve_batch_state(batch_targets: Dict[str, Dict[str, object]], tracker_lookup: Dict[str, Dict[str, object]]) -> Dict[str, object]:
    ordered_batches = ["batch_1", "batch_2", "batch_3"]
    completed_batches = [batch_id for batch_id in ordered_batches if _batch_completed(batch_id, batch_targets, tracker_lookup)]
    current_batch = next((batch_id for batch_id in ordered_batches if batch_id not in completed_batches), "batch_3")
    all_completed = len(completed_batches) == len(ordered_batches)
    if all_completed:
        current_batch = "batch_3"
    current_batch_completed = _batch_completed(current_batch, batch_targets, tracker_lookup)
    next_batch_id = ""
    if current_batch == "batch_1" and current_batch_completed:
        next_batch_id = "batch_2"
    elif current_batch == "batch_2" and current_batch_completed:
        next_batch_id = "batch_3"
    elif current_batch == "batch_3" and current_batch_completed:
        next_batch_id = ""
    else:
        next_batch_id = current_batch if current_batch in ordered_batches and current_batch not in completed_batches else ""

    if not completed_batches:
        next_batch_ready_to_start = True
    elif all_completed:
        next_batch_ready_to_start = False
    elif current_batch in {"batch_2", "batch_3"}:
        previous_batch = f"batch_{int(current_batch.split('_')[1]) - 1}"
        next_batch_ready_to_start = previous_batch in completed_batches
    else:
        next_batch_ready_to_start = False

    return {
        "completed_batches": completed_batches,
        "highest_completed_batch": completed_batches[-1] if completed_batches else "",
        "current_batch": current_batch,
        "current_batch_completed": current_batch_completed,
        "next_batch_id": next_batch_id,
        "next_batch_ready_to_start": next_batch_ready_to_start,
    }


def _batch_operational_completion(batch_state: Dict[str, object], batch_id: str) -> bool:
    completed_batches = {
        _safe_str(item)
        for item in list(batch_state.get("completed_batches") or [])
        if _safe_str(item)
    }
    if batch_id in completed_batches:
        return True
    return _safe_str(batch_state.get("current_batch")) == batch_id and _safe_bool(batch_state.get("current_batch_completed"))


def _checkpoint_material_reached(
    tracker_lookup: Dict[str, Dict[str, object]],
    metadata_segmentation_updated: bool,
    minimum_progress: Dict[str, object],
) -> Tuple[bool, List[str]]:
    blockers: List[str] = []
    for item in list(minimum_progress.get("required_metrics") or []):
        requirement = safe_dict(item)
        metric = _safe_str(requirement.get("metric"))
        operator = _safe_str(requirement.get("operator"))
        value = requirement.get("value")
        if metric == "metadata_and_segmentation_refreshed":
            passed = metadata_segmentation_updated is bool(value)
        else:
            row = safe_dict(tracker_lookup.get(metric))
            current = _safe_float(row.get("current_value"))
            target = _safe_float(value)
            if operator == ">=":
                passed = current >= target
            elif operator == "<=":
                passed = current <= target
            else:
                passed = False
        if not passed:
            if metric == "metadata_and_segmentation_refreshed":
                blockers.append("metadata_and_segmentation_refreshed=false target=true")
            else:
                blockers.append(f"{metric} actual={_safe_float(safe_dict(tracker_lookup.get(metric)).get('current_value'))} target{operator}{value}")
    return not blockers, blockers


def _progress_since_baseline_v9(tracker_lookup: Dict[str, Dict[str, object]]) -> Dict[str, object]:
    keys = [
        "min_history_bars_per_ticker",
        "additional_bars_from_v9_baseline",
        "usable_oos_windows_per_ticker",
        "coverage_ready_ticker_ratio",
        "primary_segment_total_articles",
        "primary_segment_article_days_median",
        "total_oos_trades_primary_segment",
        "no_single_fold_trade_share",
    ]
    payload: Dict[str, object] = {}
    for key in keys:
        row = safe_dict(tracker_lookup.get(key))
        payload[key] = {
            "baseline": _safe_float(row.get("baseline_value")),
            "current": _safe_float(row.get("current_value")),
            "delta": _safe_float(row.get("delta_from_baseline")),
        }
    return payload


def _build_ticker_matrix_rows(
    working: pd.DataFrame,
    batch_targets: Dict[str, Dict[str, object]],
) -> List[Dict[str, object]]:
    if working.empty:
        return []
    rows: List[Dict[str, object]] = []
    for _, item in working.sort_values(["is_primary_segment", "ticker"], ascending=[False, True]).iterrows():
        current_history = _safe_int(item.get("history_rows"))
        current_days = _safe_int(item.get("article_days"))
        is_primary = bool(item.get("is_primary_segment"))
        row = {
            "row_type": "ticker",
            "subject_id": _safe_str(item.get("ticker")),
            "metric_name": "ticker_execution_status",
            "current_snapshot": f"history={current_history}|article_days={current_days}|primary={is_primary}",
            "blocking_note": "Primary ticker still needs article-day recovery." if is_primary and current_days < 3 else "",
        }
        for batch_id, article_target in [("batch_1", 3), ("batch_2", 3), ("batch_3", 4)]:
            history_target = _safe_int(safe_dict(batch_targets.get(batch_id)).get("min_history_bars_per_ticker"))
            history_done = current_history >= history_target
            if is_primary:
                article_done = current_days >= article_target
                status = "done" if history_done and article_done else "pending"
                row[f"{batch_id}_target"] = f"history>={history_target}|article_days>={article_target}"
            else:
                status = "done" if history_done else "pending"
                row[f"{batch_id}_target"] = f"history>={history_target}"
            row[f"{batch_id}_status"] = status
        rows.append(row)
    return rows


def _build_segment_matrix_rows(
    working: pd.DataFrame,
    primary_segment: str,
    safe_segments: Sequence[str],
    batch_targets: Dict[str, Dict[str, object]],
) -> List[Dict[str, object]]:
    if working.empty:
        return []
    rows: List[Dict[str, object]] = []
    segment_specs = [primary_segment, *[item for item in safe_segments if item != primary_segment]]
    for segment in dedupe(segment_specs):
        field, value = segment.split("=", 1) if "=" in segment else ("", "")
        subset = working.loc[working[field].astype(str).eq(value)] if field and field in working.columns else pd.DataFrame()
        if subset.empty:
            snapshot = "missing"
            min_history = 0
            article_total = 0
            median_days = 0.0
        else:
            min_history = int(pd.to_numeric(subset["history_rows"], errors="coerce").fillna(0).min())
            article_total = int(pd.to_numeric(subset["news_count_total"], errors="coerce").fillna(0).sum())
            median_days = round(float(pd.to_numeric(subset["article_days"], errors="coerce").fillna(0).median()), 4)
            snapshot = f"history_min={min_history}|articles={article_total}|article_days_median={median_days}"
        row = {
            "row_type": "segment",
            "subject_id": segment,
            "metric_name": "segment_execution_status",
            "current_snapshot": snapshot,
            "blocking_note": "",
        }
        for batch_id in ["batch_1", "batch_2", "batch_3"]:
            history_target = _safe_int(safe_dict(batch_targets.get(batch_id)).get("min_history_bars_per_ticker"))
            if segment == primary_segment:
                article_target = _safe_int(safe_dict(batch_targets.get(batch_id)).get("primary_segment_total_articles"))
                days_target = _safe_float(safe_dict(batch_targets.get(batch_id)).get("primary_segment_article_days_median"))
                done = min_history >= history_target and article_total >= article_target and median_days >= days_target
                row[f"{batch_id}_target"] = f"history>={history_target}|articles>={article_target}|article_days_median>={days_target}"
                if not done and batch_id == "batch_2":
                    row["blocking_note"] = "Primary segment masih menahan checkpoint material."
            else:
                done = min_history >= history_target
                row[f"{batch_id}_target"] = f"history>={history_target}"
            row[f"{batch_id}_status"] = "done" if done else "pending"
        rows.append(row)
    return rows


def _build_global_matrix_rows(refreshed_rows: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for item in refreshed_rows:
        rows.append(
            {
                "row_type": "global_metric",
                "subject_id": _safe_str(item.get("tracker_scope")) or "global",
                "metric_name": _safe_str(item.get("metric_name")),
                "current_snapshot": item.get("current_value"),
                "batch_1_target": item.get("batch_1_target"),
                "batch_1_status": item.get("batch_1_status"),
                "batch_2_target": item.get("batch_2_target"),
                "batch_2_status": item.get("batch_2_status"),
                "batch_3_target": item.get("batch_3_target"),
                "batch_3_status": item.get("batch_3_status"),
                "blocking_note": item.get("note"),
            }
        )
    return rows


def _build_text_output(payload: Dict[str, object]) -> List[str]:
    window_semantics = safe_dict(payload.get("oos_window_threshold_semantics"))
    return [
        "Phase B Data Extension Progress Update",
        f"- current_batch={payload.get('current_batch')}",
        f"- current_batch_completed={payload.get('current_batch_completed')}",
        f"- next_batch_ready_to_start={payload.get('next_batch_ready_to_start')}",
        f"- checkpoint_material_reached={payload.get('checkpoint_material_reached')}",
        f"- recheck_readiness_gate_allowed={payload.get('recheck_readiness_gate_allowed')}",
        f"- methodology_minimum_windows={window_semantics.get('methodology_minimum_windows')}",
        f"- recommended_next_action={payload.get('recommended_next_action')}",
        f"- decisive_statement={payload.get('decisive_statement')}",
        "",
        "Remaining blockers:",
        *[f"- {item}" for item in list(payload.get("remaining_blockers") or [])],
    ]


def run_phase_b_data_extension_progress_update(
    data_dir: Path,
    output_dir: Path,
    metadata_file: Optional[Path] = None,
) -> Dict[str, object]:
    output_dir = Path(output_dir)
    data_dir = Path(data_dir)
    if not data_dir.exists():
        raise PhaseBDataExtensionProgressUpdateCliError(f"Data directory not found: {data_dir}")

    execution_artifacts, execution_availability, execution_warnings = _load_execution_artifacts(output_dir=output_dir)
    plan_artifacts, plan_availability, plan_warnings = _load_plan_artifacts(output_dir=output_dir)
    execution_plan = safe_dict(plan_artifacts.get("phase_b_data_extension_execution_plan"))
    if not execution_plan:
        raise PhaseBDataExtensionProgressUpdateCliError(
            f"Required execution plan not found or invalid: {Path(output_dir) / 'phase_b_data_extension_execution_plan.json'}"
        )
    window_semantics = safe_dict(execution_plan.get("oos_window_threshold_semantics"))

    metadata_df, metadata_warnings = _load_metadata_or_prices(data_dir=data_dir, metadata_file=metadata_file)
    segmentation_df, segmentation_warnings = _load_segmentation(output_dir=output_dir)
    v9_results, v9_warnings = _load_v9_results(output_dir=output_dir)
    limitations = dedupe([*execution_warnings, *plan_warnings, *metadata_warnings, *segmentation_warnings, *v9_warnings])

    primary_segment = _primary_segment(execution_artifacts)
    safe_segments = _safe_segments(execution_artifacts, output_dir=output_dir)
    methodology = _methodology(execution_artifacts)
    primary_trades, primary_trade_shares, _ = _primary_trade_lookup(v9_results=v9_results, primary_segment=primary_segment)
    working = _merge_ticker_context(
        metadata_df=metadata_df,
        segmentation_df=segmentation_df,
        primary_segment=primary_segment,
        safe_segments=safe_segments,
        methodology=methodology,
        primary_trades=primary_trades,
        primary_trade_shares=primary_trade_shares,
    )
    progress_tracker = _build_progress_tracker(
        working=working,
        artifacts=execution_artifacts,
        v9_results=v9_results,
        primary_segment=primary_segment,
        window_semantics=window_semantics,
    )

    baseline_tracker_path = Path(safe_dict(plan_artifacts.get("phase_b_data_extension_progress_tracker")).get("path") or Path(output_dir) / "phase_b_data_extension_progress_tracker.csv")
    baseline_lookup, baseline_warnings = _read_baseline_tracker(baseline_tracker_path)
    limitations = dedupe([*limitations, *baseline_warnings])

    refreshed_tracker = _refresh_progress_rows(progress_tracker=progress_tracker, baseline_lookup=baseline_lookup)
    tracker_lookup = _tracker_lookup(refreshed_tracker)
    batch_targets = _batch_targets(execution_plan=execution_plan)
    batch_state = _resolve_batch_state(batch_targets=batch_targets, tracker_lookup=tracker_lookup)

    metadata_segmentation_updated = _metadata_segmentation_refreshed(metadata_df=metadata_df, segmentation_df=segmentation_df)
    minimum_progress = safe_dict(execution_plan.get("minimum_progress_needed_before_recheck"))
    checkpoint_material_reached, remaining_blockers = _checkpoint_material_reached(
        tracker_lookup=tracker_lookup,
        metadata_segmentation_updated=metadata_segmentation_updated,
        minimum_progress=minimum_progress,
    )
    recheck_allowed = checkpoint_material_reached
    current_windows = _safe_float(
        safe_dict(tracker_lookup.get("usable_oos_windows_per_ticker")).get("current_value")
    )
    stretch_pending = [
        f"{batch_id} actual={current_windows} stretch_target>={_safe_float(target)}"
        for batch_id, target in list(safe_dict(window_semantics.get("stretch_target_windows_by_batch")).items())
        if current_windows < _safe_float(target)
    ]

    if batch_state["highest_completed_batch"] == "batch_1" and not checkpoint_material_reached:
        decisive_statement = "Batch-1 sudah tercapai tetapi checkpoint material belum cukup untuk refresh readiness blocker audit."
        recommended_next_action = "continue_batch_2_until_material_checkpoint_and_refresh_metadata_segmentation"
    elif not batch_state["completed_batches"]:
        decisive_statement = "Progress history naik, tetapi article-day recovery primary segment masih menahan batch."
        recommended_next_action = "keep_executing_batch_1_history_extension_and_primary_article_day_recovery"
    elif checkpoint_material_reached:
        decisive_statement = (
            "Checkpoint material operasional sudah tercapai di bawah threshold metodologi resmi. "
            "Gate readiness boleh dijalankan ulang hanya untuk refresh blocker status; strategy retry tetap tertutup."
        )
        recommended_next_action = "refresh_retest_gate_inputs_and_rerun_phase_b_retest_readiness_gate_for_status_only"
    else:
        decisive_statement = "Gate readiness belum boleh dijalankan ulang sampai blocker checkpoint material operasional selesai."
        recommended_next_action = "continue_current_batch_until_remaining_checkpoint_blockers_are_closed"

    progress_update = {
        "generated_at": _now_iso(),
        "current_batch": batch_state["current_batch"],
        "current_batch_completed": batch_state["current_batch_completed"],
        "batch_1_operationally_complete": _batch_operational_completion(batch_state, "batch_1"),
        "ready_for_batch_2": _batch_operational_completion(batch_state, "batch_1"),
        "next_batch_ready_to_start": batch_state["next_batch_ready_to_start"],
        "next_batch_id": batch_state["next_batch_id"],
        "highest_completed_batch": batch_state["highest_completed_batch"],
        "completed_batches": list(batch_state["completed_batches"]),
        "progress_since_baseline_v9": _progress_since_baseline_v9(tracker_lookup),
        "remaining_blockers": remaining_blockers,
        "checkpoint_material_reached": checkpoint_material_reached,
        "recheck_readiness_gate_allowed": recheck_allowed,
        "strategy_retry_still_blocked": True,
        "oos_window_threshold_semantics": window_semantics,
        "stretch_targets_pending": stretch_pending,
        "recommended_next_action": recommended_next_action,
        "decisive_statement": decisive_statement,
        "metadata_segmentation_updated": metadata_segmentation_updated,
        "artifact_availability": {**execution_availability, **plan_availability},
        "limitations": limitations,
    }

    recheck_status = {
        "current_batch": batch_state["current_batch"],
        "current_batch_completed": batch_state["current_batch_completed"],
        "batch_1_operationally_complete": _batch_operational_completion(batch_state, "batch_1"),
        "ready_for_batch_2": _batch_operational_completion(batch_state, "batch_1"),
        "checkpoint_material_reached": checkpoint_material_reached,
        "recheck_readiness_gate_allowed": recheck_allowed,
        "strategy_retry_still_blocked": True,
        "remaining_blockers": remaining_blockers,
        "recommended_next_action": recommended_next_action,
        "decisive_statement": decisive_statement,
        "oos_window_threshold_semantics": window_semantics,
        "stretch_targets_pending": stretch_pending,
    }

    batch_status_rows = [
        *_build_global_matrix_rows(refreshed_rows=refreshed_tracker),
        *_build_ticker_matrix_rows(working=working, batch_targets=batch_targets),
        *_build_segment_matrix_rows(
            working=working,
            primary_segment=primary_segment,
            safe_segments=safe_segments,
            batch_targets=batch_targets,
        ),
    ]

    _write_json(output_dir / PROGRESS_UPDATE_JSON_OUTPUT, progress_update)
    _write_text(output_dir / PROGRESS_UPDATE_TEXT_OUTPUT, _build_text_output(progress_update))
    _write_csv(output_dir / PROGRESS_REFRESHED_CSV_OUTPUT, refreshed_tracker, PROGRESS_COLUMNS)
    _write_csv(output_dir / BATCH_STATUS_MATRIX_OUTPUT, batch_status_rows, BATCH_MATRIX_COLUMNS)
    _write_json(output_dir / RECHECK_STATUS_OUTPUT, recheck_status)

    return {
        "phase_b_data_extension_progress_update": progress_update,
        "phase_b_recheck_readiness_status": recheck_status,
        "progress_tracker_refreshed": refreshed_tracker,
        "batch_status_matrix": batch_status_rows,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh Phase B data-extension batch progress.")
    parser.add_argument("--data-dir", default="data", help="Directory containing ticker CSV files.")
    parser.add_argument("--output-dir", default="output", help="Directory containing and receiving artifacts.")
    parser.add_argument("--metadata-file", default="data/ticker_metadata.csv", help="Optional ticker metadata CSV.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        result = run_phase_b_data_extension_progress_update(
            data_dir=Path(args.data_dir),
            output_dir=Path(args.output_dir),
            metadata_file=Path(args.metadata_file) if args.metadata_file else None,
        )
    except PhaseBDataExtensionProgressUpdateCliError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Unexpected error during data extension progress update: {exc}", file=sys.stderr)
        return 1

    payload = safe_dict(result.get("phase_b_data_extension_progress_update"))
    print("Phase B data extension progress update complete.")
    print(f"current_batch={payload.get('current_batch')}")
    print(f"current_batch_completed={payload.get('current_batch_completed')}")
    print(f"recheck_readiness_gate_allowed={payload.get('recheck_readiness_gate_allowed')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
