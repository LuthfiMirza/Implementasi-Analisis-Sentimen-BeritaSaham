"""Evaluate the Layer 1 IHSG market regime filter on top of the indicator master table."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

if __package__ is None or __package__ == "":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.phase_a import apply_market_regime_gate, backtest_signal_frame  # noqa: E402
from quant.phase_a_baseline import (  # noqa: E402
    load_optional_metadata_lookup,
    load_phase_a_baseline,
    resolve_phase_a_runtime_settings,
)


PER_TICKER_COLUMNS = [
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _load_indicator_master(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise ValueError(f"Indicator master file not found: {path}")

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
        "ihsg_regime_bullish",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Indicator master file missing required columns: {missing}")
    return frame.sort_values(["ticker", "date"]).reset_index(drop=True)


def _build_phase1_signal_frame(
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

    signal_column = "phase_1_signal_strict" if strict_mode else "phase_1_signal"
    if strict_mode:
        working[signal_column] = (
            minimum_signal
            & working["ema50_slope_up"]
            & working["close"].gt(working["open"])
        ).fillna(False)
    else:
        working[signal_column] = minimum_signal.fillna(False)

    working = apply_market_regime_gate(
        working,
        signal_column=signal_column,
        regime_column="ihsg_regime_bullish",
        gated_signal_column=f"{signal_column}_regime_filtered",
        skipped_column="market_regime_entry_skipped",
    )
    return working


def _evaluate_ticker_frame(
    ticker: str,
    frame: pd.DataFrame,
    *,
    hold_period: int,
    allow_overlap: bool,
    threshold: float,
    strict_mode: bool,
) -> Dict[str, object]:
    signal_frame = _build_phase1_signal_frame(frame, threshold=threshold, strict_mode=strict_mode)
    signal_column = "phase_1_signal_strict" if strict_mode else "phase_1_signal"
    filtered_signal_column = f"{signal_column}_regime_filtered"

    pre_signal_count = int(signal_frame[signal_column].fillna(False).astype(bool).sum())
    post_signal_count = int(signal_frame[filtered_signal_column].fillna(False).astype(bool).sum())
    skipped_signal_count = int(signal_frame["market_regime_entry_skipped"].fillna(False).astype(bool).sum())

    pre_result = backtest_signal_frame(
        signal_frame,
        signal_column=signal_column,
        hold_period=hold_period,
        allow_overlap=allow_overlap,
    )
    post_result = backtest_signal_frame(
        signal_frame,
        signal_column=filtered_signal_column,
        hold_period=hold_period,
        allow_overlap=allow_overlap,
    )

    bullish_days = int(
        pd.Series(signal_frame["ihsg_regime_bullish"], index=signal_frame.index, dtype="boolean")
        .fillna(False)
        .astype(bool)
        .sum()
    )
    non_bullish_days = int(len(signal_frame) - bullish_days)
    signal_retention_pct = round((post_signal_count / pre_signal_count) * 100.0, 4) if pre_signal_count else 0.0
    trade_retention_pct = (
        round((post_result.total_trades / pre_result.total_trades) * 100.0, 4)
        if pre_result.total_trades
        else 0.0
    )

    return {
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


def run_phase_1_market_regime_filter(
    *,
    indicator_master_file: Path,
    output_dir: Path,
    hold_period: int = 5,
    allow_overlap: bool = False,
    baseline_config: Optional[Path] = None,
    metadata_file: Optional[Path] = None,
) -> Dict[str, object]:
    frame = _load_indicator_master(indicator_master_file)
    baseline_payload, baseline_warnings, baseline_source = load_phase_a_baseline(baseline_config=baseline_config)
    metadata_lookup, metadata_warnings = load_optional_metadata_lookup(metadata_file)
    per_ticker_rows: List[Dict[str, object]] = []

    for ticker, group in frame.groupby("ticker"):
        runtime = resolve_phase_a_runtime_settings(
            ticker=ticker,
            baseline_config=baseline_payload,
            metadata_lookup=metadata_lookup,
        )
        per_ticker_rows.append(
            _evaluate_ticker_frame(
                ticker=ticker,
                frame=group.copy(),
                hold_period=hold_period,
                allow_overlap=allow_overlap,
                threshold=float(runtime["threshold"]),
                strict_mode=bool(runtime["strict_mode"]),
            )
        )

    per_ticker_df = pd.DataFrame(per_ticker_rows).reindex(columns=PER_TICKER_COLUMNS)
    output_dir.mkdir(parents=True, exist_ok=True)
    per_ticker_path = output_dir / "phase_1_market_regime_filter_per_ticker.csv"
    per_ticker_df.to_csv(per_ticker_path, index=False)

    ihsg_unique = (
        frame[["date", "ihsg_regime_bullish"]]
        .drop_duplicates(subset=["date"], keep="last")
        .sort_values("date")
        .reset_index(drop=True)
    )
    bullish_days = int(
        pd.Series(ihsg_unique["ihsg_regime_bullish"], index=ihsg_unique.index, dtype="boolean")
        .fillna(False)
        .astype(bool)
        .sum()
    )
    total_days = int(len(ihsg_unique))
    non_bullish_days = total_days - bullish_days

    summary_payload = {
        "phase": "phase_1_market_regime_filter",
        "status": "completed",
        "generated_at": _now_iso(),
        "source_files": {
            "indicator_master_file": str(indicator_master_file),
            "baseline_config": str(baseline_source) if baseline_source else None,
            "metadata_file": str(metadata_file) if metadata_file is not None else None,
        },
        "official_definition": {
            "market_regime_bullish": "ihsg_adj_close > ihsg_ema200",
            "non_bullish_behavior": "skip_new_entries",
        },
        "regime_day_distribution": {
            "total_days": total_days,
            "bullish_days": bullish_days,
            "non_bullish_days": non_bullish_days,
            "bullish_day_pct": round((bullish_days / total_days) * 100.0, 4) if total_days else 0.0,
            "non_bullish_day_pct": round((non_bullish_days / total_days) * 100.0, 4)
            if total_days
            else 0.0,
        },
        "signals_before_after": {
            "pre_filter_signals": int(per_ticker_df["pre_filter_signals"].sum()),
            "post_filter_signals": int(per_ticker_df["post_filter_signals"].sum()),
            "skipped_signals": int(per_ticker_df["skipped_signals"].sum()),
        },
        "trades_before_after": {
            "pre_filter_total_trades": int(per_ticker_df["pre_filter_total_trades"].sum()),
            "post_filter_total_trades": int(per_ticker_df["post_filter_total_trades"].sum()),
        },
        "coverage": {
            "tickers_with_pre_filter_signals": int(per_ticker_df["pre_filter_signals"].gt(0).sum()),
            "tickers_with_post_filter_signals": int(per_ticker_df["post_filter_signals"].gt(0).sum()),
            "tickers_with_coverage_collapse": int(per_ticker_df["coverage_collapsed"].astype(bool).sum()),
            "trade_retention_pct_median": round(
                float(per_ticker_df["trade_retention_pct"].median()) if not per_ticker_df.empty else 0.0,
                4,
            ),
        },
        "quality_delta": {
            "avg_pre_filter_win_rate": round(
                float(per_ticker_df["pre_filter_win_rate"].mean()) if not per_ticker_df.empty else 0.0,
                4,
            ),
            "avg_post_filter_win_rate": round(
                float(per_ticker_df["post_filter_win_rate"].mean()) if not per_ticker_df.empty else 0.0,
                4,
            ),
            "avg_delta_win_rate": round(
                float(per_ticker_df["delta_win_rate"].mean()) if not per_ticker_df.empty else 0.0,
                4,
            ),
            "avg_pre_filter_average_return": round(
                float(per_ticker_df["pre_filter_average_return"].mean()) if not per_ticker_df.empty else 0.0,
                4,
            ),
            "avg_post_filter_average_return": round(
                float(per_ticker_df["post_filter_average_return"].mean()) if not per_ticker_df.empty else 0.0,
                4,
            ),
            "avg_delta_average_return": round(
                float(per_ticker_df["delta_average_return"].mean()) if not per_ticker_df.empty else 0.0,
                4,
            ),
        },
        "usability_decision": {
            "layer_1_usable": bool(
                int(per_ticker_df["post_filter_signals"].sum()) > 0
                and int(per_ticker_df["pre_filter_signals"].sum()) > 0
            ),
            "coverage_collapse_detected": bool(per_ticker_df["coverage_collapsed"].astype(bool).any()),
        },
        "warnings": [*baseline_warnings, *metadata_warnings],
    }
    summary_path = output_dir / "phase_1_market_regime_filter_summary.json"
    summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    report_lines = [
        "Phase 1 - Market Regime Filter",
        "===============================",
        "",
        "Definition:",
        "- bullish when ihsg_adj_close > ihsg_ema200",
        "- non-bullish skips new entries",
        "",
        "Regime day distribution:",
        f"- bullish_days = {summary_payload['regime_day_distribution']['bullish_days']}",
        f"- non_bullish_days = {summary_payload['regime_day_distribution']['non_bullish_days']}",
        f"- bullish_day_pct = {summary_payload['regime_day_distribution']['bullish_day_pct']}",
        "",
        "Signals before vs after:",
        f"- pre_filter_signals = {summary_payload['signals_before_after']['pre_filter_signals']}",
        f"- post_filter_signals = {summary_payload['signals_before_after']['post_filter_signals']}",
        f"- skipped_signals = {summary_payload['signals_before_after']['skipped_signals']}",
        "",
        "Trades before vs after:",
        f"- pre_filter_total_trades = {summary_payload['trades_before_after']['pre_filter_total_trades']}",
        f"- post_filter_total_trades = {summary_payload['trades_before_after']['post_filter_total_trades']}",
        f"- tickers_with_coverage_collapse = {summary_payload['coverage']['tickers_with_coverage_collapse']}",
        "",
        "Quality delta:",
        f"- avg_delta_win_rate = {summary_payload['quality_delta']['avg_delta_win_rate']}",
        f"- avg_delta_average_return = {summary_payload['quality_delta']['avg_delta_average_return']}",
        "",
        f"Layer 1 usable: {summary_payload['usability_decision']['layer_1_usable']}",
    ]
    report_path = output_dir / "phase_1_market_regime_filter_report.txt"
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    return {
        "per_ticker_path": per_ticker_path,
        "summary_path": summary_path,
        "report_path": report_path,
        "summary": summary_payload,
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Phase 1 IHSG market regime filter evaluation.")
    parser.add_argument(
        "--indicator-master-file",
        default="data/indicator_master/stock_indicator_master.csv",
        help="Stock indicator master CSV with IHSG regime columns.",
    )
    parser.add_argument("--output-dir", default="output", help="Directory for Phase 1 artifacts.")
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
    run_phase_1_market_regime_filter(
        indicator_master_file=Path(args.indicator_master_file),
        output_dir=Path(args.output_dir),
        hold_period=int(args.hold_period),
        allow_overlap=bool(args.allow_overlap),
        baseline_config=Path(args.baseline_config) if args.baseline_config else None,
        metadata_file=Path(args.metadata_file) if args.metadata_file else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
