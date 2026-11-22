"""The conversation about the day's outfits (closet/stylejobs.py, "The conversation" and "Remembering"): the owner
writes to Claude about the outfits on Today (`say`), Claude answers in the background with words, maybe new outfits
and things worth remembering, and the owner says whether to keep each. Claude is always stood in for; the background
job is held and run by the test, and the clock is the test's."""
import json

import pytest

from closet import db, outfits, styleprofile, styling
from closet import today as today_module
from closet.stylejobs import (
    MAX_PER_DAY,
    MESSAGES,
    REFUSED,
    RETRY_S,
    STALE_S,
    TALK_MESSAGES,
    talk_of,
    words_of,
)
from closet.tagger.tagging import CapReached, RouteUnavailable, TaggingError, Unreachable

from . import test_stylejobs as jobs
from .test_stylejobs import DAY, DRIFT_C, TODAY, answers, look_of, number_of, run, today, wardrobe

fixed_today = jobs.fixed_today   # the day is TODAY and the internet is never asked, here too
styled = jobs.styled             # services whose stylist asks the stand-in, with held jobs and the test's clock

NAMES = {"tee": "White tee", "shirt": "Blue oxford", "sweater": "Grey sweater", "chinos": "Navy chinos",
         "jeans": "Dark jeans", "sneakers": "White sneakers", "boots": "Brown boots"}
ONE_MORE = "Something else."   # a message


# ------------------------------------------------------------------ helpers
def ready(styled, **extra):
    """A closet with Claude's outfits on the page: (ids, the Today answer)."""
    ids = wardrobe(styled.c)
    today(styled.c, **extra)
    run(styled)
    body = today(styled.c, **extra)
    assert body["context"]["stylist"]["state"] == "ready", body["context"]["stylist"]
    return ids, body


def say(c, text, **extra):
    return c.post("/api/outfits/today", json={**DAY, "say": text, **extra})


def sent(styled, text="Too dressy.", **extra) -> dict:
    r = say(styled.c, text, **extra)
    assert r.status_code == 200, r.text
    return r.json()


def first_brief(styled) -> dict:
    return styled.stand_in.calls[0][0]


def numbers(brief: dict, o: dict, ids: dict) -> str:
    """An outfit by its pieces' numbers in the brief, as `styling.talk_words` writes it."""
    name_of = {ids[k]: NAMES[k] for k in ids}
    return "; ".join(f"{styling.PLACE_WORDS[pl]} {number_of(brief, name_of[o['pieces'][pl]])}"
                     for pl in outfits.PLACES if o["pieces"].get(pl))


def conn_of(styled):
    return db.connect(styled.cfg.db_path("main"))


def profile_rows(styled) -> list[dict]:
    conn = conn_of(styled)
    try:
        return [dict(r) for r in conn.execute("SELECT text, source FROM style_profile ORDER BY id")]
    finally:
        conn.close()


def wear_notes(styled, item_id: str):
    conn = conn_of(styled)
    try:
        return conn.execute("SELECT wear_notes FROM items WHERE id = ?", (item_id,)).fetchone()["wear_notes"]
    finally:
        conn.close()


def remember(c, answer_id, **body):
    return c.post(f"/api/style/answers/{answer_id}/remember", json=body)


def offered(styled, things=None, setup=None):
    """Claude's outfits on the page, then a message answered with things to remember: (ids, answer id, Today).
    `things` is a function of the first brief giving what Claude offers; `setup(ids)` runs before Today."""
    ids = wardrobe(styled.c)
    if setup:
        setup(ids)
    today(styled.c)
    run(styled)
    brief = first_brief(styled)
    styled.stand_in.remember = (things(brief) if things else
                                [{"about": 0, "text": "I prefer boots to sneakers in autumn."},
                                 {"about": number_of(brief, "White tee"), "text": "Only under a layer."}])
    styled.stand_in.looks = []
    aid = sent(styled, "I'd rather wear boots.")["context"]["stylist"]["answering"]
    run(styled)
    body = today(styled.c)
    assert body["context"]["stylist"]["talk"][-1]["state"] == "ready"
    return ids, aid, body


# ------------------------------------------------------------------ sending
def test_a_message_leaves_the_outfits_on_the_page_while_claude_answers(styled):
    _, before = ready(styled)
    body = sent(styled)
    assert body["outfits"] == before["outfits"]
    st = body["context"]["stylist"]
    assert st["state"] == "ready" and st["id"] == before["context"]["stylist"]["id"]
    assert st["read"] == before["context"]["stylist"]["read"] and st["message"] is None


def test_a_message_is_a_working_turn_whose_id_is_being_answered_and_one_job_is_held(styled):
    ready(styled)
    st = sent(styled)["context"]["stylist"]
    [turn] = st["talk"]
    assert st["answering"] == turn["id"]
    assert turn == {"id": turn["id"], "said": "Too dressy.", "state": "working", "reply": None, "message": None,
                    "remember": [], "at": turn["at"]} and turn["at"]
    assert len(styled.held) == 1 and len(styled.stand_in.calls) == 1
    first, row = answers(styled.cfg)
    assert row["id"] == turn["id"] and row["said"] == "Too dressy." and row["state"] == "working"
    assert row["key"] == first["key"] and row["day"] == TODAY.isoformat()
    assert styled.c.get(f"/api/style/answers/{turn['id']}").json() == {"id": turn["id"], "state": "working",
                                                                      "message": None}


