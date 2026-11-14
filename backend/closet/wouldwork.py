"""Would this work? A piece the owner might buy, checked against the closet by rule.

Pure functions: no database, no network, no clock. `check(items, wears, piece)`
takes the closet's items and wear log (as `gaps.find_gaps` takes them) and a
description of one candidate piece (`parse_piece`), treats the piece as if it
were in the closet, and answers:

- what it would fill: the gaps of `gaps.find_gaps` that go away or get smaller
  with it, with the days it would cover that nothing covers now;
- what it goes with: on how many of the gap analysis's kinds of day the outfit
  engine (`outfits.suggest`, built around the piece) makes a good outfit with
  it, the owner's pieces it pairs with most, and an example outfit for up to
  three kinds of day;
- what it repeats: pieces already owned that do the same job (same kind,
  formality and colour group), with how often each is worn;
- what would hold it back: the engine's own rules where it rarely fits;
- a verdict, one of VERDICTS, chosen by the thresholds below, with one or two
  sentences of reasons built from the points above.

Once the owner has said how they live (`answers` and `climate`, as `life.analyse`
takes them), the gaps before and after are the weighed ones the list shows, a gap
makes the verdict "fills a gap" only when it is high on that list (RANK_MAX), and
the answer says which of the owner's situations the piece serves. Without
answers the check is exactly the plain one.

Neither `outfits.py` nor `gaps.py` is changed: both are called, and their own
pieces and rules (functions whose names start with `_`) are read, as `gaps.py`
reads the engine's. The same inputs always give the same answer.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping

from . import gaps, life, outfits, vocab

CANDIDATE_ID = "~candidate"  # the piece's id while it is tried in the closet; never an item id (those are hex)

# ------------------------------------------------------------------ verdicts
VERDICTS = {
    "fills_gap": "Fills a gap",
    "adds": "Works, and adds something",
    "have_it": "Works, but you have it already",
    "hard_to_wear": "Hard to wear with what you have",
    "too_small": "Not enough in the closet to say",
}
ALL_GAPS = 100               # gaps asked of the analysis before and after: every one, so none is cut off the end
FILL_MIN_SHARE = 0.5         # a gap counts as filled when it goes, or the piece makes a good outfit on at least this
                             # share of the kinds of day it fails on now (days, not scores: see _after)
GOOD_MIN_DAYS = 2            # a good outfit on fewer kinds of day than this and the piece is hard to wear...
GOOD_MIN_SHARE = 0.25        # ...or on less than this share of the kinds of day that suit the piece itself
REPEAT_MIN = 1               # this many owned pieces doing the same job and it is "you have it already"
HARDLY_WORN_MAX = 1          # worn at most this many times in the log is "hardly worn"...
                             # ...said only when the log has at least gaps.WEAR_MIN_LOG wears, as the gap analysis does
FEW_PARTNERS_SHARE = 1 / 3   # fewer than this share of the pieces it is worn with go with it, and the answer says so
RANK_MAX = gaps.MAX_GAPS     # with the owner's answers, a gap makes "fills a gap" only when it is this high on the
                             # weighed list, the gaps What's missing shows; one further down is listed, as low
COMPARE_MAX = 6              # owned pieces of its kind (most worn first) tried on a day it fails, to tell whether the
                             # piece or the closet falls short there
PAIRS_MAX = 6                # the owner's pieces it pairs with best, at most this many
EXAMPLES_MAX = 3             # example outfits, one per kind of day
REASONS_MAX = 2              # sentences under the verdict
NAMES_MAX = 3                # pieces named in a sentence

# Colour groups for "does the same job": dark neutrals stand in for each other, as do light ones and earth tones;
# the other colours by the engine's own families (light blue with blue, burgundy with red).
COLOR_GROUPS = {"black": "dark", "navy": "dark", "white": "light", "cream": "light", "grey": "grey",
                "tan": "earth", "brown": "earth", "olive": "green", "multi": "multi", **{
                    c: f for c, f in outfits.COLOR_FAMILY.items() if c not in ("navy", "olive")}}
# A gap found only by the wear log ("a second one like the piece you wear most") does not make the verdict "fills a
# gap": the same piece again is the answer to it, and the pieces like it you hardly wear are often the better one.
WEAR_ONLY = {"worn_most"}
# Jeans in any of these washes do the same job: the engine counts blue jeans as neutral, like navy and black ones.
DENIM_COLORS = ("blue", "light_blue", "navy", "black", "grey")

# ------------------------------------------------------------------ the description
CATEGORIES = tuple(c for c in vocab.CATEGORY if c in outfits.CATEGORY_FORMALITY)  # "other" cannot be tried in an outfit
FIELDS = ("category", "color", "formality", "season", "pattern", "weight_class", "rain_proof", "name", "material",
          "silhouette")
NAME_MAX = 120
MATERIAL_MAX = 200
RAIN_WORD = "waterproof"     # added to the material of a piece said to keep the rain off; the engine reads it


class PieceError(ValueError):
    """A description the check cannot work with, in words the owner can read."""


def _choice(data: Mapping, key: str, allowed: Iterable[str], words: str) -> str | None:
    value = data.get(key)
    if value in (None, ""):
        return None
    allowed = list(allowed)
    if value not in allowed:
        raise PieceError(f"'{value}' is not {words}. Choose one of: {', '.join(a.replace('_', ' ') for a in allowed)}.")
    return value


def _text(data: Mapping, key: str, limit: int, words: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise PieceError(f"The {words} must be text.")
    value = " ".join(value.split())
    if len(value) > limit:
        raise PieceError(f"The {words} is too long: at most {limit} characters.")
    return value or None


def parse_piece(data: object) -> dict:
    """Check a description and fill in what was left out. Raises PieceError with a sentence.

    Kind and colour are needed; formality defaults to the engine's usual one for the kind, the season to all year,
    the pattern to plain. `weight_class` is one of the engine's weight classes, `rain_proof` true when it keeps the
    rain off; `silhouette` uses the item vocabulary.
    """
    if not isinstance(data, Mapping):
        raise PieceError("Describe the piece as an object, for example {\"category\": \"coat\", \"color\": \"navy\"}.")
    unknown = sorted(set(data) - set(FIELDS))
    if unknown:
        raise PieceError(f"These are not part of a description: {', '.join(unknown)}.")
    if not data.get("category"):
        raise PieceError("Choose what kind of piece it is.")
    category = _choice(data, "category", CATEGORIES, "a kind of piece Closet can check")
    if not data.get("color"):
        raise PieceError("Choose its main colour.")
    color = _choice(data, "color", vocab.COLOR, "a colour")
    formality = _choice(data, "formality", vocab.FORMALITY, "a formality") or outfits.CATEGORY_FORMALITY[category]
    season = _choice(data, "season", vocab.SEASON, "a season") or "all"
    pattern = _choice(data, "pattern", vocab.PATTERN, "a pattern") or "solid"
    weight = _choice(data, "weight_class", outfits.WEIGHT_CLASSES, "a weight")
    rain = data.get("rain_proof", False)
    if rain is None:
        rain = False
    if not isinstance(rain, bool):
        raise PieceError("Whether it keeps the rain off must be true or false.")
    sil = data.get("silhouette") or {}
    if not isinstance(sil, Mapping):
        raise PieceError("The shape must be an object, for example {\"fit\": \"slim\"}.")
    for k, v in sil.items():
        if k not in vocab.SILHOUETTE or (v is not None and v not in vocab.SILHOUETTE[k]):
            raise PieceError(f"'{k}: {v}' is not part of a shape this app knows.")
    return {"category": category, "color": color, "formality": formality, "season": season, "pattern": pattern,
            "weight_class": weight, "rain_proof": rain, "name": _text(data, "name", NAME_MAX, "name"),
            "material": _text(data, "material", MATERIAL_MAX, "material"),
            "silhouette": {k: v for k, v in sorted(sil.items()) if v is not None}}


def piece_name(piece: Mapping) -> str:
    """The piece in a few words, for sentences and the wishlist: its name, else "Navy coat"."""
    if piece.get("name"):
        return str(piece["name"])
    words = " ".join(str(w).replace("_", " ") for w in (piece.get("color"), piece.get("category")) if w)
    return (words[:1].upper() + words[1:]) or "Piece"


SEASON_WORDS = {"warm": "for warm weather", "cool": "for cold weather", "all": "all year"}


def describe(piece: Mapping) -> str:
    """The description in one line, for the wishlist's note: "Navy coat, smart casual, all year, midweight, keeps
    the rain off"."""
    words = [piece_name(piece)]
    if piece.get("name"):
        words.append(" ".join(str(w).replace("_", " ") for w in (piece.get("color"), piece.get("category")) if w))
    if piece.get("pattern") not in (None, "solid"):
        words.append(str(piece["pattern"]))
    words += [str(piece.get("formality") or "").replace("_", " "), SEASON_WORDS.get(piece.get("season") or "all", "")]
    if piece.get("weight_class"):
        words.append(str(piece["weight_class"]).replace("_", " "))
    if piece.get("rain_proof"):
        words.append("keeps the rain off")
    return ", ".join(w for w in words if w)


