"""The day as it is dressed for: the forecast hour by hour (closet/day.py), the day in the owner's words
(closet/daynote.py, tagger/dayread.py), and what both change on Today. Claude and Open-Meteo are stood in for."""
import json
from datetime import date, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest

from closet import day, daynote, spend, wears, weather
from closet.tagger import dayread
from closet.tagger.tagging import CapReached, TaggingError, Unreachable

from .test_weather import NOON, TODAY, FakeOpenMeteo, make_item

LISBON = {"name": "Lisbon, Portugal", "latitude": 38.7167, "longitude": -9.1333, "timezone": "Europe/Lisbon"}


def hour(h, temp, feels=None, chance=0, mm=0.0, wind=5.0, gust=10.0, humidity=50.0, uv=1.0, summary="cloudy"):
    return {"hour": h, "temp_c": temp, "feels_c": temp if feels is None else feels, "rain_chance": chance,
            "rain_mm": mm, "wind_kmh": wind, "gust_kmh": gust, "humidity": humidity, "uv": uv, "summary": summary}


def a_day(**change):
    """A cool November day: 2° at night, 9° at three in the afternoon."""
    temps = [2, 2, 1, 1, 1, 2, 2, 3, 4, 5, 6, 7, 8, 8, 9, 9, 8, 7, 6, 5, 5, 4, 3, 3]
    hours = [hour(h, float(t)) for h, t in enumerate(temps)]
    for h, fields in change.items():
        hours[int(h[1:])].update(fields)
    return hours


# ------------------------------------------------------------------ the hours read
def test_the_waking_hours_are_read_not_the_night():
    read = day.read(a_day())
    assert (read["from_hour"], read["to_hour"]) == day.WAKING == (7, 22)
    assert (read["temp_low_c"], read["temp_high_c"]) == (3.0, 9.0)   # the 1° at four in the morning does not count
    assert read["rain"] is None and read["wet"] is False and read["words"] == ["3° to 9°"]


def test_hours_already_gone_are_left_out_and_come_back_when_none_are_left():
    wet_morning = a_day(h9={"rain_chance": 90, "rain_mm": 2.0})
    assert day.read(wet_morning, now_hour=8)["wet"] is True
    afternoon = day.read(wet_morning, now_hour=15)
    assert afternoon["from_hour"] == 15 and afternoon["wet"] is False and afternoon["temp_low_c"] == 4.0
    late = day.read(wet_morning, now_hour=23)   # the day is over: all of it is read again
    assert (late["from_hour"], late["to_hour"]) == (7, 22) and late["wet"] is True


def test_the_owners_hours_outside_are_the_ones_read():
    read = day.read(a_day(h20={"rain_chance": 80, "rain_mm": 1.5}), outside=(12, 18))
    assert (read["from_hour"], read["to_hour"]) == (12, 18)
    assert (read["temp_low_c"], read["temp_high_c"]) == (7.0, 9.0) and read["wet"] is False   # the rain at eight is after
    assert day.read(a_day(), outside=(18, 12))["from_hour"] == 7   # hours that make no sense: the waking day


def test_what_it_feels_like_is_said_when_it_is_far_from_the_thermometer():
    windy = a_day(**{f"h{h}": {"feels_c": t - 4.0, "wind_kmh": 38.0} for h, t in ((7, 3), (14, 9), (15, 9))})
    read = day.read(windy)
    assert (read["feels_low_c"], read["feels_high_c"]) == (-1.0, 8.0)
    assert read["words"][:2] == ["feels like -1° to 8°", "windy"]
    assert day.read(a_day(h14={"feels_c": 8.0}))["words"] == ["3° to 9°"]   # a degree apart is not worth saying
    one = [hour(13, 17.2, feels=13.4), hour(14, 16.8, feels=12.8)]
    assert day.read(one, outside=(13, 15))["words"] == ["feels like about 13°"]
    assert day.read([hour(13, 17.2), hour(14, 16.8)], outside=(13, 15))["words"] == ["about 17°"]


