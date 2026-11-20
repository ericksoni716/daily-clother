"""The style conversation (closet/stylechat.py): the owner writes to Claude about how they dress, from Settings, Your
style; Claude answers in the background and may offer lines to keep, which are kept in Your style only when the owner
taps Save, and can be taken back. Claude is stood in for; the background job is held and run by the test, and the
clock is the test's. The last tests go through the real route and meter with the API stood in for."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from closet import app as app_module
from closet import db, spend, styleprofile, stylequestions, styling
from closet.stylechat import MAX_PER_DAY, REFUSED, WHY_NOT, brief, offers
from closet.stylejobs import STALE_S
from closet.tagger import routes as tagger_routes
from closet.tagger import stylist
from closet.tagger.tagging import CapReached, RouteUnavailable, TaggingError, Unreachable

from .conftest import PASSPHRASE, FakeApi, fake_cutter


class StandIn:
    """Stands in for Claude in the style conversation: answers `reply` and offers `remember`, or raises `error`.
    `calls` holds (brief, routes)."""

    def __init__(self):
        self.calls: list = []
        self.reply = "Then a lighter layer on mild days."
        self.remember: list = ["I run warm, so one layer fewer than most people."]
        self.error: Exception | None = None

    def __call__(self, brief: dict, routes: tuple[str, ...]) -> dict:
        self.calls.append((brief, routes))
        if self.error is not None:
            raise self.error
        return {"reply": self.reply, "remember": self.remember, "route": routes[0], "model": "stand-in-model",
                "input_tokens": 700, "output_tokens": 90}


@pytest.fixture
def chatty(cfg, claude):
    """Services whose style conversation asks the stand-in; its jobs are held (`held`) and its clock is `now["t"]`."""
    claude.mode = "answers"
    stand_in = StandIn()
    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, tagger=claude, routes=lambda: claude.routes(),
                                   corrector=claude.correct, chat_ask=stand_in)
    held: list = []
    now = {"t": 1_800_000_000.0}
    sv.chat.start = held.append
    sv.chat.clock = lambda: now["t"]
    c = TestClient(app_module.create_app(sv))
    assert c.post("/api/setup", json={"passphrase": PASSPHRASE}).status_code == 204
    yield SimpleNamespace(c=c, sv=sv, stand_in=stand_in, held=held, now=now, cfg=cfg, claude=claude)
    sv.stop()


def run(env):
    while env.held:
        env.held.pop(0)()


def say(env, text="I always feel warm on the bus."):
    return env.c.post("/api/style/talk", json={"say": text})


def answered(env, text="I always feel warm on the bus.") -> dict:
    """A message sent and answered: the conversation as the page then reads it."""
    r = say(env, text)
    assert r.status_code == 200, r.text
    run(env)
    return env.c.get("/api/style/talk").json()


def remember(env, turn_id, **body):
    return env.c.post(f"/api/style/talk/{turn_id}/remember", json=body)


def lines(env) -> list[str]:
    return [ln["text"] for ln in env.c.get("/api/style/profile").json()["lines"]]


def rows(env, sql):
    conn = db.connect(env.cfg.db_path("main"))
    try:
        return [dict(r) for r in conn.execute(sql)]
    finally:
        conn.close()


# ------------------------------------------------------------------ sending and answering
def test_with_nothing_said_today_the_conversation_asks_the_first_question(chatty):
    body = chatty.c.get("/api/style/talk").json()
    assert body == {"turns": [], "answering": None, "question": stylequestions.public(stylequestions.QUESTIONS[0]),
                    "refused": None}


def test_a_message_is_a_working_turn_being_answered_and_one_job_is_held(chatty):
    r = say(chatty, "  I always feel\n warm on the bus. ")
    assert r.status_code == 200, r.text
    body = r.json()
    [turn] = body["turns"]
    assert body["answering"] == turn["id"] and body["question"] is None and body["refused"] is None
    assert turn == {"id": turn["id"], "said": "I always feel warm on the bus.", "state": "working", "reply": None,
                    "message": None, "remember": [], "at": turn["at"]}
    assert len(chatty.held) == 1 and chatty.stand_in.calls == []


def test_claude_is_told_the_profile_the_days_conversation_and_the_message(chatty):
    chatty.c.put("/api/style/profile", json={"text": "- I dress plainly."})
    answered(chatty, "First thing.")
    answered(chatty, "Second thing.")
    told, routes = chatty.stand_in.calls[1]
    assert told["profile"] == "- I dress plainly." and told["say"] == "Second thing."
    assert told["talk"] == ("What was said today, oldest first:\n- The owner: “First thing.”\n"
                            "- You: “Then a lighter layer on mild days.”")
    assert routes == ("plan",)
    assert chatty.stand_in.calls[0][0]["talk"] == ""


def test_with_the_starting_profile_in_force_claude_is_told_it():
    assert brief(None, [], "Hi.")["profile"] == styling.DEFAULT_PROFILE


def test_an_answer_is_kept_with_its_reply_and_the_lines_offered(chatty):
    body = answered(chatty)
    [turn] = body["turns"]
    assert body["answering"] is None
    assert turn["state"] == "ready" and turn["reply"] == "Then a lighter layer on mild days."
    assert turn["remember"] == [{"kind": "style", "item_id": None, "name": None,
                                 "text": "I run warm, so one layer fewer than most people.", "state": "offered"}]
    [row] = rows(chatty, "SELECT route, model, input_tokens, output_tokens, seconds FROM style_talk")
    assert row["route"] == "plan" and row["model"] == "stand-in-model" and row["input_tokens"] == 700
    assert row["output_tokens"] == 90 and row["seconds"] is not None


def test_lines_offered_are_one_sentence_each_at_most_max_keeps_and_without_duplicates():
    got = offers(["  One   thing. ", "One thing.", "", 3, "Two.", "Three."])
    assert [k["text"] for k in got] == ["One thing.", "Two."][:styling.MAX_KEEPS]
    assert offers("not a list") == [] and offers(None) == []


def test_an_answer_with_no_words_back_is_a_failed_turn(chatty):
    chatty.stand_in.reply = "  "
    [turn] = answered(chatty)["turns"]
    assert turn["state"] == "failed" and turn["message"] == WHY_NOT["answer"] and turn["remember"] == []


@pytest.mark.parametrize("error, why", [
    (Unreachable("offline"), "unreachable"), (RouteUnavailable("signed out"), "unreachable"),
    (CapReached("limit"), "limit"), (TaggingError("bad answer"), "answer"), (RuntimeError("boom"), "error")])
def test_each_failure_marks_the_turn_failed_with_a_sentence(chatty, error, why):
    chatty.stand_in.error = error
    [turn] = answered(chatty)["turns"]
    assert turn["state"] == "failed" and turn["message"] == WHY_NOT[why] and turn["reply"] is None
    assert "outfits" not in turn["message"]


def test_when_claude_cannot_be_reached_the_page_is_told_in_plain_words(chatty):
    chatty.stand_in.error = Unreachable("offline")
    [turn] = answered(chatty)["turns"]
    assert turn["message"] == "Claude couldn't be reached, so this wasn't answered."


def test_a_message_lost_when_closet_stopped_is_marked_and_another_can_be_sent(chatty):
    assert say(chatty).status_code == 200
    chatty.held.clear()   # the program stopped before the job ran
    chatty.now["t"] += STALE_S + 1
    body = chatty.c.get("/api/style/talk").json()
    assert body["answering"] is None and body["turns"][0]["message"] == WHY_NOT["lost"]
    assert say(chatty, "Again.").status_code == 200


# ------------------------------------------------------------------ refused
def refused(env, why, text="Hello."):
    r = say(env, text)
    assert r.status_code == 422 and r.json()["detail"] == REFUSED[why], r.text


def test_a_message_is_refused_while_another_is_being_answered(chatty):
    assert say(chatty).status_code == 200
    refused(chatty, "busy")


def test_a_message_is_refused_with_no_route_to_claude_and_the_page_is_told_before_it_writes(chatty):
    chatty.claude.mode = "unavailable"
    assert chatty.c.get("/api/style/talk").json()["refused"] == REFUSED["no_route"]
    refused(chatty, "no_route")
    assert chatty.stand_in.calls == [] and rows(chatty, "SELECT id FROM style_talk") == []


def test_a_message_is_refused_at_the_days_limit(chatty):
    for i in range(MAX_PER_DAY):
        answered(chatty, f"Message {i}.")
    assert chatty.c.get("/api/style/talk").json()["refused"] == REFUSED["day_limit"]
    refused(chatty, "day_limit")


def test_a_message_is_refused_in_the_demo_closet(chatty):
    assert chatty.c.post("/api/profile", json={"profile": "demo"}).status_code == 200
    assert chatty.c.get("/api/style/talk").json()["refused"] == REFUSED["demo"]
    refused(chatty, "demo")
    assert chatty.stand_in.calls == []


def test_without_a_conversation_wired_a_message_is_refused(client):
    assert client.get("/api/style/talk").json()["refused"] == REFUSED["off"]
    r = client.post("/api/style/talk", json={"say": "Hello."})
    assert r.status_code == 422 and r.json()["detail"] == REFUSED["off"]


@pytest.mark.parametrize("body, status", [({"say": ""}, 422), ({"say": "   "}, 422), ({"say": 3}, 422), ({}, 422),
                                          (["say"], 422), ({"say": "x" * (styling.MAX_SAY + 1)}, 422)])
def test_a_message_that_is_not_one_is_refused(chatty, body, status):
    assert chatty.c.post("/api/style/talk", json=body).status_code == status
    assert chatty.c.post("/api/style/talk", content=b"{", headers={"content-type": "application/json"}).status_code == 400


def test_the_conversation_needs_login(chatty):
    anon = TestClient(app_module.create_app(chatty.sv))
    assert anon.get("/api/style/talk").status_code == 401
    assert anon.post("/api/style/talk", json={"say": "Hi."}).status_code == 401
    assert anon.post("/api/style/talk/x/remember", json={"index": 0, "save": True}).status_code == 401


# ------------------------------------------------------------------ keeping what Claude offered
def test_saving_a_line_adds_it_to_your_style_marked_as_from_a_conversation(chatty):
    [turn] = answered(chatty)["turns"]
    r = remember(chatty, turn["id"], index=0, save=True)
    assert r.status_code == 200, r.text
    assert r.json() == {"kind": "style", "item_id": None, "name": None,
                        "text": "I run warm, so one layer fewer than most people.", "state": "saved"}
    profile = chatty.c.get("/api/style/profile").json()
    assert [ln["source"] for ln in profile["lines"]] == ["start", "talk"]
    assert profile["text"] == f"{styling.DEFAULT_KEPT}\n- I run warm, so one layer fewer than most people."
    assert rows(chatty, "SELECT source FROM style_profile") == [{"source": "claude"}]
    assert chatty.c.get("/api/style/talk").json()["turns"][0]["remember"][0]["state"] == "saved"


def test_undo_takes_the_line_back_out_and_offers_it_again(chatty):
    [turn] = answered(chatty)["turns"]
    remember(chatty, turn["id"], index=0, save=True)
    r = remember(chatty, turn["id"], index=0, undo=True)
    assert r.status_code == 200 and r.json()["state"] == "offered"
    assert chatty.c.get("/api/style/profile").json()["is_default"] is True
    assert remember(chatty, turn["id"], index=0, undo=True).json()["state"] == "offered"   # twice: nothing more
    assert remember(chatty, turn["id"], index=0, save=True).json()["state"] == "saved"
    assert lines(chatty)[-1] == "- I run warm, so one layer fewer than most people."


def test_undo_after_the_line_was_removed_in_settings_changes_nothing_else(chatty):
    [turn] = answered(chatty)["turns"]
    remember(chatty, turn["id"], index=0, save=True)
    line_id = chatty.c.get("/api/style/profile").json()["lines"][-1]["id"]
    chatty.c.put("/api/style/profile", json={"text": "- Mine."})
    assert chatty.c.delete(f"/api/style/lines/{line_id}").status_code == 404   # gone with the whole-text save
    assert remember(chatty, turn["id"], index=0, undo=True).json()["state"] == "offered"
    assert lines(chatty) == ["- Mine."]


def test_no_thanks_keeps_nothing(chatty):
    [turn] = answered(chatty)["turns"]
    assert remember(chatty, turn["id"], index=0, save=False).json()["state"] == "dismissed"
    assert chatty.c.get("/api/style/profile").json()["is_default"] is True
    assert remember(chatty, turn["id"], index=0, save=True).json()["state"] == "dismissed"


def test_a_line_already_in_your_style_is_not_added_twice(chatty):
    chatty.c.put("/api/style/profile", json={"text": "- I run warm, so one layer fewer than most people."})
    [turn] = answered(chatty)["turns"]
    assert remember(chatty, turn["id"], index=0, save=True).json()["state"] == "saved"
    assert lines(chatty) == ["- I run warm, so one layer fewer than most people."]


@pytest.mark.parametrize("body", [{"index": 1, "save": True}, {"index": True, "save": True}, {"save": True}])
def test_a_wrong_line_is_refused_with_a_sentence(chatty, body):
    [turn] = answered(chatty)["turns"]
    r = chatty.c.post(f"/api/style/talk/{turn['id']}/remember", json=body)
    assert r.status_code == 422 and r.json()["detail"] == "That is no longer in the conversation. Open it again."
    r = remember(chatty, "nope", index=0, save=True)
    assert r.status_code == 422


def test_keeping_must_say_true_or_false(chatty):
    [turn] = answered(chatty)["turns"]
    r = remember(chatty, turn["id"], index=0, save="yes")
    assert r.status_code == 422
    assert r.json()["detail"] == "Say which thing (index) and whether to keep it (save: true or false)."


# ------------------------------------------------------------------ the real route, the meter and the limit
@pytest.fixture
def metered(cfg, monkeypatch):
    """The real conversation, route and meter, with only the API key usable and the API stood in for."""
    monkeypatch.setattr(tagger_routes, "status", lambda order="auto", claude_exe=None: {
        "order": ["plan", "api"], "routes": [{"id": "plan", "available": False, "detail": ""},
                                             {"id": "api", "available": True, "detail": ""}]})
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-" + "x" * 40)
    api = FakeApi(input_tokens=3000, output_tokens=200)
    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, api_client=api)
    held: list = []
    sv.chat.start = held.append
    c = TestClient(app_module.create_app(sv))
    assert c.post("/api/setup", json={"passphrase": PASSPHRASE}).status_code == 204
    yield SimpleNamespace(c=c, sv=sv, api=api, held=held, cfg=cfg)
    sv.stop()


def allow(c, cap):
    assert c.put("/api/settings", json={"tagging_api_enabled": True, "tagging_api_cap_usd": cap}).status_code == 200


def test_a_message_through_the_api_key_is_recorded_as_the_style_conversation(metered):
    allow(metered.c, 5.0)
    body = answered(metered)
    [turn] = body["turns"]
    assert turn["state"] == "ready" and turn["reply"] == "Noted: a little lighter than most."
    assert [k["text"] for k in turn["remember"]] == ["I run warm."]
    [call] = rows(metered, "SELECT purpose, route, model, input_tokens, output_tokens, cost_usd FROM claude_calls")
    assert call["purpose"] == spend.PURPOSE_STYLE_CHAT == "style_talk"
    assert call["route"] == "api" and call["model"] == stylist.MODEL
    assert call["input_tokens"] == 3000 and call["output_tokens"] == 200 and call["cost_usd"] > 0
    [sent] = metered.api.requests
    assert sent["output_format"] is stylist.ChatReply and sent["max_tokens"] == stylist.CHAT_MAX_TOKENS
    assert "I always feel warm on the bus." in str(sent["messages"])


def test_at_the_monthly_limit_the_message_is_not_answered_and_nothing_is_spent(metered):
    allow(metered.c, 0.01)   # less than one message may cost
    [turn] = answered(metered)["turns"]
    assert turn["state"] == "failed" and turn["message"] == WHY_NOT["limit"]
    assert metered.api.requests == [] and rows(metered, "SELECT id FROM claude_calls") == []


def test_with_the_api_key_off_and_no_plan_the_page_is_told_claude_cannot_be_reached(metered):
    assert metered.c.get("/api/style/talk").json()["refused"] == REFUSED["no_route"]


def test_a_message_is_priced_with_the_styling_model():
    cost = spend.estimate_style_chat()
    assert 0 < cost < spend.estimate_style()
    assert cost == spend.cost_usd(spend.STYLING_MODEL, spend.CHAT_TEXT_TOKENS, stylist.CHAT_MAX_TOKENS)


def test_the_question_asks_for_words_back_and_lines_in_the_owners_voice():
    text = stylist.chat_prompt({"profile": "- I dress plainly.", "talk": "", "say": "I hate ties."})
    assert "- I dress plainly." in text and "I hate ties." in text and "conversation so far" not in text
    assert "`reply`" in text and "`remember`" in text and "The owner is asked before anything is kept." in text
    assert "conversation so far today" in stylist.chat_prompt({"profile": "x", "talk": "- The owner: “a”", "say": "b"})


def test_a_line_kept_from_the_conversation_is_what_the_stylist_reads(chatty):
    [turn] = answered(chatty)["turns"]
    remember(chatty, turn["id"], index=0, save=True)
    conn = db.connect(chatty.cfg.db_path("main"))
    try:
        assert styleprofile.text_for_stylist(conn).endswith("- I run warm, so one layer fewer than most people.")
    finally:
        conn.close()
