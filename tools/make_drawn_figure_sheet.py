"""Shoes Claude drew, on the app's As worn figure (developer tool; not shipped): sheets to look at.

    python tools/make_drawn_figure_sheet.py [--out docs/screenshots]

For the saved example drawings (the runner, drawn left and right, from bench/experiments/shoe_drawn/EXAMPLES/; the
boot, its pull tab the one at the front, shown in front of the leg, from backend/closet/drawing/shoe_examples/; the dress
shoe and the boat shoe), today's figure beside the app's own drawing of the same outfit with the drawing kept on the
shoe, as `POST /api/outfits/figure` draws it (`illustrations.describe` gives the shoe its stored drawing; the figure
is `figure.figure`): under shorts with a crew sock, full-length trousers and ankle-length trousers, a crew sock under
both. Writes drawn-figure-closeup.png (the feet, large) and drawn-figure-phone.png (whole figures at about the size
the Today screen shows one), with the SVGs beside them. The PNGs need Chrome or Chromium on the PATH.

`sheets()` draws the same sheets for any drawings kept by the app (a developer can lay their own shoes' drawings on
the figure this way, outside the repository).
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tools"))

from make_figure_sheet import to_png  # noqa: E402

from closet.drawing import drawn  # noqa: E402
from closet.drawing.figure import Piece, figure, plan  # noqa: E402
from closet.tagger.schema import Details, ItemTags, Silhouette  # noqa: E402

BENCH = ROOT / "bench" / "experiments" / "shoe_drawn" / "EXAMPLES"
OUT = ROOT / "docs" / "screenshots"
CASES = [("shorts and a crew sock", "shorts"), ("full-length trousers", "full"), ("ankle-length trousers", "ankle")]


def answer(category: str, style: str, silhouette: dict | None = None, **details) -> dict:
    return ItemTags(
        category=category, category_confidence=0.9, color="navy", color_confidence=0.9, secondary_colors=[],
        pattern="solid", pattern_confidence=0.9, formality="casual", formality_confidence=0.9, season="all",
        season_confidence=0.9, silhouette=Silhouette.of(**(silhouette or {})), silhouette_confidence=0.9,
        details=Details.plain(**({"shoe_style": style} if style else {}), **details), details_confidence=0.9,
        brand=None, size=None, material=None, needs_shot=None).model_dump(mode="json")


def kept(left, right, opening: float, top: float, instep: float, height: str, tab: bool = False) -> dict:
    """A drawing as the app keeps it (version 2), with the sheet's heights the figure reads."""
    def shoe(s) -> dict:
        return drawn.side(s).to_json()
    return {"version": drawn.VERSION, "left": shoe(left), "right": shoe(right) if right else None,
            "sheet": {"silhouette": {"height": height}, "opening_front_y": opening, "top_y": top, "instep_y": instep,
                      "front_pull_tab": tab}}


@dataclass
class Shoe:
    """One shoe on the sheets: its name, today's drawing of it (category, style, colour, details) and the drawing kept."""
    name: str
    today: tuple[str, str, str, dict]
    drawing: dict


def examples() -> list[Shoe]:
    def bench(name: str) -> str:
        return (BENCH / name).read_text(encoding="utf-8")
    return [
        Shoe("runner", ("sneakers", "runner", "#f1f0eb", {}),
             kept(bench("runner-left.svg"), bench("runner-right.svg"), 24, 16, 22, "low")),
        Shoe("boot", ("boots", "chelsea_boot", "#6e5a3f", {}), kept(drawn.split_example("boot"), None, -32, -46, 84, "ankle", tab=True)),
        Shoe("dress shoe", ("dress_shoes", "oxford", "#b5622f", {"toe_cap": "stitched"}),
             kept(drawn.example("dress-shoe"), None, 32, 32, 30, "low")),
        Shoe("boat shoe", ("dress_shoes", "loafer", "#73523f", {}),
             kept(drawn.example("boat-shoe"), None, 79.3, 79.3, 77.3, "low_profile")),
    ]


def outfit(shoes: Piece, case: str) -> dict:
    tee = Piece("tee", answer("tee", "", {"sleeve": "short"}), "#f4f2ee")
    sock = Piece("other", answer("other", "", accessory="socks", accessory_kind="casual_crew"), "#2e7d4f")
    if case == "shorts":
        bottom = Piece("shorts", None, "#6f7550")
    else:
        bottom = Piece("trousers", answer("trousers", "", {"leg": "straight", "pant_length": case}), "#6f7278")
    return {"base": tee, "bottom": bottom, "shoes": shoes, "accessories": [sock]}


def view_box(svg: str) -> tuple[float, ...]:
    return tuple(float(v) for v in re.search(r'viewBox="([^"]+)"', svg).group(1).split())


def cell(svg: str, box, x: float, y: float, w: float, h: float) -> str:
    head, rest = svg.split(">", 1)
    head = head.split("viewBox=")[0] + (f'viewBox="{box[0]:.1f} {box[1]:.1f} {box[2]:.1f} {box[3]:.1f}" '
                                        f'x="{x}" y="{y}" width="{w}" height="{h}"')
    return head + ">" + rest


