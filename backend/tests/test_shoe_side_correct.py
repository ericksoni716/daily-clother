"""The owner's one-line correction of a shoe's SIDE drawing (DECISIONS, "Which drawing a note is about"): `POST
/api/items/{id}/drawn/correct` with `about: "side"` queues the note (`closet/shoedraw.py`); the worker has Claude change
only what it asks in the side and check the change against the photos (`closet/tagger/shoedrawing.py`,
`correct_side`); the front stays exactly as it was, the drawing before is kept for going back, and the owner's notes on
the side are kept apart from those on the front and passed to every later side drawing.

Claude is never called: stand-ins answer for the worker, and for the calls both routes are stood in for.
"""
import json
from contextlib import closing
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from closet import app as app_module
from closet import db, shoedraw, spend, tracejobs
from closet.drawing import drawn, drawnside
from closet.tagger import shoedrawing as SD
from closet.tagger.shoedrawing import SideCorrectAnswer, SideCorrectCheckAnswer
from closet.tagger.tagging import CapReached, RouteUnavailable, TaggingError

from .conftest import (
    BLACK_LACES,
    CUT,
    GREY_SIDE_SVG,
    GREY_UPPER,
    PASSPHRASE,
    SIDE_AGAINST,
    SIDE_CHANGED,
    SIDE_FEATURES,
    SIDE_MEASURES,
    SIDE_SVG,
    FakeApi,
    FakeClaude,
    fake_cutter,
    side_correct_answer,
    side_correct_check_answer,
)
from .test_shoe_correct import Corrector
from .test_shoedraw import Drawer
from .test_shoedraw_side import Sider, a_side, traced_shoe
from .test_shoedrawing import Asker, clock, photos
from .test_shoeviews import Sorter, a_shoe, add, answer, get, later, row, sql

OFF = f'<g transform="translate(30 0)">{SIDE_SVG}</g>'   # moved right: off its frame


class SideCorrector:
    """Stands in for Claude changing the side drawing from the owner's note: the side kept with its upper light grey,
    said to go against the photos; or raises `error`. `calls` keeps the note, the drawing it was given, the views of
    the photos and the measures; `during` runs while it works."""

    def __init__(self):
        self.error: Exception | None = None
        self.calls: list[dict] = []
        self.during = None

    def __call__(self, photos, kept, note, routes, measures=None):
        self.calls.append({"note": note, "kept": kept, "views": [p.view for p in photos], "measures": measures})
        assert routes == ("plan",)
        if self.during:
            self.during()
        if self.error:
            raise self.error
        calls = [SD.Call("side-correct", "plan", SD.MODEL, 20_000, 5_000, 2_000, 0.06, 25.0),
                 SD.Call("side-check", "plan", SD.MODEL, 18_000, 5_000, 600, 0.03, 12.0)]
        return SD.SideCorrected(drawnside.sanitise(GREY_SIDE_SVG), ["light grey upper", "flat cream sole"],
                                kept["side"]["proportions"], 1, 37.0, calls, True, [], note=note,
                                changed=SIDE_CHANGED, against_photos=SIDE_AGAINST)


@pytest.fixture
def made(cfg):
    sorter, drawer, corrector, sider, side_corrector = Sorter(), Drawer(), Corrector(), Sider(), SideCorrector()
    drawer.side = a_side()
    routes = {"now": ("plan",)}
    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, tagger=FakeClaude(),
                                   routes=lambda: routes["now"], sorter=sorter, drawer=drawer,
                                   drawing_corrector=corrector, side_drawer=sider, side_corrector=side_corrector)
    c = TestClient(app_module.create_app(sv))
    assert c.post("/api/setup", json={"passphrase": PASSPHRASE}).status_code == 204
    yield SimpleNamespace(sv=sv, c=c, routes=routes, sorter=sorter, drawer=drawer, corrector=corrector, sider=sider,
                          side_corrector=side_corrector)
    sv.stop()


