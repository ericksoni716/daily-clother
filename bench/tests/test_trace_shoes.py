"""The shoe tracing bench, on synthetic shoes drawn here (never real photos)."""
import json
import xml.dom.minidom

import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter

from closet_bench import trace_shoes as T

UPPER, SOLE, MARK, GROUND = (38, 58, 138), (240, 238, 230), (228, 84, 40), (206, 200, 190)


def _lab(rgb):
    return T.to_lab(np.array([[rgb]], np.uint8))[0, 0]


def synthetic_shoe(toe="left", tilt=0.0, noise=0.0, shadow=False, scale=1.0, colors=(UPPER, SOLE, MARK), ground=GROUND,
                   blur=0.0, size=(720, 480)):
    """A side-on sneaker of colour blocks: upper, sole and a curved stripe across the side; drawn toe to the left
    on a lightly graded background, then optionally shadowed, mirrored, tilted, blurred and made noisy.
    Returns the photo and the shoe's true mask (0/1, the same size)."""
    upper_c, sole_c, mark_c = colors
    ss = 2
    w, h = size[0] * ss, size[1] * ss
    cx, cy = w / 2, h / 2

    def pts(seq):
        return [(cx + (x - 360) * scale * ss, cy + (y - 290) * scale * ss) for x, y in seq]

    upper = pts([(112, 350), (118, 318), (150, 300), (215, 286), (268, 262), (330, 240), (400, 220), (452, 208),
                 (492, 226), (530, 222), (576, 196), (598, 214), (606, 262), (610, 350)])
    sole = pts([(104, 352), (112, 340), (610, 340), (614, 352), (612, 384), (150, 384), (120, 376)])
    bg = np.zeros((h, w, 3), np.float32)
    bg[:] = ground
    bg *= np.linspace(1.04, 0.94, h)[:, None, None]
    img = Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    if shadow:   # a soft shadow on the ground under the shoe
        sh = Image.new("L", (w, h), 0)
        ImageDraw.Draw(sh).ellipse(pts([(130, 370), (640, 400)])[0] + pts([(130, 370), (640, 400)])[1], fill=120)
        sh = sh.filter(ImageFilter.GaussianBlur(14 * ss))
        img = Image.composite(Image.new("RGB", (w, h), (90, 88, 84)), img, sh)
        d = ImageDraw.Draw(img)
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    for poly, col in ((upper, upper_c), (sole, sole_c)):
        d.polygon(poly, fill=col)
        md.polygon(poly, fill=255)
    stripe = pts([(232 + i * 6, 330 - 70 * np.sin(np.pi * i / 100) - i * 0.7) for i in range(0, 51)])
    d.line(stripe, fill=mark_c, width=int(16 * scale * ss), joint="curve")
    arr = np.asarray(img).astype(np.float32)
    if shadow:   # the light falls from the toe: the heel half of the shoe is in shade
        m = np.asarray(mask) > 0
        dark = np.clip((np.arange(w) - cx) / (w * 0.35 * scale), 0, 1)[None, :] * 0.25
        arr[m] *= (1 - dark.repeat(h, 0)[m])[:, None]
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).resize(size, Image.LANCZOS)
    mask = mask.resize(size, Image.LANCZOS)
    if toe == "right":
        img, mask = img.transpose(Image.FLIP_LEFT_RIGHT), mask.transpose(Image.FLIP_LEFT_RIGHT)
    if tilt:
        img = img.rotate(tilt, resample=Image.BICUBIC, fillcolor=ground)
        mask = mask.rotate(tilt, resample=Image.BILINEAR, fillcolor=0)
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    if noise:
        rng = np.random.default_rng(7)
        a = np.asarray(img).astype(np.float32) + rng.normal(0, noise, (size[1], size[0], 3))
        img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    return img, (np.asarray(mask) > 127).astype(np.uint8)


CASES = {
    "plain": {},
    "noisy": dict(noise=9.0),
    "shadow": dict(shadow=True, noise=4.0),
    "tilted": dict(tilt=14.0, noise=4.0),
    "toe-right": dict(toe="right", noise=4.0),
}


@pytest.fixture(scope="module")
def traced():
    return {name: (kw, T.trace_photo(synthetic_shoe(**kw)[0], cutout="grabcut")) for name, kw in CASES.items()}


@pytest.mark.parametrize("name", list(CASES))
def test_the_cut_out_recovers_the_shoe(traced, name):
    kw, r = traced[name]
    _, truth = synthetic_shoe(**kw)
    cut = r.mask > 0
    iou = (cut & (truth > 0)).sum() / (cut | (truth > 0)).sum()
    # GrabCut (the fallback) loses some of a white sole where it lies in shade on a grey floor
    assert iou > (0.87 if name == "shadow" else 0.93), (name, iou)
    assert r.cutout_by == "grabcut"