def candidate_row(piece: Mapping) -> dict:
    """The piece as an item row the engine reads."""
    material = " ".join(w for w in (piece.get("material"), RAIN_WORD if piece.get("rain_proof") else None) if w)
    name = piece.get("name") or f"new {piece_name(piece)[:1].lower()}{piece_name(piece)[1:]}"
    return {"id": CANDIDATE_ID, "name": name, "category": piece["category"], "color": piece.get("color"),
            "color_hex": None, "pattern": piece.get("pattern") or "solid", "formality": piece.get("formality"),
            "season": piece.get("season") or "all", "weight_class": piece.get("weight_class"),
            "silhouette": dict(piece.get("silhouette") or {}), "material": material or None, "rating": None,
            "status": "active", "location": "closet", "laundry": "clean"}


# ====================================================================== pieces of the answer
def _group(p: outfits.Piece) -> str | None:
    if p.category in outfits.DENIM_CATEGORIES and p.color in DENIM_COLORS:
        return "denim"
    return COLOR_GROUPS.get(p.color or "", p.color)


def _same_job(a: outfits.Piece, b: outfits.Piece) -> bool:
    return a.category == b.category and a.formality == b.formality and _group(a) == _group(b)


def _place(p: outfits.Piece) -> str:
    return gaps.HOME_PLACE.get(p.category, "accessory")


