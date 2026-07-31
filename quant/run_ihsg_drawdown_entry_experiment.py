#!/usr/bin/env python3
"""Fase AB: does "IHSG + stock both drop >=5% over 2 days" predict a profitable bounce in BUMI/DEWA?

Origin: user shared their real BUMI/DEWA trading account (screenshots of equity curve, 2 Jan-31 Jul
2026). They pointed to 4 real discretionary decisions -- entered 8 Jul (after a 7 Jul drop), entered
9 Jul, exited ~24 Jul (after a drop), re-entered 29 Jul -- and asked whether there's a repeatable
signal behind it. Live price+news data pulled for that window showed the big moves (9 Jul, 20-23 Jul
rally; 24 Jul, 30 Jun drops) mostly track broad IHSG moves / commodity-stock rotation, not
company-specific news arriving BEFORE the price move -- most BUMI/DEWA headlines that day describe
what already happened, they don't warn ahead of it.

That's 4 anecdotes from one account over 5 weeks -- nowhere near enough to trust as a rule (this
project has repeatedly found patterns that look real on a handful of examples and fail completely
walk-forward: Fase T, Fase V, Fase W). So this script tests the ACTUAL hypothesis systematically
across BUMI and DEWA's full available price history, with the same anti-snooping discipline used
everywhere else in this project: chronological discovery/holdout split, entry deferred to day after
signal (no lookahead), net of round-trip transaction cost, and an explicit minimum sample size
before concluding anything.

Entry rule: on day t, BUY if both IHSG and the stock have a 2-day cumulative return <= -5%.
Exit rule: the user's real exits weren't on a fixed schedule (variable discretionary timing), and
there's no clean historical earnings-date dataset for BUMI/DEWA to test "exit on earnings report"
systematically -- so this tests FIXED holding periods (H = 3, 5, 10, 20 trading days) as the
honest substitute, reported across all four so no single H is cherry-picked.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

TICKERS = ["BUMI", "DEWA"]
DROP_THRESHOLD = -0.05  # 2-day cumulative return trigger, both IHSG and stock
HOLD_DAYS = [3, 5, 10, 20]
ROUND_TRIP_COST = 0.008  # 0.80% MID, same assumption used throughout this project
DISCOVERY_FRACTION = 0.70
MIN_SIGNALS_TO_CONCLUDE = 20

REPORT_JSON = Path("output/prediction_research/ihsg_drawdown_entry_experiment.json")
REPORT_TXT = Path("output/prediction_research/ihsg_drawdown_entry_experiment.txt")


def load_series(ticker: str) -> pd.DataFrame:
    df = pd.read_csv(f"data/stocks/{ticker}.csv" if ticker != "IHSG" else "data/stocks/IHSG.csv")
    date_col = "Date" if "Date" in df.columns else "date"
    close_col = "Adj Close" if "Adj Close" in df.columns else "adj_close"
    df = df.rename(columns={date_col: "date", close_col: "adj_close"})
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df["ret_1d"] = df["adj_close"].pct_change()
    df["ret_2d"] = df["adj_close"].pct_change(2)
    return df[["date", "adj_close", "ret_1d", "ret_2d"]]


def evaluate(entries: pd.DataFrame, prices: pd.Series, hold_days: int) -> dict:
    """entries: dataframe with 'idx' = integer position of the signal day in `prices`."""
    n = len(prices)
    trade_returns = []
    for idx in entries["idx"]:
        entry_idx = idx + 1  # deferred entry: buy at close of the day AFTER the signal
        exit_idx = entry_idx + hold_days
        if entry_idx >= n or exit_idx >= n:
            continue
        entry_price = prices.iloc[entry_idx]
        exit_price = prices.iloc[exit_idx]
        gross_return = (exit_price / entry_price) - 1
        net_return = gross_return - ROUND_TRIP_COST
        trade_returns.append(net_return)

    if not trade_returns:
        return {"n": 0}

    arr = np.array(trade_returns)
    return {
        "n": len(arr),
        "mean_net_return": float(arr.mean()),
        "median_net_return": float(np.median(arr)),
        "win_rate": float((arr > 0).mean()),
        "std": float(arr.std()),
    }


def baseline_all_days(prices: pd.Series, hold_days: int) -> dict:
    n = len(prices)
    rets = []
    for entry_idx in range(1, n - hold_days):
        entry_price = prices.iloc[entry_idx]
        exit_price = prices.iloc[entry_idx + hold_days]
        rets.append((exit_price / entry_price) - 1 - ROUND_TRIP_COST)
    arr = np.array(rets)
    return {"n": len(arr), "mean_net_return": float(arr.mean()), "win_rate": float((arr > 0).mean())}


def run_ticker(ticker: str, ihsg: pd.DataFrame) -> dict:
    stock = load_series(ticker)
    merged = stock.merge(ihsg, on="date", suffixes=("_stock", "_ihsg")).dropna(subset=["ret_2d_stock", "ret_2d_ihsg"])
    merged = merged.reset_index(drop=True)

    signal_mask = (merged["ret_2d_stock"] <= DROP_THRESHOLD) & (merged["ret_2d_ihsg"] <= DROP_THRESHOLD)
    signal_idx = merged.index[signal_mask].tolist()

    split_point = int(len(merged) * DISCOVERY_FRACTION)
    discovery_signals = [i for i in signal_idx if i < split_point]
    holdout_signals = [i for i in signal_idx if i >= split_point]

    result = {
        "ticker": ticker,
        "date_start": str(merged["date"].min().date()),
        "date_end": str(merged["date"].max().date()),
        "discovery_end_date": str(merged["date"].iloc[split_point].date()) if split_point < len(merged) else None,
        "total_days": len(merged),
        "total_signals": len(signal_idx),
        "discovery_signals": len(discovery_signals),
        "holdout_signals": len(holdout_signals),
        "by_hold_days": {},
    }

    for h in HOLD_DAYS:
        disc_entries = pd.DataFrame({"idx": discovery_signals})
        hold_entries = pd.DataFrame({"idx": holdout_signals})
        all_entries = pd.DataFrame({"idx": signal_idx})

        result["by_hold_days"][h] = {
            "discovery": evaluate(disc_entries, merged["adj_close_stock"], h),
            "holdout": evaluate(hold_entries, merged["adj_close_stock"], h),
            "full_sample": evaluate(all_entries, merged["adj_close_stock"], h),
            "baseline_all_days": baseline_all_days(merged["adj_close_stock"], h),
        }

    return result


def main() -> None:
    ihsg = load_series("IHSG")
    results = [run_ticker(t, ihsg) for t in TICKERS]

    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")

    lines = [
        "Fase AB: Entry 'IHSG + saham turun >=5% (2 hari)' -- BUMI/DEWA full history",
        "=============================================================================",
        "",
        f"Entry: 2-day cumulative return IHSG dan saham keduanya <= {DROP_THRESHOLD:.0%}",
        f"Exit: fixed holding period ({', '.join(str(h) for h in HOLD_DAYS)} hari) -- bukan 'jual saat laba"
        " positif' karena tidak ada dataset tanggal earnings historis yang bersih untuk BUMI/DEWA.",
        f"Biaya: {ROUND_TRIP_COST:.2%} round-trip. Split discovery/holdout: {DISCOVERY_FRACTION:.0%}/{1-DISCOVERY_FRACTION:.0%} kronologis.",
        f"Minimum sinyal untuk dianggap layak disimpulkan: {MIN_SIGNALS_TO_CONCLUDE}",
        "",
    ]

    for r in results:
        lines.append(f"### {r['ticker']} ({r['date_start']} s/d {r['date_end']}, {r['total_days']} hari)")
        lines.append(
            f"Total sinyal: {r['total_signals']} (discovery: {r['discovery_signals']}, "
            f"holdout: {r['holdout_signals']}, batas discovery: {r['discovery_end_date']})"
        )
        if r["total_signals"] < MIN_SIGNALS_TO_CONCLUDE:
            lines.append(
                f"  -> DI BAWAH AMBANG MINIMUM ({MIN_SIGNALS_TO_CONCLUDE}) -- hasil di bawah ini "
                "INDIKATIF SAJA, jangan dijadikan aturan trading."
            )
        lines.append("")
        for h, metrics in r["by_hold_days"].items():
            d, o, f, b = metrics["discovery"], metrics["holdout"], metrics["full_sample"], metrics["baseline_all_days"]
            lines.append(f"  Hold {h} hari:")
            lines.append(
                f"    Discovery : n={d.get('n',0):>3}  mean_net={d.get('mean_net_return',float('nan')):+.2%}  "
                f"win_rate={d.get('win_rate',float('nan')):.1%}"
            )
            lines.append(
                f"    Holdout   : n={o.get('n',0):>3}  mean_net={o.get('mean_net_return',float('nan')):+.2%}  "
                f"win_rate={o.get('win_rate',float('nan')):.1%}"
            )
            lines.append(
                f"    Full      : n={f.get('n',0):>3}  mean_net={f.get('mean_net_return',float('nan')):+.2%}  "
                f"win_rate={f.get('win_rate',float('nan')):.1%}"
            )
            lines.append(
                f"    Baseline (semua hari, hold {h}): mean_net={b['mean_net_return']:+.2%}  win_rate={b['win_rate']:.1%}"
            )
            lines.append("")
        lines.append("")

    REPORT_TXT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
