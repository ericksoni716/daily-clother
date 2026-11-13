import io
import zlib

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from closet import app as app_module
from closet.config import Config

PASSPHRASE = "correct horse battery"


def photo_bytes(fmt="JPEG", size=(900, 1200), color=(180, 60, 60)) -> bytes:
    im = Image.new("RGB", size, (240, 240, 235))
    ImageDraw.Draw(im).rectangle((size[0] // 4, size[1] // 6, size[0] * 3 // 4, size[1] * 5 // 6), fill=color)
    buf = io.BytesIO()
    im.save(buf, fmt)
    return buf.getvalue()


def fake_cutter(img: Image.Image) -> Image.Image:
    """Stands in for the model: keeps the middle of the photo."""
    w, h = img.size
    out = img.convert("RGBA").crop((w // 4, h // 6, w * 3 // 4, h * 5 // 6))
    return out


@pytest.fixture
def cfg(tmp_path):
    return Config(data_dir=tmp_path / "Closet", auto_download_model=False)


@pytest.fixture
def services(cfg):
    sv = app_module.build_services(cfg, cutter=fake_cutter, web_dir=None)  # independent of whether the page is built
    yield sv
    sv.stop()


@pytest.fixture
def anon(services):
    return TestClient(app_module.create_app(services))


@pytest.fixture
def client(anon):
    assert anon.post("/api/setup", json={"passphrase": PASSPHRASE}).status_code == 204
    return anon


def photo_for(key: str) -> bytes:
    """A photo of its own for each upload key: the closet refuses a photo it already has, so tests that
    need several items must send several photos. The same key gives the same photo, as a retry would."""
    h = zlib.crc32(key.encode())
    return photo_bytes(color=(40 + h % 180, 40 + (h >> 8) % 180, 40 + (h >> 16) % 180))


def upload(client, data=None, key="k1", name=None):
    fields = {"client_key": key}
    if name:
        fields["name"] = name
    return client.post("/api/items", files={"photo": ("p.jpg", data or photo_for(key), "image/jpeg")}, data=fields)
