"""A straight-on shoe drawing turned out with the app's 3D shoe solid (`closet/drawing/turned.py`): the solid's lines,
the computed turn that carries every point of the drawing with the surface under it, and the drawing it gives back.
"""
import math
import re

import numpy as np
import pytest

from closet.drawing import drawn, turned

from .conftest import SHEET

DRESS = drawn.example("dress-shoe")
TRAINER = drawn.example("trainer")


def _tilt(points) -> float:
    (x0, y0), (x1, y1) = points[0], points[-1]
    if x1 < x0:
        x0, y0, x1, y1 = x1, y1, x0, y0
    return math.degrees(math.atan2(y1 - y0, x1 - x0))


@pytest.mark.parametrize("style", turned.STYLES)
def test_the_solid_stands_on_the_ground_round_the_leg(style):
    for turn in (0.0, turned.TURN):
        g = turned.geometry(style, turn)
        # the toe tip on the ground; a runner's rocker lifts its toe, so its heel sits a little lower
        assert g["toe"][1] == pytest.approx(turned.GROUND) and abs(g["box"][3] - turned.GROUND) < (10 if style == "runner" else 6)
        x0, _, x1, _ = g["box"]
        assert x0 < 62 and x1 > 138   # wider than the leg, round it
    straight, turned_ = turned.geometry(style, 0.0), turned.geometry(style, turned.TURN)
    assert straight["toe"][0] == pytest.approx(100, abs=0.5)   # straight on, the toe is under the leg
    assert turned_["toe"][0] < straight["toe"][0] - 40   # turned out, it is to the viewer's left
    fr = turned.inner_region(style, turned.TURN, 0.65, 0.92)
    assert fr[0] > straight["toe"][0] - 10 and fr[2] > 130   # the inner side's front third shows on the right


def test_lines_across_the_shoe_tilt_with_the_turn_and_its_centre_line_leans_out():
    for style in ("oxford", "low_sneaker", "runner"):
        g0, g1 = turned.geometry(style, 0.0), turned.geometry(style, turned.TURN)
        assert abs(_tilt(g0["toe_line"])) < 0.5 and abs(_tilt(g0["lace_end"])) < 0.5
        assert 1.5 < _tilt(g1["toe_line"]) < 5 and 1.5 < _tilt(g1["lace_end"]) < 5   # the inner (right) end nearer: lower
        top, toe = g1["centre"][0], g1["centre"][-1]
        assert toe[0] < top[0] - 30 and toe[1] > top[1]   # the vamp runs down and out to the toe on the left


def test_the_computed_turn_carries_a_line_on_the_surface_exactly_as_the_solid_turns_it():
    exact = turned._exact("oxford", turned.TURN)
    g0, g1 = turned.geometry("oxford", 0.0), turned.geometry("oxford", turned.TURN)
    for a, b in zip(g0["toe_line"], g1["toe_line"], strict=True):
        assert np.allclose(exact(*a), b, atol=1e-6)
    pts = [(x, y) for y in range(-40, 245, 7) for x in range(-5, 210, 7)]
    assert np.allclose(exact.many(pts), [exact(x, y) for x, y in pts])


def test_the_turn_is_smooth_and_leaves_the_collar_and_a_shaft_upright():
    box, hinge = (29.0, 30.0, 171.0, 242.0), 32.0
    move = turned.Turn("oxford", turned.TURN, box, hinge)
    assert move(100.0, hinge - turned.EASE - 1) == pytest.approx((100.0, hinge - turned.EASE - 1))   # above: unmoved
    x, y = move(60.0, 200.0)
    assert x < 30 and abs(y - 200) < 15   # the toe swings out to the left
    a, b = move(60.0, 170.0), move(140.0, 170.0)   # a line across the toe box tilts, its inner end lower
    assert 1 < math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) < 6
    boot = turned.Turn("chelsea_boot", turned.TURN, (22.0, -40.0, 178.0, 242.0), hinge=84.0)
    for high in (-30.0, 0.0, 40.0):
        assert boot(56.0, high) == pytest.approx((56.0, high)) and boot(144.0, high) == pytest.approx((144.0, high))
    mirror = turned.Turn("oxford", turned.TURN, box, hinge, mirror=True)
    mx, my = mirror(200.0 - 60.0, 200.0)
    assert mx == pytest.approx(200.0 - x) and my == pytest.approx(y)   # the right shoe turns the other way


def test_a_long_edge_follows_the_turn_and_a_shaft_stays_upright_above_the_hinge():
    """A boot's sides drawn as single lines from the top of its shaft down into its foot: each piece of a line is moved
    with the surface under it, so above the hinge the shaft does not lean (moving only a line's two ends leaned it
    from its unmoved top to its moved bottom, and the turned drawing copied the lean)."""
    import svgelements as se

    d = "M55,-40 L55,200 L20,240 L180,240 L145,200 L145,-40 Z"
    seam = '<path d="M60,-30 L60,10" fill="none" stroke="#26221f" stroke-width="1.6"/>'   # a seam high on the shaft
    boot = drawn.side(f'<path d="{d}" fill="#6b4630" stroke="#26221f" stroke-width="4"/>{seam}')
    sheet = {"silhouette": {"height": "ankle"}, "instep_y": 85.0, "opening_front_y": -34.0}
    out = turned.turn_side(boot, "chelsea_boot", sheet)
    move = turned.Turn("chelsea_boot", turned.TURN, drawn.measure(boot)["box"], 85.0)
    turned_path = se.Path(re.search(r' d="([^"]+)"', out.front).group(1))
    on = np.array([(q.x, q.y) for q in (turned_path.point(t / 4000) for t in range(4001))])
    for x in (55.0, 145.0):
        for y in range(-40, 201, 10):
            want = np.array(move(x, float(y)))
            assert np.min(np.hypot(*(on - want).T)) < 1.0, (x, y)   # on the turned edge, where the turn puts it
            if y < 85 - turned.EASE:
                assert tuple(want) == pytest.approx((x, y))   # above the hinge: upright, where it was
    assert "M60 -30 L60 10" in out.front   # a line the turn carries whole stays a line


