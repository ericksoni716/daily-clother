"""A shoe drawn by Claude from its sorted photos, in the background (`closet/shoedraw.py`): drawn once by itself when
its photos are first sorted, waiting while they are sorted or the owner is asked about the outside, never drawn again
by itself, drawn again when the owner asks with the old drawing kept until the new one is done, Claude out of reach
or failing, the demo closet, and what the item page and `drawn.svg` show.

Claude is never called: a stand-in sorter and a stand-in drawer answer.
"""
import json
import logging
import threading
import time
from contextlib import closing
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from closet import app as app_module
from closet import db, shoedraw, spend, tracejobs
from closet.drawing import drawn
from closet.tagger import shoedrawing as SD
from closet.tagger.tagging import CapReached, RouteUnavailable, TaggingError

from .conftest import CUT, PASSPHRASE, SHEET, FakeApi, FakeClaude, fake_cutter, upload
from .test_figure_drawn import answer as tags
from .test_shoeviews import Sorter, a_shoe, add, answer, get, later, row, sql

DRESS = drawn.example("dress-shoe")
BOAT = drawn.example("boat-shoe")


class Drawer:
    """Stands in for Claude drawing the shoe: a finished drawing of `left` (the dress shoe unless told otherwise), or
    raises `error`. `calls` keeps the views of the photos it was given, `notes` the owner's notes it was given (step
    E); `during` runs while it draws."""

    def __init__(self):
        self.left = DRESS
        self.error: Exception | None = None
        self.calls: list[list[tuple]] = []
        self.notes: list[list[str]] = []
        self.styles: list[str | None] = []   # the item's shoe style it was told
        self.measures: list[dict | None] = []   # the measures from the trace it was told
        self.side: SD.Sided | None = None   # the side drawn with it, if any
        self.during = None

    def __call__(self, photos, routes, notes=(), style=None, measures=None):
        self.calls.append([(p.view, p.sure, p.image.size) for p in photos])
        self.notes.append(list(notes))
        self.styles.append(style)
        self.measures.append(measures)
        assert routes == ("plan",)
        if self.during:
            self.during()
        if self.error:
            raise self.error
        calls = [SD.Call("draw", "plan", SD.MODEL, 40_000, 10_000, 6_000, 0.24, 70.0),
                 SD.Call("check", "plan", SD.MODEL, 30_000, 10_000, 3_000, 0.14, 40.0)]
        return SD.Drawn(drawn.side(self.left), None, dict(SHEET), 1, 112.4, calls, True, [], side=self.side)


@pytest.fixture
def made(cfg):
    sorter, drawer = Sorter(), Drawer()
    routes = {"now": ("plan",)}
    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, tagger=FakeClaude(),
                                   routes=lambda: routes["now"], sorter=sorter, drawer=drawer)
    c = TestClient(app_module.create_app(sv))
    assert c.post("/api/setup", json={"passphrase": PASSPHRASE}).status_code == 204
    yield SimpleNamespace(sv=sv, c=c, routes=routes, sorter=sorter, drawer=drawer)
    sv.stop()


def sorted_shoe(m, differ=False, key="k1") -> dict:
    """A shoe with one more photo, sorted (the two photos sure, the sides alike unless `differ`)."""
    item = a_shoe(m.c, key)
    add(m.c, item, 1)
    m.sorter.reply = answer(("outer", not differ), ("inner", not differ), differ=differ)
    m.sv.views.drain(now=later())
    return item


def drawn_of(m, item) -> dict:
    return get(m.c, item)["drawn"]


# ------------------------------------------------------------------ the migration

def test_the_migration_adds_the_columns(cfg):
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    db.migrate(cfg.db_path("main"), cfg.local_backups_dir)
    with closing(db.connect(cfg.db_path("main"))) as conn:
        cols = {r[1]: r for r in conn.execute("PRAGMA table_info(items)")}
    assert {"drawn", "drawn_state", "drawn_error", "drawn_attempts"} <= set(cols)
    assert cols["drawn_attempts"][4] == "0" and cols["drawn_attempts"][3] == 1   # NOT NULL DEFAULT 0


# ------------------------------------------------------------------ drawn once by itself

