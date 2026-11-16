"""A shoe drawn by Claude from its photos (shoes drawn from understanding, step C): the drawing made safe, shown and
checked. No call to Claude is made here; `closet/tagger/shoedrawing.py` asks for the drawing and `closet/shoedraw.py`
keeps it with the item.

The drawing comes back as bare SVG elements in a fixed frame: x 0 to 200 centred on x = 100, the ground at y = 240,
about 17 units to a centimetre, one shoe pointing straight at the viewer, seen from the front and a little above. Each
shoe is in two parts (`Side`, step D): what is behind the leg (the back of a collar or a shaft, a pull tab at the back,
the lining seen inside the opening) and what is in front of it. The part behind is drawn first, then the leg (x 62 to
138, in a sock), then the part in front, so the leg goes into the shoe. A drawing kept before the parts (version 1) is
all in front.

- `sanitise` keeps only plain shapes with plain numbers and plain colours: whatever Claude writes, nothing that could
  run, link, load or hide can reach the page or the files. `side` makes both parts of a shoe safe.
- `preview_svg` puts the pair on two legs in socks, as the experiment's preview did (`bench/experiments/shoe_drawn/
  render3.js`, without its tilt), with the ink lines as thick as the outfit figure will draw them. The item page
  shows it, and Claude looks at it to check its drawing (`check_png`, rendered by resvg).
- `checks` measures renders of the drawing against the frame and says in plain words what is wrong: it stands on
  the ground, stays in the frame, is not too tall, the leg goes into it, and nothing in front of the leg hides it
  above the opening. They stand in for the four front-shoe rules, which are written for the templates' geometry.
- `stored` reads a drawing kept with the item for the outfit figure (`figure.py` places it on the feet).
"""
from __future__ import annotations

import io
import math
import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from html import escape
from pathlib import Path

INK = "#26221f"                    # the bold outline and the inner lines
TODAY_LINE = 2.2 / (4 * 0.297)     # how much thicker the figure draws them: its shoe outline is 2.2 px, and the
#                                    frame's bold outline (4 units) lands at 1.2 px on it (on_figure.py's TODAY_LINE)
THIN_INK = 4.5                     # ink strokes up to this wide are lines; thicker ones draw laces and bows, kept
FRAME = (0.0, 200.0)
GROUND = 240.0
LEG = (62.0, 138.0)
LEG_DOWN = 200.0                   # the stand-in leg in the preview goes down this far, behind the shoe
# the stand-in leg's crew sock, in the preview and the check picture: a light grey, so the shoe's own colours stand
# out (the owner, 16 November; green before, as in the experiment's render3.js), and its two rib lines
PREVIEW_SOCK, PREVIEW_SOCK_RIB = "#d3d0ca", "#a9a59d"
MAX_CHARS = 40_000                 # one drawing, as written; the liked examples are 1,300 to 2,900
MAX_ELEMENTS = 150                 # shapes and groups kept; the liked examples have 9 to 13
MAX_DEPTH = 8                      # groups inside groups
EXAMPLES_DIR = Path(__file__).resolve().parent / "shoe_examples"
EXAMPLES = ("trainer", "dress-shoe", "boat-shoe")   # the drawings the owner liked, as worked examples
# a liked drawing split by hand into its part behind the leg and its part in front (`<name>.behind.svg`,
# `<name>.front.svg`): not shown to Claude, but drawn on the demo closet's boot
SPLIT = ("boot",)

SHAPES = frozenset({"path", "circle", "ellipse", "rect", "line", "polyline", "polygon"})
ELEMENTS = SHAPES | {"g"}
SVG_NS = "http://www.w3.org/2000/svg"
_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
NUMBER = re.compile(rf"\s*{_NUM}\s*")
NUMBERS = re.compile(rf"\s*{_NUM}(?:(?:\s*,\s*|\s+){_NUM})*\s*")
PATH_DATA = re.compile(r"[MmZzLlHhVvCcSsQqTtAa0-9eE.,+\-\s]+")
POINTS = re.compile(r"[0-9eE.,+\-\s]+")
COLOUR = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})")
TRANSFORM = re.compile(r"\s*(translate|scale|rotate|matrix)\s*\(([^()]*)\)\s*,?")
TRANSFORM_ARGS = {"translate": (1, 2), "scale": (1, 2), "rotate": (1, 3), "matrix": (6,)}
COMMENT = re.compile(r"<!--.*?-->", re.S)
CHOICES = {"stroke-linejoin": ("miter", "round", "bevel"), "stroke-linecap": ("butt", "round", "square"),
           "fill-rule": ("nonzero", "evenodd")}
