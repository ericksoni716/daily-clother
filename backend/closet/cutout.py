"""Background removal by calling ONNX models directly (no `rembg` package).

The model file comes from the rembg release assets and is downloaded into the
data folder by `modelstore`, never bundled with the program.
"""
from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


@dataclass(frozen=True)
class ModelSpec:
    name: str
    url: str
    sha256: str
    size: int  # square input edge
    mean: tuple[float, float, float]
    std: tuple[float, float, float]


_BASE = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/"
MODELS = {
    "u2net": ModelSpec(
        "u2net", _BASE + "u2net.onnx",
        "8d10d2f3bb75ae3b6d527c77944fc5e7dcd94b29809d47a739a7a728a912b491",
        320, (0.485, 0.456, 0.406), (0.229, 0.224, 0.225)),
    "isnet-general-use": ModelSpec(
        "isnet-general-use", _BASE + "isnet-general-use.onnx",
        "60920e99c45464f2ba57bee2ad08c919a52bbf852739e96947fbb4358c0d964a",
        1024, (0.5, 0.5, 0.5), (1.0, 1.0, 1.0)),
}

_sessions: dict[str, object] = {}
_sessions_lock = threading.Lock()  # the cutout worker and a "Would this work?" check both make cutouts


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _session(name: str, model_path: Path):
    key = f"{name}:{model_path}"
    with _sessions_lock:   # one session per model, made once; running it from two threads is safe in onnxruntime
        if key not in _sessions:
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 2  # leave the machine usable while a queue of photos is processed
            _sessions[key] = ort.InferenceSession(str(model_path), sess_options=opts,
                                                  providers=["CPUExecutionProvider"])
        return _sessions[key]


def predict_mask(img: Image.Image, model: str, model_path: Path) -> Image.Image:
    """Return a soft foreground mask (mode L) the same size as `img`."""
    spec = MODELS[model]
    rgb = img.convert("RGB").resize((spec.size, spec.size), Image.LANCZOS)
    arr = np.asarray(rgb, dtype=np.float32)
    arr = arr / max(float(arr.max()), 1e-6)
    arr = (arr - np.array(spec.mean, dtype=np.float32)) / np.array(spec.std, dtype=np.float32)
    inp = arr.transpose(2, 0, 1)[None]
    sess = _session(model, model_path)
    out = sess.run(None, {sess.get_inputs()[0].name: inp})[0]
    pred = out[0, 0]
    lo, hi = float(pred.min()), float(pred.max())
    pred = (pred - lo) / max(hi - lo, 1e-6)
    mask = Image.fromarray((pred * 255).astype(np.uint8), "L")
    return mask.resize(img.size, Image.LANCZOS)


def make_cutout(img: Image.Image, mask: Image.Image, pad: float = 0.04) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """Apply the mask, crop to the garment with a little padding.

    Returns the RGBA cutout and the crop box in the photo's coordinates.
    """
    m = np.asarray(mask)
    ys, xs = np.where(m > 128)
    if len(xs) == 0:
        raise ValueError("mask is empty")
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    px, py = int((x1 - x0) * pad), int((y1 - y0) * pad)
    box = (max(0, x0 - px), max(0, y0 - py), min(img.width, x1 + px), min(img.height, y1 + py))
    rgba = img.convert("RGBA")
    rgba.putalpha(mask.filter(ImageFilter.GaussianBlur(0.6)))
    return rgba.crop(box), box
