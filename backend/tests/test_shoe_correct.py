"""The owner's one-line correction of a shoe's drawing (shoes drawn from understanding, step E): `POST
/api/items/{id}/drawn/correct` queues the note for the shoe drawing worker (`closet/shoedraw.py`), which has Claude
change only what it asks and check the change against the photos (`closet/tagger/shoedrawing.py`, `correct`); the
drawing before is kept and `POST /api/items/{id}/drawn/back` swaps the two; the owner's notes are carried into a later
drawing from scratch.

Claude is never called: stand-ins answer for the worker, and for the calls both routes are stood in for
(`conftest.FakeApi`, and a stand-in for `subprocess.run`).
"""
import json
import logging
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from closet import app as app_module
from closet import db, shoedraw, spend, tracejobs
from closet.drawing import drawn
from closet.tagger import correcting
from closet.tagger import shoedrawing as SD
from closet.tagger.correcting import CorrectionResult
from closet.tagger.shoedrawing import CorrectAnswer, CorrectCheckAnswer, Photo
from closet.tagger.tagging import CapReached, RouteUnavailable, TaggingError

from .conftest import (
    AGAINST,
    BLACK_LACES,
    PASSPHRASE,
    SHEET,
    FakeApi,
    FakeClaude,
    black_laces,
    correct_answer,
    correct_check_answer,
    fake_cutter,
    upload,
)
from .test_shoedraw import Drawer
from .test_shoedrawing_turned import Claude
from .test_shoeviews import Sorter, a_shoe, add, answer, get, later, row, sql

DRESS = drawn.example("dress-shoe")
LACES = drawn.sanitise(black_laces(DRESS))
TAB = '<path d="M88,-28 L88,-64 C88,-73 112,-73 112,-64 L112,-28 Z" fill="#4a2c22" stroke="#26221f" stroke-width="1.6"/>'


class Corrector:
    """Stands in for Claude changing the drawing from the owner's note: the drawing kept with its laces black (the only
    shape the note is about), said to go against the photos unless told otherwise; or raises `error`. `calls` keeps
    the note, the drawing it was given and the views of the photos; `during` runs while it works."""

    def __init__(self):
        self.error: Exception | None = None
        self.against: str | None = AGAINST
        self.calls: list[tuple] = []
        self.during = None

    def __call__(self, photos, kept, note, routes):
        self.calls.append((note, kept, [(p.view, p.sure) for p in photos]))
        assert routes == ("plan",)
        if self.during:
            self.during()
        if self.error:
            raise self.error
        left = drawn.side(kept["left"])
        calls = [SD.Call("correct", "plan", SD.MODEL, 30_000, 10_000, 3_000, 0.08, 30.0),
                 SD.Call("check", "plan", SD.MODEL, 25_000, 10_000, 1_000, 0.04, 15.2)]
        sheet = {k: v for k, v in kept["sheet"].items() if k != "owner_notes"}
        return SD.Corrected(drawn.Side(drawn.sanitise(black_laces(left.front)), left.behind), None, sheet, 1, 45.2,
                            calls, True, [], note=note, changed="The laces are black now.", against_photos=self.against)


@pytest.fixture
def made(cfg):
    sorter, drawer, corrector = Sorter(), Drawer(), Corrector()
    routes = {"now": ("plan",)}
    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, tagger=FakeClaude(),
                                   routes=lambda: routes["now"], sorter=sorter, drawer=drawer,
                                   drawing_corrector=corrector)
    c = TestClient(app_module.create_app(sv))
    assert c.post("/api/setup", json={"passphrase": PASSPHRASE}).status_code == 204
    yield SimpleNamespace(sv=sv, c=c, routes=routes, sorter=sorter, drawer=drawer, corrector=corrector)
    sv.stop()


def drawn_shoe(m, key="k1") -> dict:
    """A shoe with one more photo, sorted and drawn (the dress shoe)."""
    item = a_shoe(m.c, key)
    add(m.c, item, 1)
    m.sorter.reply = answer(("outer", True), ("inner", True))
    m.sv.views.drain(now=later())
    assert m.sv.draws.drain() == 1
    return item


def drawn_of(m, item) -> dict:
    return get(m.c, item)["drawn"]


def kept(m, item, column="drawn") -> dict | None:
    text = row(m.sv.cfg, item["id"])[column]
    return json.loads(text) if text else None


def send(m, item, note=BLACK_LACES):
    return m.c.post(f"/api/items/{item['id']}/drawn/correct", json={"note": note})


# ------------------------------------------------------------------ the migration

def test_the_migration_adds_the_previous_drawing_and_the_note(cfg):
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    db.migrate(cfg.db_path("main"), cfg.local_backups_dir)
    with closing(db.connect(cfg.db_path("main"))) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(items)")}
    assert {"drawn_prev", "drawn_note"} <= cols
    assert (Path(db.__file__).parent / "migrations" / "0028_shoe_drawn_back.sql").exists()


# ------------------------------------------------------------------ the endpoint: what it refuses

