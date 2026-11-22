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
price check, only when the page gives no price. A link is not described in the
closet's words, so it is not judged against the closet.

A wish's finds can have their prices looked up again on demand and, while the
program runs, at most once a day (`PriceScheduler`): a link's page read by Nines
first, Claude asked about the rest. Every price seen is kept, and a find whose
latest price is below the highest seen before shows a drop, on the wish and on
its row in the wishlist. The demo closet is never sent to Claude: it cannot
search, a link's page is read there by Nines alone, and the daily round only
ever opens the real closet.

Searches, price checks and reading a link run in the background on a thread of
their own; how each is getting on is held in memory only. Nothing about a wish, a product or
a link is logged.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import traceback
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from . import db, gaps, productpage, spend, wishlist, wouldwork
from .config import Config
from .items import ItemError
from .state import State
from .tagger import shopping
from .tagger.tagging import CapReached, RouteUnavailable, TaggingError

log = logging.getLogger("closet.shop")

DAY = timedelta(hours=24)       # the daily round looks at a wish's prices again once this long has passed
CHECK_EVERY = 3600.0            # seconds between looks at whether a round is due, while the program runs
FIRST_WAIT = 120.0              # seconds after the program starts before the first look
PRICE_FINDS_MAX = 12            # the newest finds still for sale whose prices are looked up, per wish
HISTORY_MAX = 30                # prices shown per find, newest last
URL_MAX = productpage.URL_MAX   # 2000
NAME_MAX = 200
# a wish made from a link is named from its product, cut at a word to this: the wish's name is its page's heading, and
# shops' names run long; the find keeps the whole name
LINK_NAME_MAX = 60
SHOP_MAX = 120
PRICE_MAX = 1_000_000.0
CURRENCY = re.compile(r"^[A-Z]{3}$")

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


class Refused(Exception):
    """A search or price check that cannot start, with the sentence to show."""


class Asker(Protocol):
    """Claude, for shopping (tests stand in for it)."""

    def find(self, wish: dict, routes: tuple[str, ...]) -> shopping.ShopAnswer: ...

    def prices(self, finds: list[dict], routes: tuple[str, ...]) -> shopping.PriceAnswer: ...


class ClaudeAsker:
    """The real one: `tagger/shopping.py` behind the monthly limit, each kind of call recorded as its own purpose."""

    def __init__(self, cfg: Config, state: State, client=None):
        self.client = client
        self.finding = spend.Meter(cfg, state, spend.PURPOSE_SHOP, spend.estimate_shop)
        self.pricing = spend.Meter(cfg, state, spend.PURPOSE_PRICES, spend.estimate_shop)

    def find(self, wish: dict, routes: tuple[str, ...]) -> shopping.ShopAnswer:
        return shopping.find(wish, routes, client=self.client, meter=self.finding)

    def prices(self, finds: list[dict], routes: tuple[str, ...]) -> shopping.PriceAnswer:
        return shopping.prices(finds, routes, client=self.client, meter=self.pricing)


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
    weight = raw.get("weight_class")
    material = _words(raw.get("material"), wouldwork.MATERIAL_MAX)
    try:
        piece = wouldwork.parse_piece({
            "category": raw.get("category"), "color": raw.get("color"), "formality": raw.get("formality"),
            "season": raw.get("season"), "pattern": raw.get("pattern"),
            "weight_class": None if weight in (None, "", "unknown") else weight,
            "rain_proof": raw.get("rain_proof") is True, "name": name[:wouldwork.NAME_MAX], "material": material})
    except wouldwork.PieceError:
        return None
    return {"name": name, "shop": shop, "url": url, "image_url": clean_url(raw.get("image_url")),
            "price": clean_price(price) if price is not None else None, "currency": currency, "piece": piece}


def clean_read(p: productpage.Product) -> dict:
    """What Nines read on a link's page, checked as Claude's answers are: text shortened, a picture only by a web
    address, a price only as a number in range (else none), a currency only as three letters (else none)."""
    return {"name": _words(p.name, NAME_MAX), "shop": _words(p.shop, SHOP_MAX), "image_url": clean_url(p.image_url),
            "price": clean_price(p.price), "currency": clean_currency(p.currency), "available": p.available is not False}


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
def judge(rows: list[dict], worn: list[dict], pieces: list[dict], weighed: dict | None = None) -> list[dict]:
    """Each piece checked against the closet: {verdict, verdict_words, reasons, checked_at}. The closet's gaps are
    worked out once for all of them. `weighed` is the gap list weighed by how the owner lives, as What's missing
    shows it (None until the owner has said): the finds are then judged exactly as "Would this work?" judges a piece."""
    if not pieces:
        return []
    before = weighed if weighed is not None else gaps.find_gaps(rows, worn, {"max_gaps": wouldwork.ALL_GAPS})
    context = (weighed or {}).get("context") or {}
    out = []
    for p in pieces:
        a = wouldwork.check(rows, worn, p, before, context.get("life"), context.get("climate"))
        out.append({"verdict": a["verdict"], "verdict_words": a["verdict_words"], "reasons": a["reasons"],
                    "checked_at": db.now()})
    return out


