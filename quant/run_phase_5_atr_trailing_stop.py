"""Evaluate Layer 5 ATR trailing stop on top of frozen Layer 1 and Layer 2 alternative."""

from __future__ import annotations

import argparse
import json
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
)
from quant.run_phase_2_1_relative_strength_redesign import _prepare_layer1_signal_frame  # noqa: E402
from quant.run_phase_2_relative_strength_stock_selection import _classify_sample_adequacy_risk  # noqa: E402
from quant.run_phase_3_rsi14_integration import _compute_features  # noqa: E402


VARIANT_SUMMARY_COLUMNS = [
    "variant_id",
    "variant_label",
    "layer_3_active",
    "exit_policy",
    "atr_multiplier",
    "time_stop_days",
    "active_ticker_count_median",
    "active_ticker_count_min",
    "active_ticker_count_max",
    "active_ticker_count_mean",
    "active_single_ticker_day_pct",
    "total_signals",
    "total_trades",
    "avg_return_per_trade",
    "avg_win_rate",
    "avg_holding_period_actual",
    "max_drawdown_per_trade",
    "tickers_with_coverage_collapse",
    "coverage_collapse_tickers",
    "sample_adequacy_risk",
    "sample_adequacy_reason",
]

PER_TICKER_COLUMNS = [
    "variant_id",
    "variant_label",
    "ticker",
    "entry_signals",
    "total_trades",
    "avg_return_per_trade",
    "avg_win_rate",
    "avg_holding_period_actual",
    "max_drawdown_per_trade",
    "coverage_collapsed",
]


@dataclass(frozen=True)
class ExitVariant:
    variant_id: str
    label: str
    layer_3_active: bool
    exit_policy: str
    atr_multiplier: Optional[float]
    time_stop_days: Optional[int]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_variant_registry() -> List[ExitVariant]:
    return [
        ExitVariant(
            variant_id="baseline_fixed_hold_5d",
            label="Baseline fixed hold 5 days",
            layer_3_active=False,
            exit_policy="fixed_hold_5d",
            atr_multiplier=None,
            time_stop_days=None,
        ),
        ExitVariant(
            variant_id="atr_trailing_stop_no_layer3",
            label="ATR trailing stop without Layer 3",
            layer_3_active=False,
            exit_policy="atr_trailing_stop",
            atr_multiplier=2.5,
            time_stop_days=15,
        ),
        ExitVariant(
            variant_id="atr_trailing_stop_with_layer3_toggle",
            label="ATR trailing stop with Layer 3 toggle",
            layer_3_active=True,
            exit_policy="atr_trailing_stop",
            atr_multiplier=2.5,
            time_stop_days=15,
        ),
    ]


def _compute_exit_features(
    frame: pd.DataFrame,
    *,
    momentum_floor_on_return_20d: float = 0.0,
    confirmation_days: int = 0,
    short_term_ema_slope_gate: str = "none",
) -> pd.DataFrame:
    working = _compute_features(
        frame,
        momentum_floor_on_return_20d=float(momentum_floor_on_return_20d),
        confirmation_days=int(confirmation_days),
        short_term_ema_slope_gate=str(short_term_ema_slope_gate),
    )
    working = working.sort_values(["ticker", "date"]).reset_index(drop=True).copy()
    working["prev_close_raw"] = working.groupby("ticker")["close"].shift(1)
    high_low = pd.to_numeric(working["high"], errors="coerce") - pd.to_numeric(working["low"], errors="coerce")
    high_prev = (
        pd.to_numeric(working["high"], errors="coerce") - pd.to_numeric(working["prev_close_raw"], errors="coerce")
    ).abs()
    low_prev = (
        pd.to_numeric(working["low"], errors="coerce") - pd.to_numeric(working["prev_close_raw"], errors="coerce")
    ).abs()
    working["true_range"] = pd.concat([high_low, high_prev, low_prev], axis=1).max(axis=1)
    working["atr14"] = (
        working.groupby("ticker")["true_range"]
        .transform(lambda series: series.rolling(window=14, min_periods=14).mean())
        .astype(float)
    )
    working["atr14_ready"] = working["atr14"].notna()
    working["layer2_alt_entry_active"] = (
        working["layer2_alt_active"].astype(bool)
    )
    working["layer3_optional_active"] = working["layer3_rsi_50_70_active"].astype(bool)
    working["available_ticker_count"] = working.groupby("date")["ticker"].transform("count").astype(int)
    return working.sort_values(["date", "ticker"]).reset_index(drop=True)


