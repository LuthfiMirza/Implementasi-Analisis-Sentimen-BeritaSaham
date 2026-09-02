#!/usr/bin/env python3
"""Fase DR: backtest EXPLORATORY -- user tempel daftar "stock picks" harian dari grup Discord
eksternal "Paper To Billion" (jasa stock-tip berbayar, bukan sumber tervalidasi proyek ini),
minta 97 ticker yang belum kita pantau dites dulu pakai strategi GABUNGAN/MOMENTUM KITA SENDIRI
sebelum diputuskan mana yang layak masuk /watchlist -- BUKAN validasi "apakah pick PTB akurat",
murni "kalau strategi kita yang sudah divalidasi (BUMI/DEWA dkk) diterapkan ke 97 saham lain ini,
yang mana yang historically menghasilkan sinyal profitable".

Entry rule DIREPLIKASI PERSIS dari detect_signal.py (bukan didesain ulang):
  - GABUNGAN: ret_2d(trigger) <= -5% (leg drawdown_20d<=-20% DISENGAJA TIDAK dites untuk ticker
    baru -- leg itu cuma divalidasi untuk COMBINED_RULE_TICKERS yang sudah ada, menerapkannya ke
    saham lain tanpa riset terpisah = klaim yang tidak berdasar).
  - MOMENTUM: RSI14(trigger) > 60.
  - Entry price = closing HARI SETELAH trigger (T+1), sama persis aturan resmi.
  - BOTTOM_REBOUND SENGAJA TIDAK dites -- didesain/dikalibrasi khusus utk volatilitas BUMI/DEWA,
    bukan aturan generik.

Exit rule DIREPLIKASI dari perilaku live TradeController/check_trailing_stop.py: trailing stop 2%
dari puncak sejak entry, ATAU 10 hari bursa (time target), mana yang lebih dulu -- BUKAN exit
waktu tetap 10 hari spt backtest_ab_ac_vs_gabungan.py (itu utk pertanyaan beda).

Episode-independence (gap>=15 hari dianggap 1 episode) dipakai spt semua validasi proyek ini
sebelumnya -- supaya sinyal yang saling berdekatan (mis. MOMENTUM retrigger tiap hari selama RSI
tetap tinggi) tidak dihitung sebagai banyak "kemenangan" independen yang menggelembungkan angka.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

DROP_THRESHOLD = -0.05
MOMENTUM_RSI_THRESHOLD = 60
TRAILING_PULLBACK_PCT = 0.02
TIME_TARGET_DAYS = 10
ROUND_TRIP_COST = 0.008
EPISODE_GAP_DAYS = 15
MIN_EPISODES = 3  # di bawah ini sampel terlalu kecil buat dipercaya

# Sengaja BUKAN koneksi MySQL langsung dari Python -- konvensi proyek ini (lihat komentar
# refreshNewsContextCache/detect_signal.py): Python tidak pernah query DB, PHP yang jembatani
# lewat file JSON. Path ini di-generate oleh artisan tinker sebelum script ini dipanggil.
PRICES_JSON_PATH = Path(__file__).parent / "ptb_backtest_prices.json"


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def load_all_series() -> dict[str, pd.DataFrame]:
    """Baca semua harga sekaligus dari JSON yang di-export PHP -- {ticker: [{date, close}, ...]}."""
    with open(PRICES_JSON_PATH, encoding="utf-8") as f:
        raw = json.load(f)

    out = {}
    for ticker, rows in raw.items():
        if not rows:
            out[ticker] = pd.DataFrame(columns=["date", "close"])
            continue
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df = df.drop_duplicates(subset="date", keep="last").sort_values("date").reset_index(drop=True)
        df["close"] = df["close"].astype(float)
        df["ret_2d"] = df["close"].pct_change(2)
        df["rsi14"] = rsi(df["close"])
        out[ticker] = df
    return out


def simulate_exit(df: pd.DataFrame, entry_idx: int) -> dict | None:
    """Trailing stop 2% dari puncak sejak entry ATAU 10 hari bursa, mana lebih dulu."""
    entry_price = df.iloc[entry_idx]["close"]
    if pd.isna(entry_price) or entry_price <= 0:
        return None
    peak = entry_price
    last_idx = min(entry_idx + TIME_TARGET_DAYS, len(df) - 1)
    for j in range(entry_idx, last_idx + 1):
        price = df.iloc[j]["close"]
        if pd.isna(price):
            continue
        peak = max(peak, price)
        trailing_sl = peak * (1 - TRAILING_PULLBACK_PCT)
        if j > entry_idx and price <= trailing_sl:
            return {
                "exit_date": df.iloc[j]["date"],
                "exit_price": float(price),
                "exit_reason": "trailing_stop",
                "held_days": j - entry_idx,
            }
    # Tidak kena trailing stop dalam window -- exit di time target (atau data habis duluan).
    exit_idx = last_idx
    return {
        "exit_date": df.iloc[exit_idx]["date"],
        "exit_price": float(df.iloc[exit_idx]["close"]),
        "exit_reason": "time_target" if exit_idx == entry_idx + TIME_TARGET_DAYS else "data_habis",
        "held_days": exit_idx - entry_idx,
    }


def find_gabungan_signals(df: pd.DataFrame) -> list[dict]:
    trades = []
    for i in range(len(df) - 1):
        ret2d = df.iloc[i]["ret_2d"]
        if pd.isna(ret2d) or ret2d > DROP_THRESHOLD:
            continue
        entry_idx = i + 1
        entry_price = df.iloc[entry_idx]["close"]
        if pd.isna(entry_price):
            continue
        exit_info = simulate_exit(df, entry_idx)
        if exit_info is None:
            continue
        net_ret = exit_info["exit_price"] / entry_price - 1 - ROUND_TRIP_COST
        trades.append({
            "trigger_date": df.iloc[i]["date"],
            "entry_date": df.iloc[entry_idx]["date"],
            "entry_price": float(entry_price),
            "net_ret": net_ret,
            **exit_info,
        })
    return trades


def find_momentum_signals(df: pd.DataFrame) -> list[dict]:
    trades = []
    for i in range(len(df) - 1):
        rsi_val = df.iloc[i]["rsi14"]
        if pd.isna(rsi_val) or rsi_val <= MOMENTUM_RSI_THRESHOLD:
            continue
        entry_idx = i + 1
        entry_price = df.iloc[entry_idx]["close"]
        if pd.isna(entry_price):
            continue
        exit_info = simulate_exit(df, entry_idx)
        if exit_info is None:
            continue
        net_ret = exit_info["exit_price"] / entry_price - 1 - ROUND_TRIP_COST
        trades.append({
            "trigger_date": df.iloc[i]["date"],
            "entry_date": df.iloc[entry_idx]["date"],
            "entry_price": float(entry_price),
            "net_ret": net_ret,
            **exit_info,
        })
    return trades


def to_episodes(trades: list[dict]) -> list[list[dict]]:
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


def summarize(episodes: list[list[dict]]) -> dict:
    ep_returns = [np.mean([t["net_ret"] for t in ep]) for ep in episodes]
    wins = sum(1 for r in ep_returns if r > 0)
    return {
        "episodes": len(episodes),
        "raw_trades": sum(len(ep) for ep in episodes),
        "win_rate": round(wins / len(episodes) * 100, 1) if episodes else 0.0,
        "avg_return_pct": round(float(np.mean(ep_returns)) * 100, 2) if episodes else 0.0,
        "total_return_pct": round(float(np.sum(ep_returns)) * 100, 2) if episodes else 0.0,
    }


def main():
    tickers = sys.argv[1:]
    if not tickers:
        print("Usage: backtest_ptb_picks.py TICKER1 TICKER2 ...", file=sys.stderr)
        sys.exit(1)

    all_series = load_all_series()

    results = []
    for ticker in tickers:
        df = all_series.get(ticker, pd.DataFrame(columns=["date", "close"]))
        if len(df) < 30:
            results.append({"ticker": ticker, "rows": len(df), "skip": "data_kurang"})
            continue

        gab_trades = find_gabungan_signals(df)
        gab_episodes = to_episodes(gab_trades)
        gab_summary = summarize(gab_episodes)

        mom_trades = find_momentum_signals(df)
        mom_episodes = to_episodes(mom_trades)
        mom_summary = summarize(mom_episodes)

        results.append({
            "ticker": ticker,
            "rows": len(df),
            "gabungan": gab_summary,
            "momentum": mom_summary,
        })

    print("ticker,rows,gab_episodes,gab_winrate,gab_avgret,gab_totalret,mom_episodes,mom_winrate,mom_avgret,mom_totalret")
    for r in results:
        if r.get("skip"):
            print(f"{r['ticker']},{r['rows']},SKIP:{r['skip']},,,,,,,")
            continue
        g, m = r["gabungan"], r["momentum"]
        print(f"{r['ticker']},{r['rows']},{g['episodes']},{g['win_rate']},{g['avg_return_pct']},{g['total_return_pct']},"
              f"{m['episodes']},{m['win_rate']},{m['avg_return_pct']},{m['total_return_pct']}")


if __name__ == "__main__":
    main()
