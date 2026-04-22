"""Evaluate broader Layer 2 relative strength redesign variants on top of frozen Layer 1."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

if __package__ is None or __package__ == "":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.phase_a_baseline import (  # noqa: E402
    load_optional_metadata_lookup,
    load_phase_a_baseline,
    resolve_phase_a_runtime_settings,
)
from quant.run_phase_1_1_market_regime_filter_refinement import _build_base_signal_frame  # noqa: E402
from quant.run_phase_2_relative_strength_stock_selection import (  # noqa: E402
    _classify_sample_adequacy_risk,
    _evaluate_variant_ticker,
    _load_layer1_frozen_frame,
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
class RedesignVariant:
    variant_id: str
    label: str
    score_column: str
    selection_mode: str
    top_pct: Optional[float]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_variant_registry() -> List[RedesignVariant]:
    return [
        RedesignVariant(
            variant_id="layer1_full_universe",
            label="Full universe after Layer 1",
            score_column="rs_score_return_20d",
            selection_mode="full_after_layer1",
            top_pct=None,
        ),
        RedesignVariant(
            variant_id="top_40pct_return_20d",
            label="Top 40% by return_20d",
            score_column="rs_score_return_20d",
            selection_mode="top_pct",
            top_pct=0.40,
        ),
        RedesignVariant(
            variant_id="top_50pct_return_20d",
            label="Top 50% by return_20d",
            score_column="rs_score_return_20d",
            selection_mode="top_pct",
            top_pct=0.50,
        ),
        RedesignVariant(
            variant_id="above_median_return_20d",
            label="Above-median return_20d",
            score_column="rs_score_return_20d",
            selection_mode="above_median",
            top_pct=None,
        ),
        RedesignVariant(
            variant_id="top_50pct_vol_adjusted_return_20d",
            label="Top 50% by return_20d / vol20",
            score_column="rs_score_vol_adjusted_return_20d",
            selection_mode="top_pct",
            top_pct=0.50,
        ),
    ]


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _prepare_layer1_signal_frame(
    stock_indicator_master_file: Path,
    ihsg_indicator_master_file: Path,
    *,
    baseline_payload: Dict[str, object],
    metadata_lookup: Dict[str, Dict[str, object]],
) -> pd.DataFrame:
    layer1_frame = _load_layer1_frozen_frame(stock_indicator_master_file, ihsg_indicator_master_file)
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

    return pd.concat(base_rows, ignore_index=True).sort_values(["date", "ticker"]).reset_index(drop=True)


def _compute_redesign_scores(frame: pd.DataFrame) -> pd.DataFrame:
    working = frame.sort_values(["ticker", "date"]).reset_index(drop=True).copy()
    working["rs_score_return_20d"] = pd.to_numeric(working["return_20d"], errors="coerce")
    working["daily_return_1d"] = working.groupby("ticker")["adj_close"].pct_change()
    working["volatility_20d"] = (
        working.groupby("ticker")["daily_return_1d"]
        .transform(lambda series: series.rolling(window=20, min_periods=20).std())
    )
    working["volatility_20d"] = pd.to_numeric(working["volatility_20d"], errors="coerce")
    working["rs_score_vol_adjusted_return_20d"] = np.where(
        working["volatility_20d"].gt(0) & working["rs_score_return_20d"].notna(),
        working["rs_score_return_20d"] / working["volatility_20d"],
        np.nan,
    )
    return working.sort_values(["date", "ticker"]).reset_index(drop=True)


def _target_selected_count(rankable_count: int, top_pct: Optional[float]) -> int:
    if rankable_count <= 0:
        return 0
    if top_pct is None:
        return int(rankable_count)
    return max(1, int(math.ceil(rankable_count * float(top_pct))))


def _apply_redesign_variant(frame: pd.DataFrame, variant: RedesignVariant) -> pd.DataFrame:
    working = frame.sort_values(["date", "ticker"]).reset_index(drop=True).copy()
    score_column = variant.score_column
    working["rs_score_active"] = pd.to_numeric(working[score_column], errors="coerce")
    working["rankable_for_rs"] = working["rs_score_active"].notna()
    working["rankable_ticker_count"] = working.groupby("date")["rankable_for_rs"].transform("sum").astype(int)
    working["available_ticker_count"] = working.groupby("date")["ticker"].transform("count").astype(int)
    working["rs_rank"] = (
        working.loc[working["rankable_for_rs"]]
        .groupby("date")["rs_score_active"]
        .rank(method="first", ascending=False)
    )
    working["rs_rank"] = working["rs_rank"].astype("Float64")

    if variant.selection_mode == "full_after_layer1":
        working["target_selected_count"] = working["available_ticker_count"].where(
            working["market_regime_bullish"],
            0,
        ).astype(int)
        working["median_score"] = pd.NA
        working["rs_selected"] = working["market_regime_bullish"].astype(bool)
    elif variant.selection_mode == "top_pct":
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
        working["median_score"] = pd.NA
        working["rs_selected"] = (
            working["market_regime_bullish"].astype(bool)
            & working["rankable_for_rs"].astype(bool)
            & working["rs_rank"].notna()
            & working["rs_rank"].le(working["target_selected_count"])
        )
    elif variant.selection_mode == "above_median":
        median_by_date = (
            working.loc[working["rankable_for_rs"], ["date", "rs_score_active"]]
            .groupby("date", as_index=False)["rs_score_active"]
            .median()
            .rename(columns={"rs_score_active": "median_score"})
        )
        working = working.merge(median_by_date, on="date", how="left")
        working["target_selected_count"] = (
            working.groupby("date")["ticker"]
            .transform(lambda s: 0)
            .astype(int)
        )
        working["rs_selected"] = (
            working["market_regime_bullish"].astype(bool)
            & working["rankable_for_rs"].astype(bool)
            & working["median_score"].notna()
            & working["rs_score_active"].gt(working["median_score"])
        )
        actual_selected = (
            working.groupby("date")["rs_selected"].transform("sum").fillna(0).astype(int)
        )
        working["target_selected_count"] = actual_selected
    else:  # pragma: no cover - defensive
        raise ValueError(f"Unsupported selection_mode: {variant.selection_mode}")

    working["active_selected"] = working["rs_selected"].astype(bool)
    working["phase_2_signal"] = (working["phase_1_signal_layer1"] & working["active_selected"]).fillna(False)
    working["phase_2_entry_skipped"] = (
        working["phase_1_signal_layer1"] & ~working["active_selected"]
    ).fillna(False)
    return working


def _summarize_variant(
    frame: pd.DataFrame,
    per_ticker_df: pd.DataFrame,
    variant: RedesignVariant,
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


def _build_failure_audit(phase_2_summary: Dict[str, object], phase_2_per_ticker_file: Path) -> Dict[str, object]:
    variant_results = pd.DataFrame(phase_2_summary.get("variant_results", []))
    if "variant_id" in variant_results.columns:
        audited = variant_results[
            variant_results["variant_id"].isin(["top_25pct_return_20d", "top_30pct_return_20d"])
        ].copy()
    else:
        audited = pd.DataFrame(
            columns=[
                "variant_id",
                "active_ticker_count_median",
                "total_trades",
                "median_trade_retention",
                "avg_delta_win_rate",
                "avg_delta_average_return",
            ]
        )
    if phase_2_per_ticker_file.exists():
        per_ticker_df = pd.read_csv(phase_2_per_ticker_file)
    else:
        per_ticker_df = pd.DataFrame()
    worst_by_variant: Dict[str, object] = {}
    for variant_id in ["top_25pct_return_20d", "top_30pct_return_20d"]:
        if per_ticker_df.empty:
            worst_by_variant[variant_id] = []
        else:
            sub = per_ticker_df[per_ticker_df["variant_id"] == variant_id][
                ["ticker", "trade_retention_pct", "delta_win_rate", "delta_average_return"]
            ].sort_values("delta_average_return")
            worst_by_variant[variant_id] = sub.head(4).to_dict(orient="records")

    return {
        "official_failure_classes": [
            "trade_retention_collapse",
            "sample_coverage_insufficient",
        ],
        "phase_2_variant_snapshot": audited[
            [
                "variant_id",
                "active_ticker_count_median",
                "total_trades",
                "median_trade_retention",
                "avg_delta_win_rate",
                "avg_delta_average_return",
            ]
        ].to_dict(orient="records"),
        "worst_ticker_drags": worst_by_variant,
        "reason_hypothesis": (
            "Top 25%/30% gagal terutama karena over-concentration pada universe 7 ticker: active universe turun "
            "ke 2-3 nama, trade retention sekitar 50%, lalu beberapa ticker besar seperti BBRI/BMRI/BBCA/TLKM "
            "menjadi drag kualitas ketika ranking terlalu sempit."
        ),
    }


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
            "Selected the redesign variant with the strongest balance of retained sample and quality delta."
        ),
    }


def _formal_decision(variant_df: pd.DataFrame, best_variant: Dict[str, object]) -> Dict[str, object]:
    if not best_variant.get("selected_variant_id"):
        return {
            "decision_code": "universe_too_small_for_relative_strength_validation",
            "reason": "No usable redesign variant was available.",
        }

    best = variant_df.loc[variant_df["variant_id"] == best_variant["selected_variant_id"]].iloc[0]
    quality_positive = bool(
        float(best["avg_delta_win_rate"]) > 0.0
        and float(best["avg_delta_average_return"]) > 0.0
        and int(best["tickers_with_coverage_collapse"]) == 0
    )
    non_inferior = bool(
        float(best["avg_delta_average_return"]) >= 0.0
        and float(best["avg_delta_win_rate"]) >= -0.25
        and float(best["median_trade_retention"]) >= 70.0
        and int(best["tickers_with_coverage_collapse"]) == 0
        and str(best["sample_adequacy_risk"]) != "high"
    )

    if quality_positive or non_inferior:
        return {
            "decision_code": "layer_2_candidate_identified",
            "quality_positive": quality_positive,
            "non_inferior": non_inferior,
            "selected_variant_id": str(best["variant_id"]),
            "selected_variant_label": str(best["variant_label"]),
            "reason": (
                "One redesign variant is quality-positive or at least non-inferior while keeping coverage healthy."
            ),
        }

    return {
        "decision_code": "universe_too_small_for_relative_strength_validation",
        "quality_positive": False,
        "non_inferior": False,
        "selected_variant_id": str(best["variant_id"]),
        "selected_variant_label": str(best["variant_label"]),
        "reason": (
            "All redesign variants remain quality-negative or sample-risky, so the current universe is too small "
            "for defensible relative strength validation."
        ),
    }


def _layer2_usability(decision: Dict[str, object]) -> Dict[str, object]:
    usable = str(decision["decision_code"]) == "layer_2_candidate_identified"
    return {
        "layer_2_usable_now": usable,
        "reason": (
            "A redesign candidate is strong enough to keep refining inside Layer 2."
            if usable
            else "Layer 2 redesign is not yet usable; the next bottleneck is universe size, not a small rule tweak."
        ),
    }


def run_phase_2_1_relative_strength_redesign(
    *,
    stock_indicator_master_file: Path,
    ihsg_indicator_master_file: Path,
    phase_2_summary_file: Path,
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

    phase_2_summary = json.loads(Path(phase_2_summary_file).read_text(encoding="utf-8"))
    phase_2_per_ticker_file = output_dir / "phase_2_relative_strength_selection_per_ticker.csv"

    enriched_frames: List[pd.DataFrame] = []
    per_ticker_rows: List[Dict[str, object]] = []
    variant_rows: List[Dict[str, object]] = []

    for variant in variants:
        variant_frame = _apply_redesign_variant(redesign_frame, variant)
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
    active_frame = pd.concat(
        [frame.drop(columns=["median_score"], errors="ignore") for frame in enriched_frames],
        ignore_index=True,
    )
    active_by_date_df = (
        active_frame
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
    decision = _formal_decision(variant_df, best_variant)
    usability = _layer2_usability(decision)
    failure_audit = _build_failure_audit(phase_2_summary, phase_2_per_ticker_file)
    universe_assessment = {
        "universe_now_too_small_for_final_validation": True,
        "max_rankable_tickers_on_any_date": int(active_by_date_df["rankable_ticker_count"].max()),
        "reason": (
            "Current pilot universe tetap terlalu kecil untuk validasi final RS, dan redesign Phase 2.1 "
            "dipakai terutama untuk menentukan apakah masih ada candidate yang cukup defensible."
        ),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    per_ticker_path = output_dir / "phase_2_1_relative_strength_redesign_per_ticker.csv"
    per_variant_path = output_dir / "phase_2_1_relative_strength_redesign_per_variant.csv"
    per_date_path = output_dir / "phase_2_1_relative_strength_redesign_active_universe_by_date.csv"
    summary_path = output_dir / "phase_2_1_relative_strength_redesign_summary.json"
    report_path = output_dir / "phase_2_1_relative_strength_redesign_report.txt"

    per_ticker_df.to_csv(per_ticker_path, index=False)
    variant_df.to_csv(per_variant_path, index=False)
    active_by_date_df.to_csv(per_date_path, index=False)

    summary_payload = {
        "phase": "phase_2_1_relative_strength_redesign",
        "status": "completed",
        "generated_at": _now_iso(),
        "source_files": {
            "stock_indicator_master_file": str(stock_indicator_master_file),
            "ihsg_indicator_master_file": str(ihsg_indicator_master_file),
            "phase_2_summary_file": str(phase_2_summary_file),
            "baseline_config": str(baseline_source) if baseline_source else None,
            "metadata_file": str(metadata_file) if metadata_file is not None else None,
        },
        "layer_1_frozen_definition": {
            "market_regime": "ihsg_ema50 > ihsg_ema200",
            "alignment_policy": "explicit_previous_trading_day_alignment",
        },
        "phase_2_failure_audit": failure_audit,
        "selection_variants_tested": [
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
        "formal_decision": decision,
        "layer_2_usability": usability,
        "universe_assessment": universe_assessment,
        "warnings": [*baseline_warnings, *metadata_warnings],
    }
    summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    report_lines = [
        "Phase 2.1 - Relative Strength Redesign",
        "======================================",
        "",
        "Failure audit from Phase 2:",
        f"- reason_hypothesis = {failure_audit['reason_hypothesis']}",
        "",
        "Variants tested:",
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
            f"- formal_decision = {decision['decision_code']}",
            f"- layer_2_usable_now = {usability['layer_2_usable_now']}",
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
    parser = argparse.ArgumentParser(description="Run Phase 2.1 relative strength redesign.")
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
        help="Phase 2 summary JSON used as the redesign source of truth.",
    )
    parser.add_argument("--output-dir", default="output", help="Directory for Phase 2.1 artifacts.")
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
    run_phase_2_1_relative_strength_redesign(
        stock_indicator_master_file=Path(args.stock_indicator_master_file),
        ihsg_indicator_master_file=Path(args.ihsg_indicator_master_file),
        phase_2_summary_file=Path(args.phase_2_summary_file),
        output_dir=Path(args.output_dir),
        hold_period=int(args.hold_period),
        allow_overlap=bool(args.allow_overlap),
        baseline_config=Path(args.baseline_config) if args.baseline_config else None,
        metadata_file=Path(args.metadata_file) if args.metadata_file else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
