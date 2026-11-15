"""The small accessories as worn on the figure: a tie under the collar, a pocket square in a tailored jacket's
breast pocket, a watch on the wrist, glasses on the face, and socks above low shoes when the trousers stop short
of them.

`figure` calls `dress` once, after it has placed everything, and puts what comes back where each belongs in its
drawing order (see `Worn`). The figure's own geometry (the wearer, the pieces it placed) is read, never changed:
if anything here fails, the outfit is drawn without the accessory.

- A tie is worn on a closed innermost top that has a collar: its knot just under the collar's points, its
  blade down to just above the belt. The collar is drawn again over the knot, so the knot sits under it.
- A pocket square stands in the breast pocket of the outermost top when that is tailored (its template marks the
  pocket with the anchor "breast"); worn open, it turns with the front it is on.
- A watch is on the wrist of the viewer's right arm, just above the hand, under any sleeve that reaches it.
- Glasses are on the eyes.
- Socks show above low shoes (not sandals, and not no-show socks) when the trousers stop short of the shoes:
  with shorts, or cropped trousers. The sock's top is SOCK_LENGTH above the ground; its colour is also drawn
  in the shoe's opening, where the ankle would show. Over a shoe Claude drew (`figure`'s drawn shoes), the sock is
  drawn under full-length trousers too: they keep their own length, so above a low shoe it shows below the hem.

One of each is drawn (the first given).

Each is drawn as the thing it is, in the round, seen from in front: a tie lies on the shirt under the collar,
which wraps the neck over its knot; a watch's strap wraps the wrist (its edges bowed); glasses' temples run out
to the sides of the head, where they go back over the ears; a sock is a tube round the ankle (its top bowed),
down inside the shoe.

`place` puts a hat or a bag (which `figure` places with the belt and the scarf) on him:
- A hat sits on the head: its band at HAT_BAND (a height on the head, by kind), its crown over the top of the
  head and the hair, its brim or peak above the eyes. It is drawn in its `worn` form, as seen at eye level.
- A bag is carried as that kind is: a briefcase, a duffel or a dopp kit in the viewer's right hand, turned a
  little away (HELD), the hand drawn again over its handle; a tote's handles over the shoulder, the bag at
  his side; a messenger's strap across the chest from the other shoulder, the bag at the hip; a sling across the
  chest; a belt bag round the waist; a backpack on his back, only its shoulder straps showing in front. Straps
  run up to the top of the shoulder they go over, as drawn (the outermost top's, else his own). `dress` draws
  it (`Worn.carry`)."""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field, replace

from .accessories import LENS_GAP, SOCK_LENGTH, SOCK_RIB
from .illustrate import INK, Spec, _draw, shade
from .templates import CX, K_PX, build

log = logging.getLogger(__name__)

SMALL = ("tie", "pocket_square", "watch", "eyewear", "socks")
KNOT_UNDER_CM = 0.6     # the tie's knot starts this far above the bottom of the collar's neck opening
TIE_ABOVE_BELT_CM = 2.2   # ...and its blade ends this far above the middle of the belt
WATCH_UP_CM = 1.2       # the middle of the watch, above the wrist
WATCH_EASE_CM = 0.3     # the strap, either side of the wrist, is this much wider than it
SOCK_ANKLE_CM = 9.0     # the shoe's opening, where the leg drawn above it ends, is this high off the ground on him
STRIPE_CM = (1.0, 1.4)  # a striped sock's stripes: how deep, and how far apart
DOT_CM = 2.2            # a dotted sock's repeat
ARGYLE_CM = 3.2         # ...and an argyle one's: a diamond about half the sock's width
SOCK_BOW_CM = 1.0       # a sock's top, a ring round the leg seen from above: how far it bows down in the middle
HEAD_SIDE_CM = 8.0      # the side of the head at the eyes, from its middle (the head's cm): where glasses' temples go back
# where a hat's band sits on the head, by template and style: cm from the middle of the head (up is less), the
# eyes at -0.3, the brows at -2.8, the top of the skull at -11.75 and of the hair at -13.7
HAT_BAND = {"cap": {"": -5.6},
            "beanie": {"cuffed": -3.6, "fisherman": -6.4, "trapper": -3.6, "beret": -6.0, "": -3.6},
            "brimmed_hat": {"fedora": -5.2, "trilby": -5.9, "panama": -5.2, "wide_brim": -5.2, "cowboy": -5.2,
                            "boater": -6.0, "bucket": -6.6, "flat_cap": -5.0, "newsboy": -5.0, "": -5.2}}
