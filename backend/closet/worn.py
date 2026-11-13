"""Outfits worn: which pieces were worn together on a day, what they were offered for, and how they went.

An outfit is recorded with its wears when the owner taps "I'm wearing this" (one transaction, see
`wear`), or by hand from pieces the owner chooses. The same pieces recorded again on the same day (from
another device, say) give back the outfit already there. The wear log stays the record of wears; an outfit
remembers which of its wears it added, so removing the outfit removes only those, or hands them on to
another outfit that day holding the same piece. A rating is one of `outfits.OUTFIT_RATINGS` with reasons
from `outfits.OUTFIT_REASONS`; `rated` gives them to the engine. A deleted item stays part of the outfits
it was worn in (listed in `gone`); an outfit with no piece left in the closet goes with its last one.
"""
from __future__ import annotations

import json
import math
import uuid

from . import db, items, outfits, wears

PLACES = outfits.PLACES
MAX_REASONS_TEXT = 30         # sentences kept from what the outfit was offered with
MAX_SENTENCE = 500            # characters per sentence kept; a longer one is shortened, ending in "…"
MAX_NOTE = 300                # characters in the note that goes with "other"
DEFAULT_PAGE = 20
MAX_PAGE = 100
RATED_READ = 200              # the newest rated outfits the engine learns from (older ones have been worn over)
MIN_PIECES = 2                # an outfit recorded by hand has at least this many pieces
# Order tops are layered in when an outfit is recorded by hand: lower goes under.
TOP_LAYER = {"tee": 0, "polo": 0, "shirt": 1, "sweater": 2, "hoodie": 2, "jacket": 3, "coat": 4}
CONTEXT_FIELDS = ("low_c", "high_c", "rain", "occasion", "mood")


def _err(message: str, status: int = 422) -> items.ItemError:
    return items.ItemError(message, status)


# ------------------------------------------------------------------ checking what is sent
def _check_pieces(value: object, ids: list[str]) -> dict:
    if not isinstance(value, dict):
        raise _err("Give the outfit's pieces by place, as today's outfits give them.")
    unknown = sorted(set(value) - set(PLACES) - {"accessories"})
    if unknown:
        raise _err(f"These are not places in an outfit: {', '.join(unknown)}.")
    pieces = {pl: value.get(pl) or None for pl in PLACES}
    acc = value.get("accessories") or []
    if not all(v is None or isinstance(v, str) for v in pieces.values()) or not isinstance(acc, list) \
            or not all(isinstance(a, str) and a for a in acc):
        raise _err("Each piece of the outfit must be an item id.")
    flat = [v for v in pieces.values() if v] + acc
    if len(flat) != len(set(flat)) or set(flat) != set(ids):
        raise _err("The outfit's pieces must be the items being worn, each once.")
    return {**pieces, "accessories": list(acc)}


def _check_context(value: object) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - set(CONTEXT_FIELDS):
        raise _err(f"The day an outfit was offered for has only {', '.join(CONTEXT_FIELDS)}.")
    out = {k: value.get(k) for k in CONTEXT_FIELDS}
    for k in ("low_c", "high_c"):
        v = out[k]
        if v is not None and (isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v)
                              or not outfits.TEMP_RANGE_C[0] <= v <= outfits.TEMP_RANGE_C[1]):
            raise _err("The day's temperatures must be numbers of degrees Celsius.")
    if out["rain"] is not None and not isinstance(out["rain"], bool):
        raise _err("Rain must be true or false.")
    if out["occasion"] is not None and out["occasion"] not in outfits.FORMALITY:
        raise _err(f"'{out['occasion']}' is not an occasion.")
    if out["mood"] is not None and out["mood"] not in outfits.MOODS:
        raise _err(f"'{out['mood']}' is not a mood.")
    return out


def _shorten(sentence: str) -> str:
    return sentence if len(sentence) <= MAX_SENTENCE else sentence[:MAX_SENTENCE - 1].rstrip() + "…"


