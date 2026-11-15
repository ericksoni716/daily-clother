import shutil

from closet import storage

from .conftest import upload

KEYS = {"items", "photos_bytes", "cutouts_bytes", "thumbnails_bytes", "database_bytes", "backups_bytes", "model_bytes",
        "logs_bytes", "total_bytes", "data_dir", "free_bytes"}
PARTS = ("photos_bytes", "cutouts_bytes", "thumbnails_bytes", "database_bytes", "backups_bytes", "model_bytes", "logs_bytes")


def test_storage_needs_login(anon):
    assert anon.get("/api/storage").status_code == 401


def test_storage_answer_has_the_promised_shape_and_no_file_names(client, cfg):
    body = client.get("/api/storage").json()
    assert set(body) == KEYS
    assert all(isinstance(body[k], int) and body[k] >= 0 for k in KEYS - {"data_dir", "free_bytes"})
    assert body["total_bytes"] == sum(body[k] for k in PARTS)
    assert body["data_dir"] == str(cfg.data_dir) and body["free_bytes"] > 0
    assert body["items"] == 0 and body["database_bytes"] > 0 and body["photos_bytes"] == 0
    assert ".webp" not in str(body) and "closet.db" not in str(body)


def test_adding_an_item_and_its_cutout_grow_the_right_numbers(client, services):
    before = client.get("/api/storage").json()
    upload(client)
    after = client.get("/api/storage").json()
    assert after["items"] == before["items"] + 1
    assert after["photos_bytes"] > 0 and after["thumbnails_bytes"] > 0 and after["cutouts_bytes"] == 0
    assert after["model_bytes"] == after["backups_bytes"] == 0
    services.worker.is_ready = lambda: True
    assert services.worker.drain() == 1
    cut = client.get("/api/storage").json()
    assert cut["cutouts_bytes"] > 0 and cut["thumbnails_bytes"] > after["thumbnails_bytes"]
    assert cut["photos_bytes"] == after["photos_bytes"]


def test_shared_folders_are_counted(client, cfg):
    for folder, name, size in ((cfg.models_dir, "m.onnx", 3000), (cfg.local_backups_dir / "pre-migration", "x.db", 2000),
                               (cfg.logs_dir, "closet.log", 500)):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(b"x" * size)
    body = client.get("/api/storage").json()
    assert (body["model_bytes"], body["backups_bytes"], body["logs_bytes"]) == (3000, 2000, 500)


def test_demo_and_main_closets_report_separately(client, cfg):
    upload(client)
    (cfg.models_dir).mkdir(parents=True, exist_ok=True)
    (cfg.models_dir / "m.onnx").write_bytes(b"x" * 1234)
    main = client.get("/api/storage").json()
    assert client.post("/api/profile", json={"profile": "demo"}).status_code == 200
    demo = client.get("/api/storage").json()
    assert demo["items"] == 49 and main["items"] == 1
    assert demo["cutouts_bytes"] > 0 and main["cutouts_bytes"] == 0
    assert demo["photos_bytes"] != main["photos_bytes"] and demo["database_bytes"] != main["database_bytes"]
    assert demo["photos_bytes"] == storage.image_bytes(cfg.images_dir("demo"))["photos_bytes"]
    assert demo["model_bytes"] == main["model_bytes"] == 1234  # shared
    assert client.post("/api/profile", json={"profile": "main"}).status_code == 200
    assert client.get("/api/storage").json()["photos_bytes"] == main["photos_bytes"]


def test_missing_folders_count_as_nothing(client, cfg):
    upload(client)
    for folder in (cfg.images_dir("main"), cfg.models_dir, cfg.local_backups_dir, cfg.logs_dir):
        shutil.rmtree(folder, ignore_errors=True)
    r = client.get("/api/storage")
    assert r.status_code == 200
    body = r.json()
    assert all(body[k] == 0 for k in PARTS if k != "database_bytes")
    assert body["items"] == 1 and body["total_bytes"] == body["database_bytes"]
    assert storage.usage(cfg, "demo")["items"] == 0  # a demo closet never opened


def test_links_out_of_the_data_folder_are_not_followed(cfg, tmp_path):
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "big.bin").write_bytes(b"x" * 5000)
    cfg.models_dir.mkdir(parents=True)
    try:
        (cfg.models_dir / "link").symlink_to(outside, target_is_directory=True)
        cfg.logs_dir.symlink_to(outside, target_is_directory=True)
    except OSError:  # pragma: no cover - creating links needs extra rights on Windows
        return
    assert storage.folder_bytes(cfg.models_dir) == 0 and storage.folder_bytes(cfg.logs_dir) == 0
