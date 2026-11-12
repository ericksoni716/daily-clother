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
                season_confidence=0.5, silhouette=Silhouette.of(sleeve="long", neck="collar"), silhouette_confidence=0.7)
    base.update(secondary_colors=[], brand=None, size=None, material=None, needs_shot=None)
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
                 fit=["slim", "regular", "oversized"], front=["none", "buttons", "half", "zip"], pockets=["none", "chest", "low", "chest-low"],
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
    t, p = silhouette_params(make_tags(category="jeans", silhouette=Silhouette.of(leg="tapered")))
    assert (t, p["leg"], p["jeans"]) == ("pants", "tapered", True)
    assert silhouette_params(make_tags(category="sneakers", silhouette=Silhouette.of()))[0] == "sneaker"


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
    assert set(schema["$defs"]) == {"Silhouette", "ShotRequest"}  # two flat helper objects, no recursion


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
