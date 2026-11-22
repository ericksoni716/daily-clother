"""A shoe's photos sorted into views (shoes drawn from understanding, step B): adding up to five more photos and
removing them, the sorting in the background (`closet/shoeviews.py`) with its quiet period, the owner's answers,
the question about the outside, the photo read for the front view, and Claude out of reach or failing.

Claude is never called: a stand-in sorter answers in the tests of the queue, and the API route and the plan route
are stood in for (`conftest.FakeApi`, and a stand-in for `subprocess.run`) in the tests of the call itself.
"""
import json
import logging
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from closet import app as app_module
from closet import db, shoeviews, spend, tracejobs
from closet.tagger import correcting
from closet.tagger import views as tagger_views
from closet.tagger.tagging import CapReached, RouteUnavailable, TaggingError
from closet.tagger.views import PhotoView, ShoeViews

from .conftest import PASSPHRASE, FakeApi, FakeClaude, fake_cutter, photo_bytes, upload, views_answer

MAIN = (900, 1200)    # the size of the main photo `upload` sends
EXTRA = (640, 480)    # the size of the other photos these tests add


def later() -> datetime:
    """The clock once the newest photo has been quiet long enough."""
    return datetime.now(UTC) + timedelta(seconds=shoeviews.SORT_QUIET + 1)


def answer(*views, differ=False) -> ShoeViews:
    """Claude's answer: one (view, sure) per photo, in the order sent."""
    return ShoeViews(photos=[PhotoView(photo=n, view=v, sure=s) for n, (v, s) in enumerate(views, 1)],
                     sides_differ=differ)


class Sorter:
    """Stands in for Claude sorting the photos: `answer` (a ShoeViews, or a function of the number of photos), or
    raises `error`. `calls` keeps the sizes of the photos it was sent, in order."""

    def __init__(self, reply=None):
        self.reply = reply or views_answer
        self.error: Exception | None = None
        self.calls: list[list[tuple[int, int]]] = []

    def __call__(self, photos, routes):
        self.calls.append([p.size for p in photos])
        assert routes == ("plan",)
        if self.error:
            raise self.error
        return self.reply(len(photos)) if callable(self.reply) else self.reply


@pytest.fixture
def sorter():
    return Sorter()


@pytest.fixture
def made(cfg, sorter):
    claude = FakeClaude()   # never describes anything: the tests say what each item is
    routes = {"now": ("plan",)}
    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, tagger=claude, routes=lambda: routes["now"],
                                   sorter=sorter)
    c = TestClient(app_module.create_app(sv))
    assert c.post("/api/setup", json={"passphrase": PASSPHRASE}).status_code == 204
    yield SimpleNamespace(sv=sv, c=c, routes=routes)
    sv.stop()


@pytest.fixture
def sv(made):
    return made.sv


@pytest.fixture
def c(made):
    return made.c


def a_shoe(c, key="k1") -> dict:
    item = upload(c, key=key).json()
    assert c.patch(f"/api/items/{item['id']}", json={"category": "sneakers"}).status_code == 200
    return item


def extra(n: int) -> bytes:
    return photo_bytes(size=EXTRA, color=(30 + 25 * n, 200 - 20 * n, 90 + 15 * n))


def add(c, item, n: int, view=None):
    data = {"view": view} if view else {}
    return c.post(f"/api/items/{item['id']}/photos", files={"photo": (f"x{n}.jpg", extra(n), "image/jpeg")}, data=data)


def get(c, item) -> dict:
    return c.get(f"/api/items/{item['id']}").json()


def photos(c, item) -> list[tuple]:
    return [(p["kind"], p["view"], p["view_sure"], p["view_by"]) for p in get(c, item)["photos"]]


def row(cfg, item_id) -> dict:
    with closing(db.connect(cfg.db_path("main"))) as conn:
        return dict(conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone())


def sql(cfg, query, args=()):
    with closing(db.connect(cfg.db_path("main"))) as conn:
        conn.execute(query, args)


# ------------------------------------------------------------------ the migration

