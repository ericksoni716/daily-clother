"""The whole drawing of a shoe (`closet/tagger/shoedrawing.draw`): three straight-on candidates side by side, the judge
keeping the one most faithful to the photos, two turns of it with the computed turn (`closet/drawing/turned.py`) as
the reference, the judge again, the judge's faults on the kept turn fixed and the fix kept only when the judge prefers
it; the photos cut to the shoe; a sandal kept straight on; failures keeping what was made. Claude is never called: a
stand-in answers each kind of question, from several threads at once.
"""
import threading

import numpy as np
import pytest
from PIL import Image

from closet.drawing import drawn, turned
from closet.tagger import shoedrawing as SD
from closet.tagger.correcting import CorrectionResult
from closet.tagger.shoedrawing import (
    CheckAnswer,
    CorrectAnswer,
    CorrectCheckAnswer,
    DrawAnswer,
    Photo,
    TurnedCheckAnswer,
    TurnedCorrectAnswer,
    TurnedCorrectCheckAnswer,
    TurnedDrawAnswer,
    Verdict,
)
from closet.tagger.tagging import RouteUnavailable, TaggingError

from .conftest import SHEET, black_laces

# Whole shoe drawings that take seconds a test: left out of pull requests unless their code changes (docs/DEVELOPING.md).
pytestmark = pytest.mark.slow

DRESS = drawn.example("dress-shoe")
LACES = drawn.sanitise(black_laces(DRESS))   # the dress shoe with black laces: another drawing that passes every check
LIFTED = f'<g transform="translate(0 -20)">{DRESS}</g>'   # off the ground: a measured fault
VIEWS = (("outer", True), ("front", True), ("inner", True))


def photos(n=3) -> list[Photo]:
    return [Photo(Image.new("RGB", (900, 700), (40 * i, 90, 120)), v, s) for i, (v, s) in enumerate(VIEWS[:n])]


def shoe(front: str, behind: str = "") -> dict:
    return {"behind": behind, "front": front}


def verdict(best: str, faults: dict | None = None) -> Verdict:
    letters = "abc"
    faults = faults or {}
    return Verdict.model_validate({"observations": "two panels", "best": best, "ranking": [best],
                                   "faults": [f"{x.upper()}: {faults.get(x, 'none')}" for x in letters]})


class Claude:
    """Stands in for `correcting.ask` from several threads: answers by the kind of answer asked for. Straight-on
    drawings come in turn from `straights`; each judge call takes the next of `verdicts`; `fail` maps an answer model
    to an exception it raises instead."""

    def __init__(self, straights=(DRESS, LACES, DRESS), verdicts=("b", "a", "b"), turned_svg=DRESS, fixed_svg=LACES,
                 fail=None, turned_svgs=None):
        self.straights, self.verdicts = list(straights), list(verdicts)
        self.turned_svg, self.fixed_svg, self.fail = turned_svg, fixed_svg, fail or {}
        self.turned_svgs = list(turned_svgs) if turned_svgs else None
        self.calls: list[dict] = []
        self.lock = threading.Lock()

    def __call__(self, text, images, routes, **kw):
        model = kw["answer_model"]
        with self.lock:
            self.calls.append({"text": text, "images": images, "names": kw.get("names"), "model": model})
            if model in self.fail:
                raise self.fail[model]
            if model is DrawAnswer:
                reply = DrawAnswer.model_validate({"sheet": SHEET, "left": shoe(self.straights.pop(0)), "right": None})
            elif model is CheckAnswer:
                reply = CheckAnswer.model_validate({"good": True, "problems": [], "sheet": SHEET,
                                                    "left": shoe(_left_of(text)), "right": None})
            elif model is Verdict:
                best = self.verdicts.pop(0)
                reply = best if isinstance(best, Verdict) else verdict(
                    best, {best: "a stray white bar on the inner side"} if best == "a" else None)
            elif model is TurnedDrawAnswer:
                svg = self.turned_svgs.pop(0) if self.turned_svgs else self.turned_svg
                reply = TurnedDrawAnswer.model_validate({"sheet": SHEET, "left": shoe(svg), "right": None})
            elif model is TurnedCheckAnswer:   # good, as it is
                reply = TurnedCheckAnswer.model_validate({"good": True, "problems": [], "sheet": SHEET,
                                                          "left": shoe(_left_of(text)), "right": None})
            elif model is TurnedCorrectAnswer:
                reply = TurnedCorrectAnswer.model_validate({"changed": "The stray bar is gone.", "against_photos": None,
                                                            "sheet": SHEET, "left": shoe(self.fixed_svg), "right": None})
            elif model is TurnedCorrectCheckAnswer:
                reply = TurnedCorrectCheckAnswer.model_validate({"good": True, "problems": [], "against_photos": None,
                                                                 "sheet": SHEET, "left": shoe(self.fixed_svg),
                                                                 "right": None})
            else:
                raise AssertionError(f"unexpected question: {model}")
        return CorrectionResult(reply, "plan", kw["model"], 30_000, 5_000, 0)

    def asked(self, model) -> list[dict]:
        return [c for c in self.calls if c["model"] is model]


