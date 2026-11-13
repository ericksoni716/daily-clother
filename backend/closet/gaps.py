"""Wardrobe gaps by rule, without a database, network or clock.

`find_gaps` returns the shopping shortlist. `analyze` also returns non-shopping
notes (including the small-closet answer). Inputs are item dictionaries and wear
rows with item_id and worn_on; neither is changed.
"""
from __future__ import annotations

import itertools
from collections import Counter
from dataclasses import dataclass
from statistics import median

from . import outfits, vocab

MIN_ITEMS = 6                 # Fewer usable garments cannot support a useful wardrobe judgment.
MAX_GAPS = 8                  # Keep the shopping shortlist manageable.
DAY_TEMPERATURES = (("cold", 2), ("cool", 12), ("mild", 20), ("hot", 28))  # Fixed representative Celsius days.
DESIRED_OUTFITS = 3           # Enough genuinely different choices for a kind of day.
MIN_DIFFERENT = outfits.MIN_PIECES_DIFFERENT  # Accessories alone do not provide variety.
ORPHAN_MAX_OUTFITS = 1        # At most this many compatible combinations makes an item an orphan.
WITNESS_LIMIT = 256           # Maximum combinations checked per compatibility probe; exhaustion is inconclusive.
MIN_WEAR_COUNT = 8            # Do not recommend a duplicate on the strength of a few wears.
WEAR_RATIO = 3                # An item must be worn this many times its neighbours' median.
MIN_PEERS = 2                 # Compare against at least this many other similar garments.
ZERO = 0                     # Empty counts and the lower score bound.
ONE = 1                      # A singleton, one additional piece, and the denominator floor for wear ratios.
SCORE_MAX = 100               # Upper bound of the help score, not a probability.
DAY_SCORE = 65               # A missing suitable piece or a warning is more urgent than a basic.
EMPTY_DAY_SCORE = 85         # No outfit at all is more urgent than warnings or limited choice.
VARIETY_SCORE = 40            # Limited choice is less urgent than unsuitable clothes.
THIN_SCORE = 50               # A single point of dependence merits a spare, not a whole wardrobe.
ORPHAN_SCORE = 55             # One purchase can bring an otherwise difficult item into use.
WEAR_SCORE = 75               # Repeated actual use outweighs a hypothetical day on the fixed grid.
BASIC_SCORE = 25              # A generic basic is only a low-priority suggestion.
DAY_BONUS_MAX = 20            # Cap the benefit of covering more of the fixed days.
METHOD_BONUS = 4              # Independent reasons modestly strengthen a recommendation.
MAX_NAMES = 3                # Keep the owner-facing sentences short.
MAX_COLOURS = 3              # Offer a few compatible neutral colours rather than a palette dump.
CORE_PLACES = ("base", "bottom", "shoes")
PLAIN_COLOURS = {
    "base": ("white", "light_blue", "cream", "navy"),
    "mid": ("navy", "grey", "cream"),
    "outer": ("navy", "black", "tan"),
    "bottom": ("navy", "grey", "tan", "olive"),
    "shoes": ("black", "brown"),
}
PLACE_NAMES = {"base": "plain top", "mid": "plain sweater", "outer": "outer layer",
               "bottom": "plain trousers", "shoes": "pair of shoes"}
CATEGORY_NAMES = {"tee": "plain T-shirt", "shirt": "plain shirt", "polo": "plain polo",
                  "sweater": "plain sweater", "hoodie": "hoodie", "coat": "coat", "jacket": "jacket",
                  "trousers": "pair of plain trousers", "jeans": "pair of jeans", "shorts": "pair of shorts",
                  "dress_shoes": "pair of smart shoes", "sneakers": "pair of sneakers",
                  "boots": "pair of boots", "sandals": "pair of sandals"}
OCCASION_NAMES = {"athletic": "sport", "casual": "casual days", "smart_casual": "smart casual days",
                  "business": "work", "formal": "formal occasions"}

