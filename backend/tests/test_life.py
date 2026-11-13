"""How the owner lives (closet/life.py), the weather where he lives (closet/climate.py), his taste, and what they
change in the gap analysis (closet/gaps.py) and the screen's API."""
import json
import sqlite3
import urllib.error
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from closet import climate, gaps, life, weather

from .test_gaps import demo_items, wears_for, without

BEFORE = json.loads((Path(__file__).parent / "data" / "gaps_before.json").read_text(encoding="utf-8"))
NOW = datetime(2026, 11, 12, 17, 0, tzinfo=UTC).timestamp()
NYC = {"name": "New York, New York, United States", "latitude": 40.7143, "longitude": -74.006, "timezone": "America/New_York"}
MIAMI = {"name": "Miami, Florida, United States", "latitude": 25.7743, "longitude": -80.1937, "timezone": "America/New_York"}
OFFICE = {"work": {"days": "most_days", "dress": "smart_casual"}, "everyday": {"days": 2}, "going_out": {"days": 1}}


def bands(cold, cool, mild, hot, wet=0.3):
    return {"bands": {"cold": {"share": cold, "wet": wet}, "cool": {"share": cool, "wet": wet},
                      "mild": {"share": mild, "wet": wet}, "hot": {"share": hot, "wet": wet}}, "source": "archive"}


WARM = bands(0.0, 0.05, 0.35, 0.6)
COLD = bands(0.45, 0.3, 0.2, 0.05)


def without_new_keys(answer: dict) -> dict:
    """The analysis as it was before this change: the keys it gained taken out."""
    answer = json.loads(json.dumps(answer))
    answer.pop("told", None)
    for g in answer["gaps"]:
        g.pop("situations", None)
        g["look_for"].pop("fit", None)
    return answer


def ranked(answer: dict) -> list[str]:
    return [g["id"] for g in answer["gaps"]]


def score_of(answer: dict, gap_id: str) -> float:
    return next((g["score"] for g in answer["gaps"] if g["id"] == gap_id), 0)


# ---------------------------------------------------------------------------- the weights
def test_with_no_answers_the_analysis_is_exactly_what_it_was():
    assert without_new_keys(gaps.find_gaps(demo_items(), [], {"max_gaps": 100})) == BEFORE["demo"]
    sparse = gaps.find_gaps(without("trench", "shoes_black", "belt_brown", "coat_grey", "trousers_navy", "dress_blue", "tee_grey"),
                            wears_for({"jeans_dark": 8, "jeans_black": 1, "tee_white": 2, "tee_grey": 2}), {"max_gaps": 100})
    assert without_new_keys(sparse) == BEFORE["sparse"]
    answer = gaps.find_gaps(demo_items(), [])
    assert answer["told"] == {"life": None, "style": None, "climate": None, "taste": None}
    assert all(g["situations"] == [] for g in answer["gaps"])
    # answers that cannot be read are no answers
    assert without_new_keys(gaps.find_gaps(demo_items(), [], {"max_gaps": 100, "life": {"work": "often"}})) == BEFORE["demo"]


def test_business_work_most_days_raises_the_business_gaps():
    casual = gaps.find_gaps(demo_items(), [], {"life": {**OFFICE, "work": {"days": "most_days", "dress": "casual"}}})
    business = gaps.find_gaps(demo_items(), [], {"life": {**OFFICE, "work": {"days": "most_days", "dress": "business"}}})
    shoes = next(g for g in business["gaps"] if g["id"] == "dress_shoes-business")
    assert ranked(business)[0] == "dress_shoes-business"
    assert shoes["score"] > score_of(casual, "dress_shoes-business") + 20
    assert shoes["situations"][0]["key"] == "work"
    assert shoes["why"][0].startswith("For work, most days")


def test_no_business_or_formal_gap_without_work_or_going_out():
    answer = gaps.find_gaps(demo_items(), [], {"max_gaps": 100, "life": {
        "work": {"days": "never"}, "going_out": {"days": "never"}, "everyday": {"days": "most_days"},
        "exercise": {"days": "weekly"}}})
    assert answer["gaps"]
    for g in answer["gaps"]:
        assert g["look_for"]["formality"] not in ("business", "formal"), g["id"]
        assert {s["key"] for s in g["situations"]} <= {"everyday", "exercise"}
    assert {d["occasion"] for d in [d for g in answer["gaps"] for d in g["evidence"]["days"]]} <= {"athletic", "casual"}


