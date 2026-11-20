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

The owner can correct a drawing with a one-line note (step E, `correct`): the note waits in `items.drawn_note` with
the shoe `waiting`, and the worker makes the change (`correcting`) as it makes a drawing, through
`shoedrawing.correct`, which changes only what the note asks and checks the change against the photos. A correction
never waits for the photos to be sorted: it uses them as they are. Each change, a correction or a new drawing,
keeps the drawing before it in `items.drawn_prev` (one level), and `back` swaps the two, so the owner goes back in
one tap and forward again the same way. The owner's notes stay with the drawing they made and are passed to a later
drawing from scratch.

Same rules as sorting the photos: when Claude cannot be reached the shoe waits, with its attempt given back and a
plain note; another failure is tried again, three times in all, then the item says so (a correction that fails
leaves the drawing as it was). The demo closet is never sent to Claude.

The shoe is drawn from its side with its drawing (`shoedrawing.draw`), and kept in the drawing's `side` entry: the
item's own drawing is made from it (`illustrations.make`), so the stored illustration is made again whenever the
drawing changes. A correction keeps the side as it is. A kept drawing with no side (drawn before sides were, or whose
side failed) is drawn its side by itself (`run_side`), one at a time when nothing else waits, at most `SIDE_TRIES`
times, with the same waiting when Claude cannot be reached; its tries are counted in the drawing itself
(`side_tries`), so a new drawing starts again from none.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections.abc import Callable
from pathlib import Path

from PIL import Image

from . import db, failures, illustrations, shoeviews, tracejobs
from .config import Config
from .state import State
from .tagger.shoedrawing import Drawn, Photo, Sided, clean_note, notes_of
from .tagger.tagging import CapReached, RouteUnavailable, Unreachable

log = logging.getLogger("closet.shoedraw")

MAX_ATTEMPTS = 3      # as for describing and sorting
SIDE_TRIES = 3        # a side drawn by itself, at most this many times for one drawing
ABOUT_USD = 2.0       # roughly what one drawing costs on the API key, until this shoe has one of its own: two
                      # drawings straight on, two turns, the judge and a fix came to $1.38 to $3.13 on the owner's five
                      # pairs through the app's own code, $1.93 on average (17 November 2026), before the cache
SHOES = tracejobs.SHOES

# the shoe's photos (the main one first, each with its view), the routes to try and, as `notes`, the owner's notes on
# the drawing it replaces -> the drawing
Drawer = Callable[..., Drawn]
# the shoe's photos, the drawing kept (as `items.drawn`), the owner's note and the routes to try -> the drawing changed
# (`shoedrawing.Corrected`)
Corrector = Callable[[list[Photo], dict, str, tuple[str, ...]], Drawn]
# the shoe's photos and the routes to try, with `sheet` (the drawing's), `notes` (the owner's) and `measures` (from its
# trace) -> the side drawn by itself (`shoedrawing.Sided`)
Sider = Callable[..., Sided]
Routes = Callable[[], tuple[str, ...]]

WAITING = "The shoe is drawn from its photos in a moment."
WAIT_SORT = "Waiting for the photos to be sorted into views; the shoe is drawn after that."
WAIT_ASK = "Waiting for your answer about which photo shows the outside; the shoe is drawn after that."
WAIT_UNSORTED = ("The photos could not be sorted into views, so the shoe can't be drawn yet. Add or remove a photo to "
                 "sort them again.")
DRAWING = "Drawing the shoe from its photos — four to ten minutes."
NO_ROUTE = "Waiting for Claude to draw the shoe: it can't be reached right now. It is drawn by itself once it can."
LIMIT = ("Waiting for Claude to draw the shoe: this month's spending limit for the API key has been reached. It is "
         "drawn when your plan can be used again, when the new month starts, or if you raise the limit in Settings.")
