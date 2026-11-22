"""The background queue that turns uploaded photos into cutouts.

Jobs live in the database, so nothing is lost if the program is closed:
unfinished work is picked up again on the next start. Uploads never wait for
this queue, and jobs wait (without failing) until the model file is ready.
Once a cutout is ready the item is queued for tagging (`tagjobs.py`), in the
same table, unless Claude has described it since that photo was added (a shoe's
photo that became its main one once its photos were sorted, `shoeviews.promote`).
A shoe whose cutout is ready waits to be traced (`tracejobs.py`): this worker
traces waiting shoes once no cutout is left to make. A cutout made while the
second background model was not there yet is looked at again once it is, and
made again when the second model would change it (`recheck`). An item Claude
described from an earlier cutout of the same photo is described again from the
new one (`redescribe`). A shoe sorted before whose main photo is its inner side
takes its outer side photo as its main one, once (`shoeviews.catch_up`).
"""
from __future__ import annotations

import logging
import shutil
import threading
from collections.abc import Callable
from pathlib import Path

from PIL import Image

from . import db, failures, images, patjobs, shoeviews, tagjobs, tracejobs
from .config import Config
from .state import State

log = logging.getLogger("closet.jobs")
MAX_ATTEMPTS = 3
FAILED = ("The background could not be removed from this photo. You can try again, or retake it "
          "against a plainer background.")

Cutter = Callable[[Image.Image], Image.Image]  # photo -> RGBA cutout

# an item (`i`) Claude described from its photo before that photo's latest cutout was made: what Claude saw was the
# older cutout (see-through, or with the bed it lay on), so its colour, pattern and cloth may have come from that
OLDER_CUTOUT = ("i.tag_photo_id IS NOT NULL AND i.tagged_at IS NOT NULL AND EXISTS (SELECT 1 FROM jobs c "
                "WHERE c.kind = 'cutout' AND c.state = 'done' AND c.photo_id = i.tag_photo_id AND c.updated_at > i.tagged_at)")


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


