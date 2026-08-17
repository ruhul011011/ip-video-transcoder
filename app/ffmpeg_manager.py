from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

from .models import Channel, ChannelStatus, VideoSettings, AudioSettings
from .storage import ChannelStore

logger = logging.getLogger("transcoder")

IS_WINDOWS = sys.platform == "win32"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def _popen_kwargs() -> dict:
    """Platform-safe subprocess flags for long-running FFmpeg workers."""
    if IS_WINDOWS:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        return {"creationflags": flags}
    return {"start_new_session": True}


def _terminate_process(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        if IS_WINDOWS:
            proc.terminate()
        else:
            os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, OSError):
        return
    try:
        proc.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        if IS_WINDOWS:
            proc.kill()
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, OSError):
        return
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass


def _which_ffmpeg() -> str:
    env = os.environ.get("FFMPEG_PATH")
    if env and Path(env).exists():
        return env
    from shutil import which

    found = which("ffmpeg")
    if not found:
        raise RuntimeError(
            "ffmpeg not found. Install ffmpeg or set FFMPEG_PATH, or run via Docker."
        )
    return found


def _is_http_like(url: str) -> bool:
    return urlparse(url).scheme.lower() in ("http", "https")


def _is_rtmp(url: str) -> bool:
    return urlparse(url).scheme.lower() in ("rtmp", "rtmps")


def _is_live_protocol(url: str) -> bool:
    scheme = urlparse(url).scheme.lower()
    return scheme in ("http", "https", "rtmp", "rtmps", "rtsp", "rtsps", "srt", "udp", "rtp")


def _origin_referer(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}/"


def _input_headers(channel: Channel, src: str) -> List[str]:
    """Build FFmpeg HTTP input options so IPTV CDNs don't return 403."""
    if not _is_http_like(src):
        return []

    user_agent = (channel.user_agent or "").strip() or DEFAULT_USER_AGENT
    header_lines: List[str] = []

    custom = (channel.http_headers or "").strip()
    if custom:
        normalized = custom.replace("\\r\\n", "\n").replace("\r\n", "\n")
        for line in normalized.split("\n"):
            line = line.strip()
            if line:
                header_lines.append(line)

    lower_blob = "\n".join(header_lines).lower()
    if "referer:" not in lower_blob:
        referer = _origin_referer(src)
        if referer:
            header_lines.append(f"Referer: {referer}")
    if "connection:" not in lower_blob:
        header_lines.append("Connection: keep-alive")
    if "accept:" not in lower_blob:
        header_lines.append("Accept: */*")

    args: List[str] = [
        "-user_agent",
        user_agent,
        "-reconnect",
        "1",
        "-reconnect_streamed",
        "1",
        "-reconnect_at_eof",
        "1",
        "-reconnect_on_network_error",
        "1",
        "-reconnect_on_http_error",
        "4xx,5xx",
        "-reconnect_delay_max",
        "10",
        "-multiple_requests",
        "1",
        "-seekable",
        "0",
        "-rw_timeout",
        "30000000",
    ]
    if header_lines:
        args += ["-headers", "".join(f"{h}\r\n" for h in header_lines)]
    return args


