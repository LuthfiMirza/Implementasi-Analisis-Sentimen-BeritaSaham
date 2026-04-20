"""Analyze why a batch data-extension ingest was rejected or not yet sufficient."""

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


ANALYSIS_JSON_OUTPUT = "phase_b_data_extension_ingest_rejection_analysis.json"
ANALYSIS_TEXT_OUTPUT = "phase_b_data_extension_ingest_rejection_analysis.txt"
CHECKLIST_CSV_OUTPUT = "phase_b_data_extension_ingest_priority_checklist.csv"
DIAGNOSTICS_CSV_OUTPUT = "phase_b_data_extension_ingest_ticker_diagnostics.csv"
GO_NO_GO_OUTPUT = "phase_b_data_extension_ingest_go_no_go.json"

DECISION_VALUES = {
    "ingest_rejected_no_material_progress",
    "ingest_accepted_but_batch_not_complete",
    "ingest_accepted_batch_1_complete",
}
CHECKLIST_COLUMNS = [
    "check_id",
    "check_scope",
    "required_for_valid_progress",
    "baseline_value",
    "current_value",
    "target_or_rule",
    "status",
    "note",
]
DIAGNOSTIC_COLUMNS = [
    "ticker",
    "priority_rank",
    "ingest_status",
    "file_change_detected",
    "history_progress_valid",
    "article_day_progress_valid",
    "metadata_refresh_valid",
    "segmentation_refresh_valid",
    "progress_classification",
    "root_cause",
    "history_rows_delta",
    "usable_oos_windows_delta",
    "article_days_delta",
    "news_count_total_delta",
]


class PhaseBDataExtensionIngestRejectionAnalysisCliError(ValueError):
    """Friendly CLI error for ingest rejection analysis."""


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


def _load_required_json(output_dir: Path, filename: str) -> Dict[str, object]:
    payload, _, available = _load_optional_json(output_dir=output_dir, filename=filename)
    if not available or not payload:
        raise PhaseBDataExtensionIngestRejectionAnalysisCliError(
            f"Required artifact not found or invalid: {Path(output_dir) / filename}"
        )
    return payload


def _load_required_csv(output_dir: Path, filename: str) -> pd.DataFrame:
    path = Path(output_dir) / filename
    if not path.exists():
        raise PhaseBDataExtensionIngestRejectionAnalysisCliError(f"Required artifact not found: {path}")
    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        raise PhaseBDataExtensionIngestRejectionAnalysisCliError(f"Failed to read {path}: {exc}") from exc
    if frame.empty:
        raise PhaseBDataExtensionIngestRejectionAnalysisCliError(f"{path} is empty.")
    return frame


def _priority_baseline_lookup(frame: pd.DataFrame) -> Dict[str, Dict[str, object]]:
    working = frame.copy()
    working["ticker"] = working["ticker"].astype(str).str.upper()
    return {
        str(row["ticker"]).upper(): dict(row)
        for _, row in working.drop_duplicates(subset=["ticker"], keep="first").iterrows()
    }


