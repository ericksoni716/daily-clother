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

Picks are kept in the closet (migration 0048). Nothing about a product is logged.

"On sale now" is a second kind of pick (`kind = "sale"`, migration 0050) in the same machinery: a second question to
Claude (`shopping.sale`, recorded as `spend.PURPOSE_SALE`) told the same about the owner and where to start
(`sale_asked`: the shops they like, `closet/shops.py`; the brands they wear and rate well; the shops they have found
things at before), each product's page then read by Nines itself through the reader a link goes through
(`Shopper.read_page`) and kept only when the page shows a real markdown (`check_sale`: the page's price, not sold out,
SALE_MIN off or more, the price before from the page's own data or else as Claude saw it), then judged and chosen as a
taste pick is. The weekly round makes a sale look too, under the same switch, never on the same day as a taste look,
and only once the owner has looked for sales once; it reads a shown sale's page again once a day (`recheck`, no
Claude): a sale that ended or sold out leaves the card, a price that changed is brought up to date.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import traceback
import uuid
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from . import aboutyou, db, shop, shops, sizes, spend, stylejobs, styleprofile, taste
from .items import ItemError
from .tagger import shopping
from .tagger.tagging import CapReached, RouteUnavailable, TaggingError

log = logging.getLogger("closet.picks")

TASTE, SALE = "taste", "sale"   # the two kinds of pick: chosen from taste, and marked down now ("On sale now")
KINDS = (TASTE, SALE)
KIND = TASTE
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
DAY = timedelta(days=1)    # a weekly look of one kind is never made within a day of a look of the other

# "On sale now"
SALE_MIN = 0.15            # a markdown under 15% is not a sale worth a pick (DECISIONS, "On sale now")
SALE_READS = 8             # pages Nines reads in one sale look, at most (each bounded by productpage.TIMEOUT)
SALE_READ_SECONDS = 60.0   # ...and the most time all of them may take; the rest are dropped
BRANDS_TOLD = 6            # brands a sale look starts from
BEFORE_TOLD = 8            # shops found at before that a sale look starts from
RECHECK_MAX = 12           # shown sale picks whose pages are read again in one round, at most
MISSES_MAX = 2             # a shown sale whose page cannot be read on this many daily reads in a row leaves the card

THIN = "Wear and rate a few more pieces and Nines can look for things you might like."
DEMO = ("The demo closet never sends anything to Claude, so it can't search shops. Open your own closet in Settings "
        "to look for things you might like.")
BUSY = "Nines is already looking. Wait for it to finish."
GONE = "That one is no longer here."
NOTHING = "Claude found nothing new for you this time."
SALE_NOTHING = "Nothing on sale this time that suits you and that Nines could check on the shop's page."
NOT_A_KIND = "Nines looks for things you might like, or for things on sale."
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


def rated_brands(rows: Iterable[Mapping], wears: Iterable[Mapping], n: int = BRANDS_TOLD) -> list[str]:
    """The brands a sale look starts from: those on an active piece the owner loves or likes, or wore on
    `aboutyou.PIECE_WEARS` days or more (never one disliked), in the order the search block says brands
    (`aboutyou.brand_names`); at most `n`."""
    rows = list(rows)
    days = aboutyou._worn_days(wears)
    good = {" ".join(r["brand"].split()).casefold() for r in rows
            if isinstance(r.get("brand"), str) and r["brand"].strip() and r.get("status") != "archived"
            and (r.get("rating") in ("love", "like") or days[r.get("id")] >= aboutyou.PIECE_WEARS)}
    return [b for b in aboutyou.brand_names(rows, days) if b.casefold() in good][:n]


