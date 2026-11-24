"""How what is owned is being used: cost per wear, what is not worn, what is worn most, Your nines, what was spent.

Pure functions: no database, no network, and the clock is passed in.
`find_insights(items, wears, today)` takes the closet's items (rows with at
least `id, name, category, color, formality, season, price_cents, status,
created_at`), the wear log (`{item_id, worn_on}` rows) and today's date, and
returns a few findings about the open closet. Each finding has a `title`,
whether there is `enough` history for its numbers to mean something, and a
`sentence` the owner reads first, naming their own items. When there is too
little history the sentence says so instead of showing numbers. The same
inputs always give the same answer. Your nines and what was spent carry
numbers only; the page puts them into words (`frontend/src/insights.ts`), so
money is said in one place (`frontend/src/spend.ts`).

This is not the gap analysis (`gaps.py`), which says what to buy; this says
how what is owned is being used. Archived items are left out; items in the
laundry count, and so do items away, though "not worn" leaves them out while
they are away (nothing nudges you to wear a suit at the cleaner's).
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from . import gaps, vocab
from .vocab import day_words

# ------------------------------------------------------------------ money
# Prices are stored in cents as the owner typed them, in their own currency (US dollars: see DECISIONS,
# "Before phase 0"). Nothing is converted; the symbol is the one the price field shows.
CURRENCY = "$"

# ------------------------------------------------------------------ cost per wear
CPW_LIST = 3                   # the best and the worst list this many pieces each
CPW_MIN_CLOSET_WEARS = 5       # the closet's own cost per wear needs at least this many wears of pieces with a price

# ------------------------------------------------------------------ never worn
RECENT_DAYS = 30               # an item added fewer than this many days ago is left out: it has not had its chance yet
NEVER_MIN_LOG_WEARS = 10       # fewer wears than this in the whole log and "not worn" says nothing yet
NEVER_MIN_SEASON_DAYS = 7      # an item is only listed once this many days of its season have passed while it could be worn
                               # (since it was added, or since the log began if that was later)

# ------------------------------------------------------------------ not worn for a long time
NEGLECT_DAYS = 90              # days of its own season since an item was last worn before it counts as not worn for a long time

# ------------------------------------------------------------------ seasons
# The months each season's clothes are worn in, for New York (the owner's home, see DECISIONS "Before phase 0").
# April and October belong to both: either kind is worn then, so neither is called neglected for sitting them out.
# "all" (or no season) is every month. A winter coat last worn in March has had no days of its season by August.
SEASON_MONTHS = {
    "warm": frozenset({4, 5, 6, 7, 8, 9, 10}),
    "cool": frozenset({10, 11, 12, 1, 2, 3, 4}),
}

# ------------------------------------------------------------------ worn most
MOST_WINDOWS = (30, 90, None)  # the last 30 days, the last 90 days, and all time (None)
MOST_LIST = 5                  # pieces listed per window
MOST_MIN_WEARS = 5             # a window with fewer wears than this says so instead of ranking

# ------------------------------------------------------------------ Your nines
NINES = 9                      # the pieces worn most in each window of MOST_WINDOWS, as a three-by-three square

# ------------------------------------------------------------------ what your clothes cost you
SPENT_MIN_PIECES = 3           # what was spent is said once at least this many pieces have both a price and a date bought
EARNED_MIN_WEARS = 3           # a piece with a price has "earned" it once worn this many times; fewer, and it has not yet
EARNED_LIST = 3                # pieces listed as having earned their price, and as not having earned it yet

# ------------------------------------------------------------------ how wears are spread within a kind of clothing
SPREAD_WINDOW_DAYS = 90        # the spread is read from the last this many days
SPREAD_MIN_PIECES = 2          # a category needs at least this many pieces to have a spread
SPREAD_MIN_WEARS = 5           # and at least this many wears in the window
SPREAD_MOST = 0.8              # "doing the work": the fewest pieces that together have this share of the wears...
SPREAD_FEW = 0.5               # ...and when they are at most this share of the category's pieces, a few do all the work

# ------------------------------------------------------------------ what the closet is made of
MAKEUP_FIELDS = ("category", "color", "formality", "season")
MAKEUP_WINDOW_DAYS = 90        # "in use" means worn in the last this many days
MAKEUP_MIN_WEARS = 10          # fewer wears than this in the log and the share in use is not shown

NO_LOG = "Nothing has been recorded as worn yet. Use “Wore it today” on an item, or “I'm wearing this” on Today."

CATEGORY_PLURAL = {
    "tee": "T-shirts", "shirt": "Shirts", "polo": "Polos", "sweater": "Sweaters", "hoodie": "Hoodies", "jacket": "Jackets",
    "coat": "Coats", "jeans": "Jeans", "trousers": "Trousers", "shorts": "Shorts", "sneakers": "Sneakers", "boots": "Boots",
    "dress_shoes": "Dress shoes", "sandals": "Sandals", "bag": "Bags", "belt": "Belts", "hat": "Hats", "scarf": "Scarves",
    "other": "Other things",
}
CATEGORY_WORD = {"tee": "T-shirt", "dress_shoes": "dress shoes", "other": "item"}


# ====================================================================== the closet as read here
@dataclass
class _Piece:
    id: str
    name: str                 # as shown after "your", as the owner wrote it: "Grey wool trousers", "New Balance 990"
    category: str | None
    color: str | None
    formality: str | None
    season: str | None
    price: int | None         # cents
    added: date | None
    acquired: date | None = None   # the date bought, as the owner gave it on the item's page
    wears: list[date] = field(default_factory=list)   # oldest first, one per day
    everyday: bool = True     # one Today offers (gaps.everyday): only these are ever "not worn"
    away: bool = False        # at the cleaner's, at the tailor's or lent out: still owned, never "not worn" meanwhile

    @property
    def last(self) -> date | None:
        return self.wears[-1] if self.wears else None

    def worn_since(self, start: date | None) -> int:
        return len(self.wears) if start is None else sum(1 for d in self.wears if d >= start)


@dataclass
class _Log:
    wears: int                # every wear in the log (archived items' too), up to today
    first: date | None        # the day of the first wear: when the owner began recording
    days: int                 # days from the first wear to today
    last: date | None = None  # the day of the last wear: when the owner last recorded one


def _date(value: object) -> date | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _get(row: object, key: str):
    try:
        return row[key]   # a dict or an sqlite3.Row
    except (KeyError, IndexError, TypeError):
        return None


def _display_name(row) -> str:
    name = _get(row, "name")
    if isinstance(name, str) and name.strip():
        return " ".join(name.split())   # as the owner wrote it: brands and places keep their capitals
    color, category = _get(row, "color"), _get(row, "category")
    words = [str(color).replace("_", " ") if color in vocab.COLOR else "",
             CATEGORY_WORD.get(category, str(category).replace("_", " ")) if category in vocab.CATEGORY else "item"]
    return " ".join(w for w in words if w)


def _closet(items: Iterable[object], wears: Iterable[object], today: date) -> tuple[list[_Piece], _Log]:
    pieces: dict[str, _Piece] = {}
    known: set[str] = set()
    for row in items:
        item_id = _get(row, "id")
        if not isinstance(item_id, str) or not item_id:
            continue
        known.add(item_id)
        if _get(row, "status") not in (None, "active"):
            continue
        price = _get(row, "price_cents")
        pieces[item_id] = _Piece(
            id=item_id, name=_display_name(row),
            category=_get(row, "category") if _get(row, "category") in vocab.CATEGORY else None,
            color=_get(row, "color") if _get(row, "color") in vocab.COLOR else None,
            formality=_get(row, "formality") if _get(row, "formality") in vocab.FORMALITY else None,
            season=_get(row, "season") if _get(row, "season") in vocab.SEASON else None,
            price=price if isinstance(price, int) and not isinstance(price, bool) and price >= 0 else None,
            added=_date(_get(row, "created_at")), acquired=_date(_get(row, "acquired_on")),
            everyday=gaps.everyday({"kind": _get(row, "kind")}), away=bool(_get(row, "away")))
    days: dict[str, set[date]] = {}
    for w in wears:
        item_id, day = _get(w, "item_id"), _date(_get(w, "worn_on"))
        if item_id in known and day is not None and day <= today:
            days.setdefault(item_id, set()).add(day)
    every = [d for s in days.values() for d in s]
    first = min(every) if every else None
    for item_id, s in days.items():
        if item_id in pieces:
            pieces[item_id].wears = sorted(s)
    ordered = sorted(pieces.values(), key=lambda p: p.id)
    return ordered, _Log(wears=len(every), first=first, days=(today - first).days if first else 0,
                         last=max(every) if every else None)


# ====================================================================== words
def money(cents: int) -> str:
    """"$45", "$45.50", "$1,040" from cents."""
    whole, part = divmod(cents, 100)
    return f"{CURRENCY}{whole:,}" + (f".{part:02d}" if part else "")


def per_wear_money(cents: int) -> str:
    """Always with cents: "$2.40", "$12.00"."""
    whole, part = divmod(cents, 100)
    return f"{CURRENCY}{whole:,}.{part:02d}"


def _n(n: int, word: str, plural: str | None = None) -> str:
    return f"{n} {word if n == 1 else (plural or word + 's')}"


def _join(words: list[str]) -> str:
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} and {words[-1]}"


def _your(pieces: list[_Piece], capital: bool = False, small: bool = False) -> str:
    """ "your White canvas sneakers"; with `small`, each name as the middle of a sentence writes it ("your white canvas
    sneakers", but "your GANT polo"), as the outfit rules' reasons do."""
    names = [p.name[0].lower() + p.name[1:] if small and len(p.name) > 1 and not p.name[1].isupper() else p.name for p in pieces]
    return ("Your " if capital else "your ") + _join(names)


def _ago(days: int) -> str:
    return "today" if days == 0 else ("yesterday" if days == 1 else f"{days} days ago")


def _quiet(log: _Log, today: date, window: int) -> bool:
    """Whether nothing at all was recorded in the last `window` days: the log stopped, not the wearing."""
    return log.last is not None and (today - log.last).days >= window


def _quiet_words(log: _Log) -> str:
    assert log.last is not None
    return f"Nothing has been recorded as worn since {day_words(log.last)}."


def _window_words(days: int | None) -> str:
    return f"in the last {days} days" if days else "since you began recording what you wear"


def _share(part: int, whole: int) -> int:
    """A whole percentage, rounded half up (the same on every machine)."""
    return (200 * part + whole) // (2 * whole) if whole else 0


def _per_wear(p: _Piece) -> int:
    """Cents a wear, rounded half up."""
    n = len(p.wears)
    return (2 * p.price + n) // (2 * n)


# ====================================================================== seasons
def season_days(after: date, today: date, season: str | None) -> int:
    """How many days after `after`, up to and including `today`, fall in the months the season's clothes are worn."""
    if after >= today:
        return 0
    months = SEASON_MONTHS.get(season or "all")
    if months is None:
        return (today - after).days
    count, d = 0, after + timedelta(days=1)
    while d <= today:
        following = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
        end = min(following - timedelta(days=1), today)
        if d.month in months:
            count += (end - d).days + 1
        d = following
    return count


# ====================================================================== the findings
def _cost_per_wear(pieces: list[_Piece]) -> dict:
    out = {"title": "Cost per wear", "enough": False, "closet": None, "best": [], "worst": [], "not_worn": []}
    priced = [p for p in pieces if p.price is not None]
    if not priced:
        return {**out, "sentence": "Add what you paid on an item's page to see what each wear of it costs."}
    worn = [p for p in priced if p.wears]

    def entry(p: _Piece) -> dict:
        c = _per_wear(p)
        return {"id": p.id, "price_cents": p.price, "wears": len(p.wears), "per_wear_cents": c,
                "sentence": f"{_your([p], True)} cost {per_wear_money(c)} a wear over {_n(len(p.wears), 'wear')}."}

    # with only a few pieces worn, half are the best and the rest the worst
    best = sorted(worn, key=lambda p: (_per_wear(p), -len(p.wears), p.name.lower(), p.id))[:min(CPW_LIST, (len(worn) + 1) // 2)]
    taken = {p.id for p in best}
    worst = sorted((p for p in worn if p.id not in taken), key=lambda p: (-_per_wear(p), len(p.wears), p.name.lower(), p.id))[:CPW_LIST]
    out["best"], out["worst"] = [entry(p) for p in best], [entry(p) for p in worst]
    out["not_worn"] = [{"id": p.id, "price_cents": p.price, "wears": 0, "per_wear_cents": None,
                        "sentence": f"Not worn yet: {_your([p])}, {money(p.price)}."}
                       for p in sorted((p for p in priced if not p.wears), key=lambda p: (-p.price, p.name.lower(), p.id))]
    spent, wears = sum(p.price for p in priced), sum(len(p.wears) for p in priced)
    if wears == 0:
        sentence = ("The one piece with a price has not been worn yet, so it has no cost per wear." if len(priced) == 1 else
                    f"None of the {len(priced)} pieces with a price has been worn yet, so there is no cost per wear to show.")
        return {**out, "sentence": sentence}
    if wears < CPW_MIN_CLOSET_WEARS:
        return {**out, "sentence": f"Pieces with a price have been worn {_n(wears, 'time')} so far. The closet's cost per wear "
                                   f"shows once they have been worn {CPW_MIN_CLOSET_WEARS} times."}
    per = (2 * spent + wears) // (2 * wears)
    out["closet"] = {"pieces": len(priced), "spent_cents": spent, "wears": wears, "per_wear_cents": per}
    whom = "the one piece with a price" if len(priced) == 1 else f"the {len(priced)} pieces with a price"
    return {**out, "enough": True,
            "sentence": f"You paid {money(spent)} for {whom} and have worn {'it' if len(priced) == 1 else 'them'} "
                        f"{_n(wears, 'time')}: {per_wear_money(per)} a wear."}


def _never_worn(pieces: list[_Piece], log: _Log, today: date) -> dict:
    out = {"title": "Not worn yet", "enough": False, "items": []}
    if log.wears == 0:
        return {**out, "sentence": NO_LOG}
    if log.wears < NEVER_MIN_LOG_WEARS:
        return {**out, "sentence": f"Record what you wear for a while longer: pieces you never wear show here once "
                                   f"{NEVER_MIN_LOG_WEARS} wears are recorded ({log.wears} so far)."}
    found, early = [], 0
    for p in pieces:
        if p.wears or not p.everyday or p.away or (p.added is not None and (today - p.added).days < RECENT_DAYS):
            continue
        since = max(p.added, log.first) if p.added else log.first
        if season_days(since, today, p.season) < NEVER_MIN_SEASON_DAYS:
            early += 1   # too early to say: not listed, and not counted as worn either
            continue
        sentence = (f"Not worn since you added it on {day_words(since)}." if p.added and p.added > log.first else
                    f"Not worn since you began recording what you wear, on {day_words(since)}.")
        found.append((since, p, sentence))
    found.sort(key=lambda x: (x[0], x[1].name.lower(), x[1].id))
    out["items"] = [{"id": p.id, "since": since.isoformat(), "sentence": s} for since, p, s in found]
    one = early == 1
    if not found and not early:
        sentence = f"Everything you have had for more than {RECENT_DAYS} days has been worn at least once."
    elif not found:
        sentence = (f"{_n(early, 'piece')} {'has' if one else 'have'} not been worn yet, but it is too early to say: you began "
                    f"recording what you wear {_ago(log.days)}, and {'it shows' if one else 'they show'} here once "
                    f"{NEVER_MIN_SEASON_DAYS} days of {'its' if one else 'their'} season have passed.")
    else:
        # the headline claims only what is true of every piece it counts
        has = "has" if len(found) == 1 else "have"
        if all(since == log.first for since, _, _ in found):
            said = f"not been worn since you began recording what you wear, {_ago(log.days)}"
        elif len(found) == 1:
            said = f"not been worn in the {_n((today - found[0][0]).days, 'day')} since you added it"
        else:
            said = f"not been worn for at least {_n(min((today - since).days for since, _, _ in found), 'day')} each"
        sentence = f"{_n(len(found), 'piece')} {has} {said}."
        if early:
            sentence += (f" {early} more {'is' if one else 'are'} left out until enough of {'its' if one else 'their'} "
                         "season has passed.")
    return {**out, "enough": True, "sentence": sentence}


def _not_worn_lately(pieces: list[_Piece], log: _Log, today: date) -> dict:
    out = {"title": "Not worn for a long time", "enough": False, "items": []}
    if log.wears == 0:
        return {**out, "sentence": NO_LOG}
    if log.days < NEGLECT_DAYS:
        return {**out, "sentence": f"You began recording what you wear {_ago(log.days)}. Pieces left unworn for "
                                   f"{NEGLECT_DAYS} days of their season show here once you have recorded that long."}
    if _quiet(log, today, NEGLECT_DAYS):
        return {**out, "sentence": f"{_quiet_words(log)} Pieces left unworn show here again once you record what you "
                                   "wear."}
    found = []
    for p in pieces:
        if not p.wears or not p.everyday or p.away:
            continue
        n = season_days(p.last, today, p.season)
        if n >= NEGLECT_DAYS:
            found.append((n, p))
    found.sort(key=lambda x: (-x[0], x[1].name.lower(), x[1].id))
    out["items"] = [{"id": p.id, "last_worn": p.last.isoformat(), "season_days": n,
                     "sentence": f"Last worn on {day_words(p.last)}; {n} days of its season have passed since."} for n, p in found]
    if not found:
        sentence = f"Everything you have worn has been worn again within {NEGLECT_DAYS} days of its season."
    else:
        sentence = (f"{_n(len(found), 'piece')} you have worn before {'has' if len(found) == 1 else 'have'} not been worn "
                    f"for {NEGLECT_DAYS} days of {'its' if len(found) == 1 else 'their'} season or more.")
    return {**out, "enough": True, "sentence": sentence}


def _worn_most(pieces: list[_Piece], log: _Log, today: date) -> dict:
    windows = []
    for days in MOST_WINDOWS:
        start = today - timedelta(days=days - 1) if days else None
        title = f"Last {days} days" if days else "All time"
        counted = [(p.worn_since(start), p) for p in pieces]
        total = sum(n for n, _ in counted)
        w = {"days": days, "title": title, "enough": False, "wears": total, "items": []}
        if log.wears == 0:
            windows.append({**w, "sentence": NO_LOG})
            continue
        if total < MOST_MIN_WEARS:
            said = f"Only {_n(total, 'wear')}" if total else "No wears"
            windows.append({**w, "sentence": f"{said} {_window_words(days)}. The pieces worn most show once there are "
                                             f"{MOST_MIN_WEARS}."})
            continue
        ranked = sorted(((n, p) for n, p in counted if n), key=lambda x: (-x[0], -x[1].last.toordinal(), x[1].name.lower(), x[1].id))
        top = ranked[0][0]
        level = sum(1 for n, _ in ranked if n == top)
        ranked = ranked[:MOST_LIST]
        tied = [p for n, p in ranked if n == top]
        sentence = f"Worn most {_window_words(days)}: {_your(tied)}, {_n(top, 'time')}{' each' if len(tied) > 1 else ''}"
        more = level - len(tied)   # pieces worn as often that did not fit in the list
        sentence += f", and {more} more worn as often." if more else "."
        if days and log.days < days - 1:
            sentence += f" You began recording what you wear {_ago(log.days)}."
        windows.append({**w, "enough": True, "sentence": sentence, "items": [{"id": p.id, "wears": n} for n, p in ranked]})
    shown = next((w for w in windows if w["enough"]), windows[-1])
    return {"title": "Worn most", "enough": shown["enough"], "sentence": shown["sentence"], "windows": windows}


def _spread(pieces: list[_Piece], log: _Log, today: date) -> dict:
    out = {"title": "How the wearing is shared", "enough": False, "days": SPREAD_WINDOW_DAYS, "categories": []}
    if log.wears == 0:
        return {**out, "sentence": NO_LOG}
    start = today - timedelta(days=SPREAD_WINDOW_DAYS - 1)
    by_category: dict[str, list[_Piece]] = {}
    for p in pieces:
        if p.category:
            by_category.setdefault(p.category, []).append(p)
    found = []
    for category, group in by_category.items():
        counted = sorted(((p.worn_since(start), p) for p in group), key=lambda x: (-x[0], x[1].name.lower(), x[1].id))
        total = sum(n for n, _ in counted)
        if len(group) < SPREAD_MIN_PIECES or total < SPREAD_MIN_WEARS:
            continue
        k, running = 0, 0
        while running < SPREAD_MOST * total:
            running += counted[k][0]
            k += 1
        share = _share(running, total)
        few = k / len(group) <= SPREAD_FEW
        label = CATEGORY_PLURAL.get(category, category)
        if few:
            sentence = (f"{label}: {k} of {len(group)} {'gets' if k == 1 else 'get'} {share}% of the wears "
                        f"({_your([p for _, p in counted[:k]], small=True)}).")
        else:
            sentence = f"{label}: worn fairly evenly; it takes {k} of {len(group)} to make up {share}% of the wears."
        found.append({"category": category, "pieces": len(group), "wears": total, "doing_most": k, "share": share,
                      "kind": "few" if few else "even", "sentence": sentence,
                      "items": [{"id": p.id, "wears": n} for n, p in counted]})
    if not found:
        return {**out, "sentence": f"Not enough wears yet to see how they are shared: a kind of clothing needs at least "
                                   f"{SPREAD_MIN_PIECES} pieces and {SPREAD_MIN_WEARS} wears in the last {SPREAD_WINDOW_DAYS} days."}
    found.sort(key=lambda c: (c["kind"] != "few", -c["wears"], c["category"]))
    few = sum(1 for c in found if c["kind"] == "few")
    if few:
        sentence = (f"In {'one kind' if few == 1 else f'{few} kinds'} of clothing, a few pieces do most of the wearing "
                    f"(the last {SPREAD_WINDOW_DAYS} days).")
    else:
        sentence = f"Within each kind of clothing, the wearing is shared fairly evenly (the last {SPREAD_WINDOW_DAYS} days)."
    return {**out, "enough": True, "sentence": sentence, "categories": found}


def _makeup(pieces: list[_Piece], log: _Log, today: date) -> dict:
    start = today - timedelta(days=MAKEUP_WINDOW_DAYS - 1)
    in_use = {p.id for p in pieces if p.worn_since(start)}
    by: dict[str, list[dict]] = {}
    for f in MAKEUP_FIELDS:
        counts: Counter = Counter(getattr(p, f) for p in pieces)
        worn: Counter = Counter(getattr(p, f) for p in pieces if p.id in in_use)
        by[f] = [{"value": v, "count": n, "worn": worn[v]}
                 for v, n in sorted(counts.items(), key=lambda x: (-x[1], x[0] is None, x[0] or ""))]
    out = {"title": "What your closet is made of", "enough": False, "pieces": len(pieces), "worn": None,
           "days": MAKEUP_WINDOW_DAYS, "by": by}
    if not pieces:
        return {**out, "sentence": "There is nothing in this closet yet."}
    if log.wears < MAKEUP_MIN_WEARS:
        return {**out, "sentence": f"You have {_n(len(pieces), 'piece')}. How much of it is in use shows once "
                                   f"{MAKEUP_MIN_WEARS} wears are recorded ({log.wears} so far)."}
    if _quiet(log, today, MAKEUP_WINDOW_DAYS):
        return {**out, "sentence": f"You have {_n(len(pieces), 'piece')}. {_quiet_words(log)} How much of it is in use "
                                   "shows again once you record what you wear."}
    n = len(in_use)
    if log.days >= MAKEUP_WINDOW_DAYS - 1:
        worn = f"{'was' if n == 1 else 'were'} worn in the last {MAKEUP_WINDOW_DAYS} days"
    else:
        worn = f"{'has' if n == 1 else 'have'} been worn since you began recording what you wear, {_ago(log.days)}"
    return {**out, "enough": True, "worn": n,
            "sentence": f"You have {_n(len(pieces), 'piece')}; {n} of them ({_share(n, len(pieces))}%) {worn}."}


def _nines(pieces: list[_Piece], log: _Log, today: date) -> dict:
    """The nine pieces worn most in each window, every piece counted (what is worn at home too: it is what was worn).

    Ties go to the piece worn more recently, then by name, as for worn most. A window with fewer than nine says how many
    were worn; one with none says why: nothing recorded yet, or nothing recorded since a day before the window."""
    windows = []
    for days in MOST_WINDOWS:
        start = today - timedelta(days=days - 1) if days else None
        ranked = sorted(((p.worn_since(start), p) for p in pieces if p.worn_since(start)),
                        key=lambda x: (-x[0], -x[1].last.toordinal(), x[1].name.lower(), x[1].id))
        if log.wears == 0:
            sentence = NO_LOG
        elif not ranked:
            sentence = _quiet_words(log) if log.last is not None and (start is None or log.last < start) else \
                f"Nothing has been recorded as worn {_window_words(days)}."
        elif len(ranked) < NINES:
            sentence = (f"Only {_n(len(ranked), 'piece')} {'was' if len(ranked) == 1 else 'were'} worn {_window_words(days)}."
                        if days else
                        f"Only {_n(len(ranked), 'piece')} {'has' if len(ranked) == 1 else 'have'} been worn {_window_words(days)}.")
        else:
            sentence = None
        windows.append({"days": days, "pieces": len(ranked), "sentence": sentence,
                        "items": [{"id": p.id, "wears": n} for n, p in ranked[:NINES]]})
    return {"title": "Your nines", "windows": windows}


def _wishlist_cost(wishlist: Iterable[dict] | None) -> dict:
    """What the open wishes would cost at today's prices: each wish at the lowest price of the finds still on sale in
    one currency (the currency of its first find given), summed by currency and never across currencies."""
    totals: dict[str, dict] = {}
    wishes = unpriced = 0
    for w in wishlist or ():
        wishes += 1
        prices = [(float(f["price"]), str(f["currency"])) for f in (w.get("prices") or ())
                  if isinstance(f.get("price"), (int, float)) and not isinstance(f.get("price"), bool) and f["price"] >= 0
                  and isinstance(f.get("currency"), str) and f["currency"]]
        if not prices:
            unpriced += 1
            continue
        currency = prices[0][1]
        cents = min(int((Decimal(str(p)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) for p, c in prices if c == currency)
        t = totals.setdefault(currency, {"currency": currency, "cents": 0, "wishes": 0})
        t["cents"] += cents
        t["wishes"] += 1
    return {"wishes": wishes, "unpriced": unpriced,
            "totals": sorted(totals.values(), key=lambda t: (-t["wishes"], t["currency"]))}


def _spending(pieces: list[_Piece], today: date, wishlist: Iterable[dict] | None) -> dict:
    """What the closet cost, from each piece's price and the date it was bought: by year, the pieces that have earned
    their price and those that have not yet, and what the wishlist would cost. Prices are in the one currency the
    price field shows (CURRENCY); the wishlist's are in each shop's."""
    priced = [p for p in pieces if p.price is not None]
    dated = [p for p in priced if p.acquired is not None]
    unpriced = [p for p in pieces if p.price is None]
    years: dict[int, dict] = {}
    for p in dated:
        y = years.setdefault(p.acquired.year, {"year": p.acquired.year, "spent_cents": 0, "pieces": 0})
        y["spent_cents"] += p.price
        y["pieces"] += 1
    earned = sorted((p for p in priced if len(p.wears) >= EARNED_MIN_WEARS),
                    key=lambda p: (_per_wear(p), -len(p.wears), p.name.lower(), p.id))[:EARNED_LIST]
    not_earned = sorted((p for p in priced if len(p.wears) < EARNED_MIN_WEARS),
                        key=lambda p: (-p.price, len(p.wears), p.name.lower(), p.id))[:EARNED_LIST]
    # the piece to fill in first: the one worn most (its cost per wear means the most) among those with no price, or,
    # when every piece has one, among those with no date bought
    missing = unpriced or [p for p in priced if p.acquired is None]
    first = min(missing, key=lambda p: (-len(p.wears), p.name.lower(), p.id)) if missing else None
    return {
        "currency": CURRENCY, "year": today.year, "pieces": len(pieces), "priced": len(priced), "dated": len(dated),
        "unpriced": len(unpriced), "first_missing": first.id if first else None,
        "enough": len(dated) >= SPENT_MIN_PIECES,
        "by_year": sorted(years.values(), key=lambda y: -y["year"]),
        "earned": [{"id": p.id, "price_cents": p.price, "wears": len(p.wears), "per_wear_cents": _per_wear(p)} for p in earned],
        "not_earned": [{"id": p.id, "price_cents": p.price, "wears": len(p.wears)} for p in not_earned],
        "wishlist": _wishlist_cost(wishlist),
    }


def find_insights(items: Iterable[object], wears: Iterable[object], today: date, wishlist: Iterable[dict] | None = None) -> dict:
    """A few findings about how the open closet is used, each with a sentence first.

    `wishlist` is the open wishes, each {wish_id, prices: [{price, currency}]}: the prices of its finds still on sale,
    after any checkout code, the newest find first.

    Returns {today, log: {wears, first, last, days}, cost_per_wear, never_worn, not_worn_lately, worn_most, nines,
    spending, spread, makeup}.
    """
    pieces, log = _closet(items if items is not None else (), wears if wears is not None else (), today)
    return {
        "today": today.isoformat(),
        "log": {"wears": log.wears, "first": log.first.isoformat() if log.first else None,
                "last": log.last.isoformat() if log.last else None, "days": log.days},
        "cost_per_wear": _cost_per_wear(pieces),
        "never_worn": _never_worn(pieces, log, today),
        "not_worn_lately": _not_worn_lately(pieces, log, today),
        "worn_most": _worn_most(pieces, log, today),
        "nines": _nines(pieces, log, today),
        "spending": _spending(pieces, today, wishlist),
        "spread": _spread(pieces, log, today),
        "makeup": _makeup(pieces, log, today),
    }