def _aggregate_progress(matrix_df: pd.DataFrame) -> Dict[str, object]:
    working = matrix_df.copy()
    working["is_primary_segment"] = working["is_primary_segment"].fillna(False).astype(bool)

    baseline_min_history = float(pd.to_numeric(working["history_rows_baseline"], errors="coerce").fillna(0).min())
    current_min_history = float(pd.to_numeric(working["history_rows_current"], errors="coerce").fillna(0).min())
    baseline_min_windows = float(pd.to_numeric(working["usable_oos_windows_baseline"], errors="coerce").fillna(0).min())
    current_min_windows = float(pd.to_numeric(working["usable_oos_windows_current"], errors="coerce").fillna(0).min())

    primary = working.loc[working["is_primary_segment"]].copy()
    baseline_primary_articles = float(pd.to_numeric(primary["news_count_total_baseline"], errors="coerce").fillna(0).sum()) if not primary.empty else 0.0
    current_primary_articles = float(pd.to_numeric(primary["news_count_total_current"], errors="coerce").fillna(0).sum()) if not primary.empty else 0.0
    baseline_primary_article_days_median = float(pd.to_numeric(primary["article_days_baseline"], errors="coerce").fillna(0).median()) if not primary.empty else 0.0
    current_primary_article_days_median = float(pd.to_numeric(primary["article_days_current"], errors="coerce").fillna(0).median()) if not primary.empty else 0.0

    file_change_detected = bool(
        (
            pd.to_numeric(working["history_rows_delta"], errors="coerce").fillna(0).ne(0)
            | pd.to_numeric(working["usable_oos_windows_delta"], errors="coerce").fillna(0).ne(0)
            | pd.to_numeric(working["article_days_delta"], errors="coerce").fillna(0).ne(0)
            | pd.to_numeric(working["news_count_total_delta"], errors="coerce").fillna(0).ne(0)
        ).any()
    )
    history_progress_valid = bool(current_min_history > baseline_min_history and current_min_windows > baseline_min_windows)
    metadata_refresh_valid = bool(working["metadata_ready"].fillna(False).astype(bool).all())
    segmentation_refresh_valid = bool(working["segmentation_ready"].fillna(False).astype(bool).all())
    primary_article_day_recovery_valid = bool(
        current_primary_articles > baseline_primary_articles and current_primary_article_days_median > baseline_primary_article_days_median
    )

    return {
        "file_change_detected": file_change_detected,
        "baseline_min_history": baseline_min_history,
        "current_min_history": current_min_history,
        "baseline_min_windows": baseline_min_windows,
        "current_min_windows": current_min_windows,
        "history_progress_valid": history_progress_valid,
        "metadata_refresh_valid": metadata_refresh_valid,
        "segmentation_refresh_valid": segmentation_refresh_valid,
        "baseline_primary_articles": baseline_primary_articles,
        "current_primary_articles": current_primary_articles,
        "baseline_primary_article_days_median": baseline_primary_article_days_median,
        "current_primary_article_days_median": current_primary_article_days_median,
        "primary_article_day_recovery_valid": primary_article_day_recovery_valid,
    }


def _batch_1_targets(execution_plan: Dict[str, object]) -> Dict[str, object]:
    for item in list(execution_plan.get("execution_batches") or []):
        batch = safe_dict(item)
        if _safe_str(batch.get("batch_id")) == "batch_1":
            return safe_dict(batch.get("targets"))
    return {}


def _batch_1_closure_valid(aggregates: Dict[str, object], batch_targets: Dict[str, object]) -> bool:
    if not batch_targets:
        return False
    return bool(
        _safe_float(aggregates.get("current_min_history")) >= _safe_float(batch_targets.get("min_history_bars_per_ticker"))
        and _safe_float(aggregates.get("current_min_windows")) >= _safe_float(batch_targets.get("usable_oos_windows_per_ticker"))
        and _safe_float(aggregates.get("current_primary_articles")) >= _safe_float(batch_targets.get("primary_segment_total_articles"))
        and _safe_float(aggregates.get("current_primary_article_days_median")) >= _safe_float(batch_targets.get("primary_segment_article_days_median"))
    )


