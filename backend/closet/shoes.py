"""The owner's side of tracing a shoe (#206, shoe tracing stage 2b).

The owner's fixes to the traced drawing (`fix`), choosing
the plain drawing for a shoe (`set_plain`), tracing it again (`retrace`), a new photo in place of the old one
(`replace_photo`, the item page's "Retake the photo"), the optional second photo from the front or from above,
read for the shoe's front view (`add_view`), and which front view the figure draws (`set_front`). The tracing
itself runs in the cut-out queue (`tracejobs`).
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from . import db, illustrations, images, items, jobs, tracejobs
from .drawing import sideshoe

VIEWS = ("front", "top")   # the second photo of a shoe: from the front, or from above
FRONTS = ("shape", "photo")   # the shoe's front view on the figure (`drawing.frontshoe`'s FROM_SHAPE, FROM_PHOTO)
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


def _locked(conn, work):
    conn.execute("BEGIN IMMEDIATE")
    try:
        work()
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


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


def set_front(conn, item_id: str, kind) -> dict:
    """The owner chooses the shoe's front view on the outfit figure: "shape" (the template for its style, in the
    traced colours), "photo" (turned from its photos), or null (the default: "photo" when a front photo was
    measured, otherwise "shape")."""
    if kind is not None and kind not in FRONTS:
        raise items.ItemError("Choose the front view: shape or photo (or null for the default).")
    _locked(conn, lambda: (_traced_row(conn, item_id), _save(conn, item_id, {"shoe_front": kind})))
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


def _store(images_dir: Path, item_id: str, data: bytes):
    photo_id = uuid.uuid4().hex
    return photo_id, images.store_upload(data, images_dir, item_id, photo_id)


def _remove_files(images_dir: Path, photo) -> None:
    for key in ("original_path", "thumb_path", "cutout_path", "cutout_thumb_path"):
        if photo[key]:
            (images_dir / photo[key]).unlink(missing_ok=True)


def _elsewhere(conn, item_id: str, source_sha256: str) -> None:
    other = conn.execute("SELECT item_id FROM photos WHERE source_sha256 = ? AND item_id != ? LIMIT 1",
                         (source_sha256, item_id)).fetchone()
    if other is not None:
        raise items.ItemError("This photo is already in the closet, as another item.", 409)


def replace_photo(conn, images_dir: Path, item_id: str, data: bytes, source_sha256: str | None = None) -> dict:
    """A new photo of the shoe in place of the old one (the item page's "Retake the photo"): the background is
    removed again, Claude describes it again (not in the demo closet) and the shoe is traced again. The old trace
    goes, the owner's fixes stay."""
    source_sha256 = items.photo_hash(data, source_sha256)
    _traced_row(conn, item_id)
    photo_id, stored = _store(images_dir, item_id, data)
    old: list = []

    def work():
        _traced_row(conn, item_id)
        if conn.execute("SELECT 1 FROM jobs WHERE kind = 'cutout' AND item_id = ? AND state = 'running'",
                        (item_id,)).fetchone():
            raise items.ItemError("The photo is still being cut out; try again in a moment.", 409)
        _elsewhere(conn, item_id, source_sha256)
        old.extend(conn.execute("SELECT * FROM photos WHERE item_id = ? AND kind = 'front'", (item_id,)).fetchall())
        conn.execute("DELETE FROM jobs WHERE kind = 'cutout' AND item_id = ? AND state = 'queued'", (item_id,))
        conn.execute("DELETE FROM photos WHERE item_id = ? AND kind = 'front'", (item_id,))
        conn.execute("INSERT INTO photos (id, item_id, kind, original_path, thumb_path, width, height, bytes, sha256, "
                     "source_sha256, created_at) VALUES (?, ?, 'front', ?, ?, ?, ?, ?, ?, ?, ?)",
                     (photo_id, item_id, stored.original_path, stored.thumb_path, stored.width, stored.height,
                      stored.bytes, stored.sha256, source_sha256, db.now()))
        tracejobs.forget(conn, item_id)
        jobs.enqueue_cutout(conn, item_id, photo_id)
        illustrations.redraw(conn, item_id)

    try:
        _locked(conn, work)
    except Exception:
        for name in (stored.original_path, stored.thumb_path):
            (images_dir / name).unlink(missing_ok=True)
        raise
    for p in old:
        _remove_files(images_dir, p)
    return items.detail(conn, items.get(conn, item_id))


def add_view(conn, images_dir: Path, item_id: str, data: bytes, view, source_sha256: str | None = None) -> dict:
    """The shoe's second photo, from the front or from above, kept for its front view; it replaces an earlier one."""
    if view not in VIEWS:
        raise items.ItemError("Say where the photo is taken from: front or top.")
    source_sha256 = items.photo_hash(data, source_sha256)
    _traced_row(conn, item_id)
    photo_id, stored = _store(images_dir, item_id, data)
    old: list = []

    def work():
        _traced_row(conn, item_id)
        _elsewhere(conn, item_id, source_sha256)
        old.extend(conn.execute("SELECT * FROM photos WHERE item_id = ? AND view IS NOT NULL", (item_id,)).fetchall())
        conn.execute("DELETE FROM photos WHERE item_id = ? AND view IS NOT NULL", (item_id,))
        conn.execute("INSERT INTO photos (id, item_id, kind, view, original_path, thumb_path, width, height, bytes, sha256, "
                     "source_sha256, created_at) VALUES (?, ?, 'detail', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (photo_id, item_id, view, stored.original_path, stored.thumb_path, stored.width, stored.height,
                      stored.bytes, stored.sha256, source_sha256, db.now()))
        conn.execute("UPDATE items SET updated_at = ?, front_look = NULL WHERE id = ?", (db.now(), item_id))
        tracejobs.mark(conn, item_id)   # traced again, with the new photo read for the front view

    try:
        _locked(conn, work)
    except Exception:
        for name in (stored.original_path, stored.thumb_path):
            (images_dir / name).unlink(missing_ok=True)
        raise
    for p in old:
        _remove_files(images_dir, p)
    return items.detail(conn, items.get(conn, item_id))

