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
    """Turns points on the shoe (x across, u from heel 0 to toe 1, h above the ground, in cm) into the drawing.
    `warp` (u, h) -> h, when given, moves heights along the shoe before it is seen (a traced sole's thickness and
    toe spring); the ground line stays where an unwarped shoe's toe touches it."""

    def __init__(self, px: float, warp=None):
        self.px = px
        self.ct, self.st = math.cos(math.radians(TURN)), math.sin(math.radians(TURN))
        self.cl, self.sl = math.cos(math.radians(LOOK)), math.sin(math.radians(LOOK))
        self.warp = None
        self.y0 = 0.0
        self.y0 = self.raw(0.0, 1.0, 0.0)[1]
        self.warp = warp

    def raw(self, x: float, u: float, h: float) -> tuple[float, float]:
        if self.warp is not None:
            h = self.warp(u, h)
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
               ankle: str | None = None, toes: str | None = None, ankle_path: str | None = None,
               traced=None, kind: str | None = None) -> FrontShoe:
    """The shoe of `spec` from the front, scaled by `px`. With `ankle` (markup for skin, with "{d}" for its path),
    the wearer's ankle stands in the shoe's opening, and a sandal holds a bare foot (`toes`: the colour of the
    lines between its toes). `ankle_path` keeps the figure's own leg contour through the opening, in shoe
    coordinates. The anchor "ankle" is where the leg above it ends, "ankle_r" its right edge there.
    With `traced` (a `traced.TracedShoe`, or its JSON) whose photo passed the quality gate, the shoe's shape,
    colour panels, marks and laces come from the trace (`_Traced`); otherwise it is drawn from its style words.
    `kind` (or a `Chosen`'s): FROM_PHOTO turns the traced side into the front view (B); FROM_SHAPE draws the
    style's template painted with the trace's colours (A). A `Chosen` may carry a front photo's `FrontLook` too."""
    p = {**spec.params, "lace_color": spec.lace_color}
    style = p.get("style") or ("high_top" if p.get("height") == "high" else "low_sneaker")
    if style not in STYLES:
        style = "low_sneaker"
    toe = p.get("toe", "round")
    look = None
    if isinstance(traced, Chosen):
        traced, kind, look = traced.trace, kind or traced.kind, traced.front
    tr = _Traced.of(usable_trace(traced), toe, style) if traced is not None and style != "sandal" else None
    shaped = tr is not None and kind == FROM_SHAPE
    if tr is not None and look is not None and not shaped:
        tr.see_front(FrontLook.of(look))
    # the shape is always the template's for the tagger's style: A and B have the same outline, opening and toe;
    # they differ only in how the trace's colours are painted on it
    ball, sole_t, table, shaft = STYLES[style]
    sole_t *= {"thin": 0.75, "chunky": 1.6}.get(p.get("sole"), 1.0)
    sole_t *= {"lug": 1.25, "eva": 1.35, "city": 0.85}.get(p.get("tread"), 1.0)
    if style == "sandal" and p.get("molded"):   # a moulded slide: one deeper piece
        sole_t *= 1.25
    if shaft and p.get("shaft"):
        shaft = max(0.35, min(0.95, float(p["shaft"]))) * LENGTH
    inset = 0.93 if style in ("loafer", "derby", "oxford") else 0.97
    if tr is not None:
        # A: the template painted with the trace's part colours; B: with the trace's colours sampled as the photo
        # shows them, bent from the traced side onto the template's
        tr = tr.on_template(ball, sole_t, table, shaft, inset, toe, sampled=not shaped)
        if shaped:
            p = {**p, **tr.template_words()}
    view = _View(px)
    hw = lambda u: _half_width(u, ball, toe)   # noqa: E731
    mid = _lean if style == "sandal" else (lambda u: 0.0)   # a sandal's footbed is the shape of a foot
    us = [i / 60 for i in range(61)]
    base = tr.base if tr is not None else spec.fill.color
    dark = luminance(base) < 0.3
    sole_c = (tr.sole_c if tr is not None else None) or spec.sole_color or sole_default or "#f4f1ea"
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
    if tr is not None:   # the traced sole: its bands from the ground up, each at its traced share of the thickness
        if len(tr.bands) > 1:
            g = ""
            for k, (f0, f1, c) in enumerate(tr.bands):
                # each band sits on the one below and hides its top: only the lower one's edge under it shows
                d = _path(_hull([view(*q) for h in (sole_t * f0, sole_t * f1) for q in contour(h)]))
                g += fill(d, c, edge=False)
                if k:
                    below = tr.bands[k - 1][2]
                    g += ln(d, 1.0, shade(below, -0.3 if luminance(below) > 0.25 else 0.25), 0.8)
            out.append(f'<g clip-path="url(#{uid}s)">{g}</g>')
    elif style in TRAINERS or p.get("tread") == "eva":   # a trainer's sole: the outsole under it a shade darker, so its edge reads under a hem
        low = [view(*q) for h in (0.0, sole_t * 0.32) for q in contour(h)]
        c = shade(sole_c, -0.22 if luminance(sole_c) > 0.25 else 0.18)
        out.append(f'<g clip-path="url(#{uid}s)">' + fill(_path(_hull(low)), c, edge=False) + "</g>")
    if tr is None and (style in ("high_top", "slip_on") + TRAINERS or p.get("foxing")):   # the stripe round a vulcanised sole
        line = [view(x, u, sole_t * 0.55) for x, u, _ in contour(0)]
        out.append(f'<g clip-path="url(#{uid}s)">' + ln(_path(line, close=False), 1.1,
                                                         shade(sole_c, -0.3 if luminance(sole_c) > 0.25 else 0.22), 1) + "</g>")
    if tr is None and (p.get("tread") in ("lug", "crepe") or style in ("boot",)):   # a thick outsole: its lower part darker
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
            ring = [view(*q) for q in _collar_ring(hw, inset, table, sole_t, shaft)]
            vamp_top = min(y for _, y in vamp_pts) if shaft else None
            upper_d, collar_seen = _collar_front(_hull(upper_pts), ring, px, vamp_top)
        out.append(fill(upper_d, base, w=2.4))
        defs += f'<clipPath id="{uid}u"><path d="{upper_d}"/></clipPath>'
        if tr is not None:   # the traced colour panels and marks, on the solid, then its outline again over their edges
            out.append(f'<g clip-path="url(#{uid}u)">' + "".join(tr.paint(view, line_c)) + "</g>"
                       + f'<path d="{upper_d}" fill="none" stroke="{INK}" stroke-width="2.4" stroke-linejoin="round"/>')
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
        if tr is None and (style == "high_top" or p.get("toe_cap") == "rubber"):   # a rubber toe in the sole's colour
            cap = [view(hw(u) * inset * math.cos(math.pi * k / 12), u, sole_t + _interp(table, u) * math.sin(math.pi * k / 12))
                   for u in us if u >= 0.87 for k in range(13)]
            cap += [view(x, u, sole_t) for x, u, _ in contour(0, inset) if u >= 0.8]
            out.append(f'<g clip-path="url(#{uid}u)">' + fill(_path(_hull(cap)), sole_c, w=1.3) + "</g>")
        if style == "chelsea_boot" or p.get("gusset"):   # its pull tab is at the back: behind the leg
            out.append(_pull_tab(view, shaft or sole_t + 9, base))
        out += _opening(p, view, hw, inset, table, sole_t, shaft, base, ankle, upper_d, uid, leg, ankle_path, collar_seen,
                        behind=tr is not None, keep=seen_by)
        if tr is not None and not shaped and tr.laced:   # B: the traced laces instead of the style's
            out += _details({**p, "laces": False}, style, view, hw, inset, table, sole_t, shaft, base, line_c, ln, fill, traced=True)
            out += tr.lacing(view, hw, inset, ln, p.get("lace_color") or _lace_shade(base))
        else:
            out += _details(p, style, view, hw, inset, table, sole_t, shaft, base, line_c, ln, fill, traced=tr is not None)
        outline_pts = sole_pts + upper_pts
        # where a trouser hem meets it: the front and the back of the opening (a low shoe's collar, the top of a
        # boot's shaft), the instep in front of it, and how wide the solid is round the opening
        ring = _collar_ring(hw, inset, table, sole_t, shaft)
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


