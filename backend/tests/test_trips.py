import copy
import random
import time
from datetime import date, timedelta

import pytest

from closet import db, outfits, trips, tripweather, wears, weather

from .test_outfits import basic_closet, demo_items, item

CORE = ("base", "mid", "outer", "bottom", "shoes")
FIRST = date(2026, 12, 1)


def days(n, lows=(4, 7, 10, 13), rain_every=3, first=FIRST, source="usual"):
    out = []
    for i in range(n):
        low = lows[i % len(lows)]
        out.append({"date": (first + timedelta(days=i)).isoformat(), "low_c": low, "high_c": low + 6 + i % 3,
                    "rain": i % rain_every == 0, "rain_chance": None, "summary": None, "source": source})
    return out


def worn(day):
    p = day["outfit"]["pieces"]
    return [p[k] for k in CORE if p[k]] + list(p["accessories"])


def core_worn(day):
    p = day["outfit"]["pieces"]
    return [p[k] for k in CORE if p[k]]


def big_closet(n=300, seed=1):
    rnd = random.Random(seed)
    cats = ["tee", "shirt", "polo", "sweater", "hoodie", "jacket", "coat", "jeans", "trousers", "shorts", "sneakers",
            "boots", "dress_shoes", "sandals", "belt", "scarf", "hat"]
    colors = ["navy", "white", "grey", "black", "blue", "red", "olive", "tan", "brown", "green"]
    return [item(f"i{i:03d}", rnd.choice(cats), rnd.choice(colors), rnd.choice(["casual", "smart_casual", "business", None]),
                 rnd.choice(["all", "warm", "cool"]), rnd.choice(["solid"] * 4 + ["stripe", "plaid"])) for i in range(n)]


# The demo closet has 11 tops; at the default of one wear each, ten cool days (some with a shirt over a tee) need
# more than that without laundry. Tests about something else allow tops two wears, as the old fixed rules did.
TOPS_TWICE = {"tops": 2}


# ---------------------------------------------------------------------- the plan
def test_every_day_is_dressed_from_packed_pieces_only():
    result = trips.plan(demo_items(), days(10), rewear=TOPS_TWICE)
    packed = {p["id"] for p in result["packed"]}
    assert result["uncovered"] == [] and len(result["days"]) == 10
    for d in result["days"]:
        assert d["outfit"] is not None and set(worn(d)) <= packed
        assert d["outfit"]["score"] > 0 and d["outfit"]["reasons"]
    counts = {pid: sum(pid in worn(d) for d in result["days"]) for pid in packed}
    assert {p["id"]: p["days"] for p in result["packed"]} == counts


def test_fewer_pieces_than_a_fresh_outfit_a_day():
    result = trips.plan(demo_items(), days(10), rewear=TOPS_TWICE)
    slots = sum(len(core_worn(d)) for d in result["days"])
    assert len(result["packed"]) < slots / 2


def test_pieces_are_grouped_and_worn_no_more_than_the_rewear_rules_allow():
    by_id = {i["id"]: i for i in demo_items()}
    for laundry in (None, {"day": 5}, {"every": 3}):
        result = trips.plan(demo_items(), days(10), {"laundry": laundry}, TOPS_TWICE)
        assert result["uncovered"] == []
        washes = {w - 1 for w in trips.wash_days(trips.check_laundry(laundry, 10), 10)}
        for p in result["packed"]:
            category = by_id[p["id"]]["category"]
            assert p["group"] == trips.GROUP_OF[category]
            kind = trips.KIND_OF.get(category)
            limit = trips.check_rewear(TOPS_TWICE).get(kind) if kind else None
            if limit:
                worn_on = {i for i, d in enumerate(result["days"]) if p["id"] in worn(d)}
                assert trips._fits(worn_on, limit, washes, [False] * 10, kind in trips.NEXT_TO_SKIN), (p, laundry)
        groups = [p["group"] for p in result["packed"]]
        assert groups == sorted(groups, key=trips.GROUP_ORDER.index)
        assert groups.count("outer") <= trips.MAX_OUTER and groups.count("shoes") <= trips.MAX_SHOES
    washed = trips.plan(demo_items(), days(10), {"laundry": {"every": 3}}, TOPS_TWICE)
    assert len(washed["packed"]) < len(trips.plan(demo_items(), days(10), rewear=TOPS_TWICE)["packed"])


