#!/usr/bin/env python3
"""Log one observed Telegram signal into the append-only tracker. Run once per signal you see,
whether it matches the pre-registered filter (BUY + confidence 5, per PROTOCOL.md) or not --
non-matching signals are still recorded (tracked=0) so the eventual report can show how many
signals were seen vs deliberately excluded, not just the ones that made the cut.

Usage (interactive, asks for each field):
    python3 quant/signal_tracker/log_signal.py

Usage (non-interactive, for scripting):
    python3 quant/signal_tracker/log_signal.py \\
        --source "Zeta AI IDX Stock Signal" --ticker GZCO --signal-type BUY \\
        --confidence 5 --stated-entry 136 --market-price-now 145 \\
        --tp1 148 --sl-default 126 --posted-at 2026-06-12T07:26:00 \\
        --indicators "MACD 1.73 bullish, RSI 58.17, EMA20/50 bearish, ADX 32.95 strong" \\
        --raw-text "full pasted message here"
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "tracker.sqlite3"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# The filter is hardcoded from PROTOCOL.md, not a CLI flag -- it must not be adjustable per run.
REQUIRED_SIGNAL_TYPE = "BUY"
REQUIRED_CONFIDENCE = 5


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return conn


def determine_tracked(signal_type: str, confidence: int | None) -> tuple[bool, str | None]:
    if signal_type.upper() != REQUIRED_SIGNAL_TYPE:
        return False, f"signal_type={signal_type} (bukan {REQUIRED_SIGNAL_TYPE})"
    if confidence != REQUIRED_CONFIDENCE:
        return False, f"confidence={confidence} (bukan {REQUIRED_CONFIDENCE})"
    return True, None


def prompt(label: str, required: bool = True, cast=str):
    while True:
        raw = input(f"{label}: ").strip()
        if not raw and required:
            print("  wajib diisi.")
            continue
        if not raw:
            return None
        try:
            return cast(raw)
        except ValueError:
            print(f"  format tidak valid, ulangi ({cast.__name__}).")


def interactive_collect() -> dict:
    print("=== Catat sinyal baru (append-only, tidak bisa diedit setelah disimpan) ===\n")
    source = prompt("Sumber (mis. 'Zeta AI IDX Stock Signal')")
    ticker = prompt("Ticker (mis. GZCO)").upper()
    signal_type = prompt("Jenis sinyal (BUY/WATCHLIST/SELL)").upper()
    confidence = prompt("Confidence score (angka, kosongkan jika tidak ada)", required=False, cast=int)
    posted_at = prompt("Waktu sinyal diposting (YYYY-MM-DDTHH:MM, atau kosongkan = sekarang)", required=False)
    if not posted_at:
        posted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    stated_entry = prompt("Harga entry yang disebut sumber", required=False, cast=float)
    market_price = prompt("Harga pasar SEKARANG (yang kamu lihat sendiri, WAJIB)", cast=float)
    tp1 = prompt("TP1 yang disebut", required=False, cast=float)
    sl_default = prompt("Stop loss default (ATR) yang disebut", required=False, cast=float)
    indicators = prompt("Indikator yang disebut (bebas teks)", required=False)
    raw_text = prompt("Tempel teks/caption asli (bebas, untuk bukti)", required=False)
    return dict(
        source=source, ticker=ticker, signal_type=signal_type, confidence=confidence,
        posted_at=posted_at, stated_entry=stated_entry, market_price=market_price,
        tp1=tp1, sl_default=sl_default, indicators=indicators, raw_text=raw_text,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source")
    parser.add_argument("--ticker")
    parser.add_argument("--signal-type")
    parser.add_argument("--confidence", type=int)
    parser.add_argument("--posted-at")
    parser.add_argument("--stated-entry", type=float)
    parser.add_argument("--market-price-now", type=float)
    parser.add_argument("--tp1", type=float)
    parser.add_argument("--sl-default", type=float)
    parser.add_argument("--indicators")
    parser.add_argument("--raw-text")
    args = parser.parse_args()

    if args.ticker and args.market_price_now is not None:
        data = dict(
            source=args.source or "unknown", ticker=args.ticker.upper(),
            signal_type=(args.signal_type or "").upper(), confidence=args.confidence,
            posted_at=args.posted_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            stated_entry=args.stated_entry, market_price=args.market_price_now,
            tp1=args.tp1, sl_default=args.sl_default,
            indicators=args.indicators, raw_text=args.raw_text,
        )
    else:
        data = interactive_collect()

    tracked, skip_reason = determine_tracked(data["signal_type"], data["confidence"])

    conn = get_connection()
    conn.execute(
        """INSERT INTO signals
           (signal_posted_at, source, ticker, signal_type, confidence_score,
            stated_entry_price, market_price_at_log, stated_tp1, stated_sl_default,
            indicators_cited, raw_text, tracked, skip_reason)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (data["posted_at"], data["source"], data["ticker"], data["signal_type"], data["confidence"],
         data["stated_entry"], data["market_price"], data["tp1"], data["sl_default"],
         data["indicators"], data["raw_text"], int(tracked), skip_reason),
    )
    conn.commit()
    row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()

    status = "TRACKED (masuk evaluasi 30 hari)" if tracked else f"TIDAK DILACAK ({skip_reason})"
    print(f"\n[{row_id}] {data['ticker']} {data['signal_type']} conf={data['confidence']} -> {status}")


if __name__ == "__main__":
    sys.exit(main())
