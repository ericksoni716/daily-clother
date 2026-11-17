"""From an item's cutout to its kept pattern (`items.pattern_fill`, see `closet.drawing.stored`).

One function, `measure`, picks the method for the pattern Claude saw:
- plaid: three ways, each tried when the one before finds nothing, and each kept only when what it rebuilt,
  laid back over the photo, explains the photo. Seen straight on: the repeat found, the crumpled cloth
  flattened into one straight repeat (each front on its own when the two agree). Photographed at
  an angle, turned, over a slope or in soft, low-contrast cloth: the cloth made regular from its own lines first
  (`straighten`), then flattened. With no regular repeat (madras): measured whole and kept as one
  garment-sized tile. With landmarks the repeat is placed on each front beside the buttons. A photo too dark
  or too light for the colour the item is called has its repeat lightened or darkened to that colour
  (`palette.exposure`). A plaid none of the three explains is not drawn as a guess: the item is drawn in its
  colour and says so;
- stripes: regular stripes folded onto one sharp repeat, or stripes with placed bands (a polo's chest band)
  drawn over a crisp ground, the collar (and, unless the photo shows bands on them, the sleeves) cut from that
  ground; colours corrected from Claude's colour words when it says the item has white or cream;
- a floral, camouflage or other irregular print: pieced together (quilted) from the whole garment;
- a graphic (a logo, a chest print) on a top: lifted from the photo with its background made see-through
  (`drawing.fills.extract_graphic`) and kept with its place on the garment; the cloth is drawn in its colour.
Anything else, or a measurement that fails, gives None: the item is drawn in its colour.
"""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

from .. import palette
from ..drawing import fills
from ..drawing.stored import VERSION, graphic_part, tile_text
from . import flatten, plaid, prints, straighten, stripes
from .common import garment_mask, quiet
from .masks import surfaces

MEASURED = ("plaid", "stripe", "floral", "camo", "other", "graphic")
TILE_SCALE = 3   # a repeat is kept at three times the photo's detail, so its lines stay crisp when drawn large
AGREES = 0.5         # a rebuilt repeat is kept when, laid back over the photo, it explains the photo this well
MIN_AREAS = 12       # and, from a straightened photo, when it was measured in at least this many areas
MIN_SHARE = 0.15     # covering at least this share of the garment (its body; sleeves lie at other angles)
MAX_DRIFT = 3.0      # and when flattening straightened cloth moved it by no more than this many repeats: a repeat
#                      far too short can "explain" any bands by sliding along them
WHOLE_AGREES = 0.35  # a plaid measured whole (madras) is kept when its two crossing sequences explain the photo


def _garment_width(cut: Image.Image) -> int:
    m = garment_mask(cut, thresh=128)
    xs = np.where(m.any(0))[0]
    return int(xs.max() - xs.min()) if len(xs) else cut.width


def _tile(img_rgb: np.ndarray, scale: int = 1) -> str:
    im = Image.fromarray(img_rgb)
    if scale > 1:
        im = im.resize((im.width * scale, im.height * scale), Image.LANCZOS)
    return tile_text(im)


def _lit(out: dict | None, tile, scale: int, words, log) -> dict | None:
    """The kept plaid with its tile, made lighter or darker when the photo was too dark or too light for the
    colour the item is called (`palette.exposure`; the first of `words` is the item's main colour). `tile` is
    the repeat in Lab as it was measured (fractions of a level kept, so a dark photo lightened four times over
    does not show the steps between its few dark levels), or RGB pixels."""
    if out is None:
        return None
    if tile.dtype == np.uint8:
        rgb = tile.astype(np.float32) / 255
    else:
        lab = np.ascontiguousarray(tile, np.float32) * (100 / 255, 1, 1) - (0, 128, 128)
        rgb = np.clip(cv2.cvtColor(lab.astype(np.float32), cv2.COLOR_LAB2RGB), 0, 1)
    gain = palette.exposure(Image.fromarray((rgb * 255).round().astype(np.uint8)), words[0] if words else None)
    if gain != 1.0:
        log(f"the photo is too {'dark' if gain > 1 else 'light'} for {words[0]}: the repeat's light is multiplied by {gain}")
        out["lit"] = gain
        lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4) * gain
        rgb = np.clip(np.where(lin <= 0.0031308, 12.92 * lin, 1.055 * np.power(np.clip(lin, 0, None), 1 / 2.4) - 0.055), 0, 1)
    return {**out, "image": _tile((rgb * 255).round().astype(np.uint8), scale)}


