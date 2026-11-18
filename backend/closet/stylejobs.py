"""Claude's outfits for the day: asked for in the background, kept in the closet, and given to Today.

Today always has the rules engine's outfits at once (`closet/today.py`). When Claude may choose (not the demo closet,
not switched off, a route to Claude usable), `Stylist.for_today` looks for Claude's answer for this day and these
choices in `style_answers`:

- **ready**: Claude's outfits are given, less any whose pieces can no longer be worn (put in the laundry since).
  When none is left and Claude is not asked again (an outfit was worn today), that is said and the engine's stand;
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
starts it. A question lost when the program stopped (still "working" after `STALE_S`) is asked again at once,
unless an outfit has been worn today.

**The conversation.** The owner can write to Claude about the outfits on the page (`say`): "too dressy", "swap the
boots", "why not the navy blazer?". A message is a question of its own, kept as a row with `said`: Claude answers
in words (`reply`), gives the outfits again when something changes (when it gives none, the ones shown stand) and
may offer things worth remembering (`remember`). While it is being answered the outfits on the page stay; when it
fails they stay too, and the message is shown as not answered. The day's messages and answers are told to Claude
with every later question that day, so "too dressy" still holds after the weather moves or the occasion changes.
A message is refused, with a sentence, when Claude's outfits are not on the page, when one is still being
answered, when no route to Claude can be used and at the day's limit. While a message is being answered no other
question is started (asking again, the weather moving, other choices): the page waits on the message and asks
Today again, so Claude's words back never sit beside outfits from another answer.

**The look.** When the stylist can draw and look (`draw`, `look`), a plain question has a second part: the outfits
Claude chose are drawn on the figure as worn, Claude is shown the pictures and keeps or changes each outfit; the
answer is ready once that is done, and `seen` records what it saw. An answer to a message of the owner's is not
looked at, so the conversation stays quick. The look can only improve an answer: when the outfits cannot be drawn,
Claude cannot be asked again, or what it gives cannot be worn, the outfits first chosen stand.

**Remembering.** Nothing is kept unless the owner says so (`settle`): a thing about their style is added to the
style profile as a line, a thing about a piece to its "How I wear it" note. Both are part of what an answer is
for, so the day's answers are moved to the new words: saving does not ask Claude again.
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

from . import db, items, outfits, styleprofile, styling
from .tagger.tagging import CapReached, RouteUnavailable, TaggingError, Unreachable

log = logging.getLogger("closet.stylejobs")

WORKING, READY, FAILED = "working", "ready", "failed"
MAX_PER_DAY = 20             # questions to Claude in one day, at most (the owner's messages are questions too)
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
    "day_limit_kept": (f"Claude has chosen outfits {MAX_PER_DAY} times today, the most in one day, so these are "
                       "still the ones it chose last."),
    "gone": f"The outfits Claude chose for today use pieces that can no longer be worn today, so {RULES}",
}
# Why a message to Claude was not answered (shown under it in the conversation)
TALK_MESSAGES = {
    "unreachable": "Claude couldn't be reached, so this wasn't answered. The outfits are as they were.",
    "limit": ("This month's spending limit for the API key has been reached and your Claude plan can't be used right "
              "now, so this wasn't answered."),
    "answer": "Claude's answer couldn't be used, so the outfits are as they were. Try saying it another way.",
    "error": "Something went wrong while Claude was answering. The outfits are as they were.",
    "lost": "Closet was closed while Claude was answering. The outfits are as they were.",
}
# Why a message was not sent at all (the request is refused with the sentence)
REFUSED = {
    "nothing": "Claude's outfits aren't on the page right now, so your message wasn't sent.",
    "busy": "Claude is still answering your last message.",
    "no_route": ("Claude can't be reached right now (your Claude plan is not signed in on this computer and the API "
                 "key is not switched on), so your message wasn't sent."),
    "day_limit": f"Claude has answered {MAX_PER_DAY} times today, the most in one day, so your message wasn't sent.",
}
OFFERED, SAVED, DISMISSED = "offered", "saved", "dismissed"


class Refused(Exception):
    """A message to Claude that was not sent, or a thing to remember that could not be kept; says why in a sentence."""

# What asks Claude: (brief, routes) -> {"looks": [...], "read": str, "route", "model", "input_tokens", "output_tokens"}
# and, when the brief carries the owner's message (`say`), "reply": str and "remember": [{about, text}] as well
Asker = Callable[[dict, tuple[str, ...]], dict]
# What draws the outfits chosen, each as worn on the figure: (the closet's database, outfits) -> one picture each
Drawer = Callable[[Path, list[dict]], list]
# What shows Claude those pictures: (brief with "chosen", pictures, routes) -> {"looks": [...], "saw": str, "route",
# "model", "input_tokens", "output_tokens"}
Looker = Callable[[dict, list, tuple[str, ...]], dict]


def _hash(what: object) -> str:
    return hashlib.sha256(json.dumps(what, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def words_of(rows: list[dict], profile: str | None) -> str:
    """The owner's lasting words that Claude is told, as one hash: the style profile, and each piece's notes and
    rating."""
    said = sorted((str(r["id"]), r.get("wear_notes") or "", r.get("notes") or "", r.get("fit_notes") or "",
                   r.get("rating") or "") for r in rows
                  if isinstance(r, dict) and r.get("id")
                  and (r.get("wear_notes") or r.get("notes") or r.get("fit_notes") or r.get("rating")))
    return _hash([profile or "", said])


def key_of(day: str, context: Mapping, ctx: outfits.Context, rows: list[dict], profile: str | None) -> str:
    """What an answer is for: the day and everything the owner chose or wrote that Claude is told, as two hashes
    with a colon between: the day's choices, then the owner's lasting words (`words_of`; apart, so that `settle` can
    move the day's answers to new words). The weather is not part of it (see `drifted`), nor which pieces are clean
    (see `wearable`), nor the day's conversation (it is told with every question)."""
    note = context.get("note") if isinstance(context.get("note"), dict) and context["note"].get("active") else {}
    what = [day, context.get("place"), ctx.occasion, ctx.mood, ctx.build_around, sorted(ctx.leave_out), sorted(ctx.keep),
            note.get("text"), note.get("from"), note.get("to")]
    return f"{_hash(what)}:{words_of(rows, profile)}"


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
                 start: Callable[[Callable[[], None]], None] | None = None, draw: Drawer | None = None,
                 look: Looker | None = None):
        self.ask, self.routes, self.clock = ask, routes, clock
        self.draw, self.look = draw, look   # both, or the outfits are not looked at as drawn
        self.start = start or (lambda job: threading.Thread(target=job, name="closet-stylist", daemon=True).start())
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ reading
    @staticmethod
    def _newest(conn, day: str, key: str):
        """The answer that stands for these choices: the newest, passing over a message of the owner's that is
        still being answered or was not answered (the outfits before it stand)."""
        return conn.execute("SELECT * FROM style_answers WHERE day = ? AND key = ? AND NOT (said IS NOT NULL AND "
                            "state != ?) ORDER BY created_at DESC, rowid DESC LIMIT 1", (day, key, READY)).fetchone()

    def _answering(self, conn, day: str):
        """The message of the owner's that Claude is answering now, or None. One lost when the program stopped is
        marked so."""
        row = conn.execute("SELECT * FROM style_answers WHERE day = ? AND said IS NOT NULL AND state = ? "
                           "ORDER BY created_at DESC, rowid DESC LIMIT 1", (day, WORKING)).fetchone()
        if row is not None and self._age(row) > STALE_S:
            conn.execute("UPDATE style_answers SET state = ?, error = 'lost', finished_at = ? WHERE day = ? AND "
                         "said IS NOT NULL AND state = ?", (FAILED, db.now(), day, WORKING))
            return None
        return row

    @staticmethod
    def get(conn, answer_id: str, now: float | None = None) -> dict | None:
        """One answer's state for the page that is waiting on it: {id, state, message} or None when unknown. One
        still "working" long after it was asked (`now`: the time by the stylist's clock) was lost when the program
        stopped: it is said to have failed, so the page stops waiting and asks Today, which marks it."""
        row = conn.execute("SELECT id, state, error, said, asked_at FROM style_answers WHERE id = ?",
                           (answer_id,)).fetchone()
        if row is None:
            return None
        why = TALK_MESSAGES if row["said"] is not None else MESSAGES
        if row["state"] == WORKING and now is not None and now - float(row["asked_at"]) > STALE_S:
            return {"id": row["id"], "state": FAILED, "message": why["lost"]}
        return {"id": row["id"], "state": row["state"],
                "message": why.get(row["error"] or "error", why["error"]) if row["state"] == FAILED else None}

    def _age(self, row) -> float:
        return self.clock() - float(row["asked_at"])

    # ------------------------------------------------------------------ for Today
    def for_today(self, conn, path: Path, *, day: date, key: str, ctx: outfits.Context, ids: set[str], worn_today: bool,
                  again: bool, brief: Callable[[], tuple[dict, styling.Listed]],
                  not_again: Mapping[tuple[str, ...], str] | None = None, say: str | None = None,
                  engine: list[dict] | None = None, count: int = 3, looking_at: int | None = None) -> dict:
        """Claude's answer for today as it stands: {state, id, outfits, read, message, talk, answering}. `state` is
        "ready" (with `outfits` and `read`), "working", or "failed" (with `message`; `outfits` empty). Starts a
        question when one is due (see the module's words). `ids`: the pieces that can be worn now; `brief`: makes
        what Claude is told, called only when a question is started; `path`: the closet's database, for the thread.

        `talk` is the day's conversation (`talk_of`) and `answering` the id of the message Claude is answering now.
        `say` sends a message about the outfits on the page (`engine` and `count`: the rules' outfits and how many
        the page shows, to tell Claude what the owner is looking at, and `looking_at`: which of them was in front of
        the owner, 0 the first); raises `Refused` when it cannot be sent."""
        found = self._for_today(conn, path, day=day, key=key, ctx=ctx, ids=ids, worn_today=worn_today, again=again,
                                brief=brief, not_again=not_again, say=say, engine=engine or [], count=count,
                                looking_at=looking_at)
        with self._lock:
            answering = self._answering(conn, day.isoformat())
        return {**found, "talk": talk_of(conn, day.isoformat()), "answering": answering["id"] if answering else None}

    def _for_today(self, conn, path: Path, *, day: date, key: str, ctx: outfits.Context, ids: set[str],
                   worn_today: bool, again: bool, brief: Callable[[], tuple[dict, styling.Listed]],
                   not_again: Mapping[tuple[str, ...], str] | None, say: str | None, engine: list[dict],
                   count: int, looking_at: int | None) -> dict:
        with self._lock:
            row = self._newest(conn, day.isoformat(), key)
            lost = False
            if say is not None:
                return self._say(conn, path, row, day=day, key=key, ctx=ctx, ids=ids, brief=brief, not_again=not_again,
                                 say=say, engine=engine, count=count, looking_at=looking_at)
            if row is not None and row["state"] == WORKING:
                if self._age(row) <= STALE_S:
                    return self._shape(row, [])
                conn.execute("UPDATE style_answers SET state = ?, error = 'lost', finished_at = ? WHERE id = ?",
                             (FAILED, db.now(), row["id"]))
                row, lost = self._newest(conn, day.isoformat(), key), True
            kept = wearable(json.loads(row["outfits"] or "[]"), ids) if row is not None and row["state"] == READY else []
            due = (row is None or again
                   or (row["state"] == READY and not worn_today and (not kept or drifted(json.loads(row["dressed"]), ctx)))
                   # a lost question is asked again at once; a failure after RETRY_S
                   or (row["state"] == FAILED and not worn_today and (lost or self._age(row) >= RETRY_S)))
            if not due:
                return self._shape(row, kept)
            answering = self._answering(conn, day.isoformat())
            if answering is not None:
                # a message is being answered: nothing else is asked until it is. What stands is given; with
                # nothing to give (other choices), the page waits on the message and then asks Today again
                if row is not None and (kept or row["state"] != READY):
                    return self._shape(row, kept)
                return {"state": WORKING, "id": answering["id"], "outfits": [], "read": None, "message": None}
            usable = tuple(sorted(self.routes(), key=lambda r: r != "api"))   # the API key first (the owner: "opus via api")
            problem = ("no_route" if not usable else "day_limit" if conn.execute(
                "SELECT COUNT(*) FROM style_answers WHERE day = ?", (day.isoformat(),)).fetchone()[0] >= MAX_PER_DAY else None)
            if problem:
                if kept:   # what there is still stands; an owner who asked again is told why nothing changed
                    said = MESSAGES["day_limit_kept"] if again and problem == "day_limit" else None
                    return {**self._shape(row, kept), "message": said}
                return {"state": FAILED, "id": None, "outfits": [], "read": None, "message": MESSAGES[problem]}
            told, listing = brief()
            talk = styling.talk_words(talk_of(conn, day.isoformat()), listing)
            if talk:   # what the owner said earlier today still holds
                told = {**told, "talk": talk}
            answer_id = self._insert(conn, day, key, ctx)
        self.start(lambda: self._run(path, answer_id, told, listing, ctx, dict(not_again or {}), usable))
        return {"state": WORKING, "id": answer_id, "outfits": [], "read": None, "message": None}

    def _insert(self, conn, day: date, key: str, ctx: outfits.Context, said: str | None = None) -> str:
        answer_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO style_answers (id, day, key, state, dressed, said, asked_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (answer_id, day.isoformat(), key, WORKING,
             json.dumps({"low_c": ctx.low_c, "high_c": ctx.high_c, "rain": ctx.rain}), said, self.clock(), db.now()))
        return answer_id

    def _say(self, conn, path: Path, row, *, day: date, key: str, ctx: outfits.Context, ids: set[str],
             brief: Callable[[], tuple[dict, styling.Listed]], not_again: Mapping | None, say: str,
             engine: list[dict], count: int, looking_at: int | None) -> dict:
        """Send the owner's message about the outfits on the page (called with the lock held). The outfits stay as
        they are while Claude answers."""
        kept = wearable(json.loads(row["outfits"] or "[]"), ids) if row is not None and row["state"] == READY else []
        if not kept:
            raise Refused(REFUSED["nothing"])
        if self._answering(conn, day.isoformat()) is not None:
            raise Refused(REFUSED["busy"])
        usable = tuple(sorted(self.routes(), key=lambda r: r != "api"))
        if not usable:
            raise Refused(REFUSED["no_route"])
        if conn.execute("SELECT COUNT(*) FROM style_answers WHERE day = ?", (day.isoformat(),)).fetchone()[0] >= MAX_PER_DAY:
            raise Refused(REFUSED["day_limit"])
        told, listing = brief()
        told = {**told, "say": say,
                "talk": styling.talk_words(talk_of(conn, day.isoformat()), listing, merged(kept, engine, count), say,
                                           looking_at)}
        answer_id = self._insert(conn, day, key, ctx, said=say)
        self.start(lambda: self._run(path, answer_id, told, listing, ctx, dict(not_again or {}), usable,
                                     shown=kept, read=row["read"]))
        return self._shape(row, kept)

    def _shape(self, row, kept: list[dict]) -> dict:
        if row["state"] == READY and not kept:
            # Claude answered, but none of its outfits can be worn now (worn and in the laundry, say) and it is not
            # asked again: the engine's stand, and that is said rather than "ready" over the rules' outfits
            return {"state": FAILED, "id": row["id"], "outfits": [], "read": None, "message": MESSAGES["gone"]}
        if row["state"] == READY:
            return {"state": READY, "id": row["id"], "outfits": kept, "read": row["read"], "message": None}
        if row["state"] == WORKING:
            return {"state": WORKING, "id": row["id"], "outfits": [], "read": None, "message": None}
        return {"state": FAILED, "id": row["id"], "outfits": [], "read": None,
                "message": MESSAGES.get(row["error"] or "error", MESSAGES["error"])}

    # ------------------------------------------------------------------ the look at the outfits as drawn
    def _still_working(self, path: Path, answer_id: str) -> None:
        """Note that a question is still being worked on, now: the time after which it counts as lost (`STALE_S`)
        runs afresh for its second part, so a slow choice followed by a slow look is not asked again meanwhile."""
        conn = db.connect(path)
        try:
            conn.execute("UPDATE style_answers SET asked_at = ? WHERE id = ? AND state = ?",
                         (self.clock(), answer_id, WORKING))
        finally:
            conn.close()

    def _looked(self, path: Path, told_id: str, told: dict, listing: styling.Listed, ctx: outfits.Context,
                not_again: dict, usable: tuple[str, ...], found: list[dict]
                ) -> tuple[list[dict], list[str], dict | None, dict]:
        """Claude's look at the outfits it chose, drawn as worn: (the outfits now, what was left out of its second
        answer, what is recorded as `seen` or None when no look was taken, the tokens it took). Never raises: when
        the look cannot be taken or gives nothing wearable, `found` stands."""
        nothing = {"input_tokens": 0, "output_tokens": 0}
        if self.draw is None or self.look is None:
            return found, [], None, nothing
        began = time.monotonic()
        try:
            self._still_working(path, told_id)
            pictures = self.draw(path, found)
            if len(pictures) != len(found):
                return found, [], None, nothing
            meta = self.look({**told, "chosen": styling.chosen_words(found, listing)}, pictures, usable)
            again, problems = styling.check(meta.get("looks") or [], listing, ctx, not_again)
        except (CapReached, RouteUnavailable, Unreachable, TaggingError) as e:
            log.info("the outfits were not looked at as drawn: %s", type(e).__name__)
            return found, [], None, nothing
        except Exception:
            log.exception("looking at the outfits as drawn failed")
            return found, [], None, nothing
        spent = {k: int(meta.get(k) or 0) for k in nothing}
        # the look's sentences count outfits within its own answer: told apart from the first answer's
        problems = [f"After the look, {p[:1].lower()}{p[1:]}" for p in problems]
        if not again:   # nothing wearable came back: what was first chosen stands
            return found, problems, None, spent
        # an outfit lost from the second answer (left out by the check, or not given again) keeps its place after
        final = merged(again, found, len(found))
        changed = sum(1 for o in final if not any(_same(o, before) for before in found))
        saw = " ".join(str(meta.get("saw") or "").split())[:styling.MAX_REPLY] or None
        return final, problems, {"saw": saw, "changed": changed, "seconds": round(time.monotonic() - began, 1)}, spent

    # ------------------------------------------------------------------ asking
    def _run(self, path: Path, answer_id: str, told: dict, listing: styling.Listed, ctx: outfits.Context,
             not_again: dict, usable: tuple[str, ...], shown: list[dict] | None = None, read: str | None = None) -> None:
        """Ask and keep the answer. `shown` (and `read`) are given for a message of the owner's: the outfits on the
        page, which stand when Claude gives none."""
        started = time.monotonic()
        talking = shown is not None
        found, problems, meta, error, reply, remember, seen = [], [], {}, None, None, [], None
        try:
            meta = self.ask(told, usable)
            looks = meta.get("looks") or []
            if talking:
                reply = " ".join(str(meta.get("reply") or "").split())[:styling.MAX_REPLY] or None
                remember = styling.keeps(meta.get("remember"), listing)
            else:
                read = " ".join(str(meta.get("read") or "").split()) or None
            if looks or not talking:
                found, problems = styling.check(looks, listing, ctx, not_again)
            else:
                found = shown   # Claude only answered: the outfits on the page stand
            if not found or (talking and not reply):
                error = "answer"
            elif not talking:
                found, more, seen, spent = self._looked(path, answer_id, told, listing, ctx, not_again, usable, found)
                problems = problems + more
                meta = {**meta, **{k: int(meta.get(k) or 0) + spent[k] for k in spent}}
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
                "input_tokens = ?, output_tokens = ?, seconds = ?, finished_at = ?, reply = ?, remember = ?, seen = ? "
                "WHERE id = ? AND state = ?",
                (FAILED if error else READY, json.dumps([] if error else found), None if error else read,
                 json.dumps(problems), error, meta.get("route"),
                 meta.get("model"), int(meta.get("input_tokens") or 0), int(meta.get("output_tokens") or 0),
                 round(time.monotonic() - started, 1), db.now(), None if error else reply,
                 json.dumps(remember) if remember and not error else None,
                 json.dumps(seen) if seen and not error else None, answer_id, WORKING))
        except Exception:
            log.exception("Claude's outfits could not be kept")
        finally:
            conn.close()