# a bag carried in the hand: where the hand holds it (template cm: its fingers come down over the bag's top), how far it is turned so that point is on top,
# and how much as wide it is drawn (carried at the side, its face is turned away from us; a dopp kit hangs by its
# end loop, its narrow side to us)
HELD = {"briefcase": ((0.0, 8.0), 0.0, 0.45), "duffel": ((0.0, 8.6), 0.0, 0.45), "pouch": ((16.6, 9.5), -90.0, 1.0)}
GRIP_CM = 10.5          # the hand closes round a handle this far down it (the hand's own cm, HAND)
STRAP_CM = 3.4          # a bag's shoulder strap, wide
TOTE_HANDLE_CM = 1.6    # ...and a tote's handles (as wide as where they are sewn on, seen turned away)
PACK_STRAP_CM = 5.6     # a backpack's shoulder straps, at the top
BELT_BAG = 0.85         # a belt bag, worn, is drawn this much as wide (it curves round the front of him)


@dataclass
class Worn:
    """What `dress` drew, each to go in at its own point of the figure's drawing: `legs` over the wearer's legs and
    under the trousers and shoes; `ankle` the markup the shoes draw in their opening, in place of skin (None: skin);
    `tie` over the innermost top and under the next; `over` over everything but a scarf, a hat or a bag; `carry`
    a bag as carried, over everything."""
    legs: str = ""
    ankle: str | None = None
    tie: str = ""
    over: str = ""
    carry: str = ""     # a bag as carried, over everything; when empty the figure draws the bag where it placed it
    defs: list[str] = field(default_factory=list)


def dress(layout, accessories, uid: str) -> Worn:
    """The small accessories among `accessories` worn on the figure `layout`. Never raises."""
    out = Worn()
    if layout is None or layout.body is None or not isinstance(accessories, (list, tuple)):
        return out
    from . import figure as fig  # the figure calls this module: import it only once both are loaded
    specs: dict[str, Spec] = {}
    for piece in accessories:
        if not isinstance(piece, fig.Piece) or piece.category != "other":
            continue
        try:
            spec = fig._spec(piece)
        except Exception:
            log.exception("drawing an accessory for an outfit failed")
            continue
        if spec.template in SMALL:
            specs.setdefault(spec.template, spec)
    for name, how in (("socks", _socks), ("tie", _tie), ("pocket_square", _square), ("watch", _watch),
                      ("eyewear", _glasses)):
        if name in specs:
            try:
                how(fig, layout, specs[name], f"{uid}x{name[0]}", out)
            except Exception:
                log.exception("wearing a %s in an outfit failed", name)
    bag = layout.get("bag")
    if bag is not None:
        try:
            out.carry = _carry(fig, layout, bag, f"{uid}xb", out)
        except Exception:
            log.exception("carrying a bag in an outfit failed")
    return out


def place(where: str, spec: Spec, layout):
    """A hat on his head or a bag carried (a `figure.Placed`), or None when there is no wearer to put it on (the
    figure then places it on its own)."""
    if layout is None or layout.body is None or where not in ("hat", "bag"):
        return None
    from . import figure as fig
    style = spec.params.get("style", "")
    if where == "hat":
        k = _head_k(fig)
        bands = HAT_BAND.get(spec.template, HAT_BAND["brimmed_hat"])
        y = fig.CHIN_Y - 11.75 * k + bands.get(style, bands[""]) * k
        spec = replace(spec, params={**spec.params, "worn": True, "px": k})
        return fig.Placed("hat", spec, build(spec.template, spec.params), [(1.0, 0.0, 0.0, 1.0, 0.0, y)], k)
    k = K_PX
    if style in HELD:
        spec = replace(spec, params={**spec.params, "px": k})
        shape = build(spec.template, spec.params)
        (u, v), turn, sx = HELD[style]
        gx, gy = _grip(fig)
        a = math.radians(turn)
        m = (sx * math.cos(a), math.sin(a), -sx * math.sin(a), math.cos(a))
        px, py = CX + u * k, v * k
        t = (*m, gx - (m[0] * px + m[2] * py), gy - (m[1] * px + m[3] * py))
        return fig.Placed("bag", spec, shape, [t], k)
    params = {**spec.params, "worn": True, "px": k}
    if style == "belt_bag":   # the strap round the waist, out to the sides of what he wears there
        spans = _spans(_outlines(fig, layout, ("bottom",) + tuple(fig.TOP_PLACES)), fig.BELT_Y)
        params["half"] = max([fig.BELT_HALF_CM + 0.6] + [max(CX - x0, x1 - CX) / k for x0, x1 in spans]) / BELT_BAG
    spec = replace(spec, params=params)
    shape = build(spec.template, params)
    x, y, sx = _carried_at(fig, style)
    return fig.Placed("bag", spec, shape, [(sx, 0.0, 0.0, 1.0, x - CX * sx, y)], k)


