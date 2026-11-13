import io
import json
import urllib.error
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest

from closet import climate, net, weather
from closet.state import State

PLACE = {"name": "Example town", "latitude": 40.0, "longitude": -70.0, "timezone": "America/New_York"}
NOW = datetime(2026, 6, 1, tzinfo=UTC).timestamp()
YEARS = [2022, 2023, 2024, 2025]


def canned(start=date(2022, 1, 1), end=date(2025, 12, 31)):
    fields = ("time", "temperature_2m_min", "temperature_2m_max", "precipitation_sum")
    daily = {field: [] for field in fields}
    for i in range((end - start).days + 1):
        day = start + timedelta(days=i)
        # Design temperatures sit exactly on each band boundary.
        temp = (8, 14.9, 15, 24)[i % 4]
        for field, value in zip(fields, (day.isoformat(), temp - 3, temp + 7, 1 if i % 8 < 4 else 0.9), strict=True):
            daily[field].append(value)
    return {"daily": daily}


@pytest.fixture
def fake(monkeypatch):
    class Service:
        def __init__(self):
            self.now = NOW
            self.data = canned()
            self.calls = []
            self.error = None

        def fetch(self, url):
            self.calls.append(url)
            if self.error:
                raise self.error
            return json.dumps(self.data).encode()

    service = Service()
    monkeypatch.setattr(weather, "_now", lambda: service.now)
    monkeypatch.setattr(weather, "fetch", service.fetch)
    return service


@pytest.fixture
def state(tmp_path):
    result = State(tmp_path / "settings.json")
    result.update(place=PLACE)
    return result


def test_full_year_shares_boundaries_and_request_privacy(state, fake):
    answer = climate.lookup(state)
    assert answer["used"] and not answer["old"] and answer["message"] is None
    assert answer["place"] == PLACE["name"] and answer["years"] == YEARS
    assert answer["shares"] == {
        "cold": {"share": 366 / 1461, "wet_share": 183 / 366},
        "cool": {"share": 365 / 1461, "wet_share": 183 / 365},
        "mild": {"share": 365 / 1461, "wet_share": 183 / 365},
        "hot": {"share": 365 / 1461, "wet_share": 183 / 365},
    }
    request = urlsplit(fake.calls[0])
    assert request.scheme == "https" and request.netloc + request.path == "archive-api.open-meteo.com/v1/archive"
    assert parse_qs(request.query) == {
        "latitude": ["40.0"], "longitude": ["-70.0"], "timezone": ["auto"],
        "start_date": ["2022-01-01"], "end_date": ["2025-12-31"],
        "daily": ["temperature_2m_min,temperature_2m_max,precipitation_sum"],
        "temperature_unit": ["celsius"], "precipitation_unit": ["mm"],
    }


def test_no_place_never_calls_weather(state, fake):
    state.update(place=None)
    assert climate.lookup(state) == {
        "used": False, "place": None, "shares": None, "years": [], "old": False, "message": climate.NO_PLACE,
    }
    assert not fake.calls


def test_empty_bands_do_not_invent_rain(state, fake):
    daily = fake.data["daily"]
    daily["temperature_2m_min"] = [30] * 1461
    daily["temperature_2m_max"] = [30] * 1461
    shares = climate.lookup(state)["shares"]
    assert shares["hot"]["share"] == 1
    assert all(shares[band] == {"share": 0.0, "wet_share": 0.0} for band in ("cold", "cool", "mild"))


@pytest.mark.parametrize("temperature,band", [
    (-10, "cold"), (8, "cold"), (8.01, "cool"), (14.99, "cool"),
    (15, "mild"), (23.99, "mild"), (24, "hot"), (40, "hot"),
])
def test_temperature_bands(temperature, band, state, fake):
    fake.data["daily"]["temperature_2m_min"] = [temperature] * 1461
    fake.data["daily"]["temperature_2m_max"] = [temperature] * 1461
    assert climate.lookup(state)["shares"][band]["share"] == 1


def test_cache_persists_and_expires_at_180_days(state, fake):
    first = climate.lookup(state)
    fake.now += climate.KEEP_S - 1
    assert climate.lookup(State(state.path)) == first
    assert len(fake.calls) == 1
    fake.now += 1
    assert climate.lookup(state) == first
    assert len(fake.calls) == 2


