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

from . import db, details, history, illustrations, items, tagjobs, vocab
from .tagger.correcting import CorrectionResult
from .tagger.schema import NAMED_HEX
from .tagger.tagging import RouteUnavailable

log = logging.getLogger("closet.corrections")

SENTENCE_MAX = 500
WAITING = ("Claude can't be reached right now, so the sentence was not read. Nothing was changed. Try again later, "
           "or pick the details instead.")
FAILED = "Claude could not read the sentence this time. Nothing was changed. Try again, or pick the details instead."
SENT_TEXT = "Your sentence and the item's description (words only, no photo) were sent to Claude."
SENT_PHOTO = ("Your sentence, the item's description and its photo with the background removed were sent to Claude, "
              "because the sentence could not be understood without seeing the item.")
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
        if v != value:
            made = illustrations.make(row, {name: v}).svg
            svg = made if made and made != base else None
        out.append({"value": v, "words": details.words(name, v), "current": v == value, "svg": svg})
    return {"name": name, "title": details.title(name), "value": value, "words": details.words(name, value),
            "own": name in details.own(row), "choices": out}


# ----------------------------------------------------------- applying
def _split(row, changes: dict, fields_allowed: bool) -> tuple[dict, dict]:
    coarse, picked = {}, {}
    for name, value in changes.items():
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
        raise items.ItemError("Say which details to change.")
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


def understand(conn, images_dir: Path, item_id: str, sentence, routes: tuple[str, ...], corrector: Corrector) -> dict:
    """Ask Claude what the sentence changes. Nothing is applied: the owner confirms the changes first."""
    text = _clean_sentence(sentence)
    row = items.get(conn, item_id)
    if not routes:
        return {"state": "waiting", "message": WAITING, "changes": [], "sentence": text}
    allowed, now = _allowed(row), _description(row)
    sent = SENT_TEXT
    try:
        result = corrector(text, now, allowed, [], routes)
        answer = result.answer
        if answer.needs_photo and not answer.changes:
            try:
                photos = tagjobs._photos(conn, images_dir, item_id)[:1]
            except (LookupError, OSError):
                photos = []
            if photos:
                sent = SENT_PHOTO
                answer = corrector(text, now, allowed, photos, routes).answer
    except RouteUnavailable:
        return {"state": "waiting", "message": WAITING, "changes": [], "sentence": text}
    except Exception as e:   # never show or log what Claude was sent
        log.warning("a correction could not be read (%s)", type(e).__name__)
        return {"state": "failed", "message": FAILED, "changes": [], "sentence": text}
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
    if refused:
        unclear = " ".join(filter(None, [unclear, "Claude answered with values the app does not know, so they were left out: "
                                         + ", ".join(refused) + "."]))
    if not out and not unclear:
        unclear = "Nothing in that sentence changes the description."
    return {"state": "understood" if out else "not_understood", "changes": out, "not_understood": unclear or None,
            "sent": sent, "sentence": text, "message": None}


def confirm(conn, item_id: str, sentence, changes) -> dict:
    """Apply the changes the owner confirmed from a correction by sentence."""
    text = _clean_sentence(sentence)
    if not isinstance(changes, list) or not changes:
        raise items.ItemError("Confirm at least one change.")
    picked = {}
    for c in changes:
        if not isinstance(c, dict) or not isinstance(c.get("name"), str) or "value" not in c:
            raise items.ItemError("Each change needs a name and a value.")
        picked[c["name"]] = c["value"]
    return apply(conn, item_id, picked, kind="sentence", sentence=text)


# --------------------------------------------------------------- undoing
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
        for part in json.loads(entry["parts"]):
            name, was = part["name"], part["before"] or {}
            if part["target"] == "field":
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
        sets.update(source=json.dumps(source), confidence=json.dumps(confidence), own_details=details.dump(owner),
                    updated_at=db.now())
        conn.execute(f"UPDATE items SET {', '.join(f'{k} = ?' for k in sets)} WHERE id = ?", [*sets.values(), item_id])
        drawn = history.drawing_before(entry) if not later else None
        if drawn is not None:   # nothing changed since: the drawing it had (the demo's are drawn by hand)
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
