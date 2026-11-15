"""Tracing a shoe from its photo in the cut-out queue (#206, stage 2b): when a shoe waits to be traced, what is kept,
how its drawing changes, the fallback with a plain explanation, the owner's fixes surviving a new trace, the
plain drawing, a new photo, the second photo and Add's instant check.

Most tests use a stand-in tracer that returns a shoe traced once from a synthetic photo (`shoe_photos`, never a real
photo); one test runs the real tracer on such a photo, start to finish.
"""
import copy
import hashlib
import io
import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from closet import app as app_module
from closet import db, illustrations, tracejobs
from closet.drawing import sideshoe, traced
from closet.drawing import trace as T
from closet.tagger.schema import Details, ItemTags, Silhouette
from closet.tagger.tagging import TagResult

from . import shoe_photos as S
from .conftest import PASSPHRASE, fake_cutter, upload

# what the template drew for these two shoes before tracing existed: an untraced shoe, and one whose photo the
# tracing turned down, must still be drawn exactly so
TEMPLATE = {"a1b2c3d4e5f6a7b8": "73b7eb4596fe59c92fb51216b04df821a933d0fe44f2895770c7c4a01a3c7446",
            "b1b2c3d4e5f6a7b8": "fb4e74c66be573d148477c188dd03a4a65bdbe66ca93bef887cf588402f92a6f"}


def tags(category="sneakers", **said) -> ItemTags:
    return ItemTags(category=category, category_confidence=0.9, color="navy", color_confidence=0.9, secondary_colors=[],
                    pattern="solid", pattern_confidence=0.9, formality="casual", formality_confidence=0.8, season="all",
                    season_confidence=0.8, silhouette=Silhouette.of(shoe_height="low"), silhouette_confidence=0.9,
                    details=Details.plain(**said), details_confidence=0.8, brand=None, size=None, material=None,
                    needs_shot=None)


def jpeg(img) -> bytes:
    out = io.BytesIO()
    img.save(out, "JPEG", quality=92)
    return out.getvalue()


@pytest.fixture(scope="module")
def shoe() -> traced.TracedShoe:
    """A white sneaker with a grey toe cap, a red heel, navy laces and three navy stripes, traced once."""
    img = S.draw(S.Shoe(upper=S.WHITE, midsole=S.WHITE, toe_cap=S.GREY, stripes=S.NAVY, heel_counter=S.RED,
                        laces=S.NAVY))[0]
    made = traced.traced_shoe(T.trace_photo(img))
    assert made is not None and made.gate["ok"] and made.marks
    return made


class Tracer:
    """Stands in for the tracer: the shoe above, or the gate's reasons when told to turn the photo down."""

    def __init__(self, shoe, reasons=None, fail=False):
        self.shoe, self.reasons, self.fail, self.calls = shoe, reasons, fail, []

    def __call__(self, img, told):
        self.calls.append(told)
        if self.fail:
            raise RuntimeError("could not trace")
        why = list(T._told(told)) + list(self.reasons or [])
        if why:
            return replace(self.shoe, gate={**self.shoe.gate, "ok": False, "reasons": why}), why
        return self.shoe, []


class Tagger:
    def __init__(self, answer: ItemTags | None):
        self.answer = answer

    def __call__(self, images, routes):
        return TagResult(self.answer, "fake", 0.1, 100, 50, 0.0, 1, route=routes[0])


@pytest.fixture
def make(cfg):
    made = []

    def build(tracer, answer=None):
        tagger = Tagger(answer)
        sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, tagger=tagger,
                                       routes=(lambda: ("plan",)) if answer else (lambda: ()), tracer=tracer)
        sv.worker.is_ready = lambda: True
        made.append(sv)
        c = TestClient(app_module.create_app(sv))
        assert c.post("/api/setup", json={"passphrase": PASSPHRASE}).status_code == 204
        return sv, c
    yield build
    for sv in made:
        sv.stop()


def row(cfg, item_id):
    conn = db.connect(cfg.db_path("main"))
    try:
        return dict(conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone())
    finally:
        conn.close()


def sql(cfg, query, args=()):
    conn = db.connect(cfg.db_path("main"))
    try:
        conn.execute(query, args)
    finally:
        conn.close()


