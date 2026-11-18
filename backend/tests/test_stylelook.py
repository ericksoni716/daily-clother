"""Claude's look at the outfits it chose, drawn on the figure (closet/stylejobs.py, "The look"): after a plain
question, each outfit Claude chose is drawn as worn, Claude is shown the pictures and keeps or changes each one; an
answer to a message of the owner's is not looked at. The look can only improve an answer. Claude is always stood
in for; the background job is held and run by the test, and the clock is the test's."""
import json
from datetime import timedelta

import pytest

from closet import app as app_module
from closet import db, spend, styling
from closet.stylejobs import MESSAGES, Stylist
from closet.tagger.tagging import CapReached, RouteUnavailable, TaggingError, Unreachable

from . import test_stylejobs as jobs
from .conftest import fake_cutter
from .test_stylejobs import TODAY, answers, look_of, make_item, number_of, run, today, wardrobe

fixed_today = jobs.fixed_today   # the day is TODAY and the internet is never asked, here too
styled = jobs.styled             # services whose stylist asks the stand-in, with held jobs and the test's clock


# ------------------------------------------------------------------ stand-ins and helpers
class LookStandIn:
    """Stands in for Claude's look. `looks` (a list, or a function of the brief) is what it gives back, by default
    `keep(brief)`: the outfits the test had Claude choose, unchanged. `error` is raised instead. `calls` holds
    (brief, pictures, routes)."""

    def __init__(self, keep):
        self.calls: list[tuple[dict, list, tuple[str, ...]]] = []
        self.keep = keep
        self.looks = None
        self.error: Exception | None = None
        self.saw = "Nothing needed changing."

    def __call__(self, brief: dict, pictures: list, routes: tuple[str, ...]) -> dict:
        self.calls.append((brief, list(pictures), routes))
        if self.error is not None:
            raise self.error
        looks = (self.looks(brief) if callable(self.looks) else self.looks if self.looks is not None
                 else self.keep(brief))
        return {"looks": looks, "saw": self.saw, "route": routes[0], "model": "stand-in-model", "input_tokens": 400,
                "output_tokens": 150}


class DrawStandIn:
    """Stands in for the drawing: one small picture per outfit, or `error` raised, or `count` pictures."""

    def __init__(self):
        self.calls: list[list[dict]] = []
        self.error: Exception | None = None
        self.count: int | None = None

    def __call__(self, path, found: list[dict]) -> list:
        self.calls.append(found)
        if self.error is not None:
            raise self.error
        return [f"picture of outfit {i}" for i in range(1, (len(found) if self.count is None else self.count) + 1)]


def oxford(brief, why="The oxford smartens the jeans."):
    return look_of(brief, why, base="Blue oxford", mid="Grey sweater", bottom="Dark jeans", shoes="Brown boots")


def easy(brief, why="Easy and warm."):
    return look_of(brief, why, base="White tee", bottom="Navy chinos", shoes="White sneakers")


def two(brief):
    return [oxford(brief), easy(brief)]


def looking(styled, choose=two, draw=None) -> LookStandIn:
    """Claude chooses `choose(brief)` and the look, by default, keeps it. `draw`: a drawing stand-in, else the
    app's own."""
    styled.stand_in.looks = choose
    look = LookStandIn(choose)
    styled.sv.stylist.look = look
    if draw is not None:
        styled.sv.stylist.draw = draw
    return look


def asked(styled) -> dict:
    """Today once Claude's job has run: the first request starts it, `run` runs it."""
    wardrobe(styled.c)
    today(styled.c)
    run(styled)
    return today(styled.c)


def newest(styled) -> dict:
    return answers(styled.cfg)[-1]


def mine(body) -> list[dict]:
    return [o for o in body["outfits"] if o.get("by") == "claude"]


# ------------------------------------------------------------------ with no look, nothing changes
def test_with_no_look_given_nothing_changes_one_call_and_no_seen(styled):
    assert styled.sv.stylist.look is None   # a stand-in asker gets no look
    styled.stand_in.looks = two
    body = asked(styled)
    assert body["context"]["stylist"]["state"] == "ready" and len(mine(body)) == 2
    r = newest(styled)
    assert r["state"] == "ready" and r["seen"] is None
    assert r["input_tokens"] == 1200 and r["output_tokens"] == 300
    assert len(styled.stand_in.calls) == 1


