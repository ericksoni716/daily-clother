import io
from pathlib import Path

import pytest
from PIL import Image

from closet import db, images, vocab

from .conftest import photo_bytes, upload


def test_upload_returns_at_once_and_is_usable_before_the_cutout(client, cfg):
    r = upload(client, name="Red thing")
    assert r.status_code == 201
    item = r.json()
    assert item["cutout_state"] == "pending" and item["name"] == "Red thing" and item["location"] == "closet"
    assert item["thumb_url"].startswith("/media/") and item["photos"][0]["cutout_url"] is None
    thumb = client.get(item["thumb_url"])
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/webp"
    assert [i["id"] for i in client.get("/api/items").json()["items"]] == [item["id"]]


def test_stored_photo_is_at_most_1600px_and_the_upload_is_not_kept(client, cfg):
    item = upload(client, photo_bytes(size=(3000, 4000))).json()
    files = sorted(p.name for p in (cfg.images_dir("main") / item["id"]).iterdir())
    assert len(files) == 2 and all(f.endswith(".webp") for f in files)
    with Image.open(cfg.images_dir("main") / item["photos"][0]["url"].removeprefix("/media/")) as im:
        assert max(im.size) == images.MAX_EDGE


@pytest.mark.parametrize("failed_save", [1, 2])
def test_failed_photo_save_leaves_no_orphan_files(client, cfg, monkeypatch, failed_save):
    save = images.save_webp
    calls = 0

    def disk_full(img, path, quality):
        nonlocal calls
        calls += 1
        if calls == failed_save:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.with_suffix(".part").write_bytes(b"partial")
            raise OSError("disk full")
        return save(img, path, quality)

    monkeypatch.setattr(images, "save_webp", disk_full)
    with pytest.raises(OSError, match="disk full"):
        upload(client)
    assert client.get("/api/items").json()["items"] == []
    assert not list(cfg.images_dir("main").glob("*"))


def test_retried_upload_with_the_same_key_makes_no_duplicate(client):
    first = upload(client, key="same")
    again = upload(client, key="same")
    assert first.status_code == 201 and again.status_code == 200
    assert first.json()["id"] == again.json()["id"]
    assert len(client.get("/api/items").json()["items"]) == 1
    assert upload(client, photo_bytes(color=(20, 90, 160)), key="other").status_code == 201


def test_a_file_that_is_not_a_photo_is_refused_clearly(client, cfg):
    r = client.post("/api/items", files={"photo": ("x.jpg", b"not an image", "image/jpeg")}, data={"client_key": "bad"})
    assert r.status_code == 400 and "not a photo" in r.json()["detail"]
    assert client.get("/api/items").json()["items"] == []
    assert not any(cfg.images_dir("main").glob("*")) if cfg.images_dir("main").exists() else True


def test_png_and_heic_uploads_are_accepted(client):
    assert upload(client, photo_bytes("PNG"), key="png").status_code == 201
    if images.HEIC:
        import pillow_heif
        buf = io.BytesIO()
        pillow_heif.from_pillow(Image.new("RGB", (640, 480), (20, 90, 160))).save(buf, format="HEIF")
        r = upload(client, buf.getvalue(), key="heic")
        assert r.status_code == 201 and r.json()["photos"][0]["width"] == 640


def test_an_avif_photo_saved_from_a_shop_is_stored_like_any_photo(client, cfg):
    buf = io.BytesIO()
    Image.new("RGB", (800, 1000), (40, 120, 70)).save(buf, "AVIF", quality=70)
    r = client.post("/api/items", files={"photo": ("shop.avif", buf.getvalue(), "image/avif")}, data={"client_key": "avif"})
    assert r.status_code == 201
    item = r.json()
    assert (item["photos"][0]["width"], item["photos"][0]["height"]) == (800, 1000)
    files = sorted(p.name for p in (cfg.images_dir("main") / item["id"]).iterdir())
    assert len(files) == 2 and all(f.endswith(".webp") for f in files)


