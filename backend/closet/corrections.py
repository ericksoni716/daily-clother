"""Correcting an item's description: by picking a detail, by saying what is wrong, and by undoing a change.

The owner's details are kept apart from Claude's answer (`items.own_details`)
and laid over it when the item is drawn (`illustrations.drawn_answer`), so
"Describe it again" never undoes them. Picking offers, for the kind of garment,
each detail with its current value and its choices in plain words, with a small
drawing of the item for every choice that changes the drawing. A sentence is
turned into changes by Claude (`tagger/correcting.py`) and applied only when the
owner confirms them. Every change is kept in the item's history
(`history.py`), and one that is still the latest change to what it touched can
be undone.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

from PIL import Image

from . import db, details, history, illustrations, items, palette, tagjobs, vocab
from .tagger.correcting import CorrectionResult
from .tagger.schema import NAMED_HEX, ItemTags
from .tagger.tagging import CapReached, RouteUnavailable

log = logging.getLogger("closet.corrections")
_UNSET = object()

SENTENCE_MAX = 500
WAITING = ("Claude can't be reached right now, so the sentence was not read. Nothing was changed. Try again later, "
           "or pick the details instead.")
FAILED = "Claude could not read the sentence this time. Nothing was changed. Try again, or pick the details instead."
SENT_TEXT = "Your sentence and the item's description (words only, no photo) were sent to Claude."
SENT_PHOTO = ("Your sentence, the item's description and its photo with the background removed were sent to Claude, "
              "because the sentence could not be understood without seeing the item.")
LIMIT = ("This month's spending limit for the API key has been reached, and your Claude plan can't be used right now, "
         "so the sentence was not read. Nothing was changed. Pick the details instead, or raise the limit in Settings.")
# why the photo was not sent when Claude asked to see it; the photo with its background is never sent
PHOTO_NOT_READY = ("Claude needs to see the item to understand that, but its photo was not sent: its background has not "
                   "been removed yet. Try again in a moment, or pick the details instead.")
PHOTO_FAILED = ("Claude needs to see the item to understand that, but its photo was not sent: its background could not "
                "be removed, and a photo with its background is never sent. Pick the details instead.")
NO_PHOTO = "Claude needs to see the item to understand that, but it has no photo. Pick the details instead."
CHANGED = "The item has changed since Claude read your sentence. Nothing was changed; ask again."
NO_KIND = "There are no details to fix for this kind of item. Change what it is first."

# a corrector: (sentence, the item's description, the values each part may take, photos, routes) -> the answer
Corrector = Callable[[str, dict, dict, list, tuple], CorrectionResult]


# ------------------------------------------------------------- by picking
def _current(row) -> dict:
    shown = illustrations.shown_details(row)
    return {name: details.shown(shown, name) for name in details.names_for(row["category"])}


def options(row) -> dict:
    """The details that can be set on this kind of garment, grouped, each with its current value."""
    kind = details.kind_of(row["category"])
    if kind is None:
        return {"kind": None, "groups": [], "message": NO_KIND}
    now, owner = _current(row), details.own(row)
    groups = []
    for group, names in details.BY_KIND[kind]:
        groups.append({"id": group, "title": details.GROUPS[group], "details": [
            {"name": n, "title": details.title(n), "value": now[n], "words": details.words(n, now[n]), "own": n in owner}
            for n in names]})
    return {"kind": kind, "groups": groups, "message": None}


def choices(row, name: str) -> dict:
    """A detail's choices, with a small drawing of the item for each choice that changes the drawing."""
    if name not in details.names_for(row["category"]):
        raise items.ItemError(f"The {details.title(name)} can't be set on this kind of item.", 404)
    value = _current(row)[name]
    base = illustrations.make(row, {name: value}).svg
    out = []
    for v in details.values(name):
        svg = None
        if v != value and name not in details.WORDED:
            made = illustrations.make(row, {name: v}).svg
            svg = made if made and made != base else None
        out.append({"value": v, "words": details.words(name, v), "current": v == value, "svg": svg})
    return {"name": name, "title": details.title(name), "value": value, "words": details.words(name, value),
            "own": name in details.own(row), "choices": out}