FAILED = "Claude could not draw the shoe from its photos after three tries."
NO_PHOTO = "A photo of this shoe is missing, so it could not be drawn. Remove it, or add the photo again, then try again."
DEMO = "The demo closet is never sent to Claude, so its shoes are not drawn from their photos."
DEMO_DRAWN = "Made in advance for the demo closet, which is never sent to Claude."
NOT_A_SHOE = "Only a shoe is drawn from its photos."
SOON = "It is drawn from its photos once they are sorted into views."
NOT_DRAWN = "Not drawn from its photos yet."
CORRECTING = "Changing the drawing: “{note}”"
CORRECT_NO_ROUTE = ("Waiting for Claude to change the drawing: it can't be reached right now. It is changed by itself "
                    "once it can.")
CORRECT_LIMIT = ("Waiting for Claude to change the drawing: this month's spending limit for the API key has been "
                 "reached. It is changed when your plan can be used again, when the new month starts, or if you raise "
                 "the limit in Settings.")
CORRECT_FAILED = ("Claude could not change the drawing after three tries, so it is as it was. Send the note again, or "
                  "say it another way.")
CORRECT_NO_PHOTO = ("A photo of this shoe is missing, so the drawing could not be changed. Remove it, or add the photo "
                    "again, then send the note again.")
CORRECT_DEMO = "The demo closet is never sent to Claude, so its drawings are not changed."
CORRECT_NOTHING = "There is no drawing to change yet."
CORRECT_BUSY = "The shoe is being drawn or its drawing changed right now. Send the note once that is done."
NO_PREVIOUS = "There is no other drawing of this shoe to go back to."
BACK_BUSY = "The shoe is being drawn or its drawing changed right now. Go back once that is done."
_WAIT_NOTES = (NO_ROUTE, LIMIT, CORRECT_NO_ROUTE, CORRECT_LIMIT)
_CORRECT_WAIT = {NO_ROUTE: CORRECT_NO_ROUTE, LIMIT: CORRECT_LIMIT}
BUSY = ("waiting", "drawing", "correcting")


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
    if row["drawn_state"] in BUSY:   # waiting or being drawn, or a correction waiting or being made
        return False
    conn.execute("UPDATE items SET drawn_state = 'waiting', drawn_error = NULL, drawn_attempts = 0, drawn_note = NULL, "
                 "updated_at = ? WHERE id = ?", (db.now(), item_id))
    if row["views_state"] in (None, "failed"):
        shoeviews.changed(conn, item_id)
    return True


def correct(conn, item_id: str, note, demo: bool = False) -> None:
    """The owner's one-line note on the shoe's drawing, inside the caller's transaction: it waits to be made (`run_one`)
    and the drawing it has stays shown until the change is done. Raises `items.ItemError`: in the demo closet, for
    anything that is not a shoe, a note that is empty or too long, a shoe with no drawing, or while it is being drawn
    or a correction is waiting or being made."""
    from . import items

    row = items.get(conn, item_id)
    if demo:
        raise items.ItemError(CORRECT_DEMO, 409)
    if not tracejobs.wanted(row["category"]):
        raise items.ItemError(NOT_A_SHOE, 409)
    try:
        text = clean_note(note)
    except ValueError as e:
        raise items.ItemError(str(e)) from None
    if _drawn(row) is None:
        raise items.ItemError(CORRECT_NOTHING, 409)
    if row["drawn_state"] in BUSY:
        raise items.ItemError(CORRECT_BUSY, 409)
    conn.execute("UPDATE items SET drawn_state = 'waiting', drawn_note = ?, drawn_error = NULL, drawn_attempts = 0, "
                 "updated_at = ? WHERE id = ?", (text, db.now(), item_id))


def back(conn, item_id: str) -> None:
    """Swap the shoe's drawing and the one before it (inside the caller's transaction): the owner goes back to the
    drawing before the last change in one tap, and forward again the same way. Raises `items.ItemError` when there is
    none, or while it is being drawn or changed."""
    from . import items

    row = items.get(conn, item_id)
    if not tracejobs.wanted(row["category"]):
        raise items.ItemError(NOT_A_SHOE, 409)
    if row["drawn_state"] in BUSY:
        raise items.ItemError(BACK_BUSY, 409)
    if _drawn(row) is None or _drawn(row, "drawn_prev") is None:
        raise items.ItemError(NO_PREVIOUS, 409)
    # a note that a correction failed was about the drawing shown; the other one is shown now
    conn.execute("UPDATE items SET drawn = drawn_prev, drawn_prev = drawn, updated_at = ?, "
                 "drawn_error = CASE WHEN drawn_state = 'done' THEN NULL ELSE drawn_error END WHERE id = ?",
                 (db.now(), item_id))
    illustrations.redraw(conn, item_id)   # the item's drawing is the side of the drawing now shown, or the trace


