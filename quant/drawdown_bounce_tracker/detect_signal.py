#!/usr/bin/env python3
"""Daily automatic detector for the BUMI/DEWA drawdown-bounce signal (Fase AB -> AC, loosened to
stock-only in Fase AW).

Run daily (see routes/console.php: research:detect-drawdown-bounce-signal). Fetches the latest
BUMI/DEWA/IHSG prices directly via yfinance (no dependency on the Laravel DB or the static
data/stocks/*.csv snapshot, which lags), checks whether the trigger condition (2-day cumulative
return <= -5% for the STOCK ITSELF -- IHSG is no longer a requirement, see Fase AW below) fired on
the most recently completed trading day, and if the next day's close is already available, logs
the signal with its entry price.

Fase AW (post-sidang, real-trading use, bukan lagi murni skripsi): syarat IHSG ikut ambruk >=5%
DIHAPUS dari trigger. Backtest Jan-Agu 2026 menunjukkan versi BUMI-only -5% (20 trade, win rate
75%, total return net +54.6%) mengalahkan aturan dual-condition lama (5 trade, win rate 80%,
+24.5%) dari sisi jumlah kesempatan dan total return, dan tetap konsisten kuat di backtest jangka
panjang sejak 2024 (discovery/holdout split, median return positif di keduanya -- lihat plan.md
Fase AW). IHSG ret_2d TETAP dihitung dan ditampilkan di alert sebagai info konteks, cuma bukan lagi
syarat wajib.

Deliberately only logs signals with trigger_date >= TRACKING_START_DATE -- everything before that
is the Fase AB historical backtest, not part of this live protocol (see PROTOCOL.md).
"""
from __future__ import annotations

import json
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
LABELS = {"BUMI": "tracked", "DEWA": "tracked", "BRPT": "tracked", "SMGR": "tracked",
          "ESSA": "tracked", "UNVR": "tracked"}  # DEWA dinaikkan dari
# "exploratory" ke "tracked" di Fase AX -- backtest BUMI-only -5% khusus DEWA (2024-sekarang)
# menunjukkan win rate 86% discovery / 88% holdout, median return tetap positif & MENINGKAT di
# holdout (tidak overfit), bahkan lebih kuat dari hasil BUMI sendiri. Lihat plan.md Fase AX.
#
# BRPT ditambahkan di Fase AY setelah screening 53 saham universe proyek + verifikasi episode
# independence (jeda >15 hari kalender = episode baru, supaya penurunan panjang berkelanjutan
# tidak dihitung sebagai banyak trade independen palsu). Per-episode: n=21, win rate 81%, median
# +1.17% -- tetap kuat setelah dikoreksi, beda dari TPIA (kandidat lain yang DITOLAK karena
# per-episode win rate cuma 52%, median ~0%, edge-nya nyaris hilang setelah koreksi). Lihat
# plan.md Fase AY untuk detail lengkap.
#
# SMGR & ESSA ditambahkan setelah episode-check terpisah: SMGR (n=18 episode, win rate 89%,
# median +1.64%, konsisten discovery 92%/holdout 83%) dan ESSA (n=19 episode, win rate 79%,
# median +1.25%, holdout MENINGKAT ke 83%/+3.58%) -- keduanya tidak ada konsentrasi episode
# besar (episode terbesar cuma ~14% dari total trade, beda dari BRPT/TPIA). INDY dicek juga tapi
# TIDAK ditambahkan -- lolos ambang tapi marginnya lebih tipis (win rate discovery cuma 57%).
#
# UNVR ditambahkan di Fase BB -- salah satu dari 12 saham RESMI proyek (sudah ada di tabel
# `stocks`, sudah terintegrasi penuh ke news/sentimen/model V6A-V6B, beda dari BRPT/SMGR/ESSA yang
# cuma dipantau lewat script ini). Backtest Des 2025-Agu 2026: n=12, win rate 83%, total return net
# +39.7% -- konsisten dengan screening awal sejak 2024 (win rate 68%, total +65.2%). Lihat plan.md
# Fase BB.

DB_PATH = Path(__file__).parent / "tracker.sqlite3"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"
ENV_PATH = Path(__file__).parent.parent.parent / ".env"


