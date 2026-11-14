"""What to pack for a trip, chosen by rule.

Pure functions: no database, no network, no clock. `plan(items, days, options)`
takes the closet's items (as the outfit engine takes them), the trip's days
(the weather for each, as `tripweather.lookup` gives it) and the owner's
choices (the trip's occasion and the days that differ, laundry on the trip,
pieces swapped out and pieces pinned in), and the owner's "Before it needs
washing" setting, and returns what to pack, one outfit for each day made only
from packed pieces, the basics to bring by count, the counts and wash days
explained in plain words, and the days that could not be covered and why. The
same inputs always give the same plan.

How it chooses: the days are dressed hardest first (coldest, then rainy, then
the dressiest). For each day the outfit engine's own search is run over the
packed pieces alone, then over the packed pieces plus one place left open
(new tops, or new shoes...), then over the whole closet, and the outfit that
adds the fewest new pieces is taken, then the one the engine scores highest.
An outfit of packed pieces is only taken when it is within SCORE_SLACK points
of the best the closet can do that day and has no warning the best one does
not have (cold, too warm, rain coming in, shoes that soak). Each piece can be
worn as many times before washing as the owner allows for its kind (KINDS,
REWEAR_DEFAULTS); on a hot or humid day (SWEATY_C) a piece worn next to the
skin is worn once and then needs washing. A wash on a day of the trip cleans
what was worn before that day, for wearing again from the next day. At most
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
from .tagger.taxonomy import GARMENT_CATEGORIES

# ------------------------------------------------------------------ re-wearing
# The kinds of clothing the owner says how often to wear before washing (Settings, "Before it needs washing"), each
# named by the taxonomy's categories of clothing (tagger.taxonomy.GARMENT_CATEGORIES says which closet categories
# those are). Basics are counts, not closet items. Shoes and accessories are not counted: worn the whole trip.
KINDS = (
    ("tops", ("knit_top", "woven_shirt")),
    ("knits", ("knitwear", "sweatshirt")),
    ("bottoms", ("bottoms",)),
    ("outer", ("outerwear", "tailoring")),
    ("basics", ()),
)
KIND_KEYS = tuple(k for k, _ in KINDS)
KIND_OF = {closet: kind for kind, cats in KINDS for cat in cats for closet in GARMENT_CATEGORIES[cat]}
REWEAR_DEFAULTS = {"tops": 1, "knits": 3, "bottoms": 3, "outer": None, "basics": 1}  # wears; None: the whole trip
MAX_REWEAR = 30              # the most wears the setting takes for one kind (a trip is at most 30 days)
NEXT_TO_SKIN = ("tops", "basics")  # worn once on a hot or humid day, whatever the owner allows
SWEATY_C = 24                # a day is hot or humid when its high, or its feels-like high, is at least this (°C)
MAX_OUTER = 1                # outer layers packed (jackets and coats) unless the days cannot be covered otherwise
MAX_SHOES = 2                # pairs of shoes packed unless the days cannot be covered otherwise
SCORE_SLACK = 10             # an outfit of packed pieces is taken when it scores within this of the day's best

# ------------------------------------------------------------------ basics (not items in the closet)
SPARE = 1                    # underwear and socks: what the days need plus this many
SLEEPWEAR_NIGHTS = 7         # one set of sleepwear for every this many nights (one in all with laundry)
GLOVES_MAX_C = 2             # gloves when a day is dressed for at or below this (°C)

# ------------------------------------------------------------------ what to pack, grouped
# The outfit engine's places: a shirt worn over a tee is still a top, a jacket under a coat still outer.
_PLACE = outfits.PLACE_CATEGORIES
GROUPS = (
    ("tops", _PLACE["base"]),
    ("layers", tuple(c for c in _PLACE["mid"] if c not in _PLACE["base"] + _PLACE["outer"])),
    ("bottoms", _PLACE["bottom"]),
    ("shoes", _PLACE["shoes"]),
    ("outer", _PLACE["outer"]),
    ("accessories", outfits.ACCESSORY_CATEGORIES),
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
    laundry: tuple[str, int] | None = None   # ("day", 4): laundry on day 4; ("every", 3): every 3 days; None: none
    leave_out: tuple[str, ...] = ()
    pin: tuple[str, ...] = ()


def wash_days(laundry: tuple[str, int] | None, n_days: int) -> list[int]:
    """The days of the trip (1 is the first) laundry is done on. A wash on day w cleans what was worn on the days
    before w, to wear again from day w + 1; a wash every N days is done on days N + 1, 2N + 1 and so on."""
    if not laundry:
        return []
    how, n = laundry
    if how == "day":
        return [n] if 1 < n < n_days else []
    return list(range(n + 1, n_days, n))


def check_laundry(value: object, n_days: int) -> tuple[str, int] | None:
    """The trip's laundry choice: none, {"day": 4} or {"every": 3}. Raises PlanError with a sentence."""
    if value is None:
        return None
    if (not isinstance(value, Mapping) or len(value) != 1 or next(iter(value)) not in ("day", "every")
            or isinstance(next(iter(value.values())), bool) or not isinstance(next(iter(value.values())), int)):
        raise PlanError("Laundry must be none, a day of the trip such as {\"day\": 4}, or every so many days such as "
                        "{\"every\": 3}.")
    (how, n), = value.items()
    if n_days < 3:
        raise PlanError("A trip this short has no day for laundry: a wash on the first or last day frees nothing.")
    if how == "day" and not 2 <= n <= n_days - 1:
        raise PlanError(f"Choose a laundry day from day 2 to day {n_days - 1}: a wash on the first or last day frees nothing.")
    if how == "every" and not 1 <= n <= n_days - 2:
        raise PlanError(f"Laundry every {n} days does not come round before the trip ends. "
                        f"Choose from every day to every {n_days - 2} days.")
    return how, n


