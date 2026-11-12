"""Compose an illustration: shape (from attributes) + fill (from the photo).

Four styles are offered for comparison. Three draw the parametric template;
the fourth traces the real outline from the cutout instead.
"""
from __future__ import annotations

import colorsys
import re
from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image

from . import fills
from .templates import H, W, Shape, _x_on, build

STYLES = ("flat", "line", "soft", "traced")
CX_ROT = (200, 120)  # patterns are turned about the middle of the chest
CARD = "#f1eee8"
INK = "#26231f"


@dataclass
class Fill:
    kind: str                                  # solid | stripes | swatch
    color: str = "#888888"
    stripes: fills.Stripes | None = None
    swatch: fills.Swatch | None = None


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
    texture: str | None = None        # corduroy | rib_knit | cable_knit | waffle: drawn tone-on-tone over the fill
    lace_color: str | None = None     # shoes: None = laces in the upper's colour
    collar_color: str | None = None   # a collar in its own colour (a rugby shirt's white twill); None = trim colour or the cloth
    weight: str | None = None         # lightweight | midweight | heavyweight | super_heavy: how much depth the cloth is drawn with
    halo: bool = False                # a fuzzy cloth (fleece, sherpa, mohair, brushed flannel): a soft, broken edge
    sheen: bool = False               # a shiny cloth (satin, nylon): a soft highlight across the body
    texture_scale: float | None = None  # the texture's spacing: corduroy wale, knit gauge (None = standard)
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
        return (f'<pattern id="p{uid}" patternUnits="userSpaceOnUse" x="{x0:.1f}" y="{y0:.1f}" width="{tw:.2f}" height="{th:.2f}">'
                f'<image href="{uri}" width="{tw + 0.4:.2f}" height="{th + 0.4:.2f}" preserveAspectRatio="none"/></pattern>',
                f"url(#p{uid})")
    return "", fill.color


