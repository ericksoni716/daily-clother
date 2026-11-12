"""Deterministic wardrobe rules. No database, network, clock, or saved state."""
from __future__ import annotations

import colorsys
import math
from dataclasses import dataclass
from heapq import nsmallest

from . import vocab

DEFAULT_COUNT = 3  # A small set of choices rather than a catalogue.
MIN_COUNT = 1  # At least one suggestion must be requested.
MAX_COUNT = 10  # Bound the response size.
MIN_TEMPERATURE_C = -60  # Reject implausible weather inputs.
MAX_TEMPERATURE_C = 60  # Reject implausible weather inputs.
COLD_C = 8  # Below this low, prefer both a middle layer and a heavy outer layer.
COOL_C = 18  # Below this low, prefer a removable layer.
HOT_C = 24  # At or above this low, offer no middle or outer layer.
WIDE_RANGE_C = 10  # Explain when the high requires removing morning layers.
WEIGHTS = {"lightweight": 1, "midweight": 2, "heavyweight": 3, "super_heavy": 4}  # Relative cloth weight.
FITS = {"slim": 0, "regular": 1, "oversized": 2}  # Outer layers must have at least as much room.
MOOD_SHIFT = {"usual": 0, "sharp": 0.5, "relaxed": -0.5}  # Half a formality step, not a new occasion.
FORMALITY_SPAN = 1  # All pieces must be within one dressiness step of one another.
OCCASION_DISTANCE = 1  # Prefer outfits within one step of the stated occasion.
MAX_LOUD_PATTERNS = 1  # Coarse tags cannot distinguish subtle from bold prints.
MAX_COLOUR_FAMILIES = 1  # Strong colours must share a tonal family.
RECENT_DAYS = 3  # Rest pieces worn within the last three days when alternatives exist.
BASE_SCORE = 90  # A suitable outfit starts here before preferences and compromises.
MIN_SCORE = 0  # Public score lower bound.
MAX_SCORE = 100  # Public score upper bound.
FORMALITY_PENALTY = 10  # Per piece and step away from the mood-adjusted target.
SEASON_PENALTY = 12  # Per piece tagged for the opposite temperature season.
WEIGHT_PENALTY = 6  # Per weight step; temperature suitability beats a single favourite.
HOT_SLEEVE_PENALTY = 6  # Prefer short sleeves at a hot day's high.
MISSING_OUTER_PENALTY = 30  # A cold day without an outer layer is a substantial compromise.
MISSING_MID_PENALTY = 10  # Prefer insulation below the coat on cold days.
LAYER_COUNT_PENALTY = 12  # Prefer one removable layer in cool weather and none in mild weather.
RAIN_OUTER_PENALTY = 5  # Prefer outer cloth that gives some evidence of rain protection.
RAIN_SHOE_PENALTY = 8  # Avoid open shoes, canvas and suede in rain.
COLD_EXPOSURE_PENALTY = 18  # Shorts and sandals leave skin exposed on cold days.
RATING_BONUS = {"love": 4, "like": 2, "meh": 0}  # Reward favourites without outweighing weather.
RECENT_PENALTY = 18  # Equal unworn pieces beat recently worn favourites.
UNKNOWN_PENALTY = 2  # Slightly prefer pieces whose matching attributes are known.
BEAM_WIDTH = 256  # Retain this many partial outfits per formality band and anchor position.
MIN_DIFFERENT_PIECES = 2  # Swapping a jacket for a hoodie is only one garment change.
HEX_CHANNEL_MAX = 255  # Scale stored RGB bytes to colour-space fractions.
NEUTRAL_SATURATION = 0.18  # Nearly grey hex-only colours count as neutral.
NEUTRAL_DARKNESS = 0.18  # Very dark hex-only colours count as neutral.
HUE_FAMILIES = ("red", "orange", "yellow", "green", "green", "green",
                "blue", "blue", "blue", "purple", "purple", "red")  # Hue sectors share the named-colour families.

