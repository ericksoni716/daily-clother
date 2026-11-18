"""What reaching Claude costs: a record of every call, the API key's monthly limit, and estimates.

Every call is written to the real closet's database (`claude_calls`): when, what
for, which route and model, the tokens in and out as reported, and the cost
worked out from the price table in `tagger/models.json`. Plan calls are counted
at no cost. Nothing about a photo, the prompt or an answer is kept.

The limit is in US dollars, the currency of the price table, for the calendar
month in the computer's local time; it is kept in the program's settings with
the switch that allows the API key. Before each API request the month's spend
plus a careful estimate of that request is compared with the limit, and the
request is not made if it could go over. Several workers can ask at once (describing, landmarks, the pieces in
a photo, a shoe's photos sorted into views, a shoe drawn from its photos or its drawing changed from the owner's
note, "Would this work?", shopping), so the
estimate of each request on its way is held against the limit until it comes back or fails: together they cannot go
over either.
"""
from __future__ import annotations

import threading
from datetime import datetime

from . import db
from .config import Config
from .state import State
from .tagger.correcting import MAX_TOKENS as CORRECT_MAX_TOKENS
from .tagger.dayread import MODEL as STYLING_MODEL
from .tagger.garments import MODEL as GARMENTS_MODEL
from .tagger.shoedrawing import MAX_TOKENS as DRAW_MAX_TOKENS
from .tagger.shoedrawing import MODEL as DRAW_MODEL
from .tagger.shopping import MAX_TOKENS as SHOP_MAX_TOKENS
from .tagger.stylist import MAX_TOKENS as STYLE_MAX_TOKENS
from .tagger.tagging import CONFIG, MAX_TOKENS, CapReached, RouteUnavailable
from .tagger.views import MODEL as VIEWS_MODEL

PURPOSE_TAG = "tag_item"
PURPOSE_CORRECT = "correct_item"   # reading the owner's sentence about an item (`tagger/correcting.py`)
PURPOSE_LANDMARKS = "item_landmarks"   # where a patterned top's buttons, neck, hem and sleeves are (`tagger/landmarks.py`)
PURPOSE_SHOP = "shop_find"            # searching shops for a wish (`tagger/shopping.py`)
PURPOSE_PRICES = "shop_prices"        # looking up the prices of a wish's finds again
PURPOSE_GARMENTS = "find_garments"    # where each piece is in a photo of several (`tagger/garments.py`)
PURPOSE_VIEWS = "sort_views"          # which view each photo of a shoe shows (`tagger/views.py`)
PURPOSE_SORT_ADD = "sort_add"         # what each photo chosen on Add shows: a piece, several, a shoe (`tagger/addsort.py`)
PURPOSE_DAY = "read_day"              # the day in the owner's words: where, when, the hours outside (`tagger/dayread.py`)
PURPOSE_STYLE = "style_outfits"       # Claude choosing the day's outfits (`tagger/stylist.py`, `closet/stylejobs.py`)
PURPOSE_DRAW = "draw_shoe"            # a shoe drawn from its photos, and its checks (`tagger/shoedrawing.py`)
PURPOSE_CORRECT_DRAWING = "correct_drawing"   # a shoe's drawing changed from the owner's note, and its checks
PRICES_CHECKED: str = CONFIG.get("prices_checked", "")
TAGGING_MODEL: str = CONFIG["roles"]["tagging"]
DESCRIBING_MODEL: str = CONFIG["roles"]["describing"]   # the description call (`tagjobs.MODEL`)
SUGGESTED_CAP_USD = 5.0     # see DECISIONS, "Spend cap for the API key"
MAX_CAP_USD = 1000.0        # a typing slip should not allow a large bill
HISTORY_MONTHS = 12