def test_with_a_drawing_but_no_look_nothing_is_drawn(styled):
    draw = DrawStandIn()
    styled.sv.stylist.draw = draw
    styled.stand_in.looks = two
    asked(styled)
    assert draw.calls == [] and newest(styled)["seen"] is None


# ------------------------------------------------------------------ a look that keeps everything
def test_a_look_that_keeps_everything_gives_the_same_outfits_ready(styled):
    look = looking(styled)
    body = asked(styled)
    st = body["context"]["stylist"]
    assert st["state"] == "ready" and st["read"] == "A cool, dry day: a layer helps." and st["message"] is None
    got = mine(body)
    assert [o["reasons"] for o in got] == [["The oxford smartens the jeans."], ["Easy and warm."]]
    assert len(got) == 2 and len(look.calls) == 1


def test_a_look_that_keeps_everything_records_what_it_saw_and_no_change(styled):
    looking(styled)
    asked(styled)
    r = newest(styled)
    seen = json.loads(r["seen"])
    assert set(seen) == {"saw", "changed", "seconds"}
    assert seen["saw"] == "Nothing needed changing." and seen["changed"] == 0
    assert isinstance(seen["seconds"], float) and seen["seconds"] >= 0
    assert json.loads(r["problems"]) == []


def test_the_tokens_on_the_row_are_the_sum_of_both_calls_and_the_route_and_model_the_first(styled):
    looking(styled)
    asked(styled)
    r = newest(styled)
    assert r["input_tokens"] == 1200 + 400 and r["output_tokens"] == 300 + 150
    assert r["route"] == "plan" and r["model"] == "stand-in-model"


def test_the_look_gets_one_picture_per_outfit_claude_chose_in_order(styled):
    drawn = []
    real = styled.sv.stylist.draw

    def draw(path, found):
        pictures = real(path, found)
        drawn.append((found, pictures))
        return pictures

    look = looking(styled, draw=draw)
    asked(styled)
    [(found, pictures)] = drawn
    stored = json.loads(newest(styled)["outfits"])
    assert [o["pieces"] for o in found] == [o["pieces"] for o in stored]   # what Claude chose, in its order
    assert [o["reasons"] for o in found] == [["The oxford smartens the jeans."], ["Easy and warm."]]
    [(_, given, _)] = look.calls
    assert len(given) == 2 and all(a is b for a, b in zip(given, pictures, strict=True))


# ------------------------------------------------------------------ what the look is told
def test_the_look_is_told_the_first_brief_and_the_outfits_chosen_by_number_with_their_pictures(styled):
    look = looking(styled, draw=DrawStandIn())
    asked(styled)
    [(first, _)] = styled.stand_in.calls
    [(told, _, _)] = look.calls
    assert set(told) == set(first) | {"chosen"}
    assert {k: told[k] for k in first} == first
    n = {name: number_of(first, name) for name in ("Blue oxford", "White tee", "Grey sweater", "Dark jeans",
                                                     "Navy chinos", "Brown boots", "White sneakers")}
    assert list(n.values()) == [1, 2, 3, 4, 5, 6, 7]
    assert told["chosen"] == (
        "- Outfit 1 (outfit-1.png): base 1; mid layer 3; bottom 4; shoes 6. "
        "Why you chose it: “The oxford smartens the jeans.”\n"
        "- Outfit 2 (outfit-2.png): base 2; bottom 5; shoes 7. Why you chose it: “Easy and warm.”")


def test_the_look_is_asked_through_the_same_routes_as_the_choice_api_key_first(styled, monkeypatch):
    look = looking(styled, draw=DrawStandIn())
    monkeypatch.setattr(styled.claude, "routes", lambda: ("plan", "api"))
    asked(styled)
    [(_, first_routes)] = styled.stand_in.calls
    [(_, _, routes)] = look.calls
    assert routes == first_routes == ("api", "plan")


# ------------------------------------------------------------------ a look that changes an outfit
def lighter(brief, why="White sneakers lighten it."):
    return look_of(brief, why, base="Blue oxford", mid="Grey sweater", bottom="Navy chinos", shoes="White sneakers")


