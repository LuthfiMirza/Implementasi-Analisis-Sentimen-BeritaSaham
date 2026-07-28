#!/usr/bin/env python3
"""Evaluate tracked signals whose 30-day horizon has elapsed, per PROTOCOL.md. Fetches real
price history via yfinance (no manual price entry at this stage -- outcomes come from the
market, not from re-reading the source's own claims).

Idempotent: signals already in `outcomes` are skipped (the table's UPDATE/DELETE triggers would
block re-writing them anyway). Run this periodically (e.g. daily) -- it only evaluates signals
that have actually reached day 30.

    python3 quant/signal_tracker/evaluate.py
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
DB_PATH = Path(__file__).parent / "tracker.sqlite3"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"
ROUND_TRIP_COST = 0.008
HORIZON_DAYS = 30


def _yf():
    try:
        import yfinance as yf
        return yf
    except ImportError:
        raise SystemExit(
            "yfinance tidak terpasang di interpreter ini. Jalankan dengan "
            "quant/.venv-fundamentals/bin/python3 quant/signal_tracker/evaluate.py"
        )


def fetch_history(ticker: str, start: datetime, end: datetime) -> pd.DataFrame | None:
    yf = _yf()
    # Index symbols (e.g. ^JKSE for IHSG) are global yfinance tickers, not IDX-listed equities --
    # unlike stock codes, they must NOT get the .JK suffix.
    symbol = ticker if ticker.startswith("^") else f"{ticker}.JK"
    try:
        df = yf.Ticker(symbol).history(
            start=start.strftime("%Y-%m-%d"),
            end=(end + timedelta(days=3)).strftime("%Y-%m-%d"),  # small buffer past horizon
            auto_adjust=True,
        )
    except Exception as e:
        print(f"  [gagal fetch {ticker}]: {e}")
        return None
    if df.empty:
        return None
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df


def evaluate_one(ticker: str, posted_at: datetime, entry_price: float,
                  tp1: float | None, sl_default: float | None) -> dict:
    horizon_end = posted_at + timedelta(days=HORIZON_DAYS)
    prices = fetch_history(ticker, posted_at, horizon_end)
    if prices is None:
        return {"result": "DATA_UNAVAILABLE"}

    window = prices[(prices.index >= posted_at) & (prices.index <= horizon_end)]
    if window.empty:
        return {"result": "DATA_UNAVAILABLE"}

    result, exit_price, exit_date = "TIME_EXIT", float(window["Close"].iloc[-1]), window.index[-1]
    for date, row in window.iterrows():
        if tp1 is not None and row["High"] >= tp1:
            result, exit_price, exit_date = "TP_HIT", tp1, date
            break
        if sl_default is not None and row["Low"] <= sl_default:
            result, exit_price, exit_date = "SL_HIT", sl_default, date
            break

    days_to_exit = (exit_date - posted_at).days
    gross = exit_price / entry_price - 1
    net = gross - ROUND_TRIP_COST

    buy_hold_row = window[window.index <= horizon_end]
    buy_hold_return = float(buy_hold_row["Close"].iloc[-1]) / entry_price - 1 if not buy_hold_row.empty else None

    ihsg = fetch_history("^JKSE", posted_at, horizon_end)
    ihsg_return = None
    if ihsg is not None:
        ihsg_window = ihsg[(ihsg.index >= posted_at) & (ihsg.index <= horizon_end)]
        if len(ihsg_window) >= 2:
            ihsg_return = float(ihsg_window["Close"].iloc[-1]) / float(ihsg_window["Close"].iloc[0]) - 1

    return {
        "result": result, "exit_price": exit_price, "exit_date": exit_date.strftime("%Y-%m-%d"),
        "days_to_exit": days_to_exit, "gross_return": round(gross, 6), "net_return": round(net, 6),
        "buy_hold_return_30d": round(buy_hold_return, 6) if buy_hold_return is not None else None,
        "ihsg_return_30d": round(ihsg_return, 6) if ihsg_return is not None else None,
    }


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    now = datetime.utcnow()
    due = conn.execute(
        """SELECT s.id, s.ticker, s.signal_posted_at, s.market_price_at_log, s.stated_tp1, s.stated_sl_default
           FROM signals s
           LEFT JOIN outcomes o ON o.signal_id = s.id
           WHERE s.tracked = 1 AND o.id IS NULL"""
    ).fetchall()

    evaluated, skipped_not_due = 0, 0
    for signal_id, ticker, posted_at_str, entry_price, tp1, sl_default in due:
        posted_at = datetime.fromisoformat(posted_at_str.replace("Z", ""))
        if now < posted_at + timedelta(days=HORIZON_DAYS):
            skipped_not_due += 1
            continue

        print(f"Evaluasi signal #{signal_id} {ticker} (posted {posted_at_str})...")
        outcome = evaluate_one(ticker, posted_at, entry_price, tp1, sl_default)
        horizon_end = (posted_at + timedelta(days=HORIZON_DAYS)).strftime("%Y-%m-%d")

        conn.execute(
            """INSERT INTO outcomes
               (signal_id, horizon_end_date, result, exit_price, exit_date, days_to_exit,
                gross_return, net_return, buy_hold_return_30d, ihsg_return_30d)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (signal_id, horizon_end, outcome["result"], outcome.get("exit_price"),
             outcome.get("exit_date"), outcome.get("days_to_exit"), outcome.get("gross_return"),
             outcome.get("net_return"), outcome.get("buy_hold_return_30d"), outcome.get("ihsg_return_30d")),
        )
        conn.commit()
        evaluated += 1
        print(f"  -> {outcome['result']}"
              + (f", net_return={outcome.get('net_return'):+.2%}" if outcome.get("net_return") is not None else ""))

    print(f"\nSelesai: {evaluated} sinyal dievaluasi, {skipped_not_due} belum sampai 30 hari.")


if __name__ == "__main__":
    main()
