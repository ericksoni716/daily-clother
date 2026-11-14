"""Regenerate the demo closet's data (developer tool; not shipped).

    python tools/make_demo.py --models-dir <folder holding isnet-general-use.onnx>

Writes backend/closet/demo_data/: items.json, images/ and the two small files
the program's self-check uses. Seven items are open-licence photos run through
the real pipeline; the rest have no photo: the first ones (DRAWN) are drawn from
templates, the newer ones (TAGGED) from their tags alone, the way the app draws
an item, with their plaid or floral drawn from a pattern tile made here (no
photo, no network). Their kept pattern goes with them, as a measured one would.

The same run writes the demo's lived-in parts: the wear history and the worn
outfits, prices, two wishes with stand-in finds from shops (one has dropped in
price) and a saved trip. Running it twice changes no file.

Each item also gets a stored tagging answer built from what this file knows
about it, so the demo closet shows the same screens as a tagged closet without
ever being sent to Claude. After a change to the tagging schema, rewrite just
those answers (no model needed):

    python tools/make_demo.py --answers-only

Some items carry a price (PRICES) so Insights has a cost per wear to show;
after changing them, rewrite just the prices (no model needed):

    python tools/make_demo.py --prices-only
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))
sys.path.insert(0, str(ROOT / "backend"))

from PIL import Image, ImageDraw  # noqa: E402

from closet import palette  # noqa: E402
from closet.drawing import DRAWING_VERSION, fills, stored  # noqa: E402
from closet.drawing.illustrate import Fill, Spec, render  # noqa: E402
from closet.drawing.item import drawing_from_answer  # noqa: E402
from closet.tagger.schema import NAMED_HEX, SCHEMA_VERSION, Details, ItemTags, Silhouette  # noqa: E402
from closet.tagger.taxonomy import FOOTWEAR, nearest_shade  # noqa: E402
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
     dict(spec=dict(lace_color="#f4f1ea"), footwear="canvas_high_top")),
    ("Brown boots", "boots", "brown", "#6b4a32", "sneaker", dict(height="high", style="boot"), dict(shoe_height="high"), "smart_casual", "cool", dict(sole="#3a2c22", footwear="service_boot")),
    ("Grey runners", "sneakers", "grey", "#a3a7ab", "sneaker", dict(style="runner"), dict(shoe_height="low"), "athletic", "all",
     dict(spec=dict(trim_color="#d9772b", lace_color="#f4f1ea"), footwear="running_shoe")),
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


def _tile_size(image: Image.Image, scale: int) -> Image.Image:
    return image.resize((image.width // scale, image.height // scale), Image.LANCZOS)


def plaid_tile(sett: list[tuple[str, int]], size: int = 96) -> Image.Image:
    """A tartan woven from one sett (colour, threads) used for warp and weft, in a 2/2 twill, so it repeats."""
    threads = [h for h, n in sett for _ in range(n)]
    lane = [threads[i * len(threads) // size] for i in range(size)]
    rgb = {h: tuple(int(h[i:i + 2], 16) for i in (1, 3, 5)) for h in set(lane)}
    img = Image.new("RGB", (size, size))
    img.putdata([rgb[lane[x]] if (x + y) % 4 < 2 else rgb[lane[y]] for y in range(size) for x in range(size)])
    return img


def floral_tile(ground: str, petals: list[str], centre: str, leaf: str, size: int = 160) -> Image.Image:
    """A repeat of flowers (five petals round a centre, two leaves) on a plain ground, drawn large and made small
    so the edges are smooth, and wrapped at the sides so the tile repeats without a seam."""
    big = 4
    s = size * big
    img = Image.new("RGB", (s, s), ground)
    draw = ImageDraw.Draw(img)
    flowers = [(0.18, 0.22, 0), (0.62, 0.12, 1), (0.42, 0.55, 0), (0.86, 0.48, 1), (0.14, 0.82, 1), (0.70, 0.86, 0)]
    for fx, fy, colour in flowers:
        for dx in (-s, 0, s):
            for dy in (-s, 0, s):
                cx, cy, r = fx * s + dx, fy * s + dy, 0.075 * s
                for lx, ly in ((-1.3, 0.9), (1.2, 1.1)):
                    draw.ellipse((cx + lx * r - 0.8 * r, cy + ly * r - 0.35 * r, cx + lx * r + 0.8 * r, cy + ly * r + 0.35 * r),
                                 fill=leaf)
                for k in range(5):
                    a = math.radians(k * 72 - 90)
                    px, py = cx + math.cos(a) * r * 0.85, cy + math.sin(a) * r * 0.85
                    draw.ellipse((px - 0.62 * r, py - 0.62 * r, px + 0.62 * r, py + 0.62 * r), fill=petals[colour])
                draw.ellipse((cx - 0.38 * r, cy - 0.38 * r, cx + 0.38 * r, cy + 0.38 * r), fill=centre)
    return _tile_size(img, big)


def kept_tile(image: Image.Image, width_frac: float, pattern: str) -> dict:
    """A pattern tile kept as the app keeps a measured one (closet/drawing/stored.py), with its colours."""
    return palette.keep({"version": stored.VERSION, "kind": "tile", "image": stored.tile_text(image), "width_frac": width_frac,
                         "length_frac": None, "phase": None, "phase_right": None}, pattern)


def kept_stripes(fill: Fill, pattern: str = "stripe") -> dict:
    """A drawn item's stripes kept as the app keeps measured ones, so a redraw and the outfit figure keep them."""
    bands = [[h, w] for h, w in fill.stripes.bands]
    return palette.keep({"version": stored.VERSION, "kind": "stripes", "orientation": fill.stripes.orientation, "bands": bands,
                         "trim_bands": None, "sleeves_banded": None}, pattern)


