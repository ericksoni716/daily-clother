"""Flatten a crumpled plaid and recover one straight, sharp repeat of it.

The photographed cloth is a perfect repeat (P x Q pixels) seen through a smooth distortion. Measure, area by
area, how far the plaid is shifted against a reference repeat (normalised matching, to a tenth of a pixel);
join those shifts into one smooth map (all at once, least squares); put every garment pixel back where it
belongs in the repeat; take the median of the pixels landing on each spot. Repeat with the sharper reference.
"""
import warnings

import cv2
import numpy as np

from .common import best_tile, garment_mask, quiet, signal, to_lab


def subpix(r, i, j):
    """Parabolic refinement of a peak at (i, j) in a cyclic score map."""
    H, W = r.shape

    def f(a, b, c):
        d = a - 2 * b + c
        return 0.0 if d >= 0 else 0.5 * (a - c) / d
    return i + f(r[(i - 1) % H, j], r[i, j], r[(i + 1) % H, j]), j + f(r[i, (j - 1) % W], r[i, j], r[i, (j + 1) % W])


def local_offsets_match(sig, m, ref, P, Q, stride_frac=0.34, cover=0.9, size=1.0, margin=0.1):
    """Offsets by normalised matching of one repeat-sized piece against the reference tiled around it.
    Returns (offsets (ox, oy) modulo (P, Q) per area, NaN where not measured; how sure each match is; the
    areas' centres as (rows, columns))."""
    H, W = m.shape
    th, tw = int(Q * size), int(P * size)
    big = np.tile(ref, (int(np.ceil((th + Q) / Q)) + 1, int(np.ceil((tw + P) / P)) + 1)).astype(np.float32)
    big = big[:th + Q, :tw + P]
    sy, sx = max(2, int(Q * stride_frac)), max(2, int(P * stride_frac))
    ys = list(range(0, H - th, sy))
    xs = list(range(0, W - tw, sx))
    off = np.full((len(ys), len(xs), 2), np.nan, np.float32)
    conf = np.zeros((len(ys), len(xs)), np.float32)
    for a, y0 in enumerate(ys):
        for b, x0 in enumerate(xs):
            wm = m[y0:y0 + th, x0:x0 + tw]
            if wm.mean() < cover:
                continue
            t = sig[y0:y0 + th, x0:x0 + tw]
            t = np.where(wm, t, t[wm].mean()).astype(np.float32)
            r = cv2.matchTemplate(big, t, cv2.TM_CCOEFF_NORMED)[:Q, :P]   # every cyclic shift once
            i, j = np.unravel_index(np.argmax(r), r.shape)
            # a near-tie with a match elsewhere (a soft or nearly symmetric plaid) says nothing: leave the area out
            far = r.copy()
            yy, xx = np.ogrid[:Q, :P]
            dy = np.minimum(np.abs(yy - i), Q - np.abs(yy - i))
            dx = np.minimum(np.abs(xx - j), P - np.abs(xx - j))
            far[(dy <= max(2, Q // 10)) & (dx <= max(2, P // 10))] = -1
            if r[i, j] - far.max() < margin:
                continue
            fi, fj = subpix(r, i, j)
            # t(x) = ref(x + (fj, fi)) : the repeat's origin is at x0 - fj
            off[a, b] = ((x0 - fj) % P, (y0 - fi) % Q)
            conf[a, b] = r[i, j]
    return off, conf, (np.array(ys) + th / 2, np.array(xs) + tw / 2)


def _poly_basis(n, mcols, deg):
    gi, gj = np.mgrid[0:n, 0:mcols].astype(np.float64)
    gi, gj = gi / max(1, n - 1) - 0.5, gj / max(1, mcols - 1) - 0.5
    return np.stack([(gi ** a * gj ** b).ravel() for a in range(deg + 1) for b in range(deg + 1 - a)], 1)


def unwrap_ls(off, conf, P, Q, min_conf=0.5, min_patch=10, deg=2):
    """Join all areas at once: the field that best agrees, in the least-squares sense, with every
    neighbour-to-neighbour difference (each taken as the shortest way round the repeat, weighted by how sure
    both matches are). One bad pair cannot throw a whole region off by a repeat, as growing one area at a
    time can. Each area then keeps its own precise measurement, moved by the whole number of repeats the
    solution says. Separate patches are solved on their own and joined to the largest by a smooth surface,
    only if they sit on it (a shirt's two fronts are separate cloth)."""
    n, mcols = conf.shape
    good = (conf >= min_conf) & ~np.isnan(off[..., 0])
    idx = -np.ones((n, mcols), int)
    cells = list(zip(*np.where(good), strict=True))
    for k, (i, j) in enumerate(cells):
        idx[i, j] = k
    out = np.full_like(off, np.nan)
    if len(cells) < min_patch:
        return out
    # connected patches
    comp = -np.ones(len(cells), int)
    c = 0
    for s in range(len(cells)):
        if comp[s] >= 0:
            continue
        stack = [s]
        comp[s] = c
        while stack:
            k = stack.pop()
            i, j = cells[k]
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                a, b = i + di, j + dj
                if 0 <= a < n and 0 <= b < mcols and idx[a, b] >= 0 and comp[idx[a, b]] < 0:
                    comp[idx[a, b]] = c
                    stack.append(idx[a, b])
        c += 1
    sizes = np.bincount(comp)
    order = np.argsort(-sizes)
    A_s = _poly_basis(n, mcols, deg)
    for rank, cid in enumerate(order):
        if sizes[cid] < min_patch:
            break
        members = [k for k in range(len(cells)) if comp[k] == cid]
        local = {k: t for t, k in enumerate(members)}
        rows, rhs_x, rhs_y, wts = [], [], [], []
        for k in members:
            i, j = cells[k]
            for di, dj in ((1, 0), (0, 1)):
                a, b = i + di, j + dj
                if a < n and b < mcols and idx[a, b] >= 0 and idx[a, b] in local:
                    k2 = idx[a, b]
                    w = min(conf[i, j], conf[a, b])
                    dx = (off[a, b, 0] - off[i, j, 0] + P / 2) % P - P / 2
                    dy = (off[a, b, 1] - off[i, j, 1] + Q / 2) % Q - Q / 2
                    rows.append((local[k], local[k2]))
                    rhs_x.append(dx)
                    rhs_y.append(dy)
                    wts.append(w)
        m = len(members)
        M = np.zeros((len(rows) + 1, m))
        for r, (p, q) in enumerate(rows):
            M[r, p], M[r, q] = -wts[r], wts[r]
        M[-1, 0] = 1.0                                   # fix the first area
        k0 = members[0]
        # the least-squares solution through the normal equations: the same answer as np.linalg.lstsq (the patch
        # is connected and its first area fixed, so there is exactly one), many times faster on a big garment
        MtM = M.T @ M
        sols = []
        for rhs, c_ in ((rhs_x, 0), (rhs_y, 1)):
            bvec = np.r_[np.array(rhs) * np.array(wts), off[cells[k0]][c_]]
            sols.append(np.linalg.solve(MtM, M.T @ bvec))
        vals = np.zeros((m, 2))
        for t, k in enumerate(members):
            i, j = cells[k]
            for c_, per in ((0, P), (1, Q)):
                kk = np.round((sols[c_][t] - off[i, j, c_]) / per)
                vals[t, c_] = off[i, j, c_] + kk * per
        if rank == 0:
            for t, k in enumerate(members):
                out[cells[k]] = vals[t]
            continue
        have = ~np.isnan(out[..., 0])
        flat = [cells[k][0] * mcols + cells[k][1] for k in members]
        ok = True
        shifted = vals.copy()
        for c_, per in ((0, P), (1, Q)):
            coef, *_ = np.linalg.lstsq(A_s[have.ravel()], out[..., c_].ravel()[have.ravel()], rcond=None)
            fit = (A_s @ coef)[flat]
            kk = np.round(np.median(fit - vals[:, c_]) / per)
            shifted[:, c_] = vals[:, c_] + kk * per
            if np.median(np.abs(shifted[:, c_] - fit)) > max(3.0, 0.08 * per):   # must sit on the same cloth
                ok = False
        if ok:
            for t, k in enumerate(members):
                out[cells[k]] = shifted[t]
    return out


def smooth_fill(field, deg=4):
    """Keep every measured area that agrees with its immediate neighbours (real folds included); replace one
    that does not (a pocket, a seam) by its neighbours' median; fill areas with no value from a smooth surface
    fitted through the measured ones."""
    f = field.copy()
    n, mcols = f.shape[:2]
    A = _poly_basis(n, mcols, deg)
    for c in range(2):
        ch = f[..., c]
        have = ~np.isnan(ch)
        pad = np.pad(ch, 1, constant_values=np.nan)
        stack = np.stack([pad[1 + di:n + 1 + di, 1 + dj:mcols + 1 + dj] for di in (-1, 0, 1) for dj in (-1, 0, 1)
                          if (di, dj) != (0, 0)])
        with np.errstate(all="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)     # an area with no measured neighbour
            med = np.nanmedian(stack, 0)
        dev = np.abs(ch - med)
        lim = max(1.5, 4 * float(np.nanmedian(dev[have])) if have.any() else 1.5)
        bad = have & ~np.isnan(med) & (dev > lim)
        ch = np.where(bad, med, ch)
        ok = ~np.isnan(ch)
        coef, *_ = np.linalg.lstsq(A[ok.ravel()], ch.ravel()[ok.ravel()], rcond=None)
        fit = (A @ coef).reshape(n, mcols)
        f[..., c] = np.where(ok, ch, fit)
    return f


def full_field(field, centres, shape):
    """The offset field at every pixel, by bilinear interpolation between area centres."""
    H, W = shape
    cy, cx = centres
    gy = (np.arange(H, dtype=np.float32) - cy[0]) / (cy[1] - cy[0] if len(cy) > 1 else 1)
    gx = (np.arange(W, dtype=np.float32) - cx[0]) / (cx[1] - cx[0] if len(cx) > 1 else 1)
    mx, my = (a.astype(np.float32) for a in np.meshgrid(gx, gy))
    return [cv2.remap(field[..., c].astype(np.float32), mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            for c in range(2)]


def measured_mask(un, centres, shape, half):
    """Pixels lying among measured areas (within half an area of one)."""
    H, W = shape
    cy, cx = centres
    have = ~np.isnan(un[..., 0])
    mk = np.zeros((H, W), np.uint8)
    for i, j in zip(*np.where(have), strict=True):
        y, x = int(cy[i]), int(cx[j])
        mk[max(0, y - half[0]):y + half[0], max(0, x - half[1]):x + half[1]] = 1
    return mk.astype(bool)


def accumulate(lab, m, ox, oy, P, Q, up=2):
    """Median of the garment pixels landing on each spot of one repeat (at `up` times the photo's detail).
    Returns (the repeat in Lab, how many pixels landed on each spot)."""
    H, W = m.shape
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    u = ((xx - ox) % P)[m]
    v = ((yy - oy) % Q)[m]
    bu = np.minimum((u * up).astype(int), P * up - 1)
    bv = np.minimum((v * up).astype(int), Q * up - 1)
    key = bv * (P * up) + bu
    order = np.argsort(key, kind="stable")
    key_s = key[order]
    px = lab[m][order]
    tile = np.full((Q * up * P * up, 3), np.nan, np.float32)
    counts = np.zeros(Q * up * P * up, int)
    starts = np.r_[0, np.where(np.diff(key_s))[0] + 1]
    ends = np.r_[starts[1:], len(key_s)]
    for s, e in zip(starts, ends, strict=True):
        tile[key_s[s]] = np.median(px[s:e], 0)
        counts[key_s[s]] = e - s
    tile = tile.reshape(Q * up, P * up, 3)
    # fill any empty spot from its neighbours
    for _ in range(4):
        miss = np.isnan(tile[..., 0])
        if not miss.any():
            break
        sm = cv2.blur(np.nan_to_num(tile), (3, 3))
        wt = cv2.blur((~miss).astype(np.float32), (3, 3))[..., None]
        tile[miss] = (sm / np.maximum(wt, 1e-3))[miss]
    return tile, counts.reshape(Q * up, P * up)


def rectify(cut, P, Q, ref_lab=None, iters=3, center_gap=0.06, log=quiet, thresh=40, stride=0.2, deg=4, cover=0.75,
            up=1, side=None):
    """Flatten the plaid of a cutout whose repeat is P x Q px. `side` ("left" or "right") uses one front only.
    Returns (one straight repeat in Lab, info with the offset map `ox`/`oy` and per-spot `counts`) or None
    when too few areas could be measured."""
    rgb = np.asarray(cut.convert("RGB"))
    lab = to_lab(rgb)
    m = garment_mask(cut, thresh=thresh)   # faint garment too: areas that are really background fail to match
    xs = np.where(m.any(0))[0]
    mid, gap = (xs.min() + xs.max()) // 2, int(center_gap * (xs.max() - xs.min()))
    mm = m.copy()
    mm[:, mid - gap: mid + gap] = False            # the button strip
    if side == "left":                               # one front only: the two fronts do not line up
        mm[:, mid:] = False
    elif side == "right":
        mm[:, :mid] = False
    sig = signal(lab)
    if ref_lab is None:
        # first reference: the repeat-sized square that best matches its neighbours (no flattening yet)
        bt = best_tile(lab, mm, P, Q)
        if bt is None:   # no square with neighbours on the garment: the best-covered square
            cov = cv2.blur(mm.astype(np.float32), (P, Q))
            cy, cx = np.unravel_index(np.argmax(cov), cov.shape)
            x, y = max(0, cx - P // 2), max(0, cy - Q // 2)
        else:
            _, x, y = bt
        ref_lab = lab[y:y + Q, x:x + P]
    info = {}
    for it in range(iters):
        if ref_lab.shape[:2] == (Q, P):
            ref_sig = signal(ref_lab)
        else:
            ref_sig = cv2.resize(signal(ref_lab), (P, Q), interpolation=cv2.INTER_AREA)
        ref_sig = cv2.GaussianBlur(ref_sig, (0, 0), 0.7)   # grain must not steer the matching
        off, conf, centres = local_offsets_match(sig, mm, ref_sig, P, Q, stride_frac=stride, cover=cover)
        un = unwrap_ls(off, conf, P, Q, min_conf=0.5)
        n_ok = int((~np.isnan(un[..., 0])).sum())
        if n_ok < 3:
            log(f"  pass {it + 1}: only {n_ok} areas could be measured")
            return None
        field = smooth_fill(un, deg=deg)
        ox, oy = full_field(field, centres, m.shape)
        use = mm & measured_mask(un, centres, m.shape, (Q // 2, P // 2))
        # only where the map is steady: where it changes fast (an edge of the measured area, a guessed stretch)
        # it would pile many photo pixels onto one spot of the repeat and draw a line that is not in the cloth
        gx_ = cv2.Sobel(ox, cv2.CV_32F, 1, 0, ksize=3) / 8
        gy_ = cv2.Sobel(oy, cv2.CV_32F, 0, 1, ksize=3) / 8
        cx_ = cv2.Sobel(ox, cv2.CV_32F, 0, 1, ksize=3) / 8
        cy_ = cv2.Sobel(oy, cv2.CV_32F, 1, 0, ksize=3) / 8
        bend = np.maximum.reduce([np.abs(gx_), np.abs(gy_), np.abs(cx_), np.abs(cy_)])
        # the steepest places of the map are dropped: the top tenth of the bend among the pixels in use, and
        # anything bending by more than half (never more than a third of the pixels, so a crumpled garment
        # still gives enough to measure)
        if use.any():
            lim_b = max(min(0.5, np.percentile(bend[use], 90)), np.percentile(bend[use], 67))
            use &= bend <= lim_b
        tile, counts = accumulate(lab, use, ox, oy, P, Q, up=up)
        # drop the pixels that disagree most with the rebuilt repeat at their spot (a seam, a pocket edge, the
        # button strip land on the same spots every time, so the median alone does not remove them), then rebuild
        H_, W_ = use.shape
        yy, xx = np.mgrid[0:H_, 0:W_].astype(np.float32)
        tu = (np.minimum(((xx - ox) % P) * up, P * up - 1)).astype(int)
        tv = (np.minimum(((yy - oy) % Q) * up, Q * up - 1)).astype(int)
        resid = np.linalg.norm(lab - tile[tv, tu], axis=2)
        lim = np.percentile(resid[use], 85)
        bad = (resid > lim).astype(np.uint8)
        # only disagreements that form lines or patches count, not the scattered grain of the cloth
        bad = cv2.morphologyEx(bad, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)) > 0
        tile, counts = accumulate(lab, use & ~bad, ox, oy, P, Q, up=up)
        spread = (np.nanmax(un[..., 0]) - np.nanmin(un[..., 0]), np.nanmax(un[..., 1]) - np.nanmin(un[..., 1]))
        log(f"  pass {it + 1}: {n_ok} areas measured (median match {np.median(conf[conf > 0]):.2f}); the cloth drifts "
            f"{spread[0]:.0f} px across and {spread[1]:.0f} px down; {np.median(counts):.0f} pixels per spot")
        ref_lab = tile
        info = dict(field=field, centres=centres, conf=conf, ox=ox, oy=oy, counts=counts)
    return ref_lab, info


def rectify_fronts(cut, P, Q, log=quiet, **kw):
    """Flatten each front of the garment on its own (the plaid does not line up across the buttons), then lay
    the second front's repeat over the first's and combine them, each spot weighted by how many pixels it holds.
    When the fronts do not clearly agree, the whole garment is flattened as one."""
    res = {}
    for side in ("left", "right"):
        r = rectify(cut, P, Q, log=lambda s, side=side: log(f"  {side}:{s}"), side=side, **kw)
        if r is not None:
            res[side] = r
    if not res:
        return None
    if len(res) == 1:
        return next(iter(res.values()))
    (ta, ia), (tb, ib) = res["left"], res["right"]
    sa, sb = signal(ta), signal(tb)
    cc = np.real(np.fft.ifft2(np.fft.fft2(sa - sa.mean()) * np.conj(np.fft.fft2(sb - sb.mean()))))
    dy, dx = np.unravel_index(np.argmax(cc), cc.shape)
    tb = np.roll(np.roll(tb, dy, 0), dx, 1)
    cb = np.roll(np.roll(ib["counts"], dy, 0), dx, 1).astype(np.float32)
    ca = ia["counts"].astype(np.float32)
    agree = float(np.corrcoef(signal(ta).ravel(), signal(tb).ravel())[0, 1])
    log(f"  the two fronts agree {agree:.2f} after lining up (shift {dx}, {dy})")
    if agree < 0.8:                       # not clearly the same: one map over the whole garment does better
        log("  the fronts do not clearly agree: flattening the whole garment as one")
        return rectify(cut, P, Q, log=log, **kw)
    w = (ca + cb)[..., None]
    merged = (ta * ca[..., None] + tb * cb[..., None]) / np.maximum(w, 1)
    return merged, dict(ia, counts=ca + cb)
