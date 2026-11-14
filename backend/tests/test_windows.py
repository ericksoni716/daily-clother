"""The parts of Closet that only matter on Windows, where the owner's hub runs.

Most run on any computer, with Windows stood in for (`platform="win32"`, a stand-in message box). The ones marked
`windows` use the real thing (Credential Manager, the registry, the tray, renaming a running program) and only
run on Windows, in the CI's Windows job. None of them leaves anything behind: the keychain entry and the registry
key they use are their own, never Closet's.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from closet import apikey, autostart, cli, instance, updates
from closet.tagger import claude_cli, correcting, garments, landmarks, shopping
from closet.tagger.tagging import PlanSignIn, TaggingError

# a program path as long as Windows paths usually go (MAX_PATH), so the command lines below are the longest
LONG_EXE = "C:\\Users\\" + "o" * 200 + "\\AppData\\Local\\Programs\\claude\\claude.exe"


def _schema(model):
    from anthropic.lib._parse._transform import transform_schema
    return transform_schema(model)


# Every call Closet makes through `claude -p`: the answer it asks for, its instructions and the tools it allows.
PLAN_CALLS = {
    "describe an item": (lambda: claude_cli.strict_schema(), claude_cli.SYSTEM, "Read"),
    "a typed correction": (lambda: _schema(correcting.CorrectionAnswer), correcting.SYSTEM, "Read"),
    "find some for a wish": (lambda: _schema(shopping.ShopAnswer), shopping.SYSTEM, shopping.PLAN_TOOLS),
    "check prices": (lambda: _schema(shopping.PriceAnswer), shopping.SYSTEM, shopping.PLAN_TOOLS),
    "pieces in one photo": (lambda: _schema(garments.Garments), garments.SYSTEM, "Read"),
    "where a top's seams are": (lambda: _schema(landmarks.Landmarks), landmarks.SYSTEM, "Read"),
}


# ------------------------------------------------------------------ claude -p
@pytest.mark.parametrize("call", list(PLAN_CALLS))
def test_every_plan_command_fits_on_a_windows_command_line(call):
    """Windows starts a program with at most 32,767 characters of command line. Describing an item used to need
    about 37,000 (the prompt and the answer's schema), so the plan route could never start on Windows."""
    schema, system, tools = PLAN_CALLS[call]
    cmd = claude_cli.print_command(LONG_EXE, "claude-haiku-5-5", "medium", schema(), tools, system, platform="win32")
    length = len(subprocess.list2cmdline(cmd))
    assert length < claude_cli.WINDOWS_COMMAND_LIMIT - 1000, f"{call}: {length} characters"


def test_a_command_too_long_for_windows_is_a_clear_failure():
    schema = {"type": "object", "description": "x" * claude_cli.WINDOWS_COMMAND_LIMIT}
    with pytest.raises(TaggingError, match="too long for Windows"):
        claude_cli.print_command("claude.exe", "m", "low", schema, "Read", "s", platform="win32")
    claude_cli.print_command("claude", "m", "low", schema, "Read", "s", platform="darwin")   # the Mac allows it


ECHO = ("import json, sys; print(json.dumps({'argv': sys.argv[1:], 'stdin': sys.stdin.buffer.read().hex()}))")


def test_the_prompt_and_the_schema_reach_the_program_whole():
    """A real program is started the way Claude Code is (on Windows: CreateProcess, the quoting of the schema, no
    console window), with a prompt Windows' own code page cannot hold, and reports what it was given."""
    prompt = 'Describe it — a café-au-lait “naïve” tee, 25 °C → 30 °C, "quoted" & | < > ^ %PATH%\nsecond line'
    cmd = claude_cli.print_command("claude", "claude-haiku-5-5", "low", claude_cli.strict_schema(), "Read",
                                   claude_cli.SYSTEM)
    assert prompt not in cmd
    proc = subprocess.run([sys.executable, "-c", ECHO, *cmd[1:]], input=prompt, capture_output=True, timeout=60,
                          **claude_cli.run_options())
    assert proc.returncode == 0, proc.stderr
    got = json.loads(proc.stdout)
    assert got["argv"] == cmd[1:]
    assert json.loads(got["argv"][got["argv"].index("--json-schema") + 1]) == claude_cli.strict_schema()
    # what arrives is UTF-8, as Claude Code reads it (Windows ends lines with \r\n on the way)
    assert bytes.fromhex(got["stdin"]).decode("utf-8").replace("\r\n", "\n") == prompt


def test_the_answer_is_read_as_utf8_whatever_the_computers_language(monkeypatch):
    seen = {}

    def run(cmd, **kw):
        seen.update(kw)
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="Not logged in")
    monkeypatch.setattr(claude_cli.subprocess, "run", run)
    from PIL import Image
    with pytest.raises(PlanSignIn):
        claude_cli.tag_item_cli("claude-haiku-5-5", [Image.new("RGB", (8, 8))], exe="claude")
    assert seen["encoding"] == "utf-8" and seen["errors"] == "replace" and "text" not in seen
    assert "stdin" not in seen and "Open each with the Read tool" in seen["input"]


