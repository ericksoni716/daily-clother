"""Ties, pocket squares, gloves, glasses, watches and socks: the accessories with small shapes of their own.

The same flat style as the clothes and the other accessories (`templates`: hats, belts, scarves, bags), and the
same way of drawing: each is drawn in centimetres about one point (its anchor), and with `px` (pixels per
centimetre) that point is put at (CX, 0) at that scale, as the outfit figure wants it; without, the piece is
scaled to fill the card. Each template's `worn` form is the one the figure draws on the wearer (`worn`), where
the card shows the piece on its own:

- `tie`: a tie knotted, from the front: its knot and blade. Anchor "knot",
  the middle of the top of the knot. style (the taxonomy's tie kinds): silk_woven | silk_printed | knit | wool |
  grenadine | bow_tie; width: skinny | slim | regular | wide; pattern (the taxonomy's tie patterns): solid |
  repp_stripe | foulard | paisley | dots | club_motif, in the second colour (`block`); worn: `length` cm from the
  knot to the tip.
- `pocket_square`: folded, standing out of a breast pocket. Anchor "pocket", the middle of the pocket's mouth.
  style: flat | one_point | puff | crown.
- `gloves`: one glove, the back of the hand, fingers up. Anchor "hand", the middle of the wrist. style:
  leather_dress | knit | mittens | fingerless | work | touchscreen.
- `eyewear`: glasses from the front. Anchor "eyes", between the middles of the lenses. style (frame):
  wayfarer | aviator | round | browline | rectangular | sport_wrap; lens: clear | grey | green | brown | mirrored
  | gradient.
- `watch`: face up, its strap running up and down from the case; worn, the strap goes across the wrist. Anchor
  "wrist", the middle of the case. style: dress | dive | field | chronograph | digital_sport; strap: leather |
  steel_bracelet | nato | rubber | canvas; dial (its shape): round | square | rectangular | cushion; dial_color
  (a hex colour); case: steel | gold, or a hex colour.
- `socks`: one sock from the side, the toe to the viewer's right. Anchor "top", the middle of its top edge.
  style: dress_otc | dress_mid_calf | casual_crew | athletic_crew | no_show | boot_ragg; pattern: solid | stripes |
  argyle | dots, in the second colour.

The body of each is the item's colour; metal (a buckle, a watch case), a lens and a dial are drawn in their own.
"""
from __future__ import annotations

import math

from .templates import BUCKLE, Shape, _Draft, _ellipse, _finish, _rr

TIE_WIDTH = {"skinny": 5.5, "slim": 7.0, "regular": 8.5, "wide": 9.8}   # cm across the blade at its widest
# a tie's knot by kind: (half its width at the top, at the bottom, its height), cm. A woven silk or a wool tie is
# thicker cloth than a printed silk, and ties a fuller knot.
TIE_KNOT = {"silk_woven": (2.3, 1.3, 4.0), "silk_printed": (2.0, 1.15, 3.5), "knit": (2.0, 1.25, 3.3),
            "wool": (2.5, 1.45, 4.3), "grenadine": (2.2, 1.25, 3.8)}
TIE_PATTERNS = ("solid", "repp_stripe", "foulard", "paisley", "dots", "club_motif")
SOCK_PATTERNS = ("solid", "stripes", "argyle", "dots")
# a lens's tint; a clear lens is a pale wash over what is behind it
LENS = {"grey": "#454a50", "green": "#4a5e40", "brown": "#6a4a30", "mirrored": "#6f9cc4", "gradient": "#454a50"}
STEEL, GOLD = BUCKLE["nickel"], BUCKLE["brass"]
POCKET = "#6b6f75"   # the jacket a pocket square stands in, on its card
SKIN = "#d6a283"   # the fingers out of a fingerless glove, on the card (the figure has its own skin colour)


def _lum(hex_: str) -> float:
    h = hex_.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _poly(pts) -> list:
    return [("M", pts[0])] + [("L", q) for q in pts[1:]] + [("Z",)]


def _smooth(pts) -> list:
    """A closed smooth curve through the points (Catmull-Rom, as cubic Béziers)."""
    n = len(pts)
    out = [("M", pts[0])]
    for i in range(n):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        out.append(("C", c1, c2, p2))
    out.append(("Z",))
    return out


def _reverse(cmds) -> list:
    """Closed subpaths, each drawn the other way round (a hole in a shape drawn the usual way)."""
    starts = [i for i, c in enumerate(cmds) if c[0] == "M"] + [len(cmds)]
    if len(starts) > 2:
        return [c for a, b in zip(starts, starts[1:], strict=False) for c in _reverse(cmds[a:b])]
    segs, cur = [], None
    start = None
    for op, *args in cmds:
        if op == "M":
            cur = start = args[0]
        elif op == "Z":
            if cur != start:
                segs.append((cur, "L", [], start))
            cur = start
        else:
            segs.append((cur, op, list(args[:-1]), args[-1]))
            cur = args[-1]
    out = [("M", segs[-1][3])]
    for a, op, ctrl, _b in reversed(segs):
        out.append((op, *reversed(ctrl), a))
    out.append(("Z",))
    return out


def _flip(cmds) -> list:
    """The path mirrored left to right, still drawn the same way round."""
    return _reverse([(op, *[(-x, y) for x, y in args]) for op, *args in cmds])


def _moved(cmds, dx=0.0, dy=0.0, deg=0.0, k=1.0) -> list:
    """The path scaled by k, turned by deg about (0, 0), then moved."""
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [(op, *[(x * k * c - y * k * s + dx, x * k * s + y * k * c + dy) for x, y in args]) for op, *args in cmds]


