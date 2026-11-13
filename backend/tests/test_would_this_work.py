"""Would this work? The two routes, the checks held in memory, and a photo described and then let go.

Claude is never reached: `FakeClaude` (conftest) stands in for both routes, and for the spending record the API is
`FakeApi` behind the real routes and monthly limit, as in test_spend.py.
"""
import gc
import re
import threading
import time
import weakref

import pytest
from fastapi.testclient import TestClient

from closet import app as app_module
from closet import db, images, spend, wouldjobs
from closet.tagger import routes as tagger_routes
from closet.tagger.tagging import RouteUnavailable

from .conftest import PASSPHRASE, FakeApi, fake_cutter, photo_bytes

COAT = {"category": "coat", "color": "tan", "formality": "smart_casual", "rain_proof": True}


def wait(client, check_id, seconds=60):
    end = time.monotonic() + seconds
    while True:
        r = client.get(f"/api/would-this-work/{check_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        if body["state"] in ("ready", "failed") or time.monotonic() > end:
            return body
        time.sleep(0.05)


def send_photo(client, data=None):
    return client.post("/api/would-this-work", files={"photo": ("p.jpg", data or photo_bytes(), "image/jpeg")})


def files(cfg):
    """Files in the data folder other than the databases: a photo written to disk would be one."""
    return {p for p in cfg.data_dir.rglob("*") if p.is_file() and not re.search(r"\.db(-wal|-shm|-journal)?$", p.name)}


@pytest.fixture
def disk(cfg):
    """What the data folder holds when a test starts; `written()` lists what was added since."""
    seen = files(cfg)

    def written():
        return sorted(files(cfg) - seen)
    return written


@pytest.fixture
def photos(monkeypatch):
    """Weak references to every photo a check decodes: dead once nothing holds the photo any more."""
    refs = []
    decode = images.decode

    def watched(data):
        img = decode(data)
        refs.append(weakref.ref(img))
        return img
    monkeypatch.setattr(images, "decode", watched)
    return refs


def let_go(refs):
    gc.collect()
    return refs and all(r() is None for r in refs)


def test_would_this_work_needs_login(anon):
    assert anon.post("/api/would-this-work", json={"piece": COAT}).status_code == 401
    assert anon.get("/api/would-this-work/abc").status_code == 401


def test_by_hand_in_the_demo_closet_starts_then_answers(client):
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    r = client.post("/api/would-this-work", json={"piece": COAT})
    assert r.status_code == 202, r.text
    started = r.json()
    assert started["state"] in ("checking", "ready") and started["way"] == "by_hand"
    assert started["piece"]["category"] == "coat" and started["piece_words"].startswith("Tan coat, smart casual")
    body = wait(client, started["id"])
    assert body["state"] == "ready" and body["message"] is None and body["finished_at"]
    answer = body["answer"]
    assert answer["verdict"] == "fills_gap" and answer["fills"][0]["gap_id"] == "outer-rain"
    demo_ids = {i["id"] for i in client.get("/api/items").json()["items"]}
    assert answer["goes_with"]["items"] and set(answer["goes_with"]["items"]) <= demo_ids


def test_nothing_is_added_to_the_closet(client):
    before = client.get("/api/items").json()["items"]
    body = wait(client, client.post("/api/would-this-work", json={"piece": COAT}).json()["id"])
    assert body["state"] == "ready" and body["answer"]["verdict"] == "too_small"
    assert client.get("/api/items").json()["items"] == before


def test_unknown_check_is_explained(client):
    r = client.get("/api/would-this-work/not-a-check")
    assert r.status_code == 404 and "forgotten when Closet is closed" in r.json()["detail"]


def test_wrong_input_is_refused_in_the_owners_words(client):
    for body, words in [({"piece": {"color": "navy"}}, "what kind of piece"),
                        ({"piece": {"category": "cape", "color": "navy"}}, "not a kind of piece"),
                        ({"piece": {"category": "coat"}}, "main colour"),
                        ({"category": "coat", "color": "navy"}, "Describe the piece by hand"),
                        ([], "Describe the piece by hand")]:
        r = client.post("/api/would-this-work", json=body)
        assert r.status_code == 422 and words in r.json()["detail"], r.text
    r = client.post("/api/would-this-work", content=b"not json", headers={"content-type": "application/json"})
    assert r.status_code == 422
    r = client.post("/api/would-this-work", data={"note": "x"}, files={"other": ("a.txt", b"x", "text/plain")})
    assert r.status_code == 422 and "Choose a photo" in r.json()["detail"]


def test_only_the_newest_finished_checks_are_kept(client):
    first = client.post("/api/would-this-work", json={"piece": COAT}).json()["id"]
    assert wait(client, first)["state"] == "ready"
    later = []
    for _ in range(wouldjobs.MAX_CHECKS):
        later.append(client.post("/api/would-this-work", json={"piece": COAT}).json()["id"])
        assert wait(client, later[-1])["state"] == "ready"
    assert client.get(f"/api/would-this-work/{first}").status_code == 404
    for check_id in later:
        assert client.get(f"/api/would-this-work/{check_id}").status_code == 200


class Profile:
    def get(self, key):
        return "main"


def blocked_checks(cfg, gate, tagger=None, routes=("plan",)):
    def closet(profile):
        gate.wait(10)
        return [], [], {"gaps": []}
    return wouldjobs.Checks(cfg, Profile(), closet, lambda: routes, tagger or (lambda imgs, r: None),
                            fake_cutter, lambda: False)


def test_a_running_check_is_never_dropped_and_too_many_are_refused(cfg):
    gate = threading.Event()
    checks = blocked_checks(cfg, gate)
    running = [checks.start_by_hand(COAT)["id"] for _ in range(wouldjobs.MAX_CHECKS)]
    with pytest.raises(wouldjobs.Refused, match="already checking"):
        checks.start_by_hand(COAT)
    assert all(checks.get(i) is not None for i in running)
    gate.set()
    end = time.monotonic() + 30
    while any(checks.get(i)["finished_at"] is None for i in running) and time.monotonic() < end:
        time.sleep(0.02)
    newest = checks.start_by_hand(COAT)["id"]   # now the oldest finished one makes room
    assert checks.get(running[0]) is None and checks.get(newest) is not None


def test_too_many_running_is_refused_in_the_owners_words(client, monkeypatch):
    monkeypatch.setattr(wouldjobs.Checks, "_new", lambda self, *a: (_ for _ in ()).throw(
        wouldjobs.Refused(wouldjobs.BUSY)))
    r = client.post("/api/would-this-work", json={"piece": COAT})
    assert r.status_code == 409 and "Wait for one of them to finish" in r.json()["detail"]


def test_a_photo_is_described_then_let_go(client, claude, cfg, photos, disk):
    claude.mode = "answers"
    r = send_photo(client)
    assert r.status_code == 202, r.text
    assert r.json()["way"] == "photo" and r.json()["state"] in ("describing", "checking", "ready")
    body = wait(client, r.json()["id"])
    assert body["state"] == "ready", body
    assert body["piece"]["category"] == "polo" and body["piece"]["color"] == "navy"
    assert body["piece"]["weight_class"] == "midweight" and body["piece"]["name"] == "Navy polo"
    assert claude.calls == [("plan",)]
    assert disk() == [] and let_go(photos)
    assert client.get("/api/items").json()["items"] == []


def test_a_photo_is_let_go_when_describing_fails(client, claude, cfg, photos, disk):
    claude.mode = "fails"
    body = wait(client, send_photo(client).json()["id"])
    assert body["state"] == "failed" and body["by_hand"] is True and "describe it by hand" in body["message"]
    assert body["answer"] is None
    assert disk() == [] and let_go(photos)


def test_an_unexpected_fault_in_the_check_fails_it_and_lets_the_photo_go(cfg, photos, disk):
    def broken(imgs, routes):
        raise RuntimeError("something nobody expected")
    checks = blocked_checks(cfg, threading.Event(), tagger=broken)
    check_id = checks.start_photo(photo_bytes())["id"]
    end = time.monotonic() + 30
    while checks.get(check_id)["state"] not in ("ready", "failed") and time.monotonic() < end:
        time.sleep(0.02)
    body = checks.get(check_id)
    assert body["state"] == "failed" and body["message"] == wouldjobs.FAILED and body["finished_at"]
    assert disk() == [] and let_go(photos)


def test_a_photo_over_the_size_limit_is_refused(client, claude, cfg, monkeypatch, disk):
    claude.mode = "answers"
    monkeypatch.setattr(images, "MAX_UPLOAD_BYTES", 1000)
    r = send_photo(client)
    assert r.status_code == 400 and "larger than" in r.json()["detail"]
    assert claude.calls == [] and disk() == []


def test_no_route_says_so_at_once_and_offers_by_hand(client, claude, cfg, disk):
    claude.mode = "unavailable"
    r = send_photo(client)
    assert r.status_code == 409 and r.json()["detail"].endswith(wouldjobs.BY_HAND)
    assert claude.calls == [] and disk() == []


def test_the_demo_closet_sends_nothing(client, claude, cfg):
    claude.mode = "answers"
    client.post("/api/profile", json={"profile": "demo"})
    seen = files(cfg)
    r = send_photo(client)
    assert r.status_code == 409 and "demo closet" in r.json()["detail"] and wouldjobs.BY_HAND in r.json()["detail"]
    assert claude.calls == [] and files(cfg) == seen


def test_a_photo_that_is_not_one_is_refused(client, claude):
    claude.mode = "answers"
    r = send_photo(client, b"not a photo")
    assert r.status_code == 400 and "not a photo" in r.json()["detail"]
    assert claude.calls == []


# ------------------------------------------------------------- the real routes and the spending record
@pytest.fixture
def api(monkeypatch):
    """Only the API key looks usable; the plan route would refuse."""
    monkeypatch.setattr(tagger_routes, "status", lambda order="auto", claude_exe=None: {
        "order": ["plan", "api"], "routes": [{"id": "plan", "available": False, "detail": ""},
                                             {"id": "api", "available": True, "detail": ""}]})

    def plan(model, images, exe=None):
        raise RouteUnavailable("not signed in")
    monkeypatch.setattr(tagger_routes.claude_cli, "tag_item_cli", plan)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-test-only-not-a-real-key")
    return FakeApi()


@pytest.fixture
def metered(cfg, api):
    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, api_client=api)
    sv.worker.is_ready = lambda: True
    c = TestClient(app_module.create_app(sv))
    assert c.post("/api/setup", json={"passphrase": PASSPHRASE}).status_code == 204
    yield c
    sv.stop()


