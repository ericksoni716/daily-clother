"""Lay the saved example drawings on the app's As worn figure, in place of today's front shoes (a picture to judge
the view by; not app code, nothing imports it).

    python bench/experiments/shoe_drawn/on_figure.py [--out bench/out/shoe_drawn]

The examples are drawn in the experiment's frame (x 0 to 200 centred on 100, ground at y = 240, the leg x 62 to 138
going in at about y = 40 to 60), from the front and a little above. Each drawing is laid on the figure's own feet:
its ground on the figure's ground, its leg on the figure's leg (the frame scaled until its leg is as wide as the
figure's ankle), its lines as thick as the figure's, the viewer's right foot mirrored unless there is a right
drawing, and the toes turned out as far as today's shoes are. A turned foot keeps the top of the shoe round the
leg: only the part below a hinge (a low shoe's opening, a boot's instep) slides sideways, more the nearer the toe,
so the collar or a boot's shaft stays upright round the leg. (Tilting the whole drawing, the first try, leant a
boot's shaft away from the leg.)

The trousers are the app's own, with their hem placed from the drawing instead of today's shoe: a full-length hem
rests on the front of the drawing's opening, but, as the trousers keep their own length, never lower than it would
rest on an ordinary sneaker (the frame's collar front at y = 50), so under a lower shoe the sock shows. Both are
done by standing the drawing's opening in for today's shoe's while the figure is drawn (`drawn_opening`); the app
itself is unchanged.

Writes on-figure-closeup.png (the feet, large), on-figure-phone.png (whole figures at phone size) and the SVGs
beside them. PNGs need Chrome or Chromium on the PATH.
"""
from __future__ import annotations

import argparse
import contextlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tools"))

from make_figure_sheet import to_png  # noqa: E402
from make_traced_front_sheet import answer  # noqa: E402

from closet.drawing import figure as F  # noqa: E402
from closet.drawing import worn as W  # noqa: E402
from closet.drawing.figure import K_PX, Piece, figure, plan  # noqa: E402

EX = HERE / "EXAMPLES"
FRAME_LEG = (62.0, 138.0)   # the frame's leg, left and right edge
FRAME_GROUND = 240.0
ORDINARY_RIM = 50.0         # the frame's collar front on an ordinary low sneaker: the lowest a full-length hem comes
INK_STROKE = re.compile(r'(stroke="#2622[13]f"[^>]*?stroke-width=")([0-9.]+)(")')
TODAY_LINE = 2.2 / (4 * 0.297)   # today's shoe outline is 2.2 px; the frame's bold outline (4 units) lands at 1.2 px


@dataclass
class Drawn:
    """One saved drawing and where, in the frame, its opening is: the top of its front where the leg goes in (a
    tongue, a vamp, a boot's shaft), the top of its back, the instep (above a low shoe's opening front, below a
    boot's: that is how the figure tells a shaft the hem rests on), and the hinge the toe turns out below."""
    label: str
    left: str
    right: str | None
    front: float
    back: float
    instep: float
    hinge: float
    size: tuple[float, float] = (1.0, 1.0)   # drawn this much as wide and as tall, standing on the same ground

    def y(self, v: float) -> float:   # a height in the saved drawing, once it is resized
        return FRAME_GROUND - (FRAME_GROUND - v) * self.size[1]

    def resized(self) -> Drawn:
        return Drawn(self.label, self.left, self.right, self.y(self.front), self.y(self.back), self.y(self.instep),
                     self.y(self.hinge), self.size)


