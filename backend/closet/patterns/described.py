"""A plaid drawn from Claude's description of it, not measured from the photo. AN EXPERIMENT, not yet in the app.

Measuring a plaid from its photo (`measure`) fails on creased, hanging or dark cloth. Here Claude would describe
the plaid in a few extra fields of the description it already gives for every item (no extra call, no extra
photo): the bands met going across and going down for one repeat, each a colour and a width, and how many
repeats fit across the chest. `tile` weaves those two band sequences into one repeat and returns the same kind
of kept pattern the measured path keeps (`{"kind": "tile", "how": "described", ...}`, see
`closet.drawing.stored`), so the drawing code draws it unchanged.

`FIELD_TEXT` and `GUIDANCE` are the words the tagging form would carry; they are not sent yet.
"""
from __future__ import annotations

import re

import cv2
import numpy as np
from PIL import Image
from pydantic import BaseModel, Field

from ..drawing.stored import VERSION, tile_text

# ---- the form ---------------------------------------------------------------------------------------------

FIELD_TEXT = {
    "plaid": "Only when the pattern is plaid (checks, tartan, gingham, buffalo check, windowpane): the plaid as "
             "bands of colour, so the app can draw it. Otherwise null.",
    "across": "The bands you cross going left to right over the front, for ONE repeat, in order, starting with the "
              "widest band. A thin line is a narrow band.",
    "down": "The bands you cross going from collar to hem, for one repeat, in order, starting with the widest band. "
            "Empty when same_both_ways is true.",
    "same_both_ways": "True when the bands going down are the same as across (most tartans, gingham, buffalo check).",
    "repeats_across_chest": "How many whole repeats fit across the front from armpit to armpit: about 1.5 for a "
                            "big buffalo check, 3 to 5 for a usual flannel, 10 or more for a small gingham.",
    "color": "The band's yarn colour as #rrggbb: the colour where it crosses a band of its own colour, as it would "
             "look in daylight (not darkened by shadow or the photo).",
    "width": "The band's width, in the same units for every band both ways (for example 1 for a thin line, 8 for "
             "a broad band).",
}

GUIDANCE = (
    "When the pattern is plaid, also describe the plaid in `plaid` so it can be drawn. Find one repeat: the "
    "smallest piece that, copied side by side, makes the cloth. List its bands left to right (`across`) and collar "
    "to hem (`down`), starting each list with the widest band, the ground. Every change of colour is a new band, "
    "including thin lines (overchecks) and a band that comes back later in the repeat. Give each band the colour "
    "of its own yarn, where it crosses itself, not the mixed colour where it crosses another band. Widths are "
    "relative and in the same units both ways, so a repeat that is taller than wide has larger widths going down. "
    "Count the repeats across the chest on the photo, from armpit to armpit. Keep it short: six to ten bands each "
    "way is usually enough; a symmetric tartan is listed in full once."
)


class Band(BaseModel):
    color: str = Field(description=FIELD_TEXT["color"])
    width: float = Field(description=FIELD_TEXT["width"])


class PlaidDescription(BaseModel):
    across: list[Band] = Field(description=FIELD_TEXT["across"])
    down: list[Band] = Field(description=FIELD_TEXT["down"])
    same_both_ways: bool = Field(description=FIELD_TEXT["same_both_ways"])
    repeats_across_chest: float = Field(description=FIELD_TEXT["repeats_across_chest"])


# ---- reading an answer safely -----------------------------------------------------------------------------

_HEX = re.compile(r"#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})")
MAX_BANDS = 40            # per direction: more is a misread, not a plaid
MIN_SHARE = 0.002         # a band narrower than this share of its repeat is dropped (it could not be drawn)
REPEATS = (0.5, 16.0)     # repeats across the chest, kept within these


def _hex(raw) -> str | None:
    if not isinstance(raw, str):
        return None
    m = _HEX.fullmatch(raw.strip())
    if not m:
        return None
    h = m.group(1).lower()
    return "#" + (h if len(h) == 6 else "".join(c * 2 for c in h))


