"""A shoe Claude drew straight on, turned out the way a man stands (shoes drawn from understanding, the turned view).

The figure shows each shoe turned out `TURN` degrees. Claude draws the shoe straight on first (the view its worked
examples and the prompt were tuned in); this module then turns that drawing with the app's own 3D shoe solid
(`frontshoe`'s footprint, top line and shaft for the shoe's style), seen by a camera matched to the liked examples:
every point of the drawing is found on the solid's surface, the solid is turned, and the point is seen again. Seams,
panels, lacing, stitching and marks move exactly as they would on a real shoe (`turn_side`). The outline does not:
it is where the surface turns away, so Claude redraws it by eye, and draws the inner side that comes into view
(`tagger/shoedrawing.py`). The guide picture Claude is shown (`guide_png`, `guide_text`) is the same solid straight
on and turned, with its construction lines.

The frame is the drawings' (x across, y down, the ground at y = 240, the leg at x 62 to 138); a turned drawing needs
the wide frame (`drawn.TURNED`). No call to Claude is made here.
"""
from __future__ import annotations

import io
import math
from dataclasses import dataclass
from functools import cache

import numpy as np

from . import drawn
from . import frontshoe as FS

TURN = 12.0            # degrees each toe is turned out on the figure
LOOK = 16.0            # degrees the camera looks down
DISTANCE = 70.0        # cm from the camera to the ball of the foot: the perspective that matches the liked examples
PX = 16.0              # frame units to a centimetre
GROUND = 240.0         # where the toe tip of the sole touches, in the frame
LACED = ("runner", "low_sneaker", "high_top", "oxford", "derby", "boot")
STYLES = ("runner", "low_sneaker", "high_top", "slip_on", "loafer", "derby", "oxford", "boot", "chelsea_boot")
# a running shoe's midsole, in cm: thicker under the heel than the ball (the drop), the toe sprung up (the rocker), the
# heel's back edge bevelled
RUNNER_SOLE = {"heel": 4.2, "fore": 3.0, "spring": 2.2, "bevel": 0.6}
HEEL_U = 0.3            # the back of the foot a boot's shaft is outlined with (heel 0, toe 1)
WORDS = {"runner": "running shoe", "low_sneaker": "low sneaker", "high_top": "high-top sneaker",
         "slip_on": "slip-on sneaker", "loafer": "boat shoe or loafer (a low-profile shoe)", "derby": "derby (a dress shoe)",
         "oxford": "oxford (a dress shoe)", "boot": "lace-up ankle boot", "chelsea_boot": "Chelsea boot"}


def _runner_lift(u: float, h: float, sole_t: float) -> float:
    """Heights along a running shoe (`RUNNER_SOLE`): the midsole's thickness from heel to ball, the toe's spring."""
    p = RUNNER_SOLE
    k = min(1.0, max(0.0, (0.75 - u) / 0.65))
    t = p["fore"] + (p["heel"] - p["fore"]) * (k * k * (3 - 2 * k))
    lift = p["spring"] * max(0.0, (u - 0.66) / 0.34) ** 2 + p["bevel"] * max(0.0, (0.07 - u) / 0.07) ** 2
    return lift + (h / sole_t * t if h <= sole_t else t + (h - sole_t))


class Camera:
    """Points on the solid (x across, u from heel 0 to toe 1, h above the ground, in cm) seen turned `turn` degrees
    toe out (to the viewer's left), from `LOOK` degrees above, at `DISTANCE`; in frame units, the toe tip at y 0."""

    def __init__(self, turn: float, sole_t: float, runner: bool = False):
        self.ct, self.st = math.cos(math.radians(turn)), math.sin(math.radians(turn))
        self.cl, self.sl = math.cos(math.radians(LOOK)), math.sin(math.radians(LOOK))
        self.sole_t, self.runner = sole_t, runner
        self.y0 = 0.0
        self.y0 = self(0.0, 1.0, 0.0)[1]

    def __call__(self, x: float, u: float, h: float) -> tuple[float, float]:
        if self.runner:
            h = _runner_lift(u, h, self.sole_t)
        z = (u - FS.BALL) * FS.LENGTH
        xr = x * self.ct - z * self.st
        zr = x * self.st + z * self.ct
        s = DISTANCE / (DISTANCE - (zr * self.cl + h * self.sl))
        return xr * s * PX, (zr * self.sl - h * self.cl) * s * PX - self.y0

    def near(self, x: float, u: float, h: float) -> float:
        """How near the camera a point is (larger: nearer), to tell what hides what."""
        return (x * self.st + (u - FS.BALL) * FS.LENGTH * self.ct) * self.cl + h * self.sl


