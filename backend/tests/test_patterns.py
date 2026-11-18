"""The pattern measurements (closet/patterns) on made-up cloth, where the right answer is known. No photos."""
import cv2
import numpy as np
import pytest
from PIL import Image

from closet.patterns import common, flatten, masks, plaid, prints, stripes

# --- a made-up crumpled plaid ------------------------------------------------------------------------------

P, Q = 40, 48
NAVY, WHITE, BURGUNDY, GREY, RED = (35, 45, 75), (240, 240, 235), (110, 30, 45), (120, 120, 120), (200, 30, 40)


def _truth_tile():
    warp = np.zeros(P, int)
    weft = np.zeros(Q, int)
    warp[:14] = 1
    warp[14:16] = 2
    warp[22:30] = 3
    warp[33] = 2
    weft[:12] = 1
    weft[12:14] = 2
    weft[20:32] = 3
    weft[40] = 2
    cols = np.array([GREY, NAVY, WHITE, BURGUNDY], np.float32)
    return (cols[warp][None, :, :] + cols[weft][:, None, :]) / 2


TRUTH = _truth_tile()


def _crumpled_plaid(H=700, W=600):
    """The true repeat seen through a slight turn and slow waves (crumpling), with noise, on a transparent
    background."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    ang = np.radians(4)
    u = (np.cos(ang) * xx + np.sin(ang) * yy) + 6 * np.sin(yy / 90) + 4 * np.sin(xx / 130)
    v = (-np.sin(ang) * xx + np.cos(ang) * yy) + 5 * np.sin(xx / 110) + 3 * np.cos(yy / 70)
    big = np.tile(TRUTH, (H // Q + 40, W // P + 40, 1))
    off = 20
    img = np.dstack([cv2.remap(big[..., c], (u % P + off * P).astype(np.float32),
                               (v % Q + off * Q).astype(np.float32), cv2.INTER_LINEAR) for c in range(3)])
    img += np.random.default_rng(0).normal(0, 6, img.shape)
    alpha = np.zeros((H, W), np.uint8)
    alpha[40:660, 60:540] = 255
    return Image.fromarray(np.dstack([np.clip(img, 0, 255).astype(np.uint8), alpha]), "RGBA")


def _best_shift_error(tile, truth):
    """Mean colour error (0-255) against the truth at the best cyclic shift."""
    return min(np.abs(np.roll(np.roll(tile, dy, 0), dx, 1) - truth).mean()
               for dy in range(truth.shape[0]) for dx in range(truth.shape[1]))


@pytest.fixture(scope="module")
def crumpled():
    cut = _crumpled_plaid()
    tile_lab, info = flatten.rectify(cut, P, Q)
    return cut, tile_lab, info


def test_period_finds_the_repeat():
    per = plaid.period(_crumpled_plaid())
    assert per is not None
    assert abs(per[0] - P) <= 1 and abs(per[1] - Q) <= 1


def test_rectify_recovers_the_repeat(crumpled):
    cut, tile_lab, info = crumpled
    assert tile_lab.shape[:2] == (Q, P)
    assert info["ox"].shape == (cut.height, cut.width)
    rec = cv2.resize(common.lab_to_rgb(tile_lab), (P, Q), interpolation=cv2.INTER_AREA).astype(np.float32)
    flat = _best_shift_error(rec, TRUTH)
    naive = _best_shift_error(np.asarray(cut.convert("RGB"))[300:300 + Q, 250:250 + P].astype(np.float32), TRUTH)
    assert flat < 0.75 * naive, (flat, naive)


def test_match_front_places_the_repeat(crumpled):
    cut, tile_lab, info = crumpled
    lm = {"button_line": [{"x": 300, "y": y} for y in (150, 250, 350, 450, 550)],
          "neck_center": {"x": 300, "y": 60}, "hem_center": {"x": 300, "y": 640}}
    phase, length_frac, anchor = plaid.placed_from_landmarks(info, P, Q, lm)
    assert 0 <= phase[0] < 1 and 0 <= phase[1] < 1
    assert length_frac == pytest.approx(P / 580)
    assert anchor == pytest.approx((300, 150 + plaid.PLACE_AT * 400))
    for side in (+1, -1):
        res = plaid.match_front(cut, tile_lab, P, Q, anchor, side)
        assert res is not None
        (u, v), held_off, score = res
        assert 0 <= u < 1 and 0 <= v < 1
        assert max(held_off) <= 4, held_off
        assert score > 0.5
    check = plaid.check_placement(cut, tile_lab, info, P, Q, anchor, phase)
    # through the flattening map alone the placement is close but not exact (why match_front exists)
    assert check["rank"] <= 0.05 * check["of"] and max(check["off_px"]) <= 8, check


# --- stripes ------------------------------------------------------------------------------------------------

def _cut(rgb, box):
    y0, y1, x0, x1 = box
    alpha = np.zeros(rgb.shape[:2], np.uint8)
    alpha[y0:y1, x0:x1] = 255
    return Image.fromarray(np.dstack([rgb, alpha]), "RGBA")


def test_measure4_vertical_stripes():
    H, W, period, dark_w = 420, 360, 18, 6
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    pos = (xx + 2.5 * np.sin(yy / 45)) % period          # a slight wave down the garment
    rgb = np.where((pos < dark_w)[..., None], np.array(NAVY, np.float32), np.array(WHITE, np.float32))
    rgb += np.random.default_rng(1).normal(0, 4, rgb.shape)
    cut = _cut(np.clip(rgb, 0, 255).astype(np.uint8), (30, 390, 30, 330))
    res = stripes.measure4(cut)
    assert res["orientation"] == "vertical"
    lab = {h: cv2.cvtColor(np.array([[[int(h[i:i + 2], 16) for i in (1, 3, 5)]]], np.uint8),
                           cv2.COLOR_RGB2LAB)[0, 0].astype(float) for h in res["yarns"]}
    truth = cv2.cvtColor(np.array([[NAVY, WHITE]], np.uint8), cv2.COLOR_RGB2LAB)[0].astype(float)
    assert len(res["yarns"]) == 2
    for t in truth:
        assert min(np.linalg.norm(c - t) for c in lab.values()) < 12
    # widths: the dark stripes take dark_w / period of the garment
    dark = min(lab, key=lambda h: lab[h][0])
    share = sum(f for h, f in res["bands"] if h == dark)
    assert share == pytest.approx(dark_w / period, abs=0.05)


def _placed_stripes(H=400, W=300, band=(170, 220)):
    """Fine ground stripes across (2 px navy in about every 6, the spacing breathing a little as real cloth does)
    with one wide red band."""
    y = np.arange(H, dtype=float)
    u = y + 1.5 * np.sin(y / 29)
    rgb = np.where((u % 6 < 2)[:, None, None], np.array(NAVY, np.float32), np.array(WHITE, np.float32))
    rgb = np.repeat(rgb, W, 1)
    rgb[band[0]:band[1]] = RED
    rgb += np.random.default_rng(2).normal(0, 3, rgb.shape)
    return _cut(np.clip(rgb, 0, 255).astype(np.uint8), (20, 380, 30, 270))


def _colour_at(bands, frac):
    edges = np.cumsum([0] + [f for _, f in bands])
    h = bands[int(np.searchsorted(edges, frac, side="right") - 1)][0]
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def test_placed_stripes_keep_the_band():
    cut = _placed_stripes()
    ground = stripes.ground_stripes(cut)
    assert ground is not None
    assert ground["orientation"] == "horizontal"
    assert ground["L"] == pytest.approx(6, abs=0.5)
    assert 150 <= ground["region"][0] and ground["region"][1] - ground["region"][0] > 80   # below the band
    dark, light = (np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)]) for h in ground["hexes"])
    assert np.abs(dark - NAVY).max() < 20 and np.abs(light - WHITE).max() < 20
    # the body's bands as measure3 gives them for a placed band (the whole sequence, no repeat): here written
    # out by hand, ground grey everywhere but the band, so only compose_placed itself is tested
    span = 360
    body = {"orientation": "horizontal",
            "bands": [("#999999", 150 / span), ("#c81e28", 50 / span), ("#999999", 160 / span)]}
    bands = stripes.compose_placed(cut, body, ground)
    assert sum(f for _, f in bands) == pytest.approx(1, abs=0.01)
    assert _colour_at(bands, (195 - 20) / span) == (0xc8, 0x1e, 0x28)         # the band, at the band's height
    # elsewhere the crisp ground repeat: both ground colours, in stripes about 6 px apart
    above = [h for h, f in bands[:len(bands) // 3]]
    assert set(above) == set(ground["hexes"])
    n_above = sum(1 for (h, _), a in zip(bands, np.cumsum([0] + [f for _, f in bands])[:-1], strict=True)
                  if a * span < 130 and h == ground["hexes"][0])
    assert n_above == pytest.approx(130 / 6, abs=3)
    band_lab, ground_lab = stripes.band_colours(["#f0f2ec", "#c82028", "#242c4b"], ground["hexes"])
    assert band_lab is not None and len(band_lab) == 1


def test_placed_band_survives_when_the_body_measures_as_a_repeat():
    """On a sharp photo measure4 folds a regular ground into one repeat and loses the band; compose_placed must
    then read the band from the photo itself."""
    cut = _placed_stripes()
    ground = stripes.ground_stripes(cut)
    body = {"orientation": "horizontal", "bands": [(ground["hexes"][0], 0.5), (ground["hexes"][1], 0.5)],
            "yarns": list(ground["hexes"]) + ["#c81e28"], "rep": np.zeros((4, 3))}
    bands = stripes.compose_placed(cut, body, ground)
    span = 360
    r, g, b = _colour_at(bands, (195 - 20) / span)
    assert r > 150 and g < 80 and b < 80        # red at the band's height


# --- sleeves -----------------------------------------------------------------------------------------------

def _t_shirt(band_on_sleeves):
    """A T shape: body 160-340 across, 100-500 down; sleeves 60-440 across, 100-200 down. A red band across the
    chest (rows 140-170), on the body only or across the sleeves too, on a pale grey ground."""
    H, W = 560, 500
    rgb = np.full((H, W, 3), 225, np.float32)
    x0, x1 = (60, 440) if band_on_sleeves else (160, 340)
    rgb[140:170, x0:x1] = (200, 30, 40)
    rgb += np.random.default_rng(3).normal(0, 3, rgb.shape)
    alpha = np.zeros((H, W), np.uint8)
    alpha[100:500, 160:340] = 255
    alpha[100:200, 60:440] = 255
    return Image.fromarray(np.dstack([np.clip(rgb, 0, 255).astype(np.uint8), alpha]), "RGBA")


LANDMARKS = {"shoulder_left": {"x": 162, "y": 102}, "shoulder_right": {"x": 338, "y": 102},
             "underarm_left": {"x": 160, "y": 199}, "underarm_right": {"x": 341, "y": 200}}


def test_sleeves_from_landmarks():
    cut = _t_shirt(False)
    regions = stripes.regions_from_landmarks(cut, LANDMARKS)
    assert regions is not None
    body, sleeves = regions
    assert sleeves[150, 100] and sleeves[150, 400] and not sleeves[300, 250]
    assert body[300, 250] and not body[150, 100]
    # an underarm point in the middle of the body is not trusted
    wrong = dict(LANDMARKS, underarm_left={"x": 250, "y": 300})
    assert stripes.regions_from_landmarks(cut, wrong) is None
    assert stripes.sleeves_carry_bands(cut, None, None, None) is None

    band = cv2.cvtColor(np.array([[[200, 30, 40]]], np.uint8), cv2.COLOR_RGB2LAB)[0].astype(np.float32)
    ground = cv2.cvtColor(np.array([[[225, 225, 225]]], np.uint8), cv2.COLOR_RGB2LAB)[0].astype(np.float32)
    assert stripes.sleeves_carry_bands(cut, band, ground, regions) is False
    cut2 = _t_shirt(True)
    assert stripes.sleeves_carry_bands(cut2, band, ground, stripes.regions_from_landmarks(cut2, LANDMARKS)) is True


# --- background-removal masks ------------------------------------------------------------------------------

def test_see_through():
    solid = np.zeros((400, 300), np.uint8)
    solid[40:360, 40:260] = 255
    assert masks.see_through(Image.fromarray(solid, "L")) < 0.02
    holes = solid.copy()
    for y in range(52, 350, 12):                  # a plaid's dark checks taken for background
        for x in range(52, 250, 12):
            holes[y:y + 7, x:x + 7] = 0
    assert masks.see_through(Image.fromarray(holes, "L")) > 0.25


# --- prints ------------------------------------------------------------------------------------------------

def _floral(H=420, W=340):
    rng = np.random.default_rng(4)
    rgb = np.full((H, W, 3), (30, 60, 40), np.float32)            # a dark green ground
    yy, xx = np.mgrid[0:H, 0:W]
    palette = np.array([(220, 120, 150), (240, 220, 120), (200, 200, 230)], np.float32)
    for _ in range(160):                                           # flowers: random round blobs
        cy, cx, r = rng.integers(0, H), rng.integers(0, W), rng.integers(4, 12)
        rgb[(yy - cy) ** 2 + (xx - cx) ** 2 < r * r] = palette[rng.integers(3)]
    rgb += rng.normal(0, 4, rgb.shape)
    return _cut(np.clip(rgb, 0, 255).astype(np.uint8), (20, 400, 30, 310))


def test_quilt_garment():
    cut = _floral()
    out, info = prints.quilt(cut, 200, 150)
    assert out.size == (200, 150)
    img, info = prints.quilt_garment(cut)
    assert abs(prints.lean(cut)) < 0.5
    assert img.size == (int(279 * 1.1), int(379 * 1.1))
    assert info["candidates"] >= 60
    assert info["distinct"] >= 0.8 * info["placed"]
    assert info["distinct"] >= 10
    arr = np.asarray(img).astype(float)
    assert arr.std() > 20                                          # flowers and ground, not one flat colour


# --- a graphic tee -------------------------------------------------------------------------------------------

def _tee(logo=True):
    """A white tee laid flat on a transparent background, with a red and navy logo on its chest if `logo`."""
    from PIL import ImageDraw
    im = Image.new("RGBA", (440, 520), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.polygon([(130, 20), (310, 20), (420, 120), (370, 180), (330, 150), (330, 500), (110, 500), (110, 150),
               (70, 180), (20, 120)], fill=WHITE + (255,))
    if logo:
        d.ellipse((170, 140, 270, 240), fill=RED + (255,))
        d.rectangle((195, 165, 245, 215), fill=NAVY + (255,))
    return im


def test_a_graphic_is_lifted_from_a_tee_and_drawn_at_its_place():
    from closet.drawing import item, stored
    from closet.patterns.measure import measure
    kept = measure(_tee(), "graphic")
    assert kept["kind"] == "plain" and kept["version"] == stored.VERSION
    x0, y0, x1, y1 = kept["graphic"]["box"]          # fractions of the garment (400 x 480 px from (20, 20))
    assert x0 <= 150 / 400 and x1 >= 250 / 400 and y0 <= 120 / 480 and y1 >= 220 / 480
    assert x1 - x0 < 0.4 and y1 - y0 < 0.4            # the logo, not the whole shirt
    g = stored.graphic_from(kept)
    assert abs(g.cx - 0.5) < 0.02 and g.image.mode == "RGBA"
    arr = np.asarray(g.image)
    assert arr[..., 3].min() < 50 and arr[..., 3].max() == 255   # the shirt around the logo is see-through
    assert stored.fill_from(kept, "#f0f0eb") is None             # the cloth itself is drawn in its colour
    plain = item.drawing_from_fields("tee", "#f0f0eb", "graphic", {"sleeve": "short", "neck": "crew"})
    drawn = item.drawing_from_fields("tee", "#f0f0eb", "graphic", {"sleeve": "short", "neck": "crew"}, graphic=g)
    assert "<image" not in plain.svg and any("graphic print" in n for n in plain.not_drawn)
    assert "<image" in drawn.svg and not any("graphic print" in n for n in drawn.not_drawn)


def test_a_plain_tee_has_no_graphic_to_lift():
    from closet.patterns.measure import measure
    assert measure(_tee(logo=False), "graphic") is None


# --- plaids the straight-on measure cannot find a repeat in ----------------------------------------------------

def _seen_at_an_angle(tile, H=760, W=700, turn=7.0, tilt=0.00045, noise=6.0, box=(90, 70, 610, 690), seed=1):
    """An endless plaid seen as a camera at the foot of a bed sees it: turned, and smaller towards the top of the
    photo (a homography), with noise, cut to a box. Returns the RGBA cutout."""
    Q_, P_ = tile.shape[:2]
    a = np.radians(turn)
    to_cloth = np.array([[np.cos(a), np.sin(a), 0], [-np.sin(a), np.cos(a), 0], [0, -tilt, 1.0]])
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    p = np.stack([xx - W / 2, yy - H / 2, np.ones_like(xx)], -1) @ to_cloth.T
    u, v = p[..., 0] / p[..., 2], p[..., 1] / p[..., 2]
    big = np.tile(tile, (4, 4, 1)).astype(np.float32)
    img = np.dstack([cv2.remap(big[..., c], (u % P_ + P_).astype(np.float32), (v % Q_ + Q_).astype(np.float32),
                               cv2.INTER_LINEAR) for c in range(3)])
    img += np.random.default_rng(seed).normal(0, noise, img.shape)
    alpha = np.zeros((H, W), np.uint8)
    x0, y0, x1, y1 = box
    alpha[y0:y1, x0:x1] = 255
    return Image.fromarray(np.dstack([np.clip(img, 0, 255).astype(np.uint8), alpha]), "RGBA")


def _soft_overcheck():
    """A soft dark plaid like a navy flannel: checks every 30 px in near-black, navy and charcoal, and a thin
    white line over every other check only, both ways, so the true repeat is 60 x 60."""
    black, navy, grey, white = (14, 15, 20), (26, 31, 52), (62, 62, 66), (150, 150, 150)
    seq = np.zeros(60, int)
    seq[15:30] = 1
    seq[45:60] = 2
    seq[7:9] = 3                      # the overcheck: in the first check, not in the second
    cols = np.array([black, navy, grey, white], np.float32)
    tile = (cols[seq][None, :, :] + cols[seq][:, None, :]) / 2
    tile[seq == 3, :] = white          # a white yarn stays white where it crosses
    tile[:, seq == 3] = white
    return tile


def _to_truth_size(image_text, truth):
    import base64
    import io
    with Image.open(io.BytesIO(base64.b64decode(image_text))) as im:
        return np.asarray(im.convert("RGB").resize((truth.shape[1], truth.shape[0]), Image.LANCZOS)).astype(np.float32)


def test_a_plaid_photographed_at_an_angle_is_straightened_and_measured():
    from closet.patterns import measure, straighten
    cut = _seen_at_an_angle(TRUTH)
    assert plaid.period(cut) is None                      # turned and tilted: no repeat along the rows and columns
    logs = []
    reg = straighten.regular(cut, logs.append)
    assert reg is not None and reg.steps == ("tilt", "evened")
    assert abs(reg.P / reg.Q - P / Q) < 0.08              # the repeat's own shape, whatever size it was evened to
    kept = measure.measure(cut, "plaid")
    assert kept["how"] == "straightened"
    assert _best_shift_error(_to_truth_size(kept["image"], TRUTH), TRUTH) < 16
    # the repeat's width on the garment: about one repeat (in the middle of the photo) over the cutout's width
    assert kept["width_frac"] == pytest.approx(P / 520, rel=0.15)


def test_an_overcheck_over_every_other_check_is_kept():
    """The jacket this was written for: checks every 30 px and a white line over every second one. Going by the
    checks alone the repeat is 30 and the white line averages away; it is 60, with the line in it."""
    from closet.patterns import measure, straighten
    tile = _soft_overcheck()
    cut = _seen_at_an_angle(tile, noise=7.0, tilt=0.0004, turn=4.0)
    reg = straighten.regular(cut)
    assert reg is not None and abs(reg.P / reg.Q - 1) < 0.08
    kept = measure.measure(cut, "plaid")
    assert kept is not None and kept["how"] == "straightened"
    got = _to_truth_size(kept["image"], tile)
    assert _best_shift_error(got, tile) < 14
    light = got.mean(2)
    # one bright line each way in the repeat, well above the cloth around it
    for profile in (light.mean(0), light.mean(1)):
        assert profile.max() > np.median(profile) + 25
        assert (profile > np.median(profile) + 25).sum() <= 6


def test_a_plaid_seen_straight_on_is_measured_as_before():
    from closet.patterns import measure
    kept = measure.measure(_crumpled_plaid(), "plaid")
    assert kept["how"] == "repeat" and kept["width_frac"] == pytest.approx(P / 480, rel=0.05)


def test_cloth_with_no_checks_is_not_drawn_as_a_guess():
    """Tagged plaid, but nothing in the photo repeats or crosses: no pattern is kept, so the item says the
    checks could not be measured and is drawn in its colour (it used to be drawn as a smear)."""
    from closet.patterns import measure
    rng = np.random.default_rng(3)
    blobs = cv2.GaussianBlur(rng.normal(0, 1, (600, 520, 3)).astype(np.float32), (0, 0), 22) * 420 + 110
    alpha = np.zeros((600, 520), np.uint8)
    alpha[40:560, 50:470] = 255
    cut = Image.fromarray(np.dstack([np.clip(blobs, 0, 255).astype(np.uint8), alpha]), "RGBA")
    assert measure.measure(cut, "plaid") is None


def test_a_plaid_with_no_regular_repeat_is_still_measured_whole():
    """A madras: bands of many widths that never repeat, crossing. Kept as one garment-sized tile."""
    from closet.patterns import measure
    rng = np.random.default_rng(5)

    def bands(n):
        out = []
        while len(out) < n:
            out += [rng.integers(40, 230, 3)] * int(rng.integers(6, 40))    # every band its own colour and width
        return np.array(out[:n], np.float32)
    img = (bands(420)[None, :, :] + bands(560)[:, None, :]) / 2 + rng.normal(0, 5, (560, 420, 3))
    alpha = np.zeros((560, 420), np.uint8)
    alpha[30:530, 40:380] = 255
    cut = Image.fromarray(np.dstack([np.clip(img, 0, 255).astype(np.uint8), alpha]), "RGBA")
    kept = measure.measure(cut, "plaid")
    assert kept is not None and kept["how"] == "whole" and kept["width_frac"] > 0.5


def _broad_plaid(P=120, Q=150, H=620, W=500, crease=9.0, seed=7):
    """A hanging shirt's plaid: broad soft bands, a repeat a quarter of the garment wide, and upright creases
    that pull the cloth sideways by up to `crease` px. Returns the cutout."""
    rng = np.random.default_rng(seed)

    def bands(n, widths, colours):
        seq = np.concatenate([np.tile(c, (w, 1)) for w, c in zip(widths, colours, strict=True)]).astype(np.float32)
        return cv2.GaussianBlur(np.tile(seq, (3, 1))[None], (0, 0), 3)[0][n:2 * n]
    warp = bands(P, (40, 14, 30, 8, 28), [(70, 60, 110), (200, 190, 160), (60, 100, 110), (170, 90, 60), (90, 80, 120)])
    weft = bands(Q, (56, 18, 36, 10, 30), [(80, 70, 120), (210, 200, 170), (70, 60, 100), (180, 100, 70), (60, 110, 120)])
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    sx = xx + crease * np.sin(xx / 37.0 + 1.3) + 0.5 * crease * np.sin(xx / 83.0 + yy / 300.0)
    img = (warp[(sx.astype(int) % P)] + weft[(yy.astype(int) % Q)]) / 2 + rng.normal(0, 4, (H, W, 3))
    alpha = np.zeros((H, W), np.uint8)
    alpha[30:H - 30, 40:W - 40] = 255
    return Image.fromarray(np.dstack([np.clip(img, 0, 255).astype(np.uint8), alpha]), "RGBA")


def test_a_large_repeat_on_creased_cloth_is_read_from_the_whole_garments_bands():
    """The owner's hanging plaid shirts (18 November): a repeat a quarter of the shirt wide, on creased cloth,
    shows in too few small areas. The garment's whole band sequences give it, and it is kept once rebuilt."""
    from closet.patterns import measure, straighten
    cut = _broad_plaid()
    readings = [(r.P, r.Q) for r in straighten.by_bands(cut)]
    assert any(abs(p - 120) <= 8 and abs(q - 150) <= 8 for p, q in readings), readings
    kept = measure.measure(cut, "plaid")
    assert kept is not None and kept["how"] in ("straightened", "repeat")
    assert kept["width_frac"] == pytest.approx(120 / 420, rel=0.12)


