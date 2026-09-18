#!/usr/bin/env python3
"""
trailing_alert_termux.py — Standalone trailing stop alert untuk Termux di HP Android.

Tidak butuh:
- MySQL / Laravel
- Mac menyala
- Python environment kompleks

Butuh:
- pip install yfinance pandas requests
- open_positions.json (di folder yang sama)
- .env berisi TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID

Cara pakai:
  python trailing_alert_termux.py          # cek trailing stop
  python trailing_alert_termux.py --test   # test kirim pesan ke Telegram

Cron di Termux (tiap 15 menit jam 9-16 hari Senin-Jumat):
  */15 9-16 * * 1-5 cd ~/sentimena && python trailing_alert_termux.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import requests
import yfinance as yf

# ── Konstanta ──────────────────────────────────────────────────────────────────
PULLBACK_THRESHOLD = 0.02   # 2% dari puncak → kirim alert
POSITIONS_PATH = Path(__file__).parent / "open_positions.json"
ENV_PATH = Path(__file__).parent / ".env"

# ── Helper: load .env ──────────────────────────────────────────────────────────
def load_env() -> tuple[str, str]:
    """Baca TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID dari .env atau environment."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        if ENV_PATH.exists():
            for line in ENV_PATH.read_text().splitlines():
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    token = line.split("=", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("TELEGRAM_CHAT_ID="):
                    chat_id = line.split("=", 1)[1].strip().strip('"').strip("'")

    return token, chat_id


# ── Helper: kirim Telegram ─────────────────────────────────────────────────────
def send_telegram(token: str, chat_id: str, msg: str) -> bool:
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
        return r.ok
    except Exception as e:
        print(f"[ERROR] Gagal kirim Telegram: {e}")
        return False


# ── Helper: harga live via yfinance ───────────────────────────────────────────
def get_price(ticker: str) -> float | None:
    try:
        t = yf.Ticker(f"{ticker}.JK")
        price = t.fast_info.last_price
        return float(price) if price else None
    except Exception:
        return None


# ── Helper: hitung hari bursa ─────────────────────────────────────────────────
def trading_days_between(start: str, end: str) -> int:
    import pandas as pd
    s = pd.Timestamp(start)
    e = pd.Timestamp(end)
    # busTradingDays = jumlah hari kerja (Senin-Jumat) antara s dan e
    return max(0, len(pd.bdate_range(s, e)) - 1)


# ── Main: cek semua posisi ────────────────────────────────────────────────────
def check_all_positions(token: str, chat_id: str) -> None:
    if not POSITIONS_PATH.exists():
        print("open_positions.json tidak ditemukan.")
        return

    positions: list[dict] = json.loads(POSITIONS_PATH.read_text())
    today = date.today().isoformat()
    now_str = datetime.now(timezone.utc).strftime("%d %b %H:%M")
    any_alert = False

    for pos in positions:
        ticker   = pos.get("ticker", "?")
        strategy = pos.get("strategy", "?")
        entry    = float(pos.get("entry_price", 0))
        entry_date = pos.get("entry_date", today)
        peak     = float(pos.get("peak_price") or entry)
        label    = f"{ticker} [{strategy.upper()}]"

        # Ambil harga live
        price = get_price(ticker)
        if price is None:
            print(f"{label}: gagal ambil harga live, skip.")
            continue

        # Update puncak
        if price > peak:
            peak = price
            pos["peak_price"] = peak

        pullback = (peak - price) / peak if peak > 0 else 0
        pnl_pct  = (price - entry) / entry * 100 if entry > 0 else 0
        td       = trading_days_between(entry_date, today)
        stop_lvl = round(peak * (1 - PULLBACK_THRESHOLD), 0)

        print(f"{label}: entry={entry} peak={peak} now={price} "
              f"pullback={pullback:.1%} PnL={pnl_pct:+.1f}% hari={td}")

        # ── Alert 1: trailing stop kena ───────────────────────────────────────
        alerted_at = float(pos.get("alerted_pullback_at_peak") or 0)
        if pullback >= PULLBACK_THRESHOLD and peak > alerted_at:
            msg = (
                f"⚠️ <b>TRAILING STOP: {label}</b>\n\n"
                f"Harga kini : Rp{price:,.0f}\n"
                f"Puncak     : Rp{peak:,.0f}\n"
                f"Mundur     : {pullback:.1%} (ambang {PULLBACK_THRESHOLD:.0%})\n"
                f"Stop level : Rp{stop_lvl:,.0f}\n"
                f"PnL        : {pnl_pct:+.1f}%\n"
                f"Hari bursa : {td}\n\n"
                f"⚡ <i>Alert saja — keputusan cut/hold di tanganmu.</i>\n"
                f"⏰ {now_str} WIB"
            )
            if send_telegram(token, chat_id, msg):
                pos["alerted_pullback_at_peak"] = peak
                any_alert = True
                print(f"  → Alert TS terkirim!")

        # ── Alert 2: H-1 target waktu (9 hari bursa) ─────────────────────────
        if pos.get("strategy") in ("gabungan", "momentum") and td == 9 and not pos.get("alerted_day9"):
            msg = (
                f"🟡 <b>H-1 TARGET WAKTU: {label}</b>\n\n"
                f"Posisi sudah <b>9 hari bursa</b> — besok hari ke-10.\n"
                f"Entry: Rp{entry:,.0f} → Sekarang: Rp{price:,.0f}\n"
                f"PnL: {pnl_pct:+.1f}%\n\n"
                f"Pertimbangkan exit besok sesuai rencana.\n"
                f"⏰ {now_str} WIB"
            )
            if send_telegram(token, chat_id, msg):
                pos["alerted_day9"] = td
                any_alert = True

        # ── Alert 3: target waktu 10 hari kena ───────────────────────────────
        if pos.get("strategy") in ("gabungan", "momentum") and td >= 10 and not pos.get("alerted_day10"):
            msg = (
                f"🟠 <b>TARGET WAKTU 10 HARI: {label}</b>\n\n"
                f"Posisi sudah <b>{td} hari bursa</b>.\n"
                f"Entry: Rp{entry:,.0f} → Sekarang: Rp{price:,.0f}\n"
                f"PnL: {pnl_pct:+.1f}%\n\n"
                f"Aturan backtest: keluar di 10 hari bursa jika belum kena target/stop.\n"
                f"⏰ {now_str} WIB"
            )
            if send_telegram(token, chat_id, msg):
                pos["alerted_day10"] = td
                any_alert = True

    # Simpan kembali state
    POSITIONS_PATH.write_text(json.dumps(positions, indent=2, ensure_ascii=False))

    if not any_alert:
        print(f"✅ Semua posisi aman. Tidak ada alert ({now_str} WIB)")


# ── Mode test ─────────────────────────────────────────────────────────────────
def test_mode(token: str, chat_id: str) -> None:
    msg = (
        "✅ <b>Test Alert — Sentimena Termux</b>\n\n"
        "Koneksi Telegram OK!\n"
        f"Script jalan di HP kamu.\n"
        f"⏰ {datetime.now().strftime('%d %b %Y %H:%M')} WIB"
    )
    ok = send_telegram(token, chat_id, msg)
    print("Test kirim:", "✅ BERHASIL" if ok else "❌ GAGAL")


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    token, chat_id = load_env()

    if not token or not chat_id:
        print("❌ TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID tidak ditemukan di .env")
        sys.exit(1)

    if "--test" in sys.argv:
        test_mode(token, chat_id)
    else:
        check_all_positions(token, chat_id)