def test_laundry_and_archived_pieces_are_left_out():
    items = demo_items()
    first = trips.plan(items, days(5))
    gone = [p["id"] for p in first["packed"]][:2]
    for i in items:
        if i["id"] == gone[0]:
            i["laundry"] = "laundry"
        if i["id"] == gone[1]:
            i["status"] = "archived"
    again = trips.plan(items, days(5))
    assert not {p["id"] for p in again["packed"]} & set(gone)


def test_a_swapped_piece_is_left_out_and_a_pinned_piece_is_taken():
    items = demo_items()
    first = trips.plan(items, days(5))
    swapped = first["packed"][0]["id"]
    second = trips.plan(items, days(5), {"leave_out": [swapped]})
    assert swapped not in {p["id"] for p in second["packed"]}
    assert all(swapped not in worn(d) for d in second["days"] if d["outfit"])
    spare = next(i["id"] for i in items if i["id"] not in {p["id"] for p in first["packed"]}
                 and i["category"] in ("tee", "shirt", "polo") and i.get("status") != "archived" and i.get("rating") != "dislike"
                 and i.get("laundry") in (None, "clean"))
    third = trips.plan(items, days(5), {"pin": [spare]})
    line = next(p for p in third["packed"] if p["id"] == spare)
    assert line["pinned"] is True
    with pytest.raises(trips.PlanError, match="both left out and taken"):
        trips.plan(items, days(5), {"pin": [spare], "leave_out": [spare]})


def test_a_pinned_piece_in_the_laundry_is_not_packed_and_the_plan_says_so():
    items = basic_closet()
    items[0]["laundry"] = "laundry"
    result = trips.plan(items, days(2), {"pin": ["tee1"]})
    assert "tee1" not in {p["id"] for p in result["packed"]}
    assert any("in the laundry" in n for n in result["notes"])


def test_a_day_that_cannot_be_covered_says_why():
    items = [i for i in basic_closet() if i["category"] not in ("sneakers", "dress_shoes")]
    result = trips.plan(items, days(2))
    assert [u["date"] for u in result["uncovered"]] == [d["date"] for d in days(2)]
    assert all(d["outfit"] is None and "no shoes" in d["problem"] for d in result["days"])
    assert result["packed"] == []


def test_a_rainy_day_with_an_outfit_warning_is_not_counted_as_uncovered():
    items = [i for i in basic_closet() if i["category"] not in ("sneakers", "dress_shoes")]
    items.append(item("suede1", "sneakers", "white", "casual", material="suede"))
    result = trips.plan(items, days(3, rain_every=2), rewear=TOPS_TWICE)  # two shirts and a tee for three days
    rainy = [d for d in result["days"] if d["weather"]["rain"]]
    dry = [d for d in result["days"] if not d["weather"]["rain"]]
    assert all(d["warning"] and "Nothing rain-proof" in d["warning"] and d["outfit"] for d in rainy)
    assert all(d["problem"] is None and d["warning"] is None for d in dry)
    # A warning means the day has an outfit to wear; only a day with no outfit is uncovered.
    assert result["uncovered"] == []
    assert [w["date"] for w in result["warnings"]] == [d["date"] for d in rainy]


def test_a_day_without_weather_is_reported_and_the_rest_are_planned():
    trip = days(3)
    trip[1] = {"date": trip[1]["date"], "low_c": None, "high_c": None, "rain": None, "source": "unknown"}
    result = trips.plan(demo_items(), trip)
    assert result["days"][1]["outfit"] is None and "not known" in result["days"][1]["problem"]
    assert result["days"][0]["outfit"] and result["days"][2]["outfit"]


def test_days_that_differ_get_their_own_occasion():
    trip = days(4)
    result = trips.plan(demo_items(), trip, {"day_occasions": {trip[2]["date"]: "business"}})
    assert [d["occasion"] for d in result["days"]] == ["casual", "casual", "business", "casual"]
    with pytest.raises(trips.PlanError, match="not a day of this trip"):
        trips.plan(demo_items(), trip, {"day_occasions": {"2030-01-01": "business"}})
    with pytest.raises(trips.PlanError, match="not an occasion"):
        trips.plan(demo_items(), trip, {"occasion": "party"})


