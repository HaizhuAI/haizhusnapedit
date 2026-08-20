#!/usr/bin/env bash
# SnapEdit Studio launcher
cd "$(dirname "$0")"
if [ ! -d venv ]; then
  echo "[setup] creating venv..."
  python3 -m venv venv
  ./venv/bin/pip install -q --upgrade pip
  ./venv/bin/pip install -q -r requirements.txt
fi
PORT="${PORT:-8000}"
echo "[run] SnapEdit Studio on http://0.0.0.0:${PORT}"
exec ./venv/bin/uvicorn backend.app:app --host 0.0.0.0 --port "${PORT}"
