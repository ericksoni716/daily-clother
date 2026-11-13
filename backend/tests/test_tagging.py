"""GET /api/tagging: which routes to Claude can be used, checked without asking Claude anything.

A fake `claude` on PATH stands in for Claude Code; the real one is never run.
"""
import json
import logging
import os
import stat
import sys

import pytest

from closet.tagger import claude_cli

SECRET_KEY = "sk-ant-api03-test-only-not-a-real-key"
EMAIL = "owner@example.com"

FAKE_CLAUDE = """#!{python}
import json, os, sys, time
with open(os.environ["FAKE_CLAUDE_LOG"], "a") as f:
    f.write(json.dumps({{"argv": sys.argv[1:], "saw_api_key": "ANTHROPIC_API_KEY" in os.environ}}) + "\\n")
mode = os.environ.get("FAKE_CLAUDE_MODE", "signed_in")
if mode == "slow":
    time.sleep(20)
signed_in = mode == "signed_in"
print(json.dumps({{"loggedIn": signed_in, "authMethod": "claude.ai" if signed_in else "none", "email": "{email}",
                  "configDirectory": os.path.join(os.path.expanduser("~"), ".claude")}}))
sys.exit(0 if signed_in else 1)
"""

needs_posix = pytest.mark.skipif(sys.platform == "win32", reason="the fake claude is a script with a #! line")


@pytest.fixture
def home(tmp_path, monkeypatch):
    """An empty home folder and an empty PATH, so no real Claude Code can be found."""
    home = tmp_path / "home"
    (home / "bin").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("PATH", str(home / "bin"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(tmp_path / "calls.jsonl"))
    return home


def install_fake(folder, mode="signed_in", monkeypatch=None):
    folder.mkdir(parents=True, exist_ok=True)
    exe = folder / "claude"
    exe.write_text(FAKE_CLAUDE.format(python=sys.executable, email=EMAIL))
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    if monkeypatch:
        monkeypatch.setenv("FAKE_CLAUDE_MODE", mode)
    return exe


def calls():
    path = os.environ["FAKE_CLAUDE_LOG"]
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(line) for line in f]


def routes(body) -> dict:
    return {r["id"]: r for r in body["routes"]}


def test_tagging_needs_login(anon):
    assert anon.get("/api/tagging").status_code == 401


def test_tagging_answer_has_the_promised_shape(client, home):
    body = client.get("/api/tagging").json()
    assert set(body) == {"order", "routes"}
    assert body["order"] == ["plan", "api"]   # the plan first: it bills nothing
    assert [r["id"] for r in body["routes"]] == body["order"]
    for r in body["routes"]:
        assert set(r) == {"id", "available", "detail"}
        assert isinstance(r["available"], bool) and isinstance(r["detail"], str)


@needs_posix
def test_plan_route_is_available_when_claude_code_is_signed_in(client, home, monkeypatch):
    install_fake(home / "bin", "signed_in", monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET_KEY)
    plan = routes(client.get("/api/tagging").json())["plan"]
    assert plan == {"id": "plan", "available": True, "detail": ""}
    # only the free login check ran, and it never saw the API key
    assert calls() == [{"argv": ["auth", "status"], "saw_api_key": False}]


@needs_posix
def test_plan_route_finds_claude_code_in_its_usual_folder_when_it_is_not_on_path(client, home, monkeypatch):
    install_fake(home / ".local" / "bin", "signed_in", monkeypatch)
    assert routes(client.get("/api/tagging").json())["plan"]["available"] is True


def test_plan_route_without_claude_code_says_it_is_not_installed(client, home):
    plan = routes(client.get("/api/tagging").json())["plan"]
    assert plan["available"] is False and "not installed" in plan["detail"]
    assert calls() == []


@needs_posix
def test_plan_route_not_signed_in(client, home, monkeypatch):
    install_fake(home / "bin", "signed_out", monkeypatch)
    plan = routes(client.get("/api/tagging").json())["plan"]
    assert plan["available"] is False and "not signed in" in plan["detail"]
    assert [c["argv"] for c in calls()] == [["auth", "status"]]


@needs_posix
def test_plan_route_check_gives_up_quickly_when_claude_code_hangs(client, home, monkeypatch):
    install_fake(home / "bin", "slow", monkeypatch)
    monkeypatch.setattr(claude_cli, "STATUS_TIMEOUT", 0.5)
    plan = routes(client.get("/api/tagging").json())["plan"]
    assert plan["available"] is False and "did not answer in time" in plan["detail"]


def test_api_route_is_available_only_with_a_key_in_the_environment(client, home, monkeypatch):
    api = routes(client.get("/api/tagging").json())["api"]
    assert api == {"id": "api", "available": False, "detail": "No API key is set."}
    monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")
    assert routes(client.get("/api/tagging").json())["api"]["available"] is False
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET_KEY)
    assert routes(client.get("/api/tagging").json())["api"] == {"id": "api", "available": True, "detail": ""}


@needs_posix
@pytest.mark.parametrize("mode", ["signed_in", "signed_out"])
def test_nothing_secret_or_personal_is_returned_or_logged(client, home, monkeypatch, caplog, mode):
    install_fake(home / "bin", mode, monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET_KEY)
    with caplog.at_level(logging.DEBUG):
        text = client.get("/api/tagging").text
    for secret in (SECRET_KEY, "sk-ant", EMAIL, str(home), ".claude", "claude.ai"):
        assert secret not in text
        assert secret not in caplog.text
