import io
import xml.dom.minidom

import numpy as np
import pytest
from PIL import Image, ImageDraw

from closet_bench import fills, tagging
from closet_bench.bench import compare, summarize
from closet_bench.illustrate import STYLES, Fill, Spec, render
from closet_bench.schema import ItemTags, Silhouette, silhouette_params
from closet_bench.templates import PANTS_DEFAULTS, SNEAKER_DEFAULTS, TOP_DEFAULTS, build


def make_tags(**kw):
    base = dict(category="shirt", category_confidence=0.9, color="blue", color_confidence=0.8, pattern="plaid",
                pattern_confidence=0.95, formality="casual", formality_confidence=0.6, season="cool",
                season_confidence=0.5, silhouette=Silhouette(sleeve="long", neck="collar"), silhouette_confidence=0.7)
    base.update(kw)
    return ItemTags(**base)


def garment(size=(400, 500), color=(200, 60, 60)):
    """A plain rectangle of cloth on a transparent background."""
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(im).rectangle((40, 40, size[0] - 40, size[1] - 40), fill=color + (255,))
    return im


# ---- templates and rendering

@pytest.mark.parametrize("template,options", [
    ("top", dict(sleeve=["none", "short", "long"], neck=["crew", "v", "collar", "hood", "turtle"], length=["cropped", "regular", "long"],
                 fit=["slim", "regular", "oversized"], front=["none", "buttons", "zip"], pockets=["none", "chest", "low", "chest-low"],
                 hem=["straight", "curved", "rib"], cuffs=["plain", "rib", "button"])),
    ("pants", dict(leg=["tapered", "straight", "wide"], length=["short", "ankle", "full"], jeans=[False, True])),
    ("sneaker", dict(height=["low", "high"], sole=["thin", "regular", "chunky"])),
])
def test_every_parameter_value_draws_valid_svg(template, options):
    for name, values in options.items():
        for v in values:
            spec = Spec(template, {name: v}, Fill("solid", "#336699"))
            for style in ("flat", "line", "soft"):
                svg = render(spec, style)
                xml.dom.minidom.parseString(svg)
                assert "nan" not in svg.lower()


def test_defaults_cover_the_documented_vocabulary():
    assert set(TOP_DEFAULTS) == {"sleeve", "neck", "length", "fit", "front", "pockets", "hem", "cuffs"}
    assert set(PANTS_DEFAULTS) == {"leg", "length", "jeans"}
    assert set(SNEAKER_DEFAULTS) == {"height", "sole"}


def test_a_correction_changes_the_drawing_and_nothing_else_does():
    straight = build("pants", dict(leg="straight")).outline
    assert build("pants", dict(leg="straight")).outline == straight  # deterministic
    assert build("pants", dict(leg="tapered")).outline != straight


def test_tops_share_anchor_points_across_parameters():
    a = build("top", dict(sleeve="short")).anchors
    b = build("top", dict(sleeve="long", neck="collar", front="buttons")).anchors
    assert a["neck"] == b["neck"] and a["shoulder_l"] == b["shoulder_l"]


def test_traced_style_follows_the_cutout():
    svg = render(Spec("top", {}, Fill("solid", "#336699")), "traced", cutout=garment())
    xml.dom.minidom.parseString(svg)
    assert set(STYLES) == {"flat", "line", "soft", "traced"}


# ---- fills

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


def test_plaid_swatch_finds_the_repeat():
    yy, xx = np.mgrid[0:500, 0:400]
    plaid = np.stack([120 + 80 * np.sin(xx * 2 * np.pi / 40), 120 + 80 * np.sin(yy * 2 * np.pi / 50),
                      np.full_like(xx, 90, dtype=float)], -1).astype(np.uint8)
    alpha = np.zeros((500, 400), np.uint8)
    alpha[40:460, 40:360] = 255
    sw = fills.pick_swatch(Image.fromarray(np.dstack([plaid, alpha]), "RGBA"))
    assert sw.method == "periodic"
    assert sw.period[0] % 40 in (0, 1, 39) and sw.period[1] % 50 in (0, 1, 49)


def test_graphic_is_lifted_with_transparent_background():
    im = garment(color=(240, 238, 230))
    ImageDraw.Draw(im).rectangle((160, 200, 240, 260), fill=(20, 20, 20, 255))
    g = fills.extract_graphic(im)
    assert g is not None
    x0, y0, x1, y1 = g.box
    assert abs(x0 - 160) < 12 and abs(x1 - 240) < 12 and abs(y0 - 200) < 12 and abs(y1 - 260) < 12
    a = np.asarray(g.image)[..., 3]
    assert a[a.shape[0] // 2, a.shape[1] // 2] == 255
    assert fills.extract_graphic(garment(color=(240, 238, 230))) is None


# ---- tagging output validation and scoring

class FakeMessages:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), 0

    def parse(self, **kw):
        self.calls += 1
        assert kw["output_format"] is ItemTags
        return self.replies.pop(0)


class Reply:
    def __init__(self, parsed, stop_reason="end_turn"):
        self.parsed_output, self.stop_reason = parsed, stop_reason
        self.usage = type("U", (), {"input_tokens": 1500, "output_tokens": 300})()


class FakeClient:
    def __init__(self, replies):
        self.messages = FakeMessages(replies)


def test_schema_rejects_values_outside_the_vocabulary():
    with pytest.raises(Exception):
        make_tags(category="spaceship")
    with pytest.raises(Exception):
        make_tags(color_confidence=1.4)


def test_tagging_retries_an_incomplete_answer_then_succeeds():
    client = FakeClient([Reply(None, "max_tokens"), Reply(make_tags())])
    r = tagging.tag_item(client, "claude-haiku-5-5", [garment()])
    assert r.attempts == 2 and r.tags.category == "shirt"
    assert r.cost_usd == pytest.approx((3000 * 0.10 + 600 * 0.50) / 1e6)


def test_tagging_fails_clearly_when_no_valid_answer_arrives():
    with pytest.raises(tagging.TaggingError, match="no valid answer after 3 attempts"):
        tagging.tag_item(FakeClient([Reply(None)] * 3), "claude-haiku-5-5", [garment()])
    with pytest.raises(tagging.TaggingError, match="declined"):
        tagging.tag_item(FakeClient([Reply(None, "refusal")]), "claude-haiku-5-5", [garment()])


def test_cutout_is_sent_as_an_opaque_jpeg():
    block = tagging.encode_image(garment())
    assert block["source"]["media_type"] == "image/jpeg"
    import base64
    assert Image.open(io.BytesIO(base64.b64decode(block["source"]["data"]))).mode == "RGB"


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


def test_tags_map_to_template_parameters():
    assert silhouette_params(make_tags())[0] == "top"
    t, p = silhouette_params(make_tags(category="jeans", silhouette=Silhouette(leg="tapered")))
    assert (t, p["leg"], p["jeans"]) == ("pants", "tapered", True)
    assert silhouette_params(make_tags(category="sneakers", silhouette=Silhouette()))[0] == "sneaker"


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
