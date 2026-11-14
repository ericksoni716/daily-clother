"""Several items from one photo: the boxes Claude finds, the owner's changes to them, and the items made from them.

Every photo here is drawn (coloured shapes on a pale background); Claude is a stand-in throughout.
"""
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from closet import app as app_module
from closet import db, sources, spend
from closet.tagger import garments
from closet.tagger.tagging import CapReached, RouteUnavailable, TaggingError, TagResult

from .conftest import ANSWER, GARMENT_BOXES, PASSPHRASE, FakeApi, FakeFinder, fake_cutter, photo_bytes, pile_bytes, upload


@pytest.fixture
def finder():
    return FakeFinder()


@pytest.fixture
def sv(cfg, claude, finder):
    claude.mode = "answers"
    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, tagger=claude, routes=lambda: claude.routes(),
                                   corrector=claude.correct, finder=finder, measurer=lambda *a: None, landmarker=None)
    sv.worker.is_ready = lambda: True   # the model stands in as downloaded
    yield sv
    sv.stop()


@pytest.fixture
def c(sv):
    client = TestClient(app_module.create_app(sv))
    assert client.post("/api/setup", json={"passphrase": PASSPHRASE}).status_code == 204
    return client


def send(c, data=None, key="s1", sha=None):
    fields = {"client_key": key}
    if sha:
        fields["photo_sha256"] = sha
    return c.post("/api/sources", files={"photo": ("pile.png", data or pile_bytes(), "image/png")}, data=fields)


def found(c, sv, key="s1", data=None):
    """A photo sent and its boxes found by the stand-in."""
    body = send(c, data, key).json()
    assert body["source"]["state"] == "finding"
    sv.finder.drain()
    return c.get(f"/api/sources/{body['source']['id']}").json()


def edges(box):
    return [box[k] for k in sources.EDGES]


# ------------------------------------------------------------------ finding the boxes

def test_a_photo_waits_for_its_boxes_then_shows_what_claude_found(c, sv, finder):
    sent = send(c)
    assert sent.status_code == 201
    body = sent.json()
    assert body["duplicate"] is False and body["item"] is None
    src = body["source"]
    assert src["state"] == "finding" and src["boxes"] == [] and src["photo_url"].startswith("/media/sources/")
    assert c.get(src["photo_url"]).status_code == 200
    assert [s["id"] for s in c.get("/api/sources").json()["sources"]] == [src["id"]]
    assert sv.finder.drain() == 1 and finder.calls == 1
    src = c.get(f"/api/sources/{src['id']}").json()
    assert src["state"] == "review" and src["found_by"] == "claude" and src["note"] is None
    assert [b["n"] for b in src["boxes"]] == [1, 2, 3]
    assert [b["label"] for b in src["boxes"]] == ["red shirt", "blue trousers", "green scarf"]
    assert [edges(b) for b in src["boxes"]] == [edges(b) for b in GARMENT_BOXES]
    assert c.get("/api/items").json()["items"] == []   # nothing is added before the owner says so


def test_each_box_shows_its_piece_cut_out(c, sv):
    src = found(c, sv)
    url = src["boxes"][0]["cutout_url"]
    r = c.get(url)
    assert r.status_code == 200 and r.headers["content-type"] == "image/webp"
    im = Image.open(io.BytesIO(r.content))
    assert max(im.size) <= sources.PREVIEW_EDGE
    assert c.get(url).content == r.content   # made once for each place of the box


def test_the_cutout_waits_for_the_model(c, sv):
    src = found(c, sv)
    sv.worker.is_ready = lambda: False
    r = c.get(src["boxes"][0]["cutout_url"])
    assert r.status_code == 409 and "model" in r.json()["detail"]


