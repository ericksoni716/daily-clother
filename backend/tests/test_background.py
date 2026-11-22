"""Windows keeping Nines running (closet/background.py): the scheduled task, turning it on and off, the launch that
never serves by itself once it is on, the hand-over, updates through the task, the sealed API key, and the endpoints.

Windows is stood in for everywhere but the last test: `elevated` (the script behind the administrator prompt),
`run_task`, `end_task` and `windows_user` are replaced, and the key is "sealed" by a stand-in. The last test registers
a real task, on the CI's Windows runner only.
"""
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from closet import apikey, autostart, background, backup, cli, config, gate, instance, updates
from closet import app as app_module
from closet.config import Config
from closet.state import State

from .conftest import LocalClient

KEY = "sk-ant-api03-" + "k" * 80
OTHER = "sk-ant-api03-" + "e" * 80
PHONE = {"host": "closet-pc.example-tailnet.ts.net", "Tailscale-User-Login": "owner@example.com"}


class Reversed:
    """Stands in for Windows' sealing: reversible, and never the key as written."""

    def seal(self, data: bytes) -> bytes:
        return b"sealed:" + data[::-1]

    def unseal(self, data: bytes) -> bytes:
        assert data.startswith(b"sealed:")
        return data[len(b"sealed:"):][::-1]


@pytest.fixture
def windows(monkeypatch, tmp_path):
    """The packaged program on Windows, with every call to Windows recorded instead of made."""
    local = tmp_path / "AppData-Local"
    home = tmp_path / "home"
    home.mkdir()
    env = SimpleNamespace(scripts=[], runs=[], ends=[], starts="startup", declined=False, autostart=False,
                          autostart_exe=None, home=home, local=local)
    monkeypatch.setattr(background, "supported", lambda platform=None, frozen=None: True)
    monkeypatch.setattr(background, "install_dir", lambda: local / "Nines")
    monkeypatch.setattr(background, "windows_user", lambda: "PC\\owner")
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("CLOSET_DATA_DIR", raising=False)

    def elevated(script, result, elevate=True):
        env.scripts.append(script)
        if env.declined:
            raise background.Declined()
        return {"ok": True, "starts": env.starts} if "Register-ScheduledTask -TaskName $TaskName" in script else {"ok": True}
    monkeypatch.setattr(background, "elevated", elevated)
    monkeypatch.setattr(background, "run_task", lambda: env.runs.append(1) or True)
    monkeypatch.setattr(background, "end_task", lambda: env.ends.append(1))
    monkeypatch.setattr(autostart, "is_enabled", lambda *a, **k: env.autostart)
    def set_enabled(on, exe=None, *a, **k):
        env.autostart, env.autostart_exe = on, exe
    monkeypatch.setattr(autostart, "set_enabled", set_enabled)
    monkeypatch.setattr(autostart, "program", lambda: str(tmp_path / "Downloads" / "Nines.exe"))
    apikey.use_sealer(Reversed())
    yield env
    apikey.use_sealer(None)
    apikey.keep_sealed(None)


@pytest.fixture
def program(tmp_path):
    exe = tmp_path / "Downloads" / "Nines.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"the program")
    return exe


@pytest.fixture
def home_cfg(windows):
    """The closet in the owner's home, where the task's copy finds it (port 8766: another app has 8765)."""
    c = Config(data_dir=windows.home / "Nines", port=8766, auto_download_model=False)
    c.data_dir.mkdir()
    return c


# ------------------------------------------------------------------ turning it on and off
def test_turning_it_on_copies_the_program_and_registers_the_task_for_the_port_in_use(windows, program, home_cfg, keychain):
    keychain.key = KEY
    windows.autostart = True
    assert background.turn_on(home_cfg, program, home_cfg.port) == {"starts": "startup"}
    assert background.installed_exe().read_bytes() == b"the program"   # its own copy, wherever the download is
    script = windows.scripts[-1]
    # the port this copy serves on, never the default, and the home the task's copy finds the closet in
    assert f"'--background --port 8766 --home {windows.home}'" in script
    assert "8765" not in script
    marker = background.read_marker()
    assert marker["starts"] == "startup" and marker["port"] == 8766 and marker["data_dir"] is None
    assert background.is_set_up(home_cfg)
    assert windows.autostart is False and marker["autostart_was_on"] is True   # start at login is off
    assert apikey.read_sealed(home_cfg.data_dir) == KEY                        # sealed for a start before sign-in
    assert KEY not in apikey.sealed_path(home_cfg.data_dir).read_text()
    assert windows.runs == []   # not started here: the ordinary copy still has the port and hands it over


def test_when_windows_will_not_run_it_without_a_sign_in_it_starts_when_you_sign_in(windows, program, home_cfg):
    windows.starts = "logon"
    assert background.turn_on(home_cfg, program, home_cfg.port) == {"starts": "logon"}
    assert background.status(home_cfg, False)["starts"] == "logon"
    # the choice is the script's: a throwaway task run as you without a sign-in, then either trigger
    script = windows.scripts[-1]
    for part in ("-LogonType S4U", "whoami.exe", "-AtStartup", "-AtLogOn -User $UserId", "-LogonType Interactive"):
        assert part in script


def test_the_task_starts_a_stopped_copy_again_and_lets_its_own_user_run_it(windows, program, home_cfg):
    background.turn_on(home_cfg, program, home_cfg.port)
    script = windows.scripts[-1]
    assert f"-RepetitionInterval (New-TimeSpan -Minutes {background.REPEAT_MINUTES})" in script
    assert "-MultipleInstances IgnoreNew" in script and "-ExecutionTimeLimit ([TimeSpan]::Zero)" in script
    assert "(A;;GRGX;;;$UserId)" in script and "-RunLevel Limited" in script


