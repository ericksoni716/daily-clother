"""What an item is: its kind, from the owner's menswear taxonomy, and the coarse category that follows from it.

The taxonomy's `garments` (`docs/menswear-taxonomy.json`) are the kinds the
tagger and the drawing really use: an oxford shirt, a henley, a fleece pullover,
a chelsea boot, joggers, a beanie. The item page shows the item's kind and lets
the owner choose another one (`corrections.set_kind`). The coarse category the
outfit engine and What's missing read (`vocab.CATEGORY`) is derived from the
kind, so choosing a kind never changes what the rest of the app means by "a
shirt" or "boots".

The owner's kind is kept with their other details (`items.own_details`, under
`garment`), so "Describe it again" never undoes it; Claude's is the tagger's
`details.garment` (or, for a shoe, a footwear id among the words it saw). Each
kind is shown in a group made from its taxonomy category, never from a list kept
by hand. A test keeps the tables here equal to the JSON.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache

from .drawing import item as draw
from .tagger.schema import Details
from .tagger.taxonomy import APP_CATEGORY, BOTTOM_DRAWINGS, FOOTWEAR, GARMENT_DRAWINGS, GARMENTS

# every kind in the taxonomy's `garments`, in its order: its taxonomy category and its signature
KINDS: dict[str, tuple[str, str]] = {
    't_shirt': ('knit_top', 'Collarless, rib neckband, no placket.'),
    'henley': ('knit_top', 'Collarless neck with a short 2–5 button placket.'),
    'polo': ('knit_top', 'Knit body, soft knit collar, short button placket, ribbed sleeve bands.'),
    'rugby_shirt': ('knit_top', 'Heavy jersey, contrast white woven collar, rubber buttons, bold hoops.'),
    'dress_shirt': ('woven_shirt', 'Crisp fine fabric, sharp collar with stays, tucked.'),
    'ocbd': ('woven_shirt', 'Oxford cloth + button-down collar with soft collar roll.'),
    'casual_button_up': ('woven_shirt', 'Untucked-length casual shirt.'),
    'flannel_shirt': ('woven_shirt', 'Brushed fuzzy matte fabric; flannel is the fabric, plaid is optional.'),
    'work_shirt': ('woven_shirt', 'Two chest pockets, triple stitching.'),
    'western_shirt': ('woven_shirt', 'Pointed yokes, pearl snaps, smile pockets, 3-snap cuffs.'),
    'camp_collar_shirt': ('woven_shirt', 'Flat one-piece collar without stand, straight hem, boxy.'),
    'popover_shirt': ('woven_shirt', 'Pullover with a half placket.'),
    'band_collar_shirt': ('woven_shirt', 'Collar stand only, no leaf.'),
    'guayabera': ('woven_shirt', 'Four patch pockets and vertical pleat rows front and back.'),
    'overshirt': ('woven_shirt', 'Heavier shirt-jacket worn as a layer.'),
    'tuxedo_shirt': ('woven_shirt', 'Pleated or piqué bib, studs, French cuffs.'),
    'crewneck_sweatshirt': ('sweatshirt', 'Ribbed neck/cuffs/hem, soft thick fleece.'),
    'hoodie': ('sweatshirt', 'Hood with drawcords; kangaroo pocket on pullovers.'),
    'pullover_sweater': ('knitwear', 'Knit pullover; gauge + fiber decide the look.'),
    'cardigan': ('knitwear', 'Knit that opens down the front.'),
    'sweater_vest': ('knitwear', 'Sleeveless knit, ribbed armholes.'),
    'chore_coat': ('outerwear', 'Three patch pockets, boxy, canvas/moleskin/twill'),
    'trucker_jacket': ('outerwear', 'Denim jacket, Type I/II/III'),
    'bomber': ('outerwear', 'Ribbed collar/cuffs/hem, nylon, sleeve pocket'),
    'varsity_jacket': ('outerwear', 'Melton body, leather sleeves, chenille letters'),
    'harrington': ('outerwear', 'Short zip jacket, check lining, umbrella yoke'),
    'field_jacket': ('outerwear', 'Four pockets, stand collar, sateen'),
    'waxed_jacket': ('outerwear', 'Waxed cotton, cord collar, bellows pockets'),
    'peacoat': ('outerwear', 'Navy melton, double-breasted'),
    'overcoat': ('outerwear', 'Knee-length wool coat'),
    'trench_coat': ('outerwear', 'Gabardine, double-breasted, belted'),
    'parka': ('outerwear', 'Long hooded'),
    'puffer': ('outerwear', 'Baffled down'),
    'quilted_jacket': ('outerwear', 'Diamond or box quilting'),
    'fleece_jacket': ('outerwear', 'Polar or sherpa fleece'),
    'leather_jacket': ('outerwear', 'Café racer, double rider, A-2'),
    'barn_jacket': ('outerwear', 'Canvas, corduroy collar'),
    'blazer': ('tailoring', 'Odd jacket, solid'),
    'sport_coat': ('tailoring', 'Odd jacket, textured'),
    'suit_jacket': ('tailoring', 'Matching trousers'),
    'chinos': ('bottoms', 'Cotton twill trousers'),
    'dress_trousers': ('bottoms', 'Wool, creased'),
    'jeans': ('bottoms', 'Five-pocket denim'),
    'corduroys': ('bottoms', 'Corduroy trousers'),
    'fatigues': ('bottoms', 'Back sateen/ripstop'),
    'cargo_pants': ('bottoms', 'Thigh bellows pockets'),
    'work_pants': ('bottoms', 'Canvas, double knee'),
    'sweatpants': ('bottoms', 'Fleece/terry'),
    'shorts': ('bottoms', 'Chino/denim/cargo/swim/linen'),
    'performance_tee': ('activewear', 'Smooth synthetic tee, mesh panels, flatlock seams.'),
    'running_long_sleeve': ('activewear', 'Long-sleeve running top with thumbholes and reflective trims.'),
    'running_singlet': ('activewear', 'Very light sleeveless running top.'),
    'compression_top': ('activewear', 'Skin-tight, panel seams, no folds.'),
    'base_layer': ('activewear', 'Slim long-sleeve thermal layer.'),
    'athletic_half_zip': ('activewear', 'Stand collar with short zip and chin guard.'),
    'track_jacket': ('activewear', 'Full zip, stand collar, side stripes or color-blocked panels.'),
    'windbreaker': ('activewear', 'Light packable nylon jacket, elastic cuffs.'),
    'softshell_jacket': ('activewear', 'Fitted stretch jacket, chest zip pocket.'),
    'rain_shell': ('activewear', 'Waterproof hooded shell, taped seams.'),
    'fleece_pullover': ('activewear', 'Fleece with stand collar and contrast nylon pocket.'),
    'soccer_jersey': ('activewear', 'Sublimated pattern, crest on chest, number on back.'),
    'basketball_jersey': ('activewear', 'Sleeveless mesh, deep armholes, numbers.'),
    'hockey_jersey': ('activewear', 'Very loose, laced V-neck, striped arms and hem.'),
    'baseball_jersey': ('activewear', 'Button front with piping, script across chest.'),
    'cycling_jersey': ('activewear', 'Slim zip jersey with three rear pockets.'),
    'running_shorts': ('activewear', 'Short inseam, split hem, liner.'),
    'two_in_one_shorts': ('activewear', 'Short outer over a longer visible compression liner.'),
    'training_shorts': ('activewear', 'Mid inseam, side and zip pockets.'),
    'basketball_shorts': ('activewear', 'Long loose mesh shorts.'),
    'compression_tights': ('activewear', 'Skin-tight to ankle or mid-thigh.'),
    'track_pants': ('activewear', 'Side stripes, ankle zips, elastic waist.'),
    'tech_pants': ('activewear', 'Slim tapered stretch woven, zip pockets.'),
    'joggers': ('activewear', 'Tapered, ribbed ankle cuffs.'),
    'open_hem_sweatpants': ('activewear', 'Straight leg, no ankle cuff.'),
    'pajama_set_woven': ('loungewear', 'Notched-lapel button top with piping, matching drawstring trousers.'),
    'pajama_set_knit': ('loungewear', 'Knit top with matching pants or shorts.'),
    'sleep_shorts': ('loungewear', 'Boxer-like, elastic waist.'),
    'lounge_pants': ('loungewear', 'Relaxed straight leg, elastic waist; often plaid flannel.'),
    'lounge_knit_set': ('loungewear', 'Relaxed crew sweater with matching knit jogger.'),
    'lounge_sweatsuit': ('loungewear', 'Matching sweatshirt or hoodie and sweatpants.'),
    'robe': ('loungewear', 'Wrap front with belt, shawl collar, knee to ankle length.'),
    'kimono_robe': ('loungewear', 'Straight collar band down the front, wide sleeves, sash.'),
    'smoking_jacket': ('loungewear', 'Short velvet jacket with quilted or satin shawl collar.'),
    'patent_oxford': ('footwear', 'Mirror-gloss black, closed lacing; black tie'),
    'plain_toe_oxford': ('footwear', 'Closed lacing, no cap'),
    'cap_toe_oxford': ('footwear', 'Closed lacing, straight toe cap'),
    'wholecut': ('footwear', 'One piece of leather, no seams but the heel'),
    'brogue': ('footwear', 'Punched edges; semi (cap + medallion) or full wingtip'),
    'derby': ('footwear', 'Open lacing, plain or cap toe'),
    'monk_strap': ('footwear', 'One or two buckled straps instead of laces'),
    'penny_loafer': ('footwear', 'Strap with a slot across the vamp'),
    'tassel_loafer': ('footwear', 'Tassels at the front'),
    'horsebit_loafer': ('footwear', 'Metal snaffle across the vamp'),
    'driving_moc': ('footwear', 'Soft slip-on with rubber nubs on sole and heel'),
    'chelsea_boot': ('footwear', 'Elastic side gussets, pull tabs'),
    'jodhpur_boot': ('footwear', 'Strap wrapping the ankle'),
    'chukka': ('footwear', 'Ankle height, 2-3 eyelets, open lacing'),
    'desert_boot': ('footwear', 'Chukka with crepe sole, unlined suede'),
    'service_boot': ('footwear', '6 in, plain or cap toe, welted'),
    'moc_toe_boot': ('footwear', '6 in moc toe, white wedge sole, oiled leather'),
    'engineer_boot': ('footwear', 'Pull-on with buckled straps'),
    'logger_boot': ('footwear', 'Tall, raised heel, lug sole'),
    'hiking_boot': ('footwear', 'Mid height, padded collar, speed hooks, lug sole'),
    'duck_boot': ('footwear', 'Rubber lower, leather or nylon upper, chain tread'),
    'rain_boot': ('footwear', 'Knee-high rubber, pull-on'),
    'western_boot': ('footwear', 'Pointed or square toe, Cuban heel, stitched shaft'),
    'combat_boot': ('footwear', '8-10 in, lug sole, speed hooks'),
    'snow_boot': ('footwear', 'Insulated, padded, chunky rubber shell'),
    'leather_court_sneaker': ('footwear', 'Clean leather, cupsole, few seams'),
    'canvas_low_top': ('footwear', 'Canvas, vulcanized sole with foxing stripe, toe cap'),
    'canvas_high_top': ('footwear', 'Canvas high-top, vulcanized sole, ankle patch'),
    'retro_court_shoe': ('footwear', 'Leather, perforated toe, side stripes, cupsole'),
    'basketball_shoe': ('footwear', 'Padded collar, chunky cupsole'),
    'skate_shoe': ('footwear', 'Suede or canvas, padded tongue and collar'),
    'retro_runner': ('footwear', 'Suede and nylon panels, EVA wedge midsole'),
    'running_shoe': ('footwear', 'Knit mesh upper, thick sculpted foam midsole'),
    'trail_runner': ('footwear', 'Lug outsole, toe bumper, toggle laces'),
    'trainer': ('footwear', 'Flat stable sole, mesh with overlays'),
    'canvas_slip_on': ('footwear', 'Elastic gussets, vulcanized sole'),
    'cleats': ('footwear', 'Molded studs'),
    'chunky_sneaker': ('footwear', 'Very thick layered midsole, many overlays'),
    'boat_shoe': ('footwear', 'Moccasin apron, rawhide laces around the collar, siped sole'),
    'camp_moc': ('footwear', 'Boat-shoe style, 2 eyelets, lug sole'),
    'espadrille': ('footwear', 'Canvas upper, braided jute sole'),
    'sandal': ('footwear', 'Fisherman, two-strap cork footbed, sport or huarache'),
    'slide': ('footwear', 'Single wide strap, molded sole'),
    'flip_flop': ('footwear', 'Thong between the toes'),
    'moccasin_slipper': ('footwear', 'Soft suede, apron toe, shearling lining'),
    'velvet_slipper': ('footwear', 'Velvet upper, quilted lining, embroidered vamp'),
    'felt_clog': ('footwear', 'Boiled wool upper, cork or rubber sole'),
    'cap': ('accessory', 'Baseball, dad, five-panel or trucker cap'),
    'beanie': ('accessory', 'Ribbed knit, cuffed'),
    'brimmed_hat': ('accessory', 'Fedora, trilby, panama, boater, bucket, flat cap'),
    'belt': ('accessory', 'Dress, casual, braided, web, western'),
    'tie': ('accessory', 'Silk, knit, wool, grenadine or bow tie'),
    'pocket_square': ('accessory', 'Silk, linen or cotton; flat, point, puff or crown fold'),
    'scarf': ('accessory', 'Knit, woven wool, cashmere, silk, bandana'),
    'gloves': ('accessory', 'Leather, knit, mittens'),
    'bag': ('accessory', 'Tote, backpack, messenger, briefcase, duffel, sling'),
    'eyewear': ('accessory', 'Wayfarer, aviator, round, browline'),
    'watch': ('accessory', 'Dress, dive, field, chronograph, digital'),
    'socks': ('accessory', 'Dress, crew, athletic, no-show, boot'),
}
# the construction axes a kind of top lists in the taxonomy, with the values it allows
# (placket_buttons: the fewest and the most)
TOP_AXES_OF: dict[str, dict[str, tuple]] = {
    't_shirt': {'sleeve_length': ('sleeveless', 'short', 'three_quarter', 'long'), 'neckline': ('crew', 'v_neck', 'scoop', 'boat', 'mock'), 'pockets': ('none', 'chest_patch_single')},
    'henley': {'sleeve_length': ('short', 'long'), 'neckline': ('henley',), 'placket': ('henley',), 'placket_buttons': (2, 5)},
    'polo': {'sleeve_length': ('short', 'long'), 'collar': ('flat_knit', 'johnny', 'camp'), 'placket': ('polo', 'zip_quarter', 'none'), 'placket_buttons': (0, 3), 'cuff': ('rib_knit', 'open_hem'), 'hem': ('tennis_tail', 'straight_with_vents', 'ribbed_band')},
    'rugby_shirt': {'sleeve_length': ('long',), 'collar': ('woven_twill_rugby',), 'placket': ('polo',)},
    'dress_shirt': {'sleeve_length': ('long',), 'collar': ('point', 'semi_spread', 'spread', 'cutaway', 'hidden_button_down', 'club', 'tab', 'pin', 'wing'), 'placket': ('front_placket', 'french_front', 'hidden_fly'), 'cuff': ('barrel_1', 'barrel_2', 'french', 'convertible', 'mitred'), 'hem': ('curved_shirt_tail',)},
    'ocbd': {'sleeve_length': ('long', 'short'), 'collar': ('button_down',), 'placket': ('front_placket',), 'cuff': ('barrel_1', 'barrel_2'), 'pockets': ('chest_patch_single', 'none'), 'hem': ('curved_shirt_tail',)},
    'casual_button_up': {'sleeve_length': ('short', 'long'), 'collar': ('point', 'button_down', 'spread', 'band', 'club'), 'placket': ('front_placket', 'french_front'), 'cuff': ('barrel_1', 'rolled', 'roll_tab', 'open_hem'), 'hem': ('straight_with_vents', 'curved_shirt_tail')},
    'flannel_shirt': {'sleeve_length': ('long',), 'collar': ('point', 'button_down'), 'cuff': ('barrel_1', 'barrel_2'), 'pockets': ('chest_flap_single', 'chest_flap_double', 'chest_patch_double')},
    'work_shirt': {'sleeve_length': ('short', 'long'), 'collar': ('point', 'button_down'), 'pockets': ('chest_flap_double', 'chest_patch_double', 'pencil_slot')},
    'western_shirt': {'sleeve_length': ('long', 'short'), 'collar': ('western', 'point'), 'placket': ('snap',), 'cuff': ('snap_3',), 'pockets': ('western_smile', 'chest_flap_double')},
    'camp_collar_shirt': {'fit': ('relaxed', 'boxy', 'regular'), 'sleeve_length': ('short', 'long'), 'collar': ('camp',), 'hem': ('straight', 'straight_with_vents')},
    'popover_shirt': {'collar': ('button_down', 'band', 'point'), 'placket': ('half_placket_popover',)},
    'band_collar_shirt': {'collar': ('band',)},
    'guayabera': {'collar': ('camp', 'point'), 'pockets': ('four_patch_guayabera',), 'hem': ('straight_with_vents',)},
    'overshirt': {'pockets': ('chest_flap_double', 'chest_patch_double', 'hip_patch_double', 'hip_flap_double'), 'hem': ('straight',)},
    'tuxedo_shirt': {'collar': ('wing', 'spread'), 'cuff': ('french',)},
    'crewneck_sweatshirt': {'neckline': ('crew',), 'cuff': ('rib_knit',), 'sleeve_construction': ('raglan', 'set_in'), 'hem': ('ribbed_band',)},
    'hoodie': {'neckline': ('hood',), 'placket': ('none', 'zip_full'), 'pockets': ('kangaroo', 'split_hand')},
    'pullover_sweater': {'neckline': ('crew', 'v_neck', 'turtleneck', 'rollneck', 'mock', 'shawl', 'boat', 'quarter_zip', 'henley', 'polo_collar'), 'sleeve_construction': ('set_in', 'raglan', 'saddle_shoulder')},
    'cardigan': {'neckline': ('v_neck', 'shawl', 'crew'), 'placket': ('front_placket', 'zip_full'), 'pockets': ('none', 'welt', 'chest_patch_double')},
    'sweater_vest': {'sleeve_length': ('sleeveless',), 'neckline': ('v_neck', 'crew')},
    'performance_tee': {'neckline': ('crew', 'v_neck'), 'sleeve_construction': ('set_in', 'raglan')},
    'running_long_sleeve': {'neckline': ('crew', 'quarter_zip')},
    'running_singlet': {'sleeve_length': ('sleeveless',)},
    'compression_top': {'fit': ('slim',), 'neckline': ('crew', 'mock')},
    'base_layer': {'neckline': ('crew', 'quarter_zip')},
    'athletic_half_zip': {'neckline': ('quarter_zip',)},
    'track_jacket': {'collar': ('stand',), 'placket': ('zip_full',), 'cuff': ('rib_knit',), 'pockets': ('split_hand',), 'hem': ('ribbed_band',)},
    'windbreaker': {'placket': ('zip_full', 'zip_half')},
    'softshell_jacket': {'collar': ('stand',), 'placket': ('zip_full',)},
    'rain_shell': {'neckline': ('hood',), 'placket': ('zip_full',)},
    'fleece_pullover': {'collar': ('stand',), 'placket': ('zip_quarter', 'zip_half', 'zip_full')},
    'soccer_jersey': {'neckline': ('v_neck', 'crew')},
    'basketball_jersey': {'sleeve_length': ('sleeveless',)},
    'hockey_jersey': {'fit': ('oversized',)},
    'baseball_jersey': {'placket': ('front_placket',)},
    'cycling_jersey': {'fit': ('slim',), 'placket': ('zip_full', 'zip_half')},
    'pajama_set_woven': {'collar': ('notch_lapel', 'camp'), 'placket': ('front_placket',), 'pockets': ('chest_patch_single',)},
    'pajama_set_knit': {'neckline': ('crew', 'henley')},
    'robe': {'collar': ('shawl',)},
    'smoking_jacket': {'collar': ('shawl',)},
}
# each accessory's app category, as the taxonomy gives it
ACCESSORIES: dict[str, str] = {
    'cap': 'hat', 'beanie': 'hat', 'brimmed_hat': 'hat', 'belt': 'belt', 'tie': 'other', 'pocket_square': 'other', 'scarf': 'scarf', 'gloves': 'other', 'bag': 'bag', 'eyewear': 'other', 'watch': 'other', 'socks': 'other'
}

# the groups the owner chooses a kind from, each with the taxonomy categories it gathers
GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("shirts", "Shirts", ("woven_shirt",)),
    ("tees", "Tees & polos", ("knit_top",)),
    ("knitwear", "Knitwear & mid layers", ("knitwear", "sweatshirt")),
    ("jackets", "Jackets & coats", ("outerwear",)),
    ("tailoring", "Tailoring", ("tailoring",)),
    ("trousers", "Trousers & shorts", ("bottoms",)),
    ("activewear", "Activewear", ("activewear",)),
    ("loungewear", "Loungewear & sleep", ("loungewear",)),
    ("shoes", "Shoes & boots", ("footwear",)),
    ("accessories", "Accessories", ("accessory",)),
)
GROUP_TITLES = {g: t for g, t, _ in GROUPS}
_GROUP_OF = {c: g for g, _, cs in GROUPS for c in cs}
# the group of an item whose kind is not known, from its coarse category
GROUP_OF_CATEGORY = {
    "tee": "tees", "polo": "tees", "shirt": "shirts", "sweater": "knitwear", "hoodie": "knitwear", "jacket": "jackets",
    "coat": "jackets", "jeans": "trousers", "trousers": "trousers", "shorts": "trousers", "sneakers": "shoes",
    "boots": "shoes", "dress_shoes": "shoes", "sandals": "shoes", "bag": "accessories", "belt": "accessories",
    "hat": "accessories", "scarf": "accessories", "other": "accessories"}

# a shoe's coarse category, from the style the taxonomy draws it in
SHOE_CATEGORY = {"low_sneaker": "sneakers", "high_top": "sneakers", "runner": "sneakers", "slip_on": "sneakers",
                 "boot": "boots", "chelsea_boot": "boots", "loafer": "dress_shoes", "derby": "dress_shoes",
                 "oxford": "dress_shoes", "sandal": "sandals"}
# a set (pyjamas, a sweatsuit) is a top or a bottom: it keeps the item's category when that is one, else this one
SET_CATEGORY = {"pajama_set_woven": "shirt", "pajama_set_knit": "tee", "lounge_knit_set": "sweater",
                "lounge_sweatsuit": "sweater"}

# the kinds in words, where the taxonomy id does not read well with its underscores made spaces
WORDS = {
    "t_shirt": "T-shirt", "ocbd": "oxford button-down", "casual_button_up": "casual shirt",
    "pajama_set_woven": "woven pyjama set", "pajama_set_knit": "knit pyjama set", "two_in_one_shorts": "two-in-one shorts",
    "open_hem_sweatpants": "open-hem sweatpants", "plain_toe_oxford": "plain-toe oxford", "cap_toe_oxford": "cap-toe oxford",
    "moc_toe_boot": "moc-toe boot", "chukka": "chukka boot", "canvas_low_top": "canvas low-top",
    "canvas_high_top": "canvas high-top", "flip_flop": "flip-flops", "trainer": "gym trainer",
    "canvas_slip_on": "canvas slip-on", "driving_moc": "driving moccasin", "camp_moc": "camp moccasin", "eyewear": "glasses", "cleats": "studded boots",
}
# common words a kind goes by, for the search ("trainers", "jumper", "tee")
ALSO = {
    "t_shirt": "tee tshirt", "polo": "polo shirt", "ocbd": "oxford shirt button down", "dress_shirt": "formal shirt",
    "casual_button_up": "button up button down", "flannel_shirt": "check lumberjack", "popover_shirt": "pullover shirt",
    "crewneck_sweatshirt": "sweatshirt jumper", "hoodie": "hooded sweatshirt", "pullover_sweater": "jumper knit crewneck",
    "cardigan": "knit jumper", "sweater_vest": "tank top knit", "puffer": "down jacket", "parka": "winter coat",
    "overcoat": "topcoat", "rain_shell": "raincoat waterproof", "windbreaker": "anorak", "suit_jacket": "suit",
    "blazer": "sport jacket", "chinos": "khakis pants", "dress_trousers": "slacks pants suit trousers",
    "jeans": "denim pants", "sweatpants": "joggers tracksuit bottoms", "joggers": "sweatpants jogging bottoms",
    "track_pants": "tracksuit bottoms", "base_layer": "thermal", "running_singlet": "vest tank",
    "fleece_pullover": "fleece", "fleece_jacket": "fleece", "robe": "dressing gown bathrobe",
    "lounge_sweatsuit": "tracksuit", "running_shoe": "trainers sneakers", "trainer": "trainers sneakers gym",
    "leather_court_sneaker": "trainers sneakers", "canvas_low_top": "trainers sneakers", "canvas_high_top": "sneakers",
    "retro_runner": "trainers sneakers", "trail_runner": "trainers", "chunky_sneaker": "trainers dad shoe",
    "flip_flop": "thongs", "slide": "sliders", "brogue": "wingtip", "cap": "baseball hat", "beanie": "hat toque",
    "brimmed_hat": "fedora hat", "bag": "backpack tote", "eyewear": "sunglasses", "socks": "sock",
}
# the construction details a kind of top may hide (the cut and the sleeve length stay for every kind)
HIDEABLE = ("neckline", "collar", "placket", "placket_buttons", "cuff", "sleeve_construction", "pockets", "hem")
_AXIS = {"fit_detail": "fit"}
_TOPS, _BOTTOMS = draw.TOPS, draw.BOTTOMS
TILE_HEX = "#8a8f98"
_HEX = re.compile(r"#[0-9a-f]{6}")


def word(kind: str) -> str:
    """A kind in plain words, for sentences: "fleece pullover", "T-shirt"."""
    return WORDS.get(kind) or kind.replace("_", " ")


def name(kind: str) -> str:
    """A kind's name, as a title: "Fleece pullover"."""
    w = word(kind)
    return w[:1].upper() + w[1:]


