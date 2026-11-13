"""What's missing from the closet, found by rule.

Pure functions: no database, no network, no clock. `find_gaps(items, wears,
options)` takes the closet's items (as the outfit engine takes them), the wear
log (`{item_id, worn_on}` rows) and options, and returns a short ranked list of
things the owner could buy that would make the closet work better, each with
what to look for, why (sentences naming the owner's own items), how much it
would help (0 to 100) and the evidence behind it. The same inputs always give
the same answer.

Gaps are found five ways, and each gap says which found it:
- "days": the outfit engine (`outfits.suggest`) is run over a fixed grid of
  days (cold, cool, mild, hot; dry and rain; every occasion). Where it returns
  nothing, has to break its own rules, warns (cold, too warm, rain) or cannot
  make three outfits that differ, the failure is turned into the piece that
  would fix it.
- "thin_place": one piece that every outfit for some kind of day rests on.
- "orphan": an item that goes into no outfit because nothing of one kind goes
  with it, and the single piece that would bring it into use.
- "worn_most": from the wear log, an item worn far more than the others of its
  kind, which a second one would relieve. Items never worn are not gaps; they
  are mentioned in `notes`.
- "basic": a short list of menswear basics (BASICS) the closet lacks.

Gaps that would be met by the same purchase are merged and their evidence
combined; the list is ranked by how much each would help and cut to MAX_GAPS.
Items in the laundry count as owned: a shirt in the wash is not missing.

The engine's own rules are read from `outfits.py` (its pieces, its options per
place, its rules for a piece and between pieces), so the two never disagree;
nothing there is changed.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from . import outfits, vocab

# ------------------------------------------------------------------ the closet
MIN_ITEMS = 8                # fewer clothes than this (not archived) and the closet is too small to judge
MAX_GAPS = 8                 # the list is cut to this many gaps

# ------------------------------------------------------------------ the grid of days
# (name, low °C, high °C): the engine dresses for the low plus 30% of the way to the high, so these
# land at about 2°C (an outer layer is needed), 10°C, 17°C and 27°C (no layers, no cool-season pieces).
TEMP_BANDS = (("cold", 0.0, 6.0), ("cool", 8.0, 14.0), ("mild", 15.0, 21.0), ("hot", 25.0, 31.0))
DAYS_PER_WEEK = 7
WEATHER_CELLS = len(TEMP_BANDS) * 2
DAY_OUTFITS = 3              # outfits asked of the engine for each day; fewer than this that differ is a failure
# How much a bad day of each occasion counts: everyday occasions most, sport and formal occasions least.
OCCASION_WEIGHT = {"athletic": 0.3, "casual": 1.0, "smart_casual": 1.0, "business": 0.7, "formal": 0.3}
# How much each kind of failure on a day counts.
FAILURE_WEIGHT = {
    "none": 1.0,        # no outfit at all: the closet has nothing for one of base, bottom or shoes
    "settle": 0.8,      # the engine had to use a piece that breaks a rule for the day (too casual, too cold...)
    "clash": 0.6,       # the engine had to put together pieces that break a rule between them
    "cold": 0.8,        # even the warmest outfit is well short of warm
    "warm": 0.5,        # even the lightest outfit is well too warm
    "rain": 0.6,        # rain and nothing that keeps it off ("take an umbrella")
    "rain_shoes": 0.4,  # rain and the best shoes are suede, canvas, linen or silk
    "few": 0.4,         # fewer than DAY_OUTFITS outfits that differ
}
DAY_SCORE_PER_POINT = 10     # a gap found on days scores this per weighted failing day...
DAY_SCORE_MAX = 95           # ...up to this

# ------------------------------------------------------------------ thin places
THIN_WARMTH_SLACK = 1.0      # on a cold day, a coat or jacket this many warmth points lighter than the one used is no second
THIN_SCORE_BASE = 25         # a thin place scores this...
THIN_SCORE_PER_POINT = 5     # ...plus this per day (weighted by occasion) that rests on the one piece...
THIN_SCORE_MAX = 60          # ...up to this

# ------------------------------------------------------------------ orphans
ORPHAN_MAX_OUTFITS = 1       # an item in at most this many of the grid's outfits may be an orphan...
ORPHAN_MAX_PARTNERS = 0      # ...when at most this many pieces of a kind it needs go with it
ORPHAN_SCORE = 30            # an orphan scores this
ORPHAN_LOVED_BONUS = 10      # more when it is an item the owner loves

# ------------------------------------------------------------------ the wear log
WEAR_MIN_LOG = 10            # fewer wears than this in the log and it says nothing yet
WEAR_HEAVY_MIN = 4           # worn at least this many times...
WEAR_HEAVY_RATIO = 3.0       # ...and at least this many times the average of the others of its category
WEAR_SCORE_BASE = 20         # an item worn out of proportion scores this...
WEAR_SCORE_PER_WEAR = 4      # ...plus this per wear above the others' average...
WEAR_SCORE_MAX = 50          # ...up to this
NEVER_WORN_NAMES = 4         # the note about items never worn names at most this many

# ------------------------------------------------------------------ merging and evidence
MERGE_SHARE = 0.25           # a merged gap scores its best finding plus this share of the others
SCORE_CAP = 100
WHY_MAX = 4                  # at most this many sentences of why
EVIDENCE_ITEMS_MAX = 8       # at most this many items as evidence
EVIDENCE_FILL_TO = 3         # fewer than this and owned items it would go with are added
COLORS_MAX = 3               # colours suggested to look for


@dataclass(frozen=True)
class Basic:
    """A piece a men's wardrobe is expected to have, and what counts as having one."""
    key: str
    name: str
    categories: tuple[str, ...]      # any of these categories...
    colors: tuple[str, ...] = ()     # ...in one of these colours (empty: any colour)
    min_formality: str | None = None  # ...at least this formal
    solid: bool = False              # ...plain, not patterned
    rain: bool = False               # ...whose name or material says it sheds water
    min_weight: int | None = None    # ...at least this weight class (0 lightweight to 3 super heavy)
    want: tuple[str, str | None, str | None] = ("tee", None, None)  # what to buy: category, formality, tag
    score: int = 30                  # how much having it would help
    why: str = ""


