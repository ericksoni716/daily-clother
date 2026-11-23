"""Dress for another day (closet/plans.py and what closet/today.py does with a plan): a plan is kept for its day, one a
day, and is not a wear; that morning Today opens on it, a piece that cannot be worn by then swapped; a plan lapses;
planned pieces are kept out of the laundry's way only when the laundry's own rule says so; a day inside a trip is
the trip's; another day's weather says where it comes from. Open-Meteo and the trip weather are stood in for."""
import json
from datetime import date, timedelta

import pytest

from closet import db, plans, today, tripweather, wears, weather

from .test_day import reader, reading
from .test_weather import NOON, TODAY, FakeOpenMeteo, make_item, small_closet

THURSDAY = TODAY                       # 12 November 2026; the laundry day is Sunday by default
SATURDAY = TODAY + timedelta(days=2)
MONDAY = TODAY + timedelta(days=4)
SUNDAY = 6


@pytest.fixture
def clock(monkeypatch):
    """The computer's day (moved by tests), the forecast for today, and a day ahead's weather as a trip's days have
    it: the forecast up to 16 days ahead, what the date is usually like beyond."""
    now = {"day": TODAY, "asked": [], "unknown": False}
    monkeypatch.setattr(wears, "today", lambda: now["day"])
    monkeypatch.setattr(weather, "_now", lambda: NOON)
    monkeypatch.setattr(weather, "fetch", FakeOpenMeteo())

    def lookup(state, place, first, last, today_):
        now["asked"].append((place["name"], first, today_))
        if now["unknown"]:
            return {"days": [tripweather.unknown(first.isoformat())],
                    "message": "Couldn't reach the weather service. Days without weather are left out of the plan until it can be looked up."}
        far = (first - today_).days >= tripweather.FORECAST_DAYS
        return {"days": [{"date": first.isoformat(), "low_c": 4.0, "high_c": 10.0, "rain": False, "rain_chance": 10,
                          "summary": None if far else "cloudy", "source": "usual" if far else "forecast"}], "message": None}
    monkeypatch.setattr(tripweather, "lookup", lookup)
    return now


def outfit_of(ids, base="tee1"):
    return {"base": ids[base], "mid": None, "outer": None, "bottom": ids["jeans"], "shoes": ids["sneakers"], "accessories": []}


def plan(client, day, pieces, **more):
    return client.put(f"/api/plans/{day.isoformat()}", json={"pieces": pieces, **more})