# name, today's drawing for the same shoe (category, style, colour, details), and the drawings to compare with it
SHOES = [
    ("runner", ("sneakers", "runner", "#f1f0eb", {}),
     [Drawn("new", "runner-left.svg", "runner-right.svg", front=24, back=16, instep=22, hinge=24)]),
    ("boot", ("boots", "chelsea_boot", "#6e5a3f", {}),
     [Drawn("new", "boot.svg", None, front=-32, back=-46, instep=84, hinge=84)]),
    ("dress shoe", ("dress_shoes", "oxford", "#b5622f", {"toe_cap": "stitched"}),
     [Drawn("new", "dress-shoe.svg", None, front=32, back=32, instep=30, hinge=32)]),
    ("boat shoe", ("dress_shoes", "loafer", "#73523f", {}),
     [Drawn("as saved", "boat-shoe.svg", None, front=34, back=34, instep=32, hinge=34),
      Drawn("lower and narrower", "boat-shoe.svg", None, front=34, back=34, instep=32, hinge=34, size=(0.92, 0.78))]),
]
CASES = [("shorts and a crew sock", "shorts"), ("full-length trousers", "full"), ("ankle-length trousers", "ankle")]


def outfit(shoe: tuple, case: str) -> dict:
    category, style, hex_, details = shoe
    shoes = Piece(category, answer(category, style, **details), hex_)
    tee = Piece("tee", answer("tee", "", {"sleeve": "short"}), "#f4f2ee")
    if case == "shorts":
        sock = Piece("other", answer("other", "", accessory="socks", accessory_kind="casual_crew"), "#2e7d4f")
        return {"base": tee, "bottom": Piece("shorts", None, "#6f7550"), "shoes": shoes, "accessories": [sock]}
    sock = Piece("other", answer("other", "", accessory="socks", accessory_kind="casual_crew"), "#2e7d4f")
    trousers = Piece("trousers", answer("trousers", "", {"leg": "straight", "pant_length": case}), "#6f7278")
    return {"base": tee, "bottom": trousers, "shoes": shoes, "accessories": [sock]}


def fragment(d: Drawn, name: str, uid: str) -> str:
    """One saved drawing, resized, its ids made unique, its ink lines (the outline, 4 units, and the inner lines,
    1.6) as thick as the figure's; the thick strokes that draw laces and bows are left as they are."""
    text = (EX / name).read_text(encoding="utf-8")
    text = INK_STROKE.sub(lambda m: m[1] + (f"{float(m[2]) * TODAY_LINE:.2f}" if float(m[2]) <= 4.5 else m[2]) + m[3],
                          text)
    text = text.replace('id="', f'id="{uid}').replace("url(#", f"url(#{uid}").replace('href="#', f'href="#{uid}')
    sx, sy = d.size
    if (sx, sy) != (1.0, 1.0):
        text = f'<g transform="translate(100 {FRAME_GROUND}) scale({sx} {sy}) translate(-100 {-FRAME_GROUND})">{text}</g>'
    return text


def turned(body: str, uid: str, shear: float, hinge: float) -> str:
    """The drawing with its toe swung out: above the hinge as it is, below it slid sideways by `shear` units for each
    unit below the hinge. The two halves meet at the hinge, where the slide is nothing."""
    if not shear:
        return body
    lower = body.replace('id="', 'id="h')   # the second copy's ids kept apart from the first's
    return (f'<clipPath id="{uid}hu"><rect x="-1000" y="-1000" width="3000" height="{1000 + hinge + 0.6}"/></clipPath>'
            f'<clipPath id="{uid}hd"><rect x="-1000" y="{hinge}" width="3000" height="2000"/></clipPath>'
            f'<g clip-path="url(#{uid}hu)">{body}</g>'
            f'<g clip-path="url(#{uid}hd)"><g transform="matrix(1 0 {shear:.4f} 1 {-shear * hinge:.3f} 0)">'
            f'{lower}</g></g>')


@dataclass
class Place:
    """How the frame lands on the figure's feet: k px a frame unit, the frame's x = 100 on each ankle, its ground
    on the figure's ground (today's sole's lowest point), and the slide of the toe a unit below the hinge."""
    k: float
    ankles: tuple[float, float]
    ground: float
    shear: float
    shoe_dx: float   # the left shoe's own coordinates: figure minus these
    shoe_dy: float

    def fig_y(self, v: float) -> float:
        return self.ground + self.k * (v - FRAME_GROUND)