TARTAN = [("#a3262a", 14), ("#1f2a44", 8), ("#a3262a", 3), ("#22422c", 8), ("#a3262a", 14), ("#d9b44a", 1)]
FLORAL = dict(ground="#1f2a44", petals=["#e3a6b4", "#ece4d0"], centre="#d9b44a", leaf="#3f7d4f")

# Items drawn from their tags alone, the way the app draws an item it has a description for: name, category, colour
# word, its hex, formality, season, silhouette, the description's details (Details), and extras (other colours seen,
# pattern and its tile, rating, location, brand). They show the kinds of clothing, shoes, accessories and details the
# app has learnt to draw since the first demo, in the owner's colour families.
TAGGED = [
    ("Forest fleece pullover", "sweater", "green", "#22422c", "casual", "cool", dict(sleeve="long", neck="collar"),
     dict(garment="fleece_pullover", fit_detail="relaxed", sleeve_length="long", collar="stand", placket="snap",
          placket_buttons=4, cuff="none", sleeve_construction="set_in", pockets="chest_flap_single", hem="straight",
          fabric="polar_fleece", fiber="polyester", weight="heavyweight", trim_color="orange", shade="forest_green"),
     dict(secondary=["navy"], rating="love", rating_reason="warm without bulk")),
    ("Khaki parka", "coat", "tan", "#c3b091", "casual", "cool", dict(sleeve="long", neck="hood", top_length="long"),
     dict(garment="parka", fit_detail="relaxed", sleeve_length="long", neckline="hood", placket="zip_full",
          cuff="rib_knit", sleeve_construction="set_in", pockets="hip_flap_double", hem="straight", fabric="twill",
          fiber="cotton", weight="super_heavy", shade="khaki"),
     {}),
    ("Floral camp shirt", "shirt", "navy", "#1f2a44", "casual", "warm", dict(sleeve="short", neck="collar"),
     dict(garment="camp_collar_shirt", fit_detail="relaxed", sleeve_length="short", collar="camp", placket="front_placket",
          placket_buttons=6, button_color="cream", cuff="open_hem", sleeve_construction="set_in", pockets="none",
          hem="straight", fabric="challis", fiber="viscose", weight="lightweight", pattern_name="floral_large", shade="navy"),
     dict(secondary=["pink", "cream"], pattern="floral", tile=(floral_tile(**FLORAL), 0.42), location="drawer")),
    ("Stone pleated chinos", "trousers", "tan", "#c9bfae", "smart_casual", "all", dict(leg="tapered", pant_length="full"),
     dict(garment="chinos", waist="belt_loops", pant_hem="turn_up", fabric="twill", fiber="cotton", weight="midweight",
          waistband="side_adjusters", fly="zip", trouser_front="single_pleat", rise="high", leg_shape="tapered",
          trouser_break="slight", hem_finish="turn_up", crease="pressed", features=["pleats", "pressed_crease"],
          trouser_pockets=["slant", "back_welt_double"], back_details=["darts"], shade="stone"),
     dict(rating="love", rating_reason="the pleats sit well")),
    ("Heather grey joggers", "trousers", "grey", "#a3a6a8", "athletic", "all", dict(leg="tapered", pant_length="full"),
     dict(garment="joggers", waist="drawstring", pant_hem="ribbed", fabric="french_terry", fiber="cotton",
          weight="midweight", color_texture="heathered", waistband="elastic_drawcord", fly="none", trouser_front="flat",
          rise="mid", leg_shape="tapered", hem_finish="ribbed_cuff", trouser_pockets=["slant"], shade="heather_grey"),
     dict(location="drawer")),
    ("Tartan lounge pants", "trousers", "red", "#a3262a", "casual", "cool", dict(leg="straight", pant_length="full"),
     dict(garment="lounge_pants", waist="drawstring", fabric="flannel", fiber="cotton", weight="midweight",
          waistband="elastic_drawcord", fly="none", trouser_front="flat", leg_shape="straight", hem_finish="plain",
          pattern_name="tartan", shade="red"),
     dict(secondary=["navy", "green"], pattern="plaid", tile=(plaid_tile(TARTAN), 0.3), location="drawer",
          rating="love", rating_reason="Sunday mornings")),
    ("Burgundy penny loafers", "dress_shoes", "burgundy", "#4e1a1d", "smart_casual", "all", dict(shoe_height="low"),
     dict(shoe_style="loafer", footwear="penny_loafer", toe_shape="round", toe_treatment="apron", lacing="slip_on",
          sole="leather", shoe_construction="blake", footwear_height="low", heel="low_stacked", upper_material="smooth_calf",
          fiber="leather", shade="oxblood"),
     dict(rating="love")),
    ("Black cap-toe oxfords", "dress_shoes", "black", "#1a1a1a", "business", "all", dict(shoe_height="low"),
     dict(shoe_style="oxford", footwear="cap_toe_oxford", toe_shape="almond", toe_treatment="cap_toe",
          lacing="closed_oxford", eyelets=5, laces="flat_waxed", lace_color="black", sole="leather",
          shoe_construction="goodyear_welt", footwear_height="low", heel="low_stacked", upper_material="smooth_calf",
          fiber="leather", shade="black"),
     {}),
    ("Tobacco suede derbies", "dress_shoes", "brown", "#7a5230", "smart_casual", "all", dict(shoe_height="low"),
     dict(shoe_style="derby", footwear="derby", toe_shape="round", toe_treatment="plain", lacing="open_derby", eyelets=5,
          laces="round_waxed", lace_color="brown", sole="crepe", sole_color="tan", shoe_construction="goodyear_welt",
          footwear_height="low", heel="flat", upper_material="suede", fiber="suede", shade="tobacco"),
     {}),
    ("Brown leather belt", "belt", "brown", "#6b4a32", "smart_casual", "all", {},
     dict(accessory="belt", accessory_kind="casual_leather", fiber="leather", shade="mid_brown"), {}),
    ("Olive canvas rucksack", "bag", "olive", "#5f6b3a", "casual", "all", {},
     dict(accessory="bag", accessory_kind="rucksack", fabric="canvas", fiber="cotton", shade="olive"), {}),
    ("Mustard beanie", "hat", "yellow", "#c9a227", "casual", "cool", {},
     dict(accessory="beanie", accessory_kind="beanie", fabric="rib_2x2", fiber="merino", shade="mustard"), {}),
    ("Rust wool scarf", "scarf", "orange", "#a4492a", "casual", "cool", {},
     dict(accessory="scarf", accessory_kind="woven_wool", fiber="lambswool", shade="rust"), dict(rating="like")),
]

