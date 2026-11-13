"""The figure composes existing shapes without changing their measurements."""
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from closet.drawing import figure
from closet.drawing.templates import K_PX, PX_CM, SHOE_G, SHOE_L

NS = {"s": "http://www.w3.org/2000/svg"}


def description(category, color="#b4b4b4", silhouette=None, **details):
    return {"category": category, "color_hex": color, "silhouette": silhouette or {}, "details": details}


TEE = description("tee", "#f7f2e8")
SHIRT = description("shirt", "#a9c3e0", placket="front_placket", collar="button_down", hem="curved_shirt_tail")
COAT = description("coat", "#302d2b", {"top_length": "knee"}, collar="notch_lapel", placket="front_placket")
SWEATER = description("sweater", "#7d303d", {"top_length": "cropped"}, hem="ribbed_band")
PANTS = description("trousers", "#394557")
SHORTS = description("shorts", "#72774e")
SHOES = description("sneakers", "#f7f2e8")
BOOTS = description("boots", "#6a4934")
OUTFITS = [
    {"base": SHIRT, "outer": COAT, "bottom": PANTS, "shoes": BOOTS},
    {"base": TEE, "bottom": SHORTS, "shoes": SHOES},
    {"base": TEE, "mid": SHIRT, "outer": COAT, "bottom": PANTS, "shoes": BOOTS},
    {"base": SHIRT, "mid": SWEATER, "bottom": PANTS, "shoes": SHOES},
]


def root(pieces):
    return ET.fromstring(figure.svg_from_pieces(pieces))


def groups(svg, place):
    return svg.findall(f".//s:g[@data-place='{place}']", NS)


def matrix(group):
    return [float(v) for v in group.attrib["transform"].removeprefix("matrix(").removesuffix(")").split()]


def test_tops_use_shared_neck_and_shoulders_without_card_centering():
    pieces = [figure._piece(raw, place) for place, raw in OUTFITS[2].items() if place in ("base", "mid", "outer")]
    for anchor in ("neck", "shoulder_l", "shoulder_r"):
        assert len({p.shape.anchors[anchor] for p in pieces}) == 1
    svg = figure.svg_from_pieces(OUTFITS[2])
    assert 'translate(0 0.0)' in svg
    assert not re.search(r'translate\(0 (?!0\.0\))', svg)
    assert all(groups(ET.fromstring(svg), p) for p in ("base", "mid", "outer"))


def test_open_layers_surround_whole_underlayer_with_back_then_fronts():
    svg = root(OUTFITS[2])
    backs = svg.find("s:g[@data-layer='backs']", NS)
    assert backs is not None
    assert list(backs)[0].attrib["data-back"] == "outer"
    assert backs.find(".//s:g[@data-back='mid']", NS) is not None
    for place, underneath in (("outer", "mid"), ("mid", "base")):
        group = groups(svg, place)[0]
        assert group.attrib["data-state"] == "open"
        children = list(group)
        assert len(children) == 2
        assert children[0].attrib["clip-path"] == f"url(#figure-{place}-under)"
        assert groups(children[0], underneath)
        assert children[1].find(".//s:use", NS) is not None  # the existing fronts
    assert groups(svg, "base")[0].attrib["data-state"] == "closed"
    order = list(svg)
    # The trousers are in front of the lining, not hidden by it below the shirt.
    assert order.index(backs) < order.index(groups(svg, "bottom")[0]) < order.index(groups(svg, "outer")[0])


@pytest.mark.parametrize("detail", [{}, {"placket": "polo"}, {"placket": "zip_half"}, {"placket": "zip_quarter"}])
def test_closed_layers_cover_chest_but_allow_neck_and_hem(detail):
    svg = root({"base": SHIRT, "mid": description("sweater", **detail)})
    group = groups(svg, "mid")[0]
    assert group.attrib["data-state"] == "closed"
    under, cover, collar = list(group)
    assert under.attrib["clip-path"] == "url(#figure-mid-under)"
    assert "clip-path" not in cover.attrib
    assert collar.attrib["clip-path"] == "url(#figure-mid-neck)"
    assert svg.find(".//s:clipPath[@id='figure-mid-neck']/s:path", NS) is not None
    # The only redraw over the closed front is clipped to the template's neck opening.
    piece = figure._piece(description("sweater", **detail), "mid")
    holes = [p.d for p in piece.shape.parts if p.role == "hole"]
    assert [p.attrib["d"] for p in svg.findall(".//s:clipPath[@id='figure-mid-neck']/s:path", NS)] == holes


@pytest.mark.parametrize("sleeve", ["sleeveless", "short", "elbow", "three_quarter"])
@pytest.mark.parametrize("placket", ["none", "front_placket"])
def test_shorter_open_and_closed_layers_do_not_erase_shirt_sleeves(sleeve, placket):
    over = description("sweater", sleeve_length=sleeve, placket=placket)
    svg = root({"base": SHIRT, "mid": over})
    visible = [path.attrib["d"] for path in svg.findall(".//s:clipPath[@id='figure-mid-under']/s:path", NS)]
    shirt = figure._piece(SHIRT, "base")
    assert len(shirt.shape.sleeves) == 2
    assert all(path in visible for path, _ in shirt.shape.sleeves)
    # A third, long-sleeved outer layer covers these exposed sleeves again.
    svg = root({"base": SHIRT, "mid": over, "outer": COAT})
    visible = [path.attrib["d"] for path in svg.findall(".//s:clipPath[@id='figure-outer-under']/s:path", NS)]
    assert all(path not in visible for path, _ in shirt.shape.sleeves)


