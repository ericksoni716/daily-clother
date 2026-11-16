"""The login is checked before an upload is read, and no request is read past its limit (closet/gate.py)."""
import asyncio
import json

import pytest

from closet import limits

from .conftest import photo_bytes, photo_for, pile_bytes

BOUNDARY = "closetboundary"
FEW_KB = 4096


def form_head(filename="p.jpg") -> bytes:
    return (f"--{BOUNDARY}\r\nContent-Disposition: form-data; name=\"client_key\"\r\n\r\nk1\r\n"
            f"--{BOUNDARY}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"{filename}\"\r\n"
            "Content-Type: image/jpeg\r\n\r\n").encode()


def form_tail() -> bytes:
    return f"\r\n--{BOUNDARY}--\r\n".encode()


class Body:
    """A request body handed to the app chunk by chunk, as it would stream in; `read` counts what the app took."""

    def __init__(self, chunks):
        self.chunks = iter(chunks)
        self.read = 0

    async def receive(self):
        chunk = next(self.chunks, None)
        if chunk is None:
            return {"type": "http.request", "body": b"", "more_body": False}
        self.read += len(chunk)
        return {"type": "http.request", "body": chunk, "more_body": True}


def endless_photo(total: int, chunk: int = 1024):
    """A multipart upload whose photo goes on for `total` bytes (finite, so the old code ends instead of hanging)."""
    yield form_head()
    for _ in range(total // chunk):
        yield b"\xff" * chunk
    yield form_tail()


def send(app, path, body: Body, cookie=None, length=None, content_type=f"multipart/form-data; boundary={BOUNDARY}"):
    """Calls the app directly (no test client buffering the body first). Returns (status, answer)."""
    headers = [(b"content-type", content_type.encode())]
    if cookie:
        headers.append((b"cookie", cookie.encode()))
    if length is not None:
        headers.append((b"content-length", str(length).encode()))
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "scheme": "http",
             "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "", "headers": headers,
             "client": ("127.0.0.1", 50000), "server": ("127.0.0.1", 8000)}
    out = {"status": None, "body": b""}

    async def reply(message):
        if message["type"] == "http.response.start":
            out["status"] = message["status"]
        elif message["type"] == "http.response.body":
            out["body"] += message.get("body", b"")

    asyncio.run(app(scope, body.receive, reply))
    return out["status"], json.loads(out["body"] or b"null")


def session_cookie(client) -> str:
    return "; ".join(f"{k}={v}" for k, v in client.cookies.items())


def kept(cfg):
    """Every file in the closet's data folder other than the databases and the program's own state."""
    return sorted(p.relative_to(cfg.data_dir).as_posix() for p in cfg.data_dir.rglob("*")
                  if p.is_file() and not p.name.endswith((".db", ".db-wal", ".db-shm", ".db-journal", ".json")))


@pytest.mark.parametrize("path", ["/api/items", "/api/sources"])
def test_an_upload_without_the_login_is_refused_before_its_body_is_read(anon, path):
    anon.post("/api/setup", json={"passphrase": "correct horse battery"})
    anon.cookies.clear()
    body = Body(endless_photo(2 * limits.MB))
    status, answer = send(anon.app, path, body)
    assert status == 401 and answer["detail"] == "Log in to continue."
    assert body.read <= FEW_KB


def test_an_upload_before_setup_is_refused_before_its_body_is_read(anon, cfg):
    body = Body(endless_photo(2 * limits.MB))
    status, answer = send(anon.app, "/api/items", body, length=2 * limits.MB)
    assert status == 401 and answer["detail"] == "Set a passphrase to get started."
    assert body.read == 0 and kept(cfg) == []


def test_a_wrong_session_is_refused_before_its_body_is_read(client):
    body = Body(endless_photo(2 * limits.MB))
    status, _ = send(client.app, "/api/items", body, cookie="closet_session=not-a-session")
    assert status == 401 and body.read <= FEW_KB


@pytest.mark.parametrize("path", ["/api/items", "/api/sources", "/api/would-this-work", "/api/items/x/photos",
                                  "/api/items/x/photo"])
def test_an_upload_too_large_is_refused_while_it_streams_in(client, cfg, monkeypatch, path):
    monkeypatch.setattr(limits, "UPLOAD_BYTES", 64 * 1024)
    before = kept(cfg)
    body = Body(endless_photo(2 * limits.MB))
    status, answer = send(client.app, path, body, cookie=session_cookie(client))
    assert status == 413 and "too large" in answer["detail"] and "Choose a smaller photo." in answer["detail"]
    assert body.read <= 64 * 1024 + 1024   # stopped at the chunk that went past the limit
    assert kept(cfg) == before
    assert client.get("/api/items").json()["items"] == [] and client.get("/api/sources").json()["sources"] == []


