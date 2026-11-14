"""The owner's outfit rules, read from `docs/menswear-taxonomy.json` (its `outfit` and `colors` blocks).

`parse(outfit, colors)` turns the file's lists and sentences into a `Rules` the outfit engine
(`closet/outfits.py`) checks. Every sentence is recognised by the words in it: a sentence the owner
deletes stops being applied, a number in it ("within one level", "at most one accent") is read, and a
sentence this module does not understand is kept in `Rules.unread` with the reason, never guessed at.

`RULES` is the owner's file as it is on disk, read once when the program starts. Tests swap it for a
copy (`use`) to check that the engine follows the file. Everything that reads it goes through
`outfits.rules()`, so Today, trips, What's missing and "Would this work?" all use the same rules.

Where the file is silent the engine keeps its own rules (warmth points, season, shorts and sandals
temperatures, the category bans per occasion): see `docs/DECISIONS.md`, "The owner's outfit rules".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import vocab
from .tagger import taxonomy

PLACES = ("base", "mid", "outer", "bottom", "shoes")
SHOE_CATEGORIES = ("sneakers", "boots", "dress_shoes", "sandals")

# ---------------------------------------------------------------- the file's place words, in the app's categories
# word -> ((category, kind or None, needs or None), ...). A kind is a test on the piece itself (its name,
# material or silhouette; see outfits._is_kind); "needs" is what it must be worn with in that place.
PLACE_WORDS: dict[str, tuple[tuple[str, str | None, str | None], ...]] = {
    "tee": (("tee", None, None),),
    "polo": (("polo", None, None),),
    "shirt": (("shirt", None, None),),
    "henley": (("tee", "henley", None),),
    "tank": (("tee", "tank", None),),
    "long_sleeve_tee": (("tee", "long_sleeve", None),),
    "fine_turtleneck": (("sweater", "fine_turtleneck", None),),
    "base_layer": (("tee", "thermal", None),),
    "sweater": (("sweater", None, None),),
    "cardigan": (("sweater", "cardigan", None),),
    "sweatshirt": (("sweater", "sweatshirt", None), ("hoodie", "sweatshirt", None)),
    "hoodie": (("hoodie", None, None),),
    "sweater_vest": (("sweater", "vest", None),),
    "overshirt": (("shirt", "overshirt", None), ("jacket", "overshirt", None)),
    "shirt_over_tee": (("shirt", None, "over_tee"),),
    "fleece": (("jacket", "fleece", None), ("sweater", "fleece", None), ("hoodie", "fleece", None)),
    "light_jacket_under_coat": (("jacket", "light", "under_coat"),),
    "jacket": (("jacket", None, None),),
    "coat": (("coat", None, None),),
    "blazer": (("jacket", "blazer", None),),
    "sport_coat": (("jacket", "sport_coat", None),),
    "shell": (("jacket", "shell", None), ("coat", "shell", None)),
    "puffer": (("jacket", "puffer", None), ("coat", "puffer", None)),
    "trousers": (("trousers", None, None),),
    "jeans": (("jeans", None, None),),
    "chinos": (("trousers", "chinos", None),),
    "cords": (("trousers", "cords", None),),
    "shorts": (("shorts", None, None),),
    "joggers": (("trousers", "joggers", None),),
    "one_pair": tuple((c, None, None) for c in SHOE_CATEGORIES),
}
ACCESSORY_WORDS = {"belt": "belt", "hat": "hat", "scarf": "scarf", "bag": "bag"}

# Words in a piece's name or material that say which kind it is (the app's categories are coarser than the file's).
KIND_WORDS: dict[str, tuple[str, ...]] = {
    "henley": ("henley",), "tank": ("tank", "singlet", "vest"), "thermal": ("thermal", "baselayer"),
    "cardigan": ("cardigan",), "sweatshirt": ("sweatshirt", "crewneck"), "vest": ("vest", "tank"),
    "overshirt": ("overshirt", "shacket"), "fleece": ("fleece",), "blazer": ("blazer",),
    "sport_coat": ("sportcoat", "sport"), "shell": ("shell", "windbreaker", "anorak"), "puffer": ("puffer",),
    "chinos": ("chino", "chinos", "khakis"), "cords": ("cord", "cords", "corduroy", "corduroys"),
    "joggers": ("jogger", "joggers", "sweatpants", "trackpants"), "loafer": ("loafer", "loafers"),
    "chunky": ("chunky",),
}
# Fine knits, for "fine_turtleneck": a turtleneck this light, or whose name or material says so.
FINE_KNIT_WORDS = ("fine", "merino", "silk", "cashmere", "sea", "island")

# The file's rain sentence names kinds of outer layer ("shell, waxed, trench, mac"); these are the words in an
# item's name or material that mean each one.
RAIN_WORDS: dict[str, tuple[str, ...]] = {
    "shell": ("shell", "hardshell", "gore", "goretex", "anorak"),
    "waxed": ("waxed", "wax"),
    "trench": ("trench",),
    "mac": ("mac", "mackintosh", "raincoat", "rain"),
    "water-resistant": ("waterproof", "rainproof"),
}

# From the owner's guide (docs/menswear-reference-extended.md 16.4 and 16.6), the words the file's
# sentences stand for: rough and smooth cloth, textured solids and loud prints.
ROUGH_WORDS = ("tweed", "flannel", "cord", "cords", "corduroy", "suede", "canvas", "boucle", "fleece")
SMOOTH_WORDS = ("worsted", "poplin", "calf", "silk", "satin", "sateen", "broadcloth", "gabardine", "pinpoint")
TEXTURED_WORDS = ("tweed", "cable", "aran", "cord", "cords", "corduroy", "boucle", "waffle", "fisherman", "shaker",
                  "moss", "marl", "chunky", "herringbone", "seersucker")
LOUD_PRINTS = ("floral", "camo", "graphic", "other")   # aloha and large florals, camo, graphic tees; "other" is novelty
TAILORING = ("business", "formal")                   # "only in tailoring": the occasions suits are worn to

# The engine's rules before it read the owner's file, in the file's own words: a block missing from the file
# (not one left empty) is read from here, so deleting a whole block keeps the old behaviour rather than none.
FALLBACK_OUTFIT: dict = {
    "places": {"base": ["tee", "shirt", "polo"], "mid": ["sweater", "hoodie", "shirt_over_tee", "light_jacket_under_coat"],
               "outer": ["jacket", "coat"], "bottom": ["trousers", "jeans", "shorts"], "shoes": ["one_pair"],
               "accessories": ["belt", "scarf", "hat", "bag"]},
    "layering_rules": ["each layer fits over the one beneath", "tucked shirt with belt loops means a belt"],
    "temperature_bands_c": [{"high_min": 24, "outfit": "base only"},
                            {"high_min": 9, "outfit": "base; optional mid or outer"},
                            {"high_min": 5, "outfit": "base + outer; optional mid; scarf"},
                            {"high_min": -99, "outfit": "base + outer; optional mid; hat, scarf"}],
    "rain": "outer should be water-resistant (waxed, mac, trench, parka, nylon, shell); avoid suede, canvas, linen or silk shoes",
    "formality_rules": ["every piece within one level of the target"],
    "color_rules": ["neutrals plus at most one accent", "denim is a neutral blue"],
}
FALLBACK_NEUTRALS = ("black", "white", "grey", "navy", "tan", "brown", "cream", "olive", "light_blue")

NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "half": 0.5}


@dataclass(frozen=True)
class Slot:
    word: str          # the file's word
    category: str      # the app category it is
    kind: str | None   # a test on the piece (outfits._is_kind)
    needs: str | None  # "over_tee" or "under_coat": what it must be worn with in this place


@dataclass(frozen=True)
class Band:
    """One of the file's temperature bands: from `high_min` °C (the day's high) up to the next band."""
    high_min: float
    text: str
    mid: str = "may"                  # "no", "may" or "must"
    outer: str = "may"
    weights: dict = field(default_factory=dict)   # place -> (lightest, heaviest) weight class wanted, 0-3
    fabrics: int = 0                  # 1: heavier fabrics, -1: lighter ones
    accessories: tuple[str, ...] = ()  # accessories to add (hat, scarf)
    shoes: tuple[tuple[str, str | None], ...] = ()    # (category, kind) the band names, preferred
    bottoms: tuple[tuple[str, int | None], ...] = ()  # (category, heaviest weight class) the band names, preferred

    @property
    def bare(self) -> bool:
        """Nothing over the base: the hot band."""
        return self.mid == "no" and self.outer == "no"


@dataclass(frozen=True)
class Rules:
    places: dict                      # place -> tuple[Slot, ...]
    accessories: tuple[str, ...]
    bands: tuple[Band, ...]           # warmest first
    # layering
    layer_order: bool = False         # each layer at least as heavy and bulky as the one under it
    collar_turtle: bool = False       # nothing collared under a turtleneck
    long_under_short: bool = False    # a long shirt never far below a short jacket
    hoodie_blazer: bool = False       # a hoodie under a blazer is streetwear (casual days only)
    belt_with_loops: bool = False     # a belt with trousers or jeans
    turtle_for_tie: bool = False      # a turtleneck under a blazer or coat stands in for shirt and tie
    vest_over_shirt: bool = False     # a sweater vest only over a shirt
    # rain
    rain_words: tuple[str, ...] = ()  # words that mean an outer layer sheds water
    rain_outer_must: bool = False     # in rain, an outer layer worn must shed water
    rain_avoid_shoes: tuple[str, ...] = ()
    rain_text: str = ""
    # formality
    levels: tuple[str, ...] = tuple(vocab.FORMALITY)  # the app's levels in the owner's order
    reach: int | None = None          # every piece within this many levels of the occasion
    impression: tuple[str, ...] = ()  # places that set the impression most strongly
    one_dressier: bool = False        # one piece may sit a level further above the rest
    down_in_shoes: tuple[str, ...] = ()   # occasions where the shoes may sit a level further below the rest
    athletic_with: tuple[str, ...] | None = None  # the only levels athletic pieces mix with
    texture_formality: bool = False   # smooth cloth counts dressier, rough cloth more casual
    # colour
    neutrals: tuple[str, ...] = ()
    brights: tuple[str, ...] = ()
    shade_lightness: dict = field(default_factory=dict)  # app colour -> 0-1, from the file's named shades
    pairings: tuple[tuple[str, str], ...] = ()
    max_accents: int | None = None
    tonal_texture: bool = False
    light_over_dark: bool = False
    near_shades: bool = False
    max_brights: int | None = None
    denim_neutral: bool = False
    double_denim: bool = False
    shoe_colours: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = ()  # (shoe colour, only with, never with)
    belt_match_on: tuple[str, ...] = ()
    # pattern
    one_pattern_safe: bool = False
    two_shared_colour: bool = False
    tailoring_three: bool = False
    same_type_never: bool = False
    textured_weight: float = 0.0
    loud_focus: bool = False
    # proportion (score only)
    fit_legs: dict = field(default_factory=dict)   # "slim"/"roomy" top -> legs that suit it
    cropped_straight: bool = False
    short_jacket: bool = False
    shoe_legs: bool = False
    shoe_break: bool = False
    # what was not understood: (where, text, why)
    unread: tuple[tuple[str, str, str], ...] = ()
    _cache: dict = field(default_factory=dict, compare=False, repr=False)

    def band(self, high_c: float) -> Band:
        for b in self.bands:
            if high_c >= b.high_min:
                return b
        return self.bands[-1] if self.bands else Band(-999, "")

    def place_categories(self, place: str) -> tuple[str, ...]:
        key = ("categories", place)
        if key not in self._cache:
            self._cache[key] = tuple(dict.fromkeys(s.category for s in self.places.get(place, ())))
        return self._cache[key]

    def slots(self, place: str, category: str) -> tuple[Slot, ...]:
        """The file's words for this place that are this app category."""
        key = ("slots", place, category)
        if key not in self._cache:
            self._cache[key] = tuple(s for s in self.places.get(place, ()) if s.category == category)
        return self._cache[key]


