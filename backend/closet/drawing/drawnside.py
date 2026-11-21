"""A shoe's side drawn by Claude from its photos: the frame, made safe, checked and shown. No call to Claude is made
here; `closet/tagger/shoedrawing.py` asks for the drawing (`draw_side`) and `closet/shoedraw.py` keeps it with the
item's drawing for the figure (its `side` entry).

The side drawing is the item's own drawing, the one the closet tile, the Wardrobe's Drawings view and the item page
show (`illustrations.make`), so it is drawn on the templates' card in their style: a 400 by 460 card, the shoe seen
exactly side-on with the toe to the left, the toe tip at x 40, the back of the heel at x 360, the ground at y 330,
the bold outline 3.8 wide and the inner lines 1.5, in #26231f (`trace.py`'s measures, which the traced drawing and
the templates use too). It comes back as bare SVG elements in that frame.

- `sanitise` makes it safe with the front drawing's rules (`drawn.sanitise`), after taking off an `<svg>` around it.
- `Measures` are the shoe's heights as shares of its length, measured from its trace (`TracedShoe.profile`) when it
  has one: given to Claude as numbers, and checked.
- `checks` measures a render of the drawing and says in plain words what is wrong: it stands on the ground line, stays
  on the card, its toe and heel are at about x 40 and x 360, its toe is on the left, it is not taller than the card
  allows, and, with measures, it is as tall for its length as the photo says.
- `card_svg` is the drawing as the app shows it; `check_png` the picture Claude checks it on (large, and at the size
  of a closet tile).
"""
from __future__ import annotations

import io
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from functools import cache

from . import drawn
from .illustrate import CARD, INK
from .trace import CARD_H, CARD_W, INNER_W, OUTLINE_W, SHOE_G, SHOE_L, SHOE_X0
from .traced import LENGTH

TOE_X, HEEL_X, GROUND = SHOE_X0, SHOE_X0 + SHOE_L, SHOE_G   # 40, 360, 330
TOP_MIN = 60.0                    # nothing above this y: the card keeps room over the tallest boot
GROUND_RANGE = (324.0, 336.0)     # where the lowest painted point must be
TOE_RANGE = (28.0, 54.0)          # where the toe tip must be (x)
HEEL_RANGE = (346.0, 372.0)       # where the back of the heel must be (x)
ON_CARD = (6.0, 394.0)            # nothing painted outside these x
TOE_SHARE = 0.15                  # the toe box is measured this share of the length back from the toe
HEIGHT_SLACK = 0.15               # the drawing's height for its length may differ this much (a share) from the trace's
TOE_SLACK_UNITS = 6.0             # and its toe box's height at least this many units, however small the toe box
TOE_RIGHT_UNITS = 5.0             # a drawing whose toe end stands this much taller than its heel end is the wrong way
BOX = (-40, -40, 480, 540)        # what the checks render, in frame units: wider than the card, so what runs off shows
BIG_W, SMALL_W, GAP = 560, 120, 20   # the check picture: the card large, and at about a closet tile's width

_SVG_OPEN = re.compile(r"^\s*(?:<\?xml[^>]*\?>\s*)?<svg\b[^>]*>", re.I)
_SVG_CLOSE = re.compile(r"</svg>\s*$", re.I)


# ------------------------------------------------------------------ made safe

def sanitise(fragment) -> str:
    """The drawing with only plain shapes left (`drawn.sanitise`'s rules); an `<svg>` around it is taken off first.
    Raises `drawn.DrawingError` as `drawn.sanitise` does."""
    if not isinstance(fragment, str):
        raise drawn.DrawingError("The drawing is not SVG text.")
    text = fragment.strip()
    if _SVG_OPEN.match(text):
        text = _SVG_CLOSE.sub("", _SVG_OPEN.sub("", text, count=1))
    return drawn.sanitise(text)


# ------------------------------------------------------------------ measured from the trace

@dataclass(frozen=True)
class Measures:
    """The shoe's heights as shares of its length (toe tip to back of heel), as the trace measured them in its side
    photo: the sole's thickness under the heel and under the toe; the upper's top above the ground at the toe box (15%
    of the length back from the toe), at the throat (where the lacing or vamp meets the opening, 60% of the way from
    the heel), at the collar's lowest point, at the heel, and at its highest."""
    sole_heel: float
    sole_toe: float
    toe_box: float
    throat: float
    collar_dip: float
    heel: float
    tallest: float

    def to_json(self) -> dict:
        return {k: round(v, 3) for k, v in asdict(self).items()}

    @classmethod
    def from_json(cls, value) -> Measures | None:
        """Measures as passed around (`to_json`), or None when they cannot be read."""
        if isinstance(value, Measures):
            return value
        if not isinstance(value, Mapping):
            return None
        try:
            got = {k: float(value[k]) for k in cls.__dataclass_fields__}
        except (KeyError, TypeError, ValueError):
            return None
        return cls(**got) if all(0 <= v <= 2 for v in got.values()) and got["tallest"] > 0 else None


