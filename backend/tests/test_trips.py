import copy
import random
import time
from datetime import date, timedelta

import pytest

from closet import db, outfits, plans, trips, tripweather, wears, weather

from .test_outfits import basic_closet, day, demo_items, item

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


def first_demo_items():
    """The demo closet as it was before its second wave of items (a parka among them): one warm outer layer,
    so a trip of cool days can always be covered with one, and one-day trips where the fewest pieces are the
    engine's best."""
    return [i for i in demo_items() if i.get("wave") != 2]


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
        result = trips.plan(first_demo_items(), days(10), {"laundry": laundry}, TOPS_TWICE)
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


def test_a_piece_in_the_laundry_today_is_packed_for_a_trip_far_enough_off():
    # what is in the wash today is clean again by a trip three or more days away; only a trip about to start goes without it
    items = basic_closet()
    items[0]["laundry"] = "laundry"
    soon = trips.plan(items, days(2), {"pin": ["tee1"]}, today=FIRST - timedelta(days=1))
    assert "tee1" not in {p["id"] for p in soon["packed"]}
    later = trips.plan(items, days(2), {"pin": ["tee1"]}, today=FIRST - timedelta(days=trips.CLEAN_BY_DAYS))
    assert "tee1" in {p["id"] for p in later["packed"]}
    assert not any("in the laundry" in n for n in later["notes"])


def test_a_trip_packs_a_piece_due_back_from_the_cleaners_as_clean_like_a_day_ahead_does():
    """Review 2, finding 2. The only wearable bottoms are jeans you took to the cleaner's out of the laundry basket,
    expected back tomorrow; the trip starts the day after. A trip packs an away piece expected back before the first
    day "as it will be by then", and back from the cleaner's a piece is clean: "Dress for another day" does exactly
    that (`plans.back_by`) and offers the jeans for the trip's first day, and the trip packs them too, saying it
    counts on them being back."""
    thursday = date(2026, 11, 12)
    first = thursday + timedelta(days=2)
    items = [i for i in basic_closet() if i["category"] not in ("trousers", "shorts")]
    jeans = next(i for i in items if i["id"] == "jeans1")
    jeans.update(laundry="laundry", away="cleaner", away_since="2026-11-10",
                 away_until=(first - timedelta(days=1)).isoformat())
    # a day ahead, by the same rule, counts them back and clean
    ahead = outfits.suggest(plans.back_by(items, first), day(4, 10), 3)
    assert ahead["outfits"] and all(o["pieces"]["bottom"] == "jeans1" for o in ahead["outfits"])
    # the trip starting that day
    plan = trips.plan(items, days(2, first=first), {}, None, today=thursday)
    assert "jeans1" in {p["id"] for p in plan["packed"]}, plan["uncovered"]
    assert any("counts on" in n and "back" in n for n in plan["notes"]), plan["notes"]


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


@pytest.mark.parametrize("weather", [{"high_c": 28}, {"feels_high_c": 26}])
@pytest.mark.parametrize("laundry, count", [(None, 4), ({"day": 2}, 3)])
def test_whole_trip_rewear_still_needs_fresh_tops_on_hot_days(weather, laundry, count):
    result = trips.plan(shirt_closet(6, "tee"), mild(4, **weather), {"laundry": laundry},
                        {"tops": None, "bottoms": None})
    assert result["uncovered"] == []
    assert len(packed_of(result, "tee")) == count
    assert len(packed_of(result, "trousers")) == 1
    assert next(c["words"] for c in result["counts"] if c["kind"] == "tops").startswith(
        f"{count} tees: one a day, as every day is hot or humid")
    if laundry:
        assert "tees" in result["washes"][0]["words"]


