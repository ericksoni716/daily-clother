"""A shoe's solid from its photos, drawn as the figure sees it (an experiment, not app code).

Side photo -> the profile along the length (bottom and top heights). Photo from above -> the plan (centre line and
half-width along the length). Front and back photos -> how rounded the cross-sections are. Colours: each visible
point takes the colour of the photo that sees it (above for what faces up, a side photo for what faces sideways),
after all the shoe's photos are reduced to a few colours together."""
import math, sys
import numpy as np
import cv2
from PIL import Image
import photos as P
from masks import load, mask as get_mask, W

L = 600                      # canonical pixels per shoe length
LENGTH_CM, BALL, LOOK, TURN = 29.5, 0.72, 24.0, 11.0
FLIP_ABOVE = {2}
INK = (38, 34, 31)
SOCK, SOCK_RIB, SKIN, BG = (47, 125, 79), (31, 90, 56), (201, 141, 107), (241, 238, 232)


def biggest(m):
    n, lab, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
    if n <= 1: return m
    return lab == (1 + np.argmax(st[1:, cv2.CC_STAT_AREA]))


def opened(m, frac=0.035):
    ys, xs = np.nonzero(m)
    k = max(3, int(frac * max(xs.max() - xs.min(), ys.max() - ys.min())) | 1)
    o = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    return biggest(o > 0)


def rotate(img, m, deg, centre):
    h, w = m.shape
    M = cv2.getRotationMatrix2D(centre, deg, 1.0)
    cs, sn = abs(M[0, 0]), abs(M[0, 1])
    nw, nh = int(h * sn + w * cs), int(h * cs + w * sn)
    M[0, 2] += nw / 2 - centre[0]; M[1, 2] += nh / 2 - centre[1]
    return (cv2.warpAffine(img, M, (nw, nh), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE),
            cv2.warpAffine(m.astype(np.uint8), M, (nw, nh), flags=cv2.INTER_NEAREST) > 0)


def crop_scale(img, m, geo, length_axis=1):
    ys, xs = np.nonzero(geo)
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    s = L / (x1 - x0)
    img, m, geo = img[y0:y1, x0:x1], m[y0:y1, x0:x1], geo[y0:y1, x0:x1]
    size = (L, max(1, int(round((y1 - y0) * s))))
    return (cv2.resize(img, size, interpolation=cv2.INTER_AREA), cv2.resize(m.astype(np.uint8), size, interpolation=cv2.INTER_NEAREST) > 0,
            cv2.resize(geo.astype(np.uint8), size, interpolation=cv2.INTER_NEAREST) > 0)


def smooth1(a, k=21):
    a = np.asarray(a, float)
    pad = np.pad(a, k, mode="edge")
    med = np.array([np.median(pad[i:i + 9]) for i in range(len(pad) - 8)])
    ker = np.hanning(k); ker /= ker.sum()
    return np.convolve(med, ker, mode="same")[k - 4:k - 4 + len(a)]