PLACES = ("base_top", "mid_layer", "outer_layer", "bottom", "shoes", "accessories")
CATEGORIES = {
    "base_top": {"tee", "shirt", "polo", "sweater", "hoodie"},
    "mid_layer": {"shirt", "sweater", "hoodie", "jacket"},
    "outer_layer": {"jacket", "coat"},
    "bottom": {"jeans", "trousers", "shorts"},
    "shoes": {"sneakers", "boots", "dress_shoes", "sandals"},
    "accessories": {"bag", "belt", "hat", "scarf"},
}
REQUIRED = {"base_top", "bottom", "shoes"}
NEUTRALS = {"black", "white", "grey", "navy", "olive", "tan", "brown", "cream"}
COLOUR_FAMILY = {"blue": "blue", "light_blue": "blue", "red": "red", "burgundy": "red", "pink": "red"}
LIGHT_MATERIALS = ("linen", "poplin", "voile", "seersucker", "silk", "merino")
HEAVY_MATERIALS = ("flannel", "fleece", "tweed", "melton", "shearling", "chunky", "canvas", "heavy")
MIDWEIGHT_MATERIALS = ("wool", "cashmere", "corduroy", "denim", "leather")
RAIN_MATERIALS = ("waxed", "waterproof", "water-resistant", "water resistant", "nylon")
DELICATE_MATERIALS = ("suede", "canvas")
CONTEXT_FIELDS = {"low_c", "high_c", "rain", "occasion", "mood", "build_around", "exclude", "days_since_worn"}


def validate_context(context: dict, count: int = DEFAULT_COUNT) -> dict:
    """Return a fresh, defaulted context or raise ValueError with readable words."""
    if not isinstance(context, dict):
        raise ValueError("Send an object describing the day's weather and occasion.")
    if set(context) - CONTEXT_FIELDS:
        raise ValueError("Some fields are not recognised. Use the weather, occasion, mood and item choices.")
    if type(count) is not int or not MIN_COUNT <= count <= MAX_COUNT:
        raise ValueError(f"Choose between {MIN_COUNT} and {MAX_COUNT} outfits.")
    for key, label in (("low_c", "low"), ("high_c", "high")):
        value = context.get(key)
        if (type(value) not in (int, float) or not MIN_TEMPERATURE_C <= value <= MAX_TEMPERATURE_C
                or not math.isfinite(value)):
            raise ValueError(f"The day's {label} must be a temperature in °C between {MIN_TEMPERATURE_C} and {MAX_TEMPERATURE_C}.")
    if context["low_c"] > context["high_c"]:
        raise ValueError("The day's low cannot be higher than its high.")
    if type(context.get("rain")) is not bool:
        raise ValueError("Say whether rain is expected using true or false.")
    if context.get("occasion") not in vocab.FORMALITY:
        raise ValueError("Choose an occasion: athletic, casual, smart casual, business or formal.")
    mood = context.get("mood", "usual")
    if not isinstance(mood, str) or mood not in MOOD_SHIFT:
        raise ValueError("Choose a mood: usual, sharp or relaxed.")
    anchor = context.get("build_around")
    if anchor is not None and (not isinstance(anchor, str) or not anchor.strip()):
        raise ValueError("The item to build around must be a non-empty item id.")
    exclude = context.get("exclude", [])
    if not isinstance(exclude, list) or any(not isinstance(i, str) or not i.strip() for i in exclude):
        raise ValueError("Items to leave out must be a list of item ids.")
    worn = context.get("days_since_worn", {})
    if not isinstance(worn, dict) or any(not isinstance(k, str) or not k.strip() or type(v) is not int or v < 0
                                        for k, v in worn.items()):
        raise ValueError("For each worn item, give its id and a whole number of days ago, zero or more.")
    return {**context, "mood": mood, "build_around": anchor, "exclude": list(exclude), "days_since_worn": dict(worn)}