def _apply_variant(frame: pd.DataFrame, variant: ExitVariant) -> pd.DataFrame:
    working = frame.sort_values(["date", "ticker"]).reset_index(drop=True).copy()
    base_active = working["layer2_alt_entry_active"].astype(bool)
    if variant.layer_3_active:
        working["active_selected"] = base_active & working["layer3_optional_active"].astype(bool)
    else:
        working["active_selected"] = base_active
    working["entry_signal"] = (working["phase_1_signal_layer1"] & working["active_selected"]).fillna(False)
    working["target_selected_count"] = (
        working.groupby("date")["active_selected"].transform("sum").fillna(0).astype(int)
    )
    return working


def _backtest_fixed_hold(
    frame: pd.DataFrame,
    *,
    signal_column: str,
    hold_period: int = 5,
    allow_overlap: bool = False,
) -> pd.DataFrame:
    working = frame.sort_values("date").reset_index(drop=True).copy()
    signal_series = working[signal_column].fillna(False).astype(bool).to_numpy()
    trades: List[Dict[str, object]] = []
    next_eligible_index = 0

    for signal_index, is_signal in enumerate(signal_series):
        if not is_signal:
            continue
        if not allow_overlap and signal_index < next_eligible_index:
            continue

        entry_index = signal_index + 1
        exit_index = entry_index + hold_period - 1
        if entry_index >= len(working) or exit_index >= len(working):
            continue

        entry_price = pd.to_numeric(pd.Series([working.at[entry_index, "open"]]), errors="coerce").iloc[0]
        exit_price = pd.to_numeric(pd.Series([working.at[exit_index, "close"]]), errors="coerce").iloc[0]
        if pd.isna(entry_price) or pd.isna(exit_price) or entry_price <= 0:
            continue

        trade_slice = working.iloc[entry_index : exit_index + 1]
        min_low = pd.to_numeric(trade_slice["low"], errors="coerce").min()
        max_drawdown_pct = (
            max(0.0, float((entry_price - min_low) / entry_price * 100.0))
            if pd.notna(min_low)
            else 0.0
        )
        trade_return = float((exit_price - entry_price) / entry_price * 100.0)
        holding_period_bars = int(exit_index - entry_index + 1)

        trades.append(
            {
                "signal_date": working.at[signal_index, "date"],
                "entry_date": working.at[entry_index, "date"],
                "exit_date": working.at[exit_index, "date"],
                "entry_price": float(entry_price),
                "exit_price": float(exit_price),
                "return_pct": trade_return,
                "is_win": bool(trade_return > 0),
                "holding_period_bars": holding_period_bars,
                "max_drawdown_pct": round(max_drawdown_pct, 4),
                "exit_reason": "fixed_hold_5d",
            }
        )
        if not allow_overlap:
            next_eligible_index = exit_index + 1

    return pd.DataFrame(trades)


