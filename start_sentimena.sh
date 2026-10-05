#!/bin/bash
# ============================================================
# START SENTIMENA — jalankan MySQL + Laravel sekaligus
# Cara pakai: double-klik file ini di Finder, atau
#             bash start_sentimena.sh di terminal
# ============================================================

LARAVEL_DIR="/Applications/XAMPP/xamppfiles/htdocs/Implementasi AnalisisSentimenBerita/laravel-app"
LOG_DIR="/tmp/sentimena_logs"
mkdir -p "$LOG_DIR"

echo "🔵 [1/3] Start MySQL (XAMPP)..."
/Applications/XAMPP/xamppfiles/bin/mysql.server start 2>&1
sleep 2

# Cek MySQL benar-benar hidup
if /Applications/XAMPP/xamppfiles/bin/mysqladmin --socket=/Applications/XAMPP/xamppfiles/var/mysql/mysql.sock ping &>/dev/null; then
    echo "✅ MySQL: HIDUP"
else
    echo "❌ MySQL gagal nyala. Cek log: /Applications/XAMPP/xamppfiles/var/mysql/*.err"
    exit 1
fi

echo ""
echo "🔵 [2/3] Start Laravel (port 8000)..."
cd "$LARAVEL_DIR"
nohup php artisan serve --host=127.0.0.1 --port=8000 > "$LOG_DIR/laravel.log" 2>&1 &
LARAVEL_PID=$!
sleep 3

# Cek Laravel jalan
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:8000/login)
if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ Laravel: HIDUP (PID $LARAVEL_PID) → http://127.0.0.1:8000"
else
    echo "⚠️  Laravel belum respond (HTTP $HTTP_CODE) — cek: tail $LOG_DIR/laravel.log"
fi

echo ""
echo "🔵 [3/4] Start Laravel Scheduler (Cron Otomatis)..."
cd "$LARAVEL_DIR"
pkill -f "php artisan schedule:work" 2>/dev/null || true
nohup php artisan schedule:work > "$LOG_DIR/scheduler.log" 2>&1 &
SCHEDULER_PID=$!
echo "✅ Scheduler: HIDUP (PID $SCHEDULER_PID) — Cron jam 15:36 WIB aktif"

echo ""
echo "🔵 [4/4] Web Dashboard siap dikunjungi:"
echo "   → http://127.0.0.1:8000/trades/radar-log"
echo "   → http://127.0.0.1:8000/trades/bsjp-tracker"
echo ""
echo "📝 Log Laravel: $LOG_DIR/laravel.log"
echo "📝 Log Scheduler: $LOG_DIR/scheduler.log"
echo "   Untuk matikan: bash stop_sentimena.sh"
echo ""
echo "✅ SELESAI — semua service jalan & Cron aktif!"
