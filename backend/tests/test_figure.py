"""The outfit drawn as worn (closet/drawing/figure.py) and the route that draws it (POST /api/outfits/figure)."""
import math
import re
import subprocess
import sys
from pathlib import Path

import pytest

from closet.drawing import figure as fig
from closet.drawing import fitting, illustrate
from closet.drawing.figure import CX, GROUND_Y, K_PX, LEG_CM, MARGIN, TOE_CM, WAIST_Y, Piece, figure, plan
from closet.drawing.templates import PX_CM
from closet.tagger.schema import Details, ItemTags, Silhouette

from .conftest import upload

BACKEND = Path(__file__).resolve().parents[1]


def answer(category: str, silhouette: dict | None = None, **details) -> dict:
    return ItemTags(
        category=category, category_confidence=0.9, color="navy", color_confidence=0.9, secondary_colors=[],
        pattern="solid", pattern_confidence=0.9, formality="casual", formality_confidence=0.9, season="all",
        season_confidence=0.9, silhouette=Silhouette.of(**(silhouette or {})), silhouette_confidence=0.9,
        details=Details.plain(**details), details_confidence=0.9, brand=None, size=None, material=None,
        needs_shot=None).model_dump(mode="json")


TEE = Piece("tee", answer("tee", {"sleeve": "short"}), "#f4f2ee")
SHIRT = Piece("shirt", answer("shirt", collar="point", placket="front_placket", cuff="barrel_1"), "#a9c3e0")
OVERSHIRT = Piece("shirt", answer("shirt", collar="point", placket="front_placket", pockets="chest_patch_double",
                                  weight="heavyweight"), "#7a5a3a")
SWEATER = Piece("sweater", answer("sweater", {"neck": "v"}), "#e8dfcb")
HOODIE = Piece("hoodie", None, "#8b8e92", silhouette={"neck": "hood"})
COAT = Piece("coat", answer("coat", {"top_length": "long"}, collar="notch_lapel", placket="front_placket"), "#232326")
JACKET = Piece("jacket", answer("jacket", collar="point", placket="zip_full"), "#2a3550")
TROUSERS = Piece("trousers", answer("trousers", {"leg": "straight", "pant_length": "full"}), "#6f7278")
JEANS = Piece("jeans", None, "#2c3a5a", silhouette={"leg": "tapered"})
SHORTS = Piece("shorts", None, "#6f7550")
BOOTS = Piece("boots", answer("boots", {"shoe_height": "high"}, shoe_style="boot"), "#6b4a32")
SNEAKERS = Piece("sneakers", None, "#e8edf0")

OUTFITS = {
    "coat, trousers and boots": dict(base=SHIRT, outer=COAT, bottom=TROUSERS, shoes=BOOTS),
    "tee, shorts and sneakers": dict(base=TEE, bottom=SHORTS, shoes=SNEAKERS),
    "three layers": dict(base=TEE, mid=OVERSHIRT, outer=COAT, bottom=JEANS, shoes=SNEAKERS),
    "a hoodie and a jacket": dict(base=SHIRT, mid=HOODIE, outer=JACKET, bottom=JEANS, shoes=BOOTS),
}


def test_tops_share_the_neck_and_shoulder_points():
    """The wearer sets the proportions: every regular top is fitted so its neck sits on his neck and each sleeve's
    shoulder seam on his shoulder point."""
    sp = {1: (CX + fig.SHOULDER_HALF_CM * K_PX, fig.SHOULDER_Y), -1: (CX - fig.SHOULDER_HALF_CM * K_PX, fig.SHOULDER_Y)}
    for name, pieces in OUTFITS.items():
        tops = [p for p in plan(pieces).pieces if p.place in ("base", "mid", "outer")]
        assert len({p.point(p.shape.anchors["neck"]) for p in tops}) == 1, name
        for p in tops:
            sleeves = fitting.sleeves(p.shape)
            assert {s.side for s in sleeves} == {1, -1}
            for s in sleeves:
                assert p.point(s.shoulder) == pytest.approx(sp[s.side], abs=0.5), (name, p.place)


@pytest.mark.parametrize("top", [SHIRT, OVERSHIRT, SWEATER, HOODIE, JACKET, COAT], ids=["shirt", "overshirt", "sweater", "hoodie", "jacket", "coat"])
def test_a_long_sleeve_ends_at_the_wrist(top):
    """Whatever the sleeve's length on the flat drawing, on him it ends round the wrist; a jacket's or coat's a
    little past it."""
    t = plan(dict(base=top, bottom=JEANS)).get("base")
    outer = fig._block_for({**fig.TOP_DEFAULTS, **t.spec.params}) in fig.OUTER_BLOCKS
    for s in fitting.sleeves(t.shape):
        start, d, length = fig._arm_line(s.side)
        cuff = t.point(s.cuff)
        along = ((cuff[0] - start[0]) * d[0] + (cuff[1] - start[1]) * d[1] - length) / K_PX   # cm past the wrist
        if outer:
            assert 0.5 <= along <= 2.5, (s.side, along)
        else:
            assert abs(along) <= 1.0, (s.side, along)


def test_a_short_sleeve_ends_above_the_elbow_and_fit_tags_still_show():
    tee = plan(dict(base=TEE, bottom=SHORTS)).get("base")
    for s in fitting.sleeves(tee.shape):
        assert tee.point(s.cuff)[1] < fig._y(fig.ELBOW_CM)
    # an oversized hoodie is fuller on him than a regular one; a slim tee narrower
    def body_half(piece):
        p = plan(dict(base=piece, bottom=JEANS)).get("base")
        return p.box(p.shape.body_box)[2] - CX
    big = Piece("hoodie", None, "#8b8e92", silhouette={"neck": "hood", "fit": "oversized"})
    slim = Piece("tee", None, "#f4f2ee", silhouette={"sleeve": "short", "fit": "slim"})
    assert body_half(big) > body_half(HOODIE) * 1.1
    assert body_half(slim) < body_half(TEE)


def test_an_open_layer_shows_what_is_under_it_and_a_closed_one_does_not():
    layout = plan(dict(base=SHIRT, mid=OVERSHIRT))
    assert layout.get("mid").open
    svg = figure(dict(base=SHIRT, mid=OVERSHIRT))
    # the overshirt's inside back, then the shirt, then its two fronts (drawn from a copy in the defs)
    back, shirt, fronts = svg.index('fill="#7a5a3a"', svg.index("</defs>")), svg.index('fill="#a9c3e0"', svg.index("</defs>")), svg.index('href="#qft1"')
    assert back < shirt < fronts

    layout = plan(dict(base=SHIRT, mid=SWEATER))
    assert not layout.get("mid").open                         # a pullover does not open
    svg = figure(dict(base=SHIRT, mid=SWEATER))
    body = svg[svg.index("</defs>"):]
    assert "href=\"#qft1\"" not in svg
    # the shirt is only drawn where it would show: below the sweater's hem and above its neck, and in its V
    before, after = body.split('fill="#e8dfcb"', 1)
    assert '<g clip-path="url(#vft1)">' in before and 'fill="#a9c3e0"' in before
    assert '<g clip-path="url(#nft1)">' in after


