#!/usr/bin/env bash
# One-shot installer for Ubuntu VPS (no GPU — uses x264 software encode)
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="ip-transcoder"
SERVICE_USER="${SUDO_USER:-$USER}"
HTTP_PORT="${HTTP_PORT:-9527}"

echo "=== IP Video Transcoder — Ubuntu installer ==="
echo "App dir : $APP_DIR"
echo "User    : $SERVICE_USER"
echo "Port    : $HTTP_PORT"
echo

if [[ "$(id -u)" -eq 0 && -z "${SUDO_USER:-}" ]]; then
  echo "Run as a normal user with sudo, e.g.:  sudo bash install-ubuntu.sh"
  echo "Or:  sudo -u ubuntu bash install-ubuntu.sh  (from that user's copy of the app)"
fi

export DEBIAN_FRONTEND=noninteractive
echo "[1/6] Installing system packages..."
sudo apt-get update -y
sudo apt-get install -y ffmpeg python3 python3-venv python3-pip curl

echo "[2/6] Checking ffmpeg..."
ffmpeg -version | head -n 1

echo "[3/6] Creating Python venv + dependencies..."
cd "$APP_DIR"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

mkdir -p data
chmod +x start-linux.sh 2>/dev/null || true

# Sensible VPS defaults (software encode, auto-restart)
if [[ ! -f data/settings.json ]]; then
  cat > data/settings.json <<EOF
{
  "http_port": ${HTTP_PORT},
  "debug_log": false,
  "auto_start_on_boot": true,
  "auto_restart_on_error": true,
  "auto_restart_delay_sec": 3,
  "loop_file_source": false,
  "seamless_streaming": true
}
EOF
  echo "Wrote data/settings.json"
fi

# Empty channels file if missing — user will recreate or import
if [[ ! -f data/channels.json ]]; then
  echo "[]" > data/channels.json
  echo "Wrote empty data/channels.json"
fi

echo "[4/6] Writing systemd service..."
# Escape spaces in path for systemd
UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
PYTHON_BIN="$APP_DIR/.venv/bin/python"

sudo tee "$UNIT_PATH" >/dev/null <<EOF
[Unit]
Description=IP Video Transcoder
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${APP_DIR}
Environment=PYTHONUNBUFFERED=1
ExecStart="${PYTHON_BIN}" -m uvicorn app.main:app --host 0.0.0.0 --port ${HTTP_PORT}
Restart=always
RestartSec=3
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

echo "[5/6] Enabling service..."
sudo systemctl daemon-reload
sudo systemctl enable --now "${SERVICE_NAME}"

echo "[6/6] Firewall (ufw) — opening port ${HTTP_PORT} if ufw is active..."
if command -v ufw >/dev/null 2>&1; then
  if sudo ufw status | grep -qi "Status: active"; then
    sudo ufw allow "${HTTP_PORT}/tcp"
    sudo ufw reload || true
  else
    echo "ufw installed but not active — open port ${HTTP_PORT} in your VPS panel if needed."
  fi
else
  echo "ufw not installed — open port ${HTTP_PORT} in your VPS cloud firewall."
fi

sleep 2
echo
echo "=== Done ==="
sudo systemctl --no-pager --full status "${SERVICE_NAME}" || true
echo
IP="$(curl -s --max-time 3 ifconfig.me || hostname -I | awk '{print $1}')"
echo "Open in browser:  http://${IP}:${HTTP_PORT}"
echo
echo "Useful commands:"
echo "  sudo systemctl status ${SERVICE_NAME}"
echo "  sudo systemctl restart ${SERVICE_NAME}"
echo "  sudo journalctl -u ${SERVICE_NAME} -f"
echo
echo "IMPORTANT: On this VPS use Encoding = H.264 (x264 software)."
echo "Do NOT use NVIDIA NVENC or Apple VideoToolbox (no GPU / not Mac)."
