"""Regenerate the demo closet's data (developer tool; not shipped).

    python tools/make_demo.py --models-dir <folder holding isnet-general-use.onnx>

Writes backend/closet/demo_data/: items.json, images/ and the two small files
the program's self-check uses. About a quarter of the items are open-licence
photos run through the real pipeline; the rest are drawn from templates only.
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

from closet_bench import cutout as C  # noqa: E402
from closet_bench import fills  # noqa: E402
from closet_bench.hardcases import build_spec  # noqa: E402
from closet_bench.illustrate import Fill, Spec, render  # noqa: E402

OUT = ROOT / "backend" / "closet" / "demo_data"
STYLE = "flat"
NS = uuid.UUID("6f1d3c1e-7b1a-4c58-9d55-000000c105e7")


def iid(name: str) -> str:
    return uuid.uuid5(NS, name).hex


def stripes(a: str, b: str, wa: float = 0.045, wb: float = 0.045) -> Fill:
    return Fill("stripes", a, stripes=fills.Stripes("horizontal", [(a, wa), (b, wb)]))


# name, category, colour word, hex or Fill, template, params, silhouette, formality, season, extras
DRAWN = [
    ("White tee", "tee", "white", "#f4f2ee", "top", dict(sleeve="short"), dict(sleeve="short", neck="crew"), "casual", "warm", dict(rating="like")),
    ("Black tee", "tee", "black", "#1f1f22", "top", dict(sleeve="short"), dict(sleeve="short", neck="crew"), "casual", "warm", {}),
    ("Grey tee", "tee", "grey", "#9a9da1", "top", dict(sleeve="short"), dict(sleeve="short", neck="crew"), "casual", "warm", dict(location="drawer")),
    ("Breton striped tee", "tee", "navy", stripes("#f1eee6", "#26324d", 0.05, 0.03), "top", dict(sleeve="long"), dict(sleeve="long", neck="crew"), "casual", "all",
     dict(pattern="stripe", rating="love", rating_reason="goes with everything")),
    ("Blue oxford shirt", "shirt", "light_blue", "#a9c3e0", "top", dict(neck="collar", front="buttons", hem="curved", cuffs="button", pockets="chest"),
     dict(sleeve="long", neck="collar"), "smart_casual", "all", dict(rating="love", brand="Sample & Co", size="M")),
    ("White dress shirt", "shirt", "white", "#f6f5f2", "top", dict(neck="collar", front="buttons", hem="curved", cuffs="button", fit="slim"),
     dict(sleeve="long", neck="collar", fit="slim"), "business", "all", {}),
    ("Chambray shirt", "shirt", "blue", "#6f8fb5", "top", dict(neck="collar", front="buttons", hem="curved", cuffs="button", pockets="chest-low"),
     dict(sleeve="long", neck="collar"), "casual", "all", {}),
    ("Navy polo", "polo", "navy", "#27344f", "top", dict(sleeve="short", neck="collar", front="half"), dict(sleeve="short", neck="collar"), "smart_casual", "warm", {}),
    ("Burgundy crew sweater", "sweater", "burgundy", "#7a2f36", "top", dict(hem="rib", cuffs="rib"), dict(sleeve="long", neck="crew"), "smart_casual", "cool", dict(rating="like")),
    ("Striped sweater", "sweater", "navy", stripes("#26324d", "#e9e3d5", 0.07, 0.035), "top", dict(hem="rib", cuffs="rib"), dict(sleeve="long", neck="crew"), "casual", "cool",
     dict(pattern="stripe")),
    ("Cream v-neck sweater", "sweater", "cream", "#e8dfcb", "top", dict(neck="v", hem="rib", cuffs="rib"), dict(sleeve="long", neck="v"), "smart_casual", "cool", {}),
    ("Grey hoodie", "hoodie", "grey", "#8b8e92", "top", dict(neck="hood", hem="rib", cuffs="rib", fit="oversized"), dict(sleeve="long", neck="hood", fit="oversized"), "casual", "cool",
     dict(rating="meh", rating_reason="too boxy")),
    ("Navy bomber jacket", "jacket", "navy", "#2a3550", "top", dict(neck="crew", front="zip", hem="rib", cuffs="rib"), dict(sleeve="long"), "casual", "cool", {}),
    ("Tan chore jacket", "jacket", "tan", "#b89b6e", "top", dict(neck="collar", front="buttons", pockets="chest-low", fit="oversized"), dict(sleeve="long", neck="collar", fit="oversized"),
     "casual", "all", dict(rating="love")),
    ("Black overcoat", "coat", "black", "#232326", "top", dict(neck="collar", front="buttons", length="long", pockets="low"), dict(sleeve="long", neck="collar", top_length="long"),
     "business", "cool", dict(location="storage")),
    ("Dark indigo jeans", "jeans", "navy", "#2c3a5a", "pants", dict(leg="tapered", jeans=True), dict(leg="tapered", pant_length="full"), "casual", "all", dict(rating="love")),
    ("Black jeans", "jeans", "black", "#232327", "pants", dict(leg="straight", jeans=True), dict(leg="straight", pant_length="full"), "casual", "all", {}),
    ("Khaki chinos", "trousers", "tan", "#bca982", "pants", dict(leg="straight"), dict(leg="straight", pant_length="full"), "smart_casual", "all", {}),
    ("Grey wool trousers", "trousers", "grey", "#6f7278", "pants", dict(leg="tapered", length="ankle"), dict(leg="tapered", pant_length="ankle"), "business", "cool", {}),
    ("Olive shorts", "shorts", "olive", "#6f7550", "pants", dict(length="short"), dict(pant_length="short"), "casual", "warm", dict(location="drawer")),
    ("Black high-tops", "sneakers", "black", "#222326", "sneaker", dict(height="high"), dict(shoe_height="high"), "casual", "all", {}),
    ("Brown boots", "boots", "brown", "#6b4a32", "sneaker", dict(height="high", sole="chunky"), dict(shoe_height="high"), "smart_casual", "cool", dict(sole="#3a2c22")),
    ("Grey runners", "sneakers", "grey", "#a3a7ab", "sneaker", dict(sole="chunky"), dict(shoe_height="low"), "athletic", "all", {}),
]

# id in bench/hardcases/cases.json -> name, category, colour word, pattern, silhouette, formality, season, extras
PHOTOS = {
    "plaid-flannel": ("Plaid flannel shirt", "shirt", "green", "plaid", dict(sleeve="long", neck="collar"), "casual", "cool", dict(rating="like")),
    "plaid-madras": ("Madras plaid shirt", "shirt", "multi", "plaid", dict(sleeve="long", neck="collar"), "casual", "warm", {}),
    "marl-sweater": ("Marl turtleneck", "sweater", "grey", "solid", dict(sleeve="long", neck="turtle"), "casual", "cool", {}),
    "graphic-tee": ("Paper plane tee", "tee", "white", "graphic", dict(sleeve="short", neck="crew"), "casual", "warm", dict(rating="like")),
    "jeans": ("Light wash jeans", "jeans", "blue", "solid", dict(leg="straight", pant_length="full"), "casual", "all", {}),
    "sneakers-pair": ("White canvas sneakers", "sneakers", "white", "solid", dict(shoe_height="low"), "casual", "all", dict(rating="love")),
    "sneaker-held": ("White leather sneakers", "sneakers", "white", "solid", dict(shoe_height="low"), "casual", "all", {}),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models-dir", type=Path, default=ROOT / "bench" / "models")
    a = ap.parse_args()
    if (OUT / "images").exists():
        shutil.rmtree(OUT / "images")
    (OUT / "images").mkdir(parents=True)
    items = []
    cases = {c["id"]: c for c in json.loads((ROOT / "bench" / "hardcases" / "cases.json").read_text())["cases"]}
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
                          illustration_svg=render(Spec(template, params, fill, sole_color=extra.get("sole")), STYLE, uid=item_id[:8]),
                          photo=None))
    # interleave so the grid mixes photographed and drawn items
    items.sort(key=lambda it: it["id"])
    (OUT / "items.json").write_text(json.dumps({"style": STYLE, "items": items}, ensure_ascii=False, indent=1), encoding="utf-8")
    # files for `closet selfcheck`
    C.load_photo(ROOT / "bench" / "hardcases" / "photos" / "jeans.jpg", 640).save(OUT / "selfcheck.webp", "WEBP", quality=80)
    shutil.copyfile(ROOT / "packaging" / "spike" / "fixtures" / "tiny.heic", OUT / "tiny.heic")
    credits = (ROOT / "bench" / "hardcases" / "ATTRIBUTION.md").read_text()
    (OUT / "CREDITS.md").write_text("Demo closet photos.\n\n" + credits.split("\n", 2)[2])
    total = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    print(f"{len(items)} items, {total // 1024} KB in {OUT}")


if __name__ == "__main__":
    main()
