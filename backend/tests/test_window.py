"""Closet's own window, with the window library and the tray faked: no real window is ever opened here.

The window is pywebview in the program (closet/window.py). These tests stand in for it with `FakeToolkit` and for the
tray icon with `FakeIcon`, and run the real launcher (`cli.serve`) and the real server around them.
"""
import inspect
import json
import logging
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest

from closet import app as app_module
from closet import cli, instance, tray
from closet import window as app_window
from closet.config import Config
from closet.state import State

from .conftest import FakeClaude, fake_cutter

URL = "http://127.0.0.1:1/"


# ---------------------------------------------------------------- stand-ins
class FakeEvent:
    """Like pywebview's events: handlers are called in turn, given the window when they ask for it; set() is True when
    one of them returned False (for `closing`: keep the window open)."""

    def __init__(self, window):
        self.window = window
        self.items = []
        self._done = threading.Event()

    def __iadd__(self, item):
        self.items.append(item)
        return self

    def set(self, *args):
        answers = []
        for item in self.items:
            params = inspect.signature(item).parameters
            if "window" in params:
                answers.append(item(self.window, *args))
            elif not params:
                answers.append(item())
            else:
                answers.append(item(*args))
        self._done.set()
        return any(a is False for a in answers)

    def wait(self, timeout=None):
        return self._done.wait(timeout)

    def is_set(self):
        return self._done.is_set()


class FakeForm:
    """The WinForms form pywebview makes on Windows: only its FormClosing event."""

    class _Event:
        def __init__(self):
            self.handlers = []

        def __iadd__(self, handler):
            self.handlers.append(handler)
            return self

    def __init__(self):
        self.FormClosing = self._Event()


class FakeWindow:
    def __init__(self, toolkit, title, **options):
        self.toolkit, self.title, self.options = toolkit, title, options
        self.events = SimpleNamespace(**{name: FakeEvent(self) for name in (
            "closing", "before_show", "loaded", "shown", "minimized", "maximized", "restored")})
        self.native = FakeForm()
        self.on_screen = False
        self.loaded_urls = [options["url"]] if options.get("url") else []
        self.calls = []
        self.gone = threading.Event()

    # what Closet asks of it
    def show(self):
        self.calls.append("show")
        self.on_screen = True

    def hide(self):
        self.calls.append("hide")
        self.on_screen = False

    def destroy(self):
        self.calls.append("destroy")
        self.on_screen = False
        self.gone.set()

    def load_url(self, url):
        self.loaded_urls.append(url)
        if self.toolkit.page_loads:
            self.events.loaded.set()

    def restore(self):
        self.calls.append("restore")

    def maximize(self):
        self.calls.append("maximize")

    # what the owner and the computer do
    def close_button(self, reason="UserClosing"):
        """The owner clicks the window's Close button; on Windows `reason` is FormClosing's CloseReason."""
        if self.toolkit.platform == "win32":
            args = SimpleNamespace(CloseReason=reason, Cancel=False)
            for handler in self.native.FormClosing.handlers:
                handler(self.native, args)
            keep = args.Cancel
        else:
            keep = self.events.closing.set()
        if not keep:
            self.destroy()
        return not keep


class FakeToolkit:
    """Stands in for pywebview. `start()` "runs the loop" until the window is destroyed."""

    def __init__(self, renderer="edgechromium", platform="linux", page_loads=True, fail_init=None, fail_start=None):
        self.renderer, self.platform, self.page_loads = renderer, platform, page_loads
        self.fail_init, self.fail_start = fail_init, fail_start
        self.window = None
        self.started = threading.Event()
        self.start_args = None
        self.mac = []

    def initialize(self):
        if self.fail_init:
            raise self.fail_init
        return self.renderer

    def screen_size(self):
        return (1920, 1080)

    def create_window(self, title, **options):
        self.window = FakeWindow(self, title, **options)
        return self.window

    def start(self, storage_path, func):
        self.start_args = {"storage_path": storage_path}
        if self.fail_start:
            raise self.fail_start
        w = self.window
        w.events.before_show.set()
        if not w.options["hidden"]:
            w.on_screen = True
        w.events.shown.set()
        if self.page_loads:   # the page given, or pywebview's own blank page for a hidden window
            w.events.loaded.set()
        threading.Thread(target=func, daemon=True).start()
        self.started.set()
        if not w.gone.wait(30):
            raise AssertionError("the window's loop was never ended")

    def mac_prepare(self, on_reopen, on_terminate, dock):
        self.mac.append(("prepare", dock))
        self.reopen, self.terminate = on_reopen, on_terminate

    def mac_dock(self, shown):
        self.mac.append(("dock", shown))


