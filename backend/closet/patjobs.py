"""Measuring an item's pattern from its photo, in the background.

An item whose pattern is stripes, plaid, floral, camouflage or another print waits to be measured once it has
a cutout and Claude has described it (`tagjobs.apply_answer` marks it), and again when the owner changes its
pattern. The worker takes one waiting item at a time: for a top it first asks Claude where the buttons, neck,
hem, shoulders and underarms are (`tagger.landmarks`, through the same routes and monthly limit as describing;
without an answer the pattern is still measured, only not placed), then measures (`patterns.measure`, which
can take a minute or two on a large photo), keeps the result in `items.pattern_fill` with the colours measured from it (`palette`), lays those colours
over the item's colour words (`palette.settle`: the owner's own colour always wins) and redraws the item.

A measurement that fails never costs the item its drawing: it is drawn in its colour and says why. The demo
closet is never measured: its drawings were made in advance.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path

from PIL import Image

from . import db, illustrations, palette
from .config import Config
from .state import State
from .tagger.tagging import RouteUnavailable

log = logging.getLogger("closet.patterns")

MEASURED = ("plaid", "stripe", "floral", "camo", "other")
TOPS = ("tee", "shirt", "polo", "sweater", "hoodie", "jacket", "coat")
FAILED = "Closet could not measure the pattern from the photo, so the drawing shows only its colour."
NO_CUTOUT = "The pattern is measured from the photo with its background removed, which this item does not have yet."

Measurer = Callable[..., dict | None]          # (cutout, pattern, words, landmarks) -> kept pattern or None
Landmarker = Callable[[Image.Image, tuple[str, ...]], dict]
Routes = Callable[[], tuple[str, ...]]


def wanted(pattern) -> bool:
    return isinstance(pattern, str) and pattern in MEASURED


def mark(conn, item_id: str) -> None:
    """After a description arrives or the owner changes the pattern: measure it (again), or stop drawing a
    pattern that no longer applies. Inside the caller's transaction."""
    row = conn.execute("SELECT pattern FROM items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        return
    if wanted(row["pattern"]):
        conn.execute("UPDATE items SET pattern_state = 'waiting', pattern_error = NULL WHERE id = ?", (item_id,))
    else:
        conn.execute("UPDATE items SET pattern_state = NULL, pattern_error = NULL, pattern_fill = NULL WHERE id = ?",
                     (item_id,))


def recover(conn) -> None:
    """A measurement interrupted by a quit starts again."""
    conn.execute("UPDATE items SET pattern_state = 'waiting' WHERE pattern_state = 'working'")


def waiting_count(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM items WHERE pattern_state IN ('waiting', 'working')").fetchone()[0]


def _words(row) -> list[str]:
    words = [row["color"]] if row["color"] else []
    try:
        answer = json.loads(row["tag_answer"]) if row["tag_answer"] else {}
        words += [w for w in answer.get("secondary_colors") or [] if isinstance(w, str)]
    except ValueError:
        pass
    return words


def _cutout(conn, images_dir: Path, item_id: str) -> Image.Image | None:
    p = conn.execute("SELECT cutout_path FROM photos WHERE item_id = ? AND cutout_path IS NOT NULL "
                     "ORDER BY kind = 'front' DESC, created_at LIMIT 1", (item_id,)).fetchone()
    if p is None:
        return None
    with Image.open(images_dir / p["cutout_path"]) as im:
        return im.convert("RGBA")


def run_one(conn, images_dir: Path, measurer: Measurer, landmarker: Landmarker | None, routes: Routes) -> str:
    """Measure the oldest waiting item. Returns 'empty' or 'done'."""
    conn.execute("BEGIN IMMEDIATE")
    row = conn.execute("SELECT * FROM items WHERE pattern_state = 'waiting' ORDER BY updated_at LIMIT 1").fetchone()
    if row is None:
        conn.execute("COMMIT")
        return "empty"
    item_id = row["id"]
    conn.execute("UPDATE items SET pattern_state = 'working' WHERE id = ?", (item_id,))
    conn.execute("COMMIT")
    try:
        cut = _cutout(conn, images_dir, item_id)
        if cut is None:
            conn.execute("UPDATE items SET pattern_state = 'failed', pattern_error = ? WHERE id = ?", (NO_CUTOUT, item_id))
            return "done"
        marks = json.loads(row["landmarks"]) if row["landmarks"] else None
        if marks is None and landmarker is not None and row["category"] in TOPS:
            usable = routes()
            if usable:
                try:
                    marks = landmarker(cut, usable)
                    conn.execute("UPDATE items SET landmarks = ? WHERE id = ?", (json.dumps(marks), item_id))
                except RouteUnavailable:
                    log.info("no route to Claude for the landmarks; the pattern is measured without placing it")
                except Exception:
                    log.warning("asking for an item's landmarks failed; measuring without them", exc_info=True)
        t0 = time.monotonic()
        kept = palette.keep(measurer(cut, row["pattern"], _words(row), marks), row["pattern"])
        log.info("measured a %s in %.1f s", row["pattern"], time.monotonic() - t0)
    except Exception as e:   # never lost: the item says why and is drawn in its colour
        log.warning("measuring an item's pattern failed: %s", type(e).__name__, exc_info=True)
        kept, error = None, FAILED
    else:
        error = None if kept is not None else FAILED
    conn.execute("BEGIN IMMEDIATE")
    try:
        now = conn.execute("SELECT pattern, pattern_state FROM items WHERE id = ?", (item_id,)).fetchone()
        if now is None or now["pattern_state"] != "working" or now["pattern"] != row["pattern"]:
            conn.execute("COMMIT")   # deleted, or the owner changed the pattern meanwhile: that measurement is next
            return "done"
        conn.execute("UPDATE items SET pattern_fill = ?, pattern_state = ?, pattern_error = ? WHERE id = ?",
                     (json.dumps(kept) if kept else None, "done" if kept else "failed", error, item_id))
        palette.settle(conn, item_id)   # the item's colour from the measured colours, unless the owner set it
        illustrations.redraw(conn, item_id)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return "done"


class Worker:
    """One thread that measures the open closet's waiting items, one at a time."""

    def __init__(self, cfg: Config, state: State, measurer: Measurer, landmarker: Landmarker | None,
                 routes: Routes, idle: float = 60):
        self.cfg, self.state, self.measurer, self.landmarker, self.routes, self.idle = (
            cfg, state, measurer, landmarker, routes, idle)
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="pattern-worker", daemon=True)
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
            except Exception:
                log.exception("pattern worker error")
            self._wake.wait(timeout=self.idle)
            self._wake.clear()

    def drain(self) -> int:
        done = 0
        profile = self.state.get("profile")
        if profile == "demo":
            return done
        path = self.cfg.db_path(profile)
        if not path.exists():
            return done
        conn = db.connect(path)
        try:
            recover(conn)
            while not self._stop.is_set() and run_one(conn, self.cfg.images_dir(profile), self.measurer,
                                                      self.landmarker, self.routes) == "done":
                done += 1
        finally:
            conn.close()
        return done
