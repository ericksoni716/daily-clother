"""Trip validation and per-closet storage; weather never silently replaces a plan."""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from . import outfits, trip_weather, trips, weather
from .items import ItemError
from .today import closet_rows

FIELDS = {"place", "first_day", "last_day", "occasion", "overrides", "can_wash", "leave_out", "pins"}
MAX_IDS = 300


def choices(body: object, *, new: bool = True) -> dict:
    if not isinstance(body, dict) or set(body) - FIELDS:
        raise ValueError("Send the place, trip dates, occasion and packing choices.")
    place = weather.check_place(body.get("place"))
    days = trip_weather.dates(body.get("first_day"), body.get("last_day"))
    if new and days[0] < trip_weather.today(place):
        raise ValueError("Choose today or a later day for a new trip.")
    occasion = body.get("occasion", "casual")
    if not isinstance(occasion, str) or occasion not in outfits.FORMALITY:
        raise ValueError("Choose an occasion: Sport, Casual, Smart casual, Business or Formal.")
    wash = body.get("can_wash", False)
    if not isinstance(wash, bool):
        raise ValueError("Say whether you can wash clothes there.")
    overrides = body.get("overrides", [])
    if not isinstance(overrides, list) or len(overrides) > len(days):
        raise ValueError("Give at most one different occasion for each day of the trip.")
    seen = set()
    for d in overrides:
        if (not isinstance(d, dict) or set(d) != {"date", "occasion"} or not isinstance(d["date"], str)
                or d["date"] not in [x.isoformat() for x in days] or d["date"] in seen
                or not isinstance(d["occasion"], str) or d["occasion"] not in outfits.FORMALITY):
            raise ValueError("Each different occasion needs its own day within the trip and a known occasion.")
        seen.add(d["date"])
    out = {**body, "place": place, "occasion": occasion, "can_wash": wash, "overrides": overrides}
    for name in ("leave_out", "pins"):
        ids = body.get(name, [])
        if (not isinstance(ids, list) or len(ids) > MAX_IDS
                or any(not isinstance(k, str) or not k or len(k) > 100 for k in ids)):
            raise ValueError("Choose pieces from the closet to take or leave out.")
        out[name] = sorted(set(ids))
    if set(out["pins"]) & set(out["leave_out"]):
        raise ValueError("A piece cannot be both pinned to take and left out.")
    return out


def make_plan(conn, state, spec):
    rows = closet_rows(conn)
    known = {r["id"] for r in rows}
    if (set(spec["pins"]) | set(spec["leave_out"])) - known:
        raise ValueError("A chosen piece is not in this closet.")
    days = trip_weather.lookup(state, spec["place"], spec["first_day"], spec["last_day"])
    return trips.plan(rows, days, **{k: spec[k] for k in ("occasion", "overrides", "can_wash", "leave_out", "pins")})


def preview(conn, state, body):
    spec = choices(body)
    return {"choices": spec, "plan": make_plan(conn, state, spec)}


def _read(row):
    return {"id": row["id"], "choices": json.loads(row["choices"]), "plan": json.loads(row["plan"]),
            "checked": json.loads(row["checked"]), "revision": row["revision"], "created_at": row["created_at"]}


def get(conn, trip_id):
    row = conn.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
    if row is None:
        raise ItemError("That trip is not in this closet.", 404)
    return _read(row)


def list_trips(conn):
    result = [_read(r) for r in conn.execute("SELECT * FROM trips")]
    now = datetime.now(UTC).date().isoformat()
    return sorted(result, key=lambda t: (t["choices"]["last_day"] < now,
                                        t["choices"]["first_day"], t["id"]))


def line_ids(plan):
    return {f"item:{p['id']}" for group in plan["packing"].values() for p in group} | {
        f"basic:{b['id']}" for b in plan["basics"]}


def create(conn, state, body):
    result = preview(conn, state, body)
    trip_id = str(uuid.uuid4())
    with conn:
        conn.execute("INSERT INTO trips (id, choices, plan, created_at) VALUES (?, ?, ?, ?)",
                     (trip_id, json.dumps(result["choices"]), json.dumps(result["plan"]), datetime.now(UTC).isoformat()))
    return get(conn, trip_id)


def open_trip(conn, state, trip_id):
    trip = get(conn, trip_id)
    spec = trip["choices"]
    now = trip_weather.today(spec["place"]).isoformat()
    if spec["last_day"] < now:
        return {**trip, "weather_changed": False, "latest_weather": []}
    latest = trip_weather.lookup(state, spec["place"], spec["first_day"], spec["last_day"])
    previous = {d["date"]: d["weather"] for d in trip["plan"]["days"]}
    changed = any(d["date"] >= now and d["low_c"] is not None
                  and any(d[k] != previous[d["date"]].get(k) for k in ("source", "low_c", "high_c", "rain")) for d in latest)
    return {**trip, "weather_changed": changed, "latest_weather": latest}


def patch(conn, state, trip_id, body):
    old = get(conn, trip_id)
    if not isinstance(body, dict) or set(body) - FIELDS - {"checked", "replan", "revision"}:
        raise ValueError("Change packing ticks, trip choices, or ask to plan again.")
    if "replan" in body and not isinstance(body["replan"], bool):
        raise ValueError("Say whether to plan again.")
    revision = body.get("revision", old["revision"])
    if isinstance(revision, bool) or not isinstance(revision, int) or revision != old["revision"]:
        raise ItemError("This trip changed on another screen. Open it again before changing it.", 409)
    updates = {k: v for k, v in body.items() if k in FIELDS}
    spec = choices({**old["choices"], **updates}, new=False)
    plan = make_plan(conn, state, spec) if updates or body.get("replan") else old["plan"]
    allowed = line_ids(plan)
    checked = {k: v for k, v in old["checked"].items() if k in allowed}
    ticks = body.get("checked", {})
    if not isinstance(ticks, dict) or any(k not in allowed or not isinstance(v, bool) for k, v in ticks.items()):
        raise ValueError("Tick a line from this trip's packing list.")
    checked.update(ticks)
    with conn:
        result = conn.execute(
            "UPDATE trips SET choices = ?, plan = ?, checked = ?, revision = revision + 1 WHERE id = ? AND revision = ?",
            (json.dumps(spec), json.dumps(plan), json.dumps(checked), trip_id, revision))
        if not result.rowcount:
            raise ItemError("This trip changed on another screen. Open it again before changing it.", 409)
    return get(conn, trip_id)


def delete(conn, trip_id):
    get(conn, trip_id)
    with conn:
        conn.execute("DELETE FROM trips WHERE id = ?", (trip_id,))
