"""Where a piece is: in the closet, or away at the cleaner's, at the tailor's or lent out.

Being away is where a piece is, not what state it is in: a piece that needs mending keeps its condition while it is at
the tailor's. An away piece is left out of outfits and trips like a piece in the laundry (`outfits._unavailable`), and
still counts as owned for What's missing, Would this work? and the insights. With it the owner may give the day they
expect it back and a short note of their own. The note stays on this computer: it is never put into anything sent to
Claude (`tests/test_away.py` checks every reader).

Coming back (`back`) does what the place means: back from the cleaner's, it is clean (its count of wears starts
again); back from the tailor's, it no longer needs mending; back from being lent, nothing else changes. A wear
recorded for today brings an away piece back (`wears._record`): it is evidently back. The latest return can be undone
(`undo_back`), putting back everything it changed. Every going and coming back is kept in `away_log` for the item's
history.
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta

from . import db

PLACES = ("cleaner", "tailor", "lent")
NOTE_MAX = 120
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# what coming back may change, kept with the return so it can be undone
_UNDONE = ("away", "away_since", "away_until", "away_note", "laundry", "wears_since_wash", "washed_at", "laundry_at",
           "laundry_by", "condition")


def _items():
    from . import items  # items reads this module for an item's answer
    return items


def _today() -> date:
    from . import wears  # the computer's local date, as the wear log has it (tests move that clock)
    return wears.today()


def _day(value: object, what: str) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not _DATE.match(value):
        raise _items().ItemError(f"Give the day {what} as YYYY-MM-DD, for example 2026-11-27.")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise _items().ItemError(f"Give the day {what} as YYYY-MM-DD, for example 2026-11-27.") from None


def check(place: object, until: object = None, note: object = None, since: object = None) -> dict:
    """The owner's choice as stored: {away, away_since, away_until, away_note}. Raises ItemError in their words."""
    if place not in PLACES:
        raise _items().ItemError("Say where it is: at the cleaner's, at the tailor's or lent out.")
    until_day = _day(until, "you expect it back")
    since_day = _day(since, "it went") or _today().isoformat()
    if since_day > (_today() + timedelta(days=1)).isoformat():
        raise _items().ItemError("The day it went can't be in the future.")
    if until_day and until_day < since_day:
        raise _items().ItemError("The day you expect it back can't be before the day it went.")
    if note is not None and not isinstance(note, str):
        raise _items().ItemError("The note is a few words of your own.")
    text = " ".join((note or "").split())
    if len(text) > NOTE_MAX:
        raise _items().ItemError(f"Keep the note to {NOTE_MAX} characters.")
    return {"away": place, "away_since": since_day, "away_until": until_day, "away_note": text or None}


def fields(row) -> dict | None:
    """Where an item is, as the closet's list carries it (so the phone's offline copy shows it): None in the closet,
    else {place, since, until}."""
    if row["away"] not in PLACES:
        return None
    return {"place": row["away"], "since": row["away_since"], "until": row["away_until"]}


def detail(conn, row) -> dict:
    """Where an item is, for its own page: `away` with the owner's note, and `came_back`, the latest return when it
    was today and can still be undone ({from, on, by, mended}; null otherwise)."""
    away = fields(row)
    if away is not None:
        away["note"] = row["away_note"]
    came = None
    last = _last(conn, row["id"])
    if away is None and last is not None and last["event"] == "back" and last["undo"]:
        on = _local_day(last["at"])
        if on >= _today().isoformat():
            before = json.loads(last["undo"])
            came = {"from": last["place"], "on": on, "by": last["by"],
                    "mended": before.get("condition") == "needs_repair" and row["condition"] != "needs_repair"}
    return {"away": away, "came_back": came}


def _local_day(stamp: str) -> str:
    from . import wears
    return wears._local_date(stamp).isoformat()


def _last(conn, item_id: str):
    return conn.execute("SELECT * FROM away_log WHERE item_id = ? ORDER BY id DESC LIMIT 1", (item_id,)).fetchone()


def _write(conn, call):
    own = not conn.in_transaction
    try:
        if own:
            conn.execute("BEGIN IMMEDIATE")
        out = call(db.now())
        if own:
            conn.execute("COMMIT")
        return out
    except Exception:
        if own and conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


