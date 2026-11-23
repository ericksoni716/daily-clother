"""Your sizes: the owner's usual size for each kind of piece, and a brand's own where it fits differently (Settings,
Everyday, "Your sizes"; migration 0047).

Sizes are free short text, as the owner would say them ("M", "32x32", "10.5 US", "40R"): sizing differs by kind, by
country and by shop, and the one reader is Claude searching shops ("Find some", `aboutyou.py`), which reads words.
Kept in the closet's own database, so the demo closet has its own and a backup takes them along.

When no size is saved for a kind, the size most common on the owner's own items of that kind (each item's `size`, on
its page) is offered as a suggestion to confirm with a tap; it is never used until it is saved. Nothing here asks
Claude.
"""
from __future__ import annotations

import sqlite3
from collections import Counter
from collections.abc import Callable, Iterable

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from . import db, outfits, trips
from .items import ItemError

# the kinds of piece a size is kept for, in the order Settings shows them, each with the words the page uses
KINDS = (("tops", "Tops"), ("knitwear", "Knitwear"), ("trousers", "Trousers and jeans"),
         ("jackets", "Jackets and coats"), ("shoes", "Shoes"))
KIND_KEYS = tuple(k for k, _ in KINDS)
# each kind of clothing trips counts (from the taxonomy's categories) to the kind its size is kept for
_FROM_TRIPS = {"tops": "tops", "knits": "knitwear", "bottoms": "trousers", "outer": "jackets"}
MAX_SIZE = 20       # characters in a size
MAX_BRAND = 40      # characters in a brand's name
MAX_BRANDS = 10     # brands that fit differently, per kind

NOT_A_KIND = "Sizes are kept for tops, knitwear, trousers and jeans, jackets and coats, and shoes."
TOO_MANY = f"You can keep at most {MAX_BRANDS} brands that fit differently for each kind."


def kind_of(category: object) -> str | None:
    """The kind a closet category's size is kept under ("shirt" is "tops", "boots" is "shoes"); None for an
    accessory, "other" or no category."""
    if not isinstance(category, str):
        return None
    if category in outfits.PLACE_CATEGORIES["shoes"]:
        return "shoes"
    return _FROM_TRIPS.get(trips.KIND_OF.get(category, ""))


