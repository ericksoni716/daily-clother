"""SQLite access and migrations.

Migrations are numbered SQL files applied in order; the database remembers its
version in `PRAGMA user_version`. Before an existing database is migrated a
copy is taken, and a database written by a newer program is refused rather
than opened.
"""
from __future__ import annotations

import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path

from .config import bundle_dir


class NewerDatabaseError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=15, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def migration_files() -> list[tuple[int, Path]]:
    files = []
    for p in sorted((bundle_dir() / "migrations").glob("*.sql")):
        files.append((int(p.name.split("_", 1)[0]), p))
    return files


def latest_version() -> int:
    files = migration_files()
    return files[-1][0] if files else 0


def snapshot(src: Path, dest: Path) -> None:
    """A consistent copy of a live database, using SQLite's own backup."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.unlink(missing_ok=True)
    s = sqlite3.connect(src)
    try:
        d = sqlite3.connect(tmp)
        try:
            s.backup(d)
            ok = d.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            d.close()
    finally:
        s.close()
    if ok != "ok":
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"backup copy failed its integrity check: {ok}")
    tmp.replace(dest)


def migrate(path: Path, backups_dir: Path) -> dict:
    """Bring the database at `path` up to date. Returns what happened."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existed = path.exists()
    conn = connect(path)
    try:
        current = conn.execute("PRAGMA user_version").fetchone()[0]
        target = latest_version()
        if current > target:
            raise NewerDatabaseError(
                f"This closet was last opened by a newer version of the program (data version {current}; "
                f"this program understands up to {target}). Download the latest version to open it. "
                "Nothing has been changed.")
        pending = [(v, p) for v, p in migration_files() if v > current]
        backup = None
        if pending and existed and current > 0:
            backup = backups_dir / f"pre-migration-v{current}-{time.strftime('%Y%m%d-%H%M%S')}.sqlite"
            snapshot(path, backup)
        for version, file in pending:
            sql = file.read_text(encoding="utf-8")
            try:
                conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {version};\nCOMMIT;")
            except Exception:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
        return {"from": current, "to": target, "applied": [v for v, _ in pending], "backup": str(backup) if backup else None}
    finally:
        conn.close()
