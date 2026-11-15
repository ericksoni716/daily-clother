"""A traced shoe seen from the front on the As worn figure (#192, stage 2c).

The traced shoes here are built by hand (or traced from a photo drawn by `shoe_photos`; no real photos), so where
each panel, mark and lace should land is known.
"""
import hashlib
import math
import re

import pytest

from closet.drawing import figure as fig
from closet.drawing import frontshoe, traced
from closet.drawing.figure import K_PX, Piece, figure, plan

from .test_figure import SHORTS, TEE, TROUSERS, _flat, _inside, answer

US = [i / 40 for i in range(41)]
BASE, PANEL, MARK, LACE = "#2a3f8f", "#cc2222", "#22cc22", "#ff00ff"


def rect(u0, u1, h0, h1):
    return [[u0, h0], [u1, h0], [u1, h1], [u0, h1]]


def made(style="low_sneaker", sole=2.0, spring=0.8, taller=0.0, panels=(), marks=(), laces=None, ok=True):
    """A traced shoe as stage 2a would give it: its profile from the style's table (`taller` cm added to the top
    line), a sole `sole` cm thick with `spring` cm of toe spring, and the given colour panels and marks."""
    table = frontshoe.STYLES[style][2]
    bottom = [max(0.0, (u - 0.8) / 0.2) * spring for u in US]
    top = [b + sole + frontshoe._interp(table, u) + taller for u, b in zip(US, bottom, strict=True)]
    regions = [traced.Region(BASE, "silhouette", [[rect(0.0, 1.0, 0.0, 12.0)]], ["upper"])]
    regions += [traced.Region(c, "upper", [[ring]], [label]) for c, ring, label in panels]
    regions.append(traced.Region("#f4f4f0", "sole", [[rect(0.0, 1.0, 0.0, sole)]], ["midsole"]))
    return traced.TracedShoe(
        version=traced.VERSION, approach="test", cutout_by="test",
        profile=traced.Profile(u=list(US), top=top, bottom=bottom, sole=[sole] * len(US)),
        parts=[traced.Part("midsole", "#f4f4f0", True), traced.Part("outsole", "#f4f4f0", False)],
        marks=[traced.Mark("panel", c, sum(q[0] for q in ring) / 4, sum(q[1] for q in ring) / 4, 1.0, 1.0, 0.0, 1,
                           [ring]) for c, ring in marks],
        laces=laces, eyelets=None, stitching=None, style=style, confidence=0.9,
        gate={"ok": ok, "reasons": [] if ok else ["blurred"], "notes": [], "told": {}, "signals": {}}, regions=regions)


def spec_of(category="sneakers", style="low_sneaker", bottom=SHORTS):
    shoes = Piece(category, answer(category, shoe_style=style), "#5a3a22")
    return plan(dict(base=TEE, bottom=bottom, shoes=shoes)).get("shoes").spec


def front(t, spec=None, **kw):
    return fig.front_shoe(spec or spec_of(), K_PX, uid="z", ankle=fig._ankle(), toes=fig.TOE_LINE, traced=t, **kw)


def painted(body: str, colour: str) -> list[list[tuple[float, float]]]:
    """The outlines filled with `colour`, each as its points."""
    return [_flat(sub) for d in re.findall(rf'<path d="([^"]+)" fill="{colour}"', body)
            for sub in re.findall(r"M[^M]+", d)]


def area(pts) -> float:
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1], strict=True))) / 2


# ------------------------------------------------------------------ nothing changes for an untraced shoe

UNTRACED = [("sneakers", "low_sneaker"), ("sneakers", "runner"), ("sneakers", "slip_on"), ("sneakers", "high_top"),
            ("dress_shoes", "loafer"), ("dress_shoes", "derby"), ("dress_shoes", "oxford"), ("boots", "boot"),
            ("boots", "chelsea_boot"), ("sandals", "sandal")]
# taken before stage 2c; change it only with a change meant to redraw untraced shoes, and say so in the pull request
UNTRACED_DIGEST = "e8991667064d4dbc9438c0f7fb9f6999a23374b2915ebd718f3077c0e61ddf11"


