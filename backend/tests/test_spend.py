"""The API key's spend cap: every call recorded, a monthly limit, an estimate for waiting items.

Claude is never called: `FakeApi` (conftest) stands in for the API and reports token counts; the plan route is
replaced by a function that answers (or says the plan's limit is reached).
"""
import json
import logging
import sqlite3
import threading
from datetime import datetime, timedelta

import anthropic
import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from closet import app as app_module
from closet import backup, db, spend, tagjobs
from closet.tagger import routes as tagger_routes
from closet.tagger.tagging import CapReached, RouteUnavailable, TaggingError, TagResult, tag_item

from .conftest import ANSWER, PASSPHRASE, FakeApi, fake_cutter, upload

SECRET_KEY = "sk-ant-api03-test-only-not-a-real-key"
ONE_CALL = spend.cost_usd("claude-haiku-5-5", 2000, 400)   # what FakeApi reports for each request


@pytest.fixture
def routes(monkeypatch):
    """Which routes look usable, and a stand-in for the plan route that answers when the plan is usable."""
    usable = {"plan": False, "api": True}
    monkeypatch.setattr(tagger_routes, "status", lambda order="auto", claude_exe=None: {
        "order": ["plan", "api"], "routes": [{"id": r, "available": usable[r], "detail": ""} for r in ("plan", "api")]})

    def plan(model, images, exe=None):
        if not usable["plan"]:
            raise RouteUnavailable("the Claude plan's usage limit has been reached")
        return TagResult(ANSWER, model, 0.1, 9000, 900, 0.0017, 1, route="plan")
    monkeypatch.setattr(tagger_routes.claude_cli, "tag_item_cli", plan)
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET_KEY)
    return usable


@pytest.fixture
def fake_api():
    return FakeApi()


@pytest.fixture
def services(cfg, routes, fake_api):
    """The real tagger, routes and meter, with the API and the plan stood in for."""
    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, api_client=fake_api)
    sv.worker.is_ready = lambda: True
    yield sv
    sv.stop()


def add(client, services, key):
    item = upload(client, key=key).json()
    services.worker.drain()
    return item


def tag(services):
    return services.tag_worker.drain()


def calls(cfg, profile="main"):
    conn = db.connect(cfg.db_path(profile))
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM claude_calls ORDER BY id")]
    finally:
        conn.close()


def attempts(cfg, item_id):
    conn = db.connect(cfg.db_path("main"))
    try:
        return conn.execute("SELECT attempts, state FROM jobs WHERE kind = 'tag' AND item_id = ?", (item_id,)).fetchone()
    finally:
        conn.close()


def allow(client, cap=5.0):
    r = client.put("/api/settings", json={"tagging_api_enabled": True, "tagging_api_cap_usd": cap})
    assert r.status_code == 200, r.text
    return r.json()


def preload(cfg, usd, month=None):
    """Spend already made this month (or in `month`)."""
    conn = db.connect(cfg.db_path("main"))
    conn.execute("INSERT INTO claude_calls (at, month, purpose, route, model, cost_usd) VALUES (?, ?, 'tag_item', 'api', "
                 "'claude-haiku-5-5', ?)", (db.now(), month or spend.this_month(), usd))
    conn.close()


def test_spend_needs_login(anon):
    assert anon.get("/api/tagging/spend").status_code == 401
    assert anon.put("/api/settings", json={"tagging_api_cap_usd": 5}).status_code == 401


