"""The outfit drawn as worn (closet/drawing/figure.py) and the route that draws it (POST /api/outfits/figure)."""
import math
import re
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from closet.drawing import figure as fig
from closet.drawing import fitting, frontshoe, illustrate, templates, worn
from closet.drawing.figure import CX, GROUND_Y, K_PX, LEG_CM, MARGIN, TOE_CM, WAIST_Y, Piece, figure, plan
from closet.drawing.templates import PX_CM
from closet.tagger.schema import Details, ItemTags, Silhouette, drawing_for

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
    # a full-length trouser: the hem rests on the shoe, never lower than its length takes it (a break above the
    # ground), and not far above the shoe's opening
    if b.spec.params.get("length", "full") == "full":
        shoes = layout.get("shoes")
        rim = shoes.point(shoes.front.anchors["opening"])[1]
        assert rim - 2.5 * K_PX < b.point(b.shape.anchors["hem"])[1] <= fig.HEM_Y + fig.DIP_CM * K_PX + 0.1


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
    """A leg wide enough to drop over the boot hides its shaft: above the hem, the boot shows only within the leg."""
    wide = Piece("trousers", answer("trousers", {"pant_length": "full"}, leg_shape="wide"), "#6f7278")
    layout = plan(dict(base=TEE, bottom=wide, shoes=BOOTS))
    b = layout.get("bottom")
    svg = figure(dict(base=TEE, bottom=wide, shoes=BOOTS), uid="q")
    (xo, hy), (xi, _) = b.point(b.shape.anchors["hem_out"]), b.point(b.shape.anchors["hem_in"])
    clip = re.search(r'<clipPath id="qk">(.*?)</clipPath>', svg).group(1)
    rects = [tuple(float(v) for v in r) for r in re.findall(r'x="([-\d.]+)" y="([-\d.]+)" width="([\d.]+)" height="([\d.]+)"', clip)]
    below, left, right = rects                                  # anywhere below the hem; above it, only in a leg
    assert below[1] == pytest.approx(hy, abs=0.1)
    assert left[0] == pytest.approx(xo, abs=0.1) and left[2] == pytest.approx(xi - xo, abs=0.1)
    assert left[1] + left[3] == pytest.approx(hy, abs=0.1) and right[0] == pytest.approx(2 * CX - xi, abs=0.1)
    assert 'clip-path="url(#qk)"' in svg
    # shorts leave the shoes whole, and so does a leg resting on top of the shaft: the boot is outside it
    assert "qk" not in figure(dict(base=TEE, bottom=SHORTS, shoes=BOOTS), uid="q")
    assert "qk" not in figure(dict(base=TEE, bottom=TROUSERS, shoes=BOOTS), uid="q")


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
    assert "other" not in got and len(layout.pieces) == 7   # a tie is not a placed piece: `worn` draws it
    assert got["belt"].point(got["belt"].shape.anchors["waist"]) == pytest.approx((fig.CX, fig.BELT_Y))
    assert got["scarf"].point(got["scarf"].shape.anchors["neck"]) == pytest.approx((fig.CX, fig.NECK_Y))
    # the hat on his head: its band across the forehead, above the eyes, its crown over the top of his hair
    k = K_PX * fig.HEAD_CM / 23.5
    middle = fig.CHIN_Y - 11.75 * k
    hx, hy = got["hat"].point(got["hat"].shape.anchors["head"])
    assert hx == pytest.approx(fig.CX) and middle - 8 * k < hy < middle - 2 * k
    assert got["hat"].box()[1] < middle - 13.7 * k and got["hat"].box()[3] < middle   # covers the hair, not the eyes
    # the bag carried on him, not beside him: it reaches no further out than his arms
    right = max(p.box()[2] for p in layout.pieces if p.place != "bag")
    assert fig.CX < got["bag"].box()[0] and got["bag"].box()[2] < right + 30 * K_PX
    # each at the same scale as the clothes (the hat at his head's)
    assert all(got[p].px_per_cm == K_PX for p in ("belt", "scarf", "bag")) and got["hat"].px_per_cm == pytest.approx(k)


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


def small(accessory: str, kind: str, color: str = "#6e2633", **details) -> Piece:
    return Piece("other", answer("other", accessory=accessory, accessory_kind=kind, **details), color)


SMALL = dict(tie=small("tie", "silk_woven"), watch=small("watch", "dive", "#6b4a2f"),
             glasses=small("eyewear", "round", "#1f1f22"), square=small("pocket_square", "puff", "#b8332e"),
             socks=small("socks", "casual_crew", "#2e7d4f"))
BLAZER = Piece("jacket", answer("jacket", garment="sport_coat", collar="notch_lapel", placket="front_placket",
                                pockets="hip_flap_double"), "#3a3f4a")
LOAFERS = Piece("dress_shoes", answer("dress_shoes", shoe_style="loafer"), "#5a3a22")


def _worn(**pieces):
    layout = plan(pieces)
    return worn.dress(layout, layout.accessories, "w"), layout


def _at(markup: str) -> tuple[float, float]:
    x, y = re.search(r'translate\((-?[\d.]+),(-?[\d.]+)\)', markup).groups()
    return CX + float(x), float(y)


def test_a_tie_is_worn_under_a_collar_and_only_there():
    dressed, _ = _worn(base=SHIRT, bottom=TROUSERS, accessories=[SMALL["tie"]])
    knot = _at(dressed.tie)
    assert knot[0] == pytest.approx(CX) and fig.NECK_Y < knot[1] < fig.NECK_Y + 10 * K_PX   # just under the collar
    assert 'clip-path="url(#wxtck)"' in dressed.tie   # the collar drawn again over the knot
    svg = figure(dict(base=SHIRT, bottom=TROUSERS, accessories=[SMALL["tie"]]))
    assert "#6e2633" in svg and svg.index("#6e2633") < svg.index(f'fill="{fig.HAIR}"')   # under the head
    for pieces in (dict(base=TEE, bottom=TROUSERS), dict(base=BLAZER, bottom=TROUSERS), dict(bottom=TROUSERS)):
        assert _worn(**pieces, accessories=[SMALL["tie"]])[0].tie == ""   # no collar, an open one, no top
    # under a V-neck sweater it is drawn over the shirt and under the sweater
    svg = figure(dict(base=SHIRT, mid=SWEATER, bottom=TROUSERS, accessories=[SMALL["tie"]]))
    assert svg.index("#6e2633") < svg.index("#e8dfcb", svg.index("#6e2633"))


def test_a_watch_is_worn_on_the_wrist_unless_a_sleeve_covers_it():
    dressed, _ = _worn(base=TEE, bottom=SHORTS, accessories=[SMALL["watch"]])
    wx, wy = fig._arm_points(+1)[2]
    x, y = _at(dressed.over)
    assert x == pytest.approx(wx, abs=0.1) and wy - 2 * K_PX < y < wy
    assert _worn(base=SHIRT, bottom=SHORTS, accessories=[SMALL["watch"]])[0].over == ""


def test_glasses_are_worn_on_the_eyes():
    dressed, layout = _worn(base=TEE, bottom=SHORTS, accessories=[SMALL["glasses"]])
    x, y = _at(dressed.over)
    eyes = [fitting.points(d) for d in layout.body.eyes]
    ey = sum(sum(q[1] for q in e) / len(e) for e in eyes) / len(eyes)
    assert x == pytest.approx(CX) and abs(y - ey) < 1.5 * K_PX