def test_editing_checks_the_vocabulary_and_records_who_set_a_field(client):
    item = upload(client).json()
    r = client.patch(f"/api/items/{item['id']}", json={"category": "jeans", "color": "navy", "silhouette": {"leg": "tapered"},
                                                       "brand": "  Acme ", "price_cents": 4500, "rating": "love"})
    assert r.status_code == 200
    body = r.json()
    assert (body["category"], body["color"], body["brand"], body["price_cents"], body["rating"]) == ("jeans", "navy", "Acme", 4500, "love")
    assert body["silhouette"] == {"leg": "tapered"} and body["source"]["category"] == "user" and body["confidence"]["category"] == 1.0
    bad = client.patch(f"/api/items/{item['id']}", json={"category": "spaceship"})
    assert bad.status_code == 422 and "not a known category" in bad.json()["detail"]
    assert client.patch(f"/api/items/{item['id']}", json={"silhouette": {"leg": "bendy"}}).status_code == 422
    assert client.patch(f"/api/items/{item['id']}", json={"id": "x"}).status_code == 422
    assert client.patch(f"/api/items/{item['id']}", json={"price_cents": -1}).status_code == 422
    assert client.patch("/api/items/nope", json={"name": "x"}).status_code == 404
    assert client.patch(f"/api/items/{item['id']}", json={"brand": ""}).json()["brand"] is None


def test_filtering_search_archive_and_delete(client, cfg):
    a = upload(client, key="a", name="Blue oxford").json()
    b = upload(client, photo_bytes(color=(20, 40, 90)), key="b", name="Old jeans").json()
    client.patch(f"/api/items/{a['id']}", json={"category": "shirt"})
    client.patch(f"/api/items/{b['id']}", json={"category": "jeans"})
    names = lambda **p: [i["name"] for i in client.get("/api/items", params=p).json()["items"]]  # noqa: E731
    assert names(category="shirt") == ["Blue oxford"]
    assert names(q="JEANS") == ["Old jeans"]
    client.patch(f"/api/items/{b['id']}", json={"status": "archived"})
    assert names() == ["Blue oxford"] and names(status="archived") == ["Old jeans"]
    assert client.delete(f"/api/items/{a['id']}").status_code == 204
    assert not (cfg.images_dir("main") / a["id"]).exists()
    assert client.get(f"/api/items/{a['id']}").status_code == 404


def test_media_cannot_escape_the_images_folder(client, cfg):
    item = upload(client).json()
    for sneaky in ("/media/../settings.json", "/media/%2e%2e/settings.json", "/media/..%2fsettings.json",
                   f"/media/{item['id']}/../../settings.json"):
        r = client.get(sneaky)
        assert "update_mode" not in r.text and "window_key" not in r.text   # names in the settings file
        assert r.status_code == 404 or "<" in r.text  # a 404 or the page itself, never the settings file


def test_vocabulary_is_served_and_matches_the_tagger(client):
    assert client.get("/api/vocab").json()["category"] == vocab.CATEGORY
    from typing import get_args

    from closet.tagger import schema
    assert list(get_args(schema.Category)) == vocab.CATEGORY
    assert list(get_args(schema.Color)) == vocab.COLOR
    assert list(get_args(schema.Pattern)) == vocab.PATTERN
    assert list(get_args(schema.Formality)) == vocab.FORMALITY
    assert list(get_args(schema.Season)) == vocab.SEASON
    assert list(get_args(schema.Neck)) == vocab.SILHOUETTE["neck"]


def test_unbuilt_page_explains_itself_and_unknown_api_paths_are_404(client):
    assert "has not been built" in client.get("/").text
    assert client.get("/api/nothing-here").status_code == 404


def test_built_page_is_served_with_fallback_for_app_routes(services, tmp_path):
    from fastapi.testclient import TestClient

    from closet import app as app_module
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<html>closet app</html>")
    (web / "assets" / "a.js").write_text("console.log(1)")
    services.web_dir = web
    c = TestClient(app_module.create_app(services))
    assert "closet app" in c.get("/").text and "closet app" in c.get("/items/123").text
    js = c.get("/assets/a.js")
    assert js.text == "console.log(1)" and "immutable" in js.headers["cache-control"]
    assert c.get("/../settings.json").status_code in (200, 404) and "update_mode" not in c.get("/../settings.json").text


