"""Claude adding to a garment's drawing at the owner's word (DECISIONS, "Claude adds to a garment's drawing"): the
parts read safely (`drawing.added`), drawn over the template on the item's drawing and moved with the garment onto the
As worn figure, asked of Claude with one check (`tagger.adding`), and kept with the item with one level to go back to
(`closet.additions`, `POST/DELETE /api/items/{id}/additions`, `POST /api/items/{id}/additions/back`).

Claude is never called: a stand-in answers for the drawing, and `correcting.ask` is stood in for the calls.
"""
import json
import threading
from contextlib import closing

import pytest
from PIL import Image

from closet import additions, db, illustrations, progress, spend
from closet import app as app_module
from closet.drawing import added, fitting
from closet.drawing.figure import Piece, flat_shape, plan
from closet.drawing.illustrate import Fill, Spec, render
from closet.drawing.templates import build
from closet.tagger import adding
from closet.tagger.correcting import CorrectionResult
from closet.tagger.tagging import CapReached, RouteUnavailable

from .conftest import FakeClaude, LocalClient, fake_cutter, upload
from .test_corrections import cut

RED = "#c0392b"
# a patch lying along the sleeve on the viewer's left of a long-sleeved top, well inside its edges
SLEEVE_PATCH = {"what": "red patch on the right sleeve", "role": "inlay",
                "d": "M 83.9,191.5 L 100.4,198.6 L 90.1,222.5 L 73.6,215.4 Z", "color": RED, "clip": False}
CHEST_TAB = {"what": "yellow tab on the chest", "role": "mark", "d": "M 222,140 L 246,140 L 246,149 L 222,149 Z",
             "color": "#f1c40f", "clip": False}


# ------------------------------------------------------------------ the parts, read

def test_a_part_is_written_again_from_its_numbers_with_every_point_an_x_y_pair():
    part = added.read_one({"what": "  a   patch ", "role": "inlay", "d": "M10 20 30 40L50,60 Q 1 2 3 4 C1,2 3,4 5,6z",
                           "color": "#ABCDEF", "clip": True})
    assert part.d == "M 10,20 L 30,40 L 50,60 Q 1,2 3,4 C 1,2 3,4 5,6 Z"
    assert (part.what, part.color, part.clip) == ("a patch", "#abcdef", True)
    assert all(fitting.PAIR.fullmatch(p) for p in part.d.replace("M ", "").replace("L ", "").replace("Q ", "")
               .replace("C ", "").replace(" Z", "").split())


@pytest.mark.parametrize("raw, why", [
    ({"role": "inlay", "d": "m 10,10 l 5,5 z"}, "uses m"),
    ({"role": "inlay", "d": "M 10,10 A 5 5 0 0 1 20,20"}, "uses A"),
    ({"role": "inlay", "d": "L 10,10 L 20,20"}, "does not start with M"),
    ({"role": "inlay", "d": "M 10,10 L 20"}, "wrong count"),
    ({"role": "inlay", "d": "M 10,10 Q 20,20 30,30 40,40 50,50"}, "wrong count"),
    ({"role": "inlay", "d": "M 10,10 L 900,20"}, "off the drawing"),
    ({"role": "inlay", "d": 'M 10,10 L 20,20" onload="alert(1)'}, "other than commands and numbers"),
    ({"role": "inlay", "d": "M 10,10"}, "fewer than two points"),
    ({"role": "inlay", "d": "M 0,0 " + "L 1,1 " * added.MAX_POINTS}, "too many points"),
    ({"role": "paint", "d": "M 10,10 L 20,20"}, "kind"),
    ({"role": "mark", "d": "M 10,10 L 20,20", "color": "red"}, "colour"),
    ({"role": "mark", "d": "M 10,10 L 20,20", "color": '#fff" onload="x'}, "colour"),
])
def test_a_part_that_cannot_be_drawn_safely_is_left_out_with_why(raw, why):
    kept, said = added.read([raw])
    assert kept == [] and len(said) == 1 and why in said[0] and said[0].startswith("part 1:")


def test_at_most_max_parts_are_kept_and_nothing_unread_reaches_a_drawing():
    raw = [dict(CHEST_TAB)] * (added.MAX_PARTS + 3) + [{"role": "inlay", "d": "nonsense"}]
    kept, said = added.read(raw)
    assert len(kept) == added.MAX_PARTS and len(said) == 4
    assert added.parts("not a list") == () and added.parts(None) == ()


