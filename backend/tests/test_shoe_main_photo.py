"""A shoe in one step (16 November): the owner adds all of a shoe's photos at once on Add, in any order, and the
main photo follows the sorting (`shoeviews.promote`): once the photos are sorted into views, a main photo that is not
a side view gives way to the outer side, else the inner side. That photo becomes the closet picture (cut out as
usual) and the photo traced for the shoe's drawing, while Claude's words on the photo it saw first stay with that
photo (`items.tag_photo_id`, migration 0029) and the item is not described again.

Claude is never called: stand-ins describe, sort and trace. Every photo is made up (`conftest.photo_bytes`).
"""
from contextlib import closing
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from closet import app as app_module
from closet import db, shoeviews, tagjobs, tracejobs
from closet.drawing import trace as T
from closet.drawing import traced

from . import shoe_photos as S
from .conftest import PASSPHRASE, fake_cutter, photo_for, upload
from .test_shoeviews import Sorter, add, answer, later
from .test_tracejobs import Tagger, Tracer, tags

S_, U = True, False   # sure, unsure


@pytest.fixture(scope="module")
def side_shoe() -> traced.TracedShoe:
    """A navy sneaker with white stripes, traced once from a made-up side-on photo."""
    made = traced.traced_shoe(T.trace_photo(S.draw(S.Shoe(stripes=S.WHITE))[0]))
    assert made is not None and made.gate["ok"]
    return made


@pytest.fixture
def make(cfg, side_shoe):
    built = []

    def build(reply, described=None):
        sorter, tracer = Sorter(reply), Tracer(side_shoe)
        sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, tagger=Tagger(described),
                                       routes=lambda: ("plan",), sorter=sorter, tracer=tracer)
        sv.worker.is_ready = lambda: True
        built.append(sv)
        c = TestClient(app_module.create_app(sv))
        assert c.post("/api/setup", json={"passphrase": PASSPHRASE}).status_code == 204
        return SimpleNamespace(sv=sv, c=c, sorter=sorter, tracer=tracer)
    yield build
    for sv in built:
        sv.stop()


def from_add(c, key="k1") -> dict:
    """A shoe added from "A shoe" on Add: its first photo."""
    r = c.post("/api/items", files={"photo": ("p.jpg", photo_for(key), "image/jpeg")},
               data={"client_key": key, "shoe": "true"})
    assert r.status_code == 201, r.text
    return r.json()


def a_shoe(m, n_more: int, key="k1") -> tuple[dict, list[str]]:
    """A shoe the owner said is a sneaker, with `n_more` more photos, its first photo cut out. Returns the item and
    its photo ids in the order added."""
    item = from_add(m.c, key)
    ids = [item["photos"][0]["id"]] + [add(m.c, item, n).json()["photos"][-1]["id"] for n in range(n_more)]
    assert m.c.patch(f"/api/items/{item['id']}", json={"category": "sneakers"}).status_code == 200
    m.sv.worker.drain()
    return item, ids


def get(c, item) -> dict:
    return c.get(f"/api/items/{item['id']}").json()


def main_and_views(c, item) -> list[tuple]:
    return [(p["id"], p["kind"], p["view"]) for p in get(c, item)["photos"]]


def row(cfg, item_id) -> dict:
    with closing(db.connect(cfg.db_path("main"))) as conn:
        return dict(conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone())


def sql(cfg, query, args=()):
    with closing(db.connect(cfg.db_path("main"))) as conn:
        return conn.execute(query, args).fetchall()


def queued(cfg, item_id, kind) -> list[str | None]:
    return [r["photo_id"] for r in sql(cfg, "SELECT photo_id FROM jobs WHERE kind = ? AND item_id = ? AND state = 'queued'",
                                       (kind, item_id))]


# ------------------------------------------------------------------ the main photo follows the sorting

