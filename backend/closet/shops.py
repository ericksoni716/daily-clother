"""Shops you like: a short list the owner keeps (Settings, Everyday, "Shops you like"; migration 0050).

Up to MAX_SHOPS shop names or sites, as the owner would write them ("Example Shop", "shop.example.com"). Each is
cleaned before it is kept (`clean`): one line, no address parts beyond the site (a pasted link keeps only its host,
without "www."), at most MAX_NAME characters, never twice. The list is read by "On sale now" (`closet/picks.py`) as
the first places a sale look starts from, and by nothing else for now; it is sent to Claude with that look, and the
Settings row says so. Kept in the closet's own database, so the demo closet has its own and a backup takes them along.
Nothing here asks Claude or opens a page.
"""
from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from . import db
from .items import ItemError

MAX_SHOPS = 12       # shops kept
MAX_NAME = 60        # characters in a shop's name or site

TOO_MANY = f"You can keep at most {MAX_SHOPS} shops. Remove one first."
EMPTY = "Write a shop's name or its site first."
TOO_LONG = f"A shop's name can be at most {MAX_NAME} characters long."
NOT_TEXT = "Write the shop's name as text."
ALREADY = "That shop is on your list already."
GONE = "That shop is no longer on your list."

_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*://", re.I)


def clean(value: object) -> str:
    """A shop's name or site as kept: one line without space at either end, control characters taken out; a pasted
    address kept as its site alone ("https://www.shop.example/sale?x=1" is "shop.example"). ItemError with the
    sentence when it is empty, too long or not text."""
    if not isinstance(value, str):
        raise ItemError(NOT_TEXT)
    text = " ".join("".join(c if c.isprintable() else " " for c in value).split())
    if _SCHEME.match(text) or (" " not in text and "/" in text and "." in text.split("/", 1)[0]):
        try:
            host = urlsplit(text if _SCHEME.match(text) else f"https://{text}").hostname or ""
        except ValueError:
            host = ""
        text = host.removeprefix("www.")
    text = text.strip(" ,;")
    if not text:
        raise ItemError(EMPTY)
    if len(text) > MAX_NAME:
        raise ItemError(TOO_LONG)
    return text


def names(conn: sqlite3.Connection) -> list[str]:
    """The shops kept, in the order they were added."""
    return [r["name"] for r in conn.execute("SELECT name FROM shops ORDER BY id")]


def current(conn: sqlite3.Connection) -> dict:
    """Shops you like as Settings shows them: {"shops": [{id, name}], "max_shops", "max_name"}."""
    return {"shops": [{"id": r["id"], "name": r["name"]} for r in conn.execute("SELECT id, name FROM shops ORDER BY id")],
            "max_shops": MAX_SHOPS, "max_name": MAX_NAME}


def add(conn: sqlite3.Connection, name: object) -> dict:
    """Keep one more shop. ItemError when it does not fit, is kept already or the list is full. Gives `current`."""
    name = clean(name)
    if conn.execute("SELECT 1 FROM shops WHERE name = ?", (name,)).fetchone():
        raise ItemError(ALREADY)
    if conn.execute("SELECT COUNT(*) FROM shops").fetchone()[0] >= MAX_SHOPS:
        raise ItemError(TOO_MANY)
    conn.execute("INSERT INTO shops (name, added_at) VALUES (?, ?)", (name, db.now()))
    return current(conn)


def remove(conn: sqlite3.Connection, shop_id: int) -> dict:
    """Take a shop off the list (ItemError 404 when it is not on it). Gives `current`."""
    if conn.execute("DELETE FROM shops WHERE id = ?", (shop_id,)).rowcount == 0:
        raise ItemError(GONE, 404)
    return current(conn)


# ------------------------------------------------------------------ the routes
class ShopBody(BaseModel):
    name: str
    model_config = {"extra": "forbid"}


def router(conn_dep: Callable) -> APIRouter:
    r = APIRouter()

    @r.get("/api/shops")
    def get_shops(conn=Depends(conn_dep)):
        return current(conn)

    @r.post("/api/shops")
    def post_shop(body: ShopBody, conn=Depends(conn_dep)):
        return add(conn, body.name)

    @r.delete("/api/shops/{shop_id}")
    def delete_shop(shop_id: int, conn=Depends(conn_dep)):
        return remove(conn, shop_id)

    return r
