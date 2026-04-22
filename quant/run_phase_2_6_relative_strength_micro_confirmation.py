"""Micro confirmation and final freeze decision pass for Layer 2."""

from __future__ import annotations

import argparse
import json
import math
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
from quant.run_phase_2_1_relative_strength_redesign import (  # noqa: E402
    _compute_redesign_scores,
    _prepare_layer1_signal_frame,
)
from quant.run_phase_2_3_relative_strength_confirmation import _pick_best_variant  # noqa: E402
from quant.run_phase_2_4_relative_strength_robustness import (  # noqa: E402
    SLICE_SUMMARY_COLUMNS,
    _build_robustness_diagnostics,
    _build_slice_registry,
    _summarize_variant_for_slice,
)
from quant.run_phase_2_relative_strength_stock_selection import _evaluate_variant_ticker  # noqa: E402


MICRO_SUMMARY_COLUMNS = [
    "variant_id",
    "variant_label",
    "policy_family",
    "top_pct",
    "full_period_total_trades",
    "full_period_median_trade_retention",
    "full_period_avg_delta_win_rate",
    "full_period_avg_delta_average_return",
    "full_period_sample_adequacy_risk",
    "full_period_tickers_with_coverage_collapse",
    "slice_count_excluding_full",
    "candidate_slice_win_count",
    "candidate_positive_return_slice_count",
    "candidate_negative_return_slice_count",
    "candidate_low_risk_slice_count",
    "candidate_avg_delta_average_return_range",
    "candidate_avg_delta_win_rate_range",
    "candidate_median_trade_retention_range",
]


@dataclass(frozen=True)
class MicroVariant:
    variant_id: str
    label: str
    score_column: str
    selection_mode: str
    top_pct: float
    cut_rounding: str
    deterministic_tie_breaker: str
    min_active_breadth_floor: int
    policy_family: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_micro_variant_registry() -> List[MicroVariant]:
    return [
        MicroVariant(
            variant_id="top_25pct_return_20d_explicit_tie_ceil_policy",
            label="Top 25% by return_20d with explicit tie handling and ceil cut",
            score_column="rs_score_return_20d",
            selection_mode="top_pct_micro",
            top_pct=0.25,
            cut_rounding="ceil",
            deterministic_tie_breaker="ticker_asc",
            min_active_breadth_floor=0,
            policy_family="explicit_tie_ceil",
        ),
        MicroVariant(
            variant_id="top_25pct_return_20d_integer_floor_policy",
            label="Top 25% by return_20d with integer floor cut per date",
            score_column="rs_score_return_20d",
            selection_mode="top_pct_micro",
            top_pct=0.25,
            cut_rounding="floor",
            deterministic_tie_breaker="ticker_asc",
            min_active_breadth_floor=0,
            policy_family="integer_floor",
        ),
        MicroVariant(
            variant_id="top_25pct_return_20d_min_breadth_floor_3_policy",
            label="Top 25% by return_20d with minimum active breadth floor 3",
            score_column="rs_score_return_20d",
            selection_mode="top_pct_micro",
            top_pct=0.25,
            cut_rounding="ceil",
            deterministic_tie_breaker="ticker_asc",
            min_active_breadth_floor=3,
            policy_family="min_breadth_floor_3",
        ),
    ]


def _target_selected_count(rankable_count: int, top_pct: float, rounding: str, min_active_breadth_floor: int) -> int:
    if rankable_count <= 0:
        return 0
    raw = float(rankable_count) * float(top_pct)
    if rounding == "floor":
        count = int(math.floor(raw))
    else:
        count = int(math.ceil(raw))
    count = max(1, count)
    if min_active_breadth_floor > 0:
        count = max(count, min(int(min_active_breadth_floor), int(rankable_count)))
    return int(min(count, int(rankable_count)))


