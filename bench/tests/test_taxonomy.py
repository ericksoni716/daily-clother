"""The taxonomy as the drawing sees it: the frozen axes match the JSON, every value has an honest
coverage entry, and every value draws a valid picture (a distinct one where it says "drawn")."""
import hashlib
import json
import math
import re
import xml.dom.minidom
from pathlib import Path

import pytest

from closet_bench.fills import Stripes
from closet_bench.illustrate import BUTTON_CONTRAST, INSIDE_CONTRAST, Fill, Spec, _over, contrast, layer, render
from closet_bench.taxonomy import (ACCESSORIES, ACCESSORY_GARMENTS, ACCESSORY_GROUP, ACCESSORY_TEMPLATES, AXES, CORDUROY_WALES,
                                   COVERAGE, GARMENT_DRAWINGS, KNIT_GAUGES, TOP_AXES, WEIGHT_CLASSES, accessory_drawing,
                                   surface_extras, top_drawing)
from closet_bench.templates import BODY_W, BLOCKS, CX, K_PX, SLEEVE_GAP, SLEEVE_HANG, build

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


def test_every_knit_marked_drawn_has_its_own_texture():
    # #163: moss, pointelle and terry are no longer drawn as pique or mesh
    knit = {"neckline": "crew", "cuff": "rib_knit", "hem": "ribbed_band"}
    drawn = [v for v, (status, _) in COVERAGE["knit_structure"].items() if status == "drawn"]
    assert {"moss", "pointelle", "terry_towelling"} <= set(drawn)
    textures = {v: surface_extras({"fabric": v})["texture"] for v in drawn}
    for v in ("moss", "pointelle", "terry_towelling"):
        assert [k for k, t in textures.items() if t == textures[v]] == [v], v
    svgs = {v: draw({**knit, "fabric": v}) for v in drawn}
    for v in ("moss", "pointelle", "terry_towelling"):
        assert [k for k, svg in svgs.items() if svg == svgs[v]] == [v], v
        valid(draw({**knit, "fabric": v, "knit_gauge": "chunky"}, "flat"))


def test_the_hidden_button_down_shows_no_buttons():
    shirt = CONTEXT["collar"]
    hidden = draw({**shirt, "collar": "hidden_button_down"})
    assert hidden != draw({**shirt, "collar": "point"}) and hidden != draw({**shirt, "collar": "button_down"})
    assert COVERAGE["collar"]["hidden_button_down"][0] == "drawn"


def test_surface_extras_suit_trousers():
    extras = surface_extras({"fabric": "corduroy", "corduroy_wale": "wide_wale", "fiber": "cotton"})
    for w in WEIGHT_CLASSES:
        svg = render(Spec("pants", {"leg": "straight"}, Fill("solid", "#6b4a2f"), **{**extras, "weight": w}), "line")
        valid(svg)
    light = render(Spec("pants", {}, Fill("solid", "#6b4a2f"), weight="lightweight"), "line")
    heavy = render(Spec("pants", {}, Fill("solid", "#6b4a2f"), weight="heavyweight"), "line")
    assert light != heavy
    valid(render(Spec("sneaker", {}, Fill("solid", "#ffffff"), weight="heavyweight", halo=True), "line"))


# ---- tailored jackets: their own construction, not a shirt with lapels

JACKETS = ("blazer", "sport_coat", "suit_jacket", "overcoat", "peacoat")
# SVG digests of garments that are not tailored jackets: rebuilding the jackets must not change one byte
# of any other drawing. First recorded before the jackets were rebuilt. Recorded again from main after the
# 84% body width and the depth shading landed there (every one was checked equal between main and the
# jackets branch). When a drawing is changed on purpose, record its digest again in the same change.
# Recorded again for #110 (drawing faults) where a drawing changed on purpose: the cause is noted on each line.
# Every lightweight garment also gained drape folds, and every heavy one with a rib band its soft shade.
UNCHANGED = {
    "t_shirt": "7ec599596bc532fc",
    "henley": "4c2da65dd3332fd4",
    "polo": "ffed94ccace3764e",
    "rugby_shirt": "58043fad9ef598d3",
    "dress_shirt": "c809ac4c9f65fe00",
    "ocbd": "06950d0f0cbd3c6d",
    "casual_button_up": "9c12d14c70ade096",   # #163: new; point collar, chest pocket, vented straight hem
    "flannel_shirt": "f64ec8598d9a7f90",
    "work_shirt": "e27744a52320dbbc",
    "western_shirt": "a1ad566838687b49",
    "camp_collar_shirt": "33fe64a35259670c",
    "popover_shirt": "cac441662b38341d",
    "band_collar_shirt": "e36611ed2e43240f",   # #110: calmer linen
    "guayabera": "8635571b38df9032",   # #110: calmer linen
    "overshirt": "dd3a6290ec43cc3a",
    "tuxedo_shirt": "1da8831867f6be24",   # #110: larger wing tips
    "crewneck_sweatshirt": "1832fa04fb176c8c",
    "hoodie": "d94a19965cb06860",
    "zip_hoodie": "8893ac4861061caa",
    "pullover_sweater": "725e485e6f2ba239",
    "cardigan": "7adab43828f8f794",
    "shawl_cardigan": "0bc8de3347821e13",
    "sweater_vest": "2525fdb5d88de43f",   # #110: armhole band keeps its width
    "quarter_zip": "a6c19157293b4d69",
    "chore_coat": "55f95cedffe81d08",
    "trucker_jacket": "1fd21e47f12d94f2",   # #110: buttoned waistband, not a rib
    "bomber": "edb93b35920fe310",
    "harrington": "85c603c5ff653c7a",
    "field_jacket": "1eab41a1382a9c74",
    "puffer": "ea68fbbdd4556bf6",   # #110: outline swells between channels
    "quilted_jacket": "9daae90d264d9d8d",
    "fleece_jacket": "d1ff07dded0b7647",
    "barn_jacket": "4a3332cae9f90e8b",
    "fleece_pullover": "2ec1c00de609e68f",
    "performance_tee": "af4dd6aa727dae5f",
    "athletic_half_zip": "c45b9acf7d42f45c",
    "track_jacket": "88e586d396ec8f5c",
    "trench_coat": "61766ef34e7fc2f6",   # #163: new; self belt
    "parka": "d5ba24eb82d51c9b",   # #163: new
    "varsity_jacket": "23fbdbda3caf80ad",   # #163: new; sleeves in the second colour
    "waxed_jacket": "fe4f98e0209ee993",   # #163: new; cord collar
    "pants.jeans": "b09a649969597eec",
    "pants.dress": "567a1b5f294a79cc",
    "shoe.derby": "f356f82e866763c4",   # redrawn on purpose: open lacing (#108)
    "shoe.low_sneaker": "f104192ad8e6afc6",
}


