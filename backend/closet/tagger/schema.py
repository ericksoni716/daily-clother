"""The attribute vocabulary and the shape of a tagging answer.

Two layers. The coarse fields (category, colour, formality, season, silhouette)
drive outfits and gaps. The `details` are what make the drawing this garment
and not a generic one: how the front opens, how many buttons and what colour,
pockets, the cloth's surface, contrast trim, and so on. Anything distinctive
that has no field yet goes in `other_features`, so it is never silently lost
and the vocabulary can grow from what real clothes need.

Every field carries the model's confidence so the review queue can show only
what is uncertain. Every property is required: the API's schema-constrained
output is at its most dependable with no optional properties. Detail fields use
an explicit "none", "na" or "same" value where they do not apply, because the
API limits how many nullable properties one schema may have.
"""
from __future__ import annotations

from typing import Literal, get_args

from pydantic import BaseModel, Field, model_validator

from . import taxonomy
from .taxonomy import (
    ACCESSORIES,
    ACCESSORY_GARMENTS,
    ACCESSORY_KINDS,
    AXES,
    BOTTOM_AXES,
    BOTTOM_DRAWINGS,
    CORDUROY_WALES,
    FOOTWEAR,
    FOOTWEAR_AXES,
    FOOTWEAR_LACING,
    FOOTWEAR_TOE_TREATMENT,
    GARMENTS,
    KNIT_GAUGES,
    SHADES,
    SHOE_STYLES,
    WEIGHT_CLASSES,
    top_drawing,
)

Category = Literal["tee", "shirt", "polo", "sweater", "hoodie", "jacket", "coat", "jeans", "trousers", "shorts",
                   "sneakers", "boots", "dress_shoes", "sandals", "bag", "belt", "hat", "scarf", "other"]
Color = Literal["black", "white", "grey", "navy", "blue", "light_blue", "green", "olive", "tan", "brown", "cream",
                "red", "burgundy", "pink", "orange", "yellow", "purple", "multi"]
Pattern = Literal["solid", "stripe", "plaid", "floral", "camo", "graphic", "other"]
Formality = Literal["athletic", "casual", "smart_casual", "business", "formal"]
Season = Literal["warm", "cool", "all"]

Sleeve = Literal["none", "short", "long"]
Neck = Literal["crew", "v", "collar", "hood", "turtle"]
TopLength = Literal["cropped", "regular", "long"]
Fit = Literal["slim", "regular", "oversized"]
Leg = Literal["tapered", "straight", "wide"]
PantLength = Literal["short", "ankle", "full"]
ShoeHeight = Literal["low", "high"]
Shot = Literal["tag", "detail", "back"]

# ---- details: what makes the drawing this garment. The construction axes are the owner's
# menswear taxonomy (docs/menswear-taxonomy.json) word for word, so the tagger, the drawing and
# the owner all use the same names. "na" is added where an axis does not apply to the item.
def _axis(name: str, *extra: str):
    return Literal[tuple(extra) + AXES[name]]


