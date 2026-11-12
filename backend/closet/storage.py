"""Disk space used by the active closet and shared program files."""
from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path

from . import db
from .config import Config


def _dir_bytes(root: Path) -> int:
    """Total size in bytes of regular files under `root`, without following symlinks."""
    total = 0
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def _image_bytes(root: Path) -> tuple[int, int, int]:
    """Return (photos_bytes, cutouts_bytes, thumbnails_bytes) under `root`."""
    photos = cutouts = thumbnails = 0
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            name = entry.name
                            if name.endswith(".part"):
                                continue
                            size = entry.stat(follow_symlinks=False).st_size
                            if name.endswith(".t.webp"):
                                thumbnails += size
                            elif name.endswith(".cut.webp"):
                                cutouts += size
                            else:
                                photos += size
                    except OSError:
                        continue
        except OSError:
            continue
    return photos, cutouts, thumbnails


def _database_bytes(db_path: Path) -> int:
    total = 0
    for suffix in ("", "-wal", "-shm", "-journal"):
        p = db_path.with_name(db_path.name + suffix)
        try:
            if not p.is_symlink() and p.is_file():
                total += p.stat().st_size
        except OSError:
            continue
    return total


def _free_bytes(data_dir: Path) -> int:
    for p in (data_dir, *data_dir.parents):
        try:
            if p.exists():
                return shutil.disk_usage(p).free
        except OSError:
            continue
    return 0


def info(cfg: Config, profile: str) -> dict:
    """Measure disk usage for `profile` and shared folders under `cfg.data_dir`."""
    db_path = cfg.db_path(profile)
    item_count = 0
    if not db_path.is_symlink() and db_path.is_file():
        try:
            conn = db.connect(db_path)
            try:
                item_count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
            finally:
                conn.close()
        except sqlite3.Error:
            item_count = 0

    photos_bytes, cutouts_bytes, thumbnails_bytes = _image_bytes(cfg.images_dir(profile))
    database_bytes = _database_bytes(db_path)
    backups_bytes = _dir_bytes(cfg.local_backups_dir)
    model_bytes = _dir_bytes(cfg.models_dir)
    logs_bytes = _dir_bytes(cfg.logs_dir)
    total_bytes = (
        photos_bytes + cutouts_bytes + thumbnails_bytes + database_bytes
        + backups_bytes + model_bytes + logs_bytes
    )
    return {
        "items": item_count,
        "photos_bytes": photos_bytes,
        "cutouts_bytes": cutouts_bytes,
        "thumbnails_bytes": thumbnails_bytes,
        "database_bytes": database_bytes,
        "backups_bytes": backups_bytes,
        "model_bytes": model_bytes,
        "logs_bytes": logs_bytes,
        "total_bytes": total_bytes,
        "data_dir": str(cfg.data_dir),
        "free_bytes": _free_bytes(cfg.data_dir),
    }
