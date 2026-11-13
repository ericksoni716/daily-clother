"""Measure a plaid's two band sequences from a photo and redraw it with straight lines.

A woven plaid is (nearly) separable: each pixel mixes the colour of its vertical band (warp) with the colour of
its horizontal band (weft). So the photo is modelled as  I(x, y) ~ w(x) + f(y) - M.  The two sequences are
measured over one repeat each, from many short pieces of the garment, each piece slid into line with the others
before they are combined, so wavy lines, folds and a slightly skewed lay do not blur the result.
"""
import sys
import numpy as np
from PIL import Image

sys.path.insert(0, ".")
import repeat2d as R  # noqa: E402
import cv2shim as S  # noqa: E402


def circ_align(seg, ref):
    """Shift of `seg` (length P, Lab) that best matches `ref`, by circular cross-correlation over all channels."""
    a = seg - seg.mean(0)
    b = ref - ref.mean(0)
    cc = sum(np.real(np.fft.ifft(np.fft.fft(a[:, c]) * np.conj(np.fft.fft(b[:, c])))) for c in range(3))
    return int(np.argmax(cc))


def one_repeat_profile(lab, m, period, axis, piece=None):
    """Median profile over one repeat along `axis` (1: across, giving the vertical bands; 0: down).

    The garment is cut into pieces one repeat long and `piece` wide the other way; each piece's mean profile
    is aligned to a reference before the median is taken."""
    if axis == 0:
        lab, m = lab.transpose(1, 0, 2), m.T
    H, W = m.shape
    piece = piece or max(6, period // 2)
    segs = []
    for y0 in range(0, H - piece, max(2, piece // 2)):
        band, bm = lab[y0:y0 + piece], m[y0:y0 + piece]
        full = bm.all(0)                       # columns fully on the garment in this strip
        prof = band.mean(0)
        for x0 in range(0, W - period, max(2, period // 3)):
            if full[x0:x0 + period].all():
                segs.append(prof[x0:x0 + period])
    if len(segs) < 4:
        return None, 0
    segs = np.array(segs)
    # reference: the piece most like the others (a medoid over a sample), then align all, twice
    ref = np.median(segs, 0)
    for _ in range(3):
        shifted = np.array([np.roll(s, -circ_align(s, ref), 0) for s in segs])
        ref = np.median(shifted, 0)
    spread = float(np.median(np.abs(shifted - ref).mean((1, 2))))
    return ref, len(segs), spread


def bands(profile, max_colours=6, min_frac=0.02):
    """Turn a one-repeat Lab profile into crisp bands [(lab colour, start, length)], by k-means on the profile."""
    P = len(profile)
    best = None
    for k in range(2, max_colours + 1):
        S.setRNGSeed(0)
        comp, lab_i, centers = S.kmeans(profile.astype(np.float32), k, None, (3, 50, 0.1), 5, S.KMEANS_PP_CENTERS)
        score = comp / P
        if best is not None and best[0] - score < 0.15 * best[0]:   # one more colour must help clearly
            break
        best = (score, lab_i.ravel(), centers)
    _, lab_i, centers = best
    # smooth away one-pixel flickers, then runs
    lab_i = lab_i.copy()
    for i in range(P):
        if lab_i[i - 1] == lab_i[(i + 1) % P] != lab_i[i]:
            lab_i[i] = lab_i[i - 1]
    runs = []
    start = 0
    # start at a boundary so the wrap-around run is whole
    shift = next((i for i in range(P) if lab_i[i] != lab_i[i - 1]), 0)
    seq = np.roll(lab_i, -shift)
    for i in range(1, P + 1):
        if i == P or seq[i] != seq[start]:
            runs.append([int(seq[start]), start, i - start])
            start = i
    # merge runs shorter than min_frac of the repeat into their neighbour with the closer colour
    changed = True
    while changed and len(runs) > 2:
        changed = False
        for j, (c, s, n) in enumerate(runs):
            if n < max(1, min_frac * P):
                prev, nxt = runs[j - 1], runs[(j + 1) % len(runs)]
                d = lambda r: np.linalg.norm(centers[r[0]] - centers[c])
                tgt = prev if d(prev) <= d(nxt) else nxt
                tgt[2] += n
                if tgt is prev and j == 0:
                    pass
                runs.pop(j)
                # recompute starts
                pos = 0
                for r in runs:
                    r[1] = pos
                    pos += r[2]
                changed = True
                break
    return [(centers[c], s, n) for c, s, n in runs], shift


def render_plaid(warp, weft, P, Q, scale=8):
    """A crisp tile, one repeat each way: band colours mixed half and half where they cross."""
    def line(bs, n):
        out = np.zeros((n * scale, 3), np.float32)
        for col, s, length in bs:
            out[s * scale:(s + length) * scale] = col
        return out
    wx, wy = line(warp, P), line(weft, Q)
    tile_lab = (wx[None, :, :] + wy[:, None, :]) / 2
    return S.cvtColor(np.clip(tile_lab, 0, 255).astype(np.uint8), S.COLOR_LAB2RGB)


def measure(path, center_gap=0.06):
    im = Image.open(path).convert("RGBA")
    rgb = np.asarray(im.convert("RGB"))
    m = R.body_mask(np.asarray(im)[..., 3])
    lab = S.cvtColor(rgb, S.COLOR_RGB2LAB).astype(np.float32)
    ac = sum(R.autocorr(lab[..., c], m)[0] for c in range(3)) / 3
    H, W = m.shape

    def first_peak(line, maxlag, lo=8):
        best = None
        for lag in range(lo, maxlag):
            v = line[lag]
            if v > line[lag - 1] and v >= line[lag + 1] and v > 0.3 and (best is None or v > best[1] + 0.05):
                best = (lag, float(v))
        return best
    px, py = first_peak(ac[0, :W], W // 2), first_peak(ac[:H, 0], H // 2)
    if not (px and py):
        return None
    xs = np.where(m.any(0))[0]
    mid, gap = (xs.min() + xs.max()) // 2, int(center_gap * (xs.max() - xs.min()))
    mb = m.copy()
    mb[:, mid - gap: mid + gap] = False       # the button strip is sewn differently
    warp_p, nw, sw = one_repeat_profile(lab, mb, px[0], 1)
    weft_p, nf, sf = one_repeat_profile(lab, mb, py[0], 0)
    # separable model: a column mean is half its warp colour plus half the average weft, so undo the mixing
    M = lab[mb].mean(0)
    warp_c = np.clip(2 * warp_p - M, 0, 255)
    weft_c = np.clip(2 * weft_p - M, 0, 255)
    wb, _ = bands(warp_c)
    fb, _ = bands(weft_c)
    tile = render_plaid(wb, fb, px[0], py[0])
    gw = xs.max() - xs.min()
    return dict(period=(px[0], py[0]), pieces=(nw, nf), spread=(round(sw, 1), round(sf, 1)), warp=wb, weft=fb,
                tile=tile, width_frac=px[0] / gw * (gw / W))


if __name__ == "__main__":
    r = measure(sys.argv[1])
    print("repeat", r["period"], "pieces", r["pieces"], "spread", r["spread"])
    for name in ("warp", "weft"):
        print(name, [(S.cvtColor(np.array([[c]], np.uint8), S.COLOR_LAB2RGB)[0, 0].tolist(), n) for c, s, n in r[name]])
    Image.fromarray(r["tile"]).save(sys.argv[2])


def _edges(bs, n):
    """Band index for every position 0..n-1 of one repeat."""
    idx = np.zeros(n, int)
    for i, (_, s, length) in enumerate(bs):
        idx[s:s + length] = i
    return idx


def crossing_colours(path, r, center_gap=0.06):
    """Colour each band crossing from the photo itself: line every repeat-sized square up with the measured
    plaid (2-D circular cross-correlation), then take the median of the pixels that land in each crossing."""
    im = Image.open(path).convert("RGBA")
    rgb = np.asarray(im.convert("RGB")).astype(np.float32)
    m = R.body_mask(np.asarray(im)[..., 3])
    xs = np.where(m.any(0))[0]
    mid, gap = (xs.min() + xs.max()) // 2, int(center_gap * (xs.max() - xs.min()))
    m[:, mid - gap: mid + gap] = False
    lab = S.cvtColor(rgb.astype(np.uint8), S.COLOR_RGB2LAB).astype(np.float32)
    P, Q = r["period"]
    model = S.cvtColor(render_plaid(r["warp"], r["weft"], P, Q, scale=1), S.COLOR_RGB2LAB).astype(np.float32)
    ref = model - model.mean((0, 1))
    Fref = [np.fft.fft2(ref[..., c]) for c in range(3)]
    ix, iy = _edges(r["warp"], P), _edges(r["weft"], Q)
    nw, nf = len(r["warp"]), len(r["weft"])
    cells = [[[] for _ in range(nw)] for _ in range(nf)]
    H, W = m.shape
    used = 0
    for y0 in range(0, H - Q, max(2, Q // 3)):
        for x0 in range(0, W - P, max(2, P // 3)):
            if not m[y0:y0 + Q, x0:x0 + P].all():
                continue
            patch = lab[y0:y0 + Q, x0:x0 + P]
            p = patch - patch.mean((0, 1))
            cc = sum(np.real(np.fft.ifft2(np.fft.fft2(p[..., c]) * np.conj(Fref[c]))) for c in range(3))
            dy, dx = np.unravel_index(np.argmax(cc), cc.shape)   # patch(y, x) ~ model(y - dy, x - dx)
            if cc.max() <= 0:
                continue
            used += 1
            vy = iy[(np.arange(Q) - dy) % Q]
            vx = ix[(np.arange(P) - dx) % P]
            prgb = rgb[y0:y0 + Q, x0:x0 + P]
            for j in range(nf):
                rows = vy == j
                if not rows.any():
                    continue
                sub = prgb[rows]
                for i in range(nw):
                    cols = vx == i
                    if cols.any():
                        cells[j][i].append(sub[:, cols].reshape(-1, 3))
    grid = np.zeros((nf, nw, 3), np.float32)
    for j in range(nf):
        for i in range(nw):
            px_ = np.concatenate(cells[j][i]) if cells[j][i] else np.zeros((1, 3))
            # the core of the crossing: drop the pixels nearest its neighbours by taking the median
            grid[j, i] = np.median(px_, 0)
    return grid, used


def render_grid(r, grid, scale=8):
    P, Q = r["period"]
    ix, iy = _edges(r["warp"], P), _edges(r["weft"], Q)
    tile = grid[iy][:, ix]                       # Q x P x 3
    return np.repeat(np.repeat(tile, scale, 0), scale, 1).clip(0, 255).astype(np.uint8)


def local_period(lab, m, min_lag=8, thresh=0.3):
    """The repeat across and down, found in several regions of the garment and combined (median), so a crumpled
    garment whose spacing changes from place to place still gives its true repeat."""
    H, W = m.shape
    xs, ys = np.where(m.any(0))[0], np.where(m.any(1))[0]
    gw, gh = xs.max() - xs.min(), ys.max() - ys.min()
    win = int(max(gw, gh) * 0.4)
    found_x, found_y = [], []

    def first(line, maxlag):
        for lag in range(min_lag, maxlag):
            if line[lag] > line[lag - 1] and line[lag] >= line[lag + 1] and line[lag] > thresh:
                # prefer a clearly stronger peak a little further out (the true repeat over a sub-repeat)
                best = (lag, line[lag])
                for l2 in range(lag + 1, min(maxlag, int(lag * 2.2))):
                    if line[l2] > line[l2 - 1] and line[l2] >= line[l2 + 1] and line[l2] > best[1] + 0.08:
                        best = (l2, line[l2])
                return best[0]
        return None
    for y0 in range(ys.min(), ys.max() - win // 2, win // 2):
        for x0 in range(xs.min(), xs.max() - win // 2, win // 2):
            sm = m[y0:y0 + win, x0:x0 + win]
            if sm.mean() < 0.6:
                continue
            sl = lab[y0:y0 + win, x0:x0 + win]
            ac = sum(R.autocorr(sl[..., c], sm)[0] for c in range(3)) / 3
            h, w = sm.shape
            px, py = first(ac[0, :w], w // 2), first(ac[:h, 0], h // 2)
            if px:
                found_x.append(px)
            if py:
                found_y.append(py)
    if not found_x or not found_y:
        return None
    return int(np.median(found_x)), int(np.median(found_y)), found_x, found_y


def _keys(bs):
    """The colour class of each band: bands measured as the same colour share a key."""
    uniq, keys = [], []
    for col, _, _ in bs:
        k = next((i for i, u in enumerate(uniq) if np.allclose(u, col)), None)
        if k is None:
            uniq.append(col)
            k = len(uniq) - 1
        keys.append(k)
    return keys


def crossing_colours_pooled(path, r, center_gap=0.06, min_cover=0.85):
    """Like crossing_colours, but every crossing of the same two band colours gets one colour, pooled from all
    of them, so a line keeps its colour along its whole length. Squares mostly on the garment are used too,
    with only their garment pixels."""
    im = Image.open(path).convert("RGBA")
    rgb = np.asarray(im.convert("RGB")).astype(np.float32)
    m = R.body_mask(np.asarray(im)[..., 3])
    xs = np.where(m.any(0))[0]
    mid, gap = (xs.min() + xs.max()) // 2, int(center_gap * (xs.max() - xs.min()))
    m[:, mid - gap: mid + gap] = False
    lab = S.cvtColor(rgb.astype(np.uint8), S.COLOR_RGB2LAB).astype(np.float32)
    P, Q = r["period"]
    model = S.cvtColor(render_plaid(r["warp"], r["weft"], P, Q, scale=1), S.COLOR_RGB2LAB).astype(np.float32)
    ref = model - model.mean((0, 1))
    Fref = [np.fft.fft2(ref[..., c]) for c in range(3)]
    ix, iy = _edges(r["warp"], P), _edges(r["weft"], Q)
    kw, kf = _keys(r["warp"]), _keys(r["weft"])
    pools: dict = {}
    H, W = m.shape
    used = 0
    for y0 in range(0, H - Q, max(2, Q // 4)):
        for x0 in range(0, W - P, max(2, P // 4)):
            pm = m[y0:y0 + Q, x0:x0 + P]
            if pm.mean() < min_cover:
                continue
            patch = lab[y0:y0 + Q, x0:x0 + P]
            p = np.where(pm[..., None], patch - patch[pm].mean(0), 0)
            cc = sum(np.real(np.fft.ifft2(np.fft.fft2(p[..., c]) * np.conj(Fref[c]))) for c in range(3))
            dy, dx = np.unravel_index(np.argmax(cc), cc.shape)
            if cc.max() <= 0:
                continue
            used += 1
            vy = iy[(np.arange(Q) - dy) % Q]
            vx = ix[(np.arange(P) - dx) % P]
            prgb = rgb[y0:y0 + Q, x0:x0 + P]
            # key of every pixel: (warp class, weft class)
            key = np.array(kf)[vy][:, None] * 100 + np.array(kw)[vx][None, :]
            # only the core of each crossing: not the pixel either side of a band edge (bands 3+ wide)
            core_y = np.ones(Q, bool); core_x = np.ones(P, bool)
            for vv, core, bs in ((vy, core_y, r["weft"]), (vx, core_x, r["warp"])):
                edge = vv != np.roll(vv, 1)
                wide = np.array([bs[b][2] for b in vv]) >= 3
                core &= ~((edge | np.roll(edge, -1)) & wide)
            pm = pm & core_y[:, None] & core_x[None, :]
            for k in np.unique(key[pm]):
                sel = (key == k) & pm
                pools.setdefault(int(k), []).append(prgb[sel])
    colour = {k: np.median(np.concatenate(v), 0) for k, v in pools.items()}
    nf, nw = len(r["weft"]), len(r["warp"])
    grid = np.zeros((nf, nw, 3), np.float32)
    for j in range(nf):
        for i in range(nw):
            grid[j, i] = colour.get(kf[j] * 100 + kw[i], [128, 128, 128])
    return grid, used, len(colour)


def _rotate_lab(win, deg):
    """Rotate a Lab window (float) about its centre; bilinear, per channel."""
    return np.dstack([np.asarray(Image.fromarray(win[..., c].astype(np.float32), "F").rotate(deg, Image.BILINEAR))
                      for c in range(3)])


def straightened_profiles(lab, m, period, axis, angles=np.arange(-12, 12.5, 1.0)):
    """Profiles across one repeat from square windows of the garment, each window first turned to the angle at
    which its lines run straightest (the profile across it is sharpest), so slanted or curving lines in a
    crumpled photo do not smear into wide, soft bands."""
    if axis == 0:
        lab, m = lab.transpose(1, 0, 2), m.T
    H, W = m.shape
    n = int(period * 2.2)             # a window a bit over two repeats wide: room to turn, enough to measure
    inner = slice(n // 6, n - n // 6)
    segs, turns = [], []
    for y0 in range(0, H - n, max(4, n // 3)):
        for x0 in range(0, W - n, max(4, n // 3)):
            wm = m[y0:y0 + n, x0:x0 + n]
            if wm.mean() < 0.85:
                continue
            win = lab[y0:y0 + n, x0:x0 + n]
            win = np.where(wm[..., None], win, win[wm].mean(0))   # off-garment pixels add no lines
            best = None
            for a in angles:
                rw = _rotate_lab(win, a)[inner, inner]
                prof = rw.mean(0)
                sharp = float(prof.var(0).sum())
                if best is None or sharp > best[0]:
                    best = (sharp, a, prof)
            _, a, prof = best
            turns.append(a)
            for x in range(0, len(prof) - period + 1, max(2, period // 3)):
                segs.append(prof[x:x + period])
    if len(segs) < 4:
        return None, 0, turns
    segs = np.array(segs)
    ref = np.median(segs, 0)
    for _ in range(3):
        shifted = np.array([np.roll(s, -circ_align(s, ref), 0) for s in segs])
        ref = np.median(shifted, 0)
    return ref, len(segs), turns


def measure_straightened(path, center_gap=0.06):
    base = measure(path)                       # the repeat (from the whole garment)
    if base is None:
        return None
    im = Image.open(path).convert("RGBA")
    rgb = np.asarray(im.convert("RGB"))
    m = R.body_mask(np.asarray(im)[..., 3])
    lab = S.cvtColor(rgb, S.COLOR_RGB2LAB).astype(np.float32)
    xs = np.where(m.any(0))[0]
    mid, gap = (xs.min() + xs.max()) // 2, int(center_gap * (xs.max() - xs.min()))
    mb = m.copy()
    mb[:, mid - gap: mid + gap] = False
    P, Q = base["period"]
    wp, nw, tw = straightened_profiles(lab, mb, P, 1)
    fp, nf, tf = straightened_profiles(lab, mb, Q, 0)
    if wp is None or fp is None:
        return None
    M = lab[mb].mean(0)
    wb, _ = bands(np.clip(2 * wp - M, 0, 255))
    fb, _ = bands(np.clip(2 * fp - M, 0, 255))
    out = dict(base, warp=wb, weft=fb, pieces=(nw, nf), turns=(np.round(np.percentile(tw, [10, 50, 90]), 1).tolist(),
                                                               np.round(np.percentile(tf, [10, 50, 90]), 1).tolist()))
    return out
