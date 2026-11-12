"""How much disk the closet takes, worked out by walking its folders.

Nothing is stored: every call walks the folders again. Only folders inside the
data folder are read, links are not followed, and no file names are returned.
A folder that does not exist counts as nothing.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from . import db
from .config import Config


def _files(root: Path):
    """Sizes and names of the files under `root`, without following links. Missing or unreadable parts are skipped."""
    if root.is_symlink():
        return
    stack = [str(root)]
    while stack:
        try:
            entries = os.scandir(stack.pop())
        except OSError:
            continue
        with entries:
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        yield entry.name, entry.stat(follow_symlinks=False).st_size
                except OSError:  # removed while we looked, or not readable
                    continue


def folder_bytes(root: Path) -> int:
    return sum(size for _, size in _files(root))


def image_bytes(images_dir: Path) -> dict[str, int]:
    """Split by the kinds `images.py` writes: photo `x.webp`, its thumbnail `x.t.webp`, cutout `x.cut.webp`, its thumbnail `x.cut.t.webp`."""
    out = {"photos_bytes": 0, "cutouts_bytes": 0, "thumbnails_bytes": 0}
    for name, size in _files(images_dir):
        if name.endswith(".t.webp"):
            out["thumbnails_bytes"] += size
        elif name.endswith(".cut.webp"):
            out["cutouts_bytes"] += size
        else:  # the photos themselves, and any half-written file
            out["photos_bytes"] += size
    return out


def database_bytes(path: Path) -> int:
    total = 0
    for p in (path, path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")):
        try:
            if not p.is_symlink() and p.is_file():
                total += p.stat().st_size
        except OSError:
            continue
    return total


def item_count(path: Path) -> int:
    if not path.is_file():
        return 0
    conn = db.connect(path)
    try:
        return conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    finally:
        conn.close()


def free_bytes(folder: Path) -> int | None:
    try:
        return shutil.disk_usage(folder).free
    except OSError:
        return None


def usage(cfg: Config, profile: str) -> dict:
    """What the given closet takes on disk. Its own images and database; the shared model, logs and local backups."""
    sizes = image_bytes(cfg.images_dir(profile))
    sizes["database_bytes"] = database_bytes(cfg.db_path(profile))
    sizes["backups_bytes"] = folder_bytes(cfg.local_backups_dir)
    sizes["model_bytes"] = folder_bytes(cfg.models_dir)
    sizes["logs_bytes"] = folder_bytes(cfg.logs_dir)
    return {
        "items": item_count(cfg.db_path(profile)), **sizes, "total_bytes": sum(sizes.values()),
        "data_dir": str(cfg.data_dir), "free_bytes": free_bytes(cfg.data_dir),
    }
