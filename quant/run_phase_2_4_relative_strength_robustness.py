"""Narrow robustness and freeze-decision pass for the Layer 2 prototype candidate."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import pandas as pd

if __package__ is None or __package__ == "":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.phase_a_baseline import (  # noqa: E402
    load_optional_metadata_lookup,
    load_phase_a_baseline,
)
from quant.run_phase_1_1_market_regime_filter_refinement import _load_ihsg_indicator_master  # noqa: E402
from quant.run_phase_2_1_relative_strength_redesign import (  # noqa: E402
    _apply_redesign_variant,
    _compute_redesign_scores,
    _prepare_layer1_signal_frame,
)
from quant.run_phase_2_3_relative_strength_confirmation import (  # noqa: E402
    _build_variant_registry,
    _pick_best_variant,
)
from quant.run_phase_2_relative_strength_stock_selection import (  # noqa: E402
    _classify_sample_adequacy_risk,
    _evaluate_variant_ticker,
)


SLICE_SUMMARY_COLUMNS = [
    "slice_id",
    "slice_label",
    "slice_group",
    "date_start",
    "date_end",
    "slice_date_count",
    "variant_id",
    "variant_label",
    "score_column",
    "selection_mode",
    "top_pct",
    "active_ticker_count_median",
    "active_ticker_count_min",
    "active_ticker_count_max",
    "active_ticker_count_mean",
    "active_single_ticker_day_pct",
    "total_signals",
    "total_trades",
    "median_trade_retention",
    "avg_delta_win_rate",
    "avg_delta_average_return",
    "tickers_with_coverage_collapse",
    "coverage_collapse_tickers",
    "sample_adequacy_risk",
    "sample_adequacy_reason",
]


@dataclass(frozen=True)
class RobustnessSlice:
    slice_id: str
    label: str
    slice_group: str
    dates: List[pd.Timestamp]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_slice_registry(
    prepared_frame: pd.DataFrame,
    ihsg_indicator_master_file: Path,
) -> List[RobustnessSlice]:
    unique_dates = (
        pd.Series(prepared_frame["date"].drop_duplicates().sort_values().tolist(), name="date")
        .reset_index(drop=True)
    )
    if unique_dates.empty:
        return []

    slices: List[RobustnessSlice] = [
        RobustnessSlice(
            slice_id="full_period",
            label="Full period",
            slice_group="all_dates",
            dates=list(unique_dates.tolist()),
        )
    ]

    dates_list = unique_dates.tolist()
    chunk_count = min(3, len(dates_list))
    chunk_sizes = [len(dates_list) // chunk_count] * chunk_count
    for idx in range(len(dates_list) % chunk_count):
        chunk_sizes[idx] += 1

    time_chunks: List[List[pd.Timestamp]] = []
    start = 0
    for size in chunk_sizes:
        end = start + size
        chunk = dates_list[start:end]
        if chunk:
            time_chunks.append(chunk)
        start = end
    time_labels = ["time_early", "time_mid", "time_late"]
    for idx, chunk in enumerate(time_chunks[:3]):
        slices.append(
            RobustnessSlice(
                slice_id=time_labels[idx],
                label=time_labels[idx].replace("_", " ").title(),
                slice_group="time",
                dates=chunk,
            )
        )

    ihsg_frame = _load_ihsg_indicator_master(ihsg_indicator_master_file).sort_values("date").reset_index(drop=True)
    aligned = pd.merge_asof(
        pd.DataFrame({"date": unique_dates}),
        ihsg_frame[["date", "ihsg_adj_close", "ihsg_ema200"]]
        .rename(
            columns={
                "date": "aligned_ihsg_date",
                "ihsg_adj_close": "aligned_ihsg_adj_close",
                "ihsg_ema200": "aligned_ihsg_ema200",
            }
        )
        .sort_values("aligned_ihsg_date"),
        left_on="date",
        right_on="aligned_ihsg_date",
        direction="backward",
    )
    aligned["regime_strength"] = (
        pd.to_numeric(aligned["aligned_ihsg_adj_close"], errors="coerce")
        / pd.to_numeric(aligned["aligned_ihsg_ema200"], errors="coerce")
        - 1.0
    )

    bullish_dates = (
        prepared_frame.loc[prepared_frame["market_regime_bullish"].astype(bool), "date"]
        .drop_duplicates()
        .sort_values()
        .reset_index(drop=True)
    )
    bullish_strength = aligned[aligned["date"].isin(bullish_dates)].dropna(subset=["regime_strength"]).copy()
    if len(bullish_strength) >= 30:
        bullish_strength["strength_bucket"] = pd.qcut(
            bullish_strength["regime_strength"],
            q=3,
            labels=["regime_low_strength", "regime_mid_strength", "regime_high_strength"],
            duplicates="drop",
        )
        for bucket in ["regime_low_strength", "regime_mid_strength", "regime_high_strength"]:
            bucket_dates = bullish_strength.loc[bullish_strength["strength_bucket"] == bucket, "date"].tolist()
            if bucket_dates:
                slices.append(
                    RobustnessSlice(
                        slice_id=bucket,
                        label=bucket.replace("_", " ").title(),
                        slice_group="regime_strength",
                        dates=bucket_dates,
                    )
                )
    return slices


def _summarize_variant_for_slice(
    frame: pd.DataFrame,
    per_ticker_df: pd.DataFrame,
    variant: object,
    slice_def: RobustnessSlice,
) -> Dict[str, object]:
    active_by_date = (
        frame.groupby("date")
        .agg(
            active_ticker_count=("active_selected", "sum"),
            available_ticker_count=("available_ticker_count", "max"),
            target_selected_count=("target_selected_count", "max"),
        )
        .reset_index()
    )
    collapse_tickers = (
        per_ticker_df.loc[per_ticker_df["coverage_collapsed"].astype(bool), "ticker"]
        .astype(str)
        .tolist()
    )
    summary = {
        "slice_id": slice_def.slice_id,
        "slice_label": slice_def.label,
        "slice_group": slice_def.slice_group,
        "date_start": min(slice_def.dates).strftime("%Y-%m-%d"),
        "date_end": max(slice_def.dates).strftime("%Y-%m-%d"),
        "slice_date_count": int(len(slice_def.dates)),
        "variant_id": variant.variant_id,
        "variant_label": variant.label,
        "score_column": variant.score_column,
        "selection_mode": variant.selection_mode,
        "top_pct": variant.top_pct,
        "active_ticker_count_median": round(float(active_by_date["active_ticker_count"].median()), 4),
        "active_ticker_count_min": int(active_by_date["active_ticker_count"].min()),
        "active_ticker_count_max": int(active_by_date["active_ticker_count"].max()),
        "active_ticker_count_mean": round(float(active_by_date["active_ticker_count"].mean()), 4),
        "active_single_ticker_day_pct": round(
            float(active_by_date["active_ticker_count"].eq(1).mean() * 100.0),
            4,
        ),
        "total_signals": int(per_ticker_df["variant_signals"].sum()),
        "total_trades": int(per_ticker_df["variant_total_trades"].sum()),
        "median_trade_retention": round(float(per_ticker_df["trade_retention_pct"].median()), 4),
        "avg_delta_win_rate": round(float(per_ticker_df["delta_win_rate"].mean()), 4),
        "avg_delta_average_return": round(float(per_ticker_df["delta_average_return"].mean()), 4),
        "tickers_with_coverage_collapse": int(len(collapse_tickers)),
        "coverage_collapse_tickers": collapse_tickers,
    }
    risk, reason = _classify_sample_adequacy_risk(
        summary,
        universe_max=int(active_by_date["available_ticker_count"].max()),
    )
    summary["sample_adequacy_risk"] = risk
    summary["sample_adequacy_reason"] = reason
    return summary


def _pick_slice_winner(slice_df: pd.DataFrame) -> Optional[str]:
    if slice_df.empty:
        return None
    normalized = slice_df.copy()
    if "variant_label" not in normalized.columns:
        normalized["variant_label"] = normalized["variant_id"].astype(str)
    if "total_trades" not in normalized.columns:
        normalized["total_trades"] = 0
    if "tickers_with_coverage_collapse" not in normalized.columns:
        normalized["tickers_with_coverage_collapse"] = 0
    best = _pick_best_variant(
        normalized[
            [
                "variant_id",
                "variant_label",
                "avg_delta_average_return",
                "avg_delta_win_rate",
                "median_trade_retention",
                "total_trades",
                "tickers_with_coverage_collapse",
            ]
        ]
    )
    return best.get("selected_variant_id")


def _build_robustness_diagnostics(slice_variant_df: pd.DataFrame, candidate_variant_id: str) -> Dict[str, object]:
    non_full = slice_variant_df[slice_variant_df["slice_id"] != "full_period"].copy()
    candidate_rows = non_full[non_full["variant_id"] == candidate_variant_id].copy()
    if candidate_rows.empty:
        return {"status": "candidate_missing"}

    winners = []
    for slice_id, group in non_full.groupby("slice_id"):
        winners.append(
            {
                "slice_id": slice_id,
                "winner_variant_id": _pick_slice_winner(group),
            }
        )
    candidate_wins = sum(1 for row in winners if row["winner_variant_id"] == candidate_variant_id)
    positive_return_slices = int(candidate_rows["avg_delta_average_return"].gt(0).sum())
    negative_return_slices = int(candidate_rows["avg_delta_average_return"].lt(0).sum())
    low_risk_slice_count = int(candidate_rows["sample_adequacy_risk"].eq("low").sum())
    severe_negative_slices = candidate_rows.loc[
        candidate_rows["avg_delta_average_return"].lt(-0.05),
        ["slice_id", "avg_delta_average_return", "avg_delta_win_rate", "median_trade_retention"],
    ].to_dict(orient="records")
    return {
        "candidate_variant_id": candidate_variant_id,
        "slice_count_excluding_full": int(candidate_rows["slice_id"].nunique()),
        "candidate_slice_win_count": int(candidate_wins),
        "candidate_positive_return_slice_count": positive_return_slices,
        "candidate_negative_return_slice_count": negative_return_slices,
        "candidate_low_risk_slice_count": low_risk_slice_count,
        "candidate_avg_delta_average_return_range": round(
            float(candidate_rows["avg_delta_average_return"].max() - candidate_rows["avg_delta_average_return"].min()),
            4,
        ),
        "candidate_avg_delta_win_rate_range": round(
            float(candidate_rows["avg_delta_win_rate"].max() - candidate_rows["avg_delta_win_rate"].min()),
            4,
        ),
        "candidate_median_trade_retention_range": round(
            float(candidate_rows["median_trade_retention"].max() - candidate_rows["median_trade_retention"].min()),
            4,
        ),
        "slice_winners": winners,
        "severe_negative_slices": severe_negative_slices,
    }


def _freeze_decision(slice_variant_df: pd.DataFrame, candidate_variant_id: str) -> Dict[str, object]:
    full_candidate = slice_variant_df[
        (slice_variant_df["slice_id"] == "full_period") & (slice_variant_df["variant_id"] == candidate_variant_id)
    ]
    if full_candidate.empty:
        return {
            "freeze_layer_2_candidate": False,
            "candidate_variant_id": candidate_variant_id,
            "reason": "Candidate row is missing from the robustness pass.",
            "remaining_blocker": "candidate_missing_from_robustness_pass",
        }
    full_row = full_candidate.iloc[0]
    diagnostics = _build_robustness_diagnostics(slice_variant_df, candidate_variant_id)
    win_count = int(diagnostics.get("candidate_slice_win_count", 0))
    slice_count = int(diagnostics.get("slice_count_excluding_full", 0))
    robust_enough = bool(
        int(full_row["tickers_with_coverage_collapse"]) == 0
        and str(full_row["sample_adequacy_risk"]) == "low"
        and float(full_row["avg_delta_average_return"]) > 0.0
        and float(full_row["median_trade_retention"]) >= 50.0
        and win_count >= max(3, slice_count - 2)
        and int(diagnostics.get("candidate_negative_return_slice_count", 999)) <= 1
        and float(diagnostics.get("candidate_avg_delta_average_return_range", 999.0)) <= 0.30
        and not diagnostics.get("severe_negative_slices")
    )
    if robust_enough:
        reason = (
            "Candidate keeps a positive full-period quality delta, remains best across most robustness slices, "
            "and does not show materially negative slice concentration."
        )
        blocker = None
    else:
        if int(diagnostics.get("candidate_slice_win_count", 0)) < max(3, int(diagnostics.get("slice_count_excluding_full", 0)) - 2):
            blocker = "candidate_advantage_is_concentrated_in_too_few_time_or_regime_slices"
        elif diagnostics.get("severe_negative_slices"):
            blocker = "candidate_turns_materially_negative_in_specific_time_or_regime_slice"
        else:
            blocker = "candidate_slice_to_slice_quality_range_still_too_wide_for_final_freeze"
        reason = (
            "Candidate is still not robust enough across time/regime slices to freeze Layer 2 as a final candidate."
        )
    return {
        "freeze_layer_2_candidate": robust_enough,
        "candidate_variant_id": candidate_variant_id,
        "reason": reason,
        "remaining_blocker": blocker,
        "robustness_diagnostics": diagnostics,
    }


def run_phase_2_4_relative_strength_robustness(
    *,
    stock_indicator_master_file: Path,
    ihsg_indicator_master_file: Path,
    phase_2_3_summary_file: Path,
    output_dir: Path,
    hold_period: int = 5,
    allow_overlap: bool = False,
    baseline_config: Optional[Path] = None,
    metadata_file: Optional[Path] = None,
) -> Dict[str, object]:
    baseline_payload, baseline_warnings, baseline_source = load_phase_a_baseline(baseline_config=baseline_config)
    metadata_lookup, metadata_warnings = load_optional_metadata_lookup(metadata_file)
    prepared_frame = _prepare_layer1_signal_frame(
        stock_indicator_master_file,
        ihsg_indicator_master_file,
        baseline_payload=baseline_payload,
        metadata_lookup=metadata_lookup,
    )
    redesign_frame = _compute_redesign_scores(prepared_frame)
    variants = _build_variant_registry()
    slices = _build_slice_registry(prepared_frame, ihsg_indicator_master_file)

    slice_rows: List[Dict[str, object]] = []
    for slice_def in slices:
        slice_frame = redesign_frame[redesign_frame["date"].isin(slice_def.dates)].copy()
        if slice_frame.empty:
            continue
        for variant in variants:
            variant_frame = _apply_redesign_variant(slice_frame, variant)
            ticker_rows: List[Dict[str, object]] = []
            for ticker, group in variant_frame.groupby("ticker"):
                ticker_rows.append(
                    {
                        "variant_id": variant.variant_id,
                        "variant_label": variant.label,
                        **_evaluate_variant_ticker(
                            ticker,
                            group.copy(),
                            hold_period=hold_period,
                            allow_overlap=allow_overlap,
                        ),
                    }
                )
            per_ticker_df = pd.DataFrame(ticker_rows)
            slice_rows.append(_summarize_variant_for_slice(variant_frame, per_ticker_df, variant, slice_def))

    slice_variant_df = pd.DataFrame(slice_rows).reindex(columns=SLICE_SUMMARY_COLUMNS)
    freeze_decision = _freeze_decision(slice_variant_df, candidate_variant_id="top_25pct_return_20d")
    phase_2_3_summary = json.loads(phase_2_3_summary_file.read_text(encoding="utf-8"))

    output_dir.mkdir(parents=True, exist_ok=True)
    per_slice_path = output_dir / "phase_2_4_relative_strength_robustness_per_slice.csv"
    summary_path = output_dir / "phase_2_4_relative_strength_robustness_summary.json"
    report_path = output_dir / "phase_2_4_relative_strength_robustness_report.txt"

    slice_variant_df.to_csv(per_slice_path, index=False)

    summary_payload = {
        "phase": "phase_2_4_relative_strength_robustness",
        "status": "completed",
        "generated_at": _now_iso(),
        "candidate_under_confirmation": "top_25pct_return_20d",
        "source_files": {
            "stock_indicator_master_file": str(stock_indicator_master_file),
            "ihsg_indicator_master_file": str(ihsg_indicator_master_file),
            "phase_2_3_summary_file": str(phase_2_3_summary_file),
            "baseline_config": str(baseline_source) if baseline_source else None,
            "metadata_file": str(metadata_file) if metadata_file is not None else None,
        },
        "prior_status_context": {
            "phase_2_3_candidate_still_best": phase_2_3_summary.get("freeze_decision", {}).get("candidate_still_best"),
            "phase_2_3_freeze_layer_2_candidate": phase_2_3_summary.get("freeze_decision", {}).get("freeze_layer_2_candidate"),
            "phase_2_3_remaining_blocker": phase_2_3_summary.get("freeze_decision", {}).get("remaining_blocker"),
        },
        "slices_tested": [
            {
                "slice_id": slice_def.slice_id,
                "slice_label": slice_def.label,
                "slice_group": slice_def.slice_group,
                "slice_date_count": len(slice_def.dates),
            }
            for slice_def in slices
        ],
        "slice_variant_results": slice_variant_df.to_dict(orient="records"),
        "freeze_decision": freeze_decision,
        "warnings": [*baseline_warnings, *metadata_warnings],
    }
    summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    report_lines = [
        "Phase 2.4 - Narrow Robustness / Freeze Decision Pass",
        "====================================================",
        "",
        "Candidate under robustness pass:",
        "- top_25pct_return_20d",
        "",
        "Slice results:",
    ]
    for slice_id, group in slice_variant_df.groupby("slice_id"):
        header = group.iloc[0]
        report_lines.append(
            f"- {slice_id}: {header['slice_label']} ({header['slice_group']}, {header['date_start']}..{header['date_end']}, dates={header['slice_date_count']})"
        )
        for _, row in group.iterrows():
            report_lines.append(
                f"  {row['variant_id']}: trades={row['total_trades']}, retention={row['median_trade_retention']}, delta_win_rate={row['avg_delta_win_rate']}, delta_avg_return={row['avg_delta_average_return']}, sample={row['sample_adequacy_risk']}"
            )
    diagnostics = freeze_decision.get("robustness_diagnostics", {})
    report_lines.extend(
        [
            "",
            "Decision:",
            f"- freeze_layer_2_candidate = {freeze_decision['freeze_layer_2_candidate']}",
            f"- reason = {freeze_decision['reason']}",
            f"- candidate_slice_win_count = {diagnostics.get('candidate_slice_win_count')}",
            f"- candidate_positive_return_slice_count = {diagnostics.get('candidate_positive_return_slice_count')}",
            f"- candidate_negative_return_slice_count = {diagnostics.get('candidate_negative_return_slice_count')}",
            f"- candidate_avg_delta_average_return_range = {diagnostics.get('candidate_avg_delta_average_return_range')}",
        ]
    )
    if freeze_decision.get("remaining_blocker"):
        report_lines.append(f"- remaining_blocker = {freeze_decision['remaining_blocker']}")
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    return {
        "per_slice_path": per_slice_path,
        "summary_path": summary_path,
        "report_path": report_path,
        "summary": summary_payload,
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase 2.4 narrow robustness pass for Layer 2.")
    parser.add_argument(
        "--stock-indicator-master-file",
        default="data/indicator_master/stock_indicator_master.csv",
        help="Stock indicator master CSV for the rebuild path.",
    )
    parser.add_argument(
        "--ihsg-indicator-master-file",
        default="data/indicator_master/IHSG_indicator_master.csv",
        help="IHSG indicator master CSV with frozen Layer 1 inputs.",
    )
    parser.add_argument(
        "--phase-2-3-summary-file",
        default="output/phase_2_3_relative_strength_confirmation_summary.json",
        help="Phase 2.3 summary JSON used as source of truth.",
    )
    parser.add_argument("--output-dir", default="output", help="Directory for Phase 2.4 artifacts.")
    parser.add_argument("--hold-period", default=5, type=int, help="Backtest hold period.")
    parser.add_argument("--allow-overlap", action="store_true", help="Allow overlapping trades.")
    parser.add_argument(
        "--baseline-config",
        default="output/phase_a_baseline_final.json",
        help="Frozen Phase A baseline config path.",
    )
    parser.add_argument(
        "--metadata-file",
        default="data/ticker_metadata.csv",
        help="Optional metadata file for threshold overrides.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    run_phase_2_4_relative_strength_robustness(
        stock_indicator_master_file=Path(args.stock_indicator_master_file),
        ihsg_indicator_master_file=Path(args.ihsg_indicator_master_file),
        phase_2_3_summary_file=Path(args.phase_2_3_summary_file),
        output_dir=Path(args.output_dir),
        hold_period=int(args.hold_period),
        allow_overlap=bool(args.allow_overlap),
        baseline_config=Path(args.baseline_config) if args.baseline_config else None,
        metadata_file=Path(args.metadata_file) if args.metadata_file else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
