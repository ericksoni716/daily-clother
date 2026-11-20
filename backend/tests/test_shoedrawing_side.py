"""A shoe drawn by Claude from its side (`closet/drawing/drawnside.py` and `shoedrawing.draw_side`): the frame made
safe, the automatic checks, the measures read from a trace, the card and the check picture; the prompts; one draw call
then at most two checks, stopping as soon as one says good, a failed check keeping the drawing so far. The side drawn
with the whole drawing, beside the turns, is tested in test_shoedrawing_turned.py. Claude is never called.
"""
import io

import pytest
from PIL import Image

from closet.drawing import drawn, drawnside
from closet.drawing.drawnside import Measures
from closet.drawing.traced import LENGTH, Profile
from closet.tagger import shoedrawing as SD
from closet.tagger.shoedrawing import SideAnswer, SideCheckAnswer
from closet.tagger.tagging import RouteUnavailable, TaggingError

from .conftest import SHEET, SIDE_FEATURES, SIDE_MEASURES, SIDE_SVG, FakeApi, side_answer, side_check_answer
from .test_shoedrawing import Asker, clock, photos

MEASURED = Measures(**SIDE_MEASURES)
LOW = f'<g transform="translate(0 99) scale(1 0.7)">{SIDE_SVG}</g>'   # a third lower, on the ground
TURNED = f'<g transform="translate(400 0) scale(-1 1)">{SIDE_SVG}</g>'                # the toe pointing right


# ------------------------------------------------------------------ made safe

def test_the_side_is_made_safe_and_its_svg_wrapper_taken_off():
    wrapped = (f'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 460">{SIDE_SVG}'
               '<script>alert(1)</script><text x="1" y="2">AIR</text><path id="x" d="M0,0 L1,1" style="fill:red"/></svg>')
    out = drawnside.sanitise(wrapped)
    assert out.startswith("<path") and "script" not in out and "text" not in out and "AIR" not in out
    assert 'id="' not in out and "style" not in out and out.count("<path") == 4
    with pytest.raises(drawn.DrawingError):
        drawnside.sanitise('<svg><image href="x.png"/></svg>')   # nothing drawable left


# ------------------------------------------------------------------ checked

def test_a_good_side_passes_every_check_and_the_measured_ones():
    svg = drawnside.sanitise(SIDE_SVG)
    m = drawnside.measure(svg)
    assert m["box"] == pytest.approx((38, 212, 362, 332), abs=1)
    assert drawnside.checks(svg) == [] and drawnside.checks(svg, MEASURED) == []


def test_the_checks_say_what_is_wrong_in_plain_words():
    lifted = drawnside.checks(f'<g transform="translate(0 -40)">{SIDE_SVG}</g>')
    assert any("does not stand on the ground line" in p for p in lifted)
    short = drawnside.checks(f'<g transform="translate(120 0) scale(0.6 1)">{SIDE_SVG}</g>')
    assert any("toe tip belongs at x 40" in p for p in short)
    assert any("runs off the card" in p for p in drawnside.checks(f'<g transform="translate(80 0)">{SIDE_SVG}</g>'))
    assert any("toe seems to point right" in p for p in drawnside.checks(TURNED))
    tall = drawnside.checks('<path d="M40,330 L360,330 L360,40 L300,40 L300,300 L40,300 Z" fill="#ffffff"/>')
    assert any("too tall for the card" in p for p in tall)
    assert drawnside.checks('<path d="M0,0" fill="#ffffff"/>') == ["Nothing of it is painted on the card."]


def test_measured_from_the_trace_a_flat_drawing_is_told_to_stand_taller():
    assert drawnside.checks(LOW) == []   # by itself nothing is wrong with it
    found = drawnside.checks(LOW, MEASURED)
    assert any(p.startswith("It is too low for its length") and "measured from the photo it is 0.35" in p for p in found)
    assert any(p.startswith("The toe box is too low and pointed") for p in found)
    # within the slack (15%) nothing is said; a drawing too tall is told so too
    assert drawnside.checks(SIDE_SVG, Measures(**{**SIDE_MEASURES, "heel": 0.32, "toe_box": 0.19})) == []
    assert any("too tall for its length" in p
               for p in drawnside.checks(SIDE_SVG, Measures(**{**SIDE_MEASURES, "heel": 0.25})))