NEUTRAL_TOPS = ("white", "grey", "navy", "black")
# The basics, from the classics `docs/menswear-reference.md` describes. Kept short: each is something
# almost every outfit the engine makes needs, or a day it cannot dress without.
BASICS = (
    # 4.1: the plain crew-neck tee is the base of casual outfits and goes under everything.
    Basic("plain_tee", "A plain tee", ("tee",), NEUTRAL_TOPS, solid=True, want=("tee", "casual", None), score=40,
          why="A plain tee in white, grey, navy or black goes under everything and with everything."),
    # 4.2: the oxford cloth button-down (OCBD) in white or light blue, the smart casual shirt.
    Basic("oxford_shirt", "An oxford or button-down shirt", ("shirt",), ("white", "light_blue"), "smart_casual",
          want=("shirt", "smart_casual", None), score=45,
          why="A white or light blue button-up shirt is the step up from a tee for smart casual and business days."),
    # 4.4: a plain crewneck or V-neck sweater in a neutral, the usual middle layer.
    Basic("neutral_sweater", "A plain sweater", ("sweater",), outfits.NEUTRALS, solid=True,
          want=("sweater", "smart_casual", None), score=35,
          why="A plain sweater in a neutral colour is the middle layer for cool days and goes over any shirt."),
    # 4.7: five-pocket jeans in a dark or black wash.
    Basic("dark_jeans", "A pair of dark jeans", ("jeans",), ("navy", "blue", "black"), solid=True,
          want=("jeans", "casual", None), score=40,
          why="Dark jeans are the casual bottom most outfits are built on."),
    # 4.7: chinos or dress trousers in a neutral, for days jeans are too casual.
    Basic("neutral_trousers", "Chinos or smart trousers", ("trousers",), outfits.NEUTRALS, "smart_casual", solid=True,
          want=("trousers", "smart_casual", None), score=45,
          why="Chinos or trousers in a neutral colour are what smart casual days need when jeans are too casual."),
    # 4.5: a topcoat, overcoat, peacoat or parka: something heavy for cold days.
    Basic("warm_coat", "A warm winter coat", ("coat",), min_weight=2, want=("coat", "smart_casual", "warm"), score=50,
          why="A heavy coat is what keeps a cold day comfortable."),
    # 4.5: a mac, trench or waxed jacket: the outer layer that sheds rain.
    Basic("rain_layer", "A rain-proof outer layer", ("jacket", "coat"), rain=True, want=("coat", "smart_casual", "rain"),
          score=45, why="A mac, trench or waxed jacket keeps the rain off without an umbrella."),
    # 4.8: minimalist sneakers in white or another neutral, the everyday casual shoe.
    Basic("plain_sneakers", "A pair of plain sneakers", ("sneakers",), ("white", "black", "grey", "navy", "cream"), "casual",
          solid=True, want=("sneakers", "casual", None), score=35,
          why="Plain sneakers in white or another neutral go with every casual outfit."),
    # 4.8: oxfords, derbies or loafers in leather, for business and formal days.
    Basic("smart_shoes", "A pair of smart leather shoes", ("dress_shoes",), min_formality="smart_casual",
          want=("dress_shoes", "business", None), score=45,
          why="Smart leather shoes (oxfords, derbies or loafers) are what business and formal days need."),
    # 4.9: a leather belt, worn with trousers and jeans.
    Basic("belt", "A leather belt", ("belt",), want=("belt", "smart_casual", None), score=20,
          why="A leather belt finishes trousers and jeans; the engine adds one to every outfit that has them."),
)

WAYS = ("days", "thin_place", "orphan", "worn_most", "basic")

# ------------------------------------------------------------------ what to buy
# The formality of a piece bought for an occasion: one step of reach means casual pieces also do for
# sport, and business pieces also do for formal occasions.
PIECE_FORMALITY = {"athletic": "casual", "casual": "casual", "smart_casual": "smart_casual", "business": "business",
                   "formal": "business"}
# What fills a place for an occasion (by PIECE_FORMALITY), on a hot day and on any other day.
PICKS = {
    "base": {"casual": (("tee", "light"), ("tee", None)), "smart_casual": (("polo", None), ("shirt", None)),
             "business": (("shirt", "light"), ("shirt", None))},
    "mid": {"casual": (("sweater", None), ("sweater", None)), "smart_casual": (("sweater", None), ("sweater", None)),
            "business": (("sweater", None), ("sweater", None))},
    "bottom": {"casual": (("shorts", None), ("jeans", None)), "smart_casual": (("trousers", "light"), ("trousers", None)),
               "business": (("trousers", "light"), ("trousers", None))},
    "shoes": {"casual": (("sneakers", None), ("sneakers", None)), "smart_casual": (("boots", None), ("boots", None)),
              "business": (("dress_shoes", None), ("dress_shoes", None))},
}
OUTER_FORMALITY = "smart_casual"  # an outer layer may sit two steps from the rest, so a smart casual one does for every day
# What each tag means for the piece to look for.
TAG_LOOK = {
    "light": {"season": "warm", "weight_class": "lightweight"},
    "warm": {"season": "cool", "weight_class": "heavyweight"},
    "rain": {"season": "all", "weight_class": "midweight", "material": "waterproof (a mac, trench, waxed cotton or shell)"},
    "rainwarm": {"season": "cool", "weight_class": "heavyweight", "material": "waterproof (a parka or waxed coat)"},
}
CATEGORY_LOOK = {"shorts": {"season": "warm", "weight_class": "lightweight"}}
RAIN_SHOES_MATERIAL = "smooth leather or rubber, not suede or canvas"
# Colours to suggest for each category, most useful first: neutrals that go with everything.
COLOR_PICKS = {
    "tee": ("white", "grey", "navy", "black"), "shirt": ("white", "light_blue", "navy"), "polo": ("navy", "white", "grey"),
    "sweater": ("navy", "grey", "cream", "brown"), "hoodie": ("grey", "navy", "black"), "jacket": ("navy", "olive", "tan"),
    "coat": ("navy", "grey", "tan", "black"), "jeans": ("navy", "blue", "black"), "trousers": ("grey", "navy", "tan"),
    "shorts": ("tan", "navy", "olive"), "sneakers": ("white", "black", "grey"), "boots": ("brown", "black"),
    "dress_shoes": ("brown", "black"), "sandals": ("brown", "black"), "belt": ("brown", "black"),
    "scarf": ("grey", "navy", "brown"), "hat": ("grey", "navy", "black"), "bag": ("brown", "black", "navy"),
}
# Names in plain words, by (category, formality, tag); None matches any.
NAMES = (
    (("coat", None, "rain"), "A rain-proof outer layer"),
    (("coat", None, "rainwarm"), "A warm, waterproof coat"),
    (("coat", None, "warm"), "A warm winter coat"),
    (("jacket", None, None), "A light jacket"),
    (("coat", None, None), "A coat"),
    (("tee", None, "light"), "A light tee for hot days"),
    (("tee", None, None), "A plain tee"),
    (("polo", None, None), "A plain polo"),
    (("shirt", "business", "light"), "A light dress shirt for hot days"),
    (("shirt", "business", None), "A plain dress shirt"),
    (("shirt", None, None), "An oxford or button-down shirt"),
    (("sweater", None, "warm"), "A heavy sweater"),
    (("sweater", None, None), "A plain sweater"),
    (("trousers", "business", "light"), "Light smart trousers for hot days"),
    (("trousers", "business", None), "Smart trousers"),
    (("trousers", None, "light"), "Light chinos for hot days"),
    (("trousers", None, None), "Chinos or smart casual trousers"),
    (("jeans", None, None), "A pair of plain jeans"),
    (("shorts", None, None), "A pair of plain shorts"),
    (("sneakers", None, None), "A pair of plain sneakers"),
    (("boots", None, None), "A pair of leather boots"),
    (("dress_shoes", None, None), "A pair of smart leather shoes"),
    (("belt", None, None), "A leather belt"),
)

