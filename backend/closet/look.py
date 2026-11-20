"""A garment's look, read from one place.

The owner chose the source of truth (docs/DECISIONS.md, "The item page consolidated"): the description the drawing
was made from, with the owner's corrections folded over it. That is `illustrations.drawn_answer`: Claude's answer
(or, for an item Claude never described, a plain one made from the item's own fields), with the owner's fields
(`source[field] == "user"`), their coarse shape (`items.silhouette`, when theirs), their details (`own_details`) and
their cloth (`own_cloth`) laid over it.

Everything that tells how a garment looks reads it through here: the item page (its summary line, `as_worn` and the
shape in its JSON), the details one by one, the review queue, corrections by sentence, and the rows the outfit
engine, the stylist, gaps and trips are given (`today.cloth`). So a word on a screen or in a prompt can never say
something the drawing does not show, and a correction changes the drawing and every word together.

`shape(row)` is the look in the closet's small coarse vocabulary (`vocab.SILHOUETTE`: sleeve, neck, top length,
fit, leg, trouser length, shoe height), read the way the drawing reads the answer (`tagger.schema.drawing_for`): the
details decide, and the coarse shape fills in what they leave unsaid. A part neither says is left out.
"""
from __future__ import annotations

import json
import logging

from . import details as owned_details
from . import illustrations, vocab
from .tagger.schema import Details

log = logging.getLogger("closet.look")

# the details that say each coarse part, and what each of their values is in the coarse words; a value not listed
# (or "na", "none", "regular") leaves the part to the coarse shape, as the drawing does
SLEEVE = {"sleeveless": "none", "short": "short", "elbow": "short", "three_quarter": "long", "long": "long"}
NECKLINE = {"crew": "crew", "scoop": "crew", "boat": "crew", "henley": "crew", "v_neck": "v", "mock": "turtle",
            "turtleneck": "turtle", "rollneck": "turtle", "hood": "hood", "polo_collar": "collar", "shawl": "collar"}
FIT = {"slim": "slim", "tailored": "slim", "relaxed": "regular", "boxy": "oversized", "oversized": "oversized"}
TOP_LENGTH = {"cropped": "cropped", "longline": "long"}
LEG = {"skinny": "tapered", "slim": "tapered", "tapered": "tapered", "straight": "straight", "relaxed": "wide",
       "wide": "wide", "bootcut": "wide", "flare": "wide", "barrel": "wide"}
PANT_LENGTH = {"cropped": "ankle", "no_break": "full", "slight": "full", "full": "full", "stacked": "full"}
SHOE_STYLE_HEIGHT = {"high_top": "high", "boot": "high", "chelsea_boot": "high", "low_sneaker": "low", "runner": "low",
                     "slip_on": "low", "loafer": "low", "derby": "low", "oxford": "low", "sandal": "low"}
FOOTWEAR_HEIGHT = {"no_show": "low", "low": "low", "high": "high", "ankle_boot": "high", "boot_6in": "high",
                   "boot_8in_plus": "high", "knee": "high"}
# which details decide each part, for telling whose word a part is (the owner's details, or Claude's)
DECIDED_BY = {"sleeve": ("sleeve_length",), "neck": ("collar", "neckline"), "fit": ("fit_detail",),
              "top_length": ("fit_detail",), "leg": ("leg_shape",), "pant_length": ("trouser_break",),
              "shoe_height": ("shoe_style", "footwear_height")}


def _json(text, default):
    try:
        return json.loads(text) if isinstance(text, str) and text else default
    except ValueError:
        return default


def answer(row) -> dict | None:
    """The description the drawing is made from, with the owner's corrections over it: `illustrations.drawn_answer`,
    or for an item never described and never corrected, the plain answer its own fields make. None when there is
    nothing to read (an accessory with no answer, or an answer that cannot be read)."""
    try:
        row = _full(row)
        found = illustrations.drawn_answer(row)
        if found is None:
            found = owned_details.plain_answer(row["category"], _json(row["silhouette"], {}), row["color"], row["pattern"])
    except Exception:   # an answer that cannot be read is nothing known, never a failed page
        log.exception("reading an item's look failed")
        return None
    return found if isinstance(found, dict) else None


# the columns the look is read from; a row made by hand (a test's, a rule's) may leave some out
COLUMNS = ("tag_answer", "own_details", "own_cloth", "source", "silhouette", "category", "color", "pattern")


def _full(row):
    keys = row.keys()
    missing = [k for k in COLUMNS if k not in keys]
    return {**dict(row), **dict.fromkeys(missing)} if missing else row


def details(row) -> dict:
    """The details as drawn: Claude's, the owner's laid over them (the plain details when there is no answer)."""
    found = (answer(row) or {}).get("details")
    return found if isinstance(found, dict) else Details.plain().model_dump(mode="json")


def _told(value, words: dict):
    return words.get(value) if isinstance(value, str) else None


def shape_of(found: dict | None) -> dict:
    """The coarse shape of an answer as drawn, in `vocab.SILHOUETTE` words: the details decide, the answer's coarse
    shape fills in what they leave unsaid; parts neither says are left out."""
    if not isinstance(found, dict):
        return {}
    coarse = found.get("silhouette") if isinstance(found.get("silhouette"), dict) else {}
    d = found.get("details") if isinstance(found.get("details"), dict) else {}
    collar = d.get("collar")
    told = {
        "sleeve": _told(d.get("sleeve_length"), SLEEVE),
        "neck": "collar" if isinstance(collar, str) and collar not in ("none", "") and collar in _COLLARS
        else _told(d.get("neckline"), NECKLINE),
        "fit": _told(d.get("fit_detail"), FIT),
        "top_length": _told(d.get("fit_detail"), TOP_LENGTH),
        "leg": _told(d.get("leg_shape"), LEG),
        "pant_length": _told(d.get("trouser_break"), PANT_LENGTH),
        "shoe_height": _told(d.get("shoe_style"), SHOE_STYLE_HEIGHT) or _told(d.get("footwear_height"), FOOTWEAR_HEIGHT),
    }
    out = {}
    for part, allowed in vocab.SILHOUETTE.items():
        value = told[part] or coarse.get(part)
        if value in allowed:
            out[part] = value
    return out


def shape(row) -> dict:
    """The item's coarse shape as its drawing shows it (`shape_of` its look)."""
    return shape_of(answer(row))


def owner_parts(row) -> set[str]:
    """The parts of the shape that are the owner's word: decided by a detail they set, or their own coarse shape."""
    row = _full(row)
    own = owned_details.own(row)
    source = _json(row["source"], {})
    theirs = set(_json(row["silhouette"], {})) if isinstance(source, dict) and source.get("silhouette") == "user" else set()
    shown = shape(row)
    return {p for p in shown if p in theirs or any(n in own for n in DECIDED_BY[p])}


def _collars() -> frozenset:
    from typing import get_args

    from .tagger.schema import Collar
    return frozenset(v for v in get_args(Collar) if v != "none")


_COLLARS = _collars()
