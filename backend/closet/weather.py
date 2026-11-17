"""Today's weather for the place the owner saved, from Open-Meteo (no key needed).

The place (a name, latitude, longitude and time zone) lives in the program's
settings, not in a closet, so the real and demo closets share it. Nothing is
guessed from the network address; until one is chosen it is New York. The only
things sent to Open-Meteo are the words typed into the place search and the
saved place's coordinates and time zone; nothing about the closet is. When the
owner taps "Use my location", the browser's position, rounded to about a
kilometre, is sent to OpenStreetMap's Nominatim to name the town, and nothing else.

The forecast also carries the day hour by hour (temperature, what it feels like, rain, wind, humidity and sun), which
`closet/day.py` reads for the hours the owner is out. A day spent somewhere else (`closet/daynote.py`) is looked up
for that place and kept apart from home's.

A forecast is kept for an hour and reused. When Open-Meteo cannot be reached
the last forecast for the same place is given back marked as old.
"""
from __future__ import annotations

import json
import logging
import math
import re
import time
import urllib.error
import urllib.request
from datetime import UTC, date, datetime
from urllib.parse import urlencode

from . import __version__, net
from .state import State

log = logging.getLogger("closet.weather")

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"   # names the place at a position (OpenStreetMap)
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_S = 6                # give up on Open-Meteo after this long
KEEP_S = 3600                # a forecast is reused for this long
RAIN_CHANCE = 50             # a chance of rain (%) at or above this counts as a rainy day
MAX_PLACES = 8               # places offered for one search
MAX_QUERY = 100              # longest place search sent
MAX_BYTES = 1 << 20          # longest answer read
NEAR_DIGITS = 2              # a position from the browser is rounded to about a kilometre before it is sent or saved
TOWN = ("city", "town", "village", "municipality", "hamlet", "suburb", "county")   # the first one found names the place
TIMEZONE = re.compile(r"^[A-Za-z0-9_+\-/]{1,64}$")

# WMO weather codes (what Open-Meteo reports) to one word.
SUMMARY = ((0, 1, "clear"), (2, 3, "cloudy"), (45, 48, "foggy"), (51, 57, "drizzle"), (61, 67, "rain"),
           (71, 77, "snow"), (80, 82, "rain"), (85, 86, "snow"), (95, 99, "storms"))
WET = ("drizzle", "rain", "snow", "storms")
# What is asked for each hour of the day, and the range each may be in (anything else is left out as unknown)
HOURLY = {"temperature_2m": (-90, 60), "apparent_temperature": (-110, 70), "precipitation_probability": (0, 100),
          "precipitation": (0, 500), "wind_speed_10m": (0, 400), "wind_gusts_10m": (0, 500),
          "relative_humidity_2m": (0, 100), "uv_index": (0, 20), "weather_code": (0, 99)}


class WeatherError(Exception):
    """Open-Meteo could not be asked or gave an answer that cannot be used, in words the owner can read."""


