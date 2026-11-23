"""Give it an outing: now and then Today builds its last outfit around a piece you like and have not worn in a while.

The rules here are pure (`choose`, `place`, `suits_weather`, `passed_over`): plain data in and out, today passed in.
The few lines at the end keep which day offered which piece (`outings`, migration 0053), read and written by
`closet/today.py`.

Who is a candidate: a piece rated love (all of those first) or like, worn or added at least `AFTER_DAYS` days ago,
counting only the days it could have been worn (a day you recorded an outfit for whose weather did not suit it does
not count, so a winter coat is not neglected in July nor at the first frost); wearable today by the rules every
outfit passes (clean, not away, not mended, right for today's weather and occasion); not loungewear, sleepwear,
swimwear or sport clothes on an ordinary day; a garment or shoes, not an accessory; not in one of the outfits that stay
on the page; and not offered as an outing in the last `REST_DAYS` days. The first candidate around whom the
build-around rules make a good outfit (`good`) is chosen; if none, there is no outing.

The rhythm: at most one outing day in `EVERY_DAYS` days. A day's outing is kept, so reloading Today offers the same
piece; "Not this piece" on it ends the day's outing, and it counts as offered for the rest.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from datetime import date

from . import db, outfits
from .tagger.taxonomy import SPORT_KINDS

# "A while": four weeks of days the piece could have been worn. A guess for the owner to change (DECISIONS, "Give it
# an outing"): long enough that a piece in the usual rotation never qualifies, short enough that a season does not
# pass without it.
AFTER_DAYS = 28
# At most one outing day in this many days: now and then, never a habit the owner learns to skip.
EVERY_DAYS = 5
# A piece offered as an outing (worn or not, turned down or not) waits this long before it is offered again.
REST_DAYS = 21
# The outing outfit must be good, not just possible: no warning at all, and at least this score (an outfit that breaks
# nothing and has nothing special scores 80, `outfits.SCORE_START`).
MIN_SCORE = 70
# At most this many candidates are tried a day, each one search built around it.
TRIES = 4
RATINGS = ("love", "like")
# Clothes made for sport, on a day that is not for sport (the taxonomy's activewear; tennis and golf shoes, loungewear
# and swimwear are never offered at all, `outfits._unavailable`).
SPORT_ONLY = SPORT_KINDS


def _the_level(p: outfits.Piece) -> str:
    """The occasion the piece is made for: its own level, so judging a past day reads only the weather."""
    return outfits.rules().levels[p.formality]


def _fits_day(p: outfits.Piece, ctx: outfits.Context) -> bool:
    """Whether the piece passes the day's rules in some place it can take: no problem for the day (weather, occasion),
    not out of its season, and a layer the day's band allows."""
    t = outfits._design_temp(ctx)
    band = outfits._band(ctx)
    for place in outfits.PLACES:
        if not outfits._fits(p, place):
            continue
        if outfits._piece_problem(p, place, ctx, t):
            continue
        if p.season == "warm" and t < outfits.WARM_SEASON_MIN_C or p.season == "cool" and t > outfits.COOL_SEASON_MAX_C:
            continue
        if place in ("mid", "outer") and getattr(band, place) == "no" and not (
                outfits.wide(ctx) and p.weight <= outfits.WIDE_LAYER_MAX):
            continue
        return True
    return False


def suits_weather(p: outfits.Piece, low_c: float, high_c: float, rain: bool) -> bool:
    """Whether a day's weather suited the piece, whatever the occasion (judged at the piece's own level)."""
    return _fits_day(p, outfits.Context(float(low_c), float(high_c), bool(rain), occasion=_the_level(p)))


def passed_over(p: outfits.Piece, since: date, today: date, dressed: list[dict]) -> int:
    """How many days since `since` (its last wear, or the day it was added) the piece could have been worn: every day
    between, less those you recorded an outfit for whose weather did not suit it. `dressed`: {day, low_c, high_c, rain}
    of the outfits recorded on Today (a day recorded twice counts once)."""
    unsuited = set()
    for d in dressed:
        try:
            day = date.fromisoformat(str(d["day"]))
        except (KeyError, ValueError):
            continue
        if since < day < today and day not in unsuited and not suits_weather(p, d["low_c"], d["high_c"], bool(d["rain"])):
            unsuited.add(day)
    return max(0, (today - since).days - len(unsuited))


