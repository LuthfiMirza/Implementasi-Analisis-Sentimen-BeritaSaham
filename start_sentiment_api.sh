#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

exec quant/.venv-sentiment/bin/python3 -m uvicorn quant.sentiment_api:app \
  --host 127.0.0.1 \
  --port 8002 \
  --reload