def test_a_shoe_is_drawn_once_its_photos_are_first_sorted(made):
    m = made
    item = a_shoe(m.c)
    assert drawn_of(m, item)["state"] is None and drawn_of(m, item)["message"] == shoedraw.NOT_DRAWN
    add(m.c, item, 1)
    assert drawn_of(m, item)["message"] == shoedraw.SOON   # the photos wait to be sorted first
    assert m.sv.draws.drain() == 0 and m.drawer.calls == []
    m.sorter.reply = answer(("outer", True), ("inner", True))
    m.sv.views.drain(now=later())
    got = drawn_of(m, item)
    assert got["state"] == "waiting" and got["message"] == shoedraw.WAITING and got["url"] is None
    assert m.sv.draws.drain() == 1
    assert m.drawer.calls == [[("outer", True, (900, 1200)), ("inner", True, (640, 480))]]   # the main photo first
    assert m.drawer.styles == [None]   # not described yet: the drawing's own sheet says what kind of shoe it is
    got = drawn_of(m, item)
    assert got["state"] == "done" and got["message"] is None and got["rounds"] == 1 and got["seconds"] == 112.4
    assert got["cost_usd"] == pytest.approx(0.38) and got["route"] == "plan" and got["photos_changed"] is False
    assert got["url"].startswith(f"/api/items/{item['id']}/drawn.svg?v=") and got["about_usd"] == 0.38
    kept = json.loads(row(m.sv.cfg, item["id"])["drawn"])
    assert kept["left"] == {"behind": "", "front": drawn.sanitise(DRESS)} and kept["sheet"] == SHEET
    assert kept["version"] == drawn.VERSION == 3 and kept["right"] is None
    assert kept["photo_ids"] == [p["id"] for p in get(m.c, item)["photos"]]
    assert kept["input_tokens"] == 70_000 and kept["output_tokens"] == 9_000 and kept["cache_read_tokens"] == 20_000
    assert [c["kind"] for c in kept["calls"]] == ["draw", "check"]
    assert row(m.sv.cfg, item["id"])["drawn_attempts"] == 0


def test_a_drawing_kept_as_version_1_is_shown_as_it_is_and_never_drawn_again_by_itself(made):
    """Step D keeps each shoe behind and in front of the leg (version 2); a drawing kept before (one text, all in
    front) stays as it is: shown on the page and on the figure, never drawn again by itself."""
    m = made
    item = sorted_shoe(m)
    assert m.sv.draws.drain() == 1
    one = {**json.loads(row(m.sv.cfg, item["id"])["drawn"]), "version": 1, "left": drawn.sanitise(DRESS)}
    sql(m.sv.cfg, "UPDATE items SET drawn = ? WHERE id = ?", (json.dumps(one), item["id"]))
    got = drawn_of(m, item)
    assert got["state"] == "done" and got["url"] and got["message"] is None
    svg = m.c.get(got["url"]).text
    assert "#b5622f" in svg.lower() and svg.index(drawn.PREVIEW_SOCK) < svg.lower().index("#b5622f")   # the leg, then the shoe
    assert m.sv.draws.drain() == 0 and len(m.drawer.calls) == 1 and get(m.c, item)["drawn_version"]
    figure = m.c.post("/api/outfits/figure", json={"shoes": item["id"]}).text
    assert "#b5622f" in figure.lower()


def test_it_waits_while_the_owner_is_asked_about_the_outside(made):
    m = made
    item = sorted_shoe(m, differ=True)
    assert get(m.c, item)["views"]["state"] == "asking"
    got = drawn_of(m, item)
    assert got["state"] == "waiting" and got["message"] == shoedraw.WAIT_ASK
    assert m.sv.draws.drain() == 0 and m.drawer.calls == []
    first = get(m.c, item)["photos"][0]
    m.c.put(f"/api/items/{item['id']}/photos/{first['id']}/view", json={"view": "outer"})
    assert drawn_of(m, item)["message"] == shoedraw.WAITING
    assert m.sv.draws.drain() == 1 and drawn_of(m, item)["state"] == "done"