def test_a_changed_outfit_is_on_the_page_with_its_new_why_as_claudes(styled):
    look = looking(styled, draw=DrawStandIn())
    look.looks = lambda brief: [lighter(brief), easy(brief)]
    look.saw = "The boots were heavy against the jeans."
    ids = wardrobe(styled.c)
    today(styled.c)
    run(styled)
    got = mine(today(styled.c))
    assert len(got) == 2
    assert got[0]["pieces"] == {"base": ids["shirt"], "mid": ids["sweater"], "outer": None, "bottom": ids["chinos"],
                                "shoes": ids["sneakers"], "accessories": []}
    assert got[0]["reasons"] == ["White sneakers lighten it."] and got[0]["by"] == "claude"
    assert got[1]["pieces"]["base"] == ids["tee"] and got[1]["reasons"] == ["Easy and warm."]
    seen = json.loads(newest(styled)["seen"])
    assert seen["changed"] == 1 and seen["saw"] == "The boots were heavy against the jeans."


def test_outfits_given_back_in_another_order_are_not_changes(styled):
    look = looking(styled, draw=DrawStandIn())
    look.looks = lambda brief: [easy(brief, "Now first."), oxford(brief)]
    body = asked(styled)
    assert json.loads(newest(styled)["seen"])["changed"] == 0
    assert [o["reasons"] for o in mine(body)] == [["Now first."], ["The oxford smartens the jeans."]]


def test_the_same_pieces_with_accessories_in_another_order_is_not_a_change(styled):
    wardrobe(styled.c)
    make_item(styled.c, "belt", "Brown belt", "belt", "brown")
    make_item(styled.c, "scarf", "Wool scarf", "scarf", "grey")

    def dressed(order):
        def choose(brief):
            o = oxford(brief)
            o["accessories"] = [number_of(brief, name) for name in order]
            return [o, easy(brief)]
        return choose

    look = looking(styled, choose=dressed(["Brown belt", "Wool scarf"]), draw=DrawStandIn())
    look.looks = dressed(["Wool scarf", "Brown belt"])
    today(styled.c)
    run(styled)
    assert json.loads(newest(styled)["seen"])["changed"] == 0


def test_an_extra_outfit_cut_from_the_page_is_not_counted_as_changed(styled):
    # the look may give more outfits than it was shown; only as many as were chosen are kept (`merged`), so one
    # left off the page changed nothing the owner sees
    look = looking(styled, draw=DrawStandIn())
    look.looks = lambda brief: [*two(brief), lighter(brief)]
    body = asked(styled)
    assert len(mine(body)) == 2 and len(json.loads(newest(styled)["outfits"])) == 2
    assert json.loads(newest(styled)["seen"])["changed"] == 0


def test_what_the_look_saw_has_its_space_collapsed_and_is_cut_to_max_reply(styled):
    look = looking(styled, draw=DrawStandIn())
    look.saw = "  Too   much\n\n navy.  " + "x" * (styling.MAX_REPLY * 2)
    asked(styled)
    saw = json.loads(newest(styled)["seen"])["saw"]
    assert len(saw) == styling.MAX_REPLY and saw.startswith("Too much navy. xx")


def test_an_empty_saw_is_kept_as_none(styled):
    look = looking(styled, draw=DrawStandIn())
    look.saw = "   "
    asked(styled)
    seen = json.loads(newest(styled)["seen"])
    assert seen["saw"] is None and seen["changed"] == 0


# ------------------------------------------------------------------ a look whose answer cannot all be worn
def test_an_outfit_from_the_look_that_cannot_be_worn_is_left_out_and_the_first_choice_kept_after(styled):
    look = looking(styled, draw=DrawStandIn())
    look.looks = lambda brief: [{**oxford(brief), "base": 999}, easy(brief, "Still easy.")]
    ids = wardrobe(styled.c)
    today(styled.c)
    run(styled)
    got = mine(today(styled.c))
    assert [o["pieces"]["base"] for o in got] == [ids["tee"], ids["shirt"]]
    assert got[0]["reasons"] == ["Still easy."] and got[1]["reasons"] == ["The oxford smartens the jeans."]
    r = newest(styled)
    assert json.loads(r["problems"]) == ["After the look, outfit 1 was left out: 999 is not a piece in the list."]
    assert json.loads(r["seen"])["changed"] == 0


