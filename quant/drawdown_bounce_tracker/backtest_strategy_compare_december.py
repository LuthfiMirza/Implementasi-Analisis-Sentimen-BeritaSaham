#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PRICE_FILE = ROOT / "quant/drawdown_bounce_tracker/ptb_backtest_prices_5y.json"
DEFAULT_TICKERS = ["BUMI", "DEWA", "BRPT", "ESSA", "UNVR", "SMGR", "TINS", "PTRO", "ENRG", "RAJA", "INET", "DSSA"]
ROUND_TRIP_COST = 0.008
HOLD_DAYS = 10
EPISODE_GAP_DAYS = 15


def load_prices(path: Path, ticker: str) -> pd.DataFrame:
    data = json.loads(path.read_text())
    rows = data.get(ticker)
    if not rows:
        raise ValueError(f"no price data for {ticker}")
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
    df["ret_2d"] = df["close"].pct_change(2)
    df["drawdown_20d"] = df["close"] / df["close"].rolling(20).max() - 1
    df["bottom_10d_prev"] = df["close"].shift(1).rolling(10).min()
    delta = df["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    df["rsi14"] = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))
    return df


def simulate(df: pd.DataFrame, trigger_idx: int, ticker: str, strategy: str, start: date, end: date) -> dict | None:
    entry_idx = trigger_idx + 1
    exit_idx = entry_idx + HOLD_DAYS
    if exit_idx >= len(df):
        return None
    entry_date = df.iloc[entry_idx]["date"]
    if not (start <= entry_date <= end):
        return None
    entry_price = float(df.iloc[entry_idx]["close"])
    exit_price = float(df.iloc[exit_idx]["close"])
    if entry_price <= 0:
        return None
    return {
        "ticker": ticker,
        "strategy": strategy,
        "trigger_date": df.iloc[trigger_idx]["date"],
        "entry_date": entry_date,
        "exit_date": df.iloc[exit_idx]["date"],
        "entry_price": entry_price,
        "exit_price": exit_price,
        "net_ret": exit_price / entry_price - 1 - ROUND_TRIP_COST,
    }


def signal_indices(df: pd.DataFrame, strategy: str) -> list[int]:
    out = []
    for i in range(1, len(df) - HOLD_DAYS - 1):
        row = df.iloc[i]
        prev = df.iloc[i - 1]
        if strategy == "GABUNGAN":
            hit = row["ret_2d"] <= -0.05 or row["drawdown_20d"] <= -0.20
        elif strategy == "MOMENTUM":
            hit = row["rsi14"] > 60
        elif strategy == "BOTTOM_REBOUND":
            level = row["bottom_10d_prev"] * 1.05
            prev_level = prev["bottom_10d_prev"] * 1.05
            hit = row["close"] > level and prev["close"] <= prev_level
        else:
            raise ValueError(strategy)
        if bool(hit) and not pd.isna(hit):
            out.append(i)
    return out


def to_episodes(trades: list[dict]) -> list[list[dict]]:
    if not trades:
        return []
    ordered = sorted(trades, key=lambda row: (row["ticker"], row["trigger_date"]))
    episodes = []
    for trade in ordered:
        if not episodes or episodes[-1][-1]["ticker"] != trade["ticker"] or (trade["trigger_date"] - episodes[-1][-1]["trigger_date"]).days > EPISODE_GAP_DAYS:
            episodes.append([trade])
        else:
            episodes[-1].append(trade)
    return episodes


def summarize(trades: list[dict]) -> dict:
    episodes = to_episodes(trades)
    ep_rets = np.array([np.mean([trade["net_ret"] for trade in episode]) for episode in episodes], dtype=float)
    raw_rets = np.array([trade["net_ret"] for trade in trades], dtype=float)
    if len(ep_rets) == 0:
        return {"trades": 0, "episodes": 0, "win_rate": 0, "total": 0, "avg": 0, "median": 0}
    return {
        "trades": len(trades),
        "episodes": len(episodes),
        "win_rate": float((ep_rets > 0).mean() * 100),
        "total": float(ep_rets.sum() * 100),
        "raw_total": float(raw_rets.sum() * 100),
        "avg": float(ep_rets.mean() * 100),
        "median": float(np.median(ep_rets) * 100),
    }


def run(start: date, end: date, tickers: list[str]) -> tuple[dict[str, list[dict]], dict[str, dict]]:
    strategies = ["GABUNGAN", "MOMENTUM", "BOTTOM_REBOUND"]
    trades_by_strategy = {strategy: [] for strategy in strategies}
    for ticker in tickers:
        df = load_prices(PRICE_FILE, ticker)
        for strategy in strategies:
            for idx in signal_indices(df, strategy):
                trade = simulate(df, idx, ticker, strategy, start, end)
                if trade:
                    trades_by_strategy[strategy].append(trade)
    return trades_by_strategy, {strategy: summarize(trades) for strategy, trades in trades_by_strategy.items()}


def markdown(start: date, end: date, tickers: list[str], summary: dict[str, dict]) -> str:
    ranked = sorted(summary.items(), key=lambda item: item[1]["total"], reverse=True)
    lines = [
        "# Backtest Strategi Desember",
        "",
        f"Periode entry: `{start}` sampai `{end}`.",
        f"Universe: `{', '.join(tickers)}`.",
        f"Exit: hold `{HOLD_DAYS}` hari bursa, biaya round-trip `{ROUND_TRIP_COST * 100:.1f}%`.",
        "",
        "| Rank | Strategi | Trade | Episode | Win Rate | Total Episode PnL | Avg Episode | Median Episode |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for rank, (name, row) in enumerate(ranked, start=1):
        lines.append(f"| {rank} | {name} | {row['trades']} | {row['episodes']} | {row['win_rate']:.1f}% | {row['total']:+.1f}% | {row['avg']:+.2f}% | {row['median']:+.2f}% |")
    winner = ranked[0][0] if ranked else "-"
    lines += ["", f"Kesimpulan sementara: `{winner}` paling profit pada total PnL level episode.", "", "Catatan: hasil eksplorasi, bukan validasi OOS final. MOMENTUM raw trade mudah menggelembung karena sinyal bisa muncul berhari-hari.", ""]
    return "\n".join(lines)


def self_check() -> None:
    df = pd.DataFrame({"date": pd.date_range("2025-12-01", periods=30).date, "close": [100] * 30})
    df.loc[10, "close"] = 94
    df.loc[12, "close"] = 80
    df.loc[13, "close"] = 85
    df["ret_2d"] = df["close"].pct_change(2)
    df["drawdown_20d"] = df["close"] / df["close"].rolling(20).max() - 1
    df["bottom_10d_prev"] = df["close"].shift(1).rolling(10).min()
    df["rsi14"] = 61
    assert 10 in signal_indices(df, "GABUNGAN")
    assert 13 in signal_indices(df, "BOTTOM_REBOUND")
    assert 1 in signal_indices(df, "MOMENTUM")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2025-12-01")
    parser.add_argument("--end", default="2026-09-01")
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    parser.add_argument("--out", default="output/strategy_december_backtest.md")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if args.self_check:
        self_check()
        print("self-check ok")
        return
    start = pd.Timestamp(args.start).date()
    end = pd.Timestamp(args.end).date()
    tickers = [ticker.strip().upper() for ticker in args.tickers.split(",") if ticker.strip()]
    _, summary = run(start, end, tickers)
    text = markdown(start, end, tickers, summary)
    Path(args.out).write_text(text)
    print(text)


if __name__ == "__main__":
    main()