def group(kind: str) -> str:
    return _GROUP_OF[KINDS[kind][0]]


def category_for(kind: str, current: str | None = None) -> str:
    """The coarse category an item of this kind is (`vocab.CATEGORY`): what the outfit engine and What's missing read."""
    if kind in FOOTWEAR:
        return SHOE_CATEGORY[FOOTWEAR[kind][0]]
    if kind in ACCESSORIES:
        return ACCESSORIES[kind]
    app = APP_CATEGORY[kind]
    if app is not None:
        return app
    return current if current in _TOPS + _BOTTOMS else SET_CATEGORY[kind]


def _part(category) -> str:
    return "top" if category in _TOPS else "bottom" if category in _BOTTOMS else "shoe" if category in draw.SHOES else "other"


def _say(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9]+", " ", text.lower()).strip() + " "


def search_words(kind: str) -> str:
    """Every word the search finds a kind by: its name, its signature, the values its taxonomy entry allows, the
    common words it goes by and its group."""
    parts = [word(kind), kind.replace("_", " "), KINDS[kind][1], ALSO.get(kind, ""), GROUP_TITLES[group(kind)]]
    for values in TOP_AXES_OF.get(kind, {}).values():
        parts += [str(v).replace("_", " ") for v in values if isinstance(v, str)]
    if kind in FOOTWEAR:
        parts.append("shoe shoes " + FOOTWEAR[kind][0].replace("_", " "))
    return " ".join(_say(" ".join(parts)).split())