def host_of(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").removeprefix("www.")
    except ValueError:
        return ""


def before_lines(found: Iterable[Mapping], named: Iterable[str], n: int = BEFORE_TOLD) -> list[str]:
    """The shops the owner has found things at before, most recent first (`found`: {shop, url}, newest first), each
    once by its site, as "Example Shop (shop.example)"; not one they named already; at most `n`."""
    skip = {s.casefold() for s in named}
    out, hosts = [], set()
    for f in found:
        host = host_of(f["url"] or "")
        name = " ".join(str(f["shop"] or "").split())[:shop.SHOP_MAX]
        if not host or host in hosts or host.casefold() in skip or name.casefold() in skip:
            continue
        hosts.add(host)
        out.append(host if not name or name.casefold() == host.casefold() else f"{name} ({host})")
        if len(out) >= n:
            break
    return out


def _size_key(size: str) -> str:
    return "".join(size.split()).casefold()


def size_for(saved_sizes: Mapping[str, Mapping], category: str | None, brand: str | None = None) -> str | None:
    """The owner's size for a product of this category: their size in its brand when they saved one, else their usual
    size for that kind; None for an accessory or when none is saved."""
    kind = sizes.kind_of(category)
    entry = saved_sizes.get(kind) or {} if kind else {}
    if brand:
        mine = next((b["size"] for b in entry.get("brands") or [] if b["brand"].casefold() == brand.casefold()), None)
        if mine:
            return mine
    return entry.get("size") or None


def percent_off(price: float, before: float) -> int:
    """How much less, in whole percent: 30 for $84 down from $120."""
    return round((before - price) / before * 100)


def check_sale(f: Mapping, read: Mapping | None, size: str | None) -> dict | None:
    """A product from a sale look, checked against its page as Nines read it (`shop.clean_read`): None when the page
    could not be read, says it is sold out or gives no price, when the price before is not above the page's price, or
    when the markdown is under SALE_MIN; also when the page (or else Claude, reading it) says the owner's `size` is sold
    out. Otherwise the product with the page's price and currency, the price before (`before_by` "page" when the page's
    own data gives it, else "claude" when only Claude saw it, in the page's currency), and `in_stock` True when the
    page lists the owner's size in stock (or else Claude says so), None when nobody said, with `in_stock_by` who said
    it ("page" or "claude")."""
    if not read or not read.get("available") or read.get("price") is None:
        return None
    price = read["price"]
    currency = read.get("currency") or f["currency"]
    if read.get("price_before") is not None and read["price_before"] > price:
        before, by = read["price_before"], "page"
    elif f.get("price_before") is not None and currency == f["currency"] and f["price_before"] > price:
        before, by = f["price_before"], "claude"
    else:
        return None
    if (before - price) / before < SALE_MIN - 1e-9:
        return None
    stock = stock_by = None
    listed = {_size_key(k): v for k, v in (read.get("sizes") or {}).items()}
    if size and _size_key(size) in listed:
        if not listed[_size_key(size)]:
            return None
        stock, stock_by = True, "page"
    elif f.get("size_in_stock") is False:
        return None
    elif f.get("size_in_stock") is True:
        stock, stock_by = True, "claude"
    return {**f, "price": price, "currency": currency, "price_before": before, "before_by": by, "in_stock": stock,
            "in_stock_by": stock_by, "image_url": f.get("image_url") or read.get("image_url")}


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


def looked(conn: sqlite3.Connection, kind: str | None = None) -> bool:
    """Whether the owner has ever tapped Look now and a look was made (of `kind`, or of either)."""
    if kind is None:
        return conn.execute("SELECT 1 FROM pick_looks WHERE source = 'look' LIMIT 1").fetchone() is not None
    return conn.execute("SELECT 1 FROM pick_looks WHERE source = 'look' AND kind = ? LIMIT 1", (kind,)).fetchone() is not None


def weekly_on(conn: sqlite3.Connection) -> bool:
    """The weekly look: as the owner set it, else on once they have tapped Look now (never before)."""
    set_to = _settings(conn)
    return looked(conn) if set_to is None else bool(set_to)


def set_weekly(conn: sqlite3.Connection, on: bool) -> None:
    conn.execute("INSERT INTO pick_settings (id, weekly) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET weekly = "
                 "excluded.weekly", (int(bool(on)),))


def due(conn: sqlite3.Connection, now: datetime, kind: str = TASTE) -> bool:
    """Whether the weekly look of `kind` is due: the switch is on (it covers both kinds), no look of that kind (Look now
    or weekly) was made in the last week, and no look of the other kind in the last day, so one week's allowance is not
    spent at once. A sale look only once the owner has looked for sales themselves."""
    if not weekly_on(conn) or (kind == SALE and not looked(conn, SALE)):
        return False
    if conn.execute("SELECT 1 FROM pick_looks WHERE source IN ('look', 'weekly') AND kind = ? AND at > ? LIMIT 1",
                    (kind, _stamp(now - WEEK))).fetchone():
        return False
    return conn.execute("SELECT 1 FROM pick_looks WHERE kind != ? AND at > ? LIMIT 1",
                        (kind, _stamp(now - DAY))).fetchone() is None


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


def found_before(conn: sqlite3.Connection) -> list[dict]:
    """Where the owner has found things before, newest first: every find of a wish, and every pick they saved."""
    return [dict(r) for r in conn.execute(
        "SELECT shop, url, found_at AS at FROM finds UNION ALL "
        "SELECT shop, url, state_at AS at FROM picks WHERE state = 'saved' ORDER BY at DESC LIMIT 200")]


def sale_asked(conn: sqlite3.Connection, rows: list[dict], wears: list[dict], seed: Mapping | None = None) -> dict:
    """What a sale look tells Claude (`shopping.sale_prompt`): what a look is told (`asked`), and where to start: the
    shops the owner likes, the brands they wear and rate well, the shops they have found things at before."""
    named = shops.names(conn)
    return {**asked(conn, rows, wears, seed), "shops": named, "brands": rated_brands(rows, wears),
            "before": before_lines(found_before(conn), named)}


def _pick(r: sqlite3.Row) -> dict:
    verdict = json.loads(r["verdict"])
    piece = json.loads(r["piece"])
    return {"id": r["id"], "kind": r["kind"], "source": r["source"], "name": r["name"], "shop": r["shop"],
            "url": r["url"], "image_url": r["image_url"], "price": r["price"], "price_before": r["price_before"],
            "currency": r["currency"], "piece": piece, "verdict": verdict.get("verdict"),
            "verdict_words": verdict.get("verdict_words"), "pairs": verdict.get("pairs", 0), "found_at": r["found_at"],
            "state": r["state"], "wish_id": r["wish_id"], "before_by": r["before_by"],
            "in_stock": None if r["in_stock"] is None else bool(r["in_stock"])}


def get_pick(conn: sqlite3.Connection, pick_id: str) -> dict:
    r = conn.execute("SELECT * FROM picks WHERE id = ?", (pick_id,)).fetchone()
    if r is None:
        raise ItemError(GONE, 404)
    return _pick(r)


def list_picks(conn: sqlite3.Connection) -> list[dict]:
    """What the card shows, for each kind (taste first, then sale, at most LIST_MAX of each): the picks not turned down
    and, for a sale, not over; the newest look first and each look's best first."""
    out = []
    for kind in KINDS:
        out += [_pick(r) for r in conn.execute(
            "SELECT * FROM picks WHERE state != 'refused' AND ended_at IS NULL AND kind = ? "
            "ORDER BY found_at DESC, rank, rowid LIMIT ?", (kind, LIST_MAX))]
    return out


def last_look(conn: sqlite3.Connection, kind: str | None = None) -> dict | None:
    r = conn.execute("SELECT source, kind, at, found FROM pick_looks WHERE ? IS NULL OR kind = ? "
                     "ORDER BY at DESC, rowid DESC LIMIT 1", (kind, kind)).fetchone()
    return dict(r) if r else None


def save_look(conn: sqlite3.Connection, source: str, chosen: list[tuple[dict, dict]], seed_id: str | None,
              kind: str = TASTE) -> int:
    """Keep a look and the picks chosen from it, in one go. A page kept meanwhile (another look) is passed over. A sale
    pick keeps its price before, who read it, whether its size is in stock, and that its page was read now.
    Returns how many picks were kept."""
    look_id, t = uuid.uuid4().hex, db.now()
    kept = 0
    conn.execute("BEGIN IMMEDIATE")
    try:
        for rank, (f, v) in enumerate(chosen):
            sale = kind == SALE
            cur = conn.execute(
                "INSERT OR IGNORE INTO picks (id, kind, source, seed_id, look_id, rank, name, shop, url, image_url, "
                "price, price_before, before_by, in_stock, in_stock_by, checked_at, currency, piece, verdict, found_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (uuid.uuid4().hex, kind, source, seed_id, look_id, rank, f["name"], f["shop"], f["url"], f["image_url"],
                 f["price"], f.get("price_before") if sale else None, f.get("before_by") if sale else None,
                 1 if sale and f.get("in_stock") else None, f.get("in_stock_by") if sale and f.get("in_stock") else None,
                 t if sale else None, f["currency"], json.dumps(f["piece"]), json.dumps(v), t))
            kept += cur.rowcount
        conn.execute("INSERT INTO pick_looks (id, source, kind, at, found) VALUES (?, ?, ?, ?, ?)",
                     (look_id, source, kind, t, kept))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return kept


