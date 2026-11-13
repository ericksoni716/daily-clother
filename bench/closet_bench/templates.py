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

from .taxonomy import SHOE_STYLES  # shared with the tagger (backend/closet/tagger/taxonomy.py)

W, H = 400, 460
CX = 200.0


@dataclass
class Part:
    d: str
    role: str  # trim | hole | sole | band | cuff | collar_r | collar_l | edge (a stroke with no fill) | inlay | stitch
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
    sole_default: str | None = None  # the sole's colour when the photo gives none (leather shoes: dark brown)
    snaps: list[tuple[float, float, float]] = field(default_factory=list)  # press studs: a ring round a cap, not a button
    # worn open: (the edge of the front that lies on top, the viewer's right one, as a run of points from the
    # neck to below the hem; how its buttonholes are cut, "vertical" or "horizontal"). The other front is its
    # mirror image. The renderer builds the two fronts from this and swings them open.
    fronts: tuple[list, str] | None = None


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
GAUGE_BAND = {"extra_fine": 0.8, "fine": 0.9, "medium": 1.0, "chunky": 1.25, "super_chunky": 1.5}

# Shirt collar leaves: where the point lies from the place the leaves meet (dx, dy), and how the point is finished.
LEAVES = {
    "semi_spread": (25, 23, "sharp"), "point": (18, 30, "sharp"), "spread": (30, 16, "sharp"), "cutaway": (33, 8.5, "sharp"),
    "button_down": (21, 27, "roll"), "hidden_button_down": (21, 27, "roll"), "club": (24, 22, "club"),
    "tab": (18, 30, "sharp"), "pin": (19, 29, "sharp"), "western": (23, 37, "sharp"),
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
            out.append((x + outward * amp * math.sin(math.pi * f), y))
    out.append(pts[-1])
    return out


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
        arm = f"Q {_pt(K)} {_pt(P1)} L " + " L ".join(_pt(v) for v in sil)
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
        right_sleeve = (f"M {_pt(S)} Q {_pt(K)} {_pt(P1)} L " + " L ".join(_pt(v) for v in corner) + f" L {_pt(Ci)} L {_pt(A)} "
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
            if cs == "tab":   # a strap joins the points under the tie, buttoned over the top button
                tw = 3.2
                first_leaf = next(i for i, q in enumerate(sh.parts) if q.role == "collar_r")
                sh.parts.insert(first_leaf, Part(_poly([(CX - 14, btn_y - tw), (CX + 14, btn_y - tw), (CX + 14, btn_y + tw),
                                                               (CX - 14, btn_y + tw)]), "cuff"))
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
        if cs == "wing":   # the stand's front tips are pressed out into small wings
            for m, side in sides:
                w = [(CX + 1.2, y_ct - 0.5), (CX + 15, y_ct - 4), (CX + 13, y_ct + 12)]
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
        for m, _ in sides:
            sh.parts.append(Part(_poly([m(v) for v in pts + inner[::-1]]), "band", clip=True))

    # ---- cuffs
    if cuff:
        Co, Ci, d = cuff
        din = _unit((A[0] - Ci[0], A[1] - Ci[1]))   # up the sleeve's inner edge
        long_cuff = sleeve in ("long", "three-quarter") and cuffs not in ("rolled", "roll-tab")
        depth = {"rib": 17 * bs, "button": 22, "button2": 22, "mitred": 22, "french": 28, "snap3": 31}.get(cuffs)
        if cuffs == "rib" and not long_cuff:
            depth = 11 * bs     # a polo's ribbed armband
        if depth and (long_cuff or cuffs == "rib") and cuffs in ("rib", "button", "button2", "mitred", "french", "snap3"):
            depth += bulk if cuffs != "rib" else 0
            Bo = (Co[0] - d[0] * depth, Co[1] - d[1] * depth)
            Bi = (Ci[0] + din[0] * depth, Ci[1] + din[1] * depth)
            at = lambda f, g: (Co[0] + (Ci[0] - Co[0]) * f - d[0] * depth * g, Co[1] + (Ci[1] - Co[1]) * f - d[1] * depth * g)
            for m in (lambda v: v, _mirror):
                band = [m(v) for v in (corner + [Ci, Bi, Bo])]
                sh.parts.append(Part(_poly(band), "band" if cuffs == "rib" else "cuff"))
                if cuffs in ("button", "mitred"):   # the button sits in the middle of the cuff's depth, clear of its edges
                    fasten(*m(at(0.34 if cuffs == "button" else 0.36, 0.5)), 2.6)
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
                sh.parts.append(Part(_poly([m(v) for v in roll]), "cuff"))
                sh.parts.append(Part(_poly([m(mid_o), m(mid_i)], close=False), "edge"))
                if cuffs == "roll-tab":   # the tab that holds the roll up, buttoned on the sleeve
                    tb = (Co[0] + (Ci[0] - Co[0]) * 0.3, Co[1] + (Ci[1] - Co[1]) * 0.3)
                    t0 = (tb[0] - d[0] * (depth - 1), tb[1] - d[1] * (depth - 1))
                    t1 = (tb[0] - d[0] * (depth + 30), tb[1] - d[1] * (depth + 30))
                    tab = [o(t0, -3.5), o(t0, 3.5), o(t1, 3.5), _lerp(o(t1, 0), (t1[0] - d[0] * 4, t1[1] - d[1] * 4), 1), o(t1, -3.5)]
                    sh.parts.append(Part(_poly([m(v) for v in tab]), "cuff"))
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
    if p["hem"] == "rib":
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
        n = (3 if pop else 2) if count is None else min(5, count - (1 if (pop and stand_button and count) else 0))
        n = max(n, 0)
        top_y = front_bottom if collar else front_bottom + 2
        first, step = top_y + (17 if collar else 13), (34 if pop else 22)
        end = first + step * max(n - 1, 0) + (14 if n else 26)
        if pop:
            end = max(end, top_y + 96)
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

    _pockets(sh, p["pockets"], sy, hy, hh, hs, p["hem"], cuff, A, rib_h, lapel_front)
    if state == "open" and front != "none":   # the edge of the front that lies on top, for the renderer to open
        if lapel_front and lapel_front[0] == "cardigan":
            apex = (CX - lapel_front[2] / 2, lapel_front[1])      # the V's point; the button band runs down from it
            sh.fronts = ([N, apex, (apex[0], hy + 20)], "vertical")
        elif lapel_front:                                       # revers or a shawl: the V runs to the break
            sh.fronts = ([N, (CX - lapel_front[2], lapel_front[1]), (CX - lapel_front[2], hy + 20)], "horizontal")
        elif front in ("buttons", "french", "hidden", "double", "zip"):
            x = CX - {"zip": 0, "double": 30}.get(front, 7)     # how far the top front reaches past the centre
            sh.fronts = ([(x, front_bottom), (x, hy + 20)], "horizontal" if front == "double" else "vertical")
    return sh


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
    sh = Shape(outline="")
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
        w_want = (B["bicep"] + dbi) * k_ * ease * 0.78
        cw0 = (B["cuff"] * 0.9 if sleeve == "long" else B["cuff"] + (B["bicep"] - B["cuff"]) * (1 - frac)) * k_ * ease

        def build(th):
            t = math.radians(th)
            d, q = (math.sin(t), math.cos(t)), (-math.cos(t), math.sin(t))   # down the sleeve; across it, toward the body
            Co = (K[0] + d[0] * ln, K[1] + d[1] * ln)
            w_top = abs((A[0] - K[0]) * d[1] - (A[1] - K[1]) * d[0])         # the sleeve's width where it leaves the body
            cw = min(cw0, 0.86 * w_top)                                        # always narrower at the cuff
            return d, q, Co, (Co[0] + q[0] * cw, Co[1] + q[1] * cw), w_top

        # the sleeve swings out until it is as wide as the arm and clear of the body, or reaches the card's edge
        th = 12.0
        while th < 40 and build(th + 0.5)[2][0] <= W - 8:
            d, q, Co, Ci, w_top = build(th)
            if w_top >= w_want and Ci[0] > _x_on(side, Ci[1]) + 5:
                break
            th += 0.5
        while th > 0 and build(th)[2][0] > W - 8:
            th -= 0.5
        d, q, Co, Ci, w_top = build(th)
        P1 = (K[0] + d[0] * r, K[1] + d[1] * r)
        arm = f"Q {_pt(K)} {_pt(P1)} L {_pt(Co)} L {_pt(Ci)} L {_pt(A)}"
        arm_l = f"L {_pt(ml(Ci))} L {_pt(ml(Co))} L {_pt(ml(P1))} Q {_pt(ml(K))} {_pt(ml(S))}"
        s1, s2 = (S[0] - 3, S[1] + (A[1] - S[1]) * 0.35), (A[0] + 4, A[1] - (A[1] - S[1]) * 0.3)
        right_sleeve = (f"M {_pt(S)} Q {_pt(K)} {_pt(P1)} L {_pt(Co)} L {_pt(Ci)} L {_pt(A)} "
                        f"C {_pt(s2)} {_pt(s1)} {_pt(S)} Z")
        sh.sleeves = [(right_sleeve, -th), (_mirror_path(right_sleeve), th)]
        c1, c2 = s1, s2
        if sleeve == "long":   # four small buttons along the vent at each cuff
            br = 1.9 + bulk * 0.1
            for i in range(4):
                b = (Co[0] + q[0] * 5.5 - d[0] * (8 + 5.2 * i), Co[1] + q[1] * 5.5 - d[1] * (8 + 5.2 * i))
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
        rows = max(1, min(4, n_b // 2 or 3))
        sp = T["db_spacing"] * k_
        yf = ny + T["db_stance"] * k_
        above = rows - 2 if rows >= 3 else 0
        ys = [yf + (i - above) * sp for i in range(rows)]
        y_break, ov = yf - 4, 32.0 + bulk
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
    nt = _qbez(N, (N[0], Tt[1] + 2), Tt, 6)          # the collar's edge from the shoulder up behind the neck
    if cs == "shawl":   # one smooth roll from the top button round the neck, no notch
        wsh = 9 * k_ + bulk * 0.6
        y1 = Bk[1] - (Bk[1] - ny) * 0.45
        outer = [Bk] + _bez(Bk, (roll_x(y1) + wsh * 1.05, y1), (N[0] + wsh * 0.4, ny + 30), N, 16)
        pieces = [(outer + nt + [Rt], [Tt, Rt] + outer)]
        edge_pts = outer
    else:
        lw = (T["db_lapel"] if dbl else T["lapel"] + (1.25 if cs == "peak" else 0)) * k_ + bulk * 0.5
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
    if roll3 and edge_x(roll3) - roll_x(roll3) > 10:
        x0 = roll_x(roll3) + 2
        sh.lines.append(f"M {_pt((x0, roll3))} L {_pt((x0 + 6, roll3 - 1))}")
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


def _pockets(sh, kind, sy, hy, hh, hs, hem, cuff, A, rib_h, lapel_front):
    def patch(x, y, w, h, flap=True):
        sh.lines.append(f"M {_pt((x, y))} L {_pt((x, y + h - 6))} Q {_pt((x, y + h))} {_pt((x + 6, y + h))} "
                        f"L {_pt((x + w - 6, y + h))} Q {_pt((x + w, y + h))} {_pt((x + w, y + h - 6))} L {_pt((x + w, y))} Z")
        if flap:
            sh.lines.append(f"M {_pt((x, y + 13))} L {_pt((x + w / 2, y + 19))} L {_pt((x + w, y + 13))}")
        else:   # a plain patch pocket: just the stitched hem across its top
            sh.lines.append(f"M {_pt((x, y + 6))} L {_pt((x + w, y + 6))}")

    def flapped(x, y, w, h, bellows=False, button=True, point=True):
        """A patch pocket under a separate buttoned flap; bellows show their folded sides."""
        fy = y + 12
        sh.lines.append(f"M {_pt((x, fy))} L {_pt((x, y + h - 6))} Q {_pt((x, y + h))} {_pt((x + 6, y + h))} "
                        f"L {_pt((x + w - 6, y + h))} Q {_pt((x + w, y + h))} {_pt((x + w, y + h - 6))} L {_pt((x + w, fy))}")
        if bellows:
            sh.lines.append(f"M {_pt((x + 3.5, fy))} L {_pt((x + 3.5, y + h - 3.5))} L {_pt((x + w - 3.5, y + h - 3.5))} L {_pt((x + w - 3.5, fy))}")
        fl = [(x - 1.5, y - 1), (x + w + 1.5, y - 1), (x + w + 1.5, fy)] + ([(x + w / 2, fy + 5)] if point else []) + [(x - 1.5, fy)]
        sh.parts.append(Part(_poly(fl), "cuff"))
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
#   hem     stitched | plain | turnup | rib  visible topstitch, blind hem, turn-up cuff, knit cuff (joggers)
#   coin    True | False                     jeans' watch pocket and rivets
#   stitch  tonal | contrast                 jeans' topstitch drawn in gold thread as well

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
    stitch = p.get("stitch", "tonal")
    leg, length = p["leg"], p["length"]
    wt = WEIGHT_LEVEL.get(p.get("weight"), 1)   # a heavy cloth: a deeper waistband, a doubled hem

    wy = 28.0
    hw = 20.5 * k                                   # half waist
    hh = (25.0 if leg != "wide" else 26.5) * k      # half hip (a 50 cm flat hip; 52-53 for a wide cut)
    cy = wy + 27.0 * k                              # crotch
    band = (4.0 * k if waist == "belt" else 4.6 * k) + max(0, wt - 1) * 2.5
    bb = wy + band                                  # bottom of the waistband
    hip_y = cy - 18                                 # the widest point, ~4/5 of the way down the rise
    # one leg: its width at the knee and the opening, and where its middle sits at the hem
    kn, op = {"tapered": (19.5, 16.5), "straight": (21.5, 19.5), "wide": (25.5, 25.0)}[leg]
    kn, op = kn * k, op * k
    inseam = {"full": 81.0, "ankle": 71.0, "short": 22.0}[length]
    hy = cy + inseam * k
    knee_y = cy + 33.0 * k
    c0 = CX - hh / 2                                # middle of the leg at the crotch
    if length == "short":
        op = 27.5 * k                               # a shorts leg opening is wider than its thigh: it flares
        hc = CX - 6 - op / 2
        Ho, Hi = (hc - op / 2, hy), (hc + op / 2, hy + 2)
        Ko = Ki = None
    else:
        hc = c0 - max(0.0, op - 19.5 * k) * 0.35    # wide legs move their middle out a little
        Ho, Hi = (hc - op / 2, hy), (hc + op / 2, hy)
        kc = c0 + (hc - c0) * (knee_y - cy) / (hy - cy)
        Ko, Ki = (kc - kn / 2, knee_y), (kc + kn / 2, knee_y)
    rib = hem_kind == "rib" and length != "short"
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
    fly = waist == "belt"
    fly_end = cy - 7.0 * k
    if fly:
        sh.lines.append(f"M {_pt((CX, bb))} L {_pt((CX, cy - 3))}")
        fw = 3.6 * k   # the J-stitch on the wearer's left (viewer's right)
        sh.lines.append(f"M {_pt((CX + fw, bb))} L {_pt((CX + fw, fly_end - 14))} Q {_pt((CX + fw, fly_end))} {_pt((CX, fly_end + 2))}")
        sh.dots.append((CX, wy + band / 2, 3.4))
        # belt loops: two in front over the pocket mouths, one on each side seam
        for x in (CX - 0.45 * hw, CX - hw + 8):
            for mm in (lambda q: q, m):
                a, b = mm((x - 3.2, wy - 2.5)), mm((x + 3.2, bb + 3.5))
                x0, x1 = min(a[0], b[0]), max(a[0], b[0])
                sh.parts.append(Part(f"M {_pt((x0, a[1]))} L {_pt((x1, a[1]))} L {_pt((x1, b[1]))} L {_pt((x0, b[1]))} Z", "trim"))
    else:
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
            if coin:
                sh.dots.append((*mm((mouth_x - 1, bb + 3)), 1.9))
                sh.dots.append((*mm((sm[0] + 4, sm[1] - 2)), 1.9))
        elif pocket == "slant":
            sh.lines.append(f"M {_pt(mm((mouth_x, bb)))} L {_pt(mm(sm))}")
        elif pocket == "side":
            sh.lines.append(f"M {_pt(mm((sm[0] + 4, bb + 4)))} L {_pt(mm((sm[0] + 2, sm[1] + 20)))}")
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
            t = 5.5 * k if length != "short" else 3 * k
            cuff = [(a[0] - 0.5, a[1] - t), (b[0] + 0.5, b[1] - t), (b[0], b[1]), (a[0], a[1])]
            sh.parts.append(Part("M " + " L ".join(_pt(mm(v)) for v in cuff) + " Z", "band"))
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

SHOE_X0, SHOE_L, SHOE_G = 40.0, 320.0, 330.0   # toe tip x, length toe to heel, ground y


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


def sneaker(**kw) -> Shape:
    """A shoe, outer side, toe to the left. Proportions in shoe lengths, from side views of real shoes:
    a low sneaker is ~2.8x as long as it is tall at the collar, a high-top's collar is ~0.53 of its length up."""
    p = {**SNEAKER_DEFAULTS, **kw}
    style = p.get("style") or ("high_top" if p["height"] == "high" else "low_sneaker")
    if style not in SHOE_STYLES:
        style = "low_sneaker"
    f = {"thin": 0.75, "regular": 1.0, "chunky": 1.6}[p["sole"]]
    heeled = style in ("loafer", "derby", "oxford", "boot", "chelsea_boot")
    laced = p.get("laces", style not in ("slip_on", "loafer", "chelsea_boot"))
    foxing = p.get("foxing", style in ("high_top", "slip_on"))
    toe_cap = p.get("toe_cap", "rubber" if style == "high_top" else "none")

    # ---- the sole: where the upper sits on it (sole top, toe -> heel) and its underside
    def sole(f):
        if heeled:
            ts = {"boot": 0.05, "chelsea_boot": 0.035}.get(style, 0.03) * (1 if f <= 1 else 1.4)
            hb = {"boot": 0.06, "chelsea_boot": 0.065}.get(style, 0.07) * (0.8 if f < 1 else 1.0)
            spring = 0.025
            breast = 0.77                                          # front face of the heel
            top = [(0.012, spring + ts * 0.9), (0.08, spring * 0.45 + ts), (0.25, ts + 0.002), (0.48, ts + 0.006),
                   (0.62, ts + hb * 0.55), (0.76, ts + hb * 0.95), (0.993, ts + hb)]
            under = (f"Q {_pt(_sp(-0.006, spring + ts * 0.5))} {_pt(_sp(0.008, spring))} "
                     f"C {_pt(_sp(0.04, spring * 0.4))} {_pt(_sp(0.12, 0))} {_pt(_sp(0.25, 0))} L {_pt(_sp(0.5, 0))} "
                     f"C {_pt(_sp(0.58, 0.004))} {_pt(_sp(0.66, hb * 0.75))} {_pt(_sp(breast - 0.01, hb))} "
                     f"L {_pt(_sp(breast, 0))} L {_pt(_sp(0.985, 0))} Q {_pt(_sp(0.997, 0))} {_pt(_sp(0.997, 0.004))} "
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
            heel_line = ""
        return top, under, heel_line

    top, under, heel_line = sole(f)
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

    front = groups[-1]
    vtop = lambda u: _poly_v(front, u)     # height of the top edge over the vamp / lacing
    tf_at = lambda u: _poly_v(top, u)      # height of the sole top

    # ---- foxing stripe on a vulcanised sole, a welt stitch on a leather one
    if foxing:
        sh.parts.append(Part(_spline([(0.004, tf_at(0.01) * 0.6), (0.3, tf_at(0.3) * 0.5), (0.996, sole_top_heel[1] * 0.5)]),
                             "edge", color="sole_line"))
    if heeled:
        sh.parts.append(Part(_spline([(0.03, tf_at(0.03) - 0.012), (0.3, tf_at(0.3) - 0.012), (0.6, tf_at(0.6) - 0.012),
                                      (0.985, sole_top_heel[1] - 0.012)]), "stitch", color="sole_line"))

    # ---- lacing: eyelets just under the top edge, laces crossing over it
    lace_span = {"low_sneaker": (0.35, 0.585), "high_top": (0.27, 0.62), "runner": (0.37, 0.585), "derby": (0.43, 0.585),
                 "oxford": (0.44, 0.58), "boot": (0.5, 0.64)}.get(style)
    if laced and lace_span:
        a, b = lace_span
        n = {"high_top": 8, "boot": 7, "derby": 5, "oxford": 5, "runner": 6}.get(style, 6)
        drop = 0.036 if not heeled else 0.026
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
        for (u, v) in eyelets:
            ex, ey = _sp(u, v)
            tip = _sp(u - 0.035, vtop(u - 0.035) + 0.03)
            if style == "boot":
                tip = _sp(u - 0.034, v + 0.045)
            sh.parts.append(Part(_capsule((ex, ey), tip, lw), "inlay", color="lace", clip=True))
            sh.dots.append((ex, ey, 2.4 if not heeled else 2.0))

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
        # the moccasin seam round the vamp, and the saddle strap across it
        sh.seams.append(_spline([(0.6, 0.205), (0.48, 0.2), (0.34, 0.178), (0.2, 0.148), (0.1, 0.12), (0.04, 0.09)]))
        strap = (_spline([(0.592, 0.27), (0.588, 0.2), (0.575, 0.158)]) + " " +
                 _spline([(0.575, 0.158), (0.53, 0.146), (0.48, 0.148)], start=False) + " " +
                 _spline([(0.48, 0.148), (0.478, 0.2), (0.482, 0.26)], start=False) + " Z")
        sh.parts.append(Part(strap, "trim", clip=True))
        sh.lines.append(_spline([(0.565, 0.205), (0.535, 0.203), (0.5, 0.198)]))
    if style in ("derby", "oxford"):
        e_lo = (0.465, vtop(0.465))
        if style == "derby":   # quarters stitched on top of the vamp: their front edge runs down and back
            sh.lines.append(_spline([(e_lo[0] - 0.005, e_lo[1] - 0.005), (0.468, 0.17), (0.52, 0.12), (0.58, tf_at(0.58) + 0.01)]))
            sh.lines.append(_spline([(0.47, vtop(0.47) - 0.05), (0.6, vtop(0.6) - 0.055), (0.66, 0.255)]))
        else:                  # closed lacing: the vamp lies over the quarters, its seam sweeps back to the heel
            sh.lines.append(_spline([(e_lo[0] - 0.005, e_lo[1] - 0.005), (0.49, 0.185), (0.56, 0.16), (0.66, 0.15),
                                     (0.72, 0.14), (0.75, tf_at(0.75) + 0.005)]))
        sh.lines.append(_spline([(0.86, tf_at(0.86)), (0.885, 0.17), (0.93, 0.24), (0.945, 0.29)]))
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
        if style != "high_top":
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
    elif toe_cap == "rubber":
        d = (f"M {_pt(_sp(-0.05, 0.0))} L {_pt(_sp(0.17, tf_at(0.17) - 0.01))} "
             + _spline([(0.17, tf_at(0.17) - 0.01), (0.165, 0.15), (0.13, 0.2), (0.11, 0.3)], start=False)
             + f" L {_pt(_sp(-0.05, 0.3))} Z")
        sh.parts.insert(0, Part(d, "inlay", color="sole", clip=True))

    # ---- a contrast side panel
    if p.get("stripe", "none") == "side":
        d = (_spline([(0.42, tf_at(0.42) - 0.01), (0.52, 0.16), (0.6, 0.235), (0.66, 0.285)]) + " "
             + _spline([(0.66, 0.285), (0.7, 0.26), (0.72, 0.22)], start=False) + " "
             + _spline([(0.72, 0.22), (0.66, 0.17), (0.58, tf_at(0.58) - 0.01)], start=False) + " Z")
        sh.parts.append(Part(d, "inlay", color="trim", clip=True))
    return sh


TEMPLATES = {"top": top, "pants": pants, "sneaker": sneaker}


def build(template: str, params: dict) -> Shape:
    return TEMPLATES[template](**params)
