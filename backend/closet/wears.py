"""What was worn when, and whether an item is clean or in the laundry.

A wear is one item on one day (the computer's local date). Each item also keeps
how many wears were recorded since it was last marked clean; a wear removed
again only lowers that count if it was recorded after the wash.

Laundry that keeps itself (when the owner leaves it on in Settings): a piece goes
in the laundry by itself once worn as often as "Before it needs washing" allows
for its kind, and everything in the laundry is clean again on the owner's laundry
day. A wear removed again takes a piece back out if that wear put it in.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from . import db, items

LAUNDRY = ("clean", "laundry")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def today() -> date:
    """Today in the computer's local time (a function so tests can move the clock)."""
    return date.today()


@dataclass(frozen=True)
class Policy:
    """The owner's laundry that keeps itself. `caps`: for each category, the wears before it needs washing (a category
    missing, or None, never goes in by itself: shoes, accessories, jackets and coats by default). `day`: the laundry
    day, Monday 0 to Sunday 6, or None for no laundry day (pieces then come out only by hand)."""
    caps: dict = field(default_factory=dict)
    day: int | None = None


def _no_policy() -> Policy | None:
    return None


_policy: Callable[[], Policy | None] = _no_policy   # the app sets it from the owner's settings


def set_policy(get: Callable[[], Policy | None]) -> None:
    global _policy
    _policy = get


LAUNDRY_DEFAULT = {"auto": True, "day": 6}   # on, with Sunday as the laundry day, until the owner says otherwise
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def laundry_setting(value: object) -> dict:
    """The owner's laundry setting as stored, with the defaults for what was never set."""
    return {**LAUNDRY_DEFAULT, **value} if isinstance(value, dict) else dict(LAUNDRY_DEFAULT)


def check_laundry_setting(value: object) -> dict:
    """{"auto": bool, "day": 0-6 or null}; raises ItemError in the owner's words."""
    if not isinstance(value, dict) or set(value) - {"auto", "day"}:
        raise items.ItemError("Say whether the laundry keeps itself and on which day you do it, "
                              "for example {\"auto\": true, \"day\": 6}.")
    out = laundry_setting(value)
    if not isinstance(out["auto"], bool):
        raise items.ItemError("Say yes or no to clothes going in the laundry by themselves.")
    if out["day"] is not None and (isinstance(out["day"], bool) or out["day"] not in range(7)):
        raise items.ItemError("Choose a laundry day from Monday to Sunday, or none.")
    return out


def policy_from(setting: object, rewear: dict) -> Policy | None:
    """The policy for the owner's setting and their "Before it needs washing" counts (`trips` kinds); None when off."""
    from .trips import KIND_OF
    s = laundry_setting(setting)
    if not s["auto"]:
        return None
    return Policy(caps={category: rewear.get(kind) for category, kind in KIND_OF.items()}, day=s["day"])


def _cap(row) -> int | None:
    policy = _policy()
    return policy.caps.get(row["category"]) if policy else None


def _after_wear(conn, item_id: str, t: str) -> None:
    """Once its wears reach the count, a clean piece goes in the laundry by itself (inside the wear's transaction)."""
    row = items.get(conn, item_id)
    cap = _cap(row)
    if cap and row["laundry"] != "laundry" and row["status"] != "archived" and row["wears_since_wash"] >= cap:
        conn.execute("UPDATE items SET laundry = 'laundry', laundry_at = ?, laundry_by = 'auto', updated_at = ? WHERE id = ?",
                     (t, t, item_id))


def _after_unwear(conn, item_id: str, t: str, worn_at: str) -> None:
    """A wear removed again takes the piece back out of the laundry when that wear is the one that put it in (it went
    in by itself at the moment the wear was recorded); never one the owner put in by hand."""
    row = items.get(conn, item_id)
    if row["laundry"] == "laundry" and row["laundry_by"] == "auto" and row["laundry_at"] == worn_at:
        conn.execute("UPDATE items SET laundry = 'clean', laundry_at = NULL, laundry_by = NULL, updated_at = ? WHERE id = ?",
                     (t, item_id))


def last_laundry_day(day: int, on: date) -> date:
    """The latest date on or before `on` that falls on the laundry day."""
    return on - timedelta(days=(on.weekday() - day) % 7)


def next_laundry_day(day: int, on: date) -> date:
    """The first date after `on` that falls on the laundry day."""
    return on + timedelta(days=(day - on.weekday()) % 7 or 7)