def catalogue() -> dict:
    """The groups and every kind in them, in the taxonomy's order, for the item page's picker and the Closet filter."""
    return {"groups": [{"id": g, "title": t} for g, t, _ in GROUPS],
            "kinds": [{"id": k, "name": name(k), "group": group(k), "category": category_for(k), "words": search_words(k),
                       "drawn": category_for(k) in draw.DRAWN} for k in KINDS]}


# ------------------------------------------------------------- an item's kind
def _json(text) -> dict | None:
    try:
        value = json.loads(text) if text else None
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def owner_kind(row) -> str | None:
    """The kind the owner chose, or None."""
    own = _json(row["own_details"] if "own_details" in row.keys() else None) or {}
    kind = own.get("garment")
    return kind if kind in KINDS else None


def said_kind(answer) -> str | None:
    """The kind in Claude's answer: its garment, or for a shoe a footwear id among the words it saw."""
    found = answer.get("details") if isinstance(answer, dict) else None
    if not isinstance(found, dict):
        return None
    if found.get("garment") in KINDS:
        return found["garment"]
    if answer.get("category") in draw.SHOES:
        for w in found.get("other_features") or []:
            if isinstance(w, str):
                for fid in FOOTWEAR:
                    if _say(fid) in _say(w):
                        return fid
    return None


