from __future__ import annotations

from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class ChannelStatus(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    ERROR = "ERROR"
    STARTING = "STARTING"
    STOPPING = "STOPPING"


class VideoSettings(BaseModel):
    enabled: bool = True
    encoding: str = "libx264"  # libx264, copy, h264_nvenc, h264_qsv, h264_videotoolbox
    frame_size: str = "640x360"  # original | WxH
    frame_rate: str = "original"  # original | number
    bitrate_kbps: int = 800
    keyframe_interval_sec: int = 5
    cbr: bool = False
    preset: str = "veryfast"


class AudioSettings(BaseModel):
    enabled: bool = True
    encoding: str = "aac"  # aac, copy
    sample_rate: str = "original"  # original | 44100 | 48000
    channels: str = "stereo"  # original | mono | stereo
    bitrate_kbps: Optional[int] = None  # None = default (128)


class ChannelCreate(BaseModel):
    media_source: str = ""
    target_format: str = "rtmp"
    target_url: str = ""
    memo: str = ""
    bind: str = ""
    # IPTV CDNs often block FFmpeg's default Lavf user-agent (HTTP 403)
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    http_headers: str = ""  # optional extra headers, one per line
    video: VideoSettings = Field(default_factory=VideoSettings)
    audio: AudioSettings = Field(default_factory=AudioSettings)


class ChannelUpdate(BaseModel):
    media_source: Optional[str] = None
    target_format: Optional[str] = None
    target_url: Optional[str] = None
    memo: Optional[str] = None
    bind: Optional[str] = None
    user_agent: Optional[str] = None
    http_headers: Optional[str] = None
    video: Optional[VideoSettings] = None
    audio: Optional[AudioSettings] = None


class Channel(ChannelCreate):
    id: str = Field(default_factory=lambda: str(uuid4()))
    index: int = 1
    status: ChannelStatus = ChannelStatus.IDLE
    error: Optional[str] = None
    pid: Optional[int] = None
    started_at: Optional[float] = None
    last_log: Optional[str] = None
    # When true, app restarts will automatically start this channel again
    autostart: bool = False


class SystemStats(BaseModel):
    cpu_percent: list[float]
    cpu_avg: float
    memory_percent: float
    gpu_percent: Optional[float] = None
