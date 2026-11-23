"""You might like: three things a week the owner might like, chosen from their taste rather than from a gap.

A look asks Claude (`tagger/shopping.py`'s `picks`, through the same routes and the same monthly limit as "Find
some", recorded with the purpose `spend.PURPOSE_PICKS`) for up to eight products on sale now, told what the closet
says about the owner as a whole (`aboutyou.for_picks`), what they already have plenty of and what they said "Not for
me" to. Every product is checked as a search's finds are (`shop.clean_find`), judged against the closet
(`shop.judge`), and the best three are kept (`choose`): never one the closet says would be hard to wear or only
repeats what is there, never a page shown before, and of different kinds of piece where it can. Fewer than three,
or none, is an answer; nothing is ever made up.

A look runs when the owner taps Look now, on More like this (seeded with that pick's described values), and by
itself once a week on the daily round (`tick`, called by `shop.PriceScheduler`): only in the owner's own closet,
only when a route to Claude can be used and the estimate fits the limit, only when the weekly look is on (`weekly`,
which is on by default once the owner has tapped Look now once, and off before), and never when there is too little
to go on (`enough`). A weekly look that cannot run says nothing and is tried at the next round.

Save makes a wish from a pick, with the product as its first find, so its price is watched like any find's. Not for
me hides it for good (Undo brings it back) and is told to the next look; after a few alike, a line may be offered
for Your style (`offers`), kept only on a tap, through the same code the conversation's offers use
(`stylejobs.keep`).

Picks are kept in the closet (migration 0048). A pick has a `kind` ("taste" here) and a place for the price before a
markdown, for "On sale now" (BACKLOG, "Finding clothes you might like", step 5), which is not built. Nothing about a
product is logged.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import traceback
import uuid
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from . import aboutyou, db, shop, spend, stylejobs, styleprofile, taste
from .items import ItemError
from .tagger import shopping
from .tagger.tagging import CapReached, RouteUnavailable, TaggingError

log = logging.getLogger("closet.picks")

KIND = "taste"             # the one kind of pick built; "sale" is step 5's
SOURCES = ("look", "weekly", "more")
SHOWN = 3                  # picks kept from one look, at most
DROP = ("hard_to_wear", "have_it")   # what the closet says would not work, or only repeats it
RANK = {"fills_gap": 0, "adds": 1, "too_small": 2}
WEEK = timedelta(days=7)
PLENTY_MIN = 3             # this many active pieces of one kind and colour is "plenty", told to the look
PLENTY_MAX = 8             # ...at most this many such lines
REFUSED_TOLD = 12          # the newest "Not for me" told to the next look
LIST_MAX = 30              # picks the card is given, newest first (it shows three, the rest behind "See earlier ones")
OFFER_MIN = 3              # this many "Not for me" alike, and a line may be offered for Your style
OFFER_SHOWN = timedelta(days=1)   # a line kept stays on the card, with Undo, this long
NAME_TOLD = 80             # characters of a turned-down product's name told to the next look
BRIGHT = ("red", "pink", "orange", "yellow", "purple")

THIN = "Wear and rate a few more pieces and Nines can look for things you might like."
DEMO = ("The demo closet never sends anything to Claude, so it can't search shops. Open your own closet in Settings "
        "to look for things you might like.")
BUSY = "Nines is already looking. Wait for it to finish."
GONE = "That one is no longer here."
NOTHING = "Claude found nothing new for you this time."
OFFER_GONE = "That line is no longer offered."

# a line offered for Your style after OFFER_MIN "Not for me" alike: (the line, in the owner's voice; why)
PATTERN_LINES = {"stripe": ("Nothing striped.", "stripes"), "plaid": ("No plaid.", "plaid"),
                 "floral": ("No florals.", "florals"), "camo": ("No camouflage.", "camouflage"),
                 "graphic": ("No graphic prints.", "graphic prints")}
NUMBER = {3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"}


def _now() -> datetime:
    """Now, in UTC (tests move it)."""
    return datetime.now(UTC)


def _stamp(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _plain(v: object) -> str:
    return " ".join(str(v).replace("_", " ").split())


# ------------------------------------------------------------------ what a look is told (pure)
def plenty(rows: Iterable[Mapping]) -> list[str]:
    """What the closet already has plenty of: PLENTY_MIN or more active pieces (none disliked) of one kind, colour and
    pattern, most first, at most PLENTY_MAX: "crewneck sweater in navy: 4 already"."""
    counts: Counter = Counter()
    for r in rows:
        if r.get("status") == "archived" or r.get("rating") == "dislike" or not r.get("color"):
            continue
        kind = r.get("kind") or r.get("category")
        if not kind:
            continue
        pattern = r.get("pattern") if r.get("pattern") not in (None, "", "solid") else ""
        counts[(_plain(kind), _plain(r["color"]), _plain(pattern))] += 1
    lines = [(n, key) for key, n in counts.items() if n >= PLENTY_MIN]
    lines.sort(key=lambda t: (-t[0], t[1]))
    return [f"{kind} in {colour}{f' {pattern}' if pattern else ''}: {n} already"
            for n, (kind, colour, pattern) in lines[:PLENTY_MAX]]


def refused_line(name: str, piece: Mapping) -> str:
    """A product turned down, for the next look: "orange tee: Example cotton tee"."""
    what = " ".join(_plain(v) for v in (piece.get("color"),
                                         piece.get("pattern") if piece.get("pattern") not in (None, "solid") else None,
                                         piece.get("category")) if v)
    return f"{what}: {' '.join(name.split())[:NAME_TOLD]}"


def like_of(piece: Mapping) -> dict:
    """What "More like this" tells the look about the pick it was asked from: its described values."""
    return {k: piece.get(k) for k, _ in shopping.LIKE_FIELDS if piece.get(k)}


def choose(found: list[dict], verdicts: list[dict], seen: set[str], n: int = SHOWN) -> list[tuple[dict, dict]]:
    """The best `n` of a look's products, each with its verdict: none the closet says would be hard to wear or only
    repeats it (`DROP`), none whose page was shown before (`seen`) or twice in the answer; the ones that fill a gap
    first, then those that add something, in Claude's order; of different kinds of piece where it can, then the next
    best whatever their kind."""
    pool, urls = [], set()
    for i, (f, v) in enumerate(zip(found, verdicts, strict=True)):
        if v["verdict"] in DROP or f["url"] in seen or f["url"] in urls:
            continue
        urls.add(f["url"])
        pool.append((RANK.get(v["verdict"], len(RANK)), i, f, v))
    pool.sort(key=lambda t: (t[0], t[1]))
    chosen, kinds = [], set()
    for t in pool:
        if len(chosen) < n and t[2]["piece"]["category"] not in kinds:
            chosen.append(t)
            kinds.add(t[2]["piece"]["category"])
    for t in pool:
        if len(chosen) < n and t not in chosen:
            chosen.append(t)
    chosen.sort(key=lambda t: (t[0], t[1]))
    return [(t[2], t[3]) for t in chosen]


def offers(refused: list[Mapping]) -> list[dict]:
    """The lines a run of "Not for me" could offer for Your style, each {text, said}: OFFER_MIN or more turned-down
    pieces in bright colours, in one pattern, or of one kind (in that order). Rules, not Claude: small and plain."""
    out = []
    bright = [p for p in refused if p.get("color") in BRIGHT]
    if len(bright) >= OFFER_MIN:
        out.append({"text": "Nothing bright.", "said": f"You passed on {NUMBER.get(len(bright), len(bright))} bright colours."})
    patterns = Counter(p.get("pattern") for p in refused if p.get("pattern") in PATTERN_LINES)
    for pattern, n in sorted(patterns.items(), key=lambda t: (-t[1], t[0])):
        if n >= OFFER_MIN:
            text, words = PATTERN_LINES[pattern]
            out.append({"text": text, "said": f"You passed on {NUMBER.get(n, n)} {words}."})
    kinds = Counter(p.get("category") for p in refused if p.get("category"))
    for kind, n in sorted(kinds.items(), key=lambda t: (-t[1], t[0])):
        if n >= OFFER_MIN:
            plural = aboutyou._plural(kind)
            out.append({"text": f"No {plural}.", "said": f"You passed on {NUMBER.get(n, n)} {plural}."})
    return out


# ------------------------------------------------------------------ the database
def _settings(conn: sqlite3.Connection) -> int | None:
    r = conn.execute("SELECT weekly FROM pick_settings WHERE id = 1").fetchone()
    return None if r is None or r["weekly"] is None else int(r["weekly"])


def looked(conn: sqlite3.Connection) -> bool:
    """Whether the owner has ever tapped Look now and a look was made."""
    return conn.execute("SELECT 1 FROM pick_looks WHERE source = 'look' LIMIT 1").fetchone() is not None


def weekly_on(conn: sqlite3.Connection) -> bool:
    """The weekly look: as the owner set it, else on once they have tapped Look now (never before)."""
    set_to = _settings(conn)
    return looked(conn) if set_to is None else bool(set_to)


def set_weekly(conn: sqlite3.Connection, on: bool) -> None:
    conn.execute("INSERT INTO pick_settings (id, weekly) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET weekly = "
                 "excluded.weekly", (int(bool(on)),))


def due(conn: sqlite3.Connection, now: datetime) -> bool:
    """Whether the weekly look is due: it is on, and no look (Look now or weekly) was made in the last week."""
    if not weekly_on(conn):
        return False
    return conn.execute("SELECT 1 FROM pick_looks WHERE source IN ('look', 'weekly') AND at > ? LIMIT 1",
                        (_stamp(now - WEEK),)).fetchone() is None


def own_lines(conn: sqlite3.Connection) -> bool:
    """Whether Your style has a line of the owner's own (not one of the starting lines)."""
    return any(line["source"] != "start" for line in styleprofile.lines(conn))


