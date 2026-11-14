"""An outfit drawn as worn: the layered figure.

One front view of a whole outfit, worn on a quiet dress form: a headless
torso with a short neck stub, in one soft tone close to the card, drawn behind
everything (`_form`). It has no head, arms, hands, legs or feet; with LIMBS it
shows a short tonal arm below a short sleeve and a leg below shorts. Each piece
is drawn by the same templates and renderer as the item drawings, from the same
description, and placed by the points on the wearer every template keeps; the
form is placed by the same points:

- Tops share the neck and shoulder points, so they are drawn where they are on
  their own card. The base top is closed. A mid or outer layer that opens all
  the way down the front is worn open over what is under it; one that does not
  (a pullover, a hoodie) is worn closed, and of what is under it only what
  would really show is drawn: below its hem, above its neck, inside its neck
  opening, and the under sleeves where its own sleeves are shorter. Three
  layers nest the same way.
- Every piece is drawn at K_PX pixels per centimetre of the garment. The tops
  are drawn at that scale already; the trousers' template is drawn at PX_CM,
  so it is scaled by K_PX / PX_CM, and the shoes are drawn at K_PX. Lengths
  are true at that scale.
  Widths follow the tops' rule: a top's body is drawn at BODY_W (84%) of its
  flat width, because laid flat the cloth that wraps round the body lies out to
  the sides; trousers wrap round the legs the same way, so their width is drawn
  at the same share (BOTTOM_W). Drawn at full flat width, their hips stood out
  past the hem of every top.
- The trousers' waist sits WAIST_BELOW_NECK_CM under the neck point, which is
  above every top's hem: tops hang over the waistband, untucked.
- The ground lies a fixed distance under the waist (rise, inseam and a little
  break), the same whatever the trousers, so ankle trousers and shorts end
  above it. The shoes stand on it as a pair, seen from the front
  (`frontshoe`), toes forward and a little out, each centred under its
  trouser leg (the viewer's right one mirrored); a full-length hem covers the
  top of the shoe and nothing of it shows beside the leg.
- Accessories (`pieces["accessories"]`, a list) go by the point each template is
  drawn about, at K_PX: a belt is worn round the trousers' waistband, and the
  first top is then worn tucked in (its body cut off at the belt, its sleeves
  kept), so the belt shows over it and under any layer worn over it; a scarf at the neck point,
  over every top; a hat's band HAT_ABOVE_NECK_CM above the neck point, where a
  forehead would be; a bag beside the figure on the viewer's right, its handle
  at the height of a hand. One of each is drawn (the first given); the other
  accessories (ties, gloves, socks...) are not drawn in the figure.

`figure(pieces)` never raises: a missing place is not drawn, a piece of the
wrong kind for its place is left out, a piece that cannot be drawn falls back
to the plainest drawing of its category, and if even that fails it is left out.
"""
from __future__ import annotations

import logging
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from . import item
from .fills import Graphic
from .frontshoe import FrontShoe, front_shoe
from .illustrate import CARD, INK, Fill, Spec, _draw
from .templates import BODY_W, CX, K_PX, PX_CM, Shape, build

log = logging.getLogger("closet.drawing")

PLACES = ("base", "mid", "outer", "bottom", "shoes")
ACCESSORY_PLACE = {"belt": "belt", "scarf": "scarf", "bag": "bag", "cap": "hat", "beanie": "hat", "brimmed_hat": "hat"}
ACCESSORY_ORDER = ("belt", "scarf", "hat", "bag")
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
TOE_CM = 5.0                  # seen a little from above, the toes stand forward of the legs: lower on the page by this
LEG_CM = 12.5 * BOTTOM_W      # the middle of each leg, from the middle of the figure: where a straight leg's hem is
MARGIN = 18.0                 # the same space on every side of the figure