def test_the_api_key_cannot_be_allowed_without_a_monthly_limit(client, services):
    s = client.get("/api/settings").json()
    assert s["tagging_api_enabled"] is False and s["tagging_api_cap_usd"] is None   # off by default, as before
    r = client.put("/api/settings", json={"tagging_api_enabled": True})
    assert r.status_code == 422 and "monthly limit" in r.json()["detail"]
    for bad in (0, -1, 0.001, 5000):
        assert client.put("/api/settings", json={"tagging_api_cap_usd": bad}).status_code == 422
    assert services.state.get("tagging_api_enabled") is False and services.state.get("tagging_api_cap_usd") is None

    s = allow(client, 7.5)
    assert s["tagging_api_enabled"] is True and s["tagging_api_cap_usd"] == 7.5
    r = client.put("/api/settings", json={"tagging_api_cap_usd": None})   # the limit cannot go while the key is on
    assert r.status_code == 422 and "off" in r.json()["detail"]
    s = client.put("/api/settings", json={"tagging_api_cap_usd": 3}).json()   # changed while on: stays on
    assert s["tagging_api_enabled"] is True and s["tagging_api_cap_usd"] == 3
    s = client.put("/api/settings", json={"tagging_api_enabled": False, "tagging_api_cap_usd": None}).json()
    assert s["tagging_api_enabled"] is False and s["tagging_api_cap_usd"] is None


def test_a_key_allowed_before_limits_existed_is_not_used_until_a_limit_is_set(client, services, routes):
    services.state.update(tagging_api_enabled=True)   # as an earlier version left it
    assert tagjobs.usable_routes(services.state) == ()
    assert client.get("/api/settings").json()["tagging_api_enabled"] is False
    allow(client)
    assert tagjobs.usable_routes(services.state) == ("api",)


def test_every_api_call_is_recorded_and_summed_for_the_month(client, services, cfg, fake_api):
    allow(client)
    a = add(client, services, "a")
    add(client, services, "b")
    assert tag(services) == 2 and fake_api.calls == 2
    assert client.get(f"/api/items/{a['id']}").json()["tag_route"] == "api"
    rows = calls(cfg)
    assert [(r["route"], r["purpose"], r["model"], r["input_tokens"], r["output_tokens"]) for r in rows] == \
        [("api", "tag_item", "claude-haiku-5-5", 2000, 400)] * 2
    assert all(r["cost_usd"] == pytest.approx(ONE_CALL) and r["prices_checked"] == spend.PRICES_CHECKED for r in rows)
    assert all(r["month"] == datetime.now().astimezone().strftime("%Y-%m") for r in rows)
    body = client.get("/api/tagging/spend").json()
    assert body["allowed"] is True and body["cap_usd"] == 5.0 and body["api_calls"] == 2 and body["plan_calls"] == 0
    assert body["spent_usd"] == pytest.approx(2 * ONE_CALL) and body["left_usd"] == pytest.approx(5 - 2 * ONE_CALL)
    assert body["input_tokens"] == 4000 and body["output_tokens"] == 800 and body["reached"] is False
    assert body["prices_checked"] == spend.PRICES_CHECKED == "2026-11-03" and body["suggested_cap_usd"] == 5.0
    assert body["history"] == [{"month": body["month"], "api_calls": 2, "plan_calls": 0, "spent_usd": pytest.approx(2 * ONE_CALL),
                                "input_tokens": 4000, "output_tokens": 800}]


def test_plan_calls_are_counted_and_cost_nothing(client, services, cfg, routes, fake_api):
    routes["plan"] = True
    allow(client)
    add(client, services, "a")
    assert tag(services) == 1 and fake_api.calls == 0   # the plan first: the API is not asked
    assert [(r["route"], r["input_tokens"], r["output_tokens"], r["cost_usd"]) for r in calls(cfg)] == [("plan", 9000, 900, 0)]
    body = client.get("/api/tagging/spend").json()
    assert body["plan_calls"] == 1 and body["api_calls"] == 0 and body["spent_usd"] == 0