def a_shoe(sv, c, key="k1", data=None):
    """An item said to be a sneaker by the owner, its cutout made and traced."""
    item = upload(c, data, key=key).json()
    assert c.patch(f"/api/items/{item['id']}", json={"category": "sneakers"}).status_code == 200
    sv.worker.drain()
    return c.get(f"/api/items/{item['id']}").json()


def svg(c, item):
    return c.get(f"/api/items/{item['id']}").json()["illustration_svg"]


# ------------------------------------------------------------------ the migration

def test_the_migration_adds_the_trace_columns(cfg, make):
    make(Tracer(None))
    conn = db.connect(cfg.db_path("main"))
    try:
        cols = {r[1]: r for r in conn.execute("PRAGMA table_info(items)")}
        assert {"trace", "trace_version", "trace_state", "trace_error", "trace_fixes", "trace_plain"} <= set(cols)
        assert cols["trace_plain"][4] == "0"   # not chosen until the owner says
        assert "view" in {r[1] for r in conn.execute("PRAGMA table_info(photos)")}
    finally:
        conn.close()


# ------------------------------------------------------------------ the queue

def test_a_shoe_is_traced_in_the_background_and_drawn_from_its_trace(cfg, make, shoe):
    tracer = Tracer(shoe)
    sv, c = make(tracer)
    item = upload(c).json()
    sv.worker.drain()
    assert tracer.calls == [] and c.get(f"/api/items/{item['id']}").json()["trace"] is None   # not a shoe yet
    changed = c.patch(f"/api/items/{item['id']}", json={"category": "sneakers"}).json()
    assert changed["trace"]["state"] == "waiting" and tracer.calls == []   # never in a request
    assert "will be traced" in changed["trace"]["message"]
    sv.worker.drain()
    got = c.get(f"/api/items/{item['id']}").json()
    assert len(tracer.calls) == 1
    assert got["trace"]["state"] == "done" and got["trace"]["drawn"] and got["trace"]["message"] is None
    stored = row(cfg, item["id"])
    assert stored["trace_version"] == tracejobs.TRACING_VERSION
    assert traced.TracedShoe.from_json(stored["trace"]).marks == shoe.marks
    assert got["illustration_svg"] == sideshoe.drawing(shoe, None, uid=item["id"][:8])
    names = [p["name"] for p in got["trace"]["parts"]]
    assert names[0] == "upper" and "toe_cap" in names and "heel_counter" in names
    assert [m["kind"] for m in got["trace"]["marks"]] == [m.kind for m in shoe.marks]
    sv.worker.drain()
    assert len(tracer.calls) == 1   # traced once


def test_anything_but_a_shoe_is_never_traced(make, shoe):
    tracer = Tracer(shoe)
    sv, c = make(tracer, answer=tags(category="polo"))
    item = upload(c).json()
    sv.worker.drain()
    sv.tag_worker.drain()
    sv.worker.drain()
    assert tracer.calls == []
    assert c.get(f"/api/items/{item['id']}").json()["trace"] is None


def test_claude_saying_it_is_a_shoe_traces_it_with_its_word_on_the_photo(cfg, make, shoe):
    tracer = Tracer(shoe)
    sv, c = make(tracer, answer=tags(shoes_in_photo="one", shoe_view="side"))
    item = upload(c).json()
    sv.worker.drain()            # the cutout; not known to be a shoe yet
    assert tracer.calls == []
    sv.tag_worker.drain()        # Claude says it is a sneaker, side-on
    sv.worker.drain()
    assert tracer.calls == [{"shoes_in_photo": "one", "shoe_view": "side"}]
    assert c.get(f"/api/items/{item['id']}").json()["trace"]["state"] == "done"


def test_a_trace_by_older_tracing_code_is_made_again(cfg, make, shoe):
    tracer = Tracer(shoe)
    sv, c = make(tracer)
    item = a_shoe(sv, c)
    sql(cfg, "UPDATE items SET trace_version = 0 WHERE id = ?", (item["id"],))
    sv.worker.drain()
    assert len(tracer.calls) == 2
    assert row(cfg, item["id"])["trace_version"] == tracejobs.TRACING_VERSION


