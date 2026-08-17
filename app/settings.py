from __future__ import annotations

import json
import threading
from pathlib import Path

from pydantic import BaseModel, Field


class GlobalSettings(BaseModel):
    http_port: int = 9527
    debug_log: bool = False
    # Resume channels marked autostart when the app process starts
    auto_start_on_boot: bool = True
    # Keep retrying when input/output fails or the source disconnects
    auto_restart_on_error: bool = True
    auto_restart_delay_sec: int = Field(default=3, ge=1, le=300)
    # For local file/folder sources: loop forever
    loop_file_source: bool = False
    # Prefer continuous publishing (extra reconnect / queue options)
    seamless_streaming: bool = True


class SettingsStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.save(GlobalSettings())

    def get(self) -> GlobalSettings:
        with self._lock:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return GlobalSettings.model_validate(raw)

    def save(self, settings: GlobalSettings) -> GlobalSettings:
        with self._lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
            tmp.replace(self.path)
            return settings

    def update(self, patch: dict) -> GlobalSettings:
        with self._lock:
            current = self.get()
            updated = current.model_copy(update=patch)
            return self.save(updated)
