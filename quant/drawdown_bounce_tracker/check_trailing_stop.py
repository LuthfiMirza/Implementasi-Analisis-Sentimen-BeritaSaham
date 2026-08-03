#!/usr/bin/env python3
"""Daily manual-trailing-stop ALERT (not execution) for open BUMI/DEWA positions.

User explicitly wants alert-only: "kasi sinyal aja di telegram... nanti saya pasang sendiri
manual trailing stop 4-5% di stockbitnya manual". This script never places or modifies any
order -- it just watches the peak price since entry for each position listed in
open_positions.json and sends one Telegram alert the first time price pulls back >= 4% from
that peak, so the user can decide whether to act (and at what exact % -- 4 or 5) themselves.

Positions are tracked in a local JSON file (not the Laravel Trade Journal / MySQL) so this stays
usable even when MySQL is off, matching the same resilience as detect_signal.py. Update
open_positions.json by hand (or ask Claude to update it) whenever a position is opened/closed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent))
from detect_signal import send_telegram_alert  # noqa: E402

PULLBACK_THRESHOLD = 0.04  # 4% -- the lower/more sensitive end of the 4-5% range the user chose
POSITIONS_PATH = Path(__file__).parent / "open_positions.json"


def load_positions() -> list[dict]:
    if not POSITIONS_PATH.is_file():
        return []
    return json.loads(POSITIONS_PATH.read_text(encoding="utf-8"))


def save_positions(positions: list[dict]) -> None:
    POSITIONS_PATH.write_text(json.dumps(positions, indent=2), encoding="utf-8")


def check_position(position: dict) -> None:
    ticker = position["ticker"]
    entry_date = position["entry_date"]

    df = yf.download(f"{ticker}.JK", start=entry_date, progress=False, auto_adjust=False)
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    if df.empty:
        print(f"{ticker}: tidak ada data harga sejak {entry_date}, dilewati.")
        return

    peak = float(df["High"].max())
    peak_date = df["High"].idxmax().date().isoformat()
    current = float(df["Close"].iloc[-1])
    current_date = df.index[-1].date().isoformat()
    pullback = (peak - current) / peak

    print(f"{ticker}: entry {position['entry_price']} ({entry_date}) | puncak {peak:.0f} ({peak_date}) "
          f"| harga sekarang {current:.0f} ({current_date}) | mundur {pullback:.1%}")

    if pullback < PULLBACK_THRESHOLD:
        return

    already_alerted = position.get("alerted_pullback_pct")
    if already_alerted is not None:
        print(f"  -> sudah pernah alert sebelumnya ({already_alerted:.1%}), dilewati (update open_positions.json untuk reset).")
        return

    unrealized_pct = (current - position["entry_price"]) / position["entry_price"]
    send_telegram_alert(
        f"\U0001F534 <b>PERINGATAN TRAILING STOP: {ticker}</b>\n\n"
        f"Harga sudah mundur <b>{pullback:.1%}</b> dari titik tertinggi sejak entry.\n\n"
        f"<b>Entry</b>: {entry_date} @ Rp{position['entry_price']:.0f}\n"
        f"<b>Puncak</b>: {peak_date} @ Rp{peak:.0f}\n"
        f"<b>Sekarang</b>: {current_date} @ Rp{current:.0f} ({unrealized_pct:+.1%} dari entry)\n\n"
        f"Ini alert saja -- TIDAK ada order otomatis dipasang. Silakan putuskan sendiri "
        f"trailing stop manual di StockBit (4-5%)."
    )
    position["alerted_pullback_pct"] = pullback
    print(f"  -> ALERT TERKIRIM ke Telegram (pullback {pullback:.1%}).")


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