LENGTHS = frozenset({"cx", "cy", "r", "rx", "ry", "x", "y", "width", "height", "x1", "y1", "x2", "y2", "stroke-width"})
OPACITIES = frozenset({"opacity", "fill-opacity", "stroke-opacity"})
ATTRIBUTES = (LENGTHS | OPACITIES | set(CHOICES)
              | {"d", "points", "fill", "stroke", "stroke-dasharray", "transform"})


class DrawingError(ValueError):
    """A drawing that cannot be used, and why, in plain words (Claude is told, so it can fix it)."""


class NothingDrawable(DrawingError):
    """Nothing drawable is left once the drawing is made safe."""


# ------------------------------------------------------------------ made safe

def _transform(value: str) -> str | None:
    out, at = [], 0
    for m in TRANSFORM.finditer(value):
        if m.start() != at:
            return None
        args = re.findall(_NUM, m.group(2))
        if not NUMBERS.fullmatch(m.group(2)) or len(args) not in TRANSFORM_ARGS[m.group(1)]:
            return None
        out.append(f"{m.group(1)}({' '.join(args)})")
        at = m.end()
    return " ".join(out) if out and value[at:].strip() == "" else None


def _value(name: str, value: str) -> str | None:
    """The attribute's value as kept, or None when it is not allowed."""
    v = value.strip()
    if name in LENGTHS:
        return v if NUMBER.fullmatch(v) else None
    if name in OPACITIES:
        return v if NUMBER.fullmatch(v) and 0 <= float(v) <= 1 else None
    if name in ("fill", "stroke"):
        return v.lower() if v == "none" or COLOUR.fullmatch(v) else None
    if name in CHOICES:
        return v if v in CHOICES[name] else None
    if name == "d":
        return " ".join(v.split()) if PATH_DATA.fullmatch(v) else None
    if name == "points":
        return " ".join(v.split()) if POINTS.fullmatch(v) else None
    if name == "stroke-dasharray":
        return v if v == "none" or NUMBERS.fullmatch(v) else None
    if name == "transform":
        return _transform(v)
    return None


def _local(tag) -> str | None:
    """An element's name without the SVG namespace; None for another namespace (or a comment)."""
    if not isinstance(tag, str):
        return None
    if tag.startswith("{"):
        ns, _, name = tag[1:].partition("}")
        return name if ns == SVG_NS else None
    return tag


def _clean(el, depth: int, kept: list[int]) -> str | None:
    name = _local(el.tag)
    if name not in ELEMENTS:
        return None   # with everything inside it: text, images, links, styles, scripts, defs, uses
    if name == "g" and depth > MAX_DEPTH:
        raise DrawingError(f"The drawing has groups inside groups more than {MAX_DEPTH} deep.")
    attrs = []
    for key, value in el.attrib.items():
        if key in ATTRIBUTES:   # a namespaced attribute (xlink:href, ...) never matches
            v = _value(key, value)
            if v is not None:
                attrs.append((key, v))
    if name == "g":
        children = [c for c in (_clean(child, depth + 1, kept) for child in el) if c]
        if not children:
            return None
    kept[0] += 1
    if kept[0] > MAX_ELEMENTS:
        raise DrawingError(f"The drawing has too many shapes: keep it to at most {MAX_ELEMENTS}.")
    a = "".join(f' {k}="{escape(v, quote=True)}"' for k, v in attrs)
    if name == "g":
        return f"<g{a}>{''.join(children)}</g>"
    kept[1] += 1
    return f"<{name}{a}/>"


