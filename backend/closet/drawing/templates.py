"""Parametric garment shapes.

Each template turns a handful of coarse parameters (the same small vocabulary
the attributes use) into geometry on a shared 400 x 460 canvas. Because the
shape is a pure function of the attributes, redrawing after a correction is
free and deterministic, and every item of a category shares anchor points
(shoulders, waist, hem) that the mannequin view can line up later.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from ..tagger.taxonomy import SHOE_STYLES  # shared with the tagger

W, H = 400, 460
CX = 200.0
CX_ROT = (200, 120)  # patterns and a sleeve's cloth are turned about the middle of the chest


@dataclass
class Part:
    d: str
    role: str  # trim | hole | sole | band | cuff | collar_r | collar_l | edge (a stroke with no fill) | inlay | stitch | fade | shine
    color: str | None = None   # inlay/stitch: "trim" | "lace" | "sole" | "sole_line" | a hex; None = the body's cloth
    clip: bool = False         # drawn inside the outline only (an inlay may be drawn oversize and cut by the edge)


@dataclass
class Shape:
    outline: str
    parts: list[Part] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    dots: list[tuple[float, float, float]] = field(default_factory=list)
    body_box: tuple[float, float, float, float] = (0, 0, W, H)
    bbox: tuple[float, float, float, float] = (0, 0, W, H)
    anchors: dict[str, tuple[float, float]] = field(default_factory=dict)
    behind: list[Part] = field(default_factory=list)
    sleeves: list[tuple[str, float]] = field(default_factory=list)  # (path, degrees the cloth is turned)
    seams: list[str] = field(default_factory=list)  # thin lines on the body that parts (a collar) lie over
    folds: list[str] = field(default_factory=list)  # soft drape wrinkles of a light cloth, fainter than a seam
    sole_default: str | None = None  # the sole's colour when the photo gives none (leather shoes: dark brown)
    snaps: list[tuple[float, float, float]] = field(default_factory=list)  # press studs: a ring round a cap, not a button
    # colour-blocking: regions of the body (a yoke) painted in the second colour, clipped by the outline, and
    # whether the sleeves are cut in it too. Parts in the second colour have color "block".
    blocks: list[str] = field(default_factory=list)
    block_sleeves: bool = False
    # worn open: (the edge of the front that lies on top, the viewer's right one, as a run of points from the
    # neck to below the hem; how its buttonholes are cut, "vertical" or "horizontal"). The other front is its
    # mirror image. The renderer builds the two fronts from this and swings them open.
    fronts: tuple[list, str] | None = None
    tailored: bool = False   # a tailored jacket or coat: its buttons and inside are drawn to stand out on any cloth


def _f(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def _pt(p) -> str:
    return f"{_f(p[0])},{_f(p[1])}"


def _mirror(p):
    return (2 * CX - p[0], p[1])


# --------------------------------------------------------------------- tops

TOP_DEFAULTS = dict(
    sleeve="long",      # none | short | elbow | three-quarter | long
    neck="crew",        # crew | v | collar | hood | turtle | scoop | boat | mock | roll | shawl
    length="regular",   # cropped | regular | long | knee
    fit="regular",      # slim | tailored | regular | relaxed | boxy | oversized
    front="none",       # none | buttons | half | zip | quarter-zip | half-zip | french | hidden | popover | double
    pockets="none",     # none | chest | chest-two | low | chest-low | kangaroo, and the finer ones listed below
    hem="straight",     # straight | curved | rib | vents | tennis | raw
    cuffs="plain",      # plain | rib | button | button2 | french | mitred | snap3 | open | rolled | roll-tab
    buttons=None,       # how many buttons show on the front; None = the usual number for this front
    neck_detail="none",  # none | v-insert (the stitched triangle under a sweatshirt's collar)
    shoulder="set-in",  # set-in | raglan | drop | saddle | dolman
)
# Optional details, each read off a photo or the taxonomy (absent = the plain shape above):
#   state     closed | open   worn unfastened, the two fronts hanging apart (only garments that open all the
#             way down the front: buttons, zip, double-breasted, cardigans, jackets)
#   collar    with neck="collar", the kind of collar:
#             point | semi_spread | spread | cutaway | button_down | hidden_button_down | club | tab | pin | western
#             (a woven shirt collar on a stand; default semi_spread on a button front)
#             knit (a polo's soft collar; default otherwise) | johnny | rugby
#             band | stand | wing | rib (stand collars with no leaves; rib = a bomber's knitted one)
#             camp | notch | peak | shawl (open collars that roll into lapels or revers)
#   v_depth   shallow | regular | deep     how far a V neck drops
#   fastener  button | snap                what closes the front (snaps: a ring round a cap)
#   armhole   tank | vest                  sleeveless: a tank's narrow straps, or a sweater vest's ribbed armholes
#   yoke      plain | western | none       a shirt's front yoke seam (default: plain on a woven shirt collar)
#   weight    lightweight | midweight | heavyweight | super_heavy   how thick the cloth is: bulk, edge depth
#   gauge     extra_fine | fine | medium | chunky | super_chunky     knit gauge: the depth of rib bands
#   binding   False | True             a contrast strip wrapped over the edges: the collar's top, the placket, the
#             sleeve ends and the hem (role "binding" inside the garment, "binding_edge" on its outline)
#   colorblock  a tuple of parts cut in the second colour: yoke | sleeves | collar | pocket
#   stripes   none | sleeve | hoops    two stripes down the outside of each sleeve (a track jacket), or stripes round
#             the arms and the body above the hem (a hockey jersey); in the trim colour
#   belt      False | True | sash      a self belt buckled round the waist (a trench coat); a robe's knotted sash
# Finer pocket values: chest-flap | chest-patch-two | pencil | western | welt | split | slash | chore |
#   chest-flap-two | guayabera | bellows | utility | hip-patch | hip-flap

# A garment laid flat is wider than it looks worn: the cloth that wraps round the body lies out to the
# sides. Drawn at its full flat width a top reads as too wide, so the body is drawn at this share of it.
BODY_W = 0.84
K_PX = 3.3   # canvas px per cm: a 56 cm chest is 185 px, and long sleeves hanging beside it still fit the card
# Flat measurements of real garments, men's M / 40R, regular fit, in cm: shoulder seam to seam, chest
# pit to pit, waist, hem, back length from the collar seam, sleeve from the shoulder seam, bicep and
# cuff (flat), short sleeve length and opening, and how far the underarm sits below the shoulder.
BLOCKS = {
    "shirt": dict(sh=46, chest=56, waist=53, hem=55, length=76, sleeve=65, bicep=20, cuff=11.5, short=25, short_open=17, depth=22),
    "tee": dict(sh=46, chest=53, waist=52, hem=53, length=71, sleeve=64, bicep=18, cuff=10, short=21, short_open=18, depth=21),
    "polo": dict(sh=46, chest=54, waist=53, hem=54, length=72, sleeve=63, bicep=19, cuff=10, short=22, short_open=16.5, depth=21),
    "knit": dict(sh=47, chest=55, waist=53, hem=53, length=68, sleeve=64, bicep=19, cuff=10, short=21, short_open=17, depth=22),
    "outer": dict(sh=47, chest=58, waist=57, hem=58, length=74, sleeve=65, bicep=21, cuff=13, short=25, short_open=19, depth=23),
    "bomber": dict(sh=47, chest=60, waist=58, hem=55, length=66, sleeve=65, bicep=21, cuff=11, short=25, short_open=19, depth=24),
    "jacket": dict(sh=46.5, chest=54.5, waist=50, hem=55, length=75, sleeve=64, bicep=19, cuff=13.5, short=25, short_open=19,
                   depth=22, waist_at=44),
    "coat": dict(sh=48, chest=60, waist=57, hem=62, length=82, sleeve=66, bicep=21, cuff=15, short=25, short_open=20, depth=24),
}
# cm added to (shoulder, chest, waist, hem, bicep, length) by the fit; from the same garments in other cuts
FIT_DELTA = {
    "slim": (-1, -4, -5, -3, -1.5, 0), "tailored": (-0.5, -3, -6, -2, -1.5, 0), "regular": (0, 0, 0, 0, 0, 0),
    "relaxed": (1.5, 4, 5, 4, 1.5, 0), "boxy": (3, 6, 8, 7, 2, -6), "oversized": (8, 8, 10, 9, 3, 3),
}
FITS = tuple(FIT_DELTA)
# A tailored jacket is cut close already: "tailored" is the measured 40R jacket itself and the other fits
# are eased from it, cm added to (chest, waist, hem, bicep, length) of the jacket or coat block.
JACKET_FIT = {
    "slim": (-2, -2.5, -2, -1, -1), "tailored": (0, 0, 0, 0, 0), "regular": (1.5, 2.5, 1.5, 0.5, 0),
    "relaxed": (4, 6, 4, 1.5, 0), "boxy": (6, 10, 7, 2, -4), "oversized": (8, 12, 9, 3, 3),
}
# Where a tailored front is built, in cm below the collar seam at the high shoulder point: the gorge,
# the fastening button and the space between buttons, the hip pockets, the lapel's widest point
# (single, double-breasted) and the breast pocket.
TAILORING = {
    "jacket": dict(gorge=9.5, stance=47, spacing=10.5, db_stance=44, db_spacing=11, pocket=57.5, lapel=8.25, db_lapel=10,
                   breast=23),
    "coat": dict(gorge=10.5, stance=40, spacing=13, db_stance=40, db_spacing=12, pocket=70, lapel=9.5, db_lapel=12,
                 breast=24),
}
WEIGHT_LEVEL = {"lightweight": 0, "midweight": 1, "heavyweight": 2, "super_heavy": 3}
# A tailored sleeve hangs close to the body: at most SLEEVE_HANG degrees from the vertical, its cuff at
# least SLEEVE_GAP px clear of the side; the underarm is rounded over UNDERARM px so the sleeve's and the
# body's outlines part cleanly instead of running into a dark wedge. Cuff buttons: CUFF_BUTTON px radius.
SLEEVE_HANG, SLEEVE_GAP, UNDERARM, CUFF_BUTTON = 19.0, 14.0, 18.0, 2.7
LAPEL_GROW = 0.4                                    # cm of lapel width for each cm of chest a fuller fit adds
GAUGE_BAND = {"extra_fine": 0.8, "fine": 0.9, "medium": 1.0, "chunky": 1.25, "super_chunky": 1.5}

# Shirt collar leaves: where the point lies from the place the leaves meet (dx, dy), and how the point is finished.
LEAVES = {
    "semi_spread": (25, 23, "sharp"), "point": (18, 30, "sharp"), "spread": (30, 16, "sharp"), "cutaway": (33, 8.5, "sharp"),
    "button_down": (21, 27, "roll"), "hidden_button_down": (21, 27, "roll"), "club": (24, 22, "club"),
    "tab": (10, 29, "sharp"), "pin": (19, 29, "sharp"), "western": (23, 37, "sharp"),
    "knit": (27, 18.5, "sharp"), "johnny": (32, 15, "sharp"), "rugby": (25, 20, "sharp"),
}
BAND_COLLARS = ("band", "stand", "wing", "rib")
LAPEL_COLLARS = ("camp", "notch", "peak", "shawl")


def _cubic_x_at_y(p0, p1, p2, p3, y: float) -> float:
    """x of a downward-running cubic bezier at height y."""
    lo, hi = 0.0, 1.0
    for _ in range(40):
        t = (lo + hi) / 2
        yy = (1 - t) ** 3 * p0[1] + 3 * (1 - t) ** 2 * t * p1[1] + 3 * (1 - t) * t * t * p2[1] + t ** 3 * p3[1]
        lo, hi = (t, hi) if yy < y else (lo, t)
    t = (lo + hi) / 2
    return (1 - t) ** 3 * p0[0] + 3 * (1 - t) ** 2 * t * p1[0] + 3 * (1 - t) * t * t * p2[0] + t ** 3 * p3[0]


def _bez(p0, p1, p2, p3, n=12):
    """Points along a cubic, p0 excluded."""
    out = []
    for i in range(1, n + 1):
        t = i / n
        a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
        out.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return out


def _qbez(p0, p1, p2, n=10):
    """Points along a quadratic, p0 excluded."""
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]) for t in (i / n for i in range(1, n + 1))]


def _poly(pts, close=True) -> str:
    return "M " + " L ".join(_pt(q) for q in pts) + (" Z" if close else "")


def _unit(v):
    ln = math.hypot(*v) or 1.0
    return (v[0] / ln, v[1] / ln)


def _rot(v, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c)


def _clip_half(poly, a, b, keep):
    """The part of a polygon on the same side of the line a-b as the point `keep` (Sutherland-Hodgman)."""
    side = lambda q: (b[0] - a[0]) * (q[1] - a[1]) - (b[1] - a[1]) * (q[0] - a[0])
    sk = side(keep)
    inside = lambda q: side(q) * sk >= 0
    out = []
    for i, cur in enumerate(poly):
        prev = poly[i - 1]
        if inside(cur):
            if not inside(prev):
                out.append(_cross(prev, cur, a, b))
            out.append(cur)
        elif inside(prev):
            out.append(_cross(prev, cur, a, b))
    return out


def _clip_run(run, a, b, keep):
    """An open polyline cut to the side of the line a-b where `keep` lies (the first visible stretch)."""
    side = lambda q: (b[0] - a[0]) * (q[1] - a[1]) - (b[1] - a[1]) * (q[0] - a[0])
    sk = side(keep)
    out = []
    for i, cur in enumerate(run):
        ins = side(cur) * sk >= 0
        if i and ins != (side(run[i - 1]) * sk >= 0):
            out.append(_cross(run[i - 1], cur, a, b))
        if ins:
            out.append(cur)
    return out


def _cross(p, q, a, b):
    """Where the segment p-q crosses the line a-b."""
    d1 = (q[0] - p[0], q[1] - p[1])
    d2 = (b[0] - a[0], b[1] - a[1])
    den = d1[0] * d2[1] - d1[1] * d2[0] or 1e-9
    t = ((a[0] - p[0]) * d2[1] - (a[1] - p[1]) * d2[0]) / den
    return (p[0] + d1[0] * t, p[1] + d1[1] * t)


def _shrink(pts, k):
    """The same polyline pulled toward its centroid: a topstitch inside an edge."""
    cx = sum(q[0] for q in pts) / len(pts)
    cy = sum(q[1] for q in pts) / len(pts)
    return [(cx + (q[0] - cx) * k, cy + (q[1] - cy) * k) for q in pts]


def _offset_line(pts, dist):
    """A polyline moved sideways by dist (positive = to the left of its direction of travel, in screen space)."""
    out = []
    for i, q in enumerate(pts):
        a, b = pts[max(i - 1, 0)], pts[min(i + 1, len(pts) - 1)]
        t = _unit((b[0] - a[0], b[1] - a[1]))
        out.append((q[0] + t[1] * dist, q[1] - t[0] * dist))
    return out


def _mirror_path(d: str) -> str:
    """The same path mirrored about the centre line (every coordinate pair is written x,y)."""
    return re.sub(r"(-?[\d.]+),(-?[\d.]+)", lambda m: f"{_f(2 * CX - float(m.group(1)))},{m.group(2)}", d)


def _scallop(pts, spacing, amp, outward=1):
    """A near-vertical edge swelling between stitched channels every `spacing` px (a puffer's baffles)."""
    out = []
    for a, b in zip(pts, pts[1:]):
        n = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) / 2))
        for i in range(n):
            x = a[0] + (b[0] - a[0]) * i / n
            y = a[1] + (b[1] - a[1]) * i / n
            f = ((y - 0.8) % spacing) / spacing
            ease = min(1.0, (y - pts[0][1]) / 14)   # grows in from the underarm, so no sliver opens beside the sleeve
            out.append((x + outward * amp * ease * math.sin(math.pi * f), y))
    out.append(pts[-1])
    return out


def _scallop_run(a, b, spacing, amp, deg, outward):
    """Points from a to b (both excluded) swelling out by up to amp between the channels of a puffer's
    sleeve. The channels are the body's, turned by deg about CX_ROT with the sleeve's cloth, so the
    pinches fall on the stitched lines; outward is the unit direction the edge swells to."""
    r = math.radians(deg)
    n = max(2, int(math.dist(a, b) / 2))
    out = []
    for i in range(1, n):
        x, y = a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n
        py = math.sin(r) * (x - CX_ROT[0]) + math.cos(r) * (y - CX_ROT[1]) + CX_ROT[1]
        f = ((py - 0.8) % spacing) / spacing
        s = amp * math.sin(math.pi * f) * min(1.0, i / n * 8, (n - i) / n * 8)   # eased in at both ends
        out.append((x + outward[0] * s, y + outward[1] * s))
    return out


def _along(pts, dist):
    """The point dist px along a polyline from its first point, and the index of the next vertex after it."""
    for i in range(1, len(pts)):
        seg = math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
        if seg >= dist and i < len(pts) - 1:
            return _lerp(pts[i - 1], pts[i], dist / seg), i
        dist -= seg
    return pts[-2], len(pts) - 1


def _x_on(pts, y):
    """x of a mostly vertical polyline at height y."""
    for a, b in zip(pts, pts[1:]):
        if min(a[1], b[1]) <= y <= max(a[1], b[1]) and a[1] != b[1]:
            return a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1])
    return pts[0][0] if y < pts[0][1] else pts[-1][0]


def _block_for(p) -> str:
    """Which measured block a top is drawn from, when the caller did not say."""
    if p.get("block") in BLOCKS:
        return p["block"]
    cs = p.get("collar")
    if p["neck"] == "collar" and cs in ("notch", "peak", "shawl"):
        return "coat" if p["length"] == "knee" else "jacket"
    if p["neck"] == "collar" and cs in ("stand", "rib"):
        return "bomber" if p["hem"] == "rib" else "outer"
    if p["neck"] == "collar" and (cs in ("knit", "johnny", "rugby") or (cs is None and p["front"] not in
                                                                            ("buttons", "french", "hidden", "popover", "double"))):
        return "polo"
    if p["neck"] == "collar":
        return "shirt"
    if p["neck"] in ("turtle", "mock", "roll", "shawl", "hood") or p["hem"] == "rib":
        return "knit"
    return "tee"


def _side_points(A, W, Hc, n=10):
    """The side seam from the underarm through the waist to the hem corner, as points."""
    up = _bez(A, (A[0] + (W[0] - A[0]) * 0.5, A[1] + (W[1] - A[1]) * 0.45), (W[0], W[1] - (W[1] - A[1]) * 0.4), W, n)
    down = _bez(W, (W[0], W[1] + (Hc[1] - W[1]) * 0.4), (Hc[0] + (W[0] - Hc[0]) * 0.3, Hc[1] - (Hc[1] - W[1]) * 0.3), Hc, n)
    return [A] + up + down


def _seg_cross(p, q, a, b):
    """Where segment p-q meets segment a-b, or None."""
    d1 = (q[0] - p[0], q[1] - p[1])
    d2 = (b[0] - a[0], b[1] - a[1])
    den = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(den) < 1e-9:
        return None
    t = ((a[0] - p[0]) * d2[1] - (a[1] - p[1]) * d2[0]) / den
    s = ((a[0] - p[0]) * d1[1] - (a[1] - p[1]) * d1[0]) / den
    if 0 <= t <= 1 and 0 <= s <= 1:
        return (p[0] + d1[0] * t, p[1] + d1[1] * t), t
    return None


def _first_cross(path, poly):
    """The first point where the polyline `path` crosses the polyline `poly`: (point, index into path, index into poly)."""
    for i in range(len(path) - 1):
        for j in range(len(poly) - 1):
            hit = _seg_cross(path[i], path[i + 1], poly[j], poly[j + 1])
            if hit:
                return hit[0], i, j
    return None


