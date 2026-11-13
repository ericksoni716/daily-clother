"""The OpenCV calls closet/drawing/fills.py makes, done with numpy and Pillow only.

Loaded as `cv2` so fills.py runs unchanged; any difference in its results comes from these primitives.
Border handling follows OpenCV's defaults (BORDER_REFLECT_101 for filters; erode/dilate treat the outside as
neutral; distanceTransform treats the outside as non-zero).
"""
import numpy as np
from PIL import Image, ImageFilter

# ---- constants the code reads
COLOR_RGB2LAB, COLOR_LAB2RGB, COLOR_RGB2GRAY = "rgb2lab", "lab2rgb", "rgb2gray"
TERM_CRITERIA_EPS, TERM_CRITERIA_MAX_ITER = 2, 1
KMEANS_PP_CENTERS = 2
DIST_C = 3
INTER_AREA, INTER_NEAREST, INTER_LINEAR = "area", "nearest", "linear"
CV_32F = 5
CC_STAT_AREA = 4
_seed = [0]


def setRNGSeed(s):
    _seed[0] = int(s)


# ---- colour (OpenCV's 8-bit Lab: L*255/100, a+128, b+128, D65)
_M = np.array([[0.412453, 0.357580, 0.180423], [0.212671, 0.715160, 0.072169], [0.019334, 0.119193, 0.950227]])
_WHITE = np.array([0.950456, 1.0, 1.088754])


def _srgb_to_linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb(c):
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.power(np.clip(c, 0, None), 1 / 2.4) - 0.055)


def _f(t):
    return np.where(t > 0.008856, np.cbrt(t), 7.787 * t + 16 / 116)


def _finv(t):
    return np.where(t > 0.206893, t ** 3, (t - 16 / 116) / 7.787)


def cvtColor(src, code):
    a = np.asarray(src)
    if code == COLOR_RGB2GRAY:
        g = a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114
        return np.clip(np.round(g), 0, 255).astype(np.uint8) if a.dtype == np.uint8 else g.astype(a.dtype)
    if code == COLOR_RGB2LAB:
        rgb = a.astype(np.float64) / 255.0
        xyz = _srgb_to_linear(rgb) @ _M.T / _WHITE
        fx, fy, fz = _f(xyz[..., 0]), _f(xyz[..., 1]), _f(xyz[..., 2])
        L = np.where(xyz[..., 1] > 0.008856, 116 * fy - 16, 903.3 * xyz[..., 1])
        lab = np.stack([L * 255 / 100, 500 * (fx - fy) + 128, 200 * (fy - fz) + 128], -1)
        return np.clip(np.round(lab), 0, 255).astype(np.uint8)
    if code == COLOR_LAB2RGB:
        lab = a.astype(np.float64)
        L, A, B = lab[..., 0] * 100 / 255, lab[..., 1] - 128, lab[..., 2] - 128
        fy = (L + 16) / 116
        xyz = np.stack([_finv(fy + A / 500), _finv(fy), _finv(fy - B / 200)], -1) * _WHITE
        rgb = _linear_to_srgb(xyz @ np.linalg.inv(_M).T)
        return np.clip(np.round(rgb * 255), 0, 255).astype(np.uint8)
    raise NotImplementedError(code)


# ---- filters
def _pad101(a, py, px):
    return np.pad(a, ((py, py), (px, px)) + ((0, 0),) * (a.ndim - 2), mode="reflect")


def blur(src, ksize):
    """Normalised box filter, BORDER_REFLECT_101, via summed-area table."""
    a = np.asarray(src, np.float64)
    kx, ky = ksize
    px, py = kx // 2, ky // 2
    p = _pad101(a, py, px)
    c = np.cumsum(np.cumsum(p, 0), 1)
    c = np.pad(c, ((1, 0), (1, 0)) + ((0, 0),) * (a.ndim - 2))
    h, w = a.shape[:2]
    s = c[ky:ky + h, kx:kx + w] - c[:h, kx:kx + w] - c[ky:ky + h, :w] + c[:h, :w]
    return (s / (kx * ky)).astype(np.float32 if a.dtype != np.uint8 else np.float32)