def sanitise(fragment) -> str:
    """The drawing with only plain shapes left (g, path, circle, ellipse, rect, line, polyline, polygon), each with
    only its geometry, plain colours (#rgb, #rrggbb or none), stroke and fill settings, and transforms made of
    numbers; ids, text, images, links, styles, scripts and url() references are dropped. Raises `DrawingError` when
    the text is not well-formed, is too long or too deep, declares anything (`<!DOCTYPE`, `<!ENTITY`, CDATA, a
    processing instruction), has too many shapes, or has nothing drawable left."""
    if not isinstance(fragment, str):
        raise DrawingError("The drawing is not SVG text.")
    if len(fragment) > MAX_CHARS:
        raise DrawingError(f"The drawing is too long: {len(fragment):,} characters, at most {MAX_CHARS:,}.")
    text = COMMENT.sub("", fragment)
    if "<!" in text or "<?" in text:
        raise DrawingError("The drawing declares something (a DOCTYPE, an entity, CDATA or a processing "
                           "instruction): only plain SVG elements are allowed.")
    try:
        root = ET.fromstring(f"<g>{text}</g>")
    except ET.ParseError as e:
        raise DrawingError("The drawing is not well-formed SVG.") from e
    kept = [0, 0]   # elements, shapes
    out = [c for c in (_clean(child, 1, kept) for child in root) if c]
    if not kept[1]:
        raise NothingDrawable("Nothing drawable is left in the drawing: draw with path, circle, ellipse, rect, line, "
                              "polyline and polygon elements (in g groups if you like), nothing else.")
    return "\n".join(out)


@dataclass(frozen=True)
class Side:
    """One shoe of a drawing, in the frame, made safe: `front`, what is in front of the leg (drawn over it), and
    `behind`, what is behind the leg seen from the front (the back of a collar or a shaft, a pull tab at the back, the
    lining seen inside the opening; drawn before the leg, so the leg covers it; may be empty)."""
    front: str
    behind: str = ""

    def to_json(self) -> dict:
        return {"behind": self.behind, "front": self.front}


def _elements(text: str) -> int:
    return len(re.findall(r"<(?![/!?])", text))


def side(value) -> Side:
    """One shoe of a drawing made safe (`sanitise`): from {"behind", "front"} (an answer, or a drawing kept since
    version 2), a `Side`, or one SVG text, which is all in front (a drawing kept as version 1). `behind` may be empty
    or have nothing drawable left; `front` must have something. Together they keep to one drawing's caps."""
    if isinstance(value, Side):
        behind, front = value.behind, value.front
    elif isinstance(value, Mapping):
        behind, front = value.get("behind") or "", value.get("front")
    else:
        behind, front = "", value
    if not isinstance(behind, str) or not isinstance(front, str):
        raise DrawingError("The drawing is not SVG text.")
    if len(behind) + len(front) > MAX_CHARS:
        raise DrawingError(f"The drawing is too long: {len(behind) + len(front):,} characters behind and in front of "
                           f"the leg together, at most {MAX_CHARS:,}.")
    front = sanitise(front)
    try:
        behind = sanitise(behind) if behind.strip() else ""
    except NothingDrawable:
        behind = ""
    if _elements(front) + _elements(behind) > MAX_ELEMENTS:
        raise DrawingError(f"The drawing has too many shapes: keep it to at most {MAX_ELEMENTS}, behind and in front "
                           "of the leg together.")
    return Side(front, behind)


# ------------------------------------------------------------------ shown

def _number(value: str | None, default: float) -> float:
    try:
        return float(value) if value is not None else default
    except ValueError:
        return default


def thicken(fragment: str, factor: float = TODAY_LINE) -> str:
    """A sanitised drawing with its ink lines (stroke #26221f, at most 4.5 wide: the outline and the inner lines)
    `factor` times as thick; thicker ink strokes (laces, a bow) and other colours are left as they are. Every element
    that strokes gets its own width, so a group's thicker line never reaches a child drawn in another colour."""
    root = ET.fromstring(f"<g>{fragment}</g>")

    def walk(el, stroke: str | None, width: float) -> None:
        stroke = el.get("stroke", stroke)
        width = _number(el.get("stroke-width"), width)
        if stroke not in (None, "none"):
            el.set("stroke-width", f"{width * factor:.2f}" if stroke == INK and width <= THIN_INK else f"{width:g}")
        for child in el:
            walk(child, stroke, width)

    for child in root:
        walk(child, None, 1.0)
    return "\n".join(ET.tostring(child, encoding="unicode", short_empty_elements=True) for child in root)