def _collar_ring(hw, inset, table, sole_t, shaft):
    """The opening's edge."""
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
            h = sole_t + _interp(table, 0.04) - 0.5 + (0.6 if math.sin(a) > 0 else 0) * math.sin(a)
            ring.append((x, u, h))
    return ring


def _opening(p, view, hw, inset, table, sole_t, shaft, base, ankle, upper_d, uid, leg, ankle_path=None, collar_seen=None,
             behind=False, keep=None):
    """The way in: the collar of a low shoe, or the top of a boot's shaft, with the dark lining inside; and the
    wearer's ankle standing in it when asked for, up to where the leg drawn above it takes over."""
    out = []
    lining = SHEARLING if p.get("lining") == "shearling" else _mix(base, LINING, 0.82)
    ring = _collar_ring(hw, inset, table, sole_t, shaft)
    rim = [view(*q) for q in ring]
    rim_d = _path(rim)
    # where the ankle is seen: in the opening, and above the back half of the collar, which is behind it (the
    # heel counter's top, seen from above, stands up behind the ankle; only the collar's sides, curving round
    # it, are in front of it)
    # (a traced shoe's ankle also stands in front of all that is behind it above the rim: the back of a boot's
    # shaft, and the heel's top beside the ankle, turned out from behind it)
    if collar_seen:
        seen_d = collar_seen
    else:
        seen = rim + [view(x, u, h + BEHIND_CM) for x, u, h in ring if u <= (0.2 if shaft else 0.27)]
        if behind:
            seen += _column(view, min(h for _, _, h in ring), leg + BEHIND_CM)
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


def _details(p, style, view, hw, inset, table, sole_t, shaft, base, line_c, ln, fill, traced=False):
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
    if style in TRAINERS and not traced:   # the overlay round the toe box (a traced shoe has its own panels)
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


# ------------------------------------------------------------------ a traced shoe (#192, stage 2c)
#
# A shoe traced from the owner's side-on photo (`traced.TracedShoe`) is drawn from the front as the same small
# solid, its shape measured instead of looked up: the upper's height along the length from the traced top line,
# the sole's thickness and toe spring from the traced sole (folded into the view as a warp of heights), a boot's
# shaft from the traced collar, the width at the ball from the style hint, adjusted by the profile. The traced
# colour pieces are painted on the solid: each side-view point (u, cm above the ground) goes onto the upper's
# cross-section at u, as high round it as it is up the traced side (a piece reaching the top line reaches the
# crest), on the outer side (-x) and, mirrored, on the inner one, then is seen with the same view as the outline.
# Only what faces the viewer is painted: each piece is cut where its side turns away, so a mark in the middle of
# the side mostly disappears and one near the toe or the instep shows, foreshortened. The photo saw the outer side;
# a pair's marks are on both sides, and the toe-out turn shows more of the inner one, so marks go on both too.

PAINT_STEP_CM = 0.3          # a traced outline is cut into steps this long before it is bent onto the solid
SHAFT_AX, SHAFT_AU, SHAFT_RX, SHAFT_RU = 0.0, 0.2, 4.7, 5.2   # a boot's shaft (as `front_shoe` draws it)
MARK_NEAR_CM = 0.6           # a colour piece over a mark (within this) in its colour is that mark (drawn as a mark)
DETAILS = ("laces", "eyelets", "stitching", "midsole", "outsole")
LACES_MIN = 3                # a traced row of laces or eyelets with fewer than this is not trusted
THIN_CM = 0.3                # a colour piece thinner than this (a highlight, a seam) is not a panel
MIN_PANEL_CM2 = 18.0         # a colour piece smaller than this (a lace, a blotch of camouflage) is not a panel either
MIN_BLOCK_CELLS = 30         # a block of one colour smaller than this many cells takes the colour round it
SOLE_SPREAD = 1.6            # how much thicker (or thinner) a traced sole may be anywhere than along its middle
PATTERN_SHARE = 0.15         # small pieces covering this share of the upper are its pattern, mixed into its colour
RIM_CM = 0.6                 # the band just under the top line (its edge in shade) is not what the crest is
NOSE_U = 0.92                # past this the photo sees the toe's end edge on: the nose takes the colours here
BOOTS = ("boot", "chelsea_boot", "high_top")
BOOT_COLLAR_CM = 10.8        # a shoe the tagger called a boot keeps its shaft when its traced collar is this high ...
BOOT_ABOVE_SOLE_CM = 7.5     # ... above the ground, and this high above the sole
SOLE_LEVELS = 20            # the sole is read at this many heights through it
GRID_U, GRID_A = 72, 16      # the upper is painted in this many steps along it and up each side
SHAFT_STEP_CM = 0.8          # ... and a boot's shaft in steps this tall
MARK_SHARE = 0.12            # a mark (or a piece taken for one) is smaller than this share of the upper; a bigger one is a panel
MARK_CONTRAST = 60.0         # and stands out from the upper's colour by this much (RGB distance, 0-255)
MARK_COLOUR = 40.0           # a colour piece this near a mark's colour (RGB distance, 0-255) and over it is that mark
TOE_U = 0.8                  # from here to the toe, the upper's height is the style's: its round toe, as A's
TOE_FROM = 0.6               # ... reached from the traced height over the stretch from here
THROAT_U = ANKLE_U + ANKLE_DEPTH_CM / LENGTH   # in front of this the upper is in front of the leg: no collar there
LACE_FROM, LACE_TO = 0.53, 0.88   # the lacing stays on the vamp, in front of the opening, behind the toe box
MIN_MARK_CM2 = 1.0           # a mark smaller than this (a speck) is not drawn on the template (A)
FROM_SHAPE, FROM_PHOTO = "shape", "photo"    # the two front views of a traced shoe: A and B


@dataclass
class Chosen:
    """A traced shoe, the front view the owner chose for it (FROM_SHAPE or FROM_PHOTO), and what its front photo
    showed (a `FrontLook` or its dict), when there is one."""
    trace: object
    kind: str = FROM_PHOTO
    front: object = None


