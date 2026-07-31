#!/usr/bin/env python3
"""Fills in outcomes for signals whose 5-day or 10-day trading horizon has elapsed.

Run daily alongside detect_signal.py. Idempotent: UNIQUE(signal_id, horizon_days) means re-running
just skips signals that already have an outcome for that horizon.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import yfinance as yf

ROUND_TRIP_COST = 0.008
HORIZONS = [5, 10]

DB_PATH = Path(__file__).parent / "tracker.sqlite3"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return conn


def fetch_series(symbol: str, start: str) -> pd.DataFrame:
    df = yf.download(symbol, start=start, progress=False, auto_adjust=False)
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df.reset_index().rename(columns={"Date": "date", "Adj Close": "adj_close"})
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df[["date", "adj_close"]].reset_index(drop=True)


def main() -> None:
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    signals = conn.execute("SELECT * FROM signals").fetchall()

    filled = 0
    for sig in signals:
        stock_series = fetch_series(f"{sig['ticker']}.JK", sig["entry_date"])
        ihsg_series = fetch_series("^JKSE", sig["entry_date"])

        for horizon in HORIZONS:
            already = conn.execute(
                "SELECT 1 FROM outcomes WHERE signal_id = ? AND horizon_days = ?",
                (sig["id"], horizon),
            ).fetchone()
            if already:
                continue

            if len(stock_series) <= horizon or len(ihsg_series) <= horizon:
                continue  # horizon hasn't elapsed yet

            exit_row = stock_series.iloc[horizon]
            ihsg_exit_row = ihsg_series.iloc[horizon]
            entry_price = sig["entry_price"]

            gross_return = (exit_row["adj_close"] / entry_price) - 1
            net_return = gross_return - ROUND_TRIP_COST
            buy_hold_return = gross_return  # same trade, no signal filter -- identical here by construction
            ihsg_return = (ihsg_exit_row["adj_close"] / ihsg_series.iloc[0]["adj_close"]) - 1

            conn.execute(
                """INSERT INTO outcomes
                (signal_id, horizon_days, exit_date, exit_price, gross_return, net_return,
                 buy_hold_return, ihsg_return)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (sig["id"], horizon, exit_row["date"].isoformat(), float(exit_row["adj_close"]),
                 float(gross_return), float(net_return), float(buy_hold_return), float(ihsg_return)),
            )
            filled += 1
            print(f"OUTCOME: {sig['ticker']} sinyal #{sig['id']} horizon {horizon}d -> "
                  f"net {net_return:+.2%} (exit {exit_row['date']})")

    conn.commit()
    conn.close()
    print(f"Selesai. {filled} outcome baru diisi." if filled else "Belum ada horizon yang lewat.")


if __name__ == "__main__":
    main()