# Each basic is a deliberately small choice from menswear-reference.md, not a claim that everyone needs every type.
BASIC_TEE = ("tee", "casual", "midweight")           # §4.1: a plain jersey tee, alone or under an open shirt.
BASIC_SHIRT = ("shirt", "business", "midweight")     # §4.2: a plain dress shirt for smarter clothes.
BASIC_TROUSERS = ("trousers", "business", "midweight")  # §4.7: plain dress trousers, not just jeans.
BASIC_KNIT = ("sweater", "smart_casual", "midweight")  # §3.2 and §4.4: a fine/medium knit that can layer.
BASIC_COAT = ("coat", "smart_casual", "super_heavy")  # §4.5 and §9.3: an overcoat for winter.
BASIC_SHOES = ("dress_shoes", "business", "midweight")  # §4.8: plain leather oxfords/derbies for smart days.
BASICS = (BASIC_TEE, BASIC_SHIRT, BASIC_TROUSERS, BASIC_KNIT, BASIC_COAT, BASIC_SHOES)


@dataclass(frozen=True)
class Options:
    limit: int = MAX_GAPS

    def __post_init__(self):
        if isinstance(self.limit, bool) or not isinstance(self.limit, int) or not ONE <= self.limit <= MAX_GAPS:
            raise ValueError(f"Limit must be a whole number from {ONE} to {MAX_GAPS}.")


def _place(p: outfits.Piece) -> str:
    return next(place for place in outfits.PLACES if p.category in outfits.PLACE_CATEGORIES[place])


def _spec(category: str, formality: str, weight: str = "midweight", *, rain: bool = False) -> dict:
    # OUTER_REACH lets this one level span every occasion; do not sell four versions of the same coat.
    if category in outfits.PLACE_CATEGORIES["outer"]:
        formality = "smart_casual"
    spec = {"category": category, "formality": formality, "season": "all", "pattern": "solid"}
    if category not in outfits.PLACE_CATEGORIES["shoes"]:
        spec["weight_class"] = weight
    if rain:
        spec["material"] = "waterproof"
    elif category in outfits.PLACE_CATEGORIES["shoes"]:
        spec["material"] = "leather"
    return spec


def _for_day(place: str, ctx: outfits.Context, *, rain: bool = False, warm: bool = False) -> dict:
    level = ("business" if ctx.occasion in ("business", "formal") else "casual"
             if ctx.occasion in ("athletic", "casual") else ctx.occasion)
    category = {"base": "shirt" if level in ("business", "smart_casual") else "tee",
                "mid": "sweater", "outer": "coat", "bottom": "trousers",
                "shoes": "dress_shoes" if level in ("business", "smart_casual") else "sneakers"}[place]
    weight = "super_heavy" if warm else "lightweight" if ctx.low_c >= outfits.HOT_C else "midweight"
    return _spec(category, level, weight, rain=rain)


def _candidate(spec: dict) -> outfits.Piece:
    return outfits._piece({**spec, "id": "__gap_candidate__", "color": "navy"})


def _fits(p: outfits.Piece, place: str, ctx: outfits.Context) -> bool:
    return (p.category in outfits.PLACE_CATEGORIES[place]
            and not (place in ("mid", "outer") and ctx.low_c >= outfits.HOT_C)
            and outfits._piece_problem(p, place, ctx, ctx.low_c) is None)


def _compatible(parts: dict[str, outfits.Piece]) -> bool:
    values = list(parts.values())
    return (len({p.id for p in values}) == len(values)
            and outfits._layers_ok(parts["base"], parts.get("mid"), parts.get("outer"))
            and not outfits._outfit_problems(values, [p for pl, p in parts.items() if pl != "outer"],
                                             parts.get("outer")))


def _replacement_works(p: outfits.Piece, place: str, parts: dict, ctx: outfits.Context) -> bool:
    replaced = {**parts, place: p}
    warmth = sum(outfits._warmth(piece, pl) for pl, piece in replaced.items())
    return (_fits(p, place, ctx) and _compatible(replaced)
            and warmth <= outfits._warmth_target(ctx.low_c) + outfits.WARMTH_TOLERANCE + outfits.WARMTH_NOTE_GAP)


def _day_record(band: str, ctx: outfits.Context, problems: list[str]) -> dict:
    return {"temperature": band, "temperature_c": ctx.low_c, "rain": ctx.rain,
            "occasion": ctx.occasion, "problems": sorted(set(problems))}


