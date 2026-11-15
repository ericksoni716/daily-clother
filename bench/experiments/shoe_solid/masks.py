"""Cut every photo out with the app's own model; keep the masks beside the scripts' work folder."""
import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps
REPO = Path("/home/user/daily-clother")
sys.path.insert(0, str(REPO / "backend"))
from closet import cutout as C
import photos as P
W = Path(__file__).resolve().parent.parent / "hull-work"; W.mkdir(exist_ok=True)
MODEL = REPO / "bench/models/isnet-general-use.onnx"

def load(n, v, side=1200):
    im = ImageOps.exif_transpose(Image.open(P.path(n, v))).convert("RGB")
    im.thumbnail((side, side))
    return im

def mask(n, v):
    f = W / f"mask-{n}-{v}.png"
    if f.exists(): return np.array(Image.open(f)) > 127
    im = load(n, v)
    m = C.predict_mask(im, "isnet-general-use", MODEL).resize(im.size)
    m.save(f)
    return np.array(m) > 127

if __name__ == "__main__":
    T = 300
    sheet = Image.new("RGB", (T * 5, T * 5), "white")
    for r, n in enumerate(P.SHOES):
        for c, v in enumerate(P.VIEWS):
            im = load(n, v); m = mask(n, v)
            a = np.array(im).astype(float)
            a[~m] = a[~m] * 0.25 + np.array([255, 0, 255]) * 0.75
            t = Image.fromarray(a.astype("uint8")); t.thumbnail((T, T))
            sheet.paste(t, (c * T + (T - t.width) // 2, r * T + (T - t.height) // 2))
    sheet.save(W / "masks-sheet.jpg", quality=85)