def _check_sentences(value: object, what: str) -> list[str]:
    """The sentences an outfit was offered with. They are made from item names, which have no length limit,
    so too many or too long are cut down rather than refused: recording what was worn must not fail on them."""
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(s, str) for s in value):
        raise _err(f"The {what} must be a list of sentences.")
    return [_shorten(s) for s in value[:MAX_REASONS_TEXT]]


def _check_score(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
        raise _err("The score must be a whole number from 0 to 100.")
    return value


# ------------------------------------------------------------------ storing and reading
def _insert(conn, day: str, recorded_by: str, pieces: dict, context: dict | None, score: int | None,
            reasons: list[str], warnings: list[str], added: list[str], t: str) -> str:
    oid = uuid.uuid4().hex
    c = context or {}
    conn.execute(
        "INSERT INTO worn_outfits (id, worn_on, recorded_by, low_c, high_c, rain, occasion, mood, score, reasons, warnings, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (oid, day, recorded_by, c.get("low_c"), c.get("high_c"), None if c.get("rain") is None else int(c["rain"]),
         c.get("occasion"), c.get("mood"), score, json.dumps(reasons), json.dumps(warnings), t, t))
    rows = [(pl, pieces[pl], 0) for pl in PLACES if pieces.get(pl)]
    rows += [("accessory", a, n) for n, a in enumerate(pieces.get("accessories") or [])]
    for place, item_id, position in rows:
        conn.execute("INSERT INTO worn_outfit_pieces (outfit_id, item_id, place, position, added_wear) VALUES (?, ?, ?, ?, ?)",
                     (oid, item_id, place, position, 1 if item_id in added else 0))
    return oid


def _same_day_outfit(conn, day: str, ids: list[str]) -> str | None:
    """The outfit already recorded on that day with exactly these pieces, if there is one."""
    marks = ", ".join("?" for _ in ids)
    row = conn.execute(
        "SELECT o.id FROM worn_outfits o WHERE o.worn_on = ? "
        "AND (SELECT COUNT(*) FROM worn_outfit_pieces p WHERE p.outfit_id = o.id) = ? "
        f"AND NOT EXISTS (SELECT 1 FROM worn_outfit_pieces p WHERE p.outfit_id = o.id AND p.item_id NOT IN ({marks})) "
        "ORDER BY o.created_at, o.id LIMIT 1", (day, len(set(ids)), *ids)).fetchone()
    return row["id"] if row else None


def _store(conn, day: str, recorded_by: str, pieces: dict, context: dict | None, score: int | None,
           reasons: list[str], warnings: list[str], added: list[str], t: str) -> str:
    ids = [v for pl in PLACES if (v := pieces.get(pl))] + list(pieces.get("accessories") or [])
    same = _same_day_outfit(conn, day, ids)
    if same is None:
        return _insert(conn, day, recorded_by, pieces, context, score, reasons, warnings, added, t)
    for item_id in added:   # a wear removed by hand in between and recorded again belongs to this outfit
        conn.execute("UPDATE worn_outfit_pieces SET added_wear = 1 WHERE outfit_id = ? AND item_id = ?", (same, item_id))
    return same


def _shape(row, pieces_rows: list, present: set[str]) -> dict:
    pieces: dict = {pl: None for pl in PLACES}
    pieces["accessories"] = []
    for p in sorted(pieces_rows, key=lambda p: (p["position"], p["item_id"])):
        if p["place"] == "accessory":
            pieces["accessories"].append(p["item_id"])
        else:
            pieces[p["place"]] = p["item_id"]
    has_context = any(row[k] is not None for k in CONTEXT_FIELDS)
    return {
        "id": row["id"], "worn_on": row["worn_on"], "recorded_by": row["recorded_by"], "pieces": pieces,
        "context": {k: (bool(row[k]) if k == "rain" and row[k] is not None else row[k]) for k in CONTEXT_FIELDS} if has_context else None,
        "score": row["score"], "reasons": json.loads(row["reasons"] or "[]"), "warnings": json.loads(row["warnings"] or "[]"),
        "rating": row["rating"], "rating_reasons": json.loads(row["rating_reasons"] or "[]"), "rating_note": row["rating_note"],
        "rated_at": row["rated_at"], "created_at": row["created_at"],
        "gone": sorted(p["item_id"] for p in pieces_rows if p["item_id"] not in present),
    }