def load_telegram_credentials() -> tuple[str | None, str | None]:
    """Read TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID (nomor UTAMA). When run via `php artisan ...`,
    Laravel's Dotenv already exports these into the OS environment (putenv), so os.environ has
    them. When run directly (`python3 detect_signal.py`, e.g. for manual testing), fall back to
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


def load_allowed_chat_ids() -> set[str]:
    """Kumpulan chat_id yang boleh mengirim perintah ke bot -- nomor utama (TELEGRAM_CHAT_ID)
    plus nomor kedua opsional (TELEGRAM_CHAT_ID_2), supaya user bisa kelola posisi dari dua
    akun Telegram. Tidak memengaruhi ke mana alert OTOMATIS (sinyal/trailing-stop) dikirim --
    itu tetap ke nomor utama lewat send_telegram_alert() tanpa argumen chat_id."""
    ids: set[str] = set()
    primary_token, primary_chat_id = load_telegram_credentials()
    if primary_chat_id:
        ids.add(str(primary_chat_id))

    second = os.environ.get("TELEGRAM_CHAT_ID_2")
    if not second and ENV_PATH.is_file():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if line.startswith("TELEGRAM_CHAT_ID_2="):
                second = line.split("=", 1)[1].strip()
                break
    if second:
        ids.add(str(second))

    return ids


# Telegram sends whatever text is on the button back as the message -- these icon labels are
# translated back to the real /status, /close BUMI, /close DEWA commands in telegram_commands.py's
# BUTTON_LABELS map, so the parsing logic only has to understand the canonical command form.
BUTTON_STATUS = "\U0001F4CA Status"
BUTTON_HISTORY = "\U0001F4DC Riwayat"
BUTTON_CLOSE_BUMI = "\U0001F534 Tutup BUMI"
BUTTON_CLOSE_DEWA = "\U0001F534 Tutup DEWA"
BUTTON_CLOSE_BRPT = "\U0001F534 Tutup BRPT"  # Fase AY -- BRPT ditambahkan sebagai saham ke-3
BUTTON_CLOSE_SMGR = "\U0001F534 Tutup SMGR"
BUTTON_CLOSE_ESSA = "\U0001F534 Tutup ESSA"
BUTTON_CLOSE_UNVR = "\U0001F534 Tutup UNVR"
BUTTON_HELP = "❓ Bantuan"


def default_keyboard() -> dict:
    """Persistent tappable keyboard shown under the message box -- tapping a button just sends
    its label as a normal message, same as typing it. Price is deliberately not on the button:
    handle_command() fills it in from the live market price when a command arrives without one,
    so these buttons work with a single tap. /price and /open TICKER aren't buttons because they
    need a free-typed ticker -- Bantuan (/help) tells the user how to type those."""
    return {
        "keyboard": [
            [BUTTON_STATUS, BUTTON_HISTORY],
            [BUTTON_CLOSE_BUMI, BUTTON_CLOSE_DEWA],
            [BUTTON_CLOSE_BRPT, BUTTON_CLOSE_SMGR],
            [BUTTON_CLOSE_ESSA, BUTTON_CLOSE_UNVR],
            [BUTTON_HELP],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }


def send_telegram_alert(text: str, reply_markup: dict | None = None, chat_id: str | None = None) -> None:
    """chat_id opsional, dan artinya beda tergantung dipakai dari mana (Fase AV):
    - Diisi EKSPLISIT (dipakai telegram_commands.py untuk balas perintah /status dst) -> kirim
      HANYA ke chat_id itu. Balasan perintah harus balik ke akun yang MENGIRIM, bukan broadcast
      ke semua akun -- kalau akun A ketik /status, akun B tidak perlu ikut dapat balasannya.
    - DIKOSONGKAN (dipakai semua alert OTOMATIS: sinyal baru, trailing stop, H-1, target waktu,
      puncak baru) -> broadcast ke SEMUA akun yang diizinkan (load_allowed_chat_ids() -- primary
      + TELEGRAM_CHAT_ID_2 kalau ada). Sebelumnya cuma ke primary, jadi alert otomatis tidak
      pernah nyampe ke akun kedua walau user sehari-hari pakai akun itu."""
    token, _ = load_telegram_credentials()
    if not token:
        print("Telegram belum dikonfigurasi (TELEGRAM_BOT_TOKEN kosong) -- alert dilewati.")
        return

    if chat_id is not None:
        targets = [chat_id]
    else:
        targets = sorted(load_allowed_chat_ids())
        if not targets:
            print("Telegram belum dikonfigurasi (TELEGRAM_CHAT_ID kosong) -- alert dilewati.")
            return

    for target in targets:
        payload = {"chat_id": target, "text": text, "parse_mode": "HTML"}
        if reply_markup is not None:
            payload["reply_markup"] = json.dumps(reply_markup)

        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json=payload,
                timeout=10,
            )
            if not resp.ok:
                print(f"Gagal kirim alert Telegram ke {target}: HTTP {resp.status_code} {resp.text}")
        except Exception as e:  # network failure must never break signal detection itself
            print(f"Gagal kirim alert Telegram ke {target}: {e}")


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
        f"{signal['ticker']} {signal['stock_ret_2d']:+.1%} (2 hari) -- syarat sinyal\n"
        f"IHSG {signal['ihsg_ret_2d']:+.1%} (2 hari) -- info konteks saja, bukan syarat\n\n"
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

    for ticker in ["BUMI", "DEWA", "BRPT", "SMGR", "ESSA", "UNVR"]:
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
            # Fase AW: BUMI-only -- syarat IHSG ikut ambruk DIHAPUS (dulu wajib
            # ret_2d_ihsg <= DROP_THRESHOLD juga). ihsg_ret_2d masih dicatat & ditampilkan di
            # alert sebagai info konteks, bukan lagi filter.
            if not (trigger_row["ret_2d_stock"] <= DROP_THRESHOLD):
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
