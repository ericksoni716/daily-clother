"""How far the work on each item has got: one progress value, worked out from the item's own columns.

A photo becomes an item in up to three steps:

1. **Cutting out**: the background removed, on this computer (`jobs.py`).
2. **Describing and drawing**: Claude describes it, and the drawing is made from that at once (`tagjobs.py`).
3. **Finishing the drawing**, only for patterned clothes and shoes: the pattern measured from the photo
   (`patjobs.py`), or a shoe's photos sorted into views, traced and drawn by Claude (`shoeviews.py`,
   `tracejobs.py`, `shoedraw.py`).

`of(row)` says which step an item is at, what is happening in plain words, what it waits for and whether a
failure can be tried again. Nothing is stored: every state it reads is already a column on `items`. The words the
page shows for this work live here and nowhere else (the page's `progress.ts` only lays them out).

What the whole program waits on (background removal not set up, Claude out of reach) is not on the item, so the
caller passes it as `Waits`; `GET /api/progress` does, and the item's own summary assumes nothing is in the way.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import shoedraw, shoeviews, spend, tagjobs, tracejobs

OF = 3   # the steps an item can go through

# ---------------------------------------------------------------- the words, in one place
TITLES = {1: "Cutting out", 2: "Describing and drawing", 3: "Finishing the drawing"}

# where each part of the work runs and how long it usually takes
ABOUT = {
    "cutout": "On this computer, in a few seconds.",
    "describing": "By Claude, usually within a minute. The drawing appears as soon as it is described.",
    "pattern": "On this computer, a minute or two.",
    "trace": "On this computer, in a few seconds.",
    "views": "By Claude, in a few seconds.",
    "shoe": "By Claude, four to ten minutes.",
}

CUTTING = "Removing the background"
DESCRIBING = "Claude is describing it"
DESCRIBE_NEXT = "Waiting its turn with Claude"
TRACING = "Tracing the shoe from its photo"
SORTING = "Sorting the shoe's photos into views"
DRAWING = "Drawing the shoe from its photos"
CORRECTING = "Changing the drawing as you asked"
MEASURING = "Measuring the {pattern} from the photo"
PATTERN_WORDS = {"stripe": "stripes", "plaid": "plaid", "floral": "print", "camo": "camouflage", "graphic": "graphic"}

# waiting: what for, in a few words (the line) and in a sentence (why)
WAIT_WORDS = {
    "model": "Waiting until background removal is set up",
    "download": "Waiting while background removal downloads",
    "claude": "Waiting until Claude can be reached",
    "limit": "Waiting for this month's limit to allow it",
    "sign-in": "Waiting for you to sign in to Claude again",
    "you": "Waiting for your answer",
}
WHY = {
    "model": "Background removal, which cuts the clothes out of the photo, isn't set up yet. It starts by itself once "
             "it is.",
    "download": "Background removal, which cuts the clothes out of the photo, is still downloading. It starts by "
                "itself once it is done.",
    "claude": "Claude can't be reached right now. The work goes on by itself once it can.",
    "limit": spend.LIMIT_REACHED,
    "sign-in": tagjobs.SIGN_IN,
    "you": "Nines needs your answer about this shoe's photos before it can carry on.",
}

CUTOUT_FAILED = "The background couldn't be removed"
DESCRIBE_FAILED = "Claude couldn't describe this item"

# the stored notes that say why a shoe's photos or drawing wait for Claude
_NO_ROUTE = {shoeviews.NO_ROUTE, shoedraw.NO_ROUTE, shoedraw.CORRECT_NO_ROUTE}
_LIMIT = {shoeviews.LIMIT, shoedraw.LIMIT, shoedraw.CORRECT_LIMIT}


@dataclass(frozen=True)
class Waits:
    """What the whole program is held up by, which no item's columns say.

    model: the background-removal model's state (`ModelStore.info()`): ready, downloading, missing or failed.
    claude: the describing queue found no way to reach Claude when it last tried."""
    model: str = "ready"
    claude: bool = False


NOTHING = Waits()


def _out(stage: str, step: int, state: str, words: str, *, waiting_for: str | None = None, why: str | None = None,
         error: str | None = None, retry: str | None = None) -> dict:
    """state: working (being done now), queued (next in line; nothing stands in its way), waiting (held up by
    `waiting_for`) or failed. retry: what trying again does (cutout, describe), or None when it cannot be."""
    return {"stage": stage, "step": step, "of": OF, "state": state, "title": TITLES[step], "words": words,
            "about": ABOUT[stage], "waiting_for": waiting_for, "why": why, "error": error,
            "can_retry": retry is not None, "retry": retry}


def _waiting(stage: str, step: int, reason: str, why: str | None = None) -> dict:
    return _out(stage, step, "waiting", WAIT_WORDS[reason], waiting_for=reason, why=why or WHY[reason])


def _claude_note(note: str | None) -> str | None:
    """What a stored note on a shoe's photos or drawing says it waits for, if anything."""
    if note in _NO_ROUTE:
        return "claude"
    if note in _LIMIT:
        return "limit"
    return None


def _pattern(row) -> dict | None:
    if row["pattern_state"] not in ("waiting", "working"):
        return None
    words = MEASURING.format(pattern=PATTERN_WORDS.get(row["pattern"], "pattern"))
    return _out("pattern", 3, "working" if row["pattern_state"] == "working" else "queued", words)


