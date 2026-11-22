"""The review queue: every new item once, and the fields the tagger was unsure of and the owner has not set.

Claude is never called: `FakeClaude` (conftest) stands in, and each test chooses how sure its answer is.
"""
import json
from contextlib import closing

import pytest

from closet import db, demo, review, vocab
from closet.tagger.tagging import TagResult

from .conftest import ANSWER, upload

# FakeClaude's own answer is unsure only of its formality (0.7)
assert [f for f in review.REVIEWED if getattr(ANSWER, f"{f}_confidence") < review.UNSURE_BELOW[f]] == ["formality"]

DEMO_ORDER = ["Madras plaid shirt", "Marl turtleneck", "White leather sneakers", "Tan chore jacket", "Grey wool trousers"]


def cut(services):
    services.worker.is_ready = lambda: True
    return services.worker.drain()


def tagged(client, services, claude, key, new=False, garment=None, **sure):
    """An item described by Claude, with these confidences (field -> number) in its answer. It counts as checked by
    the owner already (as items kept before the review offered new ones), so only its doubtful fields queue it,
    unless `new`. `garment`: the kind Claude's answer names."""
    answer = ANSWER.model_copy(update={f"{f}_confidence": v for f, v in sure.items()})
    if garment:
        answer = answer.model_copy(update={"details": answer.details.model_copy(update={"garment": garment})})
    services.tag_worker.tagger = lambda images, routes: TagResult(answer, "claude-haiku-5-5", 0.1, 100, 50, 0.0, 1, route=routes[0])
    claude.mode = "answers"
    item = upload(client, key=key).json()
    cut(services)
    assert services.tag_worker.drain() == 1
    claude.mode = "unavailable"
    if not new:
        checked(services, item["id"])
    return item["id"]


def checked(services, item_id):
    with closing(db.connect(services.cfg.db_path("main"))) as conn:
        conn.execute("UPDATE items SET checked_at = ? WHERE id = ?", (db.now(), item_id))


def queue(client):
    r = client.get("/api/review")
    assert r.status_code == 200
    return r.json()


def fields(body, item_id):
    return [f["field"] for f in next(i for i in body["items"] if i["id"] == item_id)["fields"]]


def row(**kw):
    base = {"category": "polo", "color": "navy", "pattern": "solid", "formality": "casual", "season": "warm",
            "silhouette": json.dumps({"sleeve": "short", "neck": "collar"})}
    base.update(kw)
    return base


def test_which_fields_count_as_doubtful():
    ai = {f: "ai" for f in review.REVIEWED}
    just_below = {f: round(t - 0.01, 2) for f, t in review.UNSURE_BELOW.items()}
    found = review.doubtful(row(source=json.dumps(ai), confidence=json.dumps(just_below)))
    assert [f["field"] for f in found] == list(review.REVIEWED)
    # at the threshold the tagger is sure enough
    assert review.doubtful(row(source=json.dumps(ai), confidence=json.dumps(review.UNSURE_BELOW))) == []
    # the owner's own fields, fields nobody filled, and empty fields are never doubtful
    assert review.doubtful(row(source=json.dumps({**ai, "color": "user"}), confidence=json.dumps(just_below)))[1]["field"] == "pattern"
    assert review.doubtful(row(source="{}", confidence=json.dumps(just_below))) == []
    assert review.doubtful(row(color=None, source=json.dumps({"color": "ai"}), confidence=json.dumps({"color": 0.1}))) == []
    # the demo closet's answers made in advance count as the tagger's
    assert [f["field"] for f in review.doubtful(row(source=json.dumps({"color": "demo"}), confidence=json.dumps({"color": 0.5})))] == ["color"]
    # each field comes with the tagger's value, how sure it was and the allowed values
    sil = review.doubtful(row(source=json.dumps({"silhouette": "ai", "category": "ai"}),
                              confidence=json.dumps({"silhouette": 0.4, "category": 0.5})))
    assert sil[0] == {"field": "category", "value": "polo", "confidence": 0.5, "allowed": vocab.CATEGORY}
    assert sil[1] == {"field": "silhouette", "value": {"sleeve": "short", "neck": "collar"}, "confidence": 0.4,
                      "allowed": {"sleeve": vocab.SILHOUETTE["sleeve"], "neck": vocab.SILHOUETTE["neck"]}}