def test_a_layer_that_opens_only_partly_is_worn_closed():
    polo_over = Piece("polo", answer("polo", neckline="polo_collar", placket="polo"), "#27344f")
    assert not plan(dict(base=TEE, mid=polo_over)).get("mid").open
    assert not plan(dict(base=SHIRT)).get("base").open        # the base top is always closed


@pytest.mark.parametrize("top", [TEE, SHIRT, SWEATER, HOODIE, JACKET, Piece("sweater", None, "#888888", silhouette={"top_length": "cropped"}),
                                 Piece("tee", None, "#888888", silhouette={"top_length": "cropped", "fit": "slim"})],
                         ids=["tee", "shirt", "sweater", "hoodie", "jacket", "cropped sweater", "cropped slim tee"])
@pytest.mark.parametrize("bottom", [TROUSERS, JEANS, SHORTS], ids=["trousers", "jeans", "shorts"])
def test_the_top_hangs_over_the_waistband(top, bottom):
    layout = plan(dict(base=top, bottom=bottom))
    t, b = layout.get("base"), layout.get("bottom")
    waist = b.point(b.shape.anchors["waist"])
    assert waist[1] == pytest.approx(WAIST_Y)
    band_bottom = b.point((200, b.shape.anchors["waist"][1] + 6 * PX_CM))   # deeper than any waistband
    hem = t.point(t.shape.anchors["hem"])
    assert hem[1] > band_bottom[1] + 10
    corner = [float(v) for v in re.match(r"M (-?[\d.]+),(-?[\d.]+)", b.shape.outline).groups()]
    waist_half = 200 - b.point(corner)[0]
    assert t.box(t.shape.body_box)[2] - 200 > waist_half       # and is wider than it


@pytest.mark.parametrize("name", list(OUTFITS))
def test_every_piece_is_drawn_at_the_same_scale(name):
    layout = plan(OUTFITS[name])
    # the tops and the trousers are fitted to the wearer in place; everything else is drawn at his scale
    assert {round(p.px_per_cm, 6) for p in layout.pieces if p.place not in ("base", "mid", "outer", "bottom")} <= {round(K_PX, 6)}
    b = layout.get("bottom")
    assert b.point(b.shape.anchors["waist"])[1] == pytest.approx(WAIST_Y)
    assert b.point(b.shape.anchors["crotch"])[1] == pytest.approx(fig.CROTCH_Y)
    # a full-length trouser: the hem rests on the shoe, a break above the ground
    if b.spec.params.get("length", "full") == "full":
        assert b.point(b.shape.anchors["hem"])[1] == pytest.approx(fig.HEM_Y, abs=fig.DIP_CM * K_PX + 0.1)


@pytest.mark.parametrize("name", list(OUTFITS))
def test_shoes_stand_on_the_ground_under_the_legs(name):
    layout = plan(OUTFITS[name])
    shoes, b = layout.get("shoes"), layout.get("bottom")
    assert len(shoes.transforms) == 2                          # a pair
    full = b.spec.params.get("length", "full") == "full"
    hem_y = b.point(b.shape.anchors["hem"])[1]
    legs = ([b.point(b.shape.anchors[k])[0] for k in ("leg_l", "leg_r")] if full
            else [CX - LEG_CM * K_PX, CX + LEG_CM * K_PX])
    x0, y0, x1, y1 = shoes.front.bbox
    for copy, leg in enumerate(legs):                          # each ankle centred under its leg, toes on the ground
        sx = sorted(shoes.point((x, 0.0), copy)[0] for x in (x0, x1))
        assert shoes.point(shoes.front.anchors["ankle"], copy)[0] == pytest.approx(leg)
        assert shoes.point((0.0, 0.0), copy)[1] == pytest.approx(GROUND_Y + TOE_CM * K_PX)
        assert (sx[1] <= CX) if copy == 0 else (sx[0] >= CX)
    if full:   # a full-length hem covers the top of the shoe: the toe box and the front of the sole show below it
        assert shoes.point((0.0, y0), 0)[1] < hem_y < GROUND_Y
    # seen from the front, toes forward and turned out: the left shoe's toe is left of its heel, the right one's right
    toe, heel = shoes.front.anchors["toe"], shoes.front.anchors["heel"]
    assert shoes.point(toe, 0)[0] < shoes.point(heel, 0)[0] and shoes.point(toe, 1)[0] > shoes.point(heel, 1)[0]
    assert shoes.point(toe, 0)[1] > shoes.point(heel, 0)[1]   # the toe is nearer: lower on the page


def test_under_full_length_trousers_nothing_of_a_shoe_shows_beside_the_leg():
    layout = plan(dict(base=TEE, bottom=TROUSERS, shoes=BOOTS))
    b = layout.get("bottom")
    svg = figure(dict(base=TEE, bottom=TROUSERS, shoes=BOOTS), uid="q")
    (xo, hy), (xi, _) = b.point(b.shape.anchors["hem_out"]), b.point(b.shape.anchors["hem_in"])
    clip = re.search(r'<clipPath id="qk">(.*?)</clipPath>', svg).group(1)
    rects = [tuple(float(v) for v in r) for r in re.findall(r'x="([-\d.]+)" y="([-\d.]+)" width="([\d.]+)" height="([\d.]+)"', clip)]
    below, left, right = rects                                  # anywhere below the hem; above it, only in a leg
    assert below[1] == pytest.approx(hy, abs=0.1)
    assert left[0] == pytest.approx(xo, abs=0.1) and left[2] == pytest.approx(xi - xo, abs=0.1)
    assert left[1] + left[3] == pytest.approx(hy, abs=0.1) and right[0] == pytest.approx(2 * CX - xi, abs=0.1)
    assert 'clip-path="url(#qk)"' in svg
    # shorts leave the shoes whole
    assert "qk" not in figure(dict(base=TEE, bottom=SHORTS, shoes=BOOTS), uid="q")


@pytest.mark.parametrize("style,extra", [
    ("low_sneaker", {}), ("runner", {}), ("slip_on", {}), ("high_top", {}), ("loafer", {}), ("derby", {}), ("oxford", {}),
    ("boot", {}), ("chelsea_boot", {}), ("sandal", {"other_features": ["sandal"]}), ("sandal", {"other_features": ["slide"]}),
    ("sandal", {"other_features": ["flip_flop"]})])
