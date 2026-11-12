import io
import xml.dom.minidom

import numpy as np
import pytest
from PIL import Image, ImageDraw

from closet_bench import fills, tagging
from closet_bench.bench import compare, summarize
from closet_bench.illustrate import STYLES, Fill, Spec, layer, render
from closet_bench.schema import Details, ItemTags, Silhouette, drawing_extras, drawing_for, silhouette_params
from closet_bench.templates import PANTS_DEFAULTS, SNEAKER_DEFAULTS, TOP_DEFAULTS, build


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


# ---- templates and rendering

@pytest.mark.parametrize("template,options", [
    ("top", dict(sleeve=["none", "short", "long"], neck=["crew", "v", "collar", "hood", "turtle"], length=["cropped", "regular", "long"],
                 fit=["slim", "regular", "oversized"], front=["none", "buttons", "half", "zip", "quarter-zip"],
                 pockets=["none", "chest", "chest-two", "low", "chest-low", "kangaroo"],
                 hem=["straight", "curved", "rib"], cuffs=["plain", "rib", "button"], buttons=[None, 0, 1, 3, 12],
                 neck_detail=["none", "v-insert"], shoulder=["set-in", "raglan"])),
    ("pants", dict(leg=["tapered", "straight", "wide"], length=["short", "ankle", "full"], jeans=[False, True],
                   waist=["belt", "elastic", "drawstring"], pockets=["scoop", "slant", "side", "none"], cargo=[False, True],
                   pleats=[0, 1, 2], crease=[False, True], hem=["stitched", "plain", "turnup", "rib"], coin=[False, True],
                   stitch=["tonal", "contrast"])),
    ("sneaker", dict(height=["low", "high"], sole=["thin", "regular", "chunky"],
                     style=["low_sneaker", "high_top", "runner", "slip_on", "loafer", "derby", "oxford", "boot", "chelsea_boot"],
                     toe_cap=["none", "stitched", "rubber"], stripe=["none", "side"], heel_tab=["none", "contrast"],
                     foxing=[False, True], laces=[False, True])),
])
def test_every_parameter_value_draws_valid_svg(template, options):
    for name, values in options.items():
        for v in values:
            spec = Spec(template, {name: v}, Fill("solid", "#336699"), texture="corduroy", trim_color="#ffffff", button_color="#111111")
            for style in ("flat", "line", "soft"):
                svg = render(spec, style)
                xml.dom.minidom.parseString(svg)
                assert "nan" not in svg.lower()


def test_defaults_cover_the_documented_vocabulary():
    assert set(TOP_DEFAULTS) == {"sleeve", "neck", "length", "fit", "front", "pockets", "hem", "cuffs", "buttons",
                                 "neck_detail", "shoulder"}
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


def test_a_shirt_collar_lies_over_the_placket_and_has_room_for_a_neck():
    import re
    params = dict(neck="collar", front="buttons", hem="curved", cuffs="button")
    shirt = build("top", params)
    roles = [part.role for part in shirt.parts]
    assert roles.count("collar_r") == roles.count("collar_l") == 1 and "hole" in roles and "edge" in roles
    # the placket is a seam (drawn under the collar), not a line drawn over it
    placket = [d for d in shirt.seams if re.fullmatch(r"M [\d.]+,[\d.]+ L [\d.]+,[\d.]+", d) and d.split()[1].split(",")[0] in ("193", "207")]
    assert len(placket) == 2 and not any(" 193," in d or " 207," in d for d in shirt.lines)
    hole = next(part.d for part in shirt.parts if part.role == "hole")
    xs = [float(x) for x, _ in re.findall(r"([\d.]+),([\d.]+)", hole)]
    ys = [float(y) for _, y in re.findall(r"([\d.]+),([\d.]+)", hole)]
    shoulder = shirt.anchors["shoulder_r"][0] - shirt.anchors["shoulder_l"][0]
    assert (max(xs) - min(xs)) / shoulder > 0.3            # a neck fits through the opening
    meet = max(ys)                                          # where the leaves meet at the centre front
    assert min(float(d.split()[1].split(",")[1]) for d in placket) > meet   # the placket starts below that
    svg = render(Spec("top", params, Fill("solid", "#ffffff")), "line")
    assert svg.index(placket[0]) < svg.index(hole)          # painted before the collar, so the collar covers it