# ====================================================================== reading the file
def _number(word: str) -> float | None:
    word = word.lower()
    return float(word) if re.fullmatch(r"\d+(\.\d+)?", word) else NUMBERS.get(word)


def _strings(value: object) -> list[str]:
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def _places(outfit: dict, unread: list) -> tuple[dict, tuple[str, ...]]:
    given = outfit.get("places") if isinstance(outfit.get("places"), dict) else {}
    places: dict[str, tuple[Slot, ...]] = {}
    for place in PLACES:
        slots = []
        for word in _strings(given.get(place)):
            if word in PLACE_WORDS:
                slots += [Slot(word, c, k, n) for c, k, n in PLACE_WORDS[word]]
            else:
                unread.append((f"places.{place}", word, "no category in the app is this"))
        places[place] = tuple(slots)
    accessories = []
    for word in _strings(given.get("accessories")):
        if word in ACCESSORY_WORDS:
            accessories.append(ACCESSORY_WORDS[word])
        else:
            unread.append(("places.accessories", word, "no category in the app is this"))
    return places, tuple(accessories)


_LAYER_TERMS = {"base": ("base",), "mid": ("mid", "overshirt"), "outer": ("outer", "jacket", "coat", "overshirt")}
_WEIGHT_TERMS = (("insulated", (3, 3)), ("warm", (2, 3)), ("heavy", (2, 3)), ("medium", (1, 2)), ("light", (0, 1)),
                 ("unlined", (0, 1)))