def test_a_request_that_could_pass_the_limit_is_not_made_and_the_item_waits(client, services, cfg, routes, fake_api):
    allow(client, 1.0)
    preload(cfg, 1.0 - spend.estimate_call(1) / 2)   # less than one request's worth left
    item = add(client, services, "a")
    other = add(client, services, "b")
    assert tag(services) == 0 and fake_api.calls == 0
    assert tuple(attempts(cfg, item["id"])) == (0, "queued")   # it waits; no attempt used
    for it in (item, other):
        body = client.get(f"/api/items/{it['id']}").json()
        assert body["tag_state"] == "waiting" and body["tag_error"] == spend.LIMIT_REACHED
    s = client.get("/api/tagging/spend").json()
    assert s["reached"] is True and s["left_usd"] < spend.estimate_call(1)
    assert services.state.get("tagging_api_enabled") is True   # the limit does not switch the key off

    # the plan is used whatever the limit
    routes["plan"] = True
    assert tag(services) == 2 and fake_api.calls == 0
    body = client.get(f"/api/items/{item['id']}").json()
    assert body["tag_state"] == "done" and body["tag_route"] == "plan" and body["tag_error"] is None


def test_raising_the_limit_lets_waiting_items_go(client, services, cfg, fake_api):
    allow(client, 1.0)
    preload(cfg, 0.999)
    item = add(client, services, "a")
    assert tag(services) == 0 and fake_api.calls == 0
    allow(client, 2.0)
    assert tag(services) == 1 and fake_api.calls == 1
    assert client.get(f"/api/items/{item['id']}").json()["tag_error"] is None


def test_turning_the_key_off_takes_back_the_limit_message(client, services, cfg):
    allow(client, 1.0)
    preload(cfg, 0.999)
    item = add(client, services, "a")
    tag(services)
    assert client.get(f"/api/items/{item['id']}").json()["tag_error"] == spend.LIMIT_REACHED
    client.put("/api/settings", json={"tagging_api_enabled": False})
    tag(services)   # nothing can be tried now, and the limit is not why
    body = client.get(f"/api/items/{item['id']}").json()
    assert body["tag_state"] == "waiting" and body["tag_error"] is None


def test_every_request_is_checked_and_counted_even_a_retry():
    class Incomplete(FakeApi):
        def parse(self, **kw):
            reply = super().parse(**kw)
            return reply if self.calls > 1 else type(reply)(parsed_output=None, stop_reason="max_tokens", usage=reply.usage)

    seen = []

    class Meter:
        def before_api_call(self, model, images):
            seen.append(("check", images))

        def record(self, route, model, input_tokens, output_tokens):
            seen.append((route, input_tokens, output_tokens))

    from PIL import Image
    r = tag_item(Incomplete(), "claude-haiku-5-5", [Image.new("RGBA", (40, 40))], meter=Meter())
    assert r.attempts == 2
    assert seen == [("check", 1), ("api", 2000, 400), ("check", 1), ("api", 2000, 400)]   # the failed answer is billed too


def test_the_estimate_for_waiting_items(client, services, cfg, routes):
    routes["api"] = False   # nothing can be used: they wait
    allow(client, 2.0)
    preload(cfg, 0.5)
    for k in ("a", "b", "c"):
        add(client, services, k)
    tag(services)
    body = client.get("/api/tagging/spend").json()
    assert body["waiting"] == {"items": 3, "photos": 3, "at_most_usd": pytest.approx(3 * spend.estimate_call(1))}
    assert body["per_photo_usd"] == pytest.approx(spend.estimate_call(1)) and body["left_usd"] == pytest.approx(1.5)
    # careful: the most a request could be billed (the longest answer allowed, generous prompt and photos)
    assert spend.estimate_call(1) == pytest.approx(spend.cost_usd("claude-haiku-5-5", 9600, 4000))
    assert spend.estimate_call(1) > ONE_CALL and spend.estimate_call(2) > spend.estimate_call(1)
    assert spend.estimate_call(1) < 0.01   # under a cent a photo at the prices written down