def placing(pieces: dict) -> Place:
    shoes = plan(pieces).get("shoes")
    a = shoes.front.anchors
    k = 2 * (a["ankle_r"][0] - a["ankle"][0]) / (FRAME_LEG[1] - FRAME_LEG[0])
    shear = (a["toe"][0] - a["ankle"][0]) / (a["toe"][1] - a["ankle"][1])
    t = shoes.transforms[0]
    return Place(k, (shoes.point(a["ankle"], 0)[0], shoes.point(a["ankle"], 1)[0]), shoes.box()[3] - 2, shear, t[4], t[5])


def drawn_pair(d: Drawn, p: Place, uid: str) -> str:
    """The drawing placed on each of the figure's feet, the toes turned out."""
    r = d.resized()
    out = []
    for copy in (0, 1):
        if copy == 0 or d.right is None:
            mirror, body, sh = (1 if copy == 0 else -1), fragment(d, d.left, f"{uid}{copy}"), p.shear
        else:   # the right shoe drawn on its own: not mirrored, so its toe swings the other way
            mirror, body, sh = 1, fragment(d, d.right, f"{uid}{copy}"), -p.shear
        place = (f"translate({p.ankles[copy]:.2f} {p.ground:.2f}) scale({mirror * p.k:.4f} {p.k:.4f}) "
                 f"translate(-100 {-FRAME_GROUND:.1f})")
        out.append(f'<g transform="{place}">{turned(body, f"{uid}{copy}", sh, r.hinge)}</g>')
    return "".join(out)


@contextlib.contextmanager
def drawn_opening(d: Drawn, p: Place):
    """While the figure is drawn, today's shoe's opening, instep and back of its opening are the drawing's (so the
    trousers' hem falls on the drawing), and full-length trousers are as long as it takes for their hem's front to
    just meet an ordinary sneaker's collar (with the drawings larger than today's shoes, the figure's own length, 5 cm
    above the ground, would bury a low shoe); the sock is drawn under them, for where a low shoe shows it."""
    r = d.resized()
    orig_shoe, orig_hem = F.front_shoe, F._hem

    def shoe_y(v: float) -> float:   # a frame height in the left shoe's own coordinates
        return p.fig_y(v) - p.shoe_dy

    def front_shoe(*args, **kw):
        s = orig_shoe(*args, **kw)
        ax = s.anchors["ankle"][0]
        s.anchors.update(opening=(ax, shoe_y(r.front)), instep=(ax, shoe_y(r.instep)), opening_back=(ax, shoe_y(r.back)))
        return s

    def hem(params, shoe, natural):
        if params.get("length", "full") == "full":   # long enough that its front just meets an ordinary sneaker
            meets = p.fig_y(ORDINARY_RIM) + F.HEM_FRONT_CM.get(params.get("break", "none"), 0.3) * K_PX
            natural = min(natural, meets - F.DIP_CM * K_PX)
        return orig_hem(params, shoe, natural)

    orig_socks = W._socks

    def socks(fig, layout, *args):   # the sock drawn under full-length trousers too, for where a low shoe shows it
        legs = fig._legs
        fig._legs = lambda lay: (*legs(lay)[:2], False)
        try:
            return orig_socks(fig, layout, *args)
        finally:
            fig._legs = legs

    F.front_shoe, F._hem, W._socks = front_shoe, hem, socks
    try:
        yield
    finally:
        F.front_shoe, F._hem, W._socks = orig_shoe, orig_hem, orig_socks


