"""Audit official distribution-gate and OOS-breadth target tickers for Phase B."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.phase_a_transition_utils import dedupe, read_json_object, safe_dict  # noqa: E402


AUDIT_OUTPUT = "phase_b_distribution_and_oos_target_audit.json"


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


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _read_json(path: Path, label: str) -> Dict[str, object]:
    payload, _ = read_json_object(path, label)
    return safe_dict(payload)


def _read_csv_rows(path: Path) -> List[Dict[str, object]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _parse_segment_spec(spec: str) -> Tuple[str, str]:
    token = _safe_str(spec)
    if "=" not in token:
        return "", ""
    field, value = token.split("=", 1)
    return field.strip(), value.strip()


def _provider_summary_from_push(push_payload: Dict[str, object]) -> Dict[str, List[Dict[str, object]]]:
    summary: Dict[str, List[Dict[str, object]]] = {}
    for row in list(push_payload.get("fetch_attempts") or []):
        item = safe_dict(row)
        ticker = _safe_str(item.get("ticker")).upper()
        if not ticker:
            continue
        summary.setdefault(ticker, []).append(
            {
                "provider": _safe_str(item.get("provider")),
                "raw_count": _safe_int(item.get("raw")),
                "saved_count": _safe_int(item.get("saved")),
                "updated_count": _safe_int(item.get("updated")),
                "failed": _safe_int(item.get("failed")),
            }
        )
    return summary


def _previous_summary(previous_payload: Dict[str, object]) -> Dict[str, object]:
    return safe_dict(previous_payload.get("summary"))


def _parse_blocking_thresholds_snapshot(rows: object) -> Dict[str, float]:
    parsed: Dict[str, float] = {}
    for raw in list(rows or []):
        text = _safe_str(raw)
        if " actual=" not in text:
            continue
        blocker_name, _, remainder = text.partition(" actual=")
        actual_value_text, _, _ = remainder.partition(" target")
        if blocker_name:
            parsed[blocker_name.strip()] = _safe_float(actual_value_text)
    return parsed


def run_phase_b_distribution_and_oos_target_audit(
    *,
    output_dir: Path,
    metadata_file: Path,
) -> Dict[str, object]:
    output_dir = Path(output_dir)
    metadata_file = Path(metadata_file)

    readiness = _read_json(output_dir / "phase_b_retest_readiness_gate.json", "phase_b_retest_readiness_gate")
    blocker_audit = _read_json(output_dir / "phase_b_readiness_blocker_audit.json", "phase_b_readiness_blocker_audit")
    v9_summary = _read_json(output_dir / "baseline_v9_segment_oos_summary.json", "baseline_v9_segment_oos_summary")
    v9_results = _read_csv_rows(output_dir / "baseline_v9_segment_oos_results.csv")
    segmentation_rows = _read_csv_rows(output_dir / "baseline_v6_universe_segmentation.csv")
    metadata_rows = _read_csv_rows(metadata_file)
    push_payload = _read_json(output_dir / "phase_b_primary_article_coverage_push.json", "phase_b_primary_article_coverage_push")
    previous_payload = _read_json(output_dir / AUDIT_OUTPUT, AUDIT_OUTPUT)
    previous_readiness_snapshot = safe_dict(blocker_audit.get("previous_readiness_snapshot"))
    previous_threshold_snapshot = _parse_blocking_thresholds_snapshot(previous_readiness_snapshot.get("blocking_thresholds"))

    primary_segment = _safe_str(readiness.get("primary_segment"))
    primary_field, primary_value = _parse_segment_spec(primary_segment)
    active_blockers = {
        _safe_str(item.get("blocker_name"))
        for item in list(blocker_audit.get("active_blockers") or [])
        if _safe_str(safe_dict(item).get("blocker_name"))
    }

    metadata_lookup = {_safe_str(row.get("ticker")).upper(): row for row in metadata_rows if _safe_str(row.get("ticker"))}
    segmentation_lookup = {_safe_str(row.get("ticker")).upper(): row for row in segmentation_rows if _safe_str(row.get("ticker"))}
    provider_summary = _provider_summary_from_push(push_payload)

    primary_oos_trade_lookup: Dict[str, int] = {}
    all_oos_trade_lookup: Dict[str, int] = {}
    for row in v9_results:
        if _safe_str(row.get("row_type")) != "ticker_oos_summary":
            continue
        ticker = _safe_str(row.get("ticker")).upper()
        trades = _safe_int(row.get("candidate_total_trades"))
        all_oos_trade_lookup[ticker] = max(trades, all_oos_trade_lookup.get(ticker, 0))
        if _safe_str(row.get("tested_segment")) == primary_segment:
            primary_oos_trade_lookup[ticker] = trades

    current_days_values = [_safe_int(row.get("sentiment_days_with_articles")) for row in metadata_rows]
    median_article_days_threshold = float(statistics.median(current_days_values)) if current_days_values else 0.0

    distribution_tickers: List[str] = []
    rows: List[Dict[str, object]] = []
    for ticker in sorted(set(list(metadata_lookup.keys()) + list(segmentation_lookup.keys()) + list(all_oos_trade_lookup.keys()))):
        metadata_row = safe_dict(metadata_lookup.get(ticker))
        segmentation_row = safe_dict(segmentation_lookup.get(ticker))
        segment_value_actual = _safe_str(segmentation_row.get(primary_field))
        included_primary = bool(primary_field and segment_value_actual == primary_value)
        included_distribution = included_primary
        included_active_oos = _safe_int(primary_oos_trade_lookup.get(ticker)) > 0
        article_count_total = _safe_int(
            segmentation_row.get("article_count_total", segmentation_row.get("news_count_total")),
            _safe_int(metadata_row.get("sentiment_article_count_total")),
        )
        article_days = _safe_int(
            segmentation_row.get("article_days"),
            _safe_int(metadata_row.get("sentiment_days_with_articles")),
        )
        history_rows = _safe_int(
            segmentation_row.get("history_rows", segmentation_row.get("rows")),
            _safe_int(metadata_row.get("rows_1d")),
        )
        news_density_pct = _safe_float(
            segmentation_row.get("news_density_pct"),
            round((100.0 * article_days / history_rows), 5) if history_rows > 0 else 0.0,
        )
        active_oos_trade_count = _safe_int(primary_oos_trade_lookup.get(ticker))
        if included_distribution:
            distribution_tickers.append(ticker)
        rows.append(
            {
                "ticker": ticker,
                "included_in_primary_segment": included_primary,
                "included_in_distribution_gate": included_distribution,
                "included_in_active_oos": included_active_oos,
                "article_count_total_current": article_count_total,
                "article_days_current": article_days,
                "news_density_pct_current": round(news_density_pct, 5),
                "article_share_current": 0.0,
                "active_oos_trade_count": active_oos_trade_count,
                "best_any_oos_trade_count": _safe_int(all_oos_trade_lookup.get(ticker)),
                "current_sentiment_segment": _safe_str(segmentation_row.get("sentiment_segment")),
                "current_news_segment": _safe_str(segmentation_row.get("news_segment")),
                "current_history_rows": history_rows,
                "current_metadata_article_days": _safe_int(metadata_row.get("sentiment_days_with_articles")),
                "boundary_candidate_for_primary_if_median_rises": (
                    (not included_primary)
                    and _safe_int(metadata_row.get("sentiment_days_with_articles")) == int(median_article_days_threshold)
                    and _safe_int(all_oos_trade_lookup.get(ticker)) > 0
                ),
                "provider_contribution_summary": provider_summary.get(ticker, []),
            }
        )

    distribution_total_articles = sum(
        _safe_int(row.get("article_count_total_current"))
        for row in rows
        if bool(row.get("included_in_distribution_gate"))
    )
    for row in rows:
        if bool(row.get("included_in_distribution_gate")) and distribution_total_articles > 0:
            row["article_share_current"] = round(
                _safe_int(row.get("article_count_total_current")) / float(distribution_total_articles), 4
            )
        else:
            row["article_share_current"] = 0.0

    distribution_rows = [row for row in rows if bool(row.get("included_in_distribution_gate"))]
    dominant_after = (
        max(distribution_rows, key=lambda item: (_safe_float(item.get("article_share_current")), item.get("ticker"))).get("ticker")
        if distribution_rows
        else None
    )
    share_after = max((_safe_float(row.get("article_share_current")) for row in distribution_rows), default=0.0)
    median_news_density_after = _safe_float(
        next(
            (
                safe_dict(item).get("actual_value")
                for item in list(blocker_audit.get("all_threshold_checks") or [])
                if _safe_str(safe_dict(item).get("blocker_name")) == "news_distribution_gate::median_news_density_pct"
            ),
            0.0,
        )
    )
    active_oos_after = _safe_int(
        next(
            (
                safe_dict(item).get("actual_value")
                for item in list(blocker_audit.get("all_threshold_checks") or [])
                if _safe_str(safe_dict(item).get("blocker_name")) == "oos_fairness_gate::active_ticker_count_in_oos"
            ),
            0,
        )
    )

    boundary_candidates = [
        row for row in rows
        if bool(row.get("boundary_candidate_for_primary_if_median_rises"))
    ]
    boundary_candidates.sort(key=lambda item: (-_safe_int(item.get("best_any_oos_trade_count")), item.get("ticker")))
    targeted_tickers = dedupe(
        [
            *[row["ticker"] for row in distribution_rows],
            *[row["ticker"] for row in boundary_candidates[:6]],
        ]
    )

    previous_summary = _previous_summary(previous_payload)
    summary = {
        "primary_segment": primary_segment,
        "official_target_tickers": sorted(distribution_tickers),
        "official_distribution_gate_tickers": sorted(distribution_tickers),
        "official_active_oos_tickers": sorted([ticker for ticker, trades in primary_oos_trade_lookup.items() if trades > 0]),
        "dominant_ticker": dominant_after,
        "single_ticker_article_share": round(share_after, 4),
        "median_news_density_pct": round(median_news_density_after, 4),
        "active_ticker_count_in_oos": active_oos_after,
        "median_article_days_threshold_for_sentiment_split": median_article_days_threshold,
        "boundary_candidates_for_primary_expansion": [row["ticker"] for row in boundary_candidates],
        "targeted_tickers": targeted_tickers,
    }

    payload = {
        "generated_at": _now_iso(),
        "source_of_truth_artifacts": {
            "readiness_gate": "output/phase_b_retest_readiness_gate.json",
            "blocker_audit": "output/phase_b_readiness_blocker_audit.json",
            "oos_summary": "output/baseline_v9_segment_oos_summary.json",
            "oos_results": "output/baseline_v9_segment_oos_results.csv",
            "segmentation": "output/baseline_v6_universe_segmentation.csv",
            "metadata": str(metadata_file),
        },
        "summary": summary,
        "before_after": {
            "dominant_ticker_before": previous_summary.get("dominant_ticker"),
            "dominant_ticker_after": summary.get("dominant_ticker"),
            "single_ticker_article_share_before": previous_threshold_snapshot.get(
                "news_distribution_gate::no_single_ticker_article_share",
                previous_summary.get("single_ticker_article_share"),
            ),
            "single_ticker_article_share_after": summary.get("single_ticker_article_share"),
            "median_news_density_pct_before": previous_threshold_snapshot.get(
                "news_distribution_gate::median_news_density_pct",
                previous_summary.get("median_news_density_pct"),
            ),
            "median_news_density_pct_after": summary.get("median_news_density_pct"),
            "active_ticker_count_in_oos_before": previous_threshold_snapshot.get(
                "oos_fairness_gate::active_ticker_count_in_oos",
                previous_summary.get("active_ticker_count_in_oos"),
            ),
            "active_ticker_count_in_oos_after": summary.get("active_ticker_count_in_oos"),
        },
        "targeted_tickers": targeted_tickers,
        "provider_contribution_summary": {
            ticker: provider_summary.get(ticker, [])
            for ticker in targeted_tickers
        },
        "rows": rows,
        "active_gate_blockers": sorted(active_blockers),
        "recommended_next_move": (
            "Naikkan article-day pada boundary tickers ber-trade tinggi agar median sentiment split bisa naik ke 8 sambil menambah coverage pada under-covered primary tickers; "
            "namun median_news_density_pct gate tetap jauh di bawah target 5.0 sehingga readiness kemungkinan besar masih gagal tanpa ekspansi article-day jauh lebih besar."
        ),
    }
    _write_json(output_dir / AUDIT_OUTPUT, payload)
    return payload


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit official distribution-gate and OOS target tickers for Phase B.")
    parser.add_argument("--output-dir", default="output", help="Directory containing readiness and OOS artifacts.")
    parser.add_argument("--metadata-file", default="data/ticker_metadata.csv", help="Ticker metadata CSV.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    payload = run_phase_b_distribution_and_oos_target_audit(
        output_dir=Path(args.output_dir),
        metadata_file=Path(args.metadata_file),
    )
    summary = safe_dict(payload.get("summary"))
    print("Phase B distribution and OOS target audit complete.")
    print(f"primary_segment={summary.get('primary_segment')}")
    print(f"official_target_tickers={','.join(list(summary.get('official_target_tickers') or []))}")
    print(f"active_oos_tickers={','.join(list(summary.get('official_active_oos_tickers') or []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
