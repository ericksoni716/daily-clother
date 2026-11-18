"""A garment's surface described by Claude as parameters for the app's own drawing. AN EXPERIMENT
(`bench/experiments/garment_loop`), not called by the app.

One general form instead of one per pattern: bands one way (stripes), bands both ways (plaid, check, gingham,
tartan, madras), plain cloth with parts in another colour (blocks), plain, and "other" for what the form cannot
express, which is drawn as its main colour only (saying less). Plaids are woven as `described` weaves them, with
its defaults (the scale and the band widths read from the photo, colours softened); stripes are woven the same way
along one direction and sized the same way, from the photo's band spacing against the same ruler. Every described
colour is softened as `described` softens a plaid's: described colours are cleaner and stronger than cloth.

The ruler for every count: the chest from underarm to underarm on a top (the landmarks the app asks for), the
waistband's width on trousers and shorts (read from the cutout). `drawn` turns a description into what the
drawing takes: a kept pattern (`closet.drawing.stored`), the body's colour, and the parts cut in another colour.
"""
from __future__ import annotations

from typing import Literal

import numpy as np
from PIL import Image
from pydantic import BaseModel, Field

from ..drawing.stored import VERSION, tile_text
from . import described
from .described import Band

# ---- the form ---------------------------------------------------------------------------------------------

FIELD_TEXT = {
    "surface": "The cloth's surface, so the app can draw it: one kind, with only that kind's fields filled.",
    "kind": ("plain: one colour. stripes: bands running one way. plaid: bands both ways, crossing (plaid, check, "
             "gingham, tartan, madras, windowpane). blocks: plain cloth with whole parts in another colour (yoke, "
             "sleeves, collar, pocket). other: anything else (florals, camouflage, paisley, other prints, colour "
             "blocking the parts cannot say). When unsure, say less: plain or other."),
    "bands": "stripes and plaid only, else empty: one repeat's bands, ground first. A thin line is width 1.",
    "direction": "stripes only, else null: horizontal (running side to side) or vertical.",
    "size": ("stripes and plaid only, else null: how many repeats fit across the chest (trousers and shorts: across "
             "the waist), counted the way the bands repeat: tiny more than 8, small 5-8, medium 3-5, large 2-3, "
             "huge under 2."),
    "blocks": "blocks only, else empty: each part cut in another colour than the body.",
    "colors": ("plain, blocks and other, else empty: the main colours, the body's first, each with a whole-number "
               "share of the cloth."),
    "color": "#rrggbb as it looks on this cloth.",
    "share": "Whole number; how much of the cloth it covers, against the others.",
}

GUIDANCE = ("- Surface: fill in `surface` from a quick look. A rough answer is fine; a drawing that says less is "
            "better than a wrong one.")

Kind = Literal["plain", "stripes", "plaid", "blocks", "other"]
Direction = Literal["horizontal", "vertical"]
Part = Literal["yoke", "sleeves", "collar", "pocket"]
PARTS = ("yoke", "sleeves", "collar", "pocket")


class Colour(BaseModel):
    color: str = Field(description=FIELD_TEXT["color"])
    share: int = Field(description=FIELD_TEXT["share"])


class Block(BaseModel):
    part: Part
    color: str = Field(description=FIELD_TEXT["color"])


class Surface(BaseModel):
    kind: Kind = Field(description=FIELD_TEXT["kind"])
    bands: list[Band] = Field(description=FIELD_TEXT["bands"])
    direction: Direction | None = Field(description=FIELD_TEXT["direction"])
    size: described.Size | None = Field(description=FIELD_TEXT["size"])
    blocks: list[Block] = Field(description=FIELD_TEXT["blocks"])
    colors: list[Colour] = Field(description=FIELD_TEXT["colors"])


# ---- reading an answer safely -----------------------------------------------------------------------------

KINDS = ("plain", "stripes", "plaid", "blocks", "other")
SCALE = (0.5, 2.0)     # how far one correction may make the repeat bigger or smaller


def _colours(raw) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    for c in raw if isinstance(raw, list) else []:
        if isinstance(c, BaseModel):
            c = c.model_dump()
        if not isinstance(c, dict):
            continue
        hex_ = described._hex(c.get("color"))
        try:
            share = float(c.get("share", 1))
        except (TypeError, ValueError):
            share = 1.0
        if hex_ and np.isfinite(share) and share > 0:
            out.append((hex_, share))
    return out[:8]


def _blocks(raw) -> list[tuple[str, str]]:
    out: dict[str, str] = {}
    for b in raw if isinstance(raw, list) else []:
        if isinstance(b, BaseModel):
            b = b.model_dump()
        if isinstance(b, dict) and b.get("part") in PARTS and described._hex(b.get("color")):
            out.setdefault(b["part"], described._hex(b["color"]))
    return list(out.items())


