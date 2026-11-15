#!/bin/bash
# ============================================================
# WATCHDOG SENTIMENA — Self-Healing Daemon Monitor
# Mengecek 5 layanan setiap kali dipanggil, dan menyalakan kembali
# otomatis jika ada layanan yang mati/terhenti.
# ============================================================

BASE_DIR="/Applications/XAMPP/xamppfiles/htdocs/Implementasi AnalisisSentimenBerita"
LARAVEL_DIR="$BASE_DIR/laravel-app"
LOG_DIR="/tmp/sentimena_logs"
mkdir -p "$LOG_DIR"
TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")

STATUS_MODE=0
if [ "$1" == "--status" ]; then
    STATUS_MODE=1
fi

REVIVED=0

# 1. Cek MySQL
MYSQL_STATUS="DOWN"
if /Applications/XAMPP/xamppfiles/bin/mysqladmin --socket=/Applications/XAMPP/xamppfiles/var/mysql/mysql.sock ping &>/dev/null; then
    MYSQL_STATUS="OK"
else
    if [ $STATUS_MODE -eq 0 ]; then
        echo "[$TIMESTAMP] ⚠️ MySQL mati. Menghidupkan kembali..." >> "$LOG_DIR/watchdog.log"
        /Applications/XAMPP/xamppfiles/bin/mysql.server start 2>&1 >> "$LOG_DIR/watchdog.log"
        sleep 2
        if /Applications/XAMPP/xamppfiles/bin/mysqladmin --socket=/Applications/XAMPP/xamppfiles/var/mysql/mysql.sock ping &>/dev/null; then
            MYSQL_STATUS="REVIVED"
            REVIVED=$((REVIVED + 1))
        fi
    fi
fi

# 2. Cek Sentiment API (8002)
SENTIMENT_STATUS="DOWN"
if nc -z 127.0.0.1 8002 2>/dev/null; then
    SENTIMENT_STATUS="OK"
else
    if [ $STATUS_MODE -eq 0 ]; then
        echo "[$TIMESTAMP] ⚠️ Sentiment API (8002) mati. Menghidupkan kembali..." >> "$LOG_DIR/watchdog.log"
        cd "$LARAVEL_DIR"
        nohup "$LARAVEL_DIR/quant/.venv-sentiment/bin/python3" -m uvicorn quant.sentiment_api:app --host 127.0.0.1 --port 8002 < /dev/null > "$LOG_DIR/sentiment_api.log" 2>&1 &
        disown $! 2>/dev/null || true
        SENTIMENT_STATUS="REVIVED"
        REVIVED=$((REVIVED + 1))
    fi
fi

# 3. Cek Prediction API (8001)
PRED_STATUS="DOWN"
if nc -z 127.0.0.1 8001 2>/dev/null; then
    PRED_STATUS="OK"
else
    if [ $STATUS_MODE -eq 0 ]; then
        echo "[$TIMESTAMP] ⚠️ Prediction API (8001) mati. Menghidupkan kembali..." >> "$LOG_DIR/watchdog.log"
        cd "$LARAVEL_DIR"
        nohup python3 -m uvicorn quant.prediction_api:app --host 127.0.0.1 --port 8001 < /dev/null > "$LOG_DIR/prediction_api.log" 2>&1 &
        disown $! 2>/dev/null || true
        PRED_STATUS="REVIVED"
        REVIVED=$((REVIVED + 1))
    fi
fi

# 4. Cek Laravel Web Server (8000)
LARAVEL_STATUS="DOWN"
if nc -z 127.0.0.1 8000 2>/dev/null; then
    LARAVEL_STATUS="OK"
else
    if [ $STATUS_MODE -eq 0 ]; then
        echo "[$TIMESTAMP] ⚠️ Laravel Web Server (8000) mati. Menghidupkan kembali..." >> "$LOG_DIR/watchdog.log"
        cd "$LARAVEL_DIR/public"
        PHP_CLI_SERVER_WORKERS=4 nohup php -S 127.0.0.1:8000 ../vendor/laravel/framework/src/Illuminate/Foundation/resources/server.php > "$LOG_DIR/laravel.log" 2>&1 &
        disown $! 2>/dev/null || true
        cd "$LARAVEL_DIR"
        LARAVEL_STATUS="REVIVED"
        REVIVED=$((REVIVED + 1))
    fi
fi

# 5. Cek Scheduler (php artisan schedule:work)
SCHEDULER_STATUS="DOWN"
if pgrep -f "artisan schedule:work" > /dev/null; then
    SCHEDULER_STATUS="OK"
else
    if [ $STATUS_MODE -eq 0 ]; then
        echo "[$TIMESTAMP] ⚠️ Scheduler mati. Menghidupkan kembali..." >> "$LOG_DIR/watchdog.log"
        cd "$LARAVEL_DIR"
        nohup php artisan schedule:work < /dev/null > "$LOG_DIR/scheduler.log" 2>&1 &
        disown $! 2>/dev/null || true
        SCHEDULER_STATUS="REVIVED"
        REVIVED=$((REVIVED + 1))
    fi
fi

# Output / Log Heartbeat
if [ $STATUS_MODE -eq 1 ]; then
    echo "============================================================"
    echo "🛡️ SENTIMENA SERVICE WATCHDOG STATUS ($TIMESTAMP)"
    echo "   1. MySQL Database : $MYSQL_STATUS"
    echo "   2. Sentiment API  : $SENTIMENT_STATUS (port 8002)"
    echo "   3. Prediction API : $PRED_STATUS (port 8001)"
    echo "   4. Laravel Web    : $LARAVEL_STATUS (port 8000)"
    echo "   5. Cron Scheduler : $SCHEDULER_STATUS"
    echo "============================================================"
else
    echo "[$TIMESTAMP] Heartbeat: MySQL=$MYSQL_STATUS, Sentiment=$SENTIMENT_STATUS, Pred=$PRED_STATUS, Web=$LARAVEL_STATUS, Cron=$SCHEDULER_STATUS (Revived: $REVIVED)" >> "$LOG_DIR/watchdog.log"
    # Batasi ukuran log watchdog ke 5000 baris agar tidak membengkak
    if [ -f "$LOG_DIR/watchdog.log" ]; then
        tail -n 5000 "$LOG_DIR/watchdog.log" > "$LOG_DIR/watchdog.log.tmp" && mv "$LOG_DIR/watchdog.log.tmp" "$LOG_DIR/watchdog.log"
    fi
fi
