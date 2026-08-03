#!/usr/bin/env python3
"""Poll Telegram for /open and /close commands, update open_positions.json directly -- no need
to tell Claude in chat every time a position changes.

Commands (send to @IDX_alert_keysentimen_bot -- or tap the keyboard buttons under the message box):
  /open TICKER [HARGA] [TANGGAL]   -- tambah posisi baru (HARGA/TANGGAL opsional -- kalau HARGA
                                       tidak disebut, dipakai harga penutupan terakhir live)
  /close TICKER [HARGA] [TANGGAL]  -- tutup posisi (HARGA opsional, sama seperti /open)
  /status                          -- tampilkan posisi yang lagi dipantau

Uses long-polling (getUpdates with an offset), not a webhook -- no public HTTPS endpoint needed,
works fine from a local dev machine. Only processes messages from TELEGRAM_CHAT_ID (the user's own
chat), ignores everything else, so a leaked bot token can't be used to inject fake positions.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

import requests
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent))
from detect_signal import default_keyboard, load_telegram_credentials, send_telegram_alert  # noqa: E402

POSITIONS_PATH = Path(__file__).parent / "open_positions.json"
OFFSET_PATH = Path(__file__).parent / "telegram_update_offset.txt"

# HARGA is optional -- a bare "/close BUMI" (as sent by the keyboard button, no price typed) falls
# through to fetch_live_price() below.
COMMAND_PATTERN = re.compile(
    r"^/(open|close)\s+([A-Za-z]{2,6})(?:\s+([\d.,]+))?(?:\s+(\d{4}-\d{2}-\d{2}))?", re.IGNORECASE
)


def fetch_live_price(ticker: str) -> float | None:
    df = yf.download(f"{ticker}.JK", period="5d", progress=False, auto_adjust=False)
    if df.empty:
        return None
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    return float(df["Close"].iloc[-1])


def load_positions() -> list[dict]:
    if not POSITIONS_PATH.is_file():
        return []
    return json.loads(POSITIONS_PATH.read_text(encoding="utf-8"))


def save_positions(positions: list[dict]) -> None:
    POSITIONS_PATH.write_text(json.dumps(positions, indent=2), encoding="utf-8")


def load_offset() -> int:
    if OFFSET_PATH.is_file():
        return int(OFFSET_PATH.read_text(encoding="utf-8").strip() or 0)
    return 0


def save_offset(update_id: int) -> None:
    OFFSET_PATH.write_text(str(update_id + 1), encoding="utf-8")


def handle_command(text: str, positions: list[dict]) -> tuple[list[dict], str]:
    match = COMMAND_PATTERN.match(text.strip())
    if not match:
        return positions, (
            "Perintah tidak dikenali. Pakai tombol di bawah, atau ketik:\n"
            "/open TICKER [HARGA] [TANGGAL]\n"
            "/close TICKER [HARGA] [TANGGAL]\n"
            "/status\n\n"
            "(HARGA boleh dikosongkan -- otomatis pakai harga live terakhir)"
        )

    action, ticker, price_str, cmd_date = match.groups()
    ticker = ticker.upper()
    cmd_date = cmd_date or date.today().isoformat()

    if price_str:
        price = float(price_str.replace(",", ""))
    else:
        price = fetch_live_price(ticker)
        if price is None:
            return positions, f"Tidak bisa ambil harga live {ticker} sekarang -- coba lagi dengan menyebut harganya: /{action} {ticker} HARGA"

    if action.lower() == "close":
        before = len(positions)
        positions = [p for p in positions if p["ticker"] != ticker]
        if len(positions) == before:
            return positions, f"Tidak ada posisi {ticker} yang sedang dipantau -- tidak ada yang ditutup."
        return positions, f"✅ {ticker} ditutup dari pemantauan (dicatat harga exit Rp{price:.0f}, {cmd_date}). Tidak akan ada alert lagi untuk posisi ini."

    # open
    positions = [p for p in positions if p["ticker"] != ticker]  # replace if already tracked
    positions.append({
        "ticker": ticker,
        "entry_date": cmd_date,
        "entry_price": price,
        "alerted_pullback_pct": None,
    })
    return positions, f"✅ {ticker} ditambahkan ke pemantauan trailing-stop: entry Rp{price:.0f} ({cmd_date})."


def format_status(positions: list[dict]) -> str:
    if not positions:
        return "Tidak ada posisi yang sedang dipantau."
    lines = ["<b>Posisi yang dipantau:</b>"]
    for p in positions:
        lines.append(f"- {p['ticker']}: entry Rp{p['entry_price']:.0f} ({p['entry_date']})")
    return "\n".join(lines)


def main() -> None:
    token, chat_id = load_telegram_credentials()
    if not token or not chat_id:
        print("Telegram belum dikonfigurasi -- tidak bisa cek perintah.")
        return

    offset = load_offset()
    resp = requests.get(
        f"https://api.telegram.org/bot{token}/getUpdates",
        params={"offset": offset, "timeout": 0},
        timeout=15,
    )
    resp.raise_for_status()
    updates = resp.json().get("result", [])

    if not updates:
        print("Tidak ada perintah baru.")
        return

    positions = load_positions()
    processed = 0
    latest_update_id = offset - 1

    for update in updates:
        latest_update_id = update["update_id"]
        message = update.get("message")
        if not message:
            continue
        if str(message.get("chat", {}).get("id")) != str(chat_id):
            continue  # ignore anyone except the configured owner chat

        text = message.get("text", "")
        if text.strip() == "/status":
            send_telegram_alert(format_status(positions), reply_markup=default_keyboard())
            processed += 1
            continue

        if text.startswith("/open") or text.startswith("/close"):
            positions, reply = handle_command(text, positions)
            send_telegram_alert(reply, reply_markup=default_keyboard())
            processed += 1
            print(f"Diproses: {text.strip()} -> {reply}")

    save_positions(positions)
    save_offset(latest_update_id)
    print(f"{processed} perintah diproses." if processed else "Tidak ada perintah relevan.")


if __name__ == "__main__":
    main()