Garment = Literal[("unknown",) + tuple(GARMENTS)]           # the owner's taxonomy's kinds of clothing
ColorOrSame = Literal[("same",) + get_args(Color)]          # "same" = matches the body, or does not apply
FitDetail = _axis("fit")
SleeveLength = _axis("sleeve_length", "na")
Neckline = _axis("neckline", "na")
Collar = _axis("collar")
Placket = _axis("placket")
Cuff = _axis("cuff")
SleeveConstruction = _axis("sleeve_construction", "na")
Pockets = _axis("pockets")
Hem = _axis("hem", "na")
Fabric = Literal[("unknown",) + tuple(dict.fromkeys(AXES["woven_structure"] + AXES["knit_structure"]))]
ColorTexture = _axis("color_texture")
# Weight and fibre decide how thick a garment reads and what it can be layered over or under.
Fiber = _axis("fiber", "unknown")
Weight = Literal[("unknown",) + WEIGHT_CLASSES]
KnitGauge = Literal[("na",) + KNIT_GAUGES]
CorduroyWale = Literal[("na",) + CORDUROY_WALES]
PatternName = _axis("pattern")
PatternOrientation = _axis("pattern_orientation")
Waist = Literal["na", "belt_loops", "drawstring", "elastic"]
PantHem = Literal["na", "plain", "turn_up", "ribbed"]
ShoeStyle = Literal["na", "low_sneaker", "high_top", "runner", "slip_on", "boot", "chelsea_boot", "loafer", "derby", "oxford", "sandal"]
# accessories: the taxonomy's accessory garment ids, and the kinds its `accessories` section names
Accessory = Literal[("na",) + tuple(ACCESSORY_GARMENTS)]
AccessoryKind = Literal[("na",) + ACCESSORY_KINDS]
_KINDS_HELP = "; ".join(f"{name}: {', '.join(ACCESSORIES[group])}" for name, group in (
    ("Hats", "hats"), ("Belts", "belts"), ("Scarves", "scarves"), ("Bags", "bags"), ("Ties", "ties"),
    ("Pocket squares (the fold)", "pocket_square_folds"), ("Gloves", "gloves"), ("Eyewear (the frame)", "eyewear_frames"),
    ("Watches", "watches"), ("Socks", "socks")))
# shoes: the owner's footwear kinds and attributes; trousers and shorts: the bottoms block; any item: a named shade
Footwear = Literal[("unknown",) + tuple(FOOTWEAR)]
ToeShape = Literal[("na",) + FOOTWEAR_AXES["toe_shape"]]
ToeTreatment = Literal[("na",) + tuple(FOOTWEAR_TOE_TREATMENT)]
Lacing = Literal[("na",) + tuple(FOOTWEAR_LACING)]
Laces = Literal[("na",) + FOOTWEAR_AXES["laces"]]
ShoeSole = Literal[("na",) + FOOTWEAR_AXES["sole"]]
ShoeConstruction = Literal[("na",) + FOOTWEAR_AXES["construction"]]
FootwearHeight = Literal[("na",) + FOOTWEAR_AXES["height"]]
Heel = Literal[("na",) + FOOTWEAR_AXES["heel"]]
UpperMaterial = Literal[("na",) + FOOTWEAR_AXES["upper_material"]]
Waistband = Literal[("na",) + BOTTOM_AXES["waistband"]]
Fly = Literal[("na",) + BOTTOM_AXES["fly"]]
TrouserFront = Literal[("na",) + BOTTOM_AXES["front"]]
Rise = Literal[("na",) + BOTTOM_AXES["rise"]]
LegShape = Literal[("na",) + BOTTOM_AXES["leg"]]
TrouserBreak = Literal[("na",) + BOTTOM_AXES["break"]]
HemFinish = Literal[("na",) + BOTTOM_AXES["hem_finish"]]
Crease = Literal[("na",) + BOTTOM_AXES["crease"]]
TrouserPocket = Literal[BOTTOM_AXES["pockets"]]
BackDetail = Literal[BOTTOM_AXES["back_details"]]
DenimWash = Literal[("na",) + BOTTOM_AXES["denim_washes"]]
DenimFade = Literal[BOTTOM_AXES["denim_fades"]]
Distressing = Literal[BOTTOM_AXES["distressing"]]
Shade = Literal[("unknown",) + tuple(SHADES)]
Feature = Literal["v_insert", "pleats", "pressed_crease", "contrast_stitching", "toe_cap", "side_stripe",
                  "contrast_heel_tab", "chunky_sole"]

# Stored with every answer the app keeps. Raise it whenever `ItemTags` changes shape or vocabulary, so stored
# answers can be told apart (a test holds a fingerprint of the schema and fails until this is raised).
SCHEMA_VERSION = 4

