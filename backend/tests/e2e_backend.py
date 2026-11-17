"""Starts Closet for the browser tests with stand-ins for the model and for Claude.

    cd backend && python -m tests.e2e_backend --no-browser --no-tray --port N

Every backend the browser tests start runs from here, so none of them reaches the
weather service: Open-Meteo and Nominatim are always out of reach (the place is
New York until one is chosen, so Today would otherwise ask the real one). The
specs fake the answers they need in the browser. With CLOSET_E2E_FAKES empty
nothing else is replaced: the model and Claude are the real code.

The cutout is the middle of the photo and Claude always answers with the fixed
answer in `conftest.ANSWER`, so the browser can follow an item from upload to
described without the model file or any call to Claude.

With CLOSET_E2E_ROUTES=api the plan route cannot be used and the API route is
the real one (its spend recorded and kept under the owner's limit) talking to
`conftest.FakeApi` instead of Anthropic: each request reports 20,000 tokens in
and 12,000 out, $0.008 at the prices written down, so a $0.01 limit allows
exactly one. Corrections by sentence
are read by the same stand-in the backend tests use (or, with CLOSET_E2E_ROUTES=api, by the
real API route talking to `conftest.FakeApi`).

Searching shops for a wish is a stand-in too (`FakeShop`): after a second it "finds" a tan rain-proof coat, a
navy polo and a product with a link that is not a web address (which the app drops), and a price check sees every
price 20% lower. With CLOSET_E2E_SEED=demo the owner's own closet starts as a copy of the demo closet, so what is
found is checked against a closet with something in it (the demo closet itself never searches).

Finding the pieces in a photo of several is a stand-in too: after a second it gives the boxes of
`conftest.GARMENT_BOXES` (a red piece left, a blue one in the middle, a green one right), whatever the photo.

Sorting a shoe's photos into views is a stand-in too (`conftest.views_answer`): after a second it says the photos
show, in the order sent, the outer side, from above, the inner side, the front, the back and the sole, with the two
sides unsure and looking different once both are there, so the page asks which photo shows the outside. With
CLOSET_E2E_ROUTES=api the real API route asks `conftest.FakeApi`, which answers the same.

Drawing a shoe from its photos runs the real steps (two drawings straight on, the judge, two turns, the judge again;
each drawing made safe, rendered and checked) with a stand-in for Claude's answers: after a second each, every drawing,
straight on or turned, is the dress shoe the owner liked (`conftest.draw_answer`), the first check of each says it is
good and the judge keeps the first with no fault named (so nothing is fixed), as if on the Claude plan, with made-up
token counts. With CLOSET_E2E_ROUTES=api the real
API route asks `conftest.FakeApi`, which answers the same. Changing a drawing from the owner's note runs the real steps
too: whatever the note, after a second each, the dress shoe comes back with black laces (`conftest.correct_answer`),
said to go against the photos, and the first check says it is good.

With CLOSET_E2E_TAG_FAILS=N the first N descriptions fail with a reason Closet does not recognise, which quotes
something shaped like a key and a file outside Closet's folder (both made up), so the page can show a failed item.

The API key box keeps keys in a stand-in keychain (never the computer's), and the check with Anthropic is a
stand-in too: a key ending in "refused" is turned down, any other well-formed key is accepted.
"""
import json
import os
import shutil
import sqlite3
import sys
import time
import urllib.error

from closet import apikey, app, cli, demo, tracejobs, weather
from closet.tagger import routes as tagger_routes
from closet.tagger import shoedrawing
from closet.tagger.correcting import CorrectionResult
from closet.tagger.shopping import Found, PriceAnswer, PriceSeen, ShopAnswer
from closet.tagger.tagging import TaggingError, TagResult

from .conftest import (
    ANSWER,
    GARMENT_BOXES,
    FakeApi,
    FakeClaude,
    MemoryKeychain,
    check_answer,
    correct_answer,
    correct_check_answer,
    draw_answer,
    fake_cutter,
    views_answer,
)

_real_build = app.build_services


_failing = {"left": int(os.environ.get("CLOSET_E2E_TAG_FAILS") or 0)}


def fake_claude(images, routes):
    time.sleep(1)   # long enough for the page to show it being described
    if _failing["left"] > 0:
        _failing["left"] -= 1
        raise TaggingError("the stand-in was told to fail: key sk-ant-api03-" + "Zz9" * 12
                           + " refused, see /home/someone/.claude/session.json")
    return TagResult(ANSWER, "fake-claude", 0.0, 0, 0, 0.0, 1, route=routes[0])


