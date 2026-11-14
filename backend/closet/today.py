"""Today's outfits by themselves: the weather, the wear log and the laundry fed to the engine.

`suggest(conn, state, body)` takes what the owner chose (occasion, mood, an
item to build around, items to leave out, how many outfits) and fills in the
rest: the day's temperatures and rain from the forecast for the saved place
(unless given), how many days ago each item was last worn from the wear log,
and what the owner's ratings of outfits worn before ask (`outfits.feedback_from`).
Items in the laundry are left out by the engine itself. `again` starts from an
outfit worn before: its pieces that can be worn today keep their places.
"""
from __future__ import annotations

import dataclasses
import json
from datetime import date

from . import items, outfits, wears, weather, worn
from .state import State
from .tagger.taxonomy import GARMENTS

CHOICES = ("occasion", "mood", "build_around", "leave_out", "count", "again")
WEATHER_FIELDS = ("low_c", "high_c", "rain")
# The day dressed for when no forecast can be had and no temperatures were given (DECISIONS "Today's outfits by themselves")
MILD = {"low_c": 14.0, "high_c": 20.0, "rain": False}

# A knit's gauge says how heavy it is when the tagger could not tell the weight itself.
KNIT_GAUGE_WEIGHT = {
    "extra_fine": "lightweight",   # thin, smooth stitches: a knit to wear like a shirt
    "fine": "lightweight",         # a fine merino or cotton knit, light enough to go under a jacket
    "medium": "midweight",         # the usual sweater
    "chunky": "heavyweight",       # thick stitches, warm and bulky
    "super_chunky": "super_heavy",  # as thick as fleece
}
# A fleece's weight is its pile's: polar fleece is heavyweight, sherpa as heavy as cloth comes.
FLEECE_KINDS = ("fleece_pullover", "fleece_jacket")
FLEECE_WEIGHT = {"polar_fleece": "heavyweight", "sherpa": "super_heavy"}
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
    """What is known about an item's cloth, in the keys the engine reads: `weight_class`, the silhouette's sleeve
    and `kind`, the garment in the owner's taxonomy (the owner's own choice on the item page, else the tagger's;
    None when neither said).

    Order of trust, for the weight as for the sleeve:
      1. what the owner set by hand: a material or name whose `source` is "user" (as `items.update` records it)
         and whose words give a weight (a bare fibre, "wool" or "cotton", is not enough); a sleeve in the
         silhouette (the owner's, or the answer's copied there when it was described);
      2. for a fleece (pullover or jacket), its pile: sherpa super heavy, polar fleece or anything else heavyweight;
      3. the tagger's stored answer: its weight unless "unknown", then for knitwear its knit gauge; its sleeve length;
      4. the words in the name and material, and 5. the category: the engine's own guess (`outfits._weight`, and the
         category's usual sleeve), used when steps 1 to 3 leave `weight_class` empty or the sleeve unsaid.
    A stored answer that is missing, empty or not valid JSON counts as nothing known.
    """
    source = _json(row["source"])
    source = source if isinstance(source, dict) else {}
    answer = _json(row["tag_answer"])
    details = answer.get("details") if isinstance(answer, dict) else None
    details = details if isinstance(details, dict) else {}
    silhouette = _json(row["silhouette"])
    silhouette = dict(silhouette) if isinstance(silhouette, dict) else {}

    own = _json(row["own_details"]) if "own_details" in row.keys() else None
    own = own if isinstance(own, dict) else {}
    kind = next((k for k in (own.get("garment"), details.get("garment")) if isinstance(k, str) and k in GARMENTS), None)
    fabric = own.get("fabric") or details.get("fabric")

    weight = next((w for w in (_owner_weight(row[f]) for f in ("material", "name") if source.get(f) == "user") if w), None)
    if weight is None and kind in FLEECE_KINDS:
        weight = FLEECE_WEIGHT.get(fabric, "heavyweight")
    if weight is None and details.get("weight") in outfits.WEIGHT_CLASSES:
        weight = details["weight"]
    if weight is None and isinstance(details.get("knit_gauge"), str):
        weight = KNIT_GAUGE_WEIGHT.get(details["knit_gauge"])
    if not silhouette.get("sleeve") and isinstance(details.get("sleeve_length"), str) and details["sleeve_length"] in SLEEVE_LENGTH:
        silhouette["sleeve"] = SLEEVE_LENGTH[details["sleeve_length"]]
    return {"weight_class": weight, "silhouette": silhouette, "kind": kind}


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