def test_a_spacing_twice_a_shorter_one_is_the_shorter_one_again_unless_that_one_is_weak():
    from closet.patterns import straighten
    seq = np.full((400, 3), 100.0, np.float32)
    for x in range(0, 400, 50):
        seq[x:x + 12] = (200, 120, 140)
    lags = dict(straighten._sequence_peaks(seq))
    assert any(abs(lag - 50) <= 1 for lag in lags) and any(abs(lag - 100) <= 1 for lag in lags)
    assert max(lags, key=lags.get) % 50 <= 1 or max(lags, key=lags.get) % 50 >= 49


def test_strong_bands_one_way_are_matched_when_only_another_peak_counts_as_a_tie():
    """Bold bands one way and faint ones the other (the owner's rust plaid): slid half a repeat along the bold
    bands, the piece still matches nearly as well. That is the slope of the same match, not a rival match;
    counted as a tie, no area of the shirt could be measured."""
    yy, xx = np.mgrid[0:300, 0:300].astype(np.float32)
    P = Q = 100
    sig = np.cos(2 * np.pi * xx / P) + 0.2 * np.cos(2 * np.pi * yy / Q)
    m = np.ones(sig.shape, bool)
    ref = sig[:Q, :P]
    _, strict, _ = flatten.local_offsets_match(sig, m, ref, P, Q)
    _, by_peaks, _ = flatten.local_offsets_match(sig, m, ref, P, Q, peaks=True)
    assert (strict > 0).sum() == 0 and (by_peaks > 0).sum() == by_peaks.size


