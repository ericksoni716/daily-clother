"""A garment's surface described by Claude as parameters for the app's own drawing. First an experiment
(`bench/experiments/garment_loop`, now only in the git history); the app uses it since 18 November: the pattern
job keeps what `kept_for_item` makes of the description (DECISIONS, "The cloth drawn from its description").

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
from ..tagger import surfaceform
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


# ---- the second form (after the tuning half; DESIGN.md, log of changes) ---------------------------------------
# Three gaps every arm shared on the tuning half: colour blocks the parts could not name (a panel across the chest,
# wavy bands, a stripe at the join), prints drawn as their main colour (the app's own piecing from the photo did far
# better), and fine patterns past 16 repeats across. The second form adds bands across the body to `blocks`, a
# finer size word, and says that "other" is pieced from the photo; `drawn(..., second=True)` draws them.

# The second form is the one the app asks for (`closet.tagger.surfaceform`, plain data the drawing may import);
# the names below keep the bench's harness working.
FIELD_TEXT_2 = surfaceform.FIELD_TEXT
Size2 = surfaceform.Size
Panel = surfaceform.Panel
Surface2 = surfaceform.Surface


# ---- reading an answer safely -----------------------------------------------------------------------------

KINDS = ("plain", "stripes", "plaid", "blocks", "other")
SCALE = (0.5, 2.0)     # how far one correction may make the repeat bigger or smaller
# the second form's size words as repeats across the ruler, and the most repeats it draws (the first form keeps
# `described`'s words and its cap of 16)
SIZE_REPEATS_2 = {**described.SIZE_REPEATS, "micro": 40.0, "tiny": 13.0}
REPEATS_2 = (0.5, 150.0)
MAX_PANELS = 6


def _panels(raw) -> list[tuple[float, float, str]]:
    """Bands across the body as (top, bottom) fractions of collar to hem and a colour; nonsense dropped."""
    out = []
    for p in raw if isinstance(raw, list) else []:
        if isinstance(p, BaseModel):
            p = p.model_dump()
        if not isinstance(p, dict) or not described._hex(p.get("color")):
            continue
        try:
            top, bottom = (float(np.clip(float(p.get(k)), 0, 100)) / 100 for k in ("top", "bottom"))
        except (TypeError, ValueError):
            continue
        if bottom - top >= 0.02:
            out.append((top, bottom, described._hex(p["color"])))
    return sorted(out)[:MAX_PANELS]


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
    panels = _panels(raw.get("panels"))
    direction = raw.get("direction") if raw.get("direction") in ("horizontal", "vertical") else None
    size = raw.get("size") if raw.get("size") in SIZE_REPEATS_2 else None
    fell = None
    if kind in ("stripes", "plaid") and len({c for c, _ in bands}) < 2:
        kind, fell = "other", f"a {raw.get('kind')} with fewer than two colours"
    elif kind == "stripes" and direction is None:
        kind, fell = "other", "stripes with no direction"
    elif kind == "blocks" and not blocks and not panels:
        kind, fell = "plain", "blocks with no part"
    if not colours and bands:      # the main colours of a pattern drawn as less: its bands' shares
        totals: dict[str, float] = {}
        for c, w in bands:
            totals[c] = totals.get(c, 0.0) + w
        colours = sorted(totals.items(), key=lambda kv: -kv[1])
    if not colours:
        return None
    return {"kind": kind, "bands": bands, "direction": direction, "size": size, "blocks": blocks,
            "panels": panels, "colors": colours, "fell": fell}


def patched(raw: dict, patch) -> dict:
    """A description with a correction's patch laid over it: each field the patch gives replaces the current
    one whole; fields it leaves null stay. `scale` is not part of the description (see `drawn`)."""
    if isinstance(patch, BaseModel):
        patch = patch.model_dump()
    out = dict(raw)
    for key in ("kind", "bands", "direction", "size", "blocks", "panels", "colors"):
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


# A top's chest (between the landmarks' underarms) is about this share of its cutout's width: 0.61 is the median
# over the garment loop test's 49 tops with landmarks, 84% of them within 15% of it and 94% within 25%
CHEST_PER_CUTOUT = 0.61


def outline_ruler(cut: Image.Image) -> dict | None:
    """A top's chest ruler when its landmarks could not be had (Claude out of reach): CHEST_PER_CUTOUT of the
    cutout's width, centred, a third of the way down, in the landmarks' shape."""
    a = np.asarray(cut.convert("RGBA"))[..., 3] > 128
    xs, ys = np.where(a.any(0))[0], np.where(a.any(1))[0]
    if len(xs) < 20 or len(ys) < 20:
        return None
    mid, half = (xs[0] + xs[-1]) / 2, CHEST_PER_CUTOUT * (xs[-1] - xs[0]) / 2
    y = float(ys[0] + (ys[-1] - ys[0]) / 3)
    return {"underarm_left": {"x": float(mid - half), "y": y}, "underarm_right": {"x": float(mid + half), "y": y}}


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


def _stripe_repeats_unclipped(cut, ruler, direction, least_frac=0.01):
    """`stripe_repeats` without the first form's cap (the second form's fine reading needs the raw count)."""
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
    found = _spacings(to_lab(np.ascontiguousarray(arr[..., :3])), m, direction == "vertical",
                      max(3, int(least_frac * max(m.shape))))
    return length / found[0] if found else None


def plaid_repeats_2(cut: Image.Image, ruler: dict | None) -> float | None:
    """`described.photo_repeats`, the same reading, with the second form's cap (REPEATS_2) instead of 16."""
    try:
        a, b = ruler["underarm_left"], ruler["underarm_right"]
        chest = float(np.hypot(a["x"] - b["x"], a["y"] - b["y"]))
    except (KeyError, TypeError):
        return None
    from .common import to_lab
    from .straighten import _mask, _spacings
    arr = np.asarray(cut.convert("RGBA"))
    m = _mask(arr)
    if m.sum() < 400 or not (0.15 * arr.shape[1] < chest <= arr.shape[1]):
        return None
    lab = to_lab(np.ascontiguousarray(arr[..., :3]))
    least = max(5, int(0.03 * max(m.shape)))
    across, down = _spacings(lab, m, True, least), _spacings(lab, m, False, least)
    pairs = [(max(p, q) / min(p, q), (p + q) / 2) for p in across for q in down]
    near = min(pairs, default=None)
    if near is not None and near[0] <= described.SQUARE:
        return float(np.clip(chest / near[1], *REPEATS_2))
    if down and chest / down[0] >= 1:
        return float(np.clip(chest / down[0], *REPEATS_2))
    return None


