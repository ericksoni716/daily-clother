"""Compose an illustration: shape (from attributes) + fill (from the photo).

Four styles are offered for comparison. Three draw the parametric template;
the fourth traces the real outline from the cutout instead.
"""
from __future__ import annotations

import colorsys
import math
import re
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from . import fills
from .templates import CX, CX_ROT, K_PX, H, Shape, W, _x_on, build

STYLES = ("flat", "line", "soft", "traced")
PLACE_AT = 0.35      # where along the centre line, from neck to hem, a placed pattern is lined up
CARD = "#f1eee8"
INK = "#26231f"


@dataclass
class Fill:
    kind: str                                  # solid | stripes | swatch
    color: str = "#888888"
    stripes: fills.Stripes | None = None
    swatch: fills.Swatch | None = None
    # the plain cloth the collar is cut from, when the body's stripes are placed (a polo's chest band): the
    # repeating ground stripes without the band; None = the body's own cloth
    trim_stripes: fills.Stripes | None = None
    # with trim_stripes: whether the sleeves (and cuffs) are cut from that plain cloth too. False when the photo
    # shows the placed bands continuing onto the sleeves (a rugby shirt); the collar is always the plain cloth.
    sleeves_from_trim: bool = True


@dataclass
class Spec:
    """Everything needed to draw one item; plain data so it can be stored."""
    template: str
    params: dict
    fill: Fill
    graphic: fills.Graphic | None = None
    sole_color: str | None = None
    button_color: str | None = None   # buttons and eyelets; None = pale, like the card
    trim_color: str | None = None     # a contrast collar, cuffs and ribbing; None = the garment's own cloth
    block_color: str | None = None    # colour-blocking: the second colour (a yoke, sleeves); None = a shade of the cloth
    texture: str | None = None        # corduroy | rib_knit | cable_knit | waffle: drawn tone-on-tone over the fill
    lace_color: str | None = None     # shoes: None = laces in the upper's colour
    collar_color: str | None = None   # a collar in its own colour (a rugby shirt's white twill); None = trim colour or the cloth
    weight: str | None = None         # lightweight | midweight | heavyweight | super_heavy: how much depth the cloth is drawn with
    halo: bool = False                # a fuzzy cloth (fleece, sherpa, mohair, brushed flannel): a soft, broken edge
    sheen: bool = False               # a shiny cloth (satin, nylon): a soft highlight across the body
    texture_scale: float | None = None  # the texture's spacing: corduroy wale, knit gauge (None = standard)
    colorwork: str | None = None      # a knitted-in colour pattern placed as the garment carries it (fair_isle | nordic |
                                      # argyle | intarsia | jacquard_knit | cowichan | guernsey); tops only
    motif_colors: tuple[str, ...] = ()  # the colourwork's colours (the other colours seen); () = shades of the cloth
    notes: list[str] = field(default_factory=list)


def _rgb(hex_: str) -> tuple[float, float, float]:
    h = hex_.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _hex(rgb) -> str:
    return "#" + "".join(f"{int(round(max(0, min(1, v)) * 255)):02x}" for v in rgb)


def shade(hex_: str, amount: float) -> str:
    """Darken (negative) or lighten (positive) while keeping the hue."""
    h, l, s = colorsys.rgb_to_hls(*_rgb(hex_))
    l = max(0.0, min(1.0, l + amount))
    return _hex(colorsys.hls_to_rgb(h, l, s))


