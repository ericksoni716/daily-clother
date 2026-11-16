"""Closet's own window: the app in a window of its own instead of a browser tab, like the owner's other app.

The window is pywebview (https://pywebview.flowrl.com, BSD licence): Edge WebView2 on Windows, WebKit on the Mac, and
GTK or Qt on Linux when they are installed (a closet run from source on Linux usually has neither, and uses the browser).
It shows the same page the browser and the phone get, from the same server on 127.0.0.1, with the same login.

- Closing the window hides it: Closet keeps running in the tray, so the phone and the nightly backup keep working.
  "Open Closet" in the tray, a second launch and (on the Mac) clicking the program again bring it back. Only when
  there is no tray icon to come back from does closing the window quit Closet.
- A copy started at login prepares the window hidden and loads nothing until the owner first opens it.
- The window keeps its web storage (the login cookie, the page's own settings) in `window/` in the closet's data
  folder, not in private mode, so the login is remembered like a browser remembers it. (The Mac keeps WebKit's storage
  where macOS keeps every app's, under ~/Library; WebKit has no public way to choose the folder.)
- Links that open a new tab (the shop, the release page) open in the default browser: pywebview's own setting
  `OPEN_EXTERNAL_LINKS_IN_BROWSER`, on by default. The page offers no downloads or saves.
- If the window cannot be used here (no window library, Windows without the Edge WebView2 Runtime, any error while
  starting it, or a page that never loads), `prepare()` or `run()` says so in the log and the launcher opens the
  browser instead, as Closet always did.

Threads and loops. pywebview's `start()` must be called on the main thread
(webview/__init__.py: "pywebview must be run on a main thread"), and so must AppKit on the Mac, where the tray icon
(pystray) and the window share the one NSApplication. pystray's `Icon.run_detached()` is meant for exactly this:
"This allows integrating pystray with other libraries requiring a mainloop. Call this method before entering the
mainloop of the other library." (https://pystray.readthedocs.io/en/latest/usage.html, pystray/_base.py). What it does
on each system, read in pystray 0.19.5's source:

- Windows (pystray/_win32.py `_run_detached`): starts a thread with the icon's own message loop. pywebview's WinForms
  backend (webview/platforms/winforms.py `create_window`) runs the window's loop in a thread of its own too (an STA
  thread, as WinForms needs), while the main thread waits for it.
- Mac (pystray/_darwin.py `_run_detached`): only marks the icon ready; its status item lives in
  `NSApplication.sharedApplication()`, whose loop pywebview's Cocoa backend runs on the main thread
  (webview/platforms/cocoa.py `BrowserView.first_show`, `app.run()`), so its menu works through the window's loop.
- Linux: the GTK and AppIndicator backends (pystray/_util/gtk.py) join the GLib loop that pywebview's GTK backend
  runs on the main thread; the plain X11 backend (pystray/_xorg.py) gets a thread with a loop of its own (started by
  `tray.run_beside`, because that backend's `run_detached()` leaves a thread behind that keeps the program alive).

So the launcher starts the icon with `tray.run_beside(icon)` (pystray's `run_detached()`) and then calls
`AppWindow.run()` on the main thread. When the window cannot be
used at all, nothing changes from before: the tray's own `icon.run()` blocks the main thread. When the window's loop
ends without Closet quitting, an icon that was riding on that loop (Mac, GTK) gets its own loop with `icon.run()`.

Closing on Windows is caught on the window itself (WinForms' FormClosing, which says why the window is closing), not
with pywebview's `closing` event, so that only the owner closing the window hides it: when Windows is shutting down or
signing out the window closes and Closet quits, instead of holding up the shutdown. On the Mac the app's delegate does
the same for Quit (Cmd+Q, the Dock, logging out): Closet quits cleanly at once.
"""
from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
import threading
from collections.abc import Callable
from pathlib import Path

from . import APP_NAME

log = logging.getLogger("closet.window")

# The web engines the page is built for. Windows without the Edge WebView2 Runtime falls back to Internet Explorer's
# engine ("mshtml"), which cannot run the page, so the browser is used instead.
RENDERERS = {"edgechromium": "Edge WebView2", "wkwebview": "WebKit", "gtkwebkit2": "WebKitGTK", "qtwebengine": "Qt WebEngine"}
SIZE = (1280, 860)        # wide enough for the desktop layout (1000 px and up), when the screen allows
MIN_SIZE = (390, 600)     # narrow enough for the phone layout, which the page uses below 560 px
BACKGROUND = "#F6F2EA"    # the page's own background (--bg in styles.css), shown until it has drawn
LOAD_WITHIN = 30          # seconds the page has to load once the window shows it, before the browser is used instead


