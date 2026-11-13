"""Tagging each item after its cutout: the queue, the stored answer, the owner's own fields, the demo closet.

Claude is never called: `FakeClaude` (conftest) stands in for both routes.
"""
import hashlib
import json
import logging
import sqlite3

import pytest

from closet import db, demo, jobs, tagjobs
from closet.config import bundle_dir
from closet.tagger import routes as tagger_routes
from closet.tagger.schema import SCHEMA_VERSION, ItemTags
from closet.tagger.tagging import RouteUnavailable

from .conftest import ANSWER, upload


def cut(services):
    services.worker.is_ready = lambda: True
    return services.worker.drain()


def tag(services):
    return services.tag_worker.drain()


def row(cfg, item_id, profile="main"):
    conn = db.connect(cfg.db_path(profile))
    try:
        return dict(conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone())
    finally:
        conn.close()


def tag_jobs(cfg, item_id):
    conn = db.connect(cfg.db_path("main"))
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM jobs WHERE kind = 'tag' AND item_id = ? ORDER BY id", (item_id,))]
    finally:
        conn.close()


def test_tagging_is_queued_once_the_cutout_is_ready(client, services, cfg):
    item = upload(client).json()
    assert item["tag_state"] == "none" and tag_jobs(cfg, item["id"]) == []
    assert cut(services) == 1
    body = client.get(f"/api/items/{item['id']}").json()
    assert body["tag_state"] == "waiting"
    assert [j["state"] for j in tag_jobs(cfg, item["id"])] == ["queued"]
    listed = client.get("/api/items").json()["items"][0]
    assert listed["tag_state"] == "waiting"
    settings = client.get("/api/settings").json()
    assert settings["pending_tags"] == 1 and settings["pending_cutouts"] == 0


def test_a_failed_cutout_queues_no_tagging(client, services, cfg):
    services.worker.cutter = lambda img: (_ for _ in ()).throw(RuntimeError("no"))
    item = upload(client).json()
    assert cut(services) == jobs.MAX_ATTEMPTS
    assert tag_jobs(cfg, item["id"]) == [] and row(cfg, item["id"])["tag_state"] == "none"


def test_with_no_route_the_job_waits_and_runs_when_one_appears(client, services, claude, cfg):
    item = upload(client).json()
    cut(services)
    assert tag(services) == 0 and claude.calls == []   # nothing to try: it waits, it does not fail
    assert row(cfg, item["id"])["tag_state"] == "waiting"
    assert tag_jobs(cfg, item["id"])[0]["attempts"] == 0
    claude.mode = "answers"
    assert tag(services) == 1 and claude.calls == [("plan",)]
    body = client.get(f"/api/items/{item['id']}").json()
    assert body["tag_state"] == "done" and body["tag_error"] is None


def test_a_route_that_turns_out_unusable_puts_the_job_back_without_using_an_attempt(client, services, claude, cfg):
    item = upload(client).json()
    cut(services)
    services.tag_worker.routes = lambda: ("plan",)   # looks usable, but the call finds the plan's limit reached
    assert tag(services) == 0 and len(claude.calls) == 1
    assert row(cfg, item["id"])["tag_state"] == "waiting"
    assert tag_jobs(cfg, item["id"])[0]["attempts"] == 0 and tag_jobs(cfg, item["id"])[0]["state"] == "queued"


def test_the_answer_fills_the_fields_and_the_whole_answer_is_stored(client, services, claude, cfg):
    claude.mode = "answers"
    item = upload(client).json()
    cut(services)
    assert tag(services) == 1
    body = client.get(f"/api/items/{item['id']}").json()
    assert (body["name"], body["category"], body["color"], body["pattern"], body["formality"], body["season"]) == \
        ("Navy polo", "polo", "navy", "solid", "smart_casual", "warm")
    assert body["color_hex"].startswith("#") and body["material"] == "100% cotton"
    assert body["silhouette"] == {"sleeve": "short", "neck": "collar", "fit": "regular"}
    assert body["source"]["category"] == "ai" and body["source"]["name"] == "ai"
    assert body["confidence"]["category"] == 0.95 and body["confidence"]["details"] == 0.8
    assert body["details"]["placket_buttons"] == 3 and body["details"]["collar"] == "flat_knit"
    assert "other_features" not in body["details"]
    assert body["seen_not_drawn"] == ["embroidered chest logo"]
    assert body["tag_route"] == "plan" and body["tag_model"] == "claude-haiku-5-5" and body["tagged_at"]
    assert body["tag_schema_version"] == SCHEMA_VERSION
    stored = row(cfg, item["id"])
    assert json.loads(stored["tag_answer"]) == ANSWER.model_dump(mode="json")
    assert ItemTags.model_validate_json(stored["tag_answer"]) == ANSWER
    assert client.get("/api/settings").json()["pending_tags"] == 0
    grid = client.get("/api/items").json()["items"][0]
    assert grid["name"] == "Navy polo" and grid["category"] == "polo" and grid["tag_state"] == "done"


