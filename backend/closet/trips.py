"""What to pack for a trip, chosen by rule.

Pure functions: no database, no network, no clock. `plan(items, days, options)`
takes the closet's items (as the outfit engine takes them), the trip's days
(the weather for each, as `tripweather.lookup` gives it) and the owner's
choices (the trip's occasion and the days that differ, "I can wash there",
pieces swapped out and pieces pinned in), and returns what to pack, one outfit
for each day made only from packed pieces, the basics to bring by count, and
the days that could not be covered and why. The same inputs always give the
same plan.

How it chooses: the days are dressed hardest first (coldest, then rainy, then
the dressiest). For each day the outfit engine's own search is run over the
packed pieces alone, then over the packed pieces plus one place left open
(new tops, or new shoes...), then over the whole closet, and the outfit that
adds the fewest new pieces is taken, then the one the engine scores highest.
An outfit of packed pieces is only taken when it is within SCORE_SLACK points
of the best the closet can do that day and has no warning the best one does
not have (cold, too warm, rain coming in, shoes that soak). Each piece can be
worn a set number of days (REWEAR_DAYS, more with WASH_FACTOR), and at most
MAX_OUTER outer layers and MAX_SHOES pairs of shoes are packed unless the days
cannot be covered otherwise.

The engine's rules are read from `outfits.py` (its pieces, its search, its
accessories and its explanations); nothing there is changed.
"""
from __future__ import annotations

import dataclasses
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from . import outfits

# ------------------------------------------------------------------ re-wearing
# How many days of a trip one piece can be worn, by category. Categories not listed (outer layers, shoes,
# accessories) can be worn every day.
REWEAR_DAYS = {"tee": 1, "polo": 2, "shirt": 2, "sweater": 4, "hoodie": 3, "jeans": 5, "trousers": 4, "shorts": 3}
WASH_FACTOR = 2              # "I can wash there" multiplies those days by this
MAX_OUTER = 1                # outer layers packed (jackets and coats) unless the days cannot be covered otherwise
MAX_SHOES = 2                # pairs of shoes packed unless the days cannot be covered otherwise
SCORE_SLACK = 10             # an outfit of packed pieces is taken when it scores within this of the day's best

# ------------------------------------------------------------------ basics (not items in the closet)
SPARE = 1                    # underwear and socks: one a day plus this many
WASH_CYCLE_DAYS = 4          # with washing, underwear and socks for at most this many days (plus the spare)
SLEEPWEAR_NIGHTS = 7         # one set of sleepwear for every this many nights (one in all with washing)
GLOVES_MAX_C = 2             # gloves when a day is dressed for at or below this (°C)

# ------------------------------------------------------------------ what to pack, grouped
GROUPS = (
    ("tops", ("tee", "shirt", "polo")),
    ("layers", ("sweater", "hoodie")),
    ("bottoms", ("jeans", "trousers", "shorts")),
    ("shoes", ("sneakers", "boots", "dress_shoes", "sandals")),
    ("outer", ("jacket", "coat")),
    ("accessories", ("belt", "scarf", "hat", "bag")),
)
GROUP_OF = {c: g for g, cats in GROUPS for c in cats}
GROUP_ORDER = [g for g, _ in GROUPS]

OCCASIONS = outfits.FORMALITY


class PlanError(ValueError):
    """A request the planner cannot work with, in words the owner can read."""


@dataclass(frozen=True)
class Options:
    occasion: str = "casual"
    day_occasions: Mapping[str, str] = field(default_factory=dict)
    can_wash: bool = False
    leave_out: tuple[str, ...] = ()
    pin: tuple[str, ...] = ()


def parse_options(data: Mapping, dates: Iterable[str]) -> Options:
    """Check the owner's choices for a trip. Raises PlanError with a sentence."""
    dates = set(dates)
    occasion = data.get("occasion") or "casual"
    if occasion not in OCCASIONS:
        raise PlanError(f"'{occasion}' is not an occasion. Choose one of: {', '.join(OCCASIONS)}.")
    days = data.get("day_occasions") or {}
    if not isinstance(days, Mapping):
        raise PlanError("Days that differ must be an object of date to occasion, for example {\"2026-12-04\": \"business\"}.")
    for day, occ in days.items():
        if day not in dates:
            raise PlanError(f"{day} is not a day of this trip.")
        if occ not in OCCASIONS:
            raise PlanError(f"'{occ}' is not an occasion. Choose one of: {', '.join(OCCASIONS)}.")
    wash = data.get("can_wash", False)
    if not isinstance(wash, bool):
        raise PlanError("\"I can wash there\" must be true or false.")
    lists = {}
    for key, words in (("leave_out", "Pieces to leave out"), ("pin", "Pieces to take")):
        v = data.get(key) or []
        if not isinstance(v, list) or not all(isinstance(x, str) and x for x in v):
            raise PlanError(f"{words} must be a list of item ids.")
        lists[key] = tuple(sorted(set(v)))
    both = set(lists["leave_out"]) & set(lists["pin"])
    if both:
        raise PlanError("A piece cannot be both left out and taken.")
    return Options(occasion, {k: days[k] for k in sorted(days) if days[k] != occasion}, wash, lists["leave_out"], lists["pin"])