def top(**kw) -> Shape:
    """A top, front view, as a fashion flat drawn from the flat measurements of real garments
    (BLOCKS, men's M / 40R, in cm), with the sleeves hanging over the sides of the body as they
    do on a garment laid out with its arms down."""
    p = {**TOP_DEFAULTS, **kw}
    fit = p["fit"] if p["fit"] in FIT_DELTA else "regular"
    block = _block_for(p)
    if block in TAILORING:   # a tailored jacket or coat is not a shirt with lapels: it has its own construction
        return _tailored(p, block)
    B = BLOCKS[block]
    dsh, dch, dwa, dhe, dbi, dle = FIT_DELTA[fit]
    wt = WEIGHT_LEVEL.get(p.get("weight"), 1)
    ease = (0.97, 1.0, 1.06, 1.12)[wt]               # a heavier cloth stands away from the body
    bulk = (-1.0, 0.0, 3.0, 6.0)[wt]
    bs = GAUGE_BAND.get(p.get("gauge"), 1.0) * (0.85, 1.0, 1.25, 1.5)[wt]   # depth of rib bands and cuffs
    k_ = K_PX
    jacket = block in ("jacket", "coat")
    chest = (B["chest"] + dch) / 2 * k_ * ease * BODY_W
    # The sleeves hang from the edge of the body: the shoulder point sits just outside the chest's width,
    # so the armhole runs down the body's edge and no sleeve lies over the body. (A real shoulder seam is
    # narrower than the chest; drawn that way, the arms start inside the shirt's width, which reads wrong.)
    hs = chest + 5 + (0.6, 0, 1.2, 2.4)[wt] / 2 * k_
    waist_w = (B["waist"] + dwa) / 2 * k_ * ease * BODY_W
    hh = (B["hem"] + dhe) / 2 * k_ * ease * BODY_W
    if p["hem"] == "rib" and block in ("knit", "bomber"):
        hh = min(hh, waist_w)                          # the rib draws the hem in
    length = B["length"] + dle
    length = {"cropped": length * 0.84, "long": length + 9, "knee": max(length + 30, 105)}.get(p["length"], length)
    sy = 77.0 if jacket else 80.0
    sleeve = p["sleeve"] if p["sleeve"] in ("none", "short", "elbow", "three-quarter", "long") else "long"
    cuffs = p["cuffs"]
    if cuffs in ("rolled", "roll-tab") and sleeve not in ("long", "three-quarter"):
        cuffs = "plain"
    sleeved = sleeve != "none"
    shoulder = p["shoulder"]
    front = p["front"]
    state = p.get("state", "closed")
    vest = not sleeved and p.get("armhole") == "vest"
    collar = p["neck"] == "collar" or p["neck"] == "shawl"
    shirt_front = front in ("buttons", "french", "hidden", "popover", "double")
    cs = None
    if p["neck"] == "shawl":
        cs = "shawl_knit"
    elif collar:
        cs = p.get("collar") or ("semi_spread" if shirt_front else "knit")
        if cs not in LEAVES and cs not in BAND_COLLARS and cs not in LAPEL_COLLARS:
            cs = "semi_spread" if shirt_front else "knit"
    leafy, banded, lapel = cs in LEAVES, cs in BAND_COLLARS, cs in LAPEL_COLLARS or cs == "shawl_knit"
    woven = (leafy and cs not in ("knit", "johnny", "rugby")) or cs in ("band", "wing", "camp")
    neck = p["neck"]
    nw, ny = (40.0, sy - (12.0 if jacket else 15.0)) if collar else (
        {"scoop": 36.0, "boat": 52.0}.get(neck, 30.0), 58.0 + (2 if neck == "boat" else 0))
    seam_y = ny if collar else 56.0                   # where the back length is measured from
    hy = seam_y + length * k_
    hy = min(hy, H - 30.0)                            # a knee-length coat is drawn a little short of true scale to stay on the card
    wy = seam_y + B.get("waist_at", 45) * k_
    ay = sy + B["depth"] * 1.3 * k_ + bulk * 0.5      # the underarm; drawn deeper than life so the sleeve has its width

    N = (CX + nw, ny)
    S = (CX + hs, sy)
    curved = p["hem"] == "curved"
    side_y = hy - (20 if curved else 0)
    Hc = (CX + hh, side_y)
    ul = math.hypot(S[0] - N[0], S[1] - N[1])
    u = ((S[0] - N[0]) / ul, (S[1] - N[1]) / ul)
    if sleeved and shoulder == "drop":   # the shoulder seam falls onto the arm
        S = (S[0] + u[0] * 14, S[1] + u[1] * 14)
    if not sleeved:
        chest = min(chest, hs + 6)
    Ab = (CX + chest, ay)                             # the body's real underarm: wider than the shoulder
    if shoulder == "dolman" and sleeved:
        ay = sy + (150 if sleeve in ("long", "three-quarter") else 104)
        Ab = (CX + max(chest, waist_w), ay)
    side = _side_points(Ab, (CX + waist_w, max(wy, ay + 20)), Hc)

    # ---- sleeves
    cuff = None
    seam = None   # the armhole seam: shoulder point, two control points, the visible underarm
    U = None      # where the sleeve's inner edge (or its hem) leaves the body's side
    A = Ab
    if not sleeved:
        if vest:   # a sweater vest: a wider shoulder and a ribbed armhole
            S = (CX + hs - 14, sy + 2)
            A = (CX + chest - 2, sy + 92)
            c1, c2 = (S[0] - 6, S[1] + 52), (A[0] - 26, A[1] - 4)
        else:      # a tank: narrow straps and a deep scooped armhole, not a tee with the sleeves cut off
            S = (N[0] + 26, ny + 9)
            A = (CX + chest - 4, sy + 84)
            c1, c2 = (S[0] + 2, S[1] + 52), (A[0] - 24, A[1] - 6)
        side = _side_points(A, (CX + waist_w, max(wy, A[1] + 20)), Hc)
        arm = f"C {_pt(c1)} {_pt(c2)} {_pt(A)}"
        armhole = (S, c1, c2, A)
        arm_pts_r = [S] + _bez(S, c1, c2, A, 12)
        side_from = side
    else:
        kind = "rolled" if cuffs in ("rolled", "roll-tab") else sleeve
        bicep = (B["bicep"] + dbi) * k_ * ease
        if kind == "long":
            th, ln, cw = (16.0 if jacket else 20.0), (B["sleeve"] + (2 if fit == "oversized" else 0)) * k_, B["cuff"] * 0.9 * k_ * ease
        elif kind == "three-quarter":
            th, ln, cw = 17.0, B["sleeve"] * 0.74 * k_, (B["cuff"] + 3) * k_ * ease
        elif kind in ("elbow", "rolled"):
            th, ln, cw = 24.0, B["sleeve"] * (0.5 if kind == "elbow" else 0.56) * k_, B["short_open"] * 0.92 * k_ * ease
        else:
            th, ln, cw = (44.0 if block in ("tee", "knit") else 38.0), B["short"] * k_, B["short_open"] * k_ * ease
        th += {"oversized": 3, "boxy": 2, "relaxed": 1}.get(fit, 0) + 2.0 * (wt - 1)
        if shoulder == "drop":
            ln -= 14
        r = (12 if sleeve == "short" else 9) * (0.6 if jacket else 1) + bulk * 1.2   # rounder in a thick cloth
        K = (S[0] + u[0] * r, S[1] + u[1] * r)
        w_top = bicep * (0.62 if kind == "long" else 0.7)
        for _ in range(40):
            thr = math.radians(th)
            d = (math.sin(thr), math.cos(thr))        # down the sleeve
            q = (-math.cos(thr), math.sin(thr))       # across it, toward the body
            Co = (K[0] + d[0] * ln, K[1] + d[1] * ln)
            Ci = (Co[0] + q[0] * cw, Co[1] + q[1] * cw)
            # every sleeve ends outside the body: none lies over it
            j = min(range(len(side)), key=lambda i: abs(side[i][1] - Ci[1]))
            ok = Ci[0] > side[j][0] + 5
            if Co[0] > 392:
                th = math.degrees(math.asin(max(0.0, min(1.0, (392 - K[0]) / ln))))
                thr = math.radians(th)
                d = (math.sin(thr), math.cos(thr))
                q = (-math.cos(thr), math.sin(thr))
                Co = (K[0] + d[0] * ln, K[1] + d[1] * ln)
                Ci = (Co[0] + q[0] * cw, Co[1] + q[1] * cw)
                break
            if ok:
                break
            th += 1.5
        th = thr
        P1 = (K[0] + d[0] * r, K[1] + d[1] * r)
        # the visible underarm: on the armhole, so the sleeve is w_top wide where it leaves the body
        A = Ab   # the sleeve leaves the body at the body's own underarm
        cuff = (Co, Ci, d)
        corner = [Co]
        if cuffs == "mitred" and kind in ("long", "three-quarter"):   # the cuff's open corner is cut on the slant
            dep = 22 + bulk
            corner = [(Co[0] - d[0] * dep * 0.3, Co[1] - d[1] * dep * 0.3), (Co[0] + q[0] * 6, Co[1] + q[1] * 6)]
        seam = (S, (S[0] - 3, S[1] + (A[1] - S[1]) * 0.35), (A[0] + 4, A[1] - (A[1] - S[1]) * 0.3), A)
        # where the sleeve leaves the body: along its inner edge, or along its hem if the cuff lies over the body
        under = [A, Ci] + corner[::-1]
        hit = _first_cross(under, side) if shoulder != "dolman" else None
        if hit:
            U, i_u, j_u = hit
            sleeve_run = under[i_u + 1:][::-1] if i_u else []
            # silhouette: ... corner -> (Ci if the crossing is on the hem) -> U -> down the side
            sil = [v for v in corner] + ([Ci] if i_u == 0 else []) + [U]
            side_from = [U] + side[j_u + 1:]
            over = under[:i_u + 1] + [U]          # the part of the sleeve's edge lying over the body
            sh_over = over
        else:
            sil = corner + [Ci, A]
            side_from = side
            sh_over = None
        puff, puff_in = [], []   # a puffer's sleeve swells between its channels on both edges, down to the cuff
        if p.get("quilting") == "baffle":
            amp = 3.2 + bulk * 0.3
            cuff_d = {"rib": 17 * bs, "button": 22 + bulk, "button2": 22 + bulk, "convertible": 22 + bulk, "mitred": 22 + bulk, "french": 28 + bulk,
                      "snap3": 31 + bulk}.get(cuffs, 0) if kind in ("long", "three-quarter") else 0
            end = (Co[0] - d[0] * cuff_d, Co[1] - d[1] * cuff_d)
            puff = _scallop_run(P1, end, 32.0, amp, math.degrees(thr), (d[1], -d[0])) + [end]
            if Ci in sil:   # the inner edge, from the top of the cuff up to where it meets the body
                Bi_ = _lerp(Ci, A, min(0.9, cuff_d / max(1.0, math.dist(Ci, A))))
                puff_in = [Bi_] + _scallop_run(Bi_, A, 32.0, amp, math.degrees(thr), (-d[1], d[0]))
                i_c = sil.index(Ci) + 1
                nxt = sil[i_c] if i_c < len(sil) else A
                puff_in = [v for v in puff_in if math.dist(Ci, v) < math.dist(Ci, nxt) - 10]
                sil = sil[:i_c] + puff_in + sil[i_c:]
        arm = f"Q {_pt(K)} {_pt(P1)} L " + " L ".join(_pt(v) for v in puff + sil)
        arm_pts_r = None

    # ---- outline, clockwise from the right neck point
    hem_dip = 5
    vents = p["hem"] in ("vents", "tennis")
    side_pts = list(side_from)
    if curved:
        hem = f"C {_pt((CX + hh - 48, side_y + 27))} {_pt((CX - hh + 48, side_y + 27))} {_pt(_mirror(Hc))}"
        hem_bottom = side_y + 20.25
    elif vents:
        # side vents: the front's corner turns in a little where the side seam opens
        Vt, Vb = (CX + hh, hy - 20), (CX + hh - 4, hy)
        side_pts = [v for v in side_pts if v[1] < hy - 20] + [Vt, Vb]
        hem = f"Q {_pt((CX, hy + hem_dip))} {_pt(_mirror(Vb))}"
        hem_bottom = hy + hem_dip / 2
    else:
        hem = f"Q {_pt((CX, hy + hem_dip))} {_pt(_mirror(Hc))}"
        hem_bottom = hy + hem_dip / 2
    if p.get("quilting") == "baffle":   # a puffer: the cloth swells between the stitched channels
        side_pts = _scallop(side_pts, 32.0, 3.2 + bulk * 0.3, outward=+1)
    side_r = "L " + " L ".join(_pt(v) for v in side_pts[1:]) if len(side_pts) > 1 else ""
    left_side_pts = [_mirror(v) for v in side_pts[::-1]]
    if sleeved:
        sil_l = [_mirror(v) for v in sil[::-1]]
        arm_l = (" ".join(f"L {_pt(v)}" for v in left_side_pts[1:]) + " L " + " L ".join(_pt(v) for v in sil_l[1:])
                 + "".join(f" L {_pt(_mirror(v))}" for v in puff[::-1])
                 + f" L {_pt(_mirror(P1))} Q {_pt(_mirror(K))} {_pt(_mirror(S))}")
    else:
        arm_l = (" ".join(f"L {_pt(v)}" for v in left_side_pts[1:])
                 + f" C {_pt(_mirror(c2))} {_pt(_mirror(c1))} {_pt(_mirror(S))}")
    back_neck_y = ny - 4
    rise = {"stand": 31.0, "rib": 29.0, "notch": 21.0, "peak": 21.0, "shawl": 21.0, "shawl_knit": 19.0, "camp": 15.0}.get(cs, 24.5)
    rise += (bulk * 0.6 + (-1.5 if wt == 0 else 0)) if collar else 0   # a thick collar stands taller
    k = rise / 24.5                                  # the back of the collar, scaled to how high it stands
    TR, TL = (CX + 32.5, ny - rise), (CX - 32.5, ny - rise)
    if collar:
        # The collar is one folded band and part of the silhouette: straight up its outer
        # edge from the shoulder, across the fold behind the neck, and down the other side.
        neck_path = f"L {_pt(TL)} Q {_pt((CX, ny - rise - 12.5))} {_pt(TR)} L {_pt(N)}"
    else:
        neck_path = f"Q {_pt((CX, back_neck_y))} {_pt(N)}"
    if sleeved:
        outline = f"M {_pt(N)} L {_pt(S)} {arm} {side_r} {hem} {arm_l} L {_pt(_mirror(N))} {neck_path} Z"
    else:
        outline = f"M {_pt(N)} L {_pt(S)} {arm} {side_r} {hem} {arm_l} L {_pt(_mirror(N))} {neck_path} Z"
    outline = " ".join(outline.split())
    Sl, Al, Hl, Nl = _mirror(S), _mirror(A), _mirror(Hc), _mirror(N)

    sh = Shape(outline=outline)
    # Anchors are points on the wearer, the same for every top, so the mannequin view can line garments up:
    # the base of the neck and the shoulders of a 46 cm frame. How far the cloth extends beyond them is the fit.
    sh.anchors = {"neck": (CX, 58.0), "shoulder_l": (CX - 23 * K_PX, 80.0), "shoulder_r": (CX + 23 * K_PX, 80.0),
                  "hem": (CX, hy), "neck_point_l": Nl, "neck_point_r": N}
    sh.body_box = (CX - chest, sy, CX + chest, hy)
    xs = [float(x) for x, _ in re.findall(r"(-?[\d.]+),(-?[\d.]+)", outline)]
    xmax = max(max(xs), 2 * CX - min(xs))
    top_y = {"hood": ny - 74, "turtle": ny - 34, "roll": ny - 34, "mock": ny - 20}.get(neck, ny - 4)
    if collar:
        top_y = ny - rise - 9
    sh.bbox = (2 * CX - xmax, top_y, xmax, hem_bottom + 2)
    if cuff:
        deg = math.degrees(th)
        s0, s1, s2, s3 = seam
        right_sleeve = (f"M {_pt(S)} Q {_pt(K)} {_pt(P1)} L " + " L ".join(_pt(v) for v in puff + corner) + f" L {_pt(Ci)} "
                        + "".join(f"L {_pt(v)} " for v in puff_in) + f"L {_pt(A)} "
                        f"C {_pt(s2)} {_pt(s1)} {_pt(s0)} Z")
        sh.sleeves = [(right_sleeve, -deg), (_mirror_path(right_sleeve), deg)]
        if sh_over:   # the sleeve's inner edge where it lies over the body
            for m in (lambda v: v, _mirror):
                sh.seams.append(_poly([m(v) for v in sh_over], close=False))
        cstr = " L ".join(_pt(v) for v in corner)

    snap = p.get("fastener") == "snap"

    def fasten(x, y, rad):
        (sh.snaps if snap else sh.dots).append((x, y, rad))

    # ---- neckline
    front_bottom = ny
    stand_button = None
    yoke_start = None            # a point under the collar where the yoke seam can begin
    lapel_front = None           # for open collars: (break y, overlap) of the closure under the lapels
    ml = _mirror
    sides = ((lambda v: v, "r"), (_mirror, "l"))
    if neck in ("crew", "hood", "scoop"):
        dip = (24 if sleeved else 36) + (12 if neck == "scoop" else 0)
        front_bottom = ny + dip
        sh.parts.append(Part(
            f"M {_pt(Nl)} Q {_pt((CX, back_neck_y))} {_pt(N)} Q {_pt((CX, ny + dip * 2))} {_pt(Nl)} Z", "hole"))
        rib = f"M {_pt((Nl[0] - 5 * bs, ny + 4))} Q {_pt((CX, ny + dip * 2 + 16 * bs))} {_pt((N[0] + 5 * bs, ny + 4))}"
        sh.parts.append(Part(f"{rib} L {_pt(N)} Q {_pt((CX, ny + dip * 2))} {_pt(Nl)} Z", "neckrib"))
        sh.lines.append(rib)
        if p["neck_detail"] == "v-insert" and front == "none":
            ry = ny + 4 + (dip * 2 + 12) * 0.451   # the rib's lower edge, 11 either side of centre
            sh.parts.append(Part(f"M {_pt((CX - 11, ry))} Q {_pt((CX, ry + 4.5))} {_pt((CX + 11, ry))} "
                                 f"L {_pt((CX, ry + 21))} Z", "trim"))
    elif neck == "boat":
        # wide and shallow, across the collarbones: a narrow slit finished with a turned facing
        front_bottom = ny + 9
        sh.parts.append(Part(f"M {_pt(Nl)} Q {_pt((CX, back_neck_y))} {_pt(N)} Q {_pt((CX, ny + 18))} {_pt(Nl)} Z", "hole"))
        sh.lines.append(f"M {_pt((Nl[0] - 3, ny + 6))} Q {_pt((CX, ny + 26 + 4 * bs))} {_pt((N[0] + 3, ny + 6))}")
    elif neck == "v":
        depth = {"shallow": 44, "deep": 92}.get(p.get("v_depth"), 58)
        front_bottom = ny + depth
        if front in ("buttons", "zip", "double", "french", "hidden"):
            # a cardigan: a knitted band runs up each side of the V and on down the front
            bw = 11 * bs
            ap = (CX - bw / 2, front_bottom)
            sh.parts.append(Part(f"M {_pt(Nl)} Q {_pt((CX, back_neck_y))} {_pt(N)} L {_pt(ap)} Z", "hole"))
            bottom_y = hy - (18 * bs if p["hem"] == "rib" else 0) + 0.5
            left = [Nl, (Nl[0] - bw, ny + 2), (CX - bw / 2, front_bottom + bw * 1.9), ap]
            right = [N, ap, (CX - bw / 2, bottom_y), (CX + bw / 2, bottom_y), (CX + bw / 2, front_bottom + bw * 1.3),
                     (N[0] + bw, ny + 2)]
            sh.parts.append(Part(_poly(left), "band"))
            sh.parts.append(Part(_poly(right), "band"))
            lapel_front = ("cardigan", front_bottom, bw)
        else:
            sh.parts.append(Part(
                f"M {_pt(Nl)} Q {_pt((CX, back_neck_y))} {_pt(N)} L {_pt((CX, front_bottom))} Z", "hole"))
            sh.lines.append(f"M {_pt((Nl[0] - 6 * bs, ny + 3))} L {_pt((CX, front_bottom + 10 * bs))} L {_pt((N[0] + 6 * bs, ny + 3))}")
    elif neck in ("turtle", "mock", "roll"):
        front_bottom = ny + 6
        tall = {"turtle": 30, "mock": 13, "roll": 26}[neck] + bulk
        wide = 3 if neck != "roll" else -2 - bulk * 0.5    # a roll neck bulges out over itself
        if neck == "roll":
            tube = (f"M {_pt((Nl[0] - 3, ny + 6))} C {_pt((Nl[0] - 9, ny - 6))} {_pt((Nl[0] - 6, ny - tall))} {_pt((Nl[0] + 4, ny - tall - 2))} "
                    f"Q {_pt((CX, ny - tall - 11))} {_pt((N[0] - 4, ny - tall - 2))} "
                    f"C {_pt((N[0] + 6, ny - tall))} {_pt((N[0] + 9, ny - 6))} {_pt((N[0] + 3, ny + 6))} "
                    f"Q {_pt((CX, ny + 20))} {_pt((Nl[0] - 3, ny + 6))} Z")
        else:
            tube = (f"M {_pt((Nl[0] - 3, ny + 6))} L {_pt((Nl[0] + wide, ny - tall))} Q {_pt((CX, ny - tall - 7))} {_pt((N[0] - wide, ny - tall))} "
                    f"L {_pt((N[0] + 3, ny + 6))} Q {_pt((CX, ny + 20))} {_pt((Nl[0] - 3, ny + 6))} Z")
        sh.parts.append(Part(tube, "band"))
        if neck == "turtle":   # folded down on itself
            sh.lines.append(f"M {_pt((Nl[0] + 1, ny - 12))} Q {_pt((CX, ny - 4))} {_pt((N[0] - 1, ny - 12))}")
        elif neck == "roll":   # the soft underside of the roll
            sh.parts.append(Part(f"M {_pt((Nl[0] - 4, ny - 8))} Q {_pt((CX, ny + 4))} {_pt((N[0] + 4, ny - 8))}", "edge"))
        if front in ("zip", "quarter-zip", "half-zip"):   # the zip runs up through the collar to its top
            top = ny - tall - (3.5 if neck != "roll" else 7)
            sh.parts.append(Part(f"M {_pt((CX, top))} L {_pt((CX, ny + 13))}", "edge"))
            sh.parts.append(Part(_poly([(CX - 3.5, top + 3), (CX + 3.5, top + 3), (CX + 3.5, top + 15), (CX - 3.5, top + 15)]), "trim"))
            front_bottom = ny + 13
    elif leafy:
        # Seen from the front: a wide U-shaped opening showing the inside of the back of
        # the shirt, with the collar band running across it; below, the two leaves fold
        # down and meet at the centre in an X, each ending in a point. On a woven shirt
        # the collar stand shows under the meeting point and carries the top button.
        dx, dy, finish = LEAVES[cs]
        C0 = (CX, ny + 14.5)                           # where the leaves meet
        tip = (CX + dx, C0[1] + dy)
        a, c1, c2, b = (CX + 27, ny - 12.5 * k), (CX + 30, ny - 16.5 * k), (CX + 29.5, ny - 23.5 * k), (CX + 20, ny - 25.5 * k)
        rim = (f"M {_pt(C0)} L {_pt(ml(a))} C {_pt(ml(c1))} {_pt(ml(c2))} {_pt(ml(b))} Q {_pt((CX, ny - 28.4 * k))} {_pt(b)} "
               f"C {_pt(c2)} {_pt(c1)} {_pt(a)} Z")
        sh.parts.append(Part(rim, "hole"))
        sh.parts.append(Part(f"M {_pt((CX - 27.5, ny - 14 * k))} Q {_pt((CX, ny - 16.5 * k))} {_pt((CX + 27.5, ny - 14 * k))}", "edge"))
        if cs == "johnny":   # no placket: an open V below the collar, the collar's ends lying along it
            v_bottom = ny + 62
            sh.parts.append(Part(_poly([(CX - 12, C0[1] - 2), (CX + 12, C0[1] - 2), (CX, v_bottom)]), "hole"))
            sh.parts.append(Part(f"M {_pt((CX - 12, C0[1] - 2))} L {_pt((CX, v_bottom))} L {_pt((CX + 12, C0[1] - 2))}", "edge"))

        def leaf_edge(m):
            """The leaf's visible lower edge, from the shoulder point round the tip to where the leaves meet."""
            if finish == "club":
                rr = 10
                p1 = (tip[0] + _unit((N[0] - tip[0], N[1] - tip[1]))[0] * rr, tip[1] + _unit((N[0] - tip[0], N[1] - tip[1]))[1] * rr)
                p2 = (tip[0] + _unit((C0[0] - tip[0], C0[1] - tip[1]))[0] * rr, tip[1] + _unit((C0[0] - tip[0], C0[1] - tip[1]))[1] * rr)
                return f"L {_pt(m(p1))} Q {_pt(m(tip))} {_pt(m(p2))} L {_pt(C0)}"
            if finish == "roll":   # a soft roll: the outer edge bellies out, the front edge curves
                mo = ((N[0] + tip[0]) / 2 + 4, (N[1] + tip[1]) / 2 + 1.5)
                mf = ((tip[0] + C0[0]) / 2 + 1, (tip[1] + C0[1]) / 2 + 3)
                return f"Q {_pt(m(mo))} {_pt(m(tip))} Q {_pt(m(mf))} {_pt(C0)}"
            return f"L {_pt(m(tip))} L {_pt(C0)}"

        for m, side in sides:
            leaf = (f"M {_pt((CX, ny - 30.75 * k))} Q {_pt(m((CX + 16.25, ny - 30.75 * k)))} {_pt(m(TR))} L {_pt(m(N))} "
                    f"{leaf_edge(m)} L {_pt(m(a))} C {_pt(m(c1))} {_pt(m(c2))} {_pt(m(b))} "
                    f"Q {_pt(m((CX + 10, ny - 26.95 * k)))} {_pt((CX, ny - 26.95 * k))} Z")
            sh.parts.append(Part(leaf, f"collar_{side}"))
        # every visible collar edge, so nothing is drawn twice
        sh.parts.append(Part(f"M {_pt(Nl)} {leaf_edge(_mirror)} M {_pt(N)} {leaf_edge(lambda v: v)} {rim}", "edge"))
        if wt >= 2:   # a heavy cloth: the collar's topstitch sits well in from its edge
            for m, _ in sides:
                sh.parts.append(Part(_poly([m(v) for v in _shrink([N, tip, C0], 0.78)], close=False), "edge"))
        cen = ((N[0] + tip[0] + C0[0]) / 3, (N[1] + tip[1] + C0[1]) / 3)
        yoke_start = _lerp(N, cen, 0.5)
        front_bottom = C0[1]
        if cs in ("button_down",):   # small buttons hold the points down
            inward = _unit((cen[0] - tip[0], cen[1] - tip[1]))
            for m, _ in sides:
                sh.dots.append((*m((tip[0] + inward[0] * 5.5, tip[1] + inward[1] * 5.5)), 2.1))
        if cs == "pin":              # a collar bar through both leaves, halfway down the points
            py = C0[1] + dy * 0.55
            hw = dx * 0.55 + 6
            sh.parts.append(Part(_capsule_h(CX - hw, CX + hw, py, 2.6), "inlay", color="#b9b8b2"))
        if woven:
            # the top button needs room between the leaves' front edges
            need = C0[1] + 4.6 * dy / dx
            btn_y = max(ny + 21.3, need)
            stand_y = max(ny + 26.5, btn_y + 5.2)
            # the stand's lower edge: under the leaves except between them
            sh.seams.append(f"M {_pt(Nl)} Q {_pt((CX - 22, stand_y))} {_pt((CX, stand_y))} Q {_pt((CX + 22, stand_y))} {_pt(N)}")
            front_bottom = stand_y
            stand_button = btn_y
            if cs == "tab":   # a rounded strap joins the close-set points under the tie, buttoned in the middle
                ty, tw = C0[1] + dy * 0.62, 7.5
                half = dx * (ty - C0[1]) / dy + 9       # its ends tuck under the leaves
                first_leaf = next(i for i, q in enumerate(sh.parts) if q.role == "collar_r")
                sh.parts.insert(first_leaf, Part(_capsule_h(CX - half, CX + half, ty, 2 * tw), "trim"))
                sh.dots.append((CX, ty, 3.0))
                stand_button = None
    elif banded:
        # A stand with no leaves: its front rises from the neckline seam; above its top
        # edge the inside of the back of the band shows.
        y_ct = ny + (8.0 if cs in ("stand", "rib") else 14.5)
        y_cb = ny + (24.0 if cs in ("stand", "rib") else 26.5) + bulk * 0.5
        E = _lerp(N, TR, 0.5)
        top_r = [(CX, y_ct)] + _bez((CX, y_ct), (CX + 16, y_ct), (E[0] - 2, E[1] + 12), E)
        bot_r = [N] + _bez(N, (N[0] - 2, N[1] + 17), (CX + 20, y_cb), (CX, y_cb))
        back = _qbez(TR, (CX, ny - rise - 12.5), TL, 14)
        hole = [ml(v) for v in top_r[::-1]] + top_r[1:] + [TR] + back[1:]
        sh.parts.append(Part(_poly(hole), "hole"))
        role = "band" if cs == "rib" else None
        for m, side in sides:
            band = [m(v) for v in top_r + bot_r]
            sh.parts.append(Part(_poly(band), role or f"collar_{side}"))
            if role is None:
                sh.parts.append(Part(_poly([m(v) for v in top_r + bot_r], close=True), "edge"))
        if cs == "wing":   # the stand's front tips are pressed out into wings, wide enough to read at item size
            for m, side in sides:
                w = [(CX + 1.2, y_ct - 0.5), (CX + 28, y_ct + 2), (CX + 19, y_ct + 12.5), (CX + 4.5, y_cb - 1)]
                sh.parts.append(Part(_poly([m(v) for v in w]), f"collar_{side}"))
                sh.parts.append(Part(_poly([m(v) for v in w]), "edge"))
        if front != "none":
            sh.parts.append(Part(f"M {_pt((CX, y_ct))} L {_pt((CX, y_cb))}", "edge"))
        if front in ("buttons", "french", "hidden", "popover", "half", "double") and cs != "wing":
            stand_button = (y_ct + y_cb) / 2
        if front in ("zip", "quarter-zip", "half-zip"):
            sh.parts.append(Part(_poly([(CX - 3.5, y_ct + 2), (CX + 3.5, y_ct + 2), (CX + 3.5, y_ct + 14), (CX - 3.5, y_ct + 14)]), "trim"))
        yoke_start = bot_r[3]
        front_bottom = y_cb
    elif lapel:
        lapel_front = _lapels(sh, cs, ny, N, TR, TL, k, rise, front, bulk, hy)
        yb, ov = lapel_front[1], lapel_front[2]
        yoke_start = _lerp(N, (CX + 24, ny + 26), 0.4)
        front_bottom = yb
    if neck == "hood":
        hood = (f"M {_pt((Nl[0] - 14, ny + 8))} C {_pt((CX - 70, ny - 60))} {_pt((CX - 38, ny - 84))} {_pt((CX, ny - 84))} "
                f"C {_pt((CX + 38, ny - 84))} {_pt((CX + 70, ny - 60))} {_pt((N[0] + 14, ny + 8))} Z")
        sh.behind.append(Part(hood, "trim"))
        sh.lines.append(f"M {_pt((CX - 9, front_bottom + 4))} L {_pt((CX - 11, front_bottom + 52))}")
        sh.lines.append(f"M {_pt((CX + 9, front_bottom + 4))} L {_pt((CX + 11, front_bottom + 52))}")

    blocks = tuple(p.get("colorblock") or ())
    if "collar" in blocks and collar:
        for q in sh.parts:
            if q.role in ("collar_r", "collar_l", "lapel_r", "lapel_l", "hole"):
                q.color = "block"
    if "yoke" in blocks:   # the chest and shoulders above a seam across the front
        yb = sy + 50
        curve = seam or (armhole if not sleeved else None)
        if curve and yb < curve[3][1]:
            run = [v for v in [curve[0]] + _bez(*curve, 16) if v[1] < yb] + [(_cubic_x_at_y(*curve, yb), yb)]
        else:
            run = [S, (S[0], yb)]
        region = [(Sl[0], 0.0), (S[0], 0.0)] + run + [_mirror(v) for v in run[::-1]]
        sh.blocks.append(_poly(region))
        sh.seams.append(f"M {_pt(_mirror(run[-1]))} L {_pt(run[-1])}")
    sh.block_sleeves = "sleeves" in blocks and sleeved
    on_sleeve = "block" if sh.block_sleeves else None

    # ---- yoke seams: near-parallel to the shoulder, from under the collar to the armhole
    yoke = p.get("yoke") or ("plain" if (woven and collar) else "none")
    if yoke_start and seam and yoke == "plain":
        yoke_y = sy + 14.5
        for m in (lambda v: v, _mirror):
            yoke_x = _cubic_x_at_y(*seam, yoke_y) if shoulder != "drop" else S[0] - 3
            sh.seams.append(f"M {_pt(m(yoke_start))} L {_pt(m((yoke_x, yoke_y)))}")
    elif seam and yoke == "western":
        # a western front yoke: from the armhole it dips to a point over the chest, then up to the placket
        y0 = sy + 22
        x0 = _cubic_x_at_y(*seam, y0) if shoulder != "drop" else S[0] - 3
        for m in (lambda v: v, _mirror):
            sh.seams.append(f"M {_pt(m((x0, y0)))} Q {_pt(m(((x0 + CX + 44) / 2, y0 + 12)))} {_pt(m((CX + 44, sy + 54)))} "
                            f"Q {_pt(m((CX + 26, sy + 40)))} {_pt(m((CX + 7, sy + 34)))}")

    # ---- armhole seams: from the shoulder, curving in, then straight down into the side seam
    if seam and shoulder == "raglan" and not collar:
        for m in (lambda v: v, _mirror):
            sh.seams.append(f"M {_pt(m((N[0] + 4, ny + 2)))} Q {_pt(m(((N[0] + A[0]) / 2 + 9, (ny + ay) / 2 - 8)))} {_pt(m(A))}")
    elif seam and shoulder == "dolman":
        pass   # cut in one with the body: no armhole seam to draw
    elif seam:
        s0, s1, s2, s3 = seam
        for m in (lambda v: v, _mirror):
            sh.seams.append(f"M {_pt(m(s0))} C {_pt(m(s1))} {_pt(m(s2))} {_pt(m(s3))} L {_pt(m(A))}")
            if shoulder == "saddle":   # a strip of the sleeve runs across the top of the shoulder to the neck
                st = (S[0] - 6, S[1] + 13)
                sh.seams.append(f"M {_pt(m((N[0] + 3, ny + 11)))} L {_pt(m(st))}")
    if vest:   # the ribbed band round a sweater vest's armhole
        S_, c1_, c2_, A_ = armhole
        pts = [S_] + _bez(S_, c1_, c2_, A_, 14)
        inner = _offset_line(pts, -9 * bs)
        # both edges run on past the side seam and the outline cuts them, so the band meets the side at full width
        t = _unit((pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]))
        pts = pts + [(A_[0] + 8, A_[1] + t[1] * 8 / max(t[0], 0.3))]
        inner = inner + [(inner[-1][0] + 12, inner[-1][1] + t[1] * 12 / max(t[0], 0.3))]
        for m, _ in sides:
            sh.parts.append(Part(_poly([m(v) for v in pts + inner[::-1]]), "band", clip=True))

    # ---- stripes down the outside of the sleeves (a track jacket)
    if cuff and p.get("stripes") == "sleeve":
        Co, Ci, d = cuff
        a0 = (P1[0] + d[0] * 6, P1[1] + d[1] * 6)
        a1 = (Co[0] - d[0] * 4, Co[1] - d[1] * 4)
        for o0, o1 in ((5.0, 9.5), (13.0, 17.5)):
            strip = [(a0[0] + q[0] * o0, a0[1] + q[1] * o0), (a1[0] + q[0] * o0, a1[1] + q[1] * o0),
                     (a1[0] + q[0] * o1, a1[1] + q[1] * o1), (a0[0] + q[0] * o1, a0[1] + q[1] * o1)]
            for m in (lambda v: v, _mirror):
                sh.parts.append(Part(_poly([m(v) for v in strip]), "inlay", color="trim", clip=True))
    # ---- stripes round the arms and the body above the hem (a hockey jersey)
    if p.get("stripes") == "hoops":
        bands = []
        if cuff:
            Co, Ci, d = cuff
            q_ = _unit((Ci[0] - Co[0], Ci[1] - Co[1]))
            span = (((24, 31), (37, 44)) if sleeve in ("long", "three-quarter") else ((12, 18),))
            for a, b in span:
                bands.append([(Co[0] - d[0] * a - q_[0] * 6, Co[1] - d[1] * a - q_[1] * 6),
                              (Ci[0] - d[0] * a + q_[0] * 3, Ci[1] - d[1] * a + q_[1] * 3),
                              (Ci[0] - d[0] * b + q_[0] * 3, Ci[1] - d[1] * b + q_[1] * 3),
                              (Co[0] - d[0] * b - q_[0] * 6, Co[1] - d[1] * b - q_[1] * 6)])
        for band in bands:
            for m in (lambda v: v, _mirror):
                sh.parts.append(Part(_poly([m(v) for v in band]), "inlay", color="trim", clip=True))
        for a, b in ((44, 36), (30, 22)):
            band = [(CX - hh - 4, hy - a), (CX + hh + 4, hy - a), (CX + hh + 4, hy - b), (CX - hh - 4, hy - b)]
            sh.parts.append(Part(_poly(band), "inlay", color="trim", clip=True))

    # ---- cuffs
    if cuff:
        Co, Ci, d = cuff
        din = _unit((A[0] - Ci[0], A[1] - Ci[1]))   # up the sleeve's inner edge
        long_cuff = sleeve in ("long", "three-quarter") and cuffs not in ("rolled", "roll-tab")
        depth = {"rib": 17 * bs, "button": 22, "button2": 22, "convertible": 22, "mitred": 22, "french": 28, "snap3": 31}.get(cuffs)
        if cuffs == "rib" and not long_cuff:
            depth = 11 * bs     # a polo's ribbed armband
        if depth and (long_cuff or cuffs == "rib") and cuffs in ("rib", "button", "button2", "convertible", "mitred", "french", "snap3"):
            depth += bulk if cuffs != "rib" else 0
            Bo = (Co[0] - d[0] * depth, Co[1] - d[1] * depth)
            Bi = (Ci[0] + din[0] * depth, Ci[1] + din[1] * depth)
            at = lambda f, g: (Co[0] + (Ci[0] - Co[0]) * f - d[0] * depth * g, Co[1] + (Ci[1] - Co[1]) * f - d[1] * depth * g)
            for m in (lambda v: v, _mirror):
                band = [m(v) for v in (corner + [Ci, Bi, Bo])]
                sh.parts.append(Part(_poly(band), "band" if cuffs == "rib" else "cuff", color=on_sleeve))
                if cuffs in ("button", "mitred"):   # the button sits in the middle of the cuff's depth, clear of its edges
                    fasten(*m(at(0.34 if cuffs == "button" else 0.36, 0.5)), 2.6)
                elif cuffs == "convertible":        # a button, and beside it the spare buttonhole for a cufflink
                    fasten(*m(at(0.34, 0.5)), 2.6)
                    sh.parts.append(Part(_poly([m(at(0.1, 0.5)), m(at(0.24, 0.5))], close=False), "edge"))
                elif cuffs == "button2":            # two buttons side by side
                    fasten(*m(at(0.24, 0.5)), 2.5)
                    fasten(*m(at(0.44, 0.5)), 2.5)
                elif cuffs == "snap3":              # three snaps up a deep western cuff
                    for g in (0.2, 0.5, 0.8):
                        sh.snaps.append((*m(at(0.3, g)), 2.4))
                elif cuffs == "french":             # folded back on itself, the ends held by a link
                    sh.parts.append(Part(_poly([m(at(0.0, 0.8)), m(at(1.0, 0.8))], close=False), "edge"))   # the turned-back layer
                    lc = m(at(0.2, 0.42))
                    sh.parts.append(Part(_capsule_h(lc[0] - 4, lc[0] + 4, lc[1], 4.2), "inlay", color="#c9b27a"))
                if wt >= 2 and cuffs != "rib":      # a thick cloth: a topstitch near the cuff's edge
                    sh.parts.append(Part(_poly([m(at(0.0, 0.84)), m(at(1.0, 0.84))], close=False), "edge"))
        elif cuffs in ("rolled", "roll-tab"):
            depth = 19 + bulk
            Bo = (Co[0] - d[0] * depth, Co[1] - d[1] * depth)
            Bi = (Ci[0] + din[0] * depth, Ci[1] + din[1] * depth)
            # the roll is bulkier than the sleeve: it stands a little proud of both edges
            o = lambda v, s: (v[0] + q[0] * s, v[1] + q[1] * s)
            roll = [Co, Ci, Bi, Bo]
            mid_o, mid_i = _lerp(roll[0], roll[3], 0.5), _lerp(roll[1], roll[2], 0.5)
            for m in (lambda v: v, _mirror):
                sh.parts.append(Part(_poly([m(v) for v in roll]), "cuff", color=on_sleeve))
                sh.parts.append(Part(_poly([m(mid_o), m(mid_i)], close=False), "edge"))
                if cuffs == "roll-tab":   # the tab that holds the roll up, buttoned on the sleeve
                    tb = (Co[0] + (Ci[0] - Co[0]) * 0.3, Co[1] + (Ci[1] - Co[1]) * 0.3)
                    t0 = (tb[0] - d[0] * (depth - 1), tb[1] - d[1] * (depth - 1))
                    t1 = (tb[0] - d[0] * (depth + 30), tb[1] - d[1] * (depth + 30))
                    tab = [o(t0, -3.5), o(t0, 3.5), o(t1, 3.5), _lerp(o(t1, 0), (t1[0] - d[0] * 4, t1[1] - d[1] * 4), 1), o(t1, -3.5)]
                    sh.parts.append(Part(_poly([m(v) for v in tab]), "cuff", color=on_sleeve))
                    fasten(*m((t1[0] + d[0] * 3, t1[1] + d[1] * 3)), 2.4)
        elif sleeve != "long" or cuffs == "open":
            hem_d = 10.5 + bulk * 0.6
            Bo = (Co[0] - d[0] * hem_d, Co[1] - d[1] * hem_d)
            Bi = (Ci[0] + din[0] * hem_d, Ci[1] + din[1] * hem_d)
            for m in (lambda v: v, _mirror):
                sh.lines.append(f"M {_pt(m(Bo))} L {_pt(m(Bi))}")
                if wt >= 2:   # a heavy cloth's hem is turned twice: two rows of stitching
                    sh.lines.append(f"M {_pt(m((Bo[0] - d[0] * 4, Bo[1] - d[1] * 4)))} L {_pt(m((Bi[0] - d[0] * 4, Bi[1] - d[1] * 4)))}")

    # ---- hem
    rib_h = (7.0 if block in ("knit", "bomber") else 5.5) * K_PX * bs
    if p["hem"] == "rib" and leafy and woven:   # a woven jacket (a trucker): a buttoned waistband with side adjusters
        b = min(rib_h, 5 * K_PX + bulk * 0.5)
        xb = _x_on(side_from, hy - b)
        sh.parts.append(Part(
            f"M {_pt((xb, hy - b))} L {_pt(Hc)} Q {_pt((CX, hy + hem_dip))} {_pt(Hl)} "
            f"L {_pt((2 * CX - xb, hy - b))} Q {_pt((CX, hy - b + hem_dip))} {_pt((xb, hy - b))} Z", "cuff"))
        if front != "none":
            sh.parts.append(Part(f"M {_pt((CX - 7, hy - b + hem_dip / 2))} L {_pt((CX - 7, hy + hem_dip / 2))}", "edge"))
            fasten(CX, hy - b / 2 + hem_dip / 2, 3.4)
        yt, yb_ = hy - b + 3.5, hy - 2
        xe = _x_on(side_from, hy - b / 2) - 8
        tab = [(xe, yt), (xe - 20, yt), (xe - 26, (yt + yb_) / 2), (xe - 20, yb_), (xe, yb_)]
        for m in (lambda v: v, _mirror):
            sh.parts.append(Part(_poly([m(v) for v in tab]), "cuff"))
            fasten(*m((xe - 18, (yt + yb_) / 2)), 2.4)
    elif p["hem"] == "rib":
        b = rib_h
        xb = _x_on(side_from, hy - b)
        sh.parts.append(Part(
            f"M {_pt((xb, hy - b))} L {_pt(Hc)} Q {_pt((CX, hy + hem_dip))} {_pt(Hl)} "
            f"L {_pt((2 * CX - xb, hy - b))} Q {_pt((CX, hy - b + hem_dip))} {_pt((xb, hy - b))} Z", "band"))
    elif p["hem"] in ("straight", "vents", "tennis"):
        inset = 4 if vents else 1
        hem_l = 9 + bulk * 0.6
        sh.lines.append(f"M {_pt((CX - hh + inset, hy - hem_l))} Q {_pt((CX, hy - hem_l + 5))} {_pt((CX + hh - inset, hy - hem_l))}")
        if wt >= 2:
            sh.lines.append(f"M {_pt((CX - hh + inset, hy - hem_l - 4))} Q {_pt((CX, hy - hem_l + 1))} {_pt((CX + hh - inset, hy - hem_l - 4))}")
        if vents:
            for m in (lambda v: v, _mirror):   # a bar tack at the top of each vent
                sh.lines.append(f"M {_pt(m((CX + hh - 6, hy - 20)))} L {_pt(m((CX + hh + 1, hy - 20)))}")
        if p["hem"] == "tennis":   # the back hangs longer than the front: a band of it shows below
            back = (f"M {_pt((CX + hh - 1, hy - 24))} L {_pt((CX + hh - 1.5, hy + 11))} Q {_pt((CX, hy + 22))} "
                    f"{_pt((CX - hh + 1.5, hy + 11))} L {_pt((CX - hh + 1, hy - 24))} Z")
            sh.behind.append(Part(back, "cuff"))
            sh.bbox = (sh.bbox[0], sh.bbox[1], sh.bbox[2], hy + 18)
    elif p["hem"] == "raw":   # a cut edge: no stitching, a few loose threads
        x = CX - hh + 6
        i = 0
        while x < CX + hh - 5:
            yb_ = hy + hem_dip / 2 * (1 - ((x - CX) / hh) ** 2) - 0.5
            sh.lines.append(f"M {_pt((x, yb_))} L {_pt((x + (0.8 if i % 2 else -0.6), yb_ - (3.2 if i % 3 else 4.6)))}")
            x += 6.5
            i += 1
    elif curved and wt >= 2:
        sh.lines.append(f"M {_pt((CX + hh - 2, side_y - 6))} C {_pt((CX + hh - 50, side_y + 19))} "
                        f"{_pt((CX - hh + 50, side_y + 19))} {_pt((CX - hh + 2, side_y - 6))}")

    # ---- front opening. These are seams: the collar lies over the top of them.
    bottom = hem_bottom + 2
    count = p["buttons"] if p["buttons"] is None else max(0, int(p["buttons"]))
    if lapel_front and lapel_front[0] == "cardigan":
        _, fb, bw = lapel_front
        last = hy - (rib_h if p["hem"] == "rib" else 0) - 14
        first = fb + 12
        if front == "zip":
            sh.lines.append(f"M {_pt((CX, fb + 4))} L {_pt((CX, bottom))}")
        else:
            n = count if count is not None else max(3, round((last - first) / 34) + 1)
            n = max(0, min(10, n))
            for i in range(n):
                fasten(CX, first + (last - first) * (i / (n - 1) if n > 1 else 0), 3.2)
    elif lapel_front:
        _, yb, ov = lapel_front
        dbl = front == "double"
        if front != "none":
            sh.seams.append(f"M {_pt((CX - ov, yb))} L {_pt((CX - ov, bottom))}")
            if cs == "camp":   # a shirt keeps its placket below the revers
                sh.seams.append(f"M {_pt((CX + 7, yb + 5))} L {_pt((CX + 7, bottom))}")
            if cs == "shawl_knit":
                sh.parts.append(Part(_poly([(CX - ov, yb + 1), (CX + ov, yb + 6), (CX + ov, bottom - (rib_h if p["hem"] == "rib" else 0)),
                                            (CX - ov, bottom - (rib_h if p["hem"] == "rib" else 0))]), "band"))
        if front in ("buttons", "french", "hidden", "popover", "double", "half") and count != 0:
            last = hy - (rib_h if p["hem"] == "rib" else 0) - (42 if curved else 26)
            if cs == "camp":
                n = count if count is not None else max(2, round((last - yb - 4) / 44) + 1)
                gap = (last - yb - 4) / max(n - 1, 1)
            elif dbl:
                n = count // 2 if count else 3
                gap = 40
            else:
                n = count if count is not None else (1 if cs == "shawl" else 2 if cs in ("notch", "peak") else 5)
                gap = 46 if cs in ("notch", "peak", "shawl") else (last - yb - 4) / max(n - 1, 1)
            for i in range(max(1, min(10, n))):
                y = yb + 5 + gap * i
                if dbl:
                    fasten(CX - 17, y, 3.6)
                    fasten(CX + 17, y, 3.6)
                else:
                    fasten(CX, y, 3.6 if cs != "camp" else 3.4)
        elif front in ("zip", "half-zip", "quarter-zip"):
            sh.seams.append(f"M {_pt((CX, yb))} L {_pt((CX, bottom))}")
    elif front in ("buttons", "french", "hidden", "snaps", "double"):
        top_y = front_bottom + (1.3 if collar else 2)   # just under the curve of the stand seam
        dbl = front == "double"
        if front == "buttons":
            sh.seams.append(f"M {_pt((CX - 7, top_y))} L {_pt((CX - 7, bottom))}")
            sh.seams.append(f"M {_pt((CX + 7, top_y))} L {_pt((CX + 7, bottom))}")
            if wt >= 2:   # a heavy cloth's placket: a second row of stitching
                sh.seams.append(f"M {_pt((CX + 10.5, top_y + 1))} L {_pt((CX + 10.5, bottom))}")
        elif front == "french":       # no strip sewn on: just the folded edge
            sh.seams.append(f"M {_pt((CX - 7, top_y))} L {_pt((CX - 7, bottom))}")
        elif front == "hidden":       # a fly hides the buttons; one row of stitching holds it
            sh.seams.append(f"M {_pt((CX - 7, top_y))} L {_pt((CX - 7, bottom))}")
            sh.seams.append(f"M {_pt((CX + 9, top_y))} L {_pt((CX + 9, hy - 40))} Q {_pt((CX + 9, hy - 34))} {_pt((CX + 3, hy - 32))}")
        elif dbl:                     # double-breasted with no lapels: the front wraps well past the centre
            sh.seams.append(f"M {_pt((CX - 30, top_y))} L {_pt((CX - 30, bottom))}")
        first = front_bottom + (36 if collar else 16)
        last = hy - (42 if curved else 30) - (rib_h - 4 if p["hem"] == "rib" else 0)
        if count is None:
            n = max(2, round((last - first) / 44) + 1)
        else:   # the count the tagger saw, including the one on the collar stand
            n = max(1, min(10, count - (1 if stand_button else 0)))
        if stand_button and count != 0:
            fasten(CX, stand_button, 3.4)   # the top button, on the collar stand
        if count != 0 and front != "hidden":
            for i in range(n):
                y = first + (last - first) * (i / (n - 1) if n > 1 else 0.5)
                if dbl:
                    fasten(CX - 17, y, 3.4)
                    fasten(CX + 17, y, 3.4)
                else:
                    fasten(CX, y, 3.4)
    elif front in ("half", "popover"):
        # a polo or henley placket: as long as its buttons need; a woven popover's runs to mid-chest
        pop = front == "popover"
        n = (3 if pop else 2) if count is None else min(5, count - (1 if (stand_button and count) else 0))
        n = max(n, 0)
        top_y = front_bottom if collar else front_bottom + 2
        first, step = top_y + (17 if collar else 13), (34 if pop else 22)
        end = first + step * max(n - 1, 0) + (14 if n else 26)
        if pop:
            end = max(end, top_y + 96)
        placket_seam = len(sh.seams)
        sh.seams.append(f"M {_pt((CX - 7, top_y))} L {_pt((CX - 7, end))} L {_pt((CX + 7, end))} L {_pt((CX + 7, top_y))}")
        if stand_button and count != 0:
            fasten(CX, stand_button, 3.2)
        for i in range(n):
            fasten(CX, first + step * i, 3.0)
    elif front in ("zip", "quarter-zip", "half-zip"):
        end = {"zip": bottom, "quarter-zip": front_bottom + 78, "half-zip": front_bottom + 128}[front]
        sh.seams.append(f"M {_pt((CX, front_bottom))} L {_pt((CX, end))}")
        if neck not in ("turtle", "mock", "roll") and not banded:
            sh.lines.append(f"M {_pt((CX - 4, front_bottom + 6))} L {_pt((CX - 4, front_bottom + 20))} "
                            f"L {_pt((CX + 4, front_bottom + 20))} L {_pt((CX + 4, front_bottom + 6))}")
        if front != "zip":
            sh.lines.append(f"M {_pt((CX - 5, end))} L {_pt((CX + 5, end))}")

    nd = len(sh.dots)
    _pockets(sh, p["pockets"], sy, hy, hh, hs, p["hem"], cuff, A, rib_h, lapel_front, block="pocket" in blocks)
    if snap:   # a snap front's pocket flaps close with snaps too
        sh.snaps.extend(sh.dots[nd:])
        del sh.dots[nd:]
    if p.get("binding"):
        inner, edge = [], []
        if banded:
            inner.append(_poly([ml(v) for v in top_r[::-1]] + top_r[1:], close=False))
            edge.append(_poly([E, TR] + back[1:] + [ml(E)], close=False))
        elif neck in ("crew", "scoop"):
            dip = (24 if sleeved else 36) + (12 if neck == "scoop" else 0)
            inner.append(f"M {_pt(N)} Q {_pt((CX, ny + dip * 2))} {_pt(Nl)}")
        if front in ("half", "popover"):
            inner.append(sh.seams[placket_seam])
        elif front in ("buttons", "zip", "quarter-zip", "half-zip") and not lapel_front:
            x = 7 if front == "buttons" else 4
            end = {"quarter-zip": front_bottom + 78, "half-zip": front_bottom + 128}.get(front, bottom)
            inner.extend(f"M {_pt((CX + s_ * x, front_bottom))} L {_pt((CX + s_ * x, end))}" for s_ in (-1, 1))
        if cuff:
            for m in (lambda v: v, _mirror):
                edge.append(_poly([m(v) for v in corner + [cuff[1]]], close=False))
        edge.append(f"M {_pt(side_pts[-1])} {hem}")
        sh.parts.extend(Part(d_, "binding") for d_ in inner)
        sh.parts.extend(Part(d_, "binding_edge", clip=True) for d_ in edge)
    if wt == 0 and not jacket:   # a light cloth drapes: soft folds fall from the underarm and gather at the elbow
        Ub = U or A
        # one long fold from the underarm and a shorter, steeper one below it; the two sides differ, as cloth does
        for m, folds, at in ((lambda v: v, ((3, 4, 44, 0.78, 0.62), (4, 29, 22, 0.5, 0.86)), 0.55),
                             (_mirror, ((3, 9, 36, 0.66, 0.75), (5, 40, 16, 0.38, 0.92)), 0.47)):
            for dx_, dy_, ln_, ux, uy in folds:
                a0 = (_x_on(side_from, Ub[1] + dy_) - dx_, Ub[1] + dy_)
                a1 = (a0[0] - ln_ * ux, a0[1] + ln_ * uy)
                sh.folds.append(f"M {_pt(m(a0))} Q {_pt(m((a0[0] - ln_ * ux * 0.3, a0[1] + ln_ * uy * 0.75)))} {_pt(m(a1))}")
            if cuff and sleeve in ("long", "three-quarter") and not (p["pockets"] == "utility" and m is not _mirror):
                Co, Ci, d = cuff   # an elbow fold, clear of a sleeve pocket
                o, i_ = _lerp(P1, Co, at), _lerp(A, Ci, at)
                f0, f1 = _lerp(o, i_, 0.1), _lerp(o, i_, 0.48)
                sag = _lerp(f0, f1, 0.5)
                sh.folds.append(f"M {_pt(m(f0))} Q {_pt(m((sag[0] + d[0] * 6, sag[1] + d[1] * 6)))} {_pt(m(f1))}")
    if state == "open" and front != "none":   # the edge of the front that lies on top, for the renderer to open
        if lapel_front and lapel_front[0] == "cardigan":
            apex = (CX - lapel_front[2] / 2, lapel_front[1])      # the V's point; the button band runs down from it
            sh.fronts = ([N, apex, (apex[0], hy + 20)], "vertical")
        elif lapel_front:                                       # revers or a shawl: the V runs to the break
            sh.fronts = ([N, (CX - lapel_front[2], lapel_front[1]), (CX - lapel_front[2], hy + 20)], "horizontal")
        elif front in ("buttons", "french", "hidden", "double", "zip"):
            x = CX - {"zip": 0, "double": 30}.get(front, 7)     # how far the top front reaches past the centre
            sh.fronts = ([(x, front_bottom), (x, hy + 20)], "horizontal" if front == "double" else "vertical")
    if p.get("belt"):
        _belt(sh, wy, hh, p["belt"])
    return sh