def _digest(svg):
    return hashlib.sha256(svg.encode()).hexdigest()[:16]


def _unchanged_svg(name):
    if name in GARMENT_DRAWINGS:
        p, extras, _ = top_drawing(GARMENT_DRAWINGS[name])
        return render(Spec("top", p, Fill("solid", "#336699"), **extras), "line")
    return render({
        "pants.jeans": Spec("pants", dict(jeans=True), Fill("solid", "#5b7fb5")),
        "pants.dress": Spec("pants", dict(crease=True, pleats=1), Fill("solid", "#2c3140")),
        "shoe.derby": Spec("sneaker", dict(style="derby"), Fill("solid", "#1d1e22")),
        "shoe.low_sneaker": Spec("sneaker", {}, Fill("solid", "#f2f2f0")),
    }[name], "line")


def test_every_garment_drawing_but_the_jackets_is_recorded():
    assert set(UNCHANGED) >= set(GARMENT_DRAWINGS) - set(JACKETS)


@pytest.mark.parametrize("name", sorted(UNCHANGED))
def test_non_jacket_drawings_are_unchanged(name):
    assert _digest(_unchanged_svg(name)) == UNCHANGED[name]


def _jacket(name, **kw):
    p, extras, _ = top_drawing({**GARMENT_DRAWINGS[name], **kw})
    if extras.get("weight"):
        p = {**p, "weight": extras["weight"]}
    return p, build("top", p)


@pytest.mark.parametrize("name", JACKETS)
def test_jackets_are_not_a_shirt_with_lapels(name):
    p, jacket = _jacket(name)
    assert p["block"] in ("jacket", "coat")
    shirt = build("top", {**p, "block": "shirt"})
    assert jacket.outline != shirt.outline
    assert {part.role for part in jacket.parts} >= {"lapel_r", "lapel_l", "hole", "edge"}
    assert not {part.role for part in shirt.parts} & {"lapel_r", "lapel_l"}
    assert jacket.anchors["neck"] == shirt.anchors["neck"]
    assert jacket.anchors["shoulder_l"] == shirt.anchors["shoulder_l"]
    assert jacket.anchors["shoulder_r"] == shirt.anchors["shoulder_r"]


def test_single_and_double_breasted_differ():
    _, single = _jacket("blazer", collar="peak_lapel")
    _, double = _jacket("blazer", collar="peak_lapel", placket="double_breasted", placket_buttons=6)
    front = lambda sh: sorted((x, y) for x, y, r in sh.dots if r > 3)
    assert len(front(single)) == 2 and len({x for x, _ in front(single)}) == 1
    assert len(front(double)) == 6 and len({x for x, _ in front(double)}) == 4   # the top row is set wider
    assert single.outline != double.outline or [p.d for p in single.parts] != [p.d for p in double.parts]
    assert draw({**GARMENT_DRAWINGS["blazer"], "collar": "peak_lapel"}) != draw(
        {**GARMENT_DRAWINGS["blazer"], "collar": "peak_lapel", "placket": "double_breasted", "placket_buttons": 6})


def test_blazer_sport_coat_and_suit_jacket_differ():
    shapes = {n: _jacket(n)[1] for n in ("blazer", "sport_coat", "suit_jacket")}
    key = lambda sh: (sh.outline, tuple(p.d for p in sh.parts), tuple(sh.lines))
    assert len({key(sh) for sh in shapes.values()}) == 3
    # and with the cloth left out, they still differ in their construction (pockets, lapels, buttons)
    bare = {n: _jacket(n, fabric=None, fiber=None, weight="midweight")[1] for n in shapes}
    assert len({key(sh) for sh in bare.values()}) == 3
    assert len({draw(GARMENT_DRAWINGS[n]) for n in shapes}) == 3


@pytest.mark.parametrize("name", JACKETS)
def test_jackets_stay_on_the_canvas_and_their_sleeves_off_the_body(name):
    for fit in ("slim", "tailored", "regular", "relaxed", "boxy", "oversized"):
        for weight in WEIGHT_CLASSES:
            _, sh = _jacket(name, fit=fit, weight=weight)
            pts = [(float(x), float(y)) for x, y in re.findall(r"(-?[\d.]+),(-?[\d.]+)", sh.outline)]
            assert all(0 < x < W and 0 < y < H for x, y in pts), (fit, weight)
            sleeve = [(float(x), float(y)) for x, y in re.findall(r"(-?[\d.]+),(-?[\d.]+)", sh.sleeves[0][0])]
            assert min(x for x, _ in sleeve) >= sh.body_box[2] - 0.5, (fit, weight)   # sleeves start at the body's edge
            # S, K, P1, cuff outer, cuff inner, underarm: the sleeve tapers from the armhole to the cuff
            K, Co, Ci, A = sleeve[1], sleeve[3], sleeve[4], sleeve[5]
            d = ((Co[0] - K[0]) / math.dist(K, Co), (Co[1] - K[1]) / math.dist(K, Co))
            top_w = abs((A[0] - K[0]) * d[1] - (A[1] - K[1]) * d[0])
            assert math.dist(Co, Ci) < top_w, (fit, weight)


def _shape(g, **kw):
    p, extras, _ = top_drawing({**g, **kw})
    return build("top", {**p, "weight": extras.get("weight") or p.get("weight")})


def _pts(d):
    return [(float(x), float(y)) for x, y in re.findall(r"(-?[\d.]+),(-?[\d.]+)", d)]