def measures(profile) -> Measures | None:
    """The shares measured from a trace's profile (`traced.Profile`: u from the heel, 0, to the toe, 1; heights in cm
    for a shoe `LENGTH` long); None when the profile is empty or flat."""
    import numpy as np

    try:
        u = np.asarray(profile.u, float)
        top = np.asarray(profile.top, float)
        sole = np.asarray(profile.sole, float)
    except (AttributeError, TypeError, ValueError):
        return None
    if len(u) < 5 or len(top) != len(u) or len(sole) != len(u) or not np.all(np.diff(u) > 0) or top.max() <= 0:
        return None

    def at(values, x: float) -> float:
        return float(np.interp(x, u, values)) / LENGTH

    back, mid = u <= 0.12, (u > 0.12) & (u <= 0.5)
    return Measures(sole_heel=at(sole, 0.08), sole_toe=at(sole, 1 - 0.12), toe_box=at(top, 1 - TOE_SHARE),
                    throat=at(top, 0.6), collar_dip=float(top[mid].min()) / LENGTH if mid.any() else at(top, 0.3),
                    heel=float(top[back].max()) / LENGTH if back.any() else at(top, 0.05),
                    tallest=float(top.max()) / LENGTH)


def y_of(share: float) -> float:
    """Where a height of `share` of the length lands in the frame (the ground at y 330, the length 320 units)."""
    return GROUND - share * SHOE_L


def measures_text(m: Measures) -> str:
    """The measures in words, as shares of the length and as places in the frame, for the prompts."""
    def line(name: str, share: float, where: str) -> str:
        return f"- {name}: {share:.2f} of the length, {where}"
    return "\n".join([
        line("the sole under the heel", m.sole_heel, f"about {m.sole_heel * SHOE_L:.0f} units thick"),
        line("the sole under the toe", m.sole_toe, f"about {m.sole_toe * SHOE_L:.0f} units thick"),
        line("the top of the toe box (15% of the length back from the toe tip, at x 88)", m.toe_box,
             f"at about y {y_of(m.toe_box):.0f}"),
        line("the throat (where the lacing or the vamp meets the opening, at about x 232)", m.throat,
             f"at about y {y_of(m.throat):.0f}"),
        line("the collar's lowest point", m.collar_dip, f"at about y {y_of(m.collar_dip):.0f}"),
        line("the top at the heel", m.heel, f"at about y {y_of(m.heel):.0f}"),
        line("the highest point of the shoe", m.tallest, f"at about y {y_of(m.tallest):.0f}"),
    ])


# ------------------------------------------------------------------ checked

def _alpha(svg: str):
    import numpy as np
    from PIL import Image

    x0, y0, w, h = BOX
    doc = f'<svg xmlns="{drawn.SVG_NS}" viewBox="{x0} {y0} {w} {h}" width="{w}" height="{h}">{svg}</svg>'
    with Image.open(io.BytesIO(drawn.render_png(doc, w, h))) as im:
        return np.asarray(im.convert("RGBA"))[:, :, 3] > 128


def measure(svg: str) -> dict | None:
    """Where a (sanitised) side drawing is painted, in frame units: its box (left, top, right, bottom), its height for
    its length, its toe box's height (`TOE_SHARE` of its length in from the left), and the height of each end (the
    highest point in the first and the last tenth of its length). None when nothing is painted."""
    import numpy as np

    a = _alpha(svg)
    rows, cols = np.where(a.any(axis=1))[0], np.where(a.any(axis=0))[0]
    if not len(rows):
        return None
    x0, y0 = BOX[0], BOX[1]
    left, right = float(cols[0] + x0), float(cols[-1] + 1 + x0)
    top, bottom = float(rows[0] + y0), float(rows[-1] + 1 + y0)
    length = max(right - left, 1.0)

    def height_at(x: float) -> float:
        col = a[:, int(round(x - x0))]
        hit = np.where(col)[0]
        return bottom - float(hit[0] + y0) if len(hit) else 0.0

    def end_height(c0: float, c1: float) -> float:
        part = a[:, int(round(c0 - x0)):max(int(round(c1 - x0)), int(round(c0 - x0)) + 1)]
        hit = np.where(part.any(axis=1))[0]
        return bottom - float(hit[0] + y0) if len(hit) else 0.0

    return {"box": (left, top, right, bottom), "length": length, "height": bottom - top,
            "toe_box": height_at(left + TOE_SHARE * length),
            "toe_end": end_height(left, left + 0.1 * length), "heel_end": end_height(right - 0.1 * length, right)}


