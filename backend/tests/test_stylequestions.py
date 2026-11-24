"""The questions the stylist cannot infer (closet/stylequestions.py): asked one at a time, each answer a line of Your
style, a skip remembered, and either taken back."""
import pytest

from closet import stylequestions, styling
from closet.stylequestions import QUESTIONS


def ask(client):
    return client.get("/api/style/talk").json()["question"]


def test_every_question_says_why_and_where_it_is_kept_and_has_a_line_for_each_choice():
    assert len({q.id for q in QUESTIONS}) == len(QUESTIONS) >= 5
    for q in QUESTIONS:
        assert q.ask.endswith("?") and q.why.endswith(".") and q.where and q.lead.endswith(": ")
        assert q.choices and all(label and line.endswith(".") for label, line in q.choices)
        assert "!" not in q.ask + q.why + "".join(line for _, line in q.choices)


def test_the_questions_are_asked_in_order_one_at_a_time(client):
    assert ask(client) == {"id": QUESTIONS[0].id, "ask": QUESTIONS[0].ask, "why": QUESTIONS[0].why,
                           "choices": [c for c, _ in QUESTIONS[0].choices]}


def test_a_choice_becomes_a_line_of_your_style_marked_as_an_answer(client):
    r = client.post("/api/style/questions/warmth", json={"choice": "I run warm"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["line"]["text"] == "- I run warm, so dress me a little lighter than the weather suggests."
    assert body["line"]["source"] == "question" and body["question"]["id"] == QUESTIONS[1].id
    profile = client.get("/api/style/profile").json()
    assert profile["lines"][-1] == body["line"]
    assert profile["text"].endswith("- I run warm, so dress me a little lighter than the weather suggests.")
    assert ask(client)["id"] == QUESTIONS[1].id


def test_an_answer_in_the_owners_own_words_follows_the_questions_lead(client):
    body = client.post("/api/style/questions/colours", json={"text": "  orange,   and bright green "}).json()
    assert body["line"]["text"] == "- Colours I never wear: orange, and bright green"


def test_a_skip_is_remembered_and_the_question_is_not_asked_again(client):
    body = client.post("/api/style/questions/warmth", json={"skip": True}).json()
    assert body == {"line": None, "question": stylequestions.public(QUESTIONS[1])}
    assert client.post("/api/style/questions/warmth", json={"skip": True}).status_code == 200   # twice: the same
    assert ask(client)["id"] == QUESTIONS[1].id
    assert client.get("/api/style/profile").json()["is_default"] is True


def test_undo_takes_the_answer_out_of_your_style_and_asks_again(client):
    client.post("/api/style/questions/warmth", json={"choice": "I feel the cold"})
    r = client.delete("/api/style/questions/warmth")
    assert r.status_code == 200 and r.json()["question"]["id"] == "warmth"
    profile = client.get("/api/style/profile").json()
    assert profile["is_default"] is True and profile["text"] == styling.DEFAULT_PROFILE


def test_undo_of_a_skip_asks_again(client):
    client.post("/api/style/questions/warmth", json={"skip": True})
    assert client.delete("/api/style/questions/warmth").json()["question"]["id"] == "warmth"


def test_when_every_question_is_answered_or_skipped_none_is_asked(client):
    for q in QUESTIONS:
        client.post(f"/api/style/questions/{q.id}", json={"skip": True})
    assert ask(client) is None


def test_once_something_is_said_today_no_question_is_asked(client, cfg):
    from closet import db, wears
    conn = db.connect(cfg.db_path("main"))
    # today as the server takes it (wears.today), not SQLite's own clock, so the two can never disagree
    conn.execute("INSERT INTO style_talk (id, day, said, state, asked_at, created_at) VALUES "
                 "('t', ?, 'Hi.', 'failed', 0, ?)", (wears.today().isoformat(), db.now()))
    conn.close()
    assert ask(client) is None


@pytest.mark.parametrize("body, status, words", [
    ({"choice": "Hot"}, 422, "Choose one of the answers, or write your own."),
    ({"text": "  "}, 422, "Write your answer, or choose one."),
    ({}, 422, "Write your answer, or choose one."),
    ({"text": "x" * 201}, 422, "at most 200 characters"),
])
def test_an_answer_that_is_not_one_is_refused_with_a_sentence(client, body, status, words):
    r = client.post("/api/style/questions/warmth", json=body)
    assert r.status_code == status and words in r.json()["detail"]
    assert ask(client)["id"] == "warmth"


def test_a_question_answered_twice_or_unknown_is_refused(client):
    client.post("/api/style/questions/warmth", json={"choice": "Neither"})
    r = client.post("/api/style/questions/warmth", json={"choice": "Neither"})
    assert r.status_code == 422 and r.json()["detail"] == "You have answered that already."
    assert client.post("/api/style/questions/nope", json={"choice": "x"}).status_code == 404
    assert client.delete("/api/style/questions/nope").status_code == 404
    assert client.post("/api/style/questions/warmth", json=["x"]).status_code == 422