def test_claudes_boxes_are_cut_to_the_photo_and_tidied():
    boxes = sources.tidy([
        {"x0": -0.2, "y0": 0.1, "x1": 0.3, "y1": 1.4, "label": " red shirt "},   # outside the photo: cut to it
        {"x0": 0.02, "y0": 0.12, "x1": 0.31, "y1": 0.98, "label": "red shirt again"},   # the same piece twice
        {"x0": 0.6, "y0": 0.6, "x1": 0.4, "y1": 0.2, "label": "edges reversed"},
        {"x0": 0.5, "y0": 0.5, "x1": 0.5, "y1": 0.9, "label": "empty"},
        {"x0": 0.5, "y0": 0.5, "x1": 0.51, "y1": 0.9, "label": "too thin"},
        {"x0": 1.2, "y0": 0.1, "x1": 1.5, "y1": 0.4, "label": "all outside"},
        {"x0": "a", "y0": 0.1, "x1": 0.4, "y1": 0.4},
        {"x0": float("nan"), "y0": 0.1, "x1": 0.4, "y1": 0.4},
        "not a box",
        {"x0": 0.35, "y0": 0.1, "x1": 0.65, "y1": 0.5, "label": "jacket"},   # overlaps the next, but is its own piece
        {"x0": 0.35, "y0": 0.4, "x1": 0.65, "y1": 0.95, "label": ""},
    ])
    assert [b["label"] for b in boxes] == ["red shirt", "edges reversed", "jacket", None]
    assert edges(boxes[0]) == [0.0, 0.1, 0.31, 1.0]   # cut to the photo, and joined with its twin
    assert edges(boxes[1]) == [0.4, 0.2, 0.6, 0.6]
    assert len({b["id"] for b in boxes}) == 4
    assert sources.tidy("not a list") == [] and sources.tidy([]) == []
    many = sources.tidy([{"x0": i / 50, "y0": 0, "x1": i / 50 + 0.04, "y1": 0.1} for i in range(40)])
    assert len(many) == sources.MAX_BOXES


def test_overlapping_and_empty_boxes_from_claude(c, sv, finder):
    finder.boxes = [GARMENT_BOXES[0], {**GARMENT_BOXES[0], "x1": 0.31, "label": "twin"},
                    {"x0": 0.5, "y0": 0.5, "x1": 0.5, "y1": 0.5}, {**GARMENT_BOXES[2], "x1": 1.6}]
    src = found(c, sv)
    assert [b["label"] for b in src["boxes"]] == ["red shirt", "green scarf"]
    assert src["boxes"][0]["x1"] == 0.31 and src["boxes"][1]["x1"] == 1.0


def test_no_clothes_found_asks_the_owner_to_draw_them(c, sv, finder):
    finder.boxes = []
    src = found(c, sv)
    assert src["state"] == "review" and src["boxes"] == [] and src["note"] == sources.NONE_FOUND


def test_no_route_waits_with_a_note_and_finds_once_claude_can_be_reached(c, sv, claude, finder):
    claude.mode = "unavailable"
    sid = send(c).json()["source"]["id"]
    assert sv.finder.drain() == 0 and finder.calls == 0
    src = c.get(f"/api/sources/{sid}").json()
    assert src["state"] == "finding" and src["note"] == sources.NO_ROUTE
    claude.mode = "answers"
    assert sv.finder.drain() == 1
    src = c.get(f"/api/sources/{sid}").json()
    assert src["state"] == "review" and src["note"] is None and len(src["boxes"]) == 3


def test_a_route_that_turns_out_unusable_waits_too(c, sv, finder):
    finder.error = RouteUnavailable("no")
    sid = send(c).json()["source"]["id"]
    sv.finder.drain()
    assert c.get(f"/api/sources/{sid}").json()["note"] == sources.NO_ROUTE
    finder.error = CapReached("limit")
    sv.finder.drain()
    src = c.get(f"/api/sources/{sid}").json()
    assert src["state"] == "finding" and src["note"] == sources.LIMIT


def test_after_three_failures_the_owner_draws_the_boxes(c, sv, finder):
    finder.error = TaggingError("the answer was outside the schema")
    sid = send(c).json()["source"]["id"]
    sv.finder.drain()
    assert finder.calls == sources.MAX_ATTEMPTS
    src = c.get(f"/api/sources/{sid}").json()
    assert src["state"] == "review" and src["boxes"] == [] and src["note"] == sources.FAILED


# ------------------------------------------------------------------ the spending limit

@pytest.fixture
def api_build(cfg):
    held = {}

    def build(api):
        sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, routes=lambda: ("api",), api_client=api)
        held["sv"] = sv
        client = TestClient(app_module.create_app(sv))
        assert client.post("/api/setup", json={"passphrase": PASSPHRASE}).status_code == 204
        return sv, client
    yield build
    if "sv" in held:
        held["sv"].stop()