def test_the_space_in_a_message_is_collapsed(styled):
    ready(styled)
    st = sent(styled, "  Swap the sneakers\n\n for   boots ")["context"]["stylist"]
    assert st["talk"][0]["said"] == "Swap the sneakers for boots"
    assert answers(styled.cfg)[-1]["said"] == "Swap the sneakers for boots"
    run(styled)
    assert styled.stand_in.calls[-1][0]["say"] == "Swap the sneakers for boots"


def test_a_message_and_where_the_owner_was_looking_are_not_passed_to_the_engine(styled, monkeypatch):
    ready(styled)
    seen = []
    real = outfits.parse_request

    def spy(data):
        seen.append(dict(data))
        return real(data)

    monkeypatch.setattr(outfits, "parse_request", spy)
    assert sent(styled, looking_at=1)["outfits"]
    assert seen and all("say" not in d and "looking_at" not in d for d in seen)


# ------------------------------------------------------------------ what Claude is told
def test_claude_is_told_the_message_and_the_outfits_on_the_page_in_order_by_their_numbers(styled):
    ids, before = ready(styled)
    sent(styled, "Too dressy.")
    run(styled)
    brief, _ = styled.stand_in.calls[-1]
    assert brief["say"] == "Too dressy."
    shown = before["outfits"]
    assert shown[0].get("by") == "claude" and all("by" not in o for o in shown[1:]) and len(shown) >= 2
    lines = ["The outfits on the owner's screen now, in order (the owner may call them the first, the second and so on):"]
    lines.append(f"- Outfit 1 (yours): {numbers(brief, shown[0], ids)}. You said: “{shown[0]['reasons'][0]}”")
    lines += [f"- Outfit {i} (from the app's rules): {numbers(brief, o, ids)}." for i, o in enumerate(shown[1:], 2)]
    lines += ["What was said today, oldest first:", "- The owner, just now: “Too dressy.”"]
    assert brief["talk"] == "\n".join(lines)
    # the rest of the brief is the day's, as for a plain question
    assert {"guide", "profile", "closet", "day", "worn", "shortlist", "must"} <= set(brief)


def test_claude_is_told_the_earlier_turns_oldest_first_with_its_replies(styled):
    ready(styled)
    styled.stand_in.looks = []
    styled.stand_in.reply = "Fair: here is something plainer."
    sent(styled, "Too dressy.")
    run(styled)
    styled.stand_in.reply = "The navy blazer is in the laundry."
    sent(styled, "Why not the navy blazer?")
    run(styled)
    sent(styled, "Then the boots.")
    run(styled)
    talk = styled.stand_in.calls[-1][0]["talk"]
    said = talk.split("What was said today, oldest first:\n", 1)[1].splitlines()
    assert said == ["- The owner: “Too dressy.”", "- You: “Fair: here is something plainer.”",
                    "- The owner: “Why not the navy blazer?”", "- You: “The navy blazer is in the laundry.”",
                    "- The owner, just now: “Then the boots.”"]


def test_an_unanswered_earlier_turn_is_told_as_not_reaching_the_owner(styled):
    ready(styled)
    styled.stand_in.error = Unreachable("offline")
    sent(styled, "Too dressy.")
    run(styled)
    styled.stand_in.error = None
    sent(styled, "Again: too dressy.")
    run(styled)
    talk = styled.stand_in.calls[-1][0]["talk"]
    assert talk.endswith("- The owner: “Too dressy.”\n- (your answer did not reach them)\n"
                         "- The owner, just now: “Again: too dressy.”")


def test_claude_is_told_which_outfit_was_in_front_of_the_owner(styled):
    ready(styled)
    sent(styled, "Not this one.", looking_at=1)
    run(styled)
    assert styled.stand_in.calls[-1][0]["talk"].endswith("- The owner, just now, with outfit 2 in front of them: "
                                                         "“Not this one.”")


def test_claude_is_told_the_first_outfit_was_in_front_of_the_owner_for_looking_at_zero(styled):
    ready(styled)
    sent(styled, "Not this one.", looking_at=0)
    run(styled)
    assert "with outfit 1 in front of them" in styled.stand_in.calls[-1][0]["talk"]


def test_an_outfit_not_on_the_page_in_front_of_the_owner_is_not_told(styled):
    _, before = ready(styled)
    sent(styled, "Not this one.", looking_at=len(before["outfits"]))
    run(styled)
    talk = styled.stand_in.calls[-1][0]["talk"]
    assert "in front of them" not in talk and talk.endswith("- The owner, just now: “Not this one.”")


def test_a_message_tries_the_api_key_first(styled, monkeypatch):
    ready(styled)
    monkeypatch.setattr(styled.claude, "routes", lambda: ("plan", "api"))
    sent(styled)
    run(styled)
    assert styled.stand_in.calls[-1][1] == ("api", "plan")
    assert answers(styled.cfg)[-1]["route"] == "api"


# ------------------------------------------------------------------ the answer
def test_new_outfits_from_claude_replace_the_ones_on_the_page_claudes_first(styled):
    ids, before = ready(styled)
    styled.stand_in.looks = lambda brief: [
        look_of(brief, "Plainer with boots.", base="White tee", bottom="Navy chinos", shoes="Brown boots"),
        look_of(brief, "The jeans, easy.", base="White tee", bottom="Dark jeans", shoes="Brown boots")]
    styled.stand_in.reply = "Done: the brown boots instead."
    aid = sent(styled, "Swap the sneakers for boots.")["context"]["stylist"]["answering"]
    run(styled)
    assert styled.c.get(f"/api/style/answers/{aid}").json() == {"id": aid, "state": "ready", "message": None}
    body = today(styled.c)
    st = body["context"]["stylist"]
    assert st["state"] == "ready" and st["id"] == aid and st["answering"] is None
    assert st["talk"][0]["state"] == "ready" and st["talk"][0]["reply"] == "Done: the brown boots instead."
    got = body["outfits"]
    assert [o.get("by") for o in got[:2]] == ["claude", "claude"]
    assert [o["reasons"] for o in got[:2]] == [["Plainer with boots."], ["The jeans, easy."]]
    assert [o["pieces"]["shoes"] for o in got[:2]] == [ids["boots"], ids["boots"]]
    assert all("by" not in o for o in got[2:]) and len(got) == len(before["outfits"])
    assert styled.held == []