def _ring(cx, cy, rx, ry, t) -> list:
    return _ellipse(cx, cy, rx, ry) + _reverse(_ellipse(cx, cy, rx - t, ry - t))


def _many(shapes) -> list:
    return [c for sh in shapes for c in sh]


def _grid(x0, x1, y0, y1, step, stagger=True):
    """Points on a grid over a box, every other row moved along by half a step."""
    out, row, y = [], 0, y0
    while y <= y1:
        x = x0 + (step / 2 if stagger and row % 2 else 0.0)
        while x <= x1:
            out.append((x, y))
            x += step
        y += step * (0.87 if stagger else 1.0)
        row += 1
    return out


# ------------------------------------------------------------------ ties

def tie(**kw) -> Shape:
    """A tie knotted, from the front (see the module's notes)."""
    style = kw.get("style", "silk_woven")
    if style == "bow_tie":
        return _bow_tie(kw)
    worn = bool(kw.get("worn"))
    width = kw.get("width") or ("slim" if style == "knit" else "regular")
    w = TIE_WIDTH.get(width, TIE_WIDTH["regular"]) * (0.88 if style == "knit" else 1.0)
    kt, kb, kh = TIE_KNOT.get(style, TIE_KNOT["silk_woven"])
    if width == "skinny":
        kt, kb, kh = kt * 0.85, kb * 0.85, kh * 0.9
    L = float(kw.get("length", 44.0)) if worn else 44.0
    square = style == "knit" or kw.get("end") == "square"
    tip = 0.0 if square else w * 0.42
    outline = [("M", (-kt, 0.0)), ("L", (kt, 0.0)), ("L", (kb, kh)),
               ("Q", (w / 2 * 0.62, L * 0.45), (w / 2, L - tip))]
    outline += [("L", (w / 2 - 0.2, L)), ("L", (-w / 2 + 0.2, L))] if square else [("L", (0.0, L))]
    outline += [("L", (-w / 2, L - tip)), ("Q", (-w / 2 * 0.62, L * 0.45), (-kb, kh)), ("Z",)]
    dr = _Draft(outline, anchor="knot")
    knot = [("M", (-kt, 0.0)), ("L", (kt, 0.0)), ("L", (kb, kh)), ("Q", (0.0, kh + 0.45), (-kb, kh)), ("Z",)]
    dr.part(knot, "trim")
    _tie_pattern(dr, kw.get("pattern", "solid"), w, L)
    if style == "knit":   # knitted: rows across the blade, and its square end
        y = kh + 1.6
        while y < L - 0.6:
            dr.line((-w, y), (w, y))
            y += 1.3
    elif style == "grenadine":   # an open gauze weave: a fine grid of small openings
        dr.part(_many(_ellipse(x, y, 0.16, 0.16) for x, y in _grid(-w / 2, w / 2, kh + 0.6, L, 0.75)), "fade", None, True)
    dr.part(knot, "edge")
    dr.lines.append([("M", (-kt * 0.75, 0.35)), ("Q", (0.1, kh * 0.45), (kb * 0.55, kh - 0.25))])   # the wrap of the knot
    dr.lines.append([("M", (0.15, kh + 0.15)), ("Q", (-0.35, kh + 1.2), (0.05, kh + 2.5))])   # the dimple under it
    return _finish(dr, kw.get("px"))


def _bow_tie(kw) -> Shape:
    hw, hh = 6.0, 3.0
    outline = [("M", (-hw, -hh)), ("C", (-4.4, -3.2), (-2.6, -1.6), (-0.95, -0.95)), ("L", (0.95, -0.95)),
               ("C", (2.6, -1.6), (4.4, -3.2), (hw, -hh)), ("Q", (hw + 0.7, 0.0), (hw, hh)),
               ("C", (4.4, 3.2), (2.6, 1.6), (0.95, 0.95)), ("L", (-0.95, 0.95)),
               ("C", (-2.6, 1.6), (-4.4, 3.2), (-hw, hh)), ("Q", (-hw - 0.7, 0.0), (-hw, -hh)), ("Z",)]
    dr = _Draft(outline, anchor="knot")
    _tie_pattern(dr, kw.get("pattern", "solid"), 2 * hw, hh + 1, top=-hh - 1)
    for s in (-1, 1):   # each wing folds back on itself toward the knot
        dr.lines.append([("M", (s * 1.1, -0.2)), ("Q", (s * 3.4, -0.9), (s * 5.4, -1.4))])
        dr.lines.append([("M", (s * 1.1, 0.3)), ("Q", (s * 3.4, 1.0), (s * 5.4, 1.6))])
    dr.part(_rr(-1.05, -1.25, 1.05, 1.25, 0.45), "trim")
    return _finish(dr, kw.get("px"))