def _shoe(value) -> bool:
    """One shoe as kept: one SVG text (version 1, all in front of the leg) or {behind, front} (version 2)."""
    return isinstance(value, str) or (isinstance(value, dict) and isinstance(value.get("front"), str))


def _drawn(row, column: str = "drawn") -> dict | None:
    try:
        d = json.loads(row[column]) if row[column] else None
    except ValueError:
        return None
    return d if isinstance(d, dict) and _shoe(d.get("left")) else None


def stored(row) -> dict | None:
    """The drawing kept with the item, or None. A drawing kept as version 1 (each shoe one SVG text, all in front of
    the leg) is kept and shown as it is: nothing is drawn again by itself."""
    return _drawn(row)


def _text(shoe) -> str:
    if isinstance(shoe, dict):
        return f"{shoe.get('behind') or ''}\n{shoe.get('front') or ''}"
    return shoe or ""


def correcting(row) -> bool:
    """A correction from the owner's note waits or is being made."""
    return row["drawn_state"] == "correcting" or (row["drawn_state"] == "waiting" and bool(row["drawn_note"]))


def _message(row) -> str | None:
    state = row["drawn_state"]
    if correcting(row):
        return row["drawn_error"] if state == "waiting" and row["drawn_error"] else \
            CORRECTING.format(note=row["drawn_note"])
    if state == "done" and row["drawn_error"]:   # a correction that failed: the drawing is as it was
        return row["drawn_error"]
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
    d = _drawn(row)
    if state is None and d is None:
        return SOON if row["views_state"] in ("waiting", "sorting") else NOT_DRAWN
    if d is not None and d.get("route") == "demo":
        return DEMO_DRAWN
    return None


def shown(conn, row) -> dict | None:
    """What the item page shows of a shoe drawn from its photos; None for anything that is not a shoe.

    state: null (not drawn, nor waiting to be), waiting, drawing, correcting, done or failed. message: what is
    happening or why, in plain words. url: the drawing on two legs (`drawn.svg`), versioned, while the item has one
    (the one it has stays until a new one is done); rounds, seconds, cost_usd (what the API key would charge for it,
    whichever route drew it), route and made_at: about that drawing (for a drawing changed from a note, about that
    change). photos_changed: photos were added or removed since it was made. about_usd: roughly what drawing it again
    costs on the API key.

    The owner's correction (step E): correcting: a note waits or is being drawn, and note is that note; otherwise
    corrected: this drawing is the one before changed from a note, with that note, what Claude says changed
    (changed) and, when the note asks for something the photos do not show, one plain sentence saying so
    (against_photos). has_previous: the drawing before the last change is kept (`back` swaps them), and
    previous_newer: that one is the newer of the two (the owner went back).

    side: the shoe drawn from its side with this drawing, or null: url (`drawn/side.svg`, on its card, versioned) and
    features (what makes the shoe itself from the side). side_shown: the item's own drawing is that side (the owner
    has not chosen the plain drawing), so the trace's colours and marks do not show."""
    if not tracejobs.wanted(row["category"]):
        return None
    d = _drawn(row)
    now = sorted(p["id"] for p in shoeviews.photos_of(conn, row["id"]))
    version = hashlib.sha256(f"{_text(d['left'])}{_text(d.get('right'))}{d.get('made_at')}".encode()).hexdigest()[:16] \
        if d else ""
    prev = _drawn(row, "drawn_prev")
    busy = correcting(row)
    notes = notes_of(d) if d else []
    corrected = bool(d and d.get("corrected") and notes)
    last = notes[-1] if corrected and not busy else {}
    side = side_of(d)
    side_version = hashlib.sha256(f"{side['svg']}{side.get('made_at')}".encode()).hexdigest()[:16] if side else ""
    return {
        "state": row["drawn_state"], "message": _message(row),
        "url": f"/api/items/{row['id']}/drawn.svg?v={version}" if d else None,
        "rounds": d.get("rounds") if d else None, "seconds": d.get("seconds") if d else None,
        "cost_usd": d.get("cost_usd") if d else None, "route": d.get("route") if d else None,
        "made_at": d.get("made_at") if d else None,
        "photos_changed": bool(d) and sorted(d.get("photo_ids") or []) != now,
        "about_usd": _about(d),
        "correcting": busy, "note": row["drawn_note"] if busy else last.get("note"),
        "corrected": corrected, "changed": last.get("changed"), "against_photos": last.get("against_photos"),
        "has_previous": d is not None and prev is not None,
        "previous_newer": d is not None and prev is not None and str(prev.get("made_at") or "") > str(d.get("made_at") or ""),
        "side": {"url": f"/api/items/{row['id']}/drawn/side.svg?v={side_version}",
                 "features": [f for f in side.get("features") or [] if isinstance(f, str)]} if side else None,
        "side_shown": side is not None and not row["trace_plain"],
    }


