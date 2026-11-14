"""Drawing one item of the closet: what the app calls.

Two ways in. `svg_from_answer` takes the tagger's answer as stored with the
item (its `details` make the drawing this garment and not a generic one);
`svg_from_fields` takes only the coarse fields the closet already stores
(category, colour, pattern, silhouette). Both draw in the owner's style, on a
solid fill of the item's colour unless a `fill` measured from the item's photo is
given (its stripes, plaid or print: see `closet.drawing.stored`); a top's `graphic`
lifted from its photo (a logo, a chest print) is drawn over it at its place.

Neither ever raises. A value the tagger's vocabulary does not know is dropped
and the rest kept; if the drawing still fails, the plainest drawing of the
category is returned. Accessories (bag, belt, hat, scarf) are drawn from the
taxonomy's accessory id and kind in the answer's details (a cap, beanie or brimmed
hat; a tote, backpack...), and their plainest shape without them. An "other" item is
drawn only when its answer names one of the taxonomy's other accessories (a tie, a
pocket square, gloves, glasses, a watch, socks), each with a shape of its own; any
other "other" item and unknown categories give None: there is nothing to draw.

`drawing_from_answer` and `drawing_from_fields` give the same drawing together
with what it leaves out or shows only roughly, in plain words (a pattern, a
detail drawn as something close, why it fell back to the plainest drawing), for
the item page's "seen but not drawn" list.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from ..tagger import taxonomy
from ..tagger.schema import NAMED_HEX, SILHOUETTE_FIELDS, Details, ItemTags, Silhouette, drawing_for, drawn_words
from .fills import Graphic
from .illustrate import Fill, Spec, render

log = logging.getLogger("closet.drawing")

STYLE = "line"   # style B, the owner's choice; the demo closet is drawn in it
TOPS = ("tee", "shirt", "polo", "sweater", "hoodie", "jacket", "coat")
BOTTOMS = ("jeans", "trousers", "shorts")
SHOES = ("sneakers", "boots", "dress_shoes", "sandals")
ACCESSORIES = ("bag", "belt", "hat", "scarf")
DRAWN = TOPS + BOTTOMS + SHOES + ACCESSORIES
DEFAULT_HEX = NAMED_HEX["grey"]   # when neither a colour nor a colour word is known

_HEX = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})")
_UID = re.compile(r"[A-Za-z0-9_-]{1,32}")

# what the item page lists beside the drawing, in plain words (lower case, as the tagger's own notes are)
PATTERN_WORDS = {"stripe": "stripes", "plaid": "plaid", "floral": "floral print", "camo": "camouflage",
                 "graphic": "graphic print", "other": "pattern"}
DROPPED = "some details Claude gave that the drawing does not know yet"
FELL_BACK = "its details could not be drawn, so it is shown plain"
NOT_MADE = "no drawing could be made of it"


@dataclass(frozen=True)
class Drawing:
    """An item's drawing (None when there is nothing to draw) and, in plain words, what it leaves out or shows roughly."""
    svg: str | None
    not_drawn: tuple[str, ...] = ()


def svg_from_answer(answer, color_hex: str | None = None, *, uid: str = "a") -> str | None:
    """The drawing for an item from its stored tagger answer (a dict, its JSON text or an `ItemTags`).
    `color_hex` is the item's own colour (measured from the photo or set by the owner); without it the
    answer's colour word is used."""
    return drawing_from_answer(answer, color_hex, uid=uid).svg


def svg_from_fields(category, color_hex: str | None = None, pattern=None, silhouette=None, *,
                    color: str | None = None, uid: str = "a") -> str | None:
    """The drawing for an item that has only the closet's coarse fields. `silhouette` is the item's
    silhouette object (sleeve, neck, top_length, fit, leg, pant_length, shoe_height); `color` is the
    colour word, used when there is no `color_hex`. `pattern` is accepted but not drawn: a pattern
    comes from the photo."""
    return drawing_from_fields(category, color_hex, pattern, silhouette, color=color, uid=uid).svg


def drawing_from_answer(answer, color_hex: str | None = None, *, uid: str = "a", fill: Fill | None = None,
                        graphic: Graphic | None = None) -> Drawing:
    """`svg_from_answer`, with what the drawing could not show. `fill` is the item's pattern measured from its
    photo, `graphic` a print lifted from it (drawn on tops only); with either the pattern is drawn and not listed
    as left out."""
    notes: list[str] = []
    try:
        tags = _tags(answer, notes)
        if tags is None or not _drawable(tags):
            return Drawing(None)
        svg, drawn = _draw(tags, _color(color_hex, tags.color), _uid(uid), notes, fill, graphic)
        return Drawing(svg, _notes(([] if drawn else _pattern(tags.pattern)) + notes))
    except Exception:   # never raise: the item screen must always open
        log.exception("could not draw an item from its tagger answer")
        return Drawing(None, _notes(notes + [NOT_MADE]))


