"""What was worn when, and whether an item is clean or in the laundry.

A wear is one item on one day (the computer's local date; a phone a time zone
ahead may give the next day). Each item also keeps how many wears were recorded
since it was last washed; a wear for a day the piece has been washed since (an
outfit filled in from memory, say) is kept in the log but not counted, and a
wear removed again only lowers that count if it was counted.

Laundry that keeps itself (when the owner leaves it on in Settings): a piece goes
in the laundry by itself once worn as often as "Before it needs washing" allows
for its kind, and everything in the laundry is clean again on the owner's laundry
day. A wear removed again takes a piece back out if that wear put it in.

A wear for today of a piece that is away (at the cleaner's, the tailor's, lent out: `away.py`) brings it back, and
removing that wear sends it away again.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from . import away, db, items

LAUNDRY = ("clean", "laundry")
AHEAD_DAYS = 1   # a wear may be for the computer's tomorrow: a phone a time zone ahead is already there
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


def policy() -> Policy | None:
    """The owner's laundry that keeps itself as it stands now, or None when it is off."""
    return _policy()


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


def _local_date(stamp: str) -> date:
    """The computer's local date of a time as `db.now` writes it (UTC)."""
    return datetime.strptime(stamp[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC).astimezone().date()


def washed_since(conn, row, day: date) -> bool:
    """Whether the piece has been washed since `day`, so a wear on that day is behind its last wash and does not count.

    Washed by hand: marked clean on a later date (a wear on the day it was marked clean still counts). Washed by the
    laundry day: the piece goes in by itself, the first laundry day after `day` has come (a wash on the day itself is
    at its first minute, before the wear), and its wears in the week before that laundry day, this one included,
    reached its count, so it was in the basket. Wears carried over from earlier weeks are not followed."""
    washed = None
    if row["washed_at"]:
        washed = min(_local_date(row["washed_at"]), today())   # a wash is never later than today
        if day < washed:
            return True
    cap = _cap(row)
    policy = _policy()
    if not cap or policy is None or policy.day is None:
        return False
    wash = next_laundry_day(policy.day, day)
    if wash > today():
        return False
    start = max(wash - timedelta(days=7), washed) if washed else wash - timedelta(days=7)
    others = conn.execute("SELECT COUNT(*) FROM wears WHERE item_id = ? AND worn_on >= ? AND worn_on < ? AND worn_on != ?",
                          (row["id"], start.isoformat(), wash.isoformat(), day.isoformat())).fetchone()[0]
    return others + 1 >= cap


def _check_day(worn_on: str | None) -> date:
    """The day a wear is for: today when none is given. A phone a time zone ahead of the computer may give the
    computer's tomorrow (its own today); a day after that is refused."""
    day = _parse(worn_on) if worn_on else today()
    if day > today() + timedelta(days=AHEAD_DAYS):
        raise items.ItemError("That date is in the future. Record a wear on the day, or afterwards.")
    return day


def _record(conn, item_id: str, day: date, t: str) -> bool:
    """Record one wear inside the caller's transaction; True when it is new. A wear for a day the piece has been
    washed since is kept in the log but neither counted nor puts the piece in the laundry."""
    row = items.get(conn, item_id)
    if conn.execute("SELECT 1 FROM wears WHERE item_id = ? AND worn_on = ?", (item_id, day.isoformat())).fetchone():
        return False
    if row["away"] in away.PLACES and day >= today():
        away.bring_back(conn, row, "wear", t)   # worn today, so it is evidently back (undone with the wear)
        row = items.get(conn, item_id)
    counted = not washed_since(conn, row, day)
    if conn.execute("INSERT OR IGNORE INTO wears (item_id, worn_on, created_at) VALUES (?, ?, ?)",
                    (item_id, day.isoformat(), t)).rowcount != 1:
        return False
    if counted:
        conn.execute("UPDATE items SET wears_since_wash = wears_since_wash + 1, updated_at = ? WHERE id = ?", (t, item_id))
        _after_wear(conn, item_id, t)
    else:
        conn.execute("UPDATE items SET updated_at = ? WHERE id = ?", (t, item_id))
    return True


def _unrecord(conn, item_id: str, day: str, t: str) -> bool:
    """Remove one wear inside the caller's transaction; False when there is none that day. The count goes down only
    when the wear was counted: recorded after the last wash, for a day the piece has not been washed since."""
    row = items.get(conn, item_id)  # read under the write lock: a wash may have just been recorded
    wear = conn.execute("SELECT created_at FROM wears WHERE item_id = ? AND worn_on = ?", (item_id, day)).fetchone()
    if wear is None:
        return False
    counted = ((row["washed_at"] is None or wear["created_at"] > row["washed_at"])
               and not washed_since(conn, row, date.fromisoformat(day)))
    conn.execute("DELETE FROM wears WHERE item_id = ? AND worn_on = ?", (item_id, day))
    conn.execute("UPDATE items SET wears_since_wash = max(0, wears_since_wash - ?), updated_at = ? WHERE id = ?",
                 (1 if counted else 0, t, item_id))
    _after_unwear(conn, item_id, t, wear["created_at"])
    away.unwear(conn, item_id, wear["created_at"], t)   # away again, when this wear is what brought it back
    return True


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
    date of going in (the demo closet's, made that way) waits for the owner, and so does one in the bag of a trip under
    way on the laundry day (it is in the suitcase): it waits for the first laundry day after the trip. Returns how many
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
    from . import savedtrips  # it reads this module for the day
    packed = sorted(savedtrips.in_bag_on(conn, washed))
    unless = f" AND id NOT IN ({', '.join('?' * len(packed))})" if packed else ""
    try:
        conn.execute("BEGIN IMMEDIATE")
        t = db.now()
        n = conn.execute("UPDATE items SET laundry = 'clean', wears_since_wash = 0, washed_at = ?, laundry_at = NULL, "
                         f"laundry_by = NULL, updated_at = ? WHERE laundry = 'laundry' AND laundry_at < ?{unless}",
                         (t, t, before, *packed)).rowcount
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
    day = _check_day(worn_on)
    try:
        conn.execute("BEGIN IMMEDIATE")
        t = db.now()  # taken under the write lock, so it orders correctly against a wash
        created = _record(conn, item_id, day, t)
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
        if not _unrecord(conn, item_id, day, db.now()):
            raise items.ItemError("There is no wear on that day to remove.", 404)
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
    day = _check_day(worn_on)
    recorded = []
    try:
        conn.execute("BEGIN IMMEDIATE")
        t = db.now()
        for item_id in ids:
            if _record(conn, item_id, day, t):
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
            if _unrecord(conn, item_id, day, t):
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


# what marking a piece clean changes, kept in the answer so the closet's "All clean" can put each piece back as it was
_WASHED = ("wears_since_wash", "washed_at", "laundry_at", "laundry_by")
_STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[.\dZ+:-]{0,16}")


def _restore_of(undo) -> tuple[str, dict]:
    """The wash an undo answers (its time) and what it changed, checked: an undo is what `set_laundry` answered."""
    bad = items.ItemError("That cannot be undone: the undo is not one Nines gave.")
    if not isinstance(undo, dict) or not isinstance(undo.get("washed_at"), str) or not _STAMP.fullmatch(undo["washed_at"]):
        raise bad
    before = undo.get("before")
    if not isinstance(before, dict) or set(before) != set(_WASHED):
        raise bad
    count = before["wears_since_wash"]
    if not isinstance(count, int) or isinstance(count, bool) or not 0 <= count <= 100_000:
        raise bad
    for f in ("washed_at", "laundry_at"):
        if before[f] is not None and not (isinstance(before[f], str) and _STAMP.fullmatch(before[f])):
            raise bad
    if before["laundry_by"] not in (None, "auto", "owner"):
        raise bad
    return undo["washed_at"], before


def set_laundry(conn, item_id: str, state: str, undo=None) -> dict:
    """Put an item in the laundry, or mark it clean (which starts its count of wears since the wash again).

    Marking a piece in the laundry clean answers with `undo`: the time of that wash and what it changed. Sent back with
    `state` "laundry", it puts the piece back in the laundry as it was (when it went in, and who put it there, which
    the laundry day and undoing a wear read), with the wears since the wash added to its count. A piece washed again
    since cannot be put back that way (409); one already back in the laundry is left as it is."""
    items.get(conn, item_id)
    if state not in LAUNDRY:
        raise items.ItemError("The laundry state must be clean or laundry.")
    if undo is not None and state != "laundry":
        raise items.ItemError("Only a piece marked clean can be put back in the laundry.")
    restore = _restore_of(undo) if undo is not None else None
    given = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        t = db.now()
        row = items.get(conn, item_id)   # read under the write lock
        if state == "clean":
            if row["laundry"] == "laundry":
                given = {"washed_at": t, "before": {f: row[f] for f in _WASHED}}
            conn.execute("UPDATE items SET laundry = 'clean', wears_since_wash = 0, washed_at = ?, laundry_at = NULL, "
                         "laundry_by = NULL, updated_at = ? WHERE id = ?", (t, t, item_id))
        elif restore is not None:
            washed, before = restore
            if row["laundry"] != "laundry":
                if row["washed_at"] != washed:
                    raise items.ItemError("It has been marked clean again since, so it cannot be put back that way.", 409)
                conn.execute("UPDATE items SET laundry = 'laundry', wears_since_wash = ?, washed_at = ?, laundry_at = ?, "
                             "laundry_by = ?, updated_at = ? WHERE id = ?",
                             (before["wears_since_wash"] + row["wears_since_wash"], before["washed_at"], before["laundry_at"],
                              before["laundry_by"], t, item_id))
        else:
            conn.execute("UPDATE items SET laundry = 'laundry', laundry_at = ?, laundry_by = 'owner', updated_at = ? "
                         "WHERE id = ? AND laundry != 'laundry'", (t, t, item_id))
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    out = items.detail(conn, items.get(conn, item_id))
    if given is not None:
        out["undo"] = given
    return out
