"""Backups of the real closet to a folder the owner chooses, and restore.

A backup folder holds dated snapshots of the database (taken with SQLite's
own backup, so they are consistent even while the app is in use) and a copy
of the images, to which only new files are added. The settings file, with the
passphrase hash and sessions, is not backed up, and no API key is ever stored
where a backup could pick it up.
"""
from __future__ import annotations

import json
import logging
import shutil
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from . import db
from .config import Config
from .state import State

log = logging.getLogger("closet.backup")
SUBFOLDER = "Closet backup"
KEEP_SNAPSHOTS = 14
DUE_AFTER_SECONDS = 24 * 3600


class BackupError(RuntimeError):
    pass


def _stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def _root(folder: Path) -> Path:
    return folder / SUBFOLDER


def run_backup(cfg: Config, state: State, kind: str = "manual", folder: Path | None = None) -> dict:
    """Back up the real closet now. Records and returns the outcome; never raises."""
    folder = folder or (Path(state.get("backup_folder")) if state.get("backup_folder") else None)
    at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    result = {"at": at, "ok": False, "error": None, "folder": str(folder) if folder else None, "kind": kind}
    try:
        if folder is None:
            raise BackupError("No backup folder has been chosen yet.")
        if not folder.is_dir():
            raise BackupError(f"The backup folder {folder} is not available. Check that the drive or synced folder is connected.")
        src_db = cfg.db_path("main")
        if not src_db.exists():
            raise BackupError("There is no closet to back up yet.")
        root = _root(folder)
        snap = root / "db" / f"closet-{_stamp()}.sqlite"
        db.snapshot(src_db, snap)
        copied = 0
        src_images = cfg.images_dir("main")
        if src_images.is_dir():
            for f in src_images.rglob("*"):
                if not f.is_file() or f.suffix == ".part":
                    continue
                dest = root / "images" / f.relative_to(src_images)
                if not dest.exists() or dest.stat().st_size != f.stat().st_size:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, dest)
                    copied += 1
        snaps = sorted((root / "db").glob("closet-*.sqlite"))
        for old in snaps[:-KEEP_SNAPSHOTS]:
            old.unlink(missing_ok=True)
        (root / "manifest.json").write_text(json.dumps(
            {"last_backup": at, "snapshot": snap.name, "snapshots": [s.name for s in snaps[-KEEP_SNAPSHOTS:]],
             "data_version": db.latest_version()}, indent=1))
        result.update(ok=True, snapshot=snap.name, images_copied=copied)
    except BackupError as e:
        result["error"] = str(e)
    except Exception as e:
        log.exception("backup failed")
        result["error"] = f"The backup did not finish: {e}"
    previous = state.get("last_backup") or {}
    record = dict(result)
    if not result["ok"]:  # keep showing when the last good one was
        record["last_good"] = previous.get("at") if previous.get("ok") else previous.get("last_good")
    state.update(last_backup=record)
    return record


def last_good(state: State) -> str | None:
    last = state.get("last_backup")
    if not last:
        return None
    return last["at"] if last.get("ok") else last.get("last_good")


def is_due(state: State, now: float | None = None) -> bool:
    if not state.get("backup_folder"):
        return False
    good = last_good(state)
    if good is None:
        return True
    then = datetime.strptime(good, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp()
    return (now or time.time()) - then >= DUE_AFTER_SECONDS


def restore(cfg: Config, folder: Path, snapshot: str | None = None) -> dict:
    """Replace the real closet with a backup. The current one is moved aside, not deleted."""
    root = _root(folder) if (_root(folder)).is_dir() else folder
    snaps = sorted((root / "db").glob("closet-*.sqlite"))
    if not snaps:
        raise BackupError(f"No backup was found in {folder}.")
    chosen = (root / "db" / snapshot) if snapshot else snaps[-1]
    if not chosen.exists():
        raise BackupError(f"There is no snapshot named {snapshot} in {folder}.")
    check = db.connect(chosen)
    try:
        version = check.execute("PRAGMA user_version").fetchone()[0]
        items = check.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    finally:
        check.close()
    if version > db.latest_version():
        raise BackupError("This backup was made by a newer version of the program. Download the latest version to restore it.")
    aside = None
    live_db, live_images = cfg.db_path("main"), cfg.images_dir("main")
    if live_db.exists() or live_images.exists():
        aside = cfg.data_dir / f"replaced-{_stamp()}"
        aside.mkdir(parents=True)
        for p in (live_db, live_db.with_name(live_db.name + "-wal"), live_db.with_name(live_db.name + "-shm"), live_images):
            if p.exists():
                shutil.move(str(p), str(aside / p.name))
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(chosen, live_db)
    if (root / "images").is_dir():
        shutil.copytree(root / "images", live_images)
    db.migrate(live_db, cfg.local_backups_dir)
    return {"snapshot": chosen.name, "items": items, "previous_moved_to": str(aside) if aside else None}


class Scheduler:
    """Backs up once a day while the program runs, and catches up after it was off."""

    def __init__(self, cfg: Config, state: State, check_every: float = 1800):
        self.cfg, self.state, self.check_every = cfg, state, check_every
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="backup-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def tick(self) -> dict | None:
        if is_due(self.state):
            return run_backup(self.cfg, self.state, kind="nightly")
        return None

    def _loop(self) -> None:
        self._stop.wait(20)  # let startup finish first
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("backup scheduler error")
            self._stop.wait(self.check_every)
