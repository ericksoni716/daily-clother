"""Keeping Nines running on Windows: a scheduled task that starts a background copy (`--background`) and starts it
again when it stops (DECISIONS, "Kept running by Windows").

Turning it on (from Settings, in the ordinary copy the owner is using) copies the running program to a folder of
Nines' own (`install_dir()`, %LOCALAPPDATA%\\Nines), so the task never depends on where the owner keeps the
downloaded file, and registers the task behind one administrator prompt. The elevated script first asks Windows
whether it will run a task as the owner without a sign-in (a throwaway task that runs whoami); if it will, the task
starts when the computer turns on, and otherwise when the owner signs in. Both run the copy with `--background
--port <port> --home <user folder>`, so it finds the same data folder and the owner's home before anyone signs in.
Task Scheduler's own "restart if the task fails" reacts to a task that could not be started, not to a program that
ends (with any exit code), so the task also has a trigger that repeats every few minutes with "do not start a new
instance": a background copy that has stopped is started again within `REPEAT_MINUTES`. The task's security
descriptor lets the owner's own account read and run it (`GRGX`), so a launch, an update or "Start it again" can start
it without another administrator prompt.

Once it is on, the program never serves by itself: a launch that finds no background copy running starts the task,
waits for it, and becomes a window onto it (closet/cli.py). Turning it off needs the administrator prompt again, so it
is done in the owner's own session (the window onto the background copy, or an ordinary copy), never by a background
copy, which may run where no prompt can be shown.

Every call to Windows (`elevated`, `run_task`, `end_task`, `windows_user`) is a function here that the tests replace.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from . import apikey, autostart, config, instance
from .config import Config

log = logging.getLogger("closet.background")

TASK_NAME = "Nines"            # what Windows lists in Task Scheduler
EXE_NAME = "Nines.exe"         # the copy of the program the task runs, in `install_dir()`
MARKER = "background.json"     # beside it: how the task starts, which port and whose home it was set up with
OUTCOME = "background-outcome.json"   # in the data folder: why turning it off from the window did not work
WAIT = 90                      # seconds a launch waits for the background copy to answer once the task is started
REPEAT_MINUTES = 5             # a stopped background copy is started again within this many minutes
OUTCOME_FOR = 600              # seconds Settings shows why turning it off did not work
ERROR_CANCELLED = 1223         # Windows' code for "the operation was cancelled by the user" (the prompt declined)
_NO_WINDOW = 0x08000000        # CREATE_NO_WINDOW

NOT_HERE = "Windows can keep Nines running only in the downloaded Nines program for Windows."
DECLINED = "Windows asked for permission on this computer's screen and it was not given, so nothing changed."
FROM_COMPUTER = ("Windows asks for permission on the computer's own screen, so this can only be changed in Nines on "
                 "the computer.")


class SetupError(RuntimeError):
    """Turning it on or off did not work; the message is a sentence for the owner."""


class Declined(SetupError):
    def __init__(self) -> None:
        super().__init__(DECLINED)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- where it lives
def supported(platform: str | None = None, frozen: bool | None = None) -> bool:
    """Only the packaged program on Windows: the task runs a program file, not Python and a source folder."""
    platform = platform or sys.platform
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    return platform == "win32" and frozen


def install_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    return (Path(local) if local else Path.home() / "AppData" / "Local") / "Nines"


def installed_exe() -> Path:
    return install_dir() / EXE_NAME


def marker_path() -> Path:
    return install_dir() / MARKER


def read_marker() -> dict | None:
    try:
        marker = json.loads(marker_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return marker if isinstance(marker, dict) and marker.get("starts") in ("startup", "logon") else None


def _write_marker(marker: dict) -> None:
    path = marker_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    part.write_text(json.dumps(marker, indent=1), encoding="utf-8")
    os.replace(part, path)


def task_data_dir(marker: dict) -> Path:
    """The data folder the task's copy uses: the one chosen with CLOSET_DATA_DIR when it was set up, else the usual
    one in the owner's home as it is now (Nines, or Closet while it has not been moved: closet/datafolder.py)."""
    if marker.get("data_dir"):
        return Path(marker["data_dir"])
    return config.default_data_dir(Path(marker.get("home") or Path.home()))


