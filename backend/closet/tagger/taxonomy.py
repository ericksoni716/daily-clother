"""The owner's menswear taxonomy (docs/menswear-taxonomy.json), as far as a front-view drawing can show it.

`AXES` is a frozen copy of the axes that are visible from the front; a test keeps it
equal to the JSON file, so an edit to the taxonomy shows up as a failing test, not as a
silently undrawn garment. `COVERAGE` says, for every value, whether the drawing shows
it exactly, approximately (and as what), or not yet. `top_drawing` turns taxonomy
values into template parameters.

`outfit_rules` reads the JSON itself (not a frozen copy): its `outfit` and `colors` blocks are the owner's
outfit rules, so editing the file changes how outfits are chosen (see `closet/outfit_rules.py`).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

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
# the shoe styles the drawing has a shape for
SHOE_STYLES = ("low_sneaker", "high_top", "runner", "slip_on", "loafer", "derby", "oxford", "boot", "chelsea_boot", "sandal")

# The taxonomy's footwear garments (its `garments` with category "footwear"), in its order: the app style each is
# (the JSON's app_style; "sandals" is the sandals category), what the drawing adds to that style, and how well the
# drawing shows it. A footwear id or one of the footwear block's words in the tagger's other_features picks these.
FOOTWEAR: dict[str, tuple[str, dict, str, str]] = {
    "patent_oxford": ("oxford", {"toe_cap": "none", "shine": True}, "drawn", "a plain-toe oxford with a patent gloss"),
    "plain_toe_oxford": ("oxford", {"toe_cap": "none"}, "drawn", "closed lacing, no toe cap"),
    "cap_toe_oxford": ("oxford", {"toe_cap": "stitched"}, "drawn", "closed lacing and a stitched toe cap"),
    "wholecut": ("oxford", {"toe_cap": "none", "wholecut": True}, "drawn", "closed lacing, no vamp seam"),
    "brogue": ("oxford", {"brogue": "full"}, "drawn", "a wingtip with punching; derby or oxford lacing as tagged; "
               "semi (medallion and cap) or quarter when named"),
    "derby": ("derby", {}, "drawn", "open lacing: quarters on top of the vamp, the tongue between them"),
    "monk_strap": ("derby", {"laces": False, "strap": "monk"}, "drawn", "a buckled strap across the throat, no laces"),
    "penny_loafer": ("loafer", {"strap": "penny"}, "drawn", "the saddle strap with its slot"),
    "tassel_loafer": ("loafer", {"strap": "tassel"}, "drawn", "a lace round the collar, tied at the throat, two tassels"),
    "horsebit_loafer": ("loafer", {"strap": "horsebit"}, "drawn", "a metal bit across the throat"),
    "driving_moc": ("loafer", {"strap": "none", "tread": "pebble", "heel": "flat"}, "drawn", "a plain loafer with rubber pebbles up the heel"),
    "chelsea_boot": ("chelsea_boot", {}, "drawn", "the chelsea boot with its elastic side"),
    "jodhpur_boot": ("boot", {"laces": False, "strap": "jodhpur", "shaft": 0.5}, "drawn", "a strap round the ankle, buckled on the side"),
    "chukka": ("boot", {"shaft": 0.42, "eyelets": 3}, "drawn", "an ankle boot with three eyelets"),
    "desert_boot": ("boot", {"shaft": 0.42, "eyelets": 2, "tread": "crepe"}, "drawn", "two eyelets on a honey crepe sole"),
    "service_boot": ("boot", {}, "drawn", "a laced leather boot"),
    "moc_toe_boot": ("boot", {"moc": True, "tread": "wedge"}, "drawn", "the moc toe seam on a flat white wedge sole"),
    "engineer_boot": ("boot", {"laces": False, "strap": "engineer", "shaft": 0.74}, "drawn", "a tall pull-on boot, buckled straps at the instep and the top"),
    "logger_boot": ("boot", {"shaft": 0.74, "eyelets": 8, "hooks": 4, "tread": "lug", "heel": "block"}, "drawn", "tall, speed hooks above the eyelets, a lug sole and block heel"),
    "hiking_boot": ("boot", {"shaft": 0.6, "eyelets": 6, "hooks": 3, "tread": "lug", "collar_pad": True}, "drawn", "a padded collar, speed hooks and a lug sole"),
    "duck_boot": ("boot", {"lower": "rubber", "eyelets": 5}, "drawn", "a rubber lower round the foot in the sole colour, laced leather above"),
    "rain_boot": ("boot", {"laces": False, "shaft": 0.82, "lower": "all", "heel": "flat"}, "drawn", "tall and laceless, rubber all over with a rim at the top"),
    "western_boot": ("boot", {"kind": "western_boot", "laces": False, "shaft": 0.88, "toe": "pointed", "heel": "cuban", "pull_tabs": True}, "drawn", "a tall stitched shaft, a pointed toe, a sloping cuban heel and a pull tab"),
    "combat_boot": ("boot", {"shaft": 0.74, "eyelets": 9, "tread": "lug"}, "drawn", "tall, laced high, a lug sole"),
    "snow_boot": ("boot", {"lower": "rubber", "collar_pad": True, "tread": "lug", "shaft": 0.62}, "drawn", "a rubber lower, a padded cuff and a lug sole"),
    "leather_court_sneaker": ("low_sneaker", {"kind": "leather_court_sneaker"}, "drawn", "a low sneaker, perforations on the toe"),
    "canvas_low_top": ("low_sneaker", {"foxing": True, "toe_cap": "rubber"}, "drawn", "a low sneaker with a foxing stripe and rubber toe cap"),
    "canvas_high_top": ("high_top", {}, "drawn", "a high top with its rubber toe"),
    "retro_court_shoe": ("low_sneaker", {"kind": "retro_court_shoe"}, "drawn", "a low sneaker, perforations and a toe overlay"),
    "basketball_shoe": ("high_top", {"collar_pad": True, "toe_cap": "none", "foxing": False, "sole": "chunky"}, "drawn", "a high top with a padded collar"),
    "skate_shoe": ("low_sneaker", {"tongue": "padded", "collar_pad": True}, "drawn", "a padded tongue above a padded collar"),
    "retro_runner": ("runner", {"kind": "retro_runner"}, "drawn", "a runner with a suede toe and side overlays"),
    "running_shoe": ("runner", {}, "drawn", "a runner"),
    "trail_runner": ("runner", {"tread": "lug"}, "drawn", "a runner on a lugged sole (a toggle lace when the lacing says so)"),
    "trainer": ("runner", {}, "approximate", "drawn as a running shoe"),
    "canvas_slip_on": ("slip_on", {}, "drawn", "a laceless canvas shoe"),
    "cleats": ("low_sneaker", {"tread": "cleats"}, "drawn", "studs under the sole"),
    "chunky_sneaker": ("runner", {"sole": "chunky"}, "drawn", "a runner on a chunky sole"),
    "boat_shoe": ("loafer", {"strap": "none", "lace_collar": True, "tread": "siped"}, "drawn", "a rawhide lace round the collar, tied at the side, on a white sole"),
    "camp_moc": ("loafer", {"strap": "none", "lace_collar": True, "tread": "siped"}, "approximate", "drawn as a boat shoe"),
    "espadrille": ("slip_on", {"tread": "jute", "foxing": False}, "drawn", "a slip-on on a braided rope sole"),
    "sandal": ("sandal", {"sandal": "two_strap"}, "drawn", "two buckled straps over a footbed"),
    "slide": ("sandal", {"sandal": "slide"}, "drawn", "one wide strap over a footbed"),
    "flip_flop": ("sandal", {"sandal": "thong"}, "drawn", "a thin strap from a post between the toes, back over the foot"),
    "moccasin_slipper": ("slip_on", {"moc": True, "collar_pad": True, "foxing": False}, "approximate", "a moc seam and a soft collar; no fleece texture"),
    "velvet_slipper": ("loafer", {"strap": "none"}, "approximate", "a plain loafer; no velvet nap"),
    "felt_clog": ("slip_on", {"backless": True, "foxing": False}, "drawn", "open at the back above the heel"),
}
# the footwear block's toe treatments and lacings, in its order, and what the drawing makes of each
FOOTWEAR_TOE_TREATMENT = {
    "plain": ({"toe_cap": "none"}, "drawn", ""), "cap_toe": ({"toe_cap": "stitched"}, "drawn", "a stitched toe cap"),
    "wingtip": ({"brogue": "full"}, "drawn", "on a derby or oxford: the wing and its punching"),
    "medallion": ({"brogue": "semi"}, "drawn", "on a derby or oxford: a punched toe and cap"),
    "apron": ({"moc": True}, "drawn", "a raised seam round the top of the toe (from the side, as a moc toe's)"),
    "split_toe": ({}, "not_drawn", "no split toe seam yet"),
    "rubber_toe_cap": ({"toe_cap": "rubber"}, "drawn", "the rubber toe of a canvas shoe"),
}
FOOTWEAR_LACING = {
    "closed_oxford": ({"style": "oxford"}, "drawn", "the facings meet under the vamp"),
    "open_derby": ({"style": "derby"}, "drawn", "the quarters on top of the vamp, the tongue between them"),
    "speed_hooks": ({"hooks": 3}, "drawn", "the top three lacing points are open metal hooks"),
    "d_rings": ({"rings": True}, "drawn", "metal D-rings instead of eyelets"),
    "ghillie": ({}, "not_drawn", "drawn as eyelets"), "slip_on": ({}, "drawn", "no laces"),
    "elastic_gussets": ({"gusset": True, "laces": False}, "drawn", "an elastic side panel, no laces"),
    "monk_single": ({"strap": "monk", "laces": False}, "drawn", "a buckled strap across the throat"),
    "monk_double": ({"strap": "double_monk", "laces": False}, "drawn", "two buckled straps across the throat"),
    "hook_and_loop": ({"strap": "velcro", "laces": False}, "drawn", "two straps across the instep, no laces"),
    "toggle_speed_lace": ({"toggle": True}, "drawn", "a cord lock above the top eyelet, the cord ends hanging"),
    "rawhide_around_collar": ({"lace_collar": True}, "drawn", "a lace round the collar, tied at the side"),
}
# other words for what the drawing shows, as the tagger may put them
_SHOE_WORDS = {
    "quarter brogue": {"brogue": "quarter"}, "semi brogue": {"brogue": "semi"}, "full brogue": {"brogue": "full"},
    "closed lacing": {"style": "oxford"}, "open lacing": {"style": "derby"},
    "penny strap": {"strap": "penny"}, "saddle strap": {"strap": "penny"}, "tassels": {"strap": "tassel"},
    "tassel": {"strap": "tassel"}, "horsebit": {"strap": "horsebit"}, "venetian": {"strap": "none"},
    "two strap": {"sandal": "two_strap"}, "ankle strap": {"sandal": "strap"}, "heel strap": {"sandal": "strap"},
    "strap sandal": {"sandal": "strap"}, "cap toe": {"toe_cap": "stitched"}, "toe cap": {"toe_cap": "stitched"},
}


def _say(word: str) -> str:
    return " " + re.sub(r"[^a-z0-9]+", " ", word.lower()).strip() + " "


def shoe_words(style: str, words: list[str]) -> tuple[str, dict, list[str]]:
    """What the tagger's own words (other_features) add to a shoe's drawing: (style, params, the words now drawn).
    A footwear id sets the style and its parameters (a brogue keeps a tagged derby lacing); the footwear block's
    toe treatments and lacings, and a few plain words ("tassels", "5 eyelets"), refine them, whichever comes first."""
    params: dict = {}
    used: list[str] = []
    found = []   # (kind, value, word) in the order the words come
    for word in words:
        said = _say(word)
        for fid in FOOTWEAR:
            if _say(fid) in said or (fid == "brogue" and " brogues " in said):
                found.append(("id", fid, word))
        for key, table in (("toe", FOOTWEAR_TOE_TREATMENT), ("lacing", FOOTWEAR_LACING)):
            for v in table:
                if _say(v) in said:
                    found.append((key, v, word))
        for phrase in _SHOE_WORDS:
            if _say(phrase) in said:
                found.append(("word", phrase, word))
        m = re.search(r" (\d+) eyelets? ", said)
        if m:
            found.append(("eyelets", int(m.group(1)), word))
    for kind, value, word in sorted(found, key=lambda x: x[0] != "id"):   # ids first, details over them
        if kind == "id":
            app, more, status, _ = FOOTWEAR[value]
            if value == "brogue":
                style = style if style in ("derby", "oxford") else "oxford"
            else:
                style = app
            params.update(more)
        elif kind == "eyelets":
            status = "drawn"
            params["eyelets"] = max(2, min(10, value))
        else:
            more, status, _ = ({"toe": FOOTWEAR_TOE_TREATMENT, "lacing": FOOTWEAR_LACING}[kind][value]
                               if kind != "word" else (_SHOE_WORDS[value], "drawn", ""))
            more = dict(more)
            if more.get("style") and style not in ("derby", "oxford"):
                more.pop("style")   # a lacing word only says which of the two dress shoes
            style = more.pop("style", style)
            if more.get("toe_cap") == "stitched" and params.get("brogue") == "full":   # a brogue with a cap is semi
                more = {"brogue": "semi"}
            params.update(more)
        if status == "drawn" and word not in used:
            used.append(word)
    return style, params, used

# The footwear block's other attributes: what each adds to the shoe drawing (and how well it shows), in its order
FOOTWEAR_TOE_SHAPE = {
    "round": ({}, "drawn", ""), "almond": ({"toe": "almond"}, "drawn", "a little lower and longer"),
    "chisel": ({"toe": "chisel"}, "approximate", "lower and longer; the flat chisel face is seen from above, not the side"),
    "pointed": ({"toe": "pointed"}, "drawn", "a low, long toe"),
    "moc_toe": ({"moc": True}, "drawn", "the raised U seam over the toe"),
}
FOOTWEAR_SOLE = {
    "leather": ({}, "drawn", "a dark sole with a welt stitch"), "rubber_city": ({}, "approximate", "drawn as a leather sole"),
    "studded_rubber": ({"tread": "lug"}, "approximate", "drawn as lugs"), "lug_commando": ({"tread": "lug"}, "drawn", "a thick sole cut into lugs"),
    "crepe": ({"tread": "crepe"}, "drawn", "a flat honey sole with a wavy edge"),
    "wedge": ({"tread": "wedge"}, "drawn", "a flat white block, no heel"),
    "cupsole": ({}, "drawn", "a sneaker's stitched rubber sole"), "vulcanized": ({"foxing": True}, "drawn", "the foxing stripe"),
    "eva_foam_midsole": ({}, "approximate", "a runner's sculpted midsole"),
    "siped_deck": ({"tread": "siped"}, "drawn", "a thin white sole"), "cleats": ({"tread": "cleats"}, "drawn", "studs under the sole"),
    "jute_rope": ({"tread": "jute"}, "drawn", "a braided rope sole"),
    "cork_footbed": ({}, "drawn", "a sandal's cork footbed"), "molded_slide": ({}, "approximate", "drawn as a footbed"),
}
FOOTWEAR_HEEL = {
    "flat": ({"heel": "flat"}, "drawn", "the sole runs flat to the back"), "low_stacked": ({"heel": "stacked"}, "drawn", "leather lifts"),
    "block": ({"heel": "block"}, "drawn", "a deeper heel"), "cuban": ({"heel": "cuban"}, "drawn", "tall, its back sloping in"),
}
# how high a boot's collar comes, in shoe lengths (a service boot is a six-inch boot)
_SHAFT = {"ankle_boot": 0.45, "boot_6in": 0.56, "boot_8in_plus": 0.74, "knee": 0.95}


def shoe_params(style: str, d: dict) -> tuple[str, dict]:
    """What the tagger's footwear fields add to a shoe's drawing: (style, params). The kind (`footwear`) sets the style
    and its parts; the toe, lacing, eyelets, sole, heel and height fields refine them."""
    params: dict = {}
    fid = d.get("footwear")
    if fid in FOOTWEAR:
        app, more, _, _ = FOOTWEAR[fid]
        style = (style if style in ("derby", "oxford") else "oxford") if fid == "brogue" else app
        params.update(more)
    toe = d.get("toe_treatment")
    if toe in FOOTWEAR_TOE_TREATMENT:
        more = dict(FOOTWEAR_TOE_TREATMENT[toe][0])
        if more.get("toe_cap") == "stitched" and params.get("brogue") == "full":   # a brogue with a cap is semi
            more = {"brogue": "semi"}
        params.update(more)
    lacing = d.get("lacing")
    if lacing in FOOTWEAR_LACING:
        more = dict(FOOTWEAR_LACING[lacing][0])
        if more.get("style") and style not in ("derby", "oxford"):
            more.pop("style")
        style = more.pop("style", style)
        if lacing == "slip_on" and style in ("derby", "oxford", "boot", "low_sneaker", "high_top", "runner"):
            more["laces"] = False
        params.update(more)
    if isinstance(d.get("eyelets"), int) and d["eyelets"] > 0 and params.get("laces") is not False:
        params["eyelets"] = max(2, min(10, d["eyelets"]))
    for key, table in (("toe_shape", FOOTWEAR_TOE_SHAPE), ("sole", FOOTWEAR_SOLE), ("heel", FOOTWEAR_HEEL)):
        if d.get(key) in table:
            params.update(table[d[key]][0])
    if d.get("upper_material") == "patent":
        params["shine"] = True
    height = d.get("footwear_height")
    if style in ("boot", "chelsea_boot") and height in _SHAFT:
        params["shaft"] = _SHAFT[height]
    elif style in ("low_sneaker", "high_top"):
        if height in ("mid", "high") and style == "low_sneaker":
            style = "high_top"
        elif height in ("no_show", "low") and style == "high_top":
            style = "low_sneaker"
        if height == "mid":
            params["shaft"] = 0.44
    return style, params


# The bottoms block: what each value adds to the trouser drawing (template parameters), and how well it shows
BOTTOM_DRAWING: dict[str, dict[str, tuple[dict, str, str]]] = {
    "waistband": {
        "belt_loops": ({"waist": "belt"}, "drawn", "belt loops"),
        "side_adjusters": ({"waist": "adjusters"}, "drawn", "a buckled tab each side, no loops"),
        "extended_tab": ({"waist": "tab"}, "drawn", "a buttoned tab past the fly"),
        "gurkha": ({"waist": "gurkha"}, "drawn", "a deep band, straps buckled each side"),
        "elastic_drawcord": ({"waist": "drawstring"}, "drawn", "gathered, with cords"),
        "half_elastic": ({"waist": "half_elastic"}, "drawn", "flat in front, gathered at the sides"),
        "drawstring": ({"waist": "drawstring"}, "drawn", "gathered, with cords"),
        "brace_buttons": ({"waist": "braces"}, "drawn", "buttons along the top of the band"),
    },
    "fly": {"zip": ({"fly": "zip"}, "drawn", "the J-stitch"), "button": ({"fly": "button"}, "drawn", "its buttons down the fly"),
            "none": ({"fly": "none"}, "drawn", "a centre seam, no fly")},
    "front": {
        "flat": ({"pleats": 0}, "drawn", ""), "single_pleat": ({"pleats": 1}, "drawn", "one pleat each side"),
        "double_pleat": ({"pleats": 2}, "drawn", "two pleats each side"),
        "reverse_pleat": ({"pleats": 1, "pleat_dir": "reverse"}, "approximate",
                          "a pleat with a small lip toward the pocket: at grid size it looks like any single pleat"),
        "forward_pleat": ({"pleats": 1, "pleat_dir": "forward"}, "approximate",
                          "a pleat with a small lip toward the fly: at grid size it looks like any single pleat"),
    },
    "rise": {"low": ({"rise": "low"}, "drawn", "a shorter fly and crotch"), "mid": ({}, "drawn", ""),
             "high": ({"rise": "high"}, "drawn", "a longer fly and crotch")},
    "leg": {v: ({"leg": v}, "drawn", "") for v in ("skinny", "slim", "tapered", "straight", "relaxed", "wide", "bootcut", "flare",
                                                    "barrel")},
    "break": {
        "no_break": ({}, "drawn", ""), "slight": ({"break": "slight"}, "drawn", "a shallow fold above the hem"),
        "full": ({"break": "full"}, "drawn", "a deep fold above the hem"),
        "cropped": ({"length": "ankle"}, "drawn", "ends above the ankle"),
        "stacked": ({"break": "stacked"}, "drawn", "three folds bunched above the hem"),
    },
    "hem_finish": {
        "plain": ({"hem": "plain"}, "drawn", ""), "turn_up": ({"hem": "turnup"}, "drawn", "a turned-up cuff"),
        "rolled_cuff": ({"hem": "rolled"}, "drawn", "rolled up twice"), "ribbed_cuff": ({"hem": "rib"}, "drawn", "a knitted cuff"),
        "raw": ({"hem": "raw"}, "drawn", "a frayed edge"),
        "chain_stitched": ({"hem": "chain"}, "drawn", "a row of slanting stitches above the hem"),
        "split": ({"hem": "split"}, "drawn", "a short slit at the outer seam"),
        "notched": ({"hem": "notched"}, "drawn", "a small V cut into the hem at the outer seam"),
    },
    "crease": {"pressed": ({"crease": True}, "drawn", "a line down each leg"), "none": ({"crease": False}, "drawn", "")},
    "pockets": {
        "slant": ({"pockets": "slant"}, "drawn", ""), "vertical_on_seam": ({"pockets": "side"}, "drawn", "an opening in the side seam"),
        "scoop": ({"pockets": "scoop"}, "drawn", "the curved jeans pocket"),
        "frog_mouth": ({"pockets": "frog"}, "drawn", "a horizontal opening under the band"),
        "coin": ({"coin": True}, "drawn", "the watch pocket"),
        "back_welt_single": ({}, "not_drawn", "on the back: the drawing shows the front"),
        "back_welt_double": ({}, "not_drawn", "on the back: the drawing shows the front"),
        "back_patch": ({}, "not_drawn", "on the back: the drawing shows the front"),
        "back_flap": ({}, "not_drawn", "on the back: the drawing shows the front"),
        "cargo": ({"cargo": True}, "drawn", "bellows pockets on the thighs"),
        "hammer_loop": ({"extra_pockets": ["hammer"]}, "drawn", "a loop on the left side"),
        "rule_pocket": ({"extra_pockets": ["rule"]}, "drawn", "a narrow pocket on the right thigh"),
        "zip_pocket": ({"extra_pockets": ["zip"]}, "drawn", "a zip on each thigh"),
    },
    "back_details": {
        "double_knee": ({"panels": ["double_knee"]}, "drawn", "a panel over each knee"),
        "gusseted_crotch": ({"panels": ["gusset"]}, "drawn", "a diamond set into the crotch"),
        "back_yoke": ({}, "not_drawn", "on the back"), "rivets": ({"rivets": True}, "drawn", "copper rivets at the front pocket corners"),
        "back_patch_label": ({}, "not_drawn", "on the back"), "darts": ({}, "not_drawn", "on the back"),
        "centre_back_v_loop": ({}, "not_drawn", "on the back"),
    },
    "denim_fades": {
        "whiskers": ({"fades": ["whiskers"]}, "drawn", "pale creases fanning from the crotch"),
        "honeycombs": ({}, "not_drawn", "behind the knees"), "stacks": ({"fades": ["stacks"]}, "drawn", "pale bands above the hem"),
        "train_tracks": ({"fades": ["tracks"]}, "drawn", "pale lines down the outer seams"),
        "roping": ({"fades": ["roping"]}, "drawn", "pale slanting twists along the hem"),
        "pocket_fade": ({"fades": ["pocket"]}, "drawn", "the pocket edge worn pale"),
        "knee_fade": ({"fades": ["knee"]}, "drawn", "a pale patch at each knee"),
    },
    "distressing": {
        "knee_rip": ({"distress": ["knee_rip"]}, "drawn", "a hole with white threads across it"),
        "frayed_hem": ({"hem": "raw"}, "drawn", "frayed threads at the hem"),
        "abrasion": ({"distress": ["abrasion"]}, "drawn", "a pale worn patch on the thigh"),
        "patched": ({"distress": ["patched"]}, "drawn", "a stitched patch on the thigh"),
        "sashiko_repair": ({"distress": ["sashiko"]}, "drawn", "a patch with rows of white running stitch"),
    },
}
# the bottoms field each block key is told in, on the tagger's Details
BOTTOM_FIELDS = {"waistband": "waistband", "fly": "fly", "front": "trouser_front", "rise": "rise", "leg": "leg_shape",
                 "break": "trouser_break", "hem_finish": "hem_finish", "crease": "crease", "pockets": "trouser_pockets",
                 "back_details": "back_details", "denim_fades": "denim_fades", "distressing": "distressing"}


def bottom_params(category: str, d: dict) -> dict:
    """What the tagger's bottoms fields add to a trouser drawing (template parameters), where they were told."""
    params: dict = {}
    for key, field in BOTTOM_FIELDS.items():
        told = d.get(field)
        for value in (told if isinstance(told, list) else [told]):
            if value not in BOTTOM_DRAWING[key]:
                continue
            for k, v in BOTTOM_DRAWING[key][value][0].items():
                if category == "shorts" and k in ("length", "break"):
                    continue
                params[k] = sorted(set(params.get(k, [])) | set(v)) if isinstance(v, list) else v
    if params.get("pleats") and "crease" not in params and d.get("crease") != "none":
        params["crease"] = True
    if category == "shorts" and isinstance(d.get("inseam"), int) and d["inseam"] > 0:
        params["inseam"] = d["inseam"]
    return params