def test_a_pocket_square_stands_in_a_tailored_jackets_breast_pocket():
    dressed, layout = _worn(base=SHIRT, outer=BLAZER, bottom=TROUSERS, accessories=[SMALL["square"]])
    jacket = layout.get("outer")
    bx, by = jacket.point(jacket.shape.anchors["breast"])
    a, _, _, _, e, f = (float(v) for v in re.search(r"matrix\(([^)]*)\)", dressed.over).group(1).split(","))
    x = a * CX + e   # where the square's foot lands; worn open, the front (and the pocket on it) turns to its side
    assert f == pytest.approx(by, abs=0.1) and bx <= x < jacket.box(jacket.shape.body_box)[2] and 0.5 <= a < 1.0
    assert _worn(base=SHIRT, outer=JACKET, accessories=[SMALL["square"]])[0].over == ""   # not tailored
    assert _worn(base=SHIRT, accessories=[SMALL["square"]])[0].over == ""


def test_socks_show_above_low_shoes_when_the_trousers_stop_short():
    dressed, layout = _worn(base=TEE, bottom=SHORTS, shoes=SNEAKERS, accessories=[SMALL["socks"]])
    assert "#2e7d4f" in dressed.legs and "#2e7d4f" in (dressed.ankle or "")
    top = float(re.search(r'y"><path d="M -4000,([\d.]+)', "".join(dressed.defs)).group(1))
    assert fig._y(fig.CALF_CM) < top < GROUND_Y - 10 * K_PX   # a crew sock: up the shin, below the calf
    svg = figure(dict(base=TEE, bottom=SHORTS, shoes=SNEAKERS, accessories=[SMALL["socks"]]))
    assert svg.index("#2e7d4f") < svg.index("#6f7550")   # under the shorts
    for pieces in (dict(base=TEE, bottom=TROUSERS, shoes=SNEAKERS), dict(base=TEE, bottom=SHORTS),
                   dict(base=TEE, bottom=SHORTS, shoes=SANDALS[0])):
        d = _worn(**pieces, accessories=[SMALL["socks"]])[0]
        assert d.legs == "" and d.ankle is None
    no_show = small("socks", "no_show", "#2e7d4f")
    assert _worn(base=TEE, bottom=SHORTS, shoes=SNEAKERS, accessories=[no_show])[0].legs == ""
    otc = _worn(base=TEE, bottom=SHORTS, shoes=SNEAKERS, accessories=[small("socks", "dress_otc", "#2e7d4f")])[0]
    assert float(re.search(r'y"><path d="M -4000,([\d.]+)', "".join(otc.defs)).group(1)) < fig._y(fig.CALF_CM)


@pytest.mark.parametrize("fit", ["slim", "regular", "relaxed", "oversized"])
def test_small_accessories_sit_right_on_every_fit(fit):
    # a tie under the collar and ending above the belt, a watch at the wrist below a short sleeve, socks above low
    # shoes below shorts or cropped trousers, however the garments are fitted to him
    shirt = Piece("shirt", answer("shirt", collar="point", placket="front_placket", cuff="barrel_1", fit_detail=fit),
                  "#a9c3e0")
    dressed, _ = _worn(base=shirt, bottom=TROUSERS, accessories=[SMALL["tie"]])
    knot = _at(dressed.tie)
    assert knot[0] == pytest.approx(CX) and fig.NECK_Y < knot[1] < fig.NECK_Y + 10 * K_PX
    dressed, _ = _worn(base=_tee(fit), bottom=SHORTS, accessories=[SMALL["watch"]])
    wx, wy = fig._arm_points(+1)[2]
    x, y = _at(dressed.over)
    assert x == pytest.approx(wx, abs=0.1) and wy - 2 * K_PX < y < wy
    for leg in ("slim", "straight", "wide"):
        for bottom in (Piece("shorts", answer("shorts", {"pant_length": "short"}, leg_shape=leg), "#6f7550"),
                       Piece("trousers", answer("trousers", leg_shape=leg, trouser_break="cropped"), "#6f7278")):
            dressed, layout = _worn(base=_tee(fit), bottom=bottom, shoes=SNEAKERS, accessories=[SMALL["socks"]])
            assert "#2e7d4f" in dressed.legs, (leg, bottom.category)
            top = float(re.search(r'y"><path d="M -4000,([\d.]+)', "".join(dressed.defs)).group(1))
            hem = layout.get("bottom").box(layout.get("bottom").shape.body_box)[3]
            assert top < GROUND_Y - 10 * K_PX and (bottom.category == "trousers" or hem < top), (leg, hem, top)


def test_every_small_accessory_worn_at_once_draws_and_odd_ones_do_not_raise():
    pieces = dict(base=SHIRT, outer=BLAZER, bottom=SHORTS, shoes=LOAFERS, accessories=list(SMALL.values()))
    svg = figure(pieces)
    for colour in ("#6e2633", "#1f1f22", "#b8332e", "#2e7d4f"):
        assert colour in svg, colour
    assert "#6b4a2f" not in svg   # the watch is under the jacket's sleeve
    for kind in ("bow_tie", "knit"):
        assert figure(dict(base=SHIRT, accessories=[small("tie", kind)])).startswith("<svg")
    for accessories in ([small("tie", "silk_woven", "url(javascript:x)")], [Piece("other", None, "#123456")],
                        [Piece("other", answer("other", accessory="gloves", accessory_kind="knit"), "#123456")]):
        svg = figure(dict(base=SHIRT, bottom=SHORTS, shoes=SNEAKERS, accessories=accessories))
        assert svg.startswith("<svg") and "javascript" not in svg
    assert worn.dress(None, [SMALL["tie"]], "w") == worn.Worn()
    assert worn.dress(plan(dict(base=SHIRT)), "x", "w") == worn.Worn()


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
    # the hands hang beside the thighs: each hand's middle past the trousers (the owner, 18 November: arms hanging
    # nearly straight down may touch the trousers, rather than held out clear of them)
    b = layout.get("bottom")
    for hand in body.hands:
        xs = [x for x, _ in _flat(hand)]
        assert (min(xs) + max(xs)) / 2 > b.box()[2] or (min(xs) + max(xs)) / 2 < b.box()[0]


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
    # a sleeve is a tube round the arm, drawn over the body (the outline overlaps itself where a loose body's side
    # stands out past the arm, behind it)
    tubes = [_flat(d, t.transforms[0]) for d, _ in t.shape.sleeves]
    for arm in body.arms:   # a long sleeve covers the arm to the wrist; the hand comes out of the cuff
        for p in _flat(arm):
            assert _clear(p, cover, margin) or any(_clear(p, s, margin) for s in tubes), (p, "arm")
    trousers = _flat(b.shape.outline, b.transforms[0])
    hem = b.point(b.shape.anchors["hem"])[1]
    # a hem dropping over the shoe is held up in front of it: under it is the shoe (its opening, ankle and all,
    # still under the trousers), drawn over the legs, its outline as wide as theirs
    s = layout.get("shoes")
    shoes = [_flat(s.front.outline, s.transforms[i]) for i in range(2)]
    for leg in body.legs:   # full-length trousers cover the legs down to the hem
        for p in _flat(leg):
            if p[1] < hem - margin:
                assert (_clear(p, trousers, margin) or _clear(p, cover, margin)
                        or any(_inside(p, shoe) for shoe in shoes)), (p, "leg")
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
        # the arm hangs nearly straight down beside the body (the owner, 18 November: at 11 degrees out, with the
        # elbows out, he looked hunched with his arms in front of him): the upper arm a touch out, the forearm back
        assert 3 <= out <= 8
        assert -6 <= fore <= 0 and out - fore >= 3
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
    sleeve's inner edge is on the body's edge (within a pixel), from under the underarm to where the arm leaves it;
    or, where the body has room at its sides, the body's edge is under the sleeve, behind the arm, never beside it."""
    t = plan(dict(base=SHIRT, bottom=JEANS)).get("base")
    outline = _flat(t.shape.outline, t.transforms[0])
    for s in fitting.sleeves(t.shape):
        for cm in (62, 66, 70, 76):
            y = fig._y(cm)
            lo, hi = _sleeve_across(t, s, y)
            inner = hi if s.side < 0 else lo
            edges = [x0 + (y - y0) * (x1 - x0) / (y1 - y0) for (x0, y0), (x1, y1) in zip(outline, outline[1:] + outline[:1], strict=True)
                     if (y0 > y) != (y1 > y)]
            near = sorted(edges, key=lambda x, inner=inner: abs(x - inner))
            own, body = near[0], near[1]
            # its own edge, and the body's on it, or under the sleeve: a loose body's side is behind the arm
            assert abs(own - inner) < 0.2 and (abs(body - inner) < 1.2 or lo <= body <= hi), (cm, own, body, lo, hi)


