"""Audit batch-level data extension ingest quality before progress refresh is trusted."""

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
    _load_metadata_or_prices,
    _load_segmentation,
    _methodology,
    _parse_segment_spec,
    _primary_segment,
    _safe_segments,
    _usable_oos_windows,
)


INGEST_AUDIT_JSON_OUTPUT = "phase_b_data_extension_ingest_audit.json"
INGEST_AUDIT_TEXT_OUTPUT = "phase_b_data_extension_ingest_audit.txt"
INGEST_MATRIX_OUTPUT = "phase_b_data_extension_ingest_matrix.csv"
PRIORITY_TICKER_STATUS_OUTPUT = "phase_b_priority_ticker_ingest_status.csv"
INGEST_ACCEPTANCE_OUTPUT = "phase_b_ingest_acceptance_decision.json"

TRACKED_ARTIFACTS = [
    ("phase_b_data_extension_execution_plan", "phase_b_data_extension_execution_plan.json"),
    ("phase_b_data_extension_progress_update", "phase_b_data_extension_progress_update.json"),
    ("phase_b_recheck_trigger", "phase_b_recheck_trigger.json"),
    ("phase_b_recheck_readiness_status", "phase_b_recheck_readiness_status.json"),
    ("phase_b_retest_readiness_gate", "phase_b_retest_readiness_gate.json"),
]

MATRIX_COLUMNS = [
    "ticker",
    "batch_id",
    "batch_scope",
    "is_primary_segment",
    "history_rows_baseline",
    "history_rows_current",
    "history_rows_delta",
    "usable_oos_windows_baseline",
    "usable_oos_windows_current",
    "usable_oos_windows_delta",
    "news_count_total_baseline",
    "news_count_total_current",
    "news_count_total_delta",
    "article_days_baseline",
    "article_days_current",
    "article_days_delta",
    "duplicate_rows_detected",
    "date_continuity_ok",
    "missing_ohlcv_fields",
    "history_extension_progress_ok",
    "article_day_recovery_progress_ok",
    "metadata_ready",
    "segmentation_ready",
    "ingest_status",
    "ingest_reason",
]

PRIORITY_STATUS_COLUMNS = [
    "ticker",
    "batch_id",
    "is_primary_segment",
    "ingest_status",
    "history_rows_delta",
    "usable_oos_windows_delta",
    "article_days_delta",
    "metadata_ready",
    "segmentation_ready",
    "ingest_reason",
]