def _weight(item: dict) -> int:
    if item.get("weight_class") in WEIGHTS:
        return WEIGHTS[item["weight_class"]]
    material = (item.get("material") or "").lower()
    if any(word in material for word in HEAVY_MATERIALS):
        return WEIGHTS["heavyweight"]
    if any(word in material for word in LIGHT_MATERIALS):
        return WEIGHTS["lightweight"]
    category = item.get("category")
    if category == "coat":
        return WEIGHTS["heavyweight"]
    if category in {"sweater", "hoodie", "jacket", "jeans", "boots"}:
        return WEIGHTS["midweight"]
    if any(word in material for word in MIDWEIGHT_MATERIALS):
        return WEIGHTS["midweight"]
    return WEIGHTS["lightweight"]


def _colour(item: dict) -> str | None:
    colour = item.get("color")
    if colour in NEUTRALS:
        return None
    if colour:
        return COLOUR_FAMILY.get(colour, colour)
    hex_colour = item.get("color_hex") or ""
    try:
        if len(hex_colour) != 7 or not hex_colour.startswith("#"):
            return None
        rgb = tuple(int(hex_colour[n:n + 2], 16) / HEX_CHANNEL_MAX for n in (1, 3, 5))
    except ValueError:
        return None
    hue, saturation, value = colorsys.rgb_to_hsv(*rgb)
    if saturation <= NEUTRAL_SATURATION or value <= NEUTRAL_DARKNESS:
        return None
    return HUE_FAMILIES[round(hue * len(HUE_FAMILIES)) % len(HUE_FAMILIES)]


@dataclass(frozen=True)
class _Piece:
    id: str
    category: str
    rank: int
    weight: int
    fit: int
    colour: str | None
    loud: bool
    item: dict


def _piece(item: dict) -> _Piece:
    category = item["category"]
    fallback = "business" if category == "dress_shoes" else "casual"
    formality = item.get("formality") or fallback
    return _Piece(item["id"], category, vocab.FORMALITY.index(formality), _weight(item),
                  FITS.get((item.get("silhouette") or {}).get("fit"), FITS["regular"]),
                  _colour(item), item.get("pattern") not in (None, "solid"), item)


def _available(item: dict, excluded: set[str]) -> bool:
    return (item["id"] not in excluded and item.get("status", "active") == "active"
            and item.get("rating") != "dislike" and item.get("location") != "laundry"
            and item.get("laundry_state") in (None, "clean"))


def _compatible(parts: tuple, piece: _Piece | None, place: str) -> bool:
    chosen = [p for p in parts if p is not None]
    if piece is not None:
        if any(p.id == piece.id for p in chosen):
            return False
        all_pieces = chosen + [piece]
        ranks = [p.rank for p in all_pieces]
        if max(ranks) - min(ranks) > FORMALITY_SPAN:
            return False
        if sum(p.loud for p in all_pieces) > MAX_LOUD_PATTERNS:
            return False
        colours = [p.colour for p in all_pieces if p.colour]
        if len(set(colours)) > MAX_COLOUR_FAMILIES or (colours.count("multi") > MAX_COLOUR_FAMILIES):
            return False
        if place in ("mid_layer", "outer_layer"):
            inner = chosen[-1]
            if inner.weight > piece.weight or inner.fit > piece.fit:
                return False
            if place == "mid_layer" and (inner.category in {"sweater", "hoodie"}
                                         or (piece.category == "shirt" and inner.category != "tee")):
                return False
    if place == "outer_layer":
        middle = parts[PLACES.index("mid_layer")]
        if middle and middle.category == "jacket" and (piece is None or piece.category != "coat"):
            return False
    return True


