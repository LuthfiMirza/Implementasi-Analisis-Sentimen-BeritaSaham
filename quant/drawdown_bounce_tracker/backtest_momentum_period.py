#!/usr/bin/env python3
"""Fase BZ: backtest MOMENTUM (RSI14>60) terbatas ke periode Des 2025 - sekarang, supaya bisa
dibandingkan apple-to-apple dengan angka live GABUNGAN & AI-tp30 di Trade Journal (yang sama-sama
mulai dari Des 2025).

MOMENTUM baru live 3 hari (12-14 Agu 2026), 0 trade closed -- belum ada data live untuk
dibandingkan. Backtest ini mengisi kekosongan itu dengan simulasi periode SAMA persis, aturan
SAMA persis dengan produksi (entry T+1 close, exit trailing-stop 2% / target 10 hari bursa,
peak dihitung mulai dari hari SESUDAH entry -- fix Fase BW).

RSI dihitung dari data mulai 2024-01-01 (buffer >600 hari sebelum Des 2025) supaya TIDAK kena
masalah window-drift yang baru diperbaiki di Fase BY -- nilai RSI di backtest ini stabil/konvergen
dari awal.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

MOMENTUM_TICKERS = ["BUMI", "DEWA", "BRPT"]
RSI_THRESHOLD = 60
TARGET_HOLD_DAYS = 10
PULLBACK_THRESHOLD = 0.02
ROUND_TRIP_COST = 0.008
WINDOW_START = pd.Timestamp("2025-12-01").date()
WINDOW_END = pd.Timestamp("2026-08-14").date()
EPISODE_GAP_DAYS = 15  # sama seperti Fase AY/BK/BQ/BR -- trigger berjeda <=15 hari = 1 episode


def to_episodes(trades: list[dict]) -> list[list[dict]]:
    """RSI>60 sering bertahan berhari-hari berturut-turut (satu rally panjang) -- tanpa ini,
    satu rally dihitung sebagai puluhan "trade independen" palsu, persis bias yang sudah
    dikoreksi untuk GABUNGAN di Fase AY/BK/BQ/BR. Wajib dipakai di sini juga."""
    if not trades:
        return []
    ordered = sorted(trades, key=lambda t: t["trigger_date"])
    episodes = [[ordered[0]]]
    for t in ordered[1:]:
        if (t["trigger_date"] - episodes[-1][-1]["trigger_date"]).days > EPISODE_GAP_DAYS:
            episodes.append([t])
        else:
            episodes[-1].append(t)
    return episodes


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def fetch(ticker: str) -> pd.DataFrame:
    df = yf.download(f"{ticker}.JK", start="2024-01-01", progress=False, auto_adjust=False)
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df.reset_index().rename(columns={"Date": "date"})
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["rsi14"] = rsi(df["Close"])
    return df


def simulate_trade(df: pd.DataFrame, trigger_idx: int) -> dict | None:
    """Persis produksi: entry = closing T+1, exit trailing-stop 2% (peak MULAI dari entry+1,
    fix Fase BW) atau 10 hari bursa."""
    entry_idx = trigger_idx + 1
    if entry_idx >= len(df):
        return None
    entry_date = df.iloc[entry_idx]["date"]
    if not (WINDOW_START <= entry_date <= WINDOW_END):
        return None
    entry_price = df.iloc[entry_idx]["Close"]
    if pd.isna(entry_price) or entry_price <= 0:
        return None

    peak = entry_price
    for d in range(1, TARGET_HOLD_DAYS + 1):
        day_idx = entry_idx + d
        if day_idx >= len(df):
            return None  # posisi belum selesai per akhir data -- jangan dihitung setengah jalan
        row = df.iloc[day_idx]
        if pd.isna(row["Close"]):
            return None
        if not pd.isna(row["High"]) and row["High"] > peak:
            peak = row["High"]
        stop = peak * (1 - PULLBACK_THRESHOLD)
        if not pd.isna(row["Low"]) and row["Low"] <= stop:
            exit_price, exit_reason = stop, "trailing-stop"
            break
        if d == TARGET_HOLD_DAYS:
            exit_price, exit_reason = row["Close"], "target-waktu"
    else:
        return None

    return {
        "trigger_date": df.iloc[trigger_idx]["date"],
        "entry_date": entry_date,
        "entry_price": float(entry_price),
        "exit_price": float(exit_price),
        "exit_reason": exit_reason,
        "net_ret": float(exit_price / entry_price - 1 - ROUND_TRIP_COST),
    }


def main() -> None:
    all_trades = []
    print(f"Backtest MOMENTUM, periode entry {WINDOW_START} s/d {WINDOW_END} "
          f"(sama dengan cakupan live GABUNGAN/AI-tp30 di Trade Journal)\n")

    for ticker in MOMENTUM_TICKERS:
        df = fetch(ticker)
        trades = []
        for i in range(len(df) - 1):
            row = df.iloc[i]
            if pd.isna(row["rsi14"]) or not (row["rsi14"] > RSI_THRESHOLD):
                continue
            t = simulate_trade(df, i)
            if t:
                trades.append(t)
        all_trades += [dict(t, ticker=ticker) for t in trades]

        if trades:
            rets = [t["net_ret"] for t in trades]
            wr = sum(1 for r in rets if r > 0) / len(rets) * 100
            print(f"{ticker}: {len(trades)} trade, WR={wr:.1f}%, total={sum(rets)*100:+.1f}%, "
                  f"avg={np.mean(rets)*100:+.2f}%")
        else:
            print(f"{ticker}: 0 trade di periode ini")

    print()
    if all_trades:
        rets = [t["net_ret"] for t in all_trades]
        wr = sum(1 for r in rets if r > 0) / len(rets) * 100
        print(f"=== MENTAH (per-trade, TANPA koreksi episode): {len(all_trades)} trade ===")
        print(f"Win rate    : {wr:.1f}%  |  Total: {sum(rets)*100:+.1f}%  |  "
              f"Avg: {np.mean(rets)*100:+.2f}%  |  Median: {np.median(rets)*100:+.2f}%")
        print("^ MENGGELEMBUNG -- RSI>60 sering bertahan berhari-hari, satu rally dihitung")
        print("  berkali-kali sebagai trade 'independen'. Lihat angka episode di bawah.\n")

        eps_by_ticker: dict[str, list] = {}
        for t in all_trades:
            eps_by_ticker.setdefault(t["ticker"], []).append(t)

        all_eps = []
        for ticker in MOMENTUM_TICKERS:
            eps = to_episodes(eps_by_ticker.get(ticker, []))
            all_eps += eps
            if eps:
                ep_rets = [np.mean([t["net_ret"] for t in e]) for e in eps]
                wr_e = sum(1 for r in ep_rets if r > 0) / len(ep_rets) * 100
                print(f"{ticker}: {len(eps)} episode (dari {len(eps_by_ticker[ticker])} trade "
                      f"mentah) -- WR={wr_e:.1f}%, total={sum(ep_rets)*100:+.1f}%, "
                      f"avg={np.mean(ep_rets)*100:+.2f}%")

        ep_rets_all = [np.mean([t["net_ret"] for t in e]) for e in all_eps]
        wr_all = sum(1 for r in ep_rets_all if r > 0) / len(ep_rets_all) * 100
        print()
        print(f"=== TOTAL MOMENTUM level EPISODE (angka yang BENAR dibandingkan): "
              f"{len(all_eps)} episode ===")
        print(f"Win rate    : {wr_all:.1f}%")
        print(f"Total return: {sum(ep_rets_all)*100:+.1f}%")
        print(f"Avg PnL%    : {np.mean(ep_rets_all)*100:+.2f}%")
        print(f"Median PnL% : {np.median(ep_rets_all)*100:+.2f}%")
    else:
        print("Tidak ada trade MOMENTUM yang selesai (entry+exit) di periode ini.")


if __name__ == "__main__":
    main()