def _tie_pattern(dr: _Draft, pattern: str, w: float, L: float, top: float = 0.0) -> None:
    """The tie's pattern in the second colour, over the blade and the knot (cut by its edge)."""
    x0, x1 = -w / 2 - 1, w / 2 + 1
    if pattern == "repp_stripe":   # diagonal stripes, rising to the wearer's left
        bands, y = [], top - w
        while y < L + w:
            bands.append(_poly([(x0, y), (x1, y - (x1 - x0)), (x1, y - (x1 - x0) + 1.0), (x0, y + 1.0)]))
            y += 3.4
        dr.part(_many(bands), "block", None, True)
    elif pattern == "dots":
        dr.part(_many(_ellipse(x, y, 0.3, 0.3) for x, y in _grid(x0, x1, top + 0.6, L, 1.5)), "block", None, True)
    elif pattern == "foulard":   # a small repeating diamond
        dr.part(_many(_poly([(x, y - 0.38), (x + 0.38, y), (x, y + 0.38), (x - 0.38, y)])
                      for x, y in _grid(x0, x1, top + 0.6, L, 1.3)), "block", None, True)
    elif pattern == "paisley":   # small teardrops with a curled tip, turned this way and that
        drop = [("M", (0.7, -0.95)), ("C", (0.1, -0.9), (-0.55, -0.4), (-0.45, 0.15)), ("C", (-0.35, 0.6), (0.35, 0.65), (0.45, 0.15)),
                ("C", (0.5, -0.2), (0.4, -0.5), (0.7, -0.95)), ("Z",)]
        dr.part(_many(_moved(drop, x, y, 40 if i % 2 else -25, 1.15) for i, (x, y) in enumerate(_grid(x0, x1, top + 1.0, L, 2.5))),
                "block", None, True)
    elif pattern == "club_motif":   # a small emblem (a shield) repeated
        shield = [("M", (-0.42, -0.5)), ("L", (0.42, -0.5)), ("L", (0.42, 0.05)), ("Q", (0.42, 0.45), (0.0, 0.62)),
                  ("Q", (-0.42, 0.45), (-0.42, 0.05)), ("Z",)]
        dr.part(_many(_moved(shield, x, y) for x, y in _grid(x0, x1, top + 1.2, L, 2.6)), "block", None, True)


# ------------------------------------------------------------------ pocket squares

def pocket_square(**kw) -> Shape:
    """A pocket square folded, standing out of a breast pocket (see the module's notes)."""
    style = kw.get("style", "flat")
    if style == "one_point":
        outline = _poly([(-4.3, 0.5), (-4.2, -0.5), (-0.6, -4.8), (4.2, -0.5), (4.3, 0.5)])
        folds = [[("M", (-0.6, -4.8)), ("L", (0.6, 0.3))]]
    elif style == "crown":   # three points
        outline = _poly([(-4.3, 0.5), (-4.1, -0.9), (-2.9, -3.9), (-1.5, -1.5), (0.0, -4.9), (1.5, -1.5), (2.9, -3.9),
                         (4.1, -0.9), (4.3, 0.5)])
        folds = [[("M", (x, y)), ("L", (x * 0.7, 0.3))] for x, y in ((-2.9, -3.9), (0.0, -4.9), (2.9, -3.9))]
    elif style == "puff":   # the middle of the square pushed up, loose
        outline = [("M", (-4.1, 0.5)), ("C", (-4.9, -1.6), (-3.7, -3.4), (-2.0, -3.0)), ("C", (-1.2, -4.5), (1.4, -4.7), (2.0, -3.0)),
                   ("C", (3.7, -3.6), (5.0, -1.6), (4.1, 0.5)), ("Z",)]
        folds = [[("M", (-2.6, 0.3)), ("Q", (-2.9, -1.4), (-2.0, -2.6))], [("M", (0.2, 0.3)), ("Q", (-0.4, -2.0), (0.3, -3.6))],
                 [("M", (2.7, 0.3)), ("Q", (2.9, -1.2), (2.2, -2.6))]]
    else:   # flat: a straight band of cloth just above the pocket
        outline = _rr(-4.3, -1.3, 4.3, 0.5, 0.12)
        folds = []
    dr = _Draft(outline, anchor="pocket")
    dr.lines += folds
    if not kw.get("worn"):   # on the card, the top of the pocket it stands in, in a jacket's grey
        dr.part(_rr(-5.6, 0.0, 5.6, 2.2, 0.15), "inlay", POCKET)
    return _finish(dr, kw.get("px"))


# ------------------------------------------------------------------ gloves

# (middle, width, length above the knuckles) of each finger, little finger first, cm
FINGERS = [(-3.25, 1.95, 6.0), (-1.1, 2.1, 7.6), (1.1, 2.1, 8.2), (3.25, 2.0, 7.4)]
_GLOVES = {   # half the palm's width, how wide the fingers are, the cuff (half its width at the bottom, its depth)
    "leather_dress": (4.4, 1.0, 4.4, 3.6), "knit": (4.5, 1.08, 4.3, 6.0), "mittens": (4.6, 1.0, 4.5, 5.5),
    "fingerless": (4.5, 1.08, 4.3, 4.0), "work": (4.9, 1.15, 5.9, 7.0), "touchscreen": (4.5, 1.05, 4.3, 4.6),
}