def test_measures_are_read_from_a_trace_profile_as_shares_of_the_length():
    u = [i / 40 for i in range(41)]
    top = [round(LENGTH * (0.34 if x <= 0.12 else 0.3 if x <= 0.5 else 0.3 - 0.15 * (x - 0.5) / 0.5), 3) for x in u]
    m = drawnside.measures(Profile(u, top, [0.0] * 41, [LENGTH * 0.08] * 41))
    assert m.heel == pytest.approx(0.34) and m.collar_dip == pytest.approx(0.3) and m.tallest == pytest.approx(0.34)
    assert m.toe_box == pytest.approx(0.3 - 0.15 * 0.35 / 0.5, abs=0.01) and m.sole_heel == pytest.approx(0.08)
    assert Measures.from_json(m.to_json()) == Measures(**m.to_json())
    assert drawnside.measures(Profile([0, 1], [1, 1], [0, 0], [0, 0])) is None   # too few points
    assert Measures.from_json({"heel": "tall"}) is None and Measures.from_json(None) is None
    text = drawnside.measures_text(MEASURED)
    assert "the top at the heel: 0.35 of the length, at about y 218" in text and "about 29 units thick" in text


# ------------------------------------------------------------------ shown

def test_the_card_and_the_check_picture():
    card = drawnside.card_svg(SIDE_SVG)
    assert card.startswith('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 460"')
    assert '<rect width="400" height="460" rx="18" fill="#f1eee8"/>' in card and drawnside.sanitise(SIDE_SVG) in card
    with Image.open(io.BytesIO(drawnside.check_png(SIDE_SVG))) as im:
        assert im.size == (drawnside.BIG_W + drawnside.GAP + drawnside.SMALL_W, 644)
    styles = drawnside.style_svgs()
    assert set(styles) == {"sneaker", "boot"} and all(s.startswith("<svg") for s in styles.values())


# ------------------------------------------------------------------ the prompts

def test_the_side_prompt_names_the_photos_the_front_sheet_the_style_examples_and_the_measures():
    text = SD.side_prompt(photos(), SHEET, ["the laces should be black"], MEASURED)
    assert "- Photo 1 (photo-1.jpg): the outer side, or possibly the inner side (not sure which)." in text
    assert "The side photos matter most, the outer side above all" in text
    assert '"archetype": "cap-toe oxford"' in text and '"palette"' in text and "opening_front_y" not in text
    assert "style-sneaker.png and style-boot.png" in text and "STYLE only" in text
    assert '- "the laces should be black"' in text
    assert "## Measured from your photo" in text and "at about y 218" in text
    for words in ("toe pointing LEFT", "y = 330", "x = 40", "x = 360", "No lettering", "proportions",
                  "stroke #26231f, stroke-width 3.8", "stroke-width 1.5", "particular to THIS shoe", "120 pixels"):
        assert words in text, words
    bare = SD.side_prompt(photos(1))
    assert "Measured from your photo" not in bare and "The drawing you made of it from the front" not in bare
    check = SD.side_check_prompt(photos(), {"kind": "court", "features": SIDE_FEATURES}, SIDE_SVG,
                                 ["It does not stand on the ground line."], measures=MEASURED)
    assert "drawing.png" in check and SIDE_SVG in check and "- It does not stand on the ground line." in check
    assert "Measured from the photo's outline" in check and "white leather upper with a plain toe" in check


# ------------------------------------------------------------------ the calls

def test_a_side_then_a_check_that_says_good():
    asker = Asker(side_answer(), side_check_answer())
    made = SD.draw_side(photos(), ("plan", "api"), asker=asker, clock=clock(), sheet=SHEET,
                        measures=SIDE_MEASURES)
    assert [c["answer_model"] for c in asker.calls] == [SideAnswer, SideCheckAnswer]
    first, second = asker.calls
    assert first["names"] == [f"photo-{n}.jpg" for n in range(1, 6)] + SD.SIDE_STYLE_NAMES
    assert len(first["images"]) == 7 and second["names"][-1] == "drawing.png" and len(second["images"]) == 6
    assert "Measured from your photo" in first["text"]
    assert all(c["model"] == SD.MODEL and c["effort"] == SD.EFFORT and c["system"] == SD.SYSTEM
               and c["routes"] == ("plan", "api") and c["cache_photos"] == 5 for c in asker.calls)
    assert made.svg == drawnside.sanitise(SIDE_SVG) and made.features == SIDE_FEATURES and made.measured
    assert made.rounds == 1 and made.good and made.problems == [] and made.proportions["heel"] == 0.35
    assert [c.kind for c in made.calls] == ["side", "side-check"] and made.route == "plan"
    kept = made.to_json("2026-11-20T10:00:00Z")
    assert kept["svg"] == made.svg and kept["features"] == SIDE_FEATURES and kept["cost_usd"] > 0
    assert kept["input_tokens"] == 60_000 and kept["made_at"] == "2026-11-20T10:00:00Z"


