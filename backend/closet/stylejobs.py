"""Claude's outfits for the day: asked for in the background, kept in the closet, and given to Today.

Today always has the rules engine's outfits at once (`closet/today.py`). When Claude may choose (not the demo closet,
not switched off, a route to Claude usable), `Stylist.for_today` looks for Claude's answer for this day and these
choices in `style_answers`:

- **ready**: Claude's outfits are given, less any whose pieces can no longer be worn (put in the laundry since);
- **working**: Claude is still choosing; Today shows that and asks again in a moment;
- **failed**: why, in a sentence, and the engine's outfits stand. It is asked again by itself after `RETRY_S`;
- none yet: a question is started on a thread of its own and "working" is answered.

One answer serves the whole day for the same choices (the occasion, the mood, a piece built around or left out, an
outfit worn again, the day's note, the place, the style profile and the owner's notes and ratings of pieces). It is
asked again when the weather dressed for has moved by `DRIFT_C` degrees or the rain has come or gone, when none of its
outfits can be worn any more, or when the owner asks ("Ask Claude again"); never by itself once an outfit has been
worn today, and at most `MAX_PER_DAY` times a day. A piece added or washed during the day does not ask again: Claude
sees it tomorrow, or when the owner asks.

The thread only asks and stores: everything Claude is told (`styling.brief`) is put together by the request that
starts it. A question lost when the program stopped (still "working" after `STALE_S`) is asked again.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from datetime import date
from pathlib import Path

from . import db, outfits, styling
from .tagger.tagging import CapReached, RouteUnavailable, TaggingError, Unreachable

log = logging.getLogger("closet.stylejobs")

WORKING, READY, FAILED = "working", "ready", "failed"
MAX_PER_DAY = 12             # questions to Claude in one day, at most
STALE_S = 300                # a question still "working" after this long was lost: it is asked again
RETRY_S = 300                # after a failure, the next request this much later asks again by itself
DRIFT_C = 3.0                # asked again when the low or high dressed for has moved this far

RULES = "these are from Closet's own rules."
MESSAGES = {
    "unreachable": f"Claude couldn't be reached, so {RULES}",
    "limit": f"This month's spending limit for the API key has been reached and your Claude plan can't be used right now, so {RULES}",
    "answer": f"Claude gave no outfit that can be worn today, so {RULES}",
    "error": f"Something went wrong while Claude was choosing, so {RULES}",
    "lost": f"Closet was closed while Claude was choosing, so {RULES}",
    "no_route": ("Claude can't be reached right now (your Claude plan is not signed in on this computer and the API "
                 f"key is not switched on), so {RULES}"),
    "day_limit": f"Claude has chosen outfits {MAX_PER_DAY} times today, the most in one day, so {RULES}",
}

# What asks Claude: (brief, routes) -> {"looks": [...], "read": str, "route", "model", "input_tokens", "output_tokens"}
Asker = Callable[[dict, tuple[str, ...]], dict]


def key_of(day: str, context: Mapping, ctx: outfits.Context, rows: list[dict], profile: str | None) -> str:
    """What an answer is for: the day and everything the owner chose or wrote that Claude is told. The weather is
    not part of it (see `drifted`), nor which pieces are clean (see `wearable`)."""
    note = context.get("note") if isinstance(context.get("note"), dict) and context["note"].get("active") else {}
    said = sorted((str(r["id"]), r.get("wear_notes") or "", r.get("notes") or "", r.get("fit_notes") or "",
                   r.get("rating") or "") for r in rows
                  if isinstance(r, dict) and r.get("id")
                  and (r.get("wear_notes") or r.get("notes") or r.get("fit_notes") or r.get("rating")))
    what = [day, context.get("place"), ctx.occasion, ctx.mood, ctx.build_around, sorted(ctx.leave_out), sorted(ctx.keep),
            note.get("text"), note.get("from"), note.get("to"), profile or "", said]
    return hashlib.sha256(json.dumps(what, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def drifted(dressed: Mapping | None, ctx: outfits.Context) -> bool:
    """Whether the day now dressed for is far from the one an answer was asked for."""
    if not isinstance(dressed, Mapping):
        return True
    try:
        return (abs(float(dressed["low_c"]) - ctx.low_c) >= DRIFT_C or abs(float(dressed["high_c"]) - ctx.high_c) >= DRIFT_C
                or bool(dressed["rain"]) != ctx.rain)
    except (KeyError, TypeError, ValueError):
        return True


def wearable(found: list[dict], ids: set[str]) -> list[dict]:
    """The outfits whose every piece can still be worn (is in today's list)."""
    def all_in(o: dict) -> bool:
        placed = o.get("pieces") or {}
        core = [placed.get(pl) for pl in outfits.PLACES if placed.get(pl)]
        return bool(core) and set(core) <= ids and set(placed.get("accessories") or []) <= ids
    return [o for o in found if isinstance(o, dict) and all_in(o)]


def merged(claude: list[dict], engine: list[dict], count: int) -> list[dict]:
    """Claude's outfits first, then the engine's that differ from them, up to `count`."""
    def core(o: dict) -> tuple:
        return tuple((o.get("pieces") or {}).get(pl) or "" for pl in outfits.PLACES)
    out, seen = [], set()
    for o in [*claude, *engine]:
        if core(o) not in seen and len(out) < max(count, 1):
            seen.add(core(o))
            out.append(o)
    return out


class Stylist:
    """Keeps and asks for Claude's outfits. `ask` stands in for Claude in tests; `routes` says which routes can be
    used now; `start` runs a job (a thread by default; tests run it at once or hold it)."""

    def __init__(self, ask: Asker, routes: Callable[[], tuple[str, ...]], clock: Callable[[], float] = time.time,
                 start: Callable[[Callable[[], None]], None] | None = None):
        self.ask, self.routes, self.clock = ask, routes, clock
        self.start = start or (lambda job: threading.Thread(target=job, name="closet-stylist", daemon=True).start())
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ reading
    @staticmethod
    def _newest(conn, day: str, key: str):
        return conn.execute("SELECT * FROM style_answers WHERE day = ? AND key = ? ORDER BY created_at DESC, rowid DESC "
                            "LIMIT 1", (day, key)).fetchone()

    @staticmethod
    def get(conn, answer_id: str) -> dict | None:
        """One answer's state for the page that is waiting on it: {id, state, message} or None when unknown."""
        row = conn.execute("SELECT id, state, error FROM style_answers WHERE id = ?", (answer_id,)).fetchone()
        if row is None:
            return None
        return {"id": row["id"], "state": row["state"],
                "message": MESSAGES.get(row["error"] or "error") if row["state"] == FAILED else None}

    def _age(self, row) -> float:
        return self.clock() - float(row["asked_at"])

    # ------------------------------------------------------------------ for Today
    def for_today(self, conn, path: Path, *, day: date, key: str, ctx: outfits.Context, ids: set[str], worn_today: bool,
                  again: bool, brief: Callable[[], tuple[dict, styling.Listed]],
                  not_again: Mapping[tuple[str, ...], str] | None = None) -> dict:
        """Claude's answer for today as it stands: {state, id, outfits, read, message}. `state` is "ready" (with
        `outfits` and `read`), "working", or "failed" (with `message`; `outfits` empty). Starts a question when one
        is due (see the module's words). `ids`: the pieces that can be worn now; `brief`: makes what Claude is told,
        called only when a question is started; `path`: the closet's database, for the thread."""
        with self._lock:
            row = self._newest(conn, day.isoformat(), key)
            if row is not None and row["state"] == WORKING:
                if self._age(row) <= STALE_S:
                    return self._shape(row, [])
                conn.execute("UPDATE style_answers SET state = ?, error = 'lost', finished_at = ? WHERE id = ?",
                             (FAILED, db.now(), row["id"]))
                row = self._newest(conn, day.isoformat(), key)
            kept = wearable(json.loads(row["outfits"] or "[]"), ids) if row is not None and row["state"] == READY else []
            due = (row is None or again
                   or (row["state"] == READY and not worn_today and (not kept or drifted(json.loads(row["dressed"]), ctx)))
                   or (row["state"] == FAILED and not worn_today and self._age(row) >= RETRY_S))
            if not due:
                return self._shape(row, kept)
            usable = tuple(sorted(self.routes(), key=lambda r: r != "api"))   # the API key first (the owner: "opus via api")
            problem = ("no_route" if not usable else "day_limit" if conn.execute(
                "SELECT COUNT(*) FROM style_answers WHERE day = ?", (day.isoformat(),)).fetchone()[0] >= MAX_PER_DAY else None)
            if problem:
                if kept:   # what there is still stands
                    return self._shape(row, kept)
                return {"state": FAILED, "id": None, "outfits": [], "read": None, "message": MESSAGES[problem]}
            told, listing = brief()
            answer_id = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO style_answers (id, day, key, state, dressed, asked_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (answer_id, day.isoformat(), key, WORKING,
                 json.dumps({"low_c": ctx.low_c, "high_c": ctx.high_c, "rain": ctx.rain}), self.clock(), db.now()))
        self.start(lambda: self._run(path, answer_id, told, listing, ctx, dict(not_again or {}), usable))
        return {"state": WORKING, "id": answer_id, "outfits": [], "read": None, "message": None}

    def _shape(self, row, kept: list[dict]) -> dict:
        if row["state"] == READY:
            return {"state": READY, "id": row["id"], "outfits": kept, "read": row["read"], "message": None}
        if row["state"] == WORKING:
            return {"state": WORKING, "id": row["id"], "outfits": [], "read": None, "message": None}
        return {"state": FAILED, "id": row["id"], "outfits": [], "read": None,
                "message": MESSAGES.get(row["error"] or "error", MESSAGES["error"])}

    # ------------------------------------------------------------------ asking
    def _run(self, path: Path, answer_id: str, told: dict, listing: styling.Listed, ctx: outfits.Context,
             not_again: dict, usable: tuple[str, ...]) -> None:
        started = time.monotonic()
        found, read, problems, meta, error = [], None, [], {}, None
        try:
            meta = self.ask(told, usable)
            found, problems = styling.check(meta.get("looks") or [], listing, ctx, not_again)
            read = " ".join(str(meta.get("read") or "").split()) or None
            if not found:
                error = "answer"
        except CapReached:
            error = "limit"
        except (RouteUnavailable, Unreachable):
            error = "unreachable"
        except TaggingError:
            error = "answer"
        except Exception:   # never left "working": the owner gets the engine's outfits and a sentence
            log.exception("choosing the outfits failed")
            error = "error"
        if problems:
            log.info("the stylist's answer: %d kept, %d left out", len(found), len(problems))
        conn = db.connect(path)
        try:
            conn.execute(
                "UPDATE style_answers SET state = ?, outfits = ?, read = ?, problems = ?, error = ?, route = ?, model = ?, "
                "input_tokens = ?, output_tokens = ?, seconds = ?, finished_at = ? WHERE id = ? AND state = ?",
                (FAILED if error else READY, json.dumps(found), read, json.dumps(problems), error, meta.get("route"),
                 meta.get("model"), int(meta.get("input_tokens") or 0), int(meta.get("output_tokens") or 0),
                 round(time.monotonic() - started, 1), db.now(), answer_id, WORKING))
        except Exception:
            log.exception("Claude's outfits could not be kept")
        finally:
            conn.close()


def public(found: dict | None) -> dict | None:
    """What Today is told about the stylist: {state, id, read, message}, or None when Claude does not choose here."""
    if not found:
        return None
    return {"state": found["state"], "id": found["id"], "read": found["read"], "message": found["message"]}