# ----------------------------------------------------------- applying
def _plain_value(name, value) -> None:
    """A value sent for a detail or field must be a word, a whole number or nothing (anything else: a 422)."""
    if value is None or isinstance(value, str) or (isinstance(value, int) and not isinstance(value, bool)):
        return
    if isinstance(value, bool) and name in details.FEATURES:
        return
    raise items.ItemError(f"The value for “{name}” must be one word or a whole number.")


def _split(row, changes: dict, fields_allowed: bool) -> tuple[dict, dict]:
    coarse, picked = {}, {}
    for name, value in changes.items():
        if not isinstance(name, str):
            raise items.ItemError("Each change needs the name of a detail.")
        _plain_value(name, value)
        if name in details.FIELDS or name in details.SHAPES:
            if not fields_allowed:
                raise items.ItemError(f"'{name}' is not a detail; change it with the item's other fields.")
            if name.startswith("silhouette."):
                coarse.setdefault("silhouette", {})[name.split(".", 1)[1]] = value
            else:
                coarse[name] = value
                if name == "color":
                    coarse["color_hex"] = NAMED_HEX.get(value)
        elif name in details.PICKABLE:
            picked[name] = value
        else:
            raise items.ItemError(f"'{name}' is not a detail that can be changed.")
    return coarse, picked


def apply(conn, item_id: str, changes: dict, kind: str = "detail", sentence: str | None = None) -> dict:
    """Set details (a value of None gives the detail back to Claude's answer) and, for a correction by sentence,
    the item's fields; draw the item again and keep the whole change as one entry in its history."""
    if not isinstance(changes, dict) or not changes:
        raise items.ItemError("Say which details to change, each with its new value.")
    conn.execute("BEGIN IMMEDIATE")
    try:
        before = items.get(conn, item_id)
        coarse, picked = _split(before, changes, kind == "sentence")
        if coarse:
            items.update(conn, item_id, coarse, record=False)
        row = items.get(conn, item_id)
        allowed = details.names_for(row["category"])
        owner = details.own(row)
        for name, value in picked.items():
            if name not in allowed:
                raise items.ItemError(f"The {details.title(name)} can't be set on this kind of item.")
            if value is None:
                owner.pop(name, None)
                continue
            try:
                owner[name] = details.coerce(name, value)
            except ValueError as e:
                raise items.ItemError(str(e)) from None
        if picked:
            conn.execute("UPDATE items SET own_details = ?, updated_at = ? WHERE id = ?", (details.dump(owner), db.now(), item_id))
        illustrations.redraw(conn, item_id)
        history.record(conn, before, items.get(conn, item_id), "owner", kind, sentence=sentence)
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return items.detail(conn, items.get(conn, item_id))


# ------------------------------------------------------------ by saying
def _clean_sentence(sentence) -> str:
    text = " ".join(str(sentence or "").split())
    if not text:
        raise items.ItemError("Write what is wrong, for example “it has three buttons”.")
    if len(text) > SENTENCE_MAX:
        raise items.ItemError(f"Keep it shorter than {SENTENCE_MAX} characters.")
    return text


def _allowed(row) -> dict[str, list]:
    out: dict[str, list] = {f: list(vocab.ENUM_FIELDS[f]) for f in details.FIELDS}
    out.update({f"silhouette.{k}": list(v) for k, v in vocab.SILHOUETTE.items()})
    for n in details.names_for(row["category"]):
        out[n] = [str(v) for v in details.values(n)]
    return out


def _description(row) -> dict:
    sil = illustrations._json(row["silhouette"], {})
    out = {f: row[f] for f in details.FIELDS}
    out.update({f"silhouette.{k}": sil.get(k) for k in vocab.SILHOUETTE})
    out.update(_current(row))
    return out


