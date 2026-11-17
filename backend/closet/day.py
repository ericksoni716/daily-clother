"""The day as it is dressed for, read from the forecast hour by hour.

Pure: no network, no clock, no settings. `read(hours, outside, now_hour)` takes the day's hours as
`weather._hours` gives them and says what matters for getting dressed in the hours the owner is out: what it feels
like at its coldest and warmest (wind and humidity counted, as the weather service does), when rain falls and how
hard, the wind, the sun and the humidity, each in a few plain words as well as numbers.

Which hours: the ones the owner said they are outside (`outside`, from the day in their words), otherwise the waking
day, 7:00 to 22:00. Hours already gone are left out, so at three in the afternoon the morning's frost and the
shower at ten no longer count; once the hours are all gone, they are all read again (there is nothing else to go by).

The outfit engine is given the feels-like low and high and whether it rains in those hours, in place of the whole
day's low, high and chance of rain. The rest is shown on Today and kept for the stylist (BACKLOG, "Outfits chosen
by Claude").
"""
from __future__ import annotations

WAKING = (7, 22)             # the hours dressed for when the owner has not said when they are out: 7:00 to 22:00
WET_CHANCE = 50              # an hour with at least this chance of rain (%) is a wet hour (as weather.RAIN_CHANCE)
WET_MM = 0.2                 # with no chance given, an hour with at least this much rain (mm) is one
LIGHT_MM, HEAVY_MM = 1.0, 4.0   # the wettest hour: under LIGHT_MM is light rain, HEAVY_MM or more is heavy
MOST_OF_IT = 0.8             # rain in at least this share of the hours is "most of the day"
BREEZY_KMH, WINDY_KMH, VERY_WINDY_KMH = 20, 35, 50   # the strongest steady wind
GUSTY_KMH = 60               # gusts this strong are said on a day that is not already "very windy"
STRONG_UV, VERY_STRONG_UV = 6, 8
HUMID_FEELS_C, HUMID_PERCENT = 24, 70   # humid: it feels at least this warm with the air at least this damp
FEELS_APART_C = 2.0          # "feels like" is said when it is this far from the thermometer at either end
SNOW, STORMS = "snow", "storms"


def hour_words(hour: int) -> str:
    """7 -> "7am", 12 -> "noon", 15 -> "3pm", 0 or 24 -> "midnight"."""
    hour %= 24
    if hour == 0:
        return "midnight"
    if hour == 12:
        return "noon"
    return f"{hour}am" if hour < 12 else f"{hour - 12}pm"


def span_words(start: int, end: int) -> str:
    """Hours from `start` up to `end` (not including it), as "2pm to 5pm"; one hour as "around 2pm"."""
    return f"around {hour_words(start)}" if end - start <= 1 else f"{hour_words(start)} to {hour_words(end)}"


def window(outside: tuple[int, int] | None, now_hour: int | None) -> tuple[int, int]:
    """The hours read, as (first hour, the hour after the last): the owner's hours outside or the waking day, less
    the hours already gone."""
    start, end = outside if outside and 0 <= outside[0] < outside[1] <= 24 else WAKING
    if now_hour is not None and start < now_hour < end:
        start = now_hour
    return start, end


def _most(values: list) -> float | None:
    known = [v for v in values if v is not None]
    return max(known) if known else None


def _wet(h: dict) -> bool:
    if h.get("rain_chance") is not None:
        return h["rain_chance"] >= WET_CHANCE
    return (h.get("rain_mm") or 0) >= WET_MM


