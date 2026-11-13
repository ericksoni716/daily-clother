"""An outfit drawn as worn: the layered figure.

One front view of a whole outfit, with no body drawn (the clothes stand by
themselves, as on an invisible mannequin). Each piece is drawn by the same
templates and renderer as the item drawings, from the same description, and
placed by the points on the wearer every template keeps:

- Tops share the neck and shoulder points, so they are drawn where they are on
  their own card. The base top is closed. A mid or outer layer that opens all
  the way down the front is worn open over what is under it; one that does not
  (a pullover, a hoodie) is worn closed, and of what is under it only what
  would really show is drawn: below its hem, above its neck, inside its neck
  opening, and the under sleeves where its own sleeves are shorter. Three
  layers nest the same way.
- Every piece is drawn at K_PX pixels per centimetre of the garment. The tops
  are drawn at that scale already; the trousers' template is drawn at PX_CM
  and the shoe's at SHOE_L pixels for one shoe length, so they are scaled by
  K_PX / PX_CM and by SHOE_CM * K_PX / SHOE_L. Lengths are true at that scale.
  Widths follow the tops' rule: a top's body is drawn at BODY_W (84%) of its
  flat width, because laid flat the cloth that wraps round the body lies out to
  the sides; trousers wrap round the legs the same way, so their width is drawn
  at the same share (BOTTOM_W). Drawn at full flat width, their hips stood out
  past the hem of every top.
- The trousers' waist sits WAIST_BELOW_NECK_CM under the neck point, which is
  above every top's hem: tops hang over the waistband, untucked.
- The ground lies a fixed distance under the waist (rise, inseam and a little
  break), the same whatever the trousers, so ankle trousers and shorts end
  above it. The shoes stand on it as a pair: the side-view shoe twice, the
  viewer's right one mirrored, each with its toe turned out and foreshortened
  as a shoe turned partly toward the viewer, under the legs.

`figure(pieces)` never raises: a missing place is not drawn, a piece of the
wrong kind for its place is left out, a piece that cannot be drawn falls back
to the plainest drawing of its category, and if even that fails it is left out.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from . import item
from .fills import Graphic
from .illustrate import CARD, Fill, Spec, _draw
from .templates import BODY_W, CX, K_PX, PX_CM, SHOE_G, SHOE_L, Shape, build

log = logging.getLogger("closet.drawing")

PLACES = ("base", "mid", "outer", "bottom", "shoes")
TOP_PLACES = ("base", "mid", "outer")
PLACE_TEMPLATE = {"base": "top", "mid": "top", "outer": "top", "bottom": "pants", "shoes": "sneaker"}
PLACE_CATEGORIES = {"base": item.TOPS, "mid": item.TOPS, "outer": item.TOPS, "bottom": item.BOTTOMS, "shoes": item.SHOES}
# fronts that open all the way down; worn as a mid or outer layer they are drawn open
OPENS = ("buttons", "french", "hidden", "double", "zip")
SLEEVE_RANK = {"none": 0, "short": 1, "elbow": 2, "three-quarter": 3, "long": 4}

TOP_DY = 24.0                 # the tops are drawn this far down their own card, so a hood stays on it
NECK_Y = 58.0 + TOP_DY        # the base of the neck on the wearer (the tops' "neck" anchor)
WAIST_BELOW_NECK_CM = 48.0    # where a mid-rise waistband sits on a men's medium: above every top's hem
RISE_CM, INSEAM_CM = 27.0, 81.0   # the trousers template's front rise and full inseam
BOTTOM_W = BODY_W             # the share of their flat width trousers are drawn at, as tops' bodies are
BREAK_CM = 5.0                # a full-length trouser hem rests this far above the ground, on the shoe
SHOE_CM = 29.5                # one shoe, toe to heel: a men's UK 9 / EU 43
SHOE_TURN = 0.7               # the side view foreshortened to this share of its length: turned partly toward the viewer
FOOT_CM = 5.0                 # where each heel sits, from the middle of the figure
MARGIN = 18.0                 # the same space on every side of the figure

WAIST_Y = NECK_Y + WAIST_BELOW_NECK_CM * K_PX
GROUND_Y = WAIST_Y + (RISE_CM + INSEAM_CM + BREAK_CM) * K_PX


@dataclass(frozen=True)
class Piece:
    """One item, described as its own drawing is: the stored tagger answer when there is one (with the
    owner's corrections already in it), otherwise the closet's coarse fields."""
    category: str | None = None
    answer: object = None
    color_hex: str | None = None
    color: str | None = None
    pattern: str | None = None
    silhouette: dict | None = None
    fill: Fill | None = None     # the item's pattern measured from its photo, as its own drawing uses it
    graphic: Graphic | None = None   # a print lifted from its photo (tops only), as its own drawing uses it


@dataclass
class Placed:
    """A piece as it is drawn in the figure. `transforms` map the template's canvas into the figure, one per
    copy drawn (two for the shoes), as SVG matrices (a, b, c, d, e, f)."""
    place: str
    spec: Spec
    shape: Shape
    transforms: list[tuple[float, float, float, float, float, float]]
    px_per_cm: float
    open: bool = False

    def point(self, p, copy: int = 0) -> tuple[float, float]:
        a, b, c, d, e, f = self.transforms[copy]
        return a * p[0] + c * p[1] + e, b * p[0] + d * p[1] + f

    def box(self, box=None) -> tuple[float, float, float, float]:
        """A box of the template (its drawn extent by default) in the figure, over every copy."""
        x0, y0, x1, y1 = box or self.shape.bbox
        pts = [self.point(q, i) for i in range(len(self.transforms)) for q in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))]
        return min(x for x, _ in pts), min(y for _, y in pts), max(x for x, _ in pts), max(y for _, y in pts)


@dataclass
class Layout:
    pieces: list[Placed] = field(default_factory=list)
    view: tuple[float, float, float, float] = (0.0, 0.0, 400.0, 600.0)   # x, y, width, height

    def fit(self) -> None:
        """The canvas: everything drawn, with MARGIN on every side."""
        boxes = [p.box() for p in self.pieces] or [(CX - 100, NECK_Y, CX + 100, GROUND_Y)]
        x0, y0 = min(b[0] for b in boxes) - MARGIN, min(b[1] for b in boxes) - MARGIN
        x1, y1 = max(b[2] for b in boxes) + MARGIN, max(b[3] for b in boxes) + MARGIN
        self.view = (x0, y0, x1 - x0, y1 - y0)

    def get(self, place: str) -> Placed | None:
        return next((p for p in self.pieces if p.place == place), None)


def figure(pieces: Mapping[str, Piece | None] | None, *, uid: str = "f") -> str:
    """The outfit as worn, as one SVG. `pieces` maps places (base, mid, outer, bottom, shoes) to pieces;
    a place that is missing or None is not drawn. Never raises."""
    uid = item._uid(uid)
    try:
        return _svg(plan(pieces), uid)
    except Exception:
        log.exception("could not draw an outfit as worn")
        return _empty()


def plan(pieces: Mapping[str, Piece | None] | None) -> Layout:
    """Where each piece goes: the figure's geometry, without drawing it."""
    out = Layout()
    pieces = pieces if isinstance(pieces, Mapping) else {}
    for place in PLACES:
        made = _placed(place, pieces.get(place))
        if made is not None:
            out.pieces.append(made)
    out.fit()
    return out


# ------------------------------------------------------------------ pieces

def _spec(piece: Piece) -> Spec:
    """The piece's drawing as its own item drawing would be made: from its answer, else from its fields."""
    tags = item._tags(piece.answer) if piece.answer is not None else None
    if tags is None or tags.category != piece.category:
        word = piece.color if isinstance(piece.color, str) and piece.color in item.NAMED_HEX else "grey"
        tags = item._plain(piece.category, item._known_silhouette(piece.silhouette), {}, word)
    template, params, extras, _ = item.drawing_for(tags)
    return Spec(template, dict(params), piece.fill or Fill("solid", item._color(piece.color_hex, tags.color)),
                graphic=piece.graphic if template == "top" else None, **extras)


def _plainest(piece: Piece) -> Spec:
    template, params, extras, _ = item.drawing_for(item._plain(piece.category, {}, {}))
    return Spec(template, dict(params), Fill("solid", item._color(piece.color_hex, piece.color)), **extras)


def _shape(spec: Spec) -> Shape:
    params = spec.params if not spec.weight or "weight" in spec.params else {**spec.params, "weight": spec.weight}
    return build(spec.template, params)


def _placed(place: str, piece) -> Placed | None:
    """The piece placed in the figure; the plainest drawing of its category if its own cannot be drawn;
    None if it is not something this place shows, or nothing can be drawn."""
    if not isinstance(piece, Piece) or piece.category not in PLACE_CATEGORIES[place]:
        return None
    for make in (_spec, _plainest):
        try:
            spec = make(piece)
            if spec.template == PLACE_TEMPLATE[place]:
                return _place(place, spec)
        except Exception:
            log.exception("drawing a %s for an outfit failed", piece.category)
    return None


def _place(place: str, spec: Spec) -> Placed:
    if spec.template == "top":
        spec.params.pop("state", None)
        opened = False
        if place != "base" and spec.params.get("front") in OPENS:
            worn_open = replace(spec, params={**spec.params, "state": "open"})
            shape = _shape(worn_open)
            if shape.fronts:
                spec, opened = worn_open, True
        shape = _shape(spec)
        _draw(spec, "line", "probe", dy=TOP_DY)   # fails here, not halfway through the figure
        return Placed(place, spec, shape, [(1.0, 0.0, 0.0, 1.0, 0.0, TOP_DY)], K_PX, opened)
    shape = _shape(spec)
    _draw(spec, "line", "probe", dy=0.0)
    if spec.template == "pants":
        s = K_PX / PX_CM
        sx = s * BOTTOM_W
        wx, wy = shape.anchors["waist"]
        return Placed(place, spec, shape, [(sx, 0.0, 0.0, s, CX - wx * sx, WAIST_Y - wy * s)], PX_CM * s)
    # the shoes: one side view, twice. The viewer's left shoe as drawn (toe to the left), the right one mirrored;
    # each heel under its leg, the toe turned out and the length foreshortened by the turn.
    s = SHOE_CM * K_PX / SHOE_L
    hx, gy = shape.anchors["heel"][0], SHOE_G
    heel = FOOT_CM * K_PX
    left = (s * SHOE_TURN, 0.0, 0.0, s, CX - heel - hx * s * SHOE_TURN, GROUND_Y - gy * s)
    right = (-s * SHOE_TURN, 0.0, 0.0, s, CX + heel + hx * s * SHOE_TURN, GROUND_Y - gy * s)
    return Placed(place, spec, shape, [left, right], SHOE_L / SHOE_CM * s)


# ------------------------------------------------------------------ drawing

def _matrix(t) -> str:
    return "matrix(" + " ".join(f"{v:.4f}".rstrip("0").rstrip(".") for v in t) + ")"


def _shows(p: Placed, under: list[Placed]) -> list[str] | None:
    """Where the layers under a top can be seen (paths in the template's canvas), or None for everywhere.
    Inside the top's outline (its fronts and sleeves cover most of that), below its hem as wide as its body,
    and above its collar as wide as a neck. When its sleeves are shorter than one underneath (a vest, a
    short-sleeved overshirt), nothing underneath is hidden but what it covers."""
    rank = SLEEVE_RANK.get(p.spec.params.get("sleeve", "long"), 4)
    if any(SLEEVE_RANK.get(u.spec.params.get("sleeve", "long"), 4) > rank for u in under):
        return None
    sh = p.shape
    half = (sh.body_box[2] - sh.body_box[0]) / 2
    hem_y, sh_y = sh.body_box[3], sh.anchors.get("shoulder_l", (0, 80.0))[1]
    far = 2000.0

    def poly(pts):
        return "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts) + " Z"

    return [sh.outline,
            poly([(CX - half, hem_y - 2), (CX + half, hem_y - 2), (CX + half, far), (CX - half, far)]),
            poly([(CX - 48, -far), (CX + 48, -far), (CX + 48, sh_y + 12), (CX - 48, sh_y + 12)])]


def _clip(cid: str, paths: list[str], t) -> str:
    return f'<clipPath id="{cid}">' + "".join(f'<path d="{d}" transform="{_matrix(t)}"/>' for d in paths) + "</clipPath>"


def _svg(layout: Layout, uid: str) -> str:
    defs: list[str] = []
    body: list[str] = []
    shoes, bottom = layout.get("shoes"), layout.get("bottom")
    for p, key in ((shoes, "s"), (bottom, "b")):
        if p is None:
            continue
        d, b, _, _ = _draw(p.spec, "line", f"{uid}{key}", dy=0.0)
        defs.append(d)
        body += [f'<g transform="{_matrix(t)}">{b}</g>' for t in p.transforms]
    # the tops, from the inside out: each one over everything under it
    stack, under = "", []
    for n, p in enumerate(q for q in layout.pieces if q.place in TOP_PLACES):
        tid = f"{uid}t{n}"
        d, b, _, _ = _draw(p.spec, "line", tid, layered=True, dy=TOP_DY)
        defs.append(d)
        shows = _shows(p, under) if stack else None
        seen = stack
        if stack and shows is not None:
            defs.append(_clip(f"v{tid}", shows, p.transforms[0]))
            seen = f'<g clip-path="url(#v{tid})">{stack}</g>'
        if p.open and isinstance(b, tuple):
            back, fronts = b
            stack = back + seen + fronts
        else:
            stack = seen + b
            holes = [part.d for part in p.shape.parts if part.role == "hole"]
            if seen and holes:   # what is underneath shows inside the neck opening (a shirt collar in a V)
                defs.append(_clip(f"n{tid}", holes, p.transforms[0]))
                stack += f'<g clip-path="url(#n{tid})">{seen}</g>'
        under.append(p)
    body.append(stack)
    x, y, w, h = layout.view
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x:.1f} {y:.1f} {w:.1f} {h:.1f}" '
            f'width="{w:.0f}" height="{h:.0f}"><defs>{"".join(defs)}</defs>'
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="18" fill="{CARD}"/>'
            f'{"".join(body)}</svg>')


def _empty() -> str:
    w, h = 400.0, 600.0
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" width="{w:.0f}" height="{h:.0f}">'
            f'<rect width="{w:.0f}" height="{h:.0f}" rx="18" fill="{CARD}"/></svg>')


