import json
import urllib.error
from datetime import UTC, date, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest

from closet import tripweather, wears, weather
from closet.state import State

TODAY = date(2026, 11, 12)
NOON = datetime(2026, 11, 12, 17, 0, tzinfo=UTC).timestamp()
LISBON = {"name": "Lisbon, Portugal", "latitude": 38.7167, "longitude": -9.1333, "timezone": "Europe/Lisbon"}


def iso(d: date) -> str:
    return d.isoformat()


class FakeOpenMeteo:
    """Stands in for Open-Meteo's forecast and archive. The forecast covers 16 days from TODAY: low 10+i, high 16+i,
    rain every third day. The archive has every day from five years back: low 5, high 12 (plus the year's offset),
    and rain in the years listed in `rainy_years` (counted back from the trip's year)."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.forecast_down = False
        self.archive_down = False
        self.rainy_years = {1, 2, 3}
        self.start = TODAY  # the forecast's first day

    def __call__(self, url: str) -> bytes:
        parts = urlsplit(url)
        params = {k: v[0] for k, v in parse_qs(parts.query).items()}
        where = parts.netloc + parts.path
        self.calls.append((where, params))
        if where == "api.open-meteo.com/v1/forecast":
            if self.forecast_down:
                raise urllib.error.URLError("no network")
            days = [self.start + timedelta(days=i) for i in range(int(params["forecast_days"]))]
            return json.dumps({"daily": {
                "time": [iso(d) for d in days], "temperature_2m_min": [10 + i for i in range(len(days))],
                "temperature_2m_max": [16 + i for i in range(len(days))],
                "precipitation_probability_max": [80 if i % 3 == 0 else 10 for i in range(len(days))],
                "weather_code": [61 if i % 3 == 0 else 1 for i in range(len(days))]}}).encode()
        assert where == "archive-api.open-meteo.com/v1/archive"
        if self.archive_down:
            raise urllib.error.URLError("no network")
        start, end = date.fromisoformat(params["start_date"]), date.fromisoformat(params["end_date"])
        days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        trip_year = end.year + 1
        return json.dumps({"daily": {
            "time": [iso(d) for d in days],
            "temperature_2m_min": [5 + (trip_year - d.year) for d in days],
            "temperature_2m_max": [12 + (trip_year - d.year) for d in days],
            "precipitation_sum": [4.0 if (trip_year - d.year) in self.rainy_years else 0.0 for d in days]}}).encode()

    def count(self, where: str) -> int:
        return sum(1 for w, _ in self.calls if w == where)


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(wears, "today", lambda: TODAY)
    monkeypatch.setattr(weather, "_now", lambda: NOON)
    om = FakeOpenMeteo()
    monkeypatch.setattr(weather, "fetch", om)
    return om


@pytest.fixture
def state(tmp_path):
    return State(tmp_path / "state.json")


def test_days_in_the_forecast_use_the_forecast(fake, state):
    found = tripweather.lookup(state, LISBON, TODAY + timedelta(days=3), TODAY + timedelta(days=5), TODAY)
    assert [d["source"] for d in found["days"]] == ["forecast"] * 3
    assert found["days"][0] == {"date": iso(TODAY + timedelta(days=3)), "low_c": 13.0, "high_c": 19.0, "rain": True,
                                "rain_chance": 80, "summary": "rain", "source": "forecast"}
    assert found["days"][1]["rain"] is False and found["message"] is None
    assert fake.count("archive-api.open-meteo.com/v1/archive") == 0


def test_days_beyond_the_forecast_are_what_the_dates_are_usually_like(fake, state):
    first = date(2027, 3, 1)
    found = tripweather.lookup(state, LISBON, first, first + timedelta(days=1), TODAY)
    assert fake.count("api.open-meteo.com/v1/forecast") == 0
    (_, params), = fake.calls
    assert params["start_date"] == "2022-03-01" and params["end_date"] == "2026-03-02"
    day = found["days"][0]
    # lows 6..10 over the five years average 8, highs 13..17 average 15; rain in 3 of 5 years: rainy
    assert day == {"date": "2027-03-01", "low_c": 8.0, "high_c": 15.0, "rain": True, "rain_chance": 60, "summary": None,
                   "source": "usual"}
    fake.rainy_years = {1, 2}
    state.update(trip_weather=None)
    assert tripweather.lookup(state, LISBON, first, first, TODAY)["days"][0]["rain"] is False


def test_usual_weather_uses_only_past_dates_for_a_trip_ending_over_a_year_ahead(fake, state):
    first = TODAY + timedelta(days=366)
    last = first + timedelta(days=29)
    assert tripweather.check_dates(iso(first), iso(last), TODAY) == (first, last)

    found = tripweather.lookup(state, LISBON, first, last, TODAY)

    assert all(d["source"] == "usual" for d in found["days"])
    (_, params), = [c for c in fake.calls if c[0].startswith("archive")]
    assert date.fromisoformat(params["start_date"]) <= date.fromisoformat(params["end_date"]) <= TODAY


def test_usual_weather_handles_leap_day_and_dates_across_new_year(fake, state):
    leap = date(2028, 2, 29)
    leap_day = tripweather.lookup(state, LISBON, leap, leap, TODAY)["days"][0]
    new_year = tripweather.lookup(state, LISBON, date(2027, 12, 31), date(2028, 1, 2), TODAY)["days"]

    assert leap_day["date"] == "2028-02-29" and leap_day["low_c"] is not None
    assert [d["date"] for d in new_year] == ["2027-12-31", "2028-01-01", "2028-01-02"]
    assert all(d["source"] == "usual" and d["low_c"] is not None for d in new_year)
    archive = [params for where, params in fake.calls if where.startswith("archive")]
    assert all(date.fromisoformat(p["end_date"]) <= TODAY for p in archive)


def test_usual_weather_cache_key_contains_the_exact_days_asked_for(fake, state, monkeypatch):
    first = TODAY + timedelta(days=14)
    days = [iso(first + timedelta(days=i)) for i in range(5)]
    source = lambda day: {"date": day, "low_c": 10, "high_c": 16, "rain": False, "rain_chance": 10,
                          "summary": "clear", "source": "forecast"}
    forecasts = iter([{days[0]: source(days[0]), days[4]: source(days[4])},
                      {days[0]: source(days[0]), days[2]: source(days[2]), days[4]: source(days[4])}])
    monkeypatch.setattr(tripweather, "_forecast", lambda place: next(forecasts))
    now = [NOON]
    monkeypatch.setattr(weather, "_now", lambda: now[0])

    tripweather.lookup(state, LISBON, first, first + timedelta(days=4), TODAY)
    now[0] += tripweather.KEEP_FORECAST_S + 1
    tripweather.lookup(state, LISBON, first, first + timedelta(days=4), TODAY)

    assert fake.count("archive-api.open-meteo.com/v1/archive") == 2


def test_only_the_coordinates_time_zone_and_dates_are_sent(fake, state):
    tripweather.lookup(state, LISBON, TODAY + timedelta(days=14), TODAY + timedelta(days=18), TODAY)
    for _, params in fake.calls:
        assert "Portugal" not in json.dumps(params)
        assert {"latitude", "longitude", "timezone"} <= set(params)
        assert set(params) - {"latitude", "longitude", "timezone", "daily", "temperature_unit", "forecast_days",
                              "start_date", "end_date"} == set()


def test_a_trip_that_spans_the_forecast_and_beyond(fake, state):
    found = tripweather.lookup(state, LISBON, TODAY + timedelta(days=13), TODAY + timedelta(days=19), TODAY)
    assert [d["source"] for d in found["days"]] == ["forecast"] * 3 + ["usual"] * 4
    (_, params), = [c for c in fake.calls if c[0].startswith("archive")]
    assert params["end_date"] == iso(TODAY + timedelta(days=19) - timedelta(days=365))


def test_the_archive_failing_leaves_the_forecast_days_and_says_the_others_are_unknown(fake, state):
    fake.archive_down = True
    found = tripweather.lookup(state, LISBON, TODAY + timedelta(days=14), TODAY + timedelta(days=17), TODAY)
    assert [d["source"] for d in found["days"]] == ["forecast", "forecast", "unknown", "unknown"]
    assert found["days"][2]["low_c"] is None
    assert "Couldn't reach the weather service" in found["message"] and "left out of the plan" in found["message"]


def test_the_forecast_failing_falls_back_to_the_usual_weather(fake, state):
    fake.forecast_down = True
    found = tripweather.lookup(state, LISBON, TODAY + timedelta(days=1), TODAY + timedelta(days=2), TODAY)
    assert [d["source"] for d in found["days"]] == ["usual", "usual"] and found["message"] is None


def test_answers_are_kept_and_reused(fake, state):
    for _ in range(3):
        tripweather.lookup(state, LISBON, TODAY + timedelta(days=13), TODAY + timedelta(days=19), TODAY)
    assert fake.count("api.open-meteo.com/v1/forecast") == 1
    assert fake.count("archive-api.open-meteo.com/v1/archive") == 1
    # the next day the forecast is asked for again; the archive answer is still good
    tripweather.lookup(state, LISBON, TODAY + timedelta(days=13), TODAY + timedelta(days=19), TODAY + timedelta(days=1))
    assert fake.count("api.open-meteo.com/v1/forecast") == 2


@pytest.mark.parametrize("first, last, words", [
    ("2026-12-01", "2026-12-31", "at most 30 days"),
    ("2026-12-05", "2026-12-01", "before its first day"),
    ("2026-11-11", "2026-11-13", "today or later"),
    ("2028-01-01", "2028-01-02", "a year ahead"),
    ("1 December", "2026-12-02", "YYYY-MM-DD"),
    (None, "2026-12-02", "first day"),
])
def test_dates_are_checked_in_plain_words(first, last, words):
    with pytest.raises(ValueError, match=words):
        tripweather.check_dates(first, last, TODAY)


def test_thirty_days_and_today_are_allowed():
    assert tripweather.check_dates("2026-11-12", "2026-12-11", TODAY) == (TODAY, date(2026, 12, 11))


def test_a_changed_forecast_is_noticed():
    before = [{"date": "2026-12-01", "low_c": 5, "high_c": 10, "rain": False, "source": "usual"}]
    same = [{**before[0], "low_c": 6}]
    assert not tripweather.changed(before, same)
    assert tripweather.changed(before, [{**before[0], "source": "forecast"}])
    assert tripweather.changed(before, [{**before[0], "rain": True}])
    assert tripweather.changed(before, [{**before[0], "high_c": 14}])
    assert not tripweather.changed(before, [tripweather.unknown("2026-12-01")])
    assert tripweather.in_forecast(before, date(2026, 11, 20)) and not tripweather.in_forecast(before, TODAY)


def test_given_weather_is_checked():
    first, last = date(2026, 12, 1), date(2026, 12, 2)
    days = [{"date": "2026-12-01", "low_c": 1, "high_c": 5, "rain": True}, {"date": "2026-12-02", "low_c": 2, "high_c": 6}]
    assert [d["source"] for d in tripweather.given(first, last, days)] == ["given", "given"]
    with pytest.raises(ValueError, match="every day"):
        tripweather.given(first, last, days[:1])
    with pytest.raises(ValueError, match="above the high"):
        tripweather.given(first, last, [days[0], {**days[1], "low_c": 9}])
