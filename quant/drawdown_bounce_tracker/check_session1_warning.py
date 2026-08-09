#!/usr/bin/env python3
"""Peringatan AWAL (bukan sinyal resmi) di sesi 1 (~12:00 WIB) untuk saham yang dipantau
(Fase BA, setelah Fase AZ menolak usulan mengubah aturan entry jadi 2x/hari).

Beda dari detect_signal.py: script ini TIDAK PERNAH mengubah aturan trigger/entry resmi (itu
tetap cuma jalan di closing, 15:18, entry T+1 -- lihat plan.md Fase AZ, backtest membuktikan
entry lebih cepat justru menurunkan win rate 75% -> 68% tanpa menambah return). Script ini
MURNI informasional: kalau closing sesi 1 hari ini SUDAH menembus ambang -5%/2 hari (yang sama
dipakai detect_signal.py), kirim peringatan supaya user tahu lebih awal -- TANPA menyarankan
entry, dan TANPA mencatat apapun ke tracker.sqlite3.

Backtest Fase AZ: ~39% dari kasus seperti ini recover di sesi 2 dan TIDAK jadi sinyal resmi --
jadi pesan peringatan ini HARUS eksplisit bilang "belum pasti, tunggu closing".

Dijadwalkan terpisah dari research:detect-drawdown-bounce-signal (lihat routes/console.php),
idempotent per hari per ticker (state disimpan di session1_warning_state.json) supaya tidak
double-alert kalau job re-run.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent))
from detect_signal import DROP_THRESHOLD, LABELS, send_telegram_alert  # noqa: E402

WARNING_STATE_PATH = Path(__file__).parent / "session1_warning_state.json"


def load_warning_state() -> dict:
    if not WARNING_STATE_PATH.is_file():
        return {}
    return json.loads(WARNING_STATE_PATH.read_text(encoding="utf-8"))


def save_warning_state(state: dict) -> None:
    WARNING_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def fetch_daily_closes(ticker: str, days: int = 10) -> pd.DataFrame:
    """Close MENTAH (bukan Adj Close) -- penting terutama untuk SMGR yang bagi dividen nyata,
    beda dari fetch_recent() di detect_signal.py yang masih pakai Adj Close (bug lama, belum
    diperbaiki di sana, lihat plan.md)."""
    df = yf.download(f"{ticker}.JK", period=f"{days}d", progress=False, auto_adjust=False)
    if df.empty:
        return df
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df.reset_index().rename(columns={"Date": "date"})
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def fetch_session1_price(ticker: str) -> float | None:
    """Closing sesi 1 (bar 1-jam terakhir sebelum jam 12:00 WIB) HARI INI. None kalau sesi 1
    belum kejadian/belum ada data (mis. dijalankan manual di luar jam bursa)."""
    df = yf.download(f"{ticker}.JK", period="2d", interval="1h", progress=False, auto_adjust=False)
    if df.empty:
        return None
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df.index = df.index.tz_convert("Asia/Jakarta")
    today = pd.Timestamp.now(tz="Asia/Jakarta").normalize()
    todays_session1 = df[(df.index.normalize() == today) & (df.index.hour < 12)]
    if todays_session1.empty:
        return None
    return float(todays_session1["Close"].iloc[-1])


def format_session1_warning(ticker: str, ret_2d: float, price: float) -> str:
    return (
        f"⚠️ <b>WASPADA: {ticker}</b>\n\n"
        f"Sesi 1 hari ini sudah turun <b>{ret_2d:+.1%}</b> dalam 2 hari -- sudah menembus ambang "
        f"sinyal beli ({DROP_THRESHOLD:+.0%}).\n\n"
        f"<b>Harga sesi 1</b>: Rp{price:.0f}\n\n"
        f"⚠️ <b>INI BELUM SINYAL RESMI.</b> Backtest menunjukkan ~39% kasus seperti ini "
        f"pulih lagi di sesi 2 dan TIDAK jadi sinyal beli beneran. Konfirmasi final nanti jam "
        f"15:18 setelah closing settle -- jangan entry cuma berdasarkan peringatan ini."
    )


def check_session1_warning() -> None:
    state = load_warning_state()
    today_str = date.today().isoformat()

    for ticker in LABELS:
        if state.get(ticker) == today_str:
            print(f"{ticker}: sudah diperingatkan hari ini, dilewati.")
            continue

        daily = fetch_daily_closes(ticker)
        if len(daily) < 2:
            print(f"{ticker}: data harian tidak cukup, dilewati.")
            continue

        two_days_ago_close = float(daily.iloc[-2]["Close"])
        s1_price = fetch_session1_price(ticker)
        if s1_price is None:
            print(f"{ticker}: belum ada data sesi 1 hari ini, dilewati.")
            continue

        ret_2d = s1_price / two_days_ago_close - 1
        print(f"{ticker}: sesi1={s1_price:.0f}, close 2 hari lalu={two_days_ago_close:.0f}, ret_2d={ret_2d:+.1%}")

        if ret_2d <= DROP_THRESHOLD:
            send_telegram_alert(format_session1_warning(ticker, ret_2d, s1_price))
            state[ticker] = today_str
            print(f"  -> PERINGATAN sesi 1 terkirim ({ret_2d:+.1%}).")

    save_warning_state(state)


if __name__ == "__main__":
    check_session1_warning()