_SHOE_TERMS = {"sneakers": ("sneakers", None), "loafers": ("dress_shoes", "loafer"), "sandals": ("sandals", None),
               "boots": ("boots", None), "dress shoes": ("dress_shoes", None)}
_BOTTOM_TERMS = {"shorts": "shorts", "trousers": "trousers", "jeans": "jeans", "chinos": "trousers"}


def _band(entry: dict, unread: list) -> Band | None:
    high = entry.get("high_min")
    text = entry.get("outfit")
    if isinstance(high, bool) or not isinstance(high, int | float) or not isinstance(text, str):
        unread.append(("temperature_bands_c", str(entry), "a band needs a high_min number and an outfit sentence"))
        return None
    allowed: set[str] = set()
    must: set[str] | None = None
    weights: dict[str, tuple[int, int]] = {}
    fabrics, accessories, shoes, bottoms = 0, [], [], []
    bare, any_layers = False, False
    for clause in (c.strip().lower() for c in text.split(";")):
        if not clause:
            continue
        understood = False
        if re.search(r"\bbase only\b", clause):
            bare = any_layers = understood = True
            continue
        if any(re.search(rf"\b{t}\b", clause) for terms in _LAYER_TERMS.values() for t in terms):
            any_layers = understood = True
            optional = clause.startswith("optional")
            alts = []
            for alt in re.split(r",?\s+or\s+", clause.removeprefix("optional").strip()):
                here = set()
                for part in alt.split("+"):
                    for place, terms in _LAYER_TERMS.items():
                        if any(re.search(rf"\b{t}\b", part) for t in terms):
                            here.add(place)
                            for word, (lo, hi) in _WEIGHT_TERMS:
                                if re.search(rf"\b{word}\b", part) and place != "base":
                                    old = weights.get(place)
                                    weights[place] = (min(lo, old[0]), max(hi, old[1])) if old else (lo, hi)
                                    break
                alts.append(here)
            allowed |= set().union(*alts)
            if not optional:
                common = set.intersection(*alts) if alts else set()
                must = common if must is None else must | common
        for name, (cat, kind) in _SHOE_TERMS.items():
            if re.search(rf"\b{name}\b", clause):
                shoes.append((cat, kind))
                understood = True
        for name, cat in _BOTTOM_TERMS.items():
            if re.search(rf"\b{name}\b", clause):
                light = re.search(rf"\blight {name}\b", clause) is not None
                bottoms.append((cat, 1 if light else None))
                understood = True
        for name in ("hat", "scarf", "gloves", "belt"):
            if re.search(rf"\b{name}\b", clause):
                understood = True
                if name in ACCESSORY_WORDS:
                    accessories.append(name)
                else:
                    unread.append(("temperature_bands_c", f"{high}: {name}", "no category in the app is this"))
        if re.search(r"\bheav(ier|y) fabrics\b", clause):
            fabrics, understood = 1, True
        elif re.search(r"\blight(er)? fabrics\b", clause):
            fabrics, understood = -1, True
        if not understood:
            unread.append(("temperature_bands_c", f"{high}: {clause}", "not understood"))
    must = must or set()

    def state(place: str) -> str:
        if bare or (any_layers and place not in allowed):
            return "no" if any_layers else "may"
        return "must" if place in must else "may"

    return Band(float(high), text, state("mid"), state("outer"), weights, fabrics, tuple(dict.fromkeys(accessories)),
                tuple(dict.fromkeys(shoes)), tuple(dict.fromkeys(bottoms)))


