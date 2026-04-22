"""Evaluate Layer 2 relative strength stock selection on top of frozen Layer 1."""

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

from quant.phase_a import backtest_signal_frame  # noqa: E402
from quant.phase_a_baseline import (  # noqa: E402
    load_optional_metadata_lookup,
    load_phase_a_baseline,
    resolve_phase_a_runtime_settings,
)
from quant.run_phase_1_1_market_regime_filter_refinement import (  # noqa: E402
    _build_base_signal_frame,
    _load_stock_indicator_master,
)
from quant.run_phase_1_2_market_regime_alignment_confirmation import (  # noqa: E402
    _apply_alignment_policy,
    _build_policy_registry,
    _compute_candidate_regime,
    _load_ihsg_indicator_master,
)


VARIANT_SUMMARY_COLUMNS = [
    "variant_id",
    "variant_label",
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
class SelectionVariant:
    variant_id: str
    label: str
    selection_mode: str
    top_pct: Optional[float]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_variant_registry() -> List[SelectionVariant]:
    return [
        SelectionVariant(
            variant_id="layer1_full_universe",
            label="Full universe after Layer 1",
            selection_mode="full_after_layer1",
            top_pct=None,
        ),
        SelectionVariant(
            variant_id="top_25pct_return_20d",
            label="Top 25% by return_20d",
            selection_mode="top_pct",
            top_pct=0.25,
        ),
        SelectionVariant(
            variant_id="top_30pct_return_20d",
            label="Top 30% by return_20d",
            selection_mode="top_pct",
            top_pct=0.30,
        ),
    ]


def _load_layer1_frozen_frame(
    stock_indicator_master_file: Path,
    ihsg_indicator_master_file: Path,
) -> pd.DataFrame:
    stock_frame = _load_stock_indicator_master(stock_indicator_master_file)
    ihsg_frame = _compute_candidate_regime(_load_ihsg_indicator_master(ihsg_indicator_master_file))
    policy = next(
        policy
        for policy in _build_policy_registry()
        if policy.policy_id == "explicit_previous_trading_day_alignment"
    )
    unique_stock_dates = stock_frame["date"].drop_duplicates().sort_values().reset_index(drop=True)
    daily_alignment = _apply_alignment_policy(unique_stock_dates, ihsg_frame, policy=policy)
    merged = stock_frame.merge(daily_alignment, on="date", how="left")
    merged["market_regime_bullish"] = merged["market_regime_bullish"].fillna(False).astype(bool)
    return merged.sort_values(["date", "ticker"]).reset_index(drop=True)


def _compute_relative_strength_features(frame: pd.DataFrame) -> pd.DataFrame:
    working = frame.sort_values(["date", "ticker"]).reset_index(drop=True).copy()
    working["rs_score"] = pd.to_numeric(working["return_20d"], errors="coerce")
    working["rankable_for_rs"] = working["rs_score"].notna()
    working["rankable_ticker_count"] = working.groupby("date")["rankable_for_rs"].transform("sum").astype(int)
    working["available_ticker_count"] = working.groupby("date")["ticker"].transform("count").astype(int)
    eligible = working["rankable_for_rs"]
    working["rs_rank"] = (
        working.loc[eligible]
        .groupby("date")["rs_score"]
        .rank(method="first", ascending=False)
    )
    working["rs_rank"] = working["rs_rank"].astype("Float64")
    return working


def _target_selected_count(rankable_count: int, top_pct: Optional[float]) -> int:
    if rankable_count <= 0:
        return 0
    if top_pct is None:
        return int(rankable_count)
    return max(1, int(math.ceil(rankable_count * float(top_pct))))


def _apply_selection_variant(frame: pd.DataFrame, variant: SelectionVariant) -> pd.DataFrame:
    working = frame.sort_values(["date", "ticker"]).reset_index(drop=True).copy()
    working["layer1_selected"] = working["market_regime_bullish"].astype(bool)
    if variant.selection_mode == "full_after_layer1":
        working["target_selected_count"] = working["available_ticker_count"].where(
            working["market_regime_bullish"],
            0,
        ).astype(int)
        working["rs_selected"] = working["market_regime_bullish"].astype(bool)
    else:
        per_date_target = (
            working[["date", "rankable_ticker_count"]]
            .drop_duplicates(subset=["date"], keep="last")
            .assign(
                target_selected_count=lambda df: df["rankable_ticker_count"].apply(
                    lambda value: _target_selected_count(int(value), variant.top_pct)
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
    return working


def _evaluate_variant_ticker(
    ticker: str,
    frame: pd.DataFrame,
    *,
    hold_period: int,
    allow_overlap: bool,
) -> Dict[str, object]:
    layer1_signal_count = int(frame["phase_1_signal_layer1"].fillna(False).astype(bool).sum())
    variant_signal_count = int(frame["phase_2_signal"].fillna(False).astype(bool).sum())
    skipped_signal_count = int(frame["phase_2_entry_skipped"].fillna(False).astype(bool).sum())

    layer1_result = backtest_signal_frame(
        frame,
        signal_column="phase_1_signal_layer1",
        hold_period=hold_period,
        allow_overlap=allow_overlap,
    )
    variant_result = backtest_signal_frame(
        frame,
        signal_column="phase_2_signal",
        hold_period=hold_period,
        allow_overlap=allow_overlap,
    )

    signal_retention_pct = (
        round((variant_signal_count / layer1_signal_count) * 100.0, 4) if layer1_signal_count else 0.0
    )
    trade_retention_pct = (
        round((variant_result.total_trades / layer1_result.total_trades) * 100.0, 4)
        if layer1_result.total_trades
        else 0.0
    )
    return {
        "ticker": ticker,
        "rows": int(len(frame)),
        "date_start": frame["date"].iloc[0].strftime("%Y-%m-%d"),
        "date_end": frame["date"].iloc[-1].strftime("%Y-%m-%d"),
        "applied_threshold": float(frame["applied_threshold"].iloc[0]),
        "applied_strict_mode": bool(frame["applied_strict_mode"].iloc[0]),
        "layer1_signals": layer1_signal_count,
        "variant_signals": variant_signal_count,
        "skipped_signals": skipped_signal_count,
        "signal_retention_pct": signal_retention_pct,
        "coverage_collapsed": bool(variant_signal_count == 0 and layer1_signal_count > 0),
        "layer1_total_trades": int(layer1_result.total_trades),
        "variant_total_trades": int(variant_result.total_trades),
        "trade_retention_pct": trade_retention_pct,
        "layer1_win_rate": float(layer1_result.win_rate),
        "variant_win_rate": float(variant_result.win_rate),
        "delta_win_rate": round(float(variant_result.win_rate) - float(layer1_result.win_rate), 4),
        "layer1_average_return": float(layer1_result.average_return),
        "variant_average_return": float(variant_result.average_return),
        "delta_average_return": round(
            float(variant_result.average_return) - float(layer1_result.average_return), 4
        ),
        "layer1_max_drawdown": float(layer1_result.max_drawdown),
        "variant_max_drawdown": float(variant_result.max_drawdown),
        "delta_max_drawdown": round(
            float(variant_result.max_drawdown) - float(layer1_result.max_drawdown), 4
        ),
    }


def _classify_sample_adequacy_risk(summary: Dict[str, object], universe_max: int) -> tuple[str, str]:
    median_active = float(summary["active_ticker_count_median"])
    single_day_pct = float(summary["active_single_ticker_day_pct"])
    total_trades = int(summary["total_trades"])
    collapse = int(summary["tickers_with_coverage_collapse"])

    if collapse > 0 or median_active <= 2.0 or single_day_pct >= 20.0 or total_trades < 300:
        return (
            "high",
            "Selection terlalu sempit untuk universe pilot saat ini atau trade sample turun terlalu jauh.",
        )
    if universe_max < 10 or median_active <= 3.0 or total_trades < 600:
        return (
            "moderate",
            "Prototype masih usable, tetapi universe pilot 7 ticker terlalu kecil untuk validasi final.",
        )
    return ("low", "Sample cukup untuk prototype dan tidak menunjukkan penyempitan berlebihan.")


def _summarize_variant(
    frame: pd.DataFrame,
    per_ticker_df: pd.DataFrame,
    variant: SelectionVariant,
) -> Dict[str, object]:
    active_by_date = (
        frame.groupby("date")
        .agg(
            active_ticker_count=("active_selected", "sum"),
            available_ticker_count=("available_ticker_count", "max"),
            rankable_ticker_count=("rankable_ticker_count", "max"),
            market_regime_bullish=("market_regime_bullish", "max"),
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
            "Selected the RS cut with the best balance between quality delta improvement and retained trade sample."
        ),
    }


def _layer2_usability_decision(variant_df: pd.DataFrame, best_variant: Dict[str, object]) -> Dict[str, object]:
    if not best_variant.get("selected_variant_id"):
        return {"layer_2_usable_as_prototype": False, "reason": "No RS candidate was selected."}

    selected = variant_df.loc[variant_df["variant_id"] == best_variant["selected_variant_id"]].iloc[0]
    usable = bool(
        int(selected["tickers_with_coverage_collapse"]) == 0
        and (
            float(selected["avg_delta_average_return"]) > 0.0
            or float(selected["avg_delta_win_rate"]) > 0.0
        )
    )
    reason = (
        "RS layer improves at least one quality metric without collapsing coverage, so it is usable as a prototype."
        if usable
        else "RS cuts do not improve quality enough without harming sample, so Layer 2 is not prototype-usable yet."
    )
    return {"layer_2_usable_as_prototype": usable, "reason": reason}


def run_phase_2_relative_strength_stock_selection(
    *,
    stock_indicator_master_file: Path,
    ihsg_indicator_master_file: Path,
    output_dir: Path,
    hold_period: int = 5,
    allow_overlap: bool = False,
    baseline_config: Optional[Path] = None,
    metadata_file: Optional[Path] = None,
) -> Dict[str, object]:
    layer1_frame = _load_layer1_frozen_frame(stock_indicator_master_file, ihsg_indicator_master_file)
    layer1_frame = _compute_relative_strength_features(layer1_frame)
    baseline_payload, baseline_warnings, baseline_source = load_phase_a_baseline(baseline_config=baseline_config)
    metadata_lookup, metadata_warnings = load_optional_metadata_lookup(metadata_file)
    variants = _build_variant_registry()

    enriched_frames: List[pd.DataFrame] = []
    per_ticker_rows: List[Dict[str, object]] = []
    variant_rows: List[Dict[str, object]] = []

    base_rows: List[pd.DataFrame] = []
    for ticker, group in layer1_frame.groupby("ticker"):
        runtime = resolve_phase_a_runtime_settings(
            ticker=ticker,
            baseline_config=baseline_payload,
            metadata_lookup=metadata_lookup,
        )
        prepared = _build_base_signal_frame(
            group.copy(),
            threshold=float(runtime["threshold"]),
            strict_mode=bool(runtime["strict_mode"]),
        )
        prepared["market_regime_bullish"] = prepared["market_regime_bullish"].fillna(False).astype(bool)
        prepared["phase_1_signal_layer1"] = (
            prepared["phase_1_signal_base"] & prepared["market_regime_bullish"]
        ).fillna(False)
        prepared["applied_threshold"] = float(runtime["threshold"])
        prepared["applied_strict_mode"] = bool(runtime["strict_mode"])
        base_rows.append(prepared)

    prepared_frame = pd.concat(base_rows, ignore_index=True).sort_values(["date", "ticker"]).reset_index(drop=True)

    for variant in variants:
        variant_frame = _apply_selection_variant(prepared_frame, variant)
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
        )
        .sort_values(["variant_id", "date"])
        .reset_index(drop=True)
    )

    best_variant = _pick_best_variant(variant_df)
    usability = _layer2_usability_decision(variant_df, best_variant)
    universe_small = {
        "universe_now_too_small_for_final_validation": True,
        "reason": (
            "Current pilot universe hanya 7 ticker, jadi bahkan jika cut RS berikutnya membaik "
            "hasilnya tetap belum cukup untuk validasi final."
        ),
        "max_rankable_tickers_on_any_date": int(active_by_date_df["rankable_ticker_count"].max()),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    per_ticker_path = output_dir / "phase_2_relative_strength_selection_per_ticker.csv"
    per_variant_path = output_dir / "phase_2_relative_strength_selection_per_variant.csv"
    per_date_path = output_dir / "phase_2_relative_strength_selection_active_universe_by_date.csv"
    summary_path = output_dir / "phase_2_relative_strength_selection_summary.json"
    report_path = output_dir / "phase_2_relative_strength_selection_report.txt"

    per_ticker_df.to_csv(per_ticker_path, index=False)
    variant_df.to_csv(per_variant_path, index=False)
    active_by_date_df.to_csv(per_date_path, index=False)

    summary_payload = {
        "phase": "phase_2_relative_strength_stock_selection",
        "status": "completed",
        "generated_at": _now_iso(),
        "layer_1_frozen_definition": {
            "market_regime": "ihsg_ema50 > ihsg_ema200",
            "alignment_policy": "explicit_previous_trading_day_alignment",
        },
        "source_files": {
            "stock_indicator_master_file": str(stock_indicator_master_file),
            "ihsg_indicator_master_file": str(ihsg_indicator_master_file),
            "baseline_config": str(baseline_source) if baseline_source else None,
            "metadata_file": str(metadata_file) if metadata_file is not None else None,
        },
        "selection_variants_tested": [
            {
                "variant_id": variant.variant_id,
                "variant_label": variant.label,
                "selection_mode": variant.selection_mode,
                "top_pct": variant.top_pct,
            }
            for variant in variants
        ],
        "variant_results": variant_df.to_dict(orient="records"),
        "best_variant_decision": best_variant,
        "layer_2_usability": usability,
        "universe_size_assessment": universe_small,
        "warnings": [*baseline_warnings, *metadata_warnings],
    }
    summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    report_lines = [
        "Phase 2 - Relative Strength Stock Selection",
        "===========================================",
        "",
        "Layer 1 frozen input:",
        "- regime = ihsg_ema50 > ihsg_ema200",
        "- alignment = explicit_previous_trading_day_alignment",
        "",
        "Selection variants:",
    ]
    for row in variant_df.to_dict(orient="records"):
        report_lines.extend(
            [
                f"- {row['variant_id']}: {row['variant_label']}",
                f"  active_ticker_count_median={row['active_ticker_count_median']}, active_ticker_count_min={row['active_ticker_count_min']}, active_ticker_count_max={row['active_ticker_count_max']}",
                f"  total_signals={row['total_signals']}, total_trades={row['total_trades']}, median_trade_retention={row['median_trade_retention']}",
                f"  avg_delta_win_rate={row['avg_delta_win_rate']}, avg_delta_average_return={row['avg_delta_average_return']}, coverage_collapse={row['tickers_with_coverage_collapse']}",
                f"  sample_adequacy_risk={row['sample_adequacy_risk']}: {row['sample_adequacy_reason']}",
            ]
        )

    report_lines.extend(
        [
            "",
            "Decision:",
            f"- best_variant = {best_variant.get('selected_variant_id')}",
            f"- layer_2_usable_as_prototype = {usability['layer_2_usable_as_prototype']}",
            f"- universe_now_too_small_for_final_validation = {universe_small['universe_now_too_small_for_final_validation']}",
        ]
    )
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
    parser = argparse.ArgumentParser(description="Run Phase 2 relative strength stock selection.")
    parser.add_argument(
        "--stock-indicator-master-file",
        default="data/indicator_master/stock_indicator_master.csv",
        help="Stock indicator master CSV for the rebuild path.",
    )
    parser.add_argument(
        "--ihsg-indicator-master-file",
        default="data/indicator_master/IHSG_indicator_master.csv",
        help="IHSG indicator master CSV with frozen Layer 1 regime inputs.",
    )
    parser.add_argument("--output-dir", default="output", help="Directory for Phase 2 artifacts.")
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
    run_phase_2_relative_strength_stock_selection(
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