def _left_of(text: str) -> str:
    """The left shoe's front as a check prompt shows it (the stand-in says it is good as it is)."""
    part = text.split("The left shoe, behind the leg:\n", 1)[1].split("in front of the leg:\n", 1)[1]
    return part.split("\n\nThe right shoe", 1)[0]


def clock():
    t = {"now": 0.0}
    lock = threading.Lock()

    def tick():
        with lock:
            t["now"] += 10.0
            return t["now"]
    return tick


@pytest.fixture(autouse=True)
def in_turn(monkeypatch, request):
    """The candidates and the turns made one after another, so each stand-in answer goes to a known one (they run
    side by side in the app: `test_candidates_are_made_side_by_side`)."""
    if request.node.name == "test_candidates_are_made_side_by_side":
        return

    def one_by_one(n, job):
        got, failed = [], []
        for i in range(n):
            try:
                got.append(job(i))
            except BaseException as e:
                got.append(None)
                failed.append(e)
        return got, failed
    monkeypatch.setattr(SD, "_parallel", one_by_one)


def test_candidates_are_made_side_by_side():
    meet = threading.Barrier(3, timeout=10)   # passes only when all three are under way at once
    got, failed = SD._parallel(3, lambda i: meet.wait() is not None and i)
    assert got == [0, 1, 2] and failed == []
    got, failed = SD._parallel(2, lambda i: 1 / i)
    assert got == [None, 1.0] and isinstance(failed[0], ZeroDivisionError)


def test_two_candidates_the_judge_the_turn_and_the_fix():
    claude = Claude()
    made = SD.draw(photos(), ("plan",), asker=claude, clock=clock(), style="oxford")
    assert len(claude.asked(DrawAnswer)) == SD.CANDIDATES == 2
    judged = claude.asked(Verdict)
    assert len(judged) == 3   # the candidates, the turns, the fix against the turn it fixes
    assert judged[0]["names"][-2:] == ["candidate-a.png", "candidate-b.png"]
    assert "straight.png" not in judged[0]["names"] and "straight.png" in judged[1]["names"]
    assert "seen from the front and a little above" in judged[0]["text"] and "turned out 12 degrees" in judged[1]["text"]
    # the judge kept candidate B (the black laces): it is what was turned
    assert made.straight["left"]["front"] == LACES
    turns = claude.asked(TurnedDrawAnswer)
    assert len(turns) == SD.TURNS == 2
    for t in turns:
        assert t["names"][-3:] == ["straight.png", "turned.png", "guide.png"]
        assert "turned out 12 degrees" in t["text"] and "ordinary oxford (a dress shoe)" in t["text"]
        computed = turned.turn_side(drawn.side(shoe(LACES)), "oxford", SHEET)
        assert computed.front in t["text"]   # turned.png's SVG: candidate B turned by the 3D solid
    # the judge kept turn A and named a fault: it was fixed, and the fix kept (the judge preferred it)
    fix = claude.asked(TurnedCorrectAnswer)
    assert len(fix) == 1 and "a stray white bar on the inner side" in fix[0]["text"]
    assert "x -100 to 300" in fix[0]["text"]   # with the turned view's rules
    assert made.left == drawn.side(shoe(LACES)) and made.view == "turned" and made.style == "oxford"
    kept = made.to_json(["p1"], "2026-11-17T09:00:00+00:00")
    assert kept["version"] == 3 and kept["view"] == "turned" and kept["style"] == "oxford"
    assert kept["straight"]["sheet"] == SHEET and drawn.stored(kept).view is drawn.TURNED
    kinds = [c.kind for c in made.calls]
    assert kinds.count("draw") == 2 and kinds.count("turn") == 2 and kinds.count("judge") == 3 and "correct" in kinds


