"""Tracing a shoe from a side-on photo (#192, stage 2a): the quality gate and the traced shoe as data.

Every photo here is drawn by `shoe_photos` (no real photos), so what the tracing finds can be checked against
what was drawn.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from closet.drawing import frontshoe, traced
from closet.drawing import trace as T

from . import shoe_photos as S

BACKEND = Path(__file__).resolve().parents[1]


def given(mask):
    """A cutter that returns a mask already known, as the model cut-out would."""
    return [("model", lambda img: mask.astype(np.uint8) * 255)]


def read(img, cutters=None):
    return T.trace_photo(img, cutters)


def reasons(r) -> str:
    return " | ".join(r.gate.reasons)


# ------------------------------------------------------------------ the gate

def test_a_plain_side_view_passes():
    r = read(S.draw(S.Shoe(), noise=3)[0])
    assert r.gate.ok, reasons(r)
    assert r.oriented.flipped is False


def test_the_toe_may_point_either_way():
    r = read(S.draw(S.Shoe(), noise=3, toe="right")[0])
    assert r.gate.ok, reasons(r)
    assert r.oriented.flipped is True


def test_a_shoe_in_a_white_padded_square_does_not_touch_the_edge():
    # a product photo: the shoe well inside a square of plain white, cut out by the model up to its own edge
    img, truth = S.draw(S.Shoe(), size=(1000, 1000), ground=(255, 255, 255), gradient=False, at=(0.02, 0.62),
                        px_per_cm=1000 * 0.96 / 29.5)
    r = read(img, given(truth))
    assert r.gate.signals["edge_touch"] < 0.01
    assert r.gate.ok, reasons(r)


def test_a_shoe_cut_off_by_the_frame_is_turned_down():
    img, truth = S.draw(S.Shoe())
    img, truth = img.crop((300, 0, 1000, 560)), truth[:, 300:]
    for cutters in (None, given(truth)):
        r = read(img, cutters)
        assert not r.gate.ok
        assert "runs off the edge of the photo" in reasons(r)


@pytest.mark.parametrize("shoe", [
    S.Shoe(toe_spring_cm=2.4, rocker_cm=0.5, heel_bevel_cm=1.2),                # a trainer with toe spring
    S.Shoe(upper=(120, 84, 52), midsole=(60, 50, 44), outsole=None, top=list(frontshoe._BOOT), shaft_cm=17,
           sole_cm=2.6, sole_toe_cm=2.0, toe_spring_cm=1.4),                     # a hiking boot
    S.Shoe(upper=(70, 40, 30), midsole=(40, 30, 25), outsole=None, top=list(frontshoe._DRESS), sole_cm=1.2,
           sole_toe_cm=1.0, toe_spring_cm=1.0, heel_bevel_cm=0.8),               # a brogue
], ids=["trainer", "hiking-boot", "brogue"])
def test_toe_spring_and_a_curved_sole_are_side_on(shoe):
    r = read(S.draw(shoe, noise=3)[0])
    assert r.gate.ok, reasons(r)
    assert r.gate.signals["sole_lift"] < 0.02


def test_a_sole_resting_on_neither_heel_nor_ball_is_not_side_on():
    # an outline that comes to a point underneath (a shoe seen at a slant from below, not standing on its sole)
    import cv2
    rocking = np.zeros((320, 820), np.uint8)
    cv2.fillPoly(rocking, [np.array([[10, 150], [410, 300], [810, 150], [410, 10]], np.int32)], 1)
    assert T.sole_lift(rocking) > T.GATE["sole_lift"][0]
    _, truth = S.draw(S.Shoe(toe_spring_cm=2.4, rocker_cm=0.5, heel_bevel_cm=1.2))
    assert T.sole_lift(truth) < T.GATE["sole_lift"][0] / 2


@pytest.mark.parametrize("pair", [(0.12, 0.1), (0.02, 0.25), (-0.10, 0.12)], ids=["behind", "in-depth", "heel-back"])
def test_a_pair_is_caught(pair):
    r = read(S.draw(S.Shoe(), pair=pair, noise=3)[0])
    assert not r.gate.ok
    assert "two shoes" in reasons(r) or "more than one thing" in reasons(r)


def test_two_shoes_apart_are_caught():
    img, _ = S.draw(S.Shoe(), size=(1600, 560), at=(0.02, 0.8), px_per_cm=22)
    second, _ = S.draw(S.Shoe(), size=(1600, 560), at=(0.55, 0.8), px_per_cm=22)
    both = np.minimum(np.asarray(img), np.asarray(second))
    r = read(T.Image.fromarray(both))
    assert not r.gate.ok
    assert "more than one thing" in reasons(r)


RUNNER = S.Shoe(upper=(225, 225, 228), midsole=(250, 250, 250), outsole=(60, 60, 60), heel_counter=(200, 40, 40),
                heel_tab_cm=1.6, window=(120, 135, 150), laces=(30, 30, 30), sole_cm=3.4, sole_toe_cm=2.0, toe_spring_cm=1.4)
LUG_BOOT = S.Shoe(upper=(120, 80, 50), midsole=(40, 35, 30), outsole=(40, 35, 30), top=list(frontshoe._BOOT), shaft_cm=16,
                  sole_cm=3.0, sole_toe_cm=2.4, lugs_cm=0.6, laces=(200, 170, 90), toe_spring_cm=1.0)
GLOSSY_BLACK = S.Shoe(upper=(28, 28, 32), midsole=(30, 30, 34), outsole=(20, 20, 22), gloss=True, sole_cm=2.4, sole_toe_cm=1.8)


@pytest.mark.parametrize("shoe,size", [
    (S.Shoe(), (1000, 560)),
    (S.Shoe(toe_spring_cm=2.4, rocker_cm=0.5), (1000, 560)),
    (RUNNER, (1000, 560)),               # a heel tab and an air-unit window notch the outline at the heel
    (LUG_BOOT, (1000, 760)),             # the lugs notch the sole all along
    (GLOSSY_BLACK, (1000, 560)),         # a highlight runs along just under the top edge
], ids=["plain", "toe-spring", "runner-heel-tab-window", "lug-boot", "glossy-black"])
def test_one_shoe_is_one_shoe(shoe, size):
    r = read(S.draw(shoe, size=size, noise=3)[0])
    assert r.gate.ok, reasons(r)
    assert r.gate.signals["second_sole"] < T.GATE["second_sole"][0] * 0.6
    assert r.gate.signals["second_top"] < T.GATE["second_top"][0] * 0.7


@pytest.mark.parametrize("pair", [(0.04, 0.12), (0.0, 0.12)], ids=["offset-along-and-in-depth", "straight-behind"])
def test_a_glossy_pair_side_by_side_offset_in_depth_is_caught(pair):
    r = read(S.draw(GLOSSY_BLACK, pair=pair, noise=3)[0])
    assert not r.gate.ok
    assert "two shoes: a second top edge runs along inside the outline" in reasons(r)


def test_a_white_shoe_on_a_light_grey_ground_passes():
    img, truth = S.draw(S.Shoe(upper=(248, 248, 246), midsole=(240, 240, 236), outsole=None), ground=(230, 230, 228),
                        shade_edge=10, noise=2)
    r = read(img)
    assert r.gate.ok, reasons(r)
    iou = ((r.mask > 0) & (truth > 0)).sum() / ((r.mask > 0) | (truth > 0)).sum()
    assert iou > 0.98


def test_a_shoe_that_does_not_stand_out_is_turned_down():
    img, _ = S.draw(S.Shoe(upper=(196, 190, 180), midsole=(200, 194, 184), outsole=None), noise=2)
    r = read(img)
    assert not r.gate.ok
    assert "hardly stands out" in reasons(r)


def test_a_cut_out_that_leaks_falls_back_to_the_other_way():
    img, truth = S.draw(S.Shoe(upper=(248, 248, 246), midsole=(240, 240, 236), outsole=None), ground=(230, 230, 228),
                        shade_edge=10, noise=2)

    def leaky(_img):   # what the model does on white on white: a blob of background joins the shoe
        import cv2
        m = truth.astype(np.uint8) * 255
        cv2.ellipse(m, (500, 250), (330, 200), 0, 0, 360, 255, -1)
        return m

    r = read(img, [("model", leaky), ("grabcut", T.grabcut_mask)])
    assert r.gate.ok, reasons(r)
    assert r.cutout_by == "grabcut"
    assert [a.cutout_by for a in r.attempts] == ["model", "grabcut"]
    assert r.attempts[0].reasons and not r.attempts[1].reasons


def test_when_every_cut_out_fails_the_one_with_fewest_reasons_is_kept():
    img, truth = S.draw(S.Shoe(), noise=3)
    r = read(img, [("model", lambda _i: None), ("grabcut", T.grabcut_mask)])
    assert r.cutout_by == "grabcut" and r.gate.ok
    blank = T.Image.new("RGB", (400, 300), (200, 200, 200))
    r = read(blank, [("model", lambda _i: np.zeros((300, 400), np.uint8))])
    assert not r.gate.ok and r.oriented is None


def test_refining_smooths_a_jagged_cut_out_edge():
    img, truth = S.draw(S.Shoe(upper=(248, 248, 246), midsole=(240, 240, 236), outsole=None), ground=(230, 230, 228),
                        shade_edge=10, noise=2)
    rng = np.random.default_rng(3)
    jagged = truth.copy()
    ys, xs = np.nonzero(truth)
    for i in rng.choice(len(xs), 60, replace=False):   # notches into the shoe and spurs out of it
        y, x = ys[i], xs[i]
        jagged[max(0, y - 6):y + 6, max(0, x - 6):x + 6] = rng.integers(0, 2)

    def iou(m):
        return ((m > 0) & (truth > 0)).sum() / ((m > 0) | (truth > 0)).sum()

    refined = T.refine_mask(np.asarray(img), jagged)
    assert iou(refined) > iou(jagged)


def test_a_blurred_photo_is_turned_down():
    r = read(S.draw(S.Shoe(), blur=10, noise=2)[0])
    assert not r.gate.ok
    assert "blurred" in reasons(r)


def test_a_front_view_is_turned_down():
    r = read(S.front_view())
    assert not r.gate.ok
    assert "not side-on" in reasons(r) or "toe and heel look alike" in reasons(r)


def test_every_reason_is_in_plain_words():
    for name, (_, way, why) in T.GATE.items():
        assert way in ("above", "below")
        assert "_" not in why and why[0].islower(), name


# ------------------------------------------------------------------ the traced shoe

RICH = S.Shoe(upper=S.NAVY, toe_cap=S.TAN, heel_counter=S.RED, stripes=S.WHITE, laces=S.WHITE, eyelets=S.SILVER,
              stitching=S.CREAM)


@pytest.fixture(scope="module")
def rich():
    img, _ = S.draw(RICH, noise=1)
    r = read(img)
    assert r.gate.ok, reasons(r)
    return traced.traced_shoe(r)


def test_the_profile_is_recovered(rich):
    us = np.array(rich.profile.u)
    assert us[0] == 0 and us[-1] == 1 and len(us) == traced.PROFILE_N
    sel = (us >= 0.05) & (us <= 0.95)
    assert np.abs(np.array(rich.profile.top) - RICH.top_line(us))[sel].max() < 0.5
    assert np.abs(np.array(rich.profile.bottom) - RICH.bottom(us))[sel].max() < 0.3
    assert np.median(np.abs(np.array(rich.profile.sole) - RICH.sole(us))[sel]) < 0.3
    # the upper's height above the sole, as frontshoe's tables give it
    for u, v in frontshoe._LOW[1:-1]:
        assert abs(rich.profile.top_above_sole(u) - v) < 0.7


def test_toe_spring_is_measured():
    shoe = S.Shoe(toe_spring_cm=1.6)
    flat = traced.traced_shoe(read(S.draw(S.Shoe(), noise=1)[0]))
    sprung = traced.traced_shoe(read(S.draw(shoe, noise=1)[0]))
    assert flat.profile.bottom[-3] < 0.25
    assert abs(sprung.profile.bottom[-3] - shoe.bottom(flat.profile.u[-3])) < 0.5
    assert sprung.profile.bottom[-3] > 0.8


def colour_close(hex_, rgb, de=8.0):
    return T.delta_e(T.to_lab(traced._rgb(hex_)), T.to_lab(np.array([[rgb]], np.uint8))) < de


def test_the_parts_colours_are_recovered(rich):
    want = {"toe_cap": S.TAN, "heel_counter": S.RED, "vamp": S.NAVY, "quarter": S.NAVY, "midsole": S.WHITE,
            "outsole": S.GREY, "laces": S.WHITE, "eyelets": S.SILVER, "stitching": S.CREAM}
    for name, rgb in want.items():
        p = rich.part(name)
        assert p is not None, name
        assert p.measured, name
        assert colour_close(p.color, rgb, 12), (name, p.color)
        # a part in its own colour has its own outline; one in the base colour says so
        assert p.region and all(len(pt) == 2 for pt in p.region[0]) or p.within == "upper", (name, p)
    assert rich.part("vamp").within == rich.part("quarter").within == "upper"
    # each part sits where it should along the shoe
    toe = np.array(rich.part("toe_cap").region[0])
    heel = np.array(rich.part("heel_counter").region[0])
    assert toe[:, 0].min() > 0.7 and heel[:, 0].max() < 0.3


def test_parts_follow_the_traced_panels_not_straight_lines():
    # a red mudguard from u 0.55 round the toe crosses the vamp and toe cap zones: it stays one piece
    shoe = S.Shoe(upper=(30, 30, 30), mudguard=(200, 40, 40), heel_counter=(200, 40, 40), laces=S.WHITE)
    t = traced.traced_shoe(read(S.draw(shoe, noise=1)[0]))
    red = next(r for r in t.regions if colour_close(r.color, (200, 40, 40), 12))
    assert len(red.labels) == len(red.paths)
    spans = {lab: np.array(path[0])[:, 0] for lab, path in zip(red.labels, red.paths, strict=True)}
    assert set(spans) == {"heel_counter", "vamp"}
    assert spans["vamp"].min() < 0.6 and spans["vamp"].max() > 0.97
    assert spans["heel_counter"].max() < 0.25
    # the vamp is mostly black: its colour is not a blend with the mudguard's red
    assert colour_close(t.part("vamp").color, (30, 30, 30), 8)
    # a part with its own piece is outlined by that piece
    heel = np.array(t.part("heel_counter").region[0])
    piece = np.array(red.paths[red.labels.index("heel_counter")][0])
    assert np.allclose(heel.min(0), piece.min(0), atol=[0.02, 0.3]) and np.allclose(heel.max(0), piece.max(0), atol=[0.02, 0.3])
    # every piece is labelled, and the sole's pieces as the sole's parts
    assert all(len(r.labels) == len(r.paths) for r in t.regions)
    assert t.regions[0].labels == ["upper"]
    assert "outsole" in {lab for r in t.regions for lab in r.labels}


def test_the_lace_pieces_are_labelled_laces(rich):
    laces = [lab for r in rich.regions for lab in r.labels if lab == "laces"]
    assert len(laces) >= 3


def test_a_record_of_version_1_still_reads(rich):
    d = json.loads(rich.to_json())
    d["version"] = 1
    for p in d["parts"]:
        del p["within"]
    for r in d["regions"]:
        del r["labels"]
    old = traced.TracedShoe.from_json(json.dumps(d))
    assert old.version == 1 and old.regions[0].labels == [] and old.part("vamp").within == ""


def test_a_part_not_seen_is_inferred():
    # a boot's shaft hides nothing, but a shoe with no tongue zone (a slip-on, low at the throat) still has one
    p = traced._inferred([traced.Part("vamp", "#123456", True)], "tongue", "#000000")
    assert p == "#123456"


@pytest.mark.parametrize("shoe,count", [
    (S.Shoe(upper=(225, 225, 228), laces=(30, 30, 30), lace_style="cross", lace_count=7), 7),
    (S.Shoe(upper=(200, 40, 40), laces=(240, 240, 240), eyelets=S.SILVER, lace_style="cross", lace_count=7), 7),
    (S.Shoe(upper=S.NAVY, laces=S.WHITE, lace_style="cross", lace_count=5), 5),
    (S.Shoe(upper=S.NAVY, laces=S.WHITE, lace_count=7), 7),
], ids=["cross-7-dark", "cross-7-white-silver-eyelets", "cross-5", "bars-7"])
def test_laces_that_cross_and_touch_are_each_counted(shoe, count):
    t = traced.traced_shoe(read(S.draw(shoe, noise=2)[0]))
    assert t.laces and t.laces.count == count, t.laces
    assert colour_close(t.laces.color, shoe.laces, 20)
    laces = next(p for p in t.parts if p.name == "laces")
    assert laces.region


def test_laces_and_eyelets_are_counted(rich):
    assert rich.eyelets and abs(rich.eyelets.count - 6) <= 1
    assert abs(rich.eyelets.spacing_cm - 0.06 * frontshoe.LENGTH) < 0.4
    assert rich.laces and rich.laces.count == 5
    assert abs(rich.laces.spacing_cm - 0.07 * frontshoe.LENGTH) < 0.5
    assert colour_close(rich.laces.color, S.WHITE, 12)
    assert rich.stitching and rich.stitching.count >= 4


def test_the_stripes_are_a_mark(rich):
    stripes = [m for m in rich.marks if m.kind == "stripes"]
    assert len(stripes) == 1, rich.marks
    m = stripes[0]
    assert m.count == 3
    assert 0.25 < m.u < 0.5 and 40 < m.angle < 80
    assert colour_close(m.color, S.WHITE, 12)
    assert len(m.path) == 3
    # laces, eyelets and stitching are not marks
    assert all(m.kind == "stripes" for m in rich.marks)


def test_the_style_hint_follows_the_profile(rich):
    assert rich.style in frontshoe.TRAINERS
    dress = S.Shoe(upper=(70, 40, 30), midsole=(40, 30, 25), outsole=None, top=list(frontshoe._DRESS), sole_cm=1.2,
                   sole_toe_cm=1.0, laces=(20, 15, 12), eyelets=(150, 130, 60))
    assert traced.traced_shoe(read(S.draw(dress, noise=1)[0])).style in ("derby", "oxford")
    boot = S.Shoe(upper=S.TAN, top=list(frontshoe._BOOT), shaft_cm=16, sole_cm=2.2, sole_toe_cm=1.8,
                  midsole=(60, 50, 40), outsole=None)
    assert traced.traced_shoe(read(S.draw(boot, noise=1)[0])).style in ("boot", "high_top", "chelsea_boot")


@pytest.mark.parametrize("shoe", [
    RUNNER,
    S.Shoe(upper=(30, 30, 30), midsole=(240, 240, 240), outsole=(200, 30, 30), heel_tab_cm=2.5, sole_cm=4.0,
           sole_toe_cm=2.4, toe_spring_cm=1.8, laces=(240, 240, 240)),
    GLOSSY_BLACK,
], ids=["runner-heel-tab", "thick-sole-big-tab", "glossy-low"])
def test_a_low_shoe_with_a_heel_tab_or_a_thick_sole_is_not_a_boot(shoe):
    t = traced.traced_shoe(read(S.draw(shoe, noise=2)[0]))
    assert t.style not in ("boot", "high_top", "chelsea_boot"), t.style
    if shoe.laces:
        assert t.style in frontshoe.TRAINERS


def test_the_record_round_trips_through_json(rich):
    text = rich.to_json()
    back = traced.TracedShoe.from_json(text)
    assert back == rich
    assert back.to_json() == text
    d = json.loads(text)
    assert d["version"] == traced.VERSION
    assert d["gate"]["ok"] is True and d["gate"]["reasons"] == []
    assert 0 < d["confidence"] <= 1
    assert d["regions"][0]["part"] == "silhouette"


def test_a_newer_record_is_refused(rich):
    d = json.loads(rich.to_json())
    d["version"] = traced.VERSION + 1
    with pytest.raises(ValueError):
        traced.TracedShoe.from_json(json.dumps(d))


def test_a_turned_down_photo_keeps_its_reasons_and_less_confidence():
    r = read(S.draw(S.Shoe(), pair=(0.12, 0.1), noise=3)[0])
    t = traced.traced_shoe(r)
    assert t.gate["ok"] is False and t.gate["reasons"]
    assert t.confidence <= 0.5


def test_importing_the_tracing_code_does_not_import_opencv():
    code = ("import sys\n"
            "import closet.drawing.trace, closet.drawing.traced\n"
            "print('cv2' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"
