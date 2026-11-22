"""The program's entry point (Nines.exe on Windows, Nines.app on the Mac, `python -m closet` from source).

    Nines                       start the app (what a double-click does)
    Nines --background          the server alone, with nothing shown (beside it, opening the app opens a window onto it)
    Nines restore <folder>      replace the closet with a backup
    Nines backup                back up now to the chosen folder
    Nines selfcheck             check that the bundled libraries work
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import logging.handlers
import os
import signal
import sys
import threading
import time
import webbrowser
from pathlib import Path
from types import SimpleNamespace

from . import APP_NAME, __version__, apikey, autostart, backup, config, datafolder, db, gate, instance
from . import background as kept_running
from .state import State

log = logging.getLogger("closet")

PORT_WAIT = 60.0   # seconds a background copy waits for its port to be let go of before it gives up
AFTER_WAIT = 30.0  # seconds a launch started by a hand-over waits for the copy that started it to have quit
# what `_serve` returns when Windows keeps Nines running but no background copy answers: `serve` starts it and waits
# for it outside the startup lock (the background copy takes that lock too), then tries again
AWAIT_BACKGROUND = -1
# what `_serve` returns when a newer program finds an older background copy that Windows keeps running: `serve` asks
# whether to move it to this version, and moves it, outside the startup lock (the new copy takes that lock as it starts)
MOVE_BACKGROUND = -2


LOG_FILE = "nines.log"
OLD_LOG_FILE = "closet.log"   # the log's name up to 0.13.0, when the program's words still said Closet
LOG_BACKUPS = 3


def _carry_over_log(logs: Path) -> str | None:
    """closet.log and its older parts become nines.log, once, before the log is opened, so the logs folder holds one
    name. Only when nines.log is not there yet. A part that cannot be renamed (another copy still has it open) stays as
    it is: it is only a log. What was done, for the log; None when there was nothing to do."""
    if (logs / LOG_FILE).exists() or not (logs / OLD_LOG_FILE).exists():
        return None
    kept = []
    for suffix in ("", *(f".{n}" for n in range(1, LOG_BACKUPS + 1))):
        old = logs / (OLD_LOG_FILE + suffix)
        if not old.exists():
            continue
        try:
            os.rename(old, logs / (LOG_FILE + suffix))
        except OSError:
            kept.append(old.name)
    if kept:
        return f"the log is now {LOG_FILE}; {', '.join(kept)} could not be renamed and was left as it is"
    return f"the log is now {LOG_FILE} (it was {OLD_LOG_FILE})"


def _setup_logging(cfg: config.Config, name: str = LOG_FILE) -> None:
    """`name`: a window onto a background copy logs to a file of its own, so two processes never rotate one file."""
    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    carried = _carry_over_log(cfg.logs_dir) if name == LOG_FILE else None
    handlers: list[logging.Handler] = [logging.handlers.RotatingFileHandler(
        cfg.logs_dir / name, maxBytes=1_000_000, backupCount=LOG_BACKUPS, encoding="utf-8")]
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", handlers=handlers)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    if carried:
        log.info("%s", carried)


# What the launcher says while it holds the startup lock is held back until it lets go of it: a message box waits for the
# owner, and every other launch, and the background copy Windows starts, waits for that lock meanwhile
_held: list[str] | None = None


def _say(message: str) -> None:
    """Tell the owner something even when there is no console window (once the startup lock is let go of)."""
    if _held is not None:
        _held.append(message)
        return
    _tell(message)


def _flush_held() -> None:
    global _held
    held, _held = _held, None
    for message in held or []:
        _tell(message)


def _tell(message: str) -> None:
    if sys.stdout is not None:
        print(message, flush=True)
    elif sys.platform == "win32":  # windowed build: no console, so use a message box
        try:
            _message_box(message, 0x40)  # MB_ICONINFORMATION
        except Exception:
            pass


def _message_box(text: str, flags: int) -> int:
    """Windows' own message box; returns the button pressed (IDYES is 6, IDNO 7), 0 when it could not be shown."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.MessageBoxW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT]
    user32.MessageBoxW.restype = ctypes.c_int
    return user32.MessageBoxW(None, text, APP_NAME, flags)


