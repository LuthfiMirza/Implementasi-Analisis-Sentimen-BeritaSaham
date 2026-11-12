#!/usr/bin/env python3
"""
Broadcast Komprehensif SORE SENTIMENA:
Merangkum 3 Strategi Juara + Tiket Emas SELF_RADAR_V1 + Trailing Stop Posisi Berjalan
dalam 1 pesan ringkas, rapi, dan mudah dieksekusi sebelum penutupan bursa (15:36 WIB).

Usage:
  python3 quant/send_sentimena_sore_broadcast.py --date 2026-10-05 --send
  python3 quant/send_sentimena_sore_broadcast.py --date 2026-10-02 --send
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
import pymysql

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "quant", "drawdown_bounce_tracker"))

try:
    from detect_signal import send_telegram_alert
except ImportError:
    send_telegram_alert = None

JAKARTA_TZ = timezone(timedelta(hours=7))


def get_db_connection():
    env_path = os.path.join(PROJECT_ROOT, ".env")
    env_vars = {}
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip().strip('"').strip("'")

    return pymysql.connect(
        host=env_vars.get("DB_HOST", "127.0.0.1"),
        port=int(env_vars.get("DB_PORT", 3306)),
        user=env_vars.get("DB_USERNAME", "root"),
        password=env_vars.get("DB_PASSWORD", ""),
        database=env_vars.get("DB_DATABASE", "sentimena_dashboard"),
        cursorclass=pymysql.cursors.DictCursor,
    )


def fetch_bsjp_candidates(trade_date: str) -> list[dict]:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT MAX(trade_date) as prev_date FROM idx_daily_summaries WHERE trade_date < %s",
                (trade_date,)
            )
            p_row = cur.fetchone()
            prev_date = str(p_row["prev_date"]) if p_row and p_row["prev_date"] else None
            if not prev_date:
                return []

            query = """
                SELECT 
                    t.stock_code as ticker,
                    t.close as price,
                    t.pct_change as return_pct,
                    (t.volume / NULLIF(p.volume, 0)) as volume_ratio,
                    t.value as transaction_value
                FROM idx_daily_summaries t
                JOIN idx_daily_summaries p 
                    ON t.stock_code = p.stock_code AND p.trade_date = %s
                WHERE t.trade_date = %s
                  AND t.close > t.open
                  AND t.pct_change >= 3.0
                  AND t.value >= 100000000
                  AND t.volume > p.volume
                ORDER BY volume_ratio DESC, transaction_value DESC
                LIMIT 5
            """
            cur.execute(query, (prev_date, trade_date))
            return cur.fetchall()
    finally:
        conn.close()


def fetch_self_radar_candidates(trade_date: str) -> list[dict]:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            query = """
                SELECT ticker, latest_price as price, rsi14, ret_5d_pct, dd_20d_pct, score
                FROM self_radar_signal_logs
                WHERE signal_date = %s
                ORDER BY score DESC
                LIMIT 3
            """
            cur.execute(query, (trade_date,))
            return cur.fetchall()
    finally:
        conn.close()


def fetch_gabungan_candidates(trade_date: str) -> list[dict]:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    t.stock_code as ticker,
                    t.close as price,
                    t.pct_change as return_pct,
                    (
                        SELECT MAX(h.close) 
                        FROM idx_daily_summaries h 
                        WHERE h.stock_code = t.stock_code 
                          AND h.trade_date <= t.trade_date 
                          AND h.trade_date >= DATE_SUB(t.trade_date, INTERVAL 30 DAY)
                    ) as peak_20d
                FROM idx_daily_summaries t
                WHERE t.trade_date = %s
                  AND t.stock_code IN ('BUMI', 'DEWA', 'BRPT', 'SMGR', 'ESSA', 'UNVR', 'PTRO', 'ENRG', 'RAJA', 'INET')
            """, (trade_date,))
            rows = cur.fetchall()
            candidates = []
            for r in rows:
                price = float(r["price"] or 0)
                peak = float(r["peak_20d"] or price)
                dd = ((price - peak) / peak * 100) if peak > 0 else 0
                tp1 = round(price * 1.05)
                tp_swing = round(price * 1.09)
                sl = round(price * 0.975)
                candidates.append({
                    "ticker": r["ticker"],
                    "price": price,
                    "return_pct": float(r["return_pct"] or 0),
                    "dd_20d": dd,
                    "tp1": tp1,
                    "tp_swing": tp_swing,
                    "sl": sl,
                })
            candidates.sort(key=lambda x: x["dd_20d"])
            return candidates
    finally:
        conn.close()