def drawn_shoe(m, key="k1", traced=False) -> dict:
    """A shoe with one more photo, sorted and drawn with its side (the dress shoe, the plain low side)."""
    item = a_shoe(m.c, key)
    if traced:
        sql(m.sv.cfg, "UPDATE items SET trace = ?, trace_state = 'done' WHERE id = ?",
            (traced_shoe().to_json(), item["id"]))
    add(m.c, item, 1)
    m.sorter.reply = answer(("outer", True), ("inner", True))
    m.sv.views.drain(now=later())
    assert m.sv.draws.drain() == 1
    return item


def drawn_of(m, item) -> dict:
    return get(m.c, item)["drawn"]


def kept(m, item, column="drawn") -> dict | None:
    text = row(m.sv.cfg, item["id"])[column]
    return json.loads(text) if text else None


def send(m, item, note=GREY_UPPER, about="side"):
    body = {"note": note} if about is None else {"note": note, "about": about}
    return m.c.post(f"/api/items/{item['id']}/drawn/correct", json=body)


def picture(m, item) -> str:
    return m.c.get(get(m.c, item)["illustration_url"]).text


# ------------------------------------------------------------------ the migration

def test_the_migration_adds_which_drawing_a_note_is_about(cfg):
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    db.migrate(cfg.db_path("main"), cfg.local_backups_dir)
    with closing(db.connect(cfg.db_path("main"))) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(items)")}
    assert "drawn_note_about" in cols


# ------------------------------------------------------------------ the endpoint: what it refuses

def test_about_is_the_front_or_the_side_and_nothing_else(made):
    m = made
    item = drawn_shoe(m)
    for bad in ("back", "", None, 1, ["side"], "SIDE"):
        r = send(m, item, about=bad) if bad is not None else m.c.post(
            f"/api/items/{item['id']}/drawn/correct", json={"note": GREY_UPPER, "about": None})
        assert r.status_code == 422 and r.json()["detail"] == shoedraw.CORRECT_ABOUT, bad
    assert drawn_of(m, item)["state"] == "done" and row(m.sv.cfg, item["id"])["drawn_note"] is None
    # the note is checked first, in the same plain words as for the front
    r = send(m, item, note="", about="back")
    assert r.status_code == 422 and r.json()["detail"].startswith("Write what is wrong with the drawing")
    assert send(m, item, about="front").status_code == 202   # the front, said in so many words
    r = row(m.sv.cfg, item["id"])
    assert r["drawn_note"] == GREY_UPPER and r["drawn_note_about"] is None


def test_a_note_without_about_is_about_the_front(made):
    m = made
    item = drawn_shoe(m)
    assert send(m, item, note=BLACK_LACES, about=None).status_code == 202
    assert row(m.sv.cfg, item["id"])["drawn_note_about"] is None
    got = drawn_of(m, item)
    assert got["correcting"] is True and got["correcting_side"] is False
    assert got["message"] == f"Changing the drawing: “{BLACK_LACES}”"
    assert m.sv.draws.drain() == 1 and len(m.corrector.calls) == 1 and m.side_corrector.calls == []


def test_a_note_about_the_side_needs_a_side_and_waits_its_turn(made):
    m = made
    m.drawer.side = None
    m.sider.error = RouteUnavailable("out of reach")
    item = drawn_shoe(m)
    assert kept(m, item)["side"] is None
    r = send(m, item)
    assert r.status_code == 409 and r.json()["detail"] == shoedraw.CORRECT_NO_SIDE
    assert r.json()["detail"] == "This drawing has no side drawing to change yet."
    bare = a_shoe(m.c, "k3")
    r = send(m, bare)
    assert r.status_code == 409 and r.json()["detail"] == shoedraw.CORRECT_NOTHING   # no drawing at all
    m.sider.error = None
    m.sv.draws.drain()   # its side drawn by itself
    assert send(m, item).status_code == 202
    r = send(m, item, "the sole is thinner")
    assert r.status_code == 409 and r.json()["detail"] == shoedraw.CORRECT_BUSY   # one note at a time
    r = send(m, item, BLACK_LACES, about="front")
    assert r.status_code == 409 and r.json()["detail"] == shoedraw.CORRECT_BUSY


