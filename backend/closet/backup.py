"""Backups of the real closet to a folder the owner chooses, and restore.

A backup folder holds dated snapshots of the database (taken with SQLite's
own backup, so they are consistent even while the app is in use), each with a
list of the images it had, and one store of images named by their content
(SHA-256), shared by all snapshots, so an unchanged image is kept once and an
older snapshot still has its own images. Backups made before that kept one
`images` folder for all snapshots; they are still restored. The settings file,
with the passphrase hash and sessions, is not backed up, and no API key is ever
stored where a backup could pick it up.

A restore writes a journal of its moves before making the first one, so a
restore cut short (a power cut, a forced quit) is finished or undone the next
time the program starts, never left half done.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from . import db
from .config import Config
from .state import State

log = logging.getLogger("closet.backup")
SUBFOLDER = "Closet backup"
KEEP_SNAPSHOTS = 14
DUE_AFTER_SECONDS = 24 * 3600
CONTENT = "content"              # the images, each named by its SHA-256, in folders by its first two letters
OLD_IMAGES = "images"            # the images of backups made before they were kept by content
JOURNAL = "restore-journal.json"  # in the data folder while a restore moves files
NOTICE = "restore-notice.json"    # what was done about an interrupted restore, until the owner has seen it
MOVE_TRIES = 8                    # Windows refuses to move a file another program has open: try again for ~9 s
_HEX = re.compile(r"[0-9a-f]{64}")
_backing_up = threading.Lock()


class BackupError(RuntimeError):
    pass


class RecoveryError(RuntimeError):
    """An interrupted restore could not be finished or undone yet; its journal is kept for the next start."""


def _stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def _root(folder: Path) -> Path:
    return folder / SUBFOLDER


def _image_paths(database: Path) -> list[str]:
    conn = db.connect(database)
    try:
        paths = [p for row in conn.execute("SELECT original_path, thumb_path, cutout_path, cutout_thumb_path FROM photos")
                 for p in row if p]
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'source_photos'").fetchone():
            paths.extend(p for row in conn.execute("SELECT original_path, thumb_path FROM source_photos") for p in row if p)
        return paths
    finally:
        conn.close()


def _check_images(database: Path, present: Callable[[str], bool]) -> None:
    if any(not present(p) for p in _image_paths(database)):
        raise BackupError("The backup is missing an image. Keep your current closet and try backing up again.")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _blob(root: Path, digest: str) -> Path:
    return root / CONTENT / digest[:2] / digest


def _image_list(snap: Path) -> Path:
    """The list of the images a snapshot had, beside it; a snapshot without one is in the old layout."""
    return snap.with_suffix(".json")


def _relative(rel: object) -> PurePosixPath:
    """A relative path that stays inside the folder it is read against, or ValueError."""
    if not isinstance(rel, str) or "\\" in rel or ":" in rel:
        raise ValueError(f"not a relative path: {rel!r}")
    p = PurePosixPath(rel)
    if p.is_absolute() or not p.parts or any(part in ("", ".", "..") for part in p.parts):
        raise ValueError(f"not a relative path: {rel!r}")
    return p


def _read_image_list(path: Path) -> dict[str, str]:
    images = json.loads(path.read_text(encoding="utf-8"))["images"]
    if not isinstance(images, dict):
        raise ValueError("no list of images")
    for rel, digest in images.items():
        _relative(rel)
        if not isinstance(digest, str) or not _HEX.fullmatch(digest):
            raise ValueError(f"not a SHA-256: {digest!r}")
    return images


@contextmanager
def _one_backup_at_a_time(cfg: Config) -> Iterator[None]:
    """A backup started from the command line may meet the nightly one: one waits, so neither removes images the
    other is about to list."""
    with _backing_up:
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        with open(cfg.data_dir / "backup.lock", "a+b") as f:
            if sys.platform == "win32":
                import msvcrt
                while True:
                    try:
                        f.seek(0)
                        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)   # gives up after 10 s: wait on
                        break
                    except OSError:
                        continue
                try:
                    yield
                finally:
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(f, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)


def _store_images(src_images: Path, root: Path, staged: Path) -> tuple[dict[str, str], int]:
    """Adds the closet's images that the backup does not have yet to its store. Returns {image: SHA-256}, and how
    many were copied."""
    images: dict[str, str] = {}
    copied = 0
    if not src_images.is_dir():
        return images, copied
    for f in sorted(src_images.rglob("*")):
        if not f.is_file() or f.suffix == ".part":
            continue
        digest = _sha256(f)
        if not _blob(root, digest).is_file():
            part = staged / "image.part"
            shutil.copy2(f, part)
            digest = _sha256(part)   # what was copied, should the image have changed meanwhile
            blob = _blob(root, digest)
            if not blob.is_file():
                blob.parent.mkdir(parents=True, exist_ok=True)
                part.replace(blob)
                copied += 1
        images[f.relative_to(src_images).as_posix()] = digest
    return images, copied


def _prune(root: Path) -> list[Path]:
    """Keeps the newest snapshots, then the images that one of them still needs. Returns the snapshots kept."""
    snaps = sorted((root / "db").glob("closet-*.sqlite"))
    for old in snaps[:-KEEP_SNAPSHOTS]:
        old.unlink(missing_ok=True)
        _image_list(old).unlink(missing_ok=True)
    kept = snaps[-KEEP_SNAPSHOTS:]
    for listed in (root / "db").glob("closet-*.json"):
        if not listed.with_suffix(".sqlite").exists():
            listed.unlink(missing_ok=True)
    needed: set[str] = set()
    old_layout = False
    for snap in kept:
        listed = _image_list(snap)
        if not listed.exists():
            old_layout = True
            continue
        try:
            needed.update(_read_image_list(listed).values())
        except (OSError, ValueError, KeyError, TypeError):
            log.warning("the image list of %s cannot be read; no image is removed from the backup", snap.name)
            return kept
    if not old_layout and (root / OLD_IMAGES).is_dir():
        shutil.rmtree(root / OLD_IMAGES)
    if (root / CONTENT).is_dir():
        for shard in (root / CONTENT).iterdir():
            if not shard.is_dir():
                continue
            for blob in shard.iterdir():
                if blob.is_file() and _HEX.fullmatch(blob.name) and blob.name not in needed:
                    blob.unlink(missing_ok=True)
            if not any(shard.iterdir()):
                shard.rmdir()
    return kept


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
        with _one_backup_at_a_time(cfg):
            root = _root(folder)
            snap = root / "db" / f"closet-{_stamp()}.sqlite"
            snap.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix=".backup-", dir=root) as staging:
                staged = Path(staging)
                db.snapshot(src_db, staged / snap.name)
                images, copied = _store_images(cfg.images_dir("main"), root, staged)
                _check_images(staged / snap.name, lambda p: p in images and _blob(root, images[p]).is_file())
                (staged / "images.json").write_text(json.dumps({"snapshot": snap.name, "images": images}, indent=1,
                                                               sort_keys=True), encoding="utf-8")
                (staged / "images.json").replace(_image_list(snap))   # the list first: a snapshot never lacks one
                (staged / snap.name).replace(snap)
            kept = _prune(root)   # only now that the new snapshot is in place
            (root / "manifest.json").write_text(json.dumps(
                {"last_backup": at, "snapshot": snap.name, "snapshots": [s.name for s in kept],
                 "images": CONTENT, "data_version": db.latest_version()}, indent=1))
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
    recover(cfg)   # a restore cut short before this one is finished or undone first
    root = _root(folder) if (_root(folder)).is_dir() else folder
    snaps = sorted((root / "db").glob("closet-*.sqlite"))
    if not snaps:
        raise BackupError(f"No backup was found in {folder}.")
    chosen = (root / "db" / snapshot) if snapshot else snaps[-1]
    if (snapshot and Path(snapshot).name != snapshot) or not chosen.exists():
        raise BackupError(f"There is no snapshot named {snapshot} in {folder}.")
    live_db, live_images = cfg.db_path("main"), cfg.images_dir("main")
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".restore-", dir=cfg.data_dir) as staging:
        staged = Path(staging)
        staged_db, staged_images = staged / live_db.name, staged / live_images.name
        db.snapshot(chosen, staged_db)
        check = db.connect(staged_db)
        try:
            version = check.execute("PRAGMA user_version").fetchone()[0]
            items = check.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        finally:
            check.close()
        if version > db.latest_version():
            raise BackupError("This backup was made by a newer version of the program. Download the latest version to restore it.")
        _stage_images(root, chosen, staged_images)
        db.migrate(staged_db, cfg.local_backups_dir)
        _check_images(staged_db, lambda p: (staged_images / p).is_file())
        aside = _install(cfg, staged, [staged_db, staged_images], chosen.name)
    return {"snapshot": chosen.name, "items": items, "previous_moved_to": str(aside) if aside else None}


def _stage_images(root: Path, snap: Path, dest: Path) -> None:
    """Copies the images the snapshot had into `dest`, each checked against its SHA-256."""
    listed = _image_list(snap)
    if not listed.exists():   # made before images were kept by content: the one images folder
        if (root / OLD_IMAGES).is_dir():
            shutil.copytree(root / OLD_IMAGES, dest)
        return
    try:
        images = _read_image_list(listed)
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise BackupError(f"The list of images in this backup cannot be read ({e}). Choose another snapshot.") from e
    dest.mkdir()
    for rel, digest in sorted(images.items()):
        blob = _blob(root, digest)
        if not blob.is_file():
            raise BackupError("The backup is missing an image. Keep your current closet and try backing up again.")
        target = dest.joinpath(*_relative(rel).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(blob, target)
        if _sha256(target) != digest:
            raise BackupError("An image in the backup is damaged. Keep your current closet and choose another snapshot.")


# ---------------------------------------------------------------- the restore journal

def _retrying(action: Callable[[], object]) -> None:
    """Windows refuses to move or replace a file another program has open (an antivirus, a search indexer, a
    picture viewer) for as long as it is open: try again for a while before giving up."""
    for attempt in range(MOVE_TRIES):
        try:
            action()
            return
        except PermissionError:
            if attempt == MOVE_TRIES - 1:
                raise
            time.sleep(0.25 * (attempt + 1))


def _move(src: Path, dst: Path) -> None:
    """One rename. Nothing is ever moved onto something that exists: Windows cannot replace a folder, and a file in
    use cannot be replaced."""
    _retrying(lambda: src.replace(dst))


def _fsync_dir(folder: Path) -> None:
    if os.name == "nt":   # Windows keeps a folder's entries itself, and cannot open a folder to flush it
        return
    try:
        fd = os.open(folder, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _flush(path: Path) -> None:
    """Makes sure a staged file or folder is on the disk, not only in memory, before the journal relies on it."""
    files = [f for f in path.rglob("*") if f.is_file()] if path.is_dir() else [path]
    for f in files:
        try:
            h = open(f, "r+b")   # Windows flushes only a file open for writing
        except PermissionError:
            h = open(f, "rb")    # read-only: POSIX flushes it all the same
        with h:
            try:
                os.fsync(h.fileno())
            except OSError:
                pass             # the journal still checks every new file before finishing a restore from it
    for folder in ({f.parent for f in files} | {path.parent}):
        _fsync_dir(folder)


def _write_json(path: Path, data: dict) -> None:
    """Written whole or not at all: to a file beside it, flushed to the disk, then renamed over it."""
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
        f.flush()
        os.fsync(f.fileno())
    _retrying(lambda: os.replace(tmp, path))
    _fsync_dir(path.parent)


def _fingerprint(path: Path) -> dict:
    """What a new file must be for a restore to be finished from it: the database's size and SHA-256, each image's size."""
    if path.is_dir():
        return {"files": {f.relative_to(path).as_posix(): f.stat().st_size for f in sorted(path.rglob("*")) if f.is_file()}}
    return {"size": path.stat().st_size, "sha256": _sha256(path)}


def _in_data(cfg: Config, rel: object) -> Path:
    return cfg.data_dir.joinpath(*_relative(rel).parts)


def _install(cfg: Config, staged: Path, new: list[Path], snapshot: str) -> Path | None:
    """Moves the current closet aside and the staged one in, keeping a journal of every move. Returns the folder
    the current closet went to."""
    live_db = cfg.db_path("main")
    current = [p for p in (live_db, live_db.with_name(live_db.name + "-wal"), live_db.with_name(live_db.name + "-shm"),
                           cfg.images_dir("main")) if p.exists()]
    new = [p for p in new if p.exists()]
    for p in new:
        _flush(p)
    aside = Path(tempfile.mkdtemp(prefix=f"replaced-{_stamp()}-", dir=cfg.data_dir)) if current else None

    def rel(p: Path) -> str:
        return p.relative_to(cfg.data_dir).as_posix()

    steps = [{"kind": "aside", "from": rel(p), "to": rel(aside / p.name), "done": False} for p in current if aside]
    steps += [{"kind": "install", "from": rel(p), "to": rel(cfg.data_dir / p.name), "check": _fingerprint(p),
               "done": False} for p in new]
    plan = {"version": 1, "started": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "snapshot": snapshot,
            "staging": rel(staged), "aside": rel(aside) if aside else None, "steps": steps}
    journal = cfg.data_dir / JOURNAL
    _write_json(journal, plan)
    try:
        _forward(cfg, plan, journal)
    except BaseException:
        try:
            _back(cfg, plan)
            journal.unlink(missing_ok=True)
        except Exception:
            log.exception("the restore could not be undone at once; it will be put right when Closet next starts")
        raise
    journal.unlink()
    _fsync_dir(cfg.data_dir)
    return aside


def _forward(cfg: Config, plan: dict, journal: Path) -> None:
    """Makes every move not made yet, marking each in the journal once made."""
    for step in plan["steps"]:
        src, dst = _in_data(cfg, step["from"]), _in_data(cfg, step["to"])
        if step["kind"] == "aside":
            if src.exists() and not dst.exists():
                _move(src, dst)
        elif src.exists():
            if dst.exists():
                raise OSError(f"{dst.name} is in the way of the restored {src.name}")
            _move(src, dst)
        if not step["done"]:
            step["done"] = True
            _write_json(journal, plan)


def _installed(cfg: Config, plan: dict, step: dict) -> bool:
    """Whether an install step's file is in place: gone from the staging folder, in the closet, and what was there
    before moved aside (or nothing was there)."""
    src, dst = _in_data(cfg, step["from"]), _in_data(cfg, step["to"])
    if src.exists() or not dst.exists():
        return False
    before = [s for s in plan["steps"] if s["kind"] == "aside" and s["from"] == step["to"]]
    return all(_in_data(cfg, s["to"]).exists() for s in before)


def _complete(cfg: Config, plan: dict) -> bool:
    """Whether every new file is there, whole, in the staging folder or already in place."""
    for step in plan["steps"]:
        if step["kind"] != "install":
            continue
        src = _in_data(cfg, step["from"])
        if src.exists():
            where = src
        elif _installed(cfg, plan, step):
            where = _in_data(cfg, step["to"])
        else:
            return False
        if _fingerprint(where) != step["check"]:
            return False
    return True


def _back(cfg: Config, plan: dict) -> None:
    """Undoes every move made, last first: the new files go back to the staging folder, the current closet back in."""
    for step in reversed(plan["steps"]):
        src, dst = _in_data(cfg, step["from"]), _in_data(cfg, step["to"])
        if step["kind"] == "install":
            if _installed(cfg, plan, step):
                src.parent.mkdir(parents=True, exist_ok=True)
                _move(dst, src)
        elif dst.exists():
            if src.exists():
                raise OSError(f"{src.name} is in the way of the closet from before the restore")
            _move(dst, src)


def _read_journal(cfg: Config, journal: Path) -> dict:
    plan = json.loads(journal.read_text(encoding="utf-8"))
    if not isinstance(plan, dict) or plan.get("version") != 1 or not isinstance(plan.get("steps"), list):
        raise ValueError("not a restore journal")
    _in_data(cfg, plan["staging"])
    for step in plan["steps"]:
        if not isinstance(step, dict) or step.get("kind") not in ("aside", "install"):
            raise ValueError("not a step of a restore")
        _in_data(cfg, step["from"])
        _in_data(cfg, step["to"])
        if step["kind"] == "install" and not isinstance(step.get("check"), dict):
            raise ValueError("a new file without its fingerprint")
    return plan


FINISHED = "A restore was interrupted; Closet finished it when it started again, so your closet is the one from the backup."
UNDONE = "A restore was interrupted; your closet was put back as it was before the restore."
UNREADABLE = ("A restore was interrupted, and Closet could not read its notes on how far it had got, so it moved "
              "nothing. If your closet does not look right, the closet from before the restore is in the newest "
              "\u201creplaced-\u2026\u201d folder in Closet's folder.")


def recover(cfg: Config) -> dict | None:
    """Finishes or undoes a restore that was cut short. Run on every start, before the closet's database is opened.

    The restore is finished when every new file is there and whole, and undone otherwise; either way the closet is
    all the one from before or all the one from the backup. Returns the notice left for the owner, or None when
    there was nothing to do. Raises RecoveryError when files cannot be moved yet (the journal is kept)."""
    journal = cfg.data_dir / JOURNAL
    tmp = journal.with_name(journal.name + ".tmp")
    if not journal.exists():
        if tmp.exists():
            log.warning("a restore stopped while writing its journal, before it moved anything; the closet is as it was")
            tmp.unlink(missing_ok=True)
        for staging in cfg.data_dir.glob(".restore-*") if cfg.data_dir.is_dir() else []:
            shutil.rmtree(staging, ignore_errors=True)   # what a restore cut short before its journal had staged
        return None
    try:
        plan = _read_journal(cfg, journal)
    except (OSError, ValueError, KeyError, TypeError) as e:
        kept = journal.with_name(f"restore-journal.unreadable-{_stamp()}.json")
        _retrying(lambda: os.replace(journal, kept))
        tmp.unlink(missing_ok=True)
        log.error("the journal of an interrupted restore cannot be read (%s); nothing was moved, it is kept as %s",
                  e, kept.name)
        return _tell(cfg, "unreadable", UNREADABLE)
    try:
        if _complete(cfg, plan):
            try:
                _forward(cfg, plan, journal)
                outcome = "finished"
            except OSError:
                log.exception("an interrupted restore could not be finished; undoing it")
                _back(cfg, plan)
                outcome = "undone"
        else:
            _back(cfg, plan)
            outcome = "undone"
    except OSError as e:
        log.exception("an interrupted restore could not be finished or undone")
        raise RecoveryError(f"A restore was interrupted, and Closet could not put your closet right yet ({e}). Close any "
                            "program that may be using Closet's folder, then start Closet again.") from e
    journal.unlink()
    tmp.unlink(missing_ok=True)
    shutil.rmtree(_in_data(cfg, plan["staging"]), ignore_errors=True)
    _fsync_dir(cfg.data_dir)
    log.warning("an interrupted restore of %s was %s; the closet from before it is in %s", plan.get("snapshot"),
                outcome, plan.get("aside"))
    return _tell(cfg, outcome, FINISHED if outcome == "finished" else UNDONE)


def _tell(cfg: Config, outcome: str, message: str) -> dict:
    notice = {"at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "outcome": outcome, "message": message}
    _write_json(cfg.data_dir / NOTICE, notice)
    return notice


def restore_notice(cfg: Config) -> dict | None:
    """What was done about an interrupted restore, until the owner has seen it."""
    try:
        notice = json.loads((cfg.data_dir / NOTICE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return notice if isinstance(notice, dict) and isinstance(notice.get("message"), str) else None


def dismiss_notice(cfg: Config) -> None:
    (cfg.data_dir / NOTICE).unlink(missing_ok=True)


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