def laundry_json(laundry: tuple[str, int] | None) -> dict | None:
    return {laundry[0]: laundry[1]} if laundry else None


def check_rewear(value: object) -> dict:
    """The owner's "Before it needs washing" setting, filled in with the defaults: kind -> wears (None: the whole
    trip). Raises PlanError with a sentence when it is not one."""
    if value is None:
        return dict(REWEAR_DEFAULTS)
    if not isinstance(value, Mapping):
        raise PlanError(f"Say how often each kind is worn before washing, for example {{\"tops\": 1}}. "
                        f"The kinds are: {', '.join(KIND_KEYS)}.")
    unknown = sorted(set(value) - set(KIND_KEYS))
    if unknown:
        raise PlanError(f"These are not kinds of clothing: {', '.join(map(str, unknown))}. "
                        f"The kinds are: {', '.join(KIND_KEYS)}.")
    for n in value.values():
        if n is not None and (isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= MAX_REWEAR):
            raise PlanError(f"Wears before washing must be a whole number from 1 to {MAX_REWEAR}, or none for the "
                            "whole trip.")
    return {**REWEAR_DEFAULTS, **value}


def parse_options(data: Mapping, dates: Iterable[str]) -> Options:
    """Check the owner's choices for a trip. Raises PlanError with a sentence."""
    dates = list(dates)
    n_days = len(dates)
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
    laundry = check_laundry(data.get("laundry"), n_days)
    lists = {}
    for key, words in (("leave_out", "Pieces to leave out"), ("pin", "Pieces to take")):
        v = data.get(key) or []
        if not isinstance(v, list) or not all(isinstance(x, str) and x for x in v):
            raise PlanError(f"{words} must be a list of item ids.")
        lists[key] = tuple(sorted(set(v)))
    both = set(lists["leave_out"]) & set(lists["pin"])
    if both:
        raise PlanError("A piece cannot be both left out and taken.")
    return Options(occasion, {k: days[k] for k in sorted(days) if days[k] != occasion}, laundry, lists["leave_out"], lists["pin"])


# ====================================================================== helpers
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


def sweaty(weather: Mapping) -> bool:
    """A hot or humid day: its high, or its feels-like high (which counts the humidity), reaches SWEATY_C."""
    for key in ("high_c", "feels_high_c"):
        v = weather.get(key)
        if isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v) and v >= SWEATY_C:
            return True
    return False


