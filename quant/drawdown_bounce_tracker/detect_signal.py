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
from datetime import date, datetime, time, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf

WIB = timezone(timedelta(hours=7))
MARKET_CLOSE_TIME = time(15, 20)  # closing + random close + buffer

TRACKING_START_DATE = date(2026, 7, 31)  # PROTOCOL.md lock date -- do not backdate
DROP_THRESHOLD = -0.05
DRAWDOWN_THRESHOLD = -0.20  # Fase BK: leg kedua aturan gabungan, lihat COMBINED_RULE_TICKERS
# Fase BK: aturan gabungan (ret_2d<=-5% ATAU drawdown_20d<=-20%) divalidasi ketat (protokol P1-P4,
# split 70/30 DAN 60/40, sama persis dengan yang mem-vonis kandidat DEWA TP/SL dulu) di 6 saham --
# LULUS PENUH di BUMI/DEWA/BRPT/ESSA/UNVR, SMGR gagal gate P4 (bootstrap CI95 lower bound belum
# > 0, walau arahnya tidak negatif) sehingga TETAP pakai aturan lama (ret_2d saja). Lihat plan.md
# Fase BK untuk tabel hasil lengkap per saham.
COMBINED_RULE_TICKERS = {"BUMI", "DEWA", "BRPT", "ESSA", "UNVR"}
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