def test_waist_under_untucked_hem_and_same_physical_scale():
    svg = root(OUTFITS[0])
    a, _, _, d, dx, dy = matrix(groups(svg, "bottom")[0])
    bottom = figure._piece(PANTS, "bottom").shape
    top = figure._piece(SHIRT, "base").shape
    wx, wy = bottom.anchors["waist"]
    assert a == d == K_PX / PX_CM
    assert wx * a + dx == pytest.approx(top.anchors["neck"][0])
    assert wy * a + dy == pytest.approx(figure.WAIST_Y)
    assert figure.WAIST_Y < top.anchors["hem"][1]
    # The 76 cm shirt and the 27 + 81 cm trousers use the same px/cm.
    assert (top.anchors["hem"][1] - top.anchors["neck_point_r"][1]) / 76 == pytest.approx(K_PX)
    assert (bottom.anchors["hem"][1] - wy) * d / (27 + 81) == pytest.approx(K_PX)
    order = [g.attrib.get("data-place") for g in svg if g.tag.endswith("g")]
    assert order.index("bottom") < order.index("outer")  # tops cover, rather than tuck into, the waistband


def test_shoes_share_ground_under_hems_and_do_not_move_up_for_shorts():
    for outfit in OUTFITS[:2]:
        svg = root(outfit)
        shoes = groups(svg, "shoes")
        assert len(shoes) == 2
        for shoe in shoes:
            a, _, _, d, _, dy = matrix(shoe)
            assert abs(a) == d
            assert d * SHOE_L / figure.SHOE_CM == pytest.approx(K_PX)
            assert SHOE_G * d + dy == pytest.approx(figure.GROUND_Y)
        assert matrix(shoes[0])[0] == -matrix(shoes[1])[0]
        bottom = figure._piece(outfit["bottom"], "bottom").shape
        _, _, _, scale, _, dy = matrix(groups(svg, "bottom")[0])
        hem = bottom.anchors["hem"][1] * scale + dy
        assert hem < figure.GROUND_Y
        assert figure.GROUND_Y - hem == pytest.approx((7 if outfit["bottom"] == PANTS else 66) * K_PX)
        # Shoe ankles share the trouser leg centres, not the outer toe positions.
        ankle = figure.SHOE_X0 + .78 * SHOE_L
        for side, shoe in zip((-1, 1), shoes, strict=True):
            a, _, _, _, dx, _ = matrix(shoe)
            assert ankle * a + dx == pytest.approx(figure.CX + side * figure.LEG_CENTRE)


@pytest.mark.parametrize("outfit", OUTFITS + [{"base": SWEATER}, {"shoes": BOOTS}])
def test_whole_figure_fits_canvas_with_equal_margins(outfit):
    svg = root(outfit)
    x, y, w, h = map(float, svg.attrib["viewBox"].split())
    bounds = []
    for place, raw in outfit.items():
        piece = figure._piece(raw, place)
        if place in ("bottom", "shoes"):
            for group in groups(svg, place):
                a, _, _, d, dx, dy = matrix(group)
                bounds.append(figure._bounds(piece.shape, a, d, dx, dy))
        else:
            bounds.append(figure._bounds(piece.shape))
    for distance in (min(b[0] for b in bounds) - x, min(b[1] for b in bounds) - y,
                     x + w - max(b[2] for b in bounds), y + h - max(b[3] for b in bounds)):
        assert distance == pytest.approx(figure.MARGIN, abs=.002)


@pytest.mark.parametrize("pieces", [None, [], "", {}, {"base": None}, {"base": "bad json"},
                                    {"base": {"category": []}}, {"base": {"category": "bag"}},
                                    {"base": {"category": "tee", "color": [], "details": []}},
                                    {"base": 3, "mid": b"\xff", "bottom": {"category": "trousers", "silhouette": []}}])
def test_missing_or_odd_pieces_do_not_raise(pieces):
    assert root(pieces).tag.endswith("svg")


def test_unknown_details_are_dropped_and_undrawable_details_fall_back(monkeypatch):
    raw = description("shirt", "#abc", sleeve_length="tentacles")
    assert groups(root({"base": raw}), "base")
    original = figure.drawing_for

    def fail_detailed(tags):
        if tags.details.collar == "button_down":
            raise ValueError("cannot draw this detail")
        return original(tags)

    monkeypatch.setattr(figure, "drawing_for", fail_detailed)
    actual = figure.svg_from_pieces({"base": SHIRT, "bottom": PANTS})
    expected = figure.svg_from_pieces({"base": description("shirt", SHIRT["color_hex"]), "bottom": PANTS})
    assert actual == expected


def test_description_is_not_mutated_and_cannot_inject_svg():
    raw = description("tee", '#fff" onload="alert(1)', other_features=["<script>"])
    before = json.dumps(raw)
    svg = figure.svg_from_pieces({"base": raw, '"><script>': SHIRT})
    assert json.dumps(raw) == before
    assert "onload" not in svg and "<script" not in svg
    ids = [node.attrib["id"] for node in ET.fromstring(svg).iter() if "id" in node.attrib]
    assert len(ids) == len(set(ids))


def test_figure_needs_no_opencv():
    backend = Path(__file__).resolve().parents[1]
    code = ("import sys; sys.modules['cv2'] = None; "
            "from closet.drawing.figure import svg_from_pieces; "
            "assert '<svg' in svg_from_pieces({'base': {'category': 'shirt'}})")
    subprocess.run([sys.executable, "-c", code], cwd=backend, check=True)