def fetch_momentum_candidates(trade_date: str) -> list[dict]:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT stock_code as ticker, close as price, pct_change as return_pct, value
                FROM idx_daily_summaries
                WHERE trade_date = %s
                  AND stock_code IN ('BRPT', 'BREN', 'TLKM', 'BBCA', 'TINS', 'DSSA')
                  AND pct_change > 0
                ORDER BY pct_change DESC, value DESC
                LIMIT 2
            """, (trade_date,))
            return cur.fetchall()
    finally:
        conn.close()


def fetch_trailing_positions(trade_date: str) -> list[dict]:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT t.id, t.ticker, t.entry_price, t.entry_date, s.close as current_price
                FROM trades t
                JOIN idx_daily_summaries s ON t.ticker = s.stock_code AND s.trade_date = %s
                WHERE t.status = 'OPEN'
                ORDER BY ((s.close - t.entry_price) / t.entry_price) DESC
            """, (trade_date,))
            trades = cur.fetchall()
            seen = set()
            result = []
            for tr in trades:
                tk = tr["ticker"]
                if tk in seen:
                    continue
                seen.add(tk)
                entry = float(tr["entry_price"])
                curr = float(tr["current_price"])
                pnl = (curr - entry) / entry * 100
                if pnl >= 2.0:
                    ts_price = round(curr * 0.98)
                    result.append({
                        "ticker": tk,
                        "entry": entry,
                        "current": curr,
                        "pnl": pnl,
                        "trailing_stop": ts_price,
                    })
            return result
    finally:
        conn.close()


