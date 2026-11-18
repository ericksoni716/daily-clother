"""A plaid drawn from a description of its bands (closet/patterns/described.py), an experiment not yet in the app.
Made-up descriptions only, no photos."""
import base64
import io

import cv2
import numpy as np
import pytest
from PIL import Image

from closet.drawing import item as draw
from closet.drawing import stored
from closet.drawing.templates import build
from closet.patterns import described

NAVY, WHITE, RED, GREEN = "#1f2a44", "#f2f0ea", "#b3262e", "#2f5a3c"


def _desc(across, down=(), same=True, repeats=4.0):
    return {"across": [{"color": c, "width": w} for c, w in across], "down": [{"color": c, "width": w} for c, w in down],
            "same_both_ways": same, "repeats_across_chest": repeats}


TARTAN = _desc([(NAVY, 16), (GREEN, 8), (WHITE, 2), (GREEN, 6), (RED, 4)])   # 36 units: 10 px each on a 360 px tile


def _lab(hex_or_rgb):
    rgb = np.array([[int(hex_or_rgb[i:i + 2], 16) for i in (1, 3, 5)]], np.uint8) if isinstance(hex_or_rgb, str) \
        else np.asarray(hex_or_rgb, np.uint8).reshape(1, 3)
    return cv2.cvtColor(rgb[None], cv2.COLOR_RGB2LAB)[0, 0].astype(float)


def _image(kept):
    return np.asarray(Image.open(io.BytesIO(base64.b64decode(kept["image"]))).convert("RGB"))


def test_the_tile_repeats_seamlessly():
    # the same plaid listed from its second band on is the same cloth, shifted: the seam is like any other spot
    img = described.weave(described.read(TARTAN))
    turned = described.weave(described.read(_desc([(GREEN, 8), (WHITE, 2), (GREEN, 6), (RED, 4), (NAVY, 16)])))
    assert img.shape == turned.shape == (360, 360, 3)
    assert np.abs(np.roll(img, (-160, -160), (0, 1)).astype(int) - turned.astype(int)).max() <= 2
    # and the edge columns meet as smoothly as neighbouring columns inside the tile do
    cols = img.astype(float)
    seam = np.abs(cols[:, 0] - cols[:, -1]).mean()
    inside = np.abs(np.diff(cols, axis=1)).mean(axis=(0, 2))
    assert seam <= inside.max()


