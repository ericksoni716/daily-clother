"""The details of an item the owner can set, for each kind of garment, in plain words.

The vocabulary is the tagger's (`tagger/schema.py`, `Details`). The owner's
values are kept apart from Claude's answer (`items.own_details`) and laid over
its details when the item is drawn, so "Describe it again" never undoes them.
Feature flags (a V insert, a toe cap, pleats ...) are offered one by one as
"yes" or "no". The plain words here are the ones the item page, the history and
corrections by sentence show.
"""
from __future__ import annotations

import json
from typing import get_args

from . import vocab
from .drawing.item import BOTTOMS, SHOES, TOPS
from .tagger.schema import Color, Details, Feature, ItemTags, Pattern, Silhouette

FEATURES: tuple[str, ...] = get_args(Feature)
# lists (features, the tagger's own words, a trouser's pockets and wear) are shown, not picked one by one
LISTS = ("features", "other_features", "trouser_pockets", "back_details", "denim_fades", "distressing")
DETAILS: tuple[str, ...] = tuple(n for n in Details.model_fields if n not in LISTS)
PICKABLE: tuple[str, ...] = DETAILS + FEATURES
MAX_BUTTONS = 10
# details that are a count: the most each can be
NUMBERS = {"placket_buttons": MAX_BUTTONS, "eyelets": 10, "inseam": 20}
# details whose choices are offered in words only: each choice draws the same picture
WORDED = ("shade",)
# the item's own fields a correction by sentence may change (silhouette parts as "silhouette.<part>")
FIELDS = ("category", "color", "pattern", "formality", "season")
SHAPES = tuple(f"silhouette.{k}" for k in vocab.SILHOUETTE)

GROUPS = {"shape": "Shape", "neck": "Collar and neck", "front": "Front", "sleeves": "Sleeves and cuffs",
          "pockets": "Pockets", "hem": "Hem", "sole": "Sole and laces", "lacing": "Lacing", "cloth": "Cloth"}
# what can be fixed on each kind of garment, grouped, in the order the item page shows them
BY_KIND: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "top": (
        ("neck", ("neckline", "collar", "trim_color")),
        ("front", ("placket", "placket_buttons", "button_color", "v_insert")),
        ("sleeves", ("sleeve_length", "cuff", "sleeve_construction")),
        ("pockets", ("pockets",)),
        ("hem", ("hem",)),
        ("cloth", ("fit_detail", "fabric", "fiber", "weight", "knit_gauge", "corduroy_wale", "color_texture",
                   "pattern_name", "pattern_orientation", "shade")),
    ),
    "bottom": (
        ("shape", ("leg_shape", "rise", "trouser_break", "crease", "inseam")),
        ("front", ("waistband", "fly", "trouser_front")),
        ("pockets", ("pockets",)),
        ("hem", ("hem_finish",)),
        ("cloth", ("fabric", "fiber", "weight", "corduroy_wale", "denim_wash", "contrast_stitching", "color_texture",
                   "pattern_name", "shade")),
    ),
    "shoe": (
        ("shape", ("footwear", "shoe_style", "footwear_height", "toe_shape", "toe_treatment", "toe_cap", "side_stripe",
                   "contrast_heel_tab")),
        ("lacing", ("lacing", "eyelets", "laces")),
        ("sole", ("sole", "heel", "shoe_construction", "chunky_sole", "sole_color", "lace_color")),
        ("cloth", ("upper_material", "fabric", "fiber", "color_texture", "shade")),
    ),
}