def enough(conn: sqlite3.Connection, rows: list[dict], wears: list[dict]) -> bool:
    """Whether there is enough to go on: taste has evidence by its own thresholds, or Your style has a line of the
    owner's own."""
    return bool(taste.learn(rows, wears)["used"]) or own_lines(conn)


def seen_urls(conn: sqlite3.Connection) -> set[str]:
    return {r["url"] for r in conn.execute("SELECT url FROM picks")}


def _refused(conn: sqlite3.Connection, limit: int | None = None) -> list[sqlite3.Row]:
    sql = "SELECT name, piece FROM picks WHERE state = 'refused' ORDER BY state_at DESC, rowid DESC"
    return conn.execute(sql + (" LIMIT ?" if limit else ""), (limit,) if limit else ()).fetchall()


def asked(conn: sqlite3.Connection, rows: list[dict], wears: list[dict], seed: Mapping | None = None) -> dict:
    """What a look tells Claude (`shopping.picks_prompt`)."""
    return {"about": aboutyou.for_picks(conn, rows, wears), "plenty": plenty(rows),
            "refused": [refused_line(r["name"], json.loads(r["piece"])) for r in _refused(conn, REFUSED_TOLD)],
            "like": like_of(seed) if seed else None}


def _pick(r: sqlite3.Row) -> dict:
    verdict = json.loads(r["verdict"])
    piece = json.loads(r["piece"])
    return {"id": r["id"], "kind": r["kind"], "source": r["source"], "name": r["name"], "shop": r["shop"],
            "url": r["url"], "image_url": r["image_url"], "price": r["price"], "price_before": r["price_before"],
            "currency": r["currency"], "piece": piece, "verdict": verdict.get("verdict"),
            "verdict_words": verdict.get("verdict_words"), "pairs": verdict.get("pairs", 0), "found_at": r["found_at"],
            "state": r["state"], "wish_id": r["wish_id"]}


