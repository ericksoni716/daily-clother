"""How the owner lives: the situations his weeks are made of, as he answered a few questions.

The answers are kept in the program's settings (`state.py`), like the place, one set per closet: the real
closet's are the owner's; the demo closet starts from a built-in example (DEMO_ANSWERS), so the owner's own
answers never change it and its results stay the same from run to run. Answers tried out in the demo are
kept apart from the owner's, and "forget" takes the demo back to the example.

Until the owner answers, the gap analysis behaves exactly as it did before (`gaps.OCCASION_WEIGHT`). Once he
has, each situation is turned into what the engine understands (SITUATIONS: an occasion, a mood, which weather,
which pieces count) and weighed by how often it happens.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Request, Response

from .state import State

# ------------------------------------------------------------------ the answers
# How often, as the questions offer it, stored as days a week. Other numbers from 0 to 7 are accepted too.
FREQUENCY = {"never": 0.0, "now_and_then": 0.5, "weekly": 1.0, "most_days": 5.0}
MAX_DAYS = 7.0
DAYS_STEP = 0.5               # days a week are kept to the nearest half day
# How people dress at work, in the owner's words, to the engine's occasion.
WORK_DRESS = {"casual": "casual", "smart_casual": "smart_casual", "business": "business", "formal": "formal"}
DRESS_WORDS = {"casual": "casual", "smart_casual": "smart casual", "business": "business", "formal": "formal"}
# Where the owner goes on holiday.
VACATION_WHERE = ("warm", "cold", "both")
WHERE_WORDS = {"warm": "warm places", "cold": "cold places", "both": "warm and cold places"}
MAX_WEEKS = 26                # weeks of holiday a year
STYLE_MAX = 200               # "My style in a few words"


@dataclass(frozen=True)
class Use:
    """One kind of day a situation is dressed for, as the outfit engine is asked for it."""
    occasion: str
    mood: str
    share: float              # of the situation's days
    noun: str | None = None   # what these days are called, when not the situation's days_noun


@dataclass(frozen=True)
class Situation:
    key: str
    words: str                # "work", "going out"
    days_noun: str            # what its days are called, taking weather words in front: "cold rainy work days"
    uses: tuple[Use, ...]     # for work, set by how people dress there (`uses`)
    weather: str              # "home" (the climate where he lives), "trip" (the vacation answer) or "indoors"
    why: str


# The situations, in the order the questions ask them, each with a line of reason.
SITUATIONS = (
    Situation("work", "work", "work days", (Use("smart_casual", "usual", 1.0),), "home",
              "Dressed as people dress there (the answer to the second question); the way there is in the weather here."),
    Situation("everyday", "everyday", "days out and about", (Use("casual", "usual", 1.0),), "home",
              "Errands and seeing friends: the plain casual day the engine already knows, in the weather here."),
    Situation("going_out", "going out", "evenings out",
              (Use("smart_casual", "sharp", 0.8), Use("formal", "usual", 0.2, "occasions")), "home",
              "Dinner out is smart casual, a little sharper than usual; about one time in five it is an occasion "
              "(a wedding, a party) that is formal."),
    Situation("lounging", "lounging at home", "days lounging at home", (), "indoors",
              "At home there is no weather, no shoes and no coat, so the engine is not asked: what counts is having "
              "the most relaxed pieces (a hoodie or soft top, soft trousers), told apart by category and material words."),
    Situation("exercise", "exercise", "exercise days", (Use("athletic", "usual", 1.0),), "home",
              "The engine's sport occasion, in the weather here (it cannot tell a run outside from the gym)."),
    Situation("vacation", "vacation", "vacation days", (Use("casual", "usual", 0.7), Use("smart_casual", "usual", 0.3)),
              "trip", "Casual days and smart casual evenings, in the weather of the places he goes (warm, cold or both), "
              "not the weather here."),
)
SITUATION_KEYS = tuple(s.key for s in SITUATIONS)
BY_KEY = {s.key: s for s in SITUATIONS}

# The demo closet's example life: an office worker in a temperate city.
DEMO_ANSWERS = {
    "work": {"days": 4.0, "dress": "business"},
    "everyday": {"days": 2.0},
    "going_out": {"days": 1.0},
    "lounging": {"days": 5.0},
    "exercise": {"days": 0.5},
    "vacation": {"weeks": 2, "where": "warm"},
    "style": "Classic at work, relaxed at home; navy, white and denim",
}


def uses(situation: Situation, answer: dict) -> tuple[Use, ...]:
    """The kinds of day a situation is dressed for, with the owner's answer (work's dress)."""
    if situation.key == "work":
        return (Use(WORK_DRESS[answer.get("dress") or "smart_casual"], "usual", 1.0),)
    return situation.uses


def days_a_week(key: str, answer: dict) -> float:
    """How many days a week a situation happens (vacation: its weeks a year, spread over the year)."""
    if key == "vacation":
        return float(answer.get("weeks") or 0) * 7 / 52
    return float(answer.get("days") or 0)


def often_words(key: str, answer: dict) -> str:
    """How often, in words: "4 days a week", "about once a week", "now and then", "2 weeks a year"."""
    if key == "vacation":
        weeks = answer.get("weeks") or 0
        return f"{_num(weeks)} week{'' if weeks == 1 else 's'} a year"
    d = float(answer.get("days") or 0)
    if d <= 0:
        return "never"
    if d < 1:
        return "now and then"
    if d == 1:
        return "about once a week"
    if d >= 5:
        return "most days"
    return f"{_num(d)} days a week"


def _num(n: float) -> str:
    return str(int(n)) if float(n).is_integer() else f"{n:g}"


def summary(answers: dict | None) -> list[dict]:
    """The situations the owner has, in order: [{key, words, often, days, detail}]; detail is work's dress or vacation's places."""
    if not answers:
        return []
    out = []
    for s in SITUATIONS:
        a = answers.get(s.key) or {}
        d = days_a_week(s.key, a)
        if d <= 0:
            continue
        detail = None
        if s.key == "work":
            detail = DRESS_WORDS[a.get("dress") or "smart_casual"]
        elif s.key == "vacation":
            detail = WHERE_WORDS[a.get("where") or "both"]
        out.append({"key": s.key, "words": s.words, "often": often_words(s.key, a), "days": round(d, 2), "detail": detail})
    return out


# ------------------------------------------------------------------ checking
def check(raw: object) -> dict:
    """The answers as they are kept, or ValueError with a sentence the owner can read."""
    if not isinstance(raw, dict):
        raise ValueError("Send the answers as an object, one entry per situation.")
    unknown = sorted(set(raw) - set(SITUATION_KEYS) - {"style"})
    if unknown:
        raise ValueError(f"These are not situations Closet asks about: {', '.join(unknown)}.")
    out: dict = {}
    for s in SITUATIONS:
        a = raw.get(s.key)
        if a is None:
            a = {}
        if not isinstance(a, dict):
            raise ValueError(f"The answer for {s.words} must be an object.")
        if s.key == "vacation":
            extra = sorted(set(a) - {"weeks", "where"})
            if extra:
                raise ValueError(f"Vacation is asked only how many weeks a year and where, not {', '.join(extra)}.")
            weeks = a.get("weeks", 0)
            if isinstance(weeks, bool) or not isinstance(weeks, int | float) or not math.isfinite(weeks) \
                    or not 0 <= weeks <= MAX_WEEKS or not float(weeks).is_integer():
                raise ValueError(f"Weeks of vacation a year must be a whole number from 0 to {MAX_WEEKS}.")
            where = a.get("where") or "both"
            if where not in VACATION_WHERE:
                raise ValueError("Say where you go on vacation: warm places, cold places or both.")
            out[s.key] = {"weeks": int(weeks), "where": where}
            continue
        allowed = {"days", "dress"} if s.key == "work" else {"days"}
        extra = sorted(set(a) - allowed)
        if extra:
            raise ValueError(f"For {s.words} only how often is asked{', and how people dress there' if s.key == 'work' else ''}.")
        days = a.get("days", 0)
        if isinstance(days, str) and days in FREQUENCY:
            days = FREQUENCY[days]
        if isinstance(days, bool) or not isinstance(days, int | float) or not math.isfinite(days) or not 0 <= days <= MAX_DAYS:
            raise ValueError(f"How often for {s.words} must be never, now and then, about weekly, most days, "
                             f"or a number of days a week from 0 to {MAX_DAYS:g}.")
        entry: dict = {"days": round(float(days) / DAYS_STEP) * DAYS_STEP}
        if s.key == "work":
            dress = a.get("dress") or "smart_casual"
            if dress not in WORK_DRESS:
                raise ValueError("Say how people dress at work: casual, smart casual, business or formal.")
            entry["dress"] = dress
        out[s.key] = entry
    style = raw.get("style")
    if style is not None and not isinstance(style, str):
        raise ValueError("Your style in a few words must be text.")
    style = " ".join((style or "").split())
    if len(style) > STYLE_MAX:
        raise ValueError(f"Your style in a few words is too long: at most {STYLE_MAX} characters.")
    out["style"] = style
    return out


# ------------------------------------------------------------------ kept in the settings
def _entry(state: State, profile: str) -> dict:
    kept = state.get("life") or {}
    entry = kept.get(profile) if isinstance(kept, dict) else None
    return entry if isinstance(entry, dict) else {}


def answers_for(state: State, profile: str) -> tuple[dict | None, bool]:
    """(the answers the analysis is told, whether they are the demo's built-in example). None: not answered yet."""
    kept = _entry(state, profile).get("answers")
    if isinstance(kept, dict):
        try:
            return check(kept), False
        except ValueError:
            pass
    if profile == "demo":
        return dict(DEMO_ANSWERS), True
    return None, False


def _set(state: State, profile: str, **changes) -> None:
    def fn(data: dict) -> None:
        kept = data.get("life") if isinstance(data.get("life"), dict) else {}
        kept = dict(kept)
        kept[profile] = {**(kept.get(profile) if isinstance(kept.get(profile), dict) else {}), **changes}
        data["life"] = kept
    state.mutate(fn)


def view(state: State, profile: str) -> dict:
    """What the questions screen shows: {answers, example, answered, not_now, situations}."""
    answers, example = answers_for(state, profile)
    return {"answers": answers, "example": example, "answered": answers is not None and not example,
            "not_now": bool(_entry(state, profile).get("not_now")), "situations": summary(answers)}


def asking(state: State, profile: str) -> bool:
    """Whether the gaps screen offers the questions: not answered yet, no example, and not put off with "Not now"."""
    answers, _ = answers_for(state, profile)
    return answers is None and not _entry(state, profile).get("not_now")


# ------------------------------------------------------------------ the routes
def router(state: State, profile: Callable[[], str], protected: list) -> APIRouter:
    r = APIRouter(dependencies=protected)

    @r.get("/api/life")
    def get_life():
        return view(state, profile())

    @r.put("/api/life")
    async def put_life(request: Request):
        try:
            raw = await request.json()
        except ValueError:
            raise HTTPException(422, "The answers could not be read. Try again.")
        try:
            answers = check(raw)
        except ValueError as e:
            raise HTTPException(422, str(e))
        p = profile()
        _set(state, p, answers=answers, not_now=False)
        return view(state, p)

    @r.delete("/api/life", status_code=204)
    def forget_life():
        _set(state, profile(), answers=None)
        return Response(status_code=204)

    @r.post("/api/life/not-now", status_code=204)
    def not_now():
        _set(state, profile(), not_now=True)
        return Response(status_code=204)

    return r
