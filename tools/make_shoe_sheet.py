"""Draw a sheet of the low shoes on the figure's feet, close up (developer tool; not shipped).

    python tools/make_shoe_sheet.py [OUT.svg] [--png OUT.png]

Each low style (low sneaker, runner, slip-on, loafer, derby, oxford, sandal) on the figure, worn with a bare
ankle, a no-show sock and a crew sock under shorts, then with trousers stopping short of the shoe and with
trousers resting on it: only the feet, at three times the figure's size, so the depth of the ankle in the shoe
can be checked (the back of the collar behind the ankle, the sides round it, the front over it).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tools"))

from closet.drawing.figure import Piece, figure, plan
from closet.tagger.schema import Details, ItemTags, Silhouette
from make_figure_sheet import to_png

STYLES = [("sneakers", "low_sneaker", "#e8edf0"), ("sneakers", "runner", "#3a4a6a"), ("sneakers", "slip_on", "#2a2a2e"),
          ("dress_shoes", "loafer", "#5a3a22"), ("dress_shoes", "derby", "#6b4a32"), ("dress_shoes", "oxford", "#1f1f22"),
          ("sandals", "sandal", "#a87a4f")]
CASES = ["bare ankle", "no-show sock", "crew sock", "trousers short of it", "trousers on it"]
SCALE = 3
CELL_W, CELL_H = 130, 95   # the crop round both feet, in the figure's units


def answer(category: str, silhouette: dict | None = None, **details) -> dict:
    return ItemTags(
        category=category, category_confidence=0.9, color="navy", color_confidence=0.9, secondary_colors=[],
        pattern="solid", pattern_confidence=0.9, formality="casual", formality_confidence=0.9, season="all",
        season_confidence=0.9, silhouette=Silhouette.of(**(silhouette or {})), silhouette_confidence=0.9,
        details=Details.plain(**details), details_confidence=0.9, brand=None, size=None, material=None,
        needs_shot=None).model_dump(mode="json")


def outfit(category: str, style: str, colour: str, case: str) -> dict:
    shoes = Piece(category, answer(category, shoe_style=style), colour)
    sock = {"no-show sock": "no_show", "crew sock": "casual_crew"}.get(case)
    bottom = (Piece("shorts", None, "#6f7550") if case in CASES[:3] else
              Piece("trousers", answer("trousers", {"leg": "tapered", "pant_length": "ankle" if "short" in case else "full"}), "#6f7278"))
    accessories = [Piece("other", answer("other", accessory="socks", accessory_kind=sock), "#2e7d4f")] if sock else []
    return {"base": Piece("tee", answer("tee", {"sleeve": "short"}), "#f4f2ee"), "bottom": bottom, "shoes": shoes,
                "accessories": accessories}


def cell(pieces: dict, uid: str) -> str:
    """The figure's feet: the figure's own drawing, with its view box moved to the shoes."""
    shoes = plan(pieces).get("shoes")
    _, ground = shoes.point(shoes.front.anchors["ground"])
    svg = figure(pieces, uid=uid)
    head, rest = svg.split(">", 1)
    box = f'viewBox="{200 - CELL_W / 2:.1f} {ground - CELL_H + 6:.1f} {CELL_W} {CELL_H}"'
    head = head.split("viewBox=")[0] + box + f' width="{CELL_W * SCALE}" height="{CELL_H * SCALE}"'
    return head + ">" + rest


def sheet() -> str:
    pad, label = 10, 26
    w, h = CELL_W * SCALE + pad, CELL_H * SCALE + label + pad
    out = []
    for r, (category, style, colour) in enumerate(STYLES):
        for c, case in enumerate(CASES):
            x, y = c * w + pad, r * h + pad
            out.append(f'<text x="{x}" y="{y + 18}" font-family="sans-serif" font-size="16">{style}: {case}</text>'
                       f'<g transform="translate({x} {y + label})"><rect width="{CELL_W * SCALE}" height="{CELL_H * SCALE}" '
                       f'fill="#fbfaf7" stroke="#ddd"/>{cell(outfit(category, style, colour, case), f"s{r}{c}")}</g>')
    W, H = len(CASES) * w + pad, len(STYLES) * h + pad
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">'
            f'<rect width="{W}" height="{H}" fill="#fff"/>' + "".join(out) + "</svg>")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out", nargs="?", type=Path, default=ROOT / "docs" / "screenshots" / "shoes-worn.svg")
    ap.add_argument("--png", type=Path)
    a = ap.parse_args()
    svg = sheet()
    a.out.write_text(svg, encoding="utf-8")
    print(f"wrote {a.out}")
    if a.png:
        W, H = (int(v) for v in svg.split('viewBox="0 0 ')[1].split('"')[0].split())
        to_png(a.out, a.png, (W, H))
        print(f"wrote {a.png}")


if __name__ == "__main__":
    main()