def luminance(hex_: str) -> float:
    r, g, b = _rgb(hex_)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    """The contrast ratio of two colours, as the web accessibility guidelines define it (1 to 21)."""
    def lum(hex_):
        return sum(w * (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
                   for w, c in zip((0.2126, 0.7152, 0.0722), _rgb(hex_)))
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# A jacket's buttons stand at least BUTTON_CONTRAST against its cloth (the guidelines' level for large shapes);
# its inside, shaded over the cloth, at least INSIDE_CONTRAST, or it is drawn lighter than the cloth instead.
BUTTON_CONTRAST, INSIDE_CONTRAST = 3.0, 1.3


def legible(hex_: str, ground: str, ratio: float) -> str:
    """hex_ made lighter or darker, as little as needed, to stand `ratio` against ground: first away from
    the ground's tone, then the other way; the best found if neither gets there."""
    if contrast(hex_, ground) >= ratio:
        return hex_
    away = 1 if contrast("#ffffff", ground) >= contrast("#000000", ground) else -1
    best = hex_
    for sign in (away, -away):
        for i in range(1, 21):
            c = shade(hex_, sign * 0.05 * i)
            if contrast(c, ground) >= ratio:
                return c
            if contrast(c, ground) > contrast(best, ground):
                best = c
    return best


def _over(hex_: str, top: str, opacity: float) -> str:
    """The colour of `top` laid over hex_ at an opacity."""
    return _hex(tuple(a * (1 - opacity) + b * opacity for a, b in zip(_rgb(hex_), _rgb(top))))


def inside_tint(base: str) -> tuple[str, str]:
    """The tint laid over a jacket's cloth to show its inside: darker, or on a cloth too dark for that to
    show (black, navy), lighter."""
    if contrast(_over(base, "#000000", 0.22), base) >= INSIDE_CONTRAST:
        return "#000", ".22"
    return "#fff", ".2"


def _defs_for_fill(fill: Fill, shape: Shape, uid: str, garment_w: float, garment_h: float) -> tuple[str, str]:
    """Return (defs markup, paint) for the fill."""
    if fill.kind == "solid":
        return "", fill.color
    x0, y0, _, _ = shape.bbox
    if fill.kind == "stripes" and fill.stripes:
        st = fill.stripes
        span = garment_h if st.orientation == "horizontal" else garment_w
        total = sum(w for _, w in st.bands) * span
        rects, pos = [], 0.0
        for color, wfrac in st.bands:
            size = wfrac * span
            if st.orientation == "horizontal":
                rects.append(f'<rect x="0" y="{pos:.2f}" width="10" height="{size + 0.3:.2f}" fill="{color}"/>')
            else:
                rects.append(f'<rect x="{pos:.2f}" y="0" width="{size + 0.3:.2f}" height="10" fill="{color}"/>')
            pos += size
        pw, ph = (10, total) if st.orientation == "horizontal" else (total, 10)
        return (f'<pattern id="p{uid}" patternUnits="userSpaceOnUse" x="{x0:.1f}" y="{y0:.1f}" width="{pw:.2f}" height="{ph:.2f}">'
                + "".join(rects) + "</pattern>", f"url(#p{uid})")
    if fill.kind == "swatch" and fill.swatch:
        sw = fill.swatch
        tw = sw.width_frac * garment_w
        th = tw * sw.image.height / sw.image.width
        uri = fills.data_uri(sw.image, 360, "JPEG", 84)
        px, py = x0, y0
        if sw.phase is not None and "neck" in shape.anchors and "hem" in shape.anchors:
            # placed: the tile's point sw.phase lands on the centre line PLACE_AT of the way from neck to hem,
            # and the tile is sized against the neck-to-hem length, as it was measured on the garment
            (nx, ny), (hx, hy) = shape.anchors["neck"], shape.anchors["hem"]
            if sw.length_frac:
                tw = sw.length_frac * (hy - ny)
                th = tw * sw.image.height / sw.image.width
            ax, ay = nx + PLACE_AT * (hx - nx), ny + PLACE_AT * (hy - ny)
            row = sorted(d[1] for d in shape.dots if abs(d[0] - nx) < 3)
            if len(row) >= 2:   # buttons down the front: the height is taken along the button run
                ay = row[0] + PLACE_AT * (row[-1] - row[0])
            px, py = ax - sw.phase[0] * tw, ay - sw.phase[1] * th
        img = f'<image href="{uri}" width="{tw + 0.4:.2f}" height="{th + 0.4:.2f}" preserveAspectRatio="none"/>'
        out = (f'<pattern id="p{uid}" patternUnits="userSpaceOnUse" x="{px:.1f}" y="{py:.1f}" width="{tw:.2f}" height="{th:.2f}">'
               f'{img}</pattern>')
        if sw.phase is not None and sw.phase_right is not None and "neck" in shape.anchors:
            # the other front (the viewer's right) has its own placement: on a real shirt the pattern does not
            # line up across the buttons. It shares the tile; only where it starts differs.
            rx, ry = ax - sw.phase_right[0] * tw, ay - sw.phase_right[1] * th
            out += (f'<pattern id="p{uid}r" patternUnits="userSpaceOnUse" x="{rx:.1f}" y="{ry:.1f}" width="{tw:.2f}" '
                    f'height="{th:.2f}">{img}</pattern>')
        return out, f"url(#p{uid})"
    return "", fill.color


# Textures drawn tone-on-tone. `Spec.texture_scale` stretches the spacing (2 = a corduroy wale twice as
# wide, 1.4 = a chunkier knit); "name:scale" is accepted too.
TEXTURES = ("corduroy", "rib_knit", "waffle", "cable_knit", "pique", "mesh", "seersucker", "herringbone", "twill",
            "denim", "fisherman_rib", "garter", "linen", "basket", "tweed", "ripstop", "sherpa", "fleece",
            "quilt_diamond", "quilt_box", "baffle", "moss", "pointelle", "terry",
            # plain weaves and shirtings, each with a faint surface of its own
            "plain", "poplin", "broadcloth", "oxford", "pinpoint", "royal_oxford", "end_on_end", "chambray", "dobby",
            "jacquard", "madras", "voile", "challis", "crepe",
            # the other woven cloths
            "satin", "sateen", "flannel", "brushed_twill", "moleskin", "canvas", "gabardine", "cavalry_twill",
            "whipcord", "fresco", "velvet", "melton", "waxed",
            # jerseys and plain knits
            "jersey", "interlock", "flat_knit", "slub_jersey", "marl", "french_terry", "velour", "shaker",
            # leather and suede
            "leather", "suede")


def _stitches(w: float, h: float, cols: int, rows: int, x0: float = 0.0, y0: float = 0.0) -> str:
    """Path data for a block of knit stitches, each a small V, `cols` across and `rows` down a w x h tile."""
    sw, sh_ = w / cols, h / rows
    return "".join(f"M{x0 + i * sw + sw * .16:.2f},{y0 + j * sh_ + sh_ * .22:.2f}l{sw * .34:.2f},{sh_ * .6:.2f}"
                   f"l{sw * .34:.2f},{-sh_ * .6:.2f}" for i in range(cols) for j in range(rows))


def _texture_defs(texture: str | None, uid: str, dark: bool, scale: float | None = None) -> str:
    """A tone-on-tone surface drawn over the cloth, so corduroy does not look like poplin."""
    lo, hi = ("#fff", "#000") if dark else ("#000", "#fff")
    name, _, s = (texture or "").partition(":")
    scale = s or scale
    try:
        sc = max(0.4, min(3.0, float(scale or 1.0)))
    except ValueError:
        sc = 1.0
    body = _texture_tile(name, sc, lo, hi)
    if not body:
        return ""
    w, h, marks = body
    return (f'<pattern id="t{uid}" patternUnits="userSpaceOnUse" x="{CX_ROT[0]}" y="0" width="{w:.2f}" height="{h:.2f}">'
            f'{marks}</pattern>')


def _texture_tile(name: str, sc: float, lo: str, hi: str):
    """(width, height, marks) of one tile of a surface; sc stretches the spacing (wale, gauge)."""
    if name == "corduroy":
        w = 6 * sc
        return (w, 12, f'<path d="M{w * .25:.2f},0V12" stroke="{lo}" stroke-width="{min(1.2 * sc, 2.6):.2f}" opacity=".24"/>'
                       f'<path d="M{w * .72:.2f},0V12" stroke="{hi}" stroke-width="{min(1.0 * sc, 2.2):.2f}" opacity=".12"/>')
    if name == "rib_knit":
        w = 9 * sc
        return (w, 12, f'<path d="M2,0V12" stroke="{lo}" stroke-width="{1.3 * min(sc, 1.6):.2f}" opacity=".17"/>')
    if name == "waffle":
        w = 7 * sc
        return (w, w, f'<path d="M0,.6H{w:.2f}M.6,0V{w:.2f}" stroke="{lo}" stroke-width="1.1" opacity=".15" fill="none"/>')
    if name == "cable_knit":
        return (34 * sc, 24 * sc, f'<g stroke="{lo}" stroke-width="{1.3 * min(sc, 1.5):.2f}" opacity=".2" fill="none" '
                                  f'transform="scale({sc:.3f})">'
                                  '<path d="M4,0V24M30,0V24"/><path d="M11,0C11,8 23,4 23,12C23,20 11,16 11,24"/>'
                                  '<path d="M23,0C23,8 11,4 11,12C11,20 23,16 23,24"/></g>')
    if name == "pique":      # a fine honeycomb of dimples
        return (4, 4, f'<g fill="{lo}" opacity=".2"><circle cx="1" cy="1" r=".75"/><circle cx="3" cy="3" r=".75"/></g>')
    if name == "moss":       # seed stitch: little purl bumps, each row set half a stitch over from the last
        w = 6 * sc
        return (w, w, f'<path d="M{w * .08:.2f},{w * .25:.2f}h{w * .34:.2f}M{w * .58:.2f},{w * .75:.2f}h{w * .34:.2f}" '
                      f'stroke="{lo}" stroke-width="{1.1 * min(sc, 1.6):.2f}" stroke-linecap="round" opacity=".24"/>')
    if name == "pointelle":  # eyelets set in a lattice of diamonds with plain knit between them
        return (14, 12, f'<g fill="none" stroke="{lo}" stroke-width=".8" opacity=".34"><circle cx="3.5" cy="3" r="1.3"/>'
                        f'<circle cx="10.5" cy="9" r="1.3"/></g>')
    if name == "terry":      # a pile of small loops, row on row
        return (5, 4, f'<path d="M.6,1.6a.95,.95 0 1 1 1.9,0M3.1,3.6a.95,.95 0 1 1 1.9,0" stroke="{lo}" stroke-width=".7" '
                      f'fill="none" opacity=".26"/>')
    if name == "mesh":       # open holes
        return (5, 5, f'<circle cx="2.5" cy="2.5" r="1.1" fill="none" stroke="{lo}" stroke-width=".8" opacity=".3"/>')
    if name == "seersucker":  # puckered stripes between flat ones
        return (12, 6, f'<path d="M0,1.5q1.5,-1.4 3,0t3,0M0,4.5q1.5,-1.4 3,0t3,0" stroke="{lo}" stroke-width=".8" '
                       f'fill="none" opacity=".24"/><path d="M6.4,0V6" stroke="{hi}" stroke-width="5" opacity=".1"/>')
    if name == "herringbone":
        w = 5 * sc
        return (2 * w, w, f'<path d="M0,{w:.2f}L{w:.2f},0M{w:.2f},0L{2 * w:.2f},{w:.2f}" stroke="{lo}" stroke-width=".85" '
                          f'opacity=".2" fill="none"/>')
    if name == "twill":
        return (5, 5, f'<path d="M-1,1L1,-1M0,5L5,0M4,6L6,4" stroke="{lo}" stroke-width=".8" opacity=".15"/>')
    if name == "denim":      # a steep twill with pale weft showing between the lines
        return (4, 4, f'<path d="M-1,1L1,-1M0,4L4,0M3,5L5,3" stroke="{hi}" stroke-width=".9" opacity=".16"/>'
                      f'<path d="M1,4L4,1" stroke="{lo}" stroke-width=".6" opacity=".12"/>')
    if name == "fisherman_rib":   # plump ribs with a knotted stitch
        w = 10 * sc
        return (w, 6 * sc, f'<path d="M.8,0V{6 * sc:.2f}" stroke="{lo}" stroke-width="{1.6 * min(sc, 1.6):.2f}" opacity=".2"/>'
                           f'<path d="M{w * .25:.2f},{sc:.2f}L{w * .55:.2f},{4 * sc:.2f}L{w * .85:.2f},{sc:.2f}" stroke="{lo}" '
                           f'stroke-width=".9" fill="none" opacity=".14"/>')
    if name == "garter":     # ridged rows
        h = 5 * sc
        return (8 * sc, h, f'<path d="M0,{h * .3:.2f}q{2 * sc:.2f},{1.6 * sc:.2f} {4 * sc:.2f},0t{4 * sc:.2f},0" stroke="{lo}" '
                           f'stroke-width="{0.9 * min(sc, 1.6):.2f}" fill="none" opacity=".2"/>')
    if name == "linen":      # slubs: short, uneven streaks
        return (56, 15, f'<path d="M3,3H13M31,4.5H35M14,10.5H20M40,11H50" stroke="{lo}" stroke-width=".8" opacity=".11"/>')
    if name == "basket":     # hopsack, oxford: pairs of threads over pairs
        return (6, 6, f'<path d="M.5,1.3H2.5M.5,2.3H2.5M4,3.5V5.5M5,3.5V5.5" stroke="{lo}" stroke-width=".6" opacity=".2"/>')
    if name == "tweed":      # flecks of other colours
        return (14, 13, f'<g opacity=".28"><circle cx="2" cy="3" r=".7" fill="{lo}"/><circle cx="9" cy="1.5" r=".6" fill="{hi}"/>'
                        f'<circle cx="6" cy="8" r=".7" fill="{lo}"/><circle cx="12" cy="10" r=".6" fill="{hi}"/>'
                        f'<path d="M3,11L5,11.6M10,5L11.5,6.2" stroke="{lo}" stroke-width=".6"/></g>')
    if name == "ripstop":    # a grid of heavier threads
        return (8, 8, f'<path d="M0,.5H8M.5,0V8" stroke="{lo}" stroke-width=".7" opacity=".16"/>')
    if name == "sherpa":     # a curly pile
        return (9, 8, f'<g stroke="{lo}" stroke-width=".9" fill="none" opacity=".26"><path d="M1,3q1.5,-2.4 3,0"/>'
                      f'<path d="M5.5,7q1.5,-2.4 3,0"/><path d="M6,2.6q.8,-1.6 2,-.4"/><path d="M.6,7.4q.8,-1.6 2,-.4"/></g>')
    if name == "fleece":     # a soft nap: faint scattered specks
        return (7, 7, f'<g fill="{lo}" opacity=".12"><circle cx="1.5" cy="2" r=".9"/><circle cx="5" cy="5.5" r=".8"/></g>'
                      f'<circle cx="4.6" cy="1.4" r=".7" fill="{hi}" opacity=".14"/>')
    if name == "quilt_diamond":   # stitched diamonds
        s = 24 * sc
        return (s, s, f'<path d="M0,{s / 2:.2f}L{s / 2:.2f},0L{s:.2f},{s / 2:.2f}L{s / 2:.2f},{s:.2f}Z" stroke="{lo}" '
                      f'stroke-width="1" fill="none" opacity=".34"/>')
    if name == "quilt_box":
        s = 26 * sc
        return (s, s, f'<path d="M0,.5H{s:.2f}M.5,0V{s:.2f}" stroke="{lo}" stroke-width="1" opacity=".32"/>')
    if name == "baffle":     # a puffer's channels: a stitched line, the fill swelling between
        h = 32 * sc
        return (10, h, f'<path d="M0,{h * .5:.2f}H10" stroke="{hi}" stroke-width="{h * .45:.2f}" opacity=".07"/>'
                       f'<path d="M0,.8H10" stroke="{lo}" stroke-width="1.5" opacity=".42"/>')
    return _cloth_tile(name, sc, lo, hi)


def _cloth_tile(name: str, sc: float, lo: str, hi: str):
    """The plain weaves, shirtings, jerseys and the smooth cloths: each a faint surface of its own, big enough
    to show on a closet tile, faint enough that the cloth still reads as plain cloth. White marks are light
    caught by the cloth (a float, a pale weft, a nap) on any colour; `lo` marks are its shade."""
    # ---- plain weaves and shirtings
    if name == "plain":      # one over, one under: a faint check of short dashes
        return (6, 6, f'<path d="M.7,1.5H2.7M3.7,4.5H5.7M4.5,.7V2.7M1.5,3.7V5.7" stroke="{lo}" stroke-width=".7" opacity=".14"/>')
    if name == "poplin":     # fine crosswise cords, broken where the threads cross
        return (10, 5, f'<path d="M0,1.3H4.2M5.4,1.3H10M2.6,3.8H7.8" stroke="{lo}" stroke-width=".7" opacity=".13"/>')
    if name == "broadcloth":  # denser and smoother than poplin: unbroken fine cords and a soft band of lustre
        return (20, 12, f'<path d="M0,1H20M0,4H20M0,7H20M0,10H20" stroke="{lo}" stroke-width=".45" opacity=".1"/>'
                        f'<path d="M0,5.5H20" stroke="#fff" stroke-width="2.2" opacity=".09"/>')
    if name == "oxford":     # a coloured warp over a pale weft, two by two: paired pale flecks, a darker tick between
        return (12, 10, f'<g stroke-width=".9" stroke-linecap="round"><path d="M1,1.5H5M1,3H5M7,6.5H11M7,8H11" '
                        f'stroke="#fff" opacity=".3"/><path d="M8.5,1V3.6M2.5,6V8.6" stroke="{lo}" opacity=".14"/></g>')
    if name == "pinpoint":   # an oxford woven fine: single pale points in a half-drop, a shaded point between
        return (7, 7, f'<g fill="#fff" opacity=".3"><circle cx="1.5" cy="1.5" r=".75"/><circle cx="5" cy="5" r=".75"/></g>'
                      f'<g fill="{lo}" opacity=".12"><circle cx="5" cy="1.5" r=".6"/><circle cx="1.5" cy="5" r=".6"/></g>')
    if name == "royal_oxford":   # a bolder basket with a lustre: pale blocks, a deeper tick between
        return (10, 10, f'<g fill="#fff" opacity=".27"><rect x="1" y="1" width="3.6" height="2.6" rx=".7"/>'
                        f'<rect x="6" y="6" width="3.6" height="2.6" rx=".7"/></g>'
                        f'<path d="M7.8,1V4M2.8,6V9" stroke="{lo}" stroke-width="1" opacity=".15"/>')
    if name == "end_on_end":   # coloured and white warp ends side by side: a fine upright streak, pale and dark
        return (5, 16, f'<path d="M1.2,1V9M3.7,9V15" stroke="#fff" stroke-width=".9" stroke-linecap="round" opacity=".24"/>'
                       f'<path d="M3.7,1V7M1.2,11V15" stroke="{lo}" stroke-width=".7" opacity=".11"/>')
    if name == "chambray":   # a coloured warp and a white weft in a plain weave: a frosty scatter of pale flecks
        return (12, 8, f'<path d="M1,1.5H4M7,2.2H10.5M3,5.5H6.5M8.6,6.6H11" stroke="#fff" stroke-width=".85" '
                       f'stroke-linecap="round" opacity=".26"/><path d="M5,4H6.2M10.6,4.4H11.6" stroke="{lo}" stroke-width=".7" opacity=".12"/>')
    if name == "dobby":      # a small figure woven into the cloth: a tiny diamond with a dot between
        return (12, 12, f'<path d="M6,3L9,6L6,9L3,6Z" fill="none" stroke="{lo}" stroke-width=".7" opacity=".2"/>'
                        f'<g fill="{lo}" opacity=".18"><circle cx="0" cy="0" r=".8"/><circle cx="12" cy="0" r=".8"/>'
                        f'<circle cx="0" cy="12" r=".8"/><circle cx="12" cy="12" r=".8"/></g>')
    if name == "jacquard":   # a larger figure woven tone on tone: leaves in a half-drop
        return (30, 30, f'<g fill="{lo}" opacity=".1"><path d="M8,3C12.5,6 12.5,11 8,14C3.5,11 3.5,6 8,3Z"/>'
                        f'<path d="M23,18C27.5,21 27.5,26 23,29C18.5,26 18.5,21 23,18Z"/></g>'
                        f'<path d="M8,4.5V12.5M23,19.5V27.5" stroke="#fff" stroke-width=".8" opacity=".18"/>')
    if name == "madras":     # a soft check whose bands bleed into each other (the colours come from the photo)
        return (26, 26, f'<g opacity=".1"><rect width="7" height="26" fill="{lo}"/><rect width="26" height="7" fill="{lo}"/></g>'
                        f'<g fill="#fff" opacity=".13"><rect x="14" width="3" height="26"/><rect y="14" width="26" height="3"/></g>'
                        f'<path d="M20.5,0V26M0,20.5H26" stroke="{lo}" stroke-width=".6" opacity=".12"/>')
    if name == "voile":      # sheer: a pale veil over the colour, the odd thicker thread showing through
        return (24, 18, f'<rect width="24" height="18" fill="#fff" opacity=".13"/>'
                        f'<path d="M0,5H24M15,0V18" stroke="{lo}" stroke-width=".5" opacity=".1"/>')
    if name == "challis":    # soft and matte: short fibres lying every way (its print comes from the photo)
        return (11, 10, f'<path d="M1,2l1.7,.6M6.5,1.2l1.3,1M3.5,6.6l1.6,-.5M8.4,7.6l1.4,.7" stroke="{lo}" stroke-width=".75" '
                        f'stroke-linecap="round" opacity=".15"/>')
    if name == "crepe":      # a crinkled, pebbly face
        return (10, 9, f'<path d="M1,2.5q1,-1.4 2,0t2,0M5.5,7q1,-1.4 2,0t2,0M6.5,2.2l1.2,1M1.5,6.2l1.1,-.9" stroke="{lo}" '
                       f'stroke-width=".75" fill="none" stroke-linecap="round" opacity=".19"/>')
    # ---- the other woven cloths
    if name == "satin":      # long bright floats running down the cloth
        return (9, 26, '<path d="M2,1V15M6.5,12V25" stroke="#fff" stroke-width="1" stroke-linecap="round" opacity=".17"/>')
    if name == "sateen":     # the floats run across, softer than satin's
        return (26, 8, f'<path d="M1,2H14M12,6H25" stroke="#fff" stroke-width=".9" stroke-linecap="round" opacity=".14"/>'
                       f'<path d="M17,2H22M3,6H7" stroke="{lo}" stroke-width=".6" opacity=".08"/>')
    if name == "flannel":    # a brushed nap: a soft, cloudy mottle
        return (18, 16, f'<g fill="{lo}" opacity=".07"><ellipse cx="4" cy="4" rx="4" ry="2.6"/><ellipse cx="13" cy="11.5" rx="4.5" ry="2.8"/></g>'
                        f'<g fill="#fff" opacity=".09"><ellipse cx="13" cy="3" rx="3" ry="1.8"/><ellipse cx="5" cy="12" rx="3" ry="1.8"/></g>')
    if name == "brushed_twill":   # a twill whose lines the brushing has softened, with a little nap
        return (7, 7, f'<path d="M-1,1L1,-1M0,7L7,0M6,8L8,6" stroke="{lo}" stroke-width="1.5" opacity=".08"/>'
                      f'<circle cx="2" cy="2.4" r=".7" fill="#fff" opacity=".13"/>')
    if name == "moleskin":   # a dense, sueded face: soft pale brushing and a fine stipple
        return (10, 8, f'<path d="M1,2h3M6,6h3" stroke="#fff" stroke-width="1.7" stroke-linecap="round" opacity=".08"/>'
                       f'<g fill="{lo}" opacity=".12"><circle cx="7" cy="1.6" r=".55"/><circle cx="2.5" cy="5.6" r=".55"/></g>')
    if name == "canvas":     # a coarse plain weave: thick threads over and under
        return (11, 11, f'<path d="M1.2,2.7H4.4M6.7,8.2H9.9" stroke="{lo}" stroke-width="1.8" stroke-linecap="round" opacity=".15"/>'
                        f'<path d="M8.2,1.2V4.4M2.7,6.7V9.9" stroke="{lo}" stroke-width="1.8" stroke-linecap="round" opacity=".09"/>')
    if name == "gabardine":   # a fine, steep twill, tightly packed
        return (4, 8, f'<path d="M0,8L4,0M-1,2L1,-2M3,10L5,6" stroke="{lo}" stroke-width=".7" opacity=".16"/>')
    if name == "cavalry_twill":   # a steep double cord: pairs of lines with a groove between the pairs
        return (10, 10, f'<path d="M0,10L5,0M2.3,10L7.3,0" stroke="{lo}" stroke-width="1" opacity=".16"/>')
    if name == "whipcord":   # one bold steep cord, lit along its edge
        return (8, 12, f'<path d="M0,12L6,0" stroke="{lo}" stroke-width="1.7" opacity=".14"/>'
                       f'<path d="M2,12L8,0" stroke="#fff" stroke-width=".8" opacity=".14"/>')
    if name == "fresco":     # an open, porous weave: small gaps between crisp, twisted threads
        return (12, 12, f'<g fill="{lo}" opacity=".16"><rect x="2" y="2" width="2.6" height="2.6"/>'
                        f'<rect x="8" y="8" width="2.6" height="2.6"/></g>'
                        f'<path d="M0,6.3H12M6.3,0V12" stroke="#fff" stroke-width=".8" opacity=".12"/>')
    if name == "velvet":     # the pile catching the light in soft patches
        return (16, 14, f'<g fill="#fff" opacity=".07"><ellipse cx="4" cy="3.5" rx="3.4" ry="2"/><ellipse cx="12" cy="10.5" rx="3.4" ry="2"/></g>'
                        f'<g fill="{lo}" opacity=".08"><ellipse cx="12" cy="3" rx="2.6" ry="1.6"/><ellipse cx="4" cy="11" rx="2.6" ry="1.6"/></g>')
    if name == "melton":     # felted: no weave to see, only a faint, even stipple
        return (11, 10, f'<g fill="{lo}" opacity=".12"><circle cx="2" cy="2" r=".7"/><circle cx="8" cy="4" r=".7"/>'
                        f'<circle cx="4" cy="8" r=".7"/></g>')
    if name == "waxed":      # waxed cotton: pale creases where the wax has cracked
        return (36, 30, '<path d="M3,6l7,3l5,-2M20,18l6,4l6,-3M8,24l5,-1M26,4l4,3" stroke="#fff" stroke-width="1" fill="none" '
                        'stroke-linecap="round" stroke-linejoin="round" opacity=".15"/>'
                        f'<path d="M3,7l7,3l5,-2M20,19l6,4l6,-3" stroke="{lo}" stroke-width=".6" fill="none" opacity=".08"/>')
    # ---- jerseys and plain knits: knit stitches, each a small V, in columns
    if name == "jersey":
        return (6, 5, f'<path d="{_stitches(6, 5, 1, 1)}" stroke="{lo}" stroke-width=".7" fill="none" opacity=".14"/>')
    if name == "interlock":   # a smooth double knit: the stitches of the second face sit between the first's
        return (10, 7, f'<path d="{_stitches(10, 7, 1, 1)}" stroke="{lo}" stroke-width=".55" fill="none" opacity=".1"/>'
                       f'<path d="M8.6,.5V6.5" stroke="#fff" stroke-width="1.2" opacity=".1"/>')
    if name == "flat_knit":   # a sweater's plain knitting: bigger stitches, scaled by the gauge
        w, h = 8 * sc, 7 * sc
        return (w, h, f'<path d="{_stitches(w, h, 1, 1)}" stroke="{lo}" stroke-width="{0.85 * min(sc, 1.5):.2f}" fill="none" opacity=".15"/>')
    if name == "slub_jersey":   # jersey with thicker, uneven slubs here and there
        return (30, 20, f'<path d="{_stitches(30, 20, 5, 4)}" stroke="{lo}" stroke-width=".6" fill="none" opacity=".1"/>'
                        f'<path d="M2,4.5H9M17,14.5H21" stroke="{lo}" stroke-width="1.4" stroke-linecap="round" opacity=".12"/>')
    if name == "marl":       # heathered or marled yarn: pale and dark flecks scattered over plain knitting
        return (18, 14, f'<path d="{_stitches(18, 14, 1, 1)}" stroke="{lo}" stroke-width=".6" fill="none" opacity=".08"/>'
                        f'<path d="M1.5,2.5H4.5M10,4.5H12.5M5.5,9H8.5M13.5,11.5H16.5M15,1.5H17" stroke="#fff" stroke-width="1.1" '
                        f'stroke-linecap="round" opacity=".32"/><path d="M6.5,3.5H8.5M1,7H3M11,8H13.5M3.5,12.5H5.5" '
                        f'stroke="{lo}" stroke-width="1.1" stroke-linecap="round" opacity=".24"/>')
    if name == "french_terry":   # the smooth jersey face of a heavier cloth (its loops are on the inside)
        return (7, 6, f'<path d="{_stitches(7, 6, 1, 1)}" stroke="{lo}" stroke-width=".75" fill="none" opacity=".13"/>')
    if name == "velour":     # a plush knitted pile: soft upright brush marks
        return (14, 12, f'<path d="M3,1.5v4M10,7.5v3.5" stroke="#fff" stroke-width="2.4" stroke-linecap="round" opacity=".08"/>'
                        f'<path d="M10,1.5v2.5M3,8v3" stroke="{lo}" stroke-width="2" stroke-linecap="round" opacity=".07"/>')
    if name == "shaker":     # plump ribs, each stitch tucked: a rib with a short bar across it
        w, h = 10 * sc, 6 * sc
        return (w, h, f'<path d="M1.2,0V{h:.2f}" stroke="{lo}" stroke-width="{1.6 * min(sc, 1.6):.2f}" opacity=".18"/>'
                      f'<path d="M{w * .42:.2f},{h * .5:.2f}h{w * .34:.2f}" stroke="{lo}" stroke-width="{0.9 * min(sc, 1.6):.2f}" '
                      f'stroke-linecap="round" opacity=".14"/>')
    # ---- leather and suede
    if name == "leather":    # smooth hide: soft creases where it flexes
        return (40, 34, '<path d="M4,8q5,-3 10,0M24,24q5,-3 9,1M28,6q3,2 6,1M6,26q3,-2 6,0" stroke="#fff" stroke-width="1.1" '
                        'fill="none" stroke-linecap="round" opacity=".12"/>'
                        f'<path d="M4,9q5,-3 10,0M24,25q5,-3 9,1" stroke="{lo}" stroke-width=".6" fill="none" opacity=".08"/>')
    if name == "suede":      # a nap: paler where it is brushed one way, darker the other
        return (24, 20, f'<g fill="#fff" opacity=".09"><ellipse cx="6" cy="5" rx="5.5" ry="3"/><ellipse cx="18" cy="15" rx="5" ry="3"/></g>'
                        f'<g fill="{lo}" opacity=".08"><ellipse cx="18" cy="4.5" rx="4" ry="2.4"/><ellipse cx="6" cy="15.5" rx="4" ry="2.4"/></g>')
    return None


def _motif_colors(base: str, colors) -> tuple[str, str]:
    """The colourwork's two colours: the other colours seen where they stand out from the cloth, else a pale
    cream on a dark cloth and a deep shade on a light one, with a colour between the two for the second."""
    seen = [c for c in (colors or ()) if isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c)
            and contrast(c, base) >= 1.35]
    c1 = seen[0] if seen else ("#efe6d2" if luminance(base) < 0.42 else shade(base, -0.34))
    c2 = seen[1] if len(seen) > 1 else _over(base, c1, 0.55)
    return c1, c2