def test_the_described_colours_in_the_described_proportions():
    desc = described.read(TARTAN)
    seq = described._sequence(desc["across"], 360, 10)
    names = [NAVY, GREEN, WHITE, RED]
    labs = np.array([_lab(h) for h in names])
    nearest = np.argmin(((seq[:, None, :] - labs[None]) ** 2).sum(2), 1)
    shares = np.bincount(nearest, minlength=4) / 360
    assert shares == pytest.approx([16 / 36, 14 / 36, 2 / 36, 4 / 36], abs=0.02)
    img = described.weave(desc)
    # where navy crosses navy the cloth is navy; where navy crosses white it is the two yarns mixed
    navy_block = img[30:50, 30:50].reshape(-1, 3).mean(0)
    assert np.abs(_lab(navy_block.round()) - _lab(NAVY)).max() < 4
    mixed = cv2.cvtColor(img[30:46, 245:251].astype(np.uint8), cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(float).mean(0)
    assert np.abs(mixed - (_lab(NAVY) + _lab(WHITE)) / 2).max() < 6


def test_same_both_ways_and_a_repeat_that_differs_down():
    sym = described.weave(described.read({**TARTAN, "down": [{"color": RED, "width": 3}]}))   # down ignored
    # a twill tips each spot one way along the warp and the other along the weft, so compare the colours without it
    def smooth(im):
        k = described.STEP
        return cv2.blur(np.pad(im, ((k, k), (k, k), (0, 0)), mode="wrap").astype(np.float32), (k, k))[k:-k, k:-k]
    assert described.read({**TARTAN, "down": [{"color": RED, "width": 3}]})["down"] == described.read(TARTAN)["across"]
    assert np.abs(smooth(sym) - smooth(sym.transpose(1, 0, 2))).max() <= 4
    tall = described.read(_desc([(NAVY, 6), (WHITE, 2)], [(NAVY, 9), (WHITE, 3)], same=False))
    assert tall["down"] == [(NAVY, 9.0), (WHITE, 3.0)]
    img = described.weave(tall)
    assert img.shape[0] > img.shape[1] and img.shape[0] / img.shape[1] == pytest.approx(1.5, abs=0.05)
    # not the same both ways but nothing listed down: the same bands down
    assert described.read(_desc([(NAVY, 6), (WHITE, 2)], same=False))["down"] == [(NAVY, 6.0), (WHITE, 2.0)]


def test_the_repeat_is_sized_by_the_repeats_across_the_chest():
    two, four = described.tile({**TARTAN, "repeats_across_chest": 2}), described.tile({**TARTAN, "repeats_across_chest": 4})
    assert two["width_frac"] == pytest.approx(2 * four["width_frac"], rel=0.01)
    assert two["length_frac"] == pytest.approx(described.CHEST_PER_LENGTH / 2, rel=0.01)
    assert described.tile({**TARTAN, "repeats_across_chest": 1000})["length_frac"] == pytest.approx(
        described.CHEST_PER_LENGTH / described.REPEATS[1], rel=0.01)
    assert described.tile({**TARTAN, "repeats_across_chest": float("nan")})["length_frac"] == four["length_frac"]
    # the sizes are the drawn shirt's own: its chest against its length and against its outline with long sleeves
    template, params, _, _ = draw.drawing_for(draw._plain("shirt", {"sleeve": "long", "neck": "collar"}, {}))
    shape = build(template, params)
    chest = shape.body_box[2] - shape.body_box[0]
    assert chest / (shape.anchors["hem"][1] - shape.anchors["neck"][1]) == pytest.approx(described.CHEST_PER_LENGTH, rel=0.05)
    assert chest / (shape.bbox[2] - shape.bbox[0]) == pytest.approx(described.CHEST_PER_OUTLINE, rel=0.08)


def test_a_described_plaid_is_kept_and_drawn_as_a_measured_one_is():
    kept = described.tile(TARTAN)
    assert kept["kind"] == "tile" and kept["how"] == "described" and kept["version"] == stored.VERSION
    assert kept["phase"] == pytest.approx([8 / 36, 8 / 36], abs=1e-3)   # the widest band's middle on the buttons
    fill = stored.fill_from(kept, NAVY)
    assert fill is not None and fill.kind == "swatch" and fill.swatch.length_frac == kept["length_frac"]
    d = draw.drawing_from_fields("shirt", NAVY, "plaid", {"sleeve": "long", "neck": "collar"}, fill=fill)
    assert d.svg and "<image" in d.svg and not d.not_drawn
    assert _image(kept).shape == (360, 360, 3)


@pytest.mark.parametrize("raw", [
    None, "plaid", [], {},
    _desc([]),                                           # no bands
    _desc([(NAVY, 0), (WHITE, -2)]),                     # no width
    _desc([("navy", 3), ("#12345", 2), (None, 1)]),      # no readable colour
    _desc([(NAVY, 3), (NAVY, 2)]),                       # one colour: no plaid
    {"across": [{"color": NAVY}], "down": "x", "same_both_ways": True, "repeats_across_chest": 3},
])
def test_odd_descriptions_draw_nothing(raw):
    assert described.read(raw) is None and described.tile(raw) is None


def test_odd_bands_are_made_safe():
    desc = described.read(_desc([(NAVY, 6), ("#fff", 1), ("blue", 2), (WHITE, 0), ("#B3262E", float("inf")),
                                 (RED, "2"), ("1f2a44", 1)], repeats="lots"))
    # the short hex is read, words, no width and an endless width are dropped; the last navy wraps round onto the first
    assert desc["across"] == [(NAVY, 7.0), ("#ffffff", 1.0), (RED, 2.0)]
    assert desc["repeats"] == 4.0
    many = described.read(_desc([(NAVY if i % 2 else WHITE, 1) for i in range(101)]))
    assert len(many["across"]) == described.MAX_BANDS
    # a line too thin to draw is dropped
    assert described.read(_desc([(NAVY, 1000), (WHITE, 1), (RED, 10)]))["across"] == [(NAVY, 1000.0), (RED, 10.0)]


def test_the_form_reads_an_answer_and_every_field_is_described():
    model = described.PlaidDescription.model_validate(TARTAN)
    assert described.read(model) == described.read(TARTAN)
    for m in (described.PlaidDescription, described.Band):
        assert all(f.description for f in m.model_fields.values())
    assert "plaid" in described.FIELD_TEXT and len(described.GUIDANCE) < 1200