@pytest.mark.parametrize("fit", ["slim", "regular", "oversized"])
@pytest.mark.parametrize("sleeve", ["short", "long"])
def test_sleeves_end_outside_the_body_and_inside_the_canvas(fit, sleeve):
    import re
    shape = build("top", dict(fit=fit, sleeve=sleeve))
    pts = [(float(x), float(y)) for x, y in re.findall(r"(-?[\d.]+),(-?[\d.]+)", shape.outline)]
    assert all(4 < x < 396 and 4 < y < 456 for x, y in pts)
    assert shape.sleeves and shape.bbox[2] <= 396


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
    t, p = silhouette_params(make_tags(category="jeans", silhouette=Silhouette.of(leg="tapered")))
    assert (t, p["leg"], p["jeans"]) == ("pants", "tapered", True)
    assert silhouette_params(make_tags(category="sneakers", silhouette=Silhouette.of()))[0] == "sneaker"


def test_pants_and_shoe_details_reach_the_drawing():
    t, p = silhouette_params(make_tags(category="trousers", silhouette=Silhouette.of(leg="wide"), details=Details.plain(
        waist="drawstring", pockets="cargo", pant_hem="ribbed", fabric="corduroy", features=["pleats"])))
    assert (p["waist"], p["cargo"], p["hem"], p["pleats"]) == ("drawstring", True, "rib", 1)
    jeans = silhouette_params(make_tags(category="jeans", silhouette=Silhouette.of(), details=Details.plain(features=["contrast_stitching"])))[1]
    assert jeans["stitch"] == "contrast" and "waist" not in jeans      # belt loops and a fly unless the tagger saw otherwise
    shoe = lambda category, **d: silhouette_params(make_tags(category=category, silhouette=Silhouette.of(), details=Details.plain(**d)))[1]
    assert shoe("boots")["style"] == "boot" and shoe("dress_shoes")["style"] == "derby"
    assert shoe("boots", shoe_style="chelsea_boot")["style"] == "chelsea_boot"
    assert shoe("sneakers", shoe_style="runner", features=["side_stripe", "chunky_sole"]) == dict(height="low", style="runner", sole="chunky", stripe="side")
    assert shoe("sneakers", fabric="canvas", features=["toe_cap"])["toe_cap"] == "rubber"
    assert shoe("dress_shoes", shoe_style="oxford", features=["toe_cap"])["toe_cap"] == "stitched"
    extras = drawing_extras(make_tags(category="sneakers", details=Details.plain(sole_color="white", lace_color="red", trim_color="navy")))
    assert (extras["sole_color"], extras["lace_color"], extras["trim_color"]) == ("#f6f5f2", "#b8332e", "#27344f")
    # every shoe style and every length of leg stays on the canvas
    import re
    for template, key, values in (("sneaker", "style", ["low_sneaker", "high_top", "runner", "slip_on", "loafer", "derby", "oxford", "boot", "chelsea_boot"]),
                                  ("pants", "leg", ["tapered", "straight", "wide"])):
        for v in values:
            for extra in ({}, {"sole": "chunky"} if template == "sneaker" else {"length": "short"}):
                pts = re.findall(r"(-?[\d.]+),(-?[\d.]+)", build(template, {key: v, **extra}).outline)
                assert all(2 < float(x) < 398 and 2 < float(y) < 458 for x, y in pts), (v, extra)