# ------------------------------------------------------------------ the database
def _point(r: sqlite3.Row) -> dict:
    return {"at": r["at"], "price": r["price"], "currency": r["currency"], "available": bool(r["available"])}


def _history(conn: sqlite3.Connection, find_id: str) -> list[dict]:
    rows = conn.execute("SELECT at, price, currency, available FROM find_prices WHERE find_id = ? ORDER BY at, id",
                        (find_id,)).fetchall()
    return [_point(r) for r in rows]


def drop(history: list[dict]) -> dict | None:
    """The latest price against the highest seen before it in the same currency: {from, to, currency, percent}
    when it is lower, else None."""
    if not history or history[-1]["price"] is None:
        return None
    now = history[-1]
    before = [h["price"] for h in history[:-1] if h["price"] is not None and h["currency"] == now["currency"]]
    if not before or now["price"] >= max(before) - 0.005:
        return None
    was = max(before)
    return {"from": was, "to": now["price"], "currency": now["currency"], "percent": round((was - now["price"]) / was * 100)}


def _find(conn: sqlite3.Connection, r: sqlite3.Row) -> dict:
    f = dict(r)
    f["available"] = bool(f["available"])
    f["link"] = bool(f["link"])
    f["piece"] = json.loads(f["piece"]) if f["piece"] else None   # a link has none ("null")
    f["piece_words"] = wouldwork.describe(f["piece"]) if f["piece"] else None
    verdict = json.loads(f.pop("verdict")) if f["verdict"] else None
    f["verdict"] = verdict["verdict"] if verdict else None
    f["verdict_words"] = verdict["verdict_words"] if verdict else None
    f["reasons"] = verdict["reasons"] if verdict else []
    f["checked_at"] = verdict["checked_at"] if verdict else None
    history = _history(conn, f["id"])
    f["history"] = history[-HISTORY_MAX:]
    f["drop"] = drop(history)
    return f


def list_finds(conn: sqlite3.Connection, wish_id: str) -> list[dict]:
    """A wish's finds, the newest search first and each search's best match first."""
    return [_find(conn, r) for r in conn.execute("SELECT * FROM finds WHERE wish_id = ? ORDER BY found_at DESC, rowid",
                                                 (wish_id,))]


def on_the_list(conn: sqlite3.Connection) -> dict[str, dict]:
    """What the wishlist shows on each open wish's row, by wish: `link`, its newest find sent as a link ({shop, price,
    currency, available}), and `drop`, the biggest drop among its finds ({from, to, currency, percent, shop}); None for
    either when there is none."""
    finds = conn.execute(
        "SELECT f.id, f.wish_id, f.shop, f.price, f.currency, f.available, f.link FROM finds f JOIN wishes w "
        "ON w.id = f.wish_id WHERE w.bought_at IS NULL ORDER BY f.found_at DESC, f.rowid").fetchall()
    history: dict[str, list[dict]] = {}
    for r in conn.execute("SELECT p.find_id, p.at, p.price, p.currency, p.available FROM find_prices p "
                          "JOIN finds f ON f.id = p.find_id JOIN wishes w ON w.id = f.wish_id "
                          "WHERE w.bought_at IS NULL ORDER BY p.at, p.id"):
        history.setdefault(r["find_id"], []).append(_point(r))
    out: dict[str, dict] = {}
    for f in finds:
        row = out.setdefault(f["wish_id"], {"link": None, "drop": None})
        if f["link"] and row["link"] is None:
            row["link"] = {"shop": f["shop"], "price": f["price"], "currency": f["currency"],
                           "available": bool(f["available"])}
        d = drop(history.get(f["id"], []))
        if d and (row["drop"] is None or d["percent"] > row["drop"]["percent"]):
            row["drop"] = {**d, "shop": f["shop"]}
    return out


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
            conn.execute("INSERT INTO find_prices (find_id, at, price, currency, available) VALUES (?, ?, ?, ?, 1)",
                         (find_id, t, f["price"], f["currency"]))
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
    and its price when it gives one, then kept with the others (read by "page"). The page counts as read either way. A
    wish still called by its placeholder is named after the product. True when a price was kept; False when the page
    gave none, or the find is no longer kept."""
    t = db.now()
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT url, currency FROM finds WHERE id = ? AND wish_id = ?", (find_id, wish_id)).fetchone()
        if row is None:
            conn.execute("ROLLBACK")
            return False
        conn.execute("UPDATE finds SET read_at = ? WHERE id = ?", (t, find_id))
        priced = bool(read and read["price"] is not None)
        if read:
            for column in ("name", "shop", "image_url"):
                if read[column]:
                    conn.execute(f"UPDATE finds SET {column} = ? WHERE id = ?", (read[column], find_id))
            if priced:
                currency = read["currency"] or row["currency"]
                conn.execute("UPDATE finds SET price = ?, currency = ?, available = ?, read_by = 'page', updated_at = ? "
                             "WHERE id = ?", (read["price"], currency, int(read["available"]), t, find_id))
                conn.execute("INSERT INTO find_prices (find_id, at, price, currency, available) VALUES (?, ?, ?, ?, ?)",
                             (find_id, t, read["price"], currency, int(read["available"])))
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
    answer is ignored; each read by "claude"), and note that the wish's prices were looked at. Returns how many finds
    were updated."""
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
            if not conn.execute("SELECT 1 FROM finds WHERE id = ? AND wish_id = ?", (f["id"], wish_id)).fetchone():
                continue
            price = clean_price(p.get("price")) if p.get("price") is not None else None
            if p.get("price") is not None and price is None:
                continue   # a price that is not one: not kept
            currency = clean_currency(p.get("currency")) or f["currency"]
            available = p.get("available") is not False
            conn.execute("INSERT INTO find_prices (find_id, at, price, currency, available) VALUES (?, ?, ?, ?, ?)",
                         (f["id"], t, price, currency, int(available)))
            conn.execute("UPDATE finds SET price = ?, currency = ?, available = ?, read_by = 'claude', updated_at = ? "
                         "WHERE id = ?", (price, currency, int(available), t, f["id"]))
            done.add(f["id"])
        conn.execute("UPDATE wishes SET prices_checked_at = ? WHERE id = ?", (t, wish_id))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return len(done)


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