def _about(d: dict | None) -> float:
    """Roughly what drawing the shoe again costs on the API key: what its drawing cost (for a drawing changed from a
    note, the drawing it was changed from: `drawn_cost_usd`), or a typical drawing's."""
    usd = (d.get("drawn_cost_usd") if d.get("corrected") else d.get("cost_usd")) if d else None
    return round(usd, 2) if isinstance(usd, (int, float)) and not isinstance(usd, bool) and usd > 0 else ABOUT_USD


def due(conn):
    """The waiting shoe to work on next: a correction from the owner's note (whatever its photos' views), or a drawing
    whose photos are sorted."""
    return conn.execute(f"SELECT * FROM items WHERE drawn_state = 'waiting' AND category IN {SHOES} "
                        f"AND (drawn_note IS NOT NULL OR views_state = 'sorted') ORDER BY updated_at, id LIMIT 1"
                        ).fetchone()


def note_waiting(conn, why: str | None) -> None:
    """Tell the shoes waiting to be drawn or changed what holds them up (`why`: NO_ROUTE or LIMIT, said the matching
    way to a correction), or stop saying so when `why` is None."""
    marks = ",".join("?" * len(_WAIT_NOTES))
    if why:
        conn.execute(f"UPDATE items SET drawn_error = CASE WHEN drawn_note IS NULL THEN ? ELSE ? END "
                     f"WHERE drawn_state = 'waiting' AND category IN {SHOES} "
                     f"AND (drawn_error IS NULL OR drawn_error IN ({marks}))",
                     (why, _CORRECT_WAIT.get(why, why), *_WAIT_NOTES))
    else:
        conn.execute(f"UPDATE items SET drawn_error = NULL WHERE drawn_state = 'waiting' AND drawn_error IN ({marks})",
                     _WAIT_NOTES)


def recover(conn) -> None:
    """A drawing or a correction interrupted by a quit starts again (a correction keeps its note), unless it has
    used its tries already: a drawing takes minutes, so one cut short at every start would otherwise be paid for
    again at every start, for ever."""
    conn.execute("UPDATE items SET drawn_state = 'failed', drawn_error = ? WHERE drawn_state = 'drawing' AND drawn_attempts >= ?",
                 (FAILED, MAX_ATTEMPTS))
    conn.execute("UPDATE items SET drawn_state = CASE WHEN drawn IS NOT NULL THEN 'done' END, drawn_error = ?, drawn_note = NULL "
                 "WHERE drawn_state = 'correcting' AND drawn_attempts >= ?", (CORRECT_FAILED, MAX_ATTEMPTS))
    conn.execute("UPDATE items SET drawn_state = 'waiting' WHERE drawn_state IN ('drawing', 'correcting')")