def test_a_drawing_with_a_measured_fault_is_not_chosen_while_another_has_none():
    """The judge sees every turn and ranks them; the choice is its best-ranked one that the automatic checks find
    nothing wrong with, and the fix is given that one's faults."""
    ranked = Verdict.model_validate({"observations": "x", "best": "a", "ranking": ["a", "b"],
                                     "faults": ["A: none", "B: the toe is too short"]})
    claude = Claude(verdicts=("a", ranked, "b"), turned_svgs=(LIFTED, DRESS))
    made = SD.draw(photos(), ("plan",), asker=claude, clock=clock(), style="oxford")
    judged = claude.asked(Verdict)
    assert judged[1]["names"][-2:] == ["candidate-a.png", "candidate-b.png"]   # both shown
    assert len(claude.asked(TurnedCheckAnswer)) == SD.MAX_ROUNDS + 1   # the lifted turn checked three times, in vain
    fix = claude.asked(TurnedCorrectAnswer)
    assert len(fix) == 1 and "the toe is too short" in fix[0]["text"]   # turn B's fault, not A's
    assert drawn.side(shoe(DRESS)).front in fix[0]["text"]   # turn B was fixed
    assert made.left == drawn.side(shoe(LACES)) and made.problems == []
    # every turn with a measured fault: the judge's choice stands
    claude = Claude(verdicts=("a", "b"), turned_svgs=(LIFTED, LIFTED))
    made = SD.draw(photos(), ("plan",), asker=claude, clock=clock(), style="oxford")
    assert made.problems and "does not stand on the ground" in made.problems[0]


def test_a_fix_with_a_measured_fault_is_set_aside():
    claude = Claude(fixed_svg=LIFTED)
    made = SD.draw(photos(), ("plan",), asker=claude, clock=clock(), style="oxford")
    assert len(claude.asked(TurnedCorrectAnswer)) == 1 and len(claude.asked(Verdict)) == 2   # never judged
    assert made.left == drawn.side(shoe(DRESS)) and made.problems == []


def test_no_fault_named_means_no_fix():
    claude = Claude(verdicts=("a", "b"))
    made = SD.draw(photos(), ("plan",), asker=claude, clock=clock(), style="oxford")
    assert claude.asked(TurnedCorrectAnswer) == [] and len(claude.asked(Verdict)) == 2
    assert made.straight["left"]["front"] == drawn.sanitise(DRESS) and made.left == drawn.side(shoe(DRESS))


def test_a_fix_the_judge_does_not_prefer_is_set_aside():
    claude = Claude(verdicts=("b", "a", "a"))
    made = SD.draw(photos(), ("plan",), asker=claude, clock=clock(), style="oxford")
    assert len(claude.asked(TurnedCorrectAnswer)) == 1 and made.left == drawn.side(shoe(DRESS))


def test_the_style_is_read_from_the_sheet_when_the_item_does_not_say():
    assert SD.style_of(SHEET) == "oxford"
    assert SD.style_of({"kind": "German army trainer", "silhouette": {"height": "low"}}) == "low_sneaker"
    assert SD.style_of({"kind": "max-cushion running shoe", "silhouette": {"height": "low"}}) == "runner"
    assert SD.style_of({"archetype": "two-eye boat shoe", "silhouette": {"height": "low_profile"}}) == "loafer"
    assert SD.style_of({"archetype": "Chelsea boot", "silhouette": {"height": "ankle"}}) == "chelsea_boot"
    assert SD.style_of({"archetype": "mid-cut hiking boot", "silhouette": {"height": "ankle"}}) == "boot"
    assert SD.style_of({"archetype": "slide sandal", "silhouette": {"height": "low"}}) is None
    assert SD.style_of(SHEET, "runner") == "runner" and SD.style_of(SHEET, "sandal") is None
    claude = Claude(verdicts=("a", "b"))
    made = SD.draw(photos(), ("plan",), asker=claude, clock=clock())
    assert made.style == "oxford" and "ordinary oxford" in claude.asked(TurnedDrawAnswer)[0]["text"]