def test_it_is_never_drawn_again_by_itself(made):
    m = made
    item = sorted_shoe(m)
    m.sv.draws.drain()
    before = drawn_of(m, item)
    add(m.c, item, 2)   # a photo added: sorted again, never drawn again
    m.sorter.reply = answer(("outer", True), ("inner", True), ("top", True))
    m.sv.views.drain(now=later())
    assert m.sv.draws.drain() == 0 and len(m.drawer.calls) == 1
    got = drawn_of(m, item)
    assert got["state"] == "done" and got["url"] == before["url"] and got["photos_changed"] is True
    two = get(m.c, item)["photos"][2]
    m.c.delete(f"/api/items/{item['id']}/photos/{two['id']}")
    assert drawn_of(m, item)["photos_changed"] is False   # the same photos as when it was drawn


def test_a_failed_first_drawing_is_not_tried_again_by_itself(made):
    m = made
    item = sorted_shoe(m)
    m.drawer.error = TaggingError("no usable answer")
    m.sv.draws.drain()
    assert drawn_of(m, item)["state"] == "failed"
    add(m.c, item, 2)
    m.sorter.reply = answer(("outer", True), ("inner", True), ("top", True))
    m.sv.views.drain(now=later())
    assert drawn_of(m, item)["state"] == "failed" and m.sv.draws.drain() == 0


# ------------------------------------------------------------------ drawn again when the owner asks

def test_draw_again_keeps_the_old_drawing_until_the_new_one_is_done(made):
    m = made
    item = sorted_shoe(m)
    m.sv.draws.drain()
    old = drawn_of(m, item)
    r = m.c.post(f"/api/items/{item['id']}/drawn")
    assert r.status_code == 202
    got = r.json()["drawn"]
    assert got["state"] == "waiting" and got["url"] == old["url"]   # still shown
    assert m.c.post(f"/api/items/{item['id']}/drawn").json()["drawn"]["state"] == "waiting"   # asked twice: once
    seen = {}
    m.drawer.left = BOAT
    m.drawer.during = lambda: seen.update(drawn_of(m, item))
    assert m.sv.draws.drain() == 1 and len(m.drawer.calls) == 2
    assert seen["state"] == "drawing" and seen["message"] == shoedraw.DRAWING and seen["url"] == old["url"]
    new = drawn_of(m, item)
    assert new["state"] == "done" and new["url"] != old["url"]
    assert json.loads(row(m.sv.cfg, item["id"])["drawn"])["left"]["front"] == drawn.sanitise(BOAT)


def test_a_failed_new_drawing_keeps_the_old_one(made):
    m = made
    item = sorted_shoe(m)
    m.sv.draws.drain()
    old = drawn_of(m, item)
    m.c.post(f"/api/items/{item['id']}/drawn")
    m.drawer.error = drawn.DrawingError("Nothing drawable is left in the drawing.")
    m.sv.draws.drain()
    got = drawn_of(m, item)
    assert got["state"] == "failed" and got["message"] == shoedraw.FAILED and got["url"] == old["url"]
    assert len(m.drawer.calls) == 1 + shoedraw.MAX_ATTEMPTS


def test_draw_on_a_shoe_kept_from_before_sorts_its_photos_first(made):
    m = made
    item = a_shoe(m.c)   # never sorted: a shoe kept from before
    assert get(m.c, item)["views"]["state"] is None
    got = m.c.post(f"/api/items/{item['id']}/drawn").json()
    assert got["views"]["state"] == "waiting" and got["drawn"]["state"] == "waiting"
    assert got["drawn"]["message"] == shoedraw.WAIT_SORT
    assert m.sv.draws.drain() == 0
    m.sorter.reply = answer(("outer", True))
    m.sv.views.drain(now=later())
    assert m.sv.draws.drain() == 1 and drawn_of(m, item)["state"] == "done"


def test_draw_after_the_photos_could_not_be_sorted_sorts_them_again(made):
    m = made
    item = a_shoe(m.c)
    add(m.c, item, 1)
    m.sorter.error = TaggingError("outside the schema")
    m.sv.views.drain(now=later())
    assert get(m.c, item)["views"]["state"] == "failed"
    m.sorter.error = None
    got = m.c.post(f"/api/items/{item['id']}/drawn").json()
    assert got["views"]["state"] == "waiting"


