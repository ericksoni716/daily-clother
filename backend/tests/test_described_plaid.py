"""A plaid drawn from a description of its bands (closet/patterns/described.py), used by the app through `patterns/surface.py`.
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
    # the form now asks for one list of bands (the same both ways) and a size word; the first form is still read
    answer = {"bands": TARTAN["across"], "size": "small"}
    model = described.PlaidDescription.model_validate(answer)
    assert described.read(model) == described.read(answer) == {**described.read(TARTAN), "repeats": 6.5}
    for size, repeats in described.SIZE_REPEATS.items():
        assert described.read({**answer, "size": size})["repeats"] == repeats
    assert described.read({**answer, "size": "enormous"})["repeats"] == 4.0     # an unknown word: a usual size
    for m in (described.PlaidDescription, described.Band):
        assert all(f.description for f in m.model_fields.values())
    assert "plaid" in described.FIELD_TEXT and len(described.GUIDANCE) < 300


def test_a_described_plaid_can_take_its_colours_from_the_photo():
    """Described in clean, strong colours; the photo's cloth is duller and browner. With the cutout, the repeat's
    average colour becomes the garment's, and the bands stay where they were described."""
    import base64
    import io

    import cv2
    import numpy as np
    from PIL import Image

    from closet.patterns import described
    desc = {"across": [{"color": "#3b3468", "width": 6}, {"color": "#d8c79c", "width": 2}], "down": [],
            "same_both_ways": True, "repeats_across_chest": 4}
    rng = np.random.default_rng(1)
    cloth = np.clip(rng.normal((120, 100, 90), 18, (200, 160, 3)), 0, 255).astype(np.uint8)
    cut = Image.fromarray(np.dstack([cloth, np.full((200, 160), 255, np.uint8)]), "RGBA")

    def pixels(kept):
        return np.asarray(Image.open(io.BytesIO(base64.b64decode(kept["image"]))).convert("RGB"))
    # round two: toning is no longer done whenever the cutout is passed (it is passed for the scale); it is asked for
    plain, toned = pixels(described.tile(desc, cut)), pixels(described.tile(desc, cut, tone=True))
    mean = lambda rgb: cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).reshape(-1, 3).mean(0)  # noqa: E731
    assert np.abs(mean(toned) - mean(cloth)).max() < 6 < np.abs(mean(plain) - mean(cloth)).max()
    light = lambda rgb: cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)[..., 0].astype(float).mean(0)  # noqa: E731
    assert np.corrcoef(light(plain), light(toned))[0, 1] > 0.95      # the same bands in the same places


# --- the scale read from the photo -------------------------------------------------------------------------

