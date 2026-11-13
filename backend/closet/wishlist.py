"""What the owner decided about the gaps: the ones hidden ("Not for me") and the wishlist.

Kept in the closet's own database (migration 0007), so the demo closet and the real one keep theirs apart
and backups include them. A gap is known by the `id` the analysis gives it (`closet/gaps.py`): the purchase
it suggests (its category, formality and what it is for), which stays the same when the analysis runs again.
A wish keeps a copy of the gap's name and what to look for, so it stays useful if the gap is no longer found.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from . import db
from .gaps import MAX_GAPS
from .items import ItemError

# Why a gap is "not for me": I have one that is not in the closet yet, I never dress like that, too expensive, other.
REASONS = ("have_one", "never_wear", "too_expensive", "other")
NAME_MAX = 120
NOTE_MAX = 1000


# ------------------------------------------------------------------ marking the analysis
def mark(conn: sqlite3.Connection, answer: dict, offered: int = MAX_GAPS) -> dict:
    """The analysis with each gap marked `state` "open", "hidden" or "wished" (with `hidden_reason` and `wish_id`).

    Up to `offered` open gaps are kept, best first; every hidden or wished gap the analysis found is kept too, in
    its place, so a gap the owner has decided about never pushes a new one off the list. The answer is not changed.
    """
    hidden = {r["gap_id"]: r["reason"] for r in conn.execute("SELECT gap_id, reason FROM hidden_gaps")}
    wished = {r["gap_id"]: r["id"] for r in conn.execute(
        "SELECT gap_id, id FROM wishes WHERE gap_id IS NOT NULL AND bought_at IS NULL")}
    gaps, open_count = [], 0
    for g in answer.get("gaps", []):
        if g["id"] in wished:
            state = "wished"
        elif g["id"] in hidden:
            state = "hidden"
        else:
            if open_count >= offered:
                continue
            open_count += 1
            state = "open"
        gaps.append({**g, "state": state, "hidden_reason": hidden.get(g["id"]) if state == "hidden" else None,
                     "wish_id": wished.get(g["id"])})
    return {**answer, "gaps": gaps}


def _find(gaps: list[dict], gap_id: str) -> dict:
    for g in gaps:
        if g["id"] == gap_id:
            return g
    raise ItemError("That suggestion is no longer in the list. Look again: the closet may have changed.", 404)


# ------------------------------------------------------------------ hiding
def hide(conn: sqlite3.Connection, gap: dict, reason: str | None) -> dict:
    if reason is not None and reason not in REASONS:
        raise ItemError(f"The reason must be one of: {', '.join(REASONS)}.")
    if conn.execute("SELECT 1 FROM wishes WHERE gap_id = ? AND bought_at IS NULL", (gap["id"],)).fetchone():
        raise ItemError("This is on your wishlist. Remove it from the list first.", 409)
    row = {"gap_id": gap["id"], "name": gap["name"], "reason": reason, "hidden_at": db.now()}
    conn.execute("INSERT INTO hidden_gaps (gap_id, name, reason, hidden_at) VALUES (:gap_id, :name, :reason, :hidden_at) "
                 "ON CONFLICT (gap_id) DO UPDATE SET name = excluded.name, reason = excluded.reason", row)
    return dict(conn.execute("SELECT * FROM hidden_gaps WHERE gap_id = ?", (gap["id"],)).fetchone())


def unhide(conn: sqlite3.Connection, gap_id: str) -> None:
    if not conn.execute("DELETE FROM hidden_gaps WHERE gap_id = ?", (gap_id,)).rowcount:
        raise ItemError("That suggestion is not hidden.", 404)


# ------------------------------------------------------------------ the wishlist
def _wish(r: sqlite3.Row) -> dict:
    w = dict(r)
    w["look_for"] = json.loads(w["look_for"]) if w["look_for"] else None
    return w


def get_wish(conn: sqlite3.Connection, wish_id: str) -> dict:
    r = conn.execute("SELECT * FROM wishes WHERE id = ?", (wish_id,)).fetchone()
    if r is None:
        raise ItemError("That wish is not on the list.", 404)
    return _wish(r)


def list_wishes(conn: sqlite3.Connection) -> list[dict]:
    """The wishes still wanted, newest first."""
    return [_wish(r) for r in conn.execute(
        "SELECT * FROM wishes WHERE bought_at IS NULL ORDER BY created_at DESC, rowid DESC")]


def _text(value: object, what: str, limit: int, required: bool = False) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ItemError(f"The {what} must be text.")
    value = value.strip()
    if required and not value:
        raise ItemError(f"Give the {what}.")
    if len(value) > limit:
        raise ItemError(f"The {what} is too long: at most {limit} characters.")
    return value


def add_wish(conn: sqlite3.Connection, gap: dict | None, name: str | None, note: str | None) -> tuple[dict, bool]:
    """Puts a gap (or, with `gap` None, something named by hand) on the wishlist. Returns (wish, created)."""
    note_text = _text(note, "note", NOTE_MAX)
    if gap is not None:
        existing = conn.execute("SELECT * FROM wishes WHERE gap_id = ? AND bought_at IS NULL", (gap["id"],)).fetchone()
        if existing:
            return _wish(existing), False
        name_text, look = gap["name"], json.dumps(gap.get("look_for"))
    else:
        name_text, look = _text(name, "name", NAME_MAX, required=True), None
    wish_id, t = uuid.uuid4().hex, db.now()
    conn.execute("BEGIN")
    try:
        if gap is not None:   # deciding to look for it brings a hidden gap back
            conn.execute("DELETE FROM hidden_gaps WHERE gap_id = ?", (gap["id"],))
        conn.execute("INSERT INTO wishes (id, gap_id, name, look_for, note, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (wish_id, gap["id"] if gap else None, name_text, look, note_text, t, t))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return get_wish(conn, wish_id), True


def update_wish(conn: sqlite3.Connection, wish_id: str, name: str | None, note: str | None) -> dict:
    get_wish(conn, wish_id)
    if name is not None:
        conn.execute("UPDATE wishes SET name = ?, updated_at = ? WHERE id = ?", (_text(name, "name", NAME_MAX, True), db.now(), wish_id))
    if note is not None:
        conn.execute("UPDATE wishes SET note = ?, updated_at = ? WHERE id = ?", (_text(note, "note", NOTE_MAX), db.now(), wish_id))
    return get_wish(conn, wish_id)


def mark_bought(conn: sqlite3.Connection, wish_id: str) -> dict:
    """Takes a wish off the list as bought. The row is kept; the gap is offered again if the analysis still finds it."""
    w = get_wish(conn, wish_id)
    if not w["bought_at"]:
        t = db.now()
        conn.execute("UPDATE wishes SET bought_at = ?, updated_at = ? WHERE id = ?", (t, t, wish_id))
    return get_wish(conn, wish_id)


def remove_wish(conn: sqlite3.Connection, wish_id: str) -> None:
    if not conn.execute("DELETE FROM wishes WHERE id = ?", (wish_id,)).rowcount:
        raise ItemError("That wish is not on the list.", 404)


# ------------------------------------------------------------------ the routes
class HideBody(BaseModel):
    reason: str | None = None
    model_config = {"extra": "forbid"}


class WishNew(BaseModel):
    gap_id: str | None = None
    name: str | None = None
    note: str | None = None
    model_config = {"extra": "forbid"}


class WishChange(BaseModel):
    name: str | None = None
    note: str | None = None
    model_config = {"extra": "forbid"}


def router(conn_dep: Callable, gaps_now: Callable[[], dict], protected: list) -> APIRouter:
    """The routes for hiding gaps and for the wishlist. `gaps_now()` gives the open closet's analysis (it may take
    seconds the first time, so it is called in a worker thread)."""
    r = APIRouter(dependencies=protected)

    async def gap(gap_id: str) -> dict:
        return _find((await run_in_threadpool(gaps_now)).get("gaps", []), gap_id)

    @r.post("/api/gaps/{gap_id}/hide")
    async def hide_gap(gap_id: str, body: HideBody | None = None, conn=Depends(conn_dep)):
        return hide(conn, await gap(gap_id), body.reason if body else None)

    @r.delete("/api/gaps/{gap_id}/hide", status_code=204)
    def unhide_gap(gap_id: str, conn=Depends(conn_dep)):
        unhide(conn, gap_id)
        return Response(status_code=204)

    @r.get("/api/wishlist")
    def get_wishlist(conn=Depends(conn_dep)):
        return {"wishes": list_wishes(conn)}

    @r.post("/api/wishlist")
    async def new_wish(body: WishNew, response: Response, conn=Depends(conn_dep)):
        if body.gap_id is not None and body.name is not None:
            raise HTTPException(422, "Give either the suggestion or a name, not both.")
        found = await gap(body.gap_id) if body.gap_id is not None else None
        wish, created = add_wish(conn, found, body.name, body.note)
        response.status_code = 201 if created else 200
        return wish

    @r.patch("/api/wishlist/{wish_id}")
    def change_wish(wish_id: str, body: WishChange, conn=Depends(conn_dep)):
        return update_wish(conn, wish_id, body.name, body.note)

    @r.post("/api/wishlist/{wish_id}/bought")
    def bought(wish_id: str, conn=Depends(conn_dep)):
        return mark_bought(conn, wish_id)

    @r.delete("/api/wishlist/{wish_id}", status_code=204)
    def delete_wish(wish_id: str, conn=Depends(conn_dep)):
        remove_wish(conn, wish_id)
        return Response(status_code=204)

    return r