# ------------------------------------------------------------------ words
OCCASION_ADJ = {"athletic": "sport", "casual": "casual", "smart_casual": "smart casual", "business": "business",
                "formal": "formal"}
PLACE_NOUN = {"base": ("top", "tops"), "mid": ("middle layer", "middle layers"), "outer": ("coat or jacket", "coats and jackets"),
              "bottom": ("bottoms", "bottoms"), "shoes": ("shoes", "shoes")}
PLURAL_CATEGORIES = ("jeans", "trousers", "shorts", "sneakers", "boots", "dress_shoes", "sandals")
NUMBER = {0: "no", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}
# Places an item needs partners in to make an outfit, and places a new piece would go with.
NEEDS = {"base": ("bottom", "shoes"), "mid": ("base", "bottom", "shoes"), "outer": ("base", "bottom", "shoes"),
         "bottom": ("base", "shoes"), "shoes": ("base", "bottom"), "accessory": ("bottom", "shoes")}
HOME_PLACE = {"tee": "base", "shirt": "base", "polo": "base", "sweater": "mid", "hoodie": "mid", "jacket": "outer",
              "coat": "outer", "jeans": "bottom", "trousers": "bottom", "shorts": "bottom", "sneakers": "shoes",
              "boots": "shoes", "dress_shoes": "shoes", "sandals": "shoes"}


@dataclass(frozen=True)
class Options:
    max_gaps: int = MAX_GAPS


@dataclass(frozen=True)
class Day:
    band: str
    low_c: float
    high_c: float
    rain: bool
    occasion: str
    situation: str | None = None
    frequency: float = 0
    weather_share: float = 0
    mood: str = "usual"

    @property
    def weight(self) -> float:
        # Eight weather cells per occasion in the original grid; a full week has the same scale.
        return (OCCASION_WEIGHT[self.occasion] if self.situation is None
                else self.frequency / DAYS_PER_WEEK * self.weather_share * WEATHER_CELLS)

    def as_dict(self) -> dict:
        answer = {"temperature": self.band, "low_c": self.low_c, "high_c": self.high_c, "rain": self.rain,
                  "occasion": self.occasion, "words": day_words(self)}
        if self.situation:
            answer.update(situation=self.situation, share=self.frequency / 7 * self.weather_share)
        return answer


def grid() -> list[Day]:
    """The fixed days the closet is tried on, in a fixed order."""
    return [Day(band, lo, hi, rain, occ) for band, lo, hi in TEMP_BANDS for rain in (False, True) for occ in vocab.FORMALITY]


@dataclass
class _Finding:
    way: str
    want: tuple[str, str | None, str | None]   # category, formality, tag
    place: str
    why: list[str]
    score: float
    occasions: tuple[int, ...]                   # formality levels of the occasions it is needed for
    days: list[Day] = field(default_factory=list)
    items: list[str] = field(default_factory=list)
    first_color: str | None = None
    material: str | None = None
    solid: bool = False
    name: str | None = None


# ====================================================================== words
def day_words(d: Day) -> str:
    rain = ", rainy" if d.rain else ""
    noun = "occasion" if d.occasion == "formal" else "day"
    return f"a {d.band}{rain} {OCCASION_ADJ[d.occasion]} {noun}"


def _join(parts: list[str], word: str = "and") -> str:
    if not parts:
        return ""
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + f" {word} " + parts[-1]


def _days_words(days: Iterable[Day]) -> str:
    """Days in a few words: "cold, cool or mild rainy days", "business and formal days"."""
    days = sorted(set(days), key=_day_order)
    if len(days) == 1:
        return day_words(days[0])
    bands = [b for b, _, _ in TEMP_BANDS]
    by_band_occ: dict[tuple[str, str], set[bool]] = {}
    for d in days:
        by_band_occ.setdefault((d.band, d.occasion), set()).add(d.rain)
    by_occ_rain: dict[tuple[str, bool | None], list[str]] = {}
    for (band, occ), rains in by_band_occ.items():
        flag = None if len(rains) == 2 else next(iter(rains))
        by_occ_rain.setdefault((occ, flag), []).append(band)
    groups: dict[tuple[tuple[str, ...], bool | None], list[str]] = {}
    for (occ, flag), bs in by_occ_rain.items():
        groups.setdefault((tuple(sorted(bs, key=bands.index)), flag), []).append(occ)
    phrases = []
    for (bs, flag), occs in sorted(groups.items(), key=lambda g: (-len(g[1]) * len(g[0][0]), g[0][0], str(g[0][1]))):
        words = []
        if len(bs) < len(bands):
            words.append(_join(list(bs), "or"))
        if flag is not None:
            words.append("rainy" if flag else "dry")
        occs = sorted(occs, key=vocab.FORMALITY.index)
        if len(occs) < len(vocab.FORMALITY):
            words.append(_join([OCCASION_ADJ[o] for o in occs]))
        words.append("days")
        phrases.append(" ".join(words))
    if len(phrases) > 3:
        return ", ".join(phrases[:3]) + " and other days"
    return _join(phrases)


