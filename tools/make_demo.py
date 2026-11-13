"""Regenerate the demo closet's data (developer tool; not shipped).

    python tools/make_demo.py --models-dir <folder holding isnet-general-use.onnx>

Writes backend/closet/demo_data/: items.json, images/ and the two small files
the program's self-check uses. About a quarter of the items are open-licence
photos run through the real pipeline; the rest are drawn from templates only.

Each item also gets a stored tagging answer built from what this file knows
about it, so the demo closet shows the same screens as a tagged closet without
ever being sent to Claude. After a change to the tagging schema, rewrite just
those answers (no model needed):

    python tools/make_demo.py --answers-only
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))
sys.path.insert(0, str(ROOT / "backend"))

from closet.drawing import fills  # noqa: E402
from closet.drawing.illustrate import Fill, Spec, render  # noqa: E402
from closet.tagger.schema import NAMED_HEX, SCHEMA_VERSION, Details, ItemTags, Silhouette  # noqa: E402
from closet_bench import cutout as C  # noqa: E402
from closet_bench.hardcases import build_spec  # noqa: E402

OUT = ROOT / "backend" / "closet" / "demo_data"
STYLE = "line"   # the owner chose style B: bold outline, thin inner lines
NS = uuid.UUID("6f1d3c1e-7b1a-4c58-9d55-000000c105e7")


def iid(name: str) -> str:
    return uuid.uuid5(NS, name).hex


def stripes(a: str, b: str, wa: float = 0.045, wb: float = 0.045) -> Fill:
    return Fill("stripes", a, stripes=fills.Stripes("horizontal", [(a, wa), (b, wb)]))


# name, category, colour word, hex or Fill, template, params, silhouette, formality, season, extras
DRAWN = [
    ("White tee", "tee", "white", "#f4f2ee", "top", dict(sleeve="short"), dict(sleeve="short", neck="crew"), "casual", "warm", dict(rating="like")),
    ("Black tee", "tee", "black", "#1f1f22", "top", dict(sleeve="short"), dict(sleeve="short", neck="crew"), "casual", "warm", {}),
    ("Oatmeal henley", "tee", "cream", "#e3dccb", "top", dict(sleeve="long", front="half", buttons=3), dict(sleeve="long", neck="crew"), "casual", "cool",
     dict(location="drawer", spec=dict(texture="waffle", button_color="#8a7a63"), tags=dict(button_color="tan"))),
    ("Breton striped tee", "tee", "navy", stripes("#f1eee6", "#26324d", 0.05, 0.03), "top", dict(sleeve="long"), dict(sleeve="long", neck="crew"), "casual", "all",
     dict(pattern="stripe", rating="love", rating_reason="goes with everything", tags=dict(pattern_name="breton_stripe"))),
    ("Blue oxford shirt", "shirt", "light_blue", "#a9c3e0", "top", dict(neck="collar", front="buttons", hem="curved", cuffs="button", pockets="chest", buttons=7),
     dict(sleeve="long", neck="collar"), "smart_casual", "all", dict(rating="love", brand="Sample & Co", size="M", spec=dict(button_color="#f4f1ea"), tags=dict(fabric="oxford", collar="button_down"))),
    ("White dress shirt", "shirt", "white", "#f6f5f2", "top", dict(neck="collar", front="buttons", hem="curved", cuffs="button", fit="slim"),
     dict(sleeve="long", neck="collar", fit="slim"), "business", "all", {}),
    ("Chambray shirt", "shirt", "blue", "#6f8fb5", "top", dict(neck="collar", front="buttons", hem="curved", cuffs="button", pockets="chest-two"),
     dict(sleeve="long", neck="collar"), "casual", "all", dict(tags=dict(fabric="chambray"))),
    ("Navy polo", "polo", "navy", "#27344f", "top", dict(sleeve="short", neck="collar", front="half", buttons=2), dict(sleeve="short", neck="collar"), "smart_casual", "warm",
     dict(spec=dict(button_color="#f4f1ea"), tags=dict(fabric="pique"))),
    ("Burgundy cable sweater", "sweater", "burgundy", "#7a2f36", "top", dict(hem="rib", cuffs="rib"), dict(sleeve="long", neck="crew"), "smart_casual", "cool",
     dict(rating="like", spec=dict(texture="cable_knit"))),
    ("Striped sweater", "sweater", "navy", stripes("#26324d", "#e9e3d5", 0.07, 0.035), "top", dict(hem="rib", cuffs="rib"), dict(sleeve="long", neck="crew"), "casual", "cool",
     dict(pattern="stripe")),
    ("Cream v-neck sweater", "sweater", "cream", "#e8dfcb", "top", dict(neck="v", hem="rib", cuffs="rib"), dict(sleeve="long", neck="v"), "smart_casual", "cool", {}),
    ("Grey hoodie", "hoodie", "grey", "#8b8e92", "top", dict(neck="hood", hem="rib", cuffs="rib", fit="oversized", pockets="kangaroo"), dict(sleeve="long", neck="hood", fit="oversized"), "casual", "cool",
     dict(rating="meh", rating_reason="too boxy")),
    ("Navy bomber jacket", "jacket", "navy", "#2a3550", "top", dict(neck="crew", front="zip", hem="rib", cuffs="rib"), dict(sleeve="long"), "casual", "cool", {}),
    ("Tan chore jacket", "jacket", "tan", "#b89b6e", "top", dict(neck="collar", front="buttons", pockets="chest-low", fit="oversized"), dict(sleeve="long", neck="collar", fit="oversized"),
     "casual", "all", dict(rating="love")),
    ("Black overcoat", "coat", "black", "#232326", "top", dict(neck="collar", front="buttons", length="long", pockets="low"), dict(sleeve="long", neck="collar", top_length="long"),
     "business", "cool", dict(location="storage", tags=dict(collar="notch_lapel", fabric="melton", weight="super_heavy"))),
    ("Dark indigo jeans", "jeans", "navy", "#2c3a5a", "pants", dict(leg="tapered", jeans=True, stitch="contrast"), dict(leg="tapered", pant_length="full"), "casual", "all", dict(rating="love")),
    ("Black jeans", "jeans", "black", "#232327", "pants", dict(leg="straight", jeans=True), dict(leg="straight", pant_length="full"), "casual", "all", {}),
    ("Brown corduroy trousers", "trousers", "brown", "#8a5a33", "pants", dict(leg="straight"), dict(leg="straight", pant_length="full"), "smart_casual", "cool",
     dict(spec=dict(texture="corduroy"))),
    ("Grey wool trousers", "trousers", "grey", "#6f7278", "pants", dict(leg="tapered", length="ankle", pleats=1), dict(leg="tapered", pant_length="ankle"), "business", "cool", {}),
    ("Olive shorts", "shorts", "olive", "#6f7550", "pants", dict(length="short", waist="drawstring"), dict(pant_length="short"), "casual", "warm", dict(location="drawer")),
    ("Black high-tops", "sneakers", "black", "#222326", "sneaker", dict(height="high", style="high_top"), dict(shoe_height="high"), "casual", "all",
     dict(spec=dict(lace_color="#f4f1ea"))),
    ("Brown boots", "boots", "brown", "#6b4a32", "sneaker", dict(height="high", style="boot"), dict(shoe_height="high"), "smart_casual", "cool", dict(sole="#3a2c22")),
    ("Grey runners", "sneakers", "grey", "#a3a7ab", "sneaker", dict(style="runner"), dict(shoe_height="low"), "athletic", "all",
     dict(spec=dict(trim_color="#d9772b", lace_color="#f4f1ea"))),
]

# id in bench/hardcases/cases.json -> name, category, colour word, pattern, silhouette, formality, season, extras
PHOTOS = {
    "plaid-flannel": ("Plaid flannel shirt", "shirt", "green", "plaid", dict(sleeve="long", neck="collar"), "casual", "cool",
                      dict(rating="like", tags=dict(fabric="flannel", weight="heavyweight"))),
    "plaid-madras": ("Madras plaid shirt", "shirt", "multi", "plaid", dict(sleeve="long", neck="collar"), "casual", "warm",
                     dict(tags=dict(fabric="madras", pattern_name="madras_plaid", weight="lightweight"))),
    "marl-sweater": ("Marl turtleneck", "sweater", "grey", "solid", dict(sleeve="long", neck="turtle"), "casual", "cool",
                     dict(tags=dict(color_texture="marled"))),
    "graphic-tee": ("Paper plane tee", "tee", "white", "graphic", dict(sleeve="short", neck="crew"), "casual", "warm",
                    dict(rating="like", seen=["paper plane print on the chest"])),
    "jeans": ("Light wash jeans", "jeans", "blue", "solid", dict(leg="straight", pant_length="full"), "casual", "all", {}),
    "sneakers-pair": ("White canvas sneakers", "sneakers", "white", "solid", dict(shoe_height="low"), "casual", "all", dict(rating="love")),
    "sneaker-held": ("White leather sneakers", "sneakers", "white", "solid", dict(shoe_height="low"), "casual", "all", {}),
}

# name -> days ago it was worn, days ago it was last washed (None: never), whether it is in the laundry now.
# The demo closet turns these into dates when it is first opened, so the history is always recent.
HISTORY = {
    "Dark indigo jeans": ([1, 3, 5, 8, 10, 13], 14, False),
    "White tee": ([1, 6, 12], 7, True),
    "Blue oxford shirt": ([2, 9], 5, False),
    "Breton striped tee": ([3, 11], 12, True),
    "Grey hoodie": ([2, 7], 9, True),
    "White canvas sneakers": ([1, 2, 5, 8, 9, 12], None, False),
    "Navy polo": ([4], 6, False),
    "Burgundy cable sweater": ([6, 13], 20, False),
    "Brown boots": ([6, 13], None, False),
    "Chambray shirt": ([7], 10, False),
    "Black jeans": ([4, 11], 12, False),
    "Plaid flannel shirt": ([9], 15, False),
    "Light wash jeans": ([2], 3, False),
}


def _named(hex_color: str | None) -> str:
    """The colour word nearest a hex colour (buttons, trim, soles, laces); "same" when there is none."""
    if not hex_color:
        return "same"
    rgb = lambda h: tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))  # noqa: E731
    want = rgb(hex_color)
    return min(NAMED_HEX, key=lambda n: sum((a - b) ** 2 for a, b in zip(rgb(NAMED_HEX[n]), want, strict=True)))


POCKETS = {"chest": "chest_patch_single", "chest-two": "chest_patch_double", "kangaroo": "kangaroo", "chest-low": "three_patch_chore"}
TEXTURE = {"waffle": "waffle_thermal", "cable_knit": "cable", "corduroy": "corduroy", "rib_knit": "rib_2x2"}
PATTERN_NAME = {"stripe": "multi_stripe", "plaid": "tartan", "graphic": "novelty", "floral": "floral_large", "camo": "camo_woodland"}


def demo_answer(name: str, category: str, color: str, pattern: str, sil: dict, formality: str, season: str,
                template: str, params: dict, extra: dict) -> dict:
    """The tagging answer for a demo item, as Claude would give it, built from what this file knows about the item.

    Validated against the tagger's schema, so the demo closet's stored answers are always well formed.
    """
    spec = extra.get("spec", {})
    d: dict = dict(fabric=TEXTURE.get(spec.get("texture"), "unknown"),
                   pattern_name=PATTERN_NAME.get(pattern, "solid"),
                   pattern_orientation="horizontal" if pattern == "stripe" else ("placed" if pattern == "graphic" else "all_over"),
                   trim_color=_named(spec.get("trim_color")))
    if template == "top":
        neck = params.get("neck", sil.get("neck", "crew"))
        sleeve = params.get("sleeve", sil.get("sleeve", "long"))
        placket = {"buttons": "front_placket", "zip": "zip_full", "half": "polo" if category == "polo" else "henley"}.get(params.get("front"), "none")
        buttons = params.get("buttons", {"front_placket": {"coat": 3, "jacket": 5}.get(category, 7), "polo": 2, "henley": 3}.get(placket, 0))
        if category == "polo":
            neckline, collar = "polo_collar", "flat_knit"
        elif neck == "collar":
            neckline, collar = "na", "point"
        else:
            neckline = "henley" if placket == "henley" else {"v": "v_neck", "hood": "hood", "turtle": "turtleneck"}.get(neck, "crew")
            collar = "none"
        pockets = POCKETS.get(params.get("pockets"), "none")
        if params.get("pockets") == "low":
            pockets = "welt" if category == "coat" else "hip_patch_double"
        d.update(fit_detail=params.get("fit") or sil.get("fit") or "regular",
                 sleeve_length={"none": "sleeveless", "short": "short", "long": "long"}[sleeve],
                 neckline=neckline, collar=collar, placket=placket, placket_buttons=buttons if placket != "none" else 0,
                 button_color=_named(spec.get("button_color")) if buttons else "same",
                 cuff={"button": "barrel_1", "rib": "rib_knit"}.get(params.get("cuffs"), "open_hem" if sleeve == "short" else "none"),
                 sleeve_construction="set_in", pockets=pockets,
                 hem={"curved": "curved_shirt_tail", "rib": "ribbed_band"}.get(params.get("hem"), "straight"))
    elif template == "pants":
        jeans = bool(params.get("jeans")) or category == "jeans"
        d.update(waist=params.get("waist") or "belt_loops", pant_hem="plain",
                 pockets="five_pocket_jean" if jeans else "slash",
                 features=(["pleats"] if params.get("pleats") else []) + (["contrast_stitching"] if params.get("stitch") == "contrast" else []))
        if jeans:
            d.update(fabric="denim", fiber="cotton", weight="heavyweight")
    else:   # shoes
        style = params.get("style") or ("high_top" if sil.get("shoe_height") == "high" else "low_sneaker")
        d.update(shoe_style=style, sole_color=_named(extra.get("sole")) if extra.get("sole") else "white",
                 lace_color=_named(spec.get("lace_color")) if style != "boot" else "same")
        if "canvas" in name.lower():
            d.update(fabric="canvas", fiber="cotton")
        elif "leather" in name.lower() or category == "boots":
            d.update(fiber="leather")
    d.update(extra.get("tags", {}))
    d["other_features"] = list(extra.get("seen", []))
    tags = ItemTags(category=category, category_confidence=1.0, color=color, color_confidence=1.0, secondary_colors=[],
                    pattern=pattern, pattern_confidence=1.0, formality=formality, formality_confidence=1.0,
                    season=season, season_confidence=1.0, silhouette=Silhouette.of(**sil), silhouette_confidence=1.0,
                    details=Details.plain(**d), details_confidence=1.0, brand=extra.get("brand"), size=extra.get("size"),
                    material=None, needs_shot=None)
    return tags.model_dump(mode="json")


def answers(cases: dict) -> dict[str, dict]:
    """Every demo item's stored answer, by name."""
    out = {}
    for cid, (name, category, color, pattern, sil, formality, season, extra) in PHOTOS.items():
        case = cases[cid]
        out[name] = demo_answer(name, category, color, pattern, sil, formality, season, case["template"], case.get("params", {}), extra)
    for name, category, color, _paint, template, params, sil, formality, season, extra in DRAWN:
        out[name] = demo_answer(name, category, color, extra.get("pattern", "solid"), sil, formality, season, template, params, extra)
    return out