def _levels(outfit: dict, unread: list) -> tuple[str, ...]:
    note = outfit.get("formality_notes") if isinstance(outfit.get("formality_notes"), str) else ""
    maps = dict(re.findall(r"\b(\w+) pieces map to the app's (\w+)", note))
    order: list[str] = []
    for word in _strings(outfit.get("formality_levels")):
        level = maps.get(word, word)
        if level not in vocab.FORMALITY:
            unread.append(("formality_levels", word, "not a formality the app has"))
        elif level not in order:
            order.append(level)
    if sorted(order) != sorted(vocab.FORMALITY):
        if order:
            unread.append(("formality_levels", ", ".join(order), "does not name every formality the app has; the app's order is used"))
        return tuple(vocab.FORMALITY)
    return tuple(order)


def _occasions(text: str) -> tuple[str, ...]:
    found = []
    for level in vocab.FORMALITY:
        words = (level, level.replace("_", " ")) + (("smart",) if level == "smart_casual" else ())
        if any(re.search(rf"\b{w}\b", text) for w in words):
            found.append(level)
    if "smart_casual" in found and re.search(r"\bcasual\b", text.replace("smart_casual", "").replace("smart casual", "")) is None:
        found = [f for f in found if f != "casual"]
    return tuple(found)


def _colour_list(text: str) -> tuple[str, ...]:
    return tuple(w for w in re.findall(r"[a-z_]+", text) if w in vocab.COLOR)