class PhaseBDataExtensionIngestAuditCliError(ValueError):
    """Friendly CLI error for data-extension ingest quality audit."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_str(value: object) -> str:
    return str(value or "").strip()


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


def _load_required_artifacts(output_dir: Path) -> Tuple[Dict[str, Dict[str, object]], Dict[str, bool], List[str]]:
    artifacts: Dict[str, Dict[str, object]] = {}
    availability: Dict[str, bool] = {}
    warnings: List[str] = []
    for artifact_id, filename in TRACKED_ARTIFACTS:
        payload, item_warnings, available = _load_optional_json(output_dir=output_dir, filename=filename)
        artifacts[artifact_id] = payload
        availability[artifact_id] = available
        warnings.extend(item_warnings)
    if not safe_dict(artifacts.get("phase_b_data_extension_execution_plan")):
        raise PhaseBDataExtensionIngestAuditCliError(
            f"Required execution plan not found or invalid: {Path(output_dir) / 'phase_b_data_extension_execution_plan.json'}"
        )
    if not safe_dict(artifacts.get("phase_b_data_extension_progress_update")):
        raise PhaseBDataExtensionIngestAuditCliError(
            f"Required progress update not found or invalid: {Path(output_dir) / 'phase_b_data_extension_progress_update.json'}"
        )
    return artifacts, availability, dedupe(warnings)


def _load_priority_baseline(output_dir: Path) -> Tuple[pd.DataFrame, List[str]]:
    path = Path(output_dir) / "phase_b_data_extension_priority_tickers.csv"
    if not path.exists():
        raise PhaseBDataExtensionIngestAuditCliError(f"Priority ticker baseline not found: {path}")
    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        raise PhaseBDataExtensionIngestAuditCliError(f"Failed to read {path}: {exc}") from exc
    if frame.empty or "ticker" not in frame.columns:
        raise PhaseBDataExtensionIngestAuditCliError(f"{path} does not contain usable priority ticker rows.")
    result = frame.copy()
    result["ticker"] = result["ticker"].astype(str).str.upper()
    return result, []


def _read_price_frame(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except Exception as exc:
        raise PhaseBDataExtensionIngestAuditCliError(f"Failed to read price file {path}: {exc}") from exc


def _metadata_lookup(metadata_df: pd.DataFrame) -> Dict[str, Dict[str, object]]:
    if metadata_df.empty or "ticker" not in metadata_df.columns:
        return {}
    return {
        str(row["ticker"]).upper(): dict(row)
        for _, row in metadata_df.drop_duplicates(subset=["ticker"], keep="first").iterrows()
    }


def _segmentation_lookup(segmentation_df: pd.DataFrame) -> Dict[str, Dict[str, object]]:
    if segmentation_df.empty or "ticker" not in segmentation_df.columns:
        return {}
    return {
        str(row["ticker"]).upper(): dict(row)
        for _, row in segmentation_df.drop_duplicates(subset=["ticker"], keep="first").iterrows()
    }


def _batch_priority_tickers(
    priority_baseline: pd.DataFrame,
    execution_plan: Dict[str, object],
    current_batch: str,
) -> List[str]:
    working = priority_baseline.copy()
    if current_batch == "batch_1":
        wave_mask = working["execution_wave"].astype(str).str.startswith("wave_1")
        scoped = working.loc[wave_mask].copy()
        if not scoped.empty:
            return scoped.sort_values(["priority_rank", "ticker"])["ticker"].astype(str).tolist()
    elif current_batch == "batch_2":
        wave_mask = working["execution_wave"].astype(str).str.startswith(("wave_1", "wave_2"))
        scoped = working.loc[wave_mask].copy()
        if not scoped.empty:
            return scoped.sort_values(["priority_rank", "ticker"])["ticker"].astype(str).tolist()
    return dedupe([_safe_str(item).upper() for item in list(execution_plan.get("priority_tickers") or [])]) or (
        working.sort_values(["priority_rank", "ticker"])["ticker"].astype(str).tolist()
    )


def _required_ohlcv_columns() -> List[str]:
    return ["date", "open", "high", "low", "close", "volume"]


def _evaluate_one_ticker(
    *,
    ticker: str,
    batch_id: str,
    baseline_row: Dict[str, object],
    price_frame: pd.DataFrame,
    methodology: Dict[str, int],
    primary_segment: str,
    metadata_row: Optional[Dict[str, object]],
    segmentation_row: Optional[Dict[str, object]],
) -> Dict[str, object]:
    required_cols = _required_ohlcv_columns()
    missing_fields = [column for column in required_cols if column not in price_frame.columns]

    working = price_frame.copy()
    duplicate_rows_detected = False
    date_continuity_ok = False
    if "date" in working.columns:
        parsed_dates = pd.to_datetime(working["date"], errors="coerce")
        duplicate_rows_detected = bool(parsed_dates.duplicated().any())
        date_continuity_ok = bool(parsed_dates.notna().all() and parsed_dates.is_monotonic_increasing and not duplicate_rows_detected)

    missing_ohlcv_values = False
    if not missing_fields:
        missing_ohlcv_values = bool(working[required_cols].isna().any().any())

    current_history_rows = int(len(working))
    current_article_series = (
        pd.to_numeric(working.get("sentiment_news_count_1d"), errors="coerce").fillna(0.0)
        if "sentiment_news_count_1d" in working.columns
        else pd.Series([0.0] * len(working))
    )
    current_article_days = int((current_article_series > 0).sum())
    current_news_count_total = int(float(current_article_series.sum()))
    current_windows = _usable_oos_windows(
        current_history_rows,
        _safe_int(methodology.get("warmup_bars"), 21),
        _safe_int(methodology.get("fold_size_bars"), 12),
    )

    baseline_history_rows = _safe_int(baseline_row.get("history_rows_current"))
    baseline_windows = _safe_int(baseline_row.get("usable_oos_windows_current"))
    baseline_article_days = _safe_int(baseline_row.get("article_days_current"))
    baseline_news_count_total = _safe_int(baseline_row.get("news_count_total_current"))

    history_rows_delta = current_history_rows - baseline_history_rows
    windows_delta = current_windows - baseline_windows
    article_days_delta = current_article_days - baseline_article_days
    news_count_total_delta = current_news_count_total - baseline_news_count_total

    primary_field, primary_value = _parse_segment_spec(primary_segment)
    is_primary_segment = bool(primary_field and segmentation_row and _safe_str(segmentation_row.get(primary_field)) == primary_value)

    metadata_ready = False
    if metadata_row is not None:
        metadata_ready = (
            _safe_int(metadata_row.get("history_rows", metadata_row.get("rows_1d"))) == current_history_rows
            and _safe_int(metadata_row.get("article_days", metadata_row.get("sentiment_days_with_articles"))) == current_article_days
            and _safe_int(metadata_row.get("news_count_total", metadata_row.get("sentiment_article_count_total"))) == current_news_count_total
        )

    segmentation_ready = False
    if segmentation_row is not None:
        segmentation_ready = (
            _safe_int(segmentation_row.get("history_rows", segmentation_row.get("rows"))) == current_history_rows
            and _safe_int(segmentation_row.get("article_days")) == current_article_days
            and _safe_int(segmentation_row.get("news_count_total", segmentation_row.get("article_count_total"))) == current_news_count_total
        )

    history_extension_progress_ok = bool(history_rows_delta > 0 and windows_delta > 0)
    article_day_recovery_progress_ok = bool(article_days_delta > 0) if is_primary_segment else bool(article_days_delta >= 0)

    reject_reasons: List[str] = []
    warning_reasons: List[str] = []
    if missing_fields:
        reject_reasons.append(f"missing_ohlcv_fields={','.join(missing_fields)}")
    if missing_ohlcv_values:
        reject_reasons.append("missing_ohlcv_values_detected")
    if duplicate_rows_detected:
        reject_reasons.append("duplicate_dates_detected")
    if not date_continuity_ok:
        reject_reasons.append("date_continuity_invalid")
    if not history_extension_progress_ok:
        reject_reasons.append("history_extension_did_not_increase_usable_coverage")

    if is_primary_segment and not article_day_recovery_progress_ok:
        warning_reasons.append("primary_article_day_recovery_not_visible")
    if news_count_total_delta > 0 and article_days_delta <= 0:
        warning_reasons.append("total_articles_up_but_article_day_coverage_flat")
    if not metadata_ready:
        warning_reasons.append("metadata_not_refreshed_to_current_snapshot")
    if not segmentation_ready:
        warning_reasons.append("segmentation_not_refreshed_to_current_snapshot")

    if reject_reasons:
        ingest_status = "rejected"
        ingest_reason = ";".join(dedupe(reject_reasons))
    elif warning_reasons:
        ingest_status = "accepted_with_warnings"
        ingest_reason = ";".join(dedupe(warning_reasons))
    else:
        ingest_status = "accepted"
        ingest_reason = "ingest_snapshot_valid_and_progress_visible"

    return {
        "ticker": ticker,
        "batch_id": batch_id,
        "batch_scope": "priority_ticker",
        "is_primary_segment": is_primary_segment,
        "history_rows_baseline": baseline_history_rows,
        "history_rows_current": current_history_rows,
        "history_rows_delta": history_rows_delta,
        "usable_oos_windows_baseline": baseline_windows,
        "usable_oos_windows_current": current_windows,
        "usable_oos_windows_delta": windows_delta,
        "news_count_total_baseline": baseline_news_count_total,
        "news_count_total_current": current_news_count_total,
        "news_count_total_delta": news_count_total_delta,
        "article_days_baseline": baseline_article_days,
        "article_days_current": current_article_days,
        "article_days_delta": article_days_delta,
        "duplicate_rows_detected": duplicate_rows_detected,
        "date_continuity_ok": date_continuity_ok,
        "missing_ohlcv_fields": "|".join(missing_fields),
        "history_extension_progress_ok": history_extension_progress_ok,
        "article_day_recovery_progress_ok": article_day_recovery_progress_ok,
        "metadata_ready": metadata_ready,
        "segmentation_ready": segmentation_ready,
        "ingest_status": ingest_status,
        "ingest_reason": ingest_reason,
    }


def _status_lists(rows: Sequence[Dict[str, object]]) -> Tuple[List[str], List[str], List[str]]:
    accepted = [str(row["ticker"]) for row in rows if _safe_str(row.get("ingest_status")) == "accepted"]
    rejected = [str(row["ticker"]) for row in rows if _safe_str(row.get("ingest_status")) == "rejected"]
    warnings = [str(row["ticker"]) for row in rows if _safe_str(row.get("ingest_status")) == "accepted_with_warnings"]
    return accepted, rejected, warnings


def _current_batch_targets(execution_plan: Dict[str, object], batch_id: str) -> Dict[str, object]:
    for item in list(execution_plan.get("execution_batches") or []):
        batch = safe_dict(item)
        if _safe_str(batch.get("batch_id")) == batch_id:
            return safe_dict(batch.get("targets"))
    return {}


def _batch_level_status(
    *,
    rows: Sequence[Dict[str, object]],
    batch_targets: Dict[str, object],
) -> Dict[str, object]:
    priority_rows = list(rows)
    primary_rows = [row for row in priority_rows if _safe_bool(row.get("is_primary_segment"))]
    history_extension_progress_ok = False
    article_day_recovery_progress_ok = False
    metadata_segmentation_update_ok = False

    if priority_rows:
        min_history = min(_safe_int(row.get("history_rows_current")) for row in priority_rows)
        min_windows = min(_safe_int(row.get("usable_oos_windows_current")) for row in priority_rows)
        history_extension_progress_ok = bool(
            min_history >= _safe_int(batch_targets.get("min_history_bars_per_ticker"))
            and min_windows >= _safe_int(batch_targets.get("usable_oos_windows_per_ticker"))
        )
        metadata_segmentation_update_ok = bool(
            all(_safe_bool(row.get("metadata_ready")) and _safe_bool(row.get("segmentation_ready")) for row in priority_rows)
        )

    if primary_rows:
        primary_total_articles = sum(_safe_int(row.get("news_count_total_current")) for row in primary_rows)
        primary_article_days_median = float(pd.Series([_safe_int(row.get("article_days_current")) for row in primary_rows]).median())
        article_day_recovery_progress_ok = bool(
            primary_total_articles >= _safe_int(batch_targets.get("primary_segment_total_articles"))
            and primary_article_days_median >= _safe_float(batch_targets.get("primary_segment_article_days_median"))
        )

    return {
        "history_extension_progress_ok": history_extension_progress_ok,
        "article_day_recovery_progress_ok": article_day_recovery_progress_ok,
        "metadata_segmentation_update_ok": metadata_segmentation_update_ok,
    }


def _acceptance_status(
    accepted_tickers: Sequence[str],
    rejected_tickers: Sequence[str],
    tickers_with_warnings: Sequence[str],
    batch_status: Dict[str, object],
) -> Tuple[str, str]:
    if not accepted_tickers and not tickers_with_warnings:
        return (
            "rejected",
            "reject_current_batch_ingest_until_history_extension_and_primary_article_day_recovery_show_usable_progress",
        )
    if rejected_tickers or tickers_with_warnings or not _safe_bool(batch_status.get("article_day_recovery_progress_ok")):
        return (
            "accepted_with_warnings",
            "accept_only_clean_ingest_rows_for_progress_but_keep_batch_open_until_primary_article_day_recovery_is_visible",
        )
    return (
        "accepted",
        "accept_batch_ingest_and_refresh_progress_tracker_from_clean_batch_snapshot",
    )


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


def _build_text_lines(acceptance: Dict[str, object]) -> List[str]:
    return [
        "Phase B Data Extension Ingest Audit",
        f"- batch_id={acceptance.get('batch_id')}",
        f"- ingest_audit_ready={acceptance.get('ingest_audit_ready')}",
        f"- batch_acceptance_status={acceptance.get('batch_acceptance_status')}",
        f"- article_day_recovery_progress_ok={acceptance.get('article_day_recovery_progress_ok')}",
        f"- history_extension_progress_ok={acceptance.get('history_extension_progress_ok')}",
        f"- metadata_segmentation_update_ok={acceptance.get('metadata_segmentation_update_ok')}",
        f"- recommended_next_action={acceptance.get('recommended_next_action')}",
        "",
        f"- accepted_tickers={', '.join(list(acceptance.get('accepted_tickers') or [])) or '-'}",
        f"- rejected_tickers={', '.join(list(acceptance.get('rejected_tickers') or [])) or '-'}",
        f"- tickers_with_warnings={', '.join(list(acceptance.get('tickers_with_warnings') or [])) or '-'}",
        "",
        f"- decisive_statement={acceptance.get('decisive_statement')}",
    ]


def run_phase_b_data_extension_ingest_audit(
    *,
    data_dir: Path,
    output_dir: Path,
    metadata_file: Optional[Path] = None,
) -> Dict[str, object]:
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    if not data_dir.exists():
        raise PhaseBDataExtensionIngestAuditCliError(f"Data directory not found: {data_dir}")

    artifacts, artifact_availability, artifact_warnings = _load_required_artifacts(output_dir=output_dir)
    priority_baseline, priority_warnings = _load_priority_baseline(output_dir=output_dir)
    metadata_df, metadata_warnings = _load_metadata_or_prices(data_dir=data_dir, metadata_file=metadata_file)
    segmentation_df, segmentation_warnings = _load_segmentation(output_dir=output_dir)
    limitations = dedupe([*artifact_warnings, *priority_warnings, *metadata_warnings, *segmentation_warnings])

    execution_plan = safe_dict(artifacts.get("phase_b_data_extension_execution_plan"))
    progress_update = safe_dict(artifacts.get("phase_b_data_extension_progress_update"))
    current_batch = _safe_str(progress_update.get("current_batch")) or "batch_1"
    primary_segment = _primary_segment(artifacts=artifacts)
    safe_segments = _safe_segments(artifacts=artifacts, output_dir=output_dir)
    methodology = _methodology(artifacts=artifacts)
    batch_targets = _current_batch_targets(execution_plan=execution_plan, batch_id=current_batch)

    metadata_by_ticker = _metadata_lookup(metadata_df=metadata_df)
    segmentation_by_ticker = _segmentation_lookup(segmentation_df=segmentation_df)
    priority_tickers = _batch_priority_tickers(
        priority_baseline=priority_baseline,
        execution_plan=execution_plan,
        current_batch=current_batch,
    )
    if not priority_tickers:
        raise PhaseBDataExtensionIngestAuditCliError("No priority tickers resolved for ingest audit.")

    baseline_lookup = {
        _safe_str(row.get("ticker")).upper(): dict(row)
        for _, row in priority_baseline.iterrows()
    }

    matrix_rows: List[Dict[str, object]] = []
    for ticker in priority_tickers:
        baseline_row = safe_dict(baseline_lookup.get(ticker))
        path = data_dir / f"{ticker}.csv"
        if not path.exists():
            matrix_rows.append(
                {
                    "ticker": ticker,
                    "batch_id": current_batch,
                    "batch_scope": "priority_ticker",
                    "is_primary_segment": False,
                    "history_rows_baseline": _safe_int(baseline_row.get("history_rows_current")),
                    "history_rows_current": 0,
                    "history_rows_delta": 0,
                    "usable_oos_windows_baseline": _safe_int(baseline_row.get("usable_oos_windows_current")),
                    "usable_oos_windows_current": 0,
                    "usable_oos_windows_delta": 0,
                    "news_count_total_baseline": _safe_int(baseline_row.get("news_count_total_current")),
                    "news_count_total_current": 0,
                    "news_count_total_delta": 0,
                    "article_days_baseline": _safe_int(baseline_row.get("article_days_current")),
                    "article_days_current": 0,
                    "article_days_delta": 0,
                    "duplicate_rows_detected": False,
                    "date_continuity_ok": False,
                    "missing_ohlcv_fields": "file_missing",
                    "history_extension_progress_ok": False,
                    "article_day_recovery_progress_ok": False,
                    "metadata_ready": False,
                    "segmentation_ready": False,
                    "ingest_status": "rejected",
                    "ingest_reason": "price_file_missing_for_priority_ticker",
                }
            )
            continue
        price_frame = _read_price_frame(path)
        matrix_rows.append(
            _evaluate_one_ticker(
                ticker=ticker,
                batch_id=current_batch,
                baseline_row=baseline_row,
                price_frame=price_frame,
                methodology=methodology,
                primary_segment=primary_segment,
                metadata_row=metadata_by_ticker.get(ticker),
                segmentation_row=segmentation_by_ticker.get(ticker),
            )
        )

    accepted_tickers, rejected_tickers, tickers_with_warnings = _status_lists(matrix_rows)
    batch_status = _batch_level_status(rows=matrix_rows, batch_targets=batch_targets)
    batch_acceptance_status, recommended_next_action = _acceptance_status(
        accepted_tickers=accepted_tickers,
        rejected_tickers=rejected_tickers,
        tickers_with_warnings=tickers_with_warnings,
        batch_status=batch_status,
    )

    if batch_acceptance_status == "rejected":
        decisive_statement = (
            "Batch-1 ingest belum layak diterima karena history extension belum benar-benar menambah usable coverage."
            if not _safe_bool(batch_status.get("history_extension_progress_ok"))
            else "Progress update hanya boleh dihitung dari ingest yang lolos audit kualitas."
        )
    elif not _safe_bool(batch_status.get("article_day_recovery_progress_ok")):
        decisive_statement = "Article-day recovery primary segment belum nyata walau total artikel bertambah."
    else:
        decisive_statement = "Progress update hanya boleh dihitung dari ingest yang lolos audit kualitas."

    acceptance = {
        "generated_at": _now_iso(),
        "batch_id": current_batch,
        "ingest_audit_ready": True,
        "batch_acceptance_status": batch_acceptance_status,
        "accepted_tickers": accepted_tickers,
        "rejected_tickers": rejected_tickers,
        "tickers_with_warnings": tickers_with_warnings,
        "article_day_recovery_progress_ok": _safe_bool(batch_status.get("article_day_recovery_progress_ok")),
        "history_extension_progress_ok": _safe_bool(batch_status.get("history_extension_progress_ok")),
        "metadata_segmentation_update_ok": _safe_bool(batch_status.get("metadata_segmentation_update_ok")),
        "recommended_next_action": recommended_next_action,
        "priority_tickers_audited": priority_tickers,
        "primary_segment": primary_segment,
        "safe_segments": safe_segments,
        "artifact_availability": artifact_availability,
        "limitations": limitations,
        "decisive_statement": decisive_statement,
    }

    audit_payload = {
        "generated_at": _now_iso(),
        "context": {
            "current_batch": current_batch,
            "current_batch_completed": progress_update.get("current_batch_completed"),
            "checkpoint_material_reached": progress_update.get("checkpoint_material_reached"),
            "recheck_readiness_gate_allowed": progress_update.get("recheck_readiness_gate_allowed"),
            "priority_tickers_audited": priority_tickers,
            "primary_segment": primary_segment,
        },
        "methodology": {
            "accepted_definition": "valid_ohlcv_and_date_integrity_with_visible_history_extension_and_usable_oos_coverage_gain",
            "warning_definition": "history_extension_is_visible_but_article_day_or_metadata_segmentation_recovery_is_not_fully_ready",
            "rejected_definition": "broken_snapshot_or_no_usable_history_extension_progress",
            "warmup_bars": _safe_int(methodology.get("warmup_bars"), 21),
            "fold_size_bars": _safe_int(methodology.get("fold_size_bars"), 12),
        },
        "matrix_row_count": len(matrix_rows),
        "batch_targets": batch_targets,
        "acceptance": acceptance,
    }

    text_lines = _build_text_lines(acceptance)
    results_path = output_dir / INGEST_MATRIX_OUTPUT
    priority_path = output_dir / PRIORITY_TICKER_STATUS_OUTPUT
    audit_json_path = output_dir / INGEST_AUDIT_JSON_OUTPUT
    audit_txt_path = output_dir / INGEST_AUDIT_TEXT_OUTPUT
    acceptance_path = output_dir / INGEST_ACCEPTANCE_OUTPUT

    _write_json(audit_json_path, audit_payload)
    _write_text(audit_txt_path, text_lines)
    _write_csv(results_path, matrix_rows, MATRIX_COLUMNS)
    _write_csv(priority_path, matrix_rows, PRIORITY_STATUS_COLUMNS)
    _write_json(acceptance_path, acceptance)

    return {
        "phase_b_data_extension_ingest_audit": audit_payload,
        "phase_b_ingest_acceptance_decision": acceptance,
        "phase_b_data_extension_ingest_matrix": matrix_rows,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit batch-level data extension ingest quality before progress refresh.")
    parser.add_argument("--data-dir", default="data", help="Directory containing ticker CSV files.")
    parser.add_argument("--output-dir", default="output", help="Directory containing and receiving artifacts.")
    parser.add_argument("--metadata-file", default="data/ticker_metadata.csv", help="Optional ticker metadata CSV.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        result = run_phase_b_data_extension_ingest_audit(
            data_dir=Path(args.data_dir),
            output_dir=Path(args.output_dir),
            metadata_file=Path(args.metadata_file) if args.metadata_file else None,
        )
    except PhaseBDataExtensionIngestAuditCliError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Unexpected error during ingest audit: {exc}", file=sys.stderr)
        return 1

    payload = safe_dict(result.get("phase_b_ingest_acceptance_decision"))
    print("Phase B data extension ingest audit complete.")
    print(f"batch_id={payload.get('batch_id')}")
    print(f"batch_acceptance_status={payload.get('batch_acceptance_status')}")
    print(f"recommended_next_action={payload.get('recommended_next_action')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