def _places(p: outfits.Piece) -> list[str]:
    return [pl for pl in outfits.PLACES if outfits._fits(p, pl)] or ["accessory"]


def _suits(p: outfits.Piece, ctx: outfits.Context, t: float) -> bool:
    """The piece itself is right for the day in one of its places, whatever it is worn with."""
    band = outfits._band(ctx)
    if p.category in ("scarf", "hat") and p.category not in band.accessories:
        return False
    for place in _places(p):
        if place in ("mid", "outer") and getattr(band, place) == "no":
            continue
        if not outfits._piece_problem(p, place, ctx, t):
            return True
    return False


def _problems(outfit: dict, cand: outfits.Piece, by_id: Mapping[str, outfits.Piece], ctx: outfits.Context,
              t: float) -> list[str]:
    """What keeps an outfit from being a good one, by the engine's rules (empty: a good outfit).

    The rules the gap analysis counts a day as failing on: a piece wrong for the day, pieces that clash, or an
    outfit well short of warm or well too warm. Rain is the coat's job and is not counted here.
    """
    pieces = outfit["pieces"]
    core = {pl: by_id[pieces[pl]] for pl in outfits.PLACES if pieces.get(pl) in by_id}
    accessories = [by_id[i] for i in pieces.get("accessories", []) if i in by_id]
    out = [s for pl, q in core.items() if (s := outfits._piece_problem(q, pl, ctx, t))]
    if cand in accessories and (s := outfits._piece_problem(cand, "accessory", ctx, t)):
        out.append(s)
    outer = core.get("outer")
    clothes = list(core.values())
    out += outfits._outfit_problems(clothes, [q for q in clothes if q is not outer], outer, ctx.occasion)
    if cand in accessories:
        out += outfits._outfit_problems(clothes + [cand], [], None, ctx.occasion)
    warmth = sum(outfits._warmth(q, pl) for pl, q in core.items()) + sum(outfits._warmth(q, "accessory") for q in accessories)
    target = outfits._warmth_target(t)
    if warmth < target - outfits.WARMTH_TOLERANCE - outfits.WARMTH_NOTE_GAP:
        out.append(f"the outfit is well short of warm for {outfits._temp_words(ctx)}.")
    elif warmth > target + outfits.WARMTH_TOLERANCE + outfits.WARMTH_NOTE_GAP:
        out.append(f"the outfit is much warmer than {outfits._temp_words(ctx)} calls for.")
    return out


def _try_day(engine_items: list[dict], by_id: Mapping[str, outfits.Piece], p: outfits.Piece, d: gaps.Day) -> dict:
    """The engine, built around one piece, on one kind of day of the gap analysis."""
    ctx = outfits.Context(d.low_c, d.high_c, d.rain, d.occasion, build_around=p.id)
    t = outfits._design_temp(ctx)
    found = outfits.suggest(engine_items, ctx, 1)["outfits"]
    best = found[0] if found else None
    problems = _problems(best, p, by_id, ctx, t) if best else ["nothing goes with it."]
    suits = _suits(p, ctx, t)
    return {"day": d, "suits": suits, "outfit": best, "good": best is not None and not problems and suits,
            "problems": problems, "closet": False}


def _try_days(c: gaps._Closet, cand: outfits.Piece) -> list[dict]:
    """The engine, built around the piece, on every kind of day of the gap analysis."""
    return [_try_day(c.engine_items, c.by_id, cand, d) for d in gaps.grid()]


