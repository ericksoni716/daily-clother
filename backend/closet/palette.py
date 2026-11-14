"""A patterned item's colours, from its measured pattern.

Claude often names one colour of a plaid or a stripe. Once the pattern has been measured from the photo
(`patjobs`, kept in `items.pattern_fill`), its colours are known: the stripes' widths, or how much of the
plaid's or print's tile each colour covers. This module:
- measures that palette from the kept pattern (`measured`); in a tile, a colour that is only where two yarns
  cross (a mix lying between two other colours) is shared out to those two, so a plaid gives its yarns;
- names each colour in the app's colour words (`vocab.COLOR`), keeping Claude's word for a colour when it is a
  fair name for it (`named`);
- sets the item's main colour from the largest named colour (`settle`), unless Claude's main colour covers
  nearly as much; the rest are its other colours, shown as swatches on the item page (`shown`).

A colour the owner set is never changed. The colour is still the tagger's side of the item (`source` "ai"), so
describing it again or undoing a change works as before, and the measured palette is laid over Claude's answer
again each time. Needs numpy and Pillow only (no OpenCV), so the item page can read it quickly.
"""
from __future__ import annotations

import base64
import io
import json
import logging

import numpy as np
from PIL import Image

from . import db, vocab
from .tagger.schema import NAMED_HEX

log = logging.getLogger("closet.palette")

OWNER = "user"
MIN_SHARE = 0.04      # a colour covering less than this is left out (a speck of shade, a thread)
MAX_COLOURS = 4       # the main colour and up to three others, as Claude's answer has
KEEP_CLAUDE = 0.75    # Claude's main colour stays main when it covers at least this much of the largest colour
AGREE = 12.0          # Claude's word names a measured colour when it is at most this much further (ΔE) than the nearest word
MIX_TOLERANCE = 10.0  # a colour this close (ΔE) to a blend of two or three others is where they cross
SURE = 0.9            # how sure a measured colour counts as: above the review queue's threshold for colour
TILE_SIDE = 160       # a tile is measured at most this many pixels across
TILE_COLOURS = 16     # the tile is reduced to this many colours before naming them

# each colour word with a few more shades it covers, beside the one it is drawn in (`NAMED_HEX`)
_SHADES = {
    "black": ["#000000", "#2a2a2e"], "white": ["#ffffff", "#e9e8e4"], "grey": ["#55585c", "#b2b4b7"],
    "navy": ["#1c2333", "#2f3f66"], "blue": ["#2a4f8f", "#5b86c5"], "light_blue": ["#c7d8ec", "#8fb0d6"],
    "green": ["#2e5e3a", "#5e9a62"], "olive": ["#545833", "#807f50"], "tan": ["#b39a6a", "#d4bf94"],
    "brown": ["#4a3220", "#8a6440"], "cream": ["#f2ebd9", "#e0d4b4"], "red": ["#cc2a2a", "#9e2a26"],
    "burgundy": ["#5a1e2a", "#7e2c3a"], "pink": ["#f0bcc8", "#d98a9e"], "orange": ["#e88a3a", "#c0601e"],
    "yellow": ["#f0d860", "#d4b030"], "purple": ["#503870", "#8060a8"],
}
WORDS = [w for w in vocab.COLOR if w in NAMED_HEX]   # every word but "multi"


# ------------------------------------------------------------------ colour arithmetic
def _rgb(hexes) -> np.ndarray:
    return np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in hexes], float) / 255


def _hex(rgb) -> str:
    return "#" + "".join(f"{int(round(float(v) * 255)):02x}" for v in np.clip(rgb, 0, 1))