def _head_k(fig) -> float:
    """The head's own scale: px to its cm (it is drawn 23.5 cm from crown to chin, as HEAD_CM)."""
    return K_PX * fig.HEAD_CM / 23.5


def _grip(fig) -> tuple[float, float]:
    """Where the viewer's right hand closes round a handle: across its fingers, as the figure draws the hand."""
    w, d = fig._arm_at(-1, fig._arm_length(-1))
    h = fig._unit(d[0] * 0.6, d[1] * 0.6 + 0.4)
    kh = K_PX * fig.HAND_SCALE
    return 2 * CX - (w[0] + GRIP_CM * h[0] * kh), w[1] + GRIP_CM * h[1] * kh


def _carried_at(fig, style: str) -> tuple[float, float, float]:
    """Where a bag carried on the body has its anchor (x, y in the figure), and how much as wide it is drawn."""
    k = K_PX
    if style == "tote":   # at the front of his hip, under the shoulder it hangs from, turned a little away; its far side behind his arm
        return CX + 11.5 * k, fig._y(fig.WAIST_CM - 3.0) - 22.0 * k, 0.45
    if style == "messenger":   # at the hip, on the viewer's right, partly behind his arm
        return CX + 19.5 * k, fig._y(fig.WAIST_CM + 8.0) - 14.0 * k, 0.5
    if style == "sling":   # on the chest, on the strap
        return CX + 1.0 * k, fig._y(fig.CHEST_CM - 2.0) - 20.0 * k, 0.9
    if style == "belt_bag":   # round the waist, the bag in front
        return CX, fig.BELT_Y - 0.5 * k, BELT_BAG
    return CX, fig._y(fig.CHEST_CM), 1.0   # a backpack: behind him


def _outlines(fig, layout, places) -> list[str]:
    """The outlines of the pieces at `places`, as paths in the figure."""
    from . import fitting
    return ["M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in (p.point(q) for q in fitting.points(p.shape.outline))) + " Z"
            for p in layout.pieces if p.place in places]


def _surface(fig, layout, x: float) -> float:
    """The top of what he wears (else of him) at `x`: where a strap over the shoulder there goes behind."""
    from . import fitting
    polys = [fitting.points(d) for d in _outlines(fig, layout, fig.TOP_PLACES) + [layout.body.torso]]
    ys = []
    for poly in polys:
        for (xa, ya), (xb, yb) in zip(poly, poly[1:] + poly[:1], strict=True):
            if (xa <= x) != (xb <= x):
                ys.append(ya + (x - xa) * (yb - ya) / (xb - xa))
    if not ys:
        raise ValueError("nothing at the shoulder")
    return min(ys)


