"""A pattern drawn from words alone, for a piece not in the closet (closet/drawing/wordpattern.py), on the figure and
flat; and the owner's own patterned pieces drawn exactly as before."""
import colorsys
import io
import json
from pathlib import Path

import numpy as np
import pytest

from closet import illustrations
from closet.drawing import fills, wordpattern
from closet.drawing.figure import _spec, figure
from closet.drawing.illustrate import render
from closet.drawing.item import NAMED_HEX
from closet.illustrations import new_piece
from closet.tagger.taxonomy import COVERAGE
from closet.vocab import PATTERN

DEMO = Path(__file__).resolve().parents[1] / "closet" / "demo_data" / "items.json"


def find(category, color, name, pattern):
    return new_piece({"category": category, "color": color, "name": name, "pattern": pattern, "silhouette": {}})


@pytest.mark.parametrize("category, name, kind, want", [
    ("tee", "Striped tee", None, "across"), ("sweater", "Striped jumper", None, "across"),
    ("shirt", "Striped poplin shirt", None, "down"), ("shirt", "Breton shirt", None, "across"),
    ("tee", "Vertical stripe tee", None, "down"), ("polo", "Rugby top", None, "across"),
    ("shirt", "Rugby shirt", "rugby_shirt", "across"), ("jacket", "Striped jacket", None, "pinstripe"),
    ("coat", "Chalk stripe overcoat", "overcoat", "pinstripe"), ("trousers", "Wool trousers", None, "pinstripe"),
    ("shorts", "Seersucker shorts", None, "pinstripe"),
])
def test_stripes_run_across_a_knit_and_down_anything_woven_unless_the_name_says(category, name, kind, want):
    assert wordpattern.kind_of(category, "stripe", name, kind) == want


@pytest.mark.parametrize("category, name, kind, want", [
    ("shirt", "Flannel overshirt", "overshirt", "plaid"), ("jacket", "Check wool blazer", "blazer", "windowpane"),
    ("shirt", "Gingham shirt", None, "gingham"), ("trousers", "Tartan trousers", None, "plaid"),
])
def test_a_plaid_is_a_plain_plaid_a_windowpane_on_a_blazer_and_a_gingham_when_named(category, name, kind, want):
    assert wordpattern.kind_of(category, "plaid", name, kind) == want


@pytest.mark.parametrize("category, pattern", [("shirt", "floral"), ("shirt", "camo"), ("tee", "graphic"),
                                               ("shirt", "other"), ("shirt", "solid"), ("sneakers", "stripe"),
                                               ("scarf", "plaid"), (None, "stripe")])
def test_what_the_words_cannot_draw_is_drawn_in_its_colour(category, pattern):
    assert wordpattern.fill_for(category, "navy", pattern, "A piece") is None


def test_coverage_says_which_pattern_words_are_drawn():
    assert set(COVERAGE["described_patterns"]) == set(PATTERN)
    drawn = {p for p, (status, _) in COVERAGE["described_patterns"].items() if status != "not_drawn"}
    assert drawn == {"solid", *wordpattern.DRAWN}


def _lightness(hex_):
    return colorsys.rgb_to_hls(*wordpattern._rgb(hex_))[1]


@pytest.mark.parametrize("word", ["navy", "black", "burgundy", "olive", "red", "white", "cream", "light_blue", "yellow"])
def test_the_second_colour_is_a_quiet_neighbour_of_the_ground(word):
    ground = NAMED_HEX[word]
    other = wordpattern.neighbour(ground)
    h0, l0, s0 = colorsys.rgb_to_hls(*wordpattern._rgb(ground))
    h1, l1, s1 = colorsys.rgb_to_hls(*wordpattern._rgb(other))
    assert 0.25 <= abs(l1 - l0) <= 0.4                 # it reads as a pattern
    assert (l1 > l0) == (l0 < wordpattern.MIDDLE)       # lighter on a dark ground, darker on a light one
    assert s0 < 0.05 or abs(h1 - h0) < 0.02             # the ground's own hue: no new colour


@pytest.mark.parametrize("kind", list(wordpattern.BANDS))
def test_each_tile_is_one_repeat_with_the_ground_on_the_centre_line(kind):
    img, (fx, fy) = wordpattern.tile(kind, NAMED_HEX["navy"])
    a = np.asarray(img).astype(int)
    assert img.size == (wordpattern.SIDE, wordpattern.SIDE)
    varies_down, varies_across = np.ptp(a, axis=0).max() > 30, np.ptp(a, axis=1).max() > 30
    assert (varies_down, varies_across) == {"across": (True, False), "down": (False, True), "pinstripe": (False, True)}.get(
        kind, (True, True))
    x, y = int(fx * wordpattern.SIDE), int(fy * wordpattern.SIDE)
    ground = np.array([int(NAMED_HEX["navy"][i:i + 2], 16) for i in (1, 3, 5)])
    assert np.abs(a[y, x] - ground).max() <= 3