def _ring(k: float, n_per: float = 14.0):
    """Points round the neck at `k` beyond the neckline: an oval sitting on the shoulders, as a round yoke
    lies when the sweater is laid flat. Spaced about `n_per` apart, from shoulder to shoulder through the front."""
    cx, cy, rx, ry = CX, 52.0, 35.0 + k, 40.0 + k * 0.9
    steps = max(6, int(math.pi * (rx + ry) / 2 / n_per))
    pts = []
    for i in range(-steps, steps + 1):
        t = math.pi / 2 + math.pi * i / steps * 0.62   # the front half and round onto the shoulders
        pts.append((cx + rx * math.cos(t), cy + ry * math.sin(t)))
    return pts, (cx, cy, rx, ry)


def _diamond(x: float, y: float, r: float) -> str:
    return f"M{x:.1f},{y - r:.1f}L{x + r:.1f},{y:.1f}L{x:.1f},{y + r:.1f}L{x - r:.1f},{y:.1f}Z"


def _colorwork(kind: str, shape: Shape, base: str, colors, uid: str) -> str:
    """A knitted-in colour pattern, placed where the garment carries it: a Fair Isle or Nordic yoke round the
    neck, argyle diamonds down the front, an intarsia picture on the chest, Cowichan bands, a jacquard all
    over, a guernsey's tone-on-tone yoke panel. Drawn on the body, under its seams, ribbing and parts."""
    c1, c2 = _motif_colors(base, colors)
    x0, sy, x1, hy = shape.body_box
    low = hy - 8 * K_PX    # above a ribbed hem
    out: list[str] = []

    def oval(k, colour, width):
        _, (cx, cy, rx, ry) = _ring(k)
        return (f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="none" stroke="{colour}" '
                f'stroke-width="{width}"/>')

    def border(y0, y1):   # a band across the body above the hem: two rules and a row of small diamonds
        h = y1 - y0
        row = "".join(_diamond(x, (y0 + y1) / 2, h * 0.3) for x in _range(x0 - 60, x1 + 60, h * 0.95))
        return (f'<path d="M0,{y0:.1f}H{W}M0,{y1:.1f}H{W}" stroke="{c1}" stroke-width="3.2"/>'
                f'<path d="{row}" fill="{c2}"/>')

    if kind in ("fair_isle", "nordic"):
        if kind == "nordic":   # lice: single stitches of the contrast over body and sleeves, below the yoke
            _, (cx, cy, rx, ry) = _ring(66)
            dots = "".join(f'<rect x="{x - 1.6:.1f}" y="{y - 1.6:.1f}" width="3.2" height="3.2"/>'
                           for j, y in enumerate(_range(sy + 4, low - 4, 15))
                           for x in _range(-20 + (j % 2) * 9, W + 20, 18)
                           if ((x - cx) / (rx + 5)) ** 2 + ((y - cy) / (ry + 5)) ** 2 > 1)
            out.append(f'<g fill="{c1}">{dots}</g>')
            out += [oval(8, c1, 3.6), oval(64, c1, 3.6), oval(58, c2, 2.2)]
            pts, _ = _ring(34, 26)
            out.append(f'<g fill="{c1}">' + "".join(_star(x, y, 11.5) for x, y in pts) + "</g>")
            pts, _ = _ring(34, 26)
            out.append(f'<g fill="{c2}">' + "".join(_diamond(x, y, 2.6) for x, y in pts) + "</g>")
        else:   # peerie and OXO bands round the yoke, and a border above the hem
            out += [oval(8, c1, 3.6), oval(30, c2, 3.4), oval(48, c1, 3.6), oval(66, c2, 3.2)]
            pts, _ = _ring(19, 13)
            out.append(f'<g fill="{c1}">' + "".join(_diamond(x, y, 5.6) for x, y in pts[::2]) + "</g>")
            out.append(f'<g stroke="{c1}" stroke-width="2.2">' + "".join(
                f'<path d="M{x - 4:.1f},{y - 4:.1f}l8,8M{x + 4:.1f},{y - 4:.1f}l-8,8"/>' for x, y in pts[1::2]) + "</g>")
            pts, _ = _ring(39, 10)
            out.append(f'<g fill="{c2}">' + "".join(_diamond(x, y, 3.4) for x, y in pts) + "</g>")
            pts, _ = _ring(57, 11)
            out.append(f'<g fill="{c1}">' + "".join(
                f'<path d="M{x - 3.6:.1f},{y + 2.6:.1f}L{x:.1f},{y - 3:.1f}L{x + 3.6:.1f},{y + 2.6:.1f}Z"/>' for x, y in pts) + "</g>")
            out.append(border(low - 24, low - 6))
    elif kind == "argyle":   # diamonds down the front and back; the sleeves are plain
        dw, dh = (x1 - x0) / 3, (x1 - x0) / 3 * 1.36
        top = sy - dh * 0.25
        cells, check = [], []
        for j in range(-1, int((low - top) / dh) + 2):
            for i in range(-2, 3):
                cx_, cy_ = CX + i * dw, top + j * dh
                cells.append(f"M{cx_:.1f},{cy_ - dh / 2:.1f}L{cx_ + dw / 2:.1f},{cy_:.1f}L{cx_:.1f},{cy_ + dh / 2:.1f}"
                             f"L{cx_ - dw / 2:.1f},{cy_:.1f}Z")
        for i in range(-8, 9):   # the overcheck: thin lines through the middles of the diamonds, both ways
            xa, ya = CX + i * dw, top - 2 * dh
            check.append(f"M{xa:.1f},{ya:.1f}l{dw * 8:.1f},{dh * 8:.1f}M{xa:.1f},{ya:.1f}l{-dw * 8:.1f},{dh * 8:.1f}")
        out.append(f'<clipPath id="ab{uid}"><rect x="{x0:.1f}" y="0" width="{x1 - x0:.1f}" height="{low:.1f}"/></clipPath>'
                   f'<g clip-path="url(#ab{uid})"><path d="{"".join(cells)}" fill="{c1}"/>'
                   f'<path d="{"".join(check)}" stroke="{c2}" stroke-width="1.6" fill="none" stroke-dasharray="5 3"/></g>')
    elif kind == "intarsia":   # one large picture knitted into the chest, in blocks of colour
        cell = 10.0
        rows = ("...X...", "..XXX..", ".XXOXX.", "XXOOOXX", ".XXOXX.", "..XXX..", "...X...")
        ox, oy = CX - 3.5 * cell, sy + 30
        out.append(f'<g fill="{c1}">' + "".join(f'<rect x="{ox + i * cell:.1f}" y="{oy + j * cell:.1f}" width="{cell + .3}" height="{cell + .3}"/>'
                   for j, r in enumerate(rows) for i, ch in enumerate(r) if ch == "X") + "</g>")
        out.append(f'<g fill="{c2}">' + "".join(f'<rect x="{ox + i * cell:.1f}" y="{oy + j * cell:.1f}" width="{cell + .3}" height="{cell + .3}"/>'
                   for j, r in enumerate(rows) for i, ch in enumerate(r) if ch == "O") + "</g>")
    elif kind == "jacquard_knit":   # a small two-colour figure repeated all over
        motif = "".join(_diamond(x + (j % 2) * 11, y, 4.2) for j, y in enumerate(_range(sy - 10, low - 2, 15))
                        for x in _range(-11, W + 11, 22))
        dots = "".join(f'<rect x="{x + (j % 2) * 11 + 9.5:.1f}" y="{y - 1.6:.1f}" width="3.2" height="3.2"/>'
                       for j, y in enumerate(_range(sy - 10, low - 2, 15)) for x in _range(-11, W + 11, 22))
        out.append(f'<path d="{motif}" fill="{c1}"/><g fill="{c2}">{dots}</g>')
    elif kind == "cowichan":   # bold bands across chest and lower body, round the sleeves too
        ya, yb = sy + 38, sy + 64
        zig = f"M-20,{yb - 4:.1f}" + "".join(
            f"L{x + 9:.1f},{ya + 4:.1f}L{x + 18:.1f},{yb - 4:.1f}" for x in _range(-20, W + 20, 18))
        out.append(f'<path d="M0,{ya:.1f}H{W}M0,{yb:.1f}H{W}" stroke="{c1}" stroke-width="3.6"/>'
                   f'<path d="{zig}" fill="none" stroke="{c1}" stroke-width="4.2" stroke-linejoin="miter"/>')
        y0, y1 = low - 40, low - 12
        steps = "".join(f'<path d="M{x:.1f},{y1:.1f}V{(y0 + y1) / 2:.1f}H{x + 8:.1f}V{y0 + 4:.1f}H{x + 16:.1f}'
                        f'V{(y0 + y1) / 2:.1f}H{x + 24:.1f}V{y1:.1f}Z"/>' for x in _range(-24, W + 24, 34))
        out.append(f'<g fill="{c1}">{steps}</g><path d="M0,{y0:.1f}H{W}M0,{y1 + 2:.1f}H{W}" stroke="{c2}" stroke-width="3"/>')
    elif kind == "guernsey":   # a yoke panel of knit-and-purl patterning, tone on tone, above a plain body
        tone = shade(base, 0.14 if luminance(base) < 0.3 else -0.14)
        ya = sy + 46
        ridges = "".join(f"M0,{y:.1f}H{W}" for y in _range(sy - 6, ya, 6))
        out.append(f'<g opacity=".55"><path d="{ridges}" stroke="{tone}" stroke-width="2"/>'
                   f'<path d="M0,{ya + 2:.1f}H{W}" stroke="{tone}" stroke-width="3"/>'
                   f'<path d="{"".join(_diamond(x, ya + 13, 7) for x in _range(-10, W + 10, 20))}" fill="none" '
                   f'stroke="{tone}" stroke-width="2"/><path d="M0,{ya + 24:.1f}H{W}" stroke="{tone}" stroke-width="3"/></g>')
    return "".join(out)