def _shape_all(conn, rows: list) -> list[dict]:
    if not rows:
        return []
    ids = [r["id"] for r in rows]
    by_outfit: dict[str, list] = {i: [] for i in ids}
    for p in conn.execute(f"SELECT * FROM worn_outfit_pieces WHERE outfit_id IN ({', '.join('?' for _ in ids)})", ids):
        by_outfit[p["outfit_id"]].append(p)
    pieces = sorted({p["item_id"] for ps in by_outfit.values() for p in ps})
    present = {r[0] for r in conn.execute(f"SELECT id FROM items WHERE id IN ({', '.join('?' for _ in pieces)})", pieces)}
    return [_shape(r, by_outfit[r["id"]], present) for r in rows]


def get(conn, outfit_id: str) -> dict:
    row = conn.execute("SELECT * FROM worn_outfits WHERE id = ?", (outfit_id,)).fetchone()
    if row is None:
        raise _err("That outfit is not in your list of worn outfits.", 404)
    return _shape_all(conn, [row])[0]


def list_outfits(conn, limit: int = DEFAULT_PAGE, before: str | None = None) -> dict:
    """Worn outfits, newest first: {outfits, next}. Pass `next` as `before` for the page after."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_PAGE:
        raise _err(f"Ask for 1 to {MAX_PAGE} outfits at a time.")
    args: list = []
    where = ""
    if before:
        parts = before.split("~")
        if len(parts) != 3:
            raise _err("That page marker is not one this list gave.")
        where = "WHERE (worn_on, created_at, id) < (?, ?, ?)"
        args = parts
    rows = conn.execute(f"SELECT * FROM worn_outfits {where} ORDER BY worn_on DESC, created_at DESC, id DESC LIMIT ?",
                        [*args, limit + 1]).fetchall()
    more = len(rows) > limit
    rows = rows[:limit]
    last = rows[-1] if rows else None
    return {"outfits": _shape_all(conn, rows),
            "next": f"{last['worn_on']}~{last['created_at']}~{last['id']}" if more and last else None}


def rated(conn, limit: int = RATED_READ) -> list[dict]:
    """The newest rated outfits, for the engine (`outfits.feedback_from`)."""
    rows = conn.execute("SELECT * FROM worn_outfits WHERE rating IS NOT NULL ORDER BY worn_on DESC, created_at DESC, id DESC LIMIT ?",
                        (limit,)).fetchall()
    return _shape_all(conn, rows)


# ------------------------------------------------------------------ recording
def wear(conn, item_ids: object, worn_on: str | None, outfit: object) -> dict:
    """Record the wears of an outfit and the outfit itself, all or nothing. `POST /api/wears` with `outfit`."""
    if not isinstance(outfit, dict) or set(outfit) - {"pieces", "context", "score", "reasons", "warnings"}:
        raise _err("Give the outfit as {pieces, context, score, reasons, warnings}.")
    ids = wears._ids(item_ids)
    pieces = _check_pieces(outfit.get("pieces"), ids)
    context = _check_context(outfit.get("context"))
    score = _check_score(outfit.get("score"))
    reasons = _check_sentences(outfit.get("reasons"), "reasons")
    warnings = _check_sentences(outfit.get("warnings"), "warnings")
    made: list[str] = []

    def store(day: str, recorded: list[str], t: str) -> None:
        made.append(_store(conn, day, "today", pieces, context, score, reasons, warnings, recorded, t))

    result = wears.add_many(conn, ids, worn_on, also=store)
    return {**result, "outfit": get(conn, made[0])}


def place_pieces(rows: list) -> dict:
    """Pieces chosen by hand, put in their places by category: tops are layered lightest first."""
    pieces: dict = {pl: None for pl in PLACES}
    pieces["accessories"] = []
    tops = []
    for r in rows:
        cat, name = r["category"], r["name"] or (r["category"] or "item").replace("_", " ")
        if cat in TOP_LAYER:
            tops.append(r)
        elif cat in outfits.PLACE_CATEGORIES["bottom"] or cat in outfits.PLACE_CATEGORIES["shoes"]:
            place = "bottom" if cat in outfits.PLACE_CATEGORIES["bottom"] else "shoes"
            if pieces[place]:
                raise _err("Choose one pair of shoes." if place == "shoes" else "Choose one thing for your legs.")
            pieces[place] = r["id"]
        elif cat in outfits.ACCESSORY_CATEGORIES:
            pieces["accessories"].append(r["id"])
        else:
            raise _err(f"The {name} has no category an outfit can use. Set its category first.")
    if len(tops) > 3:
        raise _err("Choose at most three layers on top.")
    tops.sort(key=lambda r: (TOP_LAYER[r["category"]], r["id"]))
    if tops:
        pieces["base"] = tops[0]["id"]
    if len(tops) == 3:
        pieces["mid"], pieces["outer"] = tops[1]["id"], tops[2]["id"]
    elif len(tops) == 2:
        pieces["outer" if tops[1]["category"] in outfits.PLACE_CATEGORIES["outer"] else "mid"] = tops[1]["id"]
    return pieces


def record_by_hand(conn, item_ids: object, worn_on: str | None) -> dict:
    """An outfit for a day dressed without the app: its wears are recorded too (those already there are kept)."""
    ids = wears._ids(item_ids)
    if len(ids) < MIN_PIECES:
        raise _err(f"Choose at least {MIN_PIECES} pieces worn together.")
    rows = [items.get(conn, i) for i in ids]
    pieces = place_pieces(rows)
    made: list[str] = []

    def store(day: str, recorded: list[str], t: str) -> None:
        made.append(_store(conn, day, "hand", pieces, None, None, [], [], recorded, t))

    wears.add_many(conn, ids, worn_on, also=store)
    return get(conn, made[0])


# ------------------------------------------------------------------ rating
def rate(conn, outfit_id: str, rating: object, reasons: object = None, note: object = None) -> dict:
    """Set, change or (with rating None) clear the rating of a worn outfit."""
    get(conn, outfit_id)
    if rating is not None and rating not in outfits.OUTFIT_RATINGS:
        raise _err(f"A rating is one of: {', '.join(outfits.OUTFIT_RATINGS)}.")
    reasons = reasons or []
    if not isinstance(reasons, list) or not all(r in outfits.OUTFIT_REASONS for r in reasons):
        raise _err(f"Reasons come from: {', '.join(outfits.OUTFIT_REASONS)}.")
    reasons = [r for r in outfits.OUTFIT_REASONS if r in reasons]   # each once, in a fixed order
    if rating is None and reasons:
        raise _err("Choose how the outfit went before giving reasons.")
    if note is not None and (not isinstance(note, str) or len(note) > MAX_NOTE):
        raise _err(f"The note can be up to {MAX_NOTE} characters.")
    note = (note or "").strip() or None
    if note and "other" not in reasons:
        raise _err("A note goes with the reason \"other\".")
    t = db.now()
    conn.execute("UPDATE worn_outfits SET rating = ?, rating_reasons = ?, rating_note = ?, rated_at = ?, updated_at = ? WHERE id = ?",
                 (rating, json.dumps(reasons), note, t if rating else None, t, outfit_id))
    return get(conn, outfit_id)


# ------------------------------------------------------------------ removing
def _held_elsewhere(conn, day: str, outfit_id: str | None) -> dict[str, str]:
    """item id -> the first other outfit that day holding it (the one a wear is handed on to)."""
    out: dict[str, str] = {}
    for r in conn.execute("SELECT p.item_id, o.id FROM worn_outfit_pieces p JOIN worn_outfits o ON o.id = p.outfit_id "
                          "WHERE o.worn_on = ? AND o.id IS NOT ? ORDER BY o.created_at, o.id", (day, outfit_id)):
        out.setdefault(r[0], r[1])
    return out


def _release(conn, outfit_id: str, day: str, flag: list[bool]):
    """Inside the transaction: hand the wears this outfit added, of pieces another outfit that day also
    holds, on to that outfit (so removing it later removes them), then forget the outfit."""
    def run(*_: object) -> None:
        held = _held_elsewhere(conn, day, outfit_id)
        for r in conn.execute("SELECT item_id FROM worn_outfit_pieces WHERE outfit_id = ? AND added_wear = 1", (outfit_id,)).fetchall():
            if r[0] in held:
                conn.execute("UPDATE worn_outfit_pieces SET added_wear = 1 WHERE outfit_id = ? AND item_id = ?", (held[r[0]], r[0]))
        flag.append(conn.execute("DELETE FROM worn_outfits WHERE id = ?", (outfit_id,)).rowcount == 1)
    return run


def _wears_of(conn, outfit_id: str, day: str) -> list[str]:
    """The wears removing this outfit removes: those it added, of pieces still in the closet that no
    other outfit that day holds."""
    held = _held_elsewhere(conn, day, outfit_id)
    return [r[0] for r in conn.execute(
        "SELECT p.item_id FROM worn_outfit_pieces p JOIN items i ON i.id = p.item_id "
        "WHERE p.outfit_id = ? AND p.added_wear = 1 ORDER BY p.item_id", (outfit_id,)) if r[0] not in held]


def _in_transaction(conn, fn) -> None:
    try:
        conn.execute("BEGIN IMMEDIATE")
        fn()
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


def _forget(conn, outfit_id: str, day: str, flag: list[bool], first: list[str] = ()) -> dict:
    ids = _wears_of(conn, outfit_id, day)
    ids.sort(key=lambda i: (first.index(i) if i in first else len(first), i))
    if ids:
        return wears.remove_many(conn, ids, day, also=_release(conn, outfit_id, day, flag))
    _in_transaction(conn, _release(conn, outfit_id, day, flag))
    return {"worn_on": day, "removed": [], "items": []}


def undo(conn, item_ids: object, worn_on: object, outfit_id: object) -> dict:
    """`POST /api/wears/remove` with `outfit_id`: the outfit goes with the wears it added (whichever device
    recorded them). If it was removed already, only the wears given that no other outfit holds go."""
    if not isinstance(outfit_id, str) or not outfit_id:
        raise _err("Give the outfit to remove as its id.")
    given = wears._ids(item_ids) if item_ids else []
    if not isinstance(worn_on, str):
        raise _err("Give the day of the wears to remove as YYYY-MM-DD.")
    day = wears._parse(worn_on).isoformat()
    flag: list[bool] = []
    row = conn.execute("SELECT worn_on FROM worn_outfits WHERE id = ?", (outfit_id,)).fetchone()
    if row is not None:
        result = _forget(conn, outfit_id, row["worn_on"], flag, given)
    else:
        held = _held_elsewhere(conn, day, None)
        left = [i for i in given if i not in held]
        result = wears.remove_many(conn, left, day) if left else {"worn_on": day, "removed": [], "items": []}
    return {**result, "outfit_removed": bool(flag and flag[0])}


def remove(conn, outfit_id: str) -> None:
    """Forget a worn outfit, with the wears recording it added (handed on if another outfit that day holds the piece)."""
    o = get(conn, outfit_id)
    _forget(conn, outfit_id, o["worn_on"], [])