# the names in sentences: "You changed the <title> from ... to ..."
TITLES = {
    "fit_detail": "cut", "sleeve_length": "sleeve length", "neckline": "neckline", "collar": "collar",
    "placket": "front", "placket_buttons": "number of buttons", "button_color": "button colour", "cuff": "cuffs",
    "sleeve_construction": "sleeve seams", "pockets": "pockets", "hem": "hem", "fabric": "fabric", "fiber": "fibre",
    "weight": "weight of the cloth", "knit_gauge": "knit", "corduroy_wale": "corduroy ridges",
    "color_texture": "colour effect", "pattern_name": "pattern's name", "pattern_orientation": "pattern direction",
    "trim_color": "trim colour", "waist": "waist", "pant_hem": "trouser hem", "shoe_style": "shoe style",
    "sole_color": "sole colour", "lace_color": "lace colour", "shade": "shade",
    "footwear": "kind of shoe", "toe_shape": "toe shape", "toe_treatment": "toe", "lacing": "fastening",
    "eyelets": "number of eyelets", "laces": "laces", "sole": "sole", "shoe_construction": "how the sole is attached",
    "footwear_height": "height", "heel": "heel", "upper_material": "upper",
    "waistband": "waistband", "fly": "fly", "trouser_front": "front", "rise": "rise", "leg_shape": "leg",
    "trouser_break": "break", "hem_finish": "hem", "crease": "crease", "trouser_pockets": "pockets",
    "back_details": "back and build", "denim_wash": "wash", "denim_fades": "fades", "distressing": "wear and repairs",
    "inseam": "inseam (inches)",
    "v_insert": "V insert under the neck", "pleats": "pleats", "pressed_crease": "pressed crease",
    "contrast_stitching": "contrast stitching", "toe_cap": "toe cap", "side_stripe": "side stripe",
    "contrast_heel_tab": "contrast heel tab", "chunky_sole": "chunky sole",
    "category": "kind of garment", "color": "colour", "color_hex": "colour shade", "pattern": "pattern",
    "formality": "formality", "season": "season", "silhouette": "shape", "name": "name", "material": "material",
    "silhouette.sleeve": "sleeves", "silhouette.neck": "neck", "silhouette.top_length": "length", "silhouette.fit": "fit",
    "silhouette.leg": "leg", "silhouette.pant_length": "trouser length", "silhouette.shoe_height": "shoe height",
}
_ANY = {"na": "doesn't apply", "none": "none", "same": "same as the cloth", "unknown": "not known",
        "light_blue": "light blue", "smart_casual": "smart casual", "dress_shoes": "dress shoes",
        "super_heavy": "very heavy", "set_in": "set in", "v_neck": "V-neck", "all_over": "all over"}