def get_pick(conn: sqlite3.Connection, pick_id: str) -> dict:
    r = conn.execute("SELECT * FROM picks WHERE id = ?", (pick_id,)).fetchone()
    if r is None:
        raise ItemError(GONE, 404)
    return _pick(r)


def list_picks(conn: sqlite3.Connection) -> list[dict]:
    """What the card shows: the picks not turned down, the newest look first and each look's best first."""
    return [_pick(r) for r in conn.execute(
        "SELECT * FROM picks WHERE state != 'refused' AND kind = ? ORDER BY found_at DESC, rank, rowid LIMIT ?",
        (KIND, LIST_MAX))]


def last_look(conn: sqlite3.Connection) -> dict | None:
    r = conn.execute("SELECT source, at, found FROM pick_looks ORDER BY at DESC, rowid DESC LIMIT 1").fetchone()
    return dict(r) if r else None


def save_look(conn: sqlite3.Connection, source: str, chosen: list[tuple[dict, dict]], seed_id: str | None) -> int:
    """Keep a look and the picks chosen from it, in one go. A page kept meanwhile (another look) is passed over.
    Returns how many picks were kept."""
    look_id, t = uuid.uuid4().hex, db.now()
    kept = 0
    conn.execute("BEGIN IMMEDIATE")
    try:
        for rank, (f, v) in enumerate(chosen):
            cur = conn.execute(
                "INSERT OR IGNORE INTO picks (id, kind, source, seed_id, look_id, rank, name, shop, url, image_url, "
                "price, currency, piece, verdict, found_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (uuid.uuid4().hex, KIND, source, seed_id, look_id, rank, f["name"], f["shop"], f["url"], f["image_url"],
                 f["price"], f["currency"], json.dumps(f["piece"]), json.dumps(v), t))
            kept += cur.rowcount
        conn.execute("INSERT INTO pick_looks (id, source, at, found) VALUES (?, ?, ?, ?)", (look_id, source, t, kept))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return kept