def _backtest_atr_trailing_stop(
    frame: pd.DataFrame,
    *,
    signal_column: str,
    atr_multiplier: float = 2.5,
    time_stop_days: int = 15,
    allow_overlap: bool = False,
) -> pd.DataFrame:
    working = frame.sort_values("date").reset_index(drop=True).copy()
    signal_series = working[signal_column].fillna(False).astype(bool).to_numpy()
    trades: List[Dict[str, object]] = []
    next_eligible_index = 0

    for signal_index, is_signal in enumerate(signal_series):
        if not is_signal:
            continue
        if not allow_overlap and signal_index < next_eligible_index:
            continue

        entry_index = signal_index + 1
        if entry_index >= len(working):
            continue

        entry_price = pd.to_numeric(pd.Series([working.at[entry_index, "open"]]), errors="coerce").iloc[0]
        entry_atr = pd.to_numeric(pd.Series([working.at[entry_index, "atr14"]]), errors="coerce").iloc[0]
        if pd.isna(entry_price) or entry_price <= 0 or pd.isna(entry_atr) or entry_atr <= 0:
            continue

        trailing_stop = float(entry_price - (entry_atr * atr_multiplier))
        exit_index: Optional[int] = None
        exit_reason: Optional[str] = None
        final_index = min(len(working) - 1, entry_index + time_stop_days - 1)

        for day_index in range(entry_index, final_index + 1):
            day_high = pd.to_numeric(pd.Series([working.at[day_index, "high"]]), errors="coerce").iloc[0]
            day_close = pd.to_numeric(pd.Series([working.at[day_index, "close"]]), errors="coerce").iloc[0]
            day_atr = pd.to_numeric(pd.Series([working.at[day_index, "atr14"]]), errors="coerce").iloc[0]

            if pd.notna(day_high) and pd.notna(day_atr) and day_atr > 0:
                trailing_stop = max(trailing_stop, float(day_high - (day_atr * atr_multiplier)))

            holding_period_bars = day_index - entry_index + 1
            if pd.notna(day_close) and day_close < trailing_stop:
                exit_index = day_index
                exit_reason = "atr_stop"
                break
            if holding_period_bars >= time_stop_days:
                exit_index = day_index
                exit_reason = "time_stop"
                break

        if exit_index is None or exit_reason is None:
            continue

        exit_price = pd.to_numeric(pd.Series([working.at[exit_index, "close"]]), errors="coerce").iloc[0]
        if pd.isna(exit_price):
            continue

        trade_slice = working.iloc[entry_index : exit_index + 1]
        min_low = pd.to_numeric(trade_slice["low"], errors="coerce").min()
        max_drawdown_pct = (
            max(0.0, float((entry_price - min_low) / entry_price * 100.0))
            if pd.notna(min_low)
            else 0.0
        )
        trade_return = float((exit_price - entry_price) / entry_price * 100.0)
        holding_period_bars = int(exit_index - entry_index + 1)

        trades.append(
            {
                "signal_date": working.at[signal_index, "date"],
                "entry_date": working.at[entry_index, "date"],
                "exit_date": working.at[exit_index, "date"],
                "entry_price": float(entry_price),
                "exit_price": float(exit_price),
                "return_pct": trade_return,
                "is_win": bool(trade_return > 0),
                "holding_period_bars": holding_period_bars,
                "max_drawdown_pct": round(max_drawdown_pct, 4),
                "exit_reason": exit_reason,
            }
        )
        if not allow_overlap:
            next_eligible_index = exit_index + 1

    return pd.DataFrame(trades)


