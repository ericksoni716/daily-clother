import json
import urllib.error
from datetime import UTC, date, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest

from closet import wears, weather

from .conftest import upload

TODAY = date(2026, 11, 12)
NOON = datetime(2026, 11, 12, 17, 0, tzinfo=UTC).timestamp()  # noon in New York
NYC = {"name": "New York, New York, United States", "latitude": 40.7143, "longitude": -74.006, "timezone": "America/New_York"}


class FakeOpenMeteo:
    """Stands in for Open-Meteo: records every address asked for and answers from `forecast`."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.down = False
        self.forecast = {"date": TODAY.isoformat(), "low": 3.2, "high": 9.8, "chance": 70, "code": 61}

    def __call__(self, url: str) -> bytes:
        parts = urlsplit(url)
        params = {k: v[0] for k, v in parse_qs(parts.query).items()}
        self.calls.append((parts.netloc + parts.path, params))
        if self.down:
            raise urllib.error.URLError("no network")
        if parts.netloc == "geocoding-api.open-meteo.com":
            if params["name"] == "Nowhere at all":
                return b'{"generationtime_ms": 0.1}'
            return json.dumps({"results": [
                {"name": "New York", "latitude": 40.71427, "longitude": -74.00597, "timezone": "America/New_York",
                 "country": "United States", "admin1": "New York"},
                {"name": "York", "latitude": 53.95763, "longitude": -1.08271, "timezone": "Europe/London",
                 "country": "United Kingdom", "admin1": "England"},
                {"name": "Broken", "latitude": "north", "longitude": 0},
            ]}).encode()
        assert parts.netloc == "api.open-meteo.com"
        f = self.forecast
        return json.dumps({"utc_offset_seconds": -18000, "daily": {
            "time": [f["date"]], "temperature_2m_min": [f["low"]], "temperature_2m_max": [f["high"]],
            "precipitation_probability_max": [f["chance"]], "weather_code": [f["code"]]}}).encode()

    def forecasts(self) -> int:
        return sum(1 for where, _ in self.calls if where.startswith("api.open-meteo.com"))


@pytest.fixture(autouse=True)
def fake(monkeypatch):
    clock = {"now": NOON}
    monkeypatch.setattr(wears, "today", lambda: TODAY)
    monkeypatch.setattr(weather, "_now", lambda: clock["now"])
    om = FakeOpenMeteo()
    om.clock = clock
    monkeypatch.setattr(weather, "fetch", om)
    return om


def save_place(client, place=NYC):
    r = client.put("/api/settings", json={"place": place})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------- places and settings
def test_place_search_returns_a_short_list_and_sends_only_the_words(client, fake):
    r = client.get("/api/places", params={"q": "  new   york "})
    assert r.status_code == 200
    places = r.json()["places"]
    assert places == [
        {"name": "New York, United States", "latitude": 40.7143, "longitude": -74.006, "timezone": "America/New_York"},
        {"name": "York, England, United Kingdom", "latitude": 53.9576, "longitude": -1.0827, "timezone": "Europe/London"},
    ]
    assert len(fake.calls) == 1
    where, params = fake.calls[0]
    assert where == "geocoding-api.open-meteo.com/v1/search"
    assert params["name"] == "new york" and set(params) == {"name", "count", "language", "format"}
    assert client.get("/api/places", params={"q": "Nowhere at all"}).json() == {"places": []}
    assert client.get("/api/places", params={"q": " "}).json() == {"places": []} and len(fake.calls) == 2


def test_place_search_says_when_the_service_cannot_be_reached(client, fake):
    fake.down = True
    r = client.get("/api/places", params={"q": "York"})
    assert r.status_code == 502 and "Couldn't reach the weather service" in r.json()["detail"]


def test_saving_and_removing_a_place(client, fake):
    assert client.get("/api/settings").json()["place"] is None
    assert save_place(client)["place"] == NYC
    assert client.get("/api/settings").json()["place"] == NYC
    for bad, words in (({"name": "X", "latitude": 95, "longitude": 0, "timezone": "UTC"}, "latitude"),
                       ({"name": "", "latitude": 1, "longitude": 0, "timezone": "UTC"}, "name"),
                       ({"name": "X", "latitude": 1, "longitude": 0, "timezone": "Not a zone!"}, "time zone")):
        r = client.put("/api/settings", json={"place": bad})
        assert r.status_code == 422 and words in r.json()["detail"]
    assert client.get("/api/settings").json()["place"] == NYC
    assert client.put("/api/settings", json={"place": None}).json()["place"] is None
    assert client.get("/api/weather").json()["place"] is None


def test_place_and_weather_need_login(anon):
    assert anon.get("/api/places", params={"q": "York"}).status_code == 401
    assert anon.get("/api/weather").status_code == 401
    assert anon.put("/api/settings", json={"place": NYC}).status_code == 401
    assert anon.post("/api/outfits/today", json={}).status_code == 401


# ---------------------------------------------------------------------- weather
def test_no_place_saved_is_said_in_plain_words(client, fake):
    r = client.get("/api/weather")
    assert r.status_code == 200
    assert r.json() == {"place": None, "weather": None, "old": False, "is_today": False,
                        "message": "Choose where you are in Settings to see today's weather."}
    assert fake.calls == []


def test_weather_answer_and_what_is_sent(client, fake):
    save_place(client)
    r = client.get("/api/weather")
    assert r.status_code == 200
    body = r.json()
    assert body["place"] == NYC and body["old"] is False and body["message"] is None and body["is_today"] is True
    assert body["weather"] == {"date": "2026-11-12", "low_c": 3.2, "high_c": 9.8, "rain_chance": 70, "rain": True,
                               "summary": "rain", "fetched_at": "2026-11-12T17:00:00Z"}
    where, params = fake.calls[0]
    assert where == "api.open-meteo.com/v1/forecast"
    assert (params["latitude"], params["longitude"], params["timezone"]) == ("40.7143", "-74.006", "America/New_York")
    assert set(params) == {"latitude", "longitude", "timezone", "daily", "temperature_unit", "forecast_days"}


def test_a_low_chance_of_rain_is_a_dry_day(client, fake):
    fake.forecast.update(chance=10, code=2)
    save_place(client)
    w = client.get("/api/weather").json()["weather"]
    assert (w["rain"], w["rain_chance"], w["summary"]) == (False, 10, "cloudy")


def test_weather_is_reused_for_an_hour(client, fake):
    save_place(client)
    first = client.get("/api/weather").json()
    fake.clock["now"] += 3500
    assert client.get("/api/weather").json() == first and fake.forecasts() == 1
    fake.clock["now"] += 200
    fake.forecast.update(low=5, high=11)
    later = client.get("/api/weather").json()
    assert fake.forecasts() == 2 and (later["weather"]["low_c"], later["weather"]["high_c"]) == (5, 11)


def test_a_new_day_asks_again_even_within_the_hour(client, fake):
    fake.clock["now"] = datetime(2026, 11, 13, 4, 50, tzinfo=UTC).timestamp()  # 23:50 in New York
    save_place(client)
    client.get("/api/weather")
    fake.clock["now"] += 20 * 60  # 00:10 the next day
    fake.forecast["date"] = "2026-11-13"
    assert client.get("/api/weather").json()["weather"]["date"] == "2026-11-13" and fake.forecasts() == 2


def test_the_last_answer_is_given_back_marked_old_when_the_service_is_down(client, fake):
    save_place(client)
    first = client.get("/api/weather").json()["weather"]
    fake.clock["now"] += 2 * 3600
    fake.down = True
    r = client.get("/api/weather")
    assert r.status_code == 200
    body = r.json()
    assert body["old"] is True and body["weather"] == first and body["is_today"] is True
    assert "Couldn't reach the weather service" in body["message"] and "last forecast" in body["message"]


def test_no_answer_at_all_is_said_in_plain_words(client, fake):
    save_place(client)
    fake.down = True
    r = client.get("/api/weather")
    assert r.status_code == 200
    body = r.json()
    assert body["weather"] is None and body["place"] == NYC and "give today's temperatures yourself" in body["message"]


def test_changing_the_place_forgets_the_old_forecast(client, fake):
    save_place(client)
    client.get("/api/weather")
    save_place(client, {**NYC, "name": "Boston", "latitude": 42.3584, "longitude": -71.0598})
    fake.down = True
    body = client.get("/api/weather").json()
    assert body["weather"] is None and body["place"]["name"] == "Boston"


def test_an_unreadable_answer_is_said_in_plain_words(client, fake, monkeypatch):
    save_place(client)
    monkeypatch.setattr(weather, "fetch", lambda url: b'{"daily": {"time": []}}')
    body = client.get("/api/weather").json()
    assert body["weather"] is None and "could not read" in body["message"]


# ---------------------------------------------------------------------- today's outfits
def make_item(client, key, **fields):
    created = upload(client, key=key).json()
    r = client.patch(f"/api/items/{created['id']}", json=fields)
    assert r.status_code == 200, r.text
    return created["id"]


def small_closet(client):
    ids = {
        "tee1": make_item(client, "a", name="White tee one", category="tee", color="white", formality="casual",
                          silhouette={"sleeve": "short"}),
        "tee2": make_item(client, "b", name="White tee two", category="tee", color="white", formality="casual",
                          silhouette={"sleeve": "short"}),
        "jeans": make_item(client, "c", name="Blue jeans", category="jeans", color="blue", formality="casual"),
        "sneakers": make_item(client, "d", name="White sneakers", category="sneakers", color="white", formality="casual"),
        "jacket": make_item(client, "e", name="Navy jacket", category="jacket", color="navy", formality="casual"),
    }
    return ids


def pieces(outfit):
    p = outfit["pieces"]
    return [p[k] for k in ("base", "mid", "outer", "bottom", "shoes") if p[k]] + p["accessories"]


def test_today_with_no_place_and_no_temperatures_asks_for_one_or_the_other(client, fake):
    r = client.post("/api/outfits/today", json={})
    assert r.status_code == 422
    assert r.json()["detail"] == ("Choose where you are in Settings so Closet can look up the weather, "
                                  "or give today's low and high temperatures.")
    assert fake.calls == []


def test_today_uses_the_weather_for_the_saved_place(client, fake):
    ids = small_closet(client)
    save_place(client)
    r = client.post("/api/outfits/today", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["missing"] == [] and body["outfits"]
    assert body["context"] == {"date": "2026-11-12", "low_c": 3.2, "high_c": 9.8, "rain": True, "source": "forecast",
                               "old": False, "place": NYC["name"], "rain_chance": 70, "summary": "rain"}
    # a cold day: the jacket goes over the tee
    assert all(o["pieces"]["outer"] == ids["jacket"] for o in body["outfits"])


def test_today_passes_over_an_item_worn_yesterday_when_an_equal_one_exists(client, fake):
    ids = small_closet(client)
    for worn, other in (("tee1", "tee2"), ("tee2", "tee1")):
        client.post(f"/api/items/{ids[worn]}/wears", json={"worn_on": (TODAY - timedelta(days=1)).isoformat()})
        best = client.post("/api/outfits/today", json={"low_c": 27, "high_c": 27}).json()["outfits"][0]
        assert best["pieces"]["base"] == ids[other], worn
        client.delete(f"/api/items/{ids[worn]}/wears/{(TODAY - timedelta(days=1)).isoformat()}")


def test_today_never_chooses_an_item_in_the_laundry(client, fake):
    ids = small_closet(client)
    client.post(f"/api/items/{ids['tee1']}/laundry", json={"state": "laundry"})
    body = client.post("/api/outfits/today", json={"low_c": 20, "high_c": 25, "count": 5}).json()
    assert body["outfits"] and all(ids["tee1"] not in pieces(o) for o in body["outfits"])
    client.post(f"/api/items/{ids['tee2']}/laundry", json={"state": "laundry"})
    body = client.post("/api/outfits/today", json={"low_c": 20, "high_c": 25}).json()
    assert body["outfits"] == [] and "in the laundry" in body["missing"][0]


def test_today_overrides_win_over_the_weather(client, fake):
    small_closet(client)
    save_place(client)
    body = client.post("/api/outfits/today", json={"high_c": 12, "rain": False}).json()
    assert body["context"] == {"date": "2026-11-12", "low_c": 3.2, "high_c": 12, "rain": False,
                                    "source": "forecast and given", "old": False, "place": NYC["name"],
                                    "rain_chance": None, "summary": "rain"}
    calls = fake.forecasts()
    body = client.post("/api/outfits/today", json={"low_c": 25, "high_c": 30, "rain": False}).json()
    assert fake.forecasts() == calls  # nothing left to look up
    assert body["context"] == {"date": "2026-11-12", "low_c": 25, "high_c": 30, "rain": False, "source": "given",
                               "old": False, "place": None, "rain_chance": None, "summary": None}
    assert all(o["pieces"]["outer"] is None for o in body["outfits"])


def test_today_with_temperatures_given_works_when_the_service_is_down(client, fake):
    small_closet(client)
    save_place(client)
    fake.down = True
    r = client.post("/api/outfits/today", json={"low_c": 15})
    assert r.status_code == 422 and r.json()["detail"].endswith("Give today's low and high temperatures instead.")
    body = client.post("/api/outfits/today", json={"low_c": 15, "high_c": 20}).json()
    assert body["outfits"] and body["context"]["rain"] is False and body["context"]["source"] == "given"


def test_today_uses_an_old_forecast_for_today_and_says_so(client, fake):
    small_closet(client)
    save_place(client)
    client.get("/api/weather")
    fake.clock["now"] += 2 * 3600
    fake.down = True
    ctx = client.post("/api/outfits/today", json={}).json()["context"]
    assert ctx["old"] is True and ctx["source"] == "forecast" and ctx["low_c"] == 3.2


def test_today_checks_its_choices(client, fake):
    small_closet(client)
    day = {"low_c": 10, "high_c": 15}
    for body, words in (({**day, "worn_days_ago": {}}, "not part of today's choices"), ({**day, "occasion": "party"}, "not an occasion"),
                        ({**day, "build_around": "missing"}, "not in this closet"), ({"low_c": 10, "high_c": 4}, "above the high"),
                        ({**day, "count": 0}, "Count")):
        r = client.post("/api/outfits/today", json=body)
        assert r.status_code == 422 and words in r.json()["detail"], body
    assert client.post("/api/outfits/today", json=[1]).status_code == 422
    r = client.post("/api/outfits/today", content=b"{nope", headers={"content-type": "application/json"})
    assert r.status_code == 400


def test_today_demo_and_main_closets_are_separate_and_share_the_place(client, fake):
    ids = small_closet(client)
    save_place(client)
    main = client.post("/api/outfits/today", json={"build_around": ids["tee1"]}).json()
    assert main["outfits"] and all(ids["tee1"] in pieces(o) for o in main["outfits"])
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    demo_items = client.get("/api/items").json()["items"]
    demo_ids = {i["id"] for i in demo_items}
    in_laundry = {i["id"] for i in demo_items if i["laundry"] == "laundry"}
    assert in_laundry, "the demo closet has items in the laundry"
    body = client.post("/api/outfits/today", json={"count": 5}).json()
    assert body["context"]["place"] == NYC["name"] and body["context"]["source"] == "forecast"
    for o in body["outfits"]:
        assert set(pieces(o)) <= demo_ids and not set(pieces(o)) & in_laundry
    assert client.post("/api/outfits/today", json={"build_around": ids["tee1"]}).status_code == 422