def save(conn: sqlite3.Connection, pick_id: str) -> str:
    """Make a wish from a pick: named after the product, looking for its kind, colour and the rest, with the product
    as its first find (its verdict and price as found, so its price is watched like any find's). The pick is marked
    saved. A pick saved before whose wish is still there gives that wish. Returns the wish's id."""
    p = get_pick(conn, pick_id)
    if p["state"] == "saved" and p["wish_id"] and conn.execute(
            "SELECT 1 FROM wishes WHERE id = ?", (p["wish_id"],)).fetchone():
        return p["wish_id"]
    piece = p["piece"]
    look = {"category": piece["category"], "formality": piece.get("formality"), "season": piece.get("season"),
            "weight_class": piece.get("weight_class"), "colors": [piece["color"]] if piece.get("color") else [],
            "pattern": piece.get("pattern"), "material": piece.get("material")}
    r = conn.execute("SELECT verdict FROM picks WHERE id = ?", (pick_id,)).fetchone()
    wish_id, find_id, t = uuid.uuid4().hex, uuid.uuid4().hex, db.now()
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("INSERT INTO wishes (id, gap_id, name, look_for, note, created_at, updated_at, found_at) "
                     "VALUES (?, NULL, ?, ?, '', ?, ?, ?)",
                     (wish_id, shop.shortened(p["name"], shop.LINK_NAME_MAX), json.dumps(look), t, t, t))
        conn.execute("INSERT INTO finds (id, wish_id, name, shop, url, image_url, price, currency, available, piece, "
                     "verdict, found_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)",
                     (find_id, wish_id, p["name"][:shop.NAME_MAX], p["shop"][:shop.SHOP_MAX], p["url"], p["image_url"],
                      p["price"], p["currency"], json.dumps(piece), r["verdict"], t, t))
        conn.execute("INSERT INTO find_prices (find_id, at, price, currency, available) VALUES (?, ?, ?, ?, 1)",
                     (find_id, t, p["price"], p["currency"]))
        conn.execute("UPDATE picks SET state = 'saved', state_at = ?, wish_id = ? WHERE id = ?", (t, wish_id, pick_id))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return wish_id


def refuse(conn: sqlite3.Connection, pick_id: str) -> None:
    """Not for me: the pick is hidden for good (until Undo) and told to the next look; a line for Your style may be
    offered (`offer_now`)."""
    get_pick(conn, pick_id)
    conn.execute("UPDATE picks SET state = 'refused', state_at = ? WHERE id = ? AND state = 'shown'", (db.now(), pick_id))
    offer_now(conn)