def test_never_in_the_demo_closet(made):
    m = made
    assert m.c.post("/api/profile", json={"profile": "demo"}).status_code == 200
    shoe = next(i for i in m.c.get("/api/items").json()["items"] if i["category"] in tracejobs.SHOES
                and m.c.get(f"/api/items/{i['id']}").json()["drawn"]["url"])
    r = send(m, shoe)
    assert r.status_code == 409 and r.json()["detail"] == shoedraw.CORRECT_DEMO
    demo = db.connect(m.sv.cfg.db_path("demo"))
    demo.execute("UPDATE items SET drawn_state = 'waiting', drawn_note = ?, drawn_note_about = 'side' WHERE id = ?",
                 (GREY_UPPER, shoe["id"]))
    demo.close()
    assert m.sv.draws.drain() == 0 and m.side_corrector.calls == []   # never sent to Claude, even if one waited


# ------------------------------------------------------------------ the worker: keeping

def test_a_side_note_changes_the_side_only_and_keeps_the_drawing_before(made):
    m = made
    item = drawn_shoe(m, traced=True)
    before, old = kept(m, item), drawn_of(m, item)
    assert send(m, item).status_code == 202
    got = drawn_of(m, item)
    assert got["state"] == "waiting" and got["correcting"] is True and got["correcting_side"] is True
    assert got["note"] == GREY_UPPER and got["message"] == f"Changing the side drawing: “{GREY_UPPER}”"
    assert got["side"]["url"] == old["side"]["url"]   # still shown until the change is done
    assert m.sv.draws.drain() == 1 and len(m.side_corrector.calls) == 1 and m.corrector.calls == []
    call = m.side_corrector.calls[0]
    assert call["note"] == GREY_UPPER and call["kept"] == before and call["views"] == ["outer", "inner"]
    assert call["measures"]["heel"] == pytest.approx(0.34)   # the measures from its trace
    now = kept(m, item)
    # the front exactly as it was: the same SVGs, sheet, notes and cost
    for key in ("left", "right", "sheet", "notes", "view", "straight", "made_at", "cost_usd", "calls", "rounds"):
        assert now[key] == before[key], key
    assert now["side"]["svg"] == drawnside.sanitise(GREY_SIDE_SVG) and now["side"]["corrected"] is True
    assert now["side"]["route"] == "plan" and now["side"]["cost_usd"] == pytest.approx(0.09)
    assert now["side_notes"] == [{"note": GREY_UPPER, "at": now["changed_at"], "against_photos": SIDE_AGAINST,
                                  "changed": SIDE_CHANGED}]
    assert now["last_change"] == "side" and kept(m, item, "drawn_prev") == before
    r = row(m.sv.cfg, item["id"])
    assert r["drawn_note"] is None and r["drawn_note_about"] is None and r["drawn_state"] == "done"
    got = drawn_of(m, item)
    assert got["url"] == old["url"]   # the front's picture is the same
    assert got["side_corrected"] is True and got["side_note"] == GREY_UPPER and got["side_changed"] == SIDE_CHANGED
    assert got["side_against_photos"] == SIDE_AGAINST and got["correcting"] is False
    assert got["corrected"] is False and got["changed"] is None   # the front's fields keep their meaning
    assert got["side"]["url"] != old["side"]["url"] and got["side"]["seconds"] == 37.0
    assert got["has_previous"] is True and got["previous_newer"] is False
    assert picture(m, item) == drawnside.card_svg(GREY_SIDE_SVG)   # the item's own drawing is the side changed