def test_a_note_is_refused_in_plain_words_when_empty_or_too_long(made):
    m = made
    item = drawn_shoe(m)
    for bad in ("", "   ", None, 42, ["a"]):
        r = m.c.post(f"/api/items/{item['id']}/drawn/correct", json={"note": bad})
        assert r.status_code == 422 and r.json()["detail"].startswith("Write what is wrong with the drawing")
    r = m.c.post(f"/api/items/{item['id']}/drawn/correct", json={})
    assert r.status_code == 422 and "Write what is wrong" in r.json()["detail"]
    r = send(m, item, "x" * (SD.NOTE_MAX + 1))
    assert r.status_code == 422 and r.json()["detail"].startswith(f"Keep the note to {SD.NOTE_MAX} characters")
    r = m.c.post(f"/api/items/{item['id']}/drawn/correct", content=b"not json", headers={"content-type": "application/json"})
    assert r.status_code == 400
    assert drawn_of(m, item)["state"] == "done" and m.corrector.calls == []
    assert send(m, item, "  the laces\n should be   black ").status_code == 202   # one line, at most NOTE_MAX
    assert row(m.sv.cfg, item["id"])["drawn_note"] == BLACK_LACES
    assert send(m, item, "y" * SD.NOTE_MAX).status_code == 409   # busy now: one correction at a time


def test_only_a_shoe_with_a_drawing_never_while_it_is_drawn_or_changed(made):
    m = made
    plain = upload(m.c, key="k2").json()
    m.c.patch(f"/api/items/{plain['id']}", json={"category": "tee"})
    r = send(m, plain)
    assert r.status_code == 409 and r.json()["detail"] == shoedraw.NOT_A_SHOE
    assert send(m, {"id": "nope"}).status_code == 404
    bare = a_shoe(m.c, "k3")
    r = send(m, bare)
    assert r.status_code == 409 and r.json()["detail"] == shoedraw.CORRECT_NOTHING
    item = drawn_shoe(m)
    m.c.post(f"/api/items/{item['id']}/drawn")   # "Draw again": waiting to be drawn
    r = send(m, item)
    assert r.status_code == 409 and r.json()["detail"] == shoedraw.CORRECT_BUSY
    m.drawer.during = lambda: seen.append(send(m, item))
    seen: list = []
    m.sv.draws.drain()
    assert seen[0].status_code == 409   # while it is being drawn
    assert send(m, item).status_code == 202
    assert send(m, item, "the sole is thinner").status_code == 409   # a correction waits
    m.corrector.during = lambda: seen.append(send(m, item, "the sole is thinner"))
    m.sv.draws.drain()
    assert seen[1].status_code == 409 and seen[1].json()["detail"] == shoedraw.CORRECT_BUSY   # one is being made
    assert len(m.corrector.calls) == 1 and m.corrector.calls[0][0] == BLACK_LACES


def test_never_in_the_demo_closet(made):
    m = made
    assert m.c.post("/api/profile", json={"profile": "demo"}).status_code == 200
    shoe = next(i for i in m.c.get("/api/items").json()["items"] if i["category"] in tracejobs.SHOES
                and m.c.get(f"/api/items/{i['id']}").json()["drawn"]["url"])
    r = m.c.post(f"/api/items/{shoe['id']}/drawn/correct", json={"note": BLACK_LACES})
    assert r.status_code == 409 and r.json()["detail"] == shoedraw.CORRECT_DEMO
    r = m.c.post(f"/api/items/{shoe['id']}/drawn/back")
    assert r.status_code == 409 and r.json()["detail"] == shoedraw.NO_PREVIOUS   # nothing kept before
    demo = db.connect(m.sv.cfg.db_path("demo"))
    demo.execute("UPDATE items SET drawn_state = 'waiting', drawn_note = ? WHERE id = ?", (BLACK_LACES, shoe["id"]))
    demo.close()
    assert m.sv.draws.drain() == 0 and m.corrector.calls == []   # never sent to Claude, even if one waited


def test_behind_the_login(made):
    m = made
    item = drawn_shoe(m)
    anon = TestClient(app_module.create_app(m.sv))
    assert anon.post(f"/api/items/{item['id']}/drawn/correct", json={"note": BLACK_LACES}).status_code == 401
    assert anon.post(f"/api/items/{item['id']}/drawn/back").status_code == 401


# ------------------------------------------------------------------ the worker

def test_a_note_is_queued_made_and_the_drawing_before_kept(made):
    m = made
    item = drawn_shoe(m)
    old, before = drawn_of(m, item), kept(m, item)
    r = send(m, item)
    assert r.status_code == 202
    got = r.json()["drawn"]
    assert got["state"] == "waiting" and got["correcting"] and got["note"] == BLACK_LACES
    assert got["message"] == f"Changing the drawing: “{BLACK_LACES}”" and got["url"] == old["url"]   # still shown
    assert get(m.c, item)["drawn_state"] == "waiting"   # the list follows it too
    seen = {}
    m.corrector.during = lambda: seen.update(drawn_of(m, item))
    assert m.sv.draws.drain() == 1
    assert seen["state"] == "correcting" and seen["correcting"] and seen["message"] == got["message"]
    assert seen["url"] == old["url"] and seen["changed"] is None
    note, given, views = m.corrector.calls[0]
    assert note == BLACK_LACES and given == before and views == [("outer", True), ("inner", True)]
    assert m.drawer.calls and len(m.drawer.calls) == 1   # not drawn again from scratch
    got = drawn_of(m, item)
    assert got["state"] == "done" and not got["correcting"] and got["message"] is None and got["corrected"]
    assert got["note"] == BLACK_LACES and got["changed"] == "The laces are black now." and got["against_photos"] == AGAINST
    assert got["has_previous"] and not got["previous_newer"] and got["url"] != old["url"]
    assert got["rounds"] == 1 and got["seconds"] == 45.2 and got["cost_usd"] == pytest.approx(0.12)   # this change's
    assert got["about_usd"] == old["about_usd"] == 0.38   # drawing it again costs what the drawing did
    assert kept(m, item, "drawn_prev") == before
    new = kept(m, item)
    assert new["version"] == drawn.VERSION and new["left"] == {"behind": "", "front": LACES} and new["corrected"] is True
    assert new["notes"] == [{"note": BLACK_LACES, "at": new["made_at"], "against_photos": AGAINST,
                             "changed": "The laces are black now."}]
    assert new["sheet"]["owner_notes"] == [BLACK_LACES] and new["drawn_cost_usd"] == before["cost_usd"]
    assert [c["kind"] for c in new["calls"]] == ["correct", "check"] and new["seconds"] == 45.2
    assert row(m.sv.cfg, item["id"])["drawn_note"] is None and row(m.sv.cfg, item["id"])["drawn_attempts"] == 0
    figure = m.c.post("/api/outfits/figure", json={"shoes": item["id"]}).text
    assert "#111111" in figure.lower()   # the As worn figure wears the changed drawing


