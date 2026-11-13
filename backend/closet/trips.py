"""Pure, deterministic packing, using the outfit engine's rules and scores.

Try difficult days first as well as calendar order, then compare complete
plans: coverage, outer/shoe limits, piece count, engine score, stable ids.
This is a bounded search, not a proof of the global minimum.
"""
from __future__ import annotations

from collections import Counter

from . import outfits as engine

TOP_WEARS = 2
TEE_WEARS = 1
KNIT_WEARS = 4
BOTTOM_WEARS = 5
WASH_MULTIPLIER = 30
MAX_OUTERS = 1
MAX_SHOES = 2
CHOICES_PER_SIZE = 12
SPARE_BASICS = 1
SLEEPWEAR_COUNT = 1
TOILETRIES_COUNT = 1
GROUPS = ("tops", "layers", "bottoms", "shoes", "outer", "accessories")


def ids(outfit: dict) -> set[str]:
    p = outfit["pieces"]
    return {p[k] for k in engine.PLACES if p.get(k)} | set(p.get("accessories", []))


def group(category: str) -> str:
    if category in ("sweater", "hoodie"):
        return "layers"
    for slot, name in (("base", "tops"), ("bottom", "bottoms"), ("shoes", "shoes"), ("outer", "outer")):
        if category in engine.PLACE_CATEGORIES[slot]:
            return name
    return "accessories"


def capacity(row: dict, wash: bool) -> int:
    cat = row.get("category")
    limit = (TEE_WEARS if cat == "tee" else TOP_WEARS if cat in ("shirt", "polo") else KNIT_WEARS
             if cat in ("sweater", "hoodie") else BOTTOM_WEARS if cat in engine.PLACE_CATEGORIES["bottom"] else 30)
    if wash:
        return limit * WASH_MULTIPLIER
    return max(0, limit - (row.get("wears_since_wash") or 0)) if limit < 30 else limit


def _choices(pool: list[engine.Piece], ctx: engine.Context, packed: set[str]) -> list[dict]:
    """Use exactly the engine's strict search, layering, accessories and explanations.

    An additional search in already-packed categories keeps reusable pieces in
    reach even when they fall outside the engine's six-candidate shortlist.
    """
    t = engine._design_temp(ctx)
    reuse_categories = {p.category for p in pool if p.id in packed}
    reuse = [p for p in pool if p.id in packed or p.category not in reuse_categories]
    found = engine._search(pool, ctx, t, None, True)
    if reuse != pool:
        found += engine._search(reuse, ctx, t, None, True)
    found.sort(key=lambda o: (len({x.piece.id for x in o.core()} - packed), -o.raw, o.ids()))
    outers = [p for p in pool if p.category in engine.PLACE_CATEGORIES["outer"]]
    sizes, seen, answer = Counter(), set(), []
    for o in found:
        if o.ids() in seen:
            continue
        seen.add(o.ids())
        if ctx.rain and (o.outer is None or not engine._rain_friendly(o.outer.piece)
                         or engine._rain_unfriendly(o.outer.piece) or engine._rain_unfriendly(o.shoes.piece)):
            continue
        engine._add_accessories(o, pool, ctx, t, None)
        warmth = sum(x.warmth for x in o.core() + o.accessories)
        if abs(warmth - engine._warmth_target(t)) > engine.WARMTH_TOLERANCE + engine.WARMTH_NOTE_GAP:
            continue
        pieces = {pl: getattr(o, pl).piece.id if getattr(o, pl) else None for pl in engine.PLACES}
        pieces["accessories"] = [x.piece.id for x in o.accessories]
        size = len({x.piece.id for x in o.core() + o.accessories} - packed)
        if sizes[size] >= CHOICES_PER_SIZE:
            continue
        sizes[size] += 1
        score, reasons, warnings = engine._explain(o, ctx, t, None, outers)
        answer.append({"pieces": pieces, "score": score, "reasons": reasons, "warnings": warnings})
    return answer