class AppWindow:
    """Closet's window: made hidden or shown, hidden again when closed, closed for good only when Closet quits.

    `keep_running()` says whether closing the window should leave Closet running (there is a tray icon to come back
    from); `on_quit()` quits Closet; `on_visible(shown)` is told when the window is shown or hidden; `on_terminate()`
    is the Mac's Quit, which must stop everything before it returns. `toolkit` replaces pywebview in tests."""

    def __init__(self, url: str, storage_dir: Path, *, hidden: bool = False,
                 keep_running: Callable[[], bool] = lambda: True, on_quit: Callable[[], None] = lambda: None,
                 on_visible: Callable[[bool], None] = lambda shown: None,
                 on_terminate: Callable[[], None] | None = None, toolkit=None, platform: str = sys.platform,
                 load_within: float = LOAD_WITHIN):
        self.url = url
        self.storage_dir = Path(storage_dir)
        self.hidden_at_start = hidden
        self.keep_running = keep_running
        self.on_quit = on_quit
        self.on_visible = on_visible
        self.on_terminate = on_terminate or on_quit
        self.platform = platform
        self.load_within = load_within
        self.usable = False           # True once prepared, until the window has gone for good
        self.visible = not hidden     # whether the owner should be seeing it now
        self.renderer: str | None = None
        self._toolkit = toolkit
        self._window = None
        self._quitting = False        # Closet is quitting: let the window close
        self._closed_by_owner = False  # the owner closed it with no tray to come back from, or the session is ending
        self._gave_up = False         # the page never loaded: close it and use the browser
        self._page_requested = not hidden
        self._page_loaded = threading.Event()
        self._watchdog_started = False
        self._minimized = False
        self._maximized = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ before the loop
    def prepare(self) -> bool:
        """Load the window's library and make the window, without running its loop. False, with the reason in the log,
        when there is no usable window here; the browser is used instead."""
        try:
            toolkit = self._toolkit or _Pywebview(self.storage_dir)
            self._toolkit = toolkit
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            self.renderer = toolkit.initialize()
            if self.renderer not in RENDERERS:
                hint = (" (the Microsoft Edge WebView2 Runtime is not installed)"
                        if self.renderer == "mshtml" else "")
                raise RuntimeError(f"its web engine here is {self.renderer!r}{hint}, which cannot show Closet")
            width, height = _fit(SIZE, toolkit.screen_size())
            window = toolkit.create_window(
                APP_NAME, url=None if self.hidden_at_start else self.url, width=width, height=height,
                min_size=MIN_SIZE, hidden=self.hidden_at_start, text_select=True, zoomable=True,
                background_color=BACKGROUND)
            events = window.events
            events.before_show += self._before_show
            events.loaded += self._loaded
            events.minimized += self._was_minimized
            events.maximized += self._was_maximized
            events.restored += self._was_restored
            if self.platform != "win32":   # on Windows the window itself is asked (see _before_show)
                events.closing += self._closing
            self._window = window
            if self.platform == "darwin":
                toolkit.mac_prepare(on_reopen=self.show, on_terminate=self._terminate, dock=not self.hidden_at_start)
            self.usable = True
            log.info("Closet opens in its own window (%s)%s", RENDERERS[self.renderer],
                     ", hidden until it is opened" if self.hidden_at_start else "")
            return True
        except Exception as e:
            log.warning("Closet's own window cannot open here (%s: %s); the browser is used instead",
                        type(e).__name__, e)
            if self.platform == "darwin" and self._toolkit is not None:
                self._toolkit.mac_dock(False)   # importing the window library gave Closet a Dock icon
            self.usable = False
            return False

    # ------------------------------------------------------------------ the loop
    def run(self) -> bool:
        """Run the window's loop on this thread (the main thread) until the window is closed for good. True when it
        ended because Closet is quitting; False when the window went for another reason (it could not start, or its
        page never loaded), and the browser should be used from now on."""
        if not self.usable:
            return False
        if self._quitting:   # Quit came before the loop started
            return True
        if self._page_requested:
            self._start_watchdog()
        try:
            self._toolkit.start(storage_path=str(self.storage_dir), func=self._started)
        except Exception as e:
            log.warning("Closet's own window stopped (%s: %s); the browser is used from now on", type(e).__name__, e)
        self.usable = False
        if self._closed_by_owner:
            self.on_quit()
        if self._quitting:
            return True
        if not self._gave_up:
            log.warning("Closet's own window closed by itself; the browser is used from now on")
        return False

    def _started(self) -> None:
        """Runs in a thread once the loop has started: a Quit that came while the window was being made closes it."""
        if self._window.events.shown.wait(60) and self._quitting:
            self._destroy()

    # ------------------------------------------------------------------ showing and hiding
    def show(self) -> bool:
        """Bring the window up (the tray's Open Closet, a second launch, the Mac's Dock). Never waits; False when there
        is no window to show, and the browser should be opened instead."""
        if not self.usable or self._quitting:
            return False
        threading.Thread(target=self._show, name="window-show", daemon=True).start()
        return True

    def _show(self) -> None:
        window = self._window
        try:
            self.visible = True
            self.on_visible(True)
            if self.platform == "darwin":
                self._toolkit.mac_dock(True)
            with self._lock:
                first = not self._page_requested
                self._page_requested = True
            if first:   # started at login: the page is loaded the first time the window is opened
                window.load_url(self.url)
                self._start_watchdog()
            if self._minimized and self._maximized:
                window.maximize()
            elif self._minimized:
                window.restore()
            window.show()
        except Exception:
            log.exception("could not show Closet's window")

    def hide(self) -> None:
        if self._window is None or self._quitting:
            return
        self.visible = False
        try:
            self._window.hide()
            if self.platform == "darwin":
                self._toolkit.mac_dock(False)   # back to a menu-bar app: no Dock icon while the window is hidden
        except Exception:
            log.exception("could not hide Closet's window")
        self.on_visible(False)

    def close(self) -> None:
        """Closet is quitting: close the window for good, which ends its loop and so `run()`."""
        with self._lock:
            already = self._quitting
            self._quitting = True
        if not already:
            self._destroy()

    def _destroy(self) -> None:
        if self._window is None:
            return
        try:
            self._window.destroy()
        except Exception:   # not made yet (`_started` closes it then) or already gone
            pass

    # ------------------------------------------------------------------ closing
    def _keep_open(self, by_owner: bool) -> bool:
        """Whether a window that is being closed should only be hidden. When it may close, and Closet is not already
        quitting, Closet quits once the window has gone (see `run`)."""
        if self._quitting or self._gave_up:
            return False
        if by_owner and self.keep_running():
            threading.Thread(target=self.hide, name="window-hide", daemon=True).start()
            return True
        with self._lock:
            self._quitting = True
            self._closed_by_owner = True
        log.info("Closet's window was closed %s; Closet quits",
                 "with no tray icon to come back from" if by_owner else "by Windows (shutting down, signing out)")
        return False

    def _closing(self):
        """pywebview's `closing` event (Mac and Linux): returning False keeps the window."""
        return False if self._keep_open(by_owner=True) else None

    def _before_show(self, window) -> None:
        """Runs as the window is made, before it is shown. On Windows, closing is caught on the WinForms form itself,
        whose FormClosing event says why it is closing (pywebview's `closing` event does not)."""
        if self.platform != "win32":
            return
        try:
            window.native.FormClosing += self._form_closing
        except Exception:
            log.warning("could not watch the window's Close button; closing it may hold up shutting down Windows",
                        exc_info=True)
            window.events.closing += self._closing

    def _form_closing(self, sender, args) -> None:
        if self._keep_open(by_owner=not _windows_wants_it_closed(args.CloseReason)):
            args.Cancel = True

    def _terminate(self) -> None:
        """The Mac's Quit (Cmd+Q, the Dock's Quit, logging out or shutting down): quit Closet completely, now."""
        with self._lock:
            self._quitting = True
        self.on_terminate()

    # ------------------------------------------------------------------ the page
    def _start_watchdog(self) -> None:
        with self._lock:
            if self._watchdog_started:
                return
            self._watchdog_started = True
        threading.Thread(target=self._watch_load, name="window-load", daemon=True).start()

    def _watch_load(self) -> None:
        if self._page_loaded.wait(self.load_within) or self._quitting or not self.usable:
            return
        log.warning("Closet's page did not load in its window within %g seconds; the browser is used instead",
                    self.load_within)
        self._gave_up = True
        self._destroy()

    def _loaded(self) -> None:
        if self._page_requested:
            self._page_loaded.set()

    def _was_minimized(self) -> None:
        self._minimized = True

    def _was_maximized(self) -> None:
        self._minimized, self._maximized = False, True

    def _was_restored(self) -> None:
        self._minimized = self._maximized = False