@dataclass(frozen=True)
class Solid:
    """The 3D solid of a shoe style, as `frontshoe` builds it."""
    style: str
    ball: float
    sole_t: float
    table: tuple
    shaft: float
    inset: float

    @classmethod
    def of(cls, style: str) -> Solid:
        if style not in STYLES:
            raise KeyError(style)
        ball, sole_t, table, shaft = FS.STYLES[style]
        return cls(style, ball, sole_t, tuple(table), shaft, 0.93 if style in ("loafer", "derby", "oxford") else 0.97)

    def hw(self, u: float) -> float:
        return FS._half_width(u, self.ball, "round")

    def camera(self, turn: float) -> Camera:
        return Camera(turn, self.sole_t, self.style == "runner")

    def surface(self, cam: Camera, u: float, share: float) -> tuple[float, float]:
        """A point on the top of the upper at u, `share` of the way out to the side (-1 to 1)."""
        w, h = self.hw(u) * self.inset, FS._interp(self.table, u)
        a = math.acos(max(-1.0, min(1.0, share)))
        return cam(w * share, u, self.sole_t + h * math.sin(a))


def _hull(pts):
    return FS._hull(pts)


def _span(poly, y: float) -> tuple[float, float] | None:
    """Where a convex polygon crosses the row y: (x left, x right), or None."""
    xs = []
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1], strict=True):
        if (y0 - y) * (y1 - y) <= 0 and y0 != y1:
            xs.append(x0 + (x1 - x0) * (y - y0) / (y1 - y0))
        elif y0 == y1 == y:
            xs += [x0, x1]
    return (min(xs), max(xs)) if xs else None


def _union_outline(polys, step: float = 0.5) -> list:
    """The outline of convex polygons that overlap row by row (a boot's foot and the shaft standing in it): down the
    left side, back up the right."""
    ys = [y for poly in polys for _, y in poly]
    left, right = [], []
    y = min(ys)
    while y <= max(ys) + 1e-9:
        spans = [sp for sp in (_span(poly, y) for poly in polys) if sp]
        if spans:
            left.append((min(a for a, _ in spans), y))
            right.append((max(b for _, b in spans), y))
        y += step
    return left + right[::-1]


def _rdp(pts, eps):
    if len(pts) < 3:
        return pts
    (x0, y0), (x1, y1) = pts[0], pts[-1]
    dx, dy = x1 - x0, y1 - y0
    n = math.hypot(dx, dy) or 1e-9
    d = [abs(dy * (x - x0) - dx * (y - y0)) / n for x, y in pts[1:-1]]
    i = max(range(len(d)), key=d.__getitem__)
    if d[i] > eps:
        return _rdp(pts[:i + 2], eps)[:-1] + _rdp(pts[i + 1:], eps)
    return [pts[0], pts[-1]]


def path(pts, close: bool = True, eps: float = 1.2) -> str:
    """Points as short SVG path data, simplified to within `eps` frame units."""
    if close and len(pts) > 3:   # split at the point farthest from the first, and simplify both halves
        far = max(range(len(pts)), key=lambda i: (pts[i][0] - pts[0][0]) ** 2 + (pts[i][1] - pts[0][1]) ** 2)
        pts = _rdp(pts[:far + 1], eps)[:-1] + _rdp(pts[far:] + pts[:1], eps)[:-1]
    else:
        pts = _rdp(pts, eps)
    return "M" + " L".join(f"{x:.0f},{y:.0f}" for x, y in pts) + (" Z" if close else "")