def build_ffmpeg_cmd(channel: Channel, ffmpeg: str, settings: Optional[object] = None) -> List[str]:
    src = channel.media_source.strip()
    dst = channel.target_url.strip()
    if not src:
        raise ValueError("Media source is required")
    if not dst:
        raise ValueError("Target URL is required")

    loop_files = bool(getattr(settings, "loop_file_source", False)) if settings else False
    seamless = bool(getattr(settings, "seamless_streaming", True)) if settings else True

    cmd: List[str] = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "warning",
        "-fflags",
        "+genpts+discardcorrupt+igndts",
        "-err_detect",
        "ignore_err",
        "-analyzeduration",
        "5000000",
        "-probesize",
        "5000000",
        "-thread_queue_size",
        "1024" if not seamless else "8192",
    ]

    live = _is_live_protocol(src)
    if not live:
        if loop_files:
            cmd += ["-stream_loop", "-1"]
        cmd += ["-re"]

    if _is_rtmp(src):
        cmd += ["-rtmp_live", "live", "-rw_timeout", "15000000"]

    cmd += _input_headers(channel, src)
    cmd += ["-i", src]

    video = channel.video
    audio = channel.audio

    # Explicit maps: the fifo muxer below cannot auto-select streams, and this
    # also keeps the TS data/subtitle streams out of the FLV output.
    if video.enabled:
        cmd += ["-map", "0:v:0?"]
    if audio.enabled:
        cmd += ["-map", "0:a:0?"]

    if video.enabled:
        cmd += _video_args(video)
    else:
        cmd += ["-vn"]

    if audio.enabled:
        cmd += _audio_args(audio)
    else:
        cmd += ["-an"]

    cmd += [
        "-max_muxing_queue_size",
        "1024" if not seamless else "8192",
        # Bounded interleave window: a stalled audio stream must not hold video
        # packets. 0 would mean "wait forever for every stream" and makes the
        # muxer emit long bursts instead of a steady stream. Keep 1s rather than
        # a tighter window so brief audio lag doesn't force non-interleaved
        # output, which some RTMP ingests reject.
        "-max_interleave_delta",
        "1000000",
        "-avoid_negative_ts",
        "make_zero",
        # Push each packet to the socket instead of filling the 32 KB avio buffer
        "-flush_packets",
        "1",
    ]

    fmt = (channel.target_format or "rtmp").lower()
    if fmt == "rtmp" or dst.startswith("rtmp"):
        if seamless:
            # Without this wrapper a single broken pipe from the RTMP ingest
            # kills ffmpeg, costing a full channel restart (restart delay plus
            # re-probing the source). The fifo muxer reconnects the output in
            # ~1s while the source connection and encoder keep running. Bounded
            # attempts so a permanently dead ingest still exits and lets the
            # supervisor do a clean restart.
            cmd += [
                "-f",
                "fifo",
                "-fifo_format",
                "flv",
                "-format_opts",
                "flvflags=no_duration_filesize",
                "-queue_size",
                "900",
                "-attempt_recovery",
                "1",
                "-recover_any_error",
                "1",
                "-recovery_wait_time",
                "1",
                "-max_recovery_attempts",
                "10",
                "-restart_with_keyframe",
                "1",
                "-drop_pkts_on_overflow",
                "1",
                dst,
            ]
        else:
            cmd += [
                "-f",
                "flv",
                "-flvflags",
                "no_duration_filesize",
                dst,
            ]
    elif fmt == "mpegts":
        cmd += ["-f", "mpegts", dst]
    elif fmt == "hls":
        cmd += [
            "-f",
            "hls",
            "-hls_time",
            "2",
            "-hls_list_size",
            "6",
            "-hls_flags",
            "delete_segments+append_list",
            dst,
        ]
    else:
        cmd += ["-f", "flv", "-flvflags", "no_duration_filesize", dst]

    return cmd


def _parse_fps(frame_rate: str) -> int:
    if not frame_rate or frame_rate.lower() == "original":
        return 25
    try:
        return max(int(float(frame_rate)), 1)
    except ValueError:
        return 25