def _rain(hours: list[dict]) -> dict | None:
    wet = [h for h in hours if _wet(h)]
    if not wet:
        return None
    first, last = wet[0]["hour"], wet[-1]["hour"] + 1
    peak = _most([h.get("rain_mm") for h in wet])
    kinds = {h.get("summary") for h in wet}
    kind = STORMS if STORMS in kinds else SNOW if SNOW in kinds else "rain"
    if kind == "rain" and peak is not None:
        kind = "light rain" if peak < LIGHT_MM else "heavy rain" if peak >= HEAVY_MM else "rain"
    most = len(wet) >= MOST_OF_IT * len(hours)
    spells: list[list[int]] = []   # the wet hours in unbroken runs, each as [first hour, the hour after its last]
    for h in wet:
        if spells and spells[-1][1] == h["hour"]:
            spells[-1][1] = h["hour"] + 1
        else:
            spells.append([h["hour"], h["hour"] + 1])
    if most and len(hours) > 2:
        words = f"{kind} most of the time"
    elif len(spells) <= 2:
        words = f"{kind} {' and '.join(span_words(a, b) for a, b in spells)}"
    else:
        words = f"{kind} on and off, {hour_words(first)} to {hour_words(last)}"
    total = [h["rain_mm"] for h in wet if h.get("rain_mm") is not None]
    return {"kind": kind, "from_hour": first, "to_hour": last, "chance": _most([h.get("rain_chance") for h in wet]),
            "mm": round(sum(total), 1) if total else None, "most": most, "words": words}


def _wind(hours: list[dict]) -> dict | None:
    steady, gust = _most([h.get("wind_kmh") for h in hours]), _most([h.get("gust_kmh") for h in hours])
    if steady is None and gust is None:
        return None
    s = steady or 0
    words = ("very windy" if s >= VERY_WINDY_KMH else "windy" if s >= WINDY_KMH else "breezy" if s >= BREEZY_KMH
             else None)
    if gust is not None and gust >= GUSTY_KMH and words != "very windy":
        words = "strong gusts" if words is None else f"{words}, strong gusts"
    return {"kmh": steady, "gust_kmh": gust, "words": words}


def read(hours: list[dict], outside: tuple[int, int] | None = None, now_hour: int | None = None) -> dict | None:
    """What the hours the owner is out are like, or None when the forecast has none of them.

    {from_hour, to_hour, temp_low_c, temp_high_c, feels_low_c, feels_high_c, feels_apart, rain, wind, uv, humid,
    wet, words}: `feels_apart` says whether it feels far enough from the thermometer to say so; `rain` is {kind, from_hour, to_hour, chance, mm, most, words} or None; `wind` is {kmh, gust_kmh, words} or None;
    `uv` the highest UV index; `humid` whether it is warm and damp; `wet` whether it rains at all in those hours (what
    the outfit engine is told); `words` is the day in short plain parts, for example ["feels like 0° to 7°",
    "rain 2pm to 5pm", "windy"], with the temperatures first.
    """
    start, end = window(outside, now_hour)
    mine = [h for h in hours if start <= h["hour"] < end]
    if not mine and now_hour is not None:   # every hour asked for is gone: read them all the same
        start, end = window(outside, None)
        mine = [h for h in hours if start <= h["hour"] < end]
    if not mine:
        return None
    temps, feels = [h["temp_c"] for h in mine], [h["feels_c"] for h in mine]
    low, high, feels_low, feels_high = min(temps), max(temps), min(feels), max(feels)
    rain, wind, uv = _rain(mine), _wind(mine), _most([h.get("uv") for h in mine])
    warmest = max(mine, key=lambda h: h["feels_c"])
    humid = feels_high >= HUMID_FEELS_C and (warmest.get("humidity") or 0) >= HUMID_PERCENT

    def deg(v: float) -> str:
        return f"{round(v)}°"
    apart = abs(feels_low - low) >= FEELS_APART_C or abs(feels_high - high) >= FEELS_APART_C
    def span(a: float, b: float) -> str:
        return f"about {deg(b)}" if round(a) == round(b) else f"{deg(a)} to {deg(b)}"
    words = [f"feels like {span(feels_low, feels_high)}" if apart else span(low, high)]
    if rain:
        words.append(rain["words"])
    if wind and wind["words"]:
        words.append(wind["words"])
    if humid:
        words.append("humid")
    if uv is not None and uv >= STRONG_UV:
        words.append("very strong sun" if uv >= VERY_STRONG_UV else "strong sun")
    return {"from_hour": start, "to_hour": end, "temp_low_c": low, "temp_high_c": high,
            "feels_low_c": feels_low, "feels_high_c": feels_high, "feels_apart": apart, "rain": rain, "wind": wind, "uv": uv,
            "humid": humid, "wet": rain is not None, "words": words}