class FakeIcon:
    """Stands in for the pystray icon: its menu's Open Closet and Quit Closet, and its loops."""

    def __init__(self, on_open, on_quit, *_):
        self.open, self.quit = on_open, on_quit
        self.detached = False
        self.ran = False
        self.stops = 0
        self.stopped = threading.Event()

    def run_detached(self):
        self.detached = True

    def run(self):
        self.ran = True
        self.stopped.wait(30)

    def stop(self):
        # pystray's plain X11 icon waits forever when stopped a second time after its loop has ended
        self.stops += 1
        assert self.stops == 1, "the tray icon was stopped twice"
        self.stopped.set()


class FakeMenuBarIcon(FakeIcon):
    """An icon whose loop is the window's (pystray on the Mac)."""
    __module__ = "pystray._darwin"


def wait_for(condition, timeout=10.0, what="it"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.02)
    raise AssertionError(f"timed out waiting for {what}")


@pytest.fixture
def window_at(tmp_path):
    """make() with the window's storage in a temporary folder."""
    def build(**kwargs):
        toolkit = kwargs.pop("toolkit", None) or FakeToolkit(**{k: kwargs.pop(k) for k in list(kwargs)
                                                                if k in ("renderer", "platform", "page_loads",
                                                                         "fail_init", "fail_start")})
        told = SimpleNamespace(quit=0, visible=[])

        def on_quit():
            told.quit += 1
        keep = kwargs.pop("keep_running", True)
        w = app_window.AppWindow(URL, tmp_path / "Closet" / "window", keep_running=lambda: keep, on_quit=on_quit,
                                 on_visible=told.visible.append, toolkit=toolkit, platform=toolkit.platform, **kwargs)
        return w, toolkit, told
    return build


def run_in_background(w):
    result = {}
    t = threading.Thread(target=lambda: result.setdefault("ended_by_quitting", w.run()), daemon=True)
    t.start()
    return t, result


# ---------------------------------------------------------------- the window on its own
def test_the_window_keeps_its_storage_in_the_closets_folder(cfg, window_at):
    assert cfg.window_dir == cfg.data_dir / "window"
    w, toolkit, _ = window_at()
    assert w.prepare()
    assert w.storage_dir.is_dir() and w.storage_dir.name == "window" and w.storage_dir.parent.name == "Closet"
    t, result = run_in_background(w)
    wait_for(toolkit.started.is_set)
    assert toolkit.start_args == {"storage_path": str(w.storage_dir)}
    w.close()
    t.join(5)
    assert result == {"ended_by_quitting": True}


def test_pywebview_is_started_with_storage_that_is_kept(monkeypatch, tmp_path):
    started = {}
    fake = SimpleNamespace(start=lambda **kw: started.update(kw))
    tk = app_window._Pywebview(tmp_path / "window")
    tk.webview = fake
    tk.start(str(tmp_path / "window"), func=print)
    assert started == {"func": print, "private_mode": False, "storage_path": str(tmp_path / "window")}


def test_the_window_is_titled_closet_and_fits_the_phone_layout(window_at):
    w, toolkit, _ = window_at()
    assert w.prepare()
    win = toolkit.window
    assert win.title == "Nines"
    assert win.options["text_select"] is True and win.options["url"] == URL and win.options["hidden"] is False
    assert win.options["min_size"][0] <= 400 and (win.options["width"], win.options["height"]) == app_window.SIZE
    assert app_window._fit((1280, 860), (1366, 768)) == (1229, 691)
    assert app_window._fit((1280, 860), (300, 300)) == app_window.MIN_SIZE
    assert app_window._fit((1280, 860), None) == (1280, 860)


def test_closing_the_window_hides_it_while_closet_keeps_running(window_at):
    w, toolkit, told = window_at()
    assert w.prepare()
    t, result = run_in_background(w)
    wait_for(toolkit.started.is_set)
    win = toolkit.window
    assert win.on_screen
    assert not win.close_button()           # kept open...
    wait_for(lambda: "hide" in win.calls)   # ...and hidden
    assert not win.on_screen and not w.visible and told.visible[-1] is False
    assert t.is_alive() and told.quit == 0  # the loop (and Closet) still runs
    assert w.show()                         # Open Closet
    wait_for(lambda: win.on_screen)
    assert w.visible and told.visible[-1] is True
    w.close()                               # Quit Closet
    t.join(5)
    assert "destroy" in win.calls and result == {"ended_by_quitting": True} and told.quit == 0


