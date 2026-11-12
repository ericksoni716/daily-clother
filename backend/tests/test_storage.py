import shutil

from .conftest import upload

EXPECTED_KEYS = {
    "items", "photos_bytes", "cutouts_bytes", "thumbnails_bytes", "database_bytes",
    "backups_bytes", "model_bytes", "logs_bytes", "total_bytes", "data_dir", "free_bytes",
}


def test_storage_requires_login(anon):
    assert anon.get("/api/storage").status_code == 401
    from .conftest import PASSPHRASE
    assert anon.post("/api/setup", json={"passphrase": PASSPHRASE}).status_code == 204
    assert anon.get("/api/storage").status_code == 200
    assert anon.post("/api/logout").status_code == 204
    assert anon.get("/api/storage").status_code == 401


def test_storage_shape_and_adding_an_item_increases_the_right_numbers(client, services, cfg):
    empty = client.get("/api/storage")
    assert empty.status_code == 200
    b0 = empty.json()
    assert set(b0.keys()) == EXPECTED_KEYS
    assert b0["items"] == 0
    assert (b0["photos_bytes"], b0["cutouts_bytes"], b0["thumbnails_bytes"]) == (0, 0, 0)
    assert (b0["backups_bytes"], b0["model_bytes"], b0["logs_bytes"]) == (0, 0, 0)
    assert b0["database_bytes"] > 0 and b0["total_bytes"] == b0["database_bytes"]
    assert b0["data_dir"] == str(cfg.data_dir) and b0["free_bytes"] > 0

    item = upload(client, name="Oxford shirt").json()
    b1 = client.get("/api/storage").json()
    assert b1["items"] == 1
    assert b1["photos_bytes"] > 0 and b1["thumbnails_bytes"] > 0 and b1["cutouts_bytes"] == 0
    assert b1["total_bytes"] > b0["total_bytes"]
    assert b1["total_bytes"] == (
        b1["photos_bytes"] + b1["cutouts_bytes"] + b1["thumbnails_bytes"]
        + b1["database_bytes"] + b1["backups_bytes"] + b1["model_bytes"] + b1["logs_bytes"]
    )
    # no file names leak in the response
    raw = str(b1)
    assert item["id"] not in raw and ".webp" not in raw and "closet.db" not in raw

    services.worker.is_ready = lambda: True
    assert services.worker.drain() == 1
    b2 = client.get("/api/storage").json()
    assert b2["cutouts_bytes"] > 0
    assert b2["thumbnails_bytes"] > b1["thumbnails_bytes"]
    assert b2["photos_bytes"] == b1["photos_bytes"]
    assert b2["total_bytes"] > b1["total_bytes"]

    client.delete(f"/api/items/{item['id']}")
    b3 = client.get("/api/storage").json()
    assert b3["items"] == 0
    assert (b3["photos_bytes"], b3["cutouts_bytes"], b3["thumbnails_bytes"]) == (0, 0, 0)


def test_demo_and_main_profiles_report_separately_but_share_model_logs_and_backups(client, cfg):
    cfg.models_dir.mkdir(parents=True, exist_ok=True)
    (cfg.models_dir / "isnet-general-use.onnx").write_bytes(b"m" * 2048)
    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    (cfg.logs_dir / "closet.log").write_bytes(b"l" * 512)
    cfg.local_backups_dir.mkdir(parents=True, exist_ok=True)
    (cfg.local_backups_dir / "pre-migration-v1.sqlite").write_bytes(b"b" * 1024)

    upload(client, name="Only in main")
    main_info = client.get("/api/storage").json()
    assert main_info["items"] == 1
    assert main_info["photos_bytes"] > 0 and main_info["cutouts_bytes"] == 0
    assert (main_info["model_bytes"], main_info["logs_bytes"], main_info["backups_bytes"]) == (2048, 512, 1024)

    client.post("/api/profile", json={"profile": "demo"})
    demo_info = client.get("/api/storage").json()
    assert demo_info["items"] == 30
    assert demo_info["photos_bytes"] > main_info["photos_bytes"]
    assert demo_info["cutouts_bytes"] > 0
    assert demo_info["thumbnails_bytes"] > main_info["thumbnails_bytes"]
    assert demo_info["database_bytes"] != main_info["database_bytes"]
    assert (demo_info["model_bytes"], demo_info["logs_bytes"], demo_info["backups_bytes"]) == (2048, 512, 1024)


def test_missing_folders_count_as_zero_and_outside_files_are_not_read(client, cfg, tmp_path):
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"x" * 9999)
    cfg.models_dir.mkdir(parents=True, exist_ok=True)
    try:
        (cfg.models_dir / "link.bin").symlink_to(outside)
    except OSError:
        pass
    assert client.get("/api/storage").json()["model_bytes"] == 0

    for folder in (cfg.images_dir("main"), cfg.local_backups_dir, cfg.models_dir, cfg.logs_dir):
        shutil.rmtree(folder, ignore_errors=True)
    for suffix in ("", "-wal", "-shm"):
        cfg.db_path("main").with_name(cfg.db_path("main").name + suffix).unlink(missing_ok=True)

    info = client.get("/api/storage").json()
    assert info["items"] == 0
    assert info["total_bytes"] == 0
    assert (info["photos_bytes"], info["cutouts_bytes"], info["thumbnails_bytes"], info["database_bytes"]) == (0, 0, 0, 0)
    assert (info["backups_bytes"], info["model_bytes"], info["logs_bytes"]) == (0, 0, 0)
    assert info["free_bytes"] > 0
