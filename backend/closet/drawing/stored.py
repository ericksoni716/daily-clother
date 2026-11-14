"""An item's pattern as measured from its photo and kept with the item, turned into a fill for the drawing.

The measuring is done by `closet.patterns` (which needs OpenCV) in the background; what it keeps is plain data
(JSON), with a plaid's or a print's tile as a small WebP image inside it. Turning that back into a
`Fill` needs neither OpenCV nor the photo, so drawing an item stays quick and the drawing code never imports
OpenCV.

The kept data (`items.pattern_fill`, version 1):
- {"kind": "stripes", "orientation": "horizontal" | "vertical", "bands": [[hex, fraction], ...],
   "trim_bands": [[hex, fraction], ...] | null, "sleeves_banded": true | false | null}
  bands run over the whole garment (fractions of its height or width, summing to 1); trim_bands are the plain
  ground a polo's collar and sleeves are cut from, when its stripes are placed.
- {"kind": "tile", "image": "<base64 WebP>", "width_frac": f, "length_frac": f | null,
   "phase": [u, v] | null, "phase_right": [u, v] | null}
  a repeat (a flattened plaid) or a whole-garment tile (a madras, a pieced print); with a phase it is lined up
  with the buttons, each front on its own (`fills.Swatch`).
- {"kind": "plain"}: the cloth itself is drawn in the item's colour (a graphic tee); kept for its graphic.
Any of these may carry a print lifted from the photo (a logo, a chest print), drawn over the cloth at its place:
  "graphic": {"image": "<base64 WebP with transparency>", "box": [x0, y0, x1, y1]}
  the box in fractions of the garment's width and height (its outline in the photo, sleeves included). Data
  without it reads as before, so the version stays 1.
"""
from __future__ import annotations

import base64
import io
import json
import re

from PIL import Image

from . import fills
from .illustrate import Fill

VERSION = 1
_HEX = re.compile(r"#[0-9a-fA-F]{6}")


def _bands(raw) -> list[tuple[str, float]] | None:
    if not isinstance(raw, list) or not raw:
        return None
    out = []
    for b in raw:
        if not (isinstance(b, (list, tuple)) and len(b) == 2 and isinstance(b[0], str) and _HEX.fullmatch(b[0])):
            return None
        f = float(b[1])
        if not (0 < f <= 1):
            return None
        out.append((b[0].lower(), f))
    return out


def _pair(raw) -> tuple[float, float] | None:
    if isinstance(raw, (list, tuple)) and len(raw) == 2:
        return float(raw[0]) % 1.0, float(raw[1]) % 1.0
    return None


MAX_IMAGE = 3_000_000   # bytes of base64: a whole-garment tile is a few hundred kB at most


def tile_text(img: Image.Image, quality: int = 88) -> str:
    """A tile as kept: WebP, base64."""
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "WEBP", quality=quality, method=4)
    return base64.b64encode(buf.getvalue()).decode()


def image_text(img: Image.Image, max_edge: int = 480, quality: int = 88) -> str:
    """A lifted graphic as kept: WebP with its transparency, base64, at most `max_edge` px on its longer side."""
    im = img.convert("RGBA")
    im.thumbnail((max_edge, max_edge), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=quality, method=4)
    return base64.b64encode(buf.getvalue()).decode()


def graphic_part(img: Image.Image, box) -> dict:
    """The kept `graphic` part for a print lifted from the photo, `box` in fractions of the garment."""
    return {"image": image_text(img), "box": [round(float(v), 4) for v in box]}


def graphic_from(data) -> fills.Graphic | None:
    """The graphic kept with an item (a dict or its JSON text), ready to draw, or None when there is none or it
    cannot be used (an older version, a damaged image, a box outside the garment)."""
    try:
        if isinstance(data, str):
            data = json.loads(data)
        if not isinstance(data, dict) or data.get("version") != VERSION:
            return None
        part = data.get("graphic")
        if not isinstance(part, dict):
            return None
        raw, box = part.get("image"), part.get("box")
        if not isinstance(raw, str) or len(raw) > MAX_IMAGE or not isinstance(box, list) or len(box) != 4:
            return None
        x0, y0, x1, y1 = (float(v) for v in box)
        if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
            return None
        with Image.open(io.BytesIO(base64.b64decode(raw, validate=True))) as im:
            im.load()
            img = im.convert("RGBA")
        return fills.Graphic(img, (x0 + x1) / 2, y0, x1 - x0, (0, 0, img.width, img.height))
    except (ValueError, TypeError, OSError, Image.DecompressionBombError):
        return None


def fill_from(data, base_color: str) -> Fill | None:
    """The fill for kept pattern data (a dict or its JSON text), or None when there is none or it cannot be used
    (an older version, a damaged tile): the item is then drawn in its colour."""
    try:
        if isinstance(data, str):
            data = json.loads(data)
        if not isinstance(data, dict) or data.get("version") != VERSION:
            return None
        if data.get("kind") == "stripes":
            bands = _bands(data.get("bands"))
            if bands is None or data.get("orientation") not in ("horizontal", "vertical"):
                return None
            trim = _bands(data.get("trim_bands"))
            way = data["orientation"]
            return Fill("stripes", bands[0][0], stripes=fills.Stripes(way, bands),
                        trim_stripes=fills.Stripes(way, trim) if trim else None,
                        sleeves_from_trim=data.get("sleeves_banded") is not True)
        if data.get("kind") == "tile":
            raw = data.get("image")
            if not isinstance(raw, str) or len(raw) > MAX_IMAGE:
                return None
            with Image.open(io.BytesIO(base64.b64decode(raw, validate=True))) as im:
                im.load()
                tile = im.convert("RGB")
            wf = float(data.get("width_frac") or 0)
            if not (0 < wf <= 2):
                return None
            lf = data.get("length_frac")
            sw = fills.Swatch(tile, wf, (0, 0, 0, 0), "measured", phase=_pair(data.get("phase")),
                              length_frac=float(lf) if lf else None, phase_right=_pair(data.get("phase_right")))
            return Fill("swatch", base_color, swatch=sw)
    except (ValueError, TypeError, OSError, Image.DecompressionBombError):
        return None
    return None