def test_whole_trip_rewear_keeps_cool_days_but_not_a_sweaty_top():
    closet = shirt_closet(6, "tee")
    assert len(packed_of(trips.plan(closet, mild(4), rewear={"tops": None}), "tee")) == 1
    mixed = mild(4)
    mixed[1]["feels_high_c"] = 26
    result = trips.plan(closet, mixed, rewear={"tops": None})
    assert result["uncovered"] == []
    assert len(packed_of(result, "tee")) == 2
    hot_tee = next(x for x in core_worn(result["days"][1]) if x.startswith("tee"))
    assert sum(hot_tee in core_worn(d) for d in result["days"]) == 1


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
    result = trips.plan(first_demo_items(), trip)
    d = trip[0]
    best = outfits.suggest(first_demo_items(), outfits.Context(d["low_c"], d["high_c"], d["rain"]), 1)["outfits"][0]
    assert result["days"][0]["outfit"]["pieces"] == best["pieces"]


# ---------------------------------------------------------------------- swimming or the beach
def trunks(id="trunks", **kw):
    return item(id, "shorts", "blue", "casual", "warm", kind="swim_trunks", name=f"Swim trunks {id}", **kw)


def hot(n, high=29, first=FIRST, source="forecast"):
    return [{"date": (first + timedelta(days=i)).isoformat(), "low_c": high - 8, "high_c": high, "rain": False,
             "rain_chance": None, "summary": None, "source": source} for i in range(n)]


def swim_ids(result):
    return [p["id"] for p in result["packed"] if p["group"] == "swim"]


def test_swimming_or_the_beach_is_parsed():
    dates = [d["date"] for d in days(3)]
    assert trips.parse_options({}, dates).swim is None   # follows the forecast
    assert trips.parse_options({"swim": True}, dates).swim is True
    assert trips.parse_options({"swim": False}, dates).swim is False
    assert trips.parse_options({"swim": None}, dates).swim is None
    for bad in ("yes", 1, [], {}):
        with pytest.raises(trips.PlanError, match="Swimming or the beach must be true, false"):
            trips.parse_options({"swim": bad}, dates)


@pytest.mark.parametrize("weather, choice, on, hot_days", [
    (days(5), None, False, 0),                          # cool days: off
    (hot(3, high=26), None, False, 0),                  # just under the owner's hottest band: off
    (hot(1, high=27) + days(4, first=FIRST + timedelta(days=1)), None, True, 1),   # one day reaching 27°C turns it on
    (hot(3, high=31), None, True, 3),
    (hot(3, high=31, source="unknown"), None, False, 0),   # weather not known yet is not a hot day
    (hot(3, high=31), False, False, 3),                 # the owner's word wins either way
    (days(5), True, True, 0),
])
def test_swimming_turns_on_by_itself_for_a_hot_forecast_and_the_owners_word_wins(weather, choice, on, hot_days):
    result = trips.plan(basic_closet() + [trunks()], weather, {"swim": choice})
    assert result["swim"] == {"on": on, "hot_days": hot_days, "hot_c": trips.SWIM_HOT_C, "missing": None}
    assert swim_ids(result) == (["trunks"] if on else [])


@pytest.mark.parametrize("n, want", [(1, ["loved"]), (7, ["loved"]), (8, ["loved", "plain"]), (14, ["loved", "plain"])])
def test_one_pair_for_up_to_a_week_and_two_for_longer(n, want):
    closet = basic_closet() + [trunks("plain"), trunks("loved", rating="love"), trunks("meh", rating="meh"),
                               trunks("gone", status="archived")]
    result = trips.plan(closet, hot(n), rewear={"tops": None})
    assert swim_ids(result) == want
    pair = next(c for c in result["counts"] if c["kind"] == "swim")
    assert pair == ({"kind": "swim", "count": 1, "words": "1 pair of swim trunks: one for a trip of up to a week"} if n <= 7
                    else {"kind": "swim", "count": 2, "words": "2 pairs of swim trunks: two for a trip of more than a week"})
    assert all(p["days"] == 0 and not p["pinned"] for p in result["packed"] if p["group"] == "swim")
    assert {f"item:{i}" for i in swim_ids(result)} <= set(trips.lines(result))   # each can be ticked as packed