def _diagnostic_row(row: Dict[str, object], baseline_lookup: Dict[str, Dict[str, object]]) -> Dict[str, object]:
    ticker = _safe_str(row.get("ticker")).upper()
    baseline = safe_dict(baseline_lookup.get(ticker))
    file_change_detected = bool(
        _safe_int(row.get("history_rows_delta")) != 0
        or _safe_int(row.get("usable_oos_windows_delta")) != 0
        or _safe_int(row.get("article_days_delta")) != 0
        or _safe_int(row.get("news_count_total_delta")) != 0
    )
    history_progress_valid = bool(
        _safe_int(row.get("history_rows_delta")) > 0 and _safe_int(row.get("usable_oos_windows_delta")) > 0
    )
    article_day_progress_valid = bool(_safe_bool(row.get("is_primary_segment")) and _safe_int(row.get("article_days_delta")) > 0) or (
        not _safe_bool(row.get("is_primary_segment"))
    )
    metadata_refresh_valid = _safe_bool(row.get("metadata_ready"))
    segmentation_refresh_valid = _safe_bool(row.get("segmentation_ready"))

    if not file_change_detected:
        progress_classification = "file_unchanged_no_progress"
        root_cause = "no_material_snapshot_change_detected"
    elif not history_progress_valid:
        progress_classification = "file_changed_but_progress_not_valid"
        root_cause = "history_effective_not_increasing"
    elif _safe_bool(row.get("is_primary_segment")) and not article_day_progress_valid:
        progress_classification = "progress_valid_but_not_enough"
        root_cause = "primary_article_day_recovery_not_visible"
    elif not metadata_refresh_valid:
        progress_classification = "progress_valid_but_not_enough"
        root_cause = "metadata_not_synchronized"
    elif not segmentation_refresh_valid:
        progress_classification = "progress_valid_but_not_enough"
        root_cause = "segmentation_not_synchronized"
    else:
        progress_classification = "progress_valid_and_batch_can_move"
        root_cause = "ticker_level_ingest_ready"

    return {
        "ticker": ticker,
        "priority_rank": _safe_int(baseline.get("priority_rank"), 0),
        "ingest_status": _safe_str(row.get("ingest_status")),
        "file_change_detected": file_change_detected,
        "history_progress_valid": history_progress_valid,
        "article_day_progress_valid": article_day_progress_valid,
        "metadata_refresh_valid": metadata_refresh_valid,
        "segmentation_refresh_valid": segmentation_refresh_valid,
        "progress_classification": progress_classification,
        "root_cause": root_cause,
        "history_rows_delta": _safe_int(row.get("history_rows_delta")),
        "usable_oos_windows_delta": _safe_int(row.get("usable_oos_windows_delta")),
        "article_days_delta": _safe_int(row.get("article_days_delta")),
        "news_count_total_delta": _safe_int(row.get("news_count_total_delta")),
    }


def _checklist_rows(
    aggregates: Dict[str, object],
    batch_targets: Dict[str, object],
    metadata_refresh_valid: bool,
    segmentation_refresh_valid: bool,
) -> List[Dict[str, object]]:
    return [
        {
            "check_id": "priority_files_materially_changed",
            "check_scope": "batch_1_priority",
            "required_for_valid_progress": True,
            "baseline_value": False,
            "current_value": aggregates["file_change_detected"],
            "target_or_rule": "at_least_one_priority_ticker_delta_nonzero",
            "status": "pass" if aggregates["file_change_detected"] else "fail",
            "note": "File data berubah belum cukup, tapi ini syarat minimal agar ada progres yang bisa dievaluasi.",
        },
        {
            "check_id": "history_effective_increase",
            "check_scope": "batch_1_priority",
            "required_for_valid_progress": True,
            "baseline_value": f"min_history={aggregates['baseline_min_history']}, min_windows={aggregates['baseline_min_windows']}",
            "current_value": f"min_history={aggregates['current_min_history']}, min_windows={aggregates['current_min_windows']}",
            "target_or_rule": "current_min_history > baseline_min_history and current_min_windows > baseline_min_windows",
            "status": "pass" if aggregates["history_progress_valid"] else "fail",
            "note": "Batch-1 baru bergerak sah jika history efektif dan usable OOS coverage sama-sama naik.",
        },
        {
            "check_id": "metadata_refresh_sync",
            "check_scope": "batch_1_priority",
            "required_for_valid_progress": True,
            "baseline_value": False,
            "current_value": metadata_refresh_valid,
            "target_or_rule": "all_priority_tickers_metadata_ready = true",
            "status": "pass" if metadata_refresh_valid else "fail",
            "note": "Progress update tidak boleh dianggap valid sebelum metadata sinkron dengan data terbaru.",
        },
        {
            "check_id": "segmentation_refresh_sync",
            "check_scope": "batch_1_priority",
            "required_for_valid_progress": True,
            "baseline_value": False,
            "current_value": segmentation_refresh_valid,
            "target_or_rule": "all_priority_tickers_segmentation_ready = true",
            "status": "pass" if segmentation_refresh_valid else "fail",
            "note": "Progress update tidak boleh dianggap valid sebelum segmentation sinkron dengan data terbaru.",
        },
        {
            "check_id": "primary_article_day_recovery",
            "check_scope": "primary_segment",
            "required_for_valid_progress": True,
            "baseline_value": f"articles={aggregates['baseline_primary_articles']}, median_article_days={aggregates['baseline_primary_article_days_median']}",
            "current_value": f"articles={aggregates['current_primary_articles']}, median_article_days={aggregates['current_primary_article_days_median']}",
            "target_or_rule": "current_articles > baseline_articles and current_median_article_days > baseline_median_article_days",
            "status": "pass" if aggregates["primary_article_day_recovery_valid"] else "fail",
            "note": "Primary article-day recovery harus benar-benar naik, bukan hanya total artikel mentah.",
        },
        {
            "check_id": "batch_1_closure",
            "check_scope": "batch_1_priority",
            "required_for_valid_progress": False,
            "baseline_value": "not_closed",
            "current_value": {
                "min_history_bars_per_ticker": aggregates["current_min_history"],
                "usable_oos_windows_per_ticker": aggregates["current_min_windows"],
                "primary_segment_total_articles": aggregates["current_primary_articles"],
                "primary_segment_article_days_median": aggregates["current_primary_article_days_median"],
            },
            "target_or_rule": batch_targets,
            "status": "pass" if _batch_1_closure_valid(aggregates, batch_targets) else "fail",
            "note": "Check ini menentukan apakah batch_1 sudah cukup ditutup, bukan sekadar bergerak.",
        },
    ]