def test_the_looks_problems_come_after_the_first_answers(styled):
    look = looking(styled, choose=lambda brief: [*two(brief), {**easy(brief), "base": 999}], draw=DrawStandIn())
    look.looks = lambda brief: [{**oxford(brief), "base": 0}, easy(brief)]
    body = asked(styled)
    assert len(mine(body)) == 2
    assert json.loads(newest(styled)["problems"]) == ["Outfit 3 was left out: 999 is not a piece in the list.",
                                                      "After the look, outfit 1 was left out: it has no base."]
    assert len(look.calls[0][1]) == 2   # only the outfits kept from the first answer were drawn


def test_the_page_never_has_fewer_of_claudes_outfits_after_the_look(styled):
    look = looking(styled, draw=DrawStandIn())
    look.looks = lambda brief: [{**oxford(brief), "shoes": 0}]   # one, unwearable: and the second not given again
    body = asked(styled)
    assert len(mine(body)) == 2


def test_an_outfit_not_given_again_by_the_look_keeps_its_place_after(styled):
    look = looking(styled, draw=DrawStandIn())
    look.looks = lambda brief: [lighter(brief)]
    ids = wardrobe(styled.c)
    today(styled.c)
    run(styled)
    got = mine(today(styled.c))
    assert [o["pieces"]["bottom"] for o in got] == [ids["chinos"], ids["jeans"]]
    assert [o["pieces"]["base"] for o in got] == [ids["shirt"], ids["shirt"]]
    # the oxford outfit Claude first chose is kept after; the tee outfit is no longer one of the two
    assert json.loads(newest(styled)["seen"])["changed"] == 1


@pytest.mark.parametrize("given", [[], None])
def test_a_look_that_gives_nothing_leaves_the_first_outfits_with_no_seen_but_counts_its_tokens(styled, given):
    look = looking(styled, draw=DrawStandIn())
    look.looks = lambda brief: given
    body = asked(styled)
    assert body["context"]["stylist"]["state"] == "ready"
    assert [o["reasons"] for o in mine(body)] == [["The oxford smartens the jeans."], ["Easy and warm."]]
    r = newest(styled)
    assert r["state"] == "ready" and r["seen"] is None and json.loads(r["problems"]) == []
    assert r["input_tokens"] == 1600 and r["output_tokens"] == 450


def test_a_look_that_gives_nothing_wearable_leaves_the_first_outfits_and_says_why_in_problems(styled):
    look = looking(styled, draw=DrawStandIn())
    look.looks = lambda brief: [{**oxford(brief), "base": 999}, {**easy(brief), "bottom": 0}]
    body = asked(styled)
    assert body["context"]["stylist"]["state"] == "ready"
    assert [o["reasons"] for o in mine(body)] == [["The oxford smartens the jeans."], ["Easy and warm."]]
    r = newest(styled)
    assert r["seen"] is None and r["input_tokens"] == 1600 and r["output_tokens"] == 450
    assert json.loads(r["problems"]) == ["After the look, outfit 1 was left out: 999 is not a piece in the list.",
                                         "After the look, outfit 2 was left out: it has no bottom."]


# ------------------------------------------------------------------ the look failing
@pytest.mark.parametrize("error", [CapReached("over the limit"), RouteUnavailable("not signed in"),
                                   Unreachable("offline"), TaggingError("no answer"), ValueError("a bug")])
def test_each_failure_of_the_look_leaves_the_first_outfits_ready(styled, error):
    look = looking(styled, draw=DrawStandIn())
    look.error = error
    body = asked(styled)
    st = body["context"]["stylist"]
    assert st["state"] == "ready" and st["message"] is None
    assert [o["reasons"] for o in mine(body)] == [["The oxford smartens the jeans."], ["Easy and warm."]]
    r = newest(styled)
    assert r["state"] == "ready" and r["error"] is None and r["seen"] is None
    assert r["input_tokens"] == 1200 and r["output_tokens"] == 300
    assert len(look.calls) == 1 and styled.held == []


