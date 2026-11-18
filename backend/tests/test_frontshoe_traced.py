"""A traced shoe seen from the front on the As worn figure (#192, stage 2c).

The traced shoes here are built by hand (or traced from a photo drawn by `shoe_photos`; no real photos), so where
each panel, mark and lace should land is known.
"""
import copy
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


def spec_of(category="sneakers", style="low_sneaker", bottom=SHORTS, **details):
    shoes = Piece(category, answer(category, shoe_style=style, **details), "#5a3a22")
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
# (changed once: a Chelsea boot's pull tab, at the back of its shaft, is drawn behind the leg, not over it; and once
# when the trousers' hem moved onto the shoe: the shoes themselves, and the figures in shorts, are byte for byte the
# same; and once when a bare ankle under cropped trousers showed points on low shoes' collars: the dress shoes and
# slip-ons got #214's rounded collar, and every low shoe rounder shoulders beside the ankle)
UNTRACED_DIGEST = "58d98c2962372ad651a2ca3ed3419eb3b4702807c423c8b99e38bc237a9fcfeb"   # taken again 18 Nov: his arms hang nearer his sides and the tee's sleeves lose ease at the underarm; the shoes are unchanged (taken 16 Nov when the tee lost its set-in armhole seam)


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

def test_both_views_are_the_templates_shape_whatever_the_trace():
    """B's outline is built exactly as A's: the template's for the style (its footprint, toe, opening and shaft).
    A taller top line, a thicker sole or a taller boot in the photo change only what is painted on it."""
    for t, spec in ((made(), None), (made(taller=2.0), None), (made(sole=3.5), None),
                    (made(style="boot"), spec_of("boots", "boot")), (made(style="boot", taller=5.0), spec_of("boots", "boot"))):
        plain = front(None, spec)
        for kind in (frontshoe.FROM_SHAPE, frontshoe.FROM_PHOTO):
            f = front(t, spec, kind=kind)
            assert (f.outline, f.anchors, f.upper, f.rim) == (plain.outline, plain.anchors, plain.upper, plain.rim)


def test_b_outline_equals_a_outline_for_every_synthetic_shoe():
    for name in RULE_SHOES:
        t = traced_photo(name, (1000, 700) if "BOOT" in name or "CHUKKA" in name else (1000, 560))
        spec = spec_of(*RULE_STYLES[name])
        a = front(t, spec, kind=frontshoe.FROM_SHAPE)
        views = [front(t, spec, kind=frontshoe.FROM_PHOTO)]
        if name in FRONT_PHOTOS:
            views.append(front(frontshoe.Chosen(t, frontshoe.FROM_PHOTO, front_look(name)), spec))
        for b in views:
            assert (b.outline, b.upper, b.rim, b.seen, b.anchors) == (a.outline, a.upper, a.rim, a.seen, a.anchors), name


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


def test_a_traced_boots_shaft_top_is_the_rounded_collar_with_the_leg_in_front_of_its_back():
    t = traced_photo("WORK_BOOT", (1000, 700))
    skin = '<path d="{d}" fill="none"/><path d="{d}" fill="#e0b090"/>'
    traced_boot = frontshoe.front_shoe(spec_of("boots", "boot"), K_PX, ankle=skin, traced=t)
    # the leg is seen above the collar's rounded lip (#214), which runs on up out of the drawing behind it
    clip = re.search(r'<clipPath id="fsa"><path d="([^"]+)"', traced_boot.defs + traced_boot.body).group(1)
    assert " C " in clip and "-4000" in clip


def test_view_a_is_the_templates_shape_and_opening():
    t = made(sole=4.5, taller=2.0)
    a, untraced = front(t, kind=frontshoe.FROM_SHAPE), front(None)
    assert a.outline == untraced.outline
    assert a.anchors == untraced.anchors


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
RULE_SHOES = ["RED_BLACK_RUNNER", "LOW_CHUKKA", "WORK_BOOT", "AIR_RUNNER", "NAVY_DERBY", "SERVICE_BOOT", "BUSY_RUNNER",
              "DARK_COLLAR", "STRIPED_COURT"]