def test_a_second_note_keeps_the_first_and_one_level_of_going_back(made):
    m = made
    item = drawn_shoe(m)
    send(m, item)
    m.sv.draws.drain()
    first = kept(m, item)
    m.corrector.against = None
    send(m, item, "the toe cap is a little lower")
    m.sv.draws.drain()
    assert m.corrector.calls[1][1] == first   # changed from the drawing with the first note
    got, new = drawn_of(m, item), kept(m, item)
    assert got["note"] == "the toe cap is a little lower" and got["against_photos"] is None
    assert [n["note"] for n in new["notes"]] == [BLACK_LACES, "the toe cap is a little lower"]
    assert new["sheet"]["owner_notes"] == [BLACK_LACES, "the toe cap is a little lower"]
    assert kept(m, item, "drawn_prev") == first   # one level: the drawing from scratch is gone
    assert new["drawn_cost_usd"] == first["drawn_cost_usd"]


def test_going_back_and_forth(made):
    m = made
    item = drawn_shoe(m)
    r = m.c.post(f"/api/items/{item['id']}/drawn/back")
    assert r.status_code == 409 and r.json()["detail"] == shoedraw.NO_PREVIOUS   # a first drawing: nothing before
    original = kept(m, item)
    send(m, item)
    m.sv.draws.drain()
    changed, newer, version = kept(m, item), drawn_of(m, item), get(m.c, item)["drawn_version"]
    r = m.c.post(f"/api/items/{item['id']}/drawn/back")
    assert r.status_code == 200
    got = r.json()["drawn"]
    assert kept(m, item) == original and kept(m, item, "drawn_prev") == changed
    assert got["has_previous"] and got["previous_newer"] and not got["corrected"] and got["note"] is None
    assert got["changed"] is None and got["against_photos"] is None and got["url"] != newer["url"]
    assert get(m.c, item)["drawn_version"] != version   # the figure on Today and Trips is asked for again
    assert "#111111" not in m.c.post("/api/outfits/figure", json={"shoes": item["id"]}).text.lower()
    got = m.c.post(f"/api/items/{item['id']}/drawn/back").json()["drawn"]   # and forward again
    assert kept(m, item) == changed and got["url"] == newer["url"] and got["corrected"] and not got["previous_newer"]
    assert got["against_photos"] == AGAINST
    send(m, item, "the sole is thinner")
    r = m.c.post(f"/api/items/{item['id']}/drawn/back")
    assert r.status_code == 409 and r.json()["detail"] == shoedraw.BACK_BUSY   # not while a change waits
    plain = upload(m.c, key="k5").json()
    m.c.patch(f"/api/items/{plain['id']}", json={"category": "tee"})
    assert m.c.post(f"/api/items/{plain['id']}/drawn/back").status_code == 409


def test_notes_are_carried_into_a_later_drawing_from_scratch(made):
    m = made
    item = drawn_shoe(m)
    assert m.drawer.notes == [[]]
    send(m, item)
    m.sv.draws.drain()
    changed = kept(m, item)
    m.c.post(f"/api/items/{item['id']}/drawn")   # "Draw again"
    m.sv.draws.drain()
    assert m.drawer.notes[-1] == [BLACK_LACES]
    new, got = kept(m, item), drawn_of(m, item)
    assert new["notes"] == changed["notes"] and new["sheet"]["owner_notes"] == [BLACK_LACES]
    assert not got["corrected"] and got["note"] is None and got["against_photos"] is None
    assert got["has_previous"] and kept(m, item, "drawn_prev") == changed   # a new drawing keeps the one before too
    m.c.post(f"/api/items/{item['id']}/drawn")   # and again: still carried
    m.sv.draws.drain()
    assert m.drawer.notes[-1] == [BLACK_LACES] and kept(m, item)["sheet"]["owner_notes"] == [BLACK_LACES]


def test_a_note_gone_back_from_is_not_given_to_a_later_drawing(made):
    m = made
    item = drawn_shoe(m)
    send(m, item)
    m.sv.draws.drain()
    m.c.post(f"/api/items/{item['id']}/drawn/back")   # the owner went back: the note was wrong about the shoe
    m.c.post(f"/api/items/{item['id']}/drawn")
    m.sv.draws.drain()
    assert m.drawer.notes[-1] == [] and kept(m, item)["notes"] == [] and "owner_notes" not in kept(m, item)["sheet"]


