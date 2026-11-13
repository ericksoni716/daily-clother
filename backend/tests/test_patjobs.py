"""Measuring an item's pattern in the background: when it waits, what it keeps, how its drawing changes, and that
a failure never costs the drawing. The measuring itself is a stand-in here (`closet.patterns` has its own tests)."""
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from closet import app as app_module
from closet import db, patjobs
from closet.drawing import stored
from closet.tagger.tagging import RouteUnavailable

from .conftest import PASSPHRASE, fake_cutter, upload

STRIPES = {"version": stored.VERSION, "kind": "stripes", "orientation": "horizontal",
           "bands": [["#1b2a49", 0.04], ["#f4f1ea", 0.06]] * 10, "trim_bands": None, "sleeves_banded": None}


class Measurer:
    def __init__(self, result=STRIPES, fail=False):
        self.result, self.fail, self.calls = result, fail, []

    def __call__(self, cut, pattern, words, marks):
        self.calls.append((cut.mode, pattern, words, marks))
        if self.fail:
            raise RuntimeError("could not measure")
        return self.result


class Landmarker:
    def __init__(self, unavailable=False):
        self.unavailable, self.calls = unavailable, 0

    def __call__(self, cut, routes):
        self.calls += 1
        if self.unavailable:
            raise RouteUnavailable("no route")
        return {"button_line": [], "neck_center": {"x": 1, "y": 1}, "hem_center": {"x": 1, "y": 9},
                "shoulder_left": {"x": 0, "y": 2}, "shoulder_right": {"x": 9, "y": 2},
                "underarm_left": {"x": 0, "y": 4}, "underarm_right": {"x": 9, "y": 4}}


@pytest.fixture
def make(cfg, claude):
    made = []

    def build(measurer, landmarker=None):
        claude.mode = "answers"
        sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, tagger=claude,
                                       routes=lambda: claude.routes(), corrector=claude.correct,
                                       measurer=measurer, landmarker=landmarker)
        made.append(sv)
        c = TestClient(app_module.create_app(sv))
        assert c.post("/api/setup", json={"passphrase": PASSPHRASE}).status_code == 204
        return sv, c
    yield build
    for sv in made:
        sv.stop()


def described(sv, c, key="k1"):
    item = upload(c, key=key).json()
    sv.worker.is_ready = lambda: True
    sv.worker.drain()
    sv.tag_worker.drain()
    return item


def row(cfg, item_id):
    conn = db.connect(cfg.db_path("main"))
    try:
        return dict(conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone())
    finally:
        conn.close()


def test_a_plain_item_is_never_measured(make, cfg):
    m = Measurer()
    sv, c = make(m)
    item = described(sv, c)
    assert sv.pattern_worker.drain() == 0 and m.calls == []
    assert row(cfg, item["id"])["pattern_state"] is None


def test_a_patterned_item_is_measured_kept_and_drawn(make, cfg):
    m, lm = Measurer(), Landmarker()
    sv, c = make(m, lm)
    item = described(sv, c)
    before = c.get(f"/api/items/{item['id']}").json()
    assert c.patch(f"/api/items/{item['id']}", json={"pattern": "stripe"}).status_code == 200
    got = c.get(f"/api/items/{item['id']}").json()
    assert got["pattern_state"] == "waiting"
    assert any("stripes" in n for n in got["drawing_notes"])          # until measured: shown in its colour, said so
    assert sv.pattern_worker.drain() == 1
    (mode, pattern, words, marks), = m.calls
    assert mode == "RGBA" and pattern == "stripe" and "navy" in words and marks is not None and lm.calls == 1
    got = c.get(f"/api/items/{item['id']}").json()
    assert got["pattern_state"] == "done" and got["pattern_error"] is None
    assert not any("stripes" in n for n in got["drawing_notes"])
    assert got["illustration_svg"] != before["illustration_svg"] and "#1b2a49" in got["illustration_svg"]
    kept = row(cfg, item["id"])
    assert json.loads(kept["pattern_fill"])["kind"] == "stripes" and json.loads(kept["landmarks"])["hem_center"]


def test_landmarks_are_asked_once_and_their_absence_does_not_stop_the_measuring(make, cfg):
    m, lm = Measurer(), Landmarker(unavailable=True)
    sv, c = make(m, lm)
    item = described(sv, c)
    c.patch(f"/api/items/{item['id']}", json={"pattern": "plaid"})
    sv.pattern_worker.drain()
    assert m.calls[0][3] is None and row(cfg, item["id"])["pattern_state"] == "done"


def test_a_failed_measurement_keeps_the_drawing_and_says_why(make, cfg):
    sv, c = make(Measurer(fail=True))
    item = described(sv, c)
    c.patch(f"/api/items/{item['id']}", json={"pattern": "floral"})
    sv.pattern_worker.drain()
    got = c.get(f"/api/items/{item['id']}").json()
    assert got["pattern_state"] == "failed" and got["pattern_error"] == patjobs.FAILED
    assert got["illustration_svg"].startswith("<svg")


def test_the_owner_saying_plain_stops_the_pattern(make, cfg):
    sv, c = make(Measurer())
    item = described(sv, c)
    c.patch(f"/api/items/{item['id']}", json={"pattern": "stripe"})
    sv.pattern_worker.drain()
    c.patch(f"/api/items/{item['id']}", json={"pattern": "solid"})
    got = c.get(f"/api/items/{item['id']}").json()
    assert got["pattern_state"] is None and "#1b2a49" not in got["illustration_svg"]
    assert row(cfg, item["id"])["pattern_fill"] is None


def test_an_interrupted_measurement_starts_again(make, cfg):
    sv, c = make(Measurer())
    item = described(sv, c)
    c.patch(f"/api/items/{item['id']}", json={"pattern": "stripe"})
    conn = db.connect(cfg.db_path("main"))
    conn.execute("UPDATE items SET pattern_state = 'working' WHERE id = ?", (item["id"],))
    conn.close()
    assert sv.pattern_worker.drain() == 1 and row(cfg, item["id"])["pattern_state"] == "done"


def test_a_damaged_kept_pattern_is_drawn_in_its_colour():
    assert stored.fill_from("not json", "#888888") is None
    assert stored.fill_from({"version": 99, "kind": "stripes"}, "#888888") is None
    assert stored.fill_from({"version": stored.VERSION, "kind": "tile", "image": "!!", "width_frac": 0.1}, "#888") is None
    bad_hex = dict(STRIPES, bands=[["red", 0.5]])
    assert stored.fill_from(bad_hex, "#888888") is None
    tile = {"version": stored.VERSION, "kind": "tile", "image": stored.tile_text(Image.new("RGB", (8, 8), "navy")),
            "width_frac": 0.1, "phase": [0.2, 0.3], "phase_right": [0.7, 0.3], "length_frac": 0.1}
    f = stored.fill_from(tile, "#888888")
    assert f.kind == "swatch" and f.swatch.phase == (0.2, 0.3) and f.swatch.phase_right == (0.7, 0.3)


def test_the_demo_closet_is_never_measured(make, cfg):
    m = Measurer()
    sv, c = make(m)
    c.post("/api/profile", json={"profile": "demo"})
    assert sv.pattern_worker.drain() == 0 and m.calls == []