# A careful upper bound on one request to describe an item: the prompt and the whole answer form as a tool (about
# 40,000 characters with the cloth's surface and its lettering, counted at 1 token for every character pair, with room
# for what the API adds for a tool), each photo at no more than 1024 px a side (about 1,400 tokens by Anthropic's rule
# of width x height / 750, rounded up), and the longest answer the request allows. (8,000 while the form went as a
# compiled structured output; 18,000 before the surface was asked for; 20,000 before the lettering.)
TEXT_TOKENS = 21000
IMAGE_TOKENS = 1600
# Reading a correction: the longest prompt the app writes (a 500-character sentence, a shirt's description and every
# value it may take, with the longest cloth and lettering, about 18,000 characters with the schema since the cloth was
# added (7,000 before); counted at 1 token for every character pair, then the whole doubled), a photo when one is sent,
# and the longest answer the request allows (`correcting.MAX_TOKENS`).
CORRECT_TEXT_TOKENS = 19000
# Sorting a shoe's photos into views: the prompt with the answer's schema (about 3,000 characters, counted at 1 token
# for every character pair, then the whole doubled and rounded up), each photo at no more than 1024 px a side, and the
# longest answer the request allows (`correcting.MAX_TOKENS`; the answer itself is a few lines).
VIEWS_TEXT_TOKENS = 4000
# Drawing a shoe, or checking its drawing: the longest prompt with the answer's schema (the brief, the worked
# examples' SVG or, for a check, the sheet and two drawings of at most `drawn.MAX_CHARS` characters each: under
# 110,000 characters in all, counted at 1 token for every character pair and rounded up), the shoe's photos and the
# example renders or the check render, and the longest answer the request allows, thinking included
# (`shoedrawing.MAX_TOKENS`).
DRAW_TEXT_TOKENS = 55_000
# Changing a shoe's drawing from the owner's note, or checking the change: the longest prompt with the answer's schema
# (the brief, the sheet, the owner's note and their latest earlier notes, and the drawing as it is or as changed, each
# shoe at most `drawn.MAX_CHARS` characters: under 110,000 characters in all, counted as above), the shoe's photos and
# one or two renders (the drawing before the note and after it), and the longest answer the request allows.
CORRECT_DRAW_TEXT_TOKENS = 55_000
# Searching shops: Claude reads the pages its web searches bring back, and reads them again at each step of its
# search, so a request takes in far more than its prompt. A careful upper bound: 300,000 tokens in, the longest
# answer the request allows, and every web search it may make, at the price per search in the price table.
SHOP_INPUT_TOKENS = 300_000
SEARCH_USD: float = CONFIG.get("web_search_per_1000", 10.0) / 1000

LIMIT_REACHED = ("This month's spending limit for the API key has been reached, and your Claude plan can't be used "
                 "right now. It will be described when your plan can be used again, when the new month starts, or if "
                 "you raise the limit in Settings.")


# What each request on its way to the API may cost, by the thread waiting for it (a thread makes one at a time),
# taken from the room left this month until the request is recorded or has failed. One lock for the whole program,
# so two workers cannot both see the same room.
_lock = threading.Lock()
_held: dict[int, float] = {}


def _now() -> datetime:
    """The computer's local time (tests move it)."""
    return datetime.now().astimezone()


def this_month() -> str:
    return _now().strftime("%Y-%m")


def price(model: str) -> dict:
    """The model's prices per million tokens; a model missing from the table is priced as the dearest one."""
    table = CONFIG["models"]
    return table.get(model) or max(table.values(), key=lambda p: p["output"])


# The most a prompt can cost per token over the plain input price: written to the cache (see models.json)
CACHE_WRITE_FACTOR = 1.25


def cost_usd(model: str, input_tokens: int, output_tokens: int, cache_write: int = 0, cache_read: int = 0) -> float:
    """What a call cost. `input_tokens` is the part of the prompt neither written to nor read from the cache, as the
    API reports it; the cached parts are priced on their own."""
    p = price(model)
    return (input_tokens * p["input"] + output_tokens * p["output"]
            + cache_write * p.get("cache_write", p["input"] * CACHE_WRITE_FACTOR)
            + cache_read * p.get("cache_read", p["input"])) / 1_000_000


