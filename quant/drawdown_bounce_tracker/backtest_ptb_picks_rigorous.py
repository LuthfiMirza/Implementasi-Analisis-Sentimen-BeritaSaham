#!/usr/bin/env python3
"""Fase DS: kelanjutan Fase DR -- backtest AWAL (backtest_ptb_picks.py) cuma pakai 1 tahun data
(5-9 episode/ticker), JAUH di bawah standar rigor proyek ini sendiri (PROTOCOL.md: n>=20 episode
sebelum kesimpulan ditarik, WAJIB dibanding beli-diamkan DAN IHSG, discovery vs holdout split
supaya tidak overfit ke satu rezim pasar). User minta "riset lebih matang" -- script ini
menerapkan standar PERSIS yang sama ke kandidat teratas dari Fase DR, pakai data historis
sepanjang yang tersedia (sampai 5 tahun, tergantung umur listing saham).

Discovery vs holdout: window dibagi 70/30 berdasar TANGGAL (bukan jumlah baris) -- 70% periode
awal = discovery (buat sekadar dilihat apakah edge ADA), 30% periode akhir = holdout (uji jujur,
tidak boleh dipakai buat "mencari" aturan). Skema exit/entry identik dgn Fase DR (trailing stop
2%/10 hari, GABUNGAN ret_2d<=-5%, MOMENTUM RSI14>60) -- tidak ada parameter baru yang dituning di
sini, murni memperpanjang window + menambah pembanding yang PROTOCOL.md wajibkan.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

DROP_THRESHOLD = -0.05
MOMENTUM_RSI_THRESHOLD = 60
TRAILING_PULLBACK_PCT = 0.02
TIME_TARGET_DAYS = 10
ROUND_TRIP_COST = 0.008
EPISODE_GAP_DAYS = 15
MIN_EPISODES_CONCLUSIVE = 20  # sama persis ambang PROTOCOL.md
DISCOVERY_FRACTION = 0.7

PRICES_JSON_PATH = Path(__file__).parent / "ptb_backtest_prices_5y.json"


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def fetch_ihsg() -> pd.DataFrame:
    df = yf.download("^JKSE", period="5y", progress=False, auto_adjust=False)
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df.reset_index().rename(columns={"Date": "date", "Close": "close"})
    df["date"] = pd.to_datetime(df["date"])
    return df[["date", "close"]]


def load_all_series() -> dict[str, pd.DataFrame]:
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
            return {"exit_date": df.iloc[j]["date"], "exit_price": float(price), "held_days": j - entry_idx}
    exit_idx = last_idx
    return {"exit_date": df.iloc[exit_idx]["date"], "exit_price": float(df.iloc[exit_idx]["close"]), "held_days": exit_idx - entry_idx}


def find_signals(df: pd.DataFrame, rule: str) -> list[dict]:
    trades = []
    for i in range(len(df) - 1):
        if rule == "gabungan":
            v = df.iloc[i]["ret_2d"]
            hit = not pd.isna(v) and v <= DROP_THRESHOLD
        else:
            v = df.iloc[i]["rsi14"]
            hit = not pd.isna(v) and v > MOMENTUM_RSI_THRESHOLD
        if not hit:
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


def episode_stats(episodes: list[list[dict]]) -> dict:
    if not episodes:
        return {"episodes": 0, "win_rate": None, "avg_return_pct": None, "median_return_pct": None}
    ep_returns = [np.mean([t["net_ret"] for t in ep]) for ep in episodes]
    wins = sum(1 for r in ep_returns if r > 0)
    return {
        "episodes": len(episodes),
        "win_rate": round(wins / len(episodes) * 100, 1),
        "avg_return_pct": round(float(np.mean(ep_returns)) * 100, 2),
        "median_return_pct": round(float(np.median(ep_returns)) * 100, 2),
    }


def buy_hold_return(df: pd.DataFrame, start_date, end_date) -> float | None:
    window = df[(df["date"] >= start_date) & (df["date"] <= end_date)]
    if len(window) < 2:
        return None
    start_price = window.iloc[0]["close"]
    end_price = window.iloc[-1]["close"]
    if pd.isna(start_price) or pd.isna(end_price) or start_price <= 0:
        return None
    return round((end_price / start_price - 1) * 100, 2)


def split_discovery_holdout(df: pd.DataFrame):
    if df.empty:
        return df, df
    dates = df["date"]
    cutoff_idx = int(len(df) * DISCOVERY_FRACTION)
    cutoff_date = dates.iloc[cutoff_idx]
    return df[df["date"] < cutoff_date], df[df["date"] >= cutoff_date], cutoff_date


def analyze_ticker(ticker: str, df: pd.DataFrame, ihsg: pd.DataFrame) -> dict:
    if len(df) < 60:
        return {"ticker": ticker, "rows": len(df), "skip": "data_kurang"}

    discovery_df, holdout_df, cutoff_date = split_discovery_holdout(df)

    result = {"ticker": ticker, "rows": len(df), "date_range": f"{df['date'].min().date()} s/d {df['date'].max().date()}",
               "cutoff_date": str(cutoff_date.date())}

    for rule_name, rule_key in [("gabungan", "gabungan"), ("momentum", "momentum")]:
        full_trades = find_signals(df, rule_key)
        full_episodes = to_episodes(full_trades)
        full_stats = episode_stats(full_episodes)

        disc_trades = [t for t in full_trades if t["trigger_date"] < cutoff_date]
        hold_trades = [t for t in full_trades if t["trigger_date"] >= cutoff_date]
        disc_stats = episode_stats(to_episodes(disc_trades))
        hold_stats = episode_stats(to_episodes(hold_trades))

        # Pembanding: rata-rata return beli-diamkan & IHSG SELAMA horizon yang sama tiap episode
        # (bukan buy-hold seluruh window -- itu tidak apple-to-apple dgn strategi yang keluar-masuk).
        bh_rets, ihsg_rets = [], []
        for ep in full_episodes:
            for t in ep:
                bh = buy_hold_return(df, t["entry_date"], t["exit_date"])
                ih = buy_hold_return(ihsg, t["entry_date"], t["exit_date"])
                if bh is not None:
                    bh_rets.append(bh)
                if ih is not None:
                    ihsg_rets.append(ih)

        result[rule_name] = {
            "full": full_stats,
            "discovery": disc_stats,
            "holdout": hold_stats,
            "vs_buy_hold_avg_pct": round(float(np.mean(bh_rets)), 2) if bh_rets else None,
            "vs_ihsg_avg_pct": round(float(np.mean(ihsg_rets)), 2) if ihsg_rets else None,
            "conclusive": full_stats["episodes"] >= MIN_EPISODES_CONCLUSIVE,
            "consistent_disc_holdout": (
                disc_stats["episodes"] >= 2 and hold_stats["episodes"] >= 2
                and disc_stats["avg_return_pct"] is not None and hold_stats["avg_return_pct"] is not None
                and (disc_stats["avg_return_pct"] > 0) == (hold_stats["avg_return_pct"] > 0)
            ),
        }

    return result


def main():
    tickers = sys.argv[1:]
    if not tickers:
        print("Usage: backtest_ptb_picks_rigorous.py TICKER1 TICKER2 ...", file=sys.stderr)
        sys.exit(1)

    print("Mengambil data IHSG (pembanding wajib)...", file=sys.stderr)
    ihsg = fetch_ihsg()
    all_series = load_all_series()

    results = []
    for ticker in tickers:
        df = all_series.get(ticker, pd.DataFrame(columns=["date", "close"]))
        results.append(analyze_ticker(ticker, df, ihsg))

    print(json.dumps(results, indent=2, default=str, ensure_ascii=False))


if __name__ == "__main__":
    main()