FINE_CROP = 400     # px: the fine reading looks at this square of the cloth at the photo's own detail
FINE_AT_LEAST = 12  # repeats across: a fine reading that finds fewer is not a fine pattern, and is not used
FINE_STRONG = 8.0   # for a size word bigger than tiny, the fine repeat must swing the cloth's colour at least this
#                     much (Lab, 0 to 255): the owner's linen pinstripe swings 21, a plain knit's own stitches 3


def _swing(lab: np.ndarray, m: np.ndarray, across: bool, spacing: int) -> float:
    """How far the cloth's colour swings at a repeat of `spacing` px: the colour along the bands (their median, so
    a crease counts little), less its slow change over three repeats, from its 5th to its 95th percentile."""
    import warnings

    import cv2
    with warnings.catch_warnings():   # a line of the square outside the garment has no colour: it is left out
        warnings.simplefilter("ignore", RuntimeWarning)
        prof = np.stack([np.nanmedian(np.where(m, lab[..., c], np.nan), axis=0 if across else 1) for c in range(3)], 1)
    prof = prof[~np.isnan(prof).any(1)].astype(np.float32)
    if len(prof) < 3 * spacing:
        return 0.0
    k = max(3, 3 * spacing) | 1
    rest = prof - np.stack([cv2.blur(prof[:, c].reshape(1, -1), (k, 1)).ravel() for c in range(3)], 1)
    return float(np.linalg.norm(np.percentile(rest, 95, axis=0) - np.percentile(rest, 5, axis=0)))


