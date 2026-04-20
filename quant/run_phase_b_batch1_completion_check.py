"""Refresh segmentation and verify whether Phase B batch-1 can be marked complete."""

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
from quant.run_baseline_v6_guardrail_review import run_baseline_v6_guardrail_review  # noqa: E402
from quant.run_phase_b_post_backfill_batch_verification import run_phase_b_post_backfill_batch_verification  # noqa: E402


ARTICLE_DAY_STATUS_JSON_OUTPUT = "phase_b_article_day_recovery_status.json"
ARTICLE_DAY_STATUS_TEXT_OUTPUT = "phase_b_article_day_recovery_status.txt"
SEGMENTATION_REFRESH_JSON_OUTPUT = "phase_b_segmentation_refresh_status.json"
SEGMENTATION_REFRESH_TEXT_OUTPUT = "phase_b_segmentation_refresh_status.txt"
BATCH1_COMPLETION_JSON_OUTPUT = "phase_b_batch1_completion_decision.json"

SEGMENTATION_FILE = "baseline_v6_universe_segmentation.csv"


class PhaseBBatch1CompletionCheckCliError(ValueError):
    """Friendly CLI error for Phase B batch-1 completion check."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_str(value: object, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


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


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _write_text(path: Path, lines: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load_json(path: Path, label: str) -> Dict[str, object]:
    payload, warnings = read_json_object(path, label)
    if payload is None:
        raise PhaseBBatch1CompletionCheckCliError(
            f"Required artifact missing or invalid: {path}" + (f" ({'; '.join(warnings)})" if warnings else "")
        )
    return safe_dict(payload)


def _load_csv(path: Path, label: str) -> pd.DataFrame:
    if not path.exists():
        raise PhaseBBatch1CompletionCheckCliError(f"Required CSV missing: {path} ({label})")
    try:
        return pd.read_csv(path)
    except Exception as exc:
        raise PhaseBBatch1CompletionCheckCliError(f"Failed to read {path} ({label}): {exc}") from exc


def _priority_tickers(post_backfill_decision: Dict[str, object]) -> List[str]:
    tickers = []
    for row in list(post_backfill_decision.get("priority_ticker_verification") or []):
        ticker = _safe_str(safe_dict(row).get("ticker")).upper()
        if ticker:
            tickers.append(ticker)
    if not tickers:
        tickers = [_safe_str(item).upper() for item in list(safe_dict(post_backfill_decision.get("primary_segment_summary")).get("primary_tickers_audited") or []) if _safe_str(item)]
    return dedupe(tickers)


def _read_price_snapshot(path: Path) -> Tuple[int, int]:
    frame = _load_csv(path, path.name)
    if frame.empty:
        return 0, 0
    article_series = (
        pd.to_numeric(frame.get("sentiment_news_count_1d"), errors="coerce").fillna(0.0)
        if "sentiment_news_count_1d" in frame.columns
        else pd.Series([0.0] * len(frame))
    )
    return int(float(article_series.sum())), int((article_series > 0).sum())


def _metadata_lookup(metadata_df: pd.DataFrame) -> Dict[str, Dict[str, object]]:
    if metadata_df.empty or "ticker" not in metadata_df.columns:
        return {}
    frame = metadata_df.copy()
    frame["ticker"] = frame["ticker"].astype(str).str.upper()
    return {
        str(row["ticker"]).upper(): dict(row)
        for _, row in frame.drop_duplicates(subset=["ticker"], keep="first").iterrows()
    }


def _segmentation_lookup(segmentation_df: pd.DataFrame) -> Dict[str, Dict[str, object]]:
    if segmentation_df.empty or "ticker" not in segmentation_df.columns:
        return {}
    frame = segmentation_df.copy()
    frame["ticker"] = frame["ticker"].astype(str).str.upper()
    return {
        str(row["ticker"]).upper(): dict(row)
        for _, row in frame.drop_duplicates(subset=["ticker"], keep="first").iterrows()
    }


def _article_day_status(
    *,
    data_dir: Path,
    metadata_file: Path,
    priority_tickers: Sequence[str],
) -> Dict[str, object]:
    metadata_df = _load_csv(metadata_file, "ticker_metadata")
    metadata_by_ticker = _metadata_lookup(metadata_df)
    ticker_rows: List[Dict[str, object]] = []
    for ticker in priority_tickers:
        price_path = Path(data_dir) / f"{ticker}.csv"
        news_count_total_current, article_days_current = _read_price_snapshot(price_path)
        metadata_row = safe_dict(metadata_by_ticker.get(ticker))
        ticker_rows.append(
            {
                "ticker": ticker,
                "news_count_total_current": news_count_total_current,
                "article_days_current": article_days_current,
                "metadata_news_count_total": _safe_int(metadata_row.get("sentiment_article_count_total")),
                "metadata_article_days": _safe_int(metadata_row.get("sentiment_days_with_articles")),
                "metadata_history_rows": _safe_int(metadata_row.get("rows_1d", metadata_row.get("history_rows"))),
            }
        )

    frame = pd.DataFrame(ticker_rows)
    if frame.empty:
        total_articles = 0.0
        median_article_days = 0.0
    else:
        total_articles = float(pd.to_numeric(frame["news_count_total_current"], errors="coerce").fillna(0).sum())
        median_article_days = round(
            float(pd.to_numeric(frame["article_days_current"], errors="coerce").fillna(0).median()), 4
        )
    limiting_by_articles = (
        frame.sort_values(["news_count_total_current", "article_days_current", "ticker"], ascending=[True, True, True])
        .head(3)["ticker"]
        .astype(str)
        .tolist()
        if not frame.empty
        else []
    )
    limiting_by_days = (
        frame.sort_values(["article_days_current", "news_count_total_current", "ticker"], ascending=[True, True, True])
        .head(3)["ticker"]
        .astype(str)
        .tolist()
        if not frame.empty
        else []
    )
    article_target_met = total_articles >= 14.0
    article_days_target_met = median_article_days >= 3.0
    return {
        "generated_at": _now_iso(),
        "priority_tickers": list(priority_tickers),
        "primary_segment_total_articles": round(total_articles, 4),
        "primary_segment_article_days_median": median_article_days,
        "article_target_met": article_target_met,
        "article_days_target_met": article_days_target_met,
        "limiting_tickers_for_total_articles": limiting_by_articles,
        "limiting_tickers_for_article_days_median": limiting_by_days,
        "per_ticker": ticker_rows,
        "recommended_next_action": (
            "continue_priority_news_extension_until_primary_article_targets_are_closed"
            if not article_target_met or not article_days_target_met
            else "article_day_targets_closed_waiting_for_segmentation_sync_or_batch_decision_refresh"
        ),
        "decisive_statement": (
            "Batch-1 belum complete karena article-day recovery primary segment masih di bawah target minimum."
            if not article_target_met or not article_days_target_met
            else "Primary segment article-day recovery sudah memenuhi target minimum batch-1."
        ),
    }


def _segmentation_alignment(
    *,
    metadata_df: pd.DataFrame,
    segmentation_df: pd.DataFrame,
    priority_tickers: Sequence[str],
) -> Tuple[bool, List[Dict[str, object]]]:
    metadata_by_ticker = _metadata_lookup(metadata_df)
    segmentation_by_ticker = _segmentation_lookup(segmentation_df)
    rows: List[Dict[str, object]] = []
    aligned = True
    for ticker in priority_tickers:
        metadata_row = safe_dict(metadata_by_ticker.get(ticker))
        segmentation_row = safe_dict(segmentation_by_ticker.get(ticker))
        metadata_history_rows = _safe_int(metadata_row.get("rows_1d", metadata_row.get("history_rows")))
        segmentation_history_rows = _safe_int(segmentation_row.get("rows", segmentation_row.get("history_rows")))
        metadata_article_days = _safe_int(metadata_row.get("sentiment_days_with_articles"))
        segmentation_article_days = _safe_int(segmentation_row.get("article_days"))
        metadata_news_count_total = _safe_int(metadata_row.get("sentiment_article_count_total"))
        segmentation_news_count_total = _safe_int(segmentation_row.get("news_count_total", segmentation_row.get("article_count_total")))
        ticker_aligned = (
            metadata_history_rows == segmentation_history_rows
            and metadata_article_days == segmentation_article_days
            and metadata_news_count_total == segmentation_news_count_total
        )
        aligned = aligned and ticker_aligned
        rows.append(
            {
                "ticker": ticker,
                "metadata_history_rows": metadata_history_rows,
                "segmentation_history_rows": segmentation_history_rows,
                "metadata_article_days": metadata_article_days,
                "segmentation_article_days": segmentation_article_days,
                "metadata_news_count_total": metadata_news_count_total,
                "segmentation_news_count_total": segmentation_news_count_total,
                "aligned": ticker_aligned,
            }
        )
    return aligned, rows


def _segmentation_refresh_status(
    *,
    output_dir: Path,
    metadata_file: Path,
    priority_tickers: Sequence[str],
    before_segmentation_df: pd.DataFrame,
    after_segmentation_df: pd.DataFrame,
) -> Dict[str, object]:
    metadata_df = _load_csv(metadata_file, "ticker_metadata")
    before_aligned, before_rows = _segmentation_alignment(
        metadata_df=metadata_df,
        segmentation_df=before_segmentation_df,
        priority_tickers=priority_tickers,
    )
    after_aligned, after_rows = _segmentation_alignment(
        metadata_df=metadata_df,
        segmentation_df=after_segmentation_df,
        priority_tickers=priority_tickers,
    )
    changed_tickers = []
    before_by_ticker = {row["ticker"]: row for row in before_rows}
    for row in after_rows:
        before_row = safe_dict(before_by_ticker.get(_safe_str(row.get("ticker"))))
        if not before_row:
            changed_tickers.append(_safe_str(row.get("ticker")))
            continue
        if (
            _safe_int(before_row.get("segmentation_history_rows")) != _safe_int(row.get("segmentation_history_rows"))
            or _safe_int(before_row.get("segmentation_article_days")) != _safe_int(row.get("segmentation_article_days"))
            or _safe_int(before_row.get("segmentation_news_count_total")) != _safe_int(row.get("segmentation_news_count_total"))
        ):
            changed_tickers.append(_safe_str(row.get("ticker")))

    return {
        "generated_at": _now_iso(),
        "segmentation_refresh_attempted": True,
        "segmentation_refresh_completed": after_aligned,
        "segmentation_sync_before_refresh": before_aligned,
        "segmentation_sync_after_refresh": after_aligned,
        "changed_priority_tickers": dedupe(changed_tickers),
        "before_refresh_alignment": before_rows,
        "after_refresh_alignment": after_rows,
        "recommended_next_action": (
            "rerun_post_backfill_verification_after_segment_refresh"
            if after_aligned
            else "investigate_segmentation_generation_path_before_marking_batch_progress"
        ),
        "decisive_statement": (
            "Segmentation refresh berhasil dan sekarang sinkron dengan snapshot terbaru."
            if after_aligned
            else "Segmentation refresh belum berhasil; artifact segment masih belum sinkron dengan snapshot terbaru."
        ),
    }


def _build_text_lines(title: str, payload: Dict[str, object], keys: Sequence[str]) -> List[str]:
    lines = [title]
    for key in keys:
        lines.append(f"- {key}={payload.get(key)}")
    if payload.get("decisive_statement"):
        lines.append(f"- decisive_statement={payload.get('decisive_statement')}")
    if payload.get("recommended_next_action"):
        lines.append(f"- recommended_next_action={payload.get('recommended_next_action')}")
    return lines


def run_phase_b_batch1_completion_check(
    *,
    data_dir: Path,
    output_dir: Path,
    metadata_file: Optional[Path] = None,
) -> Dict[str, object]:
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    resolved_metadata = Path(metadata_file) if metadata_file is not None else data_dir / "ticker_metadata.csv"
    if not data_dir.exists():
        raise PhaseBBatch1CompletionCheckCliError(f"Data directory not found: {data_dir}")
    if not resolved_metadata.exists():
        raise PhaseBBatch1CompletionCheckCliError(f"Metadata file not found: {resolved_metadata}")

    prior_decision = _load_json(output_dir / "phase_b_post_backfill_batch1_decision.json", "phase_b_post_backfill_batch1_decision")
    priority_tickers = _priority_tickers(prior_decision)
    if not priority_tickers:
        raise PhaseBBatch1CompletionCheckCliError("Priority tickers could not be resolved from post-backfill decision.")

    article_status = _article_day_status(
        data_dir=data_dir,
        metadata_file=resolved_metadata,
        priority_tickers=priority_tickers,
    )
    before_segmentation_df = _load_csv(output_dir / SEGMENTATION_FILE, SEGMENTATION_FILE)
    run_baseline_v6_guardrail_review(
        data_dir=data_dir,
        output_dir=output_dir,
        metadata_file=resolved_metadata,
    )
    after_segmentation_df = _load_csv(output_dir / SEGMENTATION_FILE, SEGMENTATION_FILE)
    segmentation_status = _segmentation_refresh_status(
        output_dir=output_dir,
        metadata_file=resolved_metadata,
        priority_tickers=priority_tickers,
        before_segmentation_df=before_segmentation_df,
        after_segmentation_df=after_segmentation_df,
    )

    verification_result = run_phase_b_post_backfill_batch_verification(
        data_dir=data_dir,
        output_dir=output_dir,
        metadata_file=resolved_metadata,
    )
    decision = safe_dict(verification_result.get("phase_b_post_backfill_batch1_decision"))
    progress = safe_dict(verification_result.get("phase_b_post_backfill_progress_update"))
    if not decision or not progress:
        raise PhaseBBatch1CompletionCheckCliError("Post-refresh batch verification did not return usable payloads.")

    completion_payload = {
        "generated_at": _now_iso(),
        "primary_segment_total_articles": round(_safe_float(article_status.get("primary_segment_total_articles")), 4),
        "primary_segment_article_days_median": round(_safe_float(article_status.get("primary_segment_article_days_median")), 4),
        "segmentation_refresh_completed": _safe_bool(segmentation_status.get("segmentation_refresh_completed")),
        "batch_1_status": _safe_str(decision.get("batch_1_status")),
        "batch_1_completed": _safe_bool(decision.get("batch_1_completed")),
        "checkpoint_material_reached": _safe_bool(decision.get("checkpoint_material_reached")),
        "recheck_readiness_gate_allowed": _safe_bool(decision.get("recheck_readiness_gate_allowed")),
        "remaining_blockers": list(decision.get("remaining_blockers") or []),
        "recommended_next_action": _safe_str(decision.get("recommended_next_action")),
        "decisive_statement": (
            "Batch-1 resmi complete setelah article target dan segmentation sync terpenuhi."
            if _safe_bool(decision.get("batch_1_completed")) and not _safe_bool(decision.get("checkpoint_material_reached"))
            else (
                "Checkpoint material sudah tercapai sehingga readiness gate sekarang boleh dijalankan ulang."
                if _safe_bool(decision.get("checkpoint_material_reached"))
                else (
                    "Segmentation refresh berhasil, tetapi article coverage primary masih belum cukup."
                    if _safe_bool(segmentation_status.get("segmentation_refresh_completed"))
                    else "Batch-1 belum complete karena article-day recovery primary segment masih di bawah target minimum."
                )
            )
        ),
        "article_day_status": article_status,
        "segmentation_refresh_status": segmentation_status,
        "post_backfill_batch1_decision": decision,
        "post_backfill_progress_update": progress,
    }

    _write_json(output_dir / ARTICLE_DAY_STATUS_JSON_OUTPUT, article_status)
    _write_text(
        output_dir / ARTICLE_DAY_STATUS_TEXT_OUTPUT,
        _build_text_lines(
            "Phase B Article-Day Recovery Status",
            article_status,
            [
                "primary_segment_total_articles",
                "primary_segment_article_days_median",
                "article_target_met",
                "article_days_target_met",
            ],
        ),
    )
    _write_json(output_dir / SEGMENTATION_REFRESH_JSON_OUTPUT, segmentation_status)
    _write_text(
        output_dir / SEGMENTATION_REFRESH_TEXT_OUTPUT,
        _build_text_lines(
            "Phase B Segmentation Refresh Status",
            segmentation_status,
            [
                "segmentation_refresh_attempted",
                "segmentation_sync_before_refresh",
                "segmentation_refresh_completed",
            ],
        ),
    )
    _write_json(output_dir / BATCH1_COMPLETION_JSON_OUTPUT, completion_payload)

    return {
        "phase_b_article_day_recovery_status": article_status,
        "phase_b_segmentation_refresh_status": segmentation_status,
        "phase_b_batch1_completion_decision": completion_payload,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh segmentation and verify whether Phase B batch-1 is complete.")
    parser.add_argument("--data-dir", default="data", help="Directory containing ticker CSV files.")
    parser.add_argument("--output-dir", default="output", help="Directory containing and receiving artifacts.")
    parser.add_argument("--metadata-file", default="data/ticker_metadata.csv", help="Optional ticker metadata CSV.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        result = run_phase_b_batch1_completion_check(
            data_dir=Path(args.data_dir),
            output_dir=Path(args.output_dir),
            metadata_file=Path(args.metadata_file) if args.metadata_file else None,
        )
    except PhaseBBatch1CompletionCheckCliError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Unexpected error during batch-1 completion check: {exc}", file=sys.stderr)
        return 1

    payload = safe_dict(result.get("phase_b_batch1_completion_decision"))
    print("Phase B batch-1 completion check complete.")
    print(f"batch_1_status={payload.get('batch_1_status')}")
    print(f"batch_1_completed={payload.get('batch_1_completed')}")
    print(f"recheck_readiness_gate_allowed={payload.get('recheck_readiness_gate_allowed')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