def test_a_sleeve_is_as_wide_as_the_arm_and_an_ease_by_fit():
    """The sleeve's width comes from the arm and the top's fit, not from the flat drawing: at the middle of the upper
    arm a slim top's sleeve stands closest to the arm, then a regular one, a jacket, a jacket worn as the outer
    layer, an oversized top; and every long sleeve is narrower at its cuff than at the upper arm."""
    knit = dict(neckline="hood", cuff="rib_knit", hem="ribbed_band")
    tops = [("base", Piece("shirt", None, "#a9c3e0", silhouette={"fit": "slim"})), ("base", SHIRT), ("base", JACKET),
            ("outer", JACKET),
            ("base", Piece("hoodie", answer("hoodie", {"neck": "hood", "fit": "oversized"}, fit_detail="oversized", **knit), "#8b8e92"))]
    eases = []
    for place, piece in tops:
        t = plan({place: piece, "bottom": JEANS}).get(place)
        for s in fitting.sleeves(t.shape):
            joint, elbow, _ = fig._arm_points(s.side)
            mid = ((joint[0] + elbow[0]) / 2, (joint[1] + elbow[1]) / 2)
            along = math.dist(joint, mid)
            lo, hi = _sleeve_across(t, s, mid[1])
            off = (hi - mid[0]) if s.side > 0 else (mid[0] - lo)          # the outer edge, from the middle of the arm
            ease = off - fig._arm_half(along)
            cuff = math.dist(t.point(s.outer), t.point(s.inner))
            assert cuff < 2 * off - K_PX, (place, piece.category)           # narrower at the cuff than at the upper arm
            assert cuff < 2 * (fig.ARM_HALVES[-1][1] + 1.5) * K_PX          # and close to the wrist
        eases.append(ease / K_PX)
    assert all(a + 0.3 < b for a, b in zip(eases, eases[1:], strict=False)), eases
    assert 0.4 <= eases[0] <= 0.9 and 0.9 <= eases[1] <= 1.6 and 1.4 <= eases[2] <= 2.1 and 1.9 <= eases[3] <= 2.6 and eases[4] >= 2.5


def test_an_oversized_hoodie_is_roomy_and_gathered_at_its_cuffs_and_hem():
    knit = dict(neckline="hood", cuff="rib_knit", hem="ribbed_band")
    big = Piece("hoodie", answer("hoodie", {"neck": "hood", "fit": "oversized"}, fit_detail="oversized", **knit), "#8b8e92")
    usual = Piece("hoodie", answer("hoodie", {"neck": "hood"}, **knit), "#8b8e92")
    loose, plain = (plan(dict(base=p, bottom=JEANS)).get("base") for p in (big, usual))

    def side(t, cm):   # the body's side at a height (px)
        return _side(t, cm) * K_PX

    hem = (loose.point(loose.shape.anchors["hem"])[1] - fig.CROWN_Y) / K_PX
    # straight from the chest, not shaped at the waist (above 68 cm its side runs in to the underarm, behind the
    # sleeve: the sleeve is a tube round the arm, in front of the loose body)
    assert side(loose, 68) == pytest.approx(side(loose, 78), abs=0.6 * K_PX)
    assert side(loose, 68) > side(plain, 68) + 2 * K_PX                       # and roomy
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


LOW_SHOES = [Piece(c, answer(c, shoe_style=s), "#5a3a22") for c, s in
             (("sneakers", "low_sneaker"), ("sneakers", "runner"), ("sneakers", "slip_on"), ("dress_shoes", "loafer"),
              ("dress_shoes", "derby"), ("dress_shoes", "oxford"))]


@pytest.mark.parametrize("footwear,lacing,pairs", [
    ("service_boot", "d_rings", 7),
    ("service_boot", "speed_hooks", 3),
    ("logger_boot", "na", 4),
])
def test_front_shoes_draw_lacing_hardware_on_the_upper(footwear, lacing, pairs):
    spec = fig._spec(Piece("boots", answer("boots", footwear=footwear, lacing=lacing), "#765432"))
    plain = replace(spec, params={k: v for k, v in spec.params.items() if k not in ("rings", "hooks")})
    drawn = fig.front_shoe(spec, K_PX, uid="z", ankle=fig._ankle())
    assert drawn.body != fig.front_shoe(plain, K_PX, uid="z", ankle=fig._ankle()).body
    hardware = re.findall(r'<path d="([^"]+)" fill="none" stroke="' + frontshoe.METAL + '"', drawn.body)
    assert len(hardware) == 2 * pairs
    assert all(_inside(point, _flat(drawn.outline)) for path in hardware for point in _flat(path))
    assert drawn.body.index('clip-path="url(#za)"') < drawn.body.index(f'stroke="{frontshoe.METAL}"')