def test_the_migration_adds_the_columns_and_keeps_the_second_photos_as_the_owners(cfg):
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    with closing(db.connect(cfg.db_path("main"))) as conn:
        for v, path in db.migration_files():
            if v <= 25:
                conn.executescript(f"BEGIN IMMEDIATE;\n{path.read_text(encoding='utf-8')}\nPRAGMA user_version = {v};\nCOMMIT;")
        conn.execute("INSERT INTO items (id, category, created_at, updated_at) VALUES ('s', 'sneakers', ?, ?)",
                     (db.now(), db.now()))
        for pid, kind, view in (("main", "front", None), ("second", "detail", "top")):
            conn.execute("INSERT INTO photos (id, item_id, kind, view, original_path, thumb_path, created_at) "
                         "VALUES (?, 's', ?, ?, ?, ?, ?)", (pid, kind, view, f"s/{pid}.webp", f"s/{pid}-t.webp", db.now()))
    db.migrate(cfg.db_path("main"), cfg.local_backups_dir)
    with closing(db.connect(cfg.db_path("main"))) as conn:
        assert {"view_sure", "view_by"} <= {r[1] for r in conn.execute("PRAGMA table_info(photos)")}
        cols = {r[1]: r for r in conn.execute("PRAGMA table_info(items)")}
        assert {"views_state", "views_error", "views_attempts", "sides_differ"} <= set(cols)
        assert cols["views_attempts"][4] == "0"
        got = {r["id"]: (r["view"], r["view_sure"], r["view_by"]) for r in conn.execute("SELECT * FROM photos")}
        assert got == {"main": (None, None, None), "second": ("top", 1, "owner")}   # the owner named it
        assert conn.execute("SELECT views_state FROM items").fetchone()[0] is None   # not sorted: no backfill


# ------------------------------------------------------------------ adding and removing photos

def test_up_to_five_more_photos_then_a_plain_refusal(c):
    item = a_shoe(c)
    for n in range(shoeviews.MAX_EXTRA):
        r = add(c, item, n)
        assert r.status_code == 201, r.text
    got = get(c, item)
    assert [(p["kind"], p["view"]) for p in got["photos"]] == [("front", None)] + [("detail", None)] * 5
    assert got["views"] == {"state": "waiting", "message": shoeviews.WAITING, "asking": None}
    r = add(c, item, 9)
    assert r.status_code == 409 and r.json()["detail"] == "A shoe can have at most 5 more photos besides its main one. Remove one first."
    assert len(get(c, item)["photos"]) == 6
    # with one removed, there is room again
    c.delete(f"/api/items/{item['id']}/photos/{got['photos'][3]['id']}")
    assert add(c, item, 9).status_code == 201


def test_the_same_photo_twice_and_a_photo_of_another_item_are_refused(c):
    item = a_shoe(c)
    assert add(c, item, 1).status_code == 201
    r = add(c, item, 1)
    assert r.status_code == 409 and r.json()["detail"] == "This photo is already one of this shoe's photos."
    from .conftest import photo_for
    r = c.post(f"/api/items/{item['id']}/photos", files={"photo": ("m.jpg", photo_for("k1"), "image/jpeg")})
    assert r.status_code == 409   # its main photo
    upload(c, key="k2")
    r = c.post(f"/api/items/{item['id']}/photos", files={"photo": ("o.jpg", photo_for("k2"), "image/jpeg")})
    assert r.status_code == 409 and "another item" in r.json()["detail"]
    assert len(get(c, item)["photos"]) == 2


def test_a_photo_named_front_or_top_is_the_owners_and_replaces_only_its_own(cfg, c):
    item = a_shoe(c)
    add(c, item, 1)
    add(c, item, 2, view="front")
    add(c, item, 3, view="top")
    first_front = next(p for p in get(c, item)["photos"] if p["view"] == "front")
    assert photos(c, item) == [("front", None, None, None), ("detail", None, None, None),
                               ("detail", "front", True, "owner"), ("detail", "top", True, "owner")]
    r = add(c, item, 4, view="front")
    assert r.status_code == 201
    assert photos(c, item) == [("front", None, None, None), ("detail", None, None, None),
                               ("detail", "top", True, "owner"), ("detail", "front", True, "owner")]
    assert first_front["id"] not in {p["id"] for p in get(c, item)["photos"]}
    assert not (cfg.images_dir("main") / first_front["url"].removeprefix("/media/")).exists()   # its files went
    assert add(c, item, 5, view="side").status_code == 422
    # a photo the owner named counts against the five, and replacing one still fits when the shoe is full
    add(c, item, 6)
    add(c, item, 7)
    assert add(c, item, 8).status_code == 409
    assert add(c, item, 8, view="top").status_code == 201


