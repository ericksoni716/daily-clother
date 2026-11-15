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

from .test_figure import SHORTS, TEE, TROUSERS, _clear, _flat, _inside, answer

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
# (changed once: a Chelsea boot's pull tab, at the back of its shaft, is drawn behind the leg, not over it)
UNTRACED_DIGEST = "67d97fa3f531603b8dbf311d6e8f23373dd2092b455f169410c5afd253ad0403"


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


def test_eyelets_traced_without_laces_still_get_their_laces():
    t = traced_photo("NAVY_DERBY")
    assert t.laces is None and t.eyelets.count >= frontshoe.LACES_MIN   # navy laces on navy: only the eyelets show
    spec = spec_of("sneakers", "derby")
    body = frontshoe.front_shoe(spec, K_PX, traced=t).body
    lace = spec.lace_color or frontshoe._lace_shade(frontshoe._Traced.of(t).base)
    assert lace_strokes(body, lace) == t.eyelets.count - 1   # a crossing between each two eyelets
    assert body.count("<circle") == 2 * t.eyelets.count


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


# ------------------------------------------------------------------ shoes the front view once got wrong (#205 review)

def near(colour: str, rgb, tol: float = 40.0) -> bool:
    return math.dist(frontshoe._rgb(colour), [v / 255 for v in rgb]) * 255 <= tol


_TRACES: dict = {}


def traced_photo(name: str, size=(1000, 560)):
    """The trace of one of `shoe_photos`' shoes (traced once per test run)."""
    if name not in _TRACES:
        from closet.drawing import trace as T

        from . import shoe_photos as S
        img, _ = S.draw(S.Shoe(**getattr(S, name)), size=size, noise=2)
        _TRACES[name] = traced.traced_shoe(T.trace_photo(img, None))
    return _TRACES[name]


def cells(t, words=None):
    tr = frontshoe._Traced.of(frontshoe.usable_trace(t), "round", words)
    return tr, [(i / frontshoe.GRID_U, math.sin(math.pi / 2 * (j + 0.5) / frontshoe.GRID_A), c, g)
                for _, i, j, c, g, part in tr.cells() if part == "foot"]


def test_the_toe_box_takes_the_colour_under_its_top_line_and_a_mudguard_stays_a_low_band():
    from . import shoe_photos as S
    tr, cs = cells(traced_photo("RED_BLACK_RUNNER"))
    toe = [(sa, c, g) for u, sa, c, g in cs if u >= 0.75]
    top = [g for sa, c, g in toe if sa >= 0.6]
    red = sum(g for sa, c, g in toe if sa >= 0.6 and near(c, S.RED, 60))
    assert red > 0.9 * sum(top)   # the toe box and the vamp, as the viewer sees them, are red
    black = [sa for sa, c, g in toe if near(c, S.BLACK, 40)]
    assert black and max(black) < 0.6   # the black mudguard only low round the toe
    assert near(tr.base, S.RED, 60)


def test_a_big_piece_in_the_laces_colour_is_still_a_panel():
    t = made(panels=[(PANEL, rect(0.45, 1.0, 0.0, 20.0), "laces")])   # the whole front, where the laces run
    assert painted(front(t).body, PANEL)


def test_a_dark_edge_along_the_top_line_does_not_colour_the_crest():
    # the top line's shade in a photo: a band just under it, darker, the length of the forefoot
    table = frontshoe.STYLES["low_sneaker"][2]
    edge = [[u, 2.0 + frontshoe._interp(table, u) + 1.0] for u in US if u >= 0.5]
    edge += [[u, 2.0 + frontshoe._interp(table, u) - 0.45] for u in reversed(US) if u >= 0.5]
    tr, cs = cells(made(spring=0.0, panels=[(PANEL, edge, "vamp")]))
    crest = [c for u, sa, c, g in cs if 0.6 <= u <= 0.9 and sa > 0.9]
    assert crest and PANEL not in crest


def test_the_sole_is_drawn_in_its_traced_bands():
    from . import shoe_photos as S
    t = traced_photo("RED_BLACK_RUNNER")
    tr = frontshoe._Traced.of(t)
    (lo, mid, red), (_, hi, white) = tr.bands[0], tr.bands[-1]
    assert near(red, S.RED, 60) and near(white, S.WHITE, 40) and lo == 0.0 and hi == 1.0
    assert 0.15 <= mid <= 0.5   # the outsole's share of the thickness, as drawn (0.9 of 3.6 cm; the window adds a little)
    body = front(t).body
    assert f'fill="{red}"' in body and f'fill="{white}"' in body


