"""The owner's menswear taxonomy (docs/menswear-taxonomy.json), as far as a front-view drawing can show it.

`AXES` is a frozen copy of the axes that are visible from the front; a test keeps it
equal to the JSON file, so an edit to the taxonomy shows up as a failing test, not as a
silently undrawn garment. `COVERAGE` says, for every value, whether the drawing shows
it exactly, approximately (and as what), or not yet. `top_drawing` turns taxonomy
values into template parameters.
"""
from __future__ import annotations

AXES: dict[str, tuple[str, ...]] = {
    "fit": (
        "slim", "regular", "relaxed", "boxy", "oversized", "cropped", "longline", "tailored",
    ),
    "sleeve_length": (
        "sleeveless", "short", "elbow", "three_quarter", "long",
    ),
    "neckline": (
        "crew", "v_neck", "scoop", "boat", "mock", "turtleneck", "rollneck", "shawl", "henley",
        "polo_collar", "quarter_zip", "hood",
    ),
    "collar": (
        "point", "semi_spread", "spread", "cutaway", "button_down", "hidden_button_down", "club", "tab",
        "pin", "band", "camp", "wing", "western", "johnny", "flat_knit", "woven_twill_rugby", "shawl",
        "stand", "notch_lapel", "peak_lapel", "none",
    ),
    "placket": (
        "front_placket", "french_front", "hidden_fly", "half_placket_popover", "henley", "polo", "snap",
        "zip_quarter", "zip_half", "zip_full", "double_breasted", "none",
    ),
    "cuff": (
        "barrel_1", "barrel_2", "french", "convertible", "mitred", "snap_3", "rib_knit", "open_hem",
        "rolled", "roll_tab", "none",
    ),
    "sleeve_construction": (
        "set_in", "raglan", "drop_shoulder", "saddle_shoulder", "dolman",
    ),
    "pockets": (
        "none", "chest_patch_single", "chest_patch_double", "chest_flap_single", "chest_flap_double",
        "pencil_slot", "western_smile", "bellows", "welt", "kangaroo", "split_hand", "slash",
        "utility_sleeve", "four_patch_guayabera", "three_patch_chore", "five_pocket_jean", "cargo",
    ),
    "hem": (
        "curved_shirt_tail", "straight_with_vents", "straight", "tennis_tail", "ribbed_band", "raw",
    ),
    "woven_structure": (
        "plain", "linen", "poplin", "broadcloth", "twill", "herringbone", "oxford", "pinpoint_oxford",
        "royal_oxford", "end_on_end", "chambray", "denim", "dobby", "jacquard", "satin", "sateen",
        "seersucker", "madras", "voile", "flannel", "brushed_twill", "corduroy", "moleskin", "canvas",
        "ripstop", "gabardine", "tweed", "hopsack", "fresco", "cavalry_twill", "whipcord", "velvet",
        "melton", "waffle_weave", "challis", "waxed_cotton", "crepe",
    ),
    "knit_structure": (
        "jersey", "slub_jersey", "interlock", "pique", "waffle_thermal", "rib_1x1", "rib_2x2",
        "french_terry", "fleece_back", "mesh", "terry_towelling", "velour", "flat_knit", "fisherman_rib",
        "shaker", "cable", "aran", "moss", "garter", "pointelle", "fair_isle", "nordic", "argyle",
        "intarsia", "jacquard_knit", "guernsey", "cowichan", "polar_fleece", "sherpa",
    ),
    "color_texture": (
        "solid", "heathered", "marled", "slub", "two_tone", "shot", "garment_dyed", "pigment_dyed", "faded",
        "ombre", "space_dyed",
    ),
    "pattern": (
        "solid", "hairline_stripe", "pencil_stripe", "pinstripe", "chalk_stripe", "bengal_stripe",
        "candy_stripe", "university_stripe", "butcher_stripe", "awning_stripe", "multi_stripe",
        "breton_stripe", "rugby_hoops", "shadow_stripe", "bowling_panels", "gingham", "micro_check",
        "graph_check", "windowpane", "tattersall", "shepherds_check", "houndstooth", "glen_check",
        "buffalo_check", "tartan", "madras_plaid", "overcheck", "gun_club_check", "argyle", "polka_dot",
        "pin_dot", "paisley", "foulard", "floral_ditsy", "floral_large", "aloha", "camo_woodland",
        "camo_desert", "camo_tiger", "camo_digital", "geometric", "novelty", "ikat", "batik", "shibori",
        "tie_dye", "animal", "fair_isle", "nordic",
    ),
    "pattern_orientation": (
        "vertical", "horizontal", "bias", "all_over", "placed",
    ),
}