def test_a_sandal_is_kept_straight_on():
    claude = Claude(verdicts=("c",))
    made = SD.draw(photos(), ("plan",), asker=claude, clock=clock(), style="sandal")
    assert claude.asked(TurnedDrawAnswer) == [] and made.view == "front" and made.straight is None
    assert made.left == drawn.side(shoe(DRESS))   # candidate C


def test_a_running_shoe_is_drawn_with_its_midsole_in_mind():
    claude = Claude(verdicts=("a", "b"))
    SD.draw(photos(), ("plan",), asker=claude, clock=clock(), style="runner")
    assert all("## A running shoe" in c["text"] for c in claude.asked(DrawAnswer))
    assert all("## A running shoe" in c["text"] and "thinning to the ball" in c["text"]
               for c in claude.asked(TurnedDrawAnswer))
    other = Claude(verdicts=("a", "b"))
    SD.draw(photos(), ("plan",), asker=other, clock=clock(), style="oxford")
    assert not any("## A running shoe" in c["text"] for c in other.calls)


def test_failures_keep_what_was_made():
    # the judge cannot answer: the first candidate, and the first turn, are kept
    made = SD.draw(photos(), ("plan",), asker=Claude(fail={Verdict: TaggingError("no answer")}), clock=clock(),
                   style="oxford")
    assert made.straight["left"]["front"] == drawn.sanitise(DRESS) and made.view == "turned"
    # the turns cannot be made: the chosen straight-on drawing is kept, straight on
    made = SD.draw(photos(), ("plan",), asker=Claude(verdicts=("b",), fail={TurnedDrawAnswer: TaggingError("x")}),
                   clock=clock(), style="oxford")
    assert made.view == "front" and made.left == drawn.side(shoe(LACES))
    # Claude cannot be reached at all: the shoe waits
    with pytest.raises(RouteUnavailable):
        SD.draw(photos(), ("plan",), asker=Claude(fail={DrawAnswer: RouteUnavailable("no route")}), clock=clock())
    # ... or not for the turns: it waits too, rather than being kept straight on
    with pytest.raises(RouteUnavailable):
        SD.draw(photos(), ("plan",), asker=Claude(fail={TurnedDrawAnswer: RouteUnavailable("no route")}),
                clock=clock(), style="oxford")
    # a fix that fails keeps the turn
    made = SD.draw(photos(), ("plan",), asker=Claude(fail={TurnedCorrectAnswer: TaggingError("x")}), clock=clock(),
                   style="oxford")
    assert made.view == "turned" and made.left == drawn.side(shoe(DRESS))