def test_a_thin_midsole_broken_by_a_window_keeps_its_band():
    from . import shoe_photos as S
    t = traced_photo("AIR_RUNNER")
    tr = frontshoe._Traced.of(t)
    (lo, mid, black), (_, hi, white) = tr.bands[0], tr.bands[-1]
    assert near(black, S.BLACK, 40) and near(white, S.WHITE, 50) and lo == 0.0 and hi == 1.0
    assert 0.5 <= mid <= 0.75   # the outsole's share: 2.6 of 3.6 cm
    body = front(t).body
    assert f'fill="{black}"' in body and f'fill="{white}"' in body


def test_a_window_in_the_sole_is_not_a_band():
    sole = [traced.Region("#f4f4f0", "sole", [[rect(0.0, 1.0, 0.0, 2.0)]], ["midsole"]),
            traced.Region("#cc2222", "sole", [[rect(0.1, 0.3, 0.6, 1.6)]], ["outsole"])]
    t = made()
    t.regions = t.regions[:-1] + sole
    assert [c for _, _, c in frontshoe._Traced.of(t).bands] == ["#f4f4f0"]


def test_a_chukka_the_tagger_calls_a_boot_keeps_its_shaft():
    t = traced_photo("LOW_CHUKKA", (1000, 640))
    assert not frontshoe.STYLES[t.style][3]   # the trace alone draws the line between a boot and a shoe higher
    boot, shoe = spec_of("boots", "boot"), spec_of("sneakers", "low_sneaker")
    as_boot, as_shoe = front(t, boot), front(t, shoe)
    assert frontshoe._Traced.of(t, "round", "boot").shaft > 9.0
    assert frontshoe._Traced.of(t, "round", "low_sneaker").shaft == 0.0

    def width_near_top(f):   # the outline's width 4 px under its top: a shaft round the ankle is wide there
        pts = _flat(f.outline)
        y = min(q[1] for q in pts) + 4.0
        xs = [x for x, yy in pts if yy <= y]
        return max(xs) - min(xs)
    assert width_near_top(as_boot) > 1.5 * 4.7 * K_PX > width_near_top(as_shoe)


def test_a_low_shoe_stays_low_whatever_the_tagger_says():
    t = made()
    assert frontshoe._Traced.of(t, "round", "boot").shaft == 0.0


def test_a_busy_upper_is_painted_in_a_few_clean_colours():
    tr, cs = cells(traced_photo("BUSY_RUNNER"))
    assert len({c for _, _, c, _ in cs}) <= 3
    # its colour is the blotches' mix, not the darkest of them
    assert 0.25 < frontshoe.luminance(tr.base) < 0.6


def test_small_pieces_take_the_colour_round_them():
    specks = [(PANEL, rect(0.3 + 0.1 * k, 0.33 + 0.1 * k, 3.0, 4.0), "quarter") for k in range(5)]   # 0.9 x 1 cm each
    big = [(MARK, rect(0.3, 0.9, 2.5, 6.0), "vamp")]
    tr, cs = cells(made(panels=specks + big))
    colours = {c for _, _, c, _ in cs}
    assert PANEL not in colours and MARK in colours


def test_a_traced_low_shoes_heel_does_not_rise_in_a_point_above_its_collar():
    for name in ("RED_BLACK_RUNNER", "BUSY_RUNNER"):
        t = traced_photo(name)
        tr = frontshoe._Traced.of(t)
        f = front(t)
        view = frontshoe._View(K_PX, tr.warp)
        back = view(0.0, 0.07, tr.sole_t + tr.rim - 0.5)[1]   # the back of the collar's rim
        assert min(y for _, y in _flat(f.outline)) > back - 1.0


def test_a_traced_low_shoes_collar_rounds_down_beside_its_opening():
    assert frontshoe._shoulder(10.0, 2.0, 5.0, 3.0, 2.0) == 10.0   # over the opening: up to the collar
    beside = [frontshoe._shoulder(10.0, 2.0, 5.0, 3.0, x) for x in (3.5, 4.0, 4.5, 5.0)]
    assert beside == sorted(beside, reverse=True) and beside[-1] == 2.0 and beside[0] > 9.0   # then down to the sole