def test_never_more_swim_trunks_than_can_be_packed_and_the_ones_asked_for_first():
    long = hot(10)
    only = trips.plan(basic_closet() + [trunks()], long)
    assert swim_ids(only) == ["trunks"]
    assert next(c for c in only["counts"] if c["kind"] == "swim")["words"] == "1 pair of swim trunks: the only pair you can pack"
    three = basic_closet() + [trunks("a", rating="love"), trunks("b"), trunks("c")]
    asked = trips.plan(three, hot(3), {"pin": ["c", "b"]})
    assert sorted(swim_ids(asked)) == ["b", "c"]   # the two asked for, though a short trip takes one
    assert next(c for c in asked["counts"] if c["kind"] == "swim")["words"] == "2 pairs of swim trunks: the ones you chose"
    assert all(p["pinned"] for p in asked["packed"] if p["group"] == "swim")
    left = trips.plan(three, hot(3), {"leave_out": ["a"]})
    assert swim_ids(left) == ["b"]


def test_with_swimming_on_and_no_swim_trunks_the_trip_says_so():
    result = trips.plan(basic_closet(), hot(3))
    assert result["swim"]["on"] and result["swim"]["missing"] == "You have no swim trunks in your closet."
    assert swim_ids(result) == [] and not any(c["kind"] == "swim" for c in result["counts"])
    assert {p["id"] for p in result["packed"]} <= {i["id"] for i in basic_closet()}   # nothing made up
    archived = trips.plan(basic_closet() + [trunks(status="archived")], hot(3))
    assert archived["swim"]["missing"] == "You have no swim trunks in your closet."
    washing = trips.plan(basic_closet() + [trunks(laundry="laundry"), trunks("b", rating="dislike")], hot(3))
    assert washing["swim"]["missing"] == "None of your swim trunks can be packed: 1 in the laundry and 1 rated dislike."
    assert trips.plan(basic_closet(), hot(3), {"swim": False})["swim"]["missing"] is None   # off: nothing to say


def test_swim_trunks_never_fill_a_days_outfit():
    # a hot week where the only shorts are swim trunks: the days are dressed without them, and they are packed beside
    closet = [i for i in basic_closet() if i["id"] != "shorts1"] + [trunks()]
    result = trips.plan(closet, hot(2, high=33))
    assert swim_ids(result) == ["trunks"]
    assert all(d["outfit"] and d["outfit"]["pieces"]["bottom"] != "trunks" for d in result["days"])
    # asked for on a trip without swimming, they are taken, still in no outfit and with no note that no day wears them
    asked = trips.plan(closet, days(4), {"pin": ["trunks"]})
    assert asked["swim"]["on"] is False and swim_ids(asked) == ["trunks"]
    assert all("trunks" not in worn(d) for d in asked["days"] if d["outfit"])
    assert not any("trunks" in n.lower() for n in asked["notes"])
    assert next(c for c in asked["counts"] if c["kind"] == "swim")["words"] == "1 pair of swim trunks: the pair you chose"


def test_shoes_for_a_sport_are_packed_only_when_asked_for_and_never_fill_a_day():
    # the only sneakers are for tennis and golf: the days are dressed without them, and they are not taken
    sport = [item("tennis", "sneakers", "white", "athletic", kind="tennis_shoe", name="Tennis shoes"),
             item("golf", "sneakers", "white", "athletic", kind="golf_shoe", name="Golf shoes")]
    closet = [i for i in basic_closet() if i["id"] != "sneakers1"] + sport
    plain = trips.plan(closet, days(4))
    assert not {p["id"] for p in plain["packed"]} & {"tennis", "golf"}
    assert all(not {"tennis", "golf"} & set(worn(d)) for d in plain["days"] if d["outfit"])
    # asked for, a pair is packed with the shoes, worn on no day, with no note that no day wears it
    asked = trips.plan(closet, days(4), {"pin": ["tennis"]})
    assert next(p for p in asked["packed"] if p["id"] == "tennis") == {"id": "tennis", "group": "shoes", "days": 0,
                                                                         "pinned": True}
    assert all("tennis" not in worn(d) for d in asked["days"] if d["outfit"])
    assert "golf" not in {p["id"] for p in asked["packed"]}
    assert not any("tennis" in n.lower() for n in asked["notes"])
    assert "item:tennis" in trips.lines(asked)   # it can be ticked as packed
    # a pair in the laundry is not packed, and the plan says why
    washing = trips.plan([{**i, "laundry": "laundry"} if i["id"] == "tennis" else i for i in closet], days(4),
                         {"pin": ["tennis"]})
    assert "tennis" not in {p["id"] for p in washing["packed"]}
    assert any("in the laundry" in n for n in washing["notes"])


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


