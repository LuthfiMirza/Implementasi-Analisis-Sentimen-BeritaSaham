"""Evaluate a non-cross-sectional Layer 2 alternative on top of frozen Layer 1."""

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
from quant.run_phase_2_1_relative_strength_redesign import _prepare_layer1_signal_frame  # noqa: E402
from quant.run_phase_2_relative_strength_stock_selection import (  # noqa: E402
    PER_TICKER_COLUMNS,
    _classify_sample_adequacy_risk,
    _evaluate_variant_ticker,
)


VARIANT_SUMMARY_COLUMNS = [
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


@dataclass(frozen=True)
class AltFilterVariant:
    variant_id: str
    label: str
    selection_mode: str
    liquidity_gate_enabled: bool
    liquidity_threshold_value: Optional[float]
    liquidity_threshold_label: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_variant_registry() -> List[AltFilterVariant]:
    return [
        AltFilterVariant(
            variant_id="layer1_full_universe",
            label="Full universe after Layer 1",
            selection_mode="full_after_layer1",
            liquidity_gate_enabled=False,
            liquidity_threshold_value=None,
            liquidity_threshold_label="none",
        ),
        AltFilterVariant(
            variant_id="alt_filter_no_liquidity_gate",
            label="Alt filter without liquidity gate",
            selection_mode="alt_filter",
            liquidity_gate_enabled=False,
            liquidity_threshold_value=None,
            liquidity_threshold_label="none",
        ),
        AltFilterVariant(
            variant_id="alt_filter_liquidity_gate_5b",
            label="Alt filter with liquidity gate >= 5B IDR",
            selection_mode="alt_filter",
            liquidity_gate_enabled=True,
            liquidity_threshold_value=5_000_000_000.0,
            liquidity_threshold_label=">= 5B IDR",
        ),
        AltFilterVariant(
            variant_id="alt_filter_liquidity_gate_10b",
            label="Alt filter with liquidity gate >= 10B IDR",
            selection_mode="alt_filter",
            liquidity_gate_enabled=True,
            liquidity_threshold_value=10_000_000_000.0,
            liquidity_threshold_label=">= 10B IDR",
        ),
        AltFilterVariant(
            variant_id="alt_filter_liquidity_gate_25b",
            label="Alt filter with liquidity gate >= 25B IDR",
            selection_mode="alt_filter",
            liquidity_gate_enabled=True,
            liquidity_threshold_value=25_000_000_000.0,
            liquidity_threshold_label=">= 25B IDR",
        ),
    ]


def _compute_alt_features(frame: pd.DataFrame) -> pd.DataFrame:
    working = frame.sort_values(["date", "ticker"]).reset_index(drop=True).copy()
    working["return_20d_numeric"] = pd.to_numeric(working["return_20d"], errors="coerce")
    working["close_numeric"] = pd.to_numeric(working["close"], errors="coerce")
    working["ema50_numeric"] = pd.to_numeric(working["ema50"], errors="coerce")
    working["volume_ma20_numeric"] = pd.to_numeric(working["volume_ma20"], errors="coerce")
    working["avg_traded_value_20d"] = working["close_numeric"] * working["volume_ma20_numeric"]
    working["alt_data_ready"] = (
        working["return_20d_numeric"].notna()
        & working["close_numeric"].notna()
        & working["ema50_numeric"].notna()
    )
    working["alt_momentum_positive"] = working["return_20d_numeric"].gt(0)
    working["alt_close_above_ema50"] = working["close_numeric"].gt(working["ema50_numeric"])
    working["available_ticker_count"] = working.groupby("date")["ticker"].transform("count").astype(int)
    return working


def _apply_variant(frame: pd.DataFrame, variant: AltFilterVariant) -> pd.DataFrame:
    working = frame.sort_values(["date", "ticker"]).reset_index(drop=True).copy()
    working["layer1_selected"] = working["market_regime_bullish"].astype(bool)

    if variant.selection_mode == "full_after_layer1":
        working["liquidity_gate_pass"] = True
        working["alt_eligible_pre_liquidity"] = working["market_regime_bullish"].astype(bool)
        working["active_selected"] = working["market_regime_bullish"].astype(bool)
    elif variant.selection_mode == "alt_filter":
        working["alt_eligible_pre_liquidity"] = (
            working["market_regime_bullish"].astype(bool)
            & working["alt_data_ready"].astype(bool)
            & working["alt_momentum_positive"].astype(bool)
            & working["alt_close_above_ema50"].astype(bool)
        )
        if variant.liquidity_gate_enabled:
            threshold = float(variant.liquidity_threshold_value or 0.0)
            working["liquidity_gate_pass"] = (
                working["avg_traded_value_20d"].notna()
                & working["avg_traded_value_20d"].ge(threshold)
            )
        else:
            working["liquidity_gate_pass"] = True
        working["active_selected"] = (
            working["alt_eligible_pre_liquidity"].astype(bool)
            & working["liquidity_gate_pass"].astype(bool)
        )
    else:  # pragma: no cover - defensive
        raise ValueError(f"Unsupported selection mode: {variant.selection_mode}")

    working["rankable_ticker_count"] = (
        working.groupby("date")["alt_eligible_pre_liquidity"].transform("sum").fillna(0).astype(int)
    )
    working["target_selected_count"] = (
        working.groupby("date")["active_selected"].transform("sum").fillna(0).astype(int)
    )
    working["phase_2_signal"] = (working["phase_1_signal_layer1"] & working["active_selected"]).fillna(False)
    working["phase_2_entry_skipped"] = (
        working["phase_1_signal_layer1"] & ~working["active_selected"]
    ).fillna(False)
    return working


def _summarize_variant(
    frame: pd.DataFrame,
    per_ticker_df: pd.DataFrame,
    variant: AltFilterVariant,
) -> Dict[str, object]:
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
        "selection_mode": variant.selection_mode,
        "liquidity_gate_enabled": bool(variant.liquidity_gate_enabled),
        "liquidity_threshold_value": (
            float(variant.liquidity_threshold_value) if variant.liquidity_threshold_value is not None else None
        ),
        "liquidity_threshold_label": variant.liquidity_threshold_label,
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
    candidates = variant_df[variant_df["variant_id"] != "layer1_full_universe"].copy()
    if candidates.empty:
        return {"status": "no_candidate", "selected_variant_id": None}

    eligible = candidates[candidates["tickers_with_coverage_collapse"] == 0].copy()
    if eligible.empty:
        eligible = candidates.copy()
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
        "reason": (
            "Selected the alternative Layer 2 filter that best improves quality while keeping retained sample usable."
        ),
    }


