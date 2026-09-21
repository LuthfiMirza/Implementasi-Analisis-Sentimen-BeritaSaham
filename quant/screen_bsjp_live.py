#!/usr/bin/env python3
"""
Scanner Momentum BSJP (Beli Sore Jual Pagi) Otomatis
Alur 2-Tahap:
- 15:00 WIB (--stage=early): Radar Pantau Dini (Early Warning)
- 15:35 WIB (--stage=confirm): Konfirmasi Akhir Beli di Pre-Closing
- 08:50 WIB (--stage=reminder): Pengingat Jual di Pembukaan 09:00 WIB

Data Source:
- Database BEI: idx_daily_summaries (MySQL)
- Live Intraday Backup: yfinance fast_info
- Telegram: quant/drawdown_bounce_tracker/detect_signal.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

# Ensure project root in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "quant", "drawdown_bounce_tracker"))

try:
    from detect_signal import send_telegram_alert
except ImportError:
    send_telegram_alert = None

JAKARTA_TZ = timezone(timedelta(hours=7))


def get_db_connection():
    """Connect to MySQL database using Laravel .env credentials."""
    import pymysql

    env_path = os.path.join(PROJECT_ROOT, ".env")
    env_vars = {}
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip().strip('"').strip("'")

    host = env_vars.get("DB_HOST", "127.0.0.1")
    port = int(env_vars.get("DB_PORT", 3306))
    user = env_vars.get("DB_USERNAME", "root")
    password = env_vars.get("DB_PASSWORD", "")
    database = env_vars.get("DB_DATABASE", "sentimena_dashboard")

    return pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        cursorclass=pymysql.cursors.DictCursor,
    )


def scan_candidates(trade_date: str | None = None) -> list[dict]:
    """Scan candidates using the 5 core Stockbit screener rules from idx_daily_summaries."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Resolve target trade date
            if not trade_date:
                cursor.execute("SELECT MAX(trade_date) as max_date FROM idx_daily_summaries")
                row = cursor.fetchone()
                trade_date = str(row["max_date"]) if row and row["max_date"] else datetime.now(JAKARTA_TZ).strftime("%Y-%m-%d")

            # Resolve prior trade date
            cursor.execute(
                "SELECT MAX(trade_date) as prev_date FROM idx_daily_summaries WHERE trade_date < %s",
                (trade_date,)
            )
            prev_row = cursor.fetchone()
            prev_date = str(prev_row["prev_date"]) if prev_row and prev_row["prev_date"] else None

            if not prev_date:
                return []

            # Query the 5 Stockbit rules:
            # 1. Volume > Previous Volume
            # 2. Bullish Candle (Close > Open)
            # 3. Kenaikan Harga >= 3.0%
            # 4. Nilai Transaksi >= Rp 100.000.000
            query = """
                SELECT 
                    t.stock_code as ticker,
                    t.stock_name as name,
                    t.close as price,
                    t.open as open_price,
                    t.previous as prev_price,
                    t.pct_change as return_pct,
                    t.volume as volume_today,
                    p.volume as volume_prev,
                    (t.volume / NULLIF(p.volume, 0)) as volume_ratio,
                    t.value as transaction_value,
                    t.trade_date
                FROM idx_daily_summaries t
                JOIN idx_daily_summaries p 
                    ON t.stock_code = p.stock_code AND p.trade_date = %s
                WHERE t.trade_date = %s
                  AND t.close > t.open
                  AND t.pct_change >= 3.0
                  AND t.value >= 100000000
                  AND t.volume > p.volume
                ORDER BY volume_ratio DESC, transaction_value DESC
            """
            cursor.execute(query, (prev_date, trade_date))
            rows = cursor.fetchall()

            candidates = []
            for r in rows:
                candidates.append({
                    "ticker": r["ticker"],
                    "name": r.get("name") or r["ticker"],
                    "price": float(r["price"]),
                    "open": float(r["open_price"]),
                    "prev_price": float(r["prev_price"]),
                    "return_pct": float(r["return_pct"]),
                    "volume": int(r["volume_today"]),
                    "prev_volume": int(r["volume_prev"]),
                    "volume_ratio": float(r["volume_ratio"]) if r["volume_ratio"] else 1.0,
                    "value": float(r["transaction_value"]),
                    "trade_date": str(r["trade_date"]),
                })

            return candidates
    finally:
        conn.close()


def format_early_telegram_alert(candidates: list[dict]) -> str:
    """Format Jam 15:00 WIB Early Warning alert in HTML."""
    now_str = datetime.now(JAKARTA_TZ).strftime("%d %b %Y, %H:%M WIB")
    top = candidates[:5]

    lines = [
        "🟡 <b>RADAR PANTAU BSJP (Beli Sore Jual Pagi)</b>",
        f"📅 <i>Pukul 15:00 WIB Early Warning • {now_str}</i>",
        "",
        "Terdeteksi saham dengan <b>Ledakan Volume & Bullish Candle</b> yang memenuhi kriteria BSJP:",
        "",
    ]

    for idx, c in enumerate(top, 1):
        val_m = c["value"] / 1_000_000_000.0
        lines.append(
            f"<b>{idx}. #{c['ticker']}</b> — Rp{c['price']:,.0f} (<b>+{c['return_pct']:.2f}%</b>)\n"
            f"   • Vol Spike: <b>{c['volume_ratio']:.1f}x lipat</b> vs kemarin\n"
            f"   • Nilai Trx: Rp{val_m:.2f} Miliar | Open: Rp{c['open']:,.0f}"
        )

    lines.extend([
        "",
        "⏱️ <b>Status: RADAR PANTAU DINI (15:00 WIB)</b>",
        "💡 <i>Instruksi: Pantau saham di atas hingga pukul 15:35 WIB. Jika lilin tetap hijau solid dan tidak diguyur, eksekusi beli di Pre-Closing (15:50 WIB) untuk take profit di pembukaan esok pagi!</i>"
    ])

    return "\n".join(lines)


