"""What reaching Claude costs: a record of every call, the API key's monthly limit, and estimates.

Every call is written to the real closet's database (`claude_calls`): when, what
for, which route and model, the tokens in and out as reported, and the cost
worked out from the price table in `tagger/models.json`. Plan calls are counted
at no cost. Nothing about a photo, the prompt or an answer is kept.

The limit is in US dollars, the currency of the price table, for the calendar
month in the computer's local time; it is kept in the program's settings with
the switch that allows the API key. Before each API request the month's spend
plus a careful estimate of that request is compared with the limit, and the
request is not made if it could go over.
"""
from __future__ import annotations

from datetime import datetime

from . import db
from .config import Config
from .state import State
from .tagger.correcting import MAX_TOKENS as CORRECT_MAX_TOKENS
from .tagger.garments import MODEL as GARMENTS_MODEL
from .tagger.shopping import MAX_TOKENS as SHOP_MAX_TOKENS
from .tagger.tagging import CONFIG, MAX_TOKENS, CapReached, RouteUnavailable

PURPOSE_TAG = "tag_item"
PURPOSE_CORRECT = "correct_item"   # reading the owner's sentence about an item (`tagger/correcting.py`)
PURPOSE_LANDMARKS = "item_landmarks"   # where a patterned top's buttons, neck, hem and sleeves are (`tagger/landmarks.py`)
PURPOSE_SHOP = "shop_find"            # searching shops for a wish (`tagger/shopping.py`)
PURPOSE_PRICES = "shop_prices"        # looking up the prices of a wish's finds again
PURPOSE_GARMENTS = "find_garments"    # where each piece is in a photo of several (`tagger/garments.py`)
PRICES_CHECKED: str = CONFIG.get("prices_checked", "")
TAGGING_MODEL: str = CONFIG["roles"]["tagging"]
SUGGESTED_CAP_USD = 5.0     # see DECISIONS, "Spend cap for the API key"
MAX_CAP_USD = 1000.0        # a typing slip should not allow a large bill
HISTORY_MONTHS = 12

# A careful upper bound on one request to describe an item: the prompt with the answer's schema and whatever the
# API adds for it (about 4,500 tokens measured, doubled), each photo at no more than 1024 px a side (about 1,400
# tokens by Anthropic's rule of width x height / 750, rounded up), and the longest answer the request allows.
TEXT_TOKENS = 8000
IMAGE_TOKENS = 1600
# Reading a correction: the longest prompt the app writes (a 500-character sentence, a shirt's description and every
# value it may take, about 7,000 characters with the schema; counted at 1 token for every character pair, then the
# whole doubled), a photo when one is sent, and the longest answer the request allows (`correcting.MAX_TOKENS`).
CORRECT_TEXT_TOKENS = 9000
# Searching shops: Claude reads the pages its web searches bring back, and reads them again at each step of its
# search, so a request takes in far more than its prompt. A careful upper bound: 300,000 tokens in, the longest
# answer the request allows, and every web search it may make, at the price per search in the price table.
SHOP_INPUT_TOKENS = 300_000
SEARCH_USD: float = CONFIG.get("web_search_per_1000", 10.0) / 1000

LIMIT_REACHED = ("This month's spending limit for the API key has been reached, and your Claude plan can't be used "
                 "right now. It will be described when your plan can be used again, when the new month starts, or if "
                 "you raise the limit in Settings.")


def _now() -> datetime:
    """The computer's local time (tests move it)."""
    return datetime.now().astimezone()


def this_month() -> str:
    return _now().strftime("%Y-%m")


def price(model: str) -> dict:
    """The model's prices per million tokens; a model missing from the table is priced as the dearest one."""
    table = CONFIG["models"]
    return table.get(model) or max(table.values(), key=lambda p: p["output"])


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    p = price(model)
    return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000


def estimate_call(photos: int, model: str = TAGGING_MODEL) -> float:
    """The most one request to describe an item with this many photos should cost."""
    return cost_usd(model, TEXT_TOKENS + IMAGE_TOKENS * max(1, photos), MAX_TOKENS)


def estimate_landmarks(photos: int, model: str = TAGGING_MODEL) -> float:
    """The most one request for an item's landmarks should cost: a short prompt and schema, the photo, a short answer."""
    return cost_usd(model, CORRECT_TEXT_TOKENS + IMAGE_TOKENS * max(1, photos), CORRECT_MAX_TOKENS)


def estimate_garments(photos: int, model: str = GARMENTS_MODEL) -> float:
    """The most one request for the boxes around the pieces in a photo should cost: a short prompt and schema, the
    photo, and the longest answer allowed (about twenty boxes fit in it)."""
    return cost_usd(model, CORRECT_TEXT_TOKENS + IMAGE_TOKENS * max(1, photos), CORRECT_MAX_TOKENS)


def estimate_correction(photos: int, model: str = TAGGING_MODEL) -> float:
    """The most one request to read a correction should cost (`photos` is 0 or 1)."""
    return cost_usd(model, CORRECT_TEXT_TOKENS + IMAGE_TOKENS * max(0, photos), CORRECT_MAX_TOKENS)


def estimate_shop(searches: int, model: str = TAGGING_MODEL) -> float:
    """The most one request to search shops should cost, with at most `searches` web searches."""
    return cost_usd(model, SHOP_INPUT_TOKENS, SHOP_MAX_TOKENS) + SEARCH_USD * max(0, searches)


def record(conn, route: str, model: str, input_tokens: int, output_tokens: int, purpose: str = PURPOSE_TAG,
           searches: int = 0) -> float:
    """Write down one call; returns what it cost (nothing on the plan route). `searches`: the web searches the API
    made for it, each billed on top of the tokens."""
    cost = cost_usd(model, input_tokens, output_tokens) + SEARCH_USD * max(0, searches) if route == "api" else 0.0
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
        "model": TAGGING_MODEL, "prices_checked": PRICES_CHECKED, "turned_off": state.get("tagging_api_off"),
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
        conn = self._connect()
        try:
            so_far = spent(conn)
        finally:
            conn.close()
        if so_far + self.estimate(images, model) > cap(self.state):
            raise CapReached("this month's spending limit for the API key has been reached")

    def record(self, route: str, model: str, input_tokens: int, output_tokens: int, searches: int = 0) -> None:
        conn = self._connect()
        try:
            record(conn, route, model, input_tokens, output_tokens, self.purpose, searches)
        finally:
            conn.close()

    def api_refused(self, reason: str) -> None:
        """Anthropic turned the key away (no credit, or the key was refused): stop using it until the owner looks."""
        self.state.update(tagging_api_enabled=False, tagging_api_off={"at": db.now(), "reason": reason})
