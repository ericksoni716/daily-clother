"""Phone-sized pictures of outfits as worn, in the light and the dark theme (developer tool; not shipped).

    python tools/make_figure_shots.py NAME [--out DIR]
    python tools/make_figure_shots.py NAME --shoes [--out DIR]

Draws five outfits with `closet.drawing.figure` (from the demo closet's items, plus a pair of sandals the demo
closet does not have, and its corduroy trousers drawn with a relaxed leg) and puts each one in a page laid out like the Today card on a 390 x 844 phone, in the light
and the dark theme, then takes a picture of the page with a Chrome or Chromium found on this computer. The
pictures are written as DIR/figure-<outfit>-<light|dark>-NAME.png (DIR is docs/screenshots by default), so the
same outfits can be compared before and after a change to the figure.

With `--shoes` it draws instead every shoe on the coverage sheets' shoe groups (`make_coverage_sheet.py`) as the
figure wears it, seen from the front, one pair to a cell, in one picture: DIR/figure-shoes-front-NAME.png.
"""
from __future__ import annotations

import argparse
import base64
import copy
import dataclasses
import html
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tools"))

from make_coverage_sheet import CASES, answer  # noqa: E402
from make_figure_sheet import demo_rows, to_png  # noqa: E402

from closet.drawing.figure import Piece, figure  # noqa: E402
from closet.drawing.frontshoe import front_shoe  # noqa: E402
from closet.drawing.illustrate import Fill, Spec  # noqa: E402
from closet.drawing.templates import build  # noqa: E402
from closet.illustrations import describe  # noqa: E402
from closet.tagger.schema import Details, ItemTags, Silhouette, drawing_for  # noqa: E402

OUT = ROOT / "docs" / "screenshots"
PHONE = (390, 844)

# the page around the figure: the app's colours (frontend/src/styles.css) for each theme
THEMES = {
    "light": dict(bg="#f6f2ea", surface="#fffdf9", ink="#26231f", muted="#6b655b", card="#f1eee8", edge="#e4ded3"),
    "dark": dict(bg="#1b1916", surface="#24211d", ink="#eeeae3", muted="#aaa397", card="#f1eee8", edge="#cfc8bb"),
}


def sandals() -> Piece:
    """Tan two-strap sandals: the demo closet has none."""
    tags = ItemTags(category="sandals", category_confidence=0.9, color="tan", color_confidence=0.9, secondary_colors=[],
                    pattern="solid", pattern_confidence=0.9, formality="casual", formality_confidence=0.9,
                    season="warm", season_confidence=0.9, silhouette=Silhouette.of(), silhouette_confidence=0.9,
                    details=Details.plain(shoe_style="sandal", other_features=["sandal"]), details_confidence=0.9,
                    brand=None, size=None, material=None, needs_shot=None)
    return Piece("sandals", tags.model_dump(mode="json"), "#a87a4f", "tan")


def relaxed(piece: Piece) -> Piece:
    """The trousers with a relaxed leg, as if the tagger had said so: the demo closet has none."""
    answer = copy.deepcopy(piece.answer)
    answer["details"]["leg_shape"] = "relaxed"
    return dataclasses.replace(piece, answer=answer)


# file name, caption, then the demo items by name for each place
OUTFITS = [
    ("open-shirt", "Open chambray shirt over a henley, jeans, sneakers",
     dict(base="Oatmeal henley", mid="Chambray shirt", bottom="Dark indigo jeans", shoes="White leather sneakers")),
    ("tucked-shirt", "Shirt tucked in with a belt, chinos, loafers",
     dict(base="Blue oxford shirt", bottom="Stone pleated chinos", shoes="Burgundy penny loafers",
          accessories=["Brown leather belt"])),
    ("shorts-sandals", "Tee, shorts and sandals", dict(base="White tee", bottom="Olive shorts", shoes=None)),
    ("coat-boots", "Overcoat over a sweater and shirt, boots",
     dict(base="Blue oxford shirt", mid="Burgundy cable sweater", outer="Black overcoat", bottom="Grey wool trousers",
          shoes="Brown boots")),
    ("hoodie-relaxed", "Oversized hoodie, relaxed trousers, sneakers",
     dict(base="Grey hoodie", bottom="Brown corduroy trousers", shoes="Grey runners")),
]
RELAXED = {"Brown corduroy trousers"}


