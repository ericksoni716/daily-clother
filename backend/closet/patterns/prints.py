"""Florals and other irregular prints: image quilting (Efros & Freeman 2001) from a garment's own cloth.

A fill as big as the garment is built from many squares taken from all over its body, each chosen to match its
neighbours where they overlap and joined along the path where they match best. No square is copied in a grid,
so nothing repeats in rows, and no single patch is stretched over the whole garment. (Tried and rejected for
plaids: it breaks their lines.)
"""
import cv2
import numpy as np
from PIL import Image

from .common import body_mask


def candidates(rgb, m, B, step):
    """Every B x B square lying wholly on the garment, every `step` px. Returns (blocks, their (y, x))."""
    H, W = m.shape
    pos = [(y, x) for y in range(0, H - B, step) for x in range(0, W - B, step) if m[y:y + B, x:x + B].all()]
    if not pos:
        return np.zeros((0, B, B, 3), np.float32), pos
    blocks = np.stack([rgb[y:y + B, x:x + B] for y, x in pos]).astype(np.float32)
    return blocks, pos


def min_cut(err):
    """Cheapest top-to-bottom path through an overlap error map (h x w); True where the new block is used."""
    h, w = err.shape
    cost = err.copy()
    for i in range(1, h):
        left = np.r_[np.inf, cost[i - 1, :-1]]
        right = np.r_[cost[i - 1, 1:], np.inf]
        cost[i] += np.minimum(np.minimum(left, cost[i - 1]), right)
    mask = np.zeros((h, w), bool)
    j = int(np.argmin(cost[-1]))
    for i in range(h - 1, -1, -1):
        mask[i, j:] = True
        if i:
            lo, hi = max(0, j - 1), min(w, j + 2)
            j = lo + int(np.argmin(cost[i - 1, lo:hi]))
    return mask


def quilt(cut: Image.Image, out_w, out_h, block_frac=0.16, overlap=1 / 5, tol=0.1, center_gap=0.06, seed=0):
    """Quilt an out_w x out_h fill from squares of the cutout's body (the button strip left out). The squares
    are as big as the cloth allows: block_frac of the garment's width, stepped down until at least 60 places
    on the body fit one. Returns (the fill as an RGB image, dict(block, overlap, candidates, distinct, placed))."""
    rgb = np.asarray(cut.convert("RGB")).astype(np.float32)
    m = body_mask(np.asarray(cut)[..., 3], 0.03)
    xs = np.where(m.any(0))[0]
    gw = xs.max() - xs.min()
    mid, gap = (xs.min() + xs.max()) // 2, int(center_gap * gw)
    m[:, mid - gap: mid + gap] = False          # the button strip
    B = max(16, int(gw * block_frac))
    while True:   # as big as the cloth allows: step down until enough places on the body fit a square
        blocks, pos = candidates(rgb, m, B, max(1, B // 10))
        if len(pos) >= 60 or B <= 16:
            break
        B = max(16, int(B * 0.85))
    ov = max(4, int(B * overlap))
    rng = np.random.default_rng(seed)
    used = np.zeros(len(blocks))
    step = B - ov
    ny, nx = int(np.ceil((out_h - ov) / step)), int(np.ceil((out_w - ov) / step))
    out = np.zeros((ny * step + ov, nx * step + ov, 3), np.float32)
    for by in range(ny):
        for bx in range(nx):
            y, x = by * step, bx * step
            err = np.zeros(len(blocks))
            if bx:
                err += ((blocks[:, :, :ov] - out[None, y:y + B, x:x + ov]) ** 2).sum((1, 2, 3))
            if by:
                err += ((blocks[:, :ov, :] - out[None, y:y + ov, x:x + B]) ** 2).sum((1, 2, 3))
            err = err * (1 + 0.5 * used)        # spread the picks over the whole garment
            if not (bx or by):
                k = int(rng.integers(len(blocks)))
            else:
                ok = np.where(err <= err.min() * (1 + tol) + 1e-6)[0]
                k = int(rng.choice(ok))
            used[k] += 1
            blk = blocks[k].copy()
            keep = np.ones((B, B), bool)        # True: the new block shows
            if bx:
                e = ((blk[:, :ov] - out[y:y + B, x:x + ov]) ** 2).sum(-1)
                keep[:, :ov] &= min_cut(e)
            if by:
                e = ((blk[:ov, :] - out[y:y + ov, x:x + B]) ** 2).sum(-1)
                keep[:ov, :] &= min_cut(e.T).T
            region = out[y:y + B, x:x + B]
            region[keep] = blk[keep]
    used_spots = int((used > 0).sum())
    return Image.fromarray(out[:out_h, :out_w].clip(0, 255).astype(np.uint8)), dict(block=B, overlap=ov,
                                                                                   candidates=len(blocks),
                                                                                   distinct=used_spots,
                                                                                   placed=int(used.sum()))


def even_light(cut: Image.Image, sigma_frac=0.08) -> Image.Image:
    """Divide out slow brightness changes inside the garment (folds, shadows, uneven light), keeping colour."""
    rgb = np.asarray(cut.convert("RGB")).astype(np.float32)
    a = np.asarray(cut)[..., 3]
    m = (a > 200).astype(np.float32)
    lab = cv2.cvtColor(rgb.astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
    L = lab[..., 0]
    s = max(cut.size) * sigma_frac
    local = cv2.GaussianBlur(L * m, (0, 0), s) / np.maximum(cv2.GaussianBlur(m, (0, 0), s), 1e-3)
    lab[..., 0] = np.clip(L - local + np.median(L[m > 0]), 0, 255)
    return Image.fromarray(np.dstack([cv2.cvtColor(lab.astype(np.uint8), cv2.COLOR_LAB2RGB), a]), "RGBA")


def lean(cut: Image.Image) -> float:
    """How far the garment leans from upright, in degrees, from its centre line between shoulders and hem."""
    a = np.asarray(cut)[..., 3] > 200
    ys = np.where(a.any(1))[0]
    top, bot = ys.min() + int(0.3 * (ys.max() - ys.min())), ys.max() - int(0.1 * (ys.max() - ys.min()))
    rows = np.arange(top, bot, 2)
    mids = [np.where(a[y])[0][[0, -1]].mean() for y in rows]
    return float(np.degrees(np.arctan(np.polyfit(rows, mids, 1)[0])))


def quilt_garment(cut: Image.Image, block_frac=0.3, overlap=1 / 4):
    """The floral recipe that worked on the owner's shirts: turn the garment upright, even out the light, then
    quilt a fill a little bigger than the garment (1.1 times) from big squares (as big as the cloth allows).
    Returns what `quilt` returns."""
    up = cut.rotate(-lean(cut), Image.BICUBIC, expand=True)
    a = np.asarray(up)[..., 3]
    xs, ys = np.where((a > 200).any(0))[0], np.where((a > 200).any(1))[0]
    return quilt(even_light(up), int((xs.max() - xs.min()) * 1.1), int((ys.max() - ys.min()) * 1.1),
                 block_frac=block_frac, overlap=overlap)
