#!/usr/bin/env python3
"""Fase CF: aturan AB/AC asli (IHSG+saham SAMA-SAMA crash >=5%/2hari, exit tahan 10 hari tetap)
diuji ke 6 saham yang SEKARANG dipantau (BUMI/DEWA/BRPT/ESSA/UNVR/SMGR), pakai protokol validasi
penuh (episode-independence + P1-P4) yang belum pernah diterapkan ke aturan ini.

KENAPA INI, BUKAN memvalidasi ulang label DB `legacy_ab_ac`: 28 trade berlabel itu ternyata di
universe SAHAM BLUE CHIP (ASII/BBCA/BBRI/dst) yang TIDAK ADA dokumentasinya di plan.md -- provenance
tidak jelas, mungkin dari sesi kerja lain. Fase AB ASLI (terdokumentasi rapi, plan.md) cuma diuji ke
BUMI/DEWA, BUMI lolos (27 episode independen), DEWA gagal (n<20, tercemar crash 2008). Daripada
percaya data yang provenance-nya tidak jelas, aturan ASLI (dual-condition, exit waktu tetap) diuji
ulang bersih ke universe yang SEKARANG relevan.

Pertanyaan: apakah aturan AB/AC ini (syarat lebih ketat -- IHSG WAJIB ikut crash, bukan cuma
saham) menghasilkan trigger di TANGGAL YANG BEDA dari GABUNGAN? Kalau kebanyakan tumpang tindih,
tidak ada nilai tambah menggabungkannya -- GABUNGAN sendiri sudah menangkap kesempatan yang sama.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

TICKERS = ["BUMI", "DEWA", "BRPT", "ESSA", "UNVR", "SMGR"]
DROP_THRESHOLD = -0.05  # sama ambang dengan GABUNGAN, tapi WAJIB IHSG ikut (beda dari GABUNGAN)
HOLD_DAYS = 10  # exit waktu tetap, horizon yang menang di validasi BUMI asli (Fase AB)
ROUND_TRIP_COST = 0.008
EPISODE_GAP_DAYS = 15
START_DATE = "2024-01-01"  # sama window dipakai validasi GABUNGAN (Fase BK/BQ), apple-to-apple


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


def fetch(symbol: str) -> pd.DataFrame:
    df = yf.download(symbol, start=START_DATE, progress=False, auto_adjust=False)
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df.reset_index().rename(columns={"Date": "date"})
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["ret_2d"] = df["Close"].pct_change(2)
    return df[["date", "Close", "ret_2d"]]


def simulate(df: pd.DataFrame, trigger_idx: int) -> dict | None:
    entry_idx = trigger_idx + 1
    exit_idx = entry_idx + HOLD_DAYS
    if exit_idx >= len(df):
        return None
    entry_price = df.iloc[entry_idx]["Close"]
    exit_price = df.iloc[exit_idx]["Close"]
    if pd.isna(entry_price) or pd.isna(exit_price) or entry_price <= 0:
        return None
    return {
        "trigger_date": df.iloc[trigger_idx]["date"],
        "entry_date": df.iloc[entry_idx]["date"],
        "entry_price": float(entry_price),
        "exit_price": float(exit_price),
        "net_ret": float(exit_price / entry_price - 1 - ROUND_TRIP_COST),
    }


def validate(episodes: list[list[dict]], label: str) -> dict:
    n_ep = len(episodes)
    if n_ep == 0:
        return {"label": label, "n_ep": 0, "verdict": "TIDAK ADA SINYAL"}

    ep_ret = np.array([np.mean([t["net_ret"] for t in ep]) for ep in episodes])

    def split_ok(frac):
        cut = int(n_ep * frac)
        holdout = ep_ret[cut:]
        return len(holdout) > 0 and holdout.mean() > 0

    p1 = split_ok(0.70) and split_ok(0.60)
    keep = max(1, int(n_ep * 0.05))
    p3 = np.sort(ep_ret)[:-keep].sum() > 0
    rng = np.random.default_rng(42)
    boot = rng.choice(ep_ret, size=(10000, n_ep), replace=True).mean(axis=1)
    ci_lo = np.percentile(boot, 2.5)
    p4 = ci_lo > 0
    passed = sum([p1, p3, p4])

    return {
        "label": label, "n_ep": n_ep,
        "total_pct": float(sum(t["net_ret"] for ep in episodes for t in ep) * 100),
        "wr_pct": float((ep_ret > 0).mean() * 100),
        "mean_pct": float(ep_ret.mean() * 100),
        "ci95_lo_pct": float(ci_lo * 100),
        "p1": p1, "p3": p3, "p4": p4, "passed": passed,
        "verdict": "LULUS PENUH" if passed == 3 else f"LULUS {passed}/3",
    }


def main() -> None:
    print(f"Fase CF -- aturan AB/AC (IHSG+saham crash bareng) ke 6 saham tracked, hold={HOLD_DAYS}d")
    print(f"Window: {START_DATE} s/d sekarang (sama dengan validasi GABUNGAN Fase BK/BQ)\n")

    ihsg = fetch("^JKSE")

    all_episodes_abac = []
    ab_trigger_dates = {}  # ticker -> set of trigger dates, untuk cek overlap dgn GABUNGAN

    print(f"{'Saham':<8}{'sinyal AB/AC':>14}{'episode':>10}")
    for ticker in TICKERS:
        stock = fetch(f"{ticker}.JK")
        merged = stock.merge(ihsg, on="date", suffixes=("_stock", "_ihsg")).dropna()

        trades = []
        trigger_dates = set()
        for i in range(len(merged) - 1):
            row = merged.iloc[i]
            if row["ret_2d_stock"] <= DROP_THRESHOLD and row["ret_2d_ihsg"] <= DROP_THRESHOLD:
                t = simulate(merged.rename(columns={"Close_stock": "Close"}), i)
                if t:
                    trades.append(t)
                    trigger_dates.add(row["date"])

        eps = to_episodes(trades)
        all_episodes_abac += eps
        ab_trigger_dates[ticker] = trigger_dates
        print(f"{ticker:<8}{len(trades):>14}{len(eps):>10}")

    print()
    result_abac = validate(all_episodes_abac, "AB/AC (dual-condition, exit 10 hari tetap)")
    print(f"=== VALIDASI AB/AC gabungan 6 saham ===")
    for k, v in result_abac.items():
        if k != "label":
            print(f"  {k}: {v}")

    # Cek overlap tanggal trigger dengan GABUNGAN (ret_2d<=-5% OR drawdown<=-20%, TANPA syarat IHSG)
    print(f"\n=== Overlap tanggal trigger: AB/AC vs GABUNGAN (per saham) ===")
    DRAWDOWN_THRESHOLD = -0.20
    total_ab, total_overlap = 0, 0
    for ticker in TICKERS:
        stock = fetch(f"{ticker}.JK")
        stock["dd_20d"] = stock["Close"] / stock["Close"].rolling(20).max() - 1
        gabungan_dates = set(
            stock.loc[(stock["ret_2d"] <= DROP_THRESHOLD) | (stock["dd_20d"] <= DRAWDOWN_THRESHOLD), "date"]
        )
        ab_dates = ab_trigger_dates[ticker]
        overlap = ab_dates & gabungan_dates
        only_ab = ab_dates - gabungan_dates
        total_ab += len(ab_dates)
        total_overlap += len(overlap)
        pct = len(overlap) / len(ab_dates) * 100 if ab_dates else 0
        print(f"  {ticker:<8} AB/AC={len(ab_dates):>3} | tumpang tindih GABUNGAN={len(overlap):>3} "
              f"({pct:.0f}%) | HANYA milik AB/AC={len(only_ab):>3}")

    print(f"\nTOTAL: {total_overlap}/{total_ab} tanggal trigger AB/AC ({total_overlap/total_ab*100:.0f}%) "
          f"SUDAH tertangkap GABUNGAN.")
    unique_ab = total_ab - total_overlap
    print(f"Cuma {unique_ab} tanggal trigger yang BENAR-BENAR baru (tidak ditangkap GABUNGAN sama sekali).")


if __name__ == "__main__":
    main()