def calls(cfg):
    conn = db.connect(cfg.db_path("main"))
    try:
        return [dict(r) for r in conn.execute("SELECT purpose, route FROM claude_calls ORDER BY id")]
    finally:
        conn.close()


def test_the_call_is_recorded_with_its_own_purpose(metered, api, cfg, disk):
    assert metered.put("/api/settings", json={"tagging_api_enabled": True, "tagging_api_cap_usd": 5}).status_code == 200
    body = wait(metered, send_photo(metered).json()["id"])
    assert body["state"] == "ready", body
    assert api.calls == 1 and calls(cfg) == [{"purpose": wouldjobs.PURPOSE, "route": "api"}]
    assert disk() == []


def test_the_monthly_limit_stops_the_call_and_says_describe_it_by_hand(metered, api, cfg, disk):
    assert metered.put("/api/settings", json={"tagging_api_enabled": True, "tagging_api_cap_usd": 0.01}).status_code == 200
    conn = db.connect(cfg.db_path("main"))
    conn.execute("INSERT INTO claude_calls (at, month, purpose, route, model, cost_usd) VALUES (?, ?, 'tag_item', 'api', "
                 "'claude-haiku-5-5', 0.01)", (db.now(), spend.this_month()))
    conn.close()
    body = wait(metered, send_photo(metered).json()["id"])
    assert body["state"] == "failed" and body["by_hand"] is True
    assert body["message"] == f"{spend.LIMIT_REACHED} {wouldjobs.BY_HAND}"
    assert api.calls == 0 and disk() == []


def test_with_the_api_key_off_no_route_can_be_used(metered, api):
    r = send_photo(metered)
    assert r.status_code == 409 and api.calls == 0