def test_every_kind_of_shoe_is_drawn_from_the_front(style, extra):
    category = {"boot": "boots", "chelsea_boot": "boots", "sandal": "sandals", "loafer": "dress_shoes",
                "derby": "dress_shoes", "oxford": "dress_shoes"}.get(style, "sneakers")
    shoes = Piece(category, answer(category, shoe_style=style, **extra), "#6b4a32")
    for bottom in (TROUSERS, SHORTS):
        layout = plan(dict(base=TEE, bottom=bottom, shoes=shoes))
        placed = layout.get("shoes")
        assert placed.front is not None and placed.front.body and placed.front.outline.startswith("M ")
        assert placed.front.ankle                                # the wearer's ankle (a bare foot in a sandal) in it
        svg = figure(dict(base=TEE, bottom=bottom, shoes=shoes))
        assert all(f'<g transform="{fig._matrix(t)}"><path' in svg for t in placed.transforms)   # the pair, as drawn
        if style == "sandal":   # skin in the sandal: the bare foot
            assert fig.SKIN in placed.front.body.split("<path", 2)[2]


@pytest.mark.parametrize("name", list(OUTFITS))
def test_the_figure_fits_its_canvas_with_even_margins(name):
    layout = plan(OUTFITS[name])
    vx, vy, vw, vh = layout.view
    boxes = [p.box() for p in layout.pieces] + [layout.body.box]
    assert min(b[0] for b in boxes) - vx == pytest.approx(MARGIN)
    assert min(b[1] for b in boxes) - vy == pytest.approx(MARGIN)
    assert vx + vw - max(b[2] for b in boxes) == pytest.approx(MARGIN)
    assert vy + vh - max(b[3] for b in boxes) == pytest.approx(MARGIN)
    svg = figure(OUTFITS[name])
    assert svg.startswith("<svg") and f'viewBox="{vx:.1f} {vy:.1f} {vw:.1f} {vh:.1f}"' in svg
    # every garment's outline (curve handles included) is on the canvas, clear of its edge
    for p in layout.pieces:
        for copy in range(len(p.transforms)):
            for x, y in re.findall(r"(-?[\d.]+),(-?[\d.]+)", p.shape.outline):
                px, py = p.point((float(x), float(y)), copy)
                assert vx + 4 <= px <= vx + vw - 4 and vy + 4 <= py <= vy + vh - 4


def test_a_knee_length_coat_with_boots_fits_too():
    # the tagger has no knee length yet, but the template does: the figure has room for it
    from closet.drawing.illustrate import Fill, Spec
    coat = fig._place("outer", Spec("top", dict(neck="collar", collar="notch", front="buttons", block="coat", length="knee"),
                                    Fill("solid", "#232326")))
    layout = plan(dict(base=SHIRT, bottom=TROUSERS, shoes=BOOTS))
    layout.pieces.insert(1, coat)
    layout.fit()
    assert coat.open and coat.point(coat.shape.anchors["hem"])[1] > WAIST_Y + 50 * K_PX
    assert GROUND_Y > coat.box()[3]
    vx, vy, vw, vh = layout.view
    for p in layout.pieces:
        x0, y0, x1, y1 = p.box()
        assert vx + MARGIN - 0.01 <= x0 and x1 <= vx + vw - MARGIN + 0.01 and vy + MARGIN - 0.01 <= y0 and y1 <= vy + vh - MARGIN + 0.01
    assert "<svg" in fig._svg(layout, "k")


def test_missing_and_odd_pieces_do_not_raise():
    for pieces in (None, {}, {"base": None}, {"hat": TEE}, {"base": "a tee"}, {"base": Piece()},
                   {"base": Piece("bag")}, {"shoes": TEE, "bottom": BOOTS},
                   {"base": Piece("tee", answer="not json")}, {"base": Piece("tee", answer={"category": "tee", "details": {"neckline": "odd"}})},
                   {"base": Piece("tee", color_hex="url(javascript:x)", silhouette={"sleeve": "tentacle"})}):
        svg = figure(pieces)
        assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert plan({"shoes": TEE, "bottom": BOOTS}).pieces == []           # the wrong kind for its place is left out
    assert "javascript" not in figure({"base": Piece("tee", color_hex="url(javascript:x)")})
    # only what is given is drawn
    assert [p.place for p in plan(dict(bottom=JEANS, shoes=SNEAKERS)).pieces] == ["bottom", "shoes"]


def test_a_piece_that_cannot_be_drawn_falls_back_to_the_plainest_of_its_category(monkeypatch):
    real = fig.build

    def build(template, params):
        if params.get("fit") == "oversized":
            raise ValueError("cannot draw this")
        return real(template, params)

    monkeypatch.setattr(fig, "build", build)
    monkeypatch.setattr(illustrate, "build", build)
    odd = Piece("hoodie", answer("hoodie", {"fit": "oversized"}, fit_detail="oversized"), "#8b8e92")
    layout = plan(dict(base=TEE, mid=odd))
    assert layout.get("mid") is not None and layout.get("mid").spec.params.get("fit") != "oversized"
    assert figure(dict(base=TEE, mid=odd)).startswith("<svg")

    def broken(template, params):
        raise ValueError("nothing can be drawn")

    monkeypatch.setattr(fig, "build", broken)
    monkeypatch.setattr(illustrate, "build", broken)
    assert plan(dict(base=TEE)).pieces == []
    assert figure(dict(base=TEE)).startswith("<svg")