def test_finding_goes_through_the_api_key_and_its_monthly_limit(api_build, cfg):
    api = FakeApi(input_tokens=3000, output_tokens=500)
    sv, c = api_build(api)
    assert c.get("/api/tagging/spend").json()["per_find_usd"] == pytest.approx(spend.estimate_garments(1), abs=1e-6)
    c.put("/api/settings", json={"tagging_api_enabled": True, "tagging_api_cap_usd": spend.estimate_garments(1) / 2})
    sid = send(c).json()["source"]["id"]
    sv.finder.drain()
    src = c.get(f"/api/sources/{sid}").json()
    assert api.calls == 0   # the estimate is checked first: nothing is sent past the limit
    assert src["state"] == "finding" and src["note"] == sources.LIMIT
    c.put("/api/settings", json={"tagging_api_cap_usd": 1.0})
    assert sv.finder.drain() == 1 and api.calls == 1
    sent = api.requests[0]
    assert sent["output_format"] is garments.Garments and sent["model"] == garments.MODEL
    src = c.get(f"/api/sources/{sid}").json()
    assert src["state"] == "review" and [b["label"] for b in src["boxes"]] == [b["label"] for b in GARMENT_BOXES]
    assert [round(b["x0"], 3) for b in src["boxes"]] == [b["x0"] for b in GARMENT_BOXES]
    conn = db.connect(cfg.db_path("main"))
    try:
        row = conn.execute("SELECT purpose, route, cost_usd FROM claude_calls").fetchone()
    finally:
        conn.close()
    assert row["purpose"] == spend.PURPOSE_GARMENTS and row["route"] == "api"
    assert row["cost_usd"] == pytest.approx(spend.cost_usd(garments.MODEL, 3000, 500))


def test_the_answer_comes_back_as_fractions_of_the_photo():
    api = FakeApi()
    photo = Image.new("RGB", (2048, 1536), (230, 230, 230))
    boxes = garments.ask(photo, ("api",), client=api)
    assert [round(b["x1"], 4) for b in boxes] == [b["x1"] for b in GARMENT_BOXES]
    sent = api.requests[0]["messages"][0]["content"]
    assert any(part.get("type") == "image" for part in sent)


# ------------------------------------------------------------------ the owner's changes

def test_remove_merge_adjust_and_add_boxes(c, sv):
    src = found(c, sv)
    sid, (red, blue, green) = src["id"], [b["id"] for b in src["boxes"]]
    after = c.delete(f"/api/sources/{sid}/boxes/{green}").json()
    assert [b["id"] for b in after["boxes"]] == [red, blue]
    merged = c.post(f"/api/sources/{sid}/boxes/merge", json={"ids": [red, blue]}).json()
    assert len(merged["boxes"]) == 1
    joined = merged["boxes"][0]
    assert joined["id"] == red and joined["label"] == "red shirt" and edges(joined) == [0.05, 0.1, 0.65, 0.9]
    moved = c.put(f"/api/sources/{sid}/boxes/{red}", json={"x0": 0.1, "y0": -0.5, "x1": 0.3, "y1": 0.5}).json()
    assert edges(moved["boxes"][0]) == [0.1, 0.0, 0.3, 0.5]   # dragged past the edge: kept to the photo
    assert moved["boxes"][0]["label"] == "red shirt"
    added = c.post(f"/api/sources/{sid}/boxes", json={"x0": 0.9, "y0": 0.9, "x1": 0.6, "y1": 0.4}).json()
    assert edges(added["boxes"][1]) == [0.6, 0.4, 0.9, 0.9] and added["boxes"][1]["n"] == 2
    assert added["boxes"][1]["cutout_url"] != added["boxes"][0]["cutout_url"]


def test_wrong_box_changes_are_refused(c, sv):
    src = found(c, sv)
    sid, first = src["id"], src["boxes"][0]["id"]
    assert c.post(f"/api/sources/{sid}/boxes", json={"x0": 1.2, "y0": 0, "x1": 1.5, "y1": 1}).status_code == 422
    assert c.put(f"/api/sources/{sid}/boxes/{first}", json={"x0": 0.5, "y0": 0, "x1": 0.5, "y1": 1}).status_code == 422
    assert c.put(f"/api/sources/{sid}/boxes/nope", json={"x0": 0, "y0": 0, "x1": 0.5, "y1": 1}).status_code == 404
    assert c.delete(f"/api/sources/{sid}/boxes/nope").status_code == 404
    assert c.post(f"/api/sources/{sid}/boxes/merge", json={"ids": [first]}).status_code == 422
    assert c.post(f"/api/sources/{sid}/boxes/merge", json={"ids": [first, "nope"]}).status_code == 404
    assert c.get("/api/sources/nope").status_code == 404
    assert len(c.get(f"/api/sources/{sid}").json()["boxes"]) == 3


