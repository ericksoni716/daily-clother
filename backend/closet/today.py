"""Today's outfits by themselves: the weather, the wear log and the laundry fed to the engine.

`suggest(conn, state, body)` takes what the owner chose (occasion, mood, an
item to build around, items to leave out, how many outfits) and fills in the
rest: the day's temperatures and rain from the forecast for the saved place
(unless given), and how many days ago each item was last worn from the wear
log. Items in the laundry are left out by the engine itself.
"""
from __future__ import annotations

import json
from datetime import date

from . import outfits, wears, weather
from .state import State

CHOICES = ("occasion", "mood", "build_around", "leave_out", "count")
WEATHER_FIELDS = ("low_c", "high_c", "rain")


def closet_rows(conn) -> list[dict]:
    """Every item in the open closet as the engine reads it."""
    return [{**{k: r[k] for k in r.keys() if k not in ("illustration_svg", "confidence", "source")},
             "silhouette": json.loads(r["silhouette"] or "{}")} for r in conn.execute("SELECT * FROM items")]


def worn_days_ago(conn) -> dict[str, int]:
    """Days since each item was last worn, from the wear log (0 is today, the computer's local date)."""
    today = wears.today()
    out = {}
    for item_id, last in conn.execute("SELECT item_id, MAX(worn_on) FROM wears GROUP BY item_id"):
        try:
            out[item_id] = max(0, (today - date.fromisoformat(last)).days)
        except (TypeError, ValueError):
            continue
    return out


def suggest(conn, state: State, body: object) -> dict:
    """Outfits for today plus the context used. Raises outfits.ContextError with a sentence for a bad request."""
    if not isinstance(body, dict):
        raise outfits.ContextError("Send today's choices as an object, for example {\"occasion\": \"casual\"}.")
    unknown = sorted(set(body) - set(CHOICES) - set(WEATHER_FIELDS))
    if unknown:
        raise outfits.ContextError(f"These are not part of today's choices: {', '.join(unknown)}.")
    given = {k: body[k] for k in WEATHER_FIELDS if body.get(k) is not None}

    forecast, place, old, message = None, None, False, None
    if len(given) < len(WEATHER_FIELDS):
        found = weather.lookup(state)
        place = found["place"]
        if found["weather"] and found["is_today"]:
            forecast, old = found["weather"], found["old"]
            message = found["message"] if old else None
        elif "low_c" not in given or "high_c" not in given:
            if not place:
                raise outfits.ContextError(
                    "Choose where you are in Settings so Closet can look up the weather, or give today's low and high temperatures.")
            raise outfits.ContextError(f"{found['message']} Give today's low and high temperatures instead.")

    day = {k: given[k] if k in given else (forecast[k] if forecast else False) for k in WEATHER_FIELDS}
    request = {k: body[k] for k in CHOICES if body.get(k) is not None}
    ctx, count = outfits.parse_request({**request, **day, "worn_days_ago": worn_days_ago(conn)})
    rows = closet_rows(conn)
    if ctx.build_around and not any(r["id"] == ctx.build_around for r in rows):
        raise outfits.ContextError("The item to build around is not in this closet.")

    from_forecast = [k for k in WEATHER_FIELDS if k not in given and forecast]
    source = "given" if not from_forecast else ("forecast" if not given else "forecast and given")
    context = {
        "date": forecast["date"] if forecast else wears.today().isoformat(),
        "low_c": ctx.low_c, "high_c": ctx.high_c, "rain": ctx.rain, "source": source, "old": old,
        "place": place["name"] if place and forecast else None,
        "rain_chance": forecast["rain_chance"] if forecast and "rain" not in given else None,
        "summary": forecast["summary"] if forecast else None,
        "message": message,
    }
    return {**outfits.suggest(rows, ctx, count), "context": context}
