"""The cloth's surface, as Claude describes it on the description call: one kind of pattern with only that kind's
fields filled, for the app's own drawing (`closet.patterns.surface` turns it into what the drawing takes).

The form is the "second form" of the garment loop test (`bench/experiments/garment_loop`, arm F), adopted by the
owner on 18 November: stripes, plaid and checks as one repeat of bands; plain cloth with parts or bands across the
body in other colours; plain; or "other" for a print, which the app pieces from the photo. Plain data only: the
drawing imports it, so nothing here may import OpenCV.
"""
from __future__ import annotations

from typing import Literal, get_args

from pydantic import BaseModel, Field

FIELD_TEXT = {
    "surface": "The cloth's surface, so the app can draw it: one kind, with only that kind's fields filled.",
    "kind": ("plain: one colour. stripes: bands running one way. plaid: bands both ways, crossing (plaid, check, "
             "gingham, tartan, madras, windowpane). blocks: plain cloth with whole parts or bands across the body in "
             "other colours (a yoke, sleeves, collar or pocket; a chest panel, a band across the chest, an upper or "
             "lower body in another colour). other: anything else (florals, camouflage, paisley, other prints, "
             "patchwork): the app pieces it from the photo. When unsure, say less: plain or other."),
    "bands": "stripes and plaid only, else empty: one repeat's bands, ground first. A thin line is width 1.",
    "direction": "stripes only, else null: horizontal (running side to side) or vertical.",
    "size": ("stripes and plaid only, else null: how many repeats fit across the chest (trousers and shorts: across "
             "the waist), counted the way the bands repeat: micro more than 20, tiny 9-20, small 5-8, medium 3-5, "
             "large 2-3, huge under 2."),
    "blocks": ("blocks only, else empty: each part cut in another colour than the body. sleeves: both sleeves in one "
               "colour; when the two differ, left_sleeve_as_seen and right_sleeve_as_seen: the sleeve on the left or "
               "the right of the photo as you see it (not the wearer's left)."),
    "panels": ("blocks only, else empty: each band of another colour running across the whole body (sleeves "
               "included), as how far down it starts and ends, from the collar (0) to the hem (100), in order from "
               "the top. A chest panel is one band; a body in two colours is one band from where the second colour "
               "starts to 100."),
    "colors": ("plain, blocks and other, else empty: the main colours, the body's first, each with a whole-number "
               "share of the cloth."),
    "color": "#rrggbb as it looks on this cloth.",
    "width": "Whole number; the ground's width shows how much of the cloth it covers.",
    "share": "Whole number; how much of the cloth it covers, against the others.",
    "top": "Where the band starts, 0 at the collar to 100 at the hem.",
    "bottom": "Where the band ends, 0 at the collar to 100 at the hem.",
    "lettering": ("Letters or words on the front of the item that you can read for certain: a brand name, a "
                  "wordmark, a slogan, a team name. Empty when there are none, when the mark is a picture or a symbol "
                  "(an animal, a crest, a swoosh, a monogram you cannot read), or when you cannot read every letter. "
                  "Never guess a letter."),
    "text": "Exactly as written, capitals, dots and spaces kept; at most 30 characters.",
    "place": ("left_chest_as_seen or right_chest_as_seen (the chest on the left or the right of the photo as you see "
              "it, not the wearer's left), center_chest, or middle (across the middle of the front)."),
    "letter_size": "small: a mark on the chest; medium: across part of the chest; large: across the whole chest.",
    "letter_style": "sans: plain block letters; serif: letters with serifs; script: joined handwriting.",
    "letter_color": "#rrggbb of the letters.",
}

GUIDANCE = ("- Surface: fill in `surface` from a quick look. A rough answer is fine; a drawing that says less is "
            "better than a wrong one.")

# The same words for the Claude plan's route, in its prompt: that route's schema goes on Claude Code's command line,
# which Windows caps at 32,767 characters, and the surface's descriptions would take it over (`claude_cli`)
NOTES = "\n".join([
    "How to fill in `surface` (" + FIELD_TEXT["surface"] + "):",
    "- kind: " + FIELD_TEXT["kind"],
    "- bands: " + FIELD_TEXT["bands"] + " Each band: color, " + FIELD_TEXT["color"] + " width, " + FIELD_TEXT["width"],
    "- direction: " + FIELD_TEXT["direction"],
    "- size: " + FIELD_TEXT["size"],
    "- blocks: " + FIELD_TEXT["blocks"] + " Each: part (yoke, sleeves, collar or pocket) and color, " + FIELD_TEXT["color"],
    "- panels: " + FIELD_TEXT["panels"] + " Each: top, " + FIELD_TEXT["top"] + " bottom, " + FIELD_TEXT["bottom"]
    + " color, " + FIELD_TEXT["color"],
    "- colors: " + FIELD_TEXT["colors"] + " Each: color, " + FIELD_TEXT["color"] + " share, " + FIELD_TEXT["share"],
    "How to fill in `lettering`: " + FIELD_TEXT["lettering"] + " Each: text, " + FIELD_TEXT["text"] + " place, "
    + FIELD_TEXT["place"] + " size, " + FIELD_TEXT["letter_size"] + " style, " + FIELD_TEXT["letter_style"]
    + " color, " + FIELD_TEXT["letter_color"],
])
FORMS = ("Surface", "Band", "Colour", "Block", "Panel", "Lettering")   # the models above, by name