def _day_order(d: Day) -> tuple:
    return ([b for b, _, _ in TEMP_BANDS].index(d.band), d.rain, vocab.FORMALITY.index(d.occasion), d.situation or "")


def _your(p: outfits.Piece) -> str:
    return f"your {p.label}"


def _plural(p: outfits.Piece) -> bool:
    return p.category in PLURAL_CATEGORIES


def _be(pieces: list[outfits.Piece]) -> str:
    return "are" if len(pieces) > 1 or (pieces and _plural(pieces[0])) else "is"


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


# ====================================================================== what to buy
def _pick(place: str, occasion: str, band: str) -> tuple[str, str | None, str | None]:
    """What to buy to fill a place on a kind of day: (category, formality, tag)."""
    if place == "outer":
        if band == "cold":
            return ("coat", OUTER_FORMALITY, "warm")
        return ("jacket", OUTER_FORMALITY, None)
    formality = PIECE_FORMALITY[occasion]
    category, tag = PICKS[place][formality][0 if band == "hot" else 1]
    return (category, formality, tag)


def _family(want: tuple[str, str | None, str | None]) -> tuple[str, str | None]:
    """Purchases of one family are merged when one piece can serve all of them."""
    category, _formality, tag = want
    if category in outfits.PLACE_CATEGORIES["outer"]:
        return ("outer", tag)  # one smart casual outer layer does for every occasion, so only what it is for matters
    return (category, tag)


def _name(want: tuple[str, str | None, str | None]) -> str:
    category, formality, tag = want
    for (c, f, t), name in NAMES:
        if c == category and (f is None or f == formality) and t == tag:
            return name
    for (c, f, _t), name in NAMES:
        if c == category and (f is None or f == formality):
            return name
    return f"A {outfits.LEVEL_WORDS.get(formality or '', '')} {category.replace('_', ' ')}".replace("  ", " ")


def _probe(want: tuple[str, str | None, str | None], color: str | None) -> outfits.Piece:
    category, formality, tag = want
    look = {**CATEGORY_LOOK.get(category, {}), **TAG_LOOK.get(tag or "", {})}
    p = outfits._piece({"id": "~gap", "category": category, "color": color, "pattern": "solid", "formality": formality,
                        "season": look.get("season", "all"), "weight_class": look.get("weight_class")})
    assert p is not None
    return p


def _pair_problems(a: outfits.Piece, a_place: str, b: outfits.Piece, b_place: str) -> list[str]:
    """The engine's rules between two pieces (formality, colour, pattern), for pieces in these places."""
    outer = a if a_place == "outer" else b if b_place == "outer" else None
    clothes = [x for x in (a, b) if x is not outer]
    return outfits._outfit_problems([a, b], clothes, outer)


def _fills(p: outfits.Piece, place: str) -> bool:
    return p.category in outfits.PLACE_CATEGORIES.get(place, ())


# ====================================================================== the closet
@dataclass
class _Closet:
    pieces: list[outfits.Piece]                   # usable pieces (not archived, not disliked), sorted by id
    by_id: dict[str, outfits.Piece]
    disliked: list[outfits.Piece]
    engine_items: list[dict]
    wear_counts: dict[str, int]
    wear_total: int
    first_wear: str | None
    last_wear: str | None


def _closet(items: Iterable[object], wears: Iterable[object]) -> _Closet:
    engine_items, pieces, disliked = [], [], []
    for it in sorted((i for i in items if isinstance(i, Mapping) and i.get("id")), key=lambda i: str(i["id"])):
        if it.get("status") == "archived":
            continue
        clean = dict(it)
        clean["laundry"] = "clean"  # a piece in the wash is still owned
        if clean.get("location") == "laundry":
            clean["location"] = None
        p = outfits._piece(clean)
        if p is None:
            continue
        if clean.get("rating") == "dislike":
            disliked.append(p)
        else:
            pieces.append(p)
        engine_items.append(clean)
    by_id = {p.id: p for p in pieces}
    seen: set[tuple[str, str]] = set()
    counts: dict[str, int] = {}
    for w in wears:
        if not isinstance(w, Mapping):
            continue
        item_id, worn_on = str(w.get("item_id") or ""), w.get("worn_on")
        if item_id in by_id and isinstance(worn_on, str) and (item_id, worn_on) not in seen:
            seen.add((item_id, worn_on))
            counts[item_id] = counts.get(item_id, 0) + 1
    dates = sorted(d for _, d in seen)
    return _Closet(pieces, by_id, disliked, engine_items, counts, len(seen), dates[0] if dates else None,
                   dates[-1] if dates else None)


# ====================================================================== days the engine cannot dress well
def _reason(p: outfits.Piece, place: str, ctx: outfits.Context, t: float) -> str:
    """Why the engine would rather not use this piece today, in a few words (mirrors outfits._piece_problem)."""
    off = outfits._formality_off(p, place, ctx.occasion)
    if off:
        return "too casual" if off < 0 else "too dressy"
    if p.category == "sandals" and ctx.rain:
        return "no good in the rain"
    if p.category in ("shorts", "sandals") and t < (outfits.SHORTS_MIN_C if p.category == "shorts" else outfits.SANDALS_MIN_C):
        return "too light for the cold"
    if t >= outfits.HOT_C and p.season == "cool":
        return "made for cooler days"
    if t >= outfits.HOT_C and place == "base" and p.weight >= 2:
        return "too heavy for the heat"
    return "made for warmer days"


def _differing(offered: list[dict]) -> int:
    """How many of the offered outfits differ from each other in at least MIN_PIECES_DIFFERENT places."""
    kept: list[dict] = []
    for o in offered:
        if all(sum(o["pieces"][k] != c["pieces"][k] for k in outfits.PLACES) >= outfits.MIN_PIECES_DIFFERENT for c in kept):
            kept.append(o)
    return len(kept)


