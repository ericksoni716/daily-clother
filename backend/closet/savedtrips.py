"""Saved trips: the weather, the packing plan and what has been packed, kept in the closet's database.

`work_out` checks what the owner asked for (place, first and last day,
occasion, the days that differ, "I can wash there", pieces swapped out and
pinned in), looks up the weather (closet/tripweather.py) and makes the plan
(closet/trips.py). `create` does the same and saves it. A saved trip keeps the
weather its plan was made for, so opening it never changes the plan:
`check_weather` looks the weather up again and only says whether it changed;
the plan is made again when the owner asks (`patch` with "replan").

Every function raises TripError with a sentence the owner can read when the
request is wrong, and TripNotFound when the trip is not in this closet.
"""
from __future__ import annotations

import json
import uuid
from datetime import date

from . import db, trips, tripweather, wears, weather
from .state import State
from .today import closet_rows

FIELDS = ("place", "first_day", "last_day", "occasion", "day_occasions", "can_wash", "leave_out", "pin", "weather")
PATCH_FIELDS = ("ticks", "occasion", "day_occasions", "can_wash", "leave_out", "pin", "replan")


class TripError(ValueError):
    """A request about a trip that cannot be done, in words the owner can read."""


class TripNotFound(LookupError):
    pass


def _today() -> date:
    return wears.today()


def _object(body: object) -> dict:
    if not isinstance(body, dict):
        raise TripError("Send the trip as an object, for example {\"place\": {...}, \"first_day\": \"2026-12-04\", ...}.")
    return body


def _unknown(body: dict, allowed: tuple[str, ...]) -> None:
    unknown = sorted(set(body) - set(allowed))
    if unknown:
        raise TripError(f"These are not part of a trip: {', '.join(unknown)}.")


def _options(data: dict, dates: list[str]) -> trips.Options:
    try:
        return trips.parse_options(data, dates)
    except trips.PlanError as e:
        raise TripError(str(e)) from None


def _plan(conn, days: list[dict], opts: trips.Options) -> dict:
    return trips.plan(closet_rows(conn), days, opts)


def _all_given(days: list[dict]) -> bool:
    return bool(days) and all(d.get("source") == "given" for d in days)


def work_out(conn, state: State, body: object) -> dict:
    """A plan for the trip asked for, not saved: the trip as it would be saved, without id or ticks."""
    body = _object(body)
    _unknown(body, FIELDS)
    try:
        place = weather.check_place(body.get("place"))
    except ValueError as e:
        raise TripError(f"Choose where the trip is. {e}") from None
    try:
        first, last = tripweather.check_dates(body.get("first_day"), body.get("last_day"), _today())
    except ValueError as e:
        raise TripError(str(e)) from None
    dates = tripweather.dates_of(first, last)
    opts = _options(body, dates)
    if body.get("weather") is not None:
        try:
            days, message = tripweather.given(first, last, body["weather"]), None
        except ValueError as e:
            raise TripError(str(e)) from None
    else:
        found = tripweather.lookup(state, place, first, last, _today())
        days, message = found["days"], found["message"]
    plan = _plan(conn, days, opts)
    return {"place": place, "first_day": first.isoformat(), "last_day": last.isoformat(), **_choices(opts),
            "weather": days, "weather_message": message, "plan": plan, "lines": trips.lines(plan)}


def _choices(opts: trips.Options) -> dict:
    return {"occasion": opts.occasion, "day_occasions": dict(opts.day_occasions), "can_wash": opts.can_wash,
            "leave_out": list(opts.leave_out), "pin": list(opts.pin)}


def _row(r) -> dict:
    plan = json.loads(r["plan"])
    lines = trips.lines(plan)
    return {"id": r["id"], "place": json.loads(r["place"]), "first_day": r["first_day"], "last_day": r["last_day"],
            "occasion": r["occasion"], "day_occasions": json.loads(r["day_occasions"]), "can_wash": bool(r["can_wash"]),
            "leave_out": json.loads(r["leave_out"]), "pin": json.loads(r["pinned"]), "weather": json.loads(r["weather"]),
            "weather_message": r["weather_message"], "plan": plan, "lines": lines,
            "packed": [x for x in json.loads(r["packed"]) if x in lines], "planned_at": r["planned_at"],
            "created_at": r["created_at"], "updated_at": r["updated_at"]}


def _load(conn, trip_id: str):
    r = conn.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
    if r is None:
        raise TripNotFound(trip_id)
    return r


def create(conn, state: State, body: object) -> dict:
    """Plan the trip and save it."""
    trip = work_out(conn, state, body)
    trip_id, now = uuid.uuid4().hex, db.now()
    conn.execute(
        "INSERT INTO trips (id, place, first_day, last_day, occasion, day_occasions, can_wash, leave_out, pinned, weather,"
        " weather_message, plan, packed, planned_at, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (trip_id, json.dumps(trip["place"]), trip["first_day"], trip["last_day"], trip["occasion"],
         json.dumps(trip["day_occasions"]), int(trip["can_wash"]), json.dumps(trip["leave_out"]), json.dumps(trip["pin"]),
         json.dumps(trip["weather"]), trip["weather_message"], json.dumps(trip["plan"]), "[]", now, now, now))
    return get(conn, trip_id)