def gloves(**kw) -> Shape:
    """One glove, the back of the hand, fingers up and the thumb to the viewer's right (see the module's notes)."""
    style = kw.get("style", "leather_dress")
    hp, fw, cw, cd = _GLOVES.get(style, _GLOVES["leather_dress"])
    kn = -9.5   # the knuckles
    cut = 2.6 if style == "fingerless" else None   # a fingerless glove stops this far up the fingers
    fingers = [(x * hp / 4.4, wd * fw, ln) for x, wd, ln in FINGERS]
    out = [("M", (-cw, cd)), ("L", (-hp + 0.2, 0.0)), ("C", (-hp - 0.2, -3.0), (-hp, -6.5), (-hp + 0.1, kn + 0.6))]
    tips = []
    if style == "mittens":   # one rounded pocket for the four fingers
        out += [("C", (-hp + 0.2, kn - 6.5), (hp - 0.5, kn - 7.6), (hp - 0.1, kn + 0.4))]
    else:
        for i, (x, wd, ln) in enumerate(fingers):
            a, b, top = x - wd / 2, x + wd / 2, kn - (min(ln, cut) if cut else ln)
            if i:
                out.append(("L", (a, kn + 0.2)))
            if cut:
                out += [("L", (a, top)), ("L", (b, top))]
                tips.append((x, wd, top, kn - ln))
            else:
                out += [("L", (a, top + wd / 2)), ("Q", (a, top), (x, top)), ("Q", (b, top), (b, top + wd / 2))]
            out.append(("L", (b, kn + 0.2) if i < 3 else (b, kn + 0.5)))
    # the side of the hand down to the thumb, round the thumb, and down to the wrist
    out += [("L", (hp + 0.1, -6.4)), ("C", (hp + 1.4, -8.0), (hp + 2.6, -10.2), (hp + 3.7, -10.0)),
            ("C", (hp + 4.9, -9.6), (hp + 4.6, -8.2), (hp + 3.9, -7.0)),
            ("C", (hp + 2.8, -5.0), (hp + 1.2, -2.4), (hp - 0.2, 0.0)), ("L", (cw, cd)), ("Z",)]
    dr = _Draft(out, anchor="hand")
    for x, wd, top, end in tips:   # the fingers out of a fingerless glove
        dr.behind.append((_rr(x - wd / 2 + 0.2, end, x + wd / 2 - 0.2, top + 0.6, wd / 2 - 0.25), "inlay", SKIN))
    cuff = [("M", (-cw, cd)), ("L", (-hp + 0.2, 0.0)), ("L", (hp - 0.2, 0.0)), ("L", (cw, cd)), ("Z",)]
    if style in ("knit", "mittens", "fingerless", "touchscreen"):   # a ribbed cuff
        dr.part(cuff, "band")
        for i in range(1, 9):
            f = i / 9
            dr.line((-hp + 0.2 + (2 * hp - 0.4) * f, 0.2), (-cw + 2 * cw * f, cd - 0.1))
        if cut:   # and ribbed edges where the fingers stop
            for x, wd, top, _ in tips:
                dr.part(_rr(x - wd / 2, top, x + wd / 2, top + 0.7, 0.1), "band")
    elif style == "work":   # a stiff gauntlet cuff in a darker leather, and a strap over the knuckles
        dr.part(cuff, "inlay", "deep")
        dr.part(_poly([(-hp - 0.2, -7.6), (hp + 0.3, -7.6), (hp + 0.3, -5.9), (-hp - 0.2, -5.9)]), "band", None, True)
        for x, _, _ in fingers:
            dr.line((x, kn - 1.0), (x, kn - 4.0))
    else:   # a leather dress glove: a short cuff, a vent and a snap, and three lines of points down the back
        dr.line((-hp + 0.2, 0.0), (hp - 0.2, 0.0))
        dr.line((cw * 0.45, cd), (cw * 0.42, cd - 2.2))
        dr.dots.append((cw * 0.68, cd * 0.4, 0.3))
        for x in (-2.2, 0.0, 2.2):
            dr.lines.append([("M", (x * hp / 4.4, kn + 0.6)), ("Q", (x * hp / 4.4 * 1.05, -6.0), (x * hp / 4.4 * 0.9, -3.5))])
        dr.part(_moved(_ellipse(0, 0, 0.45, 2.2), -2.6, -5.6, 12), "shine")
    if style == "touchscreen":   # conductive pads on the thumb and first two fingertips
        for x, wd, ln in fingers[2:]:
            dr.part(_rr(x - wd / 2, kn - ln - 0.2, x + wd / 2, kn - ln + 1.6, wd / 2), "inlay", BUCKLE["gunmetal"], True)
        dr.part(_moved(_ellipse(0, 0, 1.3, 1.0), hp + 3.9, -9.3, -35), "inlay", BUCKLE["gunmetal"], True)
    if style in ("knit", "touchscreen", "fingerless"):   # knitted: a few rows across the back of the hand
        for y in (-2.0, -4.5, -7.0):
            dr.lines.append([("M", (-hp, y)), ("Q", (0.0, y - 0.4), (hp, y))])
    return _finish(dr, kw.get("px"))


# ------------------------------------------------------------------ glasses

# one lens (the one on the viewer's left), about its middle; the nose is to the right
_LENSES = {
    "wayfarer": [(-2.75, -2.05), (-0.6, -1.75), (2.3, -1.75), (2.45, -0.3), (1.9, 1.35), (0.0, 1.75), (-1.9, 1.35), (-2.5, 0.0)],
    "aviator": [(-2.75, -1.65), (0.0, -1.9), (2.35, -1.55), (2.4, 0.2), (1.5, 2.25), (-0.3, 2.65), (-2.0, 1.85), (-2.8, 0.2)],
    "round": [(math.cos(a) * 2.15, math.sin(a) * 2.15) for a in (i * math.pi / 4 for i in range(8))],
    "browline": [(-2.6, -1.7), (0.0, -1.85), (2.4, -1.6), (2.35, 0.4), (1.4, 1.75), (-0.6, 1.85), (-2.25, 1.15)],
    "rectangular": None,
}
_RIM = {"wayfarer": (0.55, 0.45), "aviator": (0.18, 0.18), "round": (0.25, 0.25), "browline": (0.7, 0.12),
        "rectangular": (0.35, 0.35)}   # how thick the frame is above and below the lens
LENS_GAP = 3.1   # each lens's middle, from the middle of the nose


