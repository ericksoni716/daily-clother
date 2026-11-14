"""Turning an uploaded photo into the files the closet keeps.

For each photo: the uncut picture at up to 1600px (so a bad cutout can be
redone), a thumbnail, and later the cutout and its thumbnail. All WebP.
The full-size upload itself is never written to disk.
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

try:  # HEIC from iPhones; optional so a missing library degrades to a clear message
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIC = True
except Exception:  # pragma: no cover - depends on the platform build
    HEIC = False

MAX_EDGE = 1600
THUMB_EDGE = 480
MAX_UPLOAD_BYTES = 60 * 1024 * 1024


class ImageError(ValueError):
    pass


@dataclass
class Stored:
    original_path: str
    thumb_path: str
    width: int
    height: int
    bytes: int
    sha256: str


def decode(data: bytes) -> Image.Image:
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImageError("That file is larger than 60 MB. Choose a smaller photo.")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except UnidentifiedImageError as e:
        hint = "" if HEIC else " HEIC photos are not supported on this computer."
        raise ImageError("That file is not a photo this app can read (JPEG, PNG, WebP or HEIC)." + hint) from e
    except (OSError, Image.DecompressionBombError) as e:
        raise ImageError("That photo could not be opened; it may be damaged.") from e
    img = ImageOps.exif_transpose(img)
    return img.convert("RGB")


def save_webp(img: Image.Image, path: Path, quality: int) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    img.save(tmp, "WEBP", quality=quality, method=4)
    tmp.replace(path)
    return path.stat().st_size


def thumbnail(img: Image.Image, edge: int = THUMB_EDGE) -> Image.Image:
    t = img.copy()
    t.thumbnail((edge, edge), Image.LANCZOS)
    return t


def store_upload(data: bytes, images_dir: Path, item_id: str, photo_id: str) -> Stored:
    return store_image(decode(data), images_dir, item_id, photo_id, hashlib.sha256(data).hexdigest())


def store_image(img: Image.Image, images_dir: Path, folder: str, photo_id: str, sha256: str | None = None) -> Stored:
    """Keep a photo (shrunk in place to at most MAX_EDGE) and its thumbnail in `folder`; `sha256` defaults to the
    kept file's."""
    img.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
    rel = f"{folder}/{photo_id}.webp"
    rel_thumb = f"{folder}/{photo_id}.t.webp"
    size = save_webp(img, images_dir / rel, 85)
    save_webp(thumbnail(img), images_dir / rel_thumb, 80)
    if sha256 is None:
        sha256 = hashlib.sha256((images_dir / rel).read_bytes()).hexdigest()
    return Stored(rel, rel_thumb, img.width, img.height, size, sha256)


def store_cutout(cutout: Image.Image, images_dir: Path, item_id: str, photo_id: str) -> tuple[str, str]:
    rel = f"{item_id}/{photo_id}.cut.webp"
    rel_thumb = f"{item_id}/{photo_id}.cut.t.webp"
    save_webp(cutout, images_dir / rel, 82)
    save_webp(thumbnail(cutout), images_dir / rel_thumb, 80)
    return rel, rel_thumb
