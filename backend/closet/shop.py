"""Shopping for a wish: products found by Claude, each checked against the closet, and their prices over time.

"Find some" on a wish asks Claude (`tagger/shopping.py`, through the same routes
and the same monthly limit as describing an item, recorded with the purpose
`spend.PURPOSE_SHOP`) for up to eight products on sale now that match the wish.
Every product is checked before it is kept: its links must be web addresses,
its price a number and its description the closet's own words
(`wouldwork.parse_piece`); a product that does not fit is dropped and the rest
are kept. Each kept find is then tried against the closet with the "Would this
work?" rules (`wouldwork.check`) and keeps its verdict and reasons. Finds are
kept with the wish (migration 0018) until the owner removes them or the wish;
nothing is bought or opened by the program.

The owner can also send a product's page as a link (migration 0042): a new wish
made from it, or a find added to a wish. Nines reads the page itself first, from
this computer (`productpage.py`: the address checked, the page fetched with
care, its structured data read), and asks Claude to read that one page, as a
price check, only when the page gives no price. Once the page has given a name,
Claude is asked once to describe the product in the closet's words from what the
page says (`tagger/shopping.py`'s `describe`, recorded with the purpose
`spend.PURPOSE_DESCRIBE_LINK`, held against the same limit); the piece is kept
on the find and judged as a search's finds are. When Claude cannot be asked
(out of reach, the limit, the demo closet) the link waits, and is described at
the next price check or daily round that reads its page; an answer that cannot
be used is remembered by a fingerprint of what was asked (`unclear`), so the
same page is not asked about again until it changes.

A wish's finds can have their prices looked up again on demand and, while the
program runs, at most once a day (`PriceScheduler`): a link's page read by Nines
first, Claude asked about the rest. Every price seen is kept, and a find whose
latest price is below the highest seen before shows a drop, on the wish and on
its row in the wishlist. A price that came down since the owner last looked at
the wish (migration 0045), to no more than the most they would pay when they
said, is news (`news`): the page's banner tells them.

A find can have one checkout code (migration 0046), a percent or an amount off:
read from its page's text by Nines, given by Claude when it reads the page in a
price check anyway, or typed by the owner. Nines works out the price after the
code and keeps it with every price seen (`price_with`, `_add_point`); a drop,
the news and "within your price" count it when there is one (`paid`). A code
read from a page goes when the page stops showing it; a typed one stays until
the owner removes it, and saving it marks the wish's news seen.

The demo closet is never sent to Claude and has no news: it cannot search, a
link's page is read there by Nines alone, and the daily round only ever opens
the real closet.

Searches, price checks and reading a link run in the background on a thread of
their own; how each is getting on is held in memory only. Nothing about a wish, a product or
a link is logged.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
import threading
import traceback
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from . import aboutyou, db, gaps, productpage, spend, wishlist, wouldwork
from .config import Config
from .items import ItemError
from .state import State
from .tagger import shopping
from .tagger.tagging import CapReached, RouteUnavailable, TaggingError, Unreachable

log = logging.getLogger("closet.shop")

DAY = timedelta(hours=24)       # the daily round looks at a wish's prices again once this long has passed
CHECK_EVERY = 3600.0            # seconds between looks at whether a round is due, while the program runs
FIRST_WAIT = 120.0              # seconds after the program starts before the first look
PRICE_FINDS_MAX = 12            # the newest finds still for sale whose prices are looked up, per wish
HISTORY_MAX = 30                # prices shown per find, newest last
SEEN_MAX = 200                  # wishes marked seen in one request (the banner's "Got it" marks every one it told)
URL_MAX = productpage.URL_MAX   # 2000
NAME_MAX = 200
# a wish made from a link is named from its product, cut at a word to this: the wish's name is its page's heading, and
# shops' names run long; the find keeps the whole name
LINK_NAME_MAX = 60
SHOP_MAX = 120
DESCRIPTION_MAX = productpage.DESCRIPTION_MAX   # characters of a page's description sent to Claude to describe a link
BRAND_MAX = 120
COLOR_MAX = 60
PRICE_MAX = 1_000_000.0
CURRENCY = re.compile(r"^[A-Z]{3}$")
CODE = re.compile(r"^[A-Z0-9_-]{3,30}$")   # a checkout code, kept upper-case as shops show them
PERCENT_MIN, PERCENT_MAX = 1, 90             # a code's percent off

DEMO = ("The demo closet never sends anything to Claude, so it can't search shops. Open your own closet in Settings "
        "to look for this.")
NO_ROUTE = ("Claude cannot be reached right now: your Claude plan is not signed in on this computer and the API key "
            "is not switched on.")
LIMIT = (spend.LIMIT_REACHED.split(" It will be described")[0] + " Try again when your plan can be used, when the new "
         "month starts, or after raising the limit in Settings.")
NOTHING = "Claude found nothing on sale that matches. Try again later, or say more in the note."
NOT_UNDERSTOOD = "Claude's answer could not be used. Try again in a while."
FAILED = "Something went wrong while looking. Try again."
NOT_SAVED = "Nines found some but could not keep them: your closet was busy saving something else. Try again."
BUSY = "Nines is already looking for this one. Wait for it to finish."
NO_FINDS = "There is nothing to check yet: find some first."
NO_PAGE_PRICE = "The page doesn't give its price in a way Nines can read."
NO_PRICE_AT_ALL = NO_PAGE_PRICE[:-1] + ", and Claude found no price on it either."
SOME_UNREAD = "Not every page gives its price in a way Nines can read."
LINKS_ONLY = "Only the pages you sent as links were read."
DEMO_ASKS_NOTHING = "The demo closet never sends anything to Claude."
# a code you type, refused
BAD_CODE = "A code is 3 to 30 letters or digits, and can have - or _ in it."
ONE_DISCOUNT = "Give the code's percent off or its amount off, one of the two."
BAD_PERCENT = "The percent off is a number from 1 to 90."
BAD_AMOUNT = "The amount off is a number more than 0 and less than the price."
NO_PRICE_YET = "Nines doesn't know the price yet, so give the code's percent off instead."


class Refused(Exception):
    """A search or price check that cannot start, with the sentence to show."""


class Asker(Protocol):
    """Claude, for shopping (tests stand in for it)."""

    def find(self, wish: dict, routes: tuple[str, ...]) -> shopping.ShopAnswer: ...

    def prices(self, finds: list[dict], routes: tuple[str, ...]) -> shopping.PriceAnswer: ...

    def describe(self, product: dict, routes: tuple[str, ...]) -> shopping.Described: ...


class ClaudeAsker:
    """The real one: `tagger/shopping.py` behind the monthly limit, each kind of call recorded as its own purpose."""

    def __init__(self, cfg: Config, state: State, client=None):
        self.client = client
        self.finding = spend.Meter(cfg, state, spend.PURPOSE_SHOP, spend.estimate_shop)
        self.pricing = spend.Meter(cfg, state, spend.PURPOSE_PRICES, spend.estimate_shop)
        self.describing = spend.Meter(cfg, state, spend.PURPOSE_DESCRIBE_LINK, spend.estimate_describe_link)

    def find(self, wish: dict, routes: tuple[str, ...]) -> shopping.ShopAnswer:
        return shopping.find(wish, routes, client=self.client, meter=self.finding)

    def prices(self, finds: list[dict], routes: tuple[str, ...]) -> shopping.PriceAnswer:
        return shopping.prices(finds, routes, client=self.client, meter=self.pricing)

    def describe(self, product: dict, routes: tuple[str, ...]) -> shopping.Described:
        return shopping.describe(product, routes, client=self.client, meter=self.describing)


# the closet to check finds against, for a profile: (item rows, wear log)
Closet = Callable[[str], tuple[list[dict], list[dict]]]
Routes = Callable[[], tuple[str, ...]]


# ------------------------------------------------------------------ checking what Claude said
def clean_url(value: object) -> str | None:
    """A web address that can be shown as a link: http or https with a host, no spaces, not too long."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > URL_MAX or any(c.isspace() or ord(c) < 32 for c in value):
        return None
    try:
        parts = urlsplit(value)
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        return None
    return value