def wash_hex(wash) -> str | None:
    """The colour a denim wash is drawn in, when no colour was measured."""
    return shade_hex(DENIM_WASH_SHADE.get(wash)) if wash in DENIM_WASH_SHADE else None
# The garments (kinds of clothing) of the taxonomy's `garments` block, with their taxonomy category; footwear and
# accessories are left out (shoes have their own style field). A test keeps this equal to the JSON.
GARMENTS: dict[str, str] = {
    "t_shirt": "knit_top", "henley": "knit_top", "polo": "knit_top", "rugby_shirt": "knit_top",
    "dress_shirt": "woven_shirt", "ocbd": "woven_shirt", "casual_button_up": "woven_shirt", "flannel_shirt": "woven_shirt",
    "work_shirt": "woven_shirt", "western_shirt": "woven_shirt", "camp_collar_shirt": "woven_shirt",
    "popover_shirt": "woven_shirt", "band_collar_shirt": "woven_shirt", "guayabera": "woven_shirt",
    "overshirt": "woven_shirt", "tuxedo_shirt": "woven_shirt",
    "crewneck_sweatshirt": "sweatshirt", "hoodie": "sweatshirt",
    "pullover_sweater": "knitwear", "cardigan": "knitwear", "sweater_vest": "knitwear",
    "chore_coat": "outerwear", "trucker_jacket": "outerwear", "bomber": "outerwear", "varsity_jacket": "outerwear",
    "harrington": "outerwear", "field_jacket": "outerwear", "waxed_jacket": "outerwear", "peacoat": "outerwear",
    "overcoat": "outerwear", "trench_coat": "outerwear", "parka": "outerwear", "puffer": "outerwear",
    "quilted_jacket": "outerwear", "fleece_jacket": "outerwear", "leather_jacket": "outerwear", "barn_jacket": "outerwear",
    "blazer": "tailoring", "sport_coat": "tailoring", "suit_jacket": "tailoring",
    "chinos": "bottoms", "dress_trousers": "bottoms", "jeans": "bottoms", "corduroys": "bottoms", "fatigues": "bottoms",
    "cargo_pants": "bottoms", "work_pants": "bottoms", "sweatpants": "bottoms", "shorts": "bottoms",
    "performance_tee": "activewear", "running_long_sleeve": "activewear", "running_singlet": "activewear",
    "compression_top": "activewear", "base_layer": "activewear", "athletic_half_zip": "activewear",
    "track_jacket": "activewear", "windbreaker": "activewear", "softshell_jacket": "activewear", "rain_shell": "activewear",
    "fleece_pullover": "activewear", "soccer_jersey": "activewear", "basketball_jersey": "activewear",
    "hockey_jersey": "activewear", "baseball_jersey": "activewear", "cycling_jersey": "activewear",
    "running_shorts": "activewear", "two_in_one_shorts": "activewear", "training_shorts": "activewear",
    "basketball_shorts": "activewear", "compression_tights": "activewear", "track_pants": "activewear",
    "tech_pants": "activewear", "joggers": "activewear", "open_hem_sweatpants": "activewear",
    "pajama_set_woven": "loungewear", "pajama_set_knit": "loungewear", "sleep_shorts": "loungewear",
    "lounge_pants": "loungewear", "lounge_knit_set": "loungewear", "lounge_sweatsuit": "loungewear", "robe": "loungewear",
    "kimono_robe": "loungewear", "smoking_jacket": "loungewear",
}
SPORT_KINDS = frozenset(g for g, c in GARMENTS.items() if c == "activewear")
LOUNGE_KINDS = frozenset(g for g, c in GARMENTS.items() if c == "loungewear")
# The app's category for each garment: the JSON's `app_category` where it gives one (a test checks), otherwise
# the usual one for its taxonomy category. None for a set (a pyjama set, a sweatsuit): it is a top or a bottom.
_APP_BY_TAXONOMY = {"knit_top": "tee", "woven_shirt": "shirt", "sweatshirt": "sweater", "knitwear": "sweater",
                    "outerwear": "jacket", "tailoring": "jacket", "bottoms": "trousers"}