def test_without_a_tray_icon_closing_the_window_quits(window_at):
    w, toolkit, told = window_at(keep_running=False)
    assert w.prepare()
    t, result = run_in_background(w)
    wait_for(toolkit.started.is_set)
    assert toolkit.window.close_button()    # it closes...
    t.join(5)
    assert result == {"ended_by_quitting": True} and told.quit == 1   # ...and Closet quits


def test_on_windows_only_the_owner_closing_it_hides_it(window_at):
    w, toolkit, told = window_at(platform="win32")
    assert w.prepare()
    t, result = run_in_background(w)
    wait_for(toolkit.started.is_set)
    win = toolkit.window
    assert not win.events.closing.items              # watched on the form itself instead
    assert len(win.native.FormClosing.handlers) == 1
    assert not win.close_button("UserClosing")
    wait_for(lambda: "hide" in win.calls)
    assert t.is_alive()
    # Windows is shutting down: the window closes (it must not hold up the shutdown) and Closet quits
    assert win.close_button("WindowsShutDown")
    t.join(5)
    assert result == {"ended_by_quitting": True} and told.quit == 1


def test_what_windows_closes_by_itself():
    for reason in ("WindowsShutDown", "CloseReason.TaskManagerClosing", "ApplicationExitCall", 1, 4, "6"):
        assert app_window._windows_wants_it_closed(reason), reason
    for reason in ("UserClosing", "CloseReason.UserClosing", 3, "FormOwnerClosing", "None", "something new"):
        assert not app_window._windows_wants_it_closed(reason), reason


def test_quitting_closes_the_window_even_though_closing_it_only_hides_it(window_at):
    w, toolkit, told = window_at(platform="win32")
    assert w.prepare()
    t, result = run_in_background(w)
    wait_for(toolkit.started.is_set)
    w.close()   # what quit_program does; our own destroy() is a "UserClosing" on Windows
    assert toolkit.window.close_button("UserClosing")
    t.join(5)
    assert result == {"ended_by_quitting": True} and told.quit == 0


def test_started_at_login_the_window_is_hidden_and_loads_nothing_until_opened(window_at):
    w, toolkit, told = window_at(hidden=True)
    assert w.prepare()
    win = toolkit.window
    assert win.options["hidden"] is True and win.options["url"] is None
    t, result = run_in_background(w)
    wait_for(toolkit.started.is_set)
    assert not win.on_screen and win.loaded_urls == [] and not w.visible
    assert w.show()
    wait_for(lambda: win.on_screen)
    assert win.loaded_urls == [URL]    # loaded the first time it is opened
    w.hide()
    assert w.show()
    wait_for(lambda: win.on_screen)
    assert win.loaded_urls == [URL]    # and only then
    w.close()
    t.join(5)


def test_a_minimised_window_comes_back_when_opened(window_at):
    w, toolkit, _ = window_at()
    assert w.prepare()
    t, _ = run_in_background(w)
    wait_for(toolkit.started.is_set)
    win = toolkit.window
    win.events.minimized.set()
    assert w.show()
    wait_for(lambda: "show" in win.calls)
    assert win.calls[-2:] == ["restore", "show"]
    win.events.maximized.set()
    win.events.minimized.set()
    win.calls.clear()
    assert w.show()
    wait_for(lambda: "show" in win.calls)
    assert win.calls == ["maximize", "show"]
    w.close()
    t.join(5)


@pytest.mark.parametrize("problem", [
    {"fail_init": ModuleNotFoundError("No module named 'clr'")},
    {"fail_init": RuntimeError("You must have either QT or GTK with Python extensions installed")},
    {"renderer": "mshtml"},   # Windows without the Edge WebView2 Runtime
])
def test_no_usable_window_means_the_browser(window_at, caplog, problem):
    w, toolkit, _ = window_at(**problem)
    assert not w.prepare()
    assert not w.usable and not w.show()
    assert "the browser is used instead" in caplog.text
    if problem.get("renderer") == "mshtml":
        assert "WebView2 Runtime is not installed" in caplog.text
    assert w.run() is False


