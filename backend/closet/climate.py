"""The weather where the owner lives, over a year: what share of days fall in each of the gap analysis's
temperature bands, and what share of those are wet.

Worked out from the last CLIMATE_YEARS full years of daily lows, highs and rain at the saved place, from
Open-Meteo's historical archive (no key needed). Only the place's coordinates are sent. A climate does not
change by the week, so the answer is kept in the settings for KEEP_DAYS and reused; when the archive cannot be
reached it is not asked again for RETRY_S, and the analysis counts every band the same, as it did before.
The demo closet uses a built-in example (DEMO_CLIMATE), so its results never depend on the network.
"""
from __future__ import annotations

from datetime import UTC, date, datetime

from . import gaps, outfits, weather
from .state import State

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
CLIMATE_YEARS = 5            # the last this many full years
MIN_DAYS = 300               # fewer usable days than this in the answer and it is not used
KEEP_DAYS = 120              # a climate is reused for this long
ARCHIVE_TIMEOUT_S = 15      # the archive answers years of days, slower than a forecast: give up after this long
RETRY_S = 3600               # after the archive could not be reached, it is not asked again for this long
WET_DAY_MM = 1.0             # a day with at least this much rain or snow (water, mm) counts as wet


def band_edges() -> tuple[float, ...]:
    """Where one band ends and the next begins, in °C of the temperature dressed for (the low plus
    DESIGN_TEMP_SHARE of the way to the high, as the engine dresses): halfway between the grid's days."""
    design = [lo + outfits.DESIGN_TEMP_SHARE * (hi - lo) for _, lo, hi in gaps.TEMP_BANDS]
    return tuple((a + b) / 2 for a, b in zip(design, design[1:], strict=False))


def band_of(low: float, high: float) -> str:
    t = low + outfits.DESIGN_TEMP_SHARE * (high - low)
    names = [b for b, _, _ in gaps.TEMP_BANDS]
    for name, edge in zip(names, band_edges(), strict=False):
        if t < edge:
            return name
    return names[-1]


def _example(shares: dict[str, tuple[float, float]]) -> dict:
    return {"bands": {b: {"share": s, "wet": w} for b, (s, w) in shares.items()}, "years": None, "days": None,
            "source": "example"}


# The demo closet's built-in climate: a temperate city with cold, wet winters and warm summers.
DEMO_CLIMATE = _example({"cold": (0.22, 0.35), "cool": (0.28, 0.35), "mild": (0.30, 0.30), "hot": (0.20, 0.20)})


def _number(v: object) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


def shares(daily: object) -> dict:
    """The climate from the archive's `daily` block, or WeatherError when it cannot be used."""
    try:
        lows, highs = daily["temperature_2m_min"], daily["temperature_2m_max"]
        rain = daily.get("precipitation_sum") or [None] * len(lows)
        days = daily["time"]
        if not (len(lows) == len(highs) == len(rain) == len(days)):
            raise TypeError
    except (KeyError, TypeError, AttributeError):
        raise weather.WeatherError("The weather service gave an answer Closet could not read.") from None
    counts = {b: [0, 0] for b, _, _ in gaps.TEMP_BANDS}
    total = 0
    for lo, hi, mm in zip(lows, highs, rain, strict=False):
        if not (_number(lo) and _number(hi)) or lo > hi:
            continue
        band = band_of(float(lo), float(hi))
        counts[band][0] += 1
        counts[band][1] += 1 if _number(mm) and mm >= WET_DAY_MM else 0
        total += 1
    if total < MIN_DAYS:
        raise weather.WeatherError("The weather service had too few days for this place to say what its weather is like.")
    bands = {b: {"share": round(n / total, 4), "wet": round(w / n, 4) if n else 0.0} for b, (n, w) in counts.items()}
    first, last = str(days[0])[:4], str(days[-1])[:4]
    return {"bands": bands, "years": [int(first), int(last)] if first.isdigit() and last.isdigit() else None,
            "days": total, "source": "archive"}


def _years() -> tuple[str, str]:
    this_year = datetime.fromtimestamp(weather._now(), UTC).year
    return date(this_year - CLIMATE_YEARS, 1, 1).isoformat(), date(this_year - 1, 12, 31).isoformat()


def _ask(place: dict) -> dict:
    start, end = _years()
    data = weather._get(ARCHIVE_URL, {
        "latitude": place["latitude"], "longitude": place["longitude"], "start_date": start, "end_date": end,
        "daily": "temperature_2m_min,temperature_2m_max,precipitation_sum", "temperature_unit": "celsius"}, timeout=ARCHIVE_TIMEOUT_S)
    return shares(data.get("daily"))


def key(place: dict) -> str:
    return f"{place['latitude']},{place['longitude']}"


def lookup(state: State) -> dict:
    """The climate where the owner lives, for the gap analysis.

    Returns {place, climate, message}: `climate` is {bands: {band: {share, wet}}, years, days, source} or None
    (the bands then count the same); `message` says in plain words why it is not used, or None.
    """
    place = state.get("place")
    if not place:
        return {"place": None, "climate": None,
                "message": "The weather where you live is not being used: choose where you live in Settings."}
    k, kept = key(place), state.get("climate")
    kept = kept if isinstance(kept, dict) and kept.get("key") == k else None
    now = weather._now()
    if kept and kept.get("answer") and now - kept.get("fetched", 0) < KEEP_DAYS * 86400:
        return {"place": place, "climate": kept["answer"], "message": None}
    if kept and kept.get("failed_at") and now - kept["failed_at"] < RETRY_S:
        return _failed(place, kept)
    try:
        answer = _ask(place)
    except weather.WeatherError as e:
        failed = {"key": k, "fetched": (kept or {}).get("fetched"), "answer": (kept or {}).get("answer"),
                  "failed_at": now, "message": str(e)}
        if state.get("place") == place:
            state.update(climate=failed)
        return _failed(place, failed)
    if state.get("place") == place:  # the place may have been changed while the archive was asked
        state.update(climate={"key": k, "fetched": now, "answer": answer})
    return {"place": place, "climate": answer, "message": None}


def _failed(place: dict, kept: dict) -> dict:
    if kept.get("answer"):  # an older answer for the same place: a climate does not go stale quickly
        return {"place": place, "climate": kept["answer"], "message": None}
    return {"place": place, "climate": None,
            "message": f"{kept.get('message') or 'The weather service could not be reached.'} The weather where you live "
                       "is not being used yet; Closet will try again later."}