def test_going_back_and_forth_after_a_side_note(made):
    m = made
    item = drawn_shoe(m)
    before = kept(m, item)
    send(m, item)
    m.sv.draws.drain()
    after = kept(m, item)
    assert m.c.post(f"/api/items/{item['id']}/drawn/back").status_code == 200
    assert kept(m, item) == before and kept(m, item, "drawn_prev") == after
    got = drawn_of(m, item)
    assert got["side_corrected"] is False and got["previous_newer"] is True   # the newer one is a tap away
    assert picture(m, item) == drawnside.card_svg(SIDE_SVG)
    assert m.c.post(f"/api/items/{item['id']}/drawn/back").status_code == 200
    assert kept(m, item) == after and drawn_of(m, item)["side_corrected"] is True
    assert drawn_of(m, item)["previous_newer"] is False


def test_side_notes_build_up_and_are_given_to_the_next_side_correction(made):
    m = made
    item = drawn_shoe(m)
    send(m, item)
    m.sv.draws.drain()
    send(m, item, "the sole is thinner")
    m.sv.draws.drain()
    second = m.side_corrector.calls[1]["kept"]
    assert [n["note"] for n in SD.side_notes_of(second)] == [GREY_UPPER]
    assert [n["note"] for n in kept(m, item)["side_notes"]] == [GREY_UPPER, "the sole is thinner"]
    assert kept(m, item)["notes"] == []   # none on the front


def test_a_front_correction_keeps_the_side_and_its_notes(made):
    m = made
    item = drawn_shoe(m)
    send(m, item)
    m.sv.draws.drain()
    side, side_notes = kept(m, item)["side"], kept(m, item)["side_notes"]
    assert send(m, item, BLACK_LACES, about="front").status_code == 202
    assert drawn_of(m, item)["correcting_side"] is False
    assert m.sv.draws.drain() == 1 and len(m.corrector.calls) == 1
    now = kept(m, item)
    assert now["side"] == side and now["side_notes"] == side_notes and now["corrected"] is True
    assert "last_change" not in now and [n["note"] for n in now["notes"]] == [BLACK_LACES]
    got = drawn_of(m, item)
    assert got["corrected"] is True and got["note"] == BLACK_LACES and got["side_corrected"] is False
    assert got["side_note"] is None   # the last change was to the front


def test_side_notes_are_given_to_a_later_drawing_and_to_a_side_drawn_by_itself(made):
    m = made
    item = drawn_shoe(m)
    send(m, item)
    m.sv.draws.drain()
    send(m, item, BLACK_LACES, about="front")
    m.sv.draws.drain()
    # Draw again: the front's notes and the side's, each to its own drawing; the new side fails
    m.drawer.side = None
    m.sider.error = RouteUnavailable("out of reach")
    m.c.post(f"/api/items/{item['id']}/drawn")
    m.sv.draws.drain()
    assert m.drawer.notes[-1] == [BLACK_LACES] and m.drawer.side_notes[-1] == [GREY_UPPER]
    assert kept(m, item)["side"] is None and [n["note"] for n in kept(m, item)["side_notes"]] == [GREY_UPPER]
    # its side drawn later by itself keeps to them too
    m.sider.error = None
    m.sv.draws.drain()
    assert m.sider.calls[-1]["side_notes"] == [GREY_UPPER] and m.sider.calls[-1]["notes"] == [BLACK_LACES]
    assert kept(m, item)["side"]["features"] == SIDE_FEATURES


# ------------------------------------------------------------------ the worker: waiting and failing