FIELDS = ("category", "color", "pattern", "formality", "season")
DETAIL_FIELDS = ("garment", "fit_detail", "sleeve_length", "neckline", "collar", "placket", "placket_buttons", "button_color", "cuff",
                 "sleeve_construction", "pockets", "hem", "fabric", "fiber", "weight", "knit_gauge", "corduroy_wale", "color_texture", "pattern_name", "pattern_orientation",
                 "trim_color", "waist", "pant_hem", "shoe_style", "sole_color", "lace_color", "accessory", "accessory_kind",
                 "shade", "footwear", "toe_shape", "toe_treatment", "lacing", "eyelets", "laces", "sole", "shoe_construction",
                 "footwear_height", "heel", "upper_material",
                 "waistband", "fly", "trouser_front", "rise", "leg_shape", "trouser_break", "hem_finish", "crease",
                 "trouser_pockets", "back_details", "denim_wash", "denim_fades", "distressing", "inseam")
SILHOUETTE_FIELDS = ("sleeve", "neck", "top_length", "fit", "leg", "pant_length", "shoe_height")


class Silhouette(BaseModel):
    """Every field is always present; the ones that do not apply to the item's category are null."""
    sleeve: Sleeve | None
    neck: Neck | None
    top_length: TopLength | None
    fit: Fit | None
    leg: Leg | None
    pant_length: PantLength | None
    shoe_height: ShoeHeight | None

    @classmethod
    def of(cls, **known) -> Silhouette:
        """Build one from just the fields that apply."""
        return cls(**{**dict.fromkeys(SILHOUETTE_FIELDS), **known})


# Fields added since version 1, with the value an older stored answer is read with.
ADDED_IN_2 = {"garment": "unknown"}
ADDED_IN_3 = {"accessory": "na", "accessory_kind": "na"}
ADDED_IN_4 = {"shade": "unknown", "footwear": "unknown", "toe_shape": "na", "toe_treatment": "na", "lacing": "na",
              "eyelets": 0, "laces": "na", "sole": "na", "shoe_construction": "na", "footwear_height": "na", "heel": "na",
              "upper_material": "na", "waistband": "na", "fly": "na", "trouser_front": "na", "rise": "na", "leg_shape": "na",
              "trouser_break": "na", "hem_finish": "na", "crease": "na", "trouser_pockets": [], "back_details": [],
              "denim_wash": "na", "denim_fades": [], "distressing": [], "inseam": 0}