def suggest(client, **body):
    r = client.post("/api/outfits/today", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def wear_count(client, item_id):
    return client.get(f"/api/items/{item_id}").json()["wear_count"]


# ------------------------------------------------------------------ the laundry's own rule, pure
def piece(category, wears_since_wash=0):
    return {"id": category, "category": category, "wears_since_wash": wears_since_wash}


@pytest.mark.parametrize("row, plan_day, policy, held", [
    (piece("tee"), SATURDAY, wears.Policy({"tee": 1}, SUNDAY), True),          # in the laundry until Sunday
    (piece("tee"), MONDAY, wears.Policy({"tee": 1}, SUNDAY), False),           # washed on Sunday, clean on Monday
    (piece("tee"), SATURDAY + timedelta(days=1), wears.Policy({"tee": 1}, SUNDAY), False),   # washed that morning
    (piece("jacket"), SATURDAY, wears.Policy({"tee": 1, "jacket": None}, SUNDAY), False),   # a jacket never goes in
    (piece("sneakers"), SATURDAY, wears.Policy({"tee": 1}, SUNDAY), False),    # nor shoes
    (piece("sweater"), SATURDAY, wears.Policy({"sweater": 3}, SUNDAY), False),   # a knit with wears to spare
    (piece("sweater", 2), SATURDAY, wears.Policy({"sweater": 3}, SUNDAY), True),  # its last wear before the wash
    (piece("tee"), MONDAY, wears.Policy({"tee": 1}, None), True),             # no laundry day: it waits for the owner
    (piece("tee"), SATURDAY, None, False),                                      # the laundry is off
])
def test_a_planned_piece_is_held_back_only_when_wearing_it_leaves_it_in_the_laundry_on_the_day(row, plan_day, policy, held):
    planned = [{"day": plan_day.isoformat(), "pieces": {"base": row["id"], "accessories": []}}]
    assert (plans.held([row], planned, THURSDAY, policy) == {row["id"]: plan_day.isoformat()}) is held
    # the plan's own day, and days after it, hold nothing back
    assert plans.held([row], planned, plan_day, policy) == {}


def test_a_day_ahead_is_tomorrow_or_later_and_within_reach():
    assert plans.check_day("2026-11-13", TODAY) == TODAY + timedelta(days=1)
    for bad, words in (("2026-11-12", "after today"), ("2026-11-01", "after today"), ("tomorrow", "YYYY-MM-DD"),
                       ((TODAY + timedelta(days=plans.MAX_AHEAD_DAYS + 1)).isoformat(), "at most")):
        with pytest.raises(Exception, match=words):
            plans.check_day(bad, TODAY)


# ------------------------------------------------------------------ keeping a plan
def test_a_plan_is_kept_for_its_day_one_a_day_and_is_not_a_wear(client, clock):
    ids = small_closet(client)
    r = plan(client, SATURDAY, outfit_of(ids), occasion="casual", mood="usual")
    assert r.status_code == 200, r.text
    assert r.json()["replaced"] is None and r.json()["plan"]["pieces"] == outfit_of(ids)
    # nothing worn, nothing in the laundry
    assert wear_count(client, ids["tee1"]) == 0 and client.get(f"/api/items/{ids['tee1']}").json()["laundry"] == "clean"
    # one plan a day: a second takes the first one's place and gives it back, for Undo
    again = plan(client, SATURDAY, outfit_of(ids, "tee2")).json()
    assert again["replaced"]["pieces"] == outfit_of(ids) and again["plan"]["pieces"]["base"] == ids["tee2"]
    listed = client.get("/api/plans").json()["plans"]
    assert [p["day"] for p in listed] == [SATURDAY.isoformat()] and listed[0]["gone"] == []
    # removed, and given back for Undo
    removed = client.delete(f"/api/plans/{SATURDAY.isoformat()}").json()["removed"]
    assert removed["pieces"]["base"] == ids["tee2"] and client.get("/api/plans").json()["plans"] == []
    assert client.delete(f"/api/plans/{SATURDAY.isoformat()}").status_code == 404


def test_a_plan_is_refused_for_today_a_bad_day_a_piece_not_in_the_closet_and_a_trip_day(client, clock, services):
    ids = small_closet(client)
    assert plan(client, TODAY, outfit_of(ids)).status_code == 422
    assert client.put("/api/plans/saturday", json={"pieces": outfit_of(ids)}).status_code == 422
    assert plan(client, SATURDAY, {**outfit_of(ids), "base": "nothing-like-it"}).status_code == 404
    assert plan(client, SATURDAY, {"base": ids["tee1"], "accessories": []}).status_code == 422   # one piece
    assert plan(client, SATURDAY, outfit_of(ids), occasion="gala").status_code == 422
    add_trip(services, SATURDAY - timedelta(days=1), SATURDAY + timedelta(days=1))
    r = plan(client, SATURDAY, outfit_of(ids))
    assert r.status_code == 409 and "trip to Lisbon" in r.json()["detail"]


def add_trip(services, first, last):
    conn = db.connect(services.cfg.db_path(services.state.get("profile")))
    t = db.now()
    conn.execute("INSERT INTO trips (id, place, first_day, last_day, plan, planned_at, created_at, updated_at) "
                 "VALUES ('trip1', ?, ?, ?, '{}', ?, ?, ?)",
                 (json.dumps({"name": "Lisbon, Portugal"}), first.isoformat(), last.isoformat(), t, t, t))
    conn.close()


def test_a_plan_for_a_day_gone_by_lapses_quietly(client, clock):
    ids = small_closet(client)
    plan(client, TODAY + timedelta(days=1), outfit_of(ids))
    plan(client, SATURDAY, outfit_of(ids, "tee2"))
    clock["day"] = SATURDAY + timedelta(days=1)   # neither was worn
    assert client.get("/api/plans").json()["plans"] == []
    clock["day"] = TODAY
    assert client.get("/api/plans").json()["plans"] == []   # gone, not hidden


# ------------------------------------------------------------------ the morning of the day
def test_the_morning_of_the_day_today_opens_on_the_plan(client, clock):
    ids = small_closet(client)
    plan(client, SATURDAY, outfit_of(ids, "tee2"))
    assert "plan" not in suggest(client)["context"]   # not yet
    clock["day"] = SATURDAY
    answer = suggest(client)
    assert answer["context"]["plan"] == {"day": SATURDAY.isoformat(), "kept": [ids["tee2"], ids["jeans"], ids["sneakers"]],
                                         "unavailable": [], "note": None}
    # exactly as planned: no layer added to a place it left empty, though it is a cool day and a jacket is clean
    assert answer["outfits"][0]["pieces"] == outfit_of(ids, "tee2")
    # other outfits instead, on the owner's word
    assert "plan" not in suggest(client, planned=False)["context"]
    assert client.post("/api/outfits/today", json={"planned": "no"}).status_code == 422
    # "I'm wearing this" is the wear; the plan stays until the day is over
    worn = client.post("/api/wears", json={"item_ids": [ids["tee2"], ids["jeans"], ids["sneakers"]]})
    assert worn.status_code == 201 and wear_count(client, ids["tee2"]) == 1
    assert [p["day"] for p in client.get("/api/plans").json()["plans"]] == [SATURDAY.isoformat()]


def test_the_accessories_planned_go_with_the_plan(client, clock):
    ids = small_closet(client)
    belt = make_item(client, "z", name="Brown belt", category="belt", color="brown")
    planned = {**outfit_of(ids), "accessories": [belt]}
    plan(client, SATURDAY, planned)
    assert suggest(client, day=SATURDAY.isoformat())["outfits"][0]["pieces"] == planned


def test_a_planned_piece_that_cannot_be_worn_by_then_is_swapped(client, clock):
    ids = small_closet(client)
    plan(client, SATURDAY, outfit_of(ids))
    clock["day"] = SATURDAY
    client.post(f"/api/items/{ids['tee1']}/laundry", json={"state": "laundry"})
    answer = suggest(client)
    assert answer["context"]["plan"]["unavailable"] == [ids["tee1"]]
    assert answer["context"]["plan"]["kept"] == [ids["jeans"], ids["sneakers"]]
    assert answer["outfits"][0]["pieces"]["base"] == ids["tee2"]   # its place filled as "Wear this again" fills one


# ------------------------------------------------------------------ kept out of the laundry's way
def test_planned_pieces_are_kept_out_of_the_laundrys_way_on_the_days_before(client, clock):
    ids = small_closet(client)
    plan(client, SATURDAY, outfit_of(ids))   # a tee goes in the laundry after one wear; the laundry day is Sunday
    answer = suggest(client)
    assert answer["context"]["held"] == {ids["tee1"]: SATURDAY.isoformat()}
    assert answer["outfits"] and all(o["pieces"]["base"] != ids["tee1"] for o in answer["outfits"])
    # the jeans (three wears to a wash) and the sneakers are still offered
    assert any(o["pieces"]["bottom"] == ids["jeans"] for o in answer["outfits"])
    # asked for by name, it is built around, and the page is told it is planned
    around = suggest(client, build_around=ids["tee1"])
    assert all(o["pieces"]["base"] == ids["tee1"] for o in around["outfits"]) and around["context"]["held"][ids["tee1"]]
    # a plan for Monday, after Sunday's wash, holds nothing back
    client.delete(f"/api/plans/{SATURDAY.isoformat()}")
    plan(client, MONDAY, outfit_of(ids))
    assert "held" not in suggest(client)["context"]
    # and with the laundry off, nothing goes in by itself, so nothing is held back
    client.delete(f"/api/plans/{MONDAY.isoformat()}")
    plan(client, SATURDAY, outfit_of(ids))
    assert client.put("/api/settings", json={"laundry": {"auto": False, "day": 6}}).status_code == 200
    assert "held" not in suggest(client)["context"]


def test_with_no_plan_today_is_as_before(client, clock):
    small_closet(client)
    answer = suggest(client)
    assert not {"plan", "held", "ahead"} & set(answer["context"])


# ------------------------------------------------------------------ another day
def test_another_day_is_dressed_for_its_forecast_and_says_where_it_comes_from(client, clock):
    small_closet(client)
    ctx = suggest(client, day=SATURDAY.isoformat())["context"]
    assert (ctx["date"], ctx["ahead"], ctx["source"], ctx["low_c"], ctx["high_c"]) == (SATURDAY.isoformat(), True, "forecast", 4.0, 10.0)
    assert ctx["place"] == "New York, United States" and "stylist" not in ctx and ctx["detail"] is None
    assert clock["asked"][-1] == ("New York, United States", SATURDAY, TODAY)
    far = TODAY + timedelta(days=30)
    assert suggest(client, day=far.isoformat())["context"]["source"] == "usual"
    clock["unknown"] = True
    ctx = suggest(client, day=SATURDAY.isoformat())["context"]
    assert ctx["source"] == "mild" and ctx["message"].startswith("Nines can't tell what the weather will be that day")
    assert "Couldn't reach the weather service." in ctx["message"] and "left out of the plan" not in ctx["message"]
    for bad in (TODAY.isoformat(), "someday"):
        assert client.post("/api/outfits/today", json={"day": bad}).status_code == 422


def test_ahead_weather_says_why_there_is_none():
    def lookup(days, message=None):
        return lambda *a: {"days": days, "message": message}
    usual = {"date": "2026-12-20", "low_c": 1.0, "high_c": 6.0, "rain": True, "rain_chance": 60, "summary": None, "source": "usual"}
    place = {"name": "Home"}
    assert today.ahead_weather(None, place, date(2026, 12, 20), TODAY, lookup([usual])) == {"weather": usual, "message": None}
    assert today.ahead_weather(None, None, date(2026, 12, 20), TODAY)["message"].startswith("Choose where you are")
    none = today.ahead_weather(None, place, date(2026, 12, 20), TODAY, lookup([tripweather.unknown("2026-12-20")]))
    assert none == {"weather": None, "message": "The weather service has nothing for that day."}


def test_what_is_in_the_laundry_today_is_clean_by_a_day_far_enough_ahead_as_for_a_trip(client, clock):
    ids = small_closet(client)
    for key in ("tee1", "tee2"):
        client.post(f"/api/items/{ids[key]}/laundry", json={"state": "laundry"})
    soon = TODAY + timedelta(days=1)
    far = TODAY + timedelta(days=3)   # trips.CLEAN_BY_DAYS
    assert suggest(client, day=soon.isoformat())["outfits"] == []   # still in the wash tomorrow
    assert {o["pieces"]["base"] for o in suggest(client, day=far.isoformat())["outfits"]} <= {ids["tee1"], ids["tee2"]}
    assert suggest(client, day=far.isoformat())["outfits"]


def test_another_day_with_a_plan_opens_on_it(client, clock):
    ids = small_closet(client)
    plan(client, SATURDAY, outfit_of(ids, "tee2"))
    answer = suggest(client, day=SATURDAY.isoformat())
    assert answer["context"]["plan"]["kept"][0] == ids["tee2"] and answer["outfits"][0]["pieces"]["base"] == ids["tee2"]
    # the days before Saturday do not offer its tee; Saturday itself does
    assert "held" not in answer["context"]
    assert ids["tee2"] in suggest(client, day=(TODAY + timedelta(days=1)).isoformat())["context"]["held"]


def test_a_day_inside_a_saved_trip_is_the_trips(client, clock, services):
    small_closet(client)
    add_trip(services, SATURDAY, MONDAY)
    answer = suggest(client, day=SATURDAY.isoformat())
    assert answer["outfits"] == [] and answer["context"]["source"] == "trip"
    assert answer["context"]["trip"] == {"id": "trip1", "place": "Lisbon, Portugal", "first_day": SATURDAY.isoformat(),
                                         "last_day": MONDAY.isoformat()}


def test_a_word_about_another_day_is_read_for_that_day_and_sends_no_more(client, clock, services, claude):
    small_closet(client)
    claude.mode = "answers"
    asked = []
    services.day_reader = reader(reading(activity="dinner", outside=(19, 23), occasion="smart_casual"), asked)
    r = client.put("/api/day", json={"text": "Dinner at eight", "day": SATURDAY.isoformat()})
    assert r.status_code == 200 and r.json()["saved"] is True, r.text
    # the sentence, the day it is about and home's name: what today's sends
    assert asked == [("Dinner at eight", SATURDAY, "New York, United States", ("plan",))]
    note = r.json()["note"]
    assert (note["from"], note["to"], note["active"]) == (SATURDAY.isoformat(), SATURDAY.isoformat(), True)
    assert note["words"] == ["outside 7pm to 11pm", "dinner"]   # not "today"
    assert client.get("/api/day", params={"day": SATURDAY.isoformat()}).json()["note"] == note
    assert client.get("/api/day").json()["note"] is None   # today is an ordinary day
    ctx = suggest(client, day=SATURDAY.isoformat())["context"]
    assert ctx["note"]["text"] == "Dinner at eight"
    assert suggest(client, day=SATURDAY.isoformat(), occasion="casual")   # the owner's choice still stands
    # that morning it is the day's note, and the plan's line carries it
    plan_ids = small_ids(client)
    plan(client, SATURDAY, plan_ids)
    clock["day"] = SATURDAY
    ctx = suggest(client)["context"]
    assert ctx["note"]["text"] == "Dinner at eight" and ctx["plan"]["note"] == "Dinner at eight"
    assert client.get("/api/day").json()["note"]["text"] == "Dinner at eight"
    assert client.delete("/api/day").json()["note"] is None   # cleared from Today like today's note
    assert client.put("/api/day", json={"text": "x", "day": "soon"}).status_code == 422


def small_ids(client):
    items = {i["name"]: i["id"] for i in client.get("/api/items").json()["items"]}
    return {"base": items["White tee one"], "mid": None, "outer": None, "bottom": items["Blue jeans"],
            "shoes": items["White sneakers"], "accessories": []}
