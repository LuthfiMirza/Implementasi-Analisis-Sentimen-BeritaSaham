#!/usr/bin/env python3
"""Fase AD: does an RSI/Stochastic overbought EXIT beat the validated fixed 10-day hold?

Context: Fase AB validated the ENTRY rule (IHSG + stock both drop >=5% over 2 days) with a fixed
holding period as the exit. The user wants a real SELL signal too, pointing at 8 hindsight
buy/sell dates from their own account where RSI/Stoch overbought lined up 3/8 times. 3/8 from
hand-picked dates proves nothing either way -- so this tests the actual question systematically:

  Given the SAME validated entries, does exiting on overbought beat exiting on a fixed schedule?

That framing matters. Testing "overbought predicts tops" in isolation is the thing this project
has already disproved twice (Fase T's 32-indicator survey, Fase W's composite score). But as an
EXIT rule layered on entries we already trust, it is a narrower, fairer question -- and it is the
one that decides whether a sell alert is worth shipping.

Exit variants tested (all reported, no cherry-picking):
  fixed_10d        -- current production baseline from Fase AB
  rsi_gt70         -- exit the first day RSI14 > 70
  stoch_gt80       -- exit the first day Stoch %K > 80
  either           -- exit when either fires
  both             -- exit only when both fire together
All overbought variants keep a 20-day hard cap so a position cannot be held forever when the
condition never triggers -- without it the comparison would silently include open-ended holds.

Same discipline as Fase AB: chronological discovery/holdout split, entry deferred one bar after
the signal, 0.80% round-trip cost, every variant reported.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

TICKERS = ["BUMI", "DEWA"]
DROP_THRESHOLD = -0.05
ROUND_TRIP_COST = 0.008
DISCOVERY_FRACTION = 0.70
MAX_HOLD_DAYS = 20  # hard cap for overbought variants
FIXED_HOLD_DAYS = 10
MIN_SIGNALS_TO_CONCLUDE = 20

REPORT_JSON = Path("output/prediction_research/overbought_exit_experiment.json")
REPORT_TXT = Path("output/prediction_research/overbought_exit_experiment.txt")


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def stochastic_k(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    lowest = low.rolling(period).min()
    highest = high.rolling(period).max()
    return 100 * (close - lowest) / (highest - lowest).replace(0, np.nan)


def load_frame(ticker: str) -> pd.DataFrame:
    path = "data/stocks/IHSG.csv" if ticker == "IHSG" else f"data/stocks/{ticker}.csv"
    df = pd.read_csv(path)
    date_col = "Date" if "Date" in df.columns else "date"
    close_col = "Adj Close" if "Adj Close" in df.columns else "adj_close"
    high_col = "High" if "High" in df.columns else "high"
    low_col = "Low" if "Low" in df.columns else "low"
    df = df.rename(columns={date_col: "date", close_col: "adj_close", high_col: "high", low_col: "low"})
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df["ret_2d"] = df["adj_close"].pct_change(2)
    if ticker != "IHSG":
        df["rsi14"] = rsi(df["adj_close"])
        df["stoch_k"] = stochastic_k(df["high"], df["low"], df["adj_close"])
        return df[["date", "adj_close", "ret_2d", "rsi14", "stoch_k"]]
    return df[["date", "adj_close", "ret_2d"]]


def exit_index(frame: pd.DataFrame, entry_idx: int, variant: str) -> int:
    """Index of the exit bar for one trade, per variant. Never looks at data before entry_idx+1."""
    if variant == "fixed_10d":
        return min(entry_idx + FIXED_HOLD_DAYS, len(frame) - 1)

    cap = min(entry_idx + MAX_HOLD_DAYS, len(frame) - 1)
    for i in range(entry_idx + 1, cap + 1):
        rsi_hot = frame["rsi14"].iloc[i] > 70
        stoch_hot = frame["stoch_k"].iloc[i] > 80
        if variant == "rsi_gt70" and rsi_hot:
            return i
        if variant == "stoch_gt80" and stoch_hot:
            return i
        if variant == "either" and (rsi_hot or stoch_hot):
            return i
        if variant == "both" and rsi_hot and stoch_hot:
            return i
    return cap  # condition never fired within the cap


def evaluate(frame: pd.DataFrame, entries: list[int], variant: str) -> dict:
    returns, holds = [], []
    for entry_signal_idx in entries:
        entry_idx = entry_signal_idx + 1  # deferred entry, same as Fase AB
        if entry_idx >= len(frame) - 1:
            continue
        exit_idx = exit_index(frame, entry_idx, variant)
        if exit_idx <= entry_idx:
            continue
        gross = (frame["adj_close"].iloc[exit_idx] / frame["adj_close"].iloc[entry_idx]) - 1
        returns.append(gross - ROUND_TRIP_COST)
        holds.append(exit_idx - entry_idx)

    if not returns:
        return {"n": 0}
    arr = np.array(returns)
    return {
        "n": len(arr),
        "mean_net_return": float(arr.mean()),
        "median_net_return": float(np.median(arr)),
        "win_rate": float((arr > 0).mean()),
        "mean_hold_days": float(np.mean(holds)),
    }


def run_ticker(ticker: str, ihsg: pd.DataFrame) -> dict:
    stock = load_frame(ticker)
    merged = stock.merge(ihsg, on="date", suffixes=("_stock", "_ihsg"))
    merged = merged.dropna(subset=["ret_2d_stock", "ret_2d_ihsg", "rsi14", "stoch_k"]).reset_index(drop=True)
    merged = merged.rename(columns={"adj_close_stock": "adj_close"})

    signal_idx = merged.index[
        (merged["ret_2d_stock"] <= DROP_THRESHOLD) & (merged["ret_2d_ihsg"] <= DROP_THRESHOLD)
    ].tolist()
    split_point = int(len(merged) * DISCOVERY_FRACTION)
    discovery = [i for i in signal_idx if i < split_point]
    holdout = [i for i in signal_idx if i >= split_point]

    result = {
        "ticker": ticker,
        "date_start": str(merged["date"].min().date()),
        "date_end": str(merged["date"].max().date()),
        "total_signals": len(signal_idx),
        "discovery_signals": len(discovery),
        "holdout_signals": len(holdout),
        "variants": {},
    }
    for variant in ["fixed_10d", "rsi_gt70", "stoch_gt80", "either", "both"]:
        result["variants"][variant] = {
            "discovery": evaluate(merged, discovery, variant),
            "holdout": evaluate(merged, holdout, variant),
            "full_sample": evaluate(merged, signal_idx, variant),
        }
    return result


def main() -> None:
    ihsg = load_frame("IHSG")
    results = [run_ticker(t, ihsg) for t in TICKERS]

    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")

    lines = [
        "Fase AD: Exit overbought (RSI>70 / Stoch>80) vs fixed 10-hari -- BUMI/DEWA histori penuh",
        "=" * 88,
        "",
        "Entry SAMA untuk semua varian: IHSG dan saham sama-sama turun >=5% dalam 2 hari (Fase AB).",
        "Yang dibandingkan cuma cara KELUAR-nya. Semua varian dilaporkan, tidak dipilih yang bagus saja.",
        f"Biaya {ROUND_TRIP_COST:.2%} round-trip. Varian overbought dibatasi maksimum {MAX_HOLD_DAYS} hari.",
        "",
    ]
    for r in results:
        lines.append(f"### {r['ticker']} ({r['date_start']} s/d {r['date_end']})")
        lines.append(
            f"Sinyal: {r['total_signals']} total "
            f"(discovery {r['discovery_signals']}, holdout {r['holdout_signals']})"
        )
        if r["total_signals"] < MIN_SIGNALS_TO_CONCLUDE:
            lines.append(f"  -> DI BAWAH AMBANG {MIN_SIGNALS_TO_CONCLUDE} -- indikatif saja.")
        lines.append("")
        lines.append(f"{'varian':<14}{'discovery':>26}{'holdout':>26}{'rata2 hari':>13}")
        for variant, m in r["variants"].items():
            d, o, f = m["discovery"], m["holdout"], m["full_sample"]
            d_txt = f"{d.get('mean_net_return', float('nan')):+.2%} (win {d.get('win_rate', float('nan')):.0%}, n={d.get('n', 0)})"
            o_txt = f"{o.get('mean_net_return', float('nan')):+.2%} (win {o.get('win_rate', float('nan')):.0%}, n={o.get('n', 0)})"
            lines.append(f"{variant:<14}{d_txt:>26}{o_txt:>26}{f.get('mean_hold_days', float('nan')):>12.1f}")
        lines.append("")

        base = r["variants"]["fixed_10d"]
        lines.append("Selisih vs baseline fixed_10d (positif = varian exit overbought lebih baik):")
        for variant, m in r["variants"].items():
            if variant == "fixed_10d":
                continue
            dd = m["discovery"].get("mean_net_return", float("nan")) - base["discovery"].get("mean_net_return", float("nan"))
            do = m["holdout"].get("mean_net_return", float("nan")) - base["holdout"].get("mean_net_return", float("nan"))
            verdict = "LEBIH BAIK di dua-duanya" if dd > 0 and do > 0 else "tidak konsisten / lebih buruk"
            lines.append(f"  {variant:<12} discovery {dd:+.2%} | holdout {do:+.2%}  -> {verdict}")
        lines.append("")

    REPORT_TXT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