def test_claude_out_of_reach_puts_a_side_note_back_and_says_it_is_the_side(made):
    m = made
    item = drawn_shoe(m)
    before = kept(m, item)
    send(m, item)
    m.side_corrector.error = RouteUnavailable("not signed in")
    assert m.sv.draws.drain() == 0
    r = row(m.sv.cfg, item["id"])
    assert r["drawn_state"] == "waiting" and r["drawn_attempts"] == 0 and r["drawn_note_about"] == "side"
    assert drawn_of(m, item)["message"] == shoedraw.CORRECT_SIDE_NO_ROUTE
    assert "change the side drawing" in shoedraw.CORRECT_SIDE_NO_ROUTE
    m.side_corrector.error = CapReached("this month's spending limit for the API key has been reached")
    m.sv.draws.drain()
    assert drawn_of(m, item)["message"] == shoedraw.CORRECT_SIDE_LIMIT
    assert kept(m, item) == before
    m.side_corrector.error = None
    assert m.sv.draws.drain() == 1 and drawn_of(m, item)["side_corrected"] is True


def test_after_three_failures_the_drawing_is_as_it_was_and_the_page_says_so(made):
    m = made
    item = drawn_shoe(m)
    before, prev = kept(m, item), kept(m, item, "drawn_prev")
    send(m, item)
    m.side_corrector.error = TaggingError("no usable answer")
    for _ in range(3):
        m.sv.draws.drain()
    assert len(m.side_corrector.calls) == 3
    r = row(m.sv.cfg, item["id"])
    assert r["drawn_state"] == "done" and r["drawn_note"] is None and r["drawn_note_about"] is None
    assert kept(m, item) == before and kept(m, item, "drawn_prev") == prev
    assert drawn_of(m, item)["message"] == shoedraw.CORRECT_SIDE_FAILED
    assert "the side drawing" in shoedraw.CORRECT_SIDE_FAILED


def test_a_missing_photo_fails_a_side_note_at_once(made):
    m = made
    item = drawn_shoe(m)
    before = kept(m, item)
    send(m, item)
    m.side_corrector.error = FileNotFoundError("gone")
    m.sv.draws.drain()
    assert drawn_of(m, item)["message"] == shoedraw.CORRECT_SIDE_NO_PHOTO and kept(m, item) == before


def test_a_side_note_cut_short_by_a_quit_starts_again_or_gives_up(made):
    m = made
    item = drawn_shoe(m)
    send(m, item)
    sql(m.sv.cfg, "UPDATE items SET drawn_state = 'correcting', drawn_attempts = 1 WHERE id = ?", (item["id"],))
    m.sv.draws.drain()
    assert len(m.side_corrector.calls) == 1 and drawn_of(m, item)["side_corrected"] is True
    send(m, item, "the sole is thinner")
    sql(m.sv.cfg, "UPDATE items SET drawn_state = 'correcting', drawn_attempts = ? WHERE id = ?",
        (shoedraw.MAX_ATTEMPTS, item["id"]))
    m.sv.draws.drain()
    assert len(m.side_corrector.calls) == 1 and drawn_of(m, item)["message"] == shoedraw.CORRECT_SIDE_FAILED
    assert row(m.sv.cfg, item["id"])["drawn_note_about"] is None


def test_a_side_lost_while_its_note_waited_gives_up_and_leaves_the_drawing(made):
    m = made
    item = drawn_shoe(m)
    send(m, item)
    sql(m.sv.cfg, "UPDATE items SET drawn = ? WHERE id = ?", (json.dumps({**kept(m, item), "side": None}), item["id"]))
    m.sv.draws.drain()
    assert m.side_corrector.calls == [] and drawn_of(m, item)["message"] == shoedraw.CORRECT_SIDE_FAILED


# ------------------------------------------------------------------ the calls (shoedrawing.correct_side)

def a_drawing(side_notes=(), measured=True) -> dict:
    """A drawing as kept with the item, with its side (the plain low shoe)."""
    made = SD.Drawn(drawn.side(drawn.example("dress-shoe")), None, {}, 1, 100.0, [], True, [], side=a_side())
    out = made.to_json(["p1"], "2026-11-15T12:00:00.000000Z")
    out["side"]["measured"] = measured
    out["side_notes"] = [{"note": n, "at": "x", "against_photos": None, "changed": "c"} for n in side_notes]
    return out


