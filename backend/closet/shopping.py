"""Per-closet shopping choices, kept separate from the cached gap analysis."""
from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from . import db

REASONS = ("already_owned", "not_my_style", "too_expensive", "other")
BODY_LIMIT = 32_768
NAME_LIMIT = 200
DETAILS_LIMIT = 4000
NOTE_LIMIT = 2000
ID_LIMIT = 200


async def _body(request: Request, allowed: set[str]) -> dict:
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > BODY_LIMIT:
            raise HTTPException(413, "This request is too long. Use fewer words.")
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "The request was not valid JSON.")
    if not isinstance(body, dict):
        raise HTTPException(422, "Send the fields as a JSON object.")
    if set(body) - allowed:
        raise HTTPException(422, "The request contains fields that cannot be changed.")
    return body


def _text(value: object, label: str, limit: int, *, required: bool = False) -> str:
    if not isinstance(value, str) or len(value) > limit:
        raise HTTPException(422, f"{label} must be text with no more than {limit} characters.")
    if required and not value.strip():
        raise HTTPException(422, f"{label} cannot be empty.")
    return value


def _state(gap: dict, hidden: bool = False, reason: str | None = None, wished: bool = False) -> dict:
    return {**gap, "hidden": hidden, "hidden_reason": reason, "wished": wished}


def overlay(conn: sqlite3.Connection, answer: dict) -> dict:
    choices = {r["gap_id"]: r for r in conn.execute(
        "SELECT g.gap_id, g.hidden, g.hidden_reason, w.id AS wish_id FROM gap_choices g "
        "LEFT JOIN wishes w ON w.gap_id = g.gap_id AND w.bought_at IS NULL")}
    # Never attach these flags to the cached dictionaries themselves.
    return {**answer, "gaps": [
        _state(g, bool(choices[g["id"]]["hidden"]) if g["id"] in choices else False,
               choices[g["id"]]["hidden_reason"] if g["id"] in choices else None,
               g["id"] in choices and choices[g["id"]]["wish_id"] is not None)
        for g in answer["gaps"]
    ]}


def _snapshot(conn: sqlite3.Connection, gap_id: str, analyze: Callable) -> dict:
    _text(gap_id, "The suggestion id", ID_LIMIT, required=True)
    found = next((g for g in analyze(conn)["gaps"] if g["id"] == gap_id), None)
    if found is not None:
        return found
    saved = conn.execute("SELECT snapshot FROM gap_choices WHERE gap_id = ?", (gap_id,)).fetchone()
    if saved:
        return json.loads(saved["snapshot"])
    raise HTTPException(404, "That suggestion is no longer available. Refresh What's missing and try again.")


def _save_snapshot(conn: sqlite3.Connection, gap: dict) -> None:
    conn.execute(
        "INSERT INTO gap_choices (gap_id, snapshot) VALUES (?, ?) "
        "ON CONFLICT(gap_id) DO UPDATE SET snapshot = excluded.snapshot",
        (gap["id"], json.dumps(gap)),
    )


def _wish(row: sqlite3.Row) -> dict:
    return {k: json.loads(row[k]) if k == "look_for" and row[k] else row[k]
            for k in ("id", "gap_id", "name", "look_for", "details", "note", "created_at")}


