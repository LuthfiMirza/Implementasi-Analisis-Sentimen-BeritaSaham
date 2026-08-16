#!/usr/bin/env python3
"""Fase CG: saring saham dari daftar pick Paper To Billion (PTB, 19 hari Jul-Agu 2026) yang BELUM
ada di alert Telegram -- dites pakai DUA aturan yang sudah divalidasi produksi (GABUNGAN & MOMENTUM),
bukan aturan baru. PTB terbukti gaya momentum murni (analisis sesi ini: 81% pick naik dalam 5 hari,
median RSI 60, volume spike) -- jadi MOMENTUM lebih relevan diuji ke kandidat ini daripada
GABUNGAN (yang justru cari saham JATUH), tapi keduanya tetap dilaporkan untuk kelengkapan.

Protokol SAMA seperti screen_candidates.py (Fase BQ): episode independence (jeda <=15 hari kalender
per ticker = 1 episode) + gate P1-P4 (OOS split 70/30 & 60/40, exclude top-5% winner, bootstrap
CI95). Minimal 12 episode, di bawah itu ditandai sampel tipis.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent))
from detect_signal import DROP_THRESHOLD, DRAWDOWN_THRESHOLD  # noqa: E402
from screen_candidates import (  # noqa: E402
    BOOTSTRAP_N,
    MIN_EPISODES,
    PULLBACK_THRESHOLD,
    ROUND_TRIP_COST,
    TARGET_HOLD_DAYS,
    collect_trades,
    evaluate,
    fetch,
    to_episodes,
)

MOMENTUM_RSI_THRESHOLD = 60
ALREADY_TRACKED = {"BUMI", "DEWA", "BRPT", "SMGR", "ESSA", "UNVR"}

# Semua ticker unik dari 19 hari pick PTB (17 Jul - 14 Agu 2026), dikurangi yang sudah tracked.
PTB_TICKERS_RAW = """
MINA ARTO BBTN BUVA CBRE KBLV PADI TLKM TPIA TINS RAJA NCKL MEDC GTSI CUAN CTTH BUMI BRPT BRMS
BNBR BIPI ADRO RANS PANI JELI BREN ANTM AKRA AMMN AMRT BIPI BNBR BNGA BSDE BSSR BUVA ENRG GPSO
GULA HMSP HUMI ICBP IMPC INCO INDF INDY INET INKP ITMG JGLE KIJA LSIP MBMA MDIA MLPL NTBK PAMG
PANI PGAS PNLF PSAB SSIA TKIM TOBA WIRG GGRM PRDL AALI PTBA ADMR ATLA CDIA DOOH ELSA HRTA IRSX
KOKA MAXI PTRO WIFI WMUU ARCI BBCA BULL DSSA MDKA RATU AADI EMTK FUTR MDIA MLPT RMKE SMIL TOWR
VKTR BBRI COIN ERAA PAGI BMRI OILS REAL CDIA BAJA GDST KOTA MCAS BACH IATA JKON MAPI BKSL COCO
NSSS SLIS SWID
""".split()
CANDIDATES = sorted(set(PTB_TICKERS_RAW) - ALREADY_TRACKED)

START_DATE = "2024-01-01"


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def fetch_with_rsi(ticker: str) -> pd.DataFrame | None:
    df = fetch(ticker)
    if df is None:
        return None
    df["rsi14"] = rsi(df["Close"])
    return df


def simulate_momentum_trade(df: pd.DataFrame, trigger_idx: int) -> dict | None:
    """Persis produksi Momentum: entry T+1 close, exit trailing-stop 2% / target 10 hari."""
    entry_idx = trigger_idx + 1
    if entry_idx >= len(df):
        return None
    entry_price = df.iloc[entry_idx]["Close"]
    if pd.isna(entry_price) or entry_price <= 0:
        return None

    peak = entry_price
    for d in range(1, TARGET_HOLD_DAYS + 1):
        day_idx = entry_idx + d
        if day_idx >= len(df):
            return None
        row = df.iloc[day_idx]
        if pd.isna(row["Close"]):
            return None
        if not pd.isna(row["High"]) and row["High"] > peak:
            peak = row["High"]
        stop = peak * (1 - PULLBACK_THRESHOLD)
        if not pd.isna(row["Low"]) and row["Low"] <= stop:
            exit_price = stop
            break
        if d == TARGET_HOLD_DAYS:
            exit_price = row["Close"]
    else:
        return None

    return {
        "trigger_date": df.iloc[trigger_idx]["date"],
        "net_ret": float(exit_price / entry_price - 1 - ROUND_TRIP_COST),
    }


def collect_momentum_trades(df: pd.DataFrame) -> list[dict]:
    trades = []
    for i in range(len(df) - 1):
        row = df.iloc[i]
        if pd.isna(row["rsi14"]) or not (row["rsi14"] > MOMENTUM_RSI_THRESHOLD):
            continue
        t = simulate_momentum_trade(df, i)
        if t:
            trades.append(t)
    return trades


def evaluate_generic(ticker: str, trades: list[dict], label: str) -> dict | None:
    episodes = to_episodes(trades)
    n_ep = len(episodes)
    if n_ep < MIN_EPISODES:
        return {"ticker": ticker, "label": label, "n_trades": len(trades), "n_episodes": n_ep,
                "verdict": "SAMPEL TIPIS", "detail": f"cuma {n_ep} episode (min {MIN_EPISODES})"}

    ep_ret = np.array([np.mean([t["net_ret"] for t in ep]) for ep in episodes])

    def split_ok(frac):
        cut = int(n_ep * frac)
        hold = ep_ret[cut:]
        return len(hold) > 0 and hold.mean() > 0

    p1 = split_ok(0.70) and split_ok(0.60)
    keep = max(1, int(n_ep * 0.05))
    p3 = np.sort(ep_ret)[:-keep].sum() > 0
    rng = np.random.default_rng(42)
    boot = rng.choice(ep_ret, size=(BOOTSTRAP_N, n_ep), replace=True).mean(axis=1)
    ci_lo = float(np.percentile(boot, 2.5))
    p4 = ci_lo > 0
    passed = sum([p1, p3, p4])

    return {
        "ticker": ticker, "label": label, "n_trades": len(trades), "n_episodes": n_ep,
        "wr_pct": float((ep_ret > 0).mean() * 100),
        "mean_pct": float(ep_ret.mean() * 100),
        "median_pct": float(np.median(ep_ret) * 100),
        "ci95_lo_pct": ci_lo * 100,
        "p1": p1, "p3": p3, "p4": p4, "passed": passed,
        "verdict": "LULUS PENUH" if passed == 3 else f"LULUS {passed}/3",
    }


def main() -> None:
    print(f"Fase CG -- screening {len(CANDIDATES)} kandidat dari daftar pick PTB "
          f"(sudah dikurangi {len(ALREADY_TRACKED)} yang tracked): {', '.join(CANDIDATES)}\n")

    gabungan_results, momentum_results = [], []

    for i, ticker in enumerate(CANDIDATES, 1):
        try:
            df = fetch_with_rsi(ticker)
            if df is None or len(df) < 60:
                print(f"[{i:3}/{len(CANDIDATES)}] {ticker:6} -- data tidak cukup")
                continue

            g = evaluate_generic(ticker, collect_trades(df), "GABUNGAN")
            m = evaluate_generic(ticker, collect_momentum_trades(df), "MOMENTUM")
            gabungan_results.append(g)
            momentum_results.append(m)

            g_tag = g["verdict"] if g["verdict"] != "SAMPEL TIPIS" else f"tipis({g['n_episodes']}ep)"
            m_tag = m["verdict"] if m["verdict"] != "SAMPEL TIPIS" else f"tipis({m['n_episodes']}ep)"
            print(f"[{i:3}/{len(CANDIDATES)}] {ticker:6} GABUNGAN={g_tag:<16} MOMENTUM={m_tag}")
        except Exception as e:
            print(f"[{i:3}/{len(CANDIDATES)}] {ticker:6} -- ERROR: {e}")

    for label, results in [("GABUNGAN", gabungan_results), ("MOMENTUM", momentum_results)]:
        full = [r for r in results if r.get("passed") == 3]
        partial = [r for r in results if r.get("passed") == 2]
        print(f"\n{'='*78}\nAturan {label} -- LULUS PENUH (3/3 gate): {len(full)} saham")
        if full:
            print(f"{'Ticker':<8}{'n_ep':>5}{'WR':>8}{'Median':>9}{'Mean':>9}{'CI95lo':>9}")
            for r in sorted(full, key=lambda x: -x["ci95_lo_pct"]):
                print(f"{r['ticker']:<8}{r['n_episodes']:>5}{r['wr_pct']:>7.1f}%"
                      f"{r['median_pct']:>+8.2f}%{r['mean_pct']:>+8.2f}%{r['ci95_lo_pct']:>+8.2f}%")
        print(f"LULUS 2/3 (kandidat pinggiran): {len(partial)} saham")
        for r in sorted(partial, key=lambda x: -x["ci95_lo_pct"]):
            gagal = [g for g in ("p1", "p3", "p4") if not r[g]]
            print(f"  {r['ticker']:<8} n_ep={r['n_episodes']:<4} gagal di {','.join(gagal)}  "
                  f"CI95lo={r['ci95_lo_pct']:+.2f}%")

    out = Path(__file__).parent.parent.parent / "output" / "ptb_candidate_screening.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(gabungan_results + momentum_results).to_csv(out, index=False)
    print(f"\nDetail lengkap -> {out}")


if __name__ == "__main__":
    main()