def test_basics_by_count():
    result = trips.plan(demo_items(), days(10, rain_every=3, lows=(0, 4)))
    basics = {b["key"]: b["count"] for b in result["basics"]}
    assert basics["underwear"] == basics["socks"] == 10 + trips.SPARE
    assert basics["sleepwear"] == 2 and basics["umbrella"] == 1 and basics["gloves"] == 1
    washed = {b["key"]: b["count"] for b in trips.plan(demo_items(), days(10), {"laundry": {"every": 3}})["basics"]}
    assert washed["socks"] == 4 + trips.SPARE and washed["sleepwear"] == 1  # days 1-4, then again after each wash
    assert "gloves" not in washed
    assert trips.lines(result)[-len(result["basics"]):] == [f"basic:{k}" for k in basics]


def test_the_same_input_gives_the_same_plan():
    items = demo_items()
    a = trips.plan(items, days(7), {"day_occasions": {days(7)[3]["date"]: "business"}})
    shuffled = copy.deepcopy(items)
    random.Random(4).shuffle(shuffled)
    b = trips.plan(shuffled, days(7), {"day_occasions": {days(7)[3]["date"]: "business"}})
    assert a == b


def test_a_ten_day_trip_on_a_big_closet_is_quick():
    items = big_closet()
    start = time.perf_counter()
    result = trips.plan(items, days(10), {"day_occasions": {days(10)[2]["date"]: "business"}})
    assert time.perf_counter() - start < 20  # about 1 s on a laptop; generous for slow test machines
    assert len(result["days"]) == 10 and not result["uncovered"]


def test_odd_input_never_crashes():
    assert trips.plan([], days(2))["uncovered"]
    assert trips.plan([{"id": "x"}, "nonsense", {"category": "tee"}], days(1))["packed"] == []
    with pytest.raises(trips.PlanError):
        trips.plan(demo_items(), days(1), {"leave_out": "everything"})
    with pytest.raises(trips.PlanError):
        trips.plan(demo_items(), days(3), {"laundry": "yes"})


# ---------------------------------------------------------------------- re-wear, weather and laundry
def mild(n, high=21, **kw):
    return [{"date": (FIRST + timedelta(days=i)).isoformat(), "low_c": 15, "high_c": high, "rain": False,
             "rain_chance": None, "summary": None, "source": "usual", **kw} for i in range(n)]


def shirt_closet(n=10, category="shirt"):
    return ([item(f"{category}{i}", category, c, "casual", silhouette={"sleeve": "short"})
             for i, c in zip(range(n), ["white", "navy", "grey", "light_blue", "black", "olive", "tan", "cream",
                                        "blue", "brown"], strict=False)]
            + [item(f"trousers{i}", "trousers", c, "casual") for i, c in enumerate(["grey", "navy", "tan"])]
            + [item("sneakers1", "sneakers", "white", "casual")])


def packed_of(result, category):
    return [p for p in result["packed"] if p["id"].startswith(category)]


def test_a_week_of_shirts_worn_once_needs_seven_without_laundry_and_four_with_laundry_on_day_four():
    result = trips.plan(shirt_closet(), mild(7))
    assert result["uncovered"] == [] and len(packed_of(result, "shirt")) == 7
    assert "7 shirts: one a day" in [c["words"] for c in result["counts"]]
    assert result["washes"] == [] and not any(d["laundry"] for d in result["days"])

    washed = trips.plan(shirt_closet(), mild(7), {"laundry": {"day": 4}})
    assert washed["uncovered"] == [] and len(packed_of(washed, "shirt")) == 4
    assert "4 shirts: one a day, laundry on day 4" in [c["words"] for c in washed["counts"]]
    assert [d["laundry"] for d in washed["days"]] == [False, False, False, True, False, False, False]
    words = washed["washes"][0]["words"]
    assert words.startswith("Wash on day 4: the shirts") and "from days 1\u20133 are worn again from day 5" in words
    # the shirt worn on day 4 is not in that wash: days 5-7 wear the shirts of days 1-3
    by_day = [next(x for x in core_worn(d) if x.startswith("shirt")) for d in washed["days"]]
    assert by_day[3] not in by_day[4:] and set(by_day[4:]) <= set(by_day[:3])
    basics = {b["key"]: b for b in washed["basics"]}
    assert basics["underwear"]["count"] == 4 + trips.SPARE and "laundry on day 4" in basics["underwear"]["why"]
    assert {b["key"]: b["count"] for b in result["basics"]}["socks"] == 7 + trips.SPARE