def _item_cost(piece: _Piece, place: str, day: dict) -> float:
    item, low, high = piece.item, day["low_c"], day["high_c"]
    target = max(0, min(len(vocab.FORMALITY) - 1, vocab.FORMALITY.index(day["occasion"]) + MOOD_SHIFT[day["mood"]]))
    cost = abs(piece.rank - target) * FORMALITY_PENALTY - RATING_BONUS.get(item.get("rating"), 0)
    if day["days_since_worn"].get(piece.id, RECENT_DAYS + 1) <= RECENT_DAYS:
        cost += RECENT_PENALTY
    if ((low < COLD_C and item.get("season") == "warm")
            or (high >= HOT_C and item.get("season") == "cool")):
        cost += SEASON_PENALTY
    ideal = WEIGHTS["lightweight"]
    if low < COLD_C and place == "outer_layer":
        ideal = WEIGHTS["heavyweight"]
    elif low < COOL_C and place in ("mid_layer", "outer_layer", "bottom", "shoes"):
        ideal = WEIGHTS["midweight"]
    cost += abs(piece.weight - ideal) * WEIGHT_PENALTY
    if high >= HOT_C and place == "base_top" and (item.get("silhouette") or {}).get("sleeve") == "long":
        cost += HOT_SLEEVE_PENALTY
    if low < COLD_C and piece.category in {"shorts", "sandals"}:
        cost += COLD_EXPOSURE_PENALTY
    material = (item.get("material") or "").lower()
    if day["rain"]:
        if place == "outer_layer" and not any(m in material for m in RAIN_MATERIALS):
            cost += RAIN_OUTER_PENALTY
        if place == "shoes" and (piece.category == "sandals" or any(m in material for m in DELICATE_MATERIALS)):
            cost += RAIN_SHOE_PENALTY
    if any(not item.get(f) for f in ("formality", "color", "pattern", "season")):
        cost += UNKNOWN_PENALTY
    return cost


def _layer_cost(parts: tuple, day: dict) -> float:
    middle, outer = parts[PLACES.index("mid_layer")], parts[PLACES.index("outer_layer")]
    if day["low_c"] < COLD_C:
        return (MISSING_MID_PENALTY if middle is None else 0) + (MISSING_OUTER_PENALTY if outer is None else 0)
    desired = int(day["low_c"] < COOL_C)
    return abs(sum(p is not None for p in (middle, outer)) - desired) * LAYER_COUNT_PENALTY


def _key(candidate: tuple) -> tuple:
    cost, parts = candidate
    return cost, tuple(p.id if p else "" for p in parts)


def _search(pieces: list[_Piece], day: dict) -> list:
    anchor = day["build_around"]
    anchor_places = [place for place in PLACES if any(p.id == anchor and p.category in CATEGORIES[place] for p in pieces)]
    found = {}
    for anchor_place in anchor_places if anchor else [None]:
        for band in range(len(vocab.FORMALITY) - FORMALITY_SPAN):
            beam = [(0, ())]
            for place in PLACES:
                options = [p for p in pieces if p.category in CATEGORIES[place]
                           and band <= p.rank <= band + FORMALITY_SPAN
                           and (p.id != anchor or place == anchor_place)]
                if day["low_c"] >= HOT_C and place in ("mid_layer", "outer_layer"):
                    options = []
                if place == anchor_place:
                    options = [p for p in options if p.id == anchor]
                elif place not in REQUIRED:
                    # Only offer a scarf automatically; other accessories need an explicit build-around.
                    if place == "accessories":
                        options = [p for p in options if p.category == "scarf" and day["low_c"] < COLD_C]
                    options = [None, *options]
                costs = {p.id if p else None: _item_cost(p, place, day) if p else 0 for p in options}

                def extensions(beam=beam, options=options, costs=costs, place=place):
                    for cost, parts in beam:
                        for p in options:
                            if _compatible(parts, p, place):
                                new_parts = (*parts, p)
                                extra = _layer_cost(new_parts, day) if place == "outer_layer" else 0
                                yield cost + costs[p.id if p else None] + extra, new_parts

                beam = nsmallest(BEAM_WIDTH, extensions(), key=_key)
            for candidate in beam:
                found[_key(candidate)[1]] = candidate
    candidates = sorted(found.values(), key=_key)
    occasion = vocab.FORMALITY.index(day["occasion"])
    matching = [c for c in candidates if all(abs(p.rank - occasion) <= OCCASION_DISTANCE for p in c[1] if p)]
    candidates = matching or candidates
    if day["low_c"] < COLD_C:
        with_outer = [c for c in candidates if c[1][PLACES.index("outer_layer")] is not None]
        candidates = with_outer or candidates
        with_middle = [c for c in candidates if c[1][PLACES.index("mid_layer")] is not None]
        candidates = with_middle or candidates
    return candidates