def save(conn: sqlite3.Connection, pick_id: str) -> str:
    """Make a wish from a pick: named after the product, looking for its kind, colour and the rest, with the product
    as its first find (its verdict and price as found, so its price is watched like any find's; a sale's price before
    is kept first in its history, so the wish shows the drop). The pick is marked saved. A pick saved before whose wish is still there gives that wish. Returns the wish's id."""
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
        if p["kind"] == SALE and p["price_before"] is not None:   # the drop shows on the wish, and is not news to you
            conn.execute("INSERT INTO find_prices (find_id, at, price, currency, available) VALUES (?, ?, ?, ?, 1)",
                         (find_id, min(p["found_at"], t), p["price_before"], p["currency"]))
            conn.execute("UPDATE wishes SET news_seen_at = ? WHERE id = ?", (t, wish_id))
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
        self._answered: set[str] = set()   # profiles whose look Claude has answered, for the weekly look under way
        self._tried: dict[str, datetime] = {}   # kind -> a weekly look Claude answered that could not be recorded
        self._lock = threading.Lock()

    # ------------------------------------------------------------- what is going on
    def run(self, profile: str) -> dict | None:
        with self._lock:
            r = self._runs.get(profile)
            return dict(r) if r else None

    def running(self, profile: str) -> bool:
        r = self.run(profile)
        return bool(r and r["state"] == "running")

    def _begin(self, profile: str, source: str, kind: str = TASTE) -> dict | None:
        """Mark a look as running; gives back the run it replaces (a weekly look that cannot finish puts it back)."""
        with self._lock:
            r = self._runs.get(profile)
            if r and r["state"] == "running":
                raise shop.Refused(BUSY)
            self._runs[profile] = {"source": source, "kind": kind, "state": "running", "message": None, "added": None,
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
    def start(self, profile: str, source: str, seed_id: str | None = None, kind: str = TASTE) -> None:
        """Start a look of `kind` (Look now, or More like this with `seed_id`, of the seed's kind). Refused with the
        sentence to show when it cannot start; ItemError (404) for a pick no longer kept."""
        if profile == "demo":
            raise shop.Refused(DEMO)
        rows, worn = self.shopper.closet(profile)
        conn = db.connect(self.shopper.cfg.db_path(profile))
        try:
            if seed_id is not None:
                kind = get_pick(conn, seed_id)["kind"]
            elif not enough(conn, rows, worn):
                raise shop.Refused(THIN)
        finally:
            conn.close()
        if self.running(profile):
            raise shop.Refused(BUSY)
        routes = self.shopper.usable(shopping.FIND_SEARCHES)
        self._begin(profile, source, kind)

        def work() -> None:
            try:
                self.look(profile, source, routes, seed_id, kind)
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
    def look(self, profile: str, source: str, routes: tuple[str, ...], seed_id: str | None = None,
             kind: str = TASTE) -> int:
        """Ask Claude, keep what fits (for a sale, only what its page shows marked down: `check_pages`), judge each
        against the closet and keep the best three. Returns how many."""
        sale = kind == SALE
        rows, worn = self.shopper.closet(profile)
        conn = db.connect(self.shopper.cfg.db_path(profile))
        try:
            seed = get_pick(conn, seed_id)["piece"] if seed_id else None
            told = (sale_asked if sale else asked)(conn, rows, worn, seed)
            saved_sizes = sizes.saved(conn)
        finally:
            conn.close()
        answer = (self.shopper.asker.sale if sale else self.shopper.asker.picks)(told, routes)
        self._answered.add(profile)
        raw = answer.finds if hasattr(answer, "finds") else []
        found, urls = [], set()
        for r in raw[:shopping.MAX_FINDS]:
            f = (shop.clean_sale if sale else shop.clean_find)(r)
            if f and f["url"] not in urls:
                urls.add(f["url"])
                found.append(f)
        conn = db.connect(self.shopper.cfg.db_path(profile))
        try:
            seen = seen_urls(conn)
        finally:
            conn.close()
        found = [f for f in found if f["url"] not in seen]
        if sale:
            found = self.check_pages(found, saved_sizes)
        chosen = []
        if found:
            rows, worn = self.shopper.closet(profile)   # read again: the closet may have changed during the search
            verdicts = shop.judge(rows, worn, [f["piece"] for f in found], self.shopper.listed(profile, (rows, worn)))
            chosen = choose(found, verdicts, seen)
        conn = db.connect(self.shopper.cfg.db_path(profile))
        try:
            kept = save_look(conn, source, chosen, seed_id, kind)
        finally:
            conn.close()
        self._end(profile, "done", None if kept else SALE_NOTHING if sale else NOTHING, kept)
        return kept

    def check_pages(self, found: list[dict], saved_sizes: Mapping[str, Mapping]) -> list[dict]:
        """A sale look's products, each checked against its own page read by Nines (`check_sale`), in Claude's order:
        at most SALE_READS pages and SALE_READ_SECONDS for all of them; a product whose page is not read is dropped."""
        kept, start = [], time.monotonic()
        for f in found[:SALE_READS]:
            if time.monotonic() - start > SALE_READ_SECONDS:
                break
            read, _ = self.shopper.read_page(f["url"])
            checked = check_sale(f, read, size_for(saved_sizes, f["piece"]["category"], (read or {}).get("brand")))
            if checked:
                kept.append(checked)
        return kept

    def recheck(self) -> int:
        """Read each shown sale's page again, at most once a day and RECHECK_MAX in a round, in the owner's own closet
        only, by Nines alone (no Claude): a sale that ended (no longer marked down by SALE_MIN, or a price before the page
        gave is gone), sold out, or whose page could not be read on MISSES_MAX reads in a row leaves the card quietly
        (`ended_at`); a price that changed is brought up to date. Returns how many pages were read."""
        main = db.connect(self.shopper.cfg.db_path("main"))
        try:
            rows = main.execute(
                "SELECT id, url, price, price_before, before_by, currency, piece, in_stock, in_stock_by, misses FROM picks "
                "WHERE kind = ? AND state = 'shown' AND ended_at IS NULL AND (checked_at IS NULL OR checked_at <= ?) "
                "ORDER BY found_at DESC, rank LIMIT ?", (SALE, _stamp(_now() - DAY), RECHECK_MAX)).fetchall()
            saved_sizes = sizes.saved(main)
        finally:
            main.close()
        for r in rows:
            read, _ = self.shopper.read_page(r["url"])
            piece = json.loads(r["piece"])
            # Claude's word on your size still stands (one kept before who said it was kept counts as Claude's); the
            # page's own word is only what the page says now
            claude_said = bool(r["in_stock"]) and r["in_stock_by"] != "page"
            mine = {"price": r["price"], "currency": r["currency"], "image_url": None,
                    "size_in_stock": True if claude_said else None,
                    "price_before": r["price_before"] if r["before_by"] == "claude" else None}
            checked = check_sale(mine, read, size_for(saved_sizes, piece.get("category"), (read or {}).get("brand")))
            t = db.now()
            conn = db.connect(self.shopper.cfg.db_path("main"))
            try:
                if read is None:
                    misses = r["misses"] + 1
                    conn.execute("UPDATE picks SET misses = ?, checked_at = ?, ended_at = ? WHERE id = ?",
                                 (misses, t, t if misses >= MISSES_MAX else None, r["id"]))
                elif checked is None:
                    conn.execute("UPDATE picks SET checked_at = ?, ended_at = ? WHERE id = ?", (t, t, r["id"]))
                else:
                    conn.execute("UPDATE picks SET price = ?, currency = ?, price_before = ?, before_by = ?, "
                                 "in_stock = ?, in_stock_by = ?, misses = 0, checked_at = ? WHERE id = ?",
                                 (checked["price"], checked["currency"], checked["price_before"], checked["before_by"],
                                  1 if checked["in_stock"] else None, checked["in_stock_by"], t, r["id"]))
            finally:
                conn.close()
        return len(rows)

    # ------------------------------------------------------------- the weekly look, on the daily round
    def tick(self) -> int:
        """The weekly looks, then the shown sales' pages read again (`recheck`). A taste look when it is due, else a sale
        look when that is due (`due`: never both in a day). Returns 1 when a look was made."""
        made = self.weekly(TASTE) or self.weekly(SALE)
        try:
            self.recheck()
        except Exception:   # never a product in the log
            log.error("reading the sales' pages again failed\n%s", traceback.format_exc())
        return made

    def weekly(self, kind: str) -> int:
        """The weekly look of `kind`, in the owner's own closet only: when it is on and due, there is enough to go on,
        nothing else is looking, and a route to Claude can be used inside the limit. One that cannot run says nothing
        (the card shows what it showed before) and is tried at the next round; an answer that cannot be used still
        counts as the week's look, so it is not asked again every hour. Returns 1 when a look was made."""
        if self._tried_lately(kind):
            return 0
        main = db.connect(self.shopper.cfg.db_path("main"))
        try:
            if not due(main, _now(), kind):
                return 0
            rows, worn = self.shopper.closet("main")
            if not enough(main, rows, worn):
                return 0
        finally:
            main.close()
        try:
            routes = self.shopper.usable(shopping.FIND_SEARCHES)
            before = self._begin("main", "weekly", kind)
        except shop.Refused:
            return 0
        self._answered.discard("main")
        try:
            self.look("main", "weekly", routes, kind=kind)
            return 1
        except (CapReached, RouteUnavailable):
            self._put_back("main", before)
        except TaggingError:
            self._put_back("main", before)
            self._count_look(kind)
            return 1
        except Exception:
            log.error("a weekly look for things you might like (%s) failed\n%s", kind, traceback.format_exc())
            self._put_back("main", before)
            if "main" in self._answered:   # Claude answered: the week's look is made, whatever became of the answer
                self._count_look(kind)
                return 1
        return 0

    def _count_look(self, kind: str) -> None:
        """A weekly look that kept nothing still counts as the week's look: recorded with no picks, and when even that
        cannot be written, remembered while Nines runs (`_tried_lately`), so it is not asked again every hour."""
        try:
            conn = db.connect(self.shopper.cfg.db_path("main"))
            try:
                save_look(conn, "weekly", [], None, kind)
            finally:
                conn.close()
        except Exception as e:
            log.error("a weekly look (%s) could not be recorded as made: %s", kind, type(e).__name__)
            with self._lock:
                self._tried[kind] = _now()

    def _tried_lately(self, kind: str) -> bool:
        """A look Claude answered that could not be recorded holds the weekly look back as a recorded one would (`due`):
        that kind for a week, the other kind for a day."""
        now = _now()
        with self._lock:
            return any(at > now - (WEEK if k == kind else DAY) for k, at in self._tried.items())


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
            "views": {k: {"looked": looked(conn, k), "last": last_look(conn, k)} for k in KINDS},
            "shops": len(shops.names(conn)),
            "weekly": weekly_on(conn), "enough": enough(conn, rows, worn), "demo": profile == "demo",
            "estimate": picker.estimate(), "offer": current_offer(conn, _now())}


def router(picker: Picker, state, conn_dep: Callable) -> APIRouter:
    r = APIRouter()

    def answer(conn) -> dict:
        return payload(picker, conn, state.get("profile"))

    @r.get("/api/picks")
    def get_picks(conn=Depends(conn_dep)):
        return answer(conn)

    async def begin(source: str, seed_id: str | None = None, kind: str = TASTE) -> dict:
        profile = state.get("profile")
        if kind not in KINDS:
            raise HTTPException(422, NOT_A_KIND)
        try:
            # works out the routes (Claude Code's sign-in is asked, a few seconds at most): off the event loop
            await run_in_threadpool(picker.start, profile, source, seed_id, kind)
        except shop.Refused as e:
            raise HTTPException(409, str(e)) from None
        conn = db.connect(picker.shopper.cfg.db_path(profile))
        try:
            return payload(picker, conn, profile)
        finally:
            conn.close()

    @r.post("/api/picks/look", status_code=202)
    async def look_now(kind: str = TASTE):
        return await begin("look", kind=kind)

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
