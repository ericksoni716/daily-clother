"""The weather for a trip: the forecast where it reaches, and what the dates are usually like beyond it.

Days inside Open-Meteo's forecast (FORECAST_DAYS from today) get the forecast:
one low, high and rain flag a day, read the same way as today's weather. Days
beyond it get what those dates are usually like: the same calendar days in each
of the last USUAL_YEARS years from Open-Meteo's historical archive, averaged,
with a day counted as rainy when it rained in at least USUAL_RAIN_SHARE of
those years. Every day says which it is (`forecast` or `usual`); a day whose
weather could not be had is `unknown`, and the answer says why in plain words.

As with today's weather, the only things sent are the place's latitude,
longitude and time zone and the dates; nothing about the closet. Answers are
kept (in the program's settings) and reused: the forecast for an hour, the
archive for a week.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

from . import weather
from .state import State

ARCHIVE_URL = weather.ARCHIVE_URL  # asked through weather.archive_daily, the lookup the home climate uses too
FORECAST_DAYS = 16           # Open-Meteo forecasts this many days, today included
MAX_TRIP_DAYS = 30           # a trip is at most this many days, first and last included
MAX_AHEAD_DAYS = 366         # a trip can start at most this many days from today
USUAL_YEARS = 5              # "usual" weather is the same dates in each of this many past years
USUAL_RAIN_SHARE = 0.5       # a usual day is rainy when it rained in at least this share of those years
RAIN_MM = 1.0                # a day in the archive with at least this much rain or snow (mm) counts as rainy
KEEP_FORECAST_S = weather.KEEP_S  # a trip's forecast is reused for this long (and only on the same day)
KEEP_USUAL_S = 7 * 86400     # the archive does not change; what it said is reused for a week
MAX_KEPT = 12                # at most this many forecasts and this many archive answers are kept
CHANGE_C = 3.0               # a saved day whose low or high moves this much has changed

SOURCES = ("forecast", "usual", "given", "unknown")


def check_dates(first: object, last: object, today: date) -> tuple[date, date]:
    """The trip's first and last days, or ValueError with a sentence the owner can read."""
    days = []
    for value, words in ((first, "first"), (last, "last")):
        try:
            if not isinstance(value, str) or len(value) != 10:
                raise ValueError
            days.append(date.fromisoformat(value))
        except ValueError:
            raise ValueError(f"Give the trip's {words} day as YYYY-MM-DD, for example 2026-12-04.") from None
    a, b = days
    if b < a:
        raise ValueError("The trip's last day is before its first day.")
    if a < today:
        raise ValueError("The trip has to start today or later.")
    if (b - a).days + 1 > MAX_TRIP_DAYS:
        raise ValueError(f"A trip can be at most {MAX_TRIP_DAYS} days long.")
    if (a - today).days > MAX_AHEAD_DAYS:
        raise ValueError("A trip can be planned at most a year ahead.")
    return a, b


def dates_of(first: date, last: date) -> list[str]:
    return [(first + timedelta(days=n)).isoformat() for n in range((last - first).days + 1)]


def unknown(day: str) -> dict:
    return {"date": day, "low_c": None, "high_c": None, "rain": None, "rain_chance": None, "summary": None,
            "source": "unknown"}


def _number(v: object) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v) else None