RULE_STYLES = {"RED_BLACK_RUNNER": ("sneakers", "runner"), "LOW_CHUKKA": ("boots", "boot"),
               "WORK_BOOT": ("boots", "boot"), "AIR_RUNNER": ("sneakers", "runner"),
               "NAVY_DERBY": ("sneakers", "derby"), "SERVICE_BOOT": ("boots", "boot"),
               "BUSY_RUNNER": ("sneakers", "runner"), "DARK_COLLAR": ("sneakers", "low_sneaker"),
               "STRIPED_COURT": ("sneakers", "low_sneaker")}


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
    for s in frontshoe.CUT_STYLES:   # cut no-show: the collar and the opening lower
        yield f"{s} no_show", front(None, spec_of("sneakers", s, footwear_height="no_show"))
    yield "STRIPED_COURT no_show", front(traced_photo("STRIPED_COURT"), spec_of(footwear_height="no_show"),
                                         kind=frontshoe.FROM_SHAPE)


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


@pytest.mark.parametrize("taller", [0.0, 3.0])
def test_a_traced_toe_is_the_templates_toe(taller):
    """B's toe is the style's, as A draws it, whatever the trace's top line does there (a tall, boxy toe in the
    photo): its height from TOE_U on, the footprint's width, and a sole no thicker at the toe than at the ball."""
    t = made(taller=taller, sole=3.0)
    for i, u in enumerate(US):
        if u > 0.75:   # a boxy toe: the top line stays up to the end
            t.profile.top[i] = t.profile.top[[j for j, v in enumerate(US) if v <= 0.75][-1]]
        if u > 0.9:    # and a bumper that the trace took for sole
            t.profile.sole[i] = 4.5
    tr = frontshoe._Traced.of(t)
    ball, _, style, _ = frontshoe.STYLES["low_sneaker"]
    for u in (0.8, 0.85, 0.9, 0.95, 1.0):
        assert frontshoe._interp(tr.table, u) == pytest.approx(max(frontshoe._interp(style, u), 0.8), rel=0.02)
    assert tr.ball == ball
    assert max(s for u, s in zip(tr.us, tr.sole, strict=True) if u > 0.8) <= frontshoe._lerp(tr.us, tr.sole, 0.8) + 1e-9
    a, b = front(t, kind=frontshoe.FROM_SHAPE), front(t)
    tip = lambda s: [q for q in _flat(s.outline) if q[1] > s.anchors["ball"][1]]   # noqa: E731
    wa, wb = (max(x for x, _ in tip(s)) - min(x for x, _ in tip(s)) for s in (a, b))
    assert wb == pytest.approx(wa, rel=0.03)   # the toe as wide as A's: not a wide box


def block_sizes(tr) -> list[tuple[int, bool]]:
    """Each block of one colour among the upper's cells: its size, and whether another colour borders it."""
    grid = {(s, i, j, p): c for s, i, j, c, _, p in tr.cells()}
    seen, out = set(), []
    for key in grid:
        if key in seen:
            continue
        todo, n, edge = [key], 0, False
        seen.add(key)
        while todo:
            s, i, j, p = todo.pop()
            n += 1
            for q in ((s, i + 1, j, p), (s, i - 1, j, p), (s, i, j + 1, p), (s, i, j - 1, p)):
                if q in grid and grid[q] != grid[key]:
                    edge = True
                elif q in grid and q not in seen:
                    seen.add(q)
                    todo.append(q)
        out.append((n, edge))
    return out


def test_the_upper_is_painted_in_a_few_clean_blocks():
    """No speck or sliver of colour between panels: every block of one colour beside another is at least
    MIN_BLOCK_CELLS cells, in B and in A; a busy upper comes out as a handful of blocks."""
    for name in RULE_SHOES:
        t = traced_photo(name, (1000, 700) if "BOOT" in name or "CHUKKA" in name else (1000, 560))
        tr = frontshoe._Traced.of(t, "round", RULE_STYLES[name][1])
        tpl = tr.on_template(*frontshoe.STYLES["low_sneaker"][:4], 0.97, "round")
        for which in (tr, tpl):
            assert all(n >= frontshoe.MIN_BLOCK_CELLS for n, edge in block_sizes(which) if edge), name
    busy = frontshoe._Traced.of(traced_photo("BUSY_RUNNER"), "round", "runner")
    assert len(block_sizes(busy)) <= 12


def test_blotches_of_leather_are_not_panels():
    """A leather upper whose photo shows blotches a few cm across (creases, shade, wear), each up to 16 cm²: B paints
    no blotch; it reads as one clean colour."""
    blotches = [("#303032", rect(u, u + 4.0 / frontshoe.LENGTH, h, h + 4.0), "quarter")
                for u, h in ((0.1, 3.0), (0.3, 6.5), (0.45, 3.5), (0.6, 5.0), (0.75, 3.0), (0.2, 8.0))]
    tr = frontshoe._Traced.of(made(panels=blotches))
    b = tr.on_template(*frontshoe.STYLES["low_sneaker"][:4], 0.97, "round", sampled=True)
    assert len({c for _, _, _, c, _, _ in b.cells()}) == 1


