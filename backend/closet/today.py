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

# A knit's gauge says how heavy it is when the tagger could not tell the weight itself.
KNIT_GAUGE_WEIGHT = {
    "extra_fine": "lightweight",   # thin, smooth stitches: a knit to wear like a shirt
    "fine": "lightweight",         # a fine merino or cotton knit, light enough to go under a jacket
    "medium": "midweight",         # the usual sweater
    "chunky": "heavyweight",       # thick stitches, warm and bulky
    "super_chunky": "super_heavy",  # as thick as fleece
}
# The answer's sleeve length as the silhouette's sleeve (none, short or long).
SLEEVE_LENGTH = {"sleeveless": "none", "short": "short", "elbow": "short", "three_quarter": "long", "long": "long"}
# Bare fibres say less about weight than the tagger's look at the cloth, so the owner's typing them does not overrule it.
FIBRE_WORDS = ("wool", "cotton")
LEFT_OUT = ("illustration_svg", "confidence", "source", "tag_answer")  # the engine reads what is taken from these instead


def _json(text: object) -> object:
    try:
        return json.loads(text) if isinstance(text, str) and text else None
    except ValueError:
        return None


def _owner_weight(text: object) -> str | None:
    words = outfits._words(text)
    return next((outfits.WEIGHT_CLASSES[level] for word, level in outfits.WEIGHT_WORDS
                 if word in words and word not in FIBRE_WORDS), None)


def cloth(row) -> dict:
    """What is known about an item's cloth, in the keys the engine reads: `weight_class` and the silhouette's sleeve.

    Order of trust, for the weight as for the sleeve:
      1. what the owner set by hand: a material or name whose `source` is "user" (as `items.update` records it)
         and whose words give a weight (a bare fibre, "wool" or "cotton", is not enough); a sleeve in the
         silhouette (the owner's, or the answer's copied there when it was described);
      2. the tagger's stored answer: its weight unless "unknown", then for knitwear its knit gauge; its sleeve length;
      3. the words in the name and material, and 4. the category: the engine's own guess (`outfits._weight`, and the
         category's usual sleeve), used when steps 1 and 2 leave `weight_class` empty or the sleeve unsaid.
    A stored answer that is missing, empty or not valid JSON counts as nothing known.
    """
    source = _json(row["source"])
    source = source if isinstance(source, dict) else {}
    answer = _json(row["tag_answer"])
    details = answer.get("details") if isinstance(answer, dict) else None
    details = details if isinstance(details, dict) else {}
    silhouette = _json(row["silhouette"])
    silhouette = dict(silhouette) if isinstance(silhouette, dict) else {}

    weight = next((w for w in (_owner_weight(row[f]) for f in ("material", "name") if source.get(f) == "user") if w), None)
    if weight is None and details.get("weight") in outfits.WEIGHT_CLASSES:
        weight = details["weight"]
    if weight is None and isinstance(details.get("knit_gauge"), str):
        weight = KNIT_GAUGE_WEIGHT.get(details["knit_gauge"])
    if not silhouette.get("sleeve") and isinstance(details.get("sleeve_length"), str) and details["sleeve_length"] in SLEEVE_LENGTH:
        silhouette["sleeve"] = SLEEVE_LENGTH[details["sleeve_length"]]
    return {"weight_class": weight, "silhouette": silhouette}


def closet_rows(conn) -> list[dict]:
    """Every item in the open closet as the outfit engine and the gap analysis read it, in id order."""
    return [{**{k: r[k] for k in r.keys() if k not in LEFT_OUT}, **cloth(r)}
            for r in conn.execute("SELECT * FROM items ORDER BY id")]


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