def test_only_a_shoe_and_never_the_demo_closet(made):
    m = made
    plain = upload(m.c, key="k2").json()
    m.c.patch(f"/api/items/{plain['id']}", json={"category": "tee"})
    r = m.c.post(f"/api/items/{plain['id']}/drawn")
    assert r.status_code == 409 and r.json()["detail"] == shoedraw.NOT_A_SHOE
    assert get(m.c, plain)["drawn"] is None
    assert m.c.post("/api/items/nope/drawn").status_code == 404
    assert m.c.post("/api/profile", json={"profile": "demo"}).status_code == 200
    shoe = next(i for i in m.c.get("/api/items").json()["items"] if i["category"] in tracejobs.SHOES)
    r = m.c.post(f"/api/items/{shoe['id']}/drawn")
    assert r.status_code == 409 and r.json()["detail"] == shoedraw.DEMO
    sql_demo = db.connect(m.sv.cfg.db_path("demo"))
    sql_demo.execute("UPDATE items SET drawn_state = 'waiting', views_state = 'sorted' WHERE id = ?", (shoe["id"],))
    sql_demo.close()
    assert m.sv.draws.drain() == 0 and m.drawer.calls == []   # never sent to Claude, even if one waited


# ------------------------------------------------------------------ Claude out of reach, or failing

def test_claude_out_of_reach_puts_the_shoe_back_with_its_attempt(made):
    m = made
    item = sorted_shoe(m)
    m.drawer.error = RouteUnavailable("Claude Code is not signed in")
    assert m.sv.draws.drain() == 0
    got = drawn_of(m, item)
    assert got["state"] == "waiting" and got["message"] == shoedraw.NO_ROUTE
    assert row(m.sv.cfg, item["id"])["drawn_attempts"] == 0
    m.drawer.error = CapReached("this month's spending limit for the API key has been reached")
    m.sv.draws.drain()
    assert drawn_of(m, item)["message"] == shoedraw.LIMIT and row(m.sv.cfg, item["id"])["drawn_attempts"] == 0
    m.routes["now"] = ()   # no route at all: Claude is not even asked
    calls = len(m.drawer.calls)
    m.sv.draws.drain()
    assert len(m.drawer.calls) == calls and drawn_of(m, item)["message"] == shoedraw.NO_ROUTE
    m.routes["now"] = ("plan",)
    m.drawer.error = None
    assert m.sv.draws.drain() == 1 and drawn_of(m, item)["state"] == "done" and drawn_of(m, item)["message"] is None


def test_a_network_outage_keeps_the_shoe_waiting_with_its_tries(made):
    # no network or Anthropic overloaded: every try of the run fails to reach Claude, which is not the shoe's fault
    from closet.tagger.tagging import Unreachable
    m = made
    item = sorted_shoe(m)
    m.drawer.error = Unreachable("Claude could not be reached")
    for _ in range(shoedraw.MAX_ATTEMPTS + 2):
        assert m.sv.draws.drain() == 0
    got = drawn_of(m, item)
    assert got["state"] == "waiting" and got["message"] == shoedraw.NO_ROUTE
    assert row(m.sv.cfg, item["id"])["drawn_attempts"] == 0
    m.drawer.error = None
    assert m.sv.draws.drain() == 1 and drawn_of(m, item)["state"] == "done"


def test_after_three_failures_the_item_says_so(made, caplog):
    m = made
    item = sorted_shoe(m)
    m.drawer.error = TaggingError("the answer was outside the schema")
    with caplog.at_level(logging.WARNING, logger="closet.failures"):
        m.sv.draws.drain()
    assert len(m.drawer.calls) == shoedraw.MAX_ATTEMPTS == 3
    got = drawn_of(m, item)
    assert got["state"] == "failed" and got["message"] == shoedraw.FAILED and got["url"] is None
    assert "drawing from its photos failed" in caplog.text
    assert m.sv.draws.drain() == 0   # not tried again until the owner asks
    m.drawer.error = None
    m.c.post(f"/api/items/{item['id']}/drawn")   # "Try again"
    assert m.sv.draws.drain() == 1 and drawn_of(m, item)["state"] == "done"


def test_a_missing_photo_file_fails_at_once_with_a_plain_message(made):
    m = made
    item = sorted_shoe(m)
    one = get(m.c, item)["photos"][1]
    (m.sv.cfg.images_dir("main") / one["url"].removeprefix("/media/")).unlink()
    m.sv.draws.drain()
    assert drawn_of(m, item)["message"] == shoedraw.NO_PHOTO and m.drawer.calls == []