def _highest_blocking_issue(
    aggregates: Dict[str, object],
    metadata_refresh_valid: bool,
    segmentation_refresh_valid: bool,
    batch_1_closure_progress_valid: bool,
) -> str:
    if not aggregates["history_progress_valid"]:
        return "history_effective_not_increasing"
    if not aggregates["primary_article_day_recovery_valid"]:
        return "primary_article_day_recovery_not_material"
    if not metadata_refresh_valid:
        return "metadata_not_synchronized"
    if not segmentation_refresh_valid:
        return "segmentation_not_synchronized"
    if not batch_1_closure_progress_valid:
        return "batch_1_targets_not_yet_closed"
    return "none"


def _decision(
    *,
    aggregates: Dict[str, object],
    metadata_refresh_valid: bool,
    segmentation_refresh_valid: bool,
    batch_1_closure_progress_valid: bool,
) -> Tuple[str, str]:
    material_progress_detected = bool(aggregates["file_change_detected"] and aggregates["history_progress_valid"])
    if not material_progress_detected:
        return (
            "ingest_rejected_no_material_progress",
            "File data berubah, tetapi progress batch belum sah karena history efektif tidak naik.",
        )
    if batch_1_closure_progress_valid and metadata_refresh_valid and segmentation_refresh_valid and aggregates["primary_article_day_recovery_valid"]:
        return (
            "ingest_accepted_batch_1_complete",
            "Batch-1 baru boleh dianggap bergerak jika history dan article-day primary sama-sama naik.",
        )
    if not aggregates["primary_article_day_recovery_valid"]:
        return (
            "ingest_accepted_but_batch_not_complete",
            "Ingest masih ditolak sebagai penutup batch karena primary article-day recovery belum bergerak material.",
        )
    return (
        "ingest_accepted_but_batch_not_complete",
        "Progress update tidak boleh dianggap valid sebelum metadata dan segmentation sinkron dengan data terbaru.",
    )


def _recommended_next_action(decision: str, highest_blocking_issue: str) -> str:
    if decision == "ingest_rejected_no_material_progress":
        return "extend_history_rows_and_reingest_priority_tickers_before_refreshing_progress"
    if highest_blocking_issue == "primary_article_day_recovery_not_material":
        return "keep_valid_history_extension_but_raise_primary_segment_article_day_coverage_before_batch_closure"
    if highest_blocking_issue in {"metadata_not_synchronized", "segmentation_not_synchronized"}:
        return "synchronize_metadata_and_segmentation_with_latest_data_snapshot_before_progress_refresh"
    if decision == "ingest_accepted_batch_1_complete":
        return "refresh_progress_update_and_mark_batch_1_ready_for_next_batch_transition"
    return "keep_batch_1_open_and_close_remaining_targets_before_any_recheck"


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