def test_a_warm_climate_drops_the_winter_coat_and_a_cold_one_raises_it():
    closet = without("coat_grey", "coat_navy", "trench", "shoes_black", "dress_blue")
    even = gaps.find_gaps(closet, [], {"life": OFFICE})
    warm = gaps.find_gaps(closet, [], {"life": OFFICE, "climate": WARM})
    cold = gaps.find_gaps(closet, [], {"life": OFFICE, "climate": COLD})
    assert "outer-warm" in ranked(even)
    assert "outer-warm" not in ranked(warm)          # below the fold, or not offered at all
    assert ranked(cold)[0] == "outer-warm" and score_of(cold, "outer-warm") > score_of(even, "outer-warm")
    coat = next(g for g in cold["gaps"] if g["id"] == "outer-warm")
    assert "days here (about" in coat["why"][0] and "a year)" in coat["why"][0]
    assert cold["told"]["climate"]["bands"]["cold"]["share"] == 0.45


def test_a_cold_vacation_wants_the_coat_whatever_the_home_climate():
    closet = without("coat_grey", "coat_navy", "trench", "shoes_black", "dress_blue")
    away = {**OFFICE, "vacation": {"weeks": 4, "where": "cold"}}
    warm_home = gaps.find_gaps(closet, [], {"max_gaps": 100, "life": away, "climate": WARM})
    coat = next(g for g in warm_home["gaps"] if g["id"] == "outer-warm")
    assert "vacation" in {s["key"] for s in coat["situations"]}


def test_lounging_asks_for_soft_trousers_only_when_he_lounges():
    lounging = {**OFFICE, "lounging": {"days": "most_days"}}
    answer = gaps.find_gaps(demo_items(), [], {"max_gaps": 100, "life": lounging})
    soft = next(g for g in answer["gaps"] if g["id"] == "trousers-casual-lounge")
    assert soft["found_by"] == ["lounging"] and soft["situations"] == [{"key": "lounging", "words": "lounging at home", "share": 1.0}]
    assert soft["why"][0] == "For lounging at home, most days."
    assert "trousers-casual-lounge" not in ranked(gaps.find_gaps(demo_items(), [], {"max_gaps": 100, "life": OFFICE}))
    # joggers count, by their name
    joggers = demo_items() + [{"id": "joggers", "name": "Grey joggers", "category": "trousers", "color": "grey",
                               "formality": "casual", "season": "all", "material": "cotton fleece"}]
    assert "trousers-casual-lounge" not in ranked(gaps.find_gaps(joggers, [], {"max_gaps": 100, "life": lounging}))


def test_ids_stay_the_same_for_the_same_suggestion():
    before = {(g["look_for"]["category"], g["look_for"]["formality"], g["id"]) for g in BEFORE["demo"]["gaps"]}
    after = gaps.find_gaps(demo_items(), [], {"max_gaps": 100, "life": life.DEMO_ANSWERS, "climate": climate.DEMO_CLIMATE})
    old_ids = {gid for _, _, gid in before}
    for g in after["gaps"]:
        assert g["id"] in old_ids or g["found_by"] == ["lounging"] or "worn_most" in g["found_by"], g["id"]
        assert g["id"] == "-".join(x for x in g["id"].split("-") if x)


# ---------------------------------------------------------------------------- taste
TEE_GAP = without("tee_white", "tee_grey", "tee_navy")
NAVY_AND_GREY = wears_for({"polo_navy": 6, "sweater_grey": 6, "jeans_dark": 5, "trousers_grey": 5})


def test_favoured_colours_come_first_and_the_sentence_names_them():
    plain = gaps.find_gaps(TEE_GAP, NAVY_AND_GREY)
    told = gaps.find_gaps(TEE_GAP, NAVY_AND_GREY, {"life": OFFICE})
    assert next(g for g in plain["gaps"] if g["id"] == "tee-casual")["look_for"]["colors"][0] == "white"
    tee = next(g for g in told["gaps"] if g["id"] == "tee-casual")
    assert tee["look_for"]["colors"][:2] == ["grey", "navy"]
    assert "Grey and navy first: you wear and rate grey and navy most." in tee["why"]
    assert told["told"]["taste"]["used"] is True and told["told"]["taste"]["colors"] == ["grey", "navy"]


