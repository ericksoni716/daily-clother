"""Reading a correction by sentence (`tagger/correcting.py`): the prompt, both routes, and the API key's limit.

Claude is never called: the plan route's `claude -p` is replaced by a stand-in for `subprocess.run`, and the API
by `FakeApi` (conftest), which reads every correction as "two buttons".
"""
import json
from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx2 as httpx
import pytest
from anthropic.lib._parse._transform import transform_schema
from PIL import Image

from closet import app as app_module
from closet import db, spend, tagjobs
from closet.tagger import correcting
from closet.tagger import routes as tagger_routes
from closet.tagger.correcting import CorrectionAnswer
from closet.tagger.tagging import CapReached, RouteUnavailable

from .conftest import ANSWER, FakeApi, fake_cutter, upload

SECRET_KEY = "sk-ant-api03-test-only-not-a-real-key"
DESCRIPTION = {"category": "polo", "color": "navy", "placket_buttons": 3}
ALLOWED = {"color": ["navy", "green"], "placket_buttons": [str(n) for n in range(11)]}


class Meter:
    """Writes down what the meter is told; `cap` makes the check before an API request refuse."""

    def __init__(self, cap=False):
        self.cap, self.checked, self.recorded, self.refused = cap, [], [], []

    def before_api_call(self, model, images):
        self.checked.append((model, images))
        if self.cap:
            raise CapReached("this month's spending limit for the API key has been reached")

    def record(self, route, model, input_tokens, output_tokens):
        self.recorded.append((route, model, input_tokens, output_tokens))

    def api_refused(self, reason):
        self.refused.append(reason)


def cli_answer(answer: dict, usage=None, returncode=0):
    out = {"structured_output": answer, "is_error": False, "result": "",
           "usage": usage or {"input_tokens": 3000, "cache_read_input_tokens": 500, "output_tokens": 80}}
    return SimpleNamespace(returncode=returncode, stdout=json.dumps(out), stderr="")


@pytest.fixture
def cli(monkeypatch):
    """A stand-in for `claude -p`: answers `reply` and keeps the commands it was given."""
    seen = {"commands": [], "reply": cli_answer({"changes": [{"name": "placket_buttons", "value": "2"}],
                                                 "not_understood": "", "needs_photo": False}), "files": [], "inputs": []}

    def run(cmd, cwd=None, **kw):
        seen["commands"].append(cmd)
        seen["inputs"].append(kw["stdin"].read().decode("utf-8"))
        seen["files"].append(sorted(p.name for p in Path(cwd).iterdir()))
        return seen["reply"]
    monkeypatch.setattr(correcting.subprocess, "run", run)
    return seen