def test_a_tab_collar_shows_its_buttoned_strap_and_closer_points():
    point = _shape(CONTEXT["collar"], collar="point")
    tab = _shape(CONTEXT["collar"], collar="tab")
    strap = [q for q in tab.parts if q.role == "trim"]
    assert len(strap) == 1 and not [q for q in point.parts if q.role == "trim"]
    xs, ys = zip(*_pts(strap[0].d))
    assert max(ys) - min(ys) >= 14                          # tall enough to read at item size
    assert any(abs(x - 200) < 0.5 for x, _, _ in tab.dots)  # buttoned in the middle
    tip = lambda sh: max((max(_pts(q.d), key=lambda v: v[1]) for q in sh.parts if q.role == "collar_r"),
                         key=lambda v: v[1])[0]
    assert tip(tab) < tip(point)                            # the strap pulls the points together


def test_wing_tips_are_wide_enough_to_read():
    sh = _shape(GARMENT_DRAWINGS["tuxedo_shirt"])
    tips = [q for q in sh.parts if q.role == "collar_r" and len(_pts(q.d)) == 4]
    assert tips and max(x for x, _ in _pts(tips[-1].d)) - 200 >= 25


def test_lapels_on_black_and_on_plaid_get_a_shade():
    p, extras, _ = top_drawing(GARMENT_DRAWINGS["blazer"])
    lapel = next(q.d for q in build("top", {**p, "weight": extras.get("weight")}).parts if q.role == "lapel_r")
    count = lambda color: render(Spec("top", p, Fill("solid", color), **extras), "line").count(f'd="{lapel}"')
    assert count("#1a1a1c") > count("#336699")


def test_a_puffer_swells_between_its_channels():
    g = GARMENT_DRAWINGS["puffer"]
    sh = _shape(g)
    flat = _shape(g, quilting=None, weight=surface_extras(g)["weight"])
    assert sh.outline != flat.outline
    sleeve, flat_sleeve = _pts(sh.sleeves[0][0]), _pts(flat.sleeves[0][0])
    # the flat sleeve's outer edge runs straight from P1 to the cuff; the puffer's swells off that line and back
    P1, Co = flat_sleeve[2], flat_sleeve[3]
    u = ((Co[0] - P1[0]) / math.dist(P1, Co), (Co[1] - P1[1]) / math.dist(P1, Co))
    off = [abs((v[0] - P1[0]) * u[1] - (v[1] - P1[1]) * u[0]) for v in sleeve[3:40]]
    assert max(off) > 2.5 and min(off) < 0.5
    assert len(sleeve) > len(flat_sleeve) + 40          # both edges of the sleeve swell


def test_a_trucker_has_a_buttoned_waistband_not_a_rib():
    sh = _shape(GARMENT_DRAWINGS["trucker_jacket"])
    hem_rib = lambda s: [q for q in s.parts if q.role == "band" and "Q" in q.d and q.d.count("L") == 2]
    assert not hem_rib(sh)
    hy = sh.anchors["hem"][1]
    low = [d for d in sh.dots if hy - 25 < d[1] < hy and 100 < d[0] < 300]
    assert len(low) >= 3 and any(abs(x - 200) < 0.5 for x, _, _ in low)   # the front button and an adjuster each side
    assert hem_rib(_shape(GARMENT_DRAWINGS["crewneck_sweatshirt"]))          # a knit keeps its rib


def test_a_vest_armhole_band_meets_the_side_at_full_width():
    sh = _shape(GARMENT_DRAWINGS["sweater_vest"])
    band = [q for q in sh.parts if q.role == "band" and q.clip][0]
    under = max(_pts(band.d), key=lambda v: v[1])
    side = max(x for x, y in _pts(sh.outline) if abs(y - under[1]) < 3)
    assert under[0] > side    # the band's lower edge runs on past the side seam; the outline cuts it square


def test_the_linen_texture_is_sparse():
    svg = draw({**CONTEXT["fit"], "fabric": "linen"})
    tile = re.search(r'<pattern id="ta"[^>]*width="([\d.]+)" height="([\d.]+)"', svg)
    assert tile and float(tile.group(1)) * float(tile.group(2)) >= 56 * 15


def test_only_a_light_cloth_drapes_in_soft_folds():
    shirt = CONTEXT["fit"]
    light = _shape(shirt, weight="lightweight")
    assert len(light.folds) == 6     # two from each underarm, one at each elbow
    assert not _shape(shirt, weight="midweight").folds and not _shape(shirt, weight="heavyweight").folds
    assert all(f in draw({**shirt, "weight": "lightweight"}) for f in light.folds)


def test_a_heavy_knit_shades_where_the_body_meets_its_rib():
    mid = draw({**GARMENT_DRAWINGS["crewneck_sweatshirt"], "weight": "midweight"})
    heavy = draw({**GARMENT_DRAWINGS["crewneck_sweatshirt"], "weight": "heavyweight"})
    assert "feGaussianBlur" in heavy and "feGaussianBlur" not in mid


# ---- the faults left in the tailored jacket (#109)

def _flatten(d, n=16):
    """The points along an SVG path made of M, L, Q, C and Z, the curves sampled."""
    toks = re.findall(r"[MLQCZ]|-?[\d.]+,-?[\d.]+", d)
    pts, cmd, args = [], None, []
    pt = lambda s_: tuple(float(v) for v in s_.split(","))
    for tk in toks + ["Z"]:
        if tk in "MLQCZ":
            if cmd in ("M", "L"):
                pts += [pt(a) for a in args]
            elif cmd == "Q":
                for i in range(0, len(args), 2):
                    p0, c, p1 = pts[-1], pt(args[i]), pt(args[i + 1])
                    pts += [tuple((1 - t) ** 2 * p0[k] + 2 * (1 - t) * t * c[k] + t * t * p1[k] for k in (0, 1))
                            for t in (j / n for j in range(1, n + 1))]
            elif cmd == "C":
                for i in range(0, len(args), 3):
                    p0, c1, c2, p1 = pts[-1], pt(args[i]), pt(args[i + 1]), pt(args[i + 2])
                    pts += [tuple((1 - t) ** 3 * p0[k] + 3 * (1 - t) ** 2 * t * c1[k] + 3 * (1 - t) * t * t * c2[k]
                                  + t ** 3 * p1[k] for k in (0, 1)) for t in (j / n for j in range(1, n + 1))]
            cmd, args = tk, []
        else:
            args.append(tk)
    return pts


