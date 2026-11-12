"""The taxonomy as the drawing sees it: the frozen axes match the JSON, every value has an honest
coverage entry, and every value draws a valid picture (a distinct one where it says "drawn")."""
import json
import re
import xml.dom.minidom
from pathlib import Path

import pytest

from closet_bench.illustrate import Fill, Spec, render
from closet_bench.taxonomy import (AXES, CORDUROY_WALES, COVERAGE, GARMENT_DRAWINGS, KNIT_GAUGES, TOP_AXES, WEIGHT_CLASSES,
                                   surface_extras, top_drawing)
from closet_bench.templates import build

TAXONOMY = json.loads((Path(__file__).resolve().parents[2] / "docs" / "menswear-taxonomy.json").read_text())

# the garment each axis is varied on, and the value every other value is compared with
CONTEXT = {
    "fit": dict(collar="point", cuff="barrel_1", hem="curved_shirt_tail"),
    "sleeve_length": dict(neckline="crew", cuff="rib_knit"),
    "neckline": dict(cuff="rib_knit", hem="ribbed_band"),
    "collar": dict(cuff="barrel_1", hem="curved_shirt_tail"),
    "placket": dict(collar="point", cuff="barrel_1"),
    "cuff": dict(collar="point"),
    "sleeve_construction": dict(neckline="crew", cuff="rib_knit", hem="ribbed_band"),
    "pockets": dict(collar="point", cuff="barrel_1"),
    "hem": dict(collar="point", cuff="barrel_1"),
}
DEFAULT = {"fit": "regular", "sleeve_length": "long", "neckline": "crew", "collar": "none", "placket": "none",
           "cuff": "none", "sleeve_construction": "set_in", "pockets": "none", "hem": "straight"}


def draw(g, style="line", color="#336699", uid="a"):
    p, extras, notes = top_drawing(g)
    assert all(isinstance(n, str) and n for n in notes)
    return render(Spec("top", p, Fill("solid", color), **extras), style, uid=uid)


def valid(svg):
    xml.dom.minidom.parseString(svg)
    assert "nan" not in svg.lower()


def test_axes_are_a_copy_of_the_json():
    for axis, values in AXES.items():
        assert list(values) == TAXONOMY["axes"][axis], axis
    assert "fiber" in AXES
    assert list(WEIGHT_CLASSES) == list(TAXONOMY["weights"]["jersey_gsm"])
    assert list(KNIT_GAUGES) == list(TAXONOMY["weights"]["knit_gauge"])
    assert list(CORDUROY_WALES) == list(TAXONOMY["weights"]["corduroy_wales_per_inch"])


def test_coverage_names_every_value_with_a_valid_status():
    for axis in (*TOP_AXES, "woven_structure", "knit_structure", "fiber"):
        assert set(COVERAGE[axis]) == set(AXES[axis]), axis
    assert set(COVERAGE["weight"]) == set(WEIGHT_CLASSES)
    for axis, values in COVERAGE.items():
        for value, (status, note) in values.items():
            assert status in ("drawn", "approximate", "not_drawn"), (axis, value)
            assert status == "drawn" or note, (axis, value)   # anything less than drawn says why


@pytest.mark.parametrize("axis", TOP_AXES)
def test_every_value_draws_valid_svg_in_every_style_and_fit(axis):
    for value in AXES[axis]:
        for fit in (("slim", "regular", "oversized") if axis != "fit" else (None,)):
            g = {**CONTEXT[axis], axis: value, **({"fit": fit} if fit else {})}
            for style in ("flat", "line", "soft"):
                valid(draw(g, style))


@pytest.mark.parametrize("axis", TOP_AXES)
def test_a_value_marked_drawn_draws_a_different_picture(axis):
    base = draw({**CONTEXT[axis], axis: DEFAULT[axis]})
    for value, (status, _) in COVERAGE[axis].items():
        if status == "drawn" and value != DEFAULT[axis]:
            assert draw({**CONTEXT[axis], axis: value}) != base, (axis, value)


def _first_values(entry):
    g = {}
    for key, values in entry.items():
        if key in ("category", "variants", "signature", "details"):
            continue
        key = {"knit": "fabric", "weave": "fabric"}.get(key, key)
        g[key] = values[0] if isinstance(values, list) else values
    return g


def test_taxonomy_garments_draw_from_their_first_values():
    garments = {n: e for n, e in TAXONOMY["garments"].items()
                if e["category"] in ("knit_top", "woven_shirt", "sweatshirt", "knitwear")}
    assert garments
    for name, entry in garments.items():
        for style in ("flat", "line"):
            valid(draw(_first_values(entry), style, uid=name))