def add_history(items: list[dict]) -> None:
    for it in items:
        if it["name"] in HISTORY:
            worn, washed, laundry = HISTORY[it["name"]]
            it["history"] = dict(worn=worn, washed=washed, laundry=laundry)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models-dir", type=Path, default=ROOT / "bench" / "models")
    ap.add_argument("--answers-only", action="store_true", help="only rewrite the stored tagging answers in items.json")
    a = ap.parse_args()
    cases = {c["id"]: c for c in json.loads((ROOT / "bench" / "hardcases" / "cases.json").read_text())["cases"]}
    if a.answers_only:
        data = json.loads((OUT / "items.json").read_text(encoding="utf-8"))
        by_name = answers(cases)
        for it in data["items"]:
            it["answer"] = by_name[it["name"]]
        data["schema_version"] = SCHEMA_VERSION
        (OUT / "items.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"answers written for {len(data['items'])} items (schema version {SCHEMA_VERSION})")
        return
    if (OUT / "images").exists():
        shutil.rmtree(OUT / "images")
    (OUT / "images").mkdir(parents=True)
    items = []
    for cid, (name, category, color, pattern, sil, formality, season, extra) in PHOTOS.items():
        case = cases[cid]
        photo = C.load_photo(ROOT / "bench" / "hardcases" / "photos" / case["photo"], 1100)
        cut, _ = C.make_cutout(photo, C.predict_mask(photo, "isnet-general-use", a.models_dir))
        spec, info = build_spec(case, cut)
        item_id = iid(name)
        photo.save(OUT / "images" / f"{cid}.webp", "WEBP", quality=82, method=6)
        cut.save(OUT / "images" / f"{cid}.cut.webp", "WEBP", quality=80, method=6)
        items.append(dict(id=item_id, name=name, category=category, color=color, color_hex=info["base"], pattern=pattern,
                          silhouette=sil, formality=formality, season=season, location=extra.get("location", "closet"),
                          rating=extra.get("rating"), rating_reason=extra.get("rating_reason"),
                          illustration_svg=render(spec, STYLE, uid=item_id[:8]),
                          photo=dict(id=uuid.uuid5(NS, name + "/photo").hex, original=f"{cid}.webp", cutout=f"{cid}.cut.webp")))
    for name, category, color, paint, template, params, sil, formality, season, extra in DRAWN:
        fill = paint if isinstance(paint, Fill) else Fill("solid", paint)
        item_id = iid(name)
        items.append(dict(id=item_id, name=name, category=category, color=color, color_hex=fill.color,
                          pattern=extra.get("pattern", "solid"), silhouette=sil, formality=formality, season=season,
                          location=extra.get("location", "closet"), rating=extra.get("rating"),
                          rating_reason=extra.get("rating_reason"), brand=extra.get("brand"), size=extra.get("size"),
                          illustration_svg=render(Spec(template, params, fill, sole_color=extra.get("sole"), **extra.get("spec", {})), STYLE, uid=item_id[:8]),
                          photo=None))
    add_history(items)
    by_name = answers(cases)
    for it in items:
        it["answer"] = by_name[it["name"]]
    # interleave so the grid mixes photographed and drawn items
    items.sort(key=lambda it: it["id"])
    (OUT / "items.json").write_text(json.dumps({"style": STYLE, "schema_version": SCHEMA_VERSION, "items": items},
                                               ensure_ascii=False, indent=1), encoding="utf-8")
    # files for `closet selfcheck`
    C.load_photo(ROOT / "bench" / "hardcases" / "photos" / "jeans.jpg", 640).save(OUT / "selfcheck.webp", "WEBP", quality=80)
    shutil.copyfile(ROOT / "packaging" / "spike" / "fixtures" / "tiny.heic", OUT / "tiny.heic")
    credits = (ROOT / "bench" / "hardcases" / "ATTRIBUTION.md").read_text()
    (OUT / "CREDITS.md").write_text("Demo closet photos.\n\n" + credits.split("\n", 2)[2])
    total = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    print(f"{len(items)} items, {total // 1024} KB in {OUT}")


if __name__ == "__main__":
    main()