def test_the_sheet_of_demo_figures_is_written(tmp_path):
    out = tmp_path / "sheet.svg"
    run = subprocess.run([sys.executable, str(BACKEND.parent / "tools" / "make_figure_sheet.py"), str(out)],
                         capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr
    svg = out.read_text(encoding="utf-8")
    captions = re.findall(r"<text[^>]*>([^<]+)</text>", svg)
    assert len(captions) >= 8
    assert any("hot" in c.lower() and "shorts" in c.lower() for c in captions)
    assert any("cold" in c.lower() for c in captions) and any("mild" in c.lower() for c in captions)
    assert svg.count("<svg") == len(captions) + 1


def test_the_figure_needs_no_opencv():
    code = ("import sys\n"
            "from closet.drawing.figure import Piece, figure\n"
            "assert figure({'base': Piece('tee'), 'bottom': Piece('jeans'), 'shoes': Piece('boots')}).startswith('<svg')\n"
            "print('cv2' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


def test_a_print_lifted_from_the_photo_is_drawn_on_its_top_and_needs_no_opencv():
    code = ("import sys\n"
            "from dataclasses import replace\n"
            "from PIL import Image\n"
            "from closet.drawing import stored\n"
            "from closet.drawing.figure import Piece, figure\n"
            "kept = {'version': stored.VERSION, 'kind': 'plain',\n"
            "        'graphic': stored.graphic_part(Image.new('RGBA', (20, 20), (200, 30, 40, 255)), (0.4, 0.2, 0.6, 0.35))}\n"
            "g = stored.graphic_from(kept)\n"
            "tee, jeans = Piece('tee', color_hex='#f4f2ee'), Piece('jeans', color_hex='#2c3a5a')\n"
            "assert '<image' not in figure({'base': tee, 'bottom': jeans})\n"
            "assert figure({'base': replace(tee, graphic=g), 'bottom': jeans}).count('<image') == 1\n"
            "assert '<image' not in figure({'base': tee, 'bottom': replace(jeans, graphic=g)})\n"
            "print('cv2' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


# ------------------------------------------------------------------ the route

def test_the_figure_route_needs_login(anon):
    assert anon.post("/api/outfits/figure", json={"base": "x"}).status_code == 401


def test_the_figure_route_draws_the_open_closets_items(client):
    a, b = upload(client, key="a").json(), upload(client, key="b").json()
    assert client.patch(f"/api/items/{a['id']}", json={"category": "tee", "color": "red"}).status_code == 200
    assert client.patch(f"/api/items/{b['id']}", json={"category": "jeans", "color_hex": "#123456"}).status_code == 200
    r = client.post("/api/outfits/figure", json={"base": a["id"], "mid": None, "bottom": b["id"]})
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml")
    assert r.headers["cache-control"] == "no-store"
    assert r.text.startswith("<svg") and "#123456" in r.text
    # the request's shape
    for body, status in (([1], 422), ({}, 422), ({"base": None}, 422), ({"hat": a["id"]}, 422), ({"base": 3}, 422),
                         ({"base": "x" * 65}, 422), ({"base": "not-an-item"}, 422)):
        assert client.post("/api/outfits/figure", json=body).status_code == status, body
    assert client.post("/api/outfits/figure", content=b"{", headers={"content-type": "application/json"}).status_code == 400


def test_the_figure_follows_the_owners_corrections(client):
    a = upload(client, key="c").json()
    client.patch(f"/api/items/{a['id']}", json={"category": "shirt", "color_hex": "#aa0000"})
    first = client.post("/api/outfits/figure", json={"base": a["id"]}).text
    client.patch(f"/api/items/{a['id']}", json={"color_hex": "#00aa00"})
    second = client.post("/api/outfits/figure", json={"base": a["id"]}).text
    assert "#aa0000" in first and "#00aa00" in second and "#aa0000" not in second


def test_the_figure_route_keeps_demo_and_main_closets_apart(client):
    main_item = upload(client, key="d").json()
    client.patch(f"/api/items/{main_item['id']}", json={"category": "tee"})
    assert client.post("/api/outfits/figure", json={"base": main_item["id"]}).status_code == 200
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    demo = client.get("/api/items").json()
    demo_items = demo["items"] if isinstance(demo, dict) else demo
    by_cat = {it["category"]: it["id"] for it in demo_items}
    r = client.post("/api/outfits/figure", json={"base": by_cat["tee"], "outer": by_cat["coat"], "bottom": by_cat["jeans"],
                                                "shoes": by_cat["boots"]})
    assert r.status_code == 200 and r.text.startswith("<svg")
    assert client.post("/api/outfits/figure", json={"base": main_item["id"]}).status_code == 422   # not in the demo closet
    client.post("/api/profile", json={"profile": "main"})
    assert client.post("/api/outfits/figure", json={"base": by_cat["tee"]}).status_code == 422
    assert client.post("/api/outfits/figure", json={"base": main_item["id"]}).status_code == 200


# ------------------------------------------------------------------ accessories

BELT = Piece("belt", answer("belt", accessory="belt", accessory_kind="dress_belt"), "#5a3a22")
HAT = Piece("hat", answer("hat", accessory="brimmed_hat", accessory_kind="fedora"), "#555555")
SCARF = Piece("scarf", answer("scarf", accessory="scarf", accessory_kind="long_knit"), "#b8332e")
BAG = Piece("bag", answer("bag", accessory="bag", accessory_kind="tote"), "#c2a878")
TIE = Piece("other", answer("other", accessory="tie", accessory_kind="silk_woven"), "#27344f")


def test_each_accessory_is_placed_at_its_point_on_the_wearer():
    layout = plan(dict(base=TEE, bottom=JEANS, shoes=SNEAKERS, accessories=[BELT, HAT, SCARF, BAG, TIE]))
    got = {p.place: p for p in layout.pieces}
    assert [p for p in ("belt", "scarf", "hat", "bag") if p in got] == ["belt", "scarf", "hat", "bag"]
    assert "other" not in got and len(layout.pieces) == 7   # a tie is not drawn in the figure
    assert got["belt"].point(got["belt"].shape.anchors["waist"]) == pytest.approx((fig.CX, fig.BELT_Y))
    assert got["scarf"].point(got["scarf"].shape.anchors["neck"]) == pytest.approx((fig.CX, fig.NECK_Y))
    hx, hy = got["hat"].point(got["hat"].shape.anchors["head"])
    assert hx == pytest.approx(fig.CX) and hy == pytest.approx(fig.HAT_Y)
    assert got["hat"].box()[3] < fig.NECK_Y   # above the collar
    # the bag beside the figure, on the viewer's right, its handle at a hand's height
    right = max(p.box()[2] for p in layout.pieces if p.place != "bag")
    assert got["bag"].box()[0] > right
    assert got["bag"].point(got["bag"].shape.anchors["hand"])[1] == pytest.approx(fig._y(fig.WRIST_CM + 4))
    # each at the same scale as the clothes
    assert all(got[p].px_per_cm == K_PX for p in ("belt", "scarf", "hat", "bag"))


def test_a_belt_tucks_the_first_top_in_and_only_the_first_of_each_accessory_is_drawn():
    svg = figure(dict(base=TEE, bottom=JEANS, accessories=[BELT, Piece("belt", None, "#00ff00")]))
    assert "#5a3a22" not in svg or "#00ff00" not in svg
    assert 'clip-path="url(#kft0)"' in svg   # the tee is cut off at the belt
    alone = figure(dict(bottom=JEANS, accessories=[BELT]))   # on the trousers when there is no top
    assert alone.startswith("<svg") and "#kft0" not in alone


def test_odd_accessories_do_not_raise():
    for accessories in (None, "a bag", [None, 3, "x"], [TEE], [Piece("other")], [Piece("bag", answer="not json")],
                        [Piece("hat", color_hex="url(javascript:x)")]):
        svg = figure(dict(base=TEE, accessories=accessories))
        assert svg.startswith("<svg") and "javascript" not in svg
    assert [p.place for p in plan(dict(base=TEE, accessories=[TEE, Piece("other")])).pieces] == ["base"]


def test_the_figure_route_takes_accessories(client):
    a, b = upload(client, key="e").json(), upload(client, key="f").json()
    client.patch(f"/api/items/{a['id']}", json={"category": "tee"})
    client.patch(f"/api/items/{b['id']}", json={"category": "hat", "color_hex": "#654321"})
    r = client.post("/api/outfits/figure", json={"base": a["id"], "accessories": [b["id"]]})
    assert r.status_code == 200 and "#654321" in r.text
    assert client.post("/api/outfits/figure", json={"accessories": [b["id"]]}).status_code == 200
    assert client.post("/api/outfits/figure", json={"base": a["id"], "accessories": None}).status_code == 200
    for bad in ("x", [3], [""], ["x" * 65], ["not-an-item"], [b["id"]] * 9):
        assert client.post("/api/outfits/figure", json={"base": a["id"], "accessories": bad}).status_code == 422, bad


def _flat(d: str, t=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0), steps: int = 12) -> list[tuple[float, float]]:
    """The points along a path of absolute M, L, Q, C and Z commands, curves sampled, mapped by the matrix t."""
    a, b, c, dd, e, f = t
    out, cur = [], (0.0, 0.0)
    for cmd, args in re.findall(r"([MLQCZ])([^MLQCZ]*)", d):
        nums = [float(v) for v in re.findall(r"-?[\d.]+", args)]
        pts = list(zip(nums[0::2], nums[1::2], strict=True))
        if cmd in "ML":
            out += pts
        elif cmd == "Q":
            for i in range(0, len(pts), 2):
                p1, p2 = pts[i], pts[i + 1]
                out += [((1 - u) ** 2 * cur[0] + 2 * (1 - u) * u * p1[0] + u * u * p2[0],
                         (1 - u) ** 2 * cur[1] + 2 * (1 - u) * u * p1[1] + u * u * p2[1]) for u in (k / steps for k in range(1, steps + 1))]
                cur = p2
            continue
        elif cmd == "C":
            for i in range(0, len(pts), 3):
                p1, p2, p3 = pts[i:i + 3]
                out += [tuple((1 - u) ** 3 * q0 + 3 * (1 - u) ** 2 * u * q1 + 3 * (1 - u) * u * u * q2 + u ** 3 * q3
                              for q0, q1, q2, q3 in zip(cur, p1, p2, p3, strict=True)) for u in (k / steps for k in range(1, steps + 1))]
                cur = p3
            continue
        if pts:
            cur = pts[-1]
    return [(a * x + c * y + e, b * x + dd * y + f) for x, y in out]


def _inside(pt, poly) -> bool:
    """Inside the path as it is painted: SVG fills by the nonzero rule, so where a fitted sleeve lies over the
    edge of its body (the two share that line) the point is inside, as it is on the picture."""
    x, y = pt
    n, turns = len(poly), 0
    for i in range(n):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            turns += 1 if y1 > y0 else -1
    return turns != 0


def _clear(pt, poly, margin: float) -> bool:
    """Inside poly, at least `margin` from its edge."""
    return _inside(pt, poly) and all(_inside((pt[0] + dx, pt[1] + dy), poly)
                                     for dx, dy in ((margin, 0), (-margin, 0), (0, margin), (0, -margin)))


def test_the_wearer_is_drawn_first_behind_every_garment():
    for name, pieces in OUTFITS.items():
        svg = figure(pieces, uid="q")
        body = svg[svg.index("</defs>"):]
        first = re.search(r'rx="18" fill="[^"]+"/>(<[^>]+>)', body).group(1)
        assert first == '<g id="qm">', name
        group = body[body.index('<g id="qm">'):]
        assert group.index(f'fill="{fig.SKIN}"') < group.index(pieces["bottom"].color_hex)   # skin, then the clothes
    assert 'id="qm"' not in figure(dict(shoes=SNEAKERS), uid="q")   # shoes alone: nobody to wear them


def test_the_wearer_is_a_person_about_seven_and_a_half_heads_tall():
    layout = plan(dict(base=TEE, bottom=SHORTS, shoes=SNEAKERS))
    body = layout.body
    assert body.head and body.hair and len(body.ears) == 2 and len(body.arms) == 2 and len(body.hands) == 2
    assert len(body.legs) == 2
    head = _flat(body.head)
    top, chin = min(y for _, y in head), max(y for _, y in head)   # crown of the head (under the hair) to the chin
    assert chin < fig.NECK_Y and chin < layout.get("base").box()[1]   # the chin above the collar
    heads = (GROUND_Y - top) / (chin - top)
    assert 7.0 <= heads <= 8.0
    # the hands hang beside the thighs, clear of the trousers
    b = layout.get("bottom")
    for hand in body.hands:
        xs = [x for x, _ in _flat(hand)]
        assert min(xs) > b.box()[2] or max(xs) < b.box()[0]


def test_the_head_has_a_simple_face():
    svg = figure(OUTFITS["tee, shorts and sneakers"], uid="q")
    assert f'fill="{fig.EYE}"' in svg and fig.HAIR in svg
    # the head is drawn over the tops, before a scarf or a hat
    assert svg.rindex(fig.HAIR) > svg.index(TEE.color_hex)


def test_the_skin_colour_is_read_from_one_place(monkeypatch):
    monkeypatch.setattr(fig, "SKIN", "#123456")
    svg = figure(dict(base=TEE, bottom=SHORTS, shoes=Piece("sandals", answer("sandals", shoe_style="sandal"), "#6b4a32")), uid="q")
    assert "#123456" in svg and "#c68e6a" not in svg


@pytest.mark.parametrize("name", list(OUTFITS))
def test_the_shoes_are_on_the_feet(name):
    layout = plan(OUTFITS[name])
    shoes, body = layout.get("shoes"), layout.body
    ankle, edge = shoes.front.anchors["ankle"], shoes.front.anchors["ankle_r"]
    x0, _, x1, _ = shoes.front.bbox
    for copy, leg in enumerate(body.legs):
        end = shoes.point(ankle, copy)
        pts = _flat(leg)
        foot = [p for p in pts if p[1] > max(y for _, y in pts) - 1.5]   # the leg's end, across the ankle
        assert (min(x for x, _ in foot) + max(x for x, _ in foot)) / 2 == pytest.approx(end[0], abs=0.6)
        assert max(x for x, _ in foot) - min(x for x, _ in foot) == pytest.approx(2 * (edge[0] - ankle[0]), abs=0.6)
        assert min(shoes.point((x0, 0), copy)[0], shoes.point((x1, 0), copy)[0]) < end[0] < max(
            shoes.point((x0, 0), copy)[0], shoes.point((x1, 0), copy)[0])   # inside the shoe, across
        assert end[1] > shoes.point((0.0, shoes.front.bbox[1]), copy)[1]   # below the top of the shoe
    # no shoes: bare feet, drawn as the shoes would stand
    bare = plan(dict(base=TEE, bottom=SHORTS)).body
    assert bare.feet is not None and len(bare.feet[1]) == 2
    assert fig.SKIN in figure(dict(base=TEE, bottom=SHORTS), uid="q").split('<g id="qm">')[1]


@pytest.mark.parametrize("top", [SHIRT, COAT, JACKET, SWEATER], ids=["shirt", "coat", "jacket", "sweater"])
@pytest.mark.parametrize("bottom", [TROUSERS, JEANS], ids=["trousers", "jeans"])
def test_no_skin_shows_where_a_garment_covers_it(top, bottom):
    """The skin is drawn first and its outline LINE outside its paths; a garment's own outline reaches half its width
    outside the garment. So under a garment every point of the skin's paths lies at least that much inside it."""
    layout = plan(dict(base=top, bottom=bottom, shoes=SNEAKERS))
    body, t, b = layout.body, layout.get("base"), layout.get("bottom")
    margin = fig.LINE - 1.9
    cover = _flat(t.shape.outline, t.transforms[0])
    for arm in body.arms:   # a long sleeve covers the arm to the wrist; the hand comes out of the cuff
        for p in _flat(arm):
            assert _clear(p, cover, margin), (p, "arm")
    trousers = _flat(b.shape.outline, b.transforms[0])
    hem = b.point(b.shape.anchors["hem"])[1]
    for leg in body.legs:   # full-length trousers cover the legs down to the hem
        for p in _flat(leg):
            if p[1] < hem - margin:
                assert _clear(p, trousers, margin) or _clear(p, cover, margin), (p, "leg")
    for p in _flat(body.torso):   # the torso below the collar: under the top, or under the trousers below it
        if p[1] > fig.NECK_Y + 6 * K_PX:
            assert _clear(p, cover, margin) or _clear(p, trousers, margin), (p, "torso")


def test_he_has_an_average_build_with_shoulders_wider_than_hips():
    layout = plan(dict(base=SHIRT, bottom=TROUSERS, shoes=SNEAKERS))
    head = [x for x, _ in _flat(layout.body.head)]
    hw = (max(head) - min(head)) / K_PX
    shoulders, hips = 2 * fig.SHOULDER_HALF_CM / hw, 2 * fig.HIP_HALF_CM / hw
    assert 2.6 <= shoulders <= 2.8 and 1.9 <= hips <= 2.05
    assert 1.3 <= shoulders / hips <= 1.45                 # clearly broader at the shoulders than the hips
    # the trousers drawn over his hips stay well inside his shoulders
    b = layout.get("bottom")
    crotch = b.point(b.shape.anchors["crotch"])[1]
    waist = b.point(b.shape.anchors["waist"])[1]
    xs = [x for x, y in _flat(b.shape.outline, b.transforms[0]) if waist <= y <= crotch]
    assert 2 * fig.HIP_HALF_CM < (max(xs) - min(xs)) / K_PX <= 2 * fig.HIP_HALF_CM + 4   # his hips and a little ease
    assert (max(xs) - min(xs)) / K_PX / hw <= 2.2
    assert 2 * fig.SHOULDER_HALF_CM / ((max(xs) - min(xs)) / K_PX) >= 1.2


def _across(path: str, y: float) -> float:
    """How wide a closed path is at the height y (px)."""
    poly = _flat(path)
    xs = [x0 + (y - y0) * (x1 - x0) / (y1 - y0) for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1], strict=True)
          if (y0 > y) != (y1 > y)]
    return max(xs) - min(xs)


