"""Moving the data folder from Closet to Nines in the user folder, once, at start (DECISIONS, "The program file: Nines").

Up to 0.11.0 the closet lived in ~/Closet. At start, before anything opens the folder, `settle` renames it to ~/Nines
with one rename: on the same disk that is all or nothing, so the closet is never half in each. When it cannot be done
(a copy still running there, a file held open, no permission) nothing changes, this run goes on in ~/Closet
(`config.default_data_dir` picks it), and the next start tries again. When both folders exist, Nines is used and
Closet is left as it is. A data folder chosen with CLOSET_DATA_DIR is never moved.
"""
from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

OLD = "Closet"
NEW = "Nines"
SETTINGS = "settings.json"


@dataclass(frozen=True)
class Outcome:
    kind: str                  # none, moved, both, running, failed
    message: str | None = None   # for the log, once logging is set up in the folder chosen


def settle(env, home: Path, running: Callable[[Path], bool]) -> Outcome:
    """Rename `home`/Closet to `home`/Nines if it is time to. `running(folder)` says whether a copy of the program is
    serving from that folder now."""
    if env.get("CLOSET_DATA_DIR"):
        return Outcome("none")
    old, new = home / OLD, home / NEW
    if new.exists():
        if old.exists():
            return Outcome("both", f"both {new} and {old} exist: {new} is used and {old} is left as it is")
        return Outcome("none")
    if not old.is_dir():
        return Outcome("none")
    if running(old):
        return Outcome("running", f"a copy is still running in {old}, so it stays there for now; "
                                  f"it moves to {new} at a later start")
    try:
        os.rename(old, new)
    except OSError as e:
        return Outcome("failed", f"could not rename {old} to {new} ({e}); this run uses {old}, "
                                 "and the next start tries again")
    note = f"moved the data folder from {old} to {new}"
    try:
        changed = _repoint(new / SETTINGS, old, new)
    except (OSError, ValueError) as e:
        return Outcome("moved", f"{note}; the paths in its settings could not be read ({e}) and were left as they were")
    return Outcome("moved", note + (f"; repointed {', '.join(changed)}" if changed else ""))


def _inside(stored: object, old: Path, new: Path) -> str | None:
    """`stored` as a path in `new` when it is `old` or inside it; None otherwise."""
    if not isinstance(stored, str) or not stored:
        return None
    path = Path(stored)
    parts, base = [os.path.normcase(p) for p in path.parts], [os.path.normcase(p) for p in old.parts]
    if parts[:len(base)] != base:
        return None
    return str(new.joinpath(*path.parts[len(base):]))


def _repoint(settings: Path, old: Path, new: Path) -> list[str]:
    """The settings that hold a path into the data folder are pointed at the moved folder. The others are untouched,
    and so is a key the program no longer knows. Returns what changed."""
    if not settings.exists():
        return []
    data = json.loads(settings.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("not a JSON object")
    changed = []
    if (moved := _inside(data.get("backup_folder"), old, new)) is not None:
        data["backup_folder"] = moved
        changed.append("backup_folder")
    for key, field in (("update_ready", "path"), ("last_backup", "folder")):
        entry = data.get(key)
        if isinstance(entry, dict) and (moved := _inside(entry.get(field), old, new)) is not None:
            entry[field] = moved
            changed.append(f"{key}.{field}")
    if changed:
        tmp = settings.with_name(settings.name + ".moving")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        os.replace(tmp, settings)
    return changed
