"""The days the owner actually has. The unanswered gap analysis stays untouched."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from . import gaps, outfits, taste


@dataclass(frozen=True)
class Situation:
    label: str
    occasion: str
    mood: str
    bands: tuple[str, ...]
    pieces: str
    reason: str


ALL_BANDS = tuple(b for b, _, _ in gaps.TEMP_BANDS)
# One mapping of the owner's words to the engine. Work's occasion is replaced by the answer.
SITUATIONS = {
    "work": Situation("Work", "smart_casual", "sharp", ALL_BANDS, "all",
                      "The workplace's dress is the guide; getting dressed for it should not be a compromise."),
    "everyday": Situation("Everyday", "casual", "usual", ALL_BANDS, "all",
                          "Errands and seeing friends use the everyday casual wardrobe."),
    "going_out": Situation("Going out", "smart_casual", "sharp", ALL_BANDS, "all",
                           "Dinner or an occasion is a step up from everyday, not an assumed black-tie event."),
    "lounging": Situation("Lounging at home", "casual", "relaxed", ("mild",), "soft",
                         "Indoors needs relaxed tops and soft bottoms, not a rain coat or outdoor shoes."),
    "exercise": Situation("Exercise", "athletic", "relaxed", ALL_BANDS, "active",
                         "Athletic days need movable clothes; denim and tailored trousers are not sportswear."),
    "vacation": Situation("Vacation", "casual", "relaxed", ALL_BANDS, "all",
                         "Away days use the chosen warm/cold weather, never the weather at home."),
}
FREQUENCIES = (0, 0.25, 1, 4)  # never, now and then, about weekly, most days
WORK_DRESS = ("casual", "smart_casual", "business", "formal")
VACATION_BANDS = {"warm": ("mild", "hot"), "cold": ("cold", "cool"), "both": ALL_BANDS}
SOFT_WORDS = ("jersey", "fleece", "sweat", "jogger", "tracksuit", "lounge", "knit", "stretch")
RELAXED_FITS = ("regular", "relaxed", "oversized")
ACTIVE_TAGS = {None: "active", "light": "light_active", "warm": "warm_active",
               "rain": "rain_active", "rainwarm": "rainwarm_active"}
LOUNGE_CHOICES = 2
LOUNGE_MISSING_SCORE = 40
STYLE_MAX = 200
DAYS_PER_YEAR = 365.25
WEEKS_PER_YEAR = DAYS_PER_YEAR / 7
DEMO_LIFE = {
    "situations": {"work": 4, "everyday": 4, "going_out": 1, "lounging": 4, "exercise": 1, "vacation": 4},
    "work_dress": "business", "vacation_climate": "warm", "vacation_weeks": 2,
    "style_words": "Simple layers, quiet colours",
}
DEMO_CLIMATE = {
    "used": True, "place": "the example city", "years": [], "old": False,
    "shares": {b: {"share": share, "wet_share": 0.3}
               for b, share in zip(ALL_BANDS, (0.25, 0.25, 0.35, 0.15), strict=True)},
    "message": "The demo uses a fixed example of seasons, not your place or answers.",
}


def check(value: object) -> dict | None:
    """Validate the whole short questionnaire, with errors in the owner's words."""
    if value is None:
        return None
    fields = {"situations", "work_dress", "vacation_climate", "vacation_weeks", "style_words"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("Answer the six situations, work dress and vacation questions, with an optional line about your style.")
    frequencies = value["situations"]
    if not isinstance(frequencies, dict) or set(frequencies) != set(SITUATIONS):
        raise ValueError("Give how often you have each of the six situations.")
    for key, days in frequencies.items():
        if isinstance(days, bool) or not isinstance(days, int | float) or not 0 <= days <= 7:
            raise ValueError(f"For {SITUATIONS[key].label.lower()}, give between 0 and 7 days a week.")
    if value["work_dress"] not in WORK_DRESS:
        raise ValueError("For work, choose casual, smart casual, business or formal dress.")
    if not isinstance(value["vacation_climate"], str) or value["vacation_climate"] not in VACATION_BANDS:
        raise ValueError("For vacation, choose warm places, cold places or both.")
    weeks = value["vacation_weeks"]
    if isinstance(weeks, bool) or not isinstance(weeks, int | float) or not 0 <= weeks <= 52:
        raise ValueError("Give between 0 and 52 weeks of vacation a year.")
    words = value["style_words"]
    if not isinstance(words, str) or len(words) > STYLE_MAX or "\n" in words or "\r" in words:
        raise ValueError(f"Keep your style to one line, up to {STYLE_MAX} characters.")
    return {**value, "situations": dict(frequencies), "style_words": words.strip()}


def occasion(key: str, answers: dict) -> str:
    return answers["work_dress"] if key == "work" else SITUATIONS[key].occasion


def frequency(key: str, answers: dict) -> float:
    days = answers["situations"][key]
    return days * answers["vacation_weeks"] / WEEKS_PER_YEAR if key == "vacation" else days


def days_for(key: str, answers: dict, climate: dict) -> list[gaps.Day]:
    situation = SITUATIONS[key]
    freq = frequency(key, answers)
    if not freq:
        return []
    bands = VACATION_BANDS[answers["vacation_climate"]] if key == "vacation" else situation.bands
    out = []
    for band, low, high in gaps.TEMP_BANDS:
        if band not in bands:
            continue
        if key == "lounging":
            out.append(gaps.Day(band, 18, 22, False, "casual", key, freq, 1, situation.mood))
            continue
        shares = climate.get("shares") if key != "vacation" else None
        cell = shares[band] if shares else {"share": 1 / len(bands), "wet_share": 0.5}
        for rain in (False, True):
            share = cell["share"] * (cell["wet_share"] if rain else 1 - cell["wet_share"])
            if share > 0:
                out.append(gaps.Day(band, low, high, rain, occasion(key, answers), key, freq, share, situation.mood))
    return out


def soft(row: dict) -> bool:
    silhouette = row.get("silhouette") or {}
    fit = silhouette.get("fit") if isinstance(silhouette, dict) else None
    words = outfits._words(row.get("name")) + outfits._words(row.get("material"))
    return (fit is None or fit in RELAXED_FITS) and any(stem in word for stem in SOFT_WORDS for word in words)


def eligible(row: dict, key: str) -> bool:
    category = row.get("category")
    if key == "lounging":
        return row.get("formality") in (None, "athletic", "casual") and (
            category in ("tee", "hoodie") or category in ("trousers", "shorts", "sweater") and soft(row))
    if key == "exercise":
        return row.get("formality") in (None, "athletic", "casual") and (
            category in ("tee", "hoodie", "shorts", "sneakers", "jacket", "coat")
            or category == "trousers" and (row.get("formality") == "athletic" or soft(row)))
    return True


def _special_want(want: tuple, place: str, key: str) -> tuple:
    if key == "exercise":
        if want[2] in ACTIVE_TAGS.values():
            return want
        category = {"base": "tee", "mid": "hoodie", "outer": "jacket", "bottom": "trousers", "shoes": "sneakers"}[place]
        if place == "outer" and want[2] in ("warm", "rainwarm"):
            category = "coat"
        return category, "athletic", ACTIVE_TAGS.get(want[2], want[2])
    return want


def _serves(f: gaps._Finding, d: gaps.Day) -> bool:
    category, formality, tag = f.want
    if d.situation == "lounging":
        return False  # its deliberately narrower coverage is found separately
    if d.situation == "exercise":
        return tag in ACTIVE_TAGS.values()
    if tag in ("warm", "rainwarm") and d.band != "cold":
        return False
    if tag in ("rain", "rainwarm") and not d.rain:
        return False
    if (tag == "light" or category == "shorts") and d.band not in ("mild", "hot"):
        return False
    # Do not let the list of universal basics sneak business days back into a casual life.
    if formality in ("business", "formal") and d.occasion not in ("business", "formal"):
        return False
    p = gaps._probe(f.want, None)
    ctx = outfits.Context(d.low_c, d.high_c, d.rain, d.occasion)
    temperature = outfits._design_temp(ctx)
    if temperature >= outfits.HOT_C and f.place in ("mid", "outer"):
        return False
    return not outfits._piece_problem(p, f.place, ctx, temperature)


def _situation_shares(days: list[gaps.Day], answers: dict) -> list[dict]:
    out = []
    for key, spec in SITUATIONS.items():
        matching = set(d for d in days if d.situation == key)
        if not matching:
            continue
        share = sum(d.frequency / 7 * d.weather_share for d in matching)
        out.append({"id": key, "label": spec.label, "days_per_week": answers["situations"][key],
                    "share": round(share, 6), "days_per_year": round(share * DAYS_PER_YEAR, 1)})
    return out


def frequency_words(days: float) -> str:
    if days == 0:
        return "never"
    if days < 1:
        return "now and then"
    if days < 2:
        return "about once a week"
    if days < 4:
        return "a few days a week"
    return "most days" if days < 7 else "every day"


def _when(days: list[gaps.Day], answers: dict, climate: dict) -> str:
    key = days[0].situation
    assert key is not None
    label = SITUATIONS[key].label.lower()
    how_often = frequency_words(answers["situations"][key])
    if key == "vacation":
        weeks = answers["vacation_weeks"]
        how_often += f" during about {max(1, round(weeks))} {'week' if round(weeks) <= 1 else 'weeks'} away a year"
    bands = [b for b in ALL_BANDS if any(d.band == b for d in days)]
    rains = {d.rain for d in days}
    weather = gaps._join(bands, "or") + (" wet" if rains == {True} else " dry" if rains == {False} else "")
    annual = sum(d.weather_share for d in set(days)) * DAYS_PER_YEAR
    if key == "lounging":
        where = "indoors"
    elif key == "vacation":
        where = f"on {weather} days away"
    elif climate.get("used"):
        where = f"on the {weather} days here, about {annual:.0f} a year"
    else:
        where = f"on {weather} days (home weather not yet used)"
    return f"For {label}, {how_often}: {where}"


def _explain(f: gaps._Finding, answers: dict, climate: dict) -> None:
    texts = []
    for key in SITUATIONS:
        days = list(dict.fromkeys(d for d in f.days if d.situation == key))
        if not days:
            continue
        prefix = _when(days, answers, climate)
        texts.extend(f"{prefix}. {reason}" for reason in f.why)
    f.why = texts


def _lounge(c: gaps._Closet, days: list[gaps.Day]) -> list[gaps._Finding]:
    if not days:
        return []
    rows = [r for r in c.engine_items if eligible(r, "lounging") and r.get("rating") != "dislike"]
    findings = []
    for place, categories, want in (
        ("base", ("tee",), ("tee", "casual", "lounge")),
        ("bottom", ("trousers", "shorts"), ("trousers", "casual", "lounge")),
    ):
        owned = [r for r in rows if r.get("category") in categories]
        if len(owned) >= LOUNGE_CHOICES:
            continue
        score = (gaps.THIN_SCORE_BASE if owned else LOUNGE_MISSING_SCORE) * days[0].frequency / gaps.DAYS_PER_WEEK
        noun = "relaxed tee" if place == "base" else "pair of soft trousers or shorts"
        why = (f"You rely on your {owned[0]['name'] or noun}; another {noun} gives you a change."
               if owned else f"You have no suitable {noun} for home.")
        findings.append(gaps._Finding("thin_place" if owned else "days", want, place, [why], score, (1,),
                                     days, [r["id"] for r in owned]))
    return findings


def analyse(rows: list[dict], wears: list[dict], answers: dict | None, climate: dict, limit: int = 100) -> dict:
    """Reuse the engine and gap rules; only the gap analysis learns about the owner's life."""
    if answers is None:
        result = gaps.find_gaps(rows, wears, {"max_gaps": limit})
        for g in result["gaps"]:
            g["situations"] = []
        result["taste"] = {"used": False, "summary": None}
        return result
    c = gaps._closet(rows, wears)
    clothes = [p for p in c.pieces + c.disliked if p.category not in outfits.ACCESSORY_CATEGORIES]
    if len(clothes) < gaps.MIN_ITEMS:
        result = gaps.find_gaps(rows, wears, {"max_gaps": limit})
        result["taste"] = {"used": False, "summary": None}
        return result
    days = [d for key in SITUATIONS for d in days_for(key, answers, climate)]
    findings, used = [], {}
    for key in SITUATIONS:
        subset = [d for d in days if d.situation == key]
        if not subset:
            continue
        if key == "lounging":
            findings += _lounge(c, subset)
            continue
        closet = gaps._closet([r for r in rows if eligible(r, key)], wears)
        failures, thin, counts = gaps._run_grid(closet, subset)
        for pid, count in counts.items():
            used[pid] = used.get(pid, 0) + count
        for failure in failures:
            failure.want = _special_want(failure.want, failure.place, key)
        found = gaps._day_findings(failures) + gaps._thin_findings(thin)
        for f in found:
            f.want = _special_want(f.want, f.place, key)
        findings += found
    worn, notes = gaps._wear_findings(c)
    for f in gaps._basic_findings(c) + gaps._orphan_findings(c, used) + worn:
        matching = [d for d in days if _serves(f, d)]
        if not matching:
            continue
        f.days = matching
        f.occasions = gaps._levels(matching)
        f.score *= min(1, sum(d.weight for d in matching) / gaps.WEATHER_CELLS)
        findings.append(f)
    for f in findings:
        _explain(f, answers, climate)
        if f.want[2] == "lounge":
            f.name = "A relaxed tee for home" if f.want[0] == "tee" else "Soft trousers for home"
        elif f.want[2] in ACTIVE_TAGS.values():
            tag = f.want[2].removesuffix("_active")
            description = {"warm": "Warm", "light": "Light", "rain": "Waterproof",
                           "rainwarm": "Warm, waterproof"}.get(tag, "Comfortable")
            f.name = f"{description} {f.want[0].replace('_', ' ')} for exercise"
    # Merge exactly as before; the identity is still category/formality/kind, never a situation name.
    result_gaps = [g for g in gaps._merge(findings, c) if g["score"] > 0]
    for g in result_gaps:
        matching = [d for d in days if d.as_dict() in g["evidence"]["days"]]
        g["situations"] = _situation_shares(matching, answers)
        if g["id"].endswith("-lounge"):
            g["look_for"].update(material="soft jersey, fleece or knit; not denim or tailored cloth", fit="relaxed")
        elif g["id"].endswith("active"):
            tag = g["id"].split("-")[-1].removesuffix("_active")
            g["look_for"].update(gaps.TAG_LOOK.get(tag, {}))
            material = g["look_for"].get("material")
            g["look_for"]["material"] = ((material + "; ") if material else "") + "cloth you can move in; check it suits your activity"
    learned = taste.learn(rows, wears)
    taste.apply(result_gaps, learned, c)
    return {"enough": True, "message": None, "gaps": result_gaps[:limit], "notes": notes,
            "checked": {"items": len(c.pieces) + len(c.disliked), "wears": c.wear_total, "days": len(days)},
            "taste": {"used": learned["used"], "summary": learned["summary"]}}


def example() -> tuple[dict, dict]:
    return deepcopy(DEMO_LIFE), deepcopy(DEMO_CLIMATE)
