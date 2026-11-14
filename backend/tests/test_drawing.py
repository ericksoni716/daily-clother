"""Drawing an item from its tags (closet.drawing.item): the entry point the app uses."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from closet.drawing import item
from closet.drawing.illustrate import Fill, Spec, render
from closet.tagger.schema import Details, ItemTags, Silhouette, drawing_for

BACKEND = Path(__file__).resolve().parents[1]


def answer(category: str, silhouette: dict | None = None, **details) -> dict:
    """A tagger answer as the app stores it (plain JSON data)."""
    return ItemTags(
        category=category, category_confidence=0.9, color="navy", color_confidence=0.9, secondary_colors=[],
        pattern="solid", pattern_confidence=0.9, formality="casual", formality_confidence=0.9, season="all",
        season_confidence=0.9, silhouette=Silhouette.of(**(silhouette or {})), silhouette_confidence=0.9,
        details=Details.plain(**details), details_confidence=0.9, brand=None, size=None, material=None,
        needs_shot=None).model_dump(mode="json")


def expected(tags: dict, hex_: str, uid: str = "a") -> str:
    template, params, extras, _ = drawing_for(ItemTags.model_validate(tags))
    return render(Spec(template, params, Fill("solid", hex_), **extras), "line", uid=uid)


POLO = answer("polo", {"sleeve": "short"}, neckline="polo_collar", placket="polo", placket_buttons=2,
              button_color="white", fabric="pique")
TROUSERS = answer("trousers", {"leg": "tapered", "pant_length": "ankle"}, waist="belt_loops", pant_hem="turn_up",
                  features=["pleats", "pressed_crease"])
BOOTS = answer("boots", {"shoe_height": "high"}, shoe_style="chelsea_boot", sole_color="black")


@pytest.mark.parametrize("tags", [POLO, TROUSERS, BOOTS], ids=["top", "trousers", "shoes"])
def test_a_full_answer_is_drawn_with_its_details(tags):
    svg = item.svg_from_answer(tags, "#27344f", uid="i1")
    assert svg == expected(tags, "#27344f", "i1")
    assert svg.startswith("<svg") and "#27344f" in svg
    plain = answer(tags["category"])
    assert svg != item.svg_from_answer(plain, "#27344f", uid="i1")   # the details change the drawing
    # stored as JSON text works the same; without a colour of its own the colour word is used
    assert item.svg_from_answer(json.dumps(tags), "#27344f", uid="i1") == svg
    assert item.svg_from_answer(tags) == expected(tags, "#27344f")   # "navy"


def test_top_trousers_and_shoes_are_different_shapes():
    svgs = {item.svg_from_answer(t, "#777777") for t in (POLO, TROUSERS, BOOTS)}
    assert len(svgs) == 3


@pytest.mark.parametrize("category,silhouette", [
    ("shirt", {"sleeve": "long", "neck": "collar", "fit": "slim"}),
    ("jeans", {"leg": "wide", "pant_length": "ankle"}),
    ("sneakers", {"shoe_height": "high"}),
], ids=["top", "trousers", "shoes"])
def test_coarse_fields_alone_are_drawn(category, silhouette):
    svg = item.svg_from_fields(category, "#a9c3e0", "solid", silhouette, uid="c1")
    assert svg == expected(answer(category, silhouette), "#a9c3e0", "c1")
    assert svg != item.svg_from_fields(category, "#a9c3e0", "solid", {}, uid="c1")   # the silhouette is used


def test_coarse_fields_use_the_colour_word_when_there_is_no_hex():
    assert "#27344f" in item.svg_from_fields("tee", None, "solid", {}, color="navy")
    assert item.svg_from_fields("tee", None, None, None) == expected(answer("tee"), item.DEFAULT_HEX)


@pytest.mark.parametrize("category", ["other", "spacesuit", None, 3, ["tee"]])
def test_nothing_to_draw_gives_none(category):
    assert item.svg_from_fields(category, "#000000") is None
    assert item.svg_from_answer({**POLO, "category": category}) is None


@pytest.mark.parametrize("raw", [None, "", "not json", "[1, 2]", 42, [], {}, {"category": "tee"}, b"\xff"])
def test_odd_answers_never_raise(raw):
    out = item.svg_from_answer(raw)
    assert out is None or out == expected(answer("tee"), item.DEFAULT_HEX)


def test_an_answer_with_odd_values_keeps_what_is_valid():
    odd = json.loads(json.dumps(POLO))
    odd["details"]["collar"] = "cravat"                 # not in the vocabulary
    odd["details"]["placket_buttons"] = "two"
    odd["details"]["weird_new_field"] = 7
    odd["silhouette"]["sleeve"] = "very long"
    del odd["details"]["fabric"]                        # as from an older version of the schema
    odd["category_confidence"] = 5
    want = answer("polo", {}, neckline="polo_collar", placket="polo", button_color="white")
    assert item.svg_from_answer(odd, "#27344f") == expected(want, "#27344f")


def test_odd_fields_fall_back_without_raising():
    plain_tee = expected(answer("tee"), item.DEFAULT_HEX)
    assert item.svg_from_fields("tee", "red", "zigzag", {"sleeve": "tentacle", "neck": None, 7: "x"}) == plain_tee
    assert item.svg_from_fields("tee", '#fff" onload="x', None, "not a dict") == plain_tee
    assert item.svg_from_fields("tee", "#123", None, None, uid='"><script>') == expected(answer("tee"), "#123")


def test_a_drawing_that_fails_falls_back_to_the_plainest_of_its_category(monkeypatch):
    real = item.drawing_for

    def fussy(tags):
        if tags.details != Details.plain():
            raise RuntimeError("cannot draw this")
        return real(tags)

    monkeypatch.setattr(item, "drawing_for", fussy)
    assert item.svg_from_answer(BOOTS, "#6b4a32") == expected(answer("boots"), "#6b4a32")

    monkeypatch.setattr(item, "drawing_for", lambda tags: 1 / 0)
    assert item.svg_from_answer(BOOTS, "#6b4a32") is None
    assert item.svg_from_fields("boots", "#6b4a32") is None


def test_importing_the_drawing_code_does_not_import_opencv():
    code = ("import sys\n"
            "import closet.drawing, closet.drawing.templates, closet.drawing.illustrate, closet.drawing.fills\n"
            "import closet.drawing.item as item\n"
            "assert item.svg_from_fields('tee', '#ffffff').startswith('<svg')\n"
            "print('cv2' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


# ----------------------------------------------- the owner's footwear and bottoms blocks (#149)
def _drawn(tags: dict) -> tuple[str, dict]:
    template, params, _, _ = drawing_for(ItemTags.model_validate(tags))
    return template, params


@pytest.mark.parametrize("details, want_style, want", [
    (dict(footwear="chelsea_boot", sole="lug_commando"), "chelsea_boot", {"tread": "lug"}),
    (dict(footwear="logger_boot"), "boot", {"hooks": 4, "tread": "lug"}),
    (dict(footwear="desert_boot"), "boot", {"tread": "crepe"}),
    (dict(footwear="engineer_boot"), "boot", {"strap": "engineer"}),
    (dict(footwear="western_boot"), "boot", {"kind": "western_boot", "heel": "cuban", "laces": False}),
    (dict(footwear="moc_toe_boot"), "boot", {"moc": True, "tread": "wedge"}),
    (dict(footwear="canvas_high_top", footwear_height="mid"), "high_top", {"shaft": 0.44}),
    (dict(footwear="boat_shoe"), "loafer", {"tread": "siped", "lace_collar": True}),
    (dict(footwear="service_boot", footwear_height="boot_8in_plus"), "boot", {"shaft": 0.74}),
    (dict(footwear="derby", lacing="monk_double"), "derby", {"strap": "double_monk", "laces": False}),
    (dict(footwear="service_boot", sole="crepe", heel="flat", eyelets=8), "boot",
     {"tread": "crepe", "heel": "flat", "eyelets": 8}),
    (dict(footwear="canvas_low_top", footwear_height="high"), "high_top", {}),
    (dict(footwear="service_boot", lacing="d_rings"), "boot", {"rings": True}),
    (dict(footwear="trail_runner", lacing="toggle_speed_lace"), "runner", {"toggle": True, "tread": "lug"}),
    (dict(footwear="patent_oxford"), "oxford", {"shine": True, "toe_cap": "none"}),
    (dict(footwear="derby", upper_material="patent"), "derby", {"shine": True}),
    (dict(footwear="flip_flop"), "sandal", {"sandal": "thong"}),
    (dict(footwear="service_boot", toe_treatment="apron"), "boot", {"moc": True}),
])
def test_the_footwear_fields_choose_the_shoe_drawing(details, want_style, want):
    template, params = _drawn(answer("boots" if "boot" in details["footwear"] else "sneakers", **details))
    assert template == "sneaker" and params["style"] == want_style
    assert {k: params.get(k) for k in want} == want


@pytest.mark.parametrize("category, details, want", [
    ("trousers", dict(trouser_front="double_pleat"), {"pleats": 2, "crease": True}),
    ("trousers", dict(trouser_front="single_pleat", crease="none"), {"pleats": 1, "crease": False}),
    ("trousers", dict(hem_finish="turn_up", trouser_break="full", rise="high"), {"hem": "turnup", "break": "full", "rise": "high"}),
    ("trousers", dict(waistband="side_adjusters", fly="button", leg_shape="wide"), {"waist": "adjusters", "fly": "button", "leg": "wide"}),
    ("jeans", dict(denim_fades=["whiskers", "train_tracks"], distressing=["knee_rip"]),
     {"fades": ["tracks", "whiskers"], "distress": ["knee_rip"]}),
    ("trousers", dict(trouser_pockets=["frog_mouth", "zip_pocket"], back_details=["double_knee"]),
     {"pockets": "frog", "extra_pockets": ["zip"], "panels": ["double_knee"]}),
    ("shorts", dict(inseam=5, trouser_break="cropped"), {"inseam": 5, "length": "short"}),
    ("trousers", dict(hem_finish="notched", back_details=["rivets"]), {"hem": "notched", "rivets": True}),
    ("jeans", dict(denim_fades=["roping"]), {"fades": ["roping"]}),
])
def test_the_bottoms_fields_choose_the_trouser_drawing(category, details, want):
    template, params = _drawn(answer(category, **details))
    assert template == "pants"
    assert {k: params.get(k) for k in want} == want


@pytest.mark.parametrize("category, kind, want, fabric", [
    ("trousers", "chinos", {"pockets": "slant", "hem": "plain", "back_pockets": ["welt"]}, "twill"),
    ("trousers", "dress_trousers", {"crease": True, "hem": "plain", "back_pockets": ["jetted"]}, None),
    ("trousers", "jeans", {"jeans": True}, None),
    ("trousers", "corduroys", {"pockets": "slant", "back_pockets": ["welt"]}, "corduroy"),
    ("trousers", "fatigues", {"fly": "button", "back_pockets": ["flap"]}, "twill"),   # back sateen: a sheen looked glossy
    ("trousers", "cargo_pants", {"cargo": True, "back_pockets": ["flap"]}, None),
    ("trousers", "work_pants", {"panels": ["double_knee"], "extra_pockets": ["hammer", "rule"], "back_pockets": ["patch"]},
     "canvas"),
])
def test_an_everyday_trouser_kind_draws_its_own_look(category, kind, want, fabric):
    tags = ItemTags.model_validate(answer(category, garment=kind))
    template, params, extras, _ = drawing_for(tags)
    assert template == "pants" and {k: params.get(k) for k in want} == want
    from closet.tagger.taxonomy import surface_extras
    assert extras.get("texture") == (surface_extras({"fabric": fabric})["texture"] if fabric else None)
    assert item.svg_from_answer(answer(category, garment=kind)) != item.svg_from_answer(answer(category))


@pytest.mark.parametrize("category, kind, like", [
    ("trousers", "pajama_set_woven", "lounge_pants"), ("shorts", "pajama_set_knit", "sleep_shorts"),
    ("trousers", "lounge_knit_set", "joggers"), ("trousers", "lounge_sweatsuit", "sweatpants"),
    ("shorts", "lounge_sweatsuit", "training_shorts"),
])
def test_a_sets_bottom_is_drawn_as_the_bottom_it_is_cut_like(category, kind, like):
    assert _drawn(answer(category, garment=kind)) == _drawn(answer(category, garment=like))


def test_a_told_detail_wins_over_the_kinds_look():
    _, params = _drawn(answer("trousers", garment="dress_trousers", crease="none", hem_finish="turn_up"))
    assert params["crease"] is False and params["hem"] == "turnup"
    _, _, extras, _ = drawing_for(ItemTags.model_validate(answer("trousers", garment="chinos", fabric="corduroy")))
    assert extras["texture"] == "corduroy"


def test_an_answer_stored_before_the_new_fields_reads_as_nothing_told():
    old = answer("boots", shoe_style="chelsea_boot")
    for name in ("footwear", "eyelets", "trouser_pockets", "shade", "inseam", "denim_wash"):
        old["details"].pop(name)
    tags = ItemTags.model_validate(old)
    assert tags.details.footwear == "unknown" and tags.details.eyelets == 0 and tags.details.trouser_pockets == []
    assert tags.details.shade == "unknown" and tags.details.denim_wash == "na"
    assert _drawn(old) == _drawn(answer("boots", shoe_style="chelsea_boot"))


def test_the_new_fields_refuse_values_outside_the_taxonomy():
    for bad in (dict(footwear="moon_boot"), dict(shade="ultraviolet"), dict(denim_fades=["holes"]), dict(hem_finish="lace")):
        with pytest.raises(ValueError):
            Details.plain(**bad)
@pytest.mark.parametrize("category, accessory, kind, template", [
    ("bag", "bag", "daypack", "bag"), ("belt", "belt", "western", "belt"), ("hat", "cap", "trucker_cap", "cap"),
    ("hat", "beanie", "fisherman_beanie", "beanie"), ("hat", "brimmed_hat", "panama", "brimmed_hat"),
    ("scarf", "scarf", "bandana", "scarf"), ("other", "tie", "bow_tie", "accessory"), ("other", "socks", "na", "accessory")])
def test_accessories_are_drawn_by_their_own_template_from_the_taxonomy_id_and_kind(category, accessory, kind, template):
    tags = ItemTags.model_validate({**POLO, "category": category,
                                    "details": {**POLO["details"], "accessory": accessory, "accessory_kind": kind}})
    assert drawing_for(tags)[0] == template
    out = item.drawing_from_answer(tags.model_dump(mode="json"), "#7a5a3a")
    assert out.svg and out.svg != item.svg_from_answer(POLO, "#7a5a3a")


def test_an_accessorys_kind_changes_its_drawing_and_without_one_it_says_so():
    bag = {**POLO, "category": "bag", "details": {**POLO["details"], "accessory": "bag"}}
    kinds = {k: item.svg_from_answer({**bag, "details": {**bag["details"], "accessory_kind": k}}, "#333333")
             for k in ("tote", "daypack", "briefcase")}
    assert len(set(kinds.values())) == 3
    plain = item.drawing_from_fields("bag", "#333333")
    assert plain.svg and any("tote" in n for n in plain.not_drawn)
    for category in ("belt", "hat", "scarf"):
        assert item.svg_from_fields(category, "#333333") not in (None, item.svg_from_fields("tee", "#333333"))


def test_an_answer_from_before_the_accessory_fields_still_draws():
    old = json.loads(json.dumps(POLO))
    del old["details"]["accessory"], old["details"]["accessory_kind"]
    assert ItemTags.model_validate(old).details.accessory == "na"
    assert item.svg_from_answer(old, "#336699") == item.svg_from_answer(POLO, "#336699")