APP_CATEGORY: dict[str, str | None] = {
    **{g: _APP_BY_TAXONOMY.get(c) for g, c in GARMENTS.items()},
    "polo": "polo", "rugby_shirt": "polo", "hoodie": "hoodie", "peacoat": "coat", "overcoat": "coat",
    "trench_coat": "coat", "parka": "coat",
    "jeans": "jeans", "shorts": "shorts", "chinos": "trousers", "dress_trousers": "trousers", "corduroys": "trousers",
    "fatigues": "trousers", "cargo_pants": "trousers", "work_pants": "trousers", "sweatpants": "trousers",
    "performance_tee": "tee", "running_long_sleeve": "tee", "running_singlet": "tee", "compression_top": "tee",
    "base_layer": "tee", "athletic_half_zip": "sweater", "track_jacket": "jacket", "windbreaker": "jacket",
    "softshell_jacket": "jacket", "rain_shell": "jacket", "fleece_pullover": "sweater", "soccer_jersey": "tee",
    "basketball_jersey": "tee", "hockey_jersey": "tee", "baseball_jersey": "shirt", "cycling_jersey": "tee",
    "running_shorts": "shorts", "two_in_one_shorts": "shorts", "training_shorts": "shorts", "basketball_shorts": "shorts",
    "compression_tights": "trousers", "track_pants": "trousers", "tech_pants": "trousers", "joggers": "trousers",
    "open_hem_sweatpants": "trousers", "sleep_shorts": "shorts", "lounge_pants": "trousers",
    "pajama_set_woven": None, "pajama_set_knit": None, "lounge_knit_set": None, "lounge_sweatsuit": None,
    "robe": "coat", "kimono_robe": "coat", "smoking_jacket": "jacket",
}
_BOTTOM_APP = ("jeans", "trousers", "shorts")