def test_only_a_shoe_or_an_item_not_described_yet_can_have_more_photos(c):
    waiting = upload(c, key="k1").json()   # just added from "A shoe": Claude has not said what it is yet
    assert add(c, waiting, 1).status_code == 201
    assert get(c, waiting)["views"] is None   # shown once it is known to be a shoe
    polo = upload(c, key="k2").json()
    c.patch(f"/api/items/{polo['id']}", json={"category": "polo"})
    r = add(c, polo, 2)
    assert r.status_code == 409 and r.json()["detail"] == "Only a shoe can have more photos."


def test_an_extra_photo_is_removed_with_its_files_never_the_main_one(cfg, c, sv):
    item = a_shoe(c)
    add(c, item, 1)
    add(c, item, 2)
    sv.views.drain(now=later())
    assert get(c, item)["views"]["state"] == "asking"
    main, one, two = get(c, item)["photos"]
    r = c.delete(f"/api/items/{item['id']}/photos/{one['id']}")
    assert r.status_code == 200
    got = r.json()
    assert [p["id"] for p in got["photos"]] == [main["id"], two["id"]]
    assert got["views"]["state"] == "waiting"   # sorted again, without it
    for key in ("url", "thumb_url"):
        assert not (cfg.images_dir("main") / one[key].removeprefix("/media/")).exists()
    r = c.delete(f"/api/items/{item['id']}/photos/{main['id']}")
    assert r.status_code == 409 and "Retake the photo" in r.json()["detail"]
    assert c.delete(f"/api/items/{item['id']}/photos/nothing").status_code == 404
    other = a_shoe(c, key="k2")
    assert c.delete(f"/api/items/{other['id']}/photos/{two['id']}").status_code == 404   # not that item's photo
    assert len(get(c, item)["photos"]) == 2


def test_the_photo_endpoints_need_the_login(cfg):
    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, tagger=FakeClaude(), routes=lambda: ())
    try:
        anon = TestClient(app_module.create_app(sv))
        assert anon.post("/api/items/x/photos", files={"photo": ("s.jpg", b"x", "image/jpeg")}).status_code == 401
        assert anon.delete("/api/items/x/photos/y").status_code == 401
        assert anon.put("/api/items/x/photos/y/view", json={"view": "outer"}).status_code == 401
    finally:
        sv.stop()


# ------------------------------------------------------------------ sorting

def test_sorting_waits_until_the_newest_photo_is_quiet(c, sv, sorter):
    item = a_shoe(c)
    add(c, item, 1)
    assert sv.views.drain() == 0 and sorter.calls == []
    assert 0 < sv.views.soon <= shoeviews.SORT_QUIET   # it is sorted as soon as the photo is quiet, not later
    assert get(c, item)["views"]["state"] == "waiting"
    assert sv.views.drain(now=later()) == 1
    assert sorter.calls == [[MAIN, EXTRA]]   # every photo in one call, the main one first
    assert sv.views.soon is None


def test_sorting_applies_the_answer(c, sv, sorter):
    item = a_shoe(c)
    add(c, item, 1)
    add(c, item, 2)
    sorter.reply = answer(("outer", True), ("top", True), ("inner", False), differ=False)
    sv.views.drain(now=later())
    got = get(c, item)
    assert [(p["view"], p["view_sure"], p["view_by"]) for p in got["photos"]] == [
        ("outer", True, "model"), ("top", True, "model"), ("inner", False, "model")]
    assert got["views"] == {"state": "sorted", "message": None, "asking": None}   # the sides look alike: nothing to ask
    assert row(sv.cfg, item["id"])["sides_differ"] == 0


def test_a_shoe_with_only_its_main_photo_is_sorted_too(c, sv, sorter):
    item = a_shoe(c)
    other = add(c, item, 1).json()["photos"][1]
    c.delete(f"/api/items/{item['id']}/photos/{other['id']}")
    sorter.reply = answer(("outer", True))
    assert sv.views.drain(now=later()) == 1 and sorter.calls == [[MAIN]]
    assert photos(c, item) == [("front", "outer", True, "model")]