def test_a_window_that_cannot_start_means_the_browser(window_at, caplog):
    w, toolkit, _ = window_at(fail_start=OSError("WebView2 could not start"))
    assert w.prepare()
    assert w.run() is False
    assert not w.usable and not w.show()
    assert "WebView2 could not start" in caplog.text


def test_a_page_that_never_loads_means_the_browser(window_at, caplog):
    w, toolkit, _ = window_at(page_loads=False, load_within=0.2)
    assert w.prepare()
    assert w.run() is False
    assert "destroy" in toolkit.window.calls
    assert "did not load in its window" in caplog.text


def test_quit_before_the_window_is_made(window_at):
    w, toolkit, _ = window_at()
    assert w.prepare()
    w.close()
    assert w.run() is True
    assert not toolkit.started.is_set()


def test_the_mac_hides_the_dock_icon_with_the_window_and_quits_completely(window_at):
    w, toolkit, told = window_at(platform="darwin", hidden=True)
    stopped = []
    w.on_terminate = lambda: stopped.append(1)
    assert w.prepare()
    assert toolkit.mac == [("prepare", False)]   # started at login: no Dock icon
    t, result = run_in_background(w)
    wait_for(toolkit.started.is_set)
    toolkit.reopen()                             # the program double-clicked again: macOS tells this copy
    wait_for(lambda: toolkit.window.on_screen)
    assert ("dock", True) in toolkit.mac
    assert not toolkit.window.close_button()
    wait_for(lambda: toolkit.mac[-1] == ("dock", False))
    toolkit.terminate()                          # Cmd+Q, or logging out
    assert stopped == [1]
    assert toolkit.window.close_button()         # a Quit lets the window close
    t.join(5)
    assert result == {"ended_by_quitting": True}


# ---------------------------------------------------------------- the launcher with the window
def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def args(**kw):
    # the tray icon is off unless asked for (--tray); these tests ask for it, to check it still works when wanted
    return SimpleNamespace(**{"no_browser": False, "no_tray": False, "tray": True, "browser": False, "port": free_port(),
                              "replace": False, **kw})


def door(port, keyed):
    """What the real server answers: the plain address, the keyed one (which leads on to the plain one with a cookie),
    then the plain one again with that cookie."""
    def status(opener, url):
        try:
            with opener.open(url, timeout=5) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
    plain = f"http://127.0.0.1:{port}/api/session"
    jar = urllib.request.HTTPCookieProcessor()
    with_cookies = urllib.request.build_opener(jar)
    return {"plain": status(urllib.request.build_opener(), plain), "keyed": status(with_cookies, keyed),
            "after": status(with_cookies, plain)}


def health(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as r:
            return json.loads(r.read()).get("app") == "closet"
    except OSError:
        return False


def opened_at(cfg, port):
    """The address the launcher opens Closet at: its own, with the window's key that it keeps in the settings."""
    key = State(cfg.state_path).get("window_key")
    assert key
    return f"http://127.0.0.1:{port}/?key={key}"


def quit_from_settings(cfg, info):
    """Quit in Settings, as another copy asks for it: the real request, then wait until the server has gone.

    `stop_running` also waits for the copy's process to end, but here the copy runs inside this test process, which
    never ends; so it is not left to wait (timeout 0) and the test waits for what Quit does instead."""
    instance.stop_running(cfg, info, timeout=0)
    wait_for(lambda: instance.running_instance(cfg) is None, 10, "Closet to quit")


@pytest.fixture
def launcher(cfg, monkeypatch):
    """Runs the real launcher with a faked window, tray and browser; the server and its endpoints are the real ones."""
    real_build = app_module.build_services
    claude = FakeClaude()
    monkeypatch.setattr(app_module, "build_services",
                        lambda c: real_build(c, cutter=fake_cutter, web_dir=None, tagger=claude,
                                             routes=lambda: claude.routes(), corrector=claude.correct))
    # the launcher makes the window for this computer (on Windows, closing is watched on the form itself)
    env = SimpleNamespace(toolkit=FakeToolkit(platform=sys.platform), icons=[], opened=[], icon_class=FakeIcon)
    monkeypatch.setattr(app_window, "_Pywebview", lambda storage_dir: env.toolkit)
    monkeypatch.setattr(tray, "create", lambda *a: env.icons.append(env.icon_class(*a)) or env.icons[-1])
    monkeypatch.setattr(cli.webbrowser, "open", env.opened.append)
    handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}

    def run(a, drive):
        """cli.serve(a) on this (the main) thread, while `drive(env)` does what the owner does in another."""
        failure = []

        def driver():
            try:
                wait_for(lambda: instance.running_info(cfg) is not None, 30, "Closet to start")
                drive(env)
            except BaseException as e:   # noqa: B036 - reported below, after Closet has been made to quit
                failure.append(e)
                quit_anyway()

        def quit_anyway():
            info = instance.running_info(cfg)
            if info:
                instance.stop_running(cfg, info, timeout=10)
        t = threading.Thread(target=driver, daemon=True)
        t.start()
        code = cli.serve(a, cfg)
        t.join(30)
        if failure:
            raise failure[0]
        return code

    env.run = run
    env.quit = lambda info: quit_from_settings(cfg, info)
    yield env
    for sig, handler in handlers.items():
        signal.signal(sig, handler)


