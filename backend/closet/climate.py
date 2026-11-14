"""Recent full years of home weather, without sending anything about the closet.

The archive is asked through `weather.archive_daily`, the one lookup the trips'
usual weather uses too; `archive` adds this module's stricter reading of it
(every day and every value, or nothing).
"""
from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta

from . import weather
from .state import State

ARCHIVE_URL = weather.ARCHIVE_URL
YEARS = 4
# Open-Meteo's archive can lag about five days. Allow seven complete UTC days
# after New Year: the newly finished year is first requested on January 8.
ARCHIVE_GRACE_DAYS = 7
KEEP_S = 180 * 24 * 3600
RETRY_S = 3600
WET_MM = 1
DESIGN_FRACTION = 0.3
COLD_C = 8
MILD_C = 15
HOT_C = 24
BANDS = ("cold", "cool", "mild", "hot")
NO_PLACE = "Home weather is not being used. Choose where you are in Settings."
UNAVAILABLE = "Home weather is not being used. Check the internet connection or choose your place in Settings."
OLD = "Using older home weather saved for this place. Check the internet connection; Closet will try again later."
INCOMPLETE = "Home weather is not being used. The weather service has not provided complete daily weather yet. Closet will try again later."
OLD_INCOMPLETE = "Using older home weather saved for this place. The weather service has not provided complete daily weather yet; Closet will try again later."
INVALID = "The weather service did not give complete daily home weather."


class IncompleteArchive(weather.WeatherError):
    """The first missing day, separate from a connection or malformed-data error."""

    def __init__(self, missing_from: date):
        super().__init__(INVALID)
        self.missing_from = missing_from


def _finite(value: object) -> bool:
    try:
        return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        return False


def archive(place: dict, start: date, end: date) -> list[dict]:
    """Fetch inclusive daily dates, low/high °C and precipitation mm.

    Every requested date and measurement must be present, once and in order.
    Incomplete years must not turn a missing season or missing rain into a
    believable percentage. Raises weather.WeatherError for an unusable answer.
    """
    if start > end:
        raise ValueError("The first archive day must not follow the last.")
    try:
        daily = weather.archive_daily(place, start, end, timezone="auto", precipitation_unit="mm")
    except weather.ArchiveUnreadable:
        raise weather.WeatherError(INVALID) from None
    fields = ("time", *weather.ARCHIVE_DAILY)
    count = (end - start).days + 1
    if any(daily[field] is None for field in fields):
        raise weather.WeatherError(INVALID)
    lengths = {len(daily[field]) for field in fields}
    if max(lengths) > count:
        raise weather.WeatherError(INVALID)
    rows = []
    # Validate the complete prefix before identifying the first missing day.
    for i, (day, low, high, rain) in enumerate(zip(*(daily[field] for field in fields), strict=False)):
        expected = start + timedelta(days=i)
        if day != expected.isoformat():
            raise weather.WeatherError(INVALID)
        if any(value is None for value in (low, high, rain)):
            raise IncompleteArchive(expected)
        if (not all(_finite(value) for value in (low, high, rain))
                or not -100 <= low <= high <= 70 or not 0 <= rain <= 3000):
            raise weather.WeatherError(INVALID)
        rows.append({"date": day, "low_c": low, "high_c": high, "precipitation_mm": rain})
    if len(rows) < count:
        raise IncompleteArchive(start + timedelta(days=len(rows)))
    return rows


def _years(now: float) -> list[int]:
    year = (datetime.fromtimestamp(now, UTC) - timedelta(days=ARCHIVE_GRACE_DAYS)).year
    return list(range(year - YEARS, year))


def _summarize(rows: list[dict], years: list[int]) -> dict:
    counts = dict.fromkeys(BANDS, 0)
    wet = dict.fromkeys(BANDS, 0)
    for row in rows:
        temp = row["low_c"] + DESIGN_FRACTION * (row["high_c"] - row["low_c"])
        band = "cold" if temp <= COLD_C else "cool" if temp < MILD_C else "mild" if temp < HOT_C else "hot"
        counts[band] += 1
        wet[band] += row["precipitation_mm"] >= WET_MM
    return {"years": years, "shares": {
        band: {"share": counts[band] / len(rows),
               "wet_share": wet[band] / counts[band] if counts[band] else 0.0}
        for band in BANDS
    }}