def test_utc_new_year_refreshes_even_fresh_cache(state, fake):
    fake.now = datetime(2026, 12, 31, 23, 59, tzinfo=UTC).timestamp()
    climate.lookup(state)
    fake.now += 120
    # A successful recent fetch does not throttle the new-year refresh.
    fake.data = canned(date(2023, 1, 1), date(2026, 12, 31))
    result = climate.lookup(state)
    assert result["years"] == [2023, 2024, 2025, 2026]
    assert len(fake.calls) == 2


@pytest.mark.parametrize("error", [urllib.error.URLError("offline"), TimeoutError(), OSError()])
def test_failure_without_cache_is_clear_and_throttled(state, fake, error):
    fake.error = error
    first = climate.lookup(state)
    assert first == {
        "used": False, "place": PLACE["name"], "shares": None, "years": [], "old": False,
        "message": climate.UNAVAILABLE,
    }
    fake.now += climate.RETRY_S - 1
    assert climate.lookup(State(state.path)) == first and len(fake.calls) == 1
    fake.now += 1
    fake.error = None
    assert climate.lookup(state)["used"] and len(fake.calls) == 2


def test_old_same_place_cache_survives_failure_and_retries(state, fake):
    first = climate.lookup(state)
    fake.now += climate.KEEP_S
    fake.error = urllib.error.URLError("offline")
    old = climate.lookup(state)
    assert old == {**first, "old": True, "message": climate.OLD}
    assert climate.lookup(state) == old and len(fake.calls) == 2
    fake.now += climate.RETRY_S
    fake.error = None
    assert climate.lookup(state) == first and len(fake.calls) == 3


def test_different_place_cannot_reuse_cache_or_failure_throttle(state, fake):
    climate.lookup(state)
    state.update(place={**PLACE, "name": "Another town", "latitude": 41})
    fake.error = urllib.error.URLError("offline")
    answer = climate.lookup(state)
    assert not answer["used"] and not answer["old"] and answer["shares"] is None
    assert answer["place"] == "Another town" and len(fake.calls) == 2


def test_same_coordinates_new_name_uses_current_name(state, fake):
    climate.lookup(state)
    state.update(place={**PLACE, "name": "Renamed town"})
    assert climate.lookup(state)["place"] == "Renamed town" and len(fake.calls) == 1


@pytest.mark.parametrize("failure", [False, True])
@pytest.mark.parametrize("new_place", [None, {**PLACE, "name": "Another town", "longitude": 20}])
def test_place_changed_during_fetch_is_not_overwritten(state, fake, monkeypatch, failure, new_place):
    marker = {"key": "other place"}

    def fetch(url):
        state.update(place=new_place)
        state.mutate(lambda data: data.update(climate=marker))
        if failure:
            raise urllib.error.URLError("offline")
        return json.dumps(fake.data).encode()

    monkeypatch.setattr(weather, "fetch", fetch)
    answer = climate.lookup(state)
    assert state.get("climate") == marker
    assert not answer["used"] and answer["shares"] is None
    assert answer["place"] == (new_place["name"] if new_place else None)


def test_concurrent_lookup_reserves_retry_without_duplicate_request(state, fake, monkeypatch):
    def fetch(url):
        nested = climate.lookup(state)
        assert not nested["used"]
        return fake.fetch(url)

    monkeypatch.setattr(weather, "fetch", fetch)
    assert climate.lookup(state)["used"]
    assert len(fake.calls) == 1


def test_place_changed_before_reservation_does_not_make_a_request(state, fake, monkeypatch):
    mutate = state.mutate

    def raced_mutate(fn):
        state.update(place=None)
        return mutate(fn)

    monkeypatch.setattr(state, "mutate", raced_mutate)
    assert climate.lookup(state)["place"] is None
    assert not fake.calls


def test_invalid_refresh_preserves_old_valid_shares(state, fake):
    first = climate.lookup(state)
    fake.now += climate.KEEP_S
    fake.data["daily"]["precipitation_sum"][0] = None
    assert climate.lookup(state) == {**first, "old": True, "message": climate.OLD}