def test_a_drawing_interrupted_by_a_quit_starts_again(made):
    m = made
    item = sorted_shoe(m)
    sql(m.sv.cfg, "UPDATE items SET drawn_state = 'drawing' WHERE id = ?", (item["id"],))
    assert m.sv.draws.drain() == 1 and drawn_of(m, item)["state"] == "done"


def test_a_drawing_cut_short_at_every_start_is_not_paid_for_for_ever(made):
    m = made
    item = sorted_shoe(m)
    sql(m.sv.cfg, "UPDATE items SET drawn_state = 'drawing', drawn_attempts = ? WHERE id = ?", (shoedraw.MAX_ATTEMPTS, item["id"]))
    assert m.sv.draws.drain() == 0 and m.drawer.calls == []
    assert drawn_of(m, item)["state"] == "failed" and drawn_of(m, item)["message"] == shoedraw.FAILED


def test_a_shoe_deleted_while_it_is_drawn_is_left_alone(made):
    m = made
    item = sorted_shoe(m)
    m.drawer.during = lambda: m.c.delete(f"/api/items/{item['id']}")
    assert m.sv.draws.drain() == 1
    assert m.c.get(f"/api/items/{item['id']}").status_code == 404


# ------------------------------------------------------------------ two shoes at once

def shoes(m, n: int) -> list[dict]:
    """`n` shoes waiting to be drawn, each with a second photo of its own, sorted."""
    items = [a_shoe(m.c, f"k{i}") for i in range(1, n + 1)]
    for i, item in enumerate(items, 1):
        assert add(m.c, item, i).status_code == 201
    m.sorter.reply = answer(("outer", True), ("inner", True))
    m.sv.views.drain(now=later())
    assert all(row(m.sv.cfg, i["id"])["drawn_state"] == "waiting" for i in items)
    return items


def test_two_shoes_due_are_drawn_at_the_same_time(made):
    m = made
    items = shoes(m, 2)
    together = threading.Barrier(2, timeout=10)   # passed only when both drawings are under way
    m.drawer.during = together.wait
    assert m.sv.draws.drain() == 2
    assert [drawn_of(m, i)["state"] for i in items] == ["done", "done"] and len(m.drawer.calls) == 2


def test_three_shoes_are_never_drawn_more_than_two_at_once_nor_one_twice(made):
    m = made
    items = shoes(m, 3)
    lock, now, most = threading.Lock(), [0], [0]

    def during():
        with lock:
            now[0] += 1
            most[0] = max(most[0], now[0])
        time.sleep(0.3)
        with lock:
            now[0] -= 1
    m.drawer.during = during
    assert m.sv.draws.drain() == 3
    assert most[0] == shoedraw.AT_ONCE == 2
    assert len(m.drawer.calls) == 3 and all(drawn_of(m, i)["state"] == "done" for i in items)


def test_two_drains_at_once_never_draw_the_same_shoe_twice(made):
    m = made
    item = sorted_shoe(m)
    m.drawer.during = lambda: time.sleep(0.3)
    got = []
    others = [threading.Thread(target=lambda: got.append(m.sv.draws.drain())) for _ in range(2)]
    for t in others:
        t.start()
    for t in others:
        t.join(timeout=10)
    assert sorted(got) == [0, 1] and len(m.drawer.calls) == 1 and drawn_of(m, item)["state"] == "done"


def test_a_shoe_being_drawn_is_not_set_back_by_a_second_drain_or_a_wake(made):
    m = made
    item = sorted_shoe(m)
    seen = []

    def during():   # a wake, and a second drain, while the shoe is drawn
        m.sv.draws.wake()
        second = threading.Thread(target=lambda: seen.append(m.sv.draws.drain()))
        second.start()
        second.join(timeout=10)
        seen.append(row(m.sv.cfg, item["id"])["drawn_state"])
    m.drawer.during = during
    assert m.sv.draws.drain() == 1
    assert seen == [0, "drawing"] and len(m.drawer.calls) == 1
    assert drawn_of(m, item)["state"] == "done" and row(m.sv.cfg, item["id"])["drawn_attempts"] == 0