def test_with_no_outfits_from_claude_the_page_keeps_its_outfits_and_its_line_about_the_day(styled):
    _, before = ready(styled)
    styled.stand_in.looks = []
    styled.stand_in.reply = "The navy blazer is too formal for today."
    aid = sent(styled, "Why not the navy blazer?")["context"]["stylist"]["answering"]
    run(styled)
    body = today(styled.c)
    st = body["context"]["stylist"]
    assert body["outfits"] == before["outfits"]
    assert st["state"] == "ready" and st["id"] == aid and st["read"] == before["context"]["stylist"]["read"]
    assert st["talk"][0]["reply"] == "The navy blazer is too formal for today."
    assert styled.held == []


def test_an_answer_whose_outfits_all_fail_the_check_is_a_failed_turn_and_the_outfits_stand(styled):
    _, before = ready(styled)
    styled.stand_in.looks = lambda brief: [{**look_of(brief, base="White tee", bottom="Navy chinos",
                                                      shoes="Brown boots"), "base": 999}]
    aid = sent(styled)["context"]["stylist"]["answering"]
    run(styled)
    body = today(styled.c)
    st = body["context"]["stylist"]
    assert body["outfits"] == before["outfits"] and st["state"] == "ready"
    assert st["id"] == before["context"]["stylist"]["id"]
    assert st["talk"][0]["state"] == "failed" and st["talk"][0]["message"] == TALK_MESSAGES["answer"]
    assert st["talk"][0]["reply"] is None
    assert answers(styled.cfg)[-1]["error"] == "answer"
    assert styled.c.get(f"/api/style/answers/{aid}").json()["message"] == TALK_MESSAGES["answer"]


@pytest.mark.parametrize("reply", [None, "", "   "])
def test_an_answer_with_no_words_back_is_a_failed_turn(styled, reply):
    _, before = ready(styled)
    styled.stand_in.reply = reply
    sent(styled)
    run(styled)
    body = today(styled.c)
    st = body["context"]["stylist"]
    assert body["outfits"] == before["outfits"]
    assert st["talk"][0]["state"] == "failed" and st["talk"][0]["message"] == TALK_MESSAGES["answer"]
    assert answers(styled.cfg)[-1]["reply"] is None


def test_a_long_reply_is_cut_to_max_reply(styled):
    ready(styled)
    styled.stand_in.reply = "Word  " * styling.MAX_REPLY
    sent(styled)
    run(styled)
    reply = today(styled.c)["context"]["stylist"]["talk"][0]["reply"]
    assert len(reply) == styling.MAX_REPLY and reply == ("Word " * styling.MAX_REPLY)[:styling.MAX_REPLY]


def test_a_turn_records_the_route_model_tokens_and_time(styled):
    ready(styled)
    styled.stand_in.looks = []
    sent(styled)
    run(styled)
    r = answers(styled.cfg)[-1]
    assert r["state"] == "ready" and r["error"] is None and r["reply"] == "Done." and r["remember"] is None
    assert r["route"] == "plan" and r["model"] == "stand-in-model"
    assert r["input_tokens"] == 1200 and r["output_tokens"] == 300
    assert isinstance(r["seconds"], float) and r["seconds"] >= 0 and r["finished_at"]


# ------------------------------------------------------------------ failures
@pytest.mark.parametrize(("error", "why"), [
    (CapReached("over the limit"), "limit"),
    (RouteUnavailable("not signed in"), "unreachable"),
    (Unreachable("offline"), "unreachable"),
    (TaggingError("no answer"), "answer"),
    (ValueError("a bug"), "error"),
])
def test_each_failure_marks_the_turn_failed_with_a_sentence_and_the_outfits_stand(styled, error, why):
    _, before = ready(styled)
    styled.stand_in.error = error
    aid = sent(styled)["context"]["stylist"]["answering"]
    run(styled)
    body = today(styled.c)
    st = body["context"]["stylist"]
    assert body["outfits"] == before["outfits"]
    assert st["state"] == "ready" and st["id"] == before["context"]["stylist"]["id"] and st["answering"] is None
    [turn] = st["talk"]
    assert turn["state"] == "failed" and turn["message"] == TALK_MESSAGES[why] and turn["reply"] is None
    assert styled.c.get(f"/api/style/answers/{aid}").json() == {"id": aid, "state": "failed",
                                                               "message": TALK_MESSAGES[why]}
    # not sent again by itself, however long it waits
    styled.stand_in.error = None
    styled.now["t"] += RETRY_S * 10
    assert today(styled.c)["context"]["stylist"]["state"] == "ready"
    assert styled.held == [] and len(answers(styled.cfg)) == 2


# ------------------------------------------------------------------ refused
def refused(styled, reason_or_sentence, text="Too dressy.", **extra):
    before, held = answers(styled.cfg), len(styled.held)
    r = say(styled.c, text, **extra)
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == REFUSED.get(reason_or_sentence, reason_or_sentence)
    assert answers(styled.cfg) == before and len(styled.held) == held


def test_a_message_is_refused_while_claudes_first_outfits_are_still_being_chosen(styled):
    wardrobe(styled.c)
    today(styled.c)
    refused(styled, "nothing")