def test_on_windows_claude_code_starts_without_a_console_window():
    assert claude_cli.run_options("win32") == {"encoding": "utf-8", "errors": "replace", "creationflags": 0x08000000}
    assert claude_cli.run_options("darwin") == {"encoding": "utf-8", "errors": "replace"}


def _which(found: dict):
    return lambda name: found.get(name)


def test_on_windows_claude_exe_comes_before_an_npm_claude_cmd(tmp_path):
    npm = "C:\\Users\\o\\AppData\\Roaming\\npm\\claude.cmd"
    on_path = "C:\\Users\\o\\.local\\bin\\claude.exe"
    assert claude_cli.find_claude("win32", _which({"claude.exe": on_path, "claude": npm}), tmp_path, {}) == on_path
    # not on this program's PATH (Closet was started before Claude Code was installed): its usual folders
    local = tmp_path / ".local" / "bin" / "claude.exe"
    local.parent.mkdir(parents=True)
    local.write_bytes(b"")
    assert claude_cli.find_claude("win32", _which({"claude": npm}), tmp_path, {}) == str(local)
    local.unlink()
    winget = tmp_path / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links" / "claude.exe"
    winget.parent.mkdir(parents=True)
    winget.write_bytes(b"")
    env = {"LOCALAPPDATA": str(tmp_path / "AppData" / "Local")}
    assert claude_cli.find_claude("win32", _which({"claude": npm}), tmp_path, env) == str(winget)
    winget.unlink()
    # only the npm one: better than saying Claude Code is not installed
    assert claude_cli.find_claude("win32", _which({"claude": npm}), tmp_path, env) == npm
    assert claude_cli.find_claude("win32", _which({}), tmp_path, env) is None


def test_elsewhere_claude_is_found_as_before(tmp_path):
    assert claude_cli.find_claude("darwin", _which({"claude": "/opt/homebrew/bin/claude"}), tmp_path, {}) == \
        "/opt/homebrew/bin/claude"
    assert claude_cli.find_claude("darwin", _which({}), tmp_path, {}) is None
    (tmp_path / ".local" / "bin").mkdir(parents=True)
    (tmp_path / ".local" / "bin" / "claude").write_bytes(b"")
    assert claude_cli.find_claude("darwin", _which({}), tmp_path, {}) == str(tmp_path / ".local" / "bin" / "claude")


# ------------------------------------------------------------------ the launcher's question
@pytest.fixture
def windowed(monkeypatch):
    """The packaged Windows program: no console, so questions go to a message box (stood in for here)."""
    shown = []
    monkeypatch.setattr(sys, "platform", "win32")
    answer = {"button": 6}

    def box(text, flags):
        shown.append((text, flags))
        if isinstance(answer["button"], Exception):
            raise answer["button"]
        return answer["button"]
    monkeypatch.setattr(cli, "_message_box", box)
    return shown, answer


def no_console(monkeypatch):
    # set in the test itself: pytest puts its own sys.stdout back between a fixture and the test
    monkeypatch.setattr(sys, "stdin", None)
    monkeypatch.setattr(sys, "stdout", None)


def test_replacing_the_older_copy_is_asked_in_a_yes_no_box_on_top(windowed, monkeypatch):
    shown, answer = windowed
    no_console(monkeypatch)
    assert cli._ask("An older Closet is running.", yes="Use 0.3.0", no="Keep 0.2.1") is True
    text, flags = shown[0]
    assert "Yes: Use 0.3.0" in text and "No: Keep 0.2.1" in text
    assert flags & 0x4 and flags & 0x40000   # Yes and No buttons; on top of other windows
    answer["button"] = 7
    assert cli._ask("?", "yes", "no") is False
    answer["button"] = 0   # the box could not be shown: nobody was asked, so nothing is decided for the owner
    assert cli._ask("?", "yes", "no") is None
    answer["button"] = OSError("no desktop")
    assert cli._ask("?", "yes", "no") is None
    assert cli._ask("?", "yes", "no", headless=True) is None and len(shown) == 4