def undo_refuse(conn: sqlite3.Connection, pick_id: str) -> None:
    """Undo Not for me: the pick is shown again. A line offered on the strength of it, and not answered, goes when it
    no longer holds."""
    get_pick(conn, pick_id)
    conn.execute("UPDATE picks SET state = 'shown', state_at = NULL WHERE id = ? AND state = 'refused'", (pick_id,))
    still = {o["text"] for o in offers([json.loads(r["piece"]) for r in _refused(conn)])}
    for r in conn.execute("SELECT id, text FROM pick_offers WHERE state = 'offered'").fetchall():
        if r["text"] not in still:
            conn.execute("DELETE FROM pick_offers WHERE id = ?", (r["id"],))


def offer_now(conn: sqlite3.Connection) -> None:
    """Offer one line for Your style when the turned-down picks share a colour family, a pattern or a kind (`offers`):
    never while another is offered, never a line offered before or already in Your style."""
    if conn.execute("SELECT 1 FROM pick_offers WHERE state = 'offered'").fetchone():
        return
    before = {r["text"] for r in conn.execute("SELECT text FROM pick_offers")}
    for o in offers([json.loads(r["piece"]) for r in _refused(conn)]):
        if o["text"] in before or styleprofile.has_line(conn, o["text"]):
            continue
        conn.execute("INSERT INTO pick_offers (id, text, said, state, at) VALUES (?, ?, ?, 'offered', ?)",
                     (uuid.uuid4().hex, o["text"], o["said"], db.now()))
        return


def current_offer(conn: sqlite3.Connection, now: datetime) -> dict | None:
    """The line on offer, or one kept in the last day (for Undo): {id, text, said, state}."""
    r = conn.execute("SELECT id, text, said, state, at FROM pick_offers WHERE state = 'offered' OR (state = 'saved' "
                     "AND at > ?) ORDER BY state = 'offered' DESC, at DESC LIMIT 1", (_stamp(now - OFFER_SHOWN),)).fetchone()
    return {k: r[k] for k in ("id", "text", "said", "state")} if r else None


def settle_offer(conn: sqlite3.Connection, offer_id: str, save_it: bool, undo: bool = False) -> None:
    """The owner's answer to the line offered: kept in Your style (`save_it`, through `stylejobs.keep`, as a line
    offered in a conversation is), not kept, or taken back (`undo`, then offered again). Answering twice changes
    nothing. Raises `stylejobs.Refused` with a sentence when the line is not offered."""
    r = conn.execute("SELECT * FROM pick_offers WHERE id = ?", (offer_id,)).fetchone()
    if r is None:
        raise stylejobs.Refused(OFFER_GONE)
    if r["state"] != ("saved" if undo else "offered"):
        return
    thing = {"kind": "style", "text": r["text"], "line_id": r["line_id"]}
    conn.execute("BEGIN IMMEDIATE")
    try:
        if undo:
            stylejobs.unkeep(conn, thing)
            state = "offered"
        elif save_it:
            thing.pop("line_id")
            stylejobs.keep(conn, thing, OFFER_GONE)
            state = "saved"
        else:
            state = "dismissed"
        conn.execute("UPDATE pick_offers SET state = ?, line_id = ?, at = ? WHERE id = ?",
                     (state, thing.get("line_id") if state == "saved" else None, db.now(), offer_id))
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