def test_it_is_sized_as_a_pattern_described_for_an_owned_piece():
    """The same scale as the owner's own described stripes and plaids (`patterns.surface`): the ruler shares and the
    tile's width and length for the same number of repeats."""
    from PIL import Image

    from closet.patterns import described, surface
    assert (wordpattern.CHEST_PER_LENGTH, wordpattern.CHEST_PER_OUTLINE) == (described.CHEST_PER_LENGTH,
                                                                           described.CHEST_PER_OUTLINE)
    assert wordpattern.WAIST_PER_OUTLINE == surface.WAIST_PER_OUTLINE
    blank = np.zeros((8, 8, 3), np.uint8)
    for category, bottom in (("shirt", None), ("trousers", "trousers"), ("shorts", "shorts")):
        fill = wordpattern.fill_for(category, "navy", "plaid", "Plaid")
        kept = surface._kept_tile(blank, wordpattern.BANDS["plaid"][1], bottom, (0.0, 0.0), "described")
        assert fill.swatch.width_frac == pytest.approx(kept["width_frac"], abs=1e-4)
        assert (fill.swatch.length_frac is None) == (kept["length_frac"] is None)
        if kept["length_frac"]:
            assert fill.swatch.length_frac == pytest.approx(kept["length_frac"], abs=1e-4)
    assert isinstance(fill.swatch.image, Image.Image)


@pytest.mark.parametrize("category, color, name, pattern, place", [
    ("shirt", "light_blue", "Striped poplin shirt", "stripe", "base"),
    ("shirt", "red", "Flannel overshirt", "plaid", "mid"),
    ("jacket", "brown", "Check wool blazer", "plaid", "outer"),
    ("tee", "navy", "Breton top", "stripe", "base"),
    ("trousers", "navy", "Striped wool trousers", "stripe", "bottom"),
])
def test_a_finds_pattern_is_drawn_flat_and_as_worn(category, color, name, pattern, place):
    piece = find(category, color, name, pattern)
    plain = find(category, color, name, "solid")
    assert piece.fill is not None and piece.fill.color == NAMED_HEX[color] and plain.fill is None
    assert _spec(piece).fill is piece.fill
    flat = render(_spec(piece), "line", uid="w")
    assert '<pattern id="pw"' in flat and "<image" in flat and "<image" not in render(_spec(plain), "line", uid="w")
    others = {"base": find("tee", "white", "Tee", "solid"), "bottom": find("jeans", "blue", "Jeans", "solid")}
    worn = figure({**others, place: piece}, uid="x")
    assert "<image" in worn and "<image" not in figure({**others, place: plain}, uid="x")


def _row(item: dict) -> dict:
    pf = item["pattern_fill"]
    return {**item, "silhouette": json.dumps(item.get("silhouette") or {}), "source": "{}",
            "tag_answer": json.dumps(item["answer"]) if item.get("answer") else None,
            "pattern_fill": json.dumps(pf) if isinstance(pf, dict) else pf, "additions": None}


@pytest.mark.parametrize("name", ["Breton striped tee", "Striped sweater", "Plaid flannel shirt", "Madras plaid shirt"])
def test_an_owned_pieces_measured_pattern_is_drawn_byte_for_byte_as_before(name):
    """The owner's own striped and plaid pieces keep the pattern measured from their photo: their drawings are the ones
    the demo closet keeps, made before patterns were drawn from words, byte for byte, and on the figure they wear
    that same measured fill."""
    item = next(i for i in json.loads(DEMO.read_text(encoding="utf-8"))["items"] if i["name"] == name)
    row = _row(item)
    assert illustrations.make(row).svg == item["illustration_svg"]
    piece = illustrations.describe(row)
    measured = illustrations.pattern_fill(row, piece)
    assert measured is not None and measured.kind in ("stripes", "swatch")
    if measured.kind == "swatch":
        assert measured.swatch.method == "measured" and isinstance(measured.swatch, fills.Swatch)


def test_a_tile_is_small_in_the_drawing():
    img, _ = wordpattern.tile("plaid", NAMED_HEX["red"])
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=84)
    assert len(buf.getvalue()) < 12_000