def _ask(question: str, yes: str, no: str, headless: bool = False) -> bool | None:
    """Ask the owner a yes-or-no question, in a window when there is no console.
    None when nobody can be asked (started at login without a tray, or no way to show a window)."""
    if headless:
        return None
    if sys.stdin is not None and sys.stdout is not None and sys.stdin.isatty():
        try:
            answer = input(f"{question}\n[y] {yes}   [n] {no}: ").strip().lower()
        except EOFError:
            return None
        return answer in ("y", "yes")
    if sys.platform == "win32":
        # MB_YESNO | MB_ICONQUESTION | MB_SETFOREGROUND | MB_TOPMOST; Windows only offers Yes and No
        flags = 0x4 | 0x20 | 0x10000 | 0x40000
        try:
            answer = _message_box(f"{question}\n\nYes: {yes}\nNo: {no}", flags)
        except Exception:
            return None
        return {6: True, 7: False}.get(answer)  # IDYES, IDNO; 0 when the box could not be shown
    if sys.platform == "darwin":
        import subprocess

        def quoted(s: str) -> str:
            return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
        script = (f"button returned of (display dialog {quoted(question)} with title {quoted(APP_NAME)} "
                  f"buttons {{{quoted(no)}, {quoted(yes)}}} default button {quoted(yes)} "
                  f"cancel button {quoted(no)} with icon note)")
        try:
            proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=600)
        except Exception:
            return None
        if proc.returncode == 0:
            return proc.stdout.strip() == yes
        return False if "-128" in (proc.stderr or "") else None  # -128: the owner chose the cancel button
    return None


def _follow_start_at_login() -> None:
    """After replacing an older copy, start at login opens this program, not the old one."""
    try:
        if autostart.program() and autostart.is_enabled():
            autostart.set_enabled(True)
            log.info("start at login now opens %s", autostart.program())
    except Exception:
        log.warning("could not point start at login to this program", exc_info=True)


_folder_moving: datafolder.Outcome | None = None   # what moving the data folder did at this start, for the log


def _running_in(folder: Path) -> bool:
    """Whether a copy of the program is serving from `folder` now, as its lock file and health check say."""
    return instance.running_info(config.Config(folder)) is not None


def _log_folder_moving() -> None:
    outcome = _folder_moving
    if outcome is not None and outcome.message:
        (log.info if outcome.kind == "moved" else log.warning)("data folder: %s", outcome.message)


def _carry_over_start_at_login() -> None:
    """Start at login written by Closet.exe (0.11.0 and before) would open a file that is gone: it now opens this one."""
    try:
        if autostart.carry_over():
            log.info("start at login carried over from Closet.exe to %s", autostart.program())
    except Exception:
        log.warning("could not carry start at login over to this program", exc_info=True)


def _carry_over_api_key() -> None:
    """An API key kept in the keychain under Closet (0.13.0 and before) is saved under Nines (closet/apikey.py)."""
    if apikey.carry_over():
        log.info("the API key in the keychain moved from the entry named Closet to the one named Nines")


def _open_running(cfg: config.Config, info: dict, url: str) -> None:
    """Opened again while a copy runs: that copy shows its window, or, when it has none (it uses the browser, or it is
    from before Nines had a window), the browser opens as it always did, at the address with the window's key."""
    if not instance.show_running(info):
        webbrowser.open(_keyed(cfg, url))


def _keyed(cfg: config.Config, url: str) -> str:
    """`url` with the key of Nines' own window (closet/gate.py) as the running copy keeps it in the settings; `url`
    alone when there is none (a copy from before the key) or the settings cannot be read."""
    try:
        key = State(cfg.state_path).get("window_key")
    except Exception:
        key = None
    return gate.keyed_url(url, key if isinstance(key, str) else None)


def _launch_args(args, port: int, window_shown: bool = False) -> list[str]:
    """How an update starts the new program: the way this one was started, on the same port, showing its window only
    when this one's is showing (an update never opens the browser; the page already open there reconnects). A background
    copy starts a background copy."""
    if getattr(args, "background", False):   # with what Windows' task gave it, for a helper that starts it directly
        return (["--background", "--port", str(port)] + (["--home", args.home] if getattr(args, "home", None) else [])
                + (["--data-dir", args.data_dir] if getattr(args, "data_dir", None) else []))
    return ((["--no-tray"] if args.no_tray else []) + (["--tray"] if args.tray else []) + (["--browser"] if args.browser else [])
            + ([] if window_shown else ["--no-browser"]) + ["--port", str(port)])


