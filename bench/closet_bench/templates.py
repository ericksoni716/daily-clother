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
    role: str  # trim | hole | sole | band


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
    front="none",       # none | buttons | zip
    pockets="none",     # none | chest | low | chest-low
    hem="straight",     # straight | curved | rib
    cuffs="plain",      # plain | rib | button
)


def top(**kw) -> Shape:
    p = {**TOP_DEFAULTS, **kw}
    hs = {"slim": 80, "regular": 88, "oversized": 102}[p["fit"]]   # half shoulder
    hh = {"slim": 72, "regular": 82, "oversized": 98}[p["fit"]]    # half hem
    ha = {"slim": 74, "regular": 84, "oversized": 100}[p["fit"]]   # half chest
    ay = {"slim": 150, "regular": 154, "oversized": 164}[p["fit"]]
    hy = {"cropped": 296, "regular": 344, "long": 388}[p["length"]]
    nw, ny, sy = 30.0, 58.0, 80.0
    if p["fit"] == "oversized":
        sy = 84.0

    N = (CX + nw, ny)
    S = (CX + hs, sy)
    A = (CX + ha, ay)
    side_y = hy - (22 if p["hem"] == "curved" else 0)
    Hc = (CX + hh, side_y)

    right: list[tuple[float, float]] = [N, S]
    cuff = None
    if p["sleeve"] == "none":
        arm = f"Q {_pt((CX + hs - 16, (sy + ay) / 2))} {_pt(A)}"
    else:
        if p["sleeve"] == "long":
            th, ln = math.radians(20), 252.0
            cw = {"slim": 31, "regular": 35, "oversized": 42}[p["fit"]]
        else:
            th, ln = math.radians(40), 76.0
            cw = {"slim": 50, "regular": 56, "oversized": 66}[p["fit"]]
        d = (math.sin(th), math.cos(th))
        q = (-math.cos(th), math.sin(th))
        Co = (S[0] + d[0] * ln, S[1] + d[1] * ln)
        Ci = (Co[0] + q[0] * cw, Co[1] + q[1] * cw)
        cuff = (Co, Ci, d)
        arm = f"L {_pt(Co)} L {_pt(Ci)} L {_pt(A)}"

    # outline, clockwise from the right neck point
    hem_dip = 12 if p["hem"] == "curved" else 5
    Sl, Al, Hl, Nl = _mirror(S), _mirror(A), _mirror(Hc), _mirror(N)
    if p["sleeve"] == "none":
        arm_l = f"L {_pt(Al)} Q {_pt((CX - hs + 16, (sy + ay) / 2))} {_pt(Sl)}"
    else:
        Co, Ci, _ = cuff
        arm_l = f"L {_pt(Al)} L {_pt(_mirror(Ci))} L {_pt(_mirror(Co))} L {_pt(Sl)}"
    back_neck_y = ny - (16 if p["neck"] == "collar" else 4)
    if p["hem"] == "curved":
        hem = (f"C {_pt((CX + hh - 26, hy + hem_dip))} {_pt((CX - hh + 26, hy + hem_dip))} {_pt(Hl)}")
    else:
        hem = f"Q {_pt((CX, hy + hem_dip))} {_pt(Hl)}"
    outline = (f"M {_pt(N)} L {_pt(S)} {arm} L {_pt(Hc)} {hem} {arm_l} L {_pt(Nl)} "
               f"Q {_pt((CX, back_neck_y))} {_pt(N)} Z")

    sh = Shape(outline=outline)
    sh.anchors = {"neck": (CX, ny), "shoulder_l": Sl, "shoulder_r": S, "hem": (CX, hy)}
    sh.body_box = (CX - ha, sy, CX + ha, hy)
    xmax = max(S[0], A[0], Hc[0], cuff[0][0] if cuff else 0)
    sh.bbox = (2 * CX - xmax, back_neck_y - {"hood": 70, "turtle": 30}.get(p["neck"], 0), xmax, hy + hem_dip)

    # ---- neckline
    front_bottom = ny
    if p["neck"] in ("crew", "hood"):
        dip = 24
        front_bottom = ny + dip
        sh.parts.append(Part(
            f"M {_pt(Nl)} Q {_pt((CX, back_neck_y))} {_pt(N)} Q {_pt((CX, ny + dip * 2))} {_pt(Nl)} Z", "hole"))
        sh.lines.append(f"M {_pt((Nl[0] - 5, ny + 4))} Q {_pt((CX, ny + dip * 2 + 16))} {_pt((N[0] + 5, ny + 4))}")
    elif p["neck"] == "v":
        front_bottom = ny + 58
        sh.parts.append(Part(
            f"M {_pt(Nl)} Q {_pt((CX, back_neck_y))} {_pt(N)} L {_pt((CX, front_bottom))} Z", "hole"))
        sh.lines.append(f"M {_pt((Nl[0] - 6, ny + 3))} L {_pt((CX, front_bottom + 10))} L {_pt((N[0] + 6, ny + 3))}")
    elif p["neck"] == "collar":
        front_bottom = ny + 30
        sh.parts.append(Part(
            f"M {_pt(Nl)} Q {_pt((CX, back_neck_y))} {_pt(N)} L {_pt((CX, front_bottom))} Z", "hole"))
        for m in (lambda q: q, _mirror):
            leaf = [m((CX + nw + 3, ny - 5)), m((CX + 40, ny + 44)), m((CX + 1, front_bottom + 2)), m((CX + nw - 9, ny - 14))]
            sh.parts.append(Part("M " + " L ".join(_pt(q) for q in leaf) + " Z", "trim"))
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

    # ---- armhole seams
    if p["sleeve"] != "none":
        for m in (lambda q: q, _mirror):
            sh.lines.append(f"M {_pt(m(S))} Q {_pt(m((CX + hs - 14, (sy + ay) / 2)))} {_pt(m(A))}")

    # ---- cuffs
    if cuff and p["cuffs"] in ("rib", "button"):
        Co, Ci, d = cuff
        depth = 17 if p["cuffs"] == "rib" else 22
        Bo = (Co[0] - d[0] * depth, Co[1] - d[1] * depth)
        Bi = (Ci[0] - d[0] * depth, Ci[1] - d[1] * depth)
        for m in (lambda q: q, _mirror):
            band = [m(Co), m(Ci), m(Bi), m(Bo)]
            sh.parts.append(Part("M " + " L ".join(_pt(q) for q in band) + " Z", "band"))
            if p["cuffs"] == "button":
                mid = ((Ci[0] + Bi[0]) / 2 + 5, (Ci[1] + Bi[1]) / 2 - 3)
                sh.dots.append((*m(mid), 2.4))
    elif cuff and p["sleeve"] == "short":
        Co, Ci, d = cuff
        Bo = (Co[0] - d[0] * 9, Co[1] - d[1] * 9)
        Bi = (Ci[0] - d[0] * 9, Ci[1] - d[1] * 9)
        for m in (lambda q: q, _mirror):
            sh.lines.append(f"M {_pt(m(Bo))} L {_pt(m(Bi))}")

    # ---- hem
    if p["hem"] == "rib":
        b = 18
        sh.parts.append(Part(
            f"M {_pt((CX + hh, hy - b))} L {_pt(Hc)} Q {_pt((CX, hy + hem_dip))} {_pt(Hl)} "
            f"L {_pt((CX - hh, hy - b))} Q {_pt((CX, hy - b + hem_dip))} {_pt((CX + hh, hy - b))} Z", "band"))
    elif p["hem"] == "straight":
        sh.lines.append(f"M {_pt((CX - hh + 1, hy - 9))} Q {_pt((CX, hy - 4))} {_pt((CX + hh - 1, hy - 9))}")

    # ---- front opening
    bottom = hy + (hem_dip - 2 if p["hem"] == "curved" else 2)
    if p["front"] == "buttons":
        sh.lines.append(f"M {_pt((CX - 8, front_bottom + 2))} L {_pt((CX - 8, bottom))}")
        sh.lines.append(f"M {_pt((CX + 8, front_bottom + 2))} L {_pt((CX + 8, bottom))}")
        n = 6 if p["length"] != "cropped" else 5
        y0, y1 = front_bottom + 16, hy - 26
        for i in range(n):
            sh.dots.append((CX, y0 + (y1 - y0) * i / (n - 1), 3.0))
    elif p["front"] == "zip":
        sh.lines.append(f"M {_pt((CX, front_bottom))} L {_pt((CX, bottom))}")
        sh.lines.append(f"M {_pt((CX - 4, front_bottom + 6))} L {_pt((CX - 4, front_bottom + 20))} "
                        f"L {_pt((CX + 4, front_bottom + 20))} L {_pt((CX + 4, front_bottom + 6))}")

    # ---- pockets
    def patch(x, y, w, h, flap=True):
        sh.lines.append(f"M {_pt((x, y))} L {_pt((x, y + h - 6))} Q {_pt((x, y + h))} {_pt((x + 6, y + h))} "
                        f"L {_pt((x + w - 6, y + h))} Q {_pt((x + w, y + h))} {_pt((x + w, y + h - 6))} L {_pt((x + w, y))} Z")
        if flap:
            sh.lines.append(f"M {_pt((x, y + 13))} L {_pt((x + w / 2, y + 19))} L {_pt((x + w, y + 13))}")

    if p["pockets"] in ("chest", "chest-low"):
        patch(CX + 20, ay + 2, 42, 46)
        if p["pockets"] == "chest-low":
            patch(CX - 62, ay + 2, 42, 46)
    if p["pockets"] in ("low", "chest-low"):
        patch(CX + 18, hy - 86, 50, 52)
        patch(CX - 68, hy - 86, 50, 52)
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
             f"Q {_pt((300, ys - (104 if hi else 62)))} {_pt((262, ys - (150 if hi else 98)))} "
             f"L {_pt(tongue)} L {_pt(throat_end)} Q {_pt((84, ys - 46))} {_pt((48, ys - 4))} L {_pt((46, ys))} Z")
    outline = (f"M {_pt((44, ys + 3))} Q {_pt((40, base))} {_pt((66, base))} L {_pt((332, base))} "
               f"Q {_pt((356, base))} {_pt((356, ys + 6))} L {_pt((350, ys))} Q {_pt((360, ys - 48))} {_pt(heel_top)} "
               f"Q {_pt((300, ys - (104 if hi else 62)))} {_pt((262, ys - (150 if hi else 98)))} "
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
    sh.lines.append(f"M {_pt((throat_end[0] + 18, throat_end[1] + 20))} Q {_pt((230, ys - 30))} {_pt((262, ys - (150 if hi else 98) + 14))}")
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