def _fits(worn: set[int], cap: int, washes: set[int], hot: list[bool], skin: bool) -> bool:
    """Whether a piece can be worn on these days (0 is the first) and be washed only when the trip's laundry is:
    at most `cap` wears between washes, and on a hot or humid day a piece next to the skin is worn fresh and
    then needs washing. A wash on day w cleans the pieces not worn on day w."""
    count = 0
    for day, is_hot in enumerate(hot):
        if day in worn:
            if is_hot and skin:
                if count:
                    return False
                count = cap
            else:
                count += 1
                if count > cap:
                    return False
        elif day in washes:
            count = 0
    return True


def _needed(cap: int, washes: set[int], hot: list[bool], skin: bool = True) -> int:
    """How many of a basic (underwear, a pair of socks) cover every day, by the same rule as `_fits`."""
    pieces: list[int] = []   # wears since each was washed
    for day, is_hot in enumerate(hot):
        fresh = is_hot and skin
        free = [i for i, c in enumerate(pieces) if (c == 0 if fresh else c < cap)]
        if free:
            i = max(free, key=lambda i: (pieces[i], -i))
        else:
            pieces.append(0)
            i = len(pieces) - 1
        pieces[i] = cap if fresh else pieces[i] + 1
        if day in washes:
            pieces = [c if k == i else 0 for k, c in enumerate(pieces)]
    return len(pieces)


# ------------------------------------------------------------------ the plan in words
# What a count is called: by its closet category when every piece of the kind is one category, otherwise by the
# kind. (one, more than one, after "the" in a wash note)
KIND_WORDS = {"tops": ("top", "tops", "tops"), "knits": ("sweater or sweatshirt", "sweaters and sweatshirts", "sweaters"),
              "bottoms": ("pair of trousers or shorts", "pairs of trousers and shorts", "trousers"),
              "outer": ("jacket or coat", "jackets and coats", "jackets")}
CATEGORY_WORDS = {"tee": ("tee", "tees", "tees"), "shirt": ("shirt", "shirts", "shirts"), "polo": ("polo", "polos", "polos"),
                  "sweater": ("sweater", "sweaters", "sweaters"), "hoodie": ("hoodie", "hoodies", "hoodies"),
                  "trousers": ("pair of trousers", "pairs of trousers", "trousers"),
                  "shorts": ("pair of shorts", "pairs of shorts", "shorts"), "jacket": ("jacket", "jackets", "jackets"),
                  "coat": ("coat", "coats", "coats")}


def _noun(pieces: list[outfits.Piece], kind: str) -> tuple[str, str, str]:
    cats = {p.category for p in pieces}
    if len(cats) == 1 and next(iter(cats)) in CATEGORY_WORDS:
        return CATEGORY_WORDS[next(iter(cats))]
    return KIND_WORDS[kind]


def _and(words: list[str]) -> str:
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} and {words[-1]}"


def _days(a: int, b: int) -> str:
    return f"day {a}" if a == b else f"days {a}\u2013{b}"


def laundry_words(laundry: tuple[str, int] | None) -> str | None:
    """"laundry on day 4", "laundry every 3 days", "laundry every day"."""
    if not laundry:
        return None
    how, n = laundry
    if how == "day":
        return f"laundry on day {n}"
    return "laundry every day" if n == 1 else f"laundry every {n} days"