def test_details_the_tagger_saw_reach_the_drawing():
    """A polo with one dark button, a henley, a sweatshirt with a V-insert and a corduroy shirt each draw differently."""
    def draw(**kw):
        tags = make_tags(**kw)
        template, params = silhouette_params(tags)
        return params, render(Spec(template, params, Fill("solid", "#8a5a33"), **drawing_extras(tags)), "line")

    polo = dict(category="polo", silhouette=Silhouette.of(sleeve="short", neck="collar"))
    knit = dict(sleeve_length="short", neckline="polo_collar", collar="flat_knit", placket="polo")
    one, svg_one = draw(**polo, details=Details.plain(**knit, placket_buttons=1, button_color="black"))
    three, svg_three = draw(**polo, details=Details.plain(**knit, placket_buttons=3, button_color="white"))
    none_, svg_none = draw(**polo, details=Details.plain(**knit, placket_buttons=0))
    assert (one["front"], one["buttons"], three["buttons"], none_["buttons"]) == ("half", 1, 3, 0)
    assert len({svg_one, svg_three, svg_none}) == 3
    assert 'fill="#1f1f22"' in svg_one and 'fill="#f6f5f2"' in svg_three

    tee = dict(category="tee", silhouette=Silhouette.of(sleeve="long", neck="crew"))
    plain, svg_plain = draw(**tee, details=Details.plain(sleeve_length="long", neckline="crew"))
    henley, svg_henley = draw(**tee, details=Details.plain(sleeve_length="long", neckline="henley", placket="henley", placket_buttons=3))
    assert plain["front"] == "none" and henley["front"] == "half" and svg_plain != svg_henley

    sweat = dict(category="sweater", silhouette=Silhouette.of(sleeve="long", neck="crew"))
    rib = dict(sleeve_length="long", neckline="crew", cuff="rib_knit", hem="ribbed_band")
    base, svg_base = draw(**sweat, details=Details.plain(**rib))
    vee, svg_vee = draw(**sweat, details=Details.plain(**rib, features=["v_insert"]))
    big, svg_big = draw(**sweat, details=Details.plain(**rib, fit_detail="oversized"))
    assert (base["hem"], base["cuffs"]) == ("rib", "rib") and vee["neck_detail"] == "v-insert"
    assert len({svg_base, svg_vee, svg_big}) == 3

    cord, svg_cord = draw(details=Details.plain(sleeve_length="long", collar="point", placket="front_placket", placket_buttons=7,
                                               fabric="corduroy", trim_color="navy"))
    assert "<pattern id=\"ta\"" in svg_cord and 'fill="#27344f"' in svg_cord


def test_weight_and_fibre_are_tagged_and_handed_to_the_drawing():
    tags = make_tags(details=Details.plain(sleeve_length="long", collar="point", placket="snap", placket_buttons=6,
                                          pockets="hip_flap_double", fabric="flannel", fiber="woolen_wool", weight="heavyweight"))
    template, params, extras, notes = drawing_for(tags)
    assert template == "top" and params["pockets"] in ("low", "hip-patch", "hip-flap")   # hip pockets are not chest pockets
    assert tags.details.weight == "heavyweight" and tags.details.fiber == "woolen_wool"
    with pytest.raises(ValueError):
        Details.plain(weight="thick")
    cords = make_tags(category="trousers", silhouette=Silhouette.of(leg="straight"),
                      details=Details.plain(fabric="corduroy", corduroy_wale="wide_wale", weight="heavyweight"))
    assert drawing_for(cords)[2]["texture"] == "corduroy"


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


def test_the_schema_sent_to_the_api_stays_within_its_documented_limits():
    """No optional properties, no numeric or length constraints, every object closed, nothing recursive."""
    import json

    from anthropic.lib._parse._transform import transform_schema
    schema = transform_schema(ItemTags)
    text = json.dumps(schema)
    for banned in ("minimum", "maximum", "multipleOf", "minLength", "maxLength", "minItems", "maxItems"):
        assert f'"{banned}"' not in text

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False
                assert set(node.get("required", [])) == set(node.get("properties", {}))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(schema)
    assert set(schema["$defs"]) == {"Silhouette", "ShotRequest", "Details"}  # three flat helper objects, no recursion
    # the API allows only a limited number of nullable properties in one schema; details must not add any
    details = schema["$defs"]["Details"]
    assert all("anyOf" not in v and v.get("type") != ["string", "null"] for v in details["properties"].values())
    assert text.count('"anyOf"') <= 16