@dataclass
class FrontLook:
    """What a photo of the shoe from the front (or from above) shows, measured by `frontlook.measure`: the toe box's
    and the vamp's colours, the laces (how many crossings, their colour), the marks on the front (colour, where
    across (-1 outer .. 1 inner) and along (0 the throat .. 1 the toe) it sits, how big as a share of the front),
    and the front's width over its height (how round and full its toe is)."""
    toe: str | None = None
    vamp: str | None = None
    laces: int = 0
    lace_color: str | None = None
    marks: list = field(default_factory=list)   # [colour, x, v, size]
    aspect: float = 0.0

    @classmethod
    def of(cls, look) -> FrontLook | None:
        if look is None or isinstance(look, FrontLook):
            return look
        if isinstance(look, str):
            import json
            try:
                look = json.loads(look)
            except ValueError:
                return None
        if not isinstance(look, dict):
            return None
        known = {k: look[k] for k in ("toe", "vamp", "laces", "lace_color", "marks", "aspect") if k in look}
        try:
            return cls(**known)
        except TypeError:
            return None


def _see() -> tuple[float, float, float]:
    ct, st = math.cos(math.radians(TURN)), math.sin(math.radians(TURN))
    cl, sl = math.cos(math.radians(LOOK)), math.sin(math.radians(LOOK))
    return st * cl, ct * cl, sl


SEE = _see()   # the direction towards the viewer, in (x, z = (u - BALL) * LENGTH, h) on the shoe


def usable_trace(traced):
    """The traced shoe to draw from (a `traced.TracedShoe`, read from JSON when given as text), or None to keep the
    drawing from the style words: no trace, a record this program cannot read, or a photo the gate turned down."""
    if traced is None:
        return None
    if isinstance(traced, str):
        from .traced import TracedShoe  # here: `traced` imports this module
        try:
            traced = TracedShoe.from_json(traced)
        except (ValueError, KeyError, TypeError):
            return None
    try:
        ok = (bool(traced.gate.get("ok")) and STYLES.get(traced.style, (0, 0, None))[2] is not None
              and len(traced.profile.u) >= 5 and len(traced.profile.u) == len(traced.profile.top))
    except AttributeError:
        return None
    return traced if ok else None


def _lerp(xs, ys, x: float) -> float:
    if x <= xs[0]:
        return float(ys[0])
    if x >= xs[-1]:
        return float(ys[-1])
    lo, hi = 0, len(xs) - 1
    while hi - lo > 1:
        m = (lo + hi) // 2
        if xs[m] <= x:
            lo = m
        else:
            hi = m
    t = (x - xs[lo]) / ((xs[hi] - xs[lo]) or 1.0)
    return float(ys[lo] + (ys[hi] - ys[lo]) * t)


def _median(vs) -> float:
    vs = sorted(vs)
    n = len(vs)
    return float(vs[n // 2] if n % 2 else (vs[n // 2 - 1] + vs[n // 2]) / 2) if n else 0.0


def _mean7(vs) -> list[float]:
    """Each value the mean of it and its three neighbours either side: the sole's steps (a window, a heel's edge)
    eased, so the collar and the laces standing on it run smoothly."""
    return [sum(vs[max(0, i - 3):i + 4]) / len(vs[max(0, i - 3):i + 4]) for i in range(len(vs))]


def _median5(vs) -> list[float]:
    """Each value the median of it and its two neighbours either side: a heel tab or a speck is not the shape."""
    return [_median(vs[max(0, i - 2):i + 3]) for i in range(len(vs))]


def _thickness(ring) -> float:
    """How thick a traced outline (u, cm) is, in cm: twice its area over its length round."""
    pts = [(u * LENGTH, h) for u, h in ring]
    nxt = pts[1:] + pts[:1]
    area = abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, nxt, strict=True))) / 2
    return 2 * area / (sum(math.dist(a, b) for a, b in zip(pts, nxt, strict=True)) or 1.0)


def _near(a: str, b: str, tol: float = MARK_COLOUR) -> bool:
    return math.dist(_rgb(a), _rgb(b)) * 255 <= tol


def _box(ring) -> tuple[float, float, float, float]:
    return min(q[0] for q in ring), min(q[1] for q in ring), max(q[0] for q in ring), max(q[1] for q in ring)


def _over(a, b, pad: float = MARK_NEAR_CM) -> bool:
    """Whether two traced outlines' boxes overlap (within `pad` cm)."""
    (u0, h0, u1, h1), (v0, k0, v1, k1) = _box(a), _box(b)
    p = pad / LENGTH
    return u0 <= v1 + p and v0 <= u1 + p and h0 <= k1 + pad and k0 <= h1 + pad


def _centre(ring) -> tuple[float, float]:
    return sum(q[0] for q in ring) / len(ring), sum(q[1] for q in ring) / len(ring)


def _area(ring) -> float:
    """A traced outline's area, in square cm."""
    pts = [(u * LENGTH, h) for u, h in ring]
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1], strict=True))) / 2


class _Raster:
    """Traced colour layers (colour, [outline, holes ...]), painted one over another into a fine grid of the side
    view (u along the length, cm above the ground), to look up what colour the photo shows at a point."""
    DU, DH, TOP = 0.004, 0.1, 40.0

    def __init__(self, layers):
        self.colours: list[str] = []
        nu, nh = round(1 / self.DU), round(self.TOP / self.DH)
        self.grid = [bytearray(nu) for _ in range(nh)]
        for colour, rings in layers:
            if colour not in self.colours:
                self.colours.append(colour)
            v = self.colours.index(colour) + 1
            if v > 255 or not rings:
                continue
            hs = [h for ring in rings for _, h in ring]
            for row in range(max(0, int(min(hs) / self.DH)), min(nh, int(max(hs) / self.DH) + 1)):
                y = (row + 0.5) * self.DH
                xs = sorted(u0 + (u1 - u0) * (y - h0) / (h1 - h0)
                            for ring in rings for (u0, h0), (u1, h1) in zip(ring, ring[1:] + ring[:1], strict=True)
                            if (h0 <= y) != (h1 <= y))
                line = self.grid[row]
                for a, b in zip(xs[::2], xs[1::2], strict=False):   # inside between each pair of crossings
                    c0, c1 = max(0, math.ceil(a / self.DU - 0.5)), min(nu - 1, math.floor(b / self.DU - 0.5))
                    if c1 >= c0:
                        line[c0:c1 + 1] = bytes([v]) * (c1 - c0 + 1)

    def at(self, u: float, h: float) -> str | None:
        row, col = int(h / self.DH), int(u / self.DU)
        if not (0 <= row < len(self.grid) and 0 <= col < len(self.grid[0])):
            return None
        v = self.grid[row][col]
        return self.colours[v - 1] if v else None


def _merge_small(cells: list) -> list:
    """The upper's cells with each block of one colour smaller than MIN_BLOCK_CELLS (a speck, a sliver along a
    panel's edge) given the colour most common round it, so the upper reads as a few clean blocks of colour."""
    grid = {(side, i, j, part): c for side, i, j, c, _, part in cells}
    for _ in range(4):
        seen: set = set()
        changed = False
        for key in sorted(grid):
            if key in seen:
                continue
            c, block, todo, edge = grid[key], [], [key], {}
            seen.add(key)
            while todo:
                side, i, j, part = todo.pop()
                block.append((side, i, j, part))
                for q in ((side, i + 1, j, part), (side, i - 1, j, part), (side, i, j + 1, part), (side, i, j - 1, part)):
                    if q not in grid:
                        continue
                    if grid[q] == c:
                        if q not in seen:
                            seen.add(q)
                            todo.append(q)
                    else:
                        edge[grid[q]] = edge.get(grid[q], 0) + 1
            if len(block) < MIN_BLOCK_CELLS and edge:
                other = max(edge, key=lambda k: (edge[k], k))
                for q in block:
                    grid[q] = other
                changed = True
        if not changed:
            break
    return [(side, i, j, grid[(side, i, j, part)], g, part) for side, i, j, _, g, part in cells]