def test_a_trace_interrupted_by_a_quit_starts_again(cfg, make, shoe):
    tracer = Tracer(shoe)
    sv, c = make(tracer)
    item = a_shoe(sv, c)
    sql(cfg, "UPDATE items SET trace_state = 'working' WHERE id = ?", (item["id"],))
    sv.worker.drain()
    assert len(tracer.calls) == 2 and row(cfg, item["id"])["trace_state"] == "done"


def test_a_result_for_a_shoe_asked_again_meanwhile_is_set_aside(cfg, make, shoe):
    sv, c = make(Tracer(shoe))
    item = a_shoe(sv, c)

    def meanwhile(img, told):   # the owner asks for a new trace while this one runs
        sql(cfg, "UPDATE items SET trace_state = 'waiting' WHERE id = ?", (item["id"],))
        return replace(shoe, marks=[]), []

    conn = db.connect(cfg.db_path("main"))
    try:
        sql(cfg, "UPDATE items SET trace_state = 'waiting' WHERE id = ?", (item["id"],))
        assert tracejobs.run_one(conn, cfg.images_dir("main"), meanwhile) == "done"
        assert row(cfg, item["id"])["trace_state"] == "waiting"   # not kept: traced again next
        assert tracejobs.run_one(conn, cfg.images_dir("main"), Tracer(shoe)) == "done"
    finally:
        conn.close()
    assert traced.TracedShoe.from_json(row(cfg, item["id"])["trace"]).marks == shoe.marks


# ------------------------------------------------------------------ the fallback

def test_a_photo_the_gate_turns_down_keeps_the_template_drawing_and_says_why(cfg, make, shoe):
    sv, c = make(Tracer(shoe), answer=tags(shoes_in_photo="one", shoe_view="front"))
    item = upload(c).json()
    sv.worker.drain()
    sv.tag_worker.drain()
    sv.worker.drain()
    got = c.get(f"/api/items/{item['id']}").json()
    assert got["trace"]["state"] == "refused" and not got["trace"]["drawn"]
    assert got["trace"]["message"] == ("The photo shows the shoe from the front, so it's drawn from its details "
                                       "instead. A side-on photo gives a closer drawing.")
    assert got["trace"]["parts"] == [] and got["trace"]["marks"] == []
    assert got["illustration_svg"] != sideshoe.drawing(shoe, None, uid=item["id"][:8])
    assert got["illustration_svg"] and "traced-" not in got["illustration_svg"]
    assert c.post(f"/api/items/{item['id']}/trace/fix", json={"part": "upper", "color": "#112233"}).status_code == 409


def test_a_trace_that_fails_keeps_the_template_drawing(cfg, make, shoe):
    sv, c = make(Tracer(shoe, fail=True))
    item = a_shoe(sv, c)
    assert item["trace"]["state"] == "failed" and item["trace"]["message"] == tracejobs.FAILED
    assert not item["trace"]["drawn"] and item["illustration_svg"]


@pytest.mark.parametrize(("reasons", "words"), [
    ([T.TOLD[("shoes_in_photo", "pair")]], "The photo shows both shoes of a pair, so it's drawn from its details instead."),
    ([T.GATE["toe_heel"][2] + " (toe_heel 0.01, limit 0.06)"], "The photo doesn't show the shoe side-on"),
    ([T.GATE["sharpness"][2] + " (sharpness 0.01, limit 0.08)", T.GATE["aspect"][2]], "The photo is blurred"),
    (["something new"], "The photo could not be traced well"),
])
def test_the_reasons_are_said_in_plain_words(reasons, words):
    said = tracejobs.plain(reasons)
    assert said.startswith(words) and "limit" not in said and "_" not in said


