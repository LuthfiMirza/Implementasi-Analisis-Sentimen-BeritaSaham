#!/usr/bin/env python3
"""Compute technical, candlestick, volume, IHSG regime, and MFE/MAE excursion telemetry
for a batch of trades from the Laravel Trade Journal (`trades` table).

Usage:
    python3 compute_trade_indicators.py <input_json_path> <output_json_path>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    ma_up = up.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    ma_down = down.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = ma_up / ma_down.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def safe_round(val, digits: int = 2) -> float | None:
    if val is None or pd.isna(val) or np.isinf(val):
        return None
    return round(float(val), digits)


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: compute_trade_indicators.py <input_json> <output_json>", file=sys.stderr)
        sys.exit(1)

    in_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])

    trades = json.loads(in_path.read_text(encoding="utf-8"))
    if not trades:
        out_path.write_text("{}", encoding="utf-8")
        return

    tickers = sorted({str(t["ticker"]).upper().strip() for t in trades if t.get("ticker")})
    yf_symbols = [f"{t}.JK" for t in tickers] + ["^JKSE"]

    raw = yf.download(
        yf_symbols,
        start="2025-01-01",
        end="2026-11-20",
        progress=False,
        auto_adjust=False,
        group_by="ticker",
    )

    # Prepare IHSG dataframe
    ihsg = raw["^JKSE"].dropna(subset=["Close"]).copy()
    ihsg.index = ihsg.index.tz_localize(None).strftime("%Y-%m-%d")
    ihsg["ihsg_ret_1d"] = ihsg["Close"].pct_change() * 100.0
    ihsg["ihsg_ma20"] = ihsg["Close"].rolling(20, min_periods=5).mean()
    ihsg["ihsg_above_ma20"] = ihsg["Close"] >= ihsg["ihsg_ma20"]

    ticker_dfs: dict[str, pd.DataFrame] = {}
    for t in tickers:
        sym = f"{t}.JK"
        if sym not in raw.columns.get_level_values(0):
            continue
        d = raw[sym].dropna(subset=["Close"]).copy()
        if d.empty:
            continue
        d.index = d.index.tz_localize(None).strftime("%Y-%m-%d")
        d["ret_1d"] = d["Close"].pct_change() * 100.0
        d["ret_2d"] = d["Close"].pct_change(2) * 100.0
        d["dd_20d"] = (d["Close"] / d["Close"].rolling(20, min_periods=5).max() - 1.0) * 100.0
        d["lower_wick_pct"] = (d["Close"] - d["Low"]) / d["Low"].replace(0, np.nan) * 100.0
        body_top = np.maximum(d["Open"], d["Close"])
        d["upper_wick_pct"] = (d["High"] - body_top) / d["Close"].replace(0, np.nan) * 100.0
        d["body_pct"] = (d["Close"] - d["Open"]) / d["Open"].replace(0, np.nan) * 100.0
        d["rsi_14"] = compute_rsi(d["Close"], 14)
        d["vol_ma20"] = d["Volume"].rolling(20, min_periods=5).mean()
        d["vol_ratio_ma20"] = d["Volume"] / d["vol_ma20"].replace(0, np.nan)
        d["ma20"] = d["Close"].rolling(20, min_periods=5).mean()
        d["ma50"] = d["Close"].rolling(50, min_periods=10).mean()
        d["ma200"] = d["Close"].rolling(200, min_periods=30).mean()
        ticker_dfs[t] = d

    results: dict[str, dict] = {}
    ihsg_dates = list(ihsg.index)

    for tr in trades:
        tid = str(tr["id"])
        t = str(tr.get("ticker") or "").upper().strip()
        ed = str(tr.get("entry_date") or "")[:10]
        xd = str(tr.get("exit_date") or "")[:10]
        ep = float(tr.get("entry_price") or 0.0)

        item: dict = {}

        # Match IHSG on or immediately before entry_date
        ihsg_candidates = [dt for dt in ihsg_dates if dt <= ed]
        if ihsg_candidates:
            ir = ihsg.loc[ihsg_candidates[-1]]
            item["ihsg_ret_1d"] = safe_round(ir["ihsg_ret_1d"], 2)
            item["ihsg_above_ma20"] = bool(ir["ihsg_above_ma20"]) if pd.notna(ir["ihsg_above_ma20"]) else None

        if t in ticker_dfs:
            d = ticker_dfs[t]
            t_dates = list(d.index)
            candidates = [dt for dt in t_dates if dt <= ed]
            if candidates:
                matched_dt = candidates[-1]
                sr = d.loc[matched_dt]
                item["matched_date"] = matched_dt
                item["ret_1d"] = safe_round(sr["ret_1d"], 2)
                item["ret_2d"] = safe_round(sr["ret_2d"], 2)
                item["dd_20d"] = safe_round(sr["dd_20d"], 2)
                item["lower_wick_pct"] = safe_round(sr["lower_wick_pct"], 2)
                item["upper_wick_pct"] = safe_round(sr["upper_wick_pct"], 2)
                item["body_pct"] = safe_round(sr["body_pct"], 2)
                item["rsi_14"] = safe_round(sr["rsi_14"], 2)
                item["vol_ratio_ma20"] = safe_round(sr["vol_ratio_ma20"], 2)
                item["above_ma20"] = bool(sr["Close"] >= sr["ma20"]) if pd.notna(sr["ma20"]) else None
                item["above_ma50"] = bool(sr["Close"] >= sr["ma50"]) if pd.notna(sr["ma50"]) else None
                item["above_ma200"] = bool(sr["Close"] >= sr["ma200"]) if pd.notna(sr["ma200"]) else None

                # Compute MFE (Max High) & MAE (Min Low) after entry_date up to exit_date
                if ep > 0:
                    end_dt = xd if xd and xd >= matched_dt else t_dates[-1]
                    hold_slice = d[(d.index > matched_dt) & (d.index <= end_dt)]
                    if not hold_slice.empty:
                        max_high = float(hold_slice["High"].max())
                        min_low = float(hold_slice["Low"].min())
                        item["mfe_peak_price"] = safe_round(max_high, 2)
                        item["mfe_peak_pct"] = safe_round((max_high - ep) / ep * 100.0, 2)
                        item["mae_low_price"] = safe_round(min_low, 2)
                        item["mae_low_pct"] = safe_round((min_low - ep) / ep * 100.0, 2)

        results[tid] = item

    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