def kinds_for(category: str | None) -> tuple[str, ...]:
    """The garments that can be an item of the app's category: a top's kinds or a bottom's (sets are both)."""
    bottom = category in _BOTTOM_APP
    return tuple(g for g, app in APP_CATEGORY.items() if app is None or (app in _BOTTOM_APP) == bottom)


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
    "pique": "pique", "moss": "moss", "terry_towelling": "terry", "mesh": "mesh", "pointelle": "pointelle",
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
_SHEEN_FABRICS = {"satin", "sateen", "waxed_cotton", "velvet"}
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
    elif tex in ("cable_knit", "rib_knit", "fisherman_rib", "waffle", "garter", "moss"):
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
    # the kind of garment says what no axis does
    kind = g.get("garment")
    if kind in _PULLOVERS and placket == "snap":
        p["front"] = "half"   # a pullover's snaps close a short placket, not a front that opens to the hem
    if kind == "fleece_pullover":
        # the classic snap-front fleece: a contrast colour (the trim colour) binds its edges, and a second
        # colour (when one is seen) is cut into the yoke, sleeves and pocket
        if g.get("contrast_trim"):
            p["binding"] = True
        if g.get("second_color"):
            p["colorblock"] = ("yoke", "sleeves", "pocket")
    if kind == "trench_coat":
        p["belt"] = True   # the self belt buckled round the waist
    elif kind == "parka":   # long and hooded: the hood replaces a collar, a zip closes a front left open
        if p.get("collar") not in ("notch", "peak", "shawl"):
            p["neck"] = "hood"
            p.pop("collar", None)
            if p["front"] == "none" or (placket is None and p["front"] == "buttons"):
                p["front"] = "zip"
                p.pop("buttons", None)
        if p["length"] in ("regular", "cropped"):
            p["length"] = "long"
    elif kind == "varsity_jacket":
        if collar in ("stand", "none") and neckline != "hood":
            p["neck"], p["collar"] = "collar", "rib"   # the knitted collar, as on a bomber
            p["front"] = "zip" if placket == "zip_full" else "buttons"
            if placket != "zip_full":
                p["fastener"] = "snap"
        if g.get("cuff") is None:
            p["cuffs"] = "rib"
        if g.get("hem") is None:
            p["hem"] = "rib"
        if g.get("second_color"):
            p["colorblock"] = ("sleeves",)   # the leather sleeves, in the second colour seen
    elif kind == "robe":   # a wrap front held by a sash, at least to the knee
        p["belt"] = "sash"
        if p["length"] in ("regular", "cropped", "long"):
            p["length"] = "knee"
            if p.get("block") == "jacket":
                p["block"] = "coat"
    elif kind == "waxed_jacket":
        extras["collar_color"] = "#5a3d26"   # the brown corduroy collar
    g = {**g, "fabric": _KIND_FABRIC[kind]} if kind in _KIND_FABRIC and _fabric(g) in (None, "unknown") else g
    if g.get("side_stripe") and p["sleeve"] != "none":
        p["stripes"] = "sleeve"   # a track jacket's stripes run down the sleeves
    # notes for what is drawn as something close
    approx = {
        "convertible": "convertible cuff drawn as a one-button barrel cuff",
        "cargo": "cargo pockets on a top drawn as bellows pockets",
        "five_pocket_jean": "five-pocket layout belongs to jeans: not drawn on a top",
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


# the cloth a kind of top is drawn in when none was seen
_KIND_FABRIC = {"trench_coat": "gabardine", "varsity_jacket": "melton", "waxed_jacket": "waxed_cotton"}

_PULLOVERS = ("fleece_pullover", "athletic_half_zip", "crewneck_sweatshirt", "hoodie", "pullover_sweater", "base_layer",
              "running_long_sleeve", "compression_top")

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
    "casual_button_up": dict(garment="casual_button_up", collar="point", placket="front_placket", cuff="barrel_1",
                             pockets="chest_patch_single", hem="straight_with_vents", fabric="poplin"),
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
    "fleece_pullover": dict(garment="fleece_pullover", collar="stand", placket="snap", placket_buttons=4,
                            pockets="chest_flap_single", hem="straight", cuff="open_hem", fabric="polar_fleece",
                            contrast_trim=True, second_color=True),
    "performance_tee": dict(garment="performance_tee", neckline="crew", sleeve_length="short", sleeve_construction="raglan",
                            hem="straight", fit="slim", fabric="mesh", fiber="polyester"),
    "athletic_half_zip": dict(garment="athletic_half_zip", neckline="quarter_zip", placket="zip_quarter",
                              sleeve_construction="raglan", cuff="open_hem", hem="straight", fit="slim", fabric="interlock",
                              fiber="polyester", weight="lightweight"),
    "track_jacket": dict(garment="track_jacket", collar="stand", placket="zip_full", pockets="split_hand", cuff="rib_knit",
                         hem="ribbed_band", fabric="interlock", fiber="polyester", side_stripe=True),
    "trench_coat": dict(garment="trench_coat", collar="notch_lapel", placket="double_breasted", placket_buttons=6,
                        pockets="slash", hem="straight", fabric="gabardine", length="knee"),
    "parka": dict(garment="parka", neckline="hood", placket="zip_full", pockets="bellows", hem="straight", cuff="rib_knit",
                  fit="relaxed", fabric="ripstop", length="long", weight="heavyweight"),
    "varsity_jacket": dict(garment="varsity_jacket", collar="stand", placket="snap", placket_buttons=5, pockets="slash",
                           cuff="rib_knit", hem="ribbed_band", fabric="melton", second_color=True),
    "waxed_jacket": dict(garment="waxed_jacket", collar="point", placket="zip_full", pockets="hip_flap_double",
                         hem="straight", cuff="barrel_1", fabric="waxed_cotton"),
    "suit_jacket": dict(collar="peak_lapel", placket="front_placket", placket_buttons=1, pockets="welt", hem="straight",
                        fit="tailored", fabric="plain", fiber="worsted_wool", closure_material="corozo"),
}


