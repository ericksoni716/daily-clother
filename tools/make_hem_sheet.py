"""Draw sheets of trouser hems on the figure's shoes (developer tool; not shipped).

    python tools/make_hem_sheet.py [OUT_DIR] [--png] [--name NAME]

For each shoe (a low sneaker, a dress shoe, a chukka, a six-inch work boot and a Chelsea boot), a sheet of a tee
and trousers in every leg shape (skinny, slim, straight, relaxed, wide, bootcut) at every length (a full break, a
slight break, no break, cropped): only the feet, at twice the figure's size, so where the hem sits on the shoe can
be checked. A second sheet per shoe shows the whole figure at phone size for the same outfits. Written as
`hems-<shoe>-<NAME>.svg` (and `.png` with --png) and `hems-<shoe>-phone-<NAME>.svg`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tools"))

from closet.drawing.figure import Piece, figure, plan
from make_figure_sheet import to_png
from make_shoe_sheet import answer

SHOES = {
    "low-sneaker": ("sneakers", dict(shoe_style="low_sneaker"), "#e8edf0"),
    "dress-shoe": ("dress_shoes", dict(shoe_style="derby"), "#5a3a22"),
    "chukka": ("boots", dict(shoe_style="boot", footwear="chukka"), "#a07850"),
    "work-boot": ("boots", dict(shoe_style="boot", footwear="service_boot", footwear_height="boot_6in"), "#6b4a32"),
    "chelsea": ("boots", dict(shoe_style="chelsea_boot"), "#2a2420"),
}
LEGS = ["skinny", "slim", "straight", "relaxed", "wide", "bootcut"]
LENGTHS = {"full break": "full", "slight break": "slight", "no break": "no_break", "cropped": "cropped"}
SCALE = 2
CELL_W, CELL_H = 130, 110   # the crop round both feet, in the figure's units


def outfit(shoe: str, leg: str, length: str) -> dict:
    category, details, colour = SHOES[shoe]
    brk = LENGTHS[length]
    trousers = Piece("trousers", answer("trousers", {"pant_length": "ankle" if brk == "cropped" else "full"},
                                        leg_shape=leg, trouser_break=brk), "#6f7278")
    return {"base": Piece("tee", answer("tee", {"sleeve": "short"}), "#f4f2ee"), "bottom": trousers,
            "shoes": Piece(category, answer(category, **details), colour)}


def cell(pieces: dict, uid: str, scale: float, whole: bool) -> tuple[str, float, float]:
    svg = figure(pieces, uid=uid)
    head, rest = svg.split(">", 1)
    if whole:
        x, y, w, h = (float(v) for v in head.split('viewBox="')[1].split('"')[0].split())
        box = f'viewBox="{x:.1f} {y:.1f} {w:.1f} {h:.1f}"'
    else:
        shoes = plan(pieces).get("shoes")
        _, ground = shoes.point(shoes.front.anchors["ground"])
        w, h = CELL_W, CELL_H
        box = f'viewBox="{200 - CELL_W / 2:.1f} {ground - CELL_H + 6:.1f} {CELL_W} {CELL_H}"'
    head = head.split("viewBox=")[0] + box + f' width="{w * scale:.0f}" height="{h * scale:.0f}"'
    return head + ">" + rest, w * scale, h * scale


def sheet(shoe: str, whole: bool) -> str:
    pad, label = 10, 22
    scale = 0.5 if whole else SCALE
    out, W, H = [], 0.0, 0.0
    for r, leg in enumerate(LEGS):
        for c, length in enumerate(LENGTHS):
            svg, w, h = cell(outfit(shoe, leg, length), f"h{r}{c}", scale, whole)
            x, y = c * (w + pad) + pad, r * (h + label + pad) + pad
            out.append(f'<text x="{x}" y="{y + 16}" font-family="sans-serif" font-size="14">{leg}, {length}</text>'
                       f'<g transform="translate({x} {y + label})"><rect width="{w:.0f}" height="{h:.0f}" '
                       f'fill="#fbfaf7" stroke="#ddd"/>{svg}</g>')
            W, H = max(W, x + w + pad), max(H, y + label + h + pad)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" width="{W:.0f}" height="{H:.0f}">'
            f'<rect width="{W:.0f}" height="{H:.0f}" fill="#fff"/>' + "".join(out) + "</svg>")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out", nargs="?", type=Path, default=ROOT / "docs" / "screenshots")
    ap.add_argument("--png", action="store_true")
    ap.add_argument("--name", default="after")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    for shoe in SHOES:
        for whole in (False, True):
            svg = sheet(shoe, whole)
            path = a.out / f"hems-{shoe}{'-phone' if whole else ''}-{a.name}.svg"
            path.write_text(svg, encoding="utf-8")
            print(f"wrote {path}")
            if a.png:
                W, H = (int(v) for v in svg.split('viewBox="0 0 ')[1].split('"')[0].split())
                to_png(path, path.with_suffix(".png"), (W, H))
                print(f"wrote {path.with_suffix('.png')}")


if __name__ == "__main__":
    main()