def test_fields_the_owner_set_are_never_overwritten(client, services, claude, cfg):
    claude.mode = "answers"
    item = upload(client, name="Weekend polo").json()   # a name given at upload is the owner's
    client.patch(f"/api/items/{item['id']}", json={"category": "shirt", "material": "linen", "silhouette": {"sleeve": "long"}})
    cut(services)
    assert tag(services) == 1
    body = client.get(f"/api/items/{item['id']}").json()
    assert body["name"] == "Weekend polo" and body["category"] == "shirt" and body["material"] == "linen"
    assert body["silhouette"] == {"sleeve": "long"}
    assert body["source"]["category"] == "user" and body["source"]["material"] == "user" and body["confidence"]["category"] == 1.0
    assert body["color"] == "navy" and body["source"]["color"] == "ai"   # what the owner left alone is filled in
    assert json.loads(row(cfg, item["id"])["tag_answer"])["category"] == "polo"   # the whole answer is kept anyway

    # changed after tagging, then described again: the owner's change stays, the rest follows the new answer
    client.patch(f"/api/items/{item['id']}", json={"color": "green", "color_hex": "#3f7d4f"})
    assert client.post(f"/api/items/{item['id']}/retag").status_code == 202
    assert tag(services) == 1
    body = client.get(f"/api/items/{item['id']}").json()
    assert body["color"] == "green" and body["color_hex"] == "#3f7d4f" and body["source"]["color_hex"] == "user"
    assert body["tag_state"] == "done"


def test_three_failed_attempts_end_in_failed_with_a_plain_reason_then_retag_works(client, services, claude, cfg, caplog):
    claude.mode = "fails"
    item = upload(client).json()
    cut(services)
    with caplog.at_level(logging.DEBUG):
        assert tag(services) == tagjobs.MAX_ATTEMPTS == 3
    body = client.get(f"/api/items/{item['id']}").json()
    assert body["tag_state"] == "failed" and "try again" in body["tag_error"].lower()
    assert body["category"] is None and row(cfg, item["id"])["tag_answer"] is None
    assert "outside the schema" not in caplog.text   # only the kind of failure is logged, never what Claude said
    assert tag_jobs(cfg, item["id"])[0]["state"] == "failed"

    claude.mode = "answers"
    again = client.post(f"/api/items/{item['id']}/retag")
    assert again.status_code == 202 and again.json()["tag_state"] == "waiting" and again.json()["tag_error"] is None
    assert tag(services) == 1
    assert client.get(f"/api/items/{item['id']}").json()["tag_state"] == "done"


def test_retag_queues_once_and_explains_when_it_cannot(client, services, claude, cfg):
    item = upload(client).json()
    # the cutout is still to come: tagging follows it, nothing extra is queued
    assert client.post(f"/api/items/{item['id']}/retag").json()["tag_state"] == "none"
    cut(services)
    client.post(f"/api/items/{item['id']}/retag")
    client.post(f"/api/items/{item['id']}/retag")
    assert len(tag_jobs(cfg, item["id"])) == 1
    assert client.post("/api/items/nope/retag").status_code == 404

    services.worker.cutter = lambda img: (_ for _ in ()).throw(RuntimeError("no"))
    other = upload(client, key="k2").json()
    cut(services)
    r = client.post(f"/api/items/{other['id']}/retag")
    assert r.status_code == 409 and "background" in r.json()["detail"]


def test_an_interrupted_tagging_job_resumes_on_the_next_start(client, services, claude, cfg):
    item = upload(client).json()
    cut(services)
    conn = db.connect(cfg.db_path("main"))
    conn.execute("UPDATE jobs SET state = 'running' WHERE kind = 'tag'")
    conn.execute("UPDATE items SET tag_state = 'working'")
    assert jobs.requeue_interrupted(conn) == 1
    conn.close()
    assert row(cfg, item["id"])["tag_state"] == "waiting"
    claude.mode = "answers"
    assert tag(services) == 1 and row(cfg, item["id"])["tag_state"] == "done"


def test_the_demo_closet_is_never_sent_to_claude(client, services, claude, cfg):
    claude.mode = "answers"
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    items = client.get("/api/items").json()["items"]
    assert items and all(i["tag_state"] == "done" for i in items)
    polo = next(i for i in items if i["name"] == "Navy polo")
    body = client.get(f"/api/items/{polo['id']}").json()
    assert body["tag_route"] == "demo" and body["tag_model"] is None and body["tag_schema_version"] == SCHEMA_VERSION
    assert body["details"]["placket"] == "polo"
    tee = next(i for i in items if i["name"] == "Paper plane tee")
    assert client.get(f"/api/items/{tee['id']}").json()["seen_not_drawn"] == ["paper plane print on the chest"]

    # a photo added to the demo closet gets its cutout but is not queued for Claude, and cannot be sent by hand
    new = upload(client, key="demo-1").json()
    assert cut(services) == 1
    assert tag(services) == 0 and claude.calls == []
    assert row(cfg, new["id"], "demo")["tag_state"] == "none"
    r = client.post(f"/api/items/{new['id']}/retag")
    assert r.status_code == 409 and "demo" in r.json()["detail"]
    assert claude.calls == []