def serve(args, cfg: config.Config) -> int:
    global _held
    background = getattr(args, "background", False)
    if background:   # nothing shown and nobody asked: the paths of --no-tray --no-browser, with the log for what it says
        args.no_tray, args.no_browser, args.tray, args.browser = True, True, False, False
        _setup_logging(cfg)
        # its port is waited for before the startup lock is taken, so a launch meanwhile is not held up by it
        if instance.running_info(cfg) is None and not _wait_for_own_port(cfg.host, args.port or cfg.port):
            return 3
    after = getattr(args, "after", None)
    if after:   # started by a hand-over: the copy that started it lets go of the port first
        _wait_for_exit(after, AFTER_WAIT)
    launch = SimpleNamespace(alone="opened on its own" if getattr(args, "on_its_own", False) else None,
                             moved=False, awaited=False)
    for _ in range(4):
        _held = []
        try:
            with instance.startup_lock(cfg) as let_go:
                def release_startup() -> None:
                    let_go()
                    _flush_held()
                result = _serve(args, cfg, release_startup, launch)
        except TimeoutError as e:
            if background:
                log.error("%s", e)
            else:
                _say(str(e))
            return 2
        finally:
            _flush_held()
        if result == MOVE_BACKGROUND:
            launch.moved = True
            info = instance.running_info(cfg)
            if info and info.get("background"):
                _offer_to_move(args, cfg, info)
            continue
        if result != AWAIT_BACKGROUND:
            return result
        refused = False
        if not launch.awaited:
            launch.awaited = True
            found = kept_running.start_and_wait(cfg, kept_running.WAIT)
            if found:
                continue   # it answers now: this launch becomes a window onto it
            refused = found is False
        note = _background_did_not_start(args, refused)
        if note is None:
            return 6
        if kept_running.installed_is_newer(__version__):
            # the copy Windows runs updated itself past this program, which must not open the closet: the newer runs
            _start_program(kept_running.installed_exe(), "--on-its-own")
            return 0
        launch.alone = note
    return 6


def _wait_for_exit(pid: int, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while pid != os.getpid() and instance._pid_alive(pid) and time.monotonic() < deadline:
        time.sleep(0.1)


def _background_did_not_start(args, refused: bool = False) -> str | None:
    """Windows keeps Nines running, yet its background copy did not answer (or Windows would not start it at all, which
    is asked at once). The owner may open Nines on its own this time (it serves as before the switch, and Settings says
    the background copy is not running); otherwise nothing starts. Returns the note for the log when it opens on its
    own, None when it does not."""
    seconds = int(kept_running.WAIT)
    why = (f"Windows would not start {APP_NAME} in the background." if refused else
           f"{APP_NAME} is set to keep running in the background, but it did not start within {seconds} seconds.")
    answer = _ask(f"{why}\n\nOpen {APP_NAME} on its own for now? Settings, Other devices, then says what to do next.",
                  yes="Open it", no="Not now", headless=args.no_tray)
    if answer:
        return ("Windows would not start the background copy" if refused else
                f"the background copy did not answer within {seconds} seconds") + "; this copy serves on its own"
    if answer is None:
        _say(f"{why} Open {APP_NAME} again in a minute. The details are in nines.log in your data folder.")
    return None


def _start_successor(after: int, *extra: str) -> None:
    """Start this program afresh, as a double-click would; it waits until process `after` has quit. Used when this copy
    hands the port over to the background copy."""
    from . import updates
    me = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, "-m", "closet"]
    updates.spawn_detached([*me, "--after", str(after), *extra])


def _start_program(program, *extra: str) -> None:
    """Start another Nines program file, on its own (the newer copy in Nines' folder, or the one carrying on)."""
    from . import updates
    updates.spawn_detached([str(program), *extra])


def _log_error(message: str) -> None:
    log.error("%s", message)


def _wait_for_own_port(host: str, port: int) -> bool:
    """A background copy never moves to another port, because phone access is set up for its port: when the port is
    busy (an older copy still letting go of it, after an update or a restart), wait up to PORT_WAIT seconds for it."""
    if instance.port_free(host, port):
        return True
    log.warning("port %s is busy; waiting up to %g seconds for it", port, PORT_WAIT)
    if instance.wait_for_port(host, port, timeout=PORT_WAIT):
        return True
    log.error("port %s is still busy after %g seconds, so this background copy of %s stops without starting. It never "
              "moves to another port: phone access depends on port %s. Whatever started it can try again.",
              port, PORT_WAIT, APP_NAME, port)
    return False


def _beside_running(info: dict, wanted: int) -> int:
    """A background copy started while a copy already runs for this closet does not start a second server."""
    theirs = info["version"] or "an older version"
    if info["port"] == wanted:
        log.info("%s %s is already running on port %s; this background copy is not needed", APP_NAME, theirs, wanted)
        return 0
    log.error("%s %s is already running, on port %s instead of %s. Phone access depends on port %s, so this background "
              "copy stops; it can be started again once that copy has quit.", APP_NAME, theirs, info["port"], wanted, wanted)
    return 5


