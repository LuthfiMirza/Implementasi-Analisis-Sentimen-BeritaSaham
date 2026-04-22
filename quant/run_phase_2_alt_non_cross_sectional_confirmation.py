"""Narrow confirmation pass for the first alternative Layer 2 filter."""

from __future__ import annotations

import argparse
import json
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
from quant.run_phase_2_1_relative_strength_redesign import _prepare_layer1_signal_frame  # noqa: E402
from quant.run_phase_2_4_relative_strength_robustness import (  # noqa: E402
    _build_robustness_diagnostics,
    _build_slice_registry,
)
from quant.run_phase_2_alt_non_cross_sectional_filter import (  # noqa: E402
    AltFilterVariant,
    _apply_variant,
    _compute_alt_features,
    _summarize_variant,
)
from quant.run_phase_2_relative_strength_stock_selection import (  # noqa: E402
    PER_TICKER_COLUMNS,
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
    "selection_mode",
    "liquidity_gate_enabled",
    "liquidity_threshold_value",
    "liquidity_threshold_label",
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_confirmation_variant_registry() -> List[AltFilterVariant]:
    return [
        AltFilterVariant(
            variant_id="alt_filter_no_liquidity_gate",
            label="Alt filter without liquidity gate",
            selection_mode="alt_filter",
            liquidity_gate_enabled=False,
            liquidity_threshold_value=None,
            liquidity_threshold_label="none",
        ),
        AltFilterVariant(
            variant_id="alt_filter_liquidity_gate_2_5b",
            label="Alt filter with liquidity gate >= 2.5B IDR",
            selection_mode="alt_filter",
            liquidity_gate_enabled=True,
            liquidity_threshold_value=2_500_000_000.0,
            liquidity_threshold_label=">= 2.5B IDR",
        ),
        AltFilterVariant(
            variant_id="alt_filter_liquidity_gate_5b",
            label="Alt filter with liquidity gate >= 5B IDR",
            selection_mode="alt_filter",
            liquidity_gate_enabled=True,
            liquidity_threshold_value=5_000_000_000.0,
            liquidity_threshold_label=">= 5B IDR",
        ),
    ]


def _summarize_variant_for_slice(
    frame: pd.DataFrame,
    per_ticker_df: pd.DataFrame,
    variant: AltFilterVariant,
    slice_id: str,
    slice_label: str,
    slice_group: str,
) -> Dict[str, object]:
    summary = _summarize_variant(frame, per_ticker_df, variant)
    summary.update(
        {
            "slice_id": slice_id,
            "slice_label": slice_label,
            "slice_group": slice_group,
            "date_start": frame["date"].min().strftime("%Y-%m-%d"),
            "date_end": frame["date"].max().strftime("%Y-%m-%d"),
            "slice_date_count": int(frame["date"].nunique()),
        }
    )
    return summary


def _pick_slice_winner(slice_df: pd.DataFrame) -> Optional[str]:
    if slice_df.empty:
        return None
    eligible = slice_df[slice_df["tickers_with_coverage_collapse"] == 0].copy()
    if eligible.empty:
        eligible = slice_df.copy()
    eligible = eligible.sort_values(
        by=[
            "avg_delta_average_return",
            "avg_delta_win_rate",
            "median_trade_retention",
            "total_trades",
        ],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)
    return str(eligible.iloc[0]["variant_id"])


def _build_confirmation_summary(slice_variant_df: pd.DataFrame) -> pd.DataFrame:
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
                "liquidity_gate_enabled": bool(full_row["liquidity_gate_enabled"]),
                "liquidity_threshold_value": full_row["liquidity_threshold_value"],
                "liquidity_threshold_label": str(full_row["liquidity_threshold_label"]),
                "full_period_total_trades": int(full_row["total_trades"]),
                "full_period_median_trade_retention": round(float(full_row["median_trade_retention"]), 4),
                "full_period_avg_delta_win_rate": round(float(full_row["avg_delta_win_rate"]), 4),
                "full_period_avg_delta_average_return": round(float(full_row["avg_delta_average_return"]), 4),
                "full_period_tickers_with_coverage_collapse": int(full_row["tickers_with_coverage_collapse"]),
                "full_period_sample_adequacy_risk": str(full_row["sample_adequacy_risk"]),
                "candidate_slice_win_count": int(diagnostics.get("candidate_slice_win_count", 0)),
                "slice_count_excluding_full": int(diagnostics.get("slice_count_excluding_full", 0)),
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
    return pd.DataFrame(rows)


def _pick_best_variant(confirmation_df: pd.DataFrame) -> Dict[str, object]:
    if confirmation_df.empty:
        return {"status": "no_candidate", "selected_variant_id": None}
    eligible = confirmation_df[
        confirmation_df["full_period_tickers_with_coverage_collapse"].eq(0)
        & confirmation_df["full_period_sample_adequacy_risk"].eq("low")
    ].copy()
    if eligible.empty:
        eligible = confirmation_df.copy()
    eligible = eligible.sort_values(
        by=[
            "full_period_avg_delta_average_return",
            "full_period_avg_delta_win_rate",
            "candidate_slice_win_count",
            "full_period_median_trade_retention",
            "full_period_total_trades",
        ],
        ascending=[False, False, False, False, False],
    ).reset_index(drop=True)
    best = eligible.iloc[0]
    return {
        "status": "selected",
        "selected_variant_id": str(best["variant_id"]),
        "selected_variant_label": str(best["variant_label"]),
        "reason": (
            "Selected the narrow confirmation policy with the strongest full-period quality while keeping slice robustness acceptable."
        ),
    }


def _freeze_decision(confirmation_df: pd.DataFrame, candidate_variant_id: str) -> Dict[str, object]:
    candidate = confirmation_df[confirmation_df["variant_id"] == candidate_variant_id]
    if candidate.empty:
        return {
            "freeze_layer_2_alternative_candidate": False,
            "candidate_variant_id": candidate_variant_id,
            "reason": "Candidate row is missing from the confirmation summary.",
            "remaining_blocker": "candidate_missing_from_alt_confirmation_summary",
        }

    row = candidate.iloc[0]
    slice_count = int(row["slice_count_excluding_full"])
    win_count = int(row["candidate_slice_win_count"])
    robust_enough = bool(
        int(row["full_period_tickers_with_coverage_collapse"]) == 0
        and str(row["full_period_sample_adequacy_risk"]) == "low"
        and float(row["full_period_avg_delta_average_return"]) > 0.0
        and float(row["full_period_avg_delta_win_rate"]) >= 0.0
        and float(row["full_period_median_trade_retention"]) >= 75.0
        and win_count >= max(4, slice_count - 1)
        and int(row["candidate_negative_return_slice_count"]) <= 1
        and float(row["candidate_avg_delta_average_return_range"]) <= 0.30
    )
    if robust_enough:
        return {
            "freeze_layer_2_alternative_candidate": True,
            "candidate_variant_id": candidate_variant_id,
            "reason": (
                "Alternative Layer 2 candidate stays quality-positive, wins most slices, and keeps narrow enough slice dispersion to freeze."
            ),
            "remaining_blocker": None,
            "confirmation_diagnostics": row.to_dict(),
        }

    if win_count < max(4, slice_count - 1):
        blocker = "alt_candidate_advantage_not_consistent_enough_across_time_and_regime_slices"
    elif float(row["candidate_avg_delta_average_return_range"]) > 0.30:
        blocker = "alt_candidate_slice_dispersion_still_too_wide_for_freeze"
    else:
        blocker = "alt_candidate_liquidity_policy_still_not_decisive_enough"
    return {
        "freeze_layer_2_alternative_candidate": False,
        "candidate_variant_id": candidate_variant_id,
        "reason": "Alternative Layer 2 candidate is still not robust enough to freeze after the narrow confirmation pass.",
        "remaining_blocker": blocker,
        "confirmation_diagnostics": row.to_dict(),
    }


def run_phase_2_alt_non_cross_sectional_confirmation(
    *,
    stock_indicator_master_file: Path,
    ihsg_indicator_master_file: Path,
    phase_2_alt_summary_file: Path,
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
    prepared_frame = _compute_alt_features(prepared_frame)
    variants = _build_confirmation_variant_registry()
    slices = _build_slice_registry(prepared_frame, ihsg_indicator_master_file)

    slice_rows: List[Dict[str, object]] = []
    for slice_def in slices:
        slice_frame = prepared_frame[prepared_frame["date"].isin(slice_def.dates)].copy()
        if slice_frame.empty:
            continue
        for variant in variants:
            variant_frame = _apply_variant(slice_frame, variant)
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
            slice_rows.append(
                _summarize_variant_for_slice(
                    variant_frame,
                    per_ticker_df,
                    variant,
                    slice_id=slice_def.slice_id,
                    slice_label=slice_def.label,
                    slice_group=slice_def.slice_group,
                )
            )

    slice_variant_df = pd.DataFrame(slice_rows).reindex(columns=SLICE_SUMMARY_COLUMNS)
    confirmation_df = _build_confirmation_summary(slice_variant_df)
    best_variant = _pick_best_variant(confirmation_df)
    freeze_decision = _freeze_decision(confirmation_df, candidate_variant_id=str(best_variant.get("selected_variant_id")))
    prior_summary = json.loads(phase_2_alt_summary_file.read_text(encoding="utf-8"))

    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "phase_2_alt_non_cross_sectional_confirmation_summary.json"
    report_path = output_dir / "phase_2_alt_non_cross_sectional_confirmation_report.txt"
    per_slice_path = output_dir / "phase_2_alt_non_cross_sectional_confirmation_per_slice.csv"
    per_policy_path = output_dir / "phase_2_alt_non_cross_sectional_confirmation_per_policy.csv"

    slice_variant_df.to_csv(per_slice_path, index=False)
    confirmation_df.to_csv(per_policy_path, index=False)

    summary_payload = {
        "phase": "phase_2_alt_non_cross_sectional_confirmation",
        "status": "completed",
        "generated_at": _now_iso(),
        "source_files": {
            "stock_indicator_master_file": str(stock_indicator_master_file),
            "ihsg_indicator_master_file": str(ihsg_indicator_master_file),
            "phase_2_alt_summary_file": str(phase_2_alt_summary_file),
            "baseline_config": str(baseline_source) if baseline_source else None,
            "metadata_file": str(metadata_file) if metadata_file is not None else None,
        },
        "prior_status_context": {
            "phase_2_alt_best_variant": prior_summary.get("best_variant_decision", {}).get("selected_variant_id"),
            "phase_2_alt_best_liquidity_gate": prior_summary.get("best_liquidity_gate_decision", {}).get("selected_variant_id"),
            "phase_2_alt_prototype_usable": prior_summary.get("usability_decision", {}).get("layer_2_alternative_usable_as_prototype"),
        },
        "variants_tested": [
            {
                "variant_id": variant.variant_id,
                "variant_label": variant.label,
                "liquidity_gate_enabled": variant.liquidity_gate_enabled,
                "liquidity_threshold_value": variant.liquidity_threshold_value,
                "liquidity_threshold_label": variant.liquidity_threshold_label,
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
        "policy_confirmation_summary": confirmation_df.to_dict(orient="records"),
        "best_variant_decision": best_variant,
        "freeze_decision": freeze_decision,
        "warnings": [*baseline_warnings, *metadata_warnings],
    }
    summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    report_lines = [
        "Phase 2 Alternative - Narrow Confirmation",
        "=========================================",
        "",
        "Variants tested:",
    ]
    for _, row in confirmation_df.iterrows():
        report_lines.append(
            f"- {row['variant_id']}: threshold={row['liquidity_threshold_label']}, full_trades={row['full_period_total_trades']}, "
            f"full_retention={row['full_period_median_trade_retention']}, full_delta_win_rate={row['full_period_avg_delta_win_rate']}, "
            f"full_delta_avg_return={row['full_period_avg_delta_average_return']}, sample={row['full_period_sample_adequacy_risk']}, "
            f"slice_wins={row['candidate_slice_win_count']}, dispersion={row['candidate_avg_delta_average_return_range']}"
        )
    report_lines.extend(["", "Per-slice winners:"])
    for slice_id, group in slice_variant_df.groupby("slice_id"):
        report_lines.append(f"- {slice_id}: winner={_pick_slice_winner(group)}")
    report_lines.extend(
        [
            "",
            "Decision:",
            f"- best_variant = {best_variant.get('selected_variant_id')}",
            f"- freeze_layer_2_alternative_candidate = {freeze_decision['freeze_layer_2_alternative_candidate']}",
            f"- reason = {freeze_decision['reason']}",
        ]
    )
    if freeze_decision.get("remaining_blocker"):
        report_lines.append(f"- remaining_blocker = {freeze_decision['remaining_blocker']}")
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    return {
        "summary_path": summary_path,
        "report_path": report_path,
        "per_slice_path": per_slice_path,
        "per_policy_path": per_policy_path,
        "summary": summary_payload,
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run narrow confirmation for the alternative Layer 2 filter.")
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
        "--phase-2-alt-summary-file",
        default="output/phase_2_alt_non_cross_sectional_filter_summary.json",
        help="Prior alternative Layer 2 summary used as source of truth.",
    )
    parser.add_argument("--output-dir", default="output", help="Directory for output artifacts.")
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
    run_phase_2_alt_non_cross_sectional_confirmation(
        stock_indicator_master_file=Path(args.stock_indicator_master_file),
        ihsg_indicator_master_file=Path(args.ihsg_indicator_master_file),
        phase_2_alt_summary_file=Path(args.phase_2_alt_summary_file),
        output_dir=Path(args.output_dir),
        hold_period=int(args.hold_period),
        allow_overlap=bool(args.allow_overlap),
        baseline_config=Path(args.baseline_config) if args.baseline_config else None,
        metadata_file=Path(args.metadata_file) if args.metadata_file else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
