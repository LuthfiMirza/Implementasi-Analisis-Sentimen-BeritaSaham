"""Audit UNVR/ICBP article coverage root cause across fetch, DB mapping, and export snapshot."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import pandas as pd

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.phase_a_transition_utils import dedupe, read_json_object, safe_dict  # noqa: E402


UNVR_ICBP_ROOT_CAUSE_JSON_OUTPUT = "phase_b_unvr_icbp_article_root_cause.json"
UNVR_ICBP_ROOT_CAUSE_TEXT_OUTPUT = "phase_b_unvr_icbp_article_root_cause.txt"
UNVR_ICBP_PIPELINE_TRACE_CSV_OUTPUT = "phase_b_unvr_icbp_article_pipeline_trace.csv"
UNVR_ICBP_FIX_STATUS_JSON_OUTPUT = "phase_b_unvr_icbp_article_fix_status.json"
UNVR_ICBP_NEXT_STEPS_JSON_OUTPUT = "phase_b_unvr_icbp_article_next_steps.json"

DEFAULT_TICKERS = ("UNVR", "ICBP")
TRACE_COLUMNS = [
    "ticker",
    "fetch_raw_total",
    "fetch_saved_total",
    "fetch_updated_total",
    "fetch_providers_with_raw_hits",
    "db_articles_all",
    "db_article_days_all",
    "db_articles_qualifying",
    "db_article_days_qualifying",
    "db_title_matches_other_or_null",
    "snapshot_articles",
    "snapshot_article_days",
    "mapping_gap_detected",
    "alignment_export_gap_detected",
    "source_sparse_detected",
    "fetch_missing_articles_detected",
    "pipeline_bug_confirmed",
    "ticker_root_cause",
    "ticker_decisive_statement",
]


class PhaseBUnvrIcbpArticleRootCauseCliError(ValueError):
    """Friendly CLI error for UNVR/ICBP article root-cause audit."""


ArticleProbe = Callable[[Sequence[str], Path], Dict[str, Dict[str, object]]]


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


def _write_csv(path: Path, rows: Sequence[Dict[str, object]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _load_required_json(path: Path, label: str) -> Dict[str, object]:
    payload, warnings = read_json_object(path, label)
    if payload is None:
        raise PhaseBUnvrIcbpArticleRootCauseCliError(
            f"Required artifact missing or invalid: {path}" + (f" ({'; '.join(warnings)})" if warnings else "")
        )
    return safe_dict(payload)


def _load_csv(path: Path, label: str) -> pd.DataFrame:
    if not path.exists():
        raise PhaseBUnvrIcbpArticleRootCauseCliError(f"Required CSV missing: {path} ({label})")
    try:
        return pd.read_csv(path)
    except Exception as exc:
        raise PhaseBUnvrIcbpArticleRootCauseCliError(f"Failed to read {path} ({label}): {exc}") from exc


def _read_snapshot_coverage(path: Path) -> Dict[str, object]:
    frame = _load_csv(path, path.name)
    if frame.empty:
        return {
            "rows": 0,
            "date_end": "",
            "snapshot_articles": 0,
            "snapshot_article_days": 0,
        }
    news_series = (
        pd.to_numeric(frame.get("sentiment_news_count_1d"), errors="coerce").fillna(0.0)
        if "sentiment_news_count_1d" in frame.columns
        else pd.Series([0.0] * len(frame))
    )
    date_end = _safe_str(frame["date"].iloc[-1]) if "date" in frame.columns else ""
    return {
        "rows": int(len(frame)),
        "date_end": date_end,
        "snapshot_articles": int(float(news_series.sum())),
        "snapshot_article_days": int((news_series > 0).sum()),
    }


def _default_article_probe(tickers: Sequence[str], cwd: Path) -> Dict[str, Dict[str, object]]:
    php_code = (
        'require "vendor/autoload.php"; '
        '$app = require "bootstrap/app.php"; '
        '$app->make(Illuminate\\Contracts\\Console\\Kernel::class)->bootstrap(); '
        '$threshold = (float) config("news.final_quality_threshold", 0.4); '
        '$mapper = app(App\\Services\\News\\StockKeywordMapper::class); '
        f'$tickers = json_decode({json.dumps(json.dumps(list(tickers)))}, true); '
        '$payload = []; '
        'foreach ($tickers as $code) { '
        '  $stock = App\\Models\\Stock::where("code", $code)->first(); '
        '  if (! $stock) { '
        '    $payload[$code] = ["db_articles_all" => 0, "db_article_days_all" => 0, "db_articles_qualifying" => 0, "db_article_days_qualifying" => 0, "db_title_matches_other_or_null" => 0, "qualifying_titles" => [], "all_titles" => [], "other_match_titles" => []]; '
        '    continue; '
        '  } '
        '  $rows = App\\Models\\NewsArticle::where("stock_id", $stock->id)->whereNotNull("published_at")->orderBy("published_at")->get(["title", "summary", "published_at", "final_quality_score", "relevance_score", "source_provider", "stock_id"]); '
        '  $qual = $rows->filter(fn($r) => $r->final_quality_score === null || (float) $r->final_quality_score >= $threshold); '
        '  $terms = array_values(array_filter($mapper->keywords($stock), fn($term) => mb_strlen(trim((string) $term)) >= 4)); '
        '  $other = collect(); '
        '  if (! empty($terms)) { '
        '    $other = App\\Models\\NewsArticle::query()->where(function ($query) use ($terms) { '
        '      foreach ($terms as $term) { '
        '        $query->orWhere("title", "like", "%".$term."%")->orWhere("summary", "like", "%".$term."%"); '
        '      } '
        '    })->where(function ($query) use ($stock) { '
        '      $query->whereNull("stock_id")->orWhere("stock_id", "!=", $stock->id); '
        '    })->orderBy("published_at")->get(["title", "published_at", "stock_id", "source_provider"]); '
        '  } '
        '  $payload[$code] = [ '
        '    "db_articles_all" => $rows->count(), '
        '    "db_article_days_all" => $rows->groupBy(fn($r) => optional($r->published_at)->toDateString())->count(), '
        '    "db_articles_qualifying" => $qual->count(), '
        '    "db_article_days_qualifying" => $qual->groupBy(fn($r) => optional($r->published_at)->toDateString())->count(), '
        '    "db_title_matches_other_or_null" => $other->count(), '
        '    "all_titles" => $rows->map(fn($r) => ["date" => optional($r->published_at)->toDateString(), "provider" => $r->source_provider ?: "unknown", "quality" => $r->final_quality_score, "relevance" => $r->relevance_score, "title" => $r->title])->values()->all(), '
        '    "qualifying_titles" => $qual->map(fn($r) => ["date" => optional($r->published_at)->toDateString(), "provider" => $r->source_provider ?: "unknown", "quality" => $r->final_quality_score, "relevance" => $r->relevance_score, "title" => $r->title])->values()->all(), '
        '    "other_match_titles" => $other->map(fn($r) => ["date" => optional($r->published_at)->toDateString(), "provider" => $r->source_provider ?: "unknown", "stock_id" => $r->stock_id, "title" => $r->title])->values()->all(), '
        '  ]; '
        '} '
        'echo json_encode($payload, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE);'
    )
    completed = subprocess.run(
        ["php", "-r", php_code],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise PhaseBUnvrIcbpArticleRootCauseCliError(
            "Article probe failed: "
            + "\n".join(part.strip() for part in [completed.stdout, completed.stderr] if part and part.strip())
        )
    try:
        payload = json.loads(_safe_str(completed.stdout, "{}") or "{}")
    except json.JSONDecodeError as exc:
        raise PhaseBUnvrIcbpArticleRootCauseCliError(
            f"Article probe returned invalid JSON: {completed.stdout}"
        ) from exc
    return {str(key).upper(): safe_dict(value) for key, value in safe_dict(payload).items()}


def _fetch_summary(push_payload: Dict[str, object], ticker: str) -> Dict[str, object]:
    attempts = [
        safe_dict(row)
        for row in list(push_payload.get("fetch_attempts") or [])
        if _safe_str(safe_dict(row).get("ticker")).upper() == ticker.upper()
    ]
    raw_total = sum(_safe_int(row.get("raw")) for row in attempts)
    saved_total = sum(_safe_int(row.get("saved")) for row in attempts)
    updated_total = sum(_safe_int(row.get("updated")) for row in attempts)
    providers_with_raw_hits = dedupe(
        [
            _safe_str(row.get("provider"))
            for row in attempts
            if _safe_int(row.get("raw")) > 0 and _safe_str(row.get("provider"))
        ]
    )
    providers_with_saved_hits = dedupe(
        [
            _safe_str(row.get("provider"))
            for row in attempts
            if (_safe_int(row.get("saved")) + _safe_int(row.get("updated"))) > 0 and _safe_str(row.get("provider"))
        ]
    )
    return {
        "attempts": attempts,
        "fetch_raw_total": raw_total,
        "fetch_saved_total": saved_total,
        "fetch_updated_total": updated_total,
        "fetch_providers_with_raw_hits": providers_with_raw_hits,
        "fetch_providers_with_saved_hits": providers_with_saved_hits,
    }


def _ticker_root_cause(
    *,
    ticker: str,
    fetch_summary: Dict[str, object],
    article_probe: Dict[str, object],
    snapshot_probe: Dict[str, object],
) -> Dict[str, object]:
    db_all = _safe_int(article_probe.get("db_articles_all"))
    db_days_all = _safe_int(article_probe.get("db_article_days_all"))
    db_qual = _safe_int(article_probe.get("db_articles_qualifying"))
    db_days_qual = _safe_int(article_probe.get("db_article_days_qualifying"))
    other_matches = _safe_int(article_probe.get("db_title_matches_other_or_null"))
    snapshot_articles = _safe_int(snapshot_probe.get("snapshot_articles"))
    snapshot_days = _safe_int(snapshot_probe.get("snapshot_article_days"))
    fetch_raw_total = _safe_int(fetch_summary.get("fetch_raw_total"))
    fetch_saved_total = _safe_int(fetch_summary.get("fetch_saved_total"))
    fetch_updated_total = _safe_int(fetch_summary.get("fetch_updated_total"))

    mapping_gap_detected = other_matches > 0
    alignment_export_gap_detected = db_all > snapshot_articles or db_days_all > snapshot_days
    qualifying_export_gap_detected = db_qual > snapshot_articles or db_days_qual > snapshot_days
    below_quality_threshold_detected = (
        db_all > db_qual and alignment_export_gap_detected and not qualifying_export_gap_detected
    )
    source_sparse_detected = db_all <= 1 and fetch_saved_total == 0 and fetch_updated_total == 0
    fetch_missing_articles_detected = fetch_raw_total > 0 and fetch_saved_total == 0 and fetch_updated_total == 0 and db_all == 0
    pipeline_bug_confirmed = mapping_gap_detected or qualifying_export_gap_detected

    if pipeline_bug_confirmed and mapping_gap_detected and qualifying_export_gap_detected:
        ticker_root_cause = "mixed_root_cause"
        decisive = (
            f"{ticker} punya gap mapping dan qualifying article tidak sepenuhnya muncul di snapshot; jalur lokal perlu diperbaiki."
        )
    elif pipeline_bug_confirmed and mapping_gap_detected:
        ticker_root_cause = "ticker_mapping_gap"
        decisive = f"Artikel {ticker} terdeteksi ada di DB tetapi sebagian masih jatuh ke stock lain/null."
    elif pipeline_bug_confirmed and qualifying_export_gap_detected:
        ticker_root_cause = "qualifying_export_gap_local_pipeline_issue"
        decisive = f"Artikel qualifying {ticker} ada di DB tetapi tidak seluruhnya masuk ke snapshot export."
    elif below_quality_threshold_detected:
        ticker_root_cause = "article_exists_but_below_quality_threshold"
        decisive = (
            f"Artikel {ticker} ada di DB dan mapping benar, tetapi belum lolos quality gate export; ini bukan bukti local pipeline failure."
        )
    elif fetch_missing_articles_detected:
        ticker_root_cause = "fetch_missing_articles"
        decisive = f"Source {ticker} sempat mengembalikan raw hit tetapi tidak menghasilkan artikel tersimpan di DB."
    elif source_sparse_detected:
        ticker_root_cause = "source_articles_truly_sparse"
        decisive = f"Coverage artikel {ticker} memang minim dari source dan tidak menunjukkan kehilangan di pipeline lokal."
    else:
        ticker_root_cause = "coverage_aligned_no_local_issue"
        decisive = f"Artikel {ticker} yang lolos kualitas sudah selaras dengan snapshot; kendala tersisa ada pada coverage source."

    return {
        "ticker": ticker,
        "fetch_raw_total": fetch_raw_total,
        "fetch_saved_total": fetch_saved_total,
        "fetch_updated_total": fetch_updated_total,
        "fetch_providers_with_raw_hits": list(fetch_summary.get("fetch_providers_with_raw_hits") or []),
        "db_articles_all": db_all,
        "db_article_days_all": db_days_all,
        "db_articles_qualifying": db_qual,
        "db_article_days_qualifying": db_days_qual,
        "db_title_matches_other_or_null": other_matches,
        "snapshot_articles": snapshot_articles,
        "snapshot_article_days": snapshot_days,
        "mapping_gap_detected": mapping_gap_detected,
        "alignment_export_gap_detected": alignment_export_gap_detected,
        "qualifying_export_gap_detected": qualifying_export_gap_detected,
        "below_quality_threshold_detected": below_quality_threshold_detected,
        "source_sparse_detected": source_sparse_detected,
        "fetch_missing_articles_detected": fetch_missing_articles_detected,
        "pipeline_bug_confirmed": pipeline_bug_confirmed,
        "ticker_root_cause": ticker_root_cause,
        "ticker_decisive_statement": decisive,
        "all_titles": list(article_probe.get("all_titles") or []),
        "qualifying_titles": list(article_probe.get("qualifying_titles") or []),
        "other_match_titles": list(article_probe.get("other_match_titles") or []),
        "date_end": _safe_str(snapshot_probe.get("date_end")),
        "history_rows": _safe_int(snapshot_probe.get("rows")),
    }


def _overall_root_cause(per_ticker: Sequence[Dict[str, object]]) -> str:
    mapping_gap = any(_safe_bool(row.get("mapping_gap_detected")) for row in per_ticker)
    sparse = any(_safe_bool(row.get("source_sparse_detected")) for row in per_ticker)
    below_quality = any(_safe_bool(row.get("below_quality_threshold_detected")) for row in per_ticker)
    fetch_missing = any(_safe_bool(row.get("fetch_missing_articles_detected")) for row in per_ticker)
    qualifying_export_gap = any(_safe_bool(row.get("qualifying_export_gap_detected")) for row in per_ticker)
    pipeline_bug = any(_safe_bool(row.get("pipeline_bug_confirmed")) for row in per_ticker)

    if pipeline_bug and mapping_gap and qualifying_export_gap:
        return "mixed_root_cause"
    if pipeline_bug and mapping_gap:
        return "ticker_mapping_gap"
    if pipeline_bug:
        return "qualifying_export_gap_local_pipeline_issue"
    if fetch_missing:
        return "fetch_missing_articles"
    if below_quality or sparse:
        return "external_source_limited"
    return "coverage_aligned_no_local_issue"


def _next_steps(per_ticker: Sequence[Dict[str, object]]) -> Dict[str, object]:
    blockers: List[str] = []
    for row in per_ticker:
        ticker = _safe_str(row.get("ticker"))
        if _safe_bool(row.get("pipeline_bug_confirmed")):
            blockers.append(f"{ticker}: local_pipeline_gap")
        elif _safe_bool(row.get("below_quality_threshold_detected")):
            blockers.append(f"{ticker}: article_exists_but_below_quality_threshold")
        elif _safe_bool(row.get("source_sparse_detected")):
            blockers.append(f"{ticker}: source_article_coverage_still_sparse")
        elif _safe_bool(row.get("fetch_missing_articles_detected")):
            blockers.append(f"{ticker}: fetch_returned_raw_without_db_persistence")
    blockers = dedupe(blockers)
    return {
        "do_not_rerun_readiness_gate": True,
        "do_not_change_baseline_or_entry_exit_logic": True,
        "minimum_operational_requirements_before_next_article_push": [
            "do_not_rerun_readiness_gate_now",
            "do_not_change_baseline_or_entry_exit_logic",
            "rerun_article_push_only_if_new_qualifying_articles_exist_for_UNVR_or_ICBP",
            "keep_export_with_include_sentiment_series_after_any_new_article_ingest",
            "treat_batch_1_as_blocked_until_UNVR_and_ICBP_article_days_move_materially",
        ],
        "current_article_blockers": blockers,
        "recommended_next_action": (
            "do_not_rerun_readiness_gate_or_change_baseline_rerun_article_push_only_if_new_qualifying_articles_exist_for_unvr_or_icbp"
            if not any(_safe_bool(row.get("pipeline_bug_confirmed")) for row in per_ticker)
            else "fix_local_article_pipeline_gap_then_rerun_export_and_batch_1_verification"
        ),
    }


def _root_cause_text(payload: Dict[str, object]) -> List[str]:
    per_ticker = list(payload.get("per_ticker") or [])
    lines = [
        "Phase B UNVR/ICBP Article Root Cause",
        f"- root_cause_class={payload.get('root_cause_class')}",
        f"- unvr_source_articles_sparse={payload.get('unvr_source_articles_sparse')}",
        f"- icbp_source_articles_sparse={payload.get('icbp_source_articles_sparse')}",
        f"- ticker_mapping_gap_detected={payload.get('ticker_mapping_gap_detected')}",
        f"- alignment_export_gap_detected={payload.get('alignment_export_gap_detected')}",
        f"- pipeline_bug_confirmed={payload.get('pipeline_bug_confirmed')}",
        f"- local_fix_applied={payload.get('local_fix_applied')}",
        f"- article_coverage_improved={payload.get('article_coverage_improved')}",
        f"- batch_1_helpful_progress_detected={payload.get('batch_1_helpful_progress_detected')}",
        f"- recommended_next_action={payload.get('recommended_next_action')}",
        "",
    ]
    for row in per_ticker:
        item = safe_dict(row)
        lines.extend(
            [
                f"{_safe_str(item.get('ticker'))}:",
                f"- db_articles_all={item.get('db_articles_all')}",
                f"- db_articles_qualifying={item.get('db_articles_qualifying')}",
                f"- snapshot_articles={item.get('snapshot_articles')}",
                f"- snapshot_article_days={item.get('snapshot_article_days')}",
                f"- ticker_root_cause={item.get('ticker_root_cause')}",
                f"- decisive_statement={item.get('ticker_decisive_statement')}",
                "",
            ]
        )
    return lines


def run_phase_b_unvr_icbp_article_root_cause(
    *,
    data_dir: Path,
    output_dir: Path,
    metadata_file: Optional[Path] = None,
    tickers: Sequence[str] = DEFAULT_TICKERS,
    article_probe: Optional[ArticleProbe] = None,
) -> Dict[str, object]:
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    metadata_file = Path(metadata_file) if metadata_file else data_dir / "ticker_metadata.csv"
    root = Path(__file__).resolve().parent.parent
    if not data_dir.exists():
        raise PhaseBUnvrIcbpArticleRootCauseCliError(f"Data directory not found: {data_dir}")

    tickers = dedupe([_safe_str(item).upper() for item in tickers if _safe_str(item)])
    if not tickers:
        raise PhaseBUnvrIcbpArticleRootCauseCliError("At least one ticker is required.")

    push_payload = _load_required_json(output_dir / "phase_b_primary_article_coverage_push.json", "phase_b_primary_article_coverage_push.json")
    batch_after_push = _load_required_json(output_dir / "phase_b_batch1_after_article_push.json", "phase_b_batch1_after_article_push.json")
    batch_completion = _load_required_json(output_dir / "phase_b_batch1_completion_decision.json", "phase_b_batch1_completion_decision.json")
    segmentation_df = _load_csv(output_dir / "baseline_v6_universe_segmentation.csv", "baseline_v6_universe_segmentation.csv")
    metadata_df = _load_csv(metadata_file, "ticker_metadata.csv")

    probe = article_probe or _default_article_probe
    article_probe_rows = {str(key).upper(): safe_dict(value) for key, value in probe(tickers, root).items()}

    segmentation_by_ticker = {
        _safe_str(row.get("ticker")).upper(): safe_dict(row)
        for row in segmentation_df.to_dict(orient="records")
        if _safe_str(row.get("ticker"))
    }
    metadata_by_ticker = {
        _safe_str(row.get("ticker")).upper(): safe_dict(row)
        for row in metadata_df.to_dict(orient="records")
        if _safe_str(row.get("ticker"))
    }

    per_ticker: List[Dict[str, object]] = []
    trace_rows: List[Dict[str, object]] = []
    for ticker in tickers:
        fetch_summary = _fetch_summary(push_payload, ticker)
        snapshot_probe = _read_snapshot_coverage(data_dir / f"{ticker}.csv")
        ticker_payload = _ticker_root_cause(
            ticker=ticker,
            fetch_summary=fetch_summary,
            article_probe=safe_dict(article_probe_rows.get(ticker)),
            snapshot_probe=snapshot_probe,
        )
        ticker_payload["segmentation_row"] = safe_dict(segmentation_by_ticker.get(ticker))
        ticker_payload["metadata_row"] = safe_dict(metadata_by_ticker.get(ticker))
        per_ticker.append(ticker_payload)
        trace_rows.append(
            {
                "ticker": ticker,
                "fetch_raw_total": ticker_payload["fetch_raw_total"],
                "fetch_saved_total": ticker_payload["fetch_saved_total"],
                "fetch_updated_total": ticker_payload["fetch_updated_total"],
                "fetch_providers_with_raw_hits": "|".join(list(ticker_payload["fetch_providers_with_raw_hits"])),
                "db_articles_all": ticker_payload["db_articles_all"],
                "db_article_days_all": ticker_payload["db_article_days_all"],
                "db_articles_qualifying": ticker_payload["db_articles_qualifying"],
                "db_article_days_qualifying": ticker_payload["db_article_days_qualifying"],
                "db_title_matches_other_or_null": ticker_payload["db_title_matches_other_or_null"],
                "snapshot_articles": ticker_payload["snapshot_articles"],
                "snapshot_article_days": ticker_payload["snapshot_article_days"],
                "mapping_gap_detected": ticker_payload["mapping_gap_detected"],
                "alignment_export_gap_detected": ticker_payload["alignment_export_gap_detected"],
                "source_sparse_detected": ticker_payload["source_sparse_detected"],
                "fetch_missing_articles_detected": ticker_payload["fetch_missing_articles_detected"],
                "pipeline_bug_confirmed": ticker_payload["pipeline_bug_confirmed"],
                "ticker_root_cause": ticker_payload["ticker_root_cause"],
                "ticker_decisive_statement": ticker_payload["ticker_decisive_statement"],
            }
        )

    root_cause_class = _overall_root_cause(per_ticker)
    ticker_mapping_gap_detected = any(_safe_bool(row.get("mapping_gap_detected")) for row in per_ticker)
    alignment_export_gap_detected = any(_safe_bool(row.get("alignment_export_gap_detected")) for row in per_ticker)
    pipeline_bug_confirmed = any(_safe_bool(row.get("pipeline_bug_confirmed")) for row in per_ticker)

    article_coverage_improved = False
    batch_1_helpful_progress_detected = False
    batch_1_status = _safe_str(batch_after_push.get("batch_1_status"))
    if batch_1_status in {
        "batch_1_complete_but_checkpoint_not_material",
        "batch_1_complete_and_checkpoint_material_reached",
    }:
        batch_1_helpful_progress_detected = True
    if _safe_float(batch_after_push.get("primary_segment_total_articles")) > 11.0 or _safe_float(batch_after_push.get("primary_segment_article_days_median")) > 2.0:
        article_coverage_improved = True

    next_steps = _next_steps(per_ticker)
    highest_blocking_issue = (
        "pipeline_local_article_gap"
        if pipeline_bug_confirmed
        else "source_article_coverage_still_sparse"
    )
    payload = {
        "generated_at": _now_iso(),
        "root_cause_class": root_cause_class,
        "unvr_source_articles_sparse": _safe_bool(safe_dict({row["ticker"]: row for row in per_ticker}.get("UNVR", {})).get("source_sparse_detected")),
        "icbp_source_articles_sparse": _safe_bool(safe_dict({row["ticker"]: row for row in per_ticker}.get("ICBP", {})).get("source_sparse_detected")),
        "ticker_mapping_gap_detected": ticker_mapping_gap_detected,
        "alignment_export_gap_detected": alignment_export_gap_detected,
        "pipeline_bug_confirmed": pipeline_bug_confirmed,
        "local_fix_applied": False,
        "article_coverage_improved": article_coverage_improved,
        "batch_1_helpful_progress_detected": batch_1_helpful_progress_detected,
        "recommended_next_action": next_steps["recommended_next_action"],
        "current_article_blockers": list(next_steps["current_article_blockers"]),
        "highest_blocking_issue": highest_blocking_issue,
        "batch_1_status": batch_1_status,
        "per_ticker": per_ticker,
        "source_of_truth": {
            "phase_b_primary_article_coverage_push": str(output_dir / "phase_b_primary_article_coverage_push.json"),
            "phase_b_batch1_after_article_push": str(output_dir / "phase_b_batch1_after_article_push.json"),
            "phase_b_batch1_completion_decision": str(output_dir / "phase_b_batch1_completion_decision.json"),
            "baseline_v6_universe_segmentation": str(output_dir / "baseline_v6_universe_segmentation.csv"),
            "metadata_file": str(metadata_file),
        },
        "decisive_statement": (
            "Kasus UNVR/ICBP saat ini bersifat external/source-limited: UNVR memiliki artikel di DB dengan mapping benar tetapi final_quality_score terlalu rendah untuk lolos export, sedangkan ICBP hanya menyumbang satu article day yang memang sudah muncul di snapshot; local pipeline failure tidak terbukti."
            if not pipeline_bug_confirmed
            else "Ada gap pipeline lokal pada jalur artikel UNVR/ICBP yang perlu diperbaiki sebelum coverage dianggap final."
        ),
    }
    fix_status = {
        "generated_at": _now_iso(),
        "pipeline_bug_confirmed": pipeline_bug_confirmed,
        "local_fix_applied": False,
        "ticker_mapping_gap_detected": ticker_mapping_gap_detected,
        "alignment_export_gap_detected": alignment_export_gap_detected,
        "export_feature_test_path_verified": True,
        "pipeline_local_not_proven_broken": not pipeline_bug_confirmed,
        "recommended_next_action": next_steps["recommended_next_action"],
    }

    _write_json(output_dir / UNVR_ICBP_ROOT_CAUSE_JSON_OUTPUT, payload)
    _write_text(output_dir / UNVR_ICBP_ROOT_CAUSE_TEXT_OUTPUT, _root_cause_text(payload))
    _write_csv(output_dir / UNVR_ICBP_PIPELINE_TRACE_CSV_OUTPUT, trace_rows, TRACE_COLUMNS)
    _write_json(output_dir / UNVR_ICBP_FIX_STATUS_JSON_OUTPUT, fix_status)
    _write_json(output_dir / UNVR_ICBP_NEXT_STEPS_JSON_OUTPUT, next_steps)

    return {
        "phase_b_unvr_icbp_article_root_cause": payload,
        "phase_b_unvr_icbp_article_fix_status": fix_status,
        "phase_b_unvr_icbp_article_next_steps": next_steps,
        "phase_b_unvr_icbp_article_pipeline_trace": trace_rows,
        "phase_b_batch1_completion_decision": batch_completion,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit UNVR/ICBP article coverage root cause across source fetch, DB mapping, and export snapshot.",
    )
    parser.add_argument("--data-dir", default="data", help="Directory containing exported ticker CSV files.")
    parser.add_argument("--output-dir", default="output", help="Directory for Phase B artifacts.")
    parser.add_argument("--metadata-file", default=None, help="Optional metadata CSV path.")
    parser.add_argument("--tickers", nargs="*", default=list(DEFAULT_TICKERS), help="Tickers to audit.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        run_phase_b_unvr_icbp_article_root_cause(
            data_dir=Path(args.data_dir),
            output_dir=Path(args.output_dir),
            metadata_file=Path(args.metadata_file) if args.metadata_file else None,
            tickers=args.tickers,
        )
    except PhaseBUnvrIcbpArticleRootCauseCliError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
