#!/bin/bash
# Gemini Throttle Request Counter API の起動スクリプト
# 使い方: ./start_api.sh  または  systemd 経由
set -euo pipefail

cd "$(dirname "$0")"

VENV_PYTHON="/home/captain/.hermes2/installs/4af5e1a0fc404f97/environments/d01a101e0a6840ceaf822268505c3b74/venv/bin/python3"

exec "$VENV_PYTHON" -m uvicorn main:app --host "${API_HOST:-127.0.0.1}" --port "${API_PORT:-8900}"