def _since(item: dict, last_worn: Mapping[str, str]) -> tuple[date, bool] | None:
    """The day the piece was last worn (before today), or the day it was added and True when never worn."""
    try:
        if last_worn.get(item["id"]):
            return date.fromisoformat(last_worn[item["id"]][:10]), False
        return date.fromisoformat(str(item.get("created_at") or "")[:10]), True
    except ValueError:
        return None


def _core(o: dict) -> tuple:
    return tuple((o.get("pieces") or {}).get(pl) or "" for pl in outfits.PLACES)


def _ids(o: dict) -> set[str]:
    pieces = o.get("pieces") or {}
    return {pieces[pl] for pl in outfits.PLACES if pieces.get(pl)} | set(pieces.get("accessories") or [])


def wearable_today(item: dict, p: outfits.Piece, ctx: outfits.Context) -> bool:
    """Whether the piece can be an outing today: liked or loved, clean and in the closet, right for the day by the
    rules every outfit passes, and not for home, swimming or (on an ordinary day) sport."""
    if p.rating not in RATINGS or p.category in outfits.ACCESSORY_CATEGORIES:
        return False
    if outfits._unavailable(item, ctx) is not None:
        return False
    if ctx.occasion != "athletic" and item.get("kind") in SPORT_ONLY:
        return False
    return _fits_day(p, ctx)


def good(outfit: dict) -> bool:
    """An outfit worth offering as an outing: nothing to be aware of, and a score the rules call good."""
    return not outfit["warnings"] and (outfit.get("score") or 0) >= MIN_SCORE


def _built(rows: list[dict], ctx: outfits.Context, item_id: str, feedback: outfits.Feedback | None,
           staying: list[dict]) -> dict | None:
    """The best outfit built around the piece by the build-around rules, when it is good and not one already shown."""
    found = outfits.suggest(rows, dataclasses.replace(ctx, build_around=item_id), 1, feedback)["outfits"]
    if not found or not good(found[0]) or any(_core(found[0]) == _core(o) for o in staying):
        return None
    the = outfits._the(next(p for p in (outfits._piece(r) for r in rows if r.get("id") == item_id) if p))
    # the sentence about the outing says why it is here: these two would say it again
    drop = {f"Built around {the}.", f"Includes a piece you love: {the}."}
    return {**found[0], "reasons": [r for r in found[0]["reasons"] if r not in drop]}


def choose(rows: list[dict], ctx: outfits.Context, *, shown: list[dict], today: date, last_worn: Mapping[str, str],
           dressed: list[dict], history: list[dict], feedback: outfits.Feedback | None = None) -> dict | None:
    """Today's outing, or None: {item_id, rating, since, never_worn, plural, outfit, new}. `outfit` is the outfit built around
    the piece, to take the last place (`place`); `new` says it was chosen now rather than kept from earlier today.

    `shown`: today's outfits (the outing replaces the last, so its piece must not be in the others); `last_worn`: id ->
    the last day each piece was worn before today; `dressed`: the days you recorded an outfit with their weather
    (`passed_over`); `history`: the outings offered, {day, item_id, since, never_worn, turned_down}, any order.
    The caller leaves out the days that have no outing at all (a day ahead, a trip, a piece built around, a plan)."""
    if len(shown) < 2:
        return None   # the outing takes the last place, never the first
    staying = shown[:-1]
    in_staying = set().union(*(_ids(o) for o in staying))
    pieces = {r["id"]: (r, p) for r in rows if r.get("id") and (p := outfits._piece(r)) is not None}
    iso = today.isoformat()
    todays = next((h for h in history if h["day"] == iso), None)
    if todays is not None:   # the day's outing is kept: the same piece all day, or none once turned down
        got = pieces.get(todays["item_id"])
        if todays["turned_down"] or got is None or todays["item_id"] in in_staying or not wearable_today(*got, ctx):
            return None
        outfit = _built(rows, ctx, todays["item_id"], feedback, staying)
        return None if outfit is None else {
            "item_id": todays["item_id"], "rating": got[1].rating, "since": todays["since"],
            "never_worn": bool(todays["never_worn"]), "plural": outfits.plural(got[1]), "outfit": outfit, "new": False}

    for h in history:   # at most one outing day in EVERY_DAYS days
        try:
            if 0 < (today - date.fromisoformat(h["day"])).days < EVERY_DAYS:
                return None
        except ValueError:
            continue
    resting = set()
    for h in history:
        try:
            if 0 < (today - date.fromisoformat(h["day"])).days < REST_DAYS:
                resting.add(h["item_id"])
        except ValueError:
            continue
    candidates = []
    for item_id, (item, p) in pieces.items():
        if item_id in in_staying or item_id in resting or not wearable_today(item, p, ctx):
            continue
        since = _since(item, last_worn)
        if since is None:
            continue
        days = passed_over(p, since[0], today, dressed)
        if days >= AFTER_DAYS:
            candidates.append((RATINGS.index(p.rating), -days, item_id, since))
    for _, _, item_id, (since, never) in sorted(candidates)[:TRIES]:
        outfit = _built(rows, ctx, item_id, feedback, staying)
        if outfit is not None:
            p = pieces[item_id][1]
            return {"item_id": item_id, "rating": p.rating, "since": since.isoformat(), "never_worn": never,
                    "plural": outfits.plural(p), "outfit": outfit, "new": True}
    return None