def test_a_new_month_starts_at_zero(client, services, cfg, monkeypatch, fake_api):
    allow(client, 1.0)
    preload(cfg, 0.999)
    item = add(client, services, "a")
    assert tag(services) == 0
    first = spend.this_month()
    nxt = (datetime.now().astimezone().replace(day=28) + timedelta(days=5))
    monkeypatch.setattr(spend, "_now", lambda: nxt)
    body = client.get("/api/tagging/spend").json()
    assert body["month"] == nxt.strftime("%Y-%m") and body["spent_usd"] == 0 and body["api_calls"] == 0
    assert body["left_usd"] == 1.0 and body["reached"] is False
    assert tag(services) == 1 and fake_api.calls == 1
    assert client.get(f"/api/items/{item['id']}").json()["tag_state"] == "done"
    months = client.get("/api/tagging/spend").json()["history"]
    assert [m["month"] for m in months] == [nxt.strftime("%Y-%m"), first]
    assert months[0]["spent_usd"] == pytest.approx(ONE_CALL) and months[1]["spent_usd"] == pytest.approx(0.999)


def bad_request(status, message):
    resp = httpx.Response(status, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    cls = {400: anthropic.BadRequestError, 401: anthropic.AuthenticationError}[status]
    return cls(message, response=resp, body=None)


@pytest.mark.parametrize("status,message,reason", [
    (400, "Your credit balance is too low to access the Anthropic API.", "credit"),
    (401, "invalid x-api-key", "key"),
])
def test_a_refused_key_switches_the_api_route_off_and_says_why(client, services, cfg, fake_api, status, message, reason):
    allow(client)
    item = add(client, services, "a")
    fake_api.error = bad_request(status, message)
    assert tag(services) == 0 and fake_api.calls == 1
    assert tuple(attempts(cfg, item["id"])) == (0, "queued")   # waits, no attempt used
    s = client.get("/api/settings").json()
    assert s["tagging_api_enabled"] is False and s["tagging_api_off"]["reason"] == reason and s["tagging_api_off"]["at"]
    assert s["tagging_api_cap_usd"] == 5.0   # the limit is kept for when it is turned on again
    assert client.get("/api/tagging/spend").json()["turned_off"]["reason"] == reason
    assert calls(cfg) == []   # an error is not billed
    assert tag(services) == 0 and fake_api.calls == 1   # not tried again

    fake_api.error = None
    s = allow(client)   # the owner has added credit and turns it on again
    assert s["tagging_api_off"] is None
    assert tag(services) == 1


def test_nothing_secret_or_personal_in_the_record_the_answers_or_the_logs(client, services, cfg, caplog, fake_api):
    allow(client)
    add(client, services, "a")
    with caplog.at_level(logging.DEBUG):
        tag(services)
        fake_api.error = bad_request(400, f"Your credit balance is too low. key={SECRET_KEY}")
        add(client, services, "b")
        tag(services)
    rows = calls(cfg)
    assert set(rows[0]) == {"id", "at", "month", "purpose", "route", "model", "input_tokens", "output_tokens", "cost_usd",
                            "prices_checked"}   # counts and money only: no photo, prompt or answer
    texts = [json.dumps(rows), caplog.text, client.get("/api/tagging/spend").text, client.get("/api/settings").text,
             json.dumps(services.state.get("tagging_api_off"))]
    for text in texts:
        assert SECRET_KEY not in text and "credit balance" not in text and "navy" not in text.lower()
    assert str(cfg.data_dir) not in client.get("/api/tagging/spend").text


def test_the_demo_closet_never_spends(client, services, cfg, fake_api, routes):
    allow(client)
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    add(client, services, "demo-1")
    routes["plan"] = True
    assert tag(services) == 0 and fake_api.calls == 0
    assert calls(cfg, "demo") == [] and calls(cfg, "main") == []
    body = client.get("/api/tagging/spend").json()
    assert body["waiting"]["items"] == 0 and body["api_calls"] == 0 and body["plan_calls"] == 0


def test_the_record_survives_a_restart_and_is_in_backups(client, services, cfg, fake_api, tmp_path, routes):
    allow(client)
    add(client, services, "a")
    tag(services)
    services.stop()
    again = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, api_client=fake_api)
    try:
        c2 = TestClient(app_module.create_app(again))
        assert c2.post("/api/login", json={"passphrase": PASSPHRASE}).status_code == 204
        assert c2.get("/api/tagging/spend").json()["api_calls"] == 1
    finally:
        again.stop()
    folder = tmp_path / "usb"
    folder.mkdir()
    result = backup.run_backup(cfg, services.state, folder=folder)
    assert result["ok"]
    snap = sqlite3.connect(folder / backup.SUBFOLDER / "db" / result["snapshot"])
    assert snap.execute("SELECT COUNT(*), SUM(route = 'api') FROM claude_calls").fetchone() == (1, 1)
    snap.close()


