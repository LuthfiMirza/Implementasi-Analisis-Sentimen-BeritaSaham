#!/usr/bin/env python3
"""Fase CS Pass 1: backtest ide bottom-rebound user (19 Agu 2026).

Konsep (BUKAN aturan yang sudah live):
  - Bottom = harga terendah dalam 10 hari BURSA terakhir (proxy "10 hari kalender" user; data
    yfinance daily hanya berisi hari bursa, jadi 10 bar ≈ 2 minggu kalender).
  - Trigger BUY = closing hari X >= bottom_10d(X-1) * 1.05 (naik >=5% dari titik bawah),
    DAN closing hari X-1 masih < bottom_10d(X-1) * 1.05 (cross fresh, bukan re-trigger).
  - Entry = closing hari trigger (bar close, sesuai asumsi yang sudah disepakati).
  - Exit = trailing stop 2% dari puncak sejak entry (persis instruksi user).
  - Round-trip cost = 0.8% (konsisten dengan backtest GABUNGAN/MOMENTUM).
  - Max holding = 30 hari bursa (BATAS BACKTEST supaya posisi tidak "open selamanya" kalau
    trailing tidak pernah trigger -- di produksi live, keputusan hold/close ada di user).
  - Episode independence = jeda trigger <=15 hari kalender per ticker = 1 episode
    (protokol sama dengan Fase AY/BK/BQ, supaya angka bisa dibandingkan).

Beda paradigma dari GABUNGAN yang sudah live: GABUNGAN entry saat harga MASIH turun
(ret_2d <=-5% atau drawdown_20d <=-20%), taruhannya rebound teknikal. Ide ini KEBALIKANNYA:
tunggu bottom terkonfirmasi dulu (+5% dari titik bawah), baru masuk. Bukan "tangkap pisau
jatuh", tapi "tangkap bola pantul yang sudah kepastian bounce."

Data: yfinance close harian 2 tahun (~500 bar per saham). Kalau lulus gate P1-P4, baru Pass
2 (verifikasi presisi intraday 15-menit di sampel 60 hari terakhir).

Universe backtest awal: BUMI + DEWA saja (sesuai permintaan user "testing ke DEWA dan BUMI dulu").

Jalankan: python3 quant/drawdown_bounce_tracker/backtest_bottom_rebound.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent))
from screen_candidates import to_episodes, MIN_EPISODES, BOOTSTRAP_N  # noqa: E402

# Parameter (semua bisa dituning nanti kalau P1 lulus):
BOTTOM_WINDOW = 10           # bar bursa untuk rolling min (~2 minggu kalender)
REBOUND_THRESHOLD = 0.05     # trigger buy kalau harga >= bottom * (1 + this)
# Fase CS Pass 1b: banding beberapa nilai trailing (user minta setelah Pass 1a menunjukkan
# posisi hampir selalu tutup di hari yang sama karena trailing 2% terlalu ketat vs volatilitas
# BUMI/DEWA ~5-6% ATR). Longgar sedikit = winner boleh lari lebih jauh, tapi loser juga
# lebih besar. Tabel perbandingan bikin trade-off-nya kelihatan.
TRAILING_STOPS = [0.02, 0.03, 0.04]
ROUND_TRIP_COST = 0.008      # 0.8% biaya beli+jual (konsisten dgn backtest lain)
MAX_HOLDING_BARS = 30        # batas backtest saja, bukan aturan produksi
UNIVERSE = ["BUMI", "DEWA"]
START_DATE = "2024-01-01"


def fetch(ticker: str) -> pd.DataFrame | None:
    df = yf.download(f"{ticker}.JK", start=START_DATE, progress=False, auto_adjust=False)
    if df.empty or len(df) < BOTTOM_WINDOW + 30:
        return None
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df.reset_index().rename(columns={"Date": "date"})
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["bottom_10d"] = df["Close"].rolling(BOTTOM_WINDOW).min()
    return df


def simulate_trade(df: pd.DataFrame, entry_idx: int, trailing_stop: float) -> dict | None:
    """Hitung 1 trade: entry closing hari trigger, keluar saat trailing-stop 2% tersentuh atau
    max holding. Pakai High/Low harian buat cek trailing (bukan Close saja) -- ini konservatif:
    kalau pullback intraday sudah cukup, hitung stop kena walaupun close pulih."""
    entry_price = df.iloc[entry_idx]["Close"]
    if pd.isna(entry_price) or entry_price <= 0:
        return None

    peak = entry_price
    for d in range(1, MAX_HOLDING_BARS + 1):
        day_idx = entry_idx + d
        if day_idx >= len(df):
            return None  # posisi belum selesai -- jangan dihitung setengah jalan
        row = df.iloc[day_idx]
        if pd.isna(row["Close"]):
            return None

        # Puncak naik dulu (kalau intraday High baru), baru cek stop
        if not pd.isna(row["High"]) and row["High"] > peak:
            peak = float(row["High"])
        stop_level = peak * (1 - trailing_stop)

        if not pd.isna(row["Low"]) and row["Low"] <= stop_level:
            exit_price = stop_level
            exit_idx = day_idx
            reason = "trailing_stop"
            break

        if d == MAX_HOLDING_BARS:
            exit_price = float(row["Close"])
            exit_idx = day_idx
            reason = "max_holding"
    else:
        return None

    net_ret = float(exit_price / entry_price - 1 - ROUND_TRIP_COST)
    return {
        "trigger_date": df.iloc[entry_idx]["date"],
        "entry_date": df.iloc[entry_idx]["date"],
        "exit_date": df.iloc[exit_idx]["date"],
        "entry_price": float(entry_price),
        "exit_price": float(exit_price),
        "peak_price": peak,
        "hold_bars": int(exit_idx - entry_idx),
        "exit_reason": reason,
        "net_ret": net_ret,
    }


def collect_trades(df: pd.DataFrame, trailing_stop: float) -> list[dict]:
    """Cari semua bar yang cross above bottom * (1 + REBOUND_THRESHOLD) hari itu, sedangkan hari
    sebelumnya masih di bawah -- ini "first cross" agar tidak trigger tiap hari selagi harga di
    zona konfirmasi."""
    trades = []
    for i in range(BOTTOM_WINDOW, len(df) - 1):
        # Bottom yang jadi patokan = bottom SEBELUM hari trigger (tidak termasuk hari trigger)
        # -- kalau termasuk, harga trigger sendiri bisa jadi bottom-nya, jadi 0% cross. Absurd.
        bottom_prev = df.iloc[i - 1]["bottom_10d"]
        if pd.isna(bottom_prev):
            continue
        threshold = bottom_prev * (1 + REBOUND_THRESHOLD)

        close_prev = df.iloc[i - 1]["Close"]
        close_now = df.iloc[i]["Close"]
        if pd.isna(close_prev) or pd.isna(close_now):
            continue

        # "First cross": kemarin masih di bawah threshold, hari ini di atas
        if not (close_prev < threshold and close_now >= threshold):
            continue

        trade = simulate_trade(df, i, trailing_stop)
        if trade:
            trades.append(trade)
    return trades


def gate_p1_p4(ep_ret: np.ndarray) -> dict:
    n_ep = len(ep_ret)

    def split_ok(frac: float) -> tuple[bool, float]:
        cut = int(n_ep * frac)
        hold = ep_ret[cut:]
        return (len(hold) > 0 and hold.mean() > 0), (hold.mean() * 100 if len(hold) else float("nan"))

    p1_70_ok, p1_70_val = split_ok(0.70)
    p1_60_ok, p1_60_val = split_ok(0.60)
    p1 = p1_70_ok and p1_60_ok

    keep = max(1, int(n_ep * 0.05))
    sorted_ret = np.sort(ep_ret)
    excl_top = sorted_ret[:-keep] if keep < n_ep else sorted_ret
    p3_val = excl_top.sum() * 100
    p3 = p3_val > 0

    rng = np.random.default_rng(42)
    boot = rng.choice(ep_ret, size=(BOOTSTRAP_N, n_ep), replace=True).mean(axis=1)
    ci_lo, ci_hi = float(np.percentile(boot, 2.5)) * 100, float(np.percentile(boot, 97.5)) * 100
    p4 = ci_lo > 0

    return {
        "p1": p1, "p1_70_val": p1_70_val, "p1_60_val": p1_60_val,
        "p3": p3, "p3_val": p3_val,
        "p4": p4, "ci_lo": ci_lo, "ci_hi": ci_hi,
        "n_ep": n_ep,
        "win_rate_ep": float((ep_ret > 0).mean() * 100),
        "mean_ep": float(ep_ret.mean() * 100),
        "median_ep": float(np.median(ep_ret) * 100),
    }


def run_variant(dfs: dict[str, pd.DataFrame], trailing_stop: float) -> dict:
    """Jalankan backtest 1 nilai trailing_stop, return ringkasan angka semua ticker + gabungan."""
    per_ticker = {}
    for ticker, df in dfs.items():
        trades = collect_trades(df, trailing_stop)
        per_ticker[ticker] = trades

    result = {"trailing": trailing_stop, "per_ticker": {}}
    for ticker, trades in per_ticker.items():
        eps = to_episodes(trades)
        n_ep = len(eps)
        row = {
            "n_trades": len(trades), "n_ep": n_ep,
            "avg_hold": float(np.mean([t["hold_bars"] for t in trades])) if trades else 0,
        }
        if n_ep >= MIN_EPISODES:
            ep_ret = np.array([np.mean([t["net_ret"] for t in ep]) for ep in eps])
            row.update(gate_p1_p4(ep_ret))
        result["per_ticker"][ticker] = row

    # Gabungan
    all_eps = []
    for trades in per_ticker.values():
        all_eps += to_episodes(trades)
    all_eps.sort(key=lambda ep: ep[0]["trigger_date"])
    row = {"n_trades": sum(len(t) for t in per_ticker.values()), "n_ep": len(all_eps)}
    row["avg_hold"] = float(np.mean([t["hold_bars"] for tl in per_ticker.values() for t in tl])) \
                       if row["n_trades"] else 0
    if len(all_eps) >= MIN_EPISODES:
        ep_ret = np.array([np.mean([t["net_ret"] for t in ep]) for ep in all_eps])
        row.update(gate_p1_p4(ep_ret))
    result["gabungan"] = row
    return result


def print_variant_table(variants: list[dict]) -> None:
    """Tabel banding trailing 2%/3%/4% per baris (ticker), per kolom (trailing)."""
    tickers = list(variants[0]["per_ticker"].keys()) + ["GABUNGAN"]
    print(f"\n{'='*78}\nTABEL BANDING trailing 2% vs 3% vs 4%\n{'='*78}\n")
    print(f"{'Metrik':<25}", end="")
    for v in variants:
        print(f"{'trail '+str(int(v['trailing']*100))+'%':>17}", end="")
    print()
    print("-" * (25 + 17 * len(variants)))

    for ticker in tickers:
        print(f"\n[{ticker}]")
        rows = [v["gabungan"] if ticker == "GABUNGAN" else v["per_ticker"][ticker] for v in variants]

        def fmt_row(label, fn):
            print(f"  {label:<23}", end="")
            for r in rows:
                print(f"{fn(r):>17}", end="")
            print()

        fmt_row("Trade mentah", lambda r: str(r["n_trades"]))
        fmt_row("Episode", lambda r: str(r["n_ep"]))
        fmt_row("Avg hold (bar)", lambda r: f"{r['avg_hold']:.1f}")
        fmt_row("WR episode", lambda r: f"{r.get('win_rate_ep', 0):.1f}%" if "win_rate_ep" in r else "-")
        fmt_row("Mean/ep", lambda r: f"{r.get('mean_ep', 0):+.2f}%" if "mean_ep" in r else "-")
        fmt_row("CI95 lower", lambda r: f"{r.get('ci_lo', 0):+.2f}%" if "ci_lo" in r else "-")
        fmt_row("CI95 upper", lambda r: f"{r.get('ci_hi', 0):+.2f}%" if "ci_hi" in r else "-")
        fmt_row("Gate P1-P4", lambda r: (
            f"{sum([r.get('p1',False), r.get('p3',False), r.get('p4',False)])}/3"
            + (" LULUS" if sum([r.get('p1',False), r.get('p3',False), r.get('p4',False)]) == 3 else " PARSIAL")
        ) if "p1" in r else "TIPIS")


def main() -> None:
    print(f"Fase CS Pass 1 -- backtest bottom-rebound daily (BOTTOM_WINDOW={BOTTOM_WINDOW}, "
          f"REBOUND={REBOUND_THRESHOLD*100:.0f}%, COST={ROUND_TRIP_COST*100:.1f}%)")
    print(f"Data: yfinance {START_DATE}--now, universe: {UNIVERSE}, "
          f"trailing tested: {[str(int(t*100))+'%' for t in TRAILING_STOPS]}\n")

    dfs = {}
    for ticker in UNIVERSE:
        df = fetch(ticker)
        if df is None:
            print(f"{ticker}: data tidak cukup, dilewati.")
            continue
        dfs[ticker] = df

    variants = [run_variant(dfs, ts) for ts in TRAILING_STOPS]
    print_variant_table(variants)

    # Rekomendasi otomatis: mana trailing yg CI95 lower BUMI di atas nol DAN gabungan mean tertinggi
    print(f"\n{'='*78}\nREKOMENDASI (mesti tetap dilihat manual, ini pointer saja)\n{'='*78}")
    for v in variants:
        bumi = v["per_ticker"].get("BUMI", {})
        gab = v["gabungan"]
        bumi_p4 = bumi.get("p4", False)
        bumi_ci = bumi.get("ci_lo", None)
        gab_mean = gab.get("mean_ep", None)
        print(f"  trail {int(v['trailing']*100)}%: BUMI P4={'LULUS' if bumi_p4 else 'GAGAL'} "
              f"(CI95lo={bumi_ci:+.2f}%)"
              if bumi_ci is not None else f"  trail {int(v['trailing']*100)}%: BUMI sampel tipis", end="")
        print(f" | Gabungan mean/ep {gab_mean:+.2f}%" if gab_mean is not None else " | Gabungan tipis")


if __name__ == "__main__":
    main()