def _words(value: object, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    value = " ".join(value.split())
    return value[:limit].rstrip() or None


def clean_price(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return round(value, 2) if 0 <= value <= PRICE_MAX else None


def clean_currency(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip().upper()
    return value if CURRENCY.match(value) else None


def clean_find(raw: object) -> dict | None:
    """One product from Claude as a find, or None when it does not fit (the rest of the answer is kept)."""
    if hasattr(raw, "model_dump"):
        raw = raw.model_dump()
    if not isinstance(raw, dict):
        return None
    name, shop, url = _words(raw.get("name"), NAME_MAX), _words(raw.get("shop"), SHOP_MAX), clean_url(raw.get("url"))
    currency = clean_currency(raw.get("currency"))
    if not (name and shop and url and currency):
        return None
    price = raw.get("price")
    if price is not None and clean_price(price) is None:
        return None
    piece = _piece_of(raw, name)
    if piece is None:
        return None
    return {"name": name, "shop": shop, "url": url, "image_url": clean_url(raw.get("image_url")),
            "price": clean_price(price) if price is not None else None, "currency": currency, "piece": piece}


def _piece_of(raw: dict, name: str) -> dict | None:
    """A product's description in the listed values, as the closet's words (`wouldwork.parse_piece`), or None when it
    does not fit."""
    weight = raw.get("weight_class")
    material = _words(raw.get("material"), wouldwork.MATERIAL_MAX)
    try:
        return wouldwork.parse_piece({
            "category": raw.get("category"), "color": raw.get("color"), "formality": raw.get("formality"),
            "season": raw.get("season"), "pattern": raw.get("pattern"),
            "weight_class": None if weight in (None, "", "unknown") else weight,
            "rain_proof": raw.get("rain_proof") is True, "name": name[:wouldwork.NAME_MAX], "material": material})
    except wouldwork.PieceError:
        return None


def clean_described(raw: object, name: str) -> dict | None:
    """Claude's description of a page sent as a link, as a piece in the closet's words; None when Claude said it is
    not one piece of menswear, or the answer does not fit."""
    if hasattr(raw, "model_dump"):
        raw = raw.model_dump()
    if not isinstance(raw, dict) or raw.get("clothing") is not True:
        return None
    return _piece_of(raw, name)


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and abs(value) < float("inf")


def code_problem(code: object, percent: object, amount: object, price: float | None) -> tuple[dict | None, str | None]:
    """A checkout code and its discount, checked: ({code, percent, amount}, None), or (None, the sentence saying what
    is wrong). The code is letters, digits, - and _, 3 to 30 of them, kept upper-case; with either a percent off from 1
    to 90 or an amount off more than 0 and less than the price (so the price must be known)."""
    if not isinstance(code, str) or not CODE.match(code.strip().upper()) or not any(c.isalnum() for c in code):
        return None, BAD_CODE
    code = code.strip().upper()
    if (percent is None) == (amount is None):
        return None, ONE_DISCOUNT
    if percent is not None:
        if not _number(percent) or not PERCENT_MIN <= percent <= PERCENT_MAX:
            return None, BAD_PERCENT
        return {"code": code, "percent": round(float(percent), 2), "amount": None}, None
    if not _number(amount) or round(float(amount), 2) <= 0:
        return None, BAD_AMOUNT
    if price is None:
        return None, NO_PRICE_YET
    if round(float(amount), 2) >= price:
        return None, BAD_AMOUNT
    return {"code": code, "percent": None, "amount": round(float(amount), 2)}, None


def clean_code(code: object, percent: object, amount: object, price: float | None) -> dict | None:
    """A code read on a page (by Nines or by Claude), checked as `code_problem` checks a typed one, and never a word
    that is plainly not a code ("CODE", "OFF", "SALE"); None when it does not fit."""
    checked, _ = code_problem(code, percent, amount, price)
    return None if checked is None or checked["code"] in productpage.NOT_CODES else checked


def price_with(price: float | None, percent: float | None, amount: float | None) -> float | None:
    """The price after a code, rounded to cents (half up); None with no price, no code, or an amount off that is not
    less than the price (it may have come down since the code was saved)."""
    if price is None or (percent is None and amount is None):
        return None
    cents = Decimal(str(price))
    after = cents * (100 - Decimal(str(percent))) / 100 if percent is not None else cents - Decimal(str(amount))
    if after <= 0:
        return None
    return float(after.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def best_code(codes: list[dict], price: float | None) -> dict | None:
    """The biggest discount among codes already checked: the lowest price after the code, else the biggest percent."""
    if not codes:
        return None
    return min(codes, key=lambda c: (price_with(price, c["percent"], c["amount"]) or PRICE_MAX, -(c["percent"] or 0)))


def clean_read(p: productpage.Product) -> dict:
    """What Nines read on a link's page, checked as Claude's answers are: text shortened, a picture only by a web
    address, a price only as a number in range (else none), a currency only as three letters (else none), and of the
    checkout codes its text shows, the biggest discount among those that fit (`clean_code`; an amount off only in the
    page's currency), else none. Its words about the product (description, brand, colour, material) are kept only to
    be sent to Claude to describe it."""
    price, currency = clean_price(p.price), clean_currency(p.currency)
    codes = []
    for c in getattr(p, "codes", None) or []:
        checked = clean_code(c.code, c.percent, c.amount, price)
        if checked and c.amount is not None:
            if c.currency and currency and c.currency != currency:
                continue
            checked["currency"] = c.currency
        if checked:
            codes.append(checked)
    return {"name": _words(p.name, NAME_MAX), "shop": _words(p.shop, SHOP_MAX), "image_url": clean_url(p.image_url),
            "price": price, "currency": currency, "available": p.available is not False, "code": best_code(codes, price),
            "description": _words(p.description, DESCRIPTION_MAX), "brand": _words(p.brand, BRAND_MAX),
            "color": _words(p.color, COLOR_MAX), "material": _words(p.material, wouldwork.MATERIAL_MAX)}


def page_words(read: dict) -> dict:
    """What Claude is given to describe a link: only what its page says (`clean_read`), never anything from the
    closet."""
    return {k: read.get(k) for k in ("name", "shop", "brand", "color", "material", "description")}


def fingerprint(text: str) -> str:
    """A short fingerprint of what was asked, to know the same page again without keeping its words."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def shortened(text: str, limit: int) -> str:
    """The text as it is when it fits; else cut at the last word that fits, with "…" to show it was cut."""
    if len(text) <= limit:
        return text
    cut = text[:limit - 1]
    return (cut.rsplit(" ", 1)[0] if " " in cut else cut).rstrip(" ,;:-") + "…"


def placeholder(url: str) -> str:
    """What a wish made from a link is called until its page is read: the shop's address, without "www."."""
    host = (urlsplit(url).hostname or "").removeprefix("www.")
    return host[:wishlist.NAME_MAX] or "A product's page"


# ------------------------------------------------------------------ "Would this work?" for each find
def judge(rows: list[dict], worn: list[dict], pieces: list[dict], listed: dict | None = None) -> list[dict]:
    """Each piece checked against the closet: {verdict, verdict_words, reasons, checked_at}. The closet's gaps are
    worked out once for all of them. `listed` is the gap list as What's missing has it (the app keeps it): the plain
    list until the owner has said how they live, weighed by how they live once they have, its "context" saying which.
    The finds are then judged exactly as "Would this work?" judges a piece, and the list is not worked out again.
    Without it the plain list is worked out here."""
    if not pieces:
        return []
    before = listed if listed is not None else gaps.find_gaps(rows, worn, {"max_gaps": wouldwork.ALL_GAPS})
    context = (listed or {}).get("context") or {}
    out = []
    for p in pieces:
        a = wouldwork.check(rows, worn, p, before, context.get("life"), context.get("climate"))
        out.append({"verdict": a["verdict"], "verdict_words": a["verdict_words"], "reasons": a["reasons"],
                    "checked_at": db.now()})
    return out


# ------------------------------------------------------------------ the database
POINT = "at, price, currency, available, with_code, code"


def _point(r: sqlite3.Row) -> dict:
    return {"at": r["at"], "price": r["price"], "currency": r["currency"], "available": bool(r["available"]),
            "with_code": r["with_code"], "code": r["code"]}


def _history(conn: sqlite3.Connection, find_id: str) -> list[dict]:
    rows = conn.execute(f"SELECT {POINT} FROM find_prices WHERE find_id = ? ORDER BY at, id", (find_id,)).fetchall()
    return [_point(r) for r in rows]


def paid(h: Mapping) -> float | None:
    """What a price point would cost you: the price after its checkout code when there was one, else the price."""
    return h["price"] if h["price"] is None or h.get("with_code") is None else h["with_code"]


def drop(history: list[dict]) -> dict | None:
    """The latest price against the highest seen before it in the same currency, each the price after its checkout
    code when there was one (`paid`): {from, to, currency, percent} when it is lower, else None; with `code`, the code
    the latest price is after, when it is."""
    if not history or history[-1]["price"] is None:
        return None
    now = history[-1]
    before = [paid(h) for h in history[:-1] if h["price"] is not None and h["currency"] == now["currency"]]
    to = paid(now)
    if not before or to >= max(before) - 0.005:
        return None
    was = max(before)
    out = {"from": was, "to": to, "currency": now["currency"], "percent": round((was - to) / was * 100)}
    if now.get("with_code") is not None and now.get("code"):
        out["code"] = now["code"]
    return out


def _code_of(r: Mapping) -> dict | None:
    """A find's checkout code, as kept: {code, percent, amount, by, seen_at}, or None."""
    if not r["code"]:
        return None
    return {"code": r["code"], "percent": r["code_percent"], "amount": r["code_amount"], "by": r["code_by"],
            "seen_at": r["code_seen_at"]}


def unclear(verdict: str | None) -> str | None:
    """The fingerprint of what Claude was asked about a link whose answer could not be used, kept in the find's
    verdict column while it has no piece (`mark_unclear`); None otherwise."""
    v = json.loads(verdict) if verdict else None
    return v.get("unclear") if isinstance(v, dict) else None


def not_judged(f: dict, marker: str | None) -> str | None:
    """Why a find is not judged against the closet, for the sentence on its card: "unread" (its page not read yet),
    "no_name" (the page gave no name), "unclear" (Claude could not say what it is), "waiting" (Claude not asked yet:
    out of reach, the limit, the demo closet). None when it is judged, or is waiting for a search's verdict."""
    if f["piece"] or not f["link"]:
        return None
    if not f["read_at"]:
        return "unread"
    if marker:
        return "unclear"
    if f["name"] == placeholder(f["url"])[:NAME_MAX]:
        return "no_name"
    return "waiting"


def _find(conn: sqlite3.Connection, r: sqlite3.Row) -> dict:
    f = dict(r)
    f["available"] = bool(f["available"])
    f["link"] = bool(f["link"])
    f["piece"] = json.loads(f["piece"]) if f["piece"] else None   # a link not described yet has none ("null")
    f["piece_words"] = wouldwork.describe(f["piece"]) if f["piece"] else None
    marker = unclear(f["verdict"])
    verdict = json.loads(f.pop("verdict")) if f["verdict"] and not marker else None
    f["verdict"] = verdict["verdict"] if verdict else None
    f["verdict_words"] = verdict["verdict_words"] if verdict else None
    f["reasons"] = verdict["reasons"] if verdict else []
    f["checked_at"] = verdict["checked_at"] if verdict else None
    code = _code_of(f)
    for column in ("code_percent", "code_amount", "code_by", "code_seen_at", "code_removed"):
        f.pop(column)
    f["code"] = code
    f["with_code"] = price_with(f["price"], code["percent"], code["amount"]) if code else None
    f["not_judged"] = not_judged(f, marker)
    history = _history(conn, f["id"])
    f["history"] = history[-HISTORY_MAX:]
    f["drop"] = drop(history)
    return f


def list_finds(conn: sqlite3.Connection, wish_id: str) -> list[dict]:
    """A wish's finds, the newest search first and each search's best match first."""
    return [_find(conn, r) for r in conn.execute("SELECT * FROM finds WHERE wish_id = ? ORDER BY found_at DESC, rowid",
                                                 (wish_id,))]


def _open_finds(conn: sqlite3.Connection) -> tuple[list[sqlite3.Row], dict[str, list[dict]]]:
    """The finds of the wishes still wanted, the newest first, and every price each was seen at, by find."""
    finds = conn.execute(
        "SELECT f.id, f.wish_id, f.name, f.shop, f.price, f.currency, f.available, f.link, f.code, f.code_percent, "
        "f.code_amount FROM finds f JOIN wishes w ON w.id = f.wish_id WHERE w.bought_at IS NULL "
        "ORDER BY f.found_at DESC, f.rowid").fetchall()
    history: dict[str, list[dict]] = {}
    for r in conn.execute("SELECT p.find_id, p.at, p.price, p.currency, p.available, p.with_code, p.code FROM find_prices p "
                          "JOIN finds f ON f.id = p.find_id JOIN wishes w ON w.id = f.wish_id "
                          "WHERE w.bought_at IS NULL ORDER BY p.at, p.id"):
        history.setdefault(r["find_id"], []).append(_point(r))
    return finds, history


def on_the_list(conn: sqlite3.Connection) -> dict[str, dict]:
    """What the wishlist shows on each open wish's row, by wish: `link`, its newest find sent as a link ({name, shop,
    price, currency, available}, with `code` and `with_code`, the price after it, when it has a checkout code that
    applies), and `drop`, the biggest drop among its finds ({from, to, currency, percent, shop}, with `code` when the
    price it is down to is after one); None for either when there is none."""
    finds, history = _open_finds(conn)
    out: dict[str, dict] = {}
    for f in finds:
        row = out.setdefault(f["wish_id"], {"link": None, "drop": None})
        if f["link"] and row["link"] is None:
            row["link"] = {"name": f["name"], "shop": f["shop"], "price": f["price"], "currency": f["currency"],
                           "available": bool(f["available"])}
            after = price_with(f["price"], f["code_percent"], f["code_amount"]) if f["code"] else None
            if after is not None:
                row["link"].update(code=f["code"], with_code=after)
        d = drop(history.get(f["id"], []))
        if d and (row["drop"] is None or d["percent"] > row["drop"]["percent"]):
            row["drop"] = {**d, "shop": f["shop"]}
    return out


def came_down(history: list[dict]) -> dict | None:
    """The drop a find's newest price is (`drop`), with `at`, the moment the price came down to it: the first of the
    latest prices seen at that price, the price seen before them being higher. None when the newest price is no drop,
    is sold out, or went up to it from a lower one. A price checked again each day at the same price stays one drop,
    with one moment. Each price is the one after its checkout code when there was one (`paid`), so a code that appears
    and brings the price down is a drop that came down, and a code that goes is none."""
    d = drop(history)
    if d is None or not history[-1]["available"]:
        return None
    same = [h for h in history if h["price"] is not None and h["currency"] == d["currency"]]
    i = len(same) - 1
    while i > 0 and abs(paid(same[i - 1]) - d["to"]) < 0.005:
        i -= 1
    if i == 0 or paid(same[i - 1]) < d["to"]:
        return None
    return {**d, "at": same[i]["at"]}


def at_price(wish: Mapping, currency: str, price: float) -> bool | None:
    """Whether a price is no more than the most the owner would pay for the wish (`price_max`): None when they set
    none, or set it in another currency (prices are never converted)."""
    if wish["price_max"] is None or (wish["price_currency"] or wishlist.CURRENCY_DEFAULT) != currency:
        return None
    return price <= wish["price_max"] + 0.005


def news(conn: sqlite3.Connection) -> list[dict]:
    """The price news the owner has not seen, a wish at a time: an open wish one of whose finds' price came down
    (`came_down`) after the owner last saw the wish's news (`news_seen_at`), to no more than the most they would pay
    when they set it in that find's currency. A price first seen already low is no news, only a price that came down
    is; a price is the one after its checkout code when there was one. Each: {wish_id, name, shop, from, to, currency,
    percent, at, at_price}, with `code` when `to` is after one, the biggest drop of the wish's when several came down;
    the newest first. Never asked of the demo closet (the route)."""
    wishes = {r["id"]: r for r in conn.execute(
        "SELECT id, name, price_max, price_currency, news_seen_at FROM wishes WHERE bought_at IS NULL")}
    finds, history = _open_finds(conn)
    out: dict[str, dict] = {}
    for f in finds:
        w = wishes[f["wish_id"]]
        d = came_down(history.get(f["id"], []))
        if d is None or (w["news_seen_at"] and d["at"] <= w["news_seen_at"]):
            continue
        under = at_price(w, d["currency"], d["to"])
        if under is False:
            continue
        best = out.get(w["id"])
        if best is None or d["percent"] > best["percent"]:
            out[w["id"]] = {"wish_id": w["id"], "name": w["name"], "shop": f["shop"], **d, "at_price": bool(under)}
    return sorted(out.values(), key=lambda n: n["at"], reverse=True)


def mark_seen(conn: sqlite3.Connection, wish_ids: list[str]) -> None:
    """The owner has seen these wishes' price news (opened the wish's page, or dismissed the banner). Wishes no longer
    kept are passed over."""
    t = db.now()
    for wish_id in dict.fromkeys(wish_ids):
        conn.execute("UPDATE wishes SET news_seen_at = ? WHERE id = ?", (t, wish_id))


def _add_point(conn: sqlite3.Connection, find_id: str, t: str, price: float | None, currency: str, available: bool,
               changed_only: bool = False) -> None:
    """A price seen, kept with the price after the find's checkout code then (`price_with`) when the code applies.
    `changed_only`: not when it says the same as the latest point (a code saved again)."""
    r = conn.execute("SELECT code, code_percent, code_amount FROM finds WHERE id = ?", (find_id,)).fetchone()
    after = price_with(price, r["code_percent"], r["code_amount"]) if r and r["code"] else None
    point = (price, currency, int(available), after, r["code"] if after is not None else None)
    if changed_only:
        last = conn.execute("SELECT price, currency, available, with_code, code FROM find_prices WHERE find_id = ? "
                            "ORDER BY at DESC, id DESC LIMIT 1", (find_id,)).fetchone()
        if last is not None and tuple(last) == point:
            return
    conn.execute("INSERT INTO find_prices (find_id, at, price, currency, available, with_code, code) "
                 "VALUES (?, ?, ?, ?, ?, ?, ?)", (find_id, t, *point))


def _keep_code(conn: sqlite3.Connection, find_id: str, code: dict | None, by: str | None, t: str) -> None:
    """A find's checkout code kept ({code, percent, amount}, who saw it or typed it, seen now), or taken away (None)."""
    if code is None:
        conn.execute("UPDATE finds SET code = NULL, code_percent = NULL, code_amount = NULL, code_by = NULL, "
                     "code_seen_at = NULL WHERE id = ?", (find_id,))
    else:
        conn.execute("UPDATE finds SET code = ?, code_percent = ?, code_amount = ?, code_by = ?, code_seen_at = ? "
                     "WHERE id = ?", (code["code"], code["percent"], code["amount"], by, t, find_id))


def _page_code(conn: sqlite3.Connection, find_id: str, row: Mapping, code: dict | None, currency: str, priced: bool,
               t: str) -> None:
    """What Nines reading the page does to the find's code. A code you typed stays, whatever the page says. A code the
    page's text shows is kept (by "page"), in place of one Claude saw, unless it is one you removed, or an amount off
    in another currency than the find's. With none in its text, a code read from the page goes, and so does one Claude
    saw when the page gave its price (Claude is not asked to read the page then, so nothing would ever take it away)."""
    if row["code_by"] == "you":
        return
    if code and (code["code"] == row["code_removed"] or (code.get("currency") and code["currency"] != currency)):
        code = None
    if code:
        _keep_code(conn, find_id, code, "page", t)
    elif row["code_by"] == "page" or (row["code_by"] == "claude" and priced):
        _keep_code(conn, find_id, None, None, t)


def _claude_code(conn: sqlite3.Connection, find_id: str, row: Mapping, code: dict | None, t: str) -> None:
    """What Claude reading the page in a price check does to the find's code (already checked, `clean_code`): kept (by
    "claude") unless you typed one, Nines read one from the page's text, or it is one you removed; with none, a code
    Claude saw before goes."""
    if row["code_by"] in ("you", "page"):
        return
    if code and code["code"] != row["code_removed"]:
        _keep_code(conn, find_id, code, "claude", t)
    elif row["code_by"] == "claude":
        _keep_code(conn, find_id, None, None, t)


def save_finds(conn: sqlite3.Connection, wish_id: str, finds: list[dict], verdicts: list[dict]) -> int:
    """Keep what a search found, each with its verdict and its price as found. A product found before (the same
    page) is brought up to date instead of kept twice. Returns how many are new."""
    t = db.now()
    added = 0
    conn.execute("BEGIN IMMEDIATE")
    try:
        for f, v in zip(finds, verdicts, strict=True):
            old = conn.execute("SELECT id FROM finds WHERE wish_id = ? AND url = ?", (wish_id, f["url"])).fetchone()
            if old:
                find_id = old["id"]
                conn.execute("UPDATE finds SET name = ?, shop = ?, image_url = ?, price = ?, currency = ?, available = 1, "
                             "piece = ?, verdict = ?, found_at = ?, updated_at = ? WHERE id = ?",
                             (f["name"], f["shop"], f["image_url"], f["price"], f["currency"], json.dumps(f["piece"]),
                              json.dumps(v), t, t, find_id))
            else:
                find_id = uuid.uuid4().hex
                conn.execute("INSERT INTO finds (id, wish_id, name, shop, url, image_url, price, currency, available, "
                             "piece, verdict, found_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)",
                             (find_id, wish_id, f["name"], f["shop"], f["url"], f["image_url"], f["price"],
                              f["currency"], json.dumps(f["piece"]), json.dumps(v), t, t))
                added += 1
            _add_point(conn, find_id, t, f["price"], f["currency"], True)
        conn.execute("UPDATE wishes SET found_at = ? WHERE id = ?", (t, wish_id))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return added


def to_price_check(conn: sqlite3.Connection, wish_id: str) -> list[dict]:
    """The finds whose prices are looked up: the newest PRICE_FINDS_MAX, those gone last time included (they may
    be back)."""
    return [dict(r) for r in conn.execute(
        "SELECT id, name, shop, url, price, currency, link, read_at FROM finds WHERE wish_id = ? "
        "ORDER BY found_at DESC, rowid LIMIT ?", (wish_id, PRICE_FINDS_MAX))]


def new_link_wish(conn: sqlite3.Connection, url: str) -> tuple[str, str]:
    """A wish made from a product's page, with the page as its one find, both kept in one go: called by the shop's
    address until the page is read. Returns (wish id, find id)."""
    wish_id, find_id, t = uuid.uuid4().hex, uuid.uuid4().hex, db.now()
    host = placeholder(url)
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("INSERT INTO wishes (id, gap_id, name, look_for, note, created_at, updated_at) "
                     "VALUES (?, NULL, ?, NULL, '', ?, ?)", (wish_id, host, t, t))
        _insert_link(conn, find_id, wish_id, url, host, t)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return wish_id, find_id


def _insert_link(conn: sqlite3.Connection, find_id: str, wish_id: str, url: str, host: str, t: str) -> None:
    conn.execute("INSERT INTO finds (id, wish_id, name, shop, url, image_url, price, currency, available, piece, "
                 "verdict, found_at, updated_at, link) VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, 1, 'null', NULL, ?, ?, 1)",
                 (find_id, wish_id, host[:NAME_MAX], host[:SHOP_MAX], url, wishlist.CURRENCY_DEFAULT, t, t))


def keep_link(conn: sqlite3.Connection, wish_id: str, url: str) -> str:
    """A product's page added to a wish as a find sent as a link; a page already kept with the wish becomes one (its
    price read by Nines from then on). Returns the find's id."""
    old = conn.execute("SELECT id FROM finds WHERE wish_id = ? AND url = ?", (wish_id, url)).fetchone()
    if old:
        conn.execute("UPDATE finds SET link = 1 WHERE id = ?", (old["id"],))
        return old["id"]
    find_id = uuid.uuid4().hex
    _insert_link(conn, find_id, wish_id, url, placeholder(url), db.now())
    return find_id


def link_wish(conn: sqlite3.Connection, url: str) -> str | None:
    """The open wish already made from this page as a link, if there is one (sending the same page twice adds it
    once)."""
    r = conn.execute("SELECT w.id FROM finds f JOIN wishes w ON w.id = f.wish_id WHERE f.url = ? AND f.link = 1 "
                     "AND w.bought_at IS NULL ORDER BY w.created_at DESC LIMIT 1", (url,)).fetchone()
    return r["id"] if r else None


def save_read(conn: sqlite3.Connection, wish_id: str, find_id: str, read: dict | None) -> bool:
    """Keep what Nines read on a link's own page (`clean_read`): its name, shop and picture where the page gives them,
    its checkout code (`_page_code`), and its price when it gives one, then kept with the others (read by "page"), with
    the price after the code. The page counts as read either way. A wish still called by its placeholder is named after
    the product. True when a price was kept; False when the page gave none, or the find is no longer kept."""
    t = db.now()
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT url, currency, code_by, code_removed FROM finds WHERE id = ? AND wish_id = ?",
                           (find_id, wish_id)).fetchone()
        if row is None:
            conn.execute("ROLLBACK")
            return False
        conn.execute("UPDATE finds SET read_at = ? WHERE id = ?", (t, find_id))
        priced = bool(read and read["price"] is not None)
        if read:
            for column in ("name", "shop", "image_url"):
                if read[column]:
                    conn.execute(f"UPDATE finds SET {column} = ? WHERE id = ?", (read[column], find_id))
            currency = (read["currency"] if priced else None) or row["currency"]
            _page_code(conn, find_id, row, read.get("code"), currency, priced, t)
            if priced:
                conn.execute("UPDATE finds SET price = ?, currency = ?, available = ?, read_by = 'page', updated_at = ? "
                             "WHERE id = ?", (read["price"], currency, int(read["available"]), t, find_id))
                _add_point(conn, find_id, t, read["price"], currency, read["available"])
            wish = conn.execute("SELECT name, gap_id FROM wishes WHERE id = ?", (wish_id,)).fetchone()
            if read["name"] and wish and wish["gap_id"] is None and wish["name"] == placeholder(row["url"]):
                conn.execute("UPDATE wishes SET name = ?, updated_at = ? WHERE id = ?",
                             (shortened(read["name"], LINK_NAME_MAX), t, wish_id))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return priced


def read_since(find: dict, since: datetime) -> bool:
    """Whether Nines read the link's page after `since`."""
    return bool(find.get("read_at")) and find["read_at"] > since.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def save_prices(conn: sqlite3.Connection, wish_id: str, finds: list[dict], seen: list[object]) -> int:
    """Keep the prices Claude saw for the finds it was asked about (matched by their page; anything else in the
    answer is ignored; each read by "claude"), with the checkout code it saw on the page (`_claude_code`), and note
    that the wish's prices were looked at. Returns how many finds were updated."""
    by_url = {f["url"]: f for f in finds}
    t = db.now()
    done = set()
    conn.execute("BEGIN IMMEDIATE")
    try:
        for raw in seen:
            p = raw.model_dump() if hasattr(raw, "model_dump") else raw
            if not isinstance(p, dict):
                continue
            f = by_url.get(p.get("url").strip() if isinstance(p.get("url"), str) else None)
            if f is None or f["id"] in done:
                continue
            row = conn.execute("SELECT code_by, code_removed FROM finds WHERE id = ? AND wish_id = ?",
                               (f["id"], wish_id)).fetchone()
            if row is None:
                continue
            price = clean_price(p.get("price")) if p.get("price") is not None else None
            if p.get("price") is not None and price is None:
                continue   # a price that is not one: not kept
            currency = clean_currency(p.get("currency")) or f["currency"]
            available = p.get("available") is not False
            # a code that does not fit is dropped alone: the price is kept
            code = clean_code(p.get("code"), p.get("code_percent"), p.get("code_amount"), price)
            _claude_code(conn, f["id"], row, code, t)
            conn.execute("UPDATE finds SET price = ?, currency = ?, available = ?, read_by = 'claude', updated_at = ? "
                         "WHERE id = ?", (price, currency, int(available), t, f["id"]))
            _add_point(conn, f["id"], t, price, currency, available)
            done.add(f["id"])
        conn.execute("UPDATE wishes SET prices_checked_at = ? WHERE id = ?", (t, wish_id))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return len(done)


def save_piece(conn: sqlite3.Connection, wish_id: str, find_id: str, piece: dict, verdict: dict | None) -> bool:
    """Keep Claude's description of a link (and its verdict, when it was judged at once). False when the find is no
    longer kept, or was described meanwhile."""
    return bool(conn.execute("UPDATE finds SET piece = ?, verdict = ? WHERE id = ? AND wish_id = ? AND piece = 'null'",
                             (json.dumps(piece), json.dumps(verdict) if verdict else None, find_id, wish_id)).rowcount)


def mark_unclear(conn: sqlite3.Connection, wish_id: str, find_id: str, asked: str) -> None:
    """Claude was asked about a link and its answer could not be used: remember what was asked (`fingerprint`), so the
    same page is not asked about again. Kept in the verdict column, which a find with no piece has no other use for."""
    conn.execute("UPDATE finds SET verdict = ? WHERE id = ? AND wish_id = ? AND piece = 'null'",
                 (json.dumps({"unclear": asked, "at": db.now()}), find_id, wish_id))


def set_verdicts(conn: sqlite3.Connection, finds: list[dict], verdicts: list[dict]) -> None:
    for f, v in zip(finds, verdicts, strict=True):
        conn.execute("UPDATE finds SET verdict = ? WHERE id = ?", (json.dumps(v), f["id"]))


def mark_checked(conn: sqlite3.Connection, wish_id: str) -> None:
    conn.execute("UPDATE wishes SET prices_checked_at = ? WHERE id = ?", (db.now(), wish_id))


def due(conn: sqlite3.Connection, now: datetime) -> list[str]:
    """The wishes still wanted, with finds, whose prices were not looked at in the last day: oldest look first."""
    since = (now - DAY).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return [r["id"] for r in conn.execute(
        "SELECT w.id FROM wishes w WHERE w.bought_at IS NULL AND EXISTS (SELECT 1 FROM finds f WHERE f.wish_id = w.id) "
        "AND (w.prices_checked_at IS NULL OR w.prices_checked_at <= ?) "
        "ORDER BY w.prices_checked_at IS NOT NULL, w.prices_checked_at, w.created_at", (since,))]


NO_SUCH_FIND = "That find is not kept with this wish."


def remove_find(conn: sqlite3.Connection, wish_id: str, find_id: str) -> None:
    if not conn.execute("DELETE FROM finds WHERE id = ? AND wish_id = ?", (find_id, wish_id)).rowcount:
        raise ItemError(NO_SUCH_FIND, 404)


def set_code(conn: sqlite3.Connection, wish_id: str, find_id: str, code: object, percent: object, amount: object,
             seen: bool = True) -> None:
    """A checkout code you typed for a find, checked (`code_problem`; ItemError with the sentence when it does not fit,
    404 for no such find), in place of any code it had. It is yours: no read of the page changes or removes it. The
    price is kept again with the price after it, and the wish's price news is marked seen (`seen`; not in the demo
    closet): a code you add is not news to you."""
    t = db.now()
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT price, currency, available FROM finds WHERE id = ? AND wish_id = ?",
                           (find_id, wish_id)).fetchone()
        if row is None:
            raise ItemError(NO_SUCH_FIND, 404)
        checked, problem = code_problem(code, percent, amount, row["price"])
        if checked is None:
            raise ItemError(problem or BAD_CODE, 422)
        _keep_code(conn, find_id, checked, "you", t)
        if row["price"] is not None:
            _add_point(conn, find_id, t, row["price"], row["currency"], bool(row["available"]), changed_only=True)
        if seen:
            mark_seen(conn, [wish_id])
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def remove_code(conn: sqlite3.Connection, wish_id: str, find_id: str, seen: bool = True) -> None:
    """A find's checkout code taken away by you, whoever saw it; a code read from the page or by Claude is not taken
    from them again (`code_removed`). The price is kept again without it (a price going up is never news)."""
    t = db.now()
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT price, currency, available, code FROM finds WHERE id = ? AND wish_id = ?",
                           (find_id, wish_id)).fetchone()
        if row is None:
            raise ItemError(NO_SUCH_FIND, 404)
        if row["code"]:
            _keep_code(conn, find_id, None, None, t)
            conn.execute("UPDATE finds SET code_removed = ? WHERE id = ?", (row["code"], find_id))
            if row["price"] is not None:
                _add_point(conn, find_id, t, row["price"], row["currency"], bool(row["available"]), changed_only=True)
            if seen:
                mark_seen(conn, [wish_id])
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


# ------------------------------------------------------------------ the work
def _now() -> datetime:
    """Now, in UTC (tests move it)."""
    return datetime.now(UTC)


class Shopper:
    """Searches, price checks and links read, one at a time per wish, each on a thread of its own."""

    def __init__(self, cfg: Config, state: State, closet: Closet, routes: Routes, asker: Asker,
                 reader: productpage.Reader | None = None):
        self.cfg, self.state, self.closet, self.routes, self.asker = cfg, state, closet, routes, asker
        self.reader = reader or productpage.Reader()   # a link's page, read by Nines itself (tests stand in for the web)
        # the gap list as What's missing has it, as "Would this work?" is given it (set by the app: kept, so a search
        # or a price check does not work it out again); None: the plain list is worked out for each
        self.listed: Callable[[str, tuple[list[dict], list[dict]]], dict | None] = lambda profile, inputs: None
        self._runs: dict[tuple[str, str], dict] = {}   # (profile, wish id) -> the last or current search or check
        self._lock = threading.Lock()

    # ------------------------------------------------------------- what is going on
    def run(self, profile: str, wish_id: str) -> dict | None:
        with self._lock:
            r = self._runs.get((profile, wish_id))
            return dict(r) if r else None

    def running(self, profile: str, wish_id: str) -> bool:
        r = self.run(profile, wish_id)
        return bool(r and r["state"] == "running")

    def _begin(self, profile: str, wish_id: str, kind: str) -> None:
        with self._lock:
            r = self._runs.get((profile, wish_id))
            if r and r["state"] == "running":
                raise Refused(BUSY)
            self._runs[(profile, wish_id)] = {"kind": kind, "state": "running", "step": None, "message": None,
                                              "added": None, "started_at": db.now(), "finished_at": None}

    def _step(self, profile: str, wish_id: str, step: str) -> None:
        """Say who is reading now: "page" (Nines, on the shops' own pages) or "claude"."""
        with self._lock:
            r = self._runs.get((profile, wish_id))
            if r:
                r["step"] = step

    def _end(self, profile: str, wish_id: str, state: str, message: str | None = None, added: int | None = None) -> None:
        with self._lock:
            r = self._runs.get((profile, wish_id))
            if r:
                r.update(state=state, message=message, added=added, finished_at=db.now())

    def estimate(self, finds: int = 0) -> dict:
        """The most a search, and a price check of `finds` finds, would cost through the API key."""
        return {"api": spend.api_allowed(self.state),
                "find_usd": round(spend.estimate_shop(shopping.FIND_SEARCHES), 6),
                "prices_usd": round(spend.estimate_shop(min(shopping.PRICE_SEARCHES, max(1, finds))), 6)}

    def _usable(self, searches: int = 0, cost: float | None = None) -> tuple[str, ...]:
        """The routes to try, or Refused: none can be used, or only the API key can and the request could take
        the month past its limit (the estimate is checked before anything is asked): a search's with `searches` web
        searches, or `cost` when given."""
        routes = self.routes()
        if not routes:
            raise Refused(NO_ROUTE)
        if "plan" not in routes:
            limit = spend.cap(self.state)
            main = db.connect(self.cfg.db_path("main"))
            try:
                so_far = spend.spent(main)
            finally:
                main.close()
            if limit is None or so_far + (spend.estimate_shop(searches) if cost is None else cost) > limit:
                raise Refused(LIMIT)
        return routes

    # ------------------------------------------------------------- starting
    def start_find(self, profile: str, wish_id: str) -> None:
        """Start a search for the wish. Refused (or ItemError, no such wish) when it cannot start."""
        if profile == "demo":
            raise Refused(DEMO)
        self._wish(profile, wish_id)
        if self.running(profile, wish_id):
            raise Refused(BUSY)
        routes = self._usable(shopping.FIND_SEARCHES)
        self._begin(profile, wish_id, "find")
        self._thread(lambda: self.find(profile, wish_id, routes), profile, wish_id)

    def start_prices(self, profile: str, wish_id: str) -> None:
        """Start a price check. With no link among the finds it needs Claude, as before (Refused when Claude cannot
        be asked); with links, their pages are read by Nines whatever Claude can do (in the demo closet, only they)."""
        self._wish(profile, wish_id)
        conn = db.connect(self.cfg.db_path(profile))
        try:
            finds = to_price_check(conn, wish_id)
        finally:
            conn.close()
        links = any(f["link"] for f in finds)
        if profile == "demo" and not links:
            raise Refused(DEMO)
        if not finds:
            raise Refused(NO_FINDS)
        if self.running(profile, wish_id):
            raise Refused(BUSY)
        routes, why = (), DEMO_ASKS_NOTHING
        if profile != "demo":
            try:
                routes, why = self._usable(min(shopping.PRICE_SEARCHES, len(finds))), None
            except Refused as e:
                if not links:
                    raise
                why = str(e)
        self._begin(profile, wish_id, "prices")
        self._thread(lambda: self.prices(profile, wish_id, routes, why_not=why), profile, wish_id)

    def check_link(self, url: object) -> str:
        """The address as it will be kept, once checked (`productpage.Reader.check`): PageError with the sentence when
        Nines does not open it. Looks its name up, so it is called off the event loop."""
        return self.reader.check(url).url

    def add_link(self, profile: str, url: object) -> tuple[dict, bool]:
        """A new wish made from a product's page, its page read on a thread. When an open wish was already made from
        the same page it is given back instead (False), and nothing is read. PageError for an address Nines does not
        open."""
        url = self.check_link(url)
        conn = db.connect(self.cfg.db_path(profile))
        try:
            old = link_wish(conn, url)
            if old:
                return wishlist.get_wish(conn, old), False
            wish_id, find_id = new_link_wish(conn, url)
            wish = wishlist.get_wish(conn, wish_id)
        finally:
            conn.close()
        self._begin(profile, wish_id, "link")
        self._thread(lambda: self.read_link(profile, wish_id, find_id), profile, wish_id)
        return wish, True

    def add_link_to(self, profile: str, wish_id: str, url: object) -> None:
        """A product's page added to a wish, its page read on a thread. PageError for an address Nines does not open,
        ItemError for no such wish, Refused while something else runs for the wish."""
        url = self.check_link(url)
        self._wish(profile, wish_id)
        self._begin(profile, wish_id, "link")
        try:
            conn = db.connect(self.cfg.db_path(profile))
            try:
                find_id = keep_link(conn, wish_id, url)
            finally:
                conn.close()
        except Exception:
            self._end(profile, wish_id, "failed", FAILED)
            raise
        self._thread(lambda: self.read_link(profile, wish_id, find_id), profile, wish_id)

    def _wish(self, profile: str, wish_id: str) -> dict:
        conn = db.connect(self.cfg.db_path(profile))
        try:
            return wishlist.get_wish(conn, wish_id)
        finally:
            conn.close()

    def _thread(self, work: Callable[[], None], profile: str, wish_id: str) -> None:
        def run() -> None:
            try:
                work()
            except CapReached:
                self._end(profile, wish_id, "failed", LIMIT)
            except RouteUnavailable:
                self._end(profile, wish_id, "failed", NO_ROUTE)
            except TaggingError:
                self._end(profile, wish_id, "failed", NOT_UNDERSTOOD)
            except Exception:   # never the wish, a product or a link in the log: only that it failed, and where
                log.error("a search or price check failed\n%s", traceback.format_exc())
                self._end(profile, wish_id, "failed", FAILED)

        try:
            threading.Thread(target=run, name="shop", daemon=True).start()
        except Exception:
            log.exception("a search or price check could not start")
            self._end(profile, wish_id, "failed", FAILED)

    # ------------------------------------------------------------- the work itself (on the thread)
    def find(self, profile: str, wish_id: str, routes: tuple[str, ...]) -> int:
        """Ask Claude, keep what fits, check each against the closet. Returns how many finds are new."""
        wish = self._wish(profile, wish_id)
        rows, worn = self.closet(profile)
        conn = db.connect(self.cfg.db_path(profile))
        try:   # what the closet says about the owner goes with the wish, as a block of its own (aboutyou.py)
            wish = {**wish, "about": aboutyou.for_search(conn, rows, worn, wish)}
        finally:
            conn.close()
        answer = self.asker.find(wish, routes)
        raw = answer.finds if hasattr(answer, "finds") else []
        found, urls = [], set()
        for r in raw[:shopping.MAX_FINDS]:
            f = clean_find(r)
            if f and f["url"] not in urls:
                urls.add(f["url"])
                found.append(f)
        if not found:
            self._end(profile, wish_id, "done", NOTHING if not raw else NOT_UNDERSTOOD, 0)
            return 0
        rows, worn = self.closet(profile)   # read again: the closet may have changed during the search
        verdicts = judge(rows, worn, [f["piece"] for f in found], self.listed(profile, (rows, worn)))
        conn = db.connect(self.cfg.db_path(profile))
        try:
            wishlist.get_wish(conn, wish_id)   # still on the list (it may have been removed meanwhile)
            try:
                added = save_finds(conn, wish_id, found, verdicts)
            except sqlite3.OperationalError:   # waited db.connect's timeout for another writer, in vain
                log.error("the finds of a search could not be kept\n%s", traceback.format_exc())
                self._end(profile, wish_id, "failed", NOT_SAVED)
                return 0
        finally:
            conn.close()
        self._end(profile, wish_id, "done", None, added)
        return added

    def _read_page(self, url: str) -> tuple[dict | None, str | None]:
        """A link's page read by Nines: (what it says, checked; None when it could not be read), and the sentence
        when Nines would not open the address at all (then Claude is not asked either)."""
        try:
            return clean_read(self.reader.read(url)), None
        except productpage.Unsafe as e:
            return None, str(e)
        except productpage.PageError:
            return None, None
        except Exception as e:   # a page that breaks the reader is a page not read; never the address in the log
            log.error("a product's page could not be read: %s", type(e).__name__)
            return None, None

    def _link(self, profile: str, wish_id: str, find_id: str) -> dict | None:
        conn = db.connect(self.cfg.db_path(profile))
        try:
            r = conn.execute("SELECT id, name, shop, url, price, currency, link, read_at FROM finds "
                             "WHERE id = ? AND wish_id = ?", (find_id, wish_id)).fetchone()
            return dict(r) if r else None
        finally:
            conn.close()

    def _save_read(self, profile: str, wish_id: str, find_id: str, read: dict | None) -> bool:
        conn = db.connect(self.cfg.db_path(profile))
        try:
            return save_read(conn, wish_id, find_id, read)
        finally:
            conn.close()

    def read_link(self, profile: str, wish_id: str, find_id: str) -> int:
        """Read a link's page: Nines first; Claude, as a price check of that one page, only when the page gives no
        price (never in the demo closet, nor for an address Nines would not open). Then, once the page has given a
        name, Claude describes the product so it can be judged (`_describe_link`). Returns 1 when a price was kept."""
        row = self._link(profile, wish_id, find_id)
        if row is None:   # removed meanwhile
            self._end(profile, wish_id, "done", None, 0)
            return 0
        self._step(profile, wish_id, "page")
        read, refused = self._read_page(row["url"])
        got, message = self._link_price(profile, wish_id, find_id, read, refused)
        if not refused:
            self._describe_link(profile, wish_id, find_id, read)
        self._end(profile, wish_id, "done", message, got)
        return got

    def _link_price(self, profile: str, wish_id: str, find_id: str, read: dict | None,
                    refused: str | None) -> tuple[int, str | None]:
        """Keep what the page said, and ask Claude for its price when it gave none and Claude may be asked: (1 when a
        price was kept, else 0; the sentence to show, or None)."""
        if self._save_read(profile, wish_id, find_id, read):
            return 1, None
        if refused:
            return 0, refused
        if profile == "demo":
            return 0, f"{NO_PAGE_PRICE} {DEMO_ASKS_NOTHING}"
        try:
            routes = self._usable(1)
        except Refused as e:
            return 0, f"{NO_PAGE_PRICE} {e}"
        find = self._link(profile, wish_id, find_id)   # with the name the page gave, if it gave one
        if find is None:
            return 0, None
        self._step(profile, wish_id, "claude")
        answer = self.asker.prices([find], routes)
        conn = db.connect(self.cfg.db_path(profile))
        try:
            save_prices(conn, wish_id, [find], getattr(answer, "prices", []) or [])
            priced = conn.execute("SELECT price FROM finds WHERE id = ?", (find_id,)).fetchone()
        finally:
            conn.close()
        got = bool(priced and priced["price"] is not None)
        return int(got), None if got else NO_PRICE_AT_ALL

    def _describe_link(self, profile: str, wish_id: str, find_id: str, read: dict | None,
                       routes: tuple[str, ...] | None = None, judge_now: bool = True) -> bool:
        """Ask Claude once to describe a link from what its page says (`page_words`), keep the piece and, with
        `judge_now`, its verdict. Not asked: in the demo closet, for a page that gave no name, for a find already
        described, for the same page whose answer could not be used before, or when Claude cannot be asked (`routes`,
        else worked out here); the link then waits for a later reading. True when a piece was kept."""
        if profile == "demo" or not read or not read.get("name"):
            return False
        conn = db.connect(self.cfg.db_path(profile))
        try:
            row = conn.execute("SELECT piece, verdict FROM finds WHERE id = ? AND wish_id = ?",
                               (find_id, wish_id)).fetchone()
        finally:
            conn.close()
        if row is None or json.loads(row["piece"] or "null"):
            return False
        product = page_words(read)
        asked = fingerprint(shopping.describe_prompt(product))
        if unclear(row["verdict"]) == asked:
            return False
        if routes is None:
            try:
                routes = self._usable(cost=spend.estimate_describe_link())
            except Refused:
                return False
        if not routes:
            return False
        self._step(profile, wish_id, "describe")
        try:
            answer = self.asker.describe(product, routes)
        except (RouteUnavailable, Unreachable):   # not asked, or not reached: described at a later reading
            return False
        except TaggingError:   # asked, with no usable answer
            answer = None
        except Exception as e:   # never the link in the log; the page's price is kept whatever happens here
            log.error("a link could not be described: %s", type(e).__name__)
            return False
        piece = clean_described(answer, read["name"]) if answer is not None else None
        verdict = None
        if piece is not None and judge_now:
            rows, worn = self.closet(profile)
            verdict = judge(rows, worn, [piece], self.listed(profile, (rows, worn)))[0]
        conn = db.connect(self.cfg.db_path(profile))
        try:
            if piece is None:
                mark_unclear(conn, wish_id, find_id, asked)
                return False
            return save_piece(conn, wish_id, find_id, piece, verdict)
        finally:
            conn.close()

    def prices(self, profile: str, wish_id: str, routes: tuple[str, ...], daily: bool = False,
               why_not: str | None = None) -> int:
        """Look the prices of the wish's finds up again, and check them against the closet as it is now. A link's
        page is read by Nines first (in the daily round, only when it was not read in the last day), and a link not
        described yet is described from it when `routes` allow; Claude is asked about the other finds and about the
        pages that gave no price, when `routes` allow (`why_not` says why they do not). A malformed answer still counts as a look, so the daily round does not ask again and again; a look
        that could not ask Claude about a find it found does not count, so it is tried again later."""
        conn = db.connect(self.cfg.db_path(profile))
        try:
            finds = to_price_check(conn, wish_id)
        finally:
            conn.close()
        if not finds:
            self._end(profile, wish_id, "done", NO_FINDS, 0)
            return 0
        links = [f for f in finds if f["link"] and not (daily and read_since(f, _now() - DAY))]
        others = [f for f in finds if not f["link"]]
        n, unread, pages = 0, [], []
        if links:
            self._step(profile, wish_id, "page")
        for f in links:
            read, refused = self._read_page(f["url"])
            if self._save_read(profile, wish_id, f["id"], read):
                n += 1
            elif not refused:
                unread.append(f)
            if not refused:
                pages.append((f, read))
        if routes and profile != "demo":
            for f, read in pages:   # judged with the rest below
                self._describe_link(profile, wish_id, f["id"], read, routes=routes, judge_now=False)
        ask = others + unread
        answer = None
        if ask and routes and profile != "demo":
            self._step(profile, wish_id, "claude")
            try:
                answer = self.asker.prices(ask, routes)
            except TaggingError as e:
                if isinstance(e, RouteUnavailable):
                    raise
                conn = db.connect(self.cfg.db_path(profile))
                try:
                    mark_checked(conn, wish_id)
                finally:
                    conn.close()
                raise
        conn = db.connect(self.cfg.db_path(profile))
        try:
            judged = [f for f in list_finds(conn, wish_id) if f["piece"]]   # a link not described yet: not judged
        finally:
            conn.close()
        verdicts = []
        if judged:
            rows, worn = self.closet(profile)
            verdicts = judge(rows, worn, [f["piece"] for f in judged], self.listed(profile, (rows, worn)))
        conn = db.connect(self.cfg.db_path(profile))
        try:
            if answer is not None:
                n += save_prices(conn, wish_id, ask, getattr(answer, "prices", []) or [])
            elif not others:
                mark_checked(conn, wish_id)   # every find a link: read for the day, whatever the pages gave
            set_verdicts(conn, judged, verdicts)
        finally:
            conn.close()
        message = None
        if ask and answer is None:
            why = DEMO_ASKS_NOTHING if profile == "demo" else why_not or NO_ROUTE
            message = f"{why} {LINKS_ONLY}" if others else f"{SOME_UNREAD} {why}"
        self._end(profile, wish_id, "done", message, n)
        return n

    # ------------------------------------------------------------- the daily round
    def tick(self) -> int:
        """Look up the prices of every wish in the real closet not looked at in the last day. Never the demo
        closet. A link's page is read by Nines first, whether or not Claude can be reached; once Claude cannot be
        reached or the limit is reached, the rest of the round reads only those pages. Returns how many wishes were
        looked at."""
        main = db.connect(self.cfg.db_path("main"))
        try:
            waiting = due(main, _now())
            with_links = {r["wish_id"] for r in main.execute("SELECT DISTINCT wish_id FROM finds WHERE link = 1")}
        finally:
            main.close()
        if not waiting:
            return 0
        routes = self.routes()
        why = None if routes else NO_ROUTE
        done = 0
        for wish_id in waiting:
            if not routes and wish_id not in with_links:
                continue   # nothing to read without Claude: tried again at the next look
            try:
                self._begin("main", wish_id, "prices")
            except Refused:
                continue   # the owner asked for it a moment ago
            try:
                self.prices("main", wish_id, routes, daily=True, why_not=why)
                done += 1
            except (CapReached, RouteUnavailable) as e:
                why = LIMIT if isinstance(e, CapReached) else NO_ROUTE
                self._end("main", wish_id, "failed", why)
                routes = ()
            except TaggingError:
                self._end("main", wish_id, "failed", NOT_UNDERSTOOD)
                done += 1
            except ItemError:
                self._end("main", wish_id, "failed", FAILED)
            except Exception:
                log.error("a daily price check failed\n%s", traceback.format_exc())
                self._end("main", wish_id, "failed", FAILED)
        return done


class PriceScheduler:
    """Looks up the prices of the real closet's finds at most once a day per wish, while the program runs."""

    def __init__(self, shopper: Shopper, check_every: float = CHECK_EVERY, first_wait: float = FIRST_WAIT):
        self.shopper, self.check_every, self.first_wait = shopper, check_every, first_wait
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="price-checks", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        self._stop.wait(self.first_wait)   # let startup finish first
        while not self._stop.is_set():
            try:
                self.shopper.tick()
            except Exception:
                log.exception("price check scheduler error")
            self._stop.wait(self.check_every)


# ------------------------------------------------------------------ the routes
class LinkBody(BaseModel):
    url: str   # a product's page; checked by `Shopper.check_link`
    model_config = {"extra": "forbid"}


class SeenBody(BaseModel):
    wish_ids: list[str] = Field(max_length=SEEN_MAX)   # the wishes whose price news the owner has seen
    model_config = {"extra": "forbid"}


class CodeBody(BaseModel):
    code: str = Field(max_length=200)   # checked by `code_problem`, with the percent or the amount
    percent: float | None = None
    amount: float | None = None
    model_config = {"extra": "forbid"}


def router(shopper: Shopper, state: State, conn_dep: Callable) -> APIRouter:
    r = APIRouter()

    def payload(conn, profile: str, wish_id: str) -> dict:
        run = shopper.run(profile, wish_id)   # first: a run is only over once its finds are saved, so they are read
        wish = wishlist.get_wish(conn, wish_id)
        finds = list_finds(conn, wish_id)
        return {"wish_id": wish_id, "finds": finds, "run": run, "found_at": wish["found_at"],
                "prices_checked_at": wish["prices_checked_at"], "demo": profile == "demo",
                "estimate": shopper.estimate(min(len(finds), PRICE_FINDS_MAX))}

    @r.get("/api/wishlist/{wish_id}/finds")
    def get_finds(wish_id: str, conn=Depends(conn_dep)):
        return payload(conn, state.get("profile"), wish_id)

    async def start(wish_id: str, begin: Callable[[str, str], None]) -> dict:
        profile = state.get("profile")
        try:
            # works out the routes (Claude Code's sign-in is asked, a few seconds at most): off the event loop
            await run_in_threadpool(begin, profile, wish_id)
        except Refused as e:
            raise HTTPException(409, str(e)) from None
        conn = db.connect(shopper.cfg.db_path(profile))
        try:
            return payload(conn, profile, wish_id)
        finally:
            conn.close()

    @r.post("/api/wishlist/{wish_id}/find", status_code=202)
    async def find_some(wish_id: str):
        return await start(wish_id, shopper.start_find)

    @r.post("/api/wishlist/{wish_id}/prices", status_code=202)
    async def check_prices(wish_id: str):
        return await start(wish_id, shopper.start_prices)

    @r.post("/api/wishlist/link", status_code=201)
    async def add_link(body: LinkBody, response: Response):
        profile = state.get("profile")
        try:
            # the address's name is looked up before anything is kept: off the event loop
            wish, created = await run_in_threadpool(shopper.add_link, profile, body.url)
        except productpage.PageError as e:
            raise HTTPException(422, str(e)) from None
        response.status_code = 201 if created else 200
        conn = db.connect(shopper.cfg.db_path(profile))
        try:   # given the way the wishlist gives a wish (`wishlist.router`'s rows)
            return {**wish, "link": None, "drop": None, **on_the_list(conn).get(wish["id"], {})}
        finally:
            conn.close()

    @r.post("/api/wishlist/{wish_id}/link", status_code=202)
    async def add_link_to(wish_id: str, body: LinkBody):
        try:
            return await start(wish_id, lambda profile, wid: shopper.add_link_to(profile, wid, body.url))
        except productpage.PageError as e:
            raise HTTPException(422, str(e)) from None

    def news_now(conn) -> dict:
        # the demo closet has no news: its prices are only ever read when the owner asks there
        return {"news": [] if state.get("profile") == "demo" else news(conn)}

    @r.get("/api/wishlist/news")
    def get_news(conn=Depends(conn_dep)):
        return news_now(conn)

    @r.post("/api/wishlist/news/seen")
    def news_seen(body: SeenBody, conn=Depends(conn_dep)):
        if state.get("profile") != "demo":
            mark_seen(conn, body.wish_ids)
        return news_now(conn)

    @r.delete("/api/wishlist/{wish_id}/finds/{find_id}", status_code=204)
    def delete_find(wish_id: str, find_id: str, conn=Depends(conn_dep)):
        remove_find(conn, wish_id, find_id)
        return Response(status_code=204)

    @r.put("/api/wishlist/{wish_id}/finds/{find_id}/code")
    def put_code(wish_id: str, find_id: str, body: CodeBody, conn=Depends(conn_dep)):
        profile = state.get("profile")
        set_code(conn, wish_id, find_id, body.code, body.percent, body.amount, seen=profile != "demo")
        return payload(conn, profile, wish_id)

    @r.delete("/api/wishlist/{wish_id}/finds/{find_id}/code")
    def delete_code(wish_id: str, find_id: str, conn=Depends(conn_dep)):
        profile = state.get("profile")
        remove_code(conn, wish_id, find_id, seen=profile != "demo")
        return payload(conn, profile, wish_id)

    return r
