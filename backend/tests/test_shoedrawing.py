"""A shoe drawn by Claude from its photos (`closet/tagger/shoedrawing.py`): the prompts, the strict answers, and the
calls of one straight-on drawing (`draw_straight`, each candidate of `draw`): a drawing, then checks against the photos
that stop as soon as one says good, at most three; every drawing made safe before it is rendered, checked or kept; what
the automatic checks find fed into the next check. The whole drawing (candidates, the judge, the turn, the fix) is
tested in test_shoedrawing_turned.py. Both routes are
stood in for (`conftest.FakeApi`, and a stand-in for `subprocess.run`); Claude is never called.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from closet import spend
from closet.drawing import drawn
from closet.tagger import correcting
from closet.tagger import shoedrawing as SD
from closet.tagger.correcting import CorrectionResult
from closet.tagger.shoedrawing import CheckAnswer, DrawAnswer, Photo
from closet.tagger.tagging import CONFIG, RouteUnavailable, TaggingError

from .conftest import SHEET, FakeApi, check_answer, draw_answer

DRESS = drawn.example("dress-shoe")
LIFTED = f'<g transform="translate(0 -20)">{DRESS}</g>'   # the dress shoe floating above the ground
VIEWS = (("outer", False), ("top", True), ("inner", False), ("front", True), ("back", True))


def photos(n=5) -> list[Photo]:
    return [Photo(Image.new("RGB", (900, 700), (40 * i, 90, 120)), v, s) for i, (v, s) in enumerate(VIEWS[:n])]


def shoe(front: str, behind: str = "") -> dict:
    return {"behind": behind, "front": front}


def drew(left: str, right: str | None = None) -> DrawAnswer:
    return DrawAnswer.model_validate({"sheet": SHEET, "left": shoe(left), "right": shoe(right) if right else None})


def checked(left=DRESS, good=True, sheet=None, right=None) -> CheckAnswer:
    return CheckAnswer.model_validate({"good": good, "problems": [] if good else ["fixed"], "sheet": sheet or SHEET,
                                       "left": shoe(left), "right": shoe(right) if right else None})


class Asker:
    """Stands in for `correcting.ask`: answers `replies` in turn (an answer, or an exception to raise) and keeps what
    each call was given."""

    def __init__(self, *replies, route="plan", tokens=(30_000, 5_000), cached=0):
        self.replies, self.route, self.tokens, self.cached = list(replies), route, tokens, cached
        self.calls: list[dict] = []

    def __call__(self, text, images, routes, **kw):
        self.calls.append({"text": text, "images": images, "routes": routes, **kw})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return CorrectionResult(reply, self.route, kw["model"], self.tokens[0], self.tokens[1], self.cached)


def clock():
    t = {"now": 0.0}

    def tick():
        t["now"] += 10.0
        return t["now"]
    return tick


# ------------------------------------------------------------------ the prompts

def test_the_draw_prompt_carries_the_examples_the_views_and_the_brief():
    text = SD.draw_prompt(photos())
    for name in drawn.EXAMPLES:
        assert SD._example_text(name) in text and f"example-{name}.png" in text
    assert 'id="' not in text   # the examples' ids are not shown
    assert "- Photo 1 (photo-1.jpg): the outer side, or possibly the inner side (not sure which)." in text
    assert "- Photo 2 (photo-2.jpg): from above." in text
    assert "- Photo 4 (photo-4.jpg): the front (toe towards the camera)." in text
    assert "most specific kind of shoe" in text and "STYLE and the CONSTRUCTION" in text
    for words in ("ground is y = 240", "x 62 to 138", "y = 40 to 60", "y = 75 to 90", "about 145 wide",
                  "y = -30 to -50", "chukka's at about y = 0", "below y = -90", "stroke #26221f, stroke-width 4",
                  "stroke-width 1.6", "No lettering", "leg goes INTO the shoe", "a boot is NOT a tube",
                  "no thicker", "toes out", "nearer x = 200", "opening_front_y"):
        assert words in text, words
    assert "photo-6" not in SD.draw_prompt(photos(5))


def test_a_view_is_named_plainly_and_an_unsure_one_as_unsure():
    assert SD.view_words("outer", True) == "the outer side"
    assert SD.view_words("inner", False) == "the inner side, or possibly the outer side (not sure which)"
    assert SD.view_words("top", False) == "probably from above (not sure)"
    assert SD.view_words(None, None) == "a view that is not known"
    assert SD.view_words("other", True) == "a detail or another view"


def test_the_check_prompt_carries_the_drawing_the_sheet_and_the_problems():
    text = SD.check_prompt(photos(), SHEET, drawn.Side(DRESS), None, ["It does not stand on the ground."])
    assert "PHOTOS" in text and "drawing.png" in text and DRESS in text and '"archetype": "cap-toe oxford"' in text
    assert "- It does not stand on the ground." in text and "null (the app mirrors" in text
    assert "- Photo 3 (photo-3.jpg): the inner side" in text and "ground is y = 240" in text
    assert "- none" in SD.check_prompt(photos(), SHEET, drawn.Side(DRESS), drawn.Side("<path d='M0,0'/>"), [])


def test_the_answers_are_strict():
    drew(DRESS)
    for bad in ({**SHEET, "palette": SHEET["palette"][:1]}, {**SHEET, "signature": ["a"] * 5},
                {**SHEET, "palette": [{**SHEET["palette"][0], "hex": "tan"}] * 2},
                {**SHEET, "silhouette": {**SHEET["silhouette"], "height": "mid"}}, {**SHEET, "extra": 1},
                {**SHEET, "opening_front_y": "40"}, {**SHEET, "opening_front_y": 400}):
        with pytest.raises(ValueError):
            DrawAnswer.model_validate({"sheet": bad, "left": shoe(DRESS), "right": None})
    with pytest.raises(ValueError):
        CheckAnswer.model_validate({"good": "yes", "problems": [], "sheet": SHEET, "left": shoe(DRESS), "right": None})
    assert SD.MODEL == CONFIG["roles"]["drawing"] and SD.EFFORT == "medium"


# ------------------------------------------------------------------ the calls

def test_a_drawing_then_a_check_that_says_good():
    asker = Asker(draw_answer(), check_answer())
    made = SD.draw_straight(photos(), ("plan", "api"), asker=asker, clock=clock())
    assert [c["answer_model"] for c in asker.calls] == [DrawAnswer, CheckAnswer]
    first, second = asker.calls
    assert first["names"] == [f"photo-{n}.jpg" for n in range(1, 6)] + [f"example-{n}.png" for n in drawn.EXAMPLES]
    assert len(first["images"]) == 8 and max(first["images"][0].size) == 900   # photos at most 1024 px a side
    assert second["names"][-1] == "drawing.png" and len(second["images"]) == 6
    assert all(c["model"] == SD.MODEL and c["effort"] == SD.EFFORT and c["max_tokens"] == SD.MAX_TOKENS
               and c["timeout"] == SD.TIMEOUT and c["system"] == SD.SYSTEM and c["routes"] == ("plan", "api")
               for c in asker.calls)
    assert made.rounds == 1 and made.good and made.problems == []
    assert made.left == drawn.Side(drawn.sanitise(DRESS)) and made.right is None and made.sheet == SHEET
    assert [c.kind for c in made.calls] == ["draw", "check"] and made.route == "plan"
    assert made.seconds > 0 and all(c.seconds > 0 for c in made.calls)


def test_the_checks_stop_after_three_rounds():
    asker = Asker(draw_answer(), checked(good=False), checked(good=False), checked(good=False))
    made = SD.draw_straight(photos(), ("plan",), asker=asker, clock=clock())
    assert len(asker.calls) == 1 + SD.MAX_ROUNDS == 4 and made.rounds == 3 and not made.good


def test_every_drawing_is_made_safe_before_it_is_rendered_checked_or_kept(monkeypatch):
    nasty = DRESS + '<script>alert(1)</script><text>N</text><path id="x" d="M0,0" onclick="x()" fill="url(#g)"/>'
    seen = []
    real = drawn.check_png
    monkeypatch.setattr(drawn, "check_png", lambda left, right=None, view=drawn.FRONT: seen.append(left) or real(left, right, view))
    asker = Asker(drew(nasty), checked(left=nasty, good=False), check_answer())
    made = SD.draw_straight(photos(), ("plan",), asker=asker, clock=clock())
    for text in [made.left.front, *(drawn.side(s).front for s in seen), asker.calls[1]["text"]]:
        for bit in ("<script", "alert(1)", "<text>N", 'id="x"', "url(#g)", "onclick"):
            assert bit not in text
    assert made.left.front in asker.calls[2]["text"]
    assert made.rounds == 2 and made.good   # the first check's answer changed the drawing (made safe), the second said good


def test_what_the_automatic_checks_find_goes_into_the_next_check():
    asker = Asker(drew(LIFTED), checked(left=LIFTED, good=True),   # says good, but the shoe still floats: not accepted
                  checked(left=DRESS, good=False), check_answer())
    made = SD.draw_straight(photos(), ("plan",), asker=asker, clock=clock())
    texts = [c["text"] for c in asker.calls[1:]]
    assert "does not stand on the ground" in texts[0] and "does not stand on the ground" in texts[1]
    assert "## What the automatic checks found (each must be fixed)\n- none" in texts[2]
    assert made.rounds == 3 and made.good and made.problems == [] and made.left == drawn.Side(drawn.sanitise(DRESS))


def test_a_fix_that_cannot_be_used_keeps_the_drawing_before_it():
    asker = Asker(draw_answer(), checked(left="<text>no shapes</text>", good=False), check_answer())
    made = SD.draw_straight(photos(), ("plan",), asker=asker, clock=clock())
    assert "could not be used (Nothing drawable" in asker.calls[2]["text"]
    assert drawn.sanitise(DRESS) in asker.calls[2]["text"]
    assert made.left == drawn.Side(drawn.sanitise(DRESS)) and made.rounds == 2 and made.good


def test_a_check_that_fails_keeps_the_drawing_made_so_far():
    for error in (RouteUnavailable("Claude Code is not signed in"), TaggingError("no usable answer")):
        made = SD.draw_straight(photos(), ("plan",), asker=Asker(draw_answer(), error), clock=clock())
        assert made.rounds == 0 and not made.good and made.left == drawn.Side(drawn.sanitise(DRESS)) and len(made.calls) == 1


def test_a_drawing_that_fails_raises():
    with pytest.raises(RouteUnavailable):
        SD.draw_straight(photos(), ("plan",), asker=Asker(RouteUnavailable("no route")), clock=clock())
    with pytest.raises(drawn.DrawingError):
        SD.draw_straight(photos(), ("plan",), clock=clock(), asker=Asker(drew("<text/>")))


def test_the_cost_is_what_the_api_key_would_charge_without_the_plans_rereading():
    made = SD.draw_straight(photos(), ("plan",), asker=Asker(draw_answer(), check_answer(), tokens=(50_000, 6_000),
                                                    cached=20_000), clock=clock())
    one = spend.cost_usd(SD.MODEL, 30_000, 6_000)
    assert [c.cost_usd for c in made.calls] == [pytest.approx(one)] * 2
    got = made.to_json(["p1", "p2"], "2026-11-15T12:00:00+00:00")
    assert got["cost_usd"] == pytest.approx(2 * one) and got["input_tokens"] == 100_000
    assert got["cache_read_tokens"] == 40_000 and got["output_tokens"] == 12_000 and got["route"] == "plan"
    assert got["calls"][0]["kind"] == "draw" and got["photo_ids"] == ["p1", "p2"] and got["version"] == 3
    assert got["view"] == "front" and got["style"] is None and got["straight"] is None   # one drawing, straight on
    assert got["left"] == {"behind": "", "front": drawn.sanitise(DRESS)} and got["right"] is None
    assert set(got) >= {"left", "right", "sheet", "rounds", "seconds", "calls", "input_tokens", "output_tokens",
                        "cost_usd", "route", "made_at", "photo_ids", "version"}
    assert json.loads(json.dumps(got)) == got


# ------------------------------------------------------------------ through each route

class Meter:
    def __init__(self):
        self.checked, self.recorded = [], []

    def before_api_call(self, model, images):
        self.checked.append((model, images))

    def record(self, route, model, input_tokens, output_tokens):
        self.recorded.append((route, model, input_tokens, output_tokens))

    def api_refused(self, reason):
        pass


def test_through_the_api_key_the_calls_are_streamed_and_counted():
    api, meter = FakeApi(input_tokens=25_000, output_tokens=7_000), Meter()
    made = SD.draw_straight(photos(), ("api",), client=api, meter=meter)
    assert api.calls == 2 and made.rounds == 1 and made.good and made.route == "api"
    first = api.requests[0]
    assert first["model"] == SD.MODEL and first["max_tokens"] == SD.MAX_TOKENS > correcting.NONSTREAMING_MAX_TOKENS
    assert first["output_config"]["effort"] == "medium" and first["output_config"]["format"]["type"] == "json_schema"
    content = first["messages"][0]["content"]
    assert [c["text"] for c in content if c["type"] == "text"][:6] == [
        "photo-1.jpg:", "photo-2.jpg:", "photo-3.jpg:", "photo-4.jpg:", "photo-5.jpg:", "example-trainer.png:"]
    images = [c for c in content if c["type"] == "image"]
    assert [i["source"]["media_type"] for i in images] == ["image/jpeg"] * 5 + ["image/png"] * 3
    assert api.requests[1]["messages"][0]["content"][-2]["source"]["media_type"] == "image/png"   # drawing.png
    assert meter.checked == [(SD.MODEL, 8), (SD.MODEL, 6)]
    assert meter.recorded == [("api", SD.MODEL, 25_000, 7_000)] * 2
    assert made.totals()["cost_usd"] == pytest.approx(2 * spend.cost_usd(SD.MODEL, 25_000, 7_000))


def test_through_the_api_key_the_photos_are_cached_and_the_cache_counted():
    """Every call for a shoe starts with its photos: the request is cached up to the last of them, and what the cache
    wrote and read is passed on to the meter and priced at its own rate."""
    class CacheMeter(Meter):
        def record(self, route, model, input_tokens, output_tokens, **cached):
            self.recorded.append((route, model, input_tokens, output_tokens, cached))

    api, meter = FakeApi(input_tokens=5_000, output_tokens=7_000), CacheMeter()
    api.cache_write, api.cache_read = 3_000, 20_000
    made = SD.draw_straight(photos(), ("api",), client=api, meter=meter)
    for request in api.requests:
        content = request["messages"][0]["content"]
        marked = [i for i, block in enumerate(content) if "cache_control" in block]
        assert marked == [9] and content[8]["text"] == "photo-5.jpg:" and content[9]["type"] == "image"
    assert meter.recorded == [("api", SD.MODEL, 5_000, 7_000, {"cache_write": 3_000, "cache_read": 20_000})] * 2
    call = made.calls[0]
    assert (call.input_tokens, call.cache_write_tokens, call.cache_read_tokens) == (28_000, 3_000, 20_000)
    assert call.cost_usd == pytest.approx(spend.cost_usd(SD.MODEL, 5_000, 7_000, 3_000, 20_000))
    assert spend.cost_usd(SD.MODEL, 0, 0, 1_000_000, 0) == pytest.approx(5.00)   # a write: 1.25 times input
    assert spend.cost_usd(SD.MODEL, 0, 0, 0, 1_000_000) == pytest.approx(0.20)   # a read: the table's cache price
    # nothing to cache (another question with no photos named as shared): no marker, and the meter is told as before
    plain = FakeApi()
    correcting.correct_api(plain, SD.MODEL, "x", [], meter=Meter())
    assert not any("cache_control" in b for b in plain.requests[0]["messages"][0]["content"])


def test_through_the_plan_every_image_is_saved_under_its_name(monkeypatch):
    seen = []
    answers = iter([draw_answer(), check_answer()])

    def run(cmd, cwd=None, **kw):
        seen.append({"cmd": cmd, "input": kw["stdin"].read().decode("utf-8"), "timeout": kw["timeout"],
                     "files": {p.name: p.read_bytes()[:8] for p in Path(cwd).iterdir()}})
        out = {"structured_output": next(answers).model_dump(), "is_error": False, "result": "",
               "usage": {"input_tokens": 9_000, "cache_creation_input_tokens": 12_000, "cache_read_input_tokens": 30_000,
                         "output_tokens": 4_000}}
        return SimpleNamespace(returncode=0, stdout=json.dumps(out), stderr="")
    monkeypatch.setattr(correcting.subprocess, "run", run)
    meter = Meter()
    made = SD.draw_straight(photos(), ("plan",), exe="claude", meter=meter)
    assert made.rounds == 1 and made.good and made.route == "plan"
    draw, check = seen
    assert sorted(draw["files"]) == sorted([f"photo-{n}.jpg" for n in range(1, 6)] + [
        f"example-{n}.png" for n in drawn.EXAMPLES])
    assert draw["files"]["example-trainer.png"] == b"\x89PNG\r\n\x1a\n" and draw["files"]["photo-1.jpg"][:2] == b"\xff\xd8"
    assert "drawing.png" in check["files"] and "drawing.png" in check["input"]
    for call in seen:
        cmd = call["cmd"]
        assert cmd[cmd.index("--model") + 1] == SD.MODEL and cmd[cmd.index("--effort") + 1] == "medium"
        assert cmd[cmd.index("--system-prompt") + 1] == SD.SYSTEM and call["timeout"] == SD.TIMEOUT
    assert "photo-1.jpg, photo-2.jpg" in draw["input"] and "example-boat-shoe.png" in draw["input"]
    assert meter.recorded == [("plan", SD.MODEL, 51_000, 4_000)] * 2
    assert made.calls[0].cache_read_tokens == 30_000
    assert made.calls[0].cost_usd == pytest.approx(spend.cost_usd(SD.MODEL, 21_000, 4_000))


# ------------------------------------------------------------------ the estimate

def test_the_estimate_allows_for_the_longest_request():
    worst = '<path d="' + "M0,0 " * ((drawn.MAX_CHARS - 20) // 5) + '"/>'
    schema = json.dumps(CheckAnswer.model_json_schema())
    longest = SD.check_prompt(photos(6), SHEET, drawn.Side(worst), drawn.Side(worst), ["x" * 300] * 8)
    assert (len(longest) + len(schema) + len(SD.SYSTEM)) / 2 <= spend.DRAW_TEXT_TOKENS
    assert (len(SD.draw_prompt(photos(6))) + len(json.dumps(DrawAnswer.model_json_schema()))) / 2 * 2 <= spend.DRAW_TEXT_TOKENS
    assert spend.estimate_draw(9) - spend.estimate_draw(8) == pytest.approx(spend.cost_usd(SD.MODEL, spend.IMAGE_TOKENS, 0))
    assert spend.estimate_draw(8) >= spend.cost_usd(SD.MODEL, spend.DRAW_TEXT_TOKENS + 8 * spend.IMAGE_TOKENS, SD.MAX_TOKENS)


# ------------------------------------------------------------------ behind the leg and in front (step D)

TAB = '<path d="M88,-28 L88,-64 C88,-73 112,-73 112,-64 L112,-28 Z" fill="#4a2c22" stroke="#26221f" stroke-width="1.6"/>'


def test_claude_draws_each_shoe_behind_and_in_front_of_the_leg_and_both_are_kept():
    text = SD.draw_prompt(photos())
    assert "Behind the leg and in front of it: two parts" in text and "pull tab" in text
    assert "behind and front" in text and "the back of the opening" in text
    with pytest.raises(ValueError):   # one text for a shoe is no longer an answer
        DrawAnswer.model_validate({"sheet": SHEET, "left": DRESS, "right": None})
    collar = '<path d="M64,24 L136,24 L136,50 L64,50 Z" fill="#3a2a24"/>'   # the back of the collar, behind the leg
    first = DrawAnswer.model_validate({"sheet": SHEET, "left": shoe(DRESS, collar), "right": None})
    asker = Asker(first, checked(good=True))
    made = SD.draw_straight(photos(), ("plan",), asker=asker, clock=clock())
    assert made.left == drawn.Side(drawn.sanitise(DRESS), drawn.sanitise(collar)) and made.rounds == 1 and made.good
    check = asker.calls[1]["text"]
    assert "behind the leg:\n" + drawn.sanitise(collar) in check and "in front of the leg:\n" + drawn.sanitise(DRESS) in check
    kept = made.to_json([], "2026-11-15T12:00:00+00:00")
    assert kept["version"] == 3 and kept["left"] == {"behind": drawn.sanitise(collar), "front": drawn.sanitise(DRESS)}


def test_a_back_pull_tab_drawn_in_front_of_the_leg_goes_back_to_claude():
    tall = {**SHEET, "silhouette": {**SHEET["silhouette"], "height": "ankle"}}
    asker = Asker(DrawAnswer.model_validate({"sheet": tall, "left": shoe(DRESS + TAB), "right": None}),
                  CheckAnswer.model_validate({"good": True, "problems": [], "sheet": tall, "left": shoe(DRESS + TAB),
                                              "right": None}),
                  CheckAnswer.model_validate({"good": False, "problems": ["the tab is behind the leg"], "sheet": tall,
                                              "left": shoe(DRESS, TAB), "right": None}),
                  CheckAnswer.model_validate({"good": True, "problems": [], "sheet": tall, "left": shoe(DRESS, TAB),
                                              "right": None}))
    made = SD.draw_straight(photos(), ("plan",), asker=asker, clock=clock())
    assert "hides the leg above its opening" in asker.calls[1]["text"]   # for a boot too, found and sent back
    assert "hides the leg above its opening" in asker.calls[2]["text"]   # said good, but still found: not accepted
    assert made.good and made.problems == [] and made.left.behind == drawn.sanitise(TAB) and made.rounds == 3