def test_a_declined_prompt_changes_nothing(windows, program, home_cfg, keychain):
    keychain.key = KEY
    windows.autostart = True
    windows.declined = True
    with pytest.raises(background.SetupError) as e:
        background.turn_on(home_cfg, program, home_cfg.port)
    assert str(e.value) == background.DECLINED
    assert not background.installed_exe().exists() and background.read_marker() is None
    assert windows.autostart is True and not apikey.has_sealed(home_cfg.data_dir)
    assert not background.is_set_up(home_cfg)


def test_turning_it_off_removes_the_task_and_the_copy_and_leaves_the_closet(windows, program, home_cfg, keychain):
    windows.autostart = True
    background.turn_on(home_cfg, program, home_cfg.port)
    (home_cfg.data_dir / "closet.db").write_bytes(b"the closet")
    apikey.save(OTHER, home_cfg.data_dir)   # saved while it was on
    background.turn_off(home_cfg)
    assert "Unregister-ScheduledTask -TaskName $TaskName" in windows.scripts[-1]
    assert not background.installed_exe().exists() and background.read_marker() is None
    assert (home_cfg.data_dir / "closet.db").read_bytes() == b"the closet"
    assert not apikey.has_sealed(home_cfg.data_dir) and keychain.key == OTHER   # the key goes back where it was
    assert windows.autostart is True                                           # start at login as it was before


def test_a_key_removed_while_it_was_on_stays_removed(windows, program, home_cfg, keychain):
    keychain.key = KEY
    background.turn_on(home_cfg, program, home_cfg.port)

    class Locked:   # Credential Manager, as a copy started before sign-in most likely finds it
        where = "Windows Credential Manager"

        def get(self):
            raise apikey.KeychainError("no")

        def set(self, key):
            raise apikey.KeychainError("no")

        def delete(self):
            raise apikey.KeychainError("no")
    apikey.use_store(Locked())
    apikey.remove(home_cfg.data_dir)
    assert apikey.get() is None
    apikey.use_store(keychain)
    background.turn_off(home_cfg)
    assert keychain.key is None


def test_the_task_follows_the_closet_when_its_folder_moves_to_nines(windows, program):
    old = Config(data_dir=windows.home / "Closet", port=8766)
    old.data_dir.mkdir()
    background.turn_on(old, program, 8766)
    assert background.is_set_up(old)
    old.data_dir.rename(windows.home / "Nines")   # the task's copy moves it at its next start (closet/datafolder.py)
    assert background.is_set_up(Config(data_dir=windows.home / "Nines"))
    assert not background.is_set_up(Config(data_dir=windows.home / "Elsewhere"))   # another closet is not its


def test_a_data_folder_chosen_by_hand_goes_with_the_task(windows, program, tmp_path, monkeypatch):
    chosen = Config(data_dir=tmp_path / "My closet", port=8766)
    monkeypatch.setenv("CLOSET_DATA_DIR", str(chosen.data_dir))
    background.turn_on(chosen, program, 8766)
    assert f'--data-dir "{chosen.data_dir}"' in windows.scripts[-1]
    assert background.is_set_up(chosen)


def test_task_arguments_keep_a_home_with_spaces_whole():
    args = background.task_arguments(8766, r"C:\Users\Owner Name", None)
    assert args == r'--background --port 8766 --home "C:\Users\Owner Name"'


def test_nothing_is_offered_on_a_mac_or_from_source(cfg):
    assert not background.supported("darwin", True) and not background.supported("win32", False)
    assert background.status(cfg, False) == {"available": False, "on": False, "starts": None, "running": False,
                                             "port": cfg.port, "problem": None}
    with pytest.raises(background.SetupError, match="only in the downloaded Nines program for Windows"):
        background.turn_on(cfg, sys.executable, cfg.port)


def test_started_by_the_task_the_home_and_data_folder_are_set_before_anything_reads_them(monkeypatch, tmp_path):
    for name in ("USERPROFILE", "HOME", "LOCALAPPDATA", "APPDATA", "CLOSET_DATA_DIR"):
        monkeypatch.delenv(name, raising=False)
    home = tmp_path / "Owner Name"
    cli._from_task(SimpleNamespace(home=str(home), data_dir=None))
    assert os.environ["USERPROFILE"] == str(home) and os.environ["LOCALAPPDATA"] == str(home / "AppData" / "Local")
    assert config.load(home=home).data_dir == home / "Nines"
    cli._from_task(SimpleNamespace(home=None, data_dir=str(tmp_path / "chosen")))
    assert config.load().data_dir == tmp_path / "chosen"


# ------------------------------------------------------------------ the sealed key
def test_the_sealed_key_is_read_only_when_the_keychain_gives_none(windows, cfg, keychain):
    apikey.write_sealed(cfg.data_dir, KEY)
    assert apikey.get() is None                 # not falling back: Windows does not keep Nines running
    apikey.keep_sealed(cfg.data_dir)
    assert apikey.get() == KEY                  # the keychain gives none
    keychain.key = OTHER
    assert apikey.get() == OTHER                # the keychain first


def test_backups_leave_the_sealed_key_out(windows, services, cfg, tmp_path):
    apikey.write_sealed(cfg.data_dir, KEY)
    folder = tmp_path / "backups"
    folder.mkdir()
    assert backup.run_backup(cfg, services.state, folder=folder)["ok"]
    assert any(folder.rglob("*.sqlite"))
    for f in folder.rglob("*"):
        assert apikey.SEALED_FILE not in f.name
        if f.is_file():
            assert b"sealed:" not in f.read_bytes() and KEY.encode() not in f.read_bytes()


