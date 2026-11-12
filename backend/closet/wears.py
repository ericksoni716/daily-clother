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
    t = db.now()
    try:
        conn.execute("BEGIN IMMEDIATE")
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
    row = items.get(conn, item_id)
    day = _parse(worn_on).isoformat()
    try:
        conn.execute("BEGIN IMMEDIATE")
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


def set_laundry(conn, item_id: str, state: str) -> dict:
    """Put an item in the laundry, or mark it clean (which starts its count of wears since the wash again)."""
    row = items.get(conn, item_id)
    if state not in LAUNDRY:
        raise items.ItemError("The laundry state must be clean or laundry.")
    t = db.now()
    if state == "clean":
        conn.execute("UPDATE items SET laundry = 'clean', wears_since_wash = 0, washed_at = ?, updated_at = ? WHERE id = ?",
                     (t, t, item_id))
    elif row["laundry"] != "laundry":
        conn.execute("UPDATE items SET laundry = 'laundry', updated_at = ? WHERE id = ?", (t, item_id))
    return items.detail(conn, items.get(conn, item_id))
