#!/usr/bin/env python3
"""Poll Telegram for /open, /close, /status, /history, /price, /help commands, update
open_positions.json directly -- no need to tell Claude in chat every time a position changes.

Commands (send to @IDX_alert_keysentimen_bot -- or tap the keyboard buttons under the message box):
  /open TICKER [HARGA] [TANGGAL]   -- tambah posisi baru (HARGA/TANGGAL opsional -- kalau HARGA
                                       tidak disebut, dipakai harga penutupan terakhir live)
  /close TICKER [HARGA] [TANGGAL]  -- tutup posisi (HARGA opsional, sama seperti /open)
  /status                          -- tampilkan posisi yang lagi dipantau
  /history                         -- 10 posisi terakhir yang sudah ditutup (dari Trade Journal)
  /price TICKER                    -- cek harga live TICKER APA SAJA (bukan cuma BUMI/DEWA yang
                                       lagi dipantau) -- buat mantau kandidat sebelum entry
  /ihsg                            -- progres IHSG + saham yang dipantau menuju ambang entry -5%
  /help                            -- daftar perintah ini, dikirim balik ke chat

Uses long-polling (getUpdates with an offset), not a webhook -- no public HTTPS endpoint needed,
works fine from a local dev machine. Only processes messages from an ALLOWED chat -- TELEGRAM_CHAT_ID
(primary) plus the optional TELEGRAM_CHAT_ID_2 (Fase AQ, a second Telegram account/number), ignores
everyone else, so a leaked bot token can't be used to inject fake positions. Replies always go back
to whichever allowed chat actually sent the command, not always the primary one.

/history reads closed_trades_cache.json, a snapshot written by CheckTelegramCommandsCommand.php
right before this script runs (see refreshClosedTradesCache() there). This script deliberately
never queries MySQL directly -- same resilience pattern as open_positions.json -- so if the DB was
down at refresh time, /history just serves the last-known snapshot instead of failing outright.
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
from detect_signal import (  # noqa: E402
    BUTTON_CLOSE_BUMI,
    BUTTON_CLOSE_DEWA,
    BUTTON_CLOSE_BRPT,
    BUTTON_CLOSE_SMGR,
    BUTTON_CLOSE_ESSA,
    BUTTON_CLOSE_UNVR,
    BUTTON_HELP,
    BUTTON_HISTORY,
    BUTTON_STATUS,
    DROP_THRESHOLD,
    LABELS,
    default_keyboard,
    load_allowed_chat_ids,
    load_telegram_credentials,
    send_telegram_alert,
)
from check_trailing_stop import (  # noqa: E402
    PULLBACK_THRESHOLD,
    TARGET_HOLD_DAYS,
    WARN_HOLD_DAYS,
    compute_snapshot,
)

POSITIONS_PATH = Path(__file__).parent / "open_positions.json"
OFFSET_PATH = Path(__file__).parent / "telegram_update_offset.txt"
CLOSED_TRADES_CACHE_PATH = Path(__file__).parent / "closed_trades_cache.json"

# Icon button labels -> canonical command text, so handle_command()'s parsing only needs to know
# the /open, /close, /status forms.
BUTTON_LABELS = {
    BUTTON_STATUS: "/status",
    BUTTON_HISTORY: "/history",
    BUTTON_CLOSE_BUMI: "/close BUMI",
    BUTTON_CLOSE_DEWA: "/close DEWA",
    BUTTON_CLOSE_BRPT: "/close BRPT",
    BUTTON_CLOSE_SMGR: "/close SMGR",
    BUTTON_CLOSE_ESSA: "/close ESSA",
    BUTTON_CLOSE_UNVR: "/close UNVR",
    BUTTON_HELP: "/help",
}

# HARGA is optional -- a bare "/close BUMI" (as sent by the keyboard button, no price typed) falls
# through to fetch_live_price() below.
COMMAND_PATTERN = re.compile(
    r"^/(open|close)\s+([A-Za-z]{2,6})(?:\s+([\d.,]+))?(?:\s+(\d{4}-\d{2}-\d{2}))?", re.IGNORECASE
)
PRICE_PATTERN = re.compile(r"^/price\s+([A-Za-z]{2,6})", re.IGNORECASE)
IHSG_PATTERN = re.compile(r"^/ihsg\s*$", re.IGNORECASE)


def fetch_live_price(ticker: str) -> float | None:
    df = yf.download(f"{ticker}.JK", period="5d", progress=False, auto_adjust=False)
    if df.empty:
        return None
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    return float(df["Close"].iloc[-1])


def fetch_price_snapshot(ticker: str) -> dict | None:
    """Harga & jam TERKINI (bar 15 menit terakhir, sama pola dengan check_trailing_stop.py) untuk
    /price -- ticker apa saja, bukan cuma yang lagi dipantau. Persentase perubahan tetap dihitung
    terhadap penutupan HARIAN kemarin (bukan bar 15 menit sebelumnya) -- itu yang bermakna sebagai
    "naik/turun hari ini", bukan noise antar-bar."""
    daily = yf.download(f"{ticker}.JK", period="5d", progress=False, auto_adjust=False)
    if daily.empty:
        return None
    daily.columns = [c[0] if isinstance(c, tuple) else c for c in daily.columns]

    intraday = yf.download(f"{ticker}.JK", period="5d", interval="15m", progress=False, auto_adjust=False)
    if not intraday.empty:
        intraday.columns = [c[0] if isinstance(c, tuple) else c for c in intraday.columns]
        intraday.index = intraday.index.tz_convert("Asia/Jakarta")
        price = float(intraday["Close"].iloc[-1])
        as_of = intraday.index[-1]
    else:
        # fallback kalau data 15 menit kosong (mis. ticker jarang diperdagangkan)
        price = float(daily["Close"].iloc[-1])
        as_of = daily.index[-1]

    snapshot = {"price": price, "as_of": as_of, "prev_close": None, "change_pct": None}
    if len(daily) >= 2:
        prev_close = float(daily["Close"].iloc[-2])
        snapshot["prev_close"] = prev_close
        if prev_close:
            snapshot["change_pct"] = (price - prev_close) / prev_close

    return snapshot


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
            "Perintah tidak dikenali. Ketik /help untuk daftar lengkap, atau pakai tombol di bawah."
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
        # Fase BJ: telegram_commands.py sengaja tidak pernah sentuh MySQL langsung (resilience
        # sama seperti open_positions.json -- lihat CheckTelegramCommandsCommand.php). Baris
        # SYNC_CLOSE ini dicetak ke stdout supaya PHP (yang MEMANG sudah asumsikan DB nyala saat
        # command artisan jalan) bisa parse & terapkan penutupan yang sama ke tabel `trades` --
        # jembatan satu arah Telegram -> web Trade Journal, otomatis, tanpa perlu tutup 2 kali.
        print(f"SYNC_CLOSE|{ticker}|{price}|{cmd_date}")
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
    """Progres LIVE tiap posisi terhadap 3 aturan exit yang aktif (trailing stop 2%, H-1 hari
    ke-9, target waktu hari ke-10) -- dipanggil on-demand tiap /status, bukan cuma nunggu alert
    otomatis bunyi. Pakai compute_snapshot() dari check_trailing_stop.py (read-only, tidak
    pernah kirim alert/ubah open_positions.json), jadi angkanya selalu konsisten dengan yang
    dipakai sistem alert asli.

    Fase BN (dirapikan 2x atas masukan user): "Hari bursa ke-X dari 10" DIHAPUS. Lalu wording
    trailing-stop disederhanakan gaya kartu posisi broker (StockBit/IBKR dst) -- cukup dua angka
    (Puncak, Stop), tanpa mengulang aturan "-2%" atau persentase jarak tiap kali (user sudah tahu
    aturannya, alert otomatis yang bunyi begitu kena, /status cuma untuk cek cepat)."""
    if not positions:
        return "Tidak ada posisi yang sedang dipantau."

    lines = ["<b>Posisi yang dipantau:</b>\n"]
    # Fase BU: dua strategi (GABUNGAN/MOMENTUM) bisa punya posisi bersamaan di saham yang sama --
    # tag [strategi] cuma ditampilkan kalau ticker itu muncul lebih dari sekali, supaya kartu
    # normal (1 posisi per saham, kasus umum) tetap ringkas seperti sebelumnya.
    ticker_counts: dict[str, int] = {}
    for p in positions:
        ticker_counts[p["ticker"]] = ticker_counts.get(p["ticker"], 0) + 1

    for p in positions:
        ticker = p["ticker"]
        entry_price = float(p["entry_price"])
        label = f"{ticker} [{p.get('strategy', 'GABUNGAN')}]" if ticker_counts[ticker] > 1 else ticker
        snap = compute_snapshot(ticker, p["entry_date"], entry_price)

        if snap is None:
            lines.append(
                f"- <b>{label}</b>: entry Rp{entry_price:.0f} ({p['entry_date']}) "
                f"-- data harga live tidak tersedia saat ini"
            )
            continue

        sign = "\U0001F7E2" if snap["unrealized_pct"] >= 0 else "\U0001F534"
        is_ganda = p.get("signal_type") == "ganda"

        notes = []
        if snap["trading_days"] >= TARGET_HOLD_DAYS:
            notes.append(f"sudah kena target waktu {TARGET_HOLD_DAYS} hari")
        elif snap["trading_days"] >= WARN_HOLD_DAYS:
            notes.append("H-1 menuju target waktu")

        if is_ganda:
            days_left = max(0, TARGET_HOLD_DAYS - snap["trading_days"])
            note_txt = f" ({', '.join(notes)})" if notes else ""
            lines.append(
                f"{sign} <b>{label}</b>: Rp{snap['current']:.0f} ({snap['unrealized_pct']:+.1%}) "
                f"dari entry Rp{entry_price:.0f}\n"
                f"   Puncak Rp{snap['peak']:.0f} | B&amp;H {TARGET_HOLD_DAYS}d (sisa {days_left}d){note_txt}\n"
            )
        else:
            stop_price = snap["peak"] * (1 - PULLBACK_THRESHOLD)
            if snap["pullback"] >= PULLBACK_THRESHOLD:
                notes.append("sudah lewat ambang trailing stop")
            note_txt = f" ({', '.join(notes)})" if notes else ""
            lines.append(
                f"{sign} <b>{label}</b>: Rp{snap['current']:.0f} ({snap['unrealized_pct']:+.1%}) "
                f"dari entry Rp{entry_price:.0f}\n"
                f"   Puncak Rp{snap['peak']:.0f} | Stop Rp{stop_price:.0f}{note_txt}\n"
            )
    return "\n".join(lines)


def load_closed_trades() -> dict:
    """Fase BJ: cache sekarang punya 2 bagian -- {"overall": {...}, "recent": [...]}. Fallback ke
    bentuk lama (list mentah, cache dari sebelum perubahan ini) supaya tidak crash kalau
    cache belum sempat di-refresh ulang setelah deploy."""
    if not CLOSED_TRADES_CACHE_PATH.is_file():
        return {"overall": None, "recent": []}
    try:
        data = json.loads(CLOSED_TRADES_CACHE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"overall": None, "recent": []}

    if isinstance(data, list):  # cache format lama
        return {"overall": None, "recent": data}
    return {"overall": data.get("overall"), "recent": data.get("recent", [])}


RESULT_LABELS = {
    "hit_target_1": "kena target 1",
    "hit_target_2": "kena target 2",
    "stop_loss": "stop loss",
    "manual_close": "tutup manual",
}


def _short_date(iso_date: str | None) -> str:
    """'2026-07-08' -> '08 Jul' -- lebih ringkas dibaca di layar HP daripada tanggal ISO penuh."""
    if not iso_date:
        return "?"
    try:
        from datetime import datetime
        return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%d %b")
    except ValueError:
        return iso_date


def format_history(cache: dict) -> str:
    overall = cache.get("overall")
    trades = cache.get("recent") or []

    if not trades and not overall:
        return (
            "Belum ada riwayat posisi yang ditutup, atau cache-nya belum sempat di-refresh "
            "(butuh MySQL nyala minimal sekali sejak posisi terakhir ditutup)."
        )

    lines = []
    if overall:
        # Ringkasan dari SEMUA trade closed -- basis sama persis dengan kartu ringkasan di web
        # /trades, bukan cuma dihitung dari 10 posisi yang ditampilkan di bawah (dulu sempat
        # bikin bingung karena angkanya beda jauh dari web).
        total_pnl = overall.get("total_pnl") or 0
        total_sign = "-" if total_pnl < 0 else "+"
        total_txt = f"{total_sign}Rp{abs(total_pnl):,.0f}".replace(",", ".")
        lines.append(
            f"<b>Ringkasan {overall.get('total_trades', 0)} total trade (semua, seperti di web):</b>\n"
            f"\U0001F7E2 {overall.get('win_count', 0)} menang • \U0001F534 {overall.get('loss_count', 0)} rugi "
            f"• Win rate {overall.get('win_rate', 0):.1f}%\n"
            f"Total P&amp;L {total_txt} • Avg R:R 1:{overall.get('avg_rr', 0):.2f} • "
            f"Expectancy {overall.get('expectancy', 0):+.1f}% • Avg holding {overall.get('avg_holding', 0):.1f} hari\n"
        )
    else:
        win_count = sum(1 for t in trades if (t.get("pnl_total") or 0) > 0)
        loss_count = len(trades) - win_count
        total_pnl = sum(t.get("pnl_total") or 0 for t in trades)
        total_sign = "-" if total_pnl < 0 else "+"
        total_txt = f"{total_sign}Rp{abs(total_pnl):,.0f}".replace(",", ".")
        lines.append(f"\U0001F7E2 {win_count} menang • \U0001F534 {loss_count} rugi • Total P&amp;L {total_txt}\n")

    lines.append(f"<b>{min(len(trades), 10)} posisi terakhir yang ditutup:</b>")
    for t in trades[:10]:
        entry = float(t["entry_price"])
        exit_ = float(t["exit_price"]) if t.get("exit_price") is not None else None
        pnl_total = t.get("pnl_total")
        pnl_pct = t.get("pnl_percent")
        result = RESULT_LABELS.get(t.get("result"), t.get("result") or "-")
        sign = "\U0001F7E2" if (pnl_total or 0) >= 0 else "\U0001F534"

        exit_txt = f"Rp{exit_:.0f}" if exit_ is not None else "-"
        if pnl_total is not None and pnl_pct is not None:
            pnl_sign = "-" if pnl_total < 0 else ""
            pnl_txt = f"{pnl_sign}Rp{abs(pnl_total):,.0f} ({pnl_pct:+.1f}%)".replace(",", ".")
        else:
            pnl_txt = "-"
        holding_txt = f", {t['holding_days']}h" if t.get("holding_days") is not None else ""
        date_range = f"{_short_date(t.get('entry_date'))} → {_short_date(t.get('exit_date'))}{holding_txt}"

        lines.append(
            f"{sign} <b>{t['ticker']}</b>: Rp{entry:.0f} → {exit_txt} ({date_range})\n"
            f"   P&amp;L {pnl_txt} -- {result}\n"
        )
    return "\n".join(lines)


def format_help() -> str:
    return (
        "<b>Perintah yang tersedia:</b>\n\n"
        "\U0001F4CA <b>/status</b>\n"
        "Lihat posisi yang lagi dipantau trailing-stop.\n\n"
        "\U0001F4DC <b>/history</b>\n"
        "10 posisi terakhir yang sudah ditutup, dari Trade Journal.\n\n"
        "\U0001F50D <b>/price TICKER</b>\n"
        "Cek harga live ticker apa saja, contoh: <code>/price BBCA</code>.\n\n"
        "\U0001F30F <b>/ihsg</b>\n"
        "Progres IHSG + saham yang dipantau menuju ambang entry -5% dalam 2 hari.\n\n"
        "➕ <b>/open TICKER [HARGA] [TANGGAL]</b>\n"
        "Tambah posisi baru ke pemantauan. HARGA/TANGGAL boleh dikosongkan -- "
        "otomatis pakai harga live &amp; tanggal hari ini. Contoh: <code>/open BUMI 159</code>.\n\n"
        "\U0001F534 <b>/close TICKER [HARGA] [TANGGAL]</b>\n"
        "Tutup posisi dari pemantauan (tidak akan ada alert lagi untuknya). "
        "Contoh: <code>/close BUMI</code> atau tombol Tutup di bawah.\n\n"
        "❓ <b>/help</b>\n"
        "Tampilkan pesan ini.\n\n"
        "Tombol di bawah kotak pesan cuma jalan pintas untuk /status, /history, /close BUMI/DEWA, "
        "dan /help -- /price dan /open harus diketik karena ticker-nya bebas."
    )


def format_price(ticker: str, snapshot: dict | None) -> str:
    if snapshot is None:
        return f"Tidak ada data harga untuk {ticker} -- cek lagi penulisan ticker-nya (tanpa .JK)."

    price = snapshot["price"]
    as_of = snapshot["as_of"].strftime("%d %b %H:%M")
    change_pct = snapshot["change_pct"]

    if change_pct is None:
        return f"<b>{ticker}</b>: Rp{price:.0f} (per {as_of})"

    arrow = "\U0001F7E2▲" if change_pct >= 0 else "\U0001F534▼"
    return f"{arrow} <b>{ticker}</b>: Rp{price:.0f} ({change_pct:+.1%} dari penutupan sebelumnya, per {as_of})"


def fetch_2d_return(symbol: str) -> dict | None:
    """Return 2-hari kumulatif (penutupan hari ini vs 2 hari bursa sebelumnya) -- PAKAI 'Close'
    MENTAH, bukan 'Adj Close' (lihat Fase AR: Adj Close sudah dikurangi dividen masa depan,
    salah untuk perbandingan harga apa adanya). Dipakai /ihsg untuk cek progres menuju ambang
    entry -5% aturan drawdown-bounce (DROP_THRESHOLD, sama persis dengan detect_signal.py)."""
    df = yf.download(symbol, period="10d", progress=False, auto_adjust=False)
    if df.empty:
        return None
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    close = df["Close"]
    if len(close) < 3:
        return None
    ret_2d = float(close.iloc[-1] / close.iloc[-3] - 1)
    return {"ret_2d": ret_2d, "last_close": float(close.iloc[-1]), "last_date": df.index[-1]}


def format_ihsg_progress() -> str:
    ihsg = fetch_2d_return("^JKSE")
    if ihsg is None:
        return "Tidak bisa ambil data IHSG sekarang -- coba lagi nanti."

    ihsg_hit = ihsg["ret_2d"] <= DROP_THRESHOLD
    progress_pct = min(1.0, ihsg["ret_2d"] / DROP_THRESHOLD) if ihsg["ret_2d"] < 0 else 0.0
    ihsg_status = "\U0001F6A8 SUDAH LEWAT AMBANG" if ihsg_hit else f"{progress_pct:.0%} menuju ambang -5%"

    last_close_txt = f"{ihsg['last_close']:,.0f}".replace(",", ".")
    lines = [
        "<b>Progres sinyal entry drawdown-bounce</b>",
        "(aturan: IHSG DAN saham sama-sama turun ≥5% dalam 2 hari)\n",
        f"<b>IHSG</b>: {ihsg['ret_2d']:+.2%} dalam 2 hari -- {ihsg_status}",
        f"   Penutupan terakhir: {last_close_txt} ({ihsg['last_date'].strftime('%d %b')})\n",
    ]

    if not ihsg_hit:
        lines.append(
            "IHSG belum turun cukup dalam -- sinyal entry TIDAK akan muncul hari ini walau "
            "ada saham yang jatuh tajam sendirian.\n"
        )
    else:
        lines.append("IHSG sudah lewat ambang -- tinggal cek saham mana yang ikut turun juga.\n")

    lines.append("<b>Progres saham yang dipantau:</b>")
    for ticker, label in LABELS.items():
        snap = fetch_2d_return(f"{ticker}.JK")
        if snap is None:
            lines.append(f"- {ticker}: data tidak tersedia")
            continue
        hit = snap["ret_2d"] <= DROP_THRESHOLD
        tag = "\U0001F6A8 KENA" if hit else f"{snap['ret_2d']:+.2%}"
        label_tag = "" if label == "tracked" else " <i>(exploratory)</i>"
        lines.append(f"- <b>{ticker}</b>{label_tag}: {tag} dalam 2 hari")

    return "\n".join(lines)


def main() -> None:
    token, _ = load_telegram_credentials()
    allowed_ids = load_allowed_chat_ids()
    if not token or not allowed_ids:
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
        sender_chat_id = str(message.get("chat", {}).get("id"))
        if sender_chat_id not in allowed_ids:
            continue  # ignore anyone except the allowed chat(s) -- primary + TELEGRAM_CHAT_ID_2

        text = message.get("text", "")
        text = BUTTON_LABELS.get(text.strip(), text)  # translate a tapped icon button, if any

        if text.strip() == "/status":
            send_telegram_alert(format_status(positions), reply_markup=default_keyboard(), chat_id=sender_chat_id)
            processed += 1
            continue

        if text.strip() == "/history":
            send_telegram_alert(format_history(load_closed_trades()), reply_markup=default_keyboard(), chat_id=sender_chat_id)
            processed += 1
            continue

        if text.strip() == "/help":
            send_telegram_alert(format_help(), reply_markup=default_keyboard(), chat_id=sender_chat_id)
            processed += 1
            continue

        price_match = PRICE_PATTERN.match(text.strip())
        if price_match:
            ticker = price_match.group(1).upper()
            send_telegram_alert(
                format_price(ticker, fetch_price_snapshot(ticker)),
                reply_markup=default_keyboard(), chat_id=sender_chat_id,
            )
            processed += 1
            continue

        if IHSG_PATTERN.match(text.strip()):
            send_telegram_alert(format_ihsg_progress(), reply_markup=default_keyboard(), chat_id=sender_chat_id)
            processed += 1
            continue

        if text.startswith("/open") or text.startswith("/close"):
            positions, reply = handle_command(text, positions)
            send_telegram_alert(reply, reply_markup=default_keyboard(), chat_id=sender_chat_id)
            processed += 1
            print(f"Diproses: {text.strip()} -> {reply}")

    save_positions(positions)
    save_offset(latest_update_id)
    print(f"{processed} perintah diproses." if processed else "Tidak ada perintah relevan.")


if __name__ == "__main__":
    main()