def test_a_message_is_refused_when_claude_could_not_choose_outfits(styled):
    wardrobe(styled.c)
    styled.stand_in.error = Unreachable("offline")
    today(styled.c)
    run(styled)
    refused(styled, "nothing")


def test_a_message_is_refused_while_another_is_being_answered(styled):
    ready(styled)
    sent(styled)
    refused(styled, "busy", "And another thing.")


def test_a_message_is_refused_with_no_route_to_claude(styled):
    ready(styled)
    styled.claude.mode = "unavailable"
    refused(styled, "no_route")


def test_a_message_is_refused_at_the_days_limit(styled):
    ready(styled)
    conn = conn_of(styled)
    try:
        for i in range(MAX_PER_DAY - 1):
            conn.execute("INSERT INTO style_answers (id, day, key, state, dressed, asked_at, created_at) "
                         "VALUES (?, ?, 'other', 'failed', '{}', 0, '2026-11-17T08:00:00')", (f"x{i}", TODAY.isoformat()))
    finally:
        conn.close()
    refused(styled, "day_limit")
    assert f"{MAX_PER_DAY} times today" in REFUSED["day_limit"]


def test_messages_count_toward_the_days_limit(styled):
    ready(styled)
    styled.stand_in.looks = []
    for i in range(MAX_PER_DAY - 1):
        sent(styled, f"Message {i}.")
        run(styled)
    assert len(answers(styled.cfg)) == MAX_PER_DAY
    refused(styled, "day_limit")
    body = today(styled.c, ask_again=True)
    assert body["context"]["stylist"]["message"] == MESSAGES["day_limit_kept"] and styled.held == []


@pytest.mark.parametrize("text", ["", "   ", "\n\t "])
def test_an_empty_message_is_refused(styled, text):
    ready(styled)
    refused(styled, "Write what you want to tell Claude about these outfits.", text)


@pytest.mark.parametrize("text", [5, ["Too dressy."], {"text": "Too dressy."}, True])
def test_a_message_that_is_not_text_is_refused(styled, text):
    ready(styled)
    refused(styled, "Write what you want to tell Claude about these outfits.", text)


def test_a_message_longer_than_max_say_is_refused(styled):
    ready(styled)
    long = "x" * (styling.MAX_SAY + 1)
    refused(styled, f"A message to Claude can be at most {styling.MAX_SAY} characters long; this is "
                    f"{styling.MAX_SAY + 1:,}.", long)
    assert sent(styled, "y" * styling.MAX_SAY)["context"]["stylist"]["talk"][0]["said"] == "y" * styling.MAX_SAY


@pytest.mark.parametrize("looking_at", [-1, True, False, "0", 1.0, [0]])
def test_looking_at_must_be_a_place_on_the_page(styled, looking_at):
    ready(styled)
    refused(styled, "looking_at must be the place of the outfit on the page, 0 for the first.", looking_at=looking_at)


NOT_HERE = "Claude isn't choosing your outfits here, so the message wasn't sent."


def test_a_message_is_refused_without_a_stylist(client):
    wardrobe(client)
    r = client.post("/api/outfits/today", json={**DAY, "say": "Too dressy."})
    assert r.status_code == 422 and r.json()["detail"] == NOT_HERE


def test_a_message_is_refused_in_the_demo_closet(styled):
    assert styled.c.post("/api/profile", json={"profile": "demo"}).status_code == 200
    refused(styled, NOT_HERE)
    assert styled.stand_in.calls == []


def test_a_message_is_refused_with_the_stylist_switched_off(styled):
    ready(styled)
    assert styled.c.put("/api/settings", json={"stylist_on": False}).status_code == 200
    refused(styled, NOT_HERE)


# ------------------------------------------------------------------ lost
def test_a_message_lost_when_closet_stopped_is_marked_and_another_can_be_sent(styled):
    _, before = ready(styled)
    aid = sent(styled)["context"]["stylist"]["answering"]
    styled.held.clear()   # the program stopped: the job never ran
    styled.now["t"] += STALE_S - 1
    assert today(styled.c)["context"]["stylist"]["answering"] == aid
    styled.now["t"] += 2
    body = today(styled.c)
    st = body["context"]["stylist"]
    assert body["outfits"] == before["outfits"] and st["state"] == "ready" and st["answering"] is None
    assert st["talk"][0]["state"] == "failed" and st["talk"][0]["message"] == TALK_MESSAGES["lost"]
    lost = answers(styled.cfg)[-1]
    assert lost["id"] == aid and lost["error"] == "lost" and lost["finished_at"]
    assert styled.c.get(f"/api/style/answers/{aid}").json()["message"] == TALK_MESSAGES["lost"]
    assert styled.held == []
    again = sent(styled, ONE_MORE)["context"]["stylist"]
    assert again["answering"] not in (None, aid) and len(styled.held) == 1


def test_a_lost_message_does_not_stop_the_next_one_being_sent_at_once(styled):
    ready(styled)
    aid = sent(styled)["context"]["stylist"]["answering"]
    styled.held.clear()
    styled.now["t"] += STALE_S + 1
    st = sent(styled, ONE_MORE)["context"]["stylist"]
    assert st["answering"] != aid and [t["state"] for t in st["talk"]] == ["failed", "working"]
    assert st["talk"][0]["message"] == TALK_MESSAGES["lost"]


# ------------------------------------------------------------------ the conversation holds for the day
def talked(styled):
    ready(styled)
    styled.stand_in.looks = []
    styled.stand_in.reply = "Plainer it is."
    sent(styled, "Too dressy.")
    run(styled)
    styled.stand_in.looks = None


