"""Draw a sheet of the taxonomy values worked on for coverage, one garment group at a time (developer tool; not shipped).

    python tools/make_coverage_sheet.py GROUP [OUT.svg] [--png OUT.png]

GROUP is one of tops, trousers, jackets, shoes, rest, accessories. Each cell is an item drawn the way the app draws it (from a
tagger answer, in the owner's style), at two sizes: the closet grid's and the item page's. The same command run on an
older checkout of the code gives the "before" sheet. With `--png` the sheet is also turned into a picture by a Chrome
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
from closet.tagger.schema import Details, ItemTags, Silhouette  # noqa: E402

SHIRT = dict(placket="front_placket", cuff="barrel_1", hem="curved_shirt_tail")
KNIT = dict(neckline="crew", cuff="rib_knit", hem="ribbed_band", sleeve_length="long")

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
    "trousers": [
        ("trousers, no kind", "trousers", "#b9a27c", {}, {}),
        ("chinos", "trousers", "#b9a27c", dict(garment="chinos"), {}),
        ("dress trousers", "trousers", "#4a4f58", dict(garment="dress_trousers"), {}),
        ("corduroys", "trousers", "#7a5434", dict(garment="corduroys"), {}),
        ("fatigues", "trousers", "#5f6b3a", dict(garment="fatigues"), {}),
        ("cargo pants", "trousers", "#6b6550", dict(garment="cargo_pants"), {}),
        ("work pants", "trousers", "#8a6a3c", dict(garment="work_pants"), {}),
        ("jeans told as trousers", "trousers", "#3f5f8f", dict(garment="jeans"), {}),
        ("shorts", "shorts", "#b9a27c", dict(garment="shorts"), {}),
        ("split hem", "trousers", "#30343c", dict(hem_finish="split"), {}),
        ("notched hem", "trousers", "#30343c", dict(hem_finish="notched"), {}),
        ("rivets", "trousers", "#8a6a3c", dict(back_details=["rivets"]), {}),
        ("stacks fade", "jeans", "#3f5f8f", dict(denim_fades=["stacks"]), {}),
        ("roping fade", "jeans", "#3f5f8f", dict(denim_fades=["roping"]), {}),
        ("reverse pleat", "trousers", "#4a4f58", dict(trouser_front="reverse_pleat"), {}),
        ("forward pleat", "trousers", "#4a4f58", dict(trouser_front="forward_pleat"), {}),
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
    "rest": [
        ("robe", "coat", "#2a4ea0", dict(garment="robe", collar="shawl", fabric="terry_towelling"), dict(top_length="long")),
        ("smoking jacket", "jacket", "#4e1a1d", dict(garment="smoking_jacket", collar="shawl", fabric="velvet"), {}),
        ("rain shell", "jacket", "#2a6f74", dict(garment="rain_shell", neckline="hood", placket="zip_full",
                                                 pockets="slash"), {}),
        ("velvet blazer", "jacket", "#22422c", dict(collar="notch_lapel", placket="front_placket", placket_buttons=2,
                                                    fabric="velvet"), {}),
    ],
    "accessories": [
        ("silk tie", "other", "#27344f", dict(accessory="tie", accessory_kind="silk_woven"), {}),
        ("repp stripe tie", "other", "#6e2633", dict(accessory="tie", accessory_kind="silk_woven",
                                                     pattern_name="university_stripe"), {"_second": "navy"}),
        ("printed silk, dots", "other", "#27344f", dict(accessory="tie", accessory_kind="silk_printed",
                                                        pattern_name="polka_dot"), {"_second": "white"}),
        ("paisley tie", "other", "#4e1a1d", dict(accessory="tie", accessory_kind="silk_printed", pattern_name="paisley"),
         {"_second": "yellow"}),
        ("foulard tie", "other", "#1f2a44", dict(accessory="tie", accessory_kind="silk_printed", pattern_name="foulard"),
         {"_second": "light_blue"}),
        ("club tie", "other", "#22422c", dict(accessory="tie", accessory_kind="silk_printed",
                                              other_features=["club motif"]), {"_second": "yellow"}),
        ("knit tie", "other", "#2a2b2e", dict(accessory="tie", accessory_kind="knit"), {}),
        ("wool tie", "other", "#7a5a3a", dict(accessory="tie", accessory_kind="wool"), {}),
        ("grenadine", "other", "#27344f", dict(accessory="tie", accessory_kind="grenadine"), {}),
        ("skinny silk tie", "other", "#2a2b2e", dict(accessory="tie", accessory_kind="silk_woven",
                                                     other_features=["skinny tie"]), {}),
        ("bow tie", "other", "#1f1f22", dict(accessory="tie", accessory_kind="bow_tie"), {}),
        ("square, flat fold", "other", "#f6f5f2", dict(accessory="pocket_square", accessory_kind="flat"), {}),
        ("square, one point", "other", "#f6f5f2", dict(accessory="pocket_square", accessory_kind="one_point"), {}),
        ("square, puff", "other", "#b8332e", dict(accessory="pocket_square", accessory_kind="puff"), {}),
        ("square, crown", "other", "#a9c3e0", dict(accessory="pocket_square", accessory_kind="crown"), {}),
        ("leather gloves", "other", "#3a2a20", dict(accessory="gloves", accessory_kind="leather_dress"), {}),
        ("knit gloves", "other", "#6f7278", dict(accessory="gloves", accessory_kind="knit"), {}),
        ("mittens", "other", "#8a2f2a", dict(accessory="gloves", accessory_kind="mittens"), {}),
        ("fingerless", "other", "#5c6b4a", dict(accessory="gloves", accessory_kind="fingerless"), {}),
        ("work gloves", "other", "#c2a878", dict(accessory="gloves", accessory_kind="work"), {}),
        ("touchscreen", "other", "#2a2b2e", dict(accessory="gloves", accessory_kind="touchscreen"), {}),
        ("wayfarer", "other", "#1f1f22", dict(accessory="eyewear", accessory_kind="wayfarer"), {}),
        ("aviator, green lenses", "other", "#b8995a", dict(accessory="eyewear", accessory_kind="aviator",
                                                           other_features=["green lenses"]), {}),
        ("round", "other", "#6b4a2f", dict(accessory="eyewear", accessory_kind="round"), {}),
        ("browline", "other", "#2a2b2e", dict(accessory="eyewear", accessory_kind="browline"), {}),
        ("rectangular", "other", "#27344f", dict(accessory="eyewear", accessory_kind="rectangular"), {}),
        ("sport wrap, mirrored", "other", "#d9772b", dict(accessory="eyewear", accessory_kind="sport_wrap",
                                                          other_features=["mirrored lenses"]), {}),
        ("dress watch", "other", "#6b4a2f", dict(accessory="watch", accessory_kind="dress"), {"_second": "cream"}),
        ("dive watch", "other", "#8f9296", dict(accessory="watch", accessory_kind="dive"), {"_second": "navy"}),
        ("field watch, nato", "other", "#6b6f45", dict(accessory="watch", accessory_kind="field",
                                                       other_features=["nato strap"]), {}),
        ("chronograph", "other", "#1f1f22", dict(accessory="watch", accessory_kind="chronograph",
                                                 other_features=["leather strap"]), {"_second": "white"}),
        ("digital sport", "other", "#1f1f22", dict(accessory="watch", accessory_kind="digital_sport"), {}),
        ("square dial", "other", "#6b4a2f", dict(accessory="watch", accessory_kind="dress",
                                                 other_features=["square dial"]), {"_second": "cream"}),
        ("over the calf", "other", "#27344f", dict(accessory="socks", accessory_kind="dress_otc"), {}),
        ("mid-calf", "other", "#1f1f22", dict(accessory="socks", accessory_kind="dress_mid_calf"), {}),
        ("crew, striped", "other", "#b8332e", dict(accessory="socks", accessory_kind="casual_crew",
                                                   pattern_name="rugby_hoops"), {"_second": "cream"}),
        ("argyle", "other", "#6b4a2f", dict(accessory="socks", accessory_kind="dress_mid_calf", pattern_name="argyle"),
         {"_second": "cream"}),
        ("athletic crew", "other", "#f6f5f2", dict(accessory="socks", accessory_kind="athletic_crew"), {}),
        ("no-show", "other", "#ece4d0", dict(accessory="socks", accessory_kind="no_show"), {}),
        ("boot ragg", "other", "#8f9296", dict(accessory="socks", accessory_kind="boot_ragg"), {}),
        ("belt, gunmetal buckle", "belt", "#3a2a20", dict(accessory="belt", accessory_kind="dress_belt",
                                                          other_features=["gunmetal buckle"]), {}),
        ("belt, brass buckle", "belt", "#1f1f22", dict(accessory="belt", accessory_kind="dress_belt",
                                                       other_features=["brass buckle"]), {}),
    ],
}

SMALL, LARGE, CAPTION = 150, 300, 30


def answer(category: str, details: dict, silhouette: dict) -> dict:
    sil = {k: v for k, v in silhouette.items() if not k.startswith("_")}
    second = [silhouette["_second"]] if silhouette.get("_second") else []
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
        svg = item.svg_from_answer(tags, color, uid=f"c{i}") or ""
        small = item.svg_from_answer(tags, color, uid=f"s{i}") or ""
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