def test_a_version_1_drawing_is_changed_and_comes_back_as_the_current_version(made):
    m = made
    item = drawn_shoe(m)
    one = {**kept(m, item), "version": 1, "left": drawn.sanitise(DRESS)}
    one.pop("notes")
    sql(m.sv.cfg, "UPDATE items SET drawn = ? WHERE id = ?", (json.dumps(one), item["id"]))
    send(m, item)
    m.sv.draws.drain()
    assert m.corrector.calls[0][1]["left"] == drawn.sanitise(DRESS)   # given as kept
    new = kept(m, item)
    assert new["version"] == drawn.VERSION and new["left"] == {"behind": "", "front": LACES}
    assert kept(m, item, "drawn_prev") == one


def test_draw_again_while_a_correction_waits_changes_nothing(made):
    m = made
    item = drawn_shoe(m)
    send(m, item)
    r = m.c.post(f"/api/items/{item['id']}/drawn")
    assert r.status_code == 202 and r.json()["drawn"]["correcting"]
    assert row(m.sv.cfg, item["id"])["drawn_note"] == BLACK_LACES
    m.sv.draws.drain()
    assert len(m.drawer.calls) == 1 and len(m.corrector.calls) == 1


def test_a_correction_does_not_wait_for_the_photos_to_be_sorted(made):
    m = made
    item = drawn_shoe(m)
    add(m.c, item, 2)   # a photo added: sorted again in a moment, never drawn again by itself
    assert get(m.c, item)["views"]["state"] == "waiting"
    send(m, item)
    assert m.sv.draws.drain() == 1
    assert [v for v, _ in m.corrector.calls[0][2]] == ["outer", "inner", None]   # the new photo, not sorted yet
    assert drawn_of(m, item)["corrected"] and drawn_of(m, item)["photos_changed"] is False


def test_a_correction_never_runs_by_itself(made):
    m = made
    item = drawn_shoe(m)
    add(m.c, item, 2)
    m.sorter.reply = answer(("outer", True), ("inner", True), ("top", True))
    m.sv.views.drain(now=later())
    m.c.post(f"/api/items/{item['id']}/drawn")
    m.sv.draws.drain()
    assert m.sv.draws.drain() == 0 and m.corrector.calls == [] and not drawn_of(m, item)["corrected"]


def test_claude_out_of_reach_puts_the_correction_back_with_its_attempt(made):
    m = made
    item = drawn_shoe(m)
    send(m, item)
    m.corrector.error = RouteUnavailable("Claude Code is not signed in")
    assert m.sv.draws.drain() == 0
    got = drawn_of(m, item)
    assert got["state"] == "waiting" and got["correcting"] and got["message"] == shoedraw.CORRECT_NO_ROUTE
    assert row(m.sv.cfg, item["id"])["drawn_attempts"] == 0 and row(m.sv.cfg, item["id"])["drawn_note"] == BLACK_LACES
    m.corrector.error = CapReached("this month's spending limit for the API key has been reached")
    m.sv.draws.drain()
    assert drawn_of(m, item)["message"] == shoedraw.CORRECT_LIMIT and row(m.sv.cfg, item["id"])["drawn_attempts"] == 0
    m.routes["now"] = ()   # no route at all: Claude is not even asked
    calls = len(m.corrector.calls)
    m.sv.draws.drain()
    assert len(m.corrector.calls) == calls and drawn_of(m, item)["message"] == shoedraw.CORRECT_NO_ROUTE
    m.routes["now"] = ("plan",)
    m.corrector.error = None
    assert m.sv.draws.drain() == 1
    got = drawn_of(m, item)
    assert got["state"] == "done" and got["message"] is None and got["corrected"]


def test_after_three_failures_the_drawing_is_as_it_was_and_the_page_says_so(made, caplog):
    m = made
    item = drawn_shoe(m)
    old, before = drawn_of(m, item), kept(m, item)
    send(m, item)
    m.corrector.error = TaggingError("the answer was outside the schema")
    with caplog.at_level(logging.WARNING, logger="closet.failures"):
        m.sv.draws.drain()
    assert len(m.corrector.calls) == shoedraw.MAX_ATTEMPTS == 3
    got = drawn_of(m, item)
    assert got["state"] == "done" and got["message"] == shoedraw.CORRECT_FAILED and not got["correcting"]
    assert got["url"] == old["url"] and kept(m, item) == before and not got["has_previous"]
    assert row(m.sv.cfg, item["id"])["drawn_note"] is None
    assert "correction of its drawing from the owner's note failed" in caplog.text
    assert m.sv.draws.drain() == 0   # not tried again until the owner sends it again
    m.corrector.error = None
    assert send(m, item).status_code == 202
    assert drawn_of(m, item)["message"] == f"Changing the drawing: “{BLACK_LACES}”"
    assert m.sv.draws.drain() == 1 and drawn_of(m, item)["corrected"] and drawn_of(m, item)["message"] is None


def test_a_missing_photo_file_fails_the_correction_at_once(made):
    m = made
    item = drawn_shoe(m)
    one = get(m.c, item)["photos"][1]
    (m.sv.cfg.images_dir("main") / one["url"].removeprefix("/media/")).unlink()
    send(m, item)
    m.sv.draws.drain()
    got = drawn_of(m, item)
    assert got["message"] == shoedraw.CORRECT_NO_PHOTO and got["state"] == "done" and m.corrector.calls == []


def test_a_correction_interrupted_by_a_quit_starts_again(made):
    m = made
    item = drawn_shoe(m)
    send(m, item)
    sql(m.sv.cfg, "UPDATE items SET drawn_state = 'correcting' WHERE id = ?", (item["id"],))
    assert m.sv.draws.drain() == 1 and drawn_of(m, item)["corrected"] and m.corrector.calls[0][0] == BLACK_LACES