def test_the_collar_never_lies_across_the_throat():
    """A light shoe with a black heel counter and collar along the top to the throat: from the front the collar
    is behind the leg; in front of the leg the crest is the throat, in the upper's colour, in A and in B."""
    t = traced_photo("DARK_COLLAR")
    tr = frontshoe._Traced.of(t, "round", "low_sneaker")
    tpl = tr.on_template(*frontshoe.STYLES["low_sneaker"][:4], 0.97, "round")
    for which in (tr, tpl):
        cells = [(i, c) for _, i, _, c, _, part in which.cells() if part == "foot"]
        assert any(near(c, (24, 24, 26)) for i, c in cells if (i + 0.5) / frontshoe.GRID_U < frontshoe.THROAT_U)
        assert not [i for i, c in cells if (i + 0.5) / frontshoe.GRID_U > frontshoe.THROAT_U and near(c, (24, 24, 26))]
    for kind in (frontshoe.FROM_SHAPE, frontshoe.FROM_PHOTO):
        shoe = front(t, kind=kind)
        black = [c for c in set(re.findall(r'fill="(#[0-9a-f]{6})"', shoe.body)) if near(c, (24, 24, 26))]
        rim = _flat(shoe.rim)
        front_y = max(y for _, y in rim)
        ankle_x = shoe.anchors["ankle"][0]
        across = [q for c in black for ring in painted(shoe.body, c) for q in ring
                  if q[1] > front_y + 2 and abs(q[0] - ankle_x) < frontshoe.ANKLE_HALF_CM * K_PX * 0.6]
        assert not across, (kind, across[:3])


def test_view_a_takes_the_toe_box_and_vamp_from_the_top_surface():
    """A red upper with a black mudguard low round the toe (traced as the vamp's part colour): A's toe box and
    vamp are red, as B samples them, not the mudguard's black."""
    guard = [[0.55, 2.0], [1.0, 2.0], [1.0, 3.6], [0.55, 4.6]]
    t = made(panels=[("#141414", guard, "vamp")])
    t.regions[0] = traced.Region("#c01818", "silhouette", t.regions[0].paths, ["upper"])
    t.parts += [traced.Part("vamp", "#141414", True)]
    tr = frontshoe._Traced.of(t)
    tpl = tr.on_template(*frontshoe.STYLES["low_sneaker"][:4], 0.97, "round")
    assert tpl.zones["vamp"] == "#c01818"
    assert tpl.zones.get("toe_cap", "#c01818") == "#c01818"


def lab(colour) -> list[float]:
    import cv2
    import numpy as np
    rgb = frontshoe._rgb(colour) if isinstance(colour, str) else [v / 255 for v in colour]
    return cv2.cvtColor(np.float32([[rgb]]), cv2.COLOR_RGB2Lab)[0, 0].tolist()


def test_bold_stripes_are_marks_not_part_of_the_uppers_colour():
    """A white court shoe with three bold red stripes, each under a panel's size but together much of the side:
    they are its marks, kept out of the upper's colour (once mixed into it as a pattern, pink). The upper stays
    white in A and B, and the three stripes are drawn in both."""
    from . import shoe_photos as S
    t = traced_photo("BOLD_STRIPES")
    assert sum(len(m.path) for m in t.marks) == 3
    tr = frontshoe._Traced.of(t, "round", "low_sneaker")
    style = frontshoe.STYLES["low_sneaker"][:4]
    for view in (tr.on_template(*style, 0.97, "round"), tr.on_template(*style, 0.97, "round", sampled=True)):
        assert math.dist(lab(view.base), lab(S.WHITE)) <= 5
        assert all(math.dist(lab(c), lab(S.WHITE)) <= 5 for _, _, _, c, _, _ in view.cells())
    for kind in (frontshoe.FROM_SHAPE, frontshoe.FROM_PHOTO):
        body = front(t, kind=kind).body
        red = {c for c in re.findall(r'fill="(#[0-9a-f]{6})"/>', body) if near(c, (196, 30, 40))}
        assert sum(len(re.findall(rf'<path d="[^"]+" fill="{c}"/>', body)) for c in red) >= 3, kind


