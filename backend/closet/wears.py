"""What was worn when, and whether an item is clean or in the laundry.

A wear is one item on one day (the computer's local date). Each item also keeps
how many wears were recorded since it was last marked clean; a wear removed
again only lowers that count if it was recorded after the wash.
"""
from __future__ import annotations

import re
from datetime import date

from . import db, items

LAUNDRY = ("clean", "laundry")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def today() -> date:
    """Today in the computer's local time (a function so tests can move the clock)."""
    return date.today()


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
        conn.execute("UPDATE items SET wears_since_wash = max(0, wears_since_wash - ?), updated_at = ? WHERE id = ?",
                     (1 if counted else 0, db.now(), item_id))
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


def add_many(conn, item_ids: object, worn_on: str | None = None) -> dict:
    """Record a wear for every item on one day, all or nothing (an outfit worn together).

    Returns {worn_on, recorded, items}: `recorded` lists the items whose wear is new (an item already
    recorded for that day is left as it is), `items` every item as `GET /api/items/{id}` gives it.
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
                recorded.append(item_id)
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return {"worn_on": day.isoformat(), "recorded": recorded,
            "items": [items.detail(conn, items.get(conn, i)) for i in ids]}


def remove_many(conn, item_ids: object, worn_on: object) -> dict:
    """Remove the wear on one day from every item, all or nothing (undoing an outfit worn together).

    An item with no wear that day is left as it is. Returns {worn_on, removed, items}.
    """
    ids = _ids(item_ids)
    if not isinstance(worn_on, str):
        raise items.ItemError("Give the day of the wears to remove as YYYY-MM-DD.")
    day = _parse(worn_on).isoformat()
    for item_id in ids:
        items.get(conn, item_id)
    removed = []
    try:
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
            removed.append(item_id)
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
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
            conn.execute("UPDATE items SET laundry = 'clean', wears_since_wash = 0, washed_at = ?, updated_at = ? WHERE id = ?",
                         (t, t, item_id))
        else:
            conn.execute("UPDATE items SET laundry = 'laundry', updated_at = ? WHERE id = ? AND laundry != 'laundry'", (t, item_id))
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return items.detail(conn, items.get(conn, item_id))