def test_the_tagging_request_and_answer_survive_a_real_http_round_trip():
    """Run the real SDK against a local stand-in server: checks what is sent and that the answer parses."""
    import http.server
    import json
    import threading

    import anthropic
    seen = {}
    answer = make_tags(category="jeans", silhouette=Silhouette.of(leg="straight", pant_length="full")).model_dump_json()

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            seen["path"] = self.path
            seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen["auth"] = self.headers.get("authorization") or self.headers.get("x-api-key")
            body = json.dumps({"id": "msg_test", "type": "message", "role": "assistant", "model": seen["body"]["model"],
                               "content": [{"type": "text", "text": answer}], "stop_reason": "end_turn", "stop_sequence": None,
                               "usage": {"input_tokens": 1700, "output_tokens": 310}}).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        client = anthropic.Anthropic(api_key="test-key", base_url=f"http://127.0.0.1:{srv.server_address[1]}", max_retries=0)
        r = tagging.tag_item(client, "claude-haiku-5-5", [garment()])
    finally:
        srv.shutdown()
    body = seen["body"]
    assert seen["path"].endswith("/v1/messages") and seen["auth"].endswith("test-key")
    assert body["model"] == "claude-haiku-5-5" and body["output_config"]["effort"] == "low"
    assert body["output_config"]["format"]["type"] == "json_schema" and "category" in body["output_config"]["format"]["schema"]["properties"]
    assert "temperature" not in body and "thinking" not in body and "tool_choice" not in body
    kinds = [b["type"] for b in body["messages"][0]["content"]]
    assert kinds == ["image", "text"] and body["messages"][0]["content"][0]["source"]["media_type"] == "image/jpeg"
    assert r.tags.category == "jeans" and r.tags.silhouette.leg == "straight"
    assert (r.input_tokens, r.output_tokens) == (1700, 310) and r.cost_usd == pytest.approx((1700 * 0.10 + 310 * 0.50) / 1e6)


# ---- the two ways to reach Claude: the plan (claude -p) and the API key

FAKE_CLAUDE = '''#!/usr/bin/env python3
import json, os, sys
mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
record = {"argv": sys.argv[1:], "saw_api_key": "ANTHROPIC_API_KEY" in os.environ,
          "photos": sorted(f for f in os.listdir(".") if f.endswith(".jpg"))}
with open(os.environ["FAKE_CLAUDE_LOG"], "a") as f:
    f.write(json.dumps(record) + "\\n")
if mode == "limit":
    print(json.dumps({"is_error": True, "result": "You've hit your session limit · resets 3:45pm"}))
    sys.exit(1)
if mode == "silent":
    print(json.dumps({"is_error": False, "result": "I looked at the photo."}))
    sys.exit(0)
print(json.dumps({"is_error": False, "result": "", "structured_output": json.loads(os.environ["FAKE_CLAUDE_ANSWER"]),
                  "usage": {"input_tokens": 4, "cache_creation_input_tokens": 5000, "cache_read_input_tokens": 4000, "output_tokens": 900},
                  "total_cost_usd": 0.0017}))
'''


@pytest.fixture
def fake_claude(tmp_path, monkeypatch):
    import json
    import stat
    exe = tmp_path / "claude"
    exe.write_text(FAKE_CLAUDE)
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "calls.jsonl"
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    monkeypatch.setenv("FAKE_CLAUDE_ANSWER", make_tags(category="tee").model_dump_json())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-never-reach-the-plan-route")
    return str(exe), lambda: [json.loads(line) for line in log.read_text().splitlines()]


def test_plan_route_tags_through_claude_code_without_ever_seeing_the_api_key(fake_claude):
    from closet_bench import claude_cli
    exe, calls = fake_claude
    r = claude_cli.tag_item_cli("claude-haiku-5-5", [garment(), garment()], exe=exe)
    assert r.route == "plan" and r.tags.category == "tee" and r.cost_usd == pytest.approx(0.0017)
    assert (r.input_tokens, r.output_tokens) == (9004, 900)
    call = calls()[0]
    assert call["saw_api_key"] is False and call["photos"] == ["photo-1.jpg", "photo-2.jpg"]
    argv = call["argv"]
    assert argv[0] == "-p" and "photo-1.jpg, photo-2.jpg" in argv[1]
    assert argv[argv.index("--model") + 1] == "claude-haiku-5-5" and argv[argv.index("--tools") + 1] == "Read"
    assert "--bare" not in argv  # bare mode cannot use the plan login
    import json
    assert "category" in json.loads(argv[argv.index("--json-schema") + 1])["properties"]


def test_when_the_plan_runs_out_the_api_key_takes_over_for_the_rest_of_the_run(fake_claude, monkeypatch):
    from closet_bench.routes import Router
    exe, calls = fake_claude
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "limit")
    router = Router("auto", client=FakeClient([Reply(make_tags()), Reply(make_tags())]), claude_exe=exe)
    first = router.tag("claude-haiku-5-5", [garment()])
    second = router.tag("claude-haiku-5-5", [garment()])
    assert first.route == "api" and second.route == "api"
    assert len(calls()) == 1 and "usage limit" in router.skipped["plan"]  # the plan is not asked again this run