class Details(BaseModel):
    garment: Garment = Field(description="The kind of clothing, when one of these plainly fits: sportswear (performance_tee, athletic_half_zip, track_jacket, track_pants, joggers, running_shorts, compression_tights ...) is made for exercise, loungewear (lounge_pants, sleep_shorts, pajama sets, robes) for home. A fleece_pullover is a polar or sherpa fleece pullover with a short zip or snap placket; a fleece_jacket zips all the way. 'unknown' when none fits or you cannot tell; prefer the plain kind (t_shirt, chinos, shorts) unless it is clearly made for sport or lounging.")
    fit_detail: FitDetail = Field(description="How it is cut. boxy = wide and short; relaxed = roomy; oversized = dropped shoulders, clearly too big on purpose. Trousers and shoes: regular.")
    sleeve_length: SleeveLength = Field(description="'na' for anything that is not a top.")
    neckline: Neckline = Field(description="The neck opening of a collarless or knit top (a henley is 'henley', a polo 'polo_collar'). 'na' for a woven shirt, jacket or coat with a collar, and for anything that is not a top.")
    collar: Collar = Field(description="The collar or lapel, if there is one; 'none' otherwise. button_down = small buttons hold the points; camp = flat, open, no stand; band = stand only, no leaves.")
    placket: Placket = Field(description="How the front opens. A plain tee, sweatshirt or pullover: none. Trousers and shoes: none.")
    placket_buttons: int = Field(description="Buttons or snaps you can count on the front opening, including one on a collar stand. 0 when none are visible or it does not apply.")
    button_color: ColorOrSame = Field(description="Colour of the buttons; 'same' when they match the cloth or there are none.")
    cuff: Cuff = Field(description="Sleeve ends. barrel_1 / barrel_2 = one or two buttons; rib_knit = a knitted band; open_hem = a plain hemmed sleeve; none when it does not apply.")
    sleeve_construction: SleeveConstruction = Field(description="How the sleeve joins the body; 'na' when sleeveless or not a top.")
    pockets: Pockets = Field(description="Visible front pockets. patch = sewn on with no flap; five_pocket_jean for jeans; cargo for thigh pockets.")
    hem: Hem = Field(description="Bottom edge of a top; 'na' otherwise.")
    fabric: Fabric = Field(description="The cloth's structure where it is plain to see (corduroy, cable, pique, denim, flannel, oxford ...); 'unknown' when you cannot tell.")
    fiber: Fiber = Field(description="What the cloth is made of. Read it from a care tag when one is legible; otherwise your best judgement from how it looks (fuzzy wool, crumpled linen, smooth cotton), or 'unknown'.")
    weight: Weight = Field(description="How thick and substantial the cloth is, which decides how the garment sits and what it can be layered under. lightweight: linen, poplin, a thin tee, a thin nylon jacket. midweight: an oxford shirt, a standard tee, chinos. heavyweight: wool flannel, denim, a sweatshirt, polar fleece, a thick overshirt. super_heavy: sherpa, melton, a puffer, a chunky knit. 'unknown' only when you really cannot tell.")
    knit_gauge: KnitGauge = Field(description="Sweaters and other knitwear: how fine the stitches are, from extra_fine (smooth, thin) to super_chunky; 'na' otherwise.")
    corduroy_wale: CorduroyWale = Field(description="Corduroy only: how wide the ridges are, from needlecord (very fine) to jumbo; 'na' otherwise.")
    color_texture: ColorTexture = Field(description="How the colour sits in the cloth; solid when unremarkable.")
    pattern_name: PatternName = Field(description="The specific pattern; solid when there is none. Flannel is a fabric, never a pattern.")
    pattern_orientation: PatternOrientation = Field(description="Direction of stripes or pattern; all_over for solids and all-over patterns.")
    trim_color: ColorOrSame = Field(description="Colour of a contrasting collar, cuffs or ribbing, or of a strip binding the edges (as on a fleece pullover); 'same' when they match the body.")
    waist: Waist = Field(description="Trousers and shorts only; 'na' otherwise.")
    pant_hem: PantHem = Field(description="Trousers only: turn_up = a turned-up cuff; ribbed = a knitted cuff as on joggers; 'na' otherwise.")
    shoe_style: ShoeStyle = Field(description="Shoes only; 'na' otherwise. derby = open lacing, oxford = closed lacing, slip_on = a laceless canvas shoe.")
    sole_color: ColorOrSame = Field(description="Shoes: colour of the sole; 'same' otherwise.")
    lace_color: ColorOrSame = Field(description="Shoes: colour of the laces; 'same' when they match the upper, there are none, or it is not a shoe.")
    accessory: Accessory = Field(description="Accessories only: which one it is (cap, beanie and brimmed_hat are hats; tie, pocket_square, gloves, eyewear, watch and socks are filed as category 'other'). 'na' for clothes and shoes.")
    accessory_kind: AccessoryKind = Field(description="Accessories only: its kind, from the list for what it is. " + _KINDS_HELP + ". 'na' when it does not apply or you cannot tell.")
    features: list[Feature] = Field(description="Any of these that are present; empty if none. v_insert = the stitched triangle under a sweatshirt's neck; contrast_stitching = topstitching in a thread colour that stands out, as on most blue jeans; side_stripe = a contrast panel or stripe on the side of a shoe, or stripes down the sleeves of a track jacket or the sides of track trousers or shorts.")
    shade: Shade = Field(description="The owner's name for the main colour's shade, one of the shades of the main colour word (navy: navy, midnight or raw_indigo; tan: stone, khaki, sand, camel or natural_flax; ...); 'unknown' when none is close.")
    footwear: Footwear = Field(description="Shoes only: the kind of shoe or boot, when you can tell (chukka, desert_boot, service_boot, moc_toe_boot, engineer_boot, logger_boot, combat_boot, hiking_boot, western_boot, jodhpur_boot, rain_boot, snow_boot, duck_boot, canvas_low_top, canvas_high_top, leather_court_sneaker, retro_runner, trail_runner, chunky_sneaker, skate_shoe, basketball_shoe, boat_shoe, penny_loafer, cap_toe_oxford ...); 'unknown' otherwise.")
    toe_shape: ToeShape = Field(description="Shoes: the toe's shape seen from above and the side; moc_toe = a raised U-shaped seam over the toe. 'na' otherwise.")
    toe_treatment: ToeTreatment = Field(description="Shoes: what is on the toe (a cap, a wingtip, a medallion, an apron or split-toe seam, a rubber toe cap); 'na' otherwise.")
    lacing: Lacing = Field(description="Shoes: how it fastens: closed_oxford, open_derby, speed_hooks (open hooks at the top of a boot), d_rings, elastic_gussets (a chelsea), monk_single / monk_double (buckled straps), hook_and_loop, toggle_speed_lace, rawhide_around_collar (a boat shoe), slip_on; 'na' otherwise.")
    eyelets: int = Field(description="Shoes: the eyelets (and hooks) you can count on one side of the lacing; 0 when none or not a shoe.")
    laces: Laces = Field(description="Shoes: the kind of laces; 'na' when none or not a shoe.")
    sole: ShoeSole = Field(description="Shoes: the sole: leather, rubber_city, lug_commando (deep lugs), crepe (honey, wavy), wedge (a flat white block, no heel), cupsole, vulcanized (a canvas shoe's), cleats, jute_rope (an espadrille) ...; 'na' otherwise.")
    shoe_construction: ShoeConstruction = Field(description="Shoes: how the sole is attached, when the welt or stitching shows; 'na' otherwise.")
    footwear_height: FootwearHeight = Field(description="Shoes: how high it comes: low, mid or high (sneakers), ankle_boot, boot_6in, boot_8in_plus, knee; 'na' otherwise.")
    heel: Heel = Field(description="Shoes: the heel: flat, low_stacked, block, cuban (tall and angled, as on a western boot); 'na' otherwise.")
    upper_material: UpperMaterial = Field(description="Shoes: what the upper is made of; 'na' otherwise.")
    waistband: Waistband = Field(description="Trousers and shorts: how the waist is held: belt_loops, side_adjusters (buckled tabs at the sides), extended_tab, gurkha (a wide wrapped band with buckles), elastic_drawcord, half_elastic, drawstring, brace_buttons; 'na' otherwise.")
    fly: Fly = Field(description="Trousers and shorts: zip, button (a button fly) or none (a pull-on); 'na' otherwise.")
    trouser_front: TrouserFront = Field(description="Trousers and shorts: flat or pleated: single_pleat, double_pleat, reverse_pleat (opening toward the pockets), forward_pleat (opening toward the fly); 'na' otherwise.")
    rise: Rise = Field(description="Trousers and shorts: where the waist sits: low (on the hips), mid, high (at the natural waist); 'na' otherwise.")
    leg_shape: LegShape = Field(description="Trousers: the leg's shape from hip to hem; 'na' otherwise.")
    trouser_break: TrouserBreak = Field(description="Trousers: how the hem meets the shoe: no_break, slight, full, cropped (above the ankle), stacked (bunched folds); 'na' otherwise.")
    hem_finish: HemFinish = Field(description="Trousers and shorts: the hem: plain, turn_up (a pressed cuff), rolled_cuff (rolled up), ribbed_cuff (joggers), raw, chain_stitched (roping on jeans), split, notched; 'na' otherwise.")
    crease: Crease = Field(description="Trousers: pressed = a sharp crease down the front of each leg; none otherwise; 'na' when not trousers.")
    trouser_pockets: list[TrouserPocket] = Field(description="Trousers and shorts: the pockets you can see, front and back; empty otherwise.")
    back_details: list[BackDetail] = Field(description="Trousers and shorts: what is on the back or the build (double_knee, back_yoke, rivets, back_patch_label, darts ...); empty otherwise.")
    denim_wash: DenimWash = Field(description="Jeans and other denim: the wash, from raw (unwashed, near navy) through rinse, dark, mid and light to bleached; stone, acid, black, washed_black, grey, ecru, white, overdyed. 'na' when not denim.")
    denim_fades: list[DenimFade] = Field(description="Denim: the fades you can see: whiskers (at the hips), honeycombs (behind the knees), stacks (at the hem), train_tracks (along the side seams), roping (at the hem), pocket_fade, knee_fade; empty otherwise.")
    distressing: list[Distressing] = Field(description="Trousers and shorts: knee_rip, frayed_hem, abrasion, patched, sashiko_repair; empty when none.")
    inseam: int = Field(description="Shorts only: the inseam in inches as it looks (running shorts 3-5, chino shorts 7-9, cargo and basketball shorts 9-11); 0 otherwise.")
    features: list[Feature] = Field(description="Any of these that are present; empty if none. v_insert = the stitched triangle under a sweatshirt's neck; contrast_stitching = topstitching in a thread colour that stands out, as on most blue jeans; side_stripe = a contrast panel or stripe on the side of a shoe.")
    other_features: list[str] = Field(description="Up to four distinctive details nothing above covers, a few words each, e.g. 'embroidered chest logo', 'elbow patches'. Empty if none.")

    @model_validator(mode="before")
    @classmethod
    def _older(cls, data):
        """An answer stored before a field was added reads as if it had said the field's 'nothing'."""
        return {**ADDED_IN_2, **ADDED_IN_3, **ADDED_IN_4, **data} if isinstance(data, dict) else data

    @classmethod
    def plain(cls, **known) -> Details:
        """Nothing distinctive, plus whatever is known."""
        base = dict(garment="unknown", fit_detail="regular", sleeve_length="na", neckline="na", collar="none", placket="none", placket_buttons=0,
                    button_color="same", cuff="none", sleeve_construction="na", pockets="none", hem="na", fabric="unknown",
                    fiber="unknown", weight="unknown", knit_gauge="na", corduroy_wale="na",
                    color_texture="solid", pattern_name="solid", pattern_orientation="all_over", trim_color="same",
                    waist="na", pant_hem="na", shoe_style="na", sole_color="same", lace_color="same",
                    accessory="na", accessory_kind="na", **ADDED_IN_4, features=[], other_features=[])
        return cls(**{**base, **known})