def test_shoes_untraced_or_turned_down_are_drawn_exactly_as_before(tmp_path, shoe):
    """The digest test: the template drawing of a shoe not traced, turned down or failed does not change."""
    path = tmp_path / "c.sqlite"
    db.migrate(path, tmp_path / "b")
    conn = db.connect(path)
    t = "2026-01-01T00:00:00.000000Z"
    boot = tags(category="boots").model_copy(update={"color": "brown", "season": "cool",
                                                     "silhouette": Silhouette.of(shoe_height="high")})
    conn.execute("INSERT INTO items (id, category, color, color_hex, silhouette, created_at, updated_at) VALUES "
                 "('a1b2c3d4e5f6a7b8', 'sneakers', 'white', '#eeeeee', '{\"shoe_height\": \"low\"}', ?, ?)", (t, t))
    conn.execute("INSERT INTO items (id, category, color, color_hex, tag_answer, created_at, updated_at) VALUES "
                 "('b1b2c3d4e5f6a7b8', 'boots', 'brown', '#6b4a32', ?, ?, ?)",
                 (json.dumps(boot.model_dump(mode="json")), t, t))

    def digests():
        rows = conn.execute("SELECT * FROM items ORDER BY id").fetchall()
        return {r["id"]: hashlib.sha256(illustrations.make(r).svg.encode()).hexdigest() for r in rows}

    try:
        assert digests() == TEMPLATE
        for state, error in (("waiting", None), ("refused", "The photo is blurred."), ("failed", tracejobs.FAILED)):
            conn.execute("UPDATE items SET trace = ?, trace_state = ?, trace_error = ?, trace_version = 1",
                         (shoe.to_json(), state, error))
            assert digests() == TEMPLATE, state
        conn.execute("UPDATE items SET trace_state = 'done', trace_plain = 1")   # the owner chose the plain drawing
        assert digests() == TEMPLATE
        conn.execute("UPDATE items SET trace_plain = 0, trace = '{\"version\": 1}'")   # a trace that cannot be read
        assert digests() == TEMPLATE
        conn.execute("UPDATE items SET trace = ?", (shoe.to_json(),))
        assert all(digests()[k] != v for k, v in TEMPLATE.items())   # traced: the traced drawing
    finally:
        conn.close()


# ------------------------------------------------------------------ the owner's fixes

def test_fixes_change_the_drawing_and_survive_a_new_trace(cfg, make, shoe):
    tracer = Tracer(shoe)
    sv, c = make(tracer)
    item = a_shoe(sv, c)
    url = f"/api/items/{item['id']}/trace/fix"
    got = c.post(url, json={"part": "toe_cap", "color": "#22AA44"}).json()
    assert "#22aa44" in got["illustration_svg"]
    assert next(p for p in got["trace"]["parts"] if p["name"] == "toe_cap") == {
        "name": "toe_cap", "title": "toe cap", "color": "#22aa44", "traced": dict(sideshoe.parts(shoe))["toe_cap"], "own": True}
    stripes = shoe.marks[0]
    hidden = c.post(url, json={"mark": 0, "hide": True}).json()
    assert hidden["trace"]["marks"][0]["hidden"] and hidden["trace"]["fixed"]
    shown = c.post(url, json={"mark": 0, "hide": False}).json()
    assert not shown["trace"]["marks"][0]["hidden"]
    moved = c.post(url, json={"mark": 0, "nudge": [0.5, 0.5]}).json()
    moved = c.post(url, json={"mark": 0, "nudge": [0.5, -0.25]}).json()
    assert moved["trace"]["marks"][0]["moved"] == [1.0, 0.25]
    assert moved["illustration_svg"] != hidden["illustration_svg"] != got["illustration_svg"]
    far = c.post(url, json={"mark": 0, "nudge": [99, 0]}).json()
    assert far["trace"]["marks"][0]["moved"][0] == sideshoe.MOVE_CM   # never far from where it was traced
    fixes = json.loads(row(cfg, item["id"])["trace_fixes"])
    assert fixes["parts"] == {"toe_cap": "#22aa44"} and fixes["marks"][0]["kind"] == stripes.kind

    # traced again from a photo where the stripes sit a little further along: the fixes follow them
    nudged = copy.deepcopy(shoe)
    nudged.marks[0].u += 0.02
    tracer.shoe = nudged
    again = c.post(f"/api/items/{item['id']}/retrace").json()
    assert again["trace"]["state"] == "waiting"
    sv.worker.drain()
    after = c.get(f"/api/items/{item['id']}").json()
    assert len(tracer.calls) == 2
    assert json.loads(row(cfg, item["id"])["trace_fixes"]) == fixes   # kept apart from the trace
    assert after["trace"]["marks"][0]["moved"] == [sideshoe.MOVE_CM, 0.25]
    assert "#22aa44" in after["illustration_svg"]

    # a trace that no longer finds the stripes: the fix is kept, not drawn
    tracer.shoe = replace(shoe, marks=[])
    c.post(f"/api/items/{item['id']}/retrace")
    sv.worker.drain()
    assert c.get(f"/api/items/{item['id']}").json()["trace"]["marks"] == []
    assert json.loads(row(cfg, item["id"])["trace_fixes"]) == fixes

    reset = c.post(url, json={"reset": True}).json()
    assert row(cfg, item["id"])["trace_fixes"] is None and not reset["trace"]["fixed"]


