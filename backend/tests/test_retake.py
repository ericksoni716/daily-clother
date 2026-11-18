""""Retake the photo" for clothes: a new main photo in place of the old one, for anything that is not a shoe.

The item keeps its id, wears, rating, laundry and everything the owner set; it is cut out, described and its pattern
measured again from the new photo. Shoes keep their own path (traced again: test_tracejobs.py, test_shoeviews.py,
test_shoe_main_photo.py)."""

import pytest
from fastapi.testclient import TestClient

from closet import app as app_module
from closet import db, items, patjobs, tracejobs

from .conftest import PASSPHRASE, FakeFinder, fake_cutter, photo_bytes, photo_for, pile_bytes, upload
from .test_patjobs import Measurer


@pytest.fixture
def stand(cfg, claude):
    """The services with every stand-in a retake goes through: the cutter, Claude, the pattern measurer (`m`,
    failing until told otherwise) and the finder of pieces in a photo of several."""
    claude.mode = "answers"
    m = Measurer(fail=True)
    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, tagger=claude, routes=lambda: claude.routes(),
                                   corrector=claude.correct, finder=FakeFinder(), measurer=m, landmarker=None)
    sv.worker.is_ready = lambda: True
    c = TestClient(app_module.create_app(sv))
    assert c.post("/api/setup", json={"passphrase": PASSPHRASE}).status_code == 204
    yield sv, c, m
    sv.stop()


def row(cfg, item_id, profile="main"):
    conn = db.connect(cfg.db_path(profile))
    try:
        return dict(conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone())
    finally:
        conn.close()


def sql(cfg, query, args=(), profile="main"):
    conn = db.connect(cfg.db_path(profile))
    try:
        return conn.execute(query, args).fetchall()
    finally:
        conn.close()


def retake(c, item_id, data=None, key="new"):
    return c.post(f"/api/items/{item_id}/photo", files={"photo": ("p.jpg", data or photo_for(key), "image/jpeg")})


def described(sv, c, key="k1"):
    item = upload(c, key=key).json()
    sv.worker.drain()
    sv.tag_worker.drain()
    return c.get(f"/api/items/{item['id']}").json()


def a_plaid_not_measured(sv, c, cfg):
    """A described polo the owner says is plaid, whose checks could not be measured from its photo."""
    item = described(sv, c)
    assert c.patch(f"/api/items/{item['id']}", json={"pattern": "plaid"}).status_code == 200
    sv.pattern_worker.drain()
    got = c.get(f"/api/items/{item['id']}").json()
    assert got["pattern_state"] == "failed" and got["pattern_error"] == patjobs.PLAID_FAILED
    return got


def test_a_new_photo_is_cut_out_described_and_its_pattern_measured_again(stand, cfg, claude):
    sv, c, m = stand
    item = a_plaid_not_measured(sv, c, cfg)
    url = f"/api/items/{item['id']}"
    # what the owner set and did, which the new photo must not cost
    assert c.patch(url, json={"name": "Lake shirt", "brand": "Acme", "rating": "love"}).status_code == 200
    assert c.put(f"{url}/details", json={"details": {"placket_buttons": 2}}).status_code == 200
    assert c.post(f"{url}/wears").status_code in (200, 201)
    assert c.post(f"{url}/laundry", json={"state": "laundry"}).status_code == 200
    before = c.get(url).json()
    old = before["photos"][0]
    asked = len(claude.calls)

    r = retake(c, item["id"])
    assert r.status_code == 200
    got = r.json()
    assert got["id"] == item["id"] and got["cutout_state"] == "pending"
    assert [p["kind"] for p in got["photos"]] == ["front"] and got["photos"][0]["id"] != old["id"]
    for key in ("url", "cutout_url"):   # the old photo's files are gone
        assert not (cfg.images_dir("main") / old[key].removeprefix("/media/")).exists()
    # nothing measured from the old photo is shown as if it were about the new one
    assert got["pattern_state"] is None and got["pattern_error"] is None
    kept = row(cfg, item["id"])
    assert kept["pattern_fill"] is None and kept["landmarks"] is None

    assert sv.worker.drain() == 1                      # cut out again ...
    assert row(cfg, item["id"])["tag_state"] == "waiting"
    assert sv.tag_worker.drain() == 1 and len(claude.calls) == asked + 1   # ... described again ...
    assert c.get(url).json()["pattern_state"] == "waiting"                  # ... and measured again
    m.fail = False
    assert sv.pattern_worker.drain() == 1
    after = c.get(url).json()
    assert after["pattern_state"] == "done" and after["pattern_error"] is None and after["tag_state"] == "done"
    assert after["tagged_at"] > before["tagged_at"]
    # the owner's word stays theirs; wears, rating and laundry stay
    assert after["pattern"] == "plaid" and after["source"]["pattern"] == "user"
    assert after["name"] == "Lake shirt" and after["brand"] == "Acme" and after["rating"] == "love"
    assert after["own_details"] == {"placket_buttons": 2}
    assert after["wear_count"] == 1 and after["recent_wears"] == before["recent_wears"]
    assert after["laundry"] == "laundry" and after["wears_since_wash"] == before["wears_since_wash"]
    assert after["category"] == "polo"                 # what Claude said, said again


def test_a_measured_pattern_goes_with_the_old_photo(stand, cfg):
    sv, c, m = stand
    m.fail = False
    item = described(sv, c)
    c.patch(f"/api/items/{item['id']}", json={"pattern": "stripe"})
    sv.pattern_worker.drain()
    assert row(cfg, item["id"])["pattern_fill"]
    got = retake(c, item["id"]).json()
    assert got["pattern_state"] is None and got["pattern_colors"] == []
    assert row(cfg, item["id"])["pattern_fill"] is None
    assert sv.pattern_worker.drain() == 0              # not measured before it is described again
    sv.worker.drain()
    sv.tag_worker.drain()
    assert sv.pattern_worker.drain() == 1 and row(cfg, item["id"])["pattern_state"] == "done"