def test_laundry_every_few_days():
    assert trips.wash_days(("every", 3), 10) == [4, 7]
    assert trips.wash_days(("every", 1), 4) == [2, 3]
    assert trips.wash_days(("day", 4), 7) == [4]
    result = trips.plan(shirt_closet(), mild(10), {"laundry": {"every": 3}})
    assert result["uncovered"] == [] and len(packed_of(result, "shirt")) == 4
    assert [w["day"] for w in result["washes"]] == [4, 7]
    assert "4 shirts: one a day, laundry every 3 days" in [c["words"] for c in result["counts"]]


@pytest.mark.parametrize("laundry, words", [
    ({"day": 1}, "from day 2 to day 6"),
    ({"day": 7}, "from day 2 to day 6"),
    ({"every": 6}, "does not come round"),
    ({"day": 4, "every": 2}, "Laundry must be"),
    ({"day": "4"}, "Laundry must be"),
    ({"every": True}, "Laundry must be"),
])
def test_a_laundry_day_that_frees_nothing_is_refused(laundry, words):
    with pytest.raises(trips.PlanError, match=words):
        trips.plan(shirt_closet(), mild(7), {"laundry": laundry})
    with pytest.raises(trips.PlanError, match="no day for laundry"):
        trips.plan(shirt_closet(), mild(2), {"laundry": {"day": 1}})


def test_a_hot_or_humid_day_wears_a_knit_tee_once_even_when_the_owner_allows_two():
    closet = shirt_closet(6, "tee")
    twice = {"tops": 2}
    assert len(packed_of(trips.plan(closet, mild(4), rewear=twice), "tee")) == 2
    hot = trips.plan(closet, mild(4, high=trips.SWEATY_C + 4), rewear=twice)
    assert hot["uncovered"] == [] and len(packed_of(hot, "tee")) == 4
    assert all(p["days"] == 1 for p in packed_of(hot, "tee"))
    assert "4 tees: one a day, as every day is hot or humid" in [c["words"] for c in hot["counts"]]
    humid = trips.plan(closet, mild(4, feels_high_c=trips.SWEATY_C + 2), rewear=twice)  # 21°C that feels like 26°C
    assert len(packed_of(humid, "tee")) == 4
    # one hot day among cool ones: the tee worn on it is not worn again, the others twice
    mixed = mild(4)
    mixed[1]["high_c"] = trips.SWEATY_C + 4
    result = trips.plan(closet, mixed, rewear=twice)
    assert len(packed_of(result, "tee")) == 3
    hot_tee = next(x for x in core_worn(result["days"][1]) if x.startswith("tee"))
    assert sum(hot_tee in core_worn(d) for d in result["days"]) == 1
    assert "3 tees: worn up to 2 times each, once on a hot or humid day" in [c["words"] for c in result["counts"]]
    # the trousers are not next to the skin: the owner's three wears hold on hot days
    assert max(p["days"] for p in packed_of(hot, "trousers")) == 3
    assert {b["key"]: b["count"] for b in hot["basics"]}["underwear"] == 4 + trips.SPARE


def test_a_rain_day_keeps_the_rain_rules_and_does_not_change_rewear():
    rainy = mild(4, rain=True)
    result = trips.plan(shirt_closet(6, "tee"), rainy, rewear={"tops": 2})
    assert len(packed_of(result, "tee")) == 2
    assert {b["key"] for b in result["basics"]} >= {"umbrella"}


def test_jackets_and_coats_cover_the_whole_trip():
    result = trips.plan(demo_items(), days(10, lows=(2, 4)), rewear={"tops": 30, "knits": 30, "bottoms": 30})
    assert result["uncovered"] == []
    outer = [p for p in result["packed"] if p["group"] == "outer"]
    assert len(outer) == 1 and outer[0]["days"] == 10
    assert any(c["kind"] == "outer" and c["words"].endswith(": one for the whole trip") for c in result["counts"])