def _placed(out, cut, tile_lab, info, P, Q, landmarks, log, soft=False):
    """With Claude's landmarks, the repeat lined up beside the buttons, each front on its own (added to `out`)."""
    if not landmarks or landmarks.get("button_line") is None:
        return
    try:
        _, length_frac, anchor = plaid.placed_from_landmarks(info, P, Q, landmarks)
        left = plaid.match_front(cut, tile_lab, P, Q, anchor, -1, soft=soft)
        right = plaid.match_front(cut, tile_lab, P, Q, anchor, +1, soft=soft)
        if left is not None and 0 < length_frac < 1:
            out.update(length_frac=round(float(length_frac), 4), phase=[round(float(v), 4) for v in left[0]],
                       phase_right=[round(float(v), 4) for v in right[0]] if right is not None else None)
            log(f"placed: left front {left[1]} px, right front {right[1] if right else None} px from a check")
    except (ValueError, IndexError, KeyError, TypeError) as e:   # placement is a bonus: keep the plaid without it
        log(f"could not place the plaid: {type(e).__name__}")


def _moved(landmarks, to_new):
    """Claude's landmarks carried into the straightened picture (None when there are none or they do not fit)."""
    if not landmarks:
        return None
    try:
        out = {}
        for key, v in landmarks.items():
            if isinstance(v, dict) and "x" in v and "y" in v:
                x, y = to_new([[v["x"], v["y"]]])[0]
                out[key] = {**v, "x": float(x), "y": float(y)}
            elif isinstance(v, list) and all(isinstance(b, dict) and "x" in b and "y" in b for b in v):
                pts = to_new([[b["x"], b["y"]] for b in v]) if v else []
                out[key] = [{**b, "x": float(x), "y": float(y)} for b, (x, y) in zip(v, pts, strict=True)]
            else:
                out[key] = v
        return out
    except (ValueError, TypeError, KeyError):
        return None


def _button_x(landmarks):
    """Where the two fronts meet in the picture (the button line's x), or None."""
    try:
        xs = [b["x"] for b in landmarks.get("button_line") or []]
        if len(xs) < 2:
            xs = [landmarks["neck_center"]["x"], landmarks["hem_center"]["x"]]
        return float(np.median(xs))
    except (AttributeError, KeyError, TypeError):
        return None


def _straightened(cut, landmarks, log):
    """A plaid the straight-on measure could not find a repeat in: the cloth made regular from its own lines
    (`straighten`), flattened with the matching meant for soft cloth, and kept only when the rebuilt repeat
    explains the photo. Each kind of surface in the cutout is tried, the patterned one first, so bedding the
    background model kept does not decide. Returns the kept pattern or None."""
    for part in surfaces(cut, log):
        reg = straighten.regular(part, log)
        if reg is None:
            continue
        marks = _moved(landmarks, reg.to_new)
        res = flatten.rectify_fronts(reg.cut, reg.P, reg.Q, log=log, ref_lab=reg.ref, soft=True,
                                     mid=_button_x(marks) if marks else None)
        if res is None:
            continue
        tile_lab, info = res
        agrees, share = flatten.agreement(reg.cut, tile_lab, info, reg.P, reg.Q)
        log(f"the rebuilt repeat ({reg.P} x {reg.Q} px) agrees {agrees:.2f} with the photo over {share:.0%} of the garment")
        if agrees < AGREES or info["areas"] < MIN_AREAS or share < MIN_SHARE:
            continue     # a few patches that happen to match are not the garment's cloth
        if max(info["drift"]) > MAX_DRIFT:
            log(f"the map slides the cloth by {max(info['drift']):.0f} repeats: it follows the bands, it does not flatten them")
            continue
        # the repeat's width on the garment: one repeat at the middle of the cloth, back in the cutout's own pixels
        m = garment_mask(part, thresh=128)
        ys, xs = np.where(m)
        c = np.array([xs.mean(), ys.mean()])
        new = reg.to_new([c, c + (16, 0), c + (0, 16)])
        jac = np.stack([new[1] - new[0], new[2] - new[0]], 1) / 16
        across = float(np.linalg.norm(np.linalg.solve(jac, np.array([reg.P, 0.0]))))
        out = {"kind": "tile", "how": "straightened", "width_frac": round(across / max(1, _garment_width(part)), 4)}
        _placed(out, reg.cut, tile_lab, info, reg.P, reg.Q, marks, log, soft=True)
        return out, tile_lab, TILE_SCALE
    return None


