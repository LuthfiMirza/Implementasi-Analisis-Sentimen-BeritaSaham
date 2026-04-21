"""Audit realism of the Phase B news distribution density threshold."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.phase_a_transition_utils import read_json_object, safe_dict  # noqa: E402


AUDIT_OUTPUT = "phase_b_news_distribution_threshold_audit.json"


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


def _read_json(path: Path, label: str) -> Dict[str, object]:
    payload, _ = read_json_object(path, label)
    return safe_dict(payload)


def _read_csv_rows(path: Path) -> List[Dict[str, object]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _primary_pool_lookup(rows: Sequence[Dict[str, object]]) -> Dict[str, Dict[str, object]]:
    return {
        _safe_str(row.get("ticker")).upper(): safe_dict(row)
        for row in rows
        if _safe_str(row.get("ticker"))
    }


def _status_label(*, ticker: str, dominant_ticker: str, density_pct: float, median_density: float) -> str:
    if ticker == dominant_ticker:
        return "dominant"
    if density_pct < median_density:
        return "under_covered"
    return "balanced"


def run_phase_b_news_distribution_threshold_audit(
    *,
    output_dir: Path,
    metadata_file: Path,
) -> Dict[str, object]:
    output_dir = Path(output_dir)
    metadata_file = Path(metadata_file)

    readiness = _read_json(output_dir / "phase_b_retest_readiness_gate.json", "phase_b_retest_readiness_gate")
    blocker_audit = _read_json(output_dir / "phase_b_readiness_blocker_audit.json", "phase_b_readiness_blocker_audit")
    distribution_audit = _read_json(
        output_dir / "phase_b_distribution_and_oos_target_audit.json",
        "phase_b_distribution_and_oos_target_audit",
    )
    metadata_rows = _read_csv_rows(metadata_file)

    summary = safe_dict(distribution_audit.get("summary"))
    primary_rows = [safe_dict(row) for row in list(distribution_audit.get("rows") or []) if safe_dict(row)]
    primary_lookup = _primary_pool_lookup(primary_rows)
    primary_tickers = list(summary.get("official_distribution_gate_tickers") or [])
    primary_total_articles = sum(
        _safe_int(safe_dict(primary_lookup.get(ticker)).get("article_count_total_current"))
        for ticker in primary_tickers
    )
    total_universe_articles = sum(_safe_int(row.get("sentiment_article_count_total")) for row in metadata_rows)

    density_rows: List[Dict[str, object]] = []
    for row in metadata_rows:
        ticker = _safe_str(row.get("ticker")).upper()
        history_rows = _safe_int(row.get("rows_1d"))
        article_days = _safe_int(row.get("sentiment_days_with_articles"))
        article_count_total = _safe_int(row.get("sentiment_article_count_total"))
        density_pct = round((100.0 * article_days / history_rows), 4) if history_rows > 0 else 0.0
        threshold_article_days_required = int(math.ceil(0.05 * history_rows)) if history_rows > 0 else 0
        additional_article_days_needed = max(0, threshold_article_days_required - article_days)
        primary_row = safe_dict(primary_lookup.get(ticker))
        primary_pool_share = 0.0
        if ticker in primary_tickers and primary_total_articles > 0:
            primary_pool_share = round(article_count_total / float(primary_total_articles), 4)
        density_rows.append(
            {
                "ticker": ticker,
                "included_in_density_gate_universe": True,
                "included_in_primary_distribution_pool": ticker in primary_tickers,
                "article_count_total_current": article_count_total,
                "article_days_current": article_days,
                "news_density_pct_current": density_pct,
                "share_of_total_official_article_pool": round(
                    article_count_total / float(total_universe_articles), 4
                ) if total_universe_articles > 0 else 0.0,
                "share_of_primary_distribution_pool": primary_pool_share,
                "primary_article_share_current": _safe_float(primary_row.get("article_share_current")),
                "current_history_rows": history_rows,
                "threshold_article_days_required_for_5pct": threshold_article_days_required,
                "additional_article_days_needed_to_hit_5pct": additional_article_days_needed,
            }
        )

    density_values = [_safe_float(row.get("news_density_pct_current")) for row in density_rows]
    actual_median_density = round(float(statistics.median(density_values)), 4) if density_values else 0.0
    actual_mean_density = round(float(statistics.mean(density_values)), 4) if density_values else 0.0
    min_density = round(min(density_values), 4) if density_values else 0.0
    max_density = round(max(density_values), 4) if density_values else 0.0
    density_range = round(max_density - min_density, 4) if density_values else 0.0
    dominant_ticker = _safe_str(summary.get("dominant_ticker"))

    for row in density_rows:
        row["status"] = _status_label(
            ticker=_safe_str(row.get("ticker")),
            dominant_ticker=dominant_ticker,
            density_pct=_safe_float(row.get("news_density_pct_current")),
            median_density=actual_median_density,
        )

    threshold_density = 5.0
    threshold_gap = round(threshold_density - actual_median_density, 4)
    sorted_by_lift = sorted(
        density_rows,
        key=lambda item: (
            _safe_int(item.get("additional_article_days_needed_to_hit_5pct")),
            _safe_str(item.get("ticker")),
        ),
    )
    minimum_tickers_needed = (len(density_rows) // 2) + 1 if density_rows else 0
    cheapest_path = sorted_by_lift[:minimum_tickers_needed]
    minimum_additional_article_days_total = sum(
        _safe_int(item.get("additional_article_days_needed_to_hit_5pct"))
        for item in cheapest_path
    )
    current_tickers_at_or_above_threshold = [
        _safe_str(item.get("ticker"))
        for item in density_rows
        if _safe_float(item.get("news_density_pct_current")) >= threshold_density
    ]
    median_article_days_current = round(
        float(statistics.median([_safe_int(item.get("article_days_current")) for item in density_rows])),
        4,
    ) if density_rows else 0.0
    typical_history_rows = round(
        float(statistics.median([_safe_int(item.get("current_history_rows")) for item in density_rows])),
        4,
    ) if density_rows else 0.0
    threshold_article_days_typical = int(math.ceil(0.05 * typical_history_rows)) if typical_history_rows > 0 else 0
    multiple_vs_actual = round((threshold_density / actual_median_density), 2) if actual_median_density > 0 else None

    if not density_rows:
        realism_status = "insufficient_data"
        realism_reason = "Universe density rows tidak tersedia."
        operational_status = "cannot_assess"
        recommended_next_move = "refresh_artifacts_before_assessment"
    elif current_tickers_at_or_above_threshold:
        realism_status = "potentially_operational"
        realism_reason = "Sebagian ticker sudah berada di atas threshold 5.0 sehingga median bisa digeser dengan intervensi coverage tambahan."
        operational_status = "material_but_not_impossible"
        recommended_next_move = "continue_operational_distribution_rebalance"
    else:
        realism_status = "structurally_misaligned"
        realism_reason = (
            f"Tidak ada ticker di universe resmi yang mencapai density 5.0; median aktual {actual_median_density} "
            f"masih {multiple_vs_actual}x di bawah threshold dan butuh sedikitnya {minimum_tickers_needed} ticker "
            f"naik ke >=5.0."
        )
        operational_status = "not_reasonable_via_normal_operational_push"
        recommended_next_move = "escalate_policy_discussion_before_further_distribution_push"

    payload = {
        "generated_at": _now_iso(),
        "source_of_truth_artifacts": {
            "readiness_gate": "output/phase_b_retest_readiness_gate.json",
            "readiness_blocker_audit": "output/phase_b_readiness_blocker_audit.json",
            "distribution_and_oos_target_audit": "output/phase_b_distribution_and_oos_target_audit.json",
            "metadata": str(metadata_file),
        },
        "official_distribution_universe": {
            "density_gate_scope": "current ticker universe from data/ticker_metadata.csv used by news_distribution_gate::median_news_density_pct",
            "density_gate_tickers": [_safe_str(row.get("ticker")) for row in metadata_rows],
            "density_gate_ticker_count": len(metadata_rows),
            "primary_distribution_pool_scope": _safe_str(readiness.get("primary_segment")),
            "primary_distribution_pool_tickers": primary_tickers,
            "primary_distribution_pool_ticker_count": len(primary_tickers),
        },
        "per_ticker_density_breakdown": density_rows,
        "distribution_statistics": {
            "actual_median_density": actual_median_density,
            "actual_mean_density": actual_mean_density,
            "actual_min_density": min_density,
            "actual_max_density": max_density,
            "actual_density_range": density_range,
            "actual_median_article_days": median_article_days_current,
            "total_official_article_pool": total_universe_articles,
            "primary_distribution_pool_total_articles": primary_total_articles,
        },
        "actual_median_density": actual_median_density,
        "threshold_density": threshold_density,
        "gap_to_threshold": threshold_gap,
        "dominant_ticker": dominant_ticker,
        "threshold_realism_assessment": {
            "status": realism_status,
            "reason": realism_reason,
            "actual_vs_threshold_multiple": multiple_vs_actual,
        },
        "operational_feasibility_assessment": {
            "status": operational_status,
            "current_tickers_at_or_above_threshold": current_tickers_at_or_above_threshold,
            "current_ticker_count_at_or_above_threshold": len(current_tickers_at_or_above_threshold),
            "minimum_tickers_needed_at_or_above_threshold_for_median_pass": minimum_tickers_needed,
            "minimum_additional_article_days_total_for_cheapest_path": minimum_additional_article_days_total,
            "cheapest_path_to_threshold": [
                {
                    "ticker": _safe_str(item.get("ticker")),
                    "current_density": _safe_float(item.get("news_density_pct_current")),
                    "current_article_days": _safe_int(item.get("article_days_current")),
                    "required_article_days_for_5pct": _safe_int(item.get("threshold_article_days_required_for_5pct")),
                    "additional_article_days_needed": _safe_int(item.get("additional_article_days_needed_to_hit_5pct")),
                }
                for item in cheapest_path
            ],
            "typical_history_rows": typical_history_rows,
            "threshold_article_days_required_for_typical_ticker": threshold_article_days_typical,
        },
        "still_active_other_blockers": [
            "universe_coverage_gate::primary_segment_ticker_count",
            "news_distribution_gate::no_single_ticker_article_share",
        ],
        "recommended_next_move": recommended_next_move,
    }
    _write_json(output_dir / AUDIT_OUTPUT, payload)
    return payload


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit realism of the Phase B news distribution density threshold.")
    parser.add_argument("--output-dir", default="output", help="Directory containing readiness artifacts.")
    parser.add_argument("--metadata-file", default="data/ticker_metadata.csv", help="Ticker metadata CSV.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    payload = run_phase_b_news_distribution_threshold_audit(
        output_dir=Path(args.output_dir),
        metadata_file=Path(args.metadata_file),
    )
    print("Phase B news distribution threshold audit complete.")
    print(f"actual_median_density={payload.get('actual_median_density')}")
    print(f"threshold_density={payload.get('threshold_density')}")
    print(
        "official_distribution_universe="
        + ",".join(list(safe_dict(payload.get("official_distribution_universe")).get("density_gate_tickers") or []))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