def test_cool_days_use_the_owners_full_count_for_sweaters_and_trousers():
    closet = big_closet()
    category = {i["id"]: i["category"] for i in closet}
    result = trips.plan(closet, days(8, lows=(0, 3), rain_every=99), rewear={"tops": 8, "knits": 3, "bottoms": 3})
    knits = [p for p in result["packed"] if trips.KIND_OF.get(category[p["id"]]) == "knits"]
    assert knits and max(p["days"] for p in knits) == 3
    words = next(c["words"] for c in result["counts"] if c["kind"] == "knits")
    assert "cool days, worn up to 3 times each" in words
    bottoms = [p for p in result["packed"] if trips.KIND_OF.get(category[p["id"]]) == "bottoms"]
    assert max(p["days"] for p in bottoms) == 3


def test_the_kinds_are_read_from_the_taxonomy_and_never_name_jeans():
    import inspect

    from closet import savedtrips
    clothing = {c for place in ("base", "mid", "outer", "bottom") for c in outfits.PLACE_CATEGORIES[place]}
    assert set(trips.KIND_OF) == clothing  # every piece of clothing has one kind
    assert trips.KIND_OF["jeans"] == trips.KIND_OF["trousers"] == "bottoms"
    for module in (trips, savedtrips):
        assert "jeans" not in inspect.getsource(module)
    assert set(trips.REWEAR_DEFAULTS) == set(trips.KIND_KEYS)
    assert trips.REWEAR_DEFAULTS == {"tops": 1, "knits": 3, "bottoms": 3, "outer": None, "basics": 1}


def test_the_rewear_setting_is_checked():
    assert trips.check_rewear(None) == trips.REWEAR_DEFAULTS
    assert trips.check_rewear({"tops": 2})["tops"] == 2
    for bad, words in (({"jeans": 2}, "not kinds of clothing"), ({"tops": 0}, "whole number"), ({"tops": 2.5}, "whole number"),
                       ({"tops": True}, "whole number"), ([1], "Say how often")):
        with pytest.raises(trips.PlanError, match=words):
            trips.check_rewear(bad)


def test_the_engine_is_called_not_changed():
    # a one-day trip wears what the engine would choose first from the same pieces on that day
    trip = days(1)
    result = trips.plan(demo_items(), trip)
    d = trip[0]
    best = outfits.suggest(demo_items(), outfits.Context(d["low_c"], d["high_c"], d["rain"]), 1)["outfits"][0]
    assert result["days"][0]["outfit"]["pieces"] == best["pieces"]


# ---------------------------------------------------------------------- the routes
TODAY = date(2026, 11, 12)
NYC = {"name": "New York, United States", "latitude": 40.7143, "longitude": -74.006, "timezone": "America/New_York"}


@pytest.fixture
def clock(monkeypatch):
    monkeypatch.setattr(wears, "today", lambda: TODAY)
    monkeypatch.setattr(weather, "_now", lambda: 1_794_500_000.0)

    def no_network(url):
        raise AssertionError(f"the network was used: {url}")
    monkeypatch.setattr(weather, "fetch", no_network)


def body(n=5, **kw):
    trip = days(n, first=TODAY + timedelta(days=20))
    return {"place": NYC, "first_day": trip[0]["date"], "last_day": trip[-1]["date"],
            "weather": [{k: d[k] for k in ("date", "low_c", "high_c", "rain")} for d in trip], **kw}


def test_trip_routes_need_login(anon):
    for method, path in (("post", "/api/trips/plan"), ("post", "/api/trips"), ("get", "/api/trips"), ("get", "/api/trips/x"),
                         ("get", "/api/trips/x/weather"), ("patch", "/api/trips/x"), ("delete", "/api/trips/x")):
        r = getattr(anon, method)(path, **({"json": {}} if method in ("post", "patch") else {}))
        assert r.status_code == 401, path