def _lens(style: str, grow_top: float = 0.0, grow_bottom: float = 0.0) -> list:
    """One lens's outline, about its middle, grown outward by the frame's thickness."""
    if style == "rectangular":
        return _rr(-2.6 - grow_top, -1.55 - grow_top, 2.5 + grow_top, 1.5 + grow_bottom, 0.55 + grow_top)
    return _smooth([(x + math.copysign(grow_top if y < 0 else grow_bottom, x) * abs(x) / (abs(x) + abs(y) + 1e-9),
                     y + math.copysign(grow_top if y < 0 else grow_bottom, y) * abs(y) / (abs(x) + abs(y) + 1e-9))
                    for x, y in _LENSES[style]])


def eyewear(**kw) -> Shape:
    """Glasses from the front (see the module's notes)."""
    style = kw.get("style", "wayfarer")
    lens = kw.get("lens") or ("grey" if style in ("wayfarer", "aviator", "sport_wrap") else "clear")
    if style == "sport_wrap":   # one shield lens across both eyes, under a thin top bar
        shield = _smooth([(-7.0, -1.6), (-3.0, -2.0), (0.0, -1.9), (3.0, -2.0), (7.0, -1.6), (6.8, 0.4), (4.6, 2.1),
                          (1.6, 1.9), (0.0, 0.9), (-1.6, 1.9), (-4.6, 2.1), (-6.8, 0.4)])
        bar = [("M", (-7.3, -1.2)), ("C", (-4.0, -2.9), (4.0, -2.9), (7.3, -1.2)), ("L", (7.3, -0.6)),
               ("C", (4.0, -2.2), (-4.0, -2.2), (-7.3, -0.6)), ("Z",)]
        dr = _Draft(bar, anchor="eyes")
        dr.behind.append((shield, *_lens_paint(lens)))
        _lens_finish(dr, lens, [shield], 1.6)
        dr.part(_poly([(-0.55, 0.9), (0.55, 0.9), (0.4, 1.7), (-0.4, 1.7)]), "inlay", BUCKLE["matte_black"])   # the nose piece
        return _finish(dr, kw.get("px"))
    top, bottom = _RIM.get(style, _RIM["wayfarer"])
    inner = _lens(style)
    outer = _lens(style, top, bottom)
    left = [(op, *[(x - LENS_GAP, y) for x, y in args]) for op, *args in outer + _reverse(inner)]
    right = _flip(left)
    # the bridge over the nose and the temples (the arms, seen end on, going back to the ears)
    if style == "aviator":   # a double bridge: a brow bar above the lenses and a thin bridge between them
        bridge = _rr(-1.2, -1.15, 1.2, -0.9, 0.1) + _rr(-1.6, -2.05, 1.6, -1.8, 0.1)
    elif style == "round":
        bridge = [("M", (-1.0, -0.75)), ("Q", (0.0, -1.6), (1.0, -0.75)), ("L", (1.0, -0.45)), ("Q", (0.0, -1.3), (-1.0, -0.45)), ("Z",)]
    else:
        th = max(top, 0.3)
        bridge = _rr(-1.0, -1.35, 1.0, -1.35 + th + 0.25, 0.15)
    xo = LENS_GAP + (2.6 if style != "aviator" else 2.65)
    temples = _rr(xo - 0.4, -1.5, 7.3, -1.0, 0.15) + _flip(_rr(xo - 0.4, -1.5, 7.3, -1.0, 0.15))
    dr = _Draft(left + right + bridge + temples, anchor="eyes")
    lenses = [[(op, *[(x - LENS_GAP, y) for x, y in args]) for op, *args in inner]]
    lenses.append(_flip(lenses[0]))
    for d in lenses:
        dr.behind.append((d, *_lens_paint(lens)))
    _lens_finish(dr, lens, lenses, 0.0)
    if style in ("aviator", "round", "browline"):   # a metal frame: little pads on the nose
        for s in (-1, 1):
            dr.part(_ellipse(s * 1.25, 0.5, 0.25, 0.45), "inlay", STEEL)
    return _finish(dr, kw.get("px"))


def _lens_paint(lens: str) -> tuple[str, str | None]:
    return ("fade", None) if lens not in LENS else ("inlay", LENS[lens])


def _lens_finish(dr: _Draft, lens: str, lenses, x_shine: float) -> None:
    """A glint across each lens; a gradient lens fades out toward the bottom."""
    for d in lenses:
        xs = [q[0] for c in d for q in c[1:]]
        cx = (min(xs) + max(xs)) / 2 if not x_shine else 0.0
        for s in ((1,) if not x_shine else (-1, 1)):
            x = cx + (s * 3.4 if x_shine else 0.0)
            if lens == "gradient":
                dr.behind.append((_ellipse(x, 1.0, 1.7, 0.6), "fade", None))
            dr.behind.append((_poly([(x - 1.5, 0.3), (x - 0.2, -1.3), (x + 0.3, -1.3), (x - 1.0, 0.3)]), "shine", None))
            if lens == "mirrored":   # a mirror catches the sky: a second, broader glint
                dr.behind.append((_poly([(x - 0.2, 1.1), (x + 1.3, -0.9), (x + 1.75, -0.6), (x + 0.6, 1.1)]), "shine", None))


# ------------------------------------------------------------------ watches

_WATCHES = {   # the case's half width, whether it has a turning bezel, the strap it most often comes on
    "dress": (1.75, False, "leather"), "dive": (2.15, True, "steel_bracelet"), "field": (1.9, False, "nato"),
    "chronograph": (2.1, False, "leather"), "digital_sport": (2.1, False, "rubber"),
}
DIAL = {"dress": "#ece4d0", "dive": "#1f2a44", "field": "#33383a", "chronograph": "#f2f0ea", "digital_sport": "#b9c2a6"}