def style_of(row) -> str | None:
    """The item's shoe style as its description says it (with the owner's corrections), for turning its drawing with
    the right 3D solid; None when it cannot be read (the drawing's own sheet is read instead)."""
    try:
        from .illustrations import drawn_answer
        from .tagger.schema import ItemTags, drawing_for

        answer = drawn_answer(row)
        if not isinstance(answer, dict):
            return None
        return drawing_for(ItemTags.model_validate(answer))[1].get("style")
    except Exception:   # an answer from an older schema, or none: the sheet says
        return None


def side_measures(row) -> dict | None:
    """The shoe's heights as shares of its length, measured from its trace (`drawnside.measures`), for drawing its
    side; None when it has no finished trace or it cannot be read."""
    from .drawing import drawnside

    if row["trace_state"] != "done":
        return None
    shoe = tracejobs.shoe_of(row)
    m = drawnside.measures(shoe.profile) if shoe is not None else None
    return m.to_json() if m is not None else None


def side_of(kept) -> dict | None:
    """The side entry of a drawing as kept with the item, when it has one that can be shown."""
    side = kept.get("side") if isinstance(kept, dict) else None
    return side if isinstance(side, dict) and isinstance(side.get("svg"), str) and side["svg"].strip() else None


def _open(images_dir: Path, photos: list) -> list[Photo]:
    if not photos:
        raise LookupError("the shoe has no photo")
    out = []
    for p in photos:
        with Image.open(images_dir / p["original_path"]) as im:
            out.append(Photo(im.convert("RGB"), p["view"], None if p["view_sure"] is None else bool(p["view_sure"])))
    return out


class _NothingToChange(Exception):
    """The drawing a correction was to change is not there any more."""


def _no_corrector(photos, kept, note, routes):
    raise RouteUnavailable("no one is set to change drawings")


