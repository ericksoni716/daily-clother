"""A traced shoe drawn from its side, as the item's drawing (#206, shoe tracing stage 2b).

What `traced.traced_shoe` kept of the owner's photo (`TracedShoe`: its colour pieces, each labelled with the part it
lies in, and its marks) is drawn in the app's style B on the templates' card: the toe to the left at x 40, the
ground at y 330, the bold outline and the thin inner lines, so a traced shoe sits in the closet grid beside the
template drawings. It needs neither OpenCV nor the photo.

The owner's fixes (`items.trace_fixes`) are laid over the trace, never written into it:
    {"parts": {"<part>": "#rrggbb", ...},
     "marks": [{"kind": "stripes", "u": 0.31, "h": 4.2, "hide": true, "move": [dx_cm, dy_cm], "color": "#rrggbb"}]}
A part is named as the trace labels its pieces ("upper" is the shoe's base colour). A mark is known by its kind and
where the trace found it (u, the share of the length from the heel; h, cm above the ground); after a new trace, a fix
goes to the nearest mark of its kind within `NEAR_CM`, and a fix that fits no mark is kept but not drawn.
"""
from __future__ import annotations

import re

import numpy as np

from .illustrate import CARD, INK, luminance, shade
from .trace import CARD_H, CARD_W, INNER_W, OUTLINE_W, SHOE_G, SHOE_L, SHOE_X0, _d
from .traced import LENGTH, TracedShoe

NEAR_CM = 2.5          # a mark fix applies to the nearest mark of its kind at most this far, along and up
MOVE_CM = 4.0          # a mark moves at most this far from where it was traced, each way
TOP_ROOM = 40.0        # the tallest boot still leaves this much of the card above it
_HEX = re.compile(r"#[0-9a-fA-F]{6}")

# the parts in the order the owner sees them, with their names in plain words
PART_WORDS = {
    "upper": "main colour", "toe_cap": "toe cap", "vamp": "front (vamp)", "tongue": "tongue", "quarter": "side (quarter)",
    "heel_counter": "heel", "collar": "collar", "laces": "laces", "eyelets": "eyelets", "stitching": "stitching",
    "midsole": "midsole", "outsole": "outsole",
}
MARK_WORDS = {"stripes": "stripes", "curve": "curved line", "panel": "panel", "text": "lettering", "other": "mark"}


def _hex(value) -> str | None:
    return value.lower() if isinstance(value, str) and _HEX.fullmatch(value) else None


def _inside(pt, poly: np.ndarray) -> bool:
    x, y = pt
    xs, ys = poly[:, 0], poly[:, 1]
    xj, yj = np.roll(xs, 1), np.roll(ys, 1)
    cross = (ys > y) != (yj > y)
    at = (xj - xs) * (y - ys) / np.where(yj - ys == 0, 1e-12, yj - ys) + xs
    return bool(np.count_nonzero(cross & (x < at)) % 2)


def parts(shoe: TracedShoe) -> list[tuple[str, str]]:
    """The parts whose colour the owner can change, each with its traced colour: the shoe's base colour ("upper")
    and every part a traced piece of its own is labelled with (a toe cap, a heel, the sole...), in PART_WORDS order."""
    found: dict[str, tuple[int, str]] = {"upper": (1 << 30, shoe.regions[0].color)} if shoe.regions else {}
    marks = _mark_pieces(shoe)
    for i, r in enumerate(shoe.regions[1:], start=1):
        for k, (piece, label) in enumerate(zip(r.paths, r.labels or ["upper"] * len(r.paths), strict=False)):
            if (i, k) in marks or label == "upper" or not piece:
                continue
            size = len(piece[0])
            if label not in found or found[label][0] < size:
                found[label] = (size, r.color)
    return [(name, found[name][1]) for name in PART_WORDS if name in found]


def _mark_pieces(shoe: TracedShoe) -> set[tuple[int, int]]:
    """The traced pieces (region, piece) that are a mark's: in the mark's colour, their middle inside its outline.
    They are drawn with the mark, so that removing or moving it takes them along."""
    out = set()
    outlines = [(m.color, np.asarray(p, float)) for m in shoe.marks for p in m.path if len(p) >= 3]
    for i, r in enumerate(shoe.regions):
        if i == 0 or r.part != "upper":
            continue
        for k, piece in enumerate(r.paths):
            if not piece or len(piece[0]) < 3:
                continue
            mid = np.asarray(piece[0], float).mean(axis=0)
            if any(c == r.color and _inside(mid, poly) for c, poly in outlines):
                out.add((i, k))
    return out