def test_a_first_photo_from_above_gives_way_to_the_outer_side(cfg, make):
    m = make(answer(("top", S_), ("outer", S_), ("inner", S_)), described=tags(shoes_in_photo="one", shoe_view="top"))
    item, (first, outer, inner) = a_shoe(m, 2)
    m.sv.tag_worker.drain()   # Claude: a sneaker, the first photo seen from above
    assert row(cfg, item["id"])["tag_photo_id"] == first
    # the shoe is not traced from the photo from above while its photos wait to be sorted
    m.sv.worker.drain()
    assert m.tracer.calls == [] and get(m.c, item)["trace"]["state"] == "waiting"

    m.sv.views.drain(now=later())
    got = get(m.c, item)
    assert [(p["id"], p["kind"], p["view"]) for p in got["photos"]] == [
        (outer, "front", "outer"), (first, "detail", "top"), (inner, "detail", "inner")]
    assert got["views"]["state"] == "sorted"
    # the closet picture: the new main photo is cut out (its own thumbnail until then), not described again
    assert got["cutout_state"] == "pending" and queued(cfg, item["id"], "cutout") == [outer]
    assert got["thumb_url"] == got["photos"][0]["thumb_url"]
    m.sv.worker.drain()
    got = get(m.c, item)
    assert got["cutout_state"] == "ready" and got["photos"][0]["cutout_url"]
    assert got["thumb_url"] == got["photos"][0]["cutout_thumb_url"]
    assert m.c.get("/api/items").json()["items"][0]["thumb_url"] == got["photos"][0]["cutout_thumb_url"]
    assert queued(cfg, item["id"], "tag") == [] and got["tag_state"] == "done"
    # traced from the outer side, without Claude's word on the photo from above, which stays with that photo
    assert m.tracer.calls == [{}] and got["trace"]["state"] == "done" and got["trace"]["drawn"]
    with closing(db.connect(cfg.db_path("main"))) as conn:
        r = conn.execute("SELECT * FROM items WHERE id = ?", (item["id"],)).fetchone()
        photo = {p["id"]: p for p in conn.execute("SELECT * FROM photos WHERE item_id = ?", (item["id"],))}
        assert tracejobs.told(r, photo[outer]) == {}
        assert tracejobs.told(r, photo[first]) == {"shoes_in_photo": "one", "shoe_view": "top"}
        # everything that reads the main photo first reads the outer side now: drawing, describing, sorting again
        assert shoeviews.photos_of(conn, item["id"])[0]["id"] == outer
        assert tagjobs._photo_rows(conn, item["id"])[0]["id"] == outer
        assert tracejobs._front(conn, item["id"])["id"] == outer


def test_the_new_main_photo_is_the_one_retaken_and_never_removed_and_photos_are_still_known(cfg, make):
    m = make(answer(("front", S_), ("outer", S_)))
    item, (first, outer) = a_shoe(m, 1)
    m.sv.views.drain(now=later())
    m.sv.worker.drain()
    assert [p["id"] for p in get(m.c, item)["photos"]] == [outer, first]
    r = m.c.delete(f"/api/items/{item['id']}/photos/{outer}")
    assert r.status_code == 409 and "Retake the photo" in r.json()["detail"]
    # the same photos are still known as this shoe's: as a new item, or again on the shoe
    again = m.c.post("/api/items", files={"photo": ("p.jpg", photo_for("k1"), "image/jpeg")}, data={"client_key": "k9"})
    assert again.json()["duplicate"] is True and again.json()["id"] == item["id"]
    assert add(m.c, item, 0).status_code == 409   # the outer side's photo, added a second time
    # a retake replaces the main photo, the outer side now; a retaken photo is described again once cut out
    sql(cfg, "UPDATE items SET tagged_at = ?, tag_state = 'done' WHERE id = ?", (db.now(), item["id"]))
    sql(cfg, "UPDATE jobs SET state = 'done' WHERE kind = 'tag' AND item_id = ?", (item["id"],))   # described
    got = m.c.post(f"/api/items/{item['id']}/photo", files={"photo": ("p.jpg", photo_for("retake"), "image/jpeg")}).json()
    assert [p["id"] for p in got["photos"]][1:] == [first] and got["photos"][0]["id"] not in (first, outer)
    m.sv.worker.drain()
    assert queued(cfg, item["id"], "tag") == [None]
    # the old main photo can be removed like any other
    assert m.c.delete(f"/api/items/{item['id']}/photos/{first}").status_code == 200


def test_a_view_the_owner_named_wins_over_claudes(cfg, make):
    m = make(answer(("top", S_), ("outer", S_), ("inner", S_)))
    item, (first, model_outer, owner_outer) = a_shoe(m, 2)
    # the owner said the third photo is the outside before the photos were sorted; Claude says the second
    m.c.put(f"/api/items/{item['id']}/photos/{owner_outer}/view", json={"view": "outer"})
    m.sv.views.drain(now=later())
    assert main_and_views(m.c, item) == [(owner_outer, "front", "outer"), (first, "detail", "top"),
                                         (model_outer, "detail", "outer")]