def _evaluate_variant_ticker(
    ticker: str,
    frame: pd.DataFrame,
    *,
    variant: ExitVariant,
    allow_overlap: bool,
) -> tuple[Dict[str, object], pd.DataFrame]:
    signal_count = int(frame["entry_signal"].fillna(False).astype(bool).sum())
    if variant.exit_policy == "fixed_hold_5d":
        trades_df = _backtest_fixed_hold(frame, signal_column="entry_signal", hold_period=5, allow_overlap=allow_overlap)
    elif variant.exit_policy == "atr_trailing_stop":
        trades_df = _backtest_atr_trailing_stop(
            frame,
            signal_column="entry_signal",
            atr_multiplier=float(variant.atr_multiplier or 2.5),
            time_stop_days=int(variant.time_stop_days or 15),
            allow_overlap=allow_overlap,
        )
    else:  # pragma: no cover - defensive
        raise ValueError(f"Unsupported exit policy: {variant.exit_policy}")

    if trades_df.empty:
        ticker_row = {
            "variant_id": variant.variant_id,
            "variant_label": variant.label,
            "ticker": ticker,
            "entry_signals": signal_count,
            "total_trades": 0,
            "avg_return_per_trade": 0.0,
            "avg_win_rate": 0.0,
            "avg_holding_period_actual": 0.0,
            "max_drawdown_per_trade": 0.0,
            "coverage_collapsed": bool(signal_count > 0),
        }
        return ticker_row, trades_df

    ticker_row = {
        "variant_id": variant.variant_id,
        "variant_label": variant.label,
        "ticker": ticker,
        "entry_signals": signal_count,
        "total_trades": int(len(trades_df)),
        "avg_return_per_trade": round(float(trades_df["return_pct"].mean()), 4),
        "avg_win_rate": round(float(trades_df["is_win"].mean() * 100.0), 4),
        "avg_holding_period_actual": round(float(trades_df["holding_period_bars"].mean()), 4),
        "max_drawdown_per_trade": round(float(trades_df["max_drawdown_pct"].mean()), 4),
        "coverage_collapsed": False,
    }
    trades_df = trades_df.copy()
    trades_df["ticker"] = ticker
    trades_df["variant_id"] = variant.variant_id
    return ticker_row, trades_df


def _summarize_variant(
    frame: pd.DataFrame,
    per_ticker_df: pd.DataFrame,
    trades_df: pd.DataFrame,
    variant: ExitVariant,
) -> Dict[str, object]:
    active_by_date = (
        frame.groupby("date")
        .agg(
            active_ticker_count=("active_selected", "sum"),
            available_ticker_count=("available_ticker_count", "max"),
        )
        .reset_index()
    )
    collapse_tickers = (
        per_ticker_df.loc[per_ticker_df["coverage_collapsed"].astype(bool), "ticker"].astype(str).tolist()
    )
    summary = {
        "variant_id": variant.variant_id,
        "variant_label": variant.label,
        "layer_3_active": bool(variant.layer_3_active),
        "exit_policy": variant.exit_policy,
        "atr_multiplier": variant.atr_multiplier,
        "time_stop_days": variant.time_stop_days,
        "active_ticker_count_median": round(float(active_by_date["active_ticker_count"].median()), 4),
        "active_ticker_count_min": int(active_by_date["active_ticker_count"].min()),
        "active_ticker_count_max": int(active_by_date["active_ticker_count"].max()),
        "active_ticker_count_mean": round(float(active_by_date["active_ticker_count"].mean()), 4),
        "active_single_ticker_day_pct": round(
            float(active_by_date["active_ticker_count"].eq(1).mean() * 100.0), 4
        ),
        "total_signals": int(per_ticker_df["entry_signals"].sum()),
        "total_trades": int(len(trades_df)),
        "avg_return_per_trade": round(float(trades_df["return_pct"].mean()), 4) if not trades_df.empty else 0.0,
        "avg_win_rate": round(float(trades_df["is_win"].mean() * 100.0), 4) if not trades_df.empty else 0.0,
        "avg_holding_period_actual": round(float(trades_df["holding_period_bars"].mean()), 4)
        if not trades_df.empty
        else 0.0,
        "max_drawdown_per_trade": round(float(trades_df["max_drawdown_pct"].mean()), 4)
        if not trades_df.empty
        else 0.0,
        "tickers_with_coverage_collapse": int(len(collapse_tickers)),
        "coverage_collapse_tickers": collapse_tickers,
    }
    risk, reason = _classify_sample_adequacy_risk(
        {
            "active_ticker_count_median": summary["active_ticker_count_median"],
            "active_single_ticker_day_pct": summary["active_single_ticker_day_pct"],
            "total_trades": summary["total_trades"],
            "tickers_with_coverage_collapse": summary["tickers_with_coverage_collapse"],
        },
        universe_max=int(active_by_date["available_ticker_count"].max()),
    )
    summary["sample_adequacy_risk"] = risk
    summary["sample_adequacy_reason"] = reason
    return summary


