"""A pattern drawn from words alone, for a piece that is not in the closet.

A find (a product Claude described from a shop's page) and a piece typed into "Would this work?" carry a pattern
word from the vocabulary (`vocab.PATTERN`) but no photo to measure, and the shop's picture is not ours to trace.
So a striped or plaid piece is drawn with a plain, typical pattern of that word (`fill_for`): a sketch of
"striped", not a claim about this product.

- Stripes run across a knit (a tee, a polo, a sweater, a hoodie: a Breton's hoops) and down anything woven (a
  shirt's stripe, a jacket's, coat's or trousers' pinstripe), unless the piece's own name says which way
  (`ACROSS_WORDS`, `DOWN_WORDS`: "Breton", "rugby", "pinstripe", "bengal", ...).
- Plaid is a plain plaid: a wide ground, a darker band and a thin line, crossing themselves; on a blazer, sport
  coat or suit jacket a quiet windowpane check; a gingham when the name says gingham.
- The ground is the piece's own colour, as it is drawn without a pattern. The description gives no second
  colour, so the other colour is a quiet neighbour of the ground (`neighbour`): the same hue, lighter on a dark or
  middling ground and darker on a light one, so it reads as a pattern without shouting.

It is kept and drawn exactly as a pattern Claude described for one of the owner's own pieces is (`patterns.surface`:
a tile woven from bands, sized by how many repeats fit across the chest, or across the waist on trousers), so a find
beside the owner's striped shirt is the same kind of drawing at the same scale, on the figure and flat. That path
uses OpenCV; this one weaves the same tile with numpy, because the drawing never imports OpenCV to draw from words.
Florals, camouflage, prints and "other" are not drawn: the piece is drawn in its colour (`COVERAGE`,
"described_patterns").
"""
from __future__ import annotations

import colorsys
import logging
import re

import numpy as np
from PIL import Image

from . import fills, item
from .illustrate import Fill

log = logging.getLogger("closet.drawing")

DRAWN = ("stripe", "plaid")   # the vocabulary's patterns drawn from words; the rest are drawn in the piece's colour
KNITS = ("tee", "polo", "sweater", "hoodie")   # their stripes run across, unless the name says otherwise
TAILORED = ("blazer", "sport_coat", "suit_jacket")   # their plaid is a quiet windowpane check
# words in the piece's name that say which way its stripes run (whole words, any case)
ACROSS_WORDS = ("breton", "sailor", "mariniere", "marinière", "hoop", "hoops", "hooped", "rugby", "horizontal",
                "horizontally", "nautical")
DOWN_WORDS = ("vertical", "vertically", "pinstripe", "pinstriped", "pin-stripe", "pin", "chalk", "chalkstripe",
              "bengal", "candy", "university", "butcher", "pencil", "awning", "seersucker")
GINGHAM_WORDS = ("gingham",)

# One repeat's bands, ground first ("g" the ground, "n" its neighbour, "d" the ground a shade deeper), and how many
# repeats fit across the chest (across the waist on trousers and shorts), in the words `patterns.described` sizes a
# described pattern with: small 6.5, medium 4, tiny 13 (the second form's).
BANDS = {
    "across": ([("g", 5), ("n", 3)], 6.5),             # a Breton's hoops
    "down": ([("g", 2), ("n", 1)], 13.0),              # a shirt's stripe
    "pinstripe": ([("g", 9), ("n", 1)], 8.0),          # a jacket's, coat's or trousers' stripe
    "plaid": ([("g", 6), ("d", 3), ("g", 2), ("n", 1)], 4.0),
    "windowpane": ([("g", 11), ("n", 1)], 4.0),
    "gingham": ([("g", 1), ("n", 1)], 13.0),
}
# Sizing on the drawing, as `patterns.described` and `patterns.surface` size a described pattern (a test keeps
# them equal): the drawn shirt's chest is this share of its neck-to-hem length and of its outline's width, and a
# bottom's waistband this share of its outline's width.
CHEST_PER_LENGTH = 0.60
CHEST_PER_OUTLINE = 0.47
WAIST_PER_OUTLINE = {"trousers": 0.885, "jeans": 0.885, "shorts": 0.73}
SIDE = 120          # px: one repeat's tile (drawn at most a few centimetres across, it needs no more)
EDGE = 0.01         # a band's edge is softened over this share of the repeat, as a woven band's is
LIGHTER, DARKER = 0.36, -0.30   # the neighbour: this much lighter (HLS lightness) on a ground darker than MIDDLE,
MIDDLE = 0.62                   # else this much darker
DEEPER = -0.12      # the plaid's darker band: the ground this much darker (lighter on a ground darker than this)


def _rgb(hex_: str) -> tuple[float, float, float]:
    h = hex_.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _hex(rgb) -> str:
    return "#" + "".join(f"{round(max(0.0, min(1.0, c)) * 255):02x}" for c in rgb)


def _lighter(hex_: str, amount: float) -> str:
    h, light, s = colorsys.rgb_to_hls(*_rgb(hex_))
    return _hex(colorsys.hls_to_rgb(h, max(0.0, min(1.0, light + amount)), s))


