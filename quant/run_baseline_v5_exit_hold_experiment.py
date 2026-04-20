"""Run baseline v5 exit/hold redesign on top of the proven v4 anchor entry."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.evaluate_phase_a_real_data import load_price_csv  # noqa: E402
from quant.phase_a_baseline import (  # noqa: E402
    load_optional_metadata_lookup,
    load_phase_a_baseline,
    resolve_phase_a_runtime_settings,
)
from quant.phase_a_transition_utils import dedupe, read_json_object, safe_dict  # noqa: E402
from quant.run_baseline_v2_candidate_validation import (  # noqa: E402
    _candidate_signal,
    _compute_score_components,
    _feature_frame,
    _resolve_price_files,
    _safe_float,
    _safe_int,
)


PLAN_OUTPUT = "baseline_v5_redesign_plan.json"
RESULT_OUTPUT = "baseline_v5_exit_hold_results.csv"
SUMMARY_OUTPUT = "baseline_v5_exit_hold_summary.json"
REPORT_OUTPUT = "baseline_v5_exit_hold_report.txt"
GO_NO_GO_OUTPUT = "baseline_v5_exit_hold_go_no_go.json"

GO_NO_GO_DECISIONS = {
    "no_go",
    "keep_experimental",
    "promote_for_validation",
}

RESULT_COLUMNS = [
    "ticker",
    "variant_id",
    "candidate_id",
    "comparison_role",
    "entry_rule",
    "entry_anchor_rule",
    "quality_gate_id",
    "exit_rule_id",
    "exit_rule_summary",
    "max_hold_period",
    "stop_loss_pct",
    "take_profit_pct",
    "ema20_fail_exit",
    "min_trades_threshold",
    "profit_buffer_pct",
    "applied_threshold",
    "candidate_signal_count",
    "candidate_total_trades",
    "candidate_eligible_for_analysis",
    "win_rate",
    "buffered_win_rate",
    "average_return",
    "max_drawdown",
    "score_quality_reward",
    "score_trade_support_reward",
    "score_drawdown_penalty",
    "score_low_trade_penalty",
    "score",
    "exit_reason_counts",
    "category",
    "market_cap_group",
    "sector",
    "beta_group",
]

SUMMARY_COLUMNS = [
    "variant_id",
    "candidate_id",
    "comparison_role",
    "entry_rule",
    "entry_anchor_rule",
    "quality_gate_id",
    "exit_rule_id",
    "exit_rule_summary",
    "max_hold_period",
    "stop_loss_pct",
    "take_profit_pct",
    "ema20_fail_exit",
    "min_trades_threshold",
    "profit_buffer_pct",
    "ticker_count",
    "eligible_ticker_count",
    "positive_score_ticker_count",
    "total_trades_sum",
    "signal_count_sum",
    "mean_score",
    "mean_win_rate",
    "mean_buffered_win_rate",
    "mean_average_return",
    "mean_max_drawdown",
    "trade_retention_vs_reference",
    "trade_retention_vs_v4_anchor",
    "coverage_gain_vs_reference",
    "coverage_gain_vs_v4_anchor",
    "mean_average_return_delta_vs_v3",
    "mean_average_return_delta_vs_v4_anchor",
    "global_selection_score",
]


class BaselineV5ExitHoldCliError(ValueError):
    """Friendly CLI error for baseline v5 exit/hold redesign."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_for_json(value: object) -> object:
    if isinstance(value, dict):
        return {key: _sanitize_for_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_json(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_for_json(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if pd.isna(value) else float(value)
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return value


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_sanitize_for_json(payload), indent=2, ensure_ascii=True), encoding="utf-8")


def _write_text(path: Path, lines: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _buffered_win_rate(trades_df: pd.DataFrame, profit_buffer_pct: float) -> float:
    if trades_df.empty:
        return 0.0
    return round(float(trades_df["return_pct"].gt(float(profit_buffer_pct)).mean() * 100.0), 4)


def _safe_ratio(numerator: float, denominator: float) -> float:
    if float(denominator) <= 0:
        return 1.0 if float(numerator) > 0 else 0.0
    return round(float(numerator) / float(denominator), 4)


def _load_context(output_dir: Path) -> Dict[str, object]:
    artifact_map = {
        "v4_plan": "baseline_v4_redesign_plan.json",
        "v4_summary": "baseline_v4_quality_gate_summary.json",
        "v4_go_no_go": "baseline_v4_quality_gate_go_no_go.json",
        "v4_v2_summary": "baseline_v4_quality_gate_v2_summary.json",
        "v4_v2_go_no_go": "baseline_v4_quality_gate_v2_go_no_go.json",
        "roadmap": "project_roadmap_status.json",
    }
    payloads: Dict[str, object] = {}
    warnings: List[str] = []
    for key, filename in artifact_map.items():
        payload, item_warnings = read_json_object(Path(output_dir) / filename, filename)
        payloads[key] = payload if isinstance(payload, dict) else {}
        warnings.extend(item_warnings)
    payloads["warnings"] = dedupe(warnings)
    return payloads


def _build_exit_matrix(min_trades: int) -> pd.DataFrame:
    rows = [
        {
            "variant_id": "baseline_v5_hold4_extension",
            "candidate_id": "baseline_v5_hold4_extension",
            "comparison_role": "v5_candidate",
            "entry_rule": "v4_quality_gate_guard",
            "entry_anchor_rule": "close_gt_ema20_and_bullish_candle",
            "quality_gate_id": "body_strength_floor",
            "exit_rule_id": "fixed_hold_4",
            "exit_rule_summary": "Perpanjang hold dari 3 menjadi 4 bar tanpa exit tambahan.",
            "max_hold_period": 4,
            "stop_loss_pct": 0.0,
            "take_profit_pct": 0.0,
            "ema20_fail_exit": False,
            "min_trades_threshold": int(min_trades),
        },
        {
            "variant_id": "baseline_v5_hold5_extension",
            "candidate_id": "baseline_v5_hold5_extension",
            "comparison_role": "v5_candidate",
            "entry_rule": "v4_quality_gate_guard",
            "entry_anchor_rule": "close_gt_ema20_and_bullish_candle",
            "quality_gate_id": "body_strength_floor",
            "exit_rule_id": "fixed_hold_5",
            "exit_rule_summary": "Perpanjang hold menjadi 5 bar untuk menangkap follow-through lebih lama.",
            "max_hold_period": 5,
            "stop_loss_pct": 0.0,
            "take_profit_pct": 0.0,
            "ema20_fail_exit": False,
            "min_trades_threshold": int(min_trades),
        },
        {
            "variant_id": "baseline_v5_hold5_stop3_take6",
            "candidate_id": "baseline_v5_hold5_stop3_take6",
            "comparison_role": "v5_candidate",
            "entry_rule": "v4_quality_gate_guard",
            "entry_anchor_rule": "close_gt_ema20_and_bullish_candle",
            "quality_gate_id": "body_strength_floor",
            "exit_rule_id": "hold5_with_stop3_take6",
            "exit_rule_summary": "Max hold 5 bar dengan stop loss 3 persen dan take profit 6 persen.",
            "max_hold_period": 5,
            "stop_loss_pct": 3.0,
            "take_profit_pct": 6.0,
            "ema20_fail_exit": False,
            "min_trades_threshold": int(min_trades),
        },
        {
            "variant_id": "baseline_v5_hold5_ema20_fail_exit",
            "candidate_id": "baseline_v5_hold5_ema20_fail_exit",
            "comparison_role": "v5_candidate",
            "entry_rule": "v4_quality_gate_guard",
            "entry_anchor_rule": "close_gt_ema20_and_bullish_candle",
            "quality_gate_id": "body_strength_floor",
            "exit_rule_id": "hold5_with_ema20_fail_exit",
            "exit_rule_summary": "Max hold 5 bar tetapi keluar lebih cepat saat close jatuh di bawah EMA20.",
            "max_hold_period": 5,
            "stop_loss_pct": 0.0,
            "take_profit_pct": 0.0,
            "ema20_fail_exit": True,
            "min_trades_threshold": int(min_trades),
        },
    ]
    return pd.DataFrame(rows)


def _control_configs(min_trades: int) -> List[Dict[str, object]]:
    return [
        {
            "variant_id": "baseline_reference",
            "candidate_id": "baseline_v2_hold3_with_trend_guard",
            "comparison_role": "reference",
            "entry_rule": "close_gt_ema50_and_bullish_candle",
            "entry_anchor_rule": "close_gt_ema50_and_bullish_candle",
            "quality_gate_id": "none",
            "exit_rule_id": "fixed_hold_3",
            "exit_rule_summary": "Reference baseline fixed hold 3.",
            "max_hold_period": 3,
            "stop_loss_pct": 0.0,
            "take_profit_pct": 0.0,
            "ema20_fail_exit": False,
            "min_trades_threshold": int(min_trades),
        },
        {
            "variant_id": "baseline_v3_ema20_trend_guard",
            "candidate_id": "baseline_v3_ema20_trend_guard",
            "comparison_role": "v3_control",
            "entry_rule": "close_gt_ema20_and_bullish_candle",
            "entry_anchor_rule": "close_gt_ema20_and_bullish_candle",
            "quality_gate_id": "none",
            "exit_rule_id": "fixed_hold_3",
            "exit_rule_summary": "Fast anchor control fixed hold 3.",
            "max_hold_period": 3,
            "stop_loss_pct": 0.0,
            "take_profit_pct": 0.0,
            "ema20_fail_exit": False,
            "min_trades_threshold": int(min_trades),
        },
        {
            "variant_id": "baseline_v4_quality_gate_guard",
            "candidate_id": "baseline_v4_quality_gate_guard",
            "comparison_role": "v4_anchor_control",
            "entry_rule": "v4_quality_gate_guard",
            "entry_anchor_rule": "close_gt_ema20_and_bullish_candle",
            "quality_gate_id": "body_strength_floor",
            "exit_rule_id": "fixed_hold_3",
            "exit_rule_summary": "Baseline v4 iterasi pertama fixed hold 3.",
            "max_hold_period": 3,
            "stop_loss_pct": 0.0,
            "take_profit_pct": 0.0,
            "ema20_fail_exit": False,
            "min_trades_threshold": int(min_trades),
        },
    ]


def _prepare_v4_anchor_signal(feature_frame: pd.DataFrame, signal_column: str) -> pd.DataFrame:
    working = feature_frame.copy()
    if "ema20" not in working.columns:
        working["ema20"] = working["close"].ewm(span=20, adjust=False, min_periods=20).mean()

    candle_range = (working["high"] - working["low"]).clip(lower=0.0)
    candle_body = (working["close"] - working["open"]).abs()
    body_to_range_ratio = (
        candle_body.div(candle_range.where(candle_range.gt(0.0)))
    ).fillna(0.0)
    close_vs_open_pct = (
        working["close"].sub(working["open"]).div(working["open"].where(working["open"].gt(0.0))).mul(100.0)
    ).fillna(0.0)
    range_pct = (
        candle_range.div(working["close"].where(working["close"].gt(0.0))).mul(100.0)
    ).fillna(0.0)

    working[signal_column] = (
        working["close"].gt(working["ema20"])
        & working["ema20"].notna()
        & working["close"].gt(working["open"])
        & body_to_range_ratio.ge(0.55)
        & close_vs_open_pct.ge(0.35)
        & range_pct.ge(0.80)
    ).fillna(False)
    return working


def _build_entry_signal_frame(
    feature_frame: pd.DataFrame,
    config: Dict[str, object],
    threshold: float,
) -> Tuple[pd.DataFrame, str, str]:
    comparison_role = str(config.get("comparison_role") or "")
    candidate_id = str(config.get("candidate_id") or "")
    entry_rule = str(config.get("entry_rule") or "")

    if comparison_role in {"reference", "v3_control"}:
        return _candidate_signal(
            feature_frame=feature_frame,
            candidate_id=candidate_id,
            threshold=float(threshold),
            entry_rule=entry_rule,
        )

    signal_column = f"signal_{candidate_id}"
    working = _prepare_v4_anchor_signal(feature_frame=feature_frame, signal_column=signal_column)
    return working, signal_column, "close_gt_ema20_and_bullish_candle"


def _backtest_exit_variant(
    frame: pd.DataFrame,
    signal_column: str,
    max_hold_period: int,
    stop_loss_pct: float,
    take_profit_pct: float,
    ema20_fail_exit: bool,
    allow_overlap: bool = False,
) -> Dict[str, object]:
    if int(max_hold_period) < 1:
        raise ValueError("max_hold_period must be >= 1.")

    working = frame.copy().reset_index(drop=True)
    signal_series = working[signal_column].fillna(False).astype(bool).to_numpy()
    trades: List[Dict[str, object]] = []
    next_eligible_index = 0

    for signal_index, is_signal in enumerate(signal_series):
        if not is_signal:
            continue
        if not allow_overlap and signal_index < next_eligible_index:
            continue

        entry_index = signal_index + 1
        max_exit_index = signal_index + int(max_hold_period)
        if entry_index >= len(working) or max_exit_index >= len(working):
            continue

        entry_price = working.at[entry_index, "open"]
        if pd.isna(entry_price) or float(entry_price) <= 0:
            continue

        stop_price = float(entry_price) * (1.0 - (float(stop_loss_pct) / 100.0))
        take_price = float(entry_price) * (1.0 + (float(take_profit_pct) / 100.0))
        exit_index = max_exit_index
        exit_price = float(working.at[max_exit_index, "close"])
        exit_reason = "max_hold"

        for bar_index in range(entry_index, max_exit_index + 1):
            low_price = working.at[bar_index, "low"]
            high_price = working.at[bar_index, "high"]
            close_price = working.at[bar_index, "close"]
            ema20_value = working.at[bar_index, "ema20"] if "ema20" in working.columns else np.nan

            if float(stop_loss_pct) > 0 and pd.notna(low_price) and float(low_price) <= stop_price:
                exit_index = bar_index
                exit_price = float(stop_price)
                exit_reason = "stop_loss"
                break

            if float(take_profit_pct) > 0 and pd.notna(high_price) and float(high_price) >= take_price:
                exit_index = bar_index
                exit_price = float(take_price)
                exit_reason = "take_profit"
                break

            if bool(ema20_fail_exit) and pd.notna(close_price) and pd.notna(ema20_value) and float(close_price) < float(ema20_value):
                exit_index = bar_index
                exit_price = float(close_price)
                exit_reason = "ema20_fail"
                break

        trade_return = (float(exit_price) - float(entry_price)) / float(entry_price)
        trades.append(
            {
                "signal_date": working.at[signal_index, "date"],
                "entry_date": working.at[entry_index, "date"],
                "exit_date": working.at[exit_index, "date"],
                "entry_price": float(entry_price),
                "exit_price": float(exit_price),
                "return": float(trade_return),
                "return_pct": float(trade_return * 100.0),
                "is_win": bool(trade_return > 0),
                "exit_reason": exit_reason,
            }
        )

        if not allow_overlap:
            next_eligible_index = exit_index + 1

    trades_df = pd.DataFrame(trades)
    if trades_df.empty:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "average_return": 0.0,
            "max_drawdown": 0.0,
            "trades": trades_df,
            "exit_reason_counts": "",
        }

    equity = (1.0 + trades_df["return"]).cumprod()
    running_peak = equity.cummax()
    drawdown = (equity / running_peak) - 1.0
    exit_reason_counts = ",".join(
        f"{reason}:{count}" for reason, count in trades_df["exit_reason"].value_counts().sort_index().items()
    )
    return {
        "total_trades": int(len(trades_df)),
        "win_rate": round(float(trades_df["is_win"].mean() * 100.0), 2),
        "average_return": round(float(trades_df["return_pct"].mean()), 4),
        "max_drawdown": round(float(abs(drawdown.min()) * 100.0), 4),
        "trades": trades_df,
        "exit_reason_counts": exit_reason_counts,
    }


def evaluate_exit_hold_matrix(
    data_dir: Path,
    baseline_payload: Dict[str, object],
    metadata_lookup: Dict[str, Dict[str, object]],
    variant_df: pd.DataFrame,
    min_trades: int,
    profit_buffer_pct: float,
) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []

    for path in _resolve_price_files(data_dir):
        ticker = path.stem.upper()
        frame, _ = load_price_csv(path)
        runtime = resolve_phase_a_runtime_settings(
            ticker=ticker,
            baseline_config=baseline_payload,
            metadata_lookup=metadata_lookup,
        )
        metadata_row = dict(runtime.get("metadata_row") or {})
        feature_frame = _feature_frame(frame=frame, threshold=float(runtime["threshold"]))

        for config in variant_df.to_dict(orient="records"):
            signal_frame, signal_column, resolved_entry_rule = _build_entry_signal_frame(
                feature_frame=feature_frame,
                config=config,
                threshold=float(runtime["threshold"]),
            )
            signal_count = int(signal_frame[signal_column].fillna(False).astype(bool).sum())
            backtest = _backtest_exit_variant(
                frame=signal_frame,
                signal_column=signal_column,
                max_hold_period=_safe_int(config.get("max_hold_period"), 3),
                stop_loss_pct=_safe_float(config.get("stop_loss_pct")),
                take_profit_pct=_safe_float(config.get("take_profit_pct")),
                ema20_fail_exit=bool(config.get("ema20_fail_exit")),
                allow_overlap=False,
            )
            buffered_win_rate = _buffered_win_rate(backtest["trades"], profit_buffer_pct=profit_buffer_pct)
            score_components = _compute_score_components(
                total_trades=int(backtest["total_trades"]),
                buffered_win_rate=float(buffered_win_rate),
                average_return=float(backtest["average_return"]),
                max_drawdown=float(backtest["max_drawdown"]),
                min_trades_threshold=int(min_trades),
            )
            rows.append(
                {
                    "ticker": ticker,
                    "variant_id": str(config.get("variant_id") or ""),
                    "candidate_id": str(config.get("candidate_id") or ""),
                    "comparison_role": str(config.get("comparison_role") or ""),
                    "entry_rule": resolved_entry_rule,
                    "entry_anchor_rule": str(config.get("entry_anchor_rule") or ""),
                    "quality_gate_id": str(config.get("quality_gate_id") or ""),
                    "exit_rule_id": str(config.get("exit_rule_id") or ""),
                    "exit_rule_summary": str(config.get("exit_rule_summary") or ""),
                    "max_hold_period": _safe_int(config.get("max_hold_period"), 3),
                    "stop_loss_pct": _safe_float(config.get("stop_loss_pct")),
                    "take_profit_pct": _safe_float(config.get("take_profit_pct")),
                    "ema20_fail_exit": bool(config.get("ema20_fail_exit")),
                    "min_trades_threshold": int(min_trades),
                    "profit_buffer_pct": float(profit_buffer_pct),
                    "applied_threshold": float(runtime["threshold"]),
                    "candidate_signal_count": signal_count,
                    "candidate_total_trades": int(backtest["total_trades"]),
                    "candidate_eligible_for_analysis": bool(int(backtest["total_trades"]) >= int(min_trades)),
                    "win_rate": float(backtest["win_rate"]),
                    "buffered_win_rate": float(buffered_win_rate),
                    "average_return": float(backtest["average_return"]),
                    "max_drawdown": float(backtest["max_drawdown"]),
                    "score_quality_reward": float(score_components["score_quality_reward"]),
                    "score_trade_support_reward": float(score_components["score_trade_support_reward"]),
                    "score_drawdown_penalty": float(score_components["score_drawdown_penalty"]),
                    "score_low_trade_penalty": float(score_components["score_low_trade_penalty"]),
                    "score": float(score_components["score"]),
                    "exit_reason_counts": str(backtest["exit_reason_counts"]),
                    "category": metadata_row.get("category"),
                    "market_cap_group": metadata_row.get("market_cap_group"),
                    "sector": metadata_row.get("sector"),
                    "beta_group": metadata_row.get("beta_group"),
                }
            )

    results_df = pd.DataFrame(rows)
    if results_df.empty:
        return pd.DataFrame(columns=RESULT_COLUMNS)
    return results_df.reindex(columns=RESULT_COLUMNS).sort_values(
        ["ticker", "comparison_role", "score", "candidate_total_trades", "average_return"],
        ascending=[True, True, False, False, False],
    ).reset_index(drop=True)


def build_summary(results_df: pd.DataFrame) -> pd.DataFrame:
    if results_df.empty:
        return pd.DataFrame(columns=SUMMARY_COLUMNS)

    grouped = (
        results_df.groupby(
            [
                "variant_id",
                "candidate_id",
                "comparison_role",
                "entry_rule",
                "entry_anchor_rule",
                "quality_gate_id",
                "exit_rule_id",
                "exit_rule_summary",
                "max_hold_period",
                "stop_loss_pct",
                "take_profit_pct",
                "ema20_fail_exit",
                "min_trades_threshold",
                "profit_buffer_pct",
            ],
            dropna=False,
        )
        .agg(
            ticker_count=("ticker", "nunique"),
            eligible_ticker_count=("candidate_eligible_for_analysis", "sum"),
            positive_score_ticker_count=("score", lambda values: int((values > 0).sum())),
            total_trades_sum=("candidate_total_trades", "sum"),
            signal_count_sum=("candidate_signal_count", "sum"),
            mean_score=("score", "mean"),
            mean_win_rate=("win_rate", "mean"),
            mean_buffered_win_rate=("buffered_win_rate", "mean"),
            mean_average_return=("average_return", "mean"),
            mean_max_drawdown=("max_drawdown", "mean"),
        )
        .reset_index()
    )

    reference = dict(grouped.loc[grouped["variant_id"].eq("baseline_reference")].iloc[0].to_dict())
    v3_control = dict(grouped.loc[grouped["variant_id"].eq("baseline_v3_ema20_trend_guard")].iloc[0].to_dict())
    v4_anchor = dict(grouped.loc[grouped["variant_id"].eq("baseline_v4_quality_gate_guard")].iloc[0].to_dict())

    grouped["trade_retention_vs_reference"] = grouped["total_trades_sum"].map(
        lambda value: _safe_ratio(value, _safe_float(reference.get("total_trades_sum")))
    )
    grouped["trade_retention_vs_v4_anchor"] = grouped["total_trades_sum"].map(
        lambda value: _safe_ratio(value, _safe_float(v4_anchor.get("total_trades_sum")))
    )
    grouped["coverage_gain_vs_reference"] = (
        grouped["eligible_ticker_count"] - _safe_int(reference.get("eligible_ticker_count"))
    )
    grouped["coverage_gain_vs_v4_anchor"] = (
        grouped["eligible_ticker_count"] - _safe_int(v4_anchor.get("eligible_ticker_count"))
    )
    grouped["mean_average_return_delta_vs_v3"] = (
        grouped["mean_average_return"] - _safe_float(v3_control.get("mean_average_return"))
    )
    grouped["mean_average_return_delta_vs_v4_anchor"] = (
        grouped["mean_average_return"] - _safe_float(v4_anchor.get("mean_average_return"))
    )
    grouped["global_selection_score"] = (
        grouped["mean_average_return"] * 5.0
        + grouped["eligible_ticker_count"] * 6.0
        + grouped["positive_score_ticker_count"] * 2.0
        + grouped["total_trades_sum"] * 0.10
        + grouped["mean_average_return_delta_vs_v4_anchor"] * 2.0
    )
    return grouped.reindex(columns=SUMMARY_COLUMNS).sort_values(
        ["comparison_role", "global_selection_score", "eligible_ticker_count", "mean_average_return"],
        ascending=[True, False, False, False],
    ).reset_index(drop=True)


def determine_go_no_go(summary_df: pd.DataFrame) -> Dict[str, object]:
    reference = dict(summary_df.loc[summary_df["variant_id"].eq("baseline_reference")].iloc[0].to_dict())
    v3_control = dict(summary_df.loc[summary_df["variant_id"].eq("baseline_v3_ema20_trend_guard")].iloc[0].to_dict())
    v4_anchor = dict(summary_df.loc[summary_df["variant_id"].eq("baseline_v4_quality_gate_guard")].iloc[0].to_dict())
    candidates = summary_df.loc[summary_df["comparison_role"].eq("v5_candidate")].copy()
    if candidates.empty:
        raise BaselineV5ExitHoldCliError("No v5 candidates found in summary.")

    def _rank(row: pd.Series) -> Tuple[int, float, float, int, float]:
        delta_vs_v4 = _safe_float(row.get("mean_average_return_delta_vs_v4_anchor"))
        trade_ok = _safe_float(row.get("trade_retention_vs_v4_anchor")) >= 0.80
        coverage_up = _safe_int(row.get("coverage_gain_vs_v4_anchor")) >= 1
        quality_preserved = _safe_float(row.get("mean_average_return")) > 0 and _safe_float(row.get("mean_average_return_delta_vs_v3")) >= 0.25
        rank = 2 if quality_preserved and trade_ok and (coverage_up or _safe_int(row.get("eligible_ticker_count")) >= 3) and delta_vs_v4 >= 0.75 else 1 if quality_preserved and trade_ok and delta_vs_v4 >= 0.50 else 0
        return (
            rank,
            delta_vs_v4,
            _safe_float(row.get("mean_average_return")),
            _safe_int(row.get("eligible_ticker_count")),
            _safe_float(row.get("mean_score")),
        )

    ranked = candidates.sort_values(
        ["mean_average_return_delta_vs_v4_anchor", "mean_average_return", "eligible_ticker_count", "mean_score"],
        ascending=[False, False, False, False],
    ).copy()
    ranked["_rank"] = ranked.apply(_rank, axis=1)
    ranked = ranked.sort_values("_rank", ascending=False, key=lambda series: series).reset_index(drop=True)
    best = dict(ranked.iloc[0].to_dict())

    coverage_ok = _safe_int(best.get("eligible_ticker_count")) >= 3
    trade_support_ok = _safe_float(best.get("trade_retention_vs_v4_anchor")) >= 0.80
    quality_preserved = _safe_float(best.get("mean_average_return")) > 0 and _safe_float(best.get("mean_average_return_delta_vs_v3")) >= 0.25
    improved_vs_v4_anchor = _safe_float(best.get("mean_average_return_delta_vs_v4_anchor")) >= 0.75
    hypothesis_supported = bool(improved_vs_v4_anchor and trade_support_ok and quality_preserved)

    if coverage_ok and improved_vs_v4_anchor and trade_support_ok and quality_preserved:
        decision = "promote_for_validation"
        recommended_next_action = "validate_v5_exit_hold_candidate_without_changing_baseline"
    elif hypothesis_supported:
        decision = "keep_experimental"
        recommended_next_action = "keep_anchor_fixed_and_validate_best_exit_hold_variant"
    else:
        decision = "no_go"
        recommended_next_action = "exit_hold_not_enough_keep_anchor_but_reassess_root_cause"

    return {
        "best_candidate_id": str(best.get("candidate_id") or ""),
        "best_variant_id": str(best.get("variant_id") or ""),
        "decision": decision,
        "coverage_ok": bool(coverage_ok),
        "trade_support_ok": bool(trade_support_ok),
        "quality_preserved": bool(quality_preserved),
        "improved_vs_v4_anchor": bool(improved_vs_v4_anchor),
        "supports_exit_hold_hypothesis": bool(hypothesis_supported),
        "eligible_ticker_count": _safe_int(best.get("eligible_ticker_count")),
        "total_trades_sum": _safe_int(best.get("total_trades_sum")),
        "mean_average_return": _safe_float(best.get("mean_average_return")),
        "mean_average_return_delta_vs_v3": _safe_float(best.get("mean_average_return_delta_vs_v3")),
        "mean_average_return_delta_vs_v4_anchor": _safe_float(best.get("mean_average_return_delta_vs_v4_anchor")),
        "trade_retention_vs_reference": _safe_float(best.get("trade_retention_vs_reference")),
        "trade_retention_vs_v4_anchor": _safe_float(best.get("trade_retention_vs_v4_anchor")),
        "coverage_gain_vs_reference": _safe_int(best.get("coverage_gain_vs_reference")),
        "coverage_gain_vs_v4_anchor": _safe_int(best.get("coverage_gain_vs_v4_anchor")),
        "reference_variant_id": str(reference.get("variant_id") or ""),
        "v3_control_variant_id": str(v3_control.get("variant_id") or ""),
        "v4_anchor_variant_id": str(v4_anchor.get("variant_id") or ""),
        "recommended_next_action": recommended_next_action,
        "decision_notes": dedupe(
            [
                "Anchor entry utama tetap dipertahankan; eksperimen hanya mengubah exit/hold.",
                "Coverage target tercapai (>=3 ticker eligible)." if coverage_ok else "Coverage masih di bawah target minimum 3 ticker eligible.",
                "Trade retention terhadap anchor v4 cukup terjaga." if trade_support_ok else "Trade retention terhadap anchor v4 turun terlalu jauh.",
                "Quality preserved versus baseline_v3_ema20_trend_guard." if quality_preserved else "Quality belum preserved versus baseline_v3_ema20_trend_guard.",
                "Average return membaik material versus baseline_v4_quality_gate_guard iterasi pertama." if improved_vs_v4_anchor else "Average return belum membaik material versus baseline_v4_quality_gate_guard iterasi pertama.",
                "Hipotesis exit/hold mendapat dukungan data." if hypothesis_supported else "Data belum cukup membuktikan bahwa masalah utama ada di exit/hold logic.",
            ]
        ),
    }


def build_plan_payload(context_payloads: Dict[str, object], variant_df: pd.DataFrame) -> Dict[str, object]:
    roadmap = safe_dict(context_payloads.get("roadmap"))
    latest_status = safe_dict(roadmap.get("latest_execution_status"))
    v4_go = safe_dict(context_payloads.get("v4_go_no_go"))
    v4_summary = safe_dict(context_payloads.get("v4_summary"))
    v4_best = safe_dict(v4_summary.get("best_v4_candidate_summary"))
    v4_v2_go = safe_dict(context_payloads.get("v4_v2_go_no_go"))
    v4_v2_summary = safe_dict(context_payloads.get("v4_v2_summary"))
    v4_v2_best = safe_dict(v4_v2_summary.get("best_v4_candidate_summary"))
    v4_plan = safe_dict(context_payloads.get("v4_plan"))

    return {
        "generated_at": _now_iso(),
        "experiment_id": "baseline_v5_exit_hold_redesign",
        "state_snapshot": {
            "phase_a_status": latest_status.get("phase_a_status") or "closed_with_notes",
            "phase_b_status": latest_status.get("phase_b_status") or "phase_b_needs_redesign_before_continue",
            "phase_c_decision": latest_status.get("phase_c_decision") or "phase_c_no_go_yet",
        },
        "guardrails": [
            "Jangan keluar jalur roadmap.",
            "Jangan hidupkan lagi item 5-8.",
            "Jangan ubah baseline aktif.",
            "Jangan lanjut ke Phase C.",
            "Jangan ubah anchor entry utama dulu.",
            "Jangan lanjutkan entry relaxation only.",
        ],
        "redesign_hypothesis": {
            "selected_hypothesis_id": "candidate_b_simple_entry_exit_hold_redesign",
            "why_now": [
                "Quality gate setelah fast anchor pernah terlihat menjanjikan pada iterasi pertama.",
                "Iterasi v2 gagal total sehingga pelonggaran entry murni tidak layak diteruskan.",
                "Langkah lurus berikutnya adalah menguji apakah kualitas bisa dipulihkan lewat redesign exit/hold di atas anchor yang sama.",
            ],
        },
        "anchor_to_keep_fixed": {
            "variant_id": "baseline_v4_quality_gate_guard",
            "entry_anchor_rule": "close_gt_ema20_and_bullish_candle",
            "quality_gate_id": "body_strength_floor",
            "source_metrics_iter1": {
                "decision": v4_go.get("decision"),
                "eligible_ticker_count": v4_go.get("eligible_ticker_count") or v4_best.get("eligible_ticker_count"),
                "total_trades_sum": v4_go.get("total_trades_sum") or v4_best.get("total_trades_sum"),
                "mean_average_return": v4_go.get("mean_average_return") or v4_best.get("mean_average_return"),
                "quality_preserved": v4_go.get("quality_preserved"),
            },
            "failed_relaxation_v2_snapshot": {
                "decision": v4_v2_go.get("decision"),
                "eligible_ticker_count": v4_v2_go.get("eligible_ticker_count") or v4_v2_best.get("eligible_ticker_count"),
                "total_trades_sum": v4_v2_go.get("total_trades_sum") or v4_v2_best.get("total_trades_sum"),
                "mean_average_return": v4_v2_go.get("mean_average_return") or v4_v2_best.get("mean_average_return"),
                "quality_preserved": v4_v2_go.get("quality_preserved"),
                "trade_support_ok": v4_v2_go.get("trade_support_ok"),
            },
        },
        "comparison_targets": [
            "baseline_reference",
            "baseline_v3_ema20_trend_guard",
            "baseline_v4_quality_gate_guard",
        ],
        "exit_hold_variants": [_sanitize_for_json(row) for row in variant_df.to_dict(orient="records")],
        "success_criteria": {
            "preferred_decisions": ["keep_experimental", "promote_for_validation"],
            "promote_gate": "eligible_ticker_count >= 3, quality preserved vs v3, trade retention vs v4 anchor >= 0.80, dan mean_average_return improvement vs v4 anchor >= 0.75",
            "evidence_gate": "Jika coverage belum >=3 tetapi quality dan return improvement material sambil trade retention tetap terjaga, kandidat tetap boleh keep_experimental.",
        },
        "carry_forward_from_v4": safe_dict(v4_plan.get("decision_summary")),
        "warnings": list(context_payloads.get("warnings") or []),
    }


def build_summary_payload(
    summary_df: pd.DataFrame,
    go_no_go: Dict[str, object],
    plan_payload: Dict[str, object],
    context_payloads: Dict[str, object],
) -> Dict[str, object]:
    reference = dict(summary_df.loc[summary_df["variant_id"].eq("baseline_reference")].iloc[0].to_dict())
    v3_control = dict(summary_df.loc[summary_df["variant_id"].eq("baseline_v3_ema20_trend_guard")].iloc[0].to_dict())
    v4_anchor = dict(summary_df.loc[summary_df["variant_id"].eq("baseline_v4_quality_gate_guard")].iloc[0].to_dict())
    best = dict(summary_df.loc[summary_df["variant_id"].eq(go_no_go["best_variant_id"])].iloc[0].to_dict())
    return {
        "generated_at": _now_iso(),
        "plan_snapshot": _sanitize_for_json(plan_payload),
        "reference_summary": _sanitize_for_json(reference),
        "v3_control_summary": _sanitize_for_json(v3_control),
        "v4_anchor_summary": _sanitize_for_json(v4_anchor),
        "best_v5_candidate_summary": _sanitize_for_json(best),
        "go_no_go": _sanitize_for_json(go_no_go),
        "prior_v4_iter1_snapshot": _sanitize_for_json(safe_dict(context_payloads.get("v4_summary")).get("best_v4_candidate_summary")),
        "prior_v4_iter2_snapshot": _sanitize_for_json(safe_dict(context_payloads.get("v4_v2_summary")).get("best_v4_candidate_summary")),
        "warnings": list(context_payloads.get("warnings") or []),
    }


def build_report_text(summary_payload: Dict[str, object]) -> str:
    reference = safe_dict(summary_payload.get("reference_summary"))
    v3_control = safe_dict(summary_payload.get("v3_control_summary"))
    v4_anchor = safe_dict(summary_payload.get("v4_anchor_summary"))
    best = safe_dict(summary_payload.get("best_v5_candidate_summary"))
    go_no_go = safe_dict(summary_payload.get("go_no_go"))

    lines = [
        "Baseline v5 Exit/Hold Redesign",
        "===============================",
        "",
        f"- Decision: {go_no_go.get('decision')}",
        f"- Best candidate: {go_no_go.get('best_candidate_id')}",
        f"- Supports exit/hold hypothesis: {go_no_go.get('supports_exit_hold_hypothesis')}",
        f"- Coverage ok: {go_no_go.get('coverage_ok')}",
        f"- Trade support ok: {go_no_go.get('trade_support_ok')}",
        f"- Quality preserved: {go_no_go.get('quality_preserved')}",
        f"- Improved vs v4 anchor: {go_no_go.get('improved_vs_v4_anchor')}",
        f"- Recommended next action: {go_no_go.get('recommended_next_action')}",
        "",
        "Reference baseline:",
        f"- eligible_ticker_count={_safe_int(reference.get('eligible_ticker_count'))}",
        f"- total_trades_sum={_safe_int(reference.get('total_trades_sum'))}",
        f"- mean_average_return={_safe_float(reference.get('mean_average_return')):+.5f}",
        "",
        "V3 control:",
        f"- eligible_ticker_count={_safe_int(v3_control.get('eligible_ticker_count'))}",
        f"- total_trades_sum={_safe_int(v3_control.get('total_trades_sum'))}",
        f"- mean_average_return={_safe_float(v3_control.get('mean_average_return')):+.5f}",
        "",
        "V4 anchor control:",
        f"- eligible_ticker_count={_safe_int(v4_anchor.get('eligible_ticker_count'))}",
        f"- total_trades_sum={_safe_int(v4_anchor.get('total_trades_sum'))}",
        f"- mean_average_return={_safe_float(v4_anchor.get('mean_average_return')):+.5f}",
        "",
        "Best v5 candidate:",
        f"- candidate_id={best.get('candidate_id')}",
        f"- exit_rule_id={best.get('exit_rule_id')}",
        f"- eligible_ticker_count={_safe_int(best.get('eligible_ticker_count'))}",
        f"- total_trades_sum={_safe_int(best.get('total_trades_sum'))}",
        f"- mean_average_return={_safe_float(best.get('mean_average_return')):+.5f}",
        f"- trade_retention_vs_v4_anchor={_safe_float(best.get('trade_retention_vs_v4_anchor')):.4f}",
        f"- coverage_gain_vs_v4_anchor={_safe_int(best.get('coverage_gain_vs_v4_anchor'))}",
        f"- mean_average_return_delta_vs_v4_anchor={_safe_float(best.get('mean_average_return_delta_vs_v4_anchor')):+.5f}",
        f"- mean_average_return_delta_vs_v3={_safe_float(best.get('mean_average_return_delta_vs_v3')):+.5f}",
    ]
    if go_no_go.get("decision_notes"):
        lines.extend(["", "Decision notes:"])
        for item in list(go_no_go.get("decision_notes") or []):
            lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def run_baseline_v5_exit_hold_experiment(
    output_dir: Path,
    data_dir: Optional[Path] = None,
    baseline_config: Optional[Path] = None,
    metadata_file: Optional[Path] = None,
    min_trades: int = 5,
    profit_buffer_pct: float = 0.0,
) -> Dict[str, object]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    context_payloads = _load_context(output_dir=output_dir)
    variant_df = pd.concat(
        [pd.DataFrame(_control_configs(min_trades=min_trades)), _build_exit_matrix(min_trades=min_trades)],
        ignore_index=True,
    )
    plan_payload = build_plan_payload(context_payloads=context_payloads, variant_df=variant_df.loc[variant_df["comparison_role"].eq("v5_candidate")])
    _write_json(output_dir / PLAN_OUTPUT, plan_payload)

    baseline_payload, baseline_warnings, _ = load_phase_a_baseline(baseline_config=baseline_config)
    metadata_lookup, metadata_warnings = load_optional_metadata_lookup(metadata_file)
    context_payloads["warnings"] = dedupe([*list(context_payloads.get("warnings") or []), *baseline_warnings, *metadata_warnings])

    results_df = evaluate_exit_hold_matrix(
        data_dir=Path(data_dir or "data"),
        baseline_payload=baseline_payload,
        metadata_lookup=metadata_lookup,
        variant_df=variant_df,
        min_trades=int(min_trades),
        profit_buffer_pct=float(profit_buffer_pct),
    )
    if results_df.empty:
        raise BaselineV5ExitHoldCliError("No v5 exit/hold results were produced.")

    summary_df = build_summary(results_df=results_df)
    go_no_go = determine_go_no_go(summary_df=summary_df)
    summary_payload = build_summary_payload(
        summary_df=summary_df,
        go_no_go=go_no_go,
        plan_payload=plan_payload,
        context_payloads=context_payloads,
    )
    report_text = build_report_text(summary_payload=summary_payload)

    results_path = output_dir / RESULT_OUTPUT
    summary_path = output_dir / SUMMARY_OUTPUT
    report_path = output_dir / REPORT_OUTPUT
    go_no_go_path = output_dir / GO_NO_GO_OUTPUT

    results_df.to_csv(results_path, index=False)
    _write_json(summary_path, summary_payload)
    _write_text(report_path, report_text.rstrip("\n").splitlines())
    _write_json(go_no_go_path, go_no_go)

    return {
        "results_df": results_df,
        "summary_df": summary_df,
        "summary_payload": summary_payload,
        "go_no_go": go_no_go,
        "plan_payload": plan_payload,
        "artifacts": {
            "plan_json": str(output_dir / PLAN_OUTPUT),
            "results_csv": str(results_path),
            "summary_json": str(summary_path),
            "report_txt": str(report_path),
            "go_no_go_json": str(go_no_go_path),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run baseline v5 exit/hold redesign without changing the active baseline.")
    parser.add_argument("--output-dir", default="output", help="Directory for v5 artifacts.")
    parser.add_argument("--data-dir", default="data", help="Directory containing price CSV files.")
    parser.add_argument(
        "--baseline-config",
        default="output/phase_a_baseline_final.json",
        help="Path to baseline config JSON.",
    )
    parser.add_argument(
        "--metadata-file",
        default="data/ticker_metadata.csv",
        help="Optional metadata CSV path.",
    )
    parser.add_argument("--min-trades", type=int, default=5, help="Minimum trades threshold. Default: 5")
    parser.add_argument(
        "--profit-buffer-pct",
        type=float,
        default=0.0,
        help="Optional profit buffer for buffered win rate. Default: 0.0",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_baseline_v5_exit_hold_experiment(
        output_dir=Path(args.output_dir),
        data_dir=Path(args.data_dir),
        baseline_config=Path(args.baseline_config) if args.baseline_config else None,
        metadata_file=Path(args.metadata_file) if args.metadata_file else None,
        min_trades=int(args.min_trades),
        profit_buffer_pct=float(args.profit_buffer_pct),
    )
    print(f"Decision: {result['go_no_go']['decision']}")
    print(f"Best candidate: {result['go_no_go']['best_candidate_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