def test_the_photos_are_cut_to_the_shoe_when_the_model_is_there():
    big = [Photo(Image.new("RGB", (1200, 900), (200, 200, 200)), v, s) for v, s in VIEWS]

    def mask_of(img):   # the shoe in the middle third of the photo
        m = np.zeros((img.height, img.width), np.uint8)
        m[img.height // 3: 2 * img.height // 3, img.width // 3: 2 * img.width // 3] = 255
        return m
    claude = Claude(verdicts=("a", "b"))
    SD.draw(big, ("plan",), asker=claude, clock=clock(), style="oxford", mask_of=mask_of)
    sizes = {im.size for im in claude.asked(DrawAnswer)[0]["images"][:3]}
    assert sizes == {(496, 372)}   # 400 x 300 and its margin, not 1200 x 900
    claude = Claude(verdicts=("a", "b"))
    SD.draw(big, ("plan",), asker=claude, clock=clock(), style="oxford", mask_of=None)
    assert {im.size for im in claude.asked(DrawAnswer)[0]["images"][:3]} == {(1024, 768)}


def test_the_owners_note_on_a_turned_drawing_keeps_it_turned():
    made = SD.draw(photos(), ("plan",), asker=Claude(verdicts=("a", "b")), clock=clock(), style="oxford")
    kept = made.to_json([], "2026-11-17T09:00:00+00:00")
    claude = Claude()
    out = SD.correct(photos(), kept, "the laces should be black", ("plan",), asker=claude, clock=clock())
    asked = claude.asked(TurnedCorrectAnswer)
    assert len(asked) == 1 and claude.asked(CorrectAnswer) == [] and claude.asked(CorrectCheckAnswer) == []
    assert "the laces should be black" in asked[0]["text"] and "x -100 to 300" in asked[0]["text"]
    assert out.view == "turned" and out.style == "oxford" and out.straight == kept["straight"]
    again = out.to_json([], "2026-11-17T10:00:00+00:00")
    assert again["view"] == "turned" and again["notes"][0]["note"] == "the laces should be black"


def test_the_turned_view_has_its_own_forms_and_brief():
    import json
    schema = json.dumps(TurnedDrawAnswer.model_json_schema())
    assert "turned out 12 degrees" in schema and "turned out" not in json.dumps(DrawAnswer.model_json_schema())
    brief = SD.turned_brief("chelsea_boot")
    for words in ("x -100 to 300", "ordinary Chelsea boot", "guide.png", "inner side", "## The opening",
                  "## Behind the leg and in front of it", "## Where it is", "shaft stands upright"):
        assert words in brief, words
    assert "nearer x = 200" not in brief   # the straight-on left-and-right rule is replaced
    text = SD.turn_prompt(photos(), SHEET, drawn.side(shoe(DRESS)), None, "oxford")
    assert "Its DETAILS are exactly right" in text and "Its OUTLINES are not right" in text
    assert "SIGNATURE marks" in text and "never step the outline out sideways" in text
    check = SD.turned_check_prompt(photos(), SHEET, drawn.side(shoe(DRESS)), None, [], "oxford")
    assert check.startswith("You turned your straight-on drawing") and "foreshortened side face" in check


def test_the_owners_note_on_a_turned_boot_is_checked_for_a_leaning_shaft():
    """A correction of a turned drawing is measured against the turn of the straight-on drawing it was made from."""
    boot = drawn.split_example("boot")
    sheet = {**SHEET, "silhouette": {**SHEET["silhouette"], "height": "ankle"}, "instep_y": 84.0,
             "opening_front_y": -32.0, "top_y": -46.0}
    kept = {"straight": {"left": boot.to_json(), "right": None, "sheet": sheet}}
    checker = SD._kept_turn_checks(kept, "boot")
    upright = turned.turn_side(boot, "boot", sheet)
    lean = drawn.side({"behind": f'<g transform="matrix(1 0 -0.12 1 28.8 0)">{upright.behind}</g>',
                       "front": f'<g transform="matrix(1 0 -0.12 1 28.8 0)">{upright.front}</g>'})
    assert not any("shaft leans" in p for p in checker(upright, None, sheet))
    assert any("The left shoe's shaft leans" in p for p in checker(lean, None, sheet))
    assert SD._kept_turn_checks({"straight": None}, "boot") is None   # nothing to measure against


def test_a_drawing_too_long_to_turn_is_kept_straight_on(monkeypatch):
    def too_long(straight, style):
        raise drawn.DrawingError("The drawing is too long: 78,032 characters")
    monkeypatch.setattr(SD, "_computed", too_long)
    claude = Claude(verdicts=("b",))
    made = SD.draw(photos(), ("plan",), asker=claude, clock=clock(), style="oxford")
    assert made.view == "front" and made.left == drawn.side(shoe(LACES)) and claude.asked(TurnedDrawAnswer) == []


def test_the_estimate_allows_for_the_longest_turned_requests():
    """The turn, its check and the fix of the judge's faults hold the straight-on drawing turned, or the turned
    drawing, as text: at their longest they still fit the drawing's estimate."""
    import json

    from closet import spend
    worst = drawn.Side('<path d="' + "M0,0 " * ((drawn.MAX_CHARS - 20) // 5) + '"/>')
    notes = ["n" * SD.NOTE_MAX] * SD.NOTES_SENT
    for text, model in (
            (SD.turn_prompt(photos(), SHEET, worst, worst, "runner", notes), TurnedDrawAnswer),
            (SD.turned_check_prompt(photos(), SHEET, worst, worst, ["x" * 300] * 8, "runner", notes),
             TurnedCheckAnswer),
            (SD.correct_prompt(photos(), SHEET, worst, worst, "x" * SD.FIX_NOTE_MAX, notes,
                               brief=SD.turned_brief("runner")), TurnedCorrectAnswer),
            (SD.judge_prompt(photos(), SD.CANDIDATES, True, notes=notes), Verdict)):
        assert (len(text) + len(json.dumps(model.model_json_schema())) + len(SD.SYSTEM)) / 2 \
            <= spend.DRAW_TEXT_TOKENS, model
