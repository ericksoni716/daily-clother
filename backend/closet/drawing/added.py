"""What Claude drew onto an item's drawing at the owner's word: parts laid over the template's own.

The owner can ask Claude to add to a garment's drawing what no detail shows (a patch on a sleeve, a contrast panel,
a tab, a line of stitching). Claude answers with parts in the template's own coordinates (the card is W x H), each
one of four kinds (`ROLES`), and they are drawn as the template's own parts are: on the item's drawing, after the
template's parts, and on the As worn figure, where they are moved onto the wearer with the rest of the garment
(`fitting.warp`), so a patch on a sleeve stays on the sleeve as it hangs round the arm.

Nothing Claude writes goes into a drawing as it is: each part is read here, its path written again from its numbers
(absolute M, L, Q, C and Z only, every point an "x,y" pair, as the figure's warp needs), its colour checked, and a
part that cannot be read is left out. Pure: no I/O.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .fitting import points, sleeves
from .templates import H, Part, W

# what a part can be, and the template role it is drawn as: a piece in its own colour with an edge (a patch, a
# panel, a pocket), a small piece in its own colour with no edge (a logo's shape, a stripe), topstitching (dashed, in
# the thread's colour) and a line with no fill (a seam, the edge of a flap, a zip's line)
ROLES = {"inlay": "inlay", "mark": "mark", "stitch": "stitch", "line": "line"}
MAX_PARTS = 30          # parts in all
MAX_POINTS = 120        # points in one part's path
MAX_WHAT = 80           # characters in what a part is
MARGIN = 20             # how far off the card a point may lie
_HEX = re.compile(r"#[0-9a-fA-F]{6}")
_TOKEN = re.compile(r"[A-Za-z]|-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
_ARITY = {"M": 1, "L": 1, "Q": 2, "C": 3, "Z": 0}   # points each command takes (M and L may repeat theirs)


class Unreadable(ValueError):
    """A part that cannot be drawn, with why in plain words."""


@dataclass(frozen=True)
class Added:
    """One part as kept with the item: what it is (Claude's few words), its kind, its path, its colour (None: the
    garment's own cloth, or for stitching the usual thread) and whether the garment's edge cuts it."""
    what: str
    role: str
    d: str
    color: str | None = None
    clip: bool = False

    def part(self) -> Part:
        return Part(self.d, ROLES[self.role], self.color, self.clip)

    def as_json(self) -> dict:
        return {"what": self.what, "role": self.role, "d": self.d, "color": self.color, "clip": self.clip}


def _f(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def path(d) -> str:
    """The path written again from its numbers, or Unreadable. Only absolute M, L, Q, C and Z; it starts with M."""
    if not isinstance(d, str) or not d.strip():
        raise Unreadable("it has no path")
    tokens = _TOKEN.findall(d)
    if "".join(tokens) != re.sub(r"[\s,]+", "", d):
        raise Unreadable("its path has something other than commands and numbers")
    out: list[str] = []
    cmd, nums, count = None, [], 0

    def flush():
        nonlocal count
        if cmd is None:
            return
        n = _ARITY[cmd]
        if n == 0:
            if nums:
                raise Unreadable("its path closes with numbers after it")
            out.append("Z")
            return
        if not nums or len(nums) % (2 * n):
            raise Unreadable(f"its path has a {cmd} with the wrong count of numbers")
        if cmd in "QC" and len(nums) != 2 * n:
            raise Unreadable(f"its path has a {cmd} with the wrong count of numbers")
        pts = [(nums[i], nums[i + 1]) for i in range(0, len(nums), 2)]
        for x, y in pts:
            if not (-MARGIN <= x <= W + MARGIN and -MARGIN <= y <= H + MARGIN):
                raise Unreadable("its path goes off the drawing")
        count += len(pts)
        if cmd == "M" and len(pts) > 1:   # M with more pairs: the rest are lines
            out.append(f"M {_f(pts[0][0])},{_f(pts[0][1])}")
            out.append("L " + " ".join(f"{_f(x)},{_f(y)}" for x, y in pts[1:]))
        else:
            out.append(f"{cmd} " + " ".join(f"{_f(x)},{_f(y)}" for x, y in pts))

    for t in tokens:
        if t.isalpha():
            t = "Z" if t == "z" else t   # closing has no numbers, so a relative z is the same as Z
            if t not in _ARITY:
                raise Unreadable(f"its path uses {t}, which is not drawn: only M, L, Q, C and Z")
            flush()
            if not out and t != "M":
                raise Unreadable("its path does not start with M")
            cmd, nums = t, []
        else:
            if cmd is None:
                raise Unreadable("its path does not start with M")
            nums.append(float(t))
    flush()
    if count < 2:
        raise Unreadable("its path has fewer than two points")
    if count > MAX_POINTS:
        raise Unreadable("its path has too many points")
    return " ".join(out)


def read_one(raw) -> Added:
    """One part from Claude's answer (or as kept), or Unreadable."""
    if not isinstance(raw, dict):
        raise Unreadable("it is not a part")
    role = raw.get("role")
    if role not in ROLES:
        raise Unreadable(f"its kind {role!r} is not one of {', '.join(ROLES)}")
    color = raw.get("color")
    if color in ("", "none", "null"):
        color = None
    if color is not None and not (isinstance(color, str) and _HEX.fullmatch(color.strip())):
        raise Unreadable(f"its colour {color!r} is not a colour like #1a2b3c")
    what = raw.get("what")
    what = " ".join(what.split())[:MAX_WHAT] if isinstance(what, str) else ""
    return Added(what, role, path(raw.get("d")), color.strip().lower() if color else None, raw.get("clip") is True)


def read(raw) -> tuple[list[Added], list[str]]:
    """The parts that can be drawn, in their order, and why each of the others cannot (in plain words, numbered as
    given). At most MAX_PARTS are kept."""
    if not isinstance(raw, list):
        return [], ["the parts are not a list"] if raw is not None else []
    kept, why = [], []
    for i, one in enumerate(raw, 1):
        try:
            part = read_one(one)
        except Unreadable as e:
            why.append(f"part {i}: {e}")
            continue
        if len(kept) >= MAX_PARTS:
            why.append(f"part {i}: there are more than {MAX_PARTS} parts")
            continue
        kept.append(part)
    return kept, why


def parts(raw) -> tuple[Part, ...]:
    """What is kept with an item (a list of parts as JSON) as the template's parts to lay over its own; () when there
    is nothing, or nothing that can be read. Never raises."""
    try:
        return tuple(a.part() for a in read(raw)[0])
    except Exception:
        return ()


# --------------------------------------------------------------- the grid Claude places parts by

# a digit as strokes of a seven-segment display in a 4 x 7 box (no font is needed to render it): the segments are
# a top, b top right, c bottom right, d bottom, e bottom left, f top left, g middle
_SEGMENTS = {"a": "M0,0H4", "b": "M4,0V3.5", "c": "M4,3.5V7", "d": "M0,7H4", "e": "M0,3.5V7", "f": "M0,0V3.5",
             "g": "M0,3.5H4"}
_DIGITS = {"0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd", "6": "afgedc", "7": "abc",
           "8": "abcdefg", "9": "abcdfg", "-": "g"}
_GRID_DY = re.compile(r'<g transform="translate\(0 (-?\d+(?:\.\d+)?)\)">')


def _number(n: int, x: float, y: float, size: float, color: str) -> str:
    """`n` drawn as strokes, its top left corner at (x, y), `size` tall."""
    k = size / 7
    out = []
    for i, ch in enumerate(str(n)):
        segs = " ".join(_SEGMENTS[s] for s in _DIGITS[ch])
        out.append(f'<path d="{segs}" transform="translate({x + i * 6.2 * k:.1f} {y:.1f}) scale({k:.3f})" fill="none" '
                   f'stroke="{color}" stroke-width="{1.5 / k:.2f}" stroke-linecap="round"/>')
    return "".join(out)


def gridded(svg: str) -> str:
    """The item's drawing with a grid in the drawing's own coordinates (the ones parts are written in): a faint line
    every 10 units, a stronger one every 50, numbered along the top and the left. The drawing is placed on its card
    shifted down (`illustrate._draw`), so the grid is shifted with it."""
    m = _GRID_DY.search(svg)
    dy = float(m.group(1)) if m else 0.0
    lines, numbers = [], []
    blue, strong = "#1f6fd1", "#0b4fa3"
    for x in range(0, W + 1, 10):
        major = x % 50 == 0
        lines.append(f'<path d="M{x},{-dy:.1f}V{H - dy:.1f}" stroke="{strong if major else blue}" '
                     f'stroke-width="{0.7 if major else 0.35}" opacity="{0.75 if major else 0.4}"/>')
        if major and 0 < x < W:
            numbers.append(_number(x, x + 1.5, -dy + 2, 7, strong))
    first, last = int(-dy // 10) * 10, int((H - dy) // 10) * 10
    for y in range(first, last + 1, 10):
        major = y % 50 == 0
        lines.append(f'<path d="M0,{y}H{W}" stroke="{strong if major else blue}" stroke-width="{0.7 if major else 0.35}" '
                     f'opacity="{0.75 if major else 0.4}"/>')
        if major and -dy + 12 < y < H - dy - 2:
            numbers.append(_number(y, 2, y + 1.5, 7, strong))
    grid = f'<g transform="translate(0 {dy:.1f})">{"".join(lines)}{"".join(numbers)}</g>'
    return svg.replace("</svg>", grid + "</svg>") if "</svg>" in svg else svg


# --------------------------------------------------------------- the drawing's shape, in words for Claude

_ANCHOR_WORDS = {"neck": "the middle of the neck", "neck_point_l": "the neck's edge on your left",
                 "neck_point_r": "the neck's edge on your right", "shoulder_l": "the shoulder point on your left",
                 "shoulder_r": "the shoulder point on your right", "hem": "the middle of the hem",
                 "waist": "the middle of the waistband", "crotch": "the crotch", "leg_l": "the leg opening on your left",
                 "leg_r": "the leg opening on your right", "hem_out": "the outer corner of the hem on your left",
                 "hem_in": "the inner corner of the hem on your left"}


def _pt(p) -> str:
    return f"({_f(p[0])}, {_f(p[1])})"


def _box(d: str) -> str:
    pts = points(d)
    if not pts:
        return ""
    xs, ys = [x for x, _ in pts], [y for _, y in pts]
    return f"x {_f(min(xs))} to {_f(max(xs))}, y {_f(min(ys))} to {_f(max(ys))}"


def geometry(shape) -> str:
    """The template's shape (without anything Claude drew onto it), in lines Claude can place parts by: its outline,
    the box of its body, each sleeve's corners, its landmarks, and where its own parts lie."""
    lines = [f"The garment's outline: {shape.outline}",
             f"Its body (without the sleeves) lies within {_box(f'M {shape.body_box[0]},{shape.body_box[1]} L {shape.body_box[2]},{shape.body_box[3]}')}.",
             f"All of it lies within {_box(f'M {shape.bbox[0]},{shape.bbox[1]} L {shape.bbox[2]},{shape.bbox[3]}')}."]
    for s in sleeves(shape):
        where = "on your left (the wearer's right)" if s.side < 0 else "on your right (the wearer's left)"
        lines.append(f"The sleeve {where} hangs from its shoulder point {_pt(s.shoulder)}; its opening runs from "
                     f"{_pt(s.outer)} on its outer edge to {_pt(s.inner)} on its inner edge; its underarm is at "
                     f"{_pt(s.armpit)}. A part on it lies along it, between those edges.")
    marks = [f"{_ANCHOR_WORDS.get(k, k)} {_pt(v)}" for k, v in shape.anchors.items()]
    if marks:
        lines.append("Landmarks: " + "; ".join(marks) + ".")
    words = {"collar_r": "a collar leaf", "collar_l": "a collar leaf", "lapel_r": "a lapel", "lapel_l": "a lapel",
             "hole": "the inside of the neck", "band": "a band (a waistband, a rib cuff or hem)", "cuff": "a cuff",
             "trim": "a trim", "neckrib": "the neck's rib", "edge": "an edge line", "inlay": "a piece in its own colour",
             "stitch": "a line of stitching", "binding": "binding along an edge", "block": "a piece in another colour"}
    own = [f"{words.get(p.role, p.role)} at {_box(p.d)}" for p in shape.parts if words.get(p.role)]
    if own:
        lines.append("The drawing's own parts: " + "; ".join(own) + ".")
    return "\n".join(lines)