# the form: a dress form behind the clothes, one quiet tone a little darker than the card, with a faint edge
FORM = "#e4dfd5"
FORM_EDGE = "#cfc7b9"
FORM_CUT = "#ece8e0"          # the cut top of its neck stub, and the cut end of a tonal limb
LIMBS = False                 # whether a short tonal arm shows below a short sleeve and a leg below shorts
NECK_HALF_CM = 5.8            # half the neck stub's width
NECK_STUB_CM = 6.5            # how far the neck stub stands above the base of the neck, at least ...
NECK_OVER_CM = 3.0            # ... and above the highest collar, so it is seen ...
NECK_MAX_CM = 12.0            # ... up to this (a hood or a high collar hides it)
ELBOW_CM = 32.0               # from the shoulder point to the elbow, along the sleeve
KNEE_BELOW_WAIST_CM = 60.0    # the trousers template's knee
ARM_HALF_CM, THIGH_HALF_CM, KNEE_HALF_CM = 4.6, 7.2, 5.6

HAT_ABOVE_NECK_CM = 21.0      # the middle of a hat's band, at the forehead, above the base of the neck
HAND_BELOW_WAIST_CM = 22.0    # where a hand hangs holding a bag's handle, under the waist
BAG_GAP_CM = 5.0              # between the bag and the figure
BELT_HALF_CM = 20.5 * BOTTOM_W - 0.3   # a worn belt, either side of its buckle: the trousers' waist as drawn
EDGE = 2.5                    # half the drawn outline's width, in pixels: a body's edge is drawn this far outside it
TUCK_CM = 9.0                 # a top tucked in is drawn in to the belt's width over this much above the belt

WAIST_Y = NECK_Y + WAIST_BELOW_NECK_CM * K_PX
GROUND_Y = WAIST_Y + (RISE_CM + INSEAM_CM + BREAK_CM) * K_PX
BELT_Y = WAIST_Y + 2.0 * K_PX   # the middle of the waistband


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
    front: FrontShoe | None = None    # the shoes: one shoe seen from the front, in its own coordinates

    def point(self, p, copy: int = 0) -> tuple[float, float]:
        a, b, c, d, e, f = self.transforms[copy]
        return a * p[0] + c * p[1] + e, b * p[0] + d * p[1] + f

    def box(self, box=None) -> tuple[float, float, float, float]:
        """A box of the template (its drawn extent by default) in the figure, over every copy."""
        x0, y0, x1, y1 = box or self.shape.bbox
        pts = [self.point(q, i) for i in range(len(self.transforms)) for q in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))]
        return min(x for x, _ in pts), min(y for _, y in pts), max(x for x, _ in pts), max(y for _, y in pts)


@dataclass
class Form:
    """The dress form the clothes are worn on, in the figure's coordinates: a torso with shoulders and a short neck
    stub (no head, arms, hands, legs or feet), and, with LIMBS, short tonal limbs (paths ending at the elbow or the
    knee) where a short sleeve or shorts would leave them showing."""
    torso: str
    cap: str                                  # the cut top of the neck stub
    limbs: list[tuple[str, str]] = field(default_factory=list)   # (a limb, its cut end)
    ankles: bool = False                      # the shoes show the form's tonal ankle in their opening
    box: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)


@dataclass
class Layout:
    pieces: list[Placed] = field(default_factory=list)
    view: tuple[float, float, float, float] = (0.0, 0.0, 400.0, 600.0)   # x, y, width, height
    form: Form | None = None

    def fit(self) -> None:
        """The canvas: everything drawn, with MARGIN on every side."""
        boxes = [p.box() for p in self.pieces] + ([self.form.box] if self.form else [])
        boxes = boxes or [(CX - 100, NECK_Y, CX + 100, GROUND_Y)]
        x0, y0 = min(b[0] for b in boxes) - MARGIN, min(b[1] for b in boxes) - MARGIN
        x1, y1 = max(b[2] for b in boxes) + MARGIN, max(b[3] for b in boxes) + MARGIN
        self.view = (x0, y0, x1 - x0, y1 - y0)

    def get(self, place: str) -> Placed | None:
        return next((p for p in self.pieces if p.place == place), None)