def test_the_owners_answers_are_never_overwritten(c, sv, sorter):
    item = a_shoe(c)
    add(c, item, 1, view="front")   # named by the owner on adding it
    add(c, item, 2)
    sorter.reply = answer(("outer", True), ("top", True), ("back", True))
    sv.views.drain(now=later())
    assert photos(c, item) == [("front", "outer", True, "model"), ("detail", "front", True, "owner"),
                               ("detail", "back", True, "model")]
    third = get(c, item)["photos"][2]
    c.put(f"/api/items/{item['id']}/photos/{third['id']}/view", json={"view": "sole"})
    add(c, item, 3)
    sorter.reply = answer(("inner", True), ("back", True), ("front", True), ("top", True))
    sv.views.drain(now=later())
    assert photos(c, item) == [("front", "inner", True, "model"), ("detail", "front", True, "owner"),
                               ("detail", "sole", True, "owner"), ("detail", "top", True, "model")]


def test_a_photo_added_while_sorting_is_sorted_again_with_it(c, sv, sorter):
    item = a_shoe(c)
    add(c, item, 1)
    seen = {}

    def meanwhile(count):
        if len(sorter.calls) == 1:
            add(c, item, 2)   # the owner adds another photo while Claude is looking at the first two
            return answer(*[("outer", True)] * count)
        seen["before"] = [(p["view"], get(c, item)["views"]["state"]) for p in get(c, item)["photos"]]
        return answer(*[("top", True)] * count)
    sorter.reply = meanwhile
    sv.views.drain(now=later())
    assert sorter.calls == [[MAIN, EXTRA], [MAIN, EXTRA, EXTRA]]
    assert seen["before"] == [(None, "sorting")] * 3   # the first answer was set aside, not applied
    assert [p["view"] for p in get(c, item)["photos"]] == ["top"] * 3


# ------------------------------------------------------------------ when the owner is asked

S, U = True, False   # sure, unsure


@pytest.mark.parametrize("views,differ,asked", [
    ([("outer", S), ("inner", S)], True, None),                   # sides that look different, both sure
    ([("outer", U), ("inner", U)], False, None),                  # unsure, but the sides look alike: it does not matter
    ([("outer", U), ("inner", S)], True, [0, 1]),                 # one side unsure
    ([("outer", S), ("top", S), ("outer", S)], True, [0, 2]),     # two photos claim the same side
    ([("inner", U)], True, [0]),                                  # one side photo, unsure: asked about it alone
    ([("outer", S)], True, None),                                 # one side photo, sure
    ([("top", U), ("front", U)], True, None),                     # no side photo: nothing to ask
    ([("outer", S), ("inner", S), ("back", U)], True, None),      # unsure, but not about a side
])
def test_the_owner_is_asked_only_when_the_sides_differ_and_claude_could_not_tell(c, sv, sorter, views, differ, asked):
    item = a_shoe(c)
    for n in range(len(views) - 1):
        add(c, item, n)
    if len(views) == 1:   # its main photo alone: one added and removed again
        c.delete(f"/api/items/{item['id']}/photos/{add(c, item, 9).json()['photos'][1]['id']}")
    sorter.reply = answer(*views, differ=differ)
    sv.views.drain(now=later())
    got = get(c, item)
    ids = [p["id"] for p in got["photos"]]
    if asked is None:
        assert got["views"] == {"state": "sorted", "message": None, "asking": None}
    else:
        assert got["views"] == {"state": "asking", "message": None, "asking": [ids[i] for i in asked]}


def test_the_owner_says_which_photo_shows_the_outside(c, sv, sorter):
    item = a_shoe(c)
    add(c, item, 1)
    add(c, item, 2)
    sv.views.drain(now=later())   # the stand-in: outer (unsure), top, inner (unsure), the sides differ
    got = get(c, item)
    main, top, side = (p["id"] for p in got["photos"])
    assert got["views"]["state"] == "asking" and got["views"]["asking"] == [main, side]
    r = c.put(f"/api/items/{item['id']}/photos/{side}/view", json={"view": "outer"})
    assert r.status_code == 200
    got = r.json()
    # the other side follows; the outer side becomes the main photo (`promote`), the main one before stays the inner
    assert [(p["id"], p["view"], p["view_sure"], p["view_by"]) for p in got["photos"]] == [
        (side, "outer", True, "owner"), (main, "inner", True, "owner"), (top, "top", True, "model")]
    assert got["views"] == {"state": "sorted", "message": None, "asking": None}
    # sorting again later keeps the owner's answers (sent in their new order, so the stand-in is told the views)
    add(c, item, 3)
    sorter.reply = answer(("inner", U), ("outer", U), ("top", S), ("front", S))
    sv.views.drain(now=later())
    got = get(c, item)
    assert [(p["view"], p["view_by"]) for p in got["photos"]] == [
        ("outer", "owner"), ("inner", "owner"), ("top", "model"), ("front", "model")]
    assert got["views"]["state"] == "sorted"