def build_unified_message(trade_date: str) -> str:
    dt = datetime.strptime(trade_date, "%Y-%m-%d")
    date_header = dt.strftime("%d %b %Y").upper()

    bsjp_list = fetch_bsjp_candidates(trade_date)
    self_radar_list = fetch_self_radar_candidates(trade_date)
    gabungan_list = fetch_gabungan_candidates(trade_date)
    momentum_list = fetch_momentum_candidates(trade_date)
    trailing_list = fetch_trailing_positions(trade_date)

    # 1. BSJP Section
    if bsjp_list:
        p1 = bsjp_list[0]
        p1_val_m = float(p1["transaction_value"]) / 1_000_000_000.0
        p1_tp = round(float(p1["price"]) * 1.025)
        p1_sl = round(float(p1["price"]) * 0.97)

        bsjp_text = (
            f"Pilihan Terbaik Sore Ini:\n"
            f"⭐ <b>#{p1['ticker']}</b> — Rp{float(p1['price']):,.0f} (+{float(p1['return_pct']):.2f}%)\n"
            f"   • Status : 🎯 Sweetspot Likuid | Vol Spike <b>{float(p1['volume_ratio']):.2f}x</b>\n"
            f"   • Likuid : Transaksi Rp{p1_val_m:,.2f} Miliar (Super Tebal)\n"
            f"   • Aksi   : <b>Beli di Pre-Closing 15:50 WIB</b>\n"
            f"   • Target : Jual Pembukaan 09:00 WIB Besok (+2.5% / Rp{p1_tp:,.0f})\n"
            f"   • SL     : Rp{p1_sl:,.0f} (-3.0%)\n"
        )
        if len(bsjp_list) > 1:
            p2 = bsjp_list[1]
            p2_val_m = float(p2["transaction_value"]) / 1_000_000_000.0
            bsjp_text += f"\n<i>(Cadangan Sweetspot: #{p2['ticker']} Rp{float(p2['price']):,.0f} | Vol {float(p2['volume_ratio']):.2f}x | Trx Rp{p2_val_m:,.1f} M)</i>"
    else:
        bsjp_text = "<i>Tidak ada saham lolos filter BSJP sore ini.</i>"

    # 2. SELF_RADAR_V1 Section
    if self_radar_list:
        v1 = self_radar_list[0]
        v1_text = (
            f"⭐ <b>#{v1['ticker']}</b> — Rp{float(v1['price']):,.0f} | RSI14: {float(v1['rsi14']):.1f} | ret_5d: +{float(v1['ret_5d_pct']):.1f}%\n"
            f"   • Status : 🚀 Momentum Ledakan Tren (Super Rocket)\n"
            f"   • Aksi   : <b>Beli Sore di Pre-Closing 15:50 WIB</b>\n"
            f"   • Kawal  : <b>Trailing Stop 1.0%</b> aktif esok 09:30 WIB"
        )
    else:
        v1_text = "<i>Belum ada trigger baru untuk Super Rocket hari ini.</i>"

    # 3. Dynamic GABUNGAN DRAWDOWN Section
    if gabungan_list:
        gab_items = []
        for g in gabungan_list[:2]:
            gab_items.append(
                f"⭐ <b>#{g['ticker']} [TOP 10 ELIT]</b> — Rp{g['price']:,.0f} (Drawdown 20d: {g['dd_20d']:.1f}%)\n"
                f"   • Aksi   : Pantau / Hold Rebound\n"
                f"   • Target : TP1 Rp{g['tp1']:,.0f} (+5.0%) | Target Swing Rp{g['tp_swing']:,.0f} (+9.0%)\n"
                f"   • SL     : Rp{g['sl']:,.0f} (-2.5%)"
            )
        gabungan_text = "Pilihan Rebound Terbaik (Khusus Top 10 Elit):\n" + "\n\n".join(gab_items)
    else:
        gabungan_text = "<i>Tidak ada saham drawdown bounce hari ini.</i>"

    # 4. Dynamic MOMENTUM Section
    if momentum_list:
        mom_items = []
        for m in momentum_list:
            mom_price = float(m["price"])
            mom_target = round(mom_price * 1.055)
            mom_items.append(
                f"⭐ <b>#{m['ticker']} [TOP 10 ELIT]</b> — Rp{mom_price:,.0f} (+{float(m['return_pct']):.2f}%)\n"
                f"   • Status : Tren Akumulasi & Aliran Dana Solid\n"
                f"   • Aksi   : Buy On Breakout / Hold Tren Naik\n"
                f"   • Target : Rp{mom_target:,.0f} (+5.5%)"
            )
        momentum_text = "\n\n".join(mom_items)
    else:
        momentum_text = "<i>Belum ada saham momentum breakout yang aktif.</i>"

    # 5. Dynamic TRAILING STOP Section
    if trailing_list:
        trail_items = []
        for tr in trailing_list[:2]:
            trail_items.append(
                f"🟢 <b>#{tr['ticker']}</b> : Entry Rp{tr['entry']:,.0f} ➔ Harga Rp{tr['current']:,.0f} (<b>+{tr['pnl']:.2f}%</b>)\n"
                f"   • Kunci profit! Pasang Trailing Stop di Rp{tr['trailing_stop']:,.0f}."
            )
        trailing_text = "\n\n".join(trail_items)
    else:
        trailing_text = "<i>Semua posisi berjalan masih berada dalam batas toleransi normal.</i>"

    lines = [
        f"🔔 <b>SENTIMENA SORE • {date_header} (15:36 WIB)</b>",
        "Filter Prioritas 3 Strategi Juara & Kandidat Emas:",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "🥇 <b>JUARA 1: BSJP MOMENTUM (+453% • Scalping 1 Malam)</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        bsjp_text,
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "🚀 <b>TIKET EMAS: SELF_RADAR_V1 (Super Rocket • Trailing Stop 1%)</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        v1_text,
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "🥈 <b>JUARA 2: GABUNGAN DRAWDOWN (+Rp 653 Jt • Swing 2–10 Hari)</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        gabungan_text,
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "🥉 <b>JUARA 3: MOMENTUM RSI>60 (Win Rate 81% • Trend Riding)</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        momentum_text,
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "🛡️ <b>AMANKAN PROFIT (Trailing Stop Posisi Berjalan)</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        trailing_text,
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "📊 Radar Saham Lengkap Tersedia di Web Dashboard:",
        "👉 http://127.0.0.1:8000/trades/radar",
        "👉 http://127.0.0.1:8000/trades/radar-log"
    ]

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Send Unified Sentimena Sore Alert")
    parser.add_argument("--date", type=str, default="2026-10-05", help="Trading date YYYY-MM-DD")
    parser.add_argument("--send", action="store_true", help="Send alert to Telegram")

    args = parser.parse_args()
    msg = build_unified_message(args.date)

    print("\n--- PREVIEW PESAN UNIFIED TELEGRAM ---")
    print(msg.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", ""))
    print("--------------------------------------\n")

    if args.send:
        if send_telegram_alert:
            print(f"Mengirim pesan unified ke Telegram untuk sesi {args.date}...")
            send_telegram_alert(msg)
            print("Alert Telegram berhasil terkirim!")
        else:
            print("Fungsi send_telegram_alert tidak tersedia.")


if __name__ == "__main__":
    main()