def fine_repeats(cut: Image.Image, ruler: dict | None, across: bool, strong: float = 0.0) -> float | None:
    """The repeat read from a square of cloth in the middle of the garment at the photo's own detail (the
    whole-garment reading works on a picture shrunk to 420 px, where a check a few pixels wide, or a pinstripe, is
    gone). None unless it finds at least FINE_AT_LEAST repeats across the ruler, and, with `strong`, unless the
    colour swings at least that much at that repeat (`_swing`), so a weave or knit is not taken for a pattern."""
    try:
        a, b = ruler["underarm_left"], ruler["underarm_right"]
        length = float(np.hypot(a["x"] - b["x"], a["y"] - b["y"]))
    except (KeyError, TypeError):
        return None
    from .common import to_lab
    from .straighten import _mask, _spacings
    arr = np.asarray(cut.convert("RGBA"))
    m = _mask(arr)
    ys, xs = np.where(m)
    if len(xs) < 400:
        return None
    side = min(FINE_CROP, int(xs.max() - xs.min()), int(ys.max() - ys.min()))
    cy, cx = int(np.median(ys)), int(np.median(xs))
    y0, x0 = max(0, cy - side // 2), max(0, cx - side // 2)
    crop, mc = arr[y0:y0 + side, x0:x0 + side], m[y0:y0 + side, x0:x0 + side]
    if mc.mean() < 0.6:
        return None
    lab = to_lab(np.ascontiguousarray(crop[..., :3]))
    found = _spacings(lab, mc, across, 3)
    if not found:
        return None
    if strong and _swing(lab.astype(np.float32), mc, across, int(found[0])) < strong:
        return None
    reps = length / found[0]
    return float(min(reps, REPEATS_2[1])) if reps >= FINE_AT_LEAST else None


def panel_tile(panels: list[tuple[float, float, str]], body: str, aspect: float, strength: float = STRENGTH,
               width: int = 360) -> np.ndarray:
    """A garment-sized picture for bands across the body: the body colour with each band from its top to its
    bottom (fractions of the garment's height, collar to hem), edges softened a little; `aspect` is the drawn
    garment's height over its width, so the picture laid over the garment once fits it."""
    import cv2
    h = max(8, int(round(width * aspect)))
    lab = np.zeros((h, 3), np.float32)
    lab[:] = described._lab([_soft(body, strength)])[0]
    for top, bottom, colour in panels:
        lab[int(top * h):max(int(top * h) + 1, int(bottom * h))] = described._lab([_soft(colour, strength)])[0]
    lab = cv2.GaussianBlur(lab[None], (0, 0), max(0.6, 0.003 * h))[0] if h > 8 else lab
    rgb = cv2.cvtColor(np.clip(lab, 0, 255).round().astype(np.uint8)[None], cv2.COLOR_LAB2RGB)[0]
    return np.repeat(rgb[:, None, :], width, 1)


def drawn(desc: dict, cut: Image.Image | None, ruler: dict | None, bottom: str | None = None, scale: float = 1.0,
          strength: float = STRENGTH, second: bool = False, pieced: dict | None = None,
          aspect: float | None = None) -> dict:
    """What the drawing takes for a description `read` gave: {"kept": a kept pattern or None, "body": the
    cloth's colour, "blocks": [(part, hex)], "repeats": repeats across the ruler as drawn (None for no pattern),
    "scale_how": "photo" | "fine" | "said", "widths": "photo" | "said" | None, "tile": the repeat as an RGB
    array or None, "not_drawn": True when the cloth is a pattern the form cannot express}. `ruler` is a top's
    landmarks or `waist_ruler` of a bottom, `bottom` the category of trousers, jeans or shorts (None for a top),
    `scale` the size of the repeat against what the photo or the size word gives (2 = twice as big).

    With `second` (the second form): bands across the body are drawn as one garment-sized picture (`aspect`, the
    drawn garment's height over its width, needed for that), "other" is drawn as `pieced` (the app's own print
    pieced from the photo, `measure`'s kept tile) when there is one, the size words and cap are the second
    form's, and the pattern is read from the photo at its own detail first (`fine_repeats`; for a size word bigger
    than tiny only a repeat with a real swing of colour counts)."""
    kind = desc["kind"]
    out = {"kept": None, "body": _soft(desc["colors"][0][0], strength), "blocks": [], "repeats": None,
           "scale_how": None, "widths": None, "tile": None, "not_drawn": kind == "other"}
    if kind == "blocks":
        out["blocks"] = [(p, _soft(c, strength)) for p, c in desc["blocks"]]
        if second and desc.get("panels") and aspect:
            img = panel_tile(desc["panels"], desc["colors"][0][0], aspect, strength)
            out["kept"] = {"kind": "tile", "how": "panels", "image": tile_text(Image.fromarray(img), quality=92),
                           "width_frac": 1.0, "length_frac": None, "phase": None, "phase_right": None,
                           "version": VERSION}
    if kind == "other" and second and pieced:
        out.update(kept=pieced, not_drawn=False)
    if kind not in ("stripes", "plaid"):
        return out
    words = SIZE_REPEATS_2 if second else described.SIZE_REPEATS
    cap = REPEATS_2 if second else described.REPEATS
    repeats = words.get(desc["size"] or "medium", 4.0)
    how = "said"
    fine = None
    if second and cut is not None and ruler:
        # whatever the size word: Claude's word is often wrong (Sonnet says "small" for 2 to 38 repeats) and the
        # whole-garment reading below cannot see a pinstripe (the owner's linen shirt, called small: 2.6 repeats for
        # 48). For a word bigger than tiny the fine repeat must also be a real band, not the weave (FINE_STRONG)
        tiny = desc["size"] in ("micro", "tiny")
        fine = fine_repeats(cut, ruler, kind == "plaid" or desc["direction"] == "vertical", 0.0 if tiny else FINE_STRONG)
        if fine is not None:
            repeats, how = fine, "fine"
    if kind == "plaid":
        d = {"across": list(desc["bands"]), "down": list(desc["bands"]), "repeats": repeats}
        if fine is None and cut is not None and ruler:
            if second:
                seen = plaid_repeats_2(cut, ruler)
            else:
                seen = described.photo_repeats(cut, ruler)
                seen = seen[0] if seen else None
            if seen is not None:
                repeats, how = seen, "photo"
        fitted = described.photo_widths(d, cut) if cut is not None else None
        if fitted is not None:
            d = fitted[0]
        img = described.weave(described.softened(d, strength))
        first = (d["across"][0][1] / 2 / sum(w for _, w in d["across"]), d["down"][0][1] / 2 / sum(w for _, w in d["down"]))
        out["widths"] = "photo" if fitted else "said"
    else:
        if fine is None and cut is not None and ruler:
            seen = _stripe_repeats_unclipped(cut, ruler, desc["direction"]) if second else stripe_repeats(cut, ruler, desc["direction"])
            if seen is not None:
                repeats, how = seen, "photo"
        bands = [(_soft(c, strength), w) for c, w in desc["bands"]]
        img = _stripe_tile(bands, desc["direction"])
        half = bands[0][1] / 2 / sum(w for _, w in bands)
        first = (half, 0.0) if desc["direction"] == "vertical" else (0.0, half)
        out["widths"] = "said"
    repeats = float(np.clip(repeats / scale, *cap))
    out.update(kept=_kept_tile(img, repeats, bottom, first, "described"), repeats=repeats, scale_how=how, tile=img)
    return out


# ---- in the app: what the pattern job keeps for a described surface (`patjobs`, how "surface") -------------------

BOTTOMS = ("jeans", "trousers", "shorts")


def panel_stripes(desc: dict, strength: float = STRENGTH) -> dict | None:
    """Bands across the body as the app's kept stripes: one set of horizontal bands over the garment's whole height,
    not repeated, the body's colour between them (`closet.drawing.stored`, kind "stripes"). Overlapping bands are
    cut where the one above ends. None when nothing is left."""
    body = _soft(desc["colors"][0][0], strength)
    bands: list[list] = []
    at = 0.0
    for top, bottom, colour in desc.get("panels") or []:
        top = max(top, at)
        if bottom - top < 0.01:
            continue
        if top - at >= 0.005:
            bands.append([body, top - at])
        bands.append([_soft(colour, strength), bottom - top])
        at = bottom
    if not bands:
        return None
    if 1 - at >= 0.005:
        bands.append([body, 1 - at])
    merged: list[list] = []
    for c, f in bands:
        if merged and merged[-1][0] == c:
            merged[-1][1] += f
        else:
            merged.append([c, f])
    total = sum(f for _, f in merged)
    return {"kind": "stripes", "how": "panels", "orientation": "horizontal",
            "bands": [[c, round(f / total, 6)] for c, f in merged], "trim_bands": None, "sleeves_banded": True,
            "version": VERSION}


def kept_for_item(cut: Image.Image, raw, landmarks: dict | None, category: str | None) -> dict | None:
    """The kept pattern for an item whose description carries a surface (the second form): stripes and plaid
    woven and sized from the photo (`drawn(..., second=True)`, with a top's landmarks or a bottom's waistband as the
    ruler), bands across the body as `panel_stripes`, a print pieced from the photo by the app's own measuring.
    None when the surface draws no pattern (plain, or parts in another colour, which the drawing takes from the
    answer). A top without landmarks is sized against `outline_ruler`."""
    desc = read(raw)
    if surfaceform.kind_of(raw) == "other" or (desc is not None and desc["kind"] == "other"):
        # a print, or stripes or a plaid said too thinly to weave: the app's own print piecing from the photo, which
        # needs no colour from the answer (a print described with no colours is still pieced)
        from .measure import measure
        return measure(cut, "floral")
    if desc is None:
        return None
    if desc["kind"] == "blocks":
        return panel_stripes(desc) if desc.get("panels") else None
    if desc["kind"] not in ("stripes", "plaid"):
        return None
    bottom = category if category in BOTTOMS else None
    ruler = waist_ruler(cut) if bottom else landmarks or outline_ruler(cut)
    out = drawn(desc, cut, ruler, bottom=bottom, second=True)
    if out["kept"] is None:
        return None
    return {**out["kept"], "scale": out["scale_how"], "widths": out["widths"]}
