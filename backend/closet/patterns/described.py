"""A plaid drawn from Claude's description of it, not measured from the photo. First an experiment; the app now
weaves a described plaid or stripe with it through `surface` (the description's surface, adopted 18 November).

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
MOVE = 2.5         # the most a colour's share may move from Claude's, up or down (times), and only when the
GAIN = 0.10        # photo's shares explain its pixels this much better than Claude's do (`_explained`); not at all
#                    when they explain them no better, and in proportion between
HOLES = 0.01       # a cutout with more than this share of see-through holes inside its outline may have lost a
#                    colour with them (the owner's shirt by a window lost its white squares): its colours are not counted
HUE_PIXELS = 400   # a colour's hue is moved toward the photo's only with at least this many pixels where it crosses itself
WIDTHS = True      # the defaults of `tile` (see DECISIONS): widths from the photo on, hues off, colours softened
HUES = 0.0
STRENGTH = 0.8     # described colours are stronger than the cloth (photo chroma about 0.57 of theirs on the test shirts)
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


def holes(alpha: np.ndarray) -> float:
    """How much of a cutout's outline is see-through inside it: the share of the garment's filled outline that
    the background removal cut out (white squares taken for background, say)."""
    out = np.pad((alpha <= 128).astype(np.uint8), 1, constant_values=1)
    cv2.floodFill(out, np.zeros((out.shape[0] + 2, out.shape[1] + 2), np.uint8), (0, 0), 2)
    inside = int((out == 1).sum())
    return inside / max(1, inside + int((alpha > 128).sum()))


def _evidence(desc: dict, cut: Image.Image) -> dict | None:
    """What the photo says about the described yarns: each garment pixel (the weave's grain smoothed, the photo
    stretched to the described cloth's range, `_stretched`) matched to the nearest colour a crossing of two
    described yarns makes. Yarns nearly alike are one colour here (how the pixels split between them would be
    chance). None when there is too little garment, one colour, or the photo's colours lie too far from every
    crossing colour to say anything."""
    cols = list(dict.fromkeys(c for c, _ in desc["across"]))
    if len(cols) < 2:
        return None
    arr = np.asarray(cut.convert("RGBA"))
    on = cv2.erode((arr[..., 3] > 200).astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    if on.sum() < 400 or holes(arr[..., 3]) > HOLES:
        return None
    px = cv2.GaussianBlur(np.ascontiguousarray(arr[..., :3]), (0, 0), 2.0)[on]
    px = px[np.random.default_rng(0).choice(len(px), min(len(px), 40000), replace=False)]
    raw = _cie(cv2.cvtColor(px[None], cv2.COLOR_RGB2LAB)[0])
    yarn = _cie(_lab(cols))
    group = list(range(len(cols)))
    for i in range(len(cols)):
        for j in range(i):
            if np.linalg.norm(yarn[i] - yarn[j]) < SAME:
                group[i] = group[j]
                break
    groups = sorted(set(group))
    members = [[i for i in range(len(cols)) if group[i] == g] for g in groups]
    claude = np.array([sum(w for c, w in desc["across"] if group[cols.index(c)] == g) for g in groups], float)
    claude /= claude.sum()
    ref = _cie(cv2.cvtColor(weave(desc), cv2.COLOR_RGB2LAB).reshape(-1, 3))
    photo = _stretched(raw, ref)
    gl = np.array([yarn[m].mean(0) for m in members])
    pairs = [(i, j) for i in range(len(groups)) for j in range(i, len(groups))]
    mix = np.array([(gl[i] + gl[j]) / 2 for i, j in pairs])
    d = np.sqrt((((photo[:, None, :] - mix[None]) * np.array([DIST_L, 1, 1], np.float32)) ** 2).sum(2))
    near, nd = d.argmin(1), d.min(1)
    counted = nd <= FAR
    if np.median(nd) > GOOD_FIT or counted.mean() < 0.5:
        return None
    pair_share = np.bincount(near[counted], minlength=len(pairs)) / counted.sum()
    seen = np.zeros(len(groups))
    for p, s in enumerate(pair_share):
        seen[pairs[p][0]] += s / 2
        seen[pairs[p][1]] += s / 2
    return {"cols": cols, "group": group, "groups": groups, "members": members, "claude": claude, "seen": seen,
            "pairs": pairs, "pair_share": pair_share, "near": near, "counted": counted, "photo": photo, "raw": raw,
            "yarn": yarn}


def _explained(shares: np.ndarray, ev: dict) -> float:
    """How well a plaid woven with these colour shares explains the photo: 1 minus half the difference between
    the shares of the cloth each crossing would cover (w_i * w_j, twice over for two colours) and the shares of
    the photo's pixels nearest each crossing colour. 1 = the same mixture."""
    pred = np.array([shares[i] * shares[j] * (1 if i == j else 2) for i, j in ev["pairs"]])
    return float(1 - 0.5 * np.abs(pred / pred.sum() - ev["pair_share"]).sum())


def _fitted_shares(ev: dict) -> tuple[np.ndarray, float, float]:
    """The colour shares from the photo (`photo_widths`), how well they explain it, and how far they were allowed
    to move from Claude's (the cap: further the better they explain the photo than Claude's shares do)."""
    claude, seen = ev["claude"], ev["seen"]
    broad = claude >= THIN
    want = claude.copy()
    if broad.sum() >= 2 and seen[broad].sum() > 0:
        want[broad] = seen[broad] / seen[broad].sum() * claude[broad].sum()
    fit = _explained(want, ev)
    # the better the photo's own shares explain its pixels than Claude's, the further they may move Claude's
    move = 1 + (MOVE - 1) * float(np.clip((fit - _explained(claude, ev)) / GAIN, 0, 1))
    new = claude.copy()
    step = want - claude
    if (step[broad] != 0).any():
        c, s = claude[broad], step[broad]
        room = np.where(s > 0, c * move - c, c - c / move)
        t = float(min(1.0, *(room[s != 0] / np.abs(s[s != 0]))))
        new[broad] = c + t * s
    return new, fit, move


def _ground_first(bands: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """The same repeat, started at the widest band of the colour that covers most of it: that band is the ground,
    placed on the button line, whichever band the description happened to list first."""
    totals: dict[str, float] = {}
    for c, w in bands:
        totals[c] = totals.get(c, 0.0) + w
    top = max(totals, key=totals.get)
    k = max((i for i, (c, _) in enumerate(bands) if c == top), key=lambda i: bands[i][1])
    return bands[k:] + bands[:k]


def _hex_of(cie: np.ndarray) -> str:
    lab8 = np.clip(np.asarray(cie, np.float32) * np.array([255 / 100, 1, 1], np.float32) + np.array([0, 128, 128], np.float32), 0, 255)
    rgb = cv2.cvtColor(lab8.round().astype(np.uint8)[None, None], cv2.COLOR_LAB2RGB)[0, 0]
    return "#" + "".join(f"{int(v):02x}" for v in rgb)


def photo_widths(desc: dict, cut: Image.Image, hues: float = 0.0) -> tuple[dict, dict] | None:
    """The description `read` gave with its broad colours' widths taken from the photo: each garment pixel (the
    weave's grain smoothed) is matched to the nearest colour a crossing of two described yarns makes, and a yarn's
    share of the cloth is its share of those pixels, half of every crossing with another yarn (in a woven plaid
    yarn i crosses yarn j over w_i * w_j of the cloth, so these halves add up to w_i). Lines (colours under THIN)
    keep their width; the broad colours move from Claude's shares toward the photo's as far as the cap allows, which
    is wider the better the photo's shares explain its pixels than Claude's do (MOVE, GAIN); bands of one colour keep their
    proportions, and yarns nearly alike are drawn as one colour. The repeat then starts at its ground, the widest
    band of the broadest colour. With `hues` (0 to 1), each broad colour moves that part of the way toward the
    colour of the photo's pixels where it crosses itself (seen in the described cloth's range, so the photo's
    exposure and cast do not come with it). Returns (the new description, {colour: (described share, new share)}
    plus "fit" and "cap"), or None when the photo's colours do not fit the described ones well enough to say."""
    ev = _evidence(desc, cut)
    if ev is None:
        return None
    new, fit, move = _fitted_shares(ev)
    cols, group, groups, claude = ev["cols"], ev["group"], ev["groups"], ev["claude"]
    k_of = {c: groups.index(group[i]) for i, c in enumerate(cols)}
    colour = {c: cols[ev["members"][k_of[c]][0]] if len(ev["members"][k_of[c]]) == 1 else
              _hex_of(ev["yarn"][ev["members"][k_of[c]]].mean(0)) for c in cols}
    if hues > 0:
        for k in range(len(groups)):
            own = ev["pairs"].index((k, k))
            mine = ev["counted"] & (ev["near"] == own)
            if claude[k] >= THIN and mine.sum() >= HUE_PIXELS:
                target = np.median(ev["photo"][mine], axis=0)
                was = ev["yarn"][ev["members"][k]].mean(0)
                moved = _hex_of(was + hues * (target - was))
                for i in ev["members"][k]:
                    colour[cols[i]] = moved
    factor = {c: new[k_of[c]] / claude[k_of[c]] for c in cols}

    def redo(bands):
        out: list[tuple[str, float]] = []
        for c, w in bands:
            c2, w2 = colour.get(c, c), w * factor.get(c, 1.0)
            if out and out[-1][0] == c2:
                out[-1] = (c2, out[-1][1] + w2)
            else:
                out.append((c2, w2))
        if len(out) > 1 and out[0][0] == out[-1][0]:
            out[0] = (out[0][0], out[0][1] + out.pop()[1])
        return _ground_first(out)
    out = {**desc, "across": redo(desc["across"]), "down": redo(desc["down"])}
    shares = {cols[ev["members"][k][0]]: (round(float(claude[k]), 3), round(float(new[k]), 3)) for k in range(len(groups))}
    return out, {**shares, "fit": round(fit, 3), "cap": round(move, 3)}


def softened(desc: dict, strength: float) -> dict:
    """The description with every colour's strength (chroma) multiplied by `strength`, its lightness and hue kept."""
    if strength == 1.0:
        return desc

    def soft(c):
        lab = _cie(_lab([c]))[0]
        return _hex_of(lab * np.array([1, strength, strength], np.float32))
    return {**desc, "across": [(soft(c), w) for c, w in desc["across"]], "down": [(soft(c), w) for c, w in desc["down"]]}


def tile(raw, cut: Image.Image | None = None, landmarks: dict | None = None, tone: bool = False,
         widths: bool = WIDTHS, hues: float = HUES, strength: float = STRENGTH) -> dict | None:
    """The kept pattern for a described plaid (as `measure.measure` keeps a measured one), or None when the
    description has nothing to draw. Sized so its repeats fit across the drawn chest: as many as the photo shows
    when the item's cutout and Claude's landmarks are given and the photo settles it (`photo_repeats`), else as
    many as Claude said; `scale` says which. Placed with the middle of the first band (the ground) each way on
    the button line. With the cutout and `widths`, the broad colours' widths come from the photo, and with `hues`
    their colours move part of the way to the photo's (`photo_widths`; `widths` in the result says whether the
    photo was used). With `tone`, its colours are brought to the photo's as a whole (`toned`; tried, not kept
    on)."""
    desc = read(raw)
    if desc is None:
        return None
    seen = photo_repeats(cut, landmarks) if cut is not None and landmarks else None
    if seen is not None:
        desc["repeats"] = seen[0]
    fitted = photo_widths(desc, cut, hues=hues) if widths and cut is not None else None
    if fitted is not None:
        desc = fitted[0]
    img = weave(softened(desc, strength))
    if tone and cut is not None:
        img = toned(img, cut)
    first_a = desc["across"][0][1] / 2 / sum(w for _, w in desc["across"])
    first_d = desc["down"][0][1] / 2 / sum(w for _, w in desc["down"])
    return {"kind": "tile", "how": "described", "image": tile_text(Image.fromarray(img), quality=92),
            "width_frac": round(CHEST_PER_OUTLINE / desc["repeats"], 4),
            "length_frac": round(CHEST_PER_LENGTH / desc["repeats"], 4),
            "phase": [round(first_a, 4), round(first_d, 4)], "phase_right": None,
            "scale": seen[1] if seen else "said", "widths": "photo" if fitted else "said", "version": VERSION}