def _peers(c: gaps._Closet, cand: outfits.Piece) -> list[outfits.Piece]:
    """The owned pieces it is judged against: the same kind, else ones worn in the same place, most worn first."""
    owned = [p for p in c.pieces if p.id != CANDIDATE_ID]
    same = [p for p in owned if p.category == cand.category] or [p for p in owned if _place(p) == _place(cand)]
    return sorted(same, key=lambda p: (-c.wear_counts.get(p.id, 0), p.id))


def _mark_closet_days(c: gaps._Closet, tried: list[dict], peers: list[outfits.Piece]) -> None:
    """On each day that suits the piece but has no good outfit with it, mark it the closet's doing ("closet") when
    none of the owned pieces it is judged against makes a good outfit there either (tried without the piece)."""
    engine = [e for e in c.engine_items if e.get("id") != CANDIDATE_ID]
    for r in tried:
        if r["suits"] and not r["good"] and peers:
            r["closet"] = not any(_try_day(engine, c.by_id, q, r["day"])["good"] for q in peers[:COMPARE_MAX])


def _partners(tried: list[dict]) -> list[str]:
    counts: dict[str, int] = {}
    for r in tried:
        if not r["good"]:
            continue
        pieces = r["outfit"]["pieces"]
        for i in [pieces[pl] for pl in outfits.PLACES] + list(pieces["accessories"]):
            if i and i != CANDIDATE_ID:
                counts[i] = counts.get(i, 0) + 1
    return [i for i, _ in sorted(counts.items(), key=lambda x: (-x[1], x[0]))]


def _examples(tried: list[dict]) -> list[dict]:
    """A good outfit for up to EXAMPLES_MAX kinds of day: the best scoring, a different temperature each where it can."""
    good = sorted((r for r in tried if r["good"]), key=lambda r: (-r["outfit"]["score"], gaps._day_order(r["day"])))
    chosen: list[dict] = []
    for distinct in (lambda r: r["day"].band, lambda r: (r["day"].band, r["day"].occasion)):
        for r in good:
            if len(chosen) >= EXAMPLES_MAX:
                break
            if r not in chosen and all(distinct(r) != distinct(c) for c in chosen):
                chosen.append(r)
    chosen.sort(key=lambda r: gaps._day_order(r["day"]))
    return [{"day": r["day"].as_dict(), "pieces": r["outfit"]["pieces"], "score": r["outfit"]["score"],
             "reasons": r["outfit"]["reasons"]} for r in chosen]


def _grid_key(d: Mapping) -> tuple:
    """The kind of day of the gap analysis's grid, the days the piece is tried on."""
    return (d.get("temperature"), bool(d.get("rain")), d.get("occasion"))


def _day_key(d: Mapping) -> tuple:
    """A day of a gap: the kind of day and, on the weighed list, whose situation it is (None on the plain one)."""
    return (*_grid_key(d), d.get("situation"))


def _as_day(d: Mapping) -> gaps.Day:
    return gaps.Day(d["temperature"], d["low_c"], d["high_c"], d["rain"], d["occasion"])


DAY_WAYS = ("days", "thin_place")  # the gap analysis's ways that rest on kinds of day; the others rest on the pieces


def _after(c: gaps._Closet) -> list[dict]:
    """The gap analysis with the piece in the closet (`c`), as `gaps.find_gaps` makes it, except that a thin place
    resting on the piece itself is not a finding: "every outfit for these days rests on it" is what buying the piece
    the gap asked for looks like, not a gap it leaves open. So the very piece a gap asks for fills it."""
    failures, thin, used = gaps._run_grid(c)
    thin = [x for x in thin if x[0].id != CANDIDATE_ID]
    wear_found, _notes = gaps._wear_findings(c)
    findings = (gaps._day_findings(failures) + gaps._thin_findings(thin) + gaps._orphan_findings(c, used) + wear_found
                + gaps._basic_findings(c))
    return gaps._merge(findings, c)


def _labels(keys: Iterable[str | None]) -> list[str]:
    found = set(keys)
    return [spec.label for key, spec in life.SITUATIONS.items() if key in found]