def _apply_micro_variant(frame: pd.DataFrame, variant: MicroVariant) -> pd.DataFrame:
    working = frame.sort_values(["date", "ticker"]).reset_index(drop=True).copy()
    score_column = variant.score_column
    working["rs_score_active"] = pd.to_numeric(working[score_column], errors="coerce")
    working["rankable_for_rs"] = working["rs_score_active"].notna()
    working["rankable_ticker_count"] = working.groupby("date")["rankable_for_rs"].transform("sum").astype(int)
    working["available_ticker_count"] = working.groupby("date")["ticker"].transform("count").astype(int)
    working["row_id"] = range(len(working))

    ranked = working.loc[working["rankable_for_rs"]].copy()
    ranked = ranked.sort_values(
        ["date", "rs_score_active", "ticker"],
        ascending=[True, False, True],
    )
    ranked["rs_rank"] = ranked.groupby("date").cumcount() + 1
    working = working.merge(ranked[["row_id", "rs_rank"]], on="row_id", how="left")
    working["rs_rank"] = working["rs_rank"].astype("Float64")

    per_date_target = (
        working[["date", "rankable_ticker_count"]]
        .drop_duplicates(subset=["date"], keep="last")
        .assign(
            target_selected_count=lambda df: df["rankable_ticker_count"].apply(
                lambda value: _target_selected_count(
                    int(value),
                    top_pct=float(variant.top_pct),
                    rounding=variant.cut_rounding,
                    min_active_breadth_floor=int(variant.min_active_breadth_floor),
                )
            )
        )
    )
    working = working.merge(
        per_date_target[["date", "target_selected_count"]],
        on="date",
        how="left",
    )
    working["target_selected_count"] = working["target_selected_count"].fillna(0).astype(int)
    working["rs_selected"] = (
        working["market_regime_bullish"].astype(bool)
        & working["rankable_for_rs"].astype(bool)
        & working["rs_rank"].notna()
        & working["rs_rank"].le(working["target_selected_count"])
    )
    working["active_selected"] = working["rs_selected"].astype(bool)
    working["phase_2_signal"] = (working["phase_1_signal_layer1"] & working["active_selected"]).fillna(False)
    working["phase_2_entry_skipped"] = (
        working["phase_1_signal_layer1"] & ~working["active_selected"]
    ).fillna(False)
    return working.sort_values(["date", "ticker"]).reset_index(drop=True)


def _build_micro_policy_summary(slice_variant_df: pd.DataFrame, variants: List[MicroVariant]) -> pd.DataFrame:
    family_lookup = {variant.variant_id: variant.policy_family for variant in variants}
    rows: List[Dict[str, object]] = []
    for variant_id in slice_variant_df["variant_id"].dropna().drop_duplicates().tolist():
        full_row = slice_variant_df[
            (slice_variant_df["slice_id"] == "full_period") & (slice_variant_df["variant_id"] == variant_id)
        ]
        if full_row.empty:
            continue
        full_row = full_row.iloc[0]
        diagnostics = _build_robustness_diagnostics(slice_variant_df, candidate_variant_id=str(variant_id))
        rows.append(
            {
                "variant_id": str(variant_id),
                "variant_label": str(full_row["variant_label"]),
                "policy_family": str(family_lookup.get(str(variant_id), "unknown")),
                "top_pct": float(full_row["top_pct"]),
                "full_period_total_trades": int(full_row["total_trades"]),
                "full_period_median_trade_retention": round(float(full_row["median_trade_retention"]), 4),
                "full_period_avg_delta_win_rate": round(float(full_row["avg_delta_win_rate"]), 4),
                "full_period_avg_delta_average_return": round(float(full_row["avg_delta_average_return"]), 4),
                "full_period_sample_adequacy_risk": str(full_row["sample_adequacy_risk"]),
                "full_period_tickers_with_coverage_collapse": int(full_row["tickers_with_coverage_collapse"]),
                "slice_count_excluding_full": int(diagnostics.get("slice_count_excluding_full", 0)),
                "candidate_slice_win_count": int(diagnostics.get("candidate_slice_win_count", 0)),
                "candidate_positive_return_slice_count": int(diagnostics.get("candidate_positive_return_slice_count", 0)),
                "candidate_negative_return_slice_count": int(diagnostics.get("candidate_negative_return_slice_count", 0)),
                "candidate_low_risk_slice_count": int(diagnostics.get("candidate_low_risk_slice_count", 0)),
                "candidate_avg_delta_average_return_range": round(
                    float(diagnostics.get("candidate_avg_delta_average_return_range", 999.0)),
                    4,
                ),
                "candidate_avg_delta_win_rate_range": round(
                    float(diagnostics.get("candidate_avg_delta_win_rate_range", 999.0)),
                    4,
                ),
                "candidate_median_trade_retention_range": round(
                    float(diagnostics.get("candidate_median_trade_retention_range", 999.0)),
                    4,
                ),
            }
        )
    return pd.DataFrame(rows).reindex(columns=MICRO_SUMMARY_COLUMNS)


def _select_micro_policy(micro_df: pd.DataFrame) -> Dict[str, object]:
    if micro_df.empty:
        return {
            "status": "no_candidate",
            "selected_variant_id": None,
            "selected_variant_label": None,
            "reason": "Micro confirmation did not produce any candidate rows.",
        }

    eligible = micro_df[
        micro_df["full_period_tickers_with_coverage_collapse"].eq(0)
        & micro_df["full_period_sample_adequacy_risk"].eq("low")
        & micro_df["full_period_avg_delta_average_return"].gt(0)
    ].copy()
    if eligible.empty:
        eligible = micro_df.copy()

    eligible = eligible.sort_values(
        by=[
            "candidate_slice_win_count",
            "candidate_negative_return_slice_count",
            "candidate_low_risk_slice_count",
            "full_period_avg_delta_average_return",
            "candidate_avg_delta_average_return_range",
            "full_period_median_trade_retention",
            "full_period_total_trades",
        ],
        ascending=[False, True, False, False, True, False, False],
    ).reset_index(drop=True)
    best = eligible.iloc[0]
    return {
        "status": "selected",
        "selected_variant_id": str(best["variant_id"]),
        "selected_variant_label": str(best["variant_label"]),
        "reason": (
            "Selected the micro-policy that best preserved positive full-period quality while maximizing "
            "slice robustness and keeping dispersion as contained as possible."
        ),
    }