def checks(svg: str, measured: Measures | None = None) -> list[str]:
    """What is wrong with a side drawing, measured from a render of it, in plain words; empty when nothing is. With
    `measured` (from the shoe's trace), its height at the heel and at the toe box, for its length, are checked against
    the photo's within `HEIGHT_SLACK` (a photo taken a little off side-on foreshortens the length, so the trace's
    heights come out a little high; 15% allows for about 30 degrees, and still catches a drawing a third too low). The
    heel and the toe box, not the highest point: a bow of the laces or a pull tab may stand above the collar in one and
    not the other."""
    m = measure(svg)
    if m is None:
        return ["Nothing of it is painted on the card."]
    left, top, right, bottom = m["box"]
    out = []
    if not GROUND_RANGE[0] <= bottom <= GROUND_RANGE[1]:
        out.append(f"It does not stand on the ground line: its lowest point is at y {bottom:.0f}, and the sole's lowest "
                   f"point belongs at y {GROUND:.0f}.")
    if left < ON_CARD[0] or right > ON_CARD[1] or top < 0 or bottom > CARD_H:
        out.append(f"It runs off the card: it spans x {left:.0f} to {right:.0f} and y {top:.0f} to {bottom:.0f}; the card "
                   f"is x 0 to {CARD_W} and y 0 to {CARD_H}.")
    elif not (TOE_RANGE[0] <= left <= TOE_RANGE[1] and HEEL_RANGE[0] <= right <= HEEL_RANGE[1]):
        out.append(f"It is not where the frame puts it: it spans x {left:.0f} to {right:.0f}, and the toe tip belongs at "
                   f"x {TOE_X:.0f} and the back of the heel at x {HEEL_X:.0f}.")
    if m["toe_end"] > m["heel_end"] + TOE_RIGHT_UNITS:
        out.append("Its toe seems to point right: its right end stands taller than its left end. The toe points LEFT, "
                   f"at x {TOE_X:.0f}, and the heel is at the right, at x {HEEL_X:.0f}.")
    if top < TOP_MIN:
        out.append(f"It is too tall for the card: its top is at y {top:.0f}, and nothing goes above y {TOP_MIN:.0f}.")
    if measured is not None:
        length = m["length"]
        heel, want = m["heel_end"], measured.heel * length
        if abs(heel - want) > HEIGHT_SLACK * want:
            word = "low" if heel < want else "tall"
            out.append(f"It is too {word} for its length: at the heel its top is {heel / length:.2f} of its length above "
                       f"the ground (y {bottom - heel:.0f}), and measured from the photo it is {measured.heel:.2f} (y "
                       f"{bottom - want:.0f}). Redraw the whole shoe to the measured proportions, not only its heel.")
        toe, want_toe = m["toe_box"], measured.toe_box * length
        if abs(toe - want_toe) > max(HEIGHT_SLACK * want_toe, TOE_SLACK_UNITS):
            word = "low and pointed" if toe < want_toe else "tall"
            out.append(f"The toe box is too {word}: 15% of the length back from the toe tip, its top is {toe:.0f} units "
                       f"above the ground, and measured from the photo it is about {want_toe:.0f} (y "
                       f"{bottom - want_toe:.0f}).")
    return out


# ------------------------------------------------------------------ shown

def card_svg(svg: str) -> str:
    """The side drawing as the item's drawing: made safe, on the templates' card."""
    return (f'<svg xmlns="{drawn.SVG_NS}" viewBox="0 0 {CARD_W} {CARD_H}" width="{CARD_W}" height="{CARD_H}">'
            f'<rect width="{CARD_W}" height="{CARD_H}" rx="18" fill="{CARD}"/>{sanitise(svg)}</svg>')


def check_svg(svg: str) -> str:
    """The card large (560 px wide) and at about a closet tile's width (120 px) side by side, on white: what Claude
    looks at to check its side drawing."""
    card = card_svg(svg)
    inner = card[card.index(">") + 1:-len("</svg>")]
    big_h, small_h = BIG_W * CARD_H / CARD_W, SMALL_W * CARD_H / CARD_W
    w, h = BIG_W + GAP + SMALL_W, round(big_h)
    view = f'viewBox="0 0 {CARD_W} {CARD_H}"'
    return (f'<svg xmlns="{drawn.SVG_NS}" viewBox="0 0 {w} {h}" width="{w}" height="{h}"><rect width="{w}" height="{h}" '
            f'fill="#ffffff"/><svg x="0" y="0" width="{BIG_W}" height="{big_h:.1f}" {view}>{inner}</svg>'
            f'<svg x="{BIG_W + GAP}" y="{big_h - small_h:.1f}" width="{SMALL_W}" height="{small_h:.1f}" {view}>{inner}'
            f'</svg></svg>')


def check_png(svg: str) -> bytes:
    """`check_svg` as one PNG."""
    out = check_svg(svg)
    w, h = (int(v) for v in re.search(r'width="(\d+)" height="(\d+)"', out).groups())
    return drawn.render_png(out, w, h)


@cache
def style_svgs() -> dict[str, str]:
    """The app's own plain side drawings of an ordinary sneaker and an ordinary boot (the templates, from no more
    than their kind and a colour), shown to Claude as examples of the style, the card and the frame."""
    from .item import svg_from_fields  # only here: the templates import the tagger's schema

    return {"sneaker": svg_from_fields("sneakers", "#e8e6e0"), "boot": svg_from_fields("boots", "#7a5236")}


STYLE = f"stroke {INK}, stroke-width {OUTLINE_W:g} (the bold outline); stroke-width {INNER_W:g} (inner lines)"