def test_a_traced_boots_shaft_top_is_the_rounded_collar_with_the_leg_in_front_of_its_back():
    t = traced_photo("WORK_BOOT", (1000, 700))
    skin = '<path d="{d}" fill="none"/><path d="{d}" fill="#e0b090"/>'
    traced_boot = frontshoe.front_shoe(spec_of("boots", "boot"), K_PX, ankle=skin, traced=t)
    # the leg is seen above the collar's rounded lip (#214), which runs on up out of the drawing behind it
    clip = re.search(r'<clipPath id="fsa"><path d="([^"]+)"', traced_boot.defs + traced_boot.body).group(1)
    assert " C " in clip and "-4000" in clip


def test_a_boot_laced_high_has_a_round_collar_and_a_rounded_tongue(monkeypatch):
    t = traced_photo("SERVICE_BOOT", (1000, 700))
    seen = []
    real = frontshoe._collar_front

    def spy(upper, rim, px, vamp_top=None):
        seen.append((rim, vamp_top))
        return real(upper, rim, px, vamp_top)
    monkeypatch.setattr(frontshoe, "_collar_front", spy)
    body = frontshoe.front_shoe(spec_of("boots", "boot"), K_PX, ankle='<path d="{d}"/>', traced=t).body
    rim, vamp_top = seen[-1]
    assert vamp_top is None   # the collar's front is not lifted to the tongue: no point, no lining in a V
    xs = [x for x, _ in rim]
    assert max(xs) - min(xs) <= 2 * (frontshoe.ANKLE_HALF_CM + frontshoe.SNUG_CM) * K_PX * 1.01   # it hugs the leg
    tongue = re.search(r'<path d="(M [^"]+ C [^"]+)" fill="none" stroke="#[0-9a-f]+" stroke-width="1.6"', body)
    assert tongue and tongue.group(1).count(" C ") == 2   # a rounded top


# ---- the two front views: A, the template in the trace's colours; B, turned from the trace


def test_view_a_is_the_templates_shape_and_opening():
    t = made(sole=4.5, taller=2.0)
    a, untraced = front(t, kind=frontshoe.FROM_SHAPE), front(None)
    assert a.outline == untraced.outline
    assert a.anchors == untraced.anchors
    assert front(t).outline != untraced.outline   # B follows the trace


def test_view_a_paints_each_traced_part_where_the_template_has_it():
    t = made(panels=[("#c01010", rect(0.84, 1.0, 2.0, 6.0), "toe_cap")])
    t.parts += [traced.Part("toe_cap", "#c01010", True), traced.Part("heel_counter", "#10a020", True)]
    body = front(t, kind=frontshoe.FROM_SHAPE).body
    toe, heel = painted(body, "#c01010"), painted(body, "#10a020")
    assert toe and heel
    ball_y = front(t, kind=frontshoe.FROM_SHAPE).anchors["ball"][1]
    # the toe cap is low in the view (towards the viewer), the heel high (behind)
    assert max(y for ring in toe for _, y in ring) > ball_y - 5
    assert min(y for ring in heel for _, y in ring) < min(y for ring in toe for _, y in ring)


def test_view_a_draws_the_main_marks_and_the_traced_laces():
    stripe = [(0.62, 3.5), (0.66, 3.5), (0.6, 7.5), (0.56, 7.5)]
    t = made(marks=[("#e01080", stripe)], laces=traced.Row(5, 1.2, "#20b0e0", [[0.55 + 0.06 * i, 8.0] for i in range(5)]))
    body = front(t, kind=frontshoe.FROM_SHAPE).body
    assert painted(body, "#e01080")
    assert lace_strokes(body, "#20b0e0") >= 3


def test_view_a_and_b_are_each_the_same_every_time():
    t = traced_photo("RED_BLACK_RUNNER")
    for kind in (frontshoe.FROM_SHAPE, frontshoe.FROM_PHOTO):
        assert front(t, kind=kind).body == front(t.to_json(), kind=kind).body
        assert front(frontshoe.Chosen(t, kind)).body == front(t, kind=kind).body