def _video_args(video: VideoSettings) -> List[str]:
    if video.encoding == "copy":
        return ["-c:v", "copy"]

    fps = _parse_fps(video.frame_rate)
    gop_sec = video.keyframe_interval_sec if video.keyframe_interval_sec else 2
    gop = max(int(gop_sec) * fps, fps)
    bitrate = max(int(video.bitrate_kbps or 800), 50)

    vf_parts: List[str] = []
    if video.frame_size and video.frame_size.lower() != "original":
        size = video.frame_size.replace(" ", "")
        presets = {
            "nhd": "640x360",
            "hd480": "854x480",
            "hd720": "1280x720",
            "hd1080": "1920x1080",
            "4k": "3840x2160",
        }
        mapped = presets.get(size.lower(), size if "x" in size.lower() else None)
        if mapped:
            w, h = mapped.lower().split("x")
            vf_parts.append(
                f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"
            )
    if video.frame_rate and video.frame_rate.lower() != "original":
        # Rebuild a monotonic timeline so source discontinuities don't freeze players
        vf_parts.append(f"fps={fps}")
        vf_parts.append("setpts=N/FRAME_RATE/TB")

    args: List[str] = []
    if vf_parts:
        args += ["-vf", ",".join(vf_parts)]

    args += ["-c:v", video.encoding, "-fps_mode", "cfr"]
    if video.frame_rate and video.frame_rate.lower() != "original":
        args += ["-r", str(fps)]

    args += ["-b:v", f"{bitrate}k"]
    bufsize = bitrate * 4 if video.cbr else bitrate * 3
    if video.cbr:
        args += ["-minrate", f"{bitrate}k", "-maxrate", f"{bitrate}k", "-bufsize", f"{bufsize}k"]
    else:
        args += ["-maxrate", f"{int(bitrate * 1.5)}k", "-bufsize", f"{bufsize}k"]

    enc = video.encoding
    if enc == "libx264":
        # Prefer quality-friendly realtime presets. ultrafast looks blocky vs NVENC
        # at the same bitrate (common when comparing Windows GPU vs Ubuntu VPS CPU).
        preset = (video.preset or "veryfast").strip() or "veryfast"
        if preset == "ultrafast":
            preset = "veryfast"
        x264 = (
            f"keyint={gop}:min-keyint={gop}:scenecut=0:bframes=0:"
            f"force-cfr=1:rc-lookahead=10:sync-lookahead=0:sliced-threads=1:"
            f"nal-hrd={'cbr' if video.cbr else 'none'}:"
            f"vbv-maxrate={bitrate}:vbv-bufsize={bufsize}"
        )
        args += [
            "-preset",
            preset,
            "-tune",
            "zerolatency",
            "-profile:v",
            "main",
            "-pix_fmt",
            "yuv420p",
            "-g",
            str(gop),
            "-keyint_min",
            str(gop),
            "-bf",
            "0",
            "-x264-params",
            x264,
        ]
    elif enc == "h264_videotoolbox":
        args += [
            "-profile:v",
            "baseline",
            "-realtime",
            "1",
            "-pix_fmt",
            "yuv420p",
            "-g",
            str(gop),
            "-bf",
            "0",
            "-allow_sw",
            "1",
        ]
    elif enc in ("h264_nvenc", "hevc_nvenc"):
        # Tuned for NVIDIA consumer GPUs (e.g. RTX 3060) — low-latency live RTMP
        args += [
            "-preset",
            "p4",
            "-tune",
            "ll",
            "-rc",
            "cbr" if video.cbr else "vbr",
            "-pix_fmt",
            "yuv420p",
            "-profile:v",
            "main",
            "-g",
            str(gop),
            "-bf",
            "0",
            "-gpu",
            "0",
            "-delay",
            "0",
            "-zerolatency",
            "1",
        ]
    elif enc in ("h264_qsv", "hevc_qsv"):
        args += ["-preset", "veryfast", "-pix_fmt", "nv12", "-g", str(gop), "-bf", "0"]
    else:
        args += ["-g", str(gop), "-keyint_min", str(gop), "-bf", "0", "-pix_fmt", "yuv420p"]

    return args


