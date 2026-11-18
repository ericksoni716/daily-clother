"""The general surface form of the garment loop experiment (`closet.patterns.surface`), on made-up cloth only."""
import base64
import io

import numpy as np
import pytest
from PIL import Image

from closet.drawing import stored
from closet.patterns import surface


def _form(**kw):
    raw = {"kind": "plain", "bands": [], "direction": None, "size": None, "blocks": [], "colors": []}
    raw.update(kw)
    return raw


NAVY, WHITE, RED = "#1f2a44", "#f4f4f0", "#b02a2a"


def test_a_plain_cloth_is_its_main_colour_and_draws_no_pattern():
    d = surface.read(_form(colors=[{"color": NAVY, "share": 9}]))
    out = surface.drawn(d, None, None)
    assert d["kind"] == "plain" and out["kept"] is None and out["blocks"] == [] and not out["not_drawn"]
    assert out["body"].startswith("#") and len(out["body"]) == 7


@pytest.mark.parametrize("raw, why", [
    (_form(kind="plaid", bands=[{"color": NAVY, "width": 4}], colors=[]), "fewer than two colours"),
    (_form(kind="stripes", bands=[{"color": NAVY, "width": 4}, {"color": WHITE, "width": 2}]), "no direction"),
    (_form(kind="dots", colors=[{"color": RED, "share": 1}]), None),
])
def test_what_cannot_be_drawn_as_said_says_less(raw, why):
    d = surface.read(raw)
    assert d["kind"] == "other"
    assert (why is None and d["fell"] is None) or why in d["fell"]
    assert surface.drawn(d, None, None)["not_drawn"] is True


def test_blocks_with_no_part_are_plain_and_unknown_parts_are_dropped():
    d = surface.read(_form(kind="blocks", blocks=[{"part": "hood", "color": RED}], colors=[{"color": NAVY, "share": 1}]))
    assert d["kind"] == "plain"
    d = surface.read(_form(kind="blocks", blocks=[{"part": "sleeves", "color": RED}, {"part": "sleeves", "color": WHITE}],
                           colors=[{"color": NAVY, "share": 1}]))
    out = surface.drawn(d, None, None)
    assert [p for p, _ in out["blocks"]] == ["sleeves"]


def test_no_colour_at_all_is_nothing_and_a_pattern_gives_its_main_colours():
    assert surface.read(_form()) is None
    assert surface.read("not a form") is None
    d = surface.read(_form(kind="other", bands=[{"color": WHITE, "width": 1}, {"color": NAVY, "width": 5}]))
    assert d["colors"][0][0] == NAVY


def test_a_patch_replaces_whole_fields_and_keeps_what_it_leaves_null():
    raw = _form(kind="stripes", direction="horizontal", bands=[{"color": NAVY, "width": 4}, {"color": WHITE, "width": 2}])
    out = surface.patched(raw, {"kind": None, "bands": [{"color": RED, "width": 1}, {"color": WHITE, "width": 1}],
                                "direction": None, "colors": None, "blocks": None, "scale": 2})
    assert out["direction"] == "horizontal" and out["bands"][0]["color"] == RED and "scale" not in out
    assert surface.scale_of({"scale": 9}) == surface.SCALE[1]
    assert surface.scale_of({"scale": None}) == 1.0
    assert surface.scale_of({"scale": "big"}) == 1.0


def _tile(kept):
    return np.asarray(Image.open(io.BytesIO(base64.b64decode(kept["image"]))).convert("RGB")).astype(float)


def _spread(tile):
    """How much the tile's row averages differ from row to row, and its column averages from column to column."""
    return float(tile.mean(axis=1).std(axis=0).max()), float(tile.mean(axis=0).std(axis=0).max())


@pytest.mark.parametrize("direction", ["horizontal", "vertical"])
def test_stripes_are_woven_one_way_and_drawn_by_the_app(direction):
    d = surface.read(_form(kind="stripes", direction=direction, size="medium",
                           bands=[{"color": NAVY, "width": 4}, {"color": WHITE, "width": 2}]))
    out = surface.drawn(d, None, None)
    rows, cols = _spread(_tile(out["kept"]))
    along, across = (cols, rows) if direction == "horizontal" else (rows, cols)
    assert along < 3 and across > 40       # the same all along a stripe, changing across the stripes
    assert out["repeats"] == pytest.approx(4.0) and out["scale_how"] == "said"
    assert stored.fill_from(out["kept"], "#888888").kind == "swatch"


def test_a_plaid_is_woven_by_described_and_the_scale_patch_sizes_the_repeat():
    d = surface.read(_form(kind="plaid", size="large",
                           bands=[{"color": RED, "width": 6}, {"color": NAVY, "width": 4}, {"color": WHITE, "width": 1}]))
    out = surface.drawn(d, None, None)
    bigger = surface.drawn(d, None, None, scale=2.0)
    assert out["repeats"] == pytest.approx(2.5) and bigger["repeats"] == pytest.approx(1.25)
    assert bigger["kept"]["width_frac"] == pytest.approx(2 * out["kept"]["width_frac"], rel=0.01)
    rows, cols = _spread(_tile(out["kept"]))
    assert rows > 20 and cols > 20         # bands both ways


def test_on_trousers_and_shorts_the_repeat_is_sized_against_the_waistband():
    d = surface.read(_form(kind="plaid", size="medium", bands=[{"color": RED, "width": 3}, {"color": NAVY, "width": 3}]))
    trousers = surface.drawn(d, None, None, bottom="trousers")["kept"]
    shorts = surface.drawn(d, None, None, bottom="shorts")["kept"]
    assert trousers["length_frac"] is None
    assert trousers["width_frac"] == pytest.approx(0.885 / 4, abs=1e-3)
    assert shorts["width_frac"] < trousers["width_frac"]