def mark_fixes(shoe: TracedShoe, fixes: dict | None) -> list[dict | None]:
    """For each of the trace's marks, the owner's fix that applies to it (or None): the nearest fix of its kind
    within NEAR_CM of where it was traced, each fix to one mark at most."""
    out: list[dict | None] = [None] * len(shoe.marks)
    wanted = [f for f in ((fixes or {}).get("marks") or []) if isinstance(f, dict)]
    pairs = []
    for fi, f in enumerate(wanted):
        try:
            fu, fh = float(f["u"]), float(f["h"])
        except (KeyError, TypeError, ValueError):
            continue
        for mi, m in enumerate(shoe.marks):
            if m.kind != f.get("kind"):
                continue
            du, dh = abs(m.u - fu) * LENGTH, abs(m.h - fh)
            if du <= NEAR_CM and dh <= NEAR_CM:
                pairs.append((du * du + dh * dh, fi, mi))
    used: set[int] = set()
    for _, fi, mi in sorted(pairs):
        if fi in used or out[mi] is not None:
            continue
        used.add(fi)
        out[mi] = wanted[fi]
    return out


def _move(fix: dict | None) -> tuple[float, float]:
    try:
        dx, dy = (float(v) for v in (fix or {}).get("move") or (0, 0))
    except (TypeError, ValueError):
        return 0.0, 0.0
    return float(np.clip(dx, -MOVE_CM, MOVE_CM)), float(np.clip(dy, -MOVE_CM, MOVE_CM))


def drawing(shoe: TracedShoe, fixes: dict | None = None, uid: str = "s") -> str:
    """The traced shoe from its side, in style B on the card, with the owner's fixes laid over it."""
    colors = {k: c for k, v in ((fixes or {}).get("parts") or {}).items() if (c := _hex(v))}
    tallest = max(shoe.profile.top) if shoe.profile.top else 10.0
    s = min(SHOE_L / LENGTH, (SHOE_G - TOP_ROOM) / max(tallest, 1.0))
    x0 = SHOE_X0 + (SHOE_L - LENGTH * s) / 2

    def px(path, dx_cm: float = 0.0, dy_cm: float = 0.0) -> np.ndarray:
        a = np.asarray(path, float).reshape(-1, 2)
        return np.stack([x0 + (1 - a[:, 0]) * LENGTH * s - dx_cm * s, SHOE_G - (a[:, 1] + dy_cm) * s], -1)

    def d(piece, dx_cm: float = 0.0, dy_cm: float = 0.0) -> str:
        outlines = [px(p, dx_cm, dy_cm) for p in piece if len(p) >= 3]
        return _d(outlines, 1.0, 0.0, 0.0) if outlines else ""

    base = colors.get("upper") or shoe.regions[0].color
    inner = shade(base, 0.42) if luminance(base) < 0.3 else INK
    sil = "".join(d(p) for p in shoe.regions[0].paths)
    marks = _mark_pieces(shoe)
    fills, lines = [f'<path d="{sil}" fill="{base}" fill-rule="evenodd"/>'], []
    for i, r in enumerate(shoe.regions[1:], start=1):
        labels = r.labels or ["upper"] * len(r.paths)
        for k, piece in enumerate(r.paths):
            if (i, k) in marks:
                continue
            path = d(piece)
            if not path:
                continue
            label = labels[k] if k < len(labels) else "upper"
            color = colors.get(label) if label != "upper" else None
            fills.append(f'<path d="{path}" fill="{color or r.color}" fill-rule="evenodd"/>')
            lines.append(f'<path d="{path}" fill="none" stroke="{inner}" stroke-width="{INNER_W}" stroke-linejoin="round" opacity=".95"/>')
    for m, fix in zip(shoe.marks, mark_fixes(shoe, fixes), strict=True):
        if fix and fix.get("hide"):
            continue
        dx, dy = _move(fix)
        path = d(m.path, dx, dy)
        if not path:
            continue
        fills.append(f'<path d="{path}" fill="{_hex((fix or {}).get("color")) or m.color}" fill-rule="evenodd"/>')
        lines.append(f'<path d="{path}" fill="none" stroke="{inner}" stroke-width="{INNER_W}" stroke-linejoin="round" opacity=".95"/>')
    clip = f"traced-{uid}"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CARD_W} {CARD_H}" width="{CARD_W}" height="{CARD_H}">'
            f'<defs><clipPath id="{clip}"><path d="{sil}" fill-rule="evenodd"/></clipPath></defs>'
            f'<rect width="{CARD_W}" height="{CARD_H}" rx="18" fill="{CARD}"/>'
            f'<g clip-path="url(#{clip})">{"".join(fills)}{"".join(lines)}</g>'
            f'<path d="{sil}" fill="none" stroke="{INK}" stroke-width="{OUTLINE_W}" stroke-linejoin="round"/></svg>')