# Fase BL: sinyal MOMENTUM (RSI14 > 60) -- strategi KEDUA yang berjalan paralel dengan
# drawdown-bounce di atas, hasil riset "Klaster B" (pola breakout/momentum, beda struktural dari
# mean-reversion). Trigger: RSI14 > 60 (bukan ret_2d/drawdown -- justru kebalikannya, momentum
# NAIK, bukan turun). Exit SAMA (trailing stop 2% / target 10 hari bursa) supaya perbandingan
# apple-to-apple dengan drawdown-bounce.
#
# Divalidasi protokol ketat P1-P4 yang SAMA (split 70/30 & 60/40, episode-independence) di 6 saham
# -- LULUS PENUH di BUMI/DEWA/BRPT, SEBAGIAN di ESSA (3/4 gate), GAGAL di SMGR/UNVR (saham lebih
# stabil, backtest cuma valid di saham yang sudah punya bull-run kuat sepanjang periode uji).
# HANYA diaktifkan untuk 3 yang lulus penuh -- lihat plan.md Fase BL untuk detail & CAVEAT PENTING:
# validasi ini SELURUHNYA terjadi di dalam rezim tren-naik yang sama (2024-sekarang) untuk
# BUMI/DEWA/BRPT -- BEDA dari drawdown-bounce yang tidak butuh tren naik untuk profit. Belum
# teruji di kondisi pasar sideways/turun panjang -- karena itu alertnya secara eksplisit ditandai
# EXPLORATORY/regime-dependent, bukan "tracked" penuh seperti drawdown-bounce.
MOMENTUM_RSI_THRESHOLD = 60
MOMENTUM_TICKERS = {"BUMI", "DEWA", "BRPT"}
MOMENTUM_TRACKING_START_DATE = date(2026, 8, 12)  # baru diaktifkan hari ini -- jangan backdate

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
    mobile: bold labels, blank-line-separated sections, plain numbers not a wall of text).

    Fase BN (lanjutan): "Rencana exit: tahan 10 hari bursa ≈ {tanggal}" DIHAPUS -- user protes ini
    menyesatkan, karena exit sebenarnya trailing stop 2% dari puncak (bisa jauh lebih cepat dari
    10 hari) ATAU target waktu 10 hari, mana duluan -- bukan "tahan sampai tanggal X". Diganti
    penjelasan mekanisme exit yang sebenarnya (lihat check_trailing_stop.py)."""
    icon = "\U0001F7E2" if signal["label"] == "tracked" else "\U0001F7E1"
    header = f"{icon} <b>SINYAL BELI: {signal['ticker']}</b>"

    warning = ""
    if signal["label"] != "tracked":
        warning = (
            "\n\n⚠️ <b>EXPLORATORY</b> — JANGAN dijadikan kesimpulan sendirian, "
            "lihat PROTOCOL.md (sample historisnya belum cukup meyakinkan untuk DEWA)."
        )

    # Fase BK: label syarat yang trigger -- Ret 2 Hari saja, Drawdown 20 Hari saja, atau Ganda
    # (keduanya sekaligus). SMGR tidak pernah "drawdown"/"ganda" (di luar COMBINED_RULE_TICKERS).
    signal_type = signal.get("signal_type", "ret2d")
    trigger_lines = [f"{signal['ticker']} {signal['stock_ret_2d']:+.1%} (2 hari)"]
    if signal_type == "ret2d":
        trigger_lines[0] += " -- syarat sinyal (Turun Tajam 2 Hari)"
    elif signal_type == "drawdown":
        trigger_lines[0] += " -- info konteks (bukan syarat kali ini)"
    else:  # ganda
        trigger_lines[0] += " -- syarat sinyal (Turun Tajam 2 Hari)"

    dd_20d = signal.get("dd_20d")
    if dd_20d is not None:
        dd_line = f"Drawdown 20 hari: {dd_20d:+.1%}"
        if signal_type == "drawdown":
            dd_line += " -- syarat sinyal (Drawdown Dalam)"
        elif signal_type == "ganda":
            dd_line += " -- syarat sinyal (Ganda: Turun Tajam + Drawdown Dalam)"
        else:
            dd_line += " -- info konteks (bukan syarat kali ini)"
        trigger_lines.append(dd_line)

    trigger_block = "\n".join(trigger_lines)

    return (
        f"{header}\n\n"
        f"<b>Trigger</b>: {signal['trigger_date']}\n"
        f"{trigger_block}\n"
        f"IHSG {signal['ihsg_ret_2d']:+.1%} (2 hari) -- info konteks saja, bukan syarat\n\n"
        f"<b>Entry</b>: {signal['entry_date']}\n"
        f"Harga: Rp{signal['entry_price']:.0f}\n\n"
        f"<b>Exit</b>: dipantau OTOMATIS tiap 15 menit -- keluar begitu harga mundur 2% dari "
        f"puncak (trailing stop, bisa kapan saja) ATAU maksimal 10 hari bursa kalau belum kena. "
        f"Alert susulan (\U0001F389 Puncak Baru / \U0001F534 Trailing Stop / \U0001F7E0 Target "
        f"Waktu) menyusul otomatis, tidak perlu dipantau manual.\n\n"
        f"<b>Info tambahan</b> (bukan bagian aturan -- live-checked hanya cocok ~3/8 kasus):\n"
        f"RSI14: {describe_rsi(signal.get('rsi14'))}\n"
        f"Stoch %K: {describe_stoch(signal.get('stoch_k'))}"
        f"{warning}"
    )


def format_momentum_alert(signal: dict) -> str:
    """Fase BL: alert TERPISAH untuk sinyal momentum (RSI>60) -- header, icon, dan warning beda
    dari format_signal_alert() (drawdown-bounce) supaya user tidak salah kira ini aturan yang
    sama. Selalu ditandai EXPLORATORY (caveat regime-dependence, lihat catatan di
    MOMENTUM_RSI_THRESHOLD di atas), tidak peduli saham yang lulus validasi penuh sekalipun."""
    entry_date = date.fromisoformat(signal["entry_date"])
    exit_estimate = entry_date + pd.tseries.offsets.BDay(10)

    header = f"\U0001F535 <b>SINYAL MOMENTUM: {signal['ticker']}</b>"

    return (
        f"{header}\n\n"
        f"<b>Trigger</b>: {signal['trigger_date']}\n"
        f"RSI14: {signal['rsi14']:.0f} (>{MOMENTUM_RSI_THRESHOLD}) -- syarat sinyal (Momentum Naik)\n\n"
        f"<b>Entry</b>: {signal['entry_date']}\n"
        f"Harga: Rp{signal['entry_price']:.0f}\n\n"
        f"<b>Rencana exit</b>: tahan 10 hari bursa (trailing stop 2% dari puncak)\n"
        f"≈ {exit_estimate.date().isoformat()}\n\n"
        f"⚠️ <b>EXPLORATORY</b> — beda dari sinyal drawdown-bounce (mean-reversion): ini "
        f"strategi MOMENTUM (beli saat menguat, bukan saat jatuh). Divalidasi ketat tapi HANYA "
        f"di dalam rezim tren-naik 2024-sekarang -- belum teruji di kondisi pasar sideways/turun "
        f"panjang. Lihat plan.md Fase BL sebelum all-in."
    )


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        # Fase BK: schema.sql's CREATE TABLE IF NOT EXISTS doesn't retrofit columns onto a DB
        # file that already existed pre-BK -- ALTER TABLE here is the migration for those.
        conn.execute("ALTER TABLE signals ADD COLUMN signal_type TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists
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
    # 60d (not 20d) so RSI14/Stoch14/drawdown_20d rolling windows are warmed up by the trigger
    # date -- RSI/Stoch context-only (see PROTOCOL.md), drawdown_20d IS part of the entry rule
    # since Fase BK.
    #
    # Fase BK: ganti dari "Adj Close" (harga disesuaikan dividen) ke "Close" MENTAH -- bug lama
    # yang sebelumnya ditandai "low-impact untuk BUMI/DEWA" (dividennya nyaris nol) tapi WAJIB
    # diperbaiki sebelum nambah saham berdividen nyata ke daftar ini. UNVR (salah satu dari 5
    # saham yang sekarang pakai aturan gabungan) itu pembayar dividen besar -- entry_price dan
    # drawdown_20d yang baru harus konsisten dengan backtest yang sudah divalidasi (yang pakai
    # Close mentah, bukan Adj Close).
    df = yf.download(symbol, period=f"{days}d", progress=False, auto_adjust=False)
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df.reset_index().rename(columns={"Date": "date"})
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["adj_close"] = df["Close"]  # nama kolom dipertahankan ("adj_close") supaya konsumen lama
    # (format_signal_alert, dll) tidak perlu diubah -- isinya sekarang Close mentah, bukan
    # Adj Close, per catatan Fase BK di atas.
    df["ret_2d"] = df["Close"].pct_change(2)
    df["rsi14"] = rsi(df["Close"])
    df["stoch_k"] = stochastic_k(df["High"], df["Low"], df["Close"])
    df["dd_20d"] = df["Close"] / df["Close"].rolling(20).max() - 1

    # Fase BO: guard snapshot-intraday — kalau baris terakhir tanggalnya hari ini DAN bursa belum
    # tutup (< 15:20 WIB), harga Close itu BUKAN closing final (masih bisa berubah sampai 15:00).
    # Drop baris itu supaya detect()/detect_heads_up()/detect_momentum() tidak pernah pakai harga
    # intraday sebagai harga entry atau trigger.
    # Bug asli: DEWA 12 Agu 2026, script jalan 09:16 WIB → tercatat Rp448, closing asli Rp466.
    now_wib = datetime.now(WIB)
    today = now_wib.date()
    if not df.empty and df.iloc[-1]["date"] == today and now_wib.time() < MARKET_CLOSE_TIME:
        df = df.iloc[:-1]
        print(f"⏳ {symbol}: data hari ini ({today}) dibuang — bursa belum tutup ({now_wib.strftime('%H:%M')} WIB < 15:20).")

    return df[["date", "adj_close", "ret_2d", "rsi14", "stoch_k", "dd_20d"]]


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
            # Fase BK: aturan gabungan -- leg drawdown_20d cuma berlaku untuk COMBINED_RULE_TICKERS
            # (SMGR gagal gate P4 di validasi ketat, tetap pakai ret_2d saja).
            ret2d_hit = bool(trigger_row["ret_2d_stock"] <= DROP_THRESHOLD)
            dd_hit = bool(
                ticker in COMBINED_RULE_TICKERS
                and trigger_row["dd_20d_stock"] <= DRAWDOWN_THRESHOLD
            )
            if not (ret2d_hit or dd_hit):
                continue

            signal_type = "ganda" if (ret2d_hit and dd_hit) else ("ret2d" if ret2d_hit else "drawdown")

            found.append({
                "ticker": ticker,
                "label": LABELS[ticker],
                "trigger_date": trigger_date.isoformat(),
                "ihsg_ret_2d": float(trigger_row["ret_2d_ihsg"]),
                "stock_ret_2d": float(trigger_row["ret_2d_stock"]),
                "dd_20d": float(trigger_row["dd_20d_stock"]),
                "signal_type": signal_type,
                "entry_date": entry_row["date"].isoformat(),
                # Fase BK: bug lama -- kolom sudah di-suffix oleh merge() (jadi "adj_close_stock",
                # bukan "adj_close" polos), tapi baris ini belum pernah kena karena belum ada
                # sinyal live yang benar-benar tembus sejak refactor merge diperkenalkan.
                "entry_price": float(entry_row["adj_close_stock"]),
                "rsi14": None if pd.isna(trigger_row["rsi14_stock"]) else float(trigger_row["rsi14_stock"]),
                "stoch_k": None if pd.isna(trigger_row["stoch_k_stock"]) else float(trigger_row["stoch_k_stock"]),
            })

    return found


def detect_heads_up() -> list[dict]:
    """Fase BN: peringatan dini (H-1 sore) -- BUKAN sinyal resmi, murni informasional. Beda dari
    detect() yang butuh entry_row (T+1) sudah ada, fungsi ini cek HARI PALING BARU yang closing-nya
    sudah tersedia (T) -- kalau syarat trigger (ret_2d<=-5% ATAU drawdown_20d<=-20%) sudah
    terpenuhi HARI INI, kemungkinan besar (bukan pasti -- closing besok bisa mundur lagi di bawah
    ambang) ini akan jadi sinyal resmi BESOK begitu closing T+1 tersedia dan detect() jalan lagi.
    Tidak mengubah aturan entry resmi sama sekali (masih tetap closing T+1) -- cuma kasih tahu
    LEBIH AWAL (sore ini, bukan besok pagi) supaya user bisa siap-siap, persis semangat Fase BA
    (session1 warning) yang sudah divalidasi tidak mengubah keputusan entry, cuma heads-up."""
    ihsg = fetch_recent("^JKSE")
    found = []

    for ticker in ["BUMI", "DEWA", "BRPT", "SMGR", "ESSA", "UNVR"]:
        stock = fetch_recent(f"{ticker}.JK")
        merged = stock.merge(ihsg, on="date", suffixes=("_stock", "_ihsg")).dropna()
        if merged.empty:
            continue

        latest = merged.iloc[-1]
        trigger_date = latest["date"]
        if trigger_date < TRACKING_START_DATE:
            continue

        ret2d_hit = bool(latest["ret_2d_stock"] <= DROP_THRESHOLD)
        dd_hit = bool(ticker in COMBINED_RULE_TICKERS and latest["dd_20d_stock"] <= DRAWDOWN_THRESHOLD)
        if not (ret2d_hit or dd_hit):
            continue

        signal_type = "ganda" if (ret2d_hit and dd_hit) else ("ret2d" if ret2d_hit else "drawdown")

        found.append({
            "ticker": ticker,
            "label": LABELS[ticker],
            "trigger_date": trigger_date.isoformat(),
            "ihsg_ret_2d": float(latest["ret_2d_ihsg"]),
            "stock_ret_2d": float(latest["ret_2d_stock"]),
            "dd_20d": float(latest["dd_20d_stock"]),
            "signal_type": signal_type,
        })

    return found


def format_heads_up_alert(signal: dict) -> str:
    """Fase BN (dirapikan): format label-tebal per bagian, konsisten dengan format_signal_alert(),
    dan EKSPLISIT bilang ini BUKAN sinyal resmi, harga entry BELUM ada (baru diketahui besok
    sore)."""
    signal_type = signal["signal_type"]
    reason = {
        "ret2d": f"{signal['stock_ret_2d']:+.1%} (2 hari) -- sudah memenuhi syarat trigger",
        "drawdown": f"drawdown {signal['dd_20d']:+.1%} dari puncak 20 hari -- sudah memenuhi syarat trigger",
        "ganda": f"{signal['stock_ret_2d']:+.1%} (2 hari) DAN drawdown {signal['dd_20d']:+.1%} "
                 f"(20 hari) -- keduanya sudah memenuhi syarat trigger",
    }[signal_type]

    return (
        f"\U0001F7E1 <b>PERINGATAN DINI: {signal['ticker']}</b>\n\n"
        f"<b>Closing hari ini</b>: {signal['trigger_date']}\n"
        f"{signal['ticker']} {reason}\n\n"
        f"<b>Status</b>: BUKAN sinyal resmi -- harga entry belum bisa diketahui sekarang.\n\n"
        f"<b>Kemungkinan besok</b>: ini jadi Sinyal Beli resmi (~15:18 WIB), entry = closing besok.\n\n"
        f"<b>Kenapa nunggu besok</b>: aturan resmi tetap entry closing T+1, sudah dibacktest -- "
        f"entry lebih cepat dari itu malah menurunkan win rate.\n\n"
        f"<b>Yang perlu kamu lakukan</b>: cuma pantau. Ini BUKAN ajakan beli hari ini/besok pagi."
    )


def detect_momentum() -> list[dict]:
    """Fase BL: strategi momentum (RSI14 > 60), terpisah dari detect() (drawdown-bounce).
    Trigger langsung dari data saham itu sendiri, tidak perlu merge dengan IHSG (momentum tidak
    pernah pakai IHSG sebagai syarat/konteks di riset validasinya)."""
    found = []

    for ticker in sorted(MOMENTUM_TICKERS):
        stock = fetch_recent(f"{ticker}.JK").dropna(subset=["rsi14"])
        if len(stock) < 2:
            continue

        for i in range(len(stock) - 1):
            trigger_row = stock.iloc[i]
            entry_row = stock.iloc[i + 1]
            trigger_date = trigger_row["date"]

            if trigger_date < MOMENTUM_TRACKING_START_DATE:
                continue
            if not (trigger_row["rsi14"] > MOMENTUM_RSI_THRESHOLD):
                continue

            found.append({
                "ticker": ticker,
                "trigger_date": trigger_date.isoformat(),
                "rsi14": float(trigger_row["rsi14"]),
                "entry_date": entry_row["date"].isoformat(),
                "entry_price": float(entry_row["adj_close"]),
            })

    return found


POSITIONS_PATH = Path(__file__).parent / "open_positions.json"


def load_positions() -> list[dict]:
    if not POSITIONS_PATH.is_file():
        return []
    return json.loads(POSITIONS_PATH.read_text(encoding="utf-8"))


def save_positions(positions: list[dict]) -> None:
    POSITIONS_PATH.write_text(json.dumps(positions, indent=2), encoding="utf-8")


def register_open_position(ticker: str, entry_date: str, entry_price: float) -> None:
    """Fase BM: daftarkan otomatis ke open_positions.json begitu sinyal baru terdeteksi -- supaya
    check_trailing_stop.py (jalan tiap 15 menit) langsung mulai mantau TANPA perlu user ketik
    /open manual dulu. Sama seperti /open manual: replace kalau ticker itu sudah ada di daftar
    (satu ticker = satu posisi aktif pada satu waktu, konsisten dengan asumsi lama)."""
    positions = load_positions()
    positions = [p for p in positions if p["ticker"] != ticker]
    positions.append({
        "ticker": ticker,
        "entry_date": entry_date,
        "entry_price": entry_price,
        "alerted_pullback_pct": None,
    })
    save_positions(positions)


def main() -> None:
    conn = get_connection()
    signals = detect()
    momentum_signals = detect_momentum()
    heads_up_signals = detect_heads_up()

    inserted = 0
    for s in signals:
        try:
            conn.execute(
                """INSERT INTO signals
                (ticker, label, trigger_date, ihsg_ret_2d, stock_ret_2d, entry_date, entry_price,
                 rsi14, stoch_k, signal_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (s["ticker"], s["label"], s["trigger_date"], s["ihsg_ret_2d"], s["stock_ret_2d"],
                 s["entry_date"], s["entry_price"], s["rsi14"], s["stoch_k"], s["signal_type"]),
            )
            inserted += 1
            print(f"SIGNAL BARU: {s['ticker']} ({s['label']}) trigger {s['trigger_date']} "
                  f"-> entry {s['entry_date']} @ {s['entry_price']:.0f}")

            send_telegram_alert(format_signal_alert(s))

            # Fase BM: daftar otomatis ke pemantauan trailing-stop + jembatan ke Trade Journal
            # web (SYNC_OPEN diparsing PHP, sama pola dengan SYNC_CLOSE Fase BJ).
            register_open_position(s["ticker"], s["entry_date"], s["entry_price"])
            print(f"SYNC_OPEN|{s['ticker']}|{s['entry_price']}|{s['entry_date']}|GABUNGAN|{s['signal_type']}")
        except sqlite3.IntegrityError:
            pass  # already logged, UNIQUE(ticker, trigger_date) makes this idempotent

    inserted_momentum = 0
    for s in momentum_signals:
        try:
            conn.execute(
                """INSERT INTO momentum_signals
                (ticker, trigger_date, rsi14, entry_date, entry_price)
                VALUES (?, ?, ?, ?, ?)""",
                (s["ticker"], s["trigger_date"], s["rsi14"], s["entry_date"], s["entry_price"]),
            )
            inserted_momentum += 1
            print(f"SINYAL MOMENTUM BARU: {s['ticker']} trigger {s['trigger_date']} "
                  f"(RSI14={s['rsi14']:.0f}) -> entry {s['entry_date']} @ {s['entry_price']:.0f}")

            send_telegram_alert(format_momentum_alert(s))

            register_open_position(s["ticker"], s["entry_date"], s["entry_price"])
            print(f"SYNC_OPEN|{s['ticker']}|{s['entry_price']}|{s['entry_date']}|MOMENTUM|rsi{s['rsi14']:.0f}")
        except sqlite3.IntegrityError:
            pass

    inserted_heads_up = 0
    for s in heads_up_signals:
        try:
            conn.execute(
                """INSERT INTO heads_up_alerts
                (ticker, trigger_date, ihsg_ret_2d, stock_ret_2d, dd_20d, signal_type)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (s["ticker"], s["trigger_date"], s["ihsg_ret_2d"], s["stock_ret_2d"], s["dd_20d"],
                 s["signal_type"]),
            )
            inserted_heads_up += 1
            print(f"PERINGATAN DINI: {s['ticker']} closing {s['trigger_date']} sudah memenuhi "
                  f"syarat ({s['signal_type']}) -- kemungkinan jadi sinyal resmi besok.")

            send_telegram_alert(format_heads_up_alert(s))
        except sqlite3.IntegrityError:
            pass  # sudah pernah diperingatkan untuk trigger_date ini

    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    total_momentum = conn.execute("SELECT COUNT(*) FROM momentum_signals").fetchone()[0]
    total_heads_up = conn.execute("SELECT COUNT(*) FROM heads_up_alerts").fetchone()[0]
    conn.close()

    if inserted == 0:
        print(f"Tidak ada sinyal drawdown-bounce baru. Tidak ada trigger sejak {TRACKING_START_DATE}. Total tercatat: {total}.")
    else:
        print(f"{inserted} sinyal drawdown-bounce baru dicatat. Total tercatat: {total}.")

    if inserted_momentum == 0:
        print(f"Tidak ada sinyal momentum baru. Tidak ada trigger sejak {MOMENTUM_TRACKING_START_DATE}. Total tercatat: {total_momentum}.")
    else:
        print(f"{inserted_momentum} sinyal momentum baru dicatat. Total tercatat: {total_momentum}.")

    if inserted_heads_up == 0:
        print(f"Tidak ada peringatan dini baru. Total tercatat: {total_heads_up}.")
    else:
        print(f"{inserted_heads_up} peringatan dini baru dicatat. Total tercatat: {total_heads_up}.")


if __name__ == "__main__":
    main()