def fake_finder(photo, routes):
    time.sleep(1)   # long enough for the page to show it looking
    return [dict(b) for b in GARMENT_BOXES]


def fake_add_sorter(photos, routes):
    """What each photo chosen on Add shows, from its file name: "shoe..." is one shoe (all such photos the same one;
    "outer", "inner", "front" ... in the name is its side, "pair" that it shows the pair), "several..." or "pile..."
    several pieces, anything else one piece."""
    out = []
    for p in photos:
        name = p.info.get("filename", "").lower()
        if name.startswith("shoe"):   # "shoe-outer...", "shoe-front...", "shoe-pair...": the side, or the pair
            view = next((v for v in ("outer", "inner", "front", "top", "back") if v in name), "other")
            out.append({"kind": "shoe", "shoe": 1, "view": view, "pair": "pair" in name})
        else:
            kind = "pieces" if name.startswith(("several", "pile")) else "piece"
            out.append({"kind": kind, "shoe": 0, "view": None, "pair": False})
    return out


fake_add_sorter.needs_route = False   # answers on a computer with no route to Claude too (the CI)


def fake_sorter(photos, routes):
    time.sleep(1)   # long enough for the page to show it sorting
    return views_answer(len(photos))


def fake_asker(text, images, routes, answer_model=None, model="", **kw):
    """Claude's answers to the drawing and its check, after a second each: the dress shoe, said to be good, straight
    on or turned; to the judge: the first, with no fault named; and to a correction and its check: the dress shoe with
    black laces, said to go against the photos, and good."""
    time.sleep(1)   # long enough for the page to show it drawing
    if answer_model is shoedrawing.Verdict:
        answer = shoedrawing.Verdict(observations="The panels as the photos show them.", best="a",
                                     ranking=["a", "b"], faults=["A: none", "B: none"])
    else:
        answer = {shoedrawing.DrawAnswer: draw_answer, shoedrawing.TurnedDrawAnswer: draw_answer,
                  shoedrawing.CorrectAnswer: correct_answer, shoedrawing.TurnedCorrectAnswer: correct_answer,
                  shoedrawing.CorrectCheckAnswer: correct_check_answer,
                  shoedrawing.TurnedCorrectCheckAnswer: correct_check_answer}.get(answer_model, check_answer)()
        if answer_model in TURNED:   # the same answer in the turned form (the same fields): the dress shoe as drawn,
            answer = answer_model.model_validate(answer.model_dump())   # which passes the turned view's checks
    return CorrectionResult(answer, routes[0], model, 42_000, 6_500, 12_000)


TURNED = {shoedrawing.TurnedDrawAnswer, shoedrawing.TurnedCheckAnswer, shoedrawing.TurnedCorrectAnswer,
          shoedrawing.TurnedCorrectCheckAnswer}


def fake_drawer(photos, routes, notes=(), style=None):
    return shoedrawing.draw(photos, routes, asker=fake_asker, notes=notes, style=style)


def fake_drawing_corrector(photos, kept, note, routes):
    return shoedrawing.correct(photos, kept, note, routes, asker=fake_asker)


def api_only_status(order="auto", claude_exe=None):
    routes = {"plan": {"id": "plan", "available": False, "detail": "Claude Code is not installed on this computer."},
              "api": {"id": "api", "available": True, "detail": ""}}
    return {"order": list(tagger_routes.ORDERS[order]), "routes": [routes[r] for r in tagger_routes.ORDERS[order]]}


def _found(**kw) -> Found:
    base = dict(shop="Example Shop", image_url="", currency="USD", formality="smart_casual", season="all",
                pattern="solid", weight_class="midweight", rain_proof=False, material="")
    return Found(**{**base, **kw})


class FakeShop:
    """Stands in for Claude searching shops and looking up prices; never reaches the web."""

    def find(self, wish, routes):
        time.sleep(1)   # long enough for the page to show it searching
        return ShopAnswer(note="", finds=[
            _found(name="Tan gabardine rain coat", url="https://shop.example/tan-coat", price=180.0, category="coat",
                   color="tan", rain_proof=True, material="cotton gabardine"),
            _found(name="Navy pique polo", shop="Other Shop", url="https://other.example/polo", price=45.0,
                   category="polo", color="navy", season="warm"),
            _found(name="Not a real link", url="javascript:alert(1)", price=10.0, category="tee", color="white")])

    def prices(self, finds, routes):
        time.sleep(1)
        return PriceAnswer(prices=[PriceSeen(url=f["url"], price=round((f["price"] or 100) * 0.8, 2),
                                             currency=f["currency"], available=True) for f in finds])