def _offer_to_move(args, cfg: config.Config, info: dict) -> dict:
    """A newer program opened beside an older background copy. When Windows keeps that copy running, the owner is
    asked whether to move it to this version (the way an update does it, through Windows' task, with no administrator
    prompt). Otherwise, or on No, this opens a window onto the older copy. Returns the copy to open a window onto.
    Called by `serve` outside the startup lock: the new copy Windows starts takes that lock."""
    theirs, mine = info["version"] or "an older version", __version__
    if not kept_running.is_set_up(cfg) or Path(sys.executable).resolve() == kept_running.installed_exe().resolve():
        log.info("%s %s was opened while an older background copy (%s) runs; it opens a window onto that copy",
                 APP_NAME, mine, theirs)
        return info
    move = _ask(f"{APP_NAME} {theirs} is running in the background. This is {APP_NAME} {mine}.\n\n"
                f"Move the background copy to {mine}? Your closet is kept either way.",
                yes=f"Use {mine}", no=f"Keep {theirs}", headless=args.no_tray)
    if not move:
        return info
    log.info("moving the background copy from %s to %s", theirs, mine)
    moved, note = kept_running.move_to(cfg, info, sys.executable, mine)
    if not moved:
        log.warning("the background copy was not moved to %s: %s", mine, note)
        _say(note or f"The background copy stayed on {theirs}.")
    return instance.running_info(cfg) or info


def _window_only(args, cfg: config.Config, info: dict, release_startup) -> int:
    """Opened while a background copy runs: this process is only a window onto that copy, and ends when the window is
    closed; the background copy keeps running. A window already open onto it is brought forward instead. When the
    window cannot be used, the browser opens at the keyed address, as before the window."""
    _setup_logging(cfg, "window.log")
    if instance.is_newer(__version__, info["version"]):
        log.info("%s %s was opened while an older background copy (%s) runs; it opens a window onto that copy",
                 APP_NAME, __version__, info["version"])
    if _kept_running(cfg):
        kept_running.note_program(sys.executable, __version__)
    if args.no_browser:   # started at login beside a background copy: nothing to show
        return 0
    if instance.show_window_process(cfg):
        return 0
    opened = _keyed(cfg, f"http://127.0.0.1:{info['port']}/")   # never logged or printed
    if args.browser:
        webbrowser.open(opened)
        return 0
    from . import window as app_window

    door = None

    def finish() -> None:
        if door is not None:
            door.close()

    def terminate() -> None:   # the Mac's Quit: everything stops before this returns
        window.close()
        finish()

    window = app_window.AppWindow(opened, cfg.window_dir, keep_running=lambda: False, on_terminate=terminate)
    if not window.prepare():
        webbrowser.open(opened)
        return 0
    def turn_off() -> bool:
        """Asked by the background copy when the owner turns it off in Settings: Windows asks on this screen, so it is
        done here. Once it is off, an ordinary copy of this program takes over and this window gives way to it."""
        def work() -> None:
            try:
                carried = kept_running.turn_off(cfg)
            except kept_running.SetupError as e:
                kept_running.note_outcome(cfg, str(e))
                return
            except Exception as e:
                log.exception("turning off the background copy failed")
                kept_running.note_outcome(cfg, f"Turning this off did not finish ({e}).")
                return
            try:   # the program that carries on: this one, or the newer one Windows kept up to date
                _start_program(carried.program, "--after", str(os.getpid()))
            except Exception:
                log.exception("could not start Nines again after turning off the background copy")
            if carried.note:
                _say(carried.note)
            window.close()
        threading.Thread(target=work, name="turn-off", daemon=True).start()
        return True

    door = instance.WindowDoor(cfg, window.show, {"off": turn_off})
    release_startup()
    log.info("%s %s opened a window onto the background copy (%s) on port %s", APP_NAME, __version__,
             info["version"] or "an older version", info["port"])
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, lambda *_: window.close())
        except (ValueError, OSError):
            pass
    ended_well = True
    try:
        ended_well = window.run()
    except KeyboardInterrupt:
        window.close()
    finally:
        finish()
    if not ended_well:   # the window went without being closed (it failed, or its page never loaded)
        webbrowser.open(opened)
    return 0


def server_config(app, host: str, port: int):
    """How uvicorn serves Nines. `proxy_headers` is off: uvicorn otherwise believes `X-Forwarded-For` on any
    connection from this computer (every connection to Nines is one, Tailscale Serve and Cloudflare's connector
    included), so whoever sent it would choose the address the Tailscale check asks Windows about (closet/tailnet.py)."""
    import uvicorn

    return uvicorn.Config(app, host=host, port=port, log_config=None, loop="asyncio", http="h11", ws="none",
                          lifespan="off", access_log=False, proxy_headers=False)


def _kept_running(cfg: config.Config) -> bool:
    try:
        return kept_running.is_set_up(cfg)
    except Exception:
        log.warning("could not tell whether Windows keeps Nines running", exc_info=True)
        return False