def test_his_neck_is_narrower_than_his_head_and_his_shoulders_slope():
    body = plan(dict(base=TEE, bottom=SHORTS, shoes=SNEAKERS)).body
    head = [x for x, _ in _flat(body.head)]
    hw = max(head) - min(head)
    for cm in (0.5, 2.0):   # under the chin: about six tenths of the head's width
        assert 0.55 <= _across(body.torso, fig.CHIN_Y + cm * K_PX) / hw <= 0.65
    # it flares into the slope of the shoulders: wider at its base, and the shoulder points lower than the neck's base
    assert _across(body.torso, fig.NECK_Y + 1.0 * K_PX) > 1.5 * _across(body.torso, fig.CHIN_Y + 2.0 * K_PX)
    drop = (fig.SHOULDER_Y - fig.NECK_Y) / ((fig.SHOULDER_HALF_CM - fig.NECK_HALF_CM) * K_PX)
    assert 0.25 <= drop <= 0.5   # a slope of about 15 to 25 degrees, not a flat bar
    # every top's shoulder line slopes with them
    t = plan(dict(base=SHIRT, bottom=JEANS)).get("base")
    for s in fitting.sleeves(t.shape):
        assert t.point(s.shoulder)[1] > t.point(t.shape.anchors["neck"])[1] + 15