class ShotRequest(BaseModel):
    shot: Shot
    reason: str = Field(description="One short sentence the owner will read, e.g. 'I can't read the fabric: photograph the tag?'")


class ItemTags(BaseModel):
    category: Category
    category_confidence: float = Field(ge=0, le=1)
    color: Color = Field(description="Main colour. Use 'multi' only when no single colour dominates.")
    color_confidence: float = Field(ge=0, le=1)
    secondary_colors: list[Color] = Field(description="Up to three other colours; empty for a single-colour item.")
    pattern: Pattern
    pattern_confidence: float = Field(ge=0, le=1)
    formality: Formality
    formality_confidence: float = Field(ge=0, le=1)
    season: Season = Field(description="warm = hot-weather item, cool = cold-weather item, all = year-round")
    season_confidence: float = Field(ge=0, le=1)
    silhouette: Silhouette
    silhouette_confidence: float = Field(ge=0, le=1)
    details: Details
    details_confidence: float = Field(ge=0, le=1)
    brand: str | None = Field(description="Only if legible in a photo; never guessed. Otherwise null.")
    size: str | None = Field(description="Only if legible on a tag. Otherwise null.")
    material: str | None = Field(description="Only if legible on a tag. Otherwise null.")
    needs_shot: ShotRequest | None = Field(description="Null unless one more photo would settle something that matters and cannot be told from these.")