# ------------------------------------------------------------------ the work
class Picker:
    """Looks for things the owner might like, one look at a time per closet, on a thread of its own (or on the
    daily round's). Built on the `shop.Shopper`: its routes, its limit check, its closet and its stand-in for Claude."""

    def __init__(self, shopper: shop.Shopper):
        self.shopper = shopper
        self._runs: dict[str, dict] = {}   # profile -> the last or current look; in memory only
        self._lock = threading.Lock()

    # ------------------------------------------------------------- what is going on
    def run(self, profile: str) -> dict | None:
        with self._lock:
            r = self._runs.get(profile)
            return dict(r) if r else None

    def running(self, profile: str) -> bool:
        r = self.run(profile)
        return bool(r and r["state"] == "running")

    def _begin(self, profile: str, source: str) -> dict | None:
        """Mark a look as running; gives back the run it replaces (a weekly look that cannot finish puts it back)."""
        with self._lock:
            r = self._runs.get(profile)
            if r and r["state"] == "running":
                raise shop.Refused(BUSY)
            self._runs[profile] = {"source": source, "state": "running", "message": None, "added": None,
                                   "started_at": db.now(), "finished_at": None}
            return r

    def _end(self, profile: str, state: str, message: str | None = None, added: int | None = None) -> None:
        with self._lock:
            r = self._runs.get(profile)
            if r:
                r.update(state=state, message=message, added=added, finished_at=db.now())

    def _put_back(self, profile: str, before: dict | None) -> None:
        with self._lock:
            if before is None:
                self._runs.pop(profile, None)
            else:
                self._runs[profile] = before

    def estimate(self) -> dict:
        """The most a look would cost through the API key, said beside Look now."""
        return {"api": spend.api_allowed(self.shopper.state),
                "look_usd": round(spend.estimate_shop(shopping.FIND_SEARCHES), 6)}

    # ------------------------------------------------------------- starting
    def start(self, profile: str, source: str, seed_id: str | None = None) -> None:
        """Start a look (Look now, or More like this with `seed_id`). Refused with the sentence to show when it cannot
        start; ItemError (404) for a pick no longer kept."""
        if profile == "demo":
            raise shop.Refused(DEMO)
        rows, worn = self.shopper.closet(profile)
        conn = db.connect(self.shopper.cfg.db_path(profile))
        try:
            if seed_id is not None:
                get_pick(conn, seed_id)
            elif not enough(conn, rows, worn):
                raise shop.Refused(THIN)
        finally:
            conn.close()
        if self.running(profile):
            raise shop.Refused(BUSY)
        routes = self.shopper.usable(shopping.FIND_SEARCHES)
        self._begin(profile, source)

        def work() -> None:
            try:
                self.look(profile, source, routes, seed_id)
            except CapReached:
                self._end(profile, "failed", shop.LIMIT)
            except RouteUnavailable:
                self._end(profile, "failed", shop.NO_ROUTE)
            except TaggingError:
                self._end(profile, "failed", shop.NOT_UNDERSTOOD)
            except Exception:   # never a product in the log: only that it failed, and where
                log.error("a look for things you might like failed\n%s", traceback.format_exc())
                self._end(profile, "failed", shop.FAILED)

        try:
            threading.Thread(target=work, name="picks", daemon=True).start()
        except Exception:
            log.exception("a look for things you might like could not start")
            self._end(profile, "failed", shop.FAILED)

    # ------------------------------------------------------------- the look itself
    def look(self, profile: str, source: str, routes: tuple[str, ...], seed_id: str | None = None) -> int:
        """Ask Claude, keep what fits, judge each against the closet and keep the best three. Returns how many."""
        rows, worn = self.shopper.closet(profile)
        conn = db.connect(self.shopper.cfg.db_path(profile))
        try:
            seed = get_pick(conn, seed_id)["piece"] if seed_id else None
            told = asked(conn, rows, worn, seed)
        finally:
            conn.close()
        answer = self.shopper.asker.picks(told, routes)
        raw = answer.finds if hasattr(answer, "finds") else []
        found, urls = [], set()
        for r in raw[:shopping.MAX_FINDS]:
            f = shop.clean_find(r)
            if f and f["url"] not in urls:
                urls.add(f["url"])
                found.append(f)
        conn = db.connect(self.shopper.cfg.db_path(profile))
        try:
            seen = seen_urls(conn)
        finally:
            conn.close()
        found = [f for f in found if f["url"] not in seen]
        chosen = []
        if found:
            rows, worn = self.shopper.closet(profile)   # read again: the closet may have changed during the search
            verdicts = shop.judge(rows, worn, [f["piece"] for f in found], self.shopper.listed(profile, (rows, worn)))
            chosen = choose(found, verdicts, seen)
        conn = db.connect(self.shopper.cfg.db_path(profile))
        try:
            kept = save_look(conn, source, chosen, seed_id)
        finally:
            conn.close()
        self._end(profile, "done", None if kept else NOTHING, kept)
        return kept

    # ------------------------------------------------------------- the weekly look, on the daily round
    def tick(self) -> int:
        """The weekly look, in the owner's own closet only: when it is on and due, there is enough to go on, nothing
        else is looking, and a route to Claude can be used inside the limit. One that cannot run says nothing (the
        card shows what it showed before) and is tried at the next round; an answer that cannot be used still counts
        as the week's look, so it is not asked again every hour. Returns 1 when a look was made."""
        main = db.connect(self.shopper.cfg.db_path("main"))
        try:
            if not due(main, _now()):
                return 0
            rows, worn = self.shopper.closet("main")
            if not enough(main, rows, worn):
                return 0
        finally:
            main.close()
        try:
            routes = self.shopper.usable(shopping.FIND_SEARCHES)
            before = self._begin("main", "weekly")
        except shop.Refused:
            return 0
        try:
            self.look("main", "weekly", routes)
            return 1
        except (CapReached, RouteUnavailable):
            self._put_back("main", before)
        except TaggingError:
            self._put_back("main", before)
            conn = db.connect(self.shopper.cfg.db_path("main"))
            try:
                save_look(conn, "weekly", [], None)
            finally:
                conn.close()
            return 1
        except Exception:
            log.error("a weekly look for things you might like failed\n%s", traceback.format_exc())
            self._put_back("main", before)
        return 0