def _freeze_decision(micro_df: pd.DataFrame, candidate_variant_id: str) -> Dict[str, object]:
    candidate = micro_df[micro_df["variant_id"] == candidate_variant_id]
    if candidate.empty:
        return {
            "freeze_layer_2_candidate": False,
            "lock_not_frozen_yet": True,
            "candidate_variant_id": candidate_variant_id,
            "reason": "Selected micro-policy is missing from the Phase 2.6 summary.",
            "remaining_blocker": "selected_micro_policy_missing_from_phase_2_6_summary",
        }

    row = candidate.iloc[0]
    slice_count = int(row["slice_count_excluding_full"])
    win_count = int(row["candidate_slice_win_count"])
    robust_enough = bool(
        int(row["full_period_tickers_with_coverage_collapse"]) == 0
        and str(row["full_period_sample_adequacy_risk"]) == "low"
        and float(row["full_period_avg_delta_average_return"]) > 0.0
        and float(row["full_period_median_trade_retention"]) >= 50.0
        and win_count >= max(4, slice_count - 2)
        and int(row["candidate_negative_return_slice_count"]) <= 1
        and int(row["candidate_low_risk_slice_count"]) >= 4
        and float(row["candidate_avg_delta_average_return_range"]) <= 0.90
    )

    if robust_enough:
        return {
            "freeze_layer_2_candidate": True,
            "lock_not_frozen_yet": False,
            "candidate_variant_id": candidate_variant_id,
            "reason": (
                "Selected micro-policy keeps the full-period candidate positive while crossing the minimum "
                "robustness threshold across the frozen time/regime slices."
            ),
            "remaining_blocker": None,
            "micro_diagnostics": row.to_dict(),
        }

    if win_count < max(4, slice_count - 2):
        blocker = "micro_policy_still_does_not_break_slice_concentration_blocker"
    elif float(row["candidate_avg_delta_average_return_range"]) > 0.90:
        blocker = "micro_policy_still_has_too_wide_slice_quality_dispersion"
    else:
        blocker = "micro_policy_still_not_decisive_enough_for_final_freeze"
    return {
        "freeze_layer_2_candidate": False,
        "lock_not_frozen_yet": True,
        "candidate_variant_id": candidate_variant_id,
        "reason": (
            "Final micro confirmation still does not make the Layer 2 candidate robust enough to freeze, "
            "so the project should lock the status as not_frozen_yet."
        ),
        "remaining_blocker": blocker,
        "micro_diagnostics": row.to_dict(),
    }