def again_of(outfit: dict, rows: list[dict], leave_out: set[str]) -> dict:
    """Which pieces of an outfit worn before come back today: those that can be worn (not in the laundry,
    archived, disliked or left out). Places it left empty, and those whose piece cannot be worn, are open."""
    by_id = {r["id"]: r for r in rows}
    kept, unavailable = [], []
    for place in outfits.PLACES:
        pid = outfit["pieces"].get(place)
        if not pid:
            continue
        r = by_id.get(pid)
        if r is None or r.get("status") == "archived" or outfits._in_laundry(r) or r.get("rating") == "dislike" or pid in leave_out:
            unavailable.append(pid)
        else:
            kept.append(pid)
    return {"id": outfit["id"], "worn_on": outfit["worn_on"], "kept": kept, "unavailable": unavailable}


def suggest(conn, state: State, body: object) -> dict:
    """Outfits for today plus the context used. Raises outfits.ContextError with a sentence for a bad request."""
    if not isinstance(body, dict):
        raise outfits.ContextError("Send today's choices as an object, for example {\"occasion\": \"casual\"}.")
    unknown = sorted(set(body) - set(CHOICES) - set(WEATHER_FIELDS))
    if unknown:
        raise outfits.ContextError(f"These are not part of today's choices: {', '.join(unknown)}.")
    given = {k: body[k] for k in WEATHER_FIELDS if body.get(k) is not None}

    forecast, place, old, message, mild = None, None, False, None, False
    if len(given) < len(WEATHER_FIELDS):
        found = weather.lookup(state)
        place = found["place"]
        if found["weather"] and found["is_today"]:
            forecast, old = found["weather"], found["old"]
            message = found["message"] if old else None
        elif "low_c" not in given or "high_c" not in given:
            # never no outfit just because the weather is missing: dress for a mild day and say why
            mild = True
            message = (found["message"] if not found["weather"]
                       else "Today's forecast could not be fetched; the last one Closet got is for an earlier day.")

    if mild:
        def number(v):
            return isinstance(v, int | float) and not isinstance(v, bool)
        low = given["low_c"] if "low_c" in given else (
            min(MILD["low_c"], given["high_c"]) if number(given.get("high_c")) else MILD["low_c"])
        high = given["high_c"] if "high_c" in given else (max(MILD["high_c"], low) if number(low) else MILD["high_c"])
        day = {"low_c": low, "high_c": high, "rain": given.get("rain", MILD["rain"])}
    else:
        day = {k: given[k] if k in given else (forecast[k] if forecast else False) for k in WEATHER_FIELDS}
    request = {k: body[k] for k in CHOICES if body.get(k) is not None and k != "again"}
    ctx, count = outfits.parse_request({**request, **day, "worn_days_ago": worn_days_ago(conn)})
    rows = closet_rows(conn)
    if ctx.build_around and not any(r["id"] == ctx.build_around for r in rows):
        raise outfits.ContextError("The item to build around is not in this closet.")
    again = None
    if body.get("again") is not None:
        if not isinstance(body["again"], str) or not body["again"]:
            raise outfits.ContextError("The outfit to wear again must be a worn outfit's id.")
        try:
            before = worn.get(conn, body["again"])
        except items.ItemError:
            raise outfits.ContextError("That outfit is no longer in your list of worn outfits.") from None
        again = again_of(before, rows, set(ctx.leave_out))
        ctx = dataclasses.replace(ctx, keep=tuple(again["kept"]))
    feedback = outfits.feedback_from(worn.rated(conn), rows, ctx)

    from_forecast = [k for k in WEATHER_FIELDS if k not in given and forecast]
    source = "mild" if mild else "given" if not from_forecast else ("forecast" if not given else "forecast and given")
    context = {
        "date": forecast["date"] if forecast else wears.today().isoformat(),
        "low_c": ctx.low_c, "high_c": ctx.high_c, "rain": ctx.rain, "source": source, "old": old,
        "place": place["name"] if place and forecast else None,
        "rain_chance": forecast["rain_chance"] if forecast and "rain" not in given else None,
        "summary": forecast["summary"] if forecast else None,
        "message": message,
    }
    if again is not None:
        context["again"] = again
    return {**outfits.suggest(rows, ctx, count, feedback), "context": context}