def _case(style: str, dial: str, r: float) -> tuple[list, list]:
    """The case's outline and the dial inside it, about the middle."""
    if style == "digital_sport" or dial == "square":
        return _rr(-r, -r, r, r, r * 0.35), _rr(-r * 0.78, -r * 0.78, r * 0.78, r * 0.78, r * 0.22)
    if dial == "rectangular":   # a tank: taller than wide
        return _rr(-r * 0.78, -r * 1.12, r * 0.78, r * 1.12, 0.3), _rr(-r * 0.6, -r * 0.94, r * 0.6, r * 0.94, 0.15)
    if dial == "cushion":
        return _rr(-r, -r, r, r, r * 0.6), _rr(-r * 0.8, -r * 0.8, r * 0.8, r * 0.8, r * 0.5)
    return _ellipse(0, 0, r, r), _ellipse(0, 0, r * 0.8, r * 0.8)


def watch(**kw) -> Shape:
    """A watch (see the module's notes)."""
    style = kw.get("style", "dress")
    r, bezel, strap_default = _WATCHES.get(style, _WATCHES["dress"])
    strap = kw.get("strap") or strap_default
    dial = kw.get("dial", "round")
    worn = bool(kw.get("worn"))
    sw = r * 1.05   # the strap's width, at the case
    metal = {"gold": GOLD, "steel": STEEL}.get(kw.get("case"), kw.get("case")) or STEEL
    dial_c = kw.get("dial_color") or DIAL.get(style, DIAL["dress"])
    case, face = _case(style, dial, r)
    if worn:   # round the wrist: the strap across it, the case on top
        half = float(kw.get("half", 3.1))
        band = _rr(-half, -sw / 2, half, sw / 2, 0.4)
        dr = _Draft(band + case, anchor="wrist")
        dr.part(case, "inlay", metal if strap != "steel_bracelet" or kw.get("case") else None)
        dr.part(face, "inlay", dial_c)
        _hands(dr, r, dial_c, few=True)
        return _finish(dr, kw.get("px"))
    L = 9.5   # each half of the strap, out from the case
    tip = sw * 0.82
    up = [("M", (-sw / 2, -r * 0.6)), ("L", (-tip / 2, -L)), ("Q", (0, -L - 0.5), (tip / 2, -L)), ("L", (sw / 2, -r * 0.6)), ("Z",)]
    down = [("M", (-sw / 2, r * 0.6)), ("L", (-tip / 2, L + 1.2)), ("Q", (0, L + 2.2), (tip / 2, L + 1.2)), ("L", (sw / 2, r * 0.6)), ("Z",)]
    lugs = []
    if style != "digital_sport":
        for sy in (-1, 1):
            lugs.append(_poly([(-sw / 2 - 0.15, sy * r * 0.55), (-sw / 2 + 0.05, sy * (r + 0.55)), (sw / 2 - 0.05, sy * (r + 0.55)),
                               (sw / 2 + 0.15, sy * r * 0.55)]))
    crown = _rr(r - 0.1, -0.35, r + 0.45, 0.35, 0.1)
    pushers = _many(_moved(_rr(-0.22, -0.18, 0.4, 0.18, 0.08), (r + 0.05) * math.cos(a), (r + 0.05) * math.sin(a),
                           math.degrees(a)) for a in (-0.75, 0.75)) if style in ("chronograph", "digital_sport") else []
    dr = _Draft(up + down + _many(lugs), anchor="wrist")
    _strap(dr, strap, sw, tip, r, L, metal)
    dr.part(crown + pushers, "inlay", metal)
    dr.part(case, "inlay", metal if strap != "steel_bracelet" or kw.get("case") else None)
    if bezel:   # a dive watch's turning bezel, with a mark at twelve
        dr.part(_ring(0, 0, r * 0.93, r * 0.93, r * 0.2), "inlay", BUCKLE["matte_black"])
        dr.part(_poly([(0, -r * 0.76), (-0.2, -r * 0.9), (0.2, -r * 0.9)]), "mark", "#f2f0ea")
        face = _ellipse(0, 0, r * 0.72, r * 0.72)
    dr.part(face, "inlay", dial_c)
    ink = "#f2f0ea" if _lum(dial_c) < 0.4 else "#2a2b2e"
    if style == "digital_sport":   # a screen of segment figures
        segs = []
        for i, x in enumerate((-1.05, -0.35, 0.45, 1.15)):
            segs += _rr(x - 0.22, -0.55, x + 0.22, -0.45, 0.03) + _rr(x + 0.17, -0.5, x + 0.27, 0.45, 0.03)
            if i % 2 == 0:
                segs += _rr(x - 0.22, -0.05, x + 0.22, 0.05, 0.03) + _rr(x - 0.22, 0.4, x + 0.22, 0.5, 0.03)
        segs += _ellipse(0.05, -0.2, 0.06, 0.06) + _ellipse(0.05, 0.2, 0.06, 0.06)
        dr.part(segs, "mark", ink)
        return _finish(dr, kw.get("px"))
    rf = r * (0.72 if bezel else 0.8)
    marks = []
    for i in range(12):
        a = math.radians(i * 30)
        big = i % 3 == 0 and style in ("field", "dive")
        ln, wd = (0.42 if big else 0.22) * rf / 1.4, (0.13 if big else 0.07)
        x, y = math.sin(a) * (rf - 0.25 - ln / 2), -math.cos(a) * (rf - 0.25 - ln / 2)
        if dial == "rectangular":
            x, y = x * 0.75, y * 1.15
        marks += _moved(_rr(-wd, -ln / 2, wd, ln / 2, 0.03), x, y, i * 30)
    if style == "chronograph":   # three small dials
        for x, y in ((-rf * 0.45, 0.1), (rf * 0.45, 0.1), (0.0, rf * 0.5)):
            dr.part(_ellipse(x, y, rf * 0.24, rf * 0.24), "edge")
    dr.part(marks, "mark", ink)
    _hands(dr, rf, dial_c)
    return _finish(dr, kw.get("px"))