@pytest.mark.parametrize("field,value", [
    ("temperature_2m_min", None), ("temperature_2m_max", True),
    ("temperature_2m_min", "8"), ("temperature_2m_min", float("nan")),
    ("temperature_2m_min", 10 ** 400),
    ("temperature_2m_max", float("inf")), ("temperature_2m_min", -101),
    ("temperature_2m_max", -20), ("temperature_2m_max", 71),
    ("precipitation_sum", None), ("precipitation_sum", -1),
    ("precipitation_sum", float("nan")), ("precipitation_sum", 3001),
    ("time", "2022-1-1"), ("time", "2022-01-02"), ("time", "2022-02-30"),
    ("time", None),
])
def test_invalid_day_never_becomes_a_percentage(state, fake, field, value):
    fake.data["daily"][field][0] = value
    answer = climate.lookup(state)
    assert not answer["used"] and answer["shares"] is None
    assert "not being used" in answer["message"]
    assert "answer" not in state.get("climate")


@pytest.mark.parametrize("damage", ["missing_field", "short_array", "short_year", "empty", "wrong_type", "no_daily"])
def test_incomplete_coverage_is_rejected(state, fake, damage):
    daily = fake.data["daily"]
    if damage == "missing_field":
        del daily["precipitation_sum"]
    elif damage == "short_array":
        daily["temperature_2m_min"].pop()
    elif damage == "short_year":
        for field in daily:
            daily[field] = daily[field][90:]
    elif damage == "empty":
        fake.data["daily"] = dict.fromkeys(daily, [])
    elif damage == "wrong_type":
        daily["precipitation_sum"] = {}
    else:
        fake.data = {}
    assert climate.lookup(state)["shares"] is None


def test_unreadable_or_oversized_response_has_no_shares(state, fake, monkeypatch):
    for raw in (b"[]", b"{bad", b" " * weather.MAX_BYTES + b"{}"):
        state.mutate(lambda data: data.update(climate=None))
        monkeypatch.setattr(weather, "fetch", lambda url, raw=raw: raw)
        assert climate.lookup(state)["shares"] is None


def test_bad_cache_is_not_used_as_old_weather(state, fake):
    climate.lookup(state)
    kept = deepcopy(state.get("climate"))
    kept["answer"]["shares"]["cold"]["share"] = float("nan")
    state.mutate(lambda data: data.update(climate=kept))
    fake.now += climate.RETRY_S
    fake.error = urllib.error.URLError("offline")
    assert climate.lookup(state)["shares"] is None


def test_archive_is_reusable_for_an_explicit_short_range(fake):
    fake.data = canned(date(2024, 2, 28), date(2024, 3, 1))
    rows = climate.archive(PLACE, date(2024, 2, 28), date(2024, 3, 1))
    assert [row["date"] for row in rows] == ["2024-02-28", "2024-02-29", "2024-03-01"]
    assert set(rows[0]) == {"date", "low_c", "high_c", "precipitation_mm"}
    with pytest.raises(ValueError):
        climate.archive(PLACE, date(2024, 3, 1), date(2024, 2, 28))


@pytest.mark.parametrize("coordinate", [float("inf"), float("nan"), True, "40", 181, 10 ** 400])
def test_archive_refuses_invalid_coordinates_before_network(fake, coordinate):
    with pytest.raises(weather.WeatherError):
        climate.archive({**PLACE, "longitude": coordinate}, date(2024, 1, 1), date(2024, 1, 2))
    assert not fake.calls


def test_fetch_has_bounded_read_timeout_and_system_certificates(monkeypatch):
    context = object()
    seen = {}

    class Response(io.BytesIO):
        def read(self, size=-1):
            seen["read_size"] = size
            return super().read(size)

    def open_url(request, *, timeout, context):
        seen.update(timeout=timeout, context=context, url=request.full_url)
        return Response(b"{}" + b" " * weather.MAX_BYTES)

    monkeypatch.setattr(net, "ssl_context", lambda: context)
    monkeypatch.setattr(weather.urllib.request, "urlopen", open_url)
    with pytest.raises(weather.WeatherError, match="too large"):
        weather._get(climate.ARCHIVE_URL, {})
    assert seen == {"timeout": weather.TIMEOUT_S, "context": context,
                    "url": climate.ARCHIVE_URL + "?", "read_size": weather.MAX_BYTES + 1}


def test_exact_size_valid_json_is_accepted(monkeypatch):
    monkeypatch.setattr(weather, "fetch", lambda url: b"{}" + b" " * (weather.MAX_BYTES - 2))
    assert weather._get(climate.ARCHIVE_URL, {}) == {}
