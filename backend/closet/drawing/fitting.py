"""Fitting a garment's drawing onto the wearer, for the outfit figure only.

The item drawings are fashion flats: a garment laid out with its sleeves hanging beside it, drawn wider and longer
than it looks worn. The figure draws a person and fits each garment to them, without changing the garment's own
drawing: the template's Shape is built as usual and every point of it is moved by a smooth map (`warp`) before it
is drawn. A top's body is scaled about the middle of the figure; each sleeve is turned and stretched as one piece
so its shoulder point lands on the wearer's shoulder and its cuff on the arm; near the armhole the two are blended,
so the drawing stays in one piece. Shapes only use absolute M, L, Q, C and Z commands with "x,y" pairs, so a path
is warped point by point (curve control points with their curve).
"""
from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass, replace

from .templates import CX, Part, Shape

Point = tuple[float, float]
PAIR = re.compile(r"(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)")


def _f(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def warp_path(d: str, fn: Callable[[Point], Point]) -> str:
    """The path with every point moved by `fn`."""
    def move(m):
        x, y = fn((float(m[1]), float(m[2])))
        return f"{_f(x)},{_f(y)}"
    return PAIR.sub(move, d)


def points(d: str, steps: int = 8) -> list[Point]:
    """The points along a path (curves sampled), as one run; good enough for distances and extents."""
    out: list[Point] = []
    cur: Point = (0.0, 0.0)
    for cmd, args in re.findall(r"([MLQCZ])([^MLQCZ]*)", d):
        pts = [(float(a), float(b)) for a, b in PAIR.findall(args)]
        if cmd in "ML":
            out += pts
        elif cmd == "Q":
            for i in range(0, len(pts) - 1, 2):
                p1, p2 = pts[i], pts[i + 1]
                out += [((1 - t) ** 2 * cur[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
                         (1 - t) ** 2 * cur[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1])
                        for t in (j / steps for j in range(1, steps + 1))]
                cur = p2
            continue
        elif cmd == "C":
            for i in range(0, len(pts) - 2, 3):
                p1, p2, p3 = pts[i:i + 3]
                out += [tuple((1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t * t * c + t ** 3 * e
                              for a, b, c, e in zip(cur, p1, p2, p3, strict=True))
                        for t in (j / steps for j in range(1, steps + 1))]
                cur = p3
            continue
        if pts:
            cur = pts[-1]
    return out


def _seg_dist(p: Point, a: Point, b: Point) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    m = dx * dx + dy * dy
    t = 0.0 if m == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / m))
    return math.hypot(p[0] - a[0] - dx * t, p[1] - a[1] - dy * t)


def inside(p: Point, poly: list[Point]) -> bool:
    x, y = p
    hit = False
    for i in range(len(poly)):
        (x0, y0), (x1, y1) = poly[i - 1], poly[i]
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            hit = not hit
    return hit


def signed_distance(p: Point, poly: list[Point]) -> float:
    """How far `p` is inside the polygon (negative: outside)."""
    d = min(_seg_dist(p, poly[i - 1], poly[i]) for i in range(len(poly)))
    return d if inside(p, poly) else -d


@dataclass
class Sleeve:
    """One sleeve of a top's Shape: its polygon, which side it is on (-1 the viewer's left, 1 the right), and its
    four corners: the shoulder point it hangs from, the outer and the inner corner of its opening, and the
    underarm. Every sleeve path is drawn the same way: M shoulder Q . . L outer L inner L underarm C . . shoulder Z."""
    poly: list[Point]
    side: int
    shoulder: Point
    outer: Point
    inner: Point
    armpit: Point

    @property
    def cuff(self) -> Point:
        return ((self.outer[0] + self.inner[0]) / 2, (self.outer[1] + self.inner[1]) / 2)

    @property
    def half(self) -> float:
        return math.dist(self.outer, self.inner) / 2

    def at(self, u: float, v: float) -> Point:
        """A point of the sleeve: `u` from its armhole (0) to its opening (1), `v` from its outer (0) to its inner
        edge (1)."""
        return _bilinear((self.shoulder, self.outer, self.inner, self.armpit), u, v)


def sleeves(shape: Shape) -> list[Sleeve]:
    out = []
    for d, _ in shape.sleeves:
        pairs = [(float(a), float(b)) for a, b in PAIR.findall(d)]
        if len(pairs) < 6:
            continue
        poly = points(d)
        side = 1 if sum(x for x, _ in poly) / len(poly) > CX else -1
        out.append(Sleeve(poly, side, pairs[0], pairs[3], pairs[4], pairs[5]))
    return out


def _bilinear(q, u: float, v: float) -> Point:
    s, o, i, a = q
    return ((1 - u) * (1 - v) * s[0] + u * (1 - v) * o[0] + u * v * i[0] + (1 - u) * v * a[0],
            (1 - u) * (1 - v) * s[1] + u * (1 - v) * o[1] + u * v * i[1] + (1 - u) * v * a[1])


def _unbilinear(q, p: Point) -> tuple[float, float]:
    """(u, v) of `p` in the quad `q` (Newton's method; points outside it are carried on past its edges)."""
    s, o, i, a = q
    u = v = 0.5
    for _ in range(12):
        x, y = _bilinear(q, u, v)
        ex, ey = x - p[0], y - p[1]
        du = ((1 - v) * (o[0] - s[0]) + v * (i[0] - a[0]), (1 - v) * (o[1] - s[1]) + v * (i[1] - a[1]))
        dv = ((1 - u) * (a[0] - s[0]) + u * (i[0] - o[0]), (1 - u) * (a[1] - s[1]) + u * (i[1] - o[1]))
        det = du[0] * dv[1] - du[1] * dv[0]
        if abs(det) < 1e-9:
            break
        u -= (ex * dv[1] - ey * dv[0]) / det
        v -= (du[0] * ey - du[1] * ex) / det
        if abs(ex) + abs(ey) < 1e-3:
            break
    return u, v


def quad_map(src: Sleeve, dst: tuple[Point, Point, Point, Point]) -> Callable[[Point], Point]:
    """The map taking the sleeve's four corners onto `dst` (shoulder, outer, inner, underarm), straight between."""
    q = (src.shoulder, src.outer, src.inner, src.armpit)

    def fn(p: Point) -> Point:
        return _bilinear(dst, *_unbilinear(q, p))
    return fn


def affine(src: tuple[Point, Point], dst: tuple[Point, Point], across: float) -> Callable[[Point], Point]:
    """The map taking the segment `src` onto `dst` (turned and stretched along it), scaling across it by `across`."""
    (a0, a1), (b0, b1) = src, dst
    la = math.hypot(a1[0] - a0[0], a1[1] - a0[1]) or 1.0
    lb = math.hypot(b1[0] - b0[0], b1[1] - b0[1])
    g = ((a1[0] - a0[0]) / la, (a1[1] - a0[1]) / la)
    h = ((b1[0] - b0[0]) / (lb or 1.0), (b1[1] - b0[1]) / (lb or 1.0))
    s = lb / la

    def fn(p: Point) -> Point:
        u = (p[0] - a0[0]) * g[0] + (p[1] - a0[1]) * g[1]
        v = -(p[0] - a0[0]) * g[1] + (p[1] - a0[1]) * g[0]
        u, v = u * s, v * across
        return (b0[0] + u * h[0] - v * h[1], b0[1] + u * h[1] + v * h[0])
    return fn


def blend(body: Callable[[Point], Point], parts: list[tuple[list[Point], Callable[[Point], Point]]],
          width: float) -> Callable[[Point], Point]:
    """One smooth map: `body` everywhere but in the polygons of `parts` (their edges included), each of which has its
    own map; outside a polygon the two are blended over `width`."""
    def fn(p: Point) -> Point:
        q = body(p)
        for poly, own in parts:
            w = max(0.0, min(1.0, 1.0 + signed_distance(p, poly) / width))
            if w > 0:
                w = w * w * (3 - 2 * w)
                r = own(p)
                q = (q[0] + (r[0] - q[0]) * w, q[1] + (r[1] - q[1]) * w)
        return q
    return fn


def warp(shape: Shape, fn: Callable[[Point], Point], deg: Callable[[float], float] | None = None,
         radius: float = 1.0, box: Callable[[Point], Point] | None = None) -> Shape:
    """The shape with every point moved by `fn`. `deg` turns the sleeves' cloth to their new angle; dots and snaps
    keep their place on the cloth and are scaled by `radius`; the body's box is moved by `box` (default `fn`), as
    wide as its lower edge."""
    def path(d: str) -> str:
        return warp_path(d, fn)

    def part(p: Part) -> Part:
        return replace(p, d=path(p.d))

    outline = path(shape.outline)
    pts = points(outline) + [q for p in shape.parts for q in points(path(p.d))]
    xs, ys = [x for x, _ in pts], [y for _, y in pts]
    bx0, by0, bx1, by1 = shape.body_box
    (_, y0), (x0, _), (x1, y1) = (box or fn)((bx0, by0)), (box or fn)((bx0, by1)), (box or fn)((bx1, by1))
    fronts = None
    if shape.fronts:
        fronts = ([fn(q) for q in shape.fronts[0]], shape.fronts[1])
    return replace(
        shape, outline=outline, parts=[part(p) for p in shape.parts], lines=[path(d) for d in shape.lines],
        dots=[(*fn((x, y)), r * radius) for x, y, r in shape.dots],
        body_box=(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)),
        bbox=(min(xs), min(ys), max(xs), max(ys)),
        anchors={k: fn(v) for k, v in shape.anchors.items()},
        behind=[part(p) for p in shape.behind],
        sleeves=[(path(d), deg(a) if deg else a) for d, a in shape.sleeves],
        seams=[path(d) for d in shape.seams], folds=[path(d) for d in shape.folds],
        snaps=[(*fn((x, y)), r * radius) for x, y, r in shape.snaps],
        blocks=[path(d) for d in shape.blocks], fronts=fronts)
