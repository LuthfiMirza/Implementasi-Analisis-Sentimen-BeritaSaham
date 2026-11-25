#!/usr/bin/env python3
"""Fase FH-2: Walk-Forward OOS Backtest on 186k 15m Bars & Official IDX Summaries:
  Part 1: DAY2_FLUSH_CATCHER (Otomatisasi Skenario B — Day-1 Dead Low -> Day-2 Morning Flush Reversal)
  Part 2: Regime-Gated BSJP & BOTTOM_REBOUND (Breadth + Upper Wick + Late-Session Filter)
Strictly split into Discovery (Aug 26 - Oct 14) vs Holdout (Oct 15 - Nov 25), including 0.40% fee.
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
import pymysql

SOCKET_PATH = "/Applications/XAMPP/xamppfiles/var/mysql/mysql.sock"
DB_NAME = "sentimena_dashboard"
FEE_RT = 0.004  # 0.40% round trip
REPORTS_DIR = Path("/Applications/XAMPP/xamppfiles/htdocs/Implementasi AnalisisSentimenBerita/laravel-app/reports")


def get_conn():
    return pymysql.connect(user="root", unix_socket=SOCKET_PATH, database=DB_NAME, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor)


def load_15m_and_daily():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT stock_code AS ticker, bar_time, open, high, low, close, volume
                FROM intraday_prices
                ORDER BY stock_code, bar_time ASC
            """)
            bars = pd.DataFrame(cur.fetchall())

            cur.execute("""
                SELECT trade_date, stock_code AS ticker, previous, open, high, low, close, pct_change, volume, value, foreign_net_value
                FROM idx_daily_summaries
                WHERE source = 'idx_scrape' AND trade_date >= '2026-08-01' AND volume > 0
                ORDER BY trade_date ASC
            """)
            idx_df = pd.DataFrame(cur.fetchall())
    finally:
        conn.close()

    bars["bar_time"] = pd.to_datetime(bars["bar_time"])
    for c in ["open", "high", "low", "close", "volume"]:
        bars[c] = bars[c].astype(float)
    bars["date"] = bars["bar_time"].dt.strftime("%Y-%m-%d")
    bars["hhmm"] = bars["bar_time"].dt.strftime("%H:%M")

    idx_df["trade_date"] = pd.to_datetime(idx_df["trade_date"]).dt.strftime("%Y-%m-%d")
    for c in ["previous", "open", "high", "low", "close", "pct_change", "volume", "value", "foreign_net_value"]:
        idx_df[c] = idx_df[c].astype(float)
    return bars, idx_df


def backtest_day2_flush(bars: pd.DataFrame) -> pd.DataFrame:
    """Detect Day-1 Dead Low (ret_1d <= -5% and lower_wick < 0.8%, val >= Rp 5B).
    On Day-2 morning (09:00-10:30), wait for flush <= -2.5% below Day-1 close, then enter on
    the FIRST green 15m reversal bar (close > open). Exit at TP (+4.0%), SL (-2.5%), or Day-2 15:45 close."""
    # Build daily OHLCV from 15m
    daily = bars.groupby(["ticker", "date"]).agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), volume=("volume", "sum"),
    ).reset_index().sort_values(["ticker", "date"])
    daily["prev_close"] = daily.groupby("ticker")["close"].shift(1)
    daily["ret_1d"] = (daily["close"] - daily["prev_close"]) / daily["prev_close"]
    daily["lower_wick"] = (daily["close"] - daily["low"]) / daily["low"]
    daily["val_b"] = daily["close"] * daily["volume"] / 1e9
    daily["next_date"] = daily.groupby("ticker")["date"].shift(-1)

    dead_lows = daily[
        (daily["ret_1d"] <= -0.05)
        & (daily["lower_wick"] < 0.008)
        & (daily["val_b"] >= 5.0)
        & (daily["next_date"].notna())
    ]

    bars_idx = {k: g.reset_index(drop=True) for k, g in bars.groupby(["ticker", "date"])}
    trades = []

    for _, ev in dead_lows.iterrows():
        key = (ev["ticker"], ev["next_date"])
        if key not in bars_idx:
            continue
        d2 = bars_idx[key]
        d1_close = float(ev["close"])
        flushed = False
        entry_px = None
        entry_idx = None

        for idx, b in d2.iterrows():
            if b["hhmm"] > "10:30":
                break
            if (b["low"] - d1_close) / d1_close <= -0.025:
                flushed = True
            if flushed and b["close"] > b["open"] and b["close"] < d1_close:
                entry_px = float(b["close"])
                entry_idx = idx
                break

        if entry_px is None or entry_idx is None:
            continue

        # Simulate exit from entry_idx+1 until Day-2 close
        sl_px = entry_px * (1.0 - 0.025)
        tp_px = entry_px * (1.0 + 0.040)
        exit_px = float(d2["close"].iloc[-1])
        exit_type = "eod_close"
        mfe = 0.0

        for _, b in d2.iloc[entry_idx + 1 :].iterrows():
            mfe = max(mfe, (float(b["high"]) - entry_px) / entry_px * 100.0)
            if float(b["low"]) <= sl_px:
                exit_px = sl_px
                exit_type = "stop_loss"
                break
            if float(b["high"]) >= tp_px:
                exit_px = tp_px
                exit_type = "take_profit"
                break

        net_ret = ((exit_px - entry_px) / entry_px - FEE_RT) * 100.0
        trades.append({
            "date": ev["next_date"],
            "fold": "Discovery" if ev["next_date"] < "2026-10-15" else "Holdout",
            "ticker": ev["ticker"],
            "d1_ret": round(ev["ret_1d"] * 100.0, 2),
            "entry_px": entry_px,
            "exit_px": exit_px,
            "net_ret": round(net_ret, 2),
            "mfe": round(mfe, 2),
            "exit_type": exit_type,
        })

    return pd.DataFrame(trades)