# ------------------------------------------------------------------ the endpoints
@pytest.fixture
def kept(windows, program, services, monkeypatch):
    """Settings on the computer, with the closet where the task finds it."""
    monkeypatch.setattr(sys, "executable", str(program))
    handed = []
    services.on_hand_over = lambda: handed.append(1)
    c = LocalClient(app_module.create_app(services))
    windows.client, windows.handed, windows.services = c, handed, services
    monkeypatch.setattr(background, "task_data_dir", lambda marker: services.cfg.data_dir)
    return windows


def _wait(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        time.sleep(0.05)
    return condition()


def test_turning_it_on_from_settings_hands_this_copy_over(kept):
    c = kept.client
    assert c.get("/api/background").json() == {"available": True, "on": False, "starts": None, "running": False,
                                               "port": kept.services.cfg.port, "problem": None}
    r = c.post("/api/background/on")
    assert r.status_code == 200 and r.json()["on"] is True and r.json()["handing_over"] is True
    assert _wait(lambda: kept.handed == [1])
    assert c.get("/api/settings").json()["background"]["starts"] == "startup"


def test_a_declined_prompt_is_said_in_plain_words(kept):
    kept.declined = True
    r = kept.client.post("/api/background/on")
    assert r.status_code == 409 and r.json() == {"detail": background.DECLINED}
    time.sleep(0.6)
    assert kept.handed == []


def test_it_is_changed_only_on_the_computer_and_read_from_anywhere(kept):
    for path in ("/api/background/on", "/api/background/off", "/api/background/restart"):
        r = kept.client.post(path, headers=PHONE)
        assert r.status_code == 403 and r.json() == {"detail": background.FROM_COMPUTER}
    assert kept.scripts == []
    assert kept.client.get("/api/background", headers=PHONE).json()["on"] is False


def test_turning_it_off_in_the_background_copy_asks_the_window_on_this_screen(kept, monkeypatch):
    kept.client.post("/api/background/on")
    kept.services.background_copy = True
    asked = []
    monkeypatch.setattr(instance, "ask_window_process", lambda cfg, command: asked.append(command) or bool(asked[1:]))
    r = kept.client.post("/api/background/off")   # opened in a browser: no window to ask
    assert r.status_code == 409 and "Open Nines from its icon on this computer" in r.json()["detail"]
    r = kept.client.post("/api/background/off")
    assert r.status_code == 200 and r.json()["turning_off"] is True and asked == ["off", "off"]
    assert background.read_marker() is not None   # the window does it, not this copy
    assert kept.client.post("/api/background/on").status_code == 409
    assert kept.client.post("/api/background/restart").status_code == 409


def test_an_ordinary_copy_turns_it_off_itself_or_starts_it_again(kept):
    kept.client.post("/api/background/on")
    _wait(lambda: kept.handed == [1])
    r = kept.client.post("/api/background/restart")   # the background copy did not start: this copy hands over again
    assert r.status_code == 200 and _wait(lambda: kept.handed == [1, 1])
    r = kept.client.post("/api/background/off")
    assert r.status_code == 200 and r.json()["on"] is False and background.read_marker() is None
    assert r.json()["note"] is None   # the program it runs is the one that carries on


def test_turning_it_off_from_the_window_says_why_it_did_not_work(kept):
    background.note_outcome(kept.services.cfg, background.DECLINED)
    assert kept.client.get("/api/background").json()["problem"] == background.DECLINED
    assert background.read_outcome(kept.services.cfg, now=time.time() + background.OUTCOME_FOR + 1) is None


def test_saving_the_key_while_it_is_on_seals_it_and_never_sends_it(kept, monkeypatch, caplog):
    monkeypatch.setattr(apikey, "check", lambda key: None)
    kept.client.post("/api/background/on")
    r = kept.client.put("/api/settings/api-key", json={"key": KEY})
    assert r.status_code == 200 and KEY not in r.text + caplog.text
    assert apikey.read_sealed(kept.services.cfg.data_dir) == KEY
    assert kept.client.delete("/api/settings/api-key").status_code == 200
    assert apikey.has_sealed(kept.services.cfg.data_dir) and apikey.read_sealed(kept.services.cfg.data_dir) is None
    assert KEY not in kept.client.get("/api/settings").text


# ------------------------------------------------------------------ the window's door takes "off"
def test_the_window_takes_off_only_with_its_token(cfg):
    done = []
    door = instance.WindowDoor(cfg, lambda: True, {"off": lambda: done.append(1) or True})
    try:
        assert instance.ask_window_process(cfg, "off") and done == [1]
        assert not instance.ask_window_process(cfg, "something-else") and done == [1]
        lock = json.loads(instance.window_lock_path(cfg).read_text())
        instance.window_lock_path(cfg).write_text(json.dumps(dict(lock, token="not-it")))
        assert not instance.ask_window_process(cfg, "off") and done == [1]
    finally:
        door.close()


# ------------------------------------------------------------------ the launch, once it is on
@pytest.fixture
def launch(cfg, monkeypatch):
    """The launcher with Windows keeping Nines running, and no background copy answering until the task starts it."""
    env = SimpleNamespace(running=None, started=[], windows=[], asked=[], said=[], answer=False, comes_up=True)
    monkeypatch.setattr(background, "is_set_up", lambda c: True)
    monkeypatch.setattr(instance, "running_info", lambda c: env.running)

    def start_and_wait(c, timeout):
        env.started.append(timeout)
        if env.comes_up:
            env.running = {"port": 8766, "version": "0.3.0", "pid": 1, "token": "t", "background": True}
        return env.running
    monkeypatch.setattr(background, "start_and_wait", start_and_wait)
    monkeypatch.setattr(cli, "_window_only", lambda a, c, info, release: env.windows.append(info["port"]) or 0)
    monkeypatch.setattr(cli, "_ask", lambda q, yes, no, headless=False: env.asked.append(q) or env.answer)
    monkeypatch.setattr(cli, "_say", env.said.append)

    def no_server(c):
        raise RuntimeError("this copy started its own server")
    monkeypatch.setattr(app_module, "build_services", no_server)
    return env


def launch_args(**kw):
    return SimpleNamespace(**{"no_browser": False, "no_tray": False, "tray": False, "browser": False, "port": None,
                              "replace": False, "background": False, "after": None, "on_its_own": False,
                              "home": None, "data_dir": None, **kw})


def test_a_launch_starts_the_background_copy_and_opens_a_window_onto_it(cfg, launch):
    assert cli.serve(launch_args(), cfg) == 0
    assert launch.started == [background.WAIT] and launch.windows == [8766]
    assert launch.said == [] and launch.asked == []   # never its own server


def test_a_launch_beside_a_running_background_copy_does_not_start_the_task(cfg, launch):
    launch.running = {"port": 8766, "version": "0.3.0", "pid": 1, "token": "t", "background": True}
    assert cli.serve(launch_args(), cfg) == 0
    assert launch.started == [] and launch.windows == [8766]


def test_when_it_does_not_start_the_owner_chooses_whether_to_open_it_on_its_own(cfg, launch):
    launch.comes_up = False
    assert cli.serve(launch_args(), cfg) == 6             # Not now: nothing starts, no server takes the port
    assert len(launch.asked) == 1 and "did not start within 90 seconds" in launch.asked[0]
    launch.answer = True
    assert cli.serve(launch_args(), cfg) == 2             # Open it: it goes on to serve by itself (stopped here)
    assert launch.said == ["this copy started its own server"]


def test_headless_it_says_what_to_do_instead_of_serving(cfg, launch, monkeypatch):
    launch.comes_up = False
    launch.answer = None
    assert cli.serve(launch_args(no_tray=True), cfg) == 6
    assert "Open Nines again in a minute" in launch.said[0]


def test_a_hand_over_waits_for_the_copy_that_started_it(cfg, launch):
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(1)"])
    threading.Thread(target=proc.wait, daemon=True).start()   # reaped as soon as it ends, as on Windows
    t = time.monotonic()
    assert cli.serve(launch_args(after=proc.pid), cfg) == 0
    assert time.monotonic() - t >= 0.5 and proc.poll() is not None
    assert launch.windows == [8766]


# ------------------------------------------------------------------ the hand-over itself, with the real server
def test_turning_it_on_lets_go_of_the_port_and_starts_the_program_afresh(cfg, windows, program, monkeypatch):
    from .test_window import args, health, wait_for
    started = []
    monkeypatch.setattr(sys, "executable", str(program))
    monkeypatch.setattr(cli, "_start_successor", lambda after, *extra: started.append(after))
    monkeypatch.setattr(background, "task_data_dir", lambda marker: cfg.data_dir)
    monkeypatch.setattr(cli, "_carry_over_start_at_login", lambda: None)
    real_build = app_module.build_services
    from .conftest import FakeClaude, fake_cutter
    claude = FakeClaude()
    monkeypatch.setattr(app_module, "build_services",
                        lambda c: real_build(c, cutter=fake_cutter, web_dir=None, tagger=claude,
                                             routes=lambda: claude.routes(), corrector=claude.correct))
    a = args(tray=False, browser=True)   # the browser stands in for the window here: none is made
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: None)
    seen = {}

    def drive():
        wait_for(lambda: instance.running_info(cfg) is not None, 30, "Nines to start")
        key = State(cfg.state_path).get("window_key")
        jar = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
        jar.open(f"http://127.0.0.1:{a.port}/?key={key}", timeout=5).read()

        def post(path, body=None):
            req = urllib.request.Request(f"http://127.0.0.1:{a.port}{path}", method="POST",
                                         data=json.dumps(body or {}).encode(),
                                         headers={gate.CLIENT_HEADER: "1", "Content-Type": "application/json"})
            with jar.open(req, timeout=10) as r:
                return r.status, json.loads(r.read() or b"null")
        seen["on"] = post("/api/background/on")
        wait_for(lambda: not health(a.port), 15, "the ordinary copy to let go of the port")
    t = threading.Thread(target=drive, daemon=True)
    t.start()
    assert cli.serve(a, cfg) == 0
    t.join(30)
    assert seen["on"][0] == 200 and seen["on"][1]["handing_over"] is True
    assert started == [os.getpid()]   # a fresh launch, which waits for this process before it starts the task
    assert background.read_marker()["port"] == a.port
    assert not cfg.lock_path.exists()


