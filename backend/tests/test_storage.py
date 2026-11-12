import asyncio
import shutil
import sqlite3
from pathlib import Path

import pytest

from closet import db, jobs, storage

from .conftest import fake_cutter, upload

BYTE_FIELDS = {
    "photos_bytes", "cutouts_bytes", "thumbnails_bytes", "database_bytes",
    "backups_bytes", "model_bytes", "logs_bytes",
}


def test_storage_shape_and_missing_folders(client, cfg):
    for folder in (cfg.images_dir("main"), cfg.local_backups_dir, cfg.models_dir, cfg.logs_dir):
        if folder.exists():
            shutil.rmtree(folder)
    response = client.get("/api/storage")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == BYTE_FIELDS | {"items", "total_bytes", "data_dir", "free_bytes"}
    assert body["items"] == 0
    assert body["data_dir"] == str(cfg.data_dir)
    assert body["database_bytes"] > 0
    assert all(type(body[key]) is int and body[key] >= 0 for key in BYTE_FIELDS | {"total_bytes", "free_bytes"})
    assert all(body[key] == 0 for key in BYTE_FIELDS - {"database_bytes"})
    assert body["total_bytes"] == sum(body[key] for key in BYTE_FIELDS)
    assert body["free_bytes"] > 0


def test_storage_requires_login(anon):
    assert anon.get("/api/storage").status_code == 401


def test_upload_cutout_archive_and_delete_change_the_right_totals(client, cfg):
    before = client.get("/api/storage").json()
    item = upload(client).json()
    after = client.get("/api/storage").json()
    photo = item["photos"][0]
    size = lambda url: (cfg.images_dir("main") / url.removeprefix("/media/")).stat().st_size  # noqa: E731
    assert after["items"] == 1
    assert after["photos_bytes"] == size(photo["url"]) > 0
    assert after["thumbnails_bytes"] == size(photo["thumb_url"]) > 0
    assert after["cutouts_bytes"] == 0
    assert after["total_bytes"] > before["total_bytes"]

    conn = db.connect(cfg.db_path("main"))
    try:
        assert jobs.run_one(conn, cfg.images_dir("main"), fake_cutter)
        measured = client.get("/api/storage").json()
        assert measured["database_bytes"] == sum(p.stat().st_size for p in cfg.data_dir.glob("closet.db*"))
    finally:
        conn.close()
    photo = client.get(f"/api/items/{item['id']}").json()["photos"][0]
    assert measured["photos_bytes"] == after["photos_bytes"]
    assert measured["cutouts_bytes"] == size(photo["cutout_url"]) > 0
    assert measured["thumbnails_bytes"] == after["thumbnails_bytes"] + size(photo["cutout_thumb_url"])
    assert measured["total_bytes"] > after["total_bytes"]
    assert client.patch(f"/api/items/{item['id']}", json={"status": "archived"}).status_code == 200
    assert client.get("/api/storage").json()["items"] == 1
    assert client.delete(f"/api/items/{item['id']}").status_code == 204
    deleted = client.get("/api/storage").json()
    assert deleted["items"] == deleted["photos_bytes"] == deleted["cutouts_bytes"] == deleted["thumbnails_bytes"] == 0


def test_profiles_are_separate_and_local_folders_are_shared(client, cfg, tmp_path):
    for folder in (cfg.local_backups_dir, cfg.models_dir, cfg.logs_dir):
        (folder / "nested").mkdir(parents=True, exist_ok=True)
        (folder / "nested" / "sample").write_bytes(b"x" * 123)
    external = tmp_path / "external-backups"
    external.mkdir()
    (external / "ignored").write_bytes(b"x" * 1000)
    assert client.put("/api/settings", json={"backup_folder": str(external)}).status_code == 200
    upload(client)
    main = client.get("/api/storage").json()
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    demo = client.get("/api/storage").json()
    assert main["items"] == 1 and demo["items"] == 30
    for key in ("photos_bytes", "cutouts_bytes", "thumbnails_bytes", "database_bytes"):
        assert demo[key] > main[key]
    for key in ("backups_bytes", "model_bytes", "logs_bytes"):
        assert demo[key] == main[key] == 123
    assert demo["data_dir"] == main["data_dir"]
    assert client.post("/api/profile", json={"profile": "main"}).status_code == 200
    assert client.get("/api/storage").json() | {"free_bytes": 0} == main | {"free_bytes": 0}


def test_links_are_not_followed(client, cfg, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "p.webp").write_bytes(b"x" * 123)
    images = cfg.images_dir("main")
    images.mkdir()
    (images / "linked.webp").symlink_to(outside / "p.webp")
    (images / "linked-folder").symlink_to(outside, target_is_directory=True)
    (images / "loop").symlink_to(images, target_is_directory=True)
    (images / "broken.webp").symlink_to(outside / "missing")
    cfg.local_backups_dir.symlink_to(outside, target_is_directory=True)
    cfg.models_dir.symlink_to(outside, target_is_directory=True)
    measured = client.get("/api/storage").json()
    for key in ("photos_bytes", "cutouts_bytes", "thumbnails_bytes", "backups_bytes", "model_bytes"):
        assert measured[key] == 0

    # Even the profile folder and database itself must not redirect reads.
    (cfg.data_dir / "demo").symlink_to(outside, target_is_directory=True)
    assert storage.measure(cfg, "demo")["items"] == 0
    cfg.db_path("main").unlink()
    cfg.db_path("main").symlink_to(outside / "p.webp")
    assert client.get("/api/storage").json()["items"] == 0


def test_walk_tolerates_a_file_disappearing(client, cfg, monkeypatch):
    cfg.logs_dir.mkdir()
    gone = cfg.logs_dir / "gone.log"
    gone.write_bytes(b"gone")
    real_stat = Path.lstat

    def disappearing(path, *args, **kwargs):
        if path == gone:
            raise FileNotFoundError
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", disappearing)
    assert client.get("/api/storage").json()["logs_bytes"] == 0


def test_storage_walk_runs_off_the_event_loop(client, monkeypatch):
    original = storage.measure

    def measure(*args):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return original(*args)
        raise AssertionError("Storage must not run on the event loop")

    monkeypatch.setattr(storage, "measure", measure)
    assert client.get("/api/storage").status_code == 200


@pytest.mark.parametrize("error", [PermissionError, sqlite3.OperationalError])
def test_storage_error_does_not_expose_file_names(client, monkeypatch, error):
    def fail(*args):
        raise error("private-file-name")

    monkeypatch.setattr(storage, "measure", fail)
    response = client.get("/api/storage")
    assert response.status_code == 503
    assert "private-file-name" not in response.text
