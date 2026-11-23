"""Today's outfits by themselves: the weather, the wear log and the laundry fed to the engine.

`suggest(conn, state, body)` takes what the owner chose (occasion, mood, an
item to build around, items to leave out, how many outfits) and fills in the
rest: the day's temperatures and rain from the forecast for the saved place
(unless given), how many days ago each item was last worn from the wear log,
and what the owner's ratings of outfits worn before ask (`outfits.feedback_from`).
The forecast is read hour by hour for the hours the owner is out (`closet/day.py`): the engine dresses for what
those hours feel like and whether it rains in them. A day note that holds today (`closet/daynote.py`: "in Lisbon
until Friday, outside from noon") moves the weather to its place, the hours to its hours, and offers its occasion.
Items in the laundry are left out by the engine itself. `again` starts from an
outfit worn before: its pieces that can be worn today keep their places.
"""
from __future__ import annotations

import dataclasses
import json
from datetime import date

from . import day as dayparts
from . import daynote, items, kinds, look, outfits, stylejobs, styleprofile, styling, vocab, wears, weather, worn
from .state import State
from .tagger.taxonomy import FOOTWEAR, GARMENTS

CHOICES = ("occasion", "mood", "build_around", "leave_out", "count", "again", "ask_again", "say", "looking_at")
TALK = ("again", "ask_again", "say", "looking_at")   # choices that are not the engine's
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
    """What is known about an item's cloth, in the keys the engine reads: `weight_class`, the silhouette (its coarse
    shape) and `kind`, the garment in the owner's taxonomy (the owner's own choice on the item page, else the
    tagger's; for a shoe, the kind its page shows; None when neither said).

    The look is read from one place (`look`): the description the drawing was made from, with the owner's
    corrections folded over it, so the engine, the stylist, gaps and trips dress the same garment the page draws. The
    silhouette is its shape as drawn (`look.shape`): the details decide (the owner's over Claude's), the coarse shape
    fills in.

    Order of trust for the weight:
      1. what the owner set by hand: a material or name whose `source` is "user" (as `items.update` records it)
         and whose words give a weight (a bare fibre, "wool" or "cotton", is not enough);
      2. for a fleece (pullover or jacket), its pile: sherpa super heavy, polar fleece or anything else heavyweight;
      3. the look's details (the owner's over the tagger's): its weight unless "unknown", then for knitwear its knit
         gauge;
      4. the words in the name and material, and 5. the category: the engine's own guess (`outfits._weight`, and the
         category's usual sleeve), used when steps 1 to 3 leave `weight_class` empty or the sleeve unsaid.
    A stored answer that is missing, empty or not valid JSON counts as nothing known.
    """
    source = _json(row["source"])
    source = source if isinstance(source, dict) else {}
    found = look.answer(row)
    details = found.get("details") if isinstance(found, dict) else None
    details = details if isinstance(details, dict) else {}
    silhouette = look.shape_of(found) if found is not None else _plain_shape(row)

    own = _json(row["own_details"]) if "own_details" in row.keys() else None
    own = own if isinstance(own, dict) else {}
    said = own.get("garment") if isinstance(own.get("garment"), str) else details.get("garment")   # the owner's kind wins
    kind = said if isinstance(said, str) and said in GARMENTS else None   # an accessory has no garment kind here
    if kind is None:   # a shoe's kind as its page shows it (`kinds.of_row`): a tennis shoe is for tennis
        shoe = kinds.of_row(row)["kind"]
        kind = shoe if shoe in FOOTWEAR else None
    fabric = own.get("fabric") or details.get("fabric")
    fabric = fabric if isinstance(fabric, str) else None

    weight = next((w for w in (_owner_weight(row[f]) for f in ("material", "name") if source.get(f) == "user") if w), None)
    if weight is None and kind in FLEECE_KINDS:
        weight = FLEECE_WEIGHT.get(fabric, "heavyweight")
    if weight is None and details.get("weight") in outfits.WEIGHT_CLASSES:
        weight = details["weight"]
    if weight is None and isinstance(details.get("knit_gauge"), str):
        weight = KNIT_GAUGE_WEIGHT.get(details["knit_gauge"])
    return {"weight_class": weight, "silhouette": silhouette, "kind": kind}


