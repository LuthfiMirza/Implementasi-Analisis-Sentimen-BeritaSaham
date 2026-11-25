#!/usr/bin/env python3
"""Fase FF-1: Walk-Forward OOS Backtest for Grade-Weighted Sizing, Market Breadth Gate,
and Conglomerate/Correlation Cluster Exposure Cap on Sentimena Closed Trades.

Evaluates strictly out-of-sample across chronological folds (F1..F4) including
the Oct-Nov 2026 crisis regime to prevent data-snooping.
"""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd
import pymysql

SOCKET_PATH = "/Applications/XAMPP/xamppfiles/var/mysql/mysql.sock"
DB_NAME = "sentimena_dashboard"
BASE_CAPITAL = 10_000_000.0
REPORTS_DIR = Path("/Applications/XAMPP/xamppfiles/htdocs/Implementasi AnalisisSentimenBerita/laravel-app/reports")

CLUSTERS = {
    "BUMI": "BAKRIE",
    "DEWA": "BAKRIE",
    "ENRG": "BAKRIE",
    "BRMS": "BAKRIE",
    "BRPT": "BARITO",
    "BREN": "BARITO",
    "CUAN": "BARITO",
    "TPIA": "BARITO",
    "PTRO": "BARITO_ENERGY",
    "RAJA": "HAPSORO_ENERGY",
    "BBCA": "BIG_BANKS",
    "BBRI": "BIG_BANKS",
    "BMRI": "BIG_BANKS",
    "BBNI": "BIG_BANKS",
    "SMGR": "CEMENT",
    "INTP": "CEMENT",
}


