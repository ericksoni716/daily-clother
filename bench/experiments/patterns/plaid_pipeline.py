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


CHEST = 0.3   # the same chest height the renderer lines the pattern up at


def placed_phase(cut, info, P, Q):
    """Where the garment's centre line at chest height falls within the flattened repeat (fractions), and the
    repeat's size as a fraction of the garment's width, both measured on the garment itself."""
    m = dewarp.garment_mask(cut, thresh=128)
    ys, xs = np.where(m.any(1))[0], np.where(m.any(0))[0]
    gx0, gx1, gy0, gy1 = xs.min(), xs.max(), ys.min(), ys.max()
    xc, yc = int((gx0 + gx1) / 2), int(gy0 + CHEST * (gy1 - gy0))
    ox, oy = info["ox"], info["oy"]
    u = ((xc - ox[yc, xc]) % P) / P
    v = ((yc - oy[yc, xc]) % Q) / Q
    return (float(u), float(v)), P / (gx1 - gx0)


def landmarks(cut, tile_lab, info, P, Q, search=0.25):
    """The garment's button line, neck and hem in the photo. The button line is where the plaid is interrupted
    from top to bottom (the two fronts do not line up across it, and the strip itself is sewn differently):
    the column, near the middle, that disagrees most with the flattened repeat along its length."""
    rgb = np.asarray(cut.convert("RGB")); lab = dewarp.to_lab(rgb)
    m = dewarp.garment_mask(cut, thresh=128)
    H, W = m.shape
    ox, oy = info["ox"], info["oy"]
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    up = tile_lab.shape[1] // P
    tu = np.minimum(((xx - ox) % P) * up, P * up - 1).astype(int)
    tv = np.minimum(((yy - oy) % Q) * up, Q * up - 1).astype(int)
    resid = np.where(m, np.linalg.norm(lab - tile_lab[tv, tu], axis=2), np.nan)
    xs = np.where(m.any(0))[0]
    gx0, gx1 = xs.min(), xs.max()
    lo, hi = int(gx0 + (0.5 - search) * (gx1 - gx0)), int(gx0 + (0.5 + search) * (gx1 - gx0))
    with np.errstate(all="ignore"):
        col = np.nanmedian(resid[:, lo:hi], 0)
    k = max(3, P // 6)
    col_s = np.convolve(np.nan_to_num(col, nan=np.nanmedian(col)), np.ones(k) / k, "same")
    bx = lo + int(np.argmax(col_s))
    rows = np.where(m[:, bx])[0]
    return dict(button_x=bx, neck_y=int(rows.min()), hem_y=int(rows.max()), score=float(col_s.max() / np.nanmedian(col_s)))


def find_buttons(cut):
    """The button line: round shapes (Hough circles) of a button's size, of which the largest group lying in one
    near-vertical row at fairly even spacing is taken. Returns (x at each y as a line fit, the buttons) or None."""
    rgb = np.asarray(cut.convert("RGB")); m = dewarp.garment_mask(cut, thresh=128)
    xs, ys = np.where(m.any(0))[0], np.where(m.any(1))[0]
    gw, gh = xs.max() - xs.min(), ys.max() - ys.min()
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (0, 0), max(1.0, gw / 600))
    rmin, rmax = max(2, int(gw * 0.006)), max(4, int(gw * 0.022))
    circ = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, dp=1.2, minDist=rmin * 4, param1=90, param2=14,
                            minRadius=rmin, maxRadius=rmax)
    if circ is None:
        return None
    pts = [(x, y, r) for x, y, r in circ[0] if m[int(min(y, m.shape[0] - 1)), int(min(x, m.shape[1] - 1))]]
    best = None
    for x0, y0, _ in pts:
        for x1, y1, _ in pts:
            if y1 <= y0 + gh * 0.05:
                continue
            slope = (x1 - x0) / (y1 - y0)
            if abs(slope) > 0.15:
                continue
            row = [(x, y, r) for x, y, r in pts if abs(x - (x0 + slope * (y - y0))) < max(3, gw * 0.008)]
            if len(row) < 3:
                continue
            yy = np.sort([y for _, y, _ in row]); gaps = np.diff(yy)
            even = np.median(gaps) > 0 and np.std(gaps) / np.median(gaps) < 0.5
            score = len(row) + (2 if even else 0)
            if best is None or score > best[0]:
                best = (score, x0, y0, slope, row)
    if best is None:
        return None
    _, x0, y0, slope, row = best
    return dict(x_at=lambda y: x0 + slope * (y - y0), buttons=row, slope=float(slope))


PLACE_AT = 0.35   # where along the centre line, from neck to hem, the pattern is lined up


def placed_from_landmarks(info, P, Q, lm, photo_scale=1.0):
    """Where the repeat sits at the button line, PLACE_AT of the way from neck to hem, and the repeat's size as
    a fraction of the neck-to-hem length. `lm` is in the coordinates of the image Claude saw; photo_scale turns
    them into the cutout's."""
    nx, ny = lm["neck_center"]["x"] * photo_scale, lm["neck_center"]["y"] * photo_scale
    hx, hy = lm["hem_center"]["x"] * photo_scale, lm["hem_center"]["y"] * photo_scale
    bl = [(b["x"] * photo_scale, b["y"] * photo_scale) for b in lm["button_line"]]
    ay = ny + PLACE_AT * (hy - ny)
    if len(bl) >= 2:   # the button line's x at that height
        ys_, xs_ = np.array([b[1] for b in bl]), np.array([b[0] for b in bl])
        ax = float(np.polyval(np.polyfit(ys_, xs_, 1), ay))
    else:
        ax = nx + PLACE_AT * (hx - nx)
    ox, oy = info["ox"], info["oy"]
    iy, ix = int(round(ay)), int(round(ax))
    u = ((ax - ox[iy, ix]) % P) / P
    v = ((ay - oy[iy, ix]) % Q) / Q
    return (float(u), float(v)), P / (hy - ny), (ax, ay)