def _leg(line: float) -> str:
    """The stand-in leg in a light grey crew sock (PREVIEW_SOCK), its outline as thick as the shoe's. It goes on down into
    the shoe, to y = LEG_DOWN (render3.js stopped at y = 60, which left a gap above a shoe as low as a boat shoe), so
    wherever the shoe does not cover it, it shows."""
    w = 4 * line
    return (f'<g stroke-linejoin="round"><path d="M60,-150 L140,-150 L138,{LEG_DOWN:g} L62,{LEG_DOWN:g} Z" '
            f'fill="#c98d6b" stroke="{INK}" stroke-width="{w:.2f}"/><path d="M61,-92 Q100,-80 139,-92 '
            f'L138,{LEG_DOWN:g} L62,{LEG_DOWN:g} Z" fill="{PREVIEW_SOCK}" '
            f'stroke="{INK}" stroke-width="{w:.2f}"/><path d="M62,-76 Q100,-64 138,-76 M62,-62 Q100,-50 138,-62" '
            f'fill="none" stroke="{PREVIEW_SOCK_RIB}" stroke-width="2"/></g>')


PREVIEW_W, PREVIEW_H = 440, 400


def _scene(left, right, line: float) -> str:
    leg = _leg(line)

    def shoe(value) -> str:   # behind the leg, the leg, in front of it
        s = side(value)
        behind, front = (thicken(s.behind, line) if s.behind else "", thicken(s.front, line)) if line != 1 else \
            (s.behind, s.front)
        return f"{behind}{leg}{front}"
    other = (f'<g transform="translate(218,150)">{shoe(right)}</g>' if right else
             f'<g transform="translate(418,150) scale(-1,1)">{shoe(left)}</g>')
    return (f'<rect width="{PREVIEW_W}" height="{PREVIEW_H}" fill="#f1eee8"/>'
            f'<g transform="translate(22,150)">{shoe(left)}</g>{other}')


def preview_svg(left, right=None, line: float = TODAY_LINE) -> str:
    """The pair on two legs in socks: the viewer's left shoe as drawn, the right one drawn on its own when there is a
    right drawing, else the left one mirrored. Each shoe (`side`: a `Side`, {"behind", "front"} or one SVG text, all
    in front) is drawn behind the leg, then the leg, then in front of it; no tilt. The ink lines are `line` times as
    thick as drawn (the figure's weight by default)."""
    return (f'<svg xmlns="{SVG_NS}" viewBox="0 0 {PREVIEW_W} {PREVIEW_H}" width="{PREVIEW_W}" height="{PREVIEW_H}">'
            f'{_scene(left, right, line)}</svg>')


BIG_W, SMALL_W, GAP = 560, 150, 20


def check_svg(left, right=None) -> str:
    """The preview large (560 px wide) and at phone size (150 px wide) side by side, as the experiment's render3.js
    showed it: what Claude looks at to check its drawing."""
    scene = _scene(left, right, TODAY_LINE)
    big_h, small_h = BIG_W * PREVIEW_H / PREVIEW_W, SMALL_W * PREVIEW_H / PREVIEW_W
    w, h = BIG_W + GAP + SMALL_W, round(big_h)
    view = f'viewBox="0 0 {PREVIEW_W} {PREVIEW_H}"'
    return (f'<svg xmlns="{SVG_NS}" viewBox="0 0 {w} {h}" width="{w}" height="{h}"><rect width="{w}" height="{h}" '
            f'fill="#ffffff"/><svg x="0" y="0" width="{BIG_W}" height="{big_h:.1f}" {view}>{scene}</svg>'
            f'<svg x="{BIG_W + GAP}" y="{big_h - small_h:.1f}" width="{SMALL_W}" height="{small_h:.1f}" {view}>'
            f'{scene}</svg></svg>')