def plan(rows: list[dict], days: list[dict], occasion: str = "casual", overrides: list[dict] | None = None,
         can_wash: bool = False, leave_out: list[str] | None = None, pins: list[str] | None = None) -> dict:
    """Pack for at most 30 weather days; unknown weather is explicitly uncovered."""
    if not 1 <= len(days) <= 30:
        raise ValueError("A trip needs 1 to 30 days.")
    if occasion not in engine.FORMALITY:
        raise ValueError("Choose an occasion for the trip.")
    by_day = {d["date"]: d["occasion"] for d in overrides or []}
    pins = sorted(set(pins or []))
    leave = set(leave_out or [])
    usable = {r["id"]: r for r in sorted(rows, key=lambda r: r["id"])
              if engine._piece(r) and not engine._unavailable(r, engine.Context(0, 0, leave_out=tuple(leave)))}
    for pin in pins:
        if pin not in usable:
            raise ValueError("A piece you want to take is unavailable, in the laundry, archived or left out.")
    pieces = {k: engine._piece(v) for k, v in usable.items()}
    limits = {k: capacity(v, can_wash) for k, v in usable.items()}
    contexts = {}
    for index, day in enumerate(days):
        if day.get("low_c") is not None and day.get("high_c") is not None and day.get("rain") is not None:
            contexts[index] = engine.parse_request({
                **{k: day[k] for k in ("low_c", "high_c", "rain")},
                "occasion": by_day.get(day["date"], occasion),
            })[0]
    cache = {}

    def run(order):
        packed, uses, outfits = set(pins), Counter(), {}
        for i in order:
            if i not in contexts:
                continue
            ctx = contexts[i]
            available = tuple(k for k in usable if uses[k] < limits[k])
            key = (available, tuple(sorted(packed)), ctx.low_c, ctx.high_c, ctx.rain, ctx.occasion)
            if key not in cache:
                cache[key] = _choices([pieces[k] for k in available], ctx, packed)
            choices = cache[key]
            if not choices:
                continue

            def rank(o, packed=packed):
                taken = packed | ids(o)
                outer = sum(group(usable[k]["category"]) == "outer" for k in taken)
                shoes = sum(group(usable[k]["category"]) == "shoes" for k in taken)
                return (max(0, outer - MAX_OUTERS) + max(0, shoes - MAX_SHOES),
                        len(taken), -o["score"], tuple(sorted(ids(o))))

            chosen = min(choices, key=rank)
            outfits[i] = chosen
            packed |= ids(chosen)
            uses.update(ids(chosen))
        excess = (max(0, sum(group(usable[k]["category"]) == "outer" for k in packed) - MAX_OUTERS)
                  + max(0, sum(group(usable[k]["category"]) == "shoes" for k in packed) - MAX_SHOES))
        rank = (-len(outfits), excess, len(packed), -sum(o["score"] for o in outfits.values()), tuple(sorted(packed)))
        return rank, packed, uses, outfits

    calendar = list(range(len(days)))
    difficult = sorted(calendar, key=lambda i: (
        -engine.FORMALITY.index(by_day.get(days[i]["date"], occasion)),
        not bool(days[i].get("rain")), days[i].get("low_c") or 0, i))
    results = [run(order) for order in dict.fromkeys((tuple(calendar), tuple(difficult), tuple(reversed(difficult))))]
    _, packed, uses, chosen = min(results, key=lambda r: r[0])
    packing = {g: [] for g in GROUPS}
    for k in sorted(packed, key=lambda k: (usable[k].get("name") or "", k)):
        r = usable[k]
        packing[group(r["category"])].append({"id": k, "name": r.get("name") or engine._label(r),
                                             "days_worn": uses[k], "pinned": k in pins})
    daily, uncovered = [], []
    for i, d in enumerate(days):
        missing = []
        if i not in chosen:
            if i not in contexts:
                missing = ["Weather is unknown, so Closet cannot choose an outfit for this day."]
            else:
                base = engine.suggest(list(usable.values()), contexts[i], 1)
                missing = base["missing"] or [
                    "No acceptable outfit within the re-wear limits for this weather and occasion."
                    + (" Nothing rain-proof works with the available pieces." if d["rain"] else "")
                    + (" Try “I can wash there” or change the pieces left out." if not can_wash else "")]
                if base["outfits"]:
                    missing += base["outfits"][0]["warnings"]
            uncovered.append({"date": d["date"], "reasons": missing})
        daily.append({"date": d["date"], "occasion": by_day.get(d["date"], occasion),
                      "weather": d, "outfit": chosen.get(i), "missing": missing})
    basics = [
        {"id": "underwear", "name": "Underwear", "count": len(days) + SPARE_BASICS},
        {"id": "socks", "name": "Pairs of socks", "count": len(days) + SPARE_BASICS},
        {"id": "sleepwear", "name": "Sleepwear", "count": SLEEPWEAR_COUNT},
        {"id": "toiletries", "name": "Toiletries bag", "count": TOILETRIES_COUNT},
    ]
    return {"packing": packing, "basics": basics, "days": daily, "uncovered": uncovered,
            "piece_count": len(packed), "notes": [
                "Re-wear counts include wears since the last wash. Mark clothes clean before planning if you will wash before leaving.",
                *([ "Wash between wears as needed; the plan assumes clean, dry clothes will be ready." ] if can_wash else []),
                *([ "Extra outer layers or shoes are needed to cover these days." ] if min(results, key=lambda r: r[0])[0][1] else []),
                *([ "A pinned piece with 0 days worn is packed at your request, but does not fit these days." ]
                  if any(uses[k] == 0 for k in pins) else []),
            ]}
