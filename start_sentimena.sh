#!/bin/bash
# start_sentimena.sh — Auto-start semua service Sentimena saat Mac nyala
# 
# Cara install (sekali saja):
#   chmod +x start_sentimena.sh
#   
# Cara pakai manual:
#   ./start_sentimena.sh
#
# Untuk auto-start saat login Mac, tambahkan di System Settings > Login Items

set -e

LARAVEL_DIR="/Applications/XAMPP/xamppfiles/htdocs/Implementasi AnalisisSentimenBerita/laravel-app"
LOG_DIR="$LARAVEL_DIR/storage/logs"
XAMPP_BIN="/Applications/XAMPP/xamppfiles/bin"

echo "🚀 Sentimena — Starting all services..."
echo "⏰ $(date '+%Y-%m-%d %H:%M:%S')"

# ── 1. MySQL ──────────────────────────────────────────────────────────────────
echo ""
echo "▶ [1/4] MySQL..."
if $XAMPP_BIN/mysqladmin --socket=/Applications/XAMPP/xamppfiles/var/mysql/mysql.sock ping &>/dev/null; then
    echo "  ✅ MySQL sudah jalan"
else
    /Applications/XAMPP/xamppfiles/sbin/mysqld_safe \
        --defaults-file=/Applications/XAMPP/xamppfiles/etc/my.cnf \
        --socket=/Applications/XAMPP/xamppfiles/var/mysql/mysql.sock &
    sleep 4
    echo "  ✅ MySQL started"
fi

# ── 2. Laravel dev server ─────────────────────────────────────────────────────
echo ""
echo "▶ [2/4] Laravel (port 8000)..."
if curl -s --max-time 2 http://127.0.0.1:8000/login &>/dev/null; then
    echo "  ✅ Laravel sudah jalan"
else
    nohup php -S 127.0.0.1:8000 \
        -t "$LARAVEL_DIR/public" \
        "$LARAVEL_DIR/server.php" \
        >> "$LOG_DIR/laravel_server.log" 2>&1 &
    sleep 2
    echo "  ✅ Laravel started (PID $!)"
fi

# ── 3. Sentiment API ──────────────────────────────────────────────────────────
echo ""
echo "▶ [3/4] Sentiment API (port 8002)..."
if curl -s --max-time 2 http://127.0.0.1:8002/health &>/dev/null; then
    echo "  ✅ Sentiment API sudah jalan"
else
    cd "$LARAVEL_DIR"
    nohup python3 quant/sentiment_api.py \
        >> "$LOG_DIR/sentiment_api.log" 2>&1 &
    sleep 3
    echo "  ✅ Sentiment API started (PID $!)"
fi

# ── 4. Prediction API ─────────────────────────────────────────────────────────
echo ""
echo "▶ [4/4] Prediction API (port 8001)..."
if curl -s --max-time 2 http://127.0.0.1:8001/health &>/dev/null; then
    echo "  ✅ Prediction API sudah jalan"
else
    cd "$LARAVEL_DIR"
    nohup python3 quant/prediction_api.py \
        >> "$LOG_DIR/prediction_api.log" 2>&1 &
    sleep 3
    echo "  ✅ Prediction API started (PID $!)"
fi

# ── Cek akhir ─────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 Status Check:"
$XAMPP_BIN/mysqladmin --socket=/Applications/XAMPP/xamppfiles/var/mysql/mysql.sock ping 2>/dev/null \
    && echo "  🗄️  MySQL     : ✅ ALIVE" || echo "  🗄️  MySQL     : ❌ DOWN"
curl -s -o /dev/null -w "  🌐 Laravel    : ✅ HTTP %{http_code}\n" --max-time 3 http://127.0.0.1:8000/login 2>/dev/null || echo "  🌐 Laravel    : ❌ DOWN"
curl -s -o /dev/null -w "  🧠 Sentiment  : ✅ HTTP %{http_code}\n" --max-time 3 http://127.0.0.1:8002/health 2>/dev/null || echo "  🧠 Sentiment  : ❌ DOWN"
curl -s -o /dev/null -w "  📈 Prediction : ✅ HTTP %{http_code}\n" --max-time 3 http://127.0.0.1:8001/health 2>/dev/null || echo "  📈 Prediction : ❌ DOWN"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Selesai! Buka: http://127.0.0.1:8000"