def place(shown: list[dict], found: dict) -> list[dict]:
    """Today's outfits with the outing in the last place, carrying what the page says about it (`outing`). Unchanged
    when there are fewer than two, or when the piece is already in one of the others (Claude chose it, say)."""
    outfit = {**found["outfit"], "outing": {k: found[k] for k in ("item_id", "rating", "since", "never_worn", "plural")}}
    others = [o for o in shown if _core(o) != _core(outfit)]
    if len(shown) < 2:
        return shown
    staying = others[:len(shown) - 1]
    if any(found["item_id"] in _ids(o) for o in staying):
        return shown
    return [*staying, outfit]


# ------------------------------------------------------------------ what is kept
def history(conn, today: date) -> list[dict]:
    """The outings of the last few weeks (enough for the rhythm and the rest), newest first."""
    since = date.fromordinal(today.toordinal() - max(REST_DAYS, EVERY_DAYS)).isoformat()
    return [dict(r) for r in conn.execute(
        "SELECT day, item_id, since, never_worn, turned_down FROM outings WHERE day >= ? ORDER BY day DESC", (since,))]


def record(conn, today: date, found: dict) -> None:
    """Keep the day's outing (the first one chosen stands)."""
    conn.execute("INSERT OR IGNORE INTO outings (day, item_id, since, never_worn, created_at) VALUES (?, ?, ?, ?, ?)",
                 (today.isoformat(), found["item_id"], found["since"], int(found["never_worn"]), db.now()))


def turn_down(conn, today: date, left_out: set[str]) -> None:
    """"Not this piece" on the day's outing: it ends for the day, and counts as offered."""
    if left_out:
        conn.execute(f"UPDATE outings SET turned_down = 1 WHERE day = ? AND item_id IN ({','.join('?' * len(left_out))})",
                     (today.isoformat(), *sorted(left_out)))


def last_worn(conn, today: date) -> dict[str, str]:
    """The last day each piece was worn before today."""
    return {i: d for i, d in conn.execute("SELECT item_id, MAX(worn_on) FROM wears WHERE worn_on < ? GROUP BY item_id",
                                          (today.isoformat(),)) if d}


def dressed(conn, today: date) -> list[dict]:
    """The days you recorded an outfit on Today, with the weather it was chosen for (a year back at most)."""
    since = date.fromordinal(today.toordinal() - 366).isoformat()
    return [{"day": r["worn_on"], "low_c": r["low_c"], "high_c": r["high_c"], "rain": bool(r["rain"])}
            for r in conn.execute("SELECT worn_on, low_c, high_c, rain FROM worn_outfits WHERE low_c IS NOT NULL AND "
                                  "high_c IS NOT NULL AND worn_on >= ? AND worn_on < ?", (since, today.isoformat()))]