def test_launching_shows_the_window_and_quit_stops_everything(cfg, launcher):
    a = args()
    seen = {}

    def drive(env):
        wait_for(env.toolkit.started.is_set)
        win, icon = env.toolkit.window, env.icons[0]
        seen["first"] = (win.on_screen, win.loaded_urls, icon.detached, icon.ran)
        assert not win.close_button()                      # the owner closes the window
        wait_for(lambda: not win.on_screen)
        seen["closed"] = health(a.port)                    # the server (phone, backups) keeps going
        icon.open()                                        # Open Closet
        wait_for(lambda: win.on_screen)
        seen["door"] = door(a.port, opened_at(cfg, a.port))
        icon.quit()                                        # Quit Closet
    assert launcher.run(a, drive) == 0
    url = opened_at(cfg, a.port)                           # the window opens Closet with its key
    assert seen["first"] == (True, [url], True, False)     # the tray joins the window's loop instead of its own
    assert seen["closed"] is True
    assert seen["door"] == {"plain": 401, "keyed": 200, "after": 200}
    assert launcher.opened == []                           # never the browser
    assert "destroy" in launcher.toolkit.window.calls and launcher.icons[0].stops == 1
    assert not health(a.port) and not cfg.lock_path.exists()
    assert launcher.toolkit.start_args == {"storage_path": str(cfg.window_dir)}


def test_by_default_there_is_no_tray_icon_and_closing_the_window_keeps_closet_running(cfg, launcher):
    # the owner's choice: no icon near the clock or in the menu bar; the window comes back by opening the program again
    a = args(tray=False)
    seen = {}

    def drive(env):
        wait_for(env.toolkit.started.is_set)
        win = env.toolkit.window
        assert not win.close_button()                      # the owner closes the window: it is only hidden
        wait_for(lambda: not win.on_screen)
        seen["closed"] = health(a.port)                    # the phone and the nightly backup keep working
        info = instance.running_info(cfg)
        seen["shown"] = instance.show_running(info)        # opening the program again brings it back
        wait_for(lambda: win.on_screen)
        env.quit(info)                                     # Quit in Settings
    assert launcher.run(a, drive) == 0
    assert launcher.icons == []
    assert seen == {"closed": True, "shown": True}
    assert not health(a.port) and not cfg.lock_path.exists()


def test_started_at_login_no_window_opens(cfg, launcher):
    a = args(no_browser=True)

    def drive(env):
        wait_for(env.toolkit.started.is_set)
        win = env.toolkit.window
        assert win.options["hidden"] is True and not win.on_screen and win.loaded_urls == []
        env.icons[0].open()                                # until Open Closet
        wait_for(lambda: win.on_screen)
        env.icons[0].quit()
    assert launcher.run(a, drive) == 0
    assert launcher.opened == []


def test_a_second_launch_shows_the_running_copys_window(cfg, launcher):
    a = args(no_browser=True)

    def drive(env):
        wait_for(env.toolkit.started.is_set)
        win = env.toolkit.window
        assert not win.on_screen
        assert cli.serve(args(), cfg) == 0                 # double-clicked again while it runs
        wait_for(lambda: win.on_screen)
        assert env.opened == []
        env.icons[0].quit()
    assert launcher.run(a, drive) == 0


