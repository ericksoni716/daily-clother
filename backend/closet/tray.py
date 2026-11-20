"""The small icon near the clock (in the menu bar on a Mac): Open Closet, start at login, Quit.

Optional. Where no tray is available (or the library is missing) the program
simply runs without one and can be stopped from Settings. How it shares the
main thread with Closet's own window is explained in closet/window.py.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from PIL import Image

from .config import bundle_dir

log = logging.getLogger("closet.tray")


def icon_image(size: int = 64) -> Image.Image:
    """The app's icon (an empty dinner jacket on a cream rounded square, transparent outside it) at `size` px.

    Rendered from frontend/scripts/nines-icon.svg by `npm run icons` into closet/icon.png, which the packaged program
    carries (packaging/closet.spec)."""
    with Image.open(bundle_dir() / "icon.png") as im:
        return im.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)


def create(on_open: Callable[[], None], on_quit: Callable[[], None],
           autostart_get: Callable[[], bool | None], autostart_set: Callable[[bool], None]):
    """Build the tray icon, or return None when a tray cannot be used here."""
    try:
        import pystray
    except Exception as e:  # missing library or no display
        log.info("no tray icon: %s", type(e).__name__)
        return None

    def toggle(icon, item):
        try:
            autostart_set(not bool(autostart_get()))
        except Exception:
            log.exception("could not change start at login")

    entries = [pystray.MenuItem("Open Nines", lambda icon, item: on_open(), default=True)]
    if autostart_get() is not None:
        entries.append(pystray.MenuItem("Start when I log in", toggle, checked=lambda item: bool(autostart_get())))
    entries.append(pystray.MenuItem("Quit Nines", lambda icon, item: on_quit()))
    try:
        return pystray.Icon("closet", icon_image(), "Nines", pystray.Menu(*entries))
    except Exception as e:
        log.info("no tray icon: %s", type(e).__name__)
        return None


def _backend(icon) -> str:
    return type(icon).__module__.rsplit(".", 1)[-1]


def run_beside(icon) -> None:
    """Start the icon beside the loop of Closet's window, which has the main thread: pystray's `run_detached()`.

    pystray 0.19.5's plain X11 icon (Linux without GTK) is started by hand instead: its `run_detached()` calls `run()`
    in a thread, which starts the icon's setup thread a second time, and that one waits forever, keeping the program
    from ending. Its loop runs in a daemon thread here, as `run_detached()` would have run it."""
    if _backend(icon) == "_xorg":
        threading.Thread(target=icon.run, name="tray", daemon=True).start()
    else:
        icon.run_detached()


def has_own_loop(icon) -> bool:
    """Whether the icon runs a loop of its own in a thread once started by `run_beside` (Windows, plain X11), rather
    than relying on the loop of the window it shares the main thread with (the Mac, GTK). See closet/window.py."""
    return _backend(icon) not in ("_darwin", "_gtk", "_appindicator")