def _range(a: float, b: float, step: float):
    v = a
    while v <= b:
        yield v
        v += step


def _star(x: float, y: float, r: float) -> str:
    """A Selbu star: eight petals, each a small diamond pointing out from the middle."""
    d = []
    for i in range(8):
        t = math.pi / 4 * i
        px, py = x + r * 0.55 * math.cos(t), y + r * 0.55 * math.sin(t)
        ux, uy, vx, vy = math.cos(t) * r * .45, math.sin(t) * r * .45, -math.sin(t) * r * .17, math.cos(t) * r * .17
        d.append(f"M{px - ux:.1f},{py - uy:.1f}L{px + vx:.1f},{py + vy:.1f}L{px + ux:.1f},{py + uy:.1f}L{px - vx:.1f},{py - vy:.1f}Z")
    return f'<path d="{"".join(d)}"/>'


def _graphic_markup(g: fills.Graphic | None, box: tuple[float, float, float, float], clip: str) -> str:
    if not g:
        return ""
    x0, y0, x1, y1 = box
    gw = g.width * (x1 - x0)
    gh = gw * g.image.height / g.image.width
    gx = x0 + g.cx * (x1 - x0) - gw / 2
    gy = y0 + g.top * (y1 - y0)
    uri = fills.data_uri(g.image, 420, "PNG")
    return (f'<image href="{uri}" x="{gx:.1f}" y="{gy:.1f}" width="{gw:.1f}" height="{gh:.1f}" '
            f'clip-path="url(#{clip})" preserveAspectRatio="xMidYMid meet"/>')