# name -> days ago it was worn, days ago it was last washed (None: never), whether it is in the laundry now.
# The demo closet turns these into dates when it is first opened, so the history is always recent.
HISTORY = {
    "Dark indigo jeans": ([1, 3, 5, 10, 13], 14, False),
    "White tee": ([1, 5, 6, 12], 7, True),
    "Blue oxford shirt": ([2, 9, 10], 5, False),
    "Breton striped tee": ([3, 11], 12, True),
    "Grey hoodie": ([2, 7], 9, True),
    "White canvas sneakers": ([1, 2, 5, 9, 11, 12], None, False),
    "Navy polo": ([4], 6, False),
    "Burgundy cable sweater": ([6, 10, 13], 20, False),
    "Brown boots": ([6, 13, 15, 17, 20], None, False),
    "Chambray shirt": ([7], 10, False),
    "Black jeans": ([4, 11, 17], 12, False),
    "Plaid flannel shirt": ([9, 20], 15, False),
    "Light wash jeans": ([2, 12, 20], 3, False),
    "Brown corduroy trousers": ([6, 9], 10, False),
    "Tan chore jacket": ([6, 13, 15], None, False),
    "Oatmeal henley": ([13, 15], 14, False),
    "Black tee": ([7], 8, False),
    "White dress shirt": ([8], 2, False),
    "Cream v-neck sweater": ([8], None, False),
    "Grey wool trousers": ([8], None, False),
    "Navy bomber jacket": ([12], None, False),
    "Marl turtleneck": ([17], 18, False),
    "Grey runners": ([7, 16], None, False),
    "White leather sneakers": ([4], None, False),
    "Forest fleece pullover": ([5, 20], 25, False),
    "Khaki parka": ([10, 17], None, False),
    "Stone pleated chinos": ([15], None, False),
    "Heather grey joggers": ([7, 16], 10, True),
    "Tartan lounge pants": ([1, 2, 4, 5, 8, 9], 10, False),
    "Burgundy penny loafers": ([3], None, False),
    "Black cap-toe oxfords": ([8], None, False),
    "Tobacco suede derbies": ([10], None, False),
    "Brown leather belt": ([3, 6, 10], None, False),
    "Olive canvas rucksack": ([4, 15], None, False),
    "Mustard beanie": ([5, 17], None, False),
    "Rust wool scarf": ([10, 17], None, False),
}