def test_a_length_over_the_limit_is_refused_before_anything_is_read(client, cfg, monkeypatch):
    monkeypatch.setattr(limits, "UPLOAD_BYTES", 64 * 1024)
    body = Body(endless_photo(2 * limits.MB))
    status, answer = send(client.app, "/api/items", body, cookie=session_cookie(client), length=2 * limits.MB)
    assert status == 413 and "too large" in answer["detail"]
    assert body.read == 0 and kept(cfg) == []


def test_the_test_client_gets_413_for_a_photo_over_the_limit(client, cfg, monkeypatch):
    monkeypatch.setattr(limits, "UPLOAD_BYTES", 64 * 1024)
    big = photo_bytes(fmt="PNG", size=(800, 800)) + b"\0" * (128 * 1024)
    r = client.post("/api/items", files={"photo": ("p.png", big, "image/png")}, data={"client_key": "big"})
    assert r.status_code == 413 and "too large" in r.json()["detail"]
    assert kept(cfg) == [] and client.get("/api/items").json()["items"] == []


def test_a_large_json_body_is_refused_even_without_the_login(anon):
    body = Body([b'{"passphrase": "' + b"x" * (2 * limits.MB) + b'"}'])
    status, answer = send(anon.app, "/api/login", body, content_type="application/json")
    assert status == 413 and answer["detail"] == "That is more than Closet reads in one request. Try again with less."


def test_a_photo_under_the_limit_still_goes_in_without_a_length(client):
    photo = photo_for("streamed")
    chunks = [form_head()] + [photo[i:i + 1000] for i in range(0, len(photo), 1000)] + [form_tail()]
    status, item = send(client.app, "/api/items", Body(chunks), cookie=session_cookie(client))
    assert status == 201 and item["has_photo"]


def test_several_photos_and_a_photo_of_several_pieces_still_go_in(client):
    for key in ("a", "b", "c"):
        r = client.post("/api/items", files={"photo": ("p.jpg", photo_for(key), "image/jpeg")}, data={"client_key": key})
        assert r.status_code == 201
    r = client.post("/api/sources", files={"photo": ("pile.png", pile_bytes(), "image/png")}, data={"client_key": "pile"})
    assert r.status_code == 201
    assert len(client.get("/api/items").json()["items"]) == 3


def test_every_call_that_takes_a_photo_may_send_a_whole_photo(client):
    """Each route with an uploaded file gets the photo's limit, not the 1 MB of any other request: another photo of a
    shoe and a retake were once left at 1 MB, so a phone's photo was refused there."""
    import inspect
    import re

    from fastapi.routing import APIRoute

    found = []
    for route in client.app.routes:
        if not isinstance(route, APIRoute):
            continue
        takes = any("UploadFile" in str(p.annotation) for p in inspect.signature(route.endpoint).parameters.values())
        if takes:
            path = re.sub(r"\{[^}]+\}", "x", route.path)
            for method in route.methods:
                found.append((method, path))
                assert limits.limit_for(method, path) == limits.UPLOAD_BYTES, (method, route.path)
    assert ("POST", "/api/items/x/photos") in found and ("POST", "/api/items/x/photo") in found
    assert limits.limit_for("POST", "/api/shoes/check") == limits.BODY_BYTES   # Add's instant check is gone
    # and nothing else is let through as a photo
    assert limits.limit_for("PUT", "/api/items/x/photos/y/view") == limits.BODY_BYTES
    assert limits.limit_for("DELETE", "/api/items/x/photos/y") == limits.BODY_BYTES
    assert limits.limit_for("POST", "/api/items/x/correct") == limits.BODY_BYTES


def test_a_phone_sized_photo_goes_in_as_another_photo_of_a_shoe(client):
    """Add sends a shoe's second to sixth photos to the shoe's own route: a phone's photo must go in there too."""
    item = client.post("/api/items", files={"photo": ("p.jpg", photo_for("shoe"), "image/jpeg")},
                       data={"client_key": "shoe", "shoe": "true"}).json()
    big = photo_bytes(fmt="PNG", size=(800, 800)) + b"\0" * (2 * limits.MB)   # over the 1 MB of other requests
    assert len(big) > limits.BODY_BYTES
    r = client.post(f"/api/items/{item['id']}/photos", files={"photo": ("p.png", big, "image/png")})
    assert r.status_code == 201, r.text
    assert len(r.json()["photos"]) == 2
