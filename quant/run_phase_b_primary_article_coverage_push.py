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
from quant.run_phase_b_batch1_completion_check import run_phase_b_batch1_completion_check


PRIMARY_ARTICLE_PUSH_JSON_OUTPUT = "phase_b_primary_article_coverage_push.json"
PRIMARY_ARTICLE_PUSH_TEXT_OUTPUT = "phase_b_primary_article_coverage_push.txt"
PRIMARY_ARTICLE_BREAKDOWN_CSV_OUTPUT = "phase_b_primary_article_coverage_ticker_breakdown.csv"
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

DEFAULT_PRIORITY_TICKERS = ["UNVR", "ICBP", "BUMI"]
DEFAULT_PROVIDER_PLAN = ["gnews", "rss_local", "newsapi", "gdelt"]

FETCH_RESULT_PATTERN = re.compile(
    r"(?P<ticker>[A-Z0-9]+): raw (?P<raw>\d+), saved (?P<saved>\d+), updated (?P<updated>\d+)",
    re.IGNORECASE,
)


class PhaseBPrimaryArticleCoveragePushCliError(ValueError):
    """Friendly CLI error for Phase B primary article coverage push."""


CommandExecutor = Callable[[Sequence[str], Path], Dict[str, object]]
CoverageProbe = Callable[[Sequence[str], Path], Dict[str, Dict[str, object]]]
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


def _parse_fetch_metrics(result: Dict[str, object]) -> Dict[str, int]:
    match = FETCH_RESULT_PATTERN.search(_safe_str(result.get("combined_output")))
    if not match:
        return {"raw": 0, "saved": 0, "updated": 0}
    return {
        "raw": _safe_int(match.group("raw")),
        "saved": _safe_int(match.group("saved")),
        "updated": _safe_int(match.group("updated")),
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


def _build_after_push_text(payload: Dict[str, object]) -> List[str]:
    return [
        "Phase B Batch-1 After Article Push",
        f"- batch_1_status={payload.get('batch_1_status')}",
        f"- batch_1_completed={payload.get('batch_1_completed')}",
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

    db_before = coverage_probe(priority_tickers, root)
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

    breakdown_rows = _build_breakdown_rows(
        priority_tickers=priority_tickers,
        before_snapshot=before_snapshot,
        db_before=db_before,
        db_after=db_after,
        after_snapshot=after_snapshot,
        fetch_rows=fetch_rows,
    )

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
        "export_command_succeeded": _safe_bool(export_result.get("succeeded")),
        "export_command_output": _safe_str(export_result.get("combined_output")),
        "db_before": db_before,
        "db_after": db_after,
        "decisive_statement": (
            "Batch-1 resmi complete setelah total article primary mencapai >=14 dan median article days mencapai >=3."
            if _safe_bool(after_completion.get("batch_1_completed"))
            else (
                "Article coverage primary segment naik, tetapi median article days masih belum cukup untuk menutup batch-1."
                if push_effective
                else "Batch-1 belum complete karena UNVR, ICBP, dan BUMI masih menahan article-day recovery primary segment."
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
        "batch_1_completed": _safe_bool(after_completion.get("batch_1_completed")),
        "checkpoint_material_reached": _safe_bool(after_completion.get("checkpoint_material_reached")),
        "recheck_readiness_gate_allowed": _safe_bool(after_completion.get("recheck_readiness_gate_allowed")),
        "remaining_blockers": list(after_completion.get("remaining_blockers") or []),
        "recommended_next_action": _safe_str(after_completion.get("recommended_next_action")),
        "decisive_statement": (
            "Checkpoint material sudah tercapai sehingga readiness gate sekarang boleh dijalankan ulang."
            if _safe_bool(after_completion.get("checkpoint_material_reached"))
            else (
                "Walaupun batch-1 complete, retest tetap belum boleh dibuka sebelum readiness gate resmi di-rerun."
                if _safe_bool(after_completion.get("batch_1_completed"))
                else (
                    "Article coverage primary segment naik, tetapi median article days masih belum cukup untuk menutup batch-1."
                    if push_effective
                    else "Batch-1 belum complete karena UNVR, ICBP, dan BUMI masih menahan article-day recovery primary segment."
                )
            )
        ),
    }

    _write_json(output_dir / PRIMARY_ARTICLE_PUSH_JSON_OUTPUT, coverage_push_payload)
    _write_text(output_dir / PRIMARY_ARTICLE_PUSH_TEXT_OUTPUT, _build_push_text(coverage_push_payload))
    _write_csv(output_dir / PRIMARY_ARTICLE_BREAKDOWN_CSV_OUTPUT, breakdown_rows, BREAKDOWN_COLUMNS)
    _write_json(output_dir / BATCH1_AFTER_PUSH_JSON_OUTPUT, after_push_payload)
    _write_text(output_dir / BATCH1_AFTER_PUSH_TEXT_OUTPUT, _build_after_push_text(after_push_payload))

    return {
        "phase_b_primary_article_coverage_push": coverage_push_payload,
        "phase_b_primary_article_coverage_ticker_breakdown": breakdown_rows,
        "phase_b_batch1_after_article_push": after_push_payload,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Push primary article coverage for Phase B batch-1 and verify completion.")
    parser.add_argument("--data-dir", default="data", help="Directory containing ticker CSV files.")
    parser.add_argument("--output-dir", default="output", help="Directory containing and receiving artifacts.")
    parser.add_argument("--metadata-file", default="data/ticker_metadata.csv", help="Optional ticker metadata CSV.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        result = run_phase_b_primary_article_coverage_push(
            data_dir=Path(args.data_dir),
            output_dir=Path(args.output_dir),
            metadata_file=Path(args.metadata_file) if args.metadata_file else None,
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
    print(f"batch_1_completed={payload.get('batch_1_completed')}")
    print(f"recheck_readiness_gate_allowed={payload.get('recheck_readiness_gate_allowed')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