def _gauss_kernel(sigma, depth_u8):
    n = int(round(sigma * (3 if depth_u8 else 4) * 2 + 1)) | 1
    x = np.arange(n) - n // 2
    k = np.exp(-(x ** 2) / (2 * sigma * sigma))
    return k / k.sum()


def _conv1d(a, k, axis):
    """Convolve along `axis` with BORDER_REFLECT_101, through the FFT for long kernels."""
    r = len(k) // 2
    a = np.moveaxis(a, axis, -1)
    n = a.shape[-1]
    if r >= n:  # reflect padding wider than the signal: build it by repeated reflection
        idx = np.arange(-r, n + r)
        period = 2 * (n - 1) if n > 1 else 1
        idx = np.abs(idx) % period
        idx = np.where(idx >= n, period - idx, idx)
        p = a[..., idx]
    else:
        p = np.concatenate([a[..., r:0:-1], a, a[..., -2:-r - 2:-1]], -1)
    m = p.shape[-1] + len(k) - 1
    out = np.fft.irfft(np.fft.rfft(p, m) * np.fft.rfft(k, m), m)[..., 2 * r: 2 * r + n]
    return np.moveaxis(out, -1, axis)


def GaussianBlur(src, ksize, sigma):
    a = np.asarray(src, np.float64)
    k = _gauss_kernel(sigma, np.asarray(src).dtype == np.uint8)
    out = _conv1d(_conv1d(a, k, 0), k, 1) if a.shape[0] > 1 else _conv1d(a, k, 1)
    return out.astype(np.float32)


def _slide(a, k, axis, op, pad_value):
    """Running min/max of width k (k odd) along axis, the outside filled with pad_value."""
    r = k // 2
    pad = [(0, 0)] * a.ndim
    pad[axis] = (r, r)
    p = np.pad(a, pad, constant_values=pad_value)
    out = np.take(p, range(0, a.shape[axis]), axis=axis).copy()
    # van Herk / Gil-Werman would be O(n); doubling widths is O(n log k) and simple
    width, cur = 1, p.copy()
    widths = []
    while width * 2 <= k:
        n = cur.shape[axis] - width
        cur = op(np.take(cur, range(0, n), axis=axis), np.take(cur, range(width, width + n), axis=axis))
        width *= 2
        widths.append(width)
    # cur now holds windows of `width`; combine two overlapping windows to cover k
    n = a.shape[axis]
    first = np.take(cur, range(0, n), axis=axis)
    second = np.take(cur, range(k - width, k - width + n), axis=axis)
    return op(first, second)


def erode(src, kernel):
    a = np.asarray(src)
    kh, kw = np.asarray(kernel).shape
    hi = np.iinfo(a.dtype).max if a.dtype.kind in "ui" else np.inf
    return _slide(_slide(a, kh, 0, np.minimum, hi), kw, 1, np.minimum, hi)


def dilate(src, kernel):
    a = np.asarray(src)
    kh, kw = np.asarray(kernel).shape
    return _slide(_slide(a, kh, 0, np.maximum, 0), kw, 1, np.maximum, 0)


def distanceTransform(src, dist_type, mask_size):
    """Chessboard distance to the nearest zero pixel (the outside counts as non-zero), exactly:
    a pixel has distance >= d when the (2d-1)-wide square around it is all non-zero."""
    a = (np.asarray(src) > 0).astype(np.uint8)
    dist = np.zeros(a.shape, np.float32)
    lo, hi = 0, max(a.shape)
    # largest d with any pixel at distance >= d
    def at_least(d):
        return erode(a, np.ones((2 * d - 1, 2 * d - 1), np.uint8)) if d > 0 else a
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if at_least(mid).any():
            lo = mid
        else:
            hi = mid - 1
    # fill exact values with a cheap chamfer: repeated 3x3 erosion from the top level down is exact for L-inf
    cur = a.copy()
    d = 0
    while cur.any() and d < lo:
        d += 1
        dist[cur > 0] = d
        cur = erode(cur, np.ones((3, 3), np.uint8))
    return dist


def medianBlur(src, ksize):
    return np.asarray(Image.fromarray(np.asarray(src)).filter(ImageFilter.MedianFilter(ksize)))