def test_rain_is_said_with_its_hours_and_how_hard():
    def shower(first, last, mm, **more):
        return day.read(a_day(**{f"h{h}": {"rain_chance": 70, "rain_mm": mm, **more} for h in range(first, last)}))["rain"]
    rain = shower(14, 17, 2.0)
    assert rain["words"] == "rain 2pm to 5pm" and (rain["from_hour"], rain["to_hour"], rain["mm"]) == (14, 17, 6.0)
    assert shower(12, 13, 0.4)["words"] == "light rain around noon"
    assert shower(9, 11, 6.0)["words"] == "heavy rain 9am to 11am"
    assert shower(7, 22, 1.5)["words"] == "rain most of the time"
    assert shower(16, 19, 1.0, summary="snow")["words"] == "snow 4pm to 7pm"
    assert shower(16, 18, 9.0, summary="storms")["kind"] == "storms"
    # two showers are said as two, more as on and off: never as one long spell of rain
    def showers(*at):
        return day.read(a_day(**{f"h{h}": {"rain_chance": 60, "rain_mm": 0.3} for h in at}))["rain"]["words"]
    assert showers(7, 20) == "light rain around 7am and around 8pm"
    assert showers(8, 9, 17, 18, 19) == "light rain 8am to 10am and 5pm to 8pm"
    assert showers(8, 12, 16, 20) == "light rain on and off, 8am to 9pm"
    # a chance below half is not a wet hour, whatever might fall; with no chance given, the amount decides
    assert day.read(a_day(h10={"rain_chance": 40, "rain_mm": 3.0}))["rain"] is None
    assert day.read(a_day(h10={"rain_chance": None, "rain_mm": 0.5}))["rain"]["words"] == "light rain around 10am"


def test_wind_sun_and_humidity_each_get_a_word_only_when_they_matter():
    def words(**fields):
        return day.read(a_day(h14=fields))["words"][1:]
    assert words(wind_kmh=22.0) == ["breezy"] and words(wind_kmh=40.0) == ["windy"]
    assert words(wind_kmh=55.0, gust_kmh=80.0) == ["very windy"]
    assert words(wind_kmh=10.0, gust_kmh=65.0) == ["strong gusts"]
    assert words(wind_kmh=25.0, gust_kmh=65.0) == ["breezy, strong gusts"]
    assert words(uv=6.5) == ["strong sun"] and words(uv=9.0) == ["very strong sun"]
    assert words(temp_c=29.0, feels_c=33.0, humidity=80.0) == ["humid"]
    assert words(temp_c=29.0, feels_c=29.0, humidity=40.0) == []   # warm and dry
    assert words(wind_kmh=None, gust_kmh=None, uv=None, humidity=None) == []


def test_hours_as_words():
    assert [day.hour_words(h) for h in (0, 7, 12, 15, 23, 24)] == ["midnight", "7am", "noon", "3pm", "11pm", "midnight"]
    assert day.span_words(12, 18) == "noon to 6pm" and day.span_words(14, 15) == "around 2pm"


def test_a_forecast_with_no_hours_in_the_window_gives_nothing():
    assert day.read([]) is None and day.read([hour(3, 1.0)]) is None