class _Collector:
    def __init__(self, pool: list[outfits.Piece]):
        self.pool = pool
        self.by_id = {p.id: p for p in pool}
        self.entries: dict[tuple, dict] = {}

    def add(self, spec: dict, method: str, score: int, why: str, ids=(), day=None, wear_counts=None):
        key = tuple(sorted(spec.items()))
        entry = self.entries.setdefault(key, {
            "look_for": spec, "methods": {}, "method_scores": {}, "base_score": ZERO, "days": {},
            "ids": set(), "wear_counts": {},
        })
        if score > entry["method_scores"].get(method, ZERO):
            entry["methods"][method] = why
            entry["method_scores"][method] = score
        entry["base_score"] = max(entry["base_score"], score)
        entry["ids"].update(i for i in ids if i in self.by_id)
        if day:
            day_key = (day["temperature"], day["rain"], day["occasion"])
            prior = entry["days"].setdefault(day_key, {**day, "problems": []})
            prior["problems"] = sorted(set(prior["problems"]) | set(day["problems"]))
        entry["wear_counts"].update(wear_counts or {})

    def finish(self, limit: int) -> list[dict]:
        result = []
        colours = Counter(p.color for p in self.pool)
        for key, entry in sorted(self.entries.items()):
            spec = entry["look_for"]
            candidate = _candidate(spec)
            place = _place(candidate)
            partners = [p for p in self.pool if _place(p) != place
                        and not outfits._outfit_problems(
                            [candidate, p], [p] if place == "outer" else [candidate] if _place(p) == "outer"
                            else [candidate, p], candidate if place == "outer" else p if _place(p) == "outer" else None)]
            # Pair compatibility is evidence for colours/formality, not a claim of complete outfits.
            entry["ids"].update(p.id for p in partners)
            evidence = [self.by_id[i] for i in sorted(entry["ids"])] or self.pool[:MAX_NAMES]
            names = ", ".join(p.label for p in partners[:MAX_NAMES] or evidence[:MAX_NAMES])
            why = list(entry["methods"].values())
            why.append(f"Could pair with {names}." if partners else f"Consider it alongside your {names}; other gaps may remain.")
            article = "Another" if set(entry["methods"]) <= {"thin", "wear"} else "A"
            name = f"{article} {CATEGORY_NAMES[spec['category']]} for {OCCASION_NAMES[spec['formality']]}"
            if spec.get("material") == "waterproof":
                weight_words = "light" if spec["weight_class"] in ("lightweight", "midweight") else "heavier"
                name = f"A {weight_words} rain-proof outer layer"
            elif spec.get("weight_class") == "super_heavy" and place == "outer":
                name = f"{article} warm winter coat"
            result.append({
                "id": "|".join(f"{k}={v}" for k, v in key),
                "name": name, "look_for": {**spec, "colors": sorted(
                    PLAIN_COLOURS[place], key=lambda c: (-colours[c], c))[:MAX_COLOURS]},
                "why": why, "methods": sorted(entry["methods"]),
                "score": min(SCORE_MAX, entry["base_score"] + min(DAY_BONUS_MAX, len(entry["days"]))
                             + METHOD_BONUS * (len(entry["methods"]) - ONE)),
                "evidence": {"days": [entry["days"][k] for k in sorted(entry["days"])],
                             "items": [{"id": p.id, "name": p.label} for p in evidence],
                             "works_with": [p.id for p in partners],
                             "wear_counts": dict(sorted(entry["wear_counts"].items()))},
            })
        return sorted(result, key=lambda g: (-g["score"], g["id"]))[:limit]


def _empty_day_repair(eligible: dict, ctx: outfits.Context, pool: list[outfits.Piece]):
    """A bounded witness for days where even the relaxed engine cannot layer."""
    slots = list(CORE_PLACES)
    if ctx.low_c <= outfits.COLD_C and any(p.category in outfits.PLACE_CATEGORIES["outer"] for p in pool):
        slots.append("outer")
    for place in slots:
        spec = _for_day(place, ctx, warm=place == "outer")
        candidate = _candidate(spec)
        if not _fits(candidate, place, ctx):
            continue
        choices = [[candidate] if pl == place else eligible[pl] for pl in slots]
        for combo in itertools.islice(itertools.product(*choices), WITNESS_LIMIT):
            parts = dict(zip(slots, combo, strict=True))
            if _compatible(parts):
                return spec, [p.id for p in combo]
    return None


