#!/usr/bin/env python3
"""Intraday manual-trailing-stop + day-9/day-10 exit ALERTS (never execution) for open BUMI/DEWA
positions.

User explicitly wants alert-only: "kasi sinyal aja di telegram... nanti saya pasang sendiri
manual trailing stop 4-5% di stockbitnya manual". This script never places or modifies any
order -- it watches each position in open_positions.json and sends Telegram alerts:

  0. PUNCAK BARU -- price sets a new high since entry that's >=5% above the last-notified peak
     (Fase AU). Positive counterpart to the trailing stop below: tells the user the "safe level"
     just moved up, without them having to ask.
  1. TRAILING STOP -- price pulls back >= 2% from the CURRENT peak. Re-triggerable per peak
     (Fase AU) -- previously fired ONCE EVER per position; now resets whenever a new higher peak
     is set, so it can catch a fresh reversal even after an earlier pullback already alerted from
     a lower peak. Mirrors how a real trailing stop trails upward with price.
  1.5 H-1 TARGET WAKTU -- hari bursa ke-9, peringatan awal sebelum target hari ke-10 (Fase AL) --
     supaya ada waktu bersiap, bukan mendadak di hari-H.
  2. TARGET WAKTU  -- when the position reaches 10 trading days, the exit rule that won every
     backtest in Fase AB/AD/AE (fixed 10-day hold beat every overbought-indicator variant).

Alerts 0 and 1 can each fire multiple times over a position's life (once per new peak). Alerts
1.5 and 2 still fire at most once (flags stored back into open_positions.json).

Uses 15-MINUTE bars, not daily closes. Live-verified on the 21-23 Jul 2026 spike: checking every
15 minutes with a 2% threshold would have alerted at 23 Jul 13:30 (peak 196, price 192, +35.8% on
a 30 Jun entry) -- the SAME clock time as the user's real StockBit trailing stop (13:30 @ 189),
just a few points higher because this only sees 15-min bar closes, not continuous tick data like
a real broker order. That's a ~45-minute improvement over the previous hourly/4% version, which
lagged the real stop by ~1.5h (14:00 @ 184).

Tradeoff, stated plainly: 2% is tighter than BUMI/DEWA's daily ATR (~5.8-6.0%), so this WILL fire
on ordinary intraday noise sometimes, not just genuine reversals -- the user chose this explicitly
after seeing the lag-vs-false-alarm tradeoff on real numbers.

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

PULLBACK_THRESHOLD = 0.02  # 2% -- tighter than daily ATR (~5.8-6.0%), chosen deliberately by the
# user after seeing this WILL fire on ordinary intraday noise sometimes, in exchange for catching
# genuine reversals close to real-time instead of lagging by up to 1.5h.
NEW_HIGH_THRESHOLD = 0.05  # 5% -- Fase AU: new peak counts as a "milestone" worth a PUNCAK BARU
# alert once it's this much above the last-notified peak (or entry price, before the first one).
TARGET_HOLD_DAYS = 10  # trading days -- the exit that won in Fase AB/AD/AE
WARN_HOLD_DAYS = TARGET_HOLD_DAYS - 1  # H-1 (Fase AL): peringatan sehari sebelum target
POSITIONS_PATH = Path(__file__).parent / "open_positions.json"


def load_positions() -> list[dict]:
    if not POSITIONS_PATH.is_file():
        return []
    return json.loads(POSITIONS_PATH.read_text(encoding="utf-8"))


def save_positions(positions: list[dict]) -> None:
    POSITIONS_PATH.write_text(json.dumps(positions, indent=2), encoding="utf-8")


def fetch_15m_since(ticker: str, entry_date: str) -> pd.DataFrame | None:
    """15-minute bars from entry_date onward. yfinance/Yahoo caps 15m history at 60 days -- far
    more than the ~10-20 trading day holding periods this system's exit rules use, so it's never
    a binding constraint for a real open position."""
    df = yf.download(f"{ticker}.JK", period="60d", interval="15m", progress=False, auto_adjust=False)
    if df.empty:
        return None
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df.index = df.index.tz_convert("Asia/Jakarta")
    df = df[df.index.normalize() >= pd.Timestamp(entry_date, tz="Asia/Jakarta")]
    return df if not df.empty else None


def compute_snapshot(ticker: str, entry_date: str, entry_price: float) -> dict | None:
    """Read-only: puncak, harga terkini, mundur dari puncak, hari bursa ke berapa -- TIDAK PERNAH
    mengirim alert atau mengubah open_positions.json. Dipakai oleh check_position() di bawah
    (yang bisa kirim alert) dan oleh telegram_commands.py::format_status() (murni tampilan on-
    demand pas user ketik /status, terlepas dari apakah alert otomatis sudah pernah terkirim).

    Fase BW: puncak TIDAK LAGI menghitung intraday HARI ENTRY ITU SENDIRI -- cuma
    max(entry_price, High hari-hari SESUDAH entry). Ini menyamakan definisi "puncak" dengan
    backtest yang memvalidasi aturan trailing-stop (screen_candidates.py/research_average_down.py:
    peak dimulai FLAT di entry Close, baru bertambah dari entry_idx+1 dan seterusnya) -- backtest
    itu TIDAK PERNAH menghitung intraday hari entry sebagai bagian puncak.

    Bug lama (versi sebelum Fase BW) menghitung `df["High"].max()` dari SELURUH data sejak
    entry_date, TERMASUK jam-jam sebelum entry tercatat di hari yang sama -- untuk sinyal
    GABUNGAN dampaknya kecil (entry biasanya dekat harga terendah, bukan puncak sesi), tapi untuk
    sinyal MOMENTUM (entry = closing, RSI sudah tinggi -- rawan sempat spike pagi lalu turun ke
    closing) dampaknya besar. Dibuktikan nyata 14 Agu 2026: BRPT puncak lama 1965 (mundur 4,3%,
    kelihatan SUDAH kena trailing-stop) vs puncak baru 1900 (mundur cuma 1,1%, MASIH SEHAT) --
    puncak lama itu dari jam 09:00 di HARI ENTRY-nya sendiri, sebelum posisi bahkan terdaftar ke
    pemantauan (entry Momentum baru diketahui pas closing ~15:18). BUMI sama: puncak lama 187
    (mundur 4,8%) vs puncak baru 179 (mundur 0,6%)."""
    df = fetch_15m_since(ticker, entry_date)
    if df is None:
        return None

    entry_day = pd.Timestamp(entry_date, tz="Asia/Jakarta").normalize()
    after_entry_day = df[df.index.normalize() > entry_day]

    if not after_entry_day.empty and float(after_entry_day["High"].max()) > entry_price:
        peak = float(after_entry_day["High"].max())
        peak_ts = after_entry_day["High"].idxmax()
    else:
        # Belum ada hari SESUDAH entry yang bikin rekor baru di atas harga entry -- puncak
        # dianggap = harga entry itu sendiri (persis logika backtest: peak awal = entry Close).
        peak = entry_price
        entry_day_bars = df[df.index.normalize() == entry_day]
        peak_ts = entry_day_bars.index[-1] if not entry_day_bars.empty else df.index[0]

    current = float(df["Close"].iloc[-1])
    current_ts = df.index[-1]
    pullback = (peak - current) / peak
    unrealized_pct = (current - entry_price) / entry_price
    trading_days = df.index.normalize().nunique()

    return {
        "peak": peak, "peak_ts": peak_ts, "current": current, "current_ts": current_ts,
        "pullback": pullback, "unrealized_pct": unrealized_pct, "trading_days": trading_days,
    }


def check_position(position: dict) -> None:
    ticker = position["ticker"]
    entry_date = position["entry_date"]
    entry_price = float(position["entry_price"])
    signal_type = position.get("signal_type", "ret2d")
    # Fase BU: dua strategi otomatis (GABUNGAN/MOMENTUM) bisa punya posisi terbuka bersamaan di
    # saham yang sama sejak register_open_position() dikunci per (ticker, strategy) -- label ini
    # ditambahkan ke SEMUA alert supaya user tidak bingung posisi mana yang dimaksud (kejadian
    # nyata 13 Agu 2026: BRPT MOMENTUM disangka "Sinyal Beli" karena alertnya tidak menyebut
    # strategi apa pun).
    strategy = position.get("strategy", "GABUNGAN")
    label = f"{ticker} [{strategy}]"

    snap = compute_snapshot(ticker, entry_date, entry_price)
    if snap is None:
        print(f"{label}: tidak ada data 15 menit sejak {entry_date}, dilewati.")
        return

    peak, peak_ts = snap["peak"], snap["peak_ts"]
    current, current_ts = snap["current"], snap["current_ts"]
    pullback = snap["pullback"]
    unrealized_pct = snap["unrealized_pct"]
    trading_days = snap["trading_days"]

    # Fase BP: sinyal "ganda" pakai B&H 10 hari (tanpa trailing-stop) — divalidasi P1-P4,
    # total return +555% vs TS-2% +420%, CI95 lower +2.02% vs +1.07%.
    is_ganda = signal_type == "ganda"
    exit_mode = "B&H-10d" if is_ganda else "TS-2%"

    print(
        f"{label}: entry {entry_price:.0f} ({entry_date}) | puncak {peak:.0f} "
        f"({peak_ts.strftime('%d %b %H:%M')}) | sekarang {current:.0f} "
        f"({current_ts.strftime('%d %b %H:%M')}) | mundur {pullback:.1%} | "
        f"hari bursa ke-{trading_days} | P&L {unrealized_pct:+.1%} | exit={exit_mode}"
    )

    if not is_ganda:
        # --- Alert 0: puncak baru (milestone +5% dari puncak terakhir yang sudah diberi tahu) ---
        milestone_base = position.get("milestone_peak") or entry_price
        if peak >= milestone_base * (1 + NEW_HIGH_THRESHOLD):
            gain_from_last = (peak - milestone_base) / milestone_base
            new_stop_level = peak * (1 - PULLBACK_THRESHOLD)
            send_telegram_alert(
                f"\U0001F389 <b>PUNCAK BARU: {label}</b>\n\n"
                f"Harga bikin rekor tertinggi baru sejak entry: <b>Rp{peak:.0f}</b> "
                f"({peak_ts.strftime('%d %b %H:%M')}), naik <b>{gain_from_last:+.1%}</b> dari puncak "
                f"sebelumnya (Rp{milestone_base:.0f}).\n\n"
                f"<b>Entry</b>: {entry_date} @ Rp{entry_price:.0f}\n"
                f"<b>P&amp;L saat ini</b>: {unrealized_pct:+.1%}\n\n"
                f"Level trailing stop ikut naik ke sekitar <b>Rp{new_stop_level:.0f}</b> "
                f"({PULLBACK_THRESHOLD:.0%} di bawah puncak baru ini). Alert saja -- keputusan tetap "
                f"di kamu."
            )
            position["milestone_peak"] = peak
            print(f"  -> ALERT PUNCAK BARU terkirim (Rp{peak:.0f}, {gain_from_last:+.1%} dari puncak sebelumnya).")

        # --- Alert 1: trailing stop ---
        alerted_at_peak = position.get("alerted_pullback_at_peak") or 0
        if pullback >= PULLBACK_THRESHOLD and peak > alerted_at_peak:
            send_telegram_alert(
                f"\U0001F534 <b>TRAILING STOP: {label}</b>\n\n"
                f"Harga mundur <b>{pullback:.1%}</b> dari puncak sejak entry.\n\n"
                f"<b>Entry</b>: {entry_date} @ Rp{entry_price:.0f}\n"
                f"<b>Puncak</b>: {peak_ts.strftime('%d %b %H:%M')} @ Rp{peak:.0f}\n"
                f"<b>Sekarang</b>: {current_ts.strftime('%d %b %H:%M')} @ Rp{current:.0f}\n"
                f"<b>P&amp;L</b>: {unrealized_pct:+.1%} dari entry\n\n"
                f"Alert saja -- tidak ada order otomatis. Pasang trailing stop sendiri di StockBit."
            )
            position["alerted_pullback_pct"] = pullback
            position["alerted_pullback_at_peak"] = peak
            print(f"  -> ALERT TRAILING STOP terkirim ({pullback:.1%}, puncak Rp{peak:.0f}).")

    # Fase CS: alert target-waktu 10 hari cuma valid utk strategi yang BENERAN divalidasi pakai
    # exit waktu tetap (GABUNGAN/MOMENTUM, Fase AB/AD/AE). BOTTOM_REBOUND TIDAK divalidasi pakai
    # target waktu -- backtest-nya cuma trailing-stop 2% murni (MAX_HOLDING_BARS di backtest
    # cuma batas simulasi, bukan aturan). Tanpa guard ini, posisi bottom-rebound yang somehow
    # bertahan 10 hari bakal dapat alert yang ngutip temuan backtest STRATEGI LAIN seolah berlaku
    # buat dia juga -- salah kaprah, walau kemungkinan kecil kejadian (rata-rata bottom-rebound
    # keluar dalam ~1 hari bursa per backtest, trailing 2% terlalu ketat utk bertahan lama).
    uses_time_target = strategy in ("GABUNGAN", "MOMENTUM")

    # --- Alert 1.5: H-1 warning (day 9), before the day-10 target below ---
    if uses_time_target and WARN_HOLD_DAYS <= trading_days < TARGET_HOLD_DAYS and position.get("alerted_day9") is None:
        send_telegram_alert(
            f"\U0001F7E1 <b>H-1 TARGET WAKTU: {label}</b>\n\n"
            f"Posisi sudah <b>{trading_days} hari bursa</b> sejak entry -- besok (hari bursa "
            f"berikutnya) kena target waktu {TARGET_HOLD_DAYS} hari.\n\n"
            f"<b>Entry</b>: {entry_date} @ Rp{entry_price:.0f}\n"
            f"<b>Sekarang</b>: Rp{current:.0f} ({unrealized_pct:+.1%})\n\n"
            f"Peringatan awal supaya ada waktu bersiap, bukan mendadak di hari-H. Alert saja -- "
            f"keputusan tetap di kamu."
        )
        position["alerted_day9"] = trading_days
        print(f"  -> ALERT H-1 TARGET WAKTU terkirim (hari ke-{trading_days}).")

    # --- Alert 2: 10-trading-day target ---
    if uses_time_target and trading_days >= TARGET_HOLD_DAYS and position.get("alerted_day10") is None:
        send_telegram_alert(
            f"\U0001F7E0 <b>TARGET WAKTU {TARGET_HOLD_DAYS} HARI: {label}</b>\n\n"
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