def _serve(args, cfg: config.Config, release_startup, launch=None) -> int:
    """`launch.alone`: Windows keeps Nines running but this copy opens on its own (its background copy did not start
    and the owner chose to); the reason, for the log. `launch.moved`: moving the background copy was offered already."""
    import uvicorn

    from .app import build_services, create_app

    background = getattr(args, "background", False)
    say = _log_error if background else _say   # a background copy shows nothing: what it would say goes in the log
    wanted = args.port or cfg.port
    replaced_older = False
    launch = launch or SimpleNamespace(alone=None, moved=False)
    alone = launch.alone
    already = instance.running_info(cfg)
    after = getattr(args, "after", None)
    if already and after and already.get("pid") == after and not background and _kept_running(cfg):
        already = None   # the copy that handed over is still going: the task is started, its copy waits for the port
    if already and already.get("background") and not background:
        if (not launch.moved and instance.is_newer(__version__, already["version"]) and _kept_running(cfg)
                and Path(sys.executable).resolve() != kept_running.installed_exe().resolve()):
            return MOVE_BACKGROUND
        return _window_only(args, cfg, already, release_startup)
    if already and background and not (args.replace and instance.is_newer(__version__, already["version"])):
        return _beside_running(already, wanted)
    if not already and not background and alone is None and _kept_running(cfg):
        return AWAIT_BACKGROUND   # never its own server: `serve` starts the background copy and waits for it
    if already:
        url = f"http://127.0.0.1:{already['port']}/"
        theirs = already["version"] or "an older version"
        if instance.is_newer(__version__, already["version"]):
            replace = True if args.replace else _ask(
                f"An older {APP_NAME} ({theirs}) is already running. This is {APP_NAME} {__version__}.\n\n"
                f"Close the old one and use {__version__} instead? Your closet is kept either way.",
                yes=f"Use {__version__}", no=f"Keep {theirs}", headless=args.no_tray)
            if replace:
                if instance.stop_running(cfg, already):
                    replaced_older = True
                else:
                    say(f"The older {APP_NAME} ({theirs}) did not close. Quit it from its icon "
                         f"(near the clock, or in the menu bar), then open {APP_NAME} {__version__} again.")
                    return 4
            else:
                if replace is None:
                    _say(f"An older {APP_NAME} ({theirs}) is already running at {url}. Quit it from its icon or "
                         f"from Settings, then open {APP_NAME} {__version__} again to use the new version.")
                if not args.no_browser:
                    _open_running(cfg, already, url)
                return 0
        if not replaced_older:
            if not args.no_browser:
                _open_running(cfg, already, url)
            if sys.stdout is not None:
                print(f"{APP_NAME} {theirs} is already running at {url}", flush=True)
            return 0

    if not background:   # a background copy set it up before the startup lock
        _setup_logging(cfg)
    _log_folder_moving()
    _carry_over_api_key()
    if alone:
        log.warning("%s", alone)
    if not background and not _kept_running(cfg):   # with the background copy on, start at login stays off
        _carry_over_start_at_login()
    if replaced_older:
        log.info("replaced an older copy (%s) with %s", already["version"], __version__)
        _follow_start_at_login()
        instance.wait_for_port(cfg.host, args.port or cfg.port)
    try:
        if background:
            port = wanted
            if not _wait_for_own_port(cfg.host, port):
                return 3
        else:
            port = args.port or instance.pick_port(cfg.host, cfg.port)
        cfg = config.Config(cfg.data_dir, cfg.host, port, cfg.auto_download_model)
        services = build_services(cfg)
    except db.NewerDatabaseError as e:
        say(str(e))
        return 2
    except RuntimeError as e:
        say(str(e))
        return 2

    # Nines' own window, the browser it falls back to and the tray open it with the key, which the server swaps for
    # a cookie; by this computer's own name nothing else gets in (closet/gate.py). Made once and kept in the settings.
    key = gate.window_key(services.state)
    app = create_app(services, window_key=key)
    server = uvicorn.Server(server_config(app, cfg.host, port))
    server.install_signal_handlers = lambda: None  # we run it off the main thread
    url = f"http://127.0.0.1:{port}/"
    opened = gate.keyed_url(url, key)   # never logged or printed: `url` is
    ui: dict = {}   # the tray icon and Nines' own window, once they are up

    def quit_program() -> None:
        server.should_exit = True
        window = ui.get("window")
        if window is not None:
            window.close()
        icon = ui.pop("icon", None)   # stopped once: a second stop() can wait forever on a loop that has ended
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass

    def show_window() -> bool:
        """Show Nines' own window; False when there is none and the browser should be opened instead."""
        window = ui.get("window")
        return window is not None and window.show()

    def open_closet() -> None:   # the tray's "Open Nines"
        if not show_window():
            webbrowser.open(opened)

    def hand_over() -> None:
        """Windows keeps Nines running now (or should start it again): this ordinary copy lets go of the port, and a
        fresh launch of this program starts the background copy, waits for it and opens a window onto it."""
        try:
            _start_successor(os.getpid())
        except Exception:
            log.exception("could not start Nines again to hand over to the background copy")
            return
        quit_program()

    services.on_quit = quit_program
    services.on_show = show_window
    services.on_hand_over = hand_over
    services.background_copy = background
    if services.updater is not None:   # an update starts the new program the way this one was started
        services.updater.launch_args = _launch_args(args, port)
        # a background copy Windows keeps running comes back through its task, from its own folder
        services.updater.through_task = background and _kept_running(cfg) and \
            Path(sys.executable).resolve() == kept_running.installed_exe().resolve()
        if services.updater.through_task:
            kept_running.note_version(__version__)   # so an older program the owner opens knows it is older
    thread = threading.Thread(target=server.run, name="server", daemon=True)
    thread.start()
    deadline = time.time() + 30
    while not server.started and thread.is_alive() and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        say(f"{APP_NAME} could not start on port {port}. Is another program using it?")
        return 3
    instance.write_lock(cfg, port, background=background)
    services.start()
    release_startup()
    log.info("%s %s serving on %s (data folder: %s)", APP_NAME, __version__, url, cfg.data_dir)
    if port != wanted:
        log.warning("port %s was busy; using %s. Phone access set up for the usual port will not reach this one.",
                    wanted, port)
    if sys.stdout is not None:
        print(f"{APP_NAME} is running at {url}  (quit from Settings, or Ctrl+C)", flush=True)

    stopping = threading.Lock()

    def shut_down() -> None:
        """Stop the server and the background work and let go of the closet, once, whoever gets here first."""
        if not stopping.acquire(blocking=False):
            return
        server.should_exit = True
        thread.join(timeout=10)
        services.stop()
        instance.clear_lock(cfg)

    def quit_now() -> None:   # the Mac's Quit (Cmd+Q, logging out): macOS ends the program as soon as this returns
        quit_program()
        shut_down()

    # Nines' own window, unless it was asked for the browser or runs with neither a tray nor a window (the smoke
    # test, the browser tests). Started at login (--no-browser) it is made hidden, for "Open Nines" to show.
    window = None
    if not args.browser and not (args.no_tray and args.no_browser):
        from . import window as app_window

        def window_shown(shown: bool) -> None:
            if services.updater is not None:
                services.updater.launch_args = _launch_args(args, port, window_shown=shown)

        window = app_window.AppWindow(opened, cfg.window_dir, hidden=args.no_browser,
                                      keep_running=lambda: True, on_quit=quit_program,
                                      on_visible=window_shown, on_terminate=quit_now)
        if window.prepare():
            ui["window"] = window
            window_shown(window.visible)
        else:
            window = None
    if window is None and not args.no_browser:
        webbrowser.open(opened)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, lambda *_: quit_program())
        except (ValueError, OSError):
            pass

    icon = None
    if args.tray and not args.no_tray:   # no icon near the clock or in the menu bar unless asked for (the owner's choice)
        from . import tray
        icon = tray.create(open_closet, quit_program,
                           lambda: autostart.is_enabled() if autostart.program() else None, autostart.set_enabled)
    try:
        if window is not None:
            # The window's loop runs on the main thread; the tray joins it or runs beside it (see closet/window.py).
            if icon is not None:
                try:
                    tray.run_beside(icon)
                    ui["icon"] = icon
                except Exception:
                    log.info("tray icon unavailable; continuing without it")
                    icon = None
            if not window.run():   # the window has gone without Nines quitting: use the browser from now on
                ui.pop("window", None)
                if not server.should_exit:
                    if window.visible:
                        webbrowser.open(opened)
                    if icon is not None and not tray.has_own_loop(icon):
                        icon.run()   # the tray was riding on the window's loop; it needs its own now
        elif icon is not None:
            ui["icon"] = icon
            try:
                icon.run()  # blocks on the main thread until Quit
            except Exception:
                log.info("tray icon unavailable; continuing without it")
        while thread.is_alive():
            thread.join(timeout=0.5)
    except KeyboardInterrupt:
        quit_program()
    finally:
        quit_program()   # stops a tray icon still running in its own thread, which would keep the program alive
        shut_down()
    return 0


