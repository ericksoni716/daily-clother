import io

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


def test_media_needs_login_and_cannot_escape_the_images_folder(client, cfg):
    item = upload(client).json()
    for sneaky in ("/media/../settings.json", "/media/%2e%2e/settings.json", "/media/..%2fsettings.json",
                   f"/media/{item['id']}/../../settings.json"):
        r = client.get(sneaky)
        assert "sessions" not in r.text and "salt" not in r.text
        assert r.status_code == 404 or "<" in r.text  # a 404 or the page itself, never the settings file
    client.post("/api/logout")
    assert client.get(item["thumb_url"]).status_code == 401


def test_vocabulary_is_served_and_matches_the_tagger(client):
    assert client.get("/api/vocab").json()["category"] == vocab.CATEGORY
    from typing import get_args

    from closet.tagger import schema  # the bench's closet_bench.schema is this same module
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
    assert c.get("/../settings.json").status_code in (200, 404) and "passphrase" not in c.get("/../settings.json").text


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
    assert result["applied"] == [n + 1] and result["backup"] and (tmp_path / "bk").glob(f"pre-migration-v{n}-*.sqlite")
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