def send(conn, item_id: str, place: object, until: object = None, note: object = None, since: object = None) -> dict:
    """Send a piece away, or change where it is, when it is expected back or the note. Returns the item."""
    items = _items()
    row = items.get(conn, item_id)
    if row["status"] == "archived":
        raise items.ItemError("This piece is archived. Bring it back into your closet first.")
    chosen = check(place, until, note, since)
    if row["away"] == chosen["away"] and since is None:
        chosen["away_since"] = row["away_since"] or chosen["away_since"]   # still away since the day it went

    def go(t: str) -> None:
        conn.execute("UPDATE items SET away = ?, away_since = ?, away_until = ?, away_note = ?, updated_at = ? WHERE id = ?",
                     (chosen["away"], chosen["away_since"], chosen["away_until"], chosen["away_note"], t, item_id))
        if row["away"] != chosen["away"]:
            conn.execute("INSERT INTO away_log (item_id, at, event, place, by) VALUES (?, ?, 'went', ?, 'owner')",
                         (item_id, t, chosen["away"]))
    _write(conn, go)
    return items.detail(conn, items.get(conn, item_id))


def bring_back(conn, row, by: str, t: str) -> None:
    """Bring an away piece back, inside the caller's transaction: what its place means (clean from the cleaner's,
    mended from the tailor's), with everything it changes kept so it can be undone."""
    place = row["away"]
    before = {f: row[f] for f in _UNDONE}
    sets = {"away": None, "away_since": None, "away_until": None, "away_note": None}
    if place == "cleaner":
        sets.update(laundry="clean", wears_since_wash=0, washed_at=t, laundry_at=None, laundry_by=None)
    elif place == "tailor" and row["condition"] == "needs_repair":
        sets["condition"] = None
    conn.execute(f"UPDATE items SET {', '.join(f'{k} = ?' for k in sets)}, updated_at = ? WHERE id = ?",
                 (*sets.values(), t, row["id"]))
    conn.execute("INSERT INTO away_log (item_id, at, event, place, by, undo) VALUES (?, ?, 'back', ?, ?, ?)",
                 (row["id"], t, place, by, json.dumps(before)))


def back(conn, item_id: str) -> dict:
    """The owner says it is back. Returns the item; a piece already in the closet is left as it is."""
    items = _items()
    items.get(conn, item_id)

    def come(t: str) -> None:
        row = items.get(conn, item_id)   # read under the write lock
        if row["away"] in PLACES:
            bring_back(conn, row, "owner", t)
    _write(conn, come)
    return items.detail(conn, items.get(conn, item_id))


def _undo(conn, last, t: str) -> None:
    before = json.loads(last["undo"])
    conn.execute(f"UPDATE items SET {', '.join(f'{k} = ?' for k in _UNDONE)}, updated_at = ? WHERE id = ?",
                 (*(before.get(k) for k in _UNDONE), t, last["item_id"]))
    conn.execute("DELETE FROM away_log WHERE id = ?", (last["id"],))


def undo_back(conn, item_id: str) -> dict:
    """Undo the latest return: the piece is away again as it was, and what coming back changed is put back."""
    items = _items()
    items.get(conn, item_id)

    def undo(t: str) -> None:
        last = _last(conn, item_id)
        row = items.get(conn, item_id)
        if last is None or last["event"] != "back" or not last["undo"] or row["away"] in PLACES:
            raise items.ItemError("There is no return to undo.", 409)
        _undo(conn, last, t)
        # the wears since the return stay counted, as "All clean"'s undo adds them (back from the cleaner's, the count
        # had started again; from anywhere else coming back left it as it was)
        before = json.loads(last["undo"]).get("wears_since_wash") or 0
        since = row["wears_since_wash"] - (0 if last["place"] == "cleaner" else before)
        if since > 0:
            conn.execute("UPDATE items SET wears_since_wash = wears_since_wash + ? WHERE id = ?", (since, item_id))
    _write(conn, undo)
    return items.detail(conn, items.get(conn, item_id))


def unwear(conn, item_id: str, worn_at: str, t: str) -> None:
    """A wear removed again sends the piece back where it was when that very wear brought it back, on the day of the
    return, as long as its Undo lasts (`detail`); a wear removed on a later day leaves the piece where it is (inside the
    caller's transaction)."""
    last = _last(conn, item_id)
    if (last is not None and last["event"] == "back" and last["by"] == "wear" and last["at"] == worn_at and last["undo"]
            and _local_day(last["at"]) >= _today().isoformat()):
        _undo(conn, last, t)


def history(conn, item_id: str) -> list[dict]:
    """When the piece went and came back, oldest first, as {id, at, event, place, by}."""
    return [{"id": r["id"], "at": r["at"], "event": r["event"], "place": r["place"], "by": r["by"]}
            for r in conn.execute("SELECT * FROM away_log WHERE item_id = ? ORDER BY id", (item_id,))]