def added(client):
    """The trips listed, less the one the demo closet comes with (closet/demo.py)."""
    return [t for t in client.get("/api/trips").json()["trips"] if t["place"]["name"] != "Lisbon, Portugal"]


def body(n=5, **kw):
    trip = days(n, first=TODAY + timedelta(days=20))
    return {"place": NYC, "first_day": trip[0]["date"], "last_day": trip[-1]["date"],
            "weather": [{k: d[k] for k in ("date", "low_c", "high_c", "rain")} for d in trip], **kw}


def test_planning_saves_nothing_and_saving_keeps_the_trip(client, clock):
    client.post("/api/profile", json={"profile": "demo"})
    r = client.post("/api/trips/plan", json=body())
    assert r.status_code == 200, r.text
    plan = r.json()
    assert "id" not in plan and plan["place"] == NYC and len(plan["plan"]["days"]) == 5
    assert [d["source"] for d in plan["weather"]] == ["given"] * 5
    assert plan["lines"] == trips.lines(plan["plan"])
    assert added(client) == []

    r = client.post("/api/trips", json=body(occasion="smart_casual", laundry={"day": 3}))
    assert r.status_code == 201, r.text
    trip = r.json()
    assert trip["occasion"] == "smart_casual" and trip["laundry"] == {"day": 3} and trip["packed"] == []
    assert trip["plan"]["laundry"] == {"day": 3} and trip["plan"]["washes"][0]["day"] == 3
    assert client.get(f"/api/trips/{trip['id']}").json() == trip
    listed = added(client)
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
    assert added(client)[0]["packed"] == 1


def test_a_tick_sent_again_is_one_tick(client, clock):
    # a tick kept on the phone while Nines could not be reached, sent when it answers and again after a lost answer
    client.post("/api/profile", json={"profile": "demo"})
    trip = client.post("/api/trips", json=body()).json()
    line = trip["lines"][0]
    for _ in range(2):
        r = client.patch(f"/api/trips/{trip['id']}", json={"ticks": {line: True}})
        assert r.status_code == 200 and r.json()["packed"] == [line]
    for _ in range(2):
        assert client.patch(f"/api/trips/{trip['id']}", json={"ticks": {line: False}}).json()["packed"] == []
    assert added(client)[0]["packed"] == 0


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
    ({"swim": "yes"}, "Swimming or the beach must be true, false"),
])
def test_wrong_input_is_answered_in_plain_words(client, clock, change, words):
    r = client.post("/api/trips/plan", json={**body(), **change})
    assert r.status_code == 422 and words in r.json()["detail"], r.text


@pytest.mark.parametrize("path", ["/api/trips/plan", "/api/trips"])
@pytest.mark.parametrize("invalid", [{"date": []}, {"date": {}}, {"low_c": 10**400}])
def test_malformed_given_weather_is_rejected_without_saving(client, clock, path, invalid):
    request = body(1)
    request["weather"][0].update(invalid)
    response = client.post(path, json=request)
    assert response.status_code == 422
    assert response.json()["detail"]
    assert client.get("/api/trips").json()["trips"] == []


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
    assert [t["id"] for t in added(client)] == [soon["id"], later["id"]]
    monkeypatch.setattr(wears, "today", lambda: TODAY + timedelta(days=12))  # the soon trip is over
    listed = added(client)
    assert [t["id"] for t in listed] == [later["id"], soon["id"]] and listed[1]["past"] is True
    assert client.delete(f"/api/trips/{soon['id']}").status_code == 204
    assert [t["id"] for t in added(client)] == [later["id"]]