def test_a_shoe_deleted_while_it_is_changed_is_left_alone(made):
    m = made
    item = drawn_shoe(m)
    send(m, item)
    m.corrector.during = lambda: m.c.delete(f"/api/items/{item['id']}")
    assert m.sv.draws.drain() == 1
    assert m.c.get(f"/api/items/{item['id']}").status_code == 404


def test_through_the_api_key_and_its_monthly_limit(cfg):
    api = FakeApi(input_tokens=20_000, output_tokens=5_000)
    sorter = Sorter()
    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, routes=lambda: ("api",), api_client=api,
                                   sorter=lambda photos, routes: sorter.reply)
    try:
        c = TestClient(app_module.create_app(sv))
        assert c.post("/api/setup", json={"passphrase": PASSPHRASE}).status_code == 204
        item = a_shoe(c)
        add(c, item, 1)
        sorter.reply = answer(("outer", True), ("inner", True))
        sv.views.drain(now=later())
        c.put("/api/settings", json={"tagging_api_enabled": True, "tagging_api_cap_usd": 20.0})
        drawing = SD.CANDIDATES * 2 + 1 + SD.TURNS * 2 + 1   # as in test_shoedraw: no fault named, so no fix
        assert sv.draws.drain() == 1 and api.calls == drawing
        with closing(db.connect(cfg.db_path("main"))) as conn:
            so_far = spend.spent(conn)
        c.put("/api/settings", json={"tagging_api_cap_usd": round(so_far + 0.5, 2)})
        assert c.post(f"/api/items/{item['id']}/drawn/correct", json={"note": BLACK_LACES}).status_code == 202
        sv.draws.drain()
        assert api.calls == drawing   # the estimate is checked first: nothing is sent past the limit
        assert get(c, item)["drawn"]["message"] == shoedraw.CORRECT_LIMIT
        c.put("/api/settings", json={"tagging_api_cap_usd": 40.0})
        assert sv.draws.drain() == 1 and api.calls == drawing + 2
        got = get(c, item)["drawn"]
        assert got["state"] == "done" and got["corrected"] and got["route"] == "api" and got["rounds"] == 1
        assert got["against_photos"] == AGAINST and got["changed"] == "The laces are black now."
        # the change, and its check, which said good and stopped being read there (its output as the most it could be)
        assert got["cost_usd"] == pytest.approx(spend.cost_usd(SD.MODEL, 20_000, 5_000)
                                                + spend.cost_usd(SD.MODEL, 20_000, SD.MAX_TOKENS))
        with closing(db.connect(cfg.db_path("main"))) as conn:
            rows = [dict(r) for r in conn.execute("SELECT purpose, route, model FROM claude_calls ORDER BY rowid")]
        assert [r["purpose"] for r in rows] == ["draw_shoe"] * drawing + ["correct_drawing"] * 2
        assert spend.PURPOSE_CORRECT_DRAWING == "correct_drawing" and all(r["model"] == SD.MODEL for r in rows)
        assert spend.estimate_correct_drawing(8) > 0.5   # one request's careful estimate is over the room left
    finally:
        sv.stop()


# ------------------------------------------------------------------ the calls (shoedrawing.correct)

VIEWS = (("outer", False), ("top", True), ("inner", False), ("front", True), ("back", True))


def photos(n=5) -> list[Photo]:
    return [Photo(Image.new("RGB", (900, 700), (40 * i, 90, 120)), v, s) for i, (v, s) in enumerate(VIEWS[:n])]


def shoe(front: str, behind: str = "") -> dict:
    return {"behind": behind, "front": front}


def a_drawing(left=None, version=2, notes=()) -> dict:
    """A drawing as kept with the item: the dress shoe, version 2 unless told otherwise."""
    made = SD.Drawn(drawn.side(left or DRESS), None, dict(SHEET), 1, 100.0, [], True, [])
    out = made.to_json(["p1"], "2026-11-15T12:00:00.000000Z", list(notes))
    if version == 1:
        out = {**out, "version": 1, "left": drawn.sanitise(left or DRESS)}
    return out


TALL = {**SHEET, "silhouette": {**SHEET["silhouette"], "height": "ankle"}}


def changed(left=LACES, against=AGAINST, behind="", sheet=None) -> CorrectAnswer:
    answer = correct_answer(against).model_dump()
    return CorrectAnswer.model_validate({**answer, "left": shoe(left, behind), "sheet": sheet or answer["sheet"]})


def check(good=True, left=LACES, against=AGAINST, behind="", sheet=None) -> CorrectCheckAnswer:
    answer = correct_check_answer(good, against).model_dump()
    return CorrectCheckAnswer.model_validate({**answer, "left": shoe(left, behind), "sheet": sheet or answer["sheet"]})


class Asker:
    """Stands in for `correcting.ask`: answers `replies` in turn (an answer, or an exception to raise) and keeps what
    each call was given."""

    def __init__(self, *replies, route="plan", tokens=(30_000, 5_000), cached=0):
        self.replies, self.route, self.tokens, self.cached = list(replies), route, tokens, cached
        self.calls: list[dict] = []

    def __call__(self, text, images, routes, **kw):
        self.calls.append({"text": text, "images": images, "routes": routes, **kw})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return CorrectionResult(reply, self.route, kw["model"], self.tokens[0], self.tokens[1], self.cached)


def clock():
    t = {"now": 0.0}

    def tick():
        t["now"] += 10.0
        return t["now"]
    return tick


