"""The day in the owner's words: a note that today, or the days ahead, are not an ordinary day at home.

The owner types a sentence on Today ("In Lisbon until Friday", "at a match today, outside from noon to six").
Claude reads it (`tagger/dayread.py`), Nines finds the place on the map (the same search as the place in
Settings), and the note is kept in the program's settings (`day_note`), not in a closet: like the place, it is about
where the owner is. One note at a time; a new one replaces it, and it stops counting by itself after its last day.

While a note holds, Today dresses for its place's weather instead of home's, reads the forecast for the hours
it says the owner is outside (`closet/day.py`), and offers its occasion. Home stays the saved place throughout.

A day dressed ahead (Dress for another day, `closet/plans.py`) takes a word of its own the same way ("dinner at
eight"), read with that day as the day it is about and kept beside the note, by date (`day_notes`). On that day it
is the day's note; a day's own word wins over the note for several days that also holds it. Past days' words go.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from . import day as dayparts
from . import weather
from .state import State
from .tagger import dayread

MAX_TEXT = dayread.MAX_TEXT
EXAMPLES = "For example: “In Lisbon until Friday”, or “At a match today, outside from noon to six”."
NOTHING_READ = f"Nines couldn't find anything about your day in that. {EXAMPLES}"


def check_text(text: object) -> str:
    """The owner's sentence, tidied, or ValueError with a sentence."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"Say something about your day. {EXAMPLES}")
    tidy = " ".join(text.split())
    if len(tidy) > MAX_TEXT:
        raise ValueError(f"Keep it to {MAX_TEXT} characters or fewer.")
    return tidy


def _find(name: str, find_place) -> list[dict]:
    """The places on the map for a name as Claude gave it ("Charleston, United States"). The search takes a town
    with its region or country most of the time; when it finds nothing that way (or cannot answer), the town alone
    is searched and the places whose names carry the rest ("united states") come first."""
    town, _, rest = name.partition(",")
    try:
        found = find_place(name)
    except weather.WeatherError:
        if not rest.strip():
            raise
        found = []
    if found or not rest.strip():
        return found
    hints = [h.strip().lower() for h in rest.split(",") if h.strip()]
    found = find_place(town.strip())
    return [p for p in found if all(h in p["name"].lower() for h in hints)] or found


def make(text: str, reading: dict, today: date, find_place=weather.search_places) -> tuple[dict, str | None]:
    """The note to keep for a reading, and a sentence for the owner when its place could not be found (the note is
    kept without one, so its hours and occasion still count)."""
    first = today + timedelta(days=reading["starts_in_days"])
    last = first + timedelta(days=reading["days"] - 1)
    place, message = None, None
    if reading["place"]:
        try:
            found = _find(reading["place"], find_place)
        except weather.WeatherError as e:
            found, message = [], f"{e} The weather is still home's: save the note again in a moment."
        if found:
            place = found[0]
        elif message is None:
            message = (f"Nines couldn't find “{reading['place']}” on the map, so the weather is still home's. "
                       "Try the name of the town or city.")
    note = {"text": text, "from": first.isoformat(), "to": last.isoformat(), "place": place,
            "place_asked": reading["place"], "outside": list(reading["outside"]) if reading["outside"] else None,
            "exposure": reading["exposure"], "activity": reading["activity"], "occasion": reading["occasion"]}
    return note, message


def _dates(note: dict) -> tuple[date, date] | None:
    try:
        first, last = date.fromisoformat(note["from"]), date.fromisoformat(note["to"])
    except (KeyError, TypeError, ValueError):
        return None
    return (first, last) if first <= last else None


def current(state: State, today: date) -> dict | None:
    """The note kept, unless its last day has passed (or it cannot be read)."""
    note = state.get("day_note")
    dates = _dates(note) if isinstance(note, dict) else None
    return note if dates and dates[1] >= today else None


def _valid(note: object, on: date) -> dict | None:
    dates = _dates(note) if isinstance(note, dict) else None
    return note if dates and dates[0] <= on <= dates[1] else None   # type: ignore[return-value]


