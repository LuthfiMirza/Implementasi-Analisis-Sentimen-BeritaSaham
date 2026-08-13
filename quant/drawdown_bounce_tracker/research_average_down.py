#!/usr/bin/env python3
"""Fase BR: apakah "nambah muatan" (averaging down) memperbaiki hasil?

Dipicu pertanyaan nyata user saat DEWA mundur dari puncak: worth it nggak nambah posisi?
Sistem ini TIDAK punya jawaban berbasis bukti untuk itu -- SEMUA backtest sebelumnya
mengasumsikan satu entry per sinyal, modal tetap, satu posisi per saham (register_open_position()
bahkan MENGGANTI posisi, bukan menambah). Script ini mengisi kekosongan itu.

DUA JEBAKAN METODOLOGI yang ditangani eksplisit:

1. **Eksposur tidak sebanding.** Nambah muatan = modal berisiko DOBEL. Kalau cuma dibandingkan
   "% return terhadap harga rata-rata", averaging down otomatis menang di pasar naik -- padahal
   sisi ruginya juga dobel. Karena itu dilaporkan BERSAMAAN:
     - % return terhadap harga rata-rata (pertanyaan "apakah harga rata-rata saya membaik")
     - P&L absolut per 1 unit modal awal (menangkap eksposur 2x yang sebenarnya)
     - worst-case / rata-rata episode RUGI saja (menangkap sisi buruknya, bukan cuma rata-rata)

2. **Bentrok dengan trailing stop.** Untuk sinyal non-"ganda", produksi KELUAR saat mundur 2% --
   bentrok langsung dengan "tambah saat mundur 2%". Tidak mungkin dua-duanya. Jadi exit dibuat
   B&H 10 hari untuk SEMUA varian, supaya efek averaging down terisolasi dan perbandingannya
   apple-to-apple. Konsekuensinya: hasil di sini TIDAK otomatis berlaku untuk aturan produksi
   non-"ganda" yang masih pakai trailing stop.

Dua definisi "nambah muatan" diuji terpisah, karena artinya beda:
  - dari ENTRY : harga turun X% DI BAWAH harga beli  -> averaging down harfiah (harga rata2 turun)
  - dari PUNCAK: harga mundur X% dari puncak sejak entry -> kasus DEWA (masih untung dari entry)

Gate: episode independence (<=15 hari kalender = 1 episode) + bootstrap CI95 di level episode,
sama seperti Fase BP/BQ.

Jalankan: python3 quant/drawdown_bounce_tracker/research_average_down.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from detect_signal import DROP_THRESHOLD, DRAWDOWN_THRESHOLD  # noqa: E402
from screen_candidates import (  # noqa: E402
    EPISODE_GAP_DAYS,
    ROUND_TRIP_COST,
    TARGET_HOLD_DAYS,
    fetch,
    to_episodes,
)

TICKERS = ["BUMI", "DEWA", "BRPT", "ESSA", "UNVR"]  # 5 saham aturan gabungan
ADD_THRESHOLDS = [0.02, 0.03, 0.05]
BOOTSTRAP_N = 10_000


def run_trade(df: pd.DataFrame, trigger_idx: int, mode: str, thr: float | None) -> dict | None:
    """mode: 'base' | 'entry' (turun X% di bawah entry) | 'peak' (mundur X% dari puncak).

    Exit SELALU B&H 10 hari bursa (lihat catatan bentrok trailing-stop di docstring modul)."""
    entry_idx = trigger_idx + 1
    if entry_idx >= len(df):
        return None
    entry = df.iloc[entry_idx]["Close"]
    if pd.isna(entry) or entry <= 0:
        return None

    add_price = None
    peak = entry

    for d in range(1, TARGET_HOLD_DAYS + 1):
        j = entry_idx + d
        if j >= len(df):
            return None  # posisi belum selesai -- jangan dihitung setengah jalan
        row = df.iloc[j]
        if pd.isna(row["Close"]):
            return None

        if mode != "base" and add_price is None:
            low = row["Low"]
            if not pd.isna(low):
                # Pakai Low (intraday) supaya konsisten dengan cara trailing stop dideteksi.
                target = entry * (1 - thr) if mode == "entry" else peak * (1 - thr)
                if low <= target:
                    add_price = float(target)
        if not pd.isna(row["High"]) and row["High"] > peak:
            peak = row["High"]

        if d == TARGET_HOLD_DAYS:
            exit_px = float(row["Close"])
            break

    if add_price is None:  # tidak pernah kena trigger tambah -> identik dengan baseline
        avg_cost, units = float(entry), 1.0
    else:
        avg_cost, units = (float(entry) + add_price) / 2, 2.0

    pct = exit_px / avg_cost - 1 - ROUND_TRIP_COST
    # P&L absolut dinyatakan per 1 unit modal AWAL -- inilah yang menangkap eksposur 2x:
    # nambah muatan menggandakan untung DAN rugi dalam satuan yang sama.
    abs_pnl = pct * units

    return {
        "trigger_date": df.iloc[trigger_idx]["date"],
        "added": add_price is not None,
        "pct": float(pct),
        "abs_pnl": float(abs_pnl),
        "units": units,
    }


def collect(df: pd.DataFrame, mode: str, thr: float | None) -> list[dict]:
    out = []
    for i in range(len(df)):
        r2, dd = df.iloc[i]["ret_2d"], df.iloc[i]["dd_20d"]
        if pd.isna(r2) or pd.isna(dd):
            continue
        if not (r2 <= DROP_THRESHOLD or dd <= DRAWDOWN_THRESHOLD):
            continue
        t = run_trade(df, i, mode, thr)
        if t:
            out.append(t)
    return out


def summarise(per_ticker: dict[str, list[dict]], label: str) -> dict:
    """Episode dikelompokkan PER SAHAM dulu, baru digabung.

    Bug yang sempat terjadi: menggabung trade semua saham SEBELUM di-episode-kan membuat trigger
    5 saham di tanggal yang sama (crash market-wide) melebur jadi SATU episode -- sampel jatuh ke
    9 episode untuk 5 saham dan CI95-nya jadi tidak berarti."""
    eps = []
    for trades_t in per_ticker.values():
        eps += to_episodes(trades_t)
    trades = [t for lst in per_ticker.values() for t in lst]

    pct = np.array([np.mean([t["pct"] for t in e]) for e in eps])
    absp = np.array([np.mean([t["abs_pnl"] for t in e]) for e in eps])
    losers = absp[absp < 0]

    # UKURAN PENENTU: P&L per unit modal yang BENAR-BENAR dikerahkan. Varian "tambah" memakai
    # ~2x modal, jadi P&L absolutnya wajar lebih besar -- yang penting apakah lebih besarnya
    # SEBANDING dengan modal ekstranya. Kalau return per unit turun, artinya modal ekstra itu
    # lebih baik dipakai di tempat lain (mis. sinyal lain), bukan ditumpuk di posisi yang sama.
    units_ep = np.array([np.mean([t["units"] for t in e]) for e in eps])
    per_unit = float((absp / units_ep).mean() * 100)

    rng = np.random.default_rng(42)
    boot = rng.choice(absp, size=(BOOTSTRAP_N, len(absp)), replace=True).mean(axis=1)

    return {
        "label": label,
        "n_ep": len(eps),
        "per_unit": per_unit,
        "avg_units": float(units_ep.mean()),
        "add_rate": float(np.mean([t["added"] for t in trades]) * 100) if trades else 0.0,
        "pct_mean": float(pct.mean() * 100),
        "abs_mean": float(absp.mean() * 100),
        "abs_median": float(np.median(absp) * 100),
        "winrate": float((absp > 0).mean() * 100),
        "loss_mean": float(losers.mean() * 100) if len(losers) else 0.0,
        "loss_worst": float(absp.min() * 100),
        "ci95_lo": float(np.percentile(boot, 2.5) * 100),
    }


def main() -> None:
    print("Fase BR -- apakah nambah muatan (averaging down) memperbaiki hasil?")
    print(f"Saham: {', '.join(TICKERS)} | exit: B&H {TARGET_HOLD_DAYS} hari (SEMUA varian, "
          f"supaya tidak bentrok trailing stop)")
    print("Metrik utama = P&L per 1 unit modal AWAL (menangkap eksposur 2x). "
          "Semua di level episode.\n")

    data = {}
    for t in TICKERS:
        d = fetch(t)
        if d is not None:
            data[t] = d

    variants = [("base", None, "Baseline (1x entry)")]
    for thr in ADD_THRESHOLDS:
        variants.append(("entry", thr, f"Tambah saat -{thr:.0%} DI BAWAH ENTRY"))
    for thr in ADD_THRESHOLDS:
        variants.append(("peak", thr, f"Tambah saat -{thr:.0%} dari PUNCAK"))

    rows = []
    for mode, thr, label in variants:
        per_ticker = {t: collect(df, mode, thr) for t, df in data.items()}
        rows.append(summarise(per_ticker, label))

    hdr = (f"{'Varian':<32}{'n_ep':>5}{'modal':>7}{'P&L tot':>9}{'PER UNIT':>10}"
           f"{'WR':>6}{'rugi rata2':>12}{'terburuk':>10}")
    print(hdr)
    print("-" * len(hdr))
    base = rows[0]
    for r in rows:
        mark = ""
        if r is not base:
            mark = "  <= per-unit LEBIH BURUK" if r["per_unit"] < base["per_unit"] else "  <= per-unit lebih baik"
        print(f"{r['label']:<32}{r['n_ep']:>5}{r['avg_units']:>6.2f}x{r['abs_mean']:>+8.2f}%"
              f"{r['per_unit']:>+9.2f}%{r['winrate']:>5.0f}%{r['loss_mean']:>+11.2f}%"
              f"{r['loss_worst']:>+9.2f}%{mark}")

    print("\nCatatan baca:")
    print("  'P&L tot'  = P&L per 1 unit modal AWAL -- sudah memperhitungkan eksposur ganda.")
    print("  'PER UNIT' = P&L per rupiah yang BENAR-BENAR dikerahkan. INI ukuran penentunya:")
    print("               kalau turun, modal ekstra lebih baik dipakai di sinyal lain daripada")
    print("               ditumpuk di posisi yang sama.")
    print("  'rugi rata2'/'terburuk' = sisi buruk yang tersembunyi di balik rata-rata.")
    print()
    print(f"  Pembanding adil: modal 2x dipakai di DUA sinyal terpisah (baseline) menghasilkan")
    print(f"  {base['per_unit']:+.2f}% per unit -- bandingkan dengan kolom PER UNIT tiap varian.")


if __name__ == "__main__":
    main()