# How far a cloth stands off what lies under it, in px, by weight (lightweight, midweight,
# heavyweight, super heavy). A thick cloth is drawn with depth: shade inside its lower and
# right edges, seams that sink into it, and a collar and pockets that stand proud of the body.
DEPTH_PX = (0, 0, 5, 9)


def _svg(body: str, defs: str, card: bool = True) -> str:
    bg = f'<rect width="{W}" height="{H}" rx="18" fill="{CARD}"/>' if card else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">'
            f"<defs>{defs}</defs>{bg}{body}</svg>")


def render(spec: Spec, style: str, cutout: Image.Image | None = None, uid: str = "a") -> str:
    if style == "traced":
        if cutout is None:
            raise ValueError("traced style needs the cutout")
        return _render_traced(spec, cutout, uid)
    defs, body, _, _ = _draw(spec, style, uid)
    return _svg(body, defs)


def layer(under: Spec, over: Spec, style: str, uid: str = "a") -> str:
    """A garment worn open over another: both placed by the same points on the wearer. From the back forward:
    the inside of the outer garment's back, the whole garment underneath, then the outer garment's two fronts
    and sleeves. The one underneath is hidden where the outer garment's sleeves would cover it."""
    o_defs, o_body, dy, opening = _draw(over, style, uid + "o", layered=True)
    u_defs, u_body, _, _ = _draw(under, style, uid + "u", dy=dy)
    if not opening:   # the outer garment is closed: it simply covers the one underneath
        return _svg(u_body + o_body, u_defs + o_defs)
    o_back, o_fronts = o_body
    seen = f'<clipPath id="w{uid}">' + "".join(f'<path d="{d}" transform="translate(0 {dy:.1f})"/>' for d in opening) + "</clipPath>"
    return _svg(o_back + f'<g clip-path="url(#w{uid})">{u_body}</g>' + o_fronts, u_defs + o_defs + seen)


