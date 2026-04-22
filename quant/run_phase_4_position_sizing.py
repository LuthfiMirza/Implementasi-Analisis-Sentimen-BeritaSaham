"""Evaluate Layer 4 fixed-fractional position sizing on top of Layer 5 ATR trailing stop."""

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
from quant.run_phase_2_relative_strength_stock_selection import _classify_sample_adequacy_risk  # noqa: E402
from quant.run_phase_5_atr_trailing_stop import (  # noqa: E402
    _apply_variant,
    _backtest_atr_trailing_stop,
    _compute_exit_features,
)


VARIANT_SUMMARY_COLUMNS = [
    "variant_id",
    "variant_label",
    "layer_3_active",
    "position_sizing_active",
    "risk_per_trade_pct",
    "max_position_pct",
    "initial_capital",
    "total_trades",
    "portfolio_return_pct",
    "portfolio_ending_value",
    "portfolio_max_drawdown_pct",
    "avg_return_per_trade",
    "avg_win_rate",
    "avg_holding_period_actual",
    "avg_position_size_pct",
    "cap_hit_rate_pct",
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
class PositionSizingVariant:
    variant_id: str
    label: str
    layer_3_active: bool
    position_sizing_active: bool
    risk_per_trade_pct: Optional[float]
    max_position_pct: Optional[float]
    initial_capital: float


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_variant_registry() -> List[PositionSizingVariant]:
    return [
        PositionSizingVariant(
            variant_id="atr_trailing_stop_no_layer3_unsized",
            label="ATR trailing stop without Layer 3 (unsized baseline)",
            layer_3_active=False,
            position_sizing_active=False,
            risk_per_trade_pct=None,
            max_position_pct=None,
            initial_capital=100_000_000.0,
        ),
        PositionSizingVariant(
            variant_id="atr_trailing_stop_no_layer3_sized",
            label="ATR trailing stop without Layer 3 + fixed fractional sizing",
            layer_3_active=False,
            position_sizing_active=True,
            risk_per_trade_pct=2.0,
            max_position_pct=10.0,
            initial_capital=100_000_000.0,
        ),
        PositionSizingVariant(
            variant_id="atr_trailing_stop_with_layer3_toggle_sized",
            label="ATR trailing stop with Layer 3 toggle + fixed fractional sizing",
            layer_3_active=True,
            position_sizing_active=True,
            risk_per_trade_pct=2.0,
            max_position_pct=10.0,
            initial_capital=100_000_000.0,
        ),
    ]


def _build_entry_exit_frame(
    stock_indicator_master_file: Path,
    ihsg_indicator_master_file: Path,
    *,
    baseline_payload: Dict[str, object],
    metadata_lookup: Dict[str, Dict[str, object]],
) -> pd.DataFrame:
    prepared_frame = _prepare_layer1_signal_frame(
        stock_indicator_master_file,
        ihsg_indicator_master_file,
        baseline_payload=baseline_payload,
        metadata_lookup=metadata_lookup,
    )
    return _compute_exit_features(prepared_frame)


def _apply_entry_variant(frame: pd.DataFrame, variant: PositionSizingVariant) -> pd.DataFrame:
    from quant.run_phase_5_atr_trailing_stop import ExitVariant  # local import to keep scope tight

    exit_variant = ExitVariant(
        variant_id="atr_variant",
        label="atr_variant",
        layer_3_active=variant.layer_3_active,
        exit_policy="atr_trailing_stop",
        atr_multiplier=2.5,
        time_stop_days=15,
    )
    return _apply_variant(frame, exit_variant)


def _evaluate_variant_ticker(
    ticker: str,
    frame: pd.DataFrame,
    *,
    layer_3_active: bool,
    allow_overlap: bool,
) -> tuple[Dict[str, object], pd.DataFrame]:
    signal_count = int(frame["entry_signal"].fillna(False).astype(bool).sum())
    trades_df = _backtest_atr_trailing_stop(
        frame,
        signal_column="entry_signal",
        atr_multiplier=2.5,
        time_stop_days=15,
        allow_overlap=allow_overlap,
    )
    if trades_df.empty:
        ticker_row = {
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
    trades_df["layer_3_active"] = layer_3_active
    return ticker_row, trades_df


def _attach_entry_context(frame: pd.DataFrame, trades_df: pd.DataFrame) -> pd.DataFrame:
    if trades_df.empty:
        return trades_df.copy()
    entry_context = frame[["ticker", "date", "open", "atr14"]].rename(
        columns={"date": "entry_date", "open": "entry_open", "atr14": "entry_atr14"}
    )
    merged = trades_df.merge(entry_context, on=["ticker", "entry_date"], how="left")
    merged["initial_stop_price"] = merged["entry_price"] - (merged["entry_atr14"] * 2.5)
    merged["risk_per_share"] = merged["entry_price"] - merged["initial_stop_price"]
    return merged


def _apply_position_sizing(trades_df: pd.DataFrame, variant: PositionSizingVariant) -> tuple[pd.DataFrame, Dict[str, float]]:
    if trades_df.empty:
        return trades_df.copy(), {
            "portfolio_return_pct": 0.0,
            "portfolio_ending_value": float(variant.initial_capital),
            "portfolio_max_drawdown_pct": 0.0,
            "avg_position_size_pct": 0.0,
            "cap_hit_rate_pct": 0.0,
        }

    working = trades_df.sort_values(["entry_date", "ticker"]).reset_index(drop=True).copy()
    portfolio_value = float(variant.initial_capital)
    peak_value = float(variant.initial_capital)
    position_pcts: List[float] = []
    cap_hits: List[bool] = []
    ending_values: List[float] = []

    for idx, row in working.iterrows():
        if variant.position_sizing_active:
            risk_per_trade_value = portfolio_value * float(variant.risk_per_trade_pct or 0.0) / 100.0
            risk_per_share = float(row.get("risk_per_share") or 0.0)
            entry_price = float(row.get("entry_price") or 0.0)
            if risk_per_share <= 0 or entry_price <= 0:
                position_pct = 0.0
                position_value = 0.0
                cap_hit = False
            else:
                raw_position_value = (risk_per_trade_value / risk_per_share) * entry_price
                max_position_value = portfolio_value * float(variant.max_position_pct or 0.0) / 100.0
                position_value = min(raw_position_value, max_position_value)
                position_pct = (position_value / portfolio_value * 100.0) if portfolio_value > 0 else 0.0
                cap_hit = raw_position_value > max_position_value + 1e-9
        else:
            position_pct = 100.0
            position_value = portfolio_value
            cap_hit = False

        pnl_value = position_value * float(row["return_pct"]) / 100.0
        portfolio_value += pnl_value
        peak_value = max(peak_value, portfolio_value)
        portfolio_drawdown_pct = max(0.0, (peak_value - portfolio_value) / peak_value * 100.0) if peak_value > 0 else 0.0

        working.at[idx, "position_size_pct"] = round(position_pct, 4)
        working.at[idx, "position_value"] = round(position_value, 4)
        working.at[idx, "pnl_value"] = round(pnl_value, 4)
        working.at[idx, "portfolio_value_after_trade"] = round(portfolio_value, 4)
        working.at[idx, "portfolio_drawdown_pct"] = round(portfolio_drawdown_pct, 4)
        working.at[idx, "cap_hit"] = bool(cap_hit)

        position_pcts.append(position_pct)
        cap_hits.append(bool(cap_hit))
        ending_values.append(portfolio_value)

    portfolio_return_pct = (
        (float(ending_values[-1]) / float(variant.initial_capital) - 1.0) * 100.0
        if variant.initial_capital > 0
        else 0.0
    )
    metrics = {
        "portfolio_return_pct": round(float(portfolio_return_pct), 4),
        "portfolio_ending_value": round(float(ending_values[-1]), 4),
        "portfolio_max_drawdown_pct": round(float(working["portfolio_drawdown_pct"].max()), 4),
        "avg_position_size_pct": round(float(pd.Series(position_pcts).mean()), 4),
        "cap_hit_rate_pct": round(float(pd.Series(cap_hits).mean() * 100.0), 4),
    }
    return working, metrics


def _summarize_variant(
    frame: pd.DataFrame,
    per_ticker_df: pd.DataFrame,
    sized_trades_df: pd.DataFrame,
    variant: PositionSizingVariant,
    sizing_metrics: Dict[str, float],
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
        "position_sizing_active": bool(variant.position_sizing_active),
        "risk_per_trade_pct": variant.risk_per_trade_pct,
        "max_position_pct": variant.max_position_pct,
        "initial_capital": variant.initial_capital,
        "total_trades": int(len(sized_trades_df)),
        "portfolio_return_pct": sizing_metrics["portfolio_return_pct"],
        "portfolio_ending_value": sizing_metrics["portfolio_ending_value"],
        "portfolio_max_drawdown_pct": sizing_metrics["portfolio_max_drawdown_pct"],
        "avg_return_per_trade": round(float(sized_trades_df["return_pct"].mean()), 4) if not sized_trades_df.empty else 0.0,
        "avg_win_rate": round(float(sized_trades_df["is_win"].mean() * 100.0), 4) if not sized_trades_df.empty else 0.0,
        "avg_holding_period_actual": round(float(sized_trades_df["holding_period_bars"].mean()), 4)
        if not sized_trades_df.empty
        else 0.0,
        "avg_position_size_pct": sizing_metrics["avg_position_size_pct"],
        "cap_hit_rate_pct": sizing_metrics["cap_hit_rate_pct"],
        "max_drawdown_per_trade": round(float(sized_trades_df["max_drawdown_pct"].mean()), 4)
        if not sized_trades_df.empty
        else 0.0,
        "tickers_with_coverage_collapse": int(len(collapse_tickers)),
        "coverage_collapse_tickers": collapse_tickers,
    }
    risk, reason = _classify_sample_adequacy_risk(
        {
            "active_ticker_count_median": round(float(active_by_date["active_ticker_count"].median()), 4),
            "active_single_ticker_day_pct": round(float(active_by_date["active_ticker_count"].eq(1).mean() * 100.0), 4),
            "total_trades": summary["total_trades"],
            "tickers_with_coverage_collapse": summary["tickers_with_coverage_collapse"],
        },
        universe_max=int(active_by_date["available_ticker_count"].max()),
    )
    summary["sample_adequacy_risk"] = risk
    summary["sample_adequacy_reason"] = reason
    return summary


def _layer4_integration_decision(variant_df: pd.DataFrame) -> Dict[str, object]:
    unsized = variant_df.loc[variant_df["variant_id"] == "atr_trailing_stop_no_layer3_unsized"]
    sized = variant_df.loc[variant_df["variant_id"] == "atr_trailing_stop_no_layer3_sized"]
    if unsized.empty or sized.empty:
        return {
            "layer_4_usable_as_integration_layer": False,
            "reason": "Unsized or sized baseline row is missing.",
        }

    sized_row = sized.iloc[0]
    usable = bool(
        int(sized_row["tickers_with_coverage_collapse"]) == 0
        and str(sized_row["sample_adequacy_risk"]) != "high"
    )
    return {
        "layer_4_usable_as_integration_layer": usable,
        "reason": "Layer 4 first pass completed; next action is walk-forward preparation with sizing active.",
    }


def run_phase_4_position_sizing(
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
    prepared_frame = _build_entry_exit_frame(
        stock_indicator_master_file,
        ihsg_indicator_master_file,
        baseline_payload=baseline_payload,
        metadata_lookup=metadata_lookup,
    )
    variants = _build_variant_registry()

    per_ticker_rows: List[Dict[str, object]] = []
    variant_rows: List[Dict[str, object]] = []
    trade_frames: List[pd.DataFrame] = []

    for variant in variants:
        variant_frame = _apply_entry_variant(prepared_frame, variant)
        variant_frame["variant_id"] = variant.variant_id
        variant_frame["variant_label"] = variant.label

        ticker_rows: List[Dict[str, object]] = []
        variant_trade_frames: List[pd.DataFrame] = []
        for ticker, group in variant_frame.groupby("ticker"):
            ticker_row, ticker_trades = _evaluate_variant_ticker(
                ticker,
                group.copy(),
                layer_3_active=variant.layer_3_active,
                allow_overlap=allow_overlap,
            )
            ticker_row["variant_id"] = variant.variant_id
            ticker_row["variant_label"] = variant.label
            ticker_rows.append(ticker_row)
            if not ticker_trades.empty:
                variant_trade_frames.append(ticker_trades)

        per_ticker_df = pd.DataFrame(ticker_rows).reindex(columns=PER_TICKER_COLUMNS)
        trades_df = pd.concat(variant_trade_frames, ignore_index=True) if variant_trade_frames else pd.DataFrame()
        trades_df = _attach_entry_context(variant_frame, trades_df)
        sized_trades_df, sizing_metrics = _apply_position_sizing(trades_df, variant)
        per_ticker_rows.extend(per_ticker_df.to_dict(orient="records"))
        trade_frames.append(sized_trades_df)
        variant_rows.append(_summarize_variant(variant_frame, per_ticker_df, sized_trades_df, variant, sizing_metrics))

    variant_df = pd.DataFrame(variant_rows).reindex(columns=VARIANT_SUMMARY_COLUMNS)
    per_ticker_df = pd.DataFrame(per_ticker_rows).reindex(columns=PER_TICKER_COLUMNS)
    all_trades_df = pd.concat(trade_frames, ignore_index=True) if trade_frames else pd.DataFrame()
    decision = _layer4_integration_decision(variant_df)

    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "phase_4_position_sizing_summary.json"
    report_path = output_dir / "phase_4_position_sizing_report.txt"
    per_ticker_path = output_dir / "phase_4_position_sizing_per_ticker.csv"
    trades_path = output_dir / "phase_4_position_sizing_trades.csv"

    per_ticker_df.to_csv(per_ticker_path, index=False)
    all_trades_df.to_csv(trades_path, index=False)

    summary_payload = {
        "phase": "phase_4_position_sizing",
        "status": "completed",
        "generated_at": _now_iso(),
        "source_files": {
            "stock_indicator_master_file": str(stock_indicator_master_file),
            "ihsg_indicator_master_file": str(ihsg_indicator_master_file),
            "baseline_config": str(baseline_source) if baseline_source else None,
            "metadata_file": str(metadata_file) if metadata_file is not None else None,
        },
        "position_sizing_policy": {
            "risk_per_trade_pct": 2.0,
            "max_position_pct": 10.0,
            "initial_capital": 100_000_000.0,
            "note": "Layer 4 first pass uses sequential portfolio compounding over realized trades; overlapping portfolio allocation is not yet modeled separately."
        },
        "layer_3_context": {
            "layer_3_status": "optional_integration_layer",
            "layer_3_default_active": False,
        },
        "variant_results": variant_df.to_dict(orient="records"),
        "integration_decision": decision,
        "warnings": [*baseline_warnings, *metadata_warnings],
    }
    summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    report_lines = [
        "Phase 4 - Position Sizing",
        "==========================",
        "",
        "Position sizing policy:",
        "- risk_per_trade = 2% portfolio",
        "- max_position = 10% portfolio",
        "- initial_capital = 100,000,000 IDR notional",
        "",
        "Variant results:",
    ]
    for _, row in variant_df.iterrows():
        report_lines.append(
            f"- {row['variant_id']}: trades={row['total_trades']}, portfolio_return={row['portfolio_return_pct']}, "
            f"portfolio_max_dd={row['portfolio_max_drawdown_pct']}, avg_return={row['avg_return_per_trade']}, "
            f"avg_win_rate={row['avg_win_rate']}, avg_holding={row['avg_holding_period_actual']}, "
            f"avg_position_size_pct={row['avg_position_size_pct']}, cap_hit_rate={row['cap_hit_rate_pct']}, sample={row['sample_adequacy_risk']}"
        )
    report_lines.extend(
        [
            "",
            "Decision:",
            f"- layer_4_usable_as_integration_layer = {decision['layer_4_usable_as_integration_layer']}",
            f"- reason = {decision['reason']}",
            "",
            "Official next action:",
            "- Open walk-forward validation next with Layer 3 kept optional and ATR policy still frozen later at walk-forward.",
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
    parser = argparse.ArgumentParser(description="Run Phase 4 position sizing on top of Layer 5 ATR trailing stop.")
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
    run_phase_4_position_sizing(
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