def test_a_fix_back_to_as_traced_is_not_kept(cfg, make, shoe):
    sv, c = make(Tracer(shoe))
    item = a_shoe(sv, c)
    url = f"/api/items/{item['id']}/trace/fix"
    c.post(url, json={"mark": 0, "nudge": [1, 0]})
    c.post(url, json={"mark": 0, "nudge": [-1, 0]})
    c.post(url, json={"part": "upper", "color": "#101010"})
    c.post(url, json={"part": "upper", "color": None})
    assert row(cfg, item["id"])["trace_fixes"] is None


@pytest.mark.parametrize(("body", "status"), [
    ({"part": "collar_lining", "color": "#112233"}, 422), ({"part": "upper", "color": "red"}, 422),
    ({"mark": 99, "hide": True}, 404), ({"mark": True, "hide": True}, 404), ({"mark": 0, "hide": "yes"}, 422),
    ({"mark": 0, "nudge": [1]}, 422), ({"mark": 0, "nudge": ["1", 0]}, 422), ({"mark": 0}, 422), ({}, 422), ([1], 422),
])
def test_a_fix_that_makes_no_sense_is_refused_in_plain_words(make, shoe, body, status):
    sv, c = make(Tracer(shoe))
    item = a_shoe(sv, c)
    r = c.post(f"/api/items/{item['id']}/trace/fix", json=body)
    assert r.status_code == status and r.json()["detail"]


def test_the_owner_can_choose_the_plain_drawing(make, shoe):
    sv, c = make(Tracer(shoe))
    item = a_shoe(sv, c)
    traced_svg = item["illustration_svg"]
    plain = c.put(f"/api/items/{item['id']}/trace/plain", json={"plain": True}).json()
    assert plain["trace"]["plain"] and not plain["trace"]["drawn"] and plain["illustration_svg"] != traced_svg
    back = c.put(f"/api/items/{item['id']}/trace/plain", json={"plain": False}).json()
    assert back["trace"]["drawn"] and back["illustration_svg"] == traced_svg
    assert c.put(f"/api/items/{item['id']}/trace/plain", json={"plain": "yes"}).status_code == 422


def test_only_a_shoe_has_trace_actions(make, shoe):
    sv, c = make(Tracer(shoe))
    item = upload(c).json()
    for r in (c.post(f"/api/items/{item['id']}/retrace"), c.put(f"/api/items/{item['id']}/trace/plain", json={"plain": True}),
              c.post(f"/api/items/{item['id']}/trace/fix", json={"reset": True}),
              c.post(f"/api/items/{item['id']}/photo", files={"photo": ("p.jpg", jpeg(S.front_view()), "image/jpeg")})):
        assert r.status_code == 409 and "shoe" in r.json()["detail"]


def test_an_item_no_longer_a_shoe_keeps_its_trace_unused(cfg, make, shoe):
    tracer = Tracer(shoe)
    sv, c = make(tracer)
    item = a_shoe(sv, c)
    coat = c.patch(f"/api/items/{item['id']}", json={"category": "coat"}).json()
    assert coat["trace"] is None and "traced-" not in coat["illustration_svg"]
    again = c.patch(f"/api/items/{item['id']}", json={"category": "sneakers"}).json()
    assert again["trace"]["drawn"] and again["illustration_svg"] == item["illustration_svg"]
    sv.worker.drain()
    assert len(tracer.calls) == 1   # not traced again for that


# ------------------------------------------------------------------ photos