def _answer(kept: dict | None, now: float) -> dict | None:
    """Do not trust damaged settings as if they were measured percentages."""
    if not kept or not _finite(kept.get("fetched")) or kept["fetched"] > now:
        return None
    answer = kept.get("answer")
    if not isinstance(answer, dict):
        return None
    years, shares = answer.get("years"), answer.get("shares")
    if (not isinstance(years, list) or len(years) != YEARS
            or any(type(year) is not int for year in years)
            or years != list(range(years[0], years[0] + YEARS))
            or years[0] < 1940 or years[-1] >= datetime.fromtimestamp(now, UTC).year
            or not isinstance(shares, dict) or set(shares) != set(BANDS)):
        return None
    for values in shares.values():
        if not isinstance(values, dict) or any(
            not _finite(values.get(k)) or not 0 <= values[k] <= 1 for k in ("share", "wet_share")
        ):
            return None
        if values["share"] == 0 and values["wet_share"] != 0:
            return None
    if not math.isclose(sum(values["share"] for values in shares.values()), 1, abs_tol=1e-9):
        return None
    return answer


def _result(place: dict | None, answer: dict | None = None, *, old: bool = False, message: str | None = None) -> dict:
    return {"used": answer is not None, "place": place["name"] if place else None,
            "shares": answer["shares"] if answer else None, "years": answer["years"] if answer else [],
            "old": old, "message": message}


def _cached_result(place: dict, kept: dict | None, now: float, years: list[int]) -> dict:
    answer = _answer(kept, now)
    incomplete = bool(kept and type(kept.get("incomplete_year")) is int)
    pending = bool(answer and incomplete and kept["incomplete_year"] == years[-1]
                  and answer["years"] == [year - 1 for year in years])
    old = bool(answer and not pending and (answer["years"] != years or now - kept["fetched"] >= KEEP_S))
    message = None
    if old:
        message = OLD_INCOMPLETE if incomplete else OLD
    elif not answer:
        message = INCOMPLETE if incomplete else UNAVAILABLE
    return _result(place, answer, old=old, message=message)


def lookup(state: State) -> dict:
    """Home climate context; fractions are 0–1, wet_share is within its band.

    A zero-frequency band has wet_share 0 and contributes nothing. Failures
    preserve a valid same-place answer, clearly marked old, or give no shares.
    When only the newest year is incomplete, the preceding four full years
    remain usable without a warning; connection failures are not suppressed.
    Settings changes and retry reservations are checked under State's lock;
    no network call holds that lock.
    """
    place = state.get("place")
    if not place:
        return _result(None, message=NO_PLACE)
    now = weather._now()
    years = _years(now)
    key = weather._key(place)

    def reserve(data):
        if data.get("place") != place:
            return None, False
        kept = data.get("climate")
        kept = kept if isinstance(kept, dict) and kept.get("key") == key else None
        answer = _answer(kept, now)
        if answer and answer["years"] == years and now - kept["fetched"] < KEEP_S:
            return kept, False
        if kept and _finite(kept.get("attempted")) and 0 <= now - kept["attempted"] < RETRY_S:
            return kept, False
        kept = {**(kept or {}), "key": key, "attempted": now, "incomplete_year": None}
        data["climate"] = kept
        return kept, True

    kept, refresh = state.mutate(reserve, save_if_changed=True)
    if not refresh:
        current = state.get("place")
        if current != place:
            return _result(current, message=UNAVAILABLE if current else NO_PLACE)
        return _cached_result(place, kept, now, years)

    def store(data):
        current = data.get("climate")
        if (data.get("place") == place and isinstance(current, dict)
                and current.get("key") == key and current.get("attempted") == now):
            data["climate"] = kept

    try:
        rows = archive(place, date(years[0], 1, 1), date(years[-1], 12, 31))
        answer = _summarize(rows, years)
    except weather.WeatherError as error:
        if isinstance(error, IncompleteArchive):
            kept = {**kept, "incomplete_year": error.missing_from.year}
            state.mutate(store, save_if_changed=True)
        result = _cached_result(place, kept, now, years)
    else:
        kept = {**kept, "fetched": weather._now(), "answer": answer, "attempted": None}

        state.mutate(store, save_if_changed=True)
        result = _result(place, answer)
    current = state.get("place")
    if current != place:
        return _result(current, message=UNAVAILABLE if current else NO_PLACE)
    return result
