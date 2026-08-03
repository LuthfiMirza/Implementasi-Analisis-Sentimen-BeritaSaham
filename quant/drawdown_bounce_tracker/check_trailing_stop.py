#!/usr/bin/env python3
"""Intraday manual-trailing-stop + day-10 exit ALERTS (never execution) for open BUMI/DEWA
positions.

User explicitly wants alert-only: "kasi sinyal aja di telegram... nanti saya pasang sendiri
manual trailing stop 4-5% di stockbitnya manual". This script never places or modifies any
order -- it watches each position in open_positions.json and sends Telegram alerts:

  1. TRAILING STOP -- first time price pulls back >= 4% from the peak since entry.
  2. TARGET WAKTU  -- when the position reaches 10 trading days, the exit rule that won every
     backtest in Fase AB/AD/AE (fixed 10-day hold beat every overbought-indicator variant).

Both fire at most once per position (flags stored back into open_positions.json).

Uses HOURLY bars, not daily closes. Live-verified on the 21-23 Jul 2026 spike: hourly checking
would have alerted at 23 Jul 14:00 (peak 196, price 184, +36.3% on a 30 Jun entry), whereas the
old daily-close version only saw it at the 15:21 end-of-day run. Same rule, ~1.5h earlier.
Hourly data also gives a truer peak, since an intraday spike high is captured as it happens
rather than only after the daily bar closes.

Positions live in a local JSON file (not the Laravel Trade Journal / MySQL) so this keeps working
when MySQL is off, matching detect_signal.py's resilience. Manage it from Telegram with /open and
/close (see telegram_commands.py).
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent))
from detect_signal import send_telegram_alert  # noqa: E402

PULLBACK_THRESHOLD = 0.04  # 4% -- the more sensitive end of the 4-5% range the user chose
TARGET_HOLD_DAYS = 10  # trading days -- the exit that won in Fase AB/AD/AE
POSITIONS_PATH = Path(__file__).parent / "open_positions.json"


def load_positions() -> list[dict]:
    if not POSITIONS_PATH.is_file():
        return []
    return json.loads(POSITIONS_PATH.read_text(encoding="utf-8"))


def save_positions(positions: list[dict]) -> None:
    POSITIONS_PATH.write_text(json.dumps(positions, indent=2), encoding="utf-8")


def fetch_hourly_since(ticker: str, entry_date: str) -> pd.DataFrame | None:
    """Hourly bars from entry_date onward. yfinance caps hourly history at ~730 days, which is far
    more than any position we track will need."""
    df = yf.download(f"{ticker}.JK", period="730d", interval="1h", progress=False, auto_adjust=False)
    if df.empty:
        return None
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df.index = df.index.tz_convert("Asia/Jakarta")
    df = df[df.index.normalize() >= pd.Timestamp(entry_date, tz="Asia/Jakarta")]
    return df if not df.empty else None


def check_position(position: dict) -> None:
    ticker = position["ticker"]
    entry_date = position["entry_date"]
    entry_price = float(position["entry_price"])

    df = fetch_hourly_since(ticker, entry_date)
    if df is None:
        print(f"{ticker}: tidak ada data 1 jam sejak {entry_date}, dilewati.")
        return

    peak = float(df["High"].max())
    peak_ts = df["High"].idxmax()
    current = float(df["Close"].iloc[-1])
    current_ts = df.index[-1]
    pullback = (peak - current) / peak
    unrealized_pct = (current - entry_price) / entry_price
    trading_days = df.index.normalize().nunique()

    print(
        f"{ticker}: entry {entry_price:.0f} ({entry_date}) | puncak {peak:.0f} "
        f"({peak_ts.strftime('%d %b %H:%M')}) | sekarang {current:.0f} "
        f"({current_ts.strftime('%d %b %H:%M')}) | mundur {pullback:.1%} | "
        f"hari bursa ke-{trading_days} | P&L {unrealized_pct:+.1%}"
    )

    # --- Alert 1: trailing stop ---
    if pullback >= PULLBACK_THRESHOLD and position.get("alerted_pullback_pct") is None:
        send_telegram_alert(
            f"\U0001F534 <b>TRAILING STOP: {ticker}</b>\n\n"
            f"Harga mundur <b>{pullback:.1%}</b> dari puncak sejak entry.\n\n"
            f"<b>Entry</b>: {entry_date} @ Rp{entry_price:.0f}\n"
            f"<b>Puncak</b>: {peak_ts.strftime('%d %b %H:%M')} @ Rp{peak:.0f}\n"
            f"<b>Sekarang</b>: {current_ts.strftime('%d %b %H:%M')} @ Rp{current:.0f}\n"
            f"<b>P&amp;L</b>: {unrealized_pct:+.1%} dari entry\n\n"
            f"Alert saja -- tidak ada order otomatis. Pasang trailing stop sendiri di StockBit."
        )
        position["alerted_pullback_pct"] = pullback
        print(f"  -> ALERT TRAILING STOP terkirim ({pullback:.1%}).")

    # --- Alert 2: 10-trading-day target ---
    if trading_days >= TARGET_HOLD_DAYS and position.get("alerted_day10") is None:
        send_telegram_alert(
            f"\U0001F7E0 <b>TARGET WAKTU {TARGET_HOLD_DAYS} HARI: {ticker}</b>\n\n"
            f"Posisi sudah <b>{trading_days} hari bursa</b> sejak entry.\n\n"
            f"<b>Entry</b>: {entry_date} @ Rp{entry_price:.0f}\n"
            f"<b>Sekarang</b>: Rp{current:.0f} ({unrealized_pct:+.1%})\n\n"
            f"Aturan hasil backtest (Fase AB/AD/AE): keluar di {TARGET_HOLD_DAYS} hari bursa "
            f"mengalahkan semua varian exit indikator overbought yang diuji.\n\n"
            f"Alert saja -- keputusan tetap di kamu."
        )
        position["alerted_day10"] = trading_days
        print(f"  -> ALERT TARGET WAKTU terkirim (hari ke-{trading_days}).")


def main() -> None:
    positions = load_positions()
    if not positions:
        print("Tidak ada posisi terpantau (open_positions.json kosong).")
        return

    for position in positions:
        check_position(position)

    save_positions(positions)


if __name__ == "__main__":
    main()