# ------------------------------------------------------------------ updates through the task
def _plan(tmp_path, cfg, **kw):
    installed = tmp_path / "Nines" / "Nines.exe"
    installed.parent.mkdir(parents=True, exist_ok=True)
    installed.write_bytes(b"new")
    (tmp_path / "Nines" / "Nines.old.exe").write_bytes(b"old")
    return {"from": "0.3.0", "to": "0.4.0", "platform": "win32", "installed": str(installed),
            "old": str(installed.with_name("Nines.old.exe")), "inner": ".", "args": ["--background", "--port", "8766"],
            "old_pid": 4242, "data_dir": str(cfg.data_dir), "timeout": 1, "snapshots": {}, "via_task": True, **kw}


def test_a_background_copy_comes_back_through_the_task_after_an_update(cfg, tmp_path, monkeypatch):
    events, now = [], {"version": "0.3.0", "pid": 4242}
    monkeypatch.setattr(updates, "in_job", lambda: False)   # the helper left the task's job (CI's own runner is in one)
    monkeypatch.setattr(instance, "running_info", lambda c: {"port": 8766, "version": now["version"], "pid": now["pid"],
                                                             "token": "t", "background": True})
    monkeypatch.setattr(instance, "stop_running", lambda c, info, **k: events.append(("quit", info["pid"])) or True)
    monkeypatch.setattr(instance, "_pid_alive", lambda pid: False)

    def run_task():
        events.append("task")
        now.update(version="0.4.0", pid=5151)
        return True
    monkeypatch.setattr(background, "run_task", run_task)
    assert updates.watch(cfg, _plan(tmp_path, cfg), poll=0.01)
    assert events == [("quit", 4242), "task"]   # the old copy makes way first: the task starts nothing beside it
    assert json.loads(updates.outcome_path(cfg).read_text())["ok"] is True


