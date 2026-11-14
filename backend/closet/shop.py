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

A wish's finds can have their prices looked up again on demand and, while the
program runs, at most once a day (`PriceScheduler`); every price seen is kept,
and a find whose latest price is below the highest seen before shows a drop.
The demo closet is never sent to Claude: it cannot search, and the daily round
only ever opens the real closet.

Searches and price checks run in the background on a thread of their own; how
each is getting on is held in memory only. Nothing about a wish, a product or
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

from . import db, gaps, spend, wishlist, wouldwork
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
URL_MAX = 2000
NAME_MAX = 200
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
NOT_SAVED = "Closet found some but could not keep them: your closet was busy saving something else. Try again."
BUSY = "Closet is already looking for this one. Wait for it to finish."
NO_FINDS = "There is nothing to check yet: find some first."


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


# ------------------------------------------------------------------ "Would this work?" for each find
def judge(rows: list[dict], worn: list[dict], pieces: list[dict]) -> list[dict]:
    """Each piece checked against the closet: {verdict, verdict_words, reasons, checked_at}. The closet's gaps are
    worked out once for all of them."""
    if not pieces:
        return []
    before = gaps.find_gaps(rows, worn, {"max_gaps": wouldwork.ALL_GAPS})
    out = []
    for p in pieces:
        a = wouldwork.check(rows, worn, p, before)
        out.append({"verdict": a["verdict"], "verdict_words": a["verdict_words"], "reasons": a["reasons"],
                    "checked_at": db.now()})
    return out


# ------------------------------------------------------------------ the database
def _history(conn: sqlite3.Connection, find_id: str) -> list[dict]:
    rows = conn.execute("SELECT at, price, currency, available FROM find_prices WHERE find_id = ? ORDER BY at, id",
                        (find_id,)).fetchall()
    return [{"at": r["at"], "price": r["price"], "currency": r["currency"], "available": bool(r["available"])}
            for r in rows]


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
    f["piece"] = json.loads(f["piece"])
    f["piece_words"] = wouldwork.describe(f["piece"])
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
        "SELECT id, name, shop, url, price, currency FROM finds WHERE wish_id = ? ORDER BY found_at DESC, rowid LIMIT ?",
        (wish_id, PRICE_FINDS_MAX))]


def save_prices(conn: sqlite3.Connection, wish_id: str, finds: list[dict], seen: list[object]) -> int:
    """Keep the prices Claude saw for the finds it was asked about (matched by their page; anything else in the
    answer is ignored), and note that the wish's prices were looked at. Returns how many finds were updated."""
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
            price = clean_price(p.get("price")) if p.get("price") is not None else None
            if p.get("price") is not None and price is None:
                continue   # a price that is not one: not kept
            currency = clean_currency(p.get("currency")) or f["currency"]
            available = p.get("available") is not False
            conn.execute("INSERT INTO find_prices (find_id, at, price, currency, available) VALUES (?, ?, ?, ?, ?)",
                         (f["id"], t, price, currency, int(available)))
            conn.execute("UPDATE finds SET price = ?, currency = ?, available = ?, updated_at = ? WHERE id = ?",
                         (price, currency, int(available), t, f["id"]))
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
    """Searches and price checks, one at a time per wish, each on a thread of its own."""

    def __init__(self, cfg: Config, state: State, closet: Closet, routes: Routes, asker: Asker):
        self.cfg, self.state, self.closet, self.routes, self.asker = cfg, state, closet, routes, asker
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
            self._runs[(profile, wish_id)] = {"kind": kind, "state": "running", "message": None, "added": None,
                                              "started_at": db.now(), "finished_at": None}

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
        if profile == "demo":
            raise Refused(DEMO)
        self._wish(profile, wish_id)
        conn = db.connect(self.cfg.db_path(profile))
        try:
            n = len(to_price_check(conn, wish_id))
        finally:
            conn.close()
        if not n:
            raise Refused(NO_FINDS)
        if self.running(profile, wish_id):
            raise Refused(BUSY)
        routes = self._usable(min(shopping.PRICE_SEARCHES, n))
        self._begin(profile, wish_id, "prices")
        self._thread(lambda: self.prices(profile, wish_id, routes), profile, wish_id)

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
        verdicts = judge(rows, worn, [f["piece"] for f in found])
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

    def prices(self, profile: str, wish_id: str, routes: tuple[str, ...]) -> int:
        """Look the prices of the wish's finds up again, and check them against the closet as it is now. A
        malformed answer still counts as a look, so the daily round does not ask again and again."""
        conn = db.connect(self.cfg.db_path(profile))
        try:
            finds = to_price_check(conn, wish_id)
        finally:
            conn.close()
        if not finds:
            self._end(profile, wish_id, "done", NO_FINDS, 0)
            return 0
        try:
            answer = self.asker.prices(finds, routes)
        except TaggingError as e:
            if isinstance(e, RouteUnavailable):
                raise
            conn = db.connect(self.cfg.db_path(profile))
            try:
                mark_checked(conn, wish_id)
            finally:
                conn.close()
            raise
        rows, worn = self.closet(profile)
        conn = db.connect(self.cfg.db_path(profile))
        try:
            kept = list_finds(conn, wish_id)
        finally:
            conn.close()
        verdicts = judge(rows, worn, [f["piece"] for f in kept])
        conn = db.connect(self.cfg.db_path(profile))
        try:
            n = save_prices(conn, wish_id, finds, getattr(answer, "prices", []) or [])
            set_verdicts(conn, kept, verdicts)
        finally:
            conn.close()
        self._end(profile, wish_id, "done", None, n)
        return n

    # ------------------------------------------------------------- the daily round
    def tick(self) -> int:
        """Look up the prices of every wish in the real closet not looked at in the last day. Never the demo
        closet. Stops when Claude cannot be reached or the limit is reached; returns how many wishes were looked at."""
        main = db.connect(self.cfg.db_path("main"))
        try:
            waiting = due(main, _now())
        finally:
            main.close()
        if not waiting:
            return 0
        routes = self.routes()
        if not routes:
            return 0
        done = 0
        for wish_id in waiting:
            try:
                self._begin("main", wish_id, "prices")
            except Refused:
                continue   # the owner asked for it a moment ago
            try:
                self.prices("main", wish_id, routes)
                done += 1
            except (CapReached, RouteUnavailable) as e:
                self._end("main", wish_id, "failed", LIMIT if isinstance(e, CapReached) else NO_ROUTE)
                break
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
def router(shopper: Shopper, state: State, conn_dep: Callable, protected: list) -> APIRouter:
    r = APIRouter(dependencies=protected)

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

    @r.delete("/api/wishlist/{wish_id}/finds/{find_id}", status_code=204)
    def delete_find(wish_id: str, find_id: str, conn=Depends(conn_dep)):
        remove_find(conn, wish_id, find_id)
        return Response(status_code=204)

    return r