def _reasons(parts: tuple, day: dict) -> list[str]:
    chosen = [p for p in parts if p]
    outer = parts[PLACES.index("outer_layer")]
    ranks = [p.rank for p in chosen]
    occasion = vocab.FORMALITY.index(day["occasion"])
    reasons = ["The pieces stay within one step of dressiness."]
    if any(abs(rank - occasion) > OCCASION_DISTANCE for rank in ranks):
        reasons.append(f"This closet cannot match a {day['occasion'].replace('_', ' ')} occasion with these choices.")
    elif any(rank != occasion for rank in ranks):
        reasons.append(f"Some pieces are a step away from {day['occasion'].replace('_', ' ')}; check the dress code.")
    else:
        reasons.append(f"The pieces match a {day['occasion'].replace('_', ' ')} occasion.")
    colours = [p.colour for p in chosen if p.colour]
    reasons.append("The strong colours share a tonal family, with neutrals alongside." if len(colours) > 1
                   else "Neutral colours keep the outfit easy to combine, with at most one strong colour.")
    if any(p.loud for p in chosen):
        reasons.append("One patterned piece is the focus; the others are plain.")
    if day["low_c"] >= HOT_C:
        reasons.append(f"No extra top layers for a low of {day['low_c']:g}°C.")
    elif outer or parts[PLACES.index("mid_layer")]:
        reasons.append("The top layers go from lighter to heavier, with room for the layer underneath.")
    if day["low_c"] < COLD_C:
        if outer is None:
            reasons.append(f"No compatible outer layer for {day['low_c']:g}°C; this outfit may leave you cold.")
        elif outer.weight < WEIGHTS["heavyweight"]:
            reasons.append(f"No heavy outer layer fits this combination for {day['low_c']:g}°C; this may not be warm enough.")
        else:
            reasons.append(f"A heavy outer layer adds warmth for {day['low_c']:g}°C; check comfort before going out.")
        if parts[PLACES.index("mid_layer")] is None:
            reasons.append("No compatible middle layer was found; you may need more insulation.")
        if any(p.category in {"shorts", "sandals"} for p in chosen):
            reasons.append("Bare legs or open shoes may leave you cold.")
    if day["high_c"] - day["low_c"] >= WIDE_RANGE_C:
        reasons.append(f"It reaches {day['high_c']:g}°C; remove extra layers as the day warms up.")
    if day["high_c"] >= HOT_C and ((parts[0].item.get("silhouette") or {}).get("sleeve") == "long"
                                 or parts[PLACES.index("bottom")].weight > WEIGHTS["lightweight"]):
        reasons.append("Long sleeves or heavier trousers may feel warm in the afternoon.")
    if any((day["low_c"] < COLD_C and p.item.get("season") == "warm")
           or (day["high_c"] >= HOT_C and p.item.get("season") == "cool") for p in chosen):
        reasons.append("Some pieces are tagged for another season; check how warm they feel.")
    if day["rain"]:
        material = (outer.item.get("material") or "").lower() if outer else ""
        if any(m in material for m in RAIN_MATERIALS):
            reasons.append("The outer material may help in rain, but its seams and waterproofing are not recorded.")
        else:
            reasons.append("Rain is expected; these tags do not establish rain protection. Take an umbrella.")
        shoe = parts[PLACES.index("shoes")]
        if shoe.category == "sandals" or any(m in (shoe.item.get("material") or "").lower() for m in DELICATE_MATERIALS):
            reasons.append("These shoes may get wet or mark in rain.")
        else:
            reasons.append("The shoes' waterproofing and grip are not recorded.")
    if any(p.item.get("rating") == "love" for p in chosen):
        reasons.append("This includes pieces you love.")
    if any(day["days_since_worn"].get(p.id, RECENT_DAYS + 1) <= RECENT_DAYS for p in chosen):
        reasons.append("This repeats something worn in the last few days to complete the outfit.")
    if any(p.item.get("weight_class") not in WEIGHTS for p in chosen):
        reasons.append("Some cloth weights are estimated from category and material.")
    if any(not p.item.get(f) for p in chosen for f in ("formality", "color", "pattern", "season")):
        reasons.append("Some matching details are missing; check the pieces together.")
    if day["build_around"]:
        reasons.append("Your chosen item is included.")
    if day["mood"] != "usual":
        reasons.append("Your mood nudges the choice a little dressier." if day["mood"] == "sharp"
                       else "Your mood nudges the choice a little more relaxed.")
    return reasons


