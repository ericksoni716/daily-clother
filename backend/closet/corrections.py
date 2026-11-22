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

from . import db, details, history, illustrations, items, kinds, look, palette, patjobs, tagjobs, tracejobs, vocab
from .tagger import surfaceform
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
    return {name: details.shown(shown, name) for name in details.names_of(row)}


def options(row) -> dict:
    """The details that can be set on this kind of garment, grouped, each with its current value."""
    kind = details.kind_of(row["category"])
    if kind is None:
        return {"kind": None, "groups": [], "message": NO_KIND}
    now, owner = _current(row), details.own(row)
    groups = []
    for group, names in details.BY_KIND[kind]:
        shown = [n for n in names if n in now]   # the details the item's kind has
        if shown:
            groups.append({"id": group, "title": details.GROUPS[group], "details": [
                {"name": n, "title": details.title(n), "value": now[n], "words": details.words(n, now[n]), "own": n in owner}
                for n in shown]})
    return {"kind": kind, "groups": groups, "message": None}


def choices(row, name: str) -> dict:
    """A detail's choices, with a small drawing of the item for each choice that changes the drawing. The kinds
    of garment (dozens of them) are offered in words only."""
    if name not in details.names_of(row):
        raise items.ItemError(f"The {details.title(name)} can't be set on this kind of item.", 404)
    value = _current(row)[name]
    drawn = name not in details.WORDED
    base = illustrations.make(row, {name: value}).svg if drawn else None
    out = []
    for v in details.values(name, row["category"]):
        svg = None
        if drawn and v != value:
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
        if name == "shade":   # the colour's shade decides the colour word and the drawn colour, however it is set
            coarse[name] = value
        elif name in details.FIELDS or name in details.SHAPES:
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


def apply(conn, item_id: str, changes: dict, kind: str = "detail", sentence: str | None = None,
          expected: dict | None = None) -> dict:
    """Set details (a value of None gives the detail back to Claude's answer) and, for a correction by sentence,
    the item's fields; draw the item again and keep the whole change as one entry in its history."""
    if not isinstance(changes, dict) or not changes:
        raise items.ItemError("Say which details to change, each with its new value.")
    conn.execute("BEGIN IMMEDIATE")
    try:
        before = items.get(conn, item_id)
        if expected:
            now = _description(before)
            if any(now.get(name, _UNSET) != was for name, was in expected.items()):
                raise items.ItemError(CHANGED, 409)
        changes = dict(changes)
        cloth = {name: _cloth_read(name, changes.pop(name)) for name in CLOTH if name in changes and kind == "sentence"}
        coarse, picked = _split(before, changes, kind == "sentence") if changes else ({}, {})
        if coarse:
            items.update(conn, item_id, coarse, record=False)
        if cloth:   # after the fields: a pattern word set in the same sentence does not put this cloth aside
            own = surfaceform.own_cloth(items.get(conn, item_id))
            for name, value in cloth.items():
                key = "surface" if name == "cloth" else "lettering"
                if value is None:
                    own.pop(key, None)
                else:
                    own[key] = value
            conn.execute("UPDATE items SET own_cloth = ?, updated_at = ? WHERE id = ?",
                         (json.dumps(own, sort_keys=True) if own else None, db.now(), item_id))
            if "cloth" in cloth:
                patjobs.mark(conn, item_id)   # drawn and measured again from the owner's cloth
        row = items.get(conn, item_id)
        allowed = details.names_of(row)
        owner = details.own(row)
        for name, value in picked.items():
            if name not in allowed:
                raise items.ItemError(f"The {details.title(name)} can't be set on this kind of item.")
            if value is None:
                owner.pop(name, None)
                continue
            try:
                owner[name] = details.coerce(name, value, row["category"])
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


def check_kind(kind) -> None:
    if not isinstance(kind, str) or kind not in kinds.KINDS:
        raise items.ItemError("Choose one of the kinds in the list.")


def put_kind(conn, before, kind: str) -> None:
    """The kind as the owner's word, inside the caller's transaction (no history: the caller records it). It also
    counts as the owner having checked the item (`items.ESSENTIALS`)."""
    item_id = before["id"]
    category = kinds.category_for(kind, before["category"])
    source = json.loads(before["source"] or "{}")
    confidence = json.loads(before["confidence"] or "{}")
    source["category"], confidence["category"] = "user", 1.0
    owner = details.own(before)
    owner["garment"] = kind
    t = db.now()
    conn.execute("UPDATE items SET category = ?, own_details = ?, source = ?, confidence = ?, updated_at = ?, checked_at = ? "
                 "WHERE id = ?", (category, details.dump(owner), json.dumps(source), json.dumps(confidence), t, t, item_id))
    tracejobs.mark(conn, item_id, again=False)
    illustrations.redraw(conn, item_id)


