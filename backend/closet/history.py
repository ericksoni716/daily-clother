"""The history of an item's description: every change, with what it was before and after, when, and who made it.

A change is recorded when Claude's answer arrives (`tagjobs.apply_answer`), when
the owner changes one of the item's own fields that describe it (`items.update`),
picks a detail, or confirms a correction by sentence (`corrections.py`), and when
a change is undone. Each entry lists its parts: a field (its value, who set it
and how sure the tagger was), one of the owner's details (whether the owner set
it, and the value drawn), or Claude's answer itself. An entry can be undone
while it is still the latest change to everything it touched; undoing is a
change of its own, recorded the same way (`corrections.undo`).

Parts are found by comparing the item before and after, so whatever the route
of the change, the history says exactly what moved: a field's value, who set it
or how sure the tagger was (so the owner confirming a field, or giving the same
value again, is a change too: the field becomes theirs).

Each entry also keeps the drawing as it was before the change, with a
fingerprint of everything the drawing is made from (`drawn_state`), so an undo
that brings the item back to any earlier state brings back that state's drawing
(the demo closet's drawings were made in advance and cannot be drawn again).
"""
from __future__ import annotations

import hashlib
import json

from . import db, details, drawing, illustrations

# the item's own fields that describe it (all those an answer fills, `tagjobs.suggested_fields`); a change to one of
# them is recorded
DESCRIBED = ("name", "category", "color", "color_hex", "pattern", "formality", "season", "silhouette", "material")
ANSWER = ("tag_answer", "tag_schema_version", "tag_route", "tag_model", "tagged_at")
WHO = ("owner", "claude")
_MISSING = object()


def _json(text, default):
    try:
        return json.loads(text) if text else default
    except ValueError:
        return default


def field_state(row, field: str) -> dict:
    value = _json(row["silhouette"], {}) if field == "silhouette" else row[field]
    return {"value": value, "source": _json(row["source"], {}).get(field), "confidence": _json(row["confidence"], {}).get(field)}


def answer_state(row) -> dict:
    """The stored answer, and how sure Claude was of its details (kept with the field confidences)."""
    return {**{c: row[c] for c in ANSWER}, "details_confidence": _json(row["confidence"], {}).get("details")}


def drawn_state(row) -> str:
    """A fingerprint of everything the item's drawing is made from (`illustrations.make`)."""
    source = _json(row["source"], {})
    made_from = {"fields": [row[f] for f in ("category", "color", "color_hex", "pattern")],
                 "silhouette": _json(row["silhouette"], {}),
                 "owner": sorted(f for f in (*illustrations.SHOWN, "color_hex") if source.get(f) == illustrations.OWNER),
                 "answer": _json(row["tag_answer"], None), "details": details.own(row)}
    return hashlib.sha256(json.dumps(made_from, sort_keys=True).encode()).hexdigest()


def parts_between(before, after) -> list[dict]:
    """What changed in an item's description between two rows of it."""
    parts = []
    for f in DESCRIBED:
        b, a = field_state(before, f), field_state(after, f)
        if b != a:
            parts.append({"target": "field", "name": f, "before": b, "after": a})
    ob, oa = details.own(before), details.own(after)
    if ob != oa:
        sb, sa = illustrations.shown_details(before), illustrations.shown_details(after)
        for name in details.PICKABLE:
            if ob.get(name, _MISSING) != oa.get(name, _MISSING):
                parts.append({"target": "detail", "name": name,
                              "before": {"own": name in ob, "value": ob.get(name, details.shown(sb, name))},
                              "after": {"own": name in oa, "value": oa.get(name, details.shown(sa, name))}})
    if before["tag_answer"] != after["tag_answer"]:
        parts.append({"target": "answer", "name": "answer", "before": answer_state(before), "after": answer_state(after)})
    return parts


