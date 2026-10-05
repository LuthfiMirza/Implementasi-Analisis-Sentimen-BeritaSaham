#!/bin/bash
# ============================================================
# STOP SENTIMENA — matikan MySQL + Laravel sekaligus
# ============================================================

echo "🔴 Matikan Laravel & Scheduler..."
pkill -f "php artisan serve" 2>/dev/null && echo "✅ Laravel: MATI" || echo "⚠️  Laravel sudah mati"
pkill -f "php artisan schedule:work" 2>/dev/null && echo "✅ Scheduler: MATI" || echo "⚠️  Scheduler sudah mati"

echo "🔴 Matikan MySQL (XAMPP)..."
/Applications/XAMPP/xamppfiles/bin/mysql.server stop 2>&1

echo ""
echo "✅ SELESAI — semua service dimatikan."