def _same(a: Path, b: Path) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def is_set_up(cfg: Config) -> bool:
    """Whether Windows keeps a background copy running for this closet. Read from the marker and the copy, without
    asking Windows (quick enough for every launch and every read of Settings)."""
    if not supported():
        return False
    marker = read_marker()
    return marker is not None and installed_exe().is_file() and _same(task_data_dir(marker), cfg.data_dir)


def task_arguments(port: int, home: str, data_dir: str | None) -> str:
    """The command line the task gives the copy, quoted as Windows reads it (a home with spaces stays one argument)."""
    args = ["--background", "--port", str(port), "--home", home]
    if data_dir:
        args += ["--data-dir", data_dir]
    return subprocess.list2cmdline(args)


# ---------------------------------------------------------------- the scripts that run behind the prompt
def _ps(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


_SCRIPT_HEAD = r"""
$ErrorActionPreference = 'Stop'
$TaskName = __TASK__
$Exe = __EXE__
$ResultFile = __RESULT__
function Write-Result($result) { $result | ConvertTo-Json -Compress | Set-Content -LiteralPath $ResultFile -Encoding UTF8 }
"""

_INSTALL = r"""
$Arguments = __ARGS__
$UserId = __USER__
$WorkDir = __WORKDIR__
function Test-RunsWithoutSignIn {
  # A throwaway task, run as you without a sign-in and without storing your password (S4U). If Windows runs it, the
  # real task can start when the computer turns on; if not (some accounts cannot), it starts when you sign in.
  $probe = "$TaskName check"
  Unregister-ScheduledTask -TaskName $probe -Confirm:$false -ErrorAction SilentlyContinue
  try {
    $a = New-ScheduledTaskAction -Execute (Join-Path $env:SystemRoot 'System32\whoami.exe')
    $p = New-ScheduledTaskPrincipal -UserId $UserId -LogonType S4U -RunLevel Limited
    $s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName $probe -Action $a -Principal $p -Settings $s -Force | Out-Null
    Start-ScheduledTask -TaskName $probe
    for ($i = 0; $i -lt 40; $i++) {
      Start-Sleep -Milliseconds 500
      $state = (Get-ScheduledTask -TaskName $probe).State
      $last = (Get-ScheduledTaskInfo -TaskName $probe).LastTaskResult
      # 267009: still running; 267011: not run yet
      if ($state -ne 'Running' -and $state -ne 'Queued' -and $last -ne 267009 -and $last -ne 267011) { return ($last -eq 0) }
    }
    return $false
  } catch {
    return $false
  } finally {
    Unregister-ScheduledTask -TaskName $probe -Confirm:$false -ErrorAction SilentlyContinue
  }
}
try {
  $starts = if (Test-RunsWithoutSignIn) { 'startup' } else { 'logon' }
  $action = New-ScheduledTaskAction -Execute $Exe -Argument $Arguments -WorkingDirectory $WorkDir
  if ($starts -eq 'startup') {
    $first = New-ScheduledTaskTrigger -AtStartup
    $principal = New-ScheduledTaskPrincipal -UserId $UserId -LogonType S4U -RunLevel Limited
  } else {
    $first = New-ScheduledTaskTrigger -AtLogOn -User $UserId
    $principal = New-ScheduledTaskPrincipal -UserId $UserId -LogonType Interactive -RunLevel Limited
  }
  # Task Scheduler restarts a task that could not be started, not a program that ended: this trigger starts a stopped
  # background copy again every few minutes, and does nothing while one runs (IgnoreNew).
  $again = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes __REPEAT__) `
    -RepetitionDuration (New-TimeSpan -Days 9999)
  $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
  Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($first, $again) -Principal $principal `
    -Settings $settings -Description 'Keeps Nines running so your phone can reach it.' -Force | Out-Null
  # Your own account may read and run the task (a launch, an update, Start it again) without this prompt; only
  # administrators may change or remove it.
  $sid = (New-Object System.Security.Principal.NTAccount($UserId)).Translate([System.Security.Principal.SecurityIdentifier]).Value
  $service = New-Object -ComObject Schedule.Service
  $service.Connect()
  $service.GetFolder('\').GetTask($TaskName).SetSecurityDescriptor("D:(A;;FA;;;SY)(A;;FA;;;BA)(A;;GRGX;;;$sid)", 0)
  Write-Result @{ ok = $true; starts = $starts }
  exit 0
} catch {
  Write-Result @{ ok = $false; error = $_.Exception.Message }
  exit 1
}
"""

_UNINSTALL = r"""
try {
  Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
  Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $Exe } | Stop-Process -Force -ErrorAction SilentlyContinue
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
  for ($i = 0; $i -lt 20 -and (Test-Path -LiteralPath $Exe); $i++) {
    try { Remove-Item -LiteralPath $Exe -Force -ErrorAction Stop } catch { Start-Sleep -Milliseconds 500 }
  }
  Write-Result @{ ok = $true }
  exit 0
} catch {
  Write-Result @{ ok = $false; error = $_.Exception.Message }
  exit 1
}
"""


def _head(exe: Path, result: Path) -> str:
    return (_SCRIPT_HEAD.replace("__TASK__", _ps(TASK_NAME)).replace("__EXE__", _ps(str(exe)))
            .replace("__RESULT__", _ps(str(result))))


def install_script(exe: Path, arguments: str, user: str, result: Path, workdir: Path | None = None) -> str:
    """`workdir`: where the task starts the program (its own folder unless given; the Windows CI test gives another)."""
    return _head(exe, result) + (_INSTALL.replace("__ARGS__", _ps(arguments)).replace("__USER__", _ps(user))
                                 .replace("__WORKDIR__", _ps(str(workdir or Path(exe).parent)))
                                 .replace("__REPEAT__", str(REPEAT_MINUTES)))


def uninstall_script(exe: Path, result: Path) -> str:
    return _head(exe, result) + _UNINSTALL


# ---------------------------------------------------------------- the calls to Windows (tests replace these)
def _encoded(script: str) -> str:
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


def elevated(script: str, result: Path, elevate: bool = True) -> dict:
    """Run `script` in PowerShell with administrator rights; Windows asks first, on this computer's screen. The script
    goes on the command line, encoded, rather than into a file another program could change before it runs. Returns
    what it wrote to `result`. Raises Declined when the prompt was not accepted, SetupError when it did not finish.
    `elevate=False` runs it as this process already is (the Windows CI test, whose account is an administrator)."""
    result.parent.mkdir(parents=True, exist_ok=True)
    result.unlink(missing_ok=True)
    inner = f"-NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand {_encoded(script)}"
    if elevate:
        outer = ("try { $p = Start-Process -FilePath powershell.exe -Verb RunAs -WindowStyle Hidden -Wait -PassThru "
                 f"-ArgumentList {_ps(inner)}; exit $p.ExitCode }} catch {{ $e = $_.Exception; "
                 f"while ($e) {{ if ($e.NativeErrorCode -eq {ERROR_CANCELLED}) {{ exit {ERROR_CANCELLED} }}; "
                 "$e = $e.InnerException }; exit 2 }")
        command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", outer]
    else:
        command = ["powershell.exe", *inner.split(" ")]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=600, creationflags=_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise SetupError(f"Windows did not finish setting this up ({e}).") from e
    try:
        outcome = json.loads(result.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        outcome = None
    finally:
        result.unlink(missing_ok=True)
    if outcome is None:
        if proc.returncode == ERROR_CANCELLED or "canceled by the user" in (proc.stderr or "").lower():
            raise Declined()
        log.warning("the setup script left no result (exit code %s): %s", proc.returncode, (proc.stderr or "")[-500:])
        raise SetupError("Windows did not finish setting this up. Nothing was changed.")
    if not outcome.get("ok"):
        raise SetupError(f"Windows could not set this up: {outcome.get('error') or 'it did not say why'}.")
    return outcome


def run_task() -> bool:
    """Ask Task Scheduler to start the task now (it does nothing while the background copy runs). True when it took
    the request. Needs no administrator rights: the task lets its own user run it."""
    try:
        proc = subprocess.run(["schtasks", "/Run", "/TN", TASK_NAME], capture_output=True, text=True, timeout=30,
                              creationflags=_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return False
    if proc.returncode != 0:
        log.warning("Windows did not start the task %s (exit code %s)", TASK_NAME, proc.returncode)
    return proc.returncode == 0


def end_task() -> None:
    """Ask Task Scheduler to stop the task (best effort: the background copy is normally asked to quit instead)."""
    try:
        subprocess.run(["schtasks", "/End", "/TN", TASK_NAME], capture_output=True, text=True, timeout=30,
                       creationflags=_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        pass


def windows_user() -> str:
    """This account as Windows names it in a task (COMPUTER\\name, or AzureAD\\name)."""
    import csv
    import io
    out = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True, check=True,
                         timeout=30, creationflags=_NO_WINDOW).stdout
    return next(csv.reader(io.StringIO(out.strip())))[0]


# ---------------------------------------------------------------- turning it on and off
def turn_on(cfg: Config, exe: str | Path, port: int) -> dict:
    """Run by the ordinary copy the owner is using: copy `exe` (this program) into place, register the task behind one
    administrator prompt, turn off start at login, and seal the API key for a copy started before sign-in. Does not
    start the task: this copy still has the port, and hands it over afterwards (closet/cli.py). Returns {"starts"}."""
    if not supported():
        raise SetupError(NOT_HERE)
    source, target = Path(exe), installed_exe()
    copied = False
    target.parent.mkdir(parents=True, exist_ok=True)
    if not _same(source, target):
        part = target.with_name(target.name + ".part")
        try:
            shutil.copyfile(source, part)
            os.replace(part, target)
            copied = True
        except OSError as e:
            part.unlink(missing_ok=True)
            raise SetupError(f"Nines could not put a copy of itself in {target.parent} ({e}). Nothing was changed.")
    home = os.environ.get("USERPROFILE") or str(Path.home())
    chosen = os.environ.get("CLOSET_DATA_DIR") or None   # a data folder chosen by hand goes with the task
    try:
        user = windows_user()
        outcome = elevated(install_script(target, task_arguments(port, home, chosen and str(cfg.data_dir)), user,
                                          install_dir() / "setup-result.json"), install_dir() / "setup-result.json")
    except Exception as e:
        if copied:
            target.unlink(missing_ok=True)
        if isinstance(e, SetupError):
            raise
        raise SetupError(f"Windows did not finish setting this up ({e}). Nothing was changed.") from e
    starts = "startup" if outcome.get("starts") == "startup" else "logon"
    was_on = False
    try:
        was_on = autostart.is_enabled()
        if was_on:
            autostart.set_enabled(False)   # it would open a window onto the background copy at every sign-in
    except Exception:
        log.warning("could not turn off start at login", exc_info=True)
    _write_marker({"starts": starts, "port": port, "home": home, "data_dir": str(cfg.data_dir) if chosen else None,
                   "autostart_was_on": was_on, "at": _now()})
    seal_key(cfg)
    clear_outcome(cfg)
    log.info("Windows now keeps Nines running (it starts %s), on port %s",
             "when the computer turns on" if starts == "startup" else "when you sign in", port)
    return {"starts": starts}


def seal_key(cfg: Config) -> None:
    """Copy the key from Credential Manager into the sealed file, so a copy started before sign-in can use it."""
    try:
        key = apikey.store().get()
    except Exception:
        key = None
    try:
        if key:
            apikey.write_sealed(cfg.data_dir, key)
        apikey.keep_sealed(cfg.data_dir)
    except Exception:
        log.warning("could not seal the API key for the background copy; save it again in Settings")


def turn_off(cfg: Config) -> None:
    """Run in the owner's own session (the window onto the background copy, or an ordinary copy): stop the background
    copy, remove the task and the copy behind one administrator prompt, put the key back where it was, and start at
    login back on if it was on before. The closet's data is not touched."""
    if not supported():
        raise SetupError(NOT_HERE)
    marker = read_marker() or {}
    exe = installed_exe()
    elevated(uninstall_script(exe, install_dir() / "setup-result.json"), install_dir() / "setup-result.json")
    for leftover in (exe, exe.with_name(f"{exe.stem}.old{exe.suffix}"), exe.with_name(f"{exe.stem}.new{exe.suffix}"),
                     exe.with_name(f"{exe.stem}.failed{exe.suffix}"), marker_path()):
        try:
            leftover.unlink(missing_ok=True)
        except OSError:
            log.info("could not remove %s yet", leftover)
    apikey.unseal_back(cfg.data_dir)
    apikey.keep_sealed(None)
    clear_outcome(cfg)
    if marker.get("autostart_was_on") and autostart.program():
        try:
            autostart.set_enabled(True)
        except Exception:
            log.warning("could not turn start at login back on", exc_info=True)
    log.info("Windows no longer keeps Nines running")


def key_changed(cfg: Config) -> Path | None:
    """The data folder to keep the sealed key in when the key is saved or removed, while Windows keeps Nines running."""
    return cfg.data_dir if is_set_up(cfg) else None


# ---------------------------------------------------------------- waiting for it, and what Settings shows
def wait_for(cfg: Config, timeout: float = WAIT, poll: float = 0.5) -> dict | None:
    """The background copy once it answers for this closet, within `timeout` seconds; None if it does not."""
    deadline = time.monotonic() + timeout
    while True:
        info = instance.running_info(cfg)
        if info and info.get("background"):
            return info
        if time.monotonic() >= deadline:
            return None
        time.sleep(poll)


def start_and_wait(cfg: Config, timeout: float = WAIT) -> dict | None:
    """Start the task and wait for its copy. A start already under way (after boot, or the repeating trigger) is
    waited for the same way: Task Scheduler does not start a second one."""
    run_task()
    return wait_for(cfg, timeout)


def note_outcome(cfg: Config, note: str) -> None:
    path = cfg.data_dir / OUTCOME
    try:
        path.write_text(json.dumps({"at": time.time(), "note": note}), encoding="utf-8")
    except OSError:
        log.warning("could not write down why turning it off did not work")


def read_outcome(cfg: Config, now: float | None = None) -> str | None:
    try:
        outcome = json.loads((cfg.data_dir / OUTCOME).read_text(encoding="utf-8"))
        if (now or time.time()) - float(outcome["at"]) <= OUTCOME_FOR:
            return str(outcome["note"])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def clear_outcome(cfg: Config) -> None:
    try:
        (cfg.data_dir / OUTCOME).unlink(missing_ok=True)
    except OSError:
        pass


def status(cfg: Config, background_copy: bool) -> dict:
    """What Settings shows. `background_copy`: the copy answering is the background copy (so it is running now).
    `port`: the port this copy answers on, the one phone access must point at (once Windows keeps Nines running it
    never changes: the background copy never moves to another)."""
    if not supported():
        return {"available": False, "on": False, "starts": None, "running": False, "port": cfg.port, "problem": None}
    marker = read_marker() if is_set_up(cfg) else None
    return {"available": True, "on": marker is not None, "starts": marker.get("starts") if marker else None,
            "running": background_copy, "port": cfg.port, "problem": read_outcome(cfg)}


# ---------------------------------------------------------------- a newer program opened beside an older background copy
def move_to(cfg: Config, info: dict, exe: str | Path, version: str) -> tuple[bool, str | None]:
    """Move the background copy to `exe` (the newer program the owner opened), the way an update does: every closet
    backed up first, the old program kept beside the new one, both started through the task, and the old one put back
    if the new one does not answer. Needs no administrator prompt: the copy's folder is the owner's, and the task lets
    the owner run it. Returns (whether it worked, the sentence to show when it did not)."""
    from . import updates
    from .state import State
    where = updates.layout("win32", str(installed_exe()))
    if where is None:
        return False, NOT_HERE
    theirs = info.get("version") or "an older version"
    try:
        snapshots = updates.backup_all(cfg, State(cfg.state_path), theirs)
        updates.swap(where, Path(exe), updates.sha256_file(Path(exe)))
    except (updates.UpdateError, OSError) as e:
        return False, str(e)
    plan = {"from": theirs, "to": version, "platform": "win32", "installed": str(where.installed),
            "old": str(where.old), "inner": str(where.inner), "args": [], "old_pid": info.get("pid"),
            "data_dir": str(cfg.data_dir), "timeout": updates.START_THROUGH_TASK,
            "snapshots": {k: str(v) for k, v in snapshots.items()}, "via_task": True}
    updates.outcome_path(cfg).unlink(missing_ok=True)
    if updates.watch(cfg, plan):
        return True, None
    try:
        note = json.loads(updates.outcome_path(cfg).read_text(encoding="utf-8")).get("note")
    except (OSError, ValueError):
        note = None
    return False, note or f"Nines {version} did not start in the background, so {theirs} was put back."