def test_the_demo_closet_and_the_real_closet_keep_their_trips_apart(client, clock):
    client.post("/api/profile", json={"profile": "demo"})
    demo_trip = client.post("/api/trips", json=body()).json()
    client.post("/api/profile", json={"profile": "main"})
    assert client.get("/api/trips").json() == {"trips": []}
    assert client.get(f"/api/trips/{demo_trip['id']}").status_code == 404
    real = client.post("/api/trips", json=body()).json()
    assert real["plan"]["packed"] == [] and real["plan"]["uncovered"]  # nothing in the real closet yet
    client.post("/api/profile", json={"profile": "demo"})
    assert [t["id"] for t in added(client)] == [demo_trip["id"]]


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


def test_swimming_on_a_saved_trip_follows_the_forecast_until_the_owner_says(client, clock):
    client.post("/api/profile", json={"profile": "demo"})
    shorts = next(i for i in client.get("/api/items").json()["items"] if i["category"] == "shorts")
    assert client.put(f"/api/items/{shorts['id']}/kind", json={"kind": "swim_trunks"}).status_code == 200
    warm = body(5)
    for d in warm["weather"][2:]:
        d["high_c"] = 30
    trip = client.post("/api/trips", json=warm).json()
    assert trip["swim"] is None and trip["plan"]["swim"]["on"] is True and trip["plan"]["swim"]["hot_days"] == 3
    assert next(p for p in trip["plan"]["packed"] if p["id"] == shorts["id"])["group"] == "swim"
    assert f"item:{shorts['id']}" in trip["lines"]
    # the owner's word is kept, through a plan made again
    r = client.patch(f"/api/trips/{trip['id']}", json={"swim": False})
    assert r.status_code == 200, r.text
    assert r.json()["swim"] is False and r.json()["plan"]["swim"]["on"] is False
    assert all(p["id"] != shorts["id"] for p in r.json()["plan"]["packed"])
    again = client.patch(f"/api/trips/{trip['id']}", json={"replan": True}).json()
    assert again["swim"] is False and again["plan"]["swim"]["on"] is False
    assert client.get(f"/api/trips/{trip['id']}").json()["swim"] is False
    assert client.patch(f"/api/trips/{trip['id']}", json={"swim": None}).json()["plan"]["swim"]["on"] is True
    r = client.patch(f"/api/trips/{trip['id']}", json={"swim": "maybe"})
    assert r.status_code == 422 and "Swimming or the beach" in r.json()["detail"]
    # a cool trip turned on by the owner, in the real closet with no swim trunks
    client.post("/api/profile", json={"profile": "main"})
    planned = client.post("/api/trips/plan", json=body(3, swim=True)).json()
    assert planned["swim"] is True and planned["plan"]["swim"]["missing"] == "You have no swim trunks in your closet."


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


# ---------------------------------------------------------------------- a trip under way, and what goes beside the days
def steady_weather(url: str) -> bytes:
    """Open-Meteo with the same weather whenever it is asked: every forecast day 10 to 16°C and dry, every day in the
    archive 5 to 12°C and dry. So nothing about the weather changes between two looks."""
    import json
    from urllib.parse import parse_qs, urlsplit
    parts = urlsplit(url)
    params = {k: v[0] for k, v in parse_qs(parts.query).items()}
    if parts.netloc == "api.open-meteo.com":
        days_ = [wears.today() + timedelta(days=i) for i in range(int(params["forecast_days"]))]
        low, high = 10, 16
    else:
        start, end = date.fromisoformat(params["start_date"]), date.fromisoformat(params["end_date"])
        days_ = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        low, high = 5, 12
    daily = {"time": [d.isoformat() for d in days_], "temperature_2m_min": [low] * len(days_),
             "temperature_2m_max": [high] * len(days_), "precipitation_probability_max": [10] * len(days_),
             "weather_code": [1] * len(days_), "precipitation_sum": [0.0] * len(days_)}
    return json.dumps({"daily": daily}).encode()


