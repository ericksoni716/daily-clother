"""A traced shoe as data (#192, stage 2a): what `trace.trace_photo` found in a side-on photo, measured in the
coordinates `frontshoe` draws in, so the app can store it (stage 2b) and draw the shoe from it (2b and 2c).

Coordinates: `u` is the share of the length from the heel (0) to the toe tip (1); heights are in cm above the
ground the shoe rests on. The shoe is scaled to `frontshoe`'s 29.5 cm reference shoe, whatever its real size.

The record is plain data (numbers, strings, lists), versioned, and turns into JSON and back. OpenCV is imported
only inside the functions that read the photo.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field

import numpy as np

from . import frontshoe
from . import trace as T

VERSION = 2                  # raised whenever a field changes meaning; older records are read, newer ones refused
LENGTH = frontshoe.LENGTH
PROFILE_N = 41               # the side profile is sampled at this many even steps from heel to toe
DETAIL_PX = 1200             # the detail pass (laces, eyelets, stitching) looks at the shoe this long, at most
DETAIL_DE = 14.0             # a detail differs this much in colour from the shoe just round it

# Where each part of the upper usually sits on a side view: (u from, u to, share of the upper's height from, to),
# the height measured up from the top of the sole to the upper's top edge in that column. A zone only names the
# traced colour pieces: a piece takes the label of the zone it mostly lies in, and is never cut along a zone's edge.
ZONES = {
    "heel_counter": (0.0, 0.2, 0.0, 0.8),
    "quarter": (0.2, 0.42, 0.0, 0.8),
    "collar": (0.0, 0.42, 0.8, 1.01),
    "tongue": (0.42, 0.62, 0.75, 1.01),
    "vamp": (0.42, 0.82, 0.0, 0.75),
    "toe_cap": (0.82, 1.01, 0.0, 1.01),
}
LACE_STYLES = ("low_sneaker", "runner", "high_top", "derby", "oxford", "boot")


@dataclass
class Part:
    name: str
    color: str                       # "#rrggbb"
    measured: bool                   # False: not seen in the photo, so given the colour of the part it joins
    region: list[list[list[float]]] = field(default_factory=list)   # outlines, each a list of [u, cm]
    within: str = ""                 # seen, but no piece of its own: it is part of this one's piece ("upper": the base)


@dataclass
class Mark:
    kind: str                        # stripes | curve | panel | text | other
    color: str
    u: float                         # its middle
    h: float
    length_cm: float                 # along its longest side
    width_cm: float
    angle: float                     # degrees from the ground line; positive rises towards the toe
    count: int = 1                   # stripes in a set, letters in a text block
    path: list[list[list[float]]] = field(default_factory=list)     # outlines, each a list of [u, cm]


@dataclass
class Row:
    """Laces, eyelets or stitching: things repeated along a line."""
    count: int
    spacing_cm: float
    color: str
    points: list[list[float]] = field(default_factory=list)          # each one's middle, [u, cm]


@dataclass
class Profile:
    u: list[float]
    top: list[float]                 # the upper's top edge, cm above the ground
    bottom: list[float]              # the sole's underside, cm above the ground (toe spring, a curved outsole)
    sole: list[float]                # the sole's thickness, cm

    def top_above_sole(self, u: float) -> float:
        """The upper's height above the sole at `u`, as `frontshoe`'s tables give it."""
        return float(np.interp(u, self.u, np.subtract(np.subtract(self.top, self.bottom), self.sole)))


@dataclass
class Region:
    """One colour of the traced drawing, in paint order; the first is the whole shoe."""
    color: str
    part: str                        # silhouette | upper | sole
    paths: list[list[list[list[float]]]]   # pieces, each an outline then its holes, each a list of [u, cm]
    labels: list[str] = field(default_factory=list)   # each piece's part: the one it mostly lies in ("upper": the base)


@dataclass
class TracedShoe:
    version: int
    approach: str
    cutout_by: str
    profile: Profile
    parts: list[Part]
    marks: list[Mark]
    laces: Row | None
    eyelets: Row | None
    stitching: Row | None
    style: str                       # the nearest `frontshoe.STYLES` entry, from the profile
    confidence: float                # 0..1: how far to trust the trace
    gate: dict                       # {"ok": bool, "reasons": [...], "notes": [...], "told": {...}, "signals": {...}}
    regions: list[Region]

    def part(self, name: str) -> Part | None:
        return next((p for p in self.parts if p.name == name), None)

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))

    @classmethod
    def from_json(cls, text: str) -> TracedShoe:
        d = json.loads(text)
        version = d.get("version")
        if not isinstance(version, int) or version > VERSION:
            raise ValueError(f"a traced shoe of version {version!r} is newer than this program reads ({VERSION})")

        def row(r):
            return Row(**r) if r else None

        return cls(version=version, approach=d["approach"], cutout_by=d["cutout_by"], profile=Profile(**d["profile"]),
                   parts=[Part(**p) for p in d["parts"]], marks=[Mark(**m) for m in d["marks"]],
                   laces=row(d.get("laces")), eyelets=row(d.get("eyelets")), stitching=row(d.get("stitching")),
                   style=d["style"], confidence=d["confidence"], gate=d["gate"], regions=[Region(**r) for r in d["regions"]])


# ------------------------------------------------------------------ the frame: pixels to (u, cm)

@dataclass
class _Frame:
    x_toe: float
    x_heel: float
    y_ground: float
    cm: float                        # cm per pixel

    @classmethod
    def of(cls, shoe: np.ndarray) -> _Frame:
        ys, xs = np.nonzero(shoe)
        x0, x1 = float(xs.min()), float(xs.max() + 1)
        return cls(x0, x1, float(ys.max() + 1), LENGTH / max(x1 - x0, 1.0))

    def uh(self, pts) -> np.ndarray:
        pts = np.asarray(pts, np.float64).reshape(-1, 2)
        return np.stack([(self.x_heel - pts[:, 0]) / (self.x_heel - self.x_toe), (self.y_ground - pts[:, 1]) * self.cm], -1)

    def x(self, u: float) -> float:
        return self.x_heel - u * (self.x_heel - self.x_toe)

    def scaled(self, s: float) -> _Frame:
        return _Frame(self.x_toe * s, self.x_heel * s, self.y_ground * s, self.cm / s)


def _path(f: _Frame, pts) -> list[list[float]]:
    return [[round(float(u), 4), round(float(h), 3)] for u, h in f.uh(pts)]


def _outlines(f: _Frame, binary: np.ndarray, eps: float = 1.0, min_area: float = 4.0) -> list[list[list[float]]]:
    import cv2
    cs, _ = cv2.findContours(binary.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    out = []
    for c in sorted(cs, key=cv2.contourArea, reverse=True):
        if cv2.contourArea(c) < min_area:
            continue
        p = cv2.approxPolyDP(c, eps, True)[:, 0, :]
        if len(p) >= 3:
            out.append(_path(f, p + 0.5))
    return out


# ------------------------------------------------------------------ the profile

def _profile(f: _Frame, shoe: np.ndarray, sole: np.ndarray) -> Profile:
    us = np.linspace(0, 1, PROFILE_N)
    w = shoe.shape[1]
    top, bottom, thick = [], [], []
    for u in us:
        x = int(np.clip(round(f.x(u) - 0.5), f.x_toe + 1, f.x_heel - 2))
        x = min(max(x, 0), w - 1)
        col = np.nonzero(shoe[:, x])[0]
        if not len(col):
            top.append(0.0)
            bottom.append(0.0)
            thick.append(0.0)
            continue
        top.append((f.y_ground - col.min()) * f.cm)
        bottom.append((f.y_ground - col.max() - 1) * f.cm)
        thick.append(float(sole[:, x].sum()) * f.cm)
    r = [round(float(v), 3) for v in us]
    return Profile(r, [round(v, 2) for v in top], [round(max(v, 0.0), 2) for v in bottom], [round(v, 2) for v in thick])


# ------------------------------------------------------------------ the style hint

SHAFT_CM = 12.0             # a collar this high above the ground (the median along the back 30%) is a shaft ...
SHAFT_ABOVE_SOLE_CM = 9.0   # ... when it is also this high above the sole (a thick-soled runner's collar is not)


def style_hint(p: Profile, laced: bool) -> str:
    """The nearest of `frontshoe.STYLES` to the measured profile. The collar's height (its median along the back
    30% of the length, so that a heel tab or a pull loop does not count), above the ground and above the sole,
    first decides between a shoe with a shaft (a boot or a high-top) and one without. Then the nearest style is the one whose top line, standing
    on the measured sole, runs closest to the measured top, with a little weight on the sole's thickness. A
    shoe with laces is never a loafer, slip-on or Chelsea boot."""
    mid = [i for i, u in enumerate(p.u) if 0.1 <= u <= 0.9]
    sole = float(np.median([p.sole[i] for i in mid]))
    collar = float(np.median([t for u, t in zip(p.u, p.top, strict=True) if u <= 0.3]))
    heel_sole = float(np.median([t for u, t in zip(p.u, p.sole, strict=True) if u <= 0.3]))
    shafted = collar >= SHAFT_CM and collar - heel_sole >= SHAFT_ABOVE_SOLE_CM
    along = [(u, t, b) for u, t, b in zip(p.u, p.top, p.bottom, strict=True) if 0.05 <= u <= 0.95]
    best, best_d = "boot" if shafted else "low_sneaker", math.inf
    for name, (_, sole_t, table, shaft) in frontshoe.STYLES.items():
        if table is None or (laced and name not in LACE_STYLES) or bool(shaft) != shafted:
            continue

        def want(u: float, b: float, sole_t=sole_t, table=table, shaft=shaft) -> float:
            t = b + sole_t + frontshoe._interp(table, u)
            return max(t, shaft - 1.5 * u) if shaft and u < 0.42 else t

        d = float(np.sqrt(np.mean([(t - want(u, b)) ** 2 for u, t, b in along]))) + 0.3 * abs(sole - sole_t)
        if d < best_d:
            best, best_d = name, d
    return best


# ------------------------------------------------------------------ the details: laces, eyelets, stitching

@dataclass
class _Bit:
    u: float
    h: float
    length: float
    width: float
    fill: float
    lab: np.ndarray
    pts: np.ndarray                 # its pixels' outline, (u, cm)


@dataclass
class _View:
    """The shoe at up to DETAIL_PX along the length, for the details."""
    rgb: np.ndarray
    lab: np.ndarray
    mask: np.ndarray
    upper: np.ndarray              # the upper without the sole, its edge pixel trimmed
    f: _Frame


def _view(o: T.Oriented, sole_work: np.ndarray, f: _Frame) -> _View | None:
    import cv2
    rgb, mask = o.full_rgb, o.full_mask
    if rgb is None or mask is None:
        return None
    s_full = rgb.shape[1] / o.rgb.shape[1]
    length_full = (f.x_heel - f.x_toe) * s_full
    s = min(1.0, DETAIL_PX / max(length_full, 1.0))
    size = (max(1, int(round(rgb.shape[1] * s))), max(1, int(round(rgb.shape[0] * s))))
    if s < 1:
        rgb = cv2.resize(rgb, size, interpolation=cv2.INTER_AREA)
        mask = (cv2.resize(mask * 255, size, interpolation=cv2.INTER_LINEAR) > 127).astype(np.uint8)
    hf = f.scaled(size[0] / o.rgb.shape[1])
    sole = cv2.resize(sole_work.astype(np.uint8), size, interpolation=cv2.INTER_NEAREST)
    upper = (mask > 0) & (sole == 0)
    upper = cv2.erode(upper.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    if upper.sum() < 100:
        return None
    return _View(rgb, T.to_lab(rgb), mask, upper, hf)


def _bits(v: _View | None) -> list[_Bit]:
    """Small things on the upper that differ from the shoe just round them, seen at up to DETAIL_PX along the
    length, so that laces and eyelets are not lost when the trace keeps only a few colours."""
    import cv2
    if v is None:
        return []
    rgb, mask, upper, hf = v.rgb, v.mask, v.upper, v.f
    px_cm = 1 / hf.cm
    fill = rgb.copy()
    fill[mask == 0] = np.median(rgb[mask > 0], axis=0).astype(np.uint8)
    k = min(255, int(1.2 * px_cm) | 1)
    around = cv2.medianBlur(fill, k) if k >= 3 else fill
    lab, lab_around = v.lab, T.to_lab(around)
    diff = (np.linalg.norm(lab - lab_around, axis=-1) > DETAIL_DE) & upper
    diff = cv2.morphologyEx(diff.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(diff, 8)
    out = []
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        if area < max(4, 0.004 * px_cm * px_cm) or area > 3.0 * px_cm * px_cm:
            continue
        ys, xs = np.nonzero(labels == i)
        (cx, cy), (a, b), _ = cv2.minAreaRect(np.stack([xs, ys], -1).astype(np.float32))
        a, b = max(a, b) + 1, min(a, b) + 1
        u, h = hf.uh([[cx + 0.5, cy + 0.5]])[0]
        cs, _ = cv2.findContours((labels == i).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        c = max(cs, key=cv2.contourArea)[:, 0, :] + 0.5
        # its colour away from its edge, where it blends with what is round it
        core = cv2.erode((labels == i).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
        colour = np.median(lab[core] if core.sum() >= 0.2 * area else lab[ys, xs], axis=0)
        out.append(_Bit(float(u), float(h), a * hf.cm, b * hf.cm, area / (a * b), colour, hf.uh(c)))
    return out


def _peaks(sig: np.ndarray, apart: int) -> list[int]:
    """The peaks of a signal at least `apart` samples apart, each standing well above the dips beside it."""
    hi = float(sig.max())
    if hi <= 0:
        return []
    cand = [i for i in range(sig.size) if sig[i] >= 0.35 * hi
            and sig[i] >= sig[max(0, i - apart // 2):i + apart // 2 + 1].max()]
    peaks: list[int] = []
    for i in cand:
        if peaks and (i - peaks[-1] < apart or sig[peaks[-1]:i + 1].min() > 0.75 * min(sig[i], sig[peaks[-1]])):
            if sig[i] > sig[peaks[-1]]:
                peaks[-1] = i
            continue
        peaks.append(i)
    return peaks


def lace_row_of(v: _View | None, upper_lab, eyelets: Row | None = None, away: np.ndarray | None = None) -> Row | None:
    """The laces, counted along the lacing rather than piece by piece: laces that cross or touch join into one
    piece, and the pieces are lost. Along the throat (40 to 88% of the length from the heel, up to 3 cm below
    the top edge), in each of the four commonest colours there that are not the upper's, the line the laces run
    along is found (their middle depth below the top, smoothed); each lace, or each crossing, meets it once.
    Of the colours whose peaks along that line repeat regularly, the one that covers most of the line is the
    laces' (unless its peaks fall on the eyelets). With a row of eyelets, only the band down to them is looked
    at (the laces run between the eyelet rows). The stripes of a set (`away`, the view's size) are not looked at:
    their ends reach into the lacing, and their colour is not the laces'."""
    import cv2
    if v is None:
        return None
    hf, px = v.f, 1 / v.f.cm
    W = v.mask.shape[1]
    present = v.mask.any(axis=0)
    top = np.where(present, v.mask.argmax(axis=0), 0)
    x0 = int(max(0, hf.x(0.88)))
    x1 = int(min(W, hf.x(0.40)))
    if x1 - x0 < 3 * px:
        return None
    cols = np.arange(x0, x1)
    deep = 3.0 * px
    if eyelets:   # the lacing band: down to the eyelets, and a little below them
        ey = [(hf.x(u), hf.y_ground - h / hf.cm) for u, h in eyelets.points]
        below = [y - top[int(min(W - 1, max(0, x)))] for x, y in ey]
        deep = min(deep, max(below) + 1.0 * px)
    depth = np.arange(round(0.15 * px), max(round(0.15 * px) + 2, round(deep)))
    ys = (top[cols][None, :] + depth[:, None]).clip(0, v.mask.shape[0] - 1)
    inside = v.upper[ys, cols[None, :]]
    if away is not None:
        inside = inside & ~away[ys, cols[None, :]]
    band = v.lab[ys, cols[None, :]]
    off = (np.linalg.norm(band - np.asarray(upper_lab, np.float32), axis=-1) >= DETAIL_DE) & inside
    if off.sum() < 0.2 * px * px:
        return None
    keys = np.round(band[off] / 10).astype(int)
    found, counts = np.unique(keys, axis=0, return_counts=True)
    best: tuple[float, Row] | None = None
    for k in found[np.argsort(-counts)][:4]:
        colour = np.median(band[off][(keys == k).all(axis=1)], axis=0)
        laces = (np.linalg.norm(band - colour, axis=-1) < 16) & inside
        weight = laces.sum(axis=0)
        if weight.sum() < 0.3 * px * px:
            continue
        mid = np.array([np.median(depth[laces[:, j]]) if weight[j] else np.nan for j in range(cols.size)])
        ok = ~np.isnan(mid)
        if ok.sum() < 3:
            continue
        mid = np.interp(np.arange(cols.size), np.nonzero(ok)[0], mid[ok])
        mid = cv2.GaussianBlur(mid.astype(np.float32).reshape(1, -1), (0, 0), sigmaX=1.5 * px).ravel()
        reach = max(1, round(0.25 * px))
        line = np.array([laces[max(0, round(m - depth[0]) - reach):round(m - depth[0]) + reach + 1, j].mean()
                         for j, m in enumerate(mid)], np.float32)
        line = cv2.GaussianBlur(line.reshape(1, -1), (0, 0), sigmaX=max(0.5, 0.12 * px)).ravel()
        at = _peaks(line, max(2, round(0.8 * px)))
        if len(at) < 2:
            continue
        pts = [(float(hf.uh([[cols[j] + 0.5, top[cols[j]] + mid[j] + 0.5]])[0][0]),
                float(hf.uh([[cols[j] + 0.5, top[cols[j]] + mid[j] + 0.5]])[0][1])) for j in at]
        pts.sort()
        while len(pts) >= 4:   # a mark reaching into the lacing (stripes ending at it) adds a peak too close at an end
            g = np.hypot(*np.diff(np.array([[u * LENGTH, h] for u, h in pts]), axis=0).T)
            if g[0] < 0.6 * np.median(g):
                pts = pts[1:]
            elif g[-1] < 0.6 * np.median(g):
                pts = pts[:-1]
            else:
                break
        xy = np.array([[u * LENGTH, h] for u, h in pts])
        if eyelets:   # a row of eyelets, not laces
            ey = np.array([[u * LENGTH, h] for u, h in eyelets.points])
            if np.mean([np.hypot(*(ey - p).T).min() < 0.4 for p in xy]) >= 0.6:
                continue
        gaps = np.hypot(*np.diff(xy, axis=0).T)
        if len(gaps) >= 2 and np.std(gaps) > 0.45 * np.mean(gaps):
            continue
        row = Row(len(pts), round(float(np.median(gaps)), 2), T.lab_hex(colour),
                  [[round(u, 4), round(h, 3)] for u, h in pts])
        score = float(line.sum())
        if best is None or score > best[0]:
            best = (score, row)
    return best[1] if best else None


def _same_colour(bits: list[_Bit]) -> list[_Bit]:
    """The largest set of bits of one colour."""
    if not bits:
        return []
    near = [[b for b in bits if T.delta_e(b.lab, a.lab) < 18] for a in bits]
    return max(near, key=len)


def _in_line(bits: list[_Bit], tol: float) -> list[_Bit]:
    """The bits that lie along one straight line (in cm), within `tol` cm of it."""
    if len(bits) < 3:
        return bits
    pts = np.array([[b.u * LENGTH, b.h] for b in bits])
    best: list[_Bit] = []
    for i in range(len(bits)):
        for j in range(i + 1, len(bits)):
            d = pts[j] - pts[i]
            n = np.array([-d[1], d[0]]) / max(np.hypot(*d), 1e-9)
            keep = [b for b, p in zip(bits, pts, strict=True) if abs(np.dot(p - pts[i], n)) <= tol]
            if len(keep) > len(best):
                best = keep
    return best


def _row(bits: list[_Bit], regular: float = 0.45) -> Row | None:
    bits = sorted(bits, key=lambda b: b.u)
    if len(bits) < 2:
        return None
    pts = np.array([[b.u * LENGTH, b.h] for b in bits])
    gaps = np.hypot(*np.diff(pts, axis=0).T)
    if len(gaps) >= 2 and np.std(gaps) > regular * np.mean(gaps):
        return None
    color = T.lab_hex(np.median([b.lab for b in bits], axis=0))
    return Row(len(bits), round(float(np.median(gaps)), 2), color, [[round(b.u, 4), round(b.h, 3)] for b in bits])


def details(bits: list[_Bit], top_at, upper_lab) -> tuple[Row | None, Row | None, Row | None]:
    """Laces, eyelets and stitching among the small things on the upper. Bits in the upper's own colour are the
    gaps between laces or stitches, not things on it."""
    bits = [b for b in bits if T.delta_e(b.lab, upper_lab) >= DETAIL_DE]
    near_throat = [b for b in bits if 0.38 <= b.u <= 0.9 and top_at(b.u) - b.h <= 4.0]
    eyelets = _same_colour([b for b in near_throat if 0.2 <= b.length <= 1.0 and b.length / b.width < 1.6 and b.fill > 0.6])
    eyelets = _in_line(eyelets, 0.45)
    eyelet_row = _row(eyelets) if len(eyelets) >= 3 else None
    laces = _same_colour([b for b in near_throat if 0.6 <= b.length <= 4.0 and 0.12 <= b.width <= 0.9 and b.length / b.width >= 1.8])
    lace_row = _row(laces, 0.6) if len(laces) >= 2 else None
    used = {id(b) for b in (eyelets if eyelet_row else []) + (laces if lace_row else [])}
    dashes = _same_colour([b for b in bits if id(b) not in used and 0.12 <= b.length <= 0.7 and b.width <= 0.3
                           and b.length / b.width >= 1.8])
    dashes = _in_line(dashes, 0.25)
    stitch_row = _row(dashes) if len(dashes) >= 4 else None
    return lace_row, eyelet_row, stitch_row


# ------------------------------------------------------------------ parts and marks

def _hull(f: _Frame, pts_uh: list[np.ndarray]) -> list[list[list[float]]]:
    import cv2
    pts = np.concatenate(pts_uh) * np.array([1000.0, 100.0])
    hull = cv2.convexHull(pts.astype(np.float32))[:, 0, :] / np.array([1000.0, 100.0])
    return [[[round(float(u), 4), round(float(h), 3)] for u, h in hull]]


def _sole_band(t: T.Trace, ras: np.ndarray, sole: np.ndarray) -> tuple[np.ndarray, int]:
    """A midsole in another colour than the outsole: a band of one colour that runs along most of the sole, just
    above it. The trace finds the sole as the bottom colour, so this band is first taken for part of the upper.
    Returns the band (0/1) and its region, or an empty band and -1. A mark that touches the band (three stripes
    running down to the sole) is cut off at the band's usual height."""
    H, W = ras.shape
    cols = np.nonzero(sole.any(axis=0))[0]
    if not len(cols):
        return np.zeros_like(sole), -1
    y0 = np.zeros(W, int)            # the top of the sole's bottom run, per column
    for x in cols:
        y = H - 1 - int(sole[::-1, x].argmax())
        while y > 0 and sole[y - 1, x]:
            y -= 1
        y0[x] = y

    def above(x: int) -> int:   # the colour just above the sole (a pixel or two of the outline's colour can part them)
        seen = [int(ras[y, x]) for y in range(y0[x] - 1, max(y0[x] - 4, -1), -1)]
        return next((v for v in seen if v > 0), seen[0] if seen else -1)

    above = np.array([above(x) for x in cols])
    ids = [i for i, r in enumerate(t.regions) if r.part == "upper"]
    counts = {i: int((above == i).sum()) for i in ids}
    if not counts or max(counts.values()) < 0.6 * len(np.nonzero((ras >= 0).any(axis=0))[0]):
        return np.zeros_like(sole), -1
    idx = max(counts, key=counts.get)
    runs = {}
    for x in cols[above == idx]:
        y = y0[x] - 1
        while y >= 0 and ras[y, x] != idx:
            y -= 1
        while y >= 0 and ras[y, x] == idx:
            y -= 1
        runs[int(x)] = y0[x] - 1 - y
    m = float(np.median(list(runs.values())))
    shoe_h = float(((ras >= 0).sum(axis=0)).max())
    if m > 0.45 * shoe_h:
        return np.zeros_like(sole), -1
    band = np.zeros_like(sole)
    for x, run in runs.items():
        n = int(min(run, round(1.6 * m)))
        band[y0[x] - n:y0[x], x] = 1
    return band, idx


@dataclass
class _Piece:
    idx: int                         # the trace's region
    pixels: np.ndarray               # bool, the raster's size
    label: str                       # the part it mostly lies in
    part: bool                       # a piece of a part (else a mark on it)


def _zone_map(f: _Frame, upper: np.ndarray) -> np.ndarray:
    """Each upper pixel's zone, as an index into ZONES (vamp where no zone says)."""
    H, W = upper.shape
    yy, xx = np.mgrid[0:H, 0:W]
    u = (f.x_heel - (xx + 0.5)) / (f.x_heel - f.x_toe)
    top = np.where(upper.any(axis=0), upper.argmax(axis=0), H)
    base = np.where(upper.any(axis=0), H - 1 - upper[::-1].argmax(axis=0), 0)
    v = (base[None, :] - yy) / np.maximum(base - top, 1)[None, :]
    names = list(ZONES)
    out = np.full((H, W), names.index("vamp"), np.int16)
    for i, (u0, u1, v0, v1) in enumerate(ZONES.values()):
        out[(u >= u0) & (u < u1) & (v >= v0) & (v < v1)] = i
    out[~upper] = -1
    return out


def _pieces(t: T.Trace, ras: np.ndarray, upper: np.ndarray, zones: np.ndarray, marked: np.ndarray | None = None
            ) -> list[_Piece]:
    """The traced colour regions on the upper, piece by piece, each labelled with the part it mostly lies in.
    A piece belongs to a part (rather than being a mark on it) when it is the upper's base colour, when it meets
    the outline or the sole along a quarter of its edge or more (a heel counter, a toe cap, a mudguard, an
    eyestay along the top), or when it is large and not long and thin; never when it is a stripe of a set
    (`marked`), which often runs from the lacing down to the sole. Nothing is cut: a piece keeps its shape."""
    import cv2
    names = list(ZONES)
    area = max(int(upper.sum()), 1)
    outside = cv2.dilate((~upper).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    zone_area = {n: max(int((zones == i).sum()), 1) for i, n in enumerate(names)}
    out = []
    for idx, r in enumerate(t.regions):
        if r.part not in ("silhouette", "upper"):
            continue
        n, labels, stats, _ = cv2.connectedComponentsWithStats(((ras == idx) & upper).astype(np.uint8), 8)
        for i in range(1, n):
            a = int(stats[i, cv2.CC_STAT_AREA])
            if a < 0.002 * area:
                continue
            px = labels == i
            label = names[int(np.bincount(zones[px], minlength=len(names)).argmax())]
            if idx == 0:
                out.append(_Piece(idx, px, "upper", True))
                continue
            edge = px & ~(cv2.erode(px.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
            contact = float((edge & outside).sum()) / max(int(edge.sum()), 1)
            ys, xs = np.nonzero(px)
            _, (w, h), _ = cv2.minAreaRect(np.stack([xs, ys], -1).astype(np.float32))
            long_thin = max(w, h) + 1 >= 2.5 * (min(w, h) + 1)
            big = a >= 0.4 * zone_area[label] and not long_thin
            stripe = marked is not None and marked[px].mean() > 0.5
            out.append(_Piece(idx, px, label, (contact >= 0.25 or big) and not stripe))
    return out


def _parts(t: T.Trace, f: _Frame, ras: np.ndarray, sole: np.ndarray, band: np.ndarray, band_idx: int,
           marked: np.ndarray | None = None) -> tuple[list[Part], list[_Piece], dict[int, str]]:
    """Each part of the shoe from the traced colour regions: its colour is that of the part piece that covers
    most of where the part sits. When that piece is labelled with the part, the part takes its outline (all its
    pieces so labelled, in that colour); when it is another's (a heel counter reaching into the quarter, or the
    upper's base colour), the part is `within` that one. A part with too little of the shoe where it sits was
    not seen, and takes the colour of the part it joins. The sole: its pieces told apart by height, the lowest
    colour the outsole. Returns the parts, the upper's pieces and each sole region's label."""
    shoe = ras >= 0
    upper = shoe & (sole == 0)
    zones = _zone_map(f, upper)
    pieces = _pieces(t, ras, upper, zones, marked)
    main_color = t.regions[0].color
    area = int(upper.sum())
    parts: list[Part] = []
    for i, name in enumerate(ZONES):
        zone = zones == i
        n = int(zone.sum())
        if n < max(20, 0.01 * area):
            parts.append(Part(name, _inferred(parts, name, main_color), False))
            continue
        cover = [(int((p.pixels & zone).sum()), k) for k, p in enumerate(pieces) if p.part]
        if not cover or max(cover)[0] == 0:
            parts.append(Part(name, main_color, True, [], "upper"))
            continue
        top = pieces[max(cover)[1]]
        color = t.regions[top.idx].color
        if top.label == name and top.idx != 0:
            own = np.zeros_like(upper)
            for p in pieces:
                if p.part and p.label == name and p.idx == top.idx:
                    own |= p.pixels
            parts.append(Part(name, color, True, _outlines(f, own)))
        else:
            parts.append(Part(name, color, True, [], top.label))
    # the sole
    sole_labels: dict[int, str] = {}
    ids = [i for i, r in enumerate(t.regions) if r.part == "sole" and (shoe & (ras == i)).sum() >= 0.1 * max(sole.sum(), 1)]
    if sole.sum() >= 20 and (ids or band_idx >= 0):
        height = {i: float(np.nonzero(ras == i)[0].mean()) for i in ids}
        low = max(height, key=height.get) if height else -1
        if band_idx >= 0:          # a midsole in its own colour above the outsole
            sole_labels = {i: "outsole" for i in ids}
            sole_labels[band_idx] = "midsole"
        else:                      # the lowest colour is the outsole; any other, of a colour of its own, the midsole
            for i in ids:
                own = i == low or T.delta_e(t.regions[i].lab, t.regions[low].lab) >= 10
                sole_labels[i] = "outsole" if i == low else "midsole" if own else "outsole"
        for name in ("midsole", "outsole"):
            sel = [i for i, lab in sole_labels.items() if lab == name]
            if not sel:
                parts.append(Part(name, t.regions[low].color if low >= 0 else main_color, True, [], "outsole"))
                continue
            px = (band > 0) if name == "midsole" and band_idx >= 0 else np.isin(ras, sel) & (sole > 0)
            biggest = max(sel, key=lambda i: int((ras == i).sum()))
            parts.append(Part(name, t.regions[biggest].color, True, _outlines(f, px)))
    else:
        for name in ("midsole", "outsole"):
            parts.append(Part(name, main_color, False))
    return parts, pieces, sole_labels


def _inferred(parts: list[Part], name: str, main: str) -> str:
    """A part not seen in the photo takes the colour of the part it joins."""
    joins = {"tongue": "vamp", "collar": "quarter", "heel_counter": "quarter", "toe_cap": "vamp"}
    for p in parts:
        if p.name == joins.get(name) and p.measured:
            return p.color
    return main


def _angle(du_cm: float, dh: float) -> float:
    a = math.degrees(math.atan2(dh, du_cm))
    if a > 90:
        a -= 180
    elif a <= -90:
        a += 180
    return round(a, 1)


def _found(f: _Frame, idx: int, color: str, px: np.ndarray, a: int, cent) -> dict:
    """One piece of a traced colour on the upper: where it is, its size, how much of its box it fills, its angle."""
    import cv2
    (cu, ch), = f.uh([np.asarray(cent) + 0.5])
    ys, xs = np.nonzero(px)
    (_, _), (w, h), _ = cv2.minAreaRect(np.stack([xs, ys], -1).astype(np.float32))
    pts = np.stack([xs, ys], -1).astype(np.float64)
    centred = pts - pts.mean(axis=0)
    evals, evecs = np.linalg.eigh(np.cov(centred.T))
    d = evecs[:, -1]
    length, width = (max(w, h) + 1) * f.cm, (min(w, h) + 1) * f.cm
    return dict(idx=idx, color=color, u=float(cu), h=float(ch), length=length, width=width,
                fill=a / ((max(w, h) + 1) * (min(w, h) + 1)), angle=_angle(-d[0], -d[1]), area=int(a),
                path=_outlines(f, px), px=px)


STRIPE_SET = (2, 4)          # a stripe set has this many stripes, at fewest and most
STRIPE_ZONE = (0.15, 0.75)   # ... each with its middle on the quarter or midfoot (u from the heel)
STRIPE_MAX = 0.06            # ... each at most this share of the upper
STRIPE_BELOW_TOP_CM = 1.5    # ... its middle at least this far below the top edge (laces and eyestays lie along it)


def _parallel(a: float, b: float, tol: float = 15.0) -> bool:
    return abs(((a - b + 90) % 180) - 90) < tol


def _evenly_spaced(group: list[dict]) -> bool:
    """Side by side and evenly spaced: the middles, measured across the set's angle, apart by gaps of about one
    size, none of them overlapping, and the stripes of about one length."""
    a = math.radians(float(np.median([g["angle"] for g in group])))
    across = sorted(-math.sin(a) * g["u"] * LENGTH + math.cos(a) * g["h"] for g in group)
    gaps = np.diff(across)
    lengths = [g["length"] for g in group]
    return (bool(gaps.min() >= 0.3) and float(gaps.max()) <= 3.5 and max(lengths) <= 2.5 * min(lengths)
            and (len(gaps) < 2 or float(np.std(gaps)) <= 0.35 * float(np.mean(gaps))))


def _stripe_sets(t: T.Trace, f: _Frame, ras: np.ndarray, sole: np.ndarray, top_at) -> list[list[dict]]:
    """The stripe sets: in one traced colour, two to four long pieces side by side at one angle and evenly spaced,
    each small beside the upper, on the quarter or midfoot and reaching below the lacing. Thin, tapered stripes
    with soft edges fill little of their box, and one running down to the sole meets the outline: neither stops
    them being a set. Found before the laces, so a stripe's colour is never taken for the laces'."""
    import cv2
    upper = (ras >= 0) & (sole == 0)
    area = max(int(upper.sum()), 1)
    sets = []
    for idx, r in enumerate(t.regions):
        if idx == 0 or r.part != "upper":
            continue
        n, labels, stats, cent = cv2.connectedComponentsWithStats(((ras == idx) & upper).astype(np.uint8), 8)
        cand = []
        for i in range(1, n):
            a = int(stats[i, cv2.CC_STAT_AREA])
            if a < 0.002 * area or a > STRIPE_MAX * area:
                continue
            m = _found(f, idx, r.color, labels == i, a, cent[i])
            if (STRIPE_ZONE[0] <= m["u"] <= STRIPE_ZONE[1] and m["length"] >= 1.2 and m["length"] >= 2.0 * m["width"]
                    and top_at(m["u"]) - m["h"] >= STRIPE_BELOW_TOP_CM):
                cand.append(m)
        best: list[dict] = []
        for m in cand:
            group = [s for s in cand if _parallel(s["angle"], m["angle"])]
            if STRIPE_SET[0] <= len(group) <= STRIPE_SET[1] and len(group) > len(best) and _evenly_spaced(group):
                best = group
        if best:
            sets.append(sorted(best, key=lambda g: g["u"]))
    return sets


def _away(v: _View | None, marked: np.ndarray) -> np.ndarray | None:
    """The stripe sets' pixels at the detail view's size, a little wider (their soft edges), or None."""
    import cv2
    if v is None or not marked.any():
        return None
    H, W = v.mask.shape
    m = cv2.resize(marked.astype(np.uint8), (W, H), interpolation=cv2.INTER_NEAREST)
    k = max(3, int(0.3 / v.f.cm) | 1)
    return cv2.dilate(m, np.ones((k, k), np.uint8)) > 0


def _at(f: _Frame, u: float, h: float, shape) -> tuple[int, int]:
    """The pixel (row, column) at (u, cm), kept inside an image of `shape`."""
    x, y = f.x(u), f.y_ground - h / f.cm
    return int(min(shape[0] - 1, max(0, y))), int(min(shape[1] - 1, max(0, x)))


def _marks(t: T.Trace, f: _Frame, ras: np.ndarray, sole: np.ndarray, taken: np.ndarray,
           skip: list[tuple[float, float]], laces: Row | None, sets: list[list[dict]] = ()) -> list[Mark]:
    """The marks on the upper: the stripe sets found first (`sets`), then the pieces of the trace's colours that
    are not the upper's own and not a part's, grouped into stripe sets and text blocks, the rest told apart by
    shape. Laces, eyelets and stitching found by the detail pass are not marks (a lace the detail pass missed, in
    the laces' colour by the row, neither)."""
    import cv2
    upper = (ras >= 0) & (sole == 0)
    area = max(int(upper.sum()), 1)
    in_set = np.zeros(ras.shape, bool)
    for group in sets:
        for g in group:
            in_set |= g["px"]
    found = []
    for idx, r in enumerate(t.regions):
        if idx == 0 or r.part != "upper":
            continue
        n, labels, stats, cent = cv2.connectedComponentsWithStats(((ras == idx) & upper).astype(np.uint8), 8)
        for i in range(1, n):
            a = stats[i, cv2.CC_STAT_AREA]
            if a < 0.002 * area or taken[labels == i].mean() > 0.5 or in_set[labels == i].mean() > 0.5:
                continue
            (cu, ch), = f.uh([cent[i] + 0.5])
            if any(abs(cu - su) * LENGTH < 0.8 and abs(ch - sh) < 0.8 for su, sh in skip):
                continue
            if laces and T.delta_e(T.to_lab(_rgb(r.color)), T.to_lab(_rgb(laces.color))) < 18:
                lu, lh = np.array(laces.points).T
                reach = 1.5 * laces.spacing_cm / LENGTH
                if lu.min() - reach <= cu <= lu.max() + reach and abs(ch - np.interp(cu, lu, lh)) < 2.0:
                    continue
            found.append(_found(f, idx, r.color, labels == i, a, cent[i]))
    marks: list[Mark] = [_mark("stripes", group) for group in sets]
    left = list(found)
    # stripe sets: two or more straight bands of one colour, side by side at one angle
    straight = [m for m in left if m["length"] / max(m["width"], 1e-6) >= 2.5 and m["fill"] >= 0.6]
    while straight:
        m = straight[0]
        group = [s for s in straight if s["idx"] == m["idx"] and abs(((s["angle"] - m["angle"] + 90) % 180) - 90) < 15]
        straight = [s for s in straight if s not in group]
        left = [s for s in left if s not in group]
        marks.append(_mark("stripes", group))
    # text: three or more small pieces of one colour along a line
    small = [m for m in left if m["area"] < 0.005 * area and m["length"] < 1.6]
    for idx in {m["idx"] for m in small}:
        group = [m for m in small if m["idx"] == idx]
        if len(group) >= 3:
            us, hs = [g["u"] * LENGTH for g in group], [g["h"] for g in group]
            if max(us) - min(us) >= 2 * max(max(hs) - min(hs), 0.3):
                left = [m for m in left if m not in group]
                marks.append(_mark("text", group))
    for m in left:
        ratio = m["length"] / max(m["width"], 1e-6)
        kind = "curve" if ratio >= 2.5 else "panel" if m["area"] >= 0.04 * area else "other"
        marks.append(_mark(kind, [m]))
    return sorted(marks, key=lambda m: -m.u)


def _label(idx: int, piece: list[np.ndarray], ras: np.ndarray, pieces: list[_Piece], sole_labels: dict[int, str],
           sole: np.ndarray) -> str:
    """The part a piece of the traced drawing belongs to: the sole's label when it lies mostly in the sole, else
    the label of the upper's piece it mostly is; the whole shoe's silhouette is the upper's base."""
    if idx == 0:
        return "upper"
    import cv2
    m = np.zeros(ras.shape, np.uint8)
    cv2.fillPoly(m, [np.round(T._sampled(piece[0])).astype(np.int32)], 1)
    m = (m > 0) & (ras == idx)
    if idx in sole_labels and (sole.astype(bool) & m).sum() >= 0.5 * max(int(m.sum()), 1):
        return sole_labels[idx]
    best, label = 0, "upper"
    for p in pieces:
        if p.idx == idx:
            n = int((p.pixels & m).sum())
            if n > best:
                best, label = n, p.label
    return label


def _rgb(color: str) -> np.ndarray:
    return np.array([[[int(color[i:i + 2], 16) for i in (1, 3, 5)]]], np.uint8)


def _mark(kind: str, group: list[dict]) -> Mark:
    w = np.array([g["area"] for g in group], float)
    us = np.array([g["u"] for g in group])
    hs = np.array([g["h"] for g in group])
    if len(group) == 1:
        length, width, angle = group[0]["length"], group[0]["width"], group[0]["angle"]
    else:   # the whole set's size: the smallest box round all its pieces
        import cv2
        pts = np.array([[u * LENGTH, h] for g in group for path in g["path"] for u, h in path], np.float32)
        _, (a, b), _ = cv2.minAreaRect(pts)
        length, width = float(max(a, b)), float(min(a, b))
        angle = float(np.median([g["angle"] for g in group])) if kind == "stripes" else 0.0
    return Mark(kind, group[0]["color"], round(float(np.average(us, weights=w)), 4), round(float(np.average(hs, weights=w)), 3),
                round(length, 2), round(width, 2), round(angle, 1), len(group), [p for g in group for p in g["path"]])


# ------------------------------------------------------------------ the record

def traced_shoe(reading: T.Reading, approach: str | None = None) -> TracedShoe | None:
    """The traced shoe of one photo, from the reading's trace by `approach` (the best one when not given);
    None when no shoe was found."""
    o = reading.oriented
    if o is None or not reading.variants:
        return None
    name = approach or reading.best
    best = next((v for v in reading.variants if v.approach.name == name), reading.variants[0])
    t = best.trace
    ras = T.raster(t)
    shoe = ras >= 0
    if not shoe.any():
        return None
    sole_ids = [i for i, r in enumerate(t.regions) if r.part == "sole"]
    sole = np.isin(ras, sole_ids).astype(np.uint8)
    band, band_idx = _sole_band(t, ras, sole)
    sole = sole | band
    f = _Frame.of(shoe)
    profile = _profile(f, shoe, sole)
    view = _view(o, sole, f)
    bits = _bits(view)
    top_at = lambda u: float(np.interp(u, profile.u, profile.top))   # noqa: E731
    sets = _stripe_sets(t, f, ras, sole, top_at)
    marked = np.zeros(ras.shape, bool)
    for group in sets:
        for g in group:
            marked |= g["px"]
    away = _away(view, marked)
    if away is not None:   # a stripe's end is not a lace, an eyelet or a stitch
        bits = [b for b in bits if not away[_at(view.f, b.u, b.h, away.shape)]]
    pieces, eyelet_row, stitch_row = details(bits, top_at, t.regions[0].lab)
    lace_row = lace_row_of(view, t.regions[0].lab, eyelet_row, away) or pieces
    parts, pieces, sole_labels = _parts(t, f, ras, sole, band, band_idx, marked)
    for name, row in (("laces", lace_row), ("eyelets", eyelet_row), ("stitching", stitch_row)):
        if row:
            near = [b.pts for b in bits if any(abs(b.u - p[0]) < 1e-3 and abs(b.h - p[1]) < 1e-2 for p in row.points)]
            if not near:   # counted along the lacing: a box round each lace's middle
                du = 0.4 * row.spacing_cm / LENGTH
                near = [np.array([[u - du, h - 0.7], [u + du, h - 0.7], [u + du, h + 0.7], [u - du, h + 0.7]])
                        for u, h in row.points]
            parts.append(Part(name, row.color, True, _hull(f, near) if near else []))
    skip = [(p[0], p[1]) for row in (lace_row, eyelet_row, stitch_row) if row for p in row.points]
    taken = np.zeros(ras.shape, bool)
    for p in pieces:
        if p.part:
            taken |= p.pixels
    marks = _marks(t, f, ras, sole, taken, skip, lace_row, sets)
    regions = []
    for idx, r in enumerate(t.regions):
        paths = [[_path(f, p) for p in piece] for piece in r.paths]
        labels = [_label(idx, piece, ras, pieces, sole_labels, sole) for piece in r.paths]
        if idx:   # a piece in a lace, eyelet or stitch colour along that row is that detail
            for name, row in (("laces", lace_row), ("eyelets", eyelet_row), ("stitching", stitch_row)):
                if row is None or T.delta_e(r.lab, T.to_lab(_rgb(row.color))[0, 0]) > 12:
                    continue
                us, hs = [q[0] for q in row.points], [q[1] for q in row.points]
                pad = max(row.spacing_cm, 1.0) / LENGTH
                for k, path in enumerate(paths):
                    mu, mh = (float(v) for v in np.mean(np.asarray(path[0], float), axis=0))
                    if (labels[k] not in ("midsole", "outsole") and min(us) - pad <= mu <= max(us) + pad
                            and abs(mh - float(np.interp(mu, us, hs))) < 1.5):
                        labels[k] = name
        regions.append(Region(r.color, r.part, paths, labels))
    signals = {k: round(float(v), 4) for k, v in reading.gate.signals.items()}
    confidence = best.scores.score * (1.0 if reading.gate.ok else 0.5)
    return TracedShoe(VERSION, t.approach.name, reading.cutout_by, profile, parts, marks, lace_row, eyelet_row, stitch_row,
                      style_hint(profile, lace_row is not None or eyelet_row is not None), round(float(confidence), 3),
                      {"ok": reading.gate.ok, "reasons": list(reading.gate.reasons), "notes": list(reading.gate.notes),
                       "told": dict(reading.gate.told), "signals": signals}, regions)