@dataclass
class _Day:
    date: str
    weather: dict
    occasion: str
    index: int = 0                   # 0 is the trip's first day
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
    def __init__(self, items: list, days: list[_Day], opts: Options, rewear: Mapping):
        self.opts = opts
        self.rewear = dict(rewear)
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
        self.washes = {w - 1 for w in wash_days(opts.laundry, self.n_days)}
        self.hot = [sweaty(d.weather) for d in days]
        self.worn_on: dict[str, set[int]] = {}
        self.used: dict[str, int] = {}
        self.acc_used: dict[str, int] = {}
        self.packed: dict[str, outfits.Piece] = {pid: self.by_id[pid] for pid in opts.pin if pid in self.by_id}
        self.outers = [p for p in pool if p.category in outfits.PLACE_CATEGORIES["outer"]]
        self._refs: dict[tuple, _Reference | str] = {}

    # ------------------------------------------------------------ re-wearing
    def cap(self, p: outfits.Piece) -> int | None:
        """Wears before washing for the piece's kind; None: as often as the trip needs (shoes, accessories, and
        a kind the owner allows the whole trip)."""
        kind = KIND_OF.get(p.category)
        return None if kind is None else self.rewear.get(kind)

    def can_wear(self, p: outfits.Piece, d: _Day) -> bool:
        cap = self.cap(p)
        if cap is None:
            return True
        return _fits(self.worn_on.get(p.id, set()) | {d.index}, cap, self.washes, self.hot, KIND_OF[p.category] in NEXT_TO_SKIN)

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
        free = [p for p in self.pool if self.can_wear(p, d)]
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
            d.problem = ("Everything that suits this day has already been worn as often as it can be before washing. "
                         "Choose \u201cI can do laundry\u201d, allow more wears in Settings (Before it needs washing), "
                         "or take more pieces.")
            return
        d.outfit = best
        d.warning = ref.problem
        for p in _core(best):
            self.packed.setdefault(p.id, p)
            self.used[p.id] = self.used.get(p.id, 0) + 1
            self.worn_on.setdefault(p.id, set()).add(d.index)

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
                     "warning": d.warning, "laundry": d.index in self.washes}
            if d.outfit is not None:
                score, reasons, warnings = outfits._explain(d.outfit, d.ctx, d.t, None, self.outers)
                entry["warning"] = d.warning or (warnings[0] if warnings else None)
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
        basics = self.basics(order)
        return {
            "packed": packed,
            "days": days,
            "basics": basics,
            "laundry": laundry_json(self.opts.laundry),
            "counts": self.counts(),
            "washes": self.wash_notes(basics),
            "uncovered": [{"date": d["date"], "reason": d["problem"]} for d in days if d["outfit"] is None],
            "warnings": [{"date": d["date"], "reason": d["warning"]} for d in days if d["warning"]],
            "notes": self.notes,
        }

    def basics(self, order: list[_Day]) -> list[dict]:
        n = self.n_days
        cap = self.rewear.get("basics") or n
        need = _needed(cap, self.washes, self.hot)
        nights = max(0, n - 1)
        if cap == 1:
            parts = ["one a day"]
        elif self.hot and all(self.hot):
            parts = ["one a day, as every day is hot or humid"]
        elif cap >= n:
            parts = ["worn the whole trip"]
        else:
            parts = [f"worn up to {cap} times each" + (", once on a hot or humid day" if any(self.hot) else "")]
        parts.append("one spare")
        wash = laundry_words(self.opts.laundry) if self.washes else None
        if wash:
            parts.append(wash)
        why = ", ".join(parts)
        out = [
            {"key": "underwear", "name": "Underwear", "count": need + SPARE, "why": why},
            {"key": "socks", "name": "Pairs of socks", "count": need + SPARE, "why": why},
        ]
        if nights:
            sleep = 1 if self.washes else math.ceil(nights / SLEEPWEAR_NIGHTS)
            out.append({"key": "sleepwear", "name": "Sleepwear", "count": sleep})
        rainy = [d for d in order if d.ctx.rain and d.t < outfits.HOT_C]
        if any(d.outfit is None or d.outfit.outer is None or not outfits._rain_friendly(d.outfit.outer.piece) for d in rainy):
            out.append({"key": "umbrella", "name": "Umbrella", "count": 1})
        if any(d.t <= GLOVES_MAX_C for d in order):
            out.append({"key": "gloves", "name": "Gloves", "count": 1})
        return out

    def _kind_pieces(self, kind: str) -> list[outfits.Piece]:
        return [p for p in self.packed.values() if KIND_OF.get(p.category) == kind]

    def counts(self) -> list[dict]:
        """Each kind's count in plain words: "5 shirts: one a day, laundry on day 4"."""
        out = []
        wash = laundry_words(self.opts.laundry) if self.washes else None
        for kind in KIND_KEYS:
            if kind == "basics":
                continue
            pieces = self._kind_pieces(kind)
            if not pieces:
                continue
            cap = self.rewear.get(kind)
            days = set().union(*(self.worn_on.get(p.id, set()) for p in pieces))
            wears = sum(len(self.worn_on.get(p.id, ())) for p in pieces)
            one, many, _ = _noun(pieces, kind)
            parts = []
            if kind == "knits" and days:
                parts.append("1 cool day" if len(days) == 1 else f"{len(days)} cool days")
            if cap is None:
                parts.append("one for the whole trip" if len(pieces) == 1 else "worn the whole trip")
            elif cap == 1:
                parts.append("one a day" if wears == len(days) else "each worn once")
            elif kind in NEXT_TO_SKIN and days and all(self.hot[i] for i in days):
                parts.append("one a day, as every day is hot or humid")
            elif kind in NEXT_TO_SKIN and any(self.hot[i] for i in days):
                parts.append(f"worn up to {cap} times each, once on a hot or humid day")
            else:
                parts.append(f"worn up to {cap} times each")
            if wash and cap is not None:
                parts.append(wash)
            n = len(pieces)
            out.append({"kind": kind, "count": n, "words": f"{n} {one if n == 1 else many}: {', '.join(parts)}"})
        return out

    def wash_notes(self, basics: list[dict]) -> list[dict]:
        """Where each wash falls and what is worn again after it."""
        out = []
        washes = sorted(self.washes)
        basics_reused = any(b["key"] == "underwear" and b["count"] - SPARE < self.n_days for b in basics)
        for k, w in enumerate(washes):
            start = washes[k - 1] if k else 0
            nouns = []
            for kind in KIND_KEYS:
                if kind == "basics":
                    continue
                again = [p for p in self._kind_pieces(kind) if self.cap(p) is not None
                         and w not in (worn := self.worn_on.get(p.id, set()))
                         and any(start <= i < w for i in worn) and any(i > w for i in worn)]
                if again:
                    nouns.append(_noun(again, kind)[2])
            if basics_reused:
                nouns += ["underwear", "socks"]
            if nouns:
                words = (f"Wash on day {w + 1}: the {_and(nouns)} from {_days(start + 1, w)} are worn again "
                         f"from day {w + 2}.")
            else:
                words = f"Wash on day {w + 1}: nothing has to be worn again after it."
            out.append({"day": w + 1, "date": self.days[w].date, "words": words})
        return out