def test_an_untraced_shoe_is_drawn_exactly_as_before():
    h = hashlib.sha256()
    for c, s in UNTRACED:
        shoes = Piece(c, answer(c, shoe_style=s), "#5a3a22")
        for bottom in (SHORTS, TROUSERS):
            pieces = dict(base=TEE, bottom=bottom, shoes=shoes)
            h.update(figure(pieces, uid="d").encode())
            f = fig.front_shoe(plan(pieces).get("shoes").spec, K_PX, uid="z", ankle=fig._ankle(), toes=fig.TOE_LINE)
            h.update((f.outline + f.body + f.defs).encode())
    assert h.hexdigest() == UNTRACED_DIGEST


@pytest.mark.parametrize("bad", [None, made(ok=False), "not a traced shoe", '{"version": 999}'],
                         ids=["none", "gate", "text", "newer"])
def test_a_shoe_whose_trace_cannot_be_used_keeps_todays_drawing(bad):
    today = front(None)
    drawn = front(bad)
    assert (drawn.outline, drawn.body, drawn.defs) == (today.outline, today.body, today.defs)


def test_a_sandal_keeps_its_own_drawing():
    spec = spec_of("sandals", "sandal")
    today, drawn = front(None, spec), front(made(), spec)
    assert (drawn.outline, drawn.body, drawn.defs) == (today.outline, today.body, today.defs)


def test_a_traced_shoe_on_the_figure_comes_from_its_trace_and_without_one_does_not():
    t = made(panels=[(PANEL, rect(0.86, 1.0, 0.0, 20.0), "toe_box")])
    shoes = Piece("sneakers", answer("sneakers", shoe_style="low_sneaker"), "#5a3a22")
    plain = figure(dict(base=TEE, bottom=SHORTS, shoes=shoes), uid="d")
    worn = figure(dict(base=TEE, bottom=SHORTS, shoes=Piece(**{**shoes.__dict__, "traced": t})), uid="d")
    assert PANEL not in plain and PANEL in worn and BASE in worn
    assert worn == figure(dict(base=TEE, bottom=SHORTS, shoes=Piece(**{**shoes.__dict__, "traced": t.to_json()})), uid="d")


def test_the_drawing_is_the_same_every_time_and_from_its_json():
    t = made(panels=[(PANEL, rect(0.86, 1.0, 0.0, 20.0), "toe_box")], marks=[(MARK, rect(0.35, 0.6, 3.0, 4.5))],
             laces=traced.Row(5, 1.0, LACE, [[0.5 + 0.06 * i, 7.0] for i in range(5)]))
    a, b, c = front(t), front(t), front(t.to_json())
    assert (a.outline, a.body, a.defs) == (b.outline, b.body, b.defs) == (c.outline, c.body, c.defs)


# ------------------------------------------------------------------ the shape comes from the trace

def test_the_shape_follows_the_traced_profile():
    def height(t):
        x0, y0, x1, y1 = front(t).bbox
        return y1 - y0

    plain, tall, thick = made(), made(taller=2.0), made(sole=3.5)
    assert height(tall) > height(plain) + 1.0 * K_PX
    assert height(thick) > height(plain) + 1.0 * K_PX
    # the sole drawn as thick as traced: the outline's lowest point to the upper's lowest
    def sole_band(t):
        f = front(t)
        upper = _flat(re.search(rf'<path d="([^"]+)" fill="{BASE}"', f.body).group(1))
        return max(y for _, y in _flat(f.outline)) - max(y for _, y in upper)

    assert sole_band(thick) > sole_band(plain) + 1.0 * K_PX


def test_a_boot_takes_its_shaft_height_from_the_trace():
    spec = spec_of("boots", "boot")
    low, high = made(style="boot"), made(style="boot", taller=5.0)
    assert front(high, spec).anchors["top"][1] < front(low, spec).anchors["top"][1] - 3.0 * K_PX


# ------------------------------------------------------------------ the panels and marks, on the solid