_WORDS = {
    "placket": {"front_placket": "buttons", "french_front": "buttons with no strip (French front)",
                "hidden_fly": "hidden buttons", "half_placket_popover": "a half placket", "henley": "a henley placket",
                "polo": "a polo placket", "snap": "snaps", "zip_quarter": "a quarter zip", "zip_half": "a half zip",
                "zip_full": "a full zip", "double_breasted": "double-breasted", "none": "no opening"},
    "neckline": {"na": "set by the collar", "polo_collar": "polo collar", "quarter_zip": "quarter zip"},
    "collar": {"none": "no collar", "button_down": "button-down", "hidden_button_down": "hidden button-down",
               "semi_spread": "semi-spread", "flat_knit": "flat knit", "woven_twill_rugby": "rugby",
               "notch_lapel": "notch lapel", "peak_lapel": "peak lapel"},
    "cuff": {"barrel_1": "one-button cuff", "barrel_2": "two-button cuff", "snap_3": "three-snap cuff",
             "rib_knit": "rib knit", "open_hem": "plain hem", "roll_tab": "roll tab", "none": "plain sleeve end"},
    "pockets": {"none": "no pockets", "five_pocket_jean": "five pockets (jeans)", "chest_patch_single": "one chest pocket",
                "chest_patch_double": "two chest pockets", "chest_flap_single": "one chest pocket with a flap",
                "chest_flap_double": "two chest pockets with flaps", "four_patch_guayabera": "four patch pockets",
                "three_patch_chore": "three patch pockets", "hip_patch_double": "two hip pockets",
                "hip_flap_double": "two hip pockets with flaps", "utility_sleeve": "sleeve pocket",
                "split_hand": "split hand pockets", "western_smile": "western smile pockets"},
    "hem": {"curved_shirt_tail": "curved shirt tail", "straight_with_vents": "straight with vents",
            "ribbed_band": "ribbed band"},
    "pant_hem": {"turn_up": "turned up"},
    "sleeve_length": {"three_quarter": "three-quarter"},
    "shoe_style": {"low_sneaker": "low sneaker", "high_top": "high top", "slip_on": "slip-on",
                   "chelsea_boot": "Chelsea boot"},
    "sole_color": {"same": "same as the upper"}, "lace_color": {"same": "same as the upper"},
    "footwear": {"plain_toe_oxford": "plain-toe oxford", "cap_toe_oxford": "cap-toe oxford", "moc_toe_boot": "moc-toe boot",
                 "canvas_low_top": "canvas low top", "canvas_high_top": "canvas high top", "chelsea_boot": "Chelsea boot",
                 "jodhpur_boot": "jodhpur boot"},
    "toe_shape": {"moc_toe": "moc toe"}, "toe_treatment": {"cap_toe": "toe cap", "split_toe": "split toe"},
    "lacing": {"closed_oxford": "closed (oxford)", "open_derby": "open (derby)", "slip_on": "no laces (slip-on)",
               "monk_single": "one buckled strap", "monk_double": "two buckled straps",
               "hook_and_loop": "hook-and-loop straps", "rawhide_around_collar": "rawhide lace round the collar"},
    "sole": {"lug_commando": "lug (commando)", "eva_foam_midsole": "foam midsole", "siped_deck": "boat-shoe sole",
             "jute_rope": "rope (jute)"},
    "footwear_height": {"boot_6in": "6-inch boot", "boot_8in_plus": "8 inches or taller", "ankle_boot": "ankle boot",
                        "no_show": "no-show"},
    "heel": {"low_stacked": "low stacked"},
    "waistband": {"elastic_drawcord": "elastic with a cord", "brace_buttons": "brace buttons", "extended_tab": "extended tab"},
    "fly": {"button": "button fly", "zip": "zip fly", "none": "no fly"},
    "trouser_front": {"single_pleat": "one pleat", "double_pleat": "two pleats", "reverse_pleat": "reverse pleat",
                      "forward_pleat": "forward pleat"},
    "trouser_break": {"no_break": "no break", "full": "full break", "slight": "slight break"},
    "hem_finish": {"turn_up": "turned up", "rolled_cuff": "rolled", "ribbed_cuff": "ribbed cuff", "chain_stitched": "chain-stitched"},
    "crease": {"none": "no crease"},
    "denim_wash": {"washed_black": "washed black"},

    "trim_color": {"same": "same as the body"}, "button_color": {"same": "same as the cloth"},
}


def kind_of(category) -> str | None:
    """"top", "bottom" or "shoe"; None for what has no details to fix (a bag, a belt, nothing known yet)."""
    return "top" if category in TOPS else "bottom" if category in BOTTOMS else "shoe" if category in SHOES else None


def names_for(category) -> tuple[str, ...]:
    return tuple(n for _, names in BY_KIND.get(kind_of(category) or "", ()) for n in names)


def values(name: str) -> tuple:
    """The values a detail can take, in the schema's order."""
    if name in FEATURES:
        return ("no", "yes")
    if name in NUMBERS:
        return tuple(range(NUMBERS[name] + 1))
    return get_args(Details.model_fields[name].annotation)


def title(name: str) -> str:
    return TITLES.get(name, name.replace("_", " "))


