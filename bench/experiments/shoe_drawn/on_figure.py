"""Lay the saved example drawings on the app's As worn figure, in place of today's front shoes (a picture to judge
the view by; not app code, nothing imports it).

    python bench/experiments/shoe_drawn/on_figure.py [--out bench/out/shoe_drawn]

The examples are drawn in the experiment's frame (x 0 to 200 centred on 100, ground at y = 240, the leg x 62 to 138
going in at about y = 40 to 60), from the front and a little above. The figure looks down 24 degrees with the toes
turned out 11 degrees. Each drawing is laid on the figure's own feet: its ground on the figure's ground, its leg on
the figure's leg (so the frame is scaled until its leg is as wide as the figure's ankle), turned out 11 degrees
round the opening, the viewer's right foot mirrored unless there is a right drawing. Everything else (the figure,
the trousers, where their hem falls) is the app's own drawing, unchanged: the hem is still placed for today's shoe.

Writes on-figure-closeup.png (the feet, large), on-figure-phone.png (whole figures at phone size) and the SVGs
beside them. PNGs need Chrome or Chromium on the PATH.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tools"))

from make_figure_sheet import to_png  # noqa: E402
from make_traced_front_sheet import answer  # noqa: E402

from closet.drawing.figure import Piece, figure, plan  # noqa: E402

EX = HERE / "EXAMPLES"
FRAME_LEG = (62.0, 138.0)   # the frame's leg, left and right edge
FRAME_GROUND = 240.0
FRAME_OPENING = (100.0, 50.0)   # where the leg goes in: the turn is made round it
TURN = 11.0

# name, the example's left (and right) drawing, and today's drawing for the same shoe (category, style, colour, details)
SHOES = [
    ("runner", "runner-left.svg", "runner-right.svg", ("sneakers", "runner", "#f1f0eb", {})),
    ("boot", "boot.svg", None, ("boots", "chelsea_boot", "#6e5a3f", {})),
    ("dress shoe", "dress-shoe.svg", None, ("dress_shoes", "oxford", "#b5622f", {"toe_cap": "stitched"})),
    ("boat shoe", "boat-shoe.svg", None, ("dress_shoes", "loafer", "#73523f", {})),
]
CASES = [("shorts and a crew sock", "shorts"), ("full-length trousers", "full"), ("ankle-length trousers", "ankle")]


def outfit(shoe: tuple, case: str) -> dict:
    category, style, hex_, details = shoe
    shoes = Piece(category, answer(category, style, **details), hex_)
    tee = Piece("tee", answer("tee", "", {"sleeve": "short"}), "#f4f2ee")
    if case == "shorts":
        sock = Piece("other", answer("other", "", accessory="socks", accessory_kind="casual_crew"), "#2e7d4f")
        return {"base": tee, "bottom": Piece("shorts", None, "#6f7550"), "shoes": shoes, "accessories": [sock]}
    trousers = Piece("trousers", answer("trousers", "", {"leg": "straight", "pant_length": case}), "#6f7278")
    return {"base": tee, "bottom": trousers, "shoes": shoes}


INK_STROKE = re.compile(r'(stroke="#2622[13]f"[^>]*?stroke-width=")([0-9.]+)(")')
TODAY_LINE = 2.2 / (4 * 0.297)   # today's shoe outline is 2.2 px; the frame's bold outline (4 units) lands at 1.2 px


def fragment(name: str, uid: str, line: float = 1.0) -> str:
    """One example drawing with its ids made unique, its ink lines (the outline, 4 units, and the inner lines,
    1.6) drawn `line` times as thick; the thick strokes that draw laces and bows are left as they are."""
    text = (EX / name).read_text(encoding="utf-8")
    if line != 1.0:
        text = INK_STROKE.sub(lambda m: m[1] + (f"{float(m[2]) * line:.2f}" if float(m[2]) <= 4.5 else m[2]) + m[3], text)
    return text.replace('id="', f'id="{uid}').replace("url(#", f"url(#{uid}").replace('href="#', f'href="#{uid}')


def drawn_pair(pieces: dict, left: str, right: str | None, uid: str, line: float = 1.0) -> tuple[str, dict]:
    """The example drawing placed on each of the figure's feet, and the numbers it was placed by."""
    shoes = plan(pieces).get("shoes")
    a = shoes.front.anchors
    leg_w = 2 * (a["ankle_r"][0] - a["ankle"][0])
    k = leg_w / (FRAME_LEG[1] - FRAME_LEG[0])
    ground = shoes.box()[3] - 2          # today's sole's lowest point (its box has 2 px to spare)
    ox, oy = FRAME_OPENING
    out = []
    for copy in (0, 1):
        ax, ay = shoes.point(a["ankle"], copy)
        if copy == 0 or right is None:
            mirror = 1 if copy == 0 else -1
            body = fragment(left, f"{uid}{copy}", line)
            turn = TURN
        else:
            mirror, body, turn = 1, fragment(right, f"{uid}{copy}", line), -TURN
        # frame -> figure: the frame's leg centre over the figure's ankle, its ground on the figure's ground
        place = f"translate({ax:.2f} {ground:.2f}) scale({mirror * k:.4f} {k:.4f}) translate({-100:.1f} {-FRAME_GROUND:.1f})"
        out.append(f'<g transform="{place}"><g transform="rotate({turn} {ox} {oy})">{body}</g></g>')
    top = ground + k * (oy - FRAME_GROUND)
    info = {"scale": k, "leg_px": leg_w, "ground": ground, "opening_y": top, "leg_ends": shoes.point(a["ankle"])[1],
            "today_box": shoes.box()}
    return "".join(out), info