# ------------------------------------------------------------------ the forecast's hours
class HourlyOpenMeteo(FakeOpenMeteo):
    """Open-Meteo with the day hour by hour, and Lisbon on its map."""

    def __init__(self):
        super().__init__()
        self.hours = {"home": a_day(), "lisbon": [hour(h, 16.0 + (h % 12) / 2, uv=7.0 if h == 13 else 2.0) for h in range(24)]}
        self.spoil = None

    def __call__(self, url: str) -> bytes:
        parts = urlsplit(url)
        params = {k: v[0] for k, v in parse_qs(parts.query).items()}
        if parts.netloc == "geocoding-api.open-meteo.com" and params["name"].startswith("Lisbon"):
            self.calls.append((parts.netloc + parts.path, params))
            if self.down:
                raise OSError("no network")
            return json.dumps({"results": [{"name": "Lisbon", "latitude": 38.71667, "longitude": -9.13333,
                                            "timezone": "Europe/Lisbon", "country": "Portugal", "admin1": "Lisbon"}]}).encode()
        if parts.netloc == "geocoding-api.open-meteo.com" and params["name"].startswith("Atlantis"):
            return b'{"generationtime_ms": 0.1}'
        raw = super().__call__(url)
        if parts.netloc != "api.open-meteo.com":
            return raw
        data = json.loads(raw)
        where = "lisbon" if params["latitude"].startswith("38.7") else "home"
        assert "apparent_temperature" in params["hourly"] and params["wind_speed_unit"] == "kmh"
        hours, today = self.hours[where], self.forecast["date"]
        names = {"temperature_2m": "temp_c", "apparent_temperature": "feels_c", "precipitation_probability": "rain_chance",
                 "precipitation": "rain_mm", "wind_speed_10m": "wind_kmh", "wind_gusts_10m": "gust_kmh",
                 "relative_humidity_2m": "humidity", "uv_index": "uv"}
        data["hourly"] = {"time": [f"{today}T{h['hour']:02d}:00" for h in hours],
                          **{theirs: [h[ours] for h in hours] for theirs, ours in names.items()},
                          "weather_code": [61 if h["summary"] == "rain" else 3 for h in hours]}
        if where == "lisbon":
            data["utc_offset_seconds"] = 0
        if self.spoil:
            self.spoil(data)
        return json.dumps(data).encode()


@pytest.fixture
def om(monkeypatch):
    hourly = HourlyOpenMeteo()
    hourly.clock = {"now": NOON}   # noon in New York, five in the afternoon in Lisbon
    monkeypatch.setattr(wears, "today", lambda: TODAY)
    monkeypatch.setattr(weather, "_now", lambda: hourly.clock["now"])
    monkeypatch.setattr(weather, "fetch", hourly)
    return hourly


def test_the_forecast_carries_the_day_hour_by_hour(client, om):
    hours = client.get("/api/weather").json()["weather"]["hours"]
    assert len(hours) == 24 and hours[14] == {**hour(14, 9.0), "summary": "cloudy"}


@pytest.mark.parametrize("spoil", [
    lambda d: d.pop("hourly"),
    lambda d: d.update(hourly="soon"),
    lambda d: d["hourly"].update(time=None),
    lambda d: d["hourly"].update(temperature_2m=["cold"] * 24),
    lambda d: d["hourly"].update(time=["yesterday"] * 24),
])
def test_hours_that_cannot_be_read_never_fail_the_forecast(client, om, spoil):
    om.spoil = spoil
    body = client.get("/api/weather").json()
    assert body["weather"]["hours"] == [] and (body["weather"]["low_c"], body["weather"]["high_c"]) == (3.2, 9.8)


def test_an_hour_with_a_number_out_of_range_keeps_the_rest(client, om):
    om.spoil = lambda d: (d["hourly"]["wind_speed_10m"].__setitem__(14, 9999), d["hourly"]["temperature_2m"].__setitem__(3, None))
    hours = client.get("/api/weather").json()["weather"]["hours"]
    assert len(hours) == 23 and next(h for h in hours if h["hour"] == 14)["wind_kmh"] is None


# ------------------------------------------------------------------ Today dresses for the hours
def closet(client):
    return {
        "tee": make_item(client, "a", name="White tee", category="tee", color="white", formality="casual"),
        "chinos": make_item(client, "b", name="Navy chinos", category="trousers", color="navy", formality="smart_casual"),
        "sneakers": make_item(client, "c", name="White sneakers", category="sneakers", color="white", formality="casual"),
        "sweater": make_item(client, "d", name="Grey sweater", category="sweater", color="grey", formality="smart_casual"),
        "jacket": make_item(client, "e", name="Navy jacket", category="jacket", color="navy", formality="casual"),
    }


def today(client, **body):
    r = client.post("/api/outfits/today", json=body)
    assert r.status_code == 200, r.text
    return r.json()["context"]