def _belt(sh, y, half, kind=True):
    """A self belt round the waist: a band of the cloth across the body, clipped to its edges. A trench coat's is
    buckled a little off centre, its loose end hanging from the buckle; a robe's sash (kind "sash") is knotted,
    its two ends hanging."""
    h = 9.0
    band = [(CX - half - 40, y - h / 2), (CX + half + 40, y - h / 2), (CX + half + 40, y + h / 2), (CX - half - 40, y + h / 2)]
    sh.parts.append(Part(_poly(band), "trim", clip=True))
    bx = CX - 16
    if kind == "sash":
        for dx_, ln in ((-7, 46), (5, 38)):
            sh.parts.append(Part(f"M {_pt((bx + dx_ - 3, y + 3))} L {_pt((bx + dx_ * 2 - 4, y + ln))} "
                                 f"L {_pt((bx + dx_ * 2 + 4, y + ln + 1))} L {_pt((bx + dx_ + 4, y + 3))} Z", "trim"))
        sh.parts.append(Part(_poly([(bx - 6, y - h / 2 - 2), (bx + 6, y - h / 2 - 2), (bx + 5, y + h / 2 + 3),
                                    (bx - 5, y + h / 2 + 3)]), "trim"))
        return
    sh.parts.append(Part(f"M {_pt((bx - 2, y + 2))} L {_pt((bx - 9, y + 30))} L {_pt((bx - 1, y + 32))} L {_pt((bx + 5, y + 4))} Z",
                         "trim"))
    sh.parts.append(Part(_frame((bx, y), 13, h + 5, 2.6), "inlay", color="deep"))


