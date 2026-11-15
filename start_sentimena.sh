#!/bin/bash
# ============================================================
# START SENTIMENA — jalankan MySQL + Laravel sekaligus
# Cara pakai: double-klik file ini di Finder, atau
#             bash start_sentimena.sh di terminal
# ============================================================

LARAVEL_DIR="/Applications/XAMPP/xamppfiles/htdocs/Implementasi AnalisisSentimenBerita/laravel-app"
LOG_DIR="/tmp/sentimena_logs"
mkdir -p "$LOG_DIR"

echo "🔵 [1/5] Cek / Start MySQL (XAMPP)..."
if /Applications/XAMPP/xamppfiles/bin/mysqladmin --socket=/Applications/XAMPP/xamppfiles/var/mysql/mysql.sock ping &>/dev/null; then
    echo "✅ MySQL: SUDAH HIDUP"
else
    /Applications/XAMPP/xamppfiles/bin/mysql.server start 2>&1
    sleep 2
    if /Applications/XAMPP/xamppfiles/bin/mysqladmin --socket=/Applications/XAMPP/xamppfiles/var/mysql/mysql.sock ping &>/dev/null; then
        echo "✅ MySQL: HIDUP"
    else
        echo "❌ MySQL gagal nyala. Cek log: /Applications/XAMPP/xamppfiles/var/mysql/*.err"
        exit 1
    fi
fi

echo ""
echo "🔵 [2/5] Start Sentiment API (port 8002)..."
cd "$LARAVEL_DIR"
if nc -z 127.0.0.1 8002 2>/dev/null; then
    echo "✅ Sentiment API: SUDAH JALAN (port 8002)"
else
    nohup "$LARAVEL_DIR/quant/.venv-sentiment/bin/python3" -m uvicorn quant.sentiment_api:app --host 127.0.0.1 --port 8002 < /dev/null > "$LOG_DIR/sentiment_api.log" 2>&1 &
    SENTIMENT_PID=$!
    disown $SENTIMENT_PID 2>/dev/null || true
    echo "🚀 Sentiment API started (PID $SENTIMENT_PID)"
fi

echo ""
echo "🔵 [3/5] Start Prediction API (port 8001)..."
cd "$LARAVEL_DIR"
if nc -z 127.0.0.1 8001 2>/dev/null; then
    echo "✅ Prediction API: SUDAH JALAN (port 8001)"
else
    nohup python3 -m uvicorn quant.prediction_api:app --host 127.0.0.1 --port 8001 < /dev/null > "$LOG_DIR/prediction_api.log" 2>&1 &
    PRED_PID=$!
    disown $PRED_PID 2>/dev/null || true
    echo "🚀 Prediction API started (PID $PRED_PID)"
fi

echo ""
echo "🔵 [4/5] Start Laravel Web Server (port 8000)..."
cd "$LARAVEL_DIR"
if nc -z 127.0.0.1 8000 2>/dev/null; then
    echo "✅ Laravel: SUDAH JALAN di http://127.0.0.1:8000"
else
    pkill -f "127.0.0.1:8000" 2>/dev/null || true
    pkill -f "php artisan serve" 2>/dev/null || true
    cd "$LARAVEL_DIR/public"
    PHP_CLI_SERVER_WORKERS=4 nohup php -S 127.0.0.1:8000 ../vendor/laravel/framework/src/Illuminate/Foundation/resources/server.php > "$LOG_DIR/laravel.log" 2>&1 &
    LARAVEL_PID=$!
    disown $LARAVEL_PID 2>/dev/null || true
    cd "$LARAVEL_DIR"
    sleep 3
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:8000/login)
    if [ "$HTTP_CODE" = "200" ]; then
        echo "✅ Laravel: HIDUP (PID $LARAVEL_PID) → http://127.0.0.1:8000"
    else
        echo "⚠️  Laravel belum respond (HTTP $HTTP_CODE) — cek: tail $LOG_DIR/laravel.log"
    fi
fi

echo ""
echo "🔵 [5/5] Start Laravel Scheduler (Cron Otomatis)..."
cd "$LARAVEL_DIR"
pkill -f "php artisan schedule:work" 2>/dev/null || true
nohup php artisan schedule:work < /dev/null > "$LOG_DIR/scheduler.log" 2>&1 &
SCHEDULER_PID=$!
disown $SCHEDULER_PID 2>/dev/null || true
echo "✅ Scheduler: HIDUP (PID $SCHEDULER_PID) — Cron aktif"

disown -a 2>/dev/null || true

echo ""
echo "============================================================"
echo "🎉 SEMUA SERVICE AKTIF & SIAP DIAKSES:"
echo "   🌐 Web Dashboard   : http://127.0.0.1:8000"
echo "   📊 Halaman Radar   : http://127.0.0.1:8000/trades/radar-log"
echo "   📈 BSJP Tracker    : http://127.0.0.1:8000/trades/bsjp-tracker"
echo "   📰 Halaman Berita  : http://127.0.0.1:8000/news"
echo "   🤖 Sentiment Docs  : http://127.0.0.1:8002/docs"
echo "   🧠 Prediction Docs : http://127.0.0.1:8001/docs"
echo "============================================================"
echo "📝 Log Files:"
echo "   Laravel       : tail -f $LOG_DIR/laravel.log"
echo "   Sentiment API : tail -f $LOG_DIR/sentiment_api.log"
echo "   Prediction API: tail -f $LOG_DIR/prediction_api.log"
echo "   Scheduler     : tail -f $LOG_DIR/scheduler.log"
echo "============================================================"
echo "💡 Untuk mematikan semua service: bash stop_sentimena.sh"
