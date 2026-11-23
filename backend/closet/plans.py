"""Dress for another day: an outfit kept for a day ahead, and its pieces kept out of the laundry's way.

A plan is not a wear. "Wear this on Saturday" keeps the outfit for that date (one a day; a new one takes the old
one's place) and nothing else: no wear is recorded and nothing goes in the laundry until "I'm wearing this" on the
day itself. That morning Today opens on it (`closet/today.py`), its pieces that cannot be worn by then (in the
laundry, waiting to be mended, archived, gone) filled the way "Wear this again" fills one. A plan for a day that
has passed lapses quietly, worn or not. A day inside a saved trip is the trip's: it has that day's outfit already.

Kept out of the laundry's way: on the days before, Today does not offer a planned piece when wearing it then would
leave it in the laundry on the planned day, by the laundry's own rule (`closet/wears.py`: the wears a kind takes
before a wash, and the laundry day that washes what went in before it). A piece that would still be clean (a
jacket, shoes, a knit with wears to spare, or a laundry day in between) is offered as usual. `held` is that rule,
pure; the owner can still wear the piece by hand or build around it.

Where a piece is (`closet/away.py`): a day ahead counts a piece away as back when the owner expects it back before
that day, by the rule a trip packs by (`back_by`); one with no day said, or a later one, is not offered. On the
morning, a planned piece still away is filled like one in the laundry, and Today names it with where it is
(`today.again_of`'s `away`). Sending a planned piece away is never refused: the plan simply fills its place.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from . import db, items, outfits, wears

PLACES = outfits.PLACES
MAX_AHEAD_DAYS = 60       # a day can be dressed this many days ahead at most
MIN_PIECES = 2            # an outfit kept has at least this many pieces


def _err(message: str, status: int = 422) -> items.ItemError:
    return items.ItemError(message, status)


# ------------------------------------------------------------------ an outfit's pieces
def check_pieces(conn, value: object) -> dict:
    """An outfit's pieces by place, as Today's outfits give them, each one an item in the closet. Raises ItemError."""
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
    if len(flat) != len(set(flat)):
        raise _err("Each piece can be in the outfit once.")
    if len(flat) < MIN_PIECES:
        raise _err(f"An outfit has at least {MIN_PIECES} pieces.")
    if len(flat) > wears.MAX_AT_ONCE:
        raise _err(f"An outfit has at most {wears.MAX_AT_ONCE} pieces.")
    marks = ", ".join("?" for _ in flat)
    found = {r[0] for r in conn.execute(f"SELECT id FROM items WHERE id IN ({marks})", flat)}
    if set(flat) - found:
        raise _err("A piece of this outfit is not in your closet.", 404)
    return {**pieces, "accessories": list(acc)}


def ids_of(pieces: Mapping) -> list[str]:
    """Every piece of an outfit, in place order, then the accessories."""
    return [v for pl in PLACES if (v := pieces.get(pl))] + list(pieces.get("accessories") or [])


def gone_of(conn, pieces: Mapping) -> list[str]:
    """The pieces that have left the closet (deleted), sorted."""
    ids = ids_of(pieces)
    if not ids:
        return []
    present = {r[0] for r in conn.execute(f"SELECT id FROM items WHERE id IN ({', '.join('?' for _ in ids)})", ids)}
    return sorted(set(ids) - present)


# ------------------------------------------------------------------ the day
def check_day(value: object, today: date) -> date:
    """A day ahead to dress for: tomorrow or later, at most MAX_AHEAD_DAYS away. Raises ItemError."""
    try:
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError
        day = date.fromisoformat(value)
    except ValueError:
        raise _err("Give the day as YYYY-MM-DD, for example 2026-11-28.") from None
    if day <= today:
        raise _err("Choose a day after today. For today, wear the outfit.")
    if (day - today).days > MAX_AHEAD_DAYS:
        raise _err(f"A day can be dressed at most {MAX_AHEAD_DAYS} days ahead.")
    return day


def trip_on(conn, day: date) -> dict | None:
    """The saved trip that holds this day, if there is one: {id, place, first_day, last_day}."""
    r = conn.execute("SELECT id, place, first_day, last_day FROM trips WHERE first_day <= ? AND last_day >= ? "
                     "ORDER BY first_day, id LIMIT 1", (day.isoformat(), day.isoformat())).fetchone()
    if r is None:
        return None
    place = json.loads(r["place"]) if r["place"] else {}
    return {"id": r["id"], "place": place.get("name") if isinstance(place, dict) else None,
            "first_day": r["first_day"], "last_day": r["last_day"]}


# ------------------------------------------------------------------ storing and reading
def _shape(conn, r) -> dict:
    pieces = json.loads(r["pieces"])
    return {"day": r["day"], "pieces": pieces, "occasion": r["occasion"], "mood": r["mood"],
            "gone": gone_of(conn, pieces), "created_at": r["created_at"], "updated_at": r["updated_at"]}


def lapse(conn, today: date) -> int:
    """Plans for days that have passed go, worn or not. Returns how many."""
    return conn.execute("DELETE FROM day_plans WHERE day < ?", (today.isoformat(),)).rowcount


def get(conn, day: date) -> dict | None:
    r = conn.execute("SELECT * FROM day_plans WHERE day = ?", (day.isoformat(),)).fetchone()
    return _shape(conn, r) if r else None


def upcoming(conn, today: date) -> list[dict]:
    """Today's plan and those of the days ahead, soonest first (plans for days gone lapse first)."""
    lapse(conn, today)
    return [_shape(conn, r) for r in conn.execute("SELECT * FROM day_plans WHERE day >= ? ORDER BY day",
                                                  (today.isoformat(),))]


