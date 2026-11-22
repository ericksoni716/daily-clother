"""A shoe's side drawn by Claude, in the app (`closet/shoedraw.py`, `closet/illustrations.py`): kept with the drawing,
it becomes the item's own drawing (the closet tile, the item page), unless the owner chose the plain drawing; the
trace stays for when there is none, and gives its measures; a correction keeps the side, going back swaps it; a shoe
drawn without a side is drawn its side by itself, when nothing else waits, at most three times, waiting when Claude
cannot be reached, never in the demo closet.

Claude is never called: a stand-in drawer (`test_shoedraw.Drawer`) and a stand-in side drawer answer.
"""
import json
import threading
import time
from contextlib import closing
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from closet import app as app_module
from closet import db, illustrations, shoedraw
from closet.drawing import drawnside
from closet.drawing.traced import LENGTH, Profile, Region, TracedShoe
from closet.tagger import shoedrawing as SD
from closet.tagger.tagging import CapReached, RouteUnavailable, TaggingError

from .conftest import SIDE_FEATURES, SIDE_SVG, FakeClaude, fake_cutter
from .test_shoe_correct import Corrector
from .test_shoedraw import Drawer
from .test_shoeviews import Sorter, a_shoe, add, answer, get, later, row, sql


def a_side(svg: str = SIDE_SVG) -> SD.Sided:
    return SD.Sided(drawnside.sanitise(svg), list(SIDE_FEATURES), {"heel": 0.35}, 1, 60.0,
                    [SD.Call("side", "plan", SD.MODEL, 20_000, 5_000, 2_000, 0.1, 40.0)], True, [])


class Sider:
    """Stands in for Claude drawing a shoe's side by itself: `side`, or raises `error`; keeps what it was given."""

    def __init__(self):
        self.side, self.error, self.calls = a_side(), None, []

    def __call__(self, photos, routes, sheet=None, notes=(), measures=None, side_notes=()):
        self.calls.append({"views": [p.view for p in photos], "sheet": sheet, "notes": list(notes),
                           "measures": measures, "side_notes": list(side_notes)})
        if self.error:
            raise self.error
        return self.side


def traced_shoe() -> TracedShoe:
    """A traced shoe as kept: a plain profile, 0.34 of its length tall at the heel, and one blue silhouette."""
    u = [i / 40 for i in range(41)]
    top = [LENGTH * (0.34 if x <= 0.12 else 0.3 if x <= 0.5 else 0.3 - 0.12 * (x - 0.5) / 0.5) for x in u]
    outline = [[0.0, 0.0], [1.0, 0.0], [1.0, 3.0], [0.6, 8.0], [0.0, 10.0]]
    return TracedShoe(version=2, approach="test", cutout_by="grabcut", profile=Profile(u, top, [0.0] * 41,
                      [LENGTH * 0.08] * 41), parts=[], marks=[], laces=None, eyelets=None, stitching=None,
                      style="low_sneaker", confidence=0.9, gate={"ok": True, "reasons": [], "notes": [], "told": {},
                                                                    "signals": {}},
                      regions=[Region("#3366aa", "silhouette", [[outline]])])


@pytest.fixture
def made(cfg):
    sorter, drawer, corrector, sider = Sorter(), Drawer(), Corrector(), Sider()
    routes = {"now": ("plan",)}
    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, tagger=FakeClaude(),
                                   routes=lambda: routes["now"], sorter=sorter, drawer=drawer,
                                   drawing_corrector=corrector, side_drawer=sider)
    c = TestClient(app_module.create_app(sv))
    yield SimpleNamespace(sv=sv, c=c, routes=routes, sorter=sorter, drawer=drawer, corrector=corrector, sider=sider)
    sv.stop()


def sorted_shoe(m, key="k1", traced: bool = False, photo: int = 1) -> dict:
    item = a_shoe(m.c, key)
    if traced:
        with closing(db.connect(m.sv.cfg.db_path("main"))) as conn:
            conn.execute("UPDATE items SET trace = ?, trace_state = 'done' WHERE id = ?",
                         (traced_shoe().to_json(), item["id"]))
            illustrations.redraw(conn, item["id"])
    add(m.c, item, photo)   # another shoe is given another photo
    m.sorter.reply = answer(("outer", True), ("inner", True))
    m.sv.views.drain(now=later())
    return item


