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

VERSION = 1                  # raised whenever a field changes meaning; older records are read, newer ones refused
LENGTH = frontshoe.LENGTH
PROFILE_N = 41               # the side profile is sampled at this many even steps from heel to toe
DETAIL_PX = 1200             # the detail pass (laces, eyelets, stitching) looks at the shoe this long, at most
DETAIL_DE = 14.0             # a detail differs this much in colour from the shoe just round it

# Where each part of the upper sits on a side view: (u from, u to, share of the upper's height from, to), the
# height measured up from the top of the sole to the upper's top edge in that column.
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
    gate: dict                       # {"ok": bool, "reasons": [...], "signals": {...}}
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

def style_hint(p: Profile, laced: bool) -> str:
    """The nearest of `frontshoe.STYLES` to the measured profile: the upper's rise along the length, the sole's
    thickness and the collar's height. A shoe with laces is never a loafer, slip-on or Chelsea boot."""
    mid = [i for i, u in enumerate(p.u) if 0.1 <= u <= 0.9]
    sole = float(np.median([p.sole[i] for i in mid]))
    collar = max(t for u, t in zip(p.u, p.top, strict=True) if u <= 0.3)
    best, best_d = "low_sneaker", math.inf
    for name, (_, sole_t, table, shaft) in frontshoe.STYLES.items():
        if table is None or (laced and name not in LACE_STYLES):
            continue
        rise = np.sqrt(np.mean([(p.top_above_sole(u) - v) ** 2 for u, v in table if 0.05 <= u <= 0.95]))
        want_collar = shaft if shaft else sole_t + frontshoe._interp(table, 0.12)
        d = rise + 0.8 * abs(sole - sole_t) + 0.5 * abs(collar - want_collar)
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


