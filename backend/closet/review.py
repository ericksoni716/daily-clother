"""The review queue: only the fields the tagger was unsure of, and the owner has not set.

After a bulk import most of what Claude says is right; checking every field of
every item would take an evening. Each answer carries how sure the tagger was of
each field (`confidence` on the item, copied from the stored answer), so the
queue shows a field only when that number is below the field's threshold and the
value is still the tagger's (`source` is "ai", or "demo" for the demo closet's
answers made in advance). Confirming a field makes it the owner's without
changing its value, so it never comes back, not even after "Describe it again"
(`tagjobs.apply_answer` never touches a field the owner has set). Skipping
changes nothing, so a skipped item is simply still there next time.

Archived items are not reviewed. Items still waiting to be described, or that
could not be described, are not in the queue; they are counted instead.
"""
from __future__ import annotations

import json

from . import db, history, items, vocab

# How sure the tagger has to be for a field to be left alone; below this the field is shown for review.
# Starting values from the phase 0 runs (docs/PHASE0.md): every wrong answer came with 0.8 or less, and one
# wrong colour (cream for white) with exactly 0.8. To be tuned once the owner's own photos have been through
# the bench; the reasoning is in docs/DECISIONS.md ("Review queue").
UNSURE_BELOW = {
    "category": 0.7,     # always right in the bench runs; still asked when the tagger itself says it is guessing
    "color": 0.85,       # where most mistakes were (cream or white, tan or grey marl), one of them at 0.8
    "pattern": 0.7,      # always right in the bench runs
    "formality": 0.8,    # a judgement call the tagger got wrong at 0.7
    "season": 0.8,       # likewise
    "silhouette": 0.7,   # one confidence covers all its parts (sleeve, neck, fit, ...); always right in the bench runs
}
REVIEWED = tuple(UNSURE_BELOW)            # also the order the fields are shown in
TAGGER = ("ai", "demo")                   # who filled a field when it is still the tagger's suggestion
WAITING = ("waiting", "working")


def _allowed(field: str, value):
    if field == "silhouette":
        return {k: vocab.SILHOUETTE[k] for k in value if k in vocab.SILHOUETTE}
    return vocab.ENUM_FIELDS[field]


def doubtful(row) -> list[dict]:
    """The fields of an item the owner has not set and the tagger was unsure of, in the order they are shown."""
    source = json.loads(row["source"] or "{}")
    confidence = json.loads(row["confidence"] or "{}")
    out = []
    for field in REVIEWED:
        sure = confidence.get(field)
        if source.get(field) not in TAGGER or not isinstance(sure, (int, float)) or sure >= UNSURE_BELOW[field]:
            continue
        value = json.loads(row[field] or "{}") if field == "silhouette" else row[field]
        if value in (None, "", {}):
            continue
        out.append({"field": field, "value": value, "confidence": sure, "allowed": _allowed(field, value)})
    return out


def _picture(conn, row) -> tuple[str | None, str | None]:
    """The biggest picture worth judging from: the cutout, else the photo, else the drawing."""
    photo = items._front(conn, row["id"])
    if photo is not None and photo["cutout_path"]:
        return f"/media/{photo['cutout_path']}", "cutout"
    if photo is not None:
        return f"/media/{photo['original_path']}", "photo"
    summary = items.summary(conn, row)
    if summary["illustration_url"]:
        return summary["illustration_url"], "illustration"
    return None, None


def _brief(row) -> dict:
    return {"id": row["id"], "name": row["name"], "category": row["category"]}


def queue(conn, describes: bool = True) -> dict:
    """The review queue, most doubtful item first, and how many items are waiting to be described or failed.

    `describes` is False for the demo closet, whose own uploads are never described, so an item whose
    cutout is still being made there is not waiting to be described.
    """
    queued, waiting, failed = [], [], []
    for row in conn.execute("SELECT * FROM items WHERE status = 'active' ORDER BY created_at DESC, id"):
        if row["tag_state"] in WAITING or (describes and row["tag_state"] == "none" and row["cutout_state"] in ("pending", "processing")):
            waiting.append(_brief(row))
            continue
        if row["tag_state"] == "failed":
            failed.append(_brief(row))
            continue
        fields = doubtful(row)
        if fields:
            queued.append((row, fields))
    # most doubtful first: the least sure field, then the most fields to look at, then the newest
    queued.sort(key=lambda q: (min(f["confidence"] for f in q[1]), -len(q[1])))
    out = []
    for row, fields in queued:
        url, kind = _picture(conn, row)
        out.append({**items.summary(conn, row), "picture_url": url, "picture_kind": kind, "fields": fields})
    return {"count": len(out), "items": out, "waiting": len(waiting), "failed": len(failed),
            "waiting_items": waiting, "failed_items": failed}


def confirm(conn, item_id: str, fields: list) -> dict:
    """Mark fields as the owner's without changing their values. Returns the item."""
    row = items.get(conn, item_id)
    unknown = [f for f in fields if f not in REVIEWED]
    if unknown:
        raise items.ItemError(f"These fields cannot be confirmed: {', '.join(map(str, unknown))}. "
                              f"Choose from: {', '.join(REVIEWED)}.")
    source = json.loads(row["source"] or "{}")
    confidence = json.loads(row["confidence"] or "{}")
    for field in fields:
        value = json.loads(row[field] or "{}") if field == "silhouette" else row[field]
        if value in (None, "", {}):
            raise items.ItemError(f"This item has no {field} to confirm.")
        source[field], confidence[field] = "user", 1.0   # as when the owner changes it (items.update)
    if fields:   # kept in the item's history like any change: the field is the owner's now
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("UPDATE items SET source = ?, confidence = ?, updated_at = ? WHERE id = ?",
                         (json.dumps(source), json.dumps(confidence), db.now(), item_id))
            history.record(conn, row, items.get(conn, item_id), "owner", "field")
            conn.execute("COMMIT")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
    return items.detail(conn, items.get(conn, item_id))