@pytest.mark.parametrize("error", [ValueError("cannot draw"), RuntimeError("resvg"), Unreachable("odd")])
def test_when_the_drawing_fails_the_look_is_not_asked_and_the_first_outfits_stand(styled, error):
    draw = DrawStandIn()
    draw.error = error
    look = looking(styled, draw=draw)
    body = asked(styled)
    assert body["context"]["stylist"]["state"] == "ready" and len(mine(body)) == 2
    assert look.calls == [] and len(draw.calls) == 1
    r = newest(styled)
    assert r["seen"] is None and r["input_tokens"] == 1200


@pytest.mark.parametrize("count", [0, 1, 3])
def test_when_the_drawing_gives_the_wrong_number_of_pictures_the_look_is_not_asked(styled, count):
    draw = DrawStandIn()
    draw.count = count
    look = looking(styled, draw=draw)
    body = asked(styled)
    assert body["context"]["stylist"]["state"] == "ready" and len(mine(body)) == 2
    assert look.calls == [] and newest(styled)["seen"] is None


# ------------------------------------------------------------------ "not again"
def test_an_outfit_from_the_look_the_owner_said_not_again_to_is_left_out(styled):
    ids = wardrobe(styled.c)
    yesterday = (TODAY - timedelta(days=1)).isoformat()
    worn = styled.c.post("/api/outfits/worn", json={
        "item_ids": [ids["shirt"], ids["sweater"], ids["jeans"], ids["boots"]], "worn_on": yesterday})
    assert worn.status_code == 201, worn.text
    rated = styled.c.put(f"/api/outfits/worn/{worn.json()['id']}/rating", json={"rating": "not_again"})
    assert rated.status_code == 200, rated.text
    for k in ("shirt", "sweater", "jeans", "boots"):   # all clean again, so Claude could name them
        assert styled.c.post(f"/api/items/{ids[k]}/laundry", json={"state": "clean"}).status_code == 200
    look = looking(styled, choose=lambda brief: [easy(brief)], draw=DrawStandIn())
    look.looks = lambda brief: [oxford(brief), easy(brief)]
    today(styled.c)
    run(styled)
    got = mine(today(styled.c))
    assert [o["pieces"]["base"] for o in got] == [ids["tee"]]
    problems = json.loads(newest(styled)["problems"])
    assert problems == [f"After the look, outfit 1 was left out: the owner said “not again” to it on {yesterday}."]
    assert json.loads(newest(styled)["seen"])["changed"] == 0


# ------------------------------------------------------------------ the conversation is not looked at
def ready_with_look(styled) -> LookStandIn:
    look = looking(styled, draw=DrawStandIn())
    asked(styled)
    assert len(look.calls) == 1
    return look


@pytest.mark.parametrize("new_outfits", [False, True])
def test_a_message_of_the_owners_is_not_looked_at(styled, new_outfits):
    look = ready_with_look(styled)
    styled.stand_in.looks = (lambda brief: [lighter(brief), easy(brief)]) if new_outfits else []
    r = styled.c.post("/api/outfits/today", json={**jobs.DAY, "say": "Too dressy."})
    assert r.status_code == 200, r.text
    run(styled)
    turn = newest(styled)
    assert turn["said"] == "Too dressy." and turn["state"] == "ready" and turn["seen"] is None
    assert turn["input_tokens"] == 1200 and turn["output_tokens"] == 300
    assert len(look.calls) == 1   # only the first, plain question


def test_a_plain_question_after_a_message_is_looked_at(styled):
    look = ready_with_look(styled)
    styled.stand_in.looks = []
    assert styled.c.post("/api/outfits/today", json={**jobs.DAY, "say": "Too dressy."}).status_code == 200
    run(styled)
    styled.stand_in.looks = two
    assert today(styled.c, ask_again=True)["context"]["stylist"]["state"] == "working"
    run(styled)
    assert len(look.calls) == 2
    told = look.calls[1][0]
    assert "talk" in told and "chosen" in told   # the day's conversation is part of the brief it is shown
    assert json.loads(newest(styled)["seen"])["changed"] == 0


# ------------------------------------------------------------------ the first answer failing
def test_when_no_outfit_claude_gives_can_be_worn_the_look_is_not_asked(styled):
    look = looking(styled, choose=lambda brief: [{**oxford(brief), "base": 999}], draw=DrawStandIn())
    body = asked(styled)
    assert body["context"]["stylist"]["state"] == "failed" and body["context"]["stylist"]["message"] == MESSAGES["answer"]
    assert look.calls == [] and styled.sv.stylist.draw.calls == []


