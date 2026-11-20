"""The style conversation: talking to Claude about how you dress, not about a day's outfits (Settings, Your style,
"Talk to Claude about your style"; DECISIONS "Style through conversation").

It is the conversation on Today (`closet/stylejobs.py`) without the outfits, and shares its ways: a message is kept as
a row (`style_talk`) and answered on a thread of its own, so it survives a closed page; Claude answers in a few
sentences and may offer lines to keep in the style profile, which are kept only when the owner taps Save, through the
same `stylejobs.keep` as on Today (marked as kept from a conversation), and can be taken back (`settle`, undo). It is
asked through the same routes (the API key first), counted under the monthly limit (`closet/app.py` wires it with its
own purpose, `spend.PURPOSE_STYLE_CHAT`), and refused with a sentence when no route to Claude can be used, while a
message is being answered, in the demo closet (which never asks Claude) and at `MAX_PER_DAY` messages a day. Why a
message was not answered is said under it in the same words as on Today.

The day's messages and answers are told to Claude with each new message, as on Today; tomorrow starts empty, and what
lasts is the lines the owner kept. Opened with nothing said yet that day, the conversation asks the next question the
stylist cannot infer (`closet/stylequestions.py`), with no call to Claude.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from collections.abc import Callable
from datetime import date
from pathlib import Path

from . import db, styleprofile, stylequestions, styling
from .stylejobs import (
    DISMISSED,
    FAILED,
    OFFERED,
    READY,
    SAVED,
    STALE_S,
    TALK_MESSAGES,
    WORKING,
    Refused,
    api_first,
    failure,
    keep,
    public_thing,
    remembered,
    unkeep,
)

log = logging.getLogger("closet.stylechat")

MAX_PER_DAY = 20   # messages in the style conversation in one day, at most
# Why a message was not answered (shown under it): Today's words, less what they say about the outfits
WHY_NOT = {k: v.replace(" The outfits are as they were.", "").replace(", so the outfits are as they were", "")
           for k, v in TALK_MESSAGES.items()}
REFUSED = {
    "demo": "The demo closet never asks Claude, so your message wasn't sent. Open your own closet to talk about your style.",
    "busy": "Claude is still answering your last message.",
    "no_route": ("Claude can't be reached right now (your Claude plan is not signed in on this computer and the API "
                 "key is not switched on), so your message wasn't sent."),
    "day_limit": f"Claude has answered {MAX_PER_DAY} times today, the most in one day, so your message wasn't sent.",
    "off": "Claude isn't asked here, so your message wasn't sent.",
}
GONE = "That is no longer in the conversation. Open it again."

# What asks Claude: (brief with profile, talk, say; routes) -> {"reply", "remember": [str], "route", "model",
# "input_tokens", "output_tokens"}
Asker = Callable[[dict, tuple[str, ...]], dict]


def brief(profile: str | None, turns: list[dict], say: str) -> dict[str, str]:
    """What Claude is told: the profile in force (the starting one when the owner has written none), the day's
    conversation before this message, oldest first, and the message."""
    return {"profile": (profile or "").strip() or styling.DEFAULT_PROFILE,
            "talk": styling.talk_words(turns, None), "say": say}   # no outfits are shown, so no closet is needed


def offers(offered: object) -> list[dict]:
    """What Claude offers to keep, shaped as on Today (`styling.keeps`): about the owner's style, at most
    `styling.MAX_KEEPS`, each one sentence."""
    sentences = [{"about": 0, "text": t} for t in offered if isinstance(t, str)] if isinstance(offered, list) else []
    return styling.keeps(sentences, styling.Listed(ids=(), pieces={}, lines=()))


def tidy_say(text: object) -> str:
    """The owner's message as sent: one line, at most `styling.MAX_SAY` characters. Raises ValueError with a
    sentence."""
    said = " ".join(text.split()) if isinstance(text, str) else ""
    if not said:
        raise ValueError("Write what you want to tell Claude about your style.")
    if len(said) > styling.MAX_SAY:
        raise ValueError(f"A message to Claude can be at most {styling.MAX_SAY} characters long; this is {len(said):,}.")
    return said


def turns_of(conn, day: str) -> list[dict]:
    """The day's conversation, oldest first, in the shape Today's has (`stylejobs.talk_of`): [{id, said, state, reply,
    message, remember, at}]."""
    rows = conn.execute("SELECT * FROM style_talk WHERE day = ? ORDER BY created_at, rowid", (day,)).fetchall()
    return [{"id": r["id"], "said": r["said"], "state": r["state"], "reply": r["reply"] if r["state"] == READY else None,
             "message": WHY_NOT.get(r["error"] or "error", WHY_NOT["error"]) if r["state"] == FAILED else None,
             "remember": [public_thing(k) for k in remembered(r)] if r["state"] == READY else [],
             "at": r["created_at"]} for r in rows]


class Chat:
    """Keeps and asks the style conversation. `ask` stands in for Claude in tests; `routes` says which routes can be
    used now; `start` runs a job (a thread by default; tests hold it); `clock` tells a message that was lost."""

    def __init__(self, ask: Asker, routes: Callable[[], tuple[str, ...]], clock: Callable[[], float] = time.time,
                 start: Callable[[Callable[[], None]], None] | None = None):
        self.ask, self.routes, self.clock = ask, routes, clock
        self.start = start or (lambda job: threading.Thread(target=job, name="closet-style-chat", daemon=True).start())
        self._lock = threading.Lock()

    def _answering(self, conn, day: str):
        """The message Claude is answering now, or None. One lost when the program stopped is marked so."""
        row = conn.execute("SELECT * FROM style_talk WHERE day = ? AND state = ? ORDER BY created_at DESC, rowid DESC "
                           "LIMIT 1", (day, WORKING)).fetchone()
        if row is not None and self.clock() - float(row["asked_at"]) > STALE_S:
            conn.execute("UPDATE style_talk SET state = ?, error = 'lost', finished_at = ? WHERE day = ? AND state = ?",
                         (FAILED, db.now(), day, WORKING))
            return None
        return row

    def _problem(self, conn, day: str, demo: bool) -> str | None:
        if demo:
            return "demo"
        if not api_first(self.routes()):
            return "no_route"
        if conn.execute("SELECT COUNT(*) FROM style_talk WHERE day = ?", (day,)).fetchone()[0] >= MAX_PER_DAY:
            return "day_limit"
        return None

    def state(self, conn, day: date, demo: bool) -> dict:
        """The conversation as it stands: see `state_of`, with this stylist's routes and clock."""
        with self._lock:
            answering = self._answering(conn, day.isoformat())
            problem = self._problem(conn, day.isoformat(), demo)
        return state_of(conn, day, answering["id"] if answering else None, problem)

    def say(self, conn, path: Path, text: object, day: date, demo: bool) -> dict:
        """Send the owner's message and give back the conversation, with the message being answered. Raises
        ValueError for a message that is not one, `Refused` with a sentence when it cannot be sent."""
        said = tidy_say(text)
        with self._lock:
            if self._answering(conn, day.isoformat()) is not None:
                raise Refused(REFUSED["busy"])
            problem = self._problem(conn, day.isoformat(), demo)
            if problem:
                raise Refused(REFUSED[problem])
            told = brief(styleprofile.text_for_stylist(conn), turns_of(conn, day.isoformat()), said)
            turn_id = uuid.uuid4().hex
            conn.execute("INSERT INTO style_talk (id, day, said, state, asked_at, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                         (turn_id, day.isoformat(), said, WORKING, self.clock(), db.now()))
            usable = api_first(self.routes())
        self.start(lambda: self._run(path, turn_id, told, usable))
        return state_of(conn, day, turn_id, None)

    def _run(self, path: Path, turn_id: str, told: dict, usable: tuple[str, ...]) -> None:
        """Ask and keep the answer; never left "working"."""
        started = time.monotonic()
        meta, error, reply, things = {}, None, None, []
        try:
            meta = self.ask(told, usable)
            reply = " ".join(str(meta.get("reply") or "").split())[:styling.MAX_REPLY] or None
            things = offers(meta.get("remember"))
            if not reply:
                error = "answer"
        except Exception as e:
            error = failure(e, "the style conversation failed")
        conn = db.connect(path)
        try:
            conn.execute(
                "UPDATE style_talk SET state = ?, reply = ?, remember = ?, error = ?, route = ?, model = ?, "
                "input_tokens = ?, output_tokens = ?, seconds = ?, finished_at = ? WHERE id = ? AND state = ?",
                (FAILED if error else READY, None if error else reply,
                 json.dumps(things) if things and not error else None, error, meta.get("route"), meta.get("model"),
                 int(meta.get("input_tokens") or 0), int(meta.get("output_tokens") or 0),
                 round(time.monotonic() - started, 1), db.now(), turn_id, WORKING))
        except Exception:
            log.exception("the style conversation's answer could not be kept")
        finally:
            conn.close()


def state_of(conn, day: date, answering: str | None, problem: str | None) -> dict:
    """What the page is told: {turns, answering, question, refused}. `question` is the next question the stylist
    cannot infer, asked while nothing has been said today (else None); `refused` is why a message cannot be sent now
    (no route to Claude, the day's limit, the demo closet, or no conversation here at all), or None."""
    turns = turns_of(conn, day.isoformat())
    return {"turns": turns, "answering": answering,
            "question": None if turns else stylequestions.next_question(conn),
            "refused": REFUSED[problem] if problem else None}


def settle(conn, turn_id: str, index: object, save: bool, undo: bool = False) -> dict:
    """The owner's answer to a line Claude offered to keep: keep it (`save`, a new line of Your style) or not, or take
    back one kept (`undo`: it is offered again). Gives the thing back as it now stands; raises `Refused` with a
    sentence when it is unknown or cannot be kept. Answering twice changes nothing."""
    row = conn.execute("SELECT * FROM style_talk WHERE id = ?", (turn_id,)).fetchone()
    found = remembered(row) if row is not None else []
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(found):
        raise Refused(GONE)
    thing = found[index]
    if thing.get("state") != (SAVED if undo else OFFERED):
        return public_thing(thing)
    conn.execute("BEGIN IMMEDIATE")
    try:
        if undo:
            unkeep(conn, thing)
        elif save:
            keep(conn, thing, GONE)
        thing["state"] = OFFERED if undo else SAVED if save else DISMISSED
        conn.execute("UPDATE style_talk SET remember = ? WHERE id = ?", (json.dumps(found), turn_id))
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return public_thing(thing)
