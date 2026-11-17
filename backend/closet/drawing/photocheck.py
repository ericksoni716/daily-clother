"""What a shoe's photos tell the drawing without asking Claude: where the shoe is in each photo, and whether a
straight-on drawing has as much of its light material (white leather, white mesh) across the upper's front as the
front photo has.

Both need the shoe cut from its background by the app's own background model (`mask_of`, the same mask the shoe
tracing uses); with no model yet, the photos are used whole and the check is left out.

- `crop` cuts a photo to the shoe with a margin, so Claude sees the shoe at full size: a front photo taken from a metre
  away has the shoe in a third of its width.
- `FrontCheck` lays the front photo and the drawing (its upper, without the sole, the laces, the lining and the
  outlines) on the same coarse grid over their own boxes and classes each cell by the nearest of the sheet's colours.
  It says what is wrong only when the drawing has a large light area AND a large, clearly darker one beside it (the
  GAT's white leather and grey suede), and their shares differ from the photo's by more than TOLERANCE. A shoe of one
  colour, or of near-whites (a canvas plimsoll with an off-white toe cap), is never checked: in shade, a white reads as
  a light grey in a photo, and the check would push the drawing the wrong way.
"""
from __future__ import annotations

import io
from collections.abc import Callable, Mapping

import numpy as np
from PIL import Image

from . import drawn

MaskOf = Callable[[Image.Image], "np.ndarray | None"]   # a photo -> its foreground mask (0-255 or bool), or None

CROP_PAD = 0.12      # the margin round the shoe, as a share of its width and height
GRID = 24            # cells across and down
TOLERANCE = 0.08     # the share of the upper the light material may differ by
LIGHT_L = 80.0       # CIE L*: a colour this light or lighter counts as light
MERGE_DE = 12.0      # the sheet's colours closer than this are one colour
MIN_SHARE = 0.12     # the darker area must cover at least this much of the drawing's upper
CONTRAST_L = 18.0    # ... and be at least this much darker (L*) than the upper's lightest
SKIPPED = ("sole", "lace", "lining", "ink", "stitch")   # roles left out of the upper


def _mask(image: Image.Image, mask_of: MaskOf | None) -> np.ndarray | None:
    if mask_of is None:
        return None
    try:
        m = mask_of(image)
    except Exception:   # no model, or it could not read the photo: the photo is used as it is
        return None
    if m is None:
        return None
    m = np.asarray(m)
    m = m > 128 if m.dtype != bool else m
    return m if m.shape[:2] == (image.height, image.width) and m.any() else None


def crop(image: Image.Image, mask_of: MaskOf | None) -> Image.Image:
    """The photo cut to the shoe with a margin (CROP_PAD); the photo as it is when the shoe cannot be found."""
    small = image.copy()
    small.thumbnail((900, 900))
    m = _mask(small, mask_of)
    if m is None:
        return image
    ys, xs = np.where(m)
    k = image.width / small.width
    x0, x1, y0, y1 = xs.min() * k, (xs.max() + 1) * k, ys.min() * k, (ys.max() + 1) * k
    px, py = (x1 - x0) * CROP_PAD, (y1 - y0) * CROP_PAD
    box = (max(0, int(x0 - px)), max(0, int(y0 - py)), min(image.width, int(x1 + px)), min(image.height, int(y1 + py)))
    return image.crop(box)


