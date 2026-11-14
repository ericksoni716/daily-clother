"""Trace shoe photos into the flat drawing style, and find out whether it works (#192, stage 1).

    python -m closet_bench.trace_shoes [--photos private/shoes] [--out out/trace_shoes]
                                       [--cutout auto|model|grabcut] [--model isnet-general-use] [--no-png]

For every photo in the folder (side-on photos of one shoe each; `private/` is git-ignored):

1. Cut the shoe out with the app's own background removal (`closet.cutout`) when its model file is in
   `models/`, otherwise with OpenCV's GrabCut.
2. Turn it so it lies the way the templates draw a shoe: sole level, toe to the left.
3. Trace it with each approach in `APPROACHES` (k-means colours; mean-shift then k-means; bilateral
   filter then k-means; two settings each): the silhouette, colour regions in the shoe's measured colours,
   marks (logos, stripes, panels) as paths, the sole as its own region, specks removed and curves smoothed,
   drawn with the app's outline weight.
4. Score each trace (silhouette IoU against the cut-out, colour error of its regions against the photo,
   how many colours and paths, whether the high-contrast marks survived) and combine the scores.
5. Check the photo against a quality gate made of measured signals (`GATE`), so that the app can later fall
   back to its template drawing on its own when a photo is too poor to trace.

It writes one comparison sheet per photo (`shoe-NN.sheet.svg`, and `.png` when Chrome or Chromium is on the
PATH): the photo, the cut-out, every trace and today's template drawing, at item size and at grid-tile
size; an `index.html` with the scores, the gate and the recommended approach; and `results.json`.

The template drawing is drawn from a tagger answer saved beside the photo as `<photo name>.json`, when
there is one; otherwise from the measured colour and a sneaker of the measured height. Photos are listed
by number in name order, never by file name.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from . import cutout as C
from . import fills
from .illustrate import CARD, INK, luminance, shade

ROOT = Path(__file__).resolve().parent.parent
PHOTO_TYPES = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif")

WORK = 480            # the shoe's longer side, in px, while it is traced and scored
PAD = 0.06            # background kept round the shoe, as a share of its longer side
MERGE_DE = 10.0       # two colours closer than this (CIE76 ΔE) are one colour of the shoe
SPECK = 0.0015        # a patch smaller than this share of the shoe is a speck and joins its neighbour
SOLE_MAX = 0.35       # the sole is at most this share of the shoe's height
CORNER = 60.0         # a traced outline turning more sharply than this (degrees) keeps a corner there
MARK_DE = 22.0        # a mark differs from the cloth round it by more than this
OUTLINE_W, INNER_W = 3.8, 1.5   # style B, the app's: a bold outer edge, inner lines about a third of it
CARD_W, CARD_H = 400, 460       # the drawing's card, as the templates draw it
SHOE_X0, SHOE_L, SHOE_G = 40.0, 320.0, 330.0   # the templates' toe x, toe-to-heel length and ground y
ITEM_PX, TILE_PX = 400, 160     # the item page shows a drawing about 400 px wide; a closet grid tile about 160


@dataclass(frozen=True)
class Approach:
    name: str
    label: str
    prefilter: str            # none | meanshift | bilateral
    colors: int               # the most colours the upper is quantised to (close ones are then merged)
    smooth: float             # contour simplification, as a share of the shoe's longer side
    blur: float               # how strongly region edges are smoothed before tracing (px at WORK)
    sp: int = 0               # mean-shift spatial radius
    sr: int = 0               # mean-shift colour radius


APPROACHES = (
    Approach("kmeans-4", "k-means, 4 colours", "none", 4, 0.004, 1.5),
    Approach("kmeans-6", "k-means, 6 colours, light smoothing", "none", 6, 0.0025, 1.0),
    Approach("meanshift-soft", "mean-shift (8/16), then 5 colours", "meanshift", 5, 0.003, 1.2, 8, 16),
    Approach("meanshift-strong", "mean-shift (16/32), then 5 colours", "meanshift", 5, 0.005, 2.0, 16, 32),
    Approach("bilateral-5", "bilateral filter, then 5 colours", "bilateral", 5, 0.003, 1.2),
    Approach("bilateral-5-smooth", "bilateral filter, 5 colours, strong smoothing", "bilateral", 5, 0.007, 2.5),
)

# The quality gate: signal -> (limit, "below" or "above" fails, the reason in plain words)
GATE = {
    "found": (0.5, "below", "no shoe was found in the photo"),
    "size_px": (250.0, "below", "the shoe is too small in the photo"),
    "sharpness": (0.08, "below", "the photo is blurred"),
    "contrast_de": (8.0, "below", "the shoe hardly stands out from the background"),
    "clipped": (0.35, "above", "too much of the shoe is pure white or pure black (over- or under-exposed)"),
    "edge_touch": (0.03, "above", "the shoe runs off the edge of the photo"),
    "second_piece": (0.15, "above", "there is more than one thing in the photo (two shoes, or a hand)"),
    "solidity": (0.80, "below", "the outline is broken up: something covers the shoe, or background got into the cut-out"),
    "aspect": (0.9, "below", "not side-on: the shoe is taller than it is long"),
    "ground": (0.4, "below", "no flat sole along the bottom: probably not side-on"),
    "toe_heel": (0.06, "below", "toe and heel look alike: probably taken from the front, back or top"),
    "trace_iou": (0.9, "below", "even the best trace strays from the cut-out"),
}


# ------------------------------------------------------------------ colour

def to_lab(rgb: np.ndarray) -> np.ndarray:
    """uint8 RGB -> float Lab (L 0..100)."""
    return cv2.cvtColor(rgb.astype(np.float32) / 255.0, cv2.COLOR_RGB2Lab)


def lab_hex(lab) -> str:
    rgb = cv2.cvtColor(np.asarray(lab, np.float32).reshape(1, 1, 3), cv2.COLOR_Lab2RGB)[0, 0]
    r, g, b = (int(round(float(np.clip(v, 0, 1)) * 255)) for v in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def delta_e(a, b) -> float:
    return float(np.linalg.norm(np.asarray(a, np.float64) - np.asarray(b, np.float64)))


# ------------------------------------------------------------------ cut-out

def grabcut_mask(img: Image.Image) -> np.ndarray:
    """A foreground mask (uint8 0/255, the photo's size) from GrabCut started on the whole photo but a thin border."""
    rgb = np.asarray(img.convert("RGB"))
    s = min(1.0, 640 / max(rgb.shape[:2]))
    small = cv2.resize(rgb, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else rgb.copy()
    h, w = small.shape[:2]
    mx, my = max(2, int(w * 0.03)), max(2, int(h * 0.03))
    m = np.zeros((h, w), np.uint8)
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.setRNGSeed(0)
    bgr = cv2.cvtColor(small, cv2.COLOR_RGB2BGR)
    cv2.grabCut(bgr, m, (mx, my, w - 2 * mx, h - 2 * my), bgd, fgd, 6, cv2.GC_INIT_WITH_RECT)
    fg = np.isin(m, (cv2.GC_FGD, cv2.GC_PR_FGD))
    # a shadow on the ground is the background's colour, only darker: offer it back to the background and let
    # GrabCut decide again (a grey shoe's own pixels stay, since they are in its model of the shoe)
    lab = to_lab(small)
    border = np.concatenate([lab[:my].reshape(-1, 3), lab[-my:].reshape(-1, 3), lab[:, :mx].reshape(-1, 3),
                             lab[:, -mx:].reshape(-1, 3)])
    ground = np.median(border, axis=0)
    darker = ground[0] - lab[..., 0]
    shadow = fg & (np.linalg.norm(lab[..., 1:] - ground[1:], axis=-1) < 7) & (darker > 4) & (darker < 55)
    if shadow.any():
        m[shadow] = cv2.GC_PR_BGD
        cv2.grabCut(bgr, m, None, bgd, fgd, 4, cv2.GC_INIT_WITH_MASK)
        fg = np.isin(m, (cv2.GC_FGD, cv2.GC_PR_FGD))
    fg = fg.astype(np.uint8) * 255
    return cv2.resize(fg, (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_LINEAR)


def model_mask(img: Image.Image, model: str, models_dir: Path) -> np.ndarray | None:
    """The app's own background removal, when its model file is already in `models_dir` (never downloaded here)."""
    if not (models_dir / f"{model}.onnx").exists():
        return None
    from closet import cutout as app_cutout
    path = C.ensure_model(model, models_dir)   # checks the pinned checksum
    return np.asarray(app_cutout.predict_mask(img, model, path))


def clean_mask(soft: np.ndarray) -> tuple[np.ndarray, float]:
    """The largest piece of the mask (0/1) with its small holes filled, and the second piece's size against it."""
    m = (soft > 127).astype(np.uint8)
    n, cc, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    if n <= 1:
        return np.zeros_like(m), 0.0
    areas = stats[1:, cv2.CC_STAT_AREA]
    order = np.argsort(areas)[::-1]
    second = float(areas[order[1]] / areas[order[0]]) if len(order) > 1 else 0.0
    m = (cc == order[0] + 1).astype(np.uint8)
    holes = (1 - m).astype(np.uint8)
    hn, hcc, hstats, _ = cv2.connectedComponentsWithStats(holes, connectivity=4)
    limit = 0.01 * m.sum()
    for j in range(1, hn):
        x, y, w, h, a = hstats[j]
        inside = x > 0 and y > 0 and x + w < m.shape[1] and y + h < m.shape[0]
        if inside and a < limit:
            m[hcc == j] = 1
    return m, second


# ------------------------------------------------------------------ orientation

def _rotate(arr: np.ndarray, angle: float, border: int, interp: int = cv2.INTER_LINEAR) -> np.ndarray:
    h, w = arr.shape[:2]
    rot = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    cos, sin = abs(rot[0, 0]), abs(rot[0, 1])
    nw, nh = int(h * sin + w * cos) + 1, int(h * cos + w * sin) + 1
    rot[0, 2] += nw / 2 - w / 2
    rot[1, 2] += nh / 2 - h / 2
    return cv2.warpAffine(arr, rot, (nw, nh), flags=interp, borderMode=border)


def ground_edge(mask: np.ndarray) -> tuple[float, float]:
    """The ground line: the longest edge of the convex hull that faces down (within 50 degrees).
    Returns its angle in degrees (image coordinates) and its length in px."""
    cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(cs, key=cv2.contourArea)
    hull = cv2.convexHull(c)[:, 0, :].astype(np.float64)
    centre = hull.mean(axis=0)
    best, angle = 0.0, 0.0
    for i in range(len(hull)):
        p, q = hull[i], hull[(i + 1) % len(hull)]
        e = q - p
        length = float(np.hypot(*e))
        if length < 1:
            continue
        n = np.array([e[1], -e[0]]) / length
        if np.dot(n, (p + q) / 2 - centre) < 0:
            n = -n
        if n[1] > np.cos(np.radians(50)) and length > best:
            best = length
            angle = float(np.degrees(np.arctan2(e[1], e[0])))
            if angle > 90:
                angle -= 180
            elif angle <= -90:
                angle += 180
    return angle, best


@dataclass
class Oriented:
    rgb: np.ndarray           # the shoe, sole level and toe to the left, with a little background round it (WORK scale)
    mask: np.ndarray          # 0/1, the same size
    angle: float              # how far the photo was turned (degrees)
    flipped: bool             # whether it was mirrored to put the toe on the left
    toe_heel: float           # how clearly the toe end is lower than the heel end (0 = alike)
    ground: float             # the flat sole's length as a share of the shoe's length
    aspect: float             # length / height


def orient(rgb: np.ndarray, mask: np.ndarray) -> Oriented:
    angle, _ = ground_edge(mask)
    if abs(angle) > 0.3:
        rgb = _rotate(rgb, angle, cv2.BORDER_REPLICATE)
        mask = (_rotate(mask * 255, angle, cv2.BORDER_CONSTANT) > 127).astype(np.uint8)
        mask, _ = clean_mask(mask * 255)
    ys, xs = np.nonzero(mask)
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    w, h = x1 - x0, y1 - y0
    # the toe end of a side view is lower than the heel end
    cols = mask[y0:y1, x0:x1]
    present = cols.any(axis=0)
    top = np.where(present, cols.argmax(axis=0), h)
    bottom = np.where(present, h - cols[::-1].argmax(axis=0), 0)
    heights = np.where(present, bottom - top, 0).astype(np.float64)
    q = max(1, w // 4)
    left, right = heights[:q].mean(), heights[-q:].mean()
    toe_heel = abs(left - right) / max(left, right, 1.0)
    flipped = bool(left > right)
    _, ground_len = ground_edge(mask)
    pad = int(round(PAD * max(w, h)))
    H, W = mask.shape
    cx0, cy0, cx1, cy1 = max(0, x0 - pad), max(0, y0 - pad), min(W, x1 + pad), min(H, y1 + pad)
    rgb, mask = rgb[cy0:cy1, cx0:cx1], mask[cy0:cy1, cx0:cx1]
    if flipped:
        rgb, mask = rgb[:, ::-1], mask[:, ::-1]
    s = WORK / max(w, h)
    size = (max(1, int(round(rgb.shape[1] * s))), max(1, int(round(rgb.shape[0] * s))))
    rgb = cv2.resize(np.ascontiguousarray(rgb), size, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
    mask = (cv2.resize(np.ascontiguousarray(mask) * 255, size, interpolation=cv2.INTER_LINEAR) > 127).astype(np.uint8)
    return Oriented(rgb, mask, angle, flipped, float(toe_heel), float(ground_len / max(w, 1)), float(w / max(h, 1)))


# ------------------------------------------------------------------ tracing

@dataclass
class Region:
    color: str
    lab: np.ndarray
    part: str                                  # silhouette | upper | sole
    paths: list[list[np.ndarray]]              # each path: an outer contour and its holes (float px at WORK)


@dataclass
class Trace:
    approach: Approach
    regions: list[Region]                      # in paint order; regions[0] is the silhouette in the main colour
    shape: tuple[int, int]                     # the working image's (height, width)

    @property
    def colors(self) -> int:
        return len({r.color for r in self.regions})

    @property
    def paths(self) -> int:
        return sum(len(r.paths) for r in self.regions)


def prefilter(rgb: np.ndarray, mask: np.ndarray, a: Approach) -> np.ndarray:
    if a.prefilter == "none":
        return rgb
    fill = rgb.copy()
    fill[mask == 0] = np.median(rgb[mask > 0], axis=0).astype(np.uint8)
    bgr = cv2.cvtColor(fill, cv2.COLOR_RGB2BGR)
    if a.prefilter == "meanshift":
        bgr = cv2.pyrMeanShiftFiltering(bgr, a.sp, a.sr)
    else:
        for _ in range(3):
            bgr = cv2.bilateralFilter(bgr, 9, 30, 7)
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def quantise(feat: np.ndarray, real: np.ndarray, k: int) -> tuple[np.ndarray, list[np.ndarray]]:
    """k-means on `feat` (N x 3 Lab), then clusters closer than MERGE_DE merged. Returns labels and the
    clusters' real colours (the mean of `real`, the unfiltered photo, over each cluster)."""
    k = max(1, min(k, len(feat)))
    cv2.setRNGSeed(0)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    _, labels, _ = cv2.kmeans(feat.astype(np.float32), k, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    labels = labels.ravel()
    while True:
        ids = [i for i in np.unique(labels)]
        cols = {i: real[labels == i].mean(axis=0) for i in ids}
        pair, best = None, MERGE_DE
        for ai, i in enumerate(ids):
            for j in ids[ai + 1:]:
                d = delta_e(cols[i], cols[j])
                if d < best:
                    pair, best = (i, j), d
        if pair is None:
            break
        labels[labels == pair[1]] = pair[0]
    ids = list(np.unique(labels))
    remap = np.zeros(int(labels.max()) + 1, np.int32)
    for n, i in enumerate(ids):
        remap[i] = n
    labels = remap[labels]
    return labels, [real[labels == n].mean(axis=0) for n in range(len(ids))]


def smooth_labels(lmap: np.ndarray, region: np.ndarray, n: int, sigma: float) -> np.ndarray:
    """A mode filter: each pixel of `region` takes the label most present round it (Gaussian-weighted)."""
    if sigma <= 0 or n <= 1:
        return lmap
    stack = np.stack([cv2.GaussianBlur((lmap == i).astype(np.float32), (0, 0), sigma) for i in range(n)])
    out = lmap.copy()
    out[region > 0] = stack.argmax(axis=0)[region > 0]
    return out


def remove_specks(lmap: np.ndarray, region: np.ndarray, min_area: int) -> np.ndarray:
    """Patches smaller than `min_area` take the label most common round their edge."""
    kernel = np.ones((3, 3), np.uint8)
    for _ in range(4):
        changed = False
        for i in np.unique(lmap[region > 0]):
            n, cc, stats, _ = cv2.connectedComponentsWithStats(((lmap == i) & (region > 0)).astype(np.uint8), connectivity=8)
            for j in range(1, n):
                x, y, w, h, a = stats[j]
                if a >= min_area:
                    continue
                x0, y0 = max(0, x - 2), max(0, y - 2)
                x1, y1 = min(lmap.shape[1], x + w + 2), min(lmap.shape[0], y + h + 2)
                comp = (cc[y0:y1, x0:x1] == j).astype(np.uint8)
                ring = (cv2.dilate(comp, kernel) > 0) & (comp == 0) & (region[y0:y1, x0:x1] > 0)
                vals = lmap[y0:y1, x0:x1][ring]
                vals = vals[vals != i]
                if len(vals):
                    sub = lmap[y0:y1, x0:x1]
                    sub[comp > 0] = np.bincount(vals).argmax()
                    changed = True
        if not changed:
            break
    return lmap


def sole_region(lab: np.ndarray, mask: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """The sole: the band along the bottom of the shoe, found as the run of the bottom colour up each column, or,
    when the sole is the upper's colour, as the strongest horizontal edge above the bottom."""
    h, w = mask.shape
    present = mask.any(axis=0)
    xs = np.nonzero(present)[0]
    bottom = np.where(present, h - 1 - mask[::-1].argmax(axis=0), 0)
    top = np.where(present, mask.argmax(axis=0), 0)
    shoe_h = float((bottom - top)[present].max())
    cap = SOLE_MAX * shoe_h
    upper_rows = np.zeros_like(mask)
    for x in xs:
        upper_rows[top[x]:max(top[x], int(bottom[x] - cap)), x] = 1
    main = np.bincount(labels[(upper_rows > 0) & (mask > 0)].ravel()).argmax() if (upper_rows & mask).any() else -1
    bottom_label = np.array([labels[max(0, bottom[x] - 2), x] for x in xs])
    same = np.bincount(bottom_label[bottom_label >= 0]).argmax() == main if (bottom_label >= 0).any() else True
    run = np.full(w, np.nan)
    if not same:
        for x, bl in zip(xs, bottom_label, strict=True):
            y, gap, limit = bottom[x] - 2, 0, min(cap, 0.8 * (bottom[x] - top[x]))
            while y > bottom[x] - limit and gap <= 2:
                gap = 0 if labels[y, x] == bl else gap + 1
                y -= 1
            run[x] = bottom[x] - (y + gap)
    else:
        gy = np.abs(cv2.Sobel(cv2.GaussianBlur(lab[..., 0], (0, 0), 1.2), cv2.CV_32F, 0, 1, ksize=3)) / 8
        for x in xs:
            lo, hi = int(bottom[x] - min(cap, 0.8 * (bottom[x] - top[x]))), bottom[x] - 3
            if hi - lo < 3:
                continue
            col = gy[lo:hi, x] * mask[lo:hi, x]
            if col.max() >= 2.5:
                run[x] = bottom[x] - (lo + int(col.argmax()))
    good = run[xs]
    if np.isnan(good).all() or np.nanmedian(good) >= 0.95 * cap:
        run[xs] = 0.1 * shoe_h
    else:
        fill = np.nanmedian(good)
        good = np.where(np.isnan(good), fill, good)
        k = max(3, (len(xs) // 14) | 1)
        good = cv2.medianBlur(np.clip(good, 0, 255).astype(np.uint8).reshape(1, -1), min(k, 255)).ravel().astype(np.float64)
        run[xs] = np.clip(good, 0.04 * shoe_h, cap)
    sole = np.zeros_like(mask)
    for x in xs:
        sole[int(round(bottom[x] - run[x])):bottom[x] + 1, x] = 1
    return sole & mask


def _contours(binary: np.ndarray, eps: float, min_area: float) -> list[list[np.ndarray]]:
    """The pieces of a binary image as paths: [outer, holes...], simplified by `eps` px."""
    cs, hier = cv2.findContours(binary.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if hier is None:
        return []
    hier = hier[0]
    out = []
    for i, c in enumerate(cs):
        if hier[i][3] != -1 or cv2.contourArea(c) < min_area:
            continue
        path = [c]
        j = hier[i][2]
        while j != -1:
            if cv2.contourArea(cs[j]) >= min_area:
                path.append(cs[j])
            j = hier[j][0]
        simple = [cv2.approxPolyDP(p, eps, True)[:, 0, :].astype(np.float64) for p in path]
        simple = [p for p in simple if len(p) >= 3]
        if simple and len(simple[0]) >= 3:
            out.append(simple)
    return out


def silhouette(mask: np.ndarray, sigma: float) -> np.ndarray:
    """The cut-out's outline with specks and jaggies smoothed away (as the bench's traced style does)."""
    k = max(3, (max(mask.shape) // 150) | 1)
    a = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))
    a = cv2.GaussianBlur(a.astype(np.float32), (0, 0), max(sigma, 0.5))
    a = (a > 0.5).astype(np.uint8)
    keep, _ = clean_mask(a * 255)
    return keep


def trace(rgb: np.ndarray, mask: np.ndarray, a: Approach) -> Trace:
    real = to_lab(rgb)
    lab = to_lab(prefilter(rgb, mask, a))
    area = int(mask.sum())
    min_area = max(6, int(SPECK * area))
    eps = a.smooth * WORK
    sil = silhouette(mask, a.blur)
    inside = mask > 0
    # the whole shoe quantised once, to find where the sole is
    labels_all = np.full(mask.shape, -1, np.int32)
    labels_all[inside], _ = quantise(lab[inside], real[inside], a.colors)
    sole = sole_region(lab, mask, labels_all) & sil
    upper = sil & (1 - sole)
    regions: list[Region] = []
    lmap = np.full(mask.shape, -1, np.int32)
    parts = []
    for part, region, k in (("upper", upper, a.colors), ("sole", sole, 2)):
        sel = (region > 0) & inside
        if sel.sum() < min_area:
            continue
        lab_sel, real_sel = lab[sel], real[sel]
        labels, cols = quantise(lab_sel, real_sel, k)
        offset = int(lmap.max()) + 1
        sub = np.full(mask.shape, -1, np.int32)
        sub[sel] = labels
        # pixels of the region outside the cut-out (the smoothed outline reaches a little further) take the nearest label
        missing = (region > 0) & ~sel
        if missing.any():
            _, idx = cv2.distanceTransformWithLabels((sub < 0).astype(np.uint8), cv2.DIST_L2, 5,
                                                     labelType=cv2.DIST_LABEL_PIXEL)
            src = np.zeros(int(idx.max()) + 1, np.int32)
            src[idx[sub >= 0]] = sub[sub >= 0]
            sub[missing] = src[idx[missing]]
        sub = smooth_labels(sub, region, len(cols), a.blur)
        sub = remove_specks(sub, region, min_area)
        ids = [i for i in range(len(cols)) if ((sub == i) & (region > 0)).any()]
        cols = [real[(sub == i) & sel].mean(axis=0) if ((sub == i) & sel).any() else cols[i] for i in ids]
        remap = np.full(int(sub.max()) + 2, -1, np.int32)
        for n, i in enumerate(ids):
            remap[i] = n
        sub = np.where(region > 0, remap[sub], -1)
        lmap[region > 0] = sub[region > 0] + offset
        parts.append((part, region, sub, cols))
    for part, region, sub, cols in parts:
        sizes = [int(((sub == i) & (region > 0)).sum()) for i in range(len(cols))]
        main = int(np.argmax(sizes))
        if part == "upper":
            regions.append(Region(lab_hex(cols[main]), cols[main], "silhouette", _contours(sil, eps, min_area)))
        else:
            regions.append(Region(lab_hex(cols[main]), cols[main], "sole", _contours(region, eps, min_area)))
        for i in sorted(range(len(cols)), key=lambda i: -sizes[i]):
            if i == main:
                continue
            paths = _contours((sub == i) & (region > 0), eps, min_area)
            if paths:
                regions.append(Region(lab_hex(cols[i]), cols[i], part, paths))
    if not regions or regions[0].part != "silhouette":   # an all-sole shoe cannot happen, but keep the outline first
        main = real[inside].mean(axis=0)
        regions.insert(0, Region(lab_hex(main), main, "silhouette", _contours(sil, eps, min_area)))
    return Trace(a, regions, mask.shape)


# ------------------------------------------------------------------ curves

def _beziers(pts: np.ndarray) -> list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
    """A smooth closed curve through a polygon (Catmull-Rom tangents, kept to each side's length), as cubic Bezier
    segments (p0, c1, c2, p1)."""
    n = len(pts)
    tangents = []
    for i in range(n):
        a, b = pts[i] - pts[(i - 1) % n], pts[(i + 1) % n] - pts[i]
        la, lb = np.hypot(*a), np.hypot(*b)
        turn = np.degrees(np.arccos(np.clip(np.dot(a, b) / max(la * lb, 1e-9), -1, 1)))
        d = pts[(i + 1) % n] - pts[(i - 1) % n]
        # a sharp turn (the heel's corner on the sole) stays a corner; elsewhere the curve runs through smoothly
        tangents.append(np.zeros(2) if turn > CORNER else d / max(np.hypot(*d), 1e-9))
    segs = []
    for i in range(n):
        p1, p2 = pts[i], pts[(i + 1) % n]
        k = np.hypot(*(p2 - p1)) / 3   # control points a third of the way along: the curve never overshoots
        segs.append((p1, p1 + tangents[i] * k, p2 - tangents[(i + 1) % n] * k, p2))
    return segs


def _sampled(pts: np.ndarray, steps: int = 6) -> np.ndarray:
    t = np.linspace(0, 1, steps, endpoint=False)[:, None]
    out = [((1 - t) ** 3) * a + 3 * ((1 - t) ** 2) * t * b + 3 * (1 - t) * t ** 2 * c + t ** 3 * d
           for a, b, c, d in _beziers(pts)]
    return np.concatenate(out)


def _d(path: list[np.ndarray], s: float, ox: float, oy: float) -> str:
    out = []
    for pts in path:
        q = pts * s + np.array([ox, oy])
        segs = _beziers(q)
        out.append(f"M{q[0][0]:.1f},{q[0][1]:.1f}" + "".join(
            f"C{b[0]:.1f},{b[1]:.1f} {c[0]:.1f},{c[1]:.1f} {d[0]:.1f},{d[1]:.1f}" for _, b, c, d in segs) + "Z")
    return "".join(out)


def raster(t: Trace) -> np.ndarray:
    """The trace painted at WORK scale: each pixel holds the index of the region on top there (-1 = not shoe)."""
    out = np.full(t.shape, -1, np.int32)
    sil = np.zeros(t.shape, np.uint8)
    for path in t.regions[0].paths:
        cv2.fillPoly(sil, [np.round(_sampled(p)).astype(np.int32) for p in path], 1)
    for idx, r in enumerate(t.regions):
        m = np.zeros(t.shape, np.uint8)
        for path in r.paths:
            cv2.fillPoly(m, [np.round(_sampled(p)).astype(np.int32) for p in path], 1)
        out[(m > 0) & (sil > 0)] = idx
    return out


def placement(t: Trace) -> tuple[float, float, float]:
    """Scale and offset that put the traced shoe where the templates draw a shoe: toe at x 40, on the ground at y 330."""
    pts = np.concatenate([p for path in t.regions[0].paths for p in path])
    x0, y0 = pts.min(axis=0)
    x1, y1 = pts.max(axis=0)
    s = min(SHOE_L / max(x1 - x0, 1), (SHOE_G - 40) / max(y1 - y0, 1))
    ox = SHOE_X0 + (SHOE_L - (x1 - x0) * s) / 2 - x0 * s
    oy = SHOE_G - y1 * s
    return s, ox, oy


def to_svg(t: Trace, uid: str = "t") -> str:
    """The trace in the app's style B, on the templates' card."""
    s, ox, oy = placement(t)
    base = t.regions[0].color
    inner = shade(base, 0.42) if luminance(base) < 0.3 else INK
    clip = f"k{uid}"
    sil = "".join(_d(p, s, ox, oy) for p in t.regions[0].paths)
    fills_ = "".join(f'<path d="{_d(p, s, ox, oy)}" fill="{r.color}" fill-rule="evenodd"/>' for r in t.regions for p in r.paths)
    lines = "".join(f'<path d="{_d(p, s, ox, oy)}" fill="none" stroke="{inner}" stroke-width="{INNER_W}" '
                    'stroke-linejoin="round" opacity=".95"/>' for r in t.regions[1:] for p in r.paths)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CARD_W} {CARD_H}" width="{CARD_W}" height="{CARD_H}">'
            f'<defs><clipPath id="{clip}"><path d="{sil}" fill-rule="evenodd"/></clipPath></defs>'
            f'<rect width="{CARD_W}" height="{CARD_H}" rx="18" fill="{CARD}"/>'
            f'<g clip-path="url(#{clip})">{fills_}{lines}</g>'
            f'<path d="{sil}" fill="none" stroke="{INK}" stroke-width="{OUTLINE_W}" stroke-linejoin="round"/></svg>')


# ------------------------------------------------------------------ scores

def mark_mask(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """High-contrast marks (logos, stripes, panels): pixels far in colour from the median of the shoe round them."""
    inside = mask > 0
    if not inside.any():
        return np.zeros(mask.shape, bool)
    fill = rgb.copy()
    fill[~inside] = np.median(rgb[inside], axis=0).astype(np.uint8)
    lab8 = cv2.cvtColor(fill, cv2.COLOR_RGB2Lab)
    ys = np.nonzero(inside.any(axis=1))[0]
    k = max(5, int(0.25 * (ys.max() - ys.min() + 1)) | 1)
    k = min(k, 255)
    med = np.stack([cv2.medianBlur(lab8[..., c], k) for c in range(3)], axis=-1)
    diff = lab8.astype(np.float32) - med.astype(np.float32)
    diff[..., 0] *= 100 / 255
    de = np.linalg.norm(diff, axis=-1)
    core = cv2.erode(mask.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    m = ((de > MARK_DE) & core).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, cc, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    keep = np.zeros(mask.shape, bool)
    limit = SPECK * inside.sum()
    for j in range(1, n):
        if stats[j, cv2.CC_STAT_AREA] >= limit:
            keep |= cc == j
    return keep


@dataclass
class Scores:
    iou: float               # traced silhouette against the cut-out
    delta_e: float           # mean colour error of the regions against the photo (area-weighted CIE76)
    colors: int
    paths: int
    marks: float | None      # share of the photo's high-contrast marks the trace keeps; None = the photo has none
    score: float             # the combined score, 0..1


def combined(iou: float, de: float, paths: int, marks: float | None) -> float:
    clamp = lambda v: float(min(1.0, max(0.0, v)))   # noqa: E731
    parts = [(0.4, clamp((iou - 0.8) / 0.2)), (0.25, clamp(1 - de / 25)), (0.15, clamp(1 - (paths - 3) / 40))]
    if marks is not None:
        parts.append((0.2, marks))
    return sum(w * v for w, v in parts) / sum(w for w, _ in parts)


def score(t: Trace, rgb: np.ndarray, mask: np.ndarray, photo_marks: np.ndarray) -> Scores:
    r = raster(t)
    traced, cut = r >= 0, mask > 0
    iou = float((traced & cut).sum() / max((traced | cut).sum(), 1))
    real = to_lab(rgb)
    total, err = 0, 0.0
    painted = np.zeros(rgb.shape, np.uint8)
    for idx, region in enumerate(t.regions):
        pix = (r == idx) & cut
        painted[r == idx] = np.asarray([int(region.color[i:i + 2], 16) for i in (1, 3, 5)], np.uint8)
        if pix.any():
            n = int(pix.sum())
            err += n * delta_e(real[pix].mean(axis=0), region.lab)
            total += n
    marks = None
    if photo_marks.sum() >= SPECK * cut.sum():
        kept = cv2.dilate(mark_mask(painted, mask).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        marks = float((photo_marks & kept).sum() / photo_marks.sum())
    de = err / max(total, 1)
    return Scores(iou, de, t.colors, t.paths, marks, combined(iou, de, t.paths, marks))


# ------------------------------------------------------------------ the gate

def photo_signals(soft: np.ndarray) -> tuple[dict[str, float], np.ndarray]:
    """Measured signals from the photo and its cut-out, before orientation; and the cleaned mask."""
    mask, second = clean_mask(soft)
    sig: dict[str, float] = {"found": float(mask.sum() > 0.002 * mask.size)}
    if not sig["found"]:
        return sig, mask
    ys, xs = np.nonzero(mask)
    sig["size_px"] = float(max(xs.max() - xs.min() + 1, ys.max() - ys.min() + 1))
    sig["second_piece"] = second
    cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(cs, key=cv2.contourArea)
    sig["solidity"] = float(cv2.contourArea(c) / max(cv2.contourArea(cv2.convexHull(c)), 1))
    h, w = mask.shape
    bx, by = max(2, int(0.035 * w)), max(2, int(0.035 * h))
    pts = c[:, 0, :]
    near = (pts[:, 0] < bx) | (pts[:, 0] >= w - bx) | (pts[:, 1] < by) | (pts[:, 1] >= h - by)
    sig["edge_touch"] = float(near.mean())
    return sig, mask


def work_signals(o: Oriented) -> dict[str, float]:
    """Signals measured on the turned shoe at WORK scale."""
    lab = to_lab(o.rgb)
    inside = o.mask > 0
    k = np.ones((7, 7), np.uint8)
    # how far the shoe stands out from what is just outside it, measured all along its outline (the median);
    # a few px either side of the edge are skipped, so that a soft edge does not count as low contrast
    near, far = np.ones((7, 7), np.uint8), np.ones((21, 21), np.uint8)
    band_in = ((cv2.erode(o.mask, near) > 0) & ~(cv2.erode(o.mask, far) > 0)).astype(np.float32)
    band_out = ((cv2.dilate(o.mask, far) > 0) & ~(cv2.dilate(o.mask, near) > 0)).astype(np.float32)

    def local(band):
        w = cv2.GaussianBlur(band, (0, 0), 6)
        return np.stack([cv2.GaussianBlur(lab[..., c] * band, (0, 0), 6) for c in range(3)], -1) / np.maximum(w, 1e-6)[..., None]

    edge = (cv2.dilate(o.mask, np.ones((3, 3), np.uint8)) > 0) & ~(cv2.erode(o.mask, np.ones((3, 3), np.uint8)) > 0)
    edge &= (cv2.GaussianBlur(band_out, (0, 0), 6) > 0.02) & (cv2.GaussianBlur(band_in, (0, 0), 6) > 0.02)
    contrast = float(np.median(np.linalg.norm(local(band_in)[edge] - local(band_out)[edge], axis=-1))) if edge.any() else 0.0
    L = lab[..., 0]
    gx = cv2.Sobel(L, cv2.CV_32F, 1, 0, ksize=3) / 8
    gy = cv2.Sobel(L, cv2.CV_32F, 0, 1, ksize=3) / 8
    grad = np.hypot(gx, gy)
    zone = cv2.dilate(o.mask, k) > 0
    spread = max(float(np.percentile(L[zone], 98) - np.percentile(L[zone], 2)), 10.0)
    sharp = float(np.percentile(grad[zone], 99.5)) / spread
    clipped = float(((L[inside] > 98) | (L[inside] < 2)).mean())
    return {"contrast_de": contrast, "sharpness": sharp, "clipped": clipped, "aspect": o.aspect,
            "ground": o.ground, "toe_heel": o.toe_heel}


@dataclass
class Gate:
    ok: bool
    reasons: list[str]
    signals: dict[str, float]


def gate(signals: dict[str, float]) -> Gate:
    reasons = []
    for name, (limit, way, why) in GATE.items():
        v = signals.get(name)
        if v is None:
            continue
        if (way == "below" and v < limit) or (way == "above" and v > limit):
            reasons.append(f"{why} ({name} {v:.3g}, limit {limit:g})")
    return Gate(not reasons, reasons, signals)


# ------------------------------------------------------------------ one photo

@dataclass
class Variant:
    approach: Approach
    trace: Trace
    scores: Scores
    svg: str


@dataclass
class Result:
    photo: Image.Image
    cutout: Image.Image | None
    cutout_by: str
    oriented: Oriented | None
    variants: list[Variant]
    gate: Gate
    template_svg: str | None
    seconds: float
    best: str | None = None
    mask: np.ndarray | None = field(default=None, repr=False)   # the cleaned cut-out mask, the photo's size


def template_svg(answer, color_hex: str, aspect: float, uid: str) -> str | None:
    """Today's template drawing for the shoe: from its tagger answer when there is one, else a sneaker of its height."""
    from closet.drawing import item
    if answer is not None:
        svg = item.svg_from_answer(answer, color_hex, uid=uid)
        if svg:
            return svg
    return item.svg_from_fields("sneakers", color_hex, silhouette={"shoe_height": "high" if aspect < 1.8 else "low"}, uid=uid)


def trace_photo(img: Image.Image, cutout: str = "auto", model: str = "isnet-general-use",
                models_dir: Path = ROOT / "models", answer=None, uid: str = "s",
                approaches: tuple[Approach, ...] = APPROACHES) -> Result:
    t0 = time.time()
    rgb = np.asarray(img.convert("RGB"))
    soft, by = None, "grabcut"
    if cutout in ("auto", "model"):
        soft = model_mask(img, model, models_dir)
        if soft is None and cutout == "model":
            raise SystemExit(f"the cut-out model is not in {models_dir}: run the hard cases once, or use --cutout grabcut")
        by = model if soft is not None else by
    if soft is None:
        soft = grabcut_mask(img)
    signals, mask = photo_signals(soft)
    if not signals["found"]:
        g = gate(signals)
        return Result(img, None, by, None, [], g, None, time.time() - t0, mask=mask)
    cut, _ = C.make_cutout(img, Image.fromarray(mask * 255))
    o = orient(rgb, mask)
    signals.update(work_signals(o))
    photo_marks = mark_mask(o.rgb, o.mask)
    variants = []
    for n, a in enumerate(approaches):
        t = trace(o.rgb, o.mask, a)
        variants.append(Variant(a, t, score(t, o.rgb, o.mask, photo_marks), to_svg(t, f"{uid}v{n}")))
    best = max(variants, key=lambda v: v.scores.score)
    signals["trace_iou"] = max(v.scores.iou for v in variants)
    tmpl = template_svg(answer, best.trace.regions[0].color, o.aspect, f"{uid}t")
    return Result(img, cut, by, o, variants, gate(signals), tmpl, time.time() - t0, best.approach.name, mask)


# ------------------------------------------------------------------ the sheet

def _place(svg: str, x: float, y: float, w: float, h: float) -> str:
    """A drawing's own <svg> placed in a cell of the sheet."""
    head = re.match(r"<svg\b[^>]*>", svg).group(0)
    new = re.sub(r'\s(width|height|x|y)="[^"]*"', "", head)[:-1] + f' x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}">'
    return new + svg[len(head):]


def _prefix_ids(svg: str, p: str) -> str:
    """The same drawing twice on one sheet: its ids made different."""
    return svg.replace(' id="', f' id="{p}').replace("url(#", f"url(#{p}").replace('href="#', f'href="#{p}')


def _image_cell(img: Image.Image, x: float, y: float, w: float, h: float, checker: bool, fmt: str) -> str:
    uri = fills.data_uri(img, 640, fmt, 80)
    bg = 'fill="url(#chk)"' if checker else f'fill="{CARD}"'
    return (f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" rx="{w * 0.045:.0f}" {bg}/>'
            f'<image href="{uri}" x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" preserveAspectRatio="xMidYMid meet"/>')


def _text(x: float, y: float, s: str, size: int = 15, weight: str = "normal", color: str = "#26231f") -> str:
    return (f'<text x="{x:.0f}" y="{y:.0f}" font-family="system-ui,sans-serif" font-size="{size}" font-weight="{weight}" '
            f'fill="{color}">{html.escape(s, quote=False)}</text>')


def sheet(r: Result, number: int) -> str:
    """The comparison sheet: photo | cut-out | each trace | today's template, at item size and at tile size."""
    m, gap = 24, 16
    cw, ch = ITEM_PX, ITEM_PX * CARD_H // CARD_W
    tw, th = TILE_PX, TILE_PX * CARD_H // CARD_W
    cols: list[tuple[str, list[str], str]] = [("Photo", [], "photo"), ("Cut-out", [f"by {r.cutout_by}"], "cut")]
    for v in r.variants:
        sc = v.scores
        lines = [f"IoU {sc.iou:.3f} · ΔE {sc.delta_e:.1f}", f"{sc.colors} colours · {sc.paths} paths",
                 ("marks " + ("none in photo" if sc.marks is None else f"{sc.marks:.2f}")) + f" · score {sc.score:.3f}"]
        cols.append(((" ★ " if v.approach.name == r.best else "") + v.approach.name, lines, v.approach.name))
    cols.append(("Today's template", ["drawn from tags" if r.template_svg else "no drawing"], "template"))
    width = 2 * m + len(cols) * (cw + gap) - gap
    head_h = 70 + 20 * len(r.gate.reasons)
    y_item = m + head_h
    y_cap = y_item + ch + 22
    y_tile = y_cap + 3 * 19 + 26
    height = y_tile + th + m
    verdict = "passes the quality gate" if r.gate.ok else "fails the quality gate"
    o = r.oriented
    turned = f"turned {o.angle:+.1f}°" + (", mirrored (toe to the left)" if o.flipped else "") if o else "not traced"
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">',
           '<defs><pattern id="chk" width="16" height="16" patternUnits="userSpaceOnUse">'
           '<rect width="16" height="16" fill="#f4f1ea"/><rect width="8" height="8" fill="#d9d5cc"/>'
           '<rect x="8" y="8" width="8" height="8" fill="#d9d5cc"/></pattern></defs>',
           f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
           _text(m, m + 24, f"Shoe {number}: {verdict}", 24, "600", "#2e7d4f" if r.gate.ok else "#b3372f"),
           _text(m, m + 50, f"{turned} · {r.seconds:.1f} s · top row at item size ({ITEM_PX} px), "
                            f"bottom row at grid-tile size ({TILE_PX} px)", 15, color="#6d675d")]
    for i, why in enumerate(r.gate.reasons):
        out.append(_text(m, m + 72 + 20 * i, "• " + why, 15, color="#b3372f"))
    for i, (title, lines, key) in enumerate(cols):
        x = m + i * (cw + gap)
        for y, w, h in ((y_item, cw, ch), (y_tile, tw, th)):
            if key == "photo":
                out.append(_image_cell(r.photo, x, y, w, h, False, "JPEG"))
            elif key == "cut":
                if r.cutout is not None:
                    out.append(_image_cell(r.cutout, x, y, w, h, True, "PNG"))
            elif key == "template":
                if r.template_svg:
                    out.append(_place(_prefix_ids(r.template_svg, "i" if h == ch else "s"), x, y, w, h))
            else:
                v = next(v for v in r.variants if v.approach.name == key)
                out.append(_place(_prefix_ids(v.svg, "i" if h == ch else "s"), x, y, w, h))
        out.append(_text(x, y_cap, title, 16, "600"))
        for j, line in enumerate(lines):
            out.append(_text(x, y_cap + 20 + 19 * j, line, 14, color="#6d675d"))
    out.append("</svg>")
    return "".join(out)


def to_png(svg_path: Path, png_path: Path) -> bool:
    """The sheet as a picture, through a Chrome or Chromium found on this computer (as tools/make_figure_sheet.py)."""
    chrome = next((shutil.which(c) for c in ("google-chrome", "chromium", "chromium-browser", "chrome") if shutil.which(c)), None)
    if not chrome:
        return False
    svg = svg_path.read_text(encoding="utf-8")
    w, h = (int(v) for v in re.search(r'width="(\d+)" height="(\d+)"', svg).groups())
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "sheet.html"
        page.write_text(f'<html><body style="margin:0">{svg}</body></html>', encoding="utf-8")
        subprocess.run([chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                        f"--window-size={w},{h}", f"--screenshot={png_path.resolve()}", page.as_uri()],
                       check=True, capture_output=True, timeout=120)
    return png_path.exists()


# ------------------------------------------------------------------ the command

def summary(results: list[Result]) -> dict:
    """Mean scores per approach over the photos that pass the gate (all photos, when none does), and the pick."""
    usable = [r for r in results if r.gate.ok and r.variants] or [r for r in results if r.variants]
    table = {}
    for a in APPROACHES:
        vs = [v.scores for r in usable for v in r.variants if v.approach.name == a.name]
        if not vs:
            continue
        marks = [s.marks for s in vs if s.marks is not None]
        table[a.name] = {"label": a.label, "score": float(np.mean([s.score for s in vs])),
                         "iou": float(np.mean([s.iou for s in vs])), "delta_e": float(np.mean([s.delta_e for s in vs])),
                         "colors": float(np.mean([s.colors for s in vs])), "paths": float(np.mean([s.paths for s in vs])),
                         "marks": float(np.mean(marks)) if marks else None,
                         "best_on": sum(1 for r in usable if r.best == a.name)}
    pick = max(table, key=lambda k: table[k]["score"]) if table else None
    return {"photos": len(results), "passed": sum(1 for r in results if r.gate.ok), "scored_on": len(usable),
            "approaches": table, "recommended": pick}


def _index(results: list[Result], files: list[str], summ: dict, note: str) -> str:
    css = """
    :root{color-scheme:light dark;--bg:#fbfaf7;--fg:#22201c;--mut:#6d675d;--card:#fff;--line:#e3ded4}
    @media(prefers-color-scheme:dark){:root{--bg:#191816;--fg:#ece8df;--mut:#a39c8e;--card:#23211e;--line:#3a3732}}
    body{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,sans-serif}
    h1{font-size:22px;margin:4px 0 6px}h2{font-size:17px;margin:0 0 8px}p{margin:6px 0;max-width:80ch}
    .mut{color:var(--mut);font-size:13px}.ok{color:#2e7d4f}.bad{color:#b3372f}
    section{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;margin:16px 0;overflow-x:auto}
    table{border-collapse:collapse;font-size:14px}td,th{padding:3px 10px;border-bottom:1px solid var(--line);text-align:left}
    img.sheet{width:100%;min-width:900px;height:auto;display:block;border-radius:8px;background:#fff}
    """
    rec = summ["recommended"]
    p = [f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>Shoe tracing bench</title><style>{css}</style></head><body><h1>Shoe tracing bench</h1>",
         f"<p class='mut'>{html.escape(note)}</p>",
         "<section><h2>Summary</h2>",
         f"<p>{summ['photos']} photos; {summ['passed']} pass the quality gate. Mean scores over "
         f"{summ['scored_on']} photos{'' if summ['passed'] else ' (none passed, so all are shown)'}. "
         f"Recommended approach: <b>{html.escape(rec or 'none')}</b>.</p>",
         "<table><tr><th>Approach</th><th>Score</th><th>IoU</th><th>ΔE</th><th>Colours</th><th>Paths</th><th>Marks kept</th>"
         "<th>Best on</th></tr>"]
    for name, row in summ["approaches"].items():
        marks = "–" if row["marks"] is None else f"{row['marks']:.2f}"
        p.append(f"<tr><td>{'★ ' if name == rec else ''}{html.escape(name)} <span class='mut'>{html.escape(row['label'])}</span></td>"
                 f"<td>{row['score']:.3f}</td><td>{row['iou']:.3f}</td><td>{row['delta_e']:.1f}</td><td>{row['colors']:.1f}</td>"
                 f"<td>{row['paths']:.1f}</td><td>{marks}</td><td>{row['best_on']}</td></tr>")
    p.append("</table><p class='mut'>Score = 0.4 × silhouette IoU (0.8 → 0, 1 → 1) + 0.25 × colour (ΔE 25 → 0, 0 → 1) "
             "+ 0.15 × cleanliness (3 paths → 1, 43 → 0) + 0.2 × marks kept; without marks in the photo the other weights "
             "are scaled up.</p></section>")
    p.append("<section><h2>Quality gate</h2><table><tr><th>Shoe</th><th>Verdict</th><th>Why</th></tr>")
    for n, r in enumerate(results, 1):
        why = "<br>".join(html.escape(x) for x in r.gate.reasons) or "–"
        p.append(f"<tr><td>{n}</td><td class='{'ok' if r.gate.ok else 'bad'}'>{'traceable' if r.gate.ok else 'too poor'}</td>"
                 f"<td>{why}</td></tr>")
    p.append("</table><p class='mut'>Signals and limits: " + html.escape("; ".join(
        f"{k} {'≥' if way == 'below' else '≤'} {lim:g}" for k, (lim, way, _) in GATE.items())) + "</p></section>")
    for n, (r, f) in enumerate(zip(results, files, strict=True), 1):
        p.append(f"<section><h2>Shoe {n} <span class='{'ok' if r.gate.ok else 'bad'}'>"
                 f"{'traceable' if r.gate.ok else 'too poor to trace'}</span></h2>")
        p.append(f"<a href='{html.escape(f)}'><img class='sheet' src='{html.escape(f)}' alt='comparison sheet for shoe {n}'></a>")
        sig = " · ".join(f"{k} {v:.3g}" for k, v in r.gate.signals.items())
        p.append(f"<p class='mut'>{html.escape(sig)}</p></section>")
    p.append("</body></html>")
    return "".join(p)


def _result_json(r: Result) -> dict:
    o = r.oriented
    return {"gate": {"ok": r.gate.ok, "reasons": r.gate.reasons, "signals": r.gate.signals},
            "cutout_by": r.cutout_by, "seconds": round(r.seconds, 2), "best": r.best,
            "turned": None if o is None else {"angle": round(o.angle, 2), "flipped": o.flipped},
            "variants": {v.approach.name: {"iou": v.scores.iou, "delta_e": v.scores.delta_e, "colors": v.scores.colors,
                                           "paths": v.scores.paths, "marks": v.scores.marks, "score": v.scores.score,
                                           "palette": [rg.color for rg in v.trace.regions]} for v in r.variants}}


def photos_in(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in PHOTO_TYPES and p.is_file())


def run(photos: Path, out: Path, cutout: str = "auto", model: str = "isnet-general-use",
        models_dir: Path = ROOT / "models", png: bool = True, quiet: bool = False) -> Path:
    try:   # phones' HEIC photos, when pillow-heif is installed (the app has it; the bench does not need it)
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except ImportError:
        pass
    paths = photos_in(photos)
    if not paths:
        raise SystemExit(f"no photos in {photos}")
    out.mkdir(parents=True, exist_ok=True)
    results, files = [], []
    for n, path in enumerate(paths, 1):
        side = path.with_suffix(".json")
        answer = json.loads(side.read_text(encoding="utf-8")) if side.exists() else None
        r = trace_photo(C.load_photo(path), cutout, model, models_dir, answer, uid=f"s{n}")
        results.append(r)
        svg_path = out / f"shoe-{n:02d}.sheet.svg"
        svg_path.write_text(sheet(r, n), encoding="utf-8")
        png_path = svg_path.with_suffix(".png")
        made = png and to_png(svg_path, png_path)
        files.append(png_path.name if made else svg_path.name)
        if not quiet:
            print(f"shoe {n:2d}: {'traceable ' if r.gate.ok else 'too poor  '} best {r.best or '-':20s} "
                  f"{r.seconds:5.1f}s  " + ("; ".join(r.gate.reasons) or ""))
    summ = summary(results)
    (out / "results.json").write_text(json.dumps({"summary": summ, "shoes": [_result_json(r) for r in results]},
                                                 indent=2, default=float), encoding="utf-8")
    note = (f"Photos from {photos.name}/, listed by number in name order. Cut-outs by "
            f"{', '.join(sorted({r.cutout_by for r in results}))}.")
    (out / "index.html").write_text(_index(results, files, summ, note), encoding="utf-8")
    if not quiet:
        print(f"recommended approach: {summ['recommended']}")
    return out / "index.html"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--photos", type=Path, default=ROOT / "private" / "shoes")
    ap.add_argument("--out", type=Path, default=ROOT / "out" / "trace_shoes")
    ap.add_argument("--cutout", choices=("auto", "model", "grabcut"), default="auto",
                    help="auto: the app's model when its file is in --models-dir, else GrabCut")
    ap.add_argument("--model", default="isnet-general-use", choices=list(C.MODELS))
    ap.add_argument("--models-dir", type=Path, default=ROOT / "models")
    ap.add_argument("--no-png", action="store_true", help="write the sheets as SVG only")
    a = ap.parse_args()
    print("report:", run(a.photos, a.out, a.cutout, a.model, a.models_dir, png=not a.no_png))


if __name__ == "__main__":
    main()
