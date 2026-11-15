"""The background queue that turns uploaded photos into cutouts.

Jobs live in the database, so nothing is lost if the program is closed:
unfinished work is picked up again on the next start. Uploads never wait for
this queue, and jobs wait (without failing) until the model file is ready.
Once a cutout is ready the item is queued for tagging (`tagjobs.py`), in the
same table. A shoe whose cutout is ready waits to be traced (`tracejobs.py`):
this worker traces waiting shoes once no cutout is left to make.
"""
from __future__ import annotations

import logging
import shutil
import threading
from collections.abc import Callable
from pathlib import Path

from PIL import Image

from . import db, failures, images, tagjobs, tracejobs
from .config import Config
from .state import State

log = logging.getLogger("closet.jobs")
MAX_ATTEMPTS = 3
FAILED = ("The background could not be removed from this photo. You can try again, or retake it "
          "against a plainer background.")

Cutter = Callable[[Image.Image], Image.Image]  # photo -> RGBA cutout


def enqueue_cutout(conn, item_id: str, photo_id: str) -> None:
    t = db.now()
    conn.execute("INSERT INTO jobs (kind, item_id, photo_id, created_at, updated_at) VALUES ('cutout', ?, ?, ?, ?)",
                 (item_id, photo_id, t, t))
    conn.execute("UPDATE items SET cutout_state = 'pending', cutout_error = NULL, updated_at = ? WHERE id = ?", (t, item_id))


def requeue_interrupted(conn) -> int:
    """Recover both queues at startup, respecting their attempt limits."""
    return recover(conn) + tagjobs.recover(conn)


def recover(conn) -> int:
    """Recover interrupted cutouts only; the tagging worker may be running."""
    t = db.now()
    conn.execute("BEGIN IMMEDIATE")
    stale = conn.execute("SELECT id, item_id, attempts, error FROM jobs WHERE kind = 'cutout' AND state = 'running'").fetchall()
    for job in stale:
        if job["attempts"] >= MAX_ATTEMPTS:
            conn.execute("UPDATE jobs SET state = 'failed', updated_at = ? WHERE id = ?", (t, job["id"]))
            conn.execute("UPDATE items SET cutout_state = 'failed', cutout_error = ?, updated_at = ? WHERE id = ?",
                         (FAILED, t, job["item_id"]))
            failures.report(conn, job["item_id"], "cutout", job["error"])
        else:
            conn.execute("UPDATE jobs SET state = 'queued', updated_at = ? WHERE id = ?", (t, job["id"]))
            conn.execute("UPDATE items SET cutout_state = 'pending', updated_at = ? WHERE id = ?", (t, job["item_id"]))
    conn.execute("COMMIT")
    return len(stale)