def figure(pieces: Mapping[str, Piece | None] | None, *, uid: str = "f", limbs: bool = LIMBS) -> str:
    """The outfit as worn, as one SVG. `pieces` maps places (base, mid, outer, bottom, shoes) to pieces, and
    "accessories" to a list of pieces; a place that is missing or None is not drawn. With `limbs`, the form shows
    short tonal limbs below short sleeves and shorts. Never raises."""
    uid = item._uid(uid)
    try:
        return _svg(plan(pieces, limbs=limbs), uid)
    except Exception:
        log.exception("could not draw an outfit as worn")
        return _empty()


def plan(pieces: Mapping[str, Piece | None] | None, *, limbs: bool = LIMBS) -> Layout:
    """Where each piece goes: the figure's geometry, without drawing it."""
    out = Layout()
    pieces = pieces if isinstance(pieces, Mapping) else {}
    for place in PLACES:
        if place == "shoes":
            continue
        made = _placed(place, pieces.get(place))
        if made is not None:
            out.pieces.append(made)
    if any(p.place in TOP_PLACES or p.place == "bottom" for p in out.pieces):
        try:
            out.form = _form(out, limbs)
        except Exception:
            log.exception("placing the form for an outfit failed")
    made = _placed("shoes", pieces.get("shoes"))
    if made is not None:
        try:
            made = _stand(made, out)
            out.pieces.append(made)
        except Exception:
            log.exception("placing the shoes for an outfit failed")
    accessories = pieces.get("accessories")
    if isinstance(accessories, (list, tuple)):
        for made in _accessories(out, accessories):
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
    # the shoes: the item's drawing is a side view; the figure draws the same shoe from the front (frontshoe), and
    # `_stand` puts the pair under the legs once the trousers are placed. The side view's sole colour is kept.
    front = front_shoe(spec, K_PX, sole_default=shape.sole_default)
    flat = Shape(outline=front.outline, bbox=front.bbox, body_box=front.bbox, anchors=dict(front.anchors),
                 sole_default=shape.sole_default)
    return Placed(place, spec, flat, [(1.0, 0.0, 0.0, 1.0, CX - LEG_CM * K_PX, GROUND_Y),
                                      (-1.0, 0.0, 0.0, 1.0, CX + LEG_CM * K_PX, GROUND_Y)], K_PX, front=front)


def _legs(layout: Layout) -> tuple[float, float, bool]:
    """Where the middle of each leg is (the viewer's left, then right) at the ground, and whether the trousers
    reach the shoes. Full-length and ankle trousers: under the middle of each leg's opening. Shorts, or no
    trousers: under the legs of the form, where a straight leg's hem would be."""
    b = layout.get("bottom")
    left, right = CX - LEG_CM * K_PX, CX + LEG_CM * K_PX
    if b is None or b.spec.params.get("length", "full") not in ("full", "ankle"):
        return left, right, False
    if "leg_l" in b.shape.anchors and "leg_r" in b.shape.anchors:
        left, right = b.point(b.shape.anchors["leg_l"])[0], b.point(b.shape.anchors["leg_r"])[0]
    return left, right, b.spec.params.get("length", "full") == "full"


def _inside_legs(layout: Layout) -> str:
    """Under full-length trousers, where the shoes may be seen: below the hem, and above it only within the legs
    (as rectangles for a clip path); empty otherwise."""
    b = layout.get("bottom")
    if b is None or not _legs(layout)[2] or "hem_out" not in b.shape.anchors:
        return ""
    (xo, hy), (xi, _) = b.point(b.shape.anchors["hem_out"]), b.point(b.shape.anchors["hem_in"])
    xo, xi = min(xo, xi), max(xo, xi)
    rects = [(-4000.0, hy, 8000.0, 4000.0), (xo, -4000.0, xi - xo, 4000.0 + hy), (2 * CX - xi, -4000.0, xi - xo, 4000.0 + hy)]
    return "".join(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}"/>' for x, y, w, h in rects)