@pytest.mark.parametrize("footwear,lacing", [
    ("service_boot", "d_rings"),
    ("service_boot", "speed_hooks"),
    ("logger_boot", "na"),
])
@pytest.mark.parametrize("eyelets", [3, 5, 8])
def test_front_shoe_hardware_does_not_overlap_even_with_its_outline(footwear, lacing, eyelets):
    spec = fig._spec(Piece("boots", answer("boots", footwear=footwear, lacing=lacing), "#765432"))
    spec = replace(spec, params={**spec.params, "eyelets": eyelets})
    drawn = fig.front_shoe(spec, K_PX, uid="z", ankle=fig._ankle())
    paths = re.findall(r'<path d="([^"]+)" fill="none" stroke="([^"]+)" stroke-width="([^"]+)"', drawn.body)
    boxes = []
    for i, (path, colour, _) in enumerate(paths):
        if colour != frontshoe.METAL:
            continue
        assert paths[i - 1][0] == path and paths[i - 1][1] == illustrate.INK
        pad = float(paths[i - 1][2]) / 2   # the dark outline counts as hardware too
        points = _flat(path)
        boxes.append((min(x for x, _ in points) - pad, min(y for _, y in points) - pad,
                      max(x for x, _ in points) + pad, max(y for _, y in points) + pad))
    assert boxes
    for i, (x0, y0, x1, y1) in enumerate(boxes):
        for a0, b0, a1, b1 in boxes[i + 1:]:
            assert x1 < a0 or a1 < x0 or y1 < b0 or b1 < y0
    laces = [_flat(path) for i, (path, colour, width) in enumerate(paths[:-1])
             if colour == illustrate.INK and float(width) == 2.8
             and paths[i + 1][0] == path and float(paths[i + 1][2]) == 1.5]
    assert len(laces) == max(3, min(7, eyelets)) - 1 + 3
    for i, (_, y0, x1, y1) in enumerate(boxes):
        ends = [lace[0 if i % 2 == 0 else -1] for lace in laces]
        own = min(range(len(ends)), key=lambda j: abs(ends[j][1] - (y0 + y1) / 2))
        if lacing == "speed_hooks":
            assert own >= len(laces) - 3   # all three hooks belong to the shaft, not the vamp
        for j, (_, y) in enumerate(ends):
            if j != own:   # also clear the ordinary eyelet rows below the lowest logger hook
                assert y1 < y - 1.4 or y0 > y + 1.4
        if i % 2 == 0:
            # The middle half of every lace crossing remains clear of both pieces of hardware.
            left, right = laces[own][0][0], laces[own][-1][0]
            assert x1 < left + (right - left) / 4
            assert boxes[i + 1][0] > right - (right - left) / 4


def test_front_shoe_d_rings_have_a_flat_side_towards_the_lace():
    spec = fig._spec(Piece("boots", answer("boots", footwear="service_boot", lacing="d_rings"), "#765432"))
    drawn = fig.front_shoe(spec, K_PX)
    rings = re.findall(r'<path d="([^"]+)" fill="none" stroke="' + frontshoe.METAL + '"', drawn.body)
    assert len(rings) == 14
    for i in range(0, len(rings), 2):
        for side, path in zip((-1, 1), rings[i:i + 2], strict=True):
            points = _flat(path)
            # Closing the outer semicircle makes the straight, inward-facing side of the D.
            assert path.endswith("Z")
            assert points[0][0] == points[-1][0]
            assert points[0][1] < points[-1][1]
            assert all(side * (x - points[0][0]) >= -0.01 for x, _ in points)


def test_front_shoes_draw_a_toggle_and_its_two_cord_ends():
    spec = fig._spec(Piece("sneakers", answer("sneakers", footwear="trail_runner", lacing="toggle_speed_lace"), "#765432"))
    plain = replace(spec, params={k: v for k, v in spec.params.items() if k != "toggle"})
    drawn = fig.front_shoe(spec, K_PX, uid="z", ankle=fig._ankle())
    assert drawn.body != fig.front_shoe(plain, K_PX, uid="z", ankle=fig._ankle()).body
    lock = re.search(r'<rect x="([^"]+)" y="([^"]+)" width="([^"]+)" height="([^"]+)" rx="1" fill="' + illustrate.INK, drawn.body)
    assert lock is not None
    x, y, w, h = map(float, lock.groups())
    assert all(_inside(p, _flat(drawn.outline)) for p in ((x, y), (x + w, y + h)))
    tails = re.findall(r'<path d="([^"]+)" fill="none" stroke="[^"]+" stroke-width="1.5"[^>]*>', drawn.body[:lock.start()])
    assert len(tails) >= 2
    for tail in tails[-2:]:
        points = _flat(tail)
        assert len(points) >= 2 and points[-1][1] > points[0][1]
        assert all(_inside(p, _flat(drawn.outline)) for p in points)


@pytest.mark.parametrize("shoes", LOW_SHOES, ids=lambda p: p.answer["details"]["shoe_style"])
@pytest.mark.parametrize("socks", [None, "no_show", "casual_crew"])
@pytest.mark.parametrize("bottom", [SHORTS, Piece("trousers", answer("trousers", leg_shape="slim", trouser_break="cropped"),
                                                   "#6f7278")], ids=["shorts", "cropped"])
def test_the_back_of_a_low_shoes_collar_is_behind_the_ankle(shoes, socks, bottom):
    """Seen from the front and a little above, the top of a low shoe's heel counter stands up behind the ankle: it
    is drawn first, the ankle (or sock) over it, and only the collar's sides show beside the ankle."""
    accessories = [small("socks", socks)] if socks else []
    spec = plan(dict(base=TEE, bottom=bottom, shoes=shoes, accessories=accessories)).get("shoes").spec
    drawn = fig.front_shoe(spec, K_PX, uid="z", ankle=fig._ankle(), toes=fig.TOE_LINE)
    body = drawn.body
    upper, ankle = body.index(f'fill="{spec.fill.color}"'), body.index('clip-path="url(#za)"')
    assert upper < ankle   # the shoe, back of the collar and all, then the ankle
    style = spec.params["style"]
    _, sole_t, table, _ = frontshoe.STYLES[style]
    view = frontshoe._View(K_PX)
    back = view(0.0, 0.0, sole_t + frontshoe._interp(table, 0.0) - 0.6)   # the top of the heel counter, at the back
    seen = _flat(body.split('<clipPath id="za"><path d="')[1].split('"')[0])
    assert _inside(back, seen)   # the ankle is drawn over it ...
    column = _flat(frontshoe._path(frontshoe._hull(frontshoe._column(view, sole_t + 2.0, sole_t + frontshoe.ANKLE_CM))))
    assert _inside(back, column)   # ... and there is ankle there
    toe = view(0.0, 0.6, sole_t + frontshoe._interp(table, 0.6) - 0.3)   # the vamp is still in front of it
    assert not _inside(toe, seen)


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


def _arm_clip(svg: str, uid: str = "q") -> list[list[tuple[float, float]]]:
    """Where the arms are drawn again over the clothes: the clip path of their group, one area for each side."""
    d = re.search(rf'<clipPath id="{uid}rb"><path d="([^"]+)"', svg).group(1)
    return [_flat(part) for part in re.findall(r"M[^Z]+Z", d.replace("M", " M").strip().replace(" M", "M"))]


BIG_TEE = Piece("tee", answer("tee", fit_detail="oversized", sleeve_length="short", neckline="crew"), "#f4f2ee")


@pytest.mark.parametrize("pieces", [dict(base=BIG_TEE, bottom=TROUSERS),
                                    dict(base=SHIRT, mid=SWEATER, outer=COAT, bottom=TROUSERS, shoes=BOOTS),
                                    dict(base=TEE, mid=Piece("hoodie", None, "#8b8e92", silhouette={"neck": "hood", "fit": "oversized"}),
                                         bottom=JEANS)],
                         ids=["oversized tee", "open coat", "oversized hoodie"])
