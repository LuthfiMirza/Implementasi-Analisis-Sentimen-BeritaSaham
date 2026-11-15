#!/bin/bash
# ============================================================
# STOP SENTIMENA — matikan MySQL + Laravel sekaligus
# ============================================================

echo "🔴 Matikan Laravel & Scheduler..."
pkill -f "127.0.0.1:8000" 2>/dev/null || true
pkill -f "php artisan serve" 2>/dev/null && echo "✅ Laravel: MATI" || echo "✅ Laravel: MATI"
pkill -f "php artisan schedule:work" 2>/dev/null && echo "✅ Scheduler: MATI" || echo "⚠️  Scheduler sudah mati"

echo "🔴 Matikan Python APIs (Sentiment & Prediction)..."
pkill -f "uvicorn quant.sentiment_api" 2>/dev/null && echo "✅ Sentiment API: MATI" || echo "⚠️  Sentiment API sudah mati"
pkill -f "uvicorn quant.prediction_api" 2>/dev/null && echo "✅ Prediction API: MATI" || echo "⚠️  Prediction API sudah mati"

echo "🔴 Matikan MySQL (XAMPP)..."
/Applications/XAMPP/xamppfiles/bin/mysqladmin --socket=/Applications/XAMPP/xamppfiles/var/mysql/mysql.sock shutdown 2>/dev/null || /Applications/XAMPP/xamppfiles/bin/mysql.server stop 2>&1

echo ""
echo "✅ SELESAI — semua service dimatikan."