def test_planning_saves_nothing_and_saving_keeps_the_trip(client, clock):
    client.post("/api/profile", json={"profile": "demo"})
    r = client.post("/api/trips/plan", json=body())
    assert r.status_code == 200, r.text
    plan = r.json()
    assert "id" not in plan and plan["place"] == NYC and len(plan["plan"]["days"]) == 5
    assert [d["source"] for d in plan["weather"]] == ["given"] * 5
    assert plan["lines"] == trips.lines(plan["plan"])
    assert client.get("/api/trips").json() == {"trips": []}

    r = client.post("/api/trips", json=body(occasion="smart_casual", laundry={"day": 3}))
    assert r.status_code == 201, r.text
    trip = r.json()
    assert trip["occasion"] == "smart_casual" and trip["laundry"] == {"day": 3} and trip["packed"] == []
    assert trip["plan"]["laundry"] == {"day": 3} and trip["plan"]["washes"][0]["day"] == 3
    assert client.get(f"/api/trips/{trip['id']}").json() == trip
    listed = client.get("/api/trips").json()["trips"]
    assert listed == [{"id": trip["id"], "place": NYC, "first_day": trip["first_day"], "last_day": trip["last_day"],
                       "occasion": "smart_casual", "laundry": {"day": 3}, "lines": len(trip["lines"]), "packed": 0,
                       "uncovered": len(trip["plan"]["uncovered"]), "warnings": len(trip["plan"]["warnings"]), "past": False}]


def test_ticks_are_saved_and_survive_a_replan(client, clock):
    client.post("/api/profile", json={"profile": "demo"})
    trip = client.post("/api/trips", json=body()).json()
    first, basic = trip["lines"][0], "basic:socks"
    r = client.patch(f"/api/trips/{trip['id']}", json={"ticks": {first: True, basic: True}})
    assert r.status_code == 200 and r.json()["packed"] == [first, basic]
    assert client.patch(f"/api/trips/{trip['id']}", json={"ticks": {first: False}}).json()["packed"] == [basic]
    assert client.get(f"/api/trips/{trip['id']}").json()["packed"] == [basic]
    r = client.patch(f"/api/trips/{trip['id']}", json={"ticks": {"item:not-there": True}})
    assert r.status_code == 422 and "not in this trip's plan" in r.json()["detail"]
    assert client.get("/api/trips").json()["trips"][0]["packed"] == 1


def test_swap_and_pin_plan_again(client, clock):
    client.post("/api/profile", json={"profile": "demo"})
    trip = client.post("/api/trips", json=body()).json()
    swapped = trip["plan"]["packed"][0]["id"]
    client.patch(f"/api/trips/{trip['id']}", json={"ticks": {f"item:{swapped}": True, "basic:socks": True}})
    r = client.patch(f"/api/trips/{trip['id']}", json={"leave_out": [swapped]})
    assert r.status_code == 200, r.text
    again = r.json()
    assert again["leave_out"] == [swapped] and swapped not in {p["id"] for p in again["plan"]["packed"]}
    assert again["packed"] == ["basic:socks"]  # the swapped piece's tick went with it
    r = client.patch(f"/api/trips/{trip['id']}", json={"leave_out": [], "pin": [swapped]})
    assert next(p for p in r.json()["plan"]["packed"] if p["id"] == swapped)["pinned"] is True
    r = client.patch(f"/api/trips/{trip['id']}", json={"leave_out": [swapped]})
    assert r.status_code == 422 and "both left out and taken" in r.json()["detail"]


@pytest.mark.parametrize("change, words", [
    ({"first_day": "2026-11-01"}, "today or later"),
    ({"last_day": "2027-01-30"}, "at most 30 days"),
    ({"place": {"name": "X"}}, "Choose where the trip is"),
    ({"occasion": "gala"}, "not an occasion"),
    ({"luggage": 2}, "not part of a trip: luggage"),
    ({"weather": [{"date": "2026-12-02", "low_c": 1, "high_c": 3}]}, "every day of the trip"),
])
def test_wrong_input_is_answered_in_plain_words(client, clock, change, words):
    r = client.post("/api/trips/plan", json={**body(), **change})
    assert r.status_code == 422 and words in r.json()["detail"], r.text


def test_unknown_trips_and_bad_json(client, clock):
    assert client.get("/api/trips/nope").json()["detail"] == "That trip is not in this closet."
    assert client.patch("/api/trips/nope", json={"ticks": {}}).status_code == 404
    assert client.delete("/api/trips/nope").status_code == 404
    r = client.post("/api/trips", content=b"{", headers={"content-type": "application/json"})
    assert r.status_code == 400