@dataclass
class _DayFailure:
    kind: str
    place: str
    want: tuple[str, str | None, str | None]
    day: Day
    pieces: list[outfits.Piece]   # the pieces the sentence is about
    goes_with: list[str]          # item ids of the rest of the best outfit
    detail: str = ""              # a reason or an engine sentence
    count: int = 0


def _run_grid(c: _Closet, days: list[Day] | None = None) -> tuple[list[_DayFailure], list[tuple[outfits.Piece, str, Day]], dict[str, int]]:
    """Run the engine over the grid. Returns failures, thin places (piece, place, day) and how often each item was used."""
    failures: list[_DayFailure] = []
    thin: list[tuple[outfits.Piece, str, Day]] = []
    used: dict[str, int] = {}
    pool = c.pieces
    outers_owned = [p for p in pool if _fills(p, "outer")]
    for d in grid() if days is None else days:
        ctx = outfits.Context(d.low_c, d.high_c, d.rain, d.occasion, mood=d.mood)
        t = outfits._design_temp(ctx)
        result = outfits.suggest(c.engine_items, ctx, DAY_OUTFITS)
        offered = result["outfits"]
        for o in offered:
            for pid in [o["pieces"][k] for k in outfits.PLACES] + list(o["pieces"]["accessories"]):
                if pid:
                    used[pid] = used.get(pid, 0) + 1
        if not offered:
            for place in ("base", "bottom", "shoes"):
                if not any(_fills(p, place) for p in pool):
                    failures.append(_DayFailure("none", place, _pick(place, d.occasion, d.band), d, [], []))
            continue
        strict = {place: [o.piece for o in outfits._options(pool, place, ctx, t, None, True)] for place in outfits.PLACES}
        best = offered[0]
        core = {place: c.by_id.get(best["pieces"][place]) if best["pieces"][place] else None for place in outfits.PLACES}
        ids = [p.id for p in core.values() if p is not None]

        def rest(skip: outfits.Piece | None, ids: list[str] = ids) -> list[str]:
            return [i for i in ids if skip is None or i != skip.id]

        for place, p in core.items():
            if p is not None and outfits._piece_problem(p, place, ctx, t):
                failures.append(_DayFailure("settle", place, _pick(place, d.occasion, d.band), d, [p], rest(p),
                                            _reason(p, place, ctx, t)))
        outer = core["outer"]
        clothes = [p for p in core.values() if p is not None]
        under = [p for p in clothes if p is not outer]
        problems = outfits._outfit_problems(clothes, under, outer)
        if problems:
            clash = outfits._formality_clash(under, outer)
            if clash:
                occ = vocab.FORMALITY.index(d.occasion)
                culprit = max(clash, key=lambda p: (abs(p.formality - occ), p.id))
            else:
                loud = [p for p in clothes if p.pattern in outfits.LOUD_PATTERNS or not outfits._neutral(p)]
                culprit = min(loud or clothes, key=lambda p: (len(strict[_place_of(core, p)]), p.id))
            place = _place_of(core, culprit)
            failures.append(_DayFailure("clash", place, _pick(place, d.occasion, d.band), d, [culprit], rest(culprit),
                                        problems[0]))

        accessories = [c.by_id[i] for i in best["pieces"]["accessories"] if i in c.by_id]
        warmth = sum(outfits._warmth(p, place) for place, p in core.items() if p is not None)
        warmth += sum(outfits._warmth(p, "accessory") for p in accessories)
        target = outfits._warmth_target(t)
        if warmth < target - outfits.WARMTH_TOLERANCE - outfits.WARMTH_NOTE_GAP:
            # the layer missing from the outfit: a coat on a cold day without one, else a sweater, else a warmer coat
            place = "outer" if (outer is None and t <= outfits.COLD_C) or core["mid"] is not None else "mid"
            warmest = max(outers_owned, key=lambda p: (outfits._warmth(p, "outer"), p.id), default=None)
            want = _pick("outer", d.occasion, "cold") if place == "outer" else ("sweater", PIECE_FORMALITY[d.occasion], "warm")
            failures.append(_DayFailure("cold", place, want, d, [warmest] if warmest else [], ids))
        elif warmth > target + outfits.WARMTH_TOLERANCE + outfits.WARMTH_NOTE_GAP:
            heavy = [(place, p) for place, p in core.items() if p is not None and place in ("base", "bottom")]
            place, p = max(heavy, key=lambda x: (outfits._warmth(x[1], x[0]) - outfits.WARMTH[x[0]][0], x[0]))
            failures.append(_DayFailure("warm", place, _pick(place, d.occasion, "hot"), d, [p], rest(p)))

        if d.rain and t < outfits.HOT_C:
            # a day fails for rain only when none of the outfits offered keeps it off: the owner can pick the second one
            offered_outers = [c.by_id.get(o["pieces"]["outer"]) for o in offered if o["pieces"]["outer"]]
            if not any(p is not None and outfits._rain_friendly(p) for p in offered_outers):
                friendly = [p for p in outers_owned if outfits._rain_friendly(p)]
                tag = "rainwarm" if friendly and t <= outfits.COLD_C else "rain"
                failures.append(_DayFailure("rain", "outer", ("coat", OUTER_FORMALITY, tag), d, friendly, rest(outer)))
            shoes = core["shoes"]
            if shoes is not None and (word := outfits._rain_unfriendly(shoes)):
                failures.append(_DayFailure("rain_shoes", "shoes", _pick("shoes", d.occasion, d.band), d, [shoes],
                                            rest(shoes), word))

        n = _differing(offered)
        if n < DAY_OUTFITS:
            needed = ["base", "bottom", "shoes"] + (["outer"] if t <= outfits.COLD_C and outers_owned else [])
            place = min(needed, key=lambda pl: (len(strict[pl]), needed.index(pl)))
            if strict[place]:  # with nothing that suits at all, the day is already a "settle" failure
                failures.append(_DayFailure("few", place, _pick(place, d.occasion, d.band), d, strict[place],
                                            [i for i in ids if i not in {p.id for p in strict[place]}], count=n))

        for place in ("base", "bottom", "shoes", "outer"):
            if place == "outer" and t > outfits.COLD_C:
                continue
            chosen = {o["pieces"][place] for o in offered}
            if len(chosen) != 1 or None in chosen:
                continue
            p = c.by_id.get(next(iter(chosen)))
            if p is None or outfits._piece_problem(p, place, ctx, t):
                continue
            others = [q for q in strict[place] if q.id != p.id]
            if place == "outer":
                others = [q for q in others if outfits._warmth(q, "outer") >= outfits._warmth(p, "outer") - THIN_WARMTH_SLACK]
            if not others:
                thin.append((p, place, d))
    return failures, thin, used