def test_a_new_photo_is_cut_out_and_traced_again_and_the_fixes_stay(cfg, make, shoe):
    tracer = Tracer(shoe)
    sv, c = make(tracer)
    item = a_shoe(sv, c)
    c.post(f"/api/items/{item['id']}/trace/fix", json={"part": "upper", "color": "#334455"})
    old = item["photos"][0]
    r = c.post(f"/api/items/{item['id']}/photo", files={"photo": ("p.jpg", jpeg(S.draw()[0]), "image/jpeg")})
    assert r.status_code == 200
    got = r.json()
    assert got["trace"]["state"] is None and not got["trace"]["drawn"] and got["cutout_state"] == "pending"
    assert [p["kind"] for p in got["photos"]] == ["front"] and got["photos"][0]["id"] != old["id"]
    assert not (cfg.images_dir("main") / old["url"].removeprefix("/media/")).exists()
    sv.worker.drain()
    after = c.get(f"/api/items/{item['id']}").json()
    assert len(tracer.calls) == 2 and after["trace"]["state"] == "done" and "#334455" in after["illustration_svg"]
    # a photo of another item is refused
    other = upload(c, key="k2").json()
    from .conftest import photo_for
    r = c.post(f"/api/items/{item['id']}/photo", files={"photo": ("p.jpg", photo_for("k2"), "image/jpeg")})
    assert r.status_code == 409 and other["id"]


def test_a_second_photo_from_the_front_or_top_is_kept(make, shoe):
    sv, c = make(Tracer(shoe))
    item = a_shoe(sv, c)
    url = f"/api/items/{item['id']}/photos"
    r = c.post(url, files={"photo": ("f.jpg", jpeg(S.front_view()), "image/jpeg")}, data={"view": "front"})
    assert r.status_code == 201
    assert [(p["kind"], p["view"]) for p in r.json()["photos"]] == [("front", None), ("detail", "front")]
    top = S.front_view(size=(640, 600))
    r = c.post(url, files={"photo": ("t.jpg", jpeg(top), "image/jpeg")}, data={"view": "top"})
    assert [(p["kind"], p["view"]) for p in r.json()["photos"]] == [("front", None), ("detail", "top")]   # replaced
    r = c.post(url, files={"photo": ("t.jpg", jpeg(top), "image/jpeg")}, data={"view": "side"})
    assert r.status_code == 422
    sv.worker.drain()
    assert r.status_code == 422 and c.get(f"/api/items/{item['id']}").json()["cutout_state"] == "ready"


# ------------------------------------------------------------------ Add's instant check

def test_the_instant_check_passes_a_side_on_photo_and_says_why_it_turns_one_down(make, shoe):
    sv, c = make(Tracer(shoe))
    ok = c.post("/api/shoes/check", files={"photo": ("s.jpg", jpeg(S.draw(noise=3)[0]), "image/jpeg")}).json()
    assert ok == {"ok": True, "reasons": []}
    front = c.post("/api/shoes/check", files={"photo": ("f.jpg", jpeg(S.front_view()), "image/jpeg")}).json()
    assert front["ok"] is False and front["reasons"]
    assert all(r.startswith("The photo ") and "limit" not in r for r in front["reasons"])
    bad = c.post("/api/shoes/check", files={"photo": ("x.jpg", b"not a photo", "image/jpeg")})
    assert bad.status_code == 400


def test_the_instant_check_needs_the_login(cfg):
    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, tagger=Tagger(None), routes=lambda: ())
    try:
        anon = TestClient(app_module.create_app(sv))
        assert anon.post("/api/shoes/check", files={"photo": ("s.jpg", b"x", "image/jpeg")}).status_code == 401
    finally:
        sv.stop()


# ------------------------------------------------------------------ the real tracer, start to finish

def test_the_real_tracer_traces_a_synthetic_photo(cfg, make):
    img = S.draw(S.Shoe(toe_cap=S.RED, laces=S.WHITE), noise=3)[0]
    sv, c = make(tracejobs.tracer())
    item = a_shoe(sv, c, data=jpeg(img))
    assert item["trace"]["state"] == "done", item["trace"]
    assert item["trace"]["drawn"] and "toe_cap" in [p["name"] for p in item["trace"]["parts"]]