def dated(state: State, day: date) -> dict | None:
    """The word kept for one day dressed ahead, if there is one and it holds that day."""
    notes = state.get("day_notes")
    return _valid(notes.get(day.isoformat()), day) if isinstance(notes, dict) else None


def for_day(state: State, day: date) -> dict | None:
    """What is said about a day: its own word, else the note when it holds that day (a note for days ahead may)."""
    return dated(state, day) or _valid(state.get("day_note"), day)


def shown(state: State, today: date) -> dict | None:
    """The note Today shows and changes: today's own word, written ahead, else the note kept (which may be ahead)."""
    return dated(state, today) or current(state, today)


def save_for(state: State, day: date, note: dict, today: date) -> None:
    """Keeps the word about a day ahead, dropping those of days gone by."""
    def change(data: dict) -> None:
        kept = data.get("day_notes") if isinstance(data.get("day_notes"), dict) else {}
        kept = {k: v for k, v in kept.items() if k >= today.isoformat()}
        kept[day.isoformat()] = {**note, "saved_at": datetime.now().isoformat(timespec="seconds")}
        data["day_notes"] = kept
    state.mutate(change)


def clear_for(state: State, day: date) -> None:
    def change(data: dict) -> None:
        kept = dict(data.get("day_notes") or {}) if isinstance(data.get("day_notes"), dict) else {}
        kept.pop(day.isoformat(), None)
        data["day_notes"] = kept or None
    state.mutate(change)


def active(note: dict | None, today: date) -> bool:
    """Whether the note counts today (it may be for days still ahead)."""
    dates = _dates(note) if note else None
    return bool(dates and dates[0] <= today <= dates[1])


def outside(note: dict | None) -> tuple[int, int] | None:
    hours = note.get("outside") if note else None
    if isinstance(hours, list) and len(hours) == 2 and all(isinstance(h, int) and not isinstance(h, bool) for h in hours):
        return (hours[0], hours[1]) if 0 <= hours[0] < hours[1] <= 24 else None
    return None


def _day_words(d: date) -> str:
    return f"{d.strftime('%A')} {d.day} {d.strftime('%B')}"


def words(note: dict, today: date, ahead: bool = False) -> list[str]:
    """What Nines took from the note, in short plain parts: where, when, the hours outside, what for. `ahead`: said
    for a day dressed ahead (`today` is that day), which is not "today"."""
    first, last = _dates(note) or (today, today)
    parts = []
    if note.get("place"):
        parts.append(note["place"]["name"])
    if first > today:
        parts.append(f"from {_day_words(first)}" + (f" to {_day_words(last)}" if last > first else ""))
    elif last > today:
        parts.append(f"until {_day_words(last)}")
    elif not ahead:
        parts.append("today")
    hours = outside(note)
    if hours:
        parts.append(f"outside {dayparts.span_words(*hours)}")
    elif note.get("exposure") == "outside":
        parts.append("outside most of the day")
    elif note.get("exposure") == "inside":
        parts.append("indoors most of the day")
    if note.get("activity"):
        parts.append(note["activity"])
    return parts


def describe(note: dict | None, today: date, ahead: bool = False) -> dict | None:
    """The note as the page is given it (`ahead`: for a day dressed ahead, `today` being that day)."""
    if not note:
        return None
    return {"text": note.get("text") or "", "from": note["from"], "to": note["to"], "active": active(note, today),
            "place": note.get("place"), "place_asked": note.get("place_asked"), "outside": note.get("outside"),
            "exposure": note.get("exposure") or "mixed", "activity": note.get("activity") or "",
            "occasion": note.get("occasion"), "words": words(note, today, ahead)}


def save(state: State, note: dict, today: date | None = None) -> None:
    """Keeps the note about today or the days ahead; a word written ahead for today gives way to it."""
    state.update(day_note={**note, "saved_at": datetime.now().isoformat(timespec="seconds")}, weather_away=None)
    if today is not None and dated(state, today):
        clear_for(state, today)


def clear(state: State, today: date | None = None) -> None:
    """Back to an ordinary day: today's own word, written ahead, goes first; otherwise the note."""
    if today is not None and dated(state, today):
        clear_for(state, today)
        state.update(weather_away=None)
        return
    state.update(day_note=None, weather_away=None)