def assert_plain_with_talk(brief):
    assert "say" not in brief
    assert brief["talk"] == "What was said today, oldest first:\n- The owner: “Too dressy.”\n- You: “Plainer it is.”"
    assert "owner's screen" not in brief["talk"]


def test_asking_again_after_a_turn_tells_claude_what_was_said(styled):
    talked(styled)
    st = today(styled.c, ask_again=True)["context"]["stylist"]
    assert st["state"] == "working" and len(styled.held) == 1
    run(styled)
    assert_plain_with_talk(styled.stand_in.calls[-1][0])


def test_the_weather_moving_after_a_turn_tells_claude_what_was_said(styled):
    talked(styled)
    assert today(styled.c, low_c=8 + DRIFT_C)["context"]["stylist"]["state"] == "working"
    run(styled)
    assert_plain_with_talk(styled.stand_in.calls[-1][0])


def test_another_occasion_after_a_turn_tells_claude_what_was_said(styled):
    talked(styled)
    st = today(styled.c, occasion="smart_casual")["context"]["stylist"]
    assert st["state"] == "working" and len(answers(styled.cfg)) == 3
    run(styled)
    assert_plain_with_talk(styled.stand_in.calls[-1][0])
    assert today(styled.c, occasion="smart_casual")["context"]["stylist"]["talk"][0]["said"] == "Too dressy."


def test_with_no_conversation_a_plain_question_has_no_talk(styled):
    ready(styled)
    today(styled.c, ask_again=True)
    run(styled)
    assert all("talk" not in brief and "say" not in brief for brief, _ in styled.stand_in.calls)


# ------------------------------------------------------------------ talk_of
def test_the_days_talk_is_only_todays_oldest_first_with_things_to_remember_only_when_answered(styled):
    ready(styled)
    conn = conn_of(styled)
    try:
        insert = ("INSERT INTO style_answers (id, day, key, state, dressed, said, reply, remember, error, asked_at, "
                  "created_at) VALUES (?, ?, 'k', ?, '{}', ?, ?, ?, ?, 0, ?)")
        thing = json.dumps([{"kind": "style", "item_id": None, "name": None, "text": "I like grey.", "state": "offered"}])
        conn.execute(insert, ("old", "2026-11-16", "ready", "Yesterday.", "Fine.", thing, None, "2026-11-16T09:00:00"))
        conn.execute(insert, ("b", TODAY.isoformat(), "ready", "Second.", "Two.", thing, None, "2026-11-17T10:00:00"))
        conn.execute(insert, ("a", TODAY.isoformat(), "failed", "First.", "Lost words.", thing, "unreachable",
                              "2026-11-17T09:00:00"))
        conn.execute(insert, ("c", TODAY.isoformat(), "working", "Third.", "Early.", thing, None, "2026-11-17T11:00:00"))
        talk = talk_of(conn, TODAY.isoformat())
    finally:
        conn.close()
    assert [t["id"] for t in talk] == ["a", "b", "c"]
    assert talk[0] == {"id": "a", "said": "First.", "state": "failed", "reply": None,
                       "message": TALK_MESSAGES["unreachable"], "remember": [], "at": "2026-11-17T09:00:00"}
    assert talk[1] == {"id": "b", "said": "Second.", "state": "ready", "reply": "Two.", "message": None,
                       "remember": json.loads(thing), "at": "2026-11-17T10:00:00"}
    assert talk[2]["reply"] is None and talk[2]["remember"] == [] and talk[2]["message"] is None


# ------------------------------------------------------------------ remembering: what is offered
def test_things_offered_are_shaped_by_keeps(styled):
    ids, aid, body = offered(styled, lambda brief: [
        {"about": 0, "text": "  I prefer   boots in autumn. "},
        {"about": 999, "text": "No such piece."},
        {"about": number_of(brief, "White tee"), "text": ""},
        {"about": number_of(brief, "White tee"), "text": "Only under a layer." + "x" * 400},
    ])
    [turn] = body["context"]["stylist"]["talk"]
    assert turn["id"] == aid
    assert turn["remember"] == [
        {"kind": "style", "item_id": None, "name": None, "text": "I prefer boots in autumn.", "state": "offered"},
        {"kind": "piece", "item_id": ids["tee"], "name": "White tee",
         "text": ("Only under a layer." + "x" * 400)[:styling.MAX_NOTE], "state": "offered"}]


def test_at_most_max_keeps_things_are_offered_and_a_duplicate_is_dropped(styled):
    _, _, body = offered(styled, lambda brief: [{"about": 0, "text": "One."}, {"about": 0, "text": "One."},
                                                {"about": 0, "text": "Two."}, {"about": 0, "text": "Three."}])
    assert [k["text"] for k in body["context"]["stylist"]["talk"][0]["remember"]] == ["One.", "Two."][:styling.MAX_KEEPS]


# ------------------------------------------------------------------ remembering: keeping
def test_saving_a_style_thing_with_no_profile_starts_one_from_the_default(styled):
    _, aid, _ = offered(styled)
    r = remember(styled.c, aid, index=0, save=True)
    assert r.status_code == 200, r.text
    assert r.json() == {"kind": "style", "item_id": None, "name": None, "text": "I prefer boots to sneakers in autumn.",
                        "state": "saved"}
    assert profile_rows(styled) == [{"text": f"{styling.DEFAULT_KEPT}\n- I prefer boots to sneakers in autumn.",
                                     "source": "claude"}]
    assert today(styled.c)["context"]["stylist"]["talk"][0]["remember"][0]["state"] == "saved"