def test_the_side_correction_prompt_carries_the_note_the_side_the_photos_and_the_earlier_side_notes():
    text = SD.side_correct_prompt(photos(), drawnside.sanitise(SIDE_SVG), SIDE_FEATURES, GREY_UPPER,
                                  ["the toe is rounder"], drawnside.Measures(**SIDE_MEASURES))
    assert f'## The owner\'s note\n"{GREY_UPPER}"' in text and '- "the toe is rounder"' in text
    assert "earlier notes on this shoe's side drawing" in text
    assert "- Photo 1 (photo-1.jpg): the outer side, or possibly the inner side (not sure which)." in text
    assert "drawing.png shows it on its card, large and at the size of a closet tile" in text
    assert drawnside.sanitise(SIDE_SVG) in text and "- white leather upper with a plain toe" in text
    assert "the note is the owner's word, and wins over the measures" in text and "at about y" in text
    for words in ("Change ONLY what the note asks", "The note is the owner's word", "against_photos",
                  "A note can be wrong about the shoe", "toe pointing LEFT", "same frame and the same style"):
        assert words in text, words
    bare = SD.side_correct_prompt(photos(1), SIDE_SVG, SIDE_FEATURES, GREY_UPPER)
    assert "## The owner's earlier notes" not in bare and "measured this shoe's outline" not in bare
    check = SD.side_correct_check_prompt(photos(), GREY_SIDE_SVG, SIDE_FEATURES, ["It runs off the card."],
                                         GREY_UPPER, ["the toe is rounder"])
    assert "before.png" in check and "drawing.png" in check and GREY_SIDE_SVG in check
    assert "- It runs off the card." in check and "never undo it or weaken it" in check
    assert "against_photos" in check and '- "the toe is rounder"' in check


def test_a_side_is_changed_then_one_check_says_good():
    asker = Asker(side_correct_answer(), side_correct_check_answer())
    made = SD.correct_side(photos(), a_drawing(["the toe is rounder"]), f"  {GREY_UPPER}\n", ("plan", "api"),
                           asker=asker, clock=clock(), measures=SIDE_MEASURES)
    assert [c["answer_model"] for c in asker.calls] == [SideCorrectAnswer, SideCorrectCheckAnswer]
    first, second = asker.calls
    assert first["names"] == [f"photo-{n}.jpg" for n in range(1, 6)] + ["drawing.png"] and len(first["images"]) == 6
    assert second["names"][-2:] == ["before.png", "drawing.png"] and len(second["images"]) == 7
    assert f'"{GREY_UPPER}"' in first["text"] and '- "the toe is rounder"' in first["text"]
    assert drawnside.sanitise(SIDE_SVG) in first["text"] and drawnside.sanitise(GREY_SIDE_SVG) in second["text"]
    assert all(c["model"] == SD.MODEL and c["effort"] == SD.EFFORT and c["system"] == SD.SYSTEM
               and c["cache_photos"] == 5 for c in asker.calls)
    assert isinstance(made, SD.SideCorrected) and made.note == GREY_UPPER
    assert made.svg == drawnside.sanitise(GREY_SIDE_SVG) and made.good and made.rounds == 1 and made.problems == []
    assert made.changed == SIDE_CHANGED and made.against_photos == SIDE_AGAINST and made.measured
    assert made.features[0] == "light grey leather upper with a plain toe" and made.proportions == {"heel": 0.35}
    assert [c.kind for c in made.calls] == ["side-correct", "side-check"] and made.route == "plan"
    out = made.to_json("2026-11-21T10:00:00Z")
    assert out["corrected"] is True and out["svg"] == made.svg and out["made_at"] == "2026-11-21T10:00:00Z"
    assert made.entry("t") == {"note": GREY_UPPER, "at": "t", "against_photos": SIDE_AGAINST, "changed": SIDE_CHANGED}