# ====================================================================== helpers
def _cap(p: outfits.Piece, opts: Options, n_days: int) -> int:
    days = REWEAR_DAYS.get(p.category)
    if days is None:
        return n_days
    return days * (WASH_FACTOR if opts.can_wash else 1)


def _core(o: outfits._Outfit) -> list[outfits.Piece]:
    return [x.piece for x in o.core()]


def _flags(o: outfits._Outfit, ctx: outfits.Context, t: float) -> frozenset[str]:
    """What is wrong with an outfit that a better closet would fix: cold, too warm, rain coming in, shoes that soak."""
    out = set()
    warmth = sum(x.warmth for x in o.core())
    target = outfits._warmth_target(t)
    if warmth < target - outfits.WARMTH_TOLERANCE - outfits.WARMTH_NOTE_GAP:
        out.add("cold")
    elif warmth > target + outfits.WARMTH_TOLERANCE + outfits.WARMTH_NOTE_GAP:
        out.add("warm")
    if ctx.rain:
        if outfits._rain_unfriendly(o.shoes.piece):
            out.add("wet_shoes")
        if t < outfits.HOT_C and not (o.outer is not None and outfits._rain_friendly(o.outer.piece)):
            out.add("rain")
    return frozenset(out)


def _the(p: outfits.Piece, cap: bool = False) -> str:
    return outfits._the(p, cap)


@dataclass
class _Day:
    date: str
    weather: dict
    occasion: str
    ctx: outfits.Context | None = None
    t: float = 0.0
    outfit: outfits._Outfit | None = None
    problem: str | None = None
    warning: str | None = None


@dataclass
class _Reference:
    raw: float
    flags: frozenset[str]
    outer_needed: bool
    problem: str | None = None       # the day is covered, but not well: said in the plan


