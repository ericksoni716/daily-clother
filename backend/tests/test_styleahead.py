"""Claude's outfits asked for ahead of the owner's first look at Today (closet/styleahead.py): once a day, from
FROM_HOUR, with the occasion and mood the page last asked with, for a day read from today's forecast. Claude and
Open-Meteo are always stood in for; the background job is held and run by the test, and both clocks are the test's
(the computer's for `Ahead.now`, the weather's for the forecast)."""
import threading
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from closet import app as app_module
from closet import db, styleahead, wears, weather
from closet import today as today_module
from closet.styleahead import AWAY_DAYS, FROM_HOUR
from closet.stylejobs import RETRY_S
from closet.tagger.tagging import Unreachable

from . import test_stylejobs as jobs
from .test_day import HourlyOpenMeteo, reader, reading
from .test_stylejobs import TODAY, answers, run, wardrobe

styled = jobs.styled   # services whose stylist asks the stand-in, with held jobs and the test's clock

SIX_IN_NEW_YORK = datetime(2026, 11, 17, 11, 0, tzinfo=UTC).timestamp()   # the weather's clock: 6am at home
FIRST = {"occasion": "casual", "mood": "usual"}   # what the page sends on its first open, by default
SMART = {"occasion": "smart_casual", "mood": "sharp"}


@pytest.fixture(autouse=True)
def om(monkeypatch):
    """Today is TODAY, at home (New York) there is a forecast for it hour by hour, and the internet is never asked.
    `om.day["d"]` moves the day; `om.down` takes the weather service away."""
    om = HourlyOpenMeteo()
    om.forecast["date"] = TODAY.isoformat()
    om.clock = {"now": SIX_IN_NEW_YORK}
    om.day = {"d": TODAY}
    monkeypatch.setattr(wears, "today", lambda: om.day["d"])
    monkeypatch.setattr(weather, "_now", lambda: om.clock["now"])
    monkeypatch.setattr(weather, "fetch", om)
    return om


# ------------------------------------------------------------------ helpers
def move_to(om, days: int) -> None:
    """The next day (or days later): the computer's date, the forecast's date and the weather's clock all move."""
    om.day["d"] = TODAY + timedelta(days=days)
    om.forecast["date"] = om.day["d"].isoformat()
    om.clock["now"] = SIX_IN_NEW_YORK + days * 86400


def at(styled, hour: int, minute: int = 0) -> None:
    """The computer's clock, on today's date."""
    d = wears.today()
    styled.sv.ahead.now = lambda: datetime(d.year, d.month, d.day, hour, minute)


def opened(styled, days_ago: int = 1, choice: dict | None = None) -> None:
    """Today was last opened by the page `days_ago` days ago, with `choice` (as `remember` keeps it)."""
    styled.sv.state.update(today_opened=(wears.today() - timedelta(days=days_ago)).isoformat(),
                           today_choice={} if choice is None else choice)


def tick(styled, hour: int = 6) -> str:
    at(styled, hour)
    return styled.sv.ahead.tick()


def todays(styled) -> list[dict]:
    return [r for r in answers(styled.cfg) if r["day"] == wears.today().isoformat()]


def marked(styled):
    return styled.sv.state.get("today_asked_ahead")