def _crossings(poly, y):
    xs = []
    for a, b in zip(poly, poly[1:] + poly[:1]):
        if (a[1] - y) * (b[1] - y) < 0:
            xs.append(a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]))
    return sorted(xs)


def _underarm_gap(sh, y):
    """How wide the card shows between the body's right side and the right sleeve at height y (0 where they meet)."""
    xs = [x for x in _crossings(_flatten(sh.outline), y) if x > CX]
    return xs[1] - xs[0] if len(xs) >= 3 else 0.0


@pytest.mark.parametrize("name", JACKETS)
def test_jacket_sleeves_hang_close_and_part_cleanly_from_the_body(name):
    for fit in ("slim", "tailored", "regular", "relaxed", "boxy", "oversized"):
        for weight in WEIGHT_CLASSES:
            _, sh = _jacket(name, fit=fit, weight=weight)
            assert -sh.sleeves[0][1] <= SLEEVE_HANG + 1, (fit, weight)   # hanging, not splayed out
            # the two outlines (3.8 px wide) part within a few px of where they meet, so no dark wedge forms
            # (with a sharp underarm they ran together for 5 to 11 px)
            top = next(y for y in (sh.body_box[1] + 60 + i * 0.25 for i in range(600)) if _underarm_gap(sh, y) > 0)
            assert _underarm_gap(sh, top + 4) > 3.8, (fit, weight)
            sleeve = [(float(x), float(y)) for x, y in re.findall(r"(-?[\d.]+),(-?[\d.]+)", sh.sleeves[0][0])]
            Ci = sleeve[4]
            assert _underarm_gap(sh, Ci[1] - 1) >= SLEEVE_GAP - 1, (fit, weight)   # the card shows by the cuff


def _front_buttons(sh):
    return sorted((round(x, 1), round(y, 1)) for x, y, r in sh.dots if abs(x - CX) < 60)


def test_a_double_breasted_jacket_told_one_or_two_buttons_shows_six():
    for told in (1, 2, None, 6):
        _, sh = _jacket("blazer", collar="peak_lapel", placket="double_breasted", placket_buttons=told)
        buttons = _front_buttons(sh)
        assert len(buttons) == 6 and len({y for _, y in buttons}) == 3, told   # 6x1, 6x2: three rows of two
    # told one, it fastens on the bottom row: the lapels roll lower than on a 6x2
    one, two = (_jacket("blazer", collar="peak_lapel", placket="double_breasted", placket_buttons=n)[1] for n in (1, 2))
    lapel_low = lambda sh: max(y for part in sh.parts if part.role == "lapel_r" for _, y in _flatten(part.d))
    assert lapel_low(one) > lapel_low(two) + 10
    _, eight = _jacket("blazer", collar="peak_lapel", placket="double_breasted", placket_buttons=8)
    assert len(_front_buttons(eight)) == 8


def _lapel_reach(sh):
    """How far the top lapel reaches out from the centre, halfway down it."""
    lapel = max((_flatten(p_.d) for p_ in sh.parts if p_.role == "lapel_r"), key=lambda pts: max(y for _, y in pts))
    ys = [y for _, y in lapel]
    return _crossings(lapel, (min(ys) + max(ys)) / 2 + 0.01)[-1] - CX


@pytest.mark.parametrize("collar", ("notch_lapel", "peak_lapel", "shawl"))
def test_lapels_grow_with_the_fit(collar):
    reach = [_lapel_reach(_jacket("blazer", collar=collar, fit=f)[1]) for f in ("regular", "relaxed", "oversized")]
    assert reach[0] < reach[1] < reach[2] and reach[2] - reach[0] >= 4, reach


def test_cuff_buttons_are_three_quarters_the_front_buttons():
    for name in JACKETS:
        for weight in WEIGHT_CLASSES:
            _, sh = _jacket(name, weight=weight)
            cuff = sorted(((x, y, r) for x, y, r in sh.dots if x > sh.body_box[2]), key=lambda d: d[1])
            front = [r for x, y, r in sh.dots if abs(x - CX) < 60]
            assert len(cuff) == 4 and cuff[0][2] >= 0.7 * front[0], (name, weight)   # was about half
            assert all(math.dist(a[:2], b[:2]) > a[2] + b[2] for a, b in zip(cuff, cuff[1:])), (name, weight)


def test_three_roll_two_shows_the_top_buttonhole_on_the_lapel_roll():
    _, two = _jacket("sport_coat", placket_buttons=2)
    _, three = _jacket("sport_coat", placket_buttons=3)
    assert _front_buttons(three) == _front_buttons(two) and len(_front_buttons(three)) == 2   # the top button is hidden
    extra = [d for d in three.lines if d not in two.lines and " A " in d]
    assert len(extra) == 1 and not [d for d in two.lines if " A " in d]
    hole = [tuple(float(v) for v in p_.split(",")) for p_ in re.findall(r"-?[\d.]+,-?[\d.]+", extra[0])]
    y = hole[0][1] + 0.01
    assert y < min(y_ for _, y_ in _front_buttons(three))   # above the buttons that fasten
    # on the top lapel: between its roll line and its edge, at that height
    lapel = max((_flatten(p_.d) for p_ in three.parts if p_.role == "lapel_r"), key=lambda pts: max(y_ for _, y_ in pts))
    xs = _crossings(lapel, y)
    assert len(xs) >= 2 and xs[0] - 0.5 <= min(x for x, _ in hole) and max(x for x, _ in hole) <= xs[-1]


def _button_fills(svg):
    return re.findall(r'<circle cx="[\d.]+" cy="[\d.]+" r="[\d.]+" fill="(#[0-9a-f]{6})"', svg)