def test_his_arms_hang_naturally_with_the_wrists_at_the_crotch():
    body = plan(dict(base=TEE, bottom=SHORTS, shoes=SNEAKERS)).body
    for side in (-1, 1):
        joint, elbow, wrist = fig._arm_points(side)
        assert abs(wrist[1] - fig.CROTCH_Y) <= 4 * K_PX                       # the wrist level with the crotch
        assert abs(joint[0] - CX) < fig.SHOULDER_HALF_CM * K_PX and joint[1] > fig.SHOULDER_Y   # the joint in the shoulder
        out = math.degrees(math.atan2(abs(elbow[0] - CX) - abs(joint[0] - CX), elbow[1] - joint[1]))
        fore = math.degrees(math.atan2(abs(wrist[0] - CX) - abs(elbow[0] - CX), wrist[1] - elbow[1]))
        assert 8 <= out <= 20                                                 # the upper arm a little out from the body
        assert -6 <= fore <= 0 and out - fore >= 8                            # a bend at the elbow, the forearm back in a touch
    # the elbow is at the waist, and the arm tapers from the shoulder to the wrist
    assert fig.CHEST_CM < fig.ELBOW_CM <= fig.WAIST_CM
    length = fig._arm_length()
    halves = [fig._arm_half(length * t) for t in (0.1, 0.3, 0.5, 1.0)]   # below the round of the shoulder
    assert halves[0] >= halves[1] > halves[2] > halves[3] and halves[0] >= 1.6 * halves[3]
    # the fingertips reach the middle of the thigh
    for hand in body.hands:
        tips = max(y for _, y in _flat(hand))
        assert 0.3 <= (tips - fig.CROTCH_Y) / (fig._y(fig.KNEE_CM) - fig.CROTCH_Y) <= 0.6


