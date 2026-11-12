"""Compose an illustration: shape (from attributes) + fill (from the photo).

Four styles are offered for comparison. Three draw the parametric template;
the fourth traces the real outline from the cutout instead.
"""
from __future__ import annotations

import colorsys
from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image

from . import fills
from .templates import H, W, Shape, build

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


def _svg(body: str, defs: str, card: bool = True) -> str:
    bg = f'<rect width="{W}" height="{H}" rx="18" fill="{CARD}"/>' if card else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">'
            f"<defs>{defs}</defs>{bg}{body}</svg>")


def render(spec: Spec, style: str, cutout: Image.Image | None = None, uid: str = "a") -> str:
    if style == "traced":
        if cutout is None:
            raise ValueError("traced style needs the cutout")
        return _render_traced(spec, cutout, uid)
    shape = build(spec.template, spec.params)
    bx0, by0, bx1, by1 = shape.bbox
    gw, gh = bx1 - bx0, by1 - by0
    # centre the garment vertically on the card
    dy = (H - gh) / 2 - by0
    defs, paint = _defs_for_fill(spec.fill, shape, uid, gw, gh)
    base = spec.fill.color
    dark_item = luminance(base) < 0.22
    tone = shade(base, 0.16 if dark_item else -0.16)
    clip = f"c{uid}"
    defs += f'<clipPath id="{clip}"><path d="{shape.outline}"/></clipPath>'
    patterned = paint.startswith("url(")

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

    def overlay(d: str, role: str) -> str:
        if role == "edge":   # a line with no fill, e.g. the visible edges of a collar
            return halo(d, 2.4) + thin(d)
        if role in ("collar_r", "collar_l"):
            # the same cloth as the body (turned, when patterned); its edges are a separate "edge" part
            return f'<path d="{d}" fill="{turned(role[-1], -24 if role == "collar_r" else 24)}"/>'
        if role == "sole":
            c = spec.sole_color or "#f4f1ea"
            return f'<path d="{d}" fill="{c}"/>' + (f'<path d="{d}" fill="#000" opacity=".06"/>' if style != "line" else "")
        if role == "hole":
            return f'<path d="{d}" fill="{paint}"/><path d="{d}" fill="#000" opacity=".22"/>'
        # a shirt cuff is the body's own cloth: no tint where a line already marks it
        op = {"trim": 0.10, "band": 0.12, "cuff": 0.0 if style == "line" else 0.06}.get(role, 0.1)
        col = "#fff" if dark_item else "#000"
        out = f'<path d="{d}" fill="{paint}"/>' + (f'<path d="{d}" fill="{col}" opacity="{op}"/>' if op else "")
        if style in ("line", "soft"):
            out += f'<path d="{d}" fill="none" stroke="{l_stroke}" stroke-width="{l_w}" stroke-linejoin="round" opacity="{l_op}"/>'
        return out

    g = [f'<g transform="translate(0 {dy:.1f})"' + (f' filter="url(#s{uid})"' if style == "soft" else "") + ">"]
    for part in shape.behind:
        g.append(overlay(part.d, part.role))
    # the garment body; a same-paint stroke rounds the corners in the flat style
    round_stroke = f' stroke="{paint}" stroke-width="5" stroke-linejoin="round"' if style == "flat" and not patterned else ""
    g.append(f'<path d="{shape.outline}" fill="{paint}"{round_stroke}/>')
    if patterned:
        for n, (d, degrees) in enumerate(shape.sleeves):
            g.append(f'<path d="{d}" fill="{turned(f"s{n}", degrees)}"/>')
    # seams lie on the body, under anything folded over it (a collar covers the top of the placket)
    g.append(f'<g clip-path="url(#{clip})">')
    for d in shape.seams:
        g.append(halo(d))
    for d in shape.seams:
        g.append(thin(d))
    g.append("</g>")
    for part in shape.parts:
        g.append(overlay(part.d, part.role))
    g.append(_graphic_markup(spec.graphic, shape.bbox, clip))
    if style == "soft":
        g.append(f'<path d="{shape.outline}" fill="url(#g{uid})"/>')
    g.append(f'<g clip-path="url(#{clip})">')  # seams never run past the edge of the garment
    for d in shape.lines:
        g.append(halo(d))
    for d in shape.lines:
        g.append(thin(d))
    g.append("</g>")
    for x, y, r in shape.dots:
        if patterned:
            g.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r + 1.3}" fill="#fff" opacity=".45"/>')
        if style == "line":
            g.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{CARD}" stroke="{INK}" stroke-width="1.1"/>')
        else:
            g.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{l_stroke}" opacity="{min(1, l_op + 0.25)}"/>')
    if o_w:
        g.append(f'<path d="{shape.outline}" fill="none" stroke="{o_stroke}" stroke-width="{o_w}" stroke-linejoin="round"/>')
        for part in shape.parts:
            if part.role == "sole":
                g.append(f'<path d="{part.d}" fill="none" stroke="{o_stroke}" stroke-width="{o_w * 0.7:.1f}" stroke-linejoin="round"/>')
    g.append("</g>")
    return _svg("".join(g), defs)


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