# WinForms' CloseReason values that mean Windows itself is closing the window: shutting down or signing out, Task
# Manager's End task, and Application.Exit (pywebview's answer to Ctrl+C). Anything else, above all UserClosing (the
# Close button, Alt+F4, the taskbar's Close window, and Closet's own destroy() when it quits), is the owner's doing.
WINDOWS_CLOSING = {"WindowsShutDown": 1, "TaskManagerClosing": 4, "ApplicationExitCall": 6}


def _windows_wants_it_closed(reason) -> bool:
    """Whether a CloseReason (as pythonnet gives it: its name, possibly qualified, or its number) is Windows' doing.
    When unsure the window is only hidden: holding up a shutdown is better than quitting when the owner closed it."""
    text = str(reason).strip()
    if text.isdigit():
        return int(text) in WINDOWS_CLOSING.values()
    return text.rsplit(".", 1)[-1] in WINDOWS_CLOSING


def _fit(size: tuple[int, int], screen: tuple[int, int] | None) -> tuple[int, int]:
    """The window's first size: SIZE, made smaller to fit nine tenths of the screen, never below MIN_SIZE."""
    width, height = size
    if screen:
        width = min(width, int(screen[0] * 0.9))
        height = min(height, int(screen[1] * 0.9))
    return max(width, MIN_SIZE[0]), max(height, MIN_SIZE[1])