@pytest.mark.parametrize("cloth", ("#1f2a44", "#151515", "#e8e0cf", "#c2a878", "#4e3a2b", "#8b9098", "#8a6e4b", "#f4f3ee"))
def test_jacket_buttons_stand_out_from_the_cloth(cloth):
    for material in (None, "horn", "metal_shank", "corozo", "wood"):
        for name in ("blazer", "peacoat"):
            g = {**GARMENT_DRAWINGS[name], "closure_material": material}
            fills = _button_fills(draw(g, color=cloth))
            assert len(fills) >= 10, (name, material)   # the front's and the cuffs'
            assert all(contrast(f, cloth) >= BUTTON_CONTRAST for f in fills), (name, material, fills)
            p, extras, _ = top_drawing(g)
            over = Spec("top", {**p, "state": "open"}, Fill("solid", cloth), **extras)
            fills = _button_fills(render(over, "line"))   # worn open: the buttons on one front
            assert fills and all(contrast(f, cloth) >= BUTTON_CONTRAST for f in fills), (name, material, fills)
            valid(layer(Spec("top", top_drawing(GARMENT_DRAWINGS["ocbd"])[0], Fill("solid", "#f4f3ee")), over, "line"))


@pytest.mark.parametrize("cloth", ("#151515", "#1f2a44", "#000000", "#8b9098", "#e8e0cf"))
def test_a_jacket_inside_shows_on_any_cloth(cloth):
    for state in ("closed", "open"):
        p, extras, _ = top_drawing(GARMENT_DRAWINGS["blazer"])
        svg = render(Spec("top", {**p, "state": state}, Fill("solid", cloth), **extras), "line")
        tints = re.findall(r'fill="(#000|#fff)" opacity="(\.2|\.22)"', svg)
        assert tints, state
        for c, op in tints:
            inside = _over(cloth, "#000000" if c == "#000" else "#ffffff", float(op))
            assert contrast(inside, cloth) >= INSIDE_CONTRAST, (state, c, op)


def test_the_jacket_body_keeps_its_width():
    for name in JACKETS:
        p, sh = _jacket(name, fit="tailored", weight="midweight")
        assert sh.body_box[2] - CX == pytest.approx(BLOCKS[p["block"]]["chest"] / 2 * K_PX * BODY_W)


def test_the_footwear_table_follows_the_taxonomy():
    from closet_bench.taxonomy import FOOTWEAR, FOOTWEAR_LACING, FOOTWEAR_TOE_TREATMENT, SHOE_STYLES
    shoes = {n: e for n, e in TAXONOMY["garments"].items() if e["category"] == "footwear"}
    assert list(FOOTWEAR) == list(shoes)
    for fid, (style, _, _, _) in FOOTWEAR.items():
        assert style in SHOE_STYLES
        assert style == {"sandals": "sandal"}.get(shoes[fid]["app_style"], shoes[fid]["app_style"]), fid
    assert list(FOOTWEAR_TOE_TREATMENT) == TAXONOMY["footwear"]["toe_treatment"]
    assert list(FOOTWEAR_LACING) == TAXONOMY["footwear"]["lacing"]
    assert set(COVERAGE["footwear"]) == set(shoes)


@pytest.mark.parametrize("style, words, want_style, want", [
    ("na", ["penny_loafer"], "loafer", {"strap": "penny"}),
    ("loafer", ["tassels"], "loafer", {"strap": "tassel"}),
    ("na", ["horsebit loafer"], "loafer", {"strap": "horsebit"}),
    ("loafer", ["venetian"], "loafer", {"strap": "none"}),
    ("derby", ["plain_toe_oxford"], "oxford", {"toe_cap": "none"}),
    ("derby", ["cap-toe oxford", "6 eyelets"], "oxford", {"toe_cap": "stitched", "eyelets": 6}),
    ("na", ["wholecut"], "oxford", {"toe_cap": "none", "wholecut": True}),
    ("derby", ["brogue", "wingtip"], "derby", {"brogue": "full"}),
    ("na", ["brogues", "medallion"], "oxford", {"brogue": "semi"}),
    ("oxford", ["quarter brogue"], "oxford", {"brogue": "quarter"}),
    ("oxford", ["open_derby"], "derby", {}),
    ("na", ["derby"], "derby", {}),
    ("low_sneaker", ["slide"], "sandal", {"sandal": "slide"}),
    ("sandal", ["sandal", "ankle strap"], "sandal", {"sandal": "strap"}),
    ("sandal", ["flip_flop"], "sandal", {"sandal": "thong"}),
    ("runner", ["embroidered logo"], "runner", {}),
])
def test_the_taggers_shoe_words_choose_the_drawing(style, words, want_style, want):
    from closet_bench.taxonomy import shoe_words
    got_style, params, _ = shoe_words(style, words)
    assert (got_style, params) == (want_style, want)


def test_only_what_is_drawn_leaves_the_seen_list():
    from closet_bench.taxonomy import shoe_words
    # monk_strap is drawn now (#149), patent_oxford too (#163): velvet_slipper is a footwear id still drawn only approximately
    assert shoe_words("derby", ["velvet_slipper", "tassels", "5 eyelets", "red sole"])[2] == ["tassels", "5 eyelets"]
    assert shoe_words("derby", ["patent_oxford", "5 eyelets"])[2] == ["patent_oxford", "5 eyelets"]


@pytest.mark.parametrize("base, key, values", [
    (dict(style="loafer"), "strap", ["penny", "tassel", "horsebit", "none"]),
    (dict(style="sandal"), "sandal", ["slide", "two_strap", "strap", "thong"]),
    (dict(style="derby"), "brogue", ["none", "quarter", "semi", "full"]),
    (dict(style="oxford"), "brogue", ["none", "quarter", "semi", "full"]),
    (dict(style="oxford"), "eyelets", [3, 5, 7]),
    (dict(style="derby"), "eyelets", [3, 5, 7]),
    (dict(style="oxford"), "wholecut", [False, True]),
])
def test_every_shoe_variant_draws_its_own_picture_on_the_same_ground(base, key, values):
    pictures = set()
    for v in values:
        shape = build("sneaker", {**base, key: v})
        assert shape.anchors == build("sneaker", {}).anchors
        svg = render(Spec("sneaker", {**base, key: v}, Fill("solid", "#5a3b28")), "line")
        xml.dom.minidom.parseString(svg)
        pictures.add(svg)
    assert len(pictures) == len(values)