NAMED_HEX = {"black": "#1f1f22", "white": "#f6f5f2", "grey": "#8f9296", "navy": "#27344f", "blue": "#3f6fb0",
             "light_blue": "#a9c3e0", "green": "#3f7d4f", "olive": "#6b6f45", "tan": "#c2a878", "brown": "#6b4a2f",
             "cream": "#ece4d0", "red": "#b8332e", "burgundy": "#6e2633", "pink": "#e3a6b4", "orange": "#d9772b",
             "yellow": "#e3c341", "purple": "#6a4c93"}
_COARSE_SLEEVE = {"none": "sleeveless", "short": "short", "long": "long"}
_COARSE_NECK = {"crew": "crew", "v": "v_neck", "hood": "hood", "turtle": "turtleneck"}
_COARSE_FIT = {"slim": "slim", "oversized": "oversized"}


def drawing_for(tags: ItemTags) -> tuple[str, dict, dict, list[str]]:
    """Template, its parameters, `Spec` extras (colours and surfaces) and notes on what was approximated."""
    s, d = tags.silhouette, tags.details
    extras = {"button_color": NAMED_HEX.get(d.button_color), "trim_color": NAMED_HEX.get(d.trim_color),
              "sole_color": NAMED_HEX.get(d.sole_color), "lace_color": NAMED_HEX.get(d.lace_color)}
    cloth = {"fabric": d.fabric, "fiber": None if d.fiber == "unknown" else d.fiber,
             "weight": None if d.weight == "unknown" else d.weight,
             "knit_gauge": None if d.knit_gauge == "na" else d.knit_gauge,
             "corduroy_wale": None if d.corduroy_wale == "na" else d.corduroy_wale}
    if tags.category in ("bag", "belt", "hat", "scarf", "other"):
        made = taxonomy.accessory_drawing(tags.category, d.accessory, d.accessory_kind, cloth)
        if made is None:
            raise ValueError(f"there is nothing to draw for this {tags.category}")
        template, p, notes = made
        extras.update(taxonomy.surface_extras(cloth))
        if p.pop("soft", False):
            extras["halo"] = True
        if p.get("style") == "silk":
            extras["sheen"] = True
        return template, p, extras, notes
    if tags.category in ("jeans", "trousers", "shorts"):
        jeans = tags.category == "jeans" or d.pockets == "five_pocket_jean"
        p = {"leg": s.leg or "straight", "length": "short" if tags.category == "shorts" else (s.pant_length or "full"),
             "jeans": jeans}
        kind, kind_fabric, _, _ = taxonomy.BOTTOM_KINDS.get(d.garment, ({}, None, "", ""))
        p.update({k: list(v) if isinstance(v, list) else v for k, v in kind.items()})   # the kind's look, under the details
        if kind_fabric and cloth["fabric"] == "unknown":
            cloth["fabric"] = kind_fabric
        p.update(BOTTOM_DRAWINGS.get(d.garment, {}))   # what sets the kind apart: a tight leg, a slit hem, a stripe
        if d.waist in ("drawstring", "elastic"):
            p["waist"] = d.waist
        if d.pockets in ("cargo", "bellows"):
            p["cargo"] = True
        if "pleats" in d.features:
            p["pleats"] = 1
        if "pressed_crease" in d.features:
            p["crease"] = True
        if d.pant_hem in ("turn_up", "ribbed"):
            p["hem"] = {"turn_up": "turnup", "ribbed": "rib"}[d.pant_hem]
        if "contrast_stitching" in d.features:
            p["stitch"] = "contrast"
        p.update(taxonomy.bottom_params(tags.category, d.model_dump()))   # the owner's bottoms block, where told
        p.update(BOTTOM_DRAWINGS.get(d.garment, {}))   # the kind's own look wins over a told detail
        if "side_stripe" in d.features:
            p["stripe"] = "side"
        extras.update(taxonomy.surface_extras(cloth))
        return "pants", p, extras, []
    if tags.category in ("sneakers", "boots", "dress_shoes", "sandals"):
        by_category = ({"boots": "boot", "dress_shoes": "derby", "sandals": "sandal"}.get(tags.category)
                       or ("high_top" if s.shoe_height == "high" else "low_sneaker"))
        style = d.shoe_style if d.shoe_style in SHOE_STYLES else by_category
        style, told = taxonomy.shoe_params(style, d.model_dump())   # the footwear kind and attributes, where told
        style, words, _ = taxonomy.shoe_words(style, d.other_features)   # a footwear id or detail the tagger named
        p = {"height": "high" if style in ("high_top", "boot", "chelsea_boot") else "low", "style": style}
        if "chunky_sole" in d.features:
            p["sole"] = "chunky"
        if "toe_cap" in d.features:
            p["toe_cap"] = "rubber" if (style in ("high_top", "slip_on") or d.fabric == "canvas") else "stitched"
        if "side_stripe" in d.features:
            p["stripe"] = "side"
        if "contrast_heel_tab" in d.features:
            p["heel_tab"] = "contrast"
        p.update(told)
        p.update(words)
        return "sneaker", p, extras, []
    # a top: the details decide, in the taxonomy's words; the coarse silhouette fills in what the details leave "na"
    category_neck = {"shirt": "collar", "polo": "collar", "hoodie": "hood", "jacket": "collar", "coat": "collar"}.get(tags.category, "crew")
    coarse_neck = s.neck or category_neck
    g = {"fit": d.fit_detail if d.fit_detail != "regular" else _COARSE_FIT.get(s.fit, "regular"),
         "sleeve_length": d.sleeve_length if d.sleeve_length != "na" else _COARSE_SLEEVE.get(
             s.sleeve or taxonomy.KIND_SLEEVE.get(d.garment) or ("short" if tags.category in ("tee", "polo") else "long")),
         "collar": d.collar if d.collar != "none" else (taxonomy.KIND_COLLAR.get(d.garment, "point") if (coarse_neck == "collar" and d.neckline == "na") else "none"),
         "neckline": d.neckline if d.neckline != "na" else _COARSE_NECK.get(coarse_neck, "crew"),
         "placket": d.placket, "placket_buttons": d.placket_buttons if d.placket != "none" else None,
         "cuff": d.cuff, "sleeve_construction": d.sleeve_construction,
         "pockets": d.pockets,
         "hem": d.hem if d.hem != "na" else "straight", **cloth,
         "length": s.top_length or ("long" if tags.category == "coat" else "regular"),
         "garment": d.garment, "side_stripe": "side_stripe" in d.features, "contrast_trim": d.trim_color != "same",
         "second_color": bool(tags.secondary_colors), "pattern_name": d.pattern_name,
         "color_texture": d.color_texture}
    p, more, notes = top_drawing(g)
    if more.get("colorwork"):   # knitted in the other colours seen
        more["motif_colors"] = tuple(NAMED_HEX[c] for c in tags.secondary_colors if c in NAMED_HEX)
    if p.get("colorblock"):   # the second colour: the first of the other colours seen
        more["block_color"] = NAMED_HEX.get(tags.secondary_colors[0])
    if "v_insert" in d.features:
        p["neck_detail"] = "v-insert"
    if p.get("stripes") == "hoops" and not extras["trim_color"] and tags.secondary_colors:
        extras["trim_color"] = NAMED_HEX.get(tags.secondary_colors[0])   # a hockey jersey's stripes: the other colour seen
    return "top", p, {**extras, **more}, notes


def drawn_words(tags: ItemTags) -> list[str]:
    """The tagger's other_features words that the drawing shows (a shoe's footwear id, strap or lacing)."""
    if tags.category not in ("sneakers", "boots", "dress_shoes", "sandals"):
        return []
    return taxonomy.shoe_words(tags.details.shoe_style, tags.details.other_features)[2]


def silhouette_params(tags: ItemTags) -> tuple[str, dict]:
    """Map tags to an illustration template and its parameters."""
    return drawing_for(tags)[:2]


def drawing_extras(tags: ItemTags) -> dict:
    """The parts of the drawing that are colours and surfaces, not shape (keyword arguments of `Spec`)."""
    return drawing_for(tags)[2]