class Side:
    """A side photo set level on its sole, toe to the right, one shoe length = L pixels."""
    def __init__(self, n, view):
        img = np.array(load(n, view)); m = biggest(get_mask(n, view))
        self.cut_off = bool(m[:, :3].any() or m[:, -3:].any() or m[:3].any() or m[-3:].any())
        geo = opened(m)
        cnt = max(cv2.findContours(geo.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0], key=len)
        hull = cv2.convexHull(cnt)[:, 0, :].astype(float)
        cy = np.nonzero(geo)[0].mean()
        best, ang = 0, 0.0
        for a, b in zip(hull, np.roll(hull, -1, axis=0)):
            d = b - a; ln = np.hypot(*d)
            if (a[1] + b[1]) / 2 > cy and ln > best and abs(d[0]) > abs(d[1]):
                best = ln; ang = math.degrees(math.atan2(d[1], d[0]))
        if ang > 90: ang -= 180
        if ang < -90: ang += 180
        self.tilt = ang
        ys, xs = np.nonzero(geo)
        img, m2 = rotate(img, m, ang, (float(xs.mean()), float(ys.mean())))
        _, geo = rotate(img, geo, 0, (0, 0)) if False else (None, rotate(np.zeros_like(m, np.uint8), geo, ang, (float(xs.mean()), float(ys.mean())))[1])
        img, m2, geo = crop_scale(img, m2, geo)
        H = geo.shape[0]
        tops = np.array([np.argmax(geo[:, c]) if geo[:, c].any() else H for c in range(L)])
        if tops[: L // 4].mean() > tops[-L // 4:].mean():      # the toe is the low end: put it on the right
            img, m2, geo = img[:, ::-1], m2[:, ::-1], geo[:, ::-1]
        self.img, self.mask, self.geo, self.H = np.ascontiguousarray(img), m2, geo, H
        top = np.array([H - np.argmax(geo[:, c]) if geo[:, c].any() else 0 for c in range(L)], float)
        bot = np.array([H - 1 - (H - 1 - np.argmax(geo[::-1, c])) if geo[:, c].any() else 0 for c in range(L)], float)
        bot = np.array([np.argmax(geo[::-1, c]) if geo[:, c].any() else 0 for c in range(L)], float)
        self.top, self.bot = smooth1(top) / L, np.clip(smooth1(bot), 0, None) / L    # heights above the ground, in lengths


class Above:
    """The photo from above set with the heel on the left, toe on the right, the inner side down the picture."""
    def __init__(self, n):
        img = np.array(load(n, "above")); m = biggest(get_mask(n, "above"))
        geo = opened(m)
        ys, xs = np.nonzero(geo)
        pts = np.stack([xs, ys], 1).astype(float); mu = pts.mean(0)
        w, v = np.linalg.eigh(np.cov((pts - mu).T))
        ax = v[:, np.argmax(w)]
        ang = math.degrees(math.atan2(ax[1], ax[0]))
        c = (float(mu[0]), float(mu[1]))
        img, m2 = rotate(img, m, ang, c)
        geo = rotate(np.zeros_like(m, np.uint8), geo, ang, c)[1]
        img, m2, geo = crop_scale(img, m2, geo)
        H = geo.shape[0]
        def prof(g):
            lo = np.array([np.argmax(g[:, c]) if g[:, c].any() else H / 2 for c in range(L)], float)
            hi = np.array([H - np.argmax(g[::-1, c]) if g[:, c].any() else H / 2 for c in range(L)], float)
            return lo, hi
        lo, hi = prof(geo)
        wid = smooth1(hi - lo, 41)
        if wid[int(0.55 * L):int(0.85 * L)].mean() < wid[int(0.15 * L):int(0.45 * L)].mean():   # the forefoot is the wider half
            img, m2, geo = img[:, ::-1], m2[:, ::-1], geo[:, ::-1]; lo, hi = prof(geo)
        if n in FLIP_ABOVE:
            img, m2, geo = img[:, ::-1], m2[:, ::-1], geo[:, ::-1]; lo, hi = prof(geo)
        cen = smooth1((lo + hi) / 2, 41)
        if cen[int(0.93 * L)] < cen[int(0.6 * L)]:             # the toe leans to the inner side: put it at +x
            img, m2, geo = img[::-1], m2[::-1], geo[::-1]; lo, hi = prof(geo)
        self.img, self.mask, self.geo, self.H = np.ascontiguousarray(img), m2, geo, H
        self.lo, self.hi = smooth1(lo), smooth1(hi)
        self.row0 = float(np.median((self.lo + self.hi) / 2))
        self.c = ((self.lo + self.hi) / 2 - self.row0) / L     # centre line and half-width, in lengths
        self.w = np.clip((self.hi - self.lo) / 2, 0.5, None) / L


class Ends:
    """A front or back photo as a silhouette: width and height scaled to 1."""
    def __init__(self, n, view):
        m = opened(biggest(get_mask(n, view)), 0.05)
        ys, xs = np.nonzero(m)
        m = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        self.m = cv2.resize(m.astype(np.uint8), (200, 200), interpolation=cv2.INTER_NEAREST) > 0
        self.aspect = m.shape[0] / m.shape[1]


def panels(im, m, k=6, soft=3.2, small=0.02):
    """One photo cut into panels: pieces of one colour whose edges are sharp. A piece that fades into its neighbour
    (shade, a highlight, dirt) joins it; so does one too small to matter. Returns a region number per pixel."""
    ms = cv2.pyrMeanShiftFiltering(cv2.medianBlur(im, 9), 24, 38)
    lab = cv2.cvtColor(ms, cv2.COLOR_RGB2LAB).astype(np.float32)
    er = cv2.erode(m.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    _, lb, cen = cv2.kmeans(lab[er], k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.5), 3, cv2.KMEANS_PP_CENTERS)
    li = np.linalg.norm(lab[:, :, None, :] - cen[None, None], axis=3).argmin(2).astype(np.uint8)
    li = cv2.medianBlur(li, 15)
    reg = np.zeros(m.shape, np.int32); nreg = 0
    for v in range(k):
        n, cc = cv2.connectedComponents(((li == v) & m).astype(np.uint8), connectivity=4)
        reg[cc > 0] = cc[cc > 0] + nreg; nreg += n - 1
    # how sharp the photo is at each pixel: the colour step over a few pixels of the lightly blurred photo
    g = cv2.GaussianBlur(cv2.cvtColor(cv2.medianBlur(im, 5), cv2.COLOR_RGB2LAB).astype(np.float32), (0, 0), 2.0)
    gx = np.linalg.norm(g[:, 4:] - g[:, :-4], axis=2); gy = np.linalg.norm(g[4:] - g[:-4], axis=2)
    step = np.zeros(m.shape, np.float32); step[:, 2:-2] = gx; step[2:-2] = np.maximum(step[2:-2], gy)
    step = cv2.dilate(step, np.ones((5, 5), np.uint8))
    total = float(m.sum())
    parent = np.arange(nreg + 1)
    def find(x):
        while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def borders(r):
        """Every pair of touching regions, with the photo's sharpness along the edge they share (its median)."""
        ks, ss_ = [], []
        for A, B, S in ((r[:, 1:], r[:, :-1], step[:, 1:]), (r[1:], r[:-1], step[1:])):
            d = (A != B) & (A > 0) & (B > 0)
            a_, b_ = A[d].astype(np.int64), B[d].astype(np.int64)
            ks.append(np.minimum(a_, b_) * (nreg + 2) + np.maximum(a_, b_)); ss_.append(S[d])
        ks, ss_ = np.concatenate(ks), np.concatenate(ss_)
        if not len(ks): return []
        o = np.lexsort((ss_, ks)); ks, ss_ = ks[o], ss_[o]
        u, first, cnt = np.unique(ks, return_index=True, return_counts=True)
        med = ss_[first + cnt // 2]
        return sorted(zip(med.tolist(), (u // (nreg + 2)).tolist(), (u % (nreg + 2)).tolist()))
    for sv, a_, b_ in borders(reg):                     # soft edges first: shade, highlights, dirt
        if sv >= soft: break
        ra, rb = find(a_), find(b_)
        if ra != rb: parent[rb] = ra
    for _ in range(6):                                  # then anything too small to matter joins what it fades into most
        roots = np.array([find(i) for i in range(nreg + 1)])
        r = roots[reg]
        ar = np.bincount(r.ravel(), minlength=nreg + 1).astype(float)
        changed = False
        for sv, a_, b_ in borders(r):
            ra, rb = find(a_), find(b_)
            if ra != rb and min(ar[ra], ar[rb]) < small * total:
                parent[rb] = ra; ar[ra] += ar[rb]; changed = True
        if not changed: break
    roots = np.array([find(i) for i in range(nreg + 1)])
    return roots[reg], lab


def palette(imgs, masks, merge=14.0, most=5, far=30.0):
    """The shoe's few colours, from the first photo (the side); the other photos' panels take the nearest of them,
    after each photo's overall colour is brought to the side photo's (the light differs between photos). A panel
    unlike any of them (a lining seen only from above) keeps its own colour."""
    def stats(im, m):
        lab = cv2.cvtColor(cv2.medianBlur(im, 5), cv2.COLOR_RGB2LAB).astype(np.float32)
        return lab, lab[m].mean(0), lab[m].std(0) + 1e-3
    ref_lab, ref_mu, ref_sd = stats(imgs[0], masks[0])
    regs, pal, extra = [], None, []
    out = []
    for p, (im, m) in enumerate(zip(imgs, masks)):
        r, _ = panels(im, m)
        raw, mu, sd = stats(im, m)
        if p: raw = (raw - mu) / sd * ref_sd + ref_mu
        ids = [v for v in np.unique(r[m]) if v]
        cols = np.array([np.median(raw[(r == v) & m], axis=0) for v in ids]); wts = np.array([float(((r == v) & m).sum()) for v in ids])
        if p == 0:
            groups = [[i] for i in range(len(ids))]
            gc = lambda g: np.average(cols[g], axis=0, weights=wts[g])
            gw = lambda g: wts[g].sum()
            while len(groups) > 1:
                best = None
                for a_ in range(len(groups)):
                    for b_ in range(a_ + 1, len(groups)):
                        d = float(np.linalg.norm(gc(groups[a_]) - gc(groups[b_])))
                        if best is None or d < best[0]: best = (d, a_, b_)
                if best[0] >= merge and len(groups) <= most: break
                groups[best[1]] += groups[best[2]]; del groups[best[2]]
            pal = [gc(g) for g in groups]
            lut = np.zeros(r.max() + 1, np.uint8)
            for gi, g in enumerate(groups):
                for i in g: lut[ids[i]] = gi
        else:
            lut = np.zeros(r.max() + 1, np.uint8)
            for i, v in enumerate(ids):
                d = [float(np.linalg.norm(cols[i] - c)) for c in pal]
                if min(d) > far and wts[i] > 0.04 * m.sum() and len(pal) < 8:
                    pal.append(cols[i]); lut[v] = len(pal) - 1
                else:
                    lut[v] = int(np.argmin(d))
        li = lut[r]
        _, idx = cv2.distanceTransformWithLabels((~m).astype(np.uint8), cv2.DIST_L2, 3, labelType=cv2.DIST_LABEL_PIXEL)
        ys, xs = np.nonzero(m)
        l2 = np.zeros(idx.max() + 1, np.uint8); l2[idx[ys, xs]] = li[ys, xs]
        out.append(np.where(m, li, l2[idx]))
    rgb = np.array([cv2.cvtColor(np.uint8([[np.clip(c, 0, 255)]]), cv2.COLOR_LAB2RGB)[0, 0] for c in pal])
    return rgb, out


class Solid:
    def __init__(self, n):
        self.n = n
        side = Side(n, "side"); inner = Side(n, "inner")
        self.note = []
        if side.cut_off:
            self.note.append("the side photo runs off the frame: the inner side photo gives the profile")
        prof = inner if (side.cut_off and not inner.cut_off) else side
        self.side, self.inner, self.above = side, inner, Above(n)
        # worn, the shoe stands flat: the lift of the toe and the heel's curve come off the top, and the bottom is the ground
        self.raw_top, self.raw_bot = prof.top, prof.bot
        self.top, self.bot = np.maximum(prof.top - prof.bot, 0.004), np.zeros(L)
        self.c, self.w = self.above.c, self.above.w
        ramp = np.clip(np.minimum(np.arange(L), L - 1 - np.arange(L)) / 6.0, 0, 1) ** 0.5
        self.w = self.w * ramp + 1e-4
        self.cols, (self.lab_side, self.lab_inner, self.lab_above) = palette(
            [side.img, inner.img, self.above.img], [side.mask, inner.mask, self.above.mask])
        self.sole = self.sole_top(prof, self.lab_inner if prof is inner else self.lab_side)
        self.front, self.back = Ends(n, "front"), Ends(n, "back")
        self.n_rear, self.n_fore = 5.0, 2.6
        self.fit_round()

    def sole_top(self, sd, lab):
        """The solid's upright wall along its edge. Not measured: a plain share of the height, 3 cm at most."""
        return np.minimum(0.28 * self.top, 3.0 / LENGTH_CM)

    def nz(self, z): return np.where(z < 0.42, self.n_rear, np.where(z > 0.6, self.n_fore, self.n_rear + (self.n_fore - self.n_rear) * (z - 0.42) / 0.18))

    def height(self, s, i):
        """Top of the solid at share s (-1..1) across, at length index i (arrays broadcast)."""
        z = i / L
        n = self.nz(z)
        full = self.top[i] - self.bot[i]
        rho = np.clip(self.sole[i] / np.maximum(full, 1e-4), 0, 0.95)
        g = np.clip(1 - np.abs(s) ** n, 0, 1) ** (1 / n)
        return self.bot[i] + full * (rho + (1 - rho) * g)

    def end_view(self, rear):
        """The solid's silhouette seen from the back (rear) or the front, as an image 200 x 200 scaled to its box."""
        idx = np.arange(0, L, 3)
        idx = idx[idx < 0.5 * L] if rear else idx
        s = np.linspace(-1, 1, 81)
        S, I = np.meshgrid(s, idx)
        X = self.c[I] + S * self.w[I]; Ht = self.height(S, I)
        x0, x1 = (self.c - self.w)[idx].min(), (self.c + self.w)[idx].max()
        hmax = self.top[idx].max()
        im = np.zeros((200, 200), np.uint8)
        px = np.clip(((X - x0) / (x1 - x0) * 199).astype(int), 0, 199)
        for r in range(X.shape[0]):
            for c in range(X.shape[1]):
                im[199 - int(np.clip(Ht[r, c] / hmax, 0, 1) * 199):, px[r, c]] = 1
        im = cv2.morphologyEx(im, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        return im > 0

    def fit_round(self):
        def iou(a, b): return (a & b).sum() / max(1, (a | b).sum())
        grid = [2.0, 2.4, 2.8, 3.2, 3.8, 4.5, 5.5, 7.0]
        best = (-1, 5.0)
        for n in grid:
            self.n_rear = n
            v = iou(self.end_view(True), self.back.m[:, ::-1])
            v = max(v, iou(self.end_view(True), self.back.m))
            if v > best[0]: best = (v, n)
        self.n_rear, self.fit_back = best[1], best[0]
        best = (-1, 2.6)
        for n in grid:
            self.n_fore = n
            v = iou(self.end_view(False), self.front.m)
            if v > best[0]: best = (v, n)
        self.n_fore, self.fit_front = best[1], best[0]

    # ---- drawing
    def render(self, px=9.0, ss=3, turn=TURN, w=160, h=320, ground=292, leg_x=109):
        """One foot (the viewer's left) at ss times the size: part (0 none, 1 shoe, 2 sock, 3 skin) and colour label.
        The solid and the leg are cut into small flat pieces and painted from the farthest to the nearest."""
        S = px * ss
        Wd, Hd = w * ss, h * ss
        part = np.zeros((Hd, Wd), np.uint8); label = np.zeros((Hd, Wd), np.uint8)
        ct, st_, cl, sl = math.cos(math.radians(turn)), math.sin(math.radians(turn)), math.cos(math.radians(LOOK)), math.sin(math.radians(LOOK))
        zc = 0.215; ia = int(zc * L)
        toe = L - 1
        y0 = (self.c[toe] * LENGTH_CM * st_ + (toe / L - zc) * LENGTH_CM * ct) * sl
        def project(x, z, hh):
            zz = (z - zc) * LENGTH_CM
            xr = x * ct - zz * st_; zr = x * st_ + zz * ct
            return np.stack([leg_x * ss + xr * S, ground * ss + (zr * sl - hh * cl - y0) * S], -1), zr * cl + hh * sl
        polys = []    # (depth, 4 points, part, label)
        def quads(P2, D, pt, lb):
            a, b, c, d = P2[:-1, :-1], P2[:-1, 1:], P2[1:, 1:], P2[1:, :-1]
            q = np.stack([a, b, c, d], 2).reshape(-1, 4, 2)
            dd = ((D[:-1, :-1] + D[:-1, 1:] + D[1:, 1:] + D[1:, :-1]) / 4).ravel()
            lb = np.broadcast_to(lb, (P2.shape[0] - 1, P2.shape[1] - 1)).ravel()
            for k in range(len(dd)): polys.append((dd[k], q[k], pt, int(lb[k])))
        ii = np.linspace(0, L - 1, 150).astype(int)
        sj = np.sin(np.linspace(-math.pi / 2, math.pi / 2, 49))          # closer together near the edges
        Sg, Ig = np.meshgrid(sj, ii)
        X3 = (self.c[Ig] + Sg * self.w[Ig]) * LENGTH_CM; H3 = self.height(Sg, Ig) * LENGTH_CM; Z3 = Ig / L
        mid = lambda A: (A[:-1, :-1] + A[:-1, 1:] + A[1:, 1:] + A[1:, :-1]) / 4
        Xm, Hm, Im, Sm = mid(X3), mid(H3), mid(Ig.astype(float)).astype(int), mid(Sg)
        sx = (H3[:-1, 1:] - H3[:-1, :-1]) / np.maximum(X3[:-1, 1:] - X3[:-1, :-1], 1e-6)
        szz = (H3[1:, :-1] - H3[:-1, :-1]) / np.maximum((Z3[1:, :-1] - Z3[:-1, :-1]) * LENGTH_CM, 1e-6)
        slope = np.hypot(sx, szz)
        rows_a = np.clip((self.above.row0 + (Xm / LENGTH_CM) * L).astype(int), 0, self.above.H - 1)
        la = self.lab_above[rows_a, Im]
        def side_lab(sd, lab, Hcm, I):
            r = np.clip(sd.H - 1 - ((Hcm / LENGTH_CM + sd.bot[I]) * L).astype(int), 0, sd.H - 1)
            return lab[r, I]
        ls = np.where(Sm < 0, side_lab(self.side, self.lab_side, Hm, Im), side_lab(self.inner, self.lab_inner, Hm, Im))
        P2, D = project(X3, Z3, H3)
        quads(P2, D, 1, np.where(slope < 1.2, la, ls))                  # what faces up takes the photo from above
        tt = np.linspace(0, 1, 9)
        for sgn, sd, lab in ((-1, self.side, self.lab_side), (1, self.inner, self.lab_inner)):
            Tg, Iw = np.meshgrid(tt, ii)
            Hw = (self.bot[Iw] + Tg * (self.height(np.full(Iw.shape, float(sgn)), Iw) - self.bot[Iw])) * LENGTH_CM
            Xw = (self.c[Iw] + sgn * self.w[Iw]) * LENGTH_CM
            P2, D = project(Xw, Iw / L, Hw)
            quads(P2, D, 1, side_lab(sd, lab, mid(Hw), mid(Iw.astype(float)).astype(int)))
        rad0 = min(3.4, 0.8 * self.w[ia] * LENGTH_CM)
        hrim = self.top[ia] * LENGTH_CM; hs = hrim + 10.5
        th = np.linspace(0, 2 * math.pi, 49); hh = np.concatenate([np.linspace(self.bot[ia] * LENGTH_CM + 1, hs, 40), np.linspace(hs, 62, 30)[1:]])
        Tg, Hg = np.meshgrid(th, hh)
        rad = rad0 + (4.9 - rad0) * np.clip((Hg - hrim) / 24, 0, 1)
        P2, D = project(self.c[ia] * LENGTH_CM + rad * np.sin(Tg), zc + 0.9 * rad * np.cos(Tg) / LENGTH_CM, Hg)
        if getattr(self, 'with_leg', True):
            quads(P2[:40], D[:40], 2, 0); quads(P2[39:], D[39:], 3, 0)
        polys.sort(key=lambda t: t[0])
        for _, q, pt, lb in polys:
            qi = np.round(q).astype(np.int32)
            cv2.fillConvexPoly(part, qi, pt); cv2.fillConvexPoly(label, qi, lb)
        return part, label

    def picture(self, px=9.0, ss=3, turn=TURN, w=160, h=320, leg_x=109):
        part, label = self.render(px, ss, turn, w, h, leg_x=leg_x)
        shoe = cv2.morphologyEx((part == 1).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)) > 0
        k = 2 * ss + 1
        for p in (2, 3):
            pm = cv2.morphologyEx((part == p).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)) > 0
            part[pm & (part == 0)] = p
        part[shoe & (part == 0)] = 1
        # the shoe's colours: no speck smaller than a share of the shoe, and smooth edges between colours
        lab = label.copy()
        area = int((part == 1).sum())
        for _ in range(3):
            lab = cv2.medianBlur(lab, 4 * ss + 1)
            for v in np.unique(lab[part == 1]):
                n, cc, stt, _ = cv2.connectedComponentsWithStats(((lab == v) & (part == 1)).astype(np.uint8), 4)
                for j in range(1, n):
                    if stt[j, cv2.CC_STAT_AREA] < 0.02 * area:
                        blob = cc == j
                        ring = cv2.dilate(blob.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
                        nb = lab[ring & ~blob & (part == 1)]
                        if len(nb): lab[blob] = np.bincount(nb).argmax()
        img = np.zeros(part.shape + (3,), np.uint8); img[:] = BG
        for v in range(len(self.cols)): img[(part == 1) & (lab == v)] = self.cols[v]
        img[part == 2] = SOCK; img[part == 3] = SKIN
        # lines: thin between colours and where the shoe folds over itself; bold round each part
        ids = part.astype(np.int32) * 16 + np.where(part == 1, lab, 0)
        def edges(a):
            e = np.zeros(a.shape, bool)
            e[:, 1:] |= a[:, 1:] != a[:, :-1]; e[1:] |= a[1:] != a[:-1]
            return e
        thin = cv2.dilate(edges(ids).astype(np.uint8), np.ones((max(1, int(1.2 * ss)),) * 2, np.uint8)) > 0
        bold = cv2.dilate(edges(part).astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3 * ss, 3 * ss))) > 0
        thin_col = lambda: None
        dark = (img.astype(float) * 0.45).astype(np.uint8)
        img[thin & (part == 1)] = dark[thin & (part == 1)]
        img[bold] = INK
        one = Image.fromarray(img).resize((w, h), Image.LANCZOS)
        both = Image.new("RGB", (2 * w, h), BG)
        both.paste(one, (0, 0)); both.paste(one.transpose(Image.FLIP_LEFT_RIGHT), (w, 0))
        return both

    def debug(self):
        """The side and above photos set straight, with what was measured drawn on them, and the colours found."""
        s = self.inner if (self.side.cut_off and not self.inner.cut_off) else self.side
        a = s.img.copy()
        for c in range(L):
            for v, col in ((self.raw_top[c], (255, 0, 255)), (self.raw_bot[c] + self.sole[c], (0, 200, 255)), (self.raw_bot[c], (255, 0, 255))):
                r = int(np.clip(s.H - 1 - v * L, 0, s.H - 1)); a[max(0, r - 1):r + 1, c] = col
        b = self.above.img.copy()
        for c in range(L):
            for v in (self.c[c] - self.w[c], self.c[c] + self.w[c], self.c[c]):
                r = int(np.clip(self.above.row0 + v * L, 0, self.above.H - 1)); b[max(0, r - 1):r + 1, c] = (255, 0, 255)
        la = self.cols[self.lab_side]; lb = self.cols[self.lab_above]
        la[~self.side.mask] = 255; lb[~self.above.mask] = 255
        hh = max(a.shape[0], b.shape[0], la.shape[0], lb.shape[0])
        out = Image.new("RGB", (4 * L, hh), "white")
        for k, im in enumerate((a, la.astype(np.uint8), b, lb.astype(np.uint8))): out.paste(Image.fromarray(im), (k * L, 0))
        return out


if __name__ == "__main__":
    which = [int(x) for x in sys.argv[1:]] or list(P.SHOES)
    pics, dbg = [], []
    for n in which:
        sd = Solid(n)
        print(n, P.SHOES[n][0], "| colours", len(sd.cols), "| roundness rear", sd.n_rear, f"({sd.fit_back:.2f})", "fore", sd.n_fore, f"({sd.fit_front:.2f})",
              "| sole at ball %.1f cm" % (sd.sole[int(BALL * L)] * LENGTH_CM), "| height %.1f cm" % (sd.top.max() * LENGTH_CM),
              "| width %.1f cm" % (2 * sd.w.max() * LENGTH_CM), "|", "; ".join(sd.note))
        pics.append(sd.picture()); dbg.append(sd.debug())
        pics[-1].save(W / f"feet-{n}.png")
    sheet = Image.new("RGB", (320 * len(pics), 320), "white")
    for k, p in enumerate(pics): sheet.paste(p, (320 * k, 0))
    sheet.save(W / "feet-sheet.png")
    hh = sum(d.height for d in dbg)
    ds = Image.new("RGB", (4 * L, hh), "white"); y = 0
    for d in dbg: ds.paste(d, (0, y)); y += d.height
    ds.thumbnail((1800, 1800)); ds.save(W / "debug-sheet.jpg", quality=85)
