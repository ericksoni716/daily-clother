"""The cloth drawn from Claude's description of its surface (the garment loop test's arm F, adopted 18 November):
the form asked for, how a described surface reaches the pattern job and the drawing, and that answers from before
it was asked for are measured as before. Made-up cloth only."""
import json

import numpy as np
import pytest
from PIL import Image

from closet import db, patjobs, tagjobs
from closet.drawing import item as drawing_item
from closet.patterns import surface
from closet.tagger import claude_cli, surfaceform, tagging
from closet.tagger.schema import SCHEMA_VERSION, ItemTags

from .conftest import fake_cutter
from .test_patjobs import Landmarker, described, row


@pytest.fixture
def make(cfg, claude):
    """The app with a stand-in measurer and landmarker (as in test_patjobs)."""
    from fastapi.testclient import TestClient

    from closet import app as app_module
    made = []

    def build(measurer, landmarker=None):
        claude.mode = "answers"
        sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None, tagger=claude,
                                       routes=lambda: claude.routes(), corrector=claude.correct,
                                       measurer=measurer, landmarker=landmarker)
        made.append(sv)
        c = TestClient(app_module.create_app(sv))
        return sv, c
    yield build
    for sv in made:
        sv.stop()

PLAID = {"kind": "plaid", "bands": [{"color": "#7a1f2b", "width": 5}, {"color": "#1d2b3a", "width": 3}],
         "direction": None, "size": "medium", "blocks": [], "panels": [], "colors": []}
PRINT = {"kind": "other", "bands": [], "direction": None, "size": None, "blocks": [], "panels": [],
         "colors": [{"color": "#2f6b4f", "share": 6}, {"color": "#e8d9b0", "share": 4}]}
PLAIN = {"kind": "plain", "bands": [], "direction": None, "size": None, "blocks": [], "panels": [],
         "colors": [{"color": "#3a5f8a", "share": 10}]}
PARTS = {"kind": "blocks", "bands": [], "direction": None, "size": None,
         "blocks": [{"part": "sleeves", "color": "#b03030"}], "panels": [], "colors": [{"color": "#f2f0ea", "share": 7}]}
PANELS = {"kind": "blocks", "bands": [], "direction": None, "size": None, "blocks": [],
          "panels": [{"top": 0, "bottom": 40, "color": "#22304f"}], "colors": [{"color": "#ece4d0", "share": 6}]}
TILE = {"version": 1, "kind": "tile", "how": "described", "image": surface.tile_text(Image.new("RGB", (16, 16), "#7a1f2b")),
        "width_frac": 0.1, "length_frac": 0.15, "phase": [0.1, 0.1], "phase_right": None}


class SurfaceMeasurer:
    """A stand-in for the app's measurer that also takes a described surface."""

    def __init__(self, result=TILE):
        self.result, self.calls = result, []

    def __call__(self, cut, pattern, words, marks, surface=None, category=None):
        self.calls.append({"pattern": pattern, "marks": marks, "surface": surface, "category": category})
        return self.result


def _answer(cfg, item_id, surface_raw, **fields):
    conn = db.connect(cfg.db_path("main"))
    try:
        r = conn.execute("SELECT tag_answer FROM items WHERE id = ?", (item_id,)).fetchone()
        answer = json.loads(r["tag_answer"])
        answer["surface"] = surface_raw
        if "pattern" in fields:   # the answer's own pattern word, as describing keeps it
            answer["pattern"] = fields["pattern"]
        sets = {"tag_answer": json.dumps(answer), **fields}
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(f"UPDATE items SET {', '.join(f'{k} = ?' for k in sets)} WHERE id = ?", [*sets.values(), item_id])
        patjobs.mark(conn, item_id)
        conn.execute("COMMIT")
    finally:
        conn.close()


# ---- the form asked for ---------------------------------------------------------------------------------------------

def test_every_new_description_is_asked_for_its_surface_on_both_routes():
    sent = claude_cli.strict_schema()
    assert "surface" in sent["properties"] and "surface" in sent["required"]
    tool = tagging.answer_tool()["input_schema"]
    assert "surface" in tool["properties"] and "surface" in tool["required"]
    assert surfaceform.GUIDANCE in tagging.PROMPT
    assert SCHEMA_VERSION >= 7   # the surface and lettering came with version 7 and are asked for in every one since
    assert "lettering" in sent["required"] and "lettering" in tool["required"]


def test_answers_from_before_the_surface_was_asked_for_stay_valid():
    old = ItemTags.model_validate(_plain_answer())
    assert old.surface is None
    new = tagging.fitted({**_plain_answer(), "surface": PLAID})
    assert new.surface.kind == "plaid" and new.surface.bands[0].color == "#7a1f2b"


def _plain_answer():
    from .conftest import ANSWER
    data = ANSWER.model_dump(mode="json")
    data.pop("surface", None)
    return data


def test_the_description_is_made_on_its_own_model():
    assert tagjobs.MODEL == tagging.CONFIG["roles"]["describing"] == "claude-sonnet-5-5"
    assert tagging.CONFIG["roles"]["tagging"] == "claude-haiku-5-5"      # corrections and shopping stay where they were


