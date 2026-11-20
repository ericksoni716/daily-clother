"""The owner's side of tracing a shoe (#206, shoe tracing stage 2b).

The owner's fixes to the traced drawing (`fix`), choosing
the plain drawing for a shoe (`set_plain`), tracing it again (`retrace`), a new photo in place of the old one
(`replace_photo`, the item page's "Retake the photo"), the shoe's other photos (`add_photo`, `remove_photo`: up to
five, sorted into views by Claude in the background, `shoeviews`), the owner's word on which view a photo shows
(`set_view`). The tracing itself runs in the cut-out queue (`tracejobs`).
"""
from __future__ import annotations

import json
from pathlib import Path

from . import db, illustrations, items, shoeviews, tracejobs
from .drawing import sideshoe
from .tagger.views import VIEWS

MAX_MARK_FIXES = 40

def _traced_row(conn, item_id: str):
    row = items.get(conn, item_id)
    if not tracejobs.wanted(row["category"]):
        raise items.ItemError("Only a shoe is traced from its photo.", 409)
    return row


def _save(conn, item_id: str, sets: dict) -> None:
    sets = {**sets, "updated_at": db.now()}
    conn.execute(f"UPDATE items SET {', '.join(f'{k} = ?' for k in sets)} WHERE id = ?", [*sets.values(), item_id])
    illustrations.redraw(conn, item_id)


_locked = items.locked


def fix(conn, item_id: str, body) -> dict:
    """One fix to the traced drawing. `body` is one of:
    {"part": name, "color": "#rrggbb" or null (back to the traced colour)};
    {"mark": index, "hide": true or false}; {"mark": index, "nudge": [cm towards the toe, cm up]};
    {"mark": index, "color": "#rrggbb" or null}; {"reset": true} (every fix undone).
    Fixes are kept apart from the trace (`items.trace_fixes`), so a new trace keeps them where they still fit."""
    if not isinstance(body, dict):
        raise items.ItemError("Send the fix as an object, for example {\"part\": \"toe_cap\", \"color\": \"#aa3322\"}.")

    def work():
        row = _traced_row(conn, item_id)
        if body.get("reset") is True:
            _save(conn, item_id, {"trace_fixes": None})
            return
        shoe = tracejobs.shoe_of(row)
        if row["trace_state"] != "done" or shoe is None:
            raise items.ItemError("This shoe has no traced drawing to fix.", 409)
        fixes = tracejobs.fixes_of(row)
        if "part" in body:
            names = [n for n, _ in sideshoe.parts(shoe)]
            if body["part"] not in names:
                raise items.ItemError(f"Choose one of the shoe's parts: {', '.join(names)}.")
            parts = {k: v for k, v in (fixes.get("parts") or {}).items() if isinstance(v, str)}
            color = body.get("color")
            if color is None:
                parts.pop(body["part"], None)
            elif sideshoe._hex(color):
                parts[body["part"]] = color.lower()
            else:
                raise items.ItemError("The colour must be like #aa3322.")
            fixes["parts"] = parts
        elif "mark" in body:
            i = body["mark"]
            if not isinstance(i, int) or isinstance(i, bool) or not 0 <= i < len(shoe.marks):
                raise items.ItemError("That mark is not on this shoe's drawing.", 404)
            m = shoe.marks[i]
            marks = [f for f in (fixes.get("marks") or []) if isinstance(f, dict)]
            current = sideshoe.mark_fixes(shoe, {"marks": marks})[i]
            if current is None:
                if len(marks) >= MAX_MARK_FIXES:
                    raise items.ItemError("This shoe has too many fixes; undo some first.")
                current = {"kind": m.kind, "u": round(m.u, 4), "h": round(m.h, 3)}
                marks.append(current)
            if "hide" in body:
                if not isinstance(body["hide"], bool):
                    raise items.ItemError("hide must be true or false.")
                current["hide"] = body["hide"]
            elif "nudge" in body:
                step = body["nudge"]
                if (not isinstance(step, list) or len(step) != 2
                        or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in step)):
                    raise items.ItemError("nudge must be two numbers: cm towards the toe and cm up.")
                dx, dy = sideshoe._move(current)
                current["move"] = [round(max(-sideshoe.MOVE_CM, min(sideshoe.MOVE_CM, dx + step[0])), 2),
                                   round(max(-sideshoe.MOVE_CM, min(sideshoe.MOVE_CM, dy + step[1])), 2)]
            elif "color" in body:
                if body["color"] is None:
                    current.pop("color", None)
                elif sideshoe._hex(body["color"]):
                    current["color"] = body["color"].lower()
                else:
                    raise items.ItemError("The colour must be like #aa3322.")
            else:
                raise items.ItemError("Say what to do with the mark: hide, nudge or color.")
            if not current.get("hide") and current.get("move") in (None, [0, 0], [0.0, 0.0]) and "color" not in current:
                marks.remove(current)   # back as traced: nothing left to keep
            fixes["marks"] = marks
        else:
            raise items.ItemError("Say which part or mark to fix, or send {\"reset\": true}.")
        fixes = {k: v for k, v in fixes.items() if v}
        _save(conn, item_id, {"trace_fixes": json.dumps(fixes) if fixes else None})

    _locked(conn, work)
    return items.detail(conn, items.get(conn, item_id))