def seed_from_demo(cfg):
    """The owner's own closet starts as a copy of the demo closet (only when it does not exist yet)."""
    main = cfg.db_path("main")
    if main.exists():
        return
    demo.ensure(cfg)
    src, dst = sqlite3.connect(cfg.db_path("demo")), sqlite3.connect(main)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()
    if cfg.images_dir("demo").exists():
        shutil.copytree(cfg.images_dir("demo"), cfg.images_dir("main"), dirs_exist_ok=True)


def no_weather_service(url):
    """The browser tests never reach the weather service. One place is stood in for, so a day somewhere else can be
    tried: Lisbon is on the map, and its forecast is a mild, windy day with rain, the same in every hour (so the
    words on Today do not depend on the hour the test runs at). Everything else is out of reach, as before."""
    from datetime import UTC, datetime
    from urllib.parse import parse_qs, urlsplit
    parts = urlsplit(url)
    params = {k: v[0] for k, v in parse_qs(parts.query).items()}
    if parts.netloc == "geocoding-api.open-meteo.com" and params.get("name", "").lower().startswith("lisbon"):
        return json.dumps({"results": [{"name": "Lisbon", "latitude": 38.71667, "longitude": -9.13333,
                                        "timezone": "Europe/Lisbon", "country": "Portugal"}]}).encode()
    if parts.netloc == "api.open-meteo.com" and params.get("latitude", "").startswith("38.7") and "hourly" in params:
        day = datetime.now(UTC).date().isoformat()
        every = {"temperature_2m": 17.0, "apparent_temperature": 13.0, "precipitation_probability": 70,
                 "precipitation": 1.5, "wind_speed_10m": 38.0, "wind_gusts_10m": 50.0, "relative_humidity_2m": 60,
                 "uv_index": 2.0, "weather_code": 61}
        return json.dumps({"utc_offset_seconds": 0, "daily": {
            "time": [day], "temperature_2m_min": [14.0], "temperature_2m_max": [18.0],
            "precipitation_probability_max": [70], "weather_code": [61]},
            "hourly": {"time": [f"{day}T{h:02d}:00" for h in range(24)], **{k: [v] * 24 for k, v in every.items()}}}).encode()
    raise urllib.error.URLError("the browser tests never reach the weather service")


def fake_day_reader(text, today, home, routes):
    """Stands in for Claude reading the day in the owner's words, from words in the sentence itself: "Lisbon" is a
    place, "four days" four days, "outside" noon to six, "wedding" a formal day; anything else says nothing."""
    words = text.lower()
    return {"place": "Lisbon, Portugal" if "lisbon" in words else None, "starts_in_days": 0,
            "days": 4 if "four days" in words else 1, "outside": (12, 18) if "outside" in words else None,
            "exposure": "outside" if "outside" in words else "mixed",
            "activity": "a wedding" if "wedding" in words else "walking the city" if "walking" in words else "",
            "occasion": "formal" if "wedding" in words else None}


fake_day_reader.needs_route = False   # as fake_add_sorter


def build_services(cfg, **kwargs):
    # sorting the photos on Add never reaches Claude from a browser test, with or without the other stand-ins
    kwargs.setdefault("add_sorter", fake_add_sorter)
    kwargs.setdefault("day_reader", fake_day_reader)   # nor does reading the day in the owner's words
    if not os.environ.get("CLOSET_E2E_FAKES"):
        return _real_build(cfg, **kwargs)
    if os.environ.get("CLOSET_E2E_SEED") == "demo":
        seed_from_demo(cfg)
    kwargs.setdefault("shop_asker", FakeShop())
    kwargs.setdefault("tracer", tracejobs.tracer())   # shoes are traced with GrabCut alone, as without the model
    apikey.use_store(MemoryKeychain())
    apikey.check = lambda key: "refused" if key.endswith("refused") else None
    if os.environ.get("CLOSET_E2E_ROUTES") == "api":
        tagger_routes.status = api_only_status
        sv = _real_build(cfg, cutter=fake_cutter, api_client=FakeApi(input_tokens=20_000, output_tokens=12_000), **kwargs)
    else:
        reader = FakeClaude()
        reader.mode = "answers"
        sv = _real_build(cfg, cutter=fake_cutter, tagger=fake_claude, routes=lambda: ("plan",), corrector=reader.correct,
                         finder=fake_finder, sorter=fake_sorter, drawer=fake_drawer,
                         drawing_corrector=fake_drawing_corrector, **kwargs)
    sv.worker.is_ready = lambda: True
    return sv


if __name__ == "__main__":
    weather.fetch = no_weather_service
    app.build_services = build_services
    sys.exit(cli.main(sys.argv[1:]))