def test_a_new_version_that_does_not_answer_is_put_back_and_started_through_the_task(cfg, tmp_path, monkeypatch):
    events = []
    monkeypatch.setattr(updates, "in_job", lambda: False)   # the helper left the task's job (CI's own runner is in one)
    monkeypatch.setattr(instance, "running_info", lambda c: None)
    monkeypatch.setattr(instance, "_pid_alive", lambda pid: False)
    monkeypatch.setattr(background, "run_task", lambda: events.append("task") or True)
    monkeypatch.setattr(background, "end_task", lambda: events.append("end"))
    plan = _plan(tmp_path, cfg)
    assert not updates.watch(cfg, plan, poll=0.01)
    assert events == ["task", "end", "task"]
    assert Path(plan["installed"]).read_bytes() == b"old"
    assert "was put back and started again" in json.loads(updates.outcome_path(cfg).read_text())["note"]


def test_an_update_of_the_tasks_copy_says_so_in_its_plan(cfg, tmp_path, monkeypatch):
    exe = tmp_path / "Nines" / "Nines.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"old")
    (cfg.data_dir / "updates").mkdir(parents=True)
    new = b"new program"
    package = tmp_path / "download.exe"
    package.write_bytes(new)
    state = State(cfg.state_path)
    plans = []
    u = updates.Updater(cfg, state, version="0.3.0", platform="win32", frozen=True, executable=str(exe),
                        spawn=lambda program, path: plans.append(json.loads(Path(path).read_text())))
    u.through_task = True
    monkeypatch.setattr(u, "prepare", lambda release: package)
    state.update(update_ready={"version": "0.4.0", "path": str(package), "sha256": hashlib.sha256(new).hexdigest()})
    u.install({"version": "0.4.0"})
    assert plans[0]["via_task"] is True and plans[0]["timeout"] == updates.START_THROUGH_TASK
    assert exe.read_bytes() == new and exe.with_name("Nines.old.exe").read_bytes() == b"old"


def test_the_helper_leaves_the_tasks_job_where_windows_allows(monkeypatch):
    calls = []

    def popen(command, **kw):
        calls.append(kw.get("creationflags"))
        if kw.get("creationflags", 0) & updates.BREAKAWAY and len(calls) == 1:
            raise OSError("access denied")   # a job that does not allow it
        return SimpleNamespace(pid=1)
    monkeypatch.setattr(updates.os, "name", "nt")
    updates.spawn_detached(["helper"], popen=popen)
    assert calls == [updates.DETACHED | updates.BREAKAWAY, updates.DETACHED]


def test_after_the_update_the_helper_finds_a_closet_the_new_copy_moved_to_nines(cfg, tmp_path, monkeypatch):
    old = Config(tmp_path / "Closet")
    seen = []
    monkeypatch.setattr(instance, "running_info", lambda c: seen.append(c.data_dir.name) or
                        ({"version": "0.4.0", "pid": 2} if c.data_dir.name == "Nines" else None))
    assert updates._running(old, {"via_task": True})["version"] == "0.4.0" and seen == ["Closet", "Nines"]
    assert updates._running(old, {}) is None


def test_a_newer_program_moves_the_background_copy_to_itself(cfg, windows, program, monkeypatch):
    exe = background.installed_exe()
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"older program")
    plans = []
    monkeypatch.setattr(updates, "watch", lambda c, plan: plans.append(plan) or True)
    moved, note = background.move_to(cfg, {"version": "0.3.0", "pid": 77}, program, "0.4.0")
    assert moved and note is None
    assert exe.read_bytes() == b"the program" and exe.with_name("Nines.old.exe").read_bytes() == b"older program"
    assert plans[0]["via_task"] is True and plans[0]["old_pid"] == 77 and plans[0]["to"] == "0.4.0"


