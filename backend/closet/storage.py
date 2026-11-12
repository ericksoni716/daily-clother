"""On-demand file sizes for one closet and the folders shared by both."""
from __future__ import annotations

import os
import shutil
import sqlite3
import stat
from contextlib import closing
from pathlib import Path

from .config import Config


class _LinkedPath(Exception):
    pass


def _safe_stat(path: Path, root: Path):
    """Do not follow links or Windows reparse points, including parent folders."""
    current = root
    try:
        for part in path.relative_to(root).parts:
            current /= part
            info = current.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise _LinkedPath
        return path.lstat()
    except FileNotFoundError:
        return None


def _files(folder: Path, root: Path):
    pending = [folder]
    while pending:
        path = pending.pop()
        try:
            info = _safe_stat(path, root)
        except _LinkedPath:
            continue
        if info is None:
            continue
        if stat.S_ISREG(info.st_mode):
            yield path, info.st_size
        elif stat.S_ISDIR(info.st_mode):
            try:
                with os.scandir(path) as entries:
                    pending.extend(Path(entry.path) for entry in entries)
            except FileNotFoundError:
                pass  # An item may have been deleted during the walk.


def measure(cfg: Config, profile: str) -> dict:
    root = cfg.data_dir.resolve()
    profile_dir = root if profile == "main" else root / "demo"
    database = profile_dir / "closet.db"
    result = dict.fromkeys((
        "photos_bytes", "cutouts_bytes", "thumbnails_bytes", "database_bytes",
        "backups_bytes", "model_bytes", "logs_bytes",
    ), 0)

    # Check SQLite's companion files too: opening the database can read them.
    database_files = [database, *(profile_dir / f"closet.db{suffix}" for suffix in ("-wal", "-shm", "-journal"))]
    safe_database = True
    for path in database_files:
        try:
            info = _safe_stat(path, root)
        except _LinkedPath:
            safe_database = False
            continue
        if (info is None and path == database) or (info is not None and not stat.S_ISREG(info.st_mode)):
            safe_database = False

    count = 0
    if safe_database:
        with closing(sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)) as conn:
            count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]

    result["database_bytes"] = sum(size for path in database_files for _, size in _files(path, root))

    for path, size in _files(profile_dir / "images", root):
        if path.name.endswith(".t.webp"):
            result["thumbnails_bytes"] += size
        elif path.name.endswith(".cut.webp"):
            result["cutouts_bytes"] += size
        elif path.suffix == ".webp":
            result["photos_bytes"] += size

    for folder, key in (("backups", "backups_bytes"), ("models", "model_bytes"), ("logs", "logs_bytes")):
        result[key] = sum(size for _, size in _files(root / folder, root))

    return {
        "items": count, **result, "total_bytes": sum(result.values()),
        "data_dir": str(cfg.data_dir), "free_bytes": shutil.disk_usage(root).free,
    }