def test_large_panels_in_a_marks_colour_stay_panels_and_a_small_curve_is_drawn():
    """A runner with large red panels (the toe box and vamp, the quarter), which the trace also took for a red mark
    and a red logo over them, and a small black curve on the side: the red panels are not masked as marks, so the
    toe box stays red in A and B, and the curve is drawn as a mark in both."""
    red, black = "#c81e28", "#111111"
    t = made(panels=[(red, rect(0.55, 1.0, 0.0, 20.0), "vamp"), (red, rect(0.15, 0.55, 2.0, 7.0), "quarter")],
             marks=[(red, rect(0.6, 1.0, 2.0, 9.0)), (red, rect(0.3, 0.36, 5.0, 6.0)),
                    (black, [[0.3, 3.0], [0.42, 3.4], [0.52, 4.4], [0.5, 4.8], [0.4, 3.9], [0.3, 3.6]])])
    tr = frontshoe._Traced.of(t, "round", "runner")
    style = frontshoe.STYLES["runner"][:4]
    for view in (tr.on_template(*style, 0.97, "round"), tr.on_template(*style, 0.97, "round", sampled=True)):
        toe = [c for _, i, _, c, _, p in view.cells() if p == "foot" and i >= 0.85 * frontshoe.GRID_U]
        assert toe and max(set(toe), key=toe.count) == red
    for kind in (frontshoe.FROM_SHAPE, frontshoe.FROM_PHOTO):
        body = front(t, spec_of(style="runner"), kind=kind).body
        assert re.search(rf'<path d="[^"]+" fill="{black}"/>', body), kind


def test_three_bold_red_stripes_are_drawn_on_both_views_as_marks():
    """The white court shoe's three bold red stripes, masked out of its colours, are drawn: three red marks in A
    and in B, the upper still white."""
    from . import shoe_photos as S
    t = traced_photo("BOLD_STRIPES")
    for kind in (frontshoe.FROM_SHAPE, frontshoe.FROM_PHOTO):
        body = front(t, kind=kind).body
        red = [ring for c in set(re.findall(r'fill="(#[0-9a-f]{6})"/>', body)) if near(c, (196, 30, 40))
               for ring in painted(body, c)]
        assert len([ring for ring in red if area(ring) > 0.5]) >= 3, kind
        cells = frontshoe._Traced.of(t, "round", "low_sneaker").on_template(
            *frontshoe.STYLES["low_sneaker"][:4], 0.97, "round", sampled=kind == frontshoe.FROM_PHOTO).cells()
        assert all(math.dist(lab(c), lab(S.WHITE)) <= 5 for _, _, _, c, _, _ in cells)


def red_area(body: str) -> float:
    return sum(area(ring) for c in set(re.findall(r'fill="(#[0-9a-f]{6})"/>', body)) if near(c, (196, 30, 40))
               for ring in painted(body, c))


def test_stripes_taken_out_of_the_colours_are_drawn_even_when_the_trace_kept_only_a_bit_of_each():
    """A trace whose stripe marks kept only a small bit of each stripe (the rest left as colour pieces): the pieces
    taken out of the upper's colour as those marks are drawn as marks themselves, so the stripes do not vanish."""
    full = traced_photo("BOLD_STRIPES")
    t = copy.deepcopy(full)
    for m in t.marks:
        m.path = [[[u, h] for u, h in (
            (cu + du, ch + dh) for cu, ch in [frontshoe._centre(ring)] for du, dh in
            ((-0.004, -0.3), (0.004, -0.3), (0.004, 0.3), (-0.004, 0.3)))] for ring in m.path]
    for kind in (frontshoe.FROM_SHAPE, frontshoe.FROM_PHOTO):
        assert red_area(front(t, kind=kind).body) >= 0.6 * red_area(front(full, kind=kind).body), kind


def test_view_a_keeps_the_laces_colour_and_draws_the_stripes():
    """A white court shoe, white laces, three red stripes whose ends cross the lacing's row: A's laces are not
    red, and the stripes are drawn on its side, even when the trace took them for lettering."""
    t = copy.deepcopy(traced_photo("STRIPED_COURT"))
    tr = frontshoe._Traced.of(t, "round", "low_sneaker")
    assert "lace_color" not in tr.template_words() or not near(tr.template_words()["lace_color"], (196, 30, 40))
    for kinds in (None, "text"):
        if kinds:
            for m in t.marks:
                m.kind = kinds
        body = front(t, kind=frontshoe.FROM_SHAPE).body
        red = [c for c in set(re.findall(r'fill="(#[0-9a-f]{6})"', body)) if near(c, (196, 30, 40))]
        assert sum(area(ring) for c in red for ring in painted(body, c)) > 5
        assert not [c for c in set(re.findall(r'stroke="(#[0-9a-f]{6})" stroke-width="[\d.]+" stroke-linecap', body))
                    if near(c, (196, 30, 40))]   # no red lace strokes