_caught_up: dict[str, tuple] = {}   # database path -> (laundry day, its last date), once the washing is done for it


def catch_up(conn, key: str = "") -> int:
    """Everything that went in the laundry before the last laundry day is clean (washed that day); a piece with no
    date of going in (the demo closet's, made that way) waits for the owner. Returns how many
    pieces came out. Cheap to call often: once caught up for a laundry date, nothing is looked at until the next one
    (what goes in after it waits for the next laundry day)."""
    policy = _policy()
    if not policy or policy.day is None:
        return 0
    washed = last_laundry_day(policy.day, today())
    mark = (policy.day, washed)
    if _caught_up.get(key) == mark:
        return 0
    # went in before the laundry day began in this computer's time, compared as the UTC text `db.now` writes
    before = datetime.combine(washed, datetime.min.time()).astimezone().astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")
    if conn.execute("SELECT 1 FROM items WHERE laundry = 'laundry' AND laundry_at < ? LIMIT 1",
                    (before,)).fetchone() is None:
        _caught_up[key] = mark
        return 0
    try:
        conn.execute("BEGIN IMMEDIATE")
        t = db.now()
        n = conn.execute("UPDATE items SET laundry = 'clean', wears_since_wash = 0, washed_at = ?, laundry_at = NULL, "
                         "laundry_by = NULL, updated_at = ? WHERE laundry = 'laundry' AND laundry_at < ?",
                         (t, t, before)).rowcount
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    _caught_up[key] = mark
    return n


def _parse(value: str) -> date:
    try:
        if not _DATE.match(value):
            raise ValueError
        return date.fromisoformat(value)
    except ValueError:
        raise items.ItemError("Give the date as YYYY-MM-DD, for example 2026-11-12.") from None


def list_wears(conn, item_id: str) -> list[dict]:
    items.get(conn, item_id)
    return [{"worn_on": r["worn_on"], "created_at": r["created_at"]}
            for r in conn.execute("SELECT worn_on, created_at FROM wears WHERE item_id = ? ORDER BY worn_on DESC", (item_id,))]


def add(conn, item_id: str, worn_on: str | None = None) -> tuple[dict, bool]:
    """Record a wear. Returns (item, created); a second wear on the same day changes nothing."""
    items.get(conn, item_id)
    day = _parse(worn_on) if worn_on else today()
    if day > today():
        raise items.ItemError("That date is in the future. Record a wear on the day, or afterwards.")
    try:
        conn.execute("BEGIN IMMEDIATE")
        t = db.now()  # taken under the write lock, so it orders correctly against a wash
        created = conn.execute("INSERT OR IGNORE INTO wears (item_id, worn_on, created_at) VALUES (?, ?, ?)",
                               (item_id, day.isoformat(), t)).rowcount == 1
        if created:
            conn.execute("UPDATE items SET wears_since_wash = wears_since_wash + 1, updated_at = ? WHERE id = ?", (t, item_id))
            _after_wear(conn, item_id, t)
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return items.detail(conn, items.get(conn, item_id)), created


def remove(conn, item_id: str, worn_on: str) -> dict:
    items.get(conn, item_id)
    day = _parse(worn_on).isoformat()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = items.get(conn, item_id)  # read again under the write lock: a wash may have just been recorded
        wear = conn.execute("SELECT created_at FROM wears WHERE item_id = ? AND worn_on = ?", (item_id, day)).fetchone()
        if wear is None:
            raise items.ItemError("There is no wear on that day to remove.", 404)
        conn.execute("DELETE FROM wears WHERE item_id = ? AND worn_on = ?", (item_id, day))
        counted = row["washed_at"] is None or wear["created_at"] > row["washed_at"]
        t = db.now()
        conn.execute("UPDATE items SET wears_since_wash = max(0, wears_since_wash - ?), updated_at = ? WHERE id = ?",
                     (1 if counted else 0, t, item_id))
        _after_unwear(conn, item_id, t, wear["created_at"])
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return items.detail(conn, items.get(conn, item_id))


MAX_AT_ONCE = 20


def _ids(item_ids: object) -> list[str]:
    """A list of item ids, each once, in the order given. Raises ItemError."""
    if not isinstance(item_ids, list) or not item_ids or not all(isinstance(x, str) and x for x in item_ids):
        raise items.ItemError("Give the items as a list of item ids.")
    unique = list(dict.fromkeys(item_ids))
    if len(unique) > MAX_AT_ONCE:
        raise items.ItemError(f"Give at most {MAX_AT_ONCE} items at once.")
    return unique