def neighbour(ground: str) -> str:
    """The pattern's other colour when the description gives none: the ground's own hue, lighter on a dark or
    middling ground, darker on a light one (a navy ground, a pale blue stripe; a white ground, a grey one)."""
    _, light, _ = colorsys.rgb_to_hls(*_rgb(ground))
    return _lighter(ground, LIGHTER if light < MIDDLE else DARKER)


def _deeper(ground: str) -> str:
    _, light, _ = colorsys.rgb_to_hls(*_rgb(ground))
    return _lighter(ground, DEEPER if light > -DEEPER * 2 else -DEEPER)


def _words(name) -> set[str]:
    return set(re.findall(r"[\w-]+", name.lower())) if isinstance(name, str) else set()


def kind_of(category: str | None, pattern: str | None, name: str | None = None, kind: str | None = None) -> str | None:
    """Which plain pattern a piece is drawn with (a key of BANDS), or None to draw it in its colour."""
    if pattern not in DRAWN or category not in item.TOPS + item.BOTTOMS:
        return None
    words = _words(name)
    if pattern == "plaid":
        if words & set(GINGHAM_WORDS):
            return "gingham"
        return "windowpane" if kind in TAILORED else "plaid"
    across = bool(words & set(ACROSS_WORDS)) or kind == "rugby_shirt"
    down = bool(words & set(DOWN_WORDS))
    if across != down:
        way = "across" if across else "down"
    else:
        way = "across" if category in KNITS else "down"
    if way == "down" and (category in item.BOTTOMS or category in ("jacket", "coat")):
        return "pinstripe"
    return way


def _sequence(bands: list[tuple[str, float]], n: int) -> np.ndarray:
    """The bands laid along n px as RGB, each px the share-weighted mix of the bands it covers, its edges softened
    round the repeat (so the ends meet)."""
    cols = np.array([_rgb(c) for c, _ in bands])
    edges = np.concatenate([[0.0], np.cumsum([w for _, w in bands])])
    edges *= n / edges[-1]
    px = np.arange(n, dtype=float)
    seq = np.zeros((n, 3))
    for k in range(len(bands)):
        cover = np.clip(np.minimum(px + 1, edges[k + 1]) - np.maximum(px, edges[k]), 0, 1)
        seq += cover[:, None] * cols[k]
    r = max(1, int(round(EDGE * n)))
    wide = np.concatenate([seq[-r:], seq, seq[:r]])
    box = np.ones(2 * r + 1) / (2 * r + 1)
    return np.stack([np.convolve(wide[:, c], box, mode="valid") for c in range(3)], 1)


def tile(kind: str, ground: str) -> tuple[Image.Image, tuple[float, float]]:
    """One repeat of the plain pattern as a square RGB tile, and where the middle of its first (ground) band falls
    in it, as fractions of its width and height (so the ground is on the garment's centre line)."""
    colours = {"g": ground, "n": neighbour(ground), "d": _deeper(ground)}
    spec, _ = BANDS[kind]
    bands = [(colours[c], float(w)) for c, w in spec]
    seq = _sequence(bands, SIDE)
    half = bands[0][1] / 2 / sum(w for _, w in bands)
    if kind == "across":
        img, first = np.repeat(seq[:, None, :], SIDE, 1), (0.0, half)
    elif kind in ("down", "pinstripe"):
        img, first = np.repeat(seq[None, :, :], SIDE, 0), (half, 0.0)
    else:   # bands both ways, crossing: each spot the even mix of the yarn across and the yarn down
        img, first = (seq[None, :, :] + seq[:, None, :]) / 2, (half, half)
    return Image.fromarray(np.clip(img * 255, 0, 255).round().astype(np.uint8), "RGB"), first


def fill_for(category: str | None, color: str | None, pattern: str | None, name: str | None = None,
             kind: str | None = None) -> Fill | None:
    """The fill a piece not in the closet is drawn with when its pattern word is one drawn from words (stripes,
    plaid), as a tile sized as a described pattern on an owned piece is; None to draw it in its colour. `color` is
    its colour word, `name` its name (it may say which way its stripes run), `kind` its kind from the name
    (`kinds.from_words`). Never raises."""
    try:
        drawn = kind_of(category, pattern, name, kind)
        if drawn is None:
            return None
        ground = item._color(None, color if color in item.NAMED_HEX else "grey")
        img, first = tile(drawn, ground)
        repeats = BANDS[drawn][1]
        if category in item.BOTTOMS:   # sized across the waist: trousers have no neck-to-hem line
            sw = fills.Swatch(img, WAIST_PER_OUTLINE[category] / repeats, (0, 0, 0, 0), "described", phase=first)
        else:
            sw = fills.Swatch(img, CHEST_PER_OUTLINE / repeats, (0, 0, 0, 0), "described", phase=first,
                              length_frac=CHEST_PER_LENGTH / repeats)
        return Fill("swatch", ground, swatch=sw)
    except Exception:   # a pattern must never cost the piece its drawing
        log.exception("drawing a %s's pattern from its words failed; drawing it in its colour", category)
        return None
