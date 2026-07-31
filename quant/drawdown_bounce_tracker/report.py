#!/usr/bin/env python3
"""P&L-style report for the drawdown-bounce live tracker, formatted like a brokerage performance
page (date / equity / P&L) so it's directly comparable to what the trades would look like in a
real account. Refuses to draw conclusions below PROTOCOL.md's n>=20 threshold.
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

MIN_SIGNALS_TO_CONCLUDE = 20
STARTING_CAPITAL = 10_000_000  # Rp 10jt, matches this project's position-sizing convention elsewhere
# NOT 1.0 (all-in per trade). Live-verified this matters: running the demo at 100% capital-per-trade
# showed BUMI compounding to +843% but DEWA collapsing -76% purely because several signals fired
# back-to-back during the Oct 2008 crash (each new trade redeploys 100% of whatever capital survived
# the previous one, so a cluster of losses inside one crisis compounds catastrophically). 20% keeps
# the per-trade P&L readable while not letting one clustered episode wipe out the account.
POSITION_FRACTION = 0.20

DB_PATH = Path(__file__).parent / "tracker.sqlite3"


def load(conn: sqlite3.Connection, label: str, horizon: int) -> pd.DataFrame:
    query = """
    SELECT s.ticker, s.trigger_date, s.entry_date, s.entry_price, o.exit_date, o.net_return
    FROM signals s JOIN outcomes o ON o.signal_id = s.id
    WHERE s.label = ? AND o.horizon_days = ?
    ORDER BY s.entry_date
    """
    return pd.read_sql_query(query, conn, params=(label, horizon))


def build_equity_curve(trades: pd.DataFrame) -> pd.DataFrame:
    equity = STARTING_CAPITAL
    rows = []
    for _, t in trades.iterrows():
        pnl = equity * POSITION_FRACTION * t["net_return"]
        equity += pnl
        rows.append({
            "Date": t["exit_date"],
            "Ticker": t["ticker"],
            "Entry": t["entry_date"],
            "Equity": round(equity),
            "PnL": round(pnl),
            "PnL_pct": t["net_return"] * 100,
        })
    return pd.DataFrame(rows)


def print_section(label: str, horizon: int, trades: pd.DataFrame) -> None:
    n = len(trades)
    print(f"\n{'='*70}")
    print(f"{label.upper()} -- horizon {horizon} hari bursa  (n={n})")
    print(f"{'='*70}")

    if n == 0:
        print("Belum ada sinyal live yang selesai horizon-nya. Belum ada apa pun untuk dilaporkan.")
        return

    curve = build_equity_curve(trades)
    print(f"\n{'Date':<12}{'Ticker':<8}{'Entry':<12}{'Equity (Rp)':>15}{'P&L (Rp)':>15}{'P&L %':>10}")
    for _, r in curve.iterrows():
        print(f"{r['Date']:<12}{r['Ticker']:<8}{r['Entry']:<12}{r['Equity']:>15,}{r['PnL']:>15,}{r['PnL_pct']:>9.2f}%")

    total_return_pct = (curve["Equity"].iloc[-1] / STARTING_CAPITAL - 1) * 100
    win_rate = (trades["net_return"] > 0).mean() * 100
    print(f"\nModal awal hipotetis : Rp {STARTING_CAPITAL:,}")
    print(f"Equity akhir         : Rp {curve['Equity'].iloc[-1]:,}  ({total_return_pct:+.2f}% sejak awal)")
    print(f"Win rate             : {win_rate:.1f}%  ({(trades['net_return']>0).sum()}/{n})")
    print(f"Rata-rata net return per trade : {trades['net_return'].mean()*100:+.2f}%")
    print(f"Median net return per trade    : {trades['net_return'].median()*100:+.2f}%")

    if n < MIN_SIGNALS_TO_CONCLUDE:
        print(f"\n*** BELUM CUKUP DATA (n={n} < {MIN_SIGNALS_TO_CONCLUDE}). ***")
        print("*** Angka di atas INDIKATIF SAJA -- jangan dijadikan dasar keputusan trading. ***")
        print(f"*** Progres menuju ambang minimum: {n}/{MIN_SIGNALS_TO_CONCLUDE} sinyal. ***")
    else:
        print(f"\nAmbang minimum ({MIN_SIGNALS_TO_CONCLUDE}) sudah terpenuhi -- lihat plan.md untuk kesimpulan resmi.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo-historical", action="store_true",
                         help="Render report from Fase AB's historical backtest instead of the live tracker.sqlite3 -- CLEARLY labeled as illustrative, not live results.")
    args = parser.parse_args()

    if args.demo_historical:
        print("#" * 70)
        print("# CONTOH ILUSTRATIF dari backtest historis Fase AB (BUKAN sinyal live).")
        print("# Dipakai untuk menunjukkan BENTUK laporan P&L, bukan hasil live tracker.")
        print("# Tracker live yang sesungguhnya masih n=0 -- lihat report.py tanpa flag ini.")
        print("#" * 70)
        render_demo_from_backtest()
        return

    conn = sqlite3.connect(DB_PATH)
    for label in ["tracked", "exploratory"]:
        for horizon in [10, 5]:
            trades = load(conn, label, horizon)
            print_section(f"BUMI (tracked)" if label == "tracked" else "DEWA (exploratory)", horizon, trades)
    conn.close()


def render_demo_from_backtest() -> None:
    import json
    report = json.loads(Path("output/prediction_research/ihsg_drawdown_entry_experiment.json").read_text())

    def load_series(ticker: str) -> pd.DataFrame:
        fname = "data/stocks/IHSG.csv" if ticker == "IHSG" else f"data/stocks/{ticker}.csv"
        df = pd.read_csv(fname)
        date_col = "Date" if "Date" in df.columns else "date"
        close_col = "Adj Close" if "Adj Close" in df.columns else "adj_close"
        df = df.rename(columns={date_col: "date", close_col: "adj_close"})
        df["date"] = pd.to_datetime(df["date"])
        return df.sort_values("date").reset_index(drop=True)

    ihsg = load_series("IHSG")
    for r in report:
        ticker = r["ticker"]
        stock = load_series(ticker)
        merged = stock.merge(ihsg, on="date", suffixes=("_stock", "_ihsg"))
        merged["ret_2d_stock"] = merged["adj_close_stock"].pct_change(2)
        merged["ret_2d_ihsg"] = merged["adj_close_ihsg"].pct_change(2)
        merged = merged.dropna(subset=["ret_2d_stock", "ret_2d_ihsg"]).reset_index(drop=True)
        signal_idx = merged.index[(merged["ret_2d_stock"] <= -0.05) & (merged["ret_2d_ihsg"] <= -0.05)].tolist()

        horizon = 10
        rows = []
        for idx in signal_idx:
            entry_idx, exit_idx = idx + 1, idx + 1 + horizon
            if exit_idx >= len(merged):
                continue
            entry_price = merged["adj_close_stock"].iloc[entry_idx]
            exit_price = merged["adj_close_stock"].iloc[exit_idx]
            net_return = (exit_price / entry_price - 1) - 0.008
            rows.append({
                "ticker": ticker,
                "trigger_date": str(merged["date"].iloc[idx].date()),
                "entry_date": str(merged["date"].iloc[entry_idx].date()),
                "exit_date": str(merged["date"].iloc[exit_idx].date()),
                "net_return": net_return,
            })
        trades = pd.DataFrame(rows)
        print_section(f"{ticker} (CONTOH dari backtest historis, bukan live)", horizon, trades)


if __name__ == "__main__":
    main()
