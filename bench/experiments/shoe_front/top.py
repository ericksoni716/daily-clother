"""Top-down photos: cut out, one shoe of a pair, turned toe up, cropped. Saved as RGBA crops + a contact sheet."""
from common import *
import cv2
from PIL import ImageDraw
OUT = WORK / "top"; OUT.mkdir(parents=True, exist_ok=True)
VIEW = {k: "TOPP" for k in SHOES}
def norm(key, which=0):
    img = Image.open(PHOTOS / key / f"{VIEW[key]}.jpg").convert("RGB")
    soft = np.asarray(CUT[0][1](img))
    mask = (soft > 127).astype(np.uint8)
    n, lab, stats, cent = cv2.connectedComponentsWithStats(mask)
    comps = sorted(range(1, n), key=lambda i: -stats[i, cv2.CC_STAT_AREA])
    big = [i for i in comps if stats[i, cv2.CC_STAT_AREA] > 0.35 * stats[comps[0], cv2.CC_STAT_AREA]]
    big.sort(key=lambda i: cent[i][0])
    pick = big[min(which, len(big) - 1)]
    m = (lab == pick).astype(np.uint8)
    ys, xs = np.nonzero(m)
    pts = np.stack([xs, ys], 1).astype(np.float32)
    mean, vecs = cv2.PCACompute(pts, mean=None)[:2]
    ang = np.degrees(np.arctan2(vecs[0][1], vecs[0][0]))   # long axis
    rgb = np.asarray(img)
    h, w = m.shape
    R = cv2.getRotationMatrix2D((float(mean[0][0]), float(mean[0][1])), ang - 90, 1.0)   # long axis to vertical
    big_wh = (w * 2, h * 2); R[0, 2] += w / 2; R[1, 2] += h / 2
    rr = cv2.warpAffine(rgb, R, big_wh, flags=cv2.INTER_LINEAR, borderValue=(255, 255, 255))
    mm = cv2.warpAffine(m, R, big_wh, flags=cv2.INTER_NEAREST)
    ys, xs = np.nonzero(mm)
    rr, mm = rr[ys.min():ys.max() + 1, xs.min():xs.max() + 1], mm[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    return rr, mm, len(big)
if __name__ == "__main__":
    tiles = []
    for k in SHOES:
        if not (PHOTOS / k / "TOPP.jpg").exists(): continue
        rr, mm, n = norm(k)
        im = Image.fromarray(np.dstack([rr, mm * 255]))
        im.save(OUT / f"{k}.png")
        tiles.append((k, n, im))
    S = 260
    sh = Image.new("RGB", (len(tiles) * 130, S + 20), "#dddddd"); d = ImageDraw.Draw(sh)
    for i, (k, n, im) in enumerate(tiles):
        t = im.copy(); t.thumbnail((120, S)); sh.paste(t, (i * 130 + 5, 20), t); d.text((i * 130 + 5, 4), f"{k[:12]} {n}", fill="black")
    sh.save(OUT / "_contact.png"); print(sh.size)
