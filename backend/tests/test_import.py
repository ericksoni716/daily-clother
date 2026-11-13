"""Bulk import: a photo already in the closet is not added again."""
import hashlib

from closet import db

from .conftest import photo_bytes, upload

RED, BLUE = photo_bytes(color=(180, 60, 60)), photo_bytes(color=(20, 90, 160))


def count(client, status="active"):
    return len(client.get("/api/items", params={"status": status}).json()["items"])


def test_the_same_file_twice_makes_one_item(client):
    first = upload(client, RED, key="a")
    again = upload(client, RED, key="b")
    assert first.status_code == 201 and first.json()["duplicate"] is False
    assert again.status_code == 200 and again.json()["duplicate"] is True
    assert again.json()["id"] == first.json()["id"]
    assert count(client) == 1


def test_two_different_files_make_two_items(client):
    a, b = upload(client, RED, key="a"), upload(client, BLUE, key="b")
    assert (a.status_code, b.status_code) == (201, 201)
    assert not a.json()["duplicate"] and not b.json()["duplicate"] and a.json()["id"] != b.json()["id"]
    assert count(client) == 2


def test_a_retry_with_the_same_key_is_not_called_a_duplicate(client):
    first = upload(client, RED, key="a")
    again = upload(client, RED, key="a")
    assert again.status_code == 200 and again.json()["duplicate"] is False and again.json()["id"] == first.json()["id"]


def test_an_archived_item_still_counts(client):
    item = upload(client, RED, key="a").json()
    client.patch(f"/api/items/{item['id']}", json={"status": "archived"})
    again = upload(client, RED, key="b")
    assert again.status_code == 200 and again.json()["duplicate"] is True
    assert again.json()["id"] == item["id"] and again.json()["status"] == "archived"
    assert count(client) == 0 and count(client, "archived") == 1


def test_a_deleted_items_photo_can_be_added_again(client):
    item = upload(client, RED, key="a").json()
    assert client.delete(f"/api/items/{item['id']}").status_code == 204
    again = upload(client, RED, key="b")
    assert again.status_code == 201 and again.json()["duplicate"] is False and again.json()["id"] != item["id"]
    assert count(client) == 1


def test_the_hash_of_the_picked_file_is_used_when_the_browser_sends_it(client):
    # the browser shrinks the photo before sending, so what arrives can differ each time;
    # the hash of the file the owner picked is what decides
    picked = hashlib.sha256(b"the original file").hexdigest()
    first = client.post("/api/items", files={"photo": ("p.jpg", RED, "image/jpeg")},
                        data={"client_key": "a", "photo_sha256": picked})
    again = client.post("/api/items", files={"photo": ("p.jpg", BLUE, "image/jpeg")},
                        data={"client_key": "b", "photo_sha256": picked.upper()})
    assert first.status_code == 201 and again.status_code == 200 and again.json()["duplicate"] is True
    other = client.post("/api/items", files={"photo": ("p.jpg", RED, "image/jpeg")},
                        data={"client_key": "c", "photo_sha256": hashlib.sha256(b"another file").hexdigest()})
    assert other.status_code == 201
    assert count(client) == 2


def test_a_malformed_hash_is_refused(client):
    r = client.post("/api/items", files={"photo": ("p.jpg", RED, "image/jpeg")},
                    data={"client_key": "a", "photo_sha256": "not-a-hash"})
    assert r.status_code == 422 and "SHA-256" in r.json()["detail"]
    assert count(client) == 0


def test_adding_needs_login(anon):
    r = anon.post("/api/items", files={"photo": ("p.jpg", RED, "image/jpeg")}, data={"client_key": "a"})
    assert r.status_code == 401


def test_migration_0005_carries_over_the_hash_of_photos_already_in_the_closet(tmp_path, monkeypatch):
    path = tmp_path / "closet.db"
    real = db.migration_files()
    monkeypatch.setattr(db, "migration_files", lambda: [m for m in real if m[0] < 5])
    db.migrate(path, tmp_path / "bk")
    conn = db.connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
    conn.execute("INSERT INTO items (id, created_at, updated_at) VALUES ('i', 'now', 'now')")
    conn.execute("INSERT INTO photos (id, item_id, original_path, thumb_path, sha256, created_at) "
                 "VALUES ('p', 'i', 'a', 'b', 'abc', 'now')")
    conn.close()
    monkeypatch.setattr(db, "migration_files", lambda: real)
    assert 5 in db.migrate(path, tmp_path / "bk")["applied"]
    conn = db.connect(path)
    assert conn.execute("SELECT source_sha256 FROM photos WHERE id = 'p'").fetchone()[0] == "abc"
    conn.close()