def test_a_measured_fault_goes_to_the_check_and_its_fix_is_kept():
    asker = Asker(side_answer(LOW), side_check_answer(good=False), side_check_answer())
    made = SD.draw_side(photos(), ("plan",), asker=asker, clock=clock(), measures=SIDE_MEASURES)
    assert "It is too low for its length" in asker.calls[1]["text"]
    assert made.rounds == 2 and made.good and made.svg == drawnside.sanitise(SIDE_SVG)


def test_the_checks_stop_after_two_rounds_and_a_failed_check_keeps_the_drawing():
    asker = Asker(side_answer(), side_check_answer(good=False), side_check_answer(good=False))
    made = SD.draw_side(photos(), ("plan",), asker=asker, clock=clock())
    assert len(asker.calls) == 1 + SD.MAX_SIDE_ROUNDS and made.rounds == 2 and not made.good
    asker = Asker(side_answer(LOW), TaggingError("no usable answer"))
    made = SD.draw_side(photos(), ("plan",), asker=asker, clock=clock(), measures=SIDE_MEASURES)
    assert made.rounds == 0 and made.svg == drawnside.sanitise(LOW) and made.problems   # what is still wrong is kept


def test_a_fix_that_cannot_be_used_is_set_aside():
    asker = Asker(side_answer(), side_check_answer(good=False, svg="<text>no</text>"), side_check_answer())
    made = SD.draw_side(photos(), ("plan",), asker=asker, clock=clock())
    assert "could not be used" in asker.calls[2]["text"] and made.good and made.svg == drawnside.sanitise(SIDE_SVG)


def test_a_side_raises_as_a_drawing_does():
    with pytest.raises(RouteUnavailable):
        SD.draw_side(photos(), ("plan",), asker=Asker(RouteUnavailable("not signed in")), clock=clock())
    with pytest.raises(drawn.DrawingError):
        SD.draw_side(photos(), ("plan",), asker=Asker(side_answer("<text>shoe</text>")), clock=clock())


def test_features_are_kept_short_and_plain():
    assert SD._features(["  a   white\nshoe ", "", "x" * 300]) == ["a white shoe", "x" * 119 + "…"]
    assert len(SD._features([f"f{i}" for i in range(10)])) == SD.FEATURES_MAX


# ------------------------------------------------------------------ a side check that says good stops being read there

def test_a_side_check_that_says_good_stops_being_read_before_the_drawing(cut_clock):
    api = FakeApi(input_tokens=25_000, output_tokens=7_000)
    made = SD.draw_side(photos(), ("api",), client=api)
    draw, look = api.streams
    assert draw["whole"] and not look["whole"]
    assert '"good": true' in look["text"] and '"svg"' in look["text"] and "<path" not in look["text"]
    assert made.good and made.rounds == 1 and made.svg == drawnside.sanitise(SIDE_SVG)
    assert [c.cut_short for c in made.calls] == [False, True]


def test_a_side_check_given_a_measured_fault_is_read_whole():
    api = FakeApi()
    api.side = side_answer(LOW)
    made = SD.draw_side(photos(), ("api",), client=api, measures=SIDE_MEASURES)
    assert [s["whole"] for s in api.streams] == [True, True, False]   # the fix is used; its check finds nothing
    assert made.good and made.rounds == 2 and made.svg == drawnside.sanitise(SIDE_SVG)


def test_the_side_hook_cuts_only_a_good_answer():
    cut = SD._side_good_as_is(drawnside.sanitise(SIDE_SVG))
    assert cut.at == "svg"
    kept = cut.answer({"good": True, "problems": [], "features": SIDE_FEATURES})
    assert kept.svg == drawnside.sanitise(SIDE_SVG) and kept.features == SIDE_FEATURES
    assert cut.answer({"good": False, "problems": ["The toe."], "features": SIDE_FEATURES}) is None
    assert cut.answer({"good": True, "problems": []}) is None