def test_the_window_endpoint_needs_this_copys_token(cfg, anon, services):
    services.on_show = lambda: True
    assert anon.post("/api/instance/show").status_code == 403
    instance.write_lock(cfg, 8765)
    token = json.loads(cfg.lock_path.read_text())["token"]
    assert anon.post("/api/instance/show", headers={instance.QUIT_HEADER: token + "x"}).status_code == 403
    r = anon.post("/api/instance/show", headers={instance.QUIT_HEADER: token})
    assert r.status_code == 200 and r.json() == {"shown": True}
    services.on_show = lambda: False
    assert anon.post("/api/instance/show", headers={instance.QUIT_HEADER: token}).json() == {"shown": False}


def test_a_copy_without_a_window_is_opened_in_the_browser(cfg, monkeypatch):
    opened = []
    monkeypatch.setattr(cli.webbrowser, "open", opened.append)
    monkeypatch.setattr(instance, "show_running", lambda info: False)   # no window there, or an older copy
    cli._open_running(cfg, {"port": 1, "token": None}, URL)             # a copy from before the key
    State(cfg.state_path).update(window_key="the-key")
    cli._open_running(cfg, {"port": 1, "token": None}, URL)             # with the key the running copy keeps
    monkeypatch.setattr(instance, "show_running", lambda info: True)
    cli._open_running(cfg, {"port": 1, "token": "t"}, URL)
    assert opened == [URL, URL + "?key=the-key"]


def test_an_older_copy_that_has_no_window_is_still_opened_in_the_browser(cfg, monkeypatch):
    # 0.2.0 and before have no token; a later copy from before the window answers 401 (it has no such call)
    assert not instance.show_running({"port": free_port(), "version": "0.1.1", "pid": 1, "token": None})
    assert not instance.show_running({"port": free_port(), "version": "0.4.0", "pid": 1, "token": "t"})


def test_without_a_tray_or_a_window_the_running_copy_says_so(cfg, launcher):
    a = args(no_tray=True, no_browser=True)

    def drive(env):
        info = instance.running_info(cfg)
        assert instance.show_running(info) is False        # so a second launch opens the browser
        env.quit(info)
    assert launcher.run(a, drive) == 0
    assert launcher.toolkit.window is None and launcher.icons == []
    assert not health(a.port) and not cfg.lock_path.exists()


def test_when_the_window_cannot_open_the_browser_opens_as_before(cfg, launcher):
    launcher.toolkit = FakeToolkit(fail_init=ModuleNotFoundError("No module named 'webview'"))
    a = args()

    def drive(env):
        wait_for(lambda: env.icons and env.icons[0].ran)   # the tray's own loop, as before
        assert env.opened == [opened_at(cfg, a.port)]
        env.icons[0].open()                                # Open Closet opens the browser too
        assert len(env.opened) == 2
        info = instance.running_info(cfg)
        assert instance.show_running(info) is False
        env.icons[0].quit()
    assert launcher.run(a, drive) == 0


def test_a_window_that_fails_while_starting_falls_back_to_the_browser(cfg, launcher):
    launcher.toolkit = FakeToolkit(fail_start=OSError("no WebView2"))
    launcher.icon_class = FakeMenuBarIcon   # its loop was to be the window's: it gets its own
    a = args()

    def drive(env):
        wait_for(lambda: env.icons and env.icons[0].ran)
        assert env.icons[0].detached
        assert env.opened == [opened_at(cfg, a.port)]
        env.icons[0].open()
        assert len(env.opened) == 2
        env.icons[0].quit()
    assert launcher.run(a, drive) == 0


def test_browser_flag_uses_the_browser(cfg, launcher):
    a = args(browser=True)

    def drive(env):
        wait_for(lambda: env.icons and env.icons[0].ran)
        env.icons[0].quit()
    assert launcher.run(a, drive) == 0
    assert launcher.toolkit.window is None and launcher.opened == [opened_at(cfg, a.port)]


def test_an_update_opens_the_window_only_when_it_was_showing():
    a = SimpleNamespace(no_tray=False, tray=False, browser=False)
    assert cli._launch_args(a, 8765) == ["--no-browser", "--port", "8765"]
    assert cli._launch_args(a, 8765, window_shown=True) == ["--port", "8765"]
    assert cli._launch_args(SimpleNamespace(no_tray=True, tray=False, browser=True), 9000) == [
        "--no-tray", "--browser", "--no-browser", "--port", "9000"]
    assert cli._launch_args(SimpleNamespace(no_tray=False, tray=True, browser=False), 9000) == ["--tray", "--no-browser", "--port", "9000"]