def test_a_message_with_no_console_goes_to_a_box(windowed, monkeypatch):
    shown, _ = windowed
    no_console(monkeypatch)
    cli._say("The passphrase was cleared.")
    assert shown == [("The passphrase was cleared.", 0x40)]


# ------------------------------------------------------------------ processes (any computer)
def test_a_process_is_alive_until_it_has_ended():
    assert instance._pid_alive(os.getpid())
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait(timeout=60)
    assert not instance._pid_alive(proc.pid)


def test_the_updater_can_stop_a_program_that_does_not_answer():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        assert instance._pid_alive(proc.pid)
        updates._kill(proc.pid)
        proc.wait(timeout=30)
        assert not instance._pid_alive(proc.pid)
    finally:
        if proc.poll() is None:
            proc.kill()


# ------------------------------------------------------------------ the real thing, on Windows only
@pytest.mark.windows
def test_the_api_key_is_kept_in_windows_credential_manager():
    class TestCredentials(apikey.WindowsCredentials):
        TARGET = f"Closet-tests/{uuid.uuid4().hex}"   # never the owner's own entry

    store, key = TestCredentials(), "sk-ant-api03-" + "w" * 80
    try:
        assert store.get() is None
        store.delete()   # nothing there: not a problem
        store.set(key)
        assert store.get() == key
        store.set(key.replace("w", "v"))   # replacing it
        assert store.get() == key.replace("w", "v")
        with pytest.raises(ValueError):
            store.set("not a key")
        store.delete()
        assert store.get() is None
    finally:
        store.delete()


@pytest.mark.windows
def test_start_at_login_is_written_to_this_users_run_key(monkeypatch):
    import winreg
    key = rf"Software\Closet-tests\Run-{uuid.uuid4().hex}"   # never the computer's own Run key
    monkeypatch.setattr(autostart, "RUN_KEY", key)
    exe = r"C:\Users\Owner Name\Downloads\Closet.exe"
    try:
        assert not autostart.is_enabled("win32")
        autostart.set_enabled(True, exe=exe, platform="win32")
        assert autostart.is_enabled("win32")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            value, kind = winreg.QueryValueEx(k, autostart.NAME)
        assert value == f'"{exe}" --no-browser' and kind == winreg.REG_SZ   # quoted: the path has a space
        autostart.set_enabled(False, platform="win32")
        assert not autostart.is_enabled("win32")
        autostart.set_enabled(False, platform="win32")   # already off
    finally:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
        except OSError:
            pass


@pytest.mark.windows
def test_the_tray_icon_has_its_menu_on_windows():
    from closet import tray
    on = {"value": False}
    opened, quit_ = [], []
    icon = tray.create(lambda: opened.append(1), lambda: quit_.append(1), lambda: on["value"],
                       lambda v: on.update(value=v))
    assert icon is not None
    items = list(icon.menu.items)
    assert [i.text for i in items] == ["Open Closet", "Start when I log in", "Quit Closet"]
    assert items[0].default and not items[1].checked
    items[1](icon)
    assert on["value"] is True and items[1].checked
    items[0](icon)
    items[2](icon)
    assert opened == [1] and quit_ == [1]


@pytest.mark.windows
def test_a_running_program_can_be_renamed_aside_and_replaced(tmp_path):
    """What an update does on Windows: the running Closet.exe cannot be overwritten or deleted, but it can be
    renamed, so the new one takes its name and the old one is removed once it has quit."""
    program = tmp_path / "Closet.exe"
    shutil.copyfile(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "ping.exe", program)
    running = subprocess.Popen([str(program), "-n", "120", "127.0.0.1"], stdout=subprocess.DEVNULL,
                               creationflags=0x08000000)
    try:
        with pytest.raises(OSError):
            program.unlink()
        new = b"the new program"
        package = tmp_path / "download.exe"
        package.write_bytes(new)
        where = updates.layout("win32", str(program))
        updates.swap(where, package, hashlib.sha256(new).hexdigest())
        assert program.read_bytes() == new and where.old.exists()
        with pytest.raises(OSError):   # still running: the update tidies it away later
            where.old.unlink()
        assert running.poll() is None
    finally:
        updates._kill(running.pid)
        running.wait(timeout=30)
    for _ in range(50):   # Windows lets go of the file a moment after the program has ended
        try:
            where.old.unlink()
            break
        except PermissionError:
            time.sleep(0.2)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["Closet.exe", "download.exe"]