# ---- rules every front shoe keeps: A, B and the untraced templates

LIP_CM = 1.5   # the collar's padded front, rounding up to its sides, stands this far above the opening's front edge
RULE_SHOES = ["RED_BLACK_RUNNER", "LOW_CHUKKA", "WORK_BOOT", "AIR_RUNNER", "NAVY_DERBY", "SERVICE_BOOT", "BUSY_RUNNER"]
RULE_STYLES = {"RED_BLACK_RUNNER": ("sneakers", "runner"), "LOW_CHUKKA": ("boots", "boot"),
               "WORK_BOOT": ("boots", "boot"), "AIR_RUNNER": ("sneakers", "runner"),
               "NAVY_DERBY": ("sneakers", "derby"), "SERVICE_BOOT": ("boots", "boot"),
               "BUSY_RUNNER": ("sneakers", "runner")}


# the shoes given a synthetic front photo too (`shoe_photos.front_photo`): what it adds that the side cannot show
FRONT_PHOTOS = {"RED_BLACK_RUNNER": {"laces": (242, 240, 234), "toe_mark": (242, 240, 234)}, "WORK_BOOT": {},
                "SERVICE_BOOT": {}}
_LOOKS: dict = {}


def front_look(name: str) -> dict:
    """What `frontlook.measure` reads from the synthetic front photo of one of `shoe_photos`' shoes."""
    if name not in _LOOKS:
        from closet.drawing import frontlook

        from . import shoe_photos as S
        img, mask = S.front_photo(S.Shoe(**{**getattr(S, name), **FRONT_PHOTOS[name]}))
        _LOOKS[name] = frontlook.measure(img, [("true", lambda _: mask * 255)],
                                         frontlook.sole_share(traced_photo(name, (1000, 700) if "BOOT" in name else (1000, 560))))
    return _LOOKS[name]


def every_front_shoe():
    """(name, the shoe from the front with the wearer's ankle in it) for every synthetic traced shoe, A and B, and
    every untraced template but the sandal."""
    for name in RULE_SHOES:
        t = traced_photo(name, (1000, 700) if "BOOT" in name or "CHUKKA" in name else (1000, 560))
        spec = spec_of(*RULE_STYLES[name])
        for kind in (frontshoe.FROM_SHAPE, frontshoe.FROM_PHOTO):
            yield f"{name} {kind}", front(t, spec, kind=kind)
        if name in FRONT_PHOTOS:   # B with a second photo, from the front
            yield f"{name} photo+front", front(frontshoe.Chosen(t, frontshoe.FROM_PHOTO, front_look(name)), spec)
    for c, s in UNTRACED[:-1]:
        yield s, front(None, spec_of(c, s))


def after_the_leg(shoe) -> list[tuple[str, list[tuple[float, float]]]]:
    """What is painted after the wearer's ankle (the tongue apart: it is in front of the leg), each element's
    markup and points."""
    i = shoe.body.index('<g clip-path="url(#za)">')
    depth, j = 0, i
    for m in re.finditer(r"<g[ >]|</g>", shoe.body[i:]):
        depth += -1 if m.group() == "</g>" else 1
        if depth == 0:
            j = i + m.end()
            break
    rest = re.sub(r'<g data-part="tongue">.*?</g>', "", shoe.body[j:])
    out = []
    for el in re.findall(r"<(?:path|circle|ellipse|rect)[^>]*>", rest):
        if 'd="' in el:
            out.append((el, _flat(re.search(r'd="([^"]+)"', el).group(1))))
        elif "cx=" in el:
            out.append((el, [(float(re.search(r'cx="([-\d.]+)"', el).group(1)), float(re.search(r'cy="([-\d.]+)"', el).group(1)))]))
        else:
            x, y = (float(re.search(rf'{k}="([-\d.]+)"', el).group(1)) for k in ("x", "y"))
            out.append((el, [(x, y)]))
    return out


def test_the_collar_back_and_lining_are_painted_before_the_leg():
    for name, shoe in every_front_shoe():
        leg = shoe.body.index('clip-path="url(#za)"')
        lining = [m.start() for m in re.finditer(r'stroke-width="1.4" stroke-linejoin="round"/>', shoe.body)]
        assert lining and max(lining) < leg, name
        for el, _ in after_the_leg(shoe):
            assert 'stroke-width="1.4" stroke-linejoin="round"/>' not in el or "fill=\"none\"" in el, (name, el)


