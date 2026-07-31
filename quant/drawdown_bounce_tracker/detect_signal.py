#!/usr/bin/env python3
"""Daily automatic detector for the 'IHSG + stock crash together' bounce signal (Fase AB -> AC).

Run daily (see routes/console.php: research:detect-drawdown-bounce-signal). Fetches the latest
BUMI/DEWA/IHSG prices directly via yfinance (no dependency on the Laravel DB or the static
data/stocks/*.csv snapshot, which lags), checks whether the trigger condition (2-day cumulative
return <= -5% for both IHSG and the stock) fired on the most recently completed trading day, and
if the next day's close is already available, logs the signal with its entry price.

Deliberately only logs signals with trigger_date >= TRACKING_START_DATE -- everything before that
is the Fase AB historical backtest, not part of this live protocol (see PROTOCOL.md).
"""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd
import yfinance as yf

TRACKING_START_DATE = date(2026, 7, 31)  # PROTOCOL.md lock date -- do not backdate
DROP_THRESHOLD = -0.05
LABELS = {"BUMI": "tracked", "DEWA": "exploratory"}

DB_PATH = Path(__file__).parent / "tracker.sqlite3"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return conn


def fetch_recent(symbol: str, days: int = 20) -> pd.DataFrame:
    df = yf.download(symbol, period=f"{days}d", progress=False, auto_adjust=False)
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df.reset_index().rename(columns={"Date": "date", "Adj Close": "adj_close"})
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["ret_2d"] = df["adj_close"].pct_change(2)
    return df[["date", "adj_close", "ret_2d"]]


def detect() -> list[dict]:
    ihsg = fetch_recent("^JKSE")
    found = []

    for ticker in ["BUMI", "DEWA"]:
        stock = fetch_recent(f"{ticker}.JK")
        merged = stock.merge(ihsg, on="date", suffixes=("_stock", "_ihsg")).dropna()
        if len(merged) < 2:
            continue

        # Check every row that has both a trigger day and a following day with a close price.
        for i in range(len(merged) - 1):
            trigger_row = merged.iloc[i]
            entry_row = merged.iloc[i + 1]
            trigger_date = trigger_row["date"]

            if trigger_date < TRACKING_START_DATE:
                continue
            if not (trigger_row["ret_2d_stock"] <= DROP_THRESHOLD and trigger_row["ret_2d_ihsg"] <= DROP_THRESHOLD):
                continue

            found.append({
                "ticker": ticker,
                "label": LABELS[ticker],
                "trigger_date": trigger_date.isoformat(),
                "ihsg_ret_2d": float(trigger_row["ret_2d_ihsg"]),
                "stock_ret_2d": float(trigger_row["ret_2d_stock"]),
                "entry_date": entry_row["date"].isoformat(),
                "entry_price": float(entry_row["adj_close"]),
            })

    return found


def main() -> None:
    conn = get_connection()
    signals = detect()

    inserted = 0
    for s in signals:
        try:
            conn.execute(
                """INSERT INTO signals
                (ticker, label, trigger_date, ihsg_ret_2d, stock_ret_2d, entry_date, entry_price)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (s["ticker"], s["label"], s["trigger_date"], s["ihsg_ret_2d"], s["stock_ret_2d"],
                 s["entry_date"], s["entry_price"]),
            )
            inserted += 1
            print(f"SIGNAL BARU: {s['ticker']} ({s['label']}) trigger {s['trigger_date']} "
                  f"-> entry {s['entry_date']} @ {s['entry_price']:.0f}")
        except sqlite3.IntegrityError:
            pass  # already logged, UNIQUE(ticker, trigger_date) makes this idempotent

    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    conn.close()

    if inserted == 0:
        print(f"Tidak ada sinyal baru. Tidak ada trigger sejak {TRACKING_START_DATE}. Total tercatat: {total}.")
    else:
        print(f"{inserted} sinyal baru dicatat. Total tercatat: {total}.")


if __name__ == "__main__":
    main()
