"""Claude's outfits for the day (closet/stylejobs.py): asked for in the background, kept in `style_answers`, and
given to Today ahead of the rules engine's. Claude is always stood in for; the background job is held and run by the
test, and the clock is the test's."""
import dataclasses
import json
import sqlite3
import threading
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from closet import app as app_module
from closet import db, outfits, spend, stylejobs, styling, wears, weather
from closet.stylejobs import DRIFT_C, MAX_PER_DAY, MESSAGES, RETRY_S, STALE_S
from closet.tagger.tagging import CapReached, RouteUnavailable, TaggingError, Unreachable

from .conftest import fake_cutter, upload

TODAY = date(2026, 11, 17)
DAY = {"low_c": 8, "high_c": 14, "rain": False}   # the whole day given: no forecast is looked up
WORDS_TO_PLACE = {words: place for place, words in styling.PLACE_WORDS.items()}


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(wears, "today", lambda: TODAY)

    def no_network(url):
        raise AssertionError(f"tests never ask the internet ({url})")

    monkeypatch.setattr(weather, "fetch", no_network)


# ------------------------------------------------------------------ the stand-in for Claude
def shortlist_looks(brief: dict) -> list[dict]:
    """The engine's shortlist in the brief ("- base 2; bottom 5; shoes 7; accessories 9"), as looks Claude could give."""
    found = []
    for line in brief["shortlist"].splitlines():
        if not line.startswith("- ") or "found no outfit" in line:
            continue
        look = {"base": 0, "mid": 0, "outer": 0, "bottom": 0, "shoes": 0, "accessories": [],
                "why": f"Outfit {len(found) + 1} suits the day.", "watch": ""}
        for part in line[2:].split("; "):
            words, number = part.rsplit(" ", 1) if not part.startswith("accessories") else ("accessories", None)
            if number is None:
                look["accessories"] = [int(n) for n in part.removeprefix("accessories ").split(", ")]
            else:
                look[WORDS_TO_PLACE[words]] = int(number)
        found.append(look)
    return found


def number_of(brief: dict, name: str) -> int:
    """A piece's number in the brief's closet, by its name."""
    for line in brief["closet"].splitlines():
        n, rest = line.split(". ", 1)
        if rest.split(" | ")[0] == name:
            return int(n)
    raise AssertionError(f"{name} is not in the brief")


def look_of(brief: dict, why="It works.", **names) -> dict:
    """A look by the pieces' names: look_of(brief, base="White tee", bottom="Navy chinos", shoes="White sneakers")."""
    look = {"base": 0, "mid": 0, "outer": 0, "bottom": 0, "shoes": 0, "accessories": [], "why": why, "watch": ""}
    for place, name in names.items():
        look[place] = number_of(brief, name)
    return look


class StandIn:
    """Stands in for Claude choosing outfits. By default it gives the engine's first shortlisted outfit; `looks`
    (a list, or a function of the brief) changes that and `error` is raised instead. `calls` holds (brief, routes).
    A message of the owner's (`say` in the brief) is answered with `reply` and `remember` as well."""

    def __init__(self):
        self.calls: list[tuple[dict, tuple[str, ...]]] = []
        self.looks = None
        self.error: Exception | None = None
        self.read = "A cool, dry day: a layer helps."
        self.reply: str | None = "Done."
        self.remember: list = []

    def __call__(self, brief: dict, routes: tuple[str, ...]) -> dict:
        self.calls.append((brief, routes))
        if self.error is not None:
            raise self.error
        looks = (self.looks(brief) if callable(self.looks) else self.looks if self.looks is not None
                 else shortlist_looks(brief)[:1])
        got = {"looks": looks, "read": self.read, "route": routes[0], "model": "stand-in-model",
               "input_tokens": 1200, "output_tokens": 300}
        if brief.get("say"):
            got.update(read=None, reply=self.reply, remember=self.remember)
        return got


@pytest.fixture
def styled(cfg, claude):
    """Services with a stylist that asks the stand-in; its jobs are held (`held`) until the test runs them, and its
    clock is `now["t"]`."""
    claude.mode = "answers"
    stand_in = StandIn()
    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, tagger=claude, routes=lambda: claude.routes(),
                                   corrector=claude.correct, stylist_ask=stand_in)
    held: list = []
    now = {"t": 1_800_000_000.0}
    sv.stylist.start = held.append
    sv.stylist.clock = lambda: now["t"]
    anon = TestClient(app_module.create_app(sv))
    yield SimpleNamespace(c=anon, sv=sv, stand_in=stand_in, held=held, now=now, cfg=cfg, claude=claude)
    sv.stop()


def make_item(c, key, name, category, color, **more):
    r = upload(c, key=key)
    assert r.status_code == 201, r.text
    iid = r.json()["id"]
    r = c.patch(f"/api/items/{iid}", json={"name": name, "category": category, "color": color, **more})
    assert r.status_code == 200, r.text
    return iid