def test_the_arms_are_drawn_after_a_loose_bodys_sides_and_before_the_sleeves(pieces):
    """The depth order: a garment's body is a shell round him, so what of it stands out past his sides is behind his
    arms; a sleeve is a tube round the arm, in front of it. The arms are drawn again after every top, and that copy
    is masked out wherever a sleeve is, so a sleeve stays over the arm."""
    svg = figure(pieces, uid="q")
    body = svg[svg.index("</defs>"):]
    arms = body.index('<g id="qa" mask="url(#qr)">')
    for place in ("base", "mid", "outer"):
        if place in pieces:   # every top first, none of them after the arms
            assert f'fill="{pieces[place].color_hex}"' in body[:arms]
            assert f'fill="{pieces[place].color_hex}"' not in body[arms:body.index(fig.HAIR)]
    mask = re.search(r'<mask id="qr"[^>]*>(.*?)</mask>', svg).group(1)
    tops = [p for p in plan(pieces).pieces if p.place in ("base", "mid", "outer")]
    for p in tops:   # each sleeve cut out of the arms drawn again
        for d, _ in p.shape.sleeves:
            assert f'<path d="{d}" transform="{fig._matrix(p.transforms[0])}" fill="#000"' in mask


def test_the_forearm_shows_below_an_oversized_tees_sleeve_over_its_roomy_body():
    """An oversized tee: a dropped shoulder, a wide sleeve to near the elbow and a roomy body falling straight. Below
    the sleeve, beside his torso, the arm is over the tee's loose side (inside the tee's outline, in no sleeve, and
    where the arms are drawn again), and the forearm hangs out of the sleeve."""
    pieces = dict(base=BIG_TEE, bottom=TROUSERS)
    layout = plan(pieces)
    t, wearer = layout.get("base"), layout.body
    tee, tubes = _flat(t.shape.outline, t.transforms[0]), [_flat(d, t.transforms[0]) for d, _ in t.shape.sleeves]
    clip = _arm_clip(figure(pieces, uid="q"))
    for arm in wearer.arms:
        pts = _flat(arm)
        below = [p for p in pts if fig._y(fig.ELBOW_CM + 2) < p[1] < fig._y(fig.ELBOW_CM + 8)]
        assert below
        # over the tee's loose side, not in its sleeve, and drawn again there
        over = [p for p in below if _inside(p, tee) and not any(_inside(p, s) for s in tubes)]
        assert over and all(any(_inside(p, c) for c in clip) for p in over)
        assert any(_inside(p, s) for p in pts for s in tubes)   # the upper arm in the sleeve
        assert max(y for _, y in pts) > max(t.point(s.cuff)[1] for s in fitting.sleeves(t.shape)) + 15 * K_PX


def test_an_open_coat_shows_him_and_his_trousers_between_its_fronts_not_a_flat_fill():
    """Between an open coat's fronts is what is in front of its back: him (drawn again within its outline), his
    trousers and shoes, then the layers under the coat; its lining only shows at the edges, past him."""
    svg = figure(dict(base=SHIRT, mid=SWEATER, outer=COAT, bottom=TROUSERS, shoes=BOOTS), uid="q")
    body = svg[svg.index("</defs>"):]
    coat = body.index(f'fill="{COAT.color_hex}"')
    inner = body.index('<g clip-path="url(#oqt2)"><use href="#qm"/><use href="#qp"/><use href="#qw"/></g>')
    assert coat < inner < body.index(f'fill="{SWEATER.color_hex}"', inner) < body.index('href="#qqt2"')   # then its fronts
    assert '<clipPath id="oqt2">' in svg


def test_a_slim_tee_hugs_him_and_a_regular_one_has_room_at_the_sides():
    """Told apart at a glance: the slim tee follows the chest and waist, the regular one falls straight from the
    chest with room at the sides, and its sleeve is a wider tube."""
    slim, regular = (plan(dict(base=_tee(f), bottom=TROUSERS)).get("base") for f in ("slim", "regular"))
    for cm in (65.0, 75.0):
        assert _side(regular, cm) > _side(slim, cm) + 2.5, cm
    y = fig._y(57.0)
    wide = [_sleeve_across(t, next(s for s in fitting.sleeves(t.shape) if s.side == 1), y)[1] for t in (slim, regular)]
    assert wide[1] > wide[0] + 0.5 * K_PX


SCARVES = {kind: Piece("scarf", answer("scarf", accessory="scarf", accessory_kind=kind), "#b8332e")
           for kind in ("long_knit", "woven_wool", "silk")}
RUCKSACK = Piece("bag", answer("bag", accessory="bag", accessory_kind="rucksack"), "#3b4a3a")


@pytest.mark.parametrize("kind", list(SCARVES))
@pytest.mark.parametrize("coat", ["open", "none"])
def test_a_scarf_wraps_round_his_neck_in_depth(kind, coat):
    """A wrapped scarf is a band round his neck, drawn at its depths: the part going round the back of his neck
    before his neck and head; then the bag's straps on his chest; then the scarf's under end, the band across his
    throat, and the end that comes over it, before the hat. Its band is whole: no hole for the chin and collar."""
    tops = dict(base=SHIRT, mid=SWEATER, outer=COAT) if coat == "open" else dict(base=SHIRT, mid=SWEATER)
    pieces = dict(**tops, bottom=TROUSERS, shoes=BOOTS, accessories=[SCARVES[kind], RUCKSACK, HAT])
    layout = plan(pieces)
    svg = figure(pieces, uid="q")
    body = svg[svg.index("</defs>"):]
    straps = worn.dress(layout, layout.accessories, "q").carry
    assert straps and straps in body
    at = {layer: body.index(f'"url(#cqc{layer[0]})"') for layer in templates.SCARF_LAYERS}   # each layer's clip
    assert body.index('<g id="qa"') < at["back"] < body.index(fig.HAIR) < body.index(straps)
    assert body.index(straps) < at["under"] < at["front"] < at["over"] < body.rindex("#555555")
    front = templates.scarf(style=layout.get("scarf").spec.params["style"], worn=True, layer="front")
    assert not [part for part in front.parts if part.role == "hole"]
    # it rests on the base of his neck: its band no higher than a little above it
    s = layout.get("scarf")
    assert s.box(front.bbox)[1] > fig.CHIN_Y + 2 * K_PX