def _build_text_lines(go_no_go: Dict[str, object]) -> List[str]:
    return [
        "Phase B Data Extension Ingest Rejection Analysis",
        f"- decision={go_no_go.get('decision')}",
        f"- material_progress_detected={go_no_go.get('material_progress_detected')}",
        f"- history_progress_valid={go_no_go.get('history_progress_valid')}",
        f"- metadata_refresh_valid={go_no_go.get('metadata_refresh_valid')}",
        f"- segmentation_refresh_valid={go_no_go.get('segmentation_refresh_valid')}",
        f"- primary_article_day_recovery_valid={go_no_go.get('primary_article_day_recovery_valid')}",
        f"- batch_1_closure_progress_valid={go_no_go.get('batch_1_closure_progress_valid')}",
        f"- highest_blocking_issue={go_no_go.get('highest_blocking_issue')}",
        f"- recommended_next_action={go_no_go.get('recommended_next_action')}",
        "",
        f"- decisive_statement={go_no_go.get('decisive_statement')}",
    ]


def run_phase_b_data_extension_ingest_rejection_analysis(
    *,
    data_dir: Path,
    output_dir: Path,
    metadata_file: Optional[Path] = None,
) -> Dict[str, object]:
    del data_dir, metadata_file  # analysis reads frozen artifacts rather than recomputing snapshot logic
    output_dir = Path(output_dir)

    execution_plan = _load_required_json(output_dir=output_dir, filename="phase_b_data_extension_execution_plan.json")
    progress_update = _load_required_json(output_dir=output_dir, filename="phase_b_data_extension_progress_update.json")
    ingest_audit = _load_required_json(output_dir=output_dir, filename="phase_b_data_extension_ingest_audit.json")
    ingest_acceptance = _load_required_json(output_dir=output_dir, filename="phase_b_ingest_acceptance_decision.json")
    ingest_matrix = _load_required_csv(output_dir=output_dir, filename="phase_b_data_extension_ingest_matrix.csv")
    priority_baseline = _load_required_csv(output_dir=output_dir, filename="phase_b_data_extension_priority_tickers.csv")

    limitations = dedupe(list(ingest_acceptance.get("limitations") or []) + list(progress_update.get("limitations") or []))
    baseline_lookup = _priority_baseline_lookup(priority_baseline)
    aggregate = _aggregate_progress(ingest_matrix)
    metadata_refresh_valid = bool(aggregate["metadata_refresh_valid"])
    segmentation_refresh_valid = bool(aggregate["segmentation_refresh_valid"])
    batch_targets = _batch_1_targets(execution_plan=execution_plan)
    batch_1_closure_progress_valid = _batch_1_closure_valid(aggregate, batch_targets)

    diagnostics = [
        _diagnostic_row(row=dict(record), baseline_lookup=baseline_lookup)
        for _, record in ingest_matrix.iterrows()
    ]
    diagnostics.sort(key=lambda item: (item["priority_rank"] if item["priority_rank"] else 999, item["ticker"]))

    checklist = _checklist_rows(
        aggregates=aggregate,
        batch_targets=batch_targets,
        metadata_refresh_valid=metadata_refresh_valid,
        segmentation_refresh_valid=segmentation_refresh_valid,
    )

    decision, decisive_statement = _decision(
        aggregates=aggregate,
        metadata_refresh_valid=metadata_refresh_valid,
        segmentation_refresh_valid=segmentation_refresh_valid,
        batch_1_closure_progress_valid=batch_1_closure_progress_valid,
    )
    highest_blocking_issue = _highest_blocking_issue(
        aggregates=aggregate,
        metadata_refresh_valid=metadata_refresh_valid,
        segmentation_refresh_valid=segmentation_refresh_valid,
        batch_1_closure_progress_valid=batch_1_closure_progress_valid,
    )
    material_progress_detected = bool(aggregate["file_change_detected"] and aggregate["history_progress_valid"])

    go_no_go = {
        "generated_at": _now_iso(),
        "decision": decision,
        "material_progress_detected": material_progress_detected,
        "history_progress_valid": bool(aggregate["history_progress_valid"]),
        "metadata_refresh_valid": metadata_refresh_valid,
        "segmentation_refresh_valid": segmentation_refresh_valid,
        "primary_article_day_recovery_valid": bool(aggregate["primary_article_day_recovery_valid"]),
        "batch_1_closure_progress_valid": batch_1_closure_progress_valid,
        "highest_blocking_issue": highest_blocking_issue,
        "recommended_next_action": _recommended_next_action(decision=decision, highest_blocking_issue=highest_blocking_issue),
        "current_batch": progress_update.get("current_batch"),
        "batch_acceptance_status": ingest_acceptance.get("batch_acceptance_status"),
        "accepted_tickers": list(ingest_acceptance.get("accepted_tickers") or []),
        "rejected_tickers": list(ingest_acceptance.get("rejected_tickers") or []),
        "tickers_with_warnings": list(ingest_acceptance.get("tickers_with_warnings") or []),
        "decisive_statement": decisive_statement,
        "limitations": limitations,
    }
    if go_no_go["decision"] not in DECISION_VALUES:
        raise PhaseBDataExtensionIngestRejectionAnalysisCliError("Decision must remain explicit and non-ambiguous.")

    analysis = {
        "generated_at": _now_iso(),
        "context": {
            "phase_b_status": "phase_b_closed_with_learnings_no_candidate",
            "current_batch": progress_update.get("current_batch"),
            "current_batch_completed": progress_update.get("current_batch_completed"),
            "checkpoint_material_reached": progress_update.get("checkpoint_material_reached"),
            "recheck_readiness_gate_allowed": progress_update.get("recheck_readiness_gate_allowed"),
            "batch_acceptance_status": ingest_acceptance.get("batch_acceptance_status"),
        },
        "batch_1_targets": batch_targets,
        "aggregate_progress": aggregate,
        "go_no_go": go_no_go,
        "diagnostic_row_count": len(diagnostics),
        "checklist_row_count": len(checklist),
        "limitations": limitations,
    }

    _write_json(output_dir / ANALYSIS_JSON_OUTPUT, analysis)
    _write_text(output_dir / ANALYSIS_TEXT_OUTPUT, _build_text_lines(go_no_go))
    _write_csv(output_dir / CHECKLIST_CSV_OUTPUT, checklist, CHECKLIST_COLUMNS)
    _write_csv(output_dir / DIAGNOSTICS_CSV_OUTPUT, diagnostics, DIAGNOSTIC_COLUMNS)
    _write_json(output_dir / GO_NO_GO_OUTPUT, go_no_go)

    return {
        "phase_b_data_extension_ingest_rejection_analysis": analysis,
        "phase_b_data_extension_ingest_go_no_go": go_no_go,
        "phase_b_data_extension_ingest_priority_checklist": checklist,
        "phase_b_data_extension_ingest_ticker_diagnostics": diagnostics,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze why Phase B data-extension ingest was rejected or not yet sufficient.")
    parser.add_argument("--data-dir", default="data", help="Unused compatibility argument; analysis reads frozen artifacts.")
    parser.add_argument("--output-dir", default="output", help="Directory containing and receiving artifacts.")
    parser.add_argument("--metadata-file", default="data/ticker_metadata.csv", help="Unused compatibility argument.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        result = run_phase_b_data_extension_ingest_rejection_analysis(
            data_dir=Path(args.data_dir),
            output_dir=Path(args.output_dir),
            metadata_file=Path(args.metadata_file) if args.metadata_file else None,
        )
    except PhaseBDataExtensionIngestRejectionAnalysisCliError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Unexpected error during ingest rejection analysis: {exc}", file=sys.stderr)
        return 1

    payload = safe_dict(result.get("phase_b_data_extension_ingest_go_no_go"))
    print("Phase B data extension ingest rejection analysis complete.")
    print(f"decision={payload.get('decision')}")
    print(f"highest_blocking_issue={payload.get('highest_blocking_issue')}")
    print(f"recommended_next_action={payload.get('recommended_next_action')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