def render_png(svg: str, width: int, height: int | None = None, background: str | None = None) -> bytes:
    """An SVG rendered to PNG bytes by resvg (no fonts are needed: the drawings have no text)."""
    import resvg_py  # only here: nothing else in the app renders SVG

    kwargs = {"svg_string": svg, "width": int(width), "skip_system_fonts": True}
    if height is not None:
        kwargs["height"] = int(height)
    if background:
        kwargs["background"] = background
    try:
        return bytes(resvg_py.svg_to_bytes(**kwargs))
    except ValueError as e:   # resvg could not draw it (a number it cannot use, say)
        raise DrawingError("The drawing could not be rendered: check its numbers.") from e


def check_png(left, right=None) -> bytes:
    """`check_svg` as one PNG."""
    svg = check_svg(left, right)
    w, h = (int(v) for v in re.search(r'width="(\d+)" height="(\d+)"', svg).groups())
    return render_png(svg, w, h)


@cache
def example(name: str) -> str:
    """One of the worked examples, as stored (bare SVG elements)."""
    if name not in EXAMPLES:
        raise KeyError(name)
    return (EXAMPLES_DIR / f"{name}.svg").read_text(encoding="utf-8")


@cache
def example_png(name: str) -> bytes:
    """A worked example on its legs, large and at phone size, as Claude is shown it."""
    return check_png(example(name))


@cache
def split_example(name: str) -> Side:
    """A liked drawing split by hand into its part behind the leg and its part in front (`SPLIT`), made safe."""
    if name not in SPLIT:
        raise KeyError(name)
    return side({part: (EXAMPLES_DIR / f"{name}.{part}.svg").read_text(encoding="utf-8") for part in ("behind", "front")})


# ------------------------------------------------------------------ checked

SCALE = 2                     # pixels per frame unit in the renders the checks measure
BOX = (-20, -220, 240, 480)   # what they render: x -20 to 220, y -220 to 260
BAND = (255, 0, 255)          # the flat-coloured leg band they lay behind the drawing
BAND_BOX = (LEG[0], -200.0, LEG[1], GROUND)
LOW = ("low", "low_profile")
TOP_LOW, TOP_BOOT = 0.0, -90.0          # the highest a low shoe's top and a boot's top may come
GROUND_RANGE = (234.0, 246.0)           # where the lowest painted pixel must be
INSIDE = (2.0, 198.0)
LEG_IN = (72.0, 128.0)                  # the middle of the leg, hidden from just below the opening down to y 200
LEG_IN_BOTTOM = 200.0
OPENING_GAP = 8.0
ABOVE = (75.0, 125.0)                   # nothing in front of the leg over it here, more than 25 units above the opening
ABOVE_ROOM = 25.0
TAB = (86.0, 114.0)                     # a front pull tab, centred on the leg: it may rise above the opening
TAB_ROOM = 60.0                         # but no more than this above the opening's front edge
OPENING_STRIP_TAB = (76.0, 84.0)        # beside a front pull tab, where the front edge is found
OPENING_STRIP = (90.0, 110.0)           # where the drawing's front edge is found, to compare with the sheet's
OPENING_SLACK = 15.0
SHOWS_PX = 20                           # visible leg pixels allowed (anti-aliasing at the edges)
COVERS_PX = 6


def _pixels(front: str, behind: str = "", band: bool = False):
    import numpy as np
    from PIL import Image

    x0, y0, w, h = BOX
    leg = ""
    if band:
        bx0, by0, bx1, by1 = BAND_BOX
        leg = f'<rect x="{bx0}" y="{by0}" width="{bx1 - bx0}" height="{by1 - by0}" fill="#ff00ff"/>'
    svg = (f'<svg xmlns="{SVG_NS}" viewBox="{x0} {y0} {w} {h}" width="{w * SCALE}" height="{h * SCALE}">'
           f'{behind}{leg}{front}</svg>')
    with Image.open(io.BytesIO(render_png(svg, w * SCALE, h * SCALE))) as im:
        return np.asarray(im.convert("RGBA")).astype(int)


def _col(x: float) -> int:
    return int(round((x - BOX[0]) * SCALE))


def _row(y: float) -> int:
    return int(round((y - BOX[1]) * SCALE))