Kind = Literal["plain", "stripes", "plaid", "blocks", "other"]
Direction = Literal["horizontal", "vertical"]
# a side is as seen in the photo, and in the drawing, which faces the same way (not the wearer's left): Claude read the
# wearer's side for a chest print and the photo's for the sleeves of one tee when asked for the wearer's
Part = Literal["yoke", "sleeves", "left_sleeve_as_seen", "right_sleeve_as_seen", "collar", "pocket"]
PARTS: tuple[str, ...] = ("yoke", "sleeves", "left_sleeve_as_seen", "right_sleeve_as_seen", "collar", "pocket")
Place = Literal["left_chest_as_seen", "right_chest_as_seen", "center_chest", "middle"]
LetterSize = Literal["small", "medium", "large"]
LetterStyle = Literal["sans", "serif", "script"]
Size = Literal["micro", "tiny", "small", "medium", "large", "huge"]


class Band(BaseModel):
    color: str = Field(description=FIELD_TEXT["color"])
    width: int = Field(description=FIELD_TEXT["width"])


class Colour(BaseModel):
    color: str = Field(description=FIELD_TEXT["color"])
    share: int = Field(description=FIELD_TEXT["share"])


class Block(BaseModel):
    part: Part
    color: str = Field(description=FIELD_TEXT["color"])


class Panel(BaseModel):
    top: int = Field(description=FIELD_TEXT["top"])
    bottom: int = Field(description=FIELD_TEXT["bottom"])
    color: str = Field(description=FIELD_TEXT["color"])


class Lettering(BaseModel):
    text: str = Field(description=FIELD_TEXT["text"])
    place: Place = Field(description=FIELD_TEXT["place"])
    size: LetterSize = Field(description=FIELD_TEXT["letter_size"])
    style: LetterStyle = Field(description=FIELD_TEXT["letter_style"])
    color: str = Field(description=FIELD_TEXT["letter_color"])


class Surface(BaseModel):
    kind: Kind = Field(description=FIELD_TEXT["kind"])
    bands: list[Band] = Field(description=FIELD_TEXT["bands"])
    direction: Direction | None = Field(description=FIELD_TEXT["direction"])
    size: Size | None = Field(description=FIELD_TEXT["size"])
    blocks: list[Block] = Field(description=FIELD_TEXT["blocks"])
    panels: list[Panel] = Field(description=FIELD_TEXT["panels"])
    colors: list[Colour] = Field(description=FIELD_TEXT["colors"])


# ---- reading a stored answer without OpenCV (the drawing and the pattern job's queue use these) -------------------

def kind_of(raw) -> str | None:
    """The kind a stored surface says, or None when the answer has no usable surface (an answer from before the
    surface was asked for, or one Claude left empty)."""
    if isinstance(raw, BaseModel):
        raw = raw.model_dump()
    if not isinstance(raw, dict) or raw.get("kind") not in ("plain", "stripes", "plaid", "blocks", "other"):
        return None
    return raw["kind"]


def needs_photo(raw) -> bool:
    """Whether drawing this surface needs the item's photo, so the pattern job takes it: stripes and plaid (their
    scale and widths are read from the photo), bands across the body, and a print (pieced from the photo). Plain
    cloth and parts in another colour are drawn from the answer alone."""
    kind = kind_of(raw)
    if kind in ("stripes", "plaid", "other"):
        return True
    return kind == "blocks" and bool((raw.model_dump() if isinstance(raw, BaseModel) else raw).get("panels"))


def needs_ruler(raw) -> bool:
    """Whether the pattern job should ask for a top's landmarks: only to size stripes and plaid."""
    return kind_of(raw) in ("stripes", "plaid")


def _hex(raw) -> str | None:
    if not isinstance(raw, str):
        return None
    h = raw.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6 or any(c not in "0123456789abcdefABCDEF" for c in h):
        return None
    return "#" + h.lower()


