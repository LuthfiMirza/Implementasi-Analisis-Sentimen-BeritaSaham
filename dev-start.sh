#!/bin/bash
#
# Nyalakan semua service dev proyek dalam satu perintah.
#
#   ./dev-start.sh
#
# Yang dijalankan:
#   1. MySQL            (dicek; distart kalau mati)
#   2. Sentiment API    :8002  -> background, log ke storage/logs/sentiment-api.log
#   3. Prediction API   :8001  -> background, log ke storage/logs/prediction-api.log
#   4. Web Laravel      :8000  -> FOREGROUND (Ctrl+C untuk berhenti)
#
# Scheduler (idx:fetch-daily-summary dll) TIDAK diurus di sini -- itu sudah jalan
# lewat cron per-menit. Vite (npm run dev) juga tidak -- cuma perlu kalau lagi edit CSS/JS.
#
# Untuk mematikan API background: ./dev-stop.sh

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

MYSQL_BIN="/Applications/XAMPP/xamppfiles/bin/mysql.server"
PID_DIR="storage/app/dev-pids"
LOG_DIR="storage/logs"
mkdir -p "$PID_DIR" "$LOG_DIR"

say() { printf '\033[1;36m▶ %s\033[0m\n' "$1"; }
ok()  { printf '\033[1;32m  ✓ %s\033[0m\n' "$1"; }
err() { printf '\033[1;31m  ✗ %s\033[0m\n' "$1"; }

# 1. MySQL --------------------------------------------------------------------
say "MySQL (:3306)"
if nc -z 127.0.0.1 3306 2>/dev/null; then
    ok "sudah jalan"
elif [ -x "$MYSQL_BIN" ]; then
    "$MYSQL_BIN" start >/dev/null 2>&1 && ok "distart" || err "gagal start -- nyalakan manual lewat XAMPP"
else
    err "mysql.server tidak ketemu -- nyalakan MySQL manual (XAMPP)"
fi

# helper: start a background service if its port is free ---------------------
start_bg() {
    local name="$1" port="$2" script="$3" log="$4"
    say "$name (:$port)"
    if nc -z 127.0.0.1 "$port" 2>/dev/null; then
        ok "sudah jalan"
        return
    fi
    nohup bash "$script" >"$log" 2>&1 &
    echo $! > "$PID_DIR/$name.pid"
    sleep 2
    if nc -z 127.0.0.1 "$port" 2>/dev/null; then
        ok "distart (pid $(cat "$PID_DIR/$name.pid"), log: $log)"
    else
        ok "distart, masih warming up (cek $log kalau tab-nya error)"
    fi
}

# 2 & 3. Python APIs --------------------------------------------------------
start_bg "sentiment-api"  8002 "start_sentiment_api.sh"  "$LOG_DIR/sentiment-api.log"
start_bg "prediction-api" 8001 "start_prediction_api.sh" "$LOG_DIR/prediction-api.log"

# 4. Web (foreground) ------------------------------------------------------
say "Web Laravel (:8000)"
if nc -z 127.0.0.1 8000 2>/dev/null; then
    ok "sudah jalan di http://127.0.0.1:8000 -- tidak perlu start lagi"
    echo
    echo "Semua siap. API background dimatikan dengan: ./dev-stop.sh"
    exit 0
fi
echo "  (Ctrl+C untuk berhenti)"
echo
exec php artisan serve