def test_a_rain_shells_hood_lies_down_on_its_shoulders_and_a_hoodies_stands_up():
    """A rain shell's hood is drawn down: a shell sewn to the collar, lying behind the neck on the shoulders, not
    standing up over the jacket. A hoodie's hood keeps its shape."""
    tags = ItemTags.model_validate(answer("jacket", garment="rain_shell", neckline="hood", placket="zip_full"))
    template, params, _, _ = drawing_for(tags)
    assert template == "top" and params["hood"] == "down"
    for p, highest in (({"neck": "hood", "hood": "down"}, 25.0), ({"neck": "hood"}, 90.0)):
        s = templates.build("top", p)
        ny = s.anchors["neck"][1]
        top = min(y for part in s.behind for _, y in _flat(part.d))
        assert ny - top <= highest, (p, ny - top)
    assert ny - top > 60   # the hoodie's, up


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
    page, the coverage sheets) are exactly what they were before the figure fitted them (digest taken at a389de3;
    taken again on 16 November, when an ordinary set-in sleeve lost its armhole seam: DRAWING_VERSION 17).
    A deliberate change to the item drawings (with DRAWING_VERSION raised) updates this digest."""
    import hashlib

    from closet.drawing.item import svg_from_fields
    h = hashlib.sha256()
    for category, silhouette in FLAT_LAYS:
        h.update((svg_from_fields(category, "#6b4a32", None, silhouette, uid="f") or "-").encode())
    assert h.hexdigest() == "725f780c8432a4ebd1eb191cb1bcb1e8d24c6a0aa9dab8611e7cdabb540f50fa"
    # drawing a garment with its own template's shape passed in is drawing it as it is
    spec = plan(dict(base=SHIRT)).get("base").spec
    params = spec.params if not spec.weight or "weight" in spec.params else {**spec.params, "weight": spec.weight}
    assert illustrate._draw(spec, "line", "f") == illustrate._draw(spec, "line", "f", shape=illustrate.build(spec.template, params))


def test_wrapping_a_scarf_round_him_leaves_the_flat_scarves_and_hoods_alone():
    """The scarf's worn layers and the rain shell's lowered hood are their own drawings: every scarf's and the
    hoodie's own drawing is what it was before (digest taken at 4ef22e2; taken again on 16 November, when the
    hoodie's ordinary set-in sleeve lost its armhole seam)."""
    import hashlib

    from closet.drawing.item import svg_from_answer
    h = hashlib.sha256()
    for kind in ("long_knit", "woven_wool", "cashmere", "silk", "bandana", "neck_gaiter"):
        h.update(svg_from_answer(answer("scarf", accessory="scarf", accessory_kind=kind), "#b8332e", uid="f").encode())
    h.update(svg_from_answer(answer("hoodie", {"neck": "hood"}), "#8b8e92", uid="f").encode())
    assert h.hexdigest() == "7c719f464a6dd423ccd0bdf92c1a140a8b6720ee641ece7213de56797b182aea"


# ------------------------------------------------------------------ as worn: fit and length

def _tee(fit: str, **more) -> Piece:
    return Piece("tee", answer("tee", fit_detail=fit, sleeve_length="short", neckline="crew", **more), "#f4f2ee")


def _side(t, cm: float) -> float:
    """How far the top's body reaches from the middle at a height on him (cm): its outline's nearest crossing that
    is not a sleeve's edge (a sleeve is a tube round the arm, and its inner edge may lie over a loose body)."""
    y = fig._y(cm)

    def crossings(pts):
        return [x0 + (y - y0) * (x1 - x0) / (y1 - y0) for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1], strict=True)
                if (y0 > y) != (y1 > y) and x0 > CX]
    xs = crossings([t.point(q) for q in fitting.points(t.shape.outline)])
    for s in fitting.sleeves(t.shape):
        for x in crossings([t.point(q) for q in s.poly]):   # each sleeve edge is on the outline once
            xs.remove(min(xs, key=lambda v, x=x: abs(v - x)))
    return (min(xs) - CX) / K_PX


def _hem_cm(t) -> float:
    return (t.point(t.shape.anchors["hem"])[1] - fig.CROWN_Y) / K_PX


def test_the_fit_sets_how_far_the_body_and_sleeves_stand_off_him():
    """The same tee, slim to oversized: its body is wider at every height and its sleeves fuller, in that order."""
    fits = ("slim", "regular", "relaxed", "oversized")
    tops = [plan(dict(base=_tee(f), bottom=TROUSERS)).get("base") for f in fits]
    for cm in (65.0, 75.0, 85.0):
        widths = [_side(t, cm) for t in tops]
        assert all(a < b - 0.3 for a, b in zip(widths, widths[1:], strict=False)), (cm, widths)
        assert widths[-1] > widths[1] + 4.0, (cm, widths)
    sleeves = []
    for t in tops:
        s = next(s for s in fitting.sleeves(t.shape) if s.side == 1)
        y = fig._y(57.0)
        sleeves.append(_sleeve_across(t, s, y)[1])   # its outer edge, off the arm
    assert sleeves == sorted(sleeves) and sleeves[0] < sleeves[-1] - 2 * K_PX, sleeves


def test_a_slim_top_is_shaped_at_the_waist():
    t = plan(dict(base=_tee("slim"), bottom=TROUSERS)).get("base")
    chest, waist, hip = _side(t, 62.0), _side(t, fig.WAIST_CM), _side(t, fig.HIP_CM + 2)
    assert waist < chest - 0.8 and waist < hip - 1.2, (chest, waist, hip)
    assert waist > fig.WAIST_HALF_CM, waist   # still off his sides
    regular = plan(dict(base=_tee("regular"), bottom=TROUSERS)).get("base")
    assert waist < _side(regular, fig.WAIST_CM) - 1.5


@pytest.mark.parametrize(("piece", "landmark"), [
    (_tee("cropped"), "waist"), (_tee("regular"), "hip"), (_tee("longline"), "below_hip"),
    (Piece("tee", None, "#888888"), "hip"),   # nothing told: a regular length
    (Piece("jacket", answer("jacket", collar="point", placket="zip_full", fit_detail="cropped"), "#2a3550"), "waist"),
    (Piece("jacket", answer("jacket", collar="point", placket="zip_full"), "#2a3550"), "hip"),
    (Piece("coat", answer("coat", {"top_length": "long"}, collar="notch_lapel", placket="front_placket"), "#232326"), "above_knee"),
], ids=["cropped tee", "regular tee", "longline tee", "untold tee", "cropped jacket", "jacket", "long coat"])
def test_a_top_ends_at_the_landmark_its_length_goes_to(piece, landmark):
    t = plan(dict(base=piece, bottom=TROUSERS)).get("base")
    assert _hem_cm(t) == pytest.approx(fig.HEM_AT[landmark], abs=1.0)


def test_a_coat_goes_to_the_hip_the_thigh_or_the_knee():
    assert [fig.reaches({"length": n}, category="coat") for n in ("cropped", "regular", "long", "knee")] == \
        ["waist", "hip", "above_knee", "knee"]   # a long (longline) coat well down the thigh, to just above the knee
    assert [fig.reaches({"length": n}, category="jacket") for n in ("cropped", "regular", "long", "knee")] == \
        ["waist", "hip", "thigh", "knee"]
    assert [fig.reaches({"length": n}, category="shirt") for n in ("cropped", "regular", "long")] == ["waist", "hip", "below_hip"]
    assert fig.reaches({}, category="tee") == "hip"
    assert fig.HEM_AT["thigh"] < fig.HEM_AT["above_knee"] < fig.KNEE_CM < fig.HEM_AT["knee"]


def test_a_boxy_top_is_shorter_and_an_oversized_one_longer():
    hems = {f: _hem_cm(plan(dict(base=_tee(f), bottom=TROUSERS)).get("base")) for f in ("boxy", "regular", "oversized")}
    assert hems["boxy"] < hems["regular"] - 3 and hems["oversized"] > hems["regular"] + 3, hems


@pytest.mark.parametrize(("length", "cm"), [("short", fig.SLEEVE_ENDS["short"]), ("elbow", fig.SLEEVE_ENDS["elbow"]),
                                            ("three_quarter", fig.SLEEVE_ENDS["three-quarter"]), ("long", fig.WRIST_CM)])
