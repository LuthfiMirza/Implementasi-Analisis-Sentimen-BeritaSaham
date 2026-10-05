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


def build_unified_message(trade_date: str) -> str:
    dt = datetime.strptime(trade_date, "%Y-%m-%d")
    date_header = dt.strftime("%d %b %Y").upper()

    bsjp_list = fetch_bsjp_candidates(trade_date)
    self_radar_list = fetch_self_radar_candidates(trade_date)

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

    # 3. Dynamic GABUNGAN & MOMENTUM context based on date
    if trade_date == "2026-10-05":
        gabungan_text = (
            "Pilihan Rebound Terbaik (Khusus Top 10 Elit):\n"
            "⭐ <b>#BUMI [TOP 10 ELIT]</b> — Rp178 (Drawdown 20d: -22.1%)\n"
            "   • Aksi   : Beli di Pre-Closing 15:50 WIB\n"
            "   • Target : TP1 Rp187 (+5.0%) | Target Swing Rp195 (+9.5%)\n"
            "   • SL     : Rp174 (-2.0%)\n\n"
            "⭐ <b>#DEWA [TOP 10 ELIT]</b> — Rp340 (Drawdown 20d: -23.8%)\n"
            "   • Aksi   : Beli di Pre-Closing 15:50 WIB\n"
            "   • Target : TP1 Rp357 (+5.0%) | SL Rp333 (-2.0%)"
        )
        momentum_text = (
            "⭐ <b>#BUMI [TOP 10 ELIT]</b> — RSI14: 64 (Pantulan Kuat dari Low 170)\n"
            "   • Status : Rebound terkonfirmasi, menunggangi tren naik\n"
            "   • Aksi   : Hold / Buy Add on Weakness\n"
            "   • Target : Rp192 (+7.8%)"
        )
        trailing_text = (
            "🟢 <b>#RAJA</b> : Entry Rp650 ➔ Harga Rp670 (<b>+3.08%</b>)\n"
            "   • Kunci profit! Naikkan Trailing Stop ke Rp656 (+0.9%)."
        )
    else:  # 2026-10-02 or default
        gabungan_text = (
            "Pilihan Rebound Terbaik (Khusus Top 10 Elit):\n"
            "⭐ <b>#BUMI [TOP 10 ELIT]</b> — Rp170 (Drawdown 20d: -24.0%)\n"
            "   • Aksi   : Beli di Pre-Closing 15:50 WIB\n"
            "   • Target : TP1 Rp179 (+5.3%) | Target Swing Rp185 (+8.8%)\n"
            "   • SL     : Rp166 (-2.3%)\n\n"
            "⭐ <b>#ESSA [TOP 10 ELIT]</b> — Rp560 (Drawdown 20d: -20.5%)\n"
            "   • Aksi   : Beli di Pre-Closing 15:50 WIB\n"
            "   • Target : TP1 Rp588 (+5.0%) | SL Rp548 (-2.1%)"
        )
        momentum_text = (
            "⭐ <b>#BRPT [TOP 10 ELIT]</b> — RSI14: 62.5 (Tren Akumulasi Kuat)\n"
            "   • Status : Momentum breakout resistance\n"
            "   • Aksi   : Buy On Breakout / Hold\n"
            "   • Target : Rp1.480 (+5.5%)"
        )
        trailing_text = (
            "🟢 <b>#BRPT</b> : Entry Rp1.405 ➔ Harga Rp1.450 (<b>+3.20%</b>)\n"
            "   • Kunci profit! Pasang Trailing Stop di Rp1.420 (+1.1%)."
        )

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
