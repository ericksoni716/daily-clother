"""Start the program when the owner logs in to the computer (optional)."""
from __future__ import annotations

import os
import plistlib
import sys
from pathlib import Path

NAME = "Nines"
OLD_NAME = "Closet"   # the entry's name until 0.11.0, when the program was still Closet.exe; carried over at start
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"   # Windows: this user's programs started at login


def program() -> str | None:
    """The packaged program's path, or None when running from source."""
    return sys.executable if getattr(sys, "frozen", False) else None


def _label(name: str) -> str:
    return f"app.{name.lower()}"


def _linux_file(home: Path, name: str = NAME) -> Path:
    return home / ".config" / "autostart" / f"{name.lower()}.desktop"


def _mac_file(home: Path, name: str = NAME) -> Path:
    return home / "Library" / "LaunchAgents" / f"{_label(name)}.plist"


def _exists(name: str, platform: str, home: Path) -> bool:
    if platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
                winreg.QueryValueEx(k, name)
                return True
        except OSError:
            return False
    if platform == "darwin":
        return _mac_file(home, name).exists()
    return _linux_file(home, name).exists()


def _remove(name: str, platform: str, home: Path) -> None:
    if platform == "win32":
        import winreg
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            try:
                winreg.DeleteValue(k, name)
            except OSError:
                pass
        return
    (_mac_file(home, name) if platform == "darwin" else _linux_file(home, name)).unlink(missing_ok=True)


def is_enabled(platform: str = sys.platform, home: Path | None = None) -> bool:
    return _exists(NAME, platform, home or Path.home())


def carry_over(exe: str | None = None, platform: str = sys.platform, home: Path | None = None) -> bool:
    """The packaged program, at start: an entry left from when the program was Closet.exe would open a file that is
    gone (or a second copy), so it is removed and start at login opens this program instead. True when it did."""
    home = home or Path.home()
    exe = exe or program()
    if not exe or not _exists(OLD_NAME, platform, home):
        return False
    _remove(OLD_NAME, platform, home)
    set_enabled(True, exe=exe, platform=platform, home=home)
    return True


def set_enabled(enabled: bool, exe: str | None = None, platform: str = sys.platform, home: Path | None = None) -> None:
    home = home or Path.home()
    exe = exe or program()
    if enabled and not exe:
        raise RuntimeError("Start at login is only available in the downloaded program, not when running from source.")
    if not enabled:
        _remove(NAME, platform, home)
        return
    if platform == "win32":
        import winreg
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, f'"{exe}" --no-browser')
        return
    path = _mac_file(home) if platform == "darwin" else _linux_file(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    if platform == "darwin":
        path.write_bytes(plistlib.dumps({
            "Label": _label(NAME),
            "ProgramArguments": [exe, "--no-browser"],
            "RunAtLoad": True,
        }))
    else:
        path.write_text(f"[Desktop Entry]\nType=Application\nName={NAME}\nExec=\"{exe}\" --no-browser\nX-GNOME-Autostart-enabled=true\n")
        os.chmod(path, 0o644)
