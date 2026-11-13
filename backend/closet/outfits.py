"""Today's outfits, chosen by rule.

Pure functions: no database, no network, no clock. `suggest(items, context,
count)` takes the closet's items (as `GET /api/items/{id}` returns them) and
the day, and returns ranked outfits with a score and reasons in plain words.
The same inputs always give the same outfits in the same order.

How it works: every usable item is offered for the places it can fill (base
top, mid layer, outer layer, bottom, shoes). Pieces that break a rule for the
day (a hoodie on a business day, shorts at 5°C) are left out; the best few
for each place are combined; combinations that break a rule between pieces
(layering order, formality spread, two strong colours, two loud patterns) are
dropped; the rest are scored and the best that differ from each other are
offered, with accessories added last. If the strict rules leave nothing, the
search is run again with the rules turned into penalties and a warning for
each one broken, so a small closet still gets an answer.
"""
from __future__ import annotations

import colorsys
import itertools
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from . import vocab

# ------------------------------------------------------------------ temperature
DESIGN_TEMP_SHARE = 0.3      # the temperature dressed for: the low plus this share of the way to the high (a layer is easier to take off than to find)
HOT_C = 24                   # at or above: no mid or outer layer, no cool-season pieces, no heavy tops
COLD_C = 8                   # at or below: an outer layer whenever the closet has one; warm-season pieces only as a covered base
WARM_SEASON_MIN_C = 14       # below this, warm-season pieces cost SEASON_PENALTY (half when they are a covered base)
COOL_SEASON_MAX_C = 20       # above this, cool-season pieces cost SEASON_PENALTY
SHORTS_MIN_C = 18            # no shorts below this
SANDALS_MIN_C = 20           # no sandals below this (nor in rain)
SCARF_MAX_C = 8              # a scarf is added at or below this
HAT_MAX_C = 4                # a hat is added at or below this

# How warm an outfit should be, in "warmth points" (a midweight tee is 1, a heavy overcoat 5):
# target = WARMTH_TARGET_AT_0C - WARMTH_TARGET_PER_C * temperature, never below WARMTH_TARGET_MIN.
WARMTH_TARGET_AT_0C = 13.2   # about a shirt, a heavy sweater, an overcoat, trousers and a scarf
WARMTH_TARGET_PER_C = 0.45   # about one point less for every 2°C warmer
WARMTH_TARGET_MIN = 1.0      # a light tee and shorts
WARMTH_TOLERANCE = 1.0       # this far either side of the target costs nothing
WARMTH_SHORT_PER_POINT = 5   # score lost per point too cold beyond the tolerance
WARMTH_EXCESS_PER_POINT = 3  # score lost per point too warm beyond the tolerance (layers come off; cold is worse)
HOT_EXCESS_PER_POINT = 8     # the same at or above HOT_C, where nothing can come off
WARMTH_NOTE_GAP = 2.0        # beyond the tolerance by more than this, the owner is told

# Warmth points by place and weight class (lightweight, midweight, heavyweight, super_heavy).
WARMTH = {
    "base": (1.0, 1.5, 2.0, 2.5),
    "mid": (1.5, 2.0, 3.0, 4.0),
    "outer": (1.5, 2.5, 3.5, 5.0),
    "bottom": (0.5, 1.0, 1.5, 2.0),
}
LONG_SLEEVE_WARMTH = 1.0     # added for a long-sleeved base top
HOT_LONG_SLEEVE_PENALTY = 4  # a long-sleeved base top at or above HOT_C
SHORTS_WARMTH = 0.0          # shorts, whatever their cloth
ACCESSORY_WARMTH = {"scarf": 1.0, "hat": 0.5}

# ------------------------------------------------------------------ weight
WEIGHT_CLASSES = ("lightweight", "midweight", "heavyweight", "super_heavy")
# Weight class (0-3) assumed from the category when the item has none and its material and name say nothing.
CATEGORY_WEIGHT = {"tee": 1, "shirt": 1, "polo": 1, "sweater": 1, "hoodie": 2, "jacket": 2, "coat": 3,
                   "jeans": 2, "trousers": 1, "shorts": 0}
WARM_SEASON_LIGHTER = 1      # a warm-season item with no other clue is taken as this many classes lighter
# Words in the material (looked at first) or the name that give the weight class; the first match wins,
# so specific words come before generic fibres ("merino wool" is midweight, not heavyweight).
WEIGHT_WORDS = (
    ("merino", 1), ("cashmere", 1), ("linen", 0), ("seersucker", 0), ("madras", 0), ("poplin", 0), ("voile", 0),
    ("silk", 0), ("mesh", 0), ("windbreaker", 0),
    ("fleece", 3), ("sherpa", 3), ("melton", 3), ("shearling", 3), ("puffer", 3), ("parka", 3), ("overcoat", 3),
    ("topcoat", 3), ("peacoat", 3), ("chunky", 3), ("aran", 3),
    ("flannel", 2), ("denim", 2), ("corduroy", 2), ("cord", 2), ("cords", 2), ("moleskin", 2), ("canvas", 2),
    ("duck", 2), ("tweed", 2), ("cable", 2), ("sweatshirt", 2), ("leather", 2), ("suede", 2), ("waxed", 2),
    ("chore", 2), ("quilted", 2),
    ("oxford", 1), ("chambray", 1), ("jersey", 1), ("henley", 1), ("bomber", 1), ("trench", 1), ("mac", 1),
    ("raincoat", 1), ("nylon", 1),
    ("wool", 2), ("cotton", 1),
)
OVERSIZED_BULK = 1           # an oversized fit counts as this many classes bulkier when layering
BASE_UNDER_ANYTHING_MAX = 1  # a base top this light (weight 0-1: midweight or lighter) and not oversized goes under anything

# ------------------------------------------------------------------ places
PLACES = ("base", "mid", "outer", "bottom", "shoes")
PLACE_CATEGORIES = {
    "base": ("tee", "shirt", "polo"),
    "mid": ("sweater", "hoodie", "shirt", "jacket"),  # a shirt only over a tee; a jacket only under a coat
    "outer": ("jacket", "coat"),
    "bottom": ("jeans", "trousers", "shorts"),
    "shoes": ("sneakers", "boots", "dress_shoes", "sandals"),
}
ACCESSORY_CATEGORIES = ("belt", "scarf", "hat", "bag")
CANDIDATES_PER_PLACE = 6     # the best this many pieces per place are combined (plus the warmest and lightest)

# ------------------------------------------------------------------ formality
FORMALITY = vocab.FORMALITY
# Formality assumed from the category when the item has none.
CATEGORY_FORMALITY = {"tee": "casual", "polo": "smart_casual", "shirt": "smart_casual", "sweater": "smart_casual",
                      "hoodie": "casual", "jacket": "casual", "coat": "smart_casual", "jeans": "casual",
                      "trousers": "smart_casual", "shorts": "casual", "sneakers": "casual", "boots": "smart_casual",
                      "dress_shoes": "business", "sandals": "casual",
                      "belt": "smart_casual", "scarf": "smart_casual", "hat": "casual", "bag": "smart_casual"}
