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
    role: str  # trim | hole | sole | band | cuff | collar_r | collar_l | edge (a stroke with no fill)


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
    front="none",       # none | buttons | half | zip
    pockets="none",     # none | chest | low | chest-low
    hem="straight",     # straight | curved | rib
    cuffs="plain",      # plain | rib | button
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
        sh.lines.append(f"M {_pt((Nl[0] - 5, ny + 4))} Q {_pt((CX, ny + dip * 2 + 16))} {_pt((N[0] + 5, ny + 4))}")
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
    if seam:
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
    if p["front"] == "buttons":
        top_y = front_bottom + (1.3 if collar else 2)   # just under the curve of the stand seam
        sh.seams.append(f"M {_pt((CX - 7, top_y))} L {_pt((CX - 7, bottom))}")
        sh.seams.append(f"M {_pt((CX + 7, top_y))} L {_pt((CX + 7, bottom))}")
        if collar:
            sh.dots.append((CX, front_bottom - 5.2, 3.4))   # the top button, on the collar stand
        first = front_bottom + (36 if collar else 16)
        last = hy - (42 if curved else 30)
        n = max(2, round((last - first) / 44) + 1)
        for i in range(n):
            sh.dots.append((CX, first + (last - first) * i / (n - 1), 3.4))
    elif p["front"] == "half":
        top_y = front_bottom if collar else front_bottom + 2
        end = top_y + 60
        sh.seams.append(f"M {_pt((CX - 7, top_y))} L {_pt((CX - 7, end))} L {_pt((CX + 7, end))} L {_pt((CX + 7, top_y))}")
        for i in range(2):
            sh.dots.append((CX, top_y + 17 + 24 * i, 3.0))
    elif p["front"] == "zip":
        sh.seams.append(f"M {_pt((CX, front_bottom))} L {_pt((CX, bottom))}")
        sh.lines.append(f"M {_pt((CX - 4, front_bottom + 6))} L {_pt((CX - 4, front_bottom + 20))} "
                        f"L {_pt((CX + 4, front_bottom + 20))} L {_pt((CX + 4, front_bottom + 6))}")

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
    elif p["pockets"] == "chest-low":
        patch(CX + 21, chest_y, 38, 44)
        patch(CX - 59, chest_y, 38, 44)
    if p["pockets"] in ("low", "chest-low"):   # sized from the body so they clear the side seam and the placket
        w = min(50, hh - 24)
        patch(CX + hh - 14 - w, hy - 86, w, 52)
        patch(CX - hh + 14, hy - 86, w, 52)
    return sh


# -------------------------------------------------------------------- pants

PANTS_DEFAULTS = dict(leg="straight", length="full", jeans=False)


def pants(**kw) -> Shape:
    p = {**PANTS_DEFAULTS, **kw}
    wy, hw, hip_y, hip = 34.0, 74.0, 112.0, 86.0
    cy = 182.0
    hy = {"short": 252.0, "ankle": 408.0, "full": 438.0}[p["length"]]
    hem_w = {"tapered": 42.0, "straight": 58.0, "wide": 84.0}[p["leg"]]
    inset = {"tapered": 8.0, "straight": 0.0, "wide": -10.0}[p["leg"]]
    if p["length"] == "short":
        hem_w, inset = 78.0, -4.0
    xo = CX - hip + inset
    xi = xo + hem_w
    if xi > CX - 4:
        xi = CX - 4
    Wl, Hl = (CX - hw, wy), (CX - hip, hip_y)
    outline = (
        f"M {_pt(Wl)} Q {_pt((CX - hip - 1, wy + 36))} {_pt(Hl)} L {_pt((xo, hy))} L {_pt((xi, hy + 3))} "
        f"L {_pt((CX, cy))} L {_pt(_mirror((xi, hy + 3)))} L {_pt(_mirror((xo, hy)))} L {_pt(_mirror(Hl))} "
        f"Q {_pt((CX + hip + 1, wy + 36))} {_pt(_mirror(Wl))} Q {_pt((CX, wy + 6))} {_pt(Wl)} Z")
    sh = Shape(outline=outline)
    sh.bbox = (min(xo, CX - hip) - 1, wy, 2 * CX - min(xo, CX - hip) + 1, hy + 3)
    sh.body_box = (CX - hip, wy, CX + hip, hy)
    sh.anchors = {"waist": (CX, wy), "hem": (CX, hy)}
    band = 19
    sh.parts.append(Part(
        f"M {_pt(Wl)} Q {_pt((CX, wy + 6))} {_pt(_mirror(Wl))} L {_pt((CX + hw + 3, wy + band))} "
        f"Q {_pt((CX, wy + band + 6))} {_pt((CX - hw - 3, wy + band))} Z", "band"))
    # fly, pockets, hems
    sh.lines.append(f"M {_pt((CX, wy + band + 4))} L {_pt((CX, cy - 4))}")
    sh.lines.append(f"M {_pt((CX + 13, wy + band + 5))} L {_pt((CX + 13, cy - 46))} Q {_pt((CX + 12, cy - 26))} {_pt((CX, cy - 20))}")
    for m in (lambda q: q, _mirror):
        sh.lines.append(f"M {_pt(m((CX - 34, wy + band + 4)))} Q {_pt(m((CX - 40, wy + band + 34)))} {_pt(m((CX - hip + 1, hip_y - 14)))}")
        sh.lines.append(f"M {_pt(m((xo + 1, hy - 10)))} L {_pt(m((xi - 1, hy - 7)))}")
        for bx in (CX - 50, CX - 16):
            sh.lines.append(f"M {_pt(m((bx, wy + 3)))} L {_pt(m((bx, wy + band + 1)))}")
    sh.dots.append((CX + 6, wy + band / 2 + 3, 3.0))
    if p["jeans"]:
        for m in (lambda q: q, _mirror):
            sh.dots.append((*m((CX - 37, wy + band + 9)), 1.8))
        sh.lines.append(f"M {_pt((CX + 46, wy + band + 12))} Q {_pt((CX + 50, wy + band + 32))} {_pt((CX + 64, wy + band + 30))}")
    return sh