def _lightness(colors: dict) -> dict[str, float]:
    by: dict[str, list[float]] = {}
    for shade in colors.get("shades") or []:
        if isinstance(shade, dict) and shade.get("app_color") in vocab.COLOR and isinstance(shade.get("hex"), str):
            h = shade["hex"].lstrip("#")
            if re.fullmatch(r"[0-9a-fA-F]{6}", h):
                r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
                by.setdefault(shade["app_color"], []).append((max(r, g, b) + min(r, g, b)) / 2)
    return {c: sum(v) / len(v) for c, v in by.items()}


def parse(outfit: dict, colors: dict | None = None) -> Rules:
    """The engine's rules from the file's `outfit` and `colors` blocks."""
    outfit = {**FALLBACK_OUTFIT, **(outfit if isinstance(outfit, dict) else {})}
    colors = colors if isinstance(colors, dict) else {}
    unread: list[tuple[str, str, str]] = []
    r: dict = {}
    r["places"], r["accessories"] = _places(outfit, unread)

    bands = [b for e in (outfit.get("temperature_bands_c") or []) if isinstance(e, dict) and (b := _band(e, unread))]
    r["bands"] = tuple(sorted(bands, key=lambda b: -b.high_min))

    for text in _strings(outfit.get("layering_rules")):
        t = text.lower()
        if "fits over the one beneath" in t or ("thin" in t and "thick" in t and "outside" in t):
            r["layer_order"] = True
        elif "under a turtleneck" in t:
            r["collar_turtle"] = True
        elif "jacket hem" in t:
            r["long_under_short"] = True
        elif "hoodie under a blazer" in t:
            r["hoodie_blazer"] = True
        elif "belt" in t and "loops" in t:
            r["belt_with_loops"] = True
        elif "turtleneck can replace" in t:
            r["turtle_for_tie"] = True
        elif "sweater vest goes over a shirt" in t:
            r["vest_over_shirt"] = True
        elif re.search(r"base \+ mid \+ outer is the useful maximum", t):
            pass   # the engine has exactly these three places on top; a fourth layer is never offered
        elif re.search(r"\btuck", t):
            unread.append(("layering_rules", text, "the app does not record or show whether a shirt is tucked"))
        else:
            unread.append(("layering_rules", text, "not understood"))

    rain = outfit.get("rain") if isinstance(outfit.get("rain"), str) else ""
    r["rain_text"] = rain
    for clause in (c.strip().lower() for c in rain.split(";") if c.strip()):
        m = re.search(r"outer (must|should) be (water-resistant|waterproof)\s*(?:\(([^)]*)\))?", clause)
        if m:
            kinds = [k.strip() for k in (m.group(3) or "").split(",") if k.strip()] + ["water-resistant"]
            words: list[str] = []
            for k in kinds:
                words += RAIN_WORDS.get(k, (k,))
            r["rain_words"] = tuple(dict.fromkeys(words))
            r["rain_outer_must"] = m.group(1) == "must"
            continue
        m = re.search(r"avoid ([a-z ,]+?) shoes", clause)
        if m:
            r["rain_avoid_shoes"] = tuple(w for w in re.split(r",\s*|\s+or\s+|\s+and\s+", m.group(1)) if w)
            continue
        unread.append(("rain", clause, "not understood"))

    r["levels"] = _levels(outfit, unread)
    for text in _strings(outfit.get("formality_rules")):
        t = text.lower()
        if m := re.search(r"every piece within (\w+) levels? of the target", t):
            n = _number(m.group(1))
            if n is None:
                unread.append(("formality_rules", text, "the number of levels is not understood"))
            else:
                r["reach"] = int(n)
        elif "set the impression" in t:
            r["impression"] = tuple(p for p, w in (("shoes", "shoes"), ("outer", "outer")) if w in t)
        elif "dressier piece is fine" in t:
            r["one_dressier"] = True
        elif "dressing down only in shoes" in t:
            m = re.search(r"only in shoes,? and only in (.+)$", t)
            r["down_in_shoes"] = _occasions(m.group(1)) if m else ()
        elif m := re.search(r"athletic mixes only with ([a-z_ ,]+?)(?:,|$)", t):
            r["athletic_with"] = ("athletic",) + _occasions(m.group(1))
        elif "fabrics are dressier" in t:
            r["texture_formality"] = True
        else:
            unread.append(("formality_rules", text, "not understood"))

    families = colors.get("families") if isinstance(colors.get("families"), dict) else {}
    r["neutrals"] = (tuple(c for c in _strings(families.get("neutral")) if c in vocab.COLOR)
                     if "neutral" in families else FALLBACK_NEUTRALS)
    r["brights"] = tuple(c for c in _strings(families.get("bright")) if c in vocab.COLOR)
    r["shade_lightness"] = _lightness(colors)
    pairs = []
    for pair in outfit.get("color_pairings") or []:
        ok = isinstance(pair, list) and len(pair) == 2 and all(c in vocab.COLOR for c in pair)
        if ok:
            pairs.append((pair[0], pair[1]))
        else:
            unread.append(("color_pairings", str(pair), "a pairing is two of the app's colours"))
    r["pairings"] = tuple(pairs)
    for text in _strings(outfit.get("color_rules")):
        t = text.lower()
        if m := re.search(r"neutrals plus at most (\w+) accent", t):
            r["max_accents"] = int(_number(m.group(1)) or 0)
        elif "tonal" in t and "texture" in t:
            r["tonal_texture"] = True
        elif "light top with dark bottom" in t:
            r["light_over_dark"] = True
        elif "near-identical" in t:
            r["near_shades"] = True
        elif m := re.search(r"at most (\w+) bright colou?rs?", t):
            r["max_brights"] = int(_number(m.group(1)) or 0)
        elif "denim" in t:
            r["denim_neutral"] = "neutral" in t
            r["double_denim"] = "double denim" in t
        elif "shoes with" in t:
            rules = []
            for part in re.split(r";", t):
                if m := re.search(r"(\w+) shoes with everything except ([a-z_ ,]+?) (?:trousers|bottoms)", part):
                    rules.append((m.group(1), (), _colour_list(m.group(2))))
                elif m := re.search(r"(\w+) shoes with ([a-z_ ,]+)", part):
                    rules.append((m.group(1), _colour_list(m.group(2)), ()))
            r["shoe_colours"] = tuple(x for x in rules if x[0] in vocab.COLOR)
        elif m := re.search(r"belt matches shoes in (.+?) outfits", t):
            r["belt_match_on"] = _occasions(m.group(1))
        else:
            unread.append(("color_rules", text, "not understood"))

    for text in _strings(outfit.get("pattern_rules")):
        t = text.lower()
        if "one pattern per outfit" in t:
            r["one_pattern_safe"] = True
        elif "two patterns need" in t:
            r["two_shared_colour"] = "shared colo" in t
        elif "three patterns only in tailoring" in t:
            r["tailoring_three"] = True
        elif "same type" in t and "never" in t:
            r["same_type_never"] = True
        elif m := re.search(r"textured solids count as (\w+) a pattern", t):
            r["textured_weight"] = float(_number(m.group(1)) or 0)
        elif "loud prints" in t:
            r["loud_focus"] = True
        else:
            unread.append(("pattern_rules", text, "not understood"))

    for text in _strings(outfit.get("proportion_rules")):
        t = text.lower()
        if m := re.search(r"slim top with ([a-z ]+?) bottom;\s*roomy top with ([a-z ]+?) bottom", t):
            r["fit_legs"] = {"slim": tuple(re.split(r"\s+or\s+", m.group(1))),
                             "roomy": tuple(re.split(r"\s+or\s+", m.group(2)))}
        elif "cropped" in t and "trousers" in t:
            r["cropped_straight"] = True
        elif "short jackets" in t:
            r["short_jacket"] = True
        elif "chunky shoes" in t:
            r["shoe_legs"] = True
        elif "break" in t:
            r["shoe_break"] = True
        else:
            unread.append(("proportion_rules", text, "not understood"))
    return Rules(**r, unread=tuple(unread))


def load() -> Rules:
    """The rules in the owner's file as it is on disk."""
    return parse(*taxonomy.outfit_rules())


RULES: Rules = load()


def use(rules: Rules) -> Rules:
    """Make `rules` the ones every outfit is chosen by; returns the previous ones (for tests)."""
    global RULES
    old, RULES = RULES, rules
    return old
