# Complete guide: Install on Ubuntu VPS

This guide takes your Windows backup and runs it 24/7 on a remote Ubuntu VPS.

**Your VPS:** 8 vCores · 24 GB RAM · 200 GB NVMe · Ubuntu  
**Encoder on VPS:** **H.264 (x264 software)** only (no NVIDIA GPU)

---

## Before you start

You need:

1. VPS IP address  
2. SSH user (often `ubuntu` or `root`)  
3. Your Windows project folder: `IP Video Transcoder`  
4. Optional: your `data\channels.json` backup (channel list)

---

## Step 1 — Prepare the project on Windows (optional cleanup)

On your Windows PC, inside `IP Video Transcoder`:

1. You can keep `data\channels.json` (your channel list).
2. Remember: on the VPS you must change every channel’s **Encoding** from **NVIDIA NVENC** → **H.264 (x264 software)**.

---

## Step 2 — Upload the project to the VPS

### Option A — WinSCP / FileZilla (easiest)

1. Connect with SFTP to your VPS IP (port 22).
2. Upload the whole folder to:
   ```text
   /home/ubuntu/IP Video Transcoder
   ```
   (Use your real username if it is not `ubuntu`.)

### Option B — PowerShell / scp

From Windows PowerShell (adjust paths/IP/user):

```powershell
scp -r "C:\IP Video Transcoder" ubuntu@YOUR_VPS_IP:~/
```

---

## Step 3 — SSH into the VPS

```bash
ssh ubuntu@YOUR_VPS_IP
```

Go to the app folder:

```bash
cd ~/IP\ Video\ Transcoder
ls
```

You should see `app`, `static`, `requirements.txt`, `install-ubuntu.sh`, etc.

---

## Step 4 — Run the installer (does everything)

```bash
chmod +x install-ubuntu.sh start-linux.sh
sudo bash install-ubuntu.sh
```

This will:

- install `ffmpeg` + Python
- create `.venv` and install packages
- create `data/settings.json` (auto-restart ON)
- install and start a **systemd** service named `ip-transcoder`
- try to open firewall port **9527**

---

## Step 5 — Open the web UI

In your browser:

```text
http://YOUR_VPS_IP:9527
```

If it does not load:

1. **VPS panel firewall / security group** → allow inbound **TCP 9527**
2. Check service:
   ```bash
   sudo systemctl status ip-transcoder
   ```

---

## Step 6 — Fix encodings for VPS (required)

For **each channel**:

1. Select channel → **Stop Channel** (if running)
2. **Edit**
3. Encoding → **H.264 (x264 software)**  
   (not NVENC, not VideoToolbox)
4. Suggested VPS-safe settings for 8 channels:

| Setting | SD (recommended for all 8) | HD (only 1–2 channels) |
|--------|----------------------------|-------------------------|
| Frame Size | 640×360 or 854×480 | 1280×720 |
| Bitrate | 800–1200 | 2000–2500 |
| FPS | 25 | 25 |
| Keyframe | 2 | 2 |
| CBR | ON | ON |

5. **Apply** → **Start Channel**

---

## Step 7 — Confirm Global Settings

Click **Global Settings** and keep:

- ☑ Auto Start channels on app boot  
- ☑ Auto Restart Streaming on Error after **3** seconds  
- ☑ Seamless Streaming  

Save.

---

## Step 8 — Daily / ops commands

```bash
# Status
sudo systemctl status ip-transcoder

# Restart app
sudo systemctl restart ip-transcoder

# Live logs
sudo journalctl -u ip-transcoder -f

# Stop app
sudo systemctl stop ip-transcoder
```

After reboot, the service starts automatically (`enable` was set by the installer).

---

## Step 9 — Security (strongly recommended)

The UI has **no password** by default.

Minimum:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 9527/tcp
sudo ufw enable
```

Better: allow 9527 only from your home/office IP in the VPS firewall panel.

---

## Troubleshooting

| Problem | Fix |
|--------|-----|
| Page not loading | Open TCP 9527 in cloud firewall + `sudo systemctl status ip-transcoder` |
| Channel ERROR mentioning nvenc / videotoolbox | Switch encoding to **x264 software** |
| HD freezes / stuck | Too much CPU — lower resolution/bitrate or run fewer HD channels |
| Service won’t start | `sudo journalctl -u ip-transcoder -n 100 --no-pager` |
| ffmpeg missing | `sudo apt install -y ffmpeg` then `sudo systemctl restart ip-transcoder` |

---

## Capacity reminder (your 8 vCore VPS)

- **8× SD** → best stability  
- **6× SD + 2× 720p** → usually OK  
- **8× heavy 720p software** → may stutter  

Your main benefit on the VPS is **stable high-speed internet**, which is what you wanted.

---

## Files created for VPS

| File | Purpose |
|------|---------|
| `install-ubuntu.sh` | Full auto install + systemd |
| `start-linux.sh` | Manual foreground start |
| `UBUNTU-VPS.md` | This guide |
