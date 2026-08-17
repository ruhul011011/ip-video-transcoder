# Run on Windows (Ryzen / RTX PC)

Your PC specs are a great fit for this app:

| Component | Your PC | Recommendation |
|-----------|---------|----------------|
| CPU | Ryzen 9 7950X (16-core) | Plenty of headroom |
| RAM | 32 GB | Fine for many channels |
| GPU | **RTX 3060 12 GB** | Use **NVIDIA NVENC** for all HD channels |

Do **not** use Apple VideoToolbox on Windows — that is Mac-only. Use **H.264 (NVIDIA NVENC)** instead.

## 1. Install prerequisites

1. **Python 3.11+** — https://www.python.org/downloads/  
   Check **Add python.exe to PATH** during install.
2. **FFmpeg (full build with NVENC)** — https://www.gyan.dev/ffmpeg/builds/  
   Download **ffmpeg-release-full** shared or essentials+NVENC capable full build.  
   Unzip, then add the `bin` folder (contains `ffmpeg.exe`) to System PATH.
3. Confirm in a new Command Prompt:

```bat
ffmpeg -encoders | findstr nvenc
nvidia-smi
```

You should see `h264_nvenc` and your RTX 3060 listed.

## 2. Copy the project

Copy the whole `IP Video Transcoder` folder to the Windows PC, e.g.:

`C:\IP Video Transcoder`

## 3. Start the app

Double-click:

`start-windows.bat`

Or in Command Prompt:

```bat
cd "C:\IP Video Transcoder"
start-windows.bat
```

Open: http://127.0.0.1:9527

## 4. Channel settings for RTX 3060

For each HD channel (720p / 1080p):

| Setting | Value |
|--------|--------|
| Encoding | **H.264 (NVIDIA NVENC)** |
| Frame Size | 720p or 1080p |
| Frame Rate | 25 or 30 |
| Bitrate | 2500–4000 (720p) / 4500–6000 (1080p) |
| Key Frame | 2 sec |
| CBR | ON |

SD / low-res channels can stay on **H.264 (x264 software)** or also use NVENC (RTX 3060 handles many concurrent NVENC streams).

## 5. If you copied channels from the Mac

Any channel still set to **VideoToolbox** will fail on Windows. Edit each HD channel → set Encoding to **NVIDIA NVENC** → Apply → Start.

## Optional: Docker on Windows

If you prefer Docker Desktop:

```bat
docker compose up --build -d
```

For GPU NVENC inside Docker you need the NVIDIA Container Toolkit; native Windows + `start-windows.bat` is simpler for your setup.
