"""Program-wide settings kept in one small JSON file in the data folder.

Holds what is not part of a closet: the passphrase hash, login sessions, the
backup folder, the model download URL, which closet (real or demo) is
open, and where the owner is (with the last forecast for it). Never holds the
Anthropic API key.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "passphrase": None,       # {"salt", "hash", "n", "r", "p"}
    "sessions": {},           # sha256(token) -> expiry (unix seconds)
    "failed_logins": [],      # unix seconds of recent failures
    "backup_folder": None,
    "last_backup": None,      # {"at", "ok", "error", "folder", "kind"}
    "model_url": None,        # override for the model download address
    "profile": "main",
    "tagging_api_enabled": False,  # may tagging use the API key (billed)? Off until the owner turns it on in Settings
    "place": None,            # {"name", "latitude", "longitude", "timezone"}, chosen in Settings
    "weather": None,          # the last forecast for the place: {"key", "fetched", "offset", "answer"}
    "trip_weather": {},       # bounded forecast/usual weather cache, never closet contents
}


class State:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        self._data = dict(DEFAULTS)
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                raise RuntimeError(
                    f"The settings file {path} cannot be read ({e}). Move it aside to start with fresh settings; "
                    "your closet database is separate and is not affected.") from e
            self._data.update({k: v for k, v in loaded.items() if k in DEFAULTS})

    def get(self, key: str) -> Any:
        with self._lock:
            return self._data[key]

    def update(self, **changes: Any) -> None:
        with self._lock:
            for k in changes:
                if k not in DEFAULTS:
                    raise KeyError(k)
            self._data.update(changes)
            self._save()

    def mutate(self, fn) -> Any:
        """Run `fn(data)` under the lock and save; returns fn's result."""
        with self._lock:
            result = fn(self._data)
            self._save()
            return result

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)