def get(conn, trip_id: str) -> dict:
    return _row(_load(conn, trip_id))


def list_all(conn) -> list[dict]:
    """Every trip, upcoming and current first (soonest first), then past ones (latest first)."""
    today = _today().isoformat()
    out = []
    for r in conn.execute("SELECT * FROM trips"):
        t = _row(r)
        out.append({k: t[k] for k in ("id", "place", "first_day", "last_day", "occasion", "can_wash")}
                   | {"lines": len(t["lines"]), "packed": len(t["packed"]), "uncovered": len(t["plan"].get("uncovered", [])),
                      "past": t["last_day"] < today})
    upcoming = sorted((t for t in out if not t["past"]), key=lambda t: (t["first_day"], t["last_day"], t["id"]))
    past = sorted((t for t in out if t["past"]), key=lambda t: (t["first_day"], t["last_day"], t["id"]), reverse=True)
    return upcoming + past


def delete(conn, trip_id: str) -> None:
    _load(conn, trip_id)
    conn.execute("DELETE FROM trips WHERE id = ?", (trip_id,))


def _first_last(trip: dict) -> tuple[date, date]:
    return date.fromisoformat(trip["first_day"]), date.fromisoformat(trip["last_day"])


def check_weather(conn, state: State, trip_id: str) -> dict:
    """The weather for a saved trip looked up again, when its days have come into the forecast.

    Returns {"checked": bool, "changed": bool, "days": [day] or None, "message": sentence or None}. The trip and its
    plan are not changed.
    """
    trip = get(conn, trip_id)
    if _all_given(trip["weather"]) or not tripweather.in_forecast(trip["weather"], _today()):
        return {"checked": False, "changed": False, "days": None, "message": None}
    first, last = _first_last(trip)
    found = tripweather.lookup(state, trip["place"], first, last, _today())
    return {"checked": True, "changed": tripweather.changed(trip["weather"], found["days"]), "days": found["days"],
            "message": found["message"]}


def patch(conn, state: State, trip_id: str, body: object) -> dict:
    """Tick lines, change the choices (which plans again from the saved weather), or plan again with fresh weather."""
    body = _object(body)
    _unknown(body, PATCH_FIELDS)
    replan = body.get("replan", False)
    if not isinstance(replan, bool):
        raise TripError("\"Plan again\" must be true or false.")
    ticks = body.get("ticks", {})
    if not isinstance(ticks, dict) or not all(isinstance(v, bool) for v in ticks.values()):
        raise TripError("Ticks must be an object of line to true or false, for example {\"basic:socks\": true}.")
    fresh = None
    trip = get(conn, trip_id)
    if replan and not _all_given(trip["weather"]):
        # asked before the trip is locked for writing: the weather service can take a few seconds
        first, last = _first_last(trip)
        fresh = tripweather.lookup(state, trip["place"], first, last, _today())
    changes = {k: body[k] for k in ("occasion", "day_occasions", "can_wash", "leave_out", "pin") if k in body}
    conn.execute("BEGIN IMMEDIATE")  # two ticks sent at once must both be kept
    try:
        trip = get(conn, trip_id)
        packed = list(trip["packed"])
        lines = trip["lines"]
        sets: dict[str, object] = {}
        if changes or replan:
            dates = [d["date"] for d in trip["weather"]]
            opts = _options({**_choices_of(trip), **changes}, dates)
            days, message = (fresh["days"], fresh["message"]) if fresh else (trip["weather"], trip["weather_message"])
            plan = _plan(conn, days, opts)
            lines = trips.lines(plan)
            packed = [x for x in packed if x in lines]
            sets.update(occasion=opts.occasion, day_occasions=json.dumps(dict(opts.day_occasions)),
                        can_wash=int(opts.can_wash), leave_out=json.dumps(list(opts.leave_out)),
                        pinned=json.dumps(list(opts.pin)), weather=json.dumps(days), weather_message=message,
                        plan=json.dumps(plan), planned_at=db.now())
        for line, on in ticks.items():
            if line not in lines:
                raise TripError("That line is not in this trip's plan any more. Reload the trip.")
            if on and line not in packed:
                packed.append(line)
            elif not on and line in packed:
                packed.remove(line)
        sets.update(packed=json.dumps(packed), updated_at=db.now())
        conn.execute(f"UPDATE trips SET {', '.join(f'{k} = ?' for k in sets)} WHERE id = ?", (*sets.values(), trip_id))
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return get(conn, trip_id)


def _choices_of(trip: dict) -> dict:
    return {k: trip[k] for k in ("occasion", "day_occasions", "can_wash", "leave_out", "pin")}
