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

from .illustrate import INK, Spec, _hex, _rgb, _texture_defs, luminance, shade

LENGTH = 29.5          # one shoe, toe to heel, in cm: a men's UK 9
BALL = 0.72            # the ball of the foot, as a share of the length from the heel: the shoe is centred on it
LOOK = 24.0            # degrees the viewer looks down at the shoes from
TURN = 11.0            # degrees each toe is turned out
METAL = "#c9a85c"
TEXTURE_SCALE = 0.4    # an upper's surface (pebble grain, suede ...) at the figure's scale: a shoe here is a few cm wide
SHEARLING = "#ece2cc"   # a slipper's fleece lining
LINING = "#3a342e"     # the inside of a shoe: a dark warm grey, a little of the shoe's colour in it
ANKLE_CM = 13.0        # the wearer's ankle: where it is drawn up to above the sole, in a low shoe or a sandal ...
ANKLE_OVER_CM = 3.0    # ... and above the top of a boot's shaft
ANKLE_U = 0.22         # its middle, as a share of the length from the heel
ANKLE_HALF_CM, ANKLE_DEPTH_CM = 3.4, 3.8   # half its width, and half its depth from front to back
INSTEP_U = 0.47        # the instep, at the front of a low shoe's opening (or where a boot's shaft meets its vamp)
COLLAR_RIM = 0.82      # a low shoe's opening is this share of the upper's width at the collar ...
SHAFT_RIM = 0.9        # ... and a boot's this share of its shaft's
BEHIND_CM = 20.0       # how far above a low shoe's collar the ankle is still in front of the collar's back
NO_SHOW_CM = 2.0       # a no-show cut (`cut` low) stands its collar this much lower, behind the throat ...
NO_SHOW_DIP_CM = 0.6   # ... and dips its opening this much more at the sides, under the ankle bones
CUT_STYLES = ("low_sneaker", "runner", "slip_on")

