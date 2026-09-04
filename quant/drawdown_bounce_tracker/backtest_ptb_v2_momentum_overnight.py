#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import yfinance as yf

BASE = Path("quant/drawdown_bounce_tracker/backtest_strategy_compare_december.py")
SPEC = importlib.util.spec_from_file_location("strategy_compare", BASE)
BASE_MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASE_MOD)

START = pd.Timestamp("2026-07-20").date()
END = pd.Timestamp("2026-09-01").date()
CAPITAL = 10_000_000
ROUND_TRIP_COST = 0.003
EPISODE_GAP_DAYS = 15
OUT_FILE = Path("output/ptb_v2_momentum_overnight_backtest.md")


def first_30m_close(ticker: str) -> dict:
    df = yf.download(
        f"{ticker}.JK",
        start=str(START),
        end="2026-09-02",
        interval="30m",
        progress=False,
        auto_adjust=False,
        threads=False,
    )
    if df.empty:
        return {}
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]
    df = df.reset_index()
    df["dt_jkt"] = pd.to_datetime(df[df.columns[0]], utc=True).dt.tz_convert("Asia/Jakarta")
    df["date"] = df["dt_jkt"].dt.normalize().dt.tz_localize(None).dt.date
    first = df.sort_values("dt_jkt").groupby("date").first().reset_index()
    return dict(zip(first["date"], first["Close"].astype(float)))


def to_episodes(trades: list[dict]) -> list[list[dict]]:
    if not trades:
        return []
    ordered = sorted(trades, key=lambda row: (row["ticker"], row["entry_date"]))
    episodes = []
    for trade in ordered:
        if not episodes or episodes[-1][-1]["ticker"] != trade["ticker"] or (trade["entry_date"] - episodes[-1][-1]["entry_date"]).days > EPISODE_GAP_DAYS:
            episodes.append([trade])
        else:
            episodes[-1].append(trade)
    return episodes


def run() -> tuple[list[dict], list[tuple]]:
    trades = []
    for ticker in BASE_MOD.DEFAULT_TICKERS:
        daily = BASE_MOD.load_prices(BASE_MOD.PRICE_FILE, ticker)
        exits = first_30m_close(ticker)
        for idx in range(len(daily) - 1):
            row = daily.iloc[idx]
            next_row = daily.iloc[idx + 1]
            if not (START <= row["date"] <= END):
                continue
            if pd.isna(row["rsi14"]) or row["rsi14"] <= 60:
                continue
            exit_price = exits.get(next_row["date"])
            if not exit_price:
                continue
            entry_price = float(row["close"])
            trades.append({
                "ticker": ticker,
                "entry_date": row["date"],
                "exit_date": next_row["date"],
                "entry_price": entry_price,
                "exit_price": exit_price,
                "net_ret": exit_price / entry_price - 1 - ROUND_TRIP_COST,
            })
    episode_returns = []
    for episode in to_episodes(trades):
        episode_returns.append((min(t["entry_date"] for t in episode), sum(t["net_ret"] for t in episode) / len(episode), len(episode)))
    return trades, sorted(episode_returns)


def compound(episode_returns: list[tuple]) -> float:
    capital = CAPITAL
    for _, ret, _ in episode_returns:
        capital *= 1 + ret
    return capital


def main() -> None:
    trades, episode_returns = run()
    final = compound(episode_returns)
    win_rate = sum(1 for _, ret, _ in episode_returns if ret > 0) / len(episode_returns) * 100 if episode_returns else 0
    text = f"""# PTB V2 Momentum Overnight Backtest

Modal awal: `Rp{CAPITAL:,.0f}`.
Periode signal: `{START}` sampai `{END}`.
Entry: daily close saat `RSI14 > 60`.
Exit: close bar 30m pertama hari bursa berikutnya.
Biaya asumsi: `{ROUND_TRIP_COST * 100:.1f}%` round-trip.

## Hasil

- Trade mentah: `{len(trades)}`
- Episode: `{len(episode_returns)}`
- Win rate episode: `{win_rate:.1f}%`
- Modal akhir: `Rp{final:,.0f}`
- Return compound: `{(final / CAPITAL - 1) * 100:+.2f}%`

## Catatan

Ini `overnight momentum`, bukan PTB label-picks. Data exit pakai proxy first 30m Yahoo.
"""
    OUT_FILE.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