def suggest(items: list[dict], context: dict, count: int = DEFAULT_COUNT) -> dict:
    """Return {outfits: [{places, score, reasons}], messages} without mutating inputs.

    Item ids are unique, as in GET /api/items/{id}. Ties use ids, never input
    order. Hard matching rules survive all fallbacks; inadequate weather or
    occasion coverage is explained instead of silently called a good fit.
    """
    day = validate_context(context, count)
    excluded = set(day["exclude"])
    available = [i for i in items if _available(i, excluded)
                 and any(i.get("category") in categories for categories in CATEGORIES.values())]
    if day["build_around"] and not any(i["id"] == day["build_around"] for i in available):
        return {"outfits": [], "messages": ["The item to build around is unavailable in this closet, excluded, or has no outfit place."]}
    missing = [place.replace("_", " ") for place in PLACES if place in REQUIRED
               and not any(i["category"] in CATEGORIES[place] for i in available)]
    if missing:
        return {"outfits": [], "messages": [f"To make an outfit, you need an active, clean item you do not dislike for: {', '.join(missing)}."]}
    pieces = sorted((_piece(i) for i in available), key=lambda p: p.id)
    candidates = _search(pieces, day)
    if not candidates:
        return {"outfits": [], "messages": ["No combination fits the layering, dressiness, colour and pattern rules with these choices. Try another build-around item or fewer exclusions."]}
    chosen = []
    for candidate in candidates:
        candidate_ids = {p.id for p in candidate[1] if p}
        if all(max(len(candidate_ids - {p.id for p in other[1] if p}),
                   len({p.id for p in other[1] if p} - candidate_ids)) >= MIN_DIFFERENT_PIECES
               for other in chosen):
            chosen.append(candidate)
            if len(chosen) == count:
                break
    messages = []
    if len(chosen) < count:
        messages.append("There are not enough different combinations; some choices change only one piece.")
        selected = {_key(c)[1] for c in chosen}
        chosen.extend(c for c in candidates if _key(c)[1] not in selected and len(chosen) < count)
    result = []
    for cost, parts in sorted(chosen, key=_key):
        places = {place: (p.id if p else None) for place, p in zip(PLACES, parts, strict=True)}
        places["accessories"] = [places["accessories"]] if places["accessories"] else []
        result.append({"places": places, "score": round(max(MIN_SCORE, min(MAX_SCORE, BASE_SCORE - cost))),
                       "reasons": _reasons(parts, day)})
    return {"outfits": result, "messages": messages}