def test_signature_garments_draw():
    for name, g in GARMENT_DRAWINGS.items():
        valid(draw(g, uid=name))


def _outline_points(g):
    p, extras, _ = top_drawing(g)
    if extras.get("weight"):
        p = {**p, "weight": extras["weight"]}
    shape = build("top", p)
    return [(float(x), float(y)) for x, y in re.findall(r"(-?[\d.]+),(-?[\d.]+)", shape.outline)]


def test_outlines_stay_on_the_canvas():
    cases = [{**CONTEXT[axis], axis: value} for axis in TOP_AXES for value in AXES[axis]]
    cases += [{**g, "fit": "oversized", "weight": "super_heavy", "sleeve_construction": s}
              for g in ({"collar": "notch_lapel", "length": "knee"}, {"neckline": "crew", "cuff": "rib_knit"})
              for s in ("set_in", "drop_shoulder", "dolman")]
    cases += list(GARMENT_DRAWINGS.values())
    for g in cases:
        assert all(0 < x < W and 0 < y < H for x, y in _outline_points(g)), g


W, H = 400, 460


@pytest.mark.parametrize("garment", [
    dict(collar="point", placket="front_placket", cuff="barrel_1", pockets="chest_flap_double", fabric="oxford"),
    dict(neckline="crew", cuff="rib_knit", hem="ribbed_band", fabric="flat_knit"),
    dict(collar="notch_lapel", placket="front_placket", pockets="hip_flap_double", length="long", fabric="hopsack"),
])
def test_each_weight_class_draws_differently(garment):
    mid = draw({**garment, "weight": "midweight"})
    for w in WEIGHT_CLASSES:
        svg = draw({**garment, "weight": w})
        valid(svg)
        assert (svg == mid) == (w == "midweight"), w


def test_weight_is_inferred_from_fabric_and_fibre():
    w = lambda **g: surface_extras(g)["weight"]
    assert w(fabric="voile") == "lightweight" and w(fabric="oxford") == "midweight"
    order = WEIGHT_CLASSES.index
    assert order(w(fabric="flannel", fiber="woolen_wool")) > order(w(fabric="flannel", fiber="cotton")) > \
        order(w(fabric="flannel", fiber="polyester"))
    assert w(fabric="polar_fleece", fiber="polyester") == "heavyweight"
    assert w(fabric="melton") == "super_heavy" and w(fiber="linen") == "lightweight"
    assert w(fabric="flat_knit", knit_gauge="chunky") == "heavyweight"
    assert w(fabric="poplin", weight="heavyweight") == "heavyweight"   # what the tagger saw wins
    assert w() is None


def test_halo_fabrics_draw_differently():
    shirt = dict(collar="point", placket="front_placket", weight="heavyweight")
    for halo in (dict(fabric="polar_fleece"), dict(fabric="sherpa"), dict(fiber="mohair"), dict(fiber="shetland")):
        assert surface_extras({**shirt, **halo})["halo"]
    assert not surface_extras({**shirt, "fabric": "poplin"})["halo"]
    plain = draw({**shirt, "fabric": "canvas"})
    fuzzy = draw({**shirt, "fabric": "flannel"})
    assert plain != fuzzy and "feDisplacementMap" in fuzzy and "feDisplacementMap" not in plain


def test_wale_and_gauge_scale_the_texture():
    cord = [surface_extras({"fabric": "corduroy", "corduroy_wale": w}) for w in CORDUROY_WALES]
    assert all(c["texture"] == "corduroy" for c in cord)
    scales = [c["texture_scale"] or 1.0 for c in cord]
    assert scales == sorted(scales) and len(set(scales)) == len(scales)
    svgs = {draw({"collar": "point", "fabric": "corduroy", "corduroy_wale": w}) for w in CORDUROY_WALES}
    assert len(svgs) == len(CORDUROY_WALES)
    assert surface_extras({"fabric": "cable", "knit_gauge": "chunky"})["texture_scale"] > 1


def test_surface_extras_suit_trousers():
    extras = surface_extras({"fabric": "corduroy", "corduroy_wale": "wide_wale", "fiber": "cotton"})
    for w in WEIGHT_CLASSES:
        svg = render(Spec("pants", {"leg": "straight"}, Fill("solid", "#6b4a2f"), **{**extras, "weight": w}), "line")
        valid(svg)
    light = render(Spec("pants", {}, Fill("solid", "#6b4a2f"), weight="lightweight"), "line")
    heavy = render(Spec("pants", {}, Fill("solid", "#6b4a2f"), weight="heavyweight"), "line")
    assert light != heavy
    valid(render(Spec("sneaker", {}, Fill("solid", "#ffffff"), weight="heavyweight", halo=True), "line"))