def _photo(conn, images_dir: Path, row) -> tuple[list, str | None]:
    """The front photo with its background removed, or why it cannot be sent."""
    if row["cutout_state"] == "failed":
        return [], PHOTO_FAILED
    if row["cutout_state"] != "ready":
        return [], PHOTO_NOT_READY if row["cutout_state"] in ("pending", "processing") else NO_PHOTO
    photo = items._front(conn, row["id"])
    if photo is None or not photo["cutout_path"]:
        return [], NO_PHOTO
    try:
        with Image.open(images_dir / photo["cutout_path"]) as im:
            return [im.convert("RGBA")], None
    except OSError:
        return [], NO_PHOTO


def understand(conn, images_dir: Path, item_id: str, sentence, routes: tuple[str, ...], corrector: Corrector) -> dict:
    """Ask Claude what the sentence changes. Nothing is applied: the owner confirms the changes first."""
    text = _clean_sentence(sentence)
    row = items.get(conn, item_id)
    waiting = {"state": "waiting", "message": WAITING, "changes": [], "sentence": text, "limit": False}
    if not routes:
        return waiting
    allowed, now = _allowed(row), _description(row)
    sent, no_photo = SENT_TEXT, None
    try:
        result = corrector(text, now, allowed, [], routes)
        answer = result.answer
        if answer.needs_photo and not answer.changes:
            photos, no_photo = _photo(conn, images_dir, row)
            if photos:
                sent = SENT_PHOTO
                answer = corrector(text, now, allowed, photos, routes).answer
    except CapReached:
        return {**waiting, "message": LIMIT, "limit": True}
    except RouteUnavailable:
        return waiting
    except Exception as e:   # never show or log what Claude was sent
        log.warning("a correction could not be read (%s)", type(e).__name__)
        return {"state": "failed", "message": FAILED, "changes": [], "sentence": text, "limit": False}
    found: dict = {}
    refused = []
    for change in answer.changes:
        name, value = change.name, str(change.value).strip()
        if name not in allowed or value not in allowed[name]:
            refused.append(f"{details.title(name)} “{value}”" if name in allowed else f"“{name}”")
            continue
        found[name] = details.coerce(name, value) if name in details.PICKABLE else value
    out = []
    for name, value in found.items():
        if now.get(name) == value:
            continue
        out.append({"name": name, "title": details.title(name), "value": value, "before": now.get(name),
                    "before_words": details.words(name, now.get(name)), "after_words": details.words(name, value)})
    unclear = (answer.not_understood or "").strip()
    if no_photo:
        unclear = " ".join(filter(None, [unclear, no_photo]))
    if refused:
        unclear = " ".join(filter(None, [unclear, "Claude answered with values the app does not know, so they were left out: "
                                         + ", ".join(refused) + "."]))
    if not out and not unclear:
        unclear = "Nothing in that sentence changes the description."
    return {"state": "understood" if out else "not_understood", "changes": out, "not_understood": unclear or None,
            "sent": sent, "sentence": text, "message": None, "limit": False}


def confirm(conn, item_id: str, sentence, changes) -> dict:
    """Apply the changes the owner confirmed from a correction by sentence. A change that says what the value was
    when Claude read the sentence (`before`) is refused if the item has changed since."""
    text = _clean_sentence(sentence)
    if not isinstance(changes, list) or not changes:
        raise items.ItemError("Confirm at least one change.")
    picked, before = {}, {}
    for c in changes:
        if not isinstance(c, dict) or not isinstance(c.get("name"), str) or "value" not in c:
            raise items.ItemError("Each change needs a name and a value.")
        _plain_value(c["name"], c["value"])
        picked[c["name"]] = c["value"]
        if "before" in c:
            _plain_value(c["name"], c["before"])
            before[c["name"]] = c["before"]
    if before:
        now = _description(items.get(conn, item_id))
        if any(now.get(name, _UNSET) != was for name, was in before.items()):
            raise items.ItemError(CHANGED, 409)
    return apply(conn, item_id, picked, kind="sentence", sentence=text)


