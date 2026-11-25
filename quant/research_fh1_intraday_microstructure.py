#!/usr/bin/env python3
"""Fase FH-1: Out-of-Sample Evaluation of Intraday Microstructure Features (186k 15m bars)
Tests two institutional microstructure features on entry day (2026-08-26..2026-11-24):
  1. close_vs_vwap_pct: (EntryClose - DailyVWAP) / DailyVWAP * 100
  2. late_session_vol_ratio: Volume(14:30..16:00) / TotalDailyVolume * 100
Split strictly into Discovery (Aug 26 - Oct 14) vs Holdout (Oct 15 - Nov 25).
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
import pymysql

SOCKET_PATH = "/Applications/XAMPP/xamppfiles/var/mysql/mysql.sock"
DB_NAME = "sentimena_dashboard"
REPORTS_DIR = Path("/Applications/XAMPP/xamppfiles/htdocs/Implementasi AnalisisSentimenBerita/laravel-app/reports")


def get_conn():
    return pymysql.connect(user="root", unix_socket=SOCKET_PATH, database=DB_NAME, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor)


def main():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, ticker, strategy_label, signal_quality, entry_date, exit_date,
                       entry_price, pnl_percent, pnl_total, result
                FROM trades
                WHERE status='closed' AND entry_date >= '2026-08-26' AND pnl_percent IS NOT NULL
                ORDER BY entry_date ASC, id ASC
            """)
            trades = pd.DataFrame(cur.fetchall())

            tks = tuple(sorted(trades["ticker"].str.upper().unique().tolist()))
            ph = ",".join(["%s"] * len(tks))
            cur.execute(
                f"""
                SELECT stock_code AS ticker, bar_time, close, volume
                FROM intraday_prices
                WHERE stock_code IN ({ph})
                ORDER BY stock_code, bar_time ASC
                """,
                tks,
            )
            bars = pd.DataFrame(cur.fetchall())
    finally:
        conn.close()

    bars["bar_time"] = pd.to_datetime(bars["bar_time"])
    bars["date"] = bars["bar_time"].dt.strftime("%Y-%m-%d")
    bars["hhmm"] = bars["bar_time"].dt.strftime("%H:%M")
    bars["close"] = bars["close"].astype(float)
    bars["volume"] = bars["volume"].astype(float)

    # Aggregate daily microstructure features per (ticker, date)
    feat_rows = []
    for (tk, dt), grp in bars.groupby(["ticker", "date"]):
        tot_v = grp["volume"].sum()
        if tot_v <= 0:
            continue
        vwap = (grp["close"] * grp["volume"]).sum() / tot_v
        close_px = grp["close"].iloc[-1]
        late_v = grp[grp["hhmm"] >= "14:30"]["volume"].sum()
        feat_rows.append({
            "ticker": tk.upper(),
            "entry_date": dt,
            "close_vs_vwap_pct": (close_px - vwap) / vwap * 100.0 if vwap > 0 else np.nan,
            "late_vol_ratio": (late_v / tot_v) * 100.0,
        })
    fdf = pd.DataFrame(feat_rows)

    trades["ticker"] = trades["ticker"].str.upper()
    trades["entry_date"] = pd.to_datetime(trades["entry_date"]).dt.strftime("%Y-%m-%d")
    trades["pnl_percent"] = trades["pnl_percent"].astype(float)
    merged = trades.merge(fdf, on=["ticker", "entry_date"], how="inner")
    merged["fold"] = np.where(merged["entry_date"] < "2026-10-15", "Discovery", "Holdout")

    print(f"Matched {len(merged)} trades with entry-day 15m microstructure features.")

    def bucket_stats(df_sub: pd.DataFrame, col: str, bins: list, labels: list) -> list[dict]:
        tmp = df_sub.copy()
        tmp["bkt"] = pd.cut(tmp[col], bins=bins, labels=labels)
        rows = []
        for lbl in labels:
            g = tmp[tmp["bkt"] == lbl]
            if g.empty:
                continue
            gw = float(g[g["pnl_percent"] > 0]["pnl_percent"].sum())
            gl = float(-g[g["pnl_percent"] < 0]["pnl_percent"].sum())
            d_g = g[g["fold"] == "Discovery"]
            h_g = g[g["fold"] == "Holdout"]
            rows.append({
                "bucket": lbl,
                "n": len(g),
                "wr": round(float((g["pnl_percent"] > 0).mean() * 100.0), 1),
                "avg": round(float(g["pnl_percent"].mean()), 2),
                "pf": round(gw / gl, 2) if gl > 0 else 99.0,
                "disc_wr": round(float((d_g["pnl_percent"] > 0).mean() * 100.0), 1) if len(d_g) else 0.0,
                "hold_wr": round(float((h_g["pnl_percent"] > 0).mean() * 100.0), 1) if len(h_g) else 0.0,
                "hold_avg": round(float(h_g["pnl_percent"].mean()), 2) if len(h_g) else 0.0,
            })
        return rows

    vwap_stats = bucket_stats(
        merged, "close_vs_vwap_pct",
        [-100, -1.5, 0.0, 1.5, 100],
        ["Deep Below VWAP (<-1.5%)", "Below VWAP (-1.5%..0%)", "Above VWAP (0%..+1.5%)", "Strong Above VWAP (>+1.5%)"],
    )
    late_stats = bucket_stats(
        merged, "late_vol_ratio",
        [-1, 15, 30, 45, 101],
        ["Dry Late (<15%)", "Normal Late (15-30%)", "Strong Late (30-45%)", "Climax Late (>45%)"],
    )

    print("\n=== 1. CLOSE VS INTRADAY VWAP (OOS SPLIT) ===")
    for r in vwap_stats:
        print(f"  {r['bucket']:28s} | N={r['n']:3d} | WR={r['wr']:5.1f}% | Avg={r['avg']:+5.2f}% | PF={r['pf']:5.2f} | DiscWR={r['disc_wr']:5.1f}% | HoldWR={r['hold_wr']:5.1f}% (HoldAvg={r['hold_avg']:+5.2f}%)")

    print("\n=== 2. LATE-SESSION VOLUME RATIO 14:30-16:00 (OOS SPLIT) ===")
    for r in late_stats:
        print(f"  {r['bucket']:28s} | N={r['n']:3d} | WR={r['wr']:5.1f}% | Avg={r['avg']:+5.2f}% | PF={r['pf']:5.2f} | DiscWR={r['disc_wr']:5.1f}% | HoldWR={r['hold_wr']:5.1f}% (HoldAvg={r['hold_avg']:+5.2f}%)")

    lines = [
        "# Laporan Riset Kuantitatif Fase FH-1: Evaluasi OOS Fitur *Intraday Microstructure* (`VWAP` & *Late-Session Volume*)",
        "",
        f"> **Tanggal Riset**: 26 November 2026  ",
        f"> **Dataset**: `{len(merged)}` trade dengan bar 15-menit hari entry (`intraday_prices`, `2026-08-26` s/d `2026-11-24`), split Discovery vs Holdout Krisis.",
        "",
        "## 1. Posisi Harga Penutupan vs Intraday VWAP (`close_vs_vwap_pct`)",
        "",
        "| Bucket VWAP | N | WR (%) | Avg PnL (%) | PF | Disc WR | **Holdout WR** | **Holdout Avg** |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for r in vwap_stats:
        lines.append(f"| {r['bucket']} | {r['n']} | {r['wr']:.1f}% | {r['avg']:+.2f}% | **{r['pf']:.2f}** | {r['disc_wr']:.1f}% | **{r['hold_wr']:.1f}%** | **{r['hold_avg']:+.2f}%** |")

    lines.extend([
        "",
        "## 2. Rasio Volume Penutupan Sesi 2 (`14:30–16:00` / Total Harian)",
        "",
        "| Bucket Late-Session Vol | N | WR (%) | Avg PnL (%) | PF | Disc WR | **Holdout WR** | **Holdout Avg** |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ])
    for r in late_stats:
        lines.append(f"| {r['bucket']} | {r['n']} | {r['wr']:.1f}% | {r['avg']:+.2f}% | **{r['pf']:.2f}** | {r['disc_wr']:.1f}% | **{r['hold_wr']:.1f}%** | **{r['hold_avg']:+.2f}%** |")

    out_path = REPORTS_DIR / "research_fh1_intraday_microstructure_20261126.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written to: {out_path}")


if __name__ == "__main__":
    main()