def _lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB (0..1) to CIE Lab (D65)."""
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = _lin(rgb) @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


_PROTO_WORDS = [w for w in WORDS for _ in range(1 + len(_SHADES.get(w, [])))]
_PROTO_LAB = _lab(_rgb([h for w in WORDS for h in [NAMED_HEX[w], *_SHADES.get(w, [])]]))


def _distances(lab: np.ndarray) -> dict[str, float]:
    """How far a colour is from each word (its nearest shade), in ΔE."""
    d = np.linalg.norm(_PROTO_LAB - lab, axis=1)
    out: dict[str, float] = {}
    for w, v in zip(_PROTO_WORDS, d, strict=True):
        out[w] = min(out.get(w, np.inf), float(v))
    return out


# ------------------------------------------------------------------ measuring
def _on_segment(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """Where p is nearest on the line a..b (0 at a, 1 at b) and how far it is from it."""
    ab = b - a
    t = float(np.dot(p - a, ab) / max(float(np.dot(ab, ab)), 1e-9))
    return t, float(np.linalg.norm(a + t * ab - p))


def _delin(c):
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.power(np.clip(c, 0, None), 1 / 2.4) - 0.055)


def _blend(i: int, a: int, b: int, rgb: list, lab: list) -> tuple[float, float] | None:
    """How colour i sits between colours a and b: (where, 0 at a and 1 at b; how far off it is, ΔE), mixed as
    the eye sees it (in Lab: a tile drawn from measured yarns) or as light (a photo blurring two yarns), whichever
    fits better. None when it is not between them."""
    best = None
    t, err = _on_segment(lab[i], lab[a], lab[b])
    if 0.15 <= t <= 0.85:
        best = (t, err)
    la, lb = _lin(rgb[a]), _lin(rgb[b])
    t, _ = _on_segment(_lin(rgb[i]), la, lb)
    if 0.15 <= t <= 0.85:
        err = float(np.linalg.norm(_lab(_delin((1 - t) * la + t * lb)) - lab[i]))
        if best is None or err < best[1]:
            best = (t, err)
    return best


def _within(i: int, a: int, b: int, c: int, lab: list) -> tuple[list[float], float] | None:
    """How colour i sits inside the triangle of colours a, b and c in Lab (where three yarns meet in a blurred
    photo): (how much of each, how far off it is, ΔE). None when it is not well inside."""
    m = np.stack([lab[a] - lab[c], lab[b] - lab[c]], 1)
    (wa, wb), *_ = np.linalg.lstsq(m, lab[i] - lab[c], rcond=None)
    w = [float(wa), float(wb), float(1 - wa - wb)]
    if min(w) < 0.1:
        return None
    return w, float(np.linalg.norm(m @ np.array([wa, wb]) + lab[c] - lab[i]))


def _unmix(colours: list[tuple[np.ndarray, float]]) -> list[tuple[np.ndarray, float]]:
    """Share out each colour that is a blend of two others (where two yarns cross, or the photo blurs their
    edge), or of three, between them, the most clearly blended first. A yarn of its own is never a blend: it
    lies outside the others, not between them."""
    rgb = [c for c, _ in colours]
    share = [s for _, s in colours]
    lab = [_lab(c) for c in rgb]
    alive = set(range(len(rgb)))
    while len(alive) > 2:
        best = None
        for i in alive:
            others = sorted(alive - {i})
            for n, a in enumerate(others):
                for b in others[n + 1:]:
                    found = _blend(i, a, b, rgb, lab)
                    if found is not None and found[1] <= MIX_TOLERANCE and (best is None or found[1] < best[0]):
                        best = (found[1], i, {a: 1 - found[0], b: found[0]})
        if best is None and len(alive) > 3:
            for i in alive:
                others = sorted(alive - {i})
                for n, a in enumerate(others):
                    for k, b in enumerate(others[n + 1:], n + 1):
                        for c in others[k + 1:]:
                            found = _within(i, a, b, c, lab)
                            if found is not None and found[1] <= MIX_TOLERANCE and (best is None or found[1] < best[0]):
                                best = (found[1], i, dict(zip((a, b, c), found[0], strict=True)))
        if best is None:
            break
        _, i, parts = best
        for k, w in parts.items():
            share[k] += share[i] * w
        alive.discard(i)
    return [(rgb[i], share[i]) for i in alive]


def _tile_colours(raw: str) -> list[tuple[np.ndarray, float]]:
    with Image.open(io.BytesIO(base64.b64decode(raw, validate=True))) as im:
        im = im.convert("RGB")
        im.thumbnail((TILE_SIDE, TILE_SIDE))
        q = im.quantize(colors=TILE_COLOURS, method=Image.Quantize.MAXCOVERAGE, kmeans=2)
    pal = q.getpalette() or []
    counts = q.getcolors() or []
    total = sum(n for n, _ in counts) or 1
    return [(np.array(pal[3 * k:3 * k + 3], float) / 255, n / total) for n, k in counts]


def measured(kept: dict) -> list[list]:
    """The colours of a kept pattern with how much of it each covers, largest first: [[hex, share], ...].
    Stripes by the widths of their bands; a tile by its pixels, with blends shared out to the colours they
    are made of. Empty when the pattern says nothing about its colours."""
    if not isinstance(kept, dict):
        return []
    if kept.get("kind") == "stripes":
        widths: dict[str, float] = {}
        for h, f in kept.get("bands") or []:
            widths[h.lower()] = widths.get(h.lower(), 0.0) + float(f)
        colours = [(_rgb([h])[0], f) for h, f in widths.items()]
    elif kept.get("kind") == "tile" and isinstance(kept.get("image"), str):
        colours = _unmix(_tile_colours(kept["image"]))
    else:
        return []
    total = sum(s for _, s in colours) or 1
    return [[_hex(c), round(s / total, 4)] for c, s in sorted(colours, key=lambda x: -x[1])]


def keep(kept: dict | None, pattern: str) -> dict | None:
    """The kept pattern with its colours (`measured`) and the pattern word it was measured as, so colours from
    a plaid are not laid over an item that has since become striped."""
    if not kept:
        return kept
    try:
        colours = measured(kept)
    except (ValueError, TypeError, OSError, Image.DecompressionBombError):
        log.warning("could not read the colours of a measured pattern", exc_info=True)
        colours = []
    return {**kept, "colors": colours, "pattern": pattern}


# ------------------------------------------------------------------ naming
def _json(text, default):
    try:
        return json.loads(text) if text else default
    except ValueError:
        return default


def said(row) -> list[str]:
    """The colour words to keep where they fit: the owner's colour, then Claude's main and other colours."""
    source = _json(row["source"], {})
    answer = _json(row["tag_answer"], {})
    words = [row["color"]] if source.get("color") == OWNER and row["color"] else []
    if isinstance(answer, dict):
        words += [answer.get("color")] + list(answer.get("secondary_colors") or [])
    return [w for w in dict.fromkeys(words) if isinstance(w, str) and w in WORDS]


def named(colours: list[list], words: list[str] | None = None) -> list[dict]:
    """The measured colours in the app's colour words, largest first, each {"color", "hex", "share"} (the hex
    of the largest measured colour given that word). A word in `words` (Claude's) is kept for a colour when it
    is nearly as close as the nearest word; colours covering less than `MIN_SHARE` are left out."""
    words = [w for w in (words or []) if w in WORDS]
    out: dict[str, dict] = {}
    for h, share in colours:
        d = _distances(_lab(_rgb([h])[0]))
        nearest = min(d, key=d.get)
        fits = [w for w in words if d[w] <= d[nearest] + AGREE]
        word = min(fits, key=d.get) if fits else nearest
        if word in out:
            out[word]["share"] += share
        else:
            out[word] = {"color": word, "hex": h, "share": share}
    found = sorted(out.values(), key=lambda c: -c["share"])
    return [{**c, "share": round(c["share"], 4)} for c in found if c["share"] >= MIN_SHARE][:MAX_COLOURS]


def _kept(row) -> dict | None:
    keys = row.keys() if hasattr(row, "keys") else row
    if "pattern_fill" not in keys or not row["pattern_fill"] or row["pattern"] in (None, "solid"):
        return None
    kept = _json(row["pattern_fill"], None)
    if not isinstance(kept, dict) or kept.get("pattern") != row["pattern"] or not kept.get("colors"):
        return None
    return kept


def shown(row) -> list[dict]:
    """The item's measured colours as the item page shows them (empty when its pattern has none measured)."""
    kept = _kept(row)
    if kept is None:
        return []
    try:
        return named(kept["colors"], said(row))
    except (ValueError, TypeError, KeyError, IndexError):
        return []


def main_colour(found: list[dict], claude: str | None) -> dict | None:
    """The item's main colour from its named palette: the largest, unless Claude's main colour covers nearly
    as much (`KEEP_CLAUDE`)."""
    if not found:
        return None
    top = found[0]
    mine = next((c for c in found if c["color"] == claude), None)
    return mine if mine is not None and mine["share"] >= KEEP_CLAUDE * top["share"] else top


def settle(conn, item_id: str) -> bool:
    """Lay the measured palette over the item's colour, inside the caller's transaction: its main colour (and
    the colour's shade) become the palette's, unless the owner set them. True when something changed."""
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        return False
    found = shown(row)
    source = _json(row["source"], {})
    if not found or source.get("color") == OWNER:
        return False
    answer = _json(row["tag_answer"], {})
    main = main_colour(found, answer.get("color") if isinstance(answer, dict) else None)
    confidence = _json(row["confidence"], {})
    sets: dict = {}
    sure = confidence.get("color") if row["color"] == main["color"] and source.get("color") == "ai" else None
    if row["color"] != main["color"] or source.get("color") != "ai" or not isinstance(sure, (int, float)) or sure < SURE:
        sets["color"] = main["color"]
        source["color"] = "ai"
        confidence["color"] = max(SURE, sure) if isinstance(sure, (int, float)) else SURE
    if source.get("color_hex") != OWNER and (row["color_hex"] != main["hex"] or source.get("color_hex") != "ai"):
        sets["color_hex"] = main["hex"]
        source["color_hex"] = "ai"
    if not sets:
        return False
    sets.update(source=json.dumps(source), confidence=json.dumps(confidence), updated_at=db.now())
    conn.execute(f"UPDATE items SET {', '.join(f'{k} = ?' for k in sets)} WHERE id = ?", [*sets.values(), item_id])
    return True