def _day_gaps(items: list[dict], pool: list[outfits.Piece], found: _Collector) -> int:
    checked = ZERO
    all_pieces = {p.id: p for item in items if (p := outfits._piece(item)) is not None}
    for band, temperature in DAY_TEMPERATURES:
        for rain, occasion in itertools.product((False, True), vocab.FORMALITY):
            ctx = outfits.Context(temperature, temperature, rain, occasion)
            answer = outfits.suggest(items, ctx, DESIRED_OUTFITS)
            checked += ONE
            choices = answer["outfits"]
            eligible = {pl: [p for p in pool if _fits(p, pl, ctx)] for pl in outfits.PLACES}
            diverse = []
            for choice in choices:
                if all(sum(choice["pieces"][pl] != other["pieces"][pl] for pl in outfits.PLACES)
                       >= MIN_DIFFERENT for other in diverse):
                    diverse.append(choice)
            ids = {i for choice in choices for pl in outfits.PLACES if (i := choice["pieces"][pl])}
            day = _day_record(band, ctx, answer["missing"])
            for pl in CORE_PLACES:
                suitable = eligible[pl]
                if not suitable:
                    problem = f"No suitable {PLACE_NAMES[pl]} for {band} {occasion.replace('_', ' ')} days."
                    found.add(_for_day(pl, ctx), "days", DAY_SCORE if choices else EMPTY_DAY_SCORE,
                              problem, ids, _day_record(band, ctx, [*answer["missing"], problem]))
                elif len(diverse) < DESIRED_OUTFITS and len(suitable) < DESIRED_OUTFITS:
                    found.add(_for_day(pl, ctx), "days", VARIETY_SCORE,
                              "Some days offer fewer than three outfits that differ in at least two pieces.",
                              ids, _day_record(band, ctx, ["Fewer than three different outfits."]))
                if (len(suitable) == ONE and choices
                        and all(c["pieces"][pl] == suitable[ZERO].id for c in choices)):
                    p = suitable[ZERO]
                    found.add(_spec(p.category, vocab.FORMALITY[p.formality], outfits.WEIGHT_CLASSES[p.weight]),
                              "thin", THIN_SCORE,
                              f"Every suggested outfit on some days relies on your {p.label}; there is no other suitable {PLACE_NAMES[pl]}.",
                              [p.id], _day_record(band, ctx, [f"Only {p.label} fills {pl}."]))
            if not choices:
                if all(eligible[pl] for pl in CORE_PLACES):
                    repair = _empty_day_repair(eligible, ctx, pool)
                    if repair:
                        spec, companions = repair
                        found.add(spec, "days", EMPTY_DAY_SCORE,
                                  "No outfit fits together on some days; this piece makes a compatible combination.",
                                  companions, day)
                continue
            choice = choices[ZERO]
            parts = {pl: found.by_id[i] for pl in outfits.PLACES if (i := choice["pieces"][pl])}
            warnings = choice["warnings"]
            day = _day_record(band, ctx, warnings)
            outer = parts.get("outer")
            owned_rain_layer = any(outfits._rain_friendly(p) and not outfits._rain_unfriendly(p)
                                   and _replacement_works(p, "outer", parts, ctx)
                                   for p in eligible["outer"])
            if (rain and temperature < outfits.HOT_C
                    and not (outer and outfits._rain_friendly(outer) and not outfits._rain_unfriendly(outer))
                    and not owned_rain_layer):
                for weight in outfits.WEIGHT_CLASSES:
                    spec = _spec("coat", "smart_casual", weight, rain=True)
                    candidate = _candidate(spec)
                    if outfits._layers_ok(parts["base"], parts.get("mid"), candidate):
                        why = (f"Your {outer.label} may not like rain; look for a rain-friendly alternative."
                               if outer and outfits._rain_unfriendly(outer) else
                               "On some rainy days the engine can only say to take an umbrella; the chosen layers do not keep rain off.")
                        found.add(spec, "days", DAY_SCORE,
                                  why, ids, day)
                        break
            shoes = parts["shoes"]
            owned_shoes = any(not outfits._rain_unfriendly(q) and _replacement_works(q, "shoes", parts, ctx)
                              for q in eligible["shoes"])
            if rain and outfits._rain_unfriendly(shoes) and not owned_shoes:
                found.add(_for_day("shoes", ctx), "days", DAY_SCORE,
                          f"Your {shoes.label} may not like rain; look for a rain-friendly alternative.", [shoes.id], day)
            warmth = sum(outfits._warmth(p, pl) for pl, p in parts.items())
            warmth += sum(outfits.ACCESSORY_WARMTH.get(all_pieces[i].category, ZERO)
                          for i in choice["pieces"]["accessories"])
            target = outfits._warmth_target(temperature)
            if warmth < target - outfits.WARMTH_TOLERANCE - outfits.WARMTH_NOTE_GAP:
                upgrades = (("outer", _for_day("outer", ctx, warm=True)),
                            ("mid", _spec("sweater", _for_day("mid", ctx)["formality"], "super_heavy")))
                already_owned = any(
                    outfits._warmth(p, pl) > (outfits._warmth(parts[pl], pl) if pl in parts else ZERO)
                    and _compatible({**parts, pl: p})
                    for pl, _ in upgrades for p in eligible[pl])
                for pl, spec in (() if already_owned else upgrades):
                    candidate = _candidate(spec)
                    current_warmth = outfits._warmth(parts[pl], pl) if pl in parts else ZERO
                    if (outfits._warmth(candidate, pl) > current_warmth and _fits(candidate, pl, ctx)
                            and _compatible({**parts, pl: candidate})):
                        found.add(spec, "days", DAY_SCORE,
                                  f"The suggested clothes are too light for some cold days; a warmer suitable {PLACE_NAMES[pl]} would help.",
                                  ids, day)
                        break
            elif warmth > target + outfits.WARMTH_TOLERANCE + outfits.WARMTH_NOTE_GAP:
                spec = _spec(parts["base"].category, vocab.FORMALITY[parts["base"].formality], "lightweight")
                owned_lighter = any(p.weight < parts["base"].weight and _replacement_works(p, "base", parts, ctx)
                                    for p in eligible["base"])
                if _candidate(spec).weight < parts["base"].weight and not owned_lighter:
                    found.add(spec, "days", DAY_SCORE, "Some suggested outfits are too warm; a lighter top would help.", ids, day)
            # Diagnose clashes by trying one plain neutral replacement, not by parsing warning prose.
            if outfits._outfit_problems(list(parts.values()), [p for pl, p in parts.items() if pl != "outer"], outer):
                for pl in CORE_PLACES:
                    spec = _for_day(pl, ctx)
                    if _compatible({**parts, pl: _candidate(spec)}):
                        found.add(spec, "days", DAY_SCORE,
                                  "Some outfits mix competing colours, patterns or levels of dress; a plain matching piece would help.",
                                  ids, day)
            if (outer and temperature <= outfits.COLD_C and len(eligible["outer"]) == ONE
                    and all(c["pieces"]["outer"] == outer.id for c in choices)):
                found.add(_spec(outer.category, vocab.FORMALITY[outer.formality], outfits.WEIGHT_CLASSES[outer.weight]),
                          "thin", THIN_SCORE, f"Your {outer.label} is the only suitable outer layer on some days.",
                          [outer.id], _day_record(band, ctx, [f"Only {outer.label} fills the outer layer."]))
    return checked