def _stand(shoes: Placed, layout: Layout) -> Placed:
    """The pair, each shoe centred under its leg, the toes on the ground and turned out; the viewer's right shoe
    is the left one mirrored. Without full-length trousers the form's ankle stands in each shoe (with LIMBS)."""
    left, right, covered = _legs(layout)
    ankle = layout.form is not None and layout.form.ankles and not covered
    if ankle:
        shoes.front = front_shoe(shoes.spec, K_PX, sole_default=shoes.shape.sole_default, ankle=_ankle())
        shoes.shape = Shape(outline=shoes.front.outline, bbox=shoes.front.bbox, body_box=shoes.front.bbox,
                            anchors=dict(shoes.front.anchors), sole_default=shoes.shape.sole_default)
    bx = (shoes.shape.bbox[0] + shoes.shape.bbox[2]) / 2
    y = GROUND_Y + TOE_CM * K_PX
    shoes.transforms = [(1.0, 0.0, 0.0, 1.0, left - bx, y), (-1.0, 0.0, 0.0, 1.0, right + bx, y)]
    return shoes


def _ankle() -> str:
    return f'<path d="{{d}}" fill="{FORM}" stroke="{FORM_EDGE}" stroke-width="1.2" stroke-linejoin="round"/>'


# ------------------------------------------------------------------ the form

def _f(v: float) -> str:
    return f"{v:.1f}"


def _neck_top(layout: Layout) -> float:
    """Where the neck stub is cut: above the highest collar among the tops, so it shows over a shirt's collar too."""
    stub = NECK_STUB_CM * K_PX
    tops = [p for p in layout.pieces if p.place in TOP_PLACES]
    if tops:
        collar = min(p.box()[1] for p in tops)
        stub = max(stub, min(NECK_Y - collar + NECK_OVER_CM * K_PX, NECK_MAX_CM * K_PX))
    return NECK_Y - stub


def _torso(top: float) -> str:
    """The form's torso, neck stub (cut at `top`) to hips: the shoulders just inside every top's, the waist as
    wide as a worn belt (so a top tucked in under one shows nothing behind it), and it ends above the trousers'
    crotch."""
    k, n, w = K_PX, NECK_Y, WAIST_Y
    nw = NECK_HALF_CM * k
    waist = BELT_HALF_CM * k
    right = [("C", (CX + nw + 2, n + 10), (CX + 50, n + 15), (CX + 21 * k, n + 7.8 * k)),     # trapezius to the shoulder
             ("C", (CX + 23 * k, n + 9.5 * k), (CX + 21.5 * k, n + 17.5 * k), (CX + 17.6 * k, n + 20 * k)),   # the arm plate
             ("C", (CX + 17 * k, n + 30 * k), (CX + waist, w - 9 * k), (CX + waist, w)),     # down the side to the waist
             ("C", (CX + waist, w + 6 * k), (CX + 17.9 * k, w + 10 * k), (CX + 17.7 * k, w + 15 * k)),   # the hip
             ("C", (CX + 17.5 * k, w + 19 * k), (CX + 9 * k, w + 23.5 * k), (CX, w + 23.5 * k))]   # round under it

    def mirror(q):
        return (2 * CX - q[0], q[1])

    d = f"M {_f(CX + nw)},{_f(top)} L {_f(CX + nw)},{_f(n - 2)} "
    d += " ".join(f"C {_f(a[0])},{_f(a[1])} {_f(b[0])},{_f(b[1])} {_f(c[0])},{_f(c[1])}" for _, a, b, c in right)
    starts = [(CX + nw, n - 2)] + [seg[3] for seg in right[:-1]]
    for (_, a, b, _c), st in zip(reversed(right), reversed(starts), strict=True):
        a, b, st = mirror(b), mirror(a), mirror(st)
        d += f" C {_f(a[0])},{_f(a[1])} {_f(b[0])},{_f(b[1])} {_f(st[0])},{_f(st[1])}"
    return d + f" L {_f(CX - nw)},{_f(top)} Z"


