"""The bench's own code: the phase 0 fills it still uses and the scoring of tagger answers. The tests of the
app's tagger and drawing are in `backend/tests/test_templates_and_tagger.py`."""
import numpy as np
import pytest
from PIL import Image, ImageDraw

from closet_bench import fills, tagging
from closet_bench.bench import compare, summarize
from closet_bench.illustrate import Fill, Spec, render
from closet_bench.schema import Details, ItemTags, Silhouette


def make_tags(**kw):
    base = dict(category="shirt", category_confidence=0.9, color="blue", color_confidence=0.8, pattern="plaid",
                pattern_confidence=0.95, formality="casual", formality_confidence=0.6, season="cool",
                season_confidence=0.5, silhouette=Silhouette.of(sleeve="long", neck="collar"), silhouette_confidence=0.7)
    base.update(secondary_colors=[], brand=None, size=None, material=None, needs_shot=None)
    base.update(details=Details.plain(sleeve_length="long", collar="point", placket="front_placket", placket_buttons=7,
                                      cuff="barrel_1", hem="curved_shirt_tail"), details_confidence=0.8)
    base.update(kw)
    return ItemTags(**base)


def garment(size=(400, 500), color=(200, 60, 60)):
    """A plain rectangle of cloth on a transparent background."""
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(im).rectangle((40, 40, size[0] - 40, size[1] - 40), fill=color + (255,))
    return im


# ---- fills (the bench's own: the app no longer uses these)

def test_dominant_colour_of_plain_cloth():
    (hex_, share), *_ = fills.dominant_colors(garment(color=(200, 60, 60)))
    r, g, b = (int(hex_[i:i + 2], 16) for i in (1, 3, 5))
    assert abs(r - 200) < 12 and abs(g - 60) < 12 and abs(b - 60) < 12 and share > 0.9


def test_shadowed_white_is_one_colour_family_and_snaps_to_white():
    im = garment(color=(235, 235, 235))
    px = np.asarray(im).copy()
    ramp = np.linspace(235, 175, 250).astype(np.uint8)[:, None, None]  # lower half falls into shade
    px[250:, :, :3] = np.where(px[250:, :, 3:] > 0, ramp, 0)
    (hex_, share), *_ = fills.dominant_colors(Image.fromarray(px, "RGBA"))
    assert share > 0.9
    snapped = fills.snap_to_named(hex_, "white")
    assert all(int(snapped[i:i + 2], 16) >= 232 for i in (1, 3, 5))
    assert fills.snap_to_named("#6a8fd0", "blue") == "#6a8fd0"


def test_stripes_are_measured_from_the_photo():
    im = garment()
    px = np.asarray(im).copy()
    for y in range(40, 460):
        px[y, 40:360, :3] = (20, 30, 90) if ((y - 40) // 20) % 2 == 0 else (240, 240, 235)
    st = fills.measure_stripes(Image.fromarray(px, "RGBA"), "horizontal", 2)
    assert len(st.bands) == 2
    for _, width in st.bands:
        assert abs(width * 500 - 20) <= 3


def test_stripe_measurement_does_not_depend_on_previous_random_state():
    import cv2

    colours = np.array([[197, 77, 130], [169, 72, 49], [139, 155, 193], [44, 141, 81], [58, 107, 206]],
                       dtype=np.uint8)
    pixels = np.full((200, 100, 4), 255, dtype=np.uint8)
    pixels[:, :, :3] = colours[(np.arange(200) // 10) % len(colours), None, :]
    cutout = Image.fromarray(pixels)
    drawings = []
    for seed in (0, 1, 2, 3):
        cv2.setRNGSeed(seed)
        stripes = fills.measure_stripes(cutout)
        drawings.append(render(Spec("top", {}, Fill("stripes", "#888888", stripes=stripes)), "line"))
    assert all(svg == drawings[0] for svg in drawings)


def test_plaid_swatch_finds_the_repeat():
    yy, xx = np.mgrid[0:500, 0:400]
    plaid = np.stack([120 + 80 * np.sin(xx * 2 * np.pi / 40), 120 + 80 * np.sin(yy * 2 * np.pi / 50),
                      np.full_like(xx, 90, dtype=float)], -1).astype(np.uint8)
    alpha = np.zeros((500, 400), np.uint8)
    alpha[40:460, 40:360] = 255
    sw = fills.pick_swatch(Image.fromarray(np.dstack([plaid, alpha]), "RGBA"))
    assert sw.method == "periodic"
    assert sw.period[0] % 40 in (0, 1, 39) and sw.period[1] % 50 in (0, 1, 49)


def test_organic_swatch_wraps_without_a_seam():
    rng = np.random.default_rng(1)
    noise = cv2_blur(rng.integers(0, 255, (500, 400, 3)).astype(np.uint8))
    alpha = np.zeros((500, 400), np.uint8)
    alpha[40:460, 40:360] = 255
    sw = fills.pick_swatch(Image.fromarray(np.dstack([noise, alpha]), "RGBA"), organic=True)
    assert sw.method == "fade"
    t = np.asarray(sw.image).astype(float)
    seam = np.abs(t[:, 0] - t[:, -1]).mean()      # across the wrap
    inside = np.abs(t[:, 1:] - t[:, :-1]).mean()  # between ordinary neighbours
    assert seam < 2.5 * inside


def cv2_blur(a):
    import cv2
    return cv2.GaussianBlur(a, (0, 0), 6)


# ---- scoring the bench's answers

def test_compare_skips_blank_key_cells_and_scores_silhouette():
    out = compare(make_tags(), dict(category="shirt", color="navy", pattern="", sleeve="long", neck="crew"))
    assert set(out) == {"category", "color", "sleeve", "neck"}
    assert out["category"]["correct"] and not out["color"]["correct"]
    assert out["sleeve"]["correct"] and not out["neck"]["correct"]


def test_summary_reports_accuracy_and_calibration():
    rows = [{"color": dict(correct=True, confidence=0.95, got="blue", want="blue")}] * 8 + \
           [{"color": dict(correct=False, confidence=0.95, got="blue", want="navy")}] * 2
    s = summarize(rows)["color"]
    assert s["n"] == 10 and s["accuracy"] == pytest.approx(0.8)
    assert s["calibration_gap"] == pytest.approx(0.15)
    assert s["bins"][-1]["n"] == 10 and s["bins"][0]["n"] == 0


def test_recorded_answers_are_validated_like_live_ones(tmp_path):
    from closet_bench.bench import recorded_tagger
    (tmp_path / "m").mkdir()
    (tmp_path / "m" / "a.json").write_text(make_tags().model_dump_json())
    (tmp_path / "m" / "b.json").write_text('{"category": "spaceship"}')
    tag = recorded_tagger(tmp_path)
    assert tag("m", "a.jpg", []).tags.pattern == "plaid"
    with pytest.raises(tagging.TaggingError, match="does not fit the schema"):
        tag("m", "b.jpg", [])
    with pytest.raises(tagging.TaggingError, match="no recorded answer"):
        tag("m", "c.jpg", [])
