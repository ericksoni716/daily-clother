"""Find a plaid's repeat over the whole garment body with 2-D autocorrelation, then pick the sample square
that best agrees with its neighbours one repeat away (a pocket, placket or fold does not)."""
import sys, numpy as np
from PIL import Image
from numpy.fft import rfft2, irfft2

def lab(rgb):
    import cv2shim as S
    return S.cvtColor(rgb, S.COLOR_RGB2LAB).astype(np.float32)

def body_mask(alpha, shrink=0.02):
    import cv2shim as S
    m = (alpha > 200).astype(np.uint8)
    k = max(3, int(max(alpha.shape) * shrink) | 1)
    return S.erode(m, np.ones((k, k), np.uint8)).astype(bool)

def autocorr(chan, m):
    """Masked, normalised autocorrelation (only overlapping garment pixels count)."""
    x = np.where(m, chan - chan[m].mean(), 0.0)
    H, W = x.shape
    s = (2 * H, 2 * W)
    num = irfft2(np.abs(rfft2(x, s)) ** 2, s)
    mm = m.astype(float)
    cnt = irfft2(np.abs(rfft2(mm, s)) ** 2, s)
    var = (x[m] ** 2).mean()
    with np.errstate(invalid="ignore", divide="ignore"):
        ac = num / np.maximum(cnt, 1) / var
    ac[cnt < 0.25 * m.sum()] = 0       # too little overlap to trust
    return ac, H, W

def find_period(L, m, lo=10):
    ac, H, W = autocorr(L, m)
    # best horizontal lag (dy=0) and vertical lag (dx=0); look for the first strong peak
    def first_peak(line, maxlag):
        best = None
        for lag in range(lo, maxlag):
            v = line[lag]
            if v > line[lag - 1] and v >= line[lag + 1] and v > 0.3:
                if best is None or v > best[1] + 0.05:
                    best = (lag, float(v))
        return best
    px = first_peak(ac[0, :W], W // 2)
    py = first_peak(ac[:H, 0], H // 2)
    return px, py, ac

def best_tile(lab_img, m, px, py):
    """Tile origin whose repeat agrees most with its copies one repeat away (those that lie on the garment;
    at least two are needed). A pocket, the placket or a fold disagrees with its neighbours."""
    H, W = m.shape
    best = None
    for y in range(0, H - py, 2):
        for x in range(0, W - px, 2):
            if not m[y:y + py, x:x + px].all():
                continue
            t = lab_img[y:y + py, x:x + px]
            errs = []
            for dy, dx in ((0, px), (0, -px), (py, 0), (-py, 0)):
                yy, xx = y + dy, x + dx
                if 0 <= yy and yy + py <= H and 0 <= xx and xx + px <= W and m[yy:yy + py, xx:xx + px].all():
                    errs.append(np.mean((t - lab_img[yy:yy + py, xx:xx + px]) ** 2))
            if len(errs) >= 2:
                err = float(np.mean(errs))
                if best is None or err < best[0]:
                    best = (err, x, y)
    return best


if __name__ == "__main__":
    sys.path.insert(0, ".")
    im = Image.open(sys.argv[1]).convert("RGBA")
    rgb = np.asarray(im.convert("RGB")); a = np.asarray(im)[..., 3]
    m = body_mask(a)
    L = lab(rgb)
    for c, name in ((0, "L"), (1, "a"), (2, "b")):
        px, py, _ = find_period(L[..., c], m)
        print(name, "period x", px, "y", py)
    px, py, _ = find_period(L[..., 0], m)
    if px and py:
        b = best_tile(L, m, px[0], py[0])
        print("best tile at", b)
        if b:
            err, x, y = b
            tile = rgb[y:y + py[0], x:x + px[0]]
            Image.fromarray(tile).save(sys.argv[2])
            big = np.tile(tile, (4, 4, 1))
            Image.fromarray(big).save(sys.argv[2].replace(".png", "-x4.png"))