def test_nothing_of_the_shoe_hides_the_leg_above_its_opening():
    """Up the front of the ankle, from the opening's front edge to where the leg above takes over, the leg shows:
    each point is outside the upper's outline or where the leg is seen through it."""
    for name, shoe in every_front_shoe():
        view = frontshoe._View(K_PX)
        upper, rim = _flat(shoe.upper), _flat(shoe.rim)
        seen = [_flat(d) for d in shoe.seen]
        top = shoe.anchors["ankle"][1]
        bad = []
        for k in range(3, 10):   # across the middle of the ankle: its sides are behind the collar's rounded sides
            a = math.pi * k / 12
            for h in range(2, 30):
                x, y = view(frontshoe.ANKLE_HALF_CM * math.cos(a),
                            frontshoe.ANKLE_U + frontshoe.ANKLE_DEPTH_CM * math.sin(a) / frontshoe.LENGTH, h)
                near = [q[1] for q in rim if abs(q[0] - x) <= 1.8]
                if y <= top or not near or y > max(near) - LIP_CM * K_PX:
                    continue   # above where the leg takes over, or the shoe's front and the collar's lip
                if not (_inside((x, y), rim) or y < min(near)):
                    continue
                if _inside((x, y), upper) and not any(_inside((x, y), s) for s in seen):
                    bad.append((round(x), round(y)))
        assert not bad, (name, bad[:5])


def test_every_detail_lies_on_the_shoe():
    for name, shoe in every_front_shoe():
        outline = _flat(shoe.outline)
        for el, pts in after_the_leg(shoe):
            off = [q for q in pts if not _inside(q, outline) and _clear(q, [(-9e3, -9e3), (9e3, -9e3), (9e3, 9e3), (-9e3, 9e3)], 0)
                   and not any(_inside((q[0] + dx, q[1] + dy), outline) for dx in (-1.5, 0, 1.5) for dy in (-1.5, 0, 1.5))]
            assert not off, (name, el[:80], off[:3])


def test_a_traced_toe_is_rounded_as_the_templates():
    """B's toe follows the style's curve, whatever the trace's top line does there (a boxy toe in the photo)."""
    t = made(taller=0.0)
    for i, u in enumerate(US):
        if u > 0.8:
            t.profile.top[i] = t.profile.top[[j for j, v in enumerate(US) if v <= 0.8][-1]]
    tr = frontshoe._Traced.of(t)
    style = frontshoe.STYLES["low_sneaker"][2]
    k = frontshoe._interp(tr.table, 0.8) / frontshoe._interp(style, 0.8)
    for u in (0.85, 0.9, 0.95, 1.0):
        assert frontshoe._interp(tr.table, u) == pytest.approx(max(frontshoe._interp(style, u) * k, 0.8), rel=0.02)



def turns(pts, step: float = 1.0) -> list[float]:
    """How sharply a closed outline turns, in degrees, at each `step` px along it (so a point's sharpness does not
    depend on how many points the path was written with)."""
    even, carry = [pts[0]], 0.0
    for a, b in zip(pts, pts[1:] + pts[:1], strict=True):
        d = math.dist(a, b)
        s = step - carry
        while d and s <= d:
            even.append((a[0] + (b[0] - a[0]) * s / d, a[1] + (b[1] - a[1]) * s / d))
            s += step
        carry = d - (s - step) if d else carry
    out = []
    for a, b, c in zip(even, even[1:] + even[:1], even[2:] + even[:2], strict=True):
        t = math.degrees(math.atan2(c[1] - b[1], c[0] - b[0]) - math.atan2(b[1] - a[1], b[0] - a[0]))
        out.append(abs((t + 180) % 360 - 180))
    return out


def test_the_shoes_outline_has_no_points_or_horns():
    """The collar's top edge is a smooth arc: the outline turns no more sharply anywhere than at #214's rounded
    collar joins (about 60 degrees a pixel). A traced opening standing out past the solid's side once turned the
    collar's shoulder back on itself in a point."""
    for name, shoe in every_front_shoe():
        assert max(turns(_flat(shoe.upper))) < 65, name
