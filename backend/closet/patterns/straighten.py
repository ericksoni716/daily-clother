"""A plaid photographed at an angle, turned, or lying over a slope, made regular again from its own lines.

`plaid.period` and `flatten` expect cloth seen straight on: the checks the same size all over and running
along the photo's rows and columns. A photo taken from the foot of a bed has checks half as big again at the
hem as at the collar; a garment laid at a slant has them running corner to corner. Here the cloth itself says
how it lies, in three steps, each using only what the one before could not:

1. `by_lines`: a plaid's lines run two ways. In the photo each family of lines points at one spot (its
   vanishing point); the two spots give the tilt of the cloth, which is undone, and the lines are turned to
   run along the rows and columns.
2. `repeat`: the repeat's size, read area by area (so a sleeve at another angle, a pocket or a fold is one
   voice among many) and taken as the middle of what the areas say.
3. `by_repeat`: the repeat measured in every area, and one smooth map fitted through all of them that makes it
   the same size everywhere (cloth over a hanger or a duvet is not flat, so a tilt alone does not do it).

`regular` runs the three and then asks whether the repeat is really twice as long: a white line over every
other check (an overcheck) repeats at twice the checks' spacing, and a repeat finder that goes by the broad
bands alone loses it.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

from .common import autocorr, lab_to_rgb, quiet, soft, to_lab

SPREAD = 22        # how far (degrees) an area's lines may lean from the garment's own two directions
MIN_AREAS = 6      # fewer areas than this say too little to fit anything through
VISIBLE = 3.5      # a difference between the two halves of a doubled repeat this big (delta E) can be seen


@dataclass
class Regular:
    """A cutout made regular: `cut` (RGBA) with the repeat `P` x `Q` px along its rows and columns, `to_new`
    taking points (N x 2, in the original cutout's pixels) to their place in it, and `ref`, the whole garment
    folded onto one repeat (Lab), a first reference for `flatten`."""
    cut: Image.Image
    P: int
    Q: int
    to_new: object
    ref: np.ndarray
    steps: tuple[str, ...]


# --- 1. the tilt and the turn, from which way the lines run ---------------------------------------------------

def _gradients(light, m):
    g = cv2.GaussianBlur(light, (0, 0), 1.2)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    return np.where(m, np.hypot(gx, gy), 0), np.degrees(np.arctan2(gy, gx)) % 180.0


def _directions(mag, ang, bins=360):
    """How much edge there is across each direction (a histogram round the half circle, smoothed)."""
    h = np.bincount((ang * bins / 180).astype(int).ravel() % bins, weights=(mag ** 2).ravel(), minlength=bins)
    k = np.exp(-0.5 * (np.arange(-8, 9) / 2.0) ** 2)
    return np.convolve(np.r_[h[-8:], h, h[:8]], k / k.sum(), "valid")


def _peak(h, lo, hi):
    """The strongest direction between lo and hi degrees: (degrees, how far it stands above the usual)."""
    bins = len(h)
    idx = np.arange(int(np.floor(lo * bins / 180)), int(np.ceil(hi * bins / 180)) + 1)
    v = h[idx % bins]
    i = int(np.argmax(v))
    if i in (0, len(v) - 1):
        return None
    a, b, c = v[i - 1], v[i], v[i + 1]
    d = a - 2 * b + c
    return (idx[i] + (0.0 if d >= 0 else 0.5 * (a - c) / d)) * 180 / bins, float(b / (np.median(h) + 1e-9))


def _pair(h):
    """The two directions, about a right angle apart, that hold the most edges in a histogram of directions:
    ((degrees, strength), (degrees, strength)) with the first below 90, or None."""
    bins = len(h)
    best = None
    for i in range(bins // 2 + 1):
        p1 = _peak(h, i * 180 / bins - 3, i * 180 / bins + 3)
        p2 = _peak(h, p1[0] + 65, p1[0] + 115) if p1 else None
        if p2 is None:
            continue
        s = h[int(round(p1[0] * bins / 180)) % bins] + h[int(round(p2[0] * bins / 180)) % bins]
        if best is None or s > best[0]:
            best = (s, p1, p2)
    return best and best[1:]


def _families(hists):
    """The garment's own two line directions, as most of its areas have them: each area with two clear
    directions votes for its pair, and the pair with the most votes wins. A duvet left in the cutout, a sleeve
    lying at another angle or a pocket's edge are outvoted, where one count over the whole garment lets them
    in. Returns the two directions in degrees, or None."""
    votes = np.zeros(90)
    for h in hists:
        pair = _pair(h)
        if pair is None or min(pair[0][1], pair[1][1]) < 2.0:
            continue
        votes[int(round(pair[0][0])) % 90] += min(pair[0][1], pair[1][1])
    if votes.sum() == 0:
        return None
    k = np.exp(-0.5 * (np.arange(-6, 7) / 2.0) ** 2)
    smooth = np.convolve(np.r_[votes[-6:], votes, votes[:6]], k, "valid")
    top = int(np.argmax(smooth))
    near = (np.arange(90) - top + 45) % 90 - 45
    sel = np.abs(near) <= 6
    if votes[sel].sum() < 0.4 * votes.sum():      # no one pair of directions that most areas share
        return None
    a = top + float((near[sel] * votes[sel]).sum() / votes[sel].sum())
    return a, a + 90.0


def _meeting_point(cx, cy, across, w):
    """Where lines through (cx, cy), each lying square to `across` degrees, meet: a point in homogeneous
    coordinates, far away when they are parallel. Areas that point elsewhere (a sleeve) count for little."""
    t = np.radians(across)
    n = np.stack([np.cos(t), np.sin(t)], 1)
    lines = np.c_[n, -(n[:, 0] * cx + n[:, 1] * cy)]
    wt, v, off = w.copy(), None, None
    for _ in range(8):
        v = np.linalg.svd(lines * wt[:, None])[2][-1]
        d = np.stack([v[0] - cx * v[2], v[1] - cy * v[2]], 1)
        d /= np.linalg.norm(d, axis=1, keepdims=True) + 1e-12
        off = np.abs((d * n).sum(1))                     # the sine of how far each line points from it
        wt = w / (1 + (off / (2 * max(1e-3, 1.4826 * np.median(off)))) ** 2)
    return v, off


def _mask(arr):
    m = arr[..., 3] > 128
    k = max(3, int(max(m.shape) * 0.01) | 1)
    return cv2.erode(m.astype(np.uint8), np.ones((k, k), np.uint8)).astype(bool)


def _size(m):
    ys, xs = np.where(m)
    return int(max(xs.max() - xs.min(), ys.max() - ys.min())) + 1


def by_lines(cut, log=quiet):
    """The 3 x 3 map (a homography, in the cutout's pixels) that undoes the photo's tilt and turns the plaid's
    lines along the rows and columns, with the size of the picture it fills; or None when the garment does not
    show two clear families of lines."""
    arr = np.asarray(cut)
    m = _mask(arr)
    if m.sum() < 400:
        return None
    H, W = m.shape
    mag, ang = _gradients(to_lab(arr[..., :3])[..., 0], m)
    size = _size(m)
    win = int(max(48, size / 6))
    areas = [(x0, y0) for y0 in range(0, H - win + 1, win // 3) for x0 in range(0, W - win + 1, win // 3)
             if m[y0:y0 + win, x0:x0 + win].mean() >= 0.8]
    hists = [_directions(mag[y0:y0 + win, x0:x0 + win], ang[y0:y0 + win, x0:x0 + win]) for x0, y0 in areas]
    fam = _families(hists)
    if fam is None:
        return None
    rows = []
    for (x0, y0), h in zip(areas, hists, strict=True):
        row = [x0 + win / 2, y0 + win / 2]
        for a in fam:
            p = _peak(h, a - SPREAD, a + SPREAD)
            row += [np.nan, 0.0] if p is None or p[1] < 2.0 else list(p)
        rows.append(row)
    loc = np.array(rows).reshape(-1, 6)
    sc = size / 2
    cx, cy = (loc[:, 0] - W / 2) / sc, (loc[:, 1] - H / 2) / sc
    points = []
    for k in (0, 1):
        ok = ~np.isnan(loc[:, 2 + 2 * k])
        if ok.sum() < MIN_AREAS:
            return None
        v, off = _meeting_point(cx[ok], cy[ok], loc[ok, 2 + 2 * k], np.sqrt(loc[ok, 3 + 2 * k]))
        log(f"  lines across {fam[k]:.0f} degrees: {int(ok.sum())} areas, {np.degrees(np.arcsin(np.median(off))):.1f} "
            "degrees off the fit")
        points.append(v)
    horizon = np.cross(points[0], points[1])
    if abs(horizon[2]) < 1e-9:
        return None
    horizon = horizon / horizon[2]
    if np.hypot(horizon[0], horizon[1]) > 0.8:     # the cloth is seen nearly edge on: nothing to measure
        log("  the cloth is tilted too far to straighten")
        return None
    flat = np.array([[1, 0, 0], [0, 1, 0], [horizon[0], horizon[1], 1.0]])

    def run(v):
        d = (flat @ v)[:2]
        return d / (np.linalg.norm(d) + 1e-12)
    down, along = run(points[0]), run(points[1])
    if abs(down[1]) < abs(along[1]):               # the family running more nearly up and down becomes the columns
        down, along = along, down
    down, along = down * np.sign(down[1] or 1), along * np.sign(along[0] or 1)
    turn = np.linalg.inv(np.stack([along, down], 1))
    turn /= np.sqrt(abs(np.linalg.det(turn)))
    square = np.eye(3)
    square[:2, :2] = turn
    centre = np.array([[1 / sc, 0, -W / 2 / sc], [0, 1 / sc, -H / 2 / sc], [0, 0, 1]])
    Hn = square @ flat @ centre
    ys, xs = np.where(m)
    step = max(1, len(xs) // 4000)
    q = Hn @ np.stack([xs[::step], ys[::step], np.ones(len(xs[::step]))], 0)
    if (q[2] <= 0.25).any():
        log("  the cloth is tilted too far to straighten")
        return None
    q = q[:2] / q[2] * sc
    x0, y0 = q[0].min() - 4, q[1].min() - 4
    Hp = np.array([[sc, 0, -x0], [0, sc, -y0], [0, 0, 1]]) @ Hn
    out = (int(np.ceil(q[0].max() - x0)) + 4, int(np.ceil(q[1].max() - y0)) + 4)
    if max(out) > 3 * max(H, W):
        return None
    lean = np.degrees(np.arctan2(turn[1, 0], turn[0, 0]))
    log(f"  the photo's tilt undone (horizon {horizon[0]:+.2f}, {horizon[1]:+.2f}) and the cloth turned {lean:+.1f} degrees")
    return Hp, out


def _apply(Hp, pts):
    p = np.c_[np.asarray(pts, float), np.ones(len(pts))] @ Hp.T
    return p[:, :2] / p[:, 2:3]


# --- 2. the repeat's size, as the middle of what many areas say -----------------------------------------------

def _near_axis(ac, n, across):
    """The autocorrelation along one axis, taking the best within a few pixels to either side (lines that are
    not quite level still count)."""
    out = np.zeros(n)
    for lag in range(1, n):
        t = 2 + lag // 12
        out[lag] = (ac[np.r_[0:t + 1, -t:0], lag] if across else ac[lag, np.r_[0:t + 1, -t:0]]).max()
    return out


def repeat(sig, m, log=quiet):
    """The repeat (across, down) in pixels of cloth whose lines run along the rows and columns, or None. Each
    is the spacing at which most areas of the garment agree best with themselves. Areas of three sizes are
    asked: an area must hold two repeats to show one, so small areas miss a large repeat, and large areas are
    few and take in sleeves and pockets."""
    H, W = m.shape
    size = _size(m)
    peaks = ([], [])
    asked = 0
    for part in (3.5, 2.5, 1.8):
        win = int(size / part)
        places = [(mm.mean(), x0, y0) for y0 in range(0, H - win + 1, max(8, win // 3))
                  for x0 in range(0, W - win + 1, max(8, win // 3)) for mm in (m[y0:y0 + win, x0:x0 + win],)]
        full = [p for p in places if p[0] >= 0.9]
        if len(full) < 3:        # a small garment: areas mostly on it will do (only its own pixels are compared)
            full = [p for p in places if p[0] >= 0.7]
        if len(full) < 2:
            continue
        curves = ([], [])
        for _, x0, y0 in full:
            ac = autocorr(sig[y0:y0 + win, x0:x0 + win], m[y0:y0 + win, x0:x0 + win])[0]
            curves[0].append(_near_axis(ac, win // 2, True))
            curves[1].append(_near_axis(ac, win // 2, False))
        asked = max(asked, len(curves[0]))
        for k in (0, 1):
            c = np.median(curves[k], 0)
            peaks[k].extend((lag, float(c[lag])) for lag in range(6, len(c) - 1)
                            if c[lag] > c[lag - 1] and c[lag] >= c[lag + 1])
    out = []
    for found in peaks:
        top = max((v for _, v in found), default=0)
        # the spacing the areas agree on most; a shorter one only when it is as good (a plaid's bands often look
        # alike at a half or a third of the repeat, a little less well)
        out.append(next((lag for lag, v in sorted(found) if v >= max(0.2, 0.9 * top)), None))
    if not (out[0] and out[1]):
        return None
    log(f"  repeat about {out[0]} x {out[1]} px, from up to {asked} areas")
    return out[0], out[1]


# --- 3. one smooth map that makes the repeat the same size everywhere -----------------------------------------

def _local_repeats(sig, m, P, Q):
    """In each area, the plaid's own two steps: one repeat across (about (P, 0)) and one down (about (0, Q)),
    to a fraction of a pixel. Rows of (x, y, across dx, dy, score, down dx, dy, score); NaN where not found."""
    H, W = m.shape
    win = int(min(max(4 * max(P, Q), 64), _size(m) / 2.2))
    rows = []

    def step(ac, px, py, r):
        ys = np.arange(py - r, py + r + 1)
        xs = np.arange(px - r, px + r + 1)
        box = ac[np.ix_(ys % ac.shape[0], xs % ac.shape[1])]
        i, j = np.unravel_index(np.argmax(box), box.shape)
        if box[i, j] < 0.2 or i in (0, 2 * r) or j in (0, 2 * r):
            return [np.nan, np.nan, 0.0]

        def fine(a, b, c):
            d = a - 2 * b + c
            return 0.0 if d >= 0 else 0.5 * (a - c) / d
        return [xs[j] + fine(box[i, j - 1], box[i, j], box[i, j + 1]),
                ys[i] + fine(box[i - 1, j], box[i, j], box[i + 1, j]), float(box[i, j])]
    for y0 in range(0, H - win + 1, max(8, win // 3)):
        for x0 in range(0, W - win + 1, max(8, win // 3)):
            mm = m[y0:y0 + win, x0:x0 + win]
            if mm.mean() < 0.85:
                continue
            ac = autocorr(sig[y0:y0 + win, x0:x0 + win], mm)[0]
            rows.append([x0 + win / 2, y0 + win / 2] + step(ac, P, 0, max(3, int(0.28 * P)))
                        + step(ac, 0, Q, max(3, int(0.28 * Q))))
    return np.array(rows).reshape(-1, 8)


class _Map:
    """u, v (in repeats) as smooth functions of the place in the picture: second-degree polynomials, fitted so
    that one measured step across is one in u and none in v, and one step down is one in v and none in u."""

    def __init__(self, centre, scale, cu, cv_):
        self.c, self.s, self.cu, self.cv = centre, scale, cu, cv_

    @staticmethod
    def _slopes(xn, yn, flat):
        z, o = np.zeros_like(xn), np.ones_like(xn)
        if flat:
            return np.stack([o, z], -1), np.stack([z, o], -1)
        return np.stack([o, z, 2 * xn, yn, z], -1), np.stack([z, o, z, xn, 2 * yn], -1)

    @classmethod
    def fit(cls, loc, centre, scale, flat=False):
        xn, yn = (loc[:, 0] - centre[0]) / scale, (loc[:, 1] - centre[1]) / scale
        dx, dy = cls._slopes(xn, yn, flat)
        rows, to_u, to_v, w = [], [], [], []
        for k, (tu, tv) in ((2, (1.0, 0.0)), (5, (0.0, 1.0))):
            ok = ~np.isnan(loc[:, k])
            rows.append((loc[ok, k, None] * dx[ok] + loc[ok, k + 1, None] * dy[ok]) / scale)
            to_u.append(np.full(ok.sum(), tu))
            to_v.append(np.full(ok.sum(), tv))
            w.append(loc[ok, k + 2])
        A, w = np.concatenate(rows), np.concatenate(w)
        coefs = []
        for target in (np.concatenate(to_u), np.concatenate(to_v)):
            wt = w.copy()
            for _ in range(6):       # areas that disagree with the rest (a pocket, a sleeve) count for little
                c = np.linalg.lstsq(A * wt[:, None], target * wt, rcond=None)[0]
                res = np.abs(A @ c - target)
                wt = w / (1 + (res / (2 * max(0.01, 1.4826 * np.median(res)))) ** 2)
            coefs.append(c if not flat else np.r_[c, 0, 0, 0])
        return cls(centre, scale, *coefs)

    def uv(self, xn, yn):
        b = np.stack([xn, yn, xn * xn, xn * yn, yn * yn], -1)
        return b @ self.cu, b @ self.cv

    def jac(self, xn, yn):
        dx, dy = self._slopes(xn, yn, False)
        return dx @ self.cu, dy @ self.cu, dx @ self.cv, dy @ self.cv

    def at(self, pts):
        pts = np.asarray(pts, float)
        return np.stack(self.uv((pts[:, 0] - self.c[0]) / self.s, (pts[:, 1] - self.c[1]) / self.s), 1)

    def steady(self, pts):
        """Does the map keep its sense and a sensible size over these points (it must not fold over)?"""
        a, b, c, d = self.jac((pts[:, 0] - self.c[0]) / self.s, (pts[:, 1] - self.c[1]) / self.s)
        det = a * d - b * c
        mid = np.median(det)
        return mid > 0 and det.min() > 0.3 * mid and det.max() < 3.5 * mid

    def back(self, u, v, rounds=8):
        """The place in the picture that maps to (u, v), by Newton's method from the map's straight part."""
        lin = np.linalg.inv(np.array([[self.cu[0], self.cu[1]], [self.cv[0], self.cv[1]]]))
        xn, yn = lin[0, 0] * u + lin[0, 1] * v, lin[1, 0] * u + lin[1, 1] * v
        for _ in range(rounds):
            fu, fv = self.uv(xn, yn)
            a, b, c, d = self.jac(xn, yn)
            det = a * d - b * c
            det = np.where(np.abs(det) < 1e-6, 1e-6, det)
            eu, ev = fu - u, fv - v
            xn = np.clip(xn - (d * eu - b * ev) / det, -6, 6)
            yn = np.clip(yn - (a * ev - c * eu) / det, -6, 6)
        return xn * self.s + self.c[0], yn * self.s + self.c[1]


def by_repeat(sig, m, P, Q, log=quiet):
    """The smooth map that makes the repeat the same size all over, with that size: (map, P, Q), or None when
    too few areas show the repeat."""
    loc = _local_repeats(sig, m, P, Q)
    seen = [int((~np.isnan(loc[:, k])).sum()) for k in (2, 5)] if len(loc) else [0, 0]
    if min(seen) < MIN_AREAS:
        log(f"  the repeat shows in too few areas ({seen[0]} across, {seen[1]} down)")
        return None
    ys, xs = np.where(m)
    step = max(1, len(xs) // 5000)
    pts = np.stack([xs[::step], ys[::step]], 1).astype(float)
    centre, scale = (float(xs.mean()), float(ys.mean())), _size(m) / 2
    fitted = _Map.fit(loc, centre, scale)
    if not fitted.steady(pts):
        fitted = _Map.fit(loc, centre, scale, flat=True)
        if not fitted.steady(pts):
            return None
    across = np.hypot(loc[:, 2], loc[:, 3])
    down = np.hypot(loc[:, 5], loc[:, 6])
    P0, Q0 = int(round(float(np.nanmedian(across)))), int(round(float(np.nanmedian(down))))
    log(f"  the repeat measured in {seen[0]} and {seen[1]} areas: {np.nanmin(across):.0f} to {np.nanmax(across):.0f} px "
        f"across, {np.nanmin(down):.0f} to {np.nanmax(down):.0f} px down; evened out to {P0} x {Q0}")
    return fitted, P0, Q0


# --- the two together, and the repeat's true length -----------------------------------------------------------

def _delta_e(lab_a, lab_b):
    d = lab_a - lab_b
    return np.sqrt((d[..., 0] * (100 / 255)) ** 2 + d[..., 1] ** 2 + d[..., 2] ** 2)


def _halves_differ(lab, m, P, Q, across):
    """Is the repeat really two of these (2P across, or 2Q down)? Each small area of the garment, two doubled
    repeats long, is averaged along the lines (so the weave's grain drops out) and the two halves of each
    doubled repeat compared: a line that is in one half and not the other shows, and it shows the same way in
    both doubled repeats, which a pocket's edge or a seam does not. Only areas whose two doubled repeats look
    alike count (the body's cloth lying straight, not a sleeve at another angle). Returns the middle of what
    those areas say (delta E), or None with too few areas."""
    if not across:
        lab, m, P, Q = lab.transpose(1, 0, 2), m.T, Q, P
    H, W = m.shape
    bw, bh = 4 * P, max(8, Q)
    seen = []
    for y0 in range(0, H - bh + 1, max(4, bh // 2)):
        for x0 in range(0, W - bw + 1, P):
            if m[y0:y0 + bh, x0:x0 + bw].mean() < 0.97:
                continue
            col = cv2.blur(lab[y0:y0 + bh, x0:x0 + bw].mean(0)[None], (3, 1))[0] * (100 / 255, 1, 1)
            one, two = col[:2 * P] - col[:2 * P].mean(0), col[2 * P:] - col[2 * P:].mean(0)
            if (one * two).sum() < 0.5 * np.sqrt((one ** 2).sum() * (two ** 2).sum()):
                continue
            d1, d2 = col[:P] - col[P:2 * P], col[2 * P:3 * P] - col[3 * P:]
            same = np.where((d1 * d2).sum(1) > 0, np.minimum(np.linalg.norm(d1, axis=1), np.linalg.norm(d2, axis=1)), 0)
            seen.append(float(np.sort(same)[-max(1, P // 12)]))
    return float(np.median(seen)) if len(seen) >= 6 else None


def _clearest(lab, m, P, Q):
    """One repeat from where the cloth lies best: of all areas three repeats square lying wholly on the garment,
    the one that agrees most with itself one repeat on, folded onto one repeat. A sharper first reference for
    `flatten` than any single square (which carries its own fold or pocket) or the whole garment folded (which
    its sleeves and slow drift wash out). None when no such area lies on the garment."""
    H, W = m.shape
    sig = soft(lab, m, light=3 * max(P, Q))
    best = None
    for n in (3, 2):
        for y0 in range(0, H - n * Q + 1, max(4, Q // 2)):
            for x0 in range(0, W - n * P + 1, max(4, P // 2)):
                if not m[y0:y0 + n * Q, x0:x0 + n * P].all():
                    continue
                a = sig[y0:y0 + n * Q, x0:x0 + n * P]
                a = a - a.mean()
                score = ((a[:, :-P] * a[:, P:]).mean() + (a[:-Q] * a[Q:]).mean()) / ((a ** 2).mean() + 1e-6)
                if best is None or score > best[0]:
                    best = (score, x0, y0, n)
        if best is not None:
            break
    if best is None:
        return None
    _, x0, y0, n = best
    return lab[y0:y0 + n * Q, x0:x0 + n * P].reshape(n, Q, n, P, 3).mean((0, 2))


def regular(cut: Image.Image, log=quiet) -> Regular | None:
    """The cutout with its plaid made regular, and the repeat's size; None when no repeat can be found."""
    arr = np.asarray(cut.convert("RGBA"))
    steps = []
    lines = by_lines(cut, log)
    if lines is None:
        Hp, size = np.eye(3), (arr.shape[1], arr.shape[0])
    else:
        Hp, size = lines
        steps.append("tilt")
    first = cv2.warpPerspective(arr, Hp, size, flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
    m1 = _mask(first)
    if m1.sum() < 400:
        return None
    sig1 = soft(to_lab(first[..., :3]), m1, light=0.15 * _size(m1))   # slow light out; a repeat up to a quarter of the garment stays
    found = repeat(sig1, m1, log)
    if found is None:
        log("  no repeat found in the garment's areas")
        return None
    evened = by_repeat(sig1, m1, *found, log=log)
    if evened is None:
        # a repeat too large to show in many areas: the cloth as the lines alone leave it
        if lines is None:
            return None
        (P, Q), out = found, first

        def to_new(pts):
            return _apply(Hp, pts)
    else:
        fitted, P, Q = evened
        steps.append("evened")
        # the finished picture: every pixel fetched once from the original (the two maps joined), not twice
        ys, xs = np.where(m1)
        step = max(1, len(xs) // 5000)
        uv = fitted.at(np.stack([xs[::step], ys[::step]], 1))
        u0, v0 = uv[:, 0].min() - 4 / P, uv[:, 1].min() - 4 / Q
        w = int(np.ceil((uv[:, 0].max() - u0) * P)) + 4
        h = int(np.ceil((uv[:, 1].max() - v0) * Q)) + 4
        if max(w, h) > 3 * max(arr.shape[:2]) or min(w, h) < 2 * max(P, Q):
            return None
        gx, gy = np.meshgrid(np.arange(w, dtype=np.float64), np.arange(h, dtype=np.float64))
        sx, sy = fitted.back(gx / P + u0, gy / Q + v0)
        src = np.stack([sx, sy, np.ones_like(sx)], -1) @ np.linalg.inv(Hp).T
        mx = (src[..., 0] / src[..., 2]).astype(np.float32)
        my = (src[..., 1] / src[..., 2]).astype(np.float32)
        out = cv2.remap(arr, mx, my, cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
        out[..., 3] = cv2.remap(arr[..., 3], mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)

        def to_new(pts, P0=P, Q0=Q):       # the size the map was made for, before any doubling below
            uv_ = fitted.at(_apply(Hp, pts))
            return np.stack([(uv_[:, 0] - u0) * P0, (uv_[:, 1] - v0) * Q0], 1)
    lab, m = to_lab(np.ascontiguousarray(out[..., :3])), _mask(out)
    for across in (True, False) if evened is not None else ():   # only cloth made regular can be folded and compared
        for _ in range(2):             # an overcheck over every other check, and (rarely) over every fourth
            diff = _halves_differ(lab, m, P, Q, across)
            if diff is None or diff < VISIBLE:
                break
            log(f"  the repeat is twice as long {'across' if across else 'down'}: its halves differ by {diff:.1f}")
            P, Q = (2 * P, Q) if across else (P, 2 * Q)
    ref = _clearest(lab, m, P, Q)
    if ref is None:
        return None
    return Regular(Image.fromarray(out, "RGBA"), P, Q, to_new, ref, tuple(steps))


def preview(tile_lab, size=300):
    """A square of the repeat tiled, for looking at (RGB array)."""
    t = lab_to_rgb(tile_lab)
    return np.tile(t, (int(np.ceil(size / t.shape[0])), int(np.ceil(size / t.shape[1])), 1))[:size, :size]