@pytest.mark.parametrize("error", [Unreachable("offline"), CapReached("limit"), ValueError("bug")])
def test_when_claude_cannot_choose_the_look_is_not_asked(styled, error):
    look = looking(styled, draw=DrawStandIn())
    styled.stand_in.error = error
    body = asked(styled)
    assert body["context"]["stylist"]["state"] == "failed"
    assert look.calls == [] and newest(styled)["seen"] is None


# ------------------------------------------------------------------ the real drawing
def pieces(base, bottom, shoes, mid=None, outer=None, accessories=()):
    return {"pieces": {"base": base, "mid": mid, "outer": outer, "bottom": bottom, "shoes": shoes,
                       "accessories": list(accessories)}}


def test_the_real_drawing_gives_one_tall_rgb_picture_per_outfit_of_any_shape(styled):
    from closet.tagger import stylist
    ids = wardrobe(styled.c)
    coat = make_item(styled.c, "coat", "Navy coat", "coat", "navy")
    belt = make_item(styled.c, "belt", "Brown belt", "belt", "brown")
    scarf = make_item(styled.c, "scarf", "Wool scarf", "scarf", "grey")
    found = [pieces(ids["tee"], ids["chinos"], ids["sneakers"]),
             pieces(ids["shirt"], ids["jeans"], ids["boots"], mid=ids["sweater"]),
             pieces(ids["shirt"], ids["jeans"], ids["boots"], mid=ids["sweater"], outer=coat, accessories=[belt, scarf])]
    drawn = styled.sv.stylist.draw(styled.cfg.db_path("main"), found)
    assert len(drawn) == 3
    for picture in drawn:
        assert picture.mode == "RGB"
        assert picture.width == stylist.PICTURE_WIDTH and picture.height > picture.width
        assert len(picture.getcolors(maxcolors=1 << 20)) > 1
    assert drawn[0].tobytes() != drawn[2].tobytes()   # the pieces show


def test_an_outfit_whose_piece_was_deleted_since_skips_the_look_and_the_first_choice_stands(styled):
    look = looking(styled)   # the app's own drawing
    ids = wardrobe(styled.c)
    today(styled.c)
    assert styled.c.delete(f"/api/items/{ids['boots']}").status_code == 204   # while Claude was choosing
    run(styled)
    r = newest(styled)
    assert r["state"] == "ready" and r["seen"] is None and r["error"] is None
    assert [o["pieces"]["shoes"] for o in json.loads(r["outfits"])] == [ids["boots"], ids["sneakers"]]
    assert look.calls == []


# ------------------------------------------------------------------ wiring
def test_a_stand_in_asker_gets_the_drawing_but_no_look(cfg, claude):
    def ask(brief, routes):
        raise AssertionError("not asked")

    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, tagger=claude, routes=lambda: claude.routes(),
                                   corrector=claude.correct, stylist_ask=ask)
    try:
        assert sv.stylist.ask is ask and sv.stylist.look is None and callable(sv.stylist.draw)
    finally:
        sv.stop()


def test_a_stand_in_look_given_is_the_one_used(cfg, claude):
    def ask(brief, routes):
        raise AssertionError("not asked")

    def look(brief, pictures, routes):
        raise AssertionError("not looked")

    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, tagger=claude, routes=lambda: claude.routes(),
                                   corrector=claude.correct, stylist_ask=ask, stylist_look=look)
    try:
        assert sv.stylist.look is look and callable(sv.stylist.draw)
    finally:
        sv.stop()


