"""The program's entry point.

    closet                      start the app (what a double-click does)
    closet restore <folder>     replace the closet with a backup
    closet backup               back up now to the chosen folder
    closet reset-passphrase     forget the passphrase so a new one can be set
    closet selfcheck            check that the bundled libraries work
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import logging.handlers
import signal
import sys
import threading
import time
import webbrowser
from pathlib import Path

from . import APP_NAME, __version__, autostart, backup, config, db, instance
from .state import State

log = logging.getLogger("closet")


def _setup_logging(cfg: config.Config) -> None:
    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        logging.handlers.RotatingFileHandler(cfg.logs_dir / "closet.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")]
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", handlers=handlers)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def _say(message: str) -> None:
    """Tell the owner something even when there is no console window."""
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


def _open_running(info: dict, url: str) -> None:
    """Opened again while a copy runs: that copy shows its window, or, when it has none (it uses the browser, or it is
    from before Closet had a window), the browser opens as it always did."""
    if not instance.show_running(info):
        webbrowser.open(url)


def _launch_args(args, port: int, window_shown: bool = False) -> list[str]:
    """How an update starts the new program: the way this one was started, on the same port, showing its window only
    when this one's is showing (an update never opens the browser; the page already open there reconnects)."""
    return ((["--no-tray"] if args.no_tray else []) + (["--tray"] if args.tray else []) + (["--browser"] if args.browser else [])
            + ([] if window_shown else ["--no-browser"]) + ["--port", str(port)])


def serve(args, cfg: config.Config) -> int:
    try:
        with instance.startup_lock(cfg) as release_startup:
            return _serve(args, cfg, release_startup)
    except TimeoutError as e:
        _say(str(e))
        return 2


def _serve(args, cfg: config.Config, release_startup) -> int:
    import uvicorn

    from .app import build_services, create_app

    replaced_older = False
    already = instance.running_info(cfg)
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
                    _say(f"The older {APP_NAME} ({theirs}) did not close. Quit it from its icon "
                         f"(near the clock, or in the menu bar), then open {APP_NAME} {__version__} again.")
                    return 4
            else:
                if replace is None:
                    _say(f"An older {APP_NAME} ({theirs}) is already running at {url}. Quit it from its icon or "
                         f"from Settings, then open {APP_NAME} {__version__} again to use the new version.")
                if not args.no_browser:
                    _open_running(already, url)
                return 0
        if not replaced_older:
            if not args.no_browser:
                _open_running(already, url)
            if sys.stdout is not None:
                print(f"{APP_NAME} {theirs} is already running at {url}", flush=True)
            return 0

    _setup_logging(cfg)
    if replaced_older:
        log.info("replaced an older copy (%s) with %s", already["version"], __version__)
        _follow_start_at_login()
        instance.wait_for_port(cfg.host, args.port or cfg.port)
    try:
        wanted = args.port or cfg.port
        port = args.port or instance.pick_port(cfg.host, cfg.port)
        cfg = config.Config(cfg.data_dir, cfg.host, port, cfg.auto_download_model)
        services = build_services(cfg)
    except db.NewerDatabaseError as e:
        _say(str(e))
        return 2
    except RuntimeError as e:
        _say(str(e))
        return 2

    app = create_app(services)
    server = uvicorn.Server(uvicorn.Config(app, host=cfg.host, port=port, log_config=None, loop="asyncio",
                                           http="h11", ws="none", lifespan="off", access_log=False))
    server.install_signal_handlers = lambda: None  # we run it off the main thread
    url = f"http://127.0.0.1:{port}/"
    ui: dict = {}   # the tray icon and Closet's own window, once they are up

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
        """Show Closet's own window; False when there is none and the browser should be opened instead."""
        window = ui.get("window")
        return window is not None and window.show()

    def open_closet() -> None:   # the tray's "Open Closet"
        if not show_window():
            webbrowser.open(url)

    services.on_quit = quit_program
    services.on_show = show_window
    if services.updater is not None:   # an update starts the new program the way this one was started
        services.updater.launch_args = _launch_args(args, port)
    thread = threading.Thread(target=server.run, name="server", daemon=True)
    thread.start()
    deadline = time.time() + 30
    while not server.started and thread.is_alive() and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        _say(f"{APP_NAME} could not start on port {port}. Is another program using it?")
        return 3
    instance.write_lock(cfg, port)
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

    # Closet's own window, unless it was asked for the browser or runs with neither a tray nor a window (the smoke
    # test, the browser tests). Started at login (--no-browser) it is made hidden, for "Open Closet" to show.
    window = None
    if not args.browser and not (args.no_tray and args.no_browser):
        from . import window as app_window

        def window_shown(shown: bool) -> None:
            if services.updater is not None:
                services.updater.launch_args = _launch_args(args, port, window_shown=shown)

        window = app_window.AppWindow(url, cfg.window_dir, hidden=args.no_browser,
                                      keep_running=lambda: True, on_quit=quit_program,
                                      on_visible=window_shown, on_terminate=quit_now)
        if window.prepare():
            ui["window"] = window
            window_shown(window.visible)
        else:
            window = None
    if window is None and not args.no_browser:
        webbrowser.open(url)

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
            if not window.run():   # the window has gone without Closet quitting: use the browser from now on
                ui.pop("window", None)
                if not server.should_exit:
                    if window.visible:
                        webbrowser.open(url)
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


def cmd_reset(args, cfg: config.Config) -> int:
    from . import auth
    if instance.running_instance(cfg):
        _say(f"{APP_NAME} is running. Quit it first, then run this again.")
        return 1
    auth.clear_passphrase(State(cfg.state_path))
    _say("The passphrase was cleared. Start the app and it will ask for a new one. Your closet is untouched.")
    return 0


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
            raise RuntimeError("no shirt was drawn (the reason is in closet.log)")
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
    check("onnxruntime", onnx)
    check("database", database)
    check("web_page", page)
    check("drawing", drawing)
    check("model_state", model)
    check("tagger", tagger)
    check("updater", updater)
    check("window", window)
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="closet", description=f"{APP_NAME}: a private wardrobe app.")
    ap.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    ap.add_argument("--no-browser", action="store_true",
                    help="do not open Closet's window (or the browser) on start; opening the program again shows it")
    ap.add_argument("--browser", action="store_true", help="use the browser instead of Closet's own window")
    ap.add_argument("--tray", action="store_true", help="also show an icon near the clock (Windows) or in the menu bar (Mac)")
    ap.add_argument("--no-tray", action="store_true", help="run with no window to ask questions in (tests); never shows the icon")
    ap.add_argument("--port", type=int, help="listen on this port instead of the default")
    ap.add_argument("--replace", action="store_true",
                    help="if an older version is already running, close it without asking and start this one")
    sub = ap.add_subparsers(dest="command")
    r = sub.add_parser("restore", help="replace the closet with a backup")
    r.add_argument("folder", help="the backup folder you chose in Settings")
    r.add_argument("--snapshot", help="a specific snapshot file name (default: the newest)")
    b = sub.add_parser("backup", help="back up now")
    b.add_argument("--folder", help="back up here instead of the folder chosen in Settings")
    sub.add_parser("reset-passphrase", help="forget the passphrase")
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
    cfg = config.load()
    if args.command == "restore":
        return cmd_restore(args, cfg)
    if args.command == "backup":
        return cmd_backup(args, cfg)
    if args.command == "reset-passphrase":
        return cmd_reset(args, cfg)
    if args.command == "selfcheck":
        return cmd_selfcheck(args, cfg)
    return serve(args, cfg)