def _same(a: dict, b: dict) -> bool:
    """Whether two outfits are the same pieces in the same places, accessories in any order."""
    pa, pb = a.get("pieces") or {}, b.get("pieces") or {}
    return (all((pa.get(pl) or None) == (pb.get(pl) or None) for pl in outfits.PLACES)
            and sorted(pa.get("accessories") or []) == sorted(pb.get("accessories") or []))


def _remembered(row) -> list[dict]:
    try:
        found = json.loads(row["remember"]) if row["remember"] else []
    except ValueError:
        return []
    return [k for k in found if isinstance(k, dict)] if isinstance(found, list) else []


def talk_of(conn, day: str) -> list[dict]:
    """The day's conversation, oldest first: [{id, said, state, reply, message, remember, at}]. `state` is
    "working" while Claude answers, "ready" with `reply`, or "failed" with why in `message`. `remember`: what Claude
    offered to keep, [{kind: "style" or "piece", item_id, name, text, state: "offered", "saved" or "dismissed"}]."""
    rows = conn.execute("SELECT * FROM style_answers WHERE day = ? AND said IS NOT NULL ORDER BY created_at, rowid",
                        (day,)).fetchall()
    return [{"id": r["id"], "said": r["said"], "state": r["state"], "reply": r["reply"] if r["state"] == READY else None,
             "message": (TALK_MESSAGES.get(r["error"] or "error", TALK_MESSAGES["error"]) if r["state"] == FAILED
                         else None),
             "remember": _remembered(r) if r["state"] == READY else [], "at": r["created_at"]} for r in rows]


