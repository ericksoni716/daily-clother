"""Each item's drawing: made from what is known about the item and kept up to date.

The drawing is made from the item's stored tagger answer when there is one, and
from its coarse fields (category, colour, pattern, silhouette) when there is
not. Where the owner has set a field (`source[field] == "user"`), the drawing
follows the item's field, not the answer.

It is made again when tagging finishes (`tagjobs.apply_answer`), when the owner
changes a field it shows (`items.update`), and when it was made by older drawing
code than this program's (`drawing.DRAWING_VERSION`): such an item is drawn
again the first time it is asked for, so a template change never redraws a
whole closet at start-up. Drawing never fails an item: what could not be drawn
is kept, in plain words, for the item page.

The demo closet's drawings were made in advance by `tools/make_demo.py` (with
fills taken from the photos) and carry the version they were made with, so they
stay as they are until the owner changes a field they show.
"""
from __future__ import annotations

import json
import logging
import sqlite3

from . import drawing
from .drawing import item as draw
from .tagger.schema import SILHOUETTE_FIELDS

log = logging.getLogger("closet.illustrations")

# the item's own fields the drawing is made from; changing one of them draws the item again
SHOWN = frozenset(("category", "color", "color_hex", "pattern", "silhouette"))
OWNER = "user"
# the answer's details that say more than a silhouette field, and what they say when they leave it to that field:
# where the owner has changed the field, the drawing follows the owner's word
DETAIL_FOR = {"sleeve": {"sleeve_length": "na"}, "neck": {"neckline": "na", "collar": "none"},
              "fit": {"fit_detail": "regular"}, "shoe_height": {"shoe_style": "na"}}


def _json(text, default):
    try:
        return json.loads(text) if text else default
    except ValueError:
        return default


def _prepare(row) -> tuple[dict, str | None, bool]:
    source = _json(row["source"], {})
    silhouette = _json(row["silhouette"], {})
    answer = _json(row["tag_answer"], None)
    if not isinstance(answer, dict):
        return {"category": row["category"], "color": row["color"], "pattern": row["pattern"],
                "silhouette": silhouette, "details": {}}, row["color_hex"], False
    answer = dict(answer)
    for field in ("category", "color", "pattern"):
        if source.get(field) == OWNER:
            answer[field] = row[field]
    if source.get("silhouette") == OWNER and isinstance(silhouette, dict):
        said = answer.get("silhouette") if isinstance(answer.get("silhouette"), dict) else {}
        details = dict(answer["details"]) if isinstance(answer.get("details"), dict) else None
        for k, leave in DETAIL_FOR.items():
            if details is not None and silhouette.get(k) is not None and silhouette.get(k) != said.get(k):
                details.update(leave)
        if details is not None:
            answer["details"] = details
        # a field the owner left empty is the answer's
        answer["silhouette"] = {k: said.get(k) if silhouette.get(k) is None else silhouette.get(k) for k in SILHOUETTE_FIELDS}
    # the item's own colour, unless the owner chose a colour word and left the old swatch beside it
    own_hex = source.get("color_hex") == OWNER or source.get("color") != OWNER
    return answer, row["color_hex"] if own_hex else None, True


def description(row) -> dict:
    """The stored description with the owner's corrections and chosen swatch, for item and outfit drawings."""
    try:
        answer, color_hex, _ = _prepare(row)
        return {**answer, "color_hex": color_hex}
    except Exception:
        return {"category": row["category"], "color": row["color"], "color_hex": row["color_hex"],
                "silhouette": {}, "details": {}}


def make(row) -> draw.Drawing:
    """The drawing for an item row as it stands now. Never raises."""
    try:
        answer, color_hex, tagged = _prepare(row)
        uid = row["id"][:8]
        if not tagged:
            return draw.drawing_from_fields(answer["category"], color_hex, answer["pattern"], answer["silhouette"],
                                            color=answer["color"], uid=uid)
        return draw.drawing_from_answer(answer, color_hex, uid=uid)
    except Exception:   # never fail an item
        log.exception("could not draw an item")
        return draw.Drawing(None, (draw.NOT_MADE,))


def _store(conn, item_id: str, made: draw.Drawing) -> None:
    conn.execute("UPDATE items SET illustration_svg = ?, illustration_version = ?, illustration_notes = ? WHERE id = ?",
                 (made.svg, drawing.DRAWING_VERSION, json.dumps(list(made.not_drawn)) if made.not_drawn else None, item_id))


def redraw(conn, item_id: str) -> None:
    """Draw the item again from what it is now and keep it, inside the caller's transaction if there is one."""
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if row is not None:
        _store(conn, item_id, make(row))


def current(conn, row):
    """The item row with an up-to-date drawing: drawn now if it never was, or was drawn by older drawing code."""
    version = row["illustration_version"]
    if version is not None and version >= drawing.DRAWING_VERSION:
        return row
    made = make(row)
    try:
        _store(conn, row["id"], made)
    except sqlite3.Error:   # the closet is busy: shown now, kept the next time it is asked for
        log.warning("could not keep an item's new drawing; it is made again next time")
    return {**dict(row), "illustration_svg": made.svg, "illustration_version": drawing.DRAWING_VERSION,
            "illustration_notes": json.dumps(list(made.not_drawn)) if made.not_drawn else None}


def notes(row) -> list[str]:
    """What the item's drawing leaves out or shows only roughly, in plain words."""
    out = _json(row["illustration_notes"], [])
    return [n for n in out if isinstance(n, str)] if isinstance(out, list) else []