# name -> what was paid, in cents (US dollars), so Insights has a cost per wear to show; the rest have no price.
PRICES = {
    "Dark indigo jeans": 9800,
    "White tee": 2500,
    "Blue oxford shirt": 6500,
    "White canvas sneakers": 5500,
    "Brown boots": 22000,
    "Burgundy cable sweater": 12000,
    "Navy polo": 4500,
    "Black jeans": 7900,
    "Light wash jeans": 6000,
    "Black overcoat": 35000,
    "Grey wool trousers": 14000,
    "Navy bomber jacket": 16000,
    "Grey runners": 11000,
    "Forest fleece pullover": 13900,
    "Khaki parka": 29000,
    "Floral camp shirt": 6800,
    "Stone pleated chinos": 9500,
    "Burgundy penny loafers": 18500,
    "Black cap-toe oxfords": 24000,
    "Tobacco suede derbies": 17000,
    "Brown leather belt": 6000,
    "Olive canvas rucksack": 8500,
}

# name -> the fields its made-in-advance answer is unsure of, and how sure (everything else is 1.0), so the
# review queue has something to show in the demo closet. The values themselves are the right ones.
UNSURE = {
    "Madras plaid shirt": dict(color=0.5, season=0.65),            # multi or blue; light cloth but long sleeves
    "Marl turtleneck": dict(color=0.55, silhouette=0.6),           # grey or tan marl; turtleneck or mock neck
    "White leather sneakers": dict(category=0.6, formality=0.6),   # held in a hand: sneakers or dress shoes
    "Tan chore jacket": dict(category=0.65),                       # a jacket or a short coat
    "Grey wool trousers": dict(formality=0.75),                    # business or smart casual
}

# Outfits worn on some of those days, by days ago: the pieces by place (names, accessories as a list), the day they
# were offered for, and how they went. Their pieces' wears are in HISTORY. The newest has no rating, so Today asks
# about it.
def _day(low: int, high: int, occasion: str = "casual", rain: bool = False) -> dict:
    return dict(low_c=low, high_c=high, rain=rain, occasion=occasion, mood=None)