def kept(m, item, column="drawn") -> dict | None:
    text = row(m.sv.cfg, item["id"])[column]
    return json.loads(text) if text else None


def picture(m, item) -> str:
    return m.c.get(get(m.c, item)["illustration_url"]).text


# ------------------------------------------------------------------ the item's drawing

def test_a_side_drawn_with_the_drawing_becomes_the_items_drawing(made):
    m = made
    item = sorted_shoe(m, traced=True)
    traced_picture = picture(m, item)
    assert "#3366aa" in traced_picture   # the trace, until Claude's side exists
    assert get(m.c, item)["trace"]["drawn"] is True
    m.drawer.side = a_side()
    assert m.sv.draws.drain() == 1 and m.sider.calls == []   # drawn with its drawing: nothing left to do by itself
    # the drawer was told the measures from the trace
    assert m.drawer.measures[0]["heel"] == pytest.approx(0.34) and m.drawer.measures[0]["tallest"] == pytest.approx(0.34)
    got = get(m.c, item)
    assert got["drawn"]["side_shown"] is True and got["drawn"]["side"]["features"] == SIDE_FEATURES
    assert got["trace"]["drawn"] is False   # the trace's colours and marks are not what shows now
    shown = picture(m, item)
    assert shown == drawnside.card_svg(SIDE_SVG) and "#3366aa" not in shown
    r = m.c.get(got["drawn"]["side"]["url"])
    assert r.status_code == 200 and r.text == shown and r.headers["content-type"].startswith("image/svg+xml")
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert kept(m, item)["side"]["features"] == SIDE_FEATURES


def test_the_plain_drawing_wins_and_the_trace_stays_when_there_is_no_side(made):
    m = made
    item = sorted_shoe(m, traced=True)
    m.drawer.side = a_side()
    m.sv.draws.drain()
    assert m.c.put(f"/api/items/{item['id']}/trace/plain", json={"plain": True}).status_code == 200
    got = get(m.c, item)
    assert got["drawn"]["side_shown"] is False and got["drawn"]["side"] is not None   # still shown with the front
    assert picture(m, item) != drawnside.card_svg(SIDE_SVG) and "#3366aa" not in picture(m, item)   # the template
    m.c.put(f"/api/items/{item['id']}/trace/plain", json={"plain": False})
    assert picture(m, item) == drawnside.card_svg(SIDE_SVG)
    # a side that cannot be read: the trace again
    broken = {**kept(m, item), "side": {"svg": "<text>no</text>"}}
    sql(m.sv.cfg, "UPDATE items SET drawn = ? WHERE id = ?", (json.dumps(broken), item["id"]))
    assert "#3366aa" in illustrations.make(row(m.sv.cfg, item["id"])).svg


def test_a_correction_keeps_the_side_and_going_back_swaps_it(made):
    m = made
    item = sorted_shoe(m)
    m.drawer.side = a_side()
    m.sv.draws.drain()
    side = kept(m, item)["side"]
    assert m.c.post(f"/api/items/{item['id']}/drawn/correct", json={"note": "the laces should be black"}).status_code == 202
    assert m.sv.draws.drain() == 1 and len(m.corrector.calls) == 1
    assert kept(m, item)["side"] == side and kept(m, item)["corrected"] is True
    # a new drawing whose side failed: the item's drawing is no longer the side; going back brings it again
    m.drawer.side = None
    m.c.post(f"/api/items/{item['id']}/drawn")
    m.sider.error = RouteUnavailable("not signed in")
    m.sv.draws.drain()
    assert kept(m, item)["side"] is None and picture(m, item) != drawnside.card_svg(SIDE_SVG)
    assert m.c.post(f"/api/items/{item['id']}/drawn/back").status_code == 200
    assert kept(m, item)["side"] == side and picture(m, item) == drawnside.card_svg(SIDE_SVG)