# ------------------------------------------------------------------ the routes
class WeeklyBody(BaseModel):
    weekly: bool
    model_config = {"extra": "forbid"}


class OfferBody(BaseModel):
    save: bool = False
    undo: bool = False
    model_config = {"extra": "forbid"}


def payload(picker: Picker, conn: sqlite3.Connection, profile: str) -> dict:
    """Everything the card needs, in one answer."""
    run = picker.run(profile)   # first: a look is only over once its picks are kept, so they are read
    rows, worn = picker.shopper.closet(profile)
    return {"picks": list_picks(conn), "run": run, "last": last_look(conn), "looked": looked(conn),
            "weekly": weekly_on(conn), "enough": enough(conn, rows, worn), "demo": profile == "demo",
            "estimate": picker.estimate(), "offer": current_offer(conn, _now())}


def router(picker: Picker, state, conn_dep: Callable) -> APIRouter:
    r = APIRouter()

    def answer(conn) -> dict:
        return payload(picker, conn, state.get("profile"))

    @r.get("/api/picks")
    def get_picks(conn=Depends(conn_dep)):
        return answer(conn)

    async def begin(source: str, seed_id: str | None = None) -> dict:
        profile = state.get("profile")
        try:
            # works out the routes (Claude Code's sign-in is asked, a few seconds at most): off the event loop
            await run_in_threadpool(picker.start, profile, source, seed_id)
        except shop.Refused as e:
            raise HTTPException(409, str(e)) from None
        conn = db.connect(picker.shopper.cfg.db_path(profile))
        try:
            return payload(picker, conn, profile)
        finally:
            conn.close()

    @r.post("/api/picks/look", status_code=202)
    async def look_now():
        return await begin("look")

    @r.post("/api/picks/{pick_id}/more", status_code=202)
    async def more_like(pick_id: str):
        return await begin("more", pick_id)

    @r.post("/api/picks/{pick_id}/save")
    def save_pick(pick_id: str, conn=Depends(conn_dep)):
        wish_id = save(conn, pick_id)
        return {**answer(conn), "wish_id": wish_id}

    @r.post("/api/picks/{pick_id}/refuse")
    def refuse_pick(pick_id: str, conn=Depends(conn_dep)):
        refuse(conn, pick_id)
        return answer(conn)

    @r.delete("/api/picks/{pick_id}/refuse")
    def undo_refuse_pick(pick_id: str, conn=Depends(conn_dep)):
        undo_refuse(conn, pick_id)
        return answer(conn)

    @r.put("/api/picks/weekly")
    def put_weekly(body: WeeklyBody, conn=Depends(conn_dep)):
        set_weekly(conn, body.weekly)
        return answer(conn)

    @r.post("/api/picks/offer/{offer_id}")
    def answer_offer(offer_id: str, body: OfferBody, conn=Depends(conn_dep)):
        try:
            settle_offer(conn, offer_id, body.save, body.undo)
        except stylejobs.Refused as e:
            raise HTTPException(422, str(e)) from None
        return answer(conn)

    return r