def test_a_measurement_of_the_old_photo_still_running_is_not_kept(stand, cfg):
    sv, c, m = stand
    m.fail = False
    item = described(sv, c)
    c.patch(f"/api/items/{item['id']}", json={"pattern": "stripe"})
    sent = []

    def meanwhile(*args):   # the owner sends a new photo while the old one is being measured
        sent.append(retake(c, item["id"]).status_code)
        return m(*args)
    sv.pattern_worker.measurer = meanwhile
    sv.pattern_worker.drain()
    kept = row(cfg, item["id"])
    assert sent == [200] and kept["pattern_state"] is None and kept["pattern_fill"] is None


def test_refused_while_its_cutout_is_being_made(stand, cfg):
    sv, c, _ = stand
    item = upload(c).json()
    sql(cfg, "UPDATE jobs SET state = 'running' WHERE item_id = ?", (item["id"],))
    files = sorted(p.name for p in (cfg.images_dir("main") / item["id"]).iterdir())
    r = retake(c, item["id"])
    assert r.status_code == 409 and r.json()["detail"] == items.RUNNING_CUTOUT
    assert c.get(f"/api/items/{item['id']}").json()["photos"][0]["id"] == item["photos"][0]["id"]
    assert sorted(p.name for p in (cfg.images_dir("main") / item["id"]).iterdir()) == files   # nothing left behind


def test_a_queued_cutout_of_the_old_photo_is_dropped(stand, cfg):
    sv, c, _ = stand
    item = upload(c).json()                            # its cutout is queued, not made yet
    got = retake(c, item["id"]).json()
    queued = sql(cfg, "SELECT photo_id FROM jobs WHERE kind = 'cutout' AND item_id = ? AND state = 'queued'", (item["id"],))
    assert [q[0] for q in queued] == [got["photos"][0]["id"]]
    assert sv.worker.drain() == 1


def test_a_photo_already_in_the_closet_is_refused(stand, cfg):
    sv, c, _ = stand
    item = described(sv, c)
    upload(c, key="k2")
    r = retake(c, item["id"], photo_for("k2"))         # another item's photo
    assert r.status_code == 409 and r.json()["detail"] == items.ELSEWHERE
    pile = pile_bytes()
    c.post("/api/sources", files={"photo": ("pile.png", pile, "image/png")}, data={"client_key": "s1"})
    r = retake(c, item["id"], pile)                    # a photo of several pieces waiting on Add
    assert r.status_code == 409 and r.json()["detail"] == items.WAITING_SOURCE
    assert c.get(f"/api/items/{item['id']}").json()["photos"][0]["id"] == item["photos"][0]["id"]
    assert len(list((cfg.images_dir("main") / item["id"]).glob("*"))) == len(
        [k for k in ("url", "thumb_url", "cutout_url", "cutout_thumb_url") if item["photos"][0][k]])
    # its own photo again is a retake like any other (as for a shoe)
    assert retake(c, item["id"], photo_for("k1")).status_code == 200


def test_an_item_cut_from_a_photo_of_several_leaves_it(stand, cfg):
    sv, c, _ = stand
    sid = c.post("/api/sources", files={"photo": ("pile.png", pile_bytes(), "image/png")},
                 data={"client_key": "s1"}).json()["source"]["id"]
    sv.finder.drain()
    made = c.post(f"/api/sources/{sid}/add").json()["items"]
    first, *others = [i["id"] for i in made]
    assert others
    sv.worker.drain()
    folder = cfg.images_dir("main") / "sources" / sid

    got = retake(c, first).json()
    assert got["source_photo"] is None                 # its photo is its own now
    assert row(cfg, first)["source_box"] is None
    assert all(c.get(f"/api/items/{o}").json()["source_photo"]["id"] == sid for o in others)   # the others keep it
    assert folder.exists()

    for n, other in enumerate(others):
        assert retake(c, other, photo_bytes(color=(20, 160, 90 + 40 * n))).json()["source_photo"] is None
    assert sql(cfg, "SELECT COUNT(*) FROM source_photos")[0][0] == 0   # cut from by no item: not kept for nothing
    assert not folder.exists()


def test_the_demo_closet_is_cut_out_again_but_never_sent_to_claude(stand, cfg, claude):
    sv, c, m = stand
    assert c.post("/api/profile", json={"profile": "demo"}).status_code == 200
    item = next(i for i in c.get("/api/items").json()["items"]
                if not tracejobs.wanted(i["category"]) and i["has_photo"])
    before = c.get(f"/api/items/{item['id']}").json()
    asked = len(claude.calls)
    r = retake(c, item["id"])
    assert r.status_code == 200 and r.json()["cutout_state"] == "pending"
    assert sv.worker.drain() == 1
    after = c.get(f"/api/items/{item['id']}").json()
    assert after["cutout_state"] == "ready" and after["photos"][0]["cutout_url"]
    assert len(claude.calls) == asked and sv.tag_worker.drain() == 0
    assert after["tag_state"] == before["tag_state"] and after["tagged_at"] == before["tagged_at"]
    assert after["category"] == before["category"] and after["pattern_state"] is None
    assert sv.pattern_worker.drain() == 0 and m.calls == []
    assert after["source"] == before["source"]


def test_an_item_that_does_not_exist(stand):
    _, c, _ = stand
    assert retake(c, "nope").status_code == 404
