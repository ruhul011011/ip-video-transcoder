@echo off
setlocal
cd /d "%~dp0"

where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo [ERROR] ffmpeg not found in PATH.
  echo Install FFmpeg with NVIDIA support, then reopen this window.
  echo Recommended: https://www.gyan.dev/ffmpeg/builds/  ^(ffmpeg-release-full^)
  echo Add the ffmpeg\bin folder to your system PATH.
  pause
  exit /b 1
)

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python not found.
  echo Install Python 3.11+ from https://www.python.org/downloads/
  echo Enable "Add python.exe to PATH" during setup.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  python -m venv .venv
  if errorlevel 1 (
    echo Failed to create venv.
    pause
    exit /b 1
  )
  echo Installing Python packages...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

if not exist "data" mkdir data

echo.
echo Checking NVIDIA NVENC support...
ffmpeg -hide_banner -encoders 2>nul | findstr /i "h264_nvenc" >nul
if errorlevel 1 (
  echo [WARN] h264_nvenc not found in this FFmpeg build.
  echo For RTX 3060 HD channels, install a full FFmpeg build with NVENC.
) else (
  echo NVENC OK - use Encoding: H.264 ^(NVIDIA NVENC^) for HD channels.
)

echo.
echo Starting IP Video Transcoder on http://127.0.0.1:9527
echo Press Ctrl+C to stop.
echo.
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 9527
pause
