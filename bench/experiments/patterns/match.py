import numpy as np, cv2

def subpix(r, i, j):
    """Parabolic refinement of a peak at (i, j) in a cyclic score map."""
    H, W = r.shape
    def f(a, b, c):
        d = a - 2 * b + c
        return 0.0 if d >= 0 else 0.5 * (a - c) / d
    return i + f(r[(i - 1) % H, j], r[i, j], r[(i + 1) % H, j]), j + f(r[i, (j - 1) % W], r[i, j], r[i, (j + 1) % W])

def local_offsets_match(sig, m, ref, P, Q, stride_frac=0.34, cover=0.9, size=1.0, margin=0.1):
    """Offsets by normalized matching of one repeat-sized piece against the reference tiled around it."""
    H, W = m.shape
    th, tw = int(Q * size), int(P * size)
    big = np.tile(ref, (int(np.ceil((th + Q) / Q)) + 1, int(np.ceil((tw + P) / P)) + 1)).astype(np.float32)
    big = big[:th + Q, :tw + P]
    sy, sx = max(2, int(Q * stride_frac)), max(2, int(P * stride_frac))
    ys = list(range(0, H - th, sy)); xs = list(range(0, W - tw, sx))
    off = np.full((len(ys), len(xs), 2), np.nan, np.float32); conf = np.zeros((len(ys), len(xs)), np.float32)
    for a, y0 in enumerate(ys):
        for b, x0 in enumerate(xs):
            wm = m[y0:y0 + th, x0:x0 + tw]
            if wm.mean() < cover:
                continue
            t = sig[y0:y0 + th, x0:x0 + tw]
            t = np.where(wm, t, t[wm].mean()).astype(np.float32)
            r = cv2.matchTemplate(big, t, cv2.TM_CCOEFF_NORMED)[:Q, :P]   # every cyclic shift once
            i, j = np.unravel_index(np.argmax(r), r.shape)
            # a near-tie with a match elsewhere (a soft or nearly symmetric plaid) says nothing: leave the area out
            far = r.copy()
            yy, xx = np.ogrid[:Q, :P]
            dy = np.minimum(np.abs(yy - i), Q - np.abs(yy - i)); dx = np.minimum(np.abs(xx - j), P - np.abs(xx - j))
            far[(dy <= max(2, Q // 10)) & (dx <= max(2, P // 10))] = -1
            if r[i, j] - far.max() < margin:
                continue
            fi, fj = subpix(r, i, j)
            # t(x) = ref(x + (fj, fi)) : the repeat's origin is at x0 - fj
            off[a, b] = ((x0 - fj) % P, (y0 - fi) % Q)
            conf[a, b] = r[i, j]
    return off, conf, (np.array(ys) + th / 2, np.array(xs) + tw / 2)