# --------------------------------------------------------------- undoing
def _given_back(row, sets: dict, source: dict, confidence: dict, fields: list[str]) -> None:
    """Fields an undo gives back to the tagger are what the answer the item has now says, as if that answer had
    come after the undo (`tagjobs.fill`): an answer that came since the change is not undone with it."""
    text = sets["tag_answer"] if "tag_answer" in sets else row["tag_answer"]
    if not text:
        return
    try:
        tags = ItemTags.model_validate_json(text)
    except ValueError:   # an answer from an older schema: leave the fields as they were
        return
    suggested = tagjobs.suggested_fields(tags)
    for field in fields:
        if field not in suggested:
            continue
        current = sets[field] if field in sets else row[field]
        if field == "silhouette":
            current = illustrations._json(current, {})
        filled = tagjobs.fill(tags, field, current, source.get(field), suggested)
        if filled is None:
            continue
        value, by, sure = filled
        sets[field] = json.dumps(value or {}) if field == "silhouette" else value
        if by is None:
            source.pop(field, None)
            confidence.pop(field, None)
            continue
        source[field] = by
        if sure is not None:
            confidence[field] = sure


def undo(conn, item_id: str, change_id: int) -> dict:
    """Put back what a change replaced, if it is still the latest change to everything it touched."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = items.get(conn, item_id)
        entry = conn.execute("SELECT * FROM changes WHERE id = ? AND item_id = ?", (change_id, item_id)).fetchone()
        if entry is None:
            raise items.ItemError("That change is not in this item's history.", 404)
        later = conn.execute("SELECT * FROM changes WHERE item_id = ? AND id > ? ORDER BY id", (item_id, change_id)).fetchall()
        reason = history.why_not(entry, later)
        if reason:
            raise items.ItemError(reason, 409)
        source = illustrations._json(row["source"], {})
        confidence = illustrations._json(row["confidence"], {})
        owner = details.own(row)
        sets: dict = {}
        fields = []
        for part in json.loads(entry["parts"]):
            name, was = part["name"], part["before"] or {}
            if part["target"] == "field":
                fields.append(name)
                value = was.get("value")
                sets[name] = json.dumps(value or {}) if name == "silhouette" else value
                for store, key in ((source, "source"), (confidence, "confidence")):
                    if was.get(key) is None:
                        store.pop(name, None)
                    else:
                        store[name] = was[key]
            elif part["target"] == "detail":
                if was.get("own"):
                    owner[name] = was.get("value")
                else:
                    owner.pop(name, None)
            elif part["target"] == "answer":
                sets.update({c: was.get(c) for c in history.ANSWER})
                if was.get("details_confidence") is None:
                    confidence.pop("details", None)
                else:
                    confidence["details"] = was["details_confidence"]
        if "tag_answer" in sets:   # an answer put back: what the undone one gave to other fields since goes with it
            fields = list(history.DESCRIBED)
        _given_back(row, sets, source, confidence, fields)
        sets.update(source=json.dumps(source), confidence=json.dumps(confidence), own_details=details.dump(owner),
                    updated_at=db.now())
        conn.execute(f"UPDATE items SET {', '.join(f'{k} = ?' for k in sets)} WHERE id = ?", [*sets.values(), item_id])
        palette.settle(conn, item_id)   # a colour given back to the tagger is the measured one, as after describing
        drawn = history.drawing_for(conn, items.get(conn, item_id))
        if drawn is not None:   # the item is as it was before some change: the drawing it had then (the demo's are made in advance)
            conn.execute("UPDATE items SET illustration_svg = ?, illustration_version = ?, illustration_notes = ? WHERE id = ?",
                         (drawn.get("svg"), drawn.get("version"), drawn.get("notes"), item_id))
        else:
            illustrations.redraw(conn, item_id)
        new = history.record(conn, row, items.get(conn, item_id), "owner", "undo", undoes=change_id, always=True)
        conn.execute("UPDATE changes SET undone_by = ? WHERE id = ?", (new, change_id))
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return {"item": items.detail(conn, items.get(conn, item_id)), "history": history.listing(conn, item_id)}