def test_a_sleeve_ends_where_its_length_goes(length, cm):
    """Short halfway down the upper arm (below the underarm, above the elbow), elbow at the elbow, three-quarter
    down the forearm, long at the wrist."""
    shirt = Piece("shirt", answer("shirt", collar="point", placket="front_placket", sleeve_length=length,
                                  cuff="barrel_1" if length == "long" else "open_hem"), "#a9c3e0")
    t = plan(dict(base=shirt, bottom=TROUSERS)).get("base")
    for s in fitting.sleeves(t.shape):
        start, d, _ = fig._arm_line(s.side)
        cuff = t.point(s.cuff)
        assert (cuff[1] - fig.CROWN_Y) / K_PX == pytest.approx(cm, abs=1.5), (s.side, length)
    assert fig.ARMPIT_CM < fig.SLEEVE_ENDS["short"] < fig.ELBOW_CM < fig.SLEEVE_ENDS["three-quarter"] < fig.WRIST_CM


def _leg_width(b, cm: float) -> float:
    y = fig._y(cm)
    pts = [b.point(q) for q in fitting.points(b.shape.outline)]
    xs = sorted(x0 + (y - y0) * (x1 - x0) / (y1 - y0) for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1], strict=True)
                if (y0 > y) != (y1 > y) and x0 < CX)
    return (xs[-1] - xs[0]) / K_PX


def test_the_trouser_leg_follows_its_shape():
    """Slim narrows to its hem, straight falls straight, wide stays wide: the leg is wider in that order at the
    knee and the hem, and only the slim one narrows much below the knee."""
    legs = {leg: plan(dict(base=TEE, bottom=Piece("trousers", answer("trousers", {"pant_length": "full"}, leg_shape=leg),
                                                       "#6f7278"))).get("bottom") for leg in ("slim", "straight", "wide")}
    for cm in (fig.KNEE_CM, 168.0):
        w = [_leg_width(legs[k], cm) for k in ("slim", "straight", "wide")]
        assert w[0] < w[1] - 1.0 < w[2] - 2.0, (cm, w)
    taper = {k: _leg_width(b, fig.KNEE_CM) - _leg_width(b, 168.0) for k, b in legs.items()}
    assert taper["slim"] > taper["straight"] + 0.5 and taper["wide"] < 0.5, taper


def test_every_leg_shape_is_drawn_as_the_trousers_template_draws_it_and_still_fits_his_ankle():
    """The figure's taper comes from the template's own knee and opening widths for each leg shape (no second table),
    so the order at the hem is the template's; a skinny leg is not narrowed past room for his ankle."""
    assert set(fig.LEG_EASE) == set(templates.LEG_WIDTHS)
    hems = {}
    for leg in templates.LEG_WIDTHS:
        b = plan(dict(base=TEE, bottom=Piece("trousers", answer("trousers", {"pant_length": "full"}, leg_shape=leg),
                                             "#6f7278"))).get("bottom")
        hems[leg] = _leg_width(b, 168.0)
    op = {leg: w[1] for leg, w in templates.LEG_WIDTHS.items()}
    for a in op:   # a leg whose opening is clearly narrower on the flat drawing is narrower on him (barrel ~ straight)
        for b in op:
            if op[a] + 1.0 <= op[b]:
                assert hems[a] < hems[b], (a, b, hems)
    assert hems["skinny"] > 2 * frontshoe.ANKLE_HALF_CM, hems


def test_cropped_trousers_show_the_ankle():
    full = plan(dict(bottom=Piece("trousers", answer("trousers", {"pant_length": "full"}), "#6f7278"))).get("bottom")
    ankle = plan(dict(bottom=Piece("trousers", answer("trousers", {"pant_length": "ankle"}), "#6f7278"))).get("bottom")
    hem = lambda b: (b.point(b.shape.anchors["hem_out"])[1] - fig.CROWN_Y) / K_PX   # noqa: E731
    assert hem(full) == pytest.approx(fig.GROUND_CM - fig.BREAK_CM, abs=0.5)
    assert fig.CALF_CM < hem(ankle) < fig.GROUND_CM - 10.0


def test_as_worn_tells_fit_length_and_sleeves_and_leaves_out_what_was_not_told():
    worn = fig.as_worn(_tee("cropped"))
    assert worn == [{"part": "fit", "value": "regular", "field": "fit_detail"},
                    {"part": "length", "value": "waist", "field": "fit_detail"},
                    {"part": "sleeve", "value": "short", "field": "sleeve_length"}]
    assert fig.as_worn(_tee("oversized"))[0]["value"] == "oversized"
    assert [w["part"] for w in fig.as_worn(_tee("relaxed"))] == ["fit", "sleeve"]   # its length was not told
    assert fig.as_worn(Piece("tee", None, "#888888")) == []   # nothing told: drawn regular, nothing said
    assert fig.as_worn(Piece("tee", None, "#888888", silhouette={"sleeve": "long"})) == [
        {"part": "sleeve", "value": "long", "field": "sleeve_length"}]
    coat = Piece("coat", answer("coat", {"top_length": "long"}, collar="notch_lapel", placket="front_placket"), "#232326")
    assert {"part": "length", "value": "above_knee", "field": "fit_detail"} in fig.as_worn(coat)
    trousers = Piece("trousers", answer("trousers", leg_shape="slim", trouser_break="cropped"), "#6f7278")
    assert fig.as_worn(trousers) == [{"part": "leg", "value": "slim", "field": "leg_shape"},
                                     {"part": "length", "value": "ankle", "field": "trouser_break"}]
    assert fig.as_worn(Piece("shorts", answer("shorts", inseam=7), "#6f7550")) == [
        {"part": "length", "value": "short", "field": "inseam"}]
    assert fig.as_worn(SNEAKERS) == [] and fig.as_worn(Piece("hat", None, "#222222")) == []


HEM_SHOES = {
    "low sneaker": Piece("sneakers", answer("sneakers", shoe_style="low_sneaker"), "#e8edf0"),
    "dress shoe": Piece("dress_shoes", answer("dress_shoes", shoe_style="derby"), "#5a3a22"),
    "chukka": Piece("boots", answer("boots", shoe_style="boot", footwear="chukka"), "#a07850"),
    "work boot": Piece("boots", answer("boots", shoe_style="boot", footwear="service_boot", footwear_height="boot_6in"),
                       "#6b4a32"),
    "chelsea": Piece("boots", answer("boots", shoe_style="chelsea_boot"), "#2a2420"),
}
HEM_BOOTS = ["chukka", "work boot", "chelsea"]


def _legged(leg: str, brk: str) -> Piece:
    return Piece("trousers", answer("trousers", {"pant_length": "ankle" if brk == "cropped" else "full"},
                                    leg_shape=leg, trouser_break=brk), "#6f7278")


def _shoe_seen(layout) -> float:
    """The share of the left shoe's front outline not covered by the trousers."""
    shoes, b = layout.get("shoes"), layout.get("bottom")
    outline, legs = [shoes.point(q) for q in _flat(shoes.front.outline)], _flat(b.shape.outline, b.transforms[0])
    xs, ys = [x for x, _ in outline], [y for _, y in outline]
    grid = [(min(xs) + (max(xs) - min(xs)) * i / 39, min(ys) + (max(ys) - min(ys)) * j / 39) for i in range(40) for j in range(40)]
    on = [p for p in grid if _inside(p, outline)]
    return sum(not _inside(p, legs) for p in on) / len(on)