def thickness(pts) -> float:
    return 2 * area(pts) / sum(math.dist(a, b) for a, b in zip(pts, pts[1:] + pts[:1], strict=True))


def on_the_shoe(shoe, pts) -> bool:
    outline = _flat(shoe.outline)
    return all(any(_inside((q[0] + dx, q[1] + dy), outline) for dx in (-1.5, 0, 1.5) for dy in (-1.5, 0, 1.5))
               for q in pts)


@pytest.mark.parametrize("name", ["STRIPED_COURT", "BOLD_STRIPES", "REAL_STRIPES"])
def test_a_white_shoes_three_red_stripes_are_three_bands_in_a_and_b(name):
    """A white court shoe with three red stripes on its side: A and B each draw three marks, one band for each
    stripe, slanted and foreshortened by the turn but wide enough to see (no slivers of the side turned away), on
    the shoe and under its laces; the upper stays white. A stripe the trace took for a colour piece beside two
    marks (its box overlapping theirs) was once dropped, and the side walls showed only thin slivers. REAL_STRIPES
    has thin, tapered, soft-edged stripes, as a photo shows them: one was once taken for the laces."""
    from . import shoe_photos as S
    spec = getattr(S, name)
    t = traced_photo(name)
    for kind in (frontshoe.FROM_SHAPE, frontshoe.FROM_PHOTO):
        shoe = front(t, kind=kind)
        red = [ring for c in set(re.findall(r'fill="(#[0-9a-f]{6})"/>', shoe.body)) if near(c, spec["stripes"])
               for ring in painted(shoe.body, c)]
        assert len(red) == 3, kind
        assert all(area(ring) > 5 and thickness(ring) > 0.2 * K_PX for ring in red), kind
        assert all(on_the_shoe(shoe, ring) for ring in red), kind
        reds = {c for c in re.findall(r'fill="(#[0-9a-f]{6})"/>', shoe.body) if near(c, spec["stripes"])}
        last_mark = max(m.start() for c in reds for m in re.finditer(rf'fill="{c}"/>', shoe.body))
        assert last_mark < shoe.body.index('stroke-linecap="round"'), kind   # the laces are painted over them
        cells = frontshoe._Traced.of(t, "round", "low_sneaker").on_template(
            *frontshoe.STYLES["low_sneaker"][:4], 0.97, "round", sampled=kind == frontshoe.FROM_PHOTO).cells()
        own = [spec["upper"]] + ([spec["heel_counter"]] if spec.get("heel_counter") else [])   # a dark heel tab
        assert all(min(math.dist(lab(c), lab(rgb)) for rgb in own) <= 5 for _, _, _, c, _, _ in cells), kind
        laces = [c for c in re.findall(r'stroke="(#[0-9a-f]{6})" stroke-width="[\d.]+" stroke-linecap="round"', shoe.body)
                 if c != frontshoe.INK]
        assert laces and not any(near(c, spec["stripes"]) for c in laces), kind   # the laces are not the stripes' red


def test_a_small_black_curve_is_one_curved_mark_in_a_and_b():
    """A white sneaker with a small black curve on its side (a swoosh): one curved mark in A and in B, wide enough
    to see though the side is seen nearly edge on, and on the shoe."""
    t = made(marks=[("#111111", [[0.3, 3.0], [0.42, 3.4], [0.52, 4.4], [0.5, 4.8], [0.4, 3.9], [0.3, 3.6]])])
    t.regions[0].color, t.marks[0].kind = "#f2f0ea", "curve"
    for kind in (frontshoe.FROM_SHAPE, frontshoe.FROM_PHOTO):
        shoe = front(t, kind=kind)
        marks = painted(shoe.body, "#111111")
        assert len(marks) == 1, kind
        mark = marks[0]
        assert thickness(mark) >= 0.4 * K_PX, kind
        assert area(mark) < 0.9 * area(frontshoe._hull(mark)), kind   # it bends: a curve, not a straight band
        assert on_the_shoe(shoe, mark), kind



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


