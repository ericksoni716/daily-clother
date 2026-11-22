"""Claude adding to a garment's drawing at the owner's word: the owner's side (DECISIONS, "Claude adds to a garment's
drawing").

The owner writes one line in Fix the details ("a small red patch on the left sleeve"); Claude draws it onto the
template's drawing (`tagger.adding`) and the parts are kept with the item (`items.additions`, read by
`illustrations.added_of`), drawn on its own drawing and, moved with the garment, on the As worn figure. The template
drawing stays under them: changing a detail or a newer drawing version draws the template again, with the parts
still over it (they are in the template's coordinates, so a detail that changes the garment's shape can leave them out
of place: the page says so, `moved`).

One line at a time: `start` keeps it (`additions_state` 'drawing') and a thread of its own draws it (`run`), so the
page can be left and the work goes on; the item's progress shows it (`progress`), and the page is read again once it is
done. The additions before the last change are kept, one level (`additions_prev`), and `back` swaps the two; `remove`
takes every addition off, kept the same way. A shoe is not drawn on here (its drawing by Claude has its own note), nor
a piece with no drawing, nor anything in the demo closet, which is never sent to Claude.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from PIL import Image

from . import db, illustrations
from .drawing import added
from .drawing import item as draw
from .drawing.figure import flat_shape
from .tagger import adding
from .tagger.tagging import CapReached, RouteUnavailable

log = logging.getLogger("closet.additions")

SHOWN_NOTES = 5        # the owner's latest lines shown under the drawing
DRAWING = "Claude is drawing it on: “{note}”. This takes a minute or two."
NO_ROUTE = "Claude can't be reached right now, so nothing was drawn. Send it again once it can be."
LIMIT = ("This month's spending limit for the API key has been reached, so nothing was drawn. Send it again once the "
         "limit allows it.")
FAILED = "Claude could not draw that on, so the drawing is as it was. Send it again, or say it another way."
STOPPED = "Nines was closed while Claude was drawing, so the drawing is as it was. Send it again."
NO_PHOTO = "The photo could not be read, so Claude drew from your words alone."
DEMO = "The demo closet is never sent to Claude, so nothing can be drawn onto its drawings."
SHOE = "A shoe's drawing is changed under “Drawn by Claude from its photos”, further down its page."
NO_DRAWING = "This piece has no drawing to add to yet."
BUSY = "Claude is already drawing onto this piece. Send the next line once that is done."
NO_PREVIOUS = "There is no other drawing to go back to."
NOTHING = "Nothing has been drawn onto this drawing."
MOVED = ("The drawing under what Claude added has changed since (a detail or a newer drawing), so the additions may "
         "sit a little out of place. Ask Claude to move them if they do.")

Adder = Callable[..., adding.Result]


# ---------------------------------------------------------------- what is kept

def _json(text) -> dict | None:
    try:
        v = json.loads(text) if text else None
    except ValueError:
        return None
    return v if isinstance(v, dict) else None


def _kept(row, column: str = "additions") -> dict | None:
    keys = row.keys() if hasattr(row, "keys") else row
    return _json(row[column]) if column in keys else None


def _parts(kept: dict | None) -> list[added.Added]:
    return added.read(kept.get("parts"))[0] if kept else []


def drawable(row) -> bool:
    """Whether the item's drawing is one Claude can add to: a template drawing (not a shoe's) that exists."""
    return row["category"] not in draw.SHOES and bool(row["illustration_svg"])


def base_of(row) -> str | None:
    """A short fingerprint of the template's shape the item is drawn on now (its outline), without the additions; None
    when it cannot be built. Kept with the additions, so the page can say when the shape under them changed."""
    try:
        shape = flat_shape(replace(illustrations.describe(row), added=()))
    except Exception:
        return None
    return hashlib.sha256(shape.outline.encode()).hexdigest()[:16]


# ---------------------------------------------------------------- the owner's requests

def start(conn, item_id: str, note, demo: bool = False) -> str:
    """Keep the owner's line to be drawn (inside the caller's transaction) and return it cleaned; the caller starts
    `run`. Raises `items.ItemError`: in the demo closet, for a shoe or a piece with no drawing, a line that is empty or
    too long, and while another line is being drawn."""
    from . import items

    row = items.get(conn, item_id)
    if demo:
        raise items.ItemError(DEMO, 409)
    if row["category"] in draw.SHOES:
        raise items.ItemError(SHOE, 409)
    if not drawable(illustrations.current(conn, row)):
        raise items.ItemError(NO_DRAWING, 409)
    try:
        text = adding.clean_note(note)
    except ValueError as e:
        raise items.ItemError(str(e)) from None
    if row["additions_state"] == "drawing":
        raise items.ItemError(BUSY, 409)
    conn.execute("UPDATE items SET additions_state = 'drawing', additions_job = ?, updated_at = ? WHERE id = ?",
                 (json.dumps({"note": text, "at": db.now()}), db.now(), item_id))
    return text


def back(conn, item_id: str) -> None:
    """Swap the additions and the ones before the last change (inside the caller's transaction), and draw the item
    again. Raises `items.ItemError` when there is nothing to go back to, or while a line is being drawn."""
    from . import items

    row = items.get(conn, item_id)
    if row["additions_state"] == "drawing":
        raise items.ItemError(BUSY, 409)
    if _kept(row, "additions_prev") is None:
        raise items.ItemError(NO_PREVIOUS, 409)
    conn.execute("UPDATE items SET additions = additions_prev, additions_prev = coalesce(additions, ?), "
                 "additions_state = NULL, additions_job = NULL, updated_at = ? WHERE id = ?",
                 (json.dumps({"parts": []}), db.now(), item_id))
    illustrations.redraw(conn, item_id)


def remove(conn, item_id: str) -> None:
    """Take every addition off the drawing (inside the caller's transaction), keeping them to go back to. Raises
    `items.ItemError` when there are none, or while a line is being drawn."""
    from . import items

    row = items.get(conn, item_id)
    if row["additions_state"] == "drawing":
        raise items.ItemError(BUSY, 409)
    if not _parts(_kept(row)):
        raise items.ItemError(NOTHING, 409)
    conn.execute("UPDATE items SET additions_prev = additions, additions = ?, additions_state = NULL, "
                 "additions_job = NULL, updated_at = ? WHERE id = ?",
                 (json.dumps({"parts": [], "at": db.now(), "removed": True}), db.now(), item_id))
    illustrations.redraw(conn, item_id)


def recover(conn) -> None:
    """A line being drawn when Nines stopped is not drawn: the page says so, and the owner sends it again (a drawing
    costs something, so it is not started again unasked)."""
    for row in conn.execute("SELECT id FROM items WHERE additions_state = 'drawing'").fetchall():
        _finish(conn, row["id"], "failed", STOPPED)


# ---------------------------------------------------------------- drawing it

def _photo(conn, images_dir: Path, row) -> Image.Image | None:
    """The front photo with its background removed, or the photo itself; None when there is none to read."""
    photo = conn.execute("SELECT cutout_path, original_path FROM photos WHERE item_id = ? "
                         "ORDER BY kind = 'front' DESC, created_at LIMIT 1", (row["id"],)).fetchone()
    if photo is None:
        return None
    for path in (photo["cutout_path"] if row["cutout_state"] == "ready" else None, photo["original_path"]):
        if not path:
            continue
        try:
            with Image.open(images_dir / path) as im:
                im.load()
                return im.convert("RGBA")
        except OSError:
            continue
    return None


def _finish(conn, item_id: str, state: str, message: str) -> None:
    """The line is done without a drawing: `state` failed or said, with what to tell the owner."""
    job = _kept(conn.execute("SELECT additions_job FROM items WHERE id = ?", (item_id,)).fetchone(), "additions_job") or {}
    job["message"] = message
    conn.execute("UPDATE items SET additions_state = ?, additions_job = ? WHERE id = ?", (state, json.dumps(job), item_id))


def draw_now(conn, images_dir: Path, item_id: str, adder: Adder) -> None:
    """Draw the owner's line kept on the item (`start`) and keep what Claude drew, then draw the item again. `adder`
    is `tagger.adding.add` with its routes and meter given (tests pass a stand-in). Never raises: what went wrong is
    kept for the page."""
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if row is None or row["additions_state"] != "drawing":
        return
    job = _kept(row, "additions_job") or {}
    note = job.get("note") or ""
    try:
        now = _kept(row) or {}
        notes = [n.get("note") for n in now.get("notes") or [] if isinstance(n, dict)]
        current = _parts(now)
        photo = _photo(conn, images_dir, row)
        shape = flat_shape(replace(illustrations.describe(row), added=()))

        def render(parts: list[added.Added]) -> str:
            made = illustrations.make({**dict(row), "additions": json.dumps({"parts": [p.as_json() for p in parts]})})
            if not made.svg:
                raise ValueError("the drawing could not be made")
            return made.svg
        result = adder(note, notes, photo, current, added.geometry(shape), shape.outline, render)
    except CapReached:
        _finish(conn, item_id, "failed", LIMIT)
        return
    except RouteUnavailable:
        _finish(conn, item_id, "failed", NO_ROUTE)
        return
    except Exception as e:   # never show or log what Claude was sent
        log.warning("drawing onto item %s failed (%s)", item_id, type(e).__name__)
        _finish(conn, item_id, "failed", FAILED)
        return
    said = result.said or None
    if photo is None:
        said = " ".join(filter(None, [said, NO_PHOTO]))
    if [p.as_json() for p in result.parts] == [p.as_json() for p in current]:
        _finish(conn, item_id, "said", said or "Claude drew nothing for that, so the drawing is as it was.")
        return
    at = db.now()
    kept = {
        "parts": [p.as_json() for p in result.parts],
        "notes": [*(now.get("notes") or []), {"note": note, "at": at, "said": said}],
        "said": said, "at": at, "base": base_of(row), "seconds": round(result.seconds, 1), "route": result.route,
        "checks": result.checks, "api_usd": round(result.api_usd, 4), "photo": photo is not None,
    }
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("UPDATE items SET additions_prev = coalesce(additions, ?), additions = ?, additions_state = NULL, "
                     "additions_job = NULL, updated_at = ? WHERE id = ? AND additions_state = 'drawing'",
                     (json.dumps({"parts": []}), json.dumps(kept), at, item_id))
        illustrations.redraw(conn, item_id)
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        log.exception("keeping what Claude drew onto item %s failed", item_id)
        _finish(conn, item_id, "failed", FAILED)


class Drawer:
    """Draws each owner's line on a thread of its own, with its own connection to the closet it was sent in. `adder`
    gives `tagger.adding.add` with its routes and meter (tests give a stand-in)."""

    def __init__(self, adder: Callable[[], Adder]):
        self._adder = adder
        self._threads: list[threading.Thread] = []

    def run(self, item_id: str, path: Path, images: Path) -> None:
        adder = self._adder()

        def work():
            conn = db.connect(path)
            try:
                draw_now(conn, images, item_id, adder)
            except Exception:
                log.exception("drawing onto an item failed")
            finally:
                conn.close()
        t = threading.Thread(target=work, name="add-to-drawing", daemon=True)
        self._threads = [x for x in self._threads if x.is_alive()] + [t]
        t.start()

    def join(self, timeout: float = 30.0) -> None:
        """Wait for the lines being drawn (tests, and a clean stop)."""
        for t in list(self._threads):
            t.join(timeout)


# ---------------------------------------------------------------- what the page is told

def _took(kept: dict) -> str | None:
    seconds, route = kept.get("seconds"), kept.get("route")
    if not isinstance(seconds, (int, float)) or route not in ("plan", "api"):
        return None
    checks = kept.get("checks") or 0
    how = "on your Claude plan" if route == "plan" else "on the API key"
    checked = (", checked against the photo" if kept.get("photo", True) else ", checked once") if checks else ""
    usd = kept.get("api_usd")
    cost = ""
    if isinstance(usd, (int, float)) and usd > 0:
        cost = f" · about ${usd:.2f}" + (" if drawn on the API key" if route == "plan" else "")
    return f"Drawn in {round(seconds)} s {how}{checked}{cost}."


def shown(row) -> dict | None:
    """What the item page shows of the additions, or None for a piece they are not offered for (a shoe).

    {state: idle | drawing | failed | said, note, message, parts: [what each is], notes: [{note, at, said}] (the latest
    first, at most SHOWN_NOTES), said, at, took, can_go_back, back_newer, can_remove, moved (a sentence when the
    template's shape under the parts changed since they were drawn, else None)}."""
    if row["category"] in draw.SHOES:
        return None
    kept, prev = _kept(row), _kept(row, "additions_prev")
    job = _kept(row, "additions_job") or {}
    state = row["additions_state"] or "idle"
    parts = _parts(kept)
    message = job.get("message")
    if state == "drawing":
        message = DRAWING.format(note=job.get("note") or "")
    base = kept.get("base") if kept else None
    notes = [n for n in (kept.get("notes") or []) if isinstance(n, dict)] if kept else []
    return {
        "state": state, "note": job.get("note"), "message": message,
        "parts": [p.what or p.role for p in parts], "notes": notes[::-1][:SHOWN_NOTES],
        "said": kept.get("said") if kept and parts else None, "at": kept.get("at") if kept else None,
        "took": _took(kept) if kept and parts else None,
        "can_go_back": prev is not None and state != "drawing",
        "back_newer": bool(prev and kept and (prev.get("at") or "") > (kept.get("at") or "")),
        "can_remove": bool(parts) and state != "drawing",
        "moved": MOVED if parts and base and base != base_of(row) else None,
    }