def tidy(value: object, limit: int, what: str) -> str:
    """A size or a brand as kept: one line, without space at either end ('' when empty)."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ItemError(f"Write the {what} as text.")
    text = " ".join(value.split())
    if len(text) > limit:
        raise ItemError(f"A {what} can be at most {limit} characters long.")
    return text


def _check_kind(kind: object) -> str:
    if kind not in KIND_KEYS:
        raise ItemError(NOT_A_KIND, 404)
    return str(kind)


def suggested(rows: Iterable[dict]) -> dict[str, str]:
    """For each kind, the size most common on the owner's active items of that kind, as written on the most of them
    (ties: the first in alphabetical order). Pure: `rows` are item rows with `status`, `category` and `size`."""
    seen: dict[str, Counter] = {}
    spelt: dict[tuple[str, str], Counter] = {}
    for r in rows:
        kind = kind_of(r.get("category"))
        size = " ".join(r["size"].split()) if isinstance(r.get("size"), str) else ""
        if r.get("status") == "archived" or not kind or not size or len(size) > MAX_SIZE:
            continue
        key = size.casefold()
        seen.setdefault(kind, Counter())[key] += 1
        spelt.setdefault((kind, key), Counter())[size] += 1
    out = {}
    for kind, counts in seen.items():
        key = min(counts, key=lambda k: (-counts[k], k))
        names = spelt[(kind, key)]
        out[kind] = min(names, key=lambda s: (-names[s], s))
    return out


def saved(conn: sqlite3.Connection) -> dict[str, dict]:
    """What is saved, by kind: {kind: {"size": str | None, "brands": [{"brand", "size"}]}} for every kind, the brands
    in alphabetical order."""
    out = {k: {"size": None, "brands": []} for k in KIND_KEYS}
    for r in conn.execute("SELECT kind, brand, size FROM sizes ORDER BY kind, brand COLLATE NOCASE"):
        if r["kind"] not in out:
            continue
        if r["brand"]:
            out[r["kind"]]["brands"].append({"brand": r["brand"], "size": r["size"]})
        else:
            out[r["kind"]]["size"] = r["size"]
    return out


def current(conn: sqlite3.Connection) -> dict:
    """Your sizes as Settings shows them: {"kinds": [{kind, label, size, suggested, brands}]}, in KINDS order.
    `suggested` is the size most common on your items of that kind, only while none is saved."""
    have = saved(conn)
    guess = suggested(dict(r) for r in conn.execute("SELECT status, category, size FROM items"))
    return {"kinds": [{"kind": k, "label": label, "size": have[k]["size"],
                       "suggested": None if have[k]["size"] else guess.get(k),
                       "brands": have[k]["brands"]} for k, label in KINDS],
            "max_size": MAX_SIZE, "max_brand": MAX_BRAND, "max_brands": MAX_BRANDS}


def set_size(conn: sqlite3.Connection, kind: object, size: object) -> dict:
    """Keep the usual size for a kind; an empty one clears it. Gives `current`."""
    kind = _check_kind(kind)
    size = tidy(size, MAX_SIZE, "size")
    if size:
        conn.execute("INSERT INTO sizes (kind, brand, size, updated_at) VALUES (?, '', ?, ?) "
                     "ON CONFLICT (kind, brand) DO UPDATE SET size = excluded.size, updated_at = excluded.updated_at",
                     (kind, size, db.now()))
    else:
        conn.execute("DELETE FROM sizes WHERE kind = ? AND brand = ''", (kind,))
    return current(conn)


def set_brand(conn: sqlite3.Connection, kind: object, brand: object, size: object) -> dict:
    """Keep a brand's own size for a kind ("in Example Brand: L"); an empty size takes the brand off. Gives
    `current`."""
    kind = _check_kind(kind)
    brand = tidy(brand, MAX_BRAND, "brand")
    if not brand:
        raise ItemError("Write the brand's name first.")
    size = tidy(size, MAX_SIZE, "size")
    if not size:
        conn.execute("DELETE FROM sizes WHERE kind = ? AND brand = ?", (kind, brand))
        return current(conn)
    exists = conn.execute("SELECT 1 FROM sizes WHERE kind = ? AND brand = ?", (kind, brand)).fetchone()
    count = conn.execute("SELECT COUNT(*) FROM sizes WHERE kind = ? AND brand != ''", (kind,)).fetchone()[0]
    if not exists and count >= MAX_BRANDS:
        raise ItemError(TOO_MANY)
    # the brand as last written ("example brand" written again as "Example Brand" takes the new spelling)
    conn.execute("INSERT INTO sizes (kind, brand, size, updated_at) VALUES (?, ?, ?, ?) "
                 "ON CONFLICT (kind, brand) DO UPDATE SET brand = excluded.brand, size = excluded.size, "
                 "updated_at = excluded.updated_at", (kind, brand, size, db.now()))
    return current(conn)


# ------------------------------------------------------------------ the routes
class SizeBody(BaseModel):
    size: str | None = None
    model_config = {"extra": "forbid"}


class BrandSizeBody(BaseModel):
    brand: str
    size: str | None = None
    model_config = {"extra": "forbid"}


def router(conn_dep: Callable) -> APIRouter:
    r = APIRouter()

    @r.get("/api/sizes")
    def get_sizes(conn=Depends(conn_dep)):
        return current(conn)

    @r.put("/api/sizes/{kind}")
    def put_size(kind: str, body: SizeBody, conn=Depends(conn_dep)):
        return set_size(conn, kind, body.size)

    @r.put("/api/sizes/{kind}/brand")
    def put_brand_size(kind: str, body: BrandSizeBody, conn=Depends(conn_dep)):
        return set_brand(conn, kind, body.brand, body.size)

    return r
