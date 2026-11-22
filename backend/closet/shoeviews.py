"""A shoe's photos sorted into views by Claude, in the background (shoes drawn from understanding, step B).

A shoe has its main photo and up to five more (`MAX_EXTRA`), taken in any order: on Add the owner takes or chooses
them all at once, and the first one is the main photo until they are sorted. Whenever a photo is added or removed
the shoe waits to be sorted (`changed`); once its newest photo is `SORT_QUIET` seconds old (the owner may still be
adding more) one call to Claude with all of its photos, the main one first, says which view each shows: the outer or
inner side, from above, the front, the back, the sole or something else, and whether it is sure
(`tagger/views.py`). Claude's word never replaces the owner's: a photo whose view the owner gave
(`photos.view_by = 'owner'`) keeps it.

Once the views are settled (`sorted`), a main photo that is not the outer side gives way to the outer side, and a
main photo that is not a side view gives way to the inner side when there is no outer one (`promote`): that photo
becomes the closet picture, cut out as usual, and the photo traced for the shoe's drawing. A main photo that is the
outer side, or a shoe with no side photo, stays as it is. Shoes sorted before the inner side gave way too are put right
once by the cut-out queue (`catch_up`).

The owner is asked only when it matters and Claude could not tell (`question`): when the outer and inner sides look
different (a logo, stripe or panel on one side only: `items.sides_differ`) and a side photo is unsure, or two photos
claim the same side. The item page then asks which photo shows the outside.

Same rules as describing (`tagjobs.py`): when Claude cannot be reached the shoe waits, with its attempt given back
and a plain note; another failure is tried again, three times in all, then the item says so. The demo closet is
never sent to Claude, and shoes kept before this are not sorted until a photo is added or removed.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from . import db, failures, tracejobs
from .config import Config
from .state import State
from .tagger.tagging import CapReached, RouteUnavailable, Unreachable
from .tagger.views import SIDES, VIEWS, ShoeViews

log = logging.getLogger("closet.shoeviews")

SORT_QUIET = 10      # seconds after the newest photo before the photos are sorted: the owner may be adding more
MAX_ATTEMPTS = 3     # as for describing
MAX_EXTRA = 5        # photos of a shoe besides its main one
OWNER_VIEWS = ("front", "top")   # the views the owner can name when adding a photo (the second photo of before)
OPPOSITE = {"outer": "inner", "inner": "outer"}
SHOES = tracejobs.SHOES

# photos (the main one first) and the routes to try, in order -> Claude's answer
Sorter = Callable[[list[Image.Image], tuple[str, ...]], ShoeViews]
Routes = Callable[[], tuple[str, ...]]

WAITING = "The photos are sorted into views in a moment."
SORTING = "Sorting the photos into views…"
NO_ROUTE = ("Waiting for Claude to sort the photos into views: it can't be reached right now. They are sorted by "
            "themselves once it can.")
LIMIT = ("Waiting for Claude to sort the photos into views: this month's spending limit for the API key has been "
         "reached. They are sorted when your plan can be used again, when the new month starts, or if you raise the "
         "limit in Settings.")
FAILED = "Claude could not sort the photos into views after three tries. Add or remove a photo to try again."
NO_PHOTO = "A photo of this shoe is missing, so the photos could not be sorted. Remove it, or add the photo again."
DEMO = "The demo closet never sends photos to Claude, so its photos are not sorted into views."
_WAIT_NOTES = (NO_ROUTE, LIMIT)


def may_have_photos(category) -> bool:
    """A shoe, or an item Claude has not described yet (a shoe just added from "A shoe" on Add)."""
    return category is None or tracejobs.wanted(category)


def changed(conn, item_id: str, demo: bool = False) -> None:
    """A photo of the shoe was added or removed (inside the caller's transaction): it waits to be sorted again, with
    fresh attempts. In the demo closet nothing is sent to Claude, so the item says so instead."""
    if demo:
        conn.execute("UPDATE items SET views_state = NULL, views_error = ?, views_attempts = 0 WHERE id = ?",
                     (DEMO, item_id))
    else:
        conn.execute("UPDATE items SET views_state = 'waiting', views_error = NULL, views_attempts = 0 WHERE id = ?",
                     (item_id,))


def photos_of(conn, item_id: str) -> list:
    """The shoe's photos as they are sent to Claude: the main one first, then the others, oldest first."""
    return conn.execute("SELECT * FROM photos WHERE item_id = ? ORDER BY kind = 'front' DESC, created_at, id",
                        (item_id,)).fetchall()


def question(conn, row) -> list[str] | None:
    """The photos the owner is asked to choose the outside from, or None when nothing needs asking: the side photos
    Claude sorted (not those the owner named), when the two sides look different and one of them is unsure or two
    photos claim the same side."""
    if not row["sides_differ"]:
        return None
    sides = [p for p in photos_of(conn, row["id"]) if p["view"] in SIDES]
    model = [p for p in sides if p["view_by"] != "owner"]
    if not model:
        return None
    unsure = any(p["view_sure"] != 1 for p in model)
    clash = any(len(claims) > 1 and any(p["view_by"] != "owner" for p in claims)
                for claims in ([p for p in sides if p["view"] == side] for side in SIDES))
    return [p["id"] for p in model] if unsure or clash else None


def settle(conn, item_id: str) -> None:
    """After the views changed: the item asks the owner when a side question remains, else it is sorted, and the
    outer side becomes the main photo (or the inner side, when the main one is not a side view: `promote`). A shoe whose
    photos settle for the first time and that was never drawn waits to be drawn from them (`shoedraw.first_sorted`):
    once they are sorted, after the owner's answer when asked."""
    from . import shoedraw  # it reads the sorted photos, so it imports this module

    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if row is not None:
        state = "asking" if question(conn, row) else "sorted"
        conn.execute("UPDATE items SET views_state = ? WHERE id = ?", (state, item_id))
        if state == "sorted":   # while the owner is asked, which side is the outer one is not known yet
            promote(conn, item_id)
        shoedraw.first_sorted(conn, item_id)


def promote(conn, item_id: str) -> bool:
    """Once the photos are sorted (inside the caller's transaction): when the main photo is not the outer side and
    another photo is, that photo becomes the main one; when the main photo is not a side view at all and no photo
    is the outer side, the inner side does. It becomes the closet picture, cut out as usual (the old one's cutout
    job, if still waiting, goes), and the photo traced for the shoe's drawing (the old trace goes, the owner's
    fixes stay). Among several of the same side: the one the owner named, then one Claude was sure of, then the
    oldest. The old main photo stays as one of the others, with its view (the owner's word on it included).
    Returns whether the main photo changed. (22 November: an inner side that was the main photo used to stay, so
    the closet picture showed the inside while Claude's side drawing showed the outside.)

    Claude's description is not asked again: its words on the photo it saw first stay with that photo
    (`items.tag_photo_id`), and the cut-out queue does not describe again a photo Claude has already seen."""
    from . import illustrations, jobs

    photos = photos_of(conn, item_id)
    main = next((p for p in photos if p["kind"] == "front"), None)
    if main is None or main["view"] == "outer":
        return False
    found: list = []
    for side in SIDES if main["view"] not in SIDES else ("outer",):   # the outer side first
        found = [p for p in photos if p["kind"] != "front" and p["view"] == side]
        if found:
            break
    if not found:
        return False
    pick = min(found, key=lambda p: (p["view_by"] != "owner", p["view_sure"] != 1))   # the first of the best: oldest
    conn.execute("UPDATE photos SET kind = 'detail' WHERE id = ?", (main["id"],))
    conn.execute("UPDATE photos SET kind = 'front' WHERE id = ?", (pick["id"],))
    conn.execute("DELETE FROM jobs WHERE kind = 'cutout' AND item_id = ? AND state = 'queued'", (item_id,))
    jobs.enqueue_cutout(conn, item_id, pick["id"])
    tracejobs.forget(conn, item_id)
    illustrations.redraw(conn, item_id)
    return True


# a sorted shoe whose main photo is the inner side while another photo is the outer side: sorted before 22 November,
# when such a main photo stayed (since then `settle` never leaves one so)
INNER_MAIN = (f"i.views_state = 'sorted' AND i.category IN {SHOES} "
              "AND EXISTS (SELECT 1 FROM photos m WHERE m.item_id = i.id AND m.kind = 'front' AND m.view = 'inner') "
              "AND EXISTS (SELECT 1 FROM photos o WHERE o.item_id = i.id AND o.kind != 'front' AND o.view = 'outer')")


def catch_up(conn) -> int:
    """Shoes sorted before 22 November whose main photo is the inner side and that have an outer side photo: the
    outer side becomes their main photo (`promote`), once, without asking Claude again or the owner doing anything.
    Run by the cut-out queue at each round (never for the demo closet), which then cuts the new main photo out and
    traces it; once put right a shoe no longer matches, so each is changed once. Returns how many changed."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        found = [r["id"] for r in conn.execute(f"SELECT i.id FROM items i WHERE {INNER_MAIN} ORDER BY i.id")]
        changed_ = sum(promote(conn, item_id) for item_id in found)
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    if changed_:
        log.info("%s shoes sorted before now show their outer side as their picture", changed_)
    return changed_


def read(answer, count: int) -> dict[int, tuple[str, bool]]:
    """Claude's answer as photo number -> (view, sure), checked: every photo sent named once, no other."""
    if not isinstance(answer, ShoeViews):
        raise TypeError("the sorter did not return the views of the photos")
    said: dict[int, tuple[str, bool]] = {}
    for p in answer.photos:
        if not 1 <= p.photo <= count or p.photo in said or p.view not in VIEWS:
            raise ValueError("the answer named a photo that was not sent, or one photo twice")
        said[p.photo] = (p.view, p.sure)
    if len(said) != count:
        raise ValueError("the answer did not name every photo")
    return said


def apply(conn, item_id: str, photo_ids: list[str], said: dict[int, tuple[str, bool]], sides_differ: bool) -> None:
    """Claude's views for these photos (in the order they were sent), inside the caller's transaction. A photo whose
    view the owner gave keeps it."""
    for n, photo_id in enumerate(photo_ids, 1):
        view, sure = said[n]
        conn.execute("UPDATE photos SET view = ?, view_sure = ?, view_by = 'model' WHERE id = ? AND item_id = ? "
                     "AND coalesce(view_by, '') != 'owner'", (view, int(sure), photo_id, item_id))
    conn.execute("UPDATE items SET sides_differ = ?, views_error = NULL, views_attempts = 0, updated_at = ? WHERE id = ?",
                 (int(sides_differ), db.now(), item_id))
    settle(conn, item_id)


def answer(conn, item_id: str, photo_id: str, view: str) -> None:
    """The owner says which view a photo shows (inside the caller's transaction): kept as the owner's, sure, and never
    changed by sorting again. When it is the outer or inner side and exactly one other photo is a side photo, that one
    is the other side, also as the owner's; with more side photos, those Claude said show the same side show the other
    one (the owner can say which photo shows the outside at any time, so a swap Claude was sure of is put right too)."""
    conn.execute("UPDATE photos SET view = ?, view_sure = 1, view_by = 'owner' WHERE id = ? AND item_id = ?",
                 (view, photo_id, item_id))
    if view in SIDES:
        others = [p for p in photos_of(conn, item_id) if p["view"] in SIDES and p["id"] != photo_id]
        if len(others) == 1:
            conn.execute("UPDATE photos SET view = ?, view_sure = 1, view_by = 'owner' WHERE id = ?",
                         (OPPOSITE[view], others[0]["id"]))
        else:
            for p in others:
                if p["view"] == view and p["view_by"] != "owner":
                    conn.execute("UPDATE photos SET view = ?, view_sure = 1, view_by = 'owner' WHERE id = ?",
                                 (OPPOSITE[view], p["id"]))
    row = conn.execute("SELECT views_state FROM items WHERE id = ?", (item_id,)).fetchone()
    if row is not None and row["views_state"] in ("asking", "sorted"):
        settle(conn, item_id)
    conn.execute("UPDATE items SET updated_at = ? WHERE id = ?", (db.now(), item_id))


def shown(conn, row) -> dict | None:
    """What the item page shows of a shoe's photos sorted into views; None for anything that is not a shoe.

    state: null (nothing to sort: a shoe kept before this, or the demo closet), waiting, sorting, asking (the owner
    is asked which photo shows the outside), sorted or failed. message: what is happening or why, in plain words.
    asking: the ids of the photos to choose the outside from, while asking; else null."""
    if not tracejobs.wanted(row["category"]):
        return None
    state = row["views_state"]
    message = row["views_error"] or {"waiting": WAITING, "sorting": SORTING}.get(state)
    return {"state": state, "message": message, "asking": question(conn, row) if state == "asking" else None}


def _when(text: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(text) if text else None
    except ValueError:
        return None


def due(conn, now: datetime) -> tuple[object | None, float | None]:
    """The waiting shoe to sort next (its newest photo at least SORT_QUIET seconds old), and when none is due yet,
    in how many seconds the next one will be (None when no shoe waits)."""
    soon = None
    for row in conn.execute("SELECT items.*, (SELECT MAX(created_at) FROM photos WHERE photos.item_id = items.id) "
                            f"AS newest FROM items WHERE views_state = 'waiting' AND category IN {SHOES} "
                            "ORDER BY newest, id").fetchall():
        newest = _when(row["newest"])
        left = 0.0 if newest is None else SORT_QUIET - (now - newest).total_seconds()
        if left <= 0:
            return row, None
        soon = left if soon is None else min(soon, left)
    return None, soon


def note_waiting(conn, why: str | None) -> None:
    """Tell the shoes waiting to be sorted what holds them up, or stop saying so when `why` is None."""
    marks = ",".join("?" * len(_WAIT_NOTES))
    if why:
        conn.execute(f"UPDATE items SET views_error = ? WHERE views_state = 'waiting' AND category IN {SHOES} "
                     f"AND (views_error IS NULL OR views_error IN ({marks}))", (why, *_WAIT_NOTES))
    else:
        conn.execute(f"UPDATE items SET views_error = NULL WHERE views_state = 'waiting' AND views_error IN ({marks})",
                     _WAIT_NOTES)


def recover(conn) -> None:
    """Sorting interrupted by a quit starts again."""
    conn.execute("UPDATE items SET views_state = 'waiting' WHERE views_state = 'sorting'")


def _open(images_dir: Path, photos: list) -> list[Image.Image]:
    if not photos:
        raise LookupError("the shoe has no photo")
    out = []
    for p in photos:
        with Image.open(images_dir / p["original_path"]) as im:
            out.append(im.convert("RGB"))
    return out


def run_one(conn, images_dir: Path, routes: tuple[str, ...], sorter: Sorter, now: datetime | None = None) -> str:
    """Sort the photos of the shoe that is due first (`due`). Returns 'empty' (none is due), 'done' (one was worked
    on) or 'blocked' (Claude could not be reached after all: it waits again and keeps its attempts)."""
    now = now or datetime.now(UTC)
    conn.execute("BEGIN IMMEDIATE")
    row, _ = due(conn, now)
    if row is None:
        conn.execute("COMMIT")
        return "empty"
    item_id = row["id"]
    conn.execute("UPDATE items SET views_state = 'sorting', views_attempts = views_attempts + 1 WHERE id = ?", (item_id,))
    photos = photos_of(conn, item_id)
    conn.execute("COMMIT")
    attempts = row["views_attempts"] + 1
    try:
        answer = sorter(_open(images_dir, photos), routes)
        said = read(answer, len(photos))
    except (RouteUnavailable, Unreachable) as e:   # out of reach (no route, no network, overloaded): it waits
        # nothing is wrong with the photos: Claude cannot be reached right now, so it waits without losing an attempt
        log.info("sorting a shoe's photos is waiting: no route to Claude can be used right now")
        conn.execute("UPDATE items SET views_state = 'waiting', views_attempts = max(0, views_attempts - 1) "
                     "WHERE id = ? AND views_state = 'sorting'", (item_id,))
        note_waiting(conn, LIMIT if isinstance(e, CapReached) else NO_ROUTE)
        return "blocked"
    except Exception as e:   # recorded against the item, never lost; only its kind is logged
        log.warning("sorting a shoe's photos failed (attempt %s): %s", attempts, type(e).__name__)
        missing = isinstance(e, (LookupError, OSError))
        given_up = missing or attempts >= MAX_ATTEMPTS
        conn.execute("UPDATE items SET views_state = ?, views_error = ? WHERE id = ? AND views_state = 'sorting'",
                     ("failed" if given_up else "waiting", (NO_PHOTO if missing else FAILED) if given_up else None,
                      item_id))
        if given_up:
            failures.report(conn, item_id, "sorting of its photos", str(e))
        return "done"
    conn.execute("BEGIN IMMEDIATE")
    try:
        now_row = conn.execute("SELECT views_state FROM items WHERE id = ?", (item_id,)).fetchone()
        if now_row is not None and now_row["views_state"] == "sorting":   # else deleted, or a photo added or removed
            apply(conn, item_id, [p["id"] for p in photos], said, answer.sides_differ)
        note_waiting(conn, None)   # Claude could be reached: the others are no longer held up
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return "done"


class Worker:
    """One thread that sorts the photos of the open closet's waiting shoes, one shoe at a time. Never the demo's."""

    def __init__(self, cfg: Config, state: State, routes: Routes, sorter: Sorter, idle: float = 60):
        self.cfg, self.state, self.routes, self.sorter, self.idle = cfg, state, routes, sorter, idle
        self.soon: float | None = None   # seconds until the next waiting shoe is due, after the last round
        self.on_sorted: Callable[[], None] = lambda: None   # a shoe's photos were sorted (it may be drawn next)
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="shoe-views", daemon=True)
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
                log.exception("shoe views worker error")
            # a shoe whose newest photo is still too new is sorted as soon as it is quiet, not at the next round
            self._wake.wait(timeout=self.idle if self.soon is None else min(self.idle, self.soon + 0.5))

    def drain(self, now: datetime | None = None) -> int:
        """Sort every waiting shoe that is due until none is left or Claude cannot be reached. Returns how many were
        worked on. `now` stands in for the clock (tests)."""
        self.soon = None
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
                t = now or datetime.now(UTC)
                row, self.soon = due(conn, t)
                if row is None:
                    break
                routes = self.routes()   # asked before each shoe, so turning the API key off takes effect at once
                if not routes:
                    note_waiting(conn, NO_ROUTE)
                    break
                status = run_one(conn, self.cfg.images_dir(profile), routes, self.sorter, t)
                if status == "blocked":
                    break
                done += status == "done"
        finally:
            conn.close()
        if done:
            self.on_sorted()
        return done