def _place_of(core: dict[str, outfits.Piece | None], p: outfits.Piece) -> str:
    return next(place for place, q in core.items() if q is p)


def _day_findings(failures: list[_DayFailure]) -> list[_Finding]:
    groups: dict[tuple, list[_DayFailure]] = {}
    for f in failures:
        groups.setdefault((f.kind, f.want, f.place), []).append(f)
    out = []
    for (kind, want, place), fs in sorted(groups.items(), key=lambda g: (g[0][0], str(g[0][1]), g[0][2])):
        days = [f.day for f in fs]
        weight = sum(f.day.weight * FAILURE_WEIGHT[kind] for f in fs)
        why = _day_why(kind, place, fs)
        items: list[str] = []
        for f in fs:
            items += [p.id for p in f.pieces] + f.goes_with
        material = None
        if kind == "rain_shoes":
            material = RAIN_SHOES_MATERIAL
        out.append(_Finding("days", want, place, why, min(DAY_SCORE_MAX, DAY_SCORE_PER_POINT * weight),
                            _levels(days), days, _unique(items), material=material))
    return out


def _day_why(kind: str, place: str, fs: list[_DayFailure]) -> list[str]:
    days = _days_words(f.day for f in fs)
    first = fs[0]
    if kind == "none":
        return [f"There are no {PLACE_NOUN[place][1]} in this closet, so no outfit can be made on {days}."]
    if kind == "settle" or kind == "clash":
        by_piece: dict[str, list[_DayFailure]] = {}
        for f in fs:
            by_piece.setdefault(f.pieces[0].id + "|" + f.detail, []).append(f)
        out = []
        for group in sorted(by_piece.values(), key=lambda g: (-len(g), g[0].pieces[0].id))[:2]:
            p, dw = group[0].pieces[0], _days_words(f.day for f in group)
            if kind == "settle":
                out.append(f"On {dw} the closet has nothing better than {_your(p)}, which {_be([p])} {group[0].detail}.")
            else:
                out.append(f"On {dw} nothing goes together cleanly: {group[0].detail}")
        return out
    if kind == "cold":
        if not first.pieces:
            return [f"You have no coat or jacket, so on {days} every outfit is too cold."]
        p = first.pieces[0]
        if place == "mid":
            return [f"On {days} the outfit is well short of warm even with {_your(p)}: no middle layer you own suits "
                    "those days to wear under it."]
        return [f"On {days} even {_your(p)}, your warmest outer layer, leaves the outfit well short of warm."]
    if kind == "warm":
        p = first.pieces[0]
        return [f"On {days} the lightest outfit the closet can make is still too warm: {_your(p)} {_be([p])} "
                f"the lightest {PLACE_NOUN[place][0 if not _plural(p) else 1]} that suit{'' if _plural(p) else 's'}."]
    if kind == "rain":
        friendly = first.pieces
        if not friendly:
            return [f"Nothing you own keeps the rain off; on {days} the engine can only say 'take an umbrella'."]
        names = _join([_your(p) for p in friendly[:2]])
        what = "warm enough" if first.want[2] == "rainwarm" else "right"
        return [f"Only {names} {_be(friendly[:2])} made for rain, and not {what} for {days}, "
                "so the engine can only say 'take an umbrella'."]
    if kind == "rain_shoes":
        p = first.pieces[0]
        return [f"On {days} the best shoes for the outfit are {_your(p)}, which {_be([p])} {first.detail} and "
                "do not like the rain."]
    # few
    pieces = _unique_pieces(p for f in fs for p in f.pieces)
    n = min(f.count for f in fs)
    noun = PLACE_NOUN[place][0 if len(pieces) == 1 and not _plural(pieces[0]) else 1]
    return [f"On {days} the closet can make only {NUMBER.get(n, str(n))} outfit{'' if n == 1 else 's'} that differ: "
            f"{_join([_your(p) for p in pieces[:3]])} {_be(pieces[:3])} the only {noun} that suit."]


def _thin_findings(thin: list[tuple[outfits.Piece, str, Day]]) -> list[_Finding]:
    groups: dict[tuple, list[tuple[outfits.Piece, str, Day]]] = {}
    for p, place, d in thin:
        want = _pick(place, d.occasion, d.band)
        groups.setdefault((p.id, place, want), []).append((p, place, d))
    out = []
    for (_pid, place, want), entries in sorted(groups.items(), key=lambda g: (g[0][0], g[0][1], str(g[0][2]))):
        p = entries[0][0]
        days = [d for _, _, d in entries]
        weight = sum(d.weight for d in days)
        it = "they" if _plural(p) else "it"
        noun = PLACE_NOUN[place][1 if _plural(p) else 0]
        why = [f"Every outfit for {_days_words(days)} rests on {_your(p)}: {it} {_be([p])} the only {noun} that suit"
               f"{'' if _plural(p) else 's'}. If {it} {_be([p])} in the wash or being mended, there is nothing to change to."]
        base = THIN_SCORE_BASE if days[0].situation is None else THIN_SCORE_BASE * min(1, weight / WEATHER_CELLS)
        score = min(THIN_SCORE_MAX, base + THIN_SCORE_PER_POINT * weight)
        out.append(_Finding("thin_place", want, place, why, score, _levels(days), days, [p.id],
                            first_color=p.color if want[0] == p.category else None))
    return out