@pytest.mark.parametrize("top", [SHIRT, SWEATER, COAT], ids=["shirt", "sweater", "coat"])
def test_a_long_sleeve_bends_with_the_arm(top):
    """The sleeve goes round the arm all the way down, elbow included: its middle at the elbow is on the arm's."""
    t = plan(dict(base=top, bottom=JEANS)).get("base")
    for s in fitting.sleeves(t.shape):
        _, elbow, _ = fig._arm_points(s.side)
        poly = [t.point(q) for q in s.poly]
        xs = [x0 + (elbow[1] - y0) * (x1 - x0) / (y1 - y0) for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1], strict=True)
              if (y0 > elbow[1]) != (y1 > elbow[1])]
        assert (min(xs) + max(xs)) / 2 == pytest.approx(elbow[0], abs=1.5 * K_PX)
        assert max(xs) - min(xs) >= 2 * fig._arm_half(math.dist(fig._arm_points(s.side)[0], elbow)) + K_PX   # with ease


def _sleeve_across(t, s, y: float) -> tuple[float, float]:
    """A fitted sleeve's two edges at the height y."""
    poly = [t.point(q) for q in s.poly]
    xs = [x0 + (y - y0) * (x1 - x0) / (y1 - y0) for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1], strict=True)
          if (y0 > y) != (y1 > y)]
    return min(xs), max(xs)


def test_a_sleeve_beside_the_body_shares_its_line():
    """Where a sleeve hangs against the body's side the two are one line, not two heavy ones side by side: the
    sleeve's inner edge is on the body's edge (within a pixel), from under the underarm to where the arm leaves it."""
    t = plan(dict(base=SHIRT, bottom=JEANS)).get("base")
    outline = _flat(t.shape.outline, t.transforms[0])
    for s in fitting.sleeves(t.shape):
        for cm in (62, 66, 70, 76):
            y = fig._y(cm)
            lo, hi = _sleeve_across(t, s, y)
            inner = hi if s.side < 0 else lo
            edges = [x0 + (y - y0) * (x1 - x0) / (y1 - y0) for (x0, y0), (x1, y1) in zip(outline, outline[1:] + outline[:1], strict=True)
                     if (y0 > y) != (y1 > y)]
            near = sorted(abs(x - inner) for x in edges)
            assert near[0] < 0.2 and near[1] < 1.2, (cm, near[:3])   # its own edge, and the body's on it


def test_an_oversized_hoodie_is_roomy_and_gathered_at_its_cuffs_and_hem():
    knit = dict(neckline="hood", cuff="rib_knit", hem="ribbed_band")
    big = Piece("hoodie", answer("hoodie", {"neck": "hood", "fit": "oversized"}, fit_detail="oversized", **knit), "#8b8e92")
    usual = Piece("hoodie", answer("hoodie", {"neck": "hood"}, **knit), "#8b8e92")
    loose, plain = (plan(dict(base=p, bottom=JEANS)).get("base") for p in (big, usual))

    def side(t, cm):   # the body's side at a height: the nearest edge to the middle
        y, poly = fig._y(cm), _flat(t.shape.outline, t.transforms[0])
        return min(abs(x0 + (y - y0) * (x1 - x0) / (y1 - y0) - CX) for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1], strict=True)
                   if (y0 > y) != (y1 > y))

    hem = (loose.point(loose.shape.anchors["hem"])[1] - fig.CROWN_Y) / K_PX
    assert side(loose, 62) == pytest.approx(side(loose, 72), abs=0.6 * K_PX)   # straight from the chest, not shaped at the waist
    assert side(loose, 62) > side(plain, 62) + 2 * K_PX                       # and roomy
    assert side(loose, hem - 2) < side(loose, 72) - 0.8 * K_PX                # the hem band draws it in
    for s, r in zip(fitting.sleeves(loose.shape), fitting.sleeves(plain.shape), strict=True):
        ex, ey = fig._arm_points(s.side)[1]

        def off(t, sl, ex=ex, ey=ey, side=s.side):   # how far the sleeve's outer edge is from the middle of the elbow
            return max(abs(x - ex) for x in _sleeve_across(t, sl, ey) if (x - ex) * side > 0)
        assert off(loose, s) > off(plain, r) + 0.8 * K_PX                     # a fuller sleeve: further off the arm
        cuff = math.dist(loose.point(s.outer), loose.point(s.inner))
        assert cuff < 0.75 * 2 * off(loose, s)                                # gathered in at the cuff
        assert loose.point(s.shoulder)[1] > plain.point(r.shoulder)[1] + K_PX   # a dropped shoulder seam
        start, d, length = fig._arm_line(s.side)                               # and it still ends at the wrist
        c = loose.point(s.cuff)
        assert abs((c[0] - start[0]) * d[0] + (c[1] - start[1]) * d[1] - length) <= 1.0 * K_PX
    # the hood lies on the shoulders behind the neck: up beside the jaw, and out past the neck
    hood = [q for part in loose.shape.behind for q in _flat(part.d, loose.transforms[0])]
    assert fig.CHIN_Y - 8 * K_PX < min(y for _, y in hood) < fig.CHIN_Y
    assert max(x for x, _ in hood) - CX > 2 * fig.NECK_HALF_CM * K_PX


SANDALS = [Piece("sandals", answer("sandals", shoe_style="sandal", other_features=[kind]), "#a87a4f") for kind in ("sandal", "slide", "flip_flop")]


@pytest.mark.parametrize("shoes", [None] + SANDALS, ids=["bare", "two straps", "slide", "flip-flop"])
def test_a_bare_foot_is_one_shape_with_the_leg(shoes):
    layout = plan(dict(base=TEE, bottom=SHORTS, **({"shoes": shoes} if shoes else {})))
    body = layout.body
    assert len(body.foot_paths) == 2
    svg = figure(dict(base=TEE, bottom=SHORTS, **({"shoes": shoes} if shoes else {})), uid="q")
    group = svg[svg.index('<g id="qm">'):]
    for leg, foot in zip(body.legs, body.foot_paths, strict=True):
        assert f'd="{foot}" fill="none" stroke=' in group and f'd="{leg}" fill="none" stroke=' in group   # outlined together
        lp, fp = _flat(leg), _flat(foot)
        end = max(y for _, y in lp)
        assert min(y for _, y in fp) < end - 3 * K_PX < end < max(y for _, y in fp)   # the leg runs on into the ankle
        y = end - 2 * K_PX                                   # there the two are as wide as each other, and in line
        assert _across(foot, y) == pytest.approx(_across(leg, y), abs=1.0)
        mids = [(min(x for x, yy in pts if abs(yy - y) < 3) + max(x for x, yy in pts if abs(yy - y) < 3)) / 2 for pts in (fp, lp)]
        assert mids[0] == pytest.approx(mids[1], abs=1.0)
        # the ankle is the narrowest part: below it the foot widens to the ball
        assert max(x for x, _ in fp) - min(x for x, _ in fp) > 1.25 * _across(foot, y)


