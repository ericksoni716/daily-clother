"""Trip weather: forecasts nearby, five completed calendar years further away."""
from __future__ import annotations

import math
import threading
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import weather

FORECAST_DAYS = 16
MAX_TRIP_DAYS = 30
HISTORY_YEARS = 5
RAIN_MM = 0.1
RAIN_YEAR_SHARE = 0.5
USUAL_KEEP_S = 7 * 86400
RETRY_S = 300
MAX_CACHE_ENTRIES = 64
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
_cache_lock = threading.Lock()


def today(place: dict) -> date:
    try:
        zone = ZoneInfo(place["timezone"]) if place["timezone"] != "auto" else UTC
    except ZoneInfoNotFoundError:
        raise ValueError("Choose a place with a time zone Closet knows.") from None
    return datetime.fromtimestamp(weather._now(), zone).date()


def dates(first: object, last: object) -> list[date]:
    try:
        start, end = date.fromisoformat(first), date.fromisoformat(last)
        if start.isoformat() != first or end.isoformat() != last:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("Give the first and last day as dates, for example 2027-06-14.") from None
    length = (end - start).days + 1
    if not 1 <= length <= MAX_TRIP_DAYS:
        raise ValueError(f"A trip needs 1 to {MAX_TRIP_DAYS} days, with the last day after the first.")
    return [start + timedelta(days=i) for i in range(length)]


def _historical(day: date, year: int) -> date:
    # February 28 is the nearest calendar day in years without a February 29.
    try:
        return day.replace(year=year)
    except ValueError:
        return date(year, 2, 28)


def _daily(data: dict, archive: bool) -> dict[str, dict]:
    out = {}
    daily = data.get("daily") or {}
    try:
        for i, day in enumerate(daily["time"]):
            low, high = daily["temperature_2m_min"][i], daily["temperature_2m_max"][i]
            if not all(isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v) for v in (low, high)):
                continue
            if not -50 <= low <= high <= 55:
                continue
            date.fromisoformat(day)
            if archive:
                mm = daily["precipitation_sum"][i]
                if not isinstance(mm, int | float) or isinstance(mm, bool) or not math.isfinite(mm) or mm < 0:
                    continue
                rain = mm >= RAIN_MM
            else:
                chance = (daily.get("precipitation_probability_max") or [None] * len(daily["time"]))[i]
                code = (daily.get("weather_code") or [None] * len(daily["time"]))[i]
                rain = (chance >= weather.RAIN_CHANCE if isinstance(chance, int | float) and not isinstance(chance, bool)
                        else weather._summary(code) in weather.WET)
            out[day] = {"low_c": round(low, 1), "high_c": round(high, 1), "rain": rain}
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        raise weather.WeatherError("The weather service gave an answer Closet could not read.") from None
    return out


def lookup(state, place: dict, first: str, last: str) -> list[dict]:
    """Return one entry per day; a failed part never hides the other part.

    The bounded cache survives restarts. Cache keys include today's date so a
    usual day becoming a forecast cannot reuse yesterday's usual answer.
    """
    place = weather.check_place(place)
    days, now = dates(first, last), today(place)
    key = f"{weather._key(place)}:{first}:{last}:{now}"
    with _cache_lock:
        kept = (state.get("trip_weather") or {}).get(key)
    stamp = weather._now()
    if kept and stamp < kept["expires"]:
        return kept["days"]
    params = {k: place[k] for k in ("latitude", "longitude", "timezone")}
    forecast_days = [d for d in days if now <= d < now + timedelta(days=FORECAST_DAYS)]
    usual_days = [d for d in days if d >= now + timedelta(days=FORECAST_DAYS)]
    found, errors = {}, {}
    if forecast_days:
        try:
            found = _daily(weather._get(weather.FORECAST_URL, {
                **params, "start_date": forecast_days[0].isoformat(), "end_date": forecast_days[-1].isoformat(),
                "daily": "temperature_2m_min,temperature_2m_max,precipitation_probability_max,weather_code",
            }), False)
        except weather.WeatherError as e:
            errors["forecast"] = str(e)
    samples = {d: [] for d in usual_days}
    if usual_days:
        for year in range(now.year - 1, now.year - HISTORY_YEARS - 1, -1):
            mapped = {d: _historical(d, year) for d in usual_days}
            try:
                history = _daily(weather._get(ARCHIVE_URL, {
                    **params, "start_date": min(mapped.values()).isoformat(), "end_date": max(mapped.values()).isoformat(),
                    "daily": "temperature_2m_min,temperature_2m_max,precipitation_sum",
                }), True)
                for d, past in mapped.items():
                    if past.isoformat() in history:
                        samples[d].append(history[past.isoformat()])
            except weather.WeatherError as e:
                errors["usual"] = str(e)
        for d, years in samples.items():
            if len(years) == HISTORY_YEARS:
                found[d.isoformat()] = {
                    "low_c": round(sum(y["low_c"] for y in years) / HISTORY_YEARS, 1),
                    "high_c": round(sum(y["high_c"] for y in years) / HISTORY_YEARS, 1),
                    "rain": sum(y["rain"] for y in years) >= HISTORY_YEARS * RAIN_YEAR_SHARE,
                }
    answer = []
    for d in days:
        source = "forecast" if d in forecast_days else "usual"
        values = found.get(d.isoformat())
        answer.append({
            "date": d.isoformat(), "source": source, **(values or {"low_c": None, "high_c": None, "rain": None}),
            "message": None if values else errors.get(source, "The weather for this day is not available. Try again later."),
        })
    ttl = RETRY_S if any(d["message"] for d in answer) else weather.KEEP_S if forecast_days else USUAL_KEEP_S
    with _cache_lock:
        cache = dict(state.get("trip_weather") or {})
        cache[key] = {"expires": stamp + ttl, "days": answer}
        cache = dict(sorted(cache.items(), key=lambda entry: entry[1]["expires"])[-MAX_CACHE_ENTRIES:])
        state.update(trip_weather=cache)
    return answer