def words(name: str, value) -> str:
    """A value in plain words, e.g. ("placket", "half_placket_popover") -> "a half placket"."""
    if value is None or value == "" or value == {}:
        return "nothing"
    if isinstance(value, dict):   # a shape: "short sleeves, collar"
        return ", ".join(f"{words(f'silhouette.{k}', v)} {title(f'silhouette.{k}')}" for k, v in value.items())
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int):
        return ("none" if name in ("placket_buttons", "eyelets") else "not known") if value == 0 and name in NUMBERS \
            else str(value)
    if name in ("color_hex", "name", "material"):   # the owner's or Claude's own words
        return str(value)
    return _WORDS.get(name, {}).get(value) or _ANY.get(value) or str(value).replace("_", " ")


def coerce(name: str, value):
    """The owner's value for a detail in the schema's own form, or ValueError with a sentence saying what is allowed."""
    if name in FEATURES:
        if value in (True, "yes"):
            return "yes"
        if value in (False, "no"):
            return "no"
    elif name in NUMBERS:
        if isinstance(value, str) and value.strip().isdigit():
            value = int(value.strip())
        if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= NUMBERS[name]:
            return value
        raise ValueError(f"The {title(name)} must be a whole number from 0 to {NUMBERS[name]}.")
    elif name in DETAILS:
        if value in values(name):
            return value
    else:
        raise ValueError(f"'{name}' is not a detail that can be changed.")
    raise ValueError(f"'{value}' is not one of the choices for the {title(name)}.")


def own(row) -> dict:
    """The owner's own details for an item row (an empty dict when there are none)."""
    try:
        text = row["own_details"] if "own_details" in row.keys() else None
        out = json.loads(text) if text else {}
    except (ValueError, TypeError):
        return {}
    return {k: v for k, v in out.items() if k in PICKABLE} if isinstance(out, dict) else {}


def dump(values_: dict) -> str | None:
    return json.dumps(values_, sort_keys=True) if values_ else None


def lay(details: dict, owner: dict) -> dict:
    """Claude's details with the owner's laid over them."""
    out = dict(details)
    features = [f for f in (out.get("features") or []) if isinstance(f, str)]
    for k, v in owner.items():
        if k in FEATURES:
            if v == "yes" and k not in features:
                features.append(k)
            elif v == "no" and k in features:
                features.remove(k)
        else:
            out[k] = v
    out["features"] = features
    return out


def shown(details: dict, name: str):
    """A detail's value as drawn ("yes" or "no" for a feature)."""
    if name in FEATURES:
        return "yes" if name in (details.get("features") or []) else "no"
    return details.get(name)


# a shape the owner sets on the item's coarse fields puts aside their own matching details (the latest word wins)
SHAPE_DETAILS = {"sleeve": ("sleeve_length",), "neck": ("neckline", "collar"), "fit": ("fit_detail",),
                 "shoe_height": ("shoe_style",)}


def drop_for_shape(owner: dict, before: dict, after: dict) -> dict:
    out = dict(owner)
    for k, names in SHAPE_DETAILS.items():
        if before.get(k) != after.get(k):
            for n in names:
                out.pop(n, None)
    return out


def plain_answer(category, silhouette, color, pattern) -> dict | None:
    """An answer saying only what the item's own fields say, for an item Claude has not described: the owner's
    details are laid over it. None for an item with nothing to draw."""
    if category not in TOPS + BOTTOMS + SHOES:
        return None
    known = {}
    for k, v in (silhouette or {}).items() if isinstance(silhouette, dict) else ():
        if k in vocab.SILHOUETTE and v in vocab.SILHOUETTE[k]:
            known[k] = v
    return ItemTags(
        category=category, category_confidence=1, color=color if color in get_args(Color) else "grey", color_confidence=1,
        secondary_colors=[], pattern=pattern if pattern in get_args(Pattern) else "solid", pattern_confidence=1,
        formality="casual", formality_confidence=1, season="all", season_confidence=1,
        silhouette=Silhouette.of(**known), silhouette_confidence=1, details=Details.plain(), details_confidence=1,
        brand=None, size=None, material=None, needs_shot=None).model_dump(mode="json")