def test_a_newer_program_asks_before_moving_the_background_copy(cfg, monkeypatch):
    info = {"port": 8766, "version": "0.3.0", "pid": 77, "token": "t", "background": True}
    monkeypatch.setattr(cli, "__version__", "0.4.0")
    monkeypatch.setattr(background, "is_set_up", lambda c: True)
    monkeypatch.setattr(background, "installed_exe", lambda: Path("/elsewhere/Nines.exe"))
    asked, moved = [], []
    monkeypatch.setattr(cli, "_ask", lambda q, yes, no, headless=False: asked.append((q, yes, no)) or False)
    monkeypatch.setattr(background, "move_to", lambda *a: moved.append(a) or (True, None))
    assert cli._offer_to_move(SimpleNamespace(no_tray=False), cfg, info) is info
    assert asked == [("Nines 0.3.0 is running in the background. This is Nines 0.4.0.\n\nMove the background copy to "
                      "0.4.0? Your closet is kept either way.", "Use 0.4.0", "Keep 0.3.0")] and moved == []
    monkeypatch.setattr(cli, "_ask", lambda *a, **k: True)
    monkeypatch.setattr(instance, "running_info", lambda c: dict(info, version="0.4.0"))
    assert cli._offer_to_move(SimpleNamespace(no_tray=False), cfg, info)["version"] == "0.4.0" and len(moved) == 1


# ------------------------------------------------------------------ the real thing, on the CI's Windows runner only
@pytest.mark.windows
@pytest.mark.skipif(not os.environ.get("CI"), reason="registers a real scheduled task: only on the CI's runner")
def test_a_real_task_starts_the_background_copy_and_starts_it_again_after_it_is_killed(tmp_path):
    """On GitHub's Windows runner, whose account is an administrator: the real install script (run without the prompt,
    since the account already has the rights) registers a task under a name of its own that runs this Python with
    `-m closet --background` on a temporary data folder; the task's copy answers, is killed, and the task starts it
    again (by hand here: the repeating trigger's few minutes are too long for CI, and are checked in the script)."""
    from .test_window import free_port
    port = free_port()
    data = tmp_path / "closet data"
    cfg = Config(data_dir=data, port=port)
    name = f"Nines-test-{uuid.uuid4().hex[:8]}"
    backend = Path(__file__).resolve().parents[1]
    arguments = subprocess.list2cmdline(["-m", "closet", "--background", "--port", str(port),
                                         "--home", str(Path.home()), "--data-dir", str(data)])
    result = tmp_path / "result.json"
    script = background.install_script(Path(sys.executable), arguments, background.windows_user(), result,
                                       workdir=backend).replace(f"$TaskName = {background._ps(background.TASK_NAME)}",
                                                                f"$TaskName = {background._ps(name)}")
    # keep_exe: never this very Python's processes or its file; the removal only stops and removes the test's task
    removal = background.uninstall_script(Path(sys.executable), result, keep_exe=True).replace(
        f"$TaskName = {background._ps(background.TASK_NAME)}", f"$TaskName = {background._ps(name)}")
    assert "$KeepExe = $true" in removal and name in script and name in removal
    print(f"\nWindows scheduled task test: registering {name} as {background.windows_user()}", flush=True)
    try:
        outcome = background.elevated(script, result, elevate=False)
        if outcome["starts"] != "startup":
            pytest.skip("the install script chose sign-in mode: its throwaway S4U task (whoami, run as this runner's "
                        "account without a sign-in) did not finish with result 0, so the real task would only start "
                        "at sign-in and cannot be started here")

        def run():
            return subprocess.run(["schtasks", "/Run", "/TN", name], capture_output=True, text=True).returncode == 0
        assert run()
        first = background.wait_for(cfg, timeout=120, poll=1)
        assert first and first["background"], "the task's copy did not answer within two minutes"
        updates._kill(first["pid"])
        deadline = time.monotonic() + 60
        while instance.running_info(cfg) is not None and time.monotonic() < deadline:
            time.sleep(1)
        assert instance.running_info(cfg) is None
        assert run()
        second = background.wait_for(cfg, timeout=120, poll=1)
        assert second and second["pid"] != first["pid"], "the task did not start the copy again"
    finally:
        info = instance.running_info(cfg)
        if info:
            instance.stop_running(cfg, info, timeout=20)
        subprocess.run(["schtasks", "/End", "/TN", name], capture_output=True)
        try:
            background.elevated(removal, result, elevate=False)
        finally:
            subprocess.run(["schtasks", "/Delete", "/TN", name, "/F"], capture_output=True)


# ------------------------------------------------------------------ review faults
def _lock_free(cfg) -> bool:
    try:
        with instance.startup_lock(cfg, timeout=0.3):
            return True
    except TimeoutError:
        return False


def test_1_moving_the_background_copy_happens_with_the_startup_lock_let_go(cfg, monkeypatch):
    """The new copy, started through the task, takes the startup lock: the move must not hold it."""
    older = {"port": 8766, "version": "0.3.0", "pid": 77, "token": "t", "background": True}
    now = {"info": older}
    seen = {}
    monkeypatch.setattr(cli, "__version__", "0.4.0")
    monkeypatch.setattr(background, "is_set_up", lambda c: True)
    monkeypatch.setattr(background, "installed_exe", lambda: Path("/elsewhere/Nines.exe"))
    monkeypatch.setattr(instance, "running_info", lambda c: now["info"])
    monkeypatch.setattr(cli, "_ask", lambda *a, **k: True)

    def move_to(c, info, exe, version):
        seen["free while moving"] = _lock_free(cfg)
        now["info"] = dict(older, version="0.4.0", pid=78)
        return True, None
    monkeypatch.setattr(background, "move_to", move_to)
    monkeypatch.setattr(cli, "_window_only", lambda a, c, info, release: seen.setdefault("window", info["version"]) and 0)
    assert cli.serve(launch_args(), cfg) == 0
    assert seen == {"free while moving": True, "window": "0.4.0"}


