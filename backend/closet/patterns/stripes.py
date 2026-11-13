"""Stripes, measured from the photo.

1. Which way the stripes run: the dominant direction of colour change over the body.
2. The whole stripe sequence, straightened: the body is cut into narrow strips across the stripes, each strip's
   colour profile is slid piece by piece into line with a reference (so stripes that bow, slant or pucker line
   up), and the median of the lined-up strips is the sequence.
3. Regular stripes (`measure4`) are folded onto one sharp repeat by finding the stripes' position area by area
   (`fold_by_match`); the repeat length is the one that folds most sharply. Yarn colours are the clusters that
   form real stripes (a blend at an edge is only a sliver). Stripes with no repeat use the straightened
   sequence over the whole garment, laid out as fractions of it (`measure3`).
4. Placed stripes (a polo's chest bands): `ground_stripes` measures the plain repeating ground in its own
   stretch, `compose_placed` draws the plain stretches with it and the bands with their measured colours.
   `regions_from_landmarks` and `sleeves_carry_bands` tell whether the bands carry on onto the sleeves.
"""
import warnings

import cv2
import numpy as np
from PIL import Image

from .common import quiet

_W = np.array([0.6, 1, 1])     # colour distances: lightness counts a little less than the colour itself


def _hexes(lab_cols):
    rgbs = cv2.cvtColor(np.clip(lab_cols[None], 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)[0]
    return ["#{:02x}{:02x}{:02x}".format(*(int(v) for v in c)) for c in rgbs]


def _repeat_from_logs(logs):
    """The repeat length `extend_by_repeat` reported (its log line), or None when it found none."""
    line = next((s for s in logs if "repeat every" in s), None)
    return int(line.split("every ")[1].split(" px")[0]) if line else None


def mask_of(cut, thresh=200, erode_frac=0.01):
    """The garment's pixels in a cutout, shrunk a little away from its edge."""
    a = np.asarray(cut)[..., 3]
    m = (a > thresh).astype(np.uint8)
    k = max(3, int(max(a.shape) * erode_frac) | 1)
    return cv2.erode(m, np.ones((k, k), np.uint8)).astype(bool)


def orientation(lab, m):
    """'horizontal' when colour changes mostly from top to bottom (stripes run across), else 'vertical';
    and the ratio of the two."""
    L = cv2.GaussianBlur(lab[..., 0] + lab[..., 1] + lab[..., 2], (0, 0), 1.0)
    gx = cv2.Sobel(L, cv2.CV_32F, 1, 0)
    gy = cv2.Sobel(L, cv2.CV_32F, 0, 1)
    ex, ey = float((gx[m] ** 2).sum()), float((gy[m] ** 2).sum())
    return ("horizontal" if ey > ex else "vertical"), ey / max(ex, 1e-6)


def strip_profiles(lab, m, strip_frac=0.03, lo=0.2, hi=0.8, center_gap=0.05):
    """Profiles along the stripes' 'across' direction, one per narrow strip. lab/m are oriented so that the
    profile runs down axis 0. Returns profiles (n, H, 3) with NaN where off the garment, and the strips'
    centre positions."""
    H, W = m.shape
    xs = np.where(m.any(0))[0]
    gx0, gx1 = xs.min(), xs.max()
    gw = gx1 - gx0
    w = max(3, int(gw * strip_frac))
    mid = (gx0 + gx1) / 2
    profs, centres = [], []
    for x in range(int(gx0 + lo * gw), int(gx0 + hi * gw) - w, max(2, w // 2)):
        if abs(x + w / 2 - mid) < center_gap * gw:      # the button strip
            continue
        sm = m[:, x:x + w]
        cnt = sm.sum(1)
        p = (lab[:, x:x + w] * sm[..., None]).sum(1) / np.maximum(cnt, 1)[:, None]
        p[cnt < 0.6 * w] = np.nan
        profs.append(p)
        centres.append(x + w / 2)
    return np.array(profs), np.array(centres)


def align_piecewise(p, ref, piece, max_shift):
    """Slide `p` (H, 3, NaN off garment) into line with `ref`, piece by piece: the best shift for each piece,
    smoothed along the profile, then `p` resampled. Returns the aligned profile (NaN where unknown)."""
    H = len(p)
    shifts, at = [], []
    for s in range(0, H - piece, max(4, piece // 3)):
        seg = p[s:s + piece]
        if np.isnan(seg).any():
            continue
        best = None
        for d in range(-max_shift, max_shift + 1):
            a, b = s + d, s + d + piece
            if a < 0 or b > H:
                continue
            r = ref[a:b]
            if np.isnan(r).any():
                continue
            x = seg - seg.mean(0)
            y = r - r.mean(0)
            den = np.sqrt((x ** 2).sum() * (y ** 2).sum()) + 1e-6
            score = (x * y).sum() / den
            if best is None or score > best[0]:
                best = (score, d)
        if best and best[0] > 0.5:
            shifts.append(best[1])
            at.append(s + piece / 2)
    out = np.full_like(p, np.nan)
    if len(shifts) < 2:
        return out
    shifts, at = np.array(shifts, float), np.array(at)
    # smooth: median of neighbours, then interpolate along the profile
    sm = np.array([np.median(shifts[max(0, i - 2):i + 3]) for i in range(len(shifts))])
    pos = np.arange(H, dtype=float)
    d = np.interp(pos, at, sm)
    # sample p at pos - d  (p's content at y sits at y + d in ref coordinates)
    src = pos - d
    for c in range(3):
        valid = ~np.isnan(p[:, c])
        out[:, c] = np.interp(src, pos[valid], p[valid, c], left=np.nan, right=np.nan) if valid.sum() > 2 else np.nan
    # do not invent values across gaps of the original
    gap = np.interp(src, pos, np.isnan(p[:, 0]).astype(float))
    out[gap > 0.5] = np.nan
    return out


def straightened_sequence(lab, m, iters=3, log=quiet, strip_frac=0.03):
    """The stripe sequence down axis 0, straightened (see the module's docstring). Returns (sequence (H, 3) in
    Lab, NaN where unknown; the garment's first and last row) or None when too few strips fit."""
    profs, centres = strip_profiles(lab, m, strip_frac=strip_frac)
    if len(profs) < 3:
        return None
    H = profs.shape[1]
    ys = np.where(m.any(1))[0]
    gh = ys.max() - ys.min()
    piece = max(12, int(gh * 0.12))
    max_shift = max(4, int(gh * 0.06))
    # first reference: the strip with the most garment
    ref = profs[np.argmax((~np.isnan(profs[..., 0])).sum(1))]
    for it in range(iters):
        al = np.array([align_piecewise(p, ref, piece, max_shift) for p in profs])
        good = (~np.isnan(al[..., 0])).sum(0)
        with np.errstate(all="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)     # a position no strip covers
            new = np.nanmedian(al, 0)
        new[good < max(2, 0.25 * len(profs))] = np.nan
        used = int(((~np.isnan(al[..., 0])).sum(1) > 0.3 * H).sum())
        log(f"  pass {it + 1}: {used} of {len(profs)} strips lined up")
        # keep the reference where the new one is unknown
        ref = np.where(np.isnan(new), ref, new)
    # trust only positions where enough strips agree; elsewhere continue the trusted part by its repeat
    trusted = good >= max(3, 0.5 * len(profs))
    ref = np.where(trusted[:, None], ref, np.nan)
    ref = extend_by_repeat(ref, ys.min(), ys.max(), log=log)
    return ref, ys.min(), ys.max()


def extend_by_repeat(seq, y0, y1, log=quiet, min_corr=0.6):
    """Fill unknown positions of the sequence from its own repeat, with the right phase, when it has one."""
    known = ~np.isnan(seq[:, 0])
    if known.sum() < 20:
        return seq
    ks = np.where(known)[0]
    a, b = ks.min(), ks.max()
    core = seq[a:b + 1].copy()
    ok = ~np.isnan(core[:, 0])
    x = np.where(ok[:, None], core - np.nanmean(core, 0), 0)
    n = len(core)
    best = None
    for lag in range(6, n // 2):
        u, v = x[:-lag], x[lag:]
        w = ok[:-lag] & ok[lag:]
        if w.sum() < 0.5 * n:
            continue
        num = (u[w] * v[w]).sum()
        den = np.sqrt((u[w] ** 2).sum() * (v[w] ** 2).sum()) + 1e-6
        r = num / den
        if r > min_corr and (best is None or r > best[1] + 0.03):
            best = (lag, r)
            if r > 0.85:
                break
    if best is None:
        log("  no repeat in the stripes: unknown parts take the nearest colour")
        return seq
    lag = best[0]
    # measure3 and measure4 read the repeat back from this line: keep its wording
    log(f"  stripes repeat every {lag} px (match {best[1]:.2f}); unknown parts continue that repeat")
    # one repeat: median of all known positions folded onto the repeat, phase anchored at a
    fold = np.full((lag, 3), np.nan)
    for ph in range(lag):
        vals = core[ph::lag]
        vals = vals[~np.isnan(vals[:, 0])]
        if len(vals):
            fold[ph] = np.median(vals, 0)
    out = seq.copy()
    for yy in range(y0, y1 + 1):
        if np.isnan(out[yy, 0]):
            out[yy] = fold[(yy - a) % lag]
    return out


def refine_repeat(seq, lag, a, b):
    """The repeat's length to a fraction of a pixel: the length at which folding the sequence onto one repeat
    gives the sharpest (most varied) result."""
    core = seq[a:b + 1]
    ok = ~np.isnan(core[:, 0])
    pos = np.arange(len(core))[ok]
    vals = core[ok]
    best = None
    for L in np.arange(lag - 0.6, lag + 0.6, 0.02):
        bins = np.floor((pos % L) / L * 32).astype(int)
        means = np.array([vals[bins == k].mean(0) if (bins == k).any() else np.nan * np.ones(3) for k in range(32)])
        sharp = np.nanvar(means, 0).sum()
        if best is None or sharp > best[0]:
            best = (sharp, L)
    return best[1]


def folded_repeat(seq, L, a, b, up=4):
    """One repeat at `up` times the photo's detail, from every copy of it along the straightened sequence."""
    core = seq[a:b + 1]
    ok = ~np.isnan(core[:, 0])
    pos = np.arange(len(core))[ok]
    vals = core[ok]
    nb = max(8, int(round(L * up)))
    bins = np.floor((pos % L) / L * nb).astype(int) % nb
    rep = np.full((nb, 3), np.nan)
    for k in range(nb):
        sel = bins == k
        if sel.any():
            rep[k] = np.median(vals[sel], 0)
    for c in range(3):                    # fill empty bins from neighbours (cyclic)
        bad = np.isnan(rep[:, c])
        if bad.any():
            idx = np.arange(nb)
            rep[bad, c] = np.interp(idx[bad], idx[~bad], rep[~bad, c], period=nb)
    return rep


def yarn_colours(cut, kmax=8, sample=60000):
    """The garment's yarn colours (Lab) from its own pixels: generous clustering; small clusters are kept when
    they are a colour of their own (a pink accent stripe), not when they are a shade between two others."""
    rgb = np.asarray(cut.convert("RGB"))
    m = mask_of(cut, erode_frac=0.02)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)[m]
    if len(lab) > sample:
        lab = lab[np.random.default_rng(0).choice(len(lab), sample, replace=False)]
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    cv2.setRNGSeed(0)
    _, lbl, cen = cv2.kmeans(lab, kmax, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    lbl = lbl.ravel()
    share = np.bincount(lbl, minlength=kmax) / len(lbl)
    cols = []
    for i in range(kmax):
        px = lab[lbl == i]
        if len(px) < 0.003 * len(lab):
            continue
        cols.append(([np.percentile(px[:, 0], 75), np.median(px[:, 1]), np.median(px[:, 2])], share[i]))
    # drop near-duplicates (keep the bigger), and small clusters that are a shade between two bigger ones
    cols.sort(key=lambda t: -t[1])
    kept = []
    for c, sh in cols:
        c = np.array(c)
        if any(np.linalg.norm((c - k) * np.array([0.5, 1, 1])) < 10 for k, _ in kept):
            continue
        between = False
        if sh < 0.03:
            for i, (A, _) in enumerate(kept):
                for B, _ in kept[i + 1:]:
                    t = np.clip(np.dot(c - A, B - A) / (np.dot(B - A, B - A) + 1e-6), 0, 1)
                    if 0.15 < t < 0.85 and np.linalg.norm(A + t * (B - A) - c) < 7:
                        between = True
        if not between:
            kept.append((c, sh))
    return np.array([k for k, _ in kept], np.float32)


def clean_runs(labels, min_len, cyclic=True):
    """Merge runs shorter than min_len into a neighbouring run of another colour, shortest first. With
    cyclic=True the first and last runs are one run when they share a colour (the repeat wraps around)."""
    lab = np.array(labels).copy()
    n = len(lab)
    for _ in range(n):
        if cyclic:
            shift = next((i for i in range(n) if lab[i] != lab[i - 1]), None)
            if shift is None:
                break
            order = np.roll(np.arange(n), -shift)
        else:
            order = np.arange(n)
        seqv = lab[order]
        runs, s0 = [], 0
        for i in range(1, n + 1):
            if i == n or seqv[i] != seqv[s0]:
                runs.append((s0, i - s0))
                s0 = i
        if len(runs) <= 2:
            break
        j = min(range(len(runs)), key=lambda r: runs[r][1])
        st, ln = runs[j]
        if ln >= min_len:
            break
        prev_r = runs[j - 1] if (j > 0 or cyclic) else runs[j + 1]
        nxt_r = runs[(j + 1) % len(runs)] if (j + 1 < len(runs) or cyclic) else runs[j - 1]
        tgt = prev_r if prev_r[1] >= nxt_r[1] else nxt_r
        new_label = seqv[tgt[0]]
        seqv[st:st + ln] = new_label
        lab[order] = seqv
    return lab


def measure3(cut, log=quiet, up=4):
    """Stripes from the straightened sequence and the garment's yarn colours: the folded repeat when the
    stripes repeat, else the whole sequence. Returns dict(orientation, bands=[(hex, fraction)], yarns) or None."""
    rgb = np.asarray(cut.convert("RGB"))
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    m = mask_of(cut)
    way, ratio = orientation(lab, m)
    lab_o, m_o = (lab.transpose(1, 0, 2), m.T) if way == "vertical" else (lab, m)
    logs = []
    res = straightened_sequence(lab_o, m_o, log=logs.append)
    if res is None:
        return None
    seq, y0, y1 = res
    yarns = yarn_colours(cut)
    # colours the stripe sequence itself shows that no yarn colour is close to (a pink band too small a share
    # of the whole garment to make the palette): add them, so they are not snapped to a grey
    known_seq = seq[y0:y1 + 1][~np.isnan(seq[y0:y1 + 1, 0])]
    far = known_seq[np.min(np.linalg.norm((known_seq[:, None] - yarns[None]) * _W, axis=2), 1) > 14]
    if len(far) >= 3:
        k = min(3, max(1, len(far) // 4))
        cv2.setRNGSeed(0)
        _, _, extra = cv2.kmeans(far.astype(np.float32), k, None, (3, 30, 0.5), 3, cv2.KMEANS_PP_CENTERS)
        yarns = np.vstack([yarns, extra]).astype(np.float32)
    lag = _repeat_from_logs(logs)

    def nearest(cols):
        d = np.linalg.norm((cols[:, None] - yarns[None]) * _W, axis=2)
        return np.argmin(d, 1)
    if lag:
        known = np.where(~np.isnan(seq[:, 0]))[0]
        a, b = known.min(), known.max()
        L = refine_repeat(seq, lag, a, b)
        rep = folded_repeat(seq, L, a, b, up=up)
        nb = len(rep)
        lbl = clean_runs(nearest(rep), min_len=max(2, up // 2))
        n_str = len([1 for i in range(nb) if lbl[i] != lbl[i - 1]])
        log(f"  stripes run {'across' if way == 'horizontal' else 'down'}; repeat {L:.2f} px with {n_str} stripes; "
            f"{len(yarns)} yarn colours")
        ys = np.arange(y0, y1 + 1, 1.0 / up)
        idx = lbl[(np.floor(((ys - a) % L) / L * nb).astype(int)) % nb]
        step = 1.0 / up
    else:
        sub = seq[y0:y1 + 1].copy()
        kn = ~np.isnan(sub[:, 0])
        pos = np.arange(len(sub))
        for c in range(3):
            sub[:, c] = np.interp(pos, pos[kn], sub[kn, c])
        idx = clean_runs(nearest(sub), min_len=2)
        log(f"  stripes run {'across' if way == 'horizontal' else 'down'}; no repeat, the whole sequence is used; "
            f"{len(yarns)} yarn colours")
        step = 1.0
    hexes = _hexes(yarns)
    bands = []
    for i in idx:
        if bands and bands[-1][0] == hexes[i]:
            bands[-1][1] += step
        else:
            bands.append([hexes[i], step])
    total = sum(n for _, n in bands)
    return dict(orientation=way, bands=[(h, n / total) for h, n in bands], yarns=hexes)


def fold_by_phase(cut, L, way, up=4, log=quiet):
    """Fold every garment pixel onto one repeat of regular stripes, using the local position of the stripes
    read from the photo itself: the phase of the stripe spacing's wave at each point (complex demodulation).
    Phase only matters within one repeat, so nothing has to be joined across the garment.
    Returns (the repeat in Lab at `up` slots per px, each pixel's position in the repeat, the pixels used)."""
    rgb = np.asarray(cut.convert("RGB"))
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    m = mask_of(cut)
    if way == "horizontal":                     # make the stripes run down the image: the wave runs across x
        lab, m = lab.transpose(1, 0, 2), m.T
    H, W = m.shape
    s = np.zeros((H, W), np.float32)
    for c in range(3):
        ch = lab[..., c]
        s += (ch - ch[m].mean()) / (ch[m].std() + 1e-3)
    s = np.where(m, s, 0)
    xx = np.arange(W, dtype=np.float32)[None, :]
    w = 2 * np.pi / L
    re, im = s * np.cos(w * xx), -s * np.sin(w * xx)
    sx, sy = min(max(1.0, 1.5 * L), 24.0), min(max(3.0, 4.0 * L), 40.0)   # capped: big blurs are slow

    def blur(a):
        return cv2.GaussianBlur(a, (0, 0), sigmaX=sx, sigmaY=sy)
    mb = blur(m.astype(np.float32))
    re, im = blur(re) / np.maximum(mb, 1e-3), blur(im) / np.maximum(mb, 1e-3)
    amp = np.hypot(re, im)
    theta = np.arctan2(im, re)                 # the stripes are shifted by theta / w at this point
    use = m & (mb > 0.9) & (amp > np.percentile(amp[m], 40))
    u = (xx + theta / w) % L   # position within one repeat (z ~ e^(-i w x0): theta = -w x0, so x - x0 = x + theta / w)
    nb = max(8, int(round(L * up)))
    bins = (np.floor(u[use] / L * nb).astype(int)) % nb
    vals = lab[use]
    rep = np.full((nb, 3), np.nan, np.float32)
    order = np.argsort(bins, kind="stable")
    bs, vs = bins[order], vals[order]
    starts = np.searchsorted(bs, np.arange(nb))
    ends = np.searchsorted(bs, np.arange(nb), side="right")
    for k in range(nb):
        if ends[k] - starts[k] > 3:
            rep[k] = np.median(vs[starts[k]:ends[k]], 0)
    for c in range(3):
        bad = np.isnan(rep[:, c])
        if bad.any() and (~bad).any():
            idx = np.arange(nb)
            rep[bad, c] = np.interp(idx[bad], idx[~bad], rep[~bad, c], period=nb)
    log(f"  folded {int(use.sum())} pixels onto one {L:.2f} px repeat")
    return rep, u, use


def choose_repeat(cut, lag, way, log=quiet):
    """The repeat length that folds the photo most sharply: the first estimate, half and a third of it, each
    tried at nearby lengths. A repeat folds sharply at twice its length too, so the shortest one that folds
    (nearly) as sharply as the best is kept."""
    tried = []
    for base in (lag / 3, lag / 2, lag):
        if base < 3:
            continue
        for L in np.linspace(base * 0.94, base * 1.06, 7):
            rep, _, _ = fold_by_phase(cut, L, way, up=2)
            tried.append((float(rep.std(0).sum()), L))
    top = max(s for s, _ in tried)
    L = min(L for s, L in tried if s >= 0.97 * top)
    # fine-tune around it
    fine = [(float(fold_by_phase(cut, x, way, up=2)[0].std(0).sum()), x)
            for x in np.linspace(L * 0.985, L * 1.015, 7)]
    return max(fine)[1]


def _signal(lab, m):
    s = np.zeros(lab.shape[:2], np.float32)
    for c in range(3):
        ch = lab[..., c]
        s += (ch - ch[m].mean()) / (ch[m].std() + 1e-3)
    return np.where(m, s, 0).astype(np.float32)


def fold_by_match(cut, L, way, ref_rep=None, iters=3, up=4, win_h=None, log=quiet):
    """Fold every garment pixel onto one repeat, finding the stripes' position area by area by matching each
    area's profile against the whole repeat (every stripe in it, to a fraction of a pixel). Only the position
    within one repeat matters, so areas are combined as directions on a circle and nothing has to be joined.
    Returns (the repeat in Lab, each pixel's position in it, the pixels used) or None."""
    rgb = np.asarray(cut.convert("RGB"))
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    m = mask_of(cut)
    if way == "horizontal":
        lab, m = lab.transpose(1, 0, 2), m.T
    H, W = m.shape
    sig = _signal(lab, m)
    win_w = int(np.ceil(1.5 * L))
    win_h = win_h or max(8, int(1.5 * L))
    nb = max(8, int(round(L * up)))
    if ref_rep is None:
        # start from the straightened sequence folded onto the repeat (crisp where strips lined up)
        lab_o, m_o = (cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32), mask_of(cut))
        if way == "vertical":
            lab_o, m_o = lab_o.transpose(1, 0, 2), m_o.T
        res = straightened_sequence(lab_o, m_o)
        seq = res[0]
        known = np.where(~np.isnan(seq[:, 0]))[0]
        ref_rep = folded_repeat(seq, L, known.min(), known.max(), up=up)
    for it in range(iters):
        # the reference as a signal profile over one repeat, sampled every 1/up px
        rp = ref_rep.copy()
        ref_sig = np.zeros(len(rp), np.float32)
        for c in range(3):
            ch = lab[..., c][m]
            ref_sig += (rp[:, c] - ch.mean()) / (ch.std() + 1e-3)
        sy, sx = max(4, win_h // 2), max(2, int(L / 3))
        cy, cx, ph, wt = [], [], [], []
        Fr = np.fft.fft(ref_sig - ref_sig.mean())
        for y0 in range(0, H - win_h, sy):
            for x0 in range(0, W - win_w, sx):
                wm = m[y0:y0 + win_h, x0:x0 + win_w]
                if wm.mean() < 0.9:
                    continue
                prof = sig[y0:y0 + win_h, x0:x0 + win_w].mean(0)
                # resample the window profile onto the repeat's grid (1/up px), wrapping around the repeat
                # each repeat slot k sits at x = x0 + ((k/nb*L - x0) mod L) in this window: interpolate there
                slot_x = x0 + ((np.arange(nb) / nb * L - x0) % L)
                f = np.interp(slot_x, x0 + np.arange(win_w), prof)
                f = f - f.mean()
                cc = np.real(np.fft.ifft(np.fft.fft(f) * np.conj(Fr)))
                k = int(np.argmax(cc))
                den = np.sqrt((f ** 2).sum() * ((ref_sig - ref_sig.mean()) ** 2).sum()) + 1e-6
                score = cc[k] / den
                if score < (0.3 if it == 0 else 0.5):
                    continue
                a_, b_, c_ = cc[k - 1], cc[k], cc[(k + 1) % nb]
                d = a_ - 2 * b_ + c_
                kf = k + (0.5 * (a_ - c_) / d if d < 0 else 0)
                # window content at repeat position p sits at reference position p - kf: shift in px
                cy.append(y0 + win_h / 2)
                cx.append(x0 + win_w / 2)
                ph.append(kf / nb * L)
                wt.append(score)
        if len(ph) < 10:
            log(f"  pass {it + 1}: too few areas matched ({len(ph)})")
            return None
        cy, cx, ph, wt = map(np.array, (cy, cx, ph, wt))
        # a smooth field of shifts: average unit vectors on the circle, weighted, over nearby areas
        z = wt * np.exp(2j * np.pi * ph / L)
        grid_y = np.arange(0, H, 8)
        grid_x = np.arange(0, W, 8)
        Zr = np.zeros((len(grid_y), len(grid_x)))
        Zi = np.zeros_like(Zr)
        Wg = np.zeros_like(Zr)
        iy = np.clip((cy / 8).astype(int), 0, len(grid_y) - 1)
        ix = np.clip((cx / 8).astype(int), 0, len(grid_x) - 1)
        np.add.at(Zr, (iy, ix), z.real)
        np.add.at(Zi, (iy, ix), z.imag)
        np.add.at(Wg, (iy, ix), wt)
        sgm = max(1.5, 1.2 * L / 8)
        Zr, Zi, Wg = (cv2.GaussianBlur(a.astype(np.float32), (0, 0), sgm) for a in (Zr, Zi, Wg))
        shift = np.angle(Zr + 1j * Zi) / (2 * np.pi) * L
        known = Wg > 0.05 * Wg.max()
        # interpolating angles linearly across the wrap would be wrong, so nearest is used at 8 px
        full = cv2.resize(shift.astype(np.float32), (W, H), interpolation=cv2.INTER_NEAREST)
        kn = cv2.resize(known.astype(np.uint8), (W, H), interpolation=cv2.INTER_NEAREST).astype(bool)
        xx = np.arange(W, dtype=np.float32)[None, :]
        u = (xx - full) % L
        use = m & kn
        bins = np.floor(u[use] / L * nb).astype(int) % nb
        vals = lab[use]
        order = np.argsort(bins, kind="stable")
        bs, vs = bins[order], vals[order]
        st = np.searchsorted(bs, np.arange(nb))
        en = np.searchsorted(bs, np.arange(nb), side="right")
        rep = np.full((nb, 3), np.nan, np.float32)
        for k in range(nb):
            if en[k] - st[k] > 3:
                rep[k] = np.median(vs[st[k]:en[k]], 0)
        for c in range(3):
            bad = np.isnan(rep[:, c])
            if bad.any() and (~bad).any():
                idx = np.arange(nb)
                rep[bad, c] = np.interp(idx[bad], idx[~bad], rep[~bad, c], period=nb)
        log(f"  pass {it + 1}: {len(ph)} areas matched (median {np.median(wt):.2f}), {int(use.sum())} pixels folded")
        ref_rep = rep
    return rep, u, use


def measure4(cut, log=quiet, up=4):
    """Regular stripes: fold by matching into one sharp repeat, then crisp bands from the yarn colours.
    Stripes with no repeat (a placed chest band): the straightened sequence (`measure3`).
    Returns dict(orientation, bands=[(hex, fraction of the garment)], yarns=[hex], rep, lbl) or None."""
    rgb = np.asarray(cut.convert("RGB"))
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    m = mask_of(cut)
    way, _ = orientation(lab, m)
    lab_o, m_o = (lab.transpose(1, 0, 2), m.T) if way == "vertical" else (lab, m)
    logs = []
    res = straightened_sequence(lab_o, m_o, log=logs.append)
    if res is None:
        return None
    lag = _repeat_from_logs(logs)
    if not lag:
        return measure3(cut, log=log)
    # repeat length: the fast fold's pick and the first estimate, each refined, judged by the precise fold
    cands = sorted({round(choose_repeat(cut, lag, way, log=log), 2), float(lag)})
    scored = []
    for c0 in cands:
        for c in (c0 * 0.99, c0, c0 * 1.01):
            res_c = fold_by_match(cut, c, way, iters=2, up=up)
            if res_c is not None:
                scored.append((float(res_c[0].std(0).sum()), c, res_c))
    top = max(sc for sc, _, _ in scored)
    _, L, (rep, u, use) = min(((sc, c, r) for sc, c, r in scored if sc >= 0.97 * top), key=lambda t: t[1])
    log(f"  repeat {L:.2f} px chosen from {', '.join(f'{c:.2f}' for c in cands)}")
    nb = len(rep)
    # yarn colours from the sharp repeat itself. A real yarn makes stripes at least about a pixel wide; the
    # blend at the edge between two stripes is only ever a sliver. So: cluster generously, keep the clusters
    # that form a run of at least `up` slots (one photo pixel) somewhere, merge near-identical ones, and give
    # every slot the nearest kept colour.
    cv2.setRNGSeed(0)
    _, lbl6, cen6 = cv2.kmeans(rep.astype(np.float32), 6, None, (3, 50, 0.1), 5, cv2.KMEANS_PP_CENTERS)
    lbl6 = lbl6.ravel()
    longest = {}
    shift = next((i for i in range(nb) if lbl6[i] != lbl6[i - 1]), 0)
    seqv = np.roll(lbl6, -shift)
    s0 = 0
    for i in range(1, nb + 1):
        if i == nb or seqv[i] != seqv[s0]:
            longest[int(seqv[s0])] = max(longest.get(int(seqv[s0]), 0), i - s0)
            s0 = i
    keep = [k for k in range(len(cen6)) if longest.get(k, 0) >= max(3, up)]
    if len(keep) < 2:
        keep = sorted(longest, key=lambda k: -longest[k])[:2]
    merged = True
    while merged and len(keep) > 2:
        merged = False
        for a in keep:
            for b in keep:
                if a < b and np.linalg.norm(cen6[a] - cen6[b]) < 8:
                    keep.remove(b if longest[b] < longest[a] else a)
                    merged = True
                    break
            if merged:
                break
    pure = np.array([cen6[k] for k in keep], np.float32)
    lbl = np.argmin(np.linalg.norm((rep[:, None] - pure[None]) * _W, axis=2), 1)
    lbl = clean_runs(lbl, min_len=max(2, up // 2))
    edge = (lbl != np.roll(lbl, 1)) | (lbl != np.roll(lbl, -1))
    cols = []
    for k in range(len(pure)):
        sel = (lbl == k) & ~edge
        if not sel.any():
            sel = lbl == k
        cols.append(np.median(rep[sel], 0) if sel.any() else pure[k])
    cols = np.array(cols, np.float32)
    n_str = int((lbl != np.roll(lbl, 1)).sum())
    log(f"  stripes run {'across' if way == 'horizontal' else 'down'}; repeat {L:.2f} px, {n_str} stripes in it, "
        f"{len(pure)} colours")
    # lay out over the garment span, with the phase measured at the garment's starting edge
    if way == "horizontal":
        span_axis = np.where(m.any(1))[0]
    else:
        span_axis = np.where(m.any(0))[0]
    a0, a1 = span_axis.min(), span_axis.max()
    # where repeats start, in photo coordinates (u = position within the repeat; along the span axis u grows
    # with the coordinate)
    coords = np.arange(u.shape[1])[None, :].repeat(u.shape[0], 0)
    off = np.median(((coords - u)[use]) % L)
    ys = np.arange(a0, a1 + 1, 1.0 / up)
    idx = lbl[(np.floor(((ys - off) % L) / L * nb).astype(int)) % nb]
    hexes = _hexes(cols)
    bands = []
    for i in idx:
        if bands and bands[-1][0] == hexes[i]:
            bands[-1][1] += 1
        else:
            bands.append([hexes[i], 1])
    total = sum(n for _, n in bands)
    return dict(orientation=way, bands=[(h, n / total) for h, n in bands], yarns=hexes, rep=rep, lbl=lbl)


_TARGETS = {"white": (246, 246, 244), "cream": (238, 232, 214)}


def _lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _unlin(c):
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.power(np.clip(c, 0, None), 1 / 2.4) - 0.055)


def balance_to_words(result, words):
    """Correct the photo's lighting from the colour words Claude gave the item: when it says the item has
    white (or cream), the lightest neutral yarn is that colour, and every yarn gets the same correction
    (per channel, in linear light, within limits), so the other colours shift with it.
    Returns (the corrected result, (the yarn taken as white, the word, the gains)) or (result, None)."""
    word = next((w for w in ("white", "cream") if w in words), None)
    if not word:
        return result, None
    hexes = result["yarns"]
    rgb = np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in hexes], float)
    lab = cv2.cvtColor(rgb[None].astype(np.uint8), cv2.COLOR_RGB2LAB)[0].astype(float)
    chroma = np.hypot(lab[:, 1] - 128, lab[:, 2] - 128)
    neutral = [i for i in range(len(hexes)) if chroma[i] < 14]
    if not neutral:
        return result, None
    w = max(neutral, key=lambda i: lab[i, 0])
    raw = _lin(np.array(_TARGETS[word]) / 255) / np.maximum(_lin(rgb[w] / 255), 1e-4)
    # brightness is corrected freely (within 0.8 to 1.6); the balance between channels only a little (8%),
    # so a "white" that is really a blend with a coloured stripe cannot drain the colour from everything
    level = float(np.clip(np.exp(np.log(raw).mean()), 0.8, 1.6))
    tilt = np.clip(raw / np.exp(np.log(raw).mean()), 0.92, 1.08)
    gain = level * tilt
    new = np.clip(_unlin(_lin(rgb / 255) * gain) * 255, 0, 255)
    mapping = {h: "#{:02x}{:02x}{:02x}".format(*(int(round(v)) for v in c)) for h, c in zip(hexes, new, strict=True)}
    out = dict(result)
    out["yarns"] = [mapping[h] for h in hexes]
    out["bands"] = [(mapping.get(h, h), f) for h, f in result["bands"]]
    return out, (hexes[w], word, np.round(gain, 2).tolist())


def ground_region(seq, y0, y1, min_frac=0.12):
    """For placed stripes: the longest stretch of the sequence that is plain ground (low colourfulness, judged
    against the garment's own colourful bands). Returns (a, b) positions or None."""
    s = seq[y0:y1 + 1]
    ok = ~np.isnan(s[:, 0])
    chroma = np.where(ok, np.hypot(s[:, 1] - 128, s[:, 2] - 128), np.nan)
    k = max(3, int(0.03 * len(s)))
    sm = np.array([np.nanmean(chroma[max(0, i - k):i + k + 1]) if ok[max(0, i - k):i + k + 1].any() else np.nan
                   for i in range(len(s))])
    lim = np.nanpercentile(sm, 35) * 1.35
    plain = ok & (sm <= lim)
    best, start = None, None
    for i in range(len(s) + 1):
        if i < len(s) and plain[i]:
            start = i if start is None else start
        elif start is not None:
            if best is None or i - start > best[1] - best[0]:
                best = (start, i)
            start = None
    if best is None or best[1] - best[0] < min_frac * len(s):
        return None
    return y0 + best[0], y0 + best[1]


def ground_stripes(cut, log=quiet, up=4):
    """The repeating ground of placed stripes (the cloth a polo's collar is cut from), and the region it was
    measured in. Folded from that region only, by matching, so fine stripes come out sharp.
    Returns dict(orientation, bands=[(hex, fraction of the garment)] for one repeat, region, L, rep, lbl,
    hexes) or None."""
    rgb = np.asarray(cut.convert("RGB"))
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    m = mask_of(cut)
    way, _ = orientation(lab, m)
    lab_o, m_o = (lab.transpose(1, 0, 2), m.T) if way == "vertical" else (lab, m)
    res = straightened_sequence(lab_o, m_o)
    if res is None:
        return None
    seq, y0, y1 = res
    reg = ground_region(seq, y0, y1)
    if reg is None:
        return None
    a, b = reg
    sub = seq[a:b].copy()
    # the ground's repeat: autocorrelation of the plain stretch
    x = sub - np.nanmean(sub, 0)
    x = np.nan_to_num(x)
    n = len(x)
    best = None
    for lag in range(3, n // 2):
        u, v = x[:-lag], x[lag:]
        r = (u * v).sum() / (np.sqrt((u ** 2).sum() * (v ** 2).sum()) + 1e-6)
        if lag > 3 and r > 0.4 and (best is None or r > best[1] + 0.05):
            best = (lag, r)
            if r > 0.75:
                break
    if best is None:
        return None
    # fold only the ground region: hide the rest of the garment
    a_img = np.asarray(cut).copy()
    if way == "horizontal":
        a_img[:a, :, 3] = 0
        a_img[b:, :, 3] = 0
    else:
        a_img[:, :a, 3] = 0
        a_img[:, b:, 3] = 0
    gcut = Image.fromarray(a_img, "RGBA")
    scored = []
    for L in np.linspace(best[0] * 0.9, best[0] * 1.1, 9):
        r_ = fold_by_match(gcut, L, way, iters=2, up=up)
        if r_ is not None:
            scored.append((float(r_[0].std(0).sum()), L, r_[0]))
    if not scored:
        return None
    _, L, rep = max(scored, key=lambda t: t[0])
    # stripes this fine are blurred together in the photo: the fold gives their spacing and widths, but the
    # colours are taken from the photo's own extremes in the ground (its darkest and lightest tenth)
    gm = np.asarray(gcut)[..., 3] > 200
    px = lab[gm]
    lum = px[:, 0]
    dark = np.median(px[lum <= np.percentile(lum, 10)], 0)
    light = np.median(px[lum >= np.percentile(lum, 90)], 0)
    mid = (rep[:, 0].min() + rep[:, 0].max()) / 2
    lbl = (rep[:, 0] > mid).astype(int)              # 1: ground, 0: stripe
    lbl = clean_runs(lbl, min_len=max(2, up // 2))
    hexes = _hexes(np.array([dark, light], np.float32))
    span = (y1 - y0 + 1)
    runs = []
    for i in lbl:
        if runs and runs[-1][0] == hexes[i]:
            runs[-1][1] += 1
        else:
            runs.append([hexes[i], 1])
    if len(runs) > 1 and runs[0][0] == runs[-1][0]:
        runs[0][1] += runs.pop()[1]
    nb = len(lbl)
    bands = [(h, k / nb * L / span) for h, k in runs]
    log(f"  ground: rows {a}-{b}, repeat {L:.2f} px, {len(bands)} stripes, colours {sorted({h for h, _ in bands})}")
    return dict(orientation=way, bands=bands, region=(a, b), L=L, rep=rep, lbl=lbl, hexes=hexes)


def compose_placed(cut, body, ground, log=quiet, step=0.25):
    """Placed stripes: every plain stretch of the body drawn with the crisp ground repeat, the placed bands
    with their measured colours. `body` and `ground` are results of measure4 and ground_stripes.
    Returns [(hex, fraction of the garment)] from the garment's start edge."""
    rgb = np.asarray(cut.convert("RGB"))
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    m = mask_of(cut)
    way = body["orientation"]
    lab_o, m_o = (lab.transpose(1, 0, 2), m.T) if way == "vertical" else (lab, m)
    seq, y0, y1 = straightened_sequence(lab_o, m_o)
    s = seq[y0:y1 + 1]
    ok = ~np.isnan(s[:, 0])
    chroma = np.where(ok, np.hypot(s[:, 1] - 128, s[:, 2] - 128), np.nan)
    k = max(2, int(0.015 * len(s)))
    sm = np.array([np.nanmean(chroma[max(0, i - k):i + k + 1]) if ok[max(0, i - k):i + k + 1].any() else np.nan
                   for i in range(len(s))])
    lim = np.nanpercentile(sm, 35) * 1.35
    plain = np.where(np.isnan(sm), True, sm <= lim)      # unknown ends (collar, hem) are ground cloth
    span = len(s)
    # the body's measured bands as a colour at each position
    edges = np.cumsum([0] + [f for _, f in body["bands"]]) * span

    # when measure4 found a repeat it folded the placed bands away, so its bands say nothing about them: a
    # band's colour is then read from the straightened sequence itself, as the nearest of the garment's colours
    from_seq = "rep" in body
    if from_seq:
        pal_hex = list(dict.fromkeys(list(body.get("yarns") or []) + list(ground["hexes"])))
        pal = _hex_to_lab(pal_hex)
        filled = s.copy()
        for c in range(3):
            filled[:, c] = np.interp(np.arange(span), np.where(ok)[0], s[ok, c]) if ok.any() else 128

    def body_at(y):
        if from_seq:
            c = filled[min(span - 1, int(y))]
            return pal_hex[int(np.argmin(np.linalg.norm((pal - c) * np.array([0.6, 1, 1]), axis=1)))]
        i = min(len(body["bands"]) - 1, int(np.searchsorted(edges, y, side="right") - 1))
        return body["bands"][max(0, i)][0]
    L, lbl, hexes = ground["L"], ground["lbl"], ground["hexes"]
    nb = len(lbl)
    a = ground["region"][0] - y0
    out = []
    for y in np.arange(0, span, step):
        if plain[min(span - 1, int(y))]:
            h = hexes[lbl[int(((y - a) % L) / L * nb) % nb]]
        else:
            h = body_at(y)
        if out and out[-1][0] == h:
            out[-1][1] += step
        else:
            out.append([h, step])
    log(f"  {int(plain.mean() * 100)}% of the length is plain ground; {len(out)} bands")
    return [(h, n / span) for h, n in out]


def _hex_to_lab(hs):
    rgb = np.array([[[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in hs]], np.uint8)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)[0].astype(np.float32)


def _chroma(c):
    return float(np.hypot(c[..., 1] - 128, c[..., 2] - 128))


def band_colours(body_yarns_hex, ground_hex, min_d=18.0):
    """The placed bands' own colours: the body's colours that no ground colour is close to.
    Returns (band colours in Lab or None, ground colours in Lab)."""
    b, g = _hex_to_lab(body_yarns_hex), _hex_to_lab(ground_hex)
    g_chroma = max(_chroma(c) for c in g)
    # a placed band is a colour of its own: far from every ground colour and clearly more colourful than the
    # ground (the body's palette also holds the greys of the ground's fine stripes, which are not bands)
    keep = [c for c in b if np.min(np.linalg.norm((g - c) * _W, axis=1)) > min_d
            and _chroma(c) > g_chroma + 10]
    return (np.array(keep, np.float32) if keep else None), g


def regions_from_landmarks(cut, lm, scale=1.0, edge_frac=0.06):
    """Body and sleeves from Claude's shoulder and underarm points: a sleeve is the garment beyond the line from
    its shoulder point to its underarm point. Each underarm point must sit at the garment's outline (within
    edge_frac of its width of the background, at that height), or the answer is not trusted: None.
    `lm` holds shoulder_left/right and underarm_left/right as {x, y}; `scale` turns them into the cutout's
    pixels. Returns (body mask, sleeves mask) or None."""
    m = mask_of(cut, thresh=128)
    H, W = m.shape
    gw = np.ptp(np.where(m.any(0))[0])

    def point(k):
        return lm[k]["x"] * scale, lm[k]["y"] * scale
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    mu = m.astype(np.uint8)
    # how far each pixel is from the outline: inside, the distance to the background; outside, to the garment
    # (one of the two is always 0; the experiment took the smaller, which made every point pass)
    edge_dist = np.maximum(cv2.distanceTransform(mu, cv2.DIST_L2, 3), cv2.distanceTransform(1 - mu, cv2.DIST_L2, 3))
    body = m.copy()
    sleeves = np.zeros_like(m)
    for side in ("left", "right"):
        sx, sy = point(f"shoulder_{side}")
        ux, uy = point(f"underarm_{side}")
        outward = -1 if side == "left" else 1
        iy, ix = int(min(H - 1, max(0, uy))), int(min(W - 1, max(0, ux)))
        if edge_dist[iy, ix] > edge_frac * gw:   # an underarm point lies on the outline, not inside the cloth
            return None
        # the sleeve: beyond the line from the shoulder point to the underarm point (between their heights),
        # and beyond the underarm point's side line below it (a long sleeve hanging beside the body)
        t = np.clip((yy - sy) / max(1e-6, uy - sy), 0, 1)
        x_line = np.where(yy < uy, sx + t * (ux - sx), ux)
        sel = m & (yy >= sy) & (outward * (xx - x_line) > 0)
        sleeves |= sel
    body &= ~sleeves
    return body, sleeves


def sleeves_carry_bands(cut, band_lab, ground_lab, regions, near=14.0, log=quiet, ratio=0.6):
    """Whether placed bands continue onto the sleeves: the share of sleeve pixels nearer a band colour than any
    ground colour, against the same share on the body; they continue when the sleeves carry at least `ratio` of
    the body's share (a band edge leaking into a slightly misplaced sleeve region stays well under). `regions`
    is (body, sleeves) from regions_from_landmarks; None (landmarks not trusted) gives None: not known."""
    if regions is None:
        return None
    body, sleeves = regions
    if sleeves.sum() < 200 or body.sum() < 200:
        return None
    lab = cv2.cvtColor(np.asarray(cut.convert("RGB")), cv2.COLOR_RGB2LAB).astype(np.float32)
    w = np.array([0.6, 1, 1])

    def share(sel):
        px = lab[sel]
        db = np.min(np.linalg.norm((px[:, None] - band_lab[None]) * w, axis=2), 1)
        dg = np.min(np.linalg.norm((px[:, None] - ground_lab[None]) * w, axis=2), 1)
        return float(((db < dg) & (db < near)).mean())
    sb, ss = share(body), share(sleeves)
    log(f"  band colours: {sb:.1%} of the body, {ss:.1%} of the sleeves")
    return ss >= ratio * sb
