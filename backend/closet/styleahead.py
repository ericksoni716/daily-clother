"""Claude's outfits asked for ahead of the owner's first look at Today, so that the first open of the day does not
wait (BACKLOG, "Outfits chosen by Claude", step 2: "asking ahead of the first look in the morning").

While the program runs, `Ahead.tick` is called every couple of minutes. Once a day, from `FROM_HOUR` in the morning
(or whenever the computer is next awake after that), it asks Today for the owner's own closet with the occasion
and mood the owner last had on Today, exactly as the page will on its first open: that starts Claude choosing in
the background (`closet/stylejobs.py`), and the answer is kept for the day. When the owner then opens Today with
the same choices, Claude's outfits are there at once.

It asks nothing:
- in the demo closet, or with **Let Claude choose my outfits** switched off;
- before `FROM_HOUR` (a late night is still yesterday's evening, and the day's forecast should be in);
- when Today has not been opened for more than `AWAY_DAYS` days (the owner is away: nothing to dress, nothing spent);
- once Today has been asked today, by the page or by this;
- while there is no forecast for today (it is tried again: outfits for a guessed mild day would only be asked
  again when the owner opens Today), or no route to Claude, or no outfit the closet can make.

One try a day: when Claude could not be reached, the owner's own first open asks again, by the rules there.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import date, datetime

from . import db, outfits, stylejobs, today, wears
from .config import Config
from .state import State

log = logging.getLogger("closet.styleahead")

FROM_HOUR = 5        # not before five in the morning, by the computer's clock
AWAY_DAYS = 3        # not when Today was last opened more than this many days ago
CHECK_EVERY = 120    # seconds between looks at whether it is time (a look costs nothing until it is)
FIRST_WAIT = 60      # after the program starts, let it settle first
CHOICES = ("occasion", "mood")   # what the page sends on a first open, and so what is asked ahead


def remember(state: State, body: object, day: date) -> None:
    """Note that the page asked Today on `day`, and the occasion and mood it asked with: what is asked ahead
    tomorrow. Called for the owner's own closet only."""
    choice = {k: body[k] for k in CHOICES if isinstance(body, dict) and isinstance(body.get(k), str)}
    state.update(today_opened=day.isoformat(), today_choice=choice)


class Ahead:
    """Asks Claude for the day's outfits ahead of the owner. `now` is the computer's local time (tests give their
    own); `start`/`stop` run `tick` on a thread of its own, as the other schedulers do."""


    def __init__(self, cfg: Config, state: State, stylist: Callable[[], stylejobs.Stylist | None],
                 now: Callable[[], datetime] = datetime.now, check_every: float = CHECK_EVERY,
                 first_wait: float = FIRST_WAIT):
        # `stylist` gives who asks Claude now, or None (asked each time, so that taking the stylist away from the
        # services, as the browser tests do, also stops asking ahead)
        self.cfg, self.state, self.stylist, self.now = cfg, state, stylist, now
        self.check_every, self.first_wait = check_every, first_wait
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def tick(self) -> str:
        """Ask ahead when it is time. Says what it did, in a word: "asked", or why not ("demo", "off", "done",
        "early", "away", "no_forecast", "no_route", "refused")."""
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
        if self.now().hour < FROM_HOUR:
            return "early"
        try:
            opened = date.fromisoformat(state.get("today_opened") or "")
        except (TypeError, ValueError):   # never opened (the owner does not use Today yet), or not a date at all
            return "away"
        if (day - opened).days > AWAY_DAYS:
            return "away"
        choice = state.get("today_choice")
        body = {k: choice[k] for k in CHOICES if isinstance(choice, dict) and isinstance(choice.get(k), str)}
        path = self.cfg.db_path(profile)
        conn = db.connect(path)
        try:
            answer = today.suggest(conn, state, body, stylist, path, ahead=True)
        except outfits.ContextError:   # a choice kept from an older version that is no longer one: not asked ahead
            state.update(today_asked_ahead=day.isoformat())
            return "refused"
        finally:
            conn.close()
        found = answer["context"].get("stylist")
        if found is None:      # no forecast for today yet, or no outfit to be had: looked at again next time
            return "no_forecast"
        if found["id"] is None:   # nothing was asked (no route to Claude just now): looked at again next time
            return "no_route"
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
