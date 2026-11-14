"""The outfit drawn as worn (closet/drawing/figure.py) and the route that draws it (POST /api/outfits/figure)."""
import re
import subprocess
import sys
from pathlib import Path

import pytest

from closet.drawing import figure as fig
from closet.drawing import illustrate
from closet.drawing.figure import GROUND_Y, K_PX, MARGIN, WAIST_Y, Piece, figure, plan
from closet.drawing.templates import PX_CM, SHOE_G
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
    layout = plan(OUTFITS["three layers"])
    tops = [p for p in layout.pieces if p.place in ("base", "mid", "outer")]
    assert [p.place for p in tops] == ["base", "mid", "outer"]
    for anchor in ("neck", "shoulder_l", "shoulder_r"):
        assert len({p.point(p.shape.anchors[anchor]) for p in tops}) == 1


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
    assert {round(p.px_per_cm, 6) for p in layout.pieces} == {round(K_PX, 6)}
    b = layout.get("bottom")
    a, _, _, d, _, _ = b.transforms[0]
    assert d * PX_CM == pytest.approx(K_PX)                    # trouser lengths: K_PX a cm, as a top's
    # a full-length trouser: the rise and inseam from the waist, in the tops' pixels per cm
    if b.spec.params.get("length") == "full":
        assert b.point(b.shape.anchors["hem"])[1] - WAIST_Y == pytest.approx((27 + 81) * K_PX)


@pytest.mark.parametrize("name", list(OUTFITS))
def test_shoes_stand_on_the_ground_under_the_legs(name):
    layout = plan(OUTFITS[name])
    shoes, b = layout.get("shoes"), layout.get("bottom")
    assert len(shoes.transforms) == 2                          # a pair
    hem_y = b.point(b.shape.anchors["hem"])[1]
    x0, _, x1, _ = b.box(b.shape.body_box)
    for copy, (lo, hi) in enumerate(((x0, 200), (200, x1))):  # the viewer's left shoe under the left leg, and so on
        sx = sorted(shoes.point((x, SHOE_G), copy)[0] for x in (shoes.shape.bbox[0], shoes.shape.bbox[2]))
        assert shoes.point((sx[0], SHOE_G), copy)[1] == pytest.approx(GROUND_Y)
        assert sx[0] < hi and sx[1] > lo                       # overlaps the leg above it
        assert (sx[1] <= 200 + 1) if copy == 0 else (sx[0] >= 200 - 1)
        assert GROUND_Y > hem_y
    # the toes turn out: the left shoe's toe is left of its heel
    toe, heel = shoes.shape.anchors["toe"], shoes.shape.anchors["heel"]
    assert shoes.point(toe, 0)[0] < shoes.point(heel, 0)[0] and shoes.point(toe, 1)[0] > shoes.point(heel, 1)[0]


@pytest.mark.parametrize("name", list(OUTFITS))
def test_the_figure_fits_its_canvas_with_even_margins(name):
    layout = plan(OUTFITS[name])
    vx, vy, vw, vh = layout.view
    boxes = [p.box() for p in layout.pieces]
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
    assert hx == pytest.approx(fig.CX) and hy == pytest.approx(fig.NECK_Y - fig.HAT_ABOVE_NECK_CM * K_PX)
    assert got["hat"].box()[3] < fig.NECK_Y   # above the collar
    # the bag beside the figure, on the viewer's right, its handle at a hand's height
    right = max(p.box()[2] for p in layout.pieces if p.place != "bag")
    assert got["bag"].box()[0] > right
    assert got["bag"].point(got["bag"].shape.anchors["hand"])[1] == pytest.approx(WAIST_Y + fig.HAND_BELOW_WAIST_CM * K_PX)
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
