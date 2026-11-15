"""A shoe's second photo, from the front, read for its front view (#205, "From your photo").

The photos are drawn by `shoe_photos.front_photo` (never real photos), so what the reading should find is known.
"""
import math

from closet.drawing import frontlook, frontshoe
from closet.drawing import trace as T

from . import shoe_photos as S
from .test_frontshoe_traced import front, front_look, near, spec_of, traced_photo

MARKED = S.Shoe(**{**S.RED_BLACK_RUNNER, "laces": S.WHITE, "toe_mark": S.WHITE})


def read(shoe, sole=0.22, masker=None):
    img, mask = S.front_photo(shoe)
    return frontlook.measure(img, [masker or ("true", lambda _: mask * 255)], sole)


def test_the_toe_box_vamp_laces_and_a_toe_mark_are_read_from_the_front():
    look = read(MARKED)
    assert near(look["toe"], S.RED) and near(look["vamp"], S.RED)   # the toe box's top, not the black mudguard
    assert abs(look["laces"] - MARKED.lace_count) <= 1 and near(look["lace_color"], S.WHITE)
    assert len(look["marks"]) == 1
    colour, x, v, size = look["marks"][0]
    assert near(colour, S.WHITE) and 0.1 < x < 0.7 and 0.2 < v < 0.8 and 0.002 < size < 0.03
    assert 0.6 < look["aspect"] < 1.0


def test_the_cut_out_from_the_photo_reads_the_same():
    assert read(MARKED, masker=("grabcut", T.grabcut_mask)) == read(MARKED)


def test_panels_along_the_outline_are_not_marks_and_laces_the_upper_s_colour_are_not_seen():
    for name in ("RED_BLACK_RUNNER", "NAVY_DERBY", "WORK_BOOT"):
        look = read(S.Shoe(**getattr(S, name)))
        assert look["marks"] == [], name   # a mudguard, a collar and the opening run along the outline
    assert read(S.Shoe(**S.NAVY_DERBY))["laces"] == 0   # navy laces on navy
    assert read(S.Shoe(**S.WORK_BOOT))["laces"] >= 4


def test_no_shoe_found_is_none():
    img, _ = S.front_photo()
    assert frontlook.measure(img, [("none", lambda _: None)]) is None
    assert frontlook.measure(img, [("empty", lambda im: 0 * S.front_photo()[1])]) is None


def test_the_sole_share_comes_from_the_side_trace():
    boot, runner = traced_photo("WORK_BOOT", (1000, 700)), traced_photo("RED_BLACK_RUNNER")
    assert 0.05 <= frontlook.sole_share(boot) < frontlook.sole_share(runner) <= 0.4


def test_b_with_a_front_photo_draws_what_it_saw_and_a_without_it():
    t, spec = traced_photo("RED_BLACK_RUNNER"), spec_of("sneakers", "runner")
    look = front_look("RED_BLACK_RUNNER")
    with_front = front(frontshoe.Chosen(t, frontshoe.FROM_PHOTO, look), spec).body
    side_only = front(t, spec, kind=frontshoe.FROM_PHOTO).body
    assert with_front != side_only
    assert look["marks"] and look["marks"][0][0] in with_front   # the toe mark, on the front
    assert look["lace_color"] in with_front                     # the laces it counted, in their colour
    # A is the template in the trace's colours: a front photo does not change it
    assert front(frontshoe.Chosen(t, frontshoe.FROM_SHAPE, look), spec).body == front(t, spec, kind=frontshoe.FROM_SHAPE).body
    # the same every time, and the same from the look's JSON
    import json
    assert front(frontshoe.Chosen(t.to_json(), frontshoe.FROM_PHOTO, json.dumps(look)), spec).body == with_front


def test_a_front_mark_lies_on_the_toe():
    t, spec = traced_photo("RED_BLACK_RUNNER"), spec_of("sneakers", "runner")
    look = front_look("RED_BLACK_RUNNER")
    shoe = front(frontshoe.Chosen(t, frontshoe.FROM_PHOTO, look), spec)
    import re

    from .test_figure import _flat
    colour = look["marks"][0][0]
    marks = [_flat(d) for d in re.findall(rf'<path d="([^"]+)" fill="{colour}"/>', shoe.body)]
    assert marks
    ys = [y for m in marks for _, y in m]
    toe_y = max(y for _, y in _flat(shoe.upper))
    rim_y = max(y for _, y in _flat(shoe.rim))
    assert all(rim_y < y <= toe_y + 0.5 for y in ys) and math.isfinite(sum(ys))