def test_a_box_drawn_while_claude_is_looking_ends_the_wait(c, sv, finder):
    sid = send(c).json()["source"]["id"]
    drawn = c.post(f"/api/sources/{sid}/boxes", json={"x0": 0.1, "y0": 0.1, "x1": 0.4, "y1": 0.6}).json()
    assert drawn["state"] == "review" and len(drawn["boxes"]) == 1
    conn = db.connect(sv.cfg.db_path("main"))
    try:   # an answer that was already on its way is dropped, not laid over the owner's box
        row = conn.execute("SELECT * FROM source_photos WHERE id = ?", (sid,)).fetchone()
        assert sources.find_one(conn, sv.cfg.images_dir("main"), row, ("plan",), finder) == "done"
    finally:
        conn.close()
    assert len(c.get(f"/api/sources/{sid}").json()["boxes"]) == 1
    assert sv.finder.drain() == 0


# ------------------------------------------------------------------ adding the items

def test_each_box_becomes_an_item_described_like_any_other(c, sv, claude):
    src = found(c, sv)
    sid = src["id"]
    c.delete(f"/api/sources/{sid}/boxes/{src['boxes'][2]['id']}")
    done = c.post(f"/api/sources/{sid}/add")
    assert done.status_code == 200
    body = done.json()
    assert body["state"] == "added" and len(body["items"]) == 2
    assert c.get("/api/sources").json()["sources"] == []
    listed = c.get("/api/items").json()["items"]
    assert len(listed) == 2 and all(i["cutout_state"] == "pending" for i in listed)
    first = c.get(f"/api/items/{body['items'][0]['id']}").json()
    assert first["source_photo"]["id"] == sid and first["source_photo"]["photo_url"] == src["photo_url"]
    assert first["source_photo"]["box"] == {k: GARMENT_BOXES[0][k] for k in sources.EDGES}
    photo = first["photos"][0]
    pile_w, pile_h = src["width"], src["height"]   # the box, with a little of the photo around it
    assert photo["width"] == pytest.approx((0.25 + 2 * sources.PAD) * pile_w, abs=2)
    assert photo["height"] == pytest.approx((0.5 + 2 * sources.PAD) * pile_h, abs=2)
    assert not list((sv.cfg.images_dir("main") / "sources" / sid).glob("cut-*"))   # previews are not kept
    assert sv.worker.drain() == 2
    assert sv.tag_worker.drain() == 2 and len(claude.calls) == 2
    for item in c.get("/api/items").json()["items"]:
        assert item["tag_state"] == "done" and item["category"] == "polo" and item["has_illustration"]


def test_a_patterned_piece_is_measured_like_any_other(cfg, finder):
    striped = ANSWER.model_copy(update={"pattern": "stripe"})
    measured = []

    def tagger(images, routes):
        return TagResult(striped, "claude-haiku-5-5", 0.1, 100, 50, 0.0, 1, route=routes[0])

    def measurer(cut, pattern, words, marks):
        measured.append(pattern)
        return None
    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, tagger=tagger, routes=lambda: ("plan",),
                                   finder=finder, measurer=measurer, landmarker=None)
    sv.worker.is_ready = lambda: True
    try:
        c = TestClient(app_module.create_app(sv))
        assert c.post("/api/setup", json={"passphrase": PASSPHRASE}).status_code == 204
        src = found(c, sv)
        c.post(f"/api/sources/{src['id']}/add")
        sv.worker.drain()
        sv.tag_worker.drain()
        assert all(c.get(f"/api/items/{i['id']}").json()["pattern_state"] == "waiting"
                   for i in c.get("/api/items").json()["items"])
        sv.pattern_worker.drain()
        assert measured == ["stripe"] * 3
    finally:
        sv.stop()


def test_adding_twice_adds_once_and_the_boxes_are_then_fixed(c, sv):
    src = found(c, sv)
    sid = src["id"]
    first = c.post(f"/api/sources/{sid}/add").json()
    again = c.post(f"/api/sources/{sid}/add").json()
    assert [i["id"] for i in again["items"]] == [i["id"] for i in first["items"]]
    assert len(c.get("/api/items").json()["items"]) == 3
    box = src["boxes"][0]["id"]
    assert c.delete(f"/api/sources/{sid}/boxes/{box}").status_code == 409
    assert c.delete(f"/api/sources/{sid}").status_code == 409


def test_nothing_to_add_without_a_box(c, sv, finder):
    finder.boxes = []
    src = found(c, sv)
    r = c.post(f"/api/sources/{src['id']}/add")
    assert r.status_code == 422 and r.json()["detail"] == sources.NO_BOXES