def _pick_best_liquidity_gate_variant(variant_df: pd.DataFrame) -> Dict[str, object]:
    candidates = variant_df[
        variant_df["liquidity_gate_enabled"].astype(bool)
        & variant_df["variant_id"].ne("layer1_full_universe")
    ].copy()
    if candidates.empty:
        return {"status": "no_candidate", "selected_variant_id": None}

    eligible = candidates[candidates["tickers_with_coverage_collapse"] == 0].copy()
    if eligible.empty:
        eligible = candidates.copy()
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
        "selected_threshold_label": str(best["liquidity_threshold_label"]),
        "reason": "Selected the most defensible explicit liquidity threshold among the tested gates.",
    }


def _usability_decision(variant_df: pd.DataFrame, best_variant: Dict[str, object]) -> Dict[str, object]:
    if not best_variant.get("selected_variant_id"):
        return {"layer_2_alternative_usable_as_prototype": False, "reason": "No alternative Layer 2 variant was selected."}

    selected = variant_df.loc[variant_df["variant_id"] == best_variant["selected_variant_id"]].iloc[0]
    usable = bool(
        int(selected["tickers_with_coverage_collapse"]) == 0
        and str(selected["sample_adequacy_risk"]) != "high"
        and (
            float(selected["avg_delta_average_return"]) > 0.0
            or float(selected["avg_delta_win_rate"]) > 0.0
        )
    )
    reason = (
        "Alternative Layer 2 improves at least one quality metric without collapsing coverage, so it is prototype-usable."
        if usable
        else "Alternative Layer 2 still does not improve quality enough without harming sample, so it is not prototype-usable yet."
    )
    return {"layer_2_alternative_usable_as_prototype": usable, "reason": reason}


def _stability_assessment(variant_df: pd.DataFrame) -> Dict[str, object]:
    candidates = variant_df[variant_df["variant_id"] != "layer1_full_universe"].copy()
    if candidates.empty:
        return {"appears_more_stable_than_closed_rs_track": False, "reason": "No alternative variants were evaluated."}

    collapse_free = bool(candidates["tickers_with_coverage_collapse"].eq(0).all())
    sample_ok = bool(candidates["sample_adequacy_risk"].ne("high").all())
    delta_return_range = round(
        float(candidates["avg_delta_average_return"].max() - candidates["avg_delta_average_return"].min()),
        4,
    )
    trade_retention_range = round(
        float(candidates["median_trade_retention"].max() - candidates["median_trade_retention"].min()),
        4,
    )
    more_stable = bool(collapse_free and sample_ok and delta_return_range <= 0.25)
    reason = (
        "Alternative Layer 2 looks more stable than the closed RS track because explicit threshold variants keep coverage intact and show narrower quality dispersion in the first pass."
        if more_stable
        else "Alternative Layer 2 has not yet shown clearly narrower first-pass sensitivity than the closed RS track."
    )
    return {
        "appears_more_stable_than_closed_rs_track": more_stable,
        "reason": reason,
        "avg_delta_average_return_range": delta_return_range,
        "median_trade_retention_range": trade_retention_range,
        "all_variants_collapse_free": collapse_free,
        "all_variants_sample_not_high": sample_ok,
    }