def test_a_cutout_full_of_holes_is_not_measured_whole_and_does_not_fail():
    """A pale check against a bright window, cut out as a lattice of holes: nothing lines up, and it says so."""
    rng = np.random.default_rng(2)
    rgb = rng.integers(0, 255, (300, 240, 3)).astype(np.uint8)
    alpha = np.zeros((300, 240), np.uint8)
    alpha[::9, ::9] = 255
    got = plaid.no_repeat(Image.fromarray(np.dstack([rgb, alpha]), "RGBA"), lean_deg=0.0)
    assert got["agreement"] == 0.0 and got["tile"] is None


# --- what a cutout holds, and one mask from two models ----------------------------------------------------------

def _jacket_on_a_duvet(H=640, W=480):
    """A dark plaid jacket (a box with two sleeves) lying on a white duvet that fills the top of the photo and runs
    out of it, on a mid-grey floor. Returns (photo RGB, the jacket's mask, the duvet's mask), masks 0/255."""
    rng = np.random.default_rng(2)
    photo = np.full((H, W, 3), 120, np.float32)
    duvet = np.zeros((H, W), np.uint8)
    duvet[:330] = 255
    photo[duvet > 0] = 235
    jacket = np.zeros((H, W), np.uint8)
    jacket[250:560, 170:330] = 255
    cv2.fillPoly(jacket, [np.array([[170, 260], [170, 330], [70, 520], [40, 500]], np.int32)], 255)
    cv2.fillPoly(jacket, [np.array([[330, 260], [330, 330], [420, 520], [450, 500]], np.int32)], 255)
    cloth = np.tile(_soft_overcheck(), (H // 60 + 1, W // 60 + 1, 1))[:H, :W]
    photo[jacket > 0] = cloth[jacket > 0]
    photo += rng.normal(0, 4, photo.shape)
    return Image.fromarray(np.clip(photo, 0, 255).astype(np.uint8), "RGB"), jacket, duvet


def _share(mask, of):
    return float(((np.asarray(mask) > 128) & (of > 0)).sum() / max(1, (of > 0).sum()))


def test_bedding_only_one_model_kept_is_left_out_of_the_cutout():
    photo, jacket, duvet = _jacket_on_a_duvet()
    first = Image.fromarray(np.maximum(jacket, duvet), "L")        # the first model took the duvet too
    second = Image.fromarray(jacket, "L")
    assert masks.doubtful(photo, first)                            # on the photo's edge, and two kinds of surface
    assert not masks.doubtful(photo, second)
    settled = masks.settle(photo, first, second)
    assert _share(settled, jacket) > 0.97
    assert _share(settled, duvet & ~jacket) < 0.03


def test_a_part_of_the_garment_only_one_model_found_is_kept():
    photo, jacket, _ = _jacket_on_a_duvet()
    no_sleeve = jacket.copy()
    no_sleeve[:, :168] = 0                                         # the second model missed a sleeve
    settled = masks.settle(photo, Image.fromarray(jacket, "L"), Image.fromarray(no_sleeve, "L"))
    assert _share(settled, jacket) > 0.99
    # and a part in another colour that lies inside the photo (a varsity jacket's white sleeves) is kept as well
    white = np.asarray(photo).copy()
    sleeve = (jacket > 0) & (no_sleeve == 0)
    white[sleeve] = 240
    settled = masks.settle(Image.fromarray(white, "RGB"), Image.fromarray(jacket, "L"), Image.fromarray(no_sleeve, "L"))
    assert _share(settled, jacket) > 0.99


def test_a_see_through_plaid_is_still_filled_in_by_the_second_model():
    photo, jacket, _ = _jacket_on_a_duvet()
    holes = jacket.copy()
    for y in range(0, holes.shape[0], 28):
        for x in range(0, holes.shape[1], 28):
            holes[y:y + 16, x:x + 16] = 0                          # dark checks taken for background
    first = Image.fromarray(holes, "L")
    assert masks.doubtful(photo, first)
    settled = masks.settle(photo, first, Image.fromarray(jacket, "L"))
    assert _share(settled, jacket) > 0.99


def test_a_cutout_of_two_surfaces_is_split_and_the_plaid_measured():
    from closet.patterns import measure
    photo, jacket, duvet = _jacket_on_a_duvet()
    both = Image.fromarray(np.dstack([np.asarray(photo), np.maximum(jacket, duvet)]), "RGBA")
    parts = masks.surfaces(both)
    assert len(parts) == 2
    assert _share(parts[0].split()[3], jacket) > 0.9               # the patterned cloth first
    assert _share(parts[0].split()[3], duvet & ~jacket) < 0.1
    alone = Image.fromarray(np.dstack([np.asarray(photo), jacket]), "RGBA")
    assert masks.surfaces(alone) == [alone]                        # checks do not split one cloth in two
    kept = measure.measure(both, "plaid")                          # the duvet does not stop the plaid being found
    assert kept is not None and kept["kind"] == "tile" and kept["width_frac"] < 0.5


def test_a_plaid_from_a_dark_photo_is_lightened_to_the_colour_it_is_called():
    from closet.patterns import measure
    cut = _seen_at_an_angle(_soft_overcheck() * 0.45, noise=3.0, tilt=0.0004, turn=4.0)   # the same cloth, underexposed
    as_it_is = measure.measure(cut, "plaid", ["black"])
    lit = measure.measure(cut, "plaid", ["navy", "white"])
    assert "lit" not in as_it_is and lit["lit"] > 1.5
    assert _to_truth_size(lit["image"], TRUTH).mean() > 1.5 * _to_truth_size(as_it_is["image"], TRUTH).mean()
