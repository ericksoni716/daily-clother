"""The one lookup of Open-Meteo's archive (`weather.archive_daily`), shared by the home climate and the trips."""
import json
import urllib.error
from datetime import UTC, date, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest

from closet import climate, tripweather, wears, weather
from closet.state import State

TODAY = date(2026, 11, 12)
NOON = datetime(2026, 11, 12, 17, 0, tzinfo=UTC).timestamp()
LISBON = {"name": "Lisbon, Portugal", "latitude": 38.7167, "longitude": -9.1333, "timezone": "Europe/Lisbon"}


class Archive:
    """Stands in for the archive: every day asked for, low 5, high 12, 2 mm, unless `answer` is set."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.answer: dict | None = None
        self.down = False

    def __call__(self, url: str) -> bytes:
        parts = urlsplit(url)
        params = {k: v[0] for k, v in parse_qs(parts.query).items()}
        self.calls.append((parts.netloc + parts.path, params))
        if self.down:
            raise urllib.error.URLError("no network")
        if self.answer is not None:
            return json.dumps(self.answer).encode()
        start, end = date.fromisoformat(params["start_date"]), date.fromisoformat(params["end_date"])
        days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        return json.dumps({"daily": {"time": [d.isoformat() for d in days], "temperature_2m_min": [5] * len(days),
                                     "temperature_2m_max": [12] * len(days),
                                     "precipitation_sum": [2.0] * len(days)}}).encode()


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(wears, "today", lambda: TODAY)
    monkeypatch.setattr(weather, "_now", lambda: NOON)
    archive = Archive()
    monkeypatch.setattr(weather, "fetch", archive)
    return archive


def test_the_lookup_sends_only_the_place_dates_and_fields_and_gives_the_columns(fake):
    daily = weather.archive_daily(LISBON, date(2024, 2, 28), date(2024, 3, 1), timezone="Europe/Lisbon")
    assert daily == {"time": ["2024-02-28", "2024-02-29", "2024-03-01"], "temperature_2m_min": [5, 5, 5],
                     "temperature_2m_max": [12, 12, 12], "precipitation_sum": [2.0, 2.0, 2.0]}
    (where, params), = fake.calls
    assert where == "archive-api.open-meteo.com/v1/archive"
    assert params == {"latitude": "38.7167", "longitude": "-9.1333", "timezone": "Europe/Lisbon",
                      "start_date": "2024-02-28", "end_date": "2024-03-01",
                      "daily": "temperature_2m_min,temperature_2m_max,precipitation_sum", "temperature_unit": "celsius"}
    weather.archive_daily(LISBON, date(2024, 1, 1), date(2024, 1, 1), timezone="auto", precipitation_unit="mm")
    assert fake.calls[-1][1]["timezone"] == "auto" and fake.calls[-1][1]["precipitation_unit"] == "mm"


def test_a_column_that_is_not_a_list_is_none_and_no_list_of_days_is_unreadable(fake):
    fake.answer = {"daily": {"time": ["2024-01-01"], "temperature_2m_min": [1], "temperature_2m_max": "warm"}}
    daily = weather.archive_daily(LISBON, date(2024, 1, 1), date(2024, 1, 1), timezone="auto")
    assert daily["temperature_2m_max"] is None and daily["precipitation_sum"] is None
    for answer in ({}, {"daily": []}, {"daily": {"time": "2024-01-01"}}):
        fake.answer = answer
        with pytest.raises(weather.ArchiveUnreadable, match="could not read"):
            weather.archive_daily(LISBON, date(2024, 1, 1), date(2024, 1, 1), timezone="auto")


def test_errors_are_the_weather_services_own_and_bad_coordinates_are_never_sent(fake):
    fake.down = True
    with pytest.raises(weather.WeatherError, match="Couldn't reach the weather service"):
        weather.archive_daily(LISBON, date(2024, 1, 1), date(2024, 1, 1), timezone="auto")
    calls = len(fake.calls)
    for bad in (float("nan"), True, "38", 91, 10 ** 400):
        with pytest.raises(weather.ArchiveUnreadable):
            weather.archive_daily({**LISBON, "latitude": bad}, date(2024, 1, 1), date(2024, 1, 1), timezone="auto")
    assert len(fake.calls) == calls


def test_the_home_climate_and_the_trips_both_ask_through_it(fake, monkeypatch, tmp_path):
    asked = []
    real = weather.archive_daily

    def spy(place, start, end, **kw):
        asked.append(kw["timezone"])
        return real(place, start, end, **kw)

    monkeypatch.setattr(weather, "archive_daily", spy)
    state = State(tmp_path / "settings.json")
    state.update(place=LISBON)
    assert climate.lookup(state)["used"]
    first = date(2027, 3, 1)
    days = tripweather.lookup(state, LISBON, first, first, TODAY)["days"]
    assert days[0]["source"] == "usual" and days[0]["low_c"] == 5.0 and days[0]["rain"] is True
    # the climate lets the service choose the time zone; a trip uses the place's own, as each always has
    assert asked == ["auto", "Europe/Lisbon"]
    assert len(fake.calls) == 2
