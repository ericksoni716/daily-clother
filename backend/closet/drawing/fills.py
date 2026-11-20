"""What goes inside the silhouette when it is taken from the photo rather than drawn plain: the shapes a measured
pattern is kept in (`closet.patterns` measures it, `stored` reads it back) and lifting a print off the photo.

- stripes: colours and band widths, drawn as bands (`Stripes`)
- swatch:  a tileable patch of the cloth (`Swatch`)
- graphic: the real print or logo, cropped with a transparent background (`extract_graphic`)

The phase-0 measuring that once lived here (dominant colours, a swatch picked from the cutout, stripes from one
profile) gave way to `closet.patterns`; it is in the git history.
"""
from __future__ import annotations

import base64
import io
from dataclasses import dataclass

import numpy as np
from PIL import Image


def _lab(rgb: np.ndarray) -> np.ndarray:
    import cv2
    return cv2.cvtColor(rgb.astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)


def _solid_mask(cutout: Image.Image, erode_frac: float = 0.015) -> np.ndarray:
    import cv2
    a = np.asarray(cutout.split()[-1])
    m = (a > 200).astype(np.uint8)
    k = max(3, int(max(cutout.size) * erode_frac) | 1)
    return cv2.erode(m, np.ones((k, k), np.uint8)).astype(bool)


# ------------------------------------------------------------------ swatch

@dataclass
class Swatch:
    image: Image.Image          # tileable RGB tile
    width_frac: float           # tile width as a fraction of the garment's width
    box: tuple[int, int, int, int]  # where it came from in the cutout
    method: str                 # how it was made ("measured" for a kept pattern)
    period: tuple[int, int] | None = None
    # where the garment's centre line, PLACE_AT from neck to hem, falls within the tile (fractions of its width and
    # height), so the pattern is drawn lined up with the buttons as it is on the garment; None = from the corner
    phase: tuple[float, float] | None = None
    # with a phase: the tile's width as a fraction of the garment's neck-to-hem length (sizes it against the body,
    # not the outline, whose width depends on how the sleeves lie)
    length_frac: float | None = None
    # with a phase: the other front's own placement (the viewer's right); None = the same as `phase`
    phase_right: tuple[float, float] | None = None


# ----------------------------------------------------------------- stripes

@dataclass
class Stripes:
    orientation: str                    # horizontal | vertical
    bands: list[tuple[str, float]]      # (hex, width as a fraction of garment height or width), one repeat


# ----------------------------------------------------------------- graphic

@dataclass
class Graphic:
    image: Image.Image                     # RGBA crop, background removed
    cx: float                              # centre x as a fraction of garment width
    top: float                             # top edge as a fraction of garment height
    width: float                           # width as a fraction of garment width
    box: tuple[int, int, int, int]


def extract_graphic(cutout: Image.Image, zone: tuple[float, float, float, float] = (0.2, 0.12, 0.8, 0.95),
                    lo: float = 14.0, hi: float = 34.0, edge_min: float = 40.0) -> Graphic | None:
    """Find a print that differs from the garment's base colour and lift it out.

    Chroma differences count fully and lightness differences only partly, so
    wrinkles and soft shadows are mostly ignored.
    """
    import cv2
    rgb = np.asarray(cutout.convert("RGB"))
    m = _solid_mask(cutout, 0.03)
    H, W = m.shape
    lab = _lab(rgb)
    base = np.median(lab[m], axis=0)
    # compare against local lighting so folds do not read as ink
    # (a wide median on a small copy: wide enough that a solid print does not count as "lighting")
    sc = 160 / max(W, H)
    small = cv2.resize(lab[..., 0], (max(8, int(W * sc)), max(8, int(H * sc))), interpolation=cv2.INTER_AREA)
    small_m = cv2.resize(m.astype(np.uint8), (small.shape[1], small.shape[0]), interpolation=cv2.INTER_NEAREST)
    small = np.where(small_m > 0, small, base[0]).astype(np.uint8)
    Lloc = cv2.resize(cv2.medianBlur(small, 61), (W, H), interpolation=cv2.INTER_LINEAR).astype(np.float32)
    dL = np.abs(lab[..., 0] - Lloc)
    dab = np.linalg.norm(lab[..., 1:] - base[1:], axis=-1)
    d = np.sqrt((0.9 * dL) ** 2 + dab ** 2)
    zm = np.zeros_like(m)
    zx0, zy0, zx1, zy1 = int(zone[0] * W), int(zone[1] * H), int(zone[2] * W), int(zone[3] * H)
    zm[zy0:zy1, zx0:zx1] = m[zy0:zy1, zx0:zx1]
    ink = ((d > hi) & zm).astype(np.uint8)
    k = max(3, (max(W, H) // 40) | 1)
    grouped = cv2.dilate(ink, np.ones((k, k), np.uint8))
    n, lbl, stats, _ = cv2.connectedComponentsWithStats(grouped)
    # prints have crisp edges, shadows fade in: drop soft-edged candidates
    Lf = cv2.GaussianBlur(lab[..., 0], (0, 0), max(1.0, max(W, H) / 800))
    grad = np.hypot(cv2.Sobel(Lf, cv2.CV_32F, 1, 0), cv2.Sobel(Lf, cv2.CV_32F, 0, 1))
    keep = [i for i in range(1, n) if (ink[lbl == i]).sum() > 0.0004 * W * H
            and np.percentile(grad[lbl == i], 90) > edge_min]
    if not keep:
        return None
    kept = np.isin(lbl, keep)
    # merge components that sit close to the biggest one
    big = max(keep, key=lambda i: stats[i, cv2.CC_STAT_AREA])
    bx, by, bw, bh = stats[big, :4]
    x0, y0, x1, y1 = bx, by, bx + bw, by + bh
    changed = True
    while changed:
        changed = False
        for i in keep:
            sx, sy, sw, sh = stats[i, :4]
            gap = max(W, H) * 0.06
            if sx < x1 + gap and sx + sw > x0 - gap and sy < y1 + gap and sy + sh > y0 - gap:
                nx0, ny0, nx1, ny1 = min(x0, sx), min(y0, sy), max(x1, sx + sw), max(y1, sy + sh)
                if (nx0, ny0, nx1, ny1) != (x0, y0, x1, y1):
                    x0, y0, x1, y1 = nx0, ny0, nx1, ny1
                    changed = True
    alpha = np.clip((d - lo) / (hi - lo), 0, 1) * zm * kept
    crop = np.dstack([rgb[y0:y1, x0:x1], (alpha[y0:y1, x0:x1] * 255).astype(np.uint8)])
    return Graphic(Image.fromarray(crop, "RGBA"), ((x0 + x1) / 2) / W, y0 / H, (x1 - x0) / W, (int(x0), int(y0), int(x1), int(y1)))


def data_uri(img: Image.Image, max_edge: int = 320, fmt: str | None = None, quality: int = 82) -> str:
    im = img.copy()
    im.thumbnail((max_edge, max_edge), Image.LANCZOS)
    buf = io.BytesIO()
    if fmt is None:
        fmt = "PNG" if im.mode == "RGBA" else "JPEG"
    if fmt == "JPEG":
        im.convert("RGB").save(buf, "JPEG", quality=quality)
        mime = "image/jpeg"
    elif fmt == "WEBP":
        im.save(buf, "WEBP", quality=quality)
        mime = "image/webp"
    else:
        im.save(buf, "PNG", optimize=True)
        mime = "image/png"
    return f"data:{mime};base64," + base64.b64encode(buf.getvalue()).decode()