def read(raw) -> dict | None:
    """A description made safe to draw: {"kind", "bands": [(hex, width)], "direction", "size", "blocks":
    [(part, hex)], "colors": [(hex, share)], "fell": why it was drawn as less than it said, or None}. A kind
    that cannot be drawn as said falls to saying less: stripes with no direction or one colour, a plaid with one
    colour, blocks with no part, all become plain cloth in their main colour ("other" when it was a pattern).
    None when there is no colour at all."""
    if isinstance(raw, BaseModel):
        raw = raw.model_dump()
    if not isinstance(raw, dict):
        return None
    kind = raw.get("kind") if raw.get("kind") in KINDS else "other"
    bands = described._bands(raw.get("bands"))
    colours = _colours(raw.get("colors"))
    blocks = _blocks(raw.get("blocks"))
    direction = raw.get("direction") if raw.get("direction") in ("horizontal", "vertical") else None
    size = raw.get("size") if raw.get("size") in described.SIZE_REPEATS else None
    fell = None
    if kind in ("stripes", "plaid") and len({c for c, _ in bands}) < 2:
        kind, fell = "other", f"a {raw.get('kind')} with fewer than two colours"
    elif kind == "stripes" and direction is None:
        kind, fell = "other", "stripes with no direction"
    elif kind == "blocks" and not blocks:
        kind, fell = "plain", "blocks with no part"
    if not colours and bands:      # the main colours of a pattern drawn as less: its bands' shares
        totals: dict[str, float] = {}
        for c, w in bands:
            totals[c] = totals.get(c, 0.0) + w
        colours = sorted(totals.items(), key=lambda kv: -kv[1])
    if not colours:
        return None
    return {"kind": kind, "bands": bands, "direction": direction, "size": size, "blocks": blocks,
            "colors": colours, "fell": fell}


def patched(raw: dict, patch) -> dict:
    """A description with a correction's patch laid over it: each field the patch gives replaces the current
    one whole; fields it leaves null stay. `scale` is not part of the description (see `drawn`)."""
    if isinstance(patch, BaseModel):
        patch = patch.model_dump()
    out = dict(raw)
    for key in ("kind", "bands", "direction", "size", "blocks", "colors"):
        if isinstance(patch, dict) and patch.get(key) is not None:
            out[key] = patch[key]
    return out


def scale_of(patch) -> float:
    """The patch's change to the repeat's size, kept within SCALE (1 = no change)."""
    if isinstance(patch, BaseModel):
        patch = patch.model_dump()
    try:
        s = float(patch.get("scale")) if isinstance(patch, dict) and patch.get("scale") is not None else 1.0
    except (TypeError, ValueError):
        return 1.0
    return float(np.clip(s, *SCALE)) if np.isfinite(s) and s > 0 else 1.0


# ---- the ruler and the scale from the photo ---------------------------------------------------------------

def waist_ruler(cut: Image.Image) -> dict | None:
    """A pair of trousers' or shorts' ruler as two points (the landmarks' shape, `underarm_left` and
    `underarm_right`, so `described.photo_repeats` reads it as it reads a top's chest): the ends of the garment's
    widest row in the top 6% of its height, where the waistband is."""
    a = np.asarray(cut.convert("RGBA"))[..., 3] > 128
    rows = np.where(a.any(1))[0]
    if len(rows) < 20:
        return None
    top, h = rows[0], rows[-1] - rows[0]
    best = None
    for y in range(top, top + max(2, int(0.06 * h))):
        xs = np.where(a[y])[0]
        if len(xs) and (best is None or xs[-1] - xs[0] > best[2] - best[1]):
            best = (y, xs[0], xs[-1])
    if best is None:
        return None
    y, x0, x1 = best
    return {"underarm_left": {"x": float(x0), "y": float(y)}, "underarm_right": {"x": float(x1), "y": float(y)}}


def stripe_repeats(cut: Image.Image, ruler: dict | None, direction: str) -> float | None:
    """How many repeats of a stripe fit in one ruler's length, read from the photo: the shortest spacing at which
    the garment's band sequence repeats the way the stripes do (down the body for horizontal stripes, across for
    vertical), against the ruler. None when the photo shows no repeat."""
    try:
        a, b = ruler["underarm_left"], ruler["underarm_right"]
        length = float(np.hypot(a["x"] - b["x"], a["y"] - b["y"]))
    except (KeyError, TypeError):
        return None
    from .common import to_lab
    from .straighten import _mask, _spacings
    arr = np.asarray(cut.convert("RGBA"))
    m = _mask(arr)
    if m.sum() < 400 or length <= 0:
        return None
    lab = to_lab(np.ascontiguousarray(arr[..., :3]))
    found = _spacings(lab, m, direction == "vertical", max(3, int(0.01 * max(m.shape))))
    if not found:
        return None
    return float(np.clip(length / found[0], *described.REPEATS))