def _hands(dr: _Draft, r: float, dial_c: str, few: bool = False) -> None:
    ink = "#f2f0ea" if _lum(dial_c) < 0.4 else "#2a2b2e"
    hour = _moved(_poly([(-0.09, 0.15), (-0.06, -r * 0.5), (0.0, -r * 0.58), (0.06, -r * 0.5), (0.09, 0.15)]), 0, 0, 300)
    minute = _moved(_poly([(-0.07, 0.15), (-0.04, -r * 0.78), (0.0, -r * 0.84), (0.04, -r * 0.78), (0.07, 0.15)]), 0, 0, 50)
    dr.part(hour + minute + _ellipse(0, 0, 0.1 if not few else 0.15, 0.1 if not few else 0.15), "mark", ink)


def _strap(dr: _Draft, strap: str, sw: float, tip: float, r: float, L: float, metal: str) -> None:
    """The strap's own look: stitching and a buckle, links, a woven nylon pass-through, rubber grooves, canvas."""
    if strap == "steel_bracelet":   # links across, the middle row of links set apart
        y = r + 0.8
        while y < L + 0.6:
            for s in (-1, 1):
                dr.line((-sw, s * y), (sw, s * y))
            y += 0.75
        for x in (-sw * 0.2, sw * 0.2):
            dr.line((x, -L - 1), (x, -r))
            dr.line((x, r), (x, L + 2))
        dr.part(_rr(-tip / 2 - 0.1, L - 1.6, tip / 2 + 0.1, L - 0.4, 0.15), "edge")   # the clasp
        return
    if strap == "nato":   # one strap passing under the case, with two metal keepers
        dr.part(_rr(-sw / 2, -r, sw / 2, r, 0.1), "trim")
        for y in (L * 0.55, L * 0.75):
            dr.part(_rr(-tip / 2 - 0.15, y, tip / 2 + 0.15, y + 0.55, 0.12), "inlay", metal)
        for i in range(4):
            dr.dots.append((0.0, -L * 0.45 - i * 1.05, 0.13))
        return
    if strap == "rubber":   # grooves across, near the case
        for s in (-1, 1):
            for i in range(4):
                dr.line((-sw, s * (r + 0.9 + i * 0.7)), (sw, s * (r + 0.9 + i * 0.7)))
    elif strap == "canvas":   # a woven strap: its weave along it, stitched round
        for f in (-0.25, 0.0, 0.25):
            dr.line((f * sw, -L), (f * sw, -r))
            dr.line((f * sw, r), (f * sw, L + 1))
    else:   # leather: stitched round its edges
        for s in (-1, 1):
            dr.part([("M", (s * (sw / 2 - 0.22), -r * 0.6)), ("L", (s * (tip / 2 - 0.2), -L + 0.3))], "stitch", "#ece4d0")
            dr.part([("M", (s * (sw / 2 - 0.22), r * 0.6)), ("L", (s * (tip / 2 - 0.2), L + 0.8))], "stitch", "#ece4d0")
    # the buckle at the top end, and holes in the other half
    dr.part(_rr(-tip / 2 - 0.25, -L + 0.4, tip / 2 + 0.25, -L + 1.3, 0.2) + _rr(-tip / 2 + 0.05, -L + 0.65, tip / 2 - 0.05, -L + 1.05, 0.1, reverse=True),
            "inlay", metal)
    dr.part(_rr(-tip / 2 - 0.05, -L + 2.0, tip / 2 + 0.05, -L + 2.5, 0.1), "band")   # the keeper
    for i in range(5):
        dr.dots.append((0.0, L * 0.45 + i * 0.95, 0.12))


# ------------------------------------------------------------------ socks

SOCK_LENGTH = {"no_show": 0.0, "athletic_crew": 19.0, "casual_crew": 17.0, "dress_mid_calf": 30.0, "dress_otc": 44.0,
               "boot_ragg": 28.0}   # cm from the ground to the top of the sock, worn
SOCK_RIB = {"athletic_crew": 3.0, "casual_crew": 2.4, "dress_mid_calf": 2.0, "dress_otc": 2.4, "boot_ragg": 5.0}