def _worst(model: str, input_tokens: int, output_tokens: int) -> float:
    """An estimate before a call whose prompt is marked for the cache (describing an item, drawing a shoe and its
    checks): as if the whole prompt were written to it, the dearest way it can go."""
    return cost_usd(model, 0, output_tokens, cache_write=input_tokens)


def estimate_call(photos: int, model: str = DESCRIBING_MODEL) -> float:
    """The most one request to describe an item with this many photos should cost."""
    return _worst(model, TEXT_TOKENS + IMAGE_TOKENS * max(1, photos), MAX_TOKENS)


def estimate_landmarks(photos: int, model: str = TAGGING_MODEL) -> float:
    """The most one request for an item's landmarks should cost: a short prompt and schema, the photo, a short answer."""
    return cost_usd(model, CORRECT_TEXT_TOKENS + IMAGE_TOKENS * max(1, photos), CORRECT_MAX_TOKENS)


def estimate_garments(photos: int, model: str = GARMENTS_MODEL) -> float:
    """The most one request for the boxes around the pieces in a photo should cost: a short prompt and schema, the
    photo, and the longest answer allowed (about twenty boxes fit in it)."""
    return cost_usd(model, CORRECT_TEXT_TOKENS + IMAGE_TOKENS * max(1, photos), CORRECT_MAX_TOKENS)


SORT_ADD_IMAGE_TOKENS = 400   # a photo at most 512 pixels on its longest side (about width × height / 750)


def estimate_sort_add(photos: int, model: str = VIEWS_MODEL) -> float:
    """The most one request to sort the photos chosen on Add should cost: a short prompt and schema, up to ten small
    photos, and the longest answer allowed."""
    return cost_usd(model, VIEWS_TEXT_TOKENS + SORT_ADD_IMAGE_TOKENS * max(1, photos), CORRECT_MAX_TOKENS)


DAY_TEXT_TOKENS = 1500        # the question about the owner's day: instructions, the answer's form and one sentence


def estimate_day(photos: int = 0, model: str = STYLING_MODEL) -> float:
    """The most one request to read the day in the owner's words should cost: a short prompt, no photo, and the
    longest answer allowed (`photos` is always 0; the meter passes it)."""
    return cost_usd(model, DAY_TEXT_TOKENS, CORRECT_MAX_TOKENS)


STYLE_TEXT_TOKENS = 16000     # what the stylist is told for a large closet: the guide, the profile, some 250 pieces


def estimate_style(photos: int = 0, model: str = STYLING_MODEL) -> float:
    """The most one request to choose the day's outfits should cost: a long text and the longest answer allowed.
    The look at the outfits as drawn is priced the same: its text is a third of this and its few small pictures
    (`photos`, about 500 tokens each) fit well inside the rest."""
    return cost_usd(model, STYLE_TEXT_TOKENS, STYLE_MAX_TOKENS)


def estimate_views(photos: int, model: str = VIEWS_MODEL) -> float:
    """The most one request to sort a shoe's photos into views should cost: a short prompt and schema, every photo of
    the shoe (one to six), and the longest answer allowed."""
    return cost_usd(model, VIEWS_TEXT_TOKENS + IMAGE_TOKENS * max(1, photos), CORRECT_MAX_TOKENS)


def estimate_draw(images: int, model: str = DRAW_MODEL) -> float:
    """The most one request to draw a shoe, or to check its drawing, should cost: the brief and the drawings as text,
    every image sent (the shoe's photos and the renders), and the longest answer allowed."""
    return _worst(model, DRAW_TEXT_TOKENS + IMAGE_TOKENS * max(1, images), DRAW_MAX_TOKENS)


