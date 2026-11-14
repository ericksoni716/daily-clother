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
  in the shoe's opening, where the ankle would show.

One of each is drawn (the first given)."""
from __future__ import annotations

import logging
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


@dataclass
class Worn:
    """What `dress` drew, each to go in at its own point of the figure's drawing: `legs` over the wearer's legs and
    under the trousers and shoes; `ankle` the markup the shoes draw in their opening, in place of skin (None: skin);
    `tie` over the innermost top and under the next; `over` over everything but a scarf, a hat or a bag."""
    legs: str = ""
    ankle: str | None = None
    tie: str = ""
    over: str = ""
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
    return out


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
    k = K_PX * fig.HEAD_CM / 23.5
    cy = fig.CHIN_Y - 11.75 * k
    out.over += _placed(spec, uid, CX, cy - 0.3 * k, out, px=3.0 * k / LENS_GAP)


def _socks(fig, layout, spec: Spec, uid: str, out: Worn) -> None:
    shoes, bottom, body = layout.get("shoes"), layout.get("bottom"), layout.body
    style = spec.params.get("style", "casual_crew")
    if (shoes is None or bottom is None or shoes.front is None or not shoes.front.ankle or shoes.front.foot
            or fig._legs(layout)[2] or SOCK_LENGTH.get(style, 17.0) <= 0 or not body.legs):
        return
    ankle_y = shoes.point(shoes.front.anchors["ankle"])[1]
    top = ankle_y - (SOCK_LENGTH.get(style, 17.0) - SOCK_ANKLE_CM) * K_PX
    colour = spec.fill.color if spec.fill is not None else "#555555"
    second = spec.block_color or shade(colour, 0.3 if _dark(colour) else -0.3)
    pattern = spec.params.get("pattern", "solid")
    legs = body.legs
    out.defs.append(f'<clipPath id="{uid}y"><rect x="-4000" y="{top:.1f}" width="8000" height="4000"/></clipPath>')
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
    inside += (f'<path d="M -4000,{rib:.1f} H 4000" stroke="{shade(colour, -0.18)}" stroke-width="1.6"/>'
               f'<path d="M -4000,{top:.1f} H 4000" stroke="{INK}" stroke-width="{line * 0.6:.1f}"/>')
    out.legs = (f'<g clip-path="url(#{uid}y)">'
                + "".join(f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="{line}" stroke-linejoin="round"/>' for d in legs)
                + "".join(f'<path d="{d}" fill="{colour}"/>' for d in legs)
                + f'<g clip-path="url(#{uid}l)">{inside}</g></g>')
    out.ankle = (f'<path d="{{d}}" fill="none" stroke="{INK}" stroke-width="{line}" stroke-linejoin="round"/>'
                 f'<path d="{{d}}" fill="{colour}"/>')


def _dark(hex_: str) -> bool:
    h = hex_.lstrip("#")
    if len(h) != 6:
        return True
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.299 * r + 0.587 * g + 0.114 * b < 128