def test_a_shoe_that_becomes_due_during_a_drawing_is_started_at_once(made):
    m = made
    first = sorted_shoe(m, key="k1")
    second = a_shoe(m.c, "k2")
    assert add(m.c, second, 2).status_code == 201
    together = threading.Barrier(2, timeout=10)

    def during():
        if len(m.drawer.calls) == 1:   # the first shoe: the second is sorted, the worker woken, both meet
            m.sv.views.drain(now=later())
            m.sv.draws.wake()
        together.wait()
    m.drawer.during = during
    assert m.sv.draws.drain() == 2
    assert drawn_of(m, first)["state"] == "done" and drawn_of(m, second)["state"] == "done"


def test_out_of_reach_stops_both_and_keeps_their_attempts(made):
    m = made
    items = shoes(m, 3)
    m.drawer.error = CapReached("this month's spending limit for the API key has been reached")
    assert m.sv.draws.drain() == 0
    assert len(m.drawer.calls) <= shoedraw.AT_ONCE   # stopped for now, not tried over and over
    for i in items:
        assert drawn_of(m, i)["state"] == "waiting" and drawn_of(m, i)["message"] == shoedraw.LIMIT
        assert row(m.sv.cfg, i["id"])["drawn_attempts"] == 0


def test_out_of_reach_lets_the_other_shoe_finish(made):
    m = made
    items = shoes(m, 2)
    gone = threading.Event()
    first = threading.Lock()   # taken once and kept: the two are drawn at the same time, so counting calls can miss

    def during():
        if first.acquire(blocking=False):   # the first is held up; the second is finished after it
            gone.set()
            raise RouteUnavailable("Claude Code is not signed in")
        assert gone.wait(timeout=10)
    m.drawer.during = during
    assert m.sv.draws.drain() == 1
    states = sorted(drawn_of(m, i)["state"] for i in items)
    assert states == ["done", "waiting"] and len(m.drawer.calls) == 2
    assert all(row(m.sv.cfg, i["id"])["drawn_attempts"] == 0 for i in items)


# ------------------------------------------------------------------ the drawing on two legs

def test_drawn_svg_serves_the_pair_on_two_legs_behind_the_login(made):
    m = made
    item = sorted_shoe(m)
    assert m.c.get(f"/api/items/{item['id']}/drawn.svg").status_code == 404
    m.sv.draws.drain()
    r = m.c.get(drawn_of(m, item)["url"])
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml")
    assert r.headers["cache-control"] == "no-store" and "default-src 'none'" in r.headers["content-security-policy"]
    assert r.text == drawn.preview_svg(drawn.sanitise(DRESS)) and r.text.count(drawn.PREVIEW_SOCK) == 2
    anon = TestClient(app_module.create_app(m.sv))
    assert anon.get(f"/api/items/{item['id']}/drawn.svg").status_code == 401
    assert anon.post(f"/api/items/{item['id']}/drawn").status_code == 401


def test_a_shoe_only_has_drawn_details(made):
    m = made
    plain = upload(m.c, key="k3").json()
    assert get(m.c, plain)["drawn"] is None   # not described yet: not a shoe
    item = a_shoe(m.c, key="k4")
    # step E added what the page needs for the owner's correction, and going back to the drawing before
    assert set(drawn_of(m, item)) == {"state", "message", "url", "rounds", "seconds", "cost_usd", "route", "made_at",
                                      "photos_changed", "about_usd", "correcting", "note", "corrected", "changed",
                                      "against_photos", "has_previous", "previous_newer", "side", "side_shown"}
    assert drawn_of(m, item)["about_usd"] == shoedraw.ABOUT_USD
    assert drawn_of(m, item)["side"] is None and drawn_of(m, item)["side_shown"] is False
    assert {k: drawn_of(m, item)[k] for k in ("correcting", "note", "corrected", "changed", "against_photos",
                                              "has_previous", "previous_newer")} == {
        "correcting": False, "note": None, "corrected": False, "changed": None, "against_photos": None,
        "has_previous": False, "previous_newer": False}


# ------------------------------------------------------------------ through the API key and its monthly limit