def _bits(o: T.Oriented, sole_work: np.ndarray, f: _Frame) -> list[_Bit]:
    """Small things on the upper that differ from the shoe just round them, seen at up to DETAIL_PX along the
    length, so that laces and eyelets are not lost when the trace keeps only a few colours."""
    import cv2
    rgb, mask = o.full_rgb, o.full_mask
    if rgb is None or mask is None:
        return []
    s_full = rgb.shape[1] / o.rgb.shape[1]
    length_full = (f.x_heel - f.x_toe) * s_full
    s = min(1.0, DETAIL_PX / max(length_full, 1.0))
    size = (max(1, int(round(rgb.shape[1] * s))), max(1, int(round(rgb.shape[0] * s))))
    if s < 1:
        rgb = cv2.resize(rgb, size, interpolation=cv2.INTER_AREA)
        mask = (cv2.resize(mask * 255, size, interpolation=cv2.INTER_LINEAR) > 127).astype(np.uint8)
    hf = f.scaled(size[0] / o.rgb.shape[1])
    sole = cv2.resize(sole_work.astype(np.uint8), size, interpolation=cv2.INTER_NEAREST)
    px_cm = 1 / hf.cm
    upper = (mask > 0) & (sole == 0)
    upper = cv2.erode(upper.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    if upper.sum() < 100:
        return []
    fill = rgb.copy()
    fill[mask == 0] = np.median(rgb[mask > 0], axis=0).astype(np.uint8)
    k = min(255, int(1.2 * px_cm) | 1)
    around = cv2.medianBlur(fill, k) if k >= 3 else fill
    lab, lab_around = T.to_lab(rgb), T.to_lab(around)
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


def _parts(t: T.Trace, f: _Frame, ras: np.ndarray, sole: np.ndarray, band: np.ndarray) -> tuple[list[Part], set[int]]:
    """Each part of the shoe: its colour (the trace's colour that covers most of where it sits), its region,
    and whether it was seen. A part in its own colour takes the outline of that colour block."""
    shoe = ras >= 0
    upper = shoe & (sole == 0)
    H, W = ras.shape
    yy, xx = np.mgrid[0:H, 0:W]
    u = (f.x_heel - (xx + 0.5)) / (f.x_heel - f.x_toe)
    top = np.where(upper.any(axis=0), upper.argmax(axis=0), H)
    base = np.where(upper.any(axis=0), H - 1 - upper[::-1].argmax(axis=0), 0)
    v = (base[None, :] - yy) / np.maximum(base - top, 1)[None, :]
    main_color = t.regions[0].color
    area = int(upper.sum())
    parts, used = [], set()
    for name, (u0, u1, v0, v1) in ZONES.items():
        zone = upper & (u >= u0) & (u < u1) & (v >= v0) & (v < v1)
        n = int(zone.sum())
        if n < max(20, 0.01 * area):
            parts.append(Part(name, _inferred(parts, name, main_color), False))
            continue
        idx = np.bincount(ras[zone]).argmax()
        region = zone
        if idx != 0 and t.regions[idx].part == "upper":
            block = upper & (ras == idx)
            if (block & zone).sum() >= 0.6 * block.sum():
                region = block
                used.add(int(idx))
        parts.append(Part(name, t.regions[idx].color, True, _outlines(f, region)))
    sole_ids = [i for i, r in enumerate(t.regions) if r.part == "sole"]
    if sole.sum() >= 20 and sole_ids:
        if band.any():   # a midsole in its own colour above the outsole
            low, high = (sole > 0) & (band == 0), band > 0
        else:            # one band of sole: its top part is the midsole, the bottom 30% the outsole
            run = np.cumsum(sole[::-1], axis=0)[::-1]
            total = sole.sum(axis=0)[None, :]
            low = (sole > 0) & (run <= np.maximum(0.3 * total, 1))
            high = (sole > 0) & ~low
        for name, sel in (("midsole", high), ("outsole", low)):
            if sel.sum() < 10:
                sel = sole > 0
            idx = np.bincount(ras[sel & shoe]).argmax() if (sel & shoe).any() else sole_ids[0]
            parts.append(Part(name, t.regions[idx].color, True, _outlines(f, sel)))
    else:
        for name in ("midsole", "outsole"):
            parts.append(Part(name, main_color, False))
    return parts, used


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


def _marks(t: T.Trace, f: _Frame, ras: np.ndarray, sole: np.ndarray, used: set[int],
           skip: list[tuple[float, float]], laces: Row | None) -> list[Mark]:
    """The marks on the upper: the trace's colours that are not the upper's own and not a part's colour block,
    grouped into stripe sets and text blocks, the rest told apart by shape. Laces, eyelets and stitching found
    by the detail pass are not marks (a lace the detail pass missed, in the laces' colour by the row, neither)."""
    import cv2
    upper = (ras >= 0) & (sole == 0)
    area = max(int(upper.sum()), 1)
    found = []
    for idx, r in enumerate(t.regions):
        if idx == 0 or r.part != "upper" or idx in used:
            continue
        n, labels, stats, cent = cv2.connectedComponentsWithStats(((ras == idx) & upper).astype(np.uint8), 8)
        for i in range(1, n):
            a = stats[i, cv2.CC_STAT_AREA]
            if a < 0.002 * area:
                continue
            (cu, ch), = f.uh([cent[i] + 0.5])
            if any(abs(cu - su) * LENGTH < 0.8 and abs(ch - sh) < 0.8 for su, sh in skip):
                continue
            if laces and T.delta_e(T.to_lab(_rgb(r.color)), T.to_lab(_rgb(laces.color))) < 18:
                lu, lh = np.array(laces.points).T
                reach = 1.5 * laces.spacing_cm / LENGTH
                if lu.min() - reach <= cu <= lu.max() + reach and abs(ch - np.interp(cu, lu, lh)) < 2.0:
                    continue
            ys, xs = np.nonzero(labels == i)
            (_, _), (w, h), _ = cv2.minAreaRect(np.stack([xs, ys], -1).astype(np.float32))
            pts = np.stack([xs, ys], -1).astype(np.float64)
            centred = pts - pts.mean(axis=0)
            evals, evecs = np.linalg.eigh(np.cov(centred.T))
            d = evecs[:, -1]
            length, width = (max(w, h) + 1) * f.cm, (min(w, h) + 1) * f.cm
            found.append(dict(idx=idx, color=r.color, u=float(cu), h=float(ch), length=length, width=width,
                              fill=a / ((max(w, h) + 1) * (min(w, h) + 1)), angle=_angle(-d[0], -d[1]),
                              area=a, path=_outlines(f, labels == i)))
    marks: list[Mark] = []
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
    bits = _bits(o, sole, f)
    lace_row, eyelet_row, stitch_row = details(bits, lambda u: float(np.interp(u, profile.u, profile.top)), t.regions[0].lab)
    parts, used = _parts(t, f, ras, sole, band)
    for name, row in (("laces", lace_row), ("eyelets", eyelet_row), ("stitching", stitch_row)):
        if row:
            near = [b.pts for b in bits if any(abs(b.u - p[0]) < 1e-3 and abs(b.h - p[1]) < 1e-2 for p in row.points)]
            parts.append(Part(name, row.color, True, _hull(f, near) if near else []))
    skip = [(p[0], p[1]) for row in (lace_row, eyelet_row, stitch_row) if row for p in row.points]
    marks = _marks(t, f, ras, sole, used, skip, lace_row)
    regions = []
    for r in t.regions:
        paths = [[_path(f, p) for p in piece] for piece in r.paths]
        regions.append(Region(r.color, r.part, paths))
    signals = {k: round(float(v), 4) for k, v in reading.gate.signals.items()}
    confidence = best.scores.score * (1.0 if reading.gate.ok else 0.5)
    return TracedShoe(VERSION, t.approach.name, reading.cutout_by, profile, parts, marks, lace_row, eyelet_row, stitch_row,
                      style_hint(profile, lace_row is not None or eyelet_row is not None), round(float(confidence), 3),
                      {"ok": reading.gate.ok, "reasons": list(reading.gate.reasons), "signals": signals}, regions)