def run_one(conn, images_dir: Path, cutter: Cutter, tag: bool = True, second: bool = True) -> bool:
    """Process the oldest queued cutout job. Returns False when there is none.

    With `tag`, a finished cutout queues the item for tagging (not in the demo closet, which is never sent to Claude).
    `second` says whether the second background model was there for the cutter to ask; a cutout made without it is
    looked at again once it comes (`recheck`).
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
    conn.execute("UPDATE photos SET cutout_path = ?, cutout_thumb_path = ?, cutout_second = ? WHERE id = ?",
                 (rel, rel_thumb, int(second), job["photo_id"]))
    conn.execute("UPDATE jobs SET state = 'done', error = NULL, updated_at = ? WHERE id = ?", (t, job["id"]))
    conn.execute("UPDATE items SET cutout_state = 'ready', cutout_error = NULL, updated_at = ? WHERE id = ?", (t, job["item_id"]))
    # Claude's landmarks are points in the old cutout's own pixels: they are asked for again with the new one
    conn.execute("UPDATE items SET landmarks = NULL WHERE id = ?", (job["item_id"],))
    if tag and (not _described_since(conn, job["item_id"], photo) or _described_from_older_cutout(conn, job["item_id"])):
        tagjobs.enqueue(conn, job["item_id"])   # a new photo, or the photo Claude described cut out again
    elif tag:   # described already: its pattern is measured again, from the new cutout (never in the demo closet)
        patjobs.mark(conn, job["item_id"])
    tracejobs.mark(conn, job["item_id"])   # a shoe's new photo is traced again
    conn.execute("COMMIT")
    return True


def remeasure(conn) -> int:
    """Plaids older measuring code found no repeat in (`patjobs.stale`): the cutout of each is made again (it may
    have kept the bedding the garment lay on, which the two models together now leave out) and its pattern is
    then measured again from it. Returns how many."""
    conn.execute("BEGIN IMMEDIATE")
    found = patjobs.stale(conn)
    for item_id in found:
        photo = conn.execute("SELECT id FROM photos WHERE item_id = ? AND kind = 'front' ORDER BY created_at LIMIT 1",
                             (item_id,)).fetchone()
        busy = conn.execute("SELECT 1 FROM jobs WHERE kind = 'cutout' AND item_id = ? AND state IN ('queued', 'running')",
                            (item_id,)).fetchone()
        if photo is not None and busy is None:
            enqueue_cutout(conn, item_id, photo["id"])
    conn.execute("COMMIT")
    return len(found)


RECHECK_BATCH = 20   # cutouts looked at between two rounds of the queue, so a new photo never waits long behind them


def recheck(conn, images_dir: Path, limit: int = RECHECK_BATCH) -> int:
    """Cutouts made while the second background model was not there (it was still downloading, its download had
    failed, or Nines had none yet), looked at once it is: each is made again when the second model would change
    it, that is when the first model's cutout is see-through in the shape of its own pattern, runs out of the
    photo's frame or keeps two kinds of surface (`masks.doubtful_cutout`). Each is looked at once; at most `limit`
    per call, oldest first. Returns how many were looked at (0: none left)."""
    rows = conn.execute(
        "SELECT p.id, p.item_id, p.cutout_path, p.original_path, p.width, p.height FROM photos p "
        "JOIN items i ON i.id = p.item_id "
        "WHERE p.kind = 'front' AND p.cutout_path IS NOT NULL AND coalesce(p.cutout_second, 0) = 0 "
        "AND i.cutout_state = 'ready' AND i.status = 'active' ORDER BY p.created_at, p.id LIMIT ?", (limit,)).fetchall()
    if not rows:
        return 0
    from .patterns import masks  # OpenCV: loaded only once a cutout is made
    for row in rows:
        try:
            size = (row["width"], row["height"])
            if not all(size):
                with Image.open(images_dir / row["original_path"]) as photo:
                    size = photo.size
            with Image.open(images_dir / row["cutout_path"]) as cut:
                again = masks.doubtful_cutout(cut, size)
        except (OSError, ValueError) as e:   # a picture that cannot be read is left as it is
            log.warning("could not look at the cutout of photo %s again: %s", row["id"], type(e).__name__)
            again = False
        conn.execute("BEGIN IMMEDIATE")
        still = conn.execute(   # not replaced, deleted or queued since it was read
            "SELECT 1 FROM photos p JOIN items i ON i.id = p.item_id WHERE p.id = ? AND p.cutout_path = ? "
            "AND i.cutout_state = 'ready'", (row["id"], row["cutout_path"])).fetchone()
        if still is not None:
            if again:
                log.info("the cutout of item %s was made without the second background model: making it again",
                         row["item_id"])
                enqueue_cutout(conn, row["item_id"], row["id"])
            conn.execute("UPDATE photos SET cutout_second = 1 WHERE id = ?", (row["id"],))
        conn.execute("COMMIT")
    return len(rows)


def redescribe(conn) -> int:
    """Items Claude described from a cutout that was made again afterwards (the second background model redid a
    see-through one, or a plaid's was made again to leave out the bedding): each is described again, once, from the
    cutout it has now. Fields and details the owner set stay theirs. Archived items wait until they are back.
    Returns how many were queued."""
    conn.execute("BEGIN IMMEDIATE")
    found = [r["id"] for r in conn.execute(
        f"SELECT i.id FROM items i WHERE i.status = 'active' AND i.tag_state = 'done' AND i.cutout_state = 'ready' "
        f"AND {OLDER_CUTOUT}").fetchall()]
    queued = sum(tagjobs.enqueue(conn, item_id) for item_id in found)
    conn.execute("COMMIT")
    if queued:
        log.info("%s items described from an older cutout are described again", queued)
    return queued


def _described_from_older_cutout(conn, item_id: str) -> bool:
    return conn.execute(f"SELECT 1 FROM items i WHERE i.id = ? AND {OLDER_CUTOUT}", (item_id,)).fetchone() is not None


def _described_since(conn, item_id: str, photo) -> bool:
    """Claude has described the item since this photo was added, so it has seen the photo already: a shoe's photo
    that became its main one once its photos were sorted is cut out, not described again. A new or retaken photo
    always is."""
    row = conn.execute("SELECT tagged_at FROM items WHERE id = ?", (item_id,)).fetchone()
    return row is not None and bool(row["tagged_at"]) and row["tagged_at"] >= photo["created_at"]


class Worker:
    """One thread that drains the active closet's queue whenever the model is ready."""

    def __init__(self, cfg: Config, state: State, is_ready: Callable[[], bool], cutter: Cutter,
                 on_done: Callable[[], None] = lambda: None, tracer: tracejobs.Tracer | None = None,
                 second: Callable[[], bool] | None = None):
        self.cfg, self.state, self.is_ready, self.cutter, self.on_done = cfg, state, is_ready, cutter, on_done
        self.tracer = tracer   # None: shoes are not traced (tests that do not ask for it)
        # whether the second background model is ready; None: there is none to wait for (a cutter standing in)
        self.second = second
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
        waiting to be traced, one at a time, so a new photo's cutout never waits for a trace; then, a few at a
        time, the cutouts made before the second background model was there (`recheck`)."""
        done = again = 0
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
            if profile != "demo":
                remeasure(conn)
                again = redescribe(conn)   # described from a cutout made again since: described again
                shoeviews.catch_up(conn)   # a shoe sorted before whose picture is its inner side: the outer side
            images_dir = self.cfg.images_dir(profile)
            while not self._stop.is_set() and self.is_ready():
                second = self.second is None or self.second()
                if run_one(conn, images_dir, self.cutter, tag=profile != "demo", second=second):
                    done += 1
                elif self.tracer is None or tracejobs.run_one(conn, images_dir, self.tracer) == "empty":
                    if self.second is None or not second or not recheck(conn, images_dir):
                        break
        finally:
            conn.close()
        if done or again:
            self.on_done()   # wake the tagging worker for the cutouts just made, or the items to describe again
        return done
