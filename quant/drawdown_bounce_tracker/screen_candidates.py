#!/usr/bin/env python3
"""Fase BQ: screening kandidat saham baru untuk drawdown-bounce tracker.

Beda dari screening Fase AY (yang ad-hoc di dalam sesi, tidak bisa dijalankan ulang), script ini
PERMANEN dan mereproduksi protokol validasi yang berlaku SEKARANG:

  1. Aturan entry GABUNGAN (Fase BK): ret_2d <= -5% ATAU drawdown_20d <= -20%.
     Screening Fase AY dulu masih pakai aturan lama (ret_2d saja), jadi hasilnya TIDAK bisa
     dibandingkan langsung -- kandidat yang dulu ditolak bisa lolos sekarang, dan sebaliknya.
  2. Exit sesuai PRODUKSI SEKARANG (Fase BP), beda per signal_type:
       - "ganda"            -> buy & hold 10 hari bursa (TANPA trailing stop)
       - "ret2d"/"drawdown" -> trailing stop 2% dari puncak, ATAU 10 hari bursa, mana duluan
     Ini penting: menyimulasikan exit seragam akan memberi angka yang tidak pernah benar-benar
     terjadi di sistem live.
  3. Episode independence (Fase AY): trigger dengan jeda <=15 hari kalender digabung jadi SATU
     episode. Ini yang dulu menjatuhkan TPIA (win rate per-trade 78% tapi per-episode cuma 52%)
     dan trend-following sebelumnya -- tanpa koreksi ini, satu penurunan panjang terhitung
     sebagai banyak "trade independen" palsu.
  4. Gate ketat P1-P4 (Fase BK), dihitung di level EPISODE bukan trade:
       P1: expectancy holdout > 0 di split 70/30 DAN 60/40
       P2: mengalahkan buy-and-hold pada jendela yang sama
       P3: buang 5% winner teratas, expectancy masih > 0
       P4: bootstrap CI95 lower bound > 0

Data diambil LANGSUNG dari yfinance (bukan data/stocks/*.csv yang statis dan sudah basi -- per
2026-08-13 file BUMI/BBCA baru sampai 21 Jul, ANTM bahkan April). Universe tickernya saja yang
dibaca dari data/stocks/.

Jalankan:  python3 quant/drawdown_bounce_tracker/screen_candidates.py
Output   : tabel ringkas ke stdout + CSV detail ke output/drawdown_bounce_screening.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent))
from detect_signal import (  # noqa: E402
    DROP_THRESHOLD,
    DRAWDOWN_THRESHOLD,
)

TRACKED_ALREADY = {"BUMI", "DEWA", "BRPT", "SMGR", "ESSA", "UNVR"}
NOT_A_TICKER = {"IHSG", "rebuild_ticker_metadata", "ticker_metadata"}

TARGET_HOLD_DAYS = 10
PULLBACK_THRESHOLD = 0.02
ROUND_TRIP_COST = 0.008
EPISODE_GAP_DAYS = 15

START_DATE = "2024-01-01"
BOOTSTRAP_N = 10_000
MIN_EPISODES = 12  # di bawah ini sampelnya terlalu tipis untuk disimpulkan apa pun

REPO_ROOT = Path(__file__).parent.parent.parent


def universe() -> list[str]:
    tickers = sorted(
        p.stem for p in (REPO_ROOT / "data" / "stocks").glob("*.csv")
        if p.stem not in NOT_A_TICKER
    )
    return [t for t in tickers if t not in TRACKED_ALREADY]


def fetch(ticker: str) -> pd.DataFrame | None:
    df = yf.download(f"{ticker}.JK", start=START_DATE, progress=False, auto_adjust=False)
    if df.empty or len(df) < 60:
        return None
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df.reset_index().rename(columns={"Date": "date"})
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["ret_2d"] = df["Close"].pct_change(2, fill_method=None)
    df["dd_20d"] = df["Close"] / df["Close"].rolling(20).max() - 1
    return df


def simulate_trade(df: pd.DataFrame, trigger_idx: int, signal_type: str) -> dict | None:
    """Exit persis seperti produksi Fase BP: "ganda" -> B&H 10 hari, sisanya -> trailing stop 2%."""
    entry_idx = trigger_idx + 1
    if entry_idx >= len(df):
        return None
    entry_price = df.iloc[entry_idx]["Close"]
    if pd.isna(entry_price) or entry_price <= 0:
        return None

    use_trailing = signal_type != "ganda"
    peak = entry_price

    for d in range(1, TARGET_HOLD_DAYS + 1):
        day_idx = entry_idx + d
        if day_idx >= len(df):
            return None  # posisi belum selesai -- jangan dihitung setengah jalan
        row = df.iloc[day_idx]
        if pd.isna(row["Close"]):
            return None

        if use_trailing:
            if not pd.isna(row["High"]) and row["High"] > peak:
                peak = row["High"]
            stop = peak * (1 - PULLBACK_THRESHOLD)
            if not pd.isna(row["Low"]) and row["Low"] <= stop:
                return _mk(df, trigger_idx, entry_idx, entry_price, stop, day_idx, signal_type)

        if d == TARGET_HOLD_DAYS:
            return _mk(df, trigger_idx, entry_idx, entry_price, row["Close"], day_idx, signal_type)
    return None


def _mk(df, trigger_idx, entry_idx, entry_price, exit_price, exit_idx, signal_type) -> dict:
    # Buy-and-hold pembanding untuk P2: beli di hari entry yang sama, tahan penuh 10 hari bursa.
    bh_idx = min(entry_idx + TARGET_HOLD_DAYS, len(df) - 1)
    bh_price = df.iloc[bh_idx]["Close"]
    bh_ret = (bh_price / entry_price - 1 - ROUND_TRIP_COST) if not pd.isna(bh_price) else np.nan
    return {
        "trigger_date": df.iloc[trigger_idx]["date"],
        "entry_date": df.iloc[entry_idx]["date"],
        "exit_date": df.iloc[exit_idx]["date"],
        "signal_type": signal_type,
        "entry_price": float(entry_price),
        "exit_price": float(exit_price),
        "net_ret": float(exit_price / entry_price - 1 - ROUND_TRIP_COST),
        "bh_ret": float(bh_ret) if not pd.isna(bh_ret) else np.nan,
    }


def collect_trades(df: pd.DataFrame) -> list[dict]:
    trades = []
    for i in range(len(df)):
        ret2d, dd20d = df.iloc[i]["ret_2d"], df.iloc[i]["dd_20d"]
        if pd.isna(ret2d) or pd.isna(dd20d):
            continue
        ret2d_hit = ret2d <= DROP_THRESHOLD
        dd_hit = dd20d <= DRAWDOWN_THRESHOLD
        if not (ret2d_hit or dd_hit):
            continue
        signal_type = "ganda" if (ret2d_hit and dd_hit) else ("ret2d" if ret2d_hit else "drawdown")
        t = simulate_trade(df, i, signal_type)
        if t:
            trades.append(t)
    return trades


def to_episodes(trades: list[dict]) -> list[list[dict]]:
    """Trigger berjeda <=15 hari kalender = SATU episode (Fase AY)."""
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


def evaluate(ticker: str, trades: list[dict]) -> dict | None:
    episodes = to_episodes(trades)
    n_ep = len(episodes)
    if n_ep < MIN_EPISODES:
        return {"ticker": ticker, "n_trades": len(trades), "n_episodes": n_ep,
                "verdict": "SAMPEL TIPIS", "detail": f"cuma {n_ep} episode (min {MIN_EPISODES})"}

    # Semua metrik di level EPISODE (rata-rata trade dalam episode), bukan per-trade.
    ep_ret = np.array([np.mean([t["net_ret"] for t in ep]) for ep in episodes])
    ep_bh = np.array([np.nanmean([t["bh_ret"] for t in ep]) for ep in episodes])

    def split_ok(frac: float) -> bool:
        cut = int(n_ep * frac)
        holdout = ep_ret[cut:]
        return len(holdout) > 0 and holdout.mean() > 0

    p1 = split_ok(0.70) and split_ok(0.60)
    p2 = bool(np.nanmean(ep_ret) > np.nanmean(ep_bh))

    keep = max(1, int(n_ep * 0.05))
    p3 = bool(np.sort(ep_ret)[:-keep].mean() > 0)

    rng = np.random.default_rng(42)
    boot = rng.choice(ep_ret, size=(BOOTSTRAP_N, n_ep), replace=True).mean(axis=1)
    ci_lo = float(np.percentile(boot, 2.5))
    p4 = ci_lo > 0

    passed = sum([p1, p2, p3, p4])
    verdict = "LULUS PENUH" if passed == 4 else (f"LULUS {passed}/4" if passed >= 2 else "GAGAL")

    return {
        "ticker": ticker,
        "n_trades": len(trades),
        "n_episodes": n_ep,
        "total_ret_pct": float(sum(t["net_ret"] for t in trades) * 100),
        "ep_mean_pct": float(ep_ret.mean() * 100),
        "ep_median_pct": float(np.median(ep_ret) * 100),
        "ep_winrate_pct": float((ep_ret > 0).mean() * 100),
        "bh_mean_pct": float(np.nanmean(ep_bh) * 100),
        "ci95_lower_pct": ci_lo * 100,
        "P1": p1, "P2": p2, "P3": p3, "P4": p4,
        "passed": passed,
        "verdict": verdict,
        "detail": "",
    }


def main() -> None:
    candidates = universe()
    print(f"Screening {len(candidates)} kandidat (universe {len(candidates) + len(TRACKED_ALREADY)} "
          f"saham, {len(TRACKED_ALREADY)} sudah dipantau).")
    print(f"Aturan: ret_2d<={DROP_THRESHOLD:.0%} ATAU dd_20d<={DRAWDOWN_THRESHOLD:.0%} | "
          f"exit: ganda=B&H {TARGET_HOLD_DAYS}d, lainnya=trailing {PULLBACK_THRESHOLD:.0%}")
    print(f"Data sejak {START_DATE} (yfinance langsung, bukan data/stocks/*.csv yang basi).\n")

    rows = []
    for i, ticker in enumerate(candidates, 1):
        try:
            df = fetch(ticker)
            if df is None:
                print(f"[{i:2}/{len(candidates)}] {ticker:6} -- data tidak cukup, dilewati")
                continue
            trades = collect_trades(df)
            res = evaluate(ticker, trades)
            rows.append(res)
            if res.get("verdict") == "SAMPEL TIPIS":
                print(f"[{i:2}/{len(candidates)}] {ticker:6} -- {res['detail']}")
            else:
                print(f"[{i:2}/{len(candidates)}] {ticker:6} n_ep={res['n_episodes']:3} "
                      f"WR={res['ep_winrate_pct']:5.1f}% med={res['ep_median_pct']:+6.2f}% "
                      f"CI95lo={res['ci95_lower_pct']:+6.2f}% -> {res['verdict']}")
        except Exception as e:  # satu ticker gagal jangan menjatuhkan seluruh screening
            print(f"[{i:2}/{len(candidates)}] {ticker:6} -- ERROR: {e}")

    full = [r for r in rows if r.get("passed") == 4]
    partial = [r for r in rows if r.get("passed") == 3]

    print("\n" + "=" * 78)
    print(f"LULUS PENUH (4/4 gate): {len(full)} saham")
    if full:
        print(f"{'Ticker':<8}{'n_ep':>5}{'WR':>8}{'Median':>9}{'Mean':>9}{'B&H':>9}{'CI95lo':>9}")
        for r in sorted(full, key=lambda x: -x["ci95_lower_pct"]):
            print(f"{r['ticker']:<8}{r['n_episodes']:>5}{r['ep_winrate_pct']:>7.1f}%"
                  f"{r['ep_median_pct']:>+8.2f}%{r['ep_mean_pct']:>+8.2f}%"
                  f"{r['bh_mean_pct']:>+8.2f}%{r['ci95_lower_pct']:>+8.2f}%")
    print(f"\nLULUS 3/4 (kandidat pinggiran, JANGAN langsung dipakai): {len(partial)} saham")
    for r in sorted(partial, key=lambda x: -x["ci95_lower_pct"]):
        gagal = [g for g in ("P1", "P2", "P3", "P4") if not r[g]]
        print(f"  {r['ticker']:<8} n_ep={r['n_episodes']:<4} gagal di {','.join(gagal)}  "
              f"CI95lo={r['ci95_lower_pct']:+.2f}%")

    out = REPO_ROOT / "output" / "drawdown_bounce_screening.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"\nDetail lengkap -> {out.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