def _plain_shape(row) -> dict:
    """The coarse shape of an item with no description and no details of the owner's: its own fields, as the drawing
    of such an item reads them (`details.plain_answer`)."""
    found = _json(row["silhouette"])
    return {k: v for k, v in found.items() if k in vocab.SILHOUETTE and v in vocab.SILHOUETTE[k]} if isinstance(found, dict) else {}


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
    """Which pieces of an outfit worn before come back today: those that can be worn, by the engine's own list of
    what cannot (`outfits._unavailable`: in the laundry, archived, waiting to be mended, disliked or left out). A piece
    Nines never chooses by itself (tennis shoes, swim trunks, lounge pants) comes back: the owner asks for it by name,
    as when building around it. Places the outfit left empty, and those whose piece cannot be worn, are open."""
    by_id = {r["id"]: r for r in rows}
    today_ = outfits.Context(0, 0, leave_out=tuple(leave_out))   # only what is left out is read from it
    kept, unavailable = [], []
    for place in outfits.PLACES:
        pid = outfit["pieces"].get(place)
        if not pid:
            continue
        r = by_id.get(pid)
        if r is None or outfits._unavailable(r, today_) not in (None, *outfits.ASKED_FOR_ONLY):
            unavailable.append(pid)
        else:
            kept.append(pid)
    return {"id": outfit["id"], "worn_on": outfit["worn_on"], "kept": kept, "unavailable": unavailable}