def test_1_a_message_said_while_starting_is_shown_once_the_startup_lock_is_let_go(cfg, monkeypatch):
    shown = []
    monkeypatch.setattr(cli, "_tell", lambda message: shown.append((message, _lock_free(cfg))))
    monkeypatch.setattr(instance, "running_info", lambda c: None)

    def failing(c):
        raise RuntimeError("Nines could not open your closet.")
    monkeypatch.setattr(app_module, "build_services", failing)
    assert cli.serve(launch_args(port=8799), cfg) == 2
    assert shown == [("Nines could not open your closet.", True)]


def test_2_on_its_own_runs_the_newer_copy_windows_keeps_rather_than_this_older_file(cfg, launch, monkeypatch):
    launch.comes_up = False
    launch.answer = True
    started = []
    monkeypatch.setattr(background, "installed_is_newer", lambda version: True)
    monkeypatch.setattr(cli, "_start_program", lambda program, *extra: started.append((program, extra)))
    assert cli.serve(launch_args(), cfg) == 0
    assert started == [(background.installed_exe(), ("--on-its-own",))]
    assert launch.said == []   # this older file never opened the closet


def test_2_on_its_own_the_copy_started_does_not_wait_for_the_background_copy_again(cfg, launch):
    assert cli.serve(launch_args(on_its_own=True), cfg) == 2   # it serves (stopped here) without starting the task
    assert launch.started == [] and launch.said == ["this copy started its own server"]


def test_2_turning_off_puts_the_newer_program_in_place_of_the_owners(windows, program, home_cfg, monkeypatch):
    windows.autostart = True
    monkeypatch.setattr(sys, "executable", str(program))
    monkeypatch.setattr(background, "__version__", "0.3.0", raising=False)
    background.turn_on(home_cfg, program, home_cfg.port)
    background.installed_exe().write_bytes(b"the newer program")   # the copy Windows ran updated itself
    background.note_version("0.4.0")
    carried = background.turn_off(home_cfg)
    assert carried.program == program and program.read_bytes() == b"the newer program"
    assert program.with_name("Nines.old.exe").read_bytes() == b"the program"
    assert "0.4.0" in carried.note and str(program.parent) in carried.note
    assert windows.autostart_exe == str(program) and not background.installed_exe().exists()


def test_2_when_the_owners_file_cannot_be_replaced_the_newer_copy_stays_and_carries_on(windows, program, home_cfg,
                                                                                       monkeypatch):
    monkeypatch.setattr(sys, "executable", str(program))
    monkeypatch.setattr(background, "__version__", "0.3.0", raising=False)
    background.turn_on(home_cfg, program, home_cfg.port)
    background.installed_exe().write_bytes(b"the newer program")
    background.note_version("0.4.0")

    def refuse(*a, **k):
        raise updates.UpdateError("no permission")
    monkeypatch.setattr(updates, "swap", refuse)
    carried = background.turn_off(home_cfg)
    assert "$KeepExe = $false" in windows.scripts[-1]   # its bytes were kept aside, and come back in its place
    assert carried.program == background.installed_exe() and carried.program.read_bytes() == b"the newer program"
    assert program.read_bytes() == b"the program" and str(background.install_dir()) in carried.note


def test_2_an_owner_program_as_new_as_the_copy_stays_as_it_is(windows, program, home_cfg, monkeypatch):
    monkeypatch.setattr(sys, "executable", str(program))
    monkeypatch.setattr(background, "__version__", "0.4.0", raising=False)
    background.turn_on(home_cfg, program, home_cfg.port)
    carried = background.turn_off(home_cfg)
    assert carried.program == program and carried.note is None and program.read_bytes() == b"the program"
    assert "$KeepExe = $false" in windows.scripts[-1]


def test_2_the_marker_says_which_version_windows_runs(windows, program, home_cfg, monkeypatch):
    monkeypatch.setattr(background, "__version__", "0.3.0", raising=False)
    background.turn_on(home_cfg, program, home_cfg.port)
    assert background.read_marker()["version"] == "0.3.0" and not background.installed_is_newer("0.3.0")
    background.note_version("0.4.0")
    assert background.installed_is_newer("0.3.0") and not background.installed_is_newer("0.4.0")


class _Strict:
    """subprocess.run as it behaves on a Windows whose language is not English: text decoded strictly raises."""

    def __init__(self, stdout: bytes, code: int = 0, fail: Exception | None = None):
        self.stdout, self.code, self.fail, self.calls = stdout, code, fail, []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        if self.fail:
            raise self.fail
        if (kw.get("text") or kw.get("encoding")) and kw.get("errors") != "replace":
            raise UnicodeDecodeError("utf-8", self.stdout, 0, 1, "invalid start byte")
        out = self.stdout.decode("utf-8", "replace") if (kw.get("text") or kw.get("encoding")) else self.stdout
        return subprocess.CompletedProcess(cmd, self.code, out, out[:0])


def test_3_localized_windows_output_never_stops_a_launch_or_the_helper(monkeypatch):
    localized = "\"PC\\\\propriétaire\",\"S-1-5-21-1-2-3-1001\"\r\n".encode("cp1252")
    for code in (0, 1):
        monkeypatch.setattr(background.subprocess, "run", _Strict(b"\x82\x8a refus\xe9", code))
        assert background.run_task() is (code == 0)
        background.end_task()
    for failure in (OSError("no schtasks"), ValueError("anything")):
        monkeypatch.setattr(background.subprocess, "run", _Strict(b"", fail=failure))
        assert background.run_task() is False
        background.end_task()
    monkeypatch.setattr(background.subprocess, "run", _Strict(localized))
    assert background.windows_user() == "S-1-5-21-1-2-3-1001"   # the SID: ASCII, and no translation needed