def swap_shoes(svg: str, uid: str, pair: str) -> str:
    """Today's shoe pair (the group <g id=UIDp>, drawn after the legs and before the trousers) replaced by `pair`,
    inside the same clip under full-length trousers."""
    start = svg.index(f'<g id="{uid}p">')
    end = svg.index(f'<g id="{uid}w">', start)
    m = re.match(rf'<g id="{uid}p"><g clip-path="url\(#{uid}k\)">', svg[start:end])
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

    # every figure: for each shoe and outfit, today's drawing and each drawing to compare with it
    figs: dict[tuple[str, str], list[tuple[str, str]]] = {}
    grounds = {}
    for j, (name, today, drawings) in enumerate(SHOES):
        for i, (_label, case) in enumerate(CASES):
            pieces = outfit(today, case)
            p = placing(pieces)
            grounds[name] = p.ground
            row = [("today", figure(pieces, uid=f"t{j}{i}"))]
            for n, d in enumerate(drawings):
                uid = f"n{j}{i}{n}"
                with drawn_opening(d, p):
                    svg = figure(pieces, uid=uid)
                row.append((d.label, swap_shoes(svg, uid, drawn_pair(d, p, f"d{j}{i}{n}"))))
            figs[(name, case)] = row
        print(f"{name}: {p.k:.3f} px a frame unit; toe slides {p.shear:.3f} a unit below the hinge; an ordinary "
              f"sneaker's collar front at y {p.fig_y(ORDINARY_RIM):.1f}")

    # the feet, close up
    FW, FH, ZOOM = 140, 122, 2.2        # the feet's box in figure units, and how much larger it is drawn
    cw, ch = FW * ZOOM, FH * ZOOM
    lab, gap, head, sep = 190, 12, 70, 22
    widths = [len(drawings) + 1 for _, _, drawings in SHOES]
    W, H = lab + sum(widths) * (cw + gap) + len(SHOES) * sep, head + len(CASES) * (ch + gap)
    cells = []
    x0 = lab
    for name, _today, _drawings in SHOES:
        n_cols = len(figs[(name, CASES[0][1])])
        cells.append(text(x0 + n_cols * (cw + gap) / 2, 26, name, 20, weight="bold"))
        box = (200 - FW / 2, grounds[name] - FH + 8, FW, FH)
        for i, (label, case) in enumerate(CASES):
            y = head + i * (ch + gap)
            if x0 == lab:
                cells.append(text(lab - 12, y + ch / 2, label, 15, anchor="end"))
            for n, (kind, svg) in enumerate(figs[(name, case)]):
                x = x0 + n * (cw + gap)
                if i == 0:
                    cells.append(text(x + cw / 2, 52, kind))
                cells.append(f'<rect x="{x}" y="{y}" width="{cw}" height="{ch}" fill="#f1eee8"/>')
                cells.append(cell(svg, box, x, y, cw, ch))
        x0 += n_cols * (cw + gap) + sep
    sheet = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">'
             f'<rect width="{W}" height="{H}" fill="#ffffff"/>{"".join(cells)}</svg>')
    (args.out / "on-figure-closeup.svg").write_text(sheet, encoding="utf-8")
    to_png(args.out / "on-figure-closeup.svg", args.out / "on-figure-closeup.png", (int(W), int(H)))

    # whole figures at phone size (about 0.8 px a unit, as the Today screen shows one): shorts above, trousers below
    PK = 0.8
    vb = view_box(figs[(SHOES[0][0], "shorts")][0][1])
    pw, ph = vb[2] * PK, vb[3] * PK
    pcells = []
    x0 = 10
    for name, _today, _drawings in SHOES:
        n_cols = len(figs[(name, "shorts")])
        pcells.append(text(x0 + n_cols * (pw + 6) / 2, 18, name, 13, weight="bold"))
        for r, case in enumerate(("shorts", "full")):
            y = 30 + r * (ph + 30)
            for n, (kind, svg) in enumerate(figs[(name, case)]):
                x = x0 + n * (pw + 6)
                pcells.append(cell(svg, view_box(svg), x, y, pw, ph))
                if r == 1:
                    pcells.append(text(x + pw / 2, y + ph + 16, kind, 11))
        x0 += n_cols * (pw + 6) + 24
    PW, PH = x0, 30 + 2 * (ph + 30)
    psheet = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {PW:.0f} {PH:.0f}" width="{PW:.0f}" '
              f'height="{PH:.0f}"><rect width="{PW:.0f}" height="{PH:.0f}" fill="#fbfaf7"/>{"".join(pcells)}</svg>')
    (args.out / "on-figure-phone.svg").write_text(psheet, encoding="utf-8")
    to_png(args.out / "on-figure-phone.svg", args.out / "on-figure-phone.png", (int(PW), int(PH)))
    print(f"wrote {args.out}/on-figure-closeup.png and on-figure-phone.png")


if __name__ == "__main__":
    main()