def test_with_one_side_photo_the_owner_says_outside_or_inside(c, sv, sorter):
    item = a_shoe(c)
    add(c, item, 1)
    sorter.reply = answer(("outer", U), ("top", S), differ=True)
    sv.views.drain(now=later())
    got = get(c, item)
    main = got["photos"][0]["id"]
    assert got["views"]["asking"] == [main]
    got = c.put(f"/api/items/{item['id']}/photos/{main}/view", json={"view": "inner"}).json()
    assert [(p["view"], p["view_by"]) for p in got["photos"]] == [("inner", "owner"), ("top", "model")]
    assert got["views"]["state"] == "sorted"


def test_a_later_photo_of_the_same_side_as_the_owners_is_asked_about(c, sv, sorter):
    item = a_shoe(c)
    add(c, item, 1)
    sorter.reply = answer(("outer", U), ("inner", U), differ=True)
    sv.views.drain(now=later())
    main, side = (p["id"] for p in get(c, item)["photos"])
    c.put(f"/api/items/{item['id']}/photos/{main}/view", json={"view": "outer"})
    added = add(c, item, 2).json()["photos"][-1]["id"]
    sorter.reply = answer(("outer", S), ("inner", S), ("outer", S), differ=True)   # (the first two are the owner's)
    sv.views.drain(now=later())
    assert get(c, item)["views"]["asking"] == [added]
    got = c.put(f"/api/items/{item['id']}/photos/{added}/view", json={"view": "other"}).json()
    assert got["views"]["state"] == "sorted"


def test_the_owners_answer_is_checked(c, sv):
    item = a_shoe(c)
    photo = get(c, item)["photos"][0]["id"]
    url = f"/api/items/{item['id']}/photos/{photo}/view"
    assert c.put(url, json={"view": "sideways"}).status_code == 422
    assert c.put(url, json={}).status_code == 422
    assert c.put(url, content=b"not json", headers={"content-type": "application/json"}).status_code == 400
    assert c.put(f"/api/items/{item['id']}/photos/nothing/view", json={"view": "outer"}).status_code == 404
    polo = upload(c, key="k2").json()
    c.patch(f"/api/items/{polo['id']}", json={"category": "polo"})
    polo_photo = get(c, polo)["photos"][0]["id"]
    assert c.put(f"/api/items/{polo['id']}/photos/{polo_photo}/view", json={"view": "outer"}).status_code == 409
    got = c.put(url, json={"view": "outer"}).json()   # an answer before anything was sorted is kept as it is
    assert got["photos"][0]["view_by"] == "owner" and got["views"]["state"] is None


# ------------------------------------------------------------------ Claude out of reach, or failing

def test_claude_out_of_reach_puts_the_shoe_back_with_its_attempt(cfg, made, sorter):
    sv, c = made.sv, made.c
    item = a_shoe(c)
    add(c, item, 1)
    sorter.error = RouteUnavailable("Claude Code is not signed in")
    assert sv.views.drain(now=later()) == 0
    got = get(c, item)
    assert got["views"] == {"state": "waiting", "message": shoeviews.NO_ROUTE, "asking": None}
    assert row(cfg, item["id"])["views_attempts"] == 0
    sorter.error = CapReached("this month's spending limit for the API key has been reached")
    sv.views.drain(now=later())
    assert get(c, item)["views"]["message"] == shoeviews.LIMIT and row(cfg, item["id"])["views_attempts"] == 0
    made.routes["now"] = ()   # no route at all: Claude is not even asked
    calls = len(sorter.calls)
    sv.views.drain(now=later())
    assert len(sorter.calls) == calls and get(c, item)["views"]["message"] == shoeviews.NO_ROUTE
    made.routes["now"] = ("plan",)
    sorter.error = None
    assert sv.views.drain(now=later()) == 1
    assert get(c, item)["views"] == {"state": "sorted", "message": None, "asking": None}