# Categories never worn to an occasion, whatever their own formality says.
OCCASION_BANNED = {
    "business": ("hoodie", "sneakers", "sandals", "shorts"),
    "formal": ("hoodie", "sneakers", "sandals", "shorts", "tee", "polo", "jeans"),
}
OCCASION_REACH = 1           # each piece sits within this many steps of the occasion
FORMALITY_SPREAD = 1         # and within this many steps of each other
OUTER_REACH = 2              # an outer layer may sit this far from the occasion and the rest (a good coat goes over jeans)
MOODS = {"usual": 0.0, "sharp": 0.5, "relaxed": -0.5}  # how far the mood moves the formality aimed for
FORMALITY_PER_STEP = 4       # score lost per step a piece is from the formality aimed for

# ------------------------------------------------------------------ colour and pattern
NEUTRALS = ("black", "white", "grey", "navy", "tan", "brown", "cream", "olive", "light_blue")
DENIM_CATEGORIES = ("jeans",)  # blue jeans count as neutral
COLOR_FAMILY = {"red": "red", "burgundy": "red", "pink": "red", "orange": "orange", "yellow": "yellow",
                "green": "green", "olive": "green", "blue": "blue", "light_blue": "blue", "navy": "blue",
                "purple": "purple"}
TONAL_HUE_DEGREES = 25       # two strong colours whose stored hues are this close count as tonal
LOUD_PATTERNS = ("plaid", "floral", "camo", "graphic", "other")
MAX_PATTERNED = 2            # at most this many patterned pieces (of which at most one loud)
ACCENT_BONUS = 2             # neutrals with exactly one colour
ALL_NEUTRAL_BONUS = 1        # all neutrals
BELT_MATCH_BONUS = 2         # a belt the colour of the shoes

# ------------------------------------------------------------------ preference and variety
SEASON_PENALTY = 6           # a piece out of its season (see WARM_SEASON_MIN_C and COOL_SEASON_MAX_C)
RATING_SCORE = {"love": 4, "like": 1.5, "meh": -4}  # added per piece; "dislike" is never chosen
RECENT_WEAR_DAYS = 4         # worn fewer than this many days ago costs RECENT_WEAR_PENALTY, less each day
RECENT_WEAR_PENALTY = 8      # for a piece worn today; yesterday costs 3/4 of it, and so on
RECENT_WEAR_OTHER_SHARE = 0.5  # share of that for bottoms, outer layers, shoes and accessories (worn again more often)
STORAGE_PENALTY = 2          # a piece put away in storage has to be got out first
MIN_PIECES_DIFFERENT = 2     # outfits offered differ by at least this many pieces where the closet allows
OVERLAP_PENALTY = 4          # when choosing the next outfit to offer, per piece it shares with one already offered

# ------------------------------------------------------------------ rain
RAIN_UNFRIENDLY_WORDS = ("suede", "canvas", "linen", "silk")  # shoes or outer layers that soak or stain
RAIN_FRIENDLY_WORDS = ("waxed", "rain", "raincoat", "mac", "trench", "parka", "nylon", "shell", "waterproof", "gore")
RAIN_UNFRIENDLY_PENALTY = 8
RAIN_BOOTS_BONUS = 2
RAIN_OUTER_BONUS = 2         # any outer layer in rain
RAIN_FRIENDLY_BONUS = 3      # an outer layer that sheds water

# ------------------------------------------------------------------ score
SCORE_START = 80             # an outfit that breaks nothing and has nothing special scores this
PIECE_PROBLEM_PENALTY = 20   # only when the strict rules left nothing: per piece that breaks a rule for the day
OUTFIT_PROBLEM_PENALTY = 15  # likewise, per rule broken between pieces
OUTER_MISSING_PENALTY = 10   # likewise, no outer layer in the cold when one exists

# ------------------------------------------------------------------ what the owner said about outfits worn (see Feedback)
OUTFIT_RATINGS = ("loved", "fine", "not_again")
OUTFIT_REASONS = ("too_warm", "too_cold", "too_dressy", "too_casual", "colours_clashed", "uncomfortable", "compliments", "other")
LOVED_PAIR_BONUS = 1.0       # per pair of pieces worn together in an outfit rated "loved it" (or that got compliments)
LOVED_MAX_BONUS = 4.0        # at most this much in all: about one loved piece, so "a little more likely", never a rule
AVOID_PAIR_PENALTY = 3.0     # per pair of pieces that were the problem in an outfit rated "not again"
AVOID_MAX_PENALTY = 9.0      # at most this much in all: the pair is less likely, not banned (the exact outfit is)
SIMILAR_DAY_C = 4.0          # "too warm" or "too cold" counts when that day was dressed for within this many °C of today
WARMTH_SHIFT_PER_RATING = 0.5  # warmth points added to the target per "too cold" on a similar day (taken off per "too warm")
WARMTH_SHIFT_MAX = 1.5       # never more than this either way: about 3°C of dressing, the bound on what ratings can do
MONTH_WORDS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December")

DEFAULT_COUNT = 3
MAX_COUNT = 10
TEMP_RANGE_C = (-50, 55)


class ContextError(ValueError):
    """A request the engine cannot work with, in words the owner can read."""


@dataclass(frozen=True)
class Context:
    low_c: float
    high_c: float
    rain: bool = False
    occasion: str = "casual"
    mood: str = "usual"
    build_around: str | None = None
    leave_out: tuple[str, ...] = ()
    worn_days_ago: Mapping[str, int] = field(default_factory=dict)
    keep: tuple[str, ...] = ()       # pieces every outfit must hold (wearing an outfit again); not taken from requests


@dataclass(frozen=True)
class Remembered:
    """What one rated outfit taught: its pieces, the pairs of them that count, and the day it was worn."""
    day: str                                   # YYYY-MM-DD
    kind: str                                  # "loved", "compliments" or "not_again"
    pieces: frozenset[str]
    pairs: frozenset[frozenset[str]]


@dataclass(frozen=True)
class Feedback:
    """What the owner's ratings of outfits worn before ask of today's outfits. Made by `feedback_from`.

    `liked`: pieces worn together in an outfit loved (or that got compliments), a little more likely together again.
    `avoided`: the pairs that were the problem in an outfit rated "not again", less likely together again.
    `not_again`: outfits rated "not again", as (base, mid, outer, bottom, shoes) ids ("" for none) -> the day; never offered as they were.
    `warmth_shift`: warmth points added to (or, below 0, taken off) the target, from "too cold" and "too warm" on days like today.
    """
    liked: tuple[Remembered, ...] = ()
    avoided: tuple[Remembered, ...] = ()
    not_again: Mapping[tuple[str, ...], str] = field(default_factory=dict)
    warmth_shift: float = 0.0
    warmth_day: str | None = None              # the latest rating behind the shift