def test_3_the_task_and_its_security_descriptor_name_the_account_by_its_sid():
    script = background.install_script(Path(r"C:\x\Nines.exe"), "--background", "S-1-5-21-1-2-3-1001", Path("r.json"))
    assert "NTAccount" not in script and "(A;;GRGX;;;$UserId)" in script


def test_4_after_a_failed_update_the_old_program_is_back_before_the_task_is_ended(cfg, tmp_path, monkeypatch):
    events = []
    monkeypatch.setattr(instance, "running_info", lambda c: None)
    monkeypatch.setattr(instance, "_pid_alive", lambda pid: False)
    monkeypatch.setattr(updates, "in_job", lambda: False)
    monkeypatch.setattr(background, "run_task", lambda: events.append("task") or True)
    monkeypatch.setattr(background, "end_task", lambda: events.append("end"))
    real_restore = updates.restore
    monkeypatch.setattr(updates, "restore", lambda where: events.append("restore") or real_restore(where))
    assert not updates.watch(cfg, _plan(tmp_path, cfg), poll=0.01)
    assert events == ["task", "restore", "end", "task"]


def test_4_a_helper_left_in_the_tasks_job_starts_the_programs_itself_and_never_ends_the_task(cfg, tmp_path, monkeypatch):
    events = []
    monkeypatch.setattr(instance, "running_info", lambda c: None)
    monkeypatch.setattr(instance, "_pid_alive", lambda pid: False)
    monkeypatch.setattr(updates, "in_job", lambda: True)
    monkeypatch.setattr(background, "run_task", lambda: events.append("task") or True)
    monkeypatch.setattr(background, "end_task", lambda: events.append("end"))
    monkeypatch.setattr(updates, "start_program", lambda where, args: events.append(("start", tuple(args))) or None)
    plan = _plan(tmp_path, cfg, args=["--background", "--port", "8766", "--home", "C:\\Users\\o"])
    assert not updates.watch(cfg, plan, poll=0.01)
    assert events == [("start", tuple(plan["args"])), ("start", tuple(plan["args"]))]


def test_4_a_background_copy_hands_its_task_arguments_to_an_update():
    a = SimpleNamespace(no_tray=True, tray=False, browser=False, background=True, home="C:\\Users\\o", data_dir=None)
    assert cli._launch_args(a, 8766) == ["--background", "--port", "8766", "--home", "C:\\Users\\o"]


def test_5_a_background_copy_waits_for_its_port_without_holding_the_startup_lock(cfg, monkeypatch):
    seen = []
    monkeypatch.setattr(instance, "running_info", lambda c: None)
    monkeypatch.setattr(instance, "port_free", lambda host, port: False)
    monkeypatch.setattr(instance, "wait_for_port", lambda host, port, timeout: seen.append(_lock_free(cfg)) or False)
    assert cli.serve(launch_args(background=True, port=8766), cfg) == 3
    assert seen == [True]


def test_6_a_hand_over_whose_old_copy_is_slow_to_go_still_starts_the_task(cfg, launch, monkeypatch):
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(3)"])
    threading.Thread(target=proc.wait, daemon=True).start()
    monkeypatch.setattr(cli, "AFTER_WAIT", 0.1)
    launch.running = {"port": 8766, "version": "0.3.0", "pid": proc.pid, "token": "t", "background": False}
    monkeypatch.setattr(cli, "_open_running", lambda *a: pytest.fail("the copy that is going was opened"))
    assert cli.serve(launch_args(after=proc.pid), cfg) == 0
    assert launch.started == [background.WAIT] and launch.windows == [8766]
    proc.kill()


def test_7_the_elevated_command_is_short_and_runs_only_the_bytes_it_checked(tmp_path, monkeypatch):
    long_local = tmp_path / ("o" * 180) / "AppData" / "Local"
    monkeypatch.setattr(background, "install_dir", lambda: long_local / "Nines")
    script = background.install_script(Path(r"C:\x\Nines.exe"), "--background --port 8766 --home C:\\Users\\o",
                                       "S-1-5-21-1-2-3-1001", long_local / "Nines" / "setup-result.json")
    path, command = background.launcher(script)
    assert len(command) < 2000
    digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    assert digest in command and command.count("ReadAllBytes") == 1 and "ScriptBlock" in command
    assert path.read_bytes() == script.encode("utf-8")


def test_8_when_windows_will_not_start_the_task_the_owner_is_asked_at_once(cfg, launch, monkeypatch):
    monkeypatch.setattr(background, "start_and_wait", lambda c, timeout: False)
    assert cli.serve(launch_args(), cfg) == 6
    assert len(launch.asked) == 1 and "Windows would not start" in launch.asked[0]


def test_8_a_refused_task_is_not_waited_for(cfg, monkeypatch):
    monkeypatch.setattr(background, "run_task", lambda: False)
    monkeypatch.setattr(background, "wait_for", lambda *a, **k: pytest.fail("waited for a task Windows refused"))
    assert background.start_and_wait(cfg) is False


def test_9_the_task_runs_at_normal_priority():
    script = background.install_script(Path(r"C:\x\Nines.exe"), "--background", "S-1-5-21-1", Path("r.json"))
    settings = script[script.index("New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable"):]
    assert "-Priority 4" in settings.split("Register-ScheduledTask")[0]