# ------------------------------------------------------------------ drawn on the item and on the figure

LONG_SLEEVED = {"neck": "crew", "sleeve": "long", "hem": "rib", "cuffs": "rib"}


def test_the_parts_are_drawn_over_the_templates_own_parts_on_the_items_drawing():
    parts = added.parts([SLEEVE_PATCH, CHEST_TAB, {"what": "seam", "role": "line", "d": "M 200,150 L 200,250"}])
    plain = render(Spec("top", dict(LONG_SLEEVED), Fill("solid", "#2b2b2b")), "line", uid="t")
    svg = render(Spec("top", dict(LONG_SLEEVED), Fill("solid", "#2b2b2b"), added=parts), "line", uid="t")
    assert RED not in plain and f'd="{SLEEVE_PATCH["d"]}" fill="{RED}"' in svg and 'fill="#f1c40f"' in svg
    assert 'd="M 200,150 L 200,250" fill="none"' in svg
    # over the template's parts: after the last of them (the neck's inside) and its rib cuffs
    assert svg.index(RED) > svg.rindex('fill="url(#rb')


def test_a_part_on_a_sleeve_stays_on_the_sleeve_as_it_hangs_round_the_arm_on_the_figure():
    piece = Piece("sweater", None, "#2b2b2b", "black", None, {"sleeve": "long"},
                  added=added.parts([SLEEVE_PATCH, CHEST_TAB]))
    top = plan({"base": piece}).get("base")
    fitted = {p.color: p.d for p in top.shape.parts if p.color in (RED, "#f1c40f")}
    sleeve = min(fitting.sleeves(top.shape), key=lambda s: s.cuff[0])   # the one on the viewer's left
    assert all(fitting.inside(q, sleeve.poly) for q in fitting.points(fitted[RED]))
    x0, _, x1, _ = top.shape.body_box
    assert all(x0 < x < x1 for x, _ in fitting.points(fitted["#f1c40f"]))   # the tab stays on the chest
    flat = flat_shape(piece)
    assert fitted[RED] != next(p.d for p in flat.parts if p.color == RED)   # moved onto the wearer, not pasted


def test_the_plainest_drawing_a_piece_falls_back_to_carries_no_parts(monkeypatch):
    from closet.drawing import item
    notes = []
    tags = item._tags({"category": "tee", "color": "black"}, notes)
    svg, _ = item._draw(tags, "#222222", "a", notes, added=added.parts([CHEST_TAB]))
    assert "#f1c40f" in svg
    real, calls = item.drawing_for, []

    def fails_once(t):   # the item's own drawing cannot be made: the plainest one is drawn instead
        calls.append(t)
        if len(calls) == 1:
            raise ValueError("a template that cannot be built")
        return real(t)
    monkeypatch.setattr(item, "drawing_for", fails_once)
    svg, _ = item._draw(tags, "#222222", "a", notes, added=added.parts([CHEST_TAB]))
    assert len(calls) == 2 and item.FELL_BACK in notes and "#f1c40f" not in svg


# ------------------------------------------------------------------ what Claude is shown

def test_the_grid_is_drawn_in_the_drawings_own_coordinates_and_needs_no_font():
    svg = render(Spec("top", dict(LONG_SLEEVED), Fill("solid", "#2b2b2b")), "line", uid="t")
    shift = added._GRID_DY.search(svg).group(1)
    grid = added.gridded(svg)
    assert grid.count(f'<g transform="translate(0 {shift})">') == 2 and "<text" not in grid
    assert grid.endswith("</svg>") and 'd="M50,' in grid


def test_the_shape_in_words_names_each_sleeve_and_the_outline():
    words = added.geometry(build("top", dict(LONG_SLEEVED)))
    assert "The sleeve on your left (the wearer's right)" in words and "The sleeve on your right" in words
    assert "The garment's outline: M " in words and "Landmarks:" in words


def test_a_part_reaching_past_the_garment_is_found_unless_the_edge_cuts_it():
    outline = build("top", dict(LONG_SLEEVED)).outline
    off = added.read_one({"what": "tag", "role": "inlay", "d": "M 5,5 L 30,5 L 30,30 Z"})
    on = added.read_one(SLEEVE_PATCH)
    assert adding.off_garment(outline, [on, off]) == [
        "part 2 (tag) reaches past the garment's edge; if it is on the garment, keep it inside, or set clip"]
    assert adding.off_garment(outline, [added.Added("tag", "inlay", off.d, None, True)]) == []