def test_with_too_little_to_go_on_nothing_is_said_about_taste():
    answer = gaps.find_gaps(TEE_GAP, wears_for({"polo_navy": 3}), {"life": OFFICE})
    taste = answer["told"]["taste"]
    assert taste["used"] is False and taste["colors"] == [] and "Too little to go on" in taste["message"]
    assert not any("first: you wear" in s for g in answer["gaps"] for s in g["why"])


def test_a_pattern_he_avoids_is_not_suggested():
    closet = TEE_GAP + [
        {"id": f"check{n}", "name": f"Plaid shirt {n}", "category": "shirt", "color": "red", "pattern": "plaid",
         "formality": "casual", "season": "all", "rating": "dislike"} for n in range(2)]
    answer = gaps.find_gaps(closet, NAVY_AND_GREY, {"max_gaps": 100, "life": OFFICE})
    assert answer["told"]["taste"]["avoids"]["patterns"] == ["plaid"]
    assert all(g["look_for"]["pattern"] == "solid" for g in answer["gaps"])


def test_a_never_wear_hide_holds_back_its_like_and_can_be_undone(client):
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    # in the demo's example, light smart trousers are for work and going out, smart trousers for going out only
    assert "trousers-business" in [g["id"] for g in client.get("/api/gaps").json()["gaps"]]
    hide = "/api/gaps/trousers-business-light/hide"
    assert client.post(hide, json={"reason": "never_wear"}).status_code == 200
    after = {g["id"]: g for g in client.get("/api/gaps").json()["gaps"]}
    assert after["trousers-business-light"]["state"] == "hidden"
    assert after["trousers-business"]["state"] == "held" and after["trousers-business"]["held_by"] == "trousers-business-light"
    assert after["shirt-business"]["state"] == "open"            # another kind of piece is not held back
    # another reason holds nothing back
    assert client.post(hide, json={"reason": "too_expensive"}).status_code == 200
    assert all(g["state"] != "held" for g in client.get("/api/gaps").json()["gaps"])
    assert client.post(hide, json={"reason": "never_wear"}).status_code == 200
    # undo
    assert client.delete(hide).status_code == 204
    back = {g["id"]: g for g in client.get("/api/gaps").json()["gaps"]}
    assert back["trousers-business"]["state"] == "open"
    assert all(g["state"] == "open" and g["held_by"] is None for g in back.values())


# ---------------------------------------------------------------------------- the climate
class FakeArchive:
    """Stands in for Open-Meteo's archive: answers `days` (low, high, rain) and records what was asked."""

    def __init__(self, days):
        self.days = days
        self.calls: list[dict] = []
        self.timeouts: list[float | None] = []
        self.down = False

    def __call__(self, url, timeout=None):
        parts = urlsplit(url)
        assert parts.netloc + parts.path == "archive-api.open-meteo.com/v1/archive"
        self.calls.append({k: v[0] for k, v in parse_qs(parts.query).items()})
        self.timeouts.append(timeout)
        if self.down:
            raise urllib.error.URLError("no network")
        n = len(self.days)
        return json.dumps({"daily": {"time": [f"{2021 + i * 5 // n}-01-01" for i in range(n)],
                                     "temperature_2m_min": [d[0] for d in self.days],
                                     "temperature_2m_max": [d[1] for d in self.days],
                                     "precipitation_sum": [d[2] for d in self.days]}}).encode()


# 400 days: 100 cold (half wet), 100 cool, 100 mild, 100 hot (a quarter wet)
YEAR = ([(-6, 1, 5.0)] * 50 + [(-6, 1, 0.0)] * 50 + [(4, 12, 0.0)] * 100 + [(13, 21, 0.2)] * 100
        + [(24, 33, 3.0)] * 25 + [(24, 33, None)] * 75)


@pytest.fixture
def archive(monkeypatch):
    clock = {"now": NOW}
    monkeypatch.setattr(weather, "_now", lambda: clock["now"])
    fake = FakeArchive(YEAR)
    fake.clock = clock
    monkeypatch.setattr(weather, "fetch", fake)
    return fake


class FakeState:
    def __init__(self, **data):
        self.data = data

    def get(self, k):
        return self.data.get(k)

    def update(self, **changes):
        self.data.update(changes)