def swap_shoes(svg: str, uid: str, pair: str) -> str:
    """Today's shoe pair (the group <g id=UIDp>, drawn after the legs and before the trousers) replaced by `pair`,
    inside the same clip under full-length trousers."""
    start = svg.index(f'<g id="{uid}p">')
    end = svg.index(f'<g id="{uid}w">', start)
    old = svg[start:end]
    m = re.match(rf'<g id="{uid}p"><g clip-path="url\(#{uid}k\)">', old)
    inner = f'<g clip-path="url(#{uid}k)">{pair}</g>' if m else pair
    return svg[:start] + f'<g id="{uid}p">{inner}</g>' + svg[end:]


def view_box(svg: str) -> tuple[float, ...]:
    return tuple(float(v) for v in re.search(r'viewBox="([^"]+)"', svg).group(1).split())


def cell(svg: str, box: tuple[float, float, float, float], x: float, y: float, w: float, h: float) -> str:
    head, rest = svg.split(">", 1)
    head = head.split("viewBox=")[0] + (f'viewBox="{box[0]:.1f} {box[1]:.1f} {box[2]:.1f} {box[3]:.1f}" '
                                        f'x="{x}" y="{y}" width="{w}" height="{h}"')
    return head + ">" + rest


def text(x, y, s, size=15, anchor="middle", weight="normal"):
    return (f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="sans-serif" font-size="{size}" '
            f'font-weight="{weight}" fill="#26231f">{s}</text>')


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=ROOT / "bench" / "out" / "shoe_drawn")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    # the feet, close up: for each shoe, today's drawing, the example laid on as drawn, and with today's line weight
    FW, FH, ZOOM = 120, 122, 2.4        # the feet's box in figure units, and how much larger it is drawn
    cw, ch = FW * ZOOM, FH * ZOOM
    lab, gap, head = 190, 12, 70
    kinds = [("today", None), ("example laid on", 1.0), ("same, today's line weight", TODAY_LINE)]
    cols = len(SHOES) * len(kinds)
    W, H = lab + cols * (cw + gap) + len(SHOES) * 16, head + len(CASES) * (ch + gap)
    cells, notes, phone = [], [], {}
    for j, (name, left, right, today) in enumerate(SHOES):
        x0 = lab + j * (len(kinds) * (cw + gap) + 16)
        cells.append(text(x0 + len(kinds) * (cw + gap) / 2, 26, name, 20, weight="bold"))
        for i, (label, case) in enumerate(CASES):
            y = head + i * (ch + gap)
            if j == 0:
                cells.append(text(lab - 12, y + ch / 2, label, 15, anchor="end"))
            pieces = outfit(today, case)
            for n, (kind, line) in enumerate(kinds):
                x = x0 + n * (cw + gap)
                if i == 0:
                    cells.append(text(x + cw / 2, 52, kind))
                uid = f"u{j}{i}{n}"
                svg = figure(pieces, uid=uid)
                if line is not None:
                    pair, info = drawn_pair(pieces, left, right, f"d{j}{i}{n}", line)
                    svg = swap_shoes(svg, uid, pair)
                box = (200 - FW / 2, info["ground"] - FH + 8, FW, FH) if line is not None else None
                phone.setdefault((name, case), []).append((kind, svg))
                cells.append(f'<rect x="{x}" y="{y}" width="{cw}" height="{ch}" fill="#f1eee8"/>')
                cells.append((svg, x, y))
            # today's cell takes the same box as the drawn ones
            for c in range(len(cells)):
                if isinstance(cells[c], tuple):
                    sv, cx, cy = cells[c]
                    cells[c] = cell(sv, box, cx, cy, cw, ch)
            if case == "shorts":
                tb = info["today_box"]
                notes.append(f"{name}: scale {info['scale']:.3f} px a frame unit (leg {info['leg_px']:.1f} px); "
                             f"opening at y {info['opening_y']:.1f}, leg ends at y {info['leg_ends']:.1f}; "
                             f"today's pair {tb[2] - tb[0] - 4:.0f} x {tb[3] - tb[1] - 4:.0f} px")
    sheet = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">'
             f'<rect width="{W}" height="{H}" fill="#ffffff"/>{"".join(cells)}</svg>')
    (args.out / "on-figure-closeup.svg").write_text(sheet, encoding="utf-8")
    to_png(args.out / "on-figure-closeup.svg", args.out / "on-figure-closeup.png", (int(W), int(H)))

    # whole figures at phone size (about 0.8 px a unit, as the Today screen shows one): shorts above, trousers below
    PK = 0.8
    first = next(iter(phone.values()))[0][1]
    vb = view_box(first)
    pw, ph = vb[2] * PK, vb[3] * PK
    pcells = []
    for j, (name, *_rest) in enumerate(SHOES):
        x0 = 10 + j * (len(kinds) * (pw + 6) + 24)
        pcells.append(text(x0 + len(kinds) * (pw + 6) / 2, 18, name, 13, weight="bold"))
        for r, case in enumerate(("shorts", "full")):
            y = 30 + r * (ph + 30)
            for n, (_kind, svg) in enumerate(phone[(name, case)]):
                x = x0 + n * (pw + 6)
                pcells.append(cell(svg, view_box(svg), x, y, pw, ph))
                if r == 1:
                    pcells.append(text(x + pw / 2, y + ph + 16, ["today", "example", "+ line"][n], 11))
    PW, PH = 10 + len(SHOES) * (len(kinds) * (pw + 6) + 24), 30 + 2 * (ph + 30)
    psheet = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {PW:.0f} {PH:.0f}" width="{PW:.0f}" '
              f'height="{PH:.0f}"><rect width="{PW:.0f}" height="{PH:.0f}" fill="#fbfaf7"/>{"".join(pcells)}</svg>')
    (args.out / "on-figure-phone.svg").write_text(psheet, encoding="utf-8")
    to_png(args.out / "on-figure-phone.svg", args.out / "on-figure-phone.png", (int(PW), int(PH)))
    print("\n".join(notes))
    print(f"wrote {args.out}/on-figure-closeup.png and on-figure-phone.png")


if __name__ == "__main__":
    main()