def cmd_restore(args, cfg: config.Config) -> int:
    if instance.running_instance(cfg):
        _say(f"{APP_NAME} is running. Quit it first (Settings, Quit), then restore.")
        return 1
    try:
        earlier = backup.recover(cfg)   # a restore cut short before is put right first
        if earlier:
            _say(earlier["message"])
        result = backup.restore(cfg, Path(args.folder).expanduser(), args.snapshot)
    except (backup.BackupError, backup.RecoveryError) as e:
        _say(str(e))
        return 1
    msg = f"Restored {result['items']} items from {result['snapshot']}."
    if result["previous_moved_to"]:
        msg += f" The closet that was here before was moved to {result['previous_moved_to']}."
    _say(msg)
    return 0


def cmd_backup(args, cfg: config.Config) -> int:
    state = State(cfg.state_path)
    result = backup.run_backup(cfg, state, kind="manual", folder=Path(args.folder).expanduser() if args.folder else None)
    _say("Backup finished." if result["ok"] else f"Backup failed: {result['error']}")
    return 0 if result["ok"] else 1


def selfcheck(with_cutout: bool, cfg: config.Config, with_https: bool = False) -> dict:
    """Exercise the libraries that are hard to package. Returns {name: {ok, detail}}."""
    out: dict = {}

    def check(name, fn):
        try:
            out[name] = {"ok": True, "detail": fn()}
        except Exception as e:
            out[name] = {"ok": False, "detail": f"{type(e).__name__}: {e}"}

    def webp():
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGBA", (32, 32), (200, 40, 40, 128)).save(buf, "WEBP", quality=80)
        buf.seek(0)
        im = Image.open(buf)
        im.load()
        return f"{im.mode} {im.size[0]}x{im.size[1]}"

    def heic():
        import pillow_heif

        from . import images
        fixture = config.bundle_dir() / "demo_data" / "tiny.heic"
        im = images.decode(fixture.read_bytes())
        return f"pillow-heif {pillow_heif.__version__}, decoded {im.size[0]}x{im.size[1]}"

    def avif():
        from PIL import Image, features

        from . import images
        buf = io.BytesIO()
        Image.new("RGB", (32, 24), (40, 120, 70)).save(buf, "AVIF", quality=70)
        im = images.decode(buf.getvalue())
        return f"libavif {features.version('avif')}, decoded {im.size[0]}x{im.size[1]}"

    def onnx():
        import onnxruntime
        return f"onnxruntime {onnxruntime.__version__}"

    def database():
        import sqlite3
        return f"sqlite {sqlite3.sqlite_version}, {len(db.migration_files())} migration(s), demo data: " \
               f"{len(json.loads((config.bundle_dir() / 'demo_data' / 'items.json').read_text(encoding='utf-8'))['items'])} items"

    def page():
        index = config.bundle_dir() / "web" / "index.html"
        if not index.exists():
            raise FileNotFoundError("the built web page is not bundled")
        return f"web page bundled ({index.stat().st_size} bytes)"

    def drawing():
        from .drawing.item import svg_from_fields
        svg = svg_from_fields("shirt", "#a9c3e0", "solid", {"sleeve": "long", "neck": "collar"})
        if not svg or not svg.startswith("<svg"):
            raise RuntimeError("no shirt was drawn (the reason is in nines.log)")
        return f"drew a shirt from its tags ({len(svg):,} bytes of SVG)"

    def model():
        from .modelstore import ModelStore
        m = ModelStore(cfg.models_dir, State(cfg.state_path))
        m.refresh()
        return m.info()["state"]

    def cutout():
        from PIL import Image

        from .cutout import make_cutout, predict_mask
        from .modelstore import MODEL, ModelStore
        m = ModelStore(cfg.models_dir, State(cfg.state_path))
        m.refresh()
        if not m.ready:
            raise RuntimeError(f"model is {m.info()['state']}: {m.info()['error'] or 'not downloaded'}")
        photo = Image.open(config.bundle_dir() / "demo_data" / "selfcheck.webp").convert("RGB")
        cut, _ = make_cutout(photo, predict_mask(photo, MODEL, m.path))
        alpha = cut.split()[-1]
        covered = sum(1 for v in alpha.getdata() if v > 128) / (cut.width * cut.height)
        if not 0.15 < covered < 0.98:
            raise RuntimeError(f"cutout looks wrong: {covered:.0%} of the crop is foreground")
        return f"cutout {cut.width}x{cut.height}, {covered:.0%} foreground"

    def tagger():
        import anthropic

        from .tagger import claude_cli
        claude_cli.strict_schema()
        return f"anthropic {anthropic.__version__}, tagging schema ready"

    def updater():
        import hashlib

        from . import updates
        where = updates.layout()
        hashlib.sha256(b"closet").hexdigest()
        asset = updates.ASSETS.get(sys.platform)
        if asset and where is not None:
            return f"updates install {asset} in place of {where.installed.name}"
        return "updates are reported with a link (this computer installs them by hand)"

    def window():
        from . import window as app_window
        return app_window.check_bundled()

    def cloudflare():
        # the door through Cloudflare checks an RS256 signature (closet/access.py): sign a token with a key made here
        # and check it the way a request's is checked, so a build without PyJWT's RSA (cryptography) fails here
        from . import access
        return access.selfcheck()

    def https():
        import urllib.request
        from urllib.parse import urlsplit

        from . import net
        from .cutout import MODELS
        from .modelstore import MODEL, USER_AGENT
        url = MODELS[MODEL].url
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Range": "bytes=0-0"})
        with urllib.request.urlopen(req, timeout=30, context=net.ssl_context()) as r:
            return f"HTTP {r.status} from {urlsplit(r.url).hostname} using {net.trust_source()}"

    check("webp", webp)
    check("heic", heic)
    check("avif", avif)
    check("onnxruntime", onnx)
    check("database", database)
    check("web_page", page)
    check("drawing", drawing)
    check("model_state", model)
    check("tagger", tagger)
    check("updater", updater)
    check("window", window)
    check("cloudflare", cloudflare)
    if with_cutout:
        check("cutout", cutout)
    if with_https:  # the same connection the model download makes; needs the internet
        check("https", https)
    return out