# ====================================================================== orphans
def _orphan_findings(c: _Closet, used: dict[str, int]) -> list[_Finding]:
    out = []
    for p in c.pieces:
        place = HOME_PLACE.get(p.category)
        if place is None or used.get(p.id, 0) > ORPHAN_MAX_OUTFITS:
            continue
        for need in NEEDS[place]:
            candidates = [q for q in c.pieces if q.id != p.id and _fills(q, need)]
            if not candidates:
                continue  # the closet has none of these at all: the days find that
            fits = [q for q in candidates if not _pair_problems(p, place, q, need)]
            if len(fits) > ORPHAN_MAX_PARTNERS:
                continue
            reasons = {"formality": 0, "colour": 0, "pattern": 0}
            for q in candidates:
                for problem in _pair_problems(p, place, q, need):
                    reasons["formality" if "dressier" in problem else "colour" if "colour" in problem else "pattern"] += 1
            reason = max(reasons, key=lambda r: (reasons[r], r))
            words = {"formality": "too far from it in formality",
                     "colour": "a strong colour that competes with it",
                     "pattern": "patterned, and the two patterns fight"}[reason]
            occasion = vocab.FORMALITY[p.formality]
            band = "hot" if p.season == "warm" and need == "bottom" else "mild"
            want = _pick(need, occasion, band)
            plain = "plain " if reason != "formality" else ""
            noun = PLACE_NOUN[need][1]
            why = [f"{_cap(_your(p))} {_be([p])} in almost no outfit: every one of your {noun} is {words}. "
                   f"One {plain}piece in a neutral colour would bring {'them' if _plural(p) else 'it'} into use."]
            score = ORPHAN_SCORE + (ORPHAN_LOVED_BONUS if p.rating == "love" else 0)
            out.append(_Finding("orphan", want, need, why, score, (p.formality,), [], [p.id], solid=True))
            break
    return out


# ====================================================================== the wear log
def _wear_findings(c: _Closet) -> tuple[list[_Finding], list[dict]]:
    if c.wear_total < WEAR_MIN_LOG:
        return [], []
    out = []
    period = f"between {c.first_wear} and {c.last_wear}"
    for p in c.pieces:
        n = c.wear_counts.get(p.id, 0)
        if n < WEAR_HEAVY_MIN or p.category in outfits.ACCESSORY_CATEGORIES:
            continue
        others = [q for q in c.pieces if q.category == p.category and q.id != p.id]
        mean = sum(c.wear_counts.get(q.id, 0) for q in others) / len(others) if others else 0.0
        if n < WEAR_HEAVY_RATIO * mean:
            continue
        if any(q.color == p.color and q.formality == p.formality and q.pattern == p.pattern for q in others):
            continue  # a second one like it is already in the closet
        place = HOME_PLACE.get(p.category, "accessory")
        tag = None
        if place == "outer":
            tag = "warm" if p.category == "coat" and p.weight >= 2 else "rain" if outfits._rain_friendly(p) else None
        formality = OUTER_FORMALITY if place == "outer" else vocab.FORMALITY[p.formality]
        want = (p.category, formality, tag)
        kind = p.category.replace("_", " ")
        if others:
            compare = f"against {mean:.1f} on average for your other {kind}" + ("" if _plural(p) else "s")
        else:
            compare = f"and it is the only {kind} you have"
        why = [f"You wore {_your(p)} {n} times {period}, {compare}. A second one like "
               f"{'them' if _plural(p) else 'it'} would spread the wear."]
        score = min(WEAR_SCORE_MAX, WEAR_SCORE_BASE + WEAR_SCORE_PER_WEAR * (n - mean))
        thing = f"pair of {kind}" if _plural(p) else kind
        out.append(_Finding("worn_most", want, place, why, score, (p.formality,), [], [p.id], first_color=p.color,
                            name=f"Another {thing} like your {p.label}"))
    never = [p for p in c.pieces if not c.wear_counts.get(p.id)]
    notes = []
    if never:
        names = [_your(p) for p in never[:NEVER_WORN_NAMES]]
        more = len(never) - len(names)
        listed = _join(names + ([f"{more} more"] if more else []))
        notes.append({"kind": "never_worn", "items": [p.id for p in never],
                      "text": f"Not worn since the log began ({c.first_wear}): {listed}. They are not gaps, "
                              "but worth a look before buying more."})
    return out, notes


# ====================================================================== basics
def _basic_matches(b: Basic, p: outfits.Piece) -> bool:
    return (p.category in b.categories and (not b.colors or p.color in b.colors)
            and (b.min_formality is None or p.formality >= vocab.FORMALITY.index(b.min_formality))
            and (not b.solid or p.pattern == "solid") and (not b.rain or outfits._rain_friendly(p))
            and (b.min_weight is None or p.weight >= b.min_weight))


def _basic_findings(c: _Closet) -> list[_Finding]:
    out = []
    for b in BASICS:
        if any(_basic_matches(b, p) for p in c.pieces):
            continue
        why = [f"{b.why} You have none."]
        disliked = [p for p in c.disliked if _basic_matches(b, p)]
        if disliked:
            why = [f"{b.why} The only one you have, {_your(disliked[0])}, is rated dislike."]
        place = HOME_PLACE.get(b.want[0], "accessory")
        out.append(_Finding("basic", b.want, place, why, b.score, (vocab.FORMALITY.index(b.want[1] or "casual"),),
                            name=b.name))
    return out


# ====================================================================== merging
def _unique(ids: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(ids))


def _unique_pieces(pieces: Iterable[outfits.Piece]) -> list[outfits.Piece]:
    return list({p.id: p for p in pieces}.values())


def _levels(days: Iterable[Day]) -> tuple[int, ...]:
    return tuple(sorted({vocab.FORMALITY.index(d.occasion) for d in days}))


def _order(f: _Finding) -> tuple:
    return (-f.score, WAYS.index(f.way), f.why[0])