def test_oxford_and_derby_lacing_differ():
    assert build("sneaker", dict(style="oxford")).parts != build("sneaker", dict(style="derby")).parts


# ----------------------------------------------- the rest of the owner's taxonomy (#149)
def test_the_footwear_bottoms_and_colour_tables_follow_the_taxonomy():
    from closet_bench.taxonomy import (BOTTOM_AXES, BOTTOM_DRAWING, COLOR_FAMILIES, DENIM_WASH_SHADE, FABRIC_EFFECTS,
                                       FOOTWEAR_AXES, FOOTWEAR_HEEL, FOOTWEAR_SOLE, FOOTWEAR_TOE_SHAPE, SHADES,
                                       SHORTS_INSEAM_IN)
    foot, bottoms, colors = TAXONOMY["footwear"], TAXONOMY["bottoms"], TAXONOMY["colors"]
    for axis, values in FOOTWEAR_AXES.items():
        assert list(values) == foot[axis], axis
    for axis, values in BOTTOM_AXES.items():
        assert list(values) == bottoms[axis], axis
    assert list(FOOTWEAR_TOE_SHAPE) == foot["toe_shape"] and list(FOOTWEAR_SOLE) == foot["sole"]
    assert list(FOOTWEAR_HEEL) == foot["heel"]
    for key, values in BOTTOM_DRAWING.items():
        assert list(values) == bottoms[key], key
    assert list(DENIM_WASH_SHADE) == bottoms["denim_washes"]
    assert {k: list(v) for k, v in SHORTS_INSEAM_IN.items()} == bottoms["shorts_inseam_in"]
    assert {s["name"]: (s["hex"].lower(), s["app_color"]) for s in colors["shades"]} == SHADES
    assert {k: list(v) for k, v in COLOR_FAMILIES.items()} == colors["families"]
    assert list(FABRIC_EFFECTS) == list(colors["fabric_effects"])


def test_every_footwear_bottoms_and_colour_value_is_in_coverage():
    foot, bottoms, colors = TAXONOMY["footwear"], TAXONOMY["bottoms"], TAXONOMY["colors"]
    for axis in ("toe_shape", "toe_treatment", "lacing", "laces", "sole", "construction", "height", "heel",
                 "upper_material", "leather_colorways", "sneaker_colorways", "eyelets_typical"):
        assert set(COVERAGE[axis]) == set(foot[axis]), axis
    for axis in ("waistband", "fly", "front", "rise", "leg", "break", "hem_finish", "crease", "back_details",
                 "denim_washes", "denim_fades", "distressing", "shorts_inseam_in"):
        assert set(COVERAGE[axis]) == set(bottoms[axis]), axis
    assert set(COVERAGE["trouser_pockets"]) == set(bottoms["pockets"])
    assert set(COVERAGE["shades"]) == {s["name"] for s in colors["shades"]}
    assert set(COVERAGE["families"]) == set(colors["families"])
    assert set(COVERAGE["fabric_effects"]) == set(colors["fabric_effects"])


@pytest.mark.parametrize("base, key, values", [
    (dict(style="boot"), "tread", [None, "lug", "crepe", "wedge"]),
    (dict(style="boot"), "heel", [None, "flat", "block", "cuban"]),
    (dict(style="boot"), "shaft", [0.45, 0.56, 0.74]),
    (dict(style="boot"), "hooks", [0, 3]),
    (dict(style="boot", laces=False), "strap", [None, "engineer", "jodhpur"]),
    (dict(style="boot"), "moc", [False, True]),
    (dict(style="boot", laces=False), "gusset", [False, True]),
    (dict(style="oxford"), "toe", [None, "almond", "pointed"]),
    (dict(style="derby", laces=False), "strap", ["monk", "double_monk"]),
    (dict(style="low_sneaker"), "tread", [None, "cleats"]),
    (dict(style="loafer"), "lace_collar", [False, True]),
    (dict(style="boot"), "rings", [False, True]),
    (dict(style="runner"), "toggle", [False, True]),
    (dict(style="boot"), "toggle", [False, True]),
    (dict(style="oxford"), "shine", [False, True]),
])
def test_every_footwear_part_draws_its_own_picture_on_the_same_ground(base, key, values):
    pictures = set()
    for v in values:
        params = {**base, **({key: v} if v is not None else {})}
        assert build("sneaker", params).anchors == build("sneaker", {}).anchors
        svg = render(Spec("sneaker", params, Fill("solid", "#5a3b28")), "line")
        xml.dom.minidom.parseString(svg)
        pictures.add(svg)
    assert len(pictures) == len(values)


@pytest.mark.parametrize("base, key, values", [
    ({}, "rise", [None, "low", "high"]),
    ({}, "waist", ["belt", "adjusters", "gurkha", "tab", "braces", "half_elastic"]),
    ({}, "fly", [None, "button", "none"]),
    ({}, "leg", ["skinny", "slim", "straight", "relaxed", "bootcut", "flare", "barrel"]),
    ({}, "break", [None, "slight", "full", "stacked"]),
    ({}, "hem", [None, "turnup", "rolled", "raw", "split", "notched", "chain"]),
    ({}, "pleat_dir", [None, "reverse", "forward"]),
    (dict(jeans=True), "fades", [[], ["whiskers"], ["knee"], ["stacks"], ["tracks"], ["pocket"], ["roping"]]),
    (dict(jeans=True), "distress", [[], ["knee_rip"], ["abrasion"], ["patched"], ["sashiko"]]),
    ({}, "panels", [[], ["double_knee"], ["gusset"]]),
    ({}, "extra_pockets", [[], ["zip"], ["rule"], ["hammer"]]),
    ({}, "rivets", [None, True]),
    (dict(pockets="scoop"), "rivets", [None, True]),
])
def test_every_trouser_detail_draws_its_own_picture_from_the_same_waist_and_hem(base, key, values):
    base = {**base, **({"pleats": 1} if key == "pleat_dir" else {})}
    plain = build("pants", {}).anchors
    pictures = set()
    for v in values:
        params = {**base, **({key: v} if v is not None else {})}
        anchors = build("pants", params).anchors
        assert anchors["waist"] == plain["waist"] and anchors["hem"] == plain["hem"], (key, v)
        svg = render(Spec("pants", params, Fill("solid", "#2f4468")), "line")
        xml.dom.minidom.parseString(svg)
        pictures.add(svg)
    assert len(pictures) == len(values)


