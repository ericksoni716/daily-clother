"""Draw a sheet of the taxonomy values worked on for coverage, one garment group at a time (developer tool; not shipped).

    python tools/make_coverage_sheet.py GROUP [OUT.svg] [--png OUT.png]

GROUP is one of tops, trousers, jackets, shoes, rest, coverage A's tops-weaves, tops-cloths, tops-knits,
tops-colourwork, tops-fibres and tops-kinds, and coverage C's shoes-uppers, shoes-laces, shoes-soles and shoes-kinds.
Each cell is an item drawn the way the app draws it (from a tagger answer, in the owner's style), at two sizes: the
closet grid's and the item page's. The same command run on an
older checkout of the code gives the "before" sheet. A case marked `{"_back": True}` is the item page's small
drawing from the back (an older checkout without one draws the front). With `--png` the sheet is also turned into a picture by a Chrome
or Chromium found on this computer.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tools"))

from make_figure_sheet import to_png  # noqa: E402

from closet.drawing import item  # noqa: E402
from closet.tagger.taxonomy import wash_hex  # noqa: E402
from closet.tagger.schema import Details, ItemTags, Silhouette  # noqa: E402

SHIRT = dict(placket="front_placket", cuff="barrel_1", hem="curved_shirt_tail")
KNIT = dict(neckline="crew", cuff="rib_knit", hem="ribbed_band", sleeve_length="long")
TEE = dict(neckline="crew", sleeve_length="short", hem="straight")
SWEAT = dict(neckline="crew", cuff="rib_knit", hem="ribbed_band", sleeve_construction="raglan")
JACKET = dict(collar="point", placket="zip_full", cuff="barrel_1", hem="straight", pockets="hip_flap_double")


def _weave(caption: str, fabric: str, color: str = "#8fa9c4", **more) -> tuple[str, str, str, dict, dict]:
    return (caption, "shirt", color, dict(collar="point", fabric=fabric, **SHIRT, **more), {})


def _coat(caption: str, fabric: str, color: str) -> tuple[str, str, str, dict, dict]:
    return (caption, "jacket", color, dict(fabric=fabric, **JACKET), {})


def _knit(caption: str, fabric: str, color: str = "#b5a58a", **more) -> tuple[str, str, str, dict, dict]:
    return (caption, "sweater", color, dict(fabric=fabric, **{**KNIT, **more}), {})

# group -> [(caption, category, colour, details, silhouette)]
CASES: dict[str, list[tuple[str, str, str, dict, dict]]] = {
    "tops": [
        ("point collar", "shirt", "#dfe7f1", dict(collar="point", **SHIRT), {}),
        ("button-down", "shirt", "#dfe7f1", dict(collar="button_down", **SHIRT), {}),
        ("hidden button-down", "shirt", "#dfe7f1", dict(collar="hidden_button_down", **SHIRT), {}),
        ("casual button-up", "shirt", "#8fa9c4", dict(garment="casual_button_up", collar="point", pockets="chest_patch_single",
                                                      placket="front_placket", cuff="barrel_1", hem="straight_with_vents"), {}),
        ("pique (as before)", "sweater", "#8a7356", dict(fabric="pique", **KNIT), {}),
        ("moss stitch", "sweater", "#8a7356", dict(fabric="moss", **KNIT), {}),
        ("mesh (as before)", "sweater", "#d9cbb0", dict(fabric="mesh", **KNIT), {}),
        ("pointelle", "sweater", "#d9cbb0", dict(fabric="pointelle", **KNIT), {}),
        ("terry polo", "polo", "#e0a96d", dict(collar="flat_knit", placket="polo", sleeve_length="short", cuff="rib_knit",
                                              fabric="terry_towelling"), {}),
        ("chunky moss", "sweater", "#5c6b4a", dict(fabric="moss", knit_gauge="chunky", **KNIT), {}),
    ],
    # coverage A (tops and knits): plain weaves and jerseys, colourwork knits, the rest of the tops
    "tops-weaves": [
        _weave("no fabric told", "unknown"), _weave("plain weave", "plain"), _weave("poplin", "poplin"),
        _weave("broadcloth", "broadcloth"), _weave("oxford", "oxford"), _weave("pinpoint oxford", "pinpoint_oxford"),
        _weave("royal oxford", "royal_oxford"), _weave("end-on-end", "end_on_end"),
        _weave("chambray", "chambray", "#7f9cc0"), _weave("dobby", "dobby"), _weave("jacquard", "jacquard"),
        _weave("madras", "madras", "#d98a5f"), _weave("voile", "voile", "#e9e2d0"), _weave("challis", "challis", "#9a5b4c"),
        _weave("crepe", "crepe", "#6d7f95"),
    ],
    "tops-cloths": [
        _weave("satin", "satin", "#3c4a6b"), _weave("sateen", "sateen", "#6b7550"),
        _weave("flannel", "flannel", "#8a5a4a"), _weave("brushed twill", "brushed_twill", "#a08a62"),
        _coat("moleskin", "moleskin", "#5c5148"), _coat("canvas", "canvas", "#b09a6d"),
        _coat("gabardine", "gabardine", "#c3b091"), _weave("fresco", "fresco", "#7d8590"),
        _coat("cavalry twill", "cavalry_twill", "#9a8c6a"), _coat("whipcord", "whipcord", "#7a6a4f"),
        _coat("velvet", "velvet", "#4e1a1d"), _coat("melton", "melton", "#2f3b52"),
        _coat("waxed cotton", "waxed_cotton", "#4f5a3c"),
    ],
    "tops-knits": [
        ("tee, no fabric told", "tee", "#8fa9c4", dict(fabric="unknown", **TEE), {}),
        ("jersey tee", "tee", "#8fa9c4", dict(fabric="jersey", **TEE), {}),
        ("slub jersey tee", "tee", "#8fa9c4", dict(fabric="slub_jersey", **TEE), {}),
        ("interlock tee", "tee", "#8fa9c4", dict(fabric="interlock", **TEE), {}),
        ("french terry sweatshirt", "sweater", "#9aa3ad", dict(fabric="french_terry", **SWEAT), {}),
        ("velour sweatshirt", "sweater", "#5b3f6b", dict(fabric="velour", **SWEAT), {}),
        _knit("flat knit sweater", "flat_knit"), _knit("flat knit, fine gauge", "flat_knit", knit_gauge="fine"),
        _knit("shaker stitch", "shaker", knit_gauge="chunky"), _knit("rib 2x2 (as before)", "rib_2x2"),
    ],
    "tops-colourwork": [
        _knit("fair isle", "fair_isle", "#d9cbb0"),
        ("fair isle, navy and red seen", "sweater", "#d9cbb0", dict(fabric="fair_isle", **KNIT),
         {"_second": ["navy", "red"]}),
        _knit("nordic", "nordic", "#27344f"), _knit("argyle", "argyle", "#7a8a5c"),
        ("argyle cardigan", "sweater", "#7a8a5c", dict(fabric="argyle", **{**KNIT, "neckline": "v_neck",
                                                                           "placket": "front_placket"}), {}),
        _knit("intarsia", "intarsia", "#3f6fb0"), _knit("jacquard knit", "jacquard_knit", "#8a3a3a"),
        _knit("guernsey", "guernsey", "#27344f"), _knit("cowichan", "cowichan", "#efe6d2"),
        ("fair isle told as a pattern", "sweater", "#5c6b4a", dict(pattern_name="fair_isle", **KNIT), {}),
    ],
    "tops-fibres": [
        _knit("no fibre told", "unknown"), _knit("cotton", "unknown", fiber="cotton"),
        _knit("merino", "flat_knit", fiber="merino"), _knit("lambswool", "unknown", fiber="lambswool"),
        _knit("acrylic", "unknown", fiber="acrylic"), _weave("hemp", "unknown", "#b9a98a", fiber="hemp"),
        ("worsted wool jacket", "jacket", "#3a3f4a", dict(fiber="worsted_wool", **JACKET), {}),
        ("leather jacket", "jacket", "#3a2a20", dict(fiber="leather", **JACKET), {}),
        ("suede jacket", "jacket", "#9a6a43", dict(fiber="suede", **JACKET), {}),
        ("convertible cuff", "shirt", "#dfe7f1", dict(collar="point", placket="front_placket", cuff="convertible",
                                                     hem="curved_shirt_tail"), {}),
        ("cargo pockets on a top", "jacket", "#5f6b3a", dict(collar="stand", placket="zip_full", pockets="cargo",
                                                             cuff="barrel_1", hem="straight"), {}),
        ("heathered sweatshirt", "sweater", "#a3a6a8", dict(color_texture="heathered", fabric="french_terry", **SWEAT), {}),
        ("marled tee", "tee", "#3f5a7a", dict(color_texture="marled", fabric="jersey", **TEE), {}),
    ],
    "tops-kinds": [
        ("leather jacket", "jacket", "#2a2523", dict(garment="leather_jacket"), {}),
        ("windbreaker", "jacket", "#2a6f74", dict(garment="windbreaker"), {}),
        ("softshell jacket", "jacket", "#3a4250", dict(garment="softshell_jacket"), {}),
        ("rain shell", "jacket", "#c9a227", dict(garment="rain_shell"), {}),
        ("running long sleeve", "tee", "#e0644f", dict(garment="running_long_sleeve"), {}),
        ("running singlet", "tee", "#3f6fb0", dict(garment="running_singlet"), {}),
        ("compression top", "tee", "#1f1f22", dict(garment="compression_top"), {}),
        ("base layer", "tee", "#5c6b4a", dict(garment="base_layer"), {}),
        ("soccer jersey", "tee", "#c8102e", dict(garment="soccer_jersey", trim_color="white"), {"_second": "white"}),
        ("basketball jersey", "tee", "#552583", dict(garment="basketball_jersey", trim_color="yellow"), {"_second": "yellow"}),
        ("hockey jersey", "tee", "#27344f", dict(garment="hockey_jersey"), {"_second": "white"}),
        ("baseball jersey", "shirt", "#f6f5f2", dict(garment="baseball_jersey", trim_color="navy"), {"_second": "navy"}),
        ("cycling jersey", "tee", "#f2c230", dict(garment="cycling_jersey"), {}),
        ("pyjama top, woven", "shirt", "#9fb7d6", dict(garment="pajama_set_woven"), {"_second": "white"}),
        ("pyjama top, knit", "tee", "#8f9296", dict(garment="pajama_set_knit"), {}),
        ("lounge knit top", "sweater", "#b5a58a", dict(garment="lounge_knit_set"), {}),
        ("sweatsuit top", "sweater", "#8f9296", dict(garment="lounge_sweatsuit"), {}),
        ("kimono robe", "coat", "#2a4ea0", dict(garment="kimono_robe"), {}),
        ("smoking jacket", "jacket", "#4e1a1d", dict(garment="smoking_jacket"), {}),
    ],
    "trousers": [
        ("single pleat", "trousers", "#4a4f58", dict(trouser_front="single_pleat"), {}),
        ("double pleat", "trousers", "#4a4f58", dict(trouser_front="double_pleat"), {}),
        ("reverse pleat", "trousers", "#4a4f58", dict(trouser_front="reverse_pleat"), {}),
        ("forward pleat", "trousers", "#4a4f58", dict(trouser_front="forward_pleat"), {}),
        ("double pleat, stone", "trousers", "#c9bfae", dict(garment="chinos", trouser_front="double_pleat"), {}),
        ("reverse pleat, stone", "trousers", "#c9bfae", dict(garment="chinos", trouser_front="reverse_pleat"), {}),
        ("jeans, back", "jeans", "#3f5f8f", dict(trouser_pockets=["scoop", "coin", "back_patch"],
                                                 back_details=["back_yoke", "back_patch_label", "rivets"]), {"_back": True}),
        ("dress trousers, back", "trousers", "#4a4f58", dict(garment="dress_trousers", trouser_front="single_pleat",
                                                            trouser_pockets=["slant", "back_welt_double"],
                                                            back_details=["darts"]), {"_back": True}),
        ("chinos, back", "trousers", "#b9a27c", dict(garment="chinos", trouser_pockets=["slant", "back_welt_single"]),
         {"_back": True}),
        ("fatigues, back", "trousers", "#5f6b3a", dict(garment="fatigues", trouser_pockets=["slant", "back_flap"]),
         {"_back": True}),
        ("V belt loop, back", "trousers", "#30343c", dict(trouser_pockets=["slant", "back_welt_single"],
                                                          back_details=["centre_back_v_loop", "darts"]), {"_back": True}),
        ("honeycombs, back", "jeans", "#2f4468", dict(trouser_pockets=["back_patch"], back_details=["back_yoke"],
                                                      denim_fades=["honeycombs"]), {"_back": True}),
        ("fatigues", "trousers", "#5f6b3a", dict(garment="fatigues"), {}),
        ("low rise jeans", "jeans", "#3f5f8f", dict(rise="low"), {}),
        ("high rise trousers", "trousers", "#4a4f58", dict(rise="high", trouser_front="double_pleat"), {}),
        ("skinny jeans", "jeans", "#3f5f8f", dict(leg_shape="skinny"), {}),
        ("relaxed jeans", "jeans", "#3f5f8f", dict(leg_shape="relaxed"), {}),
        ("flare jeans", "jeans", "#3f5f8f", dict(leg_shape="flare"), {}),
        ("raw denim", "jeans", wash_hex("raw"), dict(denim_wash="raw"), {}),
        ("rinse wash", "jeans", wash_hex("rinse"), dict(denim_wash="rinse"), {}),
        ("dark wash", "jeans", wash_hex("dark"), dict(denim_wash="dark"), {}),
        ("mid wash", "jeans", wash_hex("mid"), dict(denim_wash="mid"), {}),
        ("light wash", "jeans", wash_hex("light"), dict(denim_wash="light"), {}),
        ("black", "jeans", wash_hex("black"), dict(denim_wash="black"), {}),
        ("washed black (faded)", "jeans", wash_hex("washed_black"), dict(denim_wash="washed_black"), {}),
        ("overdyed olive", "jeans", "#5f6b3a", dict(denim_wash="overdyed"), {}),
        ("pyjama trousers", "trousers", "#a9c4e0", dict(garment="pajama_set_woven"), {}),
        ("sweatsuit trousers", "trousers", "#8a8d91", dict(garment="lounge_sweatsuit"), {}),
        ("knit lounge set, shorts", "shorts", "#d9ccb4", dict(garment="lounge_knit_set"), {}),
    ],
    "jackets": [
        ("trench coat", "coat", "#c3b091", dict(garment="trench_coat", collar="notch_lapel", placket="double_breasted",
                                               placket_buttons=6, fabric="gabardine"), dict(top_length="long")),
        ("parka, only its kind told", "coat", "#4b5320", dict(garment="parka", placket="zip_full", pockets="bellows"), {}),
        ("varsity jacket", "jacket", "#1f2a44", dict(garment="varsity_jacket", collar="stand", placket="snap",
                                                     placket_buttons=5, cuff="rib_knit", hem="ribbed_band",
                                                     pockets="slash", fiber="woolen_wool"), {}),
        ("varsity, cream sleeves", "jacket", "#1f2a44", dict(garment="varsity_jacket", collar="stand", placket="snap",
                                                             placket_buttons=5, cuff="rib_knit", hem="ribbed_band",
                                                             pockets="slash", fiber="woolen_wool"), {"_second": "cream"}),
        ("waxed jacket", "jacket", "#4f5a3c", dict(garment="waxed_jacket", collar="point", placket="zip_full",
                                                   pockets="hip_flap_double", fabric="waxed_cotton"), {}),
        ("bomber (as before)", "jacket", "#1f2a44", dict(garment="bomber", collar="stand", placket="zip_full",
                                                         cuff="rib_knit", hem="ribbed_band"), {}),
    ],
    "shoes": [
        ("plain-toe oxford", "dress_shoes", "#1d1e22", dict(footwear="plain_toe_oxford"), {}),
        ("patent oxford", "dress_shoes", "#1d1e22", dict(footwear="patent_oxford"), {}),
        ("patent upper", "dress_shoes", "#4e1a1d", dict(shoe_style="derby", upper_material="patent"), {}),
        ("slide", "sandals", "#3a2a20", dict(footwear="slide"), {}),
        ("flip-flop", "sandals", "#3a2a20", dict(footwear="flip_flop"), {}),
        ("eyelets (boot)", "boots", "#6b4a2f", dict(footwear="service_boot"), {}),
        ("D-rings", "boots", "#6b4a2f", dict(footwear="service_boot", lacing="d_rings"), {}),
        ("speed hooks", "boots", "#6b4a2f", dict(footwear="service_boot", lacing="speed_hooks"), {}),
        ("trail runner", "sneakers", "#5a6470", dict(footwear="trail_runner"), {}),
        ("toggle lace", "sneakers", "#5a6470", dict(footwear="trail_runner", lacing="toggle_speed_lace"), {}),
        ("moc toe", "boots", "#7a5230", dict(footwear="service_boot", toe_shape="moc_toe"), {}),
        ("apron toe", "boots", "#7a5230", dict(footwear="service_boot", toe_treatment="apron"), {}),
        ("boat shoe", "dress_shoes", "#7a5230", dict(footwear="boat_shoe"), {}),
        ("camp moc", "dress_shoes", "#7a5230", dict(footwear="camp_moc"), {}),
    ],
    "shoes-uppers": [
        ("smooth calf", "dress_shoes", "#5a3a26", dict(shoe_style="derby", upper_material="smooth_calf"), {}),
        ("pebble grain", "dress_shoes", "#5a3a26", dict(shoe_style="derby", upper_material="pebble_grain"), {}),
        ("suede", "boots", "#8a6a48", dict(footwear="chukka", upper_material="suede"), {}),
        ("roughout", "boots", "#8a6a48", dict(footwear="service_boot", upper_material="roughout"), {}),
        ("nubuck", "boots", "#b08a5a", dict(footwear="service_boot", upper_material="nubuck"), {}),
        ("shell cordovan", "dress_shoes", "#4e1a1d", dict(shoe_style="oxford", upper_material="shell_cordovan"), {}),
        ("oiled pull-up", "boots", "#7a4a2a", dict(footwear="service_boot", upper_material="oiled_pull_up"), {}),
        ("canvas", "sneakers", "#c9bfae", dict(footwear="canvas_low_top", upper_material="canvas"), {}),
        ("knit mesh", "sneakers", "#5a6470", dict(footwear="running_shoe", upper_material="knit_mesh"), {}),
        ("synthetic leather", "sneakers", "#e8e4dc", dict(footwear="leather_court_sneaker", upper_material="synthetic_leather"), {}),
        ("waxed canvas", "boots", "#4f5a3c", dict(footwear="service_boot", upper_material="waxed_canvas"), {}),
        ("rubber", "boots", "#22422c", dict(footwear="rain_boot", upper_material="rubber"), {}),
        ("velvet", "dress_shoes", "#1f2a44", dict(shoe_style="loafer", upper_material="velvet"), {}),
        ("felt wool", "sneakers", "#8a8d91", dict(footwear="felt_clog", upper_material="felt_wool"), {}),
        ("woven leather", "dress_shoes", "#9a5a2c", dict(shoe_style="loafer", upper_material="woven_leather"), {}),
    ],
    "shoes-laces": [
        ("flat waxed laces", "boots", "#6b4a2f", dict(footwear="service_boot", laces="flat_waxed"), {}),
        ("round waxed laces", "dress_shoes", "#1d1e22", dict(footwear="plain_toe_oxford", laces="round_waxed"), {}),
        ("flat cotton laces", "sneakers", "#e8e4dc", dict(footwear="canvas_low_top", laces="flat_cotton"), {}),
        ("round rope laces", "boots", "#6b4a2f", dict(footwear="hiking_boot", laces="round_rope"), {}),
        ("rawhide laces", "boots", "#6b4a2f", dict(footwear="chukka", laces="rawhide"), {}),
        ("ghillie lacing", "dress_shoes", "#5a3a26", dict(shoe_style="derby", lacing="ghillie"), {}),
        ("split toe", "dress_shoes", "#7a5230", dict(shoe_style="derby", toe_treatment="split_toe"), {}),
        ("chisel toe", "dress_shoes", "#1d1e22", dict(shoe_style="oxford", toe_shape="chisel"), {}),
        ("monk strap", "dress_shoes", "#5a3a26", dict(footwear="monk_strap"), {}),
    ],
    "shoes-soles": [
        ("city rubber sole", "dress_shoes", "#5a3a26", dict(shoe_style="derby", sole="rubber_city"), {}),
        ("studded rubber sole", "dress_shoes", "#5a3a26", dict(shoe_style="derby", sole="studded_rubber"), {}),
        ("foam midsole", "sneakers", "#5a6470", dict(shoe_style="low_sneaker", sole="eva_foam_midsole"), {}),
        ("cork footbed", "sandals", "#5a3a26", dict(footwear="sandal", sole="cork_footbed"), {}),
        ("molded slide", "sandals", "#1d1e22", dict(footwear="slide", sole="molded_slide"), {}),
        ("goodyear welt", "boots", "#6b4a2f", dict(footwear="service_boot", shoe_construction="goodyear_welt"), {}),
        ("storm welt", "boots", "#6b4a2f", dict(footwear="service_boot", shoe_construction="storm_welt"), {}),
        ("blake", "dress_shoes", "#1d1e22", dict(footwear="plain_toe_oxford", shoe_construction="blake"), {}),
        ("stitchdown", "boots", "#7a5230", dict(footwear="desert_boot", shoe_construction="stitchdown"), {}),
        ("cemented", "sneakers", "#e8e4dc", dict(footwear="leather_court_sneaker", shoe_construction="cemented"), {}),
        ("vulcanized", "sneakers", "#2a4ea0", dict(shoe_style="low_sneaker", shoe_construction="vulcanized"), {}),
        ("moccasin", "dress_shoes", "#7a5230", dict(shoe_style="derby", shoe_construction="moccasin"), {}),
        ("no-show height", "sneakers", "#e8e4dc", dict(shoe_style="low_sneaker", footwear_height="no_show"), {}),
        ("knee height", "boots", "#22422c", dict(footwear="rain_boot", footwear_height="knee"), {}),
    ],
    "shoes-kinds": [
        ("trainer", "sneakers", "#5a6470", dict(footwear="trainer"), {}),
        ("running shoe (as before)", "sneakers", "#5a6470", dict(footwear="running_shoe"), {}),
        ("camp moc", "dress_shoes", "#7a5230", dict(footwear="camp_moc"), {}),
        ("boat shoe (as before)", "dress_shoes", "#7a5230", dict(footwear="boat_shoe"), {}),
        ("moccasin slipper", "dress_shoes", "#7a5230", dict(footwear="moccasin_slipper"), {}),
        ("velvet slipper", "dress_shoes", "#22422c", dict(footwear="velvet_slipper"), {}),
    ],
    "rest": [
        ("robe", "coat", "#2a4ea0", dict(garment="robe", collar="shawl", fabric="terry_towelling"), dict(top_length="long")),
        ("smoking jacket", "jacket", "#4e1a1d", dict(garment="smoking_jacket", collar="shawl", fabric="velvet"), {}),
        ("rain shell", "jacket", "#2a6f74", dict(garment="rain_shell", neckline="hood", placket="zip_full",
                                                 pockets="slash"), {}),
        ("velvet blazer", "jacket", "#22422c", dict(collar="notch_lapel", placket="front_placket", placket_buttons=2,
                                                    fabric="velvet"), {}),
    ],
}

SMALL, LARGE, CAPTION = 150, 300, 30


def answer(category: str, details: dict, silhouette: dict) -> dict:
    sil = {k: v for k, v in silhouette.items() if not k.startswith("_")}
    second = silhouette.get("_second") or []
    second = [second] if isinstance(second, str) else list(second)
    return ItemTags(
        category=category, category_confidence=0.9, color="grey", color_confidence=0.9, secondary_colors=second,
        pattern="solid", pattern_confidence=0.9, formality="casual", formality_confidence=0.9, season="all",
        season_confidence=0.9, silhouette=Silhouette.of(**sil), silhouette_confidence=0.9,
        details=Details.plain(**details), details_confidence=0.9, brand=None, size=None, material=None,
        needs_shot=None).model_dump(mode="json")


def _place(svg: str, x: float, y: float, w: float, h: float) -> str:
    return re.sub(r'width="[\d.]+" height="[\d.]+"', f'x="{x}" y="{y}" width="{w}" height="{h}"', svg, count=1)


def sheet(group: str) -> str:
    cases = CASES[group]
    cell_w = SMALL + LARGE + 10
    columns = 3
    rows = (len(cases) + columns - 1) // columns
    w, h = columns * cell_w, rows * (LARGE + CAPTION)
    cells = []
    for i, (caption, category, color, details, sil) in enumerate(cases):
        x, y = (i % columns) * cell_w, (i // columns) * (LARGE + CAPTION)
        tags = answer(category, details, sil)
        # a back view where the code has one (an older checkout draws the front: that is what it showed)
        draw = getattr(item, "back_from_answer", None) if sil.get("_back") else None
        draw = draw or item.svg_from_answer
        svg = draw(tags, color, uid=f"c{i}") or ""
        small = draw(tags, color, uid=f"s{i}") or ""
        cells.append(_place(small, x + 4, y + LARGE - SMALL, SMALL, SMALL))
        cells.append(_place(svg, x + SMALL + 6, y, LARGE, LARGE))
        cells.append(f'<text x="{x + cell_w / 2}" y="{y + LARGE + 20}" text-anchor="middle" font-family="sans-serif" '
                     f'font-size="15" fill="#26231f">{caption}</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'<rect width="{w}" height="{h}" fill="#ffffff"/>{"".join(cells)}</svg>')


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("group", choices=list(CASES))
    ap.add_argument("out", nargs="?", type=Path)
    ap.add_argument("--png", type=Path, help="also write the sheet as a PNG picture")
    args = ap.parse_args()
    out = args.out or ROOT / "bench" / "out" / f"coverage-{args.group}.svg"
    svg = sheet(args.group)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")
    print(f"wrote {out}")
    if args.png:
        w, h = (int(v) for v in re.search(r'width="(\d+)" height="(\d+)"', svg).groups())
        to_png(out, args.png, (w, h))
        print(f"wrote {args.png}")


if __name__ == "__main__":
    main()