@pytest.mark.parametrize("shoes", SANDALS, ids=["two straps", "slide", "flip-flop"])
def test_a_sandal_is_drawn_sole_then_foot_then_straps(shoes):
    front = plan(dict(base=TEE, bottom=SHORTS, shoes=shoes)).get("shoes").front
    drawn = fig.front_shoe(plan(dict(base=TEE, bottom=SHORTS, shoes=shoes)).get("shoes").spec, K_PX, uid="z",
                           ankle=fig._ankle(), toes=fig.TOE_LINE)
    body = drawn.body
    sole, skin, strap = body.index("<path"), body.index(f'fill="{fig.SKIN}"'), body.index('fill="#a87a4f"')
    assert sole < skin < strap
    assert 'clip-path="url(#zf)"' in body[strap - 400:] and f'<clipPath id="zf"><path d="{drawn.foot}"/>' in drawn.defs   # straps cut to the foot
    # the sole is under the foot and stands out round its front
    foot, shoe = _flat(front.foot), _flat(front.outline)
    ball = front.anchors["ball"][1]
    toes = [q for q in foot if q[1] > ball]
    assert toes and all(_inside(q, shoe) for q in toes)
    assert max(y for _, y in shoe) > max(y for _, y in foot) + 1.0
    assert min(x for x, _ in shoe) < min(x for x, _ in toes) - 1.0 and max(x for x, _ in shoe) > max(x for x, _ in toes) + 1.0


def test_the_toes_are_a_soft_row_of_five():
    front = plan(dict(base=TEE, bottom=SHORTS)).body.feet[0]
    pts = _flat(front.foot)
    ball = front.anchors["ball"]
    reach = [math.dist(q, ball) for q in pts if q[1] > ball[1] - 1.0]
    # five rounded toes: five places where the edge is furthest from the ball, the big toe's the furthest
    tips = [i for i in range(1, len(reach) - 1) if reach[i - 1] < reach[i] >= reach[i + 1]]
    assert len(tips) == 5
    assert len(front.toes) <= 4 and all(math.dist(*_flat(d)) < 0.8 * K_PX for d in front.toes)   # faint, short lines at most
    assert "ellipse" not in front.body and front.body.count("<path") <= 2 + len(front.toes)       # no nails, no claws


def test_his_hands_are_as_long_as_his_face():
    body = plan(dict(base=TEE, bottom=SHORTS, shoes=SNEAKERS)).body
    head, hair = _flat(body.head), _flat(body.hair)
    chin, left = max(y for _, y in head), min(x for x, _ in head)
    temple = max(y for x, y in hair if x < left + 2 * K_PX)   # the hairline at the side of the face
    face = chin - temple
    for hand in body.hands:
        pts = _flat(hand)
        length = max(math.dist(p, q) for p in pts for q in pts)
        assert 0.85 * face <= length <= 1.1 * face


def test_skin_shows_below_a_short_sleeve_and_shorts():
    layout = plan(dict(base=TEE, bottom=SHORTS, shoes=SNEAKERS))
    body, t, b = layout.body, layout.get("base"), layout.get("bottom")
    tee = _flat(t.shape.outline, t.transforms[0])
    for arm in body.arms:   # the forearm hangs out of the sleeve; the top of the arm is inside it
        pts = _flat(arm)
        assert any(not _inside(p, tee) for p in pts) and any(_inside(p, tee) for p in pts)
    hem = b.point(b.shape.anchors["hem"])[1]
    for leg in body.legs:
        assert max(y for _, y in _flat(leg)) > hem + 30 * K_PX


def test_the_chest_shows_in_an_open_top_worn_on_its_own():
    svg = figure(dict(mid=OVERSHIRT.__class__("shirt", answer("shirt", collar="point", placket="front_placket"), "#a9c3e0"),
                      bottom=JEANS), uid="q")
    body = svg[svg.index("</defs>"):]
    back = body.index('fill="#a9c3e0"')
    assert f'fill="{fig.SKIN}"' in body[back:] and '<use href="#qw"/>' in body[back:]   # skin in the opening, trousers over it


def test_the_figure_does_not_change_the_items_drawings():
    from closet.drawing import templates
    pants = templates.build("pants", {})
    assert {"waist", "crotch", "hem", "leg_l", "leg_r", "hem_out", "hem_in"} <= set(pants.anchors)
    assert pants.anchors["leg_l"][0] == pytest.approx((pants.anchors["hem_out"][0] + pants.anchors["hem_in"][0]) / 2)


FLAT_LAYS = [("tee", {"sleeve": "short"}), ("tee", {"sleeve": "short", "fit": "slim", "top_length": "cropped"}),
             ("shirt", {}), ("shirt", {"fit": "oversized", "sleeve": "short"}), ("sweater", {"neck": "v"}),
             ("hoodie", {"neck": "hood", "fit": "oversized"}), ("jacket", {}), ("coat", {"top_length": "long"}),
             ("coat", {"top_length": "knee"}), ("polo", {}), ("jeans", {"leg": "tapered"}), ("trousers", {"leg": "wide"}),
             ("chinos", {"leg": "straight", "pant_length": "ankle"}), ("shorts", {}), ("sneakers", {}),
             ("boots", {"shoe_height": "high"}), ("sandals", {}), ("dress_shoes", {})]


def test_fitting_garments_on_the_wearer_leaves_the_flat_drawings_byte_for_byte_alone():
    """The garments are fitted to the wearer only in the figure: the items' own drawings (closet tiles, the item
    page, the coverage sheets) are exactly what they were before the figure fitted them (digest taken at a389de3).
    A deliberate change to the item drawings (with DRAWING_VERSION raised) updates this digest."""
    import hashlib

    from closet.drawing.item import svg_from_fields
    h = hashlib.sha256()
    for category, silhouette in FLAT_LAYS:
        h.update((svg_from_fields(category, "#6b4a32", None, silhouette, uid="f") or "-").encode())
    assert h.hexdigest() == "17abe72e3e2f1df5c3168977260cac7f4579f3bcaeff231005f75236793b6616"
    # drawing a garment with its own template's shape passed in is drawing it as it is
    spec = plan(dict(base=SHIRT)).get("base").spec
    params = spec.params if not spec.weight or "weight" in spec.params else {**spec.params, "weight": spec.weight}
    assert illustrate._draw(spec, "line", "f") == illustrate._draw(spec, "line", "f", shape=illustrate.build(spec.template, params))