def _years_back(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # 29 February in a year without one
        return day.replace(year=day.year - years, day=28)


def _past_years(day: date, today: date) -> list[date]:
    """The most recent USUAL_YEARS calendar matches that are already in the archive."""
    out = []
    years = 1
    while len(out) < USUAL_YEARS:
        candidate = _years_back(day, years)
        if candidate < today:
            out.append(candidate)
        years += 1
    return out


# ---------------------------------------------------------------------- what is kept
def _kept(state: State, kind: str, key: str, max_age: float, on: str | None = None) -> dict | None:
    kept = state.get("trip_weather") or {}
    entry = (kept.get(kind) or {}).get(key)
    if not isinstance(entry, dict) or weather._now() - entry.get("fetched", 0) >= max_age:
        return None
    if on is not None and entry.get("on") != on:
        return None
    return entry.get("days") if isinstance(entry.get("days"), dict) else None


def _keep(state: State, kind: str, key: str, days: dict, on: str | None = None) -> None:
    def change(data: dict) -> None:
        kept = dict(data.get("trip_weather") or {})
        entries = dict(kept.get(kind) or {})
        entries[key] = {"fetched": weather._now(), "on": on, "days": days}
        for old in sorted(entries, key=lambda k: entries[k].get("fetched", 0))[:-MAX_KEPT]:
            del entries[old]
        kept[kind] = entries
        data["trip_weather"] = kept
    state.mutate(change)


# ---------------------------------------------------------------------- the forecast
def _forecast(place: dict) -> dict:
    """{date: day} for every day Open-Meteo forecasts at the place, today first."""
    data = weather._get(weather.FORECAST_URL, {
        "latitude": place["latitude"], "longitude": place["longitude"], "timezone": place["timezone"],
        "daily": "temperature_2m_min,temperature_2m_max,precipitation_probability_max,weather_code",
        "temperature_unit": "celsius", "forecast_days": FORECAST_DAYS})
    daily = data.get("daily")
    if not isinstance(daily, dict) or not isinstance(daily.get("time"), list):
        raise weather.WeatherError("The weather service gave an answer Closet could not read.")

    def column(name: str) -> list:
        values = daily.get(name)
        return values if isinstance(values, list) else []

    lows, highs = column("temperature_2m_min"), column("temperature_2m_max")
    chances, codes = column("precipitation_probability_max"), column("weather_code")
    out = {}
    for i, day in enumerate(daily["time"]):
        low = _number(lows[i]) if i < len(lows) else None
        high = _number(highs[i]) if i < len(highs) else None
        try:
            date.fromisoformat(day)
        except (TypeError, ValueError):
            continue
        if low is None or high is None:
            continue
        chance = _number(chances[i]) if i < len(chances) else None
        summary = weather._summary(codes[i] if i < len(codes) else None)
        rain = chance >= weather.RAIN_CHANCE if chance is not None else summary in weather.WET
        out[day] = {"date": day, "low_c": round(min(low, high), 1), "high_c": round(max(low, high), 1), "rain": rain,
                    "rain_chance": round(chance) if chance is not None else None, "summary": summary or "mixed",
                    "source": "forecast"}
    if not out:
        raise weather.WeatherError("The weather service gave an answer Closet could not read.")
    return out


# ---------------------------------------------------------------------- what the dates are usually like
def _usual(place: dict, days: list[str], today: date) -> dict:
    """{date: day} for each of `days` from the same dates in each of the last USUAL_YEARS years."""
    wanted = [date.fromisoformat(d) for d in days]
    history = {d: _past_years(d, today) for d in wanted}
    past_dates = [sample for samples in history.values() for sample in samples]
    start, end = min(past_dates), max(past_dates)
    daily = weather.archive_daily(place, start, end, timezone=place["timezone"])
    lows, highs, rains = (daily[k] or [] for k in weather.ARCHIVE_DAILY)
    past: dict[str, tuple[float | None, float | None, float | None]] = {}
    for i, day in enumerate(daily["time"]):
        if isinstance(day, str):
            past[day] = (_number(lows[i]) if i < len(lows) else None, _number(highs[i]) if i < len(highs) else None,
                         _number(rains[i]) if i < len(rains) else None)
    out = {}
    for d in wanted:
        temps, rained, years = [], 0, 0
        for sample in history[d]:
            low, high, rain = past.get(sample.isoformat(), (None, None, None))
            if low is not None and high is not None:
                temps.append((min(low, high), max(low, high)))
            if rain is not None:
                years += 1
                rained += rain >= RAIN_MM
        if not temps:
            continue
        out[d.isoformat()] = {
            "date": d.isoformat(), "low_c": round(sum(t[0] for t in temps) / len(temps), 1),
            "high_c": round(sum(t[1] for t in temps) / len(temps), 1),
            "rain": bool(years) and rained >= USUAL_RAIN_SHARE * years,
            "rain_chance": round(100 * rained / years) if years else None, "summary": None, "source": "usual"}
    return out


# ---------------------------------------------------------------------- a trip's days
def lookup(state: State, place: dict, first: date, last: date, today: date) -> dict:
    """The weather for every day of a trip: {"days": [day], "message": sentence or None}.

    Each day is {date, low_c, high_c, rain, rain_chance, summary, source}; `source` is `forecast`, `usual` or
    `unknown` (low, high and rain are then None). `message` says why some days are unknown.
    """
    days = dates_of(first, last)
    key = weather._key(place)
    found: dict[str, dict] = {}
    problems: list[str] = []
    if (first - today).days < FORECAST_DAYS:
        forecast = _kept(state, "forecast", key, KEEP_FORECAST_S, on=today.isoformat())
        if forecast is None:
            try:
                forecast = _forecast(place)
                _keep(state, "forecast", key, forecast, on=today.isoformat())
            except weather.WeatherError as e:
                forecast = {}
                problems.append(str(e))
        found.update({d: forecast[d] for d in days if d in forecast})
    rest = [d for d in days if d not in found]
    if rest:
        usual_key = f"{key}|{','.join(rest)}"
        usual = _kept(state, "usual", usual_key, KEEP_USUAL_S)
        if usual is None:
            try:
                usual = _usual(place, rest, today)
                _keep(state, "usual", usual_key, usual)
            except weather.WeatherError as e:
                usual = {}
                problems.append(str(e))
        found.update({d: usual[d] for d in rest if d in usual})
    out = [found.get(d) or unknown(d) for d in days]
    message = None
    if any(d["source"] == "unknown" for d in out):
        why = problems[-1] if problems else "The weather service has nothing for some of these dates."
        message = f"{why} Days without weather are left out of the plan until it can be looked up."
    return {"days": out, "message": message}


def given(first: date, last: date, value: object) -> list[dict]:
    """The weather given for every day of the trip, checked; ValueError with a sentence."""
    days = dates_of(first, last)
    if not isinstance(value, list) or not all(isinstance(d, dict) for d in value):
        raise ValueError("Give the weather as a list of days, each with a date, low_c, high_c and rain.")
    by_day = {d.get("date"): d for d in value}
    if sorted(k for k in by_day if isinstance(k, str)) != days or len(value) != len(days):
        raise ValueError("Give the weather for every day of the trip, once each, or for none.")
    out = []
    for day in days:
        d = by_day[day]
        low, high, rain = _number(d.get("low_c")), _number(d.get("high_c")), d.get("rain", False)
        if low is None or high is None or not isinstance(rain, bool):
            raise ValueError(f"The weather for {day} needs a low and a high in °C, and rain as true or false.")
        if low > high:
            raise ValueError(f"The low for {day} is above the high.")
        if not -50 <= low <= 55 or not -50 <= high <= 55:
            raise ValueError(f"The temperatures for {day} are not ones this app plans for.")
        out.append({"date": day, "low_c": round(low, 1), "high_c": round(high, 1), "rain": rain, "rain_chance": None,
                    "summary": None, "source": "given"})
    return out


def in_forecast(days: list[dict], today: date) -> bool:
    """True when some day of the trip, not yet past, is close enough for the forecast."""
    for d in days:
        try:
            ahead = (date.fromisoformat(d["date"]) - today).days
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= ahead < FORECAST_DAYS and d.get("source") != "given":
            return True
    return False


def changed(before: list[dict], after: list[dict]) -> bool:
    """True when a day's weather moved enough to plan again: it became known or forecast, its rain flipped,
    or its low or high moved by CHANGE_C or more. A day that became unknown is not a change."""
    old = {d.get("date"): d for d in before}
    for new in after:
        prev = old.get(new.get("date"))
        if prev is None or new.get("source") == "unknown":
            continue
        if prev.get("source") != new.get("source") or prev.get("rain") != new.get("rain"):
            return True
        for k in ("low_c", "high_c"):
            a, b = _number(prev.get(k)), _number(new.get(k))
            if a is None or b is None or abs(a - b) >= CHANGE_C:
                return True
    return False
