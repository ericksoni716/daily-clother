"""What goes inside the silhouette, taken from the photo rather than drawn.

- solid:   dominant colour of the cutout
- stripes: colours and band widths measured from the photo, then drawn
- swatch:  a patch of real fabric, lighting-flattened and made tileable
- graphic: the real print or logo, cropped with a transparent background
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


def _hex(rgb) -> str:
    r, g, b = (int(round(float(v))) for v in rgb)
    return f"#{max(0, min(255, r)):02x}{max(0, min(255, g)):02x}{max(0, min(255, b)):02x}"


def _solid_mask(cutout: Image.Image, erode_frac: float = 0.015) -> np.ndarray:
    import cv2
    a = np.asarray(cutout.split()[-1])
    m = (a > 200).astype(np.uint8)
    k = max(3, int(max(cutout.size) * erode_frac) | 1)
    return cv2.erode(m, np.ones((k, k), np.uint8)).astype(bool)


def dominant_colors(cutout: Image.Image, k: int = 5) -> list[tuple[str, float]]:
    """Main colours of the garment as (hex, share), largest first.

    K-means in Lab, then clusters that differ only by brightness are merged
    into one family, because they are the same cloth in light and in shadow.
    A family's brightness is taken near its bright end: shadows only ever
    darken, so the lit part is closer to the real colour.
    """
    import cv2
    rgb = np.asarray(cutout.convert("RGB"))
    m = _solid_mask(cutout)
    px = rgb[m]
    if len(px) > 40000:
        px = px[np.random.default_rng(0).choice(len(px), 40000, replace=False)]
    lab = _lab(px[None])[0]
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    cv2.setRNGSeed(0)
    _, labels, centers = cv2.kmeans(lab, k, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    labels = labels.ravel()
    parent = list(range(k))

    def find(i):
        while parent[i] != i:
            i = parent[i]
        return i

    order = np.argsort(centers[:, 0])
    for a, b in zip(order[:-1], order[1:]):
        if np.linalg.norm(centers[a, 1:] - centers[b, 1:]) < 9 and abs(centers[a, 0] - centers[b, 0]) < 30:
            parent[find(int(a))] = find(int(b))
    out = []
    for root in {find(i) for i in range(k)}:
        sel = np.isin(labels, [i for i in range(k) if find(i) == root])
        if not sel.any():
            continue
        fam = lab[sel]
        color = np.array([np.percentile(fam[:, 0], 80), np.median(fam[:, 1]), np.median(fam[:, 2])], dtype=np.float32)
        rgb1 = cv2.cvtColor(color[None, None].astype(np.uint8), cv2.COLOR_LAB2RGB)[0, 0]
        out.append((_hex(rgb1), float(sel.mean())))
    return sorted(out, key=lambda t: -t[1])


_NAMED_L = {"white": (238, None), "cream": (232, None), "black": (None, 34)}


def snap_to_named(hex_: str, name: str | None) -> str:
    """Let the attribute's colour word correct what lighting did to the photo.

    Only whites and blacks are adjusted: a white shoe shot in shade measures
    grey, and a black tee under a lamp measures charcoal.
    """
    import cv2
    if not name or name not in _NAMED_L:
        return hex_
    rgb = np.array([[[int(hex_[i:i + 2], 16) for i in (1, 3, 5)]]], dtype=np.uint8)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)[0, 0]
    lo, hi = _NAMED_L[name]
    if lo is not None:
        lab[0] = max(lab[0], lo)
        keep = 0.35 if name == "white" else 0.7
        lab[1:] = 128 + (lab[1:] - 128) * keep
    if hi is not None:
        lab[0] = min(lab[0], hi)
    return _hex(cv2.cvtColor(lab[None, None].astype(np.uint8), cv2.COLOR_LAB2RGB)[0, 0])


# ------------------------------------------------------------------ swatch

@dataclass
class Swatch:
    image: Image.Image          # tileable RGB tile
    width_frac: float           # tile width as a fraction of the garment's width
    box: tuple[int, int, int, int]  # where it came from in the cutout
    method: str                 # "periodic" or "mirror"
    period: tuple[int, int] | None = None
    # where the garment's centre line, PLACE_AT from neck to hem, falls within the tile (fractions of its width and
    # height), so the pattern is drawn lined up with the buttons as it is on the garment; None = from the corner
    phase: tuple[float, float] | None = None
    # with a phase: the tile's width as a fraction of the garment's neck-to-hem length (sizes it against the body,
    # not the outline, whose width depends on how the sleeves lie)
    length_frac: float | None = None


def _flatten_lighting(rgb: np.ndarray) -> np.ndarray:
    """Remove a smooth brightness gradient (plane + curvature) from a patch."""
    import cv2
    lab = _lab(rgb)
    L = lab[..., 0]
    h, w = L.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    xx, yy = xx / w - 0.5, yy / h - 0.5
    A = np.stack([np.ones_like(xx), xx, yy, xx * xx, yy * yy, xx * yy], -1).reshape(-1, 6)
    coef, *_ = np.linalg.lstsq(A, L.reshape(-1), rcond=None)
    trend = (A @ coef).reshape(h, w)
    lab[..., 0] = np.clip(L - trend + coef[0], 0, 255)
    return cv2.cvtColor(lab.astype(np.uint8), cv2.COLOR_LAB2RGB)


def _period(profile: np.ndarray, min_lag: int, max_lag: int) -> tuple[int, float] | None:
    x = profile - profile.mean()
    if np.allclose(x, 0):
        return None
    ac = np.correlate(x, x, "full")[len(x) - 1:]
    ac = ac / ac[0]
    # normalise for the shrinking overlap
    ac = ac * len(x) / (len(x) - np.arange(len(x)))
    best = None
    for lag in range(min_lag, min(max_lag, len(ac) - 2)):
        if ac[lag] > ac[lag - 1] and ac[lag] >= ac[lag + 1] and ac[lag] > 0.45:
            if best is None or ac[lag] > best[1] + 0.08:
                best = (lag, float(ac[lag]))
                if ac[lag] > 0.6:
                    break
    return best


def _is_periodic(chan: np.ndarray, lag: int, axis: int) -> bool:
    """Check a candidate period by sliding the patch over itself."""
    a = chan[:, :-lag] if axis == 1 else chan[:-lag]
    b = chan[:, lag:] if axis == 1 else chan[lag:]
    if a.size < 64:
        return False
    return float(np.mean((a - b) ** 2)) < 0.35 * float(chan.var() + 1e-6)


def pick_swatch(cutout: Image.Image, target_frac: float = 0.5,
                zone: tuple[float, float, float, float] = (0.2, 0.22, 0.8, 0.88),
                avoid_center: bool = False, organic: bool = False) -> Swatch:
    """Find the best square of fabric inside the garment and make it tile.

    `zone` restricts the search to the body of the garment (fractions of the
    cutout), keeping sleeves and collars out. `avoid_center` also skips the
    middle strip, where a button placket or zip would end up in the tile.
    The winning patch is evenly lit and has the same colour mix as the
    garment as a whole. `organic` says the pattern has no straight repeat
    (floral, camouflage, knit texture), which changes how the tile is made
    to wrap.
    """
    import cv2
    rgb = np.asarray(cutout.convert("RGB"))
    m = _solid_mask(cutout, 0.01).astype(np.uint8)
    H, W = m.shape
    zx0, zy0, zx1, zy1 = int(zone[0] * W), int(zone[1] * H), int(zone[2] * W), int(zone[3] * H)
    zm = np.zeros_like(m)
    zm[zy0:zy1, zx0:zx1] = m[zy0:zy1, zx0:zx1]
    if avoid_center:
        xs = np.where(m.any(0))[0]
        mid = int((xs.min() + xs.max()) / 2)
        gap = max(4, int(0.035 * W))
        zm[:, mid - gap: mid + gap] = 0
    dist = cv2.distanceTransform(zm, cv2.DIST_C, 3)  # half-size of largest inscribed square
    half = int(min(dist.max() * 0.97, target_frac * W / 2))
    if half < 12:
        raise ValueError("no usable fabric area for a swatch")
    k = (2 * half) | 1
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    mean = cv2.blur(gray, (k, k))
    low = cv2.GaussianBlur(gray, (0, 0), half / 2)
    uneven = cv2.blur((low - mean) ** 2, (k, k))
    # colour mix: share of each colour cluster inside the patch vs the garment
    lab = _lab(rgb)
    px = lab[m.astype(bool)]
    sub = px[np.random.default_rng(0).choice(len(px), min(len(px), 20000), replace=False)]
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    cv2.setRNGSeed(0)
    _, lbl, centers = cv2.kmeans(sub, 5, None, crit, 2, cv2.KMEANS_PP_CENTERS)
    share = np.bincount(lbl.ravel(), minlength=5) / len(sub)
    nearest = np.argmin(((lab[:, :, None, :] - centers[None, None]) ** 2).sum(-1), -1)
    mix = np.zeros((H, W), np.float32)
    for i in range(5):
        mix += np.abs(cv2.blur((nearest == i).astype(np.float32), (k, k)) - share[i])
    fits = dist >= half
    if not fits.any():
        raise ValueError("no usable fabric area for a swatch")
    score = uneven / (np.median(uneven[fits]) + 1e-6) + 4.0 * mix
    score = np.where(fits, score, np.inf)
    cy, cx = np.unravel_index(np.argmin(score), score.shape)
    x0, y0 = int(cx - half), int(cy - half)
    patch = _flatten_lighting(rgb[y0:y0 + 2 * half, x0:x0 + 2 * half])
    g = cv2.cvtColor(patch, cv2.COLOR_RGB2LAB).astype(np.float32)
    n = patch.shape[0]

    def axis_period(axis: int):
        best = None
        for c in range(3):
            prof = g[..., c].mean(0 if axis == 1 else 1)
            got = _period(prof, max(8, n // 10), n * 3 // 4)
            if got and _is_periodic(g[..., c], got[0], axis) and (best is None or got[1] > best[1]):
                best = got
        return best

    px_, py_ = (None, None) if organic else (axis_period(1), axis_period(0))
    if px_ and py_:
        nx, ny = max(1, n // px_[0]), max(1, n // py_[0])
        tile = _blend_edges(patch[: ny * py_[0], : nx * px_[0]])
        return Swatch(Image.fromarray(tile), tile.shape[1] / W, (x0, y0, x0 + tile.shape[1], y0 + tile.shape[0]),
                      "periodic", (px_[0], py_[0]))
    if organic:
        tile = _fade_tile(patch)
        return Swatch(Image.fromarray(tile), tile.shape[1] / W, (x0, y0, x0 + 2 * half, y0 + 2 * half), "fade")
    top = np.concatenate([patch, patch[:, ::-1]], 1)
    tile = np.concatenate([top, top[::-1]], 0)
    return Swatch(Image.fromarray(tile), tile.shape[1] / W, (x0, y0, x0 + 2 * half, y0 + 2 * half), "mirror")


def _fade_tile(patch: np.ndarray) -> np.ndarray:
    """Make an irregular texture wrap: blend the patch with a half-shifted copy.

    The shifted copy is continuous across the tile's edges, so using it near
    the edges and the original in the middle leaves no seam. Suits florals,
    camouflage and knit textures; straight lines would ghost, so plaids use
    the mirrored tile instead.
    """
    t = patch.astype(np.float32)
    h, w = t.shape[:2]
    rolled = np.roll(t, (h // 2, w // 2), (0, 1))
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    edge = np.minimum(np.minimum(xx, w - 1 - xx) / (w * 0.5), np.minimum(yy, h - 1 - yy) / (h * 0.5))
    mask = np.clip((edge - 0.12) / 0.3, 0, 1)
    mask = (mask * mask * (3 - 2 * mask))[..., None]
    return np.clip(t * mask + rolled * (1 - mask), 0, 255).astype(np.uint8)


def _blend_edges(tile: np.ndarray, frac: float = 0.06) -> np.ndarray:
    """Cross-fade opposite edges so small misalignments do not show as seams."""
    t = tile.astype(np.float32)
    h, w = t.shape[:2]
    bw, bh = max(2, int(w * frac)), max(2, int(h * frac))
    for i in range(bw):
        a = 0.5 * (1 - i / bw)
        l, r = t[:, i].copy(), t[:, w - 1 - i].copy()
        t[:, i] = l * (1 - a) + r * a
        t[:, w - 1 - i] = r * (1 - a) + l * a
    for i in range(bh):
        a = 0.5 * (1 - i / bh)
        u, d = t[i].copy(), t[h - 1 - i].copy()
        t[i] = u * (1 - a) + d * a
        t[h - 1 - i] = d * (1 - a) + u * a
    return np.clip(t, 0, 255).astype(np.uint8)


# ----------------------------------------------------------------- stripes

@dataclass
class Stripes:
    orientation: str                    # horizontal | vertical
    bands: list[tuple[str, float]]      # (hex, width as a fraction of garment height or width), one repeat


def measure_stripes(cutout: Image.Image, orientation: str = "horizontal", n_colors: int = 2) -> Stripes:
    import cv2
    sw_src = np.asarray(cutout.convert("RGB"))
    m = _solid_mask(cutout, 0.01)
    H, W = m.shape
    x0, x1, y0, y1 = int(W * 0.36), int(W * 0.64), int(H * 0.28), int(H * 0.8)
    if orientation == "vertical":
        x0, x1, y0, y1 = int(W * 0.28), int(W * 0.72), int(H * 0.4), int(H * 0.7)
    reg, rm = sw_src[y0:y1, x0:x1].astype(np.float32), m[y0:y1, x0:x1]
    axis = 1 if orientation == "horizontal" else 0
    cnt = np.maximum(rm.sum(axis), 1)[:, None]
    prof = (reg * rm[..., None]).sum(axis) / cnt
    prof = cv2.GaussianBlur(prof[None], (0, 0), 1.2)[0]
    lab = _lab(prof[None])[0]
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    _, labels, _ = cv2.kmeans(lab, n_colors, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    labels = labels.ravel()
    colors = {i: _hex(np.median(prof[labels == i], axis=0)) for i in range(n_colors) if (labels == i).any()}
    runs: list[tuple[int, int]] = []
    for lab_i in labels:
        if runs and runs[-1][0] == lab_i:
            runs[-1] = (lab_i, runs[-1][1] + 1)
        else:
            runs.append((int(lab_i), 1))
    runs = [r for r in runs[1:-1] if r[1] >= 2] or runs
    full = H if orientation == "horizontal" else W
    seq, seen = [], []
    for lab_i, _ in runs:
        if lab_i not in seen:
            seen.append(lab_i)
    for lab_i in seen:
        lens = [n for l, n in runs if l == lab_i]
        seq.append((colors[lab_i], float(np.median(lens)) / full))
    return Stripes(orientation, seq)


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