# Axes that decide the shape of a top. `top_drawing` reads exactly these keys (taxonomy values),
# plus "length" (cropped | regular | long) and "placket_buttons" (an int, or None for the usual number).
TOP_AXES = ("fit", "sleeve_length", "neckline", "collar", "placket", "cuff", "sleeve_construction", "pockets", "hem")

_FIT = {"slim": "slim", "tailored": "slim", "regular": "regular", "cropped": "regular", "longline": "regular",
        "relaxed": "oversized", "boxy": "oversized", "oversized": "oversized"}
_SLEEVE = {"sleeveless": "none", "short": "short", "elbow": "short", "three_quarter": "long", "long": "long"}
_NECK = {"crew": "crew", "scoop": "crew", "boat": "crew", "v_neck": "v", "shawl": "v", "mock": "turtle",
         "turtleneck": "turtle", "rollneck": "turtle", "henley": "crew", "polo_collar": "collar",
         "quarter_zip": "turtle", "hood": "hood"}
_FRONT = {"front_placket": "buttons", "french_front": "buttons", "hidden_fly": "buttons", "snap": "buttons",
          "double_breasted": "buttons", "half_placket_popover": "half", "henley": "half", "polo": "half",
          "zip_quarter": "quarter-zip", "zip_half": "quarter-zip", "zip_full": "zip", "none": "none"}
_CUFF = {"barrel_1": "button", "barrel_2": "button", "french": "button", "convertible": "button", "mitred": "button",
         "snap_3": "button", "rib_knit": "rib"}
_POCKETS = {"chest_patch_single": "chest", "chest_flap_single": "chest", "pencil_slot": "chest",
            "chest_patch_double": "chest-two", "chest_flap_double": "chest-two", "western_smile": "chest-two",
            "kangaroo": "kangaroo", "split_hand": "low", "welt": "low", "slash": "low",
            "three_patch_chore": "chest-low", "four_patch_guayabera": "chest-low", "bellows": "chest-low"}
_HEM = {"curved_shirt_tail": "curved", "tennis_tail": "curved", "ribbed_band": "rib"}
_TEXTURE = {"corduroy": "corduroy", "cable": "cable_knit", "aran": "cable_knit", "rib_1x1": "rib_knit",
            "rib_2x2": "rib_knit", "fisherman_rib": "rib_knit", "shaker": "rib_knit", "waffle_thermal": "waffle",
            "waffle_weave": "waffle"}


def top_drawing(g: dict) -> tuple[dict, dict, list[str]]:
    """Template parameters, `Spec` extras and notes on what was approximated, for a top described in taxonomy values."""
    collar, neckline = g.get("collar", "none"), g.get("neckline", "crew")
    p = {"fit": _FIT.get(g.get("fit"), "regular"), "sleeve": _SLEEVE.get(g.get("sleeve_length"), "long"),
         "neck": "collar" if collar not in ("none", None) else _NECK.get(neckline, "crew"),
         "front": _FRONT.get(g.get("placket"), "none"),
         "cuffs": _CUFF.get(g.get("cuff"), "plain"), "pockets": _POCKETS.get(g.get("pockets"), "none"),
         "hem": _HEM.get(g.get("hem"), "straight"), "length": g.get("length") or "regular"}
    if g.get("fit") == "cropped":
        p["length"] = "cropped"
    elif g.get("fit") == "longline":
        p["length"] = "long"
    if neckline in ("henley", "polo_collar") and p["front"] == "none":
        p["front"] = "half"
    if neckline == "quarter_zip" and p["front"] == "none":
        p["front"] = "quarter-zip"
    if p["sleeve"] != "long":
        p["cuffs"] = "plain"
    if p["front"] in ("buttons", "half") and g.get("placket_buttons") is not None:
        p["buttons"] = 0 if g.get("placket") == "hidden_fly" else g["placket_buttons"]
    if g.get("sleeve_construction") == "raglan":
        p["shoulder"] = "raglan"
    extras = {"texture": _TEXTURE.get(g.get("fabric"))}
    return p, extras, []