def _lab(rgb) -> np.ndarray:
    rgb = np.asarray(rgb, dtype=np.float64) / 255.0
    lin = np.where(rgb > 0.04045, ((rgb + 0.055) / 1.055) ** 2.4, rgb / 12.92)
    xyz = lin @ np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]]).T
    xyz /= np.array([0.9505, 1.0, 1.089])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def _grid(rgb: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The median colour of each cell of a GRID x GRID grid over the mask's box, and which cells are mostly shoe."""
    ys, xs = np.where(mask)
    rgb, mask = rgb[ys.min():ys.max() + 1, xs.min():xs.max() + 1], mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = mask.shape
    cells, valid = np.zeros((GRID, GRID, 3)), np.zeros((GRID, GRID), bool)
    for i in range(GRID):
        for j in range(GRID):
            m = mask[i * h // GRID:(i + 1) * h // GRID, j * w // GRID:(j + 1) * w // GRID]
            if m.size and m.mean() > 0.6:
                c = rgb[i * h // GRID:(i + 1) * h // GRID, j * w // GRID:(j + 1) * w // GRID]
                cells[i, j], valid[i, j] = np.median(c[m], axis=0), True
    return cells, valid


def _classes(cells: np.ndarray, palette: list, match_light: bool = False) -> np.ndarray:
    lab, pal = _lab(cells), _lab(np.array(palette)[None])[0]
    if match_light:   # a photo's light leather is darker than its true colour: its lightness stretched to the sheet's
        lit = lab[..., 0][lab[..., 0] > 0]
        if lit.size:
            lab[..., 0] = lab[..., 0] * (pal[:, 0].max() / max(float(np.percentile(lit, 95)), 1e-6))
    return (((lab[..., None, :] - pal[None, None]) ** 2) * np.array([1.0, 0.6, 0.6])).sum(-1).argmin(-1)


def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _palette(sheet: Mapping):
    """The sheet's colours (near-identical ones merged) and the outline's ink; which of them are left out of the upper,
    which are light, which are the sole's."""
    cols, roles, names = [], [], []
    for c in sheet.get("palette") or []:
        try:
            rgb = _rgb(str(c["hex"]))
        except (KeyError, ValueError, TypeError):
            continue
        role = str(c.get("role") or "").lower()
        lab = _lab(np.array([[rgb]]))[0, 0]
        same = next((i for i, q in enumerate(cols) if np.linalg.norm(_lab(np.array([[q]]))[0, 0] - lab) < MERGE_DE), None)
        if same is not None:
            if "sole" in roles[same] and "sole" not in role:
                roles[same], names[same] = role, str(c.get("name") or c["hex"])
            continue
        cols.append(rgb), roles.append(role), names.append(str(c.get("name") or c["hex"]))
    cols.append(_rgb(drawn.INK)), roles.append("ink"), names.append("ink")
    skip = {i for i, r in enumerate(roles) if any(w in r for w in SKIPPED)}
    light = {i for i, q in enumerate(cols) if i not in skip and _lab(np.array([[q]]))[0, 0, 0] >= LIGHT_L}
    sole = {i for i, r in enumerate(roles) if "sole" in r}
    return cols, names, skip, light, sole


def _upper(k: np.ndarray, v: np.ndarray, skip: set, sole: set) -> np.ndarray:
    """The cells of the upper: above the first row that is mostly sole (or the lowest quarter), less the left-out roles."""
    rows = [i for i in range(k.shape[0]) if v[i].any() and sole and np.isin(k[i][v[i]], list(sole)).mean() > 0.5]
    filled = [i for i in range(k.shape[0]) if v[i].any()]
    cut = min(rows) if rows else (filled[0] + int(0.75 * (filled[-1] - filled[0] + 1)) if filled else 0)
    up = v.copy()
    up[cut:] = False
    return up & ~np.isin(k, list(skip))


def _drawing_cells(shoe) -> tuple[np.ndarray, np.ndarray]:
    s = drawn.side(shoe)
    svg = (f'<svg xmlns="{drawn.SVG_NS}" viewBox="-100 -150 400 410" width="800" height="820">{s.behind}{s.front}</svg>')
    a = np.asarray(Image.open(io.BytesIO(drawn.render_png(svg, 800, 820))).convert("RGBA"))
    return _grid(a[..., :3].astype(np.float64), a[..., 3] > 200)


class FrontCheck:
    """The front photo, ready to measure straight-on drawings against (`problems`)."""

    def __init__(self, cells: np.ndarray, valid: np.ndarray):
        self.cells, self.valid = cells, valid

    @classmethod
    def of(cls, photo: Image.Image, mask_of: MaskOf | None) -> FrontCheck | None:
        small = photo.convert("RGB")
        small.thumbnail((900, 900))
        m = _mask(small, mask_of)
        if m is None:
            return None
        cells, valid = _grid(np.asarray(small, dtype=np.float64), m)
        return cls(cells, valid) if valid.sum() >= GRID else None

    def problems(self, shoe, sheet: Mapping) -> list[str]:
        """What is wrong with the drawing's light material against the photo, in plain words; empty when nothing is,
        or when the check does not apply."""
        cols, names, skip, light, sole = _palette(sheet)
        if not light:
            return []
        dc, dv = _drawing_cells(shoe)
        dk = _classes(dc, cols)
        keep = _upper(dk, dv, skip, sole)
        lc = _lab(dc)[..., 0][keep]   # the drawing's own lightness, cell by cell, on the upper
        top = float(np.percentile(lc, 90)) if lc.size else 0.0
        if top < LIGHT_L or float((lc <= top - CONTRAST_L).mean()) < MIN_SHARE:
            return []   # no large light area with a large, clearly darker one beside it: the check does not apply
        pk = _classes(self.cells, cols, match_light=True)
        pkeep = _upper(pk, self.valid, skip, sole)
        if not pkeep.any() or not keep.any():
            return []
        p, d = float(np.isin(pk[pkeep], list(light)).mean()), float(np.isin(dk[keep], list(light)).mean())
        if abs(p - d) <= TOLERANCE:
            return []
        which = " and ".join(names[i] for i in sorted(light))
        return [f"Measured against the front photo, the drawing has {'too much' if d > p else 'too little'} {which}: in "
                f"the photo it covers about {p:.0%} of the upper's front (the sole, laces and outlines left out), in the "
                f"drawing {d:.0%}. Look at the front photo again and draw each colour where, and as much as, it shows "
                "it: a colour the drawing has too much of is a panel drawn too large, or drawn where the photo shows "
                "another colour."]