@pytest.fixture
def moving_clock(monkeypatch):
    """The computer's date, moved by the test (`moving_clock[0] = ...`), with the weather service always the same."""
    now = [TODAY]
    monkeypatch.setattr(wears, "today", lambda: now[0])
    monkeypatch.setattr(weather, "fetch", steady_weather)
    monkeypatch.setattr(weather, "_now", lambda: 1_794_500_000.0 + (now[0] - TODAY).days * 86400)
    return now


def test_a_trip_under_way_is_not_said_to_have_new_weather_every_time_it_is_opened(client, moving_clock):
    # a five-day trip planned from the forecast; on its third day the forecast for the days to come is what it was.
    # The two days gone keep their weather: they are not "usually, on these dates", and nothing changed
    client.post("/api/profile", json={"profile": "demo"})
    r = client.post("/api/trips", json={"place": NYC, "first_day": TODAY.isoformat(),
                                        "last_day": (TODAY + timedelta(days=4)).isoformat()})
    assert r.status_code == 201, r.text
    trip = r.json()
    assert [d["source"] for d in trip["weather"]] == ["forecast"] * 5
    moving_clock[0] = TODAY + timedelta(days=2)
    check = client.get(f"/api/trips/{trip['id']}/weather").json()
    assert check["checked"] is True and check["changed"] is False
    assert check["days"][:2] == trip["weather"][:2]
    # planning again keeps the days gone as they were, weather and outfits
    again = client.patch(f"/api/trips/{trip['id']}", json={"replan": True}).json()
    assert again["weather"][:2] == trip["weather"][:2]
    assert again["plan"]["days"][:2] == trip["plan"]["days"][:2]


def test_a_saved_trip_keeps_its_ticks_and_its_days_gone_through_its_whole_life(client, moving_clock):
    """Planned a week ahead, opened the day before, on day one, mid-trip after a wear and a wash, on the last day and
    after it ended: every tick the owner made stays, and a day gone keeps the outfit it was dressed in."""
    client.post("/api/profile", json={"profile": "demo"})
    first = TODAY + timedelta(days=7)
    trip = client.post("/api/trips", json={"place": NYC, "first_day": first.isoformat(),
                                           "last_day": (first + timedelta(days=4)).isoformat()}).json()
    tid = trip["id"]
    ticks = list(trip["lines"])   # the owner packs everything
    assert client.patch(f"/api/trips/{tid}", json={"ticks": dict.fromkeys(ticks, True)}).status_code == 200

    def worn_on(trip, n):   # what day n (1 is the first) is dressed in
        p = trip["plan"]["days"][n - 1]["outfit"]["pieces"]
        return [p[k] for k in CORE if p[k]] + list(p["accessories"])

    def look(when, change):
        moving_clock[0] = when
        check = client.get(f"/api/trips/{tid}/weather").json()
        assert check["changed"] is False, (when, check)
        before = client.get(f"/api/trips/{tid}").json()
        r = client.patch(f"/api/trips/{tid}", json=change)
        assert r.status_code == 200, r.text
        after = r.json()
        assert set(ticks) <= set(after["packed"]), (when, set(ticks) - set(after["packed"]))
        gone = (when - first).days
        assert after["plan"]["days"][:max(0, gone)] == before["plan"]["days"][:max(0, gone)], when
        return after

    trip = look(first - timedelta(days=1), {"replan": True})            # the day before
    trip = look(first, {"replan": True})                                 # day one, before leaving
    day_one = worn_on(trip, 1)
    assert client.post("/api/outfits/worn", json={"item_ids": day_one, "worn_on": first.isoformat()}).status_code == 201
    moving_clock[0] = first + timedelta(days=1)
    assert any(client.get(f"/api/items/{i}").json()["laundry"] == "laundry" for i in day_one)   # the tee went in by itself
    trip = look(first + timedelta(days=1), {"swim": True})               # day two: a choice changed
    assert worn_on(trip, 1) == day_one and all(f"item:{i}" in trip["lines"] for i in day_one)
    day_two = worn_on(trip, 2)
    assert client.post("/api/outfits/worn", json={"item_ids": day_two,
                                                  "worn_on": (first + timedelta(days=1)).isoformat()}).status_code == 201
    trip = look(first + timedelta(days=2), {"laundry": {"day": 3}})      # mid-trip, a wash on day three
    assert [worn_on(trip, 1), worn_on(trip, 2)] == [day_one, day_two]
    trip = look(first + timedelta(days=4), {"replan": True})             # the last day
    ended = first + timedelta(days=6)
    moving_clock[0] = ended
    assert client.get(f"/api/trips/{tid}/weather").json()["checked"] is False
    last = client.patch(f"/api/trips/{tid}", json={"replan": True}).json()   # after it ended: nothing moves
    assert last["plan"]["days"] == trip["plan"]["days"] and last["weather"] == trip["weather"]
    assert set(ticks) <= set(last["packed"])