@cache
def geometry(style: str, turn: float) -> dict:
    """The solid's lines in the frame, seen turned `turn` degrees: the sole's and the upper's outlines, the welt line
    that shows, the vamp's centre line, the collar's edge, where the toe box begins, the middle of the inner side and,
    for a laced style, the lacing's edges and end; and the toe tip, as point lists."""
    s = Solid.of(style)
    cam = s.camera(turn)
    ax = cam(0.0, FS.ANKLE_U, s.sole_t + FS.ANKLE_CM - 4.0)[0]
    to = lambda q: (q[0] + 100 - ax, q[1] + GROUND)  # noqa: E731
    us = [i / 80 for i in range(81)]

    def ring(h):
        return [(s.hw(u), u, h) for u in us] + [(-s.hw(u), u, h) for u in reversed(us)]
    sole = [to(q) for q in _hull([cam(*q) for h in (0.0, s.sole_t) for q in ring(h)])]
    upper_pts, heel_pts = [], []
    for u in (i / 60 for i in range(61)):
        w, h = s.hw(u) * s.inset, FS._interp(s.table, u)
        ring_u = [(w * math.cos(math.pi * k / 12), u, s.sole_t + h * math.sin(math.pi * k / 12)) for k in range(13)]
        upper_pts += [cam(*q) for q in ring_u]
        if u <= HEEL_U:
            heel_pts += [cam(*q) for q in ring_u]
    upper = [to(q) for q in _hull(upper_pts)]
    if s.shaft:
        # the shaft and the heel it stands on, hulled together and outlined with the foot (not hulled with it: a hull
        # of the shaft and the toe leans the shaft out towards the turned toe, which an upright tube never does)
        tube = [cam(4.7 * math.cos(2 * math.pi * k / 24), 0.2 + 5.2 * math.sin(2 * math.pi * k / 24) / FS.LENGTH, h)
                for h in (s.sole_t + 4.0, s.shaft) for k in range(24)]
        upper = _union_outline([upper, [to(q) for q in _hull(tube + heel_pts)]])
    top = ring(s.sole_t)   # the welt line: the top of the sole where its outward side faces the camera
    seen: list = []
    for i in range(len(top)):
        (xa, ua, _), (xb, ub, _) = top[i - 1], top[(i + 1) % len(top)]
        nx, nz = (ub - ua) * FS.LENGTH, -(xb - xa)
        if nx * cam.st + nz * cam.ct > 0:
            seen.append(to(cam(*top[i])))
        elif seen and seen[-1] is not None:
            seen.append(None)
    runs, cur = [], []
    for q in seen + [None]:
        if q is None:
            if len(cur) > 1:
                runs.append(cur)
            cur = []
        else:
            cur.append(q)
    u_in = FS.INSTEP_U if not s.shaft else 0.5
    g = {"sole": sole, "upper": upper, "welt": max(runs, key=len) if runs else [],
         "centre": [to(s.surface(cam, u_in + (1 - u_in) * k / 30, 0.0)) for k in range(31)],
         "rim": [to(cam(*q)) for q in FS._collar_ring(s.hw, s.inset, list(s.table), s.sole_t, s.shaft)],
         "toe": to(cam(0.0, 1.0, 0.0)),
         "toe_line": [to(s.surface(cam, 0.80, k / 10)) for k in range(-9, 10)],
         "side_mid": [to(s.surface(cam, 0.08 + 0.86 * k / 30, 0.8)) for k in range(31)]}
    if style in LACED:
        end = 0.66 if style == "oxford" else 0.74
        g["lace_l"] = [to(s.surface(cam, u_in + (end - u_in) * k / 12, -0.32)) for k in range(13)]
        g["lace_r"] = [to(s.surface(cam, u_in + (end - u_in) * k / 12, 0.32)) for k in range(13)]
        g["lace_end"] = [to(s.surface(cam, end, k / 20)) for k in range(-7, 8)]
    xs = [p[0] for p in sole + upper]
    ys = [p[1] for p in sole + upper]
    g["box"] = (min(xs), min(ys), max(xs), max(ys))
    return g