def test_after_three_failures_the_item_says_so(cfg, c, sv, sorter, caplog):
    item = a_shoe(c)
    add(c, item, 1)
    sorter.error = TaggingError("the answer was outside the schema")
    with caplog.at_level(logging.WARNING, logger="closet.failures"):
        sv.views.drain(now=later())
    assert len(sorter.calls) == shoeviews.MAX_ATTEMPTS == 3
    assert get(c, item)["views"] == {"state": "failed", "message": shoeviews.FAILED, "asking": None}
    assert "sorting of its photos failed" in caplog.text
    assert sv.views.drain(now=later()) == 0   # not tried again until a photo is added or removed
    sorter.error = None
    add(c, item, 2)
    sv.views.drain(now=later())
    assert get(c, item)["views"]["state"] == "asking"


def test_an_answer_that_does_not_name_every_photo_once_counts_as_a_failure(c, sv, sorter):
    item = a_shoe(c)
    add(c, item, 1)
    sorter.reply = answer(("outer", True))   # one photo of two
    sv.views.drain(now=later())
    assert get(c, item)["views"]["state"] == "failed" and len(sorter.calls) == 3
    with pytest.raises(ValueError):
        shoeviews.read(ShoeViews(photos=[PhotoView(photo=1, view="top", sure=True)] * 2, sides_differ=False), 2)
    with pytest.raises(ValueError):
        shoeviews.read(answer(("top", True), ("top", True), ("top", True)), 2)


def test_a_missing_photo_file_fails_at_once_with_a_plain_message(cfg, c, sv, sorter):
    item = a_shoe(c)
    one = add(c, item, 1).json()["photos"][1]
    (cfg.images_dir("main") / one["url"].removeprefix("/media/")).unlink()
    sv.views.drain(now=later())
    assert get(c, item)["views"] == {"state": "failed", "message": shoeviews.NO_PHOTO, "asking": None}
    assert sorter.calls == []


def test_sorting_interrupted_by_a_quit_starts_again(cfg, c, sv):
    item = a_shoe(c)
    add(c, item, 1)
    sql(cfg, "UPDATE items SET views_state = 'sorting' WHERE id = ?", (item["id"],))
    assert sv.views.drain(now=later()) == 1 and get(c, item)["views"]["state"] == "sorted"


# ------------------------------------------------------------------ which shoes are sorted

def test_the_demo_closet_is_never_sent_to_claude(c, sv, sorter):
    from .test_tracejobs import jpeg
    assert c.post("/api/profile", json={"profile": "demo"}).status_code == 200
    shoe = next(i for i in c.get("/api/items").json()["items"] if i["category"] in tracejobs.SHOES)
    r = c.post(f"/api/items/{shoe['id']}/photos",
               files={"photo": ("x.jpg", jpeg(Image.new("RGB", EXTRA, (20, 90, 160))), "image/jpeg")})
    assert r.status_code == 201
    assert r.json()["views"] == {"state": None, "message": shoeviews.DEMO, "asking": None}
    assert sv.views.drain(now=later()) == 0 and sorter.calls == []


def test_a_shoe_from_add_is_sorted_once_it_is_known_to_be_a_shoe(cfg, c, sv, sorter):
    from .conftest import photo_for
    r = c.post("/api/items", files={"photo": ("p.jpg", photo_for("k1"), "image/jpeg")}, data={"client_key": "k1", "shoe": "true"})
    item = r.json()
    assert row(cfg, item["id"])["views_state"] == "waiting" and item["views"] is None
    assert sv.views.drain(now=later()) == 0   # not known to be a shoe yet
    got = c.patch(f"/api/items/{item['id']}", json={"category": "boots"}).json()
    assert got["views"]["state"] == "waiting"
    sorter.reply = answer(("inner", True))
    assert sv.views.drain(now=later()) == 1 and sorter.calls == [[MAIN]]
    assert get(c, item)["photos"][0]["view"] == "inner"
    # an item added the usual way is not
    plain = upload(c, key="k2").json()
    assert row(cfg, plain["id"])["views_state"] is None


