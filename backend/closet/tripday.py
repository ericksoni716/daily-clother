"""A trip covers today: Today dresses for where you are on a saved trip, from what you packed, without a note.

On a day inside a saved trip, Today (`closet/today.py`) dresses for the trip's place: today's weather is looked up
there again, as a trip under way looks up its days still to come (the hours you are out read as for a day note's
place), and when it cannot be, the weather the trip has for today stands. The outfit the trip's plan has for today
comes first; the other outfits come only from what is in the bag, by the rules the trip's days still to come are
dressed by (`trips.free_on`): worn whatever the laundry at home says, each no more often than its kind allows, the
days already worn counting (`savedtrips.kept_days`). The rest of the closet is at home. The rules choose on such a
day, as for a day ahead: Claude is not asked, so nothing more is sent to Claude than before.

Your own words win (DECISIONS, "A trip covers today"): a day note that puts you somewhere else, and an outfit you
planned for today, are dressed as they are on any day; building around a piece and wearing an outfit again stay on
the trip. "Not on this trip today" sets the trip aside for the rest of the day: it is kept in the program's
settings (`trip_aside`: the day and the trip), as the day's note is, so the phone and the computer agree, and it
lapses by itself the next day. When two saved trips hold today, the one that started later is the one you are on
(`plans.trip_on`).
"""
from __future__ import annotations

from datetime import date

from . import plans, savedtrips, trips, wears
from .state import State

ASIDE = "trip_aside"   # the program's settings: {"day": YYYY-MM-DD, "trip": its id}, "Not on this trip today"


_state: State | None = None   # the program's settings, for `with_you` (the app gives them: `use_state`)


def use_state(state: State) -> None:
    global _state
    _state = state


def with_you(conn, item_id: str, today: date | None = None) -> bool:
    """Whether a piece is in the bag of the trip Today dresses from today (not set aside): it is with you, clean,
    whatever the laundry at home says. The item page says Today can build an outfit around it by this
    (`items.detail`), as Today does."""
    today = today or wears.today()
    found = plans.trip_on(conn, today)
    if found is None or (_state is not None and aside(_state, found["id"], today)):
        return False
    return item_id in savedtrips.in_bag(savedtrips.get(conn, found["id"]), under_way=True)


def aside(state: State, trip_id: str, day: date) -> bool:
    """Whether the owner set this trip aside for this day ("Not on this trip today")."""
    kept = state.get(ASIDE)
    return isinstance(kept, dict) and kept.get("day") == day.isoformat() and kept.get("trip") == trip_id


def set_aside(conn, state: State, trip_id: str, on: bool, today: date | None = None) -> dict:
    """"Not on this trip today" (`on`), or its Undo: {aside, day}. Only a trip that holds today, and the one Today
    dresses from, can be set aside. Raises TripNotFound, or TripError with a sentence."""
    today = today or wears.today()
    savedtrips.get(conn, trip_id)   # TripNotFound when it is not in this closet
    if on:
        holds = plans.trip_on(conn, today)
        if not holds or holds["id"] != trip_id:
            raise savedtrips.TripError("That trip is not the one you are on today, so there is nothing to set aside.")
        state.update(**{ASIDE: {"day": today.isoformat(), "trip": trip_id}})
    elif aside(state, trip_id, today):
        state.update(**{ASIDE: None})
    return {"aside": aside(state, trip_id, today), "day": today.isoformat()}


def today_on(conn, state: State, today: date, rows: list[dict]) -> dict | None:
    """The saved trip that holds today, as Today dresses from it, or None when no trip does.

    {trip: {id, place, first_day, last_day, day, days, aside}, place: the trip's place (as saved, for the weather),
    weather: the day as the trip has it (None when it has none), outfit: the plan's pieces for today (None when the plan
    has no outfit for it), occasion: today's occasion on the trip, bag: what is in the bag, free: the pieces of the bag
    that can be worn today}. `day` is 1 on the trip's first day, `days` how many it has."""
    found = plans.trip_on(conn, today)
    if found is None:
        return None
    trip = savedtrips.get(conn, found["id"])
    iso = today.isoformat()
    first, last = date.fromisoformat(trip["first_day"]), date.fromisoformat(trip["last_day"])
    planned = next((d for d in trip["plan"].get("days", []) if isinstance(d, dict) and d.get("date") == iso), None)
    outfit = planned.get("outfit") if planned and isinstance(planned.get("outfit"), dict) else None
    weather = next((d for d in trip["weather"] if isinstance(d, dict) and d.get("date") == iso), None)
    bag = savedtrips.in_bag(trip, under_way=True)
    kept = {k: v for k, v in savedtrips.kept_days(conn, trip, today).items() if k != iso}
    try:
        free = trips.free_on(rows, trip["weather"], {k: trip[k] for k in savedtrips.CHOICES}, savedtrips.rewear(state),
                             iso, kept, bag)
    except trips.PlanError:   # choices saved by an older Nines that no longer read: what is in the bag, as it is
        free = frozenset(bag)
    place = trip["place"] if isinstance(trip["place"], dict) else None
    return {
        "trip": {"id": trip["id"], "place": place.get("name") if place else None, "first_day": trip["first_day"],
                 "last_day": trip["last_day"], "day": (today - first).days + 1, "days": (last - first).days + 1,
                 "aside": aside(state, trip["id"], today)},
        "place": place,
        "weather": weather if weather and weather.get("source") in ("forecast", "usual", "given") else None,
        "outfit": outfit.get("pieces") if outfit and isinstance(outfit.get("pieces"), dict) else None,
        "occasion": (planned or {}).get("occasion") or trip["occasion"],
        "bag": frozenset(bag),
        "free": free,
    }