OUTFITS = [
    dict(days_ago=1, pieces=dict(base="White tee", bottom="Dark indigo jeans", shoes="White canvas sneakers"),
         context=_day(9, 16), score=74, reasons=["A casual outfit for a mild day."], rating=None, rating_reasons=[]),
    dict(days_ago=2, pieces=dict(base="Blue oxford shirt", mid="Grey hoodie", bottom="Light wash jeans", shoes="White canvas sneakers"),
         context=_day(12, 18), score=68, reasons=["Two layers for a mild day."], rating="fine", rating_reasons=["too_warm"]),
    dict(days_ago=3, pieces=dict(base="Breton striped tee", bottom="Dark indigo jeans", shoes="Burgundy penny loafers",
                                 accessories=["Brown leather belt"]),
         context=_day(12, 17, "smart_casual"), score=77, reasons=["Stripes with plain pieces.", "Loafers dress up the jeans."],
         rating="loved", rating_reasons=["compliments"]),
    dict(days_ago=4, pieces=dict(base="Navy polo", bottom="Black jeans", shoes="White leather sneakers",
                                 accessories=["Olive canvas rucksack"]),
         context=_day(13, 19), score=70, reasons=["A casual outfit for a mild day."], rating="fine", rating_reasons=[]),
    dict(days_ago=5, pieces=dict(base="White tee", mid="Forest fleece pullover", bottom="Dark indigo jeans",
                                 shoes="White canvas sneakers", accessories=["Mustard beanie"]),
         context=_day(3, 9), score=76, reasons=["A warm fleece for a cold day.", "Neutrals with one colour."],
         rating="loved", rating_reasons=[]),
    dict(days_ago=6, pieces=dict(base="White tee", mid="Burgundy cable sweater", outer="Tan chore jacket",
                                 bottom="Brown corduroy trousers", shoes="Brown boots", accessories=["Brown leather belt"]),
         context=_day(4, 10, "smart_casual"), score=81,
         reasons=["Three layers for a cold day.", "Warm browns with a burgundy sweater."], rating="loved", rating_reasons=["compliments"]),
    dict(days_ago=7, pieces=dict(base="Black tee", mid="Grey hoodie", bottom="Heather grey joggers", shoes="Grey runners"),
         context=_day(6, 12, "athletic"), score=72, reasons=["Easy to move in."], rating="fine", rating_reasons=["too_cold"]),
    dict(days_ago=8, pieces=dict(base="White dress shirt", mid="Cream v-neck sweater", bottom="Grey wool trousers",
                                 shoes="Black cap-toe oxfords"),
         context=_day(7, 12, "business"), score=80, reasons=["Dressed for business.", "Quiet colours that go together."],
         rating="loved", rating_reasons=[]),
    dict(days_ago=9, pieces=dict(base="Plaid flannel shirt", bottom="Brown corduroy trousers", shoes="White canvas sneakers"),
         context=_day(8, 13), score=63, reasons=["A flannel shirt for a cool day."], rating="not_again", rating_reasons=["too_cold"]),
    dict(days_ago=10, pieces=dict(base="Blue oxford shirt", mid="Burgundy cable sweater", outer="Khaki parka",
                                  bottom="Dark indigo jeans", shoes="Tobacco suede derbies",
                                  accessories=["Rust wool scarf", "Brown leather belt"]),
         context=_day(0, 5, "smart_casual"), score=78, reasons=["Three layers and a scarf for a cold day."],
         rating="loved", rating_reasons=[]),
    dict(days_ago=11, pieces=dict(base="Breton striped tee", bottom="Black jeans", shoes="White canvas sneakers"),
         context=_day(11, 16), score=69, reasons=["A casual outfit for a mild day."], rating="fine", rating_reasons=[]),
    dict(days_ago=12, pieces=dict(base="White tee", outer="Navy bomber jacket", bottom="Light wash jeans",
                                  shoes="White canvas sneakers"),
         context=_day(9, 15), score=66, reasons=["A light jacket for a mild day."], rating="not_again",
         rating_reasons=["too_casual"]),
    dict(days_ago=13, pieces=dict(base="Oatmeal henley", mid="Burgundy cable sweater", outer="Tan chore jacket",
                                  bottom="Dark indigo jeans", shoes="Brown boots"),
         context=_day(2, 9), score=79, reasons=["Three layers for a cold day."], rating="loved", rating_reasons=[]),
    dict(days_ago=15, pieces=dict(base="Oatmeal henley", outer="Tan chore jacket", bottom="Stone pleated chinos",
                                  shoes="Brown boots", accessories=["Olive canvas rucksack"]),
         context=_day(8, 14), score=75, reasons=["Earth colours that go together."], rating="loved", rating_reasons=[]),
    dict(days_ago=17, pieces=dict(base="Marl turtleneck", outer="Khaki parka", bottom="Black jeans", shoes="Brown boots",
                                  accessories=["Mustard beanie", "Rust wool scarf"]),
         context=_day(-1, 4), score=73, reasons=["A parka, a hat and a scarf for a freezing day."], rating="fine",
         rating_reasons=["too_warm"]),
    dict(days_ago=20, pieces=dict(base="Plaid flannel shirt", mid="Forest fleece pullover", bottom="Light wash jeans",
                                  shoes="Brown boots"),
         context=_day(5, 10), score=71, reasons=["A flannel shirt under a fleece for a cool day."], rating="loved",
         rating_reasons=[]),
]

# Wishes added by hand, with what a search of shops might have found for them (stand-ins: the shops and their
# pages are made up and nothing is ever fetched). Each find's prices are given oldest first, by days ago; a find
# whose last price is lower shows the drop. The pieces are in the closet's words, as "Would this work?" reads them.
WISHES = [
    dict(name="Tan suede chukka boots", note="For weekends in the cold months.", price_max=220.0, days_ago=16,
         finds=[
             dict(name="Sand suede chukka boot", shop="Example Bootmaker", slug="sand-suede-chukka",
                  prices=[(9, 210.0), (5, 210.0), (1, 179.0)],
                  piece=dict(category="boots", color="tan", formality="smart_casual", season="all", pattern="solid",
                             material="suede")),
             dict(name="Tobacco suede desert boot", shop="Example Outfitters", slug="tobacco-desert-boot",
                  prices=[(9, 165.0), (5, 165.0), (1, 165.0)],
                  piece=dict(category="boots", color="brown", formality="casual", season="all", pattern="solid",
                             material="suede")),
         ]),
    dict(name="Navy merino crewneck", note="", price_max=150.0, days_ago=11,
         finds=[
             dict(name="Navy merino crew sweater", shop="Example Knitwear", slug="navy-merino-crew",
                  prices=[(6, 120.0), (1, 96.0)],
                  piece=dict(category="sweater", color="navy", formality="smart_casual", season="cool", pattern="solid",
                             weight_class="midweight", material="merino wool")),
             dict(name="Midnight lambswool crewneck", shop="Example Outfitters", slug="midnight-lambswool-crew",
                  prices=[(6, 135.0), (1, 135.0)],
                  piece=dict(category="sweater", color="navy", formality="smart_casual", season="cool", pattern="solid",
                             weight_class="heavyweight", material="lambswool")),
         ]),
]
STAND_IN_SHOP = "https://shop.example/demo/"

