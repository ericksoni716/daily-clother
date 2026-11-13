"""Conservative, explainable taste from recorded wears and item ratings; no text interpretation."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

from . import gaps, insights, outfits, vocab

MIN_WEARS = 10
MIN_WORN_ITEMS = 3
MIN_RATINGS = 5
MIN_VALUE_ITEMS = 2
MIN_VALUE_SCORE = 4
AVOID_SHARE = 0.75
LONG_OWNED_DAYS = 180
MIN_LOG_DAYS = 90
MIN_SEASON_DAYS = 90
MAX_WEAR_POINTS = 10
NEVER_WORN_POINTS = -2
RATING_POINTS = {"love": 4, "like": 2, "meh": 0, "dislike": -4}
AXES = ("color", "pattern", "fit", "formality")
ALLOWED = {"color": vocab.COLOR, "pattern": vocab.PATTERN, "formality": vocab.FORMALITY,
           "fit": ("slim", "regular", "relaxed", "oversized")}


def _date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def learn(rows: list[dict], wears: list[dict]) -> dict:
    rows = [r for r in rows if r.get("status") != "archived"]
    ids = {r["id"] for r in rows}
    seen = {(w.get("item_id"), w.get("worn_on")) for w in wears
            if w.get("item_id") in ids and _date(w.get("worn_on")) is not None}
    counts = Counter(i for i, _ in seen)
    wear_ready = len(seen) >= MIN_WEARS and len(counts) >= MIN_WORN_ITEMS
    rating_ready = sum(r.get("rating") in RATING_POINTS for r in rows) >= MIN_RATINGS
    empty = {"used": False, "summary": None, "wear_ready": wear_ready, "by_category": {}}
    if not (wear_ready or rating_ready):
        return empty
    dates = sorted(_date(d) for _, d in seen)
    categories = defaultdict(list)
    for row in rows:
        if row.get("category") in vocab.CATEGORY:
            categories[row["category"]].append(row)
    by_category = {category: _learn_category(items, counts, dates, wear_ready, rating_ready)
                   for category, items in categories.items()}
    used = any(profile["used"] for profile in by_category.values())
    return {"used": used, "summary": "What you wear and rate" if used else None,
            "wear_ready": wear_ready, "by_category": by_category}


def _learn_category(rows: list[dict], counts: Counter, dates: list[date],
                    wear_ready: bool, rating_ready: bool) -> dict:
    scores = {a: Counter() for a in AXES}
    positive = {a: defaultdict(set) for a in AXES}
    negative = {a: defaultdict(set) for a in AXES}
    total = {a: defaultdict(set) for a in AXES}
    for r in rows:
        count = counts[r["id"]] if wear_ready else 0
        rating = RATING_POINTS.get(r.get("rating"), 0) if rating_ready else 0
        owned = _date(r.get("created_at"))
        neglected = bool(wear_ready and dates and owned and not count and
                         (dates[-1] - dates[0]).days >= MIN_LOG_DAYS and
                         (dates[-1] - owned).days >= LONG_OWNED_DAYS and
                         insights.season_days(max(owned, dates[0]), dates[-1], r.get("season")) >= MIN_SEASON_DAYS)
        # A dislike remains a negative even if it was once worn often.
        score = (RATING_POINTS["dislike"] if rating < 0 else
                 min(MAX_WEAR_POINTS, count) + rating + (NEVER_WORN_POINTS if neglected else 0))
        silhouette = r.get("silhouette")
        values = {**r, "fit": silhouette.get("fit") if isinstance(silhouette, dict) else None}
        for axis in AXES:
            value = values.get(axis)
            if value not in ALLOWED[axis]:
                continue
            scores[axis][value] += score
            total[axis][value].add(r["id"])
            if score > 0:
                positive[axis][value].add(r["id"])
            if score < 0:
                negative[axis][value].add(r["id"])
    favoured, avoided = {}, {}
    for axis in AXES:
        favoured[axis] = sorted(
            (v for v in scores[axis] if scores[axis][v] >= MIN_VALUE_SCORE
             and len(positive[axis][v]) >= MIN_VALUE_ITEMS),
            key=lambda v: (-scores[axis][v], v))
        avoided[axis] = sorted(
            v for v in scores[axis] if len(negative[axis][v]) >= MIN_VALUE_ITEMS
            and len(negative[axis][v]) / len(total[axis][v]) >= AVOID_SHARE and scores[axis][v] < 0)
    color_wears = Counter()
    for row in rows:
        if row.get("color") in vocab.COLOR and row.get("rating") != "dislike":
            color_wears[row["color"]] += counts[row["id"]]
    worn_colors = [color for color in sorted(color_wears, key=lambda color: (-color_wears[color], color))[:2]
                   if color_wears[color] >= MIN_VALUE_SCORE] if wear_ready else []
    used = any(favoured.values()) or any(avoided.values())
    return {"used": used, "favoured": favoured, "avoided": avoided, "worn_colors": worn_colors}


def apply(found: list[dict], learned: dict, closet: gaps._Closet) -> None:
    if not learned["used"]:
        return
    for g in found:
        look = g["look_for"]
        category = look["category"]
        profile = learned["by_category"].get(category)
        if not profile or not profile["used"]:
            continue
        want = (category, look["formality"], None)
        around = [closet.by_id[i] for i in g["evidence"]["items"] if i in closet.by_id]
        candidates = list(dict.fromkeys(look["colors"] + profile["favoured"]["color"] +
                                      list(gaps.COLOR_PICKS.get(category, ()))))
        # Taste only breaks ties between colours that go equally well with the evidence.
        def rank(color: str, want: tuple = want, around: list = around, category: str = category,
                 candidates: list = candidates, profile: dict = profile) -> tuple:
            probe = gaps._probe(want, color)
            clashes = sum(bool(outfits._outfit_problems([probe, p], [])) for p in around if p.category != category)
            preferred = profile["favoured"]["color"]
            return (clashes, color in profile["avoided"]["color"],
                    preferred.index(color) if color in preferred else len(preferred), candidates.index(color))
        look["colors"] = sorted(candidates, key=rank)[:gaps.COLORS_MAX]
        favoured = [v for v in look["colors"] if v in profile["favoured"]["color"]][:2]
        if favoured:
            colors = gaps._join(favoured).replace("_", " ")
            if all(color in profile["worn_colors"] for color in favoured):
                reason = f"you wear {colors} most"
            elif learned["wear_ready"]:
                reason = f"your wears and ratings favour {colors}"
            else:
                reason = f"you rate {colors} highly"
            g["why"].append(f"Among colours that go with your clothes, these come first because {reason}.")
        look["avoid_patterns"] = profile["avoided"]["pattern"]
        look["avoid_fits"] = profile["avoided"]["fit"]
        if look.get("pattern") in look["avoid_patterns"]:
            look["pattern"] = None
        if look.get("fit") in look["avoid_fits"]:
            look["fit"] = None
        fits = [v for v in profile["favoured"]["fit"] if v not in look["avoid_fits"]]
        if fits and not look.get("fit") and category not in outfits.ACCESSORY_CATEGORIES + outfits.PLACE_CATEGORIES["shoes"]:
            look["fit"] = fits[0]
        patterns = [v for v in profile["favoured"]["pattern"] if v not in look["avoid_patterns"]]
        # Plain is the safe pairing rule; a favoured loud print is not a reason to create a clash.
        if patterns and patterns[0] == "solid" and not look.get("pattern"):
            look["pattern"] = "solid"