def _sole_bands(t, us, bottom, sole) -> list[tuple[float, float, str]]:
    """The sole's colour bands from the ground up, as the photo shows them: at each of SOLE_LEVELS heights through
    the sole, the colour most of its length shows (so a window or a logo in it does not count), then runs of one
    colour joined; a band thinner than two levels goes to the band beside it."""
    layers = []
    for r in t.regions[1:]:
        for k, piece in enumerate(r.paths):
            label = r.labels[k] if k < len(r.labels) else ""
            if (r.part == "sole" or label in ("midsole", "outsole")) and piece and len(piece[0]) >= 3:
                layers.append((r.color, [ring for ring in piece if len(ring) >= 3]))
    if not layers:
        return []
    side = _Raster(layers)
    cols = [0.1 + 0.8 * i / 40 for i in range(41)]
    levels: list[str | None] = []
    for k in range(SOLE_LEVELS):
        f = (k + 0.5) / SOLE_LEVELS
        seen: dict[str, int] = {}
        for u in cols:
            c = side.at(u, _lerp(us, bottom, u) + f * _lerp(us, sole, u))
            if c is not None:
                seen[c] = seen.get(c, 0) + 1
        best = max(seen, key=lambda c: (seen[c], c)) if seen else None
        levels.append(best if best is not None and seen[best] >= 0.3 * len(cols) else None)
    if not any(levels):
        return []
    for k in range(SOLE_LEVELS):   # a level nothing was found at takes the one below it, or above
        if levels[k] is None:
            levels[k] = next((c for c in levels[k::-1] if c), None) or next(c for c in levels[k:] if c)
    runs: list[list] = []
    for k, c in enumerate(levels):
        if runs and runs[-1][2] == c:
            runs[-1][1] = k + 1
        else:
            runs.append([k, k + 1, c])
    while len(runs) > 1 and min(r[1] - r[0] for r in runs) < 2:
        i = min(range(len(runs)), key=lambda i: (runs[i][1] - runs[i][0], i))
        j = i - 1 if i == len(runs) - 1 or (i > 0 and runs[i - 1][1] - runs[i - 1][0] >= runs[i + 1][1] - runs[i + 1][0]) else i + 1
        lo, hi = min(runs[i][0], runs[j][0]), max(runs[i][1], runs[j][1])
        runs[min(i, j)] = [lo, hi, runs[j][2]]
        del runs[max(i, j)]
        k = 0
        while k + 1 < len(runs):   # neighbours now the same colour join
            if runs[k][2] == runs[k + 1][2]:
                runs[k][1] = runs[k + 1][1]
                del runs[k + 1]
            else:
                k += 1
    return [(a / SOLE_LEVELS, b / SOLE_LEVELS, c) for a, b, c in runs]