def backtest_bsjp_regime_gate(idx_df: pd.DataFrame) -> dict:
    """Backtest BSJP Momentum (Close>Open, chg 4%..15%, Val>=5B, Vol>=1.5x prev) with vs without
    Breadth >= 40% & Upper Wick <= 1.5% gate on official IDX summaries (Aug-Nov 2026)."""
    # Daily market breadth
    breadth = idx_df.groupby("trade_date").apply(lambda g: (g["pct_change"] > 0).mean() * 100.0).rename("breadth_pct")
    df = idx_df.sort_values(["ticker", "trade_date"]).copy()
    df["prev_vol"] = df.groupby("ticker")["volume"].shift(1)
    df["vol_ratio"] = df["volume"] / df["prev_vol"]
    df["u_wick"] = (df["high"] - df["close"]) / df["close"]
    df["next_open"] = df.groupby("ticker")["open"].shift(-1)
    df["next_high"] = df.groupby("ticker")["high"].shift(-1)
    df = df.merge(breadth, on="trade_date", how="left")

    base_cands = df[
        (df["close"] > df["open"])
        & (df["pct_change"] >= 4.0) & (df["pct_change"] <= 15.0)
        & (df["value"] >= 5e9)
        & (df["vol_ratio"] >= 1.5)
        & (df["next_open"].notna()) & (df["next_open"] > 0)
    ].copy()
    # Realistic BSJP exit: exit at next open (or TP +2.5% if open < TP and next_high >= TP)
    base_cands["open_ret"] = ((base_cands["next_open"] - base_cands["close"]) / base_cands["close"] - FEE_RT) * 100.0
    base_cands["fold"] = np.where(base_cands["trade_date"] < "2026-10-15", "Discovery", "Holdout")

    variants = {
        "0_BSJP_Base (4-15%, Vol>=1.5x, Val>=5B)": base_cands,
        "1_BSJP_UpperWick<=1.5%": base_cands[base_cands["u_wick"] <= 0.015],
        "2_BSJP_Breadth>=40%": base_cands[base_cands["breadth_pct"] >= 40.0],
        "3_BSJP_Breadth>=40% + UW<=1.5%": base_cands[(base_cands["breadth_pct"] >= 40.0) & (base_cands["u_wick"] <= 0.015)],
        "4_BSJP_Breadth>=40% + UW<=1.5% + ForeignBuy": base_cands[(base_cands["breadth_pct"] >= 40.0) & (base_cands["u_wick"] <= 0.015) & (base_cands["foreign_net_value"] > 0)],
    }
    out = {}
    for k, sub in variants.items():
        if sub.empty:
            out[k] = {"n": 0, "wr": 0, "avg": 0, "pf": 0, "disc_pf": 0, "hold_pf": 0, "hold_avg": 0}
            continue
        gw = float(sub[sub["open_ret"] > 0]["open_ret"].sum())
        gl = float(-sub[sub["open_ret"] < 0]["open_ret"].sum())
        ds = sub[sub["fold"] == "Discovery"]
        hs = sub[sub["fold"] == "Holdout"]
        dgw, dgl = float(ds[ds["open_ret"] > 0]["open_ret"].sum()), float(-ds[ds["open_ret"] < 0]["open_ret"].sum())
        hgw, hgl = float(hs[hs["open_ret"] > 0]["open_ret"].sum()), float(-hs[hs["open_ret"] < 0]["open_ret"].sum())
        out[k] = {
            "n": len(sub),
            "wr": round(float((sub["open_ret"] > 0).mean() * 100.0), 1),
            "avg": round(float(sub["open_ret"].mean()), 2),
            "pf": round(gw / gl, 2) if gl > 0 else 99.0,
            "disc_pf": round(dgw / dgl, 2) if dgl > 0 else 99.0,
            "hold_pf": round(hgw / hgl, 2) if hgl > 0 else 99.0,
            "hold_avg": round(float(hs["open_ret"].mean()), 2) if len(hs) else 0.0,
        }
    return out