# A saved trip, given in days from today and planned from the weather given here (never looked up), with the
# basics already ticked as packed.
TRIP = dict(place=dict(name="Lisbon, Portugal", latitude=38.7167, longitude=-9.1333, timezone="Europe/Lisbon"),
            starts_in=12, occasion="casual", day_occasions={2: "smart_casual"}, laundry=None,
            weather=[(12, 19, False), (13, 18, True), (13, 20, False), (14, 21, False), (12, 19, False)],
            tick="basic:")


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
                template: str, params: dict, extra: dict, hex_: str | None = None) -> dict:
    """The tagging answer for a demo item, as Claude would give it, built from what this file knows about the item.

    Validated against the tagger's schema, so the demo closet's stored answers are always well formed.
    """
    spec = extra.get("spec", {})
    d: dict = dict(fabric=TEXTURE.get(spec.get("texture"), "unknown"),
                   pattern_name=PATTERN_NAME.get(pattern, "solid"),
                   pattern_orientation="horizontal" if pattern == "stripe" else ("placed" if pattern == "graphic" else "all_over"),
                   trim_color=_named(spec.get("trim_color")),
                   shade=(nearest_shade(hex_, color) if hex_ else None) or "unknown")
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
        d.update(waistband="drawstring" if params.get("waist") == "drawstring" else "belt_loops",
                 fly="none" if params.get("waist") == "drawstring" else "zip",
                 trouser_front={0: "flat", 1: "single_pleat", 2: "double_pleat"}[params.get("pleats", 0)],
                 crease="pressed" if params.get("pleats") else "none", hem_finish="plain",
                 leg_shape=params.get("leg", "straight") if category != "shorts" else "na",
                 trouser_pockets=["scoop", "coin", "back_patch"] if jeans else ["slant", "back_welt_single"])
        if jeans:
            d.update(fabric="denim", fiber="cotton", weight="heavyweight",
                     denim_wash={"navy": "dark", "black": "black", "blue": "mid", "light_blue": "light"}.get(color, "mid"))
    else:   # shoes
        style = params.get("style") or ("high_top" if sil.get("shoe_height") == "high" else "low_sneaker")
        d.update(shoe_style=style, sole_color=_named(extra.get("sole")) if extra.get("sole") else "white",
                 lace_color=_named(spec.get("lace_color")) if style != "boot" else "same")
        d["footwear"] = next((w for w in extra.get("seen", []) if w in FOOTWEAR), None) or extra.get("footwear", "unknown")
        if "canvas" in name.lower():
            d.update(fabric="canvas", fiber="cotton")
        elif "leather" in name.lower() or category == "boots":
            d.update(fiber="leather")
    d.update(extra.get("tags", {}))
    d["other_features"] = list(extra.get("seen", []))
    sure = lambda field: UNSURE.get(name, {}).get(field, 1.0)  # noqa: E731
    tags = ItemTags(category=category, category_confidence=sure("category"), color=color, color_confidence=sure("color"),
                    secondary_colors=[], pattern=pattern, pattern_confidence=sure("pattern"), formality=formality,
                    formality_confidence=sure("formality"), season=season, season_confidence=sure("season"),
                    silhouette=Silhouette.of(**sil), silhouette_confidence=sure("silhouette"),
                    details=Details.plain(**d), details_confidence=1.0, brand=extra.get("brand"), size=extra.get("size"),
                    material=None, needs_shot=None)
    return tags.model_dump(mode="json")


def tagged_answer(name: str, category: str, color: str, formality: str, season: str, sil: dict, details: dict,
                  extra: dict) -> dict:
    """The tagging answer for an item drawn from its tags: its details are given in full, as Claude would give them."""
    sure = lambda field: UNSURE.get(name, {}).get(field, 1.0)  # noqa: E731
    tags = ItemTags(category=category, category_confidence=sure("category"), color=color, color_confidence=sure("color"),
                    secondary_colors=extra.get("secondary", []), pattern=extra.get("pattern", "solid"),
                    pattern_confidence=sure("pattern"), formality=formality, formality_confidence=sure("formality"),
                    season=season, season_confidence=sure("season"), silhouette=Silhouette.of(**sil),
                    silhouette_confidence=sure("silhouette"), details=Details.plain(**details), details_confidence=1.0,
                    brand=extra.get("brand"), size=extra.get("size"), material=None, needs_shot=None)
    return tags.model_dump(mode="json")