def _bands(raw) -> list[tuple[str, float]]:
    """The usable bands: a readable colour and a width above nothing; neighbours of one colour merged."""
    out: list[tuple[str, float]] = []
    for b in raw if isinstance(raw, list) else []:
        if isinstance(b, Band):
            b = b.model_dump()
        if not isinstance(b, dict):
            continue
        colour = _hex(b.get("color"))
        try:
            width = float(b.get("width"))
        except (TypeError, ValueError):
            continue
        if colour is None or not np.isfinite(width) or width <= 0:
            continue
        if out and out[-1][0] == colour:
            out[-1] = (colour, out[-1][1] + width)
        else:
            out.append((colour, width))
    if len(out) > 1 and out[0][0] == out[-1][0]:     # the repeat wraps round: its first and last band are one
        out[0] = (out[0][0], out[0][1] + out.pop()[1])
    total = sum(w for _, w in out)
    out = [(c, w) for c, w in out if w / total >= MIN_SHARE] if out else []
    return out[:MAX_BANDS]


def read(raw) -> dict | None:
    """A description (the model, or its JSON as a dict) made safe to draw: {"across": [(hex, width), ...],
    "down": [...], "repeats": f}, with widths in the same units both ways. None when there is nothing to draw (no
    usable band, or a single colour each way, which is no plaid)."""
    if isinstance(raw, PlaidDescription):
        raw = raw.model_dump()
    if not isinstance(raw, dict):
        return None
    across = _bands(raw.get("across"))
    down = _bands(raw.get("down"))
    if not across and down:
        across = down
    if raw.get("same_both_ways") is True or not down:
        down = list(across)
    if not across or (len(across) == 1 and len(down) == 1 and across[0][0] == down[0][0]):
        return None
    try:
        repeats = float(raw.get("repeats_across_chest"))
    except (TypeError, ValueError):
        repeats = 4.0
    if not np.isfinite(repeats) or repeats <= 0:
        repeats = 4.0
    return {"across": across, "down": down, "repeats": float(np.clip(repeats, *REPEATS))}


# ---- weaving it -------------------------------------------------------------------------------------------

EDGE = 0.006       # a band's edge is softened over this share of the repeat's width (yarns are not ruled lines)
TWILL = 0.18       # how far a twill weave tips each spot towards the warp or the weft yarn (0 = an even mix)
STEP = 8           # px: one twill diagonal; the tile's sides are whole numbers of these so it repeats seamlessly
SIDE = 360         # px: the tile's longer side (the drawing hands a tile over at most this size)
# Sizing on the drawing: the drawn shirt's chest (armpit to armpit) is this share of its neck-to-hem length and
# of its outline's width with long sleeves (the shirt template; a test keeps them in step with it).
CHEST_PER_LENGTH = 0.60
CHEST_PER_OUTLINE = 0.47


def _lab(hexes: list[str]) -> np.ndarray:
    rgb = np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in hexes], np.uint8)[None]
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)[0].astype(np.float32)


def _sequence(bands: list[tuple[str, float]], n: int, unit: float) -> np.ndarray:
    """The bands laid along n px (unit px per width unit) as Lab colours, each px the share-weighted mix of the
    bands it covers, its edges softened round the repeat (so the ends meet)."""
    cols = _lab([c for c, _ in bands])
    edges = np.concatenate([[0.0], np.cumsum([w * unit for _, w in bands])])
    edges *= n / edges[-1]
    seq = np.zeros((n, 3), np.float32)
    px = np.arange(n, dtype=np.float32)
    for k in range(len(bands)):
        cover = np.clip(np.minimum(px + 1, edges[k + 1]) - np.maximum(px, edges[k]), 0, 1)
        seq += cover[:, None] * cols[k]
    sigma = max(0.6, EDGE * n)
    r = int(np.ceil(3 * sigma))
    wide = np.concatenate([seq[-r:], seq, seq[:r]])
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    return np.stack([np.convolve(wide[:, c], k, mode="valid") for c in range(3)], 1)