def _y(row: float) -> float:
    return BOX[1] + row / SCALE


def _x(col: float) -> float:
    return BOX[0] + col / SCALE


def measure(shoe) -> dict:
    """Where one shoe of a drawing (`side`) is painted, in frame units: its box (left, top, right, bottom; None when
    nothing is painted), where its part in front of the leg is painted, and, with the leg band drawn between its part
    behind and its part in front, the leg pixels left showing (for the checks)."""
    import numpy as np

    s = side(shoe)
    painted = _pixels(s.front, s.behind)[:, :, 3] > 128
    rows, cols = np.where(painted.any(axis=1))[0], np.where(painted.any(axis=0))[0]
    box = None if not len(rows) else (_x(cols[0]), _y(rows[0]), _x(cols[-1] + 1), _y(rows[-1] + 1))
    front = _pixels(s.front)[:, :, 3] > 128 if s.behind else painted
    over = _pixels(s.front, s.behind, band=True)
    leg = (np.abs(over[:, :, :3] - np.array(BAND)).max(axis=2) <= 8) & (over[:, :, 3] > 250)
    return {"box": box, "painted": painted, "front": front, "leg": leg}


def _checks_one(shoe: Side, sheet: Mapping, who: str) -> list[str]:
    m = measure(shoe)
    if m["box"] is None:
        return [f"{who}Nothing of it is painted inside the frame."]
    left, top, right, bottom = m["box"]
    height = (sheet.get("silhouette") or {}).get("height")
    opening = float(sheet.get("opening_front_y") or 0)
    low = height in LOW
    out = []
    if not GROUND_RANGE[0] <= bottom <= GROUND_RANGE[1]:
        out.append(f"{who}It does not stand on the ground: its lowest point is at y {bottom:.0f}, and the sole's "
                   f"lowest point belongs at y {GROUND:.0f} (between {GROUND_RANGE[0]:.0f} and {GROUND_RANGE[1]:.0f}).")
    if left < INSIDE[0] or right > INSIDE[1]:
        out.append(f"{who}It runs out of the frame: it spans x {left:.0f} to {right:.0f}, and must stay between x "
                   f"{INSIDE[0]:.0f} and {INSIDE[1]:.0f} (at most about 180 wide, centred on x 100).")
    limit = TOP_LOW if low else TOP_BOOT
    if top < limit:
        kind = "a low shoe's top stays below" if low else "a boot's top stays below"
        out.append(f"{who}It is too tall: its top is at y {top:.0f}, and {kind} y {limit:.0f}.")
    leg = m["leg"]
    a = opening + OPENING_GAP
    if a < LEG_IN_BOTTOM:
        shows = int(leg[_row(a):_row(LEG_IN_BOTTOM), _col(LEG_IN[0]):_col(LEG_IN[1])].sum())
        if shows > SHOWS_PX:
            out.append(f"{who}The leg is not inside the shoe: between y {a:.0f} and {LEG_IN_BOTTOM:.0f} it shows "
                       f"through the drawing in the middle (x {LEG_IN[0]:.0f} to {LEG_IN[1]:.0f}). From just below the "
                       "opening's front edge down to the sole, the upper must cover the leg completely.")
    above = opening - ABOVE_ROOM   # for every kind of shoe: a boot's opening front is the front of its shaft's top
    tab = bool(sheet.get("front_pull_tab"))   # the owner: a pull tab at the front shows, in front of the leg
    region = m["front"][:max(0, _row(above))]
    if tab:
        covers = int(region[:, _col(ABOVE[0]):_col(TAB[0])].sum() + region[:, _col(TAB[1]):_col(ABOVE[1])].sum())
        high = opening - TAB_ROOM
        if int(m["front"][:max(0, _row(high)), _col(TAB[0]):_col(TAB[1])].sum()) > COVERS_PX:
            out.append(f"{who}The pull tab at the front rises too high: it reaches above y {high:.0f}, more than "
                       f"{TAB_ROOM:.0f} units above the opening's front edge (y {opening:.0f}).")
    else:
        covers = int(region[:, _col(ABOVE[0]):_col(ABOVE[1])].sum())
    if covers > COVERS_PX:
        out.append(f"{who}It hides the leg above its opening: something in front of the leg is drawn over its middle "
                   f"higher than y {above:.0f}, more than {ABOVE_ROOM:.0f} units above the opening's front edge (y "
                   f"{opening:.0f}). Nothing in front of the leg covers it above the opening (only a low shoe's collar "
                   "sides may rise a little beside the leg); what is behind the leg, such as the back of the collar or "
                   "of the shaft or a pull tab at the back, belongs in the part behind the leg, which the leg covers. A "
                   "pull tab at the FRONT is the one exception: it stays in front, centred on the leg, with "
                   "front_pull_tab true in the sheet.")
    where = OPENING_STRIP_TAB if tab else OPENING_STRIP
    strip = leg[:, _col(where[0]):_col(where[1])].sum(axis=1)
    start = _row(BAND_BOX[1]) + 2
    hidden = next((r for r in range(start, _row(BAND_BOX[3]) - 2) if strip[r] <= 1), None)   # within the band
    if hidden is not None and abs(_y(hidden) - opening) > OPENING_SLACK:
        out.append(f"{who}The sheet's opening_front_y is {opening:.0f}, but the drawing first covers the middle of the "
                   f"leg at about y {_y(hidden):.0f}: give the height where the drawing's front edge really crosses "
                   "the leg.")
    return out