def test_saving_a_style_thing_adds_a_line_to_the_owners_profile(styled):
    def setup(ids):
        assert styled.c.put("/api/style/profile", json={"text": "I dress plainly.\n"}).status_code == 200
    _, aid, _ = offered(styled, setup=setup)
    assert remember(styled.c, aid, index=0, save=True).status_code == 200
    assert profile_rows(styled)[-1] == {"text": "I dress plainly.\n- I prefer boots to sneakers in autumn.",
                                        "source": "claude"}
    assert styled.c.get("/api/style/profile").json()["text"] == "I dress plainly.\n- I prefer boots to sneakers in autumn."


def test_saving_a_piece_thing_sets_its_how_i_wear_it_note_when_empty(styled):
    ids, aid, _ = offered(styled)
    r = remember(styled.c, aid, index=1, save=True)
    assert r.status_code == 200, r.text
    assert r.json() == {"kind": "piece", "item_id": ids["tee"], "name": "White tee", "text": "Only under a layer.",
                        "state": "saved"}
    assert wear_notes(styled, ids["tee"]) == "Only under a layer."
    assert profile_rows(styled) == []


def test_saving_a_piece_thing_adds_a_line_to_its_note(styled):
    def setup(ids):
        assert styled.c.patch(f"/api/items/{ids['tee']}", json={"wear_notes": "Tucked in."}).status_code == 200
    ids, aid, _ = offered(styled, setup=setup)
    assert remember(styled.c, aid, index=1, save=True).status_code == 200
    assert wear_notes(styled, ids["tee"]) == "Tucked in.\nOnly under a layer."


def test_a_thing_already_written_is_not_added_twice(styled):
    def setup(ids):
        assert styled.c.put("/api/style/profile", json={
            "text": "- I prefer boots to sneakers in autumn."}).status_code == 200
        assert styled.c.patch(f"/api/items/{ids['tee']}", json={"wear_notes": "Only under a layer."}).status_code == 200
    ids, aid, _ = offered(styled, setup=setup)
    assert remember(styled.c, aid, index=0, save=True).json()["state"] == "saved"
    assert remember(styled.c, aid, index=1, save=True).json()["state"] == "saved"
    assert profile_rows(styled) == [{"text": "- I prefer boots to sneakers in autumn.", "source": "owner"}]
    assert wear_notes(styled, ids["tee"]) == "Only under a layer."


def test_not_keeping_a_thing_marks_it_dismissed_and_changes_nothing_else(styled):
    ids, aid, before = offered(styled)
    rows = answers(styled.cfg)
    for i in (0, 1):
        r = remember(styled.c, aid, index=i, save=False)
        assert r.status_code == 200 and r.json()["state"] == "dismissed"
    assert profile_rows(styled) == [] and wear_notes(styled, ids["tee"]) is None
    after = answers(styled.cfg)
    assert [r["key"] for r in after] == [r["key"] for r in rows]
    assert [k["state"] for k in today(styled.c)["context"]["stylist"]["talk"][0]["remember"]] == ["dismissed",
                                                                                               "dismissed"]


def test_answering_a_thing_a_second_time_changes_nothing(styled):
    ids, aid, _ = offered(styled)
    assert remember(styled.c, aid, index=0, save=True).json()["state"] == "saved"
    assert remember(styled.c, aid, index=1, save=False).json()["state"] == "dismissed"
    profile = profile_rows(styled)
    again = remember(styled.c, aid, index=0, save=False)
    assert again.status_code == 200 and again.json()["state"] == "saved"
    again = remember(styled.c, aid, index=1, save=True)
    assert again.status_code == 200 and again.json()["state"] == "dismissed"
    assert profile_rows(styled) == profile and wear_notes(styled, ids["tee"]) is None


GONE = "That is no longer on the page. Open Today again."


@pytest.mark.parametrize("body", [{"index": 2, "save": True}, {"index": -1, "save": True},
                                  {"index": True, "save": True}, {"save": True}, {"index": "0", "save": True},
                                  {"index": 0.0, "save": True}, {"index": None, "save": True}])
def test_a_wrong_index_is_refused_with_a_sentence(styled, body):
    _, aid, _ = offered(styled)
    r = styled.c.post(f"/api/style/answers/{aid}/remember", json=body)
    assert r.status_code == 422 and r.json()["detail"] == GONE
    assert profile_rows(styled) == []


def test_an_unknown_answer_is_refused_with_a_sentence(styled):
    r = remember(styled.c, "nope", index=0, save=True)
    assert r.status_code == 422 and r.json()["detail"] == GONE


def test_a_plain_answer_has_nothing_to_remember(styled):
    ready(styled)
    aid = answers(styled.cfg)[0]["id"]
    r = remember(styled.c, aid, index=0, save=True)
    assert r.status_code == 422 and r.json()["detail"] == GONE


@pytest.mark.parametrize("body", [{"index": 0}, {"index": 0, "save": "yes"}, {"index": 0, "save": 1},
                                  {"index": 0, "save": None}, [0, True], "save"])
def test_keeping_must_say_true_or_false(styled, body):
    _, aid, _ = offered(styled)
    r = styled.c.post(f"/api/style/answers/{aid}/remember", json=body)
    assert r.status_code == 422
    assert r.json()["detail"] == "Say which thing (index) and whether to keep it (save: true or false)."


def test_keeping_needs_valid_json(styled):
    _, aid, _ = offered(styled)
    r = styled.c.post(f"/api/style/answers/{aid}/remember", content=b"{not json",
                      headers={"content-type": "application/json"})
    assert r.status_code == 400 and r.json()["detail"] == "The request was not valid JSON."


