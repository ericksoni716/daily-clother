"""A plaid drawn from Claude's description of it, not measured from the photo. AN EXPERIMENT, not yet in the app.

Measuring a plaid from its photo (`measure`) fails on creased, hanging or dark cloth. Here Claude would describe
the plaid in a few extra fields of the description it already gives for every item (no extra call, no extra
photo): the bands of one repeat, each a colour and a width, and how big the checks are. The size of the repeat
is read from the photo where it can be (`photo_repeats`, with the landmarks the app already asks for). `tile`
weaves the bands, crossing themselves, into one repeat and returns the same kind
of kept pattern the measured path keeps (`{"kind": "tile", "how": "described", ...}`, see
`closet.drawing.stored`), so the drawing code draws it unchanged.

`FIELD_TEXT` and `GUIDANCE` are the words the tagging form would carry; they are not sent yet.
"""
from __future__ import annotations

import re
from typing import Literal

import cv2
import numpy as np
from PIL import Image
from pydantic import BaseModel, Field

from ..drawing.stored import VERSION, tile_text

# ---- the form ---------------------------------------------------------------------------------------------

# Round two (the form below): one list of bands, the same both ways; widths as whole numbers; the size as a word.
# The first form (bands across and down, a yes/no for "the same both ways", a number of repeats) gave the same
# number of repeats, 4, for all six of the owner's test shirts and made each description 700 to 1,000 output
# tokens longer (Claude thought much longer about it); this one 200 to 350. The scale comes from the photo where it
# can (`photo_repeats`); the size word is the fallback. `read` still takes answers in the first form.
FIELD_TEXT = {
    "plaid": "Only when the pattern is plaid or checked, else null: its bands, so the app can draw it.",
    "bands": "One repeat's bands, ground first. A thin line is width 1.",
    "size": "Repeats across the chest: tiny more than 8, small 5-8, medium 3-5, large 2-3, huge under 2.",
    "color": "#rrggbb as it looks on this cloth.",
    "width": "Whole number; the ground's width shows how much of the cloth it covers.",
}

GUIDANCE = "- Plaid: fill in `plaid` from a quick look, ground first. A rough answer is fine."

Size = Literal["tiny", "small", "medium", "large", "huge"]


class Band(BaseModel):
    color: str = Field(description=FIELD_TEXT["color"])
    width: int = Field(description=FIELD_TEXT["width"])


class PlaidDescription(BaseModel):
    bands: list[Band] = Field(description=FIELD_TEXT["bands"])
    size: Size = Field(description=FIELD_TEXT["size"])


# ---- reading an answer safely -----------------------------------------------------------------------------

_HEX = re.compile(r"#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})")
MAX_BANDS = 40            # per direction: more is a misread, not a plaid
MIN_SHARE = 0.002         # a band narrower than this share of its repeat is dropped (it could not be drawn)
REPEATS = (0.5, 16.0)     # repeats across the chest, kept within these
# a size word, as repeats across the chest (the middle of each word's range; see FIELD_TEXT["size"])
SIZE_REPEATS = {"tiny": 10.0, "small": 6.5, "medium": 4.0, "large": 2.5, "huge": 1.6}


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
    across = _bands(raw.get("across", raw.get("bands")))
    down = _bands(raw.get("down"))
    if not across and down:
        across = down
    if raw.get("same_both_ways") is True or not down:
        down = list(across)
    if not across or (len(across) == 1 and len(down) == 1 and across[0][0] == down[0][0]):
        return None
    size = raw.get("size", raw.get("check_size"))
    try:
        repeats = SIZE_REPEATS[size] if size in SIZE_REPEATS else float(raw.get("repeats_across_chest"))
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


# ---- the scale from the photo -----------------------------------------------------------------------------

SQUARE = 1.25      # a spacing across and one down within this ratio of each other are taken as one square repeat