def _fills(before: Mapping, after: list[dict], good: set[tuple], closet: set[tuple], weighed: bool = False) -> list[dict]:
    """Gaps the piece fills or helps with, most helped first.

    Kinds of day, not scores: the days a gap fails on now are compared with the days it fails on with the piece
    (`after`). The gap's other findings (a basic, an orphan, the wear log) are settled when they are gone. `filled`
    is the verdict's test: at least FILL_MIN_SHARE of its days fail no longer and on each of them the piece makes a
    good outfit, or nothing of its kind does (`closet`: the closet falls short there, not the piece); a gap with no
    days is filled when nothing of it is left. The days named (`days`) are only those that fail no longer and on which the piece itself makes a good outfit, so
    "covering ... that nothing covers now" is never said of a day its outfit breaks a rule on. `good` and `closet`
    are kinds of day of the grid (`_grid_key`).

    `rank` is the gap's place in the list before (1 first). On the weighed list (`weighed`) `low` is true when it is
    below RANK_MAX, and `situations` names whose days it frees (or, for a gap resting on no days, whose it is for).
    `counts` is whether it makes the verdict "fills a gap".
    """
    after_by_id = {g["id"]: g for g in after}
    after_by_name = {(g["look_for"]["category"], g["name"]): g for g in after}
    out = []
    for rank, g in enumerate(before.get("gaps", []), 1):
        a = after_by_id.get(g["id"]) or after_by_name.get((g["look_for"]["category"], g["name"]))
        days = g["evidence"]["days"] if set(g.get("found_by", [])) & set(DAY_WAYS) else []
        still = {_day_key(d) for d in a["evidence"]["days"]} if a and set(a["found_by"]) & set(DAY_WAYS) else set()
        freed = [d for d in days if _day_key(d) not in still]
        covered = [d for d in freed if _grid_key(d) in good]
        settled = [w for w in g.get("found_by", []) if w not in DAY_WAYS and (a is None or w not in a["found_by"])]
        if not freed and not settled:
            continue
        open_ways = [w for w in g.get("found_by", []) if w not in DAY_WAYS and w not in settled]
        gone = len(freed) == len(days) and not open_ways
        credited = [d for d in freed if _grid_key(d) in good or _grid_key(d) in closet]
        filled = len(credited) >= FILL_MIN_SHARE * len(days) if days else gone
        low = weighed and rank > RANK_MAX
        situations = (_labels(d.get("situation") for d in credited) if days else
                      _labels(s.get("id") for s in g.get("situations") or [])) if weighed else []
        out.append({"gap_id": g["id"], "name": g["name"], "score_before": g["score"],
                    "score_after": 0 if gone or a is None else a["score"], "gone": gone, "filled": filled,
                    "days": covered, "of_days": len(days), "found_by": list(g.get("found_by", [])),
                    "rank": rank, "low": low, "situations": situations,
                    "counts": filled and not low and bool(set(g.get("found_by", [])) - WEAR_ONLY)})
    out.sort(key=lambda f: (not f["filled"], -len(f["days"]), -(f["score_before"] - f["score_after"]), f["name"]))
    return out


def _count(n: int) -> str:
    return gaps.NUMBER.get(n, str(n))


def _names(ps: list[outfits.Piece]) -> str:
    shown = [gaps._your(p) for p in ps[:NAMES_MAX]]
    more = len(ps) - len(shown)
    return gaps._join(shown + ([f"{_count(more)} more"] if more else []))


def _repeats(c: gaps._Closet, cand: outfits.Piece) -> dict:
    same = [p for p in c.pieces if p.id != CANDIDATE_ID and _same_job(p, cand)]
    same.sort(key=lambda p: (-c.wear_counts.get(p.id, 0), p.id))
    disliked = sorted((p for p in c.disliked if _same_job(p, cand)), key=lambda p: p.id)
    log = c.wear_total >= gaps.WEAR_MIN_LOG
    items = [{"id": p.id, "worn": c.wear_counts.get(p.id, 0),
              "hardly_worn": log and c.wear_counts.get(p.id, 0) <= HARDLY_WORN_MAX} for p in same]
    out = {"items": items, "disliked": [p.id for p in disliked], "text": None, "disliked_text": None}
    if disliked:
        one = len(disliked) == 1
        out["disliked_text"] = (f"{'It does' if one else 'They do'} the same job as {_names(disliked)}, "
                                f"but you rated {'it' if one and not gaps._plural(disliked[0]) else 'them'} dislike.")
        if not same:
            out["disliked_text"] = (f"The only {'piece' if one else 'pieces'} you own doing the same job "
                                    f"{'is' if one else 'are'} {_names(disliked)}, and you rated "
                                    f"{'it' if one and not gaps._plural(disliked[0]) else 'them'} dislike.")
    if not same:
        return out
    n = len(same)
    hardly = sum(1 for i in items if i["hardly_worn"])
    text = f"You have {_count(n)} like it ({_names(same)})"
    if not log:
        text += ", and the wear log is too short yet to say how often they are worn." if n > 1 else \
            ", and the wear log is too short yet to say how often it is worn."
    elif n == 1:
        worn = items[0]["worn"]
        text += ", and it is hardly worn." if hardly else f", worn {_count(worn)} time{'' if worn == 1 else 's'} in the log."
    elif hardly:
        text += f", and {_count(hardly)} of them {'is' if hardly == 1 else 'are'} hardly worn."
    else:
        text += ", and all of them are worn."
    out["text"] = text
    return out