def pieces_for(names: dict) -> dict:
    rows = demo_rows()
    out = {}
    for place, name in names.items():
        if place == "accessories":
            out[place] = [describe(rows[n]) for n in name]
        else:
            out[place] = describe(rows[name]) if name else sandals()
            if name in RELAXED:
                out[place] = relaxed(out[place])
    return out


def page(svg: str, caption: str, theme: str) -> str:
    c = THEMES[theme]
    src = "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
body {{ margin: 0; background: {c['bg']}; color: {c['ink']}; font: 15px/1.4 system-ui, sans-serif; }}
main {{ padding: 16px; }}
h1 {{ font-size: 20px; margin: 4px 0 12px; }}
.card {{ background: {c['surface']}; border-radius: 16px; padding: 12px; }}
p {{ margin: 0 0 10px; color: {c['muted']}; }}
figure {{ margin: 0; display: grid; place-items: center; border-radius: 12px; background: {c['card']};
         box-shadow: inset 0 0 0 1px {c['edge']}; }}
img {{ display: block; width: 100%; height: auto; max-height: min(62vh, 560px); object-fit: contain; }}
</style></head><body><main><h1>Today</h1><div class="card"><p>{html.escape(caption)}</p>
<figure><img src="{src}" alt=""></figure></div></main></body></html>"""


def shoot(markup: str, png: Path) -> None:
    chrome = next((shutil.which(c) for c in ("google-chrome", "chromium", "chromium-browser", "chrome") if shutil.which(c)), None)
    if not chrome:
        raise SystemExit("this needs Chrome or Chromium on the PATH")
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "page.html"
        f.write_text(markup, encoding="utf-8")
        subprocess.run([chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                        f"--window-size={PHONE[0]},{PHONE[1]}", f"--screenshot={png.resolve()}", f.as_uri()],
                       check=True, capture_output=True)


SHOE_GROUPS = ("shoes", "shoes-uppers", "shoes-laces", "shoes-soles", "shoes-kinds")


def shoe_sheet() -> str:
    """Every shoe on the coverage sheets, seen from the front as the figure draws it: a pair to a cell."""
    cases = [c for g in SHOE_GROUPS for c in CASES[g]]
    px, cw, ch, cols = 5.0, 230, 250, 6
    rows = (len(cases) + cols - 1) // cols
    cells = []
    for i, (caption, category, color, details, sil) in enumerate(cases):
        x, y = (i % cols) * cw, (i // cols) * ch
        template, params, extras, _ = drawing_for(ItemTags.model_validate(answer(category, details, sil)))
        spec = Spec(template, params, Fill("solid", color), **extras)
        shoe = front_shoe(spec, px, sole_default=build(template, params).sole_default, uid=f"f{i}")
        x0, y0, x1, y1 = shoe.bbox
        gx, gy = x + cw / 2 - 52, y + ch - 42
        pair = (f'<g transform="translate({gx:.1f} {gy:.1f})">{shoe.body}</g>'
                f'<g transform="translate({gx + 104:.1f} {gy:.1f}) scale(-1 1)">{shoe.body}</g>')
        cells.append(f'<rect x="{x + 4}" y="{y + 4}" width="{cw - 8}" height="{ch - 8}" rx="12" fill="#f1eee8"/>'
                     f'<defs>{shoe.defs}</defs>{pair}'
                     f'<text x="{x + cw / 2}" y="{y + ch - 14}" text-anchor="middle" font-family="sans-serif" '
                     f'font-size="13" fill="#26231f">{html.escape(caption)}</text>')
    w, h = cols * cw, rows * ch
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'<rect width="{w}" height="{h}" fill="#ffffff"/>{"".join(cells)}</svg>')


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("name", help="the end of each file name, such as before or after")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--shoes", action="store_true", help="draw the coverage sheets' shoes from the front instead")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.shoes:
        svg = shoe_sheet()
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "shoes.svg"
            f.write_text(svg, encoding="utf-8")
            png = args.out / f"figure-shoes-front-{args.name}.png"
            w, h = (int(v) for v in re.search(r'width="(\d+)" height="(\d+)"', svg).groups())
            to_png(f, png, (w, h))
        print(f"wrote {png}")
        return
    for key, caption, names in OUTFITS:
        svg = figure(pieces_for(names), uid="s" + key[:2])
        for theme in THEMES:
            png = args.out / f"figure-{key}-{theme}-{args.name}.png"
            shoot(page(svg, caption, theme), png)
            print(f"wrote {png}")


if __name__ == "__main__":
    main()