# Textures drawn tone-on-tone. `Spec.texture_scale` stretches the spacing (2 = a corduroy wale twice as
# wide, 1.4 = a chunkier knit); "name:scale" is accepted too.
TEXTURES = ("corduroy", "rib_knit", "waffle", "cable_knit", "pique", "mesh", "seersucker", "herringbone", "twill",
            "denim", "fisherman_rib", "garter", "linen", "basket", "tweed", "ripstop", "sherpa", "fleece",
            "quilt_diamond", "quilt_box", "baffle")


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
        return (40, 9, f'<path d="M2,2H13M21,2.5H25M8,6.5H15M27,6H38M31,8.2H34" stroke="{lo}" stroke-width=".9" opacity=".12"/>')
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
    return None


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
    clip = f"c{uid}"
    defs += f'<clipPath id="{clip}"><path d="{shape.outline}"/></clipPath>'
    patterned = paint.startswith("url(")
    tex_defs = _texture_defs(spec.texture, uid, dark_item, spec.texture_scale)
    defs += tex_defs

    def turned(name: str, degrees: float) -> str:
        """The same cloth turned by an angle (sleeves hang at an angle; collar leaves are cut on a slant)."""
        nonlocal defs
        if not patterned:
            return paint
        defs += (f'<pattern id="p{uid}{name}" href="#p{uid}" '
                 f'patternTransform="rotate({degrees:.1f} {CX_ROT[0]} {CX_ROT[1]})"/>')
        return f"url(#p{uid}{name})"

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

    def part_color(key):
        return {"trim": spec.trim_color, "lace": spec.lace_color, "sole": sole_c, "sole_line": None}.get(key, key)

    def overlay(d: str, role: str, color: str | None = None) -> str:
        if role == "edge":   # a line with no fill, e.g. the visible edges of a collar
            if color == "sole_line":   # a line on the sole (foxing stripe, heel lift): a darker tone of the sole, not the upper's
                c = shade(sole_c, -0.3 if luminance(sole_c) > 0.25 else 0.22)
                return f'<path d="{d}" fill="none" stroke="{c}" stroke-width="{l_w}" stroke-linecap="round"/>'
            return halo(d, 2.4) + thin(d)
        if role in ("collar_r", "collar_l"):
            # the same cloth as the body (turned, when patterned); its edges are a separate "edge" part
            if spec.collar_color or spec.trim_color:
                return f'<path d="{d}" fill="{spec.collar_color or spec.trim_color}"/>'
            return f'<path d="{d}" fill="{turned(role[-1], -24 if role == "collar_r" else 24)}"/>'
        if role in ("lapel_r", "lapel_l"):
            # a tailored jacket's collar and lapels: cut from the body's cloth, so they carry its surface too
            fill = spec.collar_color or spec.trim_color or turned(role[-1], -24 if role == "lapel_r" else 24)
            return f'<path d="{d}" fill="{fill}"/>' + (f'<path d="{d}" fill="url(#t{uid})"/>' if tex_defs else "")
        if role == "neckrib":   # the rib of a crew neck: only painted when it is a contrast colour
            return f'<path d="{d}" fill="{spec.trim_color}"/>' if spec.trim_color else ""
        if role == "stitch":   # topstitching in its own thread colour: dashed, never ink
            c = part_color(color) or "#c9973f"
            if color == "sole_line":
                c = shade(sole_c, -0.25 if luminance(sole_c) > 0.25 else 0.22)
            return f'<path d="{d}" fill="none" stroke="{c}" stroke-width="1.3" stroke-dasharray="3.2 2.4" stroke-linecap="round"/>'
        if role == "inlay":    # a piece in its own colour (lace, rubber toe, contrast panel); body cloth when none is given
            c = part_color(color)
            body = f'<path d="{d}" fill="{c}"/>' if c else (f'<path d="{d}" fill="{paint}"/>'
                                                           f'<path d="{d}" fill="{"#fff" if dark_item else "#000"}" opacity=".08"/>')
            return body + f'<path d="{d}" fill="none" stroke="{l_stroke if style != "flat" else shade(c or base, -0.3)}" stroke-width="{l_w}" stroke-linejoin="round" opacity="{l_op}"/>'
        if role == "sole":
            c = sole_c
            return f'<path d="{d}" fill="{c}"/>' + (f'<path d="{d}" fill="#000" opacity=".06"/>' if style != "line" else "")
        if role == "hole":
            return f'<path d="{d}" fill="{paint}"/><path d="{d}" fill="#000" opacity=".22"/>'
        # a shirt cuff is the body's own cloth: no tint where a line already marks it
        op = {"trim": 0.10, "band": 0.12, "cuff": 0.0 if style == "line" else 0.06}.get(role, 0.1)
        col = "#fff" if dark_item else "#000"
        if spec.trim_color and role in ("band", "cuff"):
            out = f'<path d="{d}" fill="{spec.trim_color}"/>'
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
    behind = "".join(overlay(part.d, part.role, part.color) for part in shape.behind)
    if not shape.fronts:
        g.append(behind)
    # the garment body; a same-paint stroke rounds the corners in the flat style
    round_stroke = f' stroke="{paint}" stroke-width="5" stroke-linejoin="round"' if style == "flat" and not patterned else ""
    g.append(f'<path d="{shape.outline}" fill="{paint}"{round_stroke}/>')
    if patterned:
        for n, (d, degrees) in enumerate(shape.sleeves):
            g.append(f'<path d="{d}" fill="{turned(f"s{n}", degrees)}"/>')
    if tex_defs:   # the surface runs down the body and along each sleeve
        g.append(f'<path d="{shape.outline}" fill="url(#t{uid})"/>')
        for n, (d, degrees) in enumerate(shape.sleeves):
            defs += (f'<pattern id="t{uid}s{n}" href="#t{uid}" '
                     f'patternTransform="rotate({degrees:.1f} {CX_ROT[0]} {CX_ROT[1]})"/>')
            g.append(f'<path d="{d}" fill="{paint if not patterned else turned(f"s{n}", degrees)}"/>'
                     f'<path d="{d}" fill="url(#t{uid}s{n})"/>')
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
    g.append("</g>")
    top_side, behind_neck = [], []   # worn open: the top front's collar and lapel; pieces behind the neck
    for part in shape.parts:   # parts marked clip are cut by the garment's edge (laces, a rubber toe)
        piece = overlay(part.d, part.role, part.color)
        if depth and part.role in ("collar_r", "collar_l", "trim"):   # a thick piece stands proud of the body
            piece = (f'<g clip-path="url(#{clip})"><path d="{part.d}" transform="translate({depth * 0.35:.1f} {depth * 0.8:.1f})" '
                     f'fill="{d_col}" opacity="{d_op + 0.05:.2f}"/></g>') + piece
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
            ring = shade(spec.button_color, 0.45) if spec.button_color and luminance(spec.button_color) < 0.08 and dark_item else INK
            return m + f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{spec.button_color or CARD}" stroke="{ring}" stroke-width="1.1"/>'
        if spec.button_color:
            return m + f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{spec.button_color}" stroke="{l_stroke}" stroke-width=".8"/>'
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
    inside = "".join(f'<path d="{part.d}" fill="{paint}"/><path d="{part.d}" fill="#000" opacity=".22"/>'
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

    back = (f'<path d="{shape.outline}" fill="{paint}"/><path d="{shape.outline}" fill="#000" opacity=".22"/>'
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
