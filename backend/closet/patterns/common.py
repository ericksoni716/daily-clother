"""Small pieces shared by the pattern measurements: the garment's mask, colour conversions, the one-channel
signal used for matching, and the repeat over the whole garment (2-D autocorrelation)."""
import cv2
import numpy as np
from numpy.fft import irfft2, rfft2


def quiet(s):
    """The default `log`: says nothing. Pass `print` (or the app's logger) to follow the steps."""


def garment_mask(cut, erode_frac=0.01, thresh=200):
    """The garment's pixels in a cutout, shrunk a little away from its edge."""
    a = np.asarray(cut)[..., 3]
    m = (a > thresh).astype(np.uint8)
    k = max(3, int(max(a.shape) * erode_frac) | 1)
    return cv2.erode(m, np.ones((k, k), np.uint8)).astype(bool)


def to_lab(rgb):
    """RGB (uint8) to OpenCV's 8-bit Lab, as float32."""
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)


def lab_to_rgb(tile_lab):
    """OpenCV's 8-bit Lab back to RGB (uint8)."""
    return cv2.cvtColor(np.clip(tile_lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)


def signal(lab):
    """One channel for matching: lightness plus the two colour axes, each scaled to its own spread."""
    out = np.zeros(lab.shape[:2], np.float32)
    for c in range(3):
        ch = lab[..., c]
        out += (ch - ch.mean()) / (ch.std() + 1e-3)
    return out


def soft(lab, m=None, grain=2.0, light=None):
    """One channel for matching soft, low-contrast cloth (a flannel in navy, black and grey). The three Lab
    channels are added as they are, so a channel that carries nothing but noise (the colour axes of a nearly
    colourless plaid) is not blown up to count as much as lightness, as `signal` does; the weave's grain is
    smoothed away over `grain` px; and with `light` (px) the slow change of light across the garment is taken
    out, measured over garment pixels only (`m`)."""
    s = np.zeros(lab.shape[:2], np.float32)
    for c in range(3):
        s += cv2.GaussianBlur(np.ascontiguousarray(lab[..., c], dtype=np.float32), (0, 0), grain)
    if light:
        w = np.ones(s.shape, np.float32) if m is None else m.astype(np.float32)
        if light > 300:      # so slow a change is the same seen small, and a blur this wide takes minutes at full size
            f = 60 / light
            small = (max(1, round(s.shape[1] * f)), max(1, round(s.shape[0] * f)))
            num = cv2.GaussianBlur(cv2.resize(s * w, small, interpolation=cv2.INTER_AREA), (0, 0), 60)
            den = cv2.GaussianBlur(cv2.resize(w, small, interpolation=cv2.INTER_AREA), (0, 0), 60)
            slow = cv2.resize(num / np.maximum(den, 1e-3), s.shape[::-1], interpolation=cv2.INTER_LINEAR)
            return s - slow
        s = s - cv2.GaussianBlur(s * w, (0, 0), light) / np.maximum(cv2.GaussianBlur(w, (0, 0), light), 1e-3)
    return s


def soft_tile(tile_lab, grain=2.0):
    """`soft` for one repeat: smoothed as the endless cloth it stands for (round its edges)."""
    k = int(np.ceil(3 * grain))
    wide = np.pad(tile_lab, ((k, k), (k, k), (0, 0)), mode="wrap")
    return soft(wide, grain=grain)[k:-k, k:-k]


def body_mask(alpha, shrink=0.02):
    """The garment from its alpha channel, shrunk by `shrink` of the image's size."""
    m = (alpha > 200).astype(np.uint8)
    k = max(3, int(max(alpha.shape) * shrink) | 1)
    return cv2.erode(m, np.ones((k, k), np.uint8)).astype(bool)


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


def best_tile(lab_img, m, px, py):
    """Tile origin whose repeat agrees most with its copies one repeat away (those that lie on the garment;
    at least two are needed). A pocket, the placket or a fold disagrees with its neighbours.
    Returns (error, x, y) or None."""
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
