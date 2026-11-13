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
        "utility_sleeve", "four_patch_guayabera", "three_patch_chore", "hip_patch_double", "hip_flap_double",
        "five_pocket_jean", "cargo",
    ),
    "hem": (
        "curved_shirt_tail", "straight_with_vents", "straight", "tennis_tail", "ribbed_band", "raw",
    ),
    "fiber": (
        "cotton", "linen", "cotton_linen", "hemp", "merino", "lambswool", "shetland", "cashmere", "yak", "camel",
        "alpaca", "mohair", "worsted_wool", "woolen_wool", "silk", "polyester", "nylon", "acrylic", "viscose", "lyocell",
        "modal", "leather", "suede", "shearling",
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


# The general thickness scale (the names of the taxonomy's jersey weights), knit gauges and corduroy
# wales, in the order of the JSON's `weights` block.
WEIGHT_CLASSES = ("lightweight", "midweight", "heavyweight", "super_heavy")
KNIT_GAUGES = ("extra_fine", "fine", "medium", "chunky", "super_chunky")
CORDUROY_WALES = ("needlecord", "standard", "mid", "wide_wale", "jumbo")
# the shoe styles the drawing has a shape for (a sandal has none yet)
SHOE_STYLES = ("low_sneaker", "high_top", "runner", "slip_on", "loafer", "derby", "oxford", "boot", "chelsea_boot")

# Axes that decide the shape of a top. `top_drawing` reads exactly these keys (taxonomy values), plus
# "length" (cropped | regular | long | knee), "placket_buttons" (an int, or None for the usual number),
# "back_detail" (western_yoke draws the pointed front yoke too), and the surface keys `surface_extras` reads.
TOP_AXES = ("fit", "sleeve_length", "neckline", "collar", "placket", "cuff", "sleeve_construction", "pockets", "hem")

_FIT = {"slim": "slim", "tailored": "tailored", "regular": "regular", "cropped": "regular", "longline": "regular",
        "relaxed": "relaxed", "boxy": "boxy", "oversized": "oversized"}
_SLEEVE = {"sleeveless": "none", "short": "short", "elbow": "elbow", "three_quarter": "three-quarter", "long": "long"}
_NECK = {"crew": "crew", "scoop": "scoop", "boat": "boat", "v_neck": "v", "shawl": "shawl", "mock": "mock",
         "turtleneck": "turtle", "rollneck": "roll", "henley": "crew", "polo_collar": "collar",
         "quarter_zip": "mock", "hood": "hood"}
_COLLAR = {"point": "point", "semi_spread": "semi_spread", "spread": "spread", "cutaway": "cutaway",
           "button_down": "button_down", "hidden_button_down": "hidden_button_down", "club": "club", "tab": "tab",
           "pin": "pin", "band": "band", "camp": "camp", "wing": "wing", "western": "western", "johnny": "johnny",
           "flat_knit": "knit", "woven_twill_rugby": "rugby", "shawl": "shawl", "stand": "stand",
           "notch_lapel": "notch", "peak_lapel": "peak"}
_FRONT = {"front_placket": "buttons", "french_front": "french", "hidden_fly": "hidden", "snap": "buttons",
          "double_breasted": "double", "half_placket_popover": "popover", "henley": "half", "polo": "half",
          "zip_quarter": "quarter-zip", "zip_half": "half-zip", "zip_full": "zip", "none": "none"}
_CUFF = {"barrel_1": "button", "barrel_2": "button2", "french": "french", "convertible": "button", "mitred": "mitred",
         "snap_3": "snap3", "rib_knit": "rib", "open_hem": "open", "rolled": "rolled", "roll_tab": "roll-tab", "none": "plain"}
_SHOULDER = {"set_in": "set-in", "raglan": "raglan", "drop_shoulder": "drop", "saddle_shoulder": "saddle", "dolman": "dolman"}
_POCKETS = {"none": "none", "chest_patch_single": "chest", "chest_patch_double": "chest-patch-two",
            "chest_flap_single": "chest-flap", "chest_flap_double": "chest-flap-two", "pencil_slot": "pencil",
            "western_smile": "western", "bellows": "bellows", "welt": "welt", "kangaroo": "kangaroo",
            "split_hand": "split", "slash": "slash", "utility_sleeve": "utility", "four_patch_guayabera": "guayabera",
            "three_patch_chore": "chore", "hip_patch_double": "hip-patch", "hip_flap_double": "hip-flap",
            "five_pocket_jean": "none", "cargo": "bellows"}
# the colour of a tailored jacket's buttons, by what they are made of (others: pale, like the card)
_BUTTON_COLOR = {"metal_shank": "#b8995a", "horn": "#4a3426", "corozo": "#6e5b45", "wood": "#7a5a3a",
                 "leather_knot": "#5a3b26", "coconut": "#5e4630"}
_HEM = {"curved_shirt_tail": "curved", "straight_with_vents": "vents", "straight": "straight", "tennis_tail": "tennis",
        "ribbed_band": "rib", "raw": "raw"}
_SHIRT_COLLARS = ("point", "semi_spread", "spread", "cutaway", "button_down", "hidden_button_down", "club", "tab", "pin",
                  "western", "band", "wing", "camp")

# ---- cloth: what a fabric or fibre does to the drawing
_TEXTURE = {   # fabric (woven or knit structure) -> tone-on-tone surface; scaled by wale or gauge where it has one
    "corduroy": "corduroy", "cable": "cable_knit", "aran": "cable_knit", "rib_1x1": "rib_knit", "rib_2x2": "rib_knit",
    "shaker": "rib_knit", "fisherman_rib": "fisherman_rib", "waffle_thermal": "waffle", "waffle_weave": "waffle",
    "pique": "pique", "moss": "pique", "terry_towelling": "pique", "mesh": "mesh", "pointelle": "mesh",
    "seersucker": "seersucker", "herringbone": "herringbone", "twill": "twill", "brushed_twill": "twill",
    "gabardine": "twill", "cavalry_twill": "twill", "whipcord": "twill", "denim": "denim", "garter": "garter",
    "guernsey": "garter", "linen": "linen", "slub_jersey": "linen", "hopsack": "basket",
    "fresco": "basket", "tweed": "tweed", "ripstop": "ripstop", "sherpa": "sherpa",
    "polar_fleece": "fleece", "fleece_back": "fleece",
}
_WALE_SCALE = {"needlecord": 0.55, "standard": 1.0, "mid": 1.4, "wide_wale": 1.9, "jumbo": 2.6}
_GAUGE_SCALE = {"extra_fine": 0.7, "fine": 0.85, "medium": 1.0, "chunky": 1.3, "super_chunky": 1.65}
_QUILT = {"baffle": "baffle", "diamond": "quilt_diamond", "box": "quilt_box"}
# fabric -> its usual weight (index into WEIGHT_CLASSES) when the tagger could not tell
_FABRIC_WEIGHT = {
    **dict.fromkeys(("voile", "poplin", "broadcloth", "pinpoint_oxford", "end_on_end", "seersucker", "madras", "challis",
                     "crepe", "satin", "sateen", "fresco", "linen", "mesh", "pointelle"), 0),
    **dict.fromkeys(("plain", "oxford", "royal_oxford", "chambray", "twill", "herringbone", "dobby", "jacquard", "gabardine",
                     "hopsack", "ripstop", "velvet", "jersey", "slub_jersey", "interlock", "pique", "rib_1x1", "rib_2x2",
                     "flat_knit", "terry_towelling", "velour", "waffle_thermal", "moss", "garter", "fair_isle", "argyle",
                     "intarsia", "jacquard_knit"), 1),
    **dict.fromkeys(("flannel", "brushed_twill", "denim", "corduroy", "moleskin", "canvas", "cavalry_twill", "whipcord",
                     "waffle_weave", "waxed_cotton", "french_terry", "fleece_back", "cable", "shaker", "fisherman_rib",
                     "polar_fleece", "nordic", "guernsey"), 2),
    **dict.fromkeys(("melton", "tweed", "sherpa", "aran", "cowichan"), 3),
}
# fibre -> its usual weight with no fabric known, and how it shifts a known fabric's weight
_FIBER_WEIGHT = {"linen": 0, "silk": 0, "viscose": 0, "lyocell": 0, "modal": 0, "nylon": 0, "cotton_linen": 0, "hemp": 1,
                 "cotton": 1, "merino": 1, "cashmere": 1, "polyester": 1, "acrylic": 1, "worsted_wool": 1, "lambswool": 1,
                 "woolen_wool": 2, "shetland": 2, "yak": 2, "camel": 2, "alpaca": 2, "mohair": 1, "leather": 2, "suede": 2,
                 "shearling": 3}
_FIBER_SHIFT = {"woolen_wool": 1, "shetland": 1, "yak": 1, "camel": 1, "alpaca": 1, "shearling": 1,
                "polyester": -1, "nylon": -1, "viscose": -1, "silk": -1, "linen": -1, "lyocell": -1, "modal": -1}
_SYNTHETIC_FABRICS = {"polar_fleece", "sherpa", "fleece_back", "ripstop", "mesh"}
_HALO_FABRICS = {"fleece_back", "polar_fleece", "sherpa", "flannel", "brushed_twill", "tweed", "velour"}
_HALO_FIBERS = {"mohair", "alpaca", "shetland", "yak", "cashmere", "shearling"}
_SHEEN_FABRICS = {"satin", "sateen", "waxed_cotton"}
_SHEEN_FIBERS = {"silk", "nylon"}


def _fabric(g: dict) -> str | None:
    for key in ("fabric", "knit_structure", "woven_structure", "knit", "weave"):
        v = g.get(key)
        if isinstance(v, (list, tuple)):
            v = v[0] if v else None
        if v:
            return v
    return None


def surface_extras(g: dict) -> dict:
    """`Spec` keyword arguments for the cloth's surface and weight: texture, texture_scale (wale or
    gauge: 1 = standard), weight, halo, sheen.
    Reads "fabric" (or "woven_structure" / "knit_structure"), "fiber", "weight", "knit_gauge",
    "corduroy_wale" and "quilting" (baffle | diamond | box). Not specific to tops."""
    fabric, fiber = _fabric(g), g.get("fiber")
    gauge, wale = g.get("knit_gauge"), g.get("corduroy_wale")
    # texture
    tex = _QUILT.get(g.get("quilting") or "") or _TEXTURE.get(fabric or "")
    if not tex and fiber in ("linen", "hemp", "cotton_linen") and not fabric:
        tex = "linen"
    if not tex and fiber == "shearling":
        tex = "sherpa"
    scale = None
    if tex == "corduroy" and wale in _WALE_SCALE and wale != "standard":
        scale = _WALE_SCALE[wale]
    elif tex in ("cable_knit", "rib_knit", "fisherman_rib", "waffle", "garter"):
        scale = _GAUGE_SCALE.get(gauge) or (1.25 if fabric == "aran" else 0.75 if fabric == "rib_1x1" else None)
        if scale == 1.0:
            scale = None
    # weight
    weight = g.get("weight") if g.get("weight") in WEIGHT_CLASSES else None
    if weight is None:
        lvl = _FABRIC_WEIGHT.get(fabric or "")
        if lvl is None:
            lvl = _FIBER_WEIGHT.get(fiber or "")
        elif fiber and not (fabric in _SYNTHETIC_FABRICS and _FIBER_SHIFT.get(fiber, 0) < 0):
            lvl += _FIBER_SHIFT.get(fiber, 0)   # wool flannel is heavier than cotton flannel; fleece is always synthetic
        if gauge in ("chunky", "super_chunky"):
            lvl = max(lvl if lvl is not None else 0, 2 if gauge == "chunky" else 3)
        elif gauge == "extra_fine":
            lvl = 0
        elif gauge == "fine" and lvl is not None:
            lvl = min(lvl, 1)
        if g.get("quilting") == "baffle":
            lvl = 3
        if lvl is not None:
            weight = WEIGHT_CLASSES[max(0, min(3, lvl))]
    halo = fabric in _HALO_FABRICS or fiber in _HALO_FIBERS
    sheen = (fabric in _SHEEN_FABRICS or fiber in _SHEEN_FIBERS) and not halo
    return {"texture": tex, "texture_scale": scale, "weight": weight, "halo": halo, "sheen": sheen}


def top_drawing(g: dict) -> tuple[dict, dict, list[str]]:
    """Template parameters, `Spec` extras and notes on what was approximated, for a top described in taxonomy values."""
    notes: list[str] = []
    collar, neckline = g.get("collar") or "none", g.get("neckline") or "crew"
    placket = g.get("placket")
    fit = g.get("fit")
    p = {"fit": _FIT.get(fit, "regular"), "sleeve": _SLEEVE.get(g.get("sleeve_length"), "long"),
         "neck": _NECK.get(neckline, "crew"), "front": _FRONT.get(placket, "none"),
         "cuffs": _CUFF.get(g.get("cuff"), "plain"), "pockets": _POCKETS.get(g.get("pockets"), "none"),
         "hem": _HEM.get(g.get("hem"), "straight"), "length": g.get("length") or "regular"}
    extras: dict = {}
    if collar != "none":
        p["neck"] = "collar"
        p["collar"] = _COLLAR.get(collar, "semi_spread")
        if placket is None:   # the closure that goes with the collar when none was said
            p["front"] = ("buttons" if collar in _SHIRT_COLLARS or collar in ("notch_lapel", "peak_lapel", "shawl")
                          else "zip" if collar == "stand" else "none" if collar == "johnny" else "half")
    elif neckline == "polo_collar":
        p["collar"] = "knit"
    if fit == "cropped":
        p["length"] = "cropped"
    elif fit == "longline":
        p["length"] = "long"
    if p.get("collar") in ("notch", "peak", "shawl"):
        # tailoring has its own construction: a jacket, or at knee length a coat
        p["block"] = "coat" if p["length"] == "knee" else "jacket"
        if g.get("pockets") is None:
            p["pockets"] = "hip-flap"     # every tailored jacket has pockets: a breast welt and two flaps
        if _BUTTON_COLOR.get(g.get("closure_material")):
            extras["button_color"] = _BUTTON_COLOR[g["closure_material"]]
        if g.get("hem") not in (None, "straight"):
            notes.append(f"{g['hem']} hem on a tailored jacket drawn as its straight hem with rounded quarters")
        if g.get("cuff") is not None:
            notes.append(f"{g['cuff']} cuff on a tailored jacket drawn as its sleeve with four cuff buttons")
        if g.get("sleeve_construction") not in (None, "set_in"):
            notes.append(f"{g['sleeve_construction']} sleeve on a tailored jacket drawn set-in at a structured shoulder")
    if neckline in ("henley", "polo_collar") and p["front"] == "none" and placket is None:
        p["front"] = "half"
    if neckline == "quarter_zip" and p["front"] == "none":
        p["front"] = "quarter-zip"
    if placket == "snap":
        p["fastener"] = "snap"
    if p["front"] in ("buttons", "half", "popover", "french", "double") and g.get("placket_buttons") is not None:
        p["buttons"] = g["placket_buttons"]
    if placket == "hidden_fly":
        p["buttons"] = None
    if g.get("sleeve_construction") in _SHOULDER:
        p["shoulder"] = _SHOULDER[g["sleeve_construction"]]
    elif fit in ("boxy", "oversized"):
        p["shoulder"] = "drop"      # the reference: boxy and oversized cuts drop the shoulder
    if p.get("shoulder") == "raglan" and p["neck"] == "collar":
        notes.append("raglan seams are not drawn under a collar")
    # sleeveless: a knit with ribbed armholes is a sweater vest, otherwise a tank
    if p["sleeve"] == "none":
        if g.get("cuff") == "rib_knit" or neckline == "v_neck" and g.get("hem") == "ribbed_band":
            p["armhole"] = "vest"
        p["cuffs"] = "plain"
    if p["sleeve"] in ("short", "elbow") and p["cuffs"] not in ("rib", "open", "plain"):
        notes.append(f"{g.get('cuff')} cuff on a short sleeve drawn as a plain hem")
        p["cuffs"] = "plain"
    if p["neck"] == "v" and g.get("v_depth"):
        p["v_depth"] = g["v_depth"]
    # western details travel together: the pointed yoke is the western shirt's signature
    if collar == "western" or g.get("pockets") == "western_smile" or g.get("back_detail") == "western_yoke":
        p["yoke"] = "western"
    if collar == "woven_twill_rugby":
        extras["collar_color"] = "#f4f1ea"
        notes.append("rugby collar drawn in white twill, the classic contrast")
    if collar == "camp" and g.get("hem") is None:
        p["hem"] = "straight"
    # notes for what is drawn as something close
    approx = {
        "hidden_button_down": "hidden button-down drawn as a soft-roll point collar (its buttons are under the points)",
        "convertible": "convertible cuff drawn as a one-button barrel cuff",
        "cargo": "cargo pockets on a top drawn as bellows pockets",
        "five_pocket_jean": "five-pocket layout belongs to jeans: not drawn on a top",
        "terry_towelling": "terry loops drawn as a fine dimpled surface",
    }
    for v in (collar, g.get("cuff"), g.get("pockets"), _fabric(g)):
        if v in approx:
            notes.append(approx[v])
    if p["pockets"] == "utility" and p["sleeve"] == "none":
        notes.append("a sleeve pocket on a sleeveless top is not drawn")
    surf = surface_extras(g)
    extras.update({k: v for k, v in surf.items() if v})
    if surf["weight"]:
        p["weight"] = surf["weight"]
    if g.get("knit_gauge") in KNIT_GAUGES:
        p["gauge"] = g["knit_gauge"]
    if g.get("quilting") == "baffle":   # a puffer: the outline swells between the stitched channels
        p["quilting"] = "baffle"
    return p, extras, notes


# Signature garments, as axis values. Outerwear and tailoring have no axis values in the taxonomy's
# `garments` block; these say how each is drawn with the top template.
GARMENT_DRAWINGS: dict[str, dict] = {
    "t_shirt": dict(neckline="crew", sleeve_length="short", hem="straight", fabric="jersey"),
    "henley": dict(neckline="henley", placket="henley", placket_buttons=3, sleeve_length="long", fabric="waffle_thermal"),
    "polo": dict(collar="flat_knit", placket="polo", placket_buttons=2, sleeve_length="short", cuff="rib_knit",
                 hem="tennis_tail", fabric="pique"),
    "rugby_shirt": dict(collar="woven_twill_rugby", placket="polo", placket_buttons=2, sleeve_length="long",
                        cuff="rib_knit", hem="straight_with_vents", fabric="jersey", weight="heavyweight"),
    "dress_shirt": dict(collar="spread", placket="front_placket", cuff="barrel_1", hem="curved_shirt_tail", fit="slim",
                        fabric="poplin"),
    "ocbd": dict(collar="button_down", placket="front_placket", cuff="barrel_1", pockets="chest_patch_single",
                 hem="curved_shirt_tail", fabric="oxford"),
    "flannel_shirt": dict(collar="point", placket="front_placket", cuff="barrel_2", pockets="chest_flap_double",
                          hem="curved_shirt_tail", fabric="flannel", fiber="cotton"),
    "work_shirt": dict(collar="point", placket="front_placket", cuff="barrel_1", pockets="pencil_slot", hem="straight_with_vents",
                       fabric="chambray"),
    "western_shirt": dict(collar="western", placket="snap", cuff="snap_3", pockets="western_smile", hem="curved_shirt_tail",
                          fit="slim", fabric="denim"),
    "camp_collar_shirt": dict(collar="camp", placket="front_placket", sleeve_length="short", hem="straight", fit="relaxed",
                              fabric="challis", fiber="viscose"),
    "popover_shirt": dict(collar="button_down", placket="half_placket_popover", cuff="barrel_1", hem="curved_shirt_tail",
                          fabric="oxford"),
    "band_collar_shirt": dict(collar="band", placket="front_placket", cuff="barrel_1", hem="curved_shirt_tail", fabric="linen"),
    "guayabera": dict(collar="camp", placket="front_placket", pockets="four_patch_guayabera", sleeve_length="short",
                      hem="straight_with_vents", fabric="linen"),
    "overshirt": dict(collar="point", placket="front_placket", cuff="barrel_1", pockets="chest_flap_double", hem="straight",
                      fit="relaxed", fabric="flannel", fiber="woolen_wool"),
    "tuxedo_shirt": dict(collar="wing", placket="hidden_fly", cuff="french", hem="curved_shirt_tail", fabric="poplin"),
    "crewneck_sweatshirt": dict(neckline="crew", sleeve_construction="raglan", cuff="rib_knit", hem="ribbed_band",
                                fabric="french_terry"),
    "hoodie": dict(neckline="hood", cuff="rib_knit", hem="ribbed_band", pockets="kangaroo", fabric="fleece_back"),
    "zip_hoodie": dict(neckline="hood", placket="zip_full", cuff="rib_knit", hem="ribbed_band", pockets="split_hand",
                       fabric="fleece_back"),
    "pullover_sweater": dict(neckline="crew", cuff="rib_knit", hem="ribbed_band", fabric="cable", fiber="lambswool"),
    "cardigan": dict(neckline="v_neck", placket="front_placket", placket_buttons=5, cuff="rib_knit", hem="ribbed_band",
                     pockets="welt", fabric="flat_knit", fiber="merino"),
    "shawl_cardigan": dict(neckline="shawl", placket="front_placket", placket_buttons=4, cuff="rib_knit", hem="ribbed_band",
                           pockets="welt", fabric="shaker", knit_gauge="chunky", fiber="lambswool"),
    "sweater_vest": dict(neckline="v_neck", sleeve_length="sleeveless", cuff="rib_knit", hem="ribbed_band",
                         fabric="cable", fiber="lambswool"),
    "quarter_zip": dict(neckline="quarter_zip", placket="zip_quarter", cuff="rib_knit", hem="ribbed_band", fabric="flat_knit",
                        fiber="merino"),
    "chore_coat": dict(collar="point", placket="front_placket", placket_buttons=5, pockets="three_patch_chore", hem="straight",
                       fit="boxy", sleeve_construction="set_in", cuff="barrel_1", fabric="canvas", length="regular"),
    "trucker_jacket": dict(collar="point", placket="front_placket", pockets="chest_flap_double", hem="ribbed_band",
                           cuff="barrel_1", fabric="denim", weight="heavyweight", length="cropped"),
    "bomber": dict(collar="stand", placket="zip_full", cuff="rib_knit", hem="ribbed_band", pockets="utility_sleeve",
                   fit="relaxed", fiber="nylon", fabric="plain", weight="lightweight"),
    "harrington": dict(collar="stand", placket="zip_full", cuff="rib_knit", hem="ribbed_band", pockets="slash",
                       fabric="gabardine", weight="midweight"),
    "field_jacket": dict(collar="stand", placket="zip_full", pockets="bellows", hem="straight", cuff="barrel_1",
                         fit="relaxed", fabric="sateen", length="long", weight="heavyweight"),
    "peacoat": dict(collar="peak_lapel", placket="double_breasted", placket_buttons=6, pockets="slash", hem="straight",
                    fabric="melton", length="long"),
    "overcoat": dict(collar="notch_lapel", placket="front_placket", placket_buttons=3, pockets="hip_flap_double",
                     hem="straight", fabric="melton", length="knee", closure_material="horn"),
    "puffer": dict(collar="stand", placket="zip_full", cuff="rib_knit", hem="straight", fit="relaxed", fiber="nylon",
                   quilting="baffle", fabric="ripstop"),
    "quilted_jacket": dict(collar="band", placket="snap", pockets="hip_patch_double", hem="straight", cuff="open_hem",
                           quilting="diamond", fiber="nylon", weight="midweight"),
    "fleece_jacket": dict(collar="stand", placket="zip_full", pockets="split_hand", hem="straight", cuff="open_hem",
                          fabric="polar_fleece"),
    "barn_jacket": dict(collar="point", placket="front_placket", pockets="hip_flap_double", hem="straight", fabric="canvas",
                        weight="heavyweight", fit="relaxed"),
    "blazer": dict(collar="notch_lapel", placket="front_placket", placket_buttons=2, pockets="hip_flap_double",
                   hem="straight", fit="tailored", fabric="hopsack", fiber="worsted_wool", closure_material="metal_shank"),
    "sport_coat": dict(collar="notch_lapel", placket="front_placket", placket_buttons=2, pockets="hip_patch_double",
                       hem="straight", fit="tailored", fabric="tweed", closure_material="horn"),
    "suit_jacket": dict(collar="peak_lapel", placket="front_placket", placket_buttons=1, pockets="welt", hem="straight",
                        fit="tailored", fabric="plain", fiber="worsted_wool", closure_material="corozo"),
}


def _c(*rows):
    return dict(rows)


D, A_, N_ = "drawn", "approximate", "not_drawn"
# For every value of every axis a front-view drawing can show: drawn (visibly distinct and right),
# approximate (drawn as something close; the note says as what) or not drawn (the note says why).
COVERAGE: dict[str, dict[str, tuple[str, str]]] = {
    "fit": _c(
        ("slim", (D, "narrow shoulders and body, slimmer sleeves")),
        ("regular", (D, "the reference shirt's proportions")),
        ("relaxed", (D, "wider body and sleeves than regular")),
        ("boxy", (D, "wide straight body, shorter, dropped shoulder")),
        ("oversized", (D, "widest body, dropped shoulder, longer and wider sleeves")),
        ("cropped", (D, "regular width, short body")),
        ("longline", (D, "regular width, long body")),
        ("tailored", (D, "slim with the side seams drawn in at the waist")),
    ),
    "sleeve_length": _c(
        ("sleeveless", (D, "tank straps, or a sweater vest's ribbed armholes when the cuff is rib")),
        ("short", (D, "")), ("elbow", (D, "ends at the elbow, hemmed")),
        ("three_quarter", (D, "ends below the elbow; takes rib cuffs")), ("long", (D, "")),
    ),
    "neckline": _c(
        ("crew", (D, "")), ("v_neck", (D, "depth adjustable (v_depth); with a button front it becomes a cardigan's banded V")),
        ("scoop", (D, "wider and deeper than a crew")), ("boat", (D, "wide shallow slit across the collarbones")),
        ("mock", (D, "short stand, not folded")), ("turtleneck", (D, "tall tube with its fold line")),
        ("rollneck", (D, "tall soft roll bulging over itself, no fold line")),
        ("shawl", (D, "a knitted shawl collar crossing at the bottom of a V")),
        ("henley", (D, "crew with a short button placket")), ("polo_collar", (D, "knit collar and placket")),
        ("quarter_zip", (D, "mock stand with the zip running up through it")), ("hood", (D, "")),
    ),
    "collar": _c(
        ("point", (D, "long narrow points, about 35 degrees off vertical")),
        ("semi_spread", (D, "the reference shirt's collar, points about 47 degrees out")),
        ("spread", (D, "points about 62 degrees out; more stand shows")),
        ("cutaway", (D, "points swept nearly horizontal; a wide stand shows between them")),
        ("button_down", (D, "soft roll and a small button at each point")),
        ("hidden_button_down", (A_, "drawn as a soft-roll point collar: its buttons are hidden under the points")),
        ("club", (D, "rounded points")), ("tab", (D, "close-set points with a buttoned strap linking them below the collar button; under a tie it would hide")),
        ("pin", (D, "point collar with a collar bar across")), ("band", (D, "stand only, no leaves; button on the band")),
        ("camp", (D, "flat collar with no stand, open notch and small revers down to the first button")),
        ("wing", (D, "stand with pressed-out wing tips, wide enough to read at item size")),
        ("western", (D, "long sharp points; also brings the pointed western yoke")),
        ("johnny", (D, "knit spread collar over an open V with no buttons")),
        ("flat_knit", (D, "the polo's soft knit collar")),
        ("woven_twill_rugby", (D, "firmer collar, drawn in white (collar_color)")),
        ("shawl", (D, "one continuous rolled collar and lapel, no notch; on a jacket, the tailored construction")),
        ("stand", (D, "taller stand collar for jackets, the zip runs to its top")),
        ("notch_lapel", (D, "a tailored jacket of its own: square shoulder, collar meeting the lapel at the gorge "
                            "with a notch, lapels rolling to the top button, quarters curving away; a coat at knee length")),
        ("peak_lapel", (D, "the tailored jacket with lapel points rising toward the shoulder")),
        ("none", (D, "the neckline decides")),
    ),
    "placket": _c(
        ("front_placket", (D, "strip with two stitch lines, buttons down the centre")),
        ("french_front", (D, "one folded edge line, buttons, no strip")),
        ("hidden_fly", (D, "edge line and one curved stitch row, no buttons below the collar")),
        ("half_placket_popover", (D, "woven placket to mid-chest, widely spaced buttons")),
        ("henley", (D, "short placket under a round neck")), ("polo", (D, "short placket under a knit collar")),
        ("snap", (D, "press studs drawn as a metal ring round a cap")),
        ("zip_quarter", (D, "short zip")), ("zip_half", (D, "zip to mid-chest")), ("zip_full", (D, "")),
        ("double_breasted", (D, "front edge well past centre, two columns of buttons; on a jacket 6x2, "
                                "the top row set wider")),
        ("none", (D, "")),
    ),
    "cuff": _c(
        ("barrel_1", (D, "one button")), ("barrel_2", (D, "two buttons side by side")),
        ("french", (D, "deep folded cuff with a cufflink, no button")),
        ("convertible", (A_, "drawn as a one-button barrel cuff: the second buttonhole does not show")),
        ("mitred", (D, "cuff corner cut on the slant")), ("snap_3", (D, "deep cuff with three snaps")),
        ("rib_knit", (D, "rib band; on short sleeves the polo's armband")),
        ("open_hem", (D, "a stitched hem at the wrist, no cuff")),
        ("rolled", (D, "sleeve rolled above the elbow into a thick band")),
        ("roll_tab", (D, "rolled sleeve with the buttoned tab that holds it")),
        ("none", (D, "plain sleeve end")),
    ),
    "sleeve_construction": _c(
        ("set_in", (D, "")), ("raglan", (D, "diagonal seams from neck to underarm (not drawn under a shirt collar)")),
        ("drop_shoulder", (D, "shoulder seam falls onto the arm, deeper armhole")),
        ("saddle_shoulder", (D, "a strip of seam across the top of the shoulder to the neck")),
        ("dolman", (D, "sleeve cut in one with the body: no armhole seam, very deep underarm")),
    ),
    "pockets": _c(
        ("none", (D, "")), ("chest_patch_single", (D, "")), ("chest_patch_double", (D, "")),
        ("chest_flap_single", (D, "patch under a buttoned pointed flap")), ("chest_flap_double", (D, "")),
        ("pencil_slot", (D, "chest patch with a stitched slot down its inner side")),
        ("western_smile", (D, "curved slits with arrow tacks")), ("bellows", (D, "four flap pockets with gusset lines")),
        ("welt", (D, "two jetted slits low on the front")), ("kangaroo", (D, "")),
        ("split_hand", (D, "a zip hoodie's pouch in two halves")), ("slash", (D, "steep welted hand-warmer slits")),
        ("utility_sleeve", (D, "zipped pocket on the upper left sleeve")),
        ("four_patch_guayabera", (D, "four buttoned patch pockets and the rows of pleats")),
        ("three_patch_chore", (D, "one chest and two large low patches")),
        ("hip_patch_double", (D, "two plain patches low on the front")),
        ("hip_flap_double", (D, "two patches with buttoned flaps low on the front")),
        ("five_pocket_jean", (N_, "a trouser pocket layout; not drawn on a top")),
        ("cargo", (A_, "drawn as bellows pockets on a top")),
    ),
    "hem": _c(
        ("curved_shirt_tail", (D, "")), ("straight_with_vents", (D, "small slits at the side seams with bar tacks")),
        ("straight", (D, "")), ("tennis_tail", (D, "vents, and the longer back showing below the front")),
        ("ribbed_band", (D, "")), ("raw", (D, "no stitch line, a few loose threads")),
    ),
}

_WOVEN_NOTES = {
    "corduroy": (D, "vertical wales, spacing set by corduroy_wale; heavy"),
    "seersucker": (D, "puckered stripes between flat ones; light"),
    "herringbone": (D, "chevron columns"), "twill": (D, "fine diagonal"), "denim": (D, "steep twill with pale weft; heavy"),
    "linen": (D, "short slub streaks; light"), "hopsack": (D, "small basket weave"), "tweed": (D, "flecks; super heavy, slight halo"),
    "ripstop": (D, "grid of heavier threads"), "waffle_weave": (D, "waffle grid; heavy"),
    "oxford": (N_, "plain at this size: oxford cloth's fine basket weave does not show; midweight"),
    "royal_oxford": (N_, "plain at this size, like oxford"), "fresco": (A_, "drawn as a basket weave; light"),
    "brushed_twill": (A_, "twill lines plus a soft edge (halo); heavy"),
    "gabardine": (A_, "drawn as a twill"), "cavalry_twill": (A_, "drawn as a single twill, not its double cord"),
    "whipcord": (A_, "drawn as a twill"),
    "flannel": (A_, "no texture of its own: heavy weight and a fuzzy edge (halo); wool fibre makes it heavier"),
    "satin": (A_, "no texture: drawn with a sheen highlight; light"), "sateen": (A_, "sheen highlight; light"),
    "waxed_cotton": (A_, "sheen highlight and heavy weight"), "melton": (A_, "no texture: drawn with the depth of a super-heavy cloth"),
    "moleskin": (A_, "no texture: the depth of a heavy cloth"), "canvas": (A_, "no texture: the depth of a heavy cloth"),
    "velvet": (N_, "pile and its sheen are not drawn yet; drawn as a plain midweight cloth"),
}
_KNIT_NOTES = {
    "pique": (D, "fine honeycomb dots"), "waffle_thermal": (D, "waffle grid"), "rib_1x1": (D, "fine vertical rib"),
    "rib_2x2": (D, "vertical rib"), "fisherman_rib": (D, "plump ribs with knotted stitches; heavy"),
    "cable": (D, "cables, scaled by knit_gauge; heavy"), "aran": (D, "chunky cables; super heavy"),
    "mesh": (D, "open holes"), "garter": (D, "ridged rows"), "sherpa": (D, "curly pile and fuzzy edge; super heavy"),
    "polar_fleece": (D, "soft nap and fuzzy edge; heavy"), "fleece_back": (D, "soft nap and fuzzy edge (worn fuzzy side out); heavy"),
    "shaker": (A_, "drawn as a rib; heavy"), "moss": (A_, "drawn as the pique dot"), "pointelle": (A_, "drawn as open mesh holes"),
    "terry_towelling": (A_, "loops drawn as the pique dot"), "slub_jersey": (A_, "slubs drawn as linen streaks"),
    "guernsey": (A_, "drawn as garter ridges; heavy"), "velour": (A_, "no texture: soft edge (halo)"),
    "french_terry": (A_, "smooth face: the depth of a heavy cloth only"),
}
COVERAGE["woven_structure"] = {
    v: _WOVEN_NOTES.get(v, (N_, "fabric/colour/pattern carry it: no visible surface at this size" if v not in ("dobby", "jacquard", "madras", "chambray")
                            else "its look is a pattern or colour effect, carried by the photo's fill"))
    for v in AXES["woven_structure"]}
COVERAGE["knit_structure"] = {
    v: _KNIT_NOTES.get(v, (N_, "a smooth face: shows only as weight" if v in ("jersey", "interlock", "flat_knit")
                           else "a colour pattern: carried by the photo's fill, not drawn"))
    for v in AXES["knit_structure"]}
COVERAGE["fiber"] = {
    v: {
        "linen": (D, "light weight and slub streaks when no fabric is known"), "cotton_linen": (D, "light weight, linen slubs"),
        "hemp": (A_, "drawn as linen slubs; midweight"), "cotton": (A_, "the default: no change"),
        "merino": (A_, "fine and clean: midweight, no halo"), "lambswool": (A_, "midweight; no halo drawn"),
        "shetland": (D, "heavier and a fuzzy edge (halo)"), "cashmere": (D, "soft edge (halo)"),
        "yak": (D, "heavier, soft edge"), "camel": (D, "heavier"), "alpaca": (D, "heavier, fuzzy edge"),
        "mohair": (D, "fuzzy edge"), "worsted_wool": (A_, "midweight, clean edge (the default look)"),
        "woolen_wool": (D, "one step heavier than the fabric alone (wool flannel vs cotton flannel)"),
        "silk": (D, "lighter and a sheen highlight"), "polyester": (D, "one step lighter than the fabric alone"),
        "nylon": (D, "lighter and a sheen highlight"), "acrylic": (A_, "drawn like wool of the same knit"),
        "viscose": (D, "lighter: fine edges"), "lyocell": (D, "lighter: fine edges"), "modal": (D, "lighter: fine edges"),
        "leather": (A_, "the depth of a heavy cloth; no leather surface or sheen"), "suede": (A_, "the depth of a heavy cloth; no nap"),
        "shearling": (D, "super heavy, sherpa curl and fuzzy edge"),
    }[v] for v in AXES["fiber"]}
COVERAGE["weight"] = {
    "lightweight": (D, "fine outline and inner lines, a touch narrower body"),
    "midweight": (D, "the reference drawing"),
    "heavyweight": (D, "heavier outline, wider body, rounder shoulder, deeper bands, doubled hem and cuff stitching, collar topstitch"),
    "super_heavy": (D, "all of heavyweight, more so"),
}


def coverage_counts() -> dict[str, tuple[int, int, int]]:
    """(drawn, approximate, not drawn) per axis."""
    return {ax: tuple(sum(1 for s, _ in vals.values() if s == st) for st in (D, A_, N_)) for ax, vals in COVERAGE.items()}