def fetch(url: str) -> bytes:
    """One GET to Open-Meteo through the computer's certificates. Tests replace this."""
    req = urllib.request.Request(url, headers={"User-Agent": f"Closet/{__version__}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S, context=net.ssl_context()) as r:
        return r.read(MAX_BYTES + 1)


def _now() -> float:
    """Unix time (a function so tests can move the clock)."""
    return time.time()


def _get(url: str, params: dict, service: str = "weather service") -> dict:
    try:
        raw = fetch(f"{url}?{urlencode(params)}")
        if len(raw) > MAX_BYTES:
            raise WeatherError(f"The {service} gave an answer that was too large.")
        data = json.loads(raw)
    except urllib.error.HTTPError as e:
        log.warning("%s answered %s", service, e.code)
        raise WeatherError(f"The {service} answered with an error ({e.code}).") from None
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        log.warning("%s not reached: %s", service, type(e).__name__)
        if net.is_certificate_error(e):
            raise WeatherError(f"The {service}'s security certificate could not be checked on this computer.") from None
        raise WeatherError(f"Couldn't reach the {service}. Check the internet connection.") from None
    except ValueError:
        raise WeatherError(f"The {service} gave an answer Closet could not read.") from None
    if not isinstance(data, dict):
        raise WeatherError(f"The {service} gave an answer Closet could not read.")
    return data


# ---------------------------------------------------------------------- places
def search_places(query: str) -> list[dict]:
    """Places whose name matches, to choose from: [{name, latitude, longitude, timezone}]."""
    q = " ".join(str(query or "").split())[:MAX_QUERY]
    if len(q) < 2:
        return []
    data = _get(GEOCODING_URL, {"name": q, "count": MAX_PLACES, "language": "en", "format": "json"})
    out = []
    for r in data.get("results") or []:
        try:
            place = check_place({
                "name": ", ".join(dict.fromkeys(str(r[k]).strip() for k in ("name", "admin1", "country") if r.get(k))),
                "latitude": r.get("latitude"), "longitude": r.get("longitude"), "timezone": r.get("timezone") or "auto"})
        except ValueError:
            continue
        out.append(place)
    return out[:MAX_PLACES]


def place_near(latitude: object, longitude: object) -> dict:
    """The town or city at a position the browser gave on the owner's tap, as it is saved.

    Open-Meteo cannot name a position, so OpenStreetMap's Nominatim does: it is sent only the coordinates, rounded
    to about a kilometre. The time zone is left to Open-Meteo ("auto"). ValueError for coordinates that are not
    numbers on the globe; WeatherError when the service cannot be reached or names no town there.
    """
    for v, limit, words in ((latitude, 90, "latitude"), (longitude, 180, "longitude")):
        if isinstance(v, bool) or not isinstance(v, int | float) or not -limit <= v <= limit:
            raise ValueError(f"The {words} must be a number from -{limit} to {limit}.")
    lat, lon = round(float(latitude), NEAR_DIGITS), round(float(longitude), NEAR_DIGITS)
    data = _get(REVERSE_URL, {"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 10, "accept-language": "en"},
                service="place-name service")
    address = data.get("address") if isinstance(data.get("address"), dict) else {}
    town = next((address[k] for k in TOWN if isinstance(address.get(k), str) and address[k].strip()), None)
    parts = (town, address.get("state"), address.get("country"))
    name = ", ".join(dict.fromkeys(p.strip() for p in parts if isinstance(p, str) and p.strip()))
    if not town or not name:
        raise WeatherError("No town or city was found where you are. Search for your place by name instead.")
    try:
        return check_place({"name": name, "latitude": lat, "longitude": lon, "timezone": "auto"})
    except ValueError:
        raise WeatherError("No town or city was found where you are. Search for your place by name instead.") from None


def check_place(place: object) -> dict:
    """A place as it is saved, or ValueError with a sentence."""
    if not isinstance(place, dict):
        raise ValueError("A place needs a name, latitude, longitude and time zone.")
    name = " ".join(str(place.get("name") or "").split())
    lat, lon, tz = place.get("latitude"), place.get("longitude"), place.get("timezone") or "auto"
    if not name or len(name) > 200:
        raise ValueError("The place needs a name.")
    for v, limit, words in ((lat, 90, "latitude"), (lon, 180, "longitude")):
        if isinstance(v, bool) or not isinstance(v, int | float) or not -limit <= v <= limit:
            raise ValueError(f"The place's {words} must be a number from -{limit} to {limit}.")
    if not isinstance(tz, str) or not TIMEZONE.match(tz):
        raise ValueError("The place's time zone is not one Closet knows, for example America/New_York.")
    return {"name": name, "latitude": round(float(lat), 4), "longitude": round(float(lon), 4), "timezone": tz}


def _key(place: dict) -> str:
    return f"{place['latitude']},{place['longitude']},{place['timezone']}"


# ---------------------------------------------------------------------- forecast
def _summary(code: object) -> str | None:
    if isinstance(code, bool) or not isinstance(code, int | float):
        return None
    for lo, hi, word in SUMMARY:
        if lo <= code <= hi:
            return word
    return None


def _hours(data: dict, day: str) -> list[dict]:
    """The day hour by hour, as the weather service gave it: [{hour, temp_c, feels_c, rain_chance, rain_mm, wind_kmh,
    gust_kmh, humidity, uv, summary}], an hour without a temperature left out and anything else unknown as None
    (what it feels like falls back on the temperature). [] when no hours can be read: the day's low and high still
    stand, so this never fails a forecast."""
    hourly = data.get("hourly")
    times = hourly.get("time") if isinstance(hourly, dict) else None
    if not isinstance(times, list):
        return []

    def at(name: str, i: int) -> float | None:
        column = hourly.get(name)
        v = column[i] if isinstance(column, list) and i < len(column) else None
        lo, hi = HOURLY[name]
        if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v) or not lo <= v <= hi:
            return None
        return round(float(v), 1)

    out, seen = [], set()
    for i, t in enumerate(times):
        if not isinstance(t, str) or not t.startswith(f"{day}T") or not t[11:13].isdigit():
            continue
        hour, temp = int(t[11:13]), at("temperature_2m", i)
        if hour > 23 or hour in seen or temp is None:
            continue
        seen.add(hour)
        feels, chance = at("apparent_temperature", i), at("precipitation_probability", i)
        out.append({"hour": hour, "temp_c": temp, "feels_c": temp if feels is None else feels,
                    "rain_chance": None if chance is None else round(chance), "rain_mm": at("precipitation", i),
                    "wind_kmh": at("wind_speed_10m", i), "gust_kmh": at("wind_gusts_10m", i),
                    "humidity": at("relative_humidity_2m", i), "uv": at("uv_index", i),
                    "summary": _summary(at("weather_code", i))})
    return sorted(out, key=lambda h: h["hour"])


def _forecast(place: dict) -> tuple[dict, int]:
    data = _get(FORECAST_URL, {
        "latitude": place["latitude"], "longitude": place["longitude"], "timezone": place["timezone"],
        "daily": "temperature_2m_min,temperature_2m_max,precipitation_probability_max,weather_code",
        "hourly": ",".join(HOURLY), "temperature_unit": "celsius", "wind_speed_unit": "kmh",
        "precipitation_unit": "mm", "forecast_days": 1})
    daily = data.get("daily")
    try:
        day = daily["time"][0]
        low, high = daily["temperature_2m_min"][0], daily["temperature_2m_max"][0]
        chance = (daily.get("precipitation_probability_max") or [None])[0]
        code = (daily.get("weather_code") or [None])[0]
        if not all(isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v) for v in (low, high)):
            raise TypeError
        if low > high:
            raise ValueError
        datetime.strptime(day, "%Y-%m-%d")
        if isinstance(chance, int | float) and not isinstance(chance, bool):
            if not math.isfinite(chance) or not 0 <= chance <= 100:
                raise ValueError
            chance = round(chance)
        else:
            chance = None
        offset = data.get("utc_offset_seconds")
        if isinstance(offset, int | float) and not isinstance(offset, bool):
            if not math.isfinite(offset) or not -86400 <= offset <= 86400:
                raise ValueError
            offset = int(offset)
        else:
            offset = 0
    except (KeyError, IndexError, TypeError, ValueError, AttributeError, OverflowError):
        raise WeatherError("The weather service gave an answer Closet could not read.") from None
    summary = _summary(code)
    rain = chance >= RAIN_CHANCE if chance is not None else summary in WET
    answer = {"date": day, "low_c": round(float(low), 1), "high_c": round(float(high), 1), "rain_chance": chance,
              "rain": rain, "summary": summary or "mixed", "hours": _hours(data, day),
              "fetched_at": datetime.fromtimestamp(_now(), UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
    return answer, offset


def _place_today(offset: int) -> str:
    return datetime.fromtimestamp(_now() + offset, UTC).date().isoformat()


def _hour_at(offset: int) -> int:
    """The hour of the day it is now at a place (0 to 23)."""
    return datetime.fromtimestamp(_now() + offset, UTC).hour


def lookup(state: State, away: dict | None = None) -> dict:
    """Today's weather for the saved place, or for `away`: the place of a day spent somewhere else.

    Returns {place, weather, old, message, is_today, hour}: `weather` is {date, low_c, high_c, rain_chance, rain,
    summary, hours, fetched_at} or None (`hours`: the day hour by hour, see `_hours`; a forecast kept from an older
    Closet has none); `old` is true when it is a forecast kept from before because Open-Meteo
    could not be reached; `message` says in plain words why there is no weather, or that it is old;
    `is_today` says whether the forecast is for today at the place (an old one may be for an earlier day);
    `hour` is the hour it is now at the place (None without a forecast). Home's forecast and an away day's are
    kept apart, so asking for one never throws the other away.
    """
    place = away or state.get("place")
    slot = "weather_away" if away else "weather"
    if not place:
        return {"place": None, "weather": None, "old": False, "is_today": False, "hour": None,
                "message": "Choose where you are in Settings to see today's weather."}
    key, kept = _key(place), state.get(slot)
    if not (isinstance(kept, dict) and kept.get("key") == key):
        kept = None
    if kept and _now() - kept["fetched"] < KEEP_S and kept["answer"]["date"] == _place_today(kept["offset"]):
        return {"place": place, "weather": kept["answer"], "old": False, "message": None, "is_today": True,
                "hour": _hour_at(kept["offset"])}
    try:
        answer, offset = _forecast(place)
    except WeatherError as e:
        if kept:
            return {"place": place, "weather": kept["answer"], "old": True, "hour": _hour_at(kept["offset"]),
                    "is_today": kept["answer"]["date"] == _place_today(kept["offset"]),
                    "message": f"{e} This is the last forecast Closet got."}
        return {"place": place, "weather": None, "old": False, "is_today": False, "hour": None,
                "message": f"{e} Try again later, or give today's temperatures yourself."}
    if away or state.get("place") == place:  # the place may have been changed while Open-Meteo was asked
        state.update(**{slot: {"key": key, "fetched": _now(), "offset": offset, "answer": answer}})
    return {"place": place, "weather": answer, "old": False, "message": None, "hour": _hour_at(offset),
            "is_today": answer["date"] == _place_today(offset)}


# ---------------------------------------------------------------------- past weather
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
ARCHIVE_DAILY = ("temperature_2m_min", "temperature_2m_max", "precipitation_sum")
UNREADABLE = "The weather service gave an answer Closet could not read."


class ArchiveUnreadable(WeatherError):
    """The archive answered, or would be asked, with something that is not a list of days."""

    def __init__(self) -> None:
        super().__init__(UNREADABLE)


def _coordinate(value: object, limit: int) -> bool:
    try:
        return (isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)
                and -limit <= value <= limit)
    except OverflowError:
        return False


def archive_daily(place: dict, start: date, end: date, *, timezone: str,
                  precipitation_unit: str | None = None, fields: tuple[str, ...] = ARCHIVE_DAILY) -> dict[str, list | None]:
    """The one lookup of Open-Meteo's archive, shared by the home climate and the trips' usual weather.

    Sends only the place's latitude and longitude, the time zone given, the dates and the daily fields; goes
    through `_get` (the computer's certificates, a bounded wait and size, errors in the owner's words). Returns
    the daily columns as the archive gave them: {"time": [...], "temperature_2m_min": list or None, ...}, a
    column that is not a list being None. What a missing day or value means is the caller's to decide; each
    keeps what it worked out in its own way. `fields` are the daily columns asked for (ARCHIVE_DAILY unless a
    caller needs more). Raises WeatherError, ArchiveUnreadable when there is no list of days.
    """
    if not _coordinate(place.get("latitude"), 90) or not _coordinate(place.get("longitude"), 180):
        raise ArchiveUnreadable
    params = {"latitude": place["latitude"], "longitude": place["longitude"], "timezone": timezone,
              "start_date": start.isoformat(), "end_date": end.isoformat(), "daily": ",".join(fields),
              "temperature_unit": "celsius"}
    if precipitation_unit:
        params["precipitation_unit"] = precipitation_unit
    daily = _get(ARCHIVE_URL, params).get("daily")
    if not isinstance(daily, dict) or not isinstance(daily.get("time"), list):
        raise ArchiveUnreadable
    return {"time": daily["time"],
            **{field: daily[field] if isinstance(daily.get(field), list) else None for field in fields}}
