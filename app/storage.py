from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import List, Optional

from .models import Channel, ChannelCreate, ChannelUpdate


class ChannelStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write([])

    def _read(self) -> List[dict]:
        with self.path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _write(self, channels: List[dict]) -> None:
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(channels, f, indent=2)
        tmp.replace(self.path)

    def list(self) -> List[Channel]:
        with self._lock:
            return [Channel.model_validate(c) for c in self._read()]

    def get(self, channel_id: str) -> Optional[Channel]:
        with self._lock:
            for c in self._read():
                if c["id"] == channel_id:
                    return Channel.model_validate(c)
            return None

    def create(self, data: ChannelCreate) -> Channel:
        with self._lock:
            channels = self._read()
            index = max((c.get("index", 0) for c in channels), default=0) + 1
            channel = Channel(**data.model_dump(), index=index)
            channels.append(channel.model_dump())
            self._write(channels)
            return channel

    def update(self, channel_id: str, data: ChannelUpdate) -> Optional[Channel]:
        with self._lock:
            channels = self._read()
            for i, raw in enumerate(channels):
                if raw["id"] != channel_id:
                    continue
                current = Channel.model_validate(raw)
                patch = data.model_dump(exclude_unset=True)
                updated = current.model_copy(update=patch)
                channels[i] = updated.model_dump()
                self._write(channels)
                return updated
            return None

    def save(self, channel: Channel) -> Channel:
        with self._lock:
            channels = self._read()
            for i, raw in enumerate(channels):
                if raw["id"] == channel.id:
                    channels[i] = channel.model_dump()
                    self._write(channels)
                    return channel
            channels.append(channel.model_dump())
            self._write(channels)
            return channel

    def delete(self, channel_id: str) -> bool:
        with self._lock:
            channels = self._read()
            new_channels = [c for c in channels if c["id"] != channel_id]
            if len(new_channels) == len(channels):
                return False
            for i, c in enumerate(sorted(new_channels, key=lambda x: x.get("index", 0)), start=1):
                c["index"] = i
            self._write(new_channels)
            return True