def test_changing_a_trip_under_way_does_not_unpack_what_was_worn_yesterday():
    # day two: the tee worn on day one went in the laundry by itself. Planned again, it is still in the suitcase
    closet = basic_closet() + [item("tee2", "tee", "grey", "casual"), item("tee3", "tee", "navy", "casual")]
    trip = days(3)
    before = trips.plan(closet, trip, {}, None, today=FIRST - timedelta(days=7))
    worn_first = before["days"][0]["outfit"]["pieces"]["base"]
    for i in closet:
        if i["id"] == worn_first:
            i["laundry"] = "laundry"
    after = trips.plan(closet, trip, {"swim": True}, None, today=FIRST + timedelta(days=1),
                       kept={trip[0]["date"]: before["days"][0]}, carried=[p["id"] for p in before["packed"]], under_way=True)
    assert worn_first in [x["id"] for x in after["packed"]]
    assert after["days"][0] == before["days"][0]
    # nothing at home is packed once the trip has begun, and what was packed stays on the list
    assert {p["id"] for p in after["packed"]} >= {p["id"] for p in before["packed"]}
    assert {p["id"] for p in after["packed"] if p["group"] != "swim"} <= {p["id"] for p in before["packed"]}


def test_a_month_away_with_one_early_wash_takes_more_than_one_set_of_sleepwear():
    # one set for every seven nights of the longest stretch between washes: 29 nights, 5; a wash on day 2, still 4
    closet = basic_closet()

    def sleepwear(options, n=30):
        return next(b["count"] for b in trips.plan(closet, days(n, lows=(12,), rain_every=99), options)["basics"]
                    if b["key"] == "sleepwear")
    assert sleepwear({}) == 5
    assert sleepwear({"laundry": {"day": 2}}) == 4
    assert sleepwear({"laundry": {"every": 7}}) == 1
    assert sleepwear({"laundry": {"day": 4}}, n=7) == 1


def test_pinned_loungewear_is_packed_beside_the_days_and_never_worn_in_them():
    # "I want to take this" on lounge pants: they go in the bag, but no day's outfit wears them out
    lounge = item("lounge", "trousers", "red", "casual", "cool", "plaid", name="Tartan lounge pants", kind="lounge_pants")
    result = trips.plan(basic_closet() + [lounge], days(5), {"pin": ["lounge"]})
    assert next(p for p in result["packed"] if p["id"] == "lounge") == {"id": "lounge", "group": "bottoms", "days": 0,
                                                                         "pinned": True}
    assert all("lounge" not in worn(d) for d in result["days"] if d["outfit"])
    assert not any("lounge" in n.lower() for n in result["notes"])