def test_when_api_credits_run_out_the_plan_takes_over(fake_claude):
    import anthropic
    import httpx2 as httpx
    from closet_bench.routes import Router
    exe, _ = fake_claude

    class Broke:
        class messages:
            @staticmethod
            def parse(**kw):
                resp = httpx.Response(400, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
                raise anthropic.BadRequestError("Your credit balance is too low to access the Anthropic API.", response=resp, body=None)

    r = Router("api-first", client=Broke(), claude_exe=exe).tag("claude-haiku-5-5", [garment()])
    assert r.route == "plan"


def test_both_routes_dry_gives_one_clear_message(fake_claude, monkeypatch):
    from closet_bench.routes import Router
    from closet_bench.tagging import RouteUnavailable
    exe, _ = fake_claude
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "limit")
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    with pytest.raises(RouteUnavailable, match="plan: .*usage limit.*api: no API key"):
        Router("auto", claude_exe=exe).tag("claude-haiku-5-5", [garment()])


def test_a_plan_answer_with_no_structured_output_is_a_failure_not_a_fallback(fake_claude, monkeypatch):
    from closet_bench.routes import Router
    exe, calls = fake_claude
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "silent")
    router = Router("auto", client=FakeClient([Reply(make_tags())]), claude_exe=exe)
    with pytest.raises(tagging.TaggingError, match="no usable answer"):
        router.tag("claude-haiku-5-5", [garment()])
    assert len(calls()) == 2 and not router.skipped  # retried on the plan, never billed to the API


def test_plan_route_without_claude_code_installed_is_reported_as_unavailable(monkeypatch):
    from closet_bench import claude_cli
    from closet_bench.tagging import RouteUnavailable
    monkeypatch.setattr(claude_cli, "find_claude", lambda: None)
    with pytest.raises(RouteUnavailable, match="not installed"):
        claude_cli.tag_item_cli("claude-haiku-5-5", [garment()])


# ---- worn open

OPENING_TOPS = [dict(neck="collar", front="buttons"), dict(neck="hood", front="zip"), dict(neck="v", front="buttons", cuffs="rib", hem="rib"),
                dict(neck="collar", collar="notch", front="buttons"), dict(neck="collar", collar="peak", front="double", length="knee")]


@pytest.mark.parametrize("params", OPENING_TOPS)
def test_a_garment_that_opens_down_the_front_can_be_drawn_open(params):
    closed, opened = build("top", params), build("top", {**params, "state": "open"})
    assert closed.fronts is None and opened.fronts is not None
    assert opened.outline == closed.outline and opened.anchors == closed.anchors   # the same garment, on the same wearer
    for run in opened.fronts:   # each front's edge runs from the neck to below the hem
        assert run[0][1] < opened.anchors["hem"][1] / 2 and run[-1][1] > opened.anchors["hem"][1]
    a = render(Spec("top", params, Fill("solid", "#336699")), "line")
    b = render(Spec("top", {**params, "state": "open"}, Fill("solid", "#336699")), "line")
    assert a != b and "matrix(" in b and "matrix(" not in a


def test_a_pullover_has_nothing_to_open():
    for params in (dict(), dict(neck="collar", front="half"), dict(front="quarter-zip", neck="mock")):
        assert build("top", {**params, "state": "open"}).fronts is None
        spec = Spec("top", params, Fill("solid", "#336699"))
        assert render(Spec("top", {**params, "state": "open"}, spec.fill), "line") == render(spec, "line")


def test_an_open_garment_shows_the_one_underneath_between_its_fronts():
    tee = Spec("top", dict(sleeve="short"), Fill("solid", "#f1eee6"))
    jacket = dict(neck="collar", collar="notch", front="buttons")
    over = layer(tee, Spec("top", {**jacket, "state": "open"}, Fill("solid", "#1f2a44")), "line")
    assert "#f1eee6" in over and "#1f2a44" in over
    # back of the jacket, then the tee (cut to the opening), then the jacket's fronts
    assert over.index("#f1eee6") < over.rindex("matrix(") and over.index("#1f2a44") < over.index("#f1eee6")
    assert over.count("<svg") == 1
    closed = layer(tee, Spec("top", jacket, Fill("solid", "#1f2a44")), "line")   # a closed jacket just covers the tee
    assert "matrix(" not in closed and closed.index("#f1eee6") < closed.index("#1f2a44")
