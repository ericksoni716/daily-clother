"""What a second photo of a shoe, from the front, shows (#205, the "From your photo" front view).

The side photo's trace (`traced.py`) gives the shoe's heights, its sole and its side marks. A photo from the front
sees what the side photo cannot: the toe box's and the vamp's colours head on, the lacing up the instep, and the
marks on the toe. `measure` reads those from the photo and its cut-out, and `frontshoe.FrontLook` carries them into
the drawing. Nothing here traces an outline: the drawing keeps the template's rounded toe and opening.

The photo is read in bands across the shoe's height (the toe nearest the camera is lowest in the photo, the
throat above it): the sole is the bottom band, the toe box the band above it, the vamp and lacing above that.
OpenCV is only imported here, inside the functions, as for the side photo.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

MAX_PHOTO = 900       # the photo is read at most this size
MIN_SHARE = 0.04      # a shoe smaller than this share of the photo is not read
SOLE_SHARE = 0.2      # the sole's share of the front's height, when the side trace does not say (`sole_share`)
# the bands, as shares of the shoe's height above the sole's top
TOE_BAND = (0.26, 0.42)     # the toe box's top surface (a mudguard is the band below it)
VAMP_BAND = (0.46, 0.62)    # the vamp, below the opening
LACE_BAND = (0.40, 0.98)    # where the lacing runs up the instep
EDGE = 0.04                 # a patch within this share of the shoe's width of its outline is a panel's edge, not a mark
MIDDLE = 0.14               # the lacing column: this share of the shoe's width each side of its middle
LACE_DE = 24.0              # a row this far in colour from the vamp is a lace
MARK_DE = 30.0              # a patch this far from both the toe's and the vamp's colours is a mark
MARK_MIN = 0.006            # ... when it is at least this share of the shoe
MAX_MARKS = 4
FRONT_ASPECT_RANGE = (0.5, 2.5)   # a front's width over its height outside this is not a front view


def _hex(rgb) -> str:
    r, g, b = (int(round(float(min(255.0, max(0.0, v))))) for v in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def _mode(pixels: np.ndarray, lab: np.ndarray) -> np.ndarray | None:
    """The most common colour among `pixels` (RGB rows), read in Lab buckets: a lace or a shadow does not pull it
    off as a median would. Returns the mean RGB of the commonest bucket."""
    if len(pixels) == 0:
        return None
    keys = np.floor(lab / np.array([8.0, 10.0, 10.0])).astype(np.int32)
    _, inverse, counts = np.unique(keys, axis=0, return_inverse=True, return_counts=True)
    inverse = inverse.reshape(-1)
    top = int(np.argmax(counts))
    near = np.linalg.norm(lab - lab[inverse == top].mean(axis=0), axis=1) < 12.0
    return pixels[near].mean(axis=0)


def _runs(flags: np.ndarray, min_len: int) -> list[tuple[int, int]]:
    out, start = [], None
    for i, f in enumerate(list(flags) + [False]):
        if f and start is None:
            start = i
        elif not f and start is not None:
            if i - start >= min_len:
                out.append((start, i))
            start = None
    return out


def sole_share(shoe) -> float:
    """The sole's share of the shoe's height seen from the front (its thickness under the toe over the top of its
    collar or shaft), from the side trace (`traced.TracedShoe`)."""
    p = shoe.profile
    at_toe = float(np.interp(0.85, p.u, np.add(p.bottom, p.sole)))
    return min(0.4, max(0.05, at_toe / max(1.0, max(p.top))))


def measure(img: Image.Image, maskers, sole: float = SOLE_SHARE) -> dict | None:
    """The front photo's look: {"toe", "vamp", "laces", "lace_color", "marks", "aspect"} as `frontshoe.FrontLook`
    takes it, or None when no shoe was found in it. `maskers`: [(name, photo -> soft mask 0..255 or None)], tried
    in order, as for the side photo; `sole`: the sole's share of the front's height (`sole_share`)."""
    import cv2

    from .trace import clean_mask, to_lab
    img = img.convert("RGB")
    img.thumbnail((MAX_PHOTO, MAX_PHOTO), Image.LANCZOS)
    rgb = np.asarray(img)
    mask = None
    for _, cut in maskers:
        soft = cut(img)
        if soft is None:
            continue
        m, _ = clean_mask(np.asarray(soft))
        if m.sum() >= MIN_SHARE * m.size:
            mask = m
            break
    if mask is None:
        return None
    mask = cv2.erode(mask, np.ones((3, 3), np.uint8))   # the edge's pixels are part background
    ys, xs = np.nonzero(mask)
    if len(ys) == 0:
        return None
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    height, width = y1 - y0, x1 - x0
    aspect = width / max(1, height)
    if not FRONT_ASPECT_RANGE[0] <= aspect <= FRONT_ASPECT_RANGE[1]:
        return None
    lab = to_lab(rgb)
    mid = (x0 + x1) / 2

    def at(share):   # the row `share` of the way up the upper, above the sole
        return int(round(y1 - (sole + share * (1 - sole)) * height))

    def band(lo, hi, half=0.5):
        """The shoe's pixels between lo and hi of the upper's height above the sole, within `half` of its width of
        the middle."""
        rows = slice(at(hi), at(lo))
        cols = slice(int(mid - half * width), int(mid + half * width) + 1)
        sel = mask[rows, cols].astype(bool)
        return rgb[rows, cols][sel].astype(np.float64), lab[rows, cols][sel].astype(np.float64)

    toe = _mode(*band(*TOE_BAND, half=0.3))
    vamp = _mode(*band(*VAMP_BAND, half=0.3))
    if toe is None or vamp is None:
        return None
    vamp_lab = to_lab(np.uint8([[np.clip(vamp, 0, 255)]]))[0, 0].astype(np.float64)
    toe_lab = to_lab(np.uint8([[np.clip(toe, 0, 255)]]))[0, 0].astype(np.float64)

    # the laces: rows of the lacing column whose colour stands off the vamp's, counted as separate runs
    rows = range(at(LACE_BAND[1]), at(LACE_BAND[0]))
    c0, c1 = int(mid - MIDDLE * width), int(mid + MIDDLE * width) + 1
    flags, lace_px = [], []
    for y in rows:
        sel = mask[y, c0:c1].astype(bool)
        if sel.sum() < 0.5 * (c1 - c0):
            flags.append(False)
            continue
        row_lab = lab[y, c0:c1][sel].astype(np.float64)
        off = np.linalg.norm(row_lab - vamp_lab, axis=1) > LACE_DE
        lace = off.mean() > 0.6
        flags.append(bool(lace))
        if lace:
            lace_px.append(rgb[y, c0:c1][sel][off])
    runs = _runs(np.array(flags), max(2, int(0.008 * height)))
    laces = len(runs) if len(runs) >= 2 else 0
    lace_color = _hex(np.median(np.concatenate(lace_px), axis=0)) if laces and lace_px else None

    # the marks on the toe and the vamp: patches off both colours, outside the lacing column, and clear of the
    # outline (a mudguard or a collar along it is a panel)
    top, bottom = at(VAMP_BAND[1]), at(0.06)
    e = max(3, int(EDGE * width))
    region = np.zeros_like(mask)
    region[top:bottom] = cv2.erode(mask, np.ones((2 * e + 1, 2 * e + 1), np.uint8))[top:bottom]
    region[:, c0:c1] = 0
    far = (np.linalg.norm(lab - vamp_lab, axis=-1) > MARK_DE) & (np.linalg.norm(lab - toe_lab, axis=-1) > MARK_DE)
    blobs = (region.astype(bool) & far).astype(np.uint8)
    n, cc, stats, cents = cv2.connectedComponentsWithStats(blobs, connectivity=8)
    area = float(mask.sum())
    found = []
    for j in range(1, n):
        a = stats[j, cv2.CC_STAT_AREA]
        by, bh = stats[j, cv2.CC_STAT_TOP], stats[j, cv2.CC_STAT_HEIGHT]
        if a >= MARK_MIN * area and by > top and by + bh < bottom:
            cx, cy = cents[j]
            colour = _hex(np.median(rgb[cc == j].astype(np.float64), axis=0))
            x = (cx - mid) / (width / 2)
            v = min(1.0, max(0.0, (cy - top) / max(1, bottom - top)))   # 0 at the throat .. 1 at the toe
            found.append((a, [colour, round(float(x), 3), round(float(v), 3), round(float(a) / area, 4)]))
    marks = [m for _, m in sorted(found, key=lambda t: -t[0])[:MAX_MARKS]]
    return {"toe": _hex(toe), "vamp": _hex(vamp), "laces": laces, "lace_color": lace_color, "marks": marks,
            "aspect": round(float(aspect), 3)}
