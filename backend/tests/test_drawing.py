"""Drawing an item from its tags (closet.drawing.item): the entry point the app uses."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from closet.drawing import item
from closet.drawing.illustrate import Fill, Spec, render
from closet.tagger.schema import Details, ItemTags, Silhouette, drawing_for

BACKEND = Path(__file__).resolve().parents[1]


def answer(category: str, silhouette: dict | None = None, **details) -> dict:
    """A tagger answer as the app stores it (plain JSON data)."""
    return ItemTags(
        category=category, category_confidence=0.9, color="navy", color_confidence=0.9, secondary_colors=[],
        pattern="solid", pattern_confidence=0.9, formality="casual", formality_confidence=0.9, season="all",
        season_confidence=0.9, silhouette=Silhouette.of(**(silhouette or {})), silhouette_confidence=0.9,
        details=Details.plain(**details), details_confidence=0.9, brand=None, size=None, material=None,
        needs_shot=None).model_dump(mode="json")


def expected(tags: dict, hex_: str, uid: str = "a") -> str:
    template, params, extras, _ = drawing_for(ItemTags.model_validate(tags))
    return render(Spec(template, params, Fill("solid", hex_), **extras), "line", uid=uid)


POLO = answer("polo", {"sleeve": "short"}, neckline="polo_collar", placket="polo", placket_buttons=2,
              button_color="white", fabric="pique")
TROUSERS = answer("trousers", {"leg": "tapered", "pant_length": "ankle"}, waist="belt_loops", pant_hem="turn_up",
                  features=["pleats", "pressed_crease"])
BOOTS = answer("boots", {"shoe_height": "high"}, shoe_style="chelsea_boot", sole_color="black")


@pytest.mark.parametrize("tags", [POLO, TROUSERS, BOOTS], ids=["top", "trousers", "shoes"])
def test_a_full_answer_is_drawn_with_its_details(tags):
    svg = item.svg_from_answer(tags, "#27344f", uid="i1")
    assert svg == expected(tags, "#27344f", "i1")
    assert svg.startswith("<svg") and "#27344f" in svg
    plain = answer(tags["category"])
    assert svg != item.svg_from_answer(plain, "#27344f", uid="i1")   # the details change the drawing
    # stored as JSON text works the same; without a colour of its own the colour word is used
    assert item.svg_from_answer(json.dumps(tags), "#27344f", uid="i1") == svg
    assert item.svg_from_answer(tags) == expected(tags, "#27344f")   # "navy"


def test_top_trousers_and_shoes_are_different_shapes():
    svgs = {item.svg_from_answer(t, "#777777") for t in (POLO, TROUSERS, BOOTS)}
    assert len(svgs) == 3


@pytest.mark.parametrize("category,silhouette", [
    ("shirt", {"sleeve": "long", "neck": "collar", "fit": "slim"}),
    ("jeans", {"leg": "wide", "pant_length": "ankle"}),
    ("sneakers", {"shoe_height": "high"}),
], ids=["top", "trousers", "shoes"])
def test_coarse_fields_alone_are_drawn(category, silhouette):
    svg = item.svg_from_fields(category, "#a9c3e0", "solid", silhouette, uid="c1")
    assert svg == expected(answer(category, silhouette), "#a9c3e0", "c1")
    assert svg != item.svg_from_fields(category, "#a9c3e0", "solid", {}, uid="c1")   # the silhouette is used


def test_coarse_fields_use_the_colour_word_when_there_is_no_hex():
    assert "#27344f" in item.svg_from_fields("tee", None, "solid", {}, color="navy")
    assert item.svg_from_fields("tee", None, None, None) == expected(answer("tee"), item.DEFAULT_HEX)


@pytest.mark.parametrize("category", ["bag", "belt", "hat", "scarf", "other", "spacesuit", None, 3, ["tee"]])
def test_nothing_to_draw_gives_none(category):
    assert item.svg_from_fields(category, "#000000") is None
    assert item.svg_from_answer({**POLO, "category": category}) is None


@pytest.mark.parametrize("raw", [None, "", "not json", "[1, 2]", 42, [], {}, {"category": "tee"}, b"\xff"])
def test_odd_answers_never_raise(raw):
    out = item.svg_from_answer(raw)
    assert out is None or out == expected(answer("tee"), item.DEFAULT_HEX)


def test_an_answer_with_odd_values_keeps_what_is_valid():
    odd = json.loads(json.dumps(POLO))
    odd["details"]["collar"] = "cravat"                 # not in the vocabulary
    odd["details"]["placket_buttons"] = "two"
    odd["details"]["weird_new_field"] = 7
    odd["silhouette"]["sleeve"] = "very long"
    del odd["details"]["fabric"]                        # as from an older version of the schema
    odd["category_confidence"] = 5
    want = answer("polo", {}, neckline="polo_collar", placket="polo", button_color="white")
    assert item.svg_from_answer(odd, "#27344f") == expected(want, "#27344f")


def test_odd_fields_fall_back_without_raising():
    plain_tee = expected(answer("tee"), item.DEFAULT_HEX)
    assert item.svg_from_fields("tee", "red", "zigzag", {"sleeve": "tentacle", "neck": None, 7: "x"}) == plain_tee
    assert item.svg_from_fields("tee", '#fff" onload="x', None, "not a dict") == plain_tee
    assert item.svg_from_fields("tee", "#123", None, None, uid='"><script>') == expected(answer("tee"), "#123")


def test_a_drawing_that_fails_falls_back_to_the_plainest_of_its_category(monkeypatch):
    real = item.drawing_for

    def fussy(tags):
        if tags.details != Details.plain():
            raise RuntimeError("cannot draw this")
        return real(tags)

    monkeypatch.setattr(item, "drawing_for", fussy)
    assert item.svg_from_answer(BOOTS, "#6b4a32") == expected(answer("boots"), "#6b4a32")

    monkeypatch.setattr(item, "drawing_for", lambda tags: 1 / 0)
    assert item.svg_from_answer(BOOTS, "#6b4a32") is None
    assert item.svg_from_fields("boots", "#6b4a32") is None


def test_importing_the_drawing_code_does_not_import_opencv():
    code = ("import sys\n"
            "import closet.drawing, closet.drawing.templates, closet.drawing.illustrate, closet.drawing.fills\n"
            "import closet.drawing.item as item\n"
            "assert item.svg_from_fields('tee', '#ffffff').startswith('<svg')\n"
            "print('cv2' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"
