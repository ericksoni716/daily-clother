"""Phone-sized pictures of how each garment sits on the As worn figure (developer tool; not shipped).

    python tools/make_fit_shots.py NAME [--out DIR]

Draws the same garment in different fits and lengths with `closet.drawing.figure`, side by side in a page laid out
like a card on a 390 x 844 phone, in the light and the dark theme, then takes a picture of the page with a Chrome or
Chromium found on this computer:

- tees: the same tee in slim, regular and oversized;
- trousers: the same trousers with a slim, a straight and a wide leg;
- lengths: a cropped jacket next to a longline coat;
- sleeves: short, elbow and long sleeves.

The pictures are written as DIR/fit-<sheet>-<light|dark>-NAME.png (DIR is docs/screenshots by default).
"""
from __future__ import annotations

import argparse
import base64
import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tools"))

from make_figure_shots import THEMES, shoot  # noqa: E402

from closet.drawing.figure import Piece, figure  # noqa: E402
from closet.tagger.schema import Details, ItemTags, Silhouette  # noqa: E402

OUT = ROOT / "docs" / "screenshots"


def answer(category: str, silhouette: dict | None = None, color: str = "grey", **details) -> dict:
    return ItemTags(
        category=category, category_confidence=0.9, color=color, color_confidence=0.9, secondary_colors=[],
        pattern="solid", pattern_confidence=0.9, formality="casual", formality_confidence=0.9, season="all",
        season_confidence=0.9, silhouette=Silhouette.of(**(silhouette or {})), silhouette_confidence=0.9,
        details=Details.plain(**details), details_confidence=0.9, brand=None, size=None, material=None,
        needs_shot=None).model_dump(mode="json")


TEE_HEX, SHIRT_HEX, TROUSER_HEX, SNEAKER_HEX = "#d9d4c7", "#a9c3e0", "#5f6670", "#e8edf0"
CHINOS = Piece("trousers", answer("trousers", {"leg": "straight", "pant_length": "full"}, garment="chinos"), "#b9a98a")
JEANS = Piece("jeans", answer("jeans", {"leg": "straight", "pant_length": "full"}), "#2c3a5a")
SNEAKERS = Piece("sneakers", None, SNEAKER_HEX)
TEE = Piece("tee", answer("tee", {"sleeve": "short"}, sleeve_length="short", neckline="crew"), "#ffffff")


def tee(fit: str) -> Piece:
    return Piece("tee", answer("tee", {"sleeve": "short"}, fit_detail=fit, sleeve_length="short", neckline="crew"), TEE_HEX)


def trousers(leg: str) -> Piece:
    return Piece("trousers", answer("trousers", {"pant_length": "full"}, leg_shape=leg, garment="chinos"), TROUSER_HEX)


def shirt(sleeve: str) -> Piece:
    cuff = "barrel_1" if sleeve == "long" else "open_hem"
    return Piece("shirt", answer("shirt", fit_detail="regular", sleeve_length=sleeve, collar="point",
                                 placket="front_placket", cuff=cuff), SHIRT_HEX)


JACKET = Piece("jacket", answer("jacket", {"top_length": "cropped"}, fit_detail="cropped", collar="point",
                                placket="zip_full", cuff="rib_knit", hem="ribbed_band"), "#2a3550")
COAT = Piece("coat", answer("coat", {"top_length": "long"}, fit_detail="longline", collar="notch_lapel",
                            placket="front_placket", placket_buttons=3), "#3b3b3e")

# sheet name, title, then (caption, pieces) for each figure
SHEETS = [
    ("tees", "The same tee: slim, regular, oversized",
     [(f, dict(base=tee(f), bottom=CHINOS, shoes=SNEAKERS)) for f in ("slim", "regular", "oversized")]),
    ("trousers", "The same trousers: slim, straight, wide leg",
     [(leg, dict(base=TEE, bottom=trousers(leg), shoes=SNEAKERS)) for leg in ("slim", "straight", "wide")]),
    ("lengths", "A cropped jacket and a longline coat",
     [("cropped jacket", dict(base=TEE, outer=JACKET, bottom=JEANS, shoes=SNEAKERS)),
      ("longline coat", dict(base=TEE, outer=COAT, bottom=JEANS, shoes=SNEAKERS))]),
    ("sleeves", "Short, elbow and long sleeves",
     [(s, dict(base=shirt(s), bottom=CHINOS, shoes=SNEAKERS)) for s in ("short", "elbow", "long")]),
]


def page(figures: list[tuple[str, str]], title: str, theme: str) -> str:
    c = THEMES[theme]
    cells = "".join(
        f'<figure><img src="data:image/svg+xml;base64,{base64.b64encode(svg.encode("utf-8")).decode("ascii")}" alt="">'
        f"<figcaption>{html.escape(caption)}</figcaption></figure>" for caption, svg in figures)
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
body {{ margin: 0; background: {c['bg']}; color: {c['ink']}; font: 15px/1.4 system-ui, sans-serif; }}
main {{ padding: 16px; }}
h1 {{ font-size: 20px; margin: 4px 0 12px; }}
.card {{ background: {c['surface']}; border-radius: 16px; padding: 10px; display: flex; gap: 6px; }}
figure {{ flex: 1; margin: 0; border-radius: 12px; background: {c['card']}; box-shadow: inset 0 0 0 1px {c['edge']};
         display: flex; flex-direction: column; align-items: center; }}
img {{ display: block; width: 100%; height: auto; max-height: 640px; object-fit: contain; }}
figcaption {{ color: {c['muted']}; font-size: 13px; padding: 4px 0 8px; }}
</style></head><body><main><h1>{html.escape(title)}</h1><div class="card">{cells}</div></main></body></html>"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("name", help="the end of each file name, such as before or after")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for key, title, figures in SHEETS:
        svgs = [(caption, figure(pieces, uid=f"{key[:2]}{i}")) for i, (caption, pieces) in enumerate(figures)]
        for theme in THEMES:
            png = args.out / f"fit-{key}-{theme}-{args.name}.png"
            shoot(page(svgs, title, theme), png)
            print(f"wrote {png}")


if __name__ == "__main__":
    main()