def cmd_selfcheck(args, cfg: config.Config) -> int:
    result = selfcheck(args.cutout, cfg, args.https)
    text = json.dumps({"version": __version__, "checks": result}, indent=1)
    if args.out:  # the windowed program has no console to print to
        Path(args.out).write_text(text, encoding="utf-8")
    elif sys.stdout is not None:
        print(text)
    return 0 if all(c["ok"] for c in result.values()) else 1


def _from_task(args) -> None:
    """Started by Windows' task, perhaps before anyone has signed in: the user folder (where the data folder, Nines'
    own folder and Claude Code's sign-in are) is the one the task was set up with, and so is a data folder chosen by
    hand. Set before anything reads them, the data folder's move included."""
    if args.home:
        home = args.home
        os.environ["USERPROFILE"] = os.environ["HOME"] = home
        os.environ.setdefault("LOCALAPPDATA", str(Path(home) / "AppData" / "Local"))
        os.environ.setdefault("APPDATA", str(Path(home) / "AppData" / "Roaming"))
    if args.data_dir:
        os.environ["CLOSET_DATA_DIR"] = args.data_dir


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="Nines", description=f"{APP_NAME}: a private wardrobe app.")
    ap.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    ap.add_argument("--no-browser", action="store_true",
                    help="do not open Nines' window (or the browser) on start; opening the program again shows it")
    ap.add_argument("--browser", action="store_true", help="use the browser instead of Nines' own window")
    ap.add_argument("--tray", action="store_true", help="also show an icon near the clock (Windows) or in the menu bar (Mac)")
    ap.add_argument("--no-tray", action="store_true", help="run with no window to ask questions in (tests); never shows the icon")
    ap.add_argument("--port", type=int, help="listen on this port instead of the default")
    ap.add_argument("--background", action="store_true",
                    help="run the server alone, with no window, tray icon, browser or questions, and never on another "
                         "port; opening the program while it runs opens a window onto it")
    ap.add_argument("--replace", action="store_true",
                    help="if an older version is already running, close it without asking and start this one")
    # given by Windows' task (closet/background.py), which may start the program before anyone signs in
    ap.add_argument("--home", help=argparse.SUPPRESS)
    ap.add_argument("--data-dir", help=argparse.SUPPRESS)
    ap.add_argument("--after", type=int, help=argparse.SUPPRESS)   # a hand-over: wait for this process to quit first
    ap.add_argument("--on-its-own", action="store_true", help=argparse.SUPPRESS)   # serve although Windows keeps a copy
    sub = ap.add_subparsers(dest="command")
    r = sub.add_parser("restore", help="replace the closet with a backup")
    r.add_argument("folder", help="the backup folder you chose in Settings")
    r.add_argument("--snapshot", help="a specific snapshot file name (default: the newest)")
    b = sub.add_parser("backup", help="back up now")
    b.add_argument("--folder", help="back up here instead of the folder chosen in Settings")
    s = sub.add_parser("selfcheck", help="check the bundled libraries")
    s.add_argument("--cutout", action="store_true", help="also run a real background removal (needs the model)")
    s.add_argument("--https", action="store_true", help="also check that the model's download server can be reached securely")
    s.add_argument("--out", help="write the result to this file instead of printing it")
    w = sub.add_parser("update-watch", help=argparse.SUPPRESS)   # run by an update: start the new program, or go back
    w.add_argument("plan")
    args = ap.parse_args(argv)
    if args.command == "update-watch":
        from . import updates
        return updates.run_watch(args.plan)
    _from_task(args)
    global _folder_moving
    # before anything opens the data folder; an update's hand-over (--replace) leaves it to the next ordinary start
    _folder_moving = None if args.replace else datafolder.settle(os.environ, Path.home(), _running_in)
    cfg = config.load()
    if args.command == "restore":
        return cmd_restore(args, cfg)
    if args.command == "backup":
        return cmd_backup(args, cfg)
    if args.command == "selfcheck":
        return cmd_selfcheck(args, cfg)
    return serve(args, cfg)