def text(x, y, s, size=15, anchor="middle", weight="normal") -> str:
    return (f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="sans-serif" font-size="{size}" '
            f'font-weight="{weight}" fill="#26231f">{s}</text>')


def sheets(shoes: list[Shoe], out: Path, stem: str = "drawn-figure") -> tuple[Path, Path]:
    """The close-up and phone sheets for `shoes`, written to `out` as <stem>-closeup.png and <stem>-phone.png."""
    out.mkdir(parents=True, exist_ok=True)
    figs: dict[tuple[str, str], list[tuple[str, str]]] = {}
    grounds = {}
    for j, shoe in enumerate(shoes):
        category, style, hex_, details = shoe.today
        today = Piece(category, answer(category, style, **details), hex_)
        mine = replace(today, drawn=shoe.drawing)
        drawn.stored(shoe.drawing)   # it must be drawable: the figure would quietly draw today's shoe otherwise
        for i, (_label, case) in enumerate(CASES):
            placed = plan(outfit(today, case)).get("shoes")
            grounds[shoe.name] = placed.box()[3] - 2
            figs[(shoe.name, case)] = [("today", figure(outfit(today, case), uid=f"t{j}{i}")),
                                       ("drawn", figure(outfit(mine, case), uid=f"n{j}{i}"))]

    # the feet, close up
    fw, fh, zoom = 140, 122, 2.2        # the feet's box in figure units, and how much larger it is drawn
    cw, ch = fw * zoom, fh * zoom
    lab, gap, head, sep = 190, 12, 70, 22
    width = lab + len(shoes) * (2 * (cw + gap) + sep)
    height = head + len(CASES) * (ch + gap)
    cells, x0 = [], lab
    for shoe in shoes:
        cells.append(text(x0 + (cw + gap), 26, shoe.name, 20, weight="bold"))
        box = (200 - fw / 2, grounds[shoe.name] - fh + 8, fw, fh)
        for i, (label, case) in enumerate(CASES):
            y = head + i * (ch + gap)
            if x0 == lab:
                cells.append(text(lab - 12, y + ch / 2, label, 15, anchor="end"))
            for n, (kind, svg) in enumerate(figs[(shoe.name, case)]):
                x = x0 + n * (cw + gap)
                if i == 0:
                    cells.append(text(x + cw / 2, 52, kind))
                cells.append(f'<rect x="{x}" y="{y}" width="{cw}" height="{ch}" fill="#f1eee8"/>')
                cells.append(cell(svg, box, x, y, cw, ch))
        x0 += 2 * (cw + gap) + sep
    closeup = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" width="{width:.0f}" '
               f'height="{height:.0f}"><rect width="{width:.0f}" height="{height:.0f}" fill="#ffffff"/>{"".join(cells)}</svg>')
    (out / f"{stem}-closeup.svg").write_text(closeup, encoding="utf-8")
    to_png(out / f"{stem}-closeup.svg", out / f"{stem}-closeup.png", (int(width), int(height)))

    # whole figures at phone size (about 0.8 px a unit, as the Today screen shows one): shorts above, trousers below
    pk = 0.8
    vb = view_box(figs[(shoes[0].name, "shorts")][0][1])
    pw, ph = vb[2] * pk, vb[3] * pk
    pcells, x0 = [], 10.0
    for shoe in shoes:
        pcells.append(text(x0 + (pw + 6), 18, shoe.name, 13, weight="bold"))
        for r, case in enumerate(("shorts", "full")):
            y = 30 + r * (ph + 30)
            for n, (kind, svg) in enumerate(figs[(shoe.name, case)]):
                x = x0 + n * (pw + 6)
                pcells.append(cell(svg, view_box(svg), x, y, pw, ph))
                if r == 1:
                    pcells.append(text(x + pw / 2, y + ph + 16, kind, 11))
        x0 += 2 * (pw + 6) + 24
    pwid, phei = x0, 30 + 2 * (ph + 30)
    phone = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {pwid:.0f} {phei:.0f}" width="{pwid:.0f}" '
             f'height="{phei:.0f}"><rect width="{pwid:.0f}" height="{phei:.0f}" fill="#fbfaf7"/>{"".join(pcells)}</svg>')
    (out / f"{stem}-phone.svg").write_text(phone, encoding="utf-8")
    to_png(out / f"{stem}-phone.svg", out / f"{stem}-phone.png", (int(pwid), int(phei)))
    return out / f"{stem}-closeup.png", out / f"{stem}-phone.png"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--keep-svg", action="store_true", help="keep the SVGs beside the PNGs")
    args = ap.parse_args()
    paths = sheets(examples(), args.out)
    if not args.keep_svg:
        for p in paths:
            p.with_suffix(".svg").unlink()
    print("wrote " + " and ".join(str(p) for p in paths))


if __name__ == "__main__":
    main()