def weave(desc: dict) -> np.ndarray:
    """One repeat of the plaid `read` describes, as an RGB image: the warp (across) and the weft (down) crossing,
    each spot the mix of the two yarns in Lab, tipped one way and the other along a faint twill diagonal."""
    wa, wd = sum(w for _, w in desc["across"]), sum(w for _, w in desc["down"])
    scale = SIDE / max(wa, wd)
    W = max(STEP, int(round(wa * scale / STEP)) * STEP)
    H = max(STEP, int(round(wd * scale / STEP)) * STEP)
    warp = _sequence(desc["across"], W, scale)
    weft = _sequence(desc["down"], H, scale)
    yy, xx = np.mgrid[0:H, 0:W]
    # a 2/2 twill: along each diagonal the warp shows, then the weft; a soft triangle wave, so it reads as grain
    phase = ((xx + yy) % STEP) / STEP
    t = (TWILL * (1 - 4 * np.abs(phase - 0.5)))[..., None].astype(np.float32)   # -TWILL .. +TWILL
    lab = (0.5 + t) * warp[None, :, :] + (0.5 - t) * weft[:, None, :]
    return cv2.cvtColor(np.clip(lab, 0, 255).round().astype(np.uint8), cv2.COLOR_LAB2RGB)


SPREAD = (0.5, 1.6)   # how far the photo may pull the described colours' contrast, per Lab channel


def toned(img: np.ndarray, cut: Image.Image) -> np.ndarray:
    """The described repeat in the photo's own colours. A description gets the bands and their order right but
    names cleaner, stronger colours than the cloth has and often the wrong one as the ground; the photo is poor
    at where the bands are but exact about what colour the garment is overall. So the repeat's colours are moved
    as a whole until their average and their spread (lightness, green-red and blue-yellow each on its own) are
    those of the garment's pixels, with the weave's grain smoothed out of both first."""
    arr = np.asarray(cut.convert("RGBA"))
    on = arr[..., 3] > 200
    if on.sum() < 400:
        return img
    photo = cv2.cvtColor(cv2.GaussianBlur(np.ascontiguousarray(arr[..., :3]), (0, 0), 2.0), cv2.COLOR_RGB2LAB)[on].astype(np.float32)
    lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB).astype(np.float32)
    flat = cv2.GaussianBlur(np.pad(lab, ((6, 6), (6, 6), (0, 0)), mode="wrap"), (0, 0), 2.0)[6:-6, 6:-6].reshape(-1, 3)
    lo, hi = np.percentile(photo, [2, 98], axis=0)        # a glint, a button, a sliver of background do not count
    kept = photo[((photo >= lo) & (photo <= hi)).all(1)]
    gain = np.clip(kept.std(0) / np.maximum(flat.std(0), 1e-3), *SPREAD)
    out = (lab - flat.mean(0)) * gain + kept.mean(0)
    return cv2.cvtColor(np.clip(out, 0, 255).round().astype(np.uint8), cv2.COLOR_LAB2RGB)


def tile(raw, cut: Image.Image | None = None) -> dict | None:
    """The kept pattern for a described plaid (as `measure.measure` keeps a measured one), or None when the
    description has nothing to draw. Sized so `repeats_across_chest` repeats fit across the drawn chest; placed
    with the middle of the first (widest) band each way on the button line. With the item's cutout, its colours
    are brought to the photo's (`toned`)."""
    desc = read(raw)
    if desc is None:
        return None
    img = weave(desc)
    if cut is not None:
        img = toned(img, cut)
    first_a = desc["across"][0][1] / 2 / sum(w for _, w in desc["across"])
    first_d = desc["down"][0][1] / 2 / sum(w for _, w in desc["down"])
    return {"kind": "tile", "how": "described", "image": tile_text(Image.fromarray(img), quality=92),
            "width_frac": round(CHEST_PER_OUTLINE / desc["repeats"], 4),
            "length_frac": round(CHEST_PER_LENGTH / desc["repeats"], 4),
            "phase": [round(first_a, 4), round(first_d, 4)], "phase_right": None, "version": VERSION}