def _groups(findings: list[_Finding]) -> list[tuple[tuple[str, str | None, str | None], list[_Finding]]]:
    """Findings that one purchase would meet, with that purchase.

    Within a family (category and tag), findings are grouped while one formality can serve every occasion
    they are needed for: within OCCASION_REACH of each, as the engine asks. The best finding is placed first.
    """
    families: dict[tuple, list[_Finding]] = {}
    for f in findings:
        families.setdefault(_family(f.want), []).append(f)
    out = []
    reach = outfits.OCCASION_REACH
    for family in sorted(families, key=str):
        fs = sorted(families[family], key=_order)
        if family[0] == "outer":
            out.append((fs[0].want, fs))
            continue
        clusters: list[tuple[set[int], list[_Finding]]] = []
        for f in fs:
            for levels, members in clusters:
                both = levels | set(f.occasions)
                if max(both) - min(both) <= 2 * reach:
                    levels |= set(f.occasions)
                    members.append(f)
                    break
            else:
                clusters.append((set(f.occasions), [f]))
        for levels, members in clusters:
            top = vocab.FORMALITY.index(members[0].want[1] or "casual")
            level = min(max(top, max(levels) - reach), min(levels) + reach)
            out.append(((family[0], vocab.FORMALITY[level], family[1]), members))
    return out


def _merge(findings: list[_Finding], c: _Closet) -> list[dict]:
    gaps = []
    for want, fs in _groups(findings):
        top = fs[0]
        score = min(SCORE_CAP, top.score + MERGE_SHARE * sum(f.score for f in fs[1:]))
        why = _unique(s for f in fs for s in f.why)[:WHY_MAX]
        days = sorted({d for f in fs for d in f.days}, key=_day_order)
        items = [i for i in _unique(i for f in fs for i in f.items) if i in c.by_id]
        category, formality, tag = want
        key = _family(want) if category in outfits.PLACE_CATEGORIES["outer"] else want
        place = top.place
        first_color = next((f.first_color for f in fs if f.first_color), None)
        colors = _colors(want, place, [c.by_id[i] for i in items], c, first_color)
        if len(items) < EVIDENCE_FILL_TO:
            items = _unique(items + _goes_with(want, place, colors[0] if colors else None, c))
        look = {"category": category, "formality": formality, "season": None, "weight_class": None,
                "colors": colors, "pattern": "solid" if any(f.solid for f in fs) else None, "material": None}
        look.update(CATEGORY_LOOK.get(category, {}))
        look.update(TAG_LOOK.get(tag or "", {}))
        look["material"] = look["material"] or next((f.material for f in fs if f.material), None)
        name = top.name if top.name and top.want == want else _name(want)
        gaps.append({
            "id": "-".join(str(k) for k in key if k),
            "name": name,
            "look_for": look,
            "why": why,
            "score": int(round(score)),
            "found_by": [w for w in WAYS if any(f.way == w for f in fs)],
            "evidence": {"days": [d.as_dict() for d in days], "items": items[:EVIDENCE_ITEMS_MAX]},
        })
    names = [g["name"] for g in gaps]
    for g in gaps:
        formality = g["look_for"]["formality"]
        if names.count(g["name"]) > 1 and formality:
            g["name"] += f" for {OCCASION_ADJ[formality]} days"
    gaps.sort(key=lambda g: (-g["score"], g["name"], g["id"]))
    return gaps


def _colors(want: tuple, place: str, around: list[outfits.Piece], c: _Closet, first: str | None) -> list[str]:
    """Colours to look for: neutrals that go with the items in the evidence, ones not owned in this category first."""
    category = want[0]
    candidates = list(COLOR_PICKS.get(category, outfits.NEUTRALS[:3]))
    if first and first in vocab.COLOR and first not in candidates:
        candidates.insert(0, first)
    owned = {p.color for p in c.pieces if p.category == category}

    def rank(color: str) -> tuple:
        probe = _probe(want, color)
        fits = sum(1 for q in around if q.category != category and not outfits._outfit_problems([probe, q], []))
        return (color != first, -fits, color in owned and color != first, candidates.index(color))

    return sorted(candidates, key=rank)[:COLORS_MAX]


def _goes_with(want: tuple, place: str, color: str | None, c: _Closet) -> list[str]:
    """Owned items the piece would go with: in the places it is worn with, by the engine's rules between pieces."""
    probe = _probe(want, color)
    out = []
    for need in NEEDS.get(place, ()):
        fits = [q for q in c.pieces if _fills(q, need) and q.category not in outfits.ACCESSORY_CATEGORIES
                and not _pair_problems(probe, place, q, need)]
        fits.sort(key=lambda q: (-c.wear_counts.get(q.id, 0), q.rating != "love", q.id))
        out += [q.id for q in fits[:2]]
    return out


# ====================================================================== entry point
def find_gaps(items: Iterable[object], wears: Iterable[object] = (), options: Options | Mapping | None = None) -> dict:
    """What's missing from the closet, best first.

    Returns {"enough": bool, "message": sentence or None, "gaps": [gap], "notes": [{kind, text, items}],
    "checked": {items, wears, days}}. Each gap: {id, name, look_for: {category, formality, season, weight_class,
    colors, pattern, material}, why: [sentences], score: 0-100, found_by: [ways], evidence: {days: [...], items: [ids]}}.
    """
    if options is None:
        opts = Options()
    elif isinstance(options, Options):
        opts = options
    else:
        opts = Options(**{k: v for k, v in dict(options).items() if k in Options.__dataclass_fields__})
    c = _closet(list(items), list(wears))
    clothes = [p for p in c.pieces + c.disliked if p.category not in outfits.ACCESSORY_CATEGORIES]
    checked = {"items": len(c.pieces) + len(c.disliked), "wears": c.wear_total, "days": 0}
    if not clothes:
        return {"enough": False, "message": "The closet is empty, so there is nothing to judge yet. Add some clothes first.",
                "gaps": [], "notes": [], "checked": checked}
    if len(clothes) < MIN_ITEMS:
        return {"enough": False,
                "message": f"With {NUMBER.get(len(clothes), str(len(clothes)))} piece{'' if len(clothes) == 1 else 's'} of "
                           f"clothing the closet is too small to say what is missing: nearly everything is. "
                           f"Add at least {MIN_ITEMS} and look again.",
                "gaps": [], "notes": [], "checked": checked}

    failures, thin, used = _run_grid(c)
    checked["days"] = len(grid())
    wear_found, notes = _wear_findings(c)
    findings = _day_findings(failures) + _thin_findings(thin) + _orphan_findings(c, used) + wear_found + _basic_findings(c)
    gaps = _merge(findings, c)
    return {"enough": True, "message": None, "gaps": gaps[:max(0, int(opts.max_gaps))], "notes": notes, "checked": checked}