def test_the_real_stylist_looks_through_stylist_look_on_the_style_meter(cfg, monkeypatch):
    from closet.tagger import correcting, stylist

    told = []
    answer = stylist.Seen(saw="Too dark.", outfits=[stylist.Look(base=1, mid=0, outer=0, bottom=2, shoes=3,
                                                                accessories=[], why="Lighter.", watch="")])

    def fake_look(brief, pictures, routes, client=None, meter=None, **kw):
        told.append((brief, pictures, routes, meter))
        return correcting.CorrectionResult(answer=answer, route="api", model="styling-model", input_tokens=700,
                                           output_tokens=90)

    monkeypatch.setattr(stylist, "look", fake_look)
    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, routes=lambda: ("api",))
    try:
        assert sv.stylist.look is not None and callable(sv.stylist.draw)
        got = sv.stylist.look({"chosen": "- Outfit 1"}, ["p"], ("api",))
    finally:
        sv.stop()
    assert got == {"looks": [{"base": 1, "mid": 0, "outer": 0, "bottom": 2, "shoes": 3, "accessories": [],
                              "why": "Lighter.", "watch": ""}], "saw": "Too dark.", "route": "api",
                   "model": "styling-model", "input_tokens": 700, "output_tokens": 90}
    [(brief, pictures, routes, meter)] = told
    assert brief == {"chosen": "- Outfit 1"} and pictures == ["p"] and routes == ("api",)
    assert meter is not None and meter.purpose == spend.PURPOSE_STYLE


def test_a_stylist_built_without_draw_or_look_never_looks():
    s = Stylist(lambda b, r: {}, lambda: ("plan",))
    assert s.draw is None and s.look is None
    found = [{"pieces": {"base": "t"}}]
    assert s._looked(None, "id", {}, None, None, {}, ("plan",), found) == (found, [], None,
                                                                     {"input_tokens": 0, "output_tokens": 0})
    s.draw = lambda path, f: pytest.fail("drawn without a look")
    assert s._looked(None, "id", {}, None, None, {}, ("plan",), found)[2] is None


# ------------------------------------------------------------------ the table
def test_a_closet_has_the_seen_column(cfg):
    path = cfg.db_path("main")
    path.parent.mkdir(parents=True, exist_ok=True)
    db.migrate(path, cfg.data_dir / "backups")
    conn = db.connect(path)
    try:
        cols = {r["name"]: r for r in conn.execute("PRAGMA table_info(style_answers)")}
        assert "seen" in cols and cols["seen"]["type"] == "TEXT" and cols["seen"]["notnull"] == 0
        conn.execute("INSERT INTO style_answers (id, day, key, state, dressed, asked_at, created_at) "
                     "VALUES ('a', '2026-11-17', 'k', 'working', '{}', 0, 'now')")
        assert conn.execute("SELECT seen FROM style_answers WHERE id = 'a'").fetchone()["seen"] is None
    finally:
        conn.close()


# ------------------------------------------------------------------ found in review (each shown failing first)
def test_a_slow_look_after_a_slow_choice_is_not_taken_for_a_lost_question(styled):
    from closet.stylejobs import STALE_S
    look = looking(styled)
    wardrobe(styled.c)
    first = today(styled.c)["context"]["stylist"]["id"]
    seen_meanwhile = []

    def slow_choice(brief):
        styled.now["t"] += STALE_S - 60   # Claude took most of the time a question may take
        return two(brief)

    def slow_look(brief):
        styled.now["t"] += STALE_S - 60   # and the look as long again: the owner's page asks meanwhile
        seen_meanwhile.append(today(styled.c)["context"]["stylist"])
        return two(brief)
    styled.stand_in.looks, look.looks = slow_choice, slow_look
    run(styled)
    assert [(s["state"], s["id"]) for s in seen_meanwhile] == [("working", first)]
    assert [r["state"] for r in answers(styled.cfg)] == ["ready"] and styled.held == []


def test_the_look_is_told_what_the_owner_said_today(styled):
    look = looking(styled)
    asked(styled)
    styled.stand_in.reply = "Done."
    r = styled.c.post("/api/outfits/today", json={**jobs.DAY, "say": "No sneakers today."})
    assert r.status_code == 200, r.text
    run(styled)
    today(styled.c, ask_again=True)
    run(styled)
    brief = look.calls[-1][0]
    assert "- The owner: “No sneakers today.”" in brief["talk"]
    from closet.tagger import stylist
    text = stylist.look_prompt(brief, 2)
    assert "# The conversation with the owner today" in text and "No sneakers today." in text
    assert "What the owner told you today still holds: do not undo it." in text
    # with nothing said, the look's question has no such part
    assert "conversation" not in stylist.look_prompt({k: v for k, v in brief.items() if k != "talk"}, 2)
