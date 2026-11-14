"""An outfit drawn as worn: the layered figure.

One front view of a whole outfit, worn by a person drawn in the garments' own
flat style (`_body`): head, neck, arms, hands, legs and feet, about 7.5 heads
tall, standing front-on with the arms a little away from the body. The skin is
one colour, SKIN, read from this one place; it is drawn first, behind every
garment, so it shows only where nothing covers it: the face and neck, the hands
below the cuffs, the forearms below short sleeves, the legs below shorts, the
ankles in low shoes and the feet in sandals. The head has a simple face (eyes,
brows, a hint of nose and mouth) or, with face=False, only hair and its shape.
Each piece is drawn by the same templates and renderer as the item drawings,
from the same description, and placed by the points on the wearer every
template keeps; the body is placed by the same points:

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
from .frontshoe import FrontShoe, bare_feet, front_shoe
from .illustrate import CARD, INK, Fill, Spec, _draw, shade
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

# the wearer: a man about 7.5 heads tall, standing front-on, drawn in the garments' own line and flat fills
SKIN = "#c68e6a"              # the skin's colour: the one place it is read from (a Settings choice can set it later)
SKIN_LINE = shade(SKIN, -0.32)   # the lines drawn on skin: fingers, ears, toes, nose and mouth
TOE_LINE = SKIN_LINE
HAIR = "#3b2e27"
EYE = "#2b211c"
FACE = True                   # a simple face (eyes, brows, a hint of nose and mouth); False: only hair and head shape
LINE = 3.8                    # the body's outline, as wide as a garment's (illustrate's "line" style)
HEAD_H_CM, HEAD_W_CM = 23.5, 15.6   # crown to chin, and across the cheeks
CHIN_CM = 7.5                 # the chin, above the base of the neck
NECK_HALF_CM = 5.8            # half the neck's width
NECK_IN_CM = 4.5              # how far the neck is drawn on down inside a top's neck opening, over its back
SHOULDER_IN_CM = 4.5          # the top of the arm, in from a top's shoulder point and down from it
ELBOW_CM, WRIST_CM = 29.0, 54.0   # from the top of the arm, along it
ARM_HALF_CM, ELBOW_HALF_CM, WRIST_HALF_CM = 4.9, 3.8, 2.7
FOREARM_DEG = 9.0             # below a short sleeve the forearm hangs this far out from straight down
BARE_ARM_DEG = 14.0           # an arm with no sleeve over it, from straight down
HIP_CM, HIP_DOWN_CM = 8.5, 12.0   # the top of each leg (hidden in the trousers), from the middle and under the waist
THIGH_HALF_CM, KNEE_HALF_CM, CALF_HALF_CM = 8.0, 5.2, 5.0
KNEE_BELOW_WAIST_CM = 60.0    # the trousers template's knee
CALF_BELOW_KNEE_CM = 13.0

HAT_ABOVE_NECK_CM = CHIN_CM + HEAD_H_CM - 9.0   # where a hat sits on the head, above the base of the neck
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
class Body:
    """The wearer, in the figure's coordinates: paths for the torso (with the neck, up under the chin), the arms,
    the hands, the legs (down into the shoes), the ears, the head and the hair, and the detail lines (fingers, ears,
    and the face's features). Garments are drawn over it from the same anchors, so skin shows only where none
    covers it. `feet` are bare feet, when there are trousers but no shoes."""
    torso: str
    arms: list[str] = field(default_factory=list)
    hands: list[str] = field(default_factory=list)
    fingers: list[str] = field(default_factory=list)
    legs: list[str] = field(default_factory=list)
    ears: list[str] = field(default_factory=list)
    ear_lines: list[str] = field(default_factory=list)
    head: str = ""
    hair: str = ""
    hair_lines: list[str] = field(default_factory=list)
    face: list[tuple[str, str, float]] = field(default_factory=list)   # (path, colour, width); eyes are filled
    eyes: list[str] = field(default_factory=list)
    cut: float | None = None    # with no trousers, the torso is not drawn below this
    feet: tuple[FrontShoe, list] | None = None
    box: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)


@dataclass
class Layout:
    pieces: list[Placed] = field(default_factory=list)
    view: tuple[float, float, float, float] = (0.0, 0.0, 400.0, 600.0)   # x, y, width, height
    body: Body | None = None

    def fit(self) -> None:
        """The canvas: everything drawn, with MARGIN on every side."""
        boxes = [p.box() for p in self.pieces] + ([self.body.box] if self.body else [])
        boxes = boxes or [(CX - 100, NECK_Y, CX + 100, GROUND_Y)]
        x0, y0 = min(b[0] for b in boxes) - MARGIN, min(b[1] for b in boxes) - MARGIN
        x1, y1 = max(b[2] for b in boxes) + MARGIN, max(b[3] for b in boxes) + MARGIN
        self.view = (x0, y0, x1 - x0, y1 - y0)

    def get(self, place: str) -> Placed | None:
        return next((p for p in self.pieces if p.place == place), None)


def figure(pieces: Mapping[str, Piece | None] | None, *, uid: str = "f", face: bool = FACE) -> str:
    """The outfit as worn, as one SVG. `pieces` maps places (base, mid, outer, bottom, shoes) to pieces, and
    "accessories" to a list of pieces; a place that is missing or None is not drawn. With `face` the wearer's
    face has simple features; without, only the head's shape and hair. Never raises."""
    uid = item._uid(uid)
    try:
        return _svg(plan(pieces), uid, face)
    except Exception:
        log.exception("could not draw an outfit as worn")
        return _empty()


def plan(pieces: Mapping[str, Piece | None] | None) -> Layout:
    """Where each piece goes: the figure's geometry, without drawing it."""
    out = Layout()
    pieces = pieces if isinstance(pieces, Mapping) else {}
    for place in PLACES:
        if place == "shoes":
            continue
        made = _placed(place, pieces.get(place))
        if made is not None:
            out.pieces.append(made)
    made = _placed("shoes", pieces.get("shoes"))
    if made is not None:
        try:
            made = _stand(made, out)
            out.pieces.append(made)
        except Exception:
            log.exception("placing the shoes for an outfit failed")
    if any(p.place in TOP_PLACES or p.place == "bottom" for p in out.pieces):
        try:
            out.body = _body(out)
        except Exception:
            log.exception("placing the wearer for an outfit failed")
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
    trousers: under the wearer's legs, where a straight leg's hem would be."""
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
    is the left one mirrored. With trousers on, the wearer's ankle stands in each shoe (a bare foot in a sandal)."""
    left, right, _ = _legs(layout)
    if layout.get("bottom") is not None:
        shoes.front = front_shoe(shoes.spec, K_PX, sole_default=shoes.shape.sole_default, ankle=_ankle(), toes=TOE_LINE)
        shoes.shape = Shape(outline=shoes.front.outline, bbox=shoes.front.bbox, body_box=shoes.front.bbox,
                            anchors=dict(shoes.front.anchors), sole_default=shoes.shape.sole_default)
    shoes.transforms = _pair(shoes.shape.bbox, left, right)
    return shoes


def _pair(bbox, left: float, right: float) -> list[tuple[float, float, float, float, float, float]]:
    bx = (bbox[0] + bbox[2]) / 2
    y = GROUND_Y + TOE_CM * K_PX
    return [(1.0, 0.0, 0.0, 1.0, left - bx, y), (-1.0, 0.0, 0.0, 1.0, right + bx, y)]


def _ankle() -> str:
    """Skin in a shoe, drawn as the body is: its outline under its fill."""
    return (f'<path d="{{d}}" fill="none" stroke="{INK}" stroke-width="{2 * LINE}" stroke-linejoin="round"/>'
            f'<path d="{{d}}" fill="{SKIN}"/>')


# ------------------------------------------------------------------ the wearer

def _f(v: float) -> str:
    return f"{v:.1f}"


def _pt(q) -> str:
    return f"{_f(q[0])},{_f(q[1])}"


def _torso(top: float, short: bool = False) -> str:
    """The torso, from the neck (cut at `top`, under the chin) to the hips: the shoulders just inside every top's,
    the waist as wide as a worn belt (so a top tucked in under one shows nothing behind it), and it ends above the
    trousers' crotch. `short`: it ends at the waist, for a figure with no trousers."""
    k, n, w = K_PX, NECK_Y, WAIST_Y
    nw = NECK_HALF_CM * k
    waist = BELT_HALF_CM * k
    right = [("C", (CX + nw + 2, n + 10), (CX + 50, n + 15), (CX + 21 * k, n + 7.8 * k)),     # trapezius to the shoulder
             ("C", (CX + 23 * k, n + 9.5 * k), (CX + 21.5 * k, n + 17.5 * k), (CX + 17.6 * k, n + 20 * k)),   # the arm plate
             ("C", (CX + 17 * k, n + 30 * k), (CX + waist, w - 9 * k), (CX + waist, w)),     # down the side to the waist
             ("C", (CX + waist, w + 6 * k), (CX + 17.9 * k, w + 10 * k), (CX + 17.7 * k, w + 15 * k)),   # the hip
             ("C", (CX + 17.5 * k, w + 19 * k), (CX + 9 * k, w + 23.5 * k), (CX, w + 23.5 * k))]   # round under it
    if short:
        right = right[:3]

    def mirror(q):
        return (2 * CX - q[0], q[1])

    d = f"M {_f(CX + nw)},{_f(top)} L {_f(CX + nw)},{_f(n - 2)} "
    d += " ".join(f"C {_pt(a)} {_pt(b)} {_pt(c)}" for _, a, b, c in right)
    d += f" L {_pt(mirror(right[-1][3]))}"
    starts = [(CX + nw, n - 2)] + [seg[3] for seg in right[:-1]]
    for (_, a, b, _c), st in zip(reversed(right), reversed(starts), strict=True):
        a, b, st = mirror(b), mirror(a), mirror(st)
        d += f" C {_pt(a)} {_pt(b)} {_pt(st)}"
    return d + f" L {_f(CX - nw)},{_f(top)} Z"


def _ellipse(cx: float, cy: float, rx: float, ry: float, deg: float = 0.0) -> str:
    pts = []
    c, s_ = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    for i in range(24):
        a = 2 * math.pi * i / 24
        x, y = rx * math.cos(a), ry * math.sin(a)
        pts.append((cx + x * c - y * s_, cy + x * s_ + y * c))
    return "M " + " L ".join(_pt(q) for q in pts) + " Z"


def _numbers(d: str) -> list[tuple[float, float]]:
    return [(float(x), float(y)) for x, y in re.findall(r"(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)", d)]


def _mirror(d: str) -> str:
    """A path of absolute points, mirrored about the middle of the figure."""
    return re.sub(r"(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)", lambda m: f"{_f(2 * CX - float(m[1]))},{m[2]}", d)


def _curve(pts, closed: bool = False) -> str:
    """A smooth curve through the points (Catmull-Rom, as cubic Béziers)."""
    n = len(pts)
    out = f"M {_pt(pts[0])}"
    for i in range(n if closed else n - 1):
        p0, p1 = pts[(i - 1) % n if closed else max(i - 1, 0)], pts[i]
        p2, p3 = pts[(i + 1) % n], pts[(i + 2) % n if closed else min(i + 2, n - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        out += f" C {_pt(c1)} {_pt(c2)} {_pt(p2)}"
    return out + (" Z" if closed else "")


def _tube(centres, halves, steps: int = 8) -> str:
    """A limb along the points `centres`, `halves` wide either side of them, rounded at its start (which is hidden
    in a garment or the torso) and cut straight across at its end (a hand or a shoe covers it)."""
    pts, hs = [], []
    for i in range(len(centres) - 1):
        (x0, y0), (x1, y1) = centres[i], centres[i + 1]
        for j in range(steps):
            t = j / steps
            pts.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
            hs.append(halves[i] + (halves[i + 1] - halves[i]) * t)
    pts.append(centres[-1])
    hs.append(halves[-1])
    left, right, normals = [], [], []
    for j, (x, y) in enumerate(pts):
        a, b = pts[max(j - 1, 0)], pts[min(j + 1, len(pts) - 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        m = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / m, dx / m
        normals.append((nx, ny, dx / m, dy / m))
        left.append((x + nx * hs[j], y + ny * hs[j]))
        right.append((x - nx * hs[j], y - ny * hs[j]))
    nx, ny, dx, dy = normals[0]
    (x, y), h = pts[0], hs[0]
    cap = [(x + h * (-nx * math.cos(a) - dx * math.sin(a)), y + h * (-ny * math.cos(a) - dy * math.sin(a)))
           for a in (math.pi * i / 8 for i in range(1, 8))]
    return "M " + " L ".join(_pt(q) for q in left + right[::-1] + cap) + " Z"


def _unit(dx: float, dy: float) -> tuple[float, float]:
    m = math.hypot(dx, dy) or 1.0
    return dx / m, dy / m


@dataclass
class _Sleeve:
    shoulder: tuple[float, float]
    down: tuple[float, float]       # along the sleeve, away from the shoulder
    out: tuple[float, float]        # across it, towards its upper (outer) edge
    reach: float                    # how far it reaches along `down` from the shoulder point
    cuff: tuple[float, float]       # the middle of its opening
    half: float                     # half the opening's width


def _sleeve(top: Placed) -> _Sleeve | None:
    """The sleeve on the viewer's left of `top`, in the figure."""
    if "shoulder_l" not in top.shape.anchors:
        return None
    sh = top.point(top.shape.anchors["shoulder_l"])
    for path, deg in top.shape.sleeves:
        pts = [top.point(q) for q in _numbers(path)]
        if not pts or sum(x for x, _ in pts) / len(pts) >= CX:
            continue
        t = math.radians(abs(deg))
        ux, uy = -math.sin(t), math.cos(t)
        vx, vy = -uy, ux
        along = [((x - sh[0]) * ux + (y - sh[1]) * uy, (x - sh[0]) * vx + (y - sh[1]) * vy) for x, y in pts]
        reach = max(a for a, _ in along)
        cuff = [c for a, c in along if a > reach - 6]
        mid, half = (min(cuff) + max(cuff)) / 2, (max(cuff) - min(cuff)) / 2
        return _Sleeve(sh, (ux, uy), (vx, vy), reach, (sh[0] + ux * reach + vx * mid, sh[1] + uy * reach + vy * mid), half)
    return None


def _rank(p: Placed) -> int:
    return SLEEVE_RANK.get(p.spec.params.get("sleeve", "long"), 4)


# a relaxed hand hanging from the wrist (0, 0) down its length (+y), its thumb towards the body (+x), in cm
HAND = [(-2.5, 0.0), (-3.0, 3.0), (-3.4, 6.4), (-3.3, 10.0), (-2.8, 13.8), (-1.3, 15.9), (0.7, 16.0), (2.1, 14.2),
        (2.6, 11.4), (3.2, 11.2), (3.7, 10.0), (3.5, 7.6), (2.9, 5.0), (2.5, 2.6), (2.5, 0.0)]
FINGERS = [[(-1.3, 10.6), (-1.4, 13.0), (-1.2, 15.2)], [(0.6, 10.8), (0.6, 13.1), (0.8, 15.3)], [(1.9, 7.8), (2.3, 9.6), (2.6, 11.3)]]


def _arm(layout: Layout) -> tuple[str, str, list[str]]:
    """The viewer's left arm with its hand, and the hand's finger lines. It follows the sleeve of the outermost top
    with the longest sleeves: down its middle to the cuff (the hand comes out of it), or, below a short sleeve, to
    the elbow inside it and then hanging nearly straight down. With no sleeve it hangs a little out from the body."""
    k = K_PX
    tops = [p for p in layout.pieces if p.place in TOP_PLACES]
    sleeve = None
    sh = (CX - 23 * k, 80.0 + TOP_DY)
    if tops:
        best = max(_rank(p) for p in tops)
        top = [p for p in tops if _rank(p) == best][-1]
        sleeve = _sleeve(top) if best > 0 else None
        if "shoulder_l" in top.shape.anchors:
            sh = top.point(top.shape.anchors["shoulder_l"])
    a = (sh[0] + SHOULDER_IN_CM * k, sh[1] + SHOULDER_IN_CM * k)
    ra, re_, rw = ARM_HALF_CM * k, ELBOW_HALF_CM * k, WRIST_HALF_CM * k
    if sleeve is not None and sleeve.reach >= (ELBOW_CM - 2) * k:
        c = sleeve.cuff
        length = math.hypot(c[0] - a[0], c[1] - a[1])
        d = _unit(c[0] - a[0], c[1] - a[1])
        wl = max(length - 1.0 * k, WRIST_CM * k)
        if wl <= length:   # the wrist in the cuff: no wider than it
            rw = min(rw, sleeve.half * 0.75)
            re_ = min(re_, max(rw, sleeve.half * 0.9))
        el = min(ELBOW_CM * k, wl * 0.55)
        e = (a[0] + d[0] * el, a[1] + d[1] * el)
        w = (a[0] + d[0] * wl, a[1] + d[1] * wl)
        f = d
    else:
        if sleeve is not None:   # aim for the underside of the opening, so the arm hangs as low as the sleeve lets it
            shift = max(0.0, sleeve.half - re_ - 1.5 * k) * 0.5
            tx, ty = sleeve.cuff[0] - sleeve.out[0] * shift, sleeve.cuff[1] - sleeve.out[1] * shift
            d = _unit(tx - a[0], ty - a[1])
        else:
            d = (-math.sin(math.radians(BARE_ARM_DEG)), math.cos(math.radians(BARE_ARM_DEG)))
        e = (a[0] + d[0] * ELBOW_CM * k, a[1] + d[1] * ELBOW_CM * k)
        f = (-math.sin(math.radians(FOREARM_DEG)), math.cos(math.radians(FOREARM_DEG)))
        w = (e[0] + f[0] * (WRIST_CM - ELBOW_CM) * k, e[1] + f[1] * (WRIST_CM - ELBOW_CM) * k)
    arm = _tube([a, e, w], [ra, re_, rw])
    h = _unit(f[0] * 0.7, f[1] * 0.7 + 0.3)        # the hand hangs a little straighter than the forearm
    p = (h[1], -h[0])

    def put(q):
        return (w[0] + (q[0] * p[0] + q[1] * h[0]) * k, w[1] + (q[0] * p[1] + q[1] * h[1]) * k)

    hand = _curve([put(q) for q in HAND], closed=True)
    fingers = [_curve([put(q) for q in line]) for line in FINGERS]
    return arm, hand, fingers


def _leg_paths(ends) -> list[str]:
    """The legs, from the hips (inside the trousers) down to each ankle in its shoe: `ends` are the ankles' middles
    and half widths, the viewer's left one first."""
    k = K_PX
    out = []
    for side, (end, rend) in zip((-1, 1), ends, strict=True):
        top = (CX + side * HIP_CM * k, WAIST_Y + HIP_DOWN_CM * k)

        def at(y, top=top, end=end):
            t = (y - top[1]) / ((end[1] - top[1]) or 1.0)
            return (top[0] + (end[0] - top[0]) * t, y)

        knee = WAIST_Y + KNEE_BELOW_WAIST_CM * k
        calf = knee + CALF_BELOW_KNEE_CM * k
        low = end[1] - 6 * k
        cs, hs = [top], [THIGH_HALF_CM * k]
        for y, r in ((knee, KNEE_HALF_CM * k), (calf, CALF_HALF_CM * k), (low, rend)):
            if top[1] < y < end[1] and y > cs[-1][1]:
                cs.append(at(y))
                hs.append(r)
        out.append(_tube(cs + [end], hs + [rend]))
    return out


# the head, in cm from its middle (y down): its shape, the hair, the ears and the face's features
HEAD = [(0.0, -11.75), (5.4, -10.4), (7.5, -6.2), (7.8, -1.5), (7.4, 3.0), (6.3, 6.9), (4.3, 9.9), (1.9, 11.6)]
HAIR_TOP = [(7.7, -2.2), (8.3, -5.6), (7.8, -9.6), (4.9, -12.7), (0.4, -13.7), (-4.6, -13.0), (-7.9, -9.9),
            (-8.4, -5.6), (-7.7, -2.2)]
HAIRLINE = [(-7.0, -2.6), (-6.8, -5.6), (-4.6, -7.4), (-1.6, -7.9), (0.9, -7.0), (3.4, -7.8), (6.0, -7.0),
            (7.0, -5.4), (7.0, -2.6)]
HAIR_LINES = [[(-1.6, -7.9), (-2.6, -10.2), (-2.2, -12.6)], [(0.9, -7.0), (1.6, -9.6), (3.4, -12.0)],
              [(-4.6, -7.4), (-6.0, -9.4), (-6.2, -11.0)]]


def _head(body: Body, chin: float) -> None:
    k = K_PX
    cy = chin - HEAD_H_CM / 2 * k

    def at(q):
        return (CX + q[0] * k, cy + q[1] * k)

    shape = HEAD + [(-x, y) for x, y in reversed(HEAD[1:])]
    shape = [q for q in shape if q != (0.0, 11.75)]
    body.head = _curve([at(q) for q in shape], closed=True)
    body.hair = _curve([at(q) for q in HAIR_TOP]) + " L" + _curve([at(q) for q in HAIRLINE])[1:] + " Z"
    body.hair_lines = [_curve([at(q) for q in line]) for line in HAIR_LINES]
    for s in (-1, 1):
        ex, ey = at((s * 7.5, 0.6))
        body.ears.append(_ellipse(ex, ey, 1.25 * k, 2.7 * k, -s * 8))
        body.ear_lines.append(_curve([at((s * 7.8, -1.0)), at((s * 8.3, 0.5)), at((s * 7.8, 2.2))]))
        x, y = at((s * 3.0, -0.3))
        body.eyes.append(_ellipse(x, y, 0.55 * k, 0.75 * k))
        body.face.append((_curve([at((s * 1.7, -2.5)), at((s * 3.0, -3.1)), at((s * 4.5, -2.6))]), HAIR, 2.2))
    body.face.append((_curve([at((0.3, 0.9)), at((0.9, 3.3)), at((0.4, 4.0)), at((-0.7, 4.0))]), SKIN_LINE, 1.5))
    body.face.append((_curve([at((-2.1, 6.6)), at((0.0, 7.3)), at((2.1, 6.6))]), SKIN_LINE, 1.8))


def _body(layout: Layout) -> Body:
    """The wearer, placed from the same points as the clothes."""
    k = K_PX
    chin = NECK_Y - CHIN_CM * k
    bottom = layout.get("bottom")
    body = Body(_torso(chin - 2 * k, short=bottom is None))
    arm, hand, fingers = _arm(layout)
    body.arms, body.hands = [arm, _mirror(arm)], [hand, _mirror(hand)]
    body.fingers = fingers + [_mirror(d) for d in fingers]
    _head(body, chin)
    pts = []
    if bottom is not None:
        shoes = layout.get("shoes")
        if shoes is not None and shoes.front is not None:
            fs, tr = shoes.front, shoes.transforms
        else:   # no shoes: bare feet
            fs = bare_feet(k, ankle=_ankle(), toes=TOE_LINE)
            tr = _pair(fs.bbox, *_legs(layout)[:2])
            body.feet = (fs, tr)
            x0, y0, x1, y1 = fs.bbox
            pts += [(t[0] * x + t[4], y + t[5]) for t in tr for x in (x0, x1) for y in (y0, y1)]
        half = abs(fs.anchors["ankle_r"][0] - fs.anchors["ankle"][0])
        ends = []
        for t in tr:
            x, y = fs.anchors["ankle"]
            ends.append(((t[0] * x + t[4], y + t[5]), half))
        body.legs = _leg_paths(ends)
    for d in [body.torso, body.head, body.hair] + body.arms + body.hands + body.legs + body.ears:
        pts += _numbers(d)
    body.box = (min(x for x, _ in pts) - LINE, min(y for _, y in pts) - LINE,
                max(x for x, _ in pts) + LINE, max(y for _, y in pts) + LINE)
    return body


def _skin(paths: list[str]) -> str:
    """Skin, as one outline round all of `paths` together: every outline first, then every fill over them."""
    return ("".join(f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="{2 * LINE}" stroke-linejoin="round"/>' for d in paths)
            + "".join(f'<path d="{d}" fill="{SKIN}"/>' for d in paths))


def _lines(paths: list[str], colour: str = SKIN_LINE, width: float = 1.5) -> str:
    return "".join(f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="{width}" stroke-linecap="round"/>' for d in paths)


def _body_markup(body: Body) -> str:
    """Everything of the wearer but the head, drawn before the clothes: the legs, the arms and hands, the torso;
    and bare feet."""
    out = _skin(body.legs + body.arms + body.hands + [body.torso]) + _lines(body.fingers)
    if body.feet is not None:
        fs, tr = body.feet
        out += "".join(f'<g transform="{_matrix(t)}">{fs.body}</g>' for t in tr)
    return out


def _head_markup(body: Body, face: bool) -> str:
    """The head, drawn over the clothes (a hood or a collar at the back is behind it): ears, head, hair, and with
    `face` the eyes, brows, nose and mouth."""
    out = _skin(body.ears + [body.head]) + _lines(body.ear_lines, width=1.4)
    out += f'<path d="{body.hair}" fill="{HAIR}" stroke="{INK}" stroke-width="2.4" stroke-linejoin="round"/>'
    out += _lines(body.hair_lines, shade(HAIR, 0.3), 1.3)
    if face:
        out += "".join(f'<path d="{d}" fill="{EYE}"/>' for d in body.eyes)
        out += "".join(_lines([d], c, w) for d, c, w in body.face)
    return out


def _neck_front(body: Body, first: Placed, cid: str, defs: list[str]) -> str:
    """The neck again over the tops, no wider than the neck (with its outline): above the innermost top's neck
    opening, and on down inside the opening a little way. What is drawn there is the back of a neckline or of a
    collar's band, which is behind the neck."""
    holes = [part.d for part in first.shape.parts if part.role == "hole"]
    if not holes:
        return ""
    cut = min(first.point(q)[1] for d in holes for q in _numbers(d)) + LINE + 1.0
    nw = NECK_HALF_CM * K_PX + LINE + 0.5
    top = NECK_Y - CHIN_CM * K_PX - 4 * K_PX
    if cut <= top:
        return ""
    low = cut + NECK_IN_CM * K_PX
    defs.append(f'<clipPath id="{cid}"><rect x="{CX - nw:.1f}" y="{top:.1f}" width="{2 * nw:.1f}" height="{low - top:.1f}"/></clipPath>')
    defs.append(f'<clipPath id="{cid}h"><rect x="{CX - nw:.1f}" y="{top:.1f}" width="{2 * nw:.1f}" height="{cut - top:.1f}"/>'
                + "".join(f'<path d="{d}" transform="{_matrix(first.transforms[0])}"/>' for d in holes) + "</clipPath>")
    return f'<g clip-path="url(#{cid})"><g clip-path="url(#{cid}h)">{_skin([body.torso])}</g></g>'


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


def _svg(layout: Layout, uid: str, face: bool = FACE) -> str:
    defs: list[str] = []
    body: list[str] = []
    wearer = layout.body
    if wearer is not None:   # the wearer first, behind everything
        body.append(f'<g id="{uid}m">{_body_markup(wearer)}</g>')
    shoes, bottom = layout.get("shoes"), layout.get("bottom")
    if shoes is not None:
        front = front_shoe(shoes.spec, K_PX, sole_default=shoes.shape.sole_default, uid=f"{uid}s",
                           ankle=_ankle() if shoes.front is not None and shoes.front.ankle else None, toes=TOE_LINE)
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
    # what the wearer shows inside the neck of the innermost top: the neck and the top of the chest, in the top's
    # own coordinates
    neck = chest = torso = ""
    if wearer is not None:
        torso = _skin([wearer.torso])
        cut = f"{uid}c"
        defs.append(f'<clipPath id="{cut}"><rect x="-4000" y="-4000" width="8000" '
                    f'height="{4000 + NECK_Y + 30 * K_PX:.1f}"/></clipPath>')
        chest = f'<g clip-path="url(#{cut})">{torso}</g>'
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
            if not stack and wearer is not None:   # nothing under it: the chest shows in the opening, the trousers over it
                seen = torso + (f'<use href="#{uid}w"/>' if lower else "")
            else:   # the neck stands in front of this one's collar at the back, behind what is under it
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
    if wearer is not None:
        if first is not None:
            body.append(_neck_front(wearer, first, f"{uid}f", defs))
        body.append(_head_markup(wearer, face))
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