def estimate_correct_drawing(images: int, model: str = DRAW_MODEL) -> float:
    """The most one request to change a shoe's drawing from the owner's note, or to check the change, should cost:
    the brief, the note and the drawing as text, every image sent (the shoe's photos and the renders), and the longest
    answer allowed."""
    return _worst(model, CORRECT_DRAW_TEXT_TOKENS + IMAGE_TOKENS * max(1, images), DRAW_MAX_TOKENS)


def estimate_correction(photos: int, model: str = TAGGING_MODEL) -> float:
    """The most one request to read a correction should cost (`photos` is 0 or 1)."""
    return cost_usd(model, CORRECT_TEXT_TOKENS + IMAGE_TOKENS * max(0, photos), CORRECT_MAX_TOKENS)


def estimate_shop(searches: int, model: str = TAGGING_MODEL) -> float:
    """The most one request to search shops should cost, with at most `searches` web searches."""
    return cost_usd(model, SHOP_INPUT_TOKENS, SHOP_MAX_TOKENS) + SEARCH_USD * max(0, searches)


def record(conn, route: str, model: str, input_tokens: int, output_tokens: int, purpose: str = PURPOSE_TAG,
           searches: int = 0, cache_write: int = 0, cache_read: int = 0) -> float:
    """Write down one call; returns what it cost (nothing on the plan route). `searches`: the web searches the API
    made for it, each billed on top of the tokens. `cache_write` / `cache_read`: the prompt's tokens written to or
    read from the cache, priced on their own and counted in the stored input tokens (the whole prompt)."""
    cost = (cost_usd(model, input_tokens, output_tokens, cache_write, cache_read) + SEARCH_USD * max(0, searches)
            if route == "api" else 0.0)
    input_tokens = int(input_tokens or 0) + int(cache_write or 0) + int(cache_read or 0)
    conn.execute("INSERT INTO claude_calls (at, month, purpose, route, model, input_tokens, output_tokens, cost_usd, "
                 "prices_checked) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                 (db.now(), this_month(), purpose, route, model, int(input_tokens or 0), int(output_tokens or 0), cost,
                  PRICES_CHECKED))
    return cost


def spent(conn, month: str | None = None) -> float:
    """What the API key has cost in the month (this month by default)."""
    row = conn.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM claude_calls WHERE month = ? AND route = 'api'",
                       (month or this_month(),)).fetchone()
    return float(row[0])


def history(conn, months: int = HISTORY_MONTHS) -> list[dict]:
    """Month by month, newest first: calls on each route, tokens and what the API key cost."""
    rows = conn.execute(
        "SELECT month, SUM(route = 'api') AS api_calls, SUM(route = 'plan') AS plan_calls, "
        "SUM(CASE WHEN route = 'api' THEN cost_usd ELSE 0 END) AS spent_usd, "
        "SUM(CASE WHEN route = 'api' THEN input_tokens ELSE 0 END) AS input_tokens, "
        "SUM(CASE WHEN route = 'api' THEN output_tokens ELSE 0 END) AS output_tokens "
        "FROM claude_calls GROUP BY month ORDER BY month DESC LIMIT ?", (months,)).fetchall()
    return [{"month": r["month"], "api_calls": r["api_calls"], "plan_calls": r["plan_calls"],
             "spent_usd": round(r["spent_usd"], 6), "input_tokens": r["input_tokens"], "output_tokens": r["output_tokens"]}
            for r in rows]


def waiting(conn) -> dict:
    """The items waiting to be described in this closet, and the most they would cost through the API key,
    each described at the first try."""
    rows = conn.execute(
        "SELECT j.item_id, (SELECT COUNT(*) FROM photos p WHERE p.item_id = j.item_id) AS photos FROM jobs j "
        "WHERE j.kind = 'tag' AND j.state IN ('queued', 'running') GROUP BY j.item_id").fetchall()
    return {"items": len(rows), "photos": sum(max(1, r["photos"]) for r in rows),
            "at_most_usd": round(sum(estimate_call(r["photos"]) for r in rows), 6)}


