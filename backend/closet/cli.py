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
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, APP_NAME, 0x40)
        except Exception:
            pass


def serve(args, cfg: config.Config) -> int:
    import uvicorn

    from .app import build_services, create_app

    already = instance.running_instance(cfg)
    if already:
        url = f"http://127.0.0.1:{already}/"
        if not args.no_browser:
            webbrowser.open(url)
        if sys.stdout is not None:
            print(f"{APP_NAME} is already running at {url}", flush=True)
        return 0

    _setup_logging(cfg)
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
    icon_holder: dict = {}

    def quit_program() -> None:
        server.should_exit = True
        icon = icon_holder.get("icon")
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass

    services.on_quit = quit_program
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
    log.info("%s %s serving on %s (data folder: %s)", APP_NAME, __version__, url, cfg.data_dir)
    if port != wanted:
        log.warning("port %s was busy; using %s. Phone access set up for the usual port will not reach this one.",
                    wanted, port)
    if sys.stdout is not None:
        print(f"{APP_NAME} is running at {url}  (quit from the tray icon, Settings, or Ctrl+C)", flush=True)
    if not args.no_browser:
        webbrowser.open(url)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, lambda *_: quit_program())
        except (ValueError, OSError):
            pass

    icon = None
    if not args.no_tray:
        from . import tray
        icon = tray.create(lambda: webbrowser.open(url), quit_program,
                           lambda: autostart.is_enabled() if autostart.program() else None, autostart.set_enabled)
    try:
        if icon is not None:
            icon_holder["icon"] = icon
            try:
                icon.run()  # blocks on the main thread until Quit
            except Exception:
                log.info("tray icon unavailable; continuing without it")
        while thread.is_alive():
            thread.join(timeout=0.5)
    except KeyboardInterrupt:
        quit_program()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        services.stop()
        instance.clear_lock(cfg)
    return 0


def cmd_restore(args, cfg: config.Config) -> int:
    if instance.running_instance(cfg):
        _say(f"{APP_NAME} is running. Quit it first (tray icon or Settings), then restore.")
        return 1
    try:
        result = backup.restore(cfg, Path(args.folder).expanduser(), args.snapshot)
    except backup.BackupError as e:
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
    ap.add_argument("--no-browser", action="store_true", help="do not open the browser on start")
    ap.add_argument("--no-tray", action="store_true", help="do not show the tray icon")
    ap.add_argument("--port", type=int, help="listen on this port instead of the default")
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
    args = ap.parse_args(argv)
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