def test_a_described_item_shows_only_its_doubtful_fields(client, services, claude):
    item = tagged(client, services, claude, "a")
    body = queue(client)
    assert body["count"] == 1 and body["waiting"] == 0 and body["failed"] == 0
    shown = body["items"][0]
    assert shown["id"] == item and shown["name"] == "Navy polo"
    assert shown["fields"] == [{"field": "formality", "value": "smart_casual", "confidence": 0.7, "allowed": vocab.FORMALITY}]
    assert shown["picture_kind"] == "cutout" and shown["picture_url"].endswith(".cut.webp")
    assert client.get(shown["picture_url"]).status_code == 200


def test_most_doubtful_first(client, services, claude):
    sure = dict(formality=0.9)
    middling = tagged(client, services, claude, "m", color=0.6, **sure)
    least = tagged(client, services, claude, "l", category=0.3, **sure)
    two = tagged(client, services, claude, "t", color=0.6, season=0.7, **sure)
    nothing = tagged(client, services, claude, "n", **sure)
    body = queue(client)
    assert [i["id"] for i in body["items"]] == [least, two, middling]   # a tie goes to the item with more to look at
    assert nothing not in [i["id"] for i in body["items"]] and body["count"] == 3
    assert fields(body, two) == ["color", "season"]


def test_confirming_makes_the_field_the_owners_and_removes_it(client, services, claude):
    item = tagged(client, services, claude, "a", color=0.5)
    before = client.get(f"/api/items/{item}").json()
    r = client.post(f"/api/items/{item}/confirm", json={"fields": ["formality"]})
    assert r.status_code == 200
    after = r.json()
    assert after["formality"] == before["formality"] == "smart_casual"
    assert after["source"]["formality"] == "user" and after["source"]["color"] == "ai"
    assert fields(queue(client), item) == ["color"]
    client.post(f"/api/items/{item}/confirm", json={"fields": ["color"]})
    assert queue(client)["count"] == 0


def test_changing_a_field_removes_it_too(client, services, claude):
    item = tagged(client, services, claude, "a", color=0.5)
    assert client.patch(f"/api/items/{item}", json={"color": "black"}).status_code == 200
    assert fields(queue(client), item) == ["formality"]


def test_a_confirmed_field_stays_out_after_describing_again(client, services, claude):
    item = tagged(client, services, claude, "a", season=0.5)
    client.post(f"/api/items/{item}/confirm", json={"fields": ["formality"]})
    client.patch(f"/api/items/{item}", json={"season": "all"})
    assert queue(client)["count"] == 0
    # described again, as unsure as before
    assert client.post(f"/api/items/{item}/retag").status_code == 202
    assert queue(client)["waiting"] == 1 and queue(client)["count"] == 0   # not queued while waiting
    claude.mode = "answers"
    assert services.tag_worker.drain() == 1
    body = client.get(f"/api/items/{item}").json()
    assert body["season"] == "all" and body["source"]["formality"] == "user"
    assert queue(client)["count"] == 0


def test_skipped_items_stay_in_and_looking_changes_nothing(client, services, claude):
    item = tagged(client, services, claude, "a")
    before = client.get(f"/api/items/{item}").json()
    queue(client)
    queue(client)
    assert client.get(f"/api/items/{item}").json() == before
    assert [i["id"] for i in queue(client)["items"]] == [item]


def test_waiting_and_failed_items_are_counted_not_queued(client, services, claude):
    ok = tagged(client, services, claude, "ok")
    claude.mode = "fails"
    failed = upload(client, key="failed").json()["id"]
    cut(services)
    services.tag_worker.tagger = claude
    services.tag_worker.drain()
    claude.mode = "unavailable"
    waiting = upload(client, key="waiting").json()["id"]
    cut(services)                                           # described as soon as Claude can be reached
    cutting = upload(client, key="cutting").json()["id"]   # described once its cutout is made
    body = queue(client)
    assert [i["id"] for i in body["items"]] == [ok]
    assert body["waiting"] == 2 and {i["id"] for i in body["waiting_items"]} == {waiting, cutting}
    assert body["failed"] == 1 and [i["id"] for i in body["failed_items"]] == [failed]


def test_archived_items_are_not_reviewed(client, services, claude):
    item = tagged(client, services, claude, "a")
    client.patch(f"/api/items/{item}", json={"status": "archived"})
    assert queue(client)["count"] == 0


def test_confirm_refuses_what_it_cannot_confirm(client, services, claude):
    item = tagged(client, services, claude, "a")
    r = client.post(f"/api/items/{item}/confirm", json={"fields": ["brand"]})
    assert r.status_code == 422 and "brand" in r.json()["detail"]
    client.patch(f"/api/items/{item}", json={"pattern": None})
    r = client.post(f"/api/items/{item}/confirm", json={"fields": ["pattern"]})
    assert r.status_code == 422 and "no pattern" in r.json()["detail"]
    assert client.post("/api/items/nope/confirm", json={"fields": ["color"]}).status_code == 404
    assert client.post(f"/api/items/{item}/confirm", json={"color": "navy"}).status_code == 422


