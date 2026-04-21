"""Rerun official ingest/progress runners after backfill and summarize Phase B batch-1 status."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.phase_a_transition_utils import dedupe, read_json_object, safe_dict  # noqa: E402
from quant.run_phase_b_data_extension_ingest_audit import run_phase_b_data_extension_ingest_audit  # noqa: E402
from quant.run_phase_b_data_extension_progress_update import run_phase_b_data_extension_progress_update  # noqa: E402


POST_BACKFILL_INGEST_JSON_OUTPUT = "phase_b_post_backfill_ingest_audit.json"
POST_BACKFILL_INGEST_TEXT_OUTPUT = "phase_b_post_backfill_ingest_audit.txt"
POST_BACKFILL_PROGRESS_JSON_OUTPUT = "phase_b_post_backfill_progress_update.json"
POST_BACKFILL_PROGRESS_TEXT_OUTPUT = "phase_b_post_backfill_progress_update.txt"
POST_BACKFILL_DECISION_JSON_OUTPUT = "phase_b_post_backfill_batch1_decision.json"

BATCH_1_STATUSES = {
    "batch_1_not_started_snapshot_still_static",
    "batch_1_started_but_not_complete",
    "batch_1_complete_but_checkpoint_not_material",
    "batch_1_complete_and_checkpoint_material_reached",
}


class PhaseBPostBackfillBatchVerificationCliError(ValueError):
    """Friendly CLI error for post-backfill batch verification."""


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


def _priority_matrix_rows(ingest_result: Dict[str, object]) -> List[Dict[str, object]]:
    rows = list(ingest_result.get("phase_b_data_extension_ingest_matrix") or [])
    return [safe_dict(row) for row in rows if _safe_str(safe_dict(row).get("batch_scope")) == "priority_ticker"]


def _bool_from_priority_rows(rows: Sequence[Dict[str, object]], field: str) -> bool:
    return any(_safe_bool(row.get(field)) for row in rows)


def _primary_rows(rows: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    return [row for row in rows if _safe_bool(row.get("is_primary_segment"))]


def _remaining_blockers(progress_payload: Dict[str, object], ingest_payload: Dict[str, object]) -> List[str]:
    blockers = [str(item) for item in list(progress_payload.get("remaining_blockers") or []) if _safe_str(item)]
    if _safe_bool(progress_payload.get("checkpoint_material_reached")):
        return dedupe(blockers)
    if not _safe_bool(ingest_payload.get("history_extension_progress_ok")):
        blockers.append("history_extension_progress_ok=false")
    if not _safe_bool(ingest_payload.get("article_day_recovery_progress_ok")):
        blockers.append("primary_article_day_recovery_progress_ok=false")
    if not _safe_bool(ingest_payload.get("metadata_segmentation_update_ok")):
        blockers.append("metadata_segmentation_update_ok=false")
    return dedupe(blockers)


def _load_execution_plan(output_dir: Path) -> Dict[str, object]:
    payload, warnings = read_json_object(Path(output_dir) / "phase_b_data_extension_execution_plan.json", "phase_b_data_extension_execution_plan.json")
    if payload is None:
        raise PhaseBPostBackfillBatchVerificationCliError(
            f"Required execution plan missing or invalid: {Path(output_dir) / 'phase_b_data_extension_execution_plan.json'}"
            + (f" ({'; '.join(warnings)})" if warnings else "")
        )
    return safe_dict(payload)


def _batch_targets(execution_plan: Dict[str, object], batch_id: str) -> Dict[str, object]:
    for item in list(execution_plan.get("execution_batches") or []):
        batch = safe_dict(item)
        if _safe_str(batch.get("batch_id")) == batch_id:
            return safe_dict(batch.get("targets"))
    return {}


def _priority_batch_completion(priority_rows: Sequence[Dict[str, object]], batch_targets: Dict[str, object]) -> bool:
    if not priority_rows or not batch_targets:
        return False
    min_history = min(_safe_int(row.get("history_rows_current")) for row in priority_rows)
    min_windows = min(_safe_int(row.get("usable_oos_windows_current")) for row in priority_rows)
    history_done = (
        min_history >= _safe_int(batch_targets.get("min_history_bars_per_ticker"))
        and min_windows >= _safe_int(batch_targets.get("usable_oos_windows_per_ticker"))
    )
    primary_rows = _primary_rows(priority_rows)
    if not primary_rows:
        return history_done
    primary_total_articles = sum(_safe_int(row.get("news_count_total_current")) for row in primary_rows)
    primary_article_days_median = float(
        pd.Series([_safe_int(row.get("article_days_current")) for row in primary_rows]).median()
    )
    primary_done = (
        primary_total_articles >= _safe_int(batch_targets.get("primary_segment_total_articles"))
        and primary_article_days_median >= float(batch_targets.get("primary_segment_article_days_median") or 0.0)
    )
    return history_done and primary_done


def _resolve_batch_1_status(
    *,
    batch_targets: Dict[str, object],
    ingest_payload: Dict[str, object],
    progress_payload: Dict[str, object],
    priority_rows: Sequence[Dict[str, object]],
) -> Tuple[str, bool, bool]:
    history_started = _bool_from_priority_rows(priority_rows, "history_extension_progress_ok")
    any_delta = any(_safe_int(row.get("history_rows_delta")) > 0 for row in priority_rows)
    batch_1_officially_started = history_started or any_delta

    batch_1_completed = _priority_batch_completion(priority_rows=priority_rows, batch_targets=batch_targets)
    checkpoint_material_reached = _safe_bool(progress_payload.get("checkpoint_material_reached"))

    if not batch_1_officially_started:
        status = "batch_1_not_started_snapshot_still_static"
    elif batch_1_completed and checkpoint_material_reached:
        status = "batch_1_complete_and_checkpoint_material_reached"
    elif batch_1_completed:
        status = "batch_1_complete_but_checkpoint_not_material"
    else:
        status = "batch_1_started_but_not_complete"
    return status, batch_1_officially_started, batch_1_completed


def _decisive_statement(
    *,
    batch_1_status: str,
    progress_payload: Dict[str, object],
    ingest_payload: Dict[str, object],
) -> str:
    if batch_1_status == "batch_1_not_started_snapshot_still_static":
        return "Batch-1 belum resmi mulai karena snapshot prioritas belum menunjukkan kenaikan history yang sah dari baseline."
    if batch_1_status == "batch_1_started_but_not_complete":
        return "Batch-1 resmi mulai bergerak karena snapshot prioritas sudah maju dari baseline."
    if batch_1_status == "batch_1_complete_but_checkpoint_not_material":
        if not _safe_bool(ingest_payload.get("article_day_recovery_progress_ok")):
            return "Batch-1 complete pada sisi history, tetapi checkpoint material masih tertahan oleh article-day recovery."
        return "Batch-1 complete, tetapi checkpoint material belum cukup untuk mengizinkan recheck readiness gate."
    if batch_1_status == "batch_1_complete_and_checkpoint_material_reached":
        return "Checkpoint material sudah tercapai sehingga readiness gate sekarang boleh dijalankan ulang."
    return _safe_str(progress_payload.get("decisive_statement"), "Status batch-1 tidak dapat ditentukan secara tegas.")


def _recommended_next_action(
    *,
    batch_1_status: str,
    recheck_allowed: bool,
    progress_payload: Dict[str, object],
) -> str:
    if batch_1_status == "batch_1_not_started_snapshot_still_static":
        return "continue_batch_1_backfill_until_priority_snapshot_advance_is_visible"
    if batch_1_status == "batch_1_started_but_not_complete":
        return "continue_batch_1_until_history_and_primary_article_day_targets_are_closed"
    if batch_1_status == "batch_1_complete_but_checkpoint_not_material":
        return "advance_to_batch_2_and_close_remaining_checkpoint_blockers_before_rerunning_gate"
    if recheck_allowed:
        return "rerun_phase_b_retest_readiness_gate_with_refreshed_post_backfill_inputs"
    return _safe_str(progress_payload.get("recommended_next_action"), "continue_current_batch")


def _build_ingest_text(payload: Dict[str, object]) -> List[str]:
    return [
        "Phase B Post-Backfill Ingest Audit",
        f"- batch_id={payload.get('batch_id')}",
        f"- batch_acceptance_status={payload.get('batch_acceptance_status')}",
        f"- history_extension_progress_ok={payload.get('history_extension_progress_ok')}",
        f"- article_day_recovery_progress_ok={payload.get('article_day_recovery_progress_ok')}",
        f"- metadata_segmentation_update_ok={payload.get('metadata_segmentation_update_ok')}",
        f"- accepted_tickers={', '.join(list(payload.get('accepted_tickers') or [])) or '-'}",
        f"- rejected_tickers={', '.join(list(payload.get('rejected_tickers') or [])) or '-'}",
        f"- tickers_with_warnings={', '.join(list(payload.get('tickers_with_warnings') or [])) or '-'}",
        f"- decisive_statement={payload.get('decisive_statement')}",
    ]


def _build_progress_text(payload: Dict[str, object]) -> List[str]:
    return [
        "Phase B Post-Backfill Progress Update",
        f"- current_batch={payload.get('current_batch')}",
        f"- current_batch_completed={payload.get('current_batch_completed')}",
        f"- highest_completed_batch={payload.get('highest_completed_batch')}",
        f"- checkpoint_material_reached={payload.get('checkpoint_material_reached')}",
        f"- recheck_readiness_gate_allowed={payload.get('recheck_readiness_gate_allowed')}",
        f"- recommended_next_action={payload.get('recommended_next_action')}",
        f"- decisive_statement={payload.get('decisive_statement')}",
        "Remaining blockers:",
        *[f"- {item}" for item in list(payload.get("remaining_blockers") or [])],
    ]


def run_phase_b_post_backfill_batch_verification(
    *,
    data_dir: Path,
    output_dir: Path,
    metadata_file: Optional[Path] = None,
) -> Dict[str, object]:
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    if not data_dir.exists():
        raise PhaseBPostBackfillBatchVerificationCliError(f"Data directory not found: {data_dir}")

    ingest_result = run_phase_b_data_extension_ingest_audit(
        data_dir=data_dir,
        output_dir=output_dir,
        metadata_file=metadata_file,
    )
    progress_result = run_phase_b_data_extension_progress_update(
        data_dir=data_dir,
        output_dir=output_dir,
        metadata_file=metadata_file,
    )

    ingest_payload = safe_dict(ingest_result.get("phase_b_ingest_acceptance_decision"))
    progress_payload = safe_dict(progress_result.get("phase_b_data_extension_progress_update"))
    if not ingest_payload or not progress_payload:
        raise PhaseBPostBackfillBatchVerificationCliError(
            "Official ingest audit or progress update did not return usable payloads."
        )
    execution_plan = _load_execution_plan(output_dir=output_dir)
    batch_targets = _batch_targets(execution_plan=execution_plan, batch_id="batch_1")

    priority_rows = _priority_matrix_rows(ingest_result)
    batch_1_status, batch_1_officially_started, batch_1_completed = _resolve_batch_1_status(
        batch_targets=batch_targets,
        ingest_payload=ingest_payload,
        progress_payload=progress_payload,
        priority_rows=priority_rows,
    )
    checkpoint_material_reached = _safe_bool(progress_payload.get("checkpoint_material_reached"))
    recheck_allowed = _safe_bool(progress_payload.get("recheck_readiness_gate_allowed"))
    if batch_1_status not in BATCH_1_STATUSES:
        raise PhaseBPostBackfillBatchVerificationCliError(f"Unexpected batch_1_status resolved: {batch_1_status}")

    remaining_blockers = _remaining_blockers(
        progress_payload=progress_payload,
        ingest_payload=ingest_payload,
    )

    primary_rows = _primary_rows(priority_rows)
    ticker_verification = [
        {
            "ticker": _safe_str(row.get("ticker")),
            "history_rows_delta": _safe_int(row.get("history_rows_delta")),
            "usable_oos_windows_delta": _safe_int(row.get("usable_oos_windows_delta")),
            "article_days_delta": _safe_int(row.get("article_days_delta")),
            "news_count_total_delta": _safe_int(row.get("news_count_total_delta")),
            "history_rows_current": _safe_int(row.get("history_rows_current")),
            "usable_oos_windows_current": _safe_int(row.get("usable_oos_windows_current")),
            "article_days_current": _safe_int(row.get("article_days_current")),
            "news_count_total_current": _safe_int(row.get("news_count_total_current")),
            "is_primary_segment": _safe_bool(row.get("is_primary_segment")),
            "ingest_status": _safe_str(row.get("ingest_status")),
        }
        for row in priority_rows
    ]

    decision = {
        "generated_at": _now_iso(),
        "batch_1_status": batch_1_status,
        "batch_1_officially_started": batch_1_officially_started,
        "batch_1_completed": batch_1_completed,
        "checkpoint_material_reached": checkpoint_material_reached,
        "recheck_readiness_gate_allowed": recheck_allowed,
        "remaining_blockers": remaining_blockers,
        "recommended_next_action": _recommended_next_action(
            batch_1_status=batch_1_status,
            recheck_allowed=recheck_allowed,
            progress_payload=progress_payload,
        ),
        "decisive_statement": _decisive_statement(
            batch_1_status=batch_1_status,
            progress_payload=progress_payload,
            ingest_payload=ingest_payload,
        ),
        "batch_id": _safe_str(ingest_payload.get("batch_id"), "batch_1"),
        "batch_acceptance_status": _safe_str(ingest_payload.get("batch_acceptance_status")),
        "history_extension_progress_ok": _safe_bool(ingest_payload.get("history_extension_progress_ok")),
        "primary_article_day_recovery_progress_ok": _safe_bool(ingest_payload.get("article_day_recovery_progress_ok")),
        "metadata_segmentation_update_ok": _safe_bool(ingest_payload.get("metadata_segmentation_update_ok")),
        "priority_ticker_verification": ticker_verification,
        "primary_segment_summary": {
            "primary_tickers_audited": [_safe_str(row.get("ticker")) for row in primary_rows],
            "article_days_current": { _safe_str(row.get("ticker")): _safe_int(row.get("article_days_current")) for row in primary_rows },
            "news_count_total_current": { _safe_str(row.get("ticker")): _safe_int(row.get("news_count_total_current")) for row in primary_rows },
        },
    }

    _write_json(output_dir / POST_BACKFILL_INGEST_JSON_OUTPUT, ingest_payload)
    _write_text(output_dir / POST_BACKFILL_INGEST_TEXT_OUTPUT, _build_ingest_text(ingest_payload))
    _write_json(output_dir / POST_BACKFILL_PROGRESS_JSON_OUTPUT, progress_payload)
    _write_text(output_dir / POST_BACKFILL_PROGRESS_TEXT_OUTPUT, _build_progress_text(progress_payload))
    _write_json(output_dir / POST_BACKFILL_DECISION_JSON_OUTPUT, decision)

    return {
        "phase_b_post_backfill_ingest_audit": ingest_payload,
        "phase_b_post_backfill_progress_update": progress_payload,
        "phase_b_post_backfill_batch1_decision": decision,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rerun official ingest/progress verification after post-backfill snapshot refresh.")
    parser.add_argument("--data-dir", default="data", help="Directory containing ticker CSV files.")
    parser.add_argument("--output-dir", default="output", help="Directory containing and receiving artifacts.")
    parser.add_argument("--metadata-file", default="data/ticker_metadata.csv", help="Optional ticker metadata CSV.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        result = run_phase_b_post_backfill_batch_verification(
            data_dir=Path(args.data_dir),
            output_dir=Path(args.output_dir),
            metadata_file=Path(args.metadata_file) if args.metadata_file else None,
        )
    except PhaseBPostBackfillBatchVerificationCliError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Unexpected error during post-backfill batch verification: {exc}", file=sys.stderr)
        return 1

    payload = safe_dict(result.get("phase_b_post_backfill_batch1_decision"))
    print("Phase B post-backfill batch verification complete.")
    print(f"batch_1_status={payload.get('batch_1_status')}")
    print(f"checkpoint_material_reached={payload.get('checkpoint_material_reached')}")
    print(f"recheck_readiness_gate_allowed={payload.get('recheck_readiness_gate_allowed')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