def test_a_profile_that_would_grow_too_long_is_refused_and_nothing_is_kept(styled):
    text = "x" * (styleprofile.MAX_TEXT - 5)

    def setup(ids):
        assert styled.c.put("/api/style/profile", json={"text": text}).status_code == 200
    _, aid, _ = offered(styled, setup=setup)
    r = remember(styled.c, aid, index=0, save=True)
    grown = len(f"{text}\n- I prefer boots to sneakers in autumn.")
    assert r.status_code == 422
    assert r.json()["detail"] == f"Your style can be at most {styleprofile.MAX_TEXT:,} characters long; this is {grown:,}."
    assert profile_rows(styled) == [{"text": text, "source": "owner"}]
    assert today(styled.c)["context"]["stylist"]["talk"][0]["remember"][0]["state"] == "offered"


def test_a_piece_deleted_since_is_refused(styled):
    ids, aid, _ = offered(styled)
    assert styled.c.delete(f"/api/items/{ids['tee']}").status_code == 204
    r = remember(styled.c, aid, index=1, save=True)
    assert r.status_code == 422 and r.json()["detail"] == "That piece is no longer in your closet."


# ------------------------------------------------------------------ keeping does not ask Claude again
def test_saving_does_not_ask_claude_again(styled):
    _, aid, before = offered(styled)
    rows = answers(styled.cfg)
    assert remember(styled.c, aid, index=0, save=True).status_code == 200
    assert remember(styled.c, aid, index=1, save=True).status_code == 200
    body = today(styled.c)
    st = body["context"]["stylist"]
    assert st["state"] == "ready" and st["id"] == before["context"]["stylist"]["id"] and st["answering"] is None
    assert body["outfits"] == before["outfits"]
    assert styled.held == [] and len(answers(styled.cfg)) == len(rows)
    conn = conn_of(styled)
    try:
        words = words_of(today_module.closet_rows(conn), styleprofile.text_for_stylist(conn))
    finally:
        conn.close()
    after = answers(styled.cfg)
    assert all(r["key"].split(":")[1] == words for r in after)
    assert [r["key"].split(":")[0] for r in after] == [r["key"].split(":")[0] for r in rows]
    assert words != rows[0]["key"].split(":")[1]


def test_changing_the_profile_by_hand_after_a_save_still_asks_again(styled):
    _, aid, before = offered(styled)
    assert remember(styled.c, aid, index=0, save=True).status_code == 200
    assert styled.c.put("/api/style/profile", json={"text": "I dress plainly."}).status_code == 200
    st = today(styled.c)["context"]["stylist"]
    assert st["state"] == "working" and st["id"] != before["context"]["stylist"]["id"] and len(styled.held) == 1


def test_changing_a_pieces_note_by_hand_after_a_save_still_asks_again(styled):
    ids, aid, before = offered(styled)
    assert remember(styled.c, aid, index=1, save=True).status_code == 200
    assert styled.c.patch(f"/api/items/{ids['tee']}", json={"wear_notes": "Never tucked."}).status_code == 200
    st = today(styled.c)["context"]["stylist"]
    assert st["state"] == "working" and st["id"] != before["context"]["stylist"]["id"] and len(styled.held) == 1


def test_saving_moves_only_the_days_answers_for_the_words_as_they_were(styled):
    _, aid, _ = offered(styled)
    conn = conn_of(styled)
    try:
        conn.execute("INSERT INTO style_answers (id, day, key, state, dressed, asked_at, created_at) "
                     "VALUES ('yesterday', '2026-11-16', ?, 'ready', '{}', 0, '2026-11-16T08:00:00')",
                     (answers(styled.cfg)[0]["key"],))
        conn.execute("INSERT INTO style_answers (id, day, key, state, dressed, asked_at, created_at) "
                     "VALUES ('other', ?, 'a:b', 'ready', '{}', 0, '2026-11-17T08:00:00')", (TODAY.isoformat(),))
    finally:
        conn.close()
    old = answers(styled.cfg)[0]["key"]
    assert remember(styled.c, aid, index=0, save=True).status_code == 200
    rows = {r["id"]: r for r in answers(styled.cfg)}
    assert rows["yesterday"]["key"] == old and rows["other"]["key"] == "a:b"
    assert rows[aid]["key"] != old


# ------------------------------------------------------------------ the table
def test_a_closet_has_the_three_columns_of_the_conversation(cfg):
    path = cfg.db_path("main")
    path.parent.mkdir(parents=True, exist_ok=True)
    db.migrate(path, cfg.data_dir / "backups")
    conn = db.connect(path)
    try:
        columns = {r["name"]: r for r in conn.execute("PRAGMA table_info(style_answers)")}
    finally:
        conn.close()
    assert {"said", "reply", "remember"} <= set(columns)
    assert all(columns[c]["type"] == "TEXT" and not columns[c]["notnull"] for c in ("said", "reply", "remember"))


# ------------------------------------------------------------------ found in review (each shown failing first)
def test_while_a_message_is_being_answered_asking_again_starts_nothing(styled):
    _, before = ready(styled)
    sent(styled)
    body = today(styled.c, ask_again=True)
    assert len(styled.held) == 1 and len(answers(styled.cfg)) == 2   # the message's job only
    assert body["outfits"] == before["outfits"] and body["context"]["stylist"]["state"] == "ready"


def test_while_a_message_is_being_answered_the_weather_moving_starts_nothing_until_it_is(styled):
    _, before = ready(styled)
    sent(styled)
    body = today(styled.c, low_c=DAY["low_c"] + DRIFT_C)
    assert len(styled.held) == 1 and len(answers(styled.cfg)) == 2
    assert body["context"]["stylist"]["state"] == "ready"
    run(styled)
    today(styled.c, low_c=DAY["low_c"] + DRIFT_C)   # the answer is in: now Claude is asked for the new weather
    assert len(styled.held) == 1 and len(answers(styled.cfg)) == 3
    brief = styled.stand_in.calls[-1][0] if not styled.held else None
    run(styled)
    brief = styled.stand_in.calls[-1][0]
    assert "- You: “Done.”" in brief["talk"] and "did not reach them" not in brief["talk"]


