"""Claude's outfits asked for ahead of the owner's first look at Today, so that the first open of the day does not
wait (BACKLOG, "Outfits chosen by Claude", step 2: "asking ahead of the first look in the morning").

While the program runs, `Ahead.tick` is called every couple of minutes. Once a day, from `FROM_HOUR` in the morning
(or whenever the computer is next awake after that), it asks Today for the owner's own closet with the occasion
and mood the owner last had on Today, exactly as the page will on its first open: that starts Claude choosing in
the background (`closet/stylejobs.py`), and the answer is kept for the day. When the owner then opens Today with
the same choices, Claude's outfits are there at once.

It asks for the hours from when the owner usually first looks at Today (the middle one of the hours of their last
`FIRST_HOURS` first looks), not from the early hour it is asked at: the day is read for the hours still to come, so
an answer for a freezing seven o'clock would be asked again at nine as weather that had moved.

It asks nothing:
- in the demo closet, or with **Let Claude choose my outfits** switched off;
- before `FROM_HOUR` (a late night is still yesterday's evening, and the day's forecast should be in);
- when Today has not been opened for more than `AWAY_DAYS` days (the owner is away: nothing to dress, nothing spent);
- once Today has been asked today, by the page or by this;
- while there is no forecast for today (it is tried again: outfits for a guessed mild day would only be asked
  again when the owner opens Today), or no route to Claude, or no outfit the closet can make.

One question a day: when Claude could not be reached, the owner's own first open asks again, by the rules there.
A look that could ask nothing (no forecast, no route) is tried again `TRY_AGAIN_S` later, not at every tick.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import date, datetime, timedelta

from . import db, outfits, stylejobs, today, wears
from .config import Config
from .state import State

log = logging.getLogger("closet.styleahead")

FROM_HOUR = 5        # not before five in the morning, by the computer's clock
AWAY_DAYS = 3        # not when Today was last opened more than this many days ago
CHECK_EVERY = 120    # seconds between looks at whether it is time (a look costs nothing until it is)
FIRST_WAIT = 60      # after the program starts, let it settle first
TRY_AGAIN_S = 900    # after a look that could ask nothing (no forecast, no route), the next try is this much later
FIRST_HOURS = 7      # the hours of the owner's last this many first looks at Today are kept
CHOICES = ("occasion", "mood")   # what the page sends on a first open, and so what is asked ahead


def now() -> datetime:
    """The computer's local time (tests give their own)."""
    return datetime.now()


def _hours(state: State) -> list[int]:
    kept = state.get("today_first_hours")
    return [h for h in kept if isinstance(h, int) and not isinstance(h, bool) and 0 <= h <= 23] if isinstance(kept, list) else []


def usual_hour(state: State) -> int | None:
    """The hour the owner usually first looks at Today: the middle one of the hours kept (one late morning does not
    move it), or None when none is kept yet."""
    hours = sorted(_hours(state))
    return hours[(len(hours) - 1) // 2] if hours else None


def remember(state: State, body: object, day: date, hour: int | None = None) -> None:
    """Note that the page asked Today on `day`, and the occasion and mood it asked with: what is asked ahead
    tomorrow. The day's first look also keeps its `hour` (the computer's clock), for `usual_hour`. Called for the
    owner's own closet only."""
    choice = {k: body[k] for k in CHOICES if isinstance(body, dict) and isinstance(body.get(k), str)}
    changes: dict = {"today_opened": day.isoformat(), "today_choice": choice}
    if hour is not None and state.get("today_opened") != day.isoformat():
        changes["today_first_hours"] = [*_hours(state), hour][-FIRST_HOURS:]
    state.update(**changes)


class Ahead:
    """Asks Claude for the day's outfits ahead of the owner. `now` is the computer's local time (tests give their
    own); `start`/`stop` run `tick` on a thread of its own, as the other schedulers do."""


    def __init__(self, cfg: Config, state: State, stylist: Callable[[], stylejobs.Stylist | None],
                 now: Callable[[], datetime] = now, check_every: float = CHECK_EVERY,
                 first_wait: float = FIRST_WAIT):
        # `stylist` gives who asks Claude now, or None (asked each time, so that taking the stylist away from the
        # services, as the browser tests do, also stops asking ahead)
        self.cfg, self.state, self.stylist, self.now = cfg, state, stylist, now
        self.check_every, self.first_wait = check_every, first_wait
        self._again: datetime | None = None   # after a look that could ask nothing: not before this
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def tick(self) -> str:
        """Ask ahead when it is time. Says what it did, in a word: "asked", or why not ("demo", "off", "done",
        "early", "away", "waiting", "no_forecast", "no_route", "refused")."""
        state = self.state
        profile = state.get("profile")
        if profile == "demo":
            return "demo"
        stylist = self.stylist()
        if stylist is None or not state.get("stylist_on"):
            return "off"
        day = wears.today()
        if day.isoformat() in (state.get("today_asked_ahead"), state.get("today_opened")):
            return "done"
        at = self.now()
        if at.hour < FROM_HOUR:
            return "early"
        try:
            opened = date.fromisoformat(state.get("today_opened") or "")
        except (TypeError, ValueError):   # never opened (the owner does not use Today yet), or not a date at all
            return "away"
        if (day - opened).days > AWAY_DAYS:
            return "away"
        if self._again is not None and at < self._again:
            return "waiting"
        choice = state.get("today_choice")
        body = {k: choice[k] for k in CHOICES if isinstance(choice, dict) and isinstance(choice.get(k), str)}
        path = self.cfg.db_path(profile)
        conn = db.connect(path)
        try:
            answer = today.suggest(conn, state, body, stylist, path, ahead=True, from_hour=usual_hour(state))
        except outfits.ContextError:   # a choice kept from an older version that is no longer one: not asked ahead
            state.update(today_asked_ahead=day.isoformat())
            return "refused"
        finally:
            conn.close()
        found = answer["context"].get("stylist")
        if found is None or found["id"] is None:
            # no forecast for today yet (or no outfit to be had), or nothing was asked (no route to Claude just
            # now): tried again in a while
            self._again = at + timedelta(seconds=TRY_AGAIN_S)
            return "no_forecast" if found is None else "no_route"
        self._again = None
        state.update(today_asked_ahead=day.isoformat())
        return "asked"

    # ------------------------------------------------------------------ the thread
    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="outfits-ahead", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        self._stop.wait(self.first_wait)
        while not self._stop.is_set():
            try:
                did = self.tick()
                if did == "asked":
                    log.info("asked Claude for today's outfits ahead of the first look")
            except Exception:
                log.exception("asking for today's outfits ahead failed")
            self._stop.wait(self.check_every)