def of_row(row) -> dict:
    """The item's kind, who said it ("owner" or "claude") and how sure Claude was. Claude's kind is shown only
    while the item is still the sort of garment Claude saw (a top, a bottom or a shoe)."""
    mine = owner_kind(row)
    if mine:
        return {"kind": mine, "by": "owner", "confidence": None}
    answer = _json(row["tag_answer"])
    said = said_kind(answer)
    if said and _part(category_for(said, row["category"])) == _part(row["category"]):
        sure = answer.get("details_confidence")
        return {"kind": said, "by": "claude", "confidence": sure if isinstance(sure, (int, float)) else None}
    return {"kind": None, "by": None, "confidence": None}


def summary_fields(row) -> dict:
    kind = of_row(row)["kind"]
    return {"kind": kind, "kind_name": name(kind) if kind else None,
            "group": group(kind) if kind else GROUP_OF_CATEGORY.get(row["category"])}


def _allowed(kind: str, axis: str) -> tuple | None:
    """The values a kind of top allows on an axis (those its taxonomy entry lists, and its signature drawing's),
    or None when it says nothing about it."""
    listed = TOP_AXES_OF.get(kind, {}).get(axis)
    sig = GARMENT_DRAWINGS.get(kind, {}).get(axis)
    if axis == "placket_buttons" and listed:
        listed = tuple(range(listed[0], listed[-1] + 1))
    if listed:
        return listed + ((sig,) if sig is not None and sig not in listed else ())
    return (sig,) if sig is not None else None