# ---- which items the pattern job takes ------------------------------------------------------------------------------

@pytest.mark.parametrize("raw, pattern, category, expected", [
    (PLAID, "plaid", "shirt", patjobs.SURFACE),
    (PRINT, "floral", "shirt", patjobs.SURFACE),
    (PANELS, "solid", "sweater", patjobs.SURFACE),
    (PLAIN, "plaid", "shirt", None),                       # the surface says plain: nothing drawn from the photo
    (PARTS, "other", "jacket", None),                      # parts in another colour: drawn from the answer alone
    (None, "stripe", "shirt", "stripe"),                   # an answer from before: measured as before
    (None, "solid", "shirt", None),
    (PLAIN, "graphic", "tee", patjobs.GRAPHIC),            # a print on plain cloth is still lifted from the photo
    (PLAID, "graphic", "tee", patjobs.SURFACE),            # a logo on patterned cloth: the cloth is drawn (logo left out)
    (PRINT, "graphic", "shirt", patjobs.SURFACE),          # an all-over print called a graphic: pieced, sleeves too
])
def test_which_items_the_pattern_job_takes(raw, pattern, category, expected):
    answer = {"details": {}} | ({"surface": raw} if raw is not None else {})
    assert patjobs.method({"category": category, "pattern": pattern, "tag_answer": json.dumps(answer)}) == expected


@pytest.mark.parametrize("owner, expected", [("solid", None), ("stripe", "stripe"), ("plaid", patjobs.SURFACE)])
def test_a_pattern_the_owner_changed_is_measured_by_their_word_not_the_described_surface(owner, expected):
    answer = {"pattern": "plaid", "details": {}, "surface": PLAID}
    assert patjobs.method({"category": "shirt", "pattern": owner, "tag_answer": json.dumps(answer)}) == expected


def test_an_owners_pattern_word_puts_the_described_parts_aside_in_the_drawing():
    from closet import illustrations
    answer = {**_plain_answer(), "category": "jacket", "pattern": "solid", "surface": PARTS}
    row_ = {"source": json.dumps({"pattern": illustrations.OWNER}), "silhouette": None, "tag_answer": json.dumps(answer),
            "category": "jacket", "color": answer["color"], "pattern": "stripe", "own_details": None}
    assert "surface" not in illustrations.drawn_answer(row_)
    kept = {**row_, "pattern": "solid"}   # the owner set the word the answer gave: the described cloth stands
    assert illustrations.drawn_answer(kept)["surface"] == PARTS


def test_a_described_plaid_is_drawn_from_its_surface_and_sized_on_the_landmarks(make, cfg):
    m, lm = SurfaceMeasurer(), Landmarker()
    sv, c = make(m, lm)
    item = described(sv, c)
    _answer(cfg, item["id"], PLAID, pattern="plaid")
    assert row(cfg, item["id"])["pattern_state"] == "waiting"
    assert sv.pattern_worker.drain() == 1
    call, = m.calls
    assert call["pattern"] == patjobs.SURFACE and call["surface"] == PLAID and call["category"] == row(cfg, item["id"])["category"]
    assert call["marks"] is not None and lm.calls == 1
    kept = row(cfg, item["id"])
    assert kept["pattern_state"] == "done" and json.loads(kept["pattern_fill"])["how"] == "described"


def test_a_print_is_pieced_without_asking_for_landmarks(make, cfg):
    m, lm = SurfaceMeasurer(), Landmarker()
    sv, c = make(m, lm)
    item = described(sv, c)
    _answer(cfg, item["id"], PRINT, pattern="floral")
    sv.pattern_worker.drain()
    assert m.calls[0]["surface"] == PRINT and m.calls[0]["marks"] is None and lm.calls == 0


def test_plain_described_cloth_is_not_measured_and_drops_an_earlier_pattern(make, cfg):
    m = SurfaceMeasurer()
    sv, c = make(m, Landmarker())
    item = described(sv, c)
    _answer(cfg, item["id"], PLAID, pattern="plaid")
    sv.pattern_worker.drain()
    _answer(cfg, item["id"], PLAIN, pattern="solid")
    r = row(cfg, item["id"])
    assert r["pattern_state"] is None and r["pattern_fill"] is None and len(m.calls) == 1


# ---- drawn from the answer ------------------------------------------------------------------------------------------

def test_parts_in_another_colour_are_drawn_from_the_answer():
    data = {**_plain_answer(), "category": "jacket", "surface": PARTS}
    tags = tagging.fitted(data)
    svg = drawing_item.drawing_from_answer(tags.model_dump(mode="json")).svg
    assert surfaceform.softened("#b03030") in svg


def test_a_plain_items_colour_is_the_described_one_softened():
    tags = tagging.fitted({**_plain_answer(), "surface": PLAIN})
    assert tagjobs.color_hex(tags) == surfaceform.softened("#3a5f8a") != "#3a5f8a"
    assert tagjobs.color_hex(tagging.fitted(_plain_answer())) == tagjobs.color_hex(ItemTags.model_validate(_plain_answer()))


