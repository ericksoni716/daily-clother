"""What the owner decided about the gaps: the ones hidden ("Not for me") and the wishlist.

Kept in the closet's own database (migration 0008), so the demo closet and the real one keep theirs apart
and backups include them. A gap is known by the `id` the analysis gives it (`closet/gaps.py`): the purchase
it suggests (its category, formality and what it is for), which stays the same when the analysis runs again.
A wish keeps a copy of the gap's name and what to look for, so it stays useful if the gap is no longer found.
"""
from __future__ import annotations

import json
import re
import sqlite3
import uuid
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from . import db, life
from .gaps import MAX_GAPS
from .items import ItemError

# Why a gap is "not for me": I have one that is not in the closet yet, I never dress like that, too expensive, other.
REASONS = ("have_one", "never_wear", "too_expensive", "other")
NAME_MAX = 120
NOTE_MAX = 1000
PRICE_MAX = 1_000_000.0
CURRENCY_DEFAULT = "USD"


# ------------------------------------------------------------------ marking the analysis
def mark(conn: sqlite3.Connection, answer: dict, offered: int = MAX_GAPS, consent: dict | None = None) -> dict:
    """The analysis with each gap marked `state` "open", "hidden" or "wished" (with `hidden_reason` and `wish_id`).

    Up to `offered` open gaps are kept, best first; every hidden or wished gap the analysis found is kept too, in
    its place, so a gap the owner has decided about never pushes a new one off the list. The answer is not changed.
    """
    hidden_rows = [dict(r) for r in conn.execute("SELECT gap_id, name, reason, hidden_at FROM hidden_gaps ORDER BY gap_id")]
    hidden = {r["gap_id"]: r["reason"] for r in hidden_rows}
    wished = {r["gap_id"]: r["id"] for r in conn.execute(
        "SELECT gap_id, id FROM wishes WHERE gap_id IS NOT NULL AND bought_at IS NULL")}
    answer = _hold_back(answer, hidden_rows, set(wished), consent)
    gaps, open_count = [], 0
    for g in answer.get("gaps", []):
        if g["id"] in wished:
            state = "wished"
        elif g["id"] in hidden:
            state = "hidden"
        elif g.get("state") == "held_back":
            state = "held_back"
        else:
            if open_count >= offered:
                if not g.get("held_back_by"):
                    continue
                state = "held_back"
            else:
                open_count += 1
                state = "open"
        gaps.append({**g, "state": state, "hidden_reason": hidden.get(g["id"]) if state == "hidden" else None,
                     "wish_id": wished.get(g["id"])})
    return {**answer, "gaps": gaps}


def _signature(gap_id: str) -> tuple[str, str, str]:
    parts = gap_id.split("-")
    # Outer layers solve different weather needs: no outer-layer hide suppresses another purchase.
    if parts[0] == "outer":
        return gap_id, "", ""
    kind = "active" if parts[-1].endswith("active") else "lounge" if parts[-1] == "lounge" else ""
    dress = next((p for p in parts[1:] if p in life.WORK_DRESS or p == "athletic"), "")
    return parts[0], dress, kind


def _hold_back(answer: dict, hidden: list[dict], wished: set[str], consent: dict | None = None) -> dict:
    context = answer.get("context")
    if not context or not context.get("life"):
        return answer
    answers = context["life"]
    by_id = {g["id"]: g for g in answer["gaps"]}
    policies = []
    for row in hidden:
        if row["reason"] != "never_wear" or row["gap_id"].split("-")[0] == "outer":
            continue
        signature = _signature(row["gap_id"])
        original = by_id.get(row["gap_id"])
        approved = (consent or {}).get(row["gap_id"], {})
        confirmed = bool(approved and approved.get("hidden_at") == row.get("hidden_at"))
        if confirmed:
            situations = [key for key in approved.get("situations", []) if key in life.SITUATIONS and life.frequency(key, answers)]
        elif original:
            situations = [s["id"] for s in original.get("situations", [])]
        else:
            # The original may no longer be missing. Its ID still tells us the dress and kind;
            # keep the decision visible and reversible rather than depending on a vanished card.
            _, dress, kind = signature
            situations = [key for key in life.SITUATIONS if life.frequency(key, answers) and (
                key == "lounging" if kind == "lounge" else key == "exercise" if kind == "active" else
                key not in ("lounging", "exercise") and (not dress or
                life.gaps.PIECE_FORMALITY[life.occasion(key, answers)] == dress))]
        policies.append({"gap_id": row["gap_id"], "name": row["name"], "situations": situations,
                         "needs_confirmation": not confirmed})
    held = []
    hidden_ids = {row["gap_id"] for row in hidden}
    for g in answer["gaps"]:
        if g["id"] in hidden_ids or g["id"] in wished:
            held.append(g)
            continue
        served = g.get("situations", [])
        causes = [{"gap_id": policy["gap_id"], "name": policy["name"],
                   "situations": [s["id"] for s in served if s["id"] in policy["situations"]]}
                  for policy in policies if not policy["needs_confirmation"]
                  and _signature(policy["gap_id"]) == _signature(g["id"])]
        causes = [cause for cause in causes if cause["situations"]]
        removed = {key for cause in causes for key in cause["situations"]}
        remaining = [s for s in served if s["id"] not in removed]
        if len(remaining) == len(served):
            held.append(g)
        elif remaining:
            before = sum(s["share"] for s in served)
            share = sum(s["share"] for s in remaining)
            score = round(g["score"] * share / before) if before else 0
            held.append({**g, "situations": remaining, "score": score, "held_back_by": causes,
                         "state": "open" if score > 0 else "held_back",
                         "why": [text for text in g["why"] if not any(
                             text.startswith(f"For {life.SITUATIONS[key].label.lower()},") for key in removed)],
                         "evidence": {**g["evidence"], "days": [
                             d for d in g["evidence"]["days"] if d.get("situation") not in removed]}})
        else:
            held.append({**g, "state": "held_back", "held_back_by": causes})
    held.sort(key=lambda g: (-g["score"], g["name"], g["id"]))
    taste = context["taste"]
    if any(not policy["needs_confirmation"] for policy in policies):
        taste = {**taste, "used": True}
    return {**answer, "gaps": held, "context": {**context, "suppressed": policies, "taste": taste}}


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
                 "ON CONFLICT (gap_id) DO UPDATE SET name = excluded.name, reason = excluded.reason, "
                 "hidden_at = excluded.hidden_at", row)
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