def _score(kind: str, found: dict, category) -> int:
    """How well a kind fits what Claude saw (0: not at all)."""
    hits = 0
    if kind in FOOTWEAR:
        hits = 2 if FOOTWEAR[kind][0] == found.get("shoe_style") else 0
    elif kind in BOTTOM_DRAWINGS:
        sig = BOTTOM_DRAWINGS[kind]
        hits = int(found.get("waist") in ("drawstring", "elastic") and found.get("waist") == sig.get("waist"))
        hits += int(found.get("pant_hem") == "ribbed" and sig.get("hem") == "rib")
    elif kind in GARMENTS:
        for n in HIDEABLE + ("fit_detail", "sleeve_length"):
            allowed = _allowed(kind, _AXIS.get(n, n))
            v = found.get(n)
            hits += int(bool(allowed) and v not in (None, "na", "none", 0) and v in allowed)
    return hits * 2 + int(category_for(kind, category) == category) if hits else 0


def alternatives(row, current: str | None, most: int = 4) -> list[str]:
    """Kinds to offer first as "Claude also thought": the kind Claude named (when it is not the item's kind now),
    then those whose details best fit what Claude saw, among the same sort of garment."""
    answer = _json(row["tag_answer"])
    if answer is None:
        return []
    said = said_kind(answer)
    found = answer.get("details") if isinstance(answer.get("details"), dict) else {}
    category = answer.get("category")
    out = [said] if said and said != current else []
    scored = []
    for i, k in enumerate(KINDS):
        if k in (current, said) or k in ACCESSORIES or _part(category_for(k, category)) != _part(category):
            continue
        s = _score(k, found, category)
        if s:
            scored.append((-s, i, k))
    out += [k for _, _, k in sorted(scored)]
    return out[:most]