@pytest.mark.parametrize("shoe", list(HEM_SHOES))
@pytest.mark.parametrize("leg", ["skinny", "slim", "straight", "relaxed"])
@pytest.mark.parametrize("brk", ["full", "slight", "no_break"])
def test_a_leg_narrower_than_the_shoe_rests_on_it_and_most_of_the_shoe_shows(shoe, leg, brk):
    """In 3D a trouser's front edge sits just in front of the shoe's opening: the toe box, most of the vamp and the
    sole show; and the opening itself is under the hem, nothing of its lining seen."""
    layout = plan(dict(base=TEE, bottom=_legged(leg, brk), shoes=HEM_SHOES[shoe]))
    assert _shoe_seen(layout) > 0.74
    shoes, b = layout.get("shoes"), layout.get("bottom")
    legs = _flat(b.shape.outline, b.transforms[0])
    for copy in range(2):
        assert all(_inside(shoes.point(q, copy), legs) for q in _flat(shoes.front.rim))


@pytest.mark.parametrize("shoe", list(HEM_SHOES))
@pytest.mark.parametrize("leg", ["wide", "bootcut"])
def test_a_wide_leg_drops_over_the_shoe_but_not_past_the_vamp(shoe, leg):
    layout = plan(dict(base=TEE, bottom=_legged(leg, "full"), shoes=HEM_SHOES[shoe]))
    shoes, b = layout.get("shoes"), layout.get("bottom")
    front = shoes.front.anchors
    x, rim = shoes.point(front["opening"])
    edge = [p for p in _flat(b.shape.outline, b.transforms[0]) if p[1] > rim - 10 * K_PX]
    assert max(y for _, y in edge) < shoes.point(front["toe"])[1] - 3 * K_PX   # the toe box and the sole's front show
    in_front = max(y for px, y in edge if abs(px - x) < 1.5 * K_PX)   # in front of the opening: behind the vamp
    assert in_front <= max(rim, shoes.point(front["instep"])[1]) + 1.4 * K_PX
    assert _shoe_seen(layout) > 0.5


@pytest.mark.parametrize("shoe", HEM_BOOTS)
@pytest.mark.parametrize("leg", ["skinny", "slim", "straight"])
@pytest.mark.parametrize("brk", ["full", "slight", "no_break"])
def test_a_slim_leg_never_drops_over_a_boots_shaft(shoe, leg, brk):
    """The ankle of a boot is thick: a slim leg sits on top of the shaft, bunching out to cover it, and the shaft
    shows below it whole (not clipped beside the leg)."""
    pieces = dict(base=TEE, bottom=_legged(leg, brk), shoes=HEM_SHOES[shoe])
    layout = plan(pieces)
    shoes, b = layout.get("shoes"), layout.get("bottom")
    assert fig._on_shoe(b.spec.params, shoes.front) == "on"
    rim = shoes.point(shoes.front.anchors["opening"])[1]
    assert b.point(b.shape.anchors["hem"])[1] <= rim + max(fig.HEM_FRONT_CM.values()) * K_PX + 0.1
    assert max(b.point(b.shape.anchors[k])[1] for k in ("hem_out", "hem_in")) < rim + 0.5 * K_PX   # not down its sides
    (xo, _), (xi, _) = b.point(b.shape.anchors["hem_out"]), b.point(b.shape.anchors["hem_in"])
    assert abs(xi - xo) >= shoes.front.width * K_PX   # as wide as the shaft it rests on
    assert "uk" not in figure(pieces, uid="u")


@pytest.mark.parametrize("shoe", list(HEM_SHOES))
@pytest.mark.parametrize("leg", ["skinny", "slim", "straight", "relaxed", "wide", "bootcut"])
def test_cropped_trousers_leave_a_gap_above_the_shoe(shoe, leg):
    socks = small("socks", "casual_crew", "#2e7d4f")
    layout = plan(dict(base=TEE, bottom=_legged(leg, "cropped"), shoes=HEM_SHOES[shoe], accessories=[socks]))
    shoes, b = layout.get("shoes"), layout.get("bottom")
    back = shoes.point(shoes.front.anchors["opening_back"])[1]
    assert max(b.point(b.shape.anchors[k])[1] for k in ("hem", "hem_out", "hem_in")) <= back - fig.CROP_GAP_CM * K_PX + 0.1
    assert not fig._legs(layout)[2]   # so the sock is drawn, in the gap
    assert 'fill="#2e7d4f"' in figure(dict(base=TEE, bottom=_legged(leg, "cropped"), shoes=HEM_SHOES[shoe],
                                           accessories=[socks]))



def test_his_sleeves_hang_in_front_of_an_open_jacket():
    """The arms are in front (the owner, 18 November): a sleeve of a jacket worn open is drawn over its fronts, with
    nothing of the body (a pocket, the hem, a front's edge) on it and its edge along the sleeve; its armhole is a seam
    only where it marks something (the owner, 16 November)."""
    layout = plan(dict(base=SHIRT, outer=BLAZER, bottom=TROUSERS))
    outer = layout.get("outer")
    assert outer.open
    only = fig._sleeve_only(outer.shape)
    polys = [fig._numbers(d) for d, _ in outer.shape.sleeves]
    for part in only.parts:   # only what lies on a sleeve is drawn on it
        pts = fig._numbers(part.d)
        assert sum(any(fig._within(q, poly) for poly in polys) for q in pts) >= fig.ON_SLEEVE * len(pts)
    assert len(only.parts) < len(outer.shape.parts) and only.fronts is None
    svg = figure(dict(base=SHIRT, outer=BLAZER, bottom=TROUSERS), uid="j")
    over = [m.start() for m in re.finditer(r'mask="url\(#slj', svg)]
    assert len(over) == 2   # the shirt's sleeves over its body, the jacket's over its fronts
    assert 'data-part="armhole"' not in svg   # ordinary set-in sleeves: no armhole seam (16 November)
    big = plan(dict(base=BIG_TEE)).get("base").spec.params   # a dropped shoulder: the seam marks it
    assert templates.seam_shows(big.get("shoulder", "set-in"), tuple(big.get("colorblock") or ()))
    assert svg.count("data-part") == 0 and 'data-part="armhole"' in figure(dict(base=BIG_TEE, bottom=TROUSERS), uid="k")
    assert len(set(re.findall(r'<mask id="([^"]+)"', svg))) == len(re.findall(r'<mask id="([^"]+)"', svg))


def test_a_sleeve_moved_past_its_armhole_keeps_its_ends():
    d = "M 10,10 L 10,90 L 30,90 L 30,40 C 25,30 20,20 10,10 Z"
    moved = fig._past_armhole(d)
    assert moved.startswith("M 10,10 L 10,90 L 30,90 L 30,40 L ") and moved.endswith(" L 10.0,10.0 Z")
    assert fig._past_armhole("M 0,0 L 5,5 Z") == "M 0,0 L 5,5 Z"   # no armhole: unchanged