def test_the_correction_prompt_carries_the_note_the_drawing_the_photos_and_the_earlier_notes():
    kept_ = a_drawing(notes=[{"note": "the toe is rounder", "at": "x", "against_photos": None, "changed": "c"}])
    text = SD.correct_prompt(photos(), kept_["sheet"], drawn.side(kept_["left"]), None, BLACK_LACES,
                             ["the toe is rounder"])
    assert f'## The owner\'s note\n"{BLACK_LACES}"' in text and '- "the toe is rounder"' in text
    assert "drawing.png" in text and drawn.sanitise(DRESS) in text and '"archetype": "cap-toe oxford"' in text
    assert "owner_notes" not in text   # the notes come in their own words, not as the sheet's
    assert "- Photo 1 (photo-1.jpg): the outer side, or possibly the inner side (not sure which)." in text
    assert "Change ONLY what the note asks" in text and "against_photos" in text and "drawn as you asked" in text
    assert "ground is y = 240" in text and "kept before drawings had two parts" not in text
    assert "kept before drawings had two parts" in SD.correct_prompt(photos(), SHEET, drawn.Side(DRESS), None, "n",
                                                                     whole=True)
    check_text = SD.correct_check_prompt(photos(), SHEET, drawn.Side(LACES), None, ["It floats."], BLACK_LACES,
                                         ["the toe is rounder"])
    for words in ("PHOTOS", "before.png", "drawing.png", BLACK_LACES, "never undo it", "Nothing else changes",
                  "- It floats.", '- "the toe is rounder"', LACES, "against_photos"):
        assert words in check_text, words


def test_only_the_noted_part_changes_and_one_check_says_good():
    asker = Asker(correct_answer(), correct_check_answer())
    made = SD.correct(photos(), a_drawing(), f"  {BLACK_LACES} ", ("plan", "api"), asker=asker, clock=clock())
    assert [c["answer_model"] for c in asker.calls] == [CorrectAnswer, CorrectCheckAnswer]
    first, second = asker.calls
    assert first["names"] == [f"photo-{n}.jpg" for n in range(1, 6)] + ["drawing.png"] and len(first["images"]) == 6
    assert second["names"][-2:] == ["before.png", "drawing.png"] and len(second["images"]) == 7
    assert second["images"][-2].size == first["images"][-1].size   # the drawing before, as first shown
    assert all(c["model"] == SD.MODEL and c["effort"] == SD.EFFORT and c["max_tokens"] == SD.MAX_TOKENS
               and c["timeout"] == SD.TIMEOUT and c["routes"] == ("plan", "api") for c in asker.calls)
    assert isinstance(made, SD.Corrected) and made.rounds == 1 and made.good and made.problems == []
    assert made.note == BLACK_LACES and made.changed == "The laces are black now." and made.against_photos == AGAINST
    assert [c.kind for c in made.calls] == ["correct", "check"] and made.seconds > 0
    # only the laces changed: every other shape is the dress shoe's, as it was
    was, now = drawn.sanitise(DRESS).splitlines(), made.left.front.splitlines()
    assert len(was) == len(now) and [i for i, (a, b) in enumerate(zip(was, now, strict=True)) if a != b] == [5]
    assert "#3a2a24" in was[5] and "#111111" in now[5]


def test_the_checks_after_a_correction_stop_after_two_rounds():
    asker = Asker(correct_answer(), check(good=False), check(good=False), check(good=False))
    made = SD.correct(photos(), a_drawing(), BLACK_LACES, ("plan",), asker=asker, clock=clock())
    assert len(asker.calls) == 1 + SD.MAX_CORRECT_ROUNDS == 3 and made.rounds == 2 and not made.good
    assert len(asker.replies) == 1


def test_against_the_photos_is_the_last_checks_word():
    made = SD.correct(photos(), a_drawing(), BLACK_LACES, ("plan",), clock=clock(),
                      asker=Asker(changed(against=None), check(good=False, against=AGAINST), check(against=AGAINST)))
    assert made.against_photos == AGAINST and made.rounds == 2
    made = SD.correct(photos(), a_drawing(), BLACK_LACES, ("plan",), clock=clock(),
                      asker=Asker(changed(against=AGAINST), check(against=None)))
    assert made.against_photos is None   # the check, having looked at the change beside the photos, found it true
    made = SD.correct(photos(), a_drawing(), BLACK_LACES, ("plan",), clock=clock(),
                      asker=Asker(changed(against="  The photos show brown laces.\n "), TaggingError("no answer")))
    assert made.against_photos == "The photos show brown laces." and made.rounds == 0   # no check: the first word
    made = SD.correct(photos(), a_drawing(), BLACK_LACES, ("plan",), clock=clock(),
                      asker=Asker(changed(against="null"), check(against="x" * 400)))
    assert len(made.against_photos) == SD.SENTENCE_MAX and made.against_photos.endswith("…")


def test_a_version_1_drawing_goes_in_and_the_current_version_comes_out():
    one = a_drawing(TAB + DRESS, version=1)
    asker = Asker(changed(left=DRESS, behind=TAB, sheet=TALL), check(left=DRESS, behind=TAB, sheet=TALL))
    made = SD.correct(photos(), one, "The pull tab is at the back of the boot", ("plan",), asker=asker, clock=clock())
    assert "kept before drawings had two parts" in asker.calls[0]["text"]
    assert "behind the leg:\n(empty)\nin front of the leg:\n" + drawn.sanitise(TAB + DRESS) in asker.calls[0]["text"]
    out = made.to_json(["p1"], "2026-11-15T13:00:00.000000Z", SD.notes_of(one))
    assert out["version"] == drawn.VERSION and out["left"] == {"behind": drawn.sanitise(TAB),
                                                                "front": drawn.sanitise(DRESS)}
    assert out["corrected"] is True and out["notes"][-1]["note"] == "The pull tab is at the back of the boot"