def _ellipse(cx: float, cy: float, rx: float, ry: float, deg: float = 0.0) -> str:
    pts = []
    for i in range(24):
        a = 2 * math.pi * i / 24
        x, y = rx * math.cos(a), ry * math.sin(a)
        c, s_ = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        pts.append((cx + x * c - y * s_, cy + x * s_ + y * c))
    return "M " + " L ".join(f"{_f(x)},{_f(y)}" for x, y in pts) + " Z"


def _limb(a: tuple[float, float], b: tuple[float, float], ra: float, rb: float) -> tuple[str, str]:
    """A tonal limb from a (hidden under the cloth) to b, ra and rb wide either side of its middle there, cut
    straight across at b; and the cut end, an ellipse seen a little from above."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy) or 1.0
    px, py = -dy / n, dx / n
    pts = [(a[0] + px * ra, a[1] + py * ra), (b[0] + px * rb, b[1] + py * rb),
           (b[0] - px * rb, b[1] - py * rb), (a[0] - px * ra, a[1] - py * ra)]
    body = "M " + " L ".join(f"{_f(x)},{_f(y)}" for x, y in pts) + " Z"
    return body, _ellipse(b[0], b[1], rb, rb * 0.32, math.degrees(math.atan2(py, px)))


def _numbers(d: str) -> list[tuple[float, float]]:
    return [(float(x), float(y)) for x, y in re.findall(r"(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)", d)]


def _arms(layout: Layout) -> list[tuple[str, str]]:
    """Short tonal arms, from inside each sleeve to the elbow, along the sleeve: only when every top has short or
    elbow sleeves (a sleeveless top shows no arm: the form has none). Drawn no wider than the sleeve's opening."""
    tops = [p for p in layout.pieces if p.place in TOP_PLACES]
    ranks = [SLEEVE_RANK.get(p.spec.params.get("sleeve", "long"), 4) for p in tops]
    if not tops or not all(r in (1, 2) for r in ranks):
        return []
    top = max(reversed(tops), key=lambda p: SLEEVE_RANK.get(p.spec.params.get("sleeve", "long"), 4))
    out = []
    for path, deg in top.shape.sleeves:
        pts = [top.point(q) for q in _numbers(path)]
        if not pts:
            continue
        side = 1 if sum(x for x, _ in pts) / len(pts) > CX else -1
        sh = top.point(top.shape.anchors["shoulder_r" if side > 0 else "shoulder_l"])
        t = math.radians(abs(deg))
        ux, uy = side * math.sin(t), math.cos(t)          # down the sleeve
        vx, vy = -uy, ux
        along = [((x - sh[0]) * ux + (y - sh[1]) * uy, (x - sh[0]) * vx + (y - sh[1]) * vy) for x, y in pts]
        reach = max(a for a, _ in along)
        cuff = [c for a, c in along if a > reach - 6]
        mid, half = (min(cuff) + max(cuff)) / 2, (max(cuff) - min(cuff)) / 2
        elbow = ELBOW_CM * K_PX
        if elbow <= reach + 4:
            continue
        r = min(ARM_HALF_CM * K_PX, half * 0.78)
        a = (sh[0] + ux * (reach - 30) + vx * mid, sh[1] + uy * (reach - 30) + vy * mid)
        b = (sh[0] + ux * elbow + vx * mid, sh[1] + uy * elbow + vy * mid)
        out.append(_limb(a, b, r, r * 0.88))
    return out


