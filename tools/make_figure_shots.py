"""Phone-sized pictures of outfits as worn, in the light and the dark theme (developer tool; not shipped).

    python tools/make_figure_shots.py NAME [--limbs] [--out DIR]

Draws four outfits with `closet.drawing.figure` (from the demo closet's items, plus a pair of sandals the demo
closet does not have) and puts each one in a page laid out like the Today card on a 390 x 844 phone, in the light
and the dark theme, then takes a picture of the page with a Chrome or Chromium found on this computer. The
pictures are written as DIR/figure-<outfit>-<light|dark>-NAME.png (DIR is docs/screenshots by default), so the
same outfits can be compared before and after a change to the figure. With `--limbs` the form shows a short tonal
arm below a short sleeve and a leg below shorts (see `figure`).
"""
from __future__ import annotations

import argparse
import base64
import html
import inspect
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tools"))

from closet.drawing.figure import Piece, figure  # noqa: E402
from closet.illustrations import describe  # noqa: E402
from closet.tagger.schema import Details, ItemTags, Silhouette  # noqa: E402
from make_figure_sheet import demo_rows  # noqa: E402

OUT = ROOT / "docs" / "screenshots"
PHONE = (390, 844)

# the page around the figure: the app's colours (frontend/src/styles.css) for each theme
THEMES = {
    "light": dict(bg="#f6f2ea", surface="#fffdf9", ink="#26231f", muted="#6b655b", card="#f1eee8", edge="#e4ded3"),
    "dark": dict(bg="#1b1916", surface="#24211d", ink="#eeeae3", muted="#aaa397", card="#e6e1d8", edge="#cfc8bb"),
}


def sandals() -> Piece:
    """Tan two-strap sandals: the demo closet has none."""
    tags = ItemTags(category="sandals", category_confidence=0.9, color="tan", color_confidence=0.9, secondary_colors=[],
                    pattern="solid", pattern_confidence=0.9, formality="casual", formality_confidence=0.9,
                    season="warm", season_confidence=0.9, silhouette=Silhouette.of(), silhouette_confidence=0.9,
                    details=Details.plain(shoe_style="sandal", other_features=["sandal"]), details_confidence=0.9,
                    brand=None, size=None, material=None, needs_shot=None)
    return Piece("sandals", tags.model_dump(mode="json"), "#a87a4f", "tan")


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
]


def pieces_for(names: dict) -> dict:
    rows = demo_rows()
    out = {}
    for place, name in names.items():
        if place == "accessories":
            out[place] = [describe(rows[n]) for n in name]
        else:
            out[place] = describe(rows[name]) if name else sandals()
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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("name", help="the end of each file name, such as before or after")
    ap.add_argument("--limbs", action="store_true", help="draw the form's short tonal arms and legs")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    extra = {"limbs": True} if args.limbs and "limbs" in inspect.signature(figure).parameters else {}
    for key, caption, names in OUTFITS:
        svg = figure(pieces_for(names), uid="s" + key[:2], **extra)
        for theme in THEMES:
            png = args.out / f"figure-{key}-{theme}-{args.name}.png"
            shoot(page(svg, caption, theme), png)
            print(f"wrote {png}")


if __name__ == "__main__":
    main()