# ---- the footwear block's attributes, the bottoms block and the colours, in the JSON's order (tests keep them equal)
FOOTWEAR_AXES: dict[str, tuple[str, ...]] = {
    "toe_shape": ("round", "almond", "chisel", "pointed", "moc_toe"),
    "laces": ("flat_waxed", "round_waxed", "flat_cotton", "round_rope", "rawhide"),
    "sole": ("leather", "rubber_city", "studded_rubber", "lug_commando", "crepe", "wedge", "cupsole", "vulcanized",
             "eva_foam_midsole", "siped_deck", "cleats", "jute_rope", "cork_footbed", "molded_slide"),
    "construction": ("goodyear_welt", "storm_welt", "blake", "stitchdown", "cemented", "vulcanized", "moccasin"),
    "height": ("no_show", "low", "mid", "high", "ankle_boot", "boot_6in", "boot_8in_plus", "knee"),
    "heel": ("flat", "low_stacked", "block", "cuban"),
    "upper_material": ("smooth_calf", "pebble_grain", "suede", "roughout", "nubuck", "shell_cordovan", "patent",
                       "oiled_pull_up", "canvas", "knit_mesh", "synthetic_leather", "waxed_canvas", "rubber", "velvet",
                       "felt_wool", "woven_leather"),
    "leather_colorways": ("black", "dark_brown", "mid_brown", "tan", "cognac", "oxblood", "walnut", "snuff_suede",
                          "sand_suede", "navy_suede", "grey_suede"),
    "sneaker_colorways": ("white", "off_white", "black", "grey", "navy", "cream_gum_sole", "multi"),
}
BOTTOM_AXES: dict[str, tuple[str, ...]] = {
    "waistband": ("belt_loops", "side_adjusters", "extended_tab", "gurkha", "elastic_drawcord", "half_elastic",
                  "drawstring", "brace_buttons"),
    "fly": ("zip", "button", "none"),
    "front": ("flat", "single_pleat", "double_pleat", "reverse_pleat", "forward_pleat"),
    "rise": ("low", "mid", "high"),
    "leg": ("skinny", "slim", "tapered", "straight", "relaxed", "wide", "bootcut", "flare", "barrel"),
    "break": ("no_break", "slight", "full", "cropped", "stacked"),
    "hem_finish": ("plain", "turn_up", "rolled_cuff", "ribbed_cuff", "raw", "chain_stitched", "split", "notched"),
    "crease": ("pressed", "none"),
    "pockets": ("slant", "vertical_on_seam", "scoop", "frog_mouth", "coin", "back_welt_single", "back_welt_double",
                "back_patch", "back_flap", "cargo", "hammer_loop", "rule_pocket", "zip_pocket"),
    "back_details": ("double_knee", "gusseted_crotch", "back_yoke", "rivets", "back_patch_label", "darts",
                     "centre_back_v_loop"),
    "denim_washes": ("raw", "rinse", "dark", "mid", "light", "bleached", "stone", "acid", "black", "washed_black", "grey",
                     "ecru", "white", "overdyed"),
    "denim_fades": ("whiskers", "honeycombs", "stacks", "train_tracks", "roping", "pocket_fade", "knee_fade"),
    "distressing": ("knee_rip", "frayed_hem", "abrasion", "patched", "sashiko_repair"),
}
# shorts: the usual inseam (inches, low and high) of each kind
SHORTS_INSEAM_IN: dict[str, tuple[int, int]] = {
    "running": (3, 5), "short_chino": (5, 7), "chino": (7, 9), "denim": (7, 10), "cargo": (9, 11), "basketball": (9, 11),
    "boardshorts": (7, 20), "swim_trunks": (3, 7), "linen_pull_on": (6, 8), "tailored": (6, 8), "sweat": (6, 9),
}
# the owner's named shades: name -> (hex, the app's colour word it is a shade of)
SHADES: dict[str, tuple[str, str]] = {
    "black": ("#1a1a1a", "black"), "faded_black": ("#2b2b2b", "black"), "charcoal": ("#36393d", "grey"),
    "slate": ("#5a6470", "grey"), "mid_grey": ("#8a8d91", "grey"), "heather_grey": ("#a3a6a8", "grey"),
    "light_grey": ("#c9cacc", "grey"), "stone": ("#c9bfae", "tan"), "khaki": ("#c3b091", "tan"),
    "sand": ("#d6c4a2", "tan"), "camel": ("#b5875a", "tan"), "natural_flax": ("#cbbd9f", "tan"),
    "tobacco": ("#7a5230", "brown"), "chocolate": ("#4a3121", "brown"), "mid_brown": ("#7b5536", "brown"),
    "cognac": ("#9a5a2c", "brown"), "rust": ("#a4492a", "orange"), "coral": ("#e5735c", "orange"),
    "oxblood": ("#4e1a1d", "burgundy"), "burgundy": ("#6d1f2a", "burgundy"), "brick": ("#9c3d2e", "red"),
    "red": ("#b22a2a", "red"), "mustard": ("#c9a227", "yellow"), "butter": ("#f0e3a1", "yellow"),
    "olive": ("#5f6b3a", "olive"), "army_green": ("#4b5320", "olive"), "sage": ("#a3ad8f", "green"),
    "forest_green": ("#22422c", "green"), "hunter_green": ("#355e3b", "green"), "teal": ("#2a6f74", "green"),
    "navy": ("#1f2a44", "navy"), "midnight": ("#191d2e", "navy"), "raw_indigo": ("#23304a", "navy"),
    "royal_blue": ("#2a4ea0", "blue"), "cobalt": ("#1e4fb8", "blue"), "mid_wash_denim": ("#5b7aa3", "blue"),
    "chambray_blue": ("#8ca5c7", "light_blue"), "oxford_blue": ("#a9c4e0", "light_blue"),
    "sky_blue": ("#bcd4ea", "light_blue"), "light_wash_denim": ("#9bb2cf", "light_blue"),
    "shirting_pink": ("#f1c8cf", "pink"), "dusty_rose": ("#c99a9a", "pink"), "lavender": ("#c8bfe0", "purple"),
    "plum": ("#4b2a45", "purple"), "optic_white": ("#f7f7f5", "white"), "off_white": ("#f1eee6", "cream"),
    "ecru": ("#e8e0cc", "cream"), "cream": ("#efe6d2", "cream"), "oatmeal": ("#d9ccb4", "cream"),
    "bone": ("#e3dccb", "cream"),
}
# the owner's colour families (app colour words), which the outfit engine and What's missing match colours by
COLOR_FAMILIES: dict[str, tuple[str, ...]] = {
    "neutral": ("black", "white", "grey", "navy", "tan", "cream", "brown", "olive"),
    "earth": ("olive", "orange", "brown", "yellow", "green", "burgundy", "cream"),
    "cool": ("blue", "light_blue", "grey", "purple", "green"),
    "warm": ("red", "orange", "yellow", "pink", "burgundy"),
    "bright": ("blue", "red", "orange", "yellow", "pink", "purple"),
}
# how a cloth changes the look of its colour
FABRIC_EFFECTS = ("denim", "black_cotton", "linen", "brushed", "corduroy_velvet", "suede", "worsted_wool",
                  "heathered_marled", "garment_pigment_dyed", "mercerised_silk_satin", "synthetic_performance", "leather",
                  "sun_fade")
# the colour a denim wash is drawn in when no colour was measured: a shade's name, or a hex of its own
DENIM_WASH_SHADE = {
    "raw": "raw_indigo", "rinse": "#283858", "dark": "#2f4468", "mid": "mid_wash_denim", "light": "light_wash_denim",
    "bleached": "sky_blue", "stone": "#7189ad", "acid": "#8b9db8", "black": "black", "washed_black": "faded_black",
    "grey": "mid_grey", "ecru": "ecru", "white": "optic_white", "overdyed": None,
}


