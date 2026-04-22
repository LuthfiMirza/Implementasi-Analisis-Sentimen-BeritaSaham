"""Narrow confirmation pass for the Layer 2 relative strength prototype candidate."""

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
from quant.run_phase_2_1_relative_strength_redesign import (  # noqa: E402
    _apply_redesign_variant,
    _compute_redesign_scores,
    _prepare_layer1_signal_frame,
)
from quant.run_phase_2_relative_strength_stock_selection import (  # noqa: E402
    _classify_sample_adequacy_risk,
    _evaluate_variant_ticker,
)


VARIANT_SUMMARY_COLUMNS = [
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

PER_TICKER_COLUMNS = [
    "variant_id",
    "variant_label",
    "ticker",
    "rows",
    "date_start",
    "date_end",
    "applied_threshold",
    "applied_strict_mode",
    "layer1_signals",
    "variant_signals",
    "skipped_signals",
    "signal_retention_pct",
    "coverage_collapsed",
    "layer1_total_trades",
    "variant_total_trades",
    "trade_retention_pct",
    "layer1_win_rate",
    "variant_win_rate",
    "delta_win_rate",
    "layer1_average_return",
    "variant_average_return",
    "delta_average_return",
    "layer1_max_drawdown",
    "variant_max_drawdown",
    "delta_max_drawdown",
]


@dataclass(frozen=True)
class ConfirmationVariant:
    variant_id: str
    label: str
    score_column: str
    selection_mode: str
    top_pct: Optional[float]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_variant_registry() -> List[ConfirmationVariant]:
    return [
        ConfirmationVariant(
            variant_id="top_25pct_return_20d",
            label="Top 25% by return_20d",
            score_column="rs_score_return_20d",
            selection_mode="top_pct",
            top_pct=0.25,
        ),
        ConfirmationVariant(
            variant_id="top_30pct_return_20d",
            label="Top 30% by return_20d",
            score_column="rs_score_return_20d",
            selection_mode="top_pct",
            top_pct=0.30,
        ),
        ConfirmationVariant(
            variant_id="top_25pct_vol_adjusted_return_20d",
            label="Top 25% by return_20d / vol20",
            score_column="rs_score_vol_adjusted_return_20d",
            selection_mode="top_pct",
            top_pct=0.25,
        ),
    ]


def _summarize_variant(frame: pd.DataFrame, per_ticker_df: pd.DataFrame, variant: ConfirmationVariant) -> Dict[str, object]:
    active_by_date = (
        frame.groupby("date")
        .agg(
            active_ticker_count=("active_selected", "sum"),
            available_ticker_count=("available_ticker_count", "max"),
            rankable_ticker_count=("rankable_ticker_count", "max"),
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


def _pick_best_variant(variant_df: pd.DataFrame) -> Dict[str, object]:
    if variant_df.empty:
        return {"status": "no_candidate", "selected_variant_id": None}

    eligible = variant_df[variant_df["tickers_with_coverage_collapse"] == 0].copy()
    if eligible.empty:
        eligible = variant_df.copy()
    eligible = eligible.sort_values(
        by=[
            "avg_delta_average_return",
            "avg_delta_win_rate",
            "median_trade_retention",
            "total_trades",
        ],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)
    best = eligible.iloc[0]
    return {
        "status": "selected",
        "selected_variant_id": str(best["variant_id"]),
        "selected_variant_label": str(best["variant_label"]),
        "reason": "Selected the narrow confirmation variant with the strongest quality delta while keeping retained sample acceptable.",
    }


def _build_stability_diagnostics(variant_df: pd.DataFrame, candidate_variant_id: str) -> Dict[str, object]:
    if variant_df.empty:
        return {"status": "no_data"}
    candidate = variant_df.loc[variant_df["variant_id"] == candidate_variant_id]
    if candidate.empty:
        return {"status": "candidate_missing"}
    candidate_row = candidate.iloc[0]
    comparator_rows = []
    for _, row in variant_df[variant_df["variant_id"] != candidate_variant_id].iterrows():
        comparator_rows.append(
            {
                "against_variant_id": str(row["variant_id"]),
                "delta_total_trades_vs_candidate": int(row["total_trades"] - candidate_row["total_trades"]),
                "delta_trade_retention_vs_candidate": round(
                    float(row["median_trade_retention"]) - float(candidate_row["median_trade_retention"]),
                    4,
                ),
                "delta_avg_delta_win_rate_vs_candidate": round(
                    float(row["avg_delta_win_rate"]) - float(candidate_row["avg_delta_win_rate"]),
                    4,
                ),
                "delta_avg_delta_average_return_vs_candidate": round(
                    float(row["avg_delta_average_return"]) - float(candidate_row["avg_delta_average_return"]),
                    4,
                ),
            }
        )
    return {
        "candidate_variant_id": candidate_variant_id,
        "avg_delta_win_rate_range": round(
            float(variant_df["avg_delta_win_rate"].max() - variant_df["avg_delta_win_rate"].min()),
            4,
        ),
        "avg_delta_average_return_range": round(
            float(variant_df["avg_delta_average_return"].max() - variant_df["avg_delta_average_return"].min()),
            4,
        ),
        "median_trade_retention_range": round(
            float(variant_df["median_trade_retention"].max() - variant_df["median_trade_retention"].min()),
            4,
        ),
        "total_trades_range": int(variant_df["total_trades"].max() - variant_df["total_trades"].min()),
        "candidate_comparator_deltas": comparator_rows,
    }


def _freeze_decision(variant_df: pd.DataFrame, best_variant: Dict[str, object], stability: Dict[str, object]) -> Dict[str, object]:
    candidate_id = "top_25pct_return_20d"
    candidate = variant_df.loc[variant_df["variant_id"] == candidate_id]
    if candidate.empty:
        return {
            "freeze_layer_2_candidate": False,
            "candidate_variant_id": candidate_id,
            "status": "candidate_missing",
            "reason": "Candidate top_25pct_return_20d is missing from the confirmation pass.",
            "remaining_blocker": "candidate_missing_from_confirmation_results",
        }

    row = candidate.iloc[0]
    candidate_is_best = best_variant.get("selected_variant_id") == candidate_id
    sensitivity_ok = bool(
        float(stability.get("avg_delta_average_return_range", 999.0)) <= 0.35
        and float(stability.get("avg_delta_win_rate_range", 999.0)) <= 1.0
    )
    freeze_ok = bool(
        candidate_is_best
        and int(row["tickers_with_coverage_collapse"]) == 0
        and str(row["sample_adequacy_risk"]) == "low"
        and float(row["avg_delta_average_return"]) > 0.0
        and float(row["median_trade_retention"]) >= 50.0
        and float(row["avg_delta_win_rate"]) >= -1.0
        and sensitivity_ok
    )
    if freeze_ok:
        reason = (
            "top_25pct_return_20d remains the best nearby variant, keeps sample adequacy low, preserves around half the trades, "
            "and still improves average-return quality without coverage collapse. Nearby comparators do not overturn the choice."
        )
        blocker = None
    else:
        reason = (
            "Candidate is still too sensitive to nearby variants or the quality trade-off is not yet strong enough "
            "to freeze Layer 2 as a final candidate."
        )
        blocker = "narrow_sensitivity_between_nearby_rs_cuts_and_quality_tradeoff_not_decisive_enough"
    return {
        "freeze_layer_2_candidate": freeze_ok,
        "candidate_variant_id": candidate_id,
        "candidate_still_best": candidate_is_best,
        "sensitivity_ok": sensitivity_ok,
        "reason": reason,
        "remaining_blocker": blocker,
    }


def run_phase_2_3_relative_strength_confirmation(
    *,
    stock_indicator_master_file: Path,
    ihsg_indicator_master_file: Path,
    phase_2_summary_file: Path,
    phase_2_1_summary_file: Path,
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

    per_ticker_rows: List[Dict[str, object]] = []
    variant_rows: List[Dict[str, object]] = []
    active_frames: List[pd.DataFrame] = []

    for variant in variants:
        variant_frame = _apply_redesign_variant(redesign_frame, variant)
        variant_frame["variant_id"] = variant.variant_id
        variant_frame["variant_label"] = variant.label
        active_frames.append(variant_frame)

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
        per_ticker_df = pd.DataFrame(ticker_rows).reindex(columns=PER_TICKER_COLUMNS)
        per_ticker_rows.extend(per_ticker_df.to_dict(orient="records"))
        variant_rows.append(_summarize_variant(variant_frame, per_ticker_df, variant))

    variant_df = pd.DataFrame(variant_rows).reindex(columns=VARIANT_SUMMARY_COLUMNS)
    per_ticker_df = pd.DataFrame(per_ticker_rows).reindex(columns=PER_TICKER_COLUMNS)
    active_by_date_df = (
        pd.concat([frame.drop(columns=["median_score"], errors="ignore") for frame in active_frames], ignore_index=True)
        .groupby(["variant_id", "variant_label", "date"], as_index=False)
        .agg(
            available_ticker_count=("available_ticker_count", "max"),
            rankable_ticker_count=("rankable_ticker_count", "max"),
            target_selected_count=("target_selected_count", "max"),
            active_ticker_count=("active_selected", "sum"),
        )
        .sort_values(["variant_id", "date"])
        .reset_index(drop=True)
    )

    best_variant = _pick_best_variant(variant_df)
    stability = _build_stability_diagnostics(variant_df, candidate_variant_id="top_25pct_return_20d")
    freeze_decision = _freeze_decision(variant_df, best_variant, stability)

    phase_2_summary = json.loads(phase_2_summary_file.read_text(encoding="utf-8"))
    phase_2_1_summary = json.loads(phase_2_1_summary_file.read_text(encoding="utf-8"))

    output_dir.mkdir(parents=True, exist_ok=True)
    per_ticker_path = output_dir / "phase_2_3_relative_strength_confirmation_per_ticker.csv"
    per_variant_path = output_dir / "phase_2_3_relative_strength_confirmation_per_variant.csv"
    per_date_path = output_dir / "phase_2_3_relative_strength_confirmation_active_universe_by_date.csv"
    summary_path = output_dir / "phase_2_3_relative_strength_confirmation_summary.json"
    report_path = output_dir / "phase_2_3_relative_strength_confirmation_report.txt"

    per_ticker_df.to_csv(per_ticker_path, index=False)
    variant_df.to_csv(per_variant_path, index=False)
    active_by_date_df.to_csv(per_date_path, index=False)

    summary_payload = {
        "phase": "phase_2_3_relative_strength_confirmation",
        "status": "completed",
        "generated_at": _now_iso(),
        "candidate_under_confirmation": "top_25pct_return_20d",
        "source_files": {
            "stock_indicator_master_file": str(stock_indicator_master_file),
            "ihsg_indicator_master_file": str(ihsg_indicator_master_file),
            "phase_2_summary_file": str(phase_2_summary_file),
            "phase_2_1_summary_file": str(phase_2_1_summary_file),
            "baseline_config": str(baseline_source) if baseline_source else None,
            "metadata_file": str(metadata_file) if metadata_file is not None else None,
        },
        "layer_1_frozen_definition": {
            "market_regime": "ihsg_ema50 > ihsg_ema200",
            "alignment_policy": "explicit_previous_trading_day_alignment",
        },
        "prior_status_context": {
            "phase_2_best_variant": phase_2_summary.get("best_variant_decision", {}).get("selected_variant_id"),
            "phase_2_layer_2_usable_as_prototype": phase_2_summary.get("layer_2_usability", {}).get(
                "layer_2_usable_as_prototype"
            ),
            "phase_2_1_formal_decision": phase_2_1_summary.get("formal_decision", {}).get("decision_code"),
            "phase_2_1_layer_2_usable_now": phase_2_1_summary.get("layer_2_usability", {}).get("layer_2_usable_now"),
        },
        "variants_tested": [
            {
                "variant_id": variant.variant_id,
                "variant_label": variant.label,
                "score_column": variant.score_column,
                "selection_mode": variant.selection_mode,
                "top_pct": variant.top_pct,
            }
            for variant in variants
        ],
        "variant_results": variant_df.to_dict(orient="records"),
        "best_variant_decision": best_variant,
        "stability_diagnostics": stability,
        "freeze_decision": freeze_decision,
        "warnings": [*baseline_warnings, *metadata_warnings],
    }
    summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    report_lines = [
        "Phase 2.3 - Narrow Confirmation for Layer 2 Candidate",
        "=====================================================",
        "",
        "Candidate under confirmation:",
        "- top_25pct_return_20d",
        "",
        "Variants tested:",
    ]
    for row in variant_df.to_dict(orient="records"):
        report_lines.extend(
            [
                f"- {row['variant_id']}: {row['variant_label']}",
                f"  total_trades={row['total_trades']}, median_trade_retention={row['median_trade_retention']}, avg_delta_win_rate={row['avg_delta_win_rate']}, avg_delta_average_return={row['avg_delta_average_return']}",
                f"  active_ticker_count_median={row['active_ticker_count_median']}, sample_adequacy_risk={row['sample_adequacy_risk']}, coverage_collapse={row['tickers_with_coverage_collapse']}",
            ]
        )
    report_lines.extend(
        [
            "",
            "Stability diagnostics:",
            f"- avg_delta_win_rate_range = {stability.get('avg_delta_win_rate_range')}",
            f"- avg_delta_average_return_range = {stability.get('avg_delta_average_return_range')}",
            f"- median_trade_retention_range = {stability.get('median_trade_retention_range')}",
            f"- total_trades_range = {stability.get('total_trades_range')}",
            "",
            "Decision:",
            f"- best_variant = {best_variant.get('selected_variant_id')}",
            f"- freeze_layer_2_candidate = {freeze_decision['freeze_layer_2_candidate']}",
            f"- reason = {freeze_decision['reason']}",
        ]
    )
    if freeze_decision.get("remaining_blocker"):
        report_lines.append(f"- remaining_blocker = {freeze_decision['remaining_blocker']}")
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    return {
        "per_ticker_path": per_ticker_path,
        "per_variant_path": per_variant_path,
        "per_date_path": per_date_path,
        "summary_path": summary_path,
        "report_path": report_path,
        "summary": summary_payload,
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase 2.3 narrow confirmation for the Layer 2 candidate.")
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
        "--phase-2-summary-file",
        default="output/phase_2_relative_strength_selection_summary.json",
        help="Phase 2 summary JSON used as context.",
    )
    parser.add_argument(
        "--phase-2-1-summary-file",
        default="output/phase_2_1_relative_strength_redesign_summary.json",
        help="Phase 2.1 summary JSON used as context.",
    )
    parser.add_argument("--output-dir", default="output", help="Directory for Phase 2.3 artifacts.")
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
    run_phase_2_3_relative_strength_confirmation(
        stock_indicator_master_file=Path(args.stock_indicator_master_file),
        ihsg_indicator_master_file=Path(args.ihsg_indicator_master_file),
        phase_2_summary_file=Path(args.phase_2_summary_file),
        phase_2_1_summary_file=Path(args.phase_2_1_summary_file),
        output_dir=Path(args.output_dir),
        hold_period=int(args.hold_period),
        allow_overlap=bool(args.allow_overlap),
        baseline_config=Path(args.baseline_config) if args.baseline_config else None,
        metadata_file=Path(args.metadata_file) if args.metadata_file else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