def _layer5_integration_decision(variant_df: pd.DataFrame) -> Dict[str, object]:
    baseline = variant_df.loc[variant_df["variant_id"] == "baseline_fixed_hold_5d"]
    atr_variant = variant_df.loc[variant_df["variant_id"] == "atr_trailing_stop_no_layer3"]
    if baseline.empty or atr_variant.empty:
        return {
            "atr_trailing_better_than_fixed_hold": False,
            "layer_5_usable_as_integration_layer": False,
            "reason": "Baseline or ATR variant row is missing.",
        }

    baseline_row = baseline.iloc[0]
    atr_row = atr_variant.iloc[0]
    better = bool(float(atr_row["avg_return_per_trade"]) > float(baseline_row["avg_return_per_trade"]))
    usable = bool(
        int(atr_row["tickers_with_coverage_collapse"]) == 0
        and str(atr_row["sample_adequacy_risk"]) != "high"
    )
    reason = (
        "ATR trailing stop beats fixed hold 5 days on average return per trade."
        if better
        else "ATR trailing stop does not beat fixed hold 5 days on average return per trade in this first integration pass."
    )
    return {
        "atr_trailing_better_than_fixed_hold": better,
        "layer_5_usable_as_integration_layer": usable,
        "reason": reason,
    }


def run_phase_5_atr_trailing_stop(
    *,
    stock_indicator_master_file: Path,
    ihsg_indicator_master_file: Path,
    output_dir: Path,
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
    prepared_frame = _compute_exit_features(prepared_frame)
    variants = _build_variant_registry()

    per_ticker_rows: List[Dict[str, object]] = []
    variant_rows: List[Dict[str, object]] = []
    trade_frames: List[pd.DataFrame] = []

    for variant in variants:
        variant_frame = _apply_variant(prepared_frame, variant)
        variant_frame["variant_id"] = variant.variant_id
        variant_frame["variant_label"] = variant.label

        ticker_rows: List[Dict[str, object]] = []
        variant_trade_frames: List[pd.DataFrame] = []
        for ticker, group in variant_frame.groupby("ticker"):
            ticker_row, ticker_trades = _evaluate_variant_ticker(
                ticker,
                group.copy(),
                variant=variant,
                allow_overlap=allow_overlap,
            )
            ticker_rows.append(ticker_row)
            if not ticker_trades.empty:
                variant_trade_frames.append(ticker_trades)

        per_ticker_df = pd.DataFrame(ticker_rows).reindex(columns=PER_TICKER_COLUMNS)
        trades_df = (
            pd.concat(variant_trade_frames, ignore_index=True)
            if variant_trade_frames
            else pd.DataFrame(
                columns=[
                    "ticker",
                    "variant_id",
                    "signal_date",
                    "entry_date",
                    "exit_date",
                    "entry_price",
                    "exit_price",
                    "return_pct",
                    "is_win",
                    "holding_period_bars",
                    "max_drawdown_pct",
                    "exit_reason",
                ]
            )
        )
        per_ticker_rows.extend(per_ticker_df.to_dict(orient="records"))
        trade_frames.append(trades_df)
        variant_rows.append(_summarize_variant(variant_frame, per_ticker_df, trades_df, variant))

    variant_df = pd.DataFrame(variant_rows).reindex(columns=VARIANT_SUMMARY_COLUMNS)
    per_ticker_df = pd.DataFrame(per_ticker_rows).reindex(columns=PER_TICKER_COLUMNS)
    all_trades_df = pd.concat(trade_frames, ignore_index=True) if trade_frames else pd.DataFrame()
    decision = _layer5_integration_decision(variant_df)

    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "phase_5_atr_trailing_stop_summary.json"
    report_path = output_dir / "phase_5_atr_trailing_stop_report.txt"
    per_ticker_path = output_dir / "phase_5_atr_trailing_stop_per_ticker.csv"
    trades_path = output_dir / "phase_5_atr_trailing_stop_trades.csv"

    per_ticker_df.to_csv(per_ticker_path, index=False)
    all_trades_df.to_csv(trades_path, index=False)

    summary_payload = {
        "phase": "phase_5_atr_trailing_stop",
        "status": "completed",
        "generated_at": _now_iso(),
        "source_files": {
            "stock_indicator_master_file": str(stock_indicator_master_file),
            "ihsg_indicator_master_file": str(ihsg_indicator_master_file),
            "baseline_config": str(baseline_source) if baseline_source else None,
            "metadata_file": str(metadata_file) if metadata_file is not None else None,
        },
        "layer_3_context": {
            "layer_3_status": "optional_integration_layer",
            "layer_3_default_active": False,
            "layer_3_toggle_rule": "RSI14 >= 50 AND RSI14 <= 70",
        },
        "atr_price_basis_policy": {
            "status": "temporary_not_final",
            "policy_label": "raw_ohlc_from_rebuild_dataset",
            "atr_definition": "ATR14 simple rolling mean of true range from raw high/low/close.",
            "note": "Policy ATR final will be frozen at walk-forward, not in this integration pass."
        },
        "layer_5_status": "experimental_integration_layer",
        "layer_5_final_validation_frozen": False,
        "variant_results": variant_df.to_dict(orient="records"),
        "integration_decision": decision,
        "warnings": [*baseline_warnings, *metadata_warnings],
    }
    summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    report_lines = [
        "Phase 5 - ATR Trailing Stop",
        "============================",
        "",
        "Layer 2 active policy:",
        "- Layer1 bullish AND return_20d > 0 AND close > ema50",
        "",
        "Layer 3 status:",
        "- optional_integration_layer",
        "- default_active = false",
        "",
        "ATR basis policy for this pass:",
        "- raw OHLC from rebuild dataset",
        "- ATR14 = simple rolling mean of true range",
        "- final ATR policy frozen later at walk-forward",
        "",
        "Variant results:",
    ]
    for _, row in variant_df.iterrows():
        report_lines.append(
            f"- {row['variant_id']}: trades={row['total_trades']}, avg_return={row['avg_return_per_trade']}, "
            f"avg_win_rate={row['avg_win_rate']}, avg_holding_period={row['avg_holding_period_actual']}, "
            f"avg_max_drawdown_per_trade={row['max_drawdown_per_trade']}, collapse={row['tickers_with_coverage_collapse']}, "
            f"sample={row['sample_adequacy_risk']}"
        )
    report_lines.extend(
        [
            "",
            "Decision:",
            f"- atr_trailing_better_than_fixed_hold = {decision['atr_trailing_better_than_fixed_hold']}",
            f"- layer_5_usable_as_integration_layer = {decision['layer_5_usable_as_integration_layer']}",
            f"- reason = {decision['reason']}",
            "",
            "Official next action:",
            "- Open Layer 4 sizing next. Do not run an extra confirmation pass for Layer 5 before touching Layer 4.",
        ]
    )
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    return {
        "summary_path": summary_path,
        "report_path": report_path,
        "per_ticker_path": per_ticker_path,
        "trades_path": trades_path,
        "summary": summary_payload,
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase 5 ATR trailing stop integration.")
    parser.add_argument(
        "--stock-indicator-master-file",
        default="data/indicator_master/stock_indicator_master.csv",
        help="Stock indicator master CSV for the frozen rebuild universe.",
    )
    parser.add_argument(
        "--ihsg-indicator-master-file",
        default="data/indicator_master/IHSG_indicator_master.csv",
        help="IHSG indicator master CSV with frozen Layer 1 inputs.",
    )
    parser.add_argument("--output-dir", default="output", help="Directory for output artifacts.")
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
    run_phase_5_atr_trailing_stop(
        stock_indicator_master_file=Path(args.stock_indicator_master_file),
        ihsg_indicator_master_file=Path(args.ihsg_indicator_master_file),
        output_dir=Path(args.output_dir),
        allow_overlap=bool(args.allow_overlap),
        baseline_config=Path(args.baseline_config) if args.baseline_config else None,
        metadata_file=Path(args.metadata_file) if args.metadata_file else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