def tagged_item(entry: tuple) -> dict:
    """An item drawn from its tags: its fields, its kept pattern (if any) and its drawing, made as the app makes them.
    `wave` 2 marks the items a demo closet made before them is given once (closet/demo.py)."""
    name, category, color, hex_, formality, season, sil, details, extra = entry
    item_id = iid(name)
    answer = tagged_answer(name, category, color, formality, season, sil, details, extra)
    kept = kept_tile(extra["tile"][0], extra["tile"][1], extra["pattern"]) if "tile" in extra else None
    fill = stored.fill_from(kept, hex_) if kept else None
    drawing = drawing_from_answer(answer, hex_, uid=item_id[:8], fill=fill)
    assert drawing.svg, f"{name} could not be drawn"
    return dict(id=item_id, wave=2, name=name, category=category, color=color, color_hex=hex_, pattern=extra.get("pattern", "solid"),
                silhouette=sil, formality=formality, season=season, location=extra.get("location", "closet"),
                rating=extra.get("rating"), rating_reason=extra.get("rating_reason"), brand=extra.get("brand"),
                size=extra.get("size"), illustration_svg=drawing.svg,
                illustration_notes=list(drawing.not_drawn) or None, pattern_fill=kept, photo=None, answer=answer)


def answers(cases: dict) -> dict[str, dict]:
    """Every demo item's stored answer, by name."""
    out = {}
    for entry in TAGGED:
        out[entry[0]] = tagged_answer(entry[0], entry[1], entry[2], entry[4], entry[5], entry[6], entry[7], entry[8])
    for cid, (name, category, color, pattern, sil, formality, season, extra) in PHOTOS.items():
        case = cases[cid]
        out[name] = demo_answer(name, category, color, pattern, sil, formality, season, case["template"], case.get("params", {}), extra)
    for name, category, color, paint, template, params, sil, formality, season, extra in DRAWN:
        out[name] = demo_answer(name, category, color, extra.get("pattern", "solid"), sil, formality, season, template, params, extra,
                                paint if isinstance(paint, str) else None)   # a patterned one has no one shade
    return out


def add_history(items: list[dict]) -> None:
    for it in items:
        if it["name"] in HISTORY:
            worn, washed, laundry = HISTORY[it["name"]]
            it["history"] = dict(worn=worn, washed=washed, laundry=laundry)


def add_prices(items: list[dict]) -> None:
    for it in items:
        if it["name"] in PRICES:
            answer = it.pop("answer", None)   # keep the answer last, as a full run writes it
            it["price_cents"] = PRICES[it["name"]]
            if answer is not None:
                it["answer"] = answer


def worn_outfits() -> list[dict]:
    """OUTFITS as items.json keeps them: pieces by item id, every place given."""
    out = []
    for o in OUTFITS:
        for name in [n for pl, n in o["pieces"].items() if pl != "accessories"] + o["pieces"].get("accessories", []):
            assert o["days_ago"] in HISTORY[name][0], f"{name} is not worn {o['days_ago']} days ago in HISTORY"
        pieces = {pl: iid(o["pieces"][pl]) if o["pieces"].get(pl) else None for pl in ("base", "mid", "outer", "bottom", "shoes")}
        out.append(dict(id=uuid.uuid5(NS, f"outfit/{o['days_ago']}").hex, days_ago=o["days_ago"], recorded_by="today",
                        pieces={**pieces, "accessories": [iid(n) for n in o["pieces"].get("accessories", [])]}, context=o["context"], score=o["score"], reasons=o["reasons"],
                        warnings=[], rating=o["rating"], rating_reasons=o["rating_reasons"], rating_note=None))
    return out


def wishes() -> list[dict]:
    """WISHES as items.json keeps them, with ids that stay the same from run to run."""
    out = []
    for w in WISHES:
        finds = [dict(id=uuid.uuid5(NS, f"find/{f['slug']}").hex, name=f["name"], shop=f["shop"], url=STAND_IN_SHOP + f["slug"],
                      piece=f["piece"], prices=[dict(days_ago=d, price=p) for d, p in f["prices"]]) for f in w["finds"]]
        out.append(dict(id=uuid.uuid5(NS, f"wish/{w['name']}").hex, name=w["name"], note=w["note"], price_max=w["price_max"],
                        currency="USD", days_ago=w["days_ago"], finds=finds))
    return out


def trip() -> dict:
    """TRIP as items.json keeps it."""
    return dict(id=uuid.uuid5(NS, "trip/" + TRIP["place"]["name"]).hex, place=TRIP["place"], starts_in=TRIP["starts_in"],
                occasion=TRIP["occasion"], day_occasions={str(k): v for k, v in TRIP["day_occasions"].items()},
                laundry=TRIP["laundry"], weather=[dict(low_c=lo, high_c=hi, rain=r) for lo, hi, r in TRIP["weather"]],
                tick=TRIP["tick"])


def lived_in() -> dict:
    """What items.json keeps besides the items: the worn outfits, the wishes and the saved trip."""
    return {"outfits": worn_outfits(), "wishes": wishes(), "trip": trip()}