class _Pywebview:
    """The few parts of pywebview Closet uses, so tests can stand in for them."""

    def __init__(self, storage_dir: Path):
        self.storage_dir = storage_dir
        self.webview = None

    def initialize(self) -> str:
        """Load pywebview and this computer's window library; returns its web engine's name."""
        import webview
        self.webview = webview
        # Qt reads where to keep its storage as its module is loaded, which initialize() does before start() sets it.
        webview._state["storage_path"] = str(self.storage_dir)
        webview._state["private_mode"] = False
        guilib = importlib.import_module("webview.guilib").initialize()
        return getattr(guilib, "renderer", None)

    def screen_size(self) -> tuple[int, int] | None:
        try:
            screens = self.webview.screens
            return (screens[0].width, screens[0].height) if screens else None
        except Exception:
            return None

    def create_window(self, title, **kwargs):
        return self.webview.create_window(title, **kwargs)

    def start(self, storage_path: str, func: Callable[[], None]) -> None:
        self.webview.start(func=func, private_mode=False, storage_path=storage_path)

    # ---- the Mac
    def mac_prepare(self, on_reopen: Callable[[], object], on_terminate: Callable[[], None], dock: bool) -> None:
        from . import window_mac
        window_mac.install_delegate(on_reopen, on_terminate)
        if not dock:
            window_mac.set_dock_icon(False, now=True)

    def mac_dock(self, shown: bool) -> None:
        try:
            from . import window_mac
            window_mac.set_dock_icon(shown)
        except Exception:
            log.debug("could not change the Dock icon", exc_info=True)


def check_bundled(platform: str = sys.platform) -> str:
    """For `closet selfcheck`: the window's library and this computer's part of it are in the program, checked without
    opening a window (the packaged smoke test runs where no window can be shown)."""
    import webview  # noqa: F401  (the library itself, with bottle and proxy_tools)
    from webview import util
    from webview._version import version

    js = Path(util.get_js_dir())
    if not any(js.glob("*.js")):
        raise FileNotFoundError("pywebview's scripts are not bundled")
    if platform == "win32":
        import clr  # pythonnet: the WinForms window
        for dll in ("Microsoft.Web.WebView2.Core.dll", "Microsoft.Web.WebView2.WinForms.dll"):
            clr.AddReference(util.interop_dll_path(dll))
        loader = Path(util.interop_dll_path("win-x64")) / "WebView2Loader.dll"
        if not loader.is_file():
            raise FileNotFoundError("WebView2Loader.dll is not bundled")
        return f"pywebview {version}, Edge WebView2 libraries loaded"
    if platform == "darwin":
        import objc
        import WebKit  # noqa: F401
        from PyObjCTools import AppHelper  # noqa: F401
        if importlib.util.find_spec("webview.platforms.cocoa") is None:
            raise ModuleNotFoundError("pywebview's Cocoa window is not bundled")
        from . import window_mac  # noqa: F401
        return f"pywebview {version}, WebKit through PyObjC {objc.__version__}"
    return f"pywebview {version}; on Linux the browser is used unless GTK or Qt is installed"
