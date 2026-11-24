"""A trip covers today (closet/tripday.py, and what closet/today.py does with it): on a day inside a saved trip Today
dresses for the trip's place, leads with the trip's outfit for the day and offers the rest only from the bag, by the
rules a trip under way dresses its days to come; a wear counts on the trip; "Not on this trip today" goes home for the
day and is undone; your own words win; of two trips, the one that started later; the rules choose, not Claude.
Open-Meteo is stood in for, and the trips' weather is given."""
import json
from datetime import timedelta

import pytest

from closet import db, plans, today, trips, wears, weather

from . import test_stylejobs
from .test_outfits import basic_closet
from .test_trips import days as trip_days
from .test_weather import HOME, NOON, NYC, TODAY, YORK, FakeOpenMeteo, make_item

TOMORROW = TODAY + timedelta(days=1)


@pytest.fixture
def clock(monkeypatch):
    """The computer's day (moved by tests) and Open-Meteo stood in for (`clock["sky"].down` takes it away)."""
    now = {"day": TODAY, "sky": FakeOpenMeteo()}
    monkeypatch.setattr(wears, "today", lambda: now["day"])
    monkeypatch.setattr(weather, "_now", lambda: NOON)
    monkeypatch.setattr(weather, "fetch", now["sky"])
    return now


def closet(client) -> dict[str, str]:
    """Enough for a few cool days: four tops, two bottoms, two pairs of shoes and a jacket."""
    def piece(key, name, category, color, **more):
        return make_item(client, key, name=name, category=category, color=color, formality="casual", **more)
    return {
        "tee1": piece("a", "White tee", "tee", "white", silhouette={"sleeve": "short"}),
        "tee2": piece("b", "Grey tee", "tee", "grey", silhouette={"sleeve": "short"}),
        "tee3": piece("c", "Navy tee", "tee", "navy", silhouette={"sleeve": "short"}),
        "shirt": piece("d", "Blue shirt", "shirt", "light_blue"),
        "jeans": piece("e", "Blue jeans", "jeans", "blue"),
        "chinos": piece("f", "Tan chinos", "trousers", "tan"),
        "sneakers": piece("g", "White sneakers", "sneakers", "white"),
        "boots": piece("h", "Brown boots", "boots", "brown"),
        "jacket": piece("i", "Navy jacket", "jacket", "navy"),
    }


def make_trip(client, first, last, place=YORK, **more) -> dict:
    n = (last - first).days + 1
    given = [{"date": (first + timedelta(days=i)).isoformat(), "low_c": 12, "high_c": 18, "rain": False} for i in range(n)]
    r = client.post("/api/trips", json={"place": place, "first_day": first.isoformat(), "last_day": last.isoformat(),
                                        "weather": given, **more})
    assert r.status_code == 201, r.text
    return r.json()