def set_kind(conn, item_id: str, kind) -> dict:
    """Say what the item is: a kind from the taxonomy. It is the owner's word (kept by "Describe it again"), the
    item's category follows from it so the outfits and What's missing read it as before, the details the kind does
    not have are hidden but kept, and the change is one entry in the history that can be undone."""
    check_kind(kind)
    conn.execute("BEGIN IMMEDIATE")
    try:
        before = items.get(conn, item_id)
        put_kind(conn, before, kind)
        history.record(conn, before, items.get(conn, item_id), "owner", "detail")
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
    for n in details.names_of(row):
        out[n] = [str(v) for v in details.values(n, row["category"])]
    return out


CLOTH = ("cloth", "lettering")   # rewritten whole by a sentence, kept as the owner's own (`items.own_cloth`)


def _text(value) -> str | None:
    return json.dumps(value, sort_keys=True) if value is not None else None


def _cloth_now(row) -> dict:
    """The cloth and lettering the item is drawn with now (the owner's over Claude's), as JSON text or None."""
    try:
        drawn = illustrations.drawn_answer(row) or {}
    except Exception:
        drawn = {}
    surface = drawn.get("surface") if surfaceform.kind_of(drawn.get("surface")) else None
    lettering = drawn.get("lettering") if isinstance(drawn.get("lettering"), list) else None
    return {"cloth": _text(surface), "lettering": _text(lettering)}


def _description(row) -> dict:
    """The item as a sentence is read against: its fields, and its look (`look`): the shape and the details as drawn,
    with the owner's corrections over Claude's."""
    sil = look.shape(row)
    out = {f: row[f] for f in details.FIELDS}
    out.update({f"silhouette.{k}": sil.get(k) for k in vocab.SILHOUETTE})
    out.update(_current(row))
    out.update(_cloth_now(row))
    return out


def _for_claude(now: dict) -> dict:
    """The description as Claude reads it: the cloth and lettering as data, not as text."""
    return {**now, **{k: json.loads(now[k]) if now.get(k) else None for k in CLOTH}}


def _cloth_changes(answer, now: dict) -> list[dict]:
    """The cloth and lettering a sentence rewrote, as changes for the owner to confirm."""
    out = []
    for name in CLOTH:
        said = getattr(answer, name, None)
        if said is None:
            continue
        value = said.model_dump(mode="json") if hasattr(said, "model_dump") else [x.model_dump(mode="json") for x in said]
        text = _text(value)
        if text == now.get(name) or (name == "lettering" and not value and not json.loads(now.get(name) or "null")):
            continue   # the same, or no lettering said where there was none
        out.append({"name": name, "title": details.title(name), "value": text, "before": now.get(name),
                    "before_words": details.words(name, now.get(name)), "after_words": details.words(name, text)})
    return out


def _cloth_read(name: str, value):
    """A confirmed cloth or lettering (JSON text) checked against the description's own form; None gives it back to
    Claude's description."""
    if value is None:
        return None
    try:
        data = json.loads(value) if isinstance(value, str) else value
        if name == "cloth":
            return surfaceform.Surface.model_validate(data).model_dump(mode="json")
        if not isinstance(data, list):
            raise ValueError
        return [surfaceform.Lettering.model_validate(x).model_dump(mode="json") for x in data]
    except ValueError:
        raise items.ItemError(f"The {name} could not be read.") from None


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
        result = corrector(text, _for_claude(now), allowed, [], routes)
        answer = result.answer
        if answer.needs_photo and not answer.changes and not _cloth_changes(answer, now):
            photos, no_photo = _photo(conn, images_dir, row)
            if photos:
                sent = SENT_PHOTO
                answer = corrector(text, _for_claude(now), allowed, photos, routes).answer
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
    out += _cloth_changes(answer, now)
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
    return apply(conn, item_id, picked, kind="sentence", sentence=text, expected=before)


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
                if name == "own_cloth":
                    sets[name] = json.dumps(value, sort_keys=True) if value else None
                    continue
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
        saved_pattern = illustrations._json(entry["drawing"], {}).get("pattern")
        restore_pattern = (("pattern" in sets or "tag_answer" in sets or "own_cloth" in sets) and isinstance(saved_pattern, dict)
                           and all(saved_pattern.get(field) == sets.get(field, row[field])
                                   for field in ("pattern", "tag_answer", "own_cloth")))
        if restore_pattern:
            sets.update({field: saved_pattern.get(field) for field in history.PATTERN})
            if sets["pattern_state"] == "working":
                sets["pattern_state"] = "waiting"
        sets.update(source=json.dumps(source), confidence=json.dumps(confidence), own_details=details.dump(owner),
                    updated_at=db.now())
        conn.execute(f"UPDATE items SET {', '.join(f'{k} = ?' for k in sets)} WHERE id = ?", [*sets.values(), item_id])
        if not restore_pattern and ("pattern" in sets or "tag_answer" in sets or "own_cloth" in sets):
            patjobs.mark(conn, item_id)
        if "category" in sets:
            tracejobs.mark(conn, item_id, again=False)
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
