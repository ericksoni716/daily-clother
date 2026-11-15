"""Draw the sheets of traced shoes seen from the front on the figure (developer tool; not shipped; #192, stage 2c).

    python tools/make_traced_front_sheet.py [--out docs/screenshots] [--svg-only]

For each synthetic shoe (drawn by `backend/tests/shoe_photos.py`, never a real photo), one row: the side trace (the
traced shoe drawn back from its data), today's front shoe (from its style words), the new front shoe (from the
trace), and the same shoe on the figure with shorts and a crew sock, then under trousers resting on it. Each sheet is
written at phone size (the figure as a phone shows it, about 0.8 px a unit) and at 2x, in the light and the dark
theme (the figure keeps its own card in both; the page round it changes), and once close up (light):
DIR/traced-front-{phone,2x}-{light,dark}.png and DIR/traced-front-closeup.png. PNGs need Chrome or Chromium.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tools"))

from closet.drawing import frontshoe, traced
from closet.drawing import trace as T
from closet.drawing.figure import K_PX, Piece, figure, plan
from closet.drawing.illustrate import CARD, INK
from closet.tagger.schema import Details, ItemTags, Silhouette
from make_figure_sheet import to_png
from tests import shoe_photos as S

GREEN, BROWN, DARK_BROWN, GUM = (30, 96, 64), (92, 56, 36), (52, 30, 20), (176, 120, 64)
BLACK, SUEDE, WHEAT = (24, 24, 26), (150, 110, 75), (196, 150, 80)
# name, the photo's shoe, the photo's size, and the tagger's words for today's drawing (category, style, colour, details)
SHOES = [
    ("runner, three stripes", S.Shoe(upper=S.NAVY, midsole=S.WHITE, outsole=S.GREY, stripes=S.WHITE, laces=S.WHITE,
                                     sole_cm=3.6, sole_toe_cm=2.4, toe_spring_cm=1.2), (1000, 560),
     ("sneakers", "runner", "#223478", {})),
    ("two-tone court shoe", S.Shoe(upper=S.WHITE, midsole=S.WHITE, outsole=(214, 210, 200), heel_counter=GREEN,
                                   collar=GREEN, laces=S.WHITE, sole_cm=2.6, sole_toe_cm=2.2), (1000, 560),
     ("sneakers", "low_sneaker", "#f2f0ea", {})),
    ("chukka boot", S.Shoe(upper=S.TAN, midsole=GUM, outsole=None, top=list(frontshoe._BOOT), shaft_cm=14.5, sole_cm=2.0,
                           sole_toe_cm=1.7, laces=DARK_BROWN, eyelets=DARK_BROWN, lace_count=3), (1000, 700),
     ("boots", "boot", "#c49662", {"shoe_height": "high"})),
    ("white on white sneaker", S.Shoe(upper=(248, 248, 246), midsole=(240, 240, 236), outsole=None, laces=(236, 236, 232)),
     (1000, 560), ("sneakers", "low_sneaker", "#f8f8f6", {})),
    ("dress shoe, toe cap", S.Shoe(upper=BROWN, toe_cap=DARK_BROWN, midsole=(40, 30, 25), outsole=None, top=list(frontshoe._DRESS),
                                   sole_cm=1.2, sole_toe_cm=1.0, laces=DARK_BROWN, stitching=(150, 110, 80), gloss=True),
     (1000, 560), ("dress_shoes", "oxford", "#5c3824", {"toe_cap": "stitched"})),
    ("red and black runner", S.Shoe(**S.RED_BLACK_RUNNER), (1000, 560), ("sneakers", "runner", "#bd1f24", {})),
    ("chukka, low collar", S.Shoe(**S.LOW_CHUKKA), (1000, 640), ("boots", "boot", "#966e4b", {})),
    ("work boot, padded collar", S.Shoe(**S.WORK_BOOT), (1000, 700),
     ("boots", "boot", "#c3954f", {"shoe_height": "high", "tread": "lug"})),
    ("service boot, laced high", S.Shoe(**S.SERVICE_BOOT), (1000, 700),
     ("boots", "boot", "#c3954f", {"shoe_height": "high", "tread": "lug"})),
    ("busy runner", S.Shoe(**S.BUSY_RUNNER), (1000, 560), ("sneakers", "runner", "#808082", {})),
    ("runner, thin white midsole", S.Shoe(**S.AIR_RUNNER), (1000, 560), ("sneakers", "runner", "#bd1f24", {})),
    ("navy derby, navy laces", S.Shoe(**S.NAVY_DERBY), (1000, 560), ("sneakers", "derby", "#223478", {})),
]
GROUNDS = {"white on white sneaker": {"ground": (230, 230, 228), "shade_edge": 10}}

THEMES = {"light": ("#fbfaf7", "#26231f"), "dark": ("#1b1916", "#eeeae3")}
SIDE_W, SIDE_H = 120, 60        # the side trace's cell, in figure units
SHOE_W, SHOE_H = 60, 46         # a front shoe's cell
FEET_W, FEET_H = 130, 110       # the feet on the figure
LABEL_W = 120


def answer(category: str, style: str, silhouette: dict | None = None, **details) -> dict:
    return ItemTags(
        category=category, category_confidence=0.9, color="navy", color_confidence=0.9, secondary_colors=[],
        pattern="solid", pattern_confidence=0.9, formality="casual", formality_confidence=0.9, season="all",
        season_confidence=0.9, silhouette=Silhouette.of(**(silhouette or {})), silhouette_confidence=0.9,
        details=Details.plain(**({"shoe_style": style} if style else {}), **details), details_confidence=0.9, brand=None, size=None, material=None,
        needs_shot=None).model_dump(mode="json")


def trace_of(shoe: S.Shoe, size, name: str) -> traced.TracedShoe:
    img, _ = S.draw(shoe, size=size, noise=2, **GROUNDS.get(name, {}))
    t = traced.traced_shoe(T.trace_photo(img, None))
    if t is None or not t.gate.get("ok"):
        raise SystemExit(f"{name}: the trace did not pass the gate: {t.gate['reasons'] if t else 'no shoe'}")
    return t


def side_svg(t: traced.TracedShoe, x: float, y: float, w: float, h: float) -> str:
    """The traced shoe drawn back from its data, side on, toe to the left: its colour pieces in paint order."""
    k = min(w / (frontshoe.LENGTH + 2), h / 20)
    gx, gy = x + (w - frontshoe.LENGTH * k) / 2, y + h - 3

    def ring(r):
        return "M" + " L".join(f"{gx + (1 - u) * frontshoe.LENGTH * k:.1f},{gy - hh * k:.1f}" for u, hh in r) + "Z"

    out = []
    for r in t.regions:
        for piece in r.paths:
            out.append(f'<path d="{"".join(ring(q) for q in piece)}" fill="{r.color}" fill-rule="evenodd"/>')
    out.append(f'<path d="{"".join(ring(q) for q in t.regions[0].paths[0][:1])}" fill="none" stroke="{INK}" stroke-width="1"/>')
    for m in t.marks:
        for q in m.path:
            out.append(f'<path d="{ring(q)}" fill="{m.color}"/>')
    return "".join(out)


def front_svg(shoe, uid: str, x: float, y: float, w: float, h: float) -> str:
    """One front shoe, as the figure draws it (K_PX), centred in a cell."""
    x0, y0, x1, y1 = shoe.bbox
    k = min(w / (x1 - x0), h / (y1 - y0), 1.0)
    tx, ty = x + w / 2 - (x0 + x1) / 2 * k, y + h / 2 - (y0 + y1) / 2 * k
    return f'<defs>{shoe.defs}</defs><g transform="translate({tx:.1f} {ty:.1f}) scale({k:.3f})">{shoe.body}</g>'.replace(
        'id="fs', f'id="{uid}').replace("url(#fs", f"url(#{uid}")


def feet_svg(pieces: dict, uid: str, x: float, y: float, w: float, h: float) -> str:
    """The figure's feet: the figure's own drawing, its view box moved to the shoes."""
    shoes = plan(pieces).get("shoes")
    _, ground = shoes.point(shoes.front.anchors["ground"])
    svg = figure(pieces, uid=uid)
    head, rest = svg.split(">", 1)
    head = head.split("viewBox=")[0] + f'viewBox="{200 - w / 2:.1f} {ground - h + 6:.1f} {w} {h}" x="{x}" y="{y}" width="{w}" height="{h}"'
    return head + ">" + rest


def outfit(shoes: Piece, case: str) -> dict:
    tee = Piece("tee", answer("tee", "", {"sleeve": "short"}), "#f4f2ee")
    if case == "shorts":
        sock = Piece("other", answer("other", "", accessory="socks", accessory_kind="casual_crew"), "#2e7d4f")
        return {"base": tee, "bottom": Piece("shorts", None, "#6f7550"), "shoes": shoes, "accessories": [sock]}
    trousers = Piece("trousers", answer("trousers", "", {"leg": "straight", "pant_length": "full"}), "#6f7278")
    return {"base": tee, "bottom": trousers, "shoes": shoes}


def rows() -> list[tuple[str, traced.TracedShoe, Piece, Piece]]:
    out = []
    for name, shoe, size, (category, style, colour, details) in SHOES:
        t = trace_of(shoe, size, name)
        ans = answer(category, style, **details)
        out.append((name, t, Piece(category, ans, colour), Piece(category, ans, colour, traced=t)))
    return out


def sheet(data, scale: float, theme: str) -> str:
    bg, ink = THEMES[theme]
    pad, head = 8, 22
    cols = [("side trace", SIDE_W, SIDE_H), ("today", SHOE_W, SHOE_H), ("from the trace", SHOE_W, SHOE_H),
            ("figure: shorts, crew sock", FEET_W, FEET_H), ("figure: trousers", FEET_W, FEET_H)]
    row_h = max(c[2] for c in cols) + pad
    W = LABEL_W + sum(c[1] + pad for c in cols) + pad
    H = head + len(data) * row_h + pad
    out = [f'<rect width="{W}" height="{H}" fill="{bg}"/>']
    x = LABEL_W
    for title, w, _ in cols:
        out.append(f'<text x="{x + w / 2}" y="15" text-anchor="middle" font-family="system-ui,sans-serif" font-size="9" fill="{ink}">{title}</text>')
        x += w + pad
    for r, (name, t, plain, worn) in enumerate(data):
        y = head + r * row_h
        out.append(f'<text x="{pad}" y="{y + row_h / 2}" font-family="system-ui,sans-serif" font-size="9" fill="{ink}">{name}</text>')
        x = LABEL_W
        for c, (_, w, h) in enumerate(cols):
            out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" fill="{CARD}"/>')
            uid = f"r{r}c{c}"
            if c == 0:
                out.append(side_svg(t, x, y, w, h))
            elif c in (1, 2):
                spec = plan({"shoes": plain}).get("shoes")
                shoe = frontshoe.front_shoe(spec.spec, K_PX, sole_default=spec.shape.sole_default, traced=t if c == 2 else None)
                out.append(front_svg(shoe, uid, x, y, w, h))
            else:
                out.append(feet_svg(outfit(worn, "shorts" if c == 3 else "trousers"), uid, x, y, w, h))
            x += w + pad
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W * scale:.0f}" height="{H * scale:.0f}">'
            + "".join(out) + "</svg>")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "screenshots")
    ap.add_argument("--svg-only", action="store_true")
    a = ap.parse_args()
    data = rows()
    a.out.mkdir(parents=True, exist_ok=True)
    # a phone shows the whole figure (about 650 units tall) in about 520 px: 0.8 px a unit
    for label, scale, theme in [("phone-light", 0.8, "light"), ("phone-dark", 0.8, "dark"), ("2x-light", 1.6, "light"),
                                ("2x-dark", 1.6, "dark"), ("closeup", 5.0, "light")]:
        svg = sheet(data, scale, theme)
        path = a.out / f"traced-front-{label}.svg"
        path.write_text(svg, encoding="utf-8")
        if not a.svg_only:
            w, h = (int(v) for v in re.search(r'width="(\d+)" height="(\d+)"', svg).groups())
            to_png(path, path.with_suffix(".png"), (w, h))
            path.unlink()
        print(f"wrote {path.with_suffix('.svg' if a.svg_only else '.png')}")


if __name__ == "__main__":
    main()