# ---- drawing it -------------------------------------------------------------------------------------------

STRENGTH = described.STRENGTH
# On trousers and shorts a tile is sized against the outline's width (they have no neck-to-hem line): the
# waistband (the widest row in the top 6% of the drawing) is this share of it, measured on the demo closet's
# trousers, jeans and shorts drawn by the app's templates (0.875 to 0.89 on six trousers and jeans, 0.73 on shorts)
WAIST_PER_OUTLINE = {"trousers": 0.885, "jeans": 0.885, "shorts": 0.73}


def _soft(hex_: str, strength: float = STRENGTH) -> str:
    return described.softened({"across": [(hex_, 1.0)], "down": [(hex_, 1.0)]}, strength)["across"][0][0]


def _stripe_tile(bands: list[tuple[str, float]], direction: str) -> np.ndarray:
    """One repeat of stripes as a square RGB image, the bands running the given way, edges softened as a woven
    band's are (`described._sequence`)."""
    n = described.SIDE
    seq = described._sequence(bands, n, n / sum(w for _, w in bands))
    import cv2
    rgb = cv2.cvtColor(np.clip(seq, 0, 255).round().astype(np.uint8)[None], cv2.COLOR_LAB2RGB)[0]
    return np.repeat(rgb[:, None, :], n, 1) if direction == "horizontal" else np.repeat(rgb[None, :, :], n, 0)


def _kept_tile(img: np.ndarray, repeats: float, bottom: str | None, first: tuple[float, float], how: str) -> dict:
    per = WAIST_PER_OUTLINE.get(bottom, 0.885) / repeats if bottom else described.CHEST_PER_OUTLINE / repeats
    return {"kind": "tile", "how": how, "image": tile_text(Image.fromarray(img), quality=92),
            "width_frac": round(per, 4), "length_frac": None if bottom else round(described.CHEST_PER_LENGTH / repeats, 4),
            "phase": [round(first[0], 4), round(first[1], 4)], "phase_right": None, "version": VERSION}


def drawn(desc: dict, cut: Image.Image | None, ruler: dict | None, bottom: str | None = None, scale: float = 1.0,
          strength: float = STRENGTH) -> dict:
    """What the drawing takes for a description `read` gave: {"kept": a kept pattern or None, "body": the
    cloth's colour, "blocks": [(part, hex)], "repeats": repeats across the ruler as drawn (None for no pattern),
    "scale_how": "photo" | "said", "widths": "photo" | "said" | None, "tile": the repeat as an RGB array or None,
    "not_drawn": True when the cloth is a pattern the form cannot express}. `ruler` is a top's landmarks or
    `waist_ruler` of a bottom, `bottom` the category of trousers, jeans or shorts (None for a top), `scale` the size
    of the repeat against what the photo or the size word gives (2 = twice as big)."""
    kind = desc["kind"]
    out = {"kept": None, "body": _soft(desc["colors"][0][0], strength), "blocks": [], "repeats": None,
           "scale_how": None, "widths": None, "tile": None, "not_drawn": kind == "other"}
    if kind == "blocks":
        out["blocks"] = [(p, _soft(c, strength)) for p, c in desc["blocks"]]
    if kind not in ("stripes", "plaid"):
        return out
    repeats = described.SIZE_REPEATS.get(desc["size"] or "medium", 4.0)
    how = "said"
    if kind == "plaid":
        d = {"across": list(desc["bands"]), "down": list(desc["bands"]), "repeats": repeats}
        seen = described.photo_repeats(cut, ruler) if cut is not None and ruler else None
        if seen is not None:
            repeats, how = seen[0], "photo"
        fitted = described.photo_widths(d, cut) if cut is not None else None
        if fitted is not None:
            d = fitted[0]
        img = described.weave(described.softened(d, strength))
        first = (d["across"][0][1] / 2 / sum(w for _, w in d["across"]), d["down"][0][1] / 2 / sum(w for _, w in d["down"]))
        out["widths"] = "photo" if fitted else "said"
    else:
        seen = stripe_repeats(cut, ruler, desc["direction"]) if cut is not None and ruler else None
        if seen is not None:
            repeats, how = seen, "photo"
        bands = [(_soft(c, strength), w) for c, w in desc["bands"]]
        img = _stripe_tile(bands, desc["direction"])
        half = bands[0][1] / 2 / sum(w for _, w in bands)
        first = (half, 0.0) if desc["direction"] == "vertical" else (0.0, half)
        out["widths"] = "said"
    repeats = float(np.clip(repeats / scale, *described.REPEATS))
    out.update(kept=_kept_tile(img, repeats, bottom, first, "described"), repeats=repeats, scale_how=how, tile=img)
    return out