def test_the_demo_and_main_closets_have_their_own_queues(client, services, claude):
    item = tagged(client, services, claude, "a")
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    body = queue(client)
    assert [i["name"] for i in body["items"]] == DEMO_ORDER and body["count"] == 5
    assert body["waiting"] == 0 and body["failed"] == 0
    assert [(f["field"], f["value"], f["confidence"]) for f in body["items"][2]["fields"]] == \
        [("category", "sneakers", 0.6), ("formality", "casual", 0.6)]
    sneakers = body["items"][2]["id"]
    assert client.post(f"/api/items/{sneakers}/confirm", json={"fields": ["category", "formality"]}).status_code == 200
    assert queue(client)["count"] == 4
    # a demo upload is never described, so it is not waiting to be
    upload(client, key="demo-1")
    assert queue(client)["waiting"] == 0
    assert client.post("/api/profile", json={"profile": "main"}).status_code == 200
    assert [i["id"] for i in queue(client)["items"]] == [item]
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    assert queue(client)["count"] == 4   # the confirmed demo item stays confirmed


def test_an_older_demo_closet_gets_the_confidences(cfg):
    demo.ensure(cfg)
    conn = db.connect(cfg.db_path("demo"))
    try:
        for r in conn.execute("SELECT id, source FROM items").fetchall():
            conn.execute("UPDATE items SET confidence = ? WHERE id = ?",
                         (json.dumps({f: 1.0 for f in json.loads(r["source"])}), r["id"]))
        assert review.queue(conn, describes=False)["count"] == 0
        assert demo.ensure(cfg) == 0
        assert [i["name"] for i in review.queue(conn, describes=False)["items"]] == DEMO_ORDER
    finally:
        conn.close()



# ------------------------------------------------------------ every new item, once (22 November)

def test_a_new_item_is_offered_once_even_when_claude_was_sure(client, services, claude):
    old = tagged(client, services, claude, "old", formality=0.9)
    new = tagged(client, services, claude, "new", new=True, garment="polo", formality=0.9)
    body = queue(client)
    assert [i["id"] for i in body["items"]] == [new] and body["count"] == 1
    shown = body["items"][0]
    assert shown["new"] is True and shown["fields"] == []
    # what the quick pass shows beside the picture: what Claude thinks it is, the name, brand and price
    assert shown["kind"] == "polo" and shown["kind_by"] == "claude" and shown["name"] == "Navy polo"
    assert shown["brand"] is None and shown["price_cents"] is None
    assert old not in [i["id"] for i in body["items"]]


def test_new_items_come_before_older_ones_with_doubts(client, services, claude):
    unsure = tagged(client, services, claude, "unsure", color=0.5)
    sure = tagged(client, services, claude, "sure", new=True, formality=0.9)
    doubtful = tagged(client, services, claude, "doubtful", new=True, color=0.6)
    assert [i["id"] for i in queue(client)["items"]] == [doubtful, sure, unsure]


def test_an_item_still_being_cut_out_is_not_offered_yet(client, services, claude):
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    item = upload(client, key="demo-new").json()["id"]   # the demo closet never describes it, so it is not waiting
    assert item not in [i["id"] for i in queue(client)["items"]]
    cut(services)
    found = next(i for i in queue(client)["items"] if i["id"] == item)
    assert found["new"] is True and found["fields"] == []


def test_checking_saves_the_essentials_confirms_the_kind_and_takes_it_out(client, services, claude):
    item = tagged(client, services, claude, "a", new=True, garment="polo", color=0.5)
    r = client.post(f"/api/items/{item}/check", json={
        "kind": "polo", "changes": {"name": "Weekend polo", "brand": "Made-up Mills", "price_cents": 4250, "color": "black"},
        "fields": ["formality"]})
    assert r.status_code == 200
    got = r.json()
    assert (got["name"], got["brand"], got["price_cents"], got["color"]) == ("Weekend polo", "Made-up Mills", 4250, "black")
    assert got["kind"] == "polo" and got["kind_by"] == "owner" and got["checked_at"]
    assert got["source"]["name"] == "user" and got["source"]["color"] == "user" and got["source"]["formality"] == "user"
    assert queue(client)["count"] == 0
    # the owner's word wins: described again, Claude's name and kind do not come back
    assert client.post(f"/api/items/{item}/retag").status_code == 202
    claude.mode = "answers"
    services.tag_worker.drain()
    again = client.get(f"/api/items/{item}").json()
    assert again["name"] == "Weekend polo" and again["kind_by"] == "owner" and again["brand"] == "Made-up Mills"
    assert queue(client)["count"] == 0
    # one change in the history, which can be undone
    history = client.get(f"/api/items/{item}/history").json()
    assert [e["by"] for e in history][:2] == ["claude", "owner"]   # described again after the owner's check