def test_a_side_change_off_its_frame_is_fixed_by_the_check_at_most_twice():
    asker = Asker(side_correct_answer(svg=OFF), side_correct_check_answer(good=False, svg=OFF),
                  side_correct_check_answer(good=False, svg=OFF))
    made = SD.correct_side(photos(), a_drawing(), GREY_UPPER, ("plan",), asker=asker, clock=clock())
    assert len(asker.calls) == 1 + SD.MAX_CORRECT_ROUNDS == 3
    assert "It is not where the frame puts it" in asker.calls[1]["text"]   # a fresh side's frame checks
    assert made.rounds == 2 and not made.good and made.problems
    asker = Asker(side_correct_answer(svg=OFF), side_correct_check_answer(good=False), side_correct_check_answer())
    made = SD.correct_side(photos(), a_drawing(), GREY_UPPER, ("plan",), asker=asker, clock=clock())
    assert made.svg == drawnside.sanitise(GREY_SIDE_SVG) and made.problems == [] and made.rounds == 2 and made.good


def test_the_measures_are_shown_not_checked_so_the_note_wins():
    tall = dict(SIDE_MEASURES, heel=0.6, toe_box=0.4)   # the drawing is far lower than these
    asker = Asker(side_correct_answer(), side_correct_check_answer())
    made = SD.correct_side(photos(), a_drawing(), GREY_UPPER, ("plan",), asker=asker, clock=clock(), measures=tall)
    assert "too low" not in asker.calls[1]["text"] and made.good and made.problems == []


def test_against_the_photos_is_the_last_checks_word_and_a_failed_check_keeps_the_change():
    asker = Asker(side_correct_answer(), side_correct_check_answer(against=None))
    made = SD.correct_side(photos(), a_drawing(), GREY_UPPER, ("plan",), asker=asker, clock=clock())
    assert made.against_photos is None
    asker = Asker(side_correct_answer(), TaggingError("no usable answer"))
    made = SD.correct_side(photos(), a_drawing(), GREY_UPPER, ("plan",), asker=asker, clock=clock())
    assert made.rounds == 0 and made.against_photos == SIDE_AGAINST and made.svg == drawnside.sanitise(GREY_SIDE_SVG)


def test_a_side_correction_raises_as_a_side_drawing_does():
    with pytest.raises(RouteUnavailable):
        SD.correct_side(photos(), a_drawing(), GREY_UPPER, ("plan",), asker=Asker(RouteUnavailable("x")),
                        clock=clock())
    with pytest.raises(drawn.DrawingError):
        SD.correct_side(photos(), a_drawing(), GREY_UPPER, ("plan",),
                        asker=Asker(side_correct_answer(svg="<text>shoe</text>")), clock=clock())
    with pytest.raises(drawn.DrawingError):
        SD.correct_side(photos(), {**a_drawing(), "side": None}, GREY_UPPER, ("plan",), asker=Asker(), clock=clock())
    with pytest.raises(ValueError):
        SD.correct_side(photos(), a_drawing(), "  ", ("plan",), asker=Asker(), clock=clock())


def test_a_side_drawing_keeps_to_the_owners_notes_on_earlier_sides():
    text = SD.side_prompt(photos(), notes=[BLACK_LACES], side_notes=[GREY_UPPER])
    assert "## The owner's notes on earlier drawings of this shoe" in text and f'- "{BLACK_LACES}"' in text
    assert "## The owner's notes on earlier side drawings of this shoe" in text and f'- "{GREY_UPPER}"' in text
    check = SD.side_check_prompt(photos(), {"features": SIDE_FEATURES}, SIDE_SVG, [], side_notes=[GREY_UPPER])
    assert f'- "{GREY_UPPER}"' in check
    assert "notes on earlier side drawings" not in SD.side_prompt(photos())
    from .conftest import side_answer, side_check_answer
    asker = Asker(side_answer(), side_check_answer())
    SD.draw_side(photos(), ("plan",), asker=asker, clock=clock(), side_notes=[GREY_UPPER])
    assert all(f'- "{GREY_UPPER}"' in c["text"] for c in asker.calls)