def _views(row) -> dict | None:
    state = row["views_state"]
    if state == "asking":
        return _waiting("views", 3, "you")
    if state not in ("waiting", "sorting"):
        return None
    if state == "waiting" and (reason := _claude_note(row["views_error"])):
        return _waiting("views", 3, reason, row["views_error"])
    return _out("views", 3, "working" if state == "sorting" else "queued", SORTING)


def _trace(row) -> dict | None:
    state = row["trace_state"]
    if state not in ("waiting", "working"):
        return None
    return _out("trace", 3, "working" if state == "working" else "queued", TRACING)


def _shoe(row) -> dict | None:
    state = row["drawn_state"]
    if state not in shoedraw.BUSY:
        return None
    words = CORRECTING if shoedraw.correcting(row) else DRAWING
    if state in ("drawing", "correcting"):
        return _out("shoe", 3, "working", words)
    if reason := _claude_note(row["drawn_error"]):
        return _waiting("shoe", 3, reason, row["drawn_error"])
    views = row["views_state"]
    if views == "asking":
        return _waiting("shoe", 3, "you")
    if views not in ("sorted", "waiting", "sorting"):   # the photos could not be sorted: the owner adds or removes one
        return _waiting("shoe", 3, "you", shoedraw.WAIT_UNSORTED)
    return _out("shoe", 3, "queued", words)


_RANK = {"working": 0, "queued": 1, "waiting": 2}


def _finishing(row) -> dict | None:
    """Step 3: the part going furthest right now (working before queued before waiting)."""
    parts = [_pattern(row)]
    if tracejobs.wanted(row["category"]):
        parts += [_trace(row), _views(row), _shoe(row)]
    parts = [p for p in parts if p is not None]
    return min(parts, key=lambda p: _RANK[p["state"]]) if parts else None


def of(row, waits: Waits = NOTHING) -> dict | None:
    """The item's progress, or None when nothing is being done to it and nothing failed on the way.

    {stage, step, of, state, title, words, about, waiting_for, why, error, can_retry, retry}: stage is cutout,
    describing, pattern, trace, views or shoe (a shoe drawn by Claude); step is 1 to 3 of `of`; title is the step's
    name and words what is happening now; about where it runs and how long it takes; waiting_for is model, download,
    claude, limit, sign-in or you (an answer from the owner), with why as a sentence."""
    cutout = row["cutout_state"]
    if cutout == "failed":
        return _out("cutout", 1, "failed", CUTOUT_FAILED, error=row["cutout_error"], retry="cutout")
    if cutout in ("pending", "processing"):
        if cutout == "pending" and waits.model != "ready":
            return _waiting("cutout", 1, "download" if waits.model == "downloading" else "model")
        return _out("cutout", 1, "working" if cutout == "processing" else "queued", CUTTING)
    tag = row["tag_state"]
    if tag == "failed":
        return _out("describing", 2, "failed", DESCRIBE_FAILED, error=row["tag_error"], retry="describe")
    if tag == "working":
        return _out("describing", 2, "working", DESCRIBING)
    if tag == "waiting":
        note = row["tag_error"]
        if note == spend.LIMIT_REACHED:
            return _waiting("describing", 2, "limit")
        if note == tagjobs.SIGN_IN:
            return _waiting("describing", 2, "sign-in")
        if waits.claude:
            return _waiting("describing", 2, "claude")
        return _out("describing", 2, "queued", DESCRIBE_NEXT)
    return _finishing(row)


def busy(progress: dict | None) -> bool:
    """Still on its way (working, queued or waiting), as against done or failed."""
    return progress is not None and progress["state"] != "failed"


# the items any part of whose work is under way, found without reading every item
_UNDER_WAY = (
    "cutout_state IN ('pending', 'processing') OR tag_state IN ('waiting', 'working') "
    "OR pattern_state IN ('waiting', 'working') "
    f"OR (category IN {tracejobs.SHOES} AND (trace_state IN ('waiting', 'working') "
    "OR views_state IN ('waiting', 'sorting', 'asking') OR drawn_state IN ('waiting', 'drawing', 'correcting')))"
)


def listing(conn, waits: Waits = NOTHING) -> dict:
    """`GET /api/progress`: the items being worked on (oldest first), each with its progress, its name and its
    small picture; how many are going ahead and how many wait; and, when items wait for something the owner can see
    to (the monthly limit, signing in, background removal), why, once."""
    out, why = [], None
    rows = conn.execute(
        "SELECT i.*, (SELECT coalesce(p.cutout_thumb_path, p.thumb_path) FROM photos p WHERE p.item_id = i.id "
        "ORDER BY p.kind = 'front' DESC, p.created_at LIMIT 1) AS thumb "
        f"FROM items i WHERE {_UNDER_WAY} ORDER BY i.created_at, i.id").fetchall()
    for row in rows:
        p = of(row, waits)
        if not busy(p):
            continue
        out.append({"id": row["id"], "name": row["name"], "category": row["category"], "color": row["color"],
                    "status": row["status"], "thumb_url": f"/media/{row['thumb']}" if row["thumb"] else None,
                    "progress": p})
        if why is None and p["state"] == "waiting" and p["waiting_for"] in ("limit", "sign-in", "model", "download"):
            why = p["why"]
    waiting = sum(1 for i in out if i["progress"]["state"] == "waiting")
    return {"items": out, "going": len(out) - waiting, "waiting": waiting, "why": why}
