"""Draw a sheet of outfits as worn, from the demo closet's items (developer tool; not shipped).

    python tools/make_figure_sheet.py [OUT.svg] [--png OUT.png]

Each figure is drawn by `closet.drawing.figure` from the items' stored descriptions,
the way `POST /api/outfits/figure` draws them. The outfits cover cold, mild and hot
days; one, two and three layers on top; shorts; boots. With `--png` the sheet is also
turned into a picture by a Chrome or Chromium found on this computer.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from closet.drawing.figure import figure  # noqa: E402
from closet.illustrations import describe  # noqa: E402

DEMO = ROOT / "backend" / "closet" / "demo_data" / "items.json"
OUT = ROOT / "docs" / "screenshots" / "outfit-figures.svg"

# caption, then the demo items by name for each place
OUTFITS = [
    ("Cold: tee, open chore jacket, open overcoat", dict(base="White tee", mid="Tan chore jacket", outer="Black overcoat",
                                                          bottom="Dark indigo jeans", shoes="Brown boots")),
    ("Cold: shirt, cable sweater, open overcoat", dict(base="Blue oxford shirt", mid="Burgundy cable sweater",
                                                        outer="Black overcoat", bottom="Brown corduroy trousers",
                                                        shoes="Brown boots")),
    ("Cool: turtleneck, open bomber", dict(base="Black tee", mid="Marl turtleneck", outer="Navy bomber jacket",
                                           bottom="Black jeans", shoes="Black high-tops")),
    ("Mild: shirt under a v-neck sweater", dict(base="White dress shirt", mid="Cream v-neck sweater",
                                                bottom="Grey wool trousers", shoes="White leather sneakers")),
    ("Mild: tee, open flannel shirt", dict(base="Black tee", mid="Plaid flannel shirt", bottom="Light wash jeans",
                                           shoes="White canvas sneakers")),
    ("Mild: henley under a hoodie", dict(base="Oatmeal henley", mid="Grey hoodie", bottom="Black jeans",
                                         shoes="Grey runners")),
    ("Warm: oxford shirt, chinos", dict(base="Blue oxford shirt", bottom="Grey wool trousers", shoes="Brown boots")),
    ("Hot: tee and shorts", dict(base="White tee", bottom="Olive shorts", shoes="White canvas sneakers")),
    ("Hot: polo and shorts", dict(base="Navy polo", bottom="Olive shorts", shoes="White leather sneakers")),
    ("Hot: chambray shirt, shorts", dict(base="Chambray shirt", bottom="Olive shorts", shoes="Grey runners")),
]

CELL_W, CELL_H, CAPTION = 300, 470, 40
COLUMNS = 5


def demo_rows() -> dict[str, dict]:
    """The demo closet's items as rows of the items table (as the demo closet is first opened: no owner corrections)."""
    items = json.loads(DEMO.read_text(encoding="utf-8"))["items"]
    return {it["name"]: {"id": it["id"], "category": it["category"], "color": it["color"], "color_hex": it["color_hex"],
                         "pattern": it["pattern"], "silhouette": json.dumps(it.get("silhouette") or {}), "source": "{}",
                         "tag_answer": json.dumps(it["answer"]) if it.get("answer") else None}
            for it in items}


def figures() -> list[tuple[str, str]]:
    rows = demo_rows()
    out = []
    for n, (caption, names) in enumerate(OUTFITS):
        pieces = {place: describe(rows[name]) for place, name in names.items()}
        out.append((caption, figure(pieces, uid="f" + chr(ord("a") + n))))
    return out


def sheet(drawn: list[tuple[str, str]]) -> str:
    rows = (len(drawn) + COLUMNS - 1) // COLUMNS
    w, h = COLUMNS * CELL_W, rows * (CELL_H + CAPTION)
    cells = []
    for i, (caption, svg) in enumerate(drawn):
        x, y = (i % COLUMNS) * CELL_W, (i // COLUMNS) * (CELL_H + CAPTION)
        inner = re.sub(r'width="[\d.]+" height="[\d.]+"', f'x="{x + 10}" y="{y + 6}" width="{CELL_W - 20}" height="{CELL_H - 6}"',
                       svg, count=1)
        cells.append(inner + f'<text x="{x + CELL_W / 2}" y="{y + CELL_H + 22}" text-anchor="middle" '
                             f'font-family="sans-serif" font-size="15" fill="#26231f">{caption}</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'<rect width="{w}" height="{h}" fill="#ffffff"/>{"".join(cells)}</svg>')


def to_png(svg_path: Path, png_path: Path, size: tuple[int, int]) -> None:
    chrome = next((shutil.which(c) for c in ("google-chrome", "chromium", "chromium-browser", "chrome") if shutil.which(c)), None)
    if not chrome:
        raise SystemExit("--png needs Chrome or Chromium on the PATH")
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "sheet.html"
        page.write_text(f'<html><body style="margin:0">{svg_path.read_text(encoding="utf-8")}</body></html>', encoding="utf-8")
        subprocess.run([chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                        f"--window-size={size[0]},{size[1]}", f"--screenshot={png_path.resolve()}", page.as_uri()],
                       check=True, capture_output=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out", nargs="?", type=Path, default=OUT)
    ap.add_argument("--png", type=Path, help="also write the sheet as a PNG picture")
    args = ap.parse_args()
    svg = sheet(figures())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(svg, encoding="utf-8")
    print(f"wrote {args.out}")
    if args.png:
        w, h = (int(v) for v in re.search(r'width="(\d+)" height="(\d+)"', svg).groups())
        to_png(args.out, args.png, (w, h))
        print(f"wrote {args.png}")


if __name__ == "__main__":
    main()
