"""Evaluate multiple Layer 1 market regime variants on the rebuild pipeline."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

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


VARIANT_SUMMARY_COLUMNS = [
    "variant_id",
    "variant_label",
    "definition",
    "mode",
    "bullish_day_pct",
    "pre_filter_signals",
    "post_filter_signals",
    "skipped_signals",
    "pre_filter_total_trades",
    "post_filter_total_trades",
    "trade_retention_pct_median",
    "avg_delta_win_rate",
    "avg_delta_average_return",
    "tickers_with_coverage_collapse",
    "coverage_collapse_tickers",
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
    "bullish_days",
    "non_bullish_days",
    "bullish_day_pct",
    "pre_filter_signals",
    "post_filter_signals",
    "skipped_signals",
    "signal_retention_pct",
    "coverage_collapsed",
    "pre_filter_total_trades",
    "post_filter_total_trades",
    "trade_retention_pct",
    "pre_filter_win_rate",
    "post_filter_win_rate",
    "delta_win_rate",
    "pre_filter_average_return",
    "post_filter_average_return",
    "delta_average_return",
    "pre_filter_max_drawdown",
    "post_filter_max_drawdown",
    "delta_max_drawdown",
]


@dataclass(frozen=True)
class RegimeVariant:
    variant_id: str
    label: str
    definition: str
    mode: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _load_stock_indicator_master(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise ValueError(f"Stock indicator master file not found: {path}")

    frame = pd.read_csv(path, parse_dates=["date"])
    required = {
        "ticker",
        "date",
        "open",
        "high",
        "low",
        "close",
        "adj_close",
        "volume",
        "ema50",
        "volume_ma20",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Stock indicator master file missing required columns: {missing}")
    return frame.sort_values(["ticker", "date"]).reset_index(drop=True)


def _load_ihsg_indicator_master(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise ValueError(f"IHSG indicator master file not found: {path}")

    frame = pd.read_csv(path, parse_dates=["date"])
    required = {"date", "adj_close", "ema50", "ema200"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"IHSG indicator master file missing required columns: {missing}")

    working = frame.sort_values("date").reset_index(drop=True).copy()
    working["ihsg_adj_close"] = pd.to_numeric(working["adj_close"], errors="coerce")
    working["ihsg_ema50"] = pd.to_numeric(working["ema50"], errors="coerce")
    working["ihsg_ema200"] = pd.to_numeric(working["ema200"], errors="coerce")
    if working[["ihsg_adj_close", "ihsg_ema50", "ihsg_ema200"]].isna().all().any():
        raise ValueError(f"IHSG indicator master file contains unusable numeric columns: {path}")

    working["ihsg_ema200_slope_up"] = (
        working["ihsg_ema200"].gt(working["ihsg_ema200"].shift(1))
        & working["ihsg_ema200"].notna()
        & working["ihsg_ema200"].shift(1).notna()
    ).fillna(False)
    return working[
        [
            "date",
            "ihsg_adj_close",
            "ihsg_ema50",
            "ihsg_ema200",
            "ihsg_ema200_slope_up",
        ]
    ]


def _build_variant_registry() -> List[RegimeVariant]:
    return [
        RegimeVariant(
            variant_id="price_above_ema200",
            label="Baseline current",
            definition="ihsg_adj_close > ihsg_ema200",
            mode="hard_gate",
        ),
        RegimeVariant(
            variant_id="price_above_ema200_and_slope_up",
            label="Price above EMA200 and EMA200 slope up",
            definition="ihsg_adj_close > ihsg_ema200 AND ihsg_ema200 > prev_ihsg_ema200",
            mode="hard_gate",
        ),
        RegimeVariant(
            variant_id="price_above_ema200_buffer_1pct",
            label="Price above EMA200 by 1%",
            definition="ihsg_adj_close > ihsg_ema200 * 1.01",
            mode="hard_gate",
        ),
        RegimeVariant(
            variant_id="ema50_above_ema200",
            label="EMA50 above EMA200",
            definition="ihsg_ema50 > ihsg_ema200",
            mode="hard_gate",
        ),
        RegimeVariant(
            variant_id="soft_risk_off_near_ema200",
            label="Soft risk-off near EMA200",
            definition=(
                "ihsg_adj_close > ihsg_ema200 OR "
                "(ihsg_adj_close > ihsg_ema200 * 0.99 AND ihsg_ema200 > prev_ihsg_ema200)"
            ),
            mode="soft_risk_off",
        ),
    ]


def _apply_variant_regime(ihsg_frame: pd.DataFrame, variant: RegimeVariant) -> pd.Series:
    price = ihsg_frame["ihsg_adj_close"]
    ema50 = ihsg_frame["ihsg_ema50"]
    ema200 = ihsg_frame["ihsg_ema200"]
    slope_up = ihsg_frame["ihsg_ema200_slope_up"]

    if variant.variant_id == "price_above_ema200":
        result = price.gt(ema200)
    elif variant.variant_id == "price_above_ema200_and_slope_up":
        result = price.gt(ema200) & slope_up
    elif variant.variant_id == "price_above_ema200_buffer_1pct":
        result = price.gt(ema200 * 1.01)
    elif variant.variant_id == "ema50_above_ema200":
        result = ema50.gt(ema200)
    elif variant.variant_id == "soft_risk_off_near_ema200":
        result = price.gt(ema200) | (price.gt(ema200 * 0.99) & slope_up)
    else:  # pragma: no cover - defensive
        raise ValueError(f"Unsupported regime variant: {variant.variant_id}")

    return result.fillna(False).astype(bool)


def _count_missing_ihsg_dates(merged: pd.DataFrame) -> Dict[str, int]:
    missing_mask = merged["ihsg_adj_close"].isna() | merged["ihsg_ema200"].isna()
    missing_rows = int(missing_mask.sum())
    missing_dates = int(merged.loc[missing_mask, "date"].nunique()) if missing_rows else 0
    return {
        "missing_rows": missing_rows,
        "missing_dates": missing_dates,
    }


def _build_base_signal_frame(
    frame: pd.DataFrame,
    *,
    threshold: float,
    strict_mode: bool,
) -> pd.DataFrame:
    working = frame.sort_values("date").reset_index(drop=True).copy()
    working["volume_ratio"] = working["volume"] / working["volume_ma20"]
    working["ema50_slope_up"] = (
        working["ema50"].gt(working["ema50"].shift(1))
        & working["ema50"].notna()
        & working["ema50"].shift(1).notna()
    ).fillna(False)
    minimum_signal = (
        working["adj_close"].gt(working["ema50"])
        & working["volume_ratio"].ge(float(threshold))
        & working["ema50"].notna()
        & working["volume_ma20"].notna()
    ).fillna(False)

    if strict_mode:
        working["phase_1_signal_base"] = (
            minimum_signal
            & working["ema50_slope_up"]
            & working["close"].gt(working["open"])
        ).fillna(False)
    else:
        working["phase_1_signal_base"] = minimum_signal.fillna(False)

    return working


def _build_variant_signal_frame(
    frame: pd.DataFrame,
    *,
    threshold: float,
    strict_mode: bool,
    variant: RegimeVariant,
) -> pd.DataFrame:
    working = _build_base_signal_frame(frame, threshold=threshold, strict_mode=strict_mode)
    working["market_regime_variant_bullish"] = _apply_variant_regime(working, variant=variant)
    working["phase_1_signal_variant"] = (
        working["phase_1_signal_base"] & working["market_regime_variant_bullish"]
    ).fillna(False)
    working["market_regime_entry_skipped"] = (
        working["phase_1_signal_base"] & ~working["market_regime_variant_bullish"]
    ).fillna(False)
    return working


def _summarize_trade_frame(trades: pd.DataFrame) -> Dict[str, float | int]:
    if trades.empty:
        return {
            "trade_count": 0,
            "win_rate": 0.0,
            "average_return": 0.0,
        }

    return {
        "trade_count": int(len(trades)),
        "win_rate": round(float(trades["is_win"].mean() * 100.0), 2),
        "average_return": round(float(trades["return_pct"].mean()), 4),
    }


def _evaluate_ticker_variant(
    ticker: str,
    frame: pd.DataFrame,
    *,
    variant: RegimeVariant,
    hold_period: int,
    allow_overlap: bool,
    threshold: float,
    strict_mode: bool,
) -> tuple[Dict[str, object], Dict[str, object]]:
    signal_frame = _build_variant_signal_frame(
        frame,
        threshold=threshold,
        strict_mode=strict_mode,
        variant=variant,
    )

    pre_signal_count = int(signal_frame["phase_1_signal_base"].fillna(False).astype(bool).sum())
    post_signal_count = int(signal_frame["phase_1_signal_variant"].fillna(False).astype(bool).sum())
    skipped_signal_count = int(signal_frame["market_regime_entry_skipped"].fillna(False).astype(bool).sum())

    pre_result = backtest_signal_frame(
        signal_frame,
        signal_column="phase_1_signal_base",
        hold_period=hold_period,
        allow_overlap=allow_overlap,
    )
    post_result = backtest_signal_frame(
        signal_frame,
        signal_column="phase_1_signal_variant",
        hold_period=hold_period,
        allow_overlap=allow_overlap,
    )
    skipped_result = backtest_signal_frame(
        signal_frame,
        signal_column="market_regime_entry_skipped",
        hold_period=hold_period,
        allow_overlap=allow_overlap,
    )

    bullish_days = int(signal_frame["market_regime_variant_bullish"].astype(bool).sum())
    non_bullish_days = int(len(signal_frame) - bullish_days)
    signal_retention_pct = round((post_signal_count / pre_signal_count) * 100.0, 4) if pre_signal_count else 0.0
    trade_retention_pct = (
        round((post_result.total_trades / pre_result.total_trades) * 100.0, 4)
        if pre_result.total_trades
        else 0.0
    )

    row = {
        "variant_id": variant.variant_id,
        "variant_label": variant.label,
        "ticker": ticker,
        "rows": int(len(signal_frame)),
        "date_start": signal_frame["date"].iloc[0].strftime("%Y-%m-%d"),
        "date_end": signal_frame["date"].iloc[-1].strftime("%Y-%m-%d"),
        "applied_threshold": float(threshold),
        "applied_strict_mode": bool(strict_mode),
        "bullish_days": bullish_days,
        "non_bullish_days": non_bullish_days,
        "bullish_day_pct": round((bullish_days / len(signal_frame)) * 100.0, 4),
        "pre_filter_signals": pre_signal_count,
        "post_filter_signals": post_signal_count,
        "skipped_signals": skipped_signal_count,
        "signal_retention_pct": signal_retention_pct,
        "coverage_collapsed": bool(post_signal_count == 0 and pre_signal_count > 0),
        "pre_filter_total_trades": int(pre_result.total_trades),
        "post_filter_total_trades": int(post_result.total_trades),
        "trade_retention_pct": trade_retention_pct,
        "pre_filter_win_rate": float(pre_result.win_rate),
        "post_filter_win_rate": float(post_result.win_rate),
        "delta_win_rate": round(float(post_result.win_rate) - float(pre_result.win_rate), 4),
        "pre_filter_average_return": float(pre_result.average_return),
        "post_filter_average_return": float(post_result.average_return),
        "delta_average_return": round(
            float(post_result.average_return) - float(pre_result.average_return), 4
        ),
        "pre_filter_max_drawdown": float(pre_result.max_drawdown),
        "post_filter_max_drawdown": float(post_result.max_drawdown),
        "delta_max_drawdown": round(
            float(post_result.max_drawdown) - float(pre_result.max_drawdown), 4
        ),
    }

    diagnostics = {
        "ticker": ticker,
        "pre_trade_count": int(pre_result.total_trades),
        "post_trade_count": int(post_result.total_trades),
        "skipped_trade_profile": _summarize_trade_frame(skipped_result.trades),
        "allowed_trade_profile": _summarize_trade_frame(post_result.trades),
    }
    return row, diagnostics


def _aggregate_variant_summary(
    per_ticker_df: pd.DataFrame,
    *,
    variant: RegimeVariant,
    daily_regime_frame: pd.DataFrame,
) -> Dict[str, object]:
    coverage_collapse_tickers = (
        per_ticker_df.loc[per_ticker_df["coverage_collapsed"].astype(bool), "ticker"]
        .astype(str)
        .tolist()
    )
    bullish_days = int(daily_regime_frame["market_regime_variant_bullish"].astype(bool).sum())
    total_days = int(len(daily_regime_frame))
    return {
        "variant_id": variant.variant_id,
        "variant_label": variant.label,
        "definition": variant.definition,
        "mode": variant.mode,
        "bullish_day_pct": round((bullish_days / total_days) * 100.0, 4) if total_days else 0.0,
        "pre_filter_signals": int(per_ticker_df["pre_filter_signals"].sum()),
        "post_filter_signals": int(per_ticker_df["post_filter_signals"].sum()),
        "skipped_signals": int(per_ticker_df["skipped_signals"].sum()),
        "pre_filter_total_trades": int(per_ticker_df["pre_filter_total_trades"].sum()),
        "post_filter_total_trades": int(per_ticker_df["post_filter_total_trades"].sum()),
        "trade_retention_pct_median": round(
            float(per_ticker_df["trade_retention_pct"].median()) if not per_ticker_df.empty else 0.0,
            4,
        ),
        "avg_delta_win_rate": round(
            float(per_ticker_df["delta_win_rate"].mean()) if not per_ticker_df.empty else 0.0,
            4,
        ),
        "avg_delta_average_return": round(
            float(per_ticker_df["delta_average_return"].mean()) if not per_ticker_df.empty else 0.0,
            4,
        ),
        "tickers_with_coverage_collapse": int(len(coverage_collapse_tickers)),
        "coverage_collapse_tickers": coverage_collapse_tickers,
    }


def _build_current_variant_diagnostics(
    per_ticker_df: pd.DataFrame,
    current_diagnostics: List[Dict[str, object]],
) -> Dict[str, object]:
    negative_delta = per_ticker_df.sort_values("delta_average_return").head(3)
    positive_delta = per_ticker_df.sort_values("delta_average_return", ascending=False).head(3)

    skipped_trade_count = sum(
        int(item["skipped_trade_profile"]["trade_count"]) for item in current_diagnostics
    )
    allowed_trade_count = sum(
        int(item["allowed_trade_profile"]["trade_count"]) for item in current_diagnostics
    )

    def _weighted_average(items: Iterable[Dict[str, object]], key: str, count_key: str) -> float:
        numerator = 0.0
        denominator = 0
        for item in items:
            profile = item[count_key]
            count = int(profile["trade_count"])
            numerator += _safe_float(profile[key]) * count
            denominator += count
        return round(numerator / denominator, 4) if denominator else 0.0

    return {
        "reason_hypothesis": (
            "Current hard gate is not quality-positive when it either removes trades that still have "
            "acceptable return profile or leaves too many weak trades during broad bullish states."
        ),
        "worst_delta_average_return_tickers": negative_delta[
            ["ticker", "delta_average_return", "delta_win_rate", "trade_retention_pct"]
        ].to_dict(orient="records"),
        "best_delta_average_return_tickers": positive_delta[
            ["ticker", "delta_average_return", "delta_win_rate", "trade_retention_pct"]
        ].to_dict(orient="records"),
        "skipped_trade_profile_aggregate": {
            "trade_count": skipped_trade_count,
            "win_rate": _weighted_average(current_diagnostics, "win_rate", "skipped_trade_profile"),
            "average_return": _weighted_average(
                current_diagnostics,
                "average_return",
                "skipped_trade_profile",
            ),
        },
        "allowed_trade_profile_aggregate": {
            "trade_count": allowed_trade_count,
            "win_rate": _weighted_average(current_diagnostics, "win_rate", "allowed_trade_profile"),
            "average_return": _weighted_average(
                current_diagnostics,
                "average_return",
                "allowed_trade_profile",
            ),
        },
    }


def _pick_final_candidate(variant_df: pd.DataFrame) -> Dict[str, object]:
    if variant_df.empty:
        return {
            "status": "no_candidate",
            "reason": "No variants were evaluated.",
            "selected_variant_id": None,
        }

    baseline_row = variant_df.loc[variant_df["variant_id"] == "price_above_ema200"]
    if baseline_row.empty:
        return {
            "status": "no_candidate",
            "reason": "Current baseline variant is missing from the evaluation set.",
            "selected_variant_id": None,
        }
    baseline = baseline_row.iloc[0]

    eligible = variant_df[
        (variant_df["tickers_with_coverage_collapse"] == 0)
        & (variant_df["trade_retention_pct_median"] >= 70.0)
        & (variant_df["avg_delta_win_rate"] >= float(baseline["avg_delta_win_rate"]))
        & (variant_df["avg_delta_average_return"] >= float(baseline["avg_delta_average_return"]))
    ].copy()

    if eligible.empty:
        return {
            "status": "needs_iteration",
            "reason": (
                "No tested variant kept coverage healthy and matched-or-beat the current baseline "
                "on both average delta win rate and average delta return."
            ),
            "selected_variant_id": None,
        }

    eligible = eligible.sort_values(
        by=[
            "avg_delta_average_return",
            "avg_delta_win_rate",
            "trade_retention_pct_median",
            "post_filter_total_trades",
        ],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)
    best = eligible.iloc[0]

    return {
        "status": "candidate_selected",
        "reason": (
            "Selected the strongest variant among healthy-coverage candidates that are not worse "
            "than the current baseline on the two official quality delta metrics."
        ),
        "selected_variant_id": str(best["variant_id"]),
        "selected_variant_label": str(best["variant_label"]),
        "freeze_layer_1": bool(
            float(best["avg_delta_average_return"]) >= 0.0 and float(best["avg_delta_win_rate"]) >= 0.0
        ),
    }


def run_phase_1_1_market_regime_filter_refinement(
    *,
    stock_indicator_master_file: Path,
    ihsg_indicator_master_file: Path,
    output_dir: Path,
    hold_period: int = 5,
    allow_overlap: bool = False,
    baseline_config: Optional[Path] = None,
    metadata_file: Optional[Path] = None,
) -> Dict[str, object]:
    stock_frame = _load_stock_indicator_master(stock_indicator_master_file)
    ihsg_frame = _load_ihsg_indicator_master(ihsg_indicator_master_file)

    merged = stock_frame.drop(
        columns=[column for column in ["ihsg_adj_close", "ihsg_ema200", "ihsg_regime_ready", "ihsg_regime_bullish"] if column in stock_frame.columns]
    ).merge(ihsg_frame, on="date", how="left")
    missing_ihsg_alignment = _count_missing_ihsg_dates(merged)

    baseline_payload, baseline_warnings, baseline_source = load_phase_a_baseline(baseline_config=baseline_config)
    metadata_lookup, metadata_warnings = load_optional_metadata_lookup(metadata_file)
    variants = _build_variant_registry()
    unique_market_dates = (
        merged[
            [
                "date",
                "ihsg_adj_close",
                "ihsg_ema50",
                "ihsg_ema200",
                "ihsg_ema200_slope_up",
            ]
        ]
        .drop_duplicates(subset=["date"], keep="last")
        .sort_values("date")
        .reset_index(drop=True)
    )

    per_ticker_rows: List[Dict[str, object]] = []
    variant_summaries: List[Dict[str, object]] = []
    current_variant_diagnostics: List[Dict[str, object]] = []

    for variant in variants:
        variant_rows: List[Dict[str, object]] = []
        variant_diagnostics: List[Dict[str, object]] = []

        for ticker, group in merged.groupby("ticker"):
            runtime = resolve_phase_a_runtime_settings(
                ticker=ticker,
                baseline_config=baseline_payload,
                metadata_lookup=metadata_lookup,
            )
            row, diagnostics = _evaluate_ticker_variant(
                ticker=ticker,
                frame=group.copy(),
                variant=variant,
                hold_period=hold_period,
                allow_overlap=allow_overlap,
                threshold=float(runtime["threshold"]),
                strict_mode=bool(runtime["strict_mode"]),
            )
            variant_rows.append(row)
            variant_diagnostics.append(diagnostics)

        variant_df = pd.DataFrame(variant_rows).reindex(columns=PER_TICKER_COLUMNS)
        daily_regime_frame = unique_market_dates.copy()
        daily_regime_frame["market_regime_variant_bullish"] = _apply_variant_regime(
            daily_regime_frame,
            variant=variant,
        )
        per_ticker_rows.extend(variant_df.to_dict(orient="records"))
        variant_summaries.append(
            _aggregate_variant_summary(
                variant_df,
                variant=variant,
                daily_regime_frame=daily_regime_frame,
            )
        )
        if variant.variant_id == "price_above_ema200":
            current_variant_diagnostics = variant_diagnostics
            current_variant_df = variant_df

    per_ticker_df = pd.DataFrame(per_ticker_rows).reindex(columns=PER_TICKER_COLUMNS)
    variant_df = pd.DataFrame(variant_summaries).reindex(columns=VARIANT_SUMMARY_COLUMNS)
    final_candidate = _pick_final_candidate(variant_df)
    current_diagnostics = _build_current_variant_diagnostics(current_variant_df, current_variant_diagnostics)

    output_dir.mkdir(parents=True, exist_ok=True)
    per_ticker_path = output_dir / "phase_1_1_market_regime_filter_refinement_per_ticker.csv"
    variant_path = output_dir / "phase_1_1_market_regime_filter_refinement_per_variant.csv"
    summary_path = output_dir / "phase_1_1_market_regime_filter_refinement_summary.json"
    report_path = output_dir / "phase_1_1_market_regime_filter_refinement_report.txt"

    per_ticker_df.to_csv(per_ticker_path, index=False)
    variant_df.to_csv(variant_path, index=False)

    summary_payload = {
        "phase": "phase_1_1_market_regime_filter_refinement",
        "status": "completed",
        "generated_at": _now_iso(),
        "source_files": {
            "stock_indicator_master_file": str(stock_indicator_master_file),
            "ihsg_indicator_master_file": str(ihsg_indicator_master_file),
            "baseline_config": str(baseline_source) if baseline_source else None,
            "metadata_file": str(metadata_file) if metadata_file is not None else None,
        },
        "ihsg_alignment": {
            **missing_ihsg_alignment,
            "missing_date_handling": "treated_as_non_bullish_for_variant_gate",
        },
        "variants_tested": [
            {
                "variant_id": variant.variant_id,
                "variant_label": variant.label,
                "definition": variant.definition,
                "mode": variant.mode,
            }
            for variant in variants
        ],
        "variant_results": variant_df.to_dict(orient="records"),
        "current_variant_audit": current_diagnostics,
        "final_candidate_decision": final_candidate,
        "warnings": [
            *baseline_warnings,
            *metadata_warnings,
            *(
                [
                    (
                        f"IHSG alignment missing on {missing_ihsg_alignment['missing_dates']} unique stock dates "
                        f"({missing_ihsg_alignment['missing_rows']} rows). Missing regime inputs are treated as non-bullish."
                    )
                ]
                if missing_ihsg_alignment["missing_dates"] > 0
                else []
            ),
        ],
    }
    summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    report_lines = [
        "Phase 1.1 - Market Regime Filter Refinement",
        "===========================================",
        "",
        "Variants tested:",
    ]
    for row in variant_df.to_dict(orient="records"):
        report_lines.extend(
            [
                f"- {row['variant_id']}: {row['definition']}",
                f"  bullish_day_pct={row['bullish_day_pct']}, pre_filter_signals={row['pre_filter_signals']}, post_filter_signals={row['post_filter_signals']}, skipped_signals={row['skipped_signals']}",
                f"  total_trades={row['post_filter_total_trades']}, median_trade_retention={row['trade_retention_pct_median']}, avg_delta_win_rate={row['avg_delta_win_rate']}, avg_delta_average_return={row['avg_delta_average_return']}",
                f"  coverage_collapse_tickers={row['coverage_collapse_tickers']}",
            ]
        )

    report_lines.extend(
        [
            "",
            "Current baseline audit:",
            f"- skipped_trade_average_return = {current_diagnostics['skipped_trade_profile_aggregate']['average_return']}",
            f"- allowed_trade_average_return = {current_diagnostics['allowed_trade_profile_aggregate']['average_return']}",
            f"- skipped_trade_win_rate = {current_diagnostics['skipped_trade_profile_aggregate']['win_rate']}",
            f"- allowed_trade_win_rate = {current_diagnostics['allowed_trade_profile_aggregate']['win_rate']}",
            "",
            "Final candidate decision:",
            f"- status = {final_candidate['status']}",
            f"- selected_variant_id = {final_candidate.get('selected_variant_id')}",
            f"- reason = {final_candidate['reason']}",
        ]
    )
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    return {
        "per_ticker_path": per_ticker_path,
        "variant_path": variant_path,
        "summary_path": summary_path,
        "report_path": report_path,
        "summary": summary_payload,
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase 1.1 market regime filter refinement.")
    parser.add_argument(
        "--stock-indicator-master-file",
        default="data/indicator_master/stock_indicator_master.csv",
        help="Stock indicator master CSV for the rebuild path.",
    )
    parser.add_argument(
        "--ihsg-indicator-master-file",
        default="data/indicator_master/IHSG_indicator_master.csv",
        help="IHSG indicator master CSV with EMA50 and EMA200.",
    )
    parser.add_argument("--output-dir", default="output", help="Directory for refinement artifacts.")
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
    run_phase_1_1_market_regime_filter_refinement(
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
