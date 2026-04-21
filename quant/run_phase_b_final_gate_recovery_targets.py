"""Audit operational recovery targets for the final two Phase B readiness blockers."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.phase_a_transition_utils import dedupe, read_json_object, safe_dict  # noqa: E402


AUDIT_OUTPUT = "phase_b_final_gate_recovery_targets.json"


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


def _parse_segment_spec(spec: str) -> Tuple[str, str]:
    token = _safe_str(spec)
    if "=" not in token:
        return "", ""
    field, value = token.split("=", 1)
    return field.strip(), value.strip()


def run_phase_b_final_gate_recovery_targets(
    *,
    output_dir: Path,
    metadata_file: Path,
) -> Dict[str, object]:
    output_dir = Path(output_dir)
    metadata_file = Path(metadata_file)

    readiness = _read_json(output_dir / "phase_b_retest_readiness_gate.json", "phase_b_retest_readiness_gate")
    distribution_audit = _read_json(
        output_dir / "phase_b_distribution_and_oos_target_audit.json",
        "phase_b_distribution_and_oos_target_audit",
    )
    threshold_audit = _read_json(
        output_dir / "phase_b_news_distribution_threshold_audit.json",
        "phase_b_news_distribution_threshold_audit",
    )
    push_payload = _read_json(output_dir / "phase_b_primary_article_coverage_push.json", "phase_b_primary_article_coverage_push")
    previous_payload = _read_json(output_dir / AUDIT_OUTPUT, AUDIT_OUTPUT)
    segmentation_rows = _read_csv_rows(output_dir / "baseline_v6_universe_segmentation.csv")
    metadata_rows = _read_csv_rows(metadata_file)

    summary = safe_dict(distribution_audit.get("summary"))
    primary_segment = _safe_str(readiness.get("primary_segment"))
    primary_field, primary_value = _parse_segment_spec(primary_segment)
    median_threshold = _safe_float(summary.get("median_article_days_threshold_for_sentiment_split"))
    dominant_ticker = _safe_str(summary.get("dominant_ticker"))
    current_primary_tickers = list(summary.get("official_distribution_gate_tickers") or [])
    primary_count = len(current_primary_tickers)
    single_ticker_share = _safe_float(summary.get("single_ticker_article_share"))
    provider_summary = _provider_summary_from_push(push_payload)

    segmentation_lookup = {
        _safe_str(row.get("ticker")).upper(): row
        for row in segmentation_rows
        if _safe_str(row.get("ticker"))
    }
    distribution_rows = {
        _safe_str(safe_dict(row).get("ticker")).upper(): safe_dict(row)
        for row in list(distribution_audit.get("rows") or [])
        if _safe_str(safe_dict(row).get("ticker"))
    }
    metadata_lookup = {
        _safe_str(row.get("ticker")).upper(): row
        for row in metadata_rows
        if _safe_str(row.get("ticker"))
    }

    candidate_rows: List[Dict[str, object]] = []
    non_primary_candidates: List[Dict[str, object]] = []
    for ticker in sorted(set(list(segmentation_lookup.keys()) + list(distribution_rows.keys()) + list(metadata_lookup.keys()))):
        segmentation_row = safe_dict(segmentation_lookup.get(ticker))
        distribution_row = safe_dict(distribution_rows.get(ticker))
        metadata_row = safe_dict(metadata_lookup.get(ticker))
        article_days = _safe_int(
            distribution_row.get("article_days_current"),
            _safe_int(segmentation_row.get("article_days"), _safe_int(metadata_row.get("sentiment_days_with_articles"))),
        )
        article_count_total = _safe_int(
            distribution_row.get("article_count_total_current"),
            _safe_int(segmentation_row.get("article_count_total"), _safe_int(metadata_row.get("sentiment_article_count_total"))),
        )
        currently_in_primary = _safe_str(segmentation_row.get(primary_field)) == primary_value if primary_field else False
        article_share_current = _safe_float(distribution_row.get("article_share_current"))
        best_any_oos_trade_count = _safe_int(distribution_row.get("best_any_oos_trade_count"))
        distance_to_primary = 0 if currently_in_primary else max(1, int(article_days - median_threshold + 1))

        row = {
            "ticker": ticker,
            "currently_in_primary_segment": currently_in_primary,
            "distance_to_primary_segment_eligibility": distance_to_primary,
            "article_count_total_current": article_count_total,
            "article_days_current": article_days,
            "article_share_current": article_share_current,
            "best_any_oos_trade_count": best_any_oos_trade_count,
            "current_sentiment_segment": _safe_str(segmentation_row.get("sentiment_segment")),
            "candidate_priority_rank": None,
        }
        candidate_rows.append(row)
        if not currently_in_primary:
            non_primary_candidates.append(row)

    non_primary_candidates.sort(
        key=lambda item: (
            _safe_int(item.get("distance_to_primary_segment_eligibility")),
            -_safe_int(item.get("article_count_total_current")),
            -_safe_int(item.get("best_any_oos_trade_count")),
            _safe_str(item.get("ticker")),
        )
    )
    for idx, row in enumerate(non_primary_candidates, start=1):
        row["candidate_priority_rank"] = idx

    recommended_candidate = safe_dict(non_primary_candidates[0]) if non_primary_candidates else {}
    boundary_candidates = [
        row for row in non_primary_candidates
        if _safe_int(row.get("distance_to_primary_segment_eligibility")) == 1
    ]
    targeted_push_tickers = [
        _safe_str(row.get("ticker"))
        for row in boundary_candidates
        if _safe_str(row.get("ticker")) != _safe_str(recommended_candidate.get("ticker"))
    ]

    previous_summary = _previous_summary(previous_payload)
    candidate_entered_primary = (
        bool(recommended_candidate)
        and _safe_str(recommended_candidate.get("ticker")) in current_primary_tickers
    )
    payload = {
        "generated_at": _now_iso(),
        "source_of_truth_artifacts": {
            "readiness_gate": "output/phase_b_retest_readiness_gate.json",
            "distribution_and_oos_target_audit": "output/phase_b_distribution_and_oos_target_audit.json",
            "news_distribution_threshold_audit": "output/phase_b_news_distribution_threshold_audit.json",
            "segmentation": "output/baseline_v6_universe_segmentation.csv",
            "metadata": str(metadata_file),
            "primary_article_push": "output/phase_b_primary_article_coverage_push.json",
        },
        "summary": {
            "primary_segment_scope": primary_segment,
            "primary_segment_official_tickers": current_primary_tickers,
            "primary_segment_ticker_count": primary_count,
            "single_ticker_article_share": single_ticker_share,
            "dominant_ticker": dominant_ticker,
            "median_article_days_threshold_for_sentiment_split": median_threshold,
            "recommended_candidate_to_become_fifth_primary_ticker": _safe_str(recommended_candidate.get("ticker")),
            "targeted_push_tickers": targeted_push_tickers,
        },
        "rows": candidate_rows,
        "provider_contribution_summary": {
            ticker: provider_summary.get(ticker, [])
            for ticker in dedupe([*targeted_push_tickers, _safe_str(recommended_candidate.get("ticker"))])
            if ticker
        },
        "before_after": {
            "primary_segment_ticker_count_before": previous_summary.get("primary_segment_ticker_count"),
            "primary_segment_ticker_count_after": primary_count,
            "single_ticker_article_share_before": previous_summary.get("single_ticker_article_share"),
            "single_ticker_article_share_after": single_ticker_share,
            "dominant_ticker_before": previous_summary.get("dominant_ticker"),
            "dominant_ticker_after": dominant_ticker,
            "recommended_candidate_before": previous_summary.get("recommended_candidate_to_become_fifth_primary_ticker"),
            "recommended_candidate_after": _safe_str(recommended_candidate.get("ticker")),
            "candidate_entered_primary_after": candidate_entered_primary,
        },
        "recommended_next_move": (
            "Push article-day coverage pada boundary tickers selain kandidat utama agar median threshold split bisa naik, sambil membiarkan kandidat utama tetap di boundary untuk masuk primary segment dan menurunkan dominant share."
            if targeted_push_tickers
            else "Tidak ada boundary candidate tersisa; evaluasi ulang source-of-truth segmentation."
        ),
    }
    _write_json(output_dir / AUDIT_OUTPUT, payload)
    return payload


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit operational recovery targets for final Phase B gate blockers.")
    parser.add_argument("--output-dir", default="output", help="Directory containing readiness artifacts.")
    parser.add_argument("--metadata-file", default="data/ticker_metadata.csv", help="Ticker metadata CSV.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    payload = run_phase_b_final_gate_recovery_targets(
        output_dir=Path(args.output_dir),
        metadata_file=Path(args.metadata_file),
    )
    summary = safe_dict(payload.get("summary"))
    print("Phase B final gate recovery target audit complete.")
    print(f"primary_segment_ticker_count={summary.get('primary_segment_ticker_count')}")
    print(f"recommended_candidate={summary.get('recommended_candidate_to_become_fifth_primary_ticker')}")
    print(f"targeted_push_tickers={','.join(list(summary.get('targeted_push_tickers') or []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