def suggest(conn, state: State, body: object, stylist: stylejobs.Stylist | None = None, path=None,
            ahead: bool = False, from_hour: int | None = None) -> dict:
    """Outfits for today plus the context used. Raises outfits.ContextError with a sentence for a bad request.

    With a `stylist` (and `path`, the closet's database, for its thread), Claude chooses: its outfits for today
    are given when they are ready, and the rules engine's meanwhile and whenever Claude cannot be asked;
    `context.stylist` says which (`closet/stylejobs.py`). `ask_again` in the body asks Claude afresh; `say` sends
    Claude a message about the outfits on the page (the conversation), which it answers in the background, and
    `looking_at` says which of the outfits was in front of the owner as they wrote (0 is the first).

    `ahead`: this is not the owner asking but Nines, ahead of their first look (`closet/styleahead.py`). Claude is
    then asked only for a day read from today's fresh forecast: outfits for a guessed or an old day would be asked
    again as soon as the owner opened Today. `from_hour` (with `ahead`): the hour the owner usually first looks, by
    the clock; the day is read from then on when that is still to come, as it will be when they look."""
    if not isinstance(body, dict):
        raise outfits.ContextError("Send today's choices as an object, for example {\"occasion\": \"casual\"}.")
    unknown = sorted(set(body) - set(CHOICES) - set(WEATHER_FIELDS))
    if unknown:
        raise outfits.ContextError(f"These are not part of today's choices: {', '.join(unknown)}.")
    given = {k: body[k] for k in WEATHER_FIELDS if body.get(k) is not None}
    note = daynote.current(state, wears.today())
    on = note if daynote.active(note, wears.today()) else None   # a note for days still ahead changes nothing yet

    forecast, place, old, message, mild, reading = None, None, False, None, False, None
    if len(given) < len(WEATHER_FIELDS):
        found = weather.lookup(state, on.get("place") if on else None)
        place = found["place"]
        if found["weather"] and found["is_today"]:
            forecast, old = found["weather"], found["old"]
            message = found["message"] if old else None
            at = found["hour"]
            if ahead and from_hour is not None and at is not None:
                at = max(at, from_hour)
            reading = dayparts.read(forecast.get("hours") or [], daynote.outside(on), at)
        elif "low_c" not in given or "high_c" not in given:
            # never no outfit just because the weather is missing: dress for a mild day and say why
            mild = True
            message = (found["message"] if not found["weather"]
                       else "Today's forecast could not be fetched; the last one Nines got is for an earlier day.")

    if mild:
        def number(v):
            return isinstance(v, int | float) and not isinstance(v, bool)
        low = given["low_c"] if "low_c" in given else (
            min(MILD["low_c"], given["high_c"]) if number(given.get("high_c")) else MILD["low_c"])
        high = given["high_c"] if "high_c" in given else (max(MILD["high_c"], low) if number(low) else MILD["high_c"])
        day = {"low_c": low, "high_c": high, "rain": given.get("rain", MILD["rain"])}
    else:
        # the hours the owner is out, as they feel, where the forecast has them; else the whole day's low and high
        dressed = ({"low_c": reading["feels_low_c"], "high_c": reading["feels_high_c"], "rain": reading["wet"]}
                   if reading else forecast)
        day = {k: given[k] if k in given else (dressed[k] if dressed else False) for k in WEATHER_FIELDS}
    if body.get("ask_again") is not None and not isinstance(body["ask_again"], bool):
        raise outfits.ContextError("ask_again must be true or false.")
    say = body.get("say")
    if say is not None:
        say = " ".join(say.split()) if isinstance(say, str) else ""
        if not say:
            raise outfits.ContextError("Write what you want to tell Claude about these outfits.")
        if len(say) > styling.MAX_SAY:
            raise outfits.ContextError(f"A message to Claude can be at most {styling.MAX_SAY} characters long; "
                                       f"this is {len(say):,}.")
    looking_at = body.get("looking_at")
    if looking_at is not None and (isinstance(looking_at, bool) or not isinstance(looking_at, int) or looking_at < 0):
        raise outfits.ContextError("looking_at must be the place of the outfit on the page, 0 for the first.")
    request = {k: body[k] for k in CHOICES if body.get(k) is not None and k not in TALK}
    if on and on.get("occasion") and "occasion" not in request:
        request["occasion"] = on["occasion"]
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
        # the hours dressed for, read from the forecast (None when it has no hours, or every number was typed)
        "detail": reading if from_forecast else None,
        "note": daynote.describe(note, wears.today()),
    }
    if again is not None:
        context["again"] = again
    answer = outfits.suggest(rows, ctx, count, feedback)
    if say is not None and (stylist is None or not answer["outfits"]):
        raise outfits.ContextError("Claude isn't choosing your outfits here, so the message wasn't sent.")
    if ahead and (source != "forecast" or old):
        stylist = None
    if stylist is not None and answer["outfits"]:
        recent = worn.list_outfits(conn, styling.HISTORY)["outfits"]
        profile = styleprofile.text_for_stylist(conn)

        def told():   # only when Claude is asked: the engine's longer shortlist, and everything Claude reads
            shortlist = outfits.suggest(rows, ctx, max(count, styling.SHORTLIST), feedback)["outfits"]
            return styling.brief(rows, context, ctx, wears.today(), recent, shortlist, profile)

        try:
            found = stylist.for_today(
                conn, path, day=wears.today(), key=stylejobs.key_of(wears.today().isoformat(), context, ctx, rows, profile),
                ctx=ctx, ids=set(styling.listed(rows, ctx).ids),
                worn_today=any(o.get("worn_on") == wears.today().isoformat() for o in recent),
                again=bool(body.get("ask_again")), brief=told, not_again=feedback.not_again,
                say=say, engine=answer["outfits"], count=count, looking_at=looking_at)
        except stylejobs.Refused as e:
            raise outfits.ContextError(str(e)) from None
        if found["state"] == stylejobs.READY:
            answer["outfits"] = stylejobs.merged(found["outfits"], answer["outfits"], count)
        context["stylist"] = stylejobs.public(found)
    return {**answer, "context": context}