def main():
    bars, idx_df = load_15m_and_daily()
    print(f"Loaded {len(bars):,} 15m bars & {len(idx_df):,} official IDX daily rows.")

    d2 = backtest_day2_flush(bars)
    print(f"\n=== PART 1: DAY2_FLUSH_CATCHER (n={len(d2)}, Fee 0.40% RT) ===")
    d2_rows = []
    for label, sub in [("ALL", d2), ("Discovery (Aug26-Oct14)", d2[d2["fold"] == "Discovery"]), ("Holdout (Oct15-Nov25)", d2[d2["fold"] == "Holdout"])]:
        if sub.empty:
            continue
        gw = float(sub[sub["net_ret"] > 0]["net_ret"].sum())
        gl = float(-sub[sub["net_ret"] < 0]["net_ret"].sum())
        pf = round(gw / gl, 2) if gl > 0 else 99.0
        wr = round(float((sub["net_ret"] > 0).mean() * 100.0), 1)
        avg = round(float(sub["net_ret"].mean()), 2)
        mfe = round(float(sub["mfe"].mean()), 2)
        print(f"  {label:24s} | N={len(sub):3d} | WR={wr:5.1f}% | AvgNet={avg:+5.2f}% | PF={pf:5.2f} | AvgMFE={mfe:+5.2f}%")
        d2_rows.append((label, len(sub), wr, avg, pf, mfe))

    bsjp_res = backtest_bsjp_regime_gate(idx_df)
    print("\n=== PART 2: REGIME-GATED BSJP MOMENTUM (NEXT-OPEN EXIT, FEE 0.40%) ===")
    for k, v in bsjp_res.items():
        print(f"  {k:44s} | N={v['n']:4d} | WR={v['wr']:5.1f}% | Avg={v['avg']:+5.2f}% | PF={v['pf']:5.2f} | DiscPF={v['disc_pf']:5.2f} | HoldPF={v['hold_pf']:5.2f} (HoldAvg={v['hold_avg']:+5.2f}%)")

    lines = [
        "# Laporan Riset Kuantitatif Fase FH-2: `DAY2_FLUSH_CATCHER` (Skenario B) & *Regime-Gated BSJP Momentum*",
        "",
        f"> **Tanggal Riset**: 26 November 2026  ",
        f"> **Dataset**: `{len(bars):,}` bar 15-menit (`intraday_prices`) & `{len(idx_df):,}` baris resmi `idx_daily_summaries` (`idx_scrape`), termasuk biaya broker `0,40%` *round-trip*.",
        "",
        "## 1. Backtest Intraday 15m: `DAY2_FLUSH_CATCHER` (Day-1 Dead Low → Day-2 Morning Flush Reversal)",
        "",
        "| Split | N | WR (%) | Avg Net (%) | PF | Avg Intraday MFE (%) |",
        "| :--- | :---: | :---: | :---: | :---: | :---: |",
    ]
    for lbl, n, wr, avg, pf, mfe in d2_rows:
        lines.append(f"| {lbl} | {n} | {wr:.1f}% | {avg:+.2f}% | **{pf:.2f}** | +{mfe:.2f}% |")

    lines.extend([
        "",
        "## 2. Backtest *Regime-Gated BSJP Momentum* (Exit Pembukaan H+1, Fee 0,40%)",
        "",
        "| Varian Filter BSJP | N | WR (%) | Avg Net (%) | PF | Disc PF | **Holdout PF** | **Holdout Avg** |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ])
    for k, v in bsjp_res.items():
        lines.append(f"| `{k}` | {v['n']} | {v['wr']:.1f}% | {v['avg']:+.2f}% | **{v['pf']:.2f}** | {v['disc_pf']:.2f} | **{v['hold_pf']:.2f}** | **{v['hold_avg']:+.2f}%** |")

    out_path = REPORTS_DIR / "research_fh2_day2_flush_bsjp_gate_20261126.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written to: {out_path}")


if __name__ == "__main__":
    main()