# ----------------------------------------------------------------- sneakers

SNEAKER_DEFAULTS = dict(height="low", sole="regular")


def sneaker(**kw) -> Shape:
    p = {**SNEAKER_DEFAULTS, **kw}
    base = 322.0
    t = {"thin": 20.0, "regular": 28.0, "chunky": 42.0}[p["sole"]]
    ys = base - t
    hi = p["height"] == "high"
    heel_top = (338.0, ys - (150 if hi else 88))
    tongue = (236.0, ys - (172 if hi else 112))
    throat_end = (146.0, ys - 50)
    sole = (f"M {_pt((44, ys + 3))} Q {_pt((40, base))} {_pt((66, base))} L {_pt((332, base))} "
            f"Q {_pt((356, base))} {_pt((356, ys + 6))} L {_pt((354, ys))} L {_pt((46, ys))} Z")
    upper = (f"M {_pt((350, ys))} Q {_pt((360, ys - 48))} {_pt(heel_top)} "
             f"Q {_pt((300, ys - (138 if hi else 62)))} {_pt((262, ys - (160 if hi else 98)))} "
             f"L {_pt(tongue)} L {_pt(throat_end)} Q {_pt((84, ys - 46))} {_pt((48, ys - 4))} L {_pt((46, ys))} Z")
    outline = (f"M {_pt((44, ys + 3))} Q {_pt((40, base))} {_pt((66, base))} L {_pt((332, base))} "
               f"Q {_pt((356, base))} {_pt((356, ys + 6))} L {_pt((350, ys))} Q {_pt((360, ys - 48))} {_pt(heel_top)} "
               f"Q {_pt((300, ys - (138 if hi else 62)))} {_pt((262, ys - (160 if hi else 98)))} "
               f"L {_pt(tongue)} L {_pt(throat_end)} Q {_pt((84, ys - 46))} {_pt((48, ys - 4))} Z")
    sh = Shape(outline=outline)
    sh.parts.append(Part(sole, "sole"))
    sh.bbox = (40, tongue[1], 360, base)
    sh.body_box = (46, tongue[1], 356, ys)
    sh.anchors = {"ground": (CX, base)}
    # toe cap, foxing stripe, heel counter, collar, laces
    sh.lines.append(f"M {_pt((122, ys - 50))} Q {_pt((100, ys - 30))} {_pt((104, ys))}")
    sh.lines.append(f"M {_pt((48, ys + t * 0.5))} L {_pt((354, ys + t * 0.5))}")
    sh.lines.append(f"M {_pt((316, ys))} Q {_pt((304, ys - 44))} {_pt((heel_top[0] - 8, heel_top[1] + 14))}")
    sh.lines.append(f"M {_pt((throat_end[0] + 18, throat_end[1] + 20))} Q {_pt((230, ys - 30))} {_pt((262, ys - (160 if hi else 98) + 14))}")
    n = 7 if hi else 5
    for i in range(n):
        f = (i + 0.6) / (n + 0.2)
        x = throat_end[0] + (tongue[0] - throat_end[0]) * f
        y = throat_end[1] + (tongue[1] - throat_end[1]) * f
        sh.lines.append(f"M {_pt((x + 1, y + 2))} L {_pt((x + 15, y + 19))}")
        sh.dots.append((x + 16, y + 21, 2.2))
    return sh


TEMPLATES = {"top": top, "pants": pants, "sneaker": sneaker}


def build(template: str, params: dict) -> Shape:
    return TEMPLATES[template](**params)