def photo_repeats(cut: Image.Image, landmarks: dict | None) -> tuple[float, str] | None:
    """How many repeats fit across the chest, read from the photo: the spacings at which the garment's whole band
    sequences repeat across and down (`straighten._spacings`, which creases and drape do not upset), against the
    chest's width between Claude's two underarm points (`landmarks`, in the cutout's pixels). A spacing across and
    one down that agree (a plaid's repeat is nearly square) settle it; else the shortest spacing down. Returns
    (repeats, how it was settled), or None when the photo says nothing: then Claude's size stands."""
    try:
        a, b = landmarks["underarm_left"], landmarks["underarm_right"]
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
    if near is not None and near[0] <= SQUARE:
        return float(np.clip(chest / near[1], *REPEATS)), "across and down agree"
    # the bands running across a garment stay straight however it hangs or lies; those running down are broken by
    # an open front, the placket and folds, so the spacing down is trusted. One wider than the chest is no repeat
    # (a madras's irregular blocks)
    if down and chest / down[0] >= 1:
        return float(np.clip(chest / down[0], *REPEATS)), "down"
    return None


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


# ---- the band widths from the photo -----------------------------------------------------------------------

THIN = 0.10        # a colour covering less than this share of the described repeat is a line: its width stays
MOVE = 1.6         # no colour's share moves further than this many times from Claude's, up or down
SAME = 10.0        # yarn colours closer than this (CIE Lab) are one colour for the count
FAR = 22.0         # a garment pixel farther than this from every crossing colour is not counted (holes, buttons)
GOOD_FIT = 12.0    # the widths are moved only when the garment's pixels lie this close to the crossings (median)
DIST_L = 0.5       # lightness counts half in the distance: exposure differs between a photo and named colours


def _cie(lab8: np.ndarray) -> np.ndarray:
    """OpenCV's 8-bit Lab as CIE L*a*b*."""
    return lab8.astype(np.float32) * np.array([100 / 255, 1, 1], np.float32) - np.array([0, 128, 128], np.float32)


def _stretched(photo: np.ndarray, ref: np.ndarray) -> np.ndarray:
    """Each channel of the photo's colours stretched so its 5th to 95th percentiles are those of `ref`: the photo's
    exposure and colour cast taken out, as far as a doubling or halving, so its colours can be compared with the
    described ones. The extremes, not the average, are matched, so how much there is of each colour is kept."""
    out = photo.copy()
    for c in range(3):
        p5, p95 = np.percentile(photo[:, c], [5, 95])
        r5, r95 = np.percentile(ref[:, c], [5, 95])
        g = float(np.clip((r95 - r5) / max(p95 - p5, 1e-3), 0.5, 2.0))
        out[:, c] = (photo[:, c] - (p5 + p95) / 2) * g + (r5 + r95) / 2
    return out