def test_shoes_kept_before_are_not_sorted_until_a_photo_is_added(cfg, c, sv, sorter):
    item = a_shoe(c)
    assert get(c, item)["views"] == {"state": None, "message": None, "asking": None}
    assert sv.views.drain(now=later()) == 0 and sorter.calls == []
    # nor when its main photo is retaken; once sorted, a new main photo is sorted again
    from . import shoe_photos as S
    from .test_tracejobs import jpeg
    sv.worker.drain()
    c.post(f"/api/items/{item['id']}/photo", files={"photo": ("p.jpg", jpeg(S.draw()[0]), "image/jpeg")})
    assert get(c, item)["views"]["state"] is None
    sv.worker.drain()
    add(c, item, 1)
    sv.views.drain(now=later())
    assert get(c, item)["views"]["state"] == "sorted"
    sv.worker.drain()
    c.post(f"/api/items/{item['id']}/photo", files={"photo": ("q.jpg", jpeg(S.draw(noise=3)[0]), "image/jpeg")})
    got = get(c, item)
    assert got["views"]["state"] == "waiting" and got["photos"][0]["view"] is None


# ------------------------------------------------------------------ no photo is read for a front view

def test_sorting_a_photo_from_the_front_or_above_leaves_the_trace_alone(cfg, c, sv, sorter):
    """The traced front view was removed: a photo from the front or from above is no longer read for it, so sorting
    one, the owner changing its view or removing it never traces the shoe again."""
    item = a_shoe(c)
    sv.worker.drain()
    a = add(c, item, 1).json()["photos"][-1]["id"]
    b = add(c, item, 2).json()["photos"][-1]["id"]
    sql(cfg, "UPDATE items SET trace_state = 'done' WHERE id = ?", (item["id"],))
    sorter.reply = answer(("outer", True), ("top", True), ("front", True))
    sv.views.drain(now=later())
    assert row(cfg, item["id"])["trace_state"] == "done"
    c.put(f"/api/items/{item['id']}/photos/{b}/view", json={"view": "back"})
    c.delete(f"/api/items/{item['id']}/photos/{a}")
    assert row(cfg, item["id"])["trace_state"] == "done"


# ------------------------------------------------------------------ the call to Claude

def test_the_prompt_explains_the_views_and_asks_for_unsure_rather_than_a_guess():
    text = tagger_views.prompt(3)
    assert "numbered 1 to 3" in text and "Photo 1 is the main photo" in text
    assert "photo 1 too, may show any view" in text and "usually of the side" not in text   # added in any order on Add
    assert "faces away from the other shoe" in text and "arch" in text and "but not always" in text
    assert "pair" in text and "rather than guess" in text and "sides_differ" in text
    assert "There is one photo, photo 1" in tagger_views.prompt(1)
    assert tagger_views.MODEL == tagger_views.CONFIG["roles"]["sorting"]
    assert set(ShoeViews.model_json_schema()["$defs"]["PhotoView"]["properties"]["view"]["enum"]) == set(tagger_views.VIEWS)


def test_the_answer_is_strict():
    with pytest.raises(ValueError):
        ShoeViews.model_validate({"photos": [{"photo": 1, "view": "side", "sure": True}], "sides_differ": False})
    with pytest.raises(ValueError):
        ShoeViews.model_validate({"photos": [{"photo": "1", "view": "top", "sure": "yes"}], "sides_differ": False})
    with pytest.raises(ValueError):
        ShoeViews.model_validate({"photos": [], "sides_differ": False, "extra": 1})


class Meter:
    def __init__(self):
        self.checked, self.recorded = [], []

    def before_api_call(self, model, images):
        self.checked.append((model, images))

    def record(self, route, model, input_tokens, output_tokens):
        self.recorded.append((route, model, input_tokens, output_tokens))

    def api_refused(self, reason):
        pass


def test_through_the_api_key_every_photo_is_sent_in_one_request():
    api, meter = FakeApi(), Meter()
    shots = [Image.new("RGB", (2000, 1500), (200, 200, 200)), Image.new("RGB", (400, 300), (20, 20, 20))]
    got = tagger_views.ask(shots, ("api",), client=api, meter=meter)
    assert got == views_answer(2)
    sent = api.requests[0]
    assert sent["output_format"] is ShoeViews and sent["model"] == tagger_views.MODEL
    assert [part["type"] for part in sent["messages"][0]["content"]] == ["image", "image", "text"]
    assert meter.checked == [(tagger_views.MODEL, 2)] and meter.recorded == [("api", tagger_views.MODEL, 2000, 400)]


