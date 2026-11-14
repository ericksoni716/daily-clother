"""Start the program when the owner logs in to the computer (optional)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

NAME = "Closet"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"   # Windows: this user's programs started at login


def program() -> str | None:
    """The packaged program's path, or None when running from source."""
    return sys.executable if getattr(sys, "frozen", False) else None


def _linux_file(home: Path) -> Path:
    return home / ".config" / "autostart" / "closet.desktop"


def _mac_file(home: Path) -> Path:
    return home / "Library" / "LaunchAgents" / "app.closet.plist"


def is_enabled(platform: str = sys.platform, home: Path | None = None) -> bool:
    home = home or Path.home()
    if platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
                winreg.QueryValueEx(k, NAME)
                return True
        except OSError:
            return False
    if platform == "darwin":
        return _mac_file(home).exists()
    return _linux_file(home).exists()


def set_enabled(enabled: bool, exe: str | None = None, platform: str = sys.platform, home: Path | None = None) -> None:
    home = home or Path.home()
    exe = exe or program()
    if enabled and not exe:
        raise RuntimeError("Start at login is only available in the downloaded program, not when running from source.")
    if platform == "win32":
        import winreg
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if enabled:
                winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, f'"{exe}" --no-browser')
            else:
                try:
                    winreg.DeleteValue(k, NAME)
                except OSError:
                    pass
        return
    path = _mac_file(home) if platform == "darwin" else _linux_file(home)
    if not enabled:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if platform == "darwin":
        path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0"><dict>\n'
            '  <key>Label</key><string>app.closet</string>\n'
            f'  <key>ProgramArguments</key><array><string>{exe}</string><string>--no-browser</string></array>\n'
            '  <key>RunAtLoad</key><true/>\n'
            '</dict></plist>\n')
    else:
        path.write_text(f"[Desktop Entry]\nType=Application\nName={NAME}\nExec=\"{exe}\" --no-browser\nX-GNOME-Autostart-enabled=true\n")
        os.chmod(path, 0o644)