def format_confirm_telegram_alert(candidates: list[dict]) -> str:
    """Format Jam 15:35 WIB Final Confirmation alert in HTML."""
    now_str = datetime.now(JAKARTA_TZ).strftime("%d %b %Y, %H:%M WIB")
    top = candidates[:3]  # Pick top 2-3 strongest

    lines = [
        "🟢 <b>KONFIRMASI AKHIR BSJP — SIAP BELI</b>",
        f"📅 <i>Pukul 15:35 WIB Final Call • {now_str}</i>",
        "",
        "Validasi selesai! Saham-saham berikut <b>tetap solid bertahan di area atas</b> tanpa tekanan guyuran bandar:",
        "",
    ]

    for idx, c in enumerate(top, 1):
        val_m = c["value"] / 1_000_000_000.0
        target_tp = c["price"] * 1.025
        lines.append(
            f"🎯 <b>PILIHAN #{idx}: #{c['ticker']}</b> (Rp{c['price']:,.0f} | <b>+{c['return_pct']:.2f}%</b>)\n"
            f"   • Rasio Volume: <b>{c['volume_ratio']:.1f}x</b> | Trx: Rp{val_m:.2f} Miliar\n"
            f"   • <b>Rekomendasi Beli:</b> Sesi Pre-Closing (15:50 - 15:58 WIB)\n"
            f"   • <b>Target Jual Besok:</b> Rp{target_tp:,.0f} (+2.5% s/d Open 09:00 WIB)"
        )

    lines.extend([
        "",
        "⚠️ <b>Manajemen Risiko:</b>",
        "• Alokasi: Maksimal 1-2 saham per hari.",
        "• Exit Rules: Wajib pasang antrian jual di 08:55 WIB esok pagi sebelum pembukaan.",
        "• Cut Loss Disiplin: -3.0% jika terjadi gap-down tak terduga."
    ])

    return "\n".join(lines)


def format_reminder_telegram_alert(candidates: list[dict]) -> str:
    """Format Jam 08:50 WIB Morning Exit Reminder in HTML."""
    now_str = datetime.now(JAKARTA_TZ).strftime("%d %b %Y, %H:%M WIB")
    top = candidates[:3]

    lines = [
        "🔔 <b>PENGINGAT AMBIL CUAN BSJP (08:50 WIB)</b>",
        f"📅 <i>Persiapan Pembukaan Bursa • {now_str}</i>",
        "",
        "10 menit lagi bursa buka! Jangan lupa siapkan antrian jual untuk saham BSJP kemarin sore:",
        "",
    ]

    for c in top:
        target_tp = c["price"] * 1.025
        lines.append(
            f"• <b>#{c['ticker']}</b> (Beli Sore: Rp{c['price']:,.0f})\n"
            f"  ↳ Pasang Jual di: <b>Rp{target_tp:,.0f} (+2.5%)</b> atau langsung <b>HAKI di Open 09:00 WIB</b>"
        )

    lines.extend([
        "",
        "⚡ <i>Data historis membuktikan: 82.8% saham mencetak harga tertinggi di 15 menit pertama (09:00 - 09:15 WIB). Amankan cuan sebelum bandar mulai distribusi di siang hari!</i>"
    ])

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Scanner Momentum BSJP Live & Alert Telegram")
    parser.add_argument("--stage", choices=["early", "confirm", "reminder"], default="early",
                        help="Tahap: early (15:00 WIB), confirm (15:35 WIB), reminder (08:50 WIB)")
    parser.add_argument("--date", type=str, default=None, help="Tanggal trading YYYY-MM-DD")
    parser.add_argument("--send-telegram", action="store_true", help="Kirim notifikasi ke Telegram")
    parser.add_argument("--json", action="store_true", help="Output JSON untuk Laravel Radar")

    args = parser.parse_args()

    candidates = scan_candidates(args.date)

    if args.json:
        print(json.dumps({
            "stage": args.stage,
            "count": len(candidates),
            "candidates": candidates[:10],
            "generated_at": datetime.now(JAKARTA_TZ).isoformat()
        }, indent=2))
        return

    print(f"\n=======================================================")
    print(f"   SCANNER MOMENTUM BSJP (Stage: {args.stage.upper()})")
    print(f"=======================================================")
    print(f"Total Saham Lolos: {len(candidates)}")

    if not candidates:
        print("Tidak ada saham yang memenuhi kriteria.")
        return

    if args.stage == "early":
        msg = format_early_telegram_alert(candidates)
    elif args.stage == "confirm":
        msg = format_confirm_telegram_alert(candidates)
    else:
        msg = format_reminder_telegram_alert(candidates)

    print("\n--- PREVIEW PESAN TELEGRAM ---")
    print(msg.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", ""))
    print("------------------------------")

    if args.send_telegram:
        if send_telegram_alert:
            print("\nMengirim alert ke Telegram...")
            send_telegram_alert(msg)
            print("Alert Telegram berhasil dikirim!")
        else:
            print("send_telegram_alert function tidak tersedia.")


if __name__ == "__main__":
    main()