def shade_hex(name) -> str | None:
    """A shade's colour: a shade of the owner's by name, or a hex given as it is."""
    if isinstance(name, str) and name.startswith("#"):
        return name
    return SHADES[name][0] if name in SHADES else None


def nearest_shade(hex_: str, color: str | None = None) -> str | None:
    """The owner's shade closest to a colour, among the shades of the colour word `color` when one is given."""
    try:
        r, g, b = (int(hex_.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, AttributeError):
        return None
    best, far = None, float("inf")
    for name, (h, app) in SHADES.items():
        if color and app != color:
            continue
        r2, g2, b2 = (int(h[i:i + 2], 16) for i in (1, 3, 5))
        d = (r - r2) ** 2 + (g - g2) ** 2 + (b - b2) ** 2
        if d < far:
            best, far = name, d
    return best


def families(color: str | None) -> tuple[str, ...]:
    """The owner's colour families a colour word belongs to."""
    return tuple(f for f, colors in COLOR_FAMILIES.items() if color in colors)


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
        ("hidden_button_down", (D, "a soft-roll point collar with no buttons showing: its buttons are under the points")),
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
                                "the top row set wider; told 1 or 2 buttons, those are the ones that fasten (6x1, 6x2)")),
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
        ("ribbed_band", (D, "a knit rib band; under a woven shirt collar (a trucker) a buttoned waistband with side adjusters")), ("raw", (D, "no stitch line, a few loose threads")),
    ),
}

_WOVEN_NOTES = {
    "corduroy": (D, "vertical wales, spacing set by corduroy_wale; heavy"),
    "seersucker": (D, "puckered stripes between flat ones; light"),
    "herringbone": (D, "chevron columns"), "twill": (D, "fine diagonal"), "denim": (D, "steep twill with pale weft; heavy"),
    "linen": (D, "sparse short slub streaks; light"), "hopsack": (D, "small basket weave"), "tweed": (D, "flecks; super heavy, slight halo"),
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
    "velvet": (A_, "a soft sheen; the pile itself is not drawn"),
}
_KNIT_NOTES = {
    "pique": (D, "fine honeycomb dots"), "waffle_thermal": (D, "waffle grid"), "rib_1x1": (D, "fine vertical rib"),
    "rib_2x2": (D, "vertical rib"), "fisherman_rib": (D, "plump ribs with knotted stitches; heavy"),
    "cable": (D, "cables, scaled by knit_gauge; heavy"), "aran": (D, "chunky cables; super heavy"),
    "mesh": (D, "open holes"), "garter": (D, "ridged rows"), "sherpa": (D, "curly pile and fuzzy edge; super heavy"),
    "polar_fleece": (D, "soft nap and fuzzy edge; heavy"), "fleece_back": (D, "soft nap and fuzzy edge (worn fuzzy side out); heavy"),
    "shaker": (A_, "drawn as a rib; heavy"), "moss": (D, "seed-stitch bumps, each row set over from the last"),
    "pointelle": (D, "eyelets spaced in a diamond lattice, plain knit between"), "terry_towelling": (D, "a pile of small loops"), "slub_jersey": (A_, "slubs drawn as linen streaks"),
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
    "lightweight": (D, "fine outline and inner lines, a touch narrower body, faint drape folds from the underarms and at the elbows"),
    "midweight": (D, "the reference drawing"),
    "heavyweight": (D, "heavier outline, wider body, rounder shoulder, deeper bands with a soft shade where the body meets them, doubled hem and cuff stitching, collar topstitch"),
    "super_heavy": (D, "all of heavyweight, more so"),
}

COVERAGE["footwear"] = {fid: (status, note) for fid, (_, _, status, note) in FOOTWEAR.items()}
COVERAGE["toe_treatment"] = {v: (status, note) for v, (_, status, note) in FOOTWEAR_TOE_TREATMENT.items()}
COVERAGE["lacing"] = {v: (status, note) for v, (_, status, note) in FOOTWEAR_LACING.items()}
COVERAGE["shoe_style"] = {
    "low_sneaker": (D, ""), "high_top": (D, ""), "runner": (D, ""), "slip_on": (D, ""), "loafer": (D, ""),
    "derby": (D, "open lacing"), "oxford": (D, "closed lacing"), "boot": (D, ""), "chelsea_boot": (D, ""),
    "sandal": (D, "a footbed on an outsole, with straps"),
}
COVERAGE["loafer_strap"] = {
    "penny": (D, "the default"), "tassel": (D, ""), "horsebit": (D, ""), "none": (D, "a venetian: the moc seam only"),
}
COVERAGE["brogue"] = {
    "none": (D, ""), "quarter": (D, "punching along the toe cap"), "semi": (D, "a medallion, and punching along the cap and seams"),
    "full": (D, "a wingtip: the wing, a medallion and punching"),
}
COVERAGE["sandal"] = {
    "slide": (D, "one wide strap"), "two_strap": (D, "the default: two buckled straps"),
    "strap": (D, "forefoot, instep, ankle and heel straps"),
}

COVERAGE["toe_shape"] = {v: (status, note) for v, (_, status, note) in FOOTWEAR_TOE_SHAPE.items()}
COVERAGE["sole"] = {v: (status, note) for v, (_, status, note) in FOOTWEAR_SOLE.items()}
COVERAGE["heel"] = {v: (status, note) for v, (_, status, note) in FOOTWEAR_HEEL.items()}
COVERAGE["height"] = {
    "no_show": (A_, "drawn as a low shoe; the sock is not drawn"), "low": (D, "a low shoe"),
    "mid": (D, "a sneaker's collar over the ankle bone"), "high": (D, "a high top"),
    "ankle_boot": (D, "a short boot shaft"), "boot_6in": (D, "the six-inch boot shaft"),
    "boot_8in_plus": (D, "a taller shaft"), "knee": (A_, "the tallest shaft the boot drawing has, below the knee"),
}
COVERAGE["eyelets_typical"] = {k: (D, "the eyelets counted on one side; the usual number when not told")
                               for k in ("dress", "sneaker", "ankle_boot", "work_boot")}
COVERAGE["laces"] = {v: (N_, "the laces are drawn in one weight whatever their kind")
                     for v in ("flat_waxed", "round_waxed", "flat_cotton", "round_rope")}
COVERAGE["laces"]["rawhide"] = (A_, "drawn as a lace round the collar on a boat shoe; elsewhere as any lace")
COVERAGE["construction"] = {
    "goodyear_welt": (A_, "the welt stitch round the sole"), "storm_welt": (A_, "the welt stitch round the sole"),
    "blake": (N_, "inside the shoe"), "stitchdown": (N_, "too small to draw"), "cemented": (N_, "glued: nothing to see"),
    "vulcanized": (A_, "the foxing stripe, when the kind of shoe has one"), "moccasin": (A_, "the moc seam, when the toe shape says so"),
}
COVERAGE["upper_material"] = {v: (N_, "the colour carries it; the drawing does not show the leather's finish") for v in (
    "smooth_calf", "pebble_grain", "suede", "roughout", "nubuck", "shell_cordovan", "patent", "oiled_pull_up", "canvas",
    "knit_mesh", "synthetic_leather", "waxed_canvas", "rubber", "velvet", "felt_wool", "woven_leather")}
COVERAGE["upper_material"]["patent"] = (D, "bright gloss streaks along the toe and the heel")
COVERAGE["leather_colorways"] = {v: (A_, "drawn in the item's colour") for v in (
    "black", "dark_brown", "mid_brown", "tan", "cognac", "oxblood", "walnut", "snuff_suede", "sand_suede", "navy_suede",
    "grey_suede")}
COVERAGE["sneaker_colorways"] = {v: (A_, "drawn in the item's colour") for v in (
    "white", "off_white", "black", "grey", "navy", "multi")}
COVERAGE["sneaker_colorways"]["cream_gum_sole"] = (A_, "the item's colour, with a gum sole when the sole colour says so")
for _key in BOTTOM_DRAWING:
    COVERAGE["trouser_pockets" if _key == "pockets" else _key] = {
        v: (status, note) for v, (_, status, note) in BOTTOM_DRAWING[_key].items()}
COVERAGE["denim_washes"] = {w: (D, "the jeans drawn in the wash's colour when no colour was measured")
                            for w in DENIM_WASH_SHADE if w != "overdyed"}
COVERAGE["denim_washes"]["overdyed"] = (N_, "an overdye has no one colour: the measured colour is used")
COVERAGE["shorts_inseam_in"] = {k: (D, "the shorts drawn to the inseam told, in inches") for k in SHORTS_INSEAM_IN}
COVERAGE["shades"] = {name: (D, "the item drawn in the shade's colour") for name in SHADES}
COVERAGE["families"] = {f: (N_, "used to match colours in outfits, not drawn") for f in COLOR_FAMILIES}
COVERAGE["fabric_effects"] = {e: (N_, "the colour as measured is drawn; the cloth's surface comes from the fabric")
                              for e in FABRIC_EFFECTS}
COVERAGE["fabric_effects"]["denim"] = (A_, "the fades the tagger names are drawn on jeans")