def test_forgetting_a_photo_removes_it(c, sv):
    src = found(c, sv)
    folder = sv.cfg.images_dir("main") / "sources" / src["id"]
    assert folder.exists()
    assert c.delete(f"/api/sources/{src['id']}").status_code == 204
    assert not folder.exists() and c.get(f"/api/sources/{src['id']}").status_code == 404


def test_the_photo_goes_with_the_last_of_its_items(c, sv):
    src = found(c, sv)
    made = c.post(f"/api/sources/{src['id']}/add").json()["items"]
    folder = sv.cfg.images_dir("main") / "sources" / src["id"]
    for item in made[:-1]:
        assert c.delete(f"/api/items/{item['id']}").status_code == 204
    assert folder.exists() and c.get(f"/api/sources/{src['id']}").status_code == 200
    assert c.delete(f"/api/items/{made[-1]['id']}").status_code == 204
    assert not folder.exists() and c.get(f"/api/sources/{src['id']}").status_code == 404
    again = send(c, key="s2")   # and the same photo can then be sent again
    assert again.status_code == 201


# ------------------------------------------------------------------ duplicates

def test_the_same_photo_is_kept_once(c, sv):
    first = send(c, key="a").json()
    retry = send(c, key="a")
    assert retry.status_code == 200 and retry.json()["duplicate"] is False
    assert retry.json()["source"]["id"] == first["source"]["id"]
    again = send(c, key="b")
    assert again.status_code == 200 and again.json()["duplicate"] is True
    assert again.json()["source"]["id"] == first["source"]["id"]
    assert send(c, pile_bytes(shift=7), key="c").status_code == 201   # a different photo is kept
    assert len(c.get("/api/sources").json()["sources"]) == 2


def test_a_photo_already_added_as_one_item_is_not_kept_again(c, sv):
    data = photo_bytes(color=(10, 120, 90))
    item = upload(c, data, key="one").json()
    r = send(c, data, key="many")
    assert r.status_code == 200 and r.json()["duplicate"] is True
    assert r.json()["source"] is None and r.json()["item"]["id"] == item["id"]
    assert c.get("/api/sources").json()["sources"] == []


def test_a_photo_whose_pieces_were_added_is_not_added_again_as_one_item(c, sv):
    data = pile_bytes()
    src = found(c, sv, data=data)
    made = c.post(f"/api/sources/{src['id']}/add").json()["items"]
    single = upload(c, data, key="single")
    assert single.status_code == 200 and single.json()["duplicate"] is True and single.json()["id"] == made[0]["id"]
    several = send(c, data, key="again")
    assert several.status_code == 200 and several.json()["duplicate"] is True
    assert several.json()["source"]["id"] == src["id"]
    assert len(c.get("/api/items").json()["items"]) == 3


def test_the_hash_of_the_picked_file_decides(c, sv):
    sha = "ab" * 32
    first = send(c, pile_bytes(), key="a", sha=sha)
    again = send(c, pile_bytes(shift=9), key="b", sha=sha.upper())
    assert first.status_code == 201 and again.json()["duplicate"] is True
    assert send(c, key="c", sha="not a hash").status_code == 422


# ------------------------------------------------------------------ the demo closet, and older closets

def test_the_demo_closet_never_asks_claude(c, sv, finder):
    assert c.post("/api/profile", json={"profile": "demo"}).status_code == 200
    r = send(c)
    assert r.status_code == 201
    src = r.json()["source"]
    assert src["state"] == "review" and src["note"] == sources.DEMO
    assert sv.finder.drain() == 0 and finder.calls == 0
    drawn = c.post(f"/api/sources/{src['id']}/boxes", json={"x0": 0.05, "y0": 0.1, "x1": 0.3, "y1": 0.6}).json()
    assert drawn["note"] == sources.DEMO   # it stays: still nothing is sent
    made = c.post(f"/api/sources/{src['id']}/add").json()["items"]
    assert len(made) == 1
    sv.worker.drain()
    assert finder.calls == 0
    conn = db.connect(sv.cfg.db_path("demo"))
    try:
        assert conn.execute("SELECT COUNT(*) FROM jobs WHERE kind = 'tag'").fetchone()[0] == 0
    finally:
        conn.close()


def test_an_older_closet_gains_the_photos_table(cfg):
    path = cfg.db_path("main")
    path.parent.mkdir(parents=True, exist_ok=True)
    db.migrate(path, cfg.local_backups_dir)
    conn = db.connect(path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] >= 22
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(items)")}
        assert {"source_photo_id", "source_box"} <= cols
        assert conn.execute("SELECT COUNT(*) FROM source_photos").fetchone()[0] == 0
    finally:
        conn.close()
