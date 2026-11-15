"""Test 1: the measured solid, painted only in the colours the feature sheet names (draw/shoe-N.json)."""
import json, sys
import numpy as np, cv2
from PIL import Image
import shape as S
DRAW = S.W.parent / "draw"

def lab_of(hexes):
    rgb = np.uint8([[[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in hexes]])
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)[0]

def snap(col, pal):
    """Nearest named colour. Lightness counts for less between colours that have a hue (shade is not a new colour)."""
    d = []
    for p in pal:
        chroma = min(np.hypot(col[1] - 128, col[2] - 128), np.hypot(p[1] - 128, p[2] - 128))
        wl = 0.45 if chroma > 14 else 0.8
        d.append(np.sqrt((wl * (col[0] - p[0])) ** 2 + (col[1] - p[1]) ** 2 + (col[2] - p[2]) ** 2))
    return int(np.argmin(d))

def named_palette(hexes):
    pal = lab_of(hexes)
    def fn(imgs, masks):
        out = []
        ref = None
        for p, (im, m) in enumerate(zip(imgs, masks)):
            r, _ = S.panels(im, m)
            raw = cv2.cvtColor(cv2.medianBlur(im, 5), cv2.COLOR_RGB2LAB).astype(np.float32)
            mu, sd = raw[m].mean(0), raw[m].std(0) + 1e-3
            if p == 0: ref = (mu, sd)
            else: raw = (raw - mu) / sd * ref[1] + ref[0]        # bring this photo's light to the side photo's
            lut = np.zeros(r.max() + 1, np.uint8)
            for v in np.unique(r[m]):
                if v: lut[v] = snap(np.median(raw[(r == v) & m], axis=0), pal)
            li = lut[r]
            _, idx = cv2.distanceTransformWithLabels((~m).astype(np.uint8), cv2.DIST_L2, 3, labelType=cv2.DIST_LABEL_PIXEL)
            ys, xs = np.nonzero(m)
            l2 = np.zeros(idx.max() + 1, np.uint8); l2[idx[ys, xs]] = li[ys, xs]
            out.append(np.where(m, li, l2[idx]))
        rgb = np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in hexes], np.uint8)
        return rgb, out
    return fn

if __name__ == "__main__":
    pics = []
    for n in range(1, 6):
        f = DRAW / f"shoe-{n}.json"
        if not f.exists(): print(n, "no feature sheet yet"); continue
        sheet = json.loads(f.read_text())
        hexes = [p["hex"] for p in sheet["palette"]]
        S.palette = named_palette(hexes)
        sd = S.Solid(n)
        p = sd.picture(); p.save(S.W / f"named-{n}.png"); pics.append(p)
        sd.debug().save(S.W / f"named-debug-{n}.jpg", quality=85)
        print(n, sheet.get("kind"), hexes)
    if pics:
        sh = Image.new("RGB", (320 * len(pics), 320), "white")
        for k, p in enumerate(pics): sh.paste(p, (320 * k, 0))
        sh.save(S.W / "named-sheet.png")
