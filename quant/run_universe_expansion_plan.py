"""Prepare a defensible expanded universe scaffold for Layer 2 validation.

This command does not fetch any new market data. It audits the current pilot
universe, evaluates whether repo-local metadata is sufficient for expansion,
and publishes a freeze-ready plan plus next commands.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


RECOMMENDED_TARGET_SIZE = 30
MINIMUM_DEFENSIBLE_SIZE = 24
MINIMUM_HISTORY_ROWS = 1250
MINIMUM_MEDIAN_DAILY_TURNOVER_IDR = 50_000_000_000
MINIMUM_SECTOR_GROUPS = 6
MAX_NAMES_PER_SECTOR_GROUP = 8
SUMMARY_JSON_FILENAME = "universe_expansion_plan_summary.json"
REPORT_TXT_FILENAME = "universe_expansion_plan_report.txt"
ALLOWED_FETCH_FREEZE_STATUSES = {"frozen", "approved"}


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_rebuild_metadata_file(path: Path) -> Path:
    if path.exists():
        return path
    fallback = path.with_name("ticker_metadata.csv")
    if fallback.exists():
        return fallback
    return path


def _safe_float(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _find_variant_row(summary_payload: dict[str, Any], variant_id: str) -> dict[str, Any]:
    for row in summary_payload.get("variant_results", []):
        if row.get("variant_id") == variant_id:
            return dict(row)
    return {}


def build_universe_expansion_plan(
    *,
    metadata_file: Path,
    rebuild_metadata_file: Path,
    phase_2_summary_file: Path,
    phase_2_1_summary_file: Path,
    candidate_file: Path,
    output_dir: Path,
) -> dict[str, Any]:
    metadata_rows = _read_csv_rows(metadata_file)
    resolved_rebuild_metadata_file = _resolve_rebuild_metadata_file(rebuild_metadata_file)
    rebuild_rows = _read_csv_rows(resolved_rebuild_metadata_file)
    phase_2_summary = _read_json(phase_2_summary_file)
    phase_2_1_summary = _read_json(phase_2_1_summary_file)
    candidate_rows = _read_csv_rows(candidate_file)

    current_rankable_max = int(
        phase_2_summary.get("universe_size_assessment", {}).get("max_rankable_tickers_on_any_date") or 0
    )
    current_variant = _find_variant_row(phase_2_1_summary, "layer1_full_universe")
    current_active_median = _safe_float(current_variant.get("active_ticker_count_median")) or 0.0

    implied_selection_counts = {
        "current_max_rankable_top_30pct": int(round(current_rankable_max * 0.30)),
        "current_max_rankable_top_40pct": int(round(current_rankable_max * 0.40)),
        "current_max_rankable_top_50pct": int(round(current_rankable_max * 0.50)),
        "minimum_defensible_top_30pct": int(round(MINIMUM_DEFENSIBLE_SIZE * 0.30)),
        "minimum_defensible_top_40pct": int(round(MINIMUM_DEFENSIBLE_SIZE * 0.40)),
        "minimum_defensible_top_50pct": int(round(MINIMUM_DEFENSIBLE_SIZE * 0.50)),
        "recommended_target_top_30pct": int(round(RECOMMENDED_TARGET_SIZE * 0.30)),
        "recommended_target_top_40pct": int(round(RECOMMENDED_TARGET_SIZE * 0.40)),
        "recommended_target_top_50pct": int(round(RECOMMENDED_TARGET_SIZE * 0.50)),
    }

    current_sectors = sorted({str(row.get("sector") or "").strip().lower() for row in metadata_rows if row.get("sector")})
    clean_rebuilt_tickers = sorted(
        row["ticker"].strip().upper()
        for row in rebuild_rows
        if str(row.get("status") or "").strip().lower() == "rebuilt" and str(row.get("ticker") or "").strip().upper() != "IHSG"
    )
    candidate_sector_groups = sorted(
        {str(row.get("sector_group") or "").strip().lower() for row in candidate_rows if row.get("sector_group")}
    )
    repo_available_candidates = [
        row["ticker"].strip().upper()
        for row in candidate_rows
        if "in_repo" in str(row.get("availability_status") or "").strip().lower()
    ]
    already_clean_candidates = [
        row["ticker"].strip().upper()
        for row in candidate_rows
        if str(row.get("availability_status") or "").strip().lower() == "in_repo_clean_rebuild"
    ]
    frozen_candidate_count = sum(
        1 for row in candidate_rows if str(row.get("freeze_status") or "").strip().lower() in ALLOWED_FETCH_FREEZE_STATUSES
    )

    repo_metadata_assessment = {
        "enough_for_current_pilot_audit": True,
        "enough_for_expanded_universe_freeze_without_external_or_manual_list": False,
        "reason": (
            "Repo hanya punya metadata operasional untuk 12 ticker lama dan rebuild bersih untuk 7 ticker, "
            "tanpa market-wide listing-status/liquidity master untuk memilih tambahan 18-23 ticker secara otomatis."
        ),
        "current_metadata_ticker_count": len(metadata_rows),
        "current_clean_rebuild_count": len(clean_rebuilt_tickers),
    }

    recommendation = {
        "recommended_universe_policy": "custom_30_liquid_long_history_manual_freeze",
        "recommended_target_size": RECOMMENDED_TARGET_SIZE,
        "minimum_defensible_size": MINIMUM_DEFENSIBLE_SIZE,
        "why_not_idx30_or_lq45_direct_only": (
            "Repo tidak menyimpan snapshot membership index yang siap dipakai sebagai source of truth, "
            "jadi index hanya dipakai sebagai referensi gaya likuiditas, bukan daftar final otomatis."
        ),
        "why_30_is_picked": (
            "Pada target 30 ticker, cut RS 30-50% akan memilih sekitar 9-15 nama per date, "
            "jauh lebih sehat daripada universe saat ini yang praktis hanya menyisakan 2-3 nama."
        ),
    }

    next_commands = [
        {
            "step": "freeze_universe_file",
            "command": "Edit data/universe/layer2_expansion_target_candidates.csv lalu ubah freeze_status kandidat final menjadi frozen.",
        },
        {
            "step": "rebuild_expanded_ohlcv",
            "command": "python3 -m quant.rebuild_yfinance_ohlcv --universe-file data/universe/layer2_expansion_target_candidates.csv --output-dir data/stocks",
        },
        {
            "step": "rebuild_indicator_master",
            "command": "python3 -m quant.build_indicator_master_table --stocks-dir data/stocks --ihsg-file data/IHSG.csv --output-dir data/indicator_master --artifact-dir output",
        },
        {
            "step": "rerun_phase_2",
            "command": "python3 -m quant.run_phase_2_relative_strength_stock_selection",
        },
        {
            "step": "rerun_phase_2_1",
            "command": "python3 -m quant.run_phase_2_1_relative_strength_redesign",
        },
    ]

    summary = {
        "phase": "universe_expansion_for_layer_2",
        "status": "completed_scaffold_only",
        "source_files": {
            "metadata_file": str(metadata_file),
            "rebuild_metadata_file": str(resolved_rebuild_metadata_file),
            "phase_2_summary_file": str(phase_2_summary_file),
            "phase_2_1_summary_file": str(phase_2_1_summary_file),
            "candidate_file": str(candidate_file),
        },
        "current_universe_audit": {
            "current_metadata_ticker_count": len(metadata_rows),
            "current_clean_rebuild_count": len(clean_rebuilt_tickers),
            "current_rankable_max_tickers_on_any_date": current_rankable_max,
            "current_active_ticker_count_median_after_layer_1": current_active_median,
            "current_sector_count_from_metadata": len(current_sectors),
            "current_sector_list": current_sectors,
            "reason_layer_2_blocked": "Current rankable breadth is too small for defensible relative-strength selection validation.",
        },
        "target_universe_decision": {
            "recommended_universe_policy": recommendation["recommended_universe_policy"],
            "recommended_target_size": RECOMMENDED_TARGET_SIZE,
            "minimum_defensible_size": MINIMUM_DEFENSIBLE_SIZE,
            "implied_selection_counts": implied_selection_counts,
        },
        "inclusion_criteria": {
            "history_minimum_daily_rows": MINIMUM_HISTORY_ROWS,
            "minimum_median_daily_turnover_idr_after_rebuild": MINIMUM_MEDIAN_DAILY_TURNOVER_IDR,
            "listing_status": "active_common_stock_on_idx_only",
            "data_cleanliness_checks": [
                "no_weekend_rows",
                "no_duplicate_dates",
                "ascending_dates",
                "no_mixed_frequency_contamination",
                "no_missing_core_prices",
            ],
            "sector_diversification": {
                "minimum_sector_groups": MINIMUM_SECTOR_GROUPS,
                "maximum_names_per_sector_group": MAX_NAMES_PER_SECTOR_GROUP,
            },
        },
        "repo_metadata_assessment": repo_metadata_assessment,
        "candidate_file_summary": {
            "candidate_count": len(candidate_rows),
            "candidate_sector_group_count": len(candidate_sector_groups),
            "candidate_sector_groups": candidate_sector_groups,
            "repo_available_candidate_count": len(repo_available_candidates),
            "repo_available_candidates": repo_available_candidates,
            "already_clean_candidate_count": len(already_clean_candidates),
            "already_clean_candidates": already_clean_candidates,
            "frozen_candidate_count": frozen_candidate_count,
        },
        "recommendation": recommendation,
        "next_commands": next_commands,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / SUMMARY_JSON_FILENAME
    report_path = output_dir / REPORT_TXT_FILENAME
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    report_lines = [
        "Universe Expansion Plan",
        "=======================",
        "",
        f"Current metadata universe = {len(metadata_rows)} ticker",
        f"Current clean rebuild universe = {len(clean_rebuilt_tickers)} ticker",
        f"Current max rankable breadth from Phase 2 = {current_rankable_max} ticker",
        f"Current median active breadth after Layer 1 = {current_active_median}",
        "",
        f"Recommended target policy = {recommendation['recommended_universe_policy']}",
        f"Recommended target size = {RECOMMENDED_TARGET_SIZE}",
        f"Minimum defensible size = {MINIMUM_DEFENSIBLE_SIZE}",
        f"Target 30 implies RS buckets around top30={implied_selection_counts['recommended_target_top_30pct']}, "
        f"top40={implied_selection_counts['recommended_target_top_40pct']}, "
        f"top50={implied_selection_counts['recommended_target_top_50pct']}",
        "",
        "Inclusion criteria:",
        f"- history_minimum_daily_rows = {MINIMUM_HISTORY_ROWS}",
        f"- minimum_median_daily_turnover_idr_after_rebuild = {MINIMUM_MEDIAN_DAILY_TURNOVER_IDR}",
        "- listing_status = active_common_stock_on_idx_only",
        "- data_cleanliness = no_weekend/no_duplicate/ascending/no_mixed_frequency/no_missing_core_prices",
        f"- sector_diversification = minimum {MINIMUM_SECTOR_GROUPS} groups, maximum {MAX_NAMES_PER_SECTOR_GROUP} names per group",
        "",
        "Repo metadata assessment:",
        f"- enough_for_current_pilot_audit = {repo_metadata_assessment['enough_for_current_pilot_audit']}",
        f"- enough_for_expanded_universe_freeze_without_external_or_manual_list = {repo_metadata_assessment['enough_for_expanded_universe_freeze_without_external_or_manual_list']}",
        f"- reason = {repo_metadata_assessment['reason']}",
        "",
        f"Candidate file = {candidate_file}",
        f"- candidate_count = {len(candidate_rows)}",
        f"- repo_available_candidate_count = {len(repo_available_candidates)}",
        f"- already_clean_candidate_count = {len(already_clean_candidates)}",
        f"- frozen_candidate_count = {frozen_candidate_count}",
        "",
        "Next commands after freeze:",
    ]
    for item in next_commands:
        report_lines.append(f"- {item['step']}: {item['command']}")
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    return summary


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare expanded-universe scaffold for Layer 2 validation.")
    parser.add_argument("--metadata-file", default="data/ticker_metadata.csv", help="Current ticker metadata CSV.")
    parser.add_argument(
        "--rebuild-metadata-file",
        default="data/stocks/rebuild_ticker_metadata.csv",
        help="Current clean rebuild metadata CSV. Falls back to data/stocks/ticker_metadata.csv when needed.",
    )
    parser.add_argument(
        "--phase-2-summary-file",
        default="output/phase_2_relative_strength_selection_summary.json",
        help="Phase 2 summary JSON.",
    )
    parser.add_argument(
        "--phase-2-1-summary-file",
        default="output/phase_2_1_relative_strength_redesign_summary.json",
        help="Phase 2.1 summary JSON.",
    )
    parser.add_argument(
        "--candidate-file",
        default="data/universe/layer2_expansion_target_candidates.csv",
        help="Expanded-universe candidate CSV.",
    )
    parser.add_argument("--output-dir", default="output", help="Directory for summary artifacts.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    build_universe_expansion_plan(
        metadata_file=Path(args.metadata_file),
        rebuild_metadata_file=Path(args.rebuild_metadata_file),
        phase_2_summary_file=Path(args.phase_2_summary_file),
        phase_2_1_summary_file=Path(args.phase_2_1_summary_file),
        candidate_file=Path(args.candidate_file),
        output_dir=Path(args.output_dir),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
