"""The cloth's surface, as Claude describes it on the description call: one kind of pattern with only that kind's
fields filled, for the app's own drawing (`closet.patterns.surface` turns it into what the drawing takes).

The form is the "second form" of the garment loop test (`bench/experiments/garment_loop`, arm F), adopted by the
owner on 18 November: stripes, plaid and checks as one repeat of bands; plain cloth with parts or bands across the
body in other colours; plain; or "other" for a print, which the app pieces from the photo. Plain data only: the
drawing imports it, so nothing here may import OpenCV.
"""
from __future__ import annotations

from typing import Literal

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
    "blocks": "blocks only, else empty: each part cut in another colour than the body.",
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
])
FORMS = ("Surface", "Band", "Colour", "Block", "Panel")   # the models above, by name

Kind = Literal["plain", "stripes", "plaid", "blocks", "other"]
Direction = Literal["horizontal", "vertical"]
Part = Literal["yoke", "sleeves", "collar", "pocket"]
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


def block_parts(raw) -> tuple[tuple[str, ...], str | None]:
    """The parts cut in another colour (yoke, sleeves, collar, pocket) and that colour (softened), from a blocks
    surface; ((), None) otherwise. The drawing has one block colour: the first part's."""
    if kind_of(raw) != "blocks":
        return (), None
    data = raw.model_dump() if isinstance(raw, BaseModel) else raw
    parts, colour = [], None
    for b in data.get("blocks") or []:
        if isinstance(b, dict) and b.get("part") in ("yoke", "sleeves", "collar", "pocket") and _hex(b.get("color")):
            if b["part"] not in parts:
                parts.append(b["part"])
            colour = colour or softened(_hex(b["color"]))
    return tuple(parts), colour