def test_while_a_message_is_being_answered_other_choices_wait_on_it(styled):
    ready(styled)
    aid = sent(styled)["context"]["stylist"]["answering"]
    body = today(styled.c, occasion="smart_casual")
    st = body["context"]["stylist"]
    # nothing new is asked: the page waits on the message, then asks Today again
    assert len(styled.held) == 1 and len(answers(styled.cfg)) == 2
    assert st["state"] == "working" and st["id"] == aid and st["answering"] == aid
    run(styled)
    today(styled.c, occasion="smart_casual")
    assert len(styled.held) == 1 and len(answers(styled.cfg)) == 3


def test_a_thing_that_is_part_of_a_longer_line_is_still_added(styled):
    def setup(ids):
        assert styled.c.put("/api/style/profile", json={"text": "- Shirts untucked."}).status_code == 200
        assert styled.c.patch(f"/api/items/{ids['tee']}", json={"wear_notes": "Never tucked."}).status_code == 200
    ids, aid, _ = offered(styled, setup=setup, things=lambda brief: [
        {"about": 0, "text": "tucked."}, {"about": number_of(brief, "White tee"), "text": "tucked."}])
    assert remember(styled.c, aid, index=0, save=True).json()["state"] == "saved"
    assert remember(styled.c, aid, index=1, save=True).json()["state"] == "saved"
    assert styled.c.get("/api/style/profile").json()["text"] == "- Shirts untucked.\n- tucked."
    assert wear_notes(styled, ids["tee"]) == "Never tucked.\ntucked."


def test_when_keeping_a_thing_fails_part_way_nothing_is_kept(styled, monkeypatch):
    from closet import stylejobs
    _, aid, _ = offered(styled)
    real, calls = stylejobs.words_of, []

    def breaks_the_second_time(rows, profile):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("the disk is full")
        return real(rows, profile)
    monkeypatch.setattr(stylejobs, "words_of", breaks_the_second_time)
    with pytest.raises(RuntimeError):
        remember(styled.c, aid, index=0, save=True)
    monkeypatch.setattr(stylejobs, "words_of", real)
    assert profile_rows(styled) == []   # the profile is as it was
    assert today(styled.c)["context"]["stylist"]["talk"][-1]["remember"][0]["state"] == "offered"


def test_a_message_lost_when_closet_stopped_is_said_so_to_the_page_waiting_on_it(styled):
    ready(styled)
    aid = sent(styled)["context"]["stylist"]["answering"]
    styled.now["t"] += STALE_S + 1
    got = styled.c.get(f"/api/style/answers/{aid}").json()
    assert got == {"id": aid, "state": "failed", "message": TALK_MESSAGES["lost"]}


def test_a_question_lost_when_closet_stopped_is_said_so_to_the_page_waiting_on_it(styled):
    wardrobe(styled.c)
    aid = today(styled.c)["context"]["stylist"]["id"]
    assert styled.c.get(f"/api/style/answers/{aid}").json()["state"] == "working"
    styled.now["t"] += STALE_S + 1
    got = styled.c.get(f"/api/style/answers/{aid}").json()
    assert got == {"id": aid, "state": "failed", "message": MESSAGES["lost"]}


def test_a_thing_about_true_or_false_is_dropped(styled):
    listing = styling.listed([], outfits.parse_request({**DAY, "worn_days_ago": {}})[0])
    assert styling.keeps([{"about": False, "text": "No ties."}, {"about": True, "text": "No ties."},
                          {"about": None, "text": "No hats."}], listing) == [
        {"kind": "style", "item_id": None, "name": None, "text": "No hats.", "state": "offered"}]


# ------------------------------------------------------------------ remembering: taking back
def test_undo_takes_a_style_line_back_out_and_offers_it_again_without_asking_claude(styled):
    _, aid, _ = offered(styled)
    remember(styled.c, aid, index=0, save=True)
    keys = [r["key"] for r in answers(styled.cfg)]
    r = remember(styled.c, aid, index=0, undo=True)
    assert r.status_code == 200 and r.json()["state"] == "offered"
    assert styled.c.get("/api/style/profile").json()["is_default"] is True
    after = answers(styled.cfg)
    assert [r["key"] for r in after] != keys and len(after) == len(keys)   # moved back to the words, not asked again
    assert today(styled.c)["context"]["stylist"]["talk"][0]["remember"][0]["state"] == "offered"
    assert styled.held == []


def test_undo_takes_a_piece_line_back_out_of_its_note(styled):
    def setup(ids):
        assert styled.c.patch(f"/api/items/{ids['tee']}", json={"wear_notes": "Tucked in."}).status_code == 200
    ids, aid, _ = offered(styled, setup=setup)
    remember(styled.c, aid, index=1, save=True)
    assert remember(styled.c, aid, index=1, undo=True).json()["state"] == "offered"
    assert wear_notes(styled, ids["tee"]) == "Tucked in."


def test_undo_of_a_thing_not_kept_changes_nothing(styled):
    _, aid, _ = offered(styled)
    assert remember(styled.c, aid, index=0, undo=True).json()["state"] == "offered"
    remember(styled.c, aid, index=0, save=False)
    assert remember(styled.c, aid, index=0, undo=True).json()["state"] == "dismissed"
    assert profile_rows(styled) == []