@pytest.mark.parametrize("name", list(CASES))
def test_every_approach_traces_the_silhouette(traced, name):
    _, r = traced[name]
    assert {v.approach.name for v in r.variants} == {a.name for a in T.APPROACHES}
    for v in r.variants:
        assert v.scores.iou > 0.93, (name, v.approach.name)
        xml.dom.minidom.parseString(v.svg)
        assert "nan" not in v.svg.lower()


@pytest.mark.parametrize("name", list(CASES))
def test_the_main_colours_are_recovered(traced, name):
    """The upper, the sole and the stripe each come out as a region in about their real colour."""
    _, r = traced[name]
    best = next(v for v in r.variants if v.approach.name == r.best)
    regions = best.trace.regions
    shade = 30 if name == "shadow" else 12   # half the shadowed shoe is in shade; its colour is the mean
    assert T.delta_e(regions[0].lab, _lab(UPPER)) < shade, name
    soles = [g for g in regions if g.part == "sole"]
    assert soles and min(T.delta_e(g.lab, _lab(SOLE)) for g in soles) < 12, name
    assert min(T.delta_e(g.lab, _lab(MARK)) for g in regions) < shade, name
    assert best.scores.marks is not None and best.scores.marks > 0.6, name
    assert best.scores.delta_e < 10, name


@pytest.mark.parametrize("name", list(CASES))
def test_the_shoe_is_turned_toe_left_with_the_sole_level(traced, name):
    kw, r = traced[name]
    assert r.oriented.flipped == (kw.get("toe") == "right")
    assert abs(r.oriented.angle + kw.get("tilt", 0.0)) < 2.5, (name, r.oriented.angle)


@pytest.mark.parametrize("name", list(CASES))
def test_usable_photos_pass_the_gate(traced, name):
    _, r = traced[name]
    assert r.gate.ok, (name, r.gate.reasons)


def test_the_gate_rejects_an_unusable_photo():
    """A small, blurred shoe that barely differs from its background, cut off at the edge."""
    img, _ = synthetic_shoe(scale=0.4, blur=5.0, noise=3.0, colors=((196, 190, 180), (214, 208, 198), (186, 180, 172)))
    r = T.trace_photo(img, cutout="grabcut")
    assert not r.gate.ok
    assert not r.variants or r.best is not None
    assert any("blurred" in x or "stands out" in x or "too small" in x or "no shoe" in x for x in r.gate.reasons)


def _two_shoes():
    a = np.asarray(synthetic_shoe(scale=0.6)[0])[:, 100:620]
    b = np.asarray(synthetic_shoe(scale=0.6, toe="right")[0])[:, 100:620]
    return Image.fromarray(np.hstack([a, b]))


@pytest.mark.parametrize("make,why", [
    (lambda: synthetic_shoe(blur=6.0, noise=2.0)[0], "blurred"),
    (lambda: synthetic_shoe(colors=((196, 190, 180), (200, 194, 184), (180, 170, 160)), noise=2.0)[0], "stands out"),
    (lambda: synthetic_shoe()[0].crop((200, 0, 720, 480)), "edge of the photo"),
    (_two_shoes, "more than one thing"),
], ids=["blurred", "low-contrast", "cut-off", "two-shoes"])
def test_the_gate_says_why_a_photo_is_too_poor(make, why):
    r = T.trace_photo(make(), cutout="grabcut", approaches=T.APPROACHES[:1])
    assert not r.gate.ok
    assert any(why in x for x in r.gate.reasons), r.gate.reasons


def test_the_gate_rejects_a_photo_that_is_not_side_on():
    """The same shoe seen from the front: about as tall as wide, toe and heel alike."""
    img = Image.new("RGB", (600, 600), GROUND)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((220, 150, 380, 470), 60, fill=UPPER)
    d.rectangle((210, 440, 390, 480), fill=SOLE)
    r = T.trace_photo(img, cutout="grabcut")
    assert not r.gate.ok
    assert any("side-on" in x or "front" in x for x in r.gate.reasons)


def test_the_gate_names_each_failing_signal():
    g = T.gate({"found": 1.0, "size_px": 100.0, "sharpness": 0.5, "edge_touch": 0.2})
    assert not g.ok and len(g.reasons) == 2
    assert T.gate({"found": 1.0, "size_px": 900.0}).ok