def test_a_demo_closet_made_before_answers_existed_gets_them(cfg):
    assert demo.ensure(cfg) > 0
    conn = db.connect(cfg.db_path("demo"))
    conn.execute("UPDATE items SET tag_state = 'none', tag_answer = NULL, tag_route = NULL, tag_schema_version = NULL")
    conn.close()
    assert demo.ensure(cfg) == 0
    conn = db.connect(cfg.db_path("demo"))
    states = {r[0] for r in conn.execute("SELECT tag_state FROM items")}
    conn.close()
    assert states == {"done"}


def test_every_demo_answer_is_a_valid_answer_in_the_current_schema():
    data = json.loads((bundle_dir() / "demo_data" / "items.json").read_text(encoding="utf-8"))
    # after a schema change, rewrite them with `python tools/make_demo.py --answers-only`
    assert data["schema_version"] == SCHEMA_VERSION
    for it in data["items"]:
        tags = ItemTags.model_validate(it["answer"])
        assert (tags.category, tags.color, tags.pattern, tags.formality, tags.season) == \
            (it["category"], it["color"], it["pattern"], it["formality"], it["season"])


# Recorded with SCHEMA_VERSION. When this fails, the tagging schema changed: raise SCHEMA_VERSION in
# closet/tagger/schema.py, record the new fingerprint here, and rewrite the demo answers.
SCHEMA_FINGERPRINTS = {1: "1edcb5f6851e"}


def test_the_schema_version_is_raised_when_the_schema_changes():
    schema = json.dumps(ItemTags.model_json_schema(), sort_keys=True)
    assert hashlib.sha256(schema.encode()).hexdigest()[:12] == SCHEMA_FINGERPRINTS[SCHEMA_VERSION]


# ---- which routes may be used

@pytest.fixture
def both_routes(monkeypatch):
    available = {"plan": True, "api": True}
    monkeypatch.setattr(tagger_routes, "status", lambda order="auto", claude_exe=None: {
        "order": ["plan", "api"], "routes": [{"id": r, "available": available[r], "detail": ""} for r in ("plan", "api")]})
    return available


def test_the_api_route_is_only_used_once_the_owner_turns_it_on(client, services, both_routes):
    state = services.state
    assert client.get("/api/settings").json()["tagging_api_enabled"] is False   # off by default
    assert tagjobs.usable_routes(state) == ("plan",)
    both_routes["plan"] = False
    assert tagjobs.usable_routes(state) == ()   # the key alone is not enough
    r = client.put("/api/settings", json={"tagging_api_enabled": True})
    assert r.status_code == 200 and r.json()["tagging_api_enabled"] is True
    assert tagjobs.usable_routes(state) == ("api",)
    both_routes["plan"] = True
    assert tagjobs.usable_routes(state) == ("plan", "api")   # in the order part 1 reports
    both_routes["api"] = False   # turned on but no key: still not used
    assert tagjobs.usable_routes(state) == ("plan",)
    assert client.put("/api/settings", json={"tagging_api_enabled": False}).json()["tagging_api_enabled"] is False


def test_the_real_tagger_never_reaches_the_api_when_only_the_plan_is_allowed(monkeypatch):
    used = []
    monkeypatch.setattr(tagger_routes.claude_cli, "tag_item_cli", lambda *a, **k: (_ for _ in ()).throw(RouteUnavailable("limit")))
    monkeypatch.setattr(tagger_routes, "tag_item", lambda *a, **k: used.append("api"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-only")
    with pytest.raises(RouteUnavailable):
        tagjobs.claude_tagger([], ("plan",))
    with pytest.raises(RouteUnavailable):
        tagjobs.claude_tagger([], ())
    assert used == []


def test_retag_needs_login(anon):
    assert anon.post("/api/items/x/retag").status_code == 401


# ---- the migration

def test_the_migration_runs_on_a_closet_made_by_the_previous_version(cfg):
    path = cfg.db_path("main")
    path.parent.mkdir(parents=True, exist_ok=True)
    old = sqlite3.connect(path)
    for version, file in db.migration_files():
        if version < 5:
            old.executescript(file.read_text(encoding="utf-8") + f"\nPRAGMA user_version = {version};")
    old.execute("INSERT INTO items (id, name, category, cutout_state, created_at, updated_at) "
                "VALUES ('a', 'Old shirt', 'shirt', 'ready', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
    old.commit()
    old.close()
    result = db.migrate(path, cfg.local_backups_dir)
    assert 5 in result["applied"] and result["backup"]
    conn = db.connect(path)
    r = dict(conn.execute("SELECT * FROM items WHERE id = 'a'").fetchone())
    conn.close()
    assert r["name"] == "Old shirt" and r["tag_state"] == "none" and r["tag_answer"] is None
