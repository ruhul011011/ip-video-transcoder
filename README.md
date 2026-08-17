# IP Video Transcoder

Multi-channel live transcoder:

**IPTV / HTTP / HLS input → H.264/AAC encode → RTMP output**

Web UI on port **9527**.

## Windows PC (RTX / Ryzen) — recommended for you

Your machine (Ryzen 9 + **RTX 3060**) should use **NVIDIA NVENC** for HD.

See full steps: **[WINDOWS.md](WINDOWS.md)**

Quick start:

1. Install Python 3.11+ and FFmpeg (full build with NVENC)
2. Copy this project folder to the PC
3. Run `start-windows.bat`
4. Open http://127.0.0.1:9527
5. For HD channels set Encoding → **H.264 (NVIDIA NVENC)**

## macOS

```bash
brew install ffmpeg
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 9527
```

For HD on Mac use **Apple VideoToolbox**.

## Ubuntu VPS (no GPU)

Yes — works on Ubuntu with your 8 vCore / 24 GB plan.

**Complete step-by-step guide:** **[UBUNTU-VPS.md](UBUNTU-VPS.md)**

```bash
chmod +x install-ubuntu.sh
sudo bash install-ubuntu.sh
```

Use **H.264 (x264 software)** on the VPS (no NVENC).

## Docker

```bash
docker compose up --build -d
```

Open: http://localhost:9527

## How to use

1. **New Channel** → **Edit**
2. Media Source = IPTV/HTTP URL
3. Target Format = RTMP
4. Target URL = `rtmp://host:1935/live/streamkey`
5. Set encode options → **Apply** → **Start Channel**

## Encoding guide

| Encoder | Use when |
|--------|----------|
| **NVIDIA NVENC** | Windows + NVIDIA GPU (your RTX 3060) |
| **Apple VideoToolbox** | macOS only |
| **x264 software** | No GPU / low-res channels |
| **Copy** | Remux only (no re-encode) |

HD tip: 720p → **2500–3500 Kbps**, keyframe **2s**, **CBR ON**.

## Global Settings

**Auto Restart Streaming on Error** keeps retrying if an IPTV input drops.

## Data

Configs: `data/channels.json`, `data/settings.json`