PAIR_REASONS = {  # why a piece it would be worn with does not go with it, as the engine's rules say
    "formality": ("is too far from it in formality", "are too far from it in formality"),
    "colour": ("has a strong colour that competes with it", "have a strong colour that competes with it"),
    "pattern": ("is patterned, and the two patterns fight", "are patterned, and the two patterns fight"),
    "layers": ("is heavier or bulkier than it, so it cannot go under it",
               "are heavier or bulkier than it, so they cannot go under it"),
}


def _pair_reason(s: str) -> str:
    return "layers" if s == "layers" else "formality" if "dressier" in s else "colour" if "colour" in s else "pattern"


def _most_common(rows: list[dict]) -> tuple[str, list[gaps.Day]]:
    counts: dict[str, list[gaps.Day]] = {}
    for r in rows:
        counts.setdefault(r["problems"][0], []).append(r["day"])
    return max(counts.items(), key=lambda x: (len(x[1]), x[0]))


def _lower(text: str) -> str:
    return text[:1].lower() + text[1:]


def _others(cand: outfits.Piece, peers: list[outfits.Piece]) -> tuple[str, bool]:
    """The pieces it is judged against, in words, and whether they read as plural."""
    noun = gaps.PLACE_NOUN.get(_place(cand), ("accessory", "accessories"))[1]
    if len(peers) > COMPARE_MAX:
        return f"your {_count(COMPARE_MAX)} most worn other {noun}", True
    if len(peers) > 1:
        return f"your other {noun}", True
    return gaps._your(peers[0]), gaps._plural(peers[0])


def _holds_back(c: gaps._Closet, cand: outfits.Piece, tried: list[dict], fills: list[dict], before: Mapping,
                peers: list[outfits.Piece]) -> list[str]:
    """The engine's own rules where the piece rarely fits. Each sentence is true of every piece or day it names."""
    out = []
    place = _place(cand)
    owned = [p for p in c.pieces if p.id != CANDIDATE_ID]
    for need in gaps.NEEDS[place]:
        partners = [q for q in owned if gaps._fills(q, need) and q.category not in outfits.ACCESSORY_CATEGORIES]
        noun = "pairs of shoes" if need == "shoes" else gaps.PLACE_NOUN[need][1]
        if not partners:
            out.append(f"You have no {noun} to wear it with.")
            continue
        why: dict[str, int] = {}
        fits = 0
        for q in partners:
            problems = gaps._pair_problems(cand, place, q, need) if place != "accessory" else \
                outfits._outfit_problems([cand, q], [])
            if need == "base" and place in ("mid", "outer") and not outfits._layers_ok(
                    q, cand if place == "mid" else None, cand if place == "outer" else None):
                problems = problems + ["layers"]
            for key in sorted({_pair_reason(s) for s in problems}):
                why[key] = why.get(key, 0) + 1
            fits += not problems
        if fits < FEW_PARTNERS_SHARE * len(partners):
            failing = len(partners) - fits
            parts = []
            for key in sorted(why, key=lambda k: (-why[k], k)):
                n = why[key]
                if n == failing:
                    verb, rest = PAIR_REASONS[key][1].split(" ", 1)
                    parts.append(f"they {verb} all {rest}" if fits == 0 else f"the rest {verb} {rest}")
                else:
                    parts.append(f"{_count(n)} {PAIR_REASONS[key][0 if n == 1 else 1]}")
            only = f"Only {_count(fits)}" if fits else "None"
            out.append(f"{only} of your {_count(len(partners))} {noun} go{'es' if fits == 1 else ''} with it: "
                       f"{gaps._join(parts)}.")
    over = {"base": ("mid", "outer"), "mid": ("outer",)}.get(place, ())

    def shape_allows(q: outfits.Piece, pl: str) -> bool:
        # the owner's rules about which kinds go over which, which are not about weight: a shirt as a mid layer
        # only over a tee, a light jacket only under a coat
        needs = outfits._needs(q, pl)
        return needs is not None and (not needs or ("over_tee" in needs and cand.category == "tee"))

    layers = [(q, pl) for q in owned for pl in over if gaps._fills(q, pl) and shape_allows(q, pl)]

    def goes_over(q: outfits.Piece, pl: str) -> bool:
        if place == "mid":
            return outfits._layers_ok(_light_base(), cand, q)
        return outfits._layers_ok(cand, q, None) if pl == "mid" else outfits._layers_ok(cand, None, q)

    if layers and not any(goes_over(q, pl) for q, pl in layers):
        out.append("Nothing you own can go over it: it is heavier or bulkier than every layer you have.")
    suits = [r for r in tried if r["suits"]]
    if not suits:
        out.append("It does not suit any of the kinds of day the closet is tried on.")
    elif not any(f["filled"] for f in fills):
        short = {d["temperature"] for g in before.get("gaps", []) if "days" in g.get("found_by", [])
                 for d in g["evidence"]["days"]}
        own = {r["day"].band for r in suits}
        if short and not own & short:
            bands = [b for b, _, _ in gaps.TEMP_BANDS]
            out.append(f"Your closet is short on {gaps._join(sorted(short, key=bands.index))} days, and this suits "
                       f"{gaps._join(sorted(own, key=bands.index))} ones.")
    mine = [r for r in suits if not r["good"] and not r["closet"]]
    if mine and len(mine) * 2 >= len(suits):
        text, days = _most_common(mine)
        out.append(f"On {gaps._days_words(days)} the best outfit with it breaks a rule: {_lower(text)}")
    closet = [r for r in suits if r["closet"]]
    if closet and len(closet) * 2 >= len(suits):
        text, days = _most_common(closet)
        who, many = _others(cand, peers)
        out.append(f"On {gaps._days_words(days)} the best outfit with it breaks a rule ({_lower(text).rstrip('.')}), "
                   f"and {who} {'do' if many else 'does'} no better there: that is what the closet lacks, not this piece.")
    return out