def suggest(client, **body) -> dict:
    r = client.post("/api/outfits/today", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def ids_of(outfit) -> set[str]:
    return set(plans.ids_of(outfit["pieces"]))


def bag_of(trip) -> set[str]:
    return {p["id"] for p in trip["plan"]["packed"]}


def wear(client, outfit, day=None):
    body = {"item_ids": sorted(ids_of(outfit)), "outfit": {
        "pieces": outfit["pieces"], "score": outfit["score"], "reasons": outfit["reasons"], "warnings": outfit["warnings"],
        "context": {"low_c": 12, "high_c": 18, "rain": False, "occasion": "casual", "mood": "usual"}}}
    if day:
        body["worn_on"] = day.isoformat()
    r = client.post("/api/wears", json=body)
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------------ the bag's rule, pure
def test_only_what_is_in_the_bag_can_be_worn_and_each_piece_no_more_often_than_its_kind_allows():
    items = basic_closet()
    days = trip_days(3)
    before = trips.plan(items, days, {}, None)
    bag = {p["id"] for p in before["packed"]}
    first, second = days[0]["date"], days[1]["date"]
    free = trips.free_on(items, days, {}, None, first, carried=bag)
    assert free and free <= bag
    # a piece in the laundry at home, but in the bag, is with you
    in_wash = sorted(bag)[0]
    washed = [{**i, "laundry": "laundry"} if i["id"] == in_wash else i for i in items]
    assert in_wash in trips.free_on(washed, days, {}, None, first, carried=bag)
    # a top worn on day one (tops once before washing) is not offered on day two; a jacket still is
    worn_day = before["days"][0]
    top = worn_day["outfit"]["pieces"]["base"]
    after = trips.free_on(items, days, {}, None, second, kept={first: worn_day}, carried=bag)
    assert top not in after and top in free
    outer = worn_day["outfit"]["pieces"]["outer"]
    assert outer is None or outer in after
    # laundry every day: washed on day two, it can be worn again on day three
    third = days[2]["date"]
    assert top not in trips.free_on(items, days, {}, None, third, kept={first: worn_day}, carried=bag)
    assert top in trips.free_on(items, days, {"laundry": {"every": 1}}, None, third, kept={first: worn_day}, carried=bag)
    # nothing in the bag: nothing to wear; a day outside the trip: nothing
    assert trips.free_on(items, days, {}, None, first, carried=()) == frozenset()
    assert trips.free_on(items, days, {}, None, "2030-01-01", carried=bag) == frozenset()


# ------------------------------------------------------------------ Today on a trip day
def test_a_trip_that_covers_today_leads_with_its_outfit_at_its_place_and_offers_only_the_bag(client, clock):
    closet(client)
    trip = make_trip(client, TODAY, TODAY + timedelta(days=2))
    home_only = make_item(client, "z", name="Red flannel shirt", category="shirt", color="red", formality="casual")
    body = suggest(client, occasion="casual", mood="usual")
    ctx = body["context"]
    assert ctx["on_trip"] == {"id": trip["id"], "place": YORK["name"], "first_day": TODAY.isoformat(),
                              "last_day": (TODAY + timedelta(days=2)).isoformat(), "day": 1, "days": 3, "aside": False,
                              "occasion": "casual", "planned": {"kept": ctx["on_trip"]["planned"]["kept"], "unavailable": []}}
    # the weather of where you are, looked up again for today there
    assert ctx["place"] == YORK["name"] and ctx["source"] == "forecast" and (ctx["low_c"], ctx["high_c"]) != (12, 18)
    assert ("api.open-meteo.com/v1/forecast", "53.9576") in [(u, p.get("latitude")) for u, p in clock["sky"].calls]
    # first the trip's outfit for today, then the bag's
    planned = trip["plan"]["days"][0]["outfit"]
    assert ids_of(body["outfits"][0]) == ids_of(planned)
    bag = bag_of(trip)
    assert len(body["outfits"]) > 1 and all(ids_of(o) <= bag for o in body["outfits"])
    assert all(home_only not in ids_of(o) for o in body["outfits"])
    assert "stylist" not in ctx   # the rules choose on a trip day


def test_another_occasion_on_a_trip_day_is_dressed_from_the_bag_without_the_trips_outfit_first(client, clock):
    closet(client)
    trip = make_trip(client, TODAY, TODAY + timedelta(days=2))
    body = suggest(client, occasion="smart_casual", mood="usual")
    assert body["context"]["on_trip"]["planned"] is None
    assert all(ids_of(o) <= bag_of(trip) for o in body["outfits"])


def test_when_the_weather_cannot_be_had_the_trip_s_own_weather_for_today_stands(client, clock, services):
    closet(client)
    trip = make_trip(client, TODAY, TODAY + timedelta(days=2))
    clock["sky"].down = True
    ctx = suggest(client, occasion="casual")["context"]
    assert (ctx["low_c"], ctx["high_c"], ctx["place"]) == (12, 18, YORK["name"])
    assert ctx["old"] is False and ctx["message"] is None   # a day typed for the trip says nothing more
    # a forecast the trip kept from before says so, once
    conn = db.connect(services.cfg.db_path(services.state.get("profile")))
    conn.execute("UPDATE trips SET weather = ? WHERE id = ?",
                 (json.dumps([{**d, "source": "forecast"} for d in trip["weather"]]), trip["id"]))
    conn.close()
    ctx = suggest(client, occasion="casual")["context"]
    assert ctx["old"] is True and ctx["message"] == today.TRIP_WEATHER and ctx["source"] == "forecast"


def test_a_wear_on_a_trip_day_counts_on_the_trip(client, clock):
    closet(client)
    trip = make_trip(client, TODAY, TODAY + timedelta(days=2))
    body = suggest(client, occasion="casual")
    other = body["outfits"][1]   # not the trip's outfit: what you wore is what counts
    assert wear(client, other)["worn_on"] == TODAY.isoformat()
    top = other["pieces"]["base"]
    clock["day"] = TOMORROW
    body = suggest(client, occasion="casual")
    assert body["context"]["on_trip"]["day"] == 2
    assert body["outfits"] and all(top not in ids_of(o) for o in body["outfits"])   # tops once before washing
    # planned again, the day gone is what you wore, not what the plan had
    again = client.patch(f"/api/trips/{trip['id']}", json={"replan": True}).json()
    assert ids_of(again["plan"]["days"][0]["outfit"]) == ids_of(other)
    assert all(top not in ids_of(d["outfit"]) for d in again["plan"]["days"][1:] if d["outfit"])


def test_not_on_this_trip_today_dresses_from_home_for_the_day_and_is_undone(client, clock):
    closet(client)
    trip = make_trip(client, TODAY, TODAY + timedelta(days=2))
    home_only = make_item(client, "z", name="Red flannel shirt", category="shirt", color="red", formality="casual")
    r = client.put(f"/api/trips/{trip['id']}/aside")
    assert r.status_code == 200 and r.json() == {"aside": True, "day": TODAY.isoformat()}
    for _ in range(2):   # kept on the server: a reload, or the phone, says the same
        ctx = suggest(client, occasion="casual", build_around=home_only)["context"]
        assert ctx["on_trip"]["aside"] is True and ctx["on_trip"]["planned"] is None
        assert ctx["place"] == HOME["name"]   # home's weather
    # the whole closet: a piece at home can be built around and its outfit uses the closet
    assert client.delete(f"/api/trips/{trip['id']}/aside").json() == {"aside": False, "day": TODAY.isoformat()}
    ctx = suggest(client, occasion="casual")["context"]
    assert ctx["on_trip"]["aside"] is False and ctx["place"] == YORK["name"]
    # set aside for one day only
    client.put(f"/api/trips/{trip['id']}/aside")
    clock["day"] = TOMORROW
    assert suggest(client, occasion="casual")["context"]["on_trip"]["aside"] is False


def test_a_wear_at_home_on_a_day_the_trip_is_set_aside_is_not_that_trip_days_outfit_when_planned_again(client, clock):
    """Review 2, a suspicion shown: with the trip set aside for the day ("Not on this trip today") you wear an outfit
    from home, with a shirt you never packed. Planning the trip again that day took that outfit as the trip's for the
    day and put the shirt left at home on the packing list (so Today on the days after would offer it from the bag).
    A day set aside is not a day of the trip: its wear is not the trip's."""
    closet(client)
    trip = make_trip(client, TODAY, TODAY + timedelta(days=2))
    home_only = make_item(client, "z", name="Red flannel shirt", category="shirt", color="red", formality="casual")
    assert client.put(f"/api/trips/{trip['id']}/aside").status_code == 200
    at_home = suggest(client, occasion="casual", build_around=home_only)["outfits"][0]
    wear(client, at_home)
    again = client.patch(f"/api/trips/{trip['id']}", json={"replan": True})
    assert again.status_code == 200, again.text
    plan = again.json()["plan"]
    assert home_only not in {p["id"] for p in plan["packed"]}, "the shirt left at home is on the packing list"
    assert plan["days"][0]["outfit"]["pieces"] != at_home["pieces"]


def test_only_the_trip_you_are_on_today_can_be_set_aside(client, clock):
    closet(client)
    later = make_trip(client, TODAY + timedelta(days=5), TODAY + timedelta(days=6))
    assert client.put(f"/api/trips/{later['id']}/aside").status_code == 422
    assert client.put("/api/trips/no-such-trip/aside").status_code == 404
    assert client.delete(f"/api/trips/{later['id']}/aside").json()["aside"] is False


# ------------------------------------------------------------------ who wins
def test_a_note_that_puts_you_somewhere_else_and_an_outfit_planned_for_today_win_over_the_trip(client, clock, services):
    ids = closet(client)
    # planned for tomorrow before the trip was saved: that morning the plan is dressed as on any day
    pieces = {"base": ids["tee1"], "mid": None, "outer": None, "bottom": ids["jeans"], "shoes": ids["sneakers"],
              "accessories": []}
    assert client.put(f"/api/plans/{TOMORROW.isoformat()}", json={"pieces": pieces}).status_code == 200
    make_trip(client, TODAY, TODAY + timedelta(days=2))
    assert suggest(client, occasion="casual")["context"].get("on_trip")
    services.state.update(day_note={"text": "In New York today", "from": TODAY.isoformat(), "to": TODAY.isoformat(),
                                    "place": NYC, "place_asked": "New York", "outside": None, "exposure": "mixed",
                                    "activity": "", "occasion": None})
    ctx = suggest(client, occasion="casual")["context"]
    assert "on_trip" not in ctx and ctx["place"] == NYC["name"]
    services.state.update(day_note=None)
    clock["day"] = TOMORROW
    body = suggest(client, occasion="casual")
    assert "on_trip" not in body["context"] and body["context"]["plan"]["kept"]
    assert ids_of(body["outfits"][0]) == set(plans.ids_of(pieces))


def test_building_around_a_piece_and_wearing_an_outfit_again_stay_on_the_trip(client, clock):
    closet(client)
    trip = make_trip(client, TODAY, TODAY + timedelta(days=2))
    bag = bag_of(trip)
    home_only = make_item(client, "z", name="Red flannel shirt", category="shirt", color="red", formality="casual")
    body = suggest(client, occasion="casual", build_around=home_only)
    assert body["context"]["on_trip"]["planned"] is None
    assert body["outfits"] and all(home_only in ids_of(o) and ids_of(o) - {home_only} <= bag for o in body["outfits"])
    # an outfit worn at home before the trip: its pieces that stayed at home are filled from the bag
    worn_before = client.post("/api/outfits/worn", json={"item_ids": [home_only, *sorted(bag)[:1]],
                                                         "worn_on": (TODAY - timedelta(days=3)).isoformat()}).json()
    body = suggest(client, occasion="casual", again=worn_before["id"])
    assert home_only in body["context"]["again"]["unavailable"]
    assert all(ids_of(o) <= bag for o in body["outfits"])


def test_of_two_trips_holding_the_day_the_one_that_started_later_is_the_one_you_are_on(client, clock):
    closet(client)
    make_trip(client, TODAY, TODAY + timedelta(days=6), place=NYC)
    inside = make_trip(client, TOMORROW, TOMORROW + timedelta(days=1))
    # a day ahead names it too
    assert suggest(client, day=TOMORROW.isoformat())["context"]["trip"]["id"] == inside["id"]
    clock["day"] = TOMORROW
    assert suggest(client, occasion="casual")["context"]["on_trip"]["id"] == inside["id"]


def test_a_trip_that_packed_nothing_dresses_from_the_whole_closet_at_its_place(client, clock, services):
    closet(client)
    trip = make_trip(client, TODAY, TODAY + timedelta(days=1))
    conn = db.connect(services.cfg.db_path(services.state.get("profile")))
    conn.execute("UPDATE trips SET plan = ? WHERE id = ?", (json.dumps({"days": [], "packed": []}), trip["id"]))
    conn.close()
    body = suggest(client, occasion="casual")
    assert body["outfits"] and body["context"]["place"] == YORK["name"] and body["context"]["on_trip"]["planned"] is None


def test_on_a_trip_that_packed_nothing_today_says_the_real_reason(client, clock):
    """Review 2, finding 8. Everything is in the laundry, and a trip starts today: it packs nothing. Today then dresses
    from the whole closet at the trip's place ("a trip that packed nothing is no bag") and finds nothing. "Nothing you
    packed makes an outfit for today" would be untrue twice over: nothing was packed, and the whole closet is what was
    just tried. The reason the rules gave (everything is in the laundry) stands, as it does once the trip is set aside."""
    ids = closet(client)
    for i in ids.values():
        assert client.post(f"/api/items/{i}/laundry", json={"state": "laundry"}).status_code == 200
    trip = make_trip(client, TODAY, TOMORROW)
    assert trip["plan"]["packed"] == []
    answer = suggest(client, low_c=12, high_c=18, rain=False)
    assert answer["context"]["on_trip"] and answer["outfits"] == []
    assert answer["missing"] != [today.NOTHING_IN_THE_BAG], answer["missing"]
    assert any("in the laundry" in m for m in answer["missing"])


# ------------------------------------------------------------------ Claude
styled = test_stylejobs.styled


def test_claude_does_not_choose_on_a_trip_day_and_does_again_once_the_trip_is_set_aside(styled, monkeypatch):
    monkeypatch.setattr(wears, "today", lambda: test_stylejobs.TODAY)
    test_stylejobs.wardrobe(styled.c)
    first = test_stylejobs.TODAY
    given = [{"date": (first + timedelta(days=i)).isoformat(), "low_c": 8, "high_c": 14, "rain": False} for i in range(2)]
    trip = styled.c.post("/api/trips", json={"place": YORK, "first_day": first.isoformat(),
                                             "last_day": (first + timedelta(days=1)).isoformat(), "weather": given}).json()
    body = test_stylejobs.today(styled.c)
    assert body["context"]["on_trip"]["id"] == trip["id"] and body["context"].get("stylist") is None
    assert styled.held == [] and styled.stand_in.calls == []
    r = styled.c.post("/api/outfits/today", json={**test_stylejobs.DAY, "say": "Too plain?"})
    assert r.status_code == 422 and "Claude isn't choosing" in r.json()["detail"]
    styled.c.put(f"/api/trips/{trip['id']}/aside")
    assert test_stylejobs.today(styled.c)["context"]["stylist"]["state"] == "working"


def test_an_outing_stays_off_on_a_trip_day_even_set_aside(styled, monkeypatch):
    from . import test_outing_today
    monkeypatch.setattr(wears, "today", lambda: test_stylejobs.TODAY)
    test_outing_today.off(styled)
    test_outing_today.closet_with_outing(styled)
    first = test_stylejobs.TODAY
    given = [{"date": first.isoformat(), "low_c": 8, "high_c": 14, "rain": False}]
    trip = styled.c.post("/api/trips", json={"place": YORK, "first_day": first.isoformat(), "last_day": first.isoformat(),
                                             "weather": given}).json()
    styled.c.put(f"/api/trips/{trip['id']}/aside")
    assert not any("outing" in o for o in test_stylejobs.today(styled.c)["outfits"])
    assert test_outing_today.outings(styled.cfg, styled.sv.state.get("profile")) == []


# ------------------------------------------------------------------ from a piece's page, and the occasion kept
def test_a_piece_of_the_bag_in_the_laundry_at_home_can_be_built_around_on_a_trip_day_and_its_page_says_so(client, clock):
    closet(client)
    trip = make_trip(client, TODAY, TODAY + timedelta(days=2))
    home_only = make_item(client, "z", name="Red flannel shirt", category="shirt", color="red", formality="casual")
    packed = next(p["id"] for p in trip["plan"]["packed"] if p["group"] == "tops")
    for piece in (packed, home_only):
        assert client.post(f"/api/items/{piece}/laundry", json={"state": "laundry"}).status_code == 200
    # the piece's page: the packed one is with you and clean; the one at home is in its laundry
    assert client.get(f"/api/items/{packed}").json()["build_around"] is None
    assert client.get(f"/api/items/{home_only}").json()["build_around"] == "laundry"
    # Today opened from it (`?around=` asks build_around): built around the packed piece, the rest from the bag
    body = suggest(client, occasion="casual", build_around=packed)
    assert body["outfits"] and all(packed in ids_of(o) and ids_of(o) <= bag_of(trip) for o in body["outfits"])
    # the one at home in its laundry: refused as at home, in the same words
    assert "in the laundry" in suggest(client, occasion="casual", build_around=home_only)["missing"][0]
    # set aside, the laundry at home counts again, on the page too
    client.put(f"/api/trips/{trip['id']}/aside")
    assert client.get(f"/api/items/{packed}").json()["build_around"] == "laundry"


def test_a_piece_of_the_bag_at_the_cleaners_at_home_can_be_built_around_on_a_trip_day_and_its_page_says_so(client,
                                                                                                         clock):
    """Review 2, a suspicion tried: a piece in the bag of today's trip that the closet says is at the cleaner's is with
    you, as Today counts it (it builds around it); its page should not say "Once it's back"."""
    closet(client)
    trip = make_trip(client, TODAY, TODAY + timedelta(days=2))
    piece = sorted(bag_of(trip))[0]
    assert client.put(f"/api/items/{piece}/away", json={"place": "cleaner"}).status_code == 200
    around = suggest(client, occasion="casual", build_around=piece)
    assert around["outfits"] and all(piece in ids_of(o) for o in around["outfits"])
    assert client.get(f"/api/items/{piece}").json()["build_around"] is None


def test_on_a_trip_day_the_occasion_this_device_kept_gives_way_to_the_trips_and_the_answer_says_which(client, clock):
    closet(client)
    trip = make_trip(client, TODAY, TODAY + timedelta(days=2), occasion="casual")
    # the page's first ask of a visit: the occasion kept from another day, not a tap
    body = suggest(client, occasion="smart_casual", mood="usual", occasion_kept=True)
    assert body["context"]["occasion"] == "casual" and body["context"]["on_trip"]["planned"] is not None
    assert ids_of(body["outfits"][0]) == ids_of(trip["plan"]["days"][0]["outfit"])
    # a tap is the owner's own choice
    body = suggest(client, occasion="smart_casual", mood="usual", occasion_kept=False)
    assert body["context"]["occasion"] == "smart_casual" and body["context"]["on_trip"]["planned"] is None
    # at home the kept occasion is the one dressed for, as always; set aside is at home
    client.put(f"/api/trips/{trip['id']}/aside")
    assert suggest(client, occasion="smart_casual", occasion_kept=True)["context"]["occasion"] == "smart_casual"
    assert client.post("/api/outfits/today", json={"occasion_kept": "yes"}).status_code == 422
