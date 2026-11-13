"""An outfit on an invisible wearer, using the unchanged single-item templates.

Descriptions are tagger answers (including partial/coarse answers), with an
optional ``color_hex``. The caller reconciles the owner's corrections first.
All coordinates are in the tops' 3.3 px/cm frame; no garment is fitted to a card.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass

from ..tagger.schema import ItemTags, drawing_for
from . import item
from .illustrate import Fill, Spec, _draw
from .templates import CX, K_PX, PX_CM, SHOE_G, SHOE_L, SHOE_X0, Shape, build

PLACES = ("base", "mid", "outer", "bottom", "shoes")
OPEN_FRONTS = ("buttons", "french", "hidden", "double", "zip")
SLEEVE_LENGTHS = {"none": 0, "short": 1, "elbow": 2, "three-quarter": 3, "long": 4}
WAIST_Y = 58 + 45 * K_PX
# The trouser block has a 27 cm rise and an 81 cm (32 inch) inside leg.
# Keep that wearer even in shorts; the last 7 cm is the foot below the hem.
GROUND_Y = WAIST_Y + (27 + 81 + 7) * K_PX
SHOE_CM = 29
SHOE_SCALE = SHOE_CM * K_PX / SHOE_L
LEG_CENTRE = 12.5 * K_PX
MARGIN = 18


@dataclass
class _Piece:
    place: str
    shape: Shape
    defs: str
    body: str | tuple[str, str]
    opening: list[str] | None
    sleeve: str


def _piece(raw, place: str) -> _Piece | None:
    """Keep known details, then try the plain category if they cannot be drawn."""
    category, color = None, item.DEFAULT_HEX
    try:
        if isinstance(raw, ItemTags):
            raw = raw.model_dump(mode="json")
        elif isinstance(raw, (str, bytes)):
            raw = json.loads(raw)
        if not isinstance(raw, dict):
            return None
        category = raw.get("category")
        allowed = item.BOTTOMS if place == "bottom" else item.SHOES if place == "shoes" else item.TOPS
        if category not in allowed:
            return None
        color = item._color(raw.get("color_hex"), raw.get("color"))
        tags = item._tags(raw)
        return _draw_piece(tags, color, place)
    except Exception:
        # A bad detail must not remove the other pieces, nor be written to logs.
        if isinstance(category, str) and category in item.DRAWN:
            try:
                return _draw_piece(item._plain(category, {}, {}), color, place)
            except Exception:
                pass
        return None


def _draw_piece(tags: ItemTags, color: str, place: str) -> _Piece:
    template, params, extras, _ = drawing_for(tags)
    if template == "top":
        params = {**params, "state": "open" if place != "base" and params.get("front") in OPEN_FRONTS else "closed"}
    spec = Spec(template, params, Fill("solid", color), **extras)
    shape = build(template, {**params, **({"weight": spec.weight} if spec.weight else {})})
    defs, body, _, opening = _draw(spec, item.STYLE, f"figure-{place}", layered=True, dy=0)
    return _Piece(place, shape, defs, body, opening, params.get("sleeve", "long"))


def _clip(paths: list[str], uid: str) -> str:
    return f'<clipPath id="{uid}">' + "".join(f'<path d="{d}"/>' for d in paths) + "</clipPath>"


def _seen(shape: Shape) -> list[str]:
    """Under a closed top only its neck and hanging hem can remain visible."""
    x0, _, x1, hem = shape.body_box
    return [
        shape.outline,
        f"M {x0},{hem - 2} H {x1} V 600 H {x0} Z",
        f"M {CX - 48},-100 H {CX + 48} V 92 H {CX - 48} Z",
    ]


def _tops(pieces: list[_Piece]) -> tuple[str, str, str]:
    defs, backs, body = "", "", ""
    for index, piece in enumerate(pieces):
        uid = f"figure-{piece.place}"
        defs += piece.defs
        if body or backs:
            # A vest or short sleeve cannot conceal the longer sleeves beneath.
            # Use those actual sleeve shapes, not a wide rectangle that would
            # also expose an oversized underlayer's body beside a fitted top.
            sleeves = [path for previous in pieces[:index]
                       if SLEEVE_LENGTHS.get(previous.sleeve, 4) > SLEEVE_LENGTHS.get(piece.sleeve, 4)
                       for path, _ in previous.shape.sleeves]
            defs += _clip((piece.opening or _seen(piece.shape)) + sleeves, uid + "-under")
        under = f'<g clip-path="url(#{uid}-under)">{body}</g>' if body else ""
        if backs:
            backs = f'<g clip-path="url(#{uid}-under)">{backs}</g>'
        if piece.opening:
            back, fronts = piece.body
            backs = f'<g data-back="{piece.place}">{back}</g>' + backs
            body = under + fronts
        elif body:
            # The single-item renderer paints the inside neck as cloth.
            # Reveal the actual collar beneath it, without exposing the chest.
            holes = [part.d for part in piece.shape.parts if part.role == "hole"]
            defs += _clip(holes, uid + "-neck")
            body = under + str(piece.body) + f'<g clip-path="url(#{uid}-neck)">{body}</g>'
        else:
            body = str(piece.body)
        state = "open" if piece.opening else "closed"
        body = f'<g data-place="{piece.place}" data-state="{state}">{body}</g>'
    return defs, backs, body


def _bounds(shape: Shape, sx: float = 1, sy: float = 1, dx: float = 0, dy: float = 0):
    x0, y0, x1, y1 = shape.bbox
    if "shoulder_l" in shape.anchors:
        # A cropped top's sleeves can hang below its hem (the card bbox).
        points = [(float(x), float(y)) for x, y in re.findall(r"(-?[\d.]+),(-?[\d.]+)", shape.outline)]
        if points:
            y0 = min(y0, *(y for _, y in points))
            y1 = max(y1, *(y for _, y in points))
    xs = (x0 * sx + dx, x1 * sx + dx)
    ys = (y0 * sy + dy, y1 * sy + dy)
    return min(xs), min(ys), max(xs), max(ys)


def svg_from_pieces(pieces) -> str:
    """Draw base, mid, outer, bottom and shoes; missing/unknown pieces are absent.

    Tops share the original neck and shoulder anchors. Bottoms are uniformly
    scaled by K_PX/PX_CM and translated to the waist. Shoes are a mirrored pair
    of outward-facing side profiles, uniformly scaled from a 29 cm sole, with
    their ankles under the trouser legs and soles on a fixed ground line.
    """
    source = pieces if isinstance(pieces, Mapping) else {}
    drawn = {place: piece for place in PLACES if (piece := _piece(source.get(place), place))}
    bounds, defs, body = [], "", ""
    shoe = drawn.get("shoes")
    if shoe:
        defs += shoe.defs
        dy = GROUND_Y - SHOE_G * SHOE_SCALE
        ankle = SHOE_X0 + 0.78 * SHOE_L
        for side in (-1, 1):
            sx = -side * SHOE_SCALE
            dx = CX + side * LEG_CENTRE - ankle * sx
            body += (f'<g data-place="shoes" transform="matrix({sx} 0 0 {SHOE_SCALE} {dx} {dy})">'
                     f"{shoe.body}</g>")
            bounds.append(_bounds(shoe.shape, sx, SHOE_SCALE, dx, dy))
    bottom = drawn.get("bottom")
    if bottom:
        scale = K_PX / PX_CM
        wx, wy = bottom.shape.anchors["waist"]
        dx, dy = CX - wx * scale, WAIST_Y - wy * scale
        defs += bottom.defs
        body += (f'<g data-place="bottom" transform="matrix({scale} 0 0 {scale} {dx} {dy})">'
                 f"{bottom.body}</g>")
        bounds.append(_bounds(bottom.shape, scale, scale, dx, dy))
    tops = [drawn[p] for p in ("base", "mid", "outer") if p in drawn]
    top_defs, backs, top_body = _tops(tops)
    defs += top_defs
    # Trouser thighs must show between coat fronts, in front of its inside back.
    body = (f'<g data-layer="backs">{backs}</g>' if backs else "") + body + top_body
    bounds.extend(_bounds(p.shape) for p in tops)
    # Bboxes include the shaped hems/collars; margin also clears strokes and fuzz.
    x0 = min((b[0] for b in bounds), default=CX - 40) - MARGIN
    y0 = min((b[1] for b in bounds), default=0) - MARGIN
    x1 = max((b[2] for b in bounds), default=CX + 40) + MARGIN
    y1 = max((b[3] for b in bounds), default=80) + MARGIN
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0:.3f} {y0:.3f} {x1 - x0:.3f} {y1 - y0:.3f}" '
            f'width="{x1 - x0:.3f}" height="{y1 - y0:.3f}" role="img" aria-labelledby="figure-title">'
            '<title id="figure-title">Outfit as worn</title>'
            f"<defs>{defs}</defs>{body}</svg>")