# per style: half width at the ball, sole thickness, how the upper's top rises from the toe (share of the length
# from the heel, height above the sole in cm), and how high the collar of a boot or high top stands (cm above the
# ground); 0 for a low shoe.
_LOW = [(0.0, 6.8), (0.12, 7.4), (0.3, 6.4), (0.46, 8.0), (0.56, 7.2), (0.7, 5.6), (0.85, 4.3), (0.95, 3.0), (1.0, 1.0)]
_DRESS = [(0.0, 6.2), (0.12, 6.6), (0.3, 5.6), (0.46, 6.6), (0.56, 6.1), (0.7, 4.7), (0.85, 3.3), (0.95, 2.2), (1.0, 0.8)]
_SLIP = [(0.0, 6.2), (0.12, 6.6), (0.3, 5.8), (0.46, 6.6), (0.56, 6.2), (0.7, 5.2), (0.85, 4.1), (0.95, 2.9), (1.0, 1.0)]
_BOOT = [(0.0, 7.6), (0.12, 7.8), (0.3, 7.6), (0.46, 8.6), (0.56, 7.6), (0.7, 6.0), (0.85, 4.6), (0.95, 3.2), (1.0, 1.1)]
TRAINERS = ("low_sneaker", "runner")
LOW_COLLARED = ("slip_on", "loafer", "derby", "oxford")   # low shoes whose collar is rounded off like a trainer's
# A low collar's narrow inner shoulder (less than LIP_ROOM px-widths from the hull's side to past the rim's side) tops
# out LIP_SHOULDER of the way from its side to the front of the opening; either shoulder of a low collar rises no
# more than LIP_RISE times as high as it is wide, so it rounds over rather than standing up in a point (#223)
LIP_SHOULDER = 0.4
LIP_RISE = 1.3
LIP_ROOM = 1.5
STYLES = {
    #               ball  sole  top     shaft
    "low_sneaker": (5.4, 2.9, _LOW, 0.0),
    "runner": (5.5, 3.6, _LOW, 0.0),
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
    ankle: bool = False   # the wearer's ankle (or bare foot) is drawn in it
    foot: str = ""        # a bare foot (in a sandal, or with no shoe): its outline, up into the leg
    toes: list[str] = field(default_factory=list)   # ...and the faint lines between its toes
    upper: str = ""       # the upper's outline, and where the leg shows through it (the opening, and above the
    seen: list[str] = field(default_factory=list)   # collar's back): for checking that nothing hides the leg
    rim: str = ""         # the opening's edge
    width: float = 0.0    # how wide (cm) the solid is round its opening: a low shoe's collar, a boot's shaft (0: a sandal)


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


def _collar_front(upper, rim, px, vamp_top=None):
    """Round the wall over the front of the opening, rather than leaving the
    convex solid's rear crown sticking up beside the wearer's ankle."""
    left, right = min(rim), max(rim)
    # the front of the opening: its lowest point across the middle (a traced sole's lift can bring a side as low)
    span = right[0] - left[0]
    bottom = max((q for q in rim if abs(q[0] - (left[0] + right[0]) / 2) <= 0.3 * span), key=lambda p: p[1])
    cut = bottom[1]
    bottom = (bottom[0], bottom[1] - 0.4 * px)
    if vamp_top is not None:
        # A short shaft can sit below the instep on a thick sole. Its front
        # cannot be cut down to the opening: the raised vamp is in front of it.
        bottom = (bottom[0], min(bottom[1], vamp_top - 0.4 * px))
    lower = []
    for a, b in zip(upper, upper[1:] + upper[:1], strict=True):
        if a[1] >= cut:
            lower.append(a)
        if (a[1] < cut) != (b[1] < cut):
            t = (cut - a[1]) / (b[1] - a[1])
            lower.append((a[0] + t * (b[0] - a[0]), cut))
    ends = sorted(p for p in lower if abs(p[1] - cut) < 0.001)
    start, end = ends[0], ends[-1]
    # The collar is a rounded lip in section: rise up its outside, turn over,
    # then follow the bowed front. Both shoulders meet the bow tangentially.
    lc, rc = left[1] - 0.35 * px, right[1] - 0.35 * px
    ly, ry = (bottom[1] - lc) / 3, (bottom[1] - rc) / 3
    lx, rx = (bottom[0] - left[0] - px) / 3, (right[0] - px - bottom[0]) / 3
    left_d = (f"C {start[0]:.1f},{lc:.1f} {left[0]:.1f},{lc:.1f} {left[0] + px:.1f},{lc + ly:.1f} "
              f"C {left[0] + 2 * px:.1f},{lc + 2 * ly:.1f} {bottom[0] - lx:.1f},{bottom[1]:.1f} ")
    right_d = (f"C {bottom[0] + rx:.1f},{bottom[1]:.1f} {right[0] - 2 * px:.1f},{rc + 2 * ry:.1f} "
               f"{right[0] - px:.1f},{rc + ry:.1f} "
               f"C {right[0]:.1f},{rc:.1f} {end[0]:.1f},{rc:.1f} {end[0]:.1f},{cut:.1f} ")
    k = 0.5523   # a cubic's handles for a quarter circle
    if vamp_top is None and left[0] + px - start[0] < LIP_ROOM * px:
        # A low shoe's narrow inner shoulder: a round arc up from the side to a top a little in from it, then an
        # S level onto the bow, so what shows of it beside a bare ankle is a smooth hump, not a point
        lt = start[0] + LIP_SHOULDER * (bottom[0] - start[0])
        top = max(lc, cut - LIP_RISE * (lt - start[0]))
        lm = (lt + bottom[0]) / 2
        left_d = (f"C {start[0]:.1f},{cut - k * (cut - top):.1f} {lt - k * (lt - start[0]):.1f},{top:.1f} {lt:.1f},{top:.1f} "
                  f"C {lm:.1f},{top:.1f} {lm:.1f},{bottom[1]:.1f} ")
    if vamp_top is None:
        # Its outer shoulder: an S from the bow up to the rim's side, past the ankle, then round down to the side
        rt = right[0]
        top = max(rc, cut - LIP_RISE * (end[0] - rt))
        rm = (bottom[0] + rt) / 2
        right_d = (f"C {rm:.1f},{bottom[1]:.1f} {rm:.1f},{top:.1f} {rt:.1f},{top:.1f} "
                   f"C {rt + k * (end[0] - rt):.1f},{top:.1f} {end[0]:.1f},{cut - k * (cut - top):.1f} {end[0]:.1f},{cut:.1f} ")
    d = f"M {start[0]:.1f},{cut:.1f} " + left_d + f"{bottom[0]:.1f},{bottom[1]:.1f} " + right_d
    # Walk the untouched lower hull from the right shoulder back to the left.
    i = lower.index(end)
    lower = lower[i:] + lower[:i]
    if lower[1][0] < end[0] and lower[1][1] == cut:
        lower = [lower[0]] + list(reversed(lower[1:]))
    seen = d + f"L {end[0]:.1f},-4000 L {start[0]:.1f},-4000 Z"
    return d + " ".join(f"L {x:.1f},{y:.1f}" for x, y in lower[1:]) + " Z", seen


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


TOE_IN_CM = 1.2        # a foot's (and a sandal's) toe end leans this far to the big toe's side
# the toes, from the big one outwards: where each starts and ends round the front of the foot (degrees from the
# inner side of the ball), and how far forward it reaches (a share of the way to the front of the footbed)
TOES = [(20.0, 70.0, 1.0), (70.0, 97.0, 0.99), (97.0, 119.0, 0.955), (119.0, 138.0, 0.915), (138.0, 155.0, 0.87)]
TOE_NOTCH = 0.05       # how far back the edge dips between two toes (a share, as above)
FOOT_IN = 0.9          # the foot's width, as a share of the footbed's


def _lean(u: float) -> float:
    """How far the middle of a foot leans to the big toe's side (+x) at u, in cm."""
    return 0.0 if u <= BALL else TOE_IN_CM * ((u - BALL) / (1 - BALL)) ** 1.5


def _smooth(pts, n: int = 6):
    """Points along a smooth curve through `pts` (Catmull-Rom)."""
    out = []
    for i in range(len(pts) - 1):
        p0, p1, p2, p3 = pts[max(i - 1, 0)], pts[i], pts[i + 1], pts[min(i + 2, len(pts) - 1)]
        for j in range(n):
            t = j / n
            out.append(tuple(0.5 * (2 * p1[k] + (p2[k] - p0[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t * t
                                    + (3 * p1[k] - 3 * p2[k] + p3[k] - p0[k]) * t ** 3) for k in (0, 1)))
    return out + [pts[-1]]


def _half_width(u: float, ball: float, toe: str) -> float:
    """Half the footprint's width at u (0 heel, 1 toe), in cm."""
    long_toe = {"almond": 0.06, "chisel": 0.08, "pointed": 0.12}.get(toe, 0.0)
    if u < 0.08:
        return 0.68 * ball * math.sqrt(max(0.0, 1 - ((0.08 - u) / 0.08) ** 2))
    if u < BALL:
        t = (u - 0.08) / (BALL - 0.08)
        return ball * (0.68 + 0.32 * t ** 1.6)
    t = (u - BALL) / (1 - BALL)
    if toe == "chisel":   # a squared-off end: the sides run on nearly straight, then turn in across a flat front
        return ball * max(0.0, 1 - t ** 12) ** 0.5 * (1 - 0.4 * t ** 2)
    return ball * math.sqrt(max(0.0, 1 - t ** 2)) ** (1 + long_toe * 8)


def front_shoe(spec: Spec, px: float, *, sole_default: str | None = None, uid: str = "fs",
               ankle: str | None = None, toes: str | None = None, ankle_path: str | None = None) -> FrontShoe:
    """The shoe of `spec` from the front, scaled by `px`. With `ankle` (markup for skin, with "{d}" for its path),
    the wearer's ankle stands in the shoe's opening, and a sandal holds a bare foot (`toes`: the colour of the
    lines between its toes). `ankle_path` keeps the figure's own leg contour through the opening, in shoe
    coordinates. The anchor "ankle" is where the leg above it ends, "ankle_r" its right edge there.
    It is always drawn from its style words, also for a shoe traced from its photo: the figure draws Claude's
    drawing of a shoe in its place when there is one (`figure._drawing_of`)."""
    p = {**spec.params, "lace_color": spec.lace_color}
    style = p.get("style") or ("high_top" if p.get("height") == "high" else "low_sneaker")
    if style not in STYLES:
        style = "low_sneaker"
    toe = p.get("toe", "round")
    ball, sole_t, table, shaft = STYLES[style]
    dip = 0.0
    if p.get("cut") == "low" and style in CUT_STYLES:   # a no-show cut: the collar and the opening lower
        table, dip = _cut_low(table), NO_SHOW_DIP_CM
    sole_t *= {"thin": 0.75, "chunky": 1.6}.get(p.get("sole"), 1.0)
    sole_t *= {"lug": 1.25, "eva": 1.35, "city": 0.85}.get(p.get("tread"), 1.0)
    if style == "sandal" and p.get("molded"):   # a moulded slide: one deeper piece
        sole_t *= 1.25
    if shaft and p.get("shaft"):
        shaft = max(0.35, min(0.95, float(p["shaft"]))) * LENGTH
    inset = 0.93 if style in ("loafer", "derby", "oxford") else 0.97
    view = _View(px)
    hw = lambda u: _half_width(u, ball, toe)   # noqa: E731
    mid = _lean if style == "sandal" else (lambda u: 0.0)   # a sandal's footbed is the shape of a foot
    us = [i / 60 for i in range(61)]
    base = spec.fill.color
    dark = luminance(base) < 0.3
    sole_c = spec.sole_color or sole_default or "#f4f1ea"
    if style == "sandal" and p.get("molded"):   # a moulded slide is one piece, in its own colour
        sole_c = spec.sole_color or shade(base, 0.14 if dark else -0.14)   # its side a shade off its top, so it reads as deep
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
        right = [(mid(u) + hw(u) * inset, u, h) for u in us]
        left = [(mid(u) - hw(u) * inset, u, h) for u in reversed(us)]
        return right + left

    # the sole: everything between the ground and the top of the sole
    sole_pts = [view(*q) for h in (0.0, sole_t) for q in contour(h)]
    sole_d = _path(_hull(sole_pts))
    out.append(fill(sole_d, sole_c))
    defs += f'<clipPath id="{uid}s"><path d="{sole_d}"/></clipPath>'
    if style in TRAINERS or p.get("tread") == "eva":   # a trainer's sole: the outsole under it a shade darker, so its edge reads under a hem
        low = [view(*q) for h in (0.0, sole_t * 0.32) for q in contour(h)]
        c = shade(sole_c, -0.22 if luminance(sole_c) > 0.25 else 0.18)
        out.append(f'<g clip-path="url(#{uid}s)">' + fill(_path(_hull(low)), c, edge=False) + "</g>")
    if style in ("high_top", "slip_on") + TRAINERS or p.get("foxing"):   # the stripe round a vulcanised sole
        line = [view(x, u, sole_t * 0.55) for x, u, _ in contour(0)]
        out.append(f'<g clip-path="url(#{uid}s)">' + ln(_path(line, close=False), 1.1,
                                                         shade(sole_c, -0.3 if luminance(sole_c) > 0.25 else 0.22), 1) + "</g>")
    if p.get("tread") in ("lug", "crepe") or style in ("boot",):   # a thick outsole: its lower part darker
        low = [view(*q) for h in (0.0, sole_t * 0.4) for q in contour(h)]
        c = shade(sole_c, -0.35 if luminance(sole_c) > 0.25 else 0.18)
        out.append(f'<g clip-path="url(#{uid}s)">' + fill(_path(_hull(low)), c, edge=False) + "</g>")

    if style == "sandal":
        leg = sole_t + ANKLE_CM
        foot_d, toe_lines, post = _foot_shape(view, ball, sole_t, leg) if ankle is not None else ("", [], None)
        more, more_defs = _sandal(p, view, hw, sole_t, base, sole_c, uid, ankle, toes, foot_d, toe_lines, post)
        out += more
        defs += more_defs
        outline_pts = sole_pts + _sandal_points(p, view, hw, sole_t)
        top = sole_t + 4
    else:
        # the upper: a half ellipse across the foot at every step from heel to toe, up to the top line
        upper_pts = []
        vamp_pts = []
        seen_by: dict = {}
        for u in us:
            w, h = hw(u) * inset, _interp(table, u)
            for k in range(13):
                a = math.pi * k / 12
                point = view(w * math.cos(a), u, sole_t + h * math.sin(a))
                upper_pts.append(point)
                if u >= ANKLE_U:
                    vamp_pts.append(point)
        ax, au, arx, aru = 0.0, 0.2, 4.7, 5.2        # the ankle: a boot's shaft, the wearer's ankle
        if shaft:
            for h in (sole_t + 4.0, shaft):
                for k in range(24):
                    a = 2 * math.pi * k / 24
                    upper_pts.append(view(ax + arx * math.cos(a), au + aru * math.sin(a) / LENGTH, h))
        upper_d = _path(_hull(upper_pts))
        collar_seen = None
        if ankle is not None and style in (*TRAINERS, *LOW_COLLARED, "boot"):
            ring = [view(*q) for q in _collar_ring(hw, inset, table, sole_t, shaft, dip)]
            vamp_top = min(y for _, y in vamp_pts) if shaft else None
            upper_d, collar_seen = _collar_front(_hull(upper_pts), ring, px, vamp_top)
        out.append(fill(upper_d, base, w=2.4))
        defs += f'<clipPath id="{uid}u"><path d="{upper_d}"/></clipPath>'
        tex = _texture_defs(spec.texture, f"{uid}x", dark, TEXTURE_SCALE)   # the upper's grain, nap or weave ...
        if tex and float(tex.split('width="')[1].split('"')[0]) < 2.5:   # ... unless it is too fine to show this small
            tex = ""
        if tex:
            defs += tex
            out.append(f'<path d="{upper_d}" fill="url(#t{uid}x)"/>')
        if spec.sheen:   # a waxed or rubber upper's soft sheen, where the light falls on its form: the toe's crown ...
            gloss = [view(hw(u) * inset * -0.32, u, sole_t + _interp(table, u) * 0.95) for u in (0.66, 0.74, 0.82, 0.88)]
            sheen = ln(_path(gloss, close=False), 0.9 * view.px, "#fff", 0.2)
            if shaft:   # ... and down the lit side of a boot's shaft
                streak = [view(ax - arx * 0.5, au + aru * 0.86 / LENGTH, h) for h in (shaft - 1.5, sole_t + 6.0)]
                sheen += ln(_path(streak, close=False), 0.8 * view.px, "#fff", 0.2)
            out.append(f'<g clip-path="url(#{uid}u)">{sheen}</g>')
        top = max(shaft, sole_t + max(h for _, h in table))
        leg = max(sole_t + ANKLE_CM, shaft + ANKLE_OVER_CM if shaft else 0.0)
        if style == "high_top" or p.get("toe_cap") == "rubber":   # a rubber toe in the sole's colour
            cap = [view(hw(u) * inset * math.cos(math.pi * k / 12), u, sole_t + _interp(table, u) * math.sin(math.pi * k / 12))
                   for u in us if u >= 0.87 for k in range(13)]
            cap += [view(x, u, sole_t) for x, u, _ in contour(0, inset) if u >= 0.8]
            out.append(f'<g clip-path="url(#{uid}u)">' + fill(_path(_hull(cap)), sole_c, w=1.3) + "</g>")
        if style == "chelsea_boot" or p.get("gusset"):   # its pull tab is at the back: behind the leg
            out.append(_pull_tab(view, shaft or sole_t + 9, base))
        out += _opening(p, view, hw, inset, table, sole_t, shaft, base, ankle, upper_d, uid, leg, ankle_path, collar_seen,
                        keep=seen_by, dip=dip)
        out += _details(p, style, view, hw, inset, table, sole_t, shaft, base, line_c, ln, fill)
        outline_pts = sole_pts + upper_pts
        # where a trouser hem meets it: the front and the back of the opening (a low shoe's collar, the top of a
        # boot's shaft), the instep in front of it, and how wide the solid is round the opening
        ring = _collar_ring(hw, inset, table, sole_t, shaft, dip)
        rim_pts = [view(*q) for q in ring]
        opening = {"opening": max(rim_pts, key=lambda q: q[1]), "opening_back": min(rim_pts, key=lambda q: q[1]),
                   "instep": view(0.0, INSTEP_U, sole_t + _interp(table, INSTEP_U))}
        width = 2 * max(abs(x) for x, _, _ in ring) / (SHAFT_RIM if shaft else COLLAR_RIM)
    hull = _hull(outline_pts)
    xs, ys = [x for x, _ in hull], [y for _, y in hull]
    anchors = {"ball": (0.0, view(0.0, BALL, 0.0)[1]), "toe": view(0.0, 1.0, 0.0), "heel": view(0.0, 0.0, 0.0),
               "ground": (0.0, 0.0), "top": (0.0, view(0.0, 0.2, top)[1]), **_ankle_anchors(view, sole_t + ANKLE_CM)}
    if style != "sandal":
        anchors.update(opening)
    shoe = FrontShoe(_path(hull), (min(xs) - 2, min(ys) - 2, max(xs) + 2, max(ys) + 2), anchors, "".join(out), defs,
                     ankle is not None, width=width if style != "sandal" else 0.0)
    if style == "sandal" and ankle is not None:
        shoe.foot, shoe.toes = foot_d, toe_lines
    elif style != "sandal":
        shoe.upper, shoe.seen, shoe.rim = upper_d, seen_by.get("seen", []), seen_by.get("rim", "")
    return shoe


def _surface(view, hw, inset, table, sole_t, u, x_share, lift=0.0):
    """A point on the top of the upper at u, x_share of the way out to the side."""
    w, h = hw(u) * inset, _interp(table, u)
    a = math.acos(max(-1.0, min(1.0, x_share)))
    return view(w * x_share, u, sole_t + h * math.sin(a) + lift)


def _ankle_anchors(view, leg: float) -> dict[str, tuple[float, float]]:
    """Where the leg above a shoe ends (a little below where the ankle drawn in the shoe is cut off), and its right
    edge there: the ankle seen turned and from above is a little wider than it is."""
    x, y = view(0.0, ANKLE_U, leg - 4.0)
    half = math.hypot(ANKLE_HALF_CM * view.ct, ANKLE_DEPTH_CM * view.st) * view.px
    return {"ankle": (x, y), "ankle_r": (x + half, y)}


def _column(view, h0: float, h1: float):
    """The ankle, as an upright cylinder from h0 to h1 above the ground."""
    return [view(ANKLE_HALF_CM * math.cos(2 * math.pi * k / 24),
                 ANKLE_U + ANKLE_DEPTH_CM * math.sin(2 * math.pi * k / 24) / LENGTH, h)
            for h in (h0, h1) for k in range(24)]


def _below(ankle: str, d: str, y: float, uid: str) -> tuple[str, str]:
    """Skin (the `ankle` markup: an outline, then a fill) drawn only below the height y, where the leg drawn above
    runs on into it, and the clip paths that takes. The fill starts a little higher than the outline: cut off at
    the same height, a faint line of the outline would show under the fill's edge."""
    line, fill = ankle.replace("{d}", d).split("/>", 1)
    defs = (f'<clipPath id="{uid}b"><rect x="-4000" y="{y:.1f}" width="8000" height="8000"/></clipPath>'
            f'<clipPath id="{uid}c"><rect x="-4000" y="{y - 3:.1f}" width="8000" height="8000"/></clipPath>')
    return f'<g clip-path="url(#{uid}b)">{line}/></g><g clip-path="url(#{uid}c)">{fill}</g>', defs


def _cut_low(table):
    """A style's top line cut no-show: lower by NO_SHOW_CM behind the throat (the collar, round the ankle), easing
    back to the style's own line at the tongue."""
    def drop(u):
        return NO_SHOW_CM * max(0.0, min(1.0, (0.46 - u) / 0.16))
    return [(u, h - drop(u)) for u, h in table]


def _collar_ring(hw, inset, table, sole_t, shaft, dip=0.0):
    """The opening's edge (a no-show cut's `dip`s that much more at the sides)."""
    if shaft:
        rx, ru = 4.7 * SHAFT_RIM, 5.2 * SHAFT_RIM
        ring = [(rx * math.cos(2 * math.pi * k / 32), 0.2 + ru * math.sin(2 * math.pi * k / 32) / LENGTH,
                 shaft) for k in range(32)]
    else:
        ring = []
        for k in range(32):
            a = 2 * math.pi * k / 32
            u = 0.27 + 0.2 * math.sin(a)                     # from just inside the heel to the throat
            x = hw(u) * inset * COLLAR_RIM * math.cos(a)
            h = sole_t + _interp(table, 0.04) - 0.5 + (0.6 if math.sin(a) > 0 else 0) * math.sin(a) - dip * math.cos(a) ** 2
            ring.append((x, u, h))
    return ring


def _opening(p, view, hw, inset, table, sole_t, shaft, base, ankle, upper_d, uid, leg, ankle_path=None, collar_seen=None,
             keep=None, dip=0.0):
    """The way in: the collar of a low shoe, or the top of a boot's shaft, with the dark lining inside; and the
    wearer's ankle standing in it when asked for, up to where the leg drawn above it takes over."""
    out = []
    lining = SHEARLING if p.get("lining") == "shearling" else _mix(base, LINING, 0.82)
    ring = _collar_ring(hw, inset, table, sole_t, shaft, dip)
    rim = [view(*q) for q in ring]
    rim_d = _path(rim)
    # where the ankle is seen: in the opening, and above the back half of the collar, which is behind it (the
    # heel counter's top, seen from above, stands up behind the ankle; only the collar's sides, curving round
    # it, are in front of it)
    if collar_seen:
        seen_d = collar_seen
    else:
        seen = rim + [view(x, u, h + BEHIND_CM) for x, u, h in ring if u <= (0.2 if shaft else 0.27)]
        seen_d = _path(_hull(seen))
    if p.get("lining") == "shearling":   # the fleece turned over the collar, a soft cream rim round the opening
        out.append(f'<path d="{rim_d}" fill="none" stroke="{INK}" stroke-width="5.4" stroke-linejoin="round"/>'
                   f'<path d="{rim_d}" fill="none" stroke="{SHEARLING}" stroke-width="3.6" stroke-linejoin="round"/>')
    out.append(f'<path d="{rim_d}" fill="{lining}" stroke="{INK}" stroke-width="1.4" stroke-linejoin="round"/>')
    if collar_seen is not None:
        out = [f'<g clip-path="url(#{uid}u)">{"".join(out)}</g>']
    if ankle is not None:
        pts = _column(view, sole_t + 2.0, leg)
        # it shows inside the opening and above the shoe, never over the shoe's front
        far = 4000
        skin, below = _below(ankle, _path(_hull(pts)), view(0.0, ANKLE_U + ANKLE_DEPTH_CM / LENGTH, leg)[1] + 1.5, uid)
        if ankle_path is not None:
            # Continue the wearer's own leg through the opening, in front of the back rim but behind the front.
            skin, below = _below(ankle, ankle_path, min(y for _, y in rim) - 3.0, uid)
        if keep is not None:
            keep.update(seen=[seen_d], rim=rim_d)
        out.append(f'<clipPath id="{uid}a"><path d="{seen_d}"/>'
                   f'<path clip-rule="evenodd" d="M {-far},{-far} L {far},{-far} L {far},{far} L {-far},{far} Z {upper_d}"/>'
                   f'</clipPath>{below}')
        out.append(f'<g clip-path="url(#{uid}a)">{skin}</g>')
    return out


def _pull_tab(view, top: float, base: str) -> str:
    """A Chelsea boot's pull tab, up from the back of its shaft: behind the leg, so drawn before it."""
    tx, ty = view(0.0, 0.2 - 0.9 * 5.2 / LENGTH, top)
    w, h = 1.25 * view.px, 1.9 * view.px
    return (f'<path d="M {tx - w:.1f},{ty + 2:.1f} L {tx - w:.1f},{ty - h:.1f} Q {tx:.1f},{ty - h - w:.1f} {tx + w:.1f},{ty - h:.1f} '
            f'L {tx + w:.1f},{ty + 2:.1f}" fill="{shade(base, -0.12)}" stroke="{INK}" stroke-width="1.2" stroke-linejoin="round"/>')


def _lace_shade(base: str) -> str:
    """Laces of no colour said: a shade off the upper's, so they read on it."""
    return shade(base, -0.28) if luminance(base) > 0.75 else shade(base, 0.35 if luminance(base) < 0.3 else -0.25)


def _details(p, style, view, hw, inset, table, sole_t, shaft, base, line_c, ln, fill):
    out = []
    s = lambda u, xs, lift=0.0: _surface(view, hw, inset, table, sole_t, u, xs, lift)   # noqa: E731
    across = lambda u, w, lift=0.15: [s(u, k / 6 * w, lift) for k in range(-6, 7)]       # noqa: E731
    laced = p.get("laces", style not in ("slip_on", "loafer", "chelsea_boot"))
    lace_c = p.get("lace_color") or None
    if p.get("moc", style == "loafer"):   # the moc apron round the top of the toe (a loafer has one unless told)
        apron = [s(u, 0.66) for u in (0.5, 0.6, 0.7, 0.8)] + [s(0.87, 0.5), s(0.9, 0.0), s(0.87, -0.5)] + \
                [s(u, -0.66) for u in (0.8, 0.7, 0.6, 0.5)]
        out.append(ln(_path(apron, close=False), 1.3))
    if p.get("split"):   # a split toe: a seam down the middle of the toe, from the apron to the sole
        out.append(ln(_path([s(0.86, 0.0), s(0.92, 0.0), s(0.97, 0.0), s(1.0, 0.0), view(0.0, 1.0, sole_t + 0.2)], close=False), 1.6))
    if style in ("loafer",):
        # the strap across the vamp
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
    strap = p.get("strap") if style != "loafer" else None
    if strap in ("monk", "double_monk", "velcro"):   # straps across the instep, buckled on the outer side (-x)
        bands = {"monk": (0.52,), "double_monk": (0.5, 0.6), "velcro": (0.53, 0.64)}[strap]
        for u in bands:
            band = across(u, 0.9, 0.3) + list(reversed(across(u + 0.05, 0.9, 0.3)))
            out.append(fill(_path(band), shade(base, -0.12 if luminance(base) > 0.2 else 0.1), w=1.2))
            if strap != "velcro":
                x, y = s(u + 0.025, -0.62, 0.4)
                out.append(f'<rect x="{x - 2.2:.1f}" y="{y - 2.6:.1f}" width="4.4" height="5.2" rx="1" fill="none" '
                           f'stroke="{METAL}" stroke-width="1.4"/>')
    if style in TRAINERS:   # the overlay round the toe box
        guard = [s(u, xs, 0.0) for u, xs in ((0.7, -0.98), (0.8, -0.9), (0.88, -0.7), (0.93, -0.35), (0.95, 0.0),
                                              (0.93, 0.35), (0.88, 0.7), (0.8, 0.9), (0.7, 0.98))]
        guard = [(x, y + 0.9 * view.px) for x, y in guard]
        out.append(ln(_path(guard, close=False), 1.3))
    if style in ("derby", "oxford", "boot", "low_sneaker", "high_top", "runner") and laced:
        # the two edges of the lacing, and the laces across them, from the throat down to the toe box (on a
        # trainer, down far enough that a row or two shows under a trouser hem)
        lo, hi = {"oxford": (0.52, 0.72), "low_sneaker": (0.52, 0.8), "runner": (0.52, 0.8)}.get(style, (0.5, 0.74))
        for xs in (-0.42, 0.42):
            out.append(ln(_path([s(u, xs, 0.05) for u in (lo - 0.03, (lo + hi) / 2, hi)], close=False), 1.2))
        n = max(3, min(7, int(p.get("eyelets", 5)))) - 1
        lace = lace_c or _lace_shade(base)
        kind = p.get("lace_kind")
        k = {"flat_waxed": 1.3, "flat_cotton": 1.3, "round_waxed": 0.8, "round_rope": 1.4, "rawhide": 1.3}.get(kind, 1.0)
        rows = []
        for i in range(n):
            u = lo + (hi - lo) * i / max(1, n - 1)
            width = 0.42 if style not in TRAINERS else 0.5
            rows.append([s(u, -width, 0.25), s(u, width, 0.25)])
            d = _path(across(u, width, 0.25), close=False)
            out.append(ln(d, 1.3 + 1.5 * k, INK, 0.9) + ln(d, 1.5 * k, lace, 1))
            if kind in ("flat_waxed", "round_waxed"):   # a waxed lace's glint
                out.append(ln(_path(across(u, 0.24, 0.3)[3:8], close=False), 0.8, "#fff", 0.75))
            elif kind == "round_rope":   # its twist
                twist = shade(lace, 0.35 if luminance(lace) < 0.7 else -0.25)
                out.append(f'<path d="{d}" fill="none" stroke="{twist}" stroke-width="{1.5 * k:.1f}" stroke-dasharray="1.2 1.4"/>')
            if p.get("ghillie"):   # the lace runs through a leather loop on each side
                for xs in (-0.46, 0.46):
                    x, y = s(u, xs, 0.25)
                    out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.9" fill="none" stroke="{INK}" stroke-width="2.4"/>'
                               f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.9" fill="none" stroke="{shade(base, -0.15)}" stroke-width="1.2"/>')
        if shaft:   # a boot laces on up its shaft
            for i in range(3):
                h = sole_t + 8.5 + i * (shaft - sole_t - 10) / 2
                d = _path([view(1.8 * k / 3, 0.2 + 5.2 / LENGTH, h) for k in range(-3, 4)], close=False)
                rows.append([view(x, 0.2 + 5.2 / LENGTH, h) for x in (-1.8, 1.8)])
                out.append(ln(d, 2.8, INK, 0.9) + ln(d, 1.5, lace, 1))
        # Hooks replace the highest pairs, continuing onto the vamp when there are more than three.
        for i, row in enumerate(sorted(rows, key=lambda row: sum(y for _, y in row))):
            hook = i < int(p.get("hooks") or 0)
            if not hook and not p.get("rings"):
                continue
            for side, (x, y) in enumerate(row):
                # Include ordinary eyelet rows when sizing the lowest hook; its outline needs clearance too.
                gap = min(abs(y - other[side][1]) for other in rows if other is not row)
                r = min(0.55 * view.px, gap * 0.2, abs(row[1][0] - row[0][0]) * 0.15)
                angles = [math.radians(-130 + j * 260 / 12) if hook else -math.pi / 2 + j * math.pi / 12 for j in range(13)]
                # The ring's straight side faces the lacing; the rounded half sits outside it.
                d = _path([(x + (2 * side - 1) * r * math.cos(a), y + r * math.sin(a)) for a in angles],
                          close=not hook)
                out.append(ln(d, min(3.0, r * 0.8), INK, 1) + ln(d, min(1.5, r * 0.4), METAL, 1))
        if p.get("toggle"):
            x, y = s(lo - 0.015, 0.0, 0.3)
            for side in (-1, 1):
                d = _path([(x, y), s(lo + 0.05, side * 0.15, 0.3), s(lo + 0.15, side * 0.1, 0.3)], close=False)
                out.append(ln(d, 2.8, INK, 1) + ln(d, 1.5, lace, 1))
            out.append(f'<rect x="{x - 0.8 * view.px:.1f}" y="{y - 0.65 * view.px:.1f}" width="{1.6 * view.px:.1f}" '
                       f'height="{1.3 * view.px:.1f}" rx="1" fill="{INK}"/>')
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
    upper = p.get("upper")
    if p.get("shine"):
        x, y = s(0.9, -0.3, 0.2)
        out.append(f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{1.4 * view.px:.1f}" ry="{0.5 * view.px:.1f}" fill="#fff" opacity=".55"/>')
    elif upper in ("smooth_calf", "synthetic_leather", "shell_cordovan"):   # a polished toe; cordovan's gloss is wider
        k = 1.35 if upper == "shell_cordovan" else 1.0
        x, y = s(0.88, -0.3, 0.2)
        out.append(f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{1.6 * k * view.px:.1f}" ry="{0.55 * k * view.px:.1f}" fill="#fff" '
                   f'opacity=".26"/>')
    elif upper == "oiled_pull_up":   # paler across the vamp, where it flexes
        x, y = s(0.72, 0.0, 0.1)
        out.append(f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{2.6 * view.px:.1f}" ry="{0.9 * view.px:.1f}" fill="#fff" opacity=".2"/>')
    return out


def _foot_top(u: float) -> float:
    """How high the top of a foot stands above the footbed at u (0 heel, 1 toe), in cm."""
    return _interp([(0.0, 7.5), (0.3, 7.0), (0.5, 5.5), (0.7, 3.8), (0.85, 2.6), (0.95, 1.6), (1.0, 0.8)], u)


def _strap(view, hw, sole_t, u0, u1):
    """A strap crossing the foot from one side of the footbed to the other, between u0 and u1."""
    def arc(u):
        w = hw(u) * 0.98
        return [view(_lean(u) + w * math.cos(math.pi * k / 12), u, sole_t + (_foot_top(u) + 0.3) * math.sin(math.pi * k / 12) ** 0.7)
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


def _foot_shape(view, ball: float, sole_t: float, leg: float):
    """A bare foot seen from the front, standing on a footbed `sole_t` above the ground: its outline as one shape
    with the ankle (which runs up to `leg`, into the leg drawn above it), the short lines between its toes, and
    the point between the big toe and the next one. The ankle is the narrowest part; below it the foot widens to
    the ball, and its front edge is a soft row of five toes, the big one on the inner side (+x), each one smaller
    and further back towards the outside."""
    def front(deg: float, scale: float, h: float = 0.5):
        a = math.radians(deg)
        u = BALL + (1 - BALL) * 0.96 * math.sin(a) * scale
        return view(_lean(u) + FOOT_IN * ball * math.cos(a) * scale, u, sole_t + h)

    edge = [front(TOES[0][0] * i / 4, 1 - TOE_NOTCH * (i / 4) ** 2) for i in range(4)]
    for a0, a1, reach in TOES:
        edge += [front(a0 + (a1 - a0) * i / 8, reach * (1 - TOE_NOTCH * (1 - math.sin(math.pi * i / 8)) ** 1.5)) for i in range(9)]
    last = TOES[-1]
    edge += [front(last[1] + (180 - last[1]) * i / 4, last[2] * (1 - TOE_NOTCH) + (1 - last[2] * (1 - TOE_NOTCH)) * (i / 4))
             for i in range(1, 5)]
    lines = []
    for (_, a, r0), (_, _, r1) in zip(TOES, TOES[1:], strict=False):
        r = min(r0, r1) * (1 - TOE_NOTCH)
        lines.append(_path([front(a, r * 0.97, 0.9), front(a, r * 0.9, 1.3)], close=False))
    post = front(TOES[0][1], min(TOES[0][2], TOES[1][2]) * 0.86, 0.9)
    anchor = _ankle_anchors(view, leg)
    (ax, _), half = anchor["ankle"], anchor["ankle_r"][0] - anchor["ankle"][0]
    y = lambda h: view(0.0, ANKLE_U, sole_t + h)[1]   # noqa: E731
    top = view(0.0, ANKLE_U, leg)[1]
    # down the inner side from the ankle to the ball, and back up the outer side: the ankle's sides are straight
    # (the leg above runs on into them), then the foot widens
    inner = [(ax + half - 2.0, top), (ax + half, y(11.5)), (ax + half, y(9.0)), (ax + half - 0.05 * view.px, y(6.0)),
             view(FOOT_IN * _half_width(0.62, ball, "round"), 0.62, sole_t + 1.0), edge[0]]
    outer = [edge[-1], view(-FOOT_IN * _half_width(0.6, ball, "round"), 0.6, sole_t + 0.9),
             view(-0.9 * _half_width(0.44, ball, "round"), 0.44, sole_t + 2.4), (ax - half - 0.05 * view.px, y(6.4)),
             (ax - half, y(9.0)), (ax - half, y(11.5)), (ax - half + 2.0, top)]
    return _path(_smooth(inner) + edge[1:-1] + _smooth(outer)), lines, post


def _toe_lines(lines: list[str], colour: str | None) -> list[str]:
    if not colour:
        return []
    return [f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="1" stroke-linecap="round" opacity=".4"/>' for d in lines]


def bare_feet(px: float, *, ankle: str, toes: str | None = None, uid: str = "fb") -> FrontShoe:
    """A bare foot from the front, placed as a shoe is (the toe on the ground line, the ball at x = 0), for a
    figure with trousers but no shoes. The figure draws `foot` with the legs, as one shape with them."""
    ball = STYLES["sandal"][0]
    view = _View(px)
    foot_d, lines, _ = _foot_shape(view, ball, 0.0, ANKLE_CM)
    pts = _points(foot_d)
    xs, ys = [x for x, _ in pts], [y for _, y in pts]
    anchors = {"ball": (0.0, view(0.0, BALL, 0.0)[1]), "toe": view(0.0, 1.0, 0.0), "heel": view(0.0, 0.0, 0.0),
               "ground": (0.0, 0.0), "top": (0.0, view(0.0, 0.2, 7.5)[1]), **_ankle_anchors(view, ANKLE_CM)}
    body = ankle.replace("{d}", foot_d) + "".join(_toe_lines(lines, toes))
    return FrontShoe(foot_d, (min(xs) - 2, min(ys) - 2, max(xs) + 2, max(ys) + 2), anchors, body, "", True, foot_d,
                     lines if toes else [])


def _points(d: str) -> list[tuple[float, float]]:
    return [(float(a), float(b)) for a, b in (pair.split(",") for pair in d.replace("M", " ").replace("L", " ").replace("Z", " ").split())]


def _sandal(p, view, hw, sole_t, base, sole_c, uid, ankle=None, toes=None, foot_d="", toe_lines=(), post=None):
    """A footbed seen from above at the front, a bare foot on it (with `ankle`), and straps over the foot: the
    sole first, then the foot, then the straps, each strap cut off at the foot's edge so it wraps over it. The
    figure has already drawn the foot with the legs, as one shape; it is drawn again here over the sole, from just
    under where the ankle's sides are straight, so nothing shows where the two meet. Returns the markup and its defs."""
    out, defs = [], ""
    us = [i / 40 for i in range(41)]
    bed = [view(_lean(u) + hw(u) * 0.94 * s, u, sole_t) for s in (1, -1) for u in (us if s > 0 else us[::-1])]
    out.append(f'<path d="{_path(bed)}" fill="{shade(sole_c, 0.12)}" stroke="{shade(sole_c, -0.25)}" stroke-width="1"/>')
    over = ""
    if ankle is not None and foot_d:
        skin, below = _below(ankle, foot_d, view(0.0, ANKLE_U, sole_t + 10.0)[1], uid)
        defs += below + f'<clipPath id="{uid}f"><path d="{foot_d}"/></clipPath>'
        out.append(skin)
        out += _toe_lines(list(toe_lines), toes)
        over = f' clip-path="url(#{uid}f)"'
    for u0, u1 in _sandal_bands(p):
        out.append(f'<path d="{_path(_strap(view, hw, sole_t, u0, u1))}" fill="{base}" stroke="{INK}" stroke-width="2" '
                   f'stroke-linejoin="round"{over}/>')
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
            a = math.pi * 4.2 / 12
            x, y = view(_lean(u) - w * math.cos(a), u, sole_t + (_foot_top(u) + 0.3) * math.sin(a) ** 0.7)
            out.append(f'<rect x="{x - 2.4:.1f}" y="{y - 2.4:.1f}" width="4.8" height="4.8" rx="1" fill="none" stroke="{METAL}" stroke-width="1.4"/>')
    if kind == "thong":   # a flip-flop: from a post between the toes, back over the foot to each side
        post = post or view(0.9, 0.9, sole_t + 0.6)
        crest = [view(sx * hw(0.7) * 0.5, 0.7, sole_t + _foot_top(0.7) * 0.85) for sx in (-1, 1)]
        ends = [view(sx * hw(0.5) * 0.97, 0.5, sole_t + 0.2) for sx in (-1, 1)]
        for c, e in zip(crest, ends, strict=True):
            d = f"M {post[0]:.1f},{post[1]:.1f} Q {c[0]:.1f},{c[1]:.1f} {e[0]:.1f},{e[1]:.1f}"
            out.append(f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="5" stroke-linecap="round"{over}/>'
                       f'<path d="{d}" fill="none" stroke="{base}" stroke-width="3" stroke-linecap="round"{over}/>')
        out.append(f'<circle cx="{post[0]:.1f}" cy="{post[1]:.1f}" r="2.2" fill="{base}" stroke="{INK}" stroke-width="1.2"/>')
    return out, defs