def add_verdicts() -> None:
    """Check each wish's finds against the demo closet with "Would this work?", as a search does, and keep the
    verdicts in items.json (the demo closet would take several seconds to work them out when first opened). The
    demo closet is made in a folder of its own for this, with a fixed today, so the verdicts are the same every run."""
    import datetime
    import tempfile

    from closet import db, demo, shop, today, wears
    from closet.config import Config
    data = json.loads((OUT / "items.json").read_text(encoding="utf-8"))
    real_today = wears.today
    wears.today = lambda: datetime.date(2026, 11, 1)
    try:
        with tempfile.TemporaryDirectory() as folder:
            cfg = Config(data_dir=Path(folder))
            demo.ensure(cfg)
            conn = db.connect(cfg.db_path("demo"))
            try:
                rows = today.closet_rows(conn)
                worn = [{"item_id": r["item_id"], "worn_on": r["worn_on"]}
                        for r in conn.execute("SELECT item_id, worn_on FROM wears ORDER BY item_id, worn_on")]
                kept = {r["id"]: json.loads(r["piece"]) for r in conn.execute("SELECT id, piece FROM finds")}
            finally:
                conn.close()
    finally:
        wears.today = real_today
    finds = [f for w in data["wishes"] for f in w["finds"]]
    for f, v in zip(finds, shop.judge(rows, worn, [kept[f["id"]] for f in finds]), strict=True):
        f["verdict"] = {k: v[k] for k in ("verdict", "verdict_words", "reasons")}
    (OUT / "items.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models-dir", type=Path, default=ROOT / "bench" / "models")
    ap.add_argument("--answers-only", action="store_true", help="only rewrite the stored tagging answers in items.json")
    ap.add_argument("--prices-only", action="store_true", help="only rewrite the prices in items.json")
    ap.add_argument("--history-only", action="store_true", help="only rewrite the wear history and worn outfits in items.json")
    a = ap.parse_args()
    cases = {c["id"]: c for c in json.loads((ROOT / "bench" / "hardcases" / "cases.json").read_text())["cases"]}
    if a.prices_only:
        data = json.loads((OUT / "items.json").read_text(encoding="utf-8"))
        for it in data["items"]:
            it.pop("price_cents", None)
        add_prices(data["items"])
        (OUT / "items.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"prices written for {sum('price_cents' in it for it in data['items'])} items")
        return
    if a.answers_only or a.history_only:
        data = json.loads((OUT / "items.json").read_text(encoding="utf-8"))
        if a.answers_only:
            by_name = answers(cases)
            for it in data["items"]:
                it["answer"] = by_name[it["name"]]
        if a.history_only:
            for it in data["items"]:
                it.pop("history", None)
            add_history(data["items"])
            for it in data["items"]:   # keep the key order a full run writes
                it["answer"] = it.pop("answer")
        data = {"style": data["style"], "schema_version": SCHEMA_VERSION, "drawing_version": data.get("drawing_version", DRAWING_VERSION),
                "items": data["items"],   # as a full run writes it (the drawings are not touched)
                **(lived_in() if a.history_only else {k: data[k] for k in ("outfits", "wishes", "trip") if k in data})}
        (OUT / "items.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        if a.history_only:
            add_verdicts()
        print(f"{'answers' if a.answers_only else 'history'} written for {len(data['items'])} items (schema version {SCHEMA_VERSION})")
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
                          **({"pattern_fill": kept_stripes(fill, extra["pattern"])} if fill.stripes else {}),
                          photo=None))
    items += [tagged_item(entry) for entry in TAGGED]
    add_history(items)
    add_prices(items)
    by_name = answers(cases)
    for it in items:
        it["answer"] = by_name[it["name"]]
    assert set(HISTORY) | set(PRICES) | set(UNSURE) <= {it["name"] for it in items}
    # interleave so the grid mixes photographed and drawn items
    items.sort(key=lambda it: it["id"])
    (OUT / "items.json").write_text(json.dumps({"style": STYLE, "schema_version": SCHEMA_VERSION, "drawing_version": DRAWING_VERSION, "items": items,
                                                **lived_in()},
                                               ensure_ascii=False, indent=1), encoding="utf-8")
    add_verdicts()
    # files for `closet selfcheck`
    C.load_photo(ROOT / "bench" / "hardcases" / "photos" / "jeans.jpg", 640).save(OUT / "selfcheck.webp", "WEBP", quality=80)
    shutil.copyfile(ROOT / "packaging" / "spike" / "fixtures" / "tiny.heic", OUT / "tiny.heic")
    credits = (ROOT / "bench" / "hardcases" / "ATTRIBUTION.md").read_text()
    (OUT / "CREDITS.md").write_text("Demo closet photos.\n\n" + credits.split("\n", 2)[2])
    total = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    print(f"{len(items)} items, {total // 1024} KB in {OUT}")


if __name__ == "__main__":
    main()