@dataclass
class _Traced:
    """The front view's shape and paint, measured from a traced shoe."""
    t: object                     # the TracedShoe
    style: str
    ball: float
    sole_t: float                 # the solid's sole thickness; the warp moves it to the traced one at each u
    table: list                   # the upper's height above the sole along the length, as STYLES' tables
    shaft: float
    base: str
    sole_c: str | None
    bands: list                   # the sole's bands from the ground up: (from, to as shares of its thickness, colour)
    us: list = field(default_factory=list)
    bottom: list = field(default_factory=list)
    sole: list = field(default_factory=list)
    side: _Raster | None = None                   # the traced upper's colours, side on
    marks: list = field(default_factory=list)     # (colour, outline) painted on both sides, unstroked
    inset: float = 0.97
    hw: object = None
    rim: float = 0.0

    @classmethod
    def of(cls, t, toe: str = "round", words: str | None = None) -> _Traced | None:
        if t is None:
            return None
        P = t.profile
        us = [float(u) for u in P.u]
        bottom5 = _median5([max(0.0, float(b)) for b in P.bottom])
        bottom = _mean7(bottom5)
        sole_raw = [float(s) for s in P.sole]
        mid = [s for u, s in zip(us, sole_raw, strict=True) if 0.1 <= u <= 0.9 and s > 0]
        style = t.style
        if STYLES[style][3] and words in BOOTS:   # both see a shaft: the tagger's word for which kind
            style = words
        elif words in BOOTS:
            # the tagger saw a boot and the trace's collar stands high enough round the ankle for one, though below
            # the trace's own line between a boot and a shoe (a chukka's collar sits just over the ankle bone)
            back = [i for i, u in enumerate(us) if u <= 0.3]
            collar = _median([float(P.top[i]) for i in back])
            heel = _median([bottom[i] + max(0.0, float(P.sole[i])) for i in back])
            if collar >= BOOT_COLLAR_CM and collar - heel >= BOOT_ABOVE_SOLE_CM:
                style = words
        ball, style_sole, style_table, style_shaft = STYLES[style]
        sole_t = min(7.0, max(0.5, _median(mid) if mid else style_sole))
        # a sole thinner or thicker than its own middle by much is a trace's slip (a white midsole under a white upper
        # read only where a stripe comes down to it), not a wedge: the front view keeps it within SOLE_SPREAD
        lo, hi = sole_t / SOLE_SPREAD, sole_t * SOLE_SPREAD
        sole5 = _median5([min(hi, max(lo, 0.4, s if s > 0 else sole_t)) for s in sole_raw])
        sole = _mean7(sole5)
        above = _median5([max(0.0, float(tp) - b - s) for tp, b, s in zip(P.top, bottom, sole, strict=True)])
        table = [(u, max(a, 0.8 if u >= 0.95 else 1.5)) for u, a in zip(us, above, strict=True)]
        shaft = 0.0
        if style_shaft:   # a shaft: the traced collar (its median along the back 30%); the upper in front of it
            collar = _median([float(tp) for u, tp in zip(us, P.top, strict=True) if u <= 0.3])
            lift = _lerp(us, bottom, SHAFT_AU) + _lerp(us, sole, SHAFT_AU) - sole_t
            shaft = min(0.95 * LENGTH, max(sole_t + 6.0, collar - lift))
            k = _interp(table, 0.56) / max(_interp(style_table, 0.56), 0.1)
            table = [(u, min(h, _interp(style_table, u) * k)) if u < 0.56 else (u, h) for u, h in table]
        # the toe is the style's, as A draws it: the trace's height runs into the style's curve from TOE_FROM, so
        # a tall or boxy toe in the photo does not square it off; the footprint (the width) is the style's too
        def toe(u, h):
            if u <= TOE_FROM:
                return h
            t = min(1.0, (u - TOE_FROM) / (TOE_U - TOE_FROM))
            return max((1 - t) * h + t * _interp(style_table, u), 0.8)
        table = [(u, toe(u, h)) for u, h in table]
        # nor is the sole thicker at the toe than across the ball (a bumper wrapping up the toe is not sole)
        cap = _lerp(us, sole, TOE_U)
        sole = [min(s, cap) if u > TOE_U else s for u, s in zip(us, sole, strict=True)]
        base = t.regions[0].color if t.regions else (t.part("vamp").color if t.part("vamp") else "#808080")
        mids, outs = t.part("midsole"), t.part("outsole")
        sole_c = mids.color if mids and mids.measured else outs.color if outs and outs.measured else None
        outsole_c, out_frac = None, 0.35
        if mids and outs and mids.measured and outs.measured and mids.color.lower() != outs.color.lower() and outs.region:
            rel = sorted((h - _lerp(us, bottom5, u)) / max(_lerp(us, sole5, u), 0.3)
                         for ring in outs.region for u, h in ring if 0.05 <= u <= 0.95)
            if rel:
                outsole_c, out_frac = outs.color, min(0.7, max(0.12, rel[int(0.8 * (len(rel) - 1))]))
        bands = _sole_bands(t, us, bottom5, sole5)
        if len({c for _, _, c in bands}) < 2 and outsole_c:
            # one colour all along, but a midsole of its own was traced (a thin one, broken by a window): its band
            bands = [(0.0, out_frac, outsole_c), (out_frac, 1.0, sole_c)]
        elif bands:
            sole_c = bands[-1][2]
        elif outsole_c:
            bands = [(0.0, out_frac, outsole_c), (out_frac, 1.0, sole_c)]
        marks = [(m.color, ring) for m in t.marks for ring in m.path if len(ring) >= 3]
        # how much upper the photo shows: the silhouette less the sole
        sil = sum(_area(ring) for r in t.regions[:1] for piece in r.paths for ring in piece[:1] if len(ring) >= 3)
        soles = sum(_area(piece[0]) for r in t.regions[1:] for k, piece in enumerate(r.paths)
                    if piece and len(piece[0]) >= 3
                    and (r.part == "sole" or (r.labels[k] if k < len(r.labels) else "") in ("midsole", "outsole")))
        small = MARK_SHARE * max(sil - soles, 1.0)
        ground = t.regions[0].color if t.regions else None
        # the marks that are only marks: each small beside the upper and standing out from it (a swoosh, a stripe),
        # not a panel the trace also called a mark (a red quarter on a runner)
        strong = [(c, ring) for c, ring in marks
                  if _area(ring) < small and (ground is None or not _near(c, ground, MARK_CONTRAST))]

        def is_mark(colour, ring) -> bool:
            # a small piece over such a mark, in its colour: the mark itself (drawn with the marks), never part of a
            # part's colour or the upper's mix
            return _area(ring) < small and any(_near(colour, c) and _over(ring, m) for c, m in strong)
        masked: list = []   # the pieces taken for marks: drawn as marks
        # what the photo shows on the upper, layer over layer as traced: the silhouette, then each colour piece
        # big enough to be a panel (a smaller piece, or a smaller hole in one, takes the colour round it)
        layers = [(r.color, [ring for piece in r.paths for ring in piece[:1] if len(ring) >= 3]) for r in t.regions[:1]]
        specks: dict[str, float] = {}   # the small pieces' area, by colour
        pieces: list = []               # the panels kept: (colour, label, outline)
        sole_area = 0.0
        for r in t.regions[1:]:
            for k, piece in enumerate(r.paths):
                label = r.labels[k] if k < len(r.labels) else ""
                if not piece or len(piece[0]) < 3:
                    continue
                if r.part == "sole" or label in ("midsole", "outsole"):
                    sole_area += _area(piece[0])
                    continue
                if _thickness(piece[0]) < THIN_CM:
                    continue   # a line of light or stitching along the side, not a panel of the upper
                if is_mark(r.color, piece[0]):
                    # drawn with the marks; the piece itself when the trace's mark kept only a bit of it
                    if not any(_near(r.color, c) and _over(piece[0], m) and _area(m) >= 0.6 * _area(piece[0])
                               for c, m in strong):
                        masked.append((r.color, piece[0]))
                    continue
                if _area(piece[0]) < MIN_PANEL_CM2:   # a lace, a speck, a blotch of camouflage: not a panel
                    specks[r.color] = specks.get(r.color, 0.0) + _area(piece[0])
                    continue
                layers.append((r.color, [ring for i, ring in enumerate(piece)
                                         if len(ring) >= 3 and (i == 0 or _area(ring) >= MIN_PANEL_CM2)]))
                pieces.append((r.color, label, piece[0]))
        if layers and layers[0][1]:
            # a busy upper (camouflage, a print): so many small pieces that together they are much of what the eye
            # sees; the upper's own colour is then their mix with it, as they blur together seen from afar
            upper = max(0.0, sum(_area(ring) for ring in layers[0][1]) - sole_area)
            small = sum(specks.values())
            if upper and small >= PATTERN_SHARE * upper:
                kept = sum(_area(ring) for _, rings in layers[1:] for ring in rings[:1])
                weights = [(layers[0][0], max(0.0, upper - kept - small))] + list(specks.items())
                total = sum(w for _, w in weights) or 1.0
                mixed = _hex(tuple(sum(_rgb(c)[i] * w for c, w in weights) / total for i in range(3)))
                layers[0] = (mixed, layers[0][1])
        tr = cls(t, style, ball, sole_t, table, shaft, "#808080", sole_c, bands, us, bottom, sole, _Raster(layers), marks + masked)
        tr.pieces = pieces
        tr.mark_colours = sorted({c for c, _ in strong})
        # the collar's and the heel counter's pieces: at the back, behind the leg, never across the throat
        back = [(c, [ring]) for c, label, ring in pieces if label in ("collar", "heel_counter")]
        tr.back = _Raster(back) if back else None
        # the collar's height at the back: the traced top line's middle over the heel (not its very end, where
        # the trace's corner is rounded off)
        tr.rim = _median([h for u, h in table if 0.03 <= u <= 0.25]) or _interp(table, 0.04)
        tr.inset = 0.93 if style in ("loafer", "derby", "oxford") else 0.97
        tr.hw = lambda u: _half_width(u, ball, toe)   # noqa: E731
        tr.hw.toe = toe
        tr.base = tr._most_seen() or base
        return tr

    @property
    def laces(self):
        return self.t.laces

    @property
    def eyelets(self):
        return self.t.eyelets

    @property
    def laced(self) -> bool:
        """Whether the trace found lacing to draw: a row of at least LACES_MIN crossings or eyelets (fewer is more
        likely a collar or a seam than laces; the style's laces are drawn instead)."""
        return any(r is not None and r.count >= LACES_MIN for r in (self.laces, self.eyelets))

    def on_template(self, ball, sole_t, table, shaft, inset, toe, sampled=False) -> _Traced:
        """The style's solid, painted with the trace. A: the trace's part colours where the template has those parts,
        and its marks and side panels bent from the traced side onto the template's at the same place. B (`sampled`):
        the colours the photo shows, sampled as on the traced shoe at the same place along it and up its side, and
        its marks bent onto the template's side the same way."""
        tpl = _Traced(self.t, self.style, ball, sole_t, list(table), shaft, self.base, self.sole_c, self.bands,
                      [0.0, 1.0], [0.0, 0.0], [sole_t, sole_t], self.side, [], inset, lambda u: _half_width(u, ball, toe),
                      self.rim)
        if sampled:
            tpl.src, tpl.front = self, self.front
            tpl.marks = [(c, [self._onto(tpl, u, h) for u, h in ring]) for c, ring in self.marks]
            tpl.base = tpl._most_seen() or self.base
            return tpl
        # a part in a mark's colour is that mark (stripes the trace took for the quarter), not the part's colour
        marked = self.mark_colours
        panels = {c for c, _, _ in self.pieces}
        parts = {q.name: q.color for q in self.t.parts if q.measured and not q.within and q.name not in DETAILS
                 and not (q.color not in panels and any(_near(q.color, c) for c in marked))}
        # the upper's own colour as B sees it under its panels (a busy upper's mixed colour)
        upper = self.side.colours[0] if self.side is not None and self.side.colours else self.base
        zones = {"upper": upper, **parts}
        # the toe box and the vamp as B sees them: the upper's top surface (a mudguard low round the toe is not it)
        for name, u0, u1 in (("vamp", 0.5, 0.8), ("toe_cap", 0.84, 0.92)):
            seen = [self._side_colour(u0 + (u1 - u0) * i / 6, 0.6 + 0.4 * j / 4) for i in range(7) for j in range(5)]
            seen = [c for c in seen if c]
            if seen:
                zones[name] = max(set(seen), key=lambda c: (seen.count(c), c))
        if zones.get("toe_cap") == zones.get("vamp", upper):
            zones.pop("toe_cap", None)
        tpl.zones = zones
        for c, ring in self.marks:   # every mark B shows (whatever its kind, and the pieces taken for marks), not specks
            if _area(ring) >= MIN_MARK_CM2:
                tpl.marks.append((c, [self._onto(tpl, u, h) for u, h in ring]))
        for c, label, ring in self.pieces:
            # a panel on the side (stripes, an overlay) in a colour A's parts do not show there: drawn at the same
            # place on the template's side, as B shows it
            u, _ = _centre(ring)
            if label in ("collar", "heel_counter") or c == tpl._zone(u, 0.3) or c == tpl._zone(u, 0.95):
                continue
            if label in ("vamp", "toe_cap") and u >= 0.5:
                continue
            tpl.marks.append((c, [self._onto(tpl, uu, h) for uu, h in ring]))
        tpl.base = tpl._most_seen() or self.base
        return tpl

    def _most_seen(self) -> str | None:
        """The colour the viewer sees most of: the shoe's own (its outline, the lining's tint)."""
        seen: dict[str, float] = {}
        for _, _, _, c, g, _ in self.cells():
            seen[c] = seen.get(c, 0.0) + g
        return max(seen, key=lambda c: (seen[c], c)) if seen else None

    def _from(self, u: float, h: float) -> float:
        """A height on the template (`self`, B) moved back to the same place on the traced side: as far up its upper
        (a share of its height there), or as far up its shaft (no higher than the traced collar)."""
        src = self.src
        ht = h - self.sole_t
        H, Ht = _interp(src.table, u), _interp(self.table, u)
        hm = ht / max(Ht, 0.1) * H if ht <= Ht else min(H + ht - Ht, max(H, src.rim) - RIM_CM)
        return _lerp(src.us, src.bottom, u) + _lerp(src.us, src.sole, u) + hm

    def _onto(self, tpl: _Traced, u: float, hp: float) -> tuple[float, float]:
        """A traced side point moved to the same place on the template's side: as far up its upper (a share of its
        height there), or as far up its shaft."""
        hm = hp - _lerp(self.us, self.bottom, u) - _lerp(self.us, self.sole, u)
        H, Ht = _interp(self.table, u), _interp(tpl.table, u)
        return u, tpl.sole_t + (hm / max(H, 0.1) * Ht if hm <= H else Ht + hm - H)

    def template_words(self) -> dict:
        """A's laces, eyelets and lace colour, from the trace."""
        out = {}
        # the colour of a row of laces counted (a shorter row is a collar's edge or a stripe's end: its colour is
        # not the laces'); else the tagger's, or the style's
        c = self.laces.color if self.laces is not None and self.laces.count >= LACES_MIN else None
        if c:
            out["lace_color"] = c
        if self.eyelets is not None and self.eyelets.count >= LACES_MIN:
            out["eyelets"] = self.eyelets.count
        if self.laced:
            out["laces"] = True
        return out

    def see_front(self, look: FrontLook | None) -> None:
        """B with a front photo: its toe box and vamp colours, laces and front marks take over from the side's (its
        outline stays the template's)."""
        if look is None:
            return
        self.front = look
        self._cells = None
        self.base = self._most_seen() or self.base

    def lift(self, u: float) -> float:
        """How far the traced sole's top stands above the solid's at u."""
        return _lerp(self.us, self.bottom, u) + _lerp(self.us, self.sole, u) - self.sole_t

    def warp(self, u: float, h: float) -> float:
        """The solid's height h at u moved onto the traced shoe: the sole stretched to its traced thickness and
        lifted by the toe spring, the upper standing on it."""
        b, s = _lerp(self.us, self.bottom, u), _lerp(self.us, self.sole, u)
        return b + h * s / self.sole_t if h <= self.sole_t else b + s + h - self.sole_t

    # ---- the solid's surface

    def on_shoe(self, hw, inset: float, u: float, hp: float, side: int) -> tuple[float, float, float, float]:
        """A traced side-view point (u, hp cm above the ground) on the solid's `side` (-1 outer, 1 inner): the point
        (x, u, h) for the view, and how much its surface faces the viewer (> 0: seen)."""
        u = min(1.0, max(0.0, u))
        hm = hp - _lerp(self.us, self.bottom, u) - _lerp(self.us, self.sole, u)   # cm above the traced sole
        H = _interp(self.table, u)
        if self.shaft and u < 0.5 and hm > H + 0.3:   # up a boot's shaft: round its cylinder
            su = min(1.0, max(-1.0, (u - SHAFT_AU) * LENGTH / SHAFT_RU))
            cu = math.sqrt(max(0.0, 1 - su * su))
            n = (side * cu / SHAFT_RX, su / SHAFT_RU, 0.0)
            g = n[0] * SEE[0] + n[1] * SEE[1]
            return (SHAFT_AX + side * SHAFT_RX * cu, SHAFT_AU + SHAFT_RU * su / LENGTH,
                    min(self.shaft, self.sole_t + hm), g / math.hypot(n[0], n[1]))
        sa = min(1.0, max(0.0, hm / max(H, 0.1)))
        a = math.asin(sa)
        ca = math.cos(a)
        w = hw(u) * inset
        x, h = side * w * ca, self.sole_t + H * sa
        # the surface's slope along the length and round the cross-section, then its outward normal
        du = 0.005
        u0, u1 = max(0.0, u - du), min(1.0, u + du)
        dw = (hw(u1) - hw(u0)) * inset / (u1 - u0)
        dH = (_interp(self.table, u1) - _interp(self.table, u0)) / (u1 - u0)
        dl = (self.lift(u1) - self.lift(u0)) / (u1 - u0)
        A = (side * dw * ca, LENGTH, dH * sa + dl)
        B = (-side * w * sa, 0.0, H * ca)
        n = (A[1] * B[2] - A[2] * B[1], A[2] * B[0] - A[0] * B[2], A[0] * B[1] - A[1] * B[0])
        if n[0] * side * ca + n[2] * sa < 0:
            n = (-n[0], -n[1], -n[2])
        size = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2) or 1.0
        return x, u, h, (n[0] * SEE[0] + n[1] * SEE[1] + n[2] * SEE[2]) / size

    def seen_part(self, hw, inset: float, ring, side: int) -> list[tuple[float, float, float]]:
        """The part of a traced outline that faces the viewer on `side`, as points on the solid. The outline is cut
        into short steps, then clipped where the surface turns away; where it is clipped, it runs along the line
        where the surface turns (found by halving)."""
        pts = []
        for (u0, h0), (u1, h1) in zip(ring, ring[1:] + ring[:1], strict=True):
            n = max(1, math.ceil(math.hypot((u1 - u0) * LENGTH, h1 - h0) / PAINT_STEP_CM))
            pts += [(u0 + (u1 - u0) * i / n, h0 + (h1 - h0) * i / n) for i in range(n)]
        g = [self.on_shoe(hw, inset, u, h, side)[3] for u, h in pts]
        if all(v <= 0 for v in g):
            return []
        out: list[tuple[float, float, bool]] = []   # (u, hp, on the turning line)
        for i, (p, q) in enumerate(zip(pts, pts[1:] + pts[:1], strict=True)):
            gp, gq = g[i], g[(i + 1) % len(pts)]
            if gp > 0:
                out.append((p[0], p[1], False))
            if (gp > 0) != (gq > 0):
                t = gp / (gp - gq)
                out.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t, True))
        if all(v > 0 for v in g):
            return [self.on_shoe(hw, inset, u, h, side)[:3] for u, h, _ in out]
        # where the outline leaves the seen part and comes back, follow the turning line between
        full = []
        for i, (u, h, edge) in enumerate(out):
            full.append((u, h))
            nu, nh, nedge = out[(i + 1) % len(out)]
            if edge and nedge:
                k = max(1, math.ceil(abs(nu - u) * LENGTH / PAINT_STEP_CM))
                for j in range(1, k):
                    uu = u + (nu - u) * j / k
                    hh = self._turn(hw, inset, uu, side, h + (nh - h) * j / k)
                    full.append((uu, hh))
        return [self.on_shoe(hw, inset, u, h, side)[:3] for u, h in full]

    def _turn(self, hw, inset: float, u: float, side: int, guess: float) -> float:
        """Where, going up the side at u, the surface turns to face the viewer (`guess` if it does not)."""
        lo = _lerp(self.us, self.bottom, u) + _lerp(self.us, self.sole, u)
        hi = lo + _interp(self.table, u)
        glo, ghi = self.on_shoe(hw, inset, u, lo, side)[3], self.on_shoe(hw, inset, u, hi, side)[3]
        if (glo > 0) == (ghi > 0):
            return guess
        for _ in range(18):
            m = (lo + hi) / 2
            if (self.on_shoe(hw, inset, u, m, side)[3] > 0) == (ghi > 0):
                hi = m
            else:
                lo = m
        return (lo + hi) / 2

    zones: dict | None = None      # A: the traced parts' colours, painted where the template has those parts
    pieces: list = field(default_factory=list)   # the traced panels: (colour, label, outline)
    mark_colours: list = field(default_factory=list)   # the colours of the marks that are only marks (small, standing out)
    back: _Raster | None = None    # where the collar's and heel counter's pieces are, side on
    front: FrontLook | None = None  # B: what a front photo showed
    src: _Traced | None = None      # B on the template: the traced shoe its colours are sampled from

    def shaft_colour(self, u: float, h: float) -> str | None:
        if self.src is not None:
            return self.src.side.at(u, self._from(u, h))
        if self.zones is not None:
            z = self.zones
            return z.get("collar", z["upper"]) if h >= self.shaft - 1.6 else z.get("quarter", z["upper"])
        return self.side.at(u, _lerp(self.us, self.bottom, u) + _lerp(self.us, self.sole, u) + h - self.sole_t)

    def _zone(self, u: float, sa: float) -> str:
        """A's colour at u, sa round the upper: each part's traced colour where the template has that part."""
        z = self.zones
        if u >= 0.82 and "toe_cap" in z:
            return z["toe_cap"]
        if u >= 0.5:
            return z.get("vamp", z["upper"])
        if u < 0.16 and "heel_counter" in z:
            return z["heel_counter"]
        if sa > 0.8 and "collar" in z and u < THROAT_U:   # the collar: behind the leg, not across the throat
            return z["collar"]
        return z.get("quarter", z["upper"])

    def colour_at(self, u: float, sa: float) -> str | None:
        if self.src is not None:
            return self.src.colour_at(u, sa)
        if self.zones is not None:
            return self._zone(u, sa)
        f = self.front
        if f is not None and sa > 0.35 and u >= 0.5:   # the front photo's colours, where it saw the shoe best
            c = f.toe if u >= 0.8 else f.vamp
            if c:
                return c
        return self._side_colour(u, sa)

    def _side_colour(self, u: float, sa: float) -> str | None:
        """The traced colour for the point on the upper at u, sa of the way up round its cross-section (sin of the
        angle; 1 at the crest): what the photo shows there, as high up the side as the point is round the shoe.
        The crest takes what is just under the top line, and the nose what is at NOSE_U: so a band low round the toe
        (a mudguard) stays low on the front."""
        u = min(u, NOSE_U)
        H = _interp(self.table, u)
        lo = _lerp(self.us, self.bottom, u) + _lerp(self.us, self.sole, u)
        hp = lo + sa * (H - min(RIM_CM, 0.3 * H))
        c = self.side.at(u, hp)
        if u > THROAT_U and self.back is not None and c is not None and self.back.at(u, hp) == c:
            # the collar's band along the top line, in front of the leg: seen from the front that is the throat
            # (the tongue and the lacing), not the collar, which stays behind the leg: the colour below the band
            while hp > lo and self.back.at(u, hp) == c:
                hp -= 0.2
            c = self.side.at(u, hp) or c
        return c

    def cells(self):
        """The upper's surface in small cells, each facing the viewer: (side, i, j, colour, facing, part), where
        part is "foot" (i along the length, j up the side) or "shaft" (i up the shaft, j round it). Cached."""
        if getattr(self, "_cells", None) is not None:
            return self._cells
        out = []
        hw, inset = self.hw, self.inset
        for side in (-1, 1):
            for i in range(GRID_U):
                u = (i + 0.5) / GRID_U
                for j in range(GRID_A):
                    a = math.pi / 2 * (j + 0.5) / GRID_A
                    g = self._facing(hw, inset, u, math.sin(a), side)
                    c = self.colour_at(u, math.sin(a)) if g > 0 else None
                    if c is not None:
                        out.append((side, i, j, c, g, "foot"))
            if self.shaft:
                for i in range(self._shaft_rows()):
                    h = self._shaft_h(i + 0.5)
                    for j in range(GRID_A):
                        su = math.sin(math.pi * ((j + 0.5) / GRID_A - 0.5))   # from the back (-1) to the front (1)
                        u = SHAFT_AU + SHAFT_RU * su / LENGTH
                        if h <= self.sole_t + _interp(self.table, u):
                            continue   # inside the foot's upper
                        cu = math.sqrt(max(0.0, 1 - su * su))
                        g = (side * cu / SHAFT_RX * SEE[0] + su / SHAFT_RU * SEE[1]) / (math.hypot(cu / SHAFT_RX, su / SHAFT_RU) or 1.0)
                        if g <= 0:
                            continue
                        c = self.shaft_colour(u, h)
                        if c is not None:
                            out.append((side, i, j, c, g, "shaft"))
        self._cells = _merge_small(out)
        return self._cells

    def _shaft_rows(self) -> int:
        return max(1, math.ceil((self.shaft - self.sole_t - 4.0) / SHAFT_STEP_CM))

    def _shaft_h(self, i: float) -> float:
        return self.sole_t + 4.0 + (self.shaft - self.sole_t - 4.0) * i / self._shaft_rows()

    def _facing(self, hw, inset: float, u: float, sa: float, side: int) -> float:
        H = _interp(self.table, u)
        return self.on_shoe(hw, inset, u, _lerp(self.us, self.bottom, u) + _lerp(self.us, self.sole, u) + sa * H, side)[3]

    def _corner(self, part: str, side: int, i: float, j: float) -> tuple[float, float, float]:
        """A cell corner on the solid: i, j counted in cells as `cells` does."""
        if part == "foot":
            u, a = min(1.0, i / GRID_U), math.pi / 2 * j / GRID_A
            return side * self.hw(u) * self.inset * math.cos(a), u, self.sole_t + _interp(self.table, u) * math.sin(a)
        su = math.sin(math.pi * (j / GRID_A - 0.5))
        return (SHAFT_AX + side * SHAFT_RX * math.sqrt(max(0.0, 1 - su * su)), SHAFT_AU + SHAFT_RU * su / LENGTH,
                self._shaft_h(i))

    def paint(self, view, line_c: str) -> list[str]:
        """The traced colours on the solid, cell by cell where it faces the viewer (runs of one colour joined into
        one outline), the back of the foot first, then a boot's shaft, then the front; then the marks, on both
        sides, each where it is seen."""
        runs: dict = {}
        for side, i, j, c, _, part in self.cells():
            runs.setdefault((part, side, i), []).append((j, c))
        groups = {"back": {}, "shaft": {}, "front": {}}
        for part, rows in (("foot", GRID_U), ("shaft", self._shaft_rows() if self.shaft else 0)):
            for side in (-1, 1):
                open_: dict = {}   # (j0, j1, colour) -> the first row of a block of identical runs
                for i in range(rows + 1):
                    here = set()
                    cells = sorted(runs.get((part, side, i), []))
                    k = 0
                    while k < len(cells):
                        j0, c = cells[k]
                        j1 = j0
                        while k + 1 < len(cells) and cells[k + 1][1] == c and cells[k + 1][0] == j1 + 1:
                            k += 1
                            j1 = cells[k][0]
                        here.add((j0, j1, c))
                        k += 1
                    for key in [key for key in open_ if key not in here]:
                        start = open_.pop(key)
                        j0, j1, c = key
                        ring = ([self._corner(part, side, start, j) for j in range(j0, j1 + 2)]
                                + [self._corner(part, side, r, j1 + 1) for r in range(start + 1, i + 1)]
                                + [self._corner(part, side, i, j) for j in range(j1 + 1, j0 - 1, -1)]
                                + [self._corner(part, side, r, j0) for r in range(i - 1, start, -1)])
                        where = "shaft" if part == "shaft" else "back" if start < 0.4 * GRID_U else "front"
                        groups[where].setdefault(c, []).append(_path([view(*q) for q in ring]))
                    for key in here:
                        open_.setdefault(key, i)
        out = []
        for where in ("back", "shaft", "front"):
            for c, ds in sorted(groups[where].items()):
                out.append(f'<path d="{" ".join(ds)}" fill="{c}" stroke="{c}" stroke-width=".6" stroke-linejoin="round"/>')
        hw, inset = self.hw, self.inset
        for colour, ring in self.marks:
            for side in (1, -1):
                seen = self.seen_part(hw, inset, [tuple(q) for q in ring], side)
                if len(seen) >= 3:
                    out.append(f'<path d="{_path([view(*q) for q in seen])}" fill="{colour}"/>')
        for colour, x, v, size in (self.front.marks if self.front is not None else []):
            # a mark the front photo saw on the toe or the vamp: an oval on the surface there
            u = 0.55 + 0.4 * min(1.0, max(0.0, float(v)))
            r = max(0.08, min(0.35, float(size) ** 0.5 * 0.6))
            ring = [(float(x) + r * math.cos(2 * math.pi * k / 16), u + r * 0.12 * math.sin(2 * math.pi * k / 16))
                    for k in range(16)]
            pts = [_surface(view, hw, inset, self.table, self.sole_t, uu, max(-0.95, min(0.95, xs)), 0.05)
                   for xs, uu in ring]
            out.append(f'<path d="{_path(pts)}" fill="{colour}"/>')
        return out

    def lacing(self, view, hw, inset: float, ln, lace_c: str = INK) -> list[str]:
        """The laces as traced: as many crossings as were counted, in their colour, spread over the stretch of the
        instep they were found along; the eyelets beside them. Eyelets with no laces found (laces the upper's
        colour do not stand out in the photo): one crossing for each pair, in `lace_c`."""
        table, sole_t = self.table, self.sole_t
        s = lambda u, xs, lift=0.0: _surface(view, hw, inset, table, sole_t, u, xs, lift)   # noqa: E731
        across = lambda u, w, lift=0.15: [s(u, k / 6 * w, lift) for k in range(-6, 7)]       # noqa: E731
        row = self.laces if self.laces is not None and self.laces.count >= LACES_MIN else self.eyelets
        lo, hi = min(q[0] for q in row.points), max(q[0] for q in row.points)
        # on the vamp: in front of the opening (a row further back floated over the ankle) and behind the toe box
        lo = max(LACE_FROM, min(lo, LACE_TO - 0.08))
        hi = min(LACE_TO, max(hi, lo + 0.08))
        out = []
        for xs in (-0.42, 0.42):
            out.append(ln(_path([s(u, xs, 0.05) for u in (lo - 0.03, (lo + hi) / 2, hi)], close=False), 1.2))
        if self.eyelets:
            ec = self.eyelets.color
            n = max(2, min(9, self.eyelets.count))
            for i in range(n):
                u = lo - 0.02 + (hi - lo + 0.02) * i / (n - 1)
                for xs in (-0.46, 0.46):
                    x, y = s(u, xs, 0.1)
                    out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{0.32 * view.px:.1f}" fill="{ec}" stroke="{INK}" stroke-width=".5"/>')
        if self.laces or self.eyelets:
            lace = self.laces.color if self.laces else lace_c
            # too few laces counted (hidden in the photo's shade, or the upper's colour): one crossing between each
            # two eyelets seen along the side
            n = self.laces.count if self.laces and self.laces.count >= LACES_MIN else (self.eyelets.count - 1 if self.eyelets else 3)
            if self.front is not None and self.front.laces >= LACES_MIN:   # the front photo saw the lacing head on
                n, lace = self.front.laces, self.front.lace_color or lace
            n = max(1, min(7, n))
            wide = 0.5 if self.style in TRAINERS else 0.42
            for i in range(n):
                u = lo + (hi - lo) * (i + 0.5) / n if n > 1 else (lo + hi) / 2
                d = _path(across(u, wide, 0.25), close=False)
                out.append(ln(d, 2.8, INK, 0.9) + ln(d, 1.5, lace, 1))
            if self.shaft:   # a boot laces on up its shaft
                for i in range(3):
                    h = sole_t + 8.5 + i * (self.shaft - sole_t - 10) / 2
                    d = _path([view(1.8 * k / 3, SHAFT_AU + SHAFT_RU / LENGTH, h) for k in range(-3, 4)], close=False)
                    out.append(ln(d, 2.8, INK, 0.9) + ln(d, 1.5, lace, 1))
        return out