def _band(a, b, wa: float, wb: float) -> list[tuple[float, float]]:
    """A strap from point a (wa wide) to point b (wb wide), as four corners."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / n, dx / n
    return [(a[0] + nx * wa / 2, a[1] + ny * wa / 2), (b[0] + nx * wb / 2, b[1] + ny * wb / 2),
            (b[0] - nx * wb / 2, b[1] - ny * wb / 2), (a[0] - nx * wa / 2, a[1] - ny * wa / 2)]


def _ribbon(run, widths, colour: str) -> str:
    """A strap along the points `run`, `widths` wide at each, its sides smoothed through them."""
    left, right = [], []
    for i, (x, y) in enumerate(run):
        a, b = run[max(i - 1, 0)], run[min(i + 1, len(run) - 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        n = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / n * widths[i] / 2, dx / n * widths[i] / 2
        left.append((x + nx, y + ny))
        right.append((x - nx, y - ny))

    def smooth(pts):
        d = ""
        for (xa, ya), (xb, yb) in zip(pts, pts[1:], strict=False):
            d += f" Q {xa:.1f},{ya:.1f} {(xa + xb) / 2:.1f},{(ya + yb) / 2:.1f}"
        return d + f" L {pts[-1][0]:.1f},{pts[-1][1]:.1f}"

    right = right[::-1]
    path = (f"M {left[0][0]:.1f},{left[0][1]:.1f}" + smooth(left) + f" L {right[0][0]:.1f},{right[0][1]:.1f}"
            + smooth(right) + " Z")
    return f'<path d="{path}" fill="{shade(colour, -0.1)}" stroke="{INK}" stroke-width="2.6" stroke-linejoin="round"/>'


def _strap_markup(pts, colour: str, curve: tuple[float, float] | None = None) -> str:
    """A strap's corners (from `_band`) drawn as a band, its long sides bent by `curve` (px, across) if given."""
    a, b, c, d = pts
    if curve:
        def mid(p, q):
            return ((p[0] + q[0]) / 2 + curve[0], (p[1] + q[1]) / 2 + curve[1])
        m1, m2 = mid(a, b), mid(c, d)
        path = (f"M {a[0]:.1f},{a[1]:.1f} Q {m1[0]:.1f},{m1[1]:.1f} {b[0]:.1f},{b[1]:.1f} L {c[0]:.1f},{c[1]:.1f} "
                f"Q {m2[0]:.1f},{m2[1]:.1f} {d[0]:.1f},{d[1]:.1f} Z")
    else:
        path = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts) + " Z"
    return (f'<path d="{path}" fill="{shade(colour, -0.1)}" stroke="{INK}" stroke-width="2.6" stroke-linejoin="round"/>')


def _behind_arms(fig, layout, markup: str, uid: str, out: Worn, body: bool = False, below: float | None = None) -> str:
    """`markup` with nothing drawn over his arms or any sleeve: a strap there goes round behind the arm. body: and
    nothing off him either (a strap goes over the shoulder, or round his side, out of sight). below: only below this
    height (above it, a strap lies on top of his shoulder)."""
    from . import fitting

    def black(ds):
        return "".join(f'<path d="{d}" fill="#000" stroke="#000" stroke-width="{2 * fig.LINE}" stroke-linejoin="round"/>'
                       for d in ds)

    sleeves = ["M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in (p.point(q) for q in fitting.points(d))) + " Z"
               for p in layout.pieces if p.place in fig.TOP_PLACES for d, _ in p.shape.sleeves]
    tops = _outlines(fig, layout, fig.TOP_PLACES)
    # his arms, but not where what he wears on top covers them (the arm runs up inside it); then his sleeves and hands
    hide = (black(layout.body.arms) + "".join(f'<path d="{d}" fill="#fff"/>' for d in tops)
            + black(sleeves) + black(layout.body.hands))
    if below is not None:
        hide += f'<rect x="-4000" y="-4000" width="8000" height="{below + 4000:.1f}" fill="#fff"/>'
    out.defs.append(f'<mask id="{uid}a" maskUnits="userSpaceOnUse" x="-4000" y="-4000" width="8000" height="8000">'
                    f'<rect x="-4000" y="-4000" width="8000" height="8000" fill="#fff"/>{hide}</mask>')
    if body:
        on = "".join(f'<path d="{d}"/>' for d in _outlines(fig, layout, fig.TOP_PLACES) + [layout.body.torso])
        out.defs.append(f'<clipPath id="{uid}b">{on}</clipPath>')
        markup = f'<g clip-path="url(#{uid}b)">{markup}</g>'
    return f'<g mask="url(#{uid}a)">{markup}</g>'


