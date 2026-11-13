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


def lattice_angle(cut):
    """The across repeat's length and tilt (degrees), from the strongest self-match off the centre."""
    import repeat2d as R2
    rgb = np.asarray(cut.convert("RGB")); m = R2.body_mask(np.asarray(cut)[..., 3]); lab = dewarp.to_lab(rgb)
    ac = sum(R2.autocorr(lab[..., c], m)[0] for c in range(3)) / 3
    c = np.fft.fftshift(ac).astype(np.float32)
    cy, cx = c.shape[0] // 2, c.shape[1] // 2
    hw = min(cx - 2, int(0.45 * m.shape[1])); hh = 12
    lo = max(12, int(0.06 * m.shape[1]))                  # shorter repeats are the weave's texture, not the plaid
    win = c[cy - hh:cy + hh + 1, cx + lo:cx + hw]          # shifts mostly across, a little up or down
    y, x = np.unravel_index(np.argmax(win), win.shape)
    dy, dx = y - hh, x + lo
    return float(np.hypot(dx, dy)), float(np.degrees(np.arctan2(dy, dx))), float(win[y, x])


def one_way(cut, log=print):
    """A plaid that repeats across but not down (madras, a placed band): the across bands folded onto their
    repeat, the down bands measured as one straightened sequence from top to bottom, then redrawn straight."""
    import stripes as S_
    P, ang, strength = lattice_angle(cut)
    up = cut.rotate(ang, Image.BICUBIC, expand=True)      # the across repeat level
    log(f"  repeats every {P:.1f} px across (turned {ang:.1f} degrees, match {strength:.2f})")
    rgb = np.asarray(up.convert("RGB")); lab = dewarp.to_lab(rgb); m = S_.mask_of(up)
    xs = np.where(m.any(0))[0]; gw = xs.max() - xs.min()
    # down: strips a whole across-repeat wide, so the across bands average out of them
    seq_d, y0, y1 = S_.straightened_sequence(lab, m, log=lambda s: None, strip_frac=min(0.5, P / gw))
    # across: tall strips, then folded onto the repeat
    seq_a, x0, x1 = S_.straightened_sequence(lab.transpose(1, 0, 2), m.T, log=lambda s: None, strip_frac=0.2)
    known = np.where(~np.isnan(seq_a[:, 0]))[0]
    rep_a = S_.folded_repeat(seq_a, P, known.min(), known.max(), up=1)
    M = lab[m].mean(0)
    span = np.arange(y0, y1 + 1)
    d = seq_d[y0:y1 + 1].copy()
    ok = ~np.isnan(d[:, 0])
    for c in range(3):
        d[:, c] = np.interp(np.arange(len(d)), np.where(ok)[0], d[ok, c])
    warp = np.clip(2 * rep_a - M, 0, 255)                  # undo the mixing with the other direction
    weft = np.clip(2 * d - M, 0, 255)
    tile = (warp[None, :, :] + weft[:, None, :]) / 2       # rows: the whole height; columns: one repeat
    rgb_t = dewarp.lab_to_rgb(tile.astype(np.float32))
    log(f"  drawn as {rgb_t.shape[1]} px across x {rgb_t.shape[0]} px down (the whole garment)")
    return dict(tile=rgb_t, P=P, width_frac=P / up.width, height_frac=len(d) / up.height)


def no_repeat(cut, log=print, lean_deg=None):
    """A plaid with no regular repeat (madras): both band sequences measured whole, straightened, and redrawn
    at their true positions across the garment. The fill is one tile the size of the garment."""
    import stripes as S_
    import quilt as Q_
    ang = Q_.lean(cut) if lean_deg is None else lean_deg
    up = cut.rotate(-ang, Image.BICUBIC, expand=True)
    rgb = np.asarray(up.convert("RGB")); lab = dewarp.to_lab(rgb); m = S_.mask_of(up)
    ys, xs = np.where(m.any(1))[0], np.where(m.any(0))[0]
    gw, gh = xs.max() - xs.min(), ys.max() - ys.min()
    # wide strips each way, so the bands running the other way average out
    seq_d, y0, y1 = S_.straightened_sequence(lab, m, log=lambda s: None, strip_frac=0.25)
    seq_a, x0, x1 = S_.straightened_sequence(lab.transpose(1, 0, 2), m.T, log=lambda s: None, strip_frac=0.25)
    def fill(seq, a, b):
        d = seq[a:b + 1].copy(); ok = ~np.isnan(d[:, 0])
        for c in range(3):
            d[:, c] = np.interp(np.arange(len(d)), np.where(ok)[0], d[ok, c])
        return d
    d, a = fill(seq_d, y0, y1), fill(seq_a, x0, x1)
    M = lab[m].mean(0)
    warp, weft = np.clip(2 * a - M, 0, 255), np.clip(2 * d - M, 0, 255)
    tile = (warp[None, :, :] + weft[:, None, :]) / 2
    log(f"  turned upright by {-ang:.1f} degrees; {len(a)} px across x {len(d)} px down, measured whole")
    return dict(tile=dewarp.lab_to_rgb(tile.astype(np.float32)), width_frac=len(a) / up.width)