def _draw(spec: Spec, style: str, uid: str, layered: bool = False, dy: float | None = None):
    """The markup for one garment: (defs, body, the vertical shift it was placed with, and, when it is worn
    open, the paths within which a garment underneath can show). With `layered`, an open garment's body comes
    back in two pieces, (the inside of its back, its two fronts), so another garment can be drawn between."""
    params = spec.params if not spec.weight or "weight" in spec.params else {**spec.params, "weight": spec.weight}
    shape = build(spec.template, params)
    bx0, by0, bx1, by1 = shape.bbox
    gw, gh = bx1 - bx0, by1 - by0
    # centre the garment vertically on the card (unless it is placed with another garment's shift)
    dy = (H - gh) / 2 - by0 if dy is None else dy
    defs, paint = _defs_for_fill(spec.fill, shape, uid, gw, gh)
    base = spec.fill.color
    dark_item = luminance(base) < 0.3
    tone = shade(base, 0.16 if dark_item else -0.16)
    in_c, in_op = inside_tint(base) if shape.tailored else ("#000", ".22")   # the inside: the back, the neck
    clip = f"c{uid}"
    defs += f'<clipPath id="{clip}"><path d="{shape.outline}"/></clipPath>'
    patterned = paint.startswith("url(")
    tex_defs = _texture_defs(spec.texture, uid, dark_item, spec.texture_scale)
    defs += tex_defs

    trim_paint = None
    if patterned and spec.fill.trim_stripes:
        tdefs, trim_paint = _defs_for_fill(Fill("stripes", spec.fill.color, stripes=spec.fill.trim_stripes), shape,
                                           f"{uid}g", gw, gh)
        defs += tdefs

    def turned(name: str, degrees: float, ground: bool = False) -> str:
        """The same cloth turned by an angle (sleeves hang at an angle; collar leaves are cut on a slant).
        ground=True: the collar's plain cloth (`Fill.trim_stripes`) when there is one."""
        nonlocal defs
        if not patterned:
            return paint
        if ground and trim_paint:
            defs += (f'<pattern id="p{uid}g{name}" href="#p{uid}g" '
                     f'patternTransform="rotate({degrees:.1f} {CX_ROT[0]} {CX_ROT[1]})"/>')
            return f"url(#p{uid}g{name})"
        defs += (f'<pattern id="p{uid}{name}" href="#p{uid}" '
                 f'patternTransform="rotate({degrees:.1f} {CX_ROT[0]} {CX_ROT[1]})"/>')
        return f"url(#p{uid}{name})"

    def collar_turn(d: str, role: str) -> float:
        """How far to turn the cloth on a collar leaf. A collar is cut with its cloth running round the neck,
        so on each leaf the stripes run along the leaf, from where it leaves the neck to its point, whichever
        way they run on the body."""
        st = spec.fill.stripes if spec.fill.kind == "stripes" else None
        nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", d)]
        pts = np.array(list(zip(nums[0::2], nums[1::2])))
        if len(pts) < 3:
            return -24 if role.endswith("_r") else 24
        # the leaf's line: from its outer corner (where it leaves the side of the neck: the point furthest
        # from the centre in the leaf's upper half) to its lowest corner (the collar point)
        tip = pts[np.argmax(pts[:, 1])]
        upper = pts[pts[:, 1] <= (pts[:, 1].min() + pts[:, 1].max()) / 2]
        outer = upper[np.argmax(np.abs(upper[:, 0] - CX_ROT[0]))]
        vx, vy = tip - outer
        n_ = float(np.hypot(vx, vy)) or 1.0
        vx, vy = vx / n_, vy / n_
        if st is not None and st.orientation == "horizontal":
            return float(np.degrees(np.arctan2(vy, vx)))     # turns (1, 0) onto the leaf
        return float(np.degrees(np.arctan2(-vx, vy)))        # turns (0, 1) onto the leaf

    if style == "flat":
        o_stroke, o_w, l_stroke, l_w, l_op = "none", 0, ("#ffffff" if dark_item else "#000000"), 2.2, 0.22
        if luminance(base) > 0.72:  # pale items need an edge to stand off the card
            o_stroke, o_w = shade(base, -0.2), 1.6
    elif style == "line":
        # a bold edge and inner lines about a third of its weight, as in a fashion flat;
        # on a dark cloth the inner lines are a lighter tone of it, since ink would vanish
        o_stroke, o_w, l_stroke, l_w, l_op = INK, 3.8, (shade(base, 0.42) if dark_item else INK), 1.5, 0.95
    else:  # soft
        o_stroke, o_w, l_stroke, l_w, l_op = shade(base, 0.2 if dark_item else -0.28), 2.4, shade(base, 0.2 if dark_item else -0.28), 1.8, 0.7
        defs += (f'<linearGradient id="g{uid}" x1="0" y1="0" x2="1" y2="1">'
                 '<stop offset="0" stop-color="#fff" stop-opacity=".22"/><stop offset=".5" stop-color="#fff" stop-opacity="0"/>'
                 '<stop offset="1" stop-color="#000" stop-opacity=".2"/></linearGradient>'
                 f'<filter id="s{uid}" x="-10%" y="-10%" width="120%" height="130%">'
                 '<feDropShadow dx="0" dy="6" stdDeviation="7" flood-color="#000" flood-opacity=".18"/></filter>')

    # A fine cloth is drawn with a finer line. A heavy one is only a little bolder: its
    # thickness is shown as depth (see DEPTH_PX), which reads as cloth where a bold line does not.
    ow_k, lw_k = {"lightweight": (0.8, 0.88), "heavyweight": (1.07, 1.03), "super_heavy": (1.14, 1.06)}.get(spec.weight or "", (1.0, 1.0))
    o_w, l_w = o_w * ow_k, l_w * lw_k
    # On a patterned cloth, seams drawn tone-on-tone disappear. There they are
    # drawn darker over a pale halo, and the garment gets an edge in every style.
    if patterned:
        l_stroke, l_op = (INK if style == "line" else shade(base, -0.42)), (0.95 if style == "line" else 0.85)
        l_w = max(l_w, 1.8)
        if not o_w:
            o_stroke, o_w = shade(base, -0.38), 2.2
    halo = (lambda d, extra=2.2: f'<path d="{d}" fill="none" stroke="#fff" stroke-width="{l_w + extra}" stroke-linecap="round" '
            f'stroke-linejoin="round" opacity=".32"/>') if patterned else (lambda d, extra=0: "")

    def thin(d: str) -> str:
        return (f'<path d="{d}" fill="none" stroke="{l_stroke}" stroke-width="{l_w}" stroke-linecap="round" '
                f'stroke-linejoin="round" opacity="{l_op}"/>')

    sole_c = spec.sole_color or shape.sole_default or "#f4f1ea"

    # colour-blocking and binding: the second colour, and the strip wrapped over the edges
    bpaint = spec.block_color or shade(base, 0.3 if dark_item else -0.3)
    bound = any(part.role in ("binding", "binding_edge") for part in shape.parts)
    bind_c = spec.trim_color or shade(base, 0.32 if dark_item else -0.32)

    def part_color(key):
        return {"trim": spec.trim_color, "lace": spec.lace_color, "sole": sole_c, "sole_line": None,
                "sole_dark": shade(sole_c, -0.35 if luminance(sole_c) > 0.25 else 0.2),   # an outsole under a sandal's footbed
                "sole_lug": shade(sole_c, -0.62 if luminance(sole_c) > 0.25 else 0.25),   # the blocks of a lug sole
                "deep": shade(base, 0.14 if luminance(base) < 0.1 else -0.15)}.get(key, key)   # deep: the same leather, in shadow

    def overlay(d: str, role: str, color: str | None = None) -> str:
        if role == "edge":   # a line with no fill, e.g. the visible edges of a collar
            if color == "sole_line":   # a line on the sole (foxing stripe, heel lift): a darker tone of the sole, not the upper's
                c = shade(sole_c, -0.3 if luminance(sole_c) > 0.25 else 0.22)
                return f'<path d="{d}" fill="none" stroke="{c}" stroke-width="{l_w}" stroke-linecap="round"/>'
            return halo(d, 2.4) + thin(d)
        if role in ("binding", "binding_edge"):   # a strip over an edge; on the outline, half of it is cut off
            w = 5.0 if role == "binding" else 10.0
            return (f'<path d="{d}" fill="none" stroke="{l_stroke}" stroke-width="{w + 2 * l_w:.1f}" stroke-linecap="round" '
                    f'stroke-linejoin="round" opacity="{l_op}"/>'
                    f'<path d="{d}" fill="none" stroke="{bind_c}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round"/>')
        if role == "block":   # a piece cut in the second colour (a pocket)
            return f'<path d="{d}" fill="{bpaint}"/>'
        if role in ("collar_r", "collar_l") and color == "block":
            return f'<path d="{d}" fill="{spec.collar_color or bpaint}"/>'
        if role in ("lapel_r", "lapel_l") and color == "block":
            return f'<path d="{d}" fill="{spec.collar_color or bpaint}"/>' + (f'<path d="{d}" fill="url(#t{uid})"/>' if tex_defs else "")
        if role in ("collar_r", "collar_l"):
            # the same cloth as the body (turned, when patterned); its edges are a separate "edge" part
            if spec.collar_color or (spec.trim_color and not bound):
                return f'<path d="{d}" fill="{spec.collar_color or spec.trim_color}"/>'
            return f'<path d="{d}" fill="{turned(role[-1] + "c", collar_turn(d, role), ground=True)}"/>'
        if role in ("lapel_r", "lapel_l"):
            # a tailored jacket's collar and lapels: cut from the body's cloth, so they carry its surface too
            fill = spec.collar_color or (spec.trim_color if not bound else None) or turned(role[-1], -24 if role == "lapel_r" else 24)
            # the lapel is the facing turned back: on a dark or patterned cloth its edges alone are lost, so a
            # shade sets it off the body (lighter on a dark plain cloth, darker on a pattern)
            facing = (f'<path d="{d}" fill="{"#fff" if dark_item and not patterned else "#000"}" '
                      f'opacity="{0.09 if dark_item and not patterned else 0.26}"/>') if (dark_item or patterned) else ""
            return (f'<path d="{d}" fill="{fill}"/>' + (f'<path d="{d}" fill="url(#t{uid})"/>' if tex_defs else "")
                    + facing)
        if role == "neckrib":   # the rib of a crew neck: only painted when it is a contrast colour
            return f'<path d="{d}" fill="{spec.trim_color}"/>' if spec.trim_color else ""
        if role == "stitch":   # topstitching in its own thread colour: dashed, never ink
            c = part_color(color) or "#c9973f"
            if color == "sole_line":
                c = shade(sole_c, -0.25 if luminance(sole_c) > 0.25 else 0.22)
            return f'<path d="{d}" fill="none" stroke="{c}" stroke-width="1.3" stroke-dasharray="3.2 2.4" stroke-linecap="round"/>'
        if role == "punch":    # brogue punching: a row of small holes along a seam
            c = shade(base, 0.3 if luminance(base) < 0.3 else -0.32)   # holes show the darker lining, or catch light on black
            return (f'<path d="{d}" fill="none" stroke="{c}" stroke-width="3.1" stroke-dasharray="0 4.8" '
                    f'stroke-linecap="round"/>')
        if role == "inlay":    # a piece in its own colour (lace, rubber toe, contrast panel); body cloth when none is given
            c = part_color(color)
            body = f'<path d="{d}" fill="{c}"/>' if c else (f'<path d="{d}" fill="{paint}"/>'
                                                           f'<path d="{d}" fill="{"#fff" if dark_item else "#000"}" opacity=".08"/>')
            return body + f'<path d="{d}" fill="none" stroke="{l_stroke if style != "flat" else shade(c or base, -0.3)}" stroke-width="{l_w}" stroke-linejoin="round" opacity="{l_op}"/>'
        if role == "shine":    # a hard gloss (patent leather): a bright streak, no edge
            return f'<path d="{d}" fill="#fff" opacity=".6"/>'
        if role == "fade":     # cloth worn paler (denim whiskers, a knee): a soft light wash over it, no edge
            op = 0.2 if dark_item else 0.3
            if color == "soft":   # palest in the middle, fading out to nothing at its edge
                nonlocal defs
                if f'id="f{uid}"' not in defs:
                    defs += (f'<radialGradient id="f{uid}"><stop offset="0" stop-color="#fff" stop-opacity="{op * 1.4:.2f}"/>'
                             f'<stop offset=".5" stop-color="#fff" stop-opacity="{op * 0.8:.2f}"/>'
                             f'<stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>')
                return f'<path d="{d}" fill="url(#f{uid})"/>'
            return f'<path d="{d}" fill="#fff" opacity="{op:.2f}"/>'
        if role == "sole":
            c = sole_c
            return f'<path d="{d}" fill="{c}"/>' + (f'<path d="{d}" fill="#000" opacity=".06"/>' if style != "line" else "")
        if role == "hole":
            # inside the neck of a top, what shows is mostly the collar band, whose cloth runs round the neck
            inner = paint if color != "block" else bpaint
            if patterned and spec.template == "top" and color != "block":
                st = spec.fill.stripes if spec.fill.kind == "stripes" else None
                inner = turned("hn", 0 if (st is not None and st.orientation == "horizontal") else 90, ground=True)
            return f'<path d="{d}" fill="{inner}"/><path d="{d}" fill="{in_c}" opacity="{in_op}"/>'
        # a shirt cuff is the body's own cloth: no tint where a line already marks it
        op = {"trim": 0.10, "band": 0.12, "cuff": 0.0 if style == "line" else 0.06}.get(role, 0.1)
        col = "#fff" if dark_item else "#000"
        if color == "block" and role in ("band", "cuff"):
            out = f'<path d="{d}" fill="{bpaint}"/>' + (f'<path d="{d}" fill="{col}" opacity="{op}"/>' if op else "")
        elif spec.trim_color and role in ("band", "cuff") and not bound:
            out = f'<path d="{d}" fill="{spec.trim_color}"/>'
        elif role == "cuff" and patterned and shape.sleeves:
            # a cuff wraps round the wrist: its cloth runs across its own sleeve's
            xs = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", d)[0::2]]
            n = 0 if (sum(xs) / max(1, len(xs))) >= CX_ROT[0] else 1
            out = f'<path d="{d}" fill="{turned(f"c{n}", shape.sleeves[n][1] + 90, ground=spec.fill.sleeves_from_trim)}"/>'
        else:
            out = f'<path d="{d}" fill="{paint}"/>' + (f'<path d="{d}" fill="{col}" opacity="{op}"/>' if op else "")
        if style in ("line", "soft"):
            out += f'<path d="{d}" fill="none" stroke="{l_stroke}" stroke-width="{l_w}" stroke-linejoin="round" opacity="{l_op}"/>'
        return out

    g = [f'<g transform="translate(0 {dy:.1f})"' + (f' filter="url(#s{uid})"' if style == "soft" else "") + ">"]
    wt = {"lightweight": 0, "midweight": 1, "heavyweight": 2, "super_heavy": 3}.get(params.get("weight"), 1)
    depth = DEPTH_PX[wt] if spec.template == "top" else 0
    # always a darker tone of the cloth (a lighter one reads as gloss); the darker the cloth, the more it takes to show
    d_col, d_op = "#000", (0.42 if dark_item else 0.22 if luminance(base) < 0.55 else 0.14)
    if depth and any(part.role == "band" for part in shape.parts):   # the soft shade a thick knit casts on its rib
        defs += (f'<filter id="r{uid}" filterUnits="userSpaceOnUse" x="-50" y="-100" width="500" height="700">'
                 f'<feGaussianBlur stdDeviation="{depth * 0.6:.1f}"/></filter>')
    behind = "".join(overlay(part.d, part.role, part.color) for part in shape.behind)
    if not shape.fronts:
        g.append(behind)
    # the garment body; a same-paint stroke rounds the corners in the flat style
    round_stroke = f' stroke="{paint}" stroke-width="5" stroke-linejoin="round"' if style == "flat" and not patterned else ""
    g.append(f'<path d="{shape.outline}" fill="{paint}"{round_stroke}/>')
    sw_ = spec.fill.swatch if spec.fill.kind == "swatch" else None
    if sw_ is not None and sw_.phase is not None and sw_.phase_right is not None and "neck" in shape.anchors:
        cxn = shape.anchors["neck"][0]
        defs += f'<clipPath id="fr{uid}"><rect x="{cxn:.1f}" y="0" width="{W}" height="{H}"/></clipPath>'
        g.append(f'<path d="{shape.outline}" fill="url(#p{uid}r)" clip-path="url(#fr{uid})"/>')
    if patterned and not shape.block_sleeves:
        # placed stripes (a polo's chest bands) are on the body only: sleeves are cut from the plain ground
        for n, (d, degrees) in enumerate(shape.sleeves):
            g.append(f'<path d="{d}" fill="{turned(f"s{n}", degrees, ground=spec.fill.sleeves_from_trim)}"/>')
    if shape.blocks:   # a yoke in the second colour, cut by the garment's edge
        g.append(f'<g clip-path="url(#{clip})">' + "".join(f'<path d="{d}" fill="{bpaint}"/>' for d in shape.blocks) + "</g>")
    if shape.block_sleeves:
        g += [f'<path d="{d}" fill="{bpaint}"/>' for d, _ in shape.sleeves]
    if tex_defs:   # the surface runs down the body and along each sleeve
        g.append(f'<path d="{shape.outline}" fill="url(#t{uid})"/>')
        for n, (d, degrees) in enumerate(shape.sleeves):
            defs += (f'<pattern id="t{uid}s{n}" href="#t{uid}" '
                     f'patternTransform="rotate({degrees:.1f} {CX_ROT[0]} {CX_ROT[1]})"/>')
            g.append(f'<path d="{d}" fill="{bpaint if shape.block_sleeves else paint if not patterned else turned(f"s{n}", degrees, ground=spec.fill.sleeves_from_trim)}"/>'
                     f'<path d="{d}" fill="url(#t{uid}s{n})"/>')
    if spec.colorwork and not patterned and spec.template == "top":   # a photo's fill already carries the pattern
        g.append(f'<g clip-path="url(#{clip})">{_colorwork(spec.colorwork, shape, base, spec.motif_colors, uid)}</g>')
    if spec.sheen and not patterned:   # one soft highlight across the chest
        defs += (f'<linearGradient id="h{uid}" x1="0" y1="0" x2="1" y2="1">'
                 '<stop offset=".2" stop-color="#fff" stop-opacity="0"/><stop offset=".34" stop-color="#fff" stop-opacity=".16"/>'
                 '<stop offset=".48" stop-color="#fff" stop-opacity="0"/></linearGradient>')
        g.append(f'<path d="{shape.outline}" fill="url(#h{uid})"/>')
    if depth:   # a thick cloth has volume: a band of shade inside its lower and right edges
        a, b = depth * 0.9, depth * 1.5
        defs += (f'<mask id="m{uid}" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}"><rect width="{W}" height="{H}" fill="#fff"/>'
                 f'<path d="{shape.outline}" transform="translate({-a:.1f} {-b:.1f})" fill="#000"/></mask>')
        g.append(f'<path d="{shape.outline}" fill="{d_col}" opacity="{d_op + 0.03:.2f}" mask="url(#m{uid})"/>')
    # seams lie on the body, under anything folded over it (a collar covers the top of the placket)
    g.append(f'<g clip-path="url(#{clip})">')
    # a seam sinks into a thick cloth: a soft band of shade beside it
    sunk = (lambda d: f'<path d="{d}" transform="translate({depth * 0.3:.1f} {depth * 0.55:.1f})" fill="none" '
            f'stroke="{d_col}" stroke-width="{depth * 1.1:.1f}" stroke-linecap="round" stroke-linejoin="round" '
            f'opacity="{d_op - 0.02:.2f}"/>') if depth else (lambda d: "")
    for d in shape.seams:
        g.append(sunk(d))
    for d in shape.seams:
        g.append(halo(d))
    for d in shape.seams:
        g.append(thin(d))
    for d in shape.folds:   # a light cloth's drape: finer and fainter than a seam
        g.append(f'<path d="{d}" fill="none" stroke="{l_stroke}" stroke-width="{l_w * 0.8:.2f}" stroke-linecap="round" '
                 f'opacity="{l_op * 0.6:.2f}"/>')
    g.append("</g>")
    top_side, behind_neck = [], []   # worn open: the top front's collar and lapel; pieces behind the neck
    for part in shape.parts:   # parts marked clip are cut by the garment's edge (laces, a rubber toe)
        piece = overlay(part.d, part.role, part.color)
        if depth and part.role in ("collar_r", "collar_l", "trim"):   # a thick piece stands proud of the body
            piece = (f'<g clip-path="url(#{clip})"><path d="{part.d}" transform="translate({depth * 0.35:.1f} {depth * 0.8:.1f})" '
                     f'fill="{d_col}" opacity="{d_op + 0.05:.2f}"/></g>') + piece
        elif depth and part.role == "band":   # a thick knit blouses over its rib: a soft shade along the rib's edge
            piece = (f'<g clip-path="url(#{clip})"><path d="{part.d}" fill="none" stroke="{d_col}" stroke-width="{depth * 2.6:.1f}" '
                     f'stroke-linejoin="round" opacity="{min(0.5, d_op + 0.15):.2f}" filter="url(#r{uid})"/></g>') + piece
        piece = f'<g clip-path="url(#{clip})">{piece}</g>' if part.clip else piece
        if shape.fronts and part.role == "hole":   # the inside of the neck is part of the back, drawn with it
            continue
        if shape.fronts and part.role in ("collar_r", "collar_l", "lapel_r", "lapel_l", "edge"):
            # A collar or lapel belongs to one front; the other front's is its mirror image (the closed drawing
            # shows that one partly covered). What lies across the centre sits behind the neck, on the back.
            xs = [float(v) for v in re.findall(r"(-?\d+(?:\.\d+)?),-?\d", part.d)]
            reach = (shape.body_box[2] - shape.body_box[0]) / 2
            if part.role != "edge" or max(abs(x - W / 2) for x in xs) < reach:   # an edge out on a sleeve stays there
                lean = (min(xs) + max(xs)) / 2 - W / 2
                (behind_neck if abs(lean) < 1.5 else top_side if lean > 0 else []).append(piece)
                continue
        g.append(piece)
    g.append(_graphic_markup(spec.graphic, shape.bbox, clip))
    if style == "soft":
        g.append(f'<path d="{shape.outline}" fill="url(#g{uid})"/>')
    g.append(f'<g clip-path="url(#{clip})">')  # seams never run past the edge of the garment
    for d in shape.lines:
        g.append(sunk(d))
    for d in shape.lines:
        g.append(halo(d))
    for d in shape.lines:
        g.append(thin(d))
    g.append("</g>")
    def button(x, y, r):
        m = f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r + 1.3}" fill="#fff" opacity=".45"/>' if patterned else ""
        if style == "line":
            fill = spec.button_color or CARD
            if shape.tailored:   # a jacket's buttons always stand out from its cloth
                fill = legible(fill, base, BUTTON_CONTRAST)
            ring = shade(fill, 0.45) if luminance(fill) < 0.08 and dark_item else INK
            return m + f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{fill}" stroke="{ring}" stroke-width="1.1"/>'
        if spec.button_color or shape.tailored:
            fill = spec.button_color or l_stroke
            if shape.tailored:
                fill = legible(fill, base, BUTTON_CONTRAST)
            return m + f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{fill}" stroke="{l_stroke}" stroke-width=".8"/>'
        return m + f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{l_stroke}" opacity="{min(1, l_op + 0.25)}"/>'

    def stud(x, y, r):   # a press stud: a metal ring round a cap
        cap = spec.button_color or "#ece6da"
        ring = "#8d8a84" if luminance(cap) > 0.35 else "#c9c5bd"
        m = f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r + 1.5}" fill="#fff" opacity=".45"/>' if patterned else ""
        return m + (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r + 0.9:.1f}" fill="{ring}" stroke="{INK if style == "line" else l_stroke}" stroke-width=".9"/>'
                    f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r * 0.62:.1f}" fill="{cap}"/>'
                    f'<circle cx="{x - r * 0.18:.1f}" cy="{y - r * 0.18:.1f}" r="{r * 0.2:.1f}" fill="#fff" opacity=".7"/>')

    pins = [(x, y, r, button) for x, y, r in shape.dots] + [(x, y, r, stud) for x, y, r in shape.snaps]
    if not shape.fronts:
        g += [draw(x, y, r) for x, y, r, draw in pins]
    if spec.halo:   # fuzz: fibres standing off the edge, then a slightly ragged outline
        defs += (f'<filter id="z{uid}" x="-5%" y="-5%" width="110%" height="110%">'
                 '<feTurbulence type="fractalNoise" baseFrequency="1.1" numOctaves="1" seed="7"/>'
                 '<feDisplacementMap in="SourceGraphic" scale="5" xChannelSelector="R" yChannelSelector="G"/></filter>'
                 f'<filter id="y{uid}" x="-5%" y="-5%" width="110%" height="110%">'
                 '<feTurbulence type="fractalNoise" baseFrequency="1.4" numOctaves="1" seed="3"/>'
                 '<feDisplacementMap in="SourceGraphic" scale="2.2" xChannelSelector="R" yChannelSelector="G"/></filter>')
        fz = shade(base, 0.08 if dark_item else (-0.13 if luminance(base) > 0.8 else -0.06))
        g.append(f'<path d="{shape.outline}" fill="none" stroke="{fz}" stroke-width="{max(o_w, 2) + 3.5:.1f}" '
                 f'stroke-linejoin="round" filter="url(#z{uid})"/>')
    if o_w:
        rag = f' filter="url(#y{uid})"' if spec.halo else ""
        g.append(f'<path d="{shape.outline}" fill="none" stroke="{o_stroke}" stroke-width="{o_w:.2f}" stroke-linejoin="round"{rag}/>')
        for part in shape.parts:
            if part.role == "sole":
                g.append(f'<path d="{part.d}" fill="none" stroke="{o_stroke}" stroke-width="{o_w * 0.7:.1f}" stroke-linejoin="round"/>')
    if not shape.fronts:
        g.append("</g>")
        return defs, "".join(g), dy, None

    # ---- worn open. The garment is taken as the layers it is made of: the back, the two fronts and what is
    # sewn to them. Both fronts are the same size: each reaches past the centre by the overlap, so the under
    # front is whole (the part the closed drawing hides is the mirror image of the top front's). The front that
    # lies on top carries the buttonholes; the one underneath carries the buttons. Each front swings open about
    # its side seam like a door, so it is drawn narrower, as a panel turned away from the viewer looks, while
    # sleeves and sides stay put. The inside of the back shows between the fronts and inside the neck.
    edge, slit = shape.fronts
    cx = W / 2
    half = (shape.body_box[2] - shape.body_box[0]) / 2
    run = [(edge[0][0], -60.0)] + list(edge) + [(edge[-1][0], H + 60.0)]
    full = []                                   # the same edge, with a point wherever it crosses the centre line
    for a, b in zip(run, run[1:]):
        full.append(a)
        if (a[0] - cx) * (b[0] - cx) < 0:
            t = (cx - a[0]) / (b[0] - a[0])
            full.append((cx, a[1] + (b[1] - a[1]) * t))
    full.append(run[-1])
    past = max(0.0, cx - min(x for x, _ in edge))             # how far a front reaches past the centre
    turn = max(0.5, (half - 0.21 * half) / (half + past))     # the fronts end up about a fifth of the chest apart
    hinge = {+1: cx + half, -1: cx - half}
    mat = {side: f"matrix({turn:.4f} 0 0 1 {hinge[side] * (1 - turn):.2f} 0)" for side in (+1, -1)}
    flip = f"matrix(-1 0 0 1 {2 * cx:.1f} 0)"

    def poly(pts, close=True):
        return "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts) + (" Z" if close else "")

    def placed(side, x, y):   # where a point on a front lands once the front has swung
        return (hinge[side] + (x - hinge[side]) * turn if abs(x - cx) < half else x), y

    def fastened(side, x, y):   # a button or its hole keeps its distance from the front's edge
        ex = _x_on(run, y) if side > 0 else 2 * cx - _x_on(run, y)
        return placed(side, ex, y)[0] + (x - ex), y

    box = (-60.0, -60.0, W + 60.0, H + 60.0)
    top_front = full + [(hinge[+1], box[3]), (hinge[+1], box[1])]
    seen_under = [(cx - abs(x - cx), y) for x, y in full]     # the under front where the top one never covered it
    under_front = seen_under + [(hinge[-1], box[3]), (hinge[-1], box[1])]
    overlap = [(min(x, cx), y) for x, y in full] + [(max(2 * cx - x, cx), y) for x, y in full][::-1]
    holes = "".join(f'<path d="{part.d}" fill="#000"/>' for part in shape.parts if part.role == "hole")
    defs += (f'<g id="q{uid}">{"".join(g[1:])}</g>'
             f'<clipPath id="kr{uid}"><path d="{poly(top_front)}"/></clipPath>'
             f'<clipPath id="kl{uid}"><path d="{poly(under_front)}"/></clipPath>'
             f'<clipPath id="ko{uid}"><path d="{poly(overlap)}"/></clipPath>'
             f'<clipPath id="ks{uid}"><rect x="{hinge[+1] - 1:.1f}" y="{box[1]}" width="{box[2] - hinge[+1] + 1:.1f}" height="{box[3] - box[1]}"/>'   # a hair under the fronts: no seam shows
             f'<rect x="{box[0]}" y="{box[1]}" width="{hinge[-1] - box[0] + 1:.1f}" height="{box[3] - box[1]}"/></clipPath>'
             f'<mask id="mh{uid}" maskUnits="userSpaceOnUse" x="{box[0]}" y="{box[1]}" width="{box[2] - box[0]}" height="{box[3] - box[1]}">'
             f'<rect x="{box[0]}" y="{box[1]}" width="{box[2] - box[0]}" height="{box[3] - box[1]}" fill="#fff"/>{holes}</mask>')
    # the fronts are clear where the neck is: the inside of the back shows there, or a garment worn underneath
    cloth = f'<use href="#q{uid}" mask="url(#mh{uid})"/>'
    inside = "".join(f'<path d="{part.d}" fill="{paint}"/><path d="{part.d}" fill="{in_c}" opacity="{in_op}"/>'
                     for part in shape.parts if part.role == "hole")
    e_stroke, e_w = (o_stroke, o_w) if o_w else (l_stroke, l_w)
    front_edge = (f'<g clip-path="url(#{clip})"><path d="{poly(edge, close=False)}" fill="none" stroke="{e_stroke}" '
                  f'stroke-width="{e_w / turn:.2f}" stroke-linejoin="round" stroke-linecap="round"/></g>')
    collar = "".join(top_side)

    def buttonhole(x, y, r):
        dx, dy_ = (0, r + 0.8) if slit == "vertical" else (r + 0.8, 0)
        return (f'<path d="M {x - dx:.1f},{y - dy_:.1f} L {x + dx:.1f},{y + dy_:.1f}" fill="none" stroke="{l_stroke}" '
                f'stroke-width="1.7" stroke-linecap="round" opacity="{l_op}"/>')

    fastenings = []
    for x, y, r, draw in pins:
        ex = _x_on(run, y)
        if ex - 0.5 <= x <= 2 * cx - ex + 0.5 and x <= cx + 1:   # where the two fronts fasten to each other
            fastenings.append(draw(*fastened(-1, 2 * cx - x, y), r))                              # the button, underneath
            fastenings.append((buttonhole if draw is button else draw)(*fastened(+1, x, y), r))   # its hole, on top
        else:   # a button for show, on a pocket or on a cuff: it stays on its own piece
            fastenings.append(draw(*placed(+1 if x >= cx else -1, x, y), r))

    back = (f'<path d="{shape.outline}" fill="{paint}"/><path d="{shape.outline}" fill="{in_c}" opacity="{in_op}"/>'
            + (f'<path d="{shape.outline}" fill="none" stroke="{o_stroke}" stroke-width="{o_w:.2f}" stroke-linejoin="round"/>' if o_w else "")
            + "".join(behind_neck)
            # the inside of the neck follows the collar as each front swings
            + f'<g transform="{mat[-1]}"><g clip-path="url(#kl{uid})">{inside}</g></g>'
            + f'<g transform="{mat[+1]}"><g clip-path="url(#kr{uid})">{inside}</g></g>')
    fronts = (f'<g clip-path="url(#ks{uid})">{cloth}</g>'                                   # sleeves and sides
              f'<g transform="{mat[-1]}"><g clip-path="url(#kl{uid})">{cloth}</g>'            # the under front ...
              f'<g clip-path="url(#ko{uid})"><g transform="{flip}">{cloth}</g></g>'           # ... with its hidden strip
              f'<g transform="{flip}">{collar}{front_edge}</g></g>'
              f'<g transform="{mat[+1]}"><g clip-path="url(#kr{uid})">{cloth}</g>{collar}{front_edge}</g>'   # the top front
              + "".join(fastenings))
    back, fronts = g[0] + behind + back + "</g>", g[0] + fronts + "</g>"
    # a garment underneath can show anywhere inside this one's outline (the fronts and sleeves then cover most
    # of it), below its hem as wide as the body, and above its collar as wide as the neck
    hem_y, sh_y = shape.body_box[3], shape.anchors.get("shoulder_l", (0, 80.0))[1]
    shows = [shape.outline, poly([(cx - half, hem_y - 2), (cx + half, hem_y - 2), (cx + half, box[3]), (cx - half, box[3])]),
             poly([(cx - 48, box[1]), (cx + 48, box[1]), (cx + 48, sh_y + 12), (cx - 48, sh_y + 12)])]
    return defs, ((back, fronts) if layered else back + fronts), dy, shows