def test_the_icon_is_the_jacket_on_its_rounded_square_at_any_size():
    """The tray's and the packaged program's icon (closet/icon.png): a cream rounded square, transparent outside it,
    with the dark jacket in the middle."""
    for size in (16, 64, 256):
        im = tray.icon_image(size)
        assert im.size == (size, size) and im.mode == "RGBA"
    im = tray.icon_image(256)
    assert im.getpixel((0, 0))[3] == 0                      # a cut corner
    assert im.getpixel((128, 6))[:3] == (246, 242, 234)     # the cream square, top middle
    assert sum(im.getpixel((150, 140))[:3]) < 120            # the jacket's dark cloth


def test_the_tray_knows_whose_loop_it_runs_on():
    assert not tray.has_own_loop(FakeMenuBarIcon(None, None))
    assert tray.has_own_loop(FakeIcon(None, None))


class FakeX11Icon(FakeIcon):
    __module__ = "pystray._xorg"


def test_the_plain_x11_tray_runs_in_a_daemon_thread():
    icon = FakeX11Icon(None, None)
    tray.run_beside(icon)
    wait_for(lambda: icon.ran)
    assert not icon.detached   # pystray's run_detached() there leaves a thread waiting forever
    loop = next(t for t in threading.enumerate() if t.name == "tray")
    assert loop.daemon
    icon.stop()
    other = FakeIcon(None, None)
    tray.run_beside(other)
    assert other.detached


def test_selfcheck_finds_the_window_library(cfg):
    result = cli.selfcheck(False, cfg)
    assert result["window"]["ok"], result["window"]
    assert "pywebview 6.2.1" in result["window"]["detail"]


@pytest.mark.windows
def test_windows_has_the_edge_window():
    """On a real Windows: pywebview's WinForms window loads, and finds the Edge WebView2 Runtime."""
    from webview.platforms import winforms
    assert winforms.renderer == "edgechromium"
    assert "Edge WebView2" in app_window.check_bundled()


def test_config_window_dir_is_inside_the_data_folder(tmp_path):
    c = Config(data_dir=tmp_path / "Closet")
    assert c.window_dir.parent == c.data_dir



# ---------------------------------------------------------------- a background copy, and the window as its own program
def test_an_update_of_a_background_copy_starts_a_background_copy():
    a = SimpleNamespace(no_tray=True, tray=False, browser=False, background=True)
    assert cli._launch_args(a, 8765) == ["--background", "--port", "8765"]
    assert cli._launch_args(a, 8765, window_shown=True) == ["--background", "--port", "8765"]


def test_a_background_copy_shows_nothing_and_a_window_opens_onto_it(cfg, launcher):
    """The program opened beside a background copy is only a window onto it: opened again, it brings that window
    forward; closed, its process ends and the background copy keeps running until Quit in Settings."""
    a = args(background=True, tray=False)
    seen = {}

    def drive(env):
        info = instance.running_info(cfg)
        seen["lock"] = (info["background"], json.loads(cfg.lock_path.read_text()).get("background"))
        seen["nothing shown"] = (env.toolkit.window, env.icons, list(env.opened))
        ended = []
        opener = threading.Thread(target=lambda: ended.append(cli.serve(args(tray=False), cfg)), daemon=True)
        opener.start()                                     # the owner opens Nines
        wait_for(env.toolkit.started.is_set)
        win = env.toolkit.window
        seen["window"] = (win.loaded_urls, win.on_screen, door(a.port, opened_at(cfg, a.port)))
        seen["window lock"] = json.loads(instance.window_lock_path(cfg).read_text())["pid"] == os.getpid()
        shows = win.calls.count("show")
        assert cli.serve(args(tray=False), cfg) == 0       # opened again: the same window comes forward
        wait_for(lambda: win.calls.count("show") > shows)
        seen["one window"] = env.toolkit.window is win
        assert win.close_button()                          # the owner closes it: it closes, it is not hidden
        opener.join(10)
        seen["closed"] = (ended, instance.window_lock_path(cfg).exists(), health(a.port))
        env.quit(info)                                     # Quit in Settings stops the background copy
    assert launcher.run(a, drive) == 0
    assert seen["lock"] == (True, True)
    assert seen["nothing shown"] == (None, [], [])
    assert seen["window"] == ([opened_at(cfg, a.port)], True, {"plain": 401, "keyed": 200, "after": 200})
    assert seen["window lock"] and seen["one window"]
    assert seen["closed"] == ([0], False, True)            # the window's process ended; the background copy did not
    assert launcher.opened == []                           # never the browser
    assert not health(a.port) and not cfg.lock_path.exists()


