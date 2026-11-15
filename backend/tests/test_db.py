import subprocess
import sys
from contextlib import closing

import pytest

from closet import backup, db, images
from closet.state import State

from .conftest import photo_bytes

MIGRATIONS = db.migration_files()
VERSIONS = [v for v, _ in MIGRATIONS]


def old_closet(cfg, version):
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    with closing(db.connect(cfg.db_path("main"))) as conn:
        for v, path in MIGRATIONS:
            if v <= version:
                conn.executescript(f"BEGIN IMMEDIATE;\n{path.read_text(encoding='utf-8')}\nPRAGMA user_version = {v};\nCOMMIT;")
        conn.execute("INSERT INTO items (id, name, created_at, updated_at) VALUES ('kept', ?, ?, ?)",
                     ("Résumé 衣服", db.now(), db.now()))
        photo = images.store_upload(photo_bytes(), cfg.images_dir("main"), "kept", "front")
        conn.execute("INSERT INTO photos (id, item_id, original_path, thumb_path, created_at) VALUES ('front', 'kept', ?, ?, ?)",
                     (photo.original_path, photo.thumb_path, db.now()))


@pytest.mark.parametrize("version", VERSIONS)
def test_backup_restore_upgrades_every_shipped_version(cfg, tmp_path, version):
    old_closet(cfg, version)
    folder = tmp_path / "Synced"
    folder.mkdir()
    state = State(cfg.state_path)
    state.update(profile="demo")
    assert backup.run_backup(cfg, state, folder=folder)["ok"]
    settings = cfg.state_path.read_bytes()
    photos = {p.relative_to(cfg.images_dir("main")): p.read_bytes()
              for p in cfg.images_dir("main").rglob("*") if p.is_file()}
    with closing(db.connect(cfg.db_path("main"))) as conn:
        conn.execute("DELETE FROM items")

    result = backup.restore(cfg, folder)
    assert result["items"] == 1
    with closing(db.connect(cfg.db_path("main"))) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == db.latest_version()
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        assert conn.execute("SELECT name FROM items WHERE id = 'kept'").fetchone()[0] == "Résumé 衣服"
        assert conn.execute("SELECT item_id FROM photos WHERE id = 'front'").fetchone()[0] == "kept"
    assert {p.relative_to(cfg.images_dir("main")): p.read_bytes()
            for p in cfg.images_dir("main").rglob("*") if p.is_file()} == photos
    assert cfg.state_path.read_bytes() == settings


@pytest.mark.parametrize("version", VERSIONS[:-1])
def test_killed_migration_rolls_back_and_can_restart(cfg, version):
    old_closet(cfg, version)
    next_version, migration = next((v, p) for v, p in MIGRATIONS if v > version)
    with closing(db.connect(cfg.db_path("main"))) as conn:
        before = conn.execute("SELECT type, name, sql FROM sqlite_master ORDER BY type, name").fetchall()
    code = """
import sqlite3
import sys
import time
from pathlib import Path
conn = sqlite3.connect(sys.argv[1], isolation_level=None)
sql = Path(sys.argv[2]).read_text(encoding="utf-8")
conn.executescript("BEGIN IMMEDIATE;\\n" + sql + "\\nPRAGMA user_version = " + sys.argv[3] + ";")
print("uncommitted", flush=True)
time.sleep(60)
"""
    with subprocess.Popen([sys.executable, "-c", code, str(cfg.db_path("main")), str(migration), str(next_version)],
                          stdout=subprocess.PIPE, text=True) as child:
        try:
            assert child.stdout.readline().strip() == "uncommitted"
        finally:
            child.kill()
            child.wait(timeout=10)
    with closing(db.connect(cfg.db_path("main"))) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == version
        assert conn.execute("SELECT type, name, sql FROM sqlite_master ORDER BY type, name").fetchall() == before
    result = db.migrate(cfg.db_path("main"), cfg.local_backups_dir)
    assert result["from"] == version and result["to"] == db.latest_version()
    with closing(db.connect(cfg.db_path("main"))) as conn:
        assert conn.execute("SELECT name FROM items WHERE id = 'kept'").fetchone()[0] == "Résumé 衣服"
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
