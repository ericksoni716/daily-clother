"""Image quilting (Efros & Freeman 2001) from a garment's own cloth: a fill as big as the garment, built from
many squares taken from all over its body, each chosen to match its neighbours where they overlap and joined
along the path where they match best. No square is copied in a grid, so nothing repeats in rows, and no
single patch is stretched over the whole garment."""
import sys
import numpy as np
from PIL import Image

sys.path.insert(0, ".")
import repeat2d as R  # noqa: E402


def candidates(rgb, m, B, step):
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
    rgb = np.asarray(cut.convert("RGB")).astype(np.float32)
    m = R.body_mask(np.asarray(cut)[..., 3], 0.03)
    xs = np.where(m.any(0))[0]
    gw = xs.max() - xs.min()
    mid, gap = (xs.min() + xs.max()) // 2, int(center_gap * gw)
    m[:, mid - gap: mid + gap] = False          # the button strip
    B = max(16, int(gw * block_frac))
    while True:   # as big as the cloth allows: step down until enough places on the body fit a square
        pos_try = candidates(rgb, m, B, max(1, B // 10)) if True else None
        if len(pos_try[1]) >= 60 or B <= 16:
            blocks, pos = pos_try
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
