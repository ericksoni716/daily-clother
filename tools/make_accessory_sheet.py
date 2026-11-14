"""Draw a sheet of the accessories (developer tool; not shipped).

    python tools/make_accessory_sheet.py [OUT.svg] [--png OUT.png]

Every kind of bag, belt, hat and scarf the taxonomy names, drawn alone the way an item's page draws it, then the
accessories that have no shape of their own yet (a plain tag stands in), then a few outfits worn with accessories,
the way `POST /api/outfits/figure` draws them. With `--png` the sheet is also turned into a picture by a Chrome or
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

# caption, then the demo items by name for each place, then the accessories as (garment id, kind)
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
]

CELL, CAPTION, COLUMNS = 150, 34, 8
FIG_W, FIG_H = 300, 470


def category(accessory: str) -> str:
    return taxonomy.ACCESSORY_GARMENTS[accessory]


def answer(accessory: str, kind: str) -> dict:
    return ItemTags(
        category=category(accessory), category_confidence=0.9, color="navy", color_confidence=0.9,
        secondary_colors=[], pattern="solid", pattern_confidence=0.9, formality="casual", formality_confidence=0.9,
        season="all", season_confidence=0.9, silhouette=Silhouette.of(), silhouette_confidence=0.9,
        details=Details.plain(accessory=accessory, accessory_kind=kind), details_confidence=0.9, brand=None,
        size=None, material=None, needs_shot=None).model_dump(mode="json")


def garment(kind: str, group: str) -> str:
    if group == "hats":
        return HATS.get(kind, "brimmed_hat")
    return next(g for g, grp in taxonomy.ACCESSORY_GROUP.items() if grp == group)


def singles() -> list[tuple[str, str]]:
    out = []
    for group in ("hats", "belts", "scarves", "bags"):
        for kind in taxonomy.ACCESSORIES[group]:
            g = garment(kind, group)
            out.append((kind.replace("_", " "), (g, kind)))
    for g in ("tie", "pocket_square", "gloves", "eyewear", "watch", "socks"):
        out.append((g.replace("_", " ") + " (tag)", (g, taxonomy.ACCESSORIES[taxonomy.ACCESSORY_GROUP[g]][0])))
    return [(caption, item.svg_from_answer(answer(g, kind), COLORS[g], uid=f"s{n}") or "")
            for n, (caption, (g, kind)) in enumerate(out)]


def figures() -> list[tuple[str, str]]:
    rows = demo_rows()
    out = []
    for n, (caption, names, worn) in enumerate(OUTFITS):
        pieces: dict = {place: describe(rows[name]) for place, name in names.items()}
        pieces["accessories"] = [Piece(category(g), answer(g, kind), COLORS[g]) for g, kind in worn]
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
    h = top + FIG_H + 40
    cells = []
    for i, (caption, svg) in enumerate(small):
        x, y = (i % COLUMNS) * CELL, (i // COLUMNS) * (CELL + CAPTION)
        cells.append(_place(svg, x + 8, y + 6, CELL - 16, CELL - 6) + _caption(caption, x + CELL / 2, y + CELL + 20, 13))
    gap = (w - len(large) * FIG_W) / (len(large) + 1)
    for i, (caption, svg) in enumerate(large):
        x = gap + i * (FIG_W + gap)
        cells.append(_place(svg, x + 10, top + 6, FIG_W - 20, FIG_H - 6) + _caption(caption, x + FIG_W / 2,
                                                                                    top + FIG_H + 22, 15))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'<rect width="{w}" height="{h}" fill="#ffffff"/>{"".join(cells)}</svg>')


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out", nargs="?", type=Path, default=OUT)
    ap.add_argument("--png", type=Path, help="also write the sheet as a PNG picture")
    args = ap.parse_args()
    svg = sheet(singles(), figures())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(svg, encoding="utf-8")
    print(f"wrote {args.out}")
    if args.png:
        w, h = (int(v) for v in re.search(r'width="(\d+)" height="(\d+)"', svg).groups())
        to_png(args.out, args.png, (w, h))
        print(f"wrote {args.png}")


if __name__ == "__main__":
    main()
