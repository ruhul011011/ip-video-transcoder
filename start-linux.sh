#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "[ERROR] ffmpeg not found."
  echo "On Ubuntu run:  sudo apt update && sudo apt install -y ffmpeg python3 python3-venv python3-pip"
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] python3 not found."
  exit 1
fi

if [[ ! -d .venv ]]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install -r requirements.txt
fi

mkdir -p data

echo
echo "Starting IP Video Transcoder on http://0.0.0.0:9527"
echo "Open: http://YOUR_SERVER_IP:9527"
echo "Press Ctrl+C to stop."
echo

exec .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 9527