def pending_count(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM jobs WHERE kind = 'cutout' AND state IN ('queued', 'running')").fetchone()[0]


def run_one(conn, images_dir: Path, cutter: Cutter, tag: bool = True) -> bool:
    """Process the oldest queued cutout job. Returns False when there is none.

    With `tag`, a finished cutout queues the item for tagging (not in the demo closet, which is never sent to Claude).
    """
    conn.execute("BEGIN IMMEDIATE")
    job = conn.execute("SELECT * FROM jobs WHERE kind = 'cutout' AND state = 'queued' ORDER BY id LIMIT 1").fetchone()
    if job is None:
        conn.execute("COMMIT")
        return False
    t = db.now()
    conn.execute("UPDATE jobs SET state = 'running', attempts = attempts + 1, updated_at = ? WHERE id = ?", (t, job["id"]))
    conn.execute("UPDATE items SET cutout_state = 'processing', updated_at = ? WHERE id = ?", (t, job["item_id"]))
    conn.execute("COMMIT")
    attempts = job["attempts"] + 1
    try:
        photo = conn.execute("SELECT * FROM photos WHERE id = ?", (job["photo_id"],)).fetchone()
        if photo is None:
            raise LookupError("the photo for this job no longer exists")
        with Image.open(images_dir / photo["original_path"]) as im:
            cut = cutter(im.convert("RGB"))
        rel, rel_thumb = images.store_cutout(cut, images_dir, job["item_id"], job["photo_id"])
    except Exception as e:  # any failure is recorded against the job, never lost
        log.warning("cutout job %s failed (attempt %s): %s", job["id"], attempts, type(e).__name__)
        t = db.now()
        if attempts < MAX_ATTEMPTS:
            conn.execute("UPDATE jobs SET state = 'queued', error = ?, updated_at = ? WHERE id = ?", (failures.kept(conn, str(e)), t, job["id"]))
            conn.execute("UPDATE items SET cutout_state = 'pending', updated_at = ? WHERE id = ?", (t, job["item_id"]))
        else:
            conn.execute("UPDATE jobs SET state = 'failed', error = ?, updated_at = ? WHERE id = ?", (failures.kept(conn, str(e)), t, job["id"]))
            conn.execute("UPDATE items SET cutout_state = 'failed', cutout_error = ?, updated_at = ? WHERE id = ?",
                         (FAILED, t, job["item_id"]))
            failures.report(conn, job["item_id"], "cutout", str(e))
        return True
    t = db.now()
    conn.execute("BEGIN IMMEDIATE")
    if conn.execute("SELECT 1 FROM items WHERE id = ?", (job["item_id"],)).fetchone() is None:
        conn.execute("COMMIT")   # deleted while its cutout ran: what was just written goes too
        shutil.rmtree(images_dir / job["item_id"], ignore_errors=True)
        return True
    conn.execute("UPDATE photos SET cutout_path = ?, cutout_thumb_path = ? WHERE id = ?", (rel, rel_thumb, job["photo_id"]))
    conn.execute("UPDATE jobs SET state = 'done', error = NULL, updated_at = ? WHERE id = ?", (t, job["id"]))
    conn.execute("UPDATE items SET cutout_state = 'ready', cutout_error = NULL, updated_at = ? WHERE id = ?", (t, job["item_id"]))
    if tag:
        tagjobs.enqueue(conn, job["item_id"])
    tracejobs.mark(conn, job["item_id"])   # a shoe's new photo is traced again
    conn.execute("COMMIT")
    return True


class Worker:
    """One thread that drains the active closet's queue whenever the model is ready."""

    def __init__(self, cfg: Config, state: State, is_ready: Callable[[], bool], cutter: Cutter,
                 on_done: Callable[[], None] = lambda: None, tracer: tracejobs.Tracer | None = None):
        self.cfg, self.state, self.is_ready, self.cutter, self.on_done = cfg, state, is_ready, cutter, on_done
        self.tracer = tracer   # None: shoes are not traced (tests that do not ask for it)
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="cutout-worker", daemon=True)
        self._thread.start()

    def wake(self) -> None:
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=10)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.drain()
            except Exception:  # keep the worker alive; the next wake retries
                log.exception("cutout worker error")
            self._wake.wait(timeout=30)
            self._wake.clear()

    def drain(self) -> int:
        """Run queued jobs until none are left (or the model is not ready): the cutouts first, then the shoes
        waiting to be traced, one at a time, so a new photo's cutout never waits for a trace."""
        done = 0
        if not self.is_ready():
            return done
        profile = self.state.get("profile")
        path = self.cfg.db_path(profile)
        if not path.exists():
            return done
        conn = db.connect(path)
        try:
            recover(conn)
            if self.tracer is not None:
                tracejobs.recover(conn)
                if profile != "demo":   # the demo's traces were made in advance, without photos to trace again
                    tracejobs.stale(conn)
            while not self._stop.is_set() and self.is_ready():
                if run_one(conn, self.cfg.images_dir(profile), self.cutter, tag=profile != "demo"):
                    done += 1
                elif self.tracer is None or tracejobs.run_one(conn, self.cfg.images_dir(profile), self.tracer) == "empty":
                    break
        finally:
            conn.close()
        if done:
            self.on_done()   # wake the tagging worker for the cutouts just made
        return done