STRENGTH = 0.8   # described colours are cleaner and stronger than cloth; the test drew them at this chroma


def softened(hex_: str, strength: float = STRENGTH) -> str:
    """A colour with its strength (CIE Lab chroma) times `strength`, lightness and hue kept; plain Python, so the
    drawing may use it."""
    h = _hex(hex_)
    if h is None:
        return hex_

    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    def gam(c):
        c = 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
        return min(255, max(0, round(c * 255)))
    r, g, b = (lin(int(h[i:i + 2], 16)) for i in (1, 3, 5))
    x, y, z = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047, 0.2126 * r + 0.7152 * g + 0.0722 * b, \
        (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116
    fx, fy, fz = f(x), f(y), f(z)
    L, A, B = 116 * fy - 16, 500 * (fx - fy) * strength, 200 * (fy - fz) * strength
    fy = (L + 16) / 116
    fx, fz = fy + A / 500, fy - B / 200

    def finv(t):
        return t ** 3 if t ** 3 > 216 / 24389 else (116 * t - 16) / (24389 / 27)
    x, y, z = finv(fx) * 0.95047, finv(fy), finv(fz) * 1.08883
    r = 3.2406 * x - 1.5372 * y - 0.4986 * z
    g = -0.9689 * x + 1.8758 * y + 0.0415 * z
    b = 0.0557 * x - 0.2040 * y + 1.0570 * z
    return "#" + "".join(f"{gam(max(0.0, c)):02x}" for c in (r, g, b))


def main_colour(raw) -> str | None:
    """The cloth's main colour from a plain, blocks or other surface (softened), or None."""
    if kind_of(raw) not in ("plain", "blocks", "other"):
        return None
    data = raw.model_dump() if isinstance(raw, BaseModel) else raw
    for c in data.get("colors") or []:
        h = _hex(c.get("color")) if isinstance(c, dict) else None
        if h:
            return softened(h)
    return None


def block_colours(raw) -> dict[str, str]:
    """The parts cut in another colour (yoke, sleeves, left_sleeve_as_seen, right_sleeve_as_seen, collar, pocket), each with its
    colour (softened), from a blocks surface; empty otherwise. Both sleeves named one by one in one colour are
    "sleeves"; a part said twice keeps its first colour."""
    if kind_of(raw) != "blocks":
        return {}
    data = raw.model_dump() if isinstance(raw, BaseModel) else raw
    out: dict[str, str] = {}
    for b in data.get("blocks") or []:
        if isinstance(b, dict) and b.get("part") in PARTS and _hex(b.get("color")) and b["part"] not in out:
            out[b["part"]] = softened(_hex(b["color"]))
    if out.get("left_sleeve_as_seen") and out["left_sleeve_as_seen"] == out.get("right_sleeve_as_seen") \
            and "sleeves" not in out:
        out["sleeves"] = out.pop("left_sleeve_as_seen")
        out.pop("right_sleeve_as_seen")
    return out


def block_parts(raw) -> tuple[tuple[str, ...], str | None]:
    """The parts cut in another colour and the first part's colour (softened), from a blocks surface; ((), None)
    otherwise (`block_colours` gives each part its own)."""
    found = block_colours(raw)
    return tuple(found), next(iter(found.values()), None)


TEXT_MAX = 30


def lettering_of(raw) -> list[dict]:
    """The lettering that can be drawn, from a stored answer's `lettering`: each {"text", "place", "size", "style",
    "color" (softened)}, at most three; text with no letter or digit, longer than TEXT_MAX or with an unknown place
    is left out."""
    out = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, BaseModel):
            item = item.model_dump()
        if not isinstance(item, dict):
            continue
        text = " ".join(str(item.get("text") or "").split())
        if not text or len(text) > TEXT_MAX or not any(c.isalnum() for c in text):
            continue
        if item.get("place") not in get_args(Place):
            continue
        out.append({"text": text, "place": item["place"],
                    "size": item.get("size") if item.get("size") in get_args(LetterSize) else "medium",
                    "style": item.get("style") if item.get("style") in get_args(LetterStyle) else "sans",
                    "color": softened(_hex(item.get("color")) or "#222222")})
    return out[:3]


# ---- the owner's own words about the cloth (`items.own_cloth`, laid over Claude's answer) ----------------------------