def _plaid(cut, landmarks, words, log):
    return _lit(*_plaid_tile(cut, landmarks, log), words, log)


def _plaid_tile(cut, landmarks, log):
    """(the kept plaid without its tile, the tile's pixels, how much larger to keep them), or (None, None, 1)."""
    found = plaid.period(cut)
    if found is not None:
        P, Q = found
        log(f"repeat {P} x {Q} px")
        res = flatten.rectify_fronts(cut, P, Q, log=log)
        if res is not None:
            tile_lab, info = res
            agrees, share = flatten.agreement(cut, tile_lab, info, P, Q)
            log(f"the rebuilt repeat agrees {agrees:.2f} with the photo over {share:.0%} of the garment")
            if agrees >= AGREES:     # a repeat found by chance in cloth that has none explains nothing: go on
                out = {"kind": "tile", "how": "repeat", "width_frac": round(P / max(1, _garment_width(cut)), 4)}
                _placed(out, cut, tile_lab, info, P, Q, landmarks, log)
                return out, tile_lab, TILE_SCALE
    log("no regular repeat seen straight on: straightening the cloth from its own lines")
    made = _straightened(cut, landmarks, log)
    if made is not None:
        return made
    r = plaid.no_repeat(cut, log=log)
    log(f"no regular repeat: measured whole, which agrees {r['agreement']:.2f} with the photo")
    if r["agreement"] < WHOLE_AGREES:
        return None, None, 1     # neither a repeat nor two crossing sequences of bands explain this photo: say so
    return {"kind": "tile", "how": "whole", "width_frac": round(float(r["width_frac"]), 4)}, r["tile"], 1


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


def _graphic(cut, log):
    """The print lifted from the garment, its box in fractions of the garment (the cutout's opaque part)."""
    a = np.asarray(cut)[..., 3]
    ys, xs = np.where(a > 128)
    if len(xs) == 0:
        return None
    gx0, gy0, gx1, gy1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    g = fills.extract_graphic(cut.crop((gx0, gy0, gx1, gy1)))
    if g is None:
        log("no print found")
        return None
    w, h = gx1 - gx0, gy1 - gy0
    x0, y0, x1, y1 = g.box
    log(f"print lifted: {x1 - x0} x {y1 - y0} px")
    return {"kind": "plain", "graphic": graphic_part(g.image, (x0 / w, y0 / h, x1 / w, y1 / h))}


def measure(cut: Image.Image, pattern: str, words: list[str] | None = None, landmarks: dict | None = None,
            log=quiet) -> dict | None:
    """The kept pattern for an item, or None to draw it in its colour. `pattern` is the item's pattern word
    (stripe, plaid, floral, camo, other), or graphic for a print to lift, `words` Claude's colour words for it, `landmarks` Claude's points in
    the cutout's own pixels (`closet.tagger.landmarks`), or None."""
    if pattern not in MEASURED:
        return None
    cut = cut.convert("RGBA")
    if pattern == "plaid":
        out = _plaid(cut, landmarks, list(words or []), log)
    elif pattern == "stripe":
        out = _stripes(cut, list(words or []), landmarks, log)
    elif pattern == "graphic":
        out = _graphic(cut, log)
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