def coverage_counts() -> dict[str, tuple[int, int, int]]:
    """(drawn, approximate, not drawn) per axis."""
    return {ax: tuple(sum(1 for s, _ in vals.values() if s == st) for st in (D, A_, N_)) for ax, vals in COVERAGE.items()}


# Trousers and shorts whose kind changes the drawing, as `pants` template parameters laid over the ones the
# details give (the details still decide the rest: a drawstring, pleats, a crease).
BOTTOM_DRAWINGS: dict[str, dict] = {
    "sweatpants": dict(waist="drawstring", pockets="side", hem="rib", leg="tapered"),
    "joggers": dict(waist="drawstring", pockets="side", hem="rib", leg="tapered"),
    "open_hem_sweatpants": dict(waist="drawstring", pockets="side", hem="plain", leg="straight"),
    "track_pants": dict(waist="elastic", pockets="side", hem="plain", leg="tapered", stripe="side"),
    "tech_pants": dict(waist="elastic", pockets="slant", hem="plain", leg="tapered"),
    "compression_tights": dict(waist="elastic", pockets="none", hem="plain", leg="skinny"),
    "lounge_pants": dict(waist="drawstring", pockets="none", hem="plain", leg="straight"),
    "running_shorts": dict(waist="drawstring", pockets="none", length="brief", hem="split"),
    "training_shorts": dict(waist="drawstring", pockets="side", hem="plain"),
    "basketball_shorts": dict(waist="drawstring", pockets="side", hem="plain", stripe="side"),
    "two_in_one_shorts": dict(waist="elastic", pockets="none", length="brief", hem="split"),
    "sleep_shorts": dict(waist="elastic", pockets="none", hem="plain"),
}
# The everyday trousers and shorts: what each kind looks like when the details leave it open, as `pants` template
# parameters laid under the ones the details give (a told detail wins), the cloth it is drawn in when none was seen,
# and how well that shows.
BOTTOM_KINDS: dict[str, tuple[dict, str | None, str, str]] = {
    "chinos": ({"pockets": "slant", "hem": "plain"}, "twill", D, "slant pockets, a plain hem and a twill texture"),
    "dress_trousers": ({"pockets": "slant", "crease": True, "hem": "plain"}, None, D,
                       "a pressed crease down each leg, slant pockets, a plain hem"),
    "jeans": ({"jeans": True}, None, D, "five pockets: the scoop, the watch pocket and its rivets, a topstitched hem"),
    "corduroys": ({"pockets": "slant"}, "corduroy", D, "slant pockets and the cord's wales"),
    "fatigues": ({"pockets": "slant", "fly": "button"}, "sateen", A_,
                 "a button fly and a sateen sheen; the back-sateen cloth is only suggested and the back flap pockets are "
                 "out of view"),
    "cargo_pants": ({"pockets": "slant", "cargo": True}, None, D, "slant pockets and bellows pockets on the thighs"),
    "work_pants": ({"pockets": "scoop", "panels": ["double_knee"], "extra_pockets": ["hammer", "rule"]}, "canvas", D,
                   "a panel over each knee, a hammer loop and a rule pocket, scoop pockets"),
    "shorts": ({}, None, D, "the shorts drawing, cut to the inseam when it was told"),
}
_KIND_NOTES = {
    "fleece_pullover": "stand collar and a short snap placket; with a trim colour its edges are bound in it, and a "
                       "second colour is cut into the yoke, sleeves and pocket",
    "performance_tee": "a slim raglan tee in a fine mesh texture",
    "athletic_half_zip": "a slim raglan top with a short zip",
    "track_jacket": "full zip, stand collar, rib cuffs and hem; with side stripes, two stripes down each sleeve in the trim colour",
    "trench_coat": "a self belt buckled round the waist; double-breasted at knee length when told",
    "parka": "a hood and a long length, whatever else was told",
    "varsity_jacket": "a knitted collar, cuffs and hem, a snap front; with a second colour, the sleeves in it (the "
                      "chenille letters are not drawn)",
    "waxed_jacket": "the brown cord collar and a waxed cotton sheen",
    "robe": "a knotted sash round the waist, to the knee; its collar and cloth from its details",
    **{k: (("a tight leg" if v.get("leg") == "skinny" else "a short inseam and a slit hem" if v.get("hem") == "split"
            else "an elastic or drawstring waist") + (" and a stripe down each side in the trim colour" if v.get("stripe") else "")
           + (", ribbed ankle cuffs" if v.get("hem") == "rib" else ""))
       for k, v in BOTTOM_DRAWINGS.items()},
}
# A kind is drawn when its drawing has what sets it apart; otherwise it is drawn from its details on the template
# of its app category (a soccer jersey as a tee with its collar and stripes as seen).
COVERAGE["garment"] = {g: (D, _KIND_NOTES[g]) if g in _KIND_NOTES else (BOTTOM_KINDS[g][2], BOTTOM_KINDS[g][3])
                       if g in BOTTOM_KINDS else (D, "") if g in GARMENT_DRAWINGS else
                       (A_, f"drawn from its details as a {APP_CATEGORY[g] or 'top or bottom'}") for g in GARMENTS}


# ---- accessories

# The taxonomy's accessory garments (its `garments` with category "accessory") and the app category each is
# filed under, and the kinds of each (its `accessories` section), in the JSON's order; a test keeps both equal
# to it. The template an accessory is drawn with is named after its garment id.
ACCESSORY_GARMENTS: dict[str, str] = {
    "cap": "hat", "beanie": "hat", "brimmed_hat": "hat", "belt": "belt", "tie": "other", "pocket_square": "other",
    "scarf": "scarf", "gloves": "other", "bag": "bag", "eyewear": "other", "watch": "other", "socks": "other",
}
ACCESSORIES: dict[str, tuple[str, ...]] = {
    "hats": ("baseball_cap_structured", "dad_cap", "five_panel", "trucker_cap", "beanie", "fisherman_beanie", "flat_cap",
             "newsboy", "bucket_hat", "fedora", "trilby", "panama", "boater", "wide_brim", "cowboy_hat", "beret", "trapper"),
    "belts": ("dress_belt", "casual_leather", "braided_leather", "canvas_web", "woven_elastic", "western", "reversible"),
    "buckle_finish": ("brass", "nickel", "gunmetal", "matte_black"),
    "ties": ("silk_woven", "silk_printed", "knit", "wool", "grenadine", "bow_tie"),
    "tie_patterns": ("solid", "repp_stripe", "foulard", "paisley", "dots", "club_motif"),
    "pocket_square_folds": ("flat", "one_point", "puff", "crown"),
    "scarves": ("long_knit", "woven_wool", "cashmere", "silk", "bandana", "neck_gaiter"),
    "gloves": ("leather_dress", "knit", "mittens", "fingerless", "work", "touchscreen"),
    "bags": ("tote", "daypack", "rucksack", "roll_top", "messenger", "briefcase", "duffel", "crossbody_sling", "belt_bag",
             "dopp_kit"),
    "eyewear_frames": ("wayfarer", "aviator", "round", "browline", "rectangular", "sport_wrap"),
    "eyewear_lenses": ("grey", "green", "brown", "mirrored", "gradient", "clear"),
    "watches": ("dress", "dive", "field", "chronograph", "digital_sport"),
    "watch_straps": ("leather", "steel_bracelet", "nato", "rubber", "canvas"),
    "socks": ("dress_otc", "dress_mid_calf", "casual_crew", "athletic_crew", "no_show", "boot_ragg"),
    "jewelry": ("signet_ring", "band", "chain", "beaded_bracelet", "cuff_bracelet", "cufflinks", "tie_bar", "lapel_pin"),
    "other": ("suspenders_button", "suspenders_clip", "umbrella_stick", "umbrella_compact"),
}
# which group of the `accessories` section names the kinds of each accessory garment
ACCESSORY_GROUP = {"cap": "hats", "beanie": "hats", "brimmed_hat": "hats", "belt": "belts", "tie": "ties",
                   "pocket_square": "pocket_square_folds", "scarf": "scarves", "gloves": "gloves", "bag": "bags",
                   "eyewear": "eyewear_frames", "watch": "watches", "socks": "socks"}
# every kind the tagger may name (a few words are shared by two groups: "knit" ties and gloves)
ACCESSORY_KINDS: tuple[str, ...] = tuple(dict.fromkeys(k for g in dict.fromkeys(ACCESSORY_GROUP.values()) for k in ACCESSORIES[g]))
# the accessories with a shape of their own; the others are drawn as a plain tag (the "accessory" template)
ACCESSORY_TEMPLATES = ("bag", "belt", "cap", "beanie", "brimmed_hat", "scarf")