def _price_range(w: dict, changes: dict) -> tuple[float | None, float | None, str | None]:
    """The wish's price range with `changes` (any of price_min, price_max, price_currency; None clears) laid over it."""
    low, high = (changes[k] if k in changes else w[k] for k in ("price_min", "price_max"))
    for value in (low, high):
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                  or not 0 <= value <= PRICE_MAX):
            raise ItemError(f"A price must be a number from 0 to {PRICE_MAX:,.0f}.")
    if low is not None and high is not None and low > high:
        raise ItemError("The lowest price must not be more than the highest.")
    currency = changes["price_currency"] if "price_currency" in changes else w["price_currency"]
    if currency is not None:
        if not isinstance(currency, str) or not re.fullmatch(r"[A-Za-z]{3}", currency.strip()):
            raise ItemError("The currency must be a three-letter code, such as USD, EUR or GBP.")
        currency = currency.strip().upper()
    if low is None and high is None:
        return None, None, None
    return (None if low is None else round(float(low), 2), None if high is None else round(float(high), 2),
            currency or CURRENCY_DEFAULT)


def update_wish(conn: sqlite3.Connection, wish_id: str, name: str | None, note: str | None,
                price: dict | None = None) -> dict:
    """Change a wish's name, note or price range (`price`: the parts of the range sent, None clearing one)."""
    w = get_wish(conn, wish_id)
    if price:
        low, high, currency = _price_range(w, price)
        conn.execute("UPDATE wishes SET price_min = ?, price_max = ?, price_currency = ?, updated_at = ? WHERE id = ?",
                     (low, high, currency, db.now(), wish_id))
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
    price_min: float | None = None
    price_max: float | None = None
    price_currency: str | None = None
    model_config = {"extra": "forbid"}


def router(conn_dep: Callable, gaps_now: Callable[[], dict], protected: list, settings=None) -> APIRouter:
    """The routes for hiding gaps and for the wishlist. `gaps_now()` gives the open closet's analysis (it may take
    seconds the first time, so it is called in a worker thread)."""
    r = APIRouter(dependencies=protected)

    async def gap(gap_id: str) -> dict:
        return _find((await run_in_threadpool(gaps_now)).get("gaps", []), gap_id)

    @r.post("/api/gaps/{gap_id}/hide")
    async def hide_gap(gap_id: str, body: HideBody | None = None, conn=Depends(conn_dep)):
        profile = settings.get("profile") if settings else None
        answer = await run_in_threadpool(gaps_now, profile) if settings else await run_in_threadpool(gaps_now)
        existing = conn.execute("SELECT * FROM hidden_gaps WHERE gap_id = ?", (gap_id,)).fetchone()
        try:
            found = _find(answer.get("gaps", []), gap_id)
        except ItemError:
            if not existing:
                raise
            found = {"id": gap_id, "name": existing["name"]}
        result = hide(conn, found, body.reason if body else None)
        if settings:
            # Only a new, explicit hide after answering can affect other purchases. Old database
            # rows have no consent; restoring a backup cannot silently enable broader hiding.
            marked = _hold_back(answer, [result], set())
            policy = next(iter(marked.get("context", {}).get("suppressed", [])), None)
            def remember(data):
                data["life_gap_hides"] = dict(data["life_gap_hides"])
                by_profile = dict(data["life_gap_hides"].get(profile, {}))
                data["life_gap_hides"][profile] = by_profile
                if policy and result["reason"] == "never_wear":
                    by_profile[gap_id] = {"hidden_at": result["hidden_at"], "situations": policy["situations"]}
                else:
                    by_profile.pop(gap_id, None)
            settings.mutate(remember)
        return result

    @r.delete("/api/gaps/{gap_id}/hide", status_code=204)
    def unhide_gap(gap_id: str, conn=Depends(conn_dep)):
        unhide(conn, gap_id)
        if settings:
            profile = settings.get("profile")
            settings.mutate(lambda data: data["life_gap_hides"].get(profile, {}).pop(gap_id, None))
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
        price = {k: getattr(body, k) for k in ("price_min", "price_max", "price_currency") if k in body.model_fields_set}
        return update_wish(conn, wish_id, body.name, body.note, price)

    @r.post("/api/wishlist/{wish_id}/bought")
    def bought(wish_id: str, conn=Depends(conn_dep)):
        return mark_bought(conn, wish_id)

    @r.delete("/api/wishlist/{wish_id}", status_code=204)
    def delete_wish(wish_id: str, conn=Depends(conn_dep)):
        remove_wish(conn, wish_id)
        return Response(status_code=204)

    return r
