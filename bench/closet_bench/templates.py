"""Parametric garment shapes.

Each template turns a handful of coarse parameters (the same small vocabulary
the attributes use) into geometry on a shared 400 x 460 canvas. Because the
shape is a pure function of the attributes, redrawing after a correction is
free and deterministic, and every item of a category shares anchor points
(shoulders, waist, hem) that the mannequin view can line up later.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

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


def _f(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def _pt(p) -> str:
    return f"{_f(p[0])},{_f(p[1])}"


def _mirror(p):
    return (2 * CX - p[0], p[1])


# --------------------------------------------------------------------- tops

TOP_DEFAULTS = dict(
    sleeve="long",      # none | short | long
    neck="crew",        # crew | v | collar | hood | turtle
    length="regular",   # cropped | regular | long
    fit="regular",      # slim | regular | oversized
    front="none",       # none | buttons | half | zip | quarter-zip
    pockets="none",     # none | chest | chest-two | low | chest-low | kangaroo
    hem="straight",     # straight | curved | rib
    cuffs="plain",      # plain | rib | button
    buttons=None,       # how many buttons show on the front; None = the usual number for this front
    neck_detail="none",  # none | v-insert (the stitched triangle under a sweatshirt's collar)
    shoulder="set-in",  # set-in | raglan (seams run from the neck to the underarm)
)


def _cubic_x_at_y(p0, p1, p2, p3, y: float) -> float:
    """x of a downward-running cubic bezier at height y."""
    lo, hi = 0.0, 1.0
    for _ in range(40):
        t = (lo + hi) / 2
        yy = (1 - t) ** 3 * p0[1] + 3 * (1 - t) ** 2 * t * p1[1] + 3 * (1 - t) * t * t * p2[1] + t ** 3 * p3[1]
        lo, hi = (t, hi) if yy < y else (lo, t)
    t = (lo + hi) / 2
    return (1 - t) ** 3 * p0[0] + 3 * (1 - t) ** 2 * t * p1[0] + 3 * (1 - t) * t * t * p2[0] + t ** 3 * p3[0]


def top(**kw) -> Shape:
    """A top, front view. Proportions are measured from flat reference drawings of real
    shirts (see docs/DECISIONS.md), normalised to the shoulder width."""
    p = {**TOP_DEFAULTS, **kw}
    fit = p["fit"]
    hs = {"slim": 80, "regular": 88, "oversized": 102}[fit]   # half shoulder
    hh = {"slim": 72, "regular": 82, "oversized": 98}[fit]    # half hem
    hy = {"cropped": 296, "regular": 344, "long": 388}[p["length"]]
    sy = 84.0 if fit == "oversized" else 80.0
    sleeved = p["sleeve"] != "none"
    if sleeved:
        # The underarm sits about half a shoulder width below the shoulder and well inside
        # it, so sleeves taper to the wrist and the body widens slightly to the hem.
        ha = hs - 13.0
        ay = sy + {"slim": 84, "regular": 89, "oversized": 96}[fit]
    else:
        ha, ay = hs - 4.0, sy + 74.0
    collar = p["neck"] == "collar"
    nw, ny = (40.0, sy - 15.0) if collar else (30.0, 58.0)   # where the neckline meets the shoulder

    N = (CX + nw, ny)
    S = (CX + hs, sy)
    A = (CX + ha, ay)
    curved = p["hem"] == "curved"
    side_y = hy - (20 if curved else 0)
    Hc = (CX + hh, side_y)
    Sl, Al, Hl, Nl = _mirror(S), _mirror(A), _mirror(Hc), _mirror(N)

    # ---- sleeves
    cuff = None
    seam = None   # the armhole seam: shoulder point, two control points, where it turns vertical
    if not sleeved:
        # a tank: narrow straps and a deep scooped armhole, not a tee with the sleeves cut off
        S = (N[0] + 26, ny + 9)
        A = (CX + hs - 8, sy + 84)
        Sl, Al = _mirror(S), _mirror(A)
        c1, c2 = (S[0] + 2, S[1] + 52), (A[0] - 24, A[1] - 6)
        arm = f"C {_pt(c1)} {_pt(c2)} {_pt(A)}"
        arm_l = f"L {_pt(Al)} C {_pt(_mirror(c2))} {_pt(_mirror(c1))} {_pt(Sl)}"
    else:
        if p["sleeve"] == "long":
            th, ln = math.radians(18), 252.0
            cw = {"slim": 31, "regular": 35, "oversized": 38}[fit]
        else:
            th, ln = math.radians(28 if fit == "oversized" else 24), {"slim": 88.0, "regular": 93.0, "oversized": 102.0}[fit]
            cw = {"slim": 54, "regular": 60, "oversized": 66}[fit]
        d = (math.sin(th), math.cos(th))          # down the sleeve
        q = (-math.cos(th), math.sin(th))         # across it, toward the body
        ul = math.hypot(S[0] - N[0], S[1] - N[1])
        u = ((S[0] - N[0]) / ul, (S[1] - N[1]) / ul)
        r = 12 if p["sleeve"] == "short" else 9   # the shoulder corner is rounded off
        K = (S[0] + u[0] * r, S[1] + u[1] * r)
        P1 = (K[0] + d[0] * r, K[1] + d[1] * r)
        Co = (K[0] + d[0] * ln, K[1] + d[1] * ln)
        if p["sleeve"] == "short":                # the sleeve hem must end outside the body
            cw = min(cw, (Co[0] - A[0] - 9) / math.cos(th))
        Ci = (Co[0] + q[0] * cw, Co[1] + q[1] * cw)
        cuff = (Co, Ci, d)
        arm = f"Q {_pt(K)} {_pt(P1)} L {_pt(Co)} L {_pt(Ci)} L {_pt(A)}"
        arm_l = (f"L {_pt(Al)} L {_pt(_mirror(Ci))} L {_pt(_mirror(Co))} L {_pt(_mirror(P1))} "
                 f"Q {_pt(_mirror(K))} {_pt(Sl)}")
        seam = (S, (S[0] - 4.5, sy + 17), (A[0], sy + 30), (A[0], sy + 50))

    # ---- outline, clockwise from the right neck point
    hem_dip = 5
    if curved:
        hem = f"C {_pt((CX + hh - 48, side_y + 27))} {_pt((CX - hh + 48, side_y + 27))} {_pt(Hl)}"
        hem_bottom = side_y + 20.25
    else:
        hem = f"Q {_pt((CX, hy + hem_dip))} {_pt(Hl)}"
        hem_bottom = hy + hem_dip / 2
    back_neck_y = ny - 4
    if collar:
        # The collar is one folded band and part of the silhouette: straight up its outer
        # edge from the shoulder, across the fold behind the neck, and down the other side.
        TR, TL = (CX + 32.5, ny - 24.5), (CX - 32.5, ny - 24.5)
        neck = f"L {_pt(TL)} Q {_pt((CX, ny - 37))} {_pt(TR)} L {_pt(N)}"
    else:
        neck = f"Q {_pt((CX, back_neck_y))} {_pt(N)}"
    outline = f"M {_pt(N)} L {_pt(S)} {arm} L {_pt(Hc)} {hem} {arm_l} L {_pt(Nl)} {neck} Z"

    sh = Shape(outline=outline)
    # the same for every neckline and sleeve, so the mannequin view can line items up
    sh.anchors = {"neck": (CX, 58.0), "shoulder_l": (CX - hs, sy), "shoulder_r": (CX + hs, sy), "hem": (CX, hy)}
    sh.body_box = (CX - ha, sy, CX + ha, hy)
    xmax = max(S[0], A[0], Hc[0], cuff[0][0] if cuff else 0)
    top_y = {"hood": ny - 74, "turtle": ny - 34, "collar": ny - 33}.get(p["neck"], ny - 4)
    sh.bbox = (2 * CX - xmax, top_y, xmax, hem_bottom + 2)
    if cuff:
        deg = math.degrees(th)
        s0, s1, s2, s3 = seam
        right_sleeve = (f"M {_pt(S)} Q {_pt(K)} {_pt(P1)} L {_pt(Co)} L {_pt(Ci)} L {_pt(A)} L {_pt(s3)} "
                        f"C {_pt(s2)} {_pt(s1)} {_pt(s0)} Z")
        left_sleeve = (f"M {_pt(Sl)} Q {_pt(_mirror(K))} {_pt(_mirror(P1))} L {_pt(_mirror(Co))} L {_pt(_mirror(Ci))} "
                       f"L {_pt(Al)} L {_pt(_mirror(s3))} C {_pt(_mirror(s2))} {_pt(_mirror(s1))} {_pt(_mirror(s0))} Z")
        sh.sleeves = [(right_sleeve, -deg), (left_sleeve, deg)]

    # ---- neckline
    front_bottom = ny
    if p["neck"] in ("crew", "hood"):
        dip = 24 if sleeved else 36
        front_bottom = ny + dip
        sh.parts.append(Part(
            f"M {_pt(Nl)} Q {_pt((CX, back_neck_y))} {_pt(N)} Q {_pt((CX, ny + dip * 2))} {_pt(Nl)} Z", "hole"))
        rib = f"M {_pt((Nl[0] - 5, ny + 4))} Q {_pt((CX, ny + dip * 2 + 16))} {_pt((N[0] + 5, ny + 4))}"
        sh.parts.append(Part(f"{rib} L {_pt(N)} Q {_pt((CX, ny + dip * 2))} {_pt(Nl)} Z", "neckrib"))
        sh.lines.append(rib)
        if p["neck_detail"] == "v-insert" and p["front"] == "none":
            ry = ny + 4 + (dip * 2 + 12) * 0.451   # the rib's lower edge, 11 either side of centre
            sh.parts.append(Part(f"M {_pt((CX - 11, ry))} Q {_pt((CX, ry + 4.5))} {_pt((CX + 11, ry))} "
                                 f"L {_pt((CX, ry + 21))} Z", "trim"))
    elif p["neck"] == "v":
        front_bottom = ny + 58
        sh.parts.append(Part(
            f"M {_pt(Nl)} Q {_pt((CX, back_neck_y))} {_pt(N)} L {_pt((CX, front_bottom))} Z", "hole"))
        sh.lines.append(f"M {_pt((Nl[0] - 6, ny + 3))} L {_pt((CX, front_bottom + 10))} L {_pt((N[0] + 6, ny + 3))}")
    elif collar:
        # Seen from the front: a wide U-shaped opening showing the inside of the back of
        # the shirt, with the collar band running across it; below, the two leaves fold
        # down and meet at the centre in an X, each ending in a point. On a button-front
        # shirt the collar stand shows under the meeting point and carries the top button.
        soft = p["front"] != "buttons"                 # a polo's knit collar: shorter, blunter leaves
        C0 = (CX, ny + 14.5)                           # where the leaves meet
        tip = (CX + 27, ny + 33) if soft else (CX + 25, ny + 37.5)
        a, c1, c2, b = (CX + 27, ny - 12.5), (CX + 30, ny - 16.5), (CX + 29.5, ny - 23.5), (CX + 20, ny - 25.5)
        ml = _mirror
        rim = (f"M {_pt(C0)} L {_pt(ml(a))} C {_pt(ml(c1))} {_pt(ml(c2))} {_pt(ml(b))} Q {_pt((CX, ny - 28.4))} {_pt(b)} "
               f"C {_pt(c2)} {_pt(c1)} {_pt(a)} Z")
        sh.parts.append(Part(rim, "hole"))
        sh.parts.append(Part(f"M {_pt((CX - 27.5, ny - 14))} Q {_pt((CX, ny - 16.5))} {_pt((CX + 27.5, ny - 14))}", "edge"))
        for side, m in (("r", lambda v: v), ("l", _mirror)):
            leaf = (f"M {_pt((CX, ny - 30.75))} Q {_pt(m((CX + 16.25, ny - 30.75)))} {_pt(m(TR))} L {_pt(m(N))} "
                    f"L {_pt(m(tip))} L {_pt(C0)} L {_pt(m(a))} C {_pt(m(c1))} {_pt(m(c2))} {_pt(m(b))} "
                    f"Q {_pt(m((CX + 10, ny - 26.95)))} {_pt((CX, ny - 26.95))} Z")
            sh.parts.append(Part(leaf, f"collar_{side}"))
        # every visible collar edge in one stroke, so nothing is drawn twice
        sh.parts.append(Part(f"M {_pt(Nl)} L {_pt(_mirror(tip))} L {_pt(C0)} L {_pt(tip)} L {_pt(N)} {rim}", "edge"))
        front_bottom = C0[1]
        if not soft:
            stand_y = ny + 26.5
            sx = (tip[0] - CX) * (stand_y - C0[1]) / (tip[1] - C0[1]) - 0.6   # ends on the leaves' front edges
            sh.parts.append(Part(f"M {_pt((CX - sx, stand_y))} Q {_pt((CX, stand_y + 1.5))} {_pt((CX + sx, stand_y))}", "edge"))
            front_bottom = stand_y
            # yoke seams: near-parallel to the shoulder, from under the leaf to the armhole
            yoke_y = sy + 14.5
            for m in ((lambda v: v, _mirror) if seam else ()):
                yoke_x = _cubic_x_at_y(*seam, yoke_y)
                sh.seams.append(f"M {_pt(m((CX + 32, ny + 12)))} L {_pt(m((yoke_x, yoke_y)))}")
    elif p["neck"] == "turtle":
        front_bottom = ny + 6
        tube = (f"M {_pt((Nl[0] - 3, ny + 6))} L {_pt((Nl[0] + 3, ny - 30))} Q {_pt((CX, ny - 37))} {_pt((N[0] - 3, ny - 30))} "
                f"L {_pt((N[0] + 3, ny + 6))} Q {_pt((CX, ny + 20))} {_pt((Nl[0] - 3, ny + 6))} Z")
        sh.parts.append(Part(tube, "band"))
        sh.lines.append(f"M {_pt((Nl[0] + 1, ny - 12))} Q {_pt((CX, ny - 4))} {_pt((N[0] - 1, ny - 12))}")
    if p["neck"] == "hood":
        hood = (f"M {_pt((Nl[0] - 14, ny + 8))} C {_pt((CX - 70, ny - 60))} {_pt((CX - 38, ny - 84))} {_pt((CX, ny - 84))} "
                f"C {_pt((CX + 38, ny - 84))} {_pt((CX + 70, ny - 60))} {_pt((N[0] + 14, ny + 8))} Z")
        sh.behind.append(Part(hood, "trim"))
        sh.lines.append(f"M {_pt((CX - 9, front_bottom + 4))} L {_pt((CX - 11, front_bottom + 52))}")
        sh.lines.append(f"M {_pt((CX + 9, front_bottom + 4))} L {_pt((CX + 11, front_bottom + 52))}")

    # ---- armhole seams: from the shoulder, curving in, then straight down into the side seam
    if seam and p["shoulder"] == "raglan" and not collar:
        for m in (lambda v: v, _mirror):
            sh.seams.append(f"M {_pt(m((N[0] + 4, ny + 2)))} Q {_pt(m(((N[0] + A[0]) / 2 + 9, (ny + ay) / 2 - 8)))} {_pt(m(A))}")
    elif seam:
        s0, s1, s2, s3 = seam
        for m in (lambda v: v, _mirror):
            sh.seams.append(f"M {_pt(m(s0))} C {_pt(m(s1))} {_pt(m(s2))} {_pt(m(s3))} L {_pt(m(A))}")

    # ---- cuffs
    if cuff and p["cuffs"] in ("rib", "button"):
        Co, Ci, d = cuff
        depth = 17 if p["cuffs"] == "rib" else 22
        Bo = (Co[0] - d[0] * depth, Co[1] - d[1] * depth)
        Bi = (Ci[0] - d[0] * depth, Ci[1] - d[1] * depth)
        for m in (lambda v: v, _mirror):
            band = [m(Co), m(Ci), m(Bi), m(Bo)]
            sh.parts.append(Part("M " + " L ".join(_pt(v) for v in band) + " Z", "band" if p["cuffs"] == "rib" else "cuff"))
            if p["cuffs"] == "button":   # the button sits in the middle of the cuff's depth, clear of its edges
                mid = (Ci[0] + (Co[0] - Ci[0]) * 0.34 - d[0] * depth / 2, Ci[1] + (Co[1] - Ci[1]) * 0.34 - d[1] * depth / 2)
                sh.dots.append((*m(mid), 2.6))
    elif cuff and p["sleeve"] == "short":
        Co, Ci, d = cuff
        Bo = (Co[0] - d[0] * 10.5, Co[1] - d[1] * 10.5)
        Bi = (Ci[0] - d[0] * 10.5, Ci[1] - d[1] * 10.5)
        for m in (lambda v: v, _mirror):
            sh.lines.append(f"M {_pt(m(Bo))} L {_pt(m(Bi))}")

    # ---- hem
    if p["hem"] == "rib":
        b = 18
        sh.parts.append(Part(
            f"M {_pt((CX + hh, hy - b))} L {_pt(Hc)} Q {_pt((CX, hy + hem_dip))} {_pt(Hl)} "
            f"L {_pt((CX - hh, hy - b))} Q {_pt((CX, hy - b + hem_dip))} {_pt((CX + hh, hy - b))} Z", "band"))
    elif p["hem"] == "straight":
        sh.lines.append(f"M {_pt((CX - hh + 1, hy - 9))} Q {_pt((CX, hy - 4))} {_pt((CX + hh - 1, hy - 9))}")

    # ---- front opening. These are seams: the collar lies over the top of them.
    bottom = hem_bottom + 2
    count = p["buttons"] if p["buttons"] is None else max(0, int(p["buttons"]))
    if p["front"] == "buttons":
        top_y = front_bottom + (1.3 if collar else 2)   # just under the curve of the stand seam
        sh.seams.append(f"M {_pt((CX - 7, top_y))} L {_pt((CX - 7, bottom))}")
        sh.seams.append(f"M {_pt((CX + 7, top_y))} L {_pt((CX + 7, bottom))}")
        first = front_bottom + (36 if collar else 16)
        last = hy - (42 if curved else 30)
        if count is None:
            n = max(2, round((last - first) / 44) + 1)
        else:   # the count the tagger saw, including the one on the collar stand
            n = max(1, min(10, count - (1 if collar else 0)))
        if collar and count != 0:
            sh.dots.append((CX, front_bottom - 5.2, 3.4))   # the top button, on the collar stand
        if count != 0:
            for i in range(n):
                sh.dots.append((CX, first + (last - first) * (i / (n - 1) if n > 1 else 0.5), 3.4))
    elif p["front"] == "half":
        # a polo or henley placket: as long as its buttons need
        n = 2 if count is None else min(5, count)
        top_y = front_bottom if collar else front_bottom + 2
        first, step = top_y + (17 if collar else 13), 22
        end = first + step * max(n - 1, 0) + (14 if n else 26)
        sh.seams.append(f"M {_pt((CX - 7, top_y))} L {_pt((CX - 7, end))} L {_pt((CX + 7, end))} L {_pt((CX + 7, top_y))}")
        for i in range(n):
            sh.dots.append((CX, first + step * i, 3.0))
    elif p["front"] in ("zip", "quarter-zip"):
        end = bottom if p["front"] == "zip" else front_bottom + 78
        sh.seams.append(f"M {_pt((CX, front_bottom))} L {_pt((CX, end))}")
        sh.lines.append(f"M {_pt((CX - 4, front_bottom + 6))} L {_pt((CX - 4, front_bottom + 20))} "
                        f"L {_pt((CX + 4, front_bottom + 20))} L {_pt((CX + 4, front_bottom + 6))}")
        if p["front"] == "quarter-zip":
            sh.lines.append(f"M {_pt((CX - 5, end))} L {_pt((CX + 5, end))}")

    # ---- pockets
    def patch(x, y, w, h, flap=True):
        sh.lines.append(f"M {_pt((x, y))} L {_pt((x, y + h - 6))} Q {_pt((x, y + h))} {_pt((x + 6, y + h))} "
                        f"L {_pt((x + w - 6, y + h))} Q {_pt((x + w, y + h))} {_pt((x + w, y + h - 6))} L {_pt((x + w, y))} Z")
        if flap:
            sh.lines.append(f"M {_pt((x, y + 13))} L {_pt((x + w / 2, y + 19))} L {_pt((x + w, y + 13))}")
        else:   # a plain patch pocket: just the stitched hem across its top
            sh.lines.append(f"M {_pt((x, y + 6))} L {_pt((x + w, y + 6))}")

    chest_y = sy + 72
    if p["pockets"] == "chest":
        patch(CX + 21, chest_y, 38, 44, flap=False)
    elif p["pockets"] in ("chest-low", "chest-two"):
        patch(CX + 21, chest_y, 38, 44)
        patch(CX - 59, chest_y, 38, 44)
    if p["pockets"] == "kangaroo":   # a hoodie's pouch: slanted openings either side
        y1 = hy - (18 if p["hem"] == "rib" else 8)
        y0, wt, wb = y1 - 76, 36.0, min(54.0, hh - 22)
        sh.lines.append(f"M {_pt((CX - wt, y0))} L {_pt((CX + wt, y0))} L {_pt((CX + wb, y0 + 40))} L {_pt((CX + wb, y1))} "
                        f"M {_pt((CX - wt, y0))} L {_pt((CX - wb, y0 + 40))} L {_pt((CX - wb, y1))}")
    if p["pockets"] in ("low", "chest-low"):   # sized from the body so they clear the side seam and the placket
        w = min(50, hh - 24)
        patch(CX + hh - 14 - w, hy - 86, w, 52)
        patch(CX - hh + 14, hy - 86, w, 52)
    return sh


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

    wy = 28.0
    hw = 20.5 * k                                   # half waist
    hh = (25.0 if leg != "wide" else 26.5) * k      # half hip (a 50 cm flat hip; 52-53 for a wide cut)
    cy = wy + 27.0 * k                              # crotch
    band = 4.0 * k if waist == "belt" else 4.6 * k
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

SHOE_STYLES = ("low_sneaker", "high_top", "runner", "slip_on", "loafer", "derby", "oxford", "boot", "chelsea_boot")
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