# ------------------------------------------------------------------ a side drawn by itself

def test_a_shoe_drawn_without_a_side_is_drawn_its_side_by_itself(made):
    m = made
    item = sorted_shoe(m, traced=True)
    m.drawer.error = RouteUnavailable("out of reach")   # nothing drawn yet: no side to draw either
    m.sv.draws.drain()
    assert m.sider.calls == []
    m.drawer.error = None
    assert m.sv.draws.drain() == 2   # the drawing, then, with nothing else waiting, its side
    call = m.sider.calls[0]
    assert call["views"] == ["outer", "inner"] and call["sheet"]["archetype"] == "cap-toe oxford"
    assert call["measures"]["heel"] == pytest.approx(0.34) and call["notes"] == []
    d = kept(m, item)
    assert d["side"]["features"] == SIDE_FEATURES and d["side"]["route"] == "plan" and d["side_tries"] == 1
    assert d["cost_usd"] == pytest.approx(0.38)   # the drawing's own cost stays its own
    assert picture(m, item) == drawnside.card_svg(SIDE_SVG)
    assert m.sv.draws.drain() == 0 and len(m.sider.calls) == 1   # once


def test_a_side_waits_when_claude_cannot_be_reached_and_stops_after_three_tries(made):
    m = made
    item = sorted_shoe(m)
    m.sider.error = CapReached("this month's spending limit for the API key has been reached")
    assert m.sv.draws.drain() == 1   # the drawing; the side waits
    assert kept(m, item).get("side_tries", 0) == 0 and get(m.c, item)["drawn"]["message"] is None
    m.sider.error = TaggingError("no usable answer")
    for _ in range(5):
        m.sv.draws.drain()
    assert len(m.sider.calls) == 1 + shoedraw.SIDE_TRIES and kept(m, item)["side_tries"] == shoedraw.SIDE_TRIES
    assert kept(m, item)["side"] is None and get(m.c, item)["drawn"]["state"] == "done"
    # a new drawing starts again from none
    m.c.post(f"/api/items/{item['id']}/drawn")
    m.sider.error = None
    assert m.sv.draws.drain() == 2 and kept(m, item)["side"]["features"] == SIDE_FEATURES


def test_a_free_place_draws_one_side_at_a_time_and_the_demos_never(made):
    m = made
    one = sorted_shoe(m, "k1")
    m.sider.error = RouteUnavailable("out of reach")
    m.sv.draws.drain()   # the first shoe drawn; its side waits
    two = sorted_shoe(m, "k2", photo=2)
    m.sider.error = None
    m.sider.side = a_side()
    lock, now, most, drawing = threading.Lock(), [0], [0], threading.Event()
    m.drawer.during = lambda: (drawing.set(), time.sleep(0.3))
    sider = m.sv.draws.sider

    def counted(photos, routes, **kw):
        with lock:
            now[0] += 1
            most[0] = max(most[0], now[0])
        time.sleep(0.2)
        with lock:
            now[0] -= 1
        return sider(photos, routes, **kw)
    m.sv.draws.sider = counted
    assert m.sv.draws.drain() == 3   # the second shoe drawn, and both sides, the first one's beside that drawing
    assert drawing.is_set() and most[0] == shoedraw.SIDES_AT_ONCE == 1   # sides one at a time
    assert kept(m, one)["side"] and kept(m, two)["side"] and len(m.sider.calls) == 3
    # a drawing made for the demo closet is never drawn its side, nor anything while the demo closet is open
    sql(m.sv.cfg, "UPDATE items SET drawn = ? WHERE id = ?",
        (json.dumps({**kept(m, one), "side": None, "route": "demo"}), one["id"]))
    with closing(db.connect(m.sv.cfg.db_path("main"))) as conn:
        assert shoedraw.side_due(conn) is None
    sql(m.sv.cfg, "UPDATE items SET drawn = ? WHERE id = ?",
        (json.dumps({**kept(m, two), "side": None}), two["id"]))
    m.sv.state.update(profile="demo")
    assert m.sv.draws.drain() == 0 and len(m.sider.calls) == 3