def _witnesses(anchor: outfits.Piece, pool: list[outfits.Piece], extra: outfits.Piece | None = None):
    """Find up to two compatible outfits, independent of top-ranked popularity.

    If the bound is reached, absence is unknown, never evidence for buying.
    Warmth is not a hard rule here: this measures whether pieces can combine.
    """
    place = _place(anchor)
    temperature = dict(DAY_TEMPERATURES)["cool" if place in ("mid", "outer") or anchor.season == "cool" else "mild"]
    ctx = outfits.Context(temperature, temperature, occasion=vocab.FORMALITY[anchor.formality])
    fixed = {place: anchor}
    if extra:
        fixed[_place(extra)] = extra
    slots = list(dict.fromkeys((*CORE_PLACES, *fixed)))
    choices = []
    for pl in slots:
        choices.append([fixed[pl]] if pl in fixed else [
            p for p in pool if _fits(p, pl, ctx) and p.id != anchor.id
            and not outfits._outfit_problems([anchor, p], [p] if place == "outer" else [anchor, p],
                                             anchor if place == "outer" else None)])
    witnesses = []
    for index, combo in enumerate(itertools.product(*choices)):
        if index >= WITNESS_LIMIT:
            return witnesses, False
        parts = dict(zip(slots, combo, strict=True))
        if all(_fits(p, pl, ctx) for pl, p in parts.items()) and _compatible(parts):
            witnesses.append(parts)
            if len(witnesses) > ORPHAN_MAX_OUTFITS:
                return witnesses, True
    return witnesses, True