def own_cloth(row) -> dict:
    """The owner's cloth and lettering for an item row: {"surface": ..., "lettering": [...]}, each key only when the
    owner set it (an empty dict when they set neither, or the row has no such column)."""
    import json
    try:
        keys = row.keys()
        text = row["own_cloth"] if "own_cloth" in keys else None
        data = json.loads(text) if text else {}
    except (ValueError, TypeError, AttributeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    if kind_of(data.get("surface")) is not None:
        out["surface"] = data["surface"]
    if isinstance(data.get("lettering"), list):
        out["lettering"] = data["lettering"]
    return out


# ---- the cloth in plain words (a correction's before and after, the item's history) ---------------------------------

# the closet's colour words and their shades (`schema.NAMED_HEX`: a test keeps the two equal; schema imports this module)
COLOUR_WORDS = {"black": "#1f1f22", "white": "#f6f5f2", "grey": "#8f9296", "navy": "#27344f", "blue": "#3f6fb0",
                "light_blue": "#a9c3e0", "green": "#3f7d4f", "olive": "#6b6f45", "tan": "#c2a878", "brown": "#6b4a2f",
                "cream": "#ece4d0", "red": "#b8332e", "burgundy": "#6e2633", "pink": "#e3a6b4", "orange": "#d9772b",
                "yellow": "#e3c341", "purple": "#6a4c93"}
PART_WORDS = {"yoke": "yoke", "sleeves": "sleeves", "left_sleeve_as_seen": "sleeve on the left",
              "right_sleeve_as_seen": "sleeve on the right", "collar": "collar", "pocket": "pocket"}
PLACE_WORDS = {"left_chest_as_seen": "on the chest, on the left", "right_chest_as_seen": "on the chest, on the right",
               "center_chest": "across the chest", "middle": "across the middle"}


def colour_word(hex_) -> str:
    """The nearest of the closet's colour words to a colour, in words ("light blue")."""
    h = _hex(hex_)
    if h is None:
        return "an unknown colour"
    rgb = [int(h[i:i + 2], 16) for i in (1, 3, 5)]
    best = min(COLOUR_WORDS, key=lambda w: sum((a - int(COLOUR_WORDS[w][i:i + 2], 16)) ** 2
                                               for a, i in zip(rgb, (1, 3, 5), strict=True)))
    return best.replace("_", " ")


def _colours_in_words(hexes) -> str:
    words = list(dict.fromkeys(colour_word(h) for h in hexes))
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1] if words else ""


def surface_words(raw) -> str:
    """A described surface in plain words: "plain green with a red left sleeve and a blue right sleeve"."""
    kind = kind_of(raw)
    if kind is None:
        return "not described"
    data = raw.model_dump() if isinstance(raw, BaseModel) else raw
    colours = [c.get("color") for c in data.get("colors") or [] if isinstance(c, dict)]
    bands = [b.get("color") for b in data.get("bands") or [] if isinstance(b, dict)]
    if kind == "plain":
        return f"plain {colour_word(colours[0])}" if colours else "plain"
    if kind == "stripes":
        way = {"horizontal": "stripes across", "vertical": "stripes down"}.get(data.get("direction"), "stripes")
        return f"{way} in {_colours_in_words(bands)}" if bands else way
    if kind == "plaid":
        return f"a check in {_colours_in_words(bands)}" if bands else "a check"
    if kind == "other":
        return f"a print in {_colours_in_words(colours)}" if colours else "a print"
    body = f"plain {colour_word(colours[0])}" if colours else "plain"
    said = [f"{colour_word(c)} {PART_WORDS[p]}" for p, c in
            ((b.get("part"), b.get("color")) for b in data.get("blocks") or [] if isinstance(b, dict)) if p in PART_WORDS]
    said += [f"a {colour_word(q.get('color'))} band across the body" for q in data.get("panels") or [] if isinstance(q, dict)]
    return body + (" with " + ", ".join(said) if said else "")


def lettering_words(raw) -> str:
    """Lettering in plain words: '"A.P.C." in navy on the left chest'; "no lettering" for none."""
    found = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, BaseModel):
            item = item.model_dump()
        if isinstance(item, dict) and item.get("text"):
            found.append(f"“{item['text']}” in {colour_word(item.get('color'))} {PLACE_WORDS.get(item.get('place'), '')}".strip())
    return "; ".join(found) if found else "no lettering"


def own_cloth_words(value) -> str:
    """The owner's cloth and lettering (`own_cloth`) in words; "Claude's" for what they have not set."""
    value = value if isinstance(value, dict) else {}
    parts = []
    if "surface" in value:
        parts.append("cloth: " + surface_words(value["surface"]))
    if "lettering" in value:
        parts.append("lettering: " + lettering_words(value["lettering"]))
    return "; ".join(parts) if parts else "as Claude described it"