def test_the_owners_line_is_one_line_and_not_too_long():
    assert adding.clean_note("  a red\npatch  ") == "a red patch"
    for bad in ("", "   ", None, "x" * (adding.NOTE_MAX + 1)):
        with pytest.raises(ValueError):
            adding.clean_note(bad)


class Asked:
    """Stands in for `correcting.ask`: each call kept (its text, image names and answer shape), answered in turn."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, text, images, routes, **kw):
        self.calls.append({"text": text, "names": kw["names"], "shape": kw["answer_model"], "images": images, **kw})
        return CorrectionResult(self.answers.pop(0), "plan", adding.MODEL, 10_000, 2_000, 1_000)


def _render(parts):
    return render(Spec("top", dict(LONG_SLEEVED), Fill("solid", "#2b2b2b"), added=tuple(p.part() for p in parts)),
                  "line", uid="t")


def _answer(*parts, said="Drew a red patch."):
    return adding.Adding(parts=[adding.Part(**p) for p in parts], said=said)


def test_claude_is_shown_the_photo_the_gridded_drawing_the_shape_the_parts_before_and_the_earlier_lines(monkeypatch):
    asked = Asked(_answer(dict(CHEST_TAB), dict(SLEEVE_PATCH)), adding.Checked(good=True))
    monkeypatch.setattr(adding.correcting, "ask", asked)
    shape = build("top", dict(LONG_SLEEVED))
    before = [added.read_one(CHEST_TAB)]
    made = adding.add("a red patch on the right sleeve", ["a yellow tab on the chest"], Image.new("RGBA", (40, 40)),
                      before, added.geometry(shape), shape.outline, _render, ("plan",))
    draw, check = asked.calls
    assert draw["names"] == ["photo.png", "drawing.png"] and check["names"] == ["photo.png", "before.png", "after.png"]
    assert draw["shape"] is adding.Adding and check["shape"] is adding.Checked
    assert draw["model"] == adding.MODEL and draw["effort"] == adding.EFFORT and draw["system"] == adding.SYSTEM
    assert "“a red patch on the right sleeve”" in draw["text"] and "- “a yellow tab on the chest”" in draw["text"]
    assert json.dumps([before[0].as_json()]) in draw["text"] and "The sleeve on your left" in draw["text"]
    assert all(im.mode == "RGB" for im in draw["images"])   # the cutout laid on white
    assert [p.as_json() for p in made.parts] == [added.read_one(CHEST_TAB).as_json(), added.read_one(SLEEVE_PATCH).as_json()]
    assert made.said == "Drew a red patch." and made.checks == 1 and made.route == "plan"
    assert made.input_tokens == 20_000 and made.api_usd == pytest.approx(
        2 * spend.cost_usd(adding.MODEL, 9_000, 2_000, 0, 1_000))


def test_the_check_is_told_what_cannot_be_read_and_its_fixed_parts_are_kept(monkeypatch):
    bad = {"what": "broken", "role": "inlay", "d": "m 1,1 l 2,2 z", "color": RED, "clip": False}
    fixed = dict(SLEEVE_PATCH)
    asked = Asked(_answer(dict(SLEEVE_PATCH), bad),
                  adding.Checked(good=False, parts=[adding.Part(**fixed)], said="Drew the patch; the other was wrong."))
    monkeypatch.setattr(adding.correcting, "ask", asked)
    shape = build("top", dict(LONG_SLEEVED))
    made = adding.add("a patch", [], None, [], added.geometry(shape), shape.outline, _render, ("plan",))
    assert "part 2: its path uses m" in asked.calls[1]["text"]
    assert asked.calls[0]["names"] == ["drawing.png"]   # no photo: drawn from the words alone
    assert [p.what for p in made.parts] == ["red patch on the right sleeve"] and made.left_out == []
    assert made.said == "Drew the patch; the other was wrong."


def test_nothing_readable_is_an_error_not_an_empty_drawing(monkeypatch):
    bad = {"what": "broken", "role": "inlay", "d": "m 1,1 l 2,2 z", "color": RED, "clip": False}
    monkeypatch.setattr(adding.correcting, "ask", Asked(_answer(bad), adding.Checked(good=True)))
    shape = build("top", dict(LONG_SLEEVED))
    with pytest.raises(ValueError):
        adding.add("a patch", [], None, [], added.geometry(shape), shape.outline, _render, ("plan",))


def test_the_estimate_allows_for_the_longest_request():
    worst = [added.Added("x" * added.MAX_WHAT, "inlay", "M " + " L ".join(["399.9,459.9"] * added.MAX_POINTS) + " Z",
                         "#123456", True)] * added.MAX_PARTS
    geometry = added.geometry(build("top", {"neck": "hood", "front": "zip", "pockets": "kangaroo", "sleeve": "long"}))
    notes = ["n" * adding.NOTE_MAX] * adding.NOTES_SENT
    for text, model in ((adding.draw_prompt("x" * adding.NOTE_MAX, notes, geometry, worst, True), adding.Adding),
                        (adding.check_prompt("x" * adding.NOTE_MAX, geometry, worst, "s" * 400, ["p" * 120] * 31, True),
                         adding.Checked)):
        assert (len(text) + len(json.dumps(model.model_json_schema())) + len(adding.SYSTEM)) / 2 <= spend.ADD_TEXT_TOKENS
    assert spend.estimate_add_to_drawing(3) >= spend.cost_usd(
        adding.MODEL, spend.ADD_TEXT_TOKENS + 3 * spend.IMAGE_TOKENS, adding.MAX_TOKENS)


# ------------------------------------------------------------------ kept with the item

class Adder:
    """Stands in for Claude drawing the owner's line: answers `parts` (with CHEST_TAB added to what is there by
    default), or raises `error`; `hold`, when set, makes it wait until released. `calls` keeps what it was given."""

    def __init__(self):
        self.parts = None
        self.error: Exception | None = None
        self.said = "Drew a yellow tab on the chest."
        self.calls: list[dict] = []
        self.hold: threading.Event | None = None

    def __call__(self, note, notes, photo, now, geometry, outline, render, routes=(), client=None, meter=None):
        self.calls.append({"note": note, "notes": notes, "photo": photo, "now": now, "geometry": geometry,
                           "svg": render([added.read_one(CHEST_TAB)]), "routes": routes, "meter": meter})
        if self.hold is not None:
            self.hold.wait(10)
        if self.error is not None:
            raise self.error
        parts = self.parts if self.parts is not None else [*now, added.read_one(CHEST_TAB)]
        return adding.Result(parts, self.said, checks=1, route="plan", api_usd=0.21, seconds=42.4)


@pytest.fixture
def adder():
    return Adder()


@pytest.fixture
def services(cfg, adder):
    claude = FakeClaude()
    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, tagger=claude, routes=lambda: ("plan",),
                                   corrector=claude.correct, adder=adder)
    sv.claude = claude
    yield sv
    sv.stop()


@pytest.fixture
def client(services):
    return LocalClient(app_module.create_app(services))


def a_top(client, services, key="k1"):
    services.claude.mode = "answers"
    item = upload(client, key=key).json()
    cut(services)
    assert services.tag_worker.drain() == 1
    return client.get(f"/api/items/{item['id']}").json()


def send(client, services, item_id, note="a yellow tab on the chest"):
    r = client.post(f"/api/items/{item_id}/additions", json={"note": note})
    services.additions.join()
    return r


def test_a_line_is_drawn_on_kept_with_the_item_and_drawn_on_its_picture(client, services, adder):
    item = a_top(client, services)
    assert item["additions"]["state"] == "idle" and item["additions"]["parts"] == []
    r = send(client, services, item["id"])
    assert r.status_code == 202
    got = client.get(f"/api/items/{item['id']}").json()
    a = got["additions"]
    assert a["state"] == "idle" and a["parts"] == ["yellow tab on the chest"]
    assert a["said"] == "Drew a yellow tab on the chest."
    assert a["notes"][0]["note"] == "a yellow tab on the chest"
    assert a["took"] == "Drawn in 42 s on your Claude plan, checked against the photo · about $0.21 if drawn on the API key."
    assert a["can_go_back"] and a["can_remove"] and not a["moved"] and not a["back_newer"]
    assert "#f1c40f" in client.get(got["illustration_url"]).text
    assert got["illustration_url"] != item["illustration_url"]
    call = adder.calls[0]
    assert call["note"] == "a yellow tab on the chest" and call["notes"] == [] and call["now"] == []
    assert call["photo"] is not None and call["routes"] == ("plan",) and call["meter"].purpose == spend.PURPOSE_ADD_TO_DRAWING
    assert "#f1c40f" in call["svg"] and "The sleeve on your left" in call["geometry"]


def test_with_no_photo_to_read_it_says_so_and_was_not_checked_against_one(client, services, adder, cfg):
    item = a_top(client, services)
    with closing(db.connect(cfg.db_path("main"))) as conn:
        conn.execute("DELETE FROM photos WHERE item_id = ?", (item["id"],))
    send(client, services, item["id"])
    a = client.get(f"/api/items/{item['id']}").json()["additions"]
    assert adder.calls[0]["photo"] is None
    assert a["said"] == "Drew a yellow tab on the chest. " + additions.NO_PHOTO
    assert a["took"].startswith("Drawn in 42 s on your Claude plan, checked once ·")


def test_the_next_line_is_given_the_parts_and_lines_before_it(client, services, adder):
    item = a_top(client, services)
    send(client, services, item["id"])
    adder.parts = [added.read_one(CHEST_TAB), added.read_one(SLEEVE_PATCH)]
    send(client, services, item["id"], "and a red patch on the right sleeve")
    assert [p.what for p in adder.calls[1]["now"]] == ["yellow tab on the chest"]
    assert adder.calls[1]["notes"] == ["a yellow tab on the chest"]
    a = client.get(f"/api/items/{item['id']}").json()["additions"]
    assert a["parts"] == ["yellow tab on the chest", "red patch on the right sleeve"]
    assert [n["note"] for n in a["notes"]] == ["and a red patch on the right sleeve", "a yellow tab on the chest"]


def test_going_back_swaps_with_the_drawing_before_and_removing_keeps_them_to_go_back_to(client, services):
    item = a_top(client, services)
    send(client, services, item["id"])
    back = client.post(f"/api/items/{item['id']}/additions/back").json()
    assert back["additions"]["parts"] == [] and back["additions"]["can_go_back"] and back["additions"]["back_newer"]
    assert "#f1c40f" not in client.get(back["illustration_url"]).text
    again = client.post(f"/api/items/{item['id']}/additions/back").json()
    assert again["additions"]["parts"] == ["yellow tab on the chest"] and not again["additions"]["back_newer"]
    gone = client.delete(f"/api/items/{item['id']}/additions").json()
    assert gone["additions"]["parts"] == [] and gone["additions"]["can_go_back"] and not gone["additions"]["can_remove"]
    assert "#f1c40f" not in client.get(gone["illustration_url"]).text
    assert client.delete(f"/api/items/{item['id']}/additions").status_code == 409
    restored = client.post(f"/api/items/{item['id']}/additions/back").json()
    assert restored["additions"]["parts"] == ["yellow tab on the chest"]


def test_there_is_nothing_to_go_back_to_before_anything_was_drawn_on(client, services):
    item = a_top(client, services)
    r = client.post(f"/api/items/{item['id']}/additions/back")
    assert r.status_code == 409 and r.json()["detail"] == additions.NO_PREVIOUS


def test_while_a_line_is_drawn_the_item_shows_it_in_its_progress_and_takes_no_other(client, services, adder):
    item = a_top(client, services)
    adder.hold = threading.Event()
    r = client.post(f"/api/items/{item['id']}/additions", json={"note": "a yellow tab on the chest"})
    try:
        a = r.json()["additions"]
        assert a["state"] == "drawing" and a["message"] == additions.DRAWING.format(note="a yellow tab on the chest")
        assert not a["can_go_back"] and not a["can_remove"]
        p = client.get(f"/api/items/{item['id']}").json()["progress"]
        assert (p["stage"], p["state"], p["words"]) == ("added", "working", progress.ADDING)
        assert [i["id"] for i in client.get("/api/progress").json()["items"]] == [item["id"]]
        again = client.post(f"/api/items/{item['id']}/additions", json={"note": "another"})
        assert again.status_code == 409 and again.json()["detail"] == additions.BUSY
        assert client.post(f"/api/items/{item['id']}/additions/back").status_code == 409
    finally:
        adder.hold.set()
        services.additions.join()
    assert client.get(f"/api/items/{item['id']}").json()["progress"] is None


@pytest.mark.parametrize("error, message", [
    (RouteUnavailable("not signed in"), additions.NO_ROUTE),
    (CapReached("limit"), additions.LIMIT),
    (RuntimeError("anything else"), additions.FAILED),
    (ValueError("nothing Claude drew could be read"), additions.FAILED),
])
def test_a_line_that_could_not_be_drawn_leaves_the_drawing_as_it_was_and_says_why(client, services, adder, error, message):
    item = a_top(client, services)
    adder.error = error
    send(client, services, item["id"])
    got = client.get(f"/api/items/{item['id']}").json()
    assert got["additions"]["state"] == "failed" and got["additions"]["message"] == message
    assert got["additions"]["note"] == "a yellow tab on the chest" and got["additions"]["parts"] == []
    assert got["illustration_url"] == item["illustration_url"]
    adder.error = None
    send(client, services, item["id"])   # sent again, it is drawn
    assert client.get(f"/api/items/{item['id']}").json()["additions"]["state"] == "idle"


def test_claude_answering_without_drawing_says_so_and_keeps_nothing_new(client, services, adder):
    item = a_top(client, services)
    adder.parts, adder.said = [], "The collar's shape is changed in Fix the details."
    send(client, services, item["id"], "make the collar rounder")
    a = client.get(f"/api/items/{item['id']}").json()["additions"]
    assert a["state"] == "said" and a["message"] == "The collar's shape is changed in Fix the details."
    assert not a["can_go_back"]


@pytest.mark.parametrize("note, status", [("", 422), ("x" * (adding.NOTE_MAX + 1), 422), (None, 422)])
def test_a_line_must_say_something_short(client, services, note, status):
    item = a_top(client, services)
    assert client.post(f"/api/items/{item['id']}/additions", json={"note": note}).status_code == status


def test_a_shoe_and_the_demo_closet_are_not_drawn_on(client, services, cfg):
    item = a_top(client, services)
    with closing(db.connect(cfg.db_path("main"))) as conn:
        conn.execute("UPDATE items SET category = 'sneakers' WHERE id = ?", (item["id"],))
    r = client.post(f"/api/items/{item['id']}/additions", json={"note": "a red stripe"})
    assert r.status_code == 409 and r.json()["detail"] == additions.SHOE
    assert client.get(f"/api/items/{item['id']}").json()["additions"] is None
    services.state.update(profile="demo")
    from closet import demo
    demo.ensure(cfg)
    with closing(db.connect(cfg.db_path("demo"))) as conn:
        demo_id = conn.execute("SELECT id FROM items WHERE category = 'tee' LIMIT 1").fetchone()["id"]
    r = client.post(f"/api/items/{demo_id}/additions", json={"note": "a red stripe"})
    assert r.status_code == 409 and r.json()["detail"] == additions.DEMO


def test_a_line_being_drawn_when_nines_stopped_is_not_drawn_and_the_page_says_to_send_it_again(cfg, adder):
    claude = FakeClaude()
    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, tagger=claude, routes=lambda: ("plan",),
                                   corrector=claude.correct, adder=adder)
    c = LocalClient(app_module.create_app(sv))
    sv.claude = claude
    item = a_top(c, sv)
    with closing(db.connect(cfg.db_path("main"))) as conn:
        conn.execute("UPDATE items SET additions_state = 'drawing', additions_job = ? WHERE id = ?",
                     (json.dumps({"note": "a tab", "at": "x"}), item["id"]))
    sv.stop()
    again = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, tagger=claude, routes=lambda: ("plan",),
                                      corrector=claude.correct, adder=adder)
    try:
        a = LocalClient(app_module.create_app(again)).get(f"/api/items/{item['id']}").json()["additions"]
        assert a["state"] == "failed" and a["message"] == additions.STOPPED and a["note"] == "a tab"
    finally:
        again.stop()


def test_the_page_says_when_the_shape_under_the_additions_changed(client, services):
    item = a_top(client, services)
    send(client, services, item["id"])
    r = client.put(f"/api/items/{item['id']}/details", json={"details": {"sleeve_length": "long"}})
    assert r.status_code == 200
    assert client.get(f"/api/items/{item['id']}").json()["additions"]["moved"]


def test_the_outfit_figure_draws_the_additions_too(client, services, cfg):
    item = a_top(client, services)
    send(client, services, item["id"])
    with closing(db.connect(cfg.db_path("main"))) as conn:
        row = conn.execute("SELECT * FROM items WHERE id = ?", (item["id"],)).fetchone()
        assert "#f1c40f" in illustrations.outfit_figure(conn, {"base": item["id"]})
        assert illustrations.added_of(row)
