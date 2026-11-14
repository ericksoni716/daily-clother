"""A patterned item's colours from its measured pattern: the palette of a kept stripe or plaid, named in the app's
colour words, laid over Claude's colour and never over the owner's. The measuring itself is a stand-in (the kept
patterns are made here); `closet.patterns` has its own tests."""
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from closet import app as app_module
from closet import db, palette, today
from closet.drawing import stored
from closet.tagger.tagging import TagResult

from .conftest import ANSWER, PASSPHRASE, fake_cutter, upload

NAVY, WHITE, GREEN, RED = "#1b2a49", "#f4f1ea", "#3f7d4f", "#b8332e"
STRIPES = {"version": stored.VERSION, "kind": "stripes", "orientation": "horizontal",
           "bands": [[NAVY, 0.06], [WHITE, 0.04]] * 10, "trim_bands": None, "sleeves_banded": None}


def _rgb(h):
    return [int(h[i:i + 2], 16) for i in (1, 3, 5)]


def plaid_tile(yarns, widths, repeats=3, blended=True) -> dict:
    """A kept plaid: the same sequence of yarns each way, every crossing the two yarns blended (as a photo sees
    them) or woven as a twill."""
    seq = np.array([i for _ in range(repeats) for i, w in enumerate(widths) for _ in range(w)])
    col = np.array([_rgb(h) for h in yarns], float)[seq]
    if blended:
        img = (col[None, :, :] + col[:, None, :]) / 2
    else:
        y, x = np.mgrid[:len(seq), :len(seq)]
        img = np.where(((((x + y) // 2) % 2) == 1)[..., None], col[None, :, :], col[:, None, :])
    im = Image.fromarray(img.astype(np.uint8)).resize((len(seq) * 3, len(seq) * 3), Image.LANCZOS)
    return {"version": stored.VERSION, "kind": "tile", "image": stored.tile_text(im), "width_frac": 0.2}


PLAID = plaid_tile([NAVY, GREEN, RED], [12, 10, 6])


def words(found):
    return [c["color"] for c in found]


# ---- the palette itself
def test_a_navy_and_white_stripe_gives_navy_and_white():
    colours = palette.measured(STRIPES)
    assert colours == [[NAVY, 0.6], [WHITE, 0.4]]   # by the widths of the bands
    assert words(palette.named(colours)) == ["navy", "white"]


@pytest.mark.parametrize("blended", [True, False])
def test_a_plaid_with_three_yarns_gives_the_three(blended):
    found = palette.named(palette.measured(plaid_tile([NAVY, GREEN, RED], [12, 10, 6], blended=blended)))
    assert sorted(words(found)) == ["green", "navy", "red"]   # the crossings are shared out, not named
    assert found[-1]["color"] == "red" and found[-1]["share"] < found[0]["share"]


def test_claudes_word_is_kept_where_it_fits_the_measured_colour():
    light = [["#c4c5c2", 0.7], ["#27344f", 0.3]]           # a white measured grey in dim light
    assert words(palette.named(light)) == ["grey", "navy"]
    assert words(palette.named(light, ["white"])) == ["white", "navy"]
    assert words(palette.named([["#b8332e", 1.0]], ["navy"])) == ["red"]   # a word that does not fit is not used


def test_claudes_main_colour_stays_main_when_it_covers_nearly_as_much():
    found = [{"color": "white", "hex": WHITE, "share": 0.52}, {"color": "navy", "hex": NAVY, "share": 0.48}]
    assert palette.main_colour(found, "navy")["color"] == "navy"
    found = [{"color": "white", "hex": WHITE, "share": 0.7}, {"color": "navy", "hex": NAVY, "share": 0.3}]
    assert palette.main_colour(found, "navy")["color"] == "white"


def test_specks_are_left_out_and_at_most_four_colours_kept():
    many = [["#1f1f22", 0.4], ["#f6f5f2", 0.2], ["#b8332e", 0.15], ["#3f7d4f", 0.12], ["#e3c341", 0.1], ["#6a4c93", 0.03]]
    assert words(palette.named(many)) == ["black", "white", "red", "green"]
    assert palette.keep({"kind": "tile", "image": "!!"}, "plaid")["colors"] == []


# ---- on an item
def tagger_for(pattern, color="navy", secondary=("white",)):
    answer = ANSWER.model_copy(update={"pattern": pattern, "color": color, "secondary_colors": list(secondary)})
    return lambda images, routes: TagResult(answer, "claude-haiku-5-5", 0.1, 100, 50, 0.0, 1, route=routes[0])


class Measurer:
    def __init__(self, result):
        self.result = result

    def __call__(self, cut, pattern, words, marks):
        return self.result


@pytest.fixture
def make(cfg, claude):
    made = []

    def build(measured, pattern="stripe", color="navy", secondary=("white",)):
        claude.mode = "answers"
        sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, tagger=tagger_for(pattern, color, secondary),
                                       routes=lambda: claude.routes(), corrector=claude.correct,
                                       measurer=Measurer(measured), landmarker=None)
        made.append(sv)
        c = TestClient(app_module.create_app(sv))
        assert c.post("/api/setup", json={"passphrase": PASSPHRASE}).status_code == 204
        return sv, c
    yield build
    for sv in made:
        sv.stop()


def measured_item(sv, c, key="k1"):
    item = upload(c, key=key).json()
    sv.worker.is_ready = lambda: True
    sv.worker.drain()
    sv.tag_worker.drain()
    assert sv.pattern_worker.drain() == 1
    return c.get(f"/api/items/{item['id']}").json()


def row(cfg, item_id):
    conn = db.connect(cfg.db_path("main"))
    try:
        return dict(conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone())
    finally:
        conn.close()


def test_a_measured_stripe_sets_the_colours_and_the_item_page_shows_them(make, cfg):
    sv, c = make(STRIPES, color="multi", secondary=())
    got = measured_item(sv, c)
    assert got["color"] == "navy" and got["color_hex"] == NAVY   # Claude said "multi"; the stripe is mostly navy
    assert got["source"]["color"] == "ai" and got["confidence"]["color"] >= palette.SURE
    assert [(p["color"], p["hex"], p["share"]) for p in got["pattern_colors"]] == [("navy", NAVY, 0.6), ("white", WHITE, 0.4)]
    kept = json.loads(row(cfg, got["id"])["pattern_fill"])
    assert kept["pattern"] == "stripe" and kept["colors"] == [[NAVY, 0.6], [WHITE, 0.4]]


def test_a_measured_plaid_gives_its_three_yarns(make, cfg):
    sv, c = make(PLAID, pattern="plaid", color="green", secondary=())
    got = measured_item(sv, c)
    assert sorted(words(got["pattern_colors"])) == ["green", "navy", "red"]
    assert got["color"] == got["pattern_colors"][0]["color"]
    # the outfit engine and What's missing read the item's colour as before, so they see the measured one
    conn = db.connect(cfg.db_path("main"))
    try:
        assert [r["color"] for r in today.closet_rows(conn) if r["id"] == got["id"]] == [got["color"]]
    finally:
        conn.close()


def test_the_owners_colour_is_never_overwritten(make, cfg):
    sv, c = make(STRIPES, color="multi", secondary=())
    item = upload(c, key="k1").json()
    sv.worker.is_ready = lambda: True
    sv.worker.drain()
    sv.tag_worker.drain()
    assert c.patch(f"/api/items/{item['id']}", json={"color": "red", "color_hex": "#b8332e"}).status_code == 200
    sv.pattern_worker.drain()
    got = c.get(f"/api/items/{item['id']}").json()
    assert got["color"] == "red" and got["color_hex"] == "#b8332e" and got["source"]["color"] == "user"
    assert words(got["pattern_colors"]) == ["navy", "white"]   # still shown beside the pattern


def test_describing_again_keeps_the_measured_colour_and_undo_gives_it_back(make, cfg):
    sv, c = make(STRIPES, color="multi", secondary=())
    got = measured_item(sv, c)
    assert c.post(f"/api/items/{got['id']}/retag").status_code == 202
    sv.tag_worker.drain()
    again = c.get(f"/api/items/{got['id']}").json()
    assert again["color"] == "navy" and again["color_hex"] == NAVY   # not "multi" while it is measured again
    c.patch(f"/api/items/{got['id']}", json={"color": "red"})
    entry = c.get(f"/api/items/{got['id']}/history").json()[0]
    assert c.post(f"/api/items/{got['id']}/history/{entry['id']}/undo").status_code == 200
    back = c.get(f"/api/items/{got['id']}").json()
    assert back["color"] == "navy" and back["source"]["color"] == "ai"


def test_colours_from_an_earlier_pattern_are_not_shown_once_it_changes(make, cfg):
    sv, c = make(STRIPES, color="multi", secondary=())
    got = measured_item(sv, c)
    c.patch(f"/api/items/{got['id']}", json={"pattern": "plaid"})
    assert c.get(f"/api/items/{got['id']}").json()["pattern_colors"] == []
    c.patch(f"/api/items/{got['id']}", json={"pattern": "solid"})
    assert c.get(f"/api/items/{got['id']}").json()["pattern_colors"] == []


def test_a_plain_item_has_no_measured_colours(make, cfg):
    sv, c = make(STRIPES, pattern="solid")
    item = upload(c, key="k1").json()
    sv.worker.is_ready = lambda: True
    sv.worker.drain()
    sv.tag_worker.drain()
    got = c.get(f"/api/items/{item['id']}").json()
    assert got["pattern_colors"] == [] and got["color"] == "navy"