def photo_widths(desc: dict, cut: Image.Image) -> tuple[dict, dict] | None:
    """The description `read` gave with its broad colours' widths taken from the photo: each garment pixel (the
    weave's grain smoothed) is matched to the nearest colour a crossing of two described yarns makes, and a yarn's
    share of the cloth is its share of those pixels, half of every crossing with another yarn (in a woven plaid
    yarn i crosses yarn j over w_i * w_j of the cloth, so these halves add up to w_i). Claude's band order and
    colours stay; lines (colours under THIN) keep their width; no share moves more than MOVE times; bands of one
    colour keep their proportions. Returns (the new description, {colour: (described share, new share)}), or None
    when the photo's colours do not fit the described ones well enough to say."""
    cols = list(dict.fromkeys(c for c, _ in desc["across"]))
    if len(cols) < 2:
        return None
    arr = np.asarray(cut.convert("RGBA"))
    on = cv2.erode((arr[..., 3] > 200).astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    if on.sum() < 400:
        return None
    px = cv2.GaussianBlur(np.ascontiguousarray(arr[..., :3]), (0, 0), 2.0)[on]
    px = px[np.random.default_rng(0).choice(len(px), min(len(px), 40000), replace=False)]
    photo = _cie(cv2.cvtColor(px[None], cv2.COLOR_RGB2LAB)[0])
    yarn = _cie(_lab(cols))
    # yarns nearly alike are one colour here: how the photo's pixels split between them would be chance
    group = list(range(len(cols)))
    for i in range(len(cols)):
        for j in range(i):
            if np.linalg.norm(yarn[i] - yarn[j]) < SAME:
                group[i] = group[j]
                break
    groups = sorted(set(group))
    claude = np.array([sum(w for c, w in desc["across"] if group[cols.index(c)] == g) for g in groups], float)
    claude /= claude.sum()
    ref = _cie(cv2.cvtColor(weave(desc), cv2.COLOR_RGB2LAB).reshape(-1, 3))
    photo = _stretched(photo, ref)
    gl = np.array([yarn[[i for i in range(len(cols)) if group[i] == g]].mean(0) for g in groups])
    pairs = [(i, j) for i in range(len(groups)) for j in range(i, len(groups))]
    mix = np.array([(gl[i] + gl[j]) / 2 for i, j in pairs])
    d = np.sqrt((((photo[:, None, :] - mix[None]) * np.array([DIST_L, 1, 1], np.float32)) ** 2).sum(2))
    near, nd = d.argmin(1), d.min(1)
    counted = nd <= FAR
    if np.median(nd) > GOOD_FIT or counted.mean() < 0.5:
        return None
    seen = np.zeros(len(groups))
    for p, n in zip(*np.unique(near[counted], return_counts=True), strict=True):
        i, j = pairs[p]
        seen[i] += n / 2
        seen[j] += n / 2
    seen /= seen.sum()
    broad = claude >= THIN
    new = claude.copy()
    if broad.sum() >= 2 and seen[broad].sum() > 0:
        # the lines keep their share; the broad colours share the rest as the photo does, moving from Claude's
        # shares toward the photo's only as far as no share goes past MOVE times its described one
        c = claude[broad]
        want = seen[broad] / seen[broad].sum() * c.sum()
        step = want - c
        room = np.where(step > 0, c * MOVE - c, c - c / MOVE)
        t = float(min(1.0, *(room[step != 0] / np.abs(step[step != 0])))) if (step != 0).any() else 0.0
        new[broad] = c + t * step
    factor = {c: new[groups.index(group[i])] / claude[groups.index(group[i])] for i, c in enumerate(cols)}
    out = {**desc, "across": [(c, w * factor[c]) for c, w in desc["across"]],
           "down": [(c, w * factor.get(c, 1.0)) for c, w in desc["down"]]}
    shares = {cols[[i for i in range(len(cols)) if group[i] == g][0]]: (round(float(claude[k]), 3), round(float(new[k]), 3))
              for k, g in enumerate(groups)}
    return out, shares


def tile(raw, cut: Image.Image | None = None, landmarks: dict | None = None, tone: bool = False,
         widths: bool = False) -> dict | None:
    """The kept pattern for a described plaid (as `measure.measure` keeps a measured one), or None when the
    description has nothing to draw. Sized so its repeats fit across the drawn chest: as many as the photo shows
    when the item's cutout and Claude's landmarks are given and the photo settles it (`photo_repeats`), else as
    many as Claude said; `scale` says which. Placed with the middle of the first band (the ground) each way on
    the button line. With `widths`, the broad colours' widths come from the photo (`photo_widths`; `widths` in the
    result says whether they did). With `tone`, its colours are brought to the photo's (`toned`; tried, not kept
    on)."""
    desc = read(raw)
    if desc is None:
        return None
    seen = photo_repeats(cut, landmarks) if cut is not None and landmarks else None
    if seen is not None:
        desc["repeats"] = seen[0]
    fitted = photo_widths(desc, cut) if widths and cut is not None else None
    if fitted is not None:
        desc = fitted[0]
    img = weave(desc)
    if tone and cut is not None:
        img = toned(img, cut)
    first_a = desc["across"][0][1] / 2 / sum(w for _, w in desc["across"])
    first_d = desc["down"][0][1] / 2 / sum(w for _, w in desc["down"])
    return {"kind": "tile", "how": "described", "image": tile_text(Image.fromarray(img), quality=92),
            "width_frac": round(CHEST_PER_OUTLINE / desc["repeats"], 4),
            "length_frac": round(CHEST_PER_LENGTH / desc["repeats"], 4),
            "phase": [round(first_a, 4), round(first_d, 4)], "phase_right": None,
            "scale": seen[1] if seen else "said", "widths": "photo" if fitted else "said", "version": VERSION}