def test_database_is_migrated_and_a_newer_one_is_refused(cfg, tmp_path):
    import pytest
    path = tmp_path / "x" / "closet.db"
    first = db.migrate(path, tmp_path / "bk")
    assert first["applied"] == [v for v, _ in db.migration_files()] and first["applied"][0] == 1 and first["backup"] is None
    assert db.migrate(path, tmp_path / "bk")["applied"] == []
    conn = db.connect(path)
    conn.execute("PRAGMA user_version = 999")
    conn.close()
    with pytest.raises(db.NewerDatabaseError, match="newer version"):
        db.migrate(path, tmp_path / "bk")


def test_a_photo_damaged_in_its_header_is_refused_clearly(client):
    import random

    buf = io.BytesIO()
    Image.new("RGB", (20, 20), (1, 2, 3)).save(buf, "PNG")
    data = bytearray(buf.getvalue())
    random.seed(1)
    for _ in range(745):   # the 745th damaged copy is one Pillow refuses with a ValueError ("Truncated IHDR chunk")
        data = bytearray(buf.getvalue())
        for _ in range(3):
            data[random.randrange(8, 40)] = random.randrange(256)
    r = client.post("/api/items", files={"photo": ("x.png", bytes(data), "image/png")}, data={"client_key": "damaged"})
    assert r.status_code == 400 and "damaged" in r.json()["detail"]


def test_the_real_and_demo_closets_keep_their_own_copy_from_before_a_migration(tmp_path, monkeypatch):
    # both are migrated within the same second when the program starts after an upgrade
    main, demo = tmp_path / "closet.db", tmp_path / "demo" / "closet.db"
    for path in (main, demo):
        db.migrate(path, tmp_path / "bk")
    conn = db.connect(main)
    conn.execute("CREATE TABLE marker (x)")
    conn.commit()
    conn.close()
    n = db.latest_version()
    extra = tmp_path / f"{n + 1:04d}_more.sql"
    extra.write_text("CREATE TABLE more (id INTEGER PRIMARY KEY);")
    real = db.migration_files()
    monkeypatch.setattr(db, "migration_files", lambda: real + [(n + 1, extra)])
    monkeypatch.setattr(db.time, "strftime", lambda fmt: "20261117-090000")
    a = db.migrate(main, tmp_path / "bk", "main")["backup"]
    b = db.migrate(demo, tmp_path / "bk", "demo")["backup"]
    assert a != b and Path(a).exists() and Path(b).exists()
    kept = db.connect(Path(a))
    assert kept.execute("SELECT name FROM sqlite_master WHERE name = 'marker'").fetchone()   # still the real closet's
    kept.close()


def test_a_backup_copy_is_taken_before_an_existing_database_is_migrated(tmp_path, monkeypatch):
    path = tmp_path / "closet.db"
    db.migrate(path, tmp_path / "bk")
    extra = tmp_path / "migs"
    extra.mkdir()
    real = db.migration_files()
    n = db.latest_version()
    more, bad = extra / f"{n + 1:04d}_more.sql", extra / f"{n + 2:04d}_bad.sql"
    more.write_text("CREATE TABLE more (id INTEGER PRIMARY KEY);")
    monkeypatch.setattr(db, "migration_files", lambda: real + [(n + 1, more)])
    result = db.migrate(path, tmp_path / "bk")
    assert result["applied"] == [n + 1] and result["backup"] and list((tmp_path / "bk").glob(f"pre-migration-main-v{n}-*.sqlite"))
    from pathlib import Path
    assert Path(result["backup"]).exists()
    # a failing migration leaves the database at its old version
    bad.write_text("CREATE TABLE ok3 (id INTEGER); THIS IS NOT SQL;")
    monkeypatch.setattr(db, "migration_files", lambda: real + [(n + 1, more), (n + 2, bad)])
    import sqlite3

    import pytest
    with pytest.raises(sqlite3.Error):
        db.migrate(path, tmp_path / "bk")
    conn = db.connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == n + 1
    assert conn.execute("SELECT name FROM sqlite_master WHERE name = 'ok3'").fetchone() is None
    conn.close()
