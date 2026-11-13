"""The review queue: only the fields the tagger was unsure of and the owner has not set.

Claude is never called: `FakeClaude` (conftest) stands in, and each test chooses how sure its answer is.
"""
import json

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


def tagged(client, services, claude, key, **sure):
    """An item described by Claude, with these confidences (field -> number) in its answer."""
    answer = ANSWER.model_copy(update={f"{f}_confidence": v for f, v in sure.items()})
    services.tag_worker.tagger = lambda images, routes: TagResult(answer, "claude-haiku-5-5", 0.1, 100, 50, 0.0, 1, route=routes[0])
    claude.mode = "answers"
    item = upload(client, key=key).json()
    cut(services)
    assert services.tag_worker.drain() == 1
    claude.mode = "unavailable"
    return item["id"]


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


@pytest.mark.parametrize("method, path", [("get", "/api/review"), ("post", "/api/items/x/confirm")])
def test_reviewing_needs_login(anon, method, path):
    r = getattr(anon, method)(path, **({"json": {"fields": ["color"]}} if method == "post" else {}))
    assert r.status_code == 401