def test_through_the_plan_every_photo_is_saved_and_named(monkeypatch):
    seen = {}

    def run(cmd, cwd=None, **kw):
        seen["cmd"], seen["input"] = cmd, kw["stdin"].read().decode("utf-8")
        seen["files"] = sorted(p.name for p in Path(cwd).iterdir())
        out = {"structured_output": views_answer(3).model_dump(), "is_error": False, "result": "",
               "usage": {"input_tokens": 5000, "output_tokens": 90}}
        return SimpleNamespace(returncode=0, stdout=json.dumps(out), stderr="")
    monkeypatch.setattr(correcting.subprocess, "run", run)
    meter = Meter()
    shots = [Image.new("RGB", (300, 200), (n * 60, 90, 90)) for n in range(3)]
    got = tagger_views.ask(shots, ("plan",), exe="claude", meter=meter)
    assert got == views_answer(3)
    assert seen["files"] == ["photo-1.jpg", "photo-2.jpg", "photo-3.jpg"]
    assert "photo-1.jpg, photo-2.jpg, photo-3.jpg" in seen["input"] and "numbered 1 to 3" in seen["input"]
    assert seen["cmd"][seen["cmd"].index("--model") + 1] == tagger_views.MODEL
    assert seen["cmd"][seen["cmd"].index("--system-prompt") + 1] == tagger_views.SYSTEM
    assert meter.recorded == [("plan", tagger_views.MODEL, 5000, 90)]


def test_sorting_goes_through_the_api_key_and_its_monthly_limit(cfg):
    api = FakeApi(input_tokens=6000, output_tokens=200)
    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, routes=lambda: ("api",), api_client=api)
    try:
        c = TestClient(app_module.create_app(sv))
        assert c.post("/api/setup", json={"passphrase": PASSPHRASE}).status_code == 204
        item = a_shoe(c)
        add(c, item, 1)
        c.put("/api/settings", json={"tagging_api_enabled": True, "tagging_api_cap_usd": 0.01})
        sql(cfg, "INSERT INTO claude_calls (at, month, purpose, route, model, cost_usd) VALUES (?, ?, 'tag_item', 'api', "
                 "'x', ?)", (db.now(), spend.this_month(), 0.01 - spend.estimate_views(2) / 2))
        sv.views.drain(now=later())
        assert api.calls == 0   # the estimate is checked first: nothing is sent past the limit
        assert get(c, item)["views"]["message"] == shoeviews.LIMIT
        c.put("/api/settings", json={"tagging_api_cap_usd": 1.0})
        assert sv.views.drain(now=later()) == 1 and api.calls == 1
        assert [p["view"] for p in get(c, item)["photos"]] == ["outer", "top"]
        with closing(db.connect(cfg.db_path("main"))) as conn:
            got = dict(conn.execute("SELECT purpose, route, model, cost_usd FROM claude_calls WHERE purpose != 'tag_item'"
                                    ).fetchone())
        assert got["purpose"] == spend.PURPOSE_VIEWS == "sort_views" and got["route"] == "api"
        assert got["model"] == tagger_views.MODEL and got["cost_usd"] == pytest.approx(spend.cost_usd(tagger_views.MODEL, 6000, 200))
    finally:
        sv.stop()


def test_the_estimate_counts_every_photo():
    one, six = spend.estimate_views(1), spend.estimate_views(6)
    assert 0 < one < six < 0.1
    assert six - one == pytest.approx(spend.cost_usd(tagger_views.MODEL, spend.IMAGE_TOKENS * 5, 0))
    assert spend.estimate_views(0) == one
    # the prompt and its schema fit in what the estimate allows for them (about 2 characters a token, doubled)
    schema = json.dumps(ShoeViews.model_json_schema())
    assert (len(tagger_views.prompt(6)) + len(tagger_views.SYSTEM) + len(schema)) / 2 * 2 <= spend.VIEWS_TEXT_TOKENS


def test_images_are_kept_small_for_claude():
    big = Image.new("RGBA", (3000, 2000), (10, 20, 30, 255))
    shown = tagger_views.shown(big)
    assert max(shown.size) == 1024 and shown.mode == "RGB"