def parse_request(data: object) -> tuple[Context, int]:
    """Check a request body and turn it into a Context and a count. Raises ContextError."""
    if not isinstance(data, dict):
        raise ContextError("Send the day as an object, for example {\"low_c\": 5, \"high_c\": 12}.")
    known = {"low_c", "high_c", "rain", "occasion", "mood", "build_around", "leave_out", "worn_days_ago", "count"}
    unknown = sorted(set(data) - known)
    if unknown:
        raise ContextError(f"These are not part of a day: {', '.join(unknown)}.")

    def temp(key: str, words: str) -> float:
        v = data.get(key)
        if v is None:
            raise ContextError(f"Give the day's {words} temperature in °C.")
        if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v):
            raise ContextError(f"The {words} temperature must be a number of degrees Celsius.")
        if not TEMP_RANGE_C[0] <= v <= TEMP_RANGE_C[1]:
            raise ContextError(f"A {words} of {v}°C is not a temperature this app plans for.")
        return float(v)

    low, high = temp("low_c", "low"), temp("high_c", "high")
    if low > high:
        raise ContextError("The low temperature is above the high one.")
    rain = data.get("rain", False)
    if not isinstance(rain, bool):
        raise ContextError("Rain must be true or false.")
    occasion = data.get("occasion") or "casual"
    if occasion not in FORMALITY:
        raise ContextError(f"'{occasion}' is not an occasion. Choose one of: {', '.join(FORMALITY)}.")
    mood = data.get("mood") or "usual"
    if mood not in MOODS:
        raise ContextError(f"'{mood}' is not a mood. Choose one of: {', '.join(MOODS)}.")
    around = data.get("build_around")
    if around is not None and (not isinstance(around, str) or not around.strip()):
        raise ContextError("The item to build around must be an item id.")
    leave = data.get("leave_out") or []
    if not isinstance(leave, list) or not all(isinstance(x, str) for x in leave):
        raise ContextError("Items to leave out must be a list of item ids.")
    if around and around in leave:
        raise ContextError("The item to build around is also in the list to leave out.")
    worn = data.get("worn_days_ago") or {}
    if not isinstance(worn, dict) or not all(
            isinstance(k, str) and isinstance(v, int) and not isinstance(v, bool) and v >= 0 for k, v in worn.items()):
        raise ContextError("When items were last worn must be an object of item id to a whole number of days ago, 0 or more.")
    count = data.get("count", DEFAULT_COUNT)
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= MAX_COUNT:
        raise ContextError(f"Count must be a whole number from 1 to {MAX_COUNT}.")
    ctx = Context(low, high, rain, occasion, mood, around.strip() if around else None, tuple(leave), dict(worn))
    return ctx, count


# ====================================================================== pieces
@dataclass(frozen=True)
class Piece:
    id: str
    label: str
    category: str
    color: str | None
    hue: float | None          # degrees, from color_hex, only for clearly coloured hexes
    pattern: str
    formality: int
    season: str
    weight: int
    bulk: int
    long_sleeve: bool
    rating: str | None
    in_storage: bool
    words: tuple[str, ...]     # material and name, as lower-case words


def _words(text: object) -> tuple[str, ...]:
    return tuple(re.findall(r"[a-z]+", str(text).lower())) if text else ()


def _label(item: dict) -> str:
    name = str(item.get("name") or "").strip()
    if not name:
        parts = [item.get("color"), item.get("category")]
        name = " ".join(str(p).replace("_", " ") for p in parts if p) or "item"
    if len(name) > 1 and not name[1].isupper():
        name = name[0].lower() + name[1:]
    return name


def _hue(hex_value: object) -> float | None:
    if not isinstance(hex_value, str) or not re.fullmatch(r"#?[0-9a-fA-F]{6}", hex_value.strip()):
        return None
    h = hex_value.strip().lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    hue, light, sat = colorsys.rgb_to_hls(r, g, b)
    return hue * 360 if sat > 0.2 and 0.1 < light < 0.9 else None


def _weight(item: dict, category: str, words_material: tuple[str, ...], words_name: tuple[str, ...]) -> int:
    for key in ("weight_class", "weight"):
        if item.get(key) in WEIGHT_CLASSES:
            return WEIGHT_CLASSES.index(item[key])
    for words in (words_material, words_name):
        for word, level in WEIGHT_WORDS:
            if word in words:
                return level
    level = CATEGORY_WEIGHT.get(category, 1)
    if item.get("season") == "warm":
        level = max(0, level - WARM_SEASON_LIGHTER)
    return level


def _in_laundry(item: dict) -> bool:
    return item.get("location") == "laundry" or item.get("laundry") not in (None, "", "clean", False)


def _piece(item: dict) -> Piece | None:
    category = item.get("category")
    if not item.get("id") or not isinstance(category, str) or category not in CATEGORY_FORMALITY:
        return None
    sil = item.get("silhouette") or {}
    if not isinstance(sil, dict):
        sil = {}
    mat, name = _words(item.get("material")), _words(item.get("name"))
    weight = _weight(item, category, mat, name)
    formality = item.get("formality") if item.get("formality") in FORMALITY else CATEGORY_FORMALITY.get(category, "casual")
    sleeve = sil.get("sleeve")
    long_sleeve = sleeve == "long" if sleeve else category in ("shirt", "sweater", "hoodie", "jacket", "coat")
    return Piece(
        id=str(item["id"]), label=_label(item), category=category,
        color=item.get("color") if item.get("color") in vocab.COLOR else None, hue=_hue(item.get("color_hex")),
        pattern=item.get("pattern") if item.get("pattern") in vocab.PATTERN else "solid",
        formality=FORMALITY.index(formality), season=item.get("season") if item.get("season") in vocab.SEASON else "all",
        weight=weight, bulk=weight + (OVERSIZED_BULK if sil.get("fit") == "oversized" else 0), long_sleeve=long_sleeve,
        rating=item.get("rating") if item.get("rating") in vocab.RATING else None, in_storage=item.get("location") == "storage", words=mat + name)


# ====================================================================== words
OCCASION_WORDS = {"athletic": "sport", "casual": "a casual day", "smart_casual": "a smart casual day",
                  "business": "a business day", "formal": "a formal occasion"}
LEVEL_WORDS = {"athletic": "sporty", "casual": "casual", "smart_casual": "smart casual", "business": "business",
               "formal": "formal"}
FAMILY_WORDS = {"red": "reds", "orange": "oranges", "yellow": "yellows", "green": "greens", "blue": "blues",
                "purple": "purples"}
NUMBER_WORDS = {2: "Two", 3: "Three", 4: "Four"}


def _deg(v: float) -> str:
    return f"{v:.0f}°C" if float(v).is_integer() else f"{v:.1f}°C"