def test_the_climate_shares_come_from_the_archive(archive):
    found = climate.lookup(FakeState(place=NYC))
    assert found["message"] is None
    c = found["climate"]
    assert c["days"] == 400 and c["years"] == [2021, 2025] and c["source"] == "archive"
    assert c["bands"] == {"cold": {"share": 0.25, "wet": 0.5}, "cool": {"share": 0.25, "wet": 0.0},
                          "mild": {"share": 0.25, "wet": 0.0}, "hot": {"share": 0.25, "wet": 0.25}}
    sent = archive.calls[0]
    assert set(sent) == {"latitude", "longitude", "start_date", "end_date", "daily", "temperature_unit"}
    assert (sent["latitude"], sent["longitude"]) == ("40.7143", "-74.006")
    assert (sent["start_date"], sent["end_date"]) == ("2021-01-01", "2025-12-31")   # the last five full years
    assert archive.timeouts == [climate.ARCHIVE_TIMEOUT_S]


def test_the_kept_climate_is_reused_for_months(archive):
    st = FakeState(place=NYC)
    first = climate.lookup(st)["climate"]
    archive.clock["now"] += 90 * 86400
    assert climate.lookup(st)["climate"] == first and len(archive.calls) == 1
    archive.clock["now"] += (climate.KEEP_DAYS - 89) * 86400
    climate.lookup(st)
    assert len(archive.calls) == 2
    # a new place is a new climate
    st.update(place=MIAMI)
    climate.lookup(st)
    assert len(archive.calls) == 3


def test_the_archive_failing_says_so_and_is_not_asked_again_at_once(archive):
    archive.down = True
    st = FakeState(place=NYC)
    found = climate.lookup(st)
    assert found["climate"] is None and "Couldn't reach the weather service" in found["message"]
    assert "not being used yet" in found["message"]
    climate.lookup(st)
    assert len(archive.calls) == 1
    archive.down = False
    archive.clock["now"] += climate.RETRY_S + 1
    assert climate.lookup(st)["climate"]["days"] == 400


def test_an_older_climate_is_used_when_the_archive_fails(archive):
    st = FakeState(place=NYC)
    first = climate.lookup(st)["climate"]
    archive.down = True
    archive.clock["now"] += (climate.KEEP_DAYS + 1) * 86400
    assert climate.lookup(st) == {"place": NYC, "climate": first, "message": None}


def test_too_few_days_is_not_a_climate(archive):
    archive.days = YEAR[:50]
    found = climate.lookup(FakeState(place=NYC))
    assert found["climate"] is None and "too few days" in found["message"]


def test_no_place_saved_counts_every_band_the_same(archive):
    found = climate.lookup(FakeState())
    assert found == {"place": None, "climate": None,
                     "message": "The weather where you live is not being used: choose where you live in Settings."}
    assert archive.calls == []


def test_the_bands_match_the_grid():
    for band, lo, hi in gaps.TEMP_BANDS:
        assert climate.band_of(lo, hi) == band


# ---------------------------------------------------------------------------- the API
def test_life_needs_login(anon):
    assert anon.get("/api/life").status_code == 401
    assert anon.put("/api/life", json={}).status_code == 401
    assert anon.delete("/api/life").status_code == 401
    assert anon.post("/api/life/not-now").status_code == 401


def test_saving_and_reading_the_answers(client):
    first = client.get("/api/life").json()
    assert first == {"answers": None, "example": False, "answered": False, "not_now": False, "situations": []}
    r = client.put("/api/life", json={"work": {"days": "most_days", "dress": "business"}, "exercise": {"days": 2.3},
                                      "vacation": {"weeks": 3, "where": "warm"}, "style": "  Plain,   dark   colours "})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answered"] is True and body["example"] is False
    assert body["answers"]["work"] == {"days": 5.0, "dress": "business"}
    assert body["answers"]["exercise"] == {"days": 2.5} and body["answers"]["everyday"] == {"days": 0.0}
    assert body["answers"]["style"] == "Plain, dark colours"
    assert [s["key"] for s in body["situations"]] == ["work", "exercise", "vacation"]
    assert client.get("/api/life").json() == body
    assert client.delete("/api/life").status_code == 204
    assert client.get("/api/life").json()["answers"] is None


