"""Outfits you keep: an outfit saved without wearing it, found under Worn and worn again in a tap.

No name is asked; one can be given later. The same pieces kept twice are one outfit, and keeping them again says
so (`already`). A piece that leaves the closet stays part of the outfit, listed in `gone`; wearing the outfit fills
its place as "Wear this again" does (`closet/today.py`, `again_of`). Removing an outfit can be undone: it is set
aside (`removed_at`) and brought back by `restore`, or by keeping the same pieces again.
"""
from __future__ import annotations

import json
import uuid
from collections.abc import Callable

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from . import db, items, plans

MAX_NAME = 60     # characters in an outfit's name


def _err(message: str, status: int = 422) -> items.ItemError:
    return items.ItemError(message, status)


def same_key(pieces: dict) -> str:
    """The pieces' ids, sorted and joined: what makes two kept outfits the same."""
    return ",".join(sorted(plans.ids_of(pieces)))


def _shape(conn, r) -> dict:
    pieces = json.loads(r["pieces"])
    return {"id": r["id"], "name": r["name"], "pieces": pieces, "gone": plans.gone_of(conn, pieces),
            "created_at": r["created_at"], "updated_at": r["updated_at"]}


def _row(conn, outfit_id: object, removed: bool = False):
    if not isinstance(outfit_id, str):
        raise _err("That outfit is not among the outfits you keep.", 404)
    r = conn.execute("SELECT * FROM kept_outfits WHERE id = ?", (outfit_id,)).fetchone()
    if r is None or (r["removed_at"] is not None) != removed:
        raise _err("That outfit is not among the outfits you keep.", 404)
    return r


def get(conn, outfit_id: str) -> dict:
    return _shape(conn, _row(conn, outfit_id))


def _check_name(name: object) -> str | None:
    if name is None:
        return None
    if not isinstance(name, str):
        raise _err("A name is a few words.")
    tidy = " ".join(name.split())
    if len(tidy) > MAX_NAME:
        raise _err(f"Keep the name to {MAX_NAME} characters or fewer.")
    return tidy or None


def keep(conn, pieces: object, name: object = None) -> dict:
    """Keep an outfit: {outfit, already}. `already` is true when these very pieces were kept before (that outfit is
    given back, its name kept); one removed before comes back."""
    checked = plans.check_pieces(conn, pieces)
    tidy = _check_name(name)
    key = same_key(checked)
    try:
        conn.execute("BEGIN IMMEDIATE")
        t = db.now()
        r = conn.execute("SELECT * FROM kept_outfits WHERE same = ?", (key,)).fetchone()
        already = r is not None and r["removed_at"] is None
        if r is None:
            oid = uuid.uuid4().hex
            conn.execute("INSERT INTO kept_outfits (id, name, pieces, same, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                         (oid, tidy, json.dumps(checked), key, t, t))
        else:
            oid = r["id"]
            if not already:   # kept again after it was removed: back, as new
                conn.execute("UPDATE kept_outfits SET removed_at = NULL, name = COALESCE(?, name), pieces = ?, "
                             "created_at = ?, updated_at = ? WHERE id = ?", (tidy, json.dumps(checked), t, t, oid))
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return {"outfit": get(conn, oid), "already": already}


def list_all(conn) -> list[dict]:
    """The outfits kept, newest first."""
    return [_shape(conn, r) for r in conn.execute(
        "SELECT * FROM kept_outfits WHERE removed_at IS NULL ORDER BY created_at DESC, id DESC")]


def rename(conn, outfit_id: str, name: object) -> dict:
    """Give an outfit a name, change it, or (empty) take it away."""
    _row(conn, outfit_id)
    conn.execute("UPDATE kept_outfits SET name = ?, updated_at = ? WHERE id = ?", (_check_name(name), db.now(), outfit_id))
    return get(conn, outfit_id)


def remove(conn, outfit_id: str) -> dict:
    """Set an outfit aside; `restore` brings it back (Undo). Returns it as it was."""
    outfit = get(conn, outfit_id)
    t = db.now()
    conn.execute("UPDATE kept_outfits SET removed_at = ?, updated_at = ? WHERE id = ?", (t, t, outfit_id))
    return outfit


def restore(conn, outfit_id: str) -> dict:
    """Bring back an outfit removed (Undo), in its place."""
    _row(conn, outfit_id, removed=True)
    conn.execute("UPDATE kept_outfits SET removed_at = NULL, updated_at = ? WHERE id = ?", (db.now(), outfit_id))
    return get(conn, outfit_id)


# ------------------------------------------------------------------ the routes
class KeepBody(BaseModel):
    pieces: dict
    name: str | None = None
    model_config = {"extra": "forbid"}


class NameBody(BaseModel):
    name: str | None = None
    model_config = {"extra": "forbid"}


def router(conn_dep: Callable) -> APIRouter:
    r = APIRouter()

    @r.get("/api/outfits/kept")
    def list_kept(conn=Depends(conn_dep)):
        return {"outfits": list_all(conn)}

    @r.post("/api/outfits/kept", status_code=201)
    def keep_outfit(body: KeepBody, response: Response, conn=Depends(conn_dep)):
        result = keep(conn, body.pieces, body.name)
        if result["already"]:
            response.status_code = 200
        return result

    @r.patch("/api/outfits/kept/{outfit_id}")
    def name_kept(outfit_id: str, body: NameBody, conn=Depends(conn_dep)):
        return rename(conn, outfit_id, body.name)

    @r.delete("/api/outfits/kept/{outfit_id}")
    def remove_kept(outfit_id: str, conn=Depends(conn_dep)):
        return {"removed": remove(conn, outfit_id)}

    @r.post("/api/outfits/kept/{outfit_id}/restore")
    def restore_kept(outfit_id: str, conn=Depends(conn_dep)):
        return restore(conn, outfit_id)

    return r