def drawing_from_fields(category, color_hex: str | None = None, pattern=None, silhouette=None, *,
                        color: str | None = None, uid: str = "a", fill: Fill | None = None,
                        graphic: Graphic | None = None) -> Drawing:
    """`svg_from_fields`, with what the drawing could not show."""
    notes: list[str] = []
    try:
        if category not in DRAWN:
            return Drawing(None)
        svg, drawn = _draw(_plain(category, _known_silhouette(silhouette), {}), _color(color_hex, color), _uid(uid),
                           notes, fill, graphic)
        return Drawing(svg, _notes(([] if drawn else _pattern(pattern)) + notes))
    except Exception:
        log.exception("could not draw an item from its fields")
        return Drawing(None, _notes(notes + [NOT_MADE]))


def _pattern(pattern) -> list[str]:
    word = PATTERN_WORDS.get(pattern) if isinstance(pattern, str) else None
    return [f"the {word}: the drawing shows only the colour for now"] if word else []


def words_drawn(answer) -> list[str]:
    """The tagger's other_features words that the item's drawing now shows (a loafer's tassels, a footwear id)."""
    try:
        tags = _tags(answer)
        return drawn_words(tags) if tags else []
    except Exception:
        log.exception("could not read which of the tagger's words are drawn")
        return []


def _notes(notes: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(n for n in notes if n))


def _tags(answer, notes: list[str] | None = None) -> ItemTags | None:
    if isinstance(answer, ItemTags):
        return answer if answer.category in DRAWN + ("other",) else None
    if isinstance(answer, (str, bytes)):
        try:
            answer = json.loads(answer)
        except ValueError:
            return None
    if not isinstance(answer, dict) or answer.get("category") not in DRAWN + ("other",):
        return None
    try:
        return ItemTags.model_validate(answer)
    except ValueError:   # an odd value somewhere, or an answer from an older schema: keep what is valid
        word = answer.get("color") if answer.get("color") in NAMED_HEX else "grey"
        silhouette, details = _known_silhouette(answer.get("silhouette")), _known_details(answer.get("details"))
        if notes is not None and (_dropped(answer.get("silhouette"), silhouette) or _dropped(answer.get("details"), details)):
            notes.append(DROPPED)
        return _plain(answer["category"], silhouette, details, word)


def _drawable(tags: ItemTags) -> bool:
    """Whether there is a drawing for the item: every category in DRAWN, and an "other" item only when its answer
    names one of the taxonomy's accessories."""
    return tags.category in DRAWN or taxonomy.accessory_drawing(tags.category, tags.details.accessory) is not None


def _dropped(raw, kept: dict) -> bool:
    """Whether anything with a value was left out of `raw` when only the known parts were kept."""
    return isinstance(raw, dict) and any(v not in (None, "", [], 0, "na", "none", "same", "unknown") and k not in kept
                                         for k, v in raw.items())


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


PATTERN_FAILED = "its pattern could not be drawn, so it is shown in its colour"


def _draw(tags: ItemTags, hex_: str, uid: str, notes: list[str], fill: Fill | None = None,
          graphic: Graphic | None = None) -> tuple[str, bool]:
    """The drawing, and whether the measured pattern (or lifted graphic) is in it. What was drawn only roughly,
    or why it fell back to the plainest drawing, is added to `notes`."""
    graphic = graphic if tags.category in TOPS else None
    if fill is not None or graphic is not None:
        try:
            template, params, extras, approximated = drawing_for(tags)
            if template in ("tie", "socks"):   # the pattern measured from the photo, not the one drawn from the words
                params.pop("pattern", None)
            svg = render(Spec(template, params, fill or Fill("solid", hex_), graphic=graphic, **extras), STYLE, uid=uid)
            notes.extend(approximated)
            return svg, True
        except Exception:   # a pattern must never cost the item its drawing
            log.exception("drawing a %s with its pattern failed; drawing it in its colour", tags.category)
            notes.append(PATTERN_FAILED)
    try:
        template, params, extras, approximated = drawing_for(tags)
        svg = render(Spec(template, params, Fill("solid", hex_), **extras), STYLE, uid=uid)
        notes.extend(approximated)
        # a tie's or socks' stripes, dots...; a colourwork knit's pattern (Fair Isle, argyle...), in the other
        # colours seen: drawn from its tags
        return svg, ((template in ("tie", "socks") and params.get("pattern", "solid") != "solid")
                     or (bool(extras.get("colorwork")) and tags.pattern in ("other", "graphic", "plaid")))
    except Exception:
        log.exception("drawing a %s failed; drawing the plainest %s instead", tags.category, tags.category)
        notes.append(FELL_BACK)
        keep = {"accessory": tags.details.accessory} if tags.category == "other" else {}
        template, params, extras, approximated = drawing_for(_plain(tags.category, {}, keep))
        svg = render(Spec(template, params, Fill("solid", hex_), **extras), STYLE, uid=uid)
        notes.extend(approximated)
        return svg, False


def _color(color_hex, word) -> str:
    """A colour safe to write into the drawing: the item's own if it is a hex colour, else its colour word's."""
    if isinstance(color_hex, str) and _HEX.fullmatch(color_hex.strip()):
        return color_hex.strip()
    return NAMED_HEX.get(word, DEFAULT_HEX) if isinstance(word, str) else DEFAULT_HEX


def _uid(uid) -> str:
    return uid if isinstance(uid, str) and _UID.fullmatch(uid) else "a"