def test_tennis_or_golf_on_the_trip_packs_their_shoes_beside_the_days():
    sport = [item("tennis", "sneakers", "white", "athletic", kind="tennis_shoe", name="Tennis shoes", rating="like"),
             item("tennis_old", "sneakers", "grey", "athletic", kind="tennis_shoe", name="Old tennis shoes"),
             item("golf", "sneakers", "white", "athletic", kind="golf_shoe", name="Golf shoes", laundry="laundry")]
    closet = basic_closet() + sport
    plain = trips.plan(closet, days(4))
    assert not {p["id"] for p in plain["packed"]} & {"tennis", "tennis_old", "golf"}
    played = trips.plan(closet, days(4), {"sport": ["tennis"]})
    assert next(p for p in played["packed"] if p["id"] == "tennis") == {"id": "tennis", "group": "shoes", "days": 0,
                                                                          "pinned": False}
    assert "tennis_old" not in {p["id"] for p in played["packed"]}   # one pair, the better liked
    assert all(not {"tennis", "tennis_old"} & set(worn(d)) for d in played["days"] if d["outfit"])
    # the pair asked for comes first
    asked = trips.plan(closet, days(4), {"sport": ["tennis"], "pin": ["tennis_old"]})
    assert {p["id"] for p in asked["packed"]} & {"tennis", "tennis_old"} == {"tennis_old"}
    # golf, with the only pair in the wash: said, not packed
    golf = trips.plan(closet, days(4), {"sport": ["golf"]})
    assert "golf" not in {p["id"] for p in golf["packed"]}
    assert "None of your golf shoes can be packed: 1 in the laundry." in golf["notes"]
    assert "You have no golf shoes in your closet." in trips.plan(basic_closet(), days(4), {"sport": ["golf"]})["notes"]
    with pytest.raises(trips.PlanError, match="tennis, golf"):
        trips.parse_options({"sport": ["polo"]}, [])


def test_a_trip_day_does_not_call_a_jacket_the_warmest_you_have_while_a_warmer_coat_is_at_home():
    # the coat is in the wash and the trip starts tomorrow: the jacket is the warmest that can go, not the warmest owned
    closet = [i for i in basic_closet() if i["id"] != "coat1"] + [
        item("parka", "coat", "olive", "casual", "cool", name="Olive parka", material="down", laundry="laundry")]
    cold = [{**d, "low_c": -8, "high_c": -2, "rain": False} for d in days(2)]
    result = trips.plan(closet, cold, {}, None, today=FIRST - timedelta(days=1))
    said = " ".join(w for d in result["days"] if d["outfit"] for w in d["outfit"]["warnings"])
    assert "the warmest you have" not in said


def test_the_plan_speaks_of_trousers_and_shoes_as_plural():
    closet = basic_closet()
    closet[7]["laundry"] = "laundry"   # the jeans
    result = trips.plan(closet, days(2), {"pin": ["jeans1"]})
    assert any(n.endswith("are in the laundry, so they are not packed.") for n in result["notes"]), result["notes"]


def test_the_sport_on_a_saved_trip_is_kept_and_changed(client, clock):
    client.post("/api/profile", json={"profile": "demo"})
    trip = client.post("/api/trips", json=body(sport=["golf"])).json()
    assert trip["sport"] == ["golf"]
    assert client.get(f"/api/trips/{trip['id']}").json()["sport"] == ["golf"]
    r = client.patch(f"/api/trips/{trip['id']}", json={"sport": ["tennis", "golf"]})
    assert r.status_code == 200 and r.json()["sport"] == ["tennis", "golf"]
    assert client.patch(f"/api/trips/{trip['id']}", json={"sport": []}).json()["sport"] == []
    r = client.patch(f"/api/trips/{trip['id']}", json={"sport": "tennis"})
    assert r.status_code == 422 and "sports on a trip" in r.json()["detail"]