def _active(conn: sqlite3.Connection, wish_id: str) -> sqlite3.Row:
    _text(wish_id, "The wish id", ID_LIMIT, required=True)
    row = conn.execute("SELECT * FROM wishes WHERE id = ? AND bought_at IS NULL", (wish_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "That wish is no longer on the wishlist.")
    return row


def router(conn_dep: Callable, analyze: Callable, protected: list) -> APIRouter:
    routes = APIRouter(dependencies=protected)

    @routes.get("/api/gaps/hidden")
    def hidden_gaps(conn=Depends(conn_dep)):
        return {"gaps": [_state(json.loads(r["snapshot"]), True, r["hidden_reason"])
                         for r in conn.execute("SELECT * FROM gap_choices WHERE hidden = 1 ORDER BY gap_id")]}

    @routes.put("/api/gaps/{gap_id}/hidden")
    async def hide(gap_id: str, request: Request, conn=Depends(conn_dep)):
        body = await _body(request, {"reason"})
        reason = body.get("reason")
        if reason is not None and (not isinstance(reason, str) or reason not in REASONS):
            raise HTTPException(422, "Choose already owned, not my style, too expensive, other, or no reason.")

        def work():
            gap = _snapshot(conn, gap_id, analyze)
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                if conn.execute("SELECT 1 FROM wishes WHERE gap_id = ? AND bought_at IS NULL", (gap_id,)).fetchone():
                    raise HTTPException(409, "Remove this piece from your wishlist before hiding it.")
                _save_snapshot(conn, gap)
                conn.execute("UPDATE gap_choices SET hidden = 1, hidden_reason = ? WHERE gap_id = ?", (reason, gap_id))
            return _state(gap, True, reason)

        return await run_in_threadpool(work)

    @routes.delete("/api/gaps/{gap_id}/hidden", status_code=204)
    def unhide(gap_id: str, conn=Depends(conn_dep)):
        _text(gap_id, "The suggestion id", ID_LIMIT, required=True)
        conn.execute("UPDATE gap_choices SET hidden = 0, hidden_reason = NULL WHERE gap_id = ?", (gap_id,))
        return Response(status_code=204)

    @routes.get("/api/wishlist")
    def wishlist(conn=Depends(conn_dep)):
        return {"wishes": [_wish(r) for r in conn.execute(
            "SELECT * FROM wishes WHERE bought_at IS NULL ORDER BY created_at DESC, id")]}

    @routes.post("/api/wishlist")
    async def add_wish(request: Request, conn=Depends(conn_dep)):
        body = await _body(request, {"gap_id", "name", "details", "note"})
        gap_id = body.get("gap_id")
        if "gap_id" in body:
            _text(gap_id, "The suggestion id", ID_LIMIT, required=True)
            if set(body) != {"gap_id"}:
                raise HTTPException(422, "Use a suggestion id on its own, or a name for a wish of your own.")
        else:
            _text(body.get("name"), "The name", NAME_LIMIT, required=True)
            _text(body.get("details", ""), "The details", DETAILS_LIMIT)
            _text(body.get("note", ""), "The note", NOTE_LIMIT)

        def work():
            gap = _snapshot(conn, gap_id, analyze) if gap_id is not None else None
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                if gap is not None:
                    existing = conn.execute(
                        "SELECT * FROM wishes WHERE gap_id = ? AND bought_at IS NULL", (gap_id,)).fetchone()
                    if existing:
                        return JSONResponse(_wish(existing), status_code=200)
                    _save_snapshot(conn, gap)
                    conn.execute("UPDATE gap_choices SET hidden = 0, hidden_reason = NULL WHERE gap_id = ?", (gap_id,))
                wish_id = uuid.uuid4().hex
                conn.execute(
                    "INSERT INTO wishes (id, gap_id, name, look_for, details, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (wish_id, gap_id, gap["name"] if gap else body["name"].strip(),
                     json.dumps(gap["look_for"]) if gap else None, "" if gap else body.get("details", ""),
                     "" if gap else body.get("note", ""), db.now()),
                )
                result = _wish(_active(conn, wish_id))
            return JSONResponse(result, status_code=201)

        return await run_in_threadpool(work)

    @routes.patch("/api/wishlist/{wish_id}")
    async def edit_note(wish_id: str, request: Request, conn=Depends(conn_dep)):
        body = await _body(request, {"note"})
        note = _text(body.get("note"), "The note", NOTE_LIMIT)

        def work():
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                _active(conn, wish_id)
                conn.execute("UPDATE wishes SET note = ? WHERE id = ?", (note, wish_id))
                return _wish(_active(conn, wish_id))

        return await run_in_threadpool(work)

    @routes.post("/api/wishlist/{wish_id}/bought", status_code=204)
    def bought(wish_id: str, conn=Depends(conn_dep)):
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            _active(conn, wish_id)
            conn.execute("UPDATE wishes SET bought_at = ? WHERE id = ?", (db.now(), wish_id))
        return Response(status_code=204)

    @routes.delete("/api/wishlist/{wish_id}", status_code=204)
    def remove(wish_id: str, conn=Depends(conn_dep)):
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            _active(conn, wish_id)
            conn.execute("DELETE FROM wishes WHERE id = ?", (wish_id,))
        return Response(status_code=204)

    return routes
