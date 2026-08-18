from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List

import psutil
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .ffmpeg_manager import FFmpegManager
from .models import Channel, ChannelCreate, ChannelStatus, ChannelUpdate, SystemStats
from .settings import GlobalSettings, SettingsStore
from .storage import ChannelStore

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

store = ChannelStore(DATA_DIR / "channels.json")
settings_store = SettingsStore(DATA_DIR / "settings.json")
manager = FFmpegManager(store, settings_store)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = settings_store.get()
    to_resume = []
    for ch in store.list():
        should_resume = settings.auto_start_on_boot and (
            ch.autostart
            or ch.status in (ChannelStatus.RUNNING, ChannelStatus.STARTING)
        )
        if ch.status in (
            ChannelStatus.RUNNING,
            ChannelStatus.STARTING,
            ChannelStatus.STOPPING,
            ChannelStatus.ERROR,
        ):
            ch.status = ChannelStatus.IDLE
            ch.pid = None
            ch.started_at = None
            store.save(ch)
        if should_resume and ch.media_source and ch.target_url:
            ch.autostart = True
            store.save(ch)
            to_resume.append(ch.id)

    for channel_id in to_resume:
        try:
            manager.start(channel_id)
            logging.getLogger("transcoder").info("Auto-resumed channel %s", channel_id)
        except Exception:
            logging.getLogger("transcoder").exception("Failed to auto-resume %s", channel_id)

    yield
    manager.shutdown()


app = FastAPI(title="IP Video Transcoder", version="1.0.0", lifespan=lifespan)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/settings", response_model=GlobalSettings)
def get_settings():
    return settings_store.get()


@app.put("/api/settings", response_model=GlobalSettings)
def put_settings(payload: GlobalSettings):
    return settings_store.save(payload)


@app.get("/api/channels", response_model=List[Channel])
def list_channels():
    manager.reconcile()
    return store.list()


@app.post("/api/channels", response_model=Channel)
def create_channel(payload: ChannelCreate):
    return store.create(payload)


@app.get("/api/channels/{channel_id}", response_model=Channel)
def get_channel(channel_id: str):
    manager.reconcile()
    channel = store.get(channel_id)
    if not channel:
        raise HTTPException(404, "Channel not found")
    return channel


@app.put("/api/channels/{channel_id}", response_model=Channel)
def update_channel(channel_id: str, payload: ChannelUpdate):
    existing = store.get(channel_id)
    if not existing:
        raise HTTPException(404, "Channel not found")
    updated = store.update(channel_id, payload)
    return updated


@app.delete("/api/channels/{channel_id}")
def delete_channel(channel_id: str):
    existing = store.get(channel_id)
    if not existing:
        raise HTTPException(404, "Channel not found")
    if existing.status.value in ("RUNNING", "STARTING", "ERROR"):
        try:
            manager.stop(channel_id)
        except Exception:
            pass
    if not store.delete(channel_id):
        raise HTTPException(404, "Channel not found")
    return {"ok": True}


@app.post("/api/channels/{channel_id}/start", response_model=Channel)
def start_channel(channel_id: str):
    try:
        return manager.start(channel_id)
    except KeyError:
        raise HTTPException(404, "Channel not found")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/channels/{channel_id}/stop", response_model=Channel)
def stop_channel(channel_id: str):
    try:
        return manager.stop(channel_id)
    except KeyError:
        raise HTTPException(404, "Channel not found")


@app.post("/api/channels/{channel_id}/restart", response_model=Channel)
def restart_channel(channel_id: str):
    try:
        return manager.restart(channel_id)
    except KeyError:
        raise HTTPException(404, "Channel not found")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/stats", response_model=SystemStats)
def stats():
    per_cpu = psutil.cpu_percent(interval=0.1, percpu=True)
    return SystemStats(
        cpu_percent=per_cpu,
        cpu_avg=sum(per_cpu) / len(per_cpu) if per_cpu else 0.0,
        memory_percent=psutil.virtual_memory().percent,
        gpu_percent=None,
    )


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