@pytest.mark.parametrize("bad, words", [
    ({"work": {"days": "sometimes"}}, "How often for work must be never, now and then, about weekly, most days"),
    ({"work": {"days": 9}}, "from 0 to 7"),
    ({"work": {"days": 3, "dress": "pyjamas"}}, "Say how people dress at work"),
    ({"vacation": {"weeks": 2.5}}, "Weeks of vacation a year must be a whole number"),
    ({"vacation": {"weeks": 2, "where": "moon"}}, "Say where you go on vacation"),
    ({"gardening": {"days": 1}}, "These are not situations Closet asks about: gardening."),
    ({"style": "x" * 300}, "too long"),
    ([1, 2], "Send the answers as an object"),
])
def test_wrong_answers_are_refused_in_plain_words(client, bad, words):
    r = client.put("/api/life", json=bad)
    assert r.status_code == 422 and words in r.json()["detail"]
    assert client.get("/api/life").json()["answers"] is None


def test_not_now_stops_asking_until_answered(client):
    assert client.get("/api/gaps").json()["asking"] is True
    assert client.post("/api/life/not-now").status_code == 204
    assert client.get("/api/gaps").json()["asking"] is False
    assert client.get("/api/life").json()["not_now"] is True


def test_the_demo_closet_keeps_its_example_whatever_the_owner_answers(client):
    assert client.put("/api/life", json={"work": {"days": "most_days", "dress": "formal"}}).status_code == 200
    client.post("/api/profile", json={"profile": "demo"})
    demo = client.get("/api/life").json()
    assert demo["example"] is True and demo["answers"] == life.check(life.DEMO_ANSWERS)
    told = client.get("/api/gaps").json()["told"]
    assert told["example"] is True and told["climate"]["source"] == "example"
    # answers tried in the demo are its own, and forgetting them takes it back to the example
    client.put("/api/life", json={"exercise": {"days": 3}})
    client.post("/api/profile", json={"profile": "main"})
    assert client.get("/api/life").json()["answers"]["work"]["dress"] == "formal"
    client.post("/api/profile", json={"profile": "demo"})
    assert client.delete("/api/life").status_code == 204
    assert client.get("/api/life").json()["answers"] == life.check(life.DEMO_ANSWERS)


def test_new_answers_throw_the_kept_analysis_away(client):
    client.post("/api/profile", json={"profile": "demo"})
    first = client.get("/api/gaps").json()
    assert client.get("/api/gaps").json() == first
    assert client.put("/api/life", json={"work": {"days": "never"}, "going_out": {"days": "never"},
                                         "everyday": {"days": "most_days"}}).status_code == 200
    after = client.get("/api/gaps").json()
    assert after["told"]["example"] is False and after != first
    assert all(g["look_for"]["formality"] not in ("business", "formal") for g in after["gaps"])


def test_a_new_place_throws_the_kept_analysis_away(client, services, archive):
    # the main closet, filled with the demo closet's clothes
    client.post("/api/profile", json={"profile": "demo"})
    client.post("/api/profile", json={"profile": "main"})
    src, dst = sqlite3.connect(services.cfg.db_path("demo")), sqlite3.connect(services.cfg.db_path("main"))
    src.backup(dst)
    src.close()
    dst.close()
    plain = client.get("/api/gaps").json()
    assert plain["told"]["answered"] is False and plain["asking"] is True and archive.calls == []
    assert client.put("/api/life", json=OFFICE).status_code == 200
    no_place = client.get("/api/gaps").json()
    assert no_place["told"]["climate"] is None and "choose where you live" in no_place["told"]["climate_message"]
    assert client.put("/api/settings", json={"place": NYC}).status_code == 200
    here = client.get("/api/gaps").json()
    assert here["told"]["place"] == NYC["name"] and here["told"]["climate"]["bands"]["cold"]["share"] == 0.25
    assert len(archive.calls) == 1
    archive.days = [(26, 34, 0.0)] * 400
    assert client.put("/api/settings", json={"place": MIAMI}).status_code == 200
    there = client.get("/api/gaps").json()
    assert there["told"]["place"] == MIAMI["name"] and there["told"]["climate"]["bands"]["hot"]["share"] == 1.0
    assert there["gaps"] != here["gaps"] and len(archive.calls) == 2