@pytest.mark.parametrize("style", ["low_sneaker", "runner", "slip_on"])
def test_a_no_show_cut_lowers_the_collar_and_the_opening(style):
    """`footwear_height=no_show` (a low-cut runner or slip-on): the collar stands lower round the ankle, and the
    opening dips further below the ankle bones, lowest at its sides, so more of the ankle shows above it. The
    shoe's front (the toe, the laces) stays where it was."""
    plain = front(None, spec_of("sneakers", style))
    cut = front(None, spec_of("sneakers", style, footwear_height="no_show"))
    rim, low = _flat(plain.rim), _flat(cut.rim)
    # every point of the opening's edge is lower on the drawing (y down), its sides the most
    assert all(b[1] > a[1] + 0.8 * K_PX for a, b in zip(rim, low, strict=True))
    sides = [i for i, q in enumerate(rim) if q[0] in (min(x for x, _ in rim), max(x for x, _ in rim))]
    assert all(low[i][1] - rim[i][1] > min(b[1] - a[1] for a, b in zip(rim, low, strict=True)) for i in sides)
    # the top of the shoe beside the ankle is lower too; its toe and sole are not
    assert min(y for _, y in _flat(cut.upper)) > min(y for _, y in _flat(plain.upper)) + 0.8 * K_PX
    # a trouser hem meets the opening where it now is, lower; every other anchor stays
    moved = ("opening", "opening_back")
    assert {k: v for k, v in cut.anchors.items() if k not in moved} == {k: v for k, v in plain.anchors.items() if k not in moved}
    assert all(cut.anchors[k][1] > plain.anchors[k][1] + 0.8 * K_PX for k in moved)
    toe = lambda s: [q for q in _flat(s.outline) if q[1] > s.anchors["ball"][1]]   # noqa: E731
    assert toe(cut) == toe(plain)
    # the leg is seen down to the lower opening: more of the ankle shows
    assert max(y for d in cut.seen for _, y in _flat(d)) > max(y for d in plain.seen for _, y in _flat(d))


def test_the_shoes_outline_has_no_points_or_horns():
    """The collar's top edge is a smooth arc: the outline turns no more sharply anywhere than at #214's rounded
    collar joins (about 60 degrees a pixel). A traced opening standing out past the solid's side once turned the
    collar's shoulder back on itself in a point."""
    for name, shoe in every_front_shoe():
        assert max(turns(_flat(shoe.upper))) < 65, name


CROPPED = Piece("trousers", answer("trousers", {"pant_length": "ankle"}, leg_shape="slim", trouser_break="cropped"),
                "#6f7278")


@pytest.mark.parametrize("c, s", [("sneakers", "low_sneaker"), ("sneakers", "runner"), ("sneakers", "slip_on"),
                                  ("dress_shoes", "loafer"), ("dress_shoes", "derby"), ("dress_shoes", "oxford")])
def test_no_point_of_a_low_collar_sticks_up_beside_the_bare_ankle(c, s):
    """Under cropped trousers the ankle shows, and where the collar's top edge meets the leg what shows of the shoe
    is a rounded shoulder: on a small circle there, at least a quarter of it is shoe. A dress shoe's raw crown once
    left a sliver standing up beside the ankle in a point (#223 review)."""
    lay = plan(dict(base=TEE, bottom=CROPPED, shoes=Piece(c, answer(c, shoe_style=s), "#5a3a22")))
    shoes = lay.get("shoes")
    t = shoes.transforms[0]
    path = fig._moved(lay.body.legs[0], (t[0], 0.0, 0.0, 1.0, -t[0] * t[4], -t[5]))
    shoe = fig.front_shoe(shoes.spec, K_PX, sole_default=shoes.shape.sole_default, uid="z", ankle=fig._ankle(),
                          ankle_path=path, toes=fig.TOE_LINE)
    upper, leg, seen = _flat(shoe.upper), _flat(path), [_flat(d) for d in shoe.seen]
    covered = lambda p: _inside(p, leg) and any(_inside(p, q) for q in seen)   # noqa: E731
    pts = []
    for a, b in zip(upper, upper[1:] + upper[:1], strict=True):
        n = max(1, int(math.dist(a, b) / 0.5))
        pts += [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n)]
    meets = [b for a, b in zip(pts[-1:] + pts[:-1], pts, strict=True) if covered(a) != covered(b)]
    assert meets, s
    for x, y in meets:
        ring = [(x + 4 * math.cos(math.radians(d)), y + 4 * math.sin(math.radians(d))) for d in range(360)]
        shown = sum(_inside(q, upper) and not covered(q) for q in ring)
        assert shown >= 90, (s, round(x, 1), round(y, 1), shown)