# Called inside the transaction with (day, item ids whose wear changed, time), to change more in the same go.
Also = Callable[[str, list[str], str], None]


def add_many(conn, item_ids: object, worn_on: str | None = None, also: Also | None = None) -> dict:
    """Record a wear for every item on one day, all or nothing (an outfit worn together).

    Returns {worn_on, recorded, items}: `recorded` lists the items whose wear is new (an item already
    recorded for that day is left as it is), `items` every item as `GET /api/items/{id}` gives it.
    `also` is called before the wears are committed (the worn outfit is stored in the same go).
    """
    ids = _ids(item_ids)
    for item_id in ids:
        items.get(conn, item_id)
    day = _parse(worn_on) if worn_on else today()
    if day > today():
        raise items.ItemError("That date is in the future. Record a wear on the day, or afterwards.")
    recorded = []
    try:
        conn.execute("BEGIN IMMEDIATE")
        t = db.now()
        for item_id in ids:
            if conn.execute("INSERT OR IGNORE INTO wears (item_id, worn_on, created_at) VALUES (?, ?, ?)",
                            (item_id, day.isoformat(), t)).rowcount == 1:
                conn.execute("UPDATE items SET wears_since_wash = wears_since_wash + 1, updated_at = ? WHERE id = ?", (t, item_id))
                _after_wear(conn, item_id, t)
                recorded.append(item_id)
        if also:
            also(day.isoformat(), recorded, t)
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return {"worn_on": day.isoformat(), "recorded": recorded,
            "items": [items.detail(conn, items.get(conn, i)) for i in ids]}


def remove_many(conn, item_ids: object, worn_on: object, also: Also | None = None) -> dict:
    """Remove the wear on one day from every item, all or nothing (undoing an outfit worn together).

    An item with no wear that day is left as it is. Returns {worn_on, removed, items}.
    When called inside an outfit's transaction, that caller commits or rolls back the whole change.
    """
    ids = _ids(item_ids)
    if not isinstance(worn_on, str):
        raise items.ItemError("Give the day of the wears to remove as YYYY-MM-DD.")
    day = _parse(worn_on).isoformat()
    for item_id in ids:
        items.get(conn, item_id)
    removed = []
    own_transaction = not conn.in_transaction
    try:
        if own_transaction:
            conn.execute("BEGIN IMMEDIATE")
        t = db.now()
        for item_id in ids:
            row = items.get(conn, item_id)  # read under the write lock: a wash may have just been recorded
            wear = conn.execute("SELECT created_at FROM wears WHERE item_id = ? AND worn_on = ?", (item_id, day)).fetchone()
            if wear is None:
                continue
            conn.execute("DELETE FROM wears WHERE item_id = ? AND worn_on = ?", (item_id, day))
            counted = row["washed_at"] is None or wear["created_at"] > row["washed_at"]
            conn.execute("UPDATE items SET wears_since_wash = max(0, wears_since_wash - ?), updated_at = ? WHERE id = ?",
                         (1 if counted else 0, t, item_id))
            _after_unwear(conn, item_id, t, wear["created_at"])
            removed.append(item_id)
        if also:
            also(day, removed, t)
        if own_transaction:
            conn.execute("COMMIT")
    except Exception:
        if own_transaction and conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return {"worn_on": day, "removed": removed, "items": [items.detail(conn, items.get(conn, i)) for i in ids]}


def set_laundry(conn, item_id: str, state: str) -> dict:
    """Put an item in the laundry, or mark it clean (which starts its count of wears since the wash again)."""
    items.get(conn, item_id)
    if state not in LAUNDRY:
        raise items.ItemError("The laundry state must be clean or laundry.")
    try:
        conn.execute("BEGIN IMMEDIATE")
        t = db.now()
        if state == "clean":
            conn.execute("UPDATE items SET laundry = 'clean', wears_since_wash = 0, washed_at = ?, laundry_at = NULL, "
                         "laundry_by = NULL, updated_at = ? WHERE id = ?", (t, t, item_id))
        else:
            conn.execute("UPDATE items SET laundry = 'laundry', laundry_at = ?, laundry_by = 'owner', updated_at = ? "
                         "WHERE id = ? AND laundry != 'laundry'", (t, t, item_id))
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return items.detail(conn, items.get(conn, item_id))
