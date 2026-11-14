"""One shoe seen from the front, for the outfit drawn as worn.

The item's own drawing is a side view (`templates.sneaker`); a figure seen from the front needs its shoes seen
from the front too. The shoe is a small solid made from the same style words (`style`, `sandal`, `shaft`,
`toe_cap`, `strap`, `laces`, `eyelets`, `sole`, `tread`, `toe`): a sole the shape of a footprint and an upper
whose cross-sections rise from the toe to the collar, with a boot's shaft round the ankle. It is turned
TURN degrees toe out and looked at from LOOK degrees above, as a fashion illustration shows a standing figure's
shoes, so the toe box and the front of the sole face the viewer and the instep runs back up under the trouser
hem. The outline is the convex hull of the solid's points as seen, so it is always one clean shape.

Coordinates: centimetres scaled by `px` (the figure's pixels per cm), x to the viewer's right, y down. The
shoe is drawn toe to the viewer's left (the viewer's left foot); the other foot is its mirror image. The
origin is the middle of the ball of the foot, the toe tip of the sole touches y = 0 (the ground line), and
the shoe is centred on x = 0 at the ball.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .illustrate import INK, Spec, _hex, _rgb, luminance, shade

LENGTH = 29.5          # one shoe, toe to heel, in cm: a men's UK 9
BALL = 0.72            # the ball of the foot, as a share of the length from the heel: the shoe is centred on it
LOOK = 24.0            # degrees the viewer looks down at the shoes from
TURN = 11.0            # degrees each toe is turned out
METAL = "#c9a85c"
LINING = "#3a342e"     # the inside of a shoe: a dark warm grey, a little of the shoe's colour in it
FORM_ANKLE_CM = 13.0   # how far the form's tonal ankle stands above the sole, when it is drawn

# per style: half width at the ball, sole thickness, how the upper's top rises from the toe (share of the length
# from the heel, height above the sole in cm), and how high the collar of a boot or high top stands (cm above the
# ground); 0 for a low shoe.
_LOW = [(0.0, 6.8), (0.12, 7.4), (0.3, 6.4), (0.46, 8.0), (0.56, 7.2), (0.7, 5.6), (0.85, 4.3), (0.95, 3.0), (1.0, 1.0)]
_DRESS = [(0.0, 6.2), (0.12, 6.6), (0.3, 5.6), (0.46, 6.6), (0.56, 6.1), (0.7, 4.7), (0.85, 3.3), (0.95, 2.2), (1.0, 0.8)]
_SLIP = [(0.0, 6.2), (0.12, 6.6), (0.3, 5.8), (0.46, 6.6), (0.56, 6.2), (0.7, 5.2), (0.85, 4.1), (0.95, 2.9), (1.0, 1.0)]
_BOOT = [(0.0, 7.6), (0.12, 7.8), (0.3, 7.6), (0.46, 8.6), (0.56, 7.6), (0.7, 6.0), (0.85, 4.6), (0.95, 3.2), (1.0, 1.1)]
STYLES = {
    #               ball  sole  top     shaft
    "low_sneaker": (5.4, 2.5, _LOW, 0.0),
    "runner": (5.5, 3.4, _LOW, 0.0),
    "slip_on": (5.2, 2.1, _SLIP, 0.0),
    "high_top": (5.4, 2.6, _LOW, 16.5),
    "loafer": (4.9, 1.1, _DRESS, 0.0),
    "derby": (4.9, 1.3, _DRESS, 0.0),
    "oxford": (4.8, 1.1, _DRESS, 0.0),
    "boot": (5.3, 2.0, _BOOT, 16.0),
    "chelsea_boot": (5.0, 1.5, _BOOT, 12.5),
    "sandal": (5.1, 2.2, None, 0.0),
}


@dataclass
class FrontShoe:
    """A shoe drawn from the front: its outline (for the figure's canvas) and its drawing, both in its own
    coordinates; `anchors` name the points the figure places it by."""
    outline: str
    bbox: tuple[float, float, float, float]
    anchors: dict[str, tuple[float, float]] = field(default_factory=dict)
    body: str = ""
    defs: str = ""
    ankle: bool = False   # the form's ankle is drawn in it


def _interp(table, u: float) -> float:
    if u <= table[0][0]:
        return table[0][1]
    for (u0, v0), (u1, v1) in zip(table, table[1:], strict=False):
        if u <= u1:
            t = (u - u0) / (u1 - u0)
            return v0 + (v1 - v0) * t
    return table[-1][1]


def _hull(pts):
    """The convex hull of points, anticlockwise (Andrew's monotone chain)."""
    pts = sorted(set((round(x, 2), round(y, 2)) for x, y in pts))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _mix(a: str, b: str, t: float) -> str:
    """a, t of the way to b."""
    return _hex(tuple(x + (y - x) * t for x, y in zip(_rgb(a), _rgb(b), strict=True)))


def _path(pts, close=True) -> str:
    return "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts) + (" Z" if close else "")


class _View:
    """Turns points on the shoe (x across, u from heel 0 to toe 1, h above the ground, in cm) into the drawing."""

    def __init__(self, px: float):
        self.px = px
        self.ct, self.st = math.cos(math.radians(TURN)), math.sin(math.radians(TURN))
        self.cl, self.sl = math.cos(math.radians(LOOK)), math.sin(math.radians(LOOK))
        self.y0 = 0.0
        self.y0 = self.raw(0.0, 1.0, 0.0)[1]

    def raw(self, x: float, u: float, h: float) -> tuple[float, float]:
        z = (u - BALL) * LENGTH
        xr = x * self.ct - z * self.st       # the toe swings out, to the viewer's left
        zr = x * self.st + z * self.ct
        return xr * self.px, (zr * self.sl - h * self.cl) * self.px - self.y0

    def __call__(self, x: float, u: float, h: float) -> tuple[float, float]:
        return self.raw(x, u, h)


def _half_width(u: float, ball: float, toe: str) -> float:
    """Half the footprint's width at u (0 heel, 1 toe), in cm."""
    long_toe = {"almond": 0.06, "chisel": 0.08, "pointed": 0.12}.get(toe, 0.0)
    if u < 0.08:
        return 0.68 * ball * math.sqrt(max(0.0, 1 - ((0.08 - u) / 0.08) ** 2))
    if u < BALL:
        t = (u - 0.08) / (BALL - 0.08)
        return ball * (0.68 + 0.32 * t ** 1.6)
    t = (u - BALL) / (1 - BALL)
    return ball * math.sqrt(max(0.0, 1 - t ** 2)) ** (1 + long_toe * 8)


def front_shoe(spec: Spec, px: float, *, sole_default: str | None = None, uid: str = "fs",
               ankle: str | None = None) -> FrontShoe:
    """The shoe of `spec` from the front, scaled by `px`. With `ankle` (a fill), the form's tonal ankle stands in
    the shoe's opening (FORM_ANKLE_CM above the sole), for a figure whose trousers leave the ankle showing."""
    p = {**spec.params, "lace_color": spec.lace_color}
    style = p.get("style") or ("high_top" if p.get("height") == "high" else "low_sneaker")
    if style not in STYLES:
        style = "low_sneaker"
    ball, sole_t, table, shaft = STYLES[style]
    sole_t *= {"thin": 0.75, "chunky": 1.6}.get(p.get("sole"), 1.0)
    if p.get("tread") == "lug":
        sole_t *= 1.25
    if shaft and p.get("shaft"):
        shaft = max(0.35, min(0.95, float(p["shaft"]))) * LENGTH
    toe = p.get("toe", "round")
    view = _View(px)
    hw = lambda u: _half_width(u, ball, toe)   # noqa: E731
    us = [i / 60 for i in range(61)]
    base = spec.fill.color
    dark = luminance(base) < 0.3
    sole_c = spec.sole_color or sole_default or "#f4f1ea"
    line_c = shade(base, 0.42) if dark else INK
    out: list[str] = []
    defs = ""

    def ln(d, w=1.3, c=None, op=0.9):
        return (f'<path d="{d}" fill="none" stroke="{c or line_c}" stroke-width="{w}" stroke-linecap="round" '
                f'stroke-linejoin="round" opacity="{op}"/>')

    def fill(d, c, edge=True, w=2.2):
        return f'<path d="{d}" fill="{c}"' + (f' stroke="{INK}" stroke-width="{w}" stroke-linejoin="round"' if edge else "") + "/>"

    def contour(h, inset=1.0):
        """The footprint's edge at height h, all the way round."""
        right = [(hw(u) * inset, u, h) for u in us]
        left = [(-hw(u) * inset, u, h) for u in reversed(us)]
        return right + left

    # the sole: everything between the ground and the top of the sole
    sole_pts = [view(*q) for h in (0.0, sole_t) for q in contour(h)]
    sole_d = _path(_hull(sole_pts))
    out.append(fill(sole_d, sole_c))
    defs += f'<clipPath id="{uid}s"><path d="{sole_d}"/></clipPath>'
    if style in ("high_top", "slip_on") or p.get("foxing"):   # the stripe round a vulcanised sole
        line = [view(x, u, sole_t * 0.55) for x, u, _ in contour(0)]
        out.append(f'<g clip-path="url(#{uid}s)">' + ln(_path(line, close=False), 1.1,
                                                         shade(sole_c, -0.3 if luminance(sole_c) > 0.25 else 0.22), 1) + "</g>")
    if p.get("tread") in ("lug", "crepe") or style in ("boot",):   # a thick outsole: its lower part darker
        low = [view(*q) for h in (0.0, sole_t * 0.4) for q in contour(h)]
        c = shade(sole_c, -0.35 if luminance(sole_c) > 0.25 else 0.18)
        out.append(f'<g clip-path="url(#{uid}s)">' + fill(_path(_hull(low)), c, edge=False) + "</g>")

    if style == "sandal":
        out += _sandal(p, view, hw, sole_t, base, sole_c, uid)
        outline_pts = sole_pts + _sandal_points(p, view, hw, sole_t)
        top = sole_t + 4
    else:
        # the upper: a half ellipse across the foot at every step from heel to toe, up to the top line
        inset = 0.93 if style in ("loafer", "derby", "oxford") else 0.97
        upper_pts = []
        for u in us:
            w, h = hw(u) * inset, _interp(table, u)
            for k in range(13):
                a = math.pi * k / 12
                upper_pts.append(view(w * math.cos(a), u, sole_t + h * math.sin(a)))
        ax, au, arx, aru = 0.0, 0.2, 4.7, 5.2        # the ankle: a boot's shaft, the form's ankle
        if shaft:
            for h in (sole_t + 4.0, shaft):
                for k in range(24):
                    a = 2 * math.pi * k / 24
                    upper_pts.append(view(ax + arx * math.cos(a), au + aru * math.sin(a) / LENGTH, h))
        upper_d = _path(_hull(upper_pts))
        out.append(fill(upper_d, base, w=2.4))
        defs += f'<clipPath id="{uid}u"><path d="{upper_d}"/></clipPath>'
        top = max(shaft, sole_t + max(h for _, h in table))
        if style == "high_top" or p.get("toe_cap") == "rubber":   # a rubber toe in the sole's colour
            cap = [view(hw(u) * inset * math.cos(math.pi * k / 12), u, sole_t + _interp(table, u) * math.sin(math.pi * k / 12))
                   for u in us if u >= 0.87 for k in range(13)]
            cap += [view(x, u, sole_t) for x, u, _ in contour(0, inset) if u >= 0.8]
            out.append(f'<g clip-path="url(#{uid}u)">' + fill(_path(_hull(cap)), sole_c, w=1.3) + "</g>")
        out += _opening(p, style, view, hw, inset, table, sole_t, shaft, base, ankle, upper_d, uid)
        out += _details(p, style, view, hw, inset, table, sole_t, shaft, base, line_c, ln, fill)
        outline_pts = sole_pts + upper_pts
    hull = _hull(outline_pts)
    xs, ys = [x for x, _ in hull], [y for _, y in hull]
    if ankle is not None:
        ys.append(view(0.0, 0.2, FORM_ANKLE_CM + sole_t)[1])
    anchors = {"ball": (0.0, view(0.0, BALL, 0.0)[1]), "toe": view(0.0, 1.0, 0.0), "heel": view(0.0, 0.0, 0.0),
               "ground": (0.0, 0.0), "top": (0.0, view(0.0, 0.2, top)[1])}
    return FrontShoe(_path(hull), (min(xs) - 2, min(ys) - 2, max(xs) + 2, max(ys) + 2), anchors, "".join(out), defs,
                     ankle is not None)


def _surface(view, hw, inset, table, sole_t, u, x_share, lift=0.0):
    """A point on the top of the upper at u, x_share of the way out to the side."""
    w, h = hw(u) * inset, _interp(table, u)
    a = math.acos(max(-1.0, min(1.0, x_share)))
    return view(w * x_share, u, sole_t + h * math.sin(a) + lift)


def _opening(p, style, view, hw, inset, table, sole_t, shaft, base, ankle, upper_d, uid):
    """The way in: the collar of a low shoe, or the top of a boot's shaft, with the dark lining inside; and the
    form's ankle standing in it when asked for."""
    out = []
    lining = _mix(base, LINING, 0.82)
    if shaft:
        rim = [view(4.7 * math.cos(2 * math.pi * k / 32) * 0.9, 0.2 + 5.2 * 0.9 * math.sin(2 * math.pi * k / 32) / LENGTH,
                    shaft) for k in range(32)]
    else:
        rim = []
        for k in range(32):
            a = 2 * math.pi * k / 32
            u = 0.27 + 0.2 * math.sin(a)                     # from just inside the heel to the throat
            x = hw(u) * inset * 0.82 * math.cos(a)
            h = sole_t + _interp(table, 0.04) - 0.5 + (0.6 if math.sin(a) > 0 else 0) * math.sin(a)
            rim.append(view(x, u, h))
    rim_d = _path(rim)
    out.append(f'<path d="{rim_d}" fill="{lining}" stroke="{INK}" stroke-width="1.4" stroke-linejoin="round"/>')
    if ankle is not None:
        top = sole_t + FORM_ANKLE_CM
        if top > (shaft or 0):
            pts = [view(3.4 * math.cos(2 * math.pi * k / 24), 0.22 + 3.8 * math.sin(2 * math.pi * k / 24) / LENGTH, h)
                   for h in (sole_t + 2.0, top) for k in range(24)]
            cap = [view(3.4 * math.cos(2 * math.pi * k / 24), 0.22 + 3.8 * math.sin(2 * math.pi * k / 24) / LENGTH, top)
                   for k in range(24)]
            # it shows inside the opening and above the shoe, never over the shoe's front
            far = 4000
            out.append(f'<clipPath id="{uid}a"><path d="{rim_d}"/>'
                       f'<path clip-rule="evenodd" d="M {-far},{-far} L {far},{-far} L {far},{far} L {-far},{far} Z {upper_d}"/>'
                       f'</clipPath>')
            out.append(f'<g clip-path="url(#{uid}a)">' + ankle.replace("{d}", _path(_hull(pts))) + "</g>")
            out.append(ankle.replace("{d}", _path(_hull(cap))))
    return out


def _details(p, style, view, hw, inset, table, sole_t, shaft, base, line_c, ln, fill):
    out = []
    s = lambda u, xs, lift=0.0: _surface(view, hw, inset, table, sole_t, u, xs, lift)   # noqa: E731
    across = lambda u, w, lift=0.15: [s(u, k / 6 * w, lift) for k in range(-6, 7)]       # noqa: E731
    laced = p.get("laces", style not in ("slip_on", "loafer", "chelsea_boot"))
    lace_c = p.get("lace_color") or None
    if style in ("loafer",):
        # the moc apron round the top of the toe, and the strap across the vamp
        if p.get("moc", True):
            apron = [s(u, 0.66) for u in (0.5, 0.6, 0.7, 0.8)] + [s(0.87, 0.5), s(0.9, 0.0), s(0.87, -0.5)] + \
                    [s(u, -0.66) for u in (0.8, 0.7, 0.6, 0.5)]
            out.append(ln(_path(apron, close=False), 1.3))
        strap = p.get("strap", "penny")
        if strap != "none":
            band = across(0.56, 0.86, 0.25) + list(reversed(across(0.6, 0.86, 0.25)))
            out.append(fill(_path(band), shade(base, -0.12 if luminance(base) > 0.2 else 0.1), w=1.2))
            if strap == "penny":
                cx, cy = s(0.58, 0.0, 0.3)
                out.append(f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{2.6 * view.px * 0.45:.1f}" ry="{0.7 * view.px * 0.45:.1f}" '
                           f'fill="{shade(base, -0.5) if luminance(base) > 0.1 else "#000"}"/>')
            elif strap == "horsebit":
                out.append(ln(_path(across(0.58, 0.5, 0.4), close=False), 2.4, METAL, 1))
            elif strap == "tassel":
                for xs in (-0.25, 0.25):
                    x, y = s(0.6, xs, 0.3)
                    out.append(f'<path d="M {x:.1f},{y:.1f} l {-1.5 * xs:.1f},5 l {3 * xs:.1f},0 Z" fill="{shade(base, -0.2)}" '
                               f'stroke="{INK}" stroke-width=".8"/>')
    if style in ("derby", "oxford", "boot", "low_sneaker", "high_top", "runner") and laced:
        # the two edges of the lacing, and the laces across them, from the throat down to the toe box
        lo, hi = (0.5, 0.74) if style != "oxford" else (0.52, 0.72)
        for xs in (-0.42, 0.42):
            out.append(ln(_path([s(u, xs, 0.05) for u in (lo - 0.03, (lo + hi) / 2, hi)], close=False), 1.2))
        n = max(3, min(7, int(p.get("eyelets", 5)))) - 1
        lace = lace_c or (shade(base, -0.28) if luminance(base) > 0.75 else shade(base, 0.35 if luminance(base) < 0.3 else -0.25))
        for i in range(n):
            u = lo + (hi - lo) * i / max(1, n - 1)
            d = _path(across(u, 0.42, 0.25), close=False)
            out.append(ln(d, 2.8, INK, 0.9) + ln(d, 1.5, lace, 1))
        if shaft:   # a boot laces on up its shaft
            for i in range(3):
                h = sole_t + 8.5 + i * (shaft - sole_t - 10) / 2
                d = _path([view(1.8 * k / 3, 0.2 + 5.2 / LENGTH, h) for k in range(-3, 4)], close=False)
                out.append(ln(d, 2.8, INK, 0.9) + ln(d, 1.5, lace, 1))
    if p.get("toe_cap") == "stitched" or p.get("brogue") in ("quarter", "semi"):
        out.append(ln(_path(across(0.83, 1.0, 0.0), close=False), 1.3))
    if p.get("brogue") == "full":   # a wingtip: the wing's point on the toe
        out.append(ln(_path([s(0.74, -1.0), s(0.86, -0.3), s(0.9, 0.0), s(0.86, 0.3), s(0.74, 1.0)], close=False), 1.3))
    if style == "chelsea_boot" or p.get("gusset"):   # the elastic panels on the sides of the shaft, and its pull tab
        top = shaft or sole_t + 9
        elastic = "#2b2724" if luminance(base) > 0.08 else "#4a4540"
        ring = lambda a, h, r=1.0: view(r * 4.7 * math.cos(a), 0.2 + r * 5.2 * math.sin(a) / LENGTH, h)   # noqa: E731
        for side in (-1, 1):
            a0, a1, am = (math.radians(d) for d in ((2, 78, 40) if side > 0 else (178, 102, 140)))
            pts = [ring(a0, top), ring(a1, top), ring(am, sole_t + 3.0, 0.97)]
            out.append(f'<path d="{_path(pts)}" fill="{elastic}" stroke="{INK}" stroke-width="1.2" stroke-linejoin="round"/>')
        tx, ty = ring(math.radians(-90), top, 0.9)
        w, h = 1.25 * view.px, 1.9 * view.px
        out.append(f'<path d="M {tx - w:.1f},{ty + 2:.1f} L {tx - w:.1f},{ty - h:.1f} Q {tx:.1f},{ty - h - w:.1f} {tx + w:.1f},{ty - h:.1f} '
                   f'L {tx + w:.1f},{ty + 2:.1f}" fill="{shade(base, -0.12)}" stroke="{INK}" stroke-width="1.2" stroke-linejoin="round"/>')
    if p.get("shine"):
        x, y = s(0.9, -0.3, 0.2)
        out.append(f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{1.4 * view.px:.1f}" ry="{0.5 * view.px:.1f}" fill="#fff" opacity=".55"/>')
    return out


def _foot_top(u: float) -> float:
    """How high the top of a foot stands above the footbed at u (0 heel, 1 toe), in cm."""
    return _interp([(0.0, 7.5), (0.3, 7.0), (0.5, 5.5), (0.7, 3.8), (0.85, 2.6), (0.95, 1.6), (1.0, 0.8)], u)


def _strap(view, hw, sole_t, u0, u1):
    """A strap crossing the foot from one side of the footbed to the other, between u0 and u1."""
    def arc(u):
        w = hw(u) * 0.98
        return [view(w * math.cos(math.pi * k / 12), u, sole_t + (_foot_top(u) + 0.3) * math.sin(math.pi * k / 12) ** 0.7)
                for k in range(13)]
    return arc(u1) + list(reversed(arc(u0)))


def _sandal_kind(p) -> str:
    kind = p.get("sandal", "two_strap")
    return kind if kind in ("slide", "two_strap", "strap", "thong") else "two_strap"


def _sandal_bands(p):
    kind = _sandal_kind(p)
    return {"slide": [(0.46, 0.83)], "two_strap": [(0.63, 0.8), (0.4, 0.57)], "strap": [(0.69, 0.83), (0.42, 0.5)],
            "thong": []}[kind]


def _sandal_points(p, view, hw, sole_t):
    pts = []
    for u0, u1 in _sandal_bands(p):
        pts += _strap(view, hw, sole_t, u0, u1)
    if _sandal_kind(p) == "strap":
        pts += [view(4.0 * math.cos(2 * math.pi * k / 16), 0.12 + 4.0 * math.sin(2 * math.pi * k / 16) / LENGTH, sole_t + 7.5)
                for k in range(16)]
    if _sandal_kind(p) == "thong":
        pts += [view(0.0, 0.7, sole_t + _foot_top(0.7))]
    return pts


def _sandal(p, view, hw, sole_t, base, sole_c, uid):
    """A footbed seen from above at the front, and straps arching over where a foot would be: no foot is drawn."""
    out = []
    bed = [view(hw(u) * 0.94 * s, u, sole_t) for s in (1, -1) for u in ([i / 40 for i in range(41)] if s > 0 else
                                                                         [1 - i / 40 for i in range(41)])]
    out.append(f'<path d="{_path(bed)}" fill="{shade(sole_c, 0.12)}" stroke="{shade(sole_c, -0.25)}" stroke-width="1"/>')
    for u0, u1 in _sandal_bands(p):
        out.append(f'<path d="{_path(_strap(view, hw, sole_t, u0, u1))}" fill="{base}" stroke="{INK}" stroke-width="2" '
                   f'stroke-linejoin="round"/>')
    kind = _sandal_kind(p)
    if kind == "strap":   # a strap round the ankle
        ring = [view(4.0 * math.cos(2 * math.pi * k / 24), 0.12 + 4.0 * math.sin(2 * math.pi * k / 24) / LENGTH, sole_t + 7.5)
                for k in range(25)]
        d = _path(ring, close=False)
        out.append(f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="4.6" stroke-linecap="round"/>'
                   f'<path d="{d}" fill="none" stroke="{base}" stroke-width="2.6" stroke-linecap="round"/>')
    if kind == "two_strap":   # a buckle on the outer side of each strap
        for u in (0.715, 0.485):
            w = hw(u) * 0.98
            a = math.pi * 3.6 / 12
            x, y = view(-w * math.cos(a), u, sole_t + (_foot_top(u) + 0.3) * math.sin(a) ** 0.7)
            out.append(f'<rect x="{x - 2.4:.1f}" y="{y - 2.4:.1f}" width="4.8" height="4.8" rx="1" fill="none" stroke="{METAL}" stroke-width="1.4"/>')
    if kind == "thong":   # a flip-flop: from a post between the toes, back over the foot to each side
        post = view(-0.8, 0.88, sole_t + 0.6)
        crest = [view(sx * hw(0.7) * 0.55, 0.7, sole_t + _foot_top(0.7) * 0.85) for sx in (-1, 1)]
        ends = [view(sx * hw(0.52) * 0.97, 0.52, sole_t + 0.2) for sx in (-1, 1)]
        for c, e in zip(crest, ends, strict=True):
            d = f"M {post[0]:.1f},{post[1]:.1f} Q {c[0]:.1f},{c[1]:.1f} {e[0]:.1f},{e[1]:.1f}"
            out.append(f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="5" stroke-linecap="round"/>'
                       f'<path d="{d}" fill="none" stroke="{base}" stroke-width="3" stroke-linecap="round"/>')
        out.append(f'<circle cx="{post[0]:.1f}" cy="{post[1]:.1f}" r="2.4" fill="{base}" stroke="{INK}" stroke-width="1.2"/>')
    return out
