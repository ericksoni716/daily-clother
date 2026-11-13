"""From an item's cutout to its kept pattern (`items.pattern_fill`, see `closet.drawing.stored`).

One function, `measure`, picks the method for the pattern Claude saw:
- plaid: the repeat found, the crumpled cloth flattened into one straight repeat (each front on its own when
  the two agree), and with landmarks the repeat placed on each front beside the buttons; a plaid with no
  regular repeat (madras) is measured whole and kept as one garment-sized tile;
- stripes: regular stripes folded onto one sharp repeat, or stripes with placed bands (a polo's chest band)
  drawn over a crisp ground, the collar (and, unless the photo shows bands on them, the sleeves) cut from that
  ground; colours corrected from Claude's colour words when it says the item has white or cream;
- a floral, camouflage or other irregular print: pieced together (quilted) from the whole garment.
Anything else, or a measurement that fails, gives None: the item is drawn in its colour.
"""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

from ..drawing.stored import VERSION, tile_text
from . import flatten, plaid, prints, stripes
from .common import garment_mask, lab_to_rgb, quiet

MEASURED = ("plaid", "stripe", "floral", "camo", "other")
TILE_SCALE = 3   # a repeat is kept at three times the photo's detail, so its lines stay crisp when drawn large


def _garment_width(cut: Image.Image) -> int:
    m = garment_mask(cut, thresh=128)
    xs = np.where(m.any(0))[0]
    return int(xs.max() - xs.min()) if len(xs) else cut.width


def _tile(img_rgb: np.ndarray, scale: int = 1) -> str:
    im = Image.fromarray(img_rgb)
    if scale > 1:
        im = im.resize((im.width * scale, im.height * scale), Image.LANCZOS)
    return tile_text(im)


def _plaid(cut, landmarks, log):
    found = plaid.period(cut)
    if found is None:
        log("no regular repeat: measured whole")
        r = plaid.no_repeat(cut, log=log)
        return {"kind": "tile", "image": _tile(r["tile"]), "width_frac": round(float(r["width_frac"]), 4)}
    P, Q = found
    log(f"repeat {P} x {Q} px")
    res = flatten.rectify_fronts(cut, P, Q, log=log)
    if res is None:
        return None
    tile_lab, info = res
    out = {"kind": "tile", "image": _tile(lab_to_rgb(tile_lab), TILE_SCALE),
           "width_frac": round(P / max(1, _garment_width(cut)), 4)}
    if landmarks and landmarks.get("button_line") is not None:
        try:
            _, length_frac, anchor = plaid.placed_from_landmarks(info, P, Q, landmarks)
            left = plaid.match_front(cut, tile_lab, P, Q, anchor, -1)
            right = plaid.match_front(cut, tile_lab, P, Q, anchor, +1)
            if left is not None and 0 < length_frac < 1:
                out.update(length_frac=round(float(length_frac), 4), phase=[round(float(v), 4) for v in left[0]],
                           phase_right=[round(float(v), 4) for v in right[0]] if right is not None else None)
                log(f"placed: left front {left[1]} px, right front {right[1] if right else None} px from a check")
        except (ValueError, IndexError, KeyError, TypeError) as e:   # placement is a bonus: keep the plaid without it
            log(f"could not place the plaid: {type(e).__name__}")
    return out


def _gain_fix(hexes, gain):
    lin = lambda c: np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)  # noqa: E731
    unlin = lambda c: np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.power(np.clip(c, 0, None), 1 / 2.4) - 0.055)  # noqa: E731
    out = {}
    for h in hexes:
        c = np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)]) / 255
        v = np.clip(unlin(lin(c) * np.array(gain)) * 255, 0, 255)
        out[h] = "#" + "".join(f"{int(round(x)):02x}" for x in v)
    return out


def _stripes(cut, words, landmarks, log):
    body = stripes.measure4(cut, log=log)
    if body is None or not body.get("bands"):
        return None
    out = {"kind": "stripes", "orientation": body["orientation"], "trim_bands": None, "sleeves_banded": None}
    ground = stripes.ground_stripes(cut, log=log)
    bands_lab = None
    if ground is not None:
        bands_lab, ground_lab = stripes.band_colours(body["yarns"], ground["hexes"])
    if ground is not None and bands_lab is not None and len(bands_lab):
        log("placed bands over a plain ground")
        bands = stripes.compose_placed(cut, body, ground, log=log)
        trim = list(ground["bands"])
        _, how = stripes.balance_to_words({"yarns": ground["hexes"], "bands": ground["bands"]}, words)
        if how:   # one lighting correction for everything, from the ground's white
            fix = _gain_fix({h for h, _ in bands} | {h for h, _ in trim}, how[2])
            bands = [(fix[h], f) for h, f in bands]
            trim = [(fix[h], f) for h, f in trim]
        out["bands"], out["trim_bands"] = bands, trim
        if landmarks:
            regions = stripes.regions_from_landmarks(cut, landmarks)
            out["sleeves_banded"] = stripes.sleeves_carry_bands(cut, bands_lab, ground_lab, regions, log=log)
    else:
        fixed, _ = stripes.balance_to_words(body, words)
        out["bands"] = fixed["bands"]
    out["bands"] = [[h, round(float(f), 6)] for h, f in out["bands"]]
    if out["trim_bands"]:
        out["trim_bands"] = [[h, round(float(f), 6)] for h, f in out["trim_bands"]]
    return out


def _print(cut, log):
    img, info = prints.quilt_garment(cut)
    log(f"pieced from {info.get('distinct')} places on the garment")
    return {"kind": "tile", "image": tile_text(img), "width_frac": round(img.width / max(1, _garment_width(cut)), 4)}


def measure(cut: Image.Image, pattern: str, words: list[str] | None = None, landmarks: dict | None = None,
            log=quiet) -> dict | None:
    """The kept pattern for an item, or None to draw it in its colour. `pattern` is the item's pattern word
    (stripe, plaid, floral, camo, other), `words` Claude's colour words for it, `landmarks` Claude's points in
    the cutout's own pixels (`closet.tagger.landmarks`), or None."""
    if pattern not in MEASURED:
        return None
    cut = cut.convert("RGBA")
    if pattern == "plaid":
        out = _plaid(cut, landmarks, log)
    elif pattern == "stripe":
        out = _stripes(cut, list(words or []), landmarks, log)
    else:
        out = _print(cut, log)
    if out is not None:
        out["version"] = VERSION
    return out


def see_through_mask(mask: Image.Image) -> float:
    """How much of a cutout's outline the background model left see-through (see `masks.see_through`)."""
    from .masks import see_through
    return see_through(mask)


def combine_masks(a: Image.Image, b: Image.Image) -> Image.Image:
    """Two background models' masks of the same photo, combined: kept where either keeps it."""
    return Image.fromarray(cv2.max(np.asarray(a), np.asarray(b)), "L")
