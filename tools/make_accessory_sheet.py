"""Draw a sheet of the accessories (developer tool; not shipped).

    python tools/make_accessory_sheet.py [OUT.svg] [--png OUT.png]

Every kind of accessory the taxonomy names (bags, belts, hats, scarves, ties, pocket squares, gloves, glasses,
watches, socks), drawn alone the way an item's page draws it, then a few outfits worn with accessories, the way
`POST /api/outfits/figure` draws them. With `--worn OUT.png` the outfits alone are also written as a picture. With `--png` the sheet is also turned into a picture by a Chrome or
Chromium found on this computer.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tools"))

from make_figure_sheet import demo_rows, to_png  # noqa: E402

from closet.drawing import item  # noqa: E402
from closet.drawing.figure import Piece, figure  # noqa: E402
from closet.illustrations import describe  # noqa: E402
from closet.tagger import taxonomy  # noqa: E402
from closet.tagger.schema import Details, ItemTags, Silhouette  # noqa: E402

OUT = ROOT / "docs" / "screenshots" / "accessories.svg"

# a colour for each accessory garment, so the sheet reads like real things
COLORS = {"cap": "#2a3550", "beanie": "#8a2f2a", "brimmed_hat": "#6b5a45", "belt": "#5a3a22", "scarf": "#b8332e",
          "bag": "#7a6a4a", "tie": "#27344f", "pocket_square": "#e8e2d6", "gloves": "#3a2a20", "eyewear": "#222222",
          "watch": "#9aa0a6", "socks": "#3b4a3a"}
HATS = {k: g for g, kinds in (("cap", ("baseball_cap_structured", "dad_cap", "five_panel", "trucker_cap")),
                              ("beanie", ("beanie", "fisherman_beanie", "beret", "trapper")))
        for k in kinds}

# a tailored jacket, which the demo closet does not have, to wear a pocket square in
BLAZER = dict(category="jacket", color="#3a3f4a",
              details=dict(garment="sport_coat", collar="notch_lapel", placket="front_placket", pockets="hip_flap_double"))

# caption, then the demo items by name (or a dict as BLAZER) for each place, then the accessories as (garment id,
# kind) or (garment id, kind, the tagger's pattern name)
OUTFITS = [
    ("Cold: overcoat, knit scarf, beanie, rucksack",
     dict(base="Blue oxford shirt", mid="Burgundy cable sweater", outer="Black overcoat",
          bottom="Brown corduroy trousers", shoes="Brown boots"),
     [("scarf", "long_knit"), ("beanie", "beanie"), ("bag", "rucksack")]),
    ("Mild: shirt, dress belt, fedora, briefcase",
     dict(base="White dress shirt", bottom="Grey wool trousers", shoes="White leather sneakers"),
     [("belt", "dress_belt"), ("brimmed_hat", "fedora"), ("bag", "briefcase")]),
    ("Hot: tee, web belt, cap, tote",
     dict(base="White tee", bottom="Olive shorts", shoes="White canvas sneakers"),
     [("belt", "canvas_web"), ("cap", "dad_cap"), ("bag", "tote")]),
    ("Office: dress shirt, repp tie, belt, watch, glasses",
     dict(base="White dress shirt", bottom="Stone pleated chinos", shoes="Black cap-toe oxfords"),
     [("belt", "dress_belt"), ("tie", "silk_woven", "university_stripe"), ("watch", "dress"), ("eyewear", "browline")]),
    ("Tailored: blazer, knit tie, puff pocket square",
     dict(base="Blue oxford shirt", outer=BLAZER, bottom="Grey wool trousers", shoes="Burgundy penny loafers"),
     [("tie", "knit"), ("pocket_square", "puff"), ("socks", "dress_mid_calf", "argyle")]),
    ("Weekend: tee, shorts, crew socks, watch, sunglasses",
     dict(base="White tee", bottom="Olive shorts", shoes="White canvas sneakers"),
     [("socks", "casual_crew", "rugby_hoops"), ("watch", "dive"), ("eyewear", "wayfarer")]),
]
SECOND = "cream"   # a patterned accessory's second colour

CELL, CAPTION, COLUMNS = 150, 34, 8
FIG_W, FIG_H = 300, 470
FIGURES_ACROSS = 3


def category(accessory: str) -> str:
    return taxonomy.ACCESSORY_GARMENTS[accessory]


def answer(accessory: str, kind: str, pattern: str | None = None) -> dict:
    return tags(category(accessory), dict(accessory=accessory, accessory_kind=kind),
                dict(pattern_name=pattern) if pattern else {}, [SECOND] if pattern else [])


def tags(cat: str, details: dict, more: dict | None = None, second: list | None = None) -> dict:
    return ItemTags(
        category=cat, category_confidence=0.9, color="navy", color_confidence=0.9,
        secondary_colors=second or [], pattern="solid", pattern_confidence=0.9, formality="casual", formality_confidence=0.9,
        season="all", season_confidence=0.9, silhouette=Silhouette.of(), silhouette_confidence=0.9,
        details=Details.plain(**details, **(more or {})), details_confidence=0.9, brand=None,
        size=None, material=None, needs_shot=None).model_dump(mode="json")


def garment(kind: str, group: str) -> str:
    if group == "hats":
        return HATS.get(kind, "brimmed_hat")
    return next(g for g, grp in taxonomy.ACCESSORY_GROUP.items() if grp == group)


def singles() -> list[tuple[str, str]]:
    out = []
    for group in ("hats", "belts", "scarves", "bags", "ties", "pocket_square_folds", "gloves", "eyewear_frames",
                  "watches", "socks"):
        for kind in taxonomy.ACCESSORIES[group]:
            g = garment(kind, group)
            out.append((kind.replace("_", " "), (g, kind)))
    return [(caption, item.svg_from_answer(answer(g, kind), COLORS[g], uid=f"s{n}") or "")
            for n, (caption, (g, kind)) in enumerate(out)]


def figures() -> list[tuple[str, str]]:
    rows = demo_rows()
    out = []
    for n, (caption, names, worn) in enumerate(OUTFITS):
        pieces: dict = {place: describe(rows[name]) if isinstance(name, str) else
                        Piece(name["category"], tags(name["category"], name["details"]), name["color"])
                        for place, name in names.items()}
        pieces["accessories"] = [Piece(category(a[0]), answer(*a), COLORS[a[0]]) for a in worn]
        out.append((caption, figure(pieces, uid="g" + chr(ord("a") + n))))
    return out


def _place(svg: str, x: float, y: float, w: float, h: float) -> str:
    return re.sub(r'width="[\d.]+" height="[\d.]+"', f'x="{x}" y="{y}" width="{w}" height="{h}"', svg, count=1)


def _caption(text: str, x: float, y: float, size: int) -> str:
    return (f'<text x="{x}" y="{y}" text-anchor="middle" font-family="sans-serif" font-size="{size}" '
            f'fill="#26231f">{text}</text>')


def sheet(small: list[tuple[str, str]], large: list[tuple[str, str]]) -> str:
    rows = (len(small) + COLUMNS - 1) // COLUMNS
    w = COLUMNS * CELL
    top = rows * (CELL + CAPTION)
    across = min(len(large), FIGURES_ACROSS) or 1
    h = top + (len(large) + across - 1) // across * (FIG_H + 40)
    cells = []
    for i, (caption, svg) in enumerate(small):
        x, y = (i % COLUMNS) * CELL, (i // COLUMNS) * (CELL + CAPTION)
        cells.append(_place(svg, x + 8, y + 6, CELL - 16, CELL - 6) + _caption(caption, x + CELL / 2, y + CELL + 20, 13))
    gap = (w - across * FIG_W) / (across + 1)
    for i, (caption, svg) in enumerate(large):
        x, y = gap + (i % across) * (FIG_W + gap), top + (i // across) * (FIG_H + 40)
        cells.append(_place(svg, x + 10, y + 6, FIG_W - 20, FIG_H - 6) + _caption(caption, x + FIG_W / 2,
                                                                                  y + FIG_H + 22, 15))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'<rect width="{w}" height="{h}" fill="#ffffff"/>{"".join(cells)}</svg>')


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out", nargs="?", type=Path, default=OUT)
    ap.add_argument("--png", type=Path, help="also write the sheet as a PNG picture")
    ap.add_argument("--worn", type=Path, help="also write the outfits alone as a PNG picture")
    args = ap.parse_args()
    large = figures()
    svg = sheet(singles(), large)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(svg, encoding="utf-8")
    print(f"wrote {args.out}")
    if args.png:
        w, h = (int(v) for v in re.search(r'width="(\d+)" height="(\d+)"', svg).groups())
        to_png(args.out, args.png, (w, h))
        print(f"wrote {args.png}")
    if args.worn:
        worn = sheet([], large)
        tmp = args.worn.with_suffix(".svg")
        tmp.write_text(worn, encoding="utf-8")
        w, h = (int(v) for v in re.search(r'width="(\d+)" height="(\d+)"', worn).groups())
        to_png(tmp, args.worn, (w, h))
        tmp.unlink()
        print(f"wrote {args.worn}")


if __name__ == "__main__":
    main()