def _thighs(layout: Layout) -> list[tuple[str, str]]:
    """Short tonal legs below shorts, to the knee, under the legs' middles."""
    b = layout.get("bottom")
    if b is None or b.spec.params.get("length") not in ("short", "brief"):
        return []
    hem = b.point(b.shape.anchors["hem"])[1]
    knee = WAIST_Y + KNEE_BELOW_WAIST_CM * K_PX
    if knee <= hem + 4:
        return []
    out = []
    for side in (-1, 1):
        x = CX + side * LEG_CM * K_PX
        out.append(_limb((x, hem - 30), (x, knee), THIGH_HALF_CM * K_PX, KNEE_HALF_CM * K_PX))
    return out


def _form(layout: Layout, limbs: bool) -> Form:
    nw, top = NECK_HALF_CM * K_PX, _neck_top(layout)
    torso = _torso(top)
    form = Form(torso, _ellipse(CX, top, nw, nw * 0.3))
    if limbs:
        form.limbs = _arms(layout) + _thighs(layout)
        form.ankles = True
    pts = _numbers(torso) + [q for d, c in form.limbs for q in _numbers(d) + _numbers(c)] + [(CX, top - nw * 0.3)]
    form.box = (min(x for x, _ in pts), min(y for _, y in pts), max(x for x, _ in pts), max(y for _, y in pts))
    return form


def _neck_front(form: Form, first: Placed, cid: str, defs: list[str]) -> str:
    """The neck stub again over the tops, above the innermost top's neck opening and no wider than the neck: what
    is drawn there is the back of a collar, which is behind the neck."""
    holes = [q for part in first.shape.parts if part.role == "hole" for q in _numbers(part.d)]
    if not holes:
        return ""
    cut = min(first.point(q)[1] for q in holes) + 1.5
    nw = NECK_HALF_CM * K_PX + 1.0
    top = min(y for _, y in _numbers(form.cap)) - 2
    if cut <= top:
        return ""
    defs.append(f'<clipPath id="{cid}"><rect x="{CX - nw:.1f}" y="{top:.1f}" width="{2 * nw:.1f}" height="{cut - top:.1f}"/></clipPath>')
    return f'<g clip-path="url(#{cid})">{_form_markup(form, limbs=False)}</g>'


def _form_markup(form: Form, *, limbs: bool = True) -> str:
    """The form, one quiet tone with a faint edge; the cut ends a shade lighter."""
    edge = f'stroke="{FORM_EDGE}" stroke-width="1.2" stroke-linejoin="round"'
    out = [f'<path d="{form.torso}" fill="{FORM}" {edge}/>', f'<path d="{form.cap}" fill="{FORM_CUT}" {edge}/>']
    if limbs:
        for d, cut in form.limbs:
            out += [f'<path d="{d}" fill="{FORM}" {edge}/>', f'<path d="{cut}" fill="{FORM_CUT}" {edge}/>']
    return "".join(out)


def _accessories(out: Layout, given) -> list[Placed]:
    """The first belt, scarf, hat and bag among `given`, placed on the figure."""
    specs: dict[str, Spec] = {}
    for piece in given:
        if not isinstance(piece, Piece) or piece.category not in item.ACCESSORIES:
            continue
        for make in (_spec, _plainest):
            try:
                spec = make(piece)
            except Exception:
                log.exception("drawing a %s for an outfit failed", piece.category)
                continue
            place = ACCESSORY_PLACE.get(spec.template)
            if place is not None:
                specs.setdefault(place, spec)
                break
    placed = []
    for place in ACCESSORY_ORDER:
        if place not in specs:
            continue
        try:
            placed.append(_place_accessory(place, specs[place], out))
        except Exception:
            log.exception("placing a %s in an outfit failed", place)
    return placed