def _orphan_gaps(pool: list[outfits.Piece], found: _Collector):
    for p in pool:
        witnesses, complete = _witnesses(p, pool)
        if not complete or len(witnesses) > ORPHAN_MAX_OUTFITS:
            continue
        for pl in CORE_PLACES:
            if pl == _place(p):
                continue
            ctx = outfits.Context(dict(DAY_TEMPERATURES)["mild"], dict(DAY_TEMPERATURES)["mild"],
                                  occasion=vocab.FORMALITY[p.formality])
            spec = _for_day(pl, ctx)
            repaired, _ = _witnesses(p, pool, _candidate(spec))
            if repaired:
                ids = {piece.id for witness in repaired for piece in witness.values()}
                found.add(spec, "orphan", ORPHAN_SCORE,
                          f"Your {p.label} fits almost no complete outfit; a {CATEGORY_NAMES[spec['category']]} makes a compatible combination.",
                          ids)
                break


def _wear_gaps(pool: list[outfits.Piece], wears: list[dict], found: _Collector) -> list[dict]:
    unique = {(w["item_id"], w["worn_on"]) for w in wears if w.get("item_id") in found.by_id and w.get("worn_on")}
    counts = Counter(item_id for item_id, _ in unique)
    notes = []
    if unique:
        never = [p for p in pool if not counts[p.id]]
        if never:
            notes.append({"kind": "never_worn", "message": "These items have no recorded wears. Try what you own before buying more.",
                          "item_ids": [p.id for p in never]})
    else:
        notes.append({"kind": "wear_history", "message": "No wears are recorded yet; wear-based suggestions need some history.",
                      "item_ids": []})
    for p in pool:
        peers = [q for q in pool if q.id != p.id and _place(q) == _place(p)
                 and abs(q.formality - p.formality) <= outfits.FORMALITY_SPREAD]
        if len(peers) < MIN_PEERS or counts[p.id] < MIN_WEAR_COUNT:
            continue
        typical = median(counts[q.id] for q in peers)
        if counts[p.id] < WEAR_RATIO * max(ONE, typical):
            continue
        found.add(_spec(p.category, vocab.FORMALITY[p.formality], outfits.WEIGHT_CLASSES[p.weight]),
                  "wear", WEAR_SCORE,
                  f"Your {p.label} has {counts[p.id]} recorded wears, far more than similar pieces. A second could share the work.",
                  [p.id, *(q.id for q in peers)], wear_counts={q.id: counts[q.id] for q in [p, *peers]})
    return notes


def analyze(items: list[dict], wears: list[dict], options: Options | None = None) -> dict:
    """A pure report: ranked gaps, non-shopping notes and the number of grid days checked."""
    options = options or Options()
    usable, pool = [], []
    for item in sorted(items, key=lambda i: str(i.get("id", ""))):
        if item.get("status") == "archived" or item.get("rating") == "dislike":
            continue
        p = outfits._piece(item)
        if p is None:
            continue
        usable.append({**item, "laundry": "clean", "location": None if item.get("location") == "laundry" else item.get("location")})
        if p.category not in outfits.ACCESSORY_CATEGORIES:
            pool.append(p)
    if len(pool) < MIN_ITEMS:
        return {"gaps": [], "notes": [{"kind": "small_closet",
                "message": f"There are too few clothes to judge yet. Add at least {MIN_ITEMS} usable garments first.",
                "item_ids": []}], "item_count": len(pool), "days_checked": ZERO}
    found = _Collector(pool)
    days_checked = _day_gaps(usable, pool, found)
    _orphan_gaps(pool, found)
    notes = _wear_gaps(pool, wears, found)
    for category, formality, weight in BASICS:
        if not any(p.category == category and outfits._neutral(p) and p.pattern == "solid"
                   and abs(p.formality - vocab.FORMALITY.index(formality)) <= outfits.OCCASION_REACH
                   and (category != "coat" or p.weight >= outfits.WEIGHT_CLASSES.index("heavyweight"))
                   for p in pool):
            found.add(_spec(category, formality, weight), "basic", BASIC_SCORE,
                      f"The short basics list includes a {CATEGORY_NAMES[category]}; none of your usable pieces fills it.",
                      [p.id for p in pool if p.category == category])
    return {"gaps": found.finish(options.limit), "notes": notes, "item_count": len(pool), "days_checked": days_checked}


def find_gaps(items: list[dict], wears: list[dict], options: Options | None = None) -> list[dict]:
    """Return at most MAX_GAPS ranked purchases; tiny closets return no purchases."""
    return analyze(items, wears, options)["gaps"]