def inner_region(style: str, turn: float, u0: float = 0.35, u1: float = 0.65) -> tuple[float, float, float, float]:
    """Where a stretch of the inner side (u0 to u1 from the heel) shows in the frame, turned: (x0, y0, x1, y1)."""
    s = Solid.of(style)
    cam = s.camera(turn)
    ax = cam(0.0, FS.ANKLE_U, s.sole_t + FS.ANKLE_CM - 4.0)[0]
    pts = []
    for i in range(11):
        u = u0 + (u1 - u0) * i / 10
        top = FS._interp(s.table, u) * 0.75
        pts += [cam(s.hw(u), u, s.sole_t + 0.6 + (top - 0.6) * k / 5) for k in range(6)]
    xs, ys = [p[0] + 100 - ax for p in pts], [p[1] + GROUND for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


# ------------------------------------------------------------------ the picture shown to Claude

def _lines_svg(g: dict) -> str:
    """The solid drawn plainly, with its construction lines, over a pale leg band."""
    out = ['<rect x="-100" y="-150" width="400" height="410" fill="#f6f4ef"/>',
           '<rect x="62" y="-150" width="76" height="350" fill="#e4e1db"/>',
           f'<path d="{path(g["sole"])}" fill="#cfcac0" stroke="#8a847a" stroke-width="2"/>',
           f'<path d="{path(g["upper"])}" fill="#ffffff" fill-opacity="0.85" stroke="#5a554d" stroke-width="2.5"/>']
    if g["welt"]:
        out.append(f'<path d="{path(g["welt"], close=False)}" fill="none" stroke="#8a847a" stroke-width="1.6"/>')
    out += [f'<path d="{path(g["centre"], close=False)}" fill="none" stroke="#b0552d" stroke-width="1.6" '
            'stroke-dasharray="5 4"/>',
            f'<path d="{path(g["rim"])}" fill="none" stroke="#2f6f9a" stroke-width="2"/>',
            f'<path d="{path(g["toe_line"], close=False)}" fill="none" stroke="#3c8a4a" stroke-width="1.8"/>',
            f'<path d="{path(g["side_mid"], close=False)}" fill="none" stroke="#8a4fb0" stroke-width="1.6" '
            'stroke-dasharray="2 3"/>']
    for k in ("lace_l", "lace_r", "lace_end"):
        if k in g:
            out.append(f'<path d="{path(g[k], close=False)}" fill="none" stroke="#c9861a" stroke-width="1.8"/>')
    return "".join(out)


@cache
def guide_png(style: str, turn: float = TURN) -> bytes:
    """guide.png: an ordinary shoe of the style straight on (left) and turned (right), from the solid."""
    svg = (f'<svg xmlns="{drawn.SVG_NS}" viewBox="0 0 820 415" width="984" height="498">'
           '<rect width="820" height="415" fill="#ffffff"/>'
           f'<g transform="translate(100,152)">{_lines_svg(geometry(style, 0.0))}</g>'
           f'<g transform="translate(520,152)">{_lines_svg(geometry(style, turn))}</g></svg>')
    return drawn.render_png(svg, 984, 498)


def guide_text(style: str, turn: float = TURN) -> str:
    """The turned panel's lines, in the frame's coordinates, for the prompt."""
    g = geometry(style, turn)
    lines = [
        f"- grey, the sole's whole outline (the upper hides all of it except the band along the bottom): {path(g['sole'])}",
        f"- dark, the upper's outline: {path(g['upper'])}",
        f"- grey line, where the upper meets the sole, the part you see: {path(g['welt'], close=False)}",
        f"- dashed red-brown, the line down the middle of the vamp, from the instep to the toe tip: "
        f"{path(g['centre'], close=False)}",
        f"- blue, the collar's edge round the opening: {path(g['rim'])}",
        f"- green, where the toe box begins (below it is the toe box's dome; a toe cap's seam is near it): "
        f"{path(g['toe_line'], close=False)}",
        f"- dotted purple, the middle height of the inner side, from the heel to the toe (side logos and stripes sit about "
        f"here): {path(g['side_mid'], close=False)}"]
    if "lace_l" in g:
        lines.append(f"- orange, the lacing's two edges and where it ends: {path(g['lace_l'], close=False)} | "
                     f"{path(g['lace_r'], close=False)} | {path(g['lace_end'], close=False)}")
    return "\n".join(lines)


# ------------------------------------------------------------------ the computed turn

def _grids(style: str, turn: float):
    """The solid as grids of points, each seen in the frame at `turn`, with how near the camera each is: the top of the
    upper, the sole's two walls and, for a boot, a shaft tall enough for any drawing (upright round the leg)."""
    s = Solid.of(style)
    cam = s.camera(turn)
    ax = cam(0.0, FS.ANKLE_U, s.sole_t + FS.ANKLE_CM - 4.0)[0]
    us = [i / 120 for i in range(121)]
    grids = [[[(s.hw(u) * s.inset * sh, u, s.sole_t + FS._interp(s.table, u) * math.sin(math.acos(max(-1, min(1, sh)))))
               for sh in (-1 + j / 30 for j in range(61))] for u in us]]
    grids += [[[(side * s.hw(u), u, s.sole_t * k / 6) for k in range(7)] for u in us] for side in (-1, 1)]
    if s.shaft:
        rx, ru, h0, h1 = 4.7 * FS.SHAFT_RIM, 5.2 * FS.SHAFT_RIM, s.sole_t + 2.0, max(s.shaft, 30.0)
        grids.append([[(rx * math.cos(2 * math.pi * k / 48), 0.2 + ru * math.sin(2 * math.pi * k / 48) / FS.LENGTH,
                        h0 + (h1 - h0) * m / 24) for m in range(25)] for k in range(49)])
    out = []
    for g in grids:
        pts = np.array(g, dtype=float)
        flat = pts.reshape(-1, 3)
        xy = np.array([cam(*q) for q in flat]) + np.array([100 - ax, GROUND])
        near = np.array([cam.near(*q) for q in flat])
        out.append((xy.reshape(pts.shape[0], pts.shape[1], 2), near.reshape(pts.shape[0], pts.shape[1])))
    return out


class _Exact:
    """Each point of a straight-on drawing found on the nearest visible triangle of the solid under it, and carried to
    the same place on that triangle turned. A point outside the solid moves as the nearest points of it do."""

    def __init__(self, style: str, turn: float):
        t0, t1, near = [], [], []
        for (a, na), (b, _) in zip(_grids(style, 0.0), _grids(style, turn), strict=True):
            r, c = a.shape[:2]
            for i in range(r - 1):
                for j in range(c - 1):
                    for tri in (((i, j), (i + 1, j), (i, j + 1)), ((i + 1, j), (i + 1, j + 1), (i, j + 1))):
                        t0.append([a[q] for q in tri])
                        t1.append([b[q] for q in tri])
                        near.append(sum(na[q] for q in tri) / 3)
        self.t0, self.t1, self.near = np.array(t0), np.array(t1), np.array(near)
        self.v0, self.d = self.t0.reshape(-1, 2), (self.t1 - self.t0).reshape(-1, 2)
        self.cells = self._index()
        keys = np.floor(self.v0 / self.CELL).astype(int)
        vcells: dict = {}
        for n, (i, j) in enumerate(keys):
            vcells.setdefault((int(i), int(j)), []).append(n)
        self.vcells = {k: np.array(v) for k, v in vcells.items()}

    CELL = 6.0   # frame units: the index's cells

    def _index(self) -> dict:
        """Which triangles' boxes (straight on) overlap each CELL-sized square of the frame."""
        lo, hi = self.t0.min(axis=1), self.t0.max(axis=1)
        cells: dict = {}
        for t, ((x0, y0), (x1, y1)) in enumerate(zip(lo, hi, strict=True)):
            for i in range(int(np.floor(x0 / self.CELL)), int(np.floor(x1 / self.CELL)) + 1):
                for j in range(int(np.floor(y0 / self.CELL)), int(np.floor(y1 / self.CELL)) + 1):
                    cells.setdefault((i, j), []).append(t)
        return {k: np.array(v) for k, v in cells.items()}

    def many(self, pts) -> np.ndarray:
        return np.array([self(x, y) for x, y in pts], dtype=float)

    def __call__(self, x: float, y: float) -> tuple[float, float]:
        idx = self.cells.get((int(np.floor(x / self.CELL)), int(np.floor(y / self.CELL))))
        if idx is not None:
            a, b, c = self.t0[idx, 0], self.t0[idx, 1], self.t0[idx, 2]
            v0, v1, v2 = b - a, c - a, np.array([x, y]) - a
            den = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
            ok = np.abs(den) > 1e-9
            den = np.where(ok, den, 1.0)
            w1 = (v2[:, 0] * v1[:, 1] - v1[:, 0] * v2[:, 1]) / den
            w2 = (v0[:, 0] * v2[:, 1] - v2[:, 0] * v0[:, 1]) / den
            w0 = 1 - w1 - w2
            inside = ok & (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
            if inside.any():
                k = np.where(inside)[0]
                best = k[np.argmax(self.near[idx[k]])]
                t = idx[best]
                q = w0[best] * self.t1[t, 0] + w1[best] * self.t1[t, 1] + w2[best] * self.t1[t, 2]
                return float(q[0]), float(q[1])
        p = np.array([x, y])
        ci, cj = int(np.floor(x / self.CELL)), int(np.floor(y / self.CELL))
        nn = None
        for ring in range(1, 12):   # the vertices in a widening block of squares round the point: any vertex outside
            parts = [self.vcells[(i, j)] for i in range(ci - ring, ci + ring + 1)   # the block is at least ring * CELL
                     for j in range(cj - ring, cj + ring + 1) if (i, j) in self.vcells]   # away, so once the sixth
            near = np.concatenate(parts) if parts else np.array([], dtype=int)   # nearest inside is nearer, they are
            if len(near) >= 6:                                                   # the six nearest of all
                d2 = ((self.v0[near] - p) ** 2).sum(axis=1)
                six = np.argpartition(d2, 5)[:6]
                if d2[six].max() <= (ring * self.CELL) ** 2:
                    nn = near[six]
                    break
        if nn is None:
            d2 = ((self.v0 - p) ** 2).sum(axis=1)
            nn = np.argpartition(d2, 6)[:6]
        d2 = ((self.v0[nn] - p) ** 2).sum(axis=1)
        w = 1.0 / (d2 + 1.0)
        m = (self.d[nn] * w[:, None]).sum(axis=0) / w.sum()
        return float(x + m[0]), float(y + m[1])


@cache
def _exact(style: str, turn: float) -> _Exact:
    return _Exact(style, turn)


EASE = 30.0   # frame units above the hinge over which the turn eases to nothing


class Turn:
    """Where a point of a straight-on drawing goes when the shoe turns: the exact turn (`_Exact`) fitted by one smooth
    movement over the drawing's box (a cubic in x and y), so smooth curves stay smooth. Above `hinge` (a low shoe's
    opening, a boot's instep) it eases to nothing, so a collar or a shaft stays upright round the leg. `mirror` turns
    the viewer's right shoe, toe to the right."""

    def __init__(self, style: str, turn: float, box: tuple[float, float, float, float], hinge: float,
                 mirror: bool = False, step: float = 4.0):
        exact = _exact(style, turn)
        x0, y0, x1, y1 = box
        src = np.array([(x, y) for y in np.arange(max(y0, hinge), y1 + step, step) for x in np.arange(x0, x1 + step, step)])
        dst = exact.many(src)
        self.c, self.s = np.array([(x0 + x1) / 2, (y0 + y1) / 2]), max(x1 - x0, y1 - y0) / 2
        a = self._basis(src)
        self.kx = np.linalg.lstsq(a, dst[:, 0] - src[:, 0], rcond=None)[0]
        self.ky = np.linalg.lstsq(a, dst[:, 1] - src[:, 1], rcond=None)[0]
        self.hinge, self.mirror = hinge, mirror

    def _basis(self, p):
        u, v = ((np.atleast_2d(p) - self.c) / self.s).T
        return np.stack([np.ones_like(u), u, v, u * u, u * v, v * v, u ** 3, u * u * v, u * v * v, v ** 3], axis=1)

    def __call__(self, x: float, y: float) -> tuple[float, float]:
        xm = 200.0 - x if self.mirror else x
        b = self._basis((xm, y))[0]
        t = min(1.0, max(0.0, (y - (self.hinge - EASE)) / EASE))
        t = t * t * (3 - 2 * t)
        nx, ny = xm + t * float(b @ self.kx), y + t * float(b @ self.ky)
        return (200.0 - nx if self.mirror else nx), ny


def _num(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


_KEEP = ("fill", "stroke", "stroke-linejoin", "stroke-linecap", "stroke-dasharray", "opacity", "fill-opacity",
         "stroke-opacity", "fill-rule")


FOLLOW = 0.5    # a moved segment follows the turn to within this (frame units), split in halves until it does
FOLLOW_DEPTH = 6   # ... at most this many times (64 pieces)
COARSE = 2.0       # ... or to within this, for a drawing whose turn would otherwise be longer than a drawing may be


def _bez(c, t: float) -> tuple[float, float]:
    """A point of a cubic Bezier (four control points)."""
    u = 1.0 - t
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = c
    a, b, d, e = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
    return a * x0 + b * x1 + d * x2 + e * x3, a * y0 + b * y1 + d * y2 + e * y3


def _halves(c):
    """A cubic Bezier split at its middle (de Casteljau)."""
    mid = lambda a, b: ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)   # noqa: E731
    p01, p12, p23 = mid(c[0], c[1]), mid(c[1], c[2]), mid(c[2], c[3])
    p012, p123 = mid(p01, p12), mid(p12, p23)
    m = mid(p012, p123)
    return (c[0], p01, p012, m), (m, p123, p23, c[3])


def _follows(c, w, move, follow: float) -> bool:
    """Whether the cubic with the moved control points `w` lies on the moved curve `c`, to within `follow`."""
    for t in (0.25, 0.5, 0.75):
        a, b = _bez(w, t), move(*_bez(c, t))
        if (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 > follow * follow:
            return False
    return True


def _moved(c, move, follow: float = FOLLOW, depth: int = 0) -> list:
    """The moved cubic as pieces of moved control points: one piece when moving its control points carries the curve
    with the turn, else its halves, each moved the same way. A long edge from a boot's shaft down into its foot stays
    on the turned surface instead of leaning from its unmoved top to its moved bottom."""
    w = tuple(move(*q) for q in c)
    if depth >= FOLLOW_DEPTH or _follows(c, w, move, follow):
        return [w]
    a, b = _halves(c)
    return _moved(a, move, follow, depth + 1) + _moved(b, move, follow, depth + 1)


def _cubic_text(pieces) -> str:
    return " ".join("C" + " ".join(f"{_num(x)} {_num(y)}" for x, y in w[1:]) for w in pieces)


def warp_fragment(fragment: str, move, follow: float = FOLLOW) -> str:
    """Bare SVG elements (a drawing's part, already made safe) with every point moved by `move`: each shape becomes a
    path in absolute coordinates, its transforms applied, its paint and stroke width kept. A segment the turn bends is
    split until it follows the turn (`_moved`); one it carries whole keeps its kind (a line stays a line)."""
    if not fragment.strip():
        return fragment
    import svgelements as se  # only here: the rest of the drawing code needs no SVG geometry

    svg = se.SVG.parse(io.StringIO(f'<svg xmlns="{drawn.SVG_NS}">{fragment}</svg>'), reify=True)
    out = []
    for el in svg.elements():
        if not isinstance(el, se.Shape) or isinstance(el, se.SVG):
            continue
        p = se.Path(el)
        p.reify()
        p.approximate_arcs_with_cubics()
        d = []
        for seg in p:
            if isinstance(seg, se.Move):
                d.append("M" + " ".join(map(_num, move(seg.end.x, seg.end.y))))
            elif isinstance(seg, se.Close):
                if seg.start is not None and seg.end is not None and (seg.start.x, seg.start.y) != (seg.end.x, seg.end.y):
                    a, b = (seg.start.x, seg.start.y), (seg.end.x, seg.end.y)   # the closing edge, bent with the turn
                    pieces = _moved((a, _third(a, b, 1), _third(a, b, 2), b), move, follow)
                    if len(pieces) > 1:
                        d.append(_cubic_text(pieces))
                d.append("Z")
            elif isinstance(seg, se.Line):
                a, b = (seg.start.x, seg.start.y), (seg.end.x, seg.end.y)
                pieces = _moved((a, _third(a, b, 1), _third(a, b, 2), b), move, follow)
                d.append("L" + " ".join(map(_num, pieces[0][3])) if len(pieces) == 1 else _cubic_text(pieces))
            elif isinstance(seg, se.CubicBezier):
                c = tuple((q.x, q.y) for q in (seg.start, seg.control1, seg.control2, seg.end))
                d.append(_cubic_text(_moved(c, move, follow)))
            elif isinstance(seg, se.QuadraticBezier):
                a, q, b = (seg.start.x, seg.start.y), (seg.control.x, seg.control.y), (seg.end.x, seg.end.y)
                c = (a, (a[0] + 2 * (q[0] - a[0]) / 3, a[1] + 2 * (q[1] - a[1]) / 3),
                     (b[0] + 2 * (q[0] - b[0]) / 3, b[1] + 2 * (q[1] - b[1]) / 3), b)
                pieces = _moved(c, move, follow)
                d.append("Q" + " ".join(f"{_num(x)} {_num(y)}" for x, y in (move(*q), move(*b)))
                         if len(pieces) == 1 else _cubic_text(pieces))
        if not d:
            continue
        attrs = [f'{k}="{el.values[k]}"' for k in _KEEP if el.values.get(k) not in (None, "")]
        if el.stroke is not None and el.stroke.value is not None and str(el.stroke) not in ("None", "none"):
            attrs.append(f'stroke-width="{_num(float(el.implicit_stroke_width or el.stroke_width or 1.0))}"')
        if el.fill is None or el.fill.value is None or str(el.fill) in ("None", "none"):
            attrs = [a for a in attrs if not a.startswith("fill=")] + ['fill="none"']
        out.append(f'<path d="{" ".join(d)}" {" ".join(attrs)}/>')
    return "".join(out)


def _third(a, b, k: int) -> tuple[float, float]:
    return a[0] + (b[0] - a[0]) * k / 3, a[1] + (b[1] - a[1]) * k / 3


def hinge_of(sheet, box) -> float:
    """The y above which the turn moves nothing: the sheet's instep for a boot, its opening's front for a low shoe."""
    height = ((sheet or {}).get("silhouette") or {}).get("height")
    return float((sheet or {}).get("instep_y" if height in ("ankle", "boot") else "opening_front_y") or box[1])


def turn_side(side: drawn.Side, style: str, sheet, turn: float = TURN, mirror: bool = False) -> drawn.Side:
    """One shoe of a straight-on drawing turned out (`mirror`: the viewer's right shoe, drawn on its own), made safe.
    The hinge above which nothing moves is the sheet's instep for a boot, its opening's front for a low shoe. A
    drawing whose turn comes out longer than a drawing may be is turned again with its segments split more coarsely
    (to within 2 units); `drawn.DrawingError` if it is still too long."""
    box = drawn.measure(side)["box"]
    if box is None:
        raise drawn.DrawingError("The drawing has nothing to turn.")
    if mirror:
        box = (200.0 - box[2], box[1], 200.0 - box[0], box[3])
    move = Turn(style, turn, box, hinge_of(sheet, box), mirror=mirror)
    for follow in (FOLLOW, COARSE):
        behind, front = warp_fragment(side.behind, move, follow), warp_fragment(side.front, move, follow)
        if len(behind) + len(front) <= drawn.MAX_CHARS or follow == COARSE:
            return drawn.side({"behind": behind, "front": front})


# ------------------------------------------------------------------ the shaft, kept upright

UPRIGHT_ROWS = 20.0     # frame units of shaft above the hinge's ease, at least, for the check to apply
UPRIGHT_TOL = 8.0       # how far (frame units) the shaft's sides may stand from the computed turn's


def _rows(side: drawn.Side, k: int = 2) -> tuple[np.ndarray, float]:
    """The shoe's silhouette in the turned frame, k pixels a unit: a mask, and the y of its first row."""
    import io as _io

    from PIL import Image
    x0, y0, w, h = -100, -150, 400, 400
    svg = (f'<svg xmlns="{drawn.SVG_NS}" viewBox="{x0} {y0} {w} {h}" width="{w * k}" height="{h * k}">'
           f'{side.behind}{side.front}</svg>')
    a = np.asarray(Image.open(_io.BytesIO(drawn.render_png(svg, w * k, h * k))).convert("RGBA"))
    return a[..., 3] > 128, float(y0)


def upright_problems(side: drawn.Side, computed: drawn.Side, sheet, which: str = "left") -> list[str]:
    """Whether a turned drawing's shaft (a boot's, above the hinge's ease) stands where the computed turn leaves it,
    upright: its sides within UPRIGHT_TOL of the computed turn's. In plain words for the next check; empty when it
    does, or when the shoe has too little above the hinge to tell (a low shoe)."""
    k = 2
    box = drawn.measure(computed)["box"]
    if box is None:
        return []
    stop = hinge_of(sheet, box) - EASE
    (md, y0), (mc, _) = _rows(side, k), _rows(computed, k)
    rows = [r for r in range(md.shape[0]) if y0 + r / k < stop and mc[r].any()]
    if len(rows) < UPRIGHT_ROWS * k:
        return []
    out_l, out_r = [], []
    for r in rows:
        xd, xc = np.flatnonzero(md[r]), np.flatnonzero(mc[r])
        if not len(xd):
            continue
        out_l.append((xc[0] - xd[0]) / k)    # > 0: the drawing's left side further left than the computed turn's
        out_r.append((xd[-1] - xc[-1]) / k)  # > 0: its right side further right
    if not out_l:
        return []
    found = []
    for name, d in (("left", np.array(out_l)), ("right", np.array(out_r))):
        far = float(np.percentile(np.abs(d), 90))
        if far > UPRIGHT_TOL:
            way = "out" if float(np.median(d)) > 0 else "in"
            found.append(f"{name} side up to {far:.0f} units {way}")
    if not found:
        return []
    return [f"The {which} shoe's shaft leans or widens: above y = {stop:.0f}, where the turn leaves the shoe as it is "
            f"straight on, its {' and its '.join(found)} from where the turn puts it. The shaft stands upright round "
            "the leg; only the foot below it turns. Keep the shaft's outline, and its elastic sides, tabs and seams, "
            "as they are straight on (as turned.png has them, where it is shown), and let the foot's outline leave "
            "the shaft's smoothly at the ankle."]