def socks(**kw) -> Shape:
    """One sock from the side (see the module's notes)."""
    style = kw.get("style", "casual_crew")
    pattern = kw.get("pattern", "solid")
    hw = 4.4 if style != "boot_ragg" else 4.9   # half the leg's width, laid flat
    foot, sole = 21.0, 7.6   # the foot's length past the back of the heel, and how high it is
    if style == "no_show":   # only a low cup round the foot: heel to toe, its opening dipping over the instep
        outline = [("M", (-hw, 0.0)), ("Q", (-hw + 4.0, 0.6), (2.0, 3.0)), ("Q", (8.0, 5.0), (foot - 6.5, 3.6)),
                   ("C", (foot - 1.5, 3.4), (foot + 1.6, 7.6), (foot - 3.0, sole)), ("L", (-hw + 2.0, sole)),
                   ("C", (-hw - 0.6, sole), (-hw - 0.9, 3.0), (-hw, 0.0)), ("Z",)]
        dr = _Draft(outline, anchor="top")
        dr.part([("M", (-hw, 0.0)), ("Q", (-hw + 4.0, 0.6), (2.0, 3.0)), ("Q", (8.0, 5.0), (foot - 6.5, 3.6)),
                 ("L", (foot - 6.4, 4.4)), ("Q", (8.0, 5.8), (2.0, 3.8)), ("Q", (-hw + 4.0, 1.4), (-hw - 0.1, 0.8)), ("Z",)], "band")
        dr.part([("M", (foot - 4.5, 3.4)), ("C", (foot + 1.6, 3.6), (foot + 1.2, 7.6), (foot - 3.0, sole)), ("L", (foot - 4.0, sole)),
                 ("Q", (foot - 5.2, 5.4), (foot - 4.5, 3.4)), ("Z",)], "trim", None, True)
        return _finish(dr, kw.get("px"))
    L = SOCK_LENGTH.get(style, 17.0) - sole + 2.0   # the top of the sock to where the leg turns into the foot
    outline = [("M", (-hw, 0.0)), ("L", (hw, 0.0)), ("L", (hw, L - 3.0)), ("Q", (hw + 0.4, L - 0.2), (hw + 4.5, L)),
               ("L", (foot - 3.5, L + 0.2)), ("C", (foot + 1.0, L + 0.2), (foot + 1.4, L + sole - 0.4), (foot - 3.0, L + sole - 0.2)),
               ("L", (-hw + 2.4, L + sole - 0.2)), ("C", (-hw - 0.6, L + sole - 0.2), (-hw - 1.2, L + 2.0), (-hw, L - 2.0)), ("Z",)]
    dr = _Draft(outline, anchor="top")
    _sock_pattern(dr, pattern, hw, L)
    # the heel and the toe, knitted in again (a second colour on a ragg sock)
    patch = "inlay" if style == "boot_ragg" else "trim"
    pc = "#ece4d0" if style == "boot_ragg" else None
    dr.part([("M", (-hw - 0.8, L - 3.0)), ("Q", (-hw + 3.0, L - 1.4), (-hw + 3.4, L + sole)), ("L", (-hw - 2.0, L + sole)), ("Z",)],
            patch, pc, True)
    dr.part([("M", (foot - 4.2, L - 0.5)), ("Q", (foot - 5.6, L + sole / 2), (foot - 4.0, L + sole + 0.5)),
             ("L", (foot + 2.0, L + sole + 0.5)), ("L", (foot + 2.0, L - 0.5)), ("Z",)], patch, pc, True)
    rib = SOCK_RIB.get(style, 2.4)
    dr.part(_rr(-hw - 0.4, -0.4, hw + 0.4, rib, 0.1), "band", None, True)
    for i in range(1, 8):
        x = -hw + 2 * hw * i / 8
        dr.line((x, 0.0), (x, rib))
    if pattern != "solid":   # a pattern knitted in: no rib down the leg to cross it
        pass
    elif style in ("dress_otc", "dress_mid_calf"):   # fine dress socks: a fine rib all the way down the leg
        for i in range(1, 6):
            x = -hw + 2 * hw * i / 6
            dr.line((x, rib + 0.6), (x, L - 3.5))
    elif style == "athletic_crew":   # a ribbed band round the arch
        dr.part(_poly([(hw + 3.0, L - 0.3), (hw + 6.0, L - 0.3), (hw + 6.0, L + sole + 0.5), (hw + 3.0, L + sole + 0.5)]), "band", None, True)
    elif style == "boot_ragg":   # a thick rib down the leg
        for i in range(1, 5):
            x = -hw + 2 * hw * i / 5
            dr.line((x, rib + 0.4), (x, L - 2.5))
    return _finish(dr, kw.get("px"))


def _sock_pattern(dr: _Draft, pattern: str, hw: float, L: float) -> None:
    """The pattern on the leg, in the second colour (the foot stays plain, as on most socks)."""
    x0, x1 = -hw - 1, hw + 5
    if pattern == "stripes":   # hoops round the leg
        bands, y = [], 4.0
        while y < L - 1.0:
            bands.append(_rr(x0, y, x1, y + 1.2, 0.0))
            y += 3.0
        dr.part(_many(bands), "block", None, True)
    elif pattern == "argyle":   # diamonds, two across, with thin lines crossing them
        diamonds, h, y = [], 3.4, 3.6
        while y + h < L:
            for x in ((-hw / 2, hw / 2) if int((y - 3.6) / h) % 2 == 0 else (0.0, -hw, hw)):
                diamonds.append(_poly([(x, y), (x + hw / 2, y + h / 2), (x, y + h), (x - hw / 2, y + h / 2)]))
            y += h
        dr.part(_many(diamonds), "block", None, True)
        k = 0
        while 3.6 + k * h < L:
            y = 3.6 + k * h
            dr.line((-hw, y), (hw, y + 2 * h))
            dr.line((hw, y), (-hw, y + 2 * h))
            k += 2
    elif pattern == "dots":
        dr.part(_many(_ellipse(x, y, 0.35, 0.35) for x, y in _grid(-hw, hw, 3.6, L - 1.0, 1.9)), "block", None, True)


SHAPES = {"tie": tie, "pocket_square": pocket_square, "gloves": gloves, "eyewear": eyewear, "watch": watch,
          "socks": socks}