def run_phase_2_alt_non_cross_sectional_filter(
    *,
    stock_indicator_master_file: Path,
    ihsg_indicator_master_file: Path,
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
    variants = _build_variant_registry()

    enriched_frames: List[pd.DataFrame] = []
    per_ticker_rows: List[Dict[str, object]] = []
    variant_rows: List[Dict[str, object]] = []

    for variant in variants:
        variant_frame = _apply_variant(prepared_frame, variant)
        variant_frame["variant_id"] = variant.variant_id
        variant_frame["variant_label"] = variant.label
        enriched_frames.append(variant_frame)

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
        pd.concat(enriched_frames, ignore_index=True)
        .groupby(["variant_id", "variant_label", "date"], as_index=False)
        .agg(
            market_regime_bullish=("market_regime_bullish", "max"),
            available_ticker_count=("available_ticker_count", "max"),
            rankable_ticker_count=("rankable_ticker_count", "max"),
            target_selected_count=("target_selected_count", "max"),
            active_ticker_count=("active_selected", "sum"),
            avg_traded_value_20d_median=("avg_traded_value_20d", "median"),
        )
        .sort_values(["variant_id", "date"])
        .reset_index(drop=True)
    )

    best_variant = _pick_best_variant(variant_df)
    best_liquidity_gate = _pick_best_liquidity_gate_variant(variant_df)
    usability = _usability_decision(variant_df, best_variant)
    stability = _stability_assessment(variant_df)

    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "phase_2_alt_non_cross_sectional_filter_summary.json"
    report_path = output_dir / "phase_2_alt_non_cross_sectional_filter_report.txt"
    per_ticker_path = output_dir / "phase_2_alt_non_cross_sectional_filter_per_ticker.csv"
    active_by_date_path = output_dir / "phase_2_alt_non_cross_sectional_filter_active_by_date.csv"

    per_ticker_df.to_csv(per_ticker_path, index=False)
    active_by_date_df.to_csv(active_by_date_path, index=False)

    summary_payload = {
        "phase": "phase_2_alt_non_cross_sectional_filter",
        "status": "completed",
        "generated_at": _now_iso(),
        "source_files": {
            "stock_indicator_master_file": str(stock_indicator_master_file),
            "ihsg_indicator_master_file": str(ihsg_indicator_master_file),
            "baseline_config": str(baseline_source) if baseline_source else None,
            "metadata_file": str(metadata_file) if metadata_file is not None else None,
        },
        "rule_definition": {
            "market_regime_bullish_required": True,
            "return_20d_positive_required": True,
            "close_above_ema50_required": True,
            "selection_style": "boolean_eligibility_filter",
            "liquidity_gate_formula": "close * volume_ma20 >= threshold",
            "tested_liquidity_thresholds": [5_000_000_000.0, 10_000_000_000.0, 25_000_000_000.0],
        },
        "variant_results": variant_df.to_dict(orient="records"),
        "best_variant_decision": best_variant,
        "best_liquidity_gate_decision": best_liquidity_gate,
        "usability_decision": usability,
        "stability_assessment": stability,
        "warnings": [*baseline_warnings, *metadata_warnings],
    }
    summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    report_lines = [
        "Phase 2 Alternative - Non-Cross-Sectional Filter",
        "================================================",
        "",
        "Rule:",
        "- Layer 1 bullish required",
        "- return_20d > 0",
        "- close > ema50",
        "- boolean eligibility filter, not top-x ranking",
        "- liquidity gate formula: close * volume_ma20 >= threshold",
        "",
        "Variant results:",
    ]
    for _, row in variant_df.iterrows():
        report_lines.append(
            f"- {row['variant_id']}: threshold={row['liquidity_threshold_label']}, signals={row['total_signals']}, "
            f"trades={row['total_trades']}, retention={row['median_trade_retention']}, "
            f"delta_win_rate={row['avg_delta_win_rate']}, delta_avg_return={row['avg_delta_average_return']}, "
            f"collapse={row['tickers_with_coverage_collapse']}, sample={row['sample_adequacy_risk']}"
        )
    report_lines.extend(
        [
            "",
            "Decisions:",
            f"- best_variant = {best_variant.get('selected_variant_id')}",
            f"- best_liquidity_gate_variant = {best_liquidity_gate.get('selected_variant_id')}",
            f"- layer_2_alternative_usable_as_prototype = {usability['layer_2_alternative_usable_as_prototype']}",
            f"- stability_vs_closed_rs = {stability['appears_more_stable_than_closed_rs_track']}",
            f"- stability_reason = {stability['reason']}",
        ]
    )
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    return {
        "summary_path": summary_path,
        "report_path": report_path,
        "per_ticker_path": per_ticker_path,
        "active_by_date_path": active_by_date_path,
        "summary": summary_payload,
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the first alternative Layer 2 experiment.")
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
    run_phase_2_alt_non_cross_sectional_filter(
        stock_indicator_master_file=Path(args.stock_indicator_master_file),
        ihsg_indicator_master_file=Path(args.ihsg_indicator_master_file),
        output_dir=Path(args.output_dir),
        hold_period=int(args.hold_period),
        allow_overlap=bool(args.allow_overlap),
        baseline_config=Path(args.baseline_config) if args.baseline_config else None,
        metadata_file=Path(args.metadata_file) if args.metadata_file else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