def plan(items: Iterable[object], days: list[Mapping], options: Options | Mapping | None = None,
         rewear: Mapping | None = None) -> dict:
    """The packing plan for a trip.

    `days` are the trip's days in order, each {date, low_c, high_c, rain, source, ...} (source `unknown` when the
    weather could not be had). `rewear` is the owner's "Before it needs washing" setting (`check_rewear`; the
    defaults when None). Returns {"packed": [{id, group, days, pinned}], "days": [{date, occasion, weather, outfit,
    problem, warning, laundry}], "basics": [{key, name, count, why}], "laundry": {"day": n} | {"every": n} | None,
    "counts": [{kind, count, words}], "washes": [{day, date, words}], "uncovered": [{date, reason}],
    "warnings": [{date, reason}], "notes": [sentences]}.
    """
    dates = [str(d.get("date")) for d in days]
    opts = options if isinstance(options, Options) else parse_options(options or {}, dates)
    trip = [_Day(str(d["date"]), dict(d), opts.day_occasions.get(str(d["date"]), opts.occasion), i)
            for i, d in enumerate(days)]
    return _Planner(list(items), trip, opts, check_rewear(rewear)).run()


def lines(result: Mapping) -> list[str]:
    """Every line of a plan that can be ticked as packed: the pieces, then the basics."""
    return [f"item:{p['id']}" for p in result.get("packed", [])] + [f"basic:{b['key']}" for b in result.get("basics", [])]
