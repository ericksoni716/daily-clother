import json
from datetime import UTC, date, datetime, timedelta
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfoNotFoundError

import pytest

from closet import trip_weather as tw
from closet import weather
from closet.state import State

PLACE = {"name": "Example", "latitude": 40, "longitude": -74, "timezone": "UTC"}
TODAY = date(2026, 11, 13)


@pytest.fixture
def meteo(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(weather, "_now", lambda: datetime(2026, 11, 13, tzinfo=UTC).timestamp())

    def fetch(url):
        p = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        calls.append((urlsplit(url).netloc, p))
        assert not ({"name", "occasion", "items"} & p.keys())
        start, end = date.fromisoformat(p["start_date"]), date.fromisoformat(p["end_date"])
        ds = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        archive = "archive-api" in url
        return json.dumps({"daily": {
            "time": [d.isoformat() for d in ds],
            "temperature_2m_min": [d.year - 2020 if archive else 12 for d in ds],
            "temperature_2m_max": [20] * len(ds),
            "precipitation_sum": [1 if d.year >= 2023 else 0 for d in ds],
            "precipitation_probability_max": [60] * len(ds),
        }}).encode()

    monkeypatch.setattr(weather, "fetch", fetch)
    return State(tmp_path / "settings.json"), calls


def test_forecast_and_cache(meteo):
    state, calls = meteo
    first, last = TODAY.isoformat(), (TODAY + timedelta(days=15)).isoformat()
    days = tw.lookup(state, PLACE, first, last)
    assert len(days) == 16 and all(d["source"] == "forecast" and d["rain"] for d in days)
    assert tw.lookup(state, PLACE, first, last) == days
    assert len(calls) == 1


def test_usual_five_year_average_and_rain_majority(meteo):
    state, calls = meteo
    days = tw.lookup(state, PLACE, "2027-06-01", "2027-06-05")
    assert len(calls) == 5
    assert {p["start_date"][:4] for _, p in calls} == {"2021", "2022", "2023", "2024", "2025"}
    assert all(d["source"] == "usual" and d["low_c"] == 3 and d["rain"] is True for d in days)


def test_both_and_archive_failure(meteo, monkeypatch):
    state, _ = meteo
    original = weather.fetch

    def failing(url):
        if "archive-api" in url:
            raise TimeoutError
        return original(url)

    monkeypatch.setattr(weather, "fetch", failing)
    days = tw.lookup(state, PLACE, "2026-11-27", "2026-11-30")
    assert [d["source"] for d in days] == ["forecast", "forecast", "usual", "usual"]
    assert days[0]["low_c"] == 12
    assert days[2]["low_c"] is None and "Couldn't reach" in days[2]["message"]


def test_spanning_success_and_new_forecast(meteo, monkeypatch):
    state, calls = meteo
    days = tw.lookup(state, PLACE, "2026-11-28", "2026-11-29")
    assert [d["source"] for d in days] == ["forecast", "usual"]
    monkeypatch.setattr(weather, "_now", lambda: datetime(2026, 11, 14, tzinfo=UTC).timestamp())
    assert all(d["source"] == "forecast" for d in tw.lookup(state, PLACE, "2026-11-28", "2026-11-29"))
    assert len(calls) == 7


@pytest.mark.parametrize("first,last", [("no", "2026-11-15"), ("2026-11-15", "2026-11-13"),
                                     ("2026-11-01", "2026-12-01"), (None, None)])
def test_date_limits(first, last):
    with pytest.raises(ValueError, match="day|date"):
        tw.dates(first, last)


def test_leap_day_and_year_boundary(meteo):
    assert tw._historical(date(2028, 2, 29), 2025) == date(2025, 2, 28)
    assert len(tw.dates("2026-12-30", "2027-01-02")) == 4
    state, _ = meteo
    result = tw.lookup(state, PLACE, "2026-12-30", "2027-01-02")
    assert len(result) == 4 and all(d["low_c"] == 3 for d in result)


def test_malformed_and_nonfinite_weather(meteo, monkeypatch):
    state, _ = meteo
    monkeypatch.setattr(weather, "fetch", lambda _: b'{"daily":{"time":["2026-11-13"],"temperature_2m_min":[NaN],"temperature_2m_max":[20]}}')
    assert tw.lookup(state, PLACE, "2026-11-13", "2026-11-13")[0]["low_c"] is None


def test_forecast_failure_keeps_usual_days(meteo, monkeypatch):
    state, _ = meteo
    original = weather.fetch

    def failing(url):
        if "archive-api" not in url:
            raise TimeoutError
        return original(url)

    monkeypatch.setattr(weather, "fetch", failing)
    days = tw.lookup(state, PLACE, "2026-11-28", "2026-11-29")
    assert days[0]["low_c"] is None
    assert days[1]["low_c"] == 3 and days[1]["source"] == "usual"


def test_cache_survives_restart_expires_and_is_bounded(meteo, monkeypatch):
    state, calls = meteo
    tw.lookup(state, PLACE, "2026-11-14", "2026-11-15")
    again = State(state.path)
    tw.lookup(again, PLACE, "2026-11-14", "2026-11-15")
    assert len(calls) == 1
    before = weather._now()
    monkeypatch.setattr(weather, "_now", lambda: before + weather.KEEP_S + 1)
    tw.lookup(again, PLACE, "2026-11-14", "2026-11-15")
    assert len(calls) == 2
    monkeypatch.setattr(tw, "MAX_CACHE_ENTRIES", 2)
    tw.lookup(again, PLACE, "2026-11-15", "2026-11-16")
    tw.lookup(again, PLACE, "2026-11-16", "2026-11-17")
    assert len(again.get("trip_weather")) == 2


def test_forecast_rain_code():
    data = {"daily": {"time": ["2026-11-13"], "temperature_2m_min": [10],
                      "temperature_2m_max": [20], "weather_code": [61]}}
    assert tw._daily(data, False)["2026-11-13"]["rain"]
    data["daily"]["precipitation_probability_max"] = [49]
    assert not tw._daily(data, False)["2026-11-13"]["rain"]


def test_incomplete_five_year_sample_is_unknown(meteo, monkeypatch):
    state, _ = meteo
    original = weather.fetch

    def incomplete(url):
        data = json.loads(original(url))
        if "start_date=2022" in url:
            data["daily"]["precipitation_sum"] = [None]
        return json.dumps(data).encode()

    monkeypatch.setattr(weather, "fetch", incomplete)
    result = tw.lookup(state, PLACE, "2027-06-01", "2027-06-01")
    assert result[0]["low_c"] is None


def test_destination_date_and_no_system_timezone_database(meteo, monkeypatch):
    monkeypatch.setattr(weather, "_now", lambda: datetime(2026, 11, 13, 1, tzinfo=UTC).timestamp())
    assert tw.today({**PLACE, "timezone": "America/New_York"}) == date(2026, 11, 12)

    def no_database(_):
        raise ZoneInfoNotFoundError

    monkeypatch.setattr(tw, "ZoneInfo", no_database)
    assert tw.today(PLACE) == TODAY