def _numbers(d):
    return [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", d)]


def test_a_pleat_is_shaded_on_the_side_it_opens_to():
    plain = build("pants", dict(pleats=1))
    assert not [p for p in plain.parts if p.role == "shade"]   # a pleat whose way is not told has no shade
    sides = {}
    for way in ("reverse", "forward"):
        shades = [p for p in build("pants", dict(pleats=1, pleat_dir=way)).parts if p.role == "shade"]
        assert len(shades) == 2   # one on each leg, mirrored
        left = min(shades, key=lambda p: _numbers(p.d)[0])
        xs = _numbers(left.d)[0::2]
        sides[way] = (xs[1] - xs[0])   # from the fold toward where it opens
        right = max(shades, key=lambda p: _numbers(p.d)[0])
        assert [round(2 * CX - x, 1) for x in xs] == [round(x, 1) for x in _numbers(right.d)[0::2]]
    assert sides["reverse"] < 0 < sides["forward"]   # toward the pocket (out) and toward the fly (in)


def test_double_pleats_are_far_enough_apart_to_read_as_two():
    flat, single, double = (build("pants", dict(pleats=n)).lines for n in (0, 1, 2))
    band = build("pants", {}).parts[0].d   # pleats start at the foot of the waistband
    bb = max(_numbers(band)[1::2])
    starts = lambda lines, but: [x for d in lines if d not in but for x, y in [_numbers(d)[:2]] if abs(y - bb) < 0.1]
    first = min(starts(single, flat))      # the left leg's pleat
    second = min(starts(double, single))   # and the one a double pleat adds beside it
    assert first - second >= 15   # about 6 px at grid size


BACK_DETAILS = [("back_pockets", [["welt"], ["jetted"], ["patch"], ["flap"]]), ("back", [["yoke"], ["label"], ["darts"], ["v_loop"]]),
                ("fades", [["honeycombs"]])]


@pytest.mark.parametrize("key,values", BACK_DETAILS)
def test_every_back_detail_draws_its_own_back_view_and_leaves_the_front_alone(key, values):
    front = render(Spec("pants", {}, Fill("solid", "#2f4468")), "line")
    plain = build("pants", dict(view="back"))
    pictures = {render(Spec("pants", dict(view="back"), Fill("solid", "#2f4468")), "line")}
    for v in values:
        assert render(Spec("pants", {key: v}, Fill("solid", "#2f4468")), "line") == front, (key, v)
        back = build("pants", {"view": "back", key: v})
        assert back.anchors == plain.anchors and back.outline == plain.outline, (key, v)
        svg = render(Spec("pants", {"view": "back", key: v}, Fill("solid", "#2f4468")), "line")
        xml.dom.minidom.parseString(svg)
        pictures.add(svg)
    assert len(pictures) == len(values) + 1


def test_the_back_view_leaves_out_what_is_on_the_front():
    front = dict(jeans=True, crease=True, pleats=2, coin=True, cargo=True, extra_pockets=["zip"], panels=["double_knee"],
                 fades=["whiskers", "knee", "pocket"], distress=["knee_rip"])
    bare = dict(jeans=True, cargo=True, crease=True)   # cargo pockets on the side of the thigh and a pressed crease show from behind too
    assert build("pants", {**front, "view": "back"}).parts == build("pants", {**bare, "view": "back"}).parts
    assert build("pants", {**front, "view": "back"}).lines == build("pants", {**bare, "view": "back"}).lines
    assert build("pants", dict(jeans=True, view="back")).parts != build("pants", dict(view="back")).parts   # jeans: a yoke and patches


def test_shorts_are_drawn_to_their_inseam():
    hems = [build("pants", dict(length="short", inseam=i)).anchors["hem"][1] for i in (3, 5, 7, 9, 11)]
    assert hems == sorted(hems) and len(set(hems)) == len(hems)
def test_garments_are_the_owners_clothing_kinds():
    from closet_bench.taxonomy import APP_CATEGORY, BOTTOM_DRAWINGS, GARMENTS, LOUNGE_KINDS, SPORT_KINDS
    data = TAXONOMY
    garments = {k: v for k, v in data["garments"].items() if v["category"] not in ("footwear", "accessory")}
    assert GARMENTS == {k: v["category"] for k, v in garments.items()}
    assert set(APP_CATEGORY) == set(GARMENTS)
    assert all(APP_CATEGORY[k] == v["app_category"] for k, v in garments.items() if v.get("app_category"))
    assert set(SPORT_KINDS) == {k for k, v in garments.items() if v["category"] == "activewear"}
    assert set(LOUNGE_KINDS) == {k for k, v in garments.items() if v["category"] == "loungewear"}
    assert "fleece_pullover" in SPORT_KINDS and APP_CATEGORY["fleece_pullover"] == "sweater"
    assert set(BOTTOM_DRAWINGS) <= set(GARMENTS)
    assert set(COVERAGE["garment"]) == set(GARMENTS)


def test_fleece_pullover_draws_its_blocks_and_binding():
    p, extras, _ = top_drawing({**GARMENT_DRAWINGS["fleece_pullover"], "contrast_trim": True, "second_color": True})
    assert p["binding"] and p["colorblock"]
    svg = render(Spec("top", p, Fill("solid", "#9fdcc4"), trim_color="#f2735f", block_color="#2f6db5", **extras), "line")
    assert 'fill="#2f6db5"' in svg and 'stroke="#f2735f"' in svg
    plain = render(Spec("top", top_drawing(GARMENT_DRAWINGS["fleece_pullover"])[0], Fill("solid", "#9fdcc4")), "line")
    assert 'fill="#2f6db5"' not in plain


def test_the_trench_coats_belt_keeps_the_anchors():
    p, extras, _ = top_drawing(GARMENT_DRAWINGS["trench_coat"])
    assert p["belt"]
    for block_length in ("knee", "regular"):
        q = {**p, "length": block_length}
        belted, plain = build("top", q), build("top", {**q, "belt": False})
        assert belted.anchors == plain.anchors and belted.outline == plain.outline
        assert len(belted.parts) == len(plain.parts) + 3
    assert draw(GARMENT_DRAWINGS["trench_coat"]) != draw({**GARMENT_DRAWINGS["trench_coat"], "garment": None})


def test_outerwear_kinds_draw_what_sets_them_apart():
    parka, _, _ = top_drawing({"garment": "parka", "collar": "point", "placket": None})
    assert parka["neck"] == "hood" and "collar" not in parka and parka["front"] == "zip" and parka["length"] == "long"
    varsity, _, _ = top_drawing({"garment": "varsity_jacket", "collar": "stand", "placket": "snap", "second_color": True})
    assert varsity["collar"] == "rib" and varsity["fastener"] == "snap" and varsity["colorblock"] == ("sleeves",)
    assert varsity["cuffs"] == "rib" and varsity["hem"] == "rib"
    assert "colorblock" not in top_drawing({"garment": "varsity_jacket", "collar": "stand"})[0]
    _, waxed, _ = top_drawing({"garment": "waxed_jacket", "collar": "point", "fabric": "unknown"})
    assert waxed["collar_color"] == "#5a3d26" and waxed["sheen"]
    for kind in ("trench_coat", "parka", "varsity_jacket", "waxed_jacket"):
        assert COVERAGE["garment"][kind][0] == "drawn", kind


def test_a_robe_is_tied_with_a_sash_and_velvet_has_a_sheen():
    robe, _, _ = top_drawing({"garment": "robe", "collar": "shawl", "length": "regular"})
    assert robe["belt"] == "sash" and robe["length"] == "knee" and robe["block"] == "coat"
    sash, buckled = build("top", robe), build("top", {**robe, "belt": True})
    assert sash.anchors == buckled.anchors and sash.parts != buckled.parts
    assert surface_extras({"fabric": "velvet"})["sheen"] and COVERAGE["woven_structure"]["velvet"][0] == "approximate"


def test_sport_and_lounge_bottoms_draw_apart():
    from closet_bench.taxonomy import BOTTOM_DRAWINGS
    svgs = {k: render(Spec("pants", dict(v), Fill("solid", "#30343c"), trim_color="#f2f2f0"), "line")
            for k, v in BOTTOM_DRAWINGS.items()}
    assert all(s.startswith("<svg") for s in svgs.values())
    assert len({svgs[k] for k in ("joggers", "track_pants", "compression_tights", "running_shorts", "open_hem_sweatpants")}) == 5


def test_accessories_are_a_copy_of_the_json():
    garments = {n: e["app_category"] for n, e in TAXONOMY["garments"].items() if e["category"] == "accessory"}
    assert ACCESSORY_GARMENTS == garments
    groups = {k: v for k, v in TAXONOMY["accessories"].items() if k != "app_category"}
    assert {k: list(v) for k, v in ACCESSORIES.items()} == groups


def test_coverage_names_every_accessory_and_every_kind():
    assert set(COVERAGE["accessory"]) == set(ACCESSORY_GARMENTS)
    for g, group in ACCESSORY_GROUP.items():
        assert set(COVERAGE[group]) == set(ACCESSORIES[group]), group
        drawn = g in ACCESSORY_TEMPLATES
        assert (COVERAGE["accessory"][g][0] == "drawn") == drawn, g
        if not drawn:   # nothing of an accessory with no shape of its own is claimed as drawn
            assert all(status == "not_drawn" for status, _ in COVERAGE[group].values()), group


STRIPED = Fill("stripes", "#27344f", stripes=Stripes("vertical", [("#27344f", 0.03), ("#ece4d0", 0.03)]))


@pytest.mark.parametrize("garment", list(ACCESSORY_GARMENTS))
def test_every_accessory_and_kind_draws_valid_svg_and_never_the_top(garment):
    category = ACCESSORY_GARMENTS[garment]
    for kind in (None, *ACCESSORIES[ACCESSORY_GROUP[garment]]):
        made = accessory_drawing(category, garment, kind)
        assert made is not None, (garment, kind)
        template, params, notes = made
        assert template != "top" and all(isinstance(n, str) and n for n in notes)
        if category == "hat":   # a hat's kind decides which of the three hats draws it
            assert template in ("cap", "beanie", "brimmed_hat"), (garment, kind)
        else:
            assert template == (garment if garment in ACCESSORY_TEMPLATES else "accessory"), (garment, kind)
        params.pop("soft", None)
        for fill in (Fill("solid", "#7a5a3a"), STRIPED):
            valid(render(Spec(template, params, fill), "line", uid="acc"))


def test_each_accessory_with_a_shape_draws_differently_by_kind():
    for garment in ACCESSORY_TEMPLATES:
        category = ACCESSORY_GARMENTS[garment]
        drawn = {kind: render(Spec(*accessory_drawing(category, garment, kind)[:2], Fill("solid", "#336699")), "line")
                 for kind, (status, _) in COVERAGE[ACCESSORY_GROUP[garment]].items() if status == "drawn"
                 and accessory_drawing(category, garment, kind)[0] == garment}
        assert len(set(drawn.values())) == len(drawn), garment


def test_the_closet_categories_of_each_kind_of_clothing_follow_the_taxonomy():
    from closet.vocab import CATEGORY
    from closet_bench.taxonomy import GARMENT_CATEGORIES
    garments = TAXONOMY["garments"].values()
    # every category of everyday clothing; footwear, accessories, activewear and loungewear are not kinds a trip counts
    clothing = {g["category"] for g in garments} - {"footwear", "accessory", "activewear", "loungewear"}
    assert set(GARMENT_CATEGORIES) == clothing
    for category, closet in GARMENT_CATEGORIES.items():
        assert closet and set(closet) <= set(CATEGORY), category
        given = {g["app_category"] for g in garments if g["category"] == category and "app_category" in g}
        assert given <= set(closet), category
    assert set(GARMENT_CATEGORIES["bottoms"]) == {g["app_category"] for g in garments if g["category"] == "bottoms"}
