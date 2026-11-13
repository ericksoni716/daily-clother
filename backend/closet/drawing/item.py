"""Drawing one item of the closet: what the app calls.

Two ways in. `svg_from_answer` takes the tagger's answer as stored with the
item (its `details` make the drawing this garment and not a generic one);
`svg_from_fields` takes only the coarse fields the closet already stores
(category, colour, pattern, silhouette). Both draw in the owner's style on a
solid fill of the item's colour; a pattern needs the photo and is not drawn.

Neither ever raises. A value the tagger's vocabulary does not know is dropped
and the rest kept; if the drawing still fails, the plainest drawing of the
category is returned. Categories with no shape (bag, belt, hat, scarf, other)
and unknown categories give None: there is nothing to draw.
"""
from __future__ import annotations

import json
import logging
import re

from ..tagger.schema import NAMED_HEX, SILHOUETTE_FIELDS, Details, ItemTags, Silhouette, drawing_for
from .illustrate import Fill, Spec, render

log = logging.getLogger("closet.drawing")

STYLE = "line"   # style B, the owner's choice; the demo closet is drawn in it
TOPS = ("tee", "shirt", "polo", "sweater", "hoodie", "jacket", "coat")
BOTTOMS = ("jeans", "trousers", "shorts")
SHOES = ("sneakers", "boots", "dress_shoes", "sandals")
DRAWN = TOPS + BOTTOMS + SHOES
DEFAULT_HEX = NAMED_HEX["grey"]   # when neither a colour nor a colour word is known

_HEX = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})")
_UID = re.compile(r"[A-Za-z0-9_-]{1,32}")


def svg_from_answer(answer, color_hex: str | None = None, *, uid: str = "a") -> str | None:
    """The drawing for an item from its stored tagger answer (a dict, its JSON text or an `ItemTags`).
    `color_hex` is the item's own colour (measured from the photo or set by the owner); without it the
    answer's colour word is used."""
    try:
        tags = _tags(answer)
        if tags is None:
            return None
        return _draw(tags, _color(color_hex, tags.color), _uid(uid))
    except Exception:   # never raise: the item screen must always open
        log.exception("could not draw an item from its tagger answer")
        return None


def svg_from_fields(category, color_hex: str | None = None, pattern=None, silhouette=None, *,
                    color: str | None = None, uid: str = "a") -> str | None:
    """The drawing for an item that has only the closet's coarse fields. `silhouette` is the item's
    silhouette object (sleeve, neck, top_length, fit, leg, pant_length, shoe_height); `color` is the
    colour word, used when there is no `color_hex`. `pattern` is accepted but not drawn: a pattern
    comes from the photo."""
    try:
        if category not in DRAWN:
            return None
        return _draw(_plain(category, _known_silhouette(silhouette), {}), _color(color_hex, color), _uid(uid))
    except Exception:
        log.exception("could not draw an item from its fields")
        return None


def _tags(answer) -> ItemTags | None:
    if isinstance(answer, ItemTags):
        return answer if answer.category in DRAWN else None
    if isinstance(answer, (str, bytes)):
        try:
            answer = json.loads(answer)
        except ValueError:
            return None
    if not isinstance(answer, dict) or answer.get("category") not in DRAWN:
        return None
    try:
        return ItemTags.model_validate(answer)
    except ValueError:   # an odd value somewhere, or an answer from an older schema: keep what is valid
        word = answer.get("color") if answer.get("color") in NAMED_HEX else "grey"
        return _plain(answer["category"], _known_silhouette(answer.get("silhouette")), _known_details(answer.get("details")), word)


def _known_silhouette(raw) -> dict:
    out = {}
    if isinstance(raw, dict):
        for k in SILHOUETTE_FIELDS:
            try:
                Silhouette.of(**{k: raw.get(k)})
            except Exception:
                continue
            out[k] = raw.get(k)
    return out


def _known_details(raw) -> dict:
    out: dict = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            if not isinstance(k, str) or k not in Details.model_fields:
                continue
            try:
                Details.plain(**{**out, k: v})
            except Exception:
                continue
            out[k] = v
    return out


def _plain(category: str, silhouette: dict, details: dict, color: str = "grey") -> ItemTags:
    """A complete answer saying nothing but the category and what is given."""
    return ItemTags(
        category=category, category_confidence=1, color=color, color_confidence=1, secondary_colors=[],
        pattern="solid", pattern_confidence=1, formality="casual", formality_confidence=1, season="all",
        season_confidence=1, silhouette=Silhouette.of(**silhouette), silhouette_confidence=1,
        details=Details.plain(**details), details_confidence=1, brand=None, size=None, material=None, needs_shot=None)


def _draw(tags: ItemTags, hex_: str, uid: str) -> str:
    try:
        template, params, extras, _ = drawing_for(tags)
        return render(Spec(template, params, Fill("solid", hex_), **extras), STYLE, uid=uid)
    except Exception:
        log.exception("drawing a %s failed; drawing the plainest %s instead", tags.category, tags.category)
        template, params, extras, _ = drawing_for(_plain(tags.category, {}, {}))
        return render(Spec(template, params, Fill("solid", hex_), **extras), STYLE, uid=uid)


def _color(color_hex, word) -> str:
    """A colour safe to write into the drawing: the item's own if it is a hex colour, else its colour word's."""
    if isinstance(color_hex, str) and _HEX.fullmatch(color_hex.strip()):
        return color_hex.strip()
    return NAMED_HEX.get(word, DEFAULT_HEX) if isinstance(word, str) else DEFAULT_HEX


def _uid(uid) -> str:
    return uid if isinstance(uid, str) and _UID.fullmatch(uid) else "a"
