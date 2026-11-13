"""Find the repeat, flatten the cloth, then turn the straightened repeat into crisp bands with pooled colours."""
import sys; sys.path.insert(0, ".")
import numpy as np, cv2
from PIL import Image
import dewarp, sett, repeat2d as R

def period(cut):
    rgb = np.asarray(cut.convert("RGB")); m = R.body_mask(np.asarray(cut)[..., 3])
    lab = dewarp.to_lab(rgb)
    ac = sum(R.autocorr(lab[..., c], m)[0] for c in range(3)) / 3
    H, W = m.shape
    def first(line, maxlag, lo=8):
        best = None
        for lag in range(lo, maxlag):
            v = line[lag]
            if v > line[lag - 1] and v >= line[lag + 1] and v > 0.3 and (best is None or v > best[1] + 0.05):
                best = (lag, float(v))
        return best
    px, py = first(ac[0, :W], W // 2), first(ac[:H, 0], H // 2)
    return (px[0], py[0]) if px and py else None

def crisp(tile_lab, P, Q, up=2):
    """Bands from the straightened repeat, and each crossing coloured by the median of its core pixels,
    pooled over every crossing of the same two band colours."""
    t = tile_lab
    M = t.reshape(-1, 3).mean(0)
    colp = t.mean(0)                      # across: the vertical bands (mixed with the average of the others)
    rowp = t.mean(1)
    wb, _ = sett.bands(np.clip(2 * colp - M, 0, 255), min_frac=0.01)
    fb, _ = sett.bands(np.clip(2 * rowp - M, 0, 255), min_frac=0.01)
    Pu, Qu = t.shape[1], t.shape[0]
    ix, iy = sett._edges(wb, Pu), sett._edges(fb, Qu)
    kw, kf = sett._keys(wb), sett._keys(fb)
    # core: not the spot either side of a band edge, for bands at least 4 spots wide
    def core(idx, bs):
        e = idx != np.roll(idx, 1); wide = np.array([bs[b][2] for b in idx]) >= 4
        return ~((e | np.roll(e, -1)) & wide)
    cy, cx = core(iy, fb), core(ix, wb)
    key = np.array(kf)[iy][:, None] * 100 + np.array(kw)[ix][None, :]
    sel = cy[:, None] & cx[None, :]
    rgb = dewarp.lab_to_rgb(t).astype(np.float32)
    colour = {int(k): np.median(rgb[(key == k) & sel], 0) for k in np.unique(key[sel])}
    for k in np.unique(key):                 # a pair with no core spot: use all its spots
        colour.setdefault(int(k), np.median(rgb[key == k], 0))
    out = np.zeros((Qu, Pu, 3), np.float32)
    for k, c in colour.items():
        out[key == k] = c
    return out.astype(np.uint8), wb, fb

def run(path, log=print):
    cut = Image.open(path).convert("RGBA")
    per = period(cut)
    if per is None:
        log("  no repeat found"); return None
    P, Q = per
    log(f"  repeat {P} x {Q} px")
    res = dewarp.rectify(cut, P, Q, log=log)
    if res is None:
        return None
    tl, info = res
    flat = dewarp.lab_to_rgb(tl)
    tile, wb, fb = crisp(tl, P, Q)
    log(f"  {len(wb)} bands across, {len(fb)} down")
    xs = np.where(dewarp.garment_mask(cut).any(0))[0]
    return dict(P=P, Q=Q, flat=flat, tile=tile, info=info, width_frac=P / cut.width, cut=cut)


def band_edges(profile, min_gap=2, k_noise=3.0):
    """Band edges where the colour changes sharply along a straightened profile (cyclic). The profile is
    smoothed a little first, and an edge must stand clearly above the grain: k_noise times the typical change
    between neighbouring spots."""
    n = len(profile)
    sm = np.stack([np.convolve(np.r_[profile[-2:, c], profile[:, c], profile[:2, c]], [0.25, 0.5, 0.25], "same")[2:-2]
                   for c in range(3)], 1)
    w = np.array([1.0, 2.5, 2.5])            # a change of colour (navy to burgundy) counts as much as of lightness
    d = np.linalg.norm((np.roll(sm, -1, 0) - np.roll(sm, 1, 0)) * w, axis=1)
    floor = k_noise * np.percentile(d, 20)        # grain: the change at the quietest spots
    peaks = [i for i in range(n) if d[i] >= d[i - 1] and d[i] > d[(i + 1) % n] and d[i] > floor]
    peaks.sort(key=lambda i: -d[i])
    kept = []
    for i in peaks:
        if all(min((i - k) % n, (k - i) % n) >= min_gap for k in kept):
            kept.append(i)
    return sorted(kept)


def crisp2(tile_lab):
    """Cells between sharp edges; each cell coloured by the median of its middle."""
    rgb = dewarp.lab_to_rgb(tile_lab).astype(np.float32)
    Qu, Pu = rgb.shape[:2]
    ex = band_edges(tile_lab.mean(0))
    ey = band_edges(tile_lab.mean(1))
    def cells(edges, n):
        if not edges:
            return [(0, n)]
        out = []
        for a, b in zip(edges, edges[1:] + [edges[0] + n]):
            out.append((a, b))
        return out
    out = np.zeros_like(rgb)
    for (y0, y1) in cells(ey, Qu):
        for (x0, x1) in cells(ex, Pu):
            ys = np.arange(y0, y1) % Qu; xs = np.arange(x0, x1) % Pu
            cy = ys[1:-1] if len(ys) >= 4 else ys      # the middle of the cell, not its edges
            cx = xs[1:-1] if len(xs) >= 4 else xs
            col = np.median(rgb[np.ix_(cy, cx)].reshape(-1, 3), 0)
            out[np.ix_(ys, xs)] = col
    return out.astype(np.uint8), len(ex), len(ey)
