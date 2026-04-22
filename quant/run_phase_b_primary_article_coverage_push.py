"""Push primary article coverage for Phase B batch-1 and verify whether completion status changes."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from quant.phase_a_transition_utils import dedupe, read_json_object, safe_dict
from quant.run_phase_b_data_extension_execution_plan import (
    _load_artifacts as _load_execution_artifacts,
    _load_metadata_or_prices,
    _parse_segment_spec as _execution_parse_segment_spec,
    _load_segmentation,
    _load_v9_results,
    _merge_ticker_context,
    _methodology as _execution_methodology,
    _primary_segment as _execution_primary_segment,
    _primary_trade_lookup as _execution_primary_trade_lookup,
    _safe_segments as _execution_safe_segments,
)
from quant.run_phase_b_batch1_completion_check import run_phase_b_batch1_completion_check


PRIMARY_ARTICLE_PUSH_JSON_OUTPUT = "phase_b_primary_article_coverage_push.json"
PRIMARY_ARTICLE_PUSH_TEXT_OUTPUT = "phase_b_primary_article_coverage_push.txt"
PRIMARY_ARTICLE_BREAKDOWN_CSV_OUTPUT = "phase_b_primary_article_coverage_ticker_breakdown.csv"
PRIMARY_ARTICLE_DROP_REASONS_JSON_OUTPUT = "phase_b_primary_article_drop_reasons_per_provider.json"
PRIMARY_ARTICLE_DROP_SAMPLES_JSON_OUTPUT = "phase_b_primary_article_dropped_samples_per_provider.json"
PRIMARY_ARTICLE_OFFICIAL_DELTA_JSON_OUTPUT = "phase_b_primary_article_official_metric_delta_per_ticker.json"
PRIMARY_ARTICLE_PRIMARY_MEMBERSHIP_JSON_OUTPUT = "phase_b_official_primary_segment_membership_audit.json"
BBCA_ARTICLE_DAY_AUDIT_JSON_OUTPUT = "bbca_article_day_audit.json"
BATCH1_AFTER_PUSH_JSON_OUTPUT = "phase_b_batch1_after_article_push.json"
BATCH1_AFTER_PUSH_TEXT_OUTPUT = "phase_b_batch1_after_article_push.txt"

BREAKDOWN_COLUMNS = [
    "ticker",
    "before_snapshot_articles",
    "before_snapshot_article_days",
    "db_before_articles",
    "db_before_article_days",
    "fetch_attempted",
    "fetch_saved_total",
    "fetch_updated_total",
    "fetch_raw_total",
    "providers_with_raw_hits",
    "providers_with_saved_hits",
    "db_after_articles",
    "db_after_article_days",
    "after_snapshot_articles",
    "after_snapshot_article_days",
    "snapshot_article_delta",
    "snapshot_article_days_delta",
    "still_blocking",
]

DEFAULT_PRIORITY_TICKERS = ["BBCA", "BMRI", "GOTO", "INDF", "UNVR"]
DEFAULT_PROVIDER_PLAN = [
    "google_news_rss",
    "idx_disclosure",
    "business_site_search",
    "gnews",
    "rss_local",
    "newsapi",
    "finnhub",
    "gdelt",
]

FETCH_RESULT_PATTERN = re.compile(
    r"(?P<ticker>[A-Z0-9]+): raw (?P<raw>\d+), saved (?P<saved>\d+), updated (?P<updated>\d+)",
    re.IGNORECASE,
)
FETCH_RESULT_JSON_PREFIX = "FETCH_RESULT_JSON:"


class PhaseBPrimaryArticleCoveragePushCliError(ValueError):
    """Friendly CLI error for Phase B primary article coverage push."""


CommandExecutor = Callable[[Sequence[str], Path], Dict[str, object]]
CoverageProbe = Callable[[Sequence[str], Path], Dict[str, Dict[str, object]]]
ArticleDetailProbe = Callable[[str, Path], Dict[str, object]]
AfterFetchHook = Callable[[Path, Path, Path], None]


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


def _normalize_dropped_samples(value: object) -> Dict[str, List[Dict[str, object]]]:
    payload = safe_dict(value)
    normalized: Dict[str, List[Dict[str, object]]] = {}
    for bucket in ("relevance", "quality", "exclusion"):
        rows: List[Dict[str, object]] = []
        for item in list(payload.get(bucket) or []):
            rows.append(safe_dict(item))
        normalized[bucket] = rows
    return normalized


def _load_required_json(path: Path, label: str) -> Dict[str, object]:
    payload, warnings = read_json_object(path, label)
    if payload is None:
        raise PhaseBPrimaryArticleCoveragePushCliError(
            f"Required artifact missing or invalid: {path}" + (f" ({'; '.join(warnings)})" if warnings else "")
        )
    return safe_dict(payload)


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


def _default_coverage_probe(tickers: Sequence[str], cwd: Path) -> Dict[str, Dict[str, object]]:
    php_code = (
        'require "vendor/autoload.php"; '
        '$app = require "bootstrap/app.php"; '
        '$app->make(Illuminate\\Contracts\\Console\\Kernel::class)->bootstrap(); '
        f'$tickers = json_decode({json.dumps(json.dumps(list(tickers)))}, true); '
        '$threshold = (float) config("news.final_quality_threshold", 0.4); '
        '$payload = []; '
        'foreach ($tickers as $code) { '
        '  $stock = App\\Models\\Stock::where("code", $code)->first(); '
        '  if (! $stock) { $payload[$code] = ["article_count_total" => 0, "article_days" => 0, "high_quality_count" => 0, "by_provider" => []]; continue; } '
        '  $rows = App\\Models\\NewsArticle::where("stock_id", $stock->id)->whereNotNull("published_at")->get(["published_at", "final_quality_score", "source_provider"]); '
        '  $articleCount = $rows->count(); '
        '  $articleDays = $rows->groupBy(fn ($r) => optional($r->published_at)->toDateString())->count(); '
        '  $highQuality = $rows->filter(fn ($r) => ((float) ($r->final_quality_score ?? 0.0)) >= $threshold)->count(); '
        '  $providers = $rows->groupBy(fn ($r) => $r->source_provider ?: "unknown")->map(fn ($g) => $g->count())->all(); '
        '  $payload[$code] = ["article_count_total" => $articleCount, "article_days" => $articleDays, "high_quality_count" => $highQuality, "by_provider" => $providers]; '
        '} '
        'echo json_encode($payload, JSON_PRETTY_PRINT);'
    )
    result = _default_command_executor(["php", "-r", php_code], cwd)
    if not result["succeeded"]:
        raise PhaseBPrimaryArticleCoveragePushCliError(f"Coverage probe failed: {result['combined_output']}")
    try:
        payload = json.loads(_safe_str(result["stdout"], "{}") or "{}")
    except json.JSONDecodeError as exc:
        raise PhaseBPrimaryArticleCoveragePushCliError(f"Coverage probe returned invalid JSON: {result['stdout']}") from exc
    return {str(key).upper(): safe_dict(value) for key, value in safe_dict(payload).items()}


def _default_article_detail_probe(ticker: str, cwd: Path) -> Dict[str, object]:
    php_code = (
        'require "vendor/autoload.php"; '
        '$app = require "bootstrap/app.php"; '
        '$app->make(Illuminate\\Contracts\\Console\\Kernel::class)->bootstrap(); '
        f'$ticker = {json.dumps(str(ticker).upper())}; '
        '$stock = App\\Models\\Stock::where("code", $ticker)->first(); '
        'if (! $stock) { echo json_encode(["ticker" => $ticker, "rows" => []], JSON_PRETTY_PRINT); return; } '
        '$rows = App\\Models\\NewsArticle::where("stock_id", $stock->id)->whereNotNull("published_at")->orderBy("published_at", "desc")->get(["title", "published_at", "source_provider", "source_url", "final_quality_score"]); '
        '$payload = ["ticker" => $ticker, "rows" => []]; '
        'foreach ($rows as $row) { '
        '  $payload["rows"][] = ['
        '    "title" => (string) ($row->title ?? ""), '
        '    "published_date" => optional($row->published_at)->toDateString(), '
        '    "source_provider" => (string) ($row->source_provider ?? "unknown"), '
        '    "source_url" => (string) ($row->source_url ?? ""), '
        '    "final_quality_score" => $row->final_quality_score === null ? null : round((float) $row->final_quality_score, 5), '
        '  ]; '
        '} '
        'echo json_encode($payload, JSON_PRETTY_PRINT);'
    )
    result = _default_command_executor(["php", "-r", php_code], cwd)
    if not result["succeeded"]:
        raise PhaseBPrimaryArticleCoveragePushCliError(f"Article detail probe failed: {result['combined_output']}")
    try:
        payload = json.loads(_safe_str(result.get("stdout"), "{}") or "{}")
    except json.JSONDecodeError as exc:
        raise PhaseBPrimaryArticleCoveragePushCliError(
            f"Article detail probe returned invalid JSON for {ticker}: {result.get('stdout')}"
        ) from exc
    return safe_dict(payload)


def _before_snapshot_lookup(batch1_completion: Dict[str, object]) -> Dict[str, Dict[str, object]]:
    article_status = safe_dict(batch1_completion.get("article_day_status"))
    return {
        _safe_str(row.get("ticker")).upper(): safe_dict(row)
        for row in list(article_status.get("per_ticker") or [])
        if _safe_str(safe_dict(row).get("ticker"))
    }


def _after_snapshot_lookup(batch1_completion: Dict[str, object]) -> Dict[str, Dict[str, object]]:
    article_status = safe_dict(batch1_completion.get("article_day_status"))
    return {
        _safe_str(row.get("ticker")).upper(): safe_dict(row)
        for row in list(article_status.get("per_ticker") or [])
        if _safe_str(safe_dict(row).get("ticker"))
    }


def _official_primary_metrics(payload: Dict[str, object]) -> Tuple[float, float]:
    progress_payload = safe_dict(payload.get("post_backfill_progress_update"))
    progress_since = safe_dict(progress_payload.get("progress_since_baseline_v9"))
    primary_articles = _safe_float(
        safe_dict(progress_since.get("primary_segment_total_articles")).get("current"),
        _safe_float(payload.get("primary_segment_total_articles")),
    )
    primary_median = _safe_float(
        safe_dict(progress_since.get("primary_segment_article_days_median")).get("current"),
        _safe_float(payload.get("primary_segment_article_days_median")),
    )
    return primary_articles, primary_median


def _parse_fetch_metrics(result: Dict[str, object]) -> Dict[str, object]:
    combined_output = _safe_str(result.get("combined_output"))
    for line in reversed(combined_output.splitlines()):
        stripped = line.strip()
        if not stripped.startswith(FETCH_RESULT_JSON_PREFIX):
            continue
        payload_text = stripped[len(FETCH_RESULT_JSON_PREFIX):].strip()
        try:
            payload = safe_dict(json.loads(payload_text))
        except json.JSONDecodeError:
            continue
        return {
            "raw": _safe_int(payload.get("raw")),
            "saved": _safe_int(payload.get("saved")),
            "updated": _safe_int(payload.get("updated")),
            "dropped_relevance": _safe_int(payload.get("dropped_relevance")),
            "dropped_quality": _safe_int(payload.get("dropped_quality")),
            "dropped_exclusion": _safe_int(payload.get("dropped_exclusion")),
            "skipped_dedup": _safe_int(payload.get("skipped_dedup")),
            "failed": _safe_int(payload.get("failed")),
            "dropped_samples": _normalize_dropped_samples(payload.get("dropped_samples")),
        }
    match = FETCH_RESULT_PATTERN.search(_safe_str(result.get("combined_output")))
    if not match:
        return {
            "raw": 0,
            "saved": 0,
            "updated": 0,
            "dropped_relevance": 0,
            "dropped_quality": 0,
            "dropped_exclusion": 0,
            "skipped_dedup": 0,
            "failed": 0 if _safe_bool(result.get("succeeded")) else 1,
            "dropped_samples": _normalize_dropped_samples(None),
        }
    return {
        "raw": _safe_int(match.group("raw")),
        "saved": _safe_int(match.group("saved")),
        "updated": _safe_int(match.group("updated")),
        "dropped_relevance": 0,
        "dropped_quality": 0,
        "dropped_exclusion": 0,
        "skipped_dedup": 0,
        "failed": 0 if _safe_bool(result.get("succeeded")) else 1,
        "dropped_samples": _normalize_dropped_samples(None),
    }


def _build_fetch_plan(priority_tickers: Sequence[str], providers: Sequence[str]) -> List[Tuple[str, str]]:
    plan: List[Tuple[str, str]] = []
    for ticker in priority_tickers:
        for provider in providers:
            plan.append((ticker, provider))
    return plan


def _run_fetch_plan(
    *,
    root: Path,
    plan: Sequence[Tuple[str, str]],
    command_executor: CommandExecutor,
) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for ticker, provider in plan:
        command = ["php", "artisan", "news:fetch", f"--stock={ticker}", f"--provider={provider}", "--limit=10", "--debug"]
        result = command_executor(command, root)
        metrics = _parse_fetch_metrics(result)
        rows.append(
            {
                "ticker": ticker,
                "provider": provider,
                "command": " ".join(command),
                "succeeded": _safe_bool(result.get("succeeded")),
                "returncode": _safe_int(result.get("returncode")),
                "raw": metrics["raw"],
                "saved": metrics["saved"],
                "updated": metrics["updated"],
                "dropped_relevance": metrics["dropped_relevance"],
                "dropped_quality": metrics["dropped_quality"],
                "dropped_exclusion": metrics["dropped_exclusion"],
                "skipped_dedup": metrics["skipped_dedup"],
                "failed": metrics["failed"],
                "dropped_samples": metrics["dropped_samples"],
                "combined_output": _safe_str(result.get("combined_output")),
            }
        )
    return rows


def _summarize_fetch_rows(rows: Sequence[Dict[str, object]], ticker: str) -> Dict[str, object]:
    subset = [safe_dict(row) for row in rows if _safe_str(safe_dict(row).get("ticker")).upper() == ticker.upper()]
    return {
        "fetch_attempted": bool(subset),
        "fetch_saved_total": sum(_safe_int(row.get("saved")) for row in subset),
        "fetch_updated_total": sum(_safe_int(row.get("updated")) for row in subset),
        "fetch_raw_total": sum(_safe_int(row.get("raw")) for row in subset),
        "providers_with_raw_hits": [row["provider"] for row in subset if _safe_int(row.get("raw")) > 0],
        "providers_with_saved_hits": [row["provider"] for row in subset if (_safe_int(row.get("saved")) + _safe_int(row.get("updated"))) > 0],
    }


def _build_provider_contribution_summary(rows: Sequence[Dict[str, object]], ticker: str) -> List[Dict[str, object]]:
    subset = [safe_dict(row) for row in rows if _safe_str(safe_dict(row).get("ticker")).upper() == ticker.upper()]
    summary: List[Dict[str, object]] = []
    for item in subset:
        summary.append(
            {
                "provider": _safe_str(item.get("provider")),
                "raw_count": _safe_int(item.get("raw")),
                "saved_count": _safe_int(item.get("saved")),
                "updated_count": _safe_int(item.get("updated")),
                "dropped_relevance": _safe_int(item.get("dropped_relevance")),
                "dropped_quality": _safe_int(item.get("dropped_quality")),
                "dropped_exclusion": _safe_int(item.get("dropped_exclusion")),
                "failed": _safe_int(item.get("failed")),
            }
        )
    return summary


def _official_primary_metric_rows(
    *,
    data_dir: Path,
    output_dir: Path,
    metadata_file: Path,
) -> Dict[str, Dict[str, object]]:
    artifacts, _, _ = _load_execution_artifacts(output_dir=output_dir)
    primary_segment = _execution_primary_segment(artifacts=artifacts)
    safe_segments = _execution_safe_segments(artifacts=artifacts, output_dir=output_dir)
    methodology = _execution_methodology(artifacts=artifacts)
    metadata_df, _ = _load_metadata_or_prices(data_dir=data_dir, metadata_file=metadata_file)
    segmentation_df, _ = _load_segmentation(output_dir=output_dir)
    v9_results, _ = _load_v9_results(output_dir=output_dir)
    primary_trades, primary_trade_shares, _ = _execution_primary_trade_lookup(
        v9_results=v9_results,
        primary_segment=primary_segment,
    )
    working = _merge_ticker_context(
        metadata_df=metadata_df,
        segmentation_df=segmentation_df,
        primary_segment=primary_segment,
        safe_segments=safe_segments,
        methodology=methodology,
        primary_trades=primary_trades,
        primary_trade_shares=primary_trade_shares,
    )
    if working.empty or "is_primary_segment" not in working.columns:
        return {}
    subset = working.loc[working["is_primary_segment"].astype(bool)].copy()
    if subset.empty:
        return {}
    rows: Dict[str, Dict[str, object]] = {}
    for _, item in subset.sort_values(["ticker"]).iterrows():
        ticker = _safe_str(item.get("ticker")).upper()
        if not ticker:
            continue
        rows[ticker] = {
            "ticker": ticker,
            "news_count_total_current": _safe_int(item.get("news_count_total")),
            "article_days_current": _safe_int(item.get("article_days")),
            "history_rows_current": _safe_int(item.get("history_rows")),
            "news_segment": _safe_str(item.get("news_segment")),
            "sentiment_segment": _safe_str(item.get("sentiment_segment")),
            "primary_oos_trades_current": _safe_int(item.get("primary_oos_trades_current")),
            "ticker_trade_share_primary": _safe_float(item.get("ticker_trade_share_primary")),
        }
    return rows


def _official_primary_selection_working(
    *,
    data_dir: Path,
    output_dir: Path,
    metadata_file: Path,
) -> Dict[str, object]:
    artifacts, _, _ = _load_execution_artifacts(output_dir=output_dir)
    primary_segment = _execution_primary_segment(artifacts=artifacts)
    primary_field, primary_value = _execution_parse_segment_spec(primary_segment)
    safe_segments = _execution_safe_segments(artifacts=artifacts, output_dir=output_dir)
    methodology = _execution_methodology(artifacts=artifacts)
    metadata_df, _ = _load_metadata_or_prices(data_dir=data_dir, metadata_file=metadata_file)
    segmentation_df, _ = _load_segmentation(output_dir=output_dir)
    v9_results, _ = _load_v9_results(output_dir=output_dir)
    primary_trades, primary_trade_shares, _ = _execution_primary_trade_lookup(
        v9_results=v9_results,
        primary_segment=primary_segment,
    )
    working = _merge_ticker_context(
        metadata_df=metadata_df,
        segmentation_df=segmentation_df,
        primary_segment=primary_segment,
        safe_segments=safe_segments,
        methodology=methodology,
        primary_trades=primary_trades,
        primary_trade_shares=primary_trade_shares,
    )
    working_rows: Dict[str, Dict[str, object]] = {}
    if not working.empty:
        for _, item in working.sort_values(["ticker"]).iterrows():
            ticker = _safe_str(item.get("ticker")).upper()
            if ticker:
                working_rows[ticker] = {
                    key: item.get(key)
                    for key in item.index.tolist()
                }
    return {
        "artifacts": artifacts,
        "primary_segment_spec": primary_segment,
        "primary_field": primary_field,
        "primary_value": primary_value,
        "working_rows": working_rows,
    }


def _build_primary_segment_membership_audit_payload(
    *,
    data_dir: Path,
    output_dir: Path,
    metadata_file: Path,
    priority_tickers: Sequence[str],
    after_completion: Dict[str, object],
) -> Dict[str, object]:
    selection = _official_primary_selection_working(
        data_dir=data_dir,
        output_dir=output_dir,
        metadata_file=metadata_file,
    )
    primary_segment_spec = _safe_str(selection.get("primary_segment_spec"))
    primary_field = _safe_str(selection.get("primary_field"))
    primary_value = _safe_str(selection.get("primary_value"))
    working_rows = {
        _safe_str(key).upper(): safe_dict(value)
        for key, value in safe_dict(selection.get("working_rows")).items()
    }
    post_backfill_decision = safe_dict(after_completion.get("post_backfill_batch1_decision"))
    verification_lookup = {
        _safe_str(row.get("ticker")).upper(): safe_dict(row)
        for row in list(post_backfill_decision.get("priority_ticker_verification") or [])
        if _safe_str(safe_dict(row).get("ticker"))
    }
    official_primary_tickers = [
        ticker for ticker, row in working_rows.items()
        if _safe_bool(row.get("is_primary_segment"))
    ]
    tickers_to_audit = dedupe([
        *list(priority_tickers),
        *list(official_primary_tickers),
    ])

    rows: List[Dict[str, object]] = []
    for ticker in tickers_to_audit:
        working_row = safe_dict(working_rows.get(ticker))
        verification_row = safe_dict(verification_lookup.get(ticker))
        actual_value = _safe_str(working_row.get(primary_field))
        included = _safe_bool(working_row.get("is_primary_segment"))
        if not working_row:
            reason = (
                "excluded because ticker is missing from the merged metadata+segmentation working set used by "
                "run_phase_b_data_extension_progress_update"
            )
        elif included:
            reason = (
                f"included because baseline_v6_universe_segmentation.csv.{primary_field}={actual_value} "
                f"matches phase_b_retest_readiness_gate.primary_segment={primary_segment_spec}"
            )
        else:
            reason = (
                f"excluded because baseline_v6_universe_segmentation.csv.{primary_field}={actual_value or '-'} "
                f"does not match phase_b_retest_readiness_gate.primary_segment={primary_segment_spec}"
            )

        if verification_row:
            reason = (
                f"{reason}; post_backfill_batch1_decision.priority_ticker_verification "
                f"is_primary_segment={_safe_bool(verification_row.get('is_primary_segment'))}"
            )
        else:
            reason = (
                f"{reason}; ticker is absent from post_backfill_batch1_decision.priority_ticker_verification "
                "so it does not participate in current batch priority verification"
            )

        article_count = _safe_int(
            verification_row.get("news_count_total_current"),
            _safe_int(working_row.get("news_count_total")),
        )
        article_days = _safe_int(
            verification_row.get("article_days_current"),
            _safe_int(working_row.get("article_days")),
        )
        still_blocking = included and article_days < 3
        rows.append(
            {
                "ticker": ticker,
                "included_in_official_primary_segment": included,
                "selection_field": primary_field,
                "selection_value_required": primary_value,
                "selection_value_actual": actual_value,
                "in_current_batch_priority_verification": bool(verification_row),
                "current_batch_verification_is_primary_segment": _safe_bool(verification_row.get("is_primary_segment")),
                "official_article_count_current": article_count,
                "official_article_days_current": article_days,
                "still_blocking": still_blocking,
                "reason": reason,
                "source_artifact_reference": {
                    "source_of_truth_artifact": "output/phase_b_retest_readiness_gate.json",
                    "source_of_truth_field": "primary_segment",
                    "segmentation_artifact": "output/baseline_v6_universe_segmentation.csv",
                    "post_backfill_decision_artifact": "output/phase_b_batch1_completion_decision.json",
                },
            }
        )

    return {
        "generated_at": _now_iso(),
        "source_of_truth_artifact": "output/phase_b_retest_readiness_gate.json",
        "source_of_truth_field": "primary_segment",
        "source_of_truth_value": primary_segment_spec,
        "official_primary_segment_selection_basis": (
            "run_phase_b_data_extension_progress_update marks a ticker as official primary when the current "
            "baseline_v6_universe_segmentation.csv value at the source-of-truth field matches the primary_segment gate; "
            "progress_since_baseline_v9 then aggregates only those rows."
        ),
        "official_primary_segment_tickers": official_primary_tickers,
        "selection_pipeline": [
            "phase_b_retest_readiness_gate.primary_segment",
            "baseline_v6_universe_segmentation.csv.<selection_field>",
            "run_phase_b_data_extension_execution_plan._merge_ticker_context -> is_primary_segment",
            "phase_b_data_extension_progress_update.progress_since_baseline_v9.primary_segment_total_articles",
            "phase_b_data_extension_progress_update.progress_since_baseline_v9.primary_segment_article_days_median",
        ],
        "rows": rows,
    }


def _build_breakdown_rows(
    *,
    priority_tickers: Sequence[str],
    before_snapshot: Dict[str, Dict[str, object]],
    db_before: Dict[str, Dict[str, object]],
    db_after: Dict[str, Dict[str, object]],
    after_snapshot: Dict[str, Dict[str, object]],
    fetch_rows: Sequence[Dict[str, object]],
) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for ticker in priority_tickers:
        before_row = safe_dict(before_snapshot.get(ticker))
        after_row = safe_dict(after_snapshot.get(ticker))
        db_before_row = safe_dict(db_before.get(ticker))
        db_after_row = safe_dict(db_after.get(ticker))
        fetch_summary = _summarize_fetch_rows(fetch_rows, ticker)
        after_days = _safe_int(after_row.get("article_days_current"))
        after_articles = _safe_int(after_row.get("news_count_total_current"))
        rows.append(
            {
                "ticker": ticker,
                "before_snapshot_articles": _safe_int(before_row.get("news_count_total_current")),
                "before_snapshot_article_days": _safe_int(before_row.get("article_days_current")),
                "db_before_articles": _safe_int(db_before_row.get("article_count_total")),
                "db_before_article_days": _safe_int(db_before_row.get("article_days")),
                "fetch_attempted": fetch_summary["fetch_attempted"],
                "fetch_saved_total": fetch_summary["fetch_saved_total"],
                "fetch_updated_total": fetch_summary["fetch_updated_total"],
                "fetch_raw_total": fetch_summary["fetch_raw_total"],
                "providers_with_raw_hits": "|".join(dedupe(fetch_summary["providers_with_raw_hits"])),
                "providers_with_saved_hits": "|".join(dedupe(fetch_summary["providers_with_saved_hits"])),
                "db_after_articles": _safe_int(db_after_row.get("article_count_total")),
                "db_after_article_days": _safe_int(db_after_row.get("article_days")),
                "after_snapshot_articles": after_articles,
                "after_snapshot_article_days": after_days,
                "snapshot_article_delta": after_articles - _safe_int(before_row.get("news_count_total_current")),
                "snapshot_article_days_delta": after_days - _safe_int(before_row.get("article_days_current")),
                "still_blocking": after_days < 3,
            }
        )
    return rows


def _build_official_metric_delta_payload(
    *,
    priority_tickers: Sequence[str],
    before_official_rows: Dict[str, Dict[str, object]],
    after_official_rows: Dict[str, Dict[str, object]],
    db_before: Dict[str, Dict[str, object]],
    db_after: Dict[str, Dict[str, object]],
    fetch_rows: Sequence[Dict[str, object]],
) -> Dict[str, object]:
    rows: List[Dict[str, object]] = []
    official_tickers = dedupe([
        *list(before_official_rows.keys()),
        *list(after_official_rows.keys()),
    ])
    for ticker in official_tickers:
        before_row = safe_dict(before_official_rows.get(ticker))
        after_row = safe_dict(after_official_rows.get(ticker))
        db_before_row = safe_dict(db_before.get(ticker))
        db_after_row = safe_dict(db_after.get(ticker))
        before_articles = _safe_int(before_row.get("news_count_total_current"))
        after_articles = _safe_int(after_row.get("news_count_total_current"))
        before_days = _safe_int(before_row.get("article_days_current"))
        after_days = _safe_int(after_row.get("article_days_current"))
        before_high_quality = _safe_int(db_before_row.get("high_quality_count"))
        after_high_quality = _safe_int(db_after_row.get("high_quality_count"))
        rows.append(
            {
                "ticker": ticker,
                "before_article_count_total": before_articles,
                "after_article_count_total": after_articles,
                "delta_article_count_total": after_articles - before_articles,
                "before_article_days": before_days,
                "after_article_days": after_days,
                "delta_article_days": after_days - before_days,
                "before_snapshot_articles": before_articles,
                "after_snapshot_articles": after_articles,
                "before_snapshot_article_days": before_days,
                "after_snapshot_article_days": after_days,
                "before_high_quality_count": before_high_quality,
                "after_high_quality_count": after_high_quality,
                "history_rows_current_before": _safe_int(before_row.get("history_rows_current")),
                "history_rows_current_after": _safe_int(after_row.get("history_rows_current")),
                "primary_oos_trades_current": _safe_int(after_row.get("primary_oos_trades_current")),
                "ticker_trade_share_primary": _safe_float(after_row.get("ticker_trade_share_primary")),
                "db_before_articles": _safe_int(db_before_row.get("article_count_total")),
                "db_after_articles": _safe_int(db_after_row.get("article_count_total")),
                "db_delta_articles": _safe_int(db_after_row.get("article_count_total")) - _safe_int(db_before_row.get("article_count_total")),
                "db_before_article_days": _safe_int(db_before_row.get("article_days")),
                "db_after_article_days": _safe_int(db_after_row.get("article_days")),
                "db_delta_article_days": _safe_int(db_after_row.get("article_days")) - _safe_int(db_before_row.get("article_days")),
                "was_in_fetch_priority_plan": ticker in {item.upper() for item in priority_tickers},
                "provider_contribution_summary": _build_provider_contribution_summary(fetch_rows, ticker),
                "still_blocking": after_days < 3 or after_articles < 4,
            }
        )

    total_before = round(sum(_safe_float(row.get("before_article_count_total")) for row in rows), 4)
    total_after = round(sum(_safe_float(row.get("after_article_count_total")) for row in rows), 4)
    total_delta = round(total_after - total_before, 4)
    before_days_vector = sorted(_safe_float(row.get("before_article_days")) for row in rows)
    after_days_vector = sorted(_safe_float(row.get("after_article_days")) for row in rows)

    def _median(values: Sequence[float]) -> float:
        if not values:
            return 0.0
        midpoint = len(values) // 2
        if len(values) % 2 == 1:
            return round(float(values[midpoint]), 4)
        return round(float(values[midpoint - 1] + values[midpoint]) / 2.0, 4)

    median_before = _median(before_days_vector)
    median_after = _median(after_days_vector)
    median_delta = round(median_after - median_before, 4)

    top_negative = sorted(
        rows,
        key=lambda row: (
            _safe_float(row.get("delta_article_count_total")),
            _safe_float(row.get("delta_article_days")),
            _safe_str(row.get("ticker")),
        ),
    )
    top_negative = [row for row in top_negative if _safe_float(row.get("delta_article_count_total")) < 0 or _safe_float(row.get("delta_article_days")) < 0][:5]
    top_negative_contributors = [
        {
            "ticker": _safe_str(row.get("ticker")).upper(),
            "delta_article_count_total": _safe_int(row.get("delta_article_count_total")),
            "delta_article_days": _safe_int(row.get("delta_article_days")),
            "before_article_count_total": _safe_int(row.get("before_article_count_total")),
            "after_article_count_total": _safe_int(row.get("after_article_count_total")),
            "before_article_days": _safe_int(row.get("before_article_days")),
            "after_article_days": _safe_int(row.get("after_article_days")),
        }
        for row in top_negative
    ]

    return {
        "generated_at": _now_iso(),
        "priority_tickers_checked": list(priority_tickers),
        "official_primary_tickers_checked": official_tickers,
        "official_metric_basis": (
            "Derived from the official progress tracker basis used by "
            "post_backfill_progress_update.progress_since_baseline_v9: metadata + segmentation merged "
            "through the primary segment definition, then aggregated with primary_segment_total_articles "
            "and primary_segment_article_days_median."
        ),
        "priority_tickers_outside_official_primary_segment": [
            ticker for ticker in priority_tickers if ticker not in set(official_tickers)
        ],
        "official_primary_tickers_missing_from_fetch_plan": [
            ticker for ticker in official_tickers if ticker not in {item.upper() for item in priority_tickers}
        ],
        "total_before": total_before,
        "total_after": total_after,
        "total_delta": total_delta,
        "median_before": median_before,
        "median_after": median_after,
        "median_delta": median_delta,
        "top_negative_contributors": top_negative_contributors,
        "rows": rows,
    }


def _build_push_text(payload: Dict[str, object]) -> List[str]:
    return [
        "Phase B Primary Article Coverage Push",
        f"- priority_tickers_checked={', '.join(list(payload.get('priority_tickers_checked') or []))}",
        f"- primary_segment_total_articles_before={payload.get('primary_segment_total_articles_before')}",
        f"- primary_segment_total_articles={payload.get('primary_segment_total_articles')}",
        f"- primary_segment_article_days_median_before={payload.get('primary_segment_article_days_median_before')}",
        f"- primary_segment_article_days_median={payload.get('primary_segment_article_days_median')}",
        f"- article_coverage_push_effective={payload.get('article_coverage_push_effective')}",
        f"- decisive_statement={payload.get('decisive_statement')}",
        f"- recommended_next_action={payload.get('recommended_next_action')}",
    ]


def _official_blocking_tickers(payload: Dict[str, object]) -> List[str]:
    rows = [safe_dict(row) for row in list(payload.get("rows") or [])]
    blocking = [
        row for row in rows
        if _safe_bool(row.get("still_blocking"))
    ]
    blocking.sort(
        key=lambda row: (
            _safe_int(row.get("after_article_days")),
            _safe_int(row.get("after_article_count_total")),
            _safe_str(row.get("ticker")),
        )
    )
    return [_safe_str(row.get("ticker")).upper() for row in blocking if _safe_str(row.get("ticker"))]


def _build_drop_reason_rows(fetch_rows: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for row in fetch_rows:
        item = safe_dict(row)
        rows.append(
            {
                "ticker": _safe_str(item.get("ticker")).upper(),
                "provider": _safe_str(item.get("provider")),
                "raw_count": _safe_int(item.get("raw")),
                "saved_count": _safe_int(item.get("saved")),
                "updated_count": _safe_int(item.get("updated")),
                "dropped_relevance": _safe_int(item.get("dropped_relevance")),
                "dropped_quality": _safe_int(item.get("dropped_quality")),
                "dropped_exclusion": _safe_int(item.get("dropped_exclusion")),
                "skipped_dedup": _safe_int(item.get("skipped_dedup")),
                "failed": _safe_int(item.get("failed")),
            }
        )
    return rows


def _build_drop_sample_rows(fetch_rows: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for row in fetch_rows:
        item = safe_dict(row)
        dropped_samples = _normalize_dropped_samples(item.get("dropped_samples"))
        rows.append(
            {
                "ticker": _safe_str(item.get("ticker")).upper(),
                "provider": _safe_str(item.get("provider")),
                "raw_count": _safe_int(item.get("raw")),
                "saved_count": _safe_int(item.get("saved")),
                "updated_count": _safe_int(item.get("updated")),
                "dropped_relevance": _safe_int(item.get("dropped_relevance")),
                "dropped_quality": _safe_int(item.get("dropped_quality")),
                "dropped_exclusion": _safe_int(item.get("dropped_exclusion")),
                "failed": _safe_int(item.get("failed")),
                "relevance_samples": dropped_samples["relevance"],
                "quality_samples": dropped_samples["quality"],
                "exclusion_samples": dropped_samples["exclusion"],
            }
        )
    return rows


def _article_rows_by_date(rows: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    grouped: Dict[str, Dict[str, object]] = {}
    for item in rows:
        row = safe_dict(item)
        published_date = _safe_str(row.get("published_date"), "unknown")
        provider = _safe_str(row.get("source_provider"), "unknown")
        bucket = grouped.setdefault(
            published_date,
            {
                "published_date": published_date,
                "article_count": 0,
                "providers": {},
                "titles": [],
            },
        )
        bucket["article_count"] = _safe_int(bucket.get("article_count")) + 1
        providers = safe_dict(bucket.get("providers"))
        providers[provider] = _safe_int(providers.get(provider)) + 1
        bucket["providers"] = providers
        titles = list(bucket.get("titles") or [])
        title = _safe_str(row.get("title"))
        if title:
            titles.append(title)
        bucket["titles"] = dedupe(titles)[:4]

    return [
        grouped[key]
        for key in sorted(grouped.keys(), reverse=True)
    ]


def _build_bbca_article_day_audit_payload(
    *,
    before_detail: Dict[str, object],
    after_detail: Dict[str, object],
    before_snapshot_row: Dict[str, object],
    after_snapshot_row: Dict[str, object],
    fetch_rows: Sequence[Dict[str, object]],
    drop_sample_rows: Sequence[Dict[str, object]],
    membership_audit_payload: Dict[str, object],
) -> Dict[str, object]:
    ticker = "BBCA"
    before_rows = [safe_dict(row) for row in list(before_detail.get("rows") or [])]
    after_rows = [safe_dict(row) for row in list(after_detail.get("rows") or [])]
    before_keys = {
        (
            _safe_str(row.get("source_url")),
            _safe_str(row.get("title")),
            _safe_str(row.get("published_date")),
        )
        for row in before_rows
    }
    added_rows = [
        row for row in after_rows
        if (
            _safe_str(row.get("source_url")),
            _safe_str(row.get("title")),
            _safe_str(row.get("published_date")),
        ) not in before_keys
    ]

    before_dates = {_safe_str(row.get("published_date")) for row in before_rows if _safe_str(row.get("published_date"))}
    added_dates = {_safe_str(row.get("published_date")) for row in added_rows if _safe_str(row.get("published_date"))}
    new_dates = sorted(date for date in added_dates if date not in before_dates)
    if new_dates:
        clustering_summary = f"new rows introduced new published dates: {', '.join(new_dates)}"
    elif added_rows:
        clustering_summary = "new rows were added, but all landed on published dates that already existed before the push"
    else:
        clustering_summary = "no new BBCA rows were inserted into the DB during this push"

    membership_row = next(
        (
            safe_dict(row)
            for row in list(membership_audit_payload.get("rows") or [])
            if _safe_str(safe_dict(row).get("ticker")).upper() == ticker
        ),
        {},
    )
    drop_row = next(
        (safe_dict(row) for row in drop_sample_rows if _safe_str(safe_dict(row).get("ticker")).upper() == ticker),
        {},
    )

    return {
        "generated_at": _now_iso(),
        "ticker": ticker,
        "official_article_days_before": _safe_int(before_snapshot_row.get("article_days_current")),
        "official_article_days_after": _safe_int(after_snapshot_row.get("article_days_current")),
        "official_article_count_before": _safe_int(before_snapshot_row.get("news_count_total_current")),
        "official_article_count_after": _safe_int(after_snapshot_row.get("news_count_total_current")),
        "included_in_official_primary_segment_after": _safe_bool(membership_row.get("included_in_official_primary_segment")),
        "official_membership_reason_after": _safe_str(membership_row.get("reason")),
        "db_article_days_before": len(before_dates),
        "db_article_days_after": len({_safe_str(row.get("published_date")) for row in after_rows if _safe_str(row.get("published_date"))}),
        "db_article_count_before": len(before_rows),
        "db_article_count_after": len(after_rows),
        "provider_fetch_summary": _build_provider_contribution_summary(fetch_rows, ticker),
        "before_by_date": _article_rows_by_date(before_rows),
        "after_by_date": _article_rows_by_date(after_rows),
        "added_rows_after_push": added_rows,
        "added_row_count": len(added_rows),
        "added_new_dates": new_dates,
        "clustering_summary": clustering_summary,
        "drop_samples": {
            "relevance": list(drop_row.get("relevance_samples") or []),
            "quality": list(drop_row.get("quality_samples") or []),
            "exclusion": list(drop_row.get("exclusion_samples") or []),
        },
    }


def _build_after_push_text(payload: Dict[str, object]) -> List[str]:
    return [
        "Phase B Batch-1 After Article Push",
        f"- batch_1_status={payload.get('batch_1_status')}",
        f"- batch_1_priority_targets_closed={payload.get('batch_1_priority_targets_closed')}",
        f"- batch_1_operationally_complete={payload.get('batch_1_operationally_complete')}",
        f"- ready_for_batch_2={payload.get('ready_for_batch_2')}",
        f"- checkpoint_material_reached={payload.get('checkpoint_material_reached')}",
        f"- recheck_readiness_gate_allowed={payload.get('recheck_readiness_gate_allowed')}",
        f"- primary_segment_total_articles={payload.get('primary_segment_total_articles')}",
        f"- primary_segment_article_days_median={payload.get('primary_segment_article_days_median')}",
        f"- decisive_statement={payload.get('decisive_statement')}",
        f"- recommended_next_action={payload.get('recommended_next_action')}",
        "Remaining blockers:",
        *[f"- {item}" for item in list(payload.get("remaining_blockers") or [])],
    ]


def run_phase_b_primary_article_coverage_push(
    *,
    data_dir: Path,
    output_dir: Path,
    metadata_file: Optional[Path] = None,
    priority_tickers: Optional[Sequence[str]] = None,
    providers: Optional[Sequence[str]] = None,
    command_executor: Optional[CommandExecutor] = None,
    coverage_probe: Optional[CoverageProbe] = None,
    article_detail_probe: Optional[ArticleDetailProbe] = None,
    after_fetch_hook: Optional[AfterFetchHook] = None,
) -> Dict[str, object]:
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    root = Path.cwd()
    resolved_metadata = Path(metadata_file) if metadata_file is not None else data_dir / "ticker_metadata.csv"
    if not data_dir.exists():
        raise PhaseBPrimaryArticleCoveragePushCliError(f"Data directory not found: {data_dir}")
    if not resolved_metadata.exists():
        raise PhaseBPrimaryArticleCoveragePushCliError(f"Metadata file not found: {resolved_metadata}")

    baseline_completion = _load_required_json(output_dir / "phase_b_batch1_completion_decision.json", "phase_b_batch1_completion_decision")
    before_article_status = safe_dict(baseline_completion.get("article_day_status"))
    priority_tickers = list(priority_tickers or DEFAULT_PRIORITY_TICKERS)
    priority_tickers = dedupe([_safe_str(item).upper() for item in priority_tickers if _safe_str(item)])
    providers = list(providers or DEFAULT_PROVIDER_PLAN)
    command_executor = command_executor or _default_command_executor
    coverage_probe = coverage_probe or _default_coverage_probe
    article_detail_probe = article_detail_probe or _default_article_detail_probe

    before_official_rows = _official_primary_metric_rows(
        data_dir=data_dir,
        output_dir=output_dir,
        metadata_file=resolved_metadata,
    )
    coverage_tickers_before = dedupe([*priority_tickers, *list(before_official_rows.keys())])
    db_before = coverage_probe(coverage_tickers_before, root)
    bbca_detail_before = article_detail_probe("BBCA", root) if "BBCA" in priority_tickers else {"ticker": "BBCA", "rows": []}
    fetch_rows = _run_fetch_plan(
        root=root,
        plan=_build_fetch_plan(priority_tickers, providers),
        command_executor=command_executor,
    )

    if after_fetch_hook is not None:
        after_fetch_hook(data_dir, output_dir, resolved_metadata)

    export_command = [
        "php",
        "artisan",
        "phase-a:export-real-data",
        f"--data-dir={data_dir}",
        f"--metadata-file={resolved_metadata}",
        "--include-sentiment-series",
    ]
    export_result = command_executor(export_command, root)

    db_after = coverage_probe(priority_tickers, root)
    completion_result = run_phase_b_batch1_completion_check(
        data_dir=data_dir,
        output_dir=output_dir,
        metadata_file=resolved_metadata,
    )
    after_completion = safe_dict(completion_result.get("phase_b_batch1_completion_decision"))
    after_article_status = safe_dict(after_completion.get("article_day_status"))
    before_snapshot = _before_snapshot_lookup(baseline_completion)
    after_snapshot = _after_snapshot_lookup(after_completion)
    after_official_rows = _official_primary_metric_rows(
        data_dir=data_dir,
        output_dir=output_dir,
        metadata_file=resolved_metadata,
    )
    coverage_tickers_after = dedupe([*priority_tickers, *list(before_official_rows.keys()), *list(after_official_rows.keys())])
    if coverage_tickers_after != coverage_tickers_before:
        db_before = coverage_probe(coverage_tickers_after, root)
    db_after = coverage_probe(coverage_tickers_after, root)
    bbca_detail_after = article_detail_probe("BBCA", root) if "BBCA" in priority_tickers else {"ticker": "BBCA", "rows": []}

    breakdown_rows = _build_breakdown_rows(
        priority_tickers=priority_tickers,
        before_snapshot=before_snapshot,
        db_before=db_before,
        db_after=db_after,
        after_snapshot=after_snapshot,
        fetch_rows=fetch_rows,
    )
    drop_reason_rows = _build_drop_reason_rows(fetch_rows)
    drop_sample_rows = _build_drop_sample_rows(fetch_rows)
    official_delta_payload = _build_official_metric_delta_payload(
        priority_tickers=priority_tickers,
        before_official_rows=before_official_rows,
        after_official_rows=after_official_rows,
        db_before=db_before,
        db_after=db_after,
        fetch_rows=fetch_rows,
    )
    membership_audit_payload = _build_primary_segment_membership_audit_payload(
        data_dir=data_dir,
        output_dir=output_dir,
        metadata_file=resolved_metadata,
        priority_tickers=priority_tickers,
        after_completion=after_completion,
    )
    bbca_article_day_audit_payload = _build_bbca_article_day_audit_payload(
        before_detail=bbca_detail_before,
        after_detail=bbca_detail_after,
        before_snapshot_row=safe_dict(before_snapshot.get("BBCA")),
        after_snapshot_row=safe_dict(after_snapshot.get("BBCA")),
        fetch_rows=fetch_rows,
        drop_sample_rows=drop_sample_rows,
        membership_audit_payload=membership_audit_payload,
    )
    official_blockers = _official_blocking_tickers(official_delta_payload)
    blocker_text = ", ".join(official_blockers[:4]) if official_blockers else "primary segment resmi"

    before_total_articles, before_median_days = _official_primary_metrics(baseline_completion)
    after_total_articles, after_median_days = _official_primary_metrics(after_completion)
    push_effective = (after_total_articles > before_total_articles) or (after_median_days > before_median_days)

    coverage_push_payload = {
        "generated_at": _now_iso(),
        "priority_tickers_checked": priority_tickers,
        "providers_attempted": list(providers),
        "primary_segment_total_articles_before": before_total_articles,
        "primary_segment_total_articles": after_total_articles,
        "primary_segment_article_days_median_before": before_median_days,
        "primary_segment_article_days_median": after_median_days,
        "article_coverage_push_effective": push_effective,
        "fetch_attempts": fetch_rows,
        "drop_reasons_per_provider": drop_reason_rows,
        "dropped_samples_per_provider": drop_sample_rows,
        "export_command_succeeded": _safe_bool(export_result.get("succeeded")),
        "export_command_output": _safe_str(export_result.get("combined_output")),
        "db_before": db_before,
        "db_after": db_after,
        "official_metric_delta_per_ticker": official_delta_payload,
        "source_of_truth_artifact": membership_audit_payload["source_of_truth_artifact"],
        "official_primary_segment_tickers": membership_audit_payload["official_primary_segment_tickers"],
        "official_primary_segment_selection_basis": membership_audit_payload["official_primary_segment_selection_basis"],
        "official_primary_segment_membership_audit": membership_audit_payload,
        "bbca_article_day_audit": bbca_article_day_audit_payload,
        "decisive_statement": (
            "Batch-1 operasional complete setelah progress resmi mengakui target prioritas sudah tertutup."
            if _safe_bool(after_completion.get("batch_1_operationally_complete"))
            else (
                "Target prioritas batch-1 sudah tertutup, tetapi progress artifact resmi belum mengakui batch sebagai complete."
                if _safe_bool(after_completion.get("batch_1_priority_targets_closed"))
                else (
                    "Article coverage primary segment naik, tetapi median article days masih belum cukup untuk menutup batch-1."
                    if push_effective
                    else f"Batch-1 belum complete karena {blocker_text} masih menahan article-day recovery primary segment resmi."
                )
            )
        ),
        "recommended_next_action": _safe_str(after_completion.get("recommended_next_action")),
    }

    after_push_payload = {
        "generated_at": _now_iso(),
        "primary_segment_total_articles": after_total_articles,
        "primary_segment_article_days_median": after_median_days,
        "priority_tickers_checked": priority_tickers,
        "article_coverage_push_effective": push_effective,
        "batch_1_status": _safe_str(after_completion.get("batch_1_status")),
        "batch_1_priority_targets_closed": _safe_bool(after_completion.get("batch_1_priority_targets_closed")),
        "batch_1_operationally_complete": _safe_bool(after_completion.get("batch_1_operationally_complete")),
        "ready_for_batch_2": _safe_bool(after_completion.get("ready_for_batch_2")),
        "batch_1_completed": _safe_bool(after_completion.get("batch_1_operationally_complete")),
        "checkpoint_material_reached": _safe_bool(after_completion.get("checkpoint_material_reached")),
        "recheck_readiness_gate_allowed": _safe_bool(after_completion.get("recheck_readiness_gate_allowed")),
        "remaining_blockers": list(after_completion.get("remaining_blockers") or []),
        "recommended_next_action": _safe_str(after_completion.get("recommended_next_action")),
        "decisive_statement": (
            "Checkpoint material sudah tercapai sehingga readiness gate sekarang boleh dijalankan ulang."
            if _safe_bool(after_completion.get("checkpoint_material_reached"))
            else (
                "Batch-1 operasional complete, tetapi retest tetap belum boleh dibuka sebelum readiness gate resmi di-rerun."
                if _safe_bool(after_completion.get("batch_1_operationally_complete"))
                else (
                    "Target prioritas batch-1 sudah tertutup, tetapi progress artifact resmi belum mengakui batch sebagai complete."
                    if _safe_bool(after_completion.get("batch_1_priority_targets_closed"))
                    else (
                        "Article coverage primary segment naik, tetapi median article days masih belum cukup untuk menutup batch-1."
                        if push_effective
                        else f"Batch-1 belum complete karena {blocker_text} masih menahan article-day recovery primary segment resmi."
                    )
                )
            )
        ),
    }

    _write_json(output_dir / PRIMARY_ARTICLE_PUSH_JSON_OUTPUT, coverage_push_payload)
    _write_text(output_dir / PRIMARY_ARTICLE_PUSH_TEXT_OUTPUT, _build_push_text(coverage_push_payload))
    _write_csv(output_dir / PRIMARY_ARTICLE_BREAKDOWN_CSV_OUTPUT, breakdown_rows, BREAKDOWN_COLUMNS)
    _write_json(
        output_dir / PRIMARY_ARTICLE_DROP_REASONS_JSON_OUTPUT,
        {
            "generated_at": _now_iso(),
            "priority_tickers_checked": priority_tickers,
            "providers_attempted": list(providers),
            "rows": drop_reason_rows,
        },
    )
    _write_json(
        output_dir / PRIMARY_ARTICLE_DROP_SAMPLES_JSON_OUTPUT,
        {
            "generated_at": _now_iso(),
            "priority_tickers_checked": priority_tickers,
            "providers_attempted": list(providers),
            "rows": drop_sample_rows,
        },
    )
    _write_json(output_dir / PRIMARY_ARTICLE_OFFICIAL_DELTA_JSON_OUTPUT, official_delta_payload)
    _write_json(output_dir / PRIMARY_ARTICLE_PRIMARY_MEMBERSHIP_JSON_OUTPUT, membership_audit_payload)
    _write_json(output_dir / BBCA_ARTICLE_DAY_AUDIT_JSON_OUTPUT, bbca_article_day_audit_payload)
    _write_json(output_dir / BATCH1_AFTER_PUSH_JSON_OUTPUT, after_push_payload)
    _write_text(output_dir / BATCH1_AFTER_PUSH_TEXT_OUTPUT, _build_after_push_text(after_push_payload))

    return {
        "phase_b_primary_article_coverage_push": coverage_push_payload,
        "phase_b_primary_article_coverage_ticker_breakdown": breakdown_rows,
        "phase_b_primary_article_drop_reasons_per_provider": drop_reason_rows,
        "phase_b_primary_article_dropped_samples_per_provider": drop_sample_rows,
        "phase_b_primary_article_official_metric_delta_per_ticker": official_delta_payload,
        "phase_b_official_primary_segment_membership_audit": membership_audit_payload,
        "bbca_article_day_audit": bbca_article_day_audit_payload,
        "phase_b_batch1_after_article_push": after_push_payload,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Push primary article coverage for Phase B batch-1 and verify completion.")
    parser.add_argument("--data-dir", default="data", help="Directory containing ticker CSV files.")
    parser.add_argument("--output-dir", default="output", help="Directory containing and receiving artifacts.")
    parser.add_argument("--metadata-file", default="data/ticker_metadata.csv", help="Optional ticker metadata CSV.")
    parser.add_argument(
        "--priority-tickers",
        default="",
        help="Comma-separated ticker list for targeted fetch. Defaults to the built-in priority list when omitted.",
    )
    parser.add_argument(
        "--providers",
        default="",
        help="Comma-separated provider list for targeted fetch. Defaults to the built-in provider plan when omitted.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    priority_tickers = [item.strip().upper() for item in str(args.priority_tickers or "").split(",") if item.strip()]
    providers = [item.strip() for item in str(args.providers or "").split(",") if item.strip()]
    try:
        result = run_phase_b_primary_article_coverage_push(
            data_dir=Path(args.data_dir),
            output_dir=Path(args.output_dir),
            metadata_file=Path(args.metadata_file) if args.metadata_file else None,
            priority_tickers=priority_tickers or None,
            providers=providers or None,
        )
    except PhaseBPrimaryArticleCoveragePushCliError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Unexpected error during primary article coverage push: {exc}", file=sys.stderr)
        return 1

    payload = safe_dict(result.get("phase_b_batch1_after_article_push"))
    print("Phase B primary article coverage push complete.")
    print(f"batch_1_status={payload.get('batch_1_status')}")
    print(f"batch_1_operationally_complete={payload.get('batch_1_operationally_complete')}")
    print(f"recheck_readiness_gate_allowed={payload.get('recheck_readiness_gate_allowed')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