def get_conn():
    return pymysql.connect(
        user="root",
        unix_socket=SOCKET_PATH,
        db=DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, ticker, strategy_label, signal_quality,
                       entry_date, exit_date, entry_price, exit_price,
                       pnl_percent, pnl_total, result, holding_days, indicators_snapshot
                FROM trades
                WHERE status = 'closed' AND pnl_percent IS NOT NULL
                ORDER BY entry_date ASC, id ASC
            """)
            trades = pd.DataFrame(cur.fetchall())

            cur.execute("""
                SELECT s.code AS ticker, sp.price_date, sp.open, sp.high, sp.low, sp.close, sp.volume
                FROM stock_prices sp
                JOIN stocks s ON s.id = sp.stock_id
                WHERE sp.source <> 'seed' AND sp.close IS NOT NULL AND sp.price_date >= '2025-11-01'
                ORDER BY s.code, sp.price_date
            """)
            prices = pd.DataFrame(cur.fetchall())
    finally:
        conn.close()

    trades["entry_date"] = pd.to_datetime(trades["entry_date"])
    trades["exit_date"] = pd.to_datetime(trades["exit_date"].fillna(trades["entry_date"]))
    trades["pnl_percent"] = trades["pnl_percent"].astype(float)
    trades["pnl_total"] = trades["pnl_total"].astype(float)
    trades["ticker"] = trades["ticker"].str.upper().str.strip()
    trades["grade"] = trades["signal_quality"].fillna("B").str.upper().str.strip()

    prices["price_date"] = pd.to_datetime(prices["price_date"])
    prices["close"] = prices["close"].astype(float)
    return trades, prices


def compute_daily_breadth(prices: pd.DataFrame) -> pd.Series:
    p = prices.sort_values(["ticker", "price_date"]).copy()
    p["prev_close"] = p.groupby("ticker")["close"].shift(1)
    p["ret_1d"] = (p["close"] - p["prev_close"]) / p["prev_close"]
    p = p.dropna(subset=["ret_1d"])
    daily = p.groupby("price_date").agg(
        n=("ret_1d", "count"),
        up=("ret_1d", lambda s: (s > 0).sum()),
    )
    daily = daily[daily["n"] >= 10]
    return (daily["up"] / daily["n"] * 100.0).rename("breadth_pct")


def compute_rolling_corr_pairs(prices: pd.DataFrame) -> dict[pd.Timestamp, pd.DataFrame]:
    piv = prices.pivot_table(index="price_date", columns="ticker", values="close").pct_change()
    # Compute monthly correlation snapshots (strictly past 60 trading days, no lookahead)
    corr_map = {}
    dates = piv.index
    for i in range(60, len(dates)):
        if i == 60 or dates[i].month != dates[i - 1].month:
            window = piv.iloc[i - 60 : i]
            corr_map[dates[i]] = window.corr(min_periods=30)
    return corr_map


def get_cluster(ticker: str) -> str:
    return CLUSTERS.get(ticker, f"SINGLE_{ticker}")


def simulate_portfolio(
    df: pd.DataFrame,
    sizing_map: dict[str, float],
    min_breadth: float | None = None,
    cluster_cap: int | None = None,
    corr_cap: float | None = None,
    corr_map: dict[pd.Timestamp, pd.DataFrame] | None = None,
    skip_blacklist: bool = True,
) -> dict:
    active: list[dict] = []
    taken = []
    skipped_grade = 0
    skipped_breadth = 0
    skipped_cluster = 0
    skipped_blacklist = 0

    corr_dates = sorted(corr_map.keys()) if corr_map else []

    for _, r in df.iterrows():
        dt = r["entry_date"]
        tk = r["ticker"]
        grade = r["grade"]

        if skip_blacklist and tk in {"PSAB", "TLKM"}:
            skipped_blacklist += 1
            continue

        mult = sizing_map.get(grade, 1.0)
        if mult <= 0:
            skipped_grade += 1
            continue

        if min_breadth is not None and pd.notna(r["breadth_pct"]) and r["breadth_pct"] < min_breadth:
            skipped_breadth += 1
            continue

        # Prune closed positions strictly before current entry_date
        active = [a for a in active if a["exit_date"] > dt]

        if cluster_cap is not None:
            cl = get_cluster(tk)
            same_cl = sum(1 for a in active if a["cluster"] == cl)
            if same_cl >= cluster_cap:
                skipped_cluster += 1
                continue

        if corr_cap is not None and corr_map and corr_dates:
            # Find latest corr matrix <= dt
            prev_dates = [d for d in corr_dates if d <= dt]
            if prev_dates:
                cmat = corr_map[prev_dates[-1]]
                if tk in cmat.columns:
                    too_corr = any(
                        a["ticker"] in cmat.index
                        and pd.notna(cmat.loc[a["ticker"], tk])
                        and cmat.loc[a["ticker"], tk] >= corr_cap
                        for a in active
                    )
                    if too_corr:
                        skipped_cluster += 1
                        continue

        # Simulated Rp PnL using standardized BASE_CAPITAL * mult
        pnl_rp = BASE_CAPITAL * mult * (r["pnl_percent"] / 100.0)
        taken.append(
            {
                "entry_date": dt,
                "exit_date": r["exit_date"],
                "ticker": tk,
                "grade": grade,
                "mult": mult,
                "pnl_pct": r["pnl_percent"],
                "pnl_rp": pnl_rp,
                "result": r["result"],
                "fold": r["fold"],
            }
        )
        active.append({"ticker": tk, "cluster": get_cluster(tk), "exit_date": r["exit_date"]})

    if not taken:
        return {"n": 0, "wr": 0, "pf": 0, "sum_pnl": 0, "max_dd": 0, "calmar": 0, "sl_cnt": 0}

    tdf = pd.DataFrame(taken).sort_values(["exit_date", "entry_date"]).reset_index(drop=True)
    eq = tdf["pnl_rp"].cumsum()
    peak = eq.cummax().clip(lower=0.0)
    dd = eq - peak
    max_dd = float(dd.min())

    gross_win = float(tdf[tdf["pnl_rp"] > 0]["pnl_rp"].sum())
    gross_loss = float(-tdf[tdf["pnl_rp"] < 0]["pnl_rp"].sum())
    pf = gross_win / gross_loss if gross_loss > 0 else 99.0
    sum_pnl = float(tdf["pnl_rp"].sum())
    wr = float((tdf["pnl_rp"] > 0).mean() * 100.0)
    calmar = sum_pnl / abs(max_dd) if max_dd < 0 else 99.0
    sl_cnt = int((tdf["result"] == "stop_loss").sum())

    # Per-fold breakdown
    folds = {}
    for fname, grp in tdf.groupby("fold"):
        gw = float(grp[grp["pnl_rp"] > 0]["pnl_rp"].sum())
        gl = float(-grp[grp["pnl_rp"] < 0]["pnl_rp"].sum())
        feq = grp["pnl_rp"].cumsum()
        fdd = float((feq - feq.cummax().clip(lower=0.0)).min())
        folds[fname] = {
            "n": len(grp),
            "wr": round(float((grp["pnl_rp"] > 0).mean() * 100.0), 1),
            "pf": round(gw / gl, 2) if gl > 0 else 99.0,
            "pnl_m": round(float(grp["pnl_rp"].sum()) / 1e6, 2),
            "max_dd_m": round(fdd / 1e6, 2),
            "sl": int((grp["result"] == "stop_loss").sum()),
        }

    return {
        "n": len(tdf),
        "wr": round(wr, 1),
        "pf": round(pf, 2),
        "sum_pnl_m": round(sum_pnl / 1e6, 2),
        "max_dd_m": round(max_dd / 1e6, 2),
        "calmar": round(calmar, 2),
        "sl_cnt": sl_cnt,
        "skipped": (skipped_grade, skipped_breadth, skipped_cluster, skipped_blacklist),
        "folds": folds,
    }


def assign_fold(dt: pd.Timestamp) -> str:
    if dt < pd.Timestamp("2026-04-01"):
        return "F1_Dec25_Mar26"
    if dt < pd.Timestamp("2026-07-01"):
        return "F2_Apr26_Jun26"
    if dt < pd.Timestamp("2026-10-01"):
        return "F3_Jul26_Sep26"
    return "F4_Oct26_Nov26_Crisis"


def main():
    trades, prices = load_data()
    breadth = compute_daily_breadth(prices)
    corr_map = compute_rolling_corr_pairs(prices)

    trades = trades.merge(breadth, left_on="entry_date", right_index=True, how="left")
    trades["fold"] = trades["entry_date"].apply(assign_fold)

    print(f"Loaded {len(trades)} closed trades | Breadth matched: {trades['breadth_pct'].notna().sum()}")
    print("Trades per fold:", trades["fold"].value_counts().sort_index().to_dict())

    flat_sizing = {"A+": 1.0, "A": 1.0, "B": 1.0, "C": 1.0}
    skip_c_sizing = {"A+": 1.0, "A": 1.0, "B": 0.5, "C": 0.0}
    boost_aplus_125 = {"A+": 1.25, "A": 1.0, "B": 0.5, "C": 0.0}
    boost_aplus_150 = {"A+": 1.50, "A": 1.0, "B": 0.5, "C": 0.0}

    configs = [
        ("0_Baseline (Flat 100%, All Grades)", flat_sizing, None, None, None, False),
        ("1_Skip_Blacklist_Only", flat_sizing, None, None, None, True),
        ("2_GradeSizing (C=0, B=50, A=100, A+=100)", skip_c_sizing, None, None, None, True),
        ("3_GradeSizing (C=0, B=50, A=100, A+=125)", boost_aplus_125, None, None, None, True),
        ("4_GradeSizing (C=0, B=50, A=100, A+=150)", boost_aplus_150, None, None, None, True),
        ("5_Breadth >= 30% (Flat)", flat_sizing, 30.0, None, None, True),
        ("6_Breadth >= 35% (Flat)", flat_sizing, 35.0, None, None, True),
        ("7_Breadth >= 40% (Flat)", flat_sizing, 40.0, None, None, True),
        ("8_Breadth >= 45% (Flat)", flat_sizing, 45.0, None, None, True),
        ("9_ClusterCap=1 (Flat)", flat_sizing, None, 1, None, True),
        ("10_CorrCap=0.65 (Flat)", flat_sizing, None, None, 0.65, True),
        ("11_Combo: Grade125 + ClusterCap=1", boost_aplus_125, None, 1, None, True),
        ("12_Combo: Grade125 + Breadth>=35% + ClusterCap=1", boost_aplus_125, 35.0, 1, None, True),
        ("13_Combo: Grade150 + Breadth>=35% + ClusterCap=1", boost_aplus_150, 35.0, 1, None, True),
        ("14_Combo: Grade125 + Breadth>=30% + ClusterCap=1", boost_aplus_125, 30.0, 1, None, True),
    ]

    results = []
    for name, sz, mb, cc, rc, sb in configs:
        res = simulate_portfolio(trades, sz, mb, cc, rc, corr_map, sb)
        res["name"] = name
        results.append(res)

    print("\n=== FF-1 GLOBAL & CRISIS FOLD COMPARISON ===")
    header = f"{'Config':48s} | {'N':>4s} | {'WR%':>5s} | {'PF':>5s} | {'PnL(Jt)':>8s} | {'MaxDD':>7s} | {'Calmar':>6s} | {'SL':>3s} | {'F4_PnL':>7s} | {'F4_DD':>7s} | {'F4_PF':>5s}"
    print(header)
    print("-" * len(header))
    for r in results:
        f4 = r["folds"].get("F4_Oct26_Nov26_Crisis", {"pnl_m": 0, "max_dd_m": 0, "pf": 0})
        print(
            f"{r['name']:48s} | {r['n']:4d} | {r['wr']:5.1f} | {r['pf']:5.2f} | "
            f"{r['sum_pnl_m']:+8.2f} | {r['max_dd_m']:7.2f} | {r['calmar']:6.2f} | {r['sl_cnt']:3d} | "
            f"{f4['pnl_m']:+7.2f} | {f4['max_dd_m']:7.2f} | {f4['pf']:5.2f}"
        )

    # Write detailed Markdown report
    lines = [
        "# Laporan Riset Kuantitatif Fase FF-1: Grade-Weighted Sizing, Market Breadth Gate, & Cluster Cap (Walk-Forward OOS)",
        "",
        f"> **Tanggal Riset**: 26 November 2026  ",
        f"> **Dataset**: `{len(trades)}` closed trades MySQL (`2025-12` s/d `2026-11-25`) dibagi menjadi **4 Fold Kronologis OOS** (F1 Des–Mar, F2 Apr–Jun, F3 Jul–Sep, F4 Krisis Okt–Nov 2026).  ",
        f"> **Modal Dasar Simulasi**: Rp 10.000.000 per unit 100% (non-compounding, *apple-to-apple*).",
        "",
        "## 1. Perbandingan Global & Fold Krisis Okt–Nov 2026 (`F4`)",
        "",
        "| Konfigurasi | Trades | WR (%) | Profit Factor | Total PnL (Rp Jt) | Max DD (Rp Jt) | Calmar | SL | F4 PnL (Jt) | F4 MaxDD (Jt) | F4 PF |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for r in results:
        f4 = r["folds"].get("F4_Oct26_Nov26_Crisis", {"pnl_m": 0, "max_dd_m": 0, "pf": 0})
        lines.append(
            f"| {r['name']} | {r['n']} | {r['wr']:.1f}% | **{r['pf']:.2f}** | {r['sum_pnl_m']:+.2f} | {r['max_dd_m']:.2f} | **{r['calmar']:.2f}** | {r['sl_cnt']} | {f4['pnl_m']:+.2f} | {f4['max_dd_m']:.2f} | {f4['pf']:.2f} |"
        )

    lines.extend(["", "## 2. Rincian Per-Fold Kronologis (Baseline vs Kandidat Utama)", ""])
    key_names = [
        "0_Baseline (Flat 100%, All Grades)",
        "2_GradeSizing (C=0, B=50, A=100, A+=100)",
        "3_GradeSizing (C=0, B=50, A=100, A+=125)",
        "6_Breadth >= 35% (Flat)",
        "9_ClusterCap=1 (Flat)",
        "11_Combo: Grade125 + ClusterCap=1",
        "12_Combo: Grade125 + Breadth>=35% + ClusterCap=1",
    ]
    for r in results:
        if r["name"] not in key_names:
            continue
        lines.append(f"### {r['name']}")
        lines.append("| Fold | N | WR (%) | PF | PnL (Rp Jt) | Max DD (Rp Jt) | SL |")
        lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |")
        for fk in sorted(r["folds"].keys()):
            fd = r["folds"][fk]
            lines.append(f"| `{fk}` | {fd['n']} | {fd['wr']:.1f}% | {fd['pf']:.2f} | {fd['pnl_m']:+.2f} | {fd['max_dd_m']:.2f} | {fd['sl']} |")
        lines.append("")

    report_path = REPORTS_DIR / "research_ff1_sizing_breadth_cluster_20261126.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written to: {report_path}")


if __name__ == "__main__":
    main()