def test_delete_and_the_order_of_the_list(client, clock, monkeypatch):
    client.post("/api/profile", json={"profile": "demo"})
    later = client.post("/api/trips", json=body()).json()
    soon_body = body(3)
    for d in soon_body["weather"]:
        d["date"] = (date.fromisoformat(d["date"]) - timedelta(days=15)).isoformat()
    soon_body["first_day"], soon_body["last_day"] = soon_body["weather"][0]["date"], soon_body["weather"][-1]["date"]
    soon = client.post("/api/trips", json=soon_body).json()
    assert [t["id"] for t in client.get("/api/trips").json()["trips"]] == [soon["id"], later["id"]]
    monkeypatch.setattr(wears, "today", lambda: TODAY + timedelta(days=12))  # the soon trip is over
    listed = client.get("/api/trips").json()["trips"]
    assert [t["id"] for t in listed] == [later["id"], soon["id"]] and listed[1]["past"] is True
    assert client.delete(f"/api/trips/{soon['id']}").status_code == 204
    assert [t["id"] for t in client.get("/api/trips").json()["trips"]] == [later["id"]]


def test_the_demo_closet_and_the_real_closet_keep_their_trips_apart(client, clock):
    client.post("/api/profile", json={"profile": "demo"})
    demo_trip = client.post("/api/trips", json=body()).json()
    client.post("/api/profile", json={"profile": "main"})
    assert client.get("/api/trips").json() == {"trips": []}
    assert client.get(f"/api/trips/{demo_trip['id']}").status_code == 404
    real = client.post("/api/trips", json=body()).json()
    assert real["plan"]["packed"] == [] and real["plan"]["uncovered"]  # nothing in the real closet yet
    client.post("/api/profile", json={"profile": "demo"})
    assert [t["id"] for t in client.get("/api/trips").json()["trips"]] == [demo_trip["id"]]


def test_migration_0012_adds_trips_to_a_closet_at_version_11(tmp_path):
    path = tmp_path / "closet.db"
    conn = db.connect(path)
    for version, migration in db.migration_files():
        if version < 12 and not migration.name.endswith("_trips.sql"):
            conn.executescript(migration.read_text(encoding="utf-8"))
            conn.execute(f"PRAGMA user_version = {version}")
    conn.execute("PRAGMA user_version = 11")
    conn.close()

    result = db.migrate(path, tmp_path / "backups")
    conn = db.connect(path)
    # 0012 is applied first; any later migration follows it (this test was written when 0012 was the last)
    assert result["applied"][0] == 12 and result["applied"] == sorted(result["applied"])
    assert conn.execute("PRAGMA user_version").fetchone()[0] == max(v for v, _ in db.migration_files())
    assert conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trips'").fetchone()
    conn.close()


def test_replan_keeps_saved_weather_and_ticks_when_the_archive_fails(client, clock, monkeypatch):
    from .test_tripweather import FakeOpenMeteo

    client.post("/api/profile", json={"profile": "demo"})
    fake = FakeOpenMeteo()
    monkeypatch.setattr(weather, "fetch", fake)
    now = [1_794_500_000.0]
    monkeypatch.setattr(weather, "_now", lambda: now[0])
    first = TODAY + timedelta(days=20)
    trip = client.post("/api/trips", json={
        "place": NYC, "first_day": first.isoformat(), "last_day": (first + timedelta(days=4)).isoformat(),
    }).json()
    assert [d["source"] for d in trip["weather"]] == ["usual"] * 5
    item_tick = f"item:{trip['plan']['packed'][0]['id']}"
    ticks = [item_tick, "basic:socks"]
    assert client.patch(f"/api/trips/{trip['id']}", json={"ticks": dict.fromkeys(ticks, True)}).status_code == 200

    fake.archive_down = True
    now[0] += tripweather.KEEP_USUAL_S + 1
    again = client.patch(f"/api/trips/{trip['id']}", json={"replan": True}).json()

    assert again["weather"] == trip["weather"]
    assert "weather could not be refreshed" in again["weather_message"]
    assert again["plan"] == trip["plan"]
    assert all(line in again["packed"] for line in ticks)