def set_plain(conn, item_id: str, plain) -> dict:
    """The owner chooses the plain (template) drawing for this shoe, or the traced one again."""
    if not isinstance(plain, bool):
        raise items.ItemError("plain must be true or false.")
    _locked(conn, lambda: (_traced_row(conn, item_id), _save(conn, item_id, {"trace_plain": int(plain)})))
    return items.detail(conn, items.get(conn, item_id))


def retrace(conn, item_id: str) -> dict:
    """Trace the shoe from its photo again, in the background; the owner's fixes are kept."""
    def work():
        _traced_row(conn, item_id)
        if items._front(conn, item_id) is None:
            raise items.ItemError("This shoe has no photo to trace.", 409)
        tracejobs.mark(conn, item_id)
    _locked(conn, work)
    return items.detail(conn, items.get(conn, item_id))


_store = items.store_photo
_remove_files = items.remove_photo_files
_elsewhere = items.refuse_elsewhere


def replace_photo(conn, images_dir: Path, item_id: str, data: bytes, source_sha256: str | None = None,
                  demo: bool = False) -> dict:
    """A new photo of the shoe in place of the old one (the item page's "Retake the photo"): the background is
    removed again, Claude describes it again (not in the demo closet) and the shoe is traced again. The old trace
    goes, the owner's fixes stay. Photos sorted into views (or waiting to be) are sorted again, with the new one.
    The steps are shared with clothes (`items.replace_front`)."""
    return items.replace_front(conn, images_dir, item_id, data, source_sha256,
                               lambda row, sha: _traced_row(conn, item_id), demo=demo)


SAME_PHOTO = "This photo is already one of this shoe's photos."
TOO_MANY = (f"A shoe can have at most {shoeviews.MAX_EXTRA} more photos besides its main one. Remove one first.")
NOT_A_SHOE = "Only a shoe can have more photos."
MAIN_PHOTO = "The main photo can't be removed. Use \u201cRetake the photo\u201d to replace it."
NO_SUCH_PHOTO = "That photo is not one of this item's photos."


def _photo_row(conn, item_id: str):
    row = items.get(conn, item_id)
    if not shoeviews.may_have_photos(row["category"]):
        raise items.ItemError(NOT_A_SHOE, 409)
    return row


