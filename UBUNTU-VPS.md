# Complete setup from GitHub → Ubuntu VPS

Repo: https://github.com/ruhul011011/ip-video-transcoder

**VPS:** Ubuntu · 8 vCores · 24 GB RAM · no GPU  
**Encoder on VPS:** **H.264 (x264 software)** only (not NVENC)

---

## 0) Make the GitHub repo reachable

If `https://github.com/ruhul011011/ip-video-transcoder` opens in a browser **without login**, use the **public** steps below.

If it shows **404**, the repo is **private**. Either:

- GitHub → repo → **Settings → General → Danger Zone → Change visibility → Public**, or  
- keep it private and use a **Personal Access Token** (see Step 2B).

---

## 1) SSH into your VPS

From your PC:

```bash
ssh ubuntu@YOUR_VPS_IP
```

(Replace `ubuntu` with your real username if different, and use your VPS IP.)

Update packages once:

```bash
sudo apt update
sudo apt install -y git curl
```

---

## 2) Download the project from GitHub

### 2A — Public repository (simplest)

```bash
cd ~
git clone https://github.com/ruhul011011/ip-video-transcoder.git
cd ip-video-transcoder
ls
```

You should see files like `app`, `static`, `install-ubuntu.sh`, `requirements.txt`.

### 2B — Private repository (token)

1. GitHub → **Settings → Developer settings → Personal access tokens**  
   Create a token with `repo` access.
2. Clone with token:

```bash
cd ~
git clone https://YOUR_GITHUB_USERNAME:YOUR_TOKEN@github.com/ruhul011011/ip-video-transcoder.git
cd ip-video-transcoder
```

---

## 3) Run the automatic installer

> **Note:** Ubuntu 26.04 may ship Python 3.14. The installer automatically prefers **Python 3.12** because current app deps do not support 3.14 yet.

```bash
chmod +x install-ubuntu.sh start-linux.sh
sudo bash install-ubuntu.sh
```

This installs:

- `ffmpeg` + Python  
- Python packages (venv)  
- systemd service `ip-transcoder` (starts on boot)  
- opens port **9527** if `ufw` is active  

Wait until it prints **Done** and a URL.

---

## 4) Open the web panel

In your browser:

```text
http://YOUR_VPS_IP:9527
```

### If the page does not load

1. In your **VPS control panel → Firewall / Security Group**, allow inbound **TCP 9527**.
2. On the server check:

```bash
sudo systemctl status ip-transcoder
sudo journalctl -u ip-transcoder -n 50 --no-pager
```

---

## 5) Create / restore your channels

### New setup
Use **New Channel** and add your IPTV → RTMP links.

### If you have Windows `channels.json` backup
On Windows, copy:

`IP Video Transcoder\data\channels.json`

Upload it (WinSCP) to the VPS as:

`/home/ubuntu/ip-video-transcoder/data/channels.json`

Then restart:

```bash
sudo systemctl restart ip-transcoder
```

**Required after Windows restore:** for every channel that used **NVIDIA NVENC**:

1. Stop channel  
2. Edit → Encoding = **H.264 (x264 software)**  
3. Apply → Start  

---

## 6) Recommended settings on this VPS (8 channels)

| Setting | Value |
|--------|--------|
| Encoding | **H.264 (x264 software)** |
| Frame Size | 640×360 or 854×480 (safer for 8 streams) |
| Bitrate | 800–1200 Kbps |
| FPS | 25 |
| Keyframe | 2 sec |
| CBR | ON |

**Global Settings:** keep Auto Restart on Error (3 sec) + Auto Start on boot + Seamless Streaming.

---

## 7) Useful commands

```bash
# Status
sudo systemctl status ip-transcoder

# Restart
sudo systemctl restart ip-transcoder

# Live logs
sudo journalctl -u ip-transcoder -f

# Update from GitHub later
cd ~/ip-video-transcoder
git pull
sudo systemctl restart ip-transcoder
```

---

## 8) Security (recommended)

```bash
sudo ufw allow OpenSSH
sudo ufw allow 9527/tcp
sudo ufw enable
```

Better: in the VPS firewall, allow port **9527 only from your home IP**.

---

## Quick copy-paste (public repo)

```bash
sudo apt update
sudo apt install -y git
cd ~
git clone https://github.com/ruhul011011/ip-video-transcoder.git
cd ip-video-transcoder
chmod +x install-ubuntu.sh start-linux.sh
sudo bash install-ubuntu.sh
```

Then open: `http://YOUR_VPS_IP:9527`

---

## Troubleshooting

| Issue | Fix |
|------|-----|
| `git clone` 404 | Make repo **public**, or use token (Step 2B) |
| UI not opening | Allow TCP **9527** in VPS firewall |
| Channel error `nvenc` | Change encoding to **x264 software** |
| Service failed | `sudo journalctl -u ip-transcoder -n 100 --no-pager` |
| HD freezes | Lower resolution/bitrate or fewer HD channels |

---

That’s the full path: **GitHub → clone on VPS → `install-ubuntu.sh` → open port 9527 → use x264**.