def _audio_args(audio: AudioSettings) -> List[str]:
    if audio.encoding == "copy":
        return ["-c:a", "copy"]

    # Smooth over IPTV timestamp jumps after HTTP reconnects
    args = [
        "-af",
        "aresample=async=1:min_hard_comp=0.100:first_pts=0,asetpts=N/SR/TB",
        "-c:a",
        audio.encoding,
    ]
    if audio.sample_rate and audio.sample_rate.lower() != "original":
        args += ["-ar", str(audio.sample_rate)]
    else:
        args += ["-ar", "44100"]

    if audio.channels:
        ch = audio.channels.lower()
        if ch == "mono":
            args += ["-ac", "1"]
        elif ch == "stereo":
            args += ["-ac", "2"]

    bitrate = audio.bitrate_kbps if audio.bitrate_kbps else 128
    args += ["-b:a", f"{bitrate}k"]
    return args


class FFmpegManager:
    def __init__(self, store: ChannelStore, settings_store=None):
        self.store = store
        self.settings_store = settings_store
        self._procs: Dict[str, subprocess.Popen] = {}
        self._lock = threading.RLock()
        self._watchers: Dict[str, threading.Thread] = {}
        self._restart_counts: Dict[str, int] = {}
        self._run_tokens: Dict[str, int] = {}
        self._manual_stop: set[str] = set()
        self._supervisor_stop = threading.Event()
        self._supervisor = threading.Thread(target=self._supervise, daemon=True)
        self._supervisor.start()

    def _settings(self):
        if self.settings_store is None:
            from .settings import GlobalSettings

            return GlobalSettings()
        return self.settings_store.get()

    def shutdown(self) -> None:
        self._supervisor_stop.set()
        self.stop_all()

    def _supervise(self) -> None:
        """Safety net: if an autostart channel is ERROR/IDLE, keep trying to start it."""
        while not self._supervisor_stop.wait(5):
            try:
                settings = self._settings()
                if not settings.auto_restart_on_error:
                    continue
                for channel in self.store.list():
                    if channel.id in self._manual_stop:
                        continue
                    if not channel.autostart:
                        continue
                    if not channel.media_source or not channel.target_url:
                        continue
                    if channel.status not in (ChannelStatus.ERROR, ChannelStatus.IDLE):
                        continue
                    proc = self._procs.get(channel.id)
                    if proc is not None and proc.poll() is None:
                        continue
                    logger.info(
                        "Supervisor retrying channel %s (status=%s)",
                        channel.index,
                        channel.status,
                    )
                    try:
                        token = self._run_tokens.get(channel.id, 0)
                        self.start(channel.id, from_restart=True, token=token)
                    except Exception:
                        logger.exception("Supervisor failed to restart channel %s", channel.id)
            except Exception:
                logger.exception("Supervisor loop error")

    def reconcile(self) -> None:
        """Fix stale status when store and live processes disagree."""
        with self._lock:
            for channel in self.store.list():
                proc = self._procs.get(channel.id)
                alive = proc is not None and proc.poll() is None

                if alive:
                    if (
                        channel.status != ChannelStatus.RUNNING
                        or channel.pid != proc.pid
                        or not channel.autostart
                    ):
                        channel.status = ChannelStatus.RUNNING
                        channel.pid = proc.pid
                        channel.error = None
                        channel.autostart = True
                        if not channel.started_at:
                            channel.started_at = time.time()
                        self.store.save(channel)
                    continue

                if channel.status in (
                    ChannelStatus.RUNNING,
                    ChannelStatus.STARTING,
                    ChannelStatus.STOPPING,
                ):
                    channel.status = ChannelStatus.IDLE
                    channel.pid = None
                    channel.started_at = None
                    self.store.save(channel)

    def start(self, channel_id: str, *, from_restart: bool = False, token: Optional[int] = None) -> Channel:
        with self._lock:
            channel = self.store.get(channel_id)
            if not channel:
                raise KeyError("Channel not found")

            existing = self._procs.get(channel_id)
            if existing is not None and existing.poll() is None:
                # Keep store in sync if a previous stop/start race left status stale
                if channel.status != ChannelStatus.RUNNING or channel.pid != existing.pid:
                    channel.status = ChannelStatus.RUNNING
                    channel.pid = existing.pid
                    channel.error = None
                    channel.autostart = True
                    if not channel.started_at:
                        channel.started_at = time.time()
                    self.store.save(channel)
                return channel

            # If a stop is mid-flight, wait briefly for it to finish before starting again
            if channel.status == ChannelStatus.STOPPING:
                self._lock.release()
                try:
                    for _ in range(20):
                        time.sleep(0.25)
                        with self._lock:
                            channel = self.store.get(channel_id)
                            if not channel:
                                raise KeyError("Channel not found")
                            if channel.status != ChannelStatus.STOPPING:
                                break
                            existing = self._procs.get(channel_id)
                            if existing is None:
                                # Stop lost the process handle; clear stuck STOPPING
                                channel.status = ChannelStatus.IDLE
                                channel.pid = None
                                channel.started_at = None
                                self.store.save(channel)
                                break
                finally:
                    self._lock.acquire()
                channel = self.store.get(channel_id)
                if not channel:
                    raise KeyError("Channel not found")
                existing = self._procs.get(channel_id)
                if existing is not None and existing.poll() is None:
                    channel.status = ChannelStatus.RUNNING
                    channel.pid = existing.pid
                    channel.autostart = True
                    self.store.save(channel)
                    return channel

            if from_restart:
                # Abort if user stopped/started a newer run while we were sleeping
                if channel_id in self._manual_stop:
                    return channel
                if token is not None and self._run_tokens.get(channel_id, 0) != token:
                    return channel
                if channel_id not in self._run_tokens:
                    self._run_tokens[channel_id] = 0
            else:
                self._manual_stop.discard(channel_id)
                self._restart_counts[channel_id] = 0
                self._run_tokens[channel_id] = self._run_tokens.get(channel_id, 0) + 1
                channel.autostart = True

            run_token = self._run_tokens.get(channel_id, 0)
            ffmpeg = _which_ffmpeg()
            settings = self._settings()
            cmd = build_ffmpeg_cmd(channel, ffmpeg, settings)
            logger.info("Starting channel %s: %s", channel.index, " ".join(cmd))

            channel.status = ChannelStatus.STARTING
            channel.error = None
            if not from_restart:
                channel.last_log = None
            self.store.save(channel)

            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    **_popen_kwargs(),
                )
            except Exception as exc:
                channel.status = ChannelStatus.ERROR
                channel.error = str(exc)
                self.store.save(channel)
                raise

            self._procs[channel_id] = proc
            channel.pid = proc.pid
            channel.started_at = time.time()
            channel.status = ChannelStatus.RUNNING
            self.store.save(channel)

            watcher = threading.Thread(
                target=self._watch,
                args=(channel_id, proc, run_token, channel.started_at),
                daemon=True,
            )
            self._watchers[channel_id] = watcher
            watcher.start()
            return channel

    def stop(self, channel_id: str, *, clear_autostart: bool = True) -> Channel:
        with self._lock:
            channel = self.store.get(channel_id)
            if not channel:
                raise KeyError("Channel not found")

            self._manual_stop.add(channel_id)
            stop_token = self._run_tokens.get(channel_id, 0) + 1
            self._run_tokens[channel_id] = stop_token
            proc = self._procs.pop(channel_id, None)
            channel.status = ChannelStatus.STOPPING
            self.store.save(channel)

        # Wait outside the lock so other channels stay responsive
        if proc is not None:
            _terminate_process(proc)

        with self._lock:
            channel = self.store.get(channel_id) or channel
            # A newer start happened while we were waiting — do not clobber it
            if self._run_tokens.get(channel_id) != stop_token:
                return self.store.get(channel_id) or channel
            channel.status = ChannelStatus.IDLE
            channel.pid = None
            channel.started_at = None
            channel.error = None
            if clear_autostart:
                channel.autostart = False
            self.store.save(channel)
            return channel

    def stop_all(self) -> None:
        ids = [c.id for c in self.store.list()]
        for channel_id in ids:
            try:
                # Keep autostart so channels resume after app restart
                self.stop(channel_id, clear_autostart=False)
            except Exception:
                logger.exception("Failed stopping channel %s", channel_id)

    def _persist_log(self, channel_id: str, lines: List[str]) -> None:
        channel = self.store.get(channel_id)
        if not channel:
            return
        channel.last_log = "\n".join(lines[-10:])
        self.store.save(channel)

    def _watch(
        self,
        channel_id: str,
        proc: subprocess.Popen,
        run_token: int,
        started_at: float,
    ) -> None:
        lines: List[str] = []
        last_save = 0.0
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                text = line.rstrip()
                if not text:
                    continue
                # Skip noisy decoder chatter that isn't actionable
                if "non-existing SPS" in text or "Increasing reorder buffer" in text:
                    continue
                if "Last message repeated" in text:
                    continue
                lines.append(text)
                if len(lines) > 50:
                    lines = lines[-50:]
                now = time.time()
                if now - last_save >= 2.0:
                    self._persist_log(channel_id, lines)
                    last_save = now
        finally:
            code = proc.wait()
            if lines:
                self._persist_log(channel_id, lines)

            should_restart = False
            restart_token: Optional[int] = None
            delay = 3
            with self._lock:
                current = self._procs.get(channel_id)
                if current is not proc:
                    return
                self._procs.pop(channel_id, None)

                # Stale watcher from an older run
                if self._run_tokens.get(channel_id) != run_token:
                    return

                channel = self.store.get(channel_id)
                if not channel:
                    return

                if channel_id in self._manual_stop or channel.status == ChannelStatus.STOPPING:
                    channel.status = ChannelStatus.IDLE
                    channel.pid = None
                    channel.started_at = None
                    self.store.save(channel)
                    return

                settings = self._settings()
                ran_for = time.time() - started_at
                if ran_for >= 60:
                    self._restart_counts[channel_id] = 0

                # Source ended or failed — keep trying while autostart + auto-restart are on
                want_retry = (
                    settings.auto_restart_on_error
                    and channel.autostart
                    and channel_id not in self._manual_stop
                )

                if code == 0 and not want_retry:
                    channel.status = ChannelStatus.IDLE
                    channel.pid = None
                    channel.started_at = None
                    self.store.save(channel)
                    return

                count = self._restart_counts.get(channel_id, 0) + 1
                self._restart_counts[channel_id] = count
                channel.status = ChannelStatus.ERROR
                channel.pid = None
                channel.error = (
                    channel.last_log
                    or f"ffmpeg exited with code {code}; auto-restart in {settings.auto_restart_delay_sec}s (try #{count})"
                )[-500:]
                if want_retry:
                    channel.last_log = (
                        f"Input/output stopped (exit {code}). "
                        f"Auto-restarting in {settings.auto_restart_delay_sec}s… (try #{count})"
                    )
                self.store.save(channel)

                if want_retry:
                    should_restart = True
                    restart_token = run_token
                    delay = max(1, int(settings.auto_restart_delay_sec))

            if should_restart and restart_token is not None:
                logger.warning(
                    "Channel %s exited (%s); restarting in %ss (attempt %s)",
                    channel_id,
                    code,
                    delay,
                    self._restart_counts.get(channel_id),
                )
                time.sleep(delay)
                if channel_id in self._manual_stop:
                    return
                if self._run_tokens.get(channel_id) != restart_token:
                    return
                try:
                    self.start(channel_id, from_restart=True, token=restart_token)
                except Exception as exc:
                    logger.exception("Auto-restart failed for %s", channel_id)
                    # Leave ERROR; supervisor will try again
                    channel = self.store.get(channel_id)
                    if channel and channel.autostart:
                        channel.status = ChannelStatus.ERROR
                        channel.error = str(exc)
                        self.store.save(channel)