def wardrobe(c, shoes=True) -> dict[str, str]:
    """A small closet that dresses a cool day several ways."""
    ids = {
        "tee": make_item(c, "tee", "White tee", "tee", "white", formality="casual"),
        "shirt": make_item(c, "shirt", "Blue oxford", "shirt", "light_blue"),
        "sweater": make_item(c, "sweater", "Grey sweater", "sweater", "grey", formality="casual"),
        "chinos": make_item(c, "chinos", "Navy chinos", "trousers", "navy", formality="casual"),
        "jeans": make_item(c, "jeans", "Dark jeans", "jeans", "navy", formality="casual"),
    }
    if shoes:
        ids["sneakers"] = make_item(c, "sneakers", "White sneakers", "sneakers", "white", formality="casual")
        ids["boots"] = make_item(c, "boots", "Brown boots", "boots", "brown", formality="casual")
    return ids


def today(c, **extra) -> dict:
    r = c.post("/api/outfits/today", json={**DAY, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def run(env) -> None:
    """Runs every held job, oldest first."""
    while env.held:
        env.held.pop(0)()


def answers(cfg) -> list[dict]:
    conn = db.connect(cfg.db_path("main"))
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM style_answers ORDER BY created_at, rowid")]
    finally:
        conn.close()


def core(o: dict) -> tuple:
    return tuple(o["pieces"].get(pl) for pl in outfits.PLACES)


# ------------------------------------------------------------------ key_of
def row(id, **more):
    r = {"id": id, "name": id, "category": "tee", "laundry": "clean", "wear_notes": None, "notes": None,
         "fit_notes": None, "rating": None}
    r.update(more)
    return r


NOTE = {"text": "Office day", "from": "2026-11-17", "to": "2026-11-17", "active": True}


def key(day="2026-11-17", context=None, ctx=None, rows=None, profile="I like navy."):
    context = {"place": "Lisbon", "note": NOTE} if context is None else context
    ctx = outfits.parse_request(DAY)[0] if ctx is None else ctx
    rows = [row("a"), row("b", notes="Runs small")] if rows is None else rows
    return stylejobs.key_of(day, context, ctx, rows, profile)


def test_the_same_choices_give_the_same_key_of_two_hashes_the_choices_then_the_owners_words():
    assert key() == key()
    choices, words = key().split(":")
    assert len(choices) == 64 and len(words) == 64
    assert words == stylejobs.words_of([row("a"), row("b", notes="Runs small")], "I like navy.")


def test_the_key_changes_with_every_choice_and_word_claude_is_told():
    base = outfits.parse_request(DAY)[0]
    changed = [
        key(day="2026-11-18"),
        key(context={"place": "Porto", "note": NOTE}),
        key(ctx=dataclasses.replace(base, occasion="business")),
        key(ctx=dataclasses.replace(base, mood="sharp")),
        key(ctx=dataclasses.replace(base, build_around="a")),
        key(ctx=dataclasses.replace(base, leave_out=("b",))),
        key(ctx=dataclasses.replace(base, keep=("a",))),
        key(context={"place": "Lisbon", "note": {**NOTE, "text": "Dinner out"}}),
        key(context={"place": "Lisbon", "note": {**NOTE, "from": "2026-11-16"}}),
        key(context={"place": "Lisbon", "note": {**NOTE, "to": "2026-11-18"}}),
        key(profile="I like grey."),
        key(rows=[row("a", wear_notes="Tucked in"), row("b", notes="Runs small")]),
        key(rows=[row("a", notes="Soft"), row("b", notes="Runs small")]),
        key(rows=[row("a", fit_notes="Short in the arms"), row("b", notes="Runs small")]),
        key(rows=[row("a", rating="love"), row("b", notes="Runs small")]),
        key(rows=[row("a"), row("b", notes="Runs large")]),
    ]
    assert key() not in changed
    assert len(set(changed)) == len(changed)


def test_the_key_does_not_change_with_the_weather_the_laundry_a_plain_new_piece_or_a_note_still_to_come():
    base = outfits.parse_request(DAY)[0]
    assert key(ctx=dataclasses.replace(base, low_c=-5, high_c=30, rain=True)) == key()
    assert key(rows=[row("a", laundry="laundry"), row("b", notes="Runs small", laundry="laundry")]) == key()
    assert key(rows=[row("a"), row("b", notes="Runs small"), row("c")]) == key()
    coming = {"text": "Wedding", "from": "2026-11-20", "to": "2026-11-20", "active": False}
    assert key(context={"place": "Lisbon", "note": coming}) == key(context={"place": "Lisbon", "note": None})
    assert (key(context={"place": "Lisbon", "note": coming})
            == key(context={"place": "Lisbon", "note": {**coming, "text": "Funeral"}}))


# ------------------------------------------------------------------ drifted
def test_the_weather_drifts_by_drift_c_degrees_or_when_the_rain_comes_or_goes():
    ctx = outfits.parse_request(DAY)[0]
    asked = {"low_c": 8, "high_c": 14, "rain": False}
    near = DRIFT_C - 0.1
    for low, high in ((8 + near, 14), (8 - near, 14), (8, 14 + near), (8, 14 - near)):
        assert not stylejobs.drifted({**asked, "low_c": low, "high_c": high}, ctx), (low, high)
    for low, high in ((8 + DRIFT_C, 14), (8 - DRIFT_C, 14), (8, 14 + DRIFT_C), (8, 14 - DRIFT_C)):
        assert stylejobs.drifted({**asked, "low_c": low, "high_c": high}, ctx), (low, high)
    assert stylejobs.drifted({**asked, "rain": True}, ctx)
    assert stylejobs.drifted(asked, dataclasses.replace(ctx, rain=True))
    assert not stylejobs.drifted(asked, ctx)


def test_a_missing_or_unreadable_day_counts_as_drifted():
    ctx = outfits.parse_request(DAY)[0]
    for dressed in (None, "8 to 14", {}, {"low_c": 8, "high_c": 14}, {"low_c": "cold", "high_c": 14, "rain": False},
                    {"low_c": None, "high_c": 14, "rain": False}):
        assert stylejobs.drifted(dressed, ctx), dressed


# ------------------------------------------------------------------ wearable, merged, public
def outfit(base, bottom="b", shoes="s", mid=None, outer=None, accessories=(), **more):
    return {"pieces": {"base": base, "mid": mid, "outer": outer, "bottom": bottom, "shoes": shoes,
                       "accessories": list(accessories)}, **more}


def test_an_outfit_is_wearable_only_when_every_piece_and_accessory_can_be_worn():
    ids = {"t", "m", "b", "s", "belt"}
    good = outfit("t", mid="m", accessories=["belt"])
    washed = outfit("t", mid="gone")
    lost_belt = outfit("t", accessories=["scarf"])
    empty = {"pieces": {}}
    no_pieces = {"score": 3}
    assert stylejobs.wearable([good, washed, lost_belt, empty, no_pieces, "t", None, 3], ids) == [good]
    assert stylejobs.wearable([], ids) == []


def test_claudes_outfits_come_first_then_the_engines_that_differ_up_to_the_count():
    claude = [outfit("t1", by="claude"), outfit("t2", by="claude")]
    engine = [outfit("t1", accessories=["belt"], score=80), outfit("t3", score=70), outfit("t4", score=60)]
    out = stylejobs.merged(claude, engine, 3)
    assert out == [claude[0], claude[1], engine[1]]   # an accessory alone does not make the engine's first differ
    assert stylejobs.merged(claude, engine, 10) == [claude[0], claude[1], engine[1], engine[2]]
    assert stylejobs.merged(claude, engine, 0) == [claude[0]]
    assert stylejobs.merged(claude, engine, -2) == [claude[0]]
    assert stylejobs.merged([], engine, 2) == engine[:2]


def test_today_is_told_the_state_id_read_message_talk_and_what_is_being_answered_but_not_the_outfits():
    assert stylejobs.public(None) is None
    found = {"state": "ready", "id": "x", "outfits": [outfit("t")], "read": "Cold.", "message": None}
    assert stylejobs.public(found) == {"state": "ready", "id": "x", "read": "Cold.", "message": None, "talk": [],
                                       "answering": None}
    turn = {"id": "y", "said": "Too dressy.", "state": "working", "reply": None, "message": None, "remember": [],
            "at": "now"}
    assert stylejobs.public({**found, "talk": [turn], "answering": "y"}) == {
        "state": "ready", "id": "x", "read": "Cold.", "message": None, "talk": [turn], "answering": "y"}


# ------------------------------------------------------------------ through Today
def test_the_first_request_gives_the_engines_outfits_at_once_and_starts_one_question(styled):
    wardrobe(styled.c)
    body = today(styled.c)
    st = body["context"]["stylist"]
    assert st["state"] == "working" and st["id"] and st["read"] is None and st["message"] is None
    assert body["outfits"] and all("by" not in o for o in body["outfits"])
    assert len(styled.held) == 1 and styled.stand_in.calls == []
    assert styled.c.get(f"/api/style/answers/{st['id']}").json() == {"id": st["id"], "state": "working", "message": None}
    [r] = answers(styled.cfg)
    assert r["id"] == st["id"] and r["day"] == TODAY.isoformat() and r["state"] == "working"
    assert json.loads(r["dressed"]) == {"low_c": 8, "high_c": 14, "rain": False}


def test_a_second_request_while_claude_is_choosing_starts_nothing_new(styled):
    wardrobe(styled.c)
    first = today(styled.c)["context"]["stylist"]
    second = today(styled.c)["context"]["stylist"]
    assert second == first and len(styled.held) == 1 and len(answers(styled.cfg)) == 1


def test_claudes_outfits_come_first_once_ready_then_the_engines_that_differ(styled):
    ids = wardrobe(styled.c)
    styled.stand_in.looks = lambda brief: [
        look_of(brief, "The oxford smartens the jeans.", base="Blue oxford", mid="Grey sweater", bottom="Dark jeans",
                shoes="Brown boots"),
        look_of(brief, "Easy and warm.", base="White tee", mid="Grey sweater", bottom="Navy chinos",
                shoes="White sneakers")]
    first = today(styled.c, count=4)
    engine = first["outfits"]
    run(styled)
    aid = first["context"]["stylist"]["id"]
    assert styled.c.get(f"/api/style/answers/{aid}").json() == {"id": aid, "state": "ready", "message": None}
    body = today(styled.c, count=4)
    st = body["context"]["stylist"]
    assert st == {"state": "ready", "id": aid, "read": "A cool, dry day: a layer helps.", "message": None,
                  "talk": [], "answering": None}
    got = body["outfits"]
    assert [o.get("by") for o in got[:2]] == ["claude", "claude"]
    assert got[0]["pieces"] == {"base": ids["shirt"], "mid": ids["sweater"], "outer": None, "bottom": ids["jeans"],
                                "shoes": ids["boots"], "accessories": []}
    assert got[0]["score"] is None and got[0]["reasons"] == ["The oxford smartens the jeans."]
    assert got[1]["reasons"] == ["Easy and warm."] and got[1]["pieces"]["base"] == ids["tee"]
    assert len(got) == 4
    rest = got[2:]
    assert all("by" not in o for o in rest)
    assert {core(o) for o in rest}.isdisjoint({core(o) for o in got[:2]})
    assert [core(o) for o in rest] == [core(o) for o in engine if core(o) not in {core(x) for x in got[:2]}][:2]
    assert len(styled.stand_in.calls) == 1


def test_the_brief_reflects_the_request_and_the_api_key_is_tried_first(styled, monkeypatch):
    ids = wardrobe(styled.c)
    assert styled.c.patch(f"/api/items/{ids['jeans']}", json={"wear_notes": "Cuffed twice"}).status_code == 200
    assert styled.c.put("/api/style/profile", json={"text": "I dress plainly and like navy."}).status_code == 200
    monkeypatch.setattr(styled.claude, "routes", lambda: ("plan", "api"))
    today(styled.c, occasion="smart_casual")
    run(styled)
    [(brief, routes)] = styled.stand_in.calls
    assert set(brief) == {"guide", "profile", "closet", "day", "worn", "shortlist", "must"}
    assert "smart casual" in brief["day"].lower()
    assert brief["profile"] == "I dress plainly and like navy."
    assert "Cuffed twice" in brief["closet"]
    assert routes == ("api", "plan")


def test_an_outfit_claude_gives_that_cannot_be_worn_is_left_out_and_the_others_kept(styled):
    wardrobe(styled.c)
    styled.stand_in.looks = lambda brief: [shortlist_looks(brief)[0], {**shortlist_looks(brief)[0], "base": 999}]
    today(styled.c)
    run(styled)
    body = today(styled.c)
    assert body["context"]["stylist"]["state"] == "ready"
    assert [o.get("by") for o in body["outfits"]].count("claude") == 1
    [r] = answers(styled.cfg)
    assert json.loads(r["problems"]) == ["Outfit 2 was left out: 999 is not a piece in the list."]
    assert len(json.loads(r["outfits"])) == 1


def test_when_no_outfit_claude_gives_can_be_worn_the_engines_stand(styled):
    wardrobe(styled.c)
    styled.stand_in.looks = lambda brief: [{**shortlist_looks(brief)[0], "base": 999}]
    engine = today(styled.c)["outfits"]
    run(styled)
    body = today(styled.c)
    st = body["context"]["stylist"]
    assert st["state"] == "failed" and st["message"] == MESSAGES["answer"] and "gave no outfit" in st["message"]
    assert body["outfits"] == engine
    assert styled.c.get(f"/api/style/answers/{st['id']}").json()["message"] == MESSAGES["answer"]


@pytest.mark.parametrize(("error", "said"), [
    (CapReached("over the limit"), "spending limit"),
    (RouteUnavailable("not signed in"), "couldn't be reached"),
    (Unreachable("offline"), "couldn't be reached"),
    (TaggingError("no answer"), "gave no outfit"),
    (ValueError("a bug"), "Something went wrong"),
])
def test_each_failure_of_claude_gives_a_sentence_and_the_engines_outfits(styled, error, said):
    wardrobe(styled.c)
    styled.stand_in.error = error
    engine = today(styled.c)["outfits"]
    run(styled)
    body = today(styled.c)
    st = body["context"]["stylist"]
    assert st["state"] == "failed" and said in st["message"], st
    assert body["outfits"] == engine
    assert [r["state"] for r in answers(styled.cfg)] == ["failed"]
    assert styled.held == []


def test_with_no_route_to_claude_nothing_is_asked_and_why_is_said(styled):
    wardrobe(styled.c)
    styled.claude.mode = "unavailable"
    body = today(styled.c)
    st = body["context"]["stylist"]
    assert st == {"state": "failed", "id": None, "read": None, "message": MESSAGES["no_route"], "talk": [],
                  "answering": None}
    assert "can't be reached right now" in st["message"] and body["outfits"]
    assert answers(styled.cfg) == [] and styled.held == [] and styled.stand_in.calls == []


def test_a_failed_answer_is_asked_again_only_after_retry_s(styled):
    wardrobe(styled.c)
    styled.stand_in.error = Unreachable("offline")
    first = today(styled.c)["context"]["stylist"]["id"]
    run(styled)
    styled.stand_in.error = None
    styled.now["t"] += RETRY_S - 1
    st = today(styled.c)["context"]["stylist"]
    assert st["state"] == "failed" and st["id"] == first and styled.held == []
    styled.now["t"] += 1
    st = today(styled.c)["context"]["stylist"]
    assert st["state"] == "working" and st["id"] != first and len(styled.held) == 1
    run(styled)
    assert today(styled.c)["context"]["stylist"]["state"] == "ready"
    assert len(styled.stand_in.calls) == 2


def test_a_question_lost_when_closet_stopped_is_marked_and_asked_again(styled):
    wardrobe(styled.c)
    first = today(styled.c)["context"]["stylist"]["id"]
    styled.now["t"] += STALE_S - 1
    assert today(styled.c)["context"]["stylist"]["id"] == first and len(styled.held) == 1
    styled.now["t"] += 2
    st = today(styled.c)["context"]["stylist"]
    assert st["state"] == "working" and st["id"] != first and len(styled.held) == 2
    lost, new = answers(styled.cfg)
    assert lost["id"] == first and lost["state"] == "failed" and lost["error"] == "lost" and lost["finished_at"]
    assert new["id"] == st["id"] and new["state"] == "working"
    assert styled.c.get(f"/api/style/answers/{first}").json()["message"] == MESSAGES["lost"]


def test_a_lost_question_is_asked_again_at_once_however_long_a_failure_waits(styled, monkeypatch):
    # found by review: it was only asked again because STALE_S and RETRY_S happened to be the same
    monkeypatch.setattr(stylejobs, "RETRY_S", STALE_S * 10)
    wardrobe(styled.c)
    first = today(styled.c)["context"]["stylist"]["id"]
    styled.now["t"] += STALE_S + 1
    st = today(styled.c)["context"]["stylist"]
    assert st["state"] == "working" and st["id"] != first and len(styled.held) == 2


def test_the_thread_does_not_overwrite_an_answer_already_given_up_on(styled):
    wardrobe(styled.c)
    first = today(styled.c)["context"]["stylist"]["id"]
    lost_job = styled.held.pop(0)
    styled.now["t"] += STALE_S + 1
    today(styled.c)      # marks the first lost and asks again
    lost_job()           # the first thread finishes late
    rows = {r["id"]: r for r in answers(styled.cfg)}
    assert rows[first]["state"] == "failed" and rows[first]["error"] == "lost" and rows[first]["outfits"] is None


def test_the_question_records_the_route_model_tokens_and_time(styled):
    wardrobe(styled.c)
    today(styled.c)
    run(styled)
    [r] = answers(styled.cfg)
    assert r["state"] == "ready" and r["error"] is None
    assert r["route"] == "plan" and r["model"] == "stand-in-model"
    assert r["input_tokens"] == 1200 and r["output_tokens"] == 300
    assert isinstance(r["seconds"], float) and r["seconds"] >= 0 and r["finished_at"]
    assert r["read"] == "A cool, dry day: a layer helps." and json.loads(r["problems"]) == []
    assert all(o["by"] == "claude" for o in json.loads(r["outfits"]))


def test_a_ready_answer_serves_the_same_choices_all_day_and_each_choice_has_its_own(styled):
    wardrobe(styled.c)
    first = today(styled.c)["context"]["stylist"]["id"]
    run(styled)
    make_item(styled.c, "belt", "Brown belt", "belt", "brown")   # a piece added during the day does not ask again
    styled.now["t"] += 6 * 3600
    st = today(styled.c)["context"]["stylist"]
    assert st["state"] == "ready" and st["id"] == first and styled.held == []
    other = today(styled.c, mood="relaxed")["context"]["stylist"]
    assert other["state"] == "working" and other["id"] != first and len(styled.held) == 1
    run(styled)
    back = today(styled.c)["context"]["stylist"]
    assert back["state"] == "ready" and back["id"] == first and styled.held == []
    assert today(styled.c, mood="relaxed")["context"]["stylist"]["id"] == other["id"]
    assert len(styled.stand_in.calls) == 2


@pytest.mark.parametrize("change", [{"low_c": 8 + DRIFT_C}, {"high_c": 14 - DRIFT_C}, {"rain": True}])
def test_the_weather_moving_far_asks_again(styled, change):
    wardrobe(styled.c)
    first = today(styled.c)["context"]["stylist"]["id"]
    run(styled)
    st = today(styled.c, **change)["context"]["stylist"]
    assert st["state"] == "working" and st["id"] != first and len(styled.held) == 1


def test_the_weather_moving_a_little_does_not_ask_again(styled):
    wardrobe(styled.c)
    first = today(styled.c)["context"]["stylist"]["id"]
    run(styled)
    near = DRIFT_C - 0.5
    st = today(styled.c, low_c=8 + near, high_c=14 - near)["context"]["stylist"]
    assert st["state"] == "ready" and st["id"] == first and styled.held == []


def test_an_outfit_whose_piece_went_in_the_laundry_is_no_longer_given_and_claude_is_asked_again_when_none_is_left(styled):
    ids = wardrobe(styled.c)
    make_item(styled.c, "polo", "Navy polo", "polo", "navy", formality="casual")   # still dresses the owner after both
    styled.stand_in.looks = lambda brief: [
        look_of(brief, base="Blue oxford", bottom="Dark jeans", shoes="Brown boots"),
        look_of(brief, base="White tee", bottom="Navy chinos", shoes="White sneakers")]
    first = today(styled.c)["context"]["stylist"]["id"]
    run(styled)
    assert wears.LAUNDRY == ("clean", "laundry")
    assert styled.c.post(f"/api/items/{ids['shirt']}/laundry", json={"state": "laundry"}).status_code == 200
    body = today(styled.c)
    assert body["context"]["stylist"]["state"] == "ready" and body["context"]["stylist"]["id"] == first
    mine = [o for o in body["outfits"] if o.get("by") == "claude"]
    assert [o["pieces"]["base"] for o in mine] == [ids["tee"]]
    assert all(ids["shirt"] not in core(o) for o in body["outfits"])
    assert styled.held == []
    assert styled.c.post(f"/api/items/{ids['tee']}/laundry", json={"state": "laundry"}).status_code == 200
    st = today(styled.c)["context"]["stylist"]
    assert st["state"] == "working" and st["id"] != first and len(styled.held) == 1


def wear_first(styled, body):
    o = body["outfits"][0]
    pieces = o["pieces"]
    item_ids = [pieces[pl] for pl in outfits.PLACES if pieces.get(pl)]
    r = styled.c.post("/api/wears", json={"item_ids": item_ids, "outfit": {
        "pieces": pieces, "context": {**DAY, "occasion": "casual", "mood": "usual"}, "score": o.get("score"),
        "reasons": o.get("reasons") or [], "warnings": o.get("warnings") or []}})
    assert r.status_code == 201, r.text


def test_once_an_outfit_is_worn_today_drift_does_not_ask_again_but_the_owner_still_can(styled):
    wardrobe(styled.c)
    first = today(styled.c)["context"]["stylist"]["id"]
    run(styled)
    wear_first(styled, today(styled.c))
    st = today(styled.c, low_c=8 + 2 * DRIFT_C, rain=True)["context"]["stylist"]
    # the outfit worn was Claude's only one, so its top is in the laundry: nothing of Claude's is left to show, and
    # still nothing is asked
    assert st["id"] == first and st["message"] == MESSAGES["gone"] and styled.held == []
    st = today(styled.c, low_c=8 + 2 * DRIFT_C, rain=True, ask_again=True)["context"]["stylist"]
    assert st["state"] == "working" and st["id"] != first and len(styled.held) == 1


def test_claudes_outfits_that_can_no_longer_be_worn_are_said_so_and_not_passed_off_as_ready(styled):
    # found by review: after wearing Claude's only outfit its top is in the laundry; Today then said "ready" with
    # Claude's line about the day over outfits that were all the rules'
    wardrobe(styled.c)
    first = today(styled.c)["context"]["stylist"]["id"]
    run(styled)
    body = today(styled.c)
    assert body["outfits"][0].get("by") == "claude"
    wear_first(styled, body)
    after = today(styled.c)
    assert after["context"]["stylist"] == {"state": "failed", "id": first, "read": None, "message": MESSAGES["gone"],
                                           "talk": [], "answering": None}
    assert "can no longer be worn" in MESSAGES["gone"]
    assert after["outfits"] and not any(o.get("by") == "claude" for o in after["outfits"]) and styled.held == []


def test_once_an_outfit_is_worn_today_a_failure_is_not_retried_by_itself(styled):
    wardrobe(styled.c)
    styled.stand_in.error = Unreachable("offline")
    first = today(styled.c)["context"]["stylist"]["id"]
    run(styled)
    wear_first(styled, today(styled.c))
    styled.now["t"] += RETRY_S * 10
    st = today(styled.c)["context"]["stylist"]
    assert st["state"] == "failed" and st["id"] == first and styled.held == []
    styled.stand_in.error = None
    st = today(styled.c, ask_again=True)["context"]["stylist"]
    assert st["state"] == "working" and len(styled.held) == 1


def test_ask_again_starts_a_new_question_even_when_an_answer_is_ready(styled):
    wardrobe(styled.c)
    first = today(styled.c)["context"]["stylist"]["id"]
    run(styled)
    st = today(styled.c, ask_again=True)["context"]["stylist"]
    assert st["state"] == "working" and st["id"] != first and len(styled.held) == 1
    assert today(styled.c, ask_again=False)["context"]["stylist"]["id"] == st["id"]   # still choosing: no third


def test_ask_again_must_be_true_or_false(styled):
    wardrobe(styled.c)
    for bad in ("yes", 1, [True]):
        r = styled.c.post("/api/outfits/today", json={**DAY, "ask_again": bad})
        assert r.status_code == 422 and r.json()["detail"] == "ask_again must be true or false."
    assert answers(styled.cfg) == []


def test_ask_again_is_not_passed_to_the_engine(styled, monkeypatch):
    wardrobe(styled.c)
    seen = []
    real = outfits.parse_request

    def spy(data):
        seen.append(dict(data))
        return real(data)

    monkeypatch.setattr(outfits, "parse_request", spy)
    assert today(styled.c, ask_again=True)["outfits"]
    assert seen and all("ask_again" not in d for d in seen)


def test_claude_is_asked_at_most_max_per_day_times_a_day(styled):
    wardrobe(styled.c)
    today(styled.c)
    run(styled)
    for _ in range(MAX_PER_DAY - 1):
        assert today(styled.c, ask_again=True)["context"]["stylist"]["state"] == "working"
        run(styled)
    assert len(answers(styled.cfg)) == MAX_PER_DAY and len(styled.stand_in.calls) == MAX_PER_DAY
    newest = answers(styled.cfg)[-1]["id"]
    body = today(styled.c, ask_again=True)   # one more: the kept answer still stands
    assert body["context"]["stylist"]["state"] == "ready" and body["context"]["stylist"]["id"] == newest
    # and the owner is told why asking again changed nothing
    assert body["context"]["stylist"]["message"] == MESSAGES["day_limit_kept"]
    assert f"{MAX_PER_DAY} times today" in MESSAGES["day_limit_kept"]
    assert today(styled.c)["context"]["stylist"]["message"] is None   # only said when asked again
    assert any(o.get("by") == "claude" for o in body["outfits"])
    assert styled.held == [] and len(answers(styled.cfg)) == MAX_PER_DAY
    mine = next(o for o in body["outfits"] if o.get("by") == "claude")
    # with none of Claude's outfits wearable any more, the day's questions are used up
    assert styled.c.post(f"/api/items/{mine['pieces']['base']}/laundry", json={"state": "laundry"}).status_code == 200
    st = today(styled.c)["context"]["stylist"]
    assert st == {"state": "failed", "id": None, "read": None, "message": MESSAGES["day_limit"], "talk": [],
                  "answering": None}
    assert f"{MAX_PER_DAY} times today" in st["message"]
    assert styled.held == [] and len(styled.stand_in.calls) == MAX_PER_DAY


def test_the_day_limit_counts_only_todays_questions(styled):
    wardrobe(styled.c)
    conn = db.connect(styled.cfg.db_path("main"))
    for i in range(MAX_PER_DAY):
        conn.execute("INSERT INTO style_answers (id, day, key, state, dressed, asked_at, created_at) "
                     "VALUES (?, '2026-11-16', 'k', 'failed', '{}', 0, '2026-11-16T08:00:00')", (f"old{i}",))
    conn.close()
    assert today(styled.c)["context"]["stylist"]["state"] == "working"


def test_the_demo_closet_never_asks_claude(styled):
    assert styled.c.post("/api/profile", json={"profile": "demo"}).status_code == 200
    body = today(styled.c)
    assert body["outfits"] and "stylist" not in body["context"]
    assert styled.held == [] and styled.stand_in.calls == []


def test_with_the_stylist_switched_off_nothing_is_asked(styled):
    wardrobe(styled.c)
    assert styled.c.get("/api/settings").json()["stylist_on"] is True
    assert styled.c.put("/api/settings", json={"stylist_on": False}).status_code == 200
    assert styled.c.get("/api/settings").json()["stylist_on"] is False
    body = today(styled.c)
    assert body["outfits"] and "stylist" not in body["context"] and styled.held == []
    assert answers(styled.cfg) == []
    assert styled.c.put("/api/settings", json={"stylist_on": True}).status_code == 200
    assert today(styled.c)["context"]["stylist"]["state"] == "working" and len(styled.held) == 1


def test_when_the_closet_cannot_dress_the_owner_claude_is_not_asked(styled):
    wardrobe(styled.c, shoes=False)
    body = today(styled.c)
    assert body["missing"] and body["outfits"] == [] and "stylist" not in body["context"]
    assert styled.held == [] and answers(styled.cfg) == []


def test_without_a_stylist_today_is_the_engines_as_before(client):
    wardrobe(client)
    body = today(client)
    assert body["outfits"] and "stylist" not in body["context"]


def test_an_unknown_answer_is_a_404_with_a_sentence(styled):
    r = styled.c.get("/api/style/answers/nope")
    assert r.status_code == 404 and r.json()["detail"] == "That answer is not known. Open Today again."


def test_two_requests_together_start_one_question(styled):
    wardrobe(styled.c)
    held = []
    stylist = stylejobs.Stylist(lambda b, r: pytest.fail("asked"), lambda: ("plan",), clock=lambda: 1.0,
                                start=held.append)
    ctx = outfits.parse_request(DAY)[0]
    path = styled.cfg.db_path("main")
    gate = threading.Barrier(2)
    got, errors = [], []

    def brief():   # made inside the lock: a slow one widens the window the other request could slip through
        threading.Event().wait(0.2)
        return {}, styling.listed([], ctx)

    def ask():
        conn = db.connect(path)
        try:
            gate.wait(timeout=5)
            got.append(stylist.for_today(conn, path, day=TODAY, key="k", ctx=ctx, ids=set(), worn_today=False,
                                         again=False, brief=brief))
        except Exception as e:   # reported below
            errors.append(e)
        finally:
            conn.close()

    threads = [threading.Thread(target=ask) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert errors == []
    assert [g["state"] for g in got] == ["working", "working"] and got[0]["id"] == got[1]["id"]
    assert len(held) == 1 and len(answers(styled.cfg)) == 1


# ------------------------------------------------------------------ money, wiring and the table
def test_a_question_about_outfits_is_priced_with_the_styling_model():
    assert spend.PURPOSE_STYLE == "style_outfits"
    cost = spend.estimate_style()
    assert 0 < cost < 1
    assert cost == spend.cost_usd(spend.STYLING_MODEL, spend.STYLE_TEXT_TOKENS, spend.STYLE_MAX_TOKENS)
    assert spend.estimate_style(photos=3) == cost


def test_the_real_stylist_turns_claudes_answer_into_looks(cfg, monkeypatch):
    from closet.tagger import correcting, stylist

    told = []
    answer = stylist.Looks(read="Cold and dry.", outfits=[stylist.Look(base=1, mid=0, outer=0, bottom=2, shoes=3,
                                                                      accessories=[4], why="Warm.", watch="")])

    def fake_ask(brief, routes, client=None, meter=None, **kw):
        told.append((brief, routes, meter))
        return correcting.CorrectionResult(answer=answer, route="api", model="styling-model", input_tokens=900,
                                           output_tokens=120)

    monkeypatch.setattr(stylist, "ask", fake_ask)
    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, routes=lambda: ("api",))
    try:
        assert sv.stylist is not None
        got = sv.stylist.ask({"closet": "1. White tee"}, ("api",))
    finally:
        sv.stop()
    assert got == {"looks": [{"base": 1, "mid": 0, "outer": 0, "bottom": 2, "shoes": 3, "accessories": [4],
                              "why": "Warm.", "watch": ""}],
                   "read": "Cold and dry.", "reply": None, "remember": [], "route": "api", "model": "styling-model",
                   "input_tokens": 900, "output_tokens": 120}
    [(brief, routes, meter)] = told
    assert brief == {"closet": "1. White tee"} and routes == ("api",)
    assert meter is not None and meter.purpose == spend.PURPOSE_STYLE


def test_a_closet_has_the_style_answers_table_and_refuses_an_unknown_state(cfg):
    path = cfg.db_path("main")
    path.parent.mkdir(parents=True, exist_ok=True)
    db.migrate(path, cfg.data_dir / "backups")
    conn = db.connect(path)
    try:
        names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE tbl_name = 'style_answers'")}
        assert {"style_answers", "style_answers_day_key"} <= names
        conn.execute("INSERT INTO style_answers (id, day, key, state, dressed, asked_at, created_at) "
                     "VALUES ('a', '2026-11-17', 'k', 'working', '{}', 0, 'now')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO style_answers (id, day, key, state, dressed, asked_at, created_at) "
                         "VALUES ('b', '2026-11-17', 'k', 'pending', '{}', 0, 'now')")
    finally:
        conn.close()