def test_a_saved_trip_notices_when_the_forecast_changes_but_keeps_its_plan(client, monkeypatch):
    from .test_tripweather import TODAY as WEATHER_TODAY
    from .test_tripweather import FakeOpenMeteo
    fake = FakeOpenMeteo()
    monkeypatch.setattr(weather, "fetch", fake)
    monkeypatch.setattr(weather, "_now", lambda: 1_794_500_000.0)
    monkeypatch.setattr(wears, "today", lambda: WEATHER_TODAY)
    client.post("/api/profile", json={"profile": "demo"})
    first = WEATHER_TODAY + timedelta(days=20)
    r = client.post("/api/trips", json={"place": NYC, "first_day": first.isoformat(),
                                        "last_day": (first + timedelta(days=2)).isoformat()})
    assert r.status_code == 201, r.text
    trip = r.json()
    assert [d["source"] for d in trip["weather"]] == ["usual"] * 3
    assert client.get(f"/api/trips/{trip['id']}/weather").json() == {"checked": False, "changed": False, "days": None,
                                                                    "message": None}
    # a week later the first days are in the forecast
    monkeypatch.setattr(wears, "today", lambda: WEATHER_TODAY + timedelta(days=7))
    fake.start = WEATHER_TODAY + timedelta(days=7)
    check = client.get(f"/api/trips/{trip['id']}/weather").json()
    assert check["checked"] is True and check["changed"] is True
    assert client.get(f"/api/trips/{trip['id']}").json()["weather"] == trip["weather"]  # not changed behind the owner's back
    again = client.patch(f"/api/trips/{trip['id']}", json={"replan": True}).json()
    assert "forecast" in [d["source"] for d in again["weather"]] and again["planned_at"] >= trip["planned_at"]


def test_the_rewear_setting_is_kept_in_settings_and_used_by_trips(client, clock):
    assert client.get("/api/settings").json()["rewear"] == trips.REWEAR_DEFAULTS
    r = client.put("/api/settings", json={"rewear": {"tops": 2}})
    assert r.status_code == 200 and r.json()["rewear"] == {**trips.REWEAR_DEFAULTS, "tops": 2}
    r = client.put("/api/settings", json={"rewear": {"outer": 4}})
    assert r.json()["rewear"] == {**trips.REWEAR_DEFAULTS, "tops": 2, "outer": 4}  # one kind at a time
    for bad in ({"tops": 0}, {"shoes": 2}, [2]):
        r = client.put("/api/settings", json={"rewear": bad})
        assert r.status_code == 422, bad
    client.post("/api/profile", json={"profile": "demo"})
    plan = client.post("/api/trips/plan", json=body(4)).json()["plan"]
    tops = next(c for c in plan["counts"] if c["kind"] == "tops")
    assert "up to 2 times each" in tops["words"]
    assert client.put("/api/settings", json={"rewear": None}).json()["rewear"] == trips.REWEAR_DEFAULTS


def test_laundry_on_a_saved_trip_can_be_changed(client, clock):
    client.post("/api/profile", json={"profile": "demo"})
    trip = client.post("/api/trips", json=body(7)).json()
    assert trip["laundry"] is None and trip["plan"]["washes"] == []
    r = client.patch(f"/api/trips/{trip['id']}", json={"laundry": {"every": 2}})
    assert r.status_code == 200, r.text
    assert r.json()["laundry"] == {"every": 2} and [w["day"] for w in r.json()["plan"]["washes"]] == [3, 5]
    r = client.patch(f"/api/trips/{trip['id']}", json={"laundry": {"day": 9}})
    assert r.status_code == 422 and "from day 2 to day 6" in r.json()["detail"]
    assert client.patch(f"/api/trips/{trip['id']}", json={"laundry": None}).json()["laundry"] is None
    assert client.post("/api/trips/plan", json=body(can_wash=True)).status_code == 422  # replaced by laundry


def test_migration_0023_keeps_i_can_wash_there_as_laundry_every_three_days(tmp_path):
    path = tmp_path / "closet.db"
    conn = db.connect(path)
    for version, migration in db.migration_files():
        if version < 23:
            conn.executescript(migration.read_text(encoding="utf-8"))
            conn.execute(f"PRAGMA user_version = {version}")
    for trip_id, wash in (("washing", 1), ("not", 0)):
        conn.execute("INSERT INTO trips (id, place, first_day, last_day, can_wash, plan, planned_at, created_at, updated_at)"
                     " VALUES (?, '{}', '2026-12-01', '2026-12-07', ?, '{}', '', '', '')", (trip_id, wash))
    conn.commit()
    conn.close()
    result = db.migrate(path, tmp_path / "backups")
    assert 23 in result["applied"]
    conn = db.connect(path)
    rows = dict(conn.execute("SELECT id, laundry FROM trips").fetchall())
    assert rows == {"washing": '{"every": 3}', "not": None}
    conn.close()