# ------------------------------------------------------------- details that follow the kind
def _top(kind) -> bool:
    return kind in GARMENTS and (APP_CATEGORY[kind] is None or APP_CATEGORY[kind] in _TOPS)


def own_fields(kind) -> frozenset | None:
    """The construction details a kind of top has: those its taxonomy entry lists and those its signature drawing
    sets. None when every detail applies (not a top, or a kind that names none)."""
    if not _top(kind):
        return None
    listed = set(TOP_AXES_OF.get(kind, {})) | set(GARMENT_DRAWINGS.get(kind, {}))
    out = frozenset(n for n in HIDEABLE if n in listed or (n == "placket_buttons" and "placket" in listed))
    return out or None


def applies(kind, name_: str) -> bool:
    """Whether a detail applies to an item of this kind (a T-shirt has no cuffs or placket); one that does not is
    hidden on the item page and left out of the drawing, but kept."""
    fields = own_fields(kind) if kind else None
    return fields is None or name_ not in HIDEABLE or name_ in fields


def conform(found: dict, kind: str | None, said: str | None, owner: dict) -> dict:
    """The details an item is drawn from, made to fit the kind the owner chose. A shoe takes the kind's style and
    footwear id; a top that is now another kind than Claude saw keeps what Claude saw where the kind allows it and
    takes the kind's own signature elsewhere; details the kind does not have are drawn plain."""
    if kind not in KINDS:
        return found
    out = dict(found)
    if kind in FOOTWEAR:
        out["garment"] = "unknown"
        if "shoe_style" not in owner:
            out["shoe_style"] = FOOTWEAR[kind][0]
        others = [w for w in out.get("other_features") or []
                  if isinstance(w, str) and not any(_say(f) in _say(w) for f in FOOTWEAR)]
        out["other_features"] = [kind.replace("_", " ")] + others
        return out
    if kind not in GARMENTS:   # an accessory: its details say nothing about it
        out["garment"] = "unknown"
        return out
    if kind == said or not _top(kind):
        return out
    fields = own_fields(kind)
    plain = Details.plain().model_dump(mode="json")
    for n in HIDEABLE + ("fit_detail", "sleeve_length"):
        if fields is not None and n in HIDEABLE and n not in fields:
            out[n] = plain[n]
            continue
        if n in owner:
            continue
        axis = _AXIS.get(n, n)
        allowed = _allowed(kind, axis)
        if allowed and out.get(n) not in allowed:
            sig = GARMENT_DRAWINGS.get(kind, {}).get(axis)
            out[n] = sig if sig is not None else allowed[0]
    return out


@lru_cache(maxsize=512)
def drawing(kind: str, hex_: str = TILE_HEX) -> str | None:
    """A small drawing of a kind, in the item's colour, for the picker; None for what is not drawn (accessories)."""
    category = category_for(kind)
    if category not in draw.DRAWN or not _HEX.fullmatch(hex_):
        return None
    found = Details.plain().model_dump(mode="json")
    if kind in GARMENTS:
        found["garment"] = kind
    answer = {
        "category": category, "category_confidence": 1, "color": "grey", "color_confidence": 1, "secondary_colors": [],
        "pattern": "solid", "pattern_confidence": 1, "formality": "casual", "formality_confidence": 1, "season": "all",
        "season_confidence": 1, "silhouette": {}, "silhouette_confidence": 1,
        "details": conform(found, kind, None, {}), "details_confidence": 1, "brand": None, "size": None,
        "material": None, "needs_shot": None}
    return draw.svg_from_answer(answer, hex_, uid="kind")