def test_through_the_api_key_a_side_correction_is_streamed_cut_short_and_counted(cut_clock):
    api = FakeApi(input_tokens=25_000, output_tokens=7_000)
    made = SD.correct_side(photos(), a_drawing(), GREY_UPPER, ("api",), client=api)
    assert api.calls == 2 and made.rounds == 1 and made.good and made.route == "api"
    assert made.svg == drawnside.sanitise(GREY_SIDE_SVG) and made.against_photos == SIDE_AGAINST
    props = api.requests[0]["output_config"]["format"]["schema"]["properties"]
    assert {"changed", "against_photos", "svg"} <= set(props)
    # the check said good and stopped being read there, before its copy of the drawing
    assert [s["whole"] for s in api.streams] == [True, False]
    assert '"against_photos"' in api.streams[1]["text"] and "<path" not in api.streams[1]["text"]
    assert [c.cut_short for c in made.calls] == [False, True]


def test_the_estimate_allows_for_the_longest_side_correction():
    worst = '<path d="' + "M0,0 " * ((drawn.MAX_CHARS - 20) // 5) + '"/>'
    notes = ["n" * SD.NOTE_MAX] * SD.NOTES_SENT
    features = ["f" * SD.FEATURE_MAX] * SD.FEATURES_MAX
    m = drawnside.Measures(**SIDE_MEASURES)
    for text, model in (
            (SD.side_correct_prompt(photos(6), worst, features, "x" * SD.NOTE_MAX, notes, m), SideCorrectAnswer),
            (SD.side_correct_check_prompt(photos(6), worst, features, ["x" * 300] * 8, "x" * SD.NOTE_MAX, notes, m),
             SideCorrectCheckAnswer)):
        assert (len(text) + len(json.dumps(model.model_json_schema())) + len(SD.SYSTEM)) / 2 \
            <= spend.CORRECT_DRAW_TEXT_TOKENS


# ------------------------------------------------------------------ through the API key: spending

def test_a_side_note_through_the_api_key_is_counted_as_a_correction(cfg, cut_clock):
    api = FakeApi(input_tokens=20_000, output_tokens=5_000)
    sorter = Sorter()
    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, routes=lambda: ("api",), api_client=api,
                                   sorter=lambda photos, routes: sorter.reply)
    try:
        c = TestClient(app_module.create_app(sv))
        assert c.post("/api/setup", json={"passphrase": PASSPHRASE}).status_code == 204
        item = a_shoe(c)
        add(c, item, 1)
        sorter.reply = answer(("outer", True), ("inner", True))
        sv.views.drain(now=later())
        c.put("/api/settings", json={"tagging_api_enabled": True, "tagging_api_cap_usd": 40.0})
        assert sv.draws.drain() == 1
        drawing = api.calls
        front = get(c, item)["drawn"]
        assert front["side"] is not None
        assert c.post(f"/api/items/{item['id']}/drawn/correct",
                      json={"note": GREY_UPPER, "about": "side"}).status_code == 202
        assert sv.draws.drain() == 1 and api.calls == drawing + 2
        got = get(c, item)["drawn"]
        assert got["side_corrected"] and got["side_against_photos"] == SIDE_AGAINST
        assert got["side"]["route"] == "api" and got["side"]["rounds"] == 1
        assert got["side"]["cost_usd"] == pytest.approx(spend.cost_usd(SD.MODEL, 20_000, 5_000)
                                                        + spend.cost_usd(SD.MODEL, 20_000, CUT))
        assert got["cost_usd"] == front["cost_usd"]   # the front's own cost stays its own
        with closing(db.connect(cfg.db_path("main"))) as conn:
            rows = [r["purpose"] for r in conn.execute("SELECT purpose FROM claude_calls ORDER BY rowid")]
        assert rows == ["draw_shoe"] * drawing + ["correct_drawing"] * 2
    finally:
        sv.stop()