def test_a_second_photo_raises_the_estimate(client, services, cfg):
    item = add(client, services, "a")
    conn = db.connect(cfg.db_path("main"))
    photo = dict(conn.execute("SELECT * FROM photos WHERE item_id = ?", (item["id"],)).fetchone())
    photo.update(id=photo["id"] + "-back", kind="back", source_sha256="other")
    conn.execute(f"INSERT INTO photos ({', '.join(photo)}) VALUES ({', '.join('?' * len(photo))})", list(photo.values()))
    conn.close()
    waiting = client.get("/api/tagging/spend").json()["waiting"]
    assert waiting["items"] == 1 and waiting["photos"] == 2
    assert waiting["at_most_usd"] == pytest.approx(spend.estimate_call(2))


class Held(FakeApi):
    """An API request that stays out until it is let go, as a long one does while another worker asks."""

    def __init__(self):
        super().__init__()
        self.inside, self.go = threading.Event(), threading.Event()

    def parse(self, **kw):
        self.inside.set()
        assert self.go.wait(10)
        return super().parse(**kw)


def test_requests_made_at_once_cannot_together_pass_the_limit(client, services, cfg):
    """Workers ask Claude at the same time (describing, landmarks, the pieces in a photo, "Would this work?",
    shopping): what a request on its way may cost counts against the limit until it has come back."""
    allow(client, 1.0)
    one = spend.estimate_call(1, "claude-haiku-5-5")
    preload(cfg, 1.0 - 1.5 * one)   # room for one request, not two
    meter, image = spend.Meter(cfg, services.state), Image.new("RGBA", (40, 40))
    slow, done = Held(), []
    first = threading.Thread(target=lambda: done.append(tag_item(slow, "claude-haiku-5-5", [image], meter=meter)))
    first.start()
    try:
        assert slow.inside.wait(10)
        other = FakeApi()
        with pytest.raises(CapReached):
            tag_item(other, "claude-haiku-5-5", [image], meter=meter)
        assert other.calls == 0   # not made: together they could have passed the limit
    finally:
        slow.go.set()
        first.join(10)
    assert len(done) == 1 and len(calls(cfg)) == 2   # the preloaded spend and the first request
    # back, it cost what it cost (much less than its estimate): there is room again
    assert tag_item(other, "claude-haiku-5-5", [image], meter=meter).route == "api" and other.calls == 1


def test_a_request_that_fails_lets_go_of_what_it_held(client, services, cfg):
    allow(client, 1.0)
    one = spend.estimate_call(1, "claude-haiku-5-5")
    preload(cfg, 1.0 - 1.5 * one)
    meter, image = spend.Meter(cfg, services.state), Image.new("RGBA", (40, 40))
    refused = FakeApi()
    refused.error = bad_request(400, "the request was not understood")
    failed = []

    def ask():
        try:
            tag_item(refused, "claude-haiku-5-5", [image], meter=meter)
        except TaggingError as e:
            failed.append(e)
    worker = threading.Thread(target=ask)
    worker.start()
    worker.join(10)
    assert len(failed) == 1 and refused.calls == 1
    other = FakeApi()   # the failed request is not out any more, so it holds nothing back
    assert tag_item(other, "claude-haiku-5-5", [image], meter=meter).route == "api" and other.calls == 1
