"""The taxonomy as the drawing sees it: the frozen axes match the JSON, every value has an honest
coverage entry, and every value draws a valid picture (a distinct one where it says "drawn")."""
import hashlib
import json
import math
import re
import xml.dom.minidom
from pathlib import Path

import pytest

from closet_bench.illustrate import BUTTON_CONTRAST, INSIDE_CONTRAST, Fill, Spec, _over, contrast, layer, render
from closet_bench.taxonomy import (AXES, CORDUROY_WALES, COVERAGE, GARMENT_DRAWINGS, KNIT_GAUGES, TOP_AXES, WEIGHT_CLASSES,
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
UNCHANGED = {
    "t_shirt": "7ec599596bc532fc",
    "henley": "4c2da65dd3332fd4",
    "polo": "ffed94ccace3764e",
    "rugby_shirt": "acc4ca8b20a1e42d",
    "dress_shirt": "e0551fcbf7514ef4",
    "ocbd": "06950d0f0cbd3c6d",
    "flannel_shirt": "f64ec8598d9a7f90",
    "work_shirt": "e27744a52320dbbc",
    "western_shirt": "a1ad566838687b49",
    "camp_collar_shirt": "bac5875fc1cc3b18",
    "popover_shirt": "cac441662b38341d",
    "band_collar_shirt": "20a9e0c807730277",
    "guayabera": "0b61b57064b7d0ad",
    "overshirt": "dd3a6290ec43cc3a",
    "tuxedo_shirt": "c95f90cddad600d7",
    "crewneck_sweatshirt": "0edf19bc449d8b09",
    "hoodie": "0126877fc9782d00",
    "zip_hoodie": "e1c1a4e860a9dd83",
    "pullover_sweater": "bfd3f8d9ffa21272",
    "cardigan": "7adab43828f8f794",
    "shawl_cardigan": "83fdf05adc7a61a4",
    "sweater_vest": "24bf8dfca26aaa93",
    "quarter_zip": "a6c19157293b4d69",
    "chore_coat": "55f95cedffe81d08",
    "trucker_jacket": "b823063b55bbcecb",
    "bomber": "b489e7d70c3f37ac",
    "harrington": "85c603c5ff653c7a",
    "field_jacket": "1eab41a1382a9c74",
    "puffer": "3a630aaefdc28a76",
    "quilted_jacket": "9daae90d264d9d8d",
    "fleece_jacket": "d1ff07dded0b7647",
    "barn_jacket": "4a3332cae9f90e8b",
    "pants.jeans": "b09a649969597eec",
    "pants.dress": "567a1b5f294a79cc",
    "shoe.derby": "37b558bd4608ec33",
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
