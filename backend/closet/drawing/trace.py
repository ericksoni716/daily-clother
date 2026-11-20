"""Tracing a side-on photo of one shoe into the flat drawing style (#192).

Moved here from the bench (`closet_bench.trace_shoes`, which imports it) so the app and the bench share one
copy, as `templates`, `illustrate` and `fills` are shared. The steps:

1. Cut the shoe out (the app's background removal, or OpenCV's GrabCut), and clean the cut-out.
2. Turn it so it lies the way the templates draw a shoe: sole level, toe to the left.
3. Trace it: the silhouette, colour regions in the shoe's measured colours, the sole as its own region, specks
   removed and curves smoothed, drawn with the app's outline weight.
4. Score the trace, and check the photo against a quality gate made of measured signals (`GATE`), so that the
   app can fall back to its template drawing on its own when a photo is too poor to trace.

OpenCV is imported only inside the functions that read a photo, so importing this module (and drawing a shoe
from its stored data) needs no OpenCV.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from .frontshoe import LENGTH
from .illustrate import CARD, INK, luminance, shade

WORK = 480            # the shoe's longer side, in px, while it is traced and scored
PAD = 0.06            # background kept round the shoe, as a share of its longer side
MERGE_DE = 10.0       # two colours closer than this (CIE76 ΔE) are one colour of the shoe
SHADE_L = 25.0        # a colour and the same colour this much darker or lighter are one colour, in light and shade
SPECK = 0.0015        # a patch smaller than this share of the shoe is a speck and joins its neighbour
SOLE_MAX = 0.35       # the sole is at most this share of the shoe's height
CORNER = 60.0         # a traced outline turning more sharply than this (degrees) keeps a corner there
REFINE_PX = 900       # the cut-out's edge is refined on the shoe's crop at most this size
FRAME_NEAR = 0.035    # a cut-out this close to the photo's frame (a share of its width or height) may run into it ...
FRAME_DE = 6.0        # a pixel on the frame this far in colour from the background is the shoe meeting the frame
CONTACT_TOL = 0.012   # outline points this close to the ground line (a share of the shoe's size) rest on it
MARK_DE = 22.0        # a mark differs from the cloth round it by more than this
OUTLINE_W, INNER_W = 3.8, 1.5   # style B, the app's: a bold outer edge, inner lines about a third of it
CARD_W, CARD_H = 400, 460       # the drawing's card, as the templates draw it
SHOE_X0, SHOE_L, SHOE_G = 40.0, 320.0, 330.0   # the templates' toe x, toe-to-heel length and ground y


@dataclass(frozen=True)
class Approach:
    name: str
    label: str
    prefilter: str            # none | meanshift | bilateral
    colors: int               # the most colours the upper is quantised to (close ones are then merged)
    smooth: float             # contour simplification, as a share of the shoe's longer side
    blur: float               # how strongly region edges are smoothed before tracing (px at WORK)
    sp: int = 0               # mean-shift spatial radius
    sr: int = 0               # mean-shift colour radius


# The one way the app traces. The bench tries five others beside it (`closet_bench.trace_shoes.APPROACHES`).
APPROACH = Approach("bilateral-5", "bilateral filter, then 5 colours", "bilateral", 5, 0.003, 1.2)

# The quality gate: signal -> (limit, "below" or "above" fails, the reason in plain words)
GATE = {
    "found": (0.5, "below", "no shoe was found in the photo"),
    "size_px": (250.0, "below", "the shoe is too small in the photo"),
    "sharpness": (0.08, "below", "the photo is blurred"),
    "contrast_de": (6.0, "below", "the shoe hardly stands out from the background"),
    "clipped": (0.35, "above", "too much of the shoe is pure white or pure black (over- or under-exposed)"),
    "edge_touch": (0.03, "above", "the shoe runs off the edge of the photo"),
    "second_piece": (0.15, "above", "there is more than one thing in the photo (two shoes, or a hand)"),
    "solidity": (0.80, "below", "the outline is broken up: something covers the shoe, or background got into the cut-out"),
    "aspect": (0.9, "below", "not side-on: the shoe is taller than it is long"),
    "sole_lift": (0.035, "above", "not side-on: the sole does not rest on its heel and its ball"),
    "toe_heel": (0.06, "below", "toe and heel look alike: probably taken from the front, back or top"),
    "trace_iou": (0.9, "below", "even the best trace strays from the cut-out"),
}

# What the tagger said about the photo (`details.shoes_in_photo` and `details.shoe_view` of its answer), when it
# was asked: the main check for a pair and for the view. Each value here turns the photo down, in plain words.
TOLD = {
    ("shoes_in_photo", "pair"): "two shoes: Claude sees both shoes of a pair in the photo",
    ("shoes_in_photo", "more"): "more than one shoe: Claude sees several shoes in the photo",
    ("shoe_view", "front"): "not side-on: Claude sees the shoe from the front",
    ("shoe_view", "back"): "not side-on: Claude sees the shoe from the back",
    ("shoe_view", "top"): "not side-on: Claude sees the shoe from above",
    ("shoe_view", "angled"): "not side-on: Claude sees the shoe at an angle",
}

# Signals that only advise: recorded and shown, never a reason to turn a photo down. On the owner's 30 photos
# the outline's shape did not tell a pair from one shoe (lug soles, heel tabs, collars and shadows give the same
# readings), so a pair is turned down only on unambiguous evidence: two pieces apart (`second_piece`), or the
# tagger saying so (`TOLD`).
ADVICE = {
    "second_sole": (0.85, "above", "maybe two shoes: something like a second sole shows beyond one end"),
    "second_top": (0.65, "above", "maybe two shoes: something like a second top edge runs inside the outline"),
}


# ------------------------------------------------------------------ colour

def to_lab(rgb: np.ndarray) -> np.ndarray:
    """uint8 RGB -> float Lab (L 0..100)."""
    import cv2
    return cv2.cvtColor(rgb.astype(np.float32) / 255.0, cv2.COLOR_RGB2Lab)


def lab_hex(lab) -> str:
    import cv2
    rgb = cv2.cvtColor(np.asarray(lab, np.float32).reshape(1, 1, 3), cv2.COLOR_Lab2RGB)[0, 0]
    r, g, b = (int(round(float(np.clip(v, 0, 1)) * 255)) for v in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def delta_e(a, b) -> float:
    return float(np.linalg.norm(np.asarray(a, np.float64) - np.asarray(b, np.float64)))


# ------------------------------------------------------------------ cut-out

def grabcut_mask(img: Image.Image) -> np.ndarray:
    """A foreground mask (uint8 0/255, the photo's size) from GrabCut started on the whole photo but a thin border."""
    import cv2
    rgb = np.asarray(img.convert("RGB"))
    s = min(1.0, 640 / max(rgb.shape[:2]))
    small = cv2.resize(rgb, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else rgb.copy()
    h, w = small.shape[:2]
    mx, my = max(2, int(w * 0.03)), max(2, int(h * 0.03))
    m = np.zeros((h, w), np.uint8)
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.setRNGSeed(0)
    bgr = cv2.cvtColor(small, cv2.COLOR_RGB2BGR)
    cv2.grabCut(bgr, m, (mx, my, w - 2 * mx, h - 2 * my), bgd, fgd, 6, cv2.GC_INIT_WITH_RECT)
    fg = np.isin(m, (cv2.GC_FGD, cv2.GC_PR_FGD))
    # a shadow on the ground is the background's colour, only darker: offer it back to the background and let
    # GrabCut decide again (a grey shoe's own pixels stay, since they are in its model of the shoe)
    lab = to_lab(small)
    border = np.concatenate([lab[:my].reshape(-1, 3), lab[-my:].reshape(-1, 3), lab[:, :mx].reshape(-1, 3),
                             lab[:, -mx:].reshape(-1, 3)])
    ground = np.median(border, axis=0)
    darker = ground[0] - lab[..., 0]
    shadow = fg & (np.linalg.norm(lab[..., 1:] - ground[1:], axis=-1) < 7) & (darker > 4) & (darker < 55)
    if shadow.any():
        m[shadow] = cv2.GC_PR_BGD
        cv2.grabCut(bgr, m, None, bgd, fgd, 4, cv2.GC_INIT_WITH_MASK)
        fg = np.isin(m, (cv2.GC_FGD, cv2.GC_PR_FGD))
    fg = fg.astype(np.uint8) * 255
    return cv2.resize(fg, (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_LINEAR)


def clean_mask(soft: np.ndarray) -> tuple[np.ndarray, float]:
    """The largest piece of the mask (0/1) with its small holes filled, and the second piece's size against it."""
    import cv2
    m = (soft > 127).astype(np.uint8)
    n, cc, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    if n <= 1:
        return np.zeros_like(m), 0.0
    areas = stats[1:, cv2.CC_STAT_AREA]
    order = np.argsort(areas)[::-1]
    second = float(areas[order[1]] / areas[order[0]]) if len(order) > 1 else 0.0
    m = (cc == order[0] + 1).astype(np.uint8)
    holes = (1 - m).astype(np.uint8)
    hn, hcc, hstats, _ = cv2.connectedComponentsWithStats(holes, connectivity=4)
    limit = 0.01 * m.sum()
    for j in range(1, hn):
        x, y, w, h, a = hstats[j]
        inside = x > 0 and y > 0 and x + w < m.shape[1] and y + h < m.shape[0]
        if inside and a < limit:
            m[hcc == j] = 1
    return m, second


def _disk(r: int) -> np.ndarray:
    import cv2
    r = max(1, int(r))
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def refine_mask(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """The cut-out's edge made to follow the photo: GrabCut run again in a narrow band round the edge (inside it
    the shoe, outside it the background, for certain), then notches and spikes narrower than about 1% of the
    shoe smoothed away. Where a white shoe on a white ground leaked into the background, the band pulls it back.
    A refinement that moves the edge a long way is not trusted: the cut-out is then only smoothed."""
    import cv2
    ys, xs = np.nonzero(mask)
    size = max(xs.max() - xs.min() + 1, ys.max() - ys.min() + 1)
    margin = int(0.08 * size) + 4
    H, W = mask.shape
    x0, y0, x1, y1 = max(0, xs.min() - margin), max(0, ys.min() - margin), min(W, xs.max() + 1 + margin), min(H, ys.max() + 1 + margin)
    crop, m = rgb[y0:y1, x0:x1], mask[y0:y1, x0:x1]
    s = min(1.0, REFINE_PX / max(crop.shape[:2]))
    if s < 1:
        crop = cv2.resize(crop, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        m = (cv2.resize(m.astype(np.float32), (crop.shape[1], crop.shape[0]), interpolation=cv2.INTER_AREA) > 0.5).astype(np.uint8)
    r = max(2, int(round(0.012 * size * s)))
    gc = np.full(m.shape, cv2.GC_BGD, np.uint8)
    gc[cv2.dilate(m, _disk(r)) > 0] = cv2.GC_PR_BGD
    gc[m > 0] = cv2.GC_PR_FGD
    gc[cv2.erode(m, _disk(r)) > 0] = cv2.GC_FGD
    smooth = _disk(max(1, int(round(0.006 * size * s))))
    out = m
    if (gc == cv2.GC_FGD).any() and (gc == cv2.GC_BGD).any():
        bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
        cv2.setRNGSeed(0)
        cv2.grabCut(np.ascontiguousarray(crop[..., ::-1]), gc, None, bgd, fgd, 3, cv2.GC_INIT_WITH_MASK)
        fg = np.isin(gc, (cv2.GC_FGD, cv2.GC_PR_FGD)).astype(np.uint8)
        if (fg & m).sum() / max((fg | m).sum(), 1) >= 0.9:
            out = fg
    out = cv2.morphologyEx(cv2.morphologyEx(out, cv2.MORPH_CLOSE, smooth), cv2.MORPH_OPEN, smooth)
    if s < 1:
        out = (cv2.resize(out.astype(np.float32), (x1 - x0, y1 - y0), interpolation=cv2.INTER_LINEAR) > 0.5).astype(np.uint8)
    full = np.zeros_like(mask)
    full[y0:y1, x0:x1] = out
    refined, _ = clean_mask(full * 255)
    return refined if refined.sum() > 0 else mask


# ------------------------------------------------------------------ orientation

def _rotate(arr: np.ndarray, angle: float, border: int, interp: int | None = None) -> np.ndarray:
    import cv2
    interp = cv2.INTER_LINEAR if interp is None else interp
    h, w = arr.shape[:2]
    rot = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    cos, sin = abs(rot[0, 0]), abs(rot[0, 1])
    nw, nh = int(h * sin + w * cos) + 1, int(h * cos + w * sin) + 1
    rot[0, 2] += nw / 2 - w / 2
    rot[1, 2] += nh / 2 - h / 2
    return cv2.warpAffine(arr, rot, (nw, nh), flags=interp, borderMode=border)


def ground_edge(mask: np.ndarray) -> tuple[float, float]:
    """The ground line: the line under the shoe that the most of its sole rests on. Each edge of the convex hull
    that faces down (within 50 degrees) is a candidate; the one with the outline's lowest points (within
    CONTACT_TOL of it) spread furthest along it wins, so a sole that rests on its heel and its ball, with toe
    spring and a curved outsole between, is levelled on those two. Returns its angle in degrees (image
    coordinates) and that spread in px."""
    import cv2
    cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(cs, key=cv2.contourArea)
    pts = c[:, 0, :].astype(np.float64)
    hull = cv2.convexHull(c)[:, 0, :].astype(np.float64)
    centre = hull.mean(axis=0)
    tol = CONTACT_TOL * float(max(np.ptp(pts[:, 0]), np.ptp(pts[:, 1]), 1.0))
    best, angle = (0.0, 0.0), 0.0
    for i in range(len(hull)):
        p, q = hull[i], hull[(i + 1) % len(hull)]
        e = q - p
        length = float(np.hypot(*e))
        if length < 1:
            continue
        d = e / length
        n = np.array([d[1], -d[0]])
        if np.dot(n, (p + q) / 2 - centre) < 0:
            n = -n
        if n[1] <= np.cos(np.radians(50)):
            continue
        along = pts[(pts - p) @ n > -tol] @ d
        key = (float(along.max() - along.min()), length)
        if key > best:
            best = key
            angle = float(np.degrees(np.arctan2(e[1], e[0])))
            if angle > 90:
                angle -= 180
            elif angle <= -90:
                angle += 180
    return angle, best[0]


def _columns(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """For each column of a mask: whether the shoe is in it, its top row and its bottom row (exclusive)."""
    h = mask.shape[0]
    present = mask.any(axis=0)
    top = np.where(present, mask.argmax(axis=0), h)
    bottom = np.where(present, h - mask[::-1].argmax(axis=0), 0)
    return present, top, bottom


def sole_lift(mask: np.ndarray) -> float:
    """How far the sole's lowest point at the heel (the back 30% of the length) or at the ball (55 to 85% from
    the heel) stays above the ground, as a share of the length; the toe end may lift (toe spring) and the outsole
    may curve between them. The mask is level, toe to the left."""
    present, _, bottom = _columns(mask)
    xs = np.nonzero(present)[0]
    if len(xs) < 4:
        return 1.0
    x0, x1 = xs[0], xs[-1] + 1
    length = x1 - x0
    u = (x1 - 1 - xs) / max(length - 1, 1)
    b = bottom[xs].astype(np.float64)
    ground = b.max()
    heel, ball = b[u <= 0.3], b[(u >= 0.55) & (u <= 0.85)]
    if not len(heel) or not len(ball):
        return 1.0
    return float(max(ground - heel.max(), ground - ball.max()) / length)


@dataclass
class Oriented:
    rgb: np.ndarray           # the shoe, sole level and toe to the left, with a little background round it (WORK scale)
    mask: np.ndarray          # 0/1, the same size
    angle: float              # how far the photo was turned (degrees)
    flipped: bool             # whether it was mirrored to put the toe on the left
    toe_heel: float           # how clearly the toe end is lower than the heel end (0 = alike)
    lift: float               # how far the heel or the ball stays off the ground, as a share of the length
    aspect: float             # length / height
    full_rgb: np.ndarray | None = field(default=None, repr=False)    # the same crop at the photo's own resolution
    full_mask: np.ndarray | None = field(default=None, repr=False)


def orient(rgb: np.ndarray, mask: np.ndarray) -> Oriented:
    import cv2
    angle, _ = ground_edge(mask)
    if abs(angle) > 0.3:
        rgb = _rotate(rgb, angle, cv2.BORDER_REPLICATE)
        mask = (_rotate(mask * 255, angle, cv2.BORDER_CONSTANT) > 127).astype(np.uint8)
        mask, _ = clean_mask(mask * 255)
    ys, xs = np.nonzero(mask)
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    w, h = x1 - x0, y1 - y0
    # the toe end of a side view is lower than the heel end
    present, top, bottom = _columns(mask[y0:y1, x0:x1])
    heights = np.where(present, bottom - top, 0).astype(np.float64)
    q = max(1, w // 4)
    left, right = heights[:q].mean(), heights[-q:].mean()
    toe_heel = abs(left - right) / max(left, right, 1.0)
    flipped = bool(left > right)
    pad = int(round(PAD * max(w, h)))
    H, W = mask.shape
    cx0, cy0, cx1, cy1 = max(0, x0 - pad), max(0, y0 - pad), min(W, x1 + pad), min(H, y1 + pad)
    rgb, mask = rgb[cy0:cy1, cx0:cx1], mask[cy0:cy1, cx0:cx1]
    if flipped:
        rgb, mask = rgb[:, ::-1], mask[:, ::-1]
    full_rgb, full_mask = np.ascontiguousarray(rgb), np.ascontiguousarray(mask)
    s = WORK / max(w, h)
    size = (max(1, int(round(rgb.shape[1] * s))), max(1, int(round(rgb.shape[0] * s))))
    rgb = cv2.resize(full_rgb, size, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
    mask = (cv2.resize(full_mask * 255, size, interpolation=cv2.INTER_LINEAR) > 127).astype(np.uint8)
    return Oriented(rgb, mask, angle, flipped, float(toe_heel), sole_lift(mask), float(w / max(h, 1)), full_rgb, full_mask)


def second_sole(mask: np.ndarray) -> tuple[float, tuple[int, int] | None]:
    """A second sole: two shoes side by side, the far one shifted along and standing higher in the photo, show
    the far shoe's sole beyond one end of the near one: going in from that end, the bottom line runs along
    raised above the ground, then steps down onto the near shoe's sole. One shoe's ends are convex (its sole
    curves down gradually from the toe or the heel), and a lug sole's steps are shallower than the limit. The
    step is looked for within 17% of the length from each end (5 cm on the reference shoe): further in, a step
    is more likely a shadow cut out with the shoe than a second shoe.
    Returns the step in cm, scaled to the reference shoe (the smaller of how high the raised run is and how
    far it drops), and where the step is (x, y). The mask is level, toe to the left."""
    present, _, bottom = _columns(mask)
    xs = np.nonzero(present)[0]
    if xs.size < 20:
        return 0.0, None
    x0, x1 = int(xs[0]), int(xs[-1]) + 1
    cm = LENGTH / (x1 - x0)
    ground = bottom[x0:x1].max()
    b = np.where(present[x0:x1], (ground - bottom[x0:x1]) * cm, 0.0)
    run, drop, after = max(2, round(0.8 / cm)), max(1, round(1.0 / cm)), max(1, round(2.0 / cm))
    best, where = 0.0, None
    for flip in (False, True):        # in from the toe, then in from the heel
        e = b[::-1] if flip else b
        for i in range(run + drop, int(0.17 * e.size) + drop):
            raised = e[i - drop - run:i - drop + 1]
            # the raised run is nearly level, and the step down from it is far steeper (a toe spring is the
            # other way round: it rises faster towards the tip)
            if np.ptp(raised) > 0.5 or e[i - drop] - e[i] < max(0.6, 3 * np.ptp(raised)):
                continue
            v = min(raised.min(), e[:i - drop + 1].min(), e[i - drop] - e[i:i + after].min())
            if v > best:
                x = x1 - 1 - (i - drop) if flip else x0 + i - drop
                best, where = float(v), (int(x), int(ground - round(e[i - drop] / cm)))
    return best, where


EDGE_DE = 3.0    # the colour change (ΔE) that counts as an edge inside the upper
ALIKE_DE = 15.0  # ... between colours this alike


def second_top(rgb: np.ndarray, mask: np.ndarray) -> tuple[float, int | None]:
    """A second top line: two shoes side by side, the far one standing higher in the photo, show the near
    shoe's top edge inside the pair's outline, running along below the outline's top at a steady depth, from
    near the heel to near the toe. One shoe's seams (a collar's padding, an eyestay, a toe cap) each follow a
    part of the top line, at different depths. Returns the share of the length (6 to 94% from the heel) along
    which an edge runs at one depth (0.8 to 4.5 cm below the top, give or take 0.5 cm), and that depth in px.
    The mask is level, toe to the left."""
    import cv2
    present, top, bottom = _columns(mask)
    xs = np.nonzero(present)[0]
    if xs.size < 20:
        return 0.0, None
    x0, x1 = int(xs[0]), int(xs[-1]) + 1
    px = (x1 - x0) / LENGTH                      # px per cm
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32) * np.array([100 / 255, 1, 1], np.float32)
    cols = np.arange(x0 + round(0.06 * (x1 - x0)), x0 + round(0.94 * (x1 - x0)))
    depth = np.arange(round(4.5 * px) + 3)
    ys = top[cols][None, :] + depth[:, None]
    keep = ys < (bottom[cols] - 3.2 * px)[None, :]           # above the sole
    ys = ys.clip(0, mask.shape[0] - 1)
    band = lab[ys, cols[None, :]]                            # the upper, straightened along its top line
    band = cv2.GaussianBlur(band, (0, 0), sigmaX=0.5 * px, sigmaY=0.5)
    up, down = np.zeros(band.shape[:2], np.float32), np.zeros(band.shape[:2], np.float32)
    up[2:] = np.linalg.norm(band[2:] - band[:-2], axis=-1)
    down[:-2] = up[2:]
    # an edge between two alike colours: a top edge over the same upper behind it, or a highlight along it;
    # not a seam between two panels of different colours
    off = max(3, round(0.3 * px))
    alike = np.zeros(band.shape[:2], bool)
    alike[off:-off] = np.linalg.norm(band[2 * off:] - band[:-2 * off], axis=-1) <= ALIKE_DE
    edge = (np.maximum(up, down) >= EDGE_DE) & alike & keep & np.roll(keep, -off, axis=0)
    edge[:round(0.8 * px)] = False
    # the path through the straightened band that meets the most edge, its depth changing by at most 1 px every
    # cm along (the far shoe may sit shifted along the near one, so the gap between the top lines changes)
    every = max(1, round(1.0 * px))
    score = edge[:, 0].astype(np.float32)
    for j in range(1, edge.shape[1]):
        if j % every == 0:
            score = np.maximum(score, np.maximum(np.r_[score[1:], 0], np.r_[0, score[:-1]]))
        score = score + edge[:, j]
    at = int(score.argmax())
    return float(score[at] / edge.shape[1]), at


# ------------------------------------------------------------------ tracing

@dataclass
class Region:
    color: str
    lab: np.ndarray
    part: str                                  # silhouette | upper | sole
    paths: list[list[np.ndarray]]              # each path: an outer contour and its holes (float px at WORK)


@dataclass
class Trace:
    approach: Approach
    regions: list[Region]                      # in paint order; regions[0] is the silhouette in the main colour
    shape: tuple[int, int]                     # the working image's (height, width)

    @property
    def colors(self) -> int:
        return len({r.color for r in self.regions})

    @property
    def paths(self) -> int:
        return sum(len(r.paths) for r in self.regions)


def prefilter(rgb: np.ndarray, mask: np.ndarray, a: Approach) -> np.ndarray:
    import cv2
    if a.prefilter == "none":
        return rgb
    fill = rgb.copy()
    fill[mask == 0] = np.median(rgb[mask > 0], axis=0).astype(np.uint8)
    bgr = cv2.cvtColor(fill, cv2.COLOR_RGB2BGR)
    if a.prefilter == "meanshift":
        bgr = cv2.pyrMeanShiftFiltering(bgr, a.sp, a.sr)
    else:
        for _ in range(3):
            bgr = cv2.bilateralFilter(bgr, 9, 30, 7)
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def same_but_shaded(a, b) -> bool:
    """Whether two Lab colours are one colour in light and in shade: the same hue, a similar share of colour,
    and lighter or darker by no more than SHADE_L (two greys of the same family count too)."""
    if abs(a[0] - b[0]) > SHADE_L:
        return False
    ca, cb = float(np.hypot(a[1], a[2])), float(np.hypot(b[1], b[2]))
    if max(ca, cb) < 8:
        return True
    if min(ca, cb) < 8 or min(ca, cb) / max(ca, cb) < 0.55:
        return False
    cos = (a[1] * b[1] + a[2] * b[2]) / (ca * cb)
    return float(np.degrees(np.arccos(np.clip(cos, -1, 1)))) < 12


def quantise(feat: np.ndarray, real: np.ndarray, k: int, shades: bool = True) -> tuple[np.ndarray, list[np.ndarray]]:
    """k-means on `feat` (N x 3 Lab); then clusters closer than MERGE_DE merged and, with `shades`, a colour and
    the same colour in shade. Returns labels and each cluster's real colour (from `real`, the unfiltered photo):
    for a colour seen in light and in shade, the lit end, as the template drawing does (PHASE0.md, finding 2)."""
    import cv2
    k = max(1, min(k, len(feat)))
    cv2.setRNGSeed(0)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    _, labels, _ = cv2.kmeans(feat.astype(np.float32), k, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    labels = labels.ravel()
    first = labels.copy()

    def merge(close) -> None:
        while True:
            ids = list(np.unique(labels))
            cols = {i: real[labels == i].mean(axis=0) for i in ids}
            pair, best = None, np.inf
            for ai, i in enumerate(ids):
                for j in ids[ai + 1:]:
                    d = delta_e(cols[i], cols[j])
                    if d < best and close(cols[i], cols[j]):
                        pair, best = (i, j), d
            if pair is None:
                return
            labels[labels == pair[1]] = pair[0]

    merge(lambda a, b: delta_e(a, b) < MERGE_DE)
    if shades:
        merge(same_but_shaded)
    ids = list(np.unique(labels))
    remap = np.zeros(int(labels.max()) + 1, np.int32)
    for n, i in enumerate(ids):
        remap[i] = n
    labels = remap[labels]
    colors = []
    for n in range(len(ids)):
        sel = labels == n
        # the clusters k-means found inside this colour that hold at least a fifth of it; the lightest is the lit end
        big = [real[sel & (first == f)].mean(axis=0) for f in np.unique(first[sel]) if (sel & (first == f)).sum() >= 0.2 * sel.sum()]
        colors.append(max(big, key=lambda c: c[0]) if len(big) > 1 else real[sel].mean(axis=0))
    return labels, colors


def smooth_labels(lmap: np.ndarray, region: np.ndarray, n: int, sigma: float) -> np.ndarray:
    """A mode filter: each pixel of `region` takes the label most present round it (Gaussian-weighted)."""
    import cv2
    if sigma <= 0 or n <= 1:
        return lmap
    stack = np.stack([cv2.GaussianBlur((lmap == i).astype(np.float32), (0, 0), sigma) for i in range(n)])
    out = lmap.copy()
    out[region > 0] = stack.argmax(axis=0)[region > 0]
    return out


def remove_specks(lmap: np.ndarray, region: np.ndarray, min_area: int) -> np.ndarray:
    """Patches smaller than `min_area` take the label most common round their edge."""
    import cv2
    kernel = np.ones((3, 3), np.uint8)
    for _ in range(4):
        changed = False
        for i in np.unique(lmap[region > 0]):
            n, cc, stats, _ = cv2.connectedComponentsWithStats(((lmap == i) & (region > 0)).astype(np.uint8), connectivity=8)
            for j in range(1, n):
                x, y, w, h, a = stats[j]
                if a >= min_area:
                    continue
                x0, y0 = max(0, x - 2), max(0, y - 2)
                x1, y1 = min(lmap.shape[1], x + w + 2), min(lmap.shape[0], y + h + 2)
                comp = (cc[y0:y1, x0:x1] == j).astype(np.uint8)
                ring = (cv2.dilate(comp, kernel) > 0) & (comp == 0) & (region[y0:y1, x0:x1] > 0)
                vals = lmap[y0:y1, x0:x1][ring]
                vals = vals[vals != i]
                if len(vals):
                    sub = lmap[y0:y1, x0:x1]
                    sub[comp > 0] = np.bincount(vals).argmax()
                    changed = True
        if not changed:
            break
    return lmap


def sole_region(lab: np.ndarray, mask: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """The sole: the band along the bottom of the shoe, found as the run of the bottom colour up each column, or,
    when the sole is the upper's colour, as the strongest horizontal edge above the bottom."""
    import cv2
    h, w = mask.shape
    present = mask.any(axis=0)
    xs = np.nonzero(present)[0]
    bottom = np.where(present, h - 1 - mask[::-1].argmax(axis=0), 0)
    top = np.where(present, mask.argmax(axis=0), 0)
    shoe_h = float((bottom - top)[present].max())
    cap = SOLE_MAX * shoe_h
    upper_rows = np.zeros_like(mask)
    for x in xs:
        upper_rows[top[x]:max(top[x], int(bottom[x] - cap)), x] = 1
    main = np.bincount(labels[(upper_rows > 0) & (mask > 0)].ravel()).argmax() if (upper_rows & mask).any() else -1
    bottom_label = np.array([labels[max(0, bottom[x] - 2), x] for x in xs])
    same = np.bincount(bottom_label[bottom_label >= 0]).argmax() == main if (bottom_label >= 0).any() else True
    run = np.full(w, np.nan)
    if not same:
        sole_label = np.bincount(bottom_label[bottom_label >= 0]).argmax()
        for x, bl in zip(xs, bottom_label, strict=True):
            if bl != sole_label:   # the sole is missing from the cut-out here, or hidden: the neighbours decide
                continue
            y, gap, limit = bottom[x] - 2, 0, min(cap, 0.8 * (bottom[x] - top[x]))
            while y > bottom[x] - limit and gap <= 2:
                gap = 0 if labels[y, x] == bl else gap + 1
                y -= 1
            run[x] = bottom[x] - (y + gap)
    else:
        gy = np.abs(cv2.Sobel(cv2.GaussianBlur(lab[..., 0], (0, 0), 1.2), cv2.CV_32F, 0, 1, ksize=3)) / 8
        for x in xs:
            lo, hi = int(bottom[x] - min(cap, 0.8 * (bottom[x] - top[x]))), bottom[x] - 3
            if hi - lo < 3:
                continue
            col = gy[lo:hi, x] * mask[lo:hi, x]
            if col.max() >= 2.5:
                run[x] = bottom[x] - (lo + int(col.argmax()))
    good = run[xs]
    if np.isnan(good).all() or np.nanmedian(good) >= 0.95 * cap:
        run[xs] = 0.1 * shoe_h
    else:
        fill = np.nanmedian(good)
        good = np.where(np.isnan(good), fill, good)
        k = max(3, (len(xs) // 14) | 1)
        good = cv2.medianBlur(np.clip(good, 0, 255).astype(np.uint8).reshape(1, -1), min(k, 255)).ravel().astype(np.float64)
        run[xs] = np.clip(good, 0.04 * shoe_h, cap)
    sole = np.zeros_like(mask)
    for x in xs:
        sole[int(round(bottom[x] - run[x])):bottom[x] + 1, x] = 1
    return sole & mask


def _contours(binary: np.ndarray, eps: float, min_area: float) -> list[list[np.ndarray]]:
    """The pieces of a binary image as paths: [outer, holes...], simplified by `eps` px."""
    import cv2
    cs, hier = cv2.findContours(binary.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if hier is None:
        return []
    hier = hier[0]
    out = []
    for i, c in enumerate(cs):
        if hier[i][3] != -1 or cv2.contourArea(c) < min_area:
            continue
        path = [c]
        j = hier[i][2]
        while j != -1:
            if cv2.contourArea(cs[j]) >= min_area:
                path.append(cs[j])
            j = hier[j][0]
        simple = [cv2.approxPolyDP(p, eps, True)[:, 0, :].astype(np.float64) for p in path]
        simple = [p for p in simple if len(p) >= 3]
        if simple and len(simple[0]) >= 3:
            out.append(simple)
    return out


def silhouette(mask: np.ndarray, sigma: float) -> np.ndarray:
    """The cut-out's outline with specks and jaggies smoothed away (as the phase-0 traced style did)."""
    import cv2
    k = max(3, (max(mask.shape) // 150) | 1)
    a = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))
    a = cv2.GaussianBlur(a.astype(np.float32), (0, 0), max(sigma, 0.5))
    a = (a > 0.5).astype(np.uint8)
    keep, _ = clean_mask(a * 255)
    return keep


def trace(rgb: np.ndarray, mask: np.ndarray, a: Approach) -> Trace:
    import cv2
    real = to_lab(rgb)
    lab = to_lab(prefilter(rgb, mask, a))
    area = int(mask.sum())
    min_area = max(6, int(SPECK * area))
    eps = a.smooth * WORK
    sil = silhouette(mask, a.blur)
    inside = mask > 0
    # the whole shoe quantised once, to find where the sole is
    labels_all = np.full(mask.shape, -1, np.int32)
    labels_all[inside], _ = quantise(lab[inside], real[inside], a.colors)
    sole = sole_region(lab, mask, labels_all) & sil
    upper = sil & (1 - sole)
    regions: list[Region] = []
    lmap = np.full(mask.shape, -1, np.int32)
    parts = []
    for part, region, k in (("upper", upper, a.colors), ("sole", sole, 2)):
        sel = (region > 0) & inside
        if sel.sum() < min_area:
            continue
        lab_sel, real_sel = lab[sel], real[sel]
        labels, cols = quantise(lab_sel, real_sel, k)
        offset = int(lmap.max()) + 1
        sub = np.full(mask.shape, -1, np.int32)
        sub[sel] = labels
        # pixels of the region outside the cut-out (the smoothed outline reaches a little further) take the nearest label
        missing = (region > 0) & ~sel
        if missing.any():
            _, idx = cv2.distanceTransformWithLabels((sub < 0).astype(np.uint8), cv2.DIST_L2, 5,
                                                     labelType=cv2.DIST_LABEL_PIXEL)
            src = np.zeros(int(idx.max()) + 1, np.int32)
            src[idx[sub >= 0]] = sub[sub >= 0]
            sub[missing] = src[idx[missing]]
        sub = smooth_labels(sub, region, len(cols), a.blur)
        sub = remove_specks(sub, region, min_area)
        ids = [i for i in range(len(cols)) if ((sub == i) & (region > 0)).any()]
        cols = [cols[i] for i in ids]
        remap = np.full(int(sub.max()) + 2, -1, np.int32)
        for n, i in enumerate(ids):
            remap[i] = n
        sub = np.where(region > 0, remap[sub], -1)
        lmap[region > 0] = sub[region > 0] + offset
        parts.append((part, region, sub, cols))
    for part, region, sub, cols in parts:
        sizes = [int(((sub == i) & (region > 0)).sum()) for i in range(len(cols))]
        main = int(np.argmax(sizes))
        if part == "upper":
            regions.append(Region(lab_hex(cols[main]), cols[main], "silhouette", _contours(sil, eps, min_area)))
        else:
            regions.append(Region(lab_hex(cols[main]), cols[main], "sole", _contours(region, eps, min_area)))
        for i in sorted(range(len(cols)), key=lambda i: -sizes[i]):
            if i == main:
                continue
            paths = _contours((sub == i) & (region > 0), eps, min_area)
            if paths:
                regions.append(Region(lab_hex(cols[i]), cols[i], part, paths))
    if not regions or regions[0].part != "silhouette":   # an all-sole shoe cannot happen, but keep the outline first
        main = real[inside].mean(axis=0)
        regions.insert(0, Region(lab_hex(main), main, "silhouette", _contours(sil, eps, min_area)))
    return Trace(a, regions, mask.shape)


# ------------------------------------------------------------------ curves

def _beziers(pts: np.ndarray) -> list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
    """A smooth closed curve through a polygon (Catmull-Rom tangents, kept to each side's length), as cubic Bezier
    segments (p0, c1, c2, p1)."""
    n = len(pts)
    tangents = []
    for i in range(n):
        a, b = pts[i] - pts[(i - 1) % n], pts[(i + 1) % n] - pts[i]
        la, lb = np.hypot(*a), np.hypot(*b)
        turn = np.degrees(np.arccos(np.clip(np.dot(a, b) / max(la * lb, 1e-9), -1, 1)))
        d = pts[(i + 1) % n] - pts[(i - 1) % n]
        # a sharp turn (the heel's corner on the sole) stays a corner; elsewhere the curve runs through smoothly
        tangents.append(np.zeros(2) if turn > CORNER else d / max(np.hypot(*d), 1e-9))
    segs = []
    for i in range(n):
        p1, p2 = pts[i], pts[(i + 1) % n]
        k = np.hypot(*(p2 - p1)) / 3   # control points a third of the way along: the curve never overshoots
        segs.append((p1, p1 + tangents[i] * k, p2 - tangents[(i + 1) % n] * k, p2))
    return segs


def _sampled(pts: np.ndarray, steps: int = 6) -> np.ndarray:
    t = np.linspace(0, 1, steps, endpoint=False)[:, None]
    out = [((1 - t) ** 3) * a + 3 * ((1 - t) ** 2) * t * b + 3 * (1 - t) * t ** 2 * c + t ** 3 * d
           for a, b, c, d in _beziers(pts)]
    return np.concatenate(out)


def _d(path: list[np.ndarray], s: float, ox: float, oy: float) -> str:
    out = []
    for pts in path:
        q = pts * s + np.array([ox, oy])
        segs = _beziers(q)
        out.append(f"M{q[0][0]:.1f},{q[0][1]:.1f}" + "".join(
            f"C{b[0]:.1f},{b[1]:.1f} {c[0]:.1f},{c[1]:.1f} {d[0]:.1f},{d[1]:.1f}" for _, b, c, d in segs) + "Z")
    return "".join(out)


def raster(t: Trace) -> np.ndarray:
    """The trace painted at WORK scale: each pixel holds the index of the region on top there (-1 = not shoe)."""
    import cv2
    out = np.full(t.shape, -1, np.int32)
    sil = np.zeros(t.shape, np.uint8)
    for path in t.regions[0].paths:
        cv2.fillPoly(sil, [np.round(_sampled(p)).astype(np.int32) for p in path], 1)
    for idx, r in enumerate(t.regions):
        m = np.zeros(t.shape, np.uint8)
        for path in r.paths:
            cv2.fillPoly(m, [np.round(_sampled(p)).astype(np.int32) for p in path], 1)
        out[(m > 0) & (sil > 0)] = idx
    return out


def placement(t: Trace) -> tuple[float, float, float]:
    """Scale and offset that put the traced shoe where the templates draw a shoe: toe at x 40, on the ground at y 330."""
    pts = np.concatenate([p for path in t.regions[0].paths for p in path])
    x0, y0 = pts.min(axis=0)
    x1, y1 = pts.max(axis=0)
    s = min(SHOE_L / max(x1 - x0, 1), (SHOE_G - 40) / max(y1 - y0, 1))
    ox = SHOE_X0 + (SHOE_L - (x1 - x0) * s) / 2 - x0 * s
    oy = SHOE_G - y1 * s
    return s, ox, oy


def to_svg(t: Trace, uid: str = "t") -> str:
    """The trace in the app's style B, on the templates' card."""
    s, ox, oy = placement(t)
    base = t.regions[0].color
    inner = shade(base, 0.42) if luminance(base) < 0.3 else INK
    clip = f"k{uid}"
    sil = "".join(_d(p, s, ox, oy) for p in t.regions[0].paths)
    fills_ = "".join(f'<path d="{_d(p, s, ox, oy)}" fill="{r.color}" fill-rule="evenodd"/>' for r in t.regions for p in r.paths)
    lines = "".join(f'<path d="{_d(p, s, ox, oy)}" fill="none" stroke="{inner}" stroke-width="{INNER_W}" '
                    'stroke-linejoin="round" opacity=".95"/>' for r in t.regions[1:] for p in r.paths)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CARD_W} {CARD_H}" width="{CARD_W}" height="{CARD_H}">'
            f'<defs><clipPath id="{clip}"><path d="{sil}" fill-rule="evenodd"/></clipPath></defs>'
            f'<rect width="{CARD_W}" height="{CARD_H}" rx="18" fill="{CARD}"/>'
            f'<g clip-path="url(#{clip})">{fills_}{lines}</g>'
            f'<path d="{sil}" fill="none" stroke="{INK}" stroke-width="{OUTLINE_W}" stroke-linejoin="round"/></svg>')


# ------------------------------------------------------------------ scores

def mark_mask(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """High-contrast marks (logos, stripes, panels): pixels far in colour from the median of the shoe round them."""
    import cv2
    inside = mask > 0
    if not inside.any():
        return np.zeros(mask.shape, bool)
    fill = rgb.copy()
    fill[~inside] = np.median(rgb[inside], axis=0).astype(np.uint8)
    lab8 = cv2.cvtColor(fill, cv2.COLOR_RGB2Lab)
    ys = np.nonzero(inside.any(axis=1))[0]
    k = max(5, int(0.25 * (ys.max() - ys.min() + 1)) | 1)
    k = min(k, 255)
    med = np.stack([cv2.medianBlur(lab8[..., c], k) for c in range(3)], axis=-1)
    diff = lab8.astype(np.float32) - med.astype(np.float32)
    diff[..., 0] *= 100 / 255
    de = np.linalg.norm(diff, axis=-1)
    core = cv2.erode(mask.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    m = ((de > MARK_DE) & core).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, cc, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    keep = np.zeros(mask.shape, bool)
    limit = SPECK * inside.sum()
    for j in range(1, n):
        if stats[j, cv2.CC_STAT_AREA] >= limit:
            keep |= cc == j
    return keep


@dataclass
class Scores:
    iou: float               # traced silhouette against the cut-out
    delta_e: float           # mean colour error of the regions against the photo (area-weighted CIE76)
    colors: int
    paths: int
    marks: float | None      # share of the photo's high-contrast marks the trace keeps; None = the photo has none
    score: float             # the combined score, 0..1


def combined(iou: float, de: float, paths: int, marks: float | None) -> float:
    clamp = lambda v: float(min(1.0, max(0.0, v)))   # noqa: E731
    parts = [(0.35, clamp((iou - 0.8) / 0.2)), (0.25, clamp(1 - de / 25)), (0.2, clamp(1 - (paths - 3) / 25))]
    if marks is not None:
        parts.append((0.2, marks))
    return sum(w * v for w, v in parts) / sum(w for w, _ in parts)


def score(t: Trace, rgb: np.ndarray, mask: np.ndarray, photo_marks: np.ndarray) -> Scores:
    import cv2
    r = raster(t)
    traced, cut = r >= 0, mask > 0
    iou = float((traced & cut).sum() / max((traced | cut).sum(), 1))
    real = to_lab(rgb)
    total, err = 0, 0.0
    painted = np.zeros(rgb.shape, np.uint8)
    for idx, region in enumerate(t.regions):
        pix = (r == idx) & cut
        painted[r == idx] = np.asarray([int(region.color[i:i + 2], 16) for i in (1, 3, 5)], np.uint8)
        if pix.any():
            n = int(pix.sum())
            err += n * delta_e(real[pix].mean(axis=0), region.lab)
            total += n
    marks = None
    if photo_marks.sum() >= SPECK * cut.sum():
        kept = cv2.dilate(mark_mask(painted, mask).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        marks = float((photo_marks & kept).sum() / photo_marks.sum())
    de = err / max(total, 1)
    return Scores(iou, de, t.colors, t.paths, marks, combined(iou, de, t.paths, marks))


# ------------------------------------------------------------------ the gate

def frame_touch(rgb: np.ndarray, mask: np.ndarray) -> float:
    """How much of the shoe's outline runs into the photo's frame, as a share of the outline's length. Only where
    the shoe really meets the frame counts: the cut-out comes within FRAME_NEAR of the frame there (GrabCut never
    reaches the frame itself) and the photo's outermost pixels there do not look like the background. A shoe
    close to the border of a white-padded product photo is not cut off: its border is plain background."""
    import cv2
    cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cs:
        return 0.0
    perimeter = max(cv2.arcLength(max(cs, key=cv2.contourArea), True), 1.0)
    h, w = mask.shape
    bx, by = max(2, int(FRAME_NEAR * w)), max(2, int(FRAME_NEAR * h))
    sides = [(mask[:by].any(axis=0), rgb[0]), (mask[-by:].any(axis=0), rgb[-1]),
             (mask[:, :bx].any(axis=1), rgb[:, 0]), (mask[:, -bx:].any(axis=1), rgb[:, -1])]
    if not any(near.any() for near, _ in sides):
        return 0.0
    ring = np.concatenate([px[~near] for near, px in sides])
    bg = np.median(to_lab(ring[None])[0], axis=0) if len(ring) >= 20 else None
    touch = 0
    for near, px in sides:
        if not near.any():
            continue
        if bg is None:
            touch += int(near.sum())
            continue
        de = np.linalg.norm(to_lab(px[near][None])[0] - bg, axis=-1)
        touch += int((de > FRAME_DE).sum())
    return float(touch / perimeter)


def photo_signals(rgb: np.ndarray, soft: np.ndarray) -> tuple[dict[str, float], np.ndarray]:
    """Measured signals from the photo and its cut-out, before orientation; and the cleaned, refined mask."""
    import cv2
    mask, second = clean_mask(soft)
    sig: dict[str, float] = {"found": float(mask.sum() > 0.002 * mask.size)}
    if not sig["found"]:
        return sig, mask
    mask = refine_mask(rgb, mask)
    ys, xs = np.nonzero(mask)
    sig["size_px"] = float(max(xs.max() - xs.min() + 1, ys.max() - ys.min() + 1))
    sig["second_piece"] = second
    cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(cs, key=cv2.contourArea)
    sig["solidity"] = float(cv2.contourArea(c) / max(cv2.contourArea(cv2.convexHull(c)), 1))
    sig["edge_touch"] = frame_touch(rgb, mask)
    return sig, mask


def work_signals(o: Oriented) -> dict[str, float]:
    """Signals measured on the turned shoe at WORK scale."""
    import cv2
    lab = to_lab(o.rgb)
    inside = o.mask > 0
    k = np.ones((7, 7), np.uint8)
    # how far the shoe stands out from what is just outside it, measured all along its outline (the median), in
    # two widths: a band a few px either side of the edge, skipped so that a soft edge does not count as low
    # contrast; and a narrow band right at the edge, where a white shoe on a white ground still differs (its
    # surface turns away from the light there, and seams and shadow lines run along it). The larger counts.
    def across(skip: int, reach: int, sigma: float) -> float:
        near, far = np.ones((2 * skip + 1,) * 2, np.uint8), np.ones((2 * reach + 1,) * 2, np.uint8)
        band_in = ((cv2.erode(o.mask, near) > 0) & ~(cv2.erode(o.mask, far) > 0)).astype(np.float32)
        band_out = ((cv2.dilate(o.mask, far) > 0) & ~(cv2.dilate(o.mask, near) > 0)).astype(np.float32)

        def local(band):
            w = cv2.GaussianBlur(band, (0, 0), sigma)
            return np.stack([cv2.GaussianBlur(lab[..., c] * band, (0, 0), sigma) for c in range(3)], -1) / np.maximum(w, 1e-6)[..., None]

        edge = (cv2.dilate(o.mask, np.ones((3, 3), np.uint8)) > 0) & ~(cv2.erode(o.mask, np.ones((3, 3), np.uint8)) > 0)
        edge &= (cv2.GaussianBlur(band_out, (0, 0), sigma) > 0.02) & (cv2.GaussianBlur(band_in, (0, 0), sigma) > 0.02)
        return float(np.median(np.linalg.norm(local(band_in)[edge] - local(band_out)[edge], axis=-1))) if edge.any() else 0.0

    contrast = max(across(3, 10, 6), across(1, 4, 3))
    L = lab[..., 0]
    gx = cv2.Sobel(L, cv2.CV_32F, 1, 0, ksize=3) / 8
    gy = cv2.Sobel(L, cv2.CV_32F, 0, 1, ksize=3) / 8
    grad = np.hypot(gx, gy)
    zone = cv2.dilate(o.mask, k) > 0
    spread = max(float(np.percentile(L[zone], 98) - np.percentile(L[zone], 2)), 10.0)
    sharp = float(np.percentile(grad[zone], 99.5)) / spread
    clipped = float(((L[inside] > 98) | (L[inside] < 2)).mean())
    return {"contrast_de": contrast, "sharpness": sharp, "clipped": clipped, "aspect": o.aspect,
            "sole_lift": o.lift, "toe_heel": o.toe_heel,
            **({"second_sole": second_sole(o.mask)[0], "second_top": second_top(o.rgb, o.mask)[0]}
               if o.aspect >= GATE["aspect"][0] else {"second_sole": 0.0, "second_top": 0.0})}


@dataclass
class Gate:
    ok: bool
    reasons: list[str]
    signals: dict[str, float]
    notes: list[str] = field(default_factory=list)      # what the advisory signals saw; never turns a photo down
    told: dict[str, str] = field(default_factory=dict)  # the tagger's word on the photo (`told_from`), when given


def _over(table: dict, signals: dict[str, float]) -> list[str]:
    out = []
    for name, (limit, way, why) in table.items():
        v = signals.get(name)
        if v is None:
            continue
        if (way == "below" and v < limit) or (way == "above" and v > limit):
            out.append(f"{why} ({name} {v:.3g}, limit {limit:g})")
    return out


def told_from(answer: dict | None) -> dict[str, str]:
    """The tagger's word on the photo from its answer (as stored, a dict): how many shoes it shows and from
    where. Empty when the answer is missing, is older than the question, or says 'na'."""
    d = (answer or {}).get("details") or {}
    return {k: d[k] for k in ("shoes_in_photo", "shoe_view") if isinstance(d.get(k), str) and d[k] != "na"}


def _told(told: dict[str, str] | None) -> list[str]:
    return [why for (k, v), why in TOLD.items() if (told or {}).get(k) == v]


def gate(signals: dict[str, float], told: dict[str, str] | None = None) -> Gate:
    reasons = _told(told) + _over(GATE, signals)
    return Gate(not reasons, reasons, signals, _over(ADVICE, signals), dict(told or {}))


# ------------------------------------------------------------------ one photo

@dataclass
class Variant:
    approach: Approach
    trace: Trace
    scores: Scores


@dataclass
class Attempt:
    """One way of cutting the photo out, and what the gate said about it before tracing."""
    cutout_by: str
    reasons: list[str]


@dataclass
class Reading:
    """What tracing one photo found: the cut-out, the shoe turned, a trace per approach, and the gate."""
    cutout_by: str
    mask: np.ndarray = field(repr=False)            # the cleaned cut-out mask (0/1), the photo's size
    oriented: Oriented | None
    variants: list[Variant]
    gate: Gate
    best: str | None = None
    seconds: float = 0.0
    attempts: list[Attempt] = field(default_factory=list)   # every cut-out tried, in order; the last one is used


Cutter = Callable[[Image.Image], "np.ndarray | None"]


def trace_photo(img: Image.Image, cutters: Sequence[tuple[str, Cutter]] | None = None,
                approaches: Sequence[Approach] = (APPROACH,), told: dict[str, str] | None = None) -> Reading:
    """Cut out, turn, trace and check one photo. `cutters` are the ways to cut it out, by name, in the order to
    try them (each returns a soft mask, 0..255, or None when it cannot run); GrabCut alone by default. When a
    cut-out fails the gate, the next way is tried before the photo is turned down (a white shoe on a white
    ground often leaks out of one cut-out and not the other); if all fail, the one with the fewest reasons wins.
    `told` is the tagger's word on the photo (`told_from`); a pair or a view other than the side turns it down."""
    t0 = time.time()
    rgb = np.asarray(img.convert("RGB"))
    cutters = list(cutters or [("grabcut", grabcut_mask)])
    tried: list[tuple[str, dict[str, float], np.ndarray, Oriented | None, Gate]] = []
    for name, cut in cutters:
        soft = cut(img)
        if soft is None:
            continue
        signals, mask = photo_signals(rgb, soft)
        o = None
        if signals["found"]:
            o = orient(rgb, mask)
            signals.update(work_signals(o))
        tried.append((name, signals, mask, o, gate(signals, told)))
        if tried[-1][4].ok or _told(told):   # another cut-out cannot change what the tagger saw
            break
    if not tried:
        signals, mask = photo_signals(rgb, grabcut_mask(img))
        o = orient(rgb, mask) if signals["found"] else None
        if o is not None:
            signals.update(work_signals(o))
        tried.append(("grabcut", signals, mask, o, gate(signals, told)))
    pick = tried[-1] if tried[-1][4].ok else min(tried, key=lambda t: len(t[4].reasons))
    attempts = [Attempt(t[0], t[4].reasons) for t in tried if t is not pick] + [Attempt(pick[0], pick[4].reasons)]
    by, signals, mask, o, _ = pick
    if o is None:
        return Reading(by, mask, None, [], gate(signals, told), None, time.time() - t0, attempts)
    photo_marks = mark_mask(o.rgb, o.mask)
    variants = []
    for a in approaches:
        t = trace(o.rgb, o.mask, a)
        variants.append(Variant(a, t, score(t, o.rgb, o.mask, photo_marks)))
    best = max(variants, key=lambda v: v.scores.score)
    signals["trace_iou"] = max(v.scores.iou for v in variants)
    return Reading(by, mask, o, variants, gate(signals, told), best.approach.name, time.time() - t0, attempts)