def run_one(conn, images_dir: Path, routes: tuple[str, ...], drawer: Drawer, corrector: Corrector = _no_corrector) -> str:
    """Draw the shoe that is due first (`due`), or make the correction it waits for. Returns 'empty' (none is due),
    'done' (one was worked on) or 'blocked' (Claude could not be reached after all: it waits again and keeps its
    attempts). The drawing it had is kept as the one before (`drawn_prev`)."""
    conn.execute("BEGIN IMMEDIATE")
    row = due(conn)
    if row is None:
        conn.execute("COMMIT")
        return "empty"
    item_id, note = row["id"], row["drawn_note"]
    working = "correcting" if note else "drawing"
    conn.execute("UPDATE items SET drawn_state = ?, drawn_attempts = drawn_attempts + 1 WHERE id = ?", (working, item_id))
    photos = shoeviews.photos_of(conn, item_id)
    conn.execute("COMMIT")
    attempts = row["drawn_attempts"] + 1
    kept = _drawn(row)
    notes = notes_of(kept) if kept else []
    try:
        if note:
            if kept is None:
                raise _NothingToChange("the shoe has no drawing to change")
            made = corrector(_open(images_dir, photos), kept, note, routes)
        else:   # the owner's notes on the drawing it replaces are kept to
            made = drawer(_open(images_dir, photos), routes, notes=[n["note"] for n in notes], style=style_of(row),
                          measures=side_measures(row))
        if not isinstance(made, Drawn):
            raise TypeError("the drawer did not return a drawing")
    except (RouteUnavailable, Unreachable) as e:   # out of reach (no route, no network, overloaded): it waits
        # nothing is wrong with the shoe: Claude cannot be reached right now, so it waits without losing an attempt
        log.info("%s a shoe is waiting: no route to Claude can be used right now", working)
        conn.execute("UPDATE items SET drawn_state = 'waiting', drawn_attempts = max(0, drawn_attempts - 1) "
                     "WHERE id = ? AND drawn_state = ?", (item_id, working))
        note_waiting(conn, LIMIT if isinstance(e, CapReached) else NO_ROUTE)
        return "blocked"
    except Exception as e:   # recorded against the item, never lost; only its kind is logged
        log.warning("%s a shoe failed (attempt %s): %s", working, attempts, type(e).__name__)
        missing = isinstance(e, (LookupError, OSError))
        given_up = missing or attempts >= MAX_ATTEMPTS or isinstance(e, _NothingToChange)
        if note and given_up:   # the drawing stays as it was, and the page says the change could not be made
            conn.execute("UPDATE items SET drawn_state = ?, drawn_error = ?, drawn_note = NULL WHERE id = ? "
                         "AND drawn_state = 'correcting'",
                         ("done" if kept else None, CORRECT_NO_PHOTO if missing else CORRECT_FAILED, item_id))
        else:
            conn.execute("UPDATE items SET drawn_state = ?, drawn_error = ? WHERE id = ? AND drawn_state = ?",
                         ("failed" if given_up else "waiting", (NO_PHOTO if missing else FAILED) if given_up else None,
                          item_id, working))
        if given_up:
            failures.report(conn, item_id, "correction of its drawing from the owner's note" if note
                            else "drawing from its photos", str(e))
        return "done"
    conn.execute("BEGIN IMMEDIATE")
    try:
        now_row = conn.execute("SELECT drawn_state FROM items WHERE id = ?", (item_id,)).fetchone()
        if now_row is not None and now_row["drawn_state"] == working:   # else deleted meanwhile
            at = db.now()
            new = made.to_json([p["id"] for p in photos], at, notes)
            if note and kept:   # what drawing it again would cost: the drawing this one was changed from
                new["drawn_cost_usd"] = kept.get("drawn_cost_usd") if kept.get("corrected") else kept.get("cost_usd")
                new["side"] = kept.get("side")   # a correction is of the front: the side stays as it is
                new["side_tries"] = kept.get("side_tries") or 0
            # the drawing it had becomes the one before (one level); a first drawing leaves none
            conn.execute("UPDATE items SET drawn_prev = COALESCE(drawn, drawn_prev), drawn = ?, drawn_state = 'done', "
                         "drawn_error = NULL, drawn_attempts = 0, drawn_note = NULL, updated_at = ? WHERE id = ?",
                         (json.dumps(new), at, item_id))
            illustrations.redraw(conn, item_id)   # its side, when it has one, is the item's drawing now
        note_waiting(conn, None)   # Claude could be reached: the others are no longer held up
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return "done"


def side_due(conn):
    """The shoe whose drawing is drawn its side next (`run_side`): a shoe with a drawing kept that has no side, has not
    used its `SIDE_TRIES`, and is neither waiting nor being drawn or changed; never one made for the demo closet. The
    oldest first."""
    rows = conn.execute(f"SELECT * FROM items WHERE drawn IS NOT NULL AND category IN {SHOES} "
                        "AND (drawn_state IS NULL OR drawn_state NOT IN ('waiting', 'drawing', 'correcting')) "
                        "ORDER BY updated_at, id").fetchall()
    for row in rows:
        kept = _drawn(row)
        if kept is None or side_of(kept) is not None or kept.get("route") == "demo":
            continue
        tries = kept.get("side_tries")
        if not isinstance(tries, int) or isinstance(tries, bool) or tries < SIDE_TRIES:
            return row
    return None


def _set_tries(conn, item_id: str, made_at, change: Callable[[int], int]) -> None:
    """Change the side's tries counted in the item's drawing, while it is still the drawing made at `made_at`."""
    row = conn.execute("SELECT drawn FROM items WHERE id = ?", (item_id,)).fetchone()
    kept = _drawn(row) if row is not None else None
    if kept is None or kept.get("made_at") != made_at:
        return
    tries = kept.get("side_tries") if isinstance(kept.get("side_tries"), int) else 0
    kept["side_tries"] = max(0, change(tries))
    conn.execute("UPDATE items SET drawn = ? WHERE id = ?", (json.dumps(kept), item_id))