def test_what_the_automatic_checks_find_goes_into_the_check_after_a_correction():
    lifted = f'<g transform="translate(0 -20)">{LACES}</g>'
    asker = Asker(changed(left=lifted), check(good=False, left=LACES), check(good=True))
    made = SD.correct(photos(), a_drawing(), BLACK_LACES, ("plan",), asker=asker, clock=clock())
    assert "does not stand on the ground" in asker.calls[1]["text"] and "- none" in asker.calls[2]["text"]
    assert made.good and made.rounds == 2 and made.left == drawn.Side(LACES)
    # said good while the automatic checks still find something: not taken as good, and kept as found
    made = SD.correct(photos(), a_drawing(), BLACK_LACES, ("plan",), clock=clock(),
                      asker=Asker(changed(left=lifted), check(good=True, left=lifted), check(good=True, left=lifted)))
    assert not made.good and made.rounds == 2 and any("does not stand on the ground" in p for p in made.problems)


def test_every_change_is_made_safe_and_an_unusable_one_raises():
    nasty = LACES + '<script>alert(1)</script><path d="M0,0" onclick="x()"/>'
    made = SD.correct(photos(), a_drawing(), BLACK_LACES, ("plan",), clock=clock(),
                      asker=Asker(changed(left=nasty), check(left=nasty)))
    assert "<script" not in made.left.front and "onclick" not in made.left.front
    with pytest.raises(drawn.DrawingError):
        SD.correct(photos(), a_drawing(), BLACK_LACES, ("plan",), clock=clock(), asker=Asker(changed(left="<text/>")))
    with pytest.raises(RouteUnavailable):
        SD.correct(photos(), a_drawing(), BLACK_LACES, ("plan",), clock=clock(), asker=Asker(RouteUnavailable("x")))
    with pytest.raises(drawn.DrawingError):
        SD.correct(photos(), {"left": DRESS}, BLACK_LACES, ("plan",), clock=clock(), asker=Asker())
    with pytest.raises(ValueError):
        SD.correct(photos(), a_drawing(), " ", ("plan",), clock=clock(), asker=Asker())


def test_a_correction_kept_adds_its_note_and_the_sheet_says_the_owners_notes():
    earlier = [{"note": "the toe is rounder", "at": "2026-11-15T12:30:00.000000Z", "against_photos": None,
                "changed": "The toe is rounder."}]
    made = SD.correct(photos(), a_drawing(notes=earlier), BLACK_LACES, ("plan",), clock=clock(),
                      asker=Asker(correct_answer(), correct_check_answer()))
    out = made.to_json(["p1", "p2"], "2026-11-15T13:00:00.000000Z", earlier)
    assert out["notes"] == [*earlier, {"note": BLACK_LACES, "at": "2026-11-15T13:00:00.000000Z",
                                       "against_photos": AGAINST, "changed": "The laces are black now."}]
    assert out["sheet"]["owner_notes"] == ["the toe is rounder", BLACK_LACES] and out["corrected"] is True
    assert '- "the toe is rounder"' in made_prompt(earlier)
    assert SD.notes_of({"notes": [{"note": " "}, "x", {"note": 3}, {"note": "ok"}]}) == [
        {"note": "ok", "at": None, "against_photos": None, "changed": None}]
    assert SD.notes_of(None) == [] and SD.notes_of({"notes": "x"}) == []


def made_prompt(earlier) -> str:
    asker = Asker(correct_answer(), correct_check_answer())
    SD.correct(photos(), a_drawing(notes=earlier), BLACK_LACES, ("plan",), clock=clock(), asker=asker)
    return asker.calls[0]["text"] + asker.calls[1]["text"]


def test_a_drawing_from_scratch_keeps_to_the_owners_notes():
    """Every question of a drawing from scratch carries them: each drawing and check, straight on and turned, each
    judge's choice and the fix of the judge's faults."""
    claude = Claude()
    SD.draw(photos(), ("plan",), asker=claude, clock=clock(), notes=[BLACK_LACES, "the toe is rounder"], style="oxford")
    kinds = {c["model"] for c in claude.calls}
    assert {SD.DrawAnswer, SD.CheckAnswer, SD.Verdict, SD.TurnedDrawAnswer, SD.TurnedCheckAnswer,
            SD.TurnedCorrectAnswer} <= kinds
    for call in claude.calls:
        assert ("## The owner's notes on earlier drawings of this shoe" in call["text"]
                or "## The owner's earlier notes on this shoe" in call["text"]), call["model"]
        assert f'- "{BLACK_LACES}"' in call["text"] and '- "the toe is rounder"' in call["text"], call["model"]
    assert "owner's notes" not in SD.draw_prompt(photos()) and "owner's notes" not in SD.judge_prompt(photos(), 3)
    many = [f"note {n}" for n in range(30)]
    text = SD.draw_prompt(photos(), many)
    assert '- "note 29"' in text and '- "note 10"' in text and '- "note 9"' not in text   # the latest NOTES_SENT


def test_a_note_is_one_line_and_not_too_long():
    assert SD.clean_note("  the laces\n are   black ") == "the laces are black"
    for bad in ("", "  ", None, 3):
        with pytest.raises(ValueError, match="Write what is wrong with the drawing"):
            SD.clean_note(bad)
    with pytest.raises(ValueError, match="200 characters or fewer"):
        SD.clean_note("x" * 201)
    assert SD.clean_note("x" * 200) == "x" * 200