def _place_accessory(place: str, spec: Spec, out: Layout) -> Placed:
    params = {**spec.params, "px": K_PX}
    if place == "belt":
        params.update(worn=True, half=BELT_HALF_CM)
    spec = replace(spec, params=params)
    shape = _shape(spec)
    _draw(spec, "line", "probe", dy=0.0)
    if place == "belt":
        x, y = CX, BELT_Y
    elif place == "scarf":
        x, y = CX, NECK_Y
    elif place == "hat":
        x, y = CX, NECK_Y - HAT_ABOVE_NECK_CM * K_PX
    else:
        boxes = [p.box() for p in out.pieces] or [(CX - 25 * K_PX, NECK_Y, CX + 25 * K_PX, GROUND_Y)]
        x = max(b[2] for b in boxes) + BAG_GAP_CM * K_PX + (CX - shape.bbox[0])
        y = WAIST_Y + HAND_BELOW_WAIST_CM * K_PX
    return Placed(place, spec, shape, [(1.0, 0.0, 0.0, 1.0, x - CX, y)], K_PX)


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


def _tucked(p: Placed) -> tuple[list[str], str]:
    """A top worn tucked in: where it shows (paths in the figure: above the belt, its body drawn in from the width
    of its body to the belt's over the last TUCK_CM, and beside its body, where the sleeves hang), and the
    drawn-in sides as ink lines. Beside the body is taken from just past its drawn edge, so the body's own sides do
    not show below the belt."""
    x0, _, x1, _ = p.box(p.shape.body_box)
    bx0, bx1 = CX - BELT_HALF_CM * K_PX, CX + BELT_HALF_CM * K_PX
    ty = BELT_Y - TUCK_CM * K_PX
    far = 4000.0
    shows = [f"M {-far:.1f},{-far:.1f} L {far:.1f},{-far:.1f} L {far:.1f},{ty:.1f} L {x1:.1f},{ty:.1f} "
             f"Q {x1:.1f},{BELT_Y - 2 * K_PX:.1f} {bx1:.1f},{BELT_Y:.1f} L {bx0:.1f},{BELT_Y:.1f} "
             f"Q {x0:.1f},{BELT_Y - 2 * K_PX:.1f} {x0:.1f},{ty:.1f} L {-far:.1f},{ty:.1f} Z",
             f"M {-far:.1f},{ty:.1f} L {x0 - EDGE:.1f},{ty:.1f} L {x0 - EDGE:.1f},{far:.1f} L {-far:.1f},{far:.1f} Z",
             f"M {x1 + EDGE:.1f},{ty:.1f} L {far:.1f},{ty:.1f} L {far:.1f},{far:.1f} L {x1 + EDGE:.1f},{far:.1f} Z"]
    sides = "".join(f'<path d="M {x:.1f},{ty:.1f} Q {x:.1f},{BELT_Y - 2 * K_PX:.1f} {bx:.1f},{BELT_Y:.1f}" fill="none" '
                    f'stroke="{INK}" stroke-width="2.6" stroke-linecap="round"/>' for x, bx in ((x0, bx0), (x1, bx1)))
    return shows, sides


def _clip(cid: str, paths: list[str], t) -> str:
    return f'<clipPath id="{cid}">' + "".join(f'<path d="{d}" transform="{_matrix(t)}"/>' for d in paths) + "</clipPath>"