def checks(left, right, sheet: Mapping) -> list[str]:
    """What is wrong with a drawing, measured from renders of it, in plain words; empty when nothing is. `left` and
    `right` are its shoes (`side`); `sheet` is the feature sheet (its silhouette's height and its opening_front_y are
    read). A right drawing is checked the same way; a sheet that says a mark is on one side only needs one."""
    out = _checks_one(side(left), sheet, "")
    if right:
        out += _checks_one(side(right), sheet, "The right shoe: ")
    elif sheet.get("one_side_mark"):
        out.append("The sheet says a mark is on one side only, but there is no right drawing: draw the viewer's right "
                   "shoe too, with the mark on its outer side, reading the right way round.")
    return out


# ------------------------------------------------------------------ kept, for the outfit figure

VERSION = 2   # the stored drawing's shape: 2 has each shoe as {behind, front}; 1 had one SVG text, all in front


@dataclass(frozen=True)
class Stored:
    """A drawing kept with the item, as the outfit figure places it: its shoes made safe (the viewer's left one, and
    the right one when it is drawn on its own), and where in the frame its opening is, from its sheet: the front of
    the opening (`opening`, opening_front_y), its highest point (`top`, top_y), the instep (`instep`, instep_y: above
    a low shoe's opening front and below a boot's, as the figure tells a shaft by), and whether it is a low shoe (its
    toe turns out below its opening front) or a boot (below its instep: `hinge`)."""
    left: Side
    right: Side | None
    opening: float
    top: float
    instep: float
    low: bool

    @property
    def hinge(self) -> float:
        return self.opening if self.low else self.instep


def _height(sheet: Mapping, key: str) -> float:
    v = sheet.get(key)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not -200 <= v <= GROUND:
        raise DrawingError(f"The drawing's sheet has no usable {key}.")
    return float(v)


def stored(value) -> Stored:
    """A drawing as kept with the item (`shoedraw`: version 1 or 2) read for the outfit figure. Raises `DrawingError`
    when it cannot be drawn there (its shoes cannot be made safe, or its sheet does not say where its opening is)."""
    if not isinstance(value, Mapping) or not isinstance(value.get("sheet"), Mapping):
        raise DrawingError("The drawing has no sheet.")
    sheet = value["sheet"]
    opening, top, instep = (_height(sheet, k) for k in ("opening_front_y", "top_y", "instep_y"))
    silhouette = sheet.get("silhouette") if isinstance(sheet.get("silhouette"), Mapping) else {}
    height = silhouette.get("height")
    low = height in LOW if height in (*LOW, "ankle", "boot") else instep < opening
    instep = min(instep, opening - 1.0) if low else max(instep, opening + 1.0)
    return Stored(side(value.get("left")), side(value["right"]) if value.get("right") else None, opening, top, instep,
                  low)