def remove_find(conn: sqlite3.Connection, wish_id: str, find_id: str) -> None:
    if not conn.execute("DELETE FROM finds WHERE id = ? AND wish_id = ?", (find_id, wish_id)).rowcount:
        raise ItemError("That find is not kept with this wish.", 404)


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
        # the gap list weighed by how the owner lives, as "Would this work?" is given it (set by the app); None: plain
        self.weighed: Callable[[str, tuple[list[dict], list[dict]]], dict | None] = lambda profile, inputs: None
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

    def _usable(self, searches: int) -> tuple[str, ...]:
        """The routes to try, or Refused: none can be used, or only the API key can and the request could take
        the month past its limit (the estimate is checked before anything is asked)."""
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
            if limit is None or so_far + spend.estimate_shop(searches) > limit:
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
        rows, worn = self.closet(profile)
        verdicts = judge(rows, worn, [f["piece"] for f in found], self.weighed(profile, (rows, worn)))
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
        price (never in the demo closet, nor for an address Nines would not open). Returns 1 when a price was kept."""
        row = self._link(profile, wish_id, find_id)
        if row is None:   # removed meanwhile
            self._end(profile, wish_id, "done", None, 0)
            return 0
        self._step(profile, wish_id, "page")
        read, refused = self._read_page(row["url"])
        if self._save_read(profile, wish_id, find_id, read):
            self._end(profile, wish_id, "done", None, 1)
            return 1
        if refused:
            self._end(profile, wish_id, "done", refused, 0)
            return 0
        if profile == "demo":
            self._end(profile, wish_id, "done", f"{NO_PAGE_PRICE} {DEMO_ASKS_NOTHING}", 0)
            return 0
        try:
            routes = self._usable(1)
        except Refused as e:
            self._end(profile, wish_id, "done", f"{NO_PAGE_PRICE} {e}", 0)
            return 0
        find = self._link(profile, wish_id, find_id)   # with the name the page gave, if it gave one
        if find is None:
            self._end(profile, wish_id, "done", None, 0)
            return 0
        self._step(profile, wish_id, "claude")
        answer = self.asker.prices([find], routes)
        conn = db.connect(self.cfg.db_path(profile))
        try:
            save_prices(conn, wish_id, [find], getattr(answer, "prices", []) or [])
            priced = conn.execute("SELECT price FROM finds WHERE id = ?", (find_id,)).fetchone()
        finally:
            conn.close()
        got = bool(priced and priced["price"] is not None)
        self._end(profile, wish_id, "done", None if got else NO_PRICE_AT_ALL, int(got))
        return int(got)

    def prices(self, profile: str, wish_id: str, routes: tuple[str, ...], daily: bool = False,
               why_not: str | None = None) -> int:
        """Look the prices of the wish's finds up again, and check them against the closet as it is now. A link's
        page is read by Nines first (in the daily round, only when it was not read in the last day); Claude is asked
        about the other finds and about the pages that gave no price, when `routes` allow (`why_not` says why they do
        not). A malformed answer still counts as a look, so the daily round does not ask again and again; a look
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
        n, unread = 0, []
        if links:
            self._step(profile, wish_id, "page")
        for f in links:
            read, refused = self._read_page(f["url"])
            if self._save_read(profile, wish_id, f["id"], read):
                n += 1
            elif not refused:
                unread.append(f)
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
            judged = [f for f in list_finds(conn, wish_id) if f["piece"]]   # a link is not described: not judged
        finally:
            conn.close()
        verdicts = []
        if judged:
            rows, worn = self.closet(profile)
            verdicts = judge(rows, worn, [f["piece"] for f in judged], self.weighed(profile, (rows, worn)))
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

    @r.delete("/api/wishlist/{wish_id}/finds/{find_id}", status_code=204)
    def delete_find(wish_id: str, find_id: str, conn=Depends(conn_dep)):
        remove_find(conn, wish_id, find_id)
        return Response(status_code=204)

    return r