def test_a_main_photo_the_owner_named_a_side_stays(cfg, make):
    m = make(answer(("top", S_), ("outer", S_)))
    item, (first, other) = a_shoe(m, 1)
    m.c.put(f"/api/items/{item['id']}/photos/{first}/view", json={"view": "inner"})
    m.sv.views.drain(now=later())   # Claude says the main photo is from above: the owner's word is kept
    assert main_and_views(m.c, item) == [(first, "front", "inner"), (other, "detail", "outer")]
    assert queued(cfg, item["id"], "cutout") == []


@pytest.mark.parametrize("views", [
    [("top", S_), ("front", S_), ("back", S_)],     # no side photo: nothing changes
    [("inner", S_), ("outer", S_)],                 # already a side photo (the inner one): nothing changes
    [("outer", U), ("top", S_)],                    # already a side photo, even unsure
])
def test_nothing_changes_without_a_side_photo_or_with_one_already_the_main(cfg, make, views):
    m = make(answer(*views))
    item, ids = a_shoe(m, len(views) - 1)
    m.sv.views.drain(now=later())
    got = get(m.c, item)
    assert [p["id"] for p in got["photos"]] == ids and got["photos"][0]["kind"] == "front"
    assert got["views"]["state"] == "sorted" and got["cutout_state"] == "ready"
    assert queued(cfg, item["id"], "cutout") == []


def test_with_no_outer_side_the_inner_side_is_the_main_photo(cfg, make):
    m = make(answer(("front", S_), ("back", S_), ("inner", U)))
    item, (first, back, inner) = a_shoe(m, 2)
    m.sv.views.drain(now=later())
    assert main_and_views(m.c, item) == [(inner, "front", "inner"), (first, "detail", "front"), (back, "detail", "back")]


def test_while_the_owner_is_asked_the_main_photo_waits_for_the_answer(cfg, make):
    m = make(answer(("top", S_), ("outer", U), ("inner", U), differ=True))
    item, (first, guess_outer, guess_inner) = a_shoe(m, 2)
    m.sv.views.drain(now=later())
    got = get(m.c, item)
    assert got["views"]["state"] == "asking" and got["photos"][0]["id"] == first
    # the owner says the third photo shows the outside: that one becomes the main photo
    got = m.c.put(f"/api/items/{item['id']}/photos/{guess_inner}/view", json={"view": "outer"}).json()
    assert [(p["id"], p["kind"], p["view"], p["view_by"]) for p in got["photos"]] == [
        (guess_inner, "front", "outer", "owner"), (first, "detail", "top", "model"),
        (guess_outer, "detail", "inner", "owner")]
    assert got["views"]["state"] == "sorted" and got["cutout_state"] == "pending"


def test_the_old_main_photo_from_the_front_is_read_for_the_front_view_once_it_is_not_the_main_one(cfg, make):
    m = make(answer(("front", S_), ("outer", S_)))
    item, (first, outer) = a_shoe(m, 1)
    m.sv.views.drain(now=later())
    with closing(db.connect(cfg.db_path("main"))) as conn:
        assert tracejobs.look_photo(conn, item["id"])["id"] == first


def test_a_shoe_kept_from_before_is_unaffected_until_its_photos_are_sorted_again(cfg, make):
    m = make(answer(("top", S_), ("outer", S_), ("front", S_)))
    item, (first, outer) = a_shoe(m, 1)
    # sorted by the version before this one: the main photo from above, another from the outer side
    sql(cfg, "UPDATE photos SET view = CASE id WHEN ? THEN 'top' ELSE 'outer' END, view_sure = 1, view_by = 'model' "
             "WHERE item_id = ?", (first, item["id"]))
    sql(cfg, "UPDATE items SET views_state = 'sorted' WHERE id = ?", (item["id"],))
    assert m.sv.views.drain(now=later()) == 0
    m.sv.worker.drain()
    assert main_and_views(m.c, item) == [(first, "front", "top"), (outer, "detail", "outer")]
    assert m.sorter.calls == [] and queued(cfg, item["id"], "cutout") == []
    # the owner adds a photo: sorted again, and then the main photo follows
    third = add(m.c, item, 5).json()["photos"][-1]["id"]
    m.sv.views.drain(now=later())
    assert main_and_views(m.c, item) == [(outer, "front", "outer"), (first, "detail", "top"), (third, "detail", "front")]