def first_open(styled, **body) -> dict:
    """The page opening Today: the occasion and mood only, no day typed, so the forecast is used."""
    r = styled.c.post("/api/outfits/today", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def nothing_asked(styled) -> bool:
    return styled.held == [] and todays(styled) == [] and styled.stand_in.calls == []


# ------------------------------------------------------------------ the happy path
def test_the_morning_after_a_look_at_today_claude_is_asked_once_and_the_first_open_is_ready_at_once(styled, om):
    wardrobe(styled.c)
    move_to(om, -1)   # yesterday the page asked Today with a choice of its own
    first_open(styled, **SMART)
    run(styled)
    assert styled.sv.state.get("today_opened") == (TODAY - timedelta(days=1)).isoformat()
    assert styled.sv.state.get("today_choice") == SMART
    calls_before = len(styled.stand_in.calls)

    move_to(om, 0)
    assert tick(styled) == "asked"
    assert len(styled.held) == 1
    [row] = todays(styled)
    assert row["state"] == "working"
    assert marked(styled) == TODAY.isoformat()
    run(styled)
    [(brief, _)] = styled.stand_in.calls[calls_before:]
    assert "Occasion: smart casual. Mood: sharp." in brief["day"]
    assert [r["state"] for r in todays(styled)] == ["ready"]

    body = first_open(styled, **SMART)
    st = body["context"]["stylist"]
    assert body["context"]["source"] == "forecast" and body["context"]["old"] is False
    assert st["state"] == "ready" and st["id"] == row["id"]
    assert body["outfits"][0].get("by") == "claude"
    assert styled.held == [] and len(todays(styled)) == 1 and len(styled.stand_in.calls) == calls_before + 1


def test_it_is_asked_once_a_day_and_again_the_next_day(styled, om):
    wardrobe(styled.c)
    opened(styled, choice=FIRST)
    assert tick(styled) == "asked"
    run(styled)
    assert tick(styled) == "done" and tick(styled, 14) == "done"
    assert len(todays(styled)) == 1 and styled.held == []
    move_to(om, 1)
    assert tick(styled) == "asked"
    assert len(todays(styled)) == 1 and len(styled.held) == 1 and marked(styled) == wears.today().isoformat()


def test_when_the_page_has_asked_today_already_nothing_is_asked_ahead(styled):
    wardrobe(styled.c)
    first_open(styled, **FIRST)
    run(styled)
    calls = len(styled.stand_in.calls)
    assert tick(styled) == "done"
    assert styled.held == [] and len(todays(styled)) == 1 and len(styled.stand_in.calls) == calls
    assert marked(styled) is None


# ------------------------------------------------------------------ when it asks
def test_before_from_hour_nothing_is_asked_and_at_from_hour_it_is(styled):
    wardrobe(styled.c)
    opened(styled)
    at(styled, FROM_HOUR - 1, 59)
    assert styled.sv.ahead.tick() == "early"
    assert tick(styled, 0) == "early"
    assert nothing_asked(styled) and marked(styled) is None
    assert tick(styled, FROM_HOUR) == "asked"
    assert len(styled.held) == 1


def test_when_today_was_never_opened_nothing_is_asked(styled):
    wardrobe(styled.c)
    assert styled.sv.state.get("today_opened") is None
    assert tick(styled) == "away"
    assert nothing_asked(styled) and marked(styled) is None


def test_today_opened_away_days_ago_is_still_asked_for(styled):
    wardrobe(styled.c)
    opened(styled, days_ago=AWAY_DAYS)
    assert tick(styled) == "asked"


def test_today_opened_more_than_away_days_ago_means_the_owner_is_away(styled):
    wardrobe(styled.c)
    opened(styled, days_ago=AWAY_DAYS + 1)
    assert tick(styled) == "away"
    assert nothing_asked(styled) and marked(styled) is None


@pytest.mark.parametrize("kept", ["yesterday", "", 20261116, ["2026-11-16"]])
def test_a_day_opened_that_is_not_a_date_counts_as_never_opened(styled, kept):
    wardrobe(styled.c)
    styled.sv.state.update(today_opened=kept, today_choice={})
    assert tick(styled) == "away"
    assert nothing_asked(styled)


# ------------------------------------------------------------------ where it never asks
def test_the_demo_closet_is_never_asked_ahead(styled):
    wardrobe(styled.c)
    assert styled.c.post("/api/profile", json={"profile": "demo"}).status_code == 200
    opened(styled)
    assert tick(styled) == "demo"
    assert styled.held == [] and styled.stand_in.calls == [] and answers(styled.cfg) == []


def test_with_the_stylist_switched_off_nothing_is_asked_ahead(styled):
    wardrobe(styled.c)
    opened(styled)
    assert styled.c.put("/api/settings", json={"stylist_on": False}).status_code == 200
    assert tick(styled) == "off"
    assert nothing_asked(styled) and marked(styled) is None


def test_with_no_stylist_at_all_nothing_is_asked_ahead(styled):
    wardrobe(styled.c)
    opened(styled)
    stylist = styled.sv.stylist
    styled.sv.stylist = None
    try:
        assert tick(styled) == "off"
    finally:
        styled.sv.stylist = stylist
    assert nothing_asked(styled) and marked(styled) is None


# ------------------------------------------------------------------ the forecast
def test_with_no_forecast_nothing_is_asked_nor_marked_and_a_later_look_with_one_asks(styled, om):
    wardrobe(styled.c)
    opened(styled)
    om.down = True
    assert tick(styled) == "no_forecast"
    assert nothing_asked(styled) and marked(styled) is None
    om.down = False
    assert tick(styled) == "asked"
    assert len(styled.held) == 1 and marked(styled) == TODAY.isoformat()


def test_an_old_forecast_for_today_is_not_asked_for(styled, om):
    wardrobe(styled.c)
    opened(styled)
    assert styled.c.get("/api/weather").json()["weather"]["date"] == TODAY.isoformat()   # kept in the state
    om.clock["now"] += 2 * 3600
    om.down = True
    assert weather.lookup(styled.sv.state)["old"] is True
    assert tick(styled, 8) == "no_forecast"
    assert nothing_asked(styled) and marked(styled) is None


def test_a_forecast_for_an_earlier_day_is_not_asked_for(styled, om):
    wardrobe(styled.c)
    move_to(om, -1)
    styled.c.get("/api/weather")   # yesterday's forecast is kept
    move_to(om, 0)
    opened(styled)
    om.down = True
    assert tick(styled) == "no_forecast"
    assert nothing_asked(styled)


# ------------------------------------------------------------------ Claude, the closet, the choice
def test_with_no_route_to_claude_nothing_is_asked_nor_marked_and_the_next_look_asks(styled):
    wardrobe(styled.c)
    opened(styled)
    styled.claude.mode = "unavailable"
    assert tick(styled) == "no_route"
    assert answers(styled.cfg) == [] and styled.held == [] and marked(styled) is None
    styled.claude.mode = "answers"
    assert tick(styled) == "asked"
    assert len(todays(styled)) == 1 and len(styled.held) == 1


def test_a_closet_that_cannot_dress_the_owner_is_not_asked_for_nor_marked(styled):
    wardrobe(styled.c, shoes=False)
    opened(styled)
    assert tick(styled) != "asked"
    assert nothing_asked(styled) and marked(styled) is None


def test_when_claude_cannot_be_reached_ahead_it_is_not_asked_again_that_day_and_the_first_open_follows_its_rules(styled):
    wardrobe(styled.c)
    opened(styled, choice=FIRST)
    styled.stand_in.error = Unreachable("offline")
    assert tick(styled) == "asked"
    first = todays(styled)[0]["id"]
    run(styled)
    assert [r["state"] for r in todays(styled)] == ["failed"]
    assert tick(styled) == "done" and styled.held == []
    styled.stand_in.error = None
    st = first_open(styled, **FIRST)["context"]["stylist"]
    assert st["state"] == "failed" and st["id"] == first and styled.held == []
    styled.now["t"] += RETRY_S
    st = first_open(styled, **FIRST)["context"]["stylist"]
    assert st["state"] == "working" and st["id"] != first and len(styled.held) == 1


def test_the_choice_asked_ahead_is_the_one_remembered(styled):
    wardrobe(styled.c)
    opened(styled, choice=SMART)
    assert tick(styled) == "asked"
    run(styled)
    [(brief, _)] = styled.stand_in.calls
    assert "Occasion: smart casual. Mood: sharp." in brief["day"]
    assert first_open(styled, **SMART)["context"]["stylist"]["state"] == "ready"


def test_with_no_choice_remembered_the_defaults_are_asked_and_the_pages_default_first_open_is_ready(styled):
    wardrobe(styled.c)
    opened(styled, choice={})
    assert tick(styled) == "asked"
    run(styled)
    [(brief, _)] = styled.stand_in.calls
    assert "Occasion: casual. Mood: usual." in brief["day"]
    body = first_open(styled, **FIRST)
    assert body["context"]["stylist"]["state"] == "ready" and styled.held == [] and len(todays(styled)) == 1


def test_a_remembered_choice_kept_in_another_shape_is_read_as_no_choice(styled):
    wardrobe(styled.c)
    styled.sv.state.update(today_opened=(TODAY - timedelta(days=1)).isoformat(),
                           today_choice={"occasion": 7, "mood": None, "build_around": "x"})
    assert tick(styled) == "asked"
    run(styled)
    assert "Occasion: casual. Mood: usual." in styled.stand_in.calls[0][0]["day"]


def test_a_remembered_choice_that_is_no_longer_one_is_refused_and_marked_and_nothing_asked(styled):
    wardrobe(styled.c)
    opened(styled, choice={"occasion": "spaceship"})
    assert tick(styled) == "refused"
    assert nothing_asked(styled) and marked(styled) == TODAY.isoformat()
    assert tick(styled) == "done"


def test_a_note_that_moves_the_day_elsewhere_is_asked_for_there_and_the_first_open_is_ready(styled):
    wardrobe(styled.c)
    styled.sv.day_reader = reader(reading(place="Lisbon, Portugal", days=2))
    r = styled.c.put("/api/day", json={"text": "In Lisbon today and tomorrow"})
    assert r.status_code == 200 and r.json()["note"]["active"] is True, r.text
    opened(styled, choice=FIRST)
    assert tick(styled) == "asked"
    run(styled)
    [(brief, _)] = styled.stand_in.calls
    assert "Lisbon" in brief["day"]
    body = first_open(styled, **FIRST)
    assert body["context"]["place"] == "Lisbon, Portugal" and body["context"]["source"] == "forecast"
    assert body["context"]["stylist"]["state"] == "ready" and styled.held == [] and len(todays(styled)) == 1


# ------------------------------------------------------------------ remember, through the Today route
def test_the_today_route_remembers_the_day_and_only_the_occasion_and_mood(styled):
    ids = wardrobe(styled.c)
    first_open(styled, occasion="smart_casual", mood="relaxed", build_around=ids["shirt"], leave_out=[ids["jeans"]],
               count=4, low_c=8)
    assert styled.sv.state.get("today_opened") == TODAY.isoformat()
    assert styled.sv.state.get("today_choice") == {"occasion": "smart_casual", "mood": "relaxed"}
    first_open(styled, occasion="business")
    assert styled.sv.state.get("today_choice") == {"occasion": "business"}


def test_a_today_request_without_a_choice_remembers_an_empty_one(styled):
    wardrobe(styled.c)
    first_open(styled)
    assert styled.sv.state.get("today_opened") == TODAY.isoformat()
    assert styled.sv.state.get("today_choice") == {}


def test_remember_keeps_only_strings_and_reads_a_body_that_is_not_an_object_as_no_choice(styled):
    state = styled.sv.state
    styleahead.remember(state, {"occasion": "business", "mood": 3, "say": "hi"}, TODAY)
    assert state.get("today_choice") == {"occasion": "business"} and state.get("today_opened") == "2026-11-17"
    styleahead.remember(state, ["occasion"], TODAY)
    assert state.get("today_choice") == {}


def test_the_demo_closet_remembers_nothing(styled):
    assert styled.c.post("/api/profile", json={"profile": "demo"}).status_code == 200
    first_open(styled, **SMART)
    assert styled.sv.state.get("today_opened") is None and styled.sv.state.get("today_choice") is None


def test_a_refused_today_request_remembers_nothing(styled):
    wardrobe(styled.c)
    r = styled.c.post("/api/outfits/today", json={"occasion": "spaceship", "mood": "usual"})
    assert r.status_code == 422
    assert styled.sv.state.get("today_opened") is None and styled.sv.state.get("today_choice") is None


# ------------------------------------------------------------------ suggest(ahead=True)
def suggest_ahead(styled, body: dict) -> dict:
    path = styled.cfg.db_path("main")
    conn = db.connect(path)
    try:
        return today_module.suggest(conn, styled.sv.state, body, styled.sv.stylist, path, ahead=True)
    finally:
        conn.close()


def test_suggest_ahead_asks_claude_for_a_day_from_todays_forecast(styled):
    wardrobe(styled.c)
    answer = suggest_ahead(styled, {})
    assert answer["context"]["source"] == "forecast" and answer["context"]["stylist"]["state"] == "working"
    assert len(styled.held) == 1


def test_suggest_ahead_with_the_day_typed_asks_nothing(styled):
    wardrobe(styled.c)
    answer = suggest_ahead(styled, dict(jobs.DAY))
    assert answer["context"]["source"] == "given" and answer["outfits"]
    assert "stylist" not in answer["context"] and nothing_asked(styled)


def test_suggest_ahead_with_the_mild_guess_asks_nothing(styled, om):
    wardrobe(styled.c)
    om.down = True
    answer = suggest_ahead(styled, {})
    assert answer["context"]["source"] == "mild" and answer["outfits"]
    assert "stylist" not in answer["context"] and nothing_asked(styled)


def test_suggest_ahead_with_part_of_the_day_typed_asks_nothing(styled):
    wardrobe(styled.c)
    answer = suggest_ahead(styled, {"rain": True})
    assert answer["context"]["source"] == "forecast and given"
    assert "stylist" not in answer["context"] and nothing_asked(styled)


# ------------------------------------------------------------------ the thread and the services
def test_the_thread_looks_again_and_again_and_stops_promptly(styled):
    ahead = styleahead.Ahead(styled.cfg, styled.sv.state, lambda: None, check_every=0.01, first_wait=0)
    calls = []
    lock = threading.Lock()

    def counted():
        with lock:
            calls.append(1)
        return "off"

    ahead.tick = counted
    ahead.start()
    deadline = time.monotonic() + 5
    while len(calls) < 3 and time.monotonic() < deadline:
        time.sleep(0.01)
    began = time.monotonic()
    ahead.stop()
    assert time.monotonic() - began < 1
    assert len(calls) >= 3 and not ahead._thread.is_alive()


def test_a_failure_inside_a_look_does_not_stop_the_thread(styled):
    ahead = styleahead.Ahead(styled.cfg, styled.sv.state, lambda: None, check_every=0.01, first_wait=0)
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("once")
        return "off"

    ahead.tick = flaky
    ahead.start()
    deadline = time.monotonic() + 5
    while len(calls) < 3 and time.monotonic() < deadline:
        time.sleep(0.01)
    ahead.stop()
    assert len(calls) >= 3 and not ahead._thread.is_alive()


def test_stopping_before_starting_is_harmless(styled):
    ahead = styleahead.Ahead(styled.cfg, styled.sv.state, lambda: None)
    ahead.stop()
    assert ahead._thread is None


def test_every_services_object_has_an_ahead_that_asks_with_the_services_stylist_of_the_moment(styled):
    ahead = styled.sv.ahead
    assert isinstance(ahead, styleahead.Ahead)
    assert ahead.state is styled.sv.state and ahead.cfg is styled.cfg
    assert ahead.stylist() is styled.sv.stylist
    styled.sv.stylist = None
    assert ahead.stylist() is None


class Recorder:
    def __init__(self, said: list, name: str):
        self.said, self.name, self.ready = said, name, True

    def start(self):
        self.said.append(f"{self.name} start")

    def stop(self):
        self.said.append(f"{self.name} stop")


def test_the_services_start_and_stop_the_ahead_with_the_other_schedulers(cfg):
    said: list = []
    sv = app_module.Services(cfg, SimpleNamespace(), Recorder(said, "model"), Recorder(said, "worker"),
                             Recorder(said, "scheduler"), ahead=Recorder(said, "ahead"))
    sv.start()
    assert "ahead start" in said
    said.clear()
    sv.stop()
    assert "ahead stop" in said
