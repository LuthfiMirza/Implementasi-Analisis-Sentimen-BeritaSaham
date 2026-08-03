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

import os
import sqlite3
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf

TRACKING_START_DATE = date(2026, 7, 31)  # PROTOCOL.md lock date -- do not backdate
DROP_THRESHOLD = -0.05
LABELS = {"BUMI": "tracked", "DEWA": "exploratory"}

DB_PATH = Path(__file__).parent / "tracker.sqlite3"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"
ENV_PATH = Path(__file__).parent.parent.parent / ".env"


def load_telegram_credentials() -> tuple[str | None, str | None]:
    """Read TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID. When run via `php artisan ...`, Laravel's
    Dotenv already exports these into the OS environment (putenv), so os.environ has them.
    When run directly (`python3 detect_signal.py`, e.g. for manual testing), fall back to
    parsing .env ourselves so the script still works standalone."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        return token, chat_id

    if ENV_PATH.is_file():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                token = line.split("=", 1)[1].strip()
            elif line.startswith("TELEGRAM_CHAT_ID="):
                chat_id = line.split("=", 1)[1].strip()

    return token, chat_id


def send_telegram_alert(text: str) -> None:
    token, chat_id = load_telegram_credentials()
    if not token or not chat_id:
        print("Telegram belum dikonfigurasi (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID kosong) -- alert dilewati.")
        return

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        if not resp.ok:
            print(f"Gagal kirim alert Telegram: HTTP {resp.status_code} {resp.text}")
    except Exception as e:  # network failure must never break signal detection itself
        print(f"Gagal kirim alert Telegram: {e}")


def describe_rsi(rsi14: float | None) -> str:
    if rsi14 is None or np.isnan(rsi14):
        return "n/a"
    if rsi14 < 30:
        return f"{rsi14:.0f} (oversold)"
    if rsi14 > 70:
        return f"{rsi14:.0f} (overbought)"
    return f"{rsi14:.0f} (netral)"


def describe_stoch(stoch_k: float | None) -> str:
    if stoch_k is None or np.isnan(stoch_k):
        return "n/a"
    if stoch_k < 20:
        return f"{stoch_k:.0f} (oversold)"
    if stoch_k > 80:
        return f"{stoch_k:.0f} (overbought)"
    return f"{stoch_k:.0f} (netral)"


def format_signal_alert(signal: dict) -> str:
    """HTML-formatted, scannable Telegram alert for one new signal (live-verified readable on
    mobile: bold labels, blank-line-separated sections, plain numbers not a wall of text)."""
    entry_date = date.fromisoformat(signal["entry_date"])
    exit_estimate = entry_date + pd.tseries.offsets.BDay(10)

    icon = "\U0001F7E2" if signal["label"] == "tracked" else "\U0001F7E1"
    header = f"{icon} <b>SINYAL BELI: {signal['ticker']}</b>"

    warning = ""
    if signal["label"] != "tracked":
        warning = (
            "\n\n⚠️ <b>EXPLORATORY</b> — JANGAN dijadikan kesimpulan sendirian, "
            "lihat PROTOCOL.md (sample historisnya belum cukup meyakinkan untuk DEWA)."
        )

    return (
        f"{header}\n\n"
        f"<b>Trigger</b>: {signal['trigger_date']}\n"
        f"IHSG {signal['ihsg_ret_2d']:+.1%} | {signal['ticker']} {signal['stock_ret_2d']:+.1%} (2 hari)\n\n"
        f"<b>Entry</b>: {signal['entry_date']}\n"
        f"Harga: Rp{signal['entry_price']:.0f}\n\n"
        f"<b>Rencana exit</b>: tahan 10 hari bursa\n"
        f"≈ {exit_estimate.date().isoformat()}\n\n"
        f"<b>Info tambahan</b> (bukan bagian aturan -- live-checked hanya cocok ~3/8 kasus):\n"
        f"RSI14: {describe_rsi(signal.get('rsi14'))}\n"
        f"Stoch %K: {describe_stoch(signal.get('stoch_k'))}"
        f"{warning}"
    )


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return conn


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def stochastic_k(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    lowest = low.rolling(period).min()
    highest = high.rolling(period).max()
    return 100 * (close - lowest) / (highest - lowest).replace(0, np.nan)


def fetch_recent(symbol: str, days: int = 60) -> pd.DataFrame:
    # 60d (not 20d) so RSI14/Stoch14's rolling windows are warmed up by the trigger date --
    # context-only indicators, not used in the entry/exit rule itself (see PROTOCOL.md).
    df = yf.download(symbol, period=f"{days}d", progress=False, auto_adjust=False)
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df.reset_index().rename(columns={"Date": "date", "Adj Close": "adj_close"})
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["ret_2d"] = df["adj_close"].pct_change(2)
    df["rsi14"] = rsi(df["adj_close"])
    df["stoch_k"] = stochastic_k(df["High"], df["Low"], df["adj_close"])
    return df[["date", "adj_close", "ret_2d", "rsi14", "stoch_k"]]


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
                "rsi14": None if pd.isna(trigger_row["rsi14_stock"]) else float(trigger_row["rsi14_stock"]),
                "stoch_k": None if pd.isna(trigger_row["stoch_k_stock"]) else float(trigger_row["stoch_k_stock"]),
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
                (ticker, label, trigger_date, ihsg_ret_2d, stock_ret_2d, entry_date, entry_price,
                 rsi14, stoch_k)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (s["ticker"], s["label"], s["trigger_date"], s["ihsg_ret_2d"], s["stock_ret_2d"],
                 s["entry_date"], s["entry_price"], s["rsi14"], s["stoch_k"]),
            )
            inserted += 1
            print(f"SIGNAL BARU: {s['ticker']} ({s['label']}) trigger {s['trigger_date']} "
                  f"-> entry {s['entry_date']} @ {s['entry_price']:.0f}")

            send_telegram_alert(format_signal_alert(s))
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