# ------------------------------------------------------------------ through each route

class Meter:
    def __init__(self):
        self.checked, self.recorded = [], []

    def before_api_call(self, model, images):
        self.checked.append((model, images))

    def record(self, route, model, input_tokens, output_tokens):
        self.recorded.append((route, model, input_tokens, output_tokens))

    def api_refused(self, reason):
        pass


def test_through_the_api_key_a_correction_is_streamed_and_counted():
    api, meter = FakeApi(input_tokens=25_000, output_tokens=7_000), Meter()
    made = SD.correct(photos(), a_drawing(), BLACK_LACES, ("api",), client=api, meter=meter)
    assert api.calls == 2 and made.rounds == 1 and made.good and made.route == "api"
    assert made.against_photos == AGAINST and made.left == drawn.Side(LACES)
    first = api.requests[0]
    assert first["model"] == SD.MODEL and first["output_config"]["effort"] == SD.EFFORT == "medium"
    assert "against_photos" in first["output_config"]["format"]["schema"]["properties"]
    content = first["messages"][0]["content"]
    assert [c["text"] for c in content if c["type"] == "text"][:6] == [
        "photo-1.jpg:", "photo-2.jpg:", "photo-3.jpg:", "photo-4.jpg:", "photo-5.jpg:", "drawing.png:"]
    names = [c["text"] for c in api.requests[1]["messages"][0]["content"] if c["type"] == "text"]
    assert "before.png:" in names and "drawing.png:" in names
    assert meter.checked == [(SD.MODEL, 6), (SD.MODEL, 7)]
    # the check said good and stopped being read there: counted once, its output as the most it could be
    assert meter.recorded == [("api", SD.MODEL, 25_000, 7_000), ("api", SD.MODEL, 25_000, SD.MAX_TOKENS)]
    assert [s["whole"] for s in api.streams] == [True, False]


def test_through_the_plan_a_correction_saves_every_image_under_its_name(monkeypatch):
    seen = []
    answers = iter([correct_answer(), correct_check_answer()])

    def run(cmd, cwd=None, **kw):
        seen.append({"cmd": cmd, "input": kw["stdin"].read().decode("utf-8"),
                     "files": sorted(p.name for p in Path(cwd).iterdir())})
        out = {"structured_output": next(answers).model_dump(), "is_error": False, "result": "",
               "usage": {"input_tokens": 9_000, "cache_creation_input_tokens": 12_000, "cache_read_input_tokens": 30_000,
                         "output_tokens": 4_000}}
        return SimpleNamespace(returncode=0, stdout=json.dumps(out), stderr="")
    monkeypatch.setattr(correcting.subprocess, "run", run)
    made = SD.correct(photos(3), a_drawing(), BLACK_LACES, ("plan",), exe="claude", meter=Meter())
    assert made.rounds == 1 and made.good and made.route == "plan" and made.against_photos == AGAINST
    fix, look = seen
    assert fix["files"] == ["drawing.png", "photo-1.jpg", "photo-2.jpg", "photo-3.jpg"]
    assert look["files"] == ["before.png", "drawing.png", "photo-1.jpg", "photo-2.jpg", "photo-3.jpg"]
    assert BLACK_LACES in fix["input"] and "before.png" in look["input"]
    for call in seen:
        cmd = call["cmd"]
        assert cmd[cmd.index("--model") + 1] == SD.MODEL and cmd[cmd.index("--effort") + 1] == SD.EFFORT
    assert made.calls[0].cost_usd == pytest.approx(spend.cost_usd(SD.MODEL, 21_000, 4_000))


def test_the_estimate_allows_for_the_longest_correction():
    worst = '<path d="' + "M0,0 " * ((drawn.MAX_CHARS - 20) // 5) + '"/>'
    notes = ["n" * SD.NOTE_MAX] * SD.NOTES_SENT
    for text, model in (
            (SD.correct_prompt(photos(6), SHEET, drawn.Side(worst), drawn.Side(worst), "x" * SD.NOTE_MAX, notes, True),
             CorrectAnswer),
            (SD.correct_check_prompt(photos(6), SHEET, drawn.Side(worst), drawn.Side(worst), ["x" * 300] * 8,
                                     "x" * SD.NOTE_MAX, notes), CorrectCheckAnswer)):
        assert (len(text) + len(json.dumps(model.model_json_schema())) + len(SD.SYSTEM)) / 2 \
            <= spend.CORRECT_DRAW_TEXT_TOKENS
    assert spend.estimate_correct_drawing(9) - spend.estimate_correct_drawing(8) == pytest.approx(
        spend.cost_usd(SD.MODEL, 0, 0, cache_write=spend.IMAGE_TOKENS))   # as written to the prompt cache
    assert spend.estimate_correct_drawing(8) >= spend.cost_usd(
        SD.MODEL, spend.CORRECT_DRAW_TEXT_TOKENS + 8 * spend.IMAGE_TOKENS, SD.MAX_TOKENS)


def test_a_correction_check_cut_short_keeps_what_it_says_against_the_photos():
    api = FakeApi()
    api.correct_checked = correct_check_answer(against="The check's own word on the photos.")
    made = SD.correct(photos(), a_drawing(), BLACK_LACES, ("api",), client=api)
    assert [s["whole"] for s in api.streams] == [True, False]
    assert '"against_photos"' in api.streams[1]["text"] and '"left"' not in api.streams[1]["text"]
    assert made.good and made.left == drawn.Side(LACES) and made.against_photos == "The check's own word on the photos."