def test_a_boots_shaft_stands_upright_in_the_guide_turned_or_not():
    """The guide's shaft is outlined with the foot, not hulled with its toe: one hull of both leaned the shaft out
    towards the turned toe, which an upright tube round the leg never does."""
    for style in ("chelsea_boot", "boot", "high_top"):
        for turn in (0.0, turned.TURN):
            upper = turned.geometry(style, turn)["upper"]
            top = min(y for _, y in upper)
            (l0, r0), (l1, r1) = turned._span(upper, top + 5), turned._span(upper, top + 60)
            assert abs(l1 - l0) < 3 and abs(r1 - r0) < 3, (style, turn)


def test_a_turned_boot_whose_shaft_leans_is_found_and_an_upright_one_is_not():
    boot = drawn.split_example("boot")
    sheet = {"silhouette": {"height": "ankle"}, "instep_y": 84.0, "opening_front_y": -32.0, "top_y": -46.0}
    computed = turned.turn_side(boot, "boot", sheet)
    assert turned.upright_problems(computed, computed, sheet) == []
    lean = drawn.side({"behind": f'<g transform="matrix(1 0 -0.12 1 28.8 0)">{computed.behind}</g>',
                       "front": f'<g transform="matrix(1 0 -0.12 1 28.8 0)">{computed.front}</g>'})
    found = turned.upright_problems(lean, computed, sheet, which="right")
    assert len(found) == 1 and found[0].startswith("The right shoe's shaft leans or widens: above y = 54")
    assert "units out" in found[0] and "only the foot below it turns" in found[0]
    oxford = turned.turn_side(drawn.side(DRESS), "oxford", SHEET)   # a low shoe: nothing above its hinge to measure
    assert turned.upright_problems(drawn.side({"behind": "", "front": f'<g transform="translate(9 0)">{oxford.front}'
                                                                     '</g>'}), oxford, SHEET) == []


def test_a_turned_drawing_keeps_its_paint_and_is_safe():
    out = turned.turn_side(drawn.side(TRAINER), "low_sneaker", SHEET)
    assert out == drawn.side(out)   # already made safe
    colours = lambda svg: sorted(set(re.findall(r'(?:fill|stroke)="(#[0-9a-fA-F]{6})"', svg)))   # noqa: E731
    assert colours(out.front) == colours(drawn.sanitise(TRAINER))
    widths = lambda svg: sorted(set(re.findall(r'stroke-width="([\d.]+)"', svg)))   # noqa: E731
    assert set(widths(out.front)) <= {"1.2", "1.6", "2", "4", "7", "10"}
    m0, m1 = drawn.measure(drawn.side(TRAINER)), drawn.measure(out)
    assert m1["box"][0] < m0["box"][0] - 30   # its toe now out to the left
    assert m1["box"][3] == pytest.approx(m0["box"][3], abs=6)   # still on the ground
    right = turned.turn_side(drawn.side(TRAINER), "low_sneaker", SHEET, mirror=True)
    r = drawn.measure(right)["box"]
    assert r[2] > m0["box"][2] + 30   # the right shoe's toe out to the right
    assert turned.warp_fragment("", lambda x, y: (x, y)) == ""


def test_the_guide_shows_an_ordinary_shoe_straight_on_and_turned():
    png = turned.guide_png("runner")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    text = turned.guide_text("oxford")
    for words in ("the sole's whole outline", "the upper's outline", "the middle of the vamp", "the collar's edge",
                  "where the toe box begins", "the middle height of the inner side", "the lacing's two edges"):
        assert words in text, words
    assert "lacing" not in turned.guide_text("chelsea_boot")
    with pytest.raises(KeyError):
        turned.geometry("sandal", 0.0)


def _hatched(lines: int) -> drawn.Side:
    """A boot drawn with `lines` long lines from its shaft's top down into its foot, in one path: a turn splits each."""
    d = " ".join(f"M{30 + i * 0.35:.2f},-40 L{30 + i * 0.35:.2f},230" for i in range(lines))
    return drawn.side({"behind": "", "front": '<path d="M20,-40 L180,-40 L190,240 L10,240 Z" fill="#6b4630"/>'
                                              f'<path d="{d}" stroke="#26221f" stroke-width="1.6" fill="none"/>'})


def test_a_turn_too_long_at_first_is_split_more_coarsely_and_one_still_too_long_is_refused():
    sheet = {"silhouette": {"height": "ankle"}, "instep_y": 85.0, "opening_front_y": -34.0}
    side = _hatched(150)
    move = turned.Turn("boot", turned.TURN, drawn.measure(side)["box"], 85.0)
    assert len(turned.warp_fragment(side.front, move)) > drawn.MAX_CHARS   # split finely: too long
    out = turned.turn_side(side, "boot", sheet)
    coarse = drawn.side({"behind": "", "front": turned.warp_fragment(side.front, move, turned.COARSE)})
    assert len(out.front) <= drawn.MAX_CHARS and out == coarse
    with pytest.raises(drawn.DrawingError, match="too long"):
        turned.turn_side(_hatched(400), "boot", sheet)