def run_side(conn, images_dir: Path, routes: tuple[str, ...], sider: Sider) -> str:
    """Draw the side of the shoe that is due first (`side_due`) by itself, and keep it with its drawing. Returns
    'empty', 'done' or 'blocked' (Claude could not be reached: the try is given back). A side that fails uses a try; a
    missing photo uses them all. The side is kept only on the drawing it was made for: if the owner went back to the
    drawing before meanwhile, it goes with the drawing it was made for (now the one before)."""
    conn.execute("BEGIN IMMEDIATE")
    row = side_due(conn)
    if row is None:
        conn.execute("COMMIT")
        return "empty"
    item_id, kept = row["id"], _drawn(row)
    made_at = kept.get("made_at")
    _set_tries(conn, item_id, made_at, lambda n: n + 1)   # counted before: a quit in the middle still used it
    photos = shoeviews.photos_of(conn, item_id)
    conn.execute("COMMIT")
    try:
        side = sider(_open(images_dir, photos), routes, sheet=kept.get("sheet") if isinstance(kept.get("sheet"), dict)
                     else None, notes=[n["note"] for n in notes_of(kept)], measures=side_measures(row))
        if not isinstance(side, Sided):
            raise TypeError("the side drawer did not return a side drawing")
    except (RouteUnavailable, Unreachable):   # out of reach: it waits, without losing its try
        log.info("drawing a shoe's side is waiting: no route to Claude can be used right now")
        with _write(conn):
            _set_tries(conn, item_id, made_at, lambda n: n - 1)
        return "blocked"
    except Exception as e:   # only its kind is logged; the item's drawing stays as it is
        log.warning("drawing a shoe's side failed: %s", type(e).__name__)
        if isinstance(e, (LookupError, OSError)):   # a photo is missing: it is not tried again for this drawing
            with _write(conn):
                _set_tries(conn, item_id, made_at, lambda n: SIDE_TRIES)
        return "done"
    with _write(conn):
        now = conn.execute("SELECT drawn, drawn_prev FROM items WHERE id = ?", (item_id,)).fetchone()
        for column in ("drawn", "drawn_prev"):
            d = _drawn(now, column) if now is not None else None
            if d is not None and d.get("made_at") == made_at and side_of(d) is None:
                d["side"] = side.to_json(db.now())
                conn.execute(f"UPDATE items SET {column} = ? WHERE id = ?", (json.dumps(d), item_id))
                illustrations.redraw(conn, item_id)
                break
    return "done"


class _write:
    """One write transaction on `conn`, rolled back if it fails."""

    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        self.conn.execute("BEGIN IMMEDIATE")
        return self.conn

    def __exit__(self, kind, value, tb):
        if kind is None:
            self.conn.execute("COMMIT")
        elif self.conn.in_transaction:
            self.conn.execute("ROLLBACK")
        return False


class Worker:
    """One thread that draws the open closet's waiting shoes, and makes the owner's corrections, one at a time; when
    none waits, it draws the side of a shoe drawn without one (`sider`; none: not done). Never the demo's."""

    def __init__(self, cfg: Config, state: State, routes: Routes, drawer: Drawer, idle: float = 60,
                 corrector: Corrector = _no_corrector, sider: Sider | None = None):
        self.cfg, self.state, self.routes, self.drawer, self.idle = cfg, state, routes, drawer, idle
        self.corrector, self.sider = corrector, sider
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
        """Draw every waiting shoe whose photos are sorted, and make every correction waiting, then draw the side of
        every shoe drawn without one, until none is left or Claude cannot be reached. Returns how many were worked
        on."""
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
                waiting = due(conn) is not None
                if not waiting and (self.sider is None or side_due(conn) is None):
                    break
                routes = self.routes()   # asked before each shoe, so turning the API key off takes effect at once
                if not routes:
                    if waiting:
                        note_waiting(conn, NO_ROUTE)
                    break
                if waiting:
                    status = run_one(conn, self.cfg.images_dir(profile), routes, self.drawer, self.corrector)
                else:   # nothing else waits: a side drawn by itself, one at a time
                    status = run_side(conn, self.cfg.images_dir(profile), routes, self.sider)
                if status == "blocked":
                    break
                done += status == "done"
        finally:
            conn.close()
        return done