def resize(src, dsize, interpolation=INTER_LINEAR):
    a = np.asarray(src)
    w, h = dsize
    mode = {INTER_AREA: Image.BOX, INTER_NEAREST: Image.NEAREST, INTER_LINEAR: Image.BILINEAR}[interpolation]
    if a.dtype == np.float32:
        return np.asarray(Image.fromarray(a, "F").resize((w, h), mode), np.float32)
    return np.asarray(Image.fromarray(a).resize((w, h), mode))


def Sobel(src, ddepth, dx, dy):
    a = np.asarray(src, np.float64)
    smooth, diff = np.array([1, 2, 1.0]), np.array([-1, 0, 1.0])
    kx, ky = (diff, smooth) if dx else (smooth, diff)

    def corr(arr, k, axis):
        arr = np.moveaxis(arr, axis, -1)
        p = np.concatenate([arr[..., 1:2], arr, arr[..., -2:-1]], -1)
        out = k[0] * p[..., :-2] + k[1] * p[..., 1:-1] + k[2] * p[..., 2:]
        return np.moveaxis(out, -1, axis)
    return corr(corr(a, kx, 1), ky, 0).astype(np.float32)


def connectedComponentsWithStats(src):
    """8-connected components by runs: label runs row by row and join runs that touch."""
    a = np.asarray(src) > 0
    h, w = a.shape
    parent = [0]

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    runs_prev, runs_all = [], []
    for y in range(h):
        row = a[y]
        d = np.diff(np.concatenate([[0], row.astype(np.int8), [0]]))
        starts, ends = np.where(d == 1)[0], np.where(d == -1)[0]
        cur = []
        j = 0
        for s, e in zip(starts, ends):
            lab = len(parent)
            parent.append(lab)
            while j < len(runs_prev) and runs_prev[j][1] < s:   # previous runs ending before s-1 cannot touch
                j += 1
            k = j
            while k < len(runs_prev) and runs_prev[k][0] <= e:  # touches if prev.start <= e and prev.end >= s-1
                ra, rb = find(lab), find(runs_prev[k][2])
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)
                k += 1
            cur.append((s, e, lab))
            runs_all.append((y, s, e, lab))
        runs_prev = cur
    roots = {}
    labels = np.zeros((h, w), np.int32)
    for y, s, e, lab in runs_all:
        r = find(lab)
        if r not in roots:
            roots[r] = len(roots) + 1
        labels[y, s:e] = roots[r]
    n = len(roots) + 1
    stats = np.zeros((n, 5), np.int32)
    stats[0] = [0, 0, w, h, int((labels == 0).sum())]
    for i in range(1, n):
        ys, xs = np.where(labels == i)
        stats[i] = [xs.min(), ys.min(), xs.max() - xs.min() + 1, ys.max() - ys.min() + 1, len(xs)]
    return n, labels, stats, None


def kmeans(data, K, bestLabels, criteria, attempts, flags):
    """k-means++ start, Lloyd iterations, best of `attempts` by compactness."""
    x = np.asarray(data, np.float64)
    _, max_iter, eps = criteria
    rng = np.random.default_rng(_seed[0])
    best = None
    for _ in range(attempts):
        c = [x[rng.integers(len(x))]]
        for _k in range(1, K):
            d2 = np.min(((x[:, None] - np.array(c)[None]) ** 2).sum(-1), 1)
            c.append(x[rng.choice(len(x), p=d2 / d2.sum())] if d2.sum() > 0 else x[rng.integers(len(x))])
        c = np.array(c)
        for _it in range(max_iter):
            lab = np.argmin(((x[:, None] - c[None]) ** 2).sum(-1), 1)
            new = np.array([x[lab == j].mean(0) if (lab == j).any() else c[j] for j in range(K)])
            moved = np.sqrt(((new - c) ** 2).sum(-1)).max()
            c = new
            if moved <= eps:
                break
        lab = np.argmin(((x[:, None] - c[None]) ** 2).sum(-1), 1)
        comp = ((x - c[lab]) ** 2).sum()
        if best is None or comp < best[0]:
            best = (comp, lab, c)
    return best[0], best[1].reshape(-1, 1).astype(np.int32), best[2].astype(np.float32)