def add_photo(conn, images_dir: Path, item_id: str, data: bytes, view=None, source_sha256: str | None = None,
              demo: bool = False) -> dict:
    """Another photo of the shoe, besides its main one (at most `shoeviews.MAX_EXTRA`). Without `view` it is sorted
    into its view with the others, in the background (`shoeviews`). With `view` (front or top, the second photo of
    before) that is the owner's word, kept as theirs, and it replaces only an earlier photo the owner named the same.
    A shoe Claude has not described yet (just added from "A shoe" on Add) can have photos added too."""
    if view is not None and view not in shoeviews.OWNER_VIEWS:
        raise items.ItemError("Say where the photo is taken from: front or top, or leave it out and Nines sorts it.")
    source_sha256 = items.photo_hash(data, source_sha256)
    _photo_row(conn, item_id)
    photo_id, stored = _store(images_dir, item_id, data)
    old: list = []

    def work():
        _photo_row(conn, item_id)
        _elsewhere(conn, item_id, source_sha256)
        replaced = conn.execute("SELECT * FROM photos WHERE item_id = ? AND kind != 'front' AND view = ? "
                                "AND view_by = 'owner'", (item_id, view)).fetchall() if view else []
        gone = {p["id"] for p in replaced}
        if any(r["id"] not in gone for r in conn.execute("SELECT id FROM photos WHERE item_id = ? AND source_sha256 = ?",
                                                          (item_id, source_sha256))):
            raise items.ItemError(SAME_PHOTO, 409)
        extra = conn.execute("SELECT COUNT(*) FROM photos WHERE item_id = ? AND kind != 'front'", (item_id,)).fetchone()[0]
        if extra - len(gone) >= shoeviews.MAX_EXTRA:
            raise items.ItemError(TOO_MANY, 409)
        old.extend(replaced)
        conn.executemany("DELETE FROM photos WHERE id = ?", [(p,) for p in gone])
        conn.execute("INSERT INTO photos (id, item_id, kind, view, view_sure, view_by, original_path, thumb_path, width, "
                     "height, bytes, sha256, source_sha256, created_at) VALUES (?, ?, 'detail', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (photo_id, item_id, view, 1 if view else None, "owner" if view else None, stored.original_path,
                      stored.thumb_path, stored.width, stored.height, stored.bytes, stored.sha256, source_sha256, db.now()))
        conn.execute("UPDATE items SET updated_at = ? WHERE id = ?", (db.now(), item_id))
        shoeviews.changed(conn, item_id, demo)       # sorted again, with the new photo

    try:
        _locked(conn, work)
    except Exception:
        for name in (stored.original_path, stored.thumb_path):
            (images_dir / name).unlink(missing_ok=True)
        raise
    for p in old:
        _remove_files(images_dir, p)
    return items.detail(conn, items.get(conn, item_id))


def remove_photo(conn, images_dir: Path, item_id: str, photo_id: str, demo: bool = False) -> dict:
    """One of the shoe's other photos goes, with its files (never the main photo: that is retaken instead). The rest
    are sorted again."""
    gone: list = []

    def work():
        row = items.get(conn, item_id)
        photo = conn.execute("SELECT * FROM photos WHERE id = ? AND item_id = ?", (photo_id, item_id)).fetchone()
        if photo is None:
            raise items.ItemError(NO_SUCH_PHOTO, 404)
        if photo["kind"] == "front":
            raise items.ItemError(MAIN_PHOTO, 409)
        conn.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
        conn.execute("UPDATE items SET updated_at = ? WHERE id = ?", (db.now(), item_id))
        if shoeviews.may_have_photos(row["category"]):
            shoeviews.changed(conn, item_id, demo)
        gone.append(photo)

    _locked(conn, work)
    for p in gone:
        _remove_files(images_dir, p)
    return items.detail(conn, items.get(conn, item_id))


def set_view(conn, item_id: str, photo_id: str, view) -> dict:
    """The owner says which view a photo of the shoe shows (the item page's question about the outside): kept as
    theirs and never changed by sorting again (`shoeviews.answer`)."""
    if view not in VIEWS:
        raise items.ItemError(f"Choose the view: {', '.join(VIEWS)}.")

    def work():
        if not tracejobs.wanted(items.get(conn, item_id)["category"]):
            raise items.ItemError("Only a shoe's photos are sorted into views.", 409)
        if conn.execute("SELECT 1 FROM photos WHERE id = ? AND item_id = ?", (photo_id, item_id)).fetchone() is None:
            raise items.ItemError(NO_SUCH_PHOTO, 404)
        shoeviews.answer(conn, item_id, photo_id, view)

    _locked(conn, work)
    return items.detail(conn, items.get(conn, item_id))
