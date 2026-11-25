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
TS_ACTIVATION_BUFFER = 0.02  # Fase FF-2 OOS (193 trades, 15m chronological): TS 2.0% only activates
# once Peak >= Entry * 1.02 (+2.0% buffer), winning BOTH Discovery (PF 3.37->3.48) & Holdout Crisis
# (PF 1.01->1.03), lifting WR 45.1%->50.8% & slashing negative trailing-stop exits by 74.5%.
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


def compute_snapshot(
    ticker: str,
    entry_date: str,
    entry_price: float,
    strategy: str = "GABUNGAN",
) -> dict | None:
    """Read-only: puncak, harga terkini, mundur dari puncak, hari bursa ke berapa -- TIDAK PERNAH
    mengirim alert atau mengubah open_positions.json. Dipakai oleh check_position() di bawah
    (yang bisa kirim alert) dan oleh telegram_commands.py::format_status() (murni tampilan on-
    demand pas user ketik /status, terlepas dari apakah alert otomatis sudah pernah terkirim).

    Fase BW: puncak TIDAK LAGI menghitung intraday HARI ENTRY ITU SENDIRI -- cuma
    max(entry_price, High hari-hari SESUDAH entry). Ini menyamakan definisi "puncak" dengan
    backtest yang memvalidasi aturan trailing-stop (screen_candidates.py/research_average_down.py:
    peak dimulai FLAT di entry Close, baru bertambah dari entry_idx+1 dan seterusnya) -- backtest
    itu TIDAK PERNAH menghitung intraday hari entry sebagai bagian puncak.

    Fase Chronological 15m Guard: jika bar terakhir (misal 16:00 pre-closing/closing) memantul
    tipis sehingga terlihat mundur < 2.0%, fungsi ini juga memeriksa bar-bar 15 menit secara
    kronologis sesudah hari entry. Jika pada jam bursa (misal 14:00 atau 15:00) harga sempat
    mundur >= 2.0% (atau >= 2.5% untuk BOTTOM_TO_TOP profit >= 3%) dari puncak berjalannya,
    maka trigger kronologis tersebut tetap tertangkap akurat dan tidak terlewat."""
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
    trading_days = df.index.normalize().nunique()

    if not after_entry_day.empty:
        gain_from_entry = (peak - entry_price) / entry_price if entry_price else 0.0
        eff_thresh = (
            0.025
            if (strategy == "BOTTOM_TO_TOP" and gain_from_entry >= 0.03)
            else PULLBACK_THRESHOLD
        )
        if pullback < eff_thresh:
            r_peak = entry_price
            r_peak_ts = after_entry_day.index[0]
            best_trig: dict | None = None
            for ts, row in after_entry_day.iterrows():
                h = float(row["High"])
                c = float(row["Close"])
                if h > r_peak:
                    r_peak = h
                    r_peak_ts = ts
                if r_peak >= entry_price * (1.0 + TS_ACTIVATION_BUFFER):
                    r_gain = (r_peak - entry_price) / entry_price
                    r_thresh = (
                        0.025
                        if (strategy == "BOTTOM_TO_TOP" and r_gain >= 0.03)
                        else PULLBACK_THRESHOLD
                    )
                    r_pb = (r_peak - c) / r_peak
                    if r_pb >= r_thresh:
                        if best_trig is None or r_peak > best_trig["peak"]:
                            best_trig = {
                                "peak": r_peak,
                                "peak_ts": r_peak_ts,
                                "current": c,
                                "current_ts": ts,
                                "pullback": r_pb,
                            }
            if best_trig is not None:
                peak = best_trig["peak"]
                peak_ts = best_trig["peak_ts"]
                current = best_trig["current"]
                current_ts = best_trig["current_ts"]
                pullback = best_trig["pullback"]
            else:
                sl_mult = 0.97 if strategy == "BOTTOM_TO_TOP" else 0.965
                sl_price = round(entry_price * sl_mult, 2)
                sl_bars = after_entry_day[after_entry_day["Close"] <= sl_price]
                if not sl_bars.empty and current > sl_price:
                    first_sl_ts = sl_bars.index[0]
                    current = float(sl_bars["Close"].iloc[0])
                    current_ts = first_sl_ts
                    pullback = (peak - current) / peak

    unrealized_pct = (current - entry_price) / entry_price

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

    snap = compute_snapshot(ticker, entry_date, entry_price, strategy=strategy)
    if snap is None:
        print(f"{label}: tidak ada data 15 menit sejak {entry_date}, dilewati.")
        return

    peak, peak_ts = snap["peak"], snap["peak_ts"]
    current, current_ts = snap["current"], snap["current_ts"]
    pullback = snap["pullback"]
    unrealized_pct = snap["unrealized_pct"]
    trading_days = snap["trading_days"]

    is_bottom_to_top = strategy == "BOTTOM_TO_TOP"
    gain_from_entry = (peak - entry_price) / entry_price if entry_price else 0.0
    pullback_thresh = 0.025 if (is_bottom_to_top and gain_from_entry >= 0.03) else PULLBACK_THRESHOLD
    exit_mode = (
        "Lock-2.5%/SL-3%"
        if (is_bottom_to_top and gain_from_entry >= 0.03)
        else ("TS-2%/SL-3%" if is_bottom_to_top else "TS-2%/SL-3.5%")
    )

    print(
        f"{label}: entry {entry_price:.0f} ({entry_date}) | puncak {peak:.0f} "
        f"({peak_ts.strftime('%d %b %H:%M')}) | sekarang {current:.0f} "
        f"({current_ts.strftime('%d %b %H:%M')}) | mundur {pullback:.1%} | "
        f"hari bursa ke-{trading_days} | P&L {unrealized_pct:+.1%} | exit={exit_mode}"
    )

    # --- Lapis 2: Puncak Baru & Trailing Stop 2.0% dari Puncak (Kunci Cuan) ---
    milestone_base = position.get("milestone_peak") or entry_price
    if peak >= milestone_base * (1 + NEW_HIGH_THRESHOLD):
        gain_from_last = (peak - milestone_base) / milestone_base
        new_stop_level = peak * (1 - pullback_thresh)
        send_telegram_alert(
            f"\U0001F389 <b>PUNCAK BARU: {label}</b>\n\n"
            f"Harga bikin rekor tertinggi baru sejak entry: <b>Rp{peak:.0f}</b> "
            f"({peak_ts.strftime('%d %b %H:%M')}), naik <b>{gain_from_last:+.1%}</b> dari puncak "
            f"sebelumnya (Rp{milestone_base:.0f}).\n\n"
            f"<b>Entry</b>: {entry_date} @ Rp{entry_price:.0f}\n"
            f"<b>P&amp;L saat ini</b>: {unrealized_pct:+.1%}\n\n"
            f"Level trailing stop ikut naik ke sekitar <b>Rp{new_stop_level:.0f}</b> "
            f"({pullback_thresh:.1%} di bawah puncak baru ini). Alert saja -- keputusan tetap "
            f"di kamu."
        )
        position["milestone_peak"] = peak
        print(f"  -> ALERT PUNCAK BARU terkirim (Rp{peak:.0f}, {gain_from_last:+.1%} dari puncak sebelumnya).")

    # --- Lapis 2 Exit: trailing stop / kunci profit (Prioritas Kronologis) ---
    alerted_at_peak = position.get("alerted_pullback_at_peak") or 0
    ts_level_price = round(peak * (1 - pullback_thresh), 2)
    has_ts_triggered = False
    # Fase FF-2 OOS: trailing stop HANYA aktif bila Peak >= Entry * (1 + TS_ACTIVATION_BUFFER) (+2.0%).
    # Mencegah noise pembukaan (+0.5%..+1.8%) memicu negative trailing stop; penurunan di bawah entry
    # tetap menjadi tanggung jawab Lapis 1 (Hard SL -3.5% / -3.0%).
    if peak >= entry_price * (1.0 + TS_ACTIVATION_BUFFER) and pullback >= pullback_thresh and peak > alerted_at_peak:
        gain_from_entry = (peak - entry_price) / entry_price
        if is_bottom_to_top:
            title = "KUNCI PROFIT (MUNDUR 2.5% DARI PUNCAK)" if gain_from_entry >= 0.03 else "TRAILING STOP"
            msg_header = f"💰 <b>{title}: {label}</b>"
        else:
            msg_header = f"\U0001F534 <b>TRAILING STOP: {label}</b>"

        send_telegram_alert(
            f"{msg_header}\n\n"
            f"Harga mundur <b>{pullback:.1%}</b> dari puncak sejak entry.\n\n"
            f"<b>Entry</b>: {entry_date} @ Rp{entry_price:.0f}\n"
            f"<b>Puncak</b>: {peak_ts.strftime('%d %b %H:%M')} @ Rp{peak:.0f}\n"
            f"<b>Level TS</b>: Rp{ts_level_price:.2f}\n"
            f"<b>Sekarang</b>: {current_ts.strftime('%d %b %H:%M')} @ Rp{current:.0f}\n"
            f"<b>P&amp;L</b>: {unrealized_pct:+.1%} dari entry\n\n"
            f"Posisi otomatis ditutup di Trade Journal pada level Trailing Stop untuk mengunci profit."
        )
        position["alerted_pullback_pct"] = pullback
        position["alerted_pullback_at_peak"] = peak
        print(f"  -> ALERT TRAILING STOP terkirim ({pullback:.1%}, puncak Rp{peak:.0f}, TS Rp{ts_level_price:.2f}).")
        print(f"SYNC_ALERT_CLOSE|{ticker}|{ts_level_price:.2f}|{current_ts.strftime('%Y-%m-%d %H:%M')}|trailing_stop|{strategy}|{entry_date}")
        has_ts_triggered = True

    # --- Lapis 1 Exit: Hard Stop Loss (Hanya jika Trailing Stop belum terpicu di harga lebih tinggi) ---
    min_sl_thresh = entry_price * (0.97 if is_bottom_to_top else 0.965)
    if not (has_ts_triggered and ts_level_price > min_sl_thresh):
        # --- Khusus BOTTOM_TO_TOP: Alert Hard Stop Loss 3.0% ---
        if is_bottom_to_top:
            sl_price = round(entry_price * 0.97, 2)
            if current <= sl_price and not position.get("alerted_sl"):
                send_telegram_alert(
                    f"\U0001F6A8 <b>CUT LOSS (STOP LOSS 3%): {label}</b>\n\n"
                    f"Harga menyentuh batas risiko stop loss 3.0%: <b>Rp{current:.0f}</b> (SL: Rp{sl_price:.0f}).\n\n"
                    f"<b>Entry</b>: {entry_date} @ Rp{entry_price:.0f}\n"
                    f"<b>Kerugian Saat Ini</b>: {unrealized_pct:+.1%}\n\n"
                    f"⚠️ Segera pastikan order Auto Cut Loss di broker tereksekusi untuk mencegah kerugian lebih dalam (anti-minus 5%)!"
                )
                position["alerted_sl"] = True
                print(f"  -> ALERT CUT LOSS 3% terkirim (Harga Rp{current:.0f} <= SL Rp{sl_price:.0f}).")
                print(f"SYNC_ALERT_CLOSE|{ticker}|{sl_price:.2f}|{current_ts.strftime('%Y-%m-%d %H:%M')}|stop_loss|{strategy}|{entry_date}")
        # --- GABUNGAN / MOMENTUM / BOTTOM_REBOUND: Alert Stop Loss Pengaman -3.5% (Golden Compromise) ---
        elif strategy in ("GABUNGAN", "MOMENTUM", "BOTTOM_REBOUND"):
            sl_price = round(entry_price * 0.965, 2)
            if current <= sl_price and not position.get("alerted_sl_initial"):
                send_telegram_alert(
                    f"\U0001F6A8 <b>PERINGATAN CUT LOSS (STOP LOSS -3.5%): {label}</b>\n\n"
                    f"Harga menyentuh batas risiko stop loss -3.5%: <b>Rp{current:.0f}</b> (Level SL: Rp{sl_price:.0f}).\n\n"
                    f"<b>Entry</b>: {entry_date} @ Rp{entry_price:.0f}\n"
                    f"<b>Kerugian Saat Ini</b>: {unrealized_pct:+.1%}\n\n"
                    f"⚠️ Batas toleransi risiko teruji optimal (-3.5%) telah tercapai. "
                    f"Disiplin eksekusi Cut Loss di broker/StockBit untuk membatasi kerugian dan melindungi modal!"
                )
                position["alerted_sl_initial"] = True
                print(f"  -> ALERT CUT LOSS -3.5% terkirim (Harga Rp{current:.0f} <= SL Rp{sl_price:.0f}).")
                print(f"SYNC_ALERT_CLOSE|{ticker}|{sl_price:.2f}|{current_ts.strftime('%Y-%m-%d %H:%M')}|stop_loss|{strategy}|{entry_date}")

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