def _garment(p, q, size=(640, 720), body=(60, 40, 580, 690)):
    """A made-up garment: a plaid with a repeat p px across and q px down over a plain cutout outline."""
    across = _desc([(NAVY, 0.5 * p), (WHITE, 0.08 * p), (GREEN, 0.3 * p), (RED, 0.12 * p)])["across"]
    down = _desc([(NAVY, 0.5 * q), (WHITE, 0.08 * q), (GREEN, 0.3 * q), (RED, 0.12 * q)])["across"]
    rep = described.weave(described.read({"across": across, "down": down}))
    rep = cv2.resize(rep, (p, q), interpolation=cv2.INTER_AREA)
    W, H = size
    cloth = np.tile(rep, (H // q + 1, W // p + 1, 1))[:H, :W]
    alpha = np.zeros((H, W), np.uint8)
    x0, y0, x1, y1 = body
    alpha[y0:y1, x0:x1] = 255
    return Image.fromarray(np.dstack([cloth, alpha]), "RGBA")


UNDERARMS = {"underarm_left": {"x": 100.0, "y": 200.0}, "underarm_right": {"x": 520.0, "y": 200.0}}   # 420 px apart


def test_the_photo_settles_the_scale_when_its_repeat_is_square():
    reps, how = described.photo_repeats(_garment(70, 70), UNDERARMS)
    assert how == "across and down agree" and reps == pytest.approx(420 / 70, rel=0.06)


def test_when_across_and_down_disagree_the_spacing_down_is_used():
    reps, how = described.photo_repeats(_garment(60, 45), UNDERARMS)
    assert how == "down" and reps == pytest.approx(420 / 45, rel=0.06)


@pytest.mark.parametrize("marks", [None, {}, {"underarm_left": {"x": 1}},
                                   {"underarm_left": {"x": 300, "y": 200}, "underarm_right": {"x": 310, "y": 200}}])
def test_no_usable_underarms_leave_the_scale_to_the_description(marks):
    assert described.photo_repeats(_garment(70, 70), marks) is None


def test_a_plain_garment_says_nothing_about_scale():
    assert described.photo_repeats(Image.new("RGBA", (640, 720), (40, 50, 80, 255)), UNDERARMS) is None


def test_the_scale_from_the_photo_sizes_the_tile():
    raw = {"bands": [{"color": NAVY, "width": 8}, {"color": WHITE, "width": 1}], "size": "medium"}
    said, seen = described.tile(raw), described.tile(raw, _garment(70, 70), UNDERARMS)
    assert said["length_frac"] == pytest.approx(described.CHEST_PER_LENGTH / described.SIZE_REPEATS["medium"], rel=0.01)
    assert seen["length_frac"] == pytest.approx(described.CHEST_PER_LENGTH * 70 / 420, rel=0.07)
    assert seen["scale"] == "across and down agree" and said["scale"] == "said"


# --- the band widths from the photo ------------------------------------------------------------------------

TAN, PURPLE = "#c9b48a", "#4a3c7a"


def _cloth(bands, light=1.0, holes_of=None, size=(480, 560)):
    """A made-up photographed garment woven from `bands` [(hex, width)], its light multiplied by `light` (a dim
    photo); with `holes_of`, the pixels nearest that colour are cut out (a cutout that lost its white squares)."""
    rep = described.weave(described.read({"bands": [{"color": c, "width": w} for c, w in bands]}))
    rep = cv2.resize(rep, (90, 90), interpolation=cv2.INTER_AREA)
    W, H = size
    cloth = np.tile(rep, (H // 90 + 1, W // 90 + 1, 1))[:H, :W]
    alpha = np.full((H, W), 255, np.uint8)
    if holes_of is not None:
        target = np.array([int(holes_of[i:i + 2], 16) for i in (1, 3, 5)])
        alpha[np.abs(cloth.astype(int) - target).sum(2) < 60] = 0
    cloth = np.clip(cloth.astype(np.float32) * light, 0, 255).astype(np.uint8)
    return Image.fromarray(np.dstack([cloth, alpha]), "RGBA")


def _said(bands):
    return described.read({"bands": [{"color": c, "width": w} for c, w in bands], "size": "medium"})


def test_the_broad_colours_widths_are_recovered_from_the_photo():
    # woven half purple, half tan, with a red line; described with purple as a wide ground, in a dim photo
    truth = [(PURPLE, 9), (TAN, 9), (RED, 1)]
    got, shares = described.photo_widths(_said([(PURPLE, 12), (TAN, 6), (RED, 1)]), _cloth(truth, light=0.7))
    assert shares[PURPLE][0] == pytest.approx(12 / 19, abs=1e-3) and shares[TAN][0] == pytest.approx(6 / 19, abs=1e-3)
    assert shares[PURPLE][1] == pytest.approx(9 / 19, abs=0.04) and shares[TAN][1] == pytest.approx(9 / 19, abs=0.04)
    assert shares[RED][1] == shares[RED][0]                                # a line keeps its width
    assert [c for c, _ in got["across"]] == [PURPLE, TAN, RED]               # the order and colours stay
    assert got["across"] == got["down"]


def test_bands_of_one_colour_keep_their_proportions():
    said = _said([(PURPLE, 8), (TAN, 3), (PURPLE, 4), (TAN, 3)])
    got, _ = described.photo_widths(said, _cloth([(PURPLE, 6), (TAN, 6), (PURPLE, 3), (TAN, 6)]))
    a, b = sorted((w for c, w in got["across"] if c == PURPLE), reverse=True)
    assert a / b == pytest.approx(2.0)


def test_no_width_moves_more_than_the_cap():
    # the photo is mostly tan; the description says a thin tan band: tan grows, but only so far
    got, shares = described.photo_widths(_said([(PURPLE, 16), (TAN, 4)]), _cloth([(PURPLE, 3), (TAN, 17)]))
    assert 0.2 < shares[TAN][1] <= 0.2 * shares["cap"] + 1e-3 and shares["cap"] <= described.MOVE


def test_the_cap_follows_how_much_better_the_photo_explains_the_cloth():
    truth = [(PURPLE, 9), (TAN, 9), (RED, 1)]
    _, right = described.photo_widths(_said(truth), _cloth(truth))           # already right: nothing to gain
    _, wrong = described.photo_widths(_said([(PURPLE, 15), (TAN, 3), (RED, 1)]), _cloth(truth))
    assert right[PURPLE][1] == pytest.approx(right[PURPLE][0], abs=0.04)     # little to gain, little moved
    assert wrong["cap"] > right["cap"] and wrong["cap"] > 2.0 and wrong[TAN][1] > 1.8 * wrong[TAN][0]


def test_a_cutout_that_lost_a_colour_cannot_take_it_away():
    # the white squares were cut out with the background: the cutout is full of holes, so its colours are not counted
    said = _said([(NAVY, 10), (WHITE, 8), (RED, 2)])
    cut = _cloth([(NAVY, 10), (WHITE, 8), (RED, 2)], holes_of=WHITE)
    assert described.holes(np.asarray(cut)[..., 3]) > described.HOLES
    assert described.photo_widths(said, cut) is None
    assert described.holes(np.asarray(_cloth([(NAVY, 10), (WHITE, 8)]))[..., 3]) == 0


@pytest.mark.parametrize("case", ["one colour", "no garment", "colours that are not there"])
def test_the_widths_stay_as_described_when_the_photo_cannot_say(case):
    said = _said([(PURPLE, 9), (TAN, 9), (RED, 2)])
    if case == "one colour":
        said, cut = {"across": [(PURPLE, 9.0)], "down": [(PURPLE, 9.0)]}, _cloth([(PURPLE, 9), (TAN, 9)])
        assert described.photo_widths(said, cut) is None
        return
    if case == "no garment":
        cut = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    else:   # bright green and magenta checks for a purple and tan description
        cut = _cloth([("#10e020", 9), ("#f010d0", 9)])
    assert described.photo_widths(said, cut) is None
    kept = described.tile({"bands": [{"color": c, "width": w} for c, w in said["across"]]}, cut, widths=True)
    assert kept["widths"] == "said"


def test_widths_from_the_photo_are_an_option_of_the_tile():
    raw = {"bands": [{"color": PURPLE, "width": 12}, {"color": TAN, "width": 6}, {"color": RED, "width": 1}]}
    cut = _cloth([(PURPLE, 9), (TAN, 9), (RED, 1)])
    # round four: on by default, as recommended (see DECISIONS)
    assert described.tile(raw, cut)["widths"] == "photo"
    assert described.tile(raw)["widths"] == "said"
    assert described.tile(raw, cut, widths=False)["widths"] == "said"


def test_the_ground_is_the_broadest_colour_whatever_was_listed_first():
    assert described._ground_first([(RED, 1), (TAN, 3), (PURPLE, 4), (TAN, 5)]) == [(TAN, 5), (RED, 1), (TAN, 3), (PURPLE, 4)]
    got, _ = described.photo_widths(_said([(TAN, 6), (PURPLE, 12), (RED, 1)]), _cloth([(PURPLE, 9), (TAN, 9), (RED, 1)]))
    totals = {c: sum(w for c2, w in got["across"] if c2 == c) for c in (PURPLE, TAN)}
    assert got["across"][0][0] == max(totals, key=totals.get)


def test_nearly_alike_yarns_are_drawn_as_one_colour():
    said = _said([(PURPLE, 8), (TAN, 4), ("#4d3e7c", 3), (RED, 1)])    # two purples a shade apart
    got, _ = described.photo_widths(said, _cloth([(PURPLE, 11), (TAN, 4), (RED, 1)]))
    assert len({c for c, _ in got["across"]}) == 3


def test_hues_move_toward_the_photo_only_when_asked():
    said = _said([(PURPLE, 9), (TAN, 9), (RED, 1)])
    cut = _cloth([("#5a3c8a", 9), (TAN, 9), (RED, 1)])                  # the cloth's purple is redder
    kept, _ = described.photo_widths(said, cut)
    moved, _ = described.photo_widths(said, cut, hues=1.0)
    assert PURPLE in {c for c, _ in kept["across"]} and PURPLE not in {c for c, _ in moved["across"]}
    new = next(c for c, _ in moved["across"] if c not in (TAN, RED))
    assert _lab(new)[1] > _lab(PURPLE)[1]                               # toward the redder purple


def test_colours_are_softened_by_default_keeping_lightness_and_hue():
    desc = described.softened(described.read(TARTAN), 0.5)
    for (c0, w0), (c1, w1) in zip(described.read(TARTAN)["across"], desc["across"], strict=True):
        a, b = _lab(c0) - [0, 128, 128], _lab(c1) - [0, 128, 128]
        assert w0 == w1 and abs(a[0] - b[0]) <= 2 and np.hypot(*b[1:]) == pytest.approx(0.5 * np.hypot(*a[1:]), abs=2)
    strong, soft = (_image(described.tile(TARTAN, strength=s)) for s in (1.0, described.STRENGTH))
    chroma = lambda rgb: np.hypot(*(cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)[..., 1:].astype(float) - 128).transpose(2, 0, 1)).mean()  # noqa: E731
    assert chroma(soft) < chroma(strong)