def _on_him(fig, layout, markup: str, y: float, uid: str, out: Worn) -> str:
    """`markup` cut off where it goes over his shoulder, out of sight: only on him, or below `y` (where the bag is)."""
    out.defs.append(f'<clipPath id="{uid}t">' + "".join(f'<path d="{d}"/>' for d in _outlines(fig, layout, fig.TOP_PLACES)
                    + [layout.body.torso]) + f'<rect x="-4000" y="{y:.1f}" width="8000" height="4000"/></clipPath>')
    return f'<g clip-path="url(#{uid}t)">{markup}</g>'


def _carry(fig, layout, bag, uid: str, out: Worn) -> str:
    """The bag `place` put on him, with what holds it there: straps up over the shoulder (each going on over it, out
    of sight, and round behind his arms), or the hand round its handle."""
    style = bag.spec.params.get("style", "tote")
    k = K_PX
    colour = bag.spec.fill.color if bag.spec.fill is not None else "#555555"
    d, b, _, _ = _draw(bag.spec, "line", uid, dy=0.0, shape=bag.shape)
    out.defs.append(d)
    drawn = f'<g transform="matrix({",".join(f"{v:.4f}" for v in bag.transforms[0])})">{b}</g>'

    def over_shoulder(x):   # a little past the top of him at x: the strap is cut off there, going on over
        return (x, _surface(fig, layout, x) - 2.0 * k)

    if style in HELD:   # in the hand: the hand again, over the handle
        wearer = layout.body
        y = _grip(fig)[1] - 3.0 * k   # from just above where it closes: the wrist's edge stays under the sleeve
        out.defs.append(f'<clipPath id="{uid}h"><rect x="-4000" y="{y:.1f}" width="8000" height="4000"/></clipPath>')
        hand = fig._skin([wearer.hands[1]]) + fig._lines(wearer.fingers[len(wearer.fingers) // 2:])
        return drawn + f'<g clip-path="url(#{uid}h)">{hand}</g>'
    if style == "tote":   # both handles up over the shoulder, down his chest to the bag at his side; his arm in front of it
        straps = ""
        for u, top in ((-8.0, 12.5), (8.0, 15.0)):   # close together on the shoulder, apart where they are sewn on
            foot = bag.point((CX + u * k, 23.0 * k))
            straps += _strap_markup(_band(foot, over_shoulder(CX + top * k), TOTE_HANDLE_CM * k, TOTE_HANDLE_CM * k), colour)
        armpit = fig._y(fig.CHEST_CM)
        return _behind_arms(fig, layout, _on_him(fig, layout, straps, armpit, uid, out) + drawn, uid, out, below=armpit)
    if style == "messenger":   # across the chest from the other shoulder down to the side of the bag
        foot = bag.point((CX - 15.0 * k, 20.0 * k))
        strap = _strap_markup(_band(foot, over_shoulder(CX - 14.0 * k), STRAP_CM * k, STRAP_CM * k), colour)
        strap = _on_him(fig, layout, strap, bag.point((CX, 14.0 * k))[1], uid, out)
        return _behind_arms(fig, layout, strap + drawn, uid, out, below=fig._y(fig.CHEST_CM))
    if style == "sling":   # over the viewer's right shoulder, across the chest, round under the other arm
        top, end = over_shoulder(CX + 13.0 * k), (CX - (fig.CHEST_HALF_CM + 6.0) * k, fig._y(fig.WAIST_CM - 2.0))
        strap = _strap_markup(_band(end, top, STRAP_CM * k * 0.8, STRAP_CM * k * 0.8), colour)
        return _behind_arms(fig, layout, strap, uid, out, body=True) + drawn
    if style == "belt_bag":   # its strap round his sides, behind his arms
        return _behind_arms(fig, layout, drawn, uid, out)
    # a backpack: on his back; in front, its straps come over the shoulders and go back under the arms
    straps, chest = "", ""
    w = PACK_STRAP_CM * k
    if style in ("backpack", "rucksack"):   # a strap across the chest, between them, its ends under them: a hand
        y = fig._y(fig.CHEST_CM - 2.0)       # below the collarbones, under a scarf's hanging ends
        x0, x1 = CX - 14.4 * k, CX + 14.4 * k
        chest = (f'<rect x="{x0:.1f}" y="{y - 1.1 * k:.1f}" width="{x1 - x0:.1f}" height="{2.2 * k:.1f}" '
                 f'fill="{shade(colour, -0.25)}" stroke="{INK}" stroke-width="2"/>'
                 f'<rect x="{CX - 1.6 * k:.1f}" y="{y - 1.2 * k:.1f}" width="{3.2 * k:.1f}" height="{2.4 * k:.1f}" '
                 f'rx="{0.4 * k:.1f}" fill="#2a2b2e" stroke="{INK}" stroke-width="1.6"/>')
    for s in (-1, 1):   # down the chest, then out to the side and round behind the arm, nearly level as it goes
        run = [over_shoulder(CX + s * 12.4 * k), (CX + s * 12.8 * k, fig._y(fig.CHEST_CM - 8.0)),
               (CX + s * 14.0 * k, fig._y(fig.CHEST_CM - 3.0)), (CX + s * 17.0 * k, fig._y(fig.CHEST_CM + 0.5)),
               (CX + s * 24.0 * k, fig._y(fig.CHEST_CM + 2.5))]
        straps += _ribbon(run, [w * 0.9, w * 0.9, w * 0.85, w * 0.8, w * 0.8], colour)
    return _behind_arms(fig, layout, chest + straps, uid, out, body=True)


def _placed(spec: Spec, uid: str, x: float, y: float, out: Worn, clip: str = "", **params) -> str:
    """The accessory drawn with its anchor at (x, y), at the figure's scale."""
    spec = replace(spec, params={**spec.params, **params, "px": params.get("px", K_PX)}, weight="lightweight")
    d, b, _, _ = _draw(spec, "line", uid, dy=0.0, shape=build(spec.template, spec.params))
    out.defs.append(d)
    g = f'<g transform="translate({x - CX:.1f},{y:.1f})">{b}</g>'
    return f'<g clip-path="url(#{clip})">{g}</g>' if clip else g


def _tie(fig, layout, spec: Spec, uid: str, out: Worn) -> None:
    if spec.params.get("style") == "bow_tie":
        top = _first_top(fig, layout)
        if top is None or top.open or not _collar(top):
            return
        hole = _hole_bottom(top)
        out.tie = _placed(spec, uid, CX, hole - 0.4 * K_PX, out, px=K_PX * 0.8) + _collar_again(top, f"{uid}c", out)
        return
    top = _first_top(fig, layout)
    if top is None or top.open or not _collar(top):
        return
    knot = _hole_bottom(top) - KNOT_UNDER_CM * K_PX
    length = (fig.BELT_Y - TIE_ABOVE_BELT_CM * K_PX - knot) / K_PX
    if length < 10:
        return
    out.tie = _placed(spec, uid, CX, knot, out, worn=True, length=length) + _collar_again(top, f"{uid}c", out)


def _first_top(fig, layout):
    return next((p for p in layout.pieces if p.place in fig.TOP_PLACES), None)


def _collar(top) -> list[str]:
    return [p.d for p in top.shape.parts if p.role in ("collar_r", "collar_l")]


def _hole_bottom(top) -> float:
    from . import fitting
    ys = [y for p in top.shape.parts if p.role == "hole" for _, y in fitting.points(p.d)]
    if not ys:
        raise ValueError("the top has no neck opening")
    return top.point((CX, max(ys)))[1]


def _collar_again(top, uid: str, out: Worn) -> str:
    """The innermost top drawn again, only where its collar is, so the collar lies over the tie's knot."""
    d, b, _, _ = _draw(top.spec, "line", uid, layered=True, dy=0.0, shape=top.shape)
    if not isinstance(b, str):
        return ""
    t = top.transforms[0]
    out.defs.append(d)
    out.defs.append(f'<clipPath id="{uid}k">' + "".join(
        f'<path d="{c}" transform="matrix({",".join(f"{v:.4f}" for v in t)})"/>' for c in _collar(top)) + "</clipPath>")
    return f'<g clip-path="url(#{uid}k)">{b}</g>'


def _square(fig, layout, spec: Spec, uid: str, out: Worn) -> None:
    tops = [p for p in layout.pieces if p.place in fig.TOP_PLACES]
    if not tops or "breast" not in tops[-1].shape.anchors:
        return
    top = tops[-1]
    x, y = top.point(top.shape.anchors["breast"])
    turn = 1.0
    if top.open and top.shape.fronts:   # the front swings open about its side, as illustrate draws it
        x0, _, x1, _ = top.shape.body_box
        half = (x1 - x0) / 2
        past = max(0.0, CX - min(px for px, _ in top.shape.fronts[0]))
        turn = max(0.5, 0.79 * half / (half + past))
        hinge = CX + half if x > CX else CX - half
        if abs(x - CX) < half:
            x = hinge + (x - hinge) * turn
    spec = replace(spec, params={**spec.params, "worn": True, "px": K_PX}, weight="lightweight")
    d, b, _, _ = _draw(spec, "line", uid, dy=0.0, shape=build(spec.template, spec.params))
    out.defs.append(d)
    # only what stands out of the pocket: the welt's edge crosses the square's foot
    out.defs.append(f'<clipPath id="{uid}k"><rect x="-4000" y="-4000" width="8000" height="{4000 + y + 1:.1f}"/></clipPath>')
    out.over += (f'<g clip-path="url(#{uid}k)"><g transform="matrix({turn:.4f},0,0,1,{x - CX * turn:.1f},{y:.1f})">'
                 f'{b}</g></g>')


def _watch(fig, layout, spec: Spec, uid: str, out: Worn) -> None:
    from . import fitting
    wx, wy = fig._arm_points(+1)[2]
    half = fig._arm_half(fig._arm_length(+1)) / K_PX + WATCH_EASE_CM
    y = wy - WATCH_UP_CM * K_PX
    # a sleeve over the wrist hides it; one that ends on the watch hides the top of it
    cuff = -1e9
    for p in layout.pieces:
        if p.place not in fig.TOP_PLACES:
            continue
        for d, _ in p.shape.sleeves:
            pts = [p.point(q) for q in fitting.points(d)]
            if pts and min(px for px, _ in pts) <= wx <= max(px for px, _ in pts):
                cuff = max(cuff, max(py for _, py in pts))
    if cuff > y - 0.5 * K_PX:   # down over the watch's middle: it is hidden
        return
    clip = ""
    if cuff > y - 3.0 * K_PX:
        clip = f"{uid}k"
        out.defs.append(f'<clipPath id="{clip}"><rect x="-4000" y="{cuff:.1f}" width="8000" height="4000"/></clipPath>')
    out.over += _placed(spec, uid, wx, y, out, clip, worn=True, half=half)


def _glasses(fig, layout, spec: Spec, uid: str, out: Worn) -> None:
    k = _head_k(fig)
    cy = fig.CHIN_Y - 11.75 * k
    out.over += _placed(spec, uid, CX, cy - 0.3 * k, out, px=3.0 * k / LENS_GAP, reach=HEAD_SIDE_CM * LENS_GAP / 3.0)


def _socks(fig, layout, spec: Spec, uid: str, out: Worn) -> None:
    shoes, bottom, body = layout.get("shoes"), layout.get("bottom"), layout.body
    style = spec.params.get("style", "casual_crew")
    covered = fig._legs(layout)[2] and getattr(shoes, "drawn", None) is None   # full-length trousers over a front view
    if (shoes is None or bottom is None or shoes.front is None or not shoes.front.ankle or shoes.front.foot
            or covered or SOCK_LENGTH.get(style, 17.0) <= 0 or not body.legs):
        return
    ankle_y = shoes.point(shoes.front.anchors["ankle"])[1]
    top = ankle_y - (SOCK_LENGTH.get(style, 17.0) - SOCK_ANKLE_CM) * K_PX
    colour = spec.fill.color if spec.fill is not None else "#555555"
    second = spec.block_color or shade(colour, 0.3 if _dark(colour) else -0.3)
    pattern = spec.params.get("pattern", "solid")
    legs = body.legs
    spans = _spans(legs, top)
    out.defs.append(f'<clipPath id="{uid}y"><path d="{_bowed(spans, top)} V 4000 H -4000 Z"/></clipPath>')
    out.defs.append(f'<clipPath id="{uid}l">' + "".join(f'<path d="{d}"/>' for d in legs) + "</clipPath>")
    line = 2 * fig.LINE
    inside = ""
    if pattern == "stripes":
        depth, gap = (c * K_PX for c in STRIPE_CM)
        y = top + SOCK_RIB.get(style, 2.4) * K_PX + gap * 0.4
        while y < ankle_y + 4 * K_PX:
            inside += f'<rect x="-4000" y="{y:.1f}" width="8000" height="{depth:.1f}" fill="{second}"/>'
            y += gap + depth
    elif pattern in ("dots", "argyle"):
        s = (DOT_CM if pattern == "dots" else ARGYLE_CM) * K_PX
        mark = (f'<circle cx="{s / 2:.1f}" cy="{s / 2:.1f}" r="{s * 0.16:.1f}" fill="{second}"/>' if pattern == "dots" else
                f'<path d="M {s / 2:.1f},0 L {s:.1f},{s / 2:.1f} L {s / 2:.1f},{s:.1f} L 0,{s / 2:.1f} Z" fill="{second}"/>')
        out.defs.append(f'<pattern id="{uid}p" patternUnits="userSpaceOnUse" width="{s:.1f}" height="{s:.1f}" '
                        f'x="{CX:.1f}" y="{top:.1f}">{mark}</pattern>')
        inside += f'<rect x="-4000" y="{top + SOCK_RIB.get(style, 2.4) * K_PX:.1f}" width="8000" height="4000" fill="url(#{uid}p)"/>'
    rib = top + SOCK_RIB.get(style, 2.4) * K_PX
    inside += (f'<path d="{_bowed(spans, rib)}" fill="none" stroke="{shade(colour, -0.18)}" stroke-width="1.6"/>'
               f'<path d="{_bowed(spans, top)}" fill="none" stroke="{INK}" stroke-width="{line * 0.6:.1f}"/>')
    out.legs = (f'<g clip-path="url(#{uid}y)">'
                + "".join(f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="{line}" stroke-linejoin="round"/>' for d in legs)
                + "".join(f'<path d="{d}" fill="{colour}"/>' for d in legs)
                + f'<g clip-path="url(#{uid}l)">{inside}</g></g>')
    out.ankle = (f'<path d="{{d}}" fill="none" stroke="{INK}" stroke-width="{line}" stroke-linejoin="round"/>'
                 f'<path d="{{d}}" fill="{colour}"/>')
    if pattern in ("stripes", "dots", "argyle"):
        # The shoe redraws the ankle in its own coordinates. Keep the sock's pattern
        # there too; a solid patch would leave only a row of diamond tips below a hem.
        tx, ty = shoes.transforms[0][-2:]
        out.ankle += (f'<clipPath id="{uid}a"><path d="{{d}}"/></clipPath>'
                     f'<g clip-path="url(#{uid}a)"><g transform="translate({-tx:.4f} {-ty:.4f})">'
                     f'{inside}</g></g>')
    # A tall boot can meet bare calf above a short sock: keep the sock's real top in this redraw too.
    tx, ty = shoes.transforms[0][-2:]
    out.ankle = (fig._ankle() + f'<g transform="translate({-tx:.4f} {-ty:.4f})"><g clip-path="url(#{uid}y)">'
                 f'<g transform="translate({tx:.4f} {ty:.4f})">{out.ankle}</g></g></g>')


def _spans(paths: list[str], y: float) -> list[tuple[float, float]]:
    """Across each of `paths` at height y: (left, right), from the viewer's left."""
    from . import fitting
    out = []
    for d in paths:
        poly = fitting.points(d)
        xs = [xa + (y - ya) * (xb - xa) / (yb - ya) for (xa, ya), (xb, yb) in zip(poly, poly[1:] + poly[:1], strict=True)
              if (ya > y) != (yb > y)]
        if xs:
            out.append((min(xs), max(xs)))
    return sorted(out)


def _bowed(spans: list[tuple[float, float]], y: float) -> str:
    """A line across at height y, bowed down by SOCK_BOW_CM in the middle of each span: a ring round each leg."""
    d = f"M -4000,{y:.1f}"
    for x0, x1 in spans:
        d += f" L {x0:.1f},{y:.1f} Q {(x0 + x1) / 2:.1f},{y + 2 * SOCK_BOW_CM * K_PX:.1f} {x1:.1f},{y:.1f}"
    return d + f" L 4000,{y:.1f}"


def _dark(hex_: str) -> bool:
    h = hex_.lstrip("#")
    if len(h) != 6:
        return True
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.299 * r + 0.587 * g + 0.114 * b < 128
