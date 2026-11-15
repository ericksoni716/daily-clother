"""A shoe drawn by Claude from its sorted photos, in the background, and kept with the item (shoes drawn from
understanding, step C).

When a shoe's photos are first sorted into views (`shoeviews`: its views settle to `sorted`, or to `asking` while the
owner is asked which photo shows the outside) and it has never been drawn, it waits to be drawn (`first_sorted`),
once, by itself. After that it is drawn again only when the owner asks
(`ask`, the item page's "Draw again"; also the way to draw a shoe kept from before, whose photos are first sent to be
sorted if they never were). Adding or removing photos never draws it again: the item page says the photos changed
since the drawing. The drawing it has stays shown until a new one is done.

A waiting shoe is drawn once its views are `sorted`; while they are being sorted, or the owner is asked which photo
shows the outside, it waits and the item page says why. The drawing itself is `tagger/shoedrawing.py`: a feature sheet
and a drawing, checked against the photos at most three times. It is kept in `items.drawn` with the sheet, the
rounds, the seconds, each call's tokens and what the API key would charge for it.

Same rules as sorting the photos: when Claude cannot be reached the shoe waits, with its attempt given back and a
plain note; another failure is tried again, three times in all, then the item says so. The demo closet is never sent
to Claude.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections.abc import Callable
from pathlib import Path

from PIL import Image

from . import db, failures, shoeviews, tracejobs
from .config import Config
from .state import State
from .tagger.shoedrawing import Drawn, Photo
from .tagger.tagging import CapReached, RouteUnavailable

log = logging.getLogger("closet.shoedraw")

MAX_ATTEMPTS = 3      # as for describing and sorting
ABOUT_USD = 0.4       # roughly what one drawing costs on the API key, until this shoe has one of its own: $0.23 to
                      # $0.70 on the owner's five pairs, $0.37 on average (15 November 2026)
SHOES = tracejobs.SHOES

# the shoe's photos (the main one first, each with its view) and the routes to try -> the drawing
Drawer = Callable[[list[Photo], tuple[str, ...]], Drawn]
Routes = Callable[[], tuple[str, ...]]

WAITING = "The shoe is drawn from its photos in a moment."
WAIT_SORT = "Waiting for the photos to be sorted into views; the shoe is drawn after that."
WAIT_ASK = "Waiting for your answer about which photo shows the outside; the shoe is drawn after that."
WAIT_UNSORTED = ("The photos could not be sorted into views, so the shoe can't be drawn yet. Add or remove a photo to "
                 "sort them again.")
DRAWING = "Drawing the shoe from its photos — about two minutes."
NO_ROUTE = "Waiting for Claude to draw the shoe: it can't be reached right now. It is drawn by itself once it can."
LIMIT = ("Waiting for Claude to draw the shoe: this month's spending limit for the API key has been reached. It is "
         "drawn when your plan can be used again, when the new month starts, or if you raise the limit in Settings.")
FAILED = "Claude could not draw the shoe from its photos after three tries."
NO_PHOTO = "A photo of this shoe is missing, so it could not be drawn. Remove it, or add the photo again, then try again."
DEMO = "The demo closet is never sent to Claude, so its shoes are not drawn from their photos."
NOT_A_SHOE = "Only a shoe is drawn from its photos."
SOON = "It is drawn from its photos once they are sorted into views."
NOT_DRAWN = "Not drawn from its photos yet."
_WAIT_NOTES = (NO_ROUTE, LIMIT)


def first_sorted(conn, item_id: str) -> None:
    """A shoe's photos were just sorted into views, or the owner is asked which shows the outside (inside the
    caller's transaction): a shoe never drawn, and never waiting or failed, waits to be drawn (once they are sorted).
    Only this once by itself; after that, only when the owner asks."""
    conn.execute("UPDATE items SET drawn_state = 'waiting', drawn_error = NULL, drawn_attempts = 0 "
                 "WHERE id = ? AND drawn IS NULL AND drawn_state IS NULL", (item_id,))


def ask(conn, item_id: str, demo: bool = False) -> bool:
    """The owner asks for the shoe to be drawn (again), inside the caller's transaction. Returns False when it is
    already waiting or being drawn (nothing changes). Photos never sorted (or whose sorting failed) are sent to be
    sorted first. The drawing it has stays until the new one is done. Raises `items.ItemError` for anything that is
    not a shoe, or in the demo closet."""
    from . import items

    row = items.get(conn, item_id)
    if demo:
        raise items.ItemError(DEMO, 409)
    if not tracejobs.wanted(row["category"]):
        raise items.ItemError(NOT_A_SHOE, 409)
    if not shoeviews.photos_of(conn, item_id):
        raise items.ItemError("This shoe has no photo to draw it from.", 409)
    if row["drawn_state"] in ("waiting", "drawing"):
        return False
    conn.execute("UPDATE items SET drawn_state = 'waiting', drawn_error = NULL, drawn_attempts = 0, updated_at = ? "
                 "WHERE id = ?", (db.now(), item_id))
    if row["views_state"] in (None, "failed"):
        shoeviews.changed(conn, item_id)
    return True


def _drawn(row) -> dict | None:
    try:
        d = json.loads(row["drawn"]) if row["drawn"] else None
    except ValueError:
        return None
    return d if isinstance(d, dict) and isinstance(d.get("left"), str) else None


def stored(row) -> dict | None:
    """The drawing kept with the item, or None."""
    return _drawn(row)


def _message(row) -> str | None:
    state = row["drawn_state"]
    if state == "waiting":
        if row["drawn_error"]:
            return row["drawn_error"]
        views = row["views_state"]
        if views in ("waiting", "sorting"):
            return WAIT_SORT
        if views == "asking":
            return WAIT_ASK
        if views != "sorted":
            return WAIT_UNSORTED
        return WAITING
    if state == "drawing":
        return DRAWING
    if state == "failed":
        return row["drawn_error"] or FAILED
    if state is None and _drawn(row) is None:
        return SOON if row["views_state"] in ("waiting", "sorting") else NOT_DRAWN
    return None


def shown(conn, row) -> dict | None:
    """What the item page shows of a shoe drawn from its photos; None for anything that is not a shoe.

    state: null (not drawn, nor waiting to be), waiting, drawing, done or failed. message: what is happening or why,
    in plain words. url: the drawing on two legs (`drawn.svg`), versioned, while the item has one (the one it has
    stays until a new one is done); rounds, seconds, cost_usd (what the API key would charge for it, whichever route
    drew it), route and made_at: about that drawing. photos_changed: photos were added or removed since it was made.
    about_usd: roughly what drawing it again costs on the API key."""
    if not tracejobs.wanted(row["category"]):
        return None
    d = _drawn(row)
    now = sorted(p["id"] for p in shoeviews.photos_of(conn, row["id"]))
    version = hashlib.sha256(f"{d['left']}{d.get('right') or ''}{d.get('made_at')}".encode()).hexdigest()[:16] if d else ""
    return {
        "state": row["drawn_state"], "message": _message(row),
        "url": f"/api/items/{row['id']}/drawn.svg?v={version}" if d else None,
        "rounds": d.get("rounds") if d else None, "seconds": d.get("seconds") if d else None,
        "cost_usd": d.get("cost_usd") if d else None, "route": d.get("route") if d else None,
        "made_at": d.get("made_at") if d else None,
        "photos_changed": bool(d) and sorted(d.get("photo_ids") or []) != now,
        "about_usd": round(d["cost_usd"], 2) if d and isinstance(d.get("cost_usd"), (int, float)) and d["cost_usd"] > 0
        else ABOUT_USD,
    }


def due(conn):
    """The waiting shoe to draw next: one whose photos are sorted."""
    return conn.execute(f"SELECT * FROM items WHERE drawn_state = 'waiting' AND views_state = 'sorted' "
                        f"AND category IN {SHOES} ORDER BY updated_at, id LIMIT 1").fetchone()


def note_waiting(conn, why: str | None) -> None:
    """Tell the shoes waiting to be drawn what holds them up, or stop saying so when `why` is None."""
    marks = ",".join("?" * len(_WAIT_NOTES))
    if why:
        conn.execute(f"UPDATE items SET drawn_error = ? WHERE drawn_state = 'waiting' AND category IN {SHOES} "
                     f"AND (drawn_error IS NULL OR drawn_error IN ({marks}))", (why, *_WAIT_NOTES))
    else:
        conn.execute(f"UPDATE items SET drawn_error = NULL WHERE drawn_state = 'waiting' AND drawn_error IN ({marks})",
                     _WAIT_NOTES)


def recover(conn) -> None:
    """A drawing interrupted by a quit starts again."""
    conn.execute("UPDATE items SET drawn_state = 'waiting' WHERE drawn_state = 'drawing'")


def _open(images_dir: Path, photos: list) -> list[Photo]:
    if not photos:
        raise LookupError("the shoe has no photo")
    out = []
    for p in photos:
        with Image.open(images_dir / p["original_path"]) as im:
            out.append(Photo(im.convert("RGB"), p["view"], None if p["view_sure"] is None else bool(p["view_sure"])))
    return out


def run_one(conn, images_dir: Path, routes: tuple[str, ...], drawer: Drawer) -> str:
    """Draw the shoe that is due first (`due`). Returns 'empty' (none is due), 'done' (one was worked on) or 'blocked'
    (Claude could not be reached after all: it waits again and keeps its attempts)."""
    conn.execute("BEGIN IMMEDIATE")
    row = due(conn)
    if row is None:
        conn.execute("COMMIT")
        return "empty"
    item_id = row["id"]
    conn.execute("UPDATE items SET drawn_state = 'drawing', drawn_attempts = drawn_attempts + 1 WHERE id = ?", (item_id,))
    photos = shoeviews.photos_of(conn, item_id)
    conn.execute("COMMIT")
    attempts = row["drawn_attempts"] + 1
    try:
        made = drawer(_open(images_dir, photos), routes)
        if not isinstance(made, Drawn):
            raise TypeError("the drawer did not return a drawing")
    except RouteUnavailable as e:
        # nothing is wrong with the shoe: Claude cannot be reached right now, so it waits without losing an attempt
        log.info("drawing a shoe is waiting: no route to Claude can be used right now")
        conn.execute("UPDATE items SET drawn_state = 'waiting', drawn_attempts = max(0, drawn_attempts - 1) "
                     "WHERE id = ? AND drawn_state = 'drawing'", (item_id,))
        note_waiting(conn, LIMIT if isinstance(e, CapReached) else NO_ROUTE)
        return "blocked"
    except Exception as e:   # recorded against the item, never lost; only its kind is logged
        log.warning("drawing a shoe failed (attempt %s): %s", attempts, type(e).__name__)
        missing = isinstance(e, (LookupError, OSError))
        given_up = missing or attempts >= MAX_ATTEMPTS
        conn.execute("UPDATE items SET drawn_state = ?, drawn_error = ? WHERE id = ? AND drawn_state = 'drawing'",
                     ("failed" if given_up else "waiting", (NO_PHOTO if missing else FAILED) if given_up else None,
                      item_id))
        if given_up:
            failures.report(conn, item_id, "drawing from its photos", str(e))
        return "done"
    conn.execute("BEGIN IMMEDIATE")
    try:
        now_row = conn.execute("SELECT drawn_state FROM items WHERE id = ?", (item_id,)).fetchone()
        if now_row is not None and now_row["drawn_state"] == "drawing":   # else deleted meanwhile
            conn.execute("UPDATE items SET drawn = ?, drawn_state = 'done', drawn_error = NULL, drawn_attempts = 0, "
                         "updated_at = ? WHERE id = ?",
                         (json.dumps(made.to_json([p["id"] for p in photos], db.now())), db.now(), item_id))
        note_waiting(conn, None)   # Claude could be reached: the others are no longer held up
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return "done"


class Worker:
    """One thread that draws the open closet's waiting shoes, one at a time. Never the demo's."""

    def __init__(self, cfg: Config, state: State, routes: Routes, drawer: Drawer, idle: float = 60):
        self.cfg, self.state, self.routes, self.drawer, self.idle = cfg, state, routes, drawer, idle
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="shoe-drawing", daemon=True)
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
            self._wake.clear()
            try:
                self.drain()
            except Exception:   # keep the worker alive; the next wake retries
                log.exception("shoe drawing worker error")
            self._wake.wait(timeout=self.idle)

    def drain(self) -> int:
        """Draw every waiting shoe whose photos are sorted until none is left or Claude cannot be reached. Returns
        how many were worked on."""
        done = 0
        profile = self.state.get("profile")
        if profile == "demo":   # the demo closet is never sent to Claude
            return done
        path = self.cfg.db_path(profile)
        if not path.exists():
            return done
        conn = db.connect(path)
        try:
            recover(conn)
            while not self._stop.is_set():
                if due(conn) is None:
                    break
                routes = self.routes()   # asked before each shoe, so turning the API key off takes effect at once
                if not routes:
                    note_waiting(conn, NO_ROUTE)
                    break
                status = run_one(conn, self.cfg.images_dir(profile), routes, self.drawer)
                if status == "blocked":
                    break
                done += status == "done"
        finally:
            conn.close()
        return done