def test_today_dresses_for_what_the_hours_ahead_feel_like(client, om):
    closet(client)
    om.hours["home"] = a_day(**{f"h{h}": {"feels_c": 0.0, "wind_kmh": 40.0} for h in (12, 13)},
                             h16={"rain_chance": 80, "rain_mm": 2.0}, h17={"rain_chance": 80, "rain_mm": 2.0})
    ctx = today(client)   # it is noon in New York
    assert (ctx["low_c"], ctx["high_c"], ctx["rain"]) == (0.0, 9.0, True)   # not the whole day's 3.2 to 9.8
    assert ctx["detail"]["from_hour"] == 12 and ctx["detail"]["words"] == ["feels like 0° to 9°", "rain 4pm to 6pm", "windy"]
    assert ctx["source"] == "forecast" and ctx["note"] is None


def test_temperatures_typed_by_hand_stand_and_the_hours_are_not_shown_for_them(client, om):
    closet(client)
    ctx = today(client, low_c=20, high_c=25, rain=False)
    assert (ctx["low_c"], ctx["high_c"], ctx["detail"], ctx["source"]) == (20, 25, None, "given")
    assert om.forecasts() == 0
    ctx = today(client, rain=True)   # only the rain said by hand: the hours still give the temperatures
    assert ctx["rain"] is True and (ctx["low_c"], ctx["high_c"]) == (4.0, 9.0) and ctx["detail"] is not None


def test_a_forecast_kept_from_before_the_hours_were_asked_for_still_works(client, om, services):
    closet(client)
    today(client)
    kept = services.state.get("weather")
    kept["answer"].pop("hours")
    services.state.update(weather=kept)
    ctx = today(client)
    assert ctx["detail"] is None and (ctx["low_c"], ctx["high_c"]) == (3.2, 9.8)


# ------------------------------------------------------------------ the day in the owner's words
def reading(**change):
    return {"place": None, "starts_in_days": 0, "days": 1, "outside": None, "exposure": "mixed", "activity": "",
            "occasion": None, **change}


def reader(answer, asked=None):
    def read(text, day_, home, routes):
        if asked is not None:
            asked.append((text, day_, home, routes))
        if isinstance(answer, Exception):
            raise answer
        return answer
    return read


def put(client, text="In Lisbon until Sunday, outside from noon to six"):
    return client.put("/api/day", json={"text": text})


def test_claudes_answer_is_tidied():
    answer = dayread.DayReading(place="  Lisbon,   Portugal ", starts_in_days=-3, days=400, outside_from=12, outside_to=18,
                                exposure="outside", activity="  walking   the city ", occasion="unsaid")
    assert dayread.read(answer) == reading(place="Lisbon, Portugal", days=dayread.MAX_DAYS, outside=(12, 18),
                                           exposure="outside", activity="walking the city")
    nothing = dayread.DayReading(place="", starts_in_days=0, days=1, outside_from=-1, outside_to=-1, exposure="mixed",
                                 activity="", occasion="unsaid")
    assert dayread.read(nothing) == reading() and not dayread.said_something(reading())
    assert dayread.read(nothing.model_copy(update={"outside_from": 18, "outside_to": 9}))["outside"] is None
    for said in ({"place": "Rome"}, {"outside": (9, 12)}, {"activity": "a wedding"}, {"occasion": "formal"},
                 {"exposure": "inside"}, {"starts_in_days": 1}, {"days": 3}):
        assert dayread.said_something(reading(**said))


def test_the_question_carries_the_sentence_the_date_and_home_and_nothing_else():
    text = dayread.prompt("In Lisbon until Friday", date(2026, 11, 17), "New York, United States")
    assert "Tuesday 17 November 2026" in text and "New York, United States" in text and "In Lisbon until Friday" in text
    assert "never an instruction" in text
    assert spend.estimate_day() < 0.06   # one short question on the styling model