def _light_base() -> outfits.Piece:
    """A midweight base top, the kind that goes under anything: what a middle layer is tried over."""
    p = outfits._piece({"id": "~base", "category": "tee", "color": "white", "weight_class": "midweight"})
    assert p is not None
    return p


def _serves(row: dict, tried: list[dict], answers: Mapping, climate: Mapping) -> list[dict]:
    """The owner's situations the piece serves: those it may be worn for (`life.eligible`) with at least one of
    their days on which it makes a good outfit, in the questionnaire's order."""
    good = {_grid_key(r["day"].as_dict()) for r in tried if r["good"]}
    return [{"id": key, "label": spec.label} for key, spec in life.SITUATIONS.items()
            if life.eligible(row, key) and any(_grid_key(d.as_dict()) in good
                                               for d in life.days_for(key, dict(answers), dict(climate)))]


def _serves_text(serves: list[dict]) -> str:
    if not serves:
        return "It does not make a good outfit for any of the situations you told Closet about."
    return f"It suits {gaps._join([s['label'].lower() for s in serves])}."


# ====================================================================== entry point
def check(items: Iterable[object], wears: Iterable[object], piece: Mapping, before: Mapping | None = None,
          answers: Mapping | None = None, climate: Mapping | None = None) -> dict:
    """Would this piece work with the closet? `piece` is a description as `parse_piece` returns it (it is checked
    again). `answers` and `climate` are how the owner lives, as `life.analyse` takes them; None while the questions
    are unanswered. `before` is the gap analysis the check compares with, when the caller has it already:
    `gaps.find_gaps(items, wears, {"max_gaps": ALL_GAPS})` without answers, `life.analyse(items, wears, answers,
    climate, ALL_GAPS)` with them.

    Returns {"enough", "message", "verdict", "verdict_words", "reasons": [sentences], "piece", "fills": [{gap_id,
    name, score_before, score_after, gone, filled, days, of_days, found_by, rank, low, situations, counts}],
    "goes_with": {days, suits, of, items, examples, text}, "repeats": {items: [{id, worn, hardly_worn}], text},
    "holds_back": [sentences], "situations": [{id, label}], "situations_text", "weighed", "checked": {items, wears,
    days}}. `situations` and `situations_text` are empty and None without answers.
    """
    weighed = answers is not None
    piece = parse_piece(piece)
    items, wears = list(items), list(wears)
    row = candidate_row(piece)
    c = gaps._closet(items + [row], wears)
    cand = c.by_id[CANDIDATE_ID]
    owned = [p for p in c.pieces + c.disliked if p.id != CANDIDATE_ID]
    clothes = [p for p in owned if p.category not in outfits.ACCESSORY_CATEGORIES]
    repeats = _repeats(c, cand)
    answer = {"enough": True, "message": None, "verdict": None, "verdict_words": None, "reasons": [], "piece": piece,
              "fills": [], "goes_with": {"days": 0, "suits": 0, "of": len(gaps.grid()), "items": [], "examples": [],
                                         "text": None},
              "repeats": repeats, "holds_back": [], "situations": [], "situations_text": None, "weighed": weighed,
              "checked": {"items": len(owned), "wears": c.wear_total, "days": 0}}
    if len(clothes) < gaps.MIN_ITEMS:
        n = len(clothes)
        message = (f"With {_count(n)} piece{'' if n == 1 else 's'} of clothing the closet is too small to say whether "
                   f"it would work. Add at least {gaps.MIN_ITEMS} and look again.") if n else \
            "The closet is empty, so there is nothing to try it with yet. Add some clothes first."
        answer.update(enough=False, message=message, verdict="too_small", verdict_words=VERDICTS["too_small"],
                      reasons=[message])
        return answer

    climate = climate or {}
    if before is None:
        before = (life.analyse(items, wears, dict(answers), dict(climate), ALL_GAPS) if answers is not None
                  else gaps.find_gaps(items, wears, {"max_gaps": ALL_GAPS}))
    tried = _try_days(c, cand)
    peers = _peers(c, cand)
    _mark_closet_days(c, tried, peers)
    good = [r for r in tried if r["good"]]
    suits = [r for r in tried if r["suits"]]
    mine = [r for r in suits if not r["good"] and not r["closet"]]
    after = (life.analyse(items + [row], wears, dict(answers), dict(climate), ALL_GAPS, without=CANDIDATE_ID)["gaps"]
             if answers is not None else _after(c))
    fills = _fills(before, after, {_grid_key(r["day"].as_dict()) for r in good},
                   {_grid_key(r["day"].as_dict()) for r in tried if r["closet"]}, weighed)
    if answers is not None:
        answer["situations"] = _serves(row, tried, answers, climate)
        answer["situations_text"] = _serves_text(answer["situations"])
    partners = _partners(tried)[:PAIRS_MAX]
    goes_text = None
    if good:
        with_words = _names([c.by_id[i] for i in partners[:2]]) if partners else ""
        goes_text = (f"It makes a good outfit on {_count(len(good))} of the {len(tried)} kinds of day the closet is "
                     f"tried on" + (f", most often with {with_words}." if with_words else "."))
    answer["goes_with"].update(days=len(good), suits=len(suits), items=partners, examples=_examples(tried), text=goes_text)
    answer["fills"] = fills
    answer["checked"]["days"] = len(tried)
    holds = _holds_back(c, cand, tried, fills, before, peers)
    answer["holds_back"] = holds

    # Judged only on the days that suit it, and only where it does worse than the owned pieces of its kind: a day
    # nothing of its kind dresses well is the closet's shortfall, said as such, not the piece's.
    fair = len(good) + len(mine)
    hard = not suits or bool(mine) and (len(good) < GOOD_MIN_DAYS or len(good) < GOOD_MIN_SHARE * fair)
    real = [f for f in fills if f["counts"]]
    if real and not hard:
        verdict = "fills_gap"
    elif hard:
        verdict = "hard_to_wear"
    elif len(repeats["items"]) >= REPEAT_MIN:
        verdict = "have_it"
    else:
        verdict = "adds"

    fill_text = None
    if real:
        top = real[0]
        more = len(real) - 1
        fill_text = f"It would fill “{top['name']}”"
        if top["situations"]:
            fill_text += f" for {gaps._join([label.lower() for label in top['situations']])}"
        if top["days"]:
            fill_text += f", covering {gaps._days_words(_as_day(d) for d in top['days'])} that nothing covers now"
        fill_text += f", and {_count(more)} more gap{'' if more == 1 else 's'}." if more else "."
    closet_text = next((h for h in holds if h.endswith("not this piece.")), None)
    if verdict == "fills_gap":
        reasons = [fill_text, goes_text or closet_text]
    elif verdict == "hard_to_wear":
        if not suits:
            reasons = ["It does not suit any of the kinds of day the closet is tried on."]
        else:
            who, many = _others(cand, peers) if peers else ("", False)
            if not good:
                first = f"Nothing you own makes a good outfit with it on any of the {_count(fair)} kinds of day that suit it"
            else:
                first = f"It makes a good outfit on only {_count(len(good))} of the {_count(fair)} kinds of day that suit it"
            if peers:
                # many: "at least one of your other tops makes one"; one piece: "your grey trousers make one"
                subject = f"at least one of {who}" if many else who
                verb = "make" if not many and gaps._plural(peers[0]) else "makes"
                first += (f"; on the other {_count(len(mine))}, {subject} {verb} one." if good else
                          f", though {subject} {verb} one on each of them.")
            else:
                first += "."
            text, days = _most_common(mine)
            reasons = [first, f"On {gaps._days_words(days)} the best outfit with it breaks a rule: {_lower(text)}"]
    elif verdict == "have_it":
        reasons = [repeats["text"], goes_text or closet_text]
    else:
        reasons = [goes_text or closet_text, repeats["disliked_text"] or "Nothing you own does quite the same job."]
    answer.update(verdict=verdict, verdict_words=VERDICTS[verdict], reasons=[r for r in reasons if r][:REASONS_MAX])
    return answer
