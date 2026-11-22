"""The review queue: every new item, once, and the fields the tagger was unsure of that the owner has not set.

An item added and not yet checked by the owner (`items.checked_at` is null) is offered once, so the owner can say
what it is, give it its real name, its brand and its price, one piece at a time (`check`); the item page's own
changes to those count as a check too (`items.ESSENTIALS`, `corrections.put_kind`). Items kept before this count
as checked (migration 0039).

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

from . import corrections, db, history, items, kinds, look, vocab

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
        value = _claudes_shape(row) if field == "silhouette" else row[field]
        if value in (None, "", {}):
            continue
        out.append({"field": field, "value": value, "confidence": sure, "allowed": _allowed(field, value)})
    return out


def _claudes_shape(row) -> dict:
    """The shape to check: as the drawing shows it (`look.shape`), less the parts the owner's own details already
    decide, which are not Claude's guess any more."""
    mine = look.owner_parts(row)
    return {k: v for k, v in look.shape(row).items() if k not in mine}


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
        new = row["checked_at"] is None and row["cutout_state"] not in ("pending", "processing")
        if fields or new:
            queued.append((row, fields, new))
    # the new items first, then the others; each most doubtful first: the least sure field, then the most fields to
    # look at, then the newest
    queued.sort(key=lambda q: (not q[2], min((f["confidence"] for f in q[1]), default=1.0), -len(q[1])))
    out = []
    for row, fields, new in queued:
        url, picture = _picture(conn, row)
        kind = kinds.of_row(row)
        out.append({**items.summary(conn, row), "picture_url": url, "picture_kind": picture, "fields": fields,
                    "new": new, "brand": row["brand"], "price_cents": row["price_cents"],
                    "kind_by": kind["by"], "kind_confidence": kind["confidence"]})
    return {"count": len(out), "items": out, "waiting": len(waiting), "failed": len(failed),
            "waiting_items": waiting, "failed_items": failed}


def _check_fields(fields) -> None:
    if not isinstance(fields, list):
        raise items.ItemError("Send the fields to confirm as a list.")
    unknown = [f for f in fields if f not in REVIEWED]
    if unknown:
        raise items.ItemError(f"These fields cannot be confirmed: {', '.join(map(str, unknown))}. "
                              f"Choose from: {', '.join(REVIEWED)}.")


def _owned(row, fields) -> tuple[dict, dict]:
    """The item's sources and confidences with these fields made the owner's, their values unchanged."""
    source = json.loads(row["source"] or "{}")
    confidence = json.loads(row["confidence"] or "{}")
    for field in fields:
        value = json.loads(row[field] or "{}") if field == "silhouette" else row[field]
        if value in (None, "", {}):
            raise items.ItemError(f"This item has no {field} to confirm.")
        source[field], confidence[field] = "user", 1.0   # as when the owner changes it (items.update)
    return source, confidence


def confirm(conn, item_id: str, fields: list) -> dict:
    """Mark fields as the owner's without changing their values. Returns the item."""
    row = items.get(conn, item_id)
    _check_fields(fields)
    source, confidence = _owned(row, fields)
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


def check(conn, item_id: str, kind=None, changes=None, fields=()) -> dict:
    """The owner has gone through the item in the review ("That's right"), all at once or not at all: what it is
    becomes their word (`kind`, the one shown, chosen or Claude's; with no kind, the category Claude gave), the
    changes they made are saved (`changes`: its name, brand and price, and any doubtful field they changed), the
    doubtful fields they left as they were are confirmed (`fields`), and it counts as checked, so it leaves the queue
    unless a doubtful field is still Claude's. One entry in the history. Returns the item."""
    changes = dict(changes or {})
    if "status" in changes:
        raise items.ItemError("Archive an item from its page.")
    if kind is not None:
        corrections.check_kind(kind)
    _check_fields(list(fields))
    conn.execute("BEGIN IMMEDIATE")
    try:
        before = items.get(conn, item_id)
        if kind is not None:
            corrections.put_kind(conn, before, kind)
        if changes:
            items.update(conn, item_id, changes, record=False)
        row = items.get(conn, item_id)
        said = list(fields)
        if kind is None and json.loads(row["source"] or "{}").get("category") in TAGGER and row["category"]:
            said.append("category")   # no kind to confirm: what it is, in the coarse word Claude gave
        source, confidence = _owned(row, dict.fromkeys(said))
        t = db.now()
        conn.execute("UPDATE items SET source = ?, confidence = ?, checked_at = ?, updated_at = ? WHERE id = ?",
                     (json.dumps(source), json.dumps(confidence), t, t, item_id))
        history.record(conn, before, items.get(conn, item_id), "owner", "field")
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return items.detail(conn, items.get(conn, item_id))