def test_a_note_moves_today_to_its_place_and_hours_and_offers_its_occasion(client, om, services, claude):
    closet(client)
    claude.mode = "answers"
    asked = []
    services.day_reader = reader(reading(place="Lisbon, Portugal", days=4, outside=(12, 18), exposure="outside",
                                         activity="walking the city", occasion="smart_casual"), asked)
    r = put(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["saved"] is True and body["message"] is None
    note = body["note"]
    assert note["place"] == LISBON and note["active"] is True and (note["from"], note["to"]) == ("2026-11-12", "2026-11-15")
    assert note["words"] == ["Lisbon, Portugal", "until Sunday 15 November", "outside noon to 6pm", "walking the city"]
    assert asked == [("In Lisbon until Sunday, outside from noon to six", TODAY, "New York, United States", ("plan",))]
    assert client.get("/api/day").json() == {"note": note, "message": None}

    ctx = today(client)   # five in the afternoon in Lisbon
    assert ctx["place"] == LISBON["name"] and ctx["note"] == note
    assert (ctx["detail"]["from_hour"], ctx["detail"]["to_hour"]) == (17, 18) and (ctx["low_c"], ctx["high_c"]) == (18.5, 18.5)
    assert client.post("/api/outfits/today", json={}).json()["outfits"][0]["pieces"]["outer"] is None   # no jacket at 18°
    # home's place and forecast are untouched
    assert client.get("/api/weather").json()["place"]["name"] == "New York, United States"
    assert services.state.get("place")["name"] == "New York, United States"

    assert client.delete("/api/day").json() == {"note": None, "message": None}
    ctx = today(client)
    assert ctx["place"] == "New York, United States" and ctx["note"] is None and ctx["high_c"] == 9.0


def test_the_notes_occasion_is_used_unless_the_owner_chose_one(client, om, services, claude):
    ids = closet(client)
    claude.mode = "answers"
    services.day_reader = reader(reading(activity="client meetings", occasion="smart_casual"))
    assert put(client, "Client meetings today").json()["saved"] is True
    outfits = client.post("/api/outfits/today", json={}).json()["outfits"]
    assert outfits and all(o["pieces"]["bottom"] == ids["chinos"] for o in outfits)
    assert client.post("/api/outfits/today", json={"occasion": "casual"}).status_code == 200


def test_a_note_for_days_ahead_waits_and_one_that_is_over_is_gone(client, om, services, claude, monkeypatch):
    closet(client)
    claude.mode = "answers"
    services.day_reader = reader(reading(place="Lisbon", starts_in_days=2, days=2))
    note = put(client, "In Lisbon this weekend").json()["note"]
    assert note["active"] is False and note["words"] == ["Lisbon, Portugal", "from Saturday 14 November to Sunday 15 November"]
    assert today(client)["place"] == "New York, United States"   # not yet
    monkeypatch.setattr(wears, "today", lambda: TODAY + timedelta(days=2))
    om.forecast["date"] = (TODAY + timedelta(days=2)).isoformat()
    om.clock["now"] = NOON + 2 * 86400
    assert today(client)["place"] == LISBON["name"]
    assert client.get("/api/day").json()["note"]["words"][1] == "until Sunday 15 November"
    monkeypatch.setattr(wears, "today", lambda: TODAY + timedelta(days=4))
    assert client.get("/api/day").json()["note"] is None


def test_a_place_that_cannot_be_found_keeps_the_rest_of_the_note(client, om, services, claude):
    closet(client)
    claude.mode = "answers"
    services.day_reader = reader(reading(place="Atlantis", outside=(9, 12)))
    body = put(client, "In Atlantis, out all morning").json()
    assert body["saved"] is True and "couldn't find “Atlantis”" in body["message"]
    assert body["note"]["place"] is None and body["note"]["place_asked"] == "Atlantis"
    assert body["note"]["words"] == ["today", "outside 9am to noon"]
    assert today(client)["place"] == "New York, United States"
    om.down = True   # the map cannot be reached at all
    services.day_reader = reader(reading(place="Lisbon"))
    body = put(client, "In Lisbon").json()
    assert body["saved"] is True and "Couldn't reach" in body["message"] and body["note"]["place"] is None


def test_a_place_with_its_country_is_found_by_its_town_when_the_whole_name_is_not():
    york = {"name": "York, England, United Kingdom", "latitude": 53.96, "longitude": -1.08, "timezone": "Europe/London"}
    york_us = {"name": "York, Pennsylvania, United States", "latitude": 39.96, "longitude": -76.73, "timezone": "America/New_York"}
    asked = []

    def find(name):
        asked.append(name)
        if name == "York, United States":
            return []
        if name == "York, Canada":
            raise weather.WeatherError("Couldn't reach the weather service.")
        return [york, york_us] if name == "York" else []
    note, message = daynote.make("In York", reading(place="York, United States"), TODAY, find)
    assert note["place"] == york_us and message is None and asked == ["York, United States", "York"]
    note, message = daynote.make("In York", reading(place="York, Canada"), TODAY, find)   # no York there: the first York
    assert note["place"] == york and message is None
    note, message = daynote.make("In York", reading(place="York"), TODAY, find)
    assert note["place"] == york
    note, message = daynote.make("On the moon", reading(place="Tranquility Base"), TODAY, find)
    assert note["place"] is None and "couldn't find “Tranquility Base”" in message


def test_when_claude_cannot_read_it_the_note_before_stays(client, om, services, claude):
    claude.mode = "answers"
    services.day_reader = reader(reading(activity="hiking", exposure="outside"))
    before = put(client, "Hiking all day").json()["note"]
    assert before["words"] == ["today", "outside most of the day", "hiking"]
    for error, said in ((CapReached("limit"), "spending limit"), (Unreachable("offline"), "can't be reached"),
                        (TaggingError("bad"), "no usable answer"), (reading(), "couldn't find anything about your day")):
        services.day_reader = reader(error)
        body = put(client, "Something else").json()
        assert body["saved"] is False and said in body["message"] and body["note"] == before, body
    claude.mode = "unavailable"   # no route to Claude: it is not even asked
    services.day_reader = lambda *a: pytest.fail("asked with no route")
    body = put(client).json()
    assert body["saved"] is False and "can't be reached" in body["message"]


def test_the_api_key_is_asked_first_for_the_day(client, om, services, claude, monkeypatch):
    claude.mode = "answers"
    monkeypatch.setattr(claude, "routes", lambda: ("plan", "api"))
    asked = []
    services.day_reader = reader(reading(activity="a wedding", occasion="formal"), asked)
    assert put(client, "A wedding today").json()["saved"] is True
    assert asked[0][3] == ("api", "plan")


def test_the_sentence_is_checked_and_the_demo_never_asks_claude(client, services, claude):
    claude.mode = "answers"
    services.day_reader = lambda *a: pytest.fail("asked")
    assert client.put("/api/day", json={"text": "   "}).status_code == 422
    assert client.put("/api/day", json={"text": "x" * (daynote.MAX_TEXT + 1)}).status_code == 422
    assert client.put("/api/day", json=["In Lisbon"]).status_code == 422
    assert client.put("/api/day", content=b"{", headers={"content-type": "application/json"}).status_code == 400
    client.post("/api/profile", json={"profile": "demo"})
    body = put(client).json()
    assert body["saved"] is False and "demo" in body["message"]


def test_the_day_needs_login(anon):
    assert anon.get("/api/day").status_code == 401
    assert anon.put("/api/day", json={"text": "In Lisbon"}).status_code == 401
    assert anon.delete("/api/day").status_code == 401


def test_a_note_that_cannot_be_read_counts_as_none(services):
    for broken in ("soon", {"from": "2026-11-12"}, {"from": "later", "to": "2026-11-12"},
                   {"from": "2026-11-14", "to": "2026-11-12"}):
        services.state.update(day_note=broken)
        assert daynote.current(services.state, TODAY) is None
    assert daynote.outside({"outside": [18, 9]}) is None and daynote.outside({"outside": ["9", 12]}) is None