def test_choosing_another_kind_while_checking(client, services, claude):
    item = tagged(client, services, claude, "a", new=True, formality=0.9)
    got = client.post(f"/api/items/{item}/check", json={"kind": "henley"}).json()
    assert got["kind"] == "henley" and got["kind_by"] == "owner" and got["category"] == "tee"
    assert queue(client)["count"] == 0


def test_checking_with_no_kind_confirms_claudes_category(client, services, claude):
    item = tagged(client, services, claude, "a", new=True, formality=0.9)
    with closing(db.connect(services.cfg.db_path("main"))) as conn:   # an answer with no kind in it
        conn.execute("UPDATE items SET tag_answer = NULL WHERE id = ?", (item,))
    got = client.post(f"/api/items/{item}/check", json={}).json()
    assert got["source"]["category"] == "user" and got["checked_at"]


def test_a_doubtful_field_left_keeps_a_checked_item_in(client, services, claude):
    item = tagged(client, services, claude, "a", new=True, color=0.5)
    client.post(f"/api/items/{item}/check", json={"kind": "polo", "fields": ["formality"]})
    assert fields(queue(client), item) == ["color"]


def test_checking_is_all_or_nothing(client, services, claude):
    item = tagged(client, services, claude, "a", new=True, garment="polo")
    r = client.post(f"/api/items/{item}/check", json={"kind": "polo", "changes": {"name": "Kept?", "price_cents": -1}})
    assert r.status_code == 422
    got = client.get(f"/api/items/{item}").json()
    assert got["name"] == "Navy polo" and got["kind_by"] == "claude" and got["checked_at"] is None
    assert client.post(f"/api/items/{item}/check", json={"kind": "no such kind"}).status_code == 422
    assert client.post(f"/api/items/{item}/check", json={"changes": {"status": "archived"}}).status_code == 422
    assert client.post(f"/api/items/{item}/check", json={"fields": ["brand"]}).status_code == 422
    assert client.post(f"/api/items/{item}/check", json={"other": 1}).status_code == 422
    assert client.post("/api/items/nope/check", json={}).status_code == 404
    assert [i["id"] for i in queue(client)["items"]] == [item]


@pytest.mark.parametrize("change", [{"name": "My polo"}, {"brand": "Made-up Mills"}, {"price_cents": 3000}])
def test_changing_an_essential_on_the_item_page_counts_as_checked(client, services, claude, change):
    item = tagged(client, services, claude, "a", new=True, formality=0.9)
    assert client.patch(f"/api/items/{item}", json=change).json()["checked_at"]
    assert queue(client)["count"] == 0


def test_saying_the_kind_on_the_item_page_counts_as_checked(client, services, claude):
    item = tagged(client, services, claude, "a", new=True, formality=0.9)
    client.patch(f"/api/items/{item}", json={"rating": "like"})   # not one of the essentials
    assert queue(client)["count"] == 1
    assert client.put(f"/api/items/{item}/kind", json={"kind": "polo"}).json()["checked_at"]
    assert queue(client)["count"] == 0


def test_items_kept_before_count_as_checked(cfg):
    # migration 0039 marks every item already in a closet as checked; the demo closet's pieces are made checked
    demo.ensure(cfg)
    with closing(db.connect(cfg.db_path("demo"))) as conn:
        assert conn.execute("SELECT count(*) FROM items WHERE checked_at IS NULL").fetchone()[0] == 0


def test_the_migration_counts_every_item_kept_before_as_checked(cfg):
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    path = cfg.db_path("main")
    with closing(db.connect(path)) as conn:   # a closet made by the previous version, with one item in it
        for version, file in db.migration_files():
            if version < 39:
                conn.executescript(f"BEGIN;\n{file.read_text(encoding='utf-8')}\nPRAGMA user_version = {version};\nCOMMIT;")
        conn.execute("INSERT INTO items (id, name, created_at, updated_at) VALUES ('kept', 'Kept', '2026-01-01', '2026-02-01')")
    db.migrate(path, cfg.local_backups_dir)
    with closing(db.connect(path)) as conn:
        assert conn.execute("SELECT checked_at FROM items WHERE id = 'kept'").fetchone()[0] == "2026-02-01"