class _Planner:
    def __init__(self, items: list, days: list[_Day], opts: Options):
        self.opts = opts
        self.days = days
        self.notes: list[str] = []
        everything = []
        for item in sorted((i for i in items if isinstance(i, Mapping) and i.get("id")), key=lambda i: str(i["id"])):
            p = outfits._piece(dict(item))
            if p is not None:
                everything.append((p, dict(item)))
        self.everything = everything
        out = outfits.Context(0, 0, leave_out=opts.leave_out)
        pins = set(opts.pin)
        pool = []
        for p, it in everything:
            why = outfits._unavailable(it, out)
            if why is None or (why == "rated dislike" and p.id in pins):
                pool.append(p)
            elif p.id in pins:
                self.notes.append(f"{_the(p, True)} is {why}, so it is not packed.")
        self.pool = pool
        self.by_id = {p.id: p for p in pool}
        known = {p.id for p, _ in everything}
        for pid in opts.pin:
            if pid not in known:
                self.notes.append("A piece you asked to take is not in this closet any more.")
        self.n_days = len(days)
        self.caps = {p.id: _cap(p, opts, self.n_days) for p in pool}
        self.used: dict[str, int] = {}
        self.acc_used: dict[str, int] = {}
        self.packed: dict[str, outfits.Piece] = {pid: self.by_id[pid] for pid in opts.pin if pid in self.by_id}
        self.outers = [p for p in pool if p.category in outfits.PLACE_CATEGORIES["outer"]]
        self._refs: dict[tuple, _Reference | str] = {}

    # ------------------------------------------------------------ one day
    def reference(self, d: _Day) -> _Reference | str:
        """The best the whole closet can do on the day (ignoring what has been worn), or why there is nothing."""
        key = (d.ctx.low_c, d.ctx.high_c, d.ctx.rain, d.ctx.occasion)
        if key in self._refs:
            return self._refs[key]
        found = outfits._search(self.pool, d.ctx, d.t, None, True)
        if not found:
            ref: _Reference | str = self._why_not(d)
        else:
            dry = [o for o in found if "wet_shoes" not in _flags(o, d.ctx, d.t)]
            best = min(dry or found, key=lambda o: (-o.raw, o.ids()))
            problem = None
            if not dry:
                word = outfits._rain_unfriendly(best.shoes.piece)
                problem = (f"Nothing rain-proof to wear on your feet: the shoes that suit the day are {word} "
                           "and will soak through. The outfit below is the best there is.")
            ref = _Reference(best.raw, _flags(best, d.ctx, d.t), d.t <= outfits.COLD_C and bool(self.outers), problem)
        self._refs[key] = ref
        return ref

    def _why_not(self, d: _Day) -> str:
        words = f"{outfits.OCCASION_WORDS[d.occasion]} at {outfits._temp_words(d.ctx)}"
        pairs = [(p, it) for p, it in self.everything]
        for place in ("base", "bottom", "shoes"):
            missing = outfits._missing_place(place, pairs, self.pool, d.ctx)
            if missing:
                return missing.replace("today", "on this trip")
        relaxed = outfits._search(self.pool, d.ctx, d.t, None, False)
        if not relaxed:
            return f"Nothing in the closet goes together for {words}."
        best = min(relaxed, key=lambda o: (-o.raw, o.ids()))
        problems = [x.problem for x in best.core() if x.problem] + best.problems
        return f"Nothing in the closet suits {words}. {problems[0] if problems else ''}".strip()

    def key(self, o: outfits._Outfit) -> tuple:
        pieces = _core(o)
        new = [p for p in pieces if p.id not in self.packed]
        groups = [GROUP_OF.get(p.category) for p in list(self.packed.values()) + new]
        over = max(0, groups.count("outer") - MAX_OUTER) + max(0, groups.count("shoes") - MAX_SHOES)
        return over, len(new), -o.raw, o.ids()

    def acceptable(self, o: outfits._Outfit, d: _Day, ref: _Reference) -> bool:
        if ref.outer_needed and o.outer is None:
            return False
        if o.raw < ref.raw - SCORE_SLACK:
            return False
        return _flags(o, d.ctx, d.t) <= ref.flags

    def dress(self, d: _Day) -> None:
        ref = self.reference(d)
        if isinstance(ref, str):
            d.problem = ref
            return
        free = [p for p in self.pool if self.used.get(p.id, 0) < self.caps[p.id]]
        packed = [p for p in free if p.id in self.packed]
        pools = [packed]
        for place in outfits.PLACES:
            opened = packed + [p for p in free if p.id not in self.packed and p.category in outfits.PLACE_CATEGORIES[place]]
            if len(opened) > len(packed):
                pools.append(opened)
        best = None
        for pool in pools:
            for o in outfits._search(pool, d.ctx, d.t, None, True):
                if self.acceptable(o, d, ref) and (best is None or self.key(o) < self.key(best)):
                    best = o
        if best is None or self.key(best)[0] > 0:
            everything = outfits._search(free, d.ctx, d.t, None, True)
            for o in everything:
                if self.acceptable(o, d, ref) and (best is None or self.key(o) < self.key(best)):
                    best = o
            if best is None:
                # nothing as good as the closet's best is left (it has been worn as often as it can be): the best left
                for o in everything:
                    k = (len(_flags(o, d.ctx, d.t) - ref.flags),) + self.key(o)
                    if ref.outer_needed and o.outer is None:
                        continue
                    if best is None or k < (len(_flags(best, d.ctx, d.t) - ref.flags),) + self.key(best):
                        best = o
        if best is None:
            d.problem = ("Everything that suits this day has already been worn as many days as the plan allows. "
                         "Choose \u201cI can wash there\u201d or take more pieces.")
            return
        d.outfit = best
        d.warning = ref.problem
        for p in _core(best):
            self.packed.setdefault(p.id, p)
            self.used[p.id] = self.used.get(p.id, 0) + 1

    def accessorize(self, d: _Day) -> None:
        o = d.outfit
        whole = dataclasses.replace(o, accessories=[])
        outfits._add_accessories(whole, self.pool, d.ctx, d.t, None)
        packed = [p for p in self.pool if p.id in self.packed and p.category in outfits.ACCESSORY_CATEGORIES]
        mine = dataclasses.replace(o, accessories=[])
        outfits._add_accessories(mine, packed, d.ctx, d.t, None)
        have = {x.piece.category for x in mine.accessories}
        mine.accessories += [x for x in whole.accessories if x.piece.category not in have]
        d.outfit = mine
        for x in mine.accessories:
            self.packed.setdefault(x.piece.id, x.piece)
            self.acc_used[x.piece.id] = self.acc_used.get(x.piece.id, 0) + 1

    # ------------------------------------------------------------ the whole trip
    def run(self) -> dict:
        known = [d for d in self.days if d.weather.get("source") != "unknown"]
        for d in self.days:
            if d not in known:
                d.problem = "The weather for this day is not known yet, so nothing was chosen for it. Try again later."
                continue
            w = d.weather
            d.ctx = outfits.Context(float(w["low_c"]), float(w["high_c"]), bool(w["rain"]), d.occasion,
                                    leave_out=self.opts.leave_out)
            d.t = outfits._design_temp(d.ctx)
        order = sorted(known, key=lambda d: (round(d.t, 1), not d.ctx.rain, -OCCASIONS.index(d.occasion), d.date))
        for d in order:
            self.dress(d)
        for d in order:
            if d.outfit is not None:
                self.accessorize(d)
        return self.answer(order)

    def answer(self, order: list[_Day]) -> dict:
        days = []
        for d in self.days:
            entry = {"date": d.date, "occasion": d.occasion, "weather": d.weather, "outfit": None, "problem": d.problem,
                     "warning": d.warning}
            if d.outfit is not None:
                score, reasons, warnings = outfits._explain(d.outfit, d.ctx, d.t, None, self.outers)
                pieces = {place: (getattr(d.outfit, place).piece.id if getattr(d.outfit, place) else None)
                          for place in outfits.PLACES}
                pieces["accessories"] = [x.piece.id for x in d.outfit.accessories]
                entry["outfit"] = {"pieces": pieces, "score": score, "reasons": reasons, "warnings": warnings}
            days.append(entry)
        packed = []
        for pid, p in self.packed.items():
            worn = self.used.get(pid, 0) + self.acc_used.get(pid, 0)
            packed.append({"id": pid, "group": GROUP_OF.get(p.category, "accessories"), "days": worn,
                           "pinned": pid in self.opts.pin})
            if not worn:
                self.notes.append(f"You asked to take {_the(p)}; no day's outfit uses it.")
        packed.sort(key=lambda x: (GROUP_ORDER.index(x["group"]), -x["days"], self.packed[x["id"]].label.lower(), x["id"]))
        return {
            "packed": packed,
            "days": days,
            "basics": self.basics(order),
            "uncovered": [{"date": d["date"], "reason": d["problem"]} for d in days if d["outfit"] is None],
            "warnings": [{"date": d["date"], "reason": d["warning"]} for d in days if d["warning"]],
            "notes": self.notes,
        }

    def basics(self, order: list[_Day]) -> list[dict]:
        n = self.n_days
        covered = min(n, WASH_CYCLE_DAYS) if self.opts.can_wash else n
        nights = max(0, n - 1)
        out = [
            {"key": "underwear", "name": "Underwear", "count": covered + SPARE},
            {"key": "socks", "name": "Pairs of socks", "count": covered + SPARE},
        ]
        if nights:
            sleep = 1 if self.opts.can_wash else math.ceil(nights / SLEEPWEAR_NIGHTS)
            out.append({"key": "sleepwear", "name": "Sleepwear", "count": sleep})
        rainy = [d for d in order if d.ctx.rain and d.t < outfits.HOT_C]
        if any(d.outfit is None or d.outfit.outer is None or not outfits._rain_friendly(d.outfit.outer.piece) for d in rainy):
            out.append({"key": "umbrella", "name": "Umbrella", "count": 1})
        if any(d.t <= GLOVES_MAX_C for d in order):
            out.append({"key": "gloves", "name": "Gloves", "count": 1})
        return out


def plan(items: Iterable[object], days: list[Mapping], options: Options | Mapping | None = None) -> dict:
    """The packing plan for a trip.

    `days` are the trip's days in order, each {date, low_c, high_c, rain, source, ...} (source `unknown` when the
    weather could not be had). Returns {"packed": [{id, group, days, pinned}], "days": [{date, occasion, weather,
    outfit, problem, warning}], "basics": [{key, name, count}], "uncovered": [{date, reason}], "warnings": [{date, reason}],
    "notes": [sentences]}.
    """
    dates = [str(d.get("date")) for d in days]
    opts = options if isinstance(options, Options) else parse_options(options or {}, dates)
    trip = [_Day(str(d["date"]), dict(d), opts.day_occasions.get(str(d["date"]), opts.occasion)) for d in days]
    return _Planner(list(items), trip, opts).run()


def lines(result: Mapping) -> list[str]:
    """Every line of a plan that can be ticked as packed: the pieces, then the basics."""
    return [f"item:{p['id']}" for p in result.get("packed", [])] + [f"basic:{b['key']}" for b in result.get("basics", [])]