def test_a_shoe_waits_to_be_traced_only_while_its_photos_are_about_to_be_sorted(cfg, make):
    m = make(answer(("outer", S_), ("top", S_)), described=tags(shoes_in_photo="one", shoe_view="side"))
    item, (first, _) = a_shoe(m, 1)
    m.sv.tag_worker.drain()
    m.sv.worker.drain()
    assert m.tracer.calls == []
    # Claude can't be reached to sort them: the shoe is traced from its main photo meanwhile
    sql(cfg, "UPDATE items SET views_error = ? WHERE id = ?", (shoeviews.NO_ROUTE, item["id"]))
    m.sv.worker.drain()
    assert m.tracer.calls == [{"shoes_in_photo": "one", "shoe_view": "side"}]
    # a shoe traced before waits for nothing when a photo is added (traced again only when what it reads changed)
    sql(cfg, "UPDATE items SET views_error = NULL, views_state = 'waiting', trace_state = 'waiting' WHERE id = ?",
        (item["id"],))
    m.sv.worker.drain()
    assert len(m.tracer.calls) == 2


def test_claude_seeing_the_pair_in_the_main_photo_is_said_on_the_item_page(cfg, make):
    m = make(answer(("outer", S_), ("inner", S_)), described=tags(shoes_in_photo="pair", shoe_view="side"))
    item, _ = a_shoe(m, 1)
    m.sv.tag_worker.drain()
    m.sv.views.drain(now=later())   # the pair seen from the side: a side view, so it stays the main photo
    m.sv.worker.drain()
    trace = get(m.c, item)["trace"]
    assert trace["state"] == "refused"
    assert trace["message"].startswith("The photo shows both shoes of a pair")
    assert "A photo of one shoe on its own" in trace["message"]


def test_the_demo_closet_never_sorts_so_its_main_photo_never_changes(cfg, make):
    m = make(answer(("top", S_), ("outer", S_)))
    assert m.c.post("/api/profile", json={"profile": "demo"}).status_code == 200
    item = from_add(m.c, "demo-shoe")
    add(m.c, item, 1)
    m.c.patch(f"/api/items/{item['id']}", json={"category": "boots"})
    assert m.sv.views.drain(now=later()) == 0 and m.sorter.calls == []
    assert get(m.c, item)["photos"][0]["id"] == item["photos"][0]["id"]


# ------------------------------------------------------------------ the photo Claude's description saw first

def test_the_description_keeps_the_photo_it_saw_first(cfg, make):
    m = make(answer(("outer", S_)), described=tags(shoes_in_photo="one", shoe_view="side"))
    item = upload(m.c).json()
    m.sv.worker.drain()
    m.sv.tag_worker.drain()
    assert row(cfg, item["id"])["tag_photo_id"] == item["photos"][0]["id"]


def test_the_migration_keeps_claudes_word_with_the_main_photo_it_was_about(cfg):
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    with closing(db.connect(cfg.db_path("main"))) as conn:
        for v, path in db.migration_files():
            if v <= 28:
                conn.executescript(f"BEGIN IMMEDIATE;\n{path.read_text(encoding='utf-8')}\nPRAGMA user_version = {v};\nCOMMIT;")
        # described after its photo; described before its photo was replaced; never described
        for item_id, photo_at, tagged_at, answer_ in (("a", "2026-11-01T10:00:00Z", "2026-11-01T10:01:00Z", "{}"),
                                                      ("b", "2026-11-02T10:00:00Z", "2026-11-01T10:01:00Z", "{}"),
                                                      ("c", "2026-11-01T10:00:00Z", None, None)):
            conn.execute("INSERT INTO items (id, category, tag_answer, tagged_at, created_at, updated_at) "
                         "VALUES (?, 'sneakers', ?, ?, ?, ?)", (item_id, answer_, tagged_at, photo_at, photo_at))
            conn.execute("INSERT INTO photos (id, item_id, kind, original_path, thumb_path, created_at) VALUES "
                         "(?, ?, 'front', 'x.webp', 'x-t.webp', ?)", (f"{item_id}-main", item_id, photo_at))
            conn.execute("INSERT INTO photos (id, item_id, kind, original_path, thumb_path, created_at) VALUES "
                         "(?, ?, 'detail', 'y.webp', 'y-t.webp', ?)", (f"{item_id}-other", item_id, photo_at))
    db.migrate(cfg.db_path("main"), cfg.local_backups_dir)
    with closing(db.connect(cfg.db_path("main"))) as conn:
        got = {r["id"]: r["tag_photo_id"] for r in conn.execute("SELECT id, tag_photo_id FROM items")}
        assert got == {"a": "a-main", "b": None, "c": None}
        assert {r["id"]: r["kind"] for r in conn.execute("SELECT id, kind FROM photos WHERE item_id = 'a'")} == {
            "a-main": "front", "a-other": "detail"}   # no photo changes: nothing is promoted by the migration