def _striped_cut(period=40, size=(600, 700), horizontal=True):
    w, h = size
    yy, xx = np.mgrid[0:h, 0:w]
    on = ((yy if horizontal else xx) % period) < period * 0.4
    rgb = np.where(on[..., None], [30, 40, 70], [240, 240, 235]).astype(np.uint8)
    alpha = np.zeros((h, w), np.uint8)
    alpha[40:h - 40, 60:w - 60] = 255
    return Image.fromarray(np.dstack([rgb, alpha]), "RGBA")


def test_the_stripes_scale_is_read_from_the_photo_against_the_ruler():
    cut = _striped_cut(period=40)
    ruler = {"underarm_left": {"x": 100.0, "y": 200.0}, "underarm_right": {"x": 500.0, "y": 200.0}}
    assert surface.stripe_repeats(cut, ruler, "horizontal") == pytest.approx(10.0, rel=0.08)
    d = surface.read(_form(kind="stripes", direction="horizontal", size="huge",
                           bands=[{"color": NAVY, "width": 4}, {"color": WHITE, "width": 6}]))
    out = surface.drawn(d, cut, ruler)
    assert out["scale_how"] == "photo" and out["repeats"] == pytest.approx(10.0, rel=0.08)
    assert surface.stripe_repeats(cut, None, "horizontal") is None


def test_the_waist_ruler_is_the_waistband_of_a_bottom():
    alpha = np.zeros((500, 400), np.uint8)
    alpha[50:70, 80:320] = 255                                   # the waistband
    alpha[70:480, 80:190] = 255
    alpha[70:480, 210:320] = 255                                 # two legs
    cut = Image.fromarray(np.dstack([np.full((500, 400, 3), 120, np.uint8), alpha]), "RGBA")
    r = surface.waist_ruler(cut)
    assert r["underarm_right"]["x"] - r["underarm_left"]["x"] == pytest.approx(239, abs=2)
    assert surface.waist_ruler(Image.new("RGBA", (50, 50))) is None


# ---- the second form -------------------------------------------------------------------------------------------

def test_the_second_form_reads_bands_across_the_body_and_drops_nonsense():
    d = surface.read(_form(kind="blocks", colors=[{"color": WHITE, "share": 6}],
                           panels=[{"top": 60, "bottom": 30, "color": RED}, {"top": 20, "bottom": 35, "color": NAVY},
                                   {"top": "x", "bottom": 50, "color": RED}, {"top": 50, "bottom": 51, "color": RED}]))
    assert d["kind"] == "blocks" and d["panels"] == [(0.2, 0.35, NAVY)]
    assert surface.read(_form(kind="blocks", colors=[{"color": WHITE, "share": 1}]))["kind"] == "plain"


def test_bands_across_the_body_are_one_garment_sized_picture():
    d = surface.read(_form(kind="blocks", colors=[{"color": WHITE, "share": 6}],
                           panels=[{"top": 50, "bottom": 100, "color": NAVY}]))
    out = surface.drawn(d, None, None, second=True, aspect=1.2)
    tile = _tile(out["kept"])
    assert out["kept"]["width_frac"] == 1.0 and out["kept"]["phase"] is None
    assert tile.shape[0] == pytest.approx(1.2 * tile.shape[1], abs=2)
    top, low = tile[: tile.shape[0] // 3].mean(), tile[-tile.shape[0] // 3:].mean()
    assert top > low + 60                                     # white above, navy below
    assert surface.drawn(d, None, None)["kept"] is None       # the first form draws no bands


def test_other_is_drawn_from_the_apps_own_piecing_in_the_second_form_only():
    pieced = {"kind": "tile", "image": "x", "width_frac": 0.9, "version": 1}
    d = surface.read(_form(kind="other", colors=[{"color": RED, "share": 1}]))
    assert surface.drawn(d, None, None, second=True, pieced=pieced)["kept"] is pieced
    first = surface.drawn(d, None, None, pieced=pieced)
    assert first["kept"] is None and first["not_drawn"] is True
    assert surface.drawn(d, None, None, second=True)["not_drawn"] is True     # nothing pieced: says less


def test_the_second_form_draws_fine_patterns_past_sixteen_across():
    d = surface.read(_form(kind="plaid", size="micro", bands=[{"color": NAVY, "width": 1}, {"color": WHITE, "width": 1}]))
    assert surface.drawn(d, None, None, second=True)["repeats"] == pytest.approx(40.0)
    assert surface.drawn(d, None, None)["repeats"] == pytest.approx(4.0)       # the first form: no such word


def test_a_fine_stripe_is_read_at_the_photos_own_detail():
    cut = _striped_cut(period=8, size=(900, 1000))
    ruler = {"underarm_left": {"x": 100.0, "y": 300.0}, "underarm_right": {"x": 740.0, "y": 300.0}}   # 640 px: 80 repeats
    assert surface.fine_repeats(cut, ruler, across=False) == pytest.approx(80.0, rel=0.08)
    d = surface.read(_form(kind="stripes", direction="horizontal", size="tiny",
                           bands=[{"color": NAVY, "width": 2}, {"color": WHITE, "width": 3}]))
    out = surface.drawn(d, cut, ruler, second=True)
    assert out["scale_how"] == "fine" and out["repeats"] == pytest.approx(80.0, rel=0.08)
    assert surface.fine_repeats(_striped_cut(period=80), ruler, across=False) is None   # broad stripes: not fine
