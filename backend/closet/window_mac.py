"""The Mac's side of Closet's window: Quit, clicking the program again, and the Dock icon.

Only imported on a Mac, after pywebview has loaded its Cocoa window (webview/platforms/cocoa.py), whose application
delegate is replaced here by a subclass before the window is made (pywebview uses `BrowserView._shared_app_delegate`
when it is set):

- Quit (Cmd+Q, the Dock's Quit, logging out, shutting down) quits Closet completely: the server stops and the closet's
  files are closed before macOS ends the program. pywebview's own delegate would ask the window first, and the window
  only hides, which would hold up logging out.
- Opening the program while it runs (double-clicking it, clicking its Dock icon) shows the window: macOS does not start
  a second copy, it tells the running one (`applicationShouldHandleReopen:hasVisibleWindows:`).
- Closet is a menu-bar program (LSUIElement in its Info.plist), but pywebview gives it a Dock icon as it loads. While
  the window shows it has a Dock icon and a menu bar (so Copy and Paste work from the keyboard); while the window is
  hidden it goes back to the menu bar only.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

import AppKit
import objc
from PyObjCTools import AppHelper

log = logging.getLogger("closet.window")

REGULAR, ACCESSORY = 0, 1            # NSApplicationActivationPolicyRegular, ...Accessory
TERMINATE_NOW = 1                    # NSTerminateNow
_installed: dict = {}


def install_delegate(on_reopen: Callable[[], object], on_terminate: Callable[[], None]) -> None:
    from webview.platforms import cocoa

    _installed["reopen"], _installed["terminate"] = on_reopen, on_terminate
    if "class" not in _installed:   # an Objective-C class can be defined once per program
        base = cocoa.BrowserView.AppDelegate

        class ClosetAppDelegate(base):
            def applicationShouldTerminate_(self, app):
                try:
                    _installed["terminate"]()
                except Exception:
                    log.exception("could not stop Closet cleanly")
                return TERMINATE_NOW

            @objc.typedSelector(b"Z@:@Z")
            def applicationShouldHandleReopen_hasVisibleWindows_(self, app, flag):
                try:
                    _installed["reopen"]()
                except Exception:
                    log.exception("could not show Closet's window")
                return True

        _installed["class"] = ClosetAppDelegate
    cocoa.BrowserView._shared_app_delegate = _installed["class"].alloc().init()


def set_dock_icon(shown: bool, now: bool = False) -> None:
    """Show or hide the Dock icon (and the menu bar). AppKit must be called on the main thread: `now` when this is it."""
    app = AppKit.NSApplication.sharedApplication()
    policy = REGULAR if shown else ACCESSORY
    if now:
        app.setActivationPolicy_(policy)
    else:
        AppHelper.callAfter(app.setActivationPolicy_, policy)