def test_the_command_writes_sheets_and_an_index(tmp_path):
    photos = tmp_path / "shoes"
    photos.mkdir()
    synthetic_shoe(noise=4.0)[0].save(photos / "a.jpg", quality=92)
    synthetic_shoe(toe="right", tilt=-8.0)[0].save(photos / "b.png")
    out = tmp_path / "out"
    index = T.run(photos, out, cutout="grabcut", png=False, quiet=True)
    assert index.exists()
    for n in (1, 2):
        svg = (out / f"shoe-{n:02d}.sheet.svg").read_text(encoding="utf-8")
        doc = xml.dom.minidom.parseString(svg)
        ids = [e.getAttribute("id") for e in doc.getElementsByTagName("*") if e.getAttribute("id")]
        assert len(ids) == len(set(ids))
        assert svg.count("Today's template") == 1
        assert "Traced data (" + T.APPROACH.name + ")" in svg and "Pairs" in svg
    text = index.read_text(encoding="utf-8")
    assert "a.jpg" not in text and "b.png" not in text   # photos are listed by number only
    assert "photos pass the quality gate" in text
    data = json.loads((out / "results.json").read_text(encoding="utf-8"))
    assert data["summary"]["recommended"] in {a.name for a in T.APPROACHES}
    assert len(data["shoes"]) == 2
    for shoe in data["shoes"]:
        traced = T.TracedShoe.from_json(json.dumps(shoe["traced"]))
        assert traced.approach == T.APPROACH.name and traced.parts and traced.regions
        assert shoe["attempts"][-1]["cutout_by"] == "grabcut"


def test_the_gate_report_counts_why_photos_were_turned_down():
    def result(reasons, attempts=1):
        g = T.Gate(not reasons, reasons, {})
        return T.Result(None, None, "grabcut", None, [], g, None, 0.0,
                        attempts=[T.Attempt("model", ["x"])] * (attempts - 1) + [T.Attempt("grabcut", reasons)])

    results = [result([]), result(["the photo is blurred (sharpness 0.05, limit 0.08)"]),
               result(["the photo is blurred (sharpness 0.02, limit 0.08)", "the shoe is too small in the photo (size_px 90, limit 250)"]),
               result([], attempts=2)]
    assert T.why_turned_down(results) == {"the photo is blurred": 2, "the shoe is too small in the photo": 1}
    report = T.gate_report(results)
    assert report.startswith("2 of 4 photos pass the quality gate.")
    assert "2 × the photo is blurred" in report
    assert "1 needed the other cut-out" in report


def test_the_traced_data_is_drawn_back_with_its_marks_numbered():
    img, _ = synthetic_shoe(noise=2.0)
    r = T.trace_photo(img, cutout="grabcut", approaches=(T.APPROACH,))
    assert r.traced is not None
    svg = T.overlay_svg(r.traced)
    xml.dom.minidom.parseString(svg)
    assert svg.count("<text") >= len(r.traced.marks) + len([p for p in r.traced.parts if p.name in T.PART_INK])
    img, lines = T.pairs_cell(r)
    assert img is not None and lines[-1] == "one shoe"


def test_a_saved_tagger_answer_draws_the_template(tmp_path):
    img, _ = synthetic_shoe()
    answer = {"category": "boots", "color": "navy", "silhouette": {"shoe_height": "high"}}
    r = T.trace_photo(img, cutout="grabcut", answer=answer, approaches=T.APPROACHES[:1])
    plain = T.trace_photo(img, cutout="grabcut", approaches=T.APPROACHES[:1])
    assert r.template_svg and plain.template_svg and r.template_svg != plain.template_svg


def test_specks_join_their_neighbour():
    lmap = np.zeros((40, 40), np.int32)
    lmap[10:12, 10:12] = 1
    lmap[20:35, 20:35] = 2
    out = T.remove_specks(lmap.copy(), np.ones_like(lmap, np.uint8), 10)
    assert (out[10:12, 10:12] == 0).all() and (out[20:35, 20:35] == 2).all()


def test_the_trace_lies_where_the_templates_draw_a_shoe(traced):
    _, r = traced["plain"]
    t = r.variants[0].trace
    s, ox, oy = T.placement(t)
    pts = np.concatenate([p for path in t.regions[0].paths for p in path]) * s + np.array([ox, oy])
    assert pts[:, 1].max() == pytest.approx(T.SHOE_G, abs=0.5)
    assert pts[:, 0].min() >= T.SHOE_X0 - 0.5 and pts[:, 0].max() <= T.SHOE_X0 + T.SHOE_L + 0.5
    # toe to the left: the left quarter of the drawing is lower than the right quarter
    raster = T.raster(t) >= 0
    cols = np.nonzero(raster.any(axis=0))[0]
    q = len(cols) // 4
    heights = raster.sum(axis=0)[cols]
    assert heights[:q].mean() < heights[-q:].mean()
    assert cv2.countNonZero(raster.astype(np.uint8)) > 0