def test_the_drawings_softening_matches_the_measurings():
    for h in ("#1f2a44", "#b02a2a", "#3fc9c4", "#ece4d0", "#000000"):
        a, b = surfaceform.softened(h), surface._soft(h)
        assert max(abs(int(a[i:i + 2], 16) - int(b[i:i + 2], 16)) for i in (1, 3, 5)) <= 2


# ---- what the pattern job keeps (`surface.kept_for_item`) -----------------------------------------------------------

def _cut(size=(500, 600)):
    w, h = size
    yy, xx = np.mgrid[0:h, 0:w]
    on = ((yy // 30 + xx // 30) % 2 == 0)
    rgb = np.where(on[..., None], [122, 31, 43], [29, 43, 58]).astype(np.uint8)
    alpha = np.zeros((h, w), np.uint8)
    alpha[40:h - 40, 50:w - 50] = 255
    return Image.fromarray(np.dstack([rgb, alpha]), "RGBA")


def test_a_plaid_is_kept_as_a_woven_tile_sized_from_the_photo():
    marks = {"underarm_left": {"x": 80.0, "y": 200.0}, "underarm_right": {"x": 420.0, "y": 200.0}}
    kept = surface.kept_for_item(_cut(), PLAID, marks, "shirt")
    assert kept["kind"] == "tile" and kept["how"] == "described" and kept["scale"] in ("photo", "said", "fine")
    assert surface.kept_for_item(_cut(), PLAID, None, "trousers")["length_frac"] is None   # a bottom: the waistband


def test_bands_across_the_body_are_kept_as_one_set_of_stripes():
    kept = surface.kept_for_item(_cut(), PANELS, None, "sweater")
    assert kept["kind"] == "stripes" and kept["how"] == "panels" and kept["orientation"] == "horizontal"
    assert [f for _, f in kept["bands"]] == pytest.approx([0.4, 0.6])
    from closet.drawing import stored
    assert stored.fill_from(kept, "#888888").kind == "stripes"


def test_a_print_is_pieced_by_the_apps_own_measuring(monkeypatch):
    from closet.patterns import measure
    seen = []
    monkeypatch.setattr(measure, "measure", lambda cut, pattern, *a, **k: seen.append(pattern) or TILE)
    assert surface.kept_for_item(_cut(), PRINT, None, "shirt") is TILE and seen == ["floral"]
    # piecing needs no colour from the answer: a print said with none is still pieced, not drawn plain
    assert surface.kept_for_item(_cut(), {**PRINT, "colors": []}, None, "shirt") is TILE and len(seen) == 2


def test_a_top_without_landmarks_is_sized_against_its_outline_not_the_size_word():
    kept = surface.kept_for_item(_cut(), PLAID, None, "shirt")
    assert kept["scale"] != "said"
    ruler = surface.outline_ruler(_cut())
    width = ruler["underarm_right"]["x"] - ruler["underarm_left"]["x"]
    assert width == pytest.approx(surface.CHEST_PER_CUTOUT * 399, abs=1)


def test_plain_cloth_and_parts_keep_no_pattern():
    assert surface.kept_for_item(_cut(), PLAIN, None, "shirt") is None
    assert surface.kept_for_item(_cut(), PARTS, None, "jacket") is None
    assert surface.kept_for_item(_cut(), {"kind": "plaid", "bands": []}, None, "shirt") is None   # nothing to draw


def test_the_plan_route_carries_the_surfaces_words_in_its_prompt_not_on_the_command_line(monkeypatch):
    """With the surface's descriptions in the schema the command line for describing an item was about 33,900
    characters, over Windows' 32,767 (`test_windows`): the plan route sends them in its prompt instead, word for
    word; the API route keeps them in the tool, as the garment loop test sent them."""
    from types import SimpleNamespace

    from .conftest import ANSWER
    sent = {}

    def run(cmd, stdin=None, **kw):
        sent["cmd"], sent["prompt"] = cmd, stdin.read().decode("utf-8")
        said = {"is_error": False, "result": "", "structured_output": ANSWER.model_dump(mode="json"),
                "usage": {"input_tokens": 10, "output_tokens": 5}}
        return SimpleNamespace(returncode=0, stdout=json.dumps(said), stderr="")
    monkeypatch.setattr(claude_cli.subprocess, "run", run)
    claude_cli.tag_item_cli("claude-sonnet-5-5", [Image.new("RGB", (40, 40))], exe="claude")
    schema = json.loads(sent["cmd"][sent["cmd"].index("--json-schema") + 1])
    for name in surfaceform.FORMS:
        assert "description" not in json.dumps(schema["$defs"][name + "Sent"]), name
    assert surfaceform.NOTES in sent["prompt"]
    for text in surfaceform.FIELD_TEXT.values():
        assert text in sent["prompt"]
        assert text in json.dumps(tagging.answer_tool())