def test_a_toe_cap_is_painted_on_the_toe_box_facing_the_viewer():
    f = front(made(panels=[(PANEL, rect(0.86, 1.0, 0.0, 20.0), "toe_box")]))
    pieces = painted(f.body, PANEL)
    assert pieces
    outline = _flat(f.outline)
    pts = [q for piece in pieces for q in piece]
    assert all(_inside(q, outline) for q in pts)
    # low on the drawing, at the near end, and to the viewer's left (where the toe turns out)
    ys = [y for _, y in outline]
    assert min(y for _, y in pts) > (min(ys) + max(ys)) / 2
    assert sum(x for x, _ in pts) / len(pts) < 0
    # the toe box faces the viewer: it shows nearly as wide as the shoe
    xs = [x for x, _ in outline]
    assert max(x for x, _ in pts) - min(x for x, _ in pts) > 0.6 * (max(xs) - min(xs))


def test_a_heel_counter_shows_only_at_the_back_behind_the_ankle():
    t = made(panels=[(PANEL, rect(0.0, 0.2, 0.0, 20.0), "heel_counter")])
    f = front(t)
    body = f.body
    toe = front(made(panels=[(PANEL, rect(0.86, 1.0, 0.0, 20.0), "toe_box")]))
    back = [q for piece in painted(body, PANEL) for q in piece]
    toe_pts = [q for piece in painted(toe.body, PANEL) for q in piece]
    assert back and max(y for _, y in back) < min(y for _, y in toe_pts)   # far up the drawing: the back
    # painted with the shoe, before the ankle stands in it
    assert body.index(f'fill="{PANEL}"') < body.index('clip-path="url(#za)"')


def test_a_mark_at_the_back_of_the_heel_is_hidden():
    f = front(made(marks=[(MARK, rect(0.0, 0.05, 3.0, 5.0))]))
    assert not painted(f.body, MARK)


def test_a_mark_on_the_side_is_foreshortened_not_pasted_flat():
    ring = rect(0.3, 0.6, 2.5, 4.5)
    f = front(made(marks=[(MARK, ring)]))
    seen = sum(area(p) for p in painted(f.body, MARK))
    flat = 0.3 * frontshoe.LENGTH * 2.0 * K_PX ** 2   # its size as the photo saw it, at the drawing's scale
    assert seen < 0.5 * flat


def test_a_mark_on_the_toe_is_drawn_on_the_front():
    f = front(made(marks=[(MARK, rect(0.9, 0.97, 2.2, 3.2))]))
    pieces = painted(f.body, MARK)
    assert pieces and sum(area(p) for p in pieces) > 0.3 * K_PX ** 2


def test_thin_lines_of_colour_are_not_panels():
    f = front(made(panels=[(PANEL, rect(0.05, 0.95, 6.0, 6.15), "collar")]))   # a highlight along the top
    assert not painted(f.body, PANEL)


# ------------------------------------------------------------------ the laces

def lace_strokes(body: str, colour: str) -> int:
    return len(re.findall(rf'stroke="{colour}"', body))


def test_the_laces_are_drawn_as_counted_in_their_colour():
    row = traced.Row(5, 1.0, LACE, [[0.5 + 0.06 * i, 7.0] for i in range(5)])
    assert lace_strokes(front(made(laces=row)).body, LACE) == 5


def test_too_few_traced_laces_give_the_styles_laces():
    row = traced.Row(2, 1.0, LACE, [[0.1, 6.0], [0.2, 6.0]])   # more likely a collar than laces
    body = front(made(laces=row)).body
    assert lace_strokes(body, LACE) == 0
    assert body.count('stroke-linecap="round"') >= 4   # the style's lacing is still drawn


# ------------------------------------------------------------------ a traced photo, end to end

def test_a_traced_photo_is_drawn_from_the_front():
    from closet.drawing import trace as T

    from . import shoe_photos as S
    shoe = S.Shoe(upper=S.NAVY, heel_counter=S.RED, stripes=S.WHITE, laces=S.WHITE, midsole=(250, 250, 250),
                  outsole=(60, 60, 60))
    img, _ = S.draw(shoe, noise=1)
    t = traced.traced_shoe(T.trace_photo(img, None))
    assert frontshoe.usable_trace(t) is not None
    drawn, today = front(t), front(None)
    assert drawn.body != today.body
    assert math.isfinite(drawn.bbox[0]) and drawn.bbox[2] - drawn.bbox[0] < 1.3 * (today.bbox[2] - today.bbox[0])
    assert drawn.body == front(t.to_json()).body