@pytest.fixture(params=["linux", "win32"])
def beside_background(cfg, monkeypatch, request):
    """A background copy as the launcher sees it (no server: the window is faked and loads nothing real). Run with the
    window on each way of closing: pywebview's `closing` event, and Windows' own (WinForms' FormClosing). The fake
    toolkit closes the window the way the window's platform does, as on the real computer."""
    State(cfg.state_path).update(window_key="the-key")
    platform = request.param
    real_window = app_window.AppWindow
    monkeypatch.setattr(app_window, "AppWindow", lambda *a, **k: real_window(*a, platform=platform, **k))
    env = SimpleNamespace(toolkit=FakeToolkit(platform=platform), opened=[], version="0.3.0")
    monkeypatch.setattr(cli, "__version__", "0.3.0")
    monkeypatch.setattr(app_window, "_Pywebview", lambda storage_dir: env.toolkit)
    monkeypatch.setattr(cli.webbrowser, "open", env.opened.append)
    monkeypatch.setattr(instance, "running_info", lambda c: {"port": 1, "version": env.version, "pid": 1, "token": "t",
                                                             "background": True})
    monkeypatch.setattr(instance, "show_running", lambda info: pytest.fail("a background copy has no window to show"))
    monkeypatch.setattr(instance, "stop_running", lambda *a, **k: pytest.fail("a background copy is not replaced here"))
    monkeypatch.setattr(cli, "_ask", lambda *a, **k: pytest.fail("nothing to ask"))
    handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    yield env
    for sig, handler in handlers.items():
        signal.signal(sig, handler)


@pytest.mark.parametrize("running", ["0.3.0", "0.4.0", "0.2.0", "0.1.0-dev"])
def test_beside_a_background_copy_of_any_version_only_a_window_opens(cfg, beside_background, running, caplog):
    caplog.set_level(logging.INFO, logger="closet")
    beside_background.version = running
    toolkit = beside_background.toolkit
    closer = threading.Thread(target=lambda: wait_for(toolkit.started.is_set) or toolkit.window.close_button(), daemon=True)
    closer.start()
    assert cli.serve(args(tray=False), cfg) == 0
    closer.join(10)
    assert toolkit.window.loaded_urls == [URL + "?key=the-key"] and beside_background.opened == []
    assert ("was opened while an older background copy (0.2.0)" in caplog.text) is (running == "0.2.0")
    assert "the-key" not in caplog.text


def test_beside_a_background_copy_the_browser_opens_when_the_window_cannot(cfg, beside_background):
    beside_background.toolkit = FakeToolkit(fail_init=ModuleNotFoundError("No module named 'webview'"))
    assert cli.serve(args(tray=False), cfg) == 0
    beside_background.toolkit = FakeToolkit(fail_start=OSError("no WebView2"))
    assert cli.serve(args(tray=False), cfg) == 0
    assert beside_background.opened == [URL + "?key=the-key"] * 2
    assert not instance.window_lock_path(cfg).exists()
    assert cli.serve(args(tray=False, browser=True), cfg) == 0         # asked for the browser
    assert cli.serve(args(tray=False, no_browser=True), cfg) == 0      # started at login: nothing to show
    assert beside_background.opened == [URL + "?key=the-key"] * 3


def test_a_stale_window_lock_is_not_trusted(cfg):
    path = instance.window_lock_path(cfg)
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    gone = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, text=True)
    for lock in ("half a lock {", {"pid": int(gone.stdout), "port": free_port(), "token": "t"},   # its process ended
                 {"pid": os.getpid(), "port": free_port(), "token": "t"}):                       # nothing answers there
        path.write_text(lock if isinstance(lock, str) else json.dumps(lock))
        assert not instance.show_window_process(cfg, timeout=1)
    shows = []
    door_ = instance.WindowDoor(cfg, lambda: shows.append(1) or True)  # the next window writes its own over it
    try:
        assert instance.show_window_process(cfg) and shows == [1]
        wrong = dict(json.loads(path.read_text()), token="not-the-token")
        path.write_text(json.dumps(wrong))
        assert not instance.show_window_process(cfg) and shows == [1]  # only with its token
        path.write_text(json.dumps(dict(wrong, token=door_.token)))
    finally:
        door_.close()
    assert not path.exists() and not instance.show_window_process(cfg, timeout=1)