# kind -> (template, its style). The hats are one group in the taxonomy, so a hat's kind decides its template.
_KIND_DRAWING = {
    "baseball_cap_structured": ("cap", "structured"), "dad_cap": ("cap", "dad"), "five_panel": ("cap", "five_panel"),
    "trucker_cap": ("cap", "trucker"), "beanie": ("beanie", "cuffed"), "fisherman_beanie": ("beanie", "fisherman"),
    "beret": ("beanie", "beret"), "trapper": ("beanie", "trapper"), "flat_cap": ("brimmed_hat", "flat_cap"),
    "newsboy": ("brimmed_hat", "newsboy"), "bucket_hat": ("brimmed_hat", "bucket"), "fedora": ("brimmed_hat", "fedora"),
    "trilby": ("brimmed_hat", "trilby"), "panama": ("brimmed_hat", "panama"), "boater": ("brimmed_hat", "boater"),
    "wide_brim": ("brimmed_hat", "wide_brim"), "cowboy_hat": ("brimmed_hat", "cowboy"),
    "dress_belt": ("belt", "dress"), "casual_leather": ("belt", "casual"), "braided_leather": ("belt", "braided"),
    "canvas_web": ("belt", "web"), "woven_elastic": ("belt", "elastic"), "western": ("belt", "western"),
    "reversible": ("belt", "dress"),
    "long_knit": ("scarf", "knit"), "woven_wool": ("scarf", "woven"), "cashmere": ("scarf", "woven"),
    "silk": ("scarf", "silk"), "bandana": ("scarf", "bandana"), "neck_gaiter": ("scarf", "gaiter"),
    "tote": ("bag", "tote"), "daypack": ("bag", "backpack"), "rucksack": ("bag", "rucksack"),
    "roll_top": ("bag", "roll_top"), "messenger": ("bag", "messenger"), "briefcase": ("bag", "briefcase"),
    "duffel": ("bag", "duffel"), "crossbody_sling": ("bag", "sling"), "belt_bag": ("bag", "belt_bag"),
    "dopp_kit": ("bag", "pouch"),
}
# the plainest drawing of each accessory category, and of each garment id, when no kind is known
_PLAIN_STYLE = {"cap": "structured", "beanie": "cuffed", "brimmed_hat": "fedora", "belt": "casual", "scarf": "woven",
                "bag": "tote"}
_UNSAID = {"bag": "which kind of bag it is was not said, so it is drawn as a tote",
           "hat": "which kind of hat it is was not said, so it is drawn as a cap",
           "knit_hat": "which kind of hat it is was not said; it looks knitted, so it is drawn as a beanie",
           "belt": "which kind of belt it is was not said, so it is drawn as a plain leather belt",
           "scarf": "which kind of scarf it is was not said, so it is drawn as a woven scarf"}
_NOUN = {"tie": "ties have", "pocket_square": "pocket squares have", "gloves": "gloves have", "eyewear": "glasses have",
         "watch": "watches have", "socks": "socks have"}


def accessory_drawing(category: str, accessory: str | None = None, kind: str | None = None,
                      cloth: dict | None = None) -> tuple[str, dict, list[str]] | None:
    """Template, parameters and notes for an accessory, from its app category, its taxonomy garment id and its
    kind (taxonomy words; "na" or None when not known). None when it is not an accessory (an "other" item that
    is none of the taxonomy's accessories). An id or kind filed under another category is not used."""
    cloth = cloth or {}
    accessory = accessory if ACCESSORY_GARMENTS.get(accessory or "") == category else None
    if category == "other":
        if accessory is None:
            return None
        return "accessory", {"kind": accessory}, [f"{_NOUN[accessory]} no shape of their own yet, so a plain tag "
                                                   "stands in for the drawing"]
    if category not in ("bag", "belt", "hat", "scarf"):
        return None
    group = ACCESSORY_GROUP[accessory or ("cap" if category == "hat" else category)]
    drawn = _KIND_DRAWING.get(kind) if kind in ACCESSORIES[group] else None
    if drawn is not None and (category == "hat" or drawn[0] == (accessory or category)):
        template, style = drawn
        notes = []
        if kind == "reversible":
            notes.append("a reversible belt is drawn as a dress belt: its other side is not shown")
        params = {"style": style}
        if kind == "cashmere":
            params["soft"] = True
        return template, params, notes
    if category == "hat":
        if accessory is not None:
            return accessory, {"style": _PLAIN_STYLE[accessory]}, []
        knitted = cloth.get("fabric") in AXES["knit_structure"] and cloth.get("fabric") not in ("jersey", "mesh")
        return ("beanie", {"style": "cuffed"}, [_UNSAID["knit_hat"]]) if knitted else \
            ("cap", {"style": "structured"}, [_UNSAID["hat"]])
    if category == "scarf" and (cloth.get("fabric") in AXES["knit_structure"] or cloth.get("fiber") == "silk"):
        style = "knit" if cloth.get("fabric") in AXES["knit_structure"] else "silk"
        return "scarf", {"style": style}, []
    return category, {"style": _PLAIN_STYLE[category]}, [_UNSAID[category]]


_ACCESSORY_NOTES = {
    "baseball_cap_structured": (D, "a tall six-panel crown with a stiff front and a curved peak"),
    "dad_cap": (D, "a lower, softer crown"),
    "five_panel": (D, "a flat front panel and a short peak"),
    "trucker_cap": (D, "a tall front panel and mesh sides"),
    "beanie": (D, "a knitted crown with a turned-up cuff"),
    "fisherman_beanie": (D, "short, sitting high, with a deep cuff"),
    "beret": (D, "a soft flat crown leaning to one side, drawn with the beanie template"),
    "trapper": (D, "a padded crown with ear flaps, drawn with the beanie template"),
    "flat_cap": (D, "a low rounded crown sloping onto a short peak"),
    "newsboy": (D, "a fuller crown in panels, with a button on top and a short peak"),
    "bucket_hat": (D, "a round crown and a brim sloping down all round"),
    "fedora": (D, "a pinched crown with a dent, a ribbon band and a medium brim"),
    "trilby": (D, "a shorter pinched crown and a narrow brim"),
    "panama": (D, "a fedora's shape in woven straw"),
    "boater": (D, "a flat-topped crown, a stiff flat brim and a band"),
    "wide_brim": (D, "a fedora's crown on a wide brim"),
    "cowboy_hat": (D, "a tall dented crown and a brim curled up at the sides"),
    "dress_belt": (D, "a narrow strap with a small buckle"),
    "casual_leather": (D, "a wider strap with a larger buckle"),
    "braided_leather": (D, "a braided strap with no holes"),
    "canvas_web": (D, "a woven web strap with a slide buckle and a metal tip"),
    "woven_elastic": (D, "a stretch strap woven in a zigzag, with no holes"),
    "western": (D, "a wide tooled strap with a large buckle"),
    "reversible": (A_, "drawn as a dress belt: its other side is not shown"),
    "long_knit": (D, "ribbed, with plain ends"),
    "woven_wool": (D, "fringed ends"),
    "cashmere": (A_, "drawn as a woven wool scarf with a soft edge (halo)"),
    "silk": (D, "a narrow scarf with pointed ends"),
    "bandana": (D, "a square folded into a triangle and knotted"),
    "neck_gaiter": (D, "a short tube"),
    "tote": (D, "an open bag with two handles"),
    "daypack": (D, "a rounded backpack with a grab handle and a zipped front pocket"),
    "rucksack": (D, "a backpack with a flap held by two straps"),
    "roll_top": (D, "a backpack whose top is rolled down and clipped"),
    "messenger": (D, "a wide flap and a strap over the shoulder"),
    "briefcase": (D, "a stiff case with a top handle and a clasp"),
    "duffel": (D, "a barrel-shaped bag with two handles"),
    "crossbody_sling": (D, "a small rounded bag on a long strap"),
    "belt_bag": (D, "a small curved pouch with a strap out to each side"),
    "dopp_kit": (D, "a small zipped case"),
}
# accessory garment ids, and the kinds of each, as the drawing shows them
COVERAGE["accessory"] = {
    g: ((D, f"its own template, `{g}`") if g in ACCESSORY_TEMPLATES else
        (N_, "no shape of its own yet: a plain tag stands in for it (the `accessory` template)"))
    for g in ACCESSORY_GARMENTS}
for _group in dict.fromkeys(ACCESSORY_GROUP.values()):
    COVERAGE[_group] = {k: _ACCESSORY_NOTES.get(k, (N_, "no shape of its own yet: a plain tag stands in for it"))
                        for k in ACCESSORIES[_group]}


# The owner's file: docs/ in a source checkout, next to this module in the packaged program (packaging/closet.spec).
_HERE = Path(__file__).resolve().parent
TAXONOMY_FILES = tuple(folder / "menswear-taxonomy.json"
                       for folder in ([_HERE.parents[2] / "docs"] if len(_HERE.parents) > 2 else []) + [_HERE])


def load(path: Path | None = None) -> dict:
    """The whole taxonomy file as a dict. Raises FileNotFoundError when neither copy is there."""
    for candidate in (path,) if path else TAXONOMY_FILES:
        if candidate.is_file():
            return json.loads(candidate.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"The menswear taxonomy is missing: looked for {', '.join(str(p) for p in TAXONOMY_FILES)}.")


def outfit_rules(taxonomy: dict | None = None) -> tuple[dict, dict]:
    """The owner's outfit rules: the file's `outfit` block and its `colors` block (empty dicts where missing)."""
    data = load() if taxonomy is None else taxonomy
    outfit = data.get("outfit") if isinstance(data.get("outfit"), dict) else {}
    colors = data.get("colors") if isinstance(data.get("colors"), dict) else {}
    return outfit, colors
