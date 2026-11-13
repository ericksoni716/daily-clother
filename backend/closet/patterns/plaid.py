"""Plaids: the repeat's size, where the flattened repeat sits on the garment (from Claude's landmarks, each
front on its own), and plaids with no regular repeat (madras)."""
import cv2
import numpy as np
from PIL import Image

from .common import autocorr, body_mask, lab_to_rgb, quiet, signal, to_lab
from .prints import lean
from .stripes import mask_of, straightened_sequence

PLACE_AT = 0.35   # where along the centre line, from neck to hem, the pattern is lined up


def period(cut):
    """The plaid's repeat (P across, Q down) in pixels, from the autocorrelation over the whole garment, or
    None when it does not clearly repeat both ways."""
    rgb = np.asarray(cut.convert("RGB"))
    m = body_mask(np.asarray(cut)[..., 3])
    lab = to_lab(rgb)
    ac = sum(autocorr(lab[..., c], m)[0] for c in range(3)) / 3
    H, W = m.shape

    def first(line, maxlag, lo=8):
        best = None
        for lag in range(lo, maxlag):
            v = line[lag]
            if v > line[lag - 1] and v >= line[lag + 1] and v > 0.3 and (best is None or v > best[1] + 0.05):
                best = (lag, float(v))
        return best
    px, py = first(ac[0, :W], W // 2), first(ac[:H, 0], H // 2)
    return (px[0], py[0]) if px and py else None


def placed_from_landmarks(info, P, Q, lm, photo_scale=1.0):
    """Where the repeat sits at the button line, PLACE_AT of the way from neck to hem, and the repeat's size as
    a fraction of the neck-to-hem length. `info` is from `flatten.rectify`; `lm` is Claude's landmarks
    (button_line, neck_center, hem_center) in the coordinates of the image Claude saw; photo_scale turns them
    into the cutout's. Returns ((u, v) as fractions of the repeat, length fraction, anchor (x, y))."""
    nx, ny = lm["neck_center"]["x"] * photo_scale, lm["neck_center"]["y"] * photo_scale
    hx, hy = lm["hem_center"]["x"] * photo_scale, lm["hem_center"]["y"] * photo_scale
    bl = [(b["x"] * photo_scale, b["y"] * photo_scale) for b in lm["button_line"]]
    ay = ny + PLACE_AT * (hy - ny)
    if len(bl) >= 2:   # buttons: the height is taken along the button run (steadier than neck and hem)
        ay = bl[0][1] + PLACE_AT * (bl[-1][1] - bl[0][1])
    if len(bl) >= 2:   # the button line's x at that height
        ys_, xs_ = np.array([b[1] for b in bl]), np.array([b[0] for b in bl])
        ax = float(np.polyval(np.polyfit(ys_, xs_, 1), ay))
    else:
        ax = nx + PLACE_AT * (hx - nx)
    ox, oy = info["ox"], info["oy"]
    iy, ix = int(round(ay)), int(round(ax))
    u = ((ax - ox[iy, ix]) % P) / P
    v = ((ay - oy[iy, ix]) % Q) / Q
    return (float(u), float(v)), P / (hy - ny), (ax, ay)


def check_placement(cut, tile_lab, info, P, Q, anchor, phase, side=+1):
    """Does the rebuilt repeat, at the measured placement, match the photo beside the button line? Compares one
    repeat of the photo (on one front, clear of the button strip) with the repeat shifted to every placement;
    returns the measured placement's rank (1 = best of all) and its match against the best."""
    rgb = np.asarray(cut.convert("RGB"))
    lab = to_lab(rgb)
    ax, ay = anchor
    x0 = int(ax + side * 0.15 * P) if side > 0 else int(ax - 0.15 * P - P)
    y0 = int(ay - Q / 2)
    patch = signal(lab[y0:y0 + Q, x0:x0 + P])
    t = cv2.resize(signal(tile_lab), (P, Q), interpolation=cv2.INTER_AREA)
    # the tile spot at the patch's top-left: phase is the anchor's spot; the patch starts (x0-ax, y0-ay) away
    u0 = int(round(phase[0] * P + (x0 - ax))) % P
    v0 = int(round(phase[1] * Q + (y0 - ay))) % Q
    scores = np.zeros((Q, P))
    pz = patch - patch.mean()
    for dv in range(Q):
        rolled = np.roll(t, -dv, 0)
        for du in range(P):
            w = np.roll(rolled, -du, 1)
            scores[dv, du] = (pz * (w - w.mean())).sum() / (np.sqrt((pz ** 2).sum() * ((w - w.mean()) ** 2).sum()) + 1e-6)
    mine = scores[v0, u0]
    rank = int((scores > mine).sum()) + 1
    by, bx = np.unravel_index(np.argmax(scores), scores.shape)
    off = (min(abs(bx - u0), P - abs(bx - u0)), min(abs(by - v0), Q - abs(by - v0)))
    return dict(rank=rank, of=P * Q, match=round(float(mine), 2), best=round(float(scores.max()), 2), off_px=off)


def _scores(lab, tile_sig, P, Q, x0, y0):
    """Match of the photo's repeat-sized patch at (x0, y0) against the repeat at every placement:
    r[dv, du] is how well the patch's top-left fits tile spot (du, dv). None when the patch leaves the photo."""
    patch = signal(lab[y0:y0 + Q, x0:x0 + P])
    if patch.shape != (Q, P):
        return None
    pz = patch - patch.mean()
    big = np.tile(tile_sig, (2, 2)).astype(np.float32)
    r = cv2.matchTemplate(big, pz.astype(np.float32), cv2.TM_CCOEFF_NORMED)[:Q, :P]
    return r


def match_front(cut, tile_lab, P, Q, anchor, side, offsets=(-1.0,), check=(0.5,)):
    """A front's placement by matching the photo beside the button line against the repeat directly: patches one
    repeat in size, just inside that front (side +1: right of the anchor, -1: left), at `offsets` repeats from
    the anchor height (the estimate), and at `check` (held out). Returns (phase at the anchor as fractions of the
    repeat, how far the held-out patch's own best is from it in px (across, down), the match score) or None."""
    rgb = np.asarray(cut.convert("RGB"))
    lab = to_lab(rgb)
    ax, ay = anchor
    x0 = int(ax + 0.15 * P) if side > 0 else int(ax - 0.15 * P - P)
    t = cv2.resize(signal(tile_lab), (P, Q), interpolation=cv2.INTER_AREA)

    def best(offs):
        acc = None
        for o in offs:
            y0 = int(ay + o * Q)
            r = _scores(lab, t, P, Q, x0, y0)
            if r is None:
                continue
            # shift so every score refers to the spot at the anchor itself
            r = np.roll(np.roll(r, int(round(-(x0 - ax))), 1), int(round(-(y0 - ay))), 0)
            acc = r if acc is None else acc + r
        if acc is None:
            return None
        v, u = np.unravel_index(np.argmax(acc), acc.shape)
        return u, v, float(acc.max() / len(offs))
    est, held = best(offsets), best(check)
    if est is None:
        return None
    u, v, sc = est
    off = None
    if held:
        off = (int(min(abs(held[0] - u), P - abs(held[0] - u))), int(min(abs(held[1] - v), Q - abs(held[1] - v))))
    return (u / P, v / Q), off, round(sc, 2)


def no_repeat(cut, log=quiet, lean_deg=None):
    """A plaid with no regular repeat (madras): both band sequences measured whole, straightened, and redrawn
    at their true positions across the garment. The fill is one tile the size of the garment.
    Returns dict(tile=RGB image array, width_frac=the tile's width as a fraction of the upright photo's)."""
    ang = lean(cut) if lean_deg is None else lean_deg
    up = cut.rotate(-ang, Image.BICUBIC, expand=True)
    rgb = np.asarray(up.convert("RGB"))
    lab = to_lab(rgb)
    m = mask_of(up)
    # wide strips each way, so the bands running the other way average out
    seq_d, y0, y1 = straightened_sequence(lab, m, strip_frac=0.25)
    seq_a, x0, x1 = straightened_sequence(lab.transpose(1, 0, 2), m.T, strip_frac=0.25)

    def fill(seq, a, b):
        d = seq[a:b + 1].copy()
        ok = ~np.isnan(d[:, 0])
        for c in range(3):
            d[:, c] = np.interp(np.arange(len(d)), np.where(ok)[0], d[ok, c])
        return d
    d, a = fill(seq_d, y0, y1), fill(seq_a, x0, x1)
    M = lab[m].mean(0)
    warp, weft = np.clip(2 * a - M, 0, 255), np.clip(2 * d - M, 0, 255)
    tile = (warp[None, :, :] + weft[:, None, :]) / 2
    log(f"  turned upright by {-ang:.1f} degrees; {len(a)} px across x {len(d)} px down, measured whole")
    return dict(tile=lab_to_rgb(tile.astype(np.float32)), width_frac=len(a) / up.width)