# ------------------------------------------------------------------ traced

def trace_outline(cutout: Image.Image, box: tuple[float, float, float, float], smooth: float = 0.004) -> tuple[str, tuple[float, float, float, float]]:
    """Vectorise the cutout's real outline, scaled to fit `box` on the canvas."""
    import cv2  # the bench's traced style only: the app's program has no OpenCV
    a = (np.asarray(cutout.split()[-1]) > 128).astype(np.uint8)
    k = max(3, (max(a.shape) // 150) | 1)
    a = cv2.morphologyEx(a, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))
    a = cv2.GaussianBlur(a * 255, (0, 0), max(a.shape) / 300)
    a = (a > 127).astype(np.uint8)
    cs, _ = cv2.findContours(a, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(cs, key=cv2.contourArea)
    c = cv2.approxPolyDP(c, smooth * cv2.arcLength(c, True), True)[:, 0, :].astype(np.float32)
    x, y, w, h = cv2.boundingRect(c.astype(np.int32))
    bx0, by0, bx1, by1 = box
    s = min((bx1 - bx0) / w, (by1 - by0) / h)
    ox = bx0 + ((bx1 - bx0) - w * s) / 2 - x * s
    oy = by0 + ((by1 - by0) - h * s) / 2 - y * s
    pts = c * s + np.array([ox, oy], dtype=np.float32)
    # Catmull-Rom through the simplified points, written as cubic beziers
    n = len(pts)
    d = [f"M {pts[0][0]:.1f},{pts[0][1]:.1f}"]
    for i in range(n):
        p0, p1, p2, p3 = pts[(i - 1) % n], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        c1 = p1 + (p2 - p0) / 8
        c2 = p2 - (p3 - p1) / 8
        d.append(f"C {c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}")
    d.append("Z")
    placed = (ox + x * s, oy + y * s, ox + (x + w) * s, oy + (y + h) * s)
    # the cutout's own frame (including its padding) in canvas coordinates
    frame = (ox, oy, ox + cutout.width * s, oy + cutout.height * s)
    return " ".join(d), frame if frame else placed


def _render_traced(spec: Spec, cutout: Image.Image, uid: str) -> str:
    d, frame = trace_outline(cutout, (30, 30, W - 30, H - 30))
    fx0, fy0, fx1, fy1 = frame
    dummy = Shape(outline=d, bbox=frame)
    defs, paint = _defs_for_fill(spec.fill, dummy, uid, fx1 - fx0, fy1 - fy0)
    clip = f"c{uid}"
    defs += f'<clipPath id="{clip}"><path d="{d}"/></clipPath>'
    base = spec.fill.color
    edge = shade(base, 0.2 if luminance(base) < 0.22 else -0.3)
    body = (f'<path d="{d}" fill="{paint}"/>' + _graphic_markup(spec.graphic, frame, clip)
            + f'<path d="{d}" fill="none" stroke="{edge}" stroke-width="2.6" stroke-linejoin="round"/>')
    return _svg(body, defs)