def save(conn, day_value: object, pieces: object, occasion: object = None, mood: object = None,
         today: date | None = None) -> dict:
    """Keep an outfit for a day ahead: {plan, replaced}. `replaced` is the plan it took the place of (for Undo), or
    None. A day inside a saved trip is refused: the trip has that day's outfit."""
    today = today or wears.today()
    day = check_day(day_value, today)
    if occasion is not None and occasion not in outfits.FORMALITY:
        raise _err(f"'{occasion}' is not an occasion.")
    if mood is not None and mood not in outfits.MOODS:
        raise _err(f"'{mood}' is not a mood.")
    trip = trip_on(conn, day)
    if trip:
        where = f" to {trip['place'].split(',')[0]}" if trip.get("place") else ""
        raise _err(f"That day is part of your trip{where}, which has its outfit already.", 409)
    checked = check_pieces(conn, pieces)
    try:
        conn.execute("BEGIN IMMEDIATE")
        before = get(conn, day)
        t = db.now()
        conn.execute("INSERT INTO day_plans (day, pieces, occasion, mood, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?) "
                     "ON CONFLICT(day) DO UPDATE SET pieces = excluded.pieces, occasion = excluded.occasion, "
                     "mood = excluded.mood, updated_at = excluded.updated_at",
                     (day.isoformat(), json.dumps(checked), occasion, mood, t, t))
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    lapse(conn, today)
    return {"plan": get(conn, day), "replaced": before}


def remove(conn, day_value: object, today: date | None = None) -> dict:
    """Take the plan for a day away: {removed} (the plan, for Undo)."""
    today = today or wears.today()
    try:
        day = date.fromisoformat(day_value) if isinstance(day_value, str) and len(day_value) == 10 else None
    except ValueError:
        day = None
    if day is None:
        raise _err("Give the day as YYYY-MM-DD, for example 2026-11-28.")
    plan = get(conn, day) if day >= today else None
    if plan is None:
        raise _err("There is no outfit planned for that day.", 404)
    conn.execute("DELETE FROM day_plans WHERE day = ?", (day.isoformat(),))
    return {"removed": plan}


# ------------------------------------------------------------------ kept out of the laundry's way
def stays_in_laundry(row: Mapping, wear_day: date, plan_day: date, policy: wears.Policy | None) -> bool:
    """Whether wearing the piece on `wear_day` would leave it in the laundry on `plan_day`, by the laundry's own rule:
    it goes in once its wears since the wash reach its kind's count, and comes out on the first laundry day after it
    went in (what went in before the laundry day began is washed that day). Never with the laundry off, for a kind
    that never goes in by itself (outer layers, shoes, accessories), or with wears to spare."""
    if policy is None:
        return False
    cap = policy.caps.get(row.get("category"))
    if not cap:
        return False
    if (row.get("wears_since_wash") or 0) + 1 < cap:
        return False
    if policy.day is None:
        return True   # nothing comes out by itself: it would wait for the owner
    return wears.next_laundry_day(policy.day, wear_day) > plan_day


def held(rows: Iterable[Mapping], plans: Iterable[Mapping], wear_day: date,
         policy: wears.Policy | None) -> dict[str, str]:
    """The planned pieces not to offer on `wear_day`: item id -> the day it is planned for (the soonest, when it is in
    more than one plan). Only plans for days after `wear_day` count."""
    by_id = {r["id"]: r for r in rows}
    out: dict[str, str] = {}
    for plan in sorted(plans, key=lambda p: p["day"]):
        day = date.fromisoformat(plan["day"])
        if day <= wear_day:
            continue
        for pid in ids_of(plan["pieces"]):
            row = by_id.get(pid)
            if row is not None and pid not in out and stays_in_laundry(row, wear_day, day, policy):
                out[pid] = plan["day"]
    return out


# ------------------------------------------------------------------ away by then
def back_before(row: Mapping, day: date) -> bool:
    """Whether an away piece is expected back before `day`: the rule a trip packs by (`trips.Planner._back_before`:
    on the day itself is too late). A piece with no day said, or a later one, is not."""
    until = row.get("away_until")
    return bool(row.get("away") and until and str(until) < day.isoformat())


def back_by(rows: list[dict], day: date) -> list[dict]:
    """The closet as it will be on a day ahead, for where pieces are: one away and expected back before that day is
    counted back, as coming back makes it (`away.bring_back`: clean from the cleaner's, mended from the tailor's); one
    away with no day said, or a later one, stays away and is not offered."""
    out = []
    for r in rows:
        if back_before(r, day):
            back = {**r, "away": None, "away_since": None, "away_until": None}
            if r["away"] == "cleaner":
                back.update(laundry="clean", wears_since_wash=0)
            elif r["away"] == "tailor" and r.get("condition") == "needs_repair":
                back["condition"] = None
            r = back
        out.append(r)
    return out


# ------------------------------------------------------------------ the routes
class PlanBody(BaseModel):
    pieces: dict
    occasion: str | None = None
    mood: str | None = None
    model_config = {"extra": "forbid"}


def router(conn_dep: Callable) -> APIRouter:
    r = APIRouter()

    @r.get("/api/plans")
    def list_plans(conn=Depends(conn_dep)):
        return {"plans": upcoming(conn, wears.today())}

    @r.put("/api/plans/{day}")
    def put_plan(day: str, body: PlanBody, conn=Depends(conn_dep)):
        return save(conn, day, body.pieces, body.occasion, body.mood)

    @r.delete("/api/plans/{day}")
    def delete_plan(day: str, conn=Depends(conn_dep)):
        return remove(conn, day)

    return r