def bad_request(status, message):
    resp = httpx.Response(status, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    cls = {400: anthropic.BadRequestError, 401: anthropic.AuthenticationError}[status]
    return cls(message, response=resp, body=None)


# ---- the prompt

def test_the_prompt_has_the_sentence_the_description_and_the_allowed_values_only():
    text = correcting.prompt("it has two buttons", DESCRIPTION, ALLOWED, with_photo=False)
    assert "it has two buttons" in text and '"placket_buttons": 3' in text
    assert "- color: navy, green" in text and "- placket_buttons: 0, 1, 2" in text
    assert "needs_photo" in text and "Never guess" in text
    assert "background removed" in correcting.prompt("x", DESCRIPTION, ALLOWED, with_photo=True)


# ---- the plan route

def test_the_plan_route_is_tried_first_and_recorded_at_no_cost(cli):
    meter, api = Meter(), FakeApi()
    result = correcting.correct("it has two buttons", DESCRIPTION, ALLOWED, [], ("plan", "api"), client=api,
                                exe="claude", meter=meter)
    assert result.route == "plan" and [(c.name, c.value) for c in result.answer.changes] == [("placket_buttons", "2")]
    assert api.calls == 0 and meter.checked == []
    assert meter.recorded == [("plan", correcting.MODEL, 3500, 80)]
    cmd = cli["commands"][0]
    assert cmd[0] == "claude" and "it has two buttons" in cli["inputs"][0] and cli["files"][0] == []
    assert not any("it has two buttons" in part for part in cmd)   # the owner's words never on a command line


def test_the_plan_route_is_given_the_photo_as_a_file(cli):
    correcting.correct("the colour is wrong", DESCRIPTION, ALLOWED, [Image.new("RGBA", (40, 60), (20, 30, 90, 255))],
                       ("plan",), exe="claude")
    assert cli["files"][0] == ["item.jpg"] and "item.jpg" in cli["inputs"][0]


def test_the_plan_route_is_given_every_photo_as_a_file_named_in_the_prompt(cli):
    photos = [Image.new("RGB", (40, 60), (20 * n, 30, 90)) for n in range(3)]
    correcting.ask("Which view does each photo show?", photos, ("plan",), exe="claude")
    assert cli["files"][0] == ["photo-1.jpg", "photo-2.jpg", "photo-3.jpg"]
    assert "in order: photo-1.jpg, photo-2.jpg, photo-3.jpg" in cli["inputs"][0]
    assert "item.jpg" not in cli["inputs"][0]


def test_a_plan_at_its_limit_falls_back_to_the_api_key(cli):
    cli["reply"] = SimpleNamespace(returncode=1, stdout=json.dumps({"is_error": True, "result": "You've hit your limit"}),
                                   stderr="")
    meter, api = Meter(), FakeApi()
    result = correcting.correct("it has two buttons", DESCRIPTION, ALLOWED, [], ("plan", "api"), client=api,
                                exe="claude", meter=meter)
    assert result.route == "api" and api.calls == 1
    assert meter.recorded == [("api", correcting.MODEL, 2000, 400)]


# ---- the API route

def test_every_api_request_is_checked_before_and_recorded_after(monkeypatch):
    meter, api = Meter(), FakeApi()
    photo = Image.new("RGBA", (40, 60), (20, 30, 90, 255))
    result = correcting.correct("the colour is wrong", DESCRIPTION, ALLOWED, [photo], ("api",), client=api, meter=meter)
    assert result.route == "api" and result.answer.changes[0].value == "2"
    assert meter.checked == [(correcting.MODEL, 1)] and meter.recorded == [("api", correcting.MODEL, 2000, 400)]
    sent = api.requests[0]
    assert sent["output_format"] is CorrectionAnswer and sent["max_tokens"] == correcting.MAX_TOKENS
    assert [c["type"] for c in sent["messages"][0]["content"]] == ["image", "text"]

    # an answer cut short is asked again: each request checked and counted
    api.correction = None
    with pytest.raises(correcting.TaggingError):
        correcting.correct("x", DESCRIPTION, ALLOWED, [], ("api",), client=api, meter=meter)
    assert len(meter.checked) == 1 + correcting.MAX_ATTEMPTS and len(meter.recorded) == 1 + correcting.MAX_ATTEMPTS


def test_the_limit_stops_the_api_request_before_it_is_made():
    meter, api = Meter(cap=True), FakeApi()
    with pytest.raises(CapReached):
        correcting.correct("it has two buttons", DESCRIPTION, ALLOWED, [], ("api",), client=api, meter=meter)
    assert api.calls == 0 and meter.recorded == []


@pytest.mark.parametrize("status,message,reason", [
    (400, "Your credit balance is too low to access the Anthropic API.", "credit"),
    (401, "invalid x-api-key", "key"),
])
def test_a_refused_key_is_reported_to_the_meter(status, message, reason):
    meter, api = Meter(), FakeApi()
    api.error = bad_request(status, message)
    with pytest.raises(RouteUnavailable):
        correcting.correct("it has two buttons", DESCRIPTION, ALLOWED, [], ("api",), client=api, meter=meter)
    assert meter.refused == [reason] and meter.recorded == [] and api.calls == 1


def test_the_estimate_is_careful():
    """The check before a request allows for the longest prompt this app writes and the longest answer allowed."""
    from closet import details, vocab
    allowed = {f: list(vocab.ENUM_FIELDS[f]) for f in details.FIELDS}
    allowed.update({f"silhouette.{k}": list(v) for k, v in vocab.SILHOUETTE.items()})
    for n in details.names_for("shirt"):
        allowed[n] = [str(v) for v in details.values(n)]
    description = {n: "a_long_value_name" for n in allowed}
    # the longest cloth and lettering the description can carry (since schema 7), and the form sent with them
    description["cloth"] = {"kind": "plaid", "bands": [{"color": "#123456", "width": 12}] * 12, "direction": None,
                            "size": "medium", "blocks": [{"part": "left_sleeve_as_seen", "color": "#123456"}] * 6,
                            "panels": [{"top": 10, "bottom": 20, "color": "#123456"}] * 6,
                            "colors": [{"color": "#123456", "share": 10}] * 8}
    description["lettering"] = [{"text": "X" * 30, "place": "center_chest", "size": "large", "style": "script",
                                 "color": "#123456"}] * 3
    text = correcting.prompt("x" * 500, description, allowed, with_photo=True)
    schema = json.dumps(transform_schema(CorrectionAnswer))
    assert (len(text) + len(schema)) / 2 * 2 <= spend.CORRECT_TEXT_TOKENS   # 2 characters to a token, then doubled
    assert spend.estimate_correction(0) < spend.estimate_correction(1)
    assert spend.estimate_correction(1) >= spend.cost_usd(spend.TAGGING_MODEL, spend.CORRECT_TEXT_TOKENS + spend.IMAGE_TOKENS,
                                                          correcting.MAX_TOKENS)


# ---- in the app: the real routes, with the plan and the API stood in for

@pytest.fixture
def usable(monkeypatch, cli):
    state = {"plan": False, "api": True}
    monkeypatch.setattr(tagger_routes, "status", lambda order="auto", claude_exe=None: {
        "order": ["plan", "api"], "routes": [{"id": r, "available": state[r], "detail": ""} for r in ("plan", "api")]})
    monkeypatch.setattr(correcting.claude_cli, "find_claude", lambda: "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET_KEY)
    return state


@pytest.fixture
def fake_api():
    return FakeApi()


@pytest.fixture
def services(cfg, usable, fake_api):
    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, api_client=fake_api)
    sv.worker.is_ready = lambda: True
    yield sv
    sv.stop()


def polo(client, services, cfg):
    item = upload(client, key="polo").json()
    services.worker.drain()
    conn = db.connect(cfg.db_path("main"))
    try:
        conn.execute("BEGIN IMMEDIATE")
        tagjobs.apply_answer(conn, item["id"], ANSWER, "plan", "fake")
        conn.execute("COMMIT")
    finally:
        conn.close()
    return item


def calls(cfg):
    conn = db.connect(cfg.db_path("main"))
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM claude_calls ORDER BY id")]
    finally:
        conn.close()


def allow(client, cap=5.0):
    r = client.put("/api/settings", json={"tagging_api_enabled": True, "tagging_api_cap_usd": cap})
    assert r.status_code == 200, r.text


def test_a_correction_through_the_api_key_is_recorded_with_its_purpose(client, services, cfg, fake_api):
    item = polo(client, services, cfg)
    allow(client)
    body = client.post(f"/api/items/{item['id']}/correct", json={"sentence": "it has two buttons"}).json()
    assert body["state"] == "understood" and body["changes"][0]["value"] == 2
    rows = calls(cfg)
    assert [(r["purpose"], r["route"], r["input_tokens"], r["output_tokens"]) for r in rows] == [
        ("correct_item", "api", 2000, 400)]
    assert rows[0]["cost_usd"] == pytest.approx(spend.cost_usd(spend.TAGGING_MODEL, 2000, 400))
    assert client.get("/api/tagging/spend").json()["api_calls"] == 1


def test_a_correction_through_the_plan_is_recorded_at_no_cost(client, services, cfg, usable, fake_api):
    item = polo(client, services, cfg)
    usable["plan"] = True
    body = client.post(f"/api/items/{item['id']}/correct", json={"sentence": "it has two buttons"}).json()
    assert body["state"] == "understood" and fake_api.calls == 0
    assert [(r["purpose"], r["route"], r["cost_usd"]) for r in calls(cfg)] == [("correct_item", "plan", 0.0)]


def test_the_spending_limit_stops_a_correction_and_offers_the_picker(client, services, cfg, fake_api):
    item = polo(client, services, cfg)
    allow(client, cap=0.01)
    conn = db.connect(cfg.db_path("main"))
    conn.execute("INSERT INTO claude_calls (at, month, purpose, route, model, cost_usd) VALUES (?, ?, 'tag_item', 'api', "
                 "?, 0.0095)", (db.now(), spend.this_month(), spend.TAGGING_MODEL))
    conn.close()
    body = client.post(f"/api/items/{item['id']}/correct", json={"sentence": "it has two buttons"}).json()
    assert body["state"] == "waiting" and body["limit"] is True and body["changes"] == []
    assert "spending limit" in body["message"] and "pick the details" in body["message"].lower()
    assert fake_api.calls == 0 and len(calls(cfg)) == 1
    assert client.get(f"/api/items/{item['id']}").json()["own_details"] == {}


def test_a_refused_key_switches_the_key_off_as_tagging_does(client, services, cfg, fake_api):
    item = polo(client, services, cfg)
    allow(client)
    fake_api.error = bad_request(400, f"Your credit balance is too low. key={SECRET_KEY}")
    body = client.post(f"/api/items/{item['id']}/correct", json={"sentence": "it has two buttons"}).json()
    assert body["state"] == "waiting" and fake_api.calls == 1
    s = client.get("/api/settings").json()
    assert s["tagging_api_enabled"] is False and s["tagging_api_off"]["reason"] == "credit"
    assert calls(cfg) == [] and SECRET_KEY not in json.dumps(body)
    # turned off: the next sentence is not sent through the key
    assert client.post(f"/api/items/{item['id']}/correct", json={"sentence": "it has two buttons"}).json()["state"] == "waiting"
    assert fake_api.calls == 1


def test_the_photo_is_sent_on_a_second_request_both_checked_and_recorded(client, services, cfg, fake_api):
    item = polo(client, services, cfg)
    allow(client)
    first = CorrectionAnswer(changes=[], not_understood="", needs_photo=True)
    answers = iter([first, CorrectionAnswer(changes=[{"name": "color", "value": "green"}], not_understood="",
                                            needs_photo=False)])
    real = fake_api.parse

    def parse(**kw):
        fake_api.correction = next(answers)
        return real(**kw)
    fake_api.parse = parse
    body = client.post(f"/api/items/{item['id']}/correct", json={"sentence": "the colour is wrong"}).json()
    assert body["state"] == "understood" and "photo" in body["sent"]
    assert [len([c for c in r["messages"][0]["content"] if c["type"] == "image"]) for r in fake_api.requests] == [0, 1]
    assert [r["purpose"] for r in calls(cfg)] == ["correct_item", "correct_item"]


# ---- the arguments for longer questions (a shoe drawn from its photos): names, max_tokens, timeout, effort

def test_by_default_ask_behaves_as_before(cli):
    """No names, no effort, no timeout given: the images are photo-N.jpg (or item.jpg), the model's effort, two
    minutes; on the API route `messages.parse` with MAX_TOKENS and nothing between the images."""
    correcting.ask("Which view?", [Image.new("RGB", (40, 60))] * 2, ("plan",), exe="claude")
    cmd = cli["commands"][0]
    assert cmd[cmd.index("--effort") + 1] == correcting.CONFIG["models"][correcting.MODEL]["effort"]
    assert cli["files"][0] == ["photo-1.jpg", "photo-2.jpg"]
    api = FakeApi()
    correcting.ask("x", [Image.new("RGB", (40, 60))] * 2, ("api",), client=api)
    sent = api.requests[0]
    assert sent["max_tokens"] == correcting.MAX_TOKENS and "output_format" in sent
    assert [c["type"] for c in sent["messages"][0]["content"]] == ["image", "image", "text"]


def test_named_images_are_saved_under_their_names_on_the_plan(monkeypatch, cli):
    seen = {}
    real = cli["reply"]

    def run(cmd, cwd=None, **kw):
        seen["timeout"], seen["cmd"] = kw["timeout"], cmd
        seen["input"] = kw["stdin"].read().decode("utf-8")
        seen["files"] = {p.name: p.read_bytes()[:4] for p in Path(cwd).iterdir()}
        return real
    monkeypatch.setattr(correcting.subprocess, "run", run)
    images = [Image.new("RGB", (40, 60), (200, 0, 0)), Image.new("RGBA", (30, 30), (0, 0, 0, 0))]
    result = correcting.ask("Look.", images, ("plan",), exe="claude", names=["photo-1.jpg", "drawing.png"],
                            timeout=600, effort="high")
    assert sorted(seen["files"]) == ["drawing.png", "photo-1.jpg"]
    assert seen["files"]["drawing.png"] == b"\x89PNG" and seen["files"]["photo-1.jpg"][:2] == b"\xff\xd8"
    assert "in the current folder: photo-1.jpg, drawing.png" in seen["input"]
    assert seen["timeout"] == 600 and seen["cmd"][seen["cmd"].index("--effort") + 1] == "high"
    assert result.cache_read_tokens == 500 and result.input_tokens == 3500


def test_names_are_checked():
    for names in (["a.jpg"], ["../x.jpg", "b.jpg"], ["a.jpg", "a.jpg"], ["a.gif", "b.jpg"], ["A B.jpg", "b.jpg"]):
        with pytest.raises(ValueError):
            correcting.ask("x", [Image.new("RGB", (4, 4))] * 2, ("plan",), exe="claude", names=names)


def test_named_images_are_labelled_on_the_api_route_and_a_png_stays_png():
    api = FakeApi()
    correcting.ask("Look.", [Image.new("RGB", (40, 60)), Image.new("RGB", (40, 60))], ("api",), client=api,
                   names=["photo-1.jpg", "drawing.png"], effort="high")
    content = api.requests[0]["messages"][0]["content"]
    assert [c.get("text") or c["source"]["media_type"] for c in content] == [
        "photo-1.jpg:", "image/jpeg", "drawing.png:", "image/png", "Look."]
    assert api.requests[0]["output_config"]["effort"] == "high"


def test_a_long_answer_is_streamed_as_the_sdk_requires():
    """The SDK refuses a request without streaming above NONSTREAMING_MAX_TOKENS; above it the answer is streamed,
    with the schema in output_config.format, and read once it has come."""
    client = anthropic.Anthropic(api_key="x")
    client._calculate_nonstreaming_timeout(correcting.NONSTREAMING_MAX_TOKENS, None)
    with pytest.raises(ValueError, match="Streaming is required"):
        client._calculate_nonstreaming_timeout(correcting.NONSTREAMING_MAX_TOKENS + 1, None)
    api, meter = FakeApi(), Meter()
    api.drawing = CorrectionAnswer(changes=[], not_understood="", needs_photo=False)
    got = correcting.ask("x", [], ("api",), client=api, meter=meter, max_tokens=correcting.NONSTREAMING_MAX_TOKENS + 1)
    sent = api.requests[0]
    assert got.answer == api.drawing and "output_format" not in sent
    # the cloth and its lettering, rewritten whole when a sentence is about them, since schema 7
    assert sent["output_config"]["format"]["schema"]["properties"].keys() == {"changes", "not_understood", "needs_photo",
                                                                              "cloth", "lettering"}
    assert sent["max_tokens"] == correcting.NONSTREAMING_MAX_TOKENS + 1
    assert meter.checked == [(correcting.MODEL, 0)] and meter.recorded == [("api", correcting.MODEL, 2000, 400)]
    correcting.ask("x", [], ("api",), client=api, max_tokens=correcting.NONSTREAMING_MAX_TOKENS)
    assert "output_format" in api.requests[1]   # at the limit: not streamed


def test_a_streamed_answer_cut_short_is_asked_again_and_counted_each_time():
    api, meter = FakeApi(), Meter()
    replies = iter([SimpleNamespace(type="text", text='{"changes": [{"name": "col'), SimpleNamespace(type="text", text="{}")])

    def stream(**kw):
        api.calls += 1
        api.requests.append(kw)
        message = SimpleNamespace(content=[next(replies)], stop_reason="max_tokens",
                                  usage=SimpleNamespace(input_tokens=100, output_tokens=50))

        class Stream:
            def __enter__(self):
                return SimpleNamespace(get_final_message=lambda: message)

            def __exit__(self, *exc):
                return False
        return Stream()
    api.stream = stream
    with pytest.raises(correcting.TaggingError, match="no valid answer"):
        correcting.ask("x", [], ("api",), client=api, meter=meter, max_tokens=64_000)
    assert len(meter.recorded) == correcting.MAX_ATTEMPTS == 2