def run_phase_2_6_relative_strength_micro_confirmation(
    *,
    stock_indicator_master_file: Path,
    ihsg_indicator_master_file: Path,
    phase_2_5_summary_file: Path,
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
    variants = _build_micro_variant_registry()
    slices = _build_slice_registry(prepared_frame, ihsg_indicator_master_file)

    slice_rows: List[Dict[str, object]] = []
    for slice_def in slices:
        slice_frame = redesign_frame[redesign_frame["date"].isin(slice_def.dates)].copy()
        if slice_frame.empty:
            continue
        for variant in variants:
            variant_frame = _apply_micro_variant(slice_frame, variant)
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
    micro_summary_df = _build_micro_policy_summary(slice_variant_df, variants)
    selection_decision = _select_micro_policy(micro_summary_df)
    freeze_decision = _freeze_decision(
        micro_summary_df,
        candidate_variant_id=str(selection_decision.get("selected_variant_id")),
    )
    phase_2_5_summary = json.loads(phase_2_5_summary_file.read_text(encoding="utf-8"))

    output_dir.mkdir(parents=True, exist_ok=True)
    per_slice_path = output_dir / "phase_2_6_relative_strength_micro_confirmation_per_slice.csv"
    per_policy_path = output_dir / "phase_2_6_relative_strength_micro_confirmation_per_policy.csv"
    summary_path = output_dir / "phase_2_6_relative_strength_micro_confirmation_summary.json"
    report_path = output_dir / "phase_2_6_relative_strength_micro_confirmation_report.txt"

    slice_variant_df.to_csv(per_slice_path, index=False)
    micro_summary_df.to_csv(per_policy_path, index=False)

    summary_payload = {
        "phase": "phase_2_6_relative_strength_micro_confirmation",
        "status": "completed",
        "generated_at": _now_iso(),
        "candidate_under_confirmation": "top_25pct_return_20d",
        "source_files": {
            "stock_indicator_master_file": str(stock_indicator_master_file),
            "ihsg_indicator_master_file": str(ihsg_indicator_master_file),
            "phase_2_5_summary_file": str(phase_2_5_summary_file),
            "baseline_config": str(baseline_source) if baseline_source else None,
            "metadata_file": str(metadata_file) if metadata_file is not None else None,
        },
        "prior_status_context": {
            "phase_2_5_selected_variant_id": phase_2_5_summary.get("selection_decision", {}).get("selected_variant_id"),
            "phase_2_5_freeze_layer_2_candidate": phase_2_5_summary.get("freeze_decision", {}).get("freeze_layer_2_candidate"),
            "phase_2_5_remaining_blocker": phase_2_5_summary.get("freeze_decision", {}).get("remaining_blocker"),
        },
        "micro_refinements_tested": [
            {
                "variant_id": variant.variant_id,
                "variant_label": variant.label,
                "top_pct": variant.top_pct,
                "cut_rounding": variant.cut_rounding,
                "deterministic_tie_breaker": variant.deterministic_tie_breaker,
                "min_active_breadth_floor": variant.min_active_breadth_floor,
                "policy_family": variant.policy_family,
            }
            for variant in variants
        ],
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
        "micro_policy_summary": micro_summary_df.to_dict(orient="records"),
        "selection_decision": selection_decision,
        "freeze_decision": freeze_decision,
        "warnings": [*baseline_warnings, *metadata_warnings],
    }
    summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    report_lines = [
        "Phase 2.6 - Micro Confirmation / Final Freeze Decision",
        "======================================================",
        "",
        "Micro refinements tested:",
    ]
    for _, row in micro_summary_df.iterrows():
        report_lines.append(
            f"- {row['variant_id']}: full_trades={row['full_period_total_trades']}, "
            f"full_retention={row['full_period_median_trade_retention']}, "
            f"full_delta_win_rate={row['full_period_avg_delta_win_rate']}, "
            f"full_delta_avg_return={row['full_period_avg_delta_average_return']}, "
            f"sample={row['full_period_sample_adequacy_risk']}, "
            f"slice_wins={row['candidate_slice_win_count']}, "
            f"dispersion={row['candidate_avg_delta_average_return_range']}"
        )
    report_lines.extend(["", "Per-slice winners:"])
    for slice_id, group in slice_variant_df.groupby("slice_id"):
        winner = _pick_best_variant(
            group[
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
        ).get("selected_variant_id")
        report_lines.append(f"- {slice_id}: winner={winner}")
    report_lines.extend(
        [
            "",
            "Decision:",
            f"- selected_micro_policy = {selection_decision['selected_variant_id']}",
            f"- freeze_layer_2_candidate = {freeze_decision['freeze_layer_2_candidate']}",
            f"- lock_not_frozen_yet = {freeze_decision['lock_not_frozen_yet']}",
            f"- reason = {freeze_decision['reason']}",
        ]
    )
    if freeze_decision.get("remaining_blocker"):
        report_lines.append(f"- remaining_blocker = {freeze_decision['remaining_blocker']}")
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    return {
        "per_slice_path": per_slice_path,
        "per_policy_path": per_policy_path,
        "summary_path": summary_path,
        "report_path": report_path,
        "summary": summary_payload,
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase 2.6 micro confirmation for Layer 2.")
    parser.add_argument(
        "--stock-indicator-master-file",
        default="data/indicator_master/stock_indicator_master.csv",
        help="Stock indicator master CSV for the frozen 50-ticker universe.",
    )
    parser.add_argument(
        "--ihsg-indicator-master-file",
        default="data/indicator_master/IHSG_indicator_master.csv",
        help="IHSG indicator master CSV with frozen Layer 1 inputs.",
    )
    parser.add_argument(
        "--phase-2-5-summary-file",
        default="output/phase_2_5_relative_strength_boundary_refinement_summary.json",
        help="Phase 2.5 summary JSON used as source of truth.",
    )
    parser.add_argument("--output-dir", default="output", help="Directory for Phase 2.6 artifacts.")
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
    run_phase_2_6_relative_strength_micro_confirmation(
        stock_indicator_master_file=Path(args.stock_indicator_master_file),
        ihsg_indicator_master_file=Path(args.ihsg_indicator_master_file),
        phase_2_5_summary_file=Path(args.phase_2_5_summary_file),
        output_dir=Path(args.output_dir),
        hold_period=int(args.hold_period),
        allow_overlap=bool(args.allow_overlap),
        baseline_config=Path(args.baseline_config) if args.baseline_config else None,
        metadata_file=Path(args.metadata_file) if args.metadata_file else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