def test_drawing_goes_through_the_api_key_and_its_monthly_limit(cfg, cut_clock):
    api = FakeApi(input_tokens=20_000, output_tokens=5_000)
    api.cache_write, api.cache_read = 1_000, 4_000   # each request writes some of the photos to the cache, reads some
    sorter = Sorter()
    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, routes=lambda: ("api",), api_client=api,
                                   sorter=lambda photos, routes: sorter.reply(len(photos)) if callable(sorter.reply)
                                   else sorter.reply)
    try:
        c = TestClient(app_module.create_app(sv))
        assert c.post("/api/setup", json={"passphrase": PASSPHRASE}).status_code == 204
        item = a_shoe(c)
        add(c, item, 1)
        sorter.reply = answer(("outer", True), ("inner", True))
        sv.views.drain(now=later())
        c.put("/api/settings", json={"tagging_api_enabled": True, "tagging_api_cap_usd": 0.5})
        sv.draws.drain()
        assert api.calls == 0   # the estimate is checked first: nothing is sent past the limit
        assert get(c, item)["drawn"]["message"] == shoedraw.LIMIT
        c.put("/api/settings", json={"tagging_api_cap_usd": 20.0})
        # two candidates and a check each, the judge, two turns and a check each, the judge again (no fault named:
        # no fix); beside the turns, the side and its check, counted in the drawing's calls and its cost
        calls = SD.CANDIDATES * 2 + 1 + SD.TURNS * 2 + 1 + 2
        assert sv.draws.drain() == 1 and api.calls == calls == 12
        # every request is cached up to its last photo (the shoe's two photos come first in each), and nowhere else
        for request in api.requests:
            content = request["messages"][0]["content"]
            marked = [i for i, block in enumerate(content) if "cache_control" in block]
            assert marked == [3] and content[3]["type"] == "image" and content[2]["text"] == "photo-2.jpg:"
            assert content[3]["cache_control"] == {"type": "ephemeral"}
        got = get(c, item)["drawn"]
        assert got["state"] == "done" and got["route"] == "api" and got["rounds"] == SD.CANDIDATES + SD.TURNS
        # what the cache wrote and read is counted at its own price, in the drawing's cost and in the month's spend
        one = spend.cost_usd(SD.MODEL, 20_000, 5_000, cache_write=1_000, cache_read=4_000)
        assert one == pytest.approx(spend.cost_usd(SD.MODEL, 20_000, 5_000) + (1_000 * 4.00 * 1.25 + 4_000 * 0.20) / 1e6)
        # each check says good and stops being read there, the side's too: its output is estimated from its time
        cut = SD.CANDIDATES + SD.TURNS + 1
        short = spend.cost_usd(SD.MODEL, 20_000, CUT, cache_write=1_000, cache_read=4_000)
        assert [s["whole"] for s in api.streams].count(False) == cut
        assert got["cost_usd"] == pytest.approx((calls - cut) * one + cut * short)
        with closing(db.connect(cfg.db_path("main"))) as conn:
            rows = [dict(r) for r in conn.execute("SELECT purpose, route, model, input_tokens, cost_usd FROM "
                                                  "claude_calls WHERE purpose = 'draw_shoe'")]
            month = spend.spent(conn)
        assert len(rows) == calls and spend.PURPOSE_DRAW == "draw_shoe"
        assert all(r["route"] == "api" and r["model"] == SD.MODEL for r in rows)
        assert all(r["input_tokens"] == 25_000 for r in rows)
        assert sorted(round(r["cost_usd"], 9) for r in rows) == pytest.approx(sorted([one] * (calls - cut) + [short] * cut))
        assert month >= (calls - cut) * one + cut * short - 1e-9
        assert spend.estimate_draw(8) > 0.5   # one request's careful estimate is over the first limit
    finally:
        sv.stop()


def test_the_drawer_is_told_the_shoes_style_from_its_description(made):
    """The drawing is turned with the 3D shoe of the item's own style, as its description says it."""
    m = made
    item = a_shoe(m.c)
    sql(m.sv.cfg, "UPDATE items SET tag_answer = ? WHERE id = ?",
        (json.dumps(tags("sneakers", "high_top", {"height": "high"})), item["id"]))
    add(m.c, item, 1)
    m.sorter.reply = answer(("outer", True), ("inner", True))
    m.sv.views.drain(now=later())
    assert m.sv.draws.drain() == 1
    assert m.drawer.styles == ["high_top"] == [shoedraw.style_of(row(m.sv.cfg, item["id"]))]
