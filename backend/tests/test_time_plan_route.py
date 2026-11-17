"""tools/time_plan_route.py: the developer tool that times the plan route several ways. Never reaches Claude: a
stand-in Claude Code (a small Python script) answers the streamed calls."""
import importlib.util
import json
import sys
import textwrap
from pathlib import Path

import pytest
from PIL import Image

from closet.tagger import claude_cli

from .conftest import ANSWER

TOOL = Path(__file__).resolve().parents[2] / "tools" / "time_plan_route.py"


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("time_plan_route", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def stand_in(tmp_path: Path, answer: dict | None, api_ms: int = 2500) -> list[str]:
    """A Claude Code that reads one streamed message, checks it carries the photo and the prompt, and answers."""
    said = tmp_path / f"answer-{len(list(tmp_path.iterdir()))}.json"
    said.write_text(json.dumps(answer), encoding="utf-8")
    script = tmp_path / f"claude_stand_in-{said.stem}.py"
    script.write_text(textwrap.dedent(f"""
        import json, os, sys
        answer = json.loads(open({str(said)!r}, encoding="utf-8").read())
        msg = json.loads(sys.stdin.readline())
        content = msg["message"]["content"]
        assert msg["type"] == "user" and content[0]["type"] == "image" and content[-1]["type"] == "text"
        assert content[0]["source"]["media_type"] == "image/jpeg"
        assert not os.listdir(".")   # started in an empty folder, as the app's calls are
        print(json.dumps({{"type": "system", "subtype": "init"}}), flush=True)
        print(json.dumps({{"type": "result", "is_error": False, "duration_api_ms": {api_ms},
                           "structured_output": answer}}), flush=True)
    """), encoding="utf-8")
    return [sys.executable, str(script)]


def test_the_streamed_commands_send_no_tools_and_the_lean_one_loads_no_settings(tool):
    cmd = tool.stream_command("claude", "claude-haiku-5-5", lean=False)
    assert cmd[:2] == ["claude", "--input-format"] and "stream-json" in cmd
    assert cmd[cmd.index("--output-format") + 1] == "stream-json" and "--verbose" in cmd
    assert cmd[cmd.index("--tools") + 1] == "" and "--setting-sources" not in cmd
    assert "--no-session-persistence" in cmd and "--strict-mcp-config" in cmd   # as the app's own calls
    lean = tool.stream_command("claude", "claude-haiku-5-5", lean=True)
    assert lean[lean.index("--setting-sources") + 1] == "" and "--disable-slash-commands" in lean


def test_the_message_carries_each_photo_inline_then_the_apps_own_prompt(tool):
    msg = json.loads(tool.message([Image.new("RGBA", (2000, 1000), (10, 20, 30, 255)), Image.new("RGB", (40, 40))]))
    content = msg["message"]["content"]
    assert [c["type"] for c in content] == ["image", "image", "text"]
    assert content[-1]["text"] == tool.PROMPT
    import base64
    import io
    with Image.open(io.BytesIO(base64.b64decode(content[0]["source"]["data"]))) as im:
        assert im.format == "JPEG" and max(im.size) == 1024   # as the plan route sends photos today


def test_a_streamed_call_is_timed_and_its_answer_checked_against_the_form(tool, tmp_path):
    msg = tool.message([Image.new("RGB", (40, 40))])
    seconds, good, api = tool.stream_call(stand_in(tmp_path, ANSWER.model_dump(mode="json")), msg, None, 30)
    assert good and api == 2.5 and seconds > 0
    # an answer outside the form is not counted as usable
    seconds, good, api = tool.stream_call(stand_in(tmp_path, {"category": "spaceship"}), msg, None, 30)
    assert not good
    # Claude Code started ahead: only the time after the photos are sent counts
    seconds, good, _ = tool.stream_call(stand_in(tmp_path, ANSWER.model_dump(mode="json")), msg, 1.0, 30)
    assert good and seconds < 1.0


def test_a_call_that_never_answers_is_stopped(tool, tmp_path):
    script = tmp_path / "silent.py"
    script.write_text("import sys, time\nsys.stdin.readline()\ntime.sleep(60)\n", encoding="utf-8")
    seconds, good, api = tool.stream_call([sys.executable, str(script)], tool.message([Image.new("RGB", (8, 8))]),
                                          None, 1.0)
    assert not good and api is None and seconds < 30


def test_todays_call_is_the_apps_own_and_its_claude_seconds_are_read(tool, monkeypatch):
    from types import SimpleNamespace
    said = {"is_error": False, "duration_api_ms": 4200, "structured_output": ANSWER.model_dump(mode="json")}
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout=json.dumps(said), stderr="")
    monkeypatch.setattr(claude_cli.subprocess, "run", fake_run)
    seconds, good, api = tool.today_call("claude", "claude-haiku-5-5", [Image.new("RGB", (40, 40))], 30)
    assert good and api == 4.2 and calls and calls[0][calls[0].index("--tools") + 1] == "Read"


def test_the_summary_judges_each_change_on_claudes_time_and_claude_codes_own_apart(tool):
    times = {"today": [7.0, 7.0, 7.0], "lean": [6.0, 6.0, 6.0], "ready": [4.0, 4.0, 4.0]}
    claude = {"today": [5.5, 5.5, 5.5], "lean": [5.3, 5.3, 5.3], "ready": [3.9, 3.9, 3.9]}
    lines = tool.summary(times, {"today": 3, "lean": 3, "ready": 2}, 3, claude)
    text = "\n".join(lines)
    assert "today" in lines[1] and "1.5s" in lines[1] and "3 of 3" in lines[1]
    assert "2 of 3 fitted the form" in text
    assert "Claude Code started ahead of the call: saves +2.0s in all, +1.4s of Claude's time, +0.6s of Claude Code's own" in text
    assert "Today Claude Code's own part is 1.5s of 7.0s" in text
    # a way Claude Code gave no seconds for shows a dash, not a guess
    lines = tool.summary({"today": [7.0]}, {"today": 1}, 1, {"today": [None]})
    assert lines[1].count("-") == 2


def test_unknown_ways_are_refused(tool):
    with pytest.raises(SystemExit):
        tool.main(["--ways", "teleport"])