def record(conn, before, after, by: str, kind: str, sentence: str | None = None, undoes: int | None = None,
           always: bool = False) -> int | None:
    """Record what changed between `before` and `after` (rows of the same item). Returns the entry's id, or None
    when nothing in the description changed (unless `always`)."""
    parts = parts_between(before, after)
    if not parts and not always:
        return None
    drawn = {"svg": before["illustration_svg"], "version": before["illustration_version"], "notes": before["illustration_notes"],
             "state": drawn_state(before)}
    cur = conn.execute("INSERT INTO changes (item_id, at, by, kind, parts, sentence, drawing, undoes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (after["id"], db.now(), by, kind, json.dumps(parts), sentence, json.dumps(drawn), undoes))
    return cur.lastrowid


def key(part: dict) -> str:
    return f"{part['target']}:{part['name']}"


def entries(conn, item_id: str) -> list:
    """The item's history, oldest first, as stored."""
    return conn.execute("SELECT * FROM changes WHERE item_id = ? ORDER BY id", (item_id,)).fetchall()


def why_not(entry, later: list) -> str | None:
    """Why an entry cannot be undone now, in plain words; None when it can.

    A later change blocks it when it touched the same thing and is still in effect: a later change that was
    itself undone, and the undo that cancelled it, do not count (an undo that was undone again, putting the
    change back, does).
    """
    if entry["undone_by"] is not None:
        return "This change has been undone."
    parts = _json(entry["parts"], [])
    if not parts:
        return "Nothing to undo."
    if any(p["target"] == "answer" and not (p["before"] or {}).get("tag_answer") for p in parts):
        return "Claude's first description can't be undone; change what is wrong instead."
    touched = {key(p) for p in parts}
    standing: dict = {}   # the later entries still in effect, by id
    for e in later:
        if e["kind"] == "undo" and e["undoes"] in standing:
            del standing[e["undoes"]]   # the two cancel out
        else:
            standing[e["id"]] = e
    for e in standing.values():
        clash = [p for p in _json(e["parts"], []) if key(p) in touched]
        if clash:
            return f"The {_title(clash[0])} changed again later; undo that first."
    return None


def _title(part: dict) -> str:
    return "description" if part["target"] == "answer" else details.title(part["name"])


def _value(part: dict, side: str):
    state = part[side] or {}
    return state.get("value") if part["target"] != "answer" else None


def _public_part(part: dict) -> dict:
    out = {"target": part["target"], "name": part["name"], "title": _title(part)}
    if part["target"] == "answer":
        return {**out, "before": None, "after": None, "before_words": "", "after_words": "", "same": False}
    b, a = _value(part, "before"), _value(part, "after")
    same = b == a   # only who set it (or how sure the tagger was) changed
    if part["name"] == "silhouette" and isinstance(b, dict) and isinstance(a, dict):   # only the parts that changed
        moved = [k for k in dict.fromkeys([*b, *a]) if b.get(k) != a.get(k)]
        b, a = {k: b[k] for k in moved if k in b}, {k: a[k] for k in moved if k in a}
    return {**out, "before": b, "after": a, "before_words": details.words(part["name"], b),
            "after_words": details.words(part["name"], a), "same": same}


def listing(conn, item_id: str) -> list[dict]:
    """The item's history, newest first, in a form the item page can put into words."""
    rows = entries(conn, item_id)
    out = []
    for n, e in enumerate(rows):
        reason = why_not(e, rows[n + 1:])
        parts = _json(e["parts"], [])
        out.append({
            "id": e["id"], "at": e["at"], "by": e["by"], "kind": e["kind"], "sentence": e["sentence"],
            "undoes": e["undoes"], "undone": e["undone_by"] is not None, "can_undo": reason is None,
            "why_not": reason if e["undone_by"] is None else None,
            "first_description": any(p["target"] == "answer" and not (p["before"] or {}).get("tag_answer") for p in parts),
            # Claude growing more or less sure of a value it already gave is not worth a line
            "parts": [q for q in map(_public_part, parts) if not (q["same"] and e["by"] == "claude")],
        })
    out.reverse()
    return out


def drawing_for(conn, row) -> dict | None:
    """The drawing the item had when it was last exactly as it is now (in what the drawing is made from), if one
    is kept and was made by this program's drawing code."""
    state = drawn_state(row)
    for e in reversed(entries(conn, row["id"])):
        drawn = _json(e["drawing"], None)
        if isinstance(drawn, dict) and drawn.get("state") == state and drawn.get("version") == drawing.DRAWING_VERSION:
            return drawn
    return None