def settle(conn, answer_id: str, index: int, save: bool) -> dict:
    """The owner's answer to a thing Claude offered to remember: keep it (`save`) or not. Kept, a thing about their
    style becomes a new line of the style profile and a thing about a piece a new line of its "How I wear it" note,
    and the day's answers are moved to the new words so that Claude is not asked again for it. Gives the thing back
    as it now stands. Raises `Refused` with a sentence when it is unknown or cannot be kept; answering twice
    changes nothing."""
    row = conn.execute("SELECT * FROM style_answers WHERE id = ?", (answer_id,)).fetchone()
    found = _remembered(row) if row is not None else []
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(found):
        raise Refused("That is no longer on the page. Open Today again.")
    thing = found[index]
    if thing.get("state") != OFFERED:
        return thing
    def written(old: str) -> bool:   # the same line is there already (not merely inside a longer one)
        return thing["text"] in (line.strip().removeprefix("- ").strip() for line in old.splitlines())

    conn.execute("BEGIN IMMEDIATE")   # the words, the day's answers and the thing change together or not at all
    try:
        if save:
            before = words_of(_spoken(conn), styleprofile.text_for_stylist(conn))
            try:
                if thing.get("kind") == styling.PIECE:
                    item = conn.execute("SELECT wear_notes FROM items WHERE id = ?", (thing.get("item_id"),)).fetchone()
                    if item is None:
                        raise Refused("That piece is no longer in your closet.")
                    old = (item["wear_notes"] or "").strip()
                    if not written(old):
                        items.update(conn, thing["item_id"],
                                     {"wear_notes": f"{old}\n{thing['text']}" if old else thing["text"]})
                else:
                    old = styleprofile.text_for_stylist(conn) or styling.DEFAULT_KEPT
                    if not written(old):
                        styleprofile.save(conn, f"{old.rstrip()}\n- {thing['text']}", "claude")
            except (ValueError, items.ItemError) as e:
                raise Refused(str(e)) from None
            after = words_of(_spoken(conn), styleprofile.text_for_stylist(conn))
            if after != before:   # the answers for the words as they were now stand for the new ones
                conn.execute("UPDATE style_answers SET key = substr(key, 1, instr(key, ':')) || ? WHERE day = ? AND "
                             "substr(key, instr(key, ':') + 1) = ? AND instr(key, ':') > 0", (after, row["day"], before))
        thing["state"] = SAVED if save else DISMISSED
        conn.execute("UPDATE style_answers SET remember = ? WHERE id = ?", (json.dumps(found), answer_id))
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return thing


def _spoken(conn) -> list[dict]:
    """Each piece's notes and rating as `words_of` reads them (the same as `today.closet_rows` gives)."""
    return [dict(r) for r in conn.execute("SELECT id, wear_notes, notes, fit_notes, rating FROM items ORDER BY id")]


def public(found: dict | None) -> dict | None:
    """What Today is told about the stylist: {state, id, read, message, talk, answering}, or None when Claude does
    not choose here."""
    if not found:
        return None
    return {"state": found["state"], "id": found["id"], "read": found["read"], "message": found["message"],
            "talk": found.get("talk") or [], "answering": found.get("answering")}