def cap(state: State) -> float | None:
    value = state.get("tagging_api_cap_usd")
    return float(value) if isinstance(value, (int, float)) and value > 0 else None


def api_allowed(state: State) -> bool:
    """The owner has allowed the API key, with a limit."""
    return bool(state.get("tagging_api_enabled")) and cap(state) is not None


def summary(cfg: Config, state: State, conn) -> dict:
    """What `GET /api/tagging/spend` answers. The record is the real closet's; `conn` is the open closet,
    whose waiting items are estimated (the demo closet's never wait)."""
    main = db.connect(cfg.db_path("main"))
    try:
        month = this_month()
        months = history(main)
    finally:
        main.close()
    now = next((m for m in months if m["month"] == month), None) or \
        {"month": month, "api_calls": 0, "plan_calls": 0, "spent_usd": 0.0, "input_tokens": 0, "output_tokens": 0}
    limit = cap(state)
    left = max(0.0, limit - now["spent_usd"]) if limit is not None else None
    one = estimate_call(1)
    return {
        "allowed": api_allowed(state), "cap_usd": limit, "suggested_cap_usd": SUGGESTED_CAP_USD,
        "max_cap_usd": MAX_CAP_USD, "month": month, "spent_usd": now["spent_usd"], "api_calls": now["api_calls"],
        "plan_calls": now["plan_calls"], "input_tokens": now["input_tokens"], "output_tokens": now["output_tokens"],
        "left_usd": round(left, 6) if left is not None else None,
        "reached": left is not None and left < one,
        "per_photo_usd": round(one, 6), "per_find_usd": round(estimate_garments(1), 6), "waiting": waiting(conn) if state.get("profile") != "demo" else
        {"items": 0, "photos": 0, "at_most_usd": 0.0},
        "model": DESCRIBING_MODEL, "prices_checked": PRICES_CHECKED, "turned_off": state.get("tagging_api_off"),
        "history": months,
    }


class Meter:
    """The app's `tagger.tagging.Meter`: records every call in the real closet and keeps the API key under the limit."""

    def __init__(self, cfg: Config, state: State, purpose: str = PURPOSE_TAG, estimate=estimate_call):
        self.cfg, self.state, self.purpose, self.estimate = cfg, state, purpose, estimate

    def _connect(self):
        return db.connect(self.cfg.db_path("main"))

    def before_api_call(self, model: str, images: int) -> None:
        if not api_allowed(self.state):   # turned off (or the limit removed) since the routes were worked out
            raise RouteUnavailable("the API key is not allowed in Settings")
        cost, me = self.estimate(images, model), threading.get_ident()
        with _lock:
            _held.pop(me, None)   # this thread's last request has come back or failed
            conn = self._connect()
            try:
                so_far = spent(conn)
            finally:
                conn.close()
            limit = cap(self.state)
            if limit is None or not self.state.get("tagging_api_enabled"):
                raise RouteUnavailable("the API key is not allowed in Settings")
            if so_far + sum(_held.values()) + cost > limit:
                raise CapReached("this month's spending limit for the API key has been reached")
            _held[me] = cost

    def record(self, route: str, model: str, input_tokens: int, output_tokens: int, searches: int = 0,
               cache_write: int = 0, cache_read: int = 0) -> None:
        with _lock:
            conn = self._connect()
            try:
                record(conn, route, model, input_tokens, output_tokens, self.purpose, searches, cache_write, cache_read)
            finally:
                conn.close()
                if route == "api":
                    _held.pop(threading.get_ident(), None)   # now counted at what it cost

    def release(self) -> None:
        """The request this thread sent did not come back (an error, a refusal, no connection): nothing was billed,
        so what it held is let go."""
        with _lock:
            _held.pop(threading.get_ident(), None)

    def api_refused(self, reason: str) -> None:
        """Anthropic turned the key away (no credit, or the key was refused): stop using it until the owner looks."""
        self.state.update(tagging_api_enabled=False, tagging_api_off={"at": db.now(), "reason": reason})
