"""Where things live and how the server listens.

Everything a different host would need to change is here and comes from the
environment, so moving to an always-on machine later is configuration only.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

PROFILES = ("main", "demo")
DEFAULT_PORT = 8765


@dataclass(frozen=True)
class Config:
    data_dir: Path
    host: str = "127.0.0.1"
    port: int = DEFAULT_PORT
    auto_download_model: bool = True

    # ---- folders (all under the data folder, never next to the program)
    def profile_dir(self, profile: str) -> Path:
        if profile not in PROFILES:
            raise ValueError(f"unknown profile {profile!r}")
        return self.data_dir if profile == "main" else self.data_dir / "demo"

    def db_path(self, profile: str) -> Path:
        return self.profile_dir(profile) / "closet.db"

    def images_dir(self, profile: str) -> Path:
        return self.profile_dir(profile) / "images"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def local_backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def state_path(self) -> Path:
        return self.data_dir / "settings.json"

    @property
    def lock_path(self) -> Path:
        return self.data_dir / "closet.lock"


def load(env: dict | None = None) -> Config:
    env = os.environ if env is None else env
    data_dir = Path(env.get("CLOSET_DATA_DIR") or Path.home() / "Closet").expanduser()
    return Config(
        data_dir=data_dir,
        host=env.get("CLOSET_HOST", "127.0.0.1"),
        port=int(env.get("CLOSET_PORT", DEFAULT_PORT)),
        auto_download_model=env.get("CLOSET_NO_AUTO_DOWNLOAD", "") not in ("1", "true", "yes"),
    )


def bundle_dir() -> Path:
    """Folder holding files shipped with the program (frontend, migrations, demo data)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "closet"
    return Path(__file__).resolve().parent