def _tailored(p, block) -> Shape:
    """A tailored jacket or coat, front view, built as one rather than as a shirt with lapels: drawn from
    the flat measurements of a real 40R two-button jacket (BLOCKS["jacket"]) or overcoat (BLOCKS["coat"]).
    A structured, nearly square shoulder with the sleeve hung from the body's edge; a suppressed waist; the
    collar wrapping the back of the neck and meeting the lapel at the gorge; the lapels rolling to the top
    button, the V between them showing the inside of the jacket; front edges curving away below the bottom
    button; a breast welt, two hip pockets, front darts and four buttons at each cuff."""
    B, T = BLOCKS[block], TAILORING[block]
    k_ = K_PX
    coat = block == "coat"
    fit = p["fit"] if p["fit"] in JACKET_FIT else "regular"
    dch, dwa, dhe, dbi, dle = JACKET_FIT[fit]
    wt = WEIGHT_LEVEL.get(p.get("weight"), 1)
    ease = (0.98, 1.0, 1.04, 1.08)[wt]             # a heavier cloth stands away from the body
    bulk = (-1.0, 0.0, 3.0, 6.0)[wt]
    chest = (B["chest"] + dch) / 2 * k_ * ease * BODY_W   # the same share of the flat width as every top
    waist_w = (B["waist"] + dwa) / 2 * k_ * ease * BODY_W
    hh = (B["hem"] + dhe) / 2 * k_ * ease * BODY_W
    # the same rule as every top: the shoulder point just outside the chest's width, the armhole down its edge
    hs = chest + 5 + (0.6, 0, 1.2, 2.4)[wt] / 2 * k_
    length = B["length"] + dle
    length = {"cropped": length * 0.84, "long": length + 9, "knee": max(length + 30, 105)}.get(p["length"], length)
    sy = 80.0
    ny = sy - 10.0                                  # the high shoulder point: the shoulder is padded nearly square
    hy = min(ny + length * k_, H - 30.0)
    wy = ny + B.get("waist_at", 46) * k_
    ay = min(sy + B["depth"] * 1.45 * k_ + bulk * 0.5, wy - 18)
    nw = 36.0 + bulk * 0.4
    N, S = (CX + nw, ny), (CX + hs, sy)
    A = (CX + chest, ay)
    side = _side_points(A, (CX + waist_w, max(wy, ay + 20)), (CX + hh, hy))
    u = _unit((S[0] - N[0], S[1] - N[1]))
    sh = Shape(outline="", tailored=True)
    ml = _mirror

    # ---- sleeves
    sleeve = p["sleeve"] if p["sleeve"] in ("none", "short", "elbow", "three-quarter", "long") else "long"
    if sleeve == "none":   # a waistcoat's narrower shoulder and a cut-away armhole
        S = (N[0] + u[0] * (hs - nw) * 0.8, N[1] + u[1] * (hs - nw) * 0.8)
        A = (CX + chest - 2, ay)
        c1, c2 = (S[0] - 4, S[1] + 50), (A[0] - 20, A[1] - 6)
        side = _side_points(A, (CX + waist_w, max(wy, ay + 20)), (CX + hh, hy))
        arm = f"C {_pt(c1)} {_pt(c2)} {_pt(A)}"
        arm_l = f"C {_pt(ml(c2))} {_pt(ml(c1))} {_pt(ml(S))}"
    else:
        r = 4.0 + bulk * 0.8                         # a crisp corner where the sleeve head meets the padded shoulder
        K = (S[0] + u[0] * r, S[1] + u[1] * r)
        frac = {"long": 1.0, "three-quarter": 0.74, "elbow": 0.5, "short": 0.36}[sleeve]
        ln = (B["sleeve"] + (2 if fit == "oversized" else 0)) * k_ * frac
        w_want = (B["bicep"] + dbi) * k_ * ease * 0.72
        cw0 = (B["cuff"] * 0.9 if sleeve == "long" else B["cuff"] + (B["bicep"] - B["cuff"]) * (1 - frac)) * k_ * ease

        def build(th):
            t = math.radians(th)
            d, q = (math.sin(t), math.cos(t)), (-math.cos(t), math.sin(t))   # down the sleeve; across it, toward the body
            Co = (K[0] + d[0] * ln, K[1] + d[1] * ln)
            w_top = abs((A[0] - K[0]) * d[1] - (A[1] - K[1]) * d[0])         # the sleeve's width where it leaves the body
            cw = min(cw0, 0.86 * w_top)                                        # always narrower at the cuff
            return d, q, Co, (Co[0] + q[0] * cw, Co[1] + q[1] * cw), w_top

        # the sleeve swings out until it is as wide as the arm (or hangs as far out as a sleeve does) and its
        # cuff is clear of the body, or it reaches the card's edge
        th = 10.0
        while th < 40 and build(th + 0.5)[2][0] <= W - 8:
            d, q, Co, Ci, w_top = build(th)
            if (w_top >= w_want or th >= SLEEVE_HANG) and Ci[0] > _x_on(side, Ci[1]) + SLEEVE_GAP:
                break
            th += 0.5
        while th > 0 and build(th)[2][0] > W - 8:
            th -= 0.5
        d, q, Co, Ci, w_top = build(th)
        P1 = (K[0] + d[0] * r, K[1] + d[1] * r)
        # a rounded underarm: the outline leaves the sleeve's inner edge and joins the side a little below A
        fl = UNDERARM + bulk
        e = _unit((Ci[0] - A[0], Ci[1] - A[1]))
        E1 = (A[0] + e[0] * fl, A[1] + e[1] * fl)
        E2, cut = _along(side, fl)
        side = [E2] + side[cut:]
        arm = f"Q {_pt(K)} {_pt(P1)} L {_pt(Co)} L {_pt(Ci)} L {_pt(E1)} Q {_pt(A)} {_pt(E2)}"
        arm_l = (f"Q {_pt(ml(A))} {_pt(ml(E1))} L {_pt(ml(Ci))} L {_pt(ml(Co))} L {_pt(ml(P1))} "
                 f"Q {_pt(ml(K))} {_pt(ml(S))}")
        s1, s2 = (S[0] - 3, S[1] + (A[1] - S[1]) * 0.35), (A[0] + 4, A[1] - (A[1] - S[1]) * 0.3)
        right_sleeve = (f"M {_pt(S)} Q {_pt(K)} {_pt(P1)} L {_pt(Co)} L {_pt(Ci)} L {_pt(A)} "
                        f"C {_pt(s2)} {_pt(s1)} {_pt(S)} Z")
        sh.sleeves = [(right_sleeve, -th), (_mirror_path(right_sleeve), th)]
        c1, c2 = s1, s2
        if sleeve == "long":   # four buttons along the vent at each cuff, side by side, just apart
            br = CUFF_BUTTON + bulk * 0.1
            for i in range(4):
                a_ = 9 + (2 * br + 1.2) * i
                b = (Co[0] + q[0] * 6.5 - d[0] * a_, Co[1] + q[1] * 6.5 - d[1] * a_)
                sh.dots += [(b[0], b[1], br), (ml(b)[0], ml(b)[1], br)]
    for m in (lambda v: v, ml):   # the armhole seam runs down the edge of the body
        sh.seams.append(f"M {_pt(m(S))} C {_pt(m(c1))} {_pt(m(c2))} {_pt(m(A))}")

    # ---- the stance: where the front buttons, and where the lapels roll from
    dbl = p["front"] == "double"
    n_b = p.get("buttons")
    if p["front"] not in ("buttons", "double", "half", "popover", "french", "hidden"):
        n_b = 0
    elif n_b is None:
        n_b = 6 if dbl else (3 if coat else 2)
    n_b = max(0, int(n_b))
    roll3 = None                                    # three-roll-two: the top buttonhole shows on the lapel
    if dbl:   # 6x2: rows of two; the fastening row, one below it, the rest above the break for show
        # Told one or two buttons, those are the ones that fasten (6x1, 6x2): a double-breasted front shows
        # six. Told more, that is every button on it.
        rows = 3 if n_b <= 2 else max(2, min(4, n_b // 2))
        sp = T["db_spacing"] * k_
        yf = ny + T["db_stance"] * k_
        above = rows - 2 if rows >= 3 else 0
        ys = [yf + (i - above) * sp for i in range(rows)]
        # 6x1: the lapels roll down to the bottom row, the only one that fastens
        y_break, ov = (ys[-1] if n_b == 1 else yf) - 4, 32.0 + bulk
    else:
        sp = T["spacing"] * k_
        yb = ny + T["stance"] * k_
        if coat:
            ys = [y for y in (yb + i * sp for i in range(max(n_b, 1))) if y <= hy - 45]
        elif n_b <= 1:
            ys = [yb]
        elif n_b <= 3:
            ys = [yb, yb + sp]
            roll3 = yb - sp if n_b == 3 else None
        else:
            n = min(n_b, 6)
            top = max(ny + 70, yb + sp - (n - 1) * sp)
            ys = [top + (yb + sp - top) * i / (n - 1) for i in range(n)]
        y_break, ov = ys[0] - 4, 6.6
        ys = ys if n_b else []
    Bk = (CX - ov, y_break)
    Rt = (CX + 22.0 + bulk * 0.4, ny)
    roll_x = lambda y: Bk[0] + (Rt[0] - Bk[0]) * (Bk[1] - y) / (Bk[1] - Rt[1])
    Tt = (roll_x(ny - 10 - bulk * 0.3), ny - 10 - bulk * 0.3)   # the collar's fold, where it turns behind the neck
    top_c = ny - 17 - bulk * 0.5
    ur = _unit((Rt[0] - Bk[0], Rt[1] - Bk[1]))
    nr = (-ur[1], ur[0])                            # square to the roll line, out toward the shoulder

    # ---- collar and lapels (right side: the wearer's left, which lies on top)
    cs = p.get("collar") if p.get("collar") in ("notch", "peak", "shawl") else "notch"
    grow = max(0.0, dch) * LAPEL_GROW               # a fuller cut has broader lapels, in cm
    nt = _qbez(N, (N[0], Tt[1] + 2), Tt, 6)          # the collar's edge from the shoulder up behind the neck
    if cs == "shawl":   # one smooth roll from the top button round the neck, no notch
        wsh = (9 + grow) * k_ + bulk * 0.6
        y1 = Bk[1] - (Bk[1] - ny) * 0.45
        outer = [Bk] + _bez(Bk, (roll_x(y1) + wsh * 1.05, y1), (N[0] + wsh * 0.4, ny + 30), N, 16)
        pieces = [(outer + nt + [Rt], [Tt, Rt] + outer)]
        edge_pts = outer
    else:
        lw = (T["db_lapel"] if dbl else T["lapel"] + (1.25 if cs == "peak" else 0)) * k_ + grow * k_ + bulk * 0.5
        y_g = ny + T["gorge"] * k_
        Ry = y_g - nr[1] * lw
        P = (roll_x(Ry) + nr[0] * lw, y_g)          # the lapel's widest point, at the height of the gorge
        a = math.radians(22)
        g = (-math.cos(a), -math.sin(a))            # the gorge rises gently toward the neck
        G = _cross(P, (P[0] + g[0], P[1] + g[1]), Bk, Rt)
        pg = math.hypot(G[0] - P[0], G[1] - P[1])
        belly = 3.0
        if cs == "peak":   # the point turns up toward the shoulder; the collar tucks in under it
            X = (P[0] + g[0] * min(15, 0.55 * pg), P[1] + g[1] * min(15, 0.55 * pg))
            Tp = (P[0] + 0.22 * lw, P[1] - 0.52 * lw)
            sl_y = ny + (sy - ny) * (Tp[0] - N[0]) / (S[0] - N[0])
            Tp = (Tp[0], max(Tp[1], sl_y + 6))
            v = _unit((Tp[0] - X[0], Tp[1] - X[1]))
            cl = min(11, 0.7 * math.hypot(Tp[0] - X[0], Tp[1] - X[1]))
            Cp = (X[0] + _rot(v, -20)[0] * cl, X[1] + _rot(v, -20)[1] * cl)
            tip = [Tp]
            belly = 5.0
        else:              # a notch: the collar's end and the lapel part at about 80 degrees
            X = (P[0] + g[0] * min(13, 0.48 * pg), P[1] + g[1] * min(13, 0.48 * pg))
            v = _rot((-g[0], -g[1]), -80)
            Cp = (X[0] + v[0] * 11.5, X[1] + v[1] * 11.5)
            tip = []
        mid = _lerp(Bk, P, 0.5)
        vb = _unit((P[0] - Bk[0], P[1] - Bk[1]))
        edge_pts = [Bk] + _qbez(Bk, (mid[0] - vb[1] * belly, mid[1] + vb[0] * belly), P, 12)
        if roll3:   # three-roll-two: below the top buttonhole the lapel is not pressed flat but rolls softly over
            # the top button down to the middle one, so it is broad there, not a point
            Q3 = (roll_x(roll3) + 11 + bulk * 0.5, roll3)
            v3 = _unit((P[0] - Q3[0], P[1] - Q3[1]))
            m3 = _lerp(Q3, P, 0.5)
            low = [Bk] + _qbez(Bk, (Q3[0] - v3[0] * 10, Q3[1] - v3[1] * 10), Q3, 6)
            edge_pts = low + _qbez(Q3, (m3[0] - v3[1] * belly, m3[1] + v3[0] * belly), P, 10)
        mc = _lerp(Cp, N, 0.5)
        outer_c = [Cp] + _qbez(Cp, (mc[0] + 3, mc[1]), N, 6)
        leaf = [G, X] + outer_c + nt + [Rt]
        lapel = edge_pts + tip + [X, G]
        pieces = [(leaf, [Tt, Rt, G, X] + outer_c), (lapel, [G] + edge_pts + tip + [X])]
    # the opening between the roll lines shows the inside; above it, the collar's band behind the neck
    t = (CX - Bk[0]) / (Rt[0] - Bk[0]) if Rt[0] != Bk[0] else 0.0
    Xc = _lerp(Bk, Rt, t)
    rim = f"M {_pt(ml(Rt))} Q {_pt((CX, ny - 3))} {_pt(Rt)}"
    sh.parts.append(Part(f"M {_pt(Xc)} L {_pt(Rt)} Q {_pt((CX, ny - 3))} {_pt(ml(Rt))} Z", "hole"))
    sh.parts.append(Part(f"M {_pt(Tt)} Q {_pt((CX, top_c))} {_pt(ml(Tt))} L {_pt(ml(Rt))} "
                         f"Q {_pt((CX, ny - 3))} {_pt(Rt)} Z", "lapel_l"))
    sh.parts.append(Part(rim, "edge"))

    # ---- front edges: straight to the bottom button, then the quarters curve away into a rounded hem
    if dbl or coat:
        rc = 8.0
        front_run = [Bk, (CX - ov, hy - rc)] + _qbez((CX - ov, hy - rc), (CX - ov, hy), (CX - ov + rc, hy), 4)
    else:
        y_q = (ys[-1] if ys else Bk[1] + 4) + (10 if len(ys) <= 1 else 5)
        y_q = min(y_q, hy - 24)
        Qs, Qe = (CX - ov, y_q), (CX + 0.42 * hh, hy)
        curve = [Qs] + _bez(Qs, (CX - ov, y_q + (hy - y_q) * 0.55), (Qe[0] - (Qe[0] - Qs[0]) * 0.5, hy), Qe, 16)
        front_run = [Bk] + curve
        i = next(i for i, v in enumerate(curve) if v[0] >= CX)
        C = _lerp(curve[i - 1], curve[i], (CX - curve[i - 1][0]) / (curve[i][0] - curve[i - 1][0]))
        after = [C] + curve[i:]
        # below where the two fronts part, the inside of the back shows between them
        sh.parts.append(Part(_poly(after + [ml(v) for v in after[::-1]]), "hole"))
        sh.parts.append(Part(_poly([ml(v) for v in after], close=False), "edge"))
    keep = (10.0, Bk[1])
    for pts, run in pieces:   # the under (viewer's left) side first, cut where the top front's roll line crosses it
        lp = _clip_half([ml(v) for v in pts], Bk, Rt, keep)
        if len(lp) >= 3:
            sh.parts.append(Part(_poly(lp), "lapel_l"))
            lr = _clip_run([ml(v) for v in run], Bk, Rt, keep)
            if len(lr) >= 2:
                sh.parts.append(Part(_poly(lr, close=False), "edge"))
    for pts, run in pieces:
        sh.parts.append(Part(_poly(pts), "lapel_r"))
        sh.parts.append(Part(_poly(run, close=False), "edge"))
    sh.parts.append(Part(_poly(front_run, close=False), "edge"))
    edge_x = lambda y: _x_on(edge_pts, y)          # the top lapel's outer edge

    # ---- buttons and buttonholes
    rb = 3.6 + bulk * 0.15
    for y in ys:
        if not dbl:
            sh.dots.append((CX, y, rb))
            continue
        if y < y_break:   # rows above the break are set wider, for show
            xl, xr = min(CX - 26 - bulk, roll_x(y) - 7), max(CX + 26 + bulk, edge_x(y) + 7)
        else:
            xl, xr = CX - 19 - bulk, CX + 19 + bulk
        sh.dots += [(xl, y, rb), (xr, y, rb)]
    if roll3 and cs != "shawl":   # the top buttonhole on the roll of the lapel; its button is hidden under it
        x0, x1 = roll_x(roll3), edge_x(roll3) - 3.5   # it runs on under the roll
        sh.lines.append(f"M {_pt((x0, roll3))} L {_pt((x1, roll3))} M {_pt((x1 + 1.2, roll3))} "
                        f"A 1.2 1.2 0 1 0 {_pt((x1 - 1.2, roll3))} A 1.2 1.2 0 1 0 {_pt((x1 + 1.2, roll3))}")
    if cs != "shawl":   # the lapel buttonhole, just below the notch
        yh = y_g + 14
        c = (roll_x(yh) + (edge_x(yh) - roll_x(yh)) * 0.5, yh)
        sh.lines.append(f"M {_pt((c[0] - 3.7, c[1] - 1.5))} L {_pt((c[0] + 3.7, c[1] + 1.5))}")

    # ---- pockets and darts
    kind = p["pockets"]
    if kind.startswith("chest") or kind in ("pencil", "western", "none"):
        lower = "none"
    else:
        lower = {"hip-patch": "patch", "chore": "patch", "low": "patch", "welt": "jetted",
                 "slash": "slash", "split": "slash", "kangaroo": "slash"}.get(kind, "flap")
    pw = 15.5 * k_
    yp = min(ny + T["pocket"] * k_, hy - 30)
    p_bot = {"flap": yp + 18, "patch": min(yp + 52, hy - 9), "jetted": yp + 4}.get(lower, yp)
    x0 = CX + 0.3 * hh
    x0 = max(x0, _x_on(front_run, p_bot) + 7, _x_on(front_run, yp) + 7)
    x1 = min(x0 + pw, _x_on(side, p_bot) - 8, _x_on(side, yp) - 8)
    pocket = []
    if lower == "flap":
        fh = 18.0
        pocket = [f"M {_pt((x0 - 1, yp))} L {_pt((x1 + 1, yp))}",
                  f"M {_pt((x0, yp))} L {_pt((x0, yp + fh - 3))} Q {_pt((x0, yp + fh))} {_pt((x0 + 3, yp + fh))} "
                  f"L {_pt((x1 - 3, yp + fh))} Q {_pt((x1, yp + fh))} {_pt((x1, yp + fh - 3))} L {_pt((x1, yp))}"]
    elif lower == "jetted":
        pocket = [f"M {_pt((x0, yp))} L {_pt((x1, yp))} L {_pt((x1, yp + 3.2))} L {_pt((x0, yp + 3.2))} Z"]
    elif lower == "patch":
        yt, rp = yp - 4, 7.0
        pocket = [f"M {_pt((x0, yt))} L {_pt((x0, p_bot - rp))} Q {_pt((x0, p_bot))} {_pt((x0 + rp, p_bot))} "
                  f"L {_pt((x1 - rp, p_bot))} Q {_pt((x1, p_bot))} {_pt((x1, p_bot - rp))} L {_pt((x1, yt))} Z",
                  f"M {_pt((x0, yt + 6))} L {_pt((x1, yt + 6))}"]
    elif lower == "slash":   # a coat's hand-warmers: slanted welts at the waist, the top toward the front
        xs_ = CX + 0.58 * hh
        xb_ = min(xs_ + 12, _x_on(side, wy + 46) - 16)
        pocket = [_poly([(xs_, wy - 8), (xs_ + 6, wy - 8), (xb_ + 6, wy + 46), (xb_, wy + 46)])]
    for d_ in pocket:
        sh.lines += [d_, _mirror_path(d_)]
    if kind != "none" and lower != "slash":   # the breast welt, on the wearer's left only, rising to the outside
        yc = ny + T["breast"] * k_
        b0 = max(CX + 0.36 * chest, edge_x(yc + 8) + 7)
        b1 = min(b0 + 10 * k_, CX + chest - 10)
        sh.lines.append(_poly([(b0, yc), (b1, yc - 4), (b1, yc + 4), (b0, yc + 8)]))
    if not coat and lower != "slash":   # front darts, from below the chest into the hip pocket
        xd = x0 + pw * 0.42 if lower != "none" else CX + 0.55 * chest
        yd0 = ny + T["breast"] * k_ + 26
        yd1 = (yp - 4 if lower == "patch" else yp) - 1
        dart = f"M {_pt((xd + 1, yd0))} Q {_pt((xd - 2.5, wy))} {_pt((xd, yd1))}"
        sh.seams += [dart, _mirror_path(dart)]

    # ---- outline, clockwise from the right neck point
    side_r = " ".join(f"L {_pt(v)}" for v in side[1:])
    side_l = " ".join(f"L {_pt(ml(v))}" for v in side[::-1][1:])
    neck_path = (f"Q {_pt((ml(N)[0], Tt[1] + 2))} {_pt(ml(Tt))} Q {_pt((CX, top_c))} {_pt(Tt)} "
                 f"Q {_pt((N[0], Tt[1] + 2))} {_pt(N)}")
    sh.outline = " ".join(f"M {_pt(N)} L {_pt(S)} {arm} {side_r} L {_pt(ml(side[-1]))} {side_l} {arm_l} "
                          f"L {_pt(ml(N))} {neck_path} Z".split())
    sh.anchors = {"neck": (CX, 58.0), "shoulder_l": (CX - 23 * K_PX, 80.0), "shoulder_r": (CX + 23 * K_PX, 80.0),
                  "hem": (CX, hy), "neck_point_l": ml(N), "neck_point_r": N}
    sh.body_box = (CX - chest, sy, CX + chest, hy)
    xs = [float(x) for x, _ in re.findall(r"(-?[\d.]+),(-?[\d.]+)", sh.outline)]
    xmax = max(max(xs), 2 * CX - min(xs))
    sh.bbox = (2 * CX - xmax, (Tt[1] + top_c) / 2 - 2, xmax, hy + 2)
    if p.get("belt"):
        _belt(sh, wy, hh, p["belt"])
    if p.get("state") == "open" and p["front"] != "none":   # the top front's edge: the roll line, then the front
        sh.fronts = ([Rt] + front_run + [(front_run[-1][0], hy + 20)], "horizontal")
    return sh


def _capsule_h(x0, x1, y, h) -> str:
    """A horizontal rounded bar: a collar pin, a cufflink."""
    r = h / 2
    return (f"M {_pt((x0 + r, y - r))} L {_pt((x1 - r, y - r))} A {_f(r)} {_f(r)} 0 0 1 {_pt((x1 - r, y + r))} "
            f"L {_pt((x0 + r, y + r))} A {_f(r)} {_f(r)} 0 0 1 {_pt((x0 + r, y - r))} Z")


def _lapels(sh, cs, ny, N, TR, TL, k, rise, front, bulk, hy):
    """Open collars that roll into lapels (or a shirt's revers): the V shows the inside of the
    garment; each side is a collar piece and a lapel piece meeting at the gorge, with a notch
    where they part. The fronts overlap, the wearer's left (viewer's right) on top, so the under
    lapel is cut where the top one crosses it. Returns ("lapel", break y, overlap)."""
    dbl = front == "double"
    knit = cs == "shawl_knit"
    if cs == "camp":
        yb, ov = ny + 66, 7.0
    elif knit:
        yb, ov = ny + (100 if front != "none" else 84), 6.0
    else:
        yb, ov = (ny + 118, 30.0) if dbl else (ny + 134, 7.0)
    if front == "none" and not knit:
        ov = 0.0
    a, c1, c2, b = (CX + 27, ny - 12.5 * k), (CX + 30, ny - 16.5 * k), (CX + 29.5, ny - 23.5 * k), (CX + 20, ny - 25.5 * k)
    A0 = (CX - ov, yb)
    xr = lambda y: A0[0] + (a[0] - A0[0]) * (yb - y) / (yb - a[1])
    back_top = [(CX, ny - 30.75 * k)] + _qbez((CX, ny - 30.75 * k), (CX + 16.25, ny - 30.75 * k), TR, 6)
    fold = [b] + _qbez(b, (CX + 10, ny - 26.95 * k), (CX, ny - 26.95 * k), 5)
    rim = [a] + _bez(a, c1, c2, b, 8)      # up the inside of the collar, a -> b
    # the collar's back part, from the shoulder point round behind the neck to the fold and down to a
    behind = [N] + back_top[::-1] + fold[::-1] + rim[::-1][1:]
    pieces = []   # (points, role suffix kind) for the right side; left ones are mirrored and clipped
    if cs in ("shawl", "shawl_knit"):
        wsh = (34.0 if not knit else 30.0) + bulk
        outer = [A0] + _bez(A0, (CX + wsh * 0.9, yb - (yb - ny) * 0.42), (N[0] + wsh * 0.42, ny + 34), N, 16)
        pieces.append((outer + behind[1:] + [a], outer, False))
    else:
        if cs == "camp":
            yn, wl, gd, clen, ang = ny + 40, 19.0, 8.0, 33.0, -22.0
        else:
            yn, wl, gd, clen, ang = ny + 40, (38.0 if dbl else 31.0) + bulk * 0.6, 10.0, 15.0, -72.0
        Pn = (xr(yn) + wl, yn)
        G = (xr(yn - gd), yn - gd)
        X = _lerp(G, Pn, 0.55 if cs != "camp" else 0.45)
        if cs == "peak":
            Pn = (xr(yn) + wl + 7, yn - 17)
            X = _lerp(G, (xr(yn) + wl, yn), 0.55)
            v = _unit((Pn[0] - X[0], Pn[1] - X[1]))
            Cp = (X[0] + _rot(v, -30)[0] * 13, X[1] + _rot(v, -30)[1] * 13)
        else:
            v = _unit((Pn[0] - X[0], Pn[1] - X[1]))
            Cp = (X[0] + _rot(v, ang)[0] * clen, X[1] + _rot(v, ang)[1] * clen)
        mid = _lerp(A0, Pn, 0.5)
        nrm = _unit((Pn[1] - A0[1], -(Pn[0] - A0[0])))
        nrm = nrm if nrm[0] > 0 else (-nrm[0], -nrm[1])
        front_edge = [A0] + _qbez(A0, (mid[0] + nrm[0] * 4, mid[1] + nrm[1] * 4), Pn, 12)
        lapel_pts = front_edge + [X, G]
        mc = _lerp(Cp, N, 0.5)
        out_c = (mc[0] + (3 if cs == "camp" else 5), mc[1])
        run = [G, X, Cp] + _qbez(Cp, out_c, N, 8)
        pieces.append((run[:-1] + behind + [a], run, False))
        pieces.append((lapel_pts, lapel_pts, True))
    # the opening: between the two roll lines, above where they cross
    t = (CX - A0[0]) / (a[0] - A0[0]) if a[0] != A0[0] else 0.0
    Xc = _lerp(A0, a, t)
    hole = [Xc] + rim + _qbez(b, (CX, ny - 28.4 * k), _mirror(b), 8) + [_mirror(v) for v in rim[::-1]]
    sh.parts.append(Part(_poly(hole), "hole"))
    sh.parts.append(Part(_poly(hole), "edge"))
    # each piece is stroked only along its visible edges, never across the back where the two sides meet
    for pts, run, closed in pieces:   # the under (viewer's left) side first, cut where the top front crosses it
        lp = _clip_half([_mirror(v) for v in pts], A0, a, _mirror(a))
        if len(lp) >= 3:
            sh.parts.append(Part(_poly(lp), "collar_l"))
            lr = _clip_half([_mirror(v) for v in run], A0, a, _mirror(a)) if closed else _clip_run([_mirror(v) for v in run], A0, a, _mirror(a))
            if len(lr) >= 2:
                sh.parts.append(Part(_poly(lr, close=closed), "edge"))
    for pts, run, closed in pieces:
        sh.parts.append(Part(_poly(pts), "collar_r"))
        sh.parts.append(Part(_poly(run, close=closed), "edge"))
    if cs in ("shawl", "shawl_knit") and Xc[1] < yb - 0.5:   # the top shawl's fold, below where the V closes
        sh.parts.append(Part(_poly([Xc, A0], close=False), "edge"))
    return ("lapel", yb, ov)


def _pockets(sh, kind, sy, hy, hh, hs, hem, cuff, A, rib_h, lapel_front, block=False):
    color = "block" if block else None   # colour-blocking: patch pockets and their flaps in the second colour

    def patch(x, y, w, h, flap=True):
        d = (f"M {_pt((x, y))} L {_pt((x, y + h - 6))} Q {_pt((x, y + h))} {_pt((x + 6, y + h))} "
             f"L {_pt((x + w - 6, y + h))} Q {_pt((x + w, y + h))} {_pt((x + w, y + h - 6))} L {_pt((x + w, y))} Z")
        if block:
            sh.parts.append(Part(d, "block"))
        sh.lines.append(d)
        if flap:
            sh.lines.append(f"M {_pt((x, y + 13))} L {_pt((x + w / 2, y + 19))} L {_pt((x + w, y + 13))}")
        else:   # a plain patch pocket: just the stitched hem across its top
            sh.lines.append(f"M {_pt((x, y + 6))} L {_pt((x + w, y + 6))}")

    def flapped(x, y, w, h, bellows=False, button=True, point=True):
        """A patch pocket under a separate buttoned flap; bellows show their folded sides."""
        fy = y + 12
        d = (f"M {_pt((x, fy))} L {_pt((x, y + h - 6))} Q {_pt((x, y + h))} {_pt((x + 6, y + h))} "
             f"L {_pt((x + w - 6, y + h))} Q {_pt((x + w, y + h))} {_pt((x + w, y + h - 6))} L {_pt((x + w, fy))}")
        if block:
            sh.parts.append(Part(d + " Z", "block"))
        sh.lines.append(d)
        if bellows:
            sh.lines.append(f"M {_pt((x + 3.5, fy))} L {_pt((x + 3.5, y + h - 3.5))} L {_pt((x + w - 3.5, y + h - 3.5))} L {_pt((x + w - 3.5, fy))}")
        fl = [(x - 1.5, y - 1), (x + w + 1.5, y - 1), (x + w + 1.5, fy)] + ([(x + w / 2, fy + 5)] if point else []) + [(x - 1.5, fy)]
        sh.parts.append(Part(_poly(fl), "cuff", color=color))
        if button:
            sh.dots.append((x + w / 2, fy + (1 if point else -4), 2.4))

    chest_y = sy + 72
    lo_y = hy - 86 - (rib_h - 6 if hem == "rib" else 0)
    lw = min(50, hh - 24)
    if kind == "chest":
        patch(CX + 21, chest_y, 38, 44, flap=False)
    elif kind in ("chest-low", "chest-two"):
        patch(CX + 21, chest_y, 38, 44)
        patch(CX - 59, chest_y, 38, 44)
    elif kind == "chest-flap":
        flapped(CX + 21, chest_y - 4, 38, 46)
    elif kind == "chest-flap-two":
        flapped(CX + 21, chest_y - 4, 38, 46)
        flapped(CX - 59, chest_y - 4, 38, 46)
    elif kind == "chest-patch-two":
        patch(CX + 21, chest_y, 38, 44, flap=False)
        patch(CX - 59, chest_y, 38, 44, flap=False)
    elif kind == "pencil":   # a chest pocket with a narrow slot stitched down its inner side
        patch(CX + 21, chest_y, 38, 44, flap=False)
        sh.lines.append(f"M {_pt((CX + 29, chest_y + 6))} L {_pt((CX + 29, chest_y + 38))}")
    elif kind == "western":  # curved "smile" slits with arrow tacks at each end
        for m in (lambda v: v, _mirror):
            x0, x1, y = CX + 24, CX + 58, chest_y + 2
            sh.lines.append(f"M {_pt(m((x0, y)))} Q {_pt(m(((x0 + x1) / 2, y + 11)))} {_pt(m((x1, y)))}")
            for xe in (x0, x1):
                sh.lines.append(f"M {_pt(m((xe - 3.2, y + 3)))} L {_pt(m((xe, y - 3.5)))} L {_pt(m((xe + 3.2, y + 3)))}")
    elif kind == "chore":    # one chest patch, two big low ones
        patch(CX + 21, chest_y, 38, 44, flap=False)
        w = min(54, hh - 22)
        patch(CX + hh - 12 - w, lo_y - 6, w, 58, flap=False)
        patch(CX - hh + 12, lo_y - 6, w, 58, flap=False)
    elif kind == "guayabera":   # four patch pockets with buttoned points, and the rows of pleats
        for m in (lambda v: v, _mirror):
            for x in (CX + 30, CX + 35):   # seams: the pocket flaps lie over them
                sh.seams.append(f"M {_pt(m((x, sy + 22)))} L {_pt(m((x, hy - 14)))}")
        flapped(CX + 21, chest_y - 2, 36, 40, point=True)
        flapped(CX - 57, chest_y - 2, 36, 40, point=True)
        w = min(46, hh - 26)
        flapped(CX + hh - 14 - w, lo_y, w, 50, point=True)
        flapped(CX - hh + 14, lo_y, w, 50, point=True)
    elif kind == "bellows":  # a field jacket's four pleated pockets
        flapped(CX + 20, chest_y - 6, 40, 48, bellows=True, point=False)
        flapped(CX - 60, chest_y - 6, 40, 48, bellows=True, point=False)
        w = min(54, hh - 22)
        flapped(CX + hh - 12 - w, lo_y - 4, w, 58, bellows=True, point=False)
        flapped(CX - hh + 12, lo_y - 4, w, 58, bellows=True, point=False)
    elif kind == "welt":     # two jetted slits low on the front
        for m in (lambda v: v, _mirror):
            x0, y = CX + 18, lo_y + 14
            sh.lines.append(_poly([m((x0, y)), m((x0 + lw - 4, y - 3)), m((x0 + lw - 4, y + 3)), m((x0, y + 6))]))
    elif kind == "slash":    # steep slanted hand-warmer slits, with a narrow welt
        for m in (lambda v: v, _mirror):
            top = (CX + hh - 34, lo_y - 18)
            bot = (CX + hh - 22, lo_y + 46)
            sh.lines.append(_poly([m(top), m(bot), m((bot[0] + 6, bot[1] - 1)), m((top[0] + 6, top[1] - 1))]))
    elif kind == "split":    # a zip hoodie's pouch in two halves
        y1 = hy - (rib_h if hem == "rib" else 8)
        y0, wt_, wb = y1 - 72, 30.0, min(54.0, hh - 22)
        for m in (lambda v: v, _mirror):
            sh.lines.append(f"M {_pt(m((CX + 5, y0)))} L {_pt(m((CX + wt_, y0)))} L {_pt(m((CX + wb, y0 + 40)))} L {_pt(m((CX + wb, y1)))}")
    elif kind == "utility" and cuff:   # a zipped pocket on the upper left sleeve (viewer's right)
        Co, Ci, d = cuff
        qv = _unit((Ci[0] - Co[0], Ci[1] - Co[1]))
        base = (A[0] + 12, A[1] + 8)   # just past the underarm, on the sleeve
        c = (base[0] + d[0] * 26 - qv[0] * 6, base[1] + d[1] * 26 - qv[1] * 6)
        w, h = 20.0, 30.0
        corners = [(c[0] + qv[0] * sx * w / 2 + d[0] * sy_ * h / 2, c[1] + qv[1] * sx * w / 2 + d[1] * sy_ * h / 2)
                   for sx, sy_ in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        sh.lines.append(_poly(corners))
        z0, z1 = _lerp(corners[0], corners[3], 0.2), _lerp(corners[1], corners[2], 0.2)
        sh.lines.append(_poly([z0, z1], close=False))
    elif kind in ("hip-patch", "hip-flap"):   # a pair of pockets low on the front, at hip level
        w = min(52, hh - 22)
        for x in (CX + hh - 13 - w, CX - hh + 13):
            if kind == "hip-patch":
                patch(x, lo_y - 2, w, 54, flap=False)
            else:
                flapped(x, lo_y - 6, w, 58, point=False)
    if kind in ("low", "chest-low"):   # sized from the body so they clear the side seam and the placket
        w = min(50, hh - 24)
        patch(CX + hh - 14 - w, hy - 86, w, 52)
        patch(CX - hh + 14, hy - 86, w, 52)
    if kind == "kangaroo":   # a hoodie's pouch: slanted openings either side
        y1 = hy - (18 if hem == "rib" else 8)
        y0, wt_, wb = y1 - 76, 36.0, min(54.0, hh - 22)
        sh.lines.append(f"M {_pt((CX - wt_, y0))} L {_pt((CX + wt_, y0))} L {_pt((CX + wb, y0 + 40))} L {_pt((CX + wb, y1))} "
                        f"M {_pt((CX - wt_, y0))} L {_pt((CX - wb, y0 + 40))} L {_pt((CX - wb, y1))}")


# -------------------------------------------------------------------- pants

PANTS_DEFAULTS = dict(leg="straight", length="full", jeans=False)
# Optional details, each read off a photo (defaults follow `jeans`):
#   waist   belt | elastic | drawstring      how it fastens; elastic/drawstring have no fly
#   pockets scoop | slant | none             front pocket opening (scoop = jeans' curved one)
#   cargo   False | True                     bellows pockets on the outer thighs
#   pleats  0 | 1 | 2                        per side; pleated trousers also get a crease
#   crease  False | True                     pressed front crease (dress trousers)
#   hem     stitched | plain | turnup | rib | split   visible topstitch, blind hem, turn-up cuff, knit cuff
#           (joggers), a running short's slit at the side
#   stripe  none | side                      a stripe down each outer seam (track trousers), in the trim colour
# leg also takes skinny (compression tights) and length brief (running shorts: a short inseam).
#   coin    True | False                     jeans' watch pocket and rivets
#   rivets  True | False                     rivets at the front pocket corners (default: with the watch pocket)
#   stitch  tonal | contrast                 jeans' topstitch drawn in gold thread as well
# The owner's bottoms block adds (each optional; the defaults draw what the lines above draw):
#   waist   + adjusters | gurkha | tab | braces | half_elastic   only a belt waist has loops
#   fly     zip | button | none              a button fly shows its buttons; a pull-on has none
#   rise    low | mid | high                 how deep the crotch sits below the waist (23 / 27 / 31 cm); the hem stays put
#   leg     + skinny | slim | relaxed | bootcut | flare | barrel
#   pleat_dir reverse | forward              which way a pleat opens (toward the pocket, or toward the fly)
#   break   none | slight | full | stacked   folds where the hem meets the shoe
#   hem     + rolled | raw | split | notched | chain   a rolled cuff, a frayed edge, a side slit, a V notch at the
#           outer seam, chain-stitched roping
#   pockets + side | frog | none             on the side seam; a horizontal frog-mouth opening
#   extra_pockets [zip, rule, hammer]        a zipped thigh pocket, a carpenter's rule pocket and hammer loop
#   panels  [double_knee, gusset]            a work trouser's knee panels, a gusseted crotch
#   fades   [whiskers, knee, stacks, tracks, pocket, roping]   lighter cloth where denim wears
#   distress [knee_rip, abrasion, patched, sashiko, frayed]

PX_CM = 3.92   # canvas px per cm: a 105 cm outseam fills 412 px


def _cubic_y_free(x, bb, mouth_x, sm):
    """Height of the left scoop-pocket curve at x (the curve the jeans' watch pocket must clear)."""
    p0, p1, p2, p3 = (mouth_x, bb), (mouth_x - 4, bb + 26), (sm[0] + 20, sm[1] + 1), sm
    lo, hi = 0.0, 1.0
    for _ in range(40):
        t = (lo + hi) / 2
        xx = (1 - t) ** 3 * p0[0] + 3 * (1 - t) ** 2 * t * p1[0] + 3 * (1 - t) * t * t * p2[0] + t ** 3 * p3[0]
        lo, hi = (t, hi) if xx > x else (lo, t)
    t = (lo + hi) / 2
    return (1 - t) ** 3 * p0[1] + 3 * (1 - t) ** 2 * t * p1[1] + 3 * (1 - t) * t * t * p2[1] + t ** 3 * p3[1]


def _lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def pants(**kw) -> Shape:
    """Trousers, front view, as a fashion flat. Measured from a men's 32x32 straight jean laid flat
    (waist 41, hip 52, front rise 27, knee 21.5, opening 19.5, inseam 81, outseam 105 cm)."""
    p = {**PANTS_DEFAULTS, **kw}
    k = PX_CM
    jeans = bool(p["jeans"])
    waist = p.get("waist", "belt")
    pocket = p.get("pockets", "scoop" if jeans else "slant")
    hem_kind = p.get("hem", "stitched" if (jeans or not p.get("crease")) else "plain")
    pleats = int(p.get("pleats", 0))
    crease = bool(p.get("crease", pleats > 0))
    cargo = bool(p.get("cargo", False))
    coin = bool(p.get("coin", jeans))
    rivets = bool(p.get("rivets", coin))
    stitch = p.get("stitch", "tonal")
    leg, length = p["leg"], p["length"]
    wt = WEIGHT_LEVEL.get(p.get("weight"), 1)   # a heavy cloth: a deeper waistband, a doubled hem

    wy = 28.0
    hw = 20.5 * k                                   # half waist
    hh = {"wide": 26.5, "barrel": 26.5, "skinny": 22.5}.get(leg, 25.0) * k   # half hip (a 50 cm flat hip; 52-53 wide, 45 stretch)
    rise = {"low": 23.0, "high": 31.0}.get(p.get("rise"), 27.0)
    cy = wy + rise * k                              # crotch
    band = ({"gurkha": 7.0 * k}.get(waist) or (4.0 * k if waist in ("belt", "adjusters", "tab", "braces") else 4.6 * k)
            + max(0, wt - 1) * 2.5)
    bb = wy + band                                  # bottom of the waistband
    hip_y = cy - 18                                 # the widest point, ~4/5 of the way down the rise
    # one leg: its width at the knee and the opening, and where its middle sits at the hem
    kn, op = {"tapered": (19.5, 16.5), "straight": (21.5, 19.5), "wide": (25.5, 25.0), "skinny": (15.0, 11.0),
              "slim": (18.5, 16.0), "relaxed": (23.5, 21.5), "bootcut": (20.0, 22.5), "flare": (20.0, 27.0),
              "barrel": (27.0, 19.0)}.get(leg, (21.5, 19.5))
    kn, op = kn * k, op * k
    inseam = {"full": 81.0, "ankle": 71.0, "short": 22.0, "brief": 12.0}[length]
    short = length in ("short", "brief")
    if short and p.get("inseam"):                   # shorts told their inseam, in inches
        inseam = max(3, min(20, int(p["inseam"]))) * 2.54
    hy = wy + (27.0 + inseam) * k                   # the hem stays where it is whatever the rise
    knee_y = wy + (27.0 + 33.0) * k
    c0 = CX - hh / 2                                # middle of the leg at the crotch
    if short:
        op = 27.5 * k                               # a shorts leg opening is wider than its thigh: it flares
        hc = CX - 6 - op / 2
        Ho, Hi = (hc - op / 2, hy), (hc + op / 2, hy + 2)
        Ko = Ki = None
    else:
        hc = c0 - max(0.0, op - 19.5 * k) * 0.35    # wide legs move their middle out a little
        Ho, Hi = (hc - op / 2, hy), (hc + op / 2, hy)
        kc = c0 + (hc - c0) * (knee_y - cy) / (hy - cy)
        Ko, Ki = (kc - kn / 2, knee_y), (kc + kn / 2, knee_y)
    rib = hem_kind == "rib" and not short
    if rib:                                         # joggers: the leg gathers into a knitted cuff
        Ho, Hi = (hc - op / 2 + 3, hy), (hc + op / 2 - 3, hy)

    W0 = (CX - hw, wy)
    Hp = (CX - hh, hip_y)
    # outer seam: waist corner, a smooth hip curve, then nearly straight to the hem
    # outer seam: waist corner, out over the hip, then straight on down the leg with no bulge:
    # the hip curve leaves Hp in the direction the leg runs
    nxt = Ko if Ko else Ho
    dl = math.hypot(nxt[0] - Hp[0], nxt[1] - Hp[1])
    dvec = ((nxt[0] - Hp[0]) / dl, (nxt[1] - Hp[1]) / dl)
    hip_c1 = (CX - hw - 7, wy + 30)
    tang = dvec if Ko else (0.0, 1.0)               # shorts: the hip is a corner, the leg flares from it
    hip_c2 = (Hp[0] - tang[0] * 40, Hp[1] - tang[1] * 40)
    if Ko:
        dk = math.hypot(Ho[0] - Ko[0], Ho[1] - Ko[1])
        kvec = ((Ho[0] - Ko[0]) / dk, (Ho[1] - Ko[1]) / dk)
        kc1 = (Hp[0] + dvec[0] * 50, Hp[1] + dvec[1] * 50)
        kc2 = (Ko[0] - kvec[0] * 50, Ko[1] - kvec[1] * 50)
        out_leg = f"C {_pt(kc1)} {_pt(kc2)} {_pt(Ko)} L {_pt(Ho)}"
        in_leg = f"L {_pt(Ki)} L {_pt((CX, cy))}"
    else:
        out_leg = f"L {_pt(Ho)}"
        in_leg = f"L {_pt((CX, cy))}"
    m = _mirror

    left = f"M {_pt(W0)} C {_pt(hip_c1)} {_pt(hip_c2)} {_pt(Hp)} {out_leg} L {_pt(Hi)} {in_leg}"
    # the right half, walked back up: crotch -> inner hem -> outer hem -> hip -> waist
    if Ko:
        right = (f"L {_pt(m(Ki))} L {_pt(m(Hi))} L {_pt(m(Ho))} "
                 f"L {_pt(m(Ko))} C {_pt(m(kc2))} {_pt(m(kc1))} {_pt(m(Hp))} "
                 f"C {_pt(m(hip_c2))} {_pt(m(hip_c1))} {_pt(m(W0))}")
    else:
        right = (f"L {_pt(m(Hi))} L {_pt(m(Ho))} L {_pt(m(Hp))} "
                 f"C {_pt(m(hip_c2))} {_pt(m(hip_c1))} {_pt(m(W0))}")
    outline = f"{left} {right} Z"
    sh = Shape(outline=outline)
    xmin = min(Ho[0], Hp[0]) - 2
    sh.bbox = (xmin, wy - 3, 2 * CX - xmin, hy + 4)
    sh.body_box = (CX - hh, wy, CX + hh, hy)
    sh.anchors = {"waist": (CX, wy), "crotch": (CX, cy), "hem": (CX, hy)}

    def side_x(y):
        """x of the left outer seam at height y (above the hip)."""
        return _cubic_x_at_y(W0, hip_c1, hip_c2, Hp, y)

    # ---- waistband: straight across, its ends on the side seams
    xb = side_x(bb)
    sh.parts.append(Part(f"M {_pt(W0)} L {_pt(m(W0))} L {_pt(m((xb, bb)))} L {_pt((xb, bb))} Z", "band"))

    # ---- fly or drawstring
    fly_kind = p.get("fly", "zip" if waist not in ("elastic", "drawstring") else "none")
    fly = waist not in ("elastic", "drawstring") or fly_kind != "none"
    fly_end = cy - 7.0 * k
    if waist == "half_elastic":   # flat in front, gathered at the sides
        for s_ in (-1, 1):
            for i in range(4):
                x = CX + s_ * (hw - 6 - i * 6)
                sh.lines.append(f"M {_pt((x, wy + 4))} L {_pt((x + 1, bb - 4))}")
    if fly and fly_kind == "none":   # a flat-front pull-on: no fly, a centre seam only
        sh.lines.append(f"M {_pt((CX, bb))} L {_pt((CX, cy - 3))}")
        sh.dots.append((CX, wy + band / 2, 3.4))
    elif fly:
        sh.lines.append(f"M {_pt((CX, bb))} L {_pt((CX, cy - 3))}")
        fw = 3.6 * k   # the J-stitch on the wearer's left (viewer's right)
        sh.lines.append(f"M {_pt((CX + fw, bb))} L {_pt((CX + fw, fly_end - 14))} Q {_pt((CX + fw, fly_end))} {_pt((CX, fly_end + 2))}")
        sh.dots.append((CX, wy + band / 2, 3.4))
        if fly_kind == "button":   # a button fly: its buttons show down the placket
            for i in range(4):
                sh.dots.append((CX + fw / 2, bb + 12 + i * (fly_end - bb - 20) / 3, 2.2))
        if waist == "tab":   # an extended tab past the fly, buttoned
            tab = [(CX - 2, wy + 2), (CX - 6.5 * k, wy + 2), (CX - 7.5 * k, wy + band / 2), (CX - 6.5 * k, bb - 2), (CX - 2, bb - 2)]
            sh.parts.append(Part("M " + " L ".join(_pt(q) for q in tab) + " Z", "trim"))
            sh.dots.append((CX - 5.5 * k, wy + band / 2, 2.6))
        if waist == "adjusters":   # a buckled tab on each side of the waistband
            for mm in (lambda q: q, m):
                x0 = side_x(wy) + 4
                sh.parts.append(Part("M " + " L ".join(_pt(mm(q)) for q in ((x0 - 3, wy + 4), (x0 + 30, wy + 4), (x0 + 30, bb - 4),
                                                                             (x0 - 3, bb - 4))) + " Z", "trim"))
                sh.parts.append(Part(_frame(mm((x0 + 22, wy + band / 2)), 9, band - 2, 2), "inlay", color=METAL))
        if waist == "gurkha":   # a wide band, its straps wrapping forward to a buckle on each side
            for mm in (lambda q: q, m):
                x0 = side_x(wy) + 2
                strap = [(x0, wy + 5), (CX - 0.35 * hw, wy + 9), (CX - 0.35 * hw, bb - 9), (x0, bb - 5)]
                sh.parts.append(Part("M " + " L ".join(_pt(mm(q)) for q in strap) + " Z", "trim"))
                sh.parts.append(Part(_frame(mm((CX - 0.35 * hw - 6, wy + band / 2)), 11, band - 16, 2.4), "inlay", color=METAL))
            sh.lines.append(f"M {_pt((CX - hw + 6, wy + band / 2))} L {_pt((CX + hw - 6, wy + band / 2))}")
        if waist == "braces":   # brace buttons along the inside of the waistband, two each side of the front
            for x in (CX - 0.6 * hw, CX - 0.3 * hw, CX + 0.3 * hw, CX + 0.6 * hw):
                sh.dots.append((x, wy + 2.5, 2.6))
    if waist == "belt":
        # belt loops: two in front over the pocket mouths, one on each side seam
        for x in (CX - 0.45 * hw, CX - hw + 8):
            for mm in (lambda q: q, m):
                a, b = mm((x - 3.2, wy - 2.5)), mm((x + 3.2, bb + 3.5))
                x0, x1 = min(a[0], b[0]), max(a[0], b[0])
                sh.parts.append(Part(f"M {_pt((x0, a[1]))} L {_pt((x1, a[1]))} L {_pt((x1, b[1]))} L {_pt((x0, b[1]))} Z", "trim"))
    if not fly:
        sh.lines.append(f"M {_pt((CX, bb))} L {_pt((CX, cy - 3))}")
        # the gathers of the elastic
        n = 15
        for i in range(n):
            x = CX - hw + 9 + (2 * hw - 18) * i / (n - 1)
            if abs(x - CX) < 14 and waist == "drawstring":
                continue
            sh.lines.append(f"M {_pt((x, wy + 4))} L {_pt((x + 1, bb - 4))}")
        if waist == "drawstring":
            for s in (-1, 1):
                sh.dots.append((CX + s * 9, wy + band / 2, 2.3))
                tip = (CX + s * 15, bb + 46)
                sh.parts.append(Part(f"M {_pt((CX + s * 9, wy + band / 2))} C {_pt((CX + s * 10, bb + 10))} "
                                     f"{_pt((CX + s * 17, bb + 22))} {_pt(tip)}", "edge"))
                sh.parts.append(Part(f"M {_pt((tip[0] - 2, tip[1] - 1))} L {_pt((tip[0] - 2.4, tip[1] + 8))} "
                                     f"L {_pt((tip[0] + 2.4, tip[1] + 8))} L {_pt((tip[0] + 2, tip[1] - 1))} Z", "trim"))

    # ---- front pockets
    stitch_lines = []
    side_mouth_y = bb + (9.0 if pocket == "scoop" else 15.0) * k
    sm = (side_x(side_mouth_y) + 0.5, side_mouth_y)
    mouth_x = CX - (0.48 if pocket == "scoop" else 0.56) * hw
    for mm in (lambda q: q, m):
        if pocket == "scoop":
            d = f"M {_pt(mm((mouth_x, bb)))} C {_pt(mm((mouth_x - 4, bb + 26)))} {_pt(mm((sm[0] + 20, sm[1] + 1)))} {_pt(mm(sm))}"
            sh.lines.append(d)
            stitch_lines.append(f"M {_pt(mm((mouth_x - 4, bb)))} C {_pt(mm((mouth_x - 8, bb + 22)))} {_pt(mm((sm[0] + 18, sm[1] - 3)))} {_pt(mm((sm[0], sm[1] - 4)))}")
            if rivets:
                sh.dots.append((*mm((mouth_x - 1, bb + 3)), 1.9))
                sh.dots.append((*mm((sm[0] + 4, sm[1] - 2)), 1.9))
        elif pocket == "slant":
            sh.lines.append(f"M {_pt(mm((mouth_x, bb)))} L {_pt(mm(sm))}")
            if rivets:   # a work trouser's rivets at the corners of its pocket mouth
                sh.dots.append((*mm((mouth_x - 2, bb + 3)), 1.9))
                sh.dots.append((*mm((sm[0] + 4, sm[1] - 3)), 1.9))
        elif pocket == "side":
            sh.lines.append(f"M {_pt(mm((sm[0] + 4, bb + 4)))} L {_pt(mm((sm[0] + 2, sm[1] + 20)))}")
        elif pocket == "frog":   # a horizontal opening just under the waistband
            sh.lines.append(f"M {_pt(mm((mouth_x - 4, bb + 14)))} L {_pt(mm((side_x(bb + 14) + 10, bb + 14)))}")
    if pocket == "scoop" and coin:
        # the watch pocket sits on the wearer's right (viewer's left), inside the scoop
        cx0, cx1 = side_x(bb) + 7, mouth_x - 9
        depth = min(6.5 * k, _cubic_y_free(cx1, bb, mouth_x, sm) - bb - 5)
        sh.lines.append(f"M {_pt((cx0, bb))} L {_pt((cx0 + 1.5, bb + depth))} L {_pt((cx1 - 1.5, bb + depth))} L {_pt((cx1, bb))}")
        stitch_lines.append(f"M {_pt((cx0, bb + 4))} L {_pt((cx1, bb + 4))}")

    # ---- pleats and crease
    for mm in (lambda q: q, m):
        if pleats:
            for i in range(pleats):
                x = CX - 0.30 * hw - i * 12
                sh.lines.append(f"M {_pt(mm((x, bb)))} L {_pt(mm((x - 1.5, bb + (34 if i == 0 else 24))))}")
                if p.get("pleat_dir"):   # the fold's lip, on the side it opens to
                    s_ = -1 if p["pleat_dir"] == "reverse" else 1
                    sh.lines.append(f"M {_pt(mm((x, bb)))} L {_pt(mm((x + s_ * 5, bb + 3)))}")
        if crease and Ko:
            top = (c0 + 2, bb + (34 if pleats else 60))
            sh.lines.append(f"M {_pt(mm(top))} L {_pt(mm(((Ko[0] + Ki[0]) / 2, knee_y)))} L {_pt(mm((hc, hy - 4)))}")

    # ---- cargo pockets: on the side of the thigh, so only the front half shows
    if cargo:
        top_y = cy + 6
        ph, pw = 21.0 * k, 11.0 * k
        for mm in (lambda q: q, m):
            xo = Hp[0] - 6
            xi = Hp[0] + pw
            sh.lines.append(f"M {_pt(mm((xo, top_y + 16)))} L {_pt(mm((xi, top_y + 16)))} L {_pt(mm((xi + 1, top_y + ph - 6)))} "
                            f"Q {_pt(mm((xi + 1, top_y + ph)))} {_pt(mm((xi - 5, top_y + ph)))} L {_pt(mm((xo, top_y + ph)))}")
            sh.parts.append(Part(f"M {_pt(mm((xo, top_y)))} L {_pt(mm((xi + 2, top_y)))} L {_pt(mm((xi + 2, top_y + 18)))} "
                                 f"Q {_pt(mm((xi + 2, top_y + 21)))} {_pt(mm((xi - 2, top_y + 21)))} L {_pt(mm((xo, top_y + 21)))} Z", "trim", clip=True))
            sh.dots.append((*mm((xi - 7, top_y + 14)), 2.2))

    # ---- the owner's details: more pockets, work panels, fades and wear
    def leg_x(y, inner=False):
        """x of the left leg's outer (or inner) edge at height y, below the crotch."""
        if not Ko:
            pts = [(Hp[0], Hp[1]), Ho] if not inner else [(CX, cy), Hi]
        else:
            pts = [(Hp[0], Hp[1]), Ko, Ho] if not inner else [(CX, cy), Ki, Hi]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if y0 <= y <= y1:
                return x0 + (x1 - x0) * (y - y0) / ((y1 - y0) or 1)
        return pts[-1][0]

    def quad(pts, role, color=None, both=True, clip=True):
        for mm in ((lambda q: q, m) if both else (lambda q: q,)):
            sh.parts.append(Part("M " + " L ".join(_pt(mm(q)) for q in pts) + " Z", role, color=color, clip=clip))
    extra = set(p.get("extra_pockets") or ())
    if "zip" in extra:   # a zipped pocket on each thigh
        y0 = cy + 8
        for mm in (lambda q: q, m):
            a_, b_ = mm((leg_x(y0) + 12, y0)), mm((leg_x(y0 + 40) + 20, y0 + 40))
            sh.parts.append(Part(_capsule(a_, b_, 3.6), "inlay", color="#2a2a2a"))
    if "rule" in extra and Ko:   # a carpenter's rule pocket on the wearer's right thigh (the viewer's left)
        y0 = cy + 6
        x0 = leg_x(y0) + 6
        sh.parts.append(Part(f"M {_pt((x0, y0))} L {_pt((x0 + 22, y0))} L {_pt((x0 + 24, y0 + 30 * k))} L {_pt((x0 + 2, y0 + 30 * k))} Z",
                             "trim", clip=True))
    if "hammer" in extra:   # a hammer loop on the wearer's left (the viewer's right) side
        y0 = cy + 20
        xr = 2 * CX - leg_x(y0)
        sh.parts.append(Part(f"M {_pt((xr - 16, y0))} L {_pt((xr - 4, y0))} L {_pt((xr - 4, y0 + 34))} L {_pt((xr - 16, y0 + 34))} Z",
                             "trim", clip=True))
    panels = set(p.get("panels") or ())
    if "double_knee" in panels and Ko:   # a second layer of cloth over each knee
        y0, y1 = knee_y - 26 * k * 0.5 - 30, knee_y + 34
        quad([(leg_x(y0) - 4, y0), (leg_x(y0, True) + 4, y0), (leg_x(y1, True) + 4, y1), (leg_x(y1) - 4, y1)], "trim")
    if "gusset" in panels:   # a diamond of cloth set into the crotch
        sh.parts.append(Part(f"M {_pt((CX, cy - 22))} L {_pt((CX + 9, cy - 4))} L {_pt((CX, cy + 4))} L {_pt((CX - 9, cy - 4))} Z",
                             "trim", clip=True))
    def soft(c, rx, ry):   # a worn patch: paler toward its middle, with no edge
        (x, y), a_, b_ = c, rx * 1.3, ry * 1.3
        sh.parts.append(Part(f"M {_f(x - a_)},{_f(y)} A {_f(a_)} {_f(b_)} 0 1 0 {_f(x + a_)},{_f(y)} "
                             f"A {_f(a_)} {_f(b_)} 0 1 0 {_f(x - a_)},{_f(y)} Z", "fade", color="soft", clip=True))
    def softline(a_, b_, w):   # a pale line with soft sides
        for f_ in (2.0, 0.8):
            sh.parts.append(Part(_capsule(a_, b_, w * f_), "fade", color="soft", clip=True))
    fades = set(p.get("fades") or ())
    if fades:
        for mm in (lambda q: q, m):
            if "whiskers" in fades:   # pale creases fanning from the crotch over the top of the thigh
                for i in range(5):
                    y = cy - 10 + i * 9
                    a_, b_ = mm((CX - 12, y + 2)), mm((CX - 0.42 * hh + i * 4, y - 10))
                    softline(a_, b_, 3.0 - i * 0.35)
            if "knee" in fades and Ko:
                kx = (leg_x(knee_y) + leg_x(knee_y, True)) / 2
                soft(mm((kx, knee_y - 10)), kn * 0.36, kn * 0.6)
            if "pocket" in fades:   # the front pocket's edge, worn pale
                softline(mm((mouth_x, bb + 2)), mm((sm[0] + 6, sm[1] - 2)), 6)
            if "tracks" in fades and Ko:   # pale lines along the outer seams
                softline(mm((leg_x(cy + 20) + 3, cy + 20)), mm((Ho[0] + 4, hy - 12)), 4.0)
            if "roping" in fades and Ko:   # the chain-stitched hem twisted pale: slanting streaks along it
                for j in range(6):
                    x = Ho[0] + 4 + (Hi[0] - Ho[0] - 12) * j / 5
                    softline(mm((x, hy - 3)), mm((x + 5, hy - 12)), 2.2)
            if "stacks" in fades and Ko:   # pale bands where the hem bunches
                for i in range(3):
                    y = hy - 14 - i * 16
                    softline(mm((leg_x(y) + 3, y)), mm((leg_x(y, True) - 3, y - 4)), 2.8)
    distress = set(p.get("distress") or ())
    for n_leg, mm in enumerate((lambda q: q, m)):
        if Ko and distress & {"knee_rip", "abrasion"}:
            kx = (leg_x(knee_y) + leg_x(knee_y, True)) / 2
            if "abrasion" in distress and n_leg == 1:   # on one thigh
                soft(mm((kx, cy + 50)), kn * 0.3, kn * 0.45)
            if "knee_rip" in distress:   # a torn hole, its white weft threads left across it
                w_ = kn * 0.32
                sh.parts.append(Part(f"M {_pt(mm((kx - w_, knee_y - 14)))} Q {_pt(mm((kx, knee_y - 22)))} {_pt(mm((kx + w_, knee_y - 14)))} "
                                     f"L {_pt(mm((kx + w_, knee_y + 2)))} Q {_pt(mm((kx, knee_y + 8)))} {_pt(mm((kx - w_, knee_y + 2)))} Z",
                                     "inlay", color="deep"))
                for j in range(4):
                    y = knee_y - 13 + j * 5
                    sh.parts.append(Part(f"M {_pt(mm((kx - w_ + 1, y)))} Q {_pt(mm((kx, y + 1.5)))} {_pt(mm((kx + w_ - 1, y)))}",
                                         "stitch", color="#f2efe6"))
        if Ko and distress & {"patched", "sashiko"} and n_leg == 0:   # on one thigh   # a patch on the thigh; sashiko: rows of white running stitch
            x0 = leg_x(cy + 30) + 16
            pts = [(x0, cy + 30), (x0 + 30, cy + 28), (x0 + 31, cy + 62), (x0 + 1, cy + 63)]
            sh.parts.append(Part("M " + " L ".join(_pt(mm(q)) for q in pts) + " Z", "trim", clip=True))
            rows = range(5) if "sashiko" in distress else ()
            for j in rows:
                sh.parts.append(Part(f"M {_pt(mm((x0 + 3, cy + 34 + j * 6.5)))} L {_pt(mm((x0 + 28, cy + 33 + j * 6.5)))}", "stitch",
                                     color="#f2efe6"))
            if "patched" in distress:
                sh.parts.append(Part("M " + " L ".join(_pt(mm(q)) for q in _shift(pts, 0, 0)) + " Z", "stitch"))

    # ---- the break: folds where the hem meets the shoe
    brk = p.get("break", "none")
    if Ko and brk in ("slight", "full", "stacked"):
        n_ = {"slight": 1, "full": 2, "stacked": 3}[brk]
        for mm in (lambda q: q, m):
            for i in range(n_):
                y = hy - (7 if brk == "slight" else 13) - i * 15
                xo, xi = leg_x(y) + 2, leg_x(y, True) - 2
                dip = 3 if brk == "slight" else 7
                sh.lines.append(f"M {_pt(mm((xo, y + (dip if i % 2 else 0))))} Q {_pt(mm(((xo + xi) / 2, y + dip * (0 if i % 2 else 1))))} "
                                f"{_pt(mm((xi, y + (0 if i % 2 else dip * 0.4))))}")

    # ---- hems
    for mm in (lambda q: q, m):
        a, b = Ho, Hi
        if hem_kind == "stitched":
            sh.lines.append(f"M {_pt(mm((a[0] - 1, a[1] - 2.2 * k)))} L {_pt(mm((b[0] + 1, b[1] - 2.2 * k)))}")
            stitch_lines.append(f"M {_pt(mm((a[0], a[1] - 2.2 * k - 4)))} L {_pt(mm((b[0], b[1] - 2.2 * k - 4)))}")
            if wt >= 2:
                sh.lines.append(f"M {_pt(mm((a[0] - 1, a[1] - 2.2 * k - 5)))} L {_pt(mm((b[0] + 1, b[1] - 2.2 * k - 5)))}")
        elif hem_kind == "turnup":
            t = 4.0 * k
            cuff = [(a[0] - 2.5, a[1] - t), (b[0] + 2.5, b[1] - t), (b[0] + 1.5, b[1] + 1), (a[0] - 1.5, a[1] + 1)]
            sh.parts.append(Part("M " + " L ".join(_pt(mm(v)) for v in cuff) + " Z", "cuff"))
        elif hem_kind == "rib":
            t = 5.5 * k if not short else 3 * k
            cuff = [(a[0] - 0.5, a[1] - t), (b[0] + 0.5, b[1] - t), (b[0], b[1]), (a[0], a[1])]
            sh.parts.append(Part("M " + " L ".join(_pt(mm(v)) for v in cuff) + " Z", "band"))
        elif hem_kind == "rolled":   # rolled up twice: two narrow turns showing the cloth's inside
            for j, t in enumerate((3.2 * k, 6.4 * k)):
                cuff = [(a[0] - 2.5, a[1] - t), (b[0] + 2.5, b[1] - t), (b[0] + 2, b[1] - t + 3.2 * k), (a[0] - 2, a[1] - t + 3.2 * k)]
                sh.parts.append(Part("M " + " L ".join(_pt(mm(v)) for v in cuff) + " Z", "cuff" if j else "band"))
        elif hem_kind == "raw":     # a cut edge, frayed: short threads hanging below it
            for j in range(7):
                x = a[0] + 3 + (b[0] - a[0] - 6) * j / 6
                sh.parts.append(Part(f"M {_pt(mm((x, a[1] - 2)))} L {_pt(mm((x + 0.6, a[1] + 3.5)))}", "edge"))
        elif hem_kind == "split":   # a side slit at the outer seam, the hem turned up either side of it
            sh.lines.append(f"M {_pt(mm((a[0] + 2, a[1] - 0.5)))} Q {_pt(mm((a[0] + 9, a[1] - 9)))} {_pt(mm((a[0] + 5, a[1] - 18)))}")
            sh.lines.append(f"M {_pt(mm((a[0] + 9, a[1] - 2.2 * k)))} L {_pt(mm((b[0] + 1, b[1] - 2.2 * k)))}")
        elif hem_kind == "notched":   # a small V cut up into the hem at the outer seam
            sh.lines.append(f"M {_pt(mm((a[0] + 1.5, a[1] - 0.5)))} L {_pt(mm((a[0] + 7.5, a[1] - 12)))} "
                            f"L {_pt(mm((a[0] + 13.5, a[1] - 0.5)))}")
            sh.lines.append(f"M {_pt(mm((a[0] + 12.4, a[1] - 2.2 * k)))} L {_pt(mm((b[0] + 1, b[1] - 2.2 * k)))}")
        elif hem_kind == "chain":   # chain stitch: the hem's roping, a row of slanting twists
            sh.lines.append(f"M {_pt(mm((a[0] - 1, a[1] - 2.2 * k)))} L {_pt(mm((b[0] + 1, b[1] - 2.2 * k)))}")
            for j in range(7):
                x = a[0] + 2 + (b[0] - a[0] - 8) * j / 6
                sh.parts.append(Part(f"M {_pt(mm((x, a[1] - 2.2 * k - 3)))} L {_pt(mm((x + 5, a[1] - 2.2 * k - 10)))}", "stitch"))

    # ---- a stripe down each outer seam
    if p.get("stripe") == "side":
        run = [(side_x(y), y) for y in (bb + 2, (bb + hip_y) / 2, hip_y - 1)] + [Hp] + ([Ko] if Ko else []) + [Ho]
        a_, b_ = _offset_line(run, 3.0), _offset_line(run, 10.0)
        for mm in (lambda q: q, m):
            sh.parts.append(Part(_poly([mm(v) for v in a_ + b_[::-1]]), "inlay", color="trim", clip=True))
    if stitch == "contrast":
        for d in stitch_lines:
            sh.parts.append(Part(d, "stitch"))
    return sh


# -------------------------------------------------------------------- shoes

SNEAKER_DEFAULTS = dict(height="low", sole="regular")
# Optional details, each read off a photo:
#   style    low_sneaker | high_top | runner | slip_on | loafer | derby | oxford | boot | chelsea_boot
#            (default from `height`: low -> low_sneaker, high -> high_top)
#   toe_cap  none | stitched | rubber      a seam across the toe, or a rubber bumper in the sole colour
#   stripe   none | side                  a contrast panel on the side (trim colour)
#   heel_tab none | contrast              the heel tab / pull loop in the trim colour
#   foxing   True | False                 the stripe round a vulcanised sole (default for high_top, slip_on)
#   laces    True | False                 default by style
#   eyelets  2..10                        how many eyelets a laced shoe has (default by style: 5 on a dress shoe)
#   strap    penny | tassel | horsebit | none   what lies across a loafer's vamp (default penny; none: a venetian)
#   brogue   none | quarter | semi | full  punching on a derby or oxford: along the toe cap (quarter), and a
#                                         medallion and the seams too (semi), or a wingtip's wing instead of a cap (full)
#   wholecut True | False                 an oxford cut from one piece: no vamp seam
#   sandal   slide | two_strap | strap     (style sandal) one wide strap; two buckled straps (default); or a
#                                         forefoot strap with an instep strap up to an ankle strap and a heel strap
#   kind     a footwear id                 what only that kind has (a western boot's stitching, a court shoe's
#                                         perforations, a retro runner's overlays)
#   shaft    0.35..0.95                    a boot's or high top's collar height, in shoe lengths (a service boot: 0.6)
#   toe      round | almond | chisel | pointed   a lower, longer toe for the last three
#   moc      True | False                  a moc toe's raised seam over the toe
#   tread    none | lug | crepe | wedge | cleats | jute | pebble | siped   what the sole is made of, as it shows
#   heel     flat | stacked | block | cuban   a heeled shoe's heel (default: a low stacked one, no lifts drawn)
#   hooks    0..6                          the top eyelets of a boot are speed hooks
#   gusset   True | False                  an elastic side panel (a chelsea always has one)
#   strap    + engineer | jodhpur | monk | double_monk | velcro   straps and buckles on boots and shoes
#   lower    none | rubber | all           a duck boot's rubber lower; a rain boot is rubber all over
#   collar_pad True | False                a padded collar (basketball, skate, hiking; a snow boot's fleece cuff)
#   tongue   regular | padded             a skate shoe's padded tongue standing above the collar
#   lace_collar True | False               a rawhide lace round the collar, tied at the side (a boat shoe)
#   backless True | False                  a clog: no back above the heel
#   pull_tabs True | False                 a western boot's pull tab at the top of the shaft
#   rings    True | False                  D-rings instead of eyelets (a work or hiking boot)
#   toggle   True | False                  a speed lace: a cord lock above the top eyelet, the cord ends hanging
#   shine    True | False                  patent leather: bright gloss streaks along the toe and the heel
#   sandal   + thong                       (style sandal) a flip-flop: a Y strap from a post between the toes

SHOE_X0, SHOE_L, SHOE_G = 40.0, 320.0, 330.0   # toe tip x, length toe to heel, ground y
METAL = "#c9a85c"   # a buckle or a horsebit


def _sp(u, v):
    """Shoe coordinates: u runs from the toe (0) to the heel (1), v is height above the ground; both in shoe lengths."""
    return (SHOE_X0 + u * SHOE_L, SHOE_G - v * SHOE_L)


def _spline(pts, start=True) -> str:
    """A smooth curve through the points (Catmull-Rom as cubic beziers), ends clamped."""
    P = [_sp(*q) for q in pts]
    out = [f"M {_pt(P[0])}"] if start else []
    n = len(P)
    for i in range(n - 1):
        p0, p1, p2, p3 = P[max(i - 1, 0)], P[i], P[i + 1], P[min(i + 2, n - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        out.append(f"C {_pt(c1)} {_pt(c2)} {_pt(p2)}")
    return " ".join(out)


def _chain(groups) -> str:
    """Several smooth runs joined at corners; each run starts where the last ended."""
    return " ".join(_spline(g, start=(i == 0)) for i, g in enumerate(groups))


def _poly_v(pts, u):
    """Height of a polyline (u ascending or descending) at u."""
    q = sorted(pts)
    for (u0, v0), (u1, v1) in zip(q, q[1:]):
        if u0 <= u <= u1:
            return v0 + (v1 - v0) * (u - u0) / (u1 - u0 or 1)
    return q[0][1] if u < q[0][0] else q[-1][1]


def _capsule(a, b, w) -> str:
    """A rounded bar from a to b (canvas points), w wide: a lace seen from the side."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    ln = math.hypot(dx, dy) or 1
    nx, ny = -dy / ln * w / 2, dx / ln * w / 2
    r = w / 2
    return (f"M {_pt((a[0] + nx, a[1] + ny))} L {_pt((b[0] + nx, b[1] + ny))} "
            f"A {_f(r)} {_f(r)} 0 0 0 {_pt((b[0] - nx, b[1] - ny))} L {_pt((a[0] - nx, a[1] - ny))} "
            f"A {_f(r)} {_f(r)} 0 0 0 {_pt((a[0] + nx, a[1] + ny))} Z")


def _ring(c, r_out, r_in) -> str:
    """A ring (canvas point, radii): the inner circle runs the other way, so it is a hole in any fill."""
    (x, y), a, b = c, r_out, r_in
    return (f"M {_f(x - a)},{_f(y)} A {_f(a)} {_f(a)} 0 1 0 {_f(x + a)},{_f(y)} A {_f(a)} {_f(a)} 0 1 0 {_f(x - a)},{_f(y)} Z "
            f"M {_f(x - b)},{_f(y)} A {_f(b)} {_f(b)} 0 1 1 {_f(x + b)},{_f(y)} A {_f(b)} {_f(b)} 0 1 1 {_f(x - b)},{_f(y)} Z")


def _frame(c, w, h, t) -> str:
    """A buckle seen from the side: a rectangular frame (canvas centre, width, height, bar thickness)."""
    (x, y) = c
    o = [(x - w / 2, y - h / 2), (x + w / 2, y - h / 2), (x + w / 2, y + h / 2), (x - w / 2, y + h / 2)]
    i = [(x - w / 2 + t, y - h / 2 + t), (x - w / 2 + t, y + h / 2 - t), (x + w / 2 - t, y + h / 2 - t), (x + w / 2 - t, y - h / 2 + t)]
    return "M " + " L ".join(_pt(q) for q in o) + " Z M " + " L ".join(_pt(q) for q in i) + " Z"


def _shift(pts, du=0.0, dv=0.0):
    return [(u + du, v + dv) for u, v in pts]


def _sandal(p, f) -> Shape:
    """A sandal, outer side, toe to the left: straps over a thick footbed of cork or rubber on a thin outsole.
    Nothing is drawn of a foot, so the card shows between the straps. The straps follow the top of a foot standing
    on the footbed (a man's foot is about 2.5 cm high at the toes and 6 cm at the instep)."""
    kind = p.get("sandal", "two_strap")
    if kind not in ("slide", "two_strap", "strap", "thong"):
        kind = "two_strap"
    th_toe, th_heel, spring = 0.065 * f, 0.095 * f, 0.012
    top = [(0.012, spring + th_toe * 0.8), (0.06, spring * 0.4 + th_toe), (0.3, th_toe + 0.002),
           (0.6, th_toe + (th_heel - th_toe) * 0.6), (0.85, th_heel), (0.99, th_heel)]
    tf = lambda u: _poly_v(top, u)
    foot = [(0.0, 0.03), (0.1, 0.06), (0.2, 0.08), (0.3, 0.095), (0.4, 0.12), (0.5, 0.15), (0.6, 0.185),
            (0.7, 0.225), (0.8, 0.25)]
    over = lambda u: tf(u) + _poly_v(foot, u) + 0.014   # the top of a strap lying over the foot

    sole_d = (_spline(top) + f" Q {_pt(_sp(1.004, th_heel))} {_pt(_sp(1.002, th_heel * 0.6))} "
              f"L {_pt(_sp(0.997, 0.006))} Q {_pt(_sp(0.995, 0))} {_pt(_sp(0.97, 0))} L {_pt(_sp(0.2, 0))} "
              f"C {_pt(_sp(0.08, 0))} {_pt(_sp(0.02, spring * 0.3))} {_pt(_sp(-0.002, spring + th_toe * 0.35))} "
              f"Q {_pt(_sp(-0.006, spring + th_toe * 0.7))} {_pt(_sp(*top[0]))} Z")
    straps, buckles, rims = [], [], []

    def band(u0, u1, lean=0.0):
        """A strap crossing the foot: up from the footbed at u0, narrowing as it rises, arching over the top of the
        foot and down to the footbed at u1; `lean` tips it towards the heel."""
        w = (u1 - u0) * 0.16
        a, b = (u0 + w + lean, over(u0 + w + lean)), (u1 - w + lean, over(u1 - w + lean))
        h0, h1 = (a[1] + tf(u0)) / 2, (b[1] + tf(u1)) / 2
        crown = [(a[0] + (b[0] - a[0]) * k, over(a[0] + (b[0] - a[0]) * k) + 0.014 * math.sin(math.pi * k)) for k in (0.33, 0.67)]
        rims.append(_spline([(a[0] + 0.01, a[1] - 0.016), *[(u, v - 0.016) for u, v in crown], (b[0] - 0.01, b[1] - 0.016)]))
        return _chain([[(u0, tf(u0)), (u0 + w * 0.4 + lean * 0.5, h0), a], [a, *crown, b],
                       [b, (u1 - w * 0.4 + lean * 0.5, h1), (u1, tf(u1))]]) + " Z"

    top_v = over(0.5)
    if kind == "slide":
        straps.append(band(0.17, 0.54, -0.01))
    elif kind == "thong":   # a flip-flop: a thin strap from the post between the toes, back over the foot to the sole
        w = 0.022 * SHOE_L
        post, crest = (0.1, tf(0.1) + 0.012), (0.3, over(0.3) - 0.01)
        straps += [_capsule(_sp(*post), _sp(*crest), w), _capsule(_sp(*crest), _sp(0.47, tf(0.47) + 0.004), w)]
        straps.append(_capsule(_sp(0.1, tf(0.1) - 0.004), _sp(*post), w * 1.3))
        top_v = over(0.3) + 0.004
    elif kind == "two_strap":
        straps += [band(0.2, 0.37), band(0.43, 0.6, 0.005)]
        buckles += [(0.315, over(0.315) - 0.042), (0.55, over(0.55) - 0.05)]
        top_v = over(0.56) + 0.01
    else:   # a forefoot strap; a strap from the midfoot up to the ankle, an ankle strap round it, a heel strap
        lo = lambda u: tf(u) + 0.17 - 0.19 * (u - 0.63) - 0.12 * (u - 0.63) * (1 - u)   # the ankle strap's lower edge
        hi = lambda u: lo(u) + 0.04
        straps.append(band(0.17, 0.31))
        straps.append(_chain([[(0.5, tf(0.5)), (0.56, tf(0.5) + 0.09), (0.615, hi(0.63) - 0.002)],
                              [(0.615, hi(0.63) - 0.002), (0.69, hi(0.69) - 0.002)],
                              [(0.69, hi(0.69) - 0.002), (0.63, tf(0.6) + 0.09), (0.585, tf(0.585))]]) + " Z")
        straps.append(_chain([[(0.925, tf(0.925)), (0.93, (tf(0.93) + lo(0.94)) / 2), (0.945, lo(0.945) + 0.01)],
                              [(0.945, lo(0.945) + 0.01), (0.99, lo(0.99) + 0.01)],
                              [(0.99, lo(0.99) + 0.01), (1.0, (tf(1.0) + lo(1.0)) / 2), (0.996, tf(0.996))]]) + " Z")
        straps.append(_chain([[(0.63, lo(0.63)), (0.625, hi(0.63))],
                              [(0.625, hi(0.63)), (0.78, hi(0.78) + 0.004), (0.92, hi(0.92) - 0.002), (0.995, hi(0.995) - 0.012)],
                              [(0.995, hi(0.995) - 0.012), (0.998, lo(0.998) - 0.004)],
                              [(0.998, lo(0.998) - 0.004), (0.92, lo(0.92)), (0.78, lo(0.78) + 0.002), (0.63, lo(0.63))]]) + " Z")
        buckles.append((0.66, (lo(0.66) + hi(0.66)) / 2))
        top_v = hi(0.63) + 0.002

    sh = Shape(outline=" ".join([sole_d, *straps]))
    sh.parts.append(Part(sole_d, "sole"))
    # the outsole under the footbed, and the footbed's lining along its top
    out_top = [(-0.05, spring + 0.03 * f), (0.06, spring * 0.4 + 0.026 * f), (0.2, 0.025 * f), (1.05, 0.025 * f)]
    sh.parts.append(Part(_spline(out_top) + f" L {_pt(_sp(1.05, -0.02))} L {_pt(_sp(-0.05, -0.02))} Z", "inlay",
                         color="sole_dark", clip=True))
    sh.parts.append(Part(_spline(_shift(top[1:-1], 0, -0.01)), "edge", color="sole_line"))
    for d in rims:
        sh.parts.append(Part(d, "edge"))
    for c in buckles:
        x, y = _sp(*c)
        sh.parts.append(Part(_frame((x, y), 0.048 * SHOE_L, 0.07 * SHOE_L, 3.6), "inlay", color=METAL))
        sh.parts.append(Part(f"M {_f(x - 0.012 * SHOE_L)},{_f(y)} L {_f(x + 0.02 * SHOE_L)},{_f(y)}", "edge"))   # the prong
    sh.bbox = (SHOE_X0 - 4, SHOE_G - top_v * SHOE_L - 14, SHOE_X0 + SHOE_L + 4, SHOE_G + 1)
    sh.body_box = (SHOE_X0, SHOE_G - top_v * SHOE_L, SHOE_X0 + SHOE_L, SHOE_G)
    sh.anchors = {"ground": (CX, SHOE_G), "toe": (SHOE_X0, SHOE_G), "heel": (SHOE_X0 + SHOE_L, SHOE_G)}
    sh.sole_default = "#c9a77c"   # cork
    return sh


def sneaker(**kw) -> Shape:
    """A shoe, outer side, toe to the left. Proportions in shoe lengths, from side views of real shoes:
    a low sneaker is ~2.8x as long as it is tall at the collar, a high-top's collar is ~0.53 of its length up."""
    p = {**SNEAKER_DEFAULTS, **kw}
    style = p.get("style") or ("high_top" if p["height"] == "high" else "low_sneaker")
    if style not in SHOE_STYLES:
        style = "low_sneaker"
    f = {"thin": 0.75, "regular": 1.0, "chunky": 1.6}.get(p["sole"], 1.0)
    if style == "sandal":
        return _sandal(p, f)
    kind = p.get("kind")
    tread = p.get("tread", "none")
    heel_kind = p.get("heel", "stacked")
    lower = p.get("lower", "none")
    if tread in ("lug", "crepe") and p["sole"] == "regular":
        f = 1.25 if tread == "lug" else 0.9                    # a lug sole is thicker than a city one
    heeled = style in ("loafer", "derby", "oxford", "boot", "chelsea_boot") and tread not in ("wedge", "crepe") and heel_kind != "flat"
    laced = p.get("laces", style not in ("slip_on", "loafer", "chelsea_boot"))
    foxing = p.get("foxing", style in ("high_top", "slip_on"))
    toe_cap = p.get("toe_cap", "rubber" if style == "high_top" else "none")
    brogue = p.get("brogue", "none") if style in ("derby", "oxford") else "none"
    if brogue == "full":                                       # a wingtip's wing takes the place of a cap
        toe_cap = "none"
    elif brogue in ("quarter", "semi"):                        # the punching runs along a toe cap
        toe_cap = "stitched"

    # ---- the sole: where the upper sits on it (sole top, toe -> heel) and its underside
    def sole(f):
        if heeled:
            ts = {"boot": 0.05, "chelsea_boot": 0.035}.get(style, 0.03) * (1 if f <= 1 else 1.4)
            hb = {"boot": 0.06, "chelsea_boot": 0.065}.get(style, 0.07) * (0.8 if f < 1 else 1.0)
            hb = {"cuban": 0.105, "block": 0.075}.get(heel_kind, hb)
            spring = 0.025
            breast = 0.77                                          # front face of the heel
            foot_b = breast + (0.03 if heel_kind == "cuban" else 0)  # where it meets the ground: a cuban heel slopes in
            back_b = 0.955 if heel_kind == "cuban" else 0.985
            top = [(0.012, spring + ts * 0.9), (0.08, spring * 0.45 + ts), (0.25, ts + 0.002), (0.48, ts + 0.006),
                   (0.62, ts + hb * 0.55), (0.76, ts + hb * 0.95), (0.993, ts + hb)]
            under = (f"Q {_pt(_sp(-0.006, spring + ts * 0.5))} {_pt(_sp(0.008, spring))} "
                     f"C {_pt(_sp(0.04, spring * 0.4))} {_pt(_sp(0.12, 0))} {_pt(_sp(0.25, 0))} L {_pt(_sp(0.5, 0))} "
                     f"C {_pt(_sp(0.58, 0.004))} {_pt(_sp(0.66, hb * 0.75))} {_pt(_sp(breast - 0.01, hb))} "
                     f"L {_pt(_sp(foot_b, 0))} L {_pt(_sp(back_b, 0))} Q {_pt(_sp(back_b + 0.012, 0))} {_pt(_sp(back_b + 0.012, 0.004))} "
                     f"L {_pt(_sp(1.0, ts + hb - 0.008))} L {_pt(_sp(*top[-1]))}")
            heel_line = f"M {_pt(_sp(breast - 0.012, hb))} L {_pt(_sp(1.0, hb))}"
        else:
            th = {"runner": 0.15, "high_top": 0.105, "slip_on": 0.09}.get(style, 0.12) * f
            tf = {"runner": 0.085, "high_top": 0.085, "slip_on": 0.075}.get(style, 0.09) * (1 + (f - 1) * 0.8)
            spring = 0.06 if style == "runner" else 0.03
            rock = 0.36 if style == "runner" else 0.26                  # where the toe starts to lift
            bev = 0.02 if style == "runner" else 0.006                  # heel bevel
            top = [(0.012, spring + tf * 0.85), (0.07, spring * 0.55 + tf), (0.25, tf + 0.003),
                   (0.5, tf + (th - tf) * 0.35), (0.75, th - 0.004), (0.993, th)]
            if style == "runner":   # a sculpted midsole: rises at the heel, dips under the arch
                top = [(0.012, spring + tf * 0.85), (0.07, spring * 0.5 + tf), (0.25, tf), (0.45, tf + 0.006),
                       (0.62, th * 0.8), (0.8, th * 0.95), (0.993, th)]
            under = (f"Q {_pt(_sp(-0.008, spring + tf * 0.45))} {_pt(_sp(0.01, spring))} "
                     f"C {_pt(_sp(0.06, spring * 0.3))} {_pt(_sp(rock * 0.45, 0))} {_pt(_sp(rock, 0))} L {_pt(_sp(0.95, 0))} "
                     f"C {_pt(_sp(1.0, bev))} {_pt(_sp(1.008, bev + 0.03))} {_pt(_sp(1.003, th - 0.01))} L {_pt(_sp(*top[-1]))}")
            heel_line, hb = "", 0.0
        return top, under, heel_line, hb

    top, under, heel_line, hb = sole(f)
    top_reg = sole(1.0)[0]
    sole_top_heel = top[-1]

    # ---- the upper: heel back -> collar -> (tongue) -> lacing / vamp -> toe, ending on the sole
    st = top[-1][1]
    T0 = top[0]
    U = {
        "low_sneaker": [[(0.993, st), (1.0, st + 0.09), (0.99, 0.25), (0.965, 0.335)],
                        [(0.965, 0.335), (0.93, 0.33), (0.86, 0.29), (0.79, 0.277), (0.72, 0.298), (0.67, 0.33)],
                        [(0.67, 0.33), (0.665, 0.362), (0.635, 0.375), (0.605, 0.36)],
                        [(0.605, 0.36), (0.47, 0.3), (0.35, 0.25), (0.25, 0.228), (0.15, 0.21), (0.07, 0.188), (0.025, 0.155), T0]],
        "high_top": [[(0.993, st), (1.0, 0.2), (0.985, 0.38), (0.958, 0.535)],
                     [(0.958, 0.535), (0.86, 0.548), (0.76, 0.556), (0.705, 0.562)],
                     [(0.705, 0.562), (0.697, 0.592), (0.668, 0.6), (0.648, 0.582)],
                     [(0.648, 0.582), (0.5, 0.45), (0.36, 0.322), (0.25, 0.238), (0.15, 0.208), (0.07, 0.186), (0.025, 0.152), T0]],
        "runner": [[(0.99, st), (0.998, 0.25), (0.985, 0.35), (0.99, 0.405)],
                   [(0.99, 0.405), (0.965, 0.405), (0.93, 0.375), (0.85, 0.315), (0.77, 0.305), (0.7, 0.34), (0.668, 0.375)],
                   [(0.668, 0.375), (0.66, 0.405), (0.63, 0.418), (0.605, 0.4)],
                   [(0.605, 0.4), (0.48, 0.33), (0.36, 0.268), (0.25, 0.235), (0.15, 0.212), (0.07, 0.188), (0.025, 0.16), T0]],
        "slip_on": [[(0.993, st), (1.0, st + 0.08), (0.987, 0.26), (0.965, 0.3)],
                    [(0.965, 0.3), (0.9, 0.29), (0.8, 0.268), (0.7, 0.252), (0.625, 0.248)],
                    [(0.625, 0.248), (0.6, 0.262), (0.58, 0.268)],
                    [(0.58, 0.268), (0.47, 0.252), (0.36, 0.23), (0.25, 0.208), (0.14, 0.185), (0.06, 0.158), (0.02, 0.13), T0]],
        "loafer": [[(0.993, st), (1.0, 0.16), (0.99, 0.25), (0.975, 0.285)],
                   [(0.975, 0.285), (0.92, 0.28), (0.83, 0.255), (0.72, 0.235), (0.63, 0.226)],
                   [(0.63, 0.232), (0.605, 0.246), (0.585, 0.25)],
                   [(0.585, 0.25), (0.48, 0.242), (0.37, 0.223), (0.26, 0.198), (0.15, 0.168), (0.07, 0.138), (0.025, 0.105), T0]],
        "derby": [[(0.993, st), (1.0, 0.16), (0.99, 0.255), (0.975, 0.3)],
                  [(0.975, 0.3), (0.92, 0.292), (0.84, 0.262), (0.76, 0.257), (0.69, 0.28), (0.648, 0.302)],
                  [(0.648, 0.302), (0.64, 0.327), (0.617, 0.33), (0.6, 0.312)],
                  [(0.6, 0.312), (0.53, 0.272), (0.46, 0.238), (0.38, 0.214), (0.27, 0.188), (0.16, 0.158), (0.08, 0.128), (0.03, 0.098), T0]],
        "boot": [[(0.993, st), (1.003, 0.2), (0.99, 0.33), (0.975, 0.45), (0.982, 0.56)],
                 [(0.982, 0.56), (0.86, 0.566), (0.74, 0.562), (0.7, 0.566)],
                 [(0.7, 0.566), (0.694, 0.596), (0.664, 0.602), (0.645, 0.585)],
                 [(0.645, 0.585), (0.626, 0.47), (0.592, 0.375), (0.535, 0.305), (0.44, 0.27), (0.34, 0.253), (0.22, 0.232),
                  (0.12, 0.205), (0.05, 0.172), (0.018, 0.135), T0]],
        "chelsea_boot": [[(0.993, st), (1.003, 0.2), (0.99, 0.33), (0.975, 0.45), (0.978, 0.55)],
                         [(0.978, 0.55), (0.86, 0.535), (0.74, 0.537), (0.68, 0.552)],
                         [(0.68, 0.552), (0.655, 0.47), (0.615, 0.37), (0.545, 0.285), (0.445, 0.245), (0.33, 0.224), (0.21, 0.196),
                          (0.11, 0.16), (0.05, 0.128), (0.02, 0.1), T0]],
    }
    U["oxford"] = U["derby"]
    # the tables are drawn on a regular sole; a thicker or thinner one lifts or lowers the upper with it
    s_toe, s_heel = T0[1] - top_reg[0][1], st - top_reg[-1][1]
    groups = [[q if q in (T0, (0.993, st), (0.99, st)) else (q[0], q[1] + s_toe + (s_heel - s_toe) * q[0]) for q in g]
              for g in U[style]]
    toe = p.get("toe", "round")
    if toe in ("almond", "chisel", "pointed"):   # a longer, lower toe: the vamp slopes down to it
        k = {"almond": 0.88, "chisel": 0.8, "pointed": 0.6}[toe]
        groups[-1] = [q if q == T0 or q[0] > 0.4 else (q[0], T0[1] + (q[1] - T0[1]) * (k + (1 - k) * q[0] / 0.4))
                      for q in groups[-1]]
    shaft = p.get("shaft")
    if shaft and style in ("boot", "chelsea_boot", "high_top"):   # a taller or shorter shaft: stretch it above the ankle
        knee, hi = 0.3, max(v for g in groups for _, v in g)
        k = (max(0.35, min(0.95, float(shaft))) - knee) / (hi - knee)
        groups = [[(u, v if v <= knee else knee + (v - knee) * k) for u, v in g] for g in groups]
    if style == "boot" and not laced:   # a pull-on boot has no tongue: the collar runs straight across the front
        g = groups[2]
        groups[2] = [g[0], ((g[0][0] + g[-1][0]) / 2, (g[0][1] + g[-1][1]) / 2), g[-1]]
    if p.get("tongue") == "padded" and style in ("low_sneaker", "high_top", "runner", "derby", "oxford", "boot"):
        g = groups[2]                                  # a padded tongue stands above the collar
        groups[2] = [g[0]] + [(u, v + 0.035) for u, v in g[1:-1]] + [g[-1]]
    if p.get("backless") and style in ("slip_on", "loafer"):   # a clog: the back is cut away above the heel
        mid = groups[1][-1]
        groups[0] = [(0.993, st), (0.997, st + 0.02), (0.975, st + 0.04)]
        groups[1] = [(0.975, st + 0.04), (0.88, st + 0.05), (0.78, st + 0.08), (0.7, (st + 0.08 + mid[1]) / 2), mid]
    upper_d = _chain(groups)
    outline = f"{upper_d} {under} Z"
    sh = Shape(outline=outline)
    sole_part = f"M {_pt(_sp(*T0))} {under} " + _spline(list(reversed(top)), start=False) + " Z"
    sh.parts.append(Part(sole_part, "sole"))
    if heel_line:
        sh.parts.append(Part(heel_line, "edge", color="sole_line"))
    ys = [v for g in groups for _, v in g]
    top_y = SHOE_G - max(ys) * SHOE_L
    sh.bbox = (SHOE_X0 - 4, top_y - 14, SHOE_X0 + SHOE_L + 4, SHOE_G + 1)
    sh.body_box = (SHOE_X0, top_y, SHOE_X0 + SHOE_L, SHOE_G)
    sh.anchors = {"ground": (CX, SHOE_G), "toe": (SHOE_X0, SHOE_G), "heel": (SHOE_X0 + SHOE_L, SHOE_G)}
    sh.sole_default = "#3b2b21" if heeled else None
    sh.sole_default = {"crepe": "#c9a36b", "wedge": "#ece6d8", "jute": "#cdb88f", "siped": "#ece6d8",
                       "pebble": "#4a3326"}.get(tread, sh.sole_default)
    if p.get("backless"):                                 # a clog's cork footbed
        sh.sole_default = "#b98d5e"
    if lower == "all":                                    # a rain boot: a dark rubber sole, no welt
        sh.sole_default = "#2f3330"

    front = groups[-1]
    vtop = lambda u: _poly_v(front, u)     # height of the top edge over the vamp / lacing
    tf_at = lambda u: _poly_v(top, u)      # height of the sole top

    # ---- foxing stripe on a vulcanised sole, a welt stitch on a leather one
    if foxing:
        sh.parts.append(Part(_spline([(0.004, tf_at(0.01) * 0.6), (0.3, tf_at(0.3) * 0.5), (0.996, sole_top_heel[1] * 0.5)]),
                             "edge", color="sole_line"))
    if heeled and lower != "all":
        sh.parts.append(Part(_spline([(0.03, tf_at(0.03) - 0.012), (0.3, tf_at(0.3) - 0.012), (0.6, tf_at(0.6) - 0.012),
                                      (0.985, sole_top_heel[1] - 0.012)]), "stitch", color="sole_line"))

    # ---- what the sole is made of, as it shows from the side
    if tread == "lug":       # deep lugs: dark blocks along the bottom of the sole
        for i in range(13):
            u = 0.05 + i * 0.072
            if heeled and 0.48 < u < 0.79:
                continue
            lug = (f"M {_pt(_sp(u, 0))} L {_pt(_sp(u, 0.026))} L {_pt(_sp(u + 0.04, 0.026))} L {_pt(_sp(u + 0.04, 0))} Z")
            sh.parts.append(Part(lug, "inlay", color="sole_lug", clip=True))
    elif tread == "crepe":   # a crepe sole's soft, wavy edge
        sh.parts.append(Part(_spline([(0.02 + i * 0.07, 0.02 + (0.006 if i % 2 else 0)) for i in range(14)]),
                             "edge", color="sole_line"))
    elif tread == "cleats":  # studs under the sole
        for u in (0.08, 0.2, 0.32, 0.44, 0.74, 0.88):
            stud = f"M {_pt(_sp(u - 0.025, 0.03))} L {_pt(_sp(u - 0.015, 0))} L {_pt(_sp(u + 0.015, 0))} L {_pt(_sp(u + 0.025, 0.03))} Z"
            sh.parts.append(Part(stud, "inlay", color="sole_dark"))
    elif tread == "jute":    # a braided rope sole: short slanting strokes all round
        for i in range(30):
            u = 0.03 + i * 0.032
            v = tf_at(u) * 0.5
            sh.parts.append(Part(f"M {_pt(_sp(u, v - 0.02))} L {_pt(_sp(u + 0.016, v + 0.02))}", "edge", color="sole_line"))
    elif tread == "pebble":  # a driving moc's rubber pebbles run up the back of the heel
        for u, v in ((0.94, 0.05), (0.975, 0.075), (0.99, 0.12), (0.9, 0.035), (0.86, 0.03), (0.82, 0.03), (0.955, 0.1)):
            sh.parts.append(Part(_ring(_sp(u, v), 0.016 * SHOE_L, 0.01), "inlay", color="sole"))
    elif tread == "siped":   # a boat shoe's thin white sole, with its siping showing as one line
        sh.parts.append(Part(_spline([(0.02, tf_at(0.02) * 0.45), (0.5, tf_at(0.5) * 0.45), (0.99, sole_top_heel[1] * 0.45)]),
                             "edge", color="sole_line"))
    if heeled and p.get("heel") == "stacked":   # the leather lifts of a stacked heel
        for k in (0.33, 0.66):
            sh.parts.append(Part(f"M {_pt(_sp(0.78, hb * k))} L {_pt(_sp(0.995, hb * k))}", "edge", color="sole_line"))
    if lower in ("rubber", "all"):
        if lower == "rubber":   # a duck boot's rubber lower: up over the toe and round the foot, in the sole's colour
            rim = [(-0.02, 0.2), (0.12, 0.17), (0.3, 0.15), (0.48, 0.17), (0.6, 0.2), (0.75, 0.2), (0.9, 0.19), (1.03, 0.19)]
            d = _spline(rim) + f" L {_pt(_sp(1.03, -0.02))} L {_pt(_sp(-0.02, -0.02))} Z"
            sh.parts.insert(0, Part(d, "inlay", color="sole", clip=True))
        else:                   # a rain boot: a rolled rubber rim at the top of the shaft
            rim = groups[1]
            d = _spline(rim) + " " + _spline(_shift(rim[::-1], 0, -0.035), start=False) + " Z"
            sh.parts.append(Part(d, "band", clip=True))

    # ---- lacing: eyelets just under the top edge, laces crossing over it
    lace_span = {"low_sneaker": (0.35, 0.585), "high_top": (0.27, 0.62), "runner": (0.37, 0.585), "derby": (0.43, 0.585),
                 "oxford": (0.44, 0.58), "boot": (0.5, 0.64)}.get(style)
    a, b = lace_span or (0.44, 0.58)
    if laced and lace_span:
        n0 = {"high_top": 8, "boot": 7, "derby": 5, "oxford": 5, "runner": 6}.get(style, 6)
        n = max(2, min(10, int(p.get("eyelets") or n0)))
        if n != n0 and style != "boot":   # more or fewer eyelets: a longer or shorter facing, ending by the collar
            a = b - (b - a) * min(1.15, (n - 1) / (n0 - 1))
        drop = 0.036 if not heeled else 0.05 if style == "derby" else 0.026
        if style == "boot":
            pts = [(a + (b - a) * i / (n - 1)) for i in range(n)]
        else:
            pts = [a + (b - a) * i / (n - 1) for i in range(n)]
        eyelets = []
        for u in pts:
            uu = u
            if style == "boot":   # the boot's lacing runs up its front, which turns steep: walk along the curve
                pass
            v = vtop(uu) - drop
            eyelets.append((uu, v))
        if style == "boot":
            # place eyelets evenly along the front curve between heights 0.26 and 0.55
            curve = groups[-1][:5]
            seg = []
            for (u0, v0), (u1, v1) in zip(curve, curve[1:]):
                seg.append(((u0, v0), (u1, v1), math.hypot(u1 - u0, v1 - v0)))
            total = sum(s[2] for s in seg)
            eyelets = []
            for i in range(n):
                d = total * (0.06 + 0.86 * i / (n - 1))
                for (p0, p1, ln) in seg:
                    if d <= ln:
                        t = d / ln
                        u, v = p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t
                        # step inward, perpendicular to the edge
                        du, dv = p1[0] - p0[0], p1[1] - p0[1]
                        L = math.hypot(du, dv)
                        eyelets.append((u - dv / L * 0.03, v + du / L * 0.03))
                        break
                    d -= ln
            eyelets = [(u, v) for u, v in eyelets]
        # the eyelet stay: a seam under the eyelets, curving back into the collar
        e0, e1 = eyelets[-1], eyelets[0]
        if style in ("low_sneaker", "high_top", "runner"):
            sh.lines.append(_spline([(e1[0] - 0.03, e1[1] - 0.028), (e0[0] + 0.015, e0[1] - 0.045), (e0[0] + 0.06, e0[1] - 0.03)]))
        lw = 5.2 if not heeled else 3.6
        if style == "derby":
            # open lacing: the near facing's edge runs under the top of the shoe, and between it and the far facing
            # the tongue shows, with the laces crossing over it
            near = [(u, vtop(u) - 0.032) for u in (a - 0.03, a, (a + b) / 2, b, b + 0.03)]
            sh.parts.append(Part(_spline(near) + f" L {_pt(_sp(b + 0.03, 0.5))} L {_pt(_sp(a - 0.03, 0.5))} Z", "inlay",
                                 color="deep", clip=True))
            sh.lines.append(_spline(near))
        for i, (u, v) in enumerate(eyelets):
            ex, ey = _sp(u, v)
            tip = _sp(u - 0.035, vtop(u - 0.035) + 0.03)
            if style == "boot":
                tip = _sp(u - 0.034, v + 0.045)
            if style == "derby":   # each lace crosses the tongue to the far facing, over the eyelet in front
                if i == 0:
                    sh.dots.append((ex, ey, 2.0))
                    continue
                uf = eyelets[i - 1][0]   # and the lace from the eyelet in front crosses it, back to the far facing here
                sh.parts.append(Part(_capsule(_sp(*eyelets[i - 1]), _sp(u, vtop(u) - 0.004), 3.0), "inlay", color="lace", clip=True))
                tip = _sp(uf, vtop(uf) - 0.004)
            if style == "oxford":   # closed lacing: the facings meet, the laces lie flat and short across them
                tip = _sp(u - 0.024, vtop(u - 0.024) + 0.012)
            sh.parts.append(Part(_capsule((ex, ey), tip, lw), "inlay", color="lace", clip=True))
            top_ = i < int(p.get("hooks") or 0) if style == "boot" else i >= len(eyelets) - int(p.get("hooks") or 0)
            if top_:   # a speed hook (a boot's eyelets run from the top down): a metal hook open to the front
                hx, hy = _sp(u - 0.028, v + 0.026)
                sh.parts.append(Part(_capsule((ex, ey), (hx, hy), 5.0), "inlay", color=METAL))
                sh.parts.append(Part(_ring((hx, hy), 5.0, 2.4), "inlay", color=METAL))
                continue
            if p.get("rings"):   # a D-ring: a metal loop stitched to the facing, the lace through it
                sh.parts.append(Part(_ring((ex, ey), 4.6, 2.0), "inlay", color=METAL))
                continue
            sh.dots.append((ex, ey, 2.4 if not heeled else 2.0))
        if p.get("toggle"):   # a speed lace: one thin cord pulled through a lock above the top eyelet, its ends hanging
            tu, tv = eyelets[0] if style == "boot" else eyelets[-1]
            lock = _sp(tu - 0.05, tv + 0.07)
            sh.parts.append(Part(_capsule(_sp(tu, tv), lock, 3.0), "inlay", color="lace"))
            for end in ((tu - 0.1, tv + 0.02), (tu - 0.085, tv + 0.0)):
                sh.parts.append(Part(_capsule(lock, _sp(*end), 2.6), "inlay", color="lace"))
            sh.parts.append(Part(_capsule(_sp(tu - 0.054, tv + 0.085), _sp(tu - 0.046, tv + 0.055), 9.0), "inlay", color="deep"))

    # ---- per-style construction lines
    lift = lambda u: s_toe + (s_heel - s_toe) * u   # how far a thick sole has raised the upper here
    if style in ("low_sneaker", "runner"):
        # heel counter
        sh.lines.append(_spline([(0.8, sole_top_heel[1] - 0.01), (0.83, 0.2 + lift(0.83)), (0.89, 0.27 + lift(0.89)),
                                 (0.915, groups[1][1][1] - 0.01)]))
    if style == "runner":
        # a sweeping overlay from the midfoot to the heel, and a toe overlay
        sh.lines.append(_spline([(0.3, tf_at(0.3) + 0.002), (0.38, 0.2), (0.47, 0.235), (0.56, 0.27)]))
        sh.lines.append(_spline([(0.12, tf_at(0.12)), (0.14, 0.15), (0.17, 0.19), (0.19, 0.24)]))
        sh.lines.append(_spline([(0.02, tf_at(0.02) * 0.5), (0.3, 0.025), (0.7, 0.02), (0.99, 0.035)]))   # outsole
    if style == "slip_on":
        gore = _spline([(0.632, 0.27), (0.617, 0.215), (0.607, 0.192), (0.597, 0.215), (0.585, 0.275)])
        sh.parts.append(Part(gore + " Z", "band", clip=True))
    if style == "loafer":
        # the moccasin seam round the vamp, and what lies across it
        strap = p.get("strap", "penny")
        moc = [(0.6, 0.205), (0.48, 0.2), (0.34, 0.178), (0.2, 0.148), (0.1, 0.12), (0.04, 0.09)]
        sh.seams.append(_spline(moc[1:] if strap == "tassel" else moc))
        if strap == "penny":   # the saddle strap across the vamp under the topline, with the slot cut in it
            band = (_spline([(0.612, 0.3), (0.606, 0.2), (0.594, 0.152)]) + " " +
                    _spline([(0.594, 0.152), (0.52, 0.14), (0.44, 0.146)], start=False) + " " +
                    _spline([(0.44, 0.146), (0.432, 0.2), (0.435, 0.3)], start=False) + " Z")
            sh.parts.append(Part(band, "trim", clip=True))
            sh.lines.append(_spline([(0.436, vtop(0.436) - 0.014), (0.52, vtop(0.52) - 0.014), (0.606, vtop(0.606) - 0.014)]))
            lip = [(0.478, 0.2), (0.502, 0.214), (0.53, 0.219), (0.558, 0.214), (0.582, 0.2)]
            slot = (_spline(lip) + " " + _spline([(0.582, 0.2), (0.558, 0.19), (0.53, 0.187), (0.502, 0.19), (0.478, 0.2)],
                                                  start=False) + " Z")
            sh.parts.append(Part(slot, "inlay", color="#211813", clip=True))
        elif strap == "tassel":   # a lace runs round the collar and ties at the throat; two tassels hang on the vamp
            cord = _spline(_shift(groups[1], 0, -0.012)) + " " + _spline(_shift(groups[1][::-1], 0, -0.026), start=False) + " Z"
            sh.parts.append(Part(cord, "inlay", color="deep", clip=True))
            knot = (0.57, 0.2)
            sh.parts.append(Part(_capsule(_sp(0.632, vtop(0.632) - 0.018), _sp(*knot), 4.0), "inlay", color="deep", clip=True))
            for tx, ty in ((0.515, 0.182), (0.543, 0.172)):
                sh.parts.append(Part(_capsule(_sp(*knot), _sp(tx, ty), 4.0), "inlay", color="deep"))
                # the tassel hangs down and a little forward, towards the toe
                body = [(tx - 0.011, ty), (tx + 0.011, ty), (tx + 0.006, ty - 0.085), (tx - 0.022, ty - 0.097), (tx - 0.042, ty - 0.083)]
                sh.parts.append(Part("M " + " L ".join(_pt(_sp(*q)) for q in body) + " Z", "inlay", color="deep"))
                sh.parts.append(Part(_capsule(_sp(tx - 0.014, ty - 0.007), _sp(tx + 0.012, ty - 0.007), 8.0), "inlay", color="deep"))
                for k in (-0.014, 0.0, 0.014):
                    sh.parts.append(Part(f"M {_pt(_sp(tx + k * 0.6, ty - 0.016))} L {_pt(_sp(tx - 0.02 + k * 1.3, ty - 0.086))}", "edge"))
            sh.parts.append(Part(_ring(_sp(*knot), 5.0, 1.8), "inlay", color="deep"))
        elif strap == "horsebit":   # a metal bit across the throat: two links between a ring at each end
            for (u0, v0), (u1, v1) in (((0.476, 0.192), (0.522, 0.199)), ((0.522, 0.199), (0.564, 0.192))):
                sh.parts.append(Part(_capsule(_sp(u0, v0), _sp(u1, v1), 7.0), "inlay", color=METAL))
            sh.parts.append(Part(_ring(_sp(0.466, 0.192), 0.017 * SHOE_L, 0.009 * SHOE_L), "inlay", color=METAL))
            sh.parts.append(Part(_ring(_sp(0.578, 0.19), 0.022 * SHOE_L, 0.012 * SHOE_L), "inlay", color=METAL))
    if style in ("derby", "oxford"):
        e0 = a - 0.022                                   # just in front of the first eyelet
        e_lo = (e0, vtop(e0))
        punched = []                                     # seams with a row of brogue punching beside them
        if style == "derby":   # quarters stitched on top of the vamp: their front edge runs down and back
            edge = [(e_lo[0] - 0.005, e_lo[1] - 0.005), (e0 + 0.003, 0.17), (e0 + 0.055, 0.12), (e0 + 0.115, tf_at(e0 + 0.115) + 0.01)]
            sh.lines.append(_spline(edge))
            sh.parts.append(Part(_spline(_shift(edge, 0.012)), "stitch", color="sole_line"))   # the quarter's stitching
            punched.append(_shift(edge[1:], 0.024))
        else:                  # closed lacing: the vamp lies over the quarters, its seam sweeps back to the heel
            seam = [(e_lo[0] - 0.005, e_lo[1] - 0.005), (e0 + 0.025, 0.185), (e0 + 0.095, 0.16), (0.66, 0.15),
                    (0.72, 0.14), (0.75, tf_at(0.75) + 0.005)]
            if not p.get("wholecut"):   # a wholecut is one piece of leather: no vamp seam
                sh.lines.append(_spline(seam))
                punched.append(_shift(seam[1:], -0.014))
            # the facings meet over the tongue: their lower edge runs under the eyelets, from the throat to the collar
            sh.lines.append(_spline([(e0 - 0.004, vtop(e0 - 0.004) - 0.012), (e0 + 0.016, vtop(e0 + 0.016) - 0.044),
                                     (b, vtop(b) - 0.05), (b + 0.045, vtop(b + 0.045) - 0.032), (b + 0.062, vtop(b + 0.062))]))
        counter = [(0.86, tf_at(0.86)), (0.885, 0.17), (0.93, 0.24), (0.945, 0.29)]
        sh.lines.append(_spline(counter))
        punched.append(_shift(counter, -0.014))
        if brogue == "full":   # a wingtip: the wing cap's edge runs from the top of the toe back down to the welt
            wing = [(0.19, vtop(0.19) - 0.004), (0.205, 0.15), (0.24, 0.128), (0.3, 0.126), (0.36, 0.11), (0.41, 0.075),
                    (0.45, tf_at(0.45) + 0.002)]
            if style == "derby":   # the wing ends ahead of the quarters, which lie over it
                wing = [(0.19, vtop(0.19) - 0.004), (0.205, 0.15), (0.24, 0.128), (0.29, 0.122), (0.33, 0.1), (0.37, tf_at(0.37) + 0.002)]
            sh.lines.append(_spline(wing))
            sh.lines.append(_spline(_shift(wing, 0.012)))
            sh.parts.append(Part(_spline(_shift(wing, 0.025)), "punch", clip=True))
        if brogue in ("semi", "full"):   # a medallion on the toe, and punching along the seams
            for k, w in ((0.007, 0.04), (0.018, 0.028), (0.029, 0.016)):   # a fan of punching on top of the toe
                sh.parts.append(Part(_spline([(0.13 - w, vtop(0.13 - w) - k), (0.13, vtop(0.13) - k - 0.012), (0.13 + w, vtop(0.13 + w) - k)]),
                                     "punch", clip=True))
            for run in punched:
                sh.parts.append(Part(_spline(run), "punch", clip=True))
    if style == "boot":
        sh.lines.append(_spline([(0.52, 0.29), (0.53, 0.2), (0.56, 0.14), (0.62, tf_at(0.62) + 0.008)]))
        sh.lines.append(_spline([(0.82, tf_at(0.82)), (0.85, 0.2), (0.9, 0.25), (0.99, 0.27)]))
    if style == "chelsea_boot":
        g = (_spline([(0.735, 0.6), (0.745, 0.47), (0.77, 0.36), (0.8, 0.29)]) + " " +
             _spline([(0.8, 0.29), (0.83, 0.36), (0.855, 0.47), (0.865, 0.6)], start=False) + " Z")
        sh.parts.append(Part(g, "band", clip=True))
        for i in range(1, 6):
            x = 0.745 + i * 0.02
            sh.lines.append(_spline([(x, 0.56), (x + (0.8 - x) * 0.25, 0.42)]))
        sh.lines.append(_spline([(0.86, tf_at(0.86)), (0.885, 0.17), (0.93, 0.24), (0.99, 0.26)]))

    # ---- pull loops: at the back of boots and runners, at the front of a chelsea
    tab = p.get("heel_tab", "none")
    tab_role = dict(color="trim") if tab == "contrast" else {}
    if style in ("boot", "chelsea_boot", "high_top"):
        hx = groups[1][0]
        lu = hx[0] - 0.035
        loop = (f"M {_pt(_sp(lu, hx[1] - 0.04))} L {_pt(_sp(lu + 0.002, hx[1] + 0.045))} "
                f"Q {_pt(_sp(lu + 0.02, hx[1] + 0.06))} {_pt(_sp(lu + 0.038, hx[1] + 0.045))} L {_pt(_sp(lu + 0.04, hx[1] - 0.04))} Z")
        if style != "high_top" and not p.get("pull_tabs"):
            sh.behind.append(Part(loop, "trim"))
            sh.bbox = (sh.bbox[0], min(sh.bbox[1], SHOE_G - (hx[1] + 0.065) * SHOE_L), sh.bbox[2], sh.bbox[3])
    if style == "chelsea_boot":
        fx = groups[2][0]
        loop = (f"M {_pt(_sp(fx[0] - 0.005, fx[1] - 0.04))} L {_pt(_sp(fx[0] - 0.01, fx[1] + 0.04))} "
                f"Q {_pt(_sp(fx[0] + 0.008, fx[1] + 0.058))} {_pt(_sp(fx[0] + 0.028, fx[1] + 0.035))} L {_pt(_sp(fx[0] + 0.03, fx[1] - 0.04))} Z")
        sh.behind.append(Part(loop, "trim"))
    if style in ("low_sneaker", "runner", "high_top") and tab == "contrast" or style == "runner":
        hx = groups[1][0]
        d = (f"M {_pt(_sp(hx[0] - 0.05, hx[1] + 0.02))} L {_pt(_sp(hx[0] - 0.045, hx[1] - 0.12))} "
             f"L {_pt(_sp(1.02, hx[1] - 0.13))} L {_pt(_sp(1.02, hx[1] + 0.02))} Z")
        sh.parts.append(Part(d, "inlay", clip=True, **tab_role))

    # ---- toe cap: a seam, or a rubber bumper in the sole colour
    if toe_cap == "stitched":
        u0 = 0.21 if heeled else 0.24
        sh.lines.append(_spline([(u0, tf_at(u0) - 0.005), (u0 - 0.008, tf_at(u0) + 0.05), (u0 - 0.03, vtop(u0 - 0.03) + 0.01)]))
        if heeled:
            sh.lines.append(_spline([(u0 + 0.012, tf_at(u0) - 0.005), (u0 + 0.004, tf_at(u0) + 0.05), (u0 - 0.018, vtop(u0 - 0.018) + 0.01)]))
        if brogue in ("quarter", "semi"):
            sh.parts.append(Part(_spline([(u0 + 0.025, tf_at(u0) - 0.005), (u0 + 0.017, tf_at(u0) + 0.05),
                                          (u0 - 0.005, vtop(u0 - 0.005) + 0.01)]), "punch", clip=True))
    elif toe_cap == "rubber":
        d = (f"M {_pt(_sp(-0.05, 0.0))} L {_pt(_sp(0.17, tf_at(0.17) - 0.01))} "
             + _spline([(0.17, tf_at(0.17) - 0.01), (0.165, 0.15), (0.13, 0.2), (0.11, 0.3)], start=False)
             + f" L {_pt(_sp(-0.05, 0.3))} Z")
        sh.parts.insert(0, Part(d, "inlay", color="sole", clip=True))

    # ---- what the kind adds
    if p.get("moc") and style != "loafer":   # a moc toe: a raised seam round the top of the toe, stitched
        # the apron's edge: from low on the toe's front, back along the top of the foot, up into the throat
        seam = [(0.02, tf_at(0.02) + 0.03), (0.06, vtop(0.06) - 0.045)] + [(u, vtop(u) - 0.045) for u in (0.15, 0.25, 0.35)]
        seam.append((0.44, vtop(0.44) - 0.008))
        sh.lines.append(_spline(seam))
        sh.lines.append(_spline(_shift(seam[1:-1], 0, 0.014)))   # the raised ridge's other side
        sh.parts.append(Part(_spline(_shift(seam[1:-1], 0, -0.012)), "stitch", color="deep"))
    if p.get("gusset") and style != "chelsea_boot" and style in ("boot", "high_top", "slip_on", "loafer", "derby"):
        top_g = max(v for _, v in groups[1]) - 0.01
        g = (_spline([(0.735, top_g + 0.03), (0.745, top_g * 0.8), (0.77, top_g * 0.62), (0.8, top_g * 0.5)]) + " " +
             _spline([(0.8, top_g * 0.5), (0.83, top_g * 0.62), (0.855, top_g * 0.8), (0.865, top_g + 0.03)], start=False) + " Z")
        sh.parts.append(Part(g, "band", clip=True))
    strap = p.get("strap", "none") if style != "loafer" else "none"

    def buckled(band, at, w=0.03):
        sh.parts.append(Part(band, "trim", clip=True))
        cx, cy = _sp(*at)
        sh.parts.append(Part(_frame((cx, cy), w * SHOE_L, w * SHOE_L * 1.3, 0.008 * SHOE_L), "inlay", color=METAL))

    def band(pts, w):
        return _spline(pts) + " " + _spline(_shift(pts[::-1], 0, -w), start=False) + " Z"
    if strap == "engineer":   # a strap over the instep and one round the top of the shaft, each buckled
        buckled(band([(0.5, vtop(0.5) + 0.05), (0.58, 0.25), (0.67, 0.16), (0.75, tf_at(0.75) + 0.035)], 0.065), (0.6, 0.22), 0.05)
        t = max(v for _, v in groups[1])
        buckled(band([(0.6, t - 0.04), (0.8, t - 0.035), (1.03, t - 0.035)], 0.045), (0.86, t - 0.06), 0.045)
    elif strap == "jodhpur":   # a strap from the back round the ankle, buckled on the outer side
        buckled(band([(0.74, 0.345), (0.86, 0.35), (1.03, 0.37)], 0.045), (0.77, 0.325), 0.045)
    elif strap in ("monk", "double_monk"):   # a strap across the throat, buckled on the outer side
        for k in ((0.0,) if strap == "monk" else (0.0, -0.07)):
            u0 = 0.5 + k
            buckled(band([(u0 - 0.03, vtop(u0 - 0.03) + 0.03), (u0 + 0.02, 0.21 + k * 0.4), (u0 + 0.1, 0.17 + k * 0.4)], 0.04),
                    (u0 + 0.1, 0.15 + k * 0.4), 0.045)
    elif strap == "velcro":   # straps across the instep
        for u0 in (0.42, 0.52):
            sh.parts.append(Part(band([(u0 - 0.03, vtop(u0 - 0.03) + 0.03), (u0 + 0.02, 0.22), (u0 + 0.05, 0.17)], 0.05), "trim",
                                 clip=True))
    if p.get("collar_pad"):   # a padded collar, or a snow boot's fleece cuff
        pad = band(_shift(groups[1], 0, 0.005), 0.05 if style != "boot" else 0.07)
        sh.parts.append(Part(pad, "band", clip=True))
    if p.get("lace_collar"):   # a rawhide lace round the collar, through the vamp, tied at the side
        cord = _spline(_shift(groups[1], 0, -0.014)) + " " + _spline(_shift(groups[1][::-1], 0, -0.028), start=False) + " Z"
        sh.parts.append(Part(cord, "inlay", color="lace", clip=True))
        knot = _sp(0.7, groups[1][-2][1] - 0.02)
        for tip in ((0.63, 0.13), (0.7, 0.115)):   # the two ends hang from the knot, splayed
            sh.parts.append(Part(_capsule(knot, _sp(*tip), 5.0), "inlay", color="lace"))
        sh.parts.append(Part(_ring(knot, 7.0, 2.4), "inlay", color="lace"))
        for u in (0.48, 0.55):   # and two eyelets on the vamp
            sh.dots.append((*_sp(u, vtop(u) - 0.03), 2.2))
    if p.get("pull_tabs"):   # a western boot's pull tab, standing at the top of the shaft's side seam
        t = (0.82, _poly_v(groups[1][::-1], 0.82))
        tab_d = (f"M {_pt(_sp(t[0] - 0.02, t[1] - 0.03))} L {_pt(_sp(t[0] - 0.022, t[1] + 0.06))} "
                 f"Q {_pt(_sp(t[0], t[1] + 0.085))} {_pt(_sp(t[0] + 0.022, t[1] + 0.06))} L {_pt(_sp(t[0] + 0.02, t[1] - 0.03))} Z")
        sh.behind.append(Part(tab_d, "trim"))
        sh.bbox = (sh.bbox[0], min(sh.bbox[1], SHOE_G - (t[1] + 0.1) * SHOE_L), sh.bbox[2], sh.bbox[3])
    if kind == "western_boot":   # decorative stitching on the shaft
        t = max(v for _, v in groups[1])
        for k in (0.0, 0.03, 0.06):
            sh.parts.append(Part(_spline([(0.7, t - 0.12 - k), (0.78, t - 0.2 - k), (0.86, t - 0.14 - k), (0.93, t - 0.22 - k)]),
                                 "stitch", color="deep"))
    if kind in ("leather_court_sneaker", "retro_court_shoe"):   # perforations on the toe box, an overlay at the toe
        for i in range(4):
            for j in range(2):
                u = 0.14 + i * 0.035 + j * 0.017
                sh.dots.append((*_sp(u, vtop(u) - 0.035 - j * 0.025), 1.2))
        sh.lines.append(_spline([(0.25, tf_at(0.25)), (0.26, 0.14), (0.24, 0.19), (0.23, vtop(0.23))]))
    if kind == "retro_court_shoe" or kind == "retro_runner":   # overlays: a suede toe, an eyestay, a heel piece
        sh.parts.append(Part(_spline([(0.08, tf_at(0.08)), (0.13, 0.16), (0.2, vtop(0.2) - 0.01)]) +
                             f" L {_pt(_sp(-0.05, 0.3))} L {_pt(_sp(-0.05, 0))} Z", "inlay", color="deep", clip=True))
        sh.lines.append(_spline([(0.4, tf_at(0.4)), (0.5, 0.16), (0.6, 0.24), (0.66, vtop(0.66) if style != "runner" else 0.3)]))

    # ---- patent leather: a hard gloss, two bright streaks catching the light along the toe and the heel
    if p.get("shine"):
        sh.parts.append(Part(band([(0.05, vtop(0.05) - 0.045), (0.12, vtop(0.12) - 0.032), (0.22, vtop(0.22) - 0.03),
                                   (0.3, vtop(0.3) - 0.034)], 0.016), "shine", clip=True))
        sh.parts.append(Part(band([(0.8, tf_at(0.8) + 0.06), (0.86, tf_at(0.86) + 0.07), (0.93, tf_at(0.93) + 0.075)], 0.012),
                             "shine", clip=True))

    # ---- a contrast side panel
    if p.get("stripe", "none") == "side":
        d = (_spline([(0.42, tf_at(0.42) - 0.01), (0.52, 0.16), (0.6, 0.235), (0.66, 0.285)]) + " "
             + _spline([(0.66, 0.285), (0.7, 0.26), (0.72, 0.22)], start=False) + " "
             + _spline([(0.72, 0.22), (0.66, 0.17), (0.58, tf_at(0.58) - 0.01)], start=False) + " Z")
        sh.parts.append(Part(d, "inlay", color="trim", clip=True))
    return sh


# -------------------------------------------------------------- accessories
# Bags, belts, hats and scarves, front view, in the same style as the clothes. Each is drawn in centimetres
# about one point on the wearer (its anchor): a hat's "head" (the middle of its band, where it meets the
# forehead), a belt's "waist" (the middle of the strap, worn), a scarf's "neck" (the base of the neck its loop
# goes round) and a bag's "hand" (the top of its handle or strap). With `px` (pixels per centimetre) the anchor
# is put at (CX, 0) at that scale, as the outfit figure wants it; without, the piece is scaled to fill the card.
# The other accessories (ties, gloves, glasses ...) have no shape of their own yet: `accessory` draws a plain tag.

BUCKLE = {"brass": "#b8955a", "nickel": "#c4c6c9", "gunmetal": "#5d6066", "matte_black": "#2a2b2e"}
FIT_W, FIT_H = 330.0, 380.0   # the room an accessory may take on its card


@dataclass
class _Draft:
    """An accessory in centimetres about its anchor: path commands, as (op, point, ...) tuples."""
    outline: list
    parts: list = field(default_factory=list)    # (cmds, role, color, clip)
    behind: list = field(default_factory=list)   # (cmds, role, color)
    lines: list = field(default_factory=list)    # cmds
    dots: list = field(default_factory=list)     # (x, y, r)
    anchor: str = "anchor"

    def part(self, cmds, role="trim", color=None, clip=False):
        self.parts.append((cmds, role, color, clip))

    def line(self, *pts):
        self.lines.append([("M", pts[0])] + [("L", q) for q in pts[1:]])


def _path(cmds, k, ox, oy):
    """An SVG path from commands in centimetres, and points along it (for its extent)."""
    t = lambda q: (ox + q[0] * k, oy + q[1] * k)
    d, pts, cur, start = [], [], (ox, oy), (ox, oy)
    for op, *args in cmds:
        args = [t(q) for q in args]
        if op == "M":
            cur = start = args[0]
            pts.append(cur)
        elif op == "L":
            pts.append(args[0])
            cur = args[0]
        elif op == "Q":
            pts += _qbez(cur, *args)
            cur = args[-1]
        elif op == "C":
            pts += _bez(cur, *args)
            cur = args[-1]
        else:
            cur = start
        d.append(op + "".join(" " + _pt(a) for a in args))
    return " ".join(d), pts


def _finish(dr: _Draft, px=None) -> Shape:
    """The draft at `px` pixels per centimetre with its anchor at (CX, 0), or fitted to the card."""
    if px is None:
        pts = [q for c in [dr.outline] + [p[0] for p in dr.parts] + [b[0] for b in dr.behind]
               for q in _path(c, 1.0, 0.0, 0.0)[1]]
        pts += [(x + s * r, y + s * r) for x, y, r in dr.dots for s in (-1, 1)]
        x0, x1 = min(x for x, _ in pts), max(x for x, _ in pts)
        y0, y1 = min(y for _, y in pts), max(y for _, y in pts)
        k = min(14.0, FIT_W / max(x1 - x0, 1e-6), FIT_H / max(y1 - y0, 1e-6))
        ox, oy = CX - (x0 + x1) / 2 * k, H / 2 - (y0 + y1) / 2 * k
    else:
        k, ox, oy = float(px), CX, 0.0
    outline, pts = _path(dr.outline, k, ox, oy)
    sh = Shape(outline)
    for cmds, role, color, clip in dr.parts:
        d, more = _path(cmds, k, ox, oy)
        sh.parts.append(Part(d, role, color, clip))
        pts += more
    for cmds, role, color in dr.behind:
        d, more = _path(cmds, k, ox, oy)
        sh.behind.append(Part(d, role, color))
        pts += more
    sh.lines = [_path(c, k, ox, oy)[0] for c in dr.lines]
    sh.dots = [(ox + x * k, oy + y * k, r * k) for x, y, r in dr.dots]
    pts += [(ox + (x + s * r) * k, oy + (y + s * r) * k) for x, y, r in dr.dots for s in (-1, 1)]
    sh.bbox = (min(x for x, _ in pts), min(y for _, y in pts), max(x for x, _ in pts), max(y for _, y in pts))
    sh.body_box = sh.bbox
    sh.anchors = {dr.anchor: (ox, oy)}
    return sh


def _rr(x0, y0, x1, y1, r, reverse=False):
    """A rounded rectangle; drawn the other way round with `reverse` (a hole in a shape drawn the usual way)."""
    if not reverse:
        return [("M", (x0 + r, y0)), ("L", (x1 - r, y0)), ("Q", (x1, y0), (x1, y0 + r)), ("L", (x1, y1 - r)),
                ("Q", (x1, y1), (x1 - r, y1)), ("L", (x0 + r, y1)), ("Q", (x0, y1), (x0, y1 - r)), ("L", (x0, y0 + r)),
                ("Q", (x0, y0), (x0 + r, y0)), ("Z",)]
    return [("M", (x0 + r, y0)), ("Q", (x0, y0), (x0, y0 + r)), ("L", (x0, y1 - r)), ("Q", (x0, y1), (x0 + r, y1)),
            ("L", (x1 - r, y1)), ("Q", (x1, y1), (x1, y1 - r)), ("L", (x1, y0 + r)), ("Q", (x1, y0), (x1 - r, y0)), ("Z",)]


def _ellipse(cx, cy, rx, ry):
    m = 0.5523
    return [("M", (cx - rx, cy)), ("C", (cx - rx, cy - ry * m), (cx - rx * m, cy - ry), (cx, cy - ry)),
            ("C", (cx + rx * m, cy - ry), (cx + rx, cy - ry * m), (cx + rx, cy)),
            ("C", (cx + rx, cy + ry * m), (cx + rx * m, cy + ry), (cx, cy + ry)),
            ("C", (cx - rx * m, cy + ry), (cx - rx, cy + ry * m), (cx - rx, cy)), ("Z",)]


def _arch(x, y, half, top, width):
    """A strap or handle rising from (±half, y) to `top`, `width` wide (a band: its outer and inner edges)."""
    o, i = half + width / 2, half - width / 2
    lift = (y - top) * 4 / 3
    return [("M", (x - o, y)), ("C", (x - o, y - lift - width * 0.5), (x + o, y - lift - width * 0.5), (x + o, y)),
            ("L", (x + i, y)), ("C", (x + i, y - lift + width * 0.9), (x - i, y - lift + width * 0.9), (x - i, y)), ("Z",)]


HAT_STYLES = ("structured", "dad", "five_panel", "trucker")


def cap(**kw) -> Shape:
    """A peaked cap from the front: a crown of panels over a curved peak. style: structured | dad | five_panel | trucker."""
    style = kw.get("style", "structured")
    hc = {"structured": 12.0, "dad": 10.0, "five_panel": 11.0, "trucker": 13.0}.get(style, 12.0)
    soft = style == "dad"
    hw, bw, drop = 8.6, 9.8, (5.5 if style != "five_panel" else 4.2)
    top = 0.62 if soft else 0.5
    dr = _Draft([("M", (-bw, 0.4)), ("L", (-hw, 0.0)),
                 ("C", (-hw - 0.3, -hc * 0.7), (-hw * top, -hc), (0, -hc)),
                 ("C", (hw * top, -hc), (hw + 0.3, -hc * 0.7), (hw, 0.0)),
                 ("L", (bw, 0.4)), ("Q", (0, drop * 2 - 0.4), (-bw, 0.4)), ("Z",)], anchor="head")
    # the peak, its top a shade apart from the crown; the crown's seam along it
    dr.part([("M", (-bw, 0.4)), ("Q", (0, 2.6), (bw, 0.4)), ("Q", (0, drop * 2 - 0.4), (-bw, 0.4)), ("Z",)])
    dr.lines.append([("M", (-bw * 0.8, 1.2)), ("Q", (0, drop * 1.65), (bw * 0.8, 1.2))])   # stitching round the peak
    if style == "five_panel":   # one wide flat front panel
        dr.lines.append([("M", (-4.2, 1.2)), ("C", (-4.4, -4), (-3.6, -hc * 0.8), (0, -hc))])
        dr.lines.append([("M", (4.2, 1.2)), ("C", (4.4, -4), (3.6, -hc * 0.8), (0, -hc))])
    else:
        dr.line((0, -hc), (0, 1.3))
        for s in (-1, 1):
            dr.lines.append([("M", (0, -hc)), ("C", (s * 4.5, -hc * 0.8), (s * 6.2, -hc * 0.35), (s * 6.4, 0.6))])
            dr.dots.append((s * 4.6, -hc * 0.62, 0.28))   # eyelets
    if style == "trucker":   # mesh on the side panels
        for s in (-1, 1):
            for i in range(6):
                y = -hc * 0.75 + i * 1.7
                dr.line((s * 6.2, y), (s * 9.5, y + 2.4))
                dr.line((s * 6.2, y + 2.4), (s * 9.5, y))
    dr.part(_ellipse(0, -hc + 0.25, 0.75, 0.4), "inlay")   # the button on top
    return _finish(dr, kw.get("px"))


def beanie(**kw) -> Shape:
    """A soft hat with no brim. style: cuffed | fisherman (short, high, deep cuff) | beret | trapper (ear flaps)."""
    style = kw.get("style", "cuffed")
    if style == "beret":
        dr = _Draft([("M", (-8.6, 0.0)), ("L", (-8.8, -1.6)), ("C", (-15.5, -2.2), (-14.5, -9.5), (-3, -9.8)),
                     ("C", (7, -10.2), (14.5, -6.5), (13.5, -3.2)), ("C", (13, -1.6), (10.5, -1.4), (8.8, -1.6)),
                     ("L", (8.6, 0.0)), ("Q", (0, 0.6), (-8.6, 0.0)), ("Z",)], anchor="head")
        dr.part([("M", (-8.6, 0.0)), ("L", (-8.8, -1.6)), ("Q", (0, -2.2), (8.8, -1.6)), ("L", (8.6, 0.0)),
                 ("Q", (0, 0.6), (-8.6, 0.0)), ("Z",)], "band")
        dr.part([("M", (-0.4, -9.8)), ("L", (-0.2, -11.3)), ("L", (0.8, -11.2)), ("L", (0.8, -9.8)), ("Z",)], "inlay")
        return _finish(dr, kw.get("px"))
    tall, cuff, hw = {"cuffed": (20.0, 6.0, 9.2), "fisherman": (13.5, 5.5, 9.4), "trapper": (17.0, 5.0, 9.6)}.get(style, (20.0, 6.0, 9.2))
    dome = [("M", (-hw + 0.2, 0.0)), ("L", (-hw, -cuff)),
            ("C", (-hw, -tall * 0.78), (-hw * 0.55, -tall), (0, -tall)),
            ("C", (hw * 0.55, -tall), (hw, -tall * 0.78), (hw, -cuff)), ("L", (hw - 0.2, 0.0)),
            ("Q", (0, 0.8), (-hw + 0.2, 0.0)), ("Z",)]
    outline = list(dome)
    if style == "trapper":   # ear flaps hanging from the sides, under the turned-up front
        for s in (-1, 1):
            outline += [("M", (s * (hw - 0.4), -2.0)), ("L", (s * (hw + 0.4), 7.5)),
                        ("Q", (s * (hw - 1.6), 11.0), (s * (hw - 4.6), 7.8)), ("L", (s * (hw - 4.2), 0.2)), ("Z",)]
    dr = _Draft(outline, anchor="head")
    dr.part([("M", (-hw + 0.2, 0.0)), ("L", (-hw, -cuff)), ("Q", (0, -cuff - 0.7), (hw, -cuff)),
             ("L", (hw - 0.2, 0.0)), ("Q", (0, 0.8), (-hw + 0.2, 0.0)), ("Z",)], "band")
    if style != "trapper":   # rib running up the cuff, and the crown gathered to the top
        n = int(hw * 2 / 1.1)
        for i in range(1, n):
            x = -hw + i * 2 * hw / n
            dr.line((x, -cuff - 0.2), (x, 0.9))
        for x in (-5.0, -1.8, 1.8, 5.0):
            dr.lines.append([("M", (x * 1.15, -cuff - 0.4)), ("Q", (x * 0.85, -tall * 0.75), (x * 0.25, -tall + 0.3))])
    else:
        for s in (-1, 1):
            dr.lines.append([("M", (s * (hw - 1.4), 1.2)), ("L", (s * (hw - 0.9), 7.2))])
        dr.line((0, -tall), (0, -cuff - 0.4))
    return _finish(dr, kw.get("px"))


# crown height, crown top half width, top shape, brim half width, brim tip height, brim fall at the front, band
_BRIMMED = {
    "fedora": (11.0, 7.0, "dent", 15.0, -1.2, 2.6, 2.0),
    "trilby": (9.5, 6.5, "dent", 11.0, -0.6, 3.0, 1.8),
    "panama": (11.0, 7.0, "dent", 15.0, -1.2, 2.6, 2.0),
    "wide_brim": (12.0, 7.2, "dent", 20.0, -1.0, 3.2, 2.2),
    "cowboy": (13.0, 7.6, "cattleman", 19.0, -5.5, 3.0, 1.6),
    "boater": (8.0, 8.8, "flat", 15.0, -0.6, 1.4, 3.4),
    "bucket": (8.5, 7.6, "round", 0.0, 0.0, 0.0, 0.0),
    "flat_cap": (6.2, 9.4, "low", 8.4, 0.2, 3.6, 0.0),
    "newsboy": (8.2, 10.6, "full", 8.4, 0.2, 3.6, 0.0),
}


def brimmed_hat(**kw) -> Shape:
    """A hat with a brim or a short peak, from the front. style: fedora | trilby | panama | wide_brim | cowboy |
    boater | bucket | flat_cap | newsboy."""
    style = kw.get("style", "fedora")
    hc, tw, top, bw, tip, fall, band = _BRIMMED.get(style, _BRIMMED["fedora"])
    hw = 8.6
    if top == "dent":
        crown = [("C", (-hw + 0.3, -hc * 0.6), (-tw - 0.2, -hc + 1), (-tw, -hc)),
                 ("Q", (-tw * 0.5, -hc - 1.2), (0, -hc + 1.3)), ("Q", (tw * 0.5, -hc - 1.2), (tw, -hc)),
                 ("C", (tw + 0.2, -hc + 1), (hw - 0.3, -hc * 0.6), (hw, -0.8))]
    elif top == "cattleman":
        crown = [("C", (-hw + 0.3, -hc * 0.6), (-tw - 0.5, -hc + 1), (-tw, -hc)),
                 ("Q", (-tw * 0.6, -hc - 0.8), (-2.2, -hc + 0.6)), ("Q", (0, -hc + 2.4), (2.2, -hc + 0.6)),
                 ("Q", (tw * 0.6, -hc - 0.8), (tw, -hc)), ("C", (tw + 0.5, -hc + 1), (hw - 0.3, -hc * 0.6), (hw, -0.8))]
    elif top == "flat":
        crown = [("L", (-tw, -hc)), ("L", (tw, -hc)), ("L", (hw, -0.8))]
    elif top == "round":
        crown = [("C", (-hw, -hc * 0.75), (-tw, -hc), (0, -hc)), ("C", (tw, -hc), (hw, -hc * 0.75), (hw, -0.8))]
    else:   # a flat cap or a newsboy: a crown wider than the head, sloping forward onto the peak
        crown = [("C", (-tw - 0.4, -2.5), (-tw * 0.85, -hc), (0, -hc)), ("C", (tw * 0.85, -hc), (tw + 0.4, -2.5), (hw, -0.8))]
    if style == "bucket":   # the brim slopes down all round
        outline = ([("M", (-hw - 0.2, -0.8))] + crown +
                   [("L", (13.2, 5.6)), ("Q", (0, 9.4), (-13.2, 5.6)), ("Z",)])
        dr = _Draft(outline, anchor="head")
        dr.part([("M", (-hw - 0.2, -0.8)), ("Q", (0, 0.4), (hw, -0.8)), ("L", (13.2, 5.6)), ("Q", (0, 9.4), (-13.2, 5.6)),
                 ("Z",)])
        for f in (0.35, 0.6, 0.85):   # rows of stitching round the brim
            dr.lines.append([("M", (-hw - 4.6 * f, -0.8 + 6.4 * f)), ("Q", (0, 0.4 + 7.6 * f), (hw + 4.6 * f, -0.8 + 6.4 * f))])
        dr.lines.append([("M", (-hw + 0.4, -3.0)), ("Q", (0, -1.8), (hw - 0.4, -3.0))])
        return _finish(dr, kw.get("px"))
    # the brim as seen from the front: its upper edge rises from each tip to the crown, its front edge falls below
    up = [("M", (-bw, tip)), ("Q", (-(bw + hw) / 2, tip - 0.4 if tip < -2 else -1.2), (-hw - 0.2, -0.8))]
    down = [("Q", ((bw + hw) / 2, tip - 0.4 if tip < -2 else -1.2), (bw, tip)), ("Q", (0, fall * 2 - tip), (-bw, tip)), ("Z",)]
    dr = _Draft(up + crown + down, anchor="head")
    dr.part(up + [("Q", (0, 0.5), (hw, -0.8))] + down)   # the brim, a shade apart from the crown
    if band:
        dr.part([("M", (-hw - 0.4, -0.5)), ("L", (-hw + 0.1, -0.8 - band)), ("Q", (0, -band - 0.2), (hw - 0.1, -0.8 - band)),
                 ("L", (hw + 0.4, -0.5)), ("Q", (0, 0.6), (-hw - 0.4, -0.5)), ("Z",)], "band", clip=True)
    if top in ("dent", "cattleman"):   # the pinches at the front of the crown
        for s in (-1, 1):
            dr.lines.append([("M", (s * 1.6, -hc + 1.4)), ("Q", (s * 3.2, -hc + 3.5), (s * 3.0, -hc + 5.5))])
    if style == "panama":   # woven straw
        for i in range(1, int(hc / 1.1)):
            y = -0.8 - band - i * 1.1
            dr.lines.append([("M", (-hw, y)), ("Q", (0, y + 0.5), (hw, y))])
        for f in (0.45, 0.75):
            dr.lines.append([("M", (-bw * f - hw * (1 - f), tip * f)), ("Q", (0, (fall * 2 - tip) * f + 0.4), (bw * f + hw * (1 - f), tip * f))])
    if style in ("flat_cap", "newsboy"):
        dr.lines.append([("M", (-hw + 0.5, -1.2)), ("Q", (0, -0.2), (hw - 0.5, -1.2))])   # where the crown is snapped to the peak
    if style == "newsboy":   # eight panels to a button on top
        for x in (-7.0, -3.4, 3.4, 7.0):
            dr.lines.append([("M", (0, -hc)), ("Q", (x * 0.8, -hc * 0.7), (x, -1.4))])
        dr.part(_ellipse(0, -hc + 0.2, 0.8, 0.45), "inlay")
    return _finish(dr, kw.get("px"))


# strap width (cm), buckle size, buckle colour, holes, stitching
_BELTS = {"dress": (3.0, 1.0, "nickel", True), "casual": (3.8, 1.25, "brass", True),
          "braided": (3.5, 1.15, "brass", False), "web": (3.2, 1.0, "gunmetal", False),
          "elastic": (3.5, 1.1, "nickel", False), "western": (4.0, 1.6, "nickel", True)}


def belt(**kw) -> Shape:
    """A belt. On its own card it lies folded in half, buckle at the top left and the tip at the bottom; `worn`
    draws the front of it fastened round the waist, `half` cm either side of the buckle. style: dress | casual |
    braided | web | elastic | western. `buckle`: brass | nickel | gunmetal | matte_black."""
    style = kw.get("style", "casual")
    w, bk, metal, holes = _BELTS.get(style, _BELTS["casual"])
    metal = BUCKLE.get(kw.get("buckle") or metal, BUCKLE["nickel"])
    if kw.get("worn"):
        half = float(kw.get("half", 17.2))
        dr = _Draft([("M", (-half, -w / 2 + 0.15)), ("Q", (0, -w / 2 - 0.25), (half, -w / 2 + 0.15)),
                     ("L", (half, w / 2 + 0.15)), ("Q", (0, w / 2 - 0.25), (-half, w / 2 + 0.15)), ("Z",)], anchor="waist")
        bw_ = 2.4 * bk
        # the end of the strap past the buckle, then the buckle's frame and its prong
        dr.part([("M", (bw_ * 0.4, -w / 2 + 0.05)), ("L", (bw_ + 5.0, -w / 2 + 0.1)), ("L", (bw_ + 6.0, 0.0)),
                 ("L", (bw_ + 5.0, w / 2 + 0.1)), ("L", (bw_ * 0.4, w / 2 + 0.05)), ("Z",)], "trim")
        if style in ("dress", "casual", "western"):
            dr.part(_rr(bw_ + 1.6, -w / 2 - 0.2, bw_ + 2.6, w / 2 + 0.2, 0.2), "band")   # the keeper
        y0, y1 = -w / 2 - 0.45 * bk, w / 2 + 0.45 * bk
        if style == "western":
            dr.part(_ellipse(0, 0, bw_, (y1 - y0) / 2 + 0.6), "inlay", metal)
            dr.part(_ellipse(0, 0, bw_ * 0.62, (y1 - y0) / 2 - 0.4), "edge")
        else:
            x0, x1, t = -bw_ / 2, bw_ / 2, 0.42 * bk
            dr.part(_rr(x0, y0, x1, y1, 0.35) + _rr(x0 + t, y0 + t, x1 - t, y1 - t, 0.15, reverse=True), "inlay", metal)
            if style not in ("web", "elastic"):
                dr.part(_rr(x0 + t * 0.6, -0.16, x1 - t * 0.2, 0.16, 0.1), "inlay", metal)
        _belt_surface(dr, style, [(-half + 0.3, half - 0.3, 0.0)], w)
        return _finish(dr, kw.get("px"))
    # laid flat, folded in half: the buckle end along the top, round the fold, the tip back along the bottom
    L, g = 15.0, 0.6
    tip = -L + 4.0
    outline = [("M", (-L, -g - w)), ("L", (L, -g - w)), ("C", (L + (w + g) * 1.33, -g - w), (L + (w + g) * 1.33, g + w), (L, g + w)),
               ("L", (tip + 1.6, g + w))]
    if style in ("web", "elastic"):
        outline += [("L", (tip, g + w)), ("L", (tip, g))]
    else:
        outline += [("L", (tip - 0.6, g + w / 2)), ("L", (tip + 1.6, g))]
    outline += [("L", (L, g)), ("Q", (L + g * 1.4, 0), (L, -g)), ("L", (-L, -g)), ("Z",)]
    dr = _Draft(outline, anchor="buckle")
    yc = -g - w / 2
    bx0, bx1 = -L - 3.2 * bk, -L + 0.6
    y0, y1 = yc - w / 2 - 0.55 * bk, yc + w / 2 + 0.55 * bk
    if style == "western":
        dr.part(_ellipse((bx0 + bx1) / 2 - 0.6, yc, (bx1 - bx0) / 2 + 1.0, (y1 - y0) / 2 + 0.6), "inlay", metal)
        dr.part(_ellipse((bx0 + bx1) / 2 - 0.6, yc, (bx1 - bx0) / 2 - 0.2, (y1 - y0) / 2 - 0.6), "edge")
    else:
        t = 0.45 * bk
        dr.part(_rr(bx0, y0, bx1, y1, 0.4) + _rr(bx0 + t, y0 + t, bx1 - t, y1 - t, 0.2, reverse=True), "inlay", metal)
        if style not in ("web", "elastic"):
            dr.part(_rr(bx0 + t * 0.5, yc - 0.17, bx1 + 1.0, yc + 0.17, 0.1), "inlay", metal)   # the prong
    if style in ("dress", "casual", "western"):
        dr.part(_rr(-L + 3.0, -g - w - 0.25, -L + 4.2, -g + 0.25, 0.25), "band")   # the keeper
    if style in ("web", "elastic"):   # a metal tip on the end of the strap
        dr.part([("M", (tip - 0.1, g - 0.05)), ("L", (tip + 2.2, g - 0.05)), ("L", (tip + 2.2, g + w + 0.05)),
                 ("L", (tip - 0.1, g + w + 0.05)), ("Z",)], "inlay", metal)
    if holes:
        for i in range(5):
            dr.dots.append((tip + 5.0 + i * 2.6, g + w / 2, 0.24 if style != "western" else 0.3))
    _belt_surface(dr, style, [(-L + 0.5, L, yc), (tip + 2.4 if style in ("web", "elastic") else tip + 1.0, L, g + w / 2)], w)
    return _finish(dr, kw.get("px"))


def _belt_surface(dr: _Draft, style: str, runs, w):
    """Stitching, tooling or the weave along each straight run of strap, (x from, x to, middle y)."""
    for x0, x1, y in runs:
        if style in ("casual", "western", "dress"):
            inset = 0.45 if style != "dress" else 0.35
            dr.line((x0, y - w / 2 + inset), (x1, y - w / 2 + inset))
            dr.line((x0, y + w / 2 - inset), (x1, y + w / 2 - inset))
        if style == "western":   # tooled scrolls down the middle
            x = x0 + 1.5
            while x < x1 - 2:
                dr.lines.append([("M", (x, y + 0.6)), ("Q", (x + 0.8, y - 1.2), (x + 1.6, y)), ("Q", (x + 2.2, y + 0.9), (x + 2.8, y - 0.4))])
                x += 3.6
        elif style == "braided":   # strands crossing in chevrons
            x = x0
            while x < x1 - 1.4:
                dr.line((x, y - w / 2), (x + 1.4, y))
                dr.line((x, y + w / 2), (x + 1.4, y))
                x += 1.4
        elif style == "web":   # the weave runs along the strap
            for f in (-0.25, 0.25):
                dr.line((x0, y + f * w), (x1, y + f * w))
        elif style == "elastic":   # a zigzag weave
            pts, x, s = [], x0, -1
            while x < x1:
                pts.append((x, y + s * w * 0.32))
                x += 1.0
                s = -s
            if len(pts) > 1:
                dr.line(*pts)


def scarf(**kw) -> Shape:
    """A scarf as worn round the neck, its two ends hanging in front. style: knit | woven (fringed) | silk |
    bandana | gaiter."""
    style = kw.get("style", "woven")
    if style == "gaiter":
        dr = _Draft([("M", (-9.0, -6.5)), ("Q", (0, -8.0), (9.0, -6.5)), ("C", (9.8, -1), (9.8, 5), (9.6, 9.0)),
                     ("Q", (0, 11.0), (-9.6, 9.0)), ("C", (-9.8, 5), (-9.8, -1), (-9.0, -6.5)), ("Z",)], anchor="neck")
        dr.part([("M", (-9.0, -6.5)), ("Q", (0, -8.0), (9.0, -6.5)), ("Q", (0, -4.4), (-9.0, -6.5)), ("Z",)], "hole")
        for y in (-2.0, 2.0, 5.6):   # it bunches round the neck
            dr.lines.append([("M", (-9.4, y)), ("Q", (-4.5, y + 1.4), (0, y + 0.3)), ("Q", (4.5, y - 0.9), (9.4, y + 0.6))])
        return _finish(dr, kw.get("px"))
    loop = [("M", (-9.5, -2.0)), ("C", (-8.0, -8.5), (8.0, -8.5), (9.5, -2.0))]
    if style == "bandana":   # a square folded into a triangle, tied behind the neck
        dr = _Draft(loop + [("L", (0.6, 19.0)), ("L", (-0.6, 19.0)), ("Z",)], anchor="neck")
        dr.lines.append([("M", (-9.6, -1.4)), ("Q", (0, 3.4), (9.6, -1.4))])
        dr.lines.append([("M", (-6.5, 4.0)), ("L", (-0.4, 16.5))])
        dr.lines.append([("M", (6.5, 4.0)), ("L", (0.4, 16.5))])
        return _finish(dr, kw.get("px"))
    wide = 4.6 if style == "silk" else 6.4
    ll, lr = 54.0, 49.0
    ends = {}
    for s, ln in ((-1, ll), (1, lr)):
        ox, ix = s * 9.5, s * (9.5 - wide)
        ends[s] = (ox, ix, ln)
    oxl, ixl, _ = ends[-1]
    oxr, ixr, _ = ends[1]
    if style == "silk":   # pointed ends
        right_end = [("L", (oxr - 0.6, lr)), ("L", ((oxr + ixr) / 2, lr + 4.0)), ("L", (ixr + 0.4, lr - 1.0))]
        left_end = [("L", (ixl - 0.4, ll - 1.0)), ("L", ((oxl + ixl) / 2, ll + 4.0)), ("L", (oxl + 0.6, ll))]
    else:
        right_end = [("L", (oxr - 0.6, lr)), ("L", (ixr + 0.3, lr))]
        left_end = [("L", (ixl - 0.3, ll)), ("L", (oxl + 0.6, ll))]
    outline = (loop + [("C", (10.0, 15.0), (oxr - 0.2, 35.0), (oxr - 0.6, lr - 0.01))] + right_end[1:]
               + [("C", (ixr + 0.5, 30.0), (ixr + 0.9, 10.0), (4.0, 0.0)),
                  ("C", (3.0, -3.6), (-3.0, -3.6), (-4.0, 0.0)),
                  ("C", (ixl - 0.9, 10.0), (ixl - 0.5, 30.0), (ixl - 0.3, ll - 0.01))] + left_end[1:]
               + [("C", (oxl + 0.2, 35.0), (-10.0, 15.0), (-9.5, -2.0)), ("Z",)])
    dr = _Draft(outline, anchor="neck")
    for s in (-1, 1):   # where the scarf comes round from behind the neck
        dr.lines.append([("M", (s * 9.6, -1.6)), ("Q", (s * 7.0, 1.6), (s * 4.0, 0.3))])
    if style == "knit":   # rib down each end
        for s, (ox, ix, ln) in ends.items():
            for f in (0.2, 0.4, 0.6, 0.8):
                x = ix + (ox - ix) * f
                dr.line((x - s * 0.2, 1.5), (x + s * 0.5, ln + 1))
            dr.line((ox, ln - 3.0), (ix, ln - 3.0))
    elif style == "woven":   # a fringe on each end
        for s, (ox, ix, ln) in ends.items():
            a, b = sorted((ox - s * 0.6, ix + s * 0.3))
            n = int((b - a) / 0.55)
            for i in range(n + 1):
                x = a + i * (b - a) / max(n, 1)
                dr.part([("M", (x, ln)), ("L", (x + 0.1, ln + 3.2))], "edge")
            dr.line((a, ln - 1.4), (b, ln - 1.4))
    return _finish(dr, kw.get("px"))


def bag(**kw) -> Shape:
    """A bag from the front. style: tote | backpack | rucksack | roll_top | messenger | briefcase | duffel | sling |
    belt_bag | pouch."""
    style = kw.get("style", "tote")
    if style == "tote":
        dr = _Draft([("M", (-20.0, 22.0)), ("L", (20.0, 22.0)), ("L", (18.0, 58.0)), ("Q", (18.0, 60.0), (16.0, 60.0)),
                     ("L", (-16.0, 60.0)), ("Q", (-18.0, 60.0), (-18.0, 58.0)), ("Z",)], anchor="hand")
        dr.behind.append((_arch(0, 23.0, 8.0, 0.0, 2.6), "trim", None))
        dr.line((-20, 24.6), (20, 24.6))
        for s in (-1, 1):   # the handles are sewn on down the front
            dr.part([("M", (s * 9.3, 21.6)), ("L", (s * 6.7, 21.6)), ("L", (s * 6.7, 29.0)), ("L", (s * 9.3, 29.0)), ("Z",)], "trim")
        return _finish(dr, kw.get("px"))
    if style in ("backpack", "rucksack", "roll_top"):
        if style == "roll_top":
            body = [("M", (-14.5, 14.0)), ("L", (14.5, 14.0)), ("L", (15.0, 56.0)), ("Q", (15.0, 60.0), (11.0, 60.0)),
                    ("L", (-11.0, 60.0)), ("Q", (-15.0, 60.0), (-15.0, 56.0)), ("Z",)]
        else:
            body = [("M", (-15.0, 56.0)), ("L", (-15.5, 18.0)), ("C", (-15.5, 9.0), (-9.0, 5.0), (0, 5.0)),
                    ("C", (9.0, 5.0), (15.5, 9.0), (15.5, 18.0)), ("L", (15.0, 56.0)), ("Q", (15.0, 60.0), (11.0, 60.0)),
                    ("L", (-11.0, 60.0)), ("Q", (-15.0, 60.0), (-15.0, 56.0)), ("Z",)]
        dr = _Draft(body, anchor="hand")
        for s in (-1, 1):   # the shoulder straps, behind
            dr.behind.append(([("M", (s * 9.0, 12.0)), ("C", (s * 19.0, 16.0), (s * 19.0, 40.0), (s * 17.0, 56.0)),
                               ("L", (s * 14.0, 55.0)), ("C", (s * 15.5, 40.0), (s * 15.0, 20.0), (s * 6.0, 13.0)), ("Z",)], "trim", None))
        if style == "roll_top":
            dr.part(_rr(-15.6, 6.5, 15.6, 15.0, 3.5), "trim")
            dr.line((-15.0, 10.8), (15.0, 10.8))
            dr.part(_rr(-1.4, 13.0, 1.4, 26.0, 0.5), "band")
            dr.part(_rr(-2.0, 20.0, 2.0, 24.0, 0.6), "inlay", BUCKLE["matte_black"])
            dr.anchor = "hand"
            dr.behind.append(([("M", (-1.0, 6.6)), ("L", (-1.0, 1.0)), ("L", (1.0, 1.0)), ("L", (1.0, 6.6)), ("Z",)], "trim", None))
        else:
            dr.behind.append((_arch(0, 6.0, 3.2, 0.0, 1.6), "trim", None))   # the grab handle
            if style == "rucksack":   # a flap over the top, held by two straps
                dr.part([("M", (-15.3, 18.0)), ("C", (-15.4, 9.0), (-9.0, 4.6), (0, 4.6)), ("C", (9.0, 4.6), (15.4, 9.0), (15.3, 18.0)),
                         ("L", (15.2, 27.0)), ("Q", (15.0, 31.0), (11.0, 31.0)), ("L", (-11.0, 31.0)), ("Q", (-15.0, 31.0), (-15.2, 27.0)),
                         ("Z",)])
                for x in (-7.0, 7.0):
                    dr.part(_rr(x - 1.2, 24.0, x + 1.2, 44.0, 0.4), "band")
                    dr.part(_rr(x - 1.7, 36.0, x + 1.7, 39.0, 0.4), "inlay", BUCKLE["brass"])
            else:   # a zip round the top and a zipped pocket on the front
                dr.lines.append([("M", (-14.0, 30.0)), ("L", (-14.2, 18.0)), ("C", (-14.2, 10.0), (-8.5, 6.6), (0, 6.6)),
                                 ("C", (8.5, 6.6), (14.2, 10.0), (14.2, 18.0)), ("L", (14.0, 30.0))])
                dr.part(_rr(-11.5, 33.0, 11.5, 55.0, 4.0))
                dr.line((-10.0, 36.0), (10.0, 36.0))
                dr.part(_rr(5.2, 36.0, 6.8, 40.5, 0.5), "inlay", BUCKLE["gunmetal"])
                dr.part(_rr(-13.0, 26.0, -11.4, 30.5, 0.5), "inlay", BUCKLE["gunmetal"])
        return _finish(dr, kw.get("px"))
    if style == "messenger":
        dr = _Draft(_rr(-19.0, 14.0, 19.0, 44.0, 2.5), anchor="hand")
        dr.behind.append((_arch(0, 16.0, 17.0, 0.0, 3.6), "trim", None))
        dr.part([("M", (-19.2, 16.0)), ("Q", (-19.2, 13.6), (-16.5, 13.6)), ("L", (16.5, 13.6)), ("Q", (19.2, 13.6), (19.2, 16.0)),
                 ("L", (19.2, 33.0)), ("Q", (19.2, 37.0), (15.0, 37.0)), ("L", (-15.0, 37.0)), ("Q", (-19.2, 37.0), (-19.2, 33.0)), ("Z",)])
        for x in (-9.0, 9.0):
            dr.part(_rr(x - 1.3, 28.0, x + 1.3, 41.0, 0.4), "band")
            dr.part(_rr(x - 1.8, 34.5, x + 1.8, 37.5, 0.4), "inlay", BUCKLE["brass"])
        return _finish(dr, kw.get("px"))
    if style == "briefcase":
        dr = _Draft(_rr(-20.0, 10.0, 20.0, 40.0, 1.6), anchor="hand")
        dr.behind.append((_arch(0, 10.5, 5.0, 3.0, 1.6), "trim", None))
        for s in (-1, 1):
            dr.part(_rr(s * 5.0 - 1.0, 9.0, s * 5.0 + 1.0, 11.0, 0.4), "inlay", BUCKLE["brass"])
        dr.line((-20.0, 17.0), (20.0, 17.0))
        dr.part(_rr(-2.2, 15.6, 2.2, 19.6, 0.6), "inlay", BUCKLE["brass"])
        return _finish(dr, kw.get("px"))
    if style == "duffel":
        dr = _Draft([("M", (-23.0, 12.0)), ("L", (23.0, 12.0)), ("C", (30.5, 12.0), (30.5, 40.0), (23.0, 40.0)),
                     ("L", (-23.0, 40.0)), ("C", (-30.5, 40.0), (-30.5, 12.0), (-23.0, 12.0)), ("Z",)], anchor="hand")
        dr.behind.append((_arch(0, 14.0, 7.0, 0.0, 2.4), "trim", None))
        for s in (-1, 1):   # the round ends, and the handles sewn down the sides
            dr.lines.append([("M", (s * 23.0, 12.2)), ("C", (s * 17.5, 14.0), (s * 17.5, 38.0), (s * 23.0, 39.8))])
            dr.part([("M", (s * 8.2, 13.6)), ("L", (s * 5.8, 13.6)), ("L", (s * 5.8, 40.2)), ("L", (s * 8.2, 40.2)), ("Z",)], "trim")
        dr.line((-17.0, 15.0), (17.0, 15.0))
        return _finish(dr, kw.get("px"))
    if style == "sling":
        dr = _Draft([("M", (-12.0, 20.0)), ("Q", (0, 15.0), (12.0, 20.0)), ("C", (14.5, 24.0), (14.0, 34.0), (9.0, 35.0)),
                     ("Q", (0, 36.5), (-9.0, 35.0)), ("C", (-14.0, 34.0), (-14.5, 24.0), (-12.0, 20.0)), ("Z",)], anchor="hand")
        dr.behind.append((_arch(0, 22.0, 8.0, 0.0, 2.4), "trim", None))
        dr.lines.append([("M", (-11.0, 23.5)), ("Q", (0, 19.0), (11.0, 23.5))])
        dr.part(_rr(7.6, 21.6, 9.0, 25.6, 0.5), "inlay", BUCKLE["gunmetal"])
        return _finish(dr, kw.get("px"))
    if style == "belt_bag":
        dr = _Draft([("M", (-15.0, 3.0)), ("Q", (0, 0.0), (15.0, 3.0)), ("C", (16.0, 8.0), (14.0, 15.0), (8.0, 16.0)),
                     ("Q", (0, 17.0), (-8.0, 16.0)), ("C", (-14.0, 15.0), (-16.0, 8.0), (-15.0, 3.0)), ("Z",)], anchor="hand")
        for s in (-1, 1):   # the strap out to each side
            dr.behind.append(([("M", (s * 14.0, 5.0)), ("L", (s * 27.0, 3.6)), ("L", (s * 27.0, 7.4)), ("L", (s * 14.0, 8.6)), ("Z",)], "trim", None))
        dr.part(_rr(-25.5, 3.0, -21.5, 8.0, 0.6), "inlay", BUCKLE["matte_black"])
        dr.lines.append([("M", (-13.5, 6.0)), ("Q", (0, 3.0), (13.5, 6.0))])
        dr.part(_rr(9.0, 4.4, 10.4, 8.4, 0.5), "inlay", BUCKLE["gunmetal"])
        return _finish(dr, kw.get("px"))
    # a pouch: a small zipped case with a loop on one end
    dr = _Draft(_rr(-13.0, 4.0, 13.0, 18.0, 3.0), anchor="hand")
    dr.behind.append(([("M", (12.0, 6.5)), ("L", (16.0, 6.5)), ("Q", (17.5, 9.5), (16.0, 12.5)), ("L", (12.0, 12.5)), ("L", (12.0, 11.0)),
                       ("L", (15.0, 11.0)), ("Q", (15.8, 9.5), (15.0, 8.0)), ("L", (12.0, 8.0)), ("Z",)], "trim", None))
    dr.line((-12.0, 6.6), (12.0, 6.6))
    dr.part(_rr(-9.5, 6.0, -8.0, 10.0, 0.5), "inlay", BUCKLE["gunmetal"])
    return _finish(dr, kw.get("px"))


def accessory(**kw) -> Shape:
    """A plain tag, standing in for an accessory with no shape of its own yet (a tie, gloves, glasses ...)."""
    dr = _Draft([("M", (-4.0, -8.0)), ("L", (4.0, -8.0)), ("L", (8.0, -3.5)), ("L", (8.0, 11.0)), ("Q", (8.0, 12.0), (7.0, 12.0)),
                 ("L", (-7.0, 12.0)), ("Q", (-8.0, 12.0), (-8.0, 11.0)), ("L", (-8.0, -3.5)), ("Z",)], anchor="tag")
    dr.part(_ellipse(0, -4.6, 1.1, 1.1), "hole")
    dr.part([("M", (0, -5.6)), ("C", (-2.5, -11.0), (3.5, -13.0), (5.5, -9.5)), ("C", (7.5, -6.0), (3.0, -4.0), (0.8, -4.8))], "edge")
    for y in (2.0, 4.6, 7.2):
        dr.line((-5.0, y), (5.0 if y < 7 else 1.5, y))
    return _finish(dr, kw.get("px"))


TEMPLATES = {"top": top, "pants": pants, "sneaker": sneaker, "cap": cap, "beanie": beanie, "brimmed_hat": brimmed_hat,
             "belt": belt, "scarf": scarf, "bag": bag, "accessory": accessory}


def build(template: str, params: dict) -> Shape:
    return TEMPLATES[template](**params)