def _temp_words(ctx: Context) -> str:
    return _deg(ctx.low_c) if ctx.low_c == ctx.high_c else f"{_deg(ctx.low_c)} to {_deg(ctx.high_c)}"


def _the(p: Piece, cap: bool = False) -> str:
    return ("The " if cap else "the ") + p.label


def _join(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _days_words(d: int) -> str:
    return "today" if d == 0 else "yesterday" if d == 1 else f"{d} days ago"


# ====================================================================== rules
def _design_temp(ctx: Context) -> float:
    return ctx.low_c + DESIGN_TEMP_SHARE * (ctx.high_c - ctx.low_c)


def _warmth_target(t: float) -> float:
    return max(WARMTH_TARGET_MIN, WARMTH_TARGET_AT_0C - WARMTH_TARGET_PER_C * t)


def _warmth(p: Piece, place: str) -> float:
    if place == "bottom" and p.category == "shorts":
        return SHORTS_WARMTH
    if place in WARMTH:
        return WARMTH[place][p.weight] + (LONG_SLEEVE_WARMTH if place == "base" and p.long_sleeve else 0)
    return ACCESSORY_WARMTH.get(p.category, 0.0)


def _formality_off(p: Piece, place: str, occasion: str) -> int:
    """-1 if the piece is too casual for the occasion, 1 if too dressy, 0 if it fits."""
    occ = FORMALITY.index(occasion)
    reach = OUTER_REACH if place == "outer" else OCCASION_REACH
    if p.category in OCCASION_BANNED.get(occasion, ()) or p.formality < occ - reach:
        return -1
    return 1 if p.formality > occ + reach else 0


def _piece_problem(p: Piece, place: str, ctx: Context, t: float) -> str | None:
    """Why this piece is wrong for the day in this place, as a sentence; None if it is fine."""
    off = _formality_off(p, place, ctx.occasion)
    if off < 0:
        return f"{_the(p, True)} is more casual than {OCCASION_WORDS[ctx.occasion]} calls for."
    if off > 0:
        return f"{_the(p, True)} is dressier than {OCCASION_WORDS[ctx.occasion]} calls for."
    if p.category == "shorts" and t < SHORTS_MIN_C:
        return f"It is too cold for shorts at {_temp_words(ctx)}."
    if p.category == "sandals" and ctx.rain:
        return "Sandals are no good in the rain."
    if p.category == "sandals" and t < SANDALS_MIN_C:
        return f"It is too cold for sandals at {_temp_words(ctx)}."
    if t >= HOT_C and p.season == "cool":
        return f"{_the(p, True)} is made for cooler days than {_temp_words(ctx)}."
    if t >= HOT_C and place == "base" and p.weight >= 2:
        return f"{_the(p, True)} is too heavy for {_temp_words(ctx)}."
    if t <= COLD_C and p.season == "warm" and place != "base":
        return f"{_the(p, True)} is made for warmer days than {_temp_words(ctx)}."
    return None


def _rain_unfriendly(p: Piece) -> str | None:
    return next((w for w in RAIN_UNFRIENDLY_WORDS if w in p.words), None)


def _rain_friendly(p: Piece) -> bool:
    return any(w in p.words for w in RAIN_FRIENDLY_WORDS)


def _piece_score(p: Piece, place: str, ctx: Context, t: float) -> float:
    """Everything about a piece that does not depend on the rest of the outfit."""
    target = FORMALITY.index(ctx.occasion) + MOODS[ctx.mood]
    s = -FORMALITY_PER_STEP * abs(p.formality - target)
    s += RATING_SCORE.get(p.rating or "", 0)
    days = ctx.worn_days_ago.get(p.id)
    if days is not None and days < RECENT_WEAR_DAYS:
        share = 1.0 if place in ("base", "mid") else RECENT_WEAR_OTHER_SHARE
        s -= RECENT_WEAR_PENALTY * share * (RECENT_WEAR_DAYS - days) / RECENT_WEAR_DAYS
    if p.season == "warm" and t < WARM_SEASON_MIN_C:
        s -= SEASON_PENALTY * (0.5 if place == "base" else 1.0)
    if p.season == "cool" and t > COOL_SEASON_MAX_C:
        s -= SEASON_PENALTY
    if p.in_storage:
        s -= STORAGE_PENALTY
    if place == "base" and p.long_sleeve and t >= HOT_C:
        s -= HOT_LONG_SLEEVE_PENALTY
    if ctx.rain and place in ("shoes", "outer"):
        if _rain_unfriendly(p):
            s -= RAIN_UNFRIENDLY_PENALTY
        if place == "shoes" and p.category == "boots":
            s += RAIN_BOOTS_BONUS
        if place == "outer":
            s += RAIN_OUTER_BONUS + (RAIN_FRIENDLY_BONUS if _rain_friendly(p) else 0)
    return s


def _layers_ok(base: Piece, mid: Piece | None, outer: Piece | None) -> bool:
    """Nothing is worn over something heavier or bulkier than itself."""
    if mid is not None:
        if mid.category == "shirt" and base.category != "tee":
            return False
        if mid.category == "jacket" and (outer is None or outer.category != "coat"):
            return False
    stack = [p for p in (base, mid, outer) if p is not None]
    return all(a.weight <= b.weight and a.bulk <= b.bulk for a, b in itertools.pairwise(stack)
               if not (a is base and base.weight <= BASE_UNDER_ANYTHING_MAX and base.bulk == base.weight))


def _neutral(p: Piece) -> bool:
    return p.color is None or p.color in NEUTRALS or (p.category in DENIM_CATEGORIES and p.color == "blue")


def _tonal(a: Piece, b: Piece) -> bool:
    if a.color == "multi" or b.color == "multi":
        return False
    if COLOR_FAMILY.get(a.color or "") == COLOR_FAMILY.get(b.color or "") and a.color in COLOR_FAMILY:
        return True
    if a.hue is not None and b.hue is not None:
        d = abs(a.hue - b.hue) % 360
        return min(d, 360 - d) <= TONAL_HUE_DEGREES
    return False


def _formality_clash(clothes: list[Piece], outer: Piece | None) -> tuple[Piece, Piece] | None:
    """Two pieces too far apart in formality (the outer layer is allowed further), or None."""
    lo = min(clothes, key=lambda p: (p.formality, p.id))
    hi = max(clothes, key=lambda p: (p.formality, p.id))
    if hi.formality - lo.formality > FORMALITY_SPREAD:
        return hi, lo
    if outer is not None:
        for p in clothes:
            if abs(outer.formality - p.formality) > OUTER_REACH:
                return (outer, p) if outer.formality > p.formality else (p, outer)
    return None


def _outfit_problems(pieces: list[Piece], clothes: list[Piece], outer: Piece | None = None) -> list[str]:
    """Rules between pieces: formality spread, colour, pattern. Sentences; empty when all is well.

    `clothes` are the pieces under the outer layer (and the shoes), whose formality must sit close together.
    """
    out = []
    clash = _formality_clash(clothes, outer) if clothes else None
    if clash:
        out.append(f"{_the(clash[0], True)} is a lot dressier than {_the(clash[1])}.")
    strong = [p for p in pieces if not _neutral(p)]
    for a, b in itertools.combinations(strong, 2):
        if not _tonal(a, b):
            out.append(f"{_the(a, True)} and {_the(b)} are two strong colours that compete.")
            break
    loud = [p for p in pieces if p.pattern in LOUD_PATTERNS]
    patterned = [p for p in pieces if p.pattern != "solid"]
    if len(loud) > 1:
        out.append(f"{_the(loud[0], True)} and {_the(loud[1])} are two bold patterns together.")
    elif len(patterned) > MAX_PATTERNED:
        out.append(f"{_join([_the(p) for p in patterned]).capitalize()} are too many patterns at once.")
    return out


# ====================================================================== search
@dataclass(frozen=True)
class _Option:
    piece: Piece
    place: str
    score: float
    warmth: float
    problem: str | None


@dataclass
class _Outfit:
    base: _Option
    mid: _Option | None
    outer: _Option | None
    bottom: _Option
    shoes: _Option
    raw: float
    problems: list[str]
    accessories: list[_Option] = field(default_factory=list)

    def core(self) -> list[_Option]:
        return [o for o in (self.base, self.mid, self.outer, self.bottom, self.shoes) if o is not None]

    def ids(self) -> tuple[str, ...]:
        return tuple(o.piece.id if o else "" for o in (self.base, self.mid, self.outer, self.bottom, self.shoes))


def _options(pool: list[Piece], place: str, ctx: Context, t: float, forced: tuple[Piece, str] | None,
             strict: bool) -> list[_Option]:
    out = []
    for p in pool:
        if p.category not in PLACE_CATEGORIES[place]:
            continue
        if forced is not None:
            if forced[0].id == p.id and forced[1] != place:
                continue
            if forced[1] == place and forced[0].id != p.id:
                continue
        is_forced = forced is not None and forced[0].id == p.id
        problem = None if is_forced else _piece_problem(p, place, ctx, t)
        if problem and strict:
            continue
        if place in ("mid", "outer") and t >= HOT_C and not is_forced:
            continue
        score = _piece_score(p, place, ctx, t) - (PIECE_PROBLEM_PENALTY if problem else 0)
        out.append(_Option(p, place, score, _warmth(p, place), problem))
    out.sort(key=lambda o: (-o.score, o.piece.id))
    keep = out[:CANDIDATES_PER_PLACE]
    for extra in (max(out, key=lambda o: (o.warmth, o.score), default=None),
                  min(out, key=lambda o: (o.warmth, -o.score), default=None)):
        if extra is not None and extra not in keep:
            keep.append(extra)
    keep += [o for o in out if o.piece.id in ctx.keep and o not in keep]   # pieces kept from an outfit worn again
    return keep


def _search(pool: list[Piece], ctx: Context, t: float, forced: tuple[Piece, str] | None, strict: bool,
            warmth_shift: float = 0.0) -> list[_Outfit]:
    opts = {place: _options(pool, place, ctx, t, forced, strict) for place in PLACES}
    if not opts["base"] or not opts["bottom"] or not opts["shoes"]:
        return []
    target = _warmth_target(t) + warmth_shift
    mids: list[_Option | None] = list(opts["mid"])
    outers: list[_Option | None] = list(opts["outer"])
    if not (forced and forced[1] == "mid"):
        mids.append(None)
    cold_needs_outer = t <= COLD_C and any(p.category in PLACE_CATEGORIES["outer"] for p in pool)
    if not (forced and forced[1] == "outer") and not (cold_needs_outer and (strict or outers)):
        outers.append(None)
    found = []
    for base, mid, outer in itertools.product(opts["base"], mids, outers):
        if not _layers_ok(base.piece, mid.piece if mid else None, outer.piece if outer else None):
            continue
        top_ids = {base.piece.id, mid.piece.id if mid else None, outer.piece.id if outer else None}
        if len({x for x in top_ids if x}) != 1 + (mid is not None) + (outer is not None):
            continue
        for bottom, shoes in itertools.product(opts["bottom"], opts["shoes"]):
            core = [o for o in (base, mid, outer, bottom, shoes) if o is not None]
            clothes = [o.piece for o in core]
            problems = _outfit_problems(clothes, [o.piece for o in core if o is not outer], outer.piece if outer else None)
            if problems and strict:
                continue
            warmth = sum(o.warmth for o in core)
            raw = sum(o.score for o in core) - _warmth_penalty(warmth, target, t)
            raw -= OUTFIT_PROBLEM_PENALTY * len(problems)
            if not strict and cold_needs_outer and outer is None:
                raw -= OUTER_MISSING_PENALTY
            raw += _colour_bonus(clothes)
            found.append(_Outfit(base, mid, outer, bottom, shoes, raw, problems))
    return found


def _warmth_penalty(warmth: float, target: float, t: float) -> float:
    gap = warmth - target
    if gap < -WARMTH_TOLERANCE:
        return WARMTH_SHORT_PER_POINT * (-gap - WARMTH_TOLERANCE)
    if gap > WARMTH_TOLERANCE:
        return (HOT_EXCESS_PER_POINT if t >= HOT_C else WARMTH_EXCESS_PER_POINT) * (gap - WARMTH_TOLERANCE)
    return 0.0


def _colour_bonus(pieces: list[Piece]) -> float:
    strong = [p for p in pieces if not _neutral(p)]
    if not strong:
        return ALL_NEUTRAL_BONUS
    return ACCENT_BONUS if len(strong) == 1 else 0.0


def _shared(a: _Outfit, b: _Outfit) -> int:
    return sum(1 for x, y in zip(a.ids(), b.ids(), strict=True) if x == y)


def _different(a: _Outfit, b: _Outfit) -> int:
    return len(PLACES) - _shared(a, b)


def _pick(found: list[_Outfit], count: int) -> list[_Outfit]:
    """The best outfits that differ from each other, as far as the closet allows."""
    found = sorted(found, key=lambda o: (-o.raw, o.ids()))
    chosen: list[_Outfit] = []
    for need in (MIN_PIECES_DIFFERENT, 1):
        while len(chosen) < count:
            best, best_key = None, None
            for o in found:
                if any(o is c or _different(o, c) < need for c in chosen):
                    continue
                key = o.raw - OVERLAP_PENALTY * max((_shared(o, c) for c in chosen), default=0)
                if best_key is None or key > best_key:
                    best, best_key = o, key
            if best is None:
                break
            chosen.append(best)
    return chosen


def _add_accessories(o: _Outfit, pool: list[Piece], ctx: Context, t: float, forced: tuple[Piece, str] | None) -> None:
    clothes = [x.piece for x in o.core()]
    for category in ACCESSORY_CATEGORIES:
        if forced and forced[1] == "accessory" and forced[0].category == category:
            o.accessories.append(_Option(forced[0], "accessory", _piece_score(forced[0], "accessory", ctx, t),
                                         _warmth(forced[0], "accessory"), None))
            clothes.append(forced[0])
            continue
        wanted = ((category == "scarf" and t <= SCARF_MAX_C) or (category == "hat" and t <= HAT_MAX_C)
                  or (category == "belt" and o.bottom.piece.category in ("trousers", "jeans")))
        if not wanted:
            continue
        best = None
        for p in pool:
            if p.category != category or (forced and forced[0].id == p.id):
                continue
            if _piece_problem(p, "accessory", ctx, t) or _outfit_problems(clothes + [p], []):
                continue
            score = _piece_score(p, "accessory", ctx, t)
            if category == "belt" and p.color == o.shoes.piece.color:
                score += BELT_MATCH_BONUS
            key = (score, p.id)
            if best is None or key > best[0]:
                best = (key, p)
        if best is not None:
            p = best[1]
            o.accessories.append(_Option(p, "accessory", best[0][0], _warmth(p, "accessory"), None))
            clothes.append(p)


# ====================================================================== explaining
def _explain(o: _Outfit, ctx: Context, t: float, forced: tuple[Piece, str] | None,
             closet_outers: list[Piece], feedback: Feedback | None = None) -> tuple[int, list[str], list[str]]:
    core = o.core()
    every = core + o.accessories
    pieces = [x.piece for x in core]
    reasons: list[str] = []
    warnings: list[str] = []
    if forced:
        reasons.append(f"Built around {_the(forced[0])}.")
        problem = _piece_problem(forced[0], forced[1], ctx, t)
        if problem:
            warnings.append(f"{problem} You asked to build around it, so the rest is chosen to suit it.")

    target = _warmth_target(t) + (feedback.warmth_shift if feedback else 0.0)
    warmth = sum(x.warmth for x in every)
    tops = [x.piece for x in (o.base, o.mid, o.outer) if x is not None]
    if len(tops) == 1 and t >= HOT_C:
        reasons.append(f"One light layer for {_temp_words(ctx)}.")
    elif len(tops) > 1:
        heavier_out = all(a.weight <= b.weight for a, b in itertools.pairwise(tops))
        reasons.append(f"{NUMBER_WORDS.get(len(tops), str(len(tops)))} layers for {_temp_words(ctx)}: "
                       f"{_join([_the(p) for p in tops])}"
                       f"{', each at least as heavy as the one under it' if heavier_out else ''}.")
    else:
        reasons.append(f"A single layer on top is enough for {_temp_words(ctx)}.")
    if warmth < target - WARMTH_TOLERANCE - WARMTH_NOTE_GAP:
        warmest = max(closet_outers, key=lambda p: (_warmth(p, "outer"), p.id), default=None)
        if o.outer is None and warmest is None:
            warnings.append(f"You have no coat or jacket to wear today; this will be cold for {_temp_words(ctx)}.")
        elif o.outer is not None and warmest is not None and _warmth(o.outer.piece, "outer") >= _warmth(warmest, "outer"):
            warnings.append(f"No coat warm enough for {_temp_words(ctx)}; {_the(o.outer.piece)} is the warmest you have.")
        else:
            warnings.append(f"This is lighter than {_temp_words(ctx)} calls for; take another layer if you will be out long.")
    elif warmth > target + WARMTH_TOLERANCE + WARMTH_NOTE_GAP:
        warnings.append(f"This is warmer than {_temp_words(ctx)} calls for; nothing lighter suited the rest.")

    under = [x.piece for x in core if x is not o.outer]
    levels = sorted({p.formality for p in under})
    clean = not _formality_clash(under, o.outer.piece if o.outer else None) and not any(
        _formality_off(x.piece, x.place, ctx.occasion) for x in core)
    if clean:
        occasion = OCCASION_WORDS[ctx.occasion]
        if len(levels) == 1:
            reasons.append(f"Everything is {LEVEL_WORDS[FORMALITY[levels[0]]]}, right for {occasion}.")
        else:
            reasons.append(f"Everything sits between {LEVEL_WORDS[FORMALITY[levels[0]]]} and "
                           f"{LEVEL_WORDS[FORMALITY[levels[-1]]]}, right for {occasion}.")
    if o.outer is not None and clean and levels and o.outer.piece.formality > levels[-1]:
        reasons.append(f"{_the(o.outer.piece, True)} is dressier than the rest, which is fine for the layer on top.")
    if ctx.mood != "usual":
        reasons.append("Leaning a little dressier, as you asked." if ctx.mood == "sharp"
                       else "Leaning a little more relaxed, as you asked.")

    strong = [p for p in pieces if not _neutral(p)]
    if not strong:
        reasons.append("All neutral colours, so everything goes together.")
    elif len(strong) == 1:
        colour = "a mix of colours" if strong[0].color == "multi" else (strong[0].color or "").replace("_", " ")
        reasons.append(f"One colour, {colour} from {_the(strong[0])}, against neutrals.")
    elif all(_tonal(a, b) for a, b in itertools.combinations(strong, 2)):
        family = FAMILY_WORDS.get(COLOR_FAMILY.get(strong[0].color or "", ""), "shades of one colour")
        reasons.append(f"Tonal {family}: {_join([_the(p) for p in strong])}.")
    loud = [p for p in pieces if p.pattern in LOUD_PATTERNS]
    patterned = [p for p in pieces if p.pattern != "solid"]
    if len(loud) == 1 and len(patterned) == 1:
        reasons.append(f"{_the(loud[0], True)} is the only pattern; everything else is plain.")
    elif len(patterned) == 1:
        reasons.append(f"The {patterned[0].pattern} of {_the(patterned[0])} is the only pattern.")

    loved = [x.piece for x in every if x.piece.rating == "love"]
    if loved:
        reasons.append(f"Includes {'a piece' if len(loved) == 1 else 'pieces'} you love: {_join([_the(p) for p in loved])}.")
    belt = next((x.piece for x in o.accessories if x.piece.category == "belt"), None)
    if belt and belt.color and belt.color == o.shoes.piece.color:
        reasons.append(f"{_the(belt, True)} matches {_the(o.shoes.piece)}.")
    if feedback:
        _explain_feedback(core, feedback, reasons, warnings)

    if ctx.rain:
        if o.shoes.piece.category == "boots":
            reasons.append(f"{_the(o.shoes.piece, True)} stand up to the rain.")
        if o.outer is not None and _rain_friendly(o.outer.piece):
            reasons.append(f"{_the(o.outer.piece, True)} keeps the rain off.")
        else:
            warnings.append("Rain is expected and nothing here keeps it off; take an umbrella.")
        for x in (o.outer, o.shoes):
            if x is not None and (word := _rain_unfriendly(x.piece)):
                warnings.append(f"{_the(x.piece, True)} is {word} and may not like the rain.")

    for x in every:
        if x.problem and not (forced and x.piece.id == forced[0].id):
            warnings.append(f"{x.problem} Nothing better suited is clean and available.")
    for p in o.problems:
        warnings.append(f"{p} Nothing in the closet made a better match.")
    for x in every:
        days = ctx.worn_days_ago.get(x.piece.id)
        if days is not None and days < RECENT_WEAR_DAYS and x.place in ("base", "mid"):
            warnings.append(f"You wore {_the(x.piece)} {_days_words(days)}; nothing else suited as well.")
    for x in every:
        if x.piece.in_storage:
            warnings.append(f"{_the(x.piece, True)} is in storage; get it out first.")

    raw = o.raw + sum(x.score for x in o.accessories)
    raw += _warmth_penalty(sum(x.warmth for x in core), target, t) - _warmth_penalty(warmth, target, t)
    score = max(0, min(100, round(SCORE_START + raw)))
    return score, reasons, warnings


# ====================================================================== learning from ratings
def _date_words(day: str) -> str:
    """ "3 November" from "2026-11-03"; the day as given if it is not a date."""
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", day or "")
    if not m or not 1 <= int(m.group(2)) <= 12:
        return day
    return f"{int(m.group(3))} {MONTH_WORDS[int(m.group(2)) - 1]}"


def _pairs(ids: object) -> frozenset[frozenset[str]]:
    return frozenset(frozenset(p) for p in itertools.combinations(sorted(set(ids)), 2))


def _problem_pairs(ids: frozenset[str], reasons: set[str], known: Mapping[str, Piece], same_occasion: bool) -> frozenset[frozenset[str]]:
    """The pairs of an outfit rated "not again" that its reasons say were the problem."""
    every = _pairs(ids)
    ps = [known[i] for i in sorted(ids) if i in known]
    out: set[frozenset[str]] = set()
    if not reasons - {"compliments"} or reasons & {"uncomfortable", "other"}:
        out |= every   # no reason given, or one that does not say which piece: the whole outfit
    if "colours_clashed" in reasons:
        loud = [p for p in ps if not _neutral(p) or p.pattern != "solid"]
        if len(loud) >= 2:
            out |= _pairs(p.id for p in loud)
        elif loud:
            out |= {frozenset((loud[0].id, p.id)) for p in ps if p is not loud[0]}
        else:
            out |= every
    for reason, pick in (("too_dressy", max), ("too_casual", min)):
        # too dressy for one occasion can be right for another, so only on the same kind of day
        if reason in reasons and same_occasion and ps:
            level = pick(p.formality for p in ps)
            odd = [p for p in ps if p.formality == level]
            if len(odd) == len(ps):
                out |= every
            else:
                out |= {frozenset((a.id, b.id)) for a in odd for b in ps if b.formality != level}
    return frozenset(out)


def feedback_from(rated: list[dict], items: list[dict], context: Context) -> Feedback:
    """Turn rated outfits (as `GET /api/outfits/worn` gives them) into what the engine needs for this day.

    Pure: the same outfits, items and day always give the same Feedback. Unrated outfits teach nothing.
    """
    known = {p.id: p for p in (_piece(i) for i in items if isinstance(i, dict) and i.get("id")) if p is not None}
    t = _design_temp(context)
    liked: list[Remembered] = []
    avoided: list[Remembered] = []
    not_again: dict[tuple[str, ...], str] = {}
    votes: list[tuple[str, int]] = []
    for o in sorted((o for o in rated if isinstance(o, dict)), key=lambda o: (str(o.get("worn_on")), str(o.get("id")))):
        rating = o.get("rating")
        if rating not in OUTFIT_RATINGS:
            continue
        reasons = {r for r in (o.get("rating_reasons") or ()) if r in OUTFIT_REASONS}
        day = str(o.get("worn_on") or "")
        placed = o.get("pieces") if isinstance(o.get("pieces"), dict) else {}
        core = {pl: str(placed[pl]) for pl in PLACES if placed.get(pl)}
        ids = frozenset(core.values())
        if rating == "loved" or ("compliments" in reasons and rating != "not_again"):
            if len(ids) >= 2:
                liked.append(Remembered(day, "loved" if rating == "loved" else "compliments", ids, _pairs(ids)))
        if rating == "not_again" and ids:
            not_again[tuple(core.get(pl, "") for pl in PLACES)] = day
            day_ctx = o.get("context") if isinstance(o.get("context"), dict) else {}
            bad = _problem_pairs(ids, reasons, known, day_ctx.get("occasion") in (None, context.occasion))
            if bad:
                avoided.append(Remembered(day, "not_again", ids, bad))
        direction = ("too_cold" in reasons) - ("too_warm" in reasons)
        day_ctx = o.get("context") if isinstance(o.get("context"), dict) else {}
        low, high = day_ctx.get("low_c"), day_ctx.get("high_c")
        if direction and all(isinstance(v, int | float) and not isinstance(v, bool) for v in (low, high)):
            then = low + DESIGN_TEMP_SHARE * (high - low)
            if abs(then - t) <= SIMILAR_DAY_C:
                votes.append((day, direction))
    total = sum(d for _, d in votes)
    shift = max(-WARMTH_SHIFT_MAX, min(WARMTH_SHIFT_MAX, WARMTH_SHIFT_PER_RATING * total))
    shift_day = max((day for day, d in votes if total and (d > 0) == (total > 0)), default=None)
    return Feedback(tuple(liked), tuple(avoided), not_again, shift, shift_day if shift else None)


def _feedback_score(ids: tuple[str, ...], liked: frozenset[frozenset[str]], avoided: frozenset[frozenset[str]]) -> float:
    pairs = _pairs(i for i in ids if i)
    good = sum(1 for p in pairs if p in liked)
    bad = sum(1 for p in pairs if p in avoided)
    return min(LOVED_MAX_BONUS, LOVED_PAIR_BONUS * good) - min(AVOID_MAX_PENALTY, AVOID_PAIR_PENALTY * bad)


def _explain_feedback(core: list[_Option], fb: Feedback, reasons: list[str], warnings: list[str]) -> None:
    ids = frozenset(x.piece.id for x in core)
    pairs = _pairs(ids)
    best = max((r for r in fb.liked if len(r.pieces & ids) >= 2),
               key=lambda r: (len(r.pieces & ids), r.day, r.kind), default=None)
    if best is not None:
        when = _date_words(best.day)
        shared = [x.piece for x in core if x.piece.id in best.pieces]
        if best.pieces == ids:
            reasons.append(f"You loved this outfit on {when}." if best.kind == "loved"
                           else f"You got compliments for this outfit on {when}.")
        elif best.kind == "loved":
            reasons.append(f"You loved {_join([_the(p) for p in shared])} together on {when}.")
        else:
            reasons.append(f"You got compliments wearing {_join([_the(p) for p in shared])} together on {when}.")
    bad = max((r for r in fb.avoided if r.pairs & pairs), key=lambda r: r.day, default=None)
    if bad is not None:
        hit = set().union(*(p for p in bad.pairs & pairs))
        named = [x.piece for x in core if x.piece.id in hit]
        warnings.append(f"{_join([_the(named[0], True)] + [_the(p) for p in named[1:]])} were together in an outfit "
                        f"you said not again to on {_date_words(bad.day)}.")
    if fb.warmth_shift > 0 and fb.warmth_day:
        reasons.append(f"Dressed a little warmer than usual: you were cold on a day like this on {_date_words(fb.warmth_day)}.")
    elif fb.warmth_shift < 0 and fb.warmth_day:
        reasons.append(f"Dressed a little lighter than usual: you were too warm on a day like this on {_date_words(fb.warmth_day)}.")


# ====================================================================== entry point
PLACE_WORDS = {"base": "tops (tees, shirts or polos)", "bottom": "trousers, jeans or shorts", "shoes": "shoes"}


def _unavailable(item: dict, ctx: Context) -> str | None:
    if item.get("status") == "archived":
        return "archived"
    if _in_laundry(item):
        return "in the laundry"
    if str(item.get("id")) in ctx.leave_out:
        return "left out today"
    if item.get("rating") == "dislike":
        return "rated dislike"
    return None


def _missing_place(place: str, everything: list[tuple[Piece, dict]], pool: list[Piece], ctx: Context) -> str | None:
    if any(p.category in PLACE_CATEGORIES[place] for p in pool):
        return None
    words = PLACE_WORDS[place]
    held = [it for p, it in everything if p.category in PLACE_CATEGORIES[place]]
    if not held:
        return f"There are no {words} in this closet yet."
    counts: dict[str, int] = {}
    for it in held:
        why = _unavailable(it, ctx) or "not usable"
        counts[why] = counts.get(why, 0) + 1
    parts = [f"{n} {why}" for why, n in sorted(counts.items())]
    return f"None of your {words} can be worn today: {_join(parts)}."


def suggest(items: list[dict], context: Context | dict, count: int = DEFAULT_COUNT, feedback: Feedback | None = None) -> dict:
    """Ranked outfits for the day.

    Returns {"outfits": [{"pieces": {base, mid, outer, bottom, shoes, accessories}, "score", "reasons",
    "warnings"}], "missing": [sentences]}. `missing` says what the closet lacks when no outfit can be made.
    `feedback` is what the owner's ratings of earlier outfits ask (see `feedback_from`); without it, or with
    an empty one, the outfits are exactly those the rules alone give.
    """
    ctx = context if isinstance(context, Context) else parse_request(dict(context))[0]
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ContextError(f"Count must be a whole number from 1 to {MAX_COUNT}.")
    t = _design_temp(ctx)
    everything = []
    for item in sorted((i for i in items if isinstance(i, dict) and i.get("id")), key=lambda i: str(i["id"])):
        p = _piece(item)
        if p is not None:
            everything.append((p, item))
    if not everything:
        return {"outfits": [], "missing": ["The closet has nothing to wear yet. Add some clothes first."]}

    forced_piece, forced_places = None, [None]
    if ctx.build_around:
        match = next(((p, it) for p, it in everything if p.id == ctx.build_around), None)
        if match is None:
            raw = next((i for i in items if isinstance(i, dict) and str(i.get("id")) == ctx.build_around), None)
            if raw is None:
                return {"outfits": [], "missing": ["The item to build around is not in this closet."]}
            return {"outfits": [], "missing": [
                f"The {_label(raw)} has no category an outfit can use. Set its category, then build around it."]}
        forced_piece, it = match
        why = _unavailable(it, ctx)
        if why in ("archived", "in the laundry"):
            return {"outfits": [], "missing": [f"{_the(forced_piece, True)} is {why}, so there is nothing to build around it."]}
        if forced_piece.category in ACCESSORY_CATEGORIES:
            forced_places = ["accessory"]
        else:
            forced_places = [pl for pl in PLACES if forced_piece.category in PLACE_CATEGORIES[pl]]

    pool = [p for p, it in everything if not _unavailable(it, ctx) or (forced_piece and p.id == forced_piece.id)]
    missing = [m for place in ("base", "bottom", "shoes") if (m := _missing_place(place, everything, pool, ctx))]
    if missing:
        return {"outfits": [], "missing": missing}

    fb = feedback or Feedback()
    liked = frozenset().union(*(r.pairs for r in fb.liked))
    avoided = frozenset().union(*(r.pairs for r in fb.avoided))
    refused: list[str] = []   # days of "not again" outfits that were the only ones left

    def run(strict: bool) -> list[tuple[_Outfit, tuple[Piece, str] | None]]:
        seen, out = set(), []
        for place in forced_places:
            forced = (forced_piece, place) if forced_piece is not None and place is not None else None
            core_forced = forced if forced and place != "accessory" else None
            for o in _search(pool, ctx, t, core_forced, strict, fb.warmth_shift):
                if o.ids() in seen:
                    continue
                seen.add(o.ids())
                if ctx.keep and not set(ctx.keep) <= set(o.ids()):
                    continue
                if o.ids() in fb.not_again:
                    refused.append(fb.not_again[o.ids()])
                    continue
                if liked or avoided:
                    o.raw += _feedback_score(o.ids(), liked, avoided)
                out.append((o, forced))
        return out

    found = run(strict=True) or run(strict=False)
    if not found:
        if refused:
            return {"outfits": [], "missing": [
                f"The only outfit the closet can make today is one you said not again to on {_date_words(max(refused))}."]}
        if ctx.keep:
            return {"outfits": [], "missing": ["The pieces kept from that outfit do not make an outfit for today."]}
        what = f"goes with {_the(forced_piece)}" if forced_piece else "works together today"
        return {"outfits": [], "missing": [f"Nothing in the closet {what}."]}
    forced_of = {id(o): f for o, f in found}
    closet_outers = [p for p in pool if p.category in PLACE_CATEGORIES["outer"]]
    result = []
    for rank, o in enumerate(_pick([o for o, _ in found], count)):
        forced = forced_of[id(o)]
        _add_accessories(o, pool, ctx, t, forced)
        score, reasons, warnings = _explain(o, ctx, t, forced, closet_outers, feedback)
        pieces = {place: (getattr(o, place).piece.id if getattr(o, place) else None) for place in PLACES}
        pieces["accessories"] = [x.piece.id for x in o.accessories]
        result.append((-score, rank, {"pieces": pieces, "score": score, "reasons": reasons, "warnings": warnings}))
    result.sort(key=lambda r: (r[0], r[1]))
    return {"outfits": [r[2] for r in result], "missing": []}
