#!/bin/bash
#
# Matikan service background yang dinyalakan ./dev-start.sh (Sentiment & Prediction API).
# MySQL dan cron TIDAK disentuh. Web server (:8000) matikan sendiri dengan Ctrl+C.

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

PID_DIR="storage/app/dev-pids"

for f in "$PID_DIR"/*.pid; do
    [ -e "$f" ] || continue
    name="$(basename "$f" .pid)"
    pid="$(cat "$f")"
    # uvicorn --reload spawns children -- kill the whole process group
    if kill -0 "$pid" 2>/dev/null; then
        pkill -TERM -P "$pid" 2>/dev/null
        kill -TERM "$pid" 2>/dev/null
        printf '  ✓ %s dihentikan (pid %s)\n' "$name" "$pid"
    else
        printf '  - %s sudah mati\n' "$name"
    fi
    rm -f "$f"
done

# sapu sisa uvicorn yang mungkin lolos
pkill -f "uvicorn quant.sentiment_api" 2>/dev/null && echo "  ✓ sisa sentiment_api disapu"
pkill -f "uvicorn quant.prediction_api" 2>/dev/null && echo "  ✓ sisa prediction_api disapu"

echo "Selesai."