def _svg(layout: Layout, uid: str) -> str:
    defs: list[str] = []
    body: list[str] = []
    form = layout.form
    if form is not None:   # the form first, behind everything
        body.append(f'<g id="{uid}m">{_form_markup(form)}</g>')
    shoes, bottom = layout.get("shoes"), layout.get("bottom")
    if shoes is not None:
        front = front_shoe(shoes.spec, K_PX, sole_default=shoes.shape.sole_default, uid=f"{uid}s",
                           ankle=_ankle() if shoes.front is not None and shoes.front.ankle else None)
        defs.append(front.defs)
        pair = "".join(f'<g transform="{_matrix(t)}">{front.body}</g>' for t in shoes.transforms)
        legs = _inside_legs(layout)
        if legs:   # under full-length trousers: nothing of a shoe shows beside the leg above the hem
            defs.append(f'<clipPath id="{uid}k">{legs}</clipPath>')
            pair = f'<g clip-path="url(#{uid}k)">{pair}</g>'
        body.append(pair)
    lower = ""
    if bottom is not None:
        d, b, _, _ = _draw(bottom.spec, "line", f"{uid}b", dy=0.0)
        defs.append(d)
        lower = "".join(f'<g transform="{_matrix(t)}">{b}</g>' for t in bottom.transforms)
    # the tops, from the inside out: each one over everything under it
    extra = {}
    for p in layout.pieces:
        if p.place in ACCESSORY_ORDER:
            d, b, _, _ = _draw(p.spec, "line", f"{uid}{p.place[0]}", dy=0.0)
            defs.append(d)
            extra[p.place] = f'<g transform="{_matrix(p.transforms[0])}">{b}</g>'
    belt = extra.get("belt", "")
    first = next((q for q in layout.pieces if q.place in TOP_PLACES), None)
    if belt and (first is None or first.open):   # nothing to tuck in: the belt is seen on the trousers
        lower += belt
        belt = ""
    if lower:
        body.append(f'<g id="{uid}w">{lower}</g>')
    # what the form shows inside the neck of the innermost top: its neck and the top of its chest, in the top's
    # own coordinates
    neck = chest = ""
    if form is not None:
        cut = f"{uid}c"
        defs.append(f'<clipPath id="{cut}"><rect x="-4000" y="-4000" width="8000" '
                    f'height="{4000 + NECK_Y + 30 * K_PX:.1f}"/></clipPath>')
        chest = f'<g clip-path="url(#{cut})">{_form_markup(form, limbs=False)}</g>'
        neck = f'<g transform="translate(0 {-TOP_DY:.1f})">{chest}</g>'
    stack, under = "", []
    for n, p in enumerate(q for q in layout.pieces if q.place in TOP_PLACES):
        tid = f"{uid}t{n}"
        d, b, _, _ = _draw(p.spec, "line", tid, layered=True, dy=TOP_DY, inside=neck if not stack and not p.open else None)
        defs.append(d)
        if belt and isinstance(b, str):   # tucked in: its body ends at the belt, its sleeves hang beside it
            shows, sides = _tucked(p)
            defs.append(_clip(f"k{tid}", shows, (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)))
            b = f'<g clip-path="url(#k{tid})">{b}</g>' + sides + belt
            belt = ""
        shows = _shows(p, under) if stack else None
        seen = stack
        if stack and shows is not None:
            defs.append(_clip(f"v{tid}", shows, p.transforms[0]))
            seen = f'<g clip-path="url(#v{tid})">{stack}</g>'
        if p.open and isinstance(b, tuple):
            back, fronts = b
            if not stack and form is not None:   # nothing under it: the form shows in the opening, the trousers over it
                seen = f'<use href="#{uid}m"/>' + (f'<use href="#{uid}w"/>' if lower else "")
            else:   # the form's neck stands in front of this one's collar at the back, behind what is under it
                seen = chest + seen
            stack = back + seen + fronts
        else:
            stack = seen + b
            holes = [part.d for part in p.shape.parts if part.role == "hole"]
            if seen and holes:   # what is underneath shows inside the neck opening (a shirt collar in a V)
                defs.append(_clip(f"n{tid}", holes, p.transforms[0]))
                stack += f'<g clip-path="url(#n{tid})">{chest}{seen}</g>'
        under.append(p)
    body.append(stack)
    if form is not None and first is not None:
        body.append(_neck_front(form, first, f"{uid}f", defs))
    body += [extra[k] for k in ("scarf", "hat", "bag") if k in extra]
    x, y, w, h = layout.view
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x:.1f} {y:.1f} {w:.1f} {h:.1f}" '
            f'width="{w:.0f}" height="{h:.0f}"><defs>{"".join(defs)}</defs>'
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="18" fill="{CARD}"/>'
            f'{"".join(body)}</svg>')


def _empty() -> str:
    w, h = 400.0, 600.0
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" width="{w:.0f}" height="{h:.0f}">'
            f'<rect width="{w:.0f}" height="{h:.0f}" rx="18" fill="{CARD}"/></svg>')