def test_a_side_goes_with_the_drawing_it_was_made_for(made):
    m = made
    item = sorted_shoe(m)
    m.sider.error = RouteUnavailable("out of reach")
    m.sv.draws.drain()   # the first drawing, without a side
    m.drawer.left = SD.drawn.example("boat-shoe")
    m.c.post(f"/api/items/{item['id']}/drawn")
    m.sv.draws.drain()   # the second, without a side either
    first = kept(m, item, "drawn_prev")["made_at"]
    m.sider.error = None
    went_back = []

    def back_meanwhile(photos, routes, **kw):   # the owner goes back to the first while the second's side is drawn
        if not went_back:
            went_back.append(m.c.post(f"/api/items/{item['id']}/drawn/back").status_code)
        return m.sider(photos, routes, **kw)
    m.sv.draws.sider = back_meanwhile
    assert m.sv.draws.drain() == 2 and went_back == [200]
    # the second's side is kept with the second (now the one before); then the first is drawn its own
    assert kept(m, item)["made_at"] == first and kept(m, item)["side"]["features"] == SIDE_FEATURES
    assert kept(m, item, "drawn_prev")["side"]["features"] == SIDE_FEATURES


# ------------------------------------------------------------------ with shoes drawn at the same time

def a_shoe_without_its_side(m, key="k1", photo=1) -> dict:
    """A shoe drawn, its side not drawn yet (Claude was out of reach for it)."""
    item = sorted_shoe(m, key, photo=photo)
    m.sider.error = RouteUnavailable("out of reach")
    m.sv.draws.drain()
    m.sider.error = None
    assert kept(m, item)["side"] is None and get(m.c, item)["drawn"]["state"] == "done"
    return item


def test_the_same_shoes_side_is_never_drawn_twice_at_once(made):
    m = made
    item = a_shoe_without_its_side(m)
    calls = len(m.sider.calls)
    sider = m.sv.draws.sider

    def slow(photos, routes, **kw):   # long enough for the drain to look for more work meanwhile
        time.sleep(0.5)
        return sider(photos, routes, **kw)
    m.sv.draws.sider = slow
    assert m.sv.draws.drain() == 1
    assert len(m.sider.calls) == calls + 1 and kept(m, item)["side_tries"] == 1


def test_a_second_drain_never_takes_a_side_being_drawn(made):
    m = made
    item = a_shoe_without_its_side(m)
    calls = len(m.sider.calls)
    sider, seen = m.sv.draws.sider, []

    def during(photos, routes, **kw):   # a second drain while the side is drawn
        second = threading.Thread(target=lambda: seen.append(m.sv.draws.drain()))
        second.start()
        second.join(timeout=10)
        r = row(m.sv.cfg, item["id"])   # its recover left it as it was: no state changed, its try still counted
        seen.append((r["drawn_state"], json.loads(r["drawn"])["side_tries"]))
        return sider(photos, routes, **kw)
    m.sv.draws.sider = during
    assert m.sv.draws.drain() == 1 and seen == [0, ("done", 1)]
    assert len(m.sider.calls) == calls + 1 and kept(m, item)["side"]["features"] == SIDE_FEATURES


def test_a_shoe_whose_side_is_drawn_is_drawn_or_corrected_only_after_it(made):
    m = made
    item = a_shoe_without_its_side(m)
    sider, order = m.sv.draws.sider, []

    def during(photos, routes, **kw):   # the owner asks for a correction while the side is drawn
        assert m.c.post(f"/api/items/{item['id']}/drawn/correct", json={"note": "black laces"}).status_code == 202
        m.sv.draws.wake()
        time.sleep(0.5)   # time for the worker to look for work: the correction must wait for the side
        order.append(("side", len(m.corrector.calls)))
        return sider(photos, routes, **kw)
    m.sv.draws.sider = during
    m.sv.draws.drain()
    assert order == [("side", 0)] and len(m.corrector.calls) == 1
    d = kept(m, item)
    assert d["corrected"] is True and d["side"]["features"] == SIDE_FEATURES   # the correction kept the new side
    assert row(m.sv.cfg, item["id"])["drawn_state"] == "done"
