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
