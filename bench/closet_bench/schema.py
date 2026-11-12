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

from typing import Literal, Optional, get_args

from pydantic import BaseModel, Field

from . import taxonomy
from .taxonomy import AXES, CORDUROY_WALES, KNIT_GAUGES, WEIGHT_CLASSES, top_drawing
from .templates import SHOE_STYLES

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
Feature = Literal["v_insert", "pleats", "pressed_crease", "contrast_stitching", "toe_cap", "side_stripe",
                  "contrast_heel_tab", "chunky_sole"]

FIELDS = ("category", "color", "pattern", "formality", "season")
DETAIL_FIELDS = ("fit_detail", "sleeve_length", "neckline", "collar", "placket", "placket_buttons", "button_color", "cuff",
                 "sleeve_construction", "pockets", "hem", "fabric", "fiber", "weight", "knit_gauge", "corduroy_wale", "color_texture", "pattern_name", "pattern_orientation",
                 "trim_color", "waist", "pant_hem", "shoe_style", "sole_color", "lace_color")
SILHOUETTE_FIELDS = ("sleeve", "neck", "top_length", "fit", "leg", "pant_length", "shoe_height")


class Silhouette(BaseModel):
    """Every field is always present; the ones that do not apply to the item's category are null."""
    sleeve: Optional[Sleeve]
    neck: Optional[Neck]
    top_length: Optional[TopLength]
    fit: Optional[Fit]
    leg: Optional[Leg]
    pant_length: Optional[PantLength]
    shoe_height: Optional[ShoeHeight]

    @classmethod
    def of(cls, **known) -> "Silhouette":
        """Build one from just the fields that apply."""
        return cls(**{**dict.fromkeys(SILHOUETTE_FIELDS), **known})


class Details(BaseModel):
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
    weight: Weight = Field(description="How thick and substantial the cloth is, which decides how the garment sits and what it can be layered under. lightweight: linen, poplin, a thin tee, a thin nylon jacket. midweight: an oxford shirt, a standard tee, chinos. heavyweight: wool flannel, denim, a sweatshirt, a thick overshirt. super_heavy: fleece, sherpa, melton, a puffer, a chunky knit. 'unknown' only when you really cannot tell.")
    knit_gauge: KnitGauge = Field(description="Sweaters and other knitwear: how fine the stitches are, from extra_fine (smooth, thin) to super_chunky; 'na' otherwise.")
    corduroy_wale: CorduroyWale = Field(description="Corduroy only: how wide the ridges are, from needlecord (very fine) to jumbo; 'na' otherwise.")
    color_texture: ColorTexture = Field(description="How the colour sits in the cloth; solid when unremarkable.")
    pattern_name: PatternName = Field(description="The specific pattern; solid when there is none. Flannel is a fabric, never a pattern.")
    pattern_orientation: PatternOrientation = Field(description="Direction of stripes or pattern; all_over for solids and all-over patterns.")
    trim_color: ColorOrSame = Field(description="Colour of a contrasting collar, cuffs or ribbing; 'same' when they match the body.")
    waist: Waist = Field(description="Trousers and shorts only; 'na' otherwise.")
    pant_hem: PantHem = Field(description="Trousers only: turn_up = a turned-up cuff; ribbed = a knitted cuff as on joggers; 'na' otherwise.")
    shoe_style: ShoeStyle = Field(description="Shoes only; 'na' otherwise. derby = open lacing, oxford = closed lacing, slip_on = a laceless canvas shoe.")
    sole_color: ColorOrSame = Field(description="Shoes: colour of the sole; 'same' otherwise.")
    lace_color: ColorOrSame = Field(description="Shoes: colour of the laces; 'same' when they match the upper, there are none, or it is not a shoe.")
    features: list[Feature] = Field(description="Any of these that are present; empty if none. v_insert = the stitched triangle under a sweatshirt's neck; contrast_stitching = topstitching in a thread colour that stands out, as on most blue jeans; side_stripe = a contrast panel or stripe on the side of a shoe.")
    other_features: list[str] = Field(description="Up to four distinctive details nothing above covers, a few words each, e.g. 'embroidered chest logo', 'elbow patches'. Empty if none.")

    @classmethod
    def plain(cls, **known) -> "Details":
        """Nothing distinctive, plus whatever is known."""
        base = dict(fit_detail="regular", sleeve_length="na", neckline="na", collar="none", placket="none", placket_buttons=0,
                    button_color="same", cuff="none", sleeve_construction="na", pockets="none", hem="na", fabric="unknown",
                    fiber="unknown", weight="unknown", knit_gauge="na", corduroy_wale="na",
                    color_texture="solid", pattern_name="solid", pattern_orientation="all_over", trim_color="same",
                    waist="na", pant_hem="na", shoe_style="na", sole_color="same", lace_color="same",
                    features=[], other_features=[])
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
    brand: Optional[str] = Field(description="Only if legible in a photo; never guessed. Otherwise null.")
    size: Optional[str] = Field(description="Only if legible on a tag. Otherwise null.")
    material: Optional[str] = Field(description="Only if legible on a tag. Otherwise null.")
    needs_shot: Optional[ShotRequest] = Field(description="Null unless one more photo would settle something that matters and cannot be told from these.")


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
    if tags.category in ("jeans", "trousers", "shorts"):
        jeans = tags.category == "jeans" or d.pockets == "five_pocket_jean"
        p = {"leg": s.leg or "straight", "length": "short" if tags.category == "shorts" else (s.pant_length or "full"),
             "jeans": jeans}
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
        extras.update(taxonomy.surface_extras(cloth))
        return "pants", p, extras, []
    if tags.category in ("sneakers", "boots", "dress_shoes", "sandals"):
        by_category = {"boots": "boot", "dress_shoes": "derby"}.get(tags.category) or ("high_top" if s.shoe_height == "high" else "low_sneaker")
        style = d.shoe_style if d.shoe_style in SHOE_STYLES else by_category   # no sandal shape yet: drawn as a low shoe
        p = {"height": "high" if style in ("high_top", "boot", "chelsea_boot") else "low", "style": style}
        if "chunky_sole" in d.features:
            p["sole"] = "chunky"
        if "toe_cap" in d.features:
            p["toe_cap"] = "rubber" if (style in ("high_top", "slip_on") or d.fabric == "canvas") else "stitched"
        if "side_stripe" in d.features:
            p["stripe"] = "side"
        if "contrast_heel_tab" in d.features:
            p["heel_tab"] = "contrast"
        return "sneaker", p, extras, (["sandals have no shape of their own yet"] if tags.category == "sandals" else [])
    # a top: the details decide, in the taxonomy's words; the coarse silhouette fills in what the details leave "na"
    category_neck = {"shirt": "collar", "polo": "collar", "hoodie": "hood", "jacket": "collar", "coat": "collar"}.get(tags.category, "crew")
    coarse_neck = s.neck or category_neck
    g = {"fit": d.fit_detail if d.fit_detail != "regular" else _COARSE_FIT.get(s.fit, "regular"),
         "sleeve_length": d.sleeve_length if d.sleeve_length != "na" else _COARSE_SLEEVE.get(
             s.sleeve or ("short" if tags.category in ("tee", "polo") else "long")),
         "collar": d.collar if d.collar != "none" else ("point" if (coarse_neck == "collar" and d.neckline == "na") else "none"),
         "neckline": d.neckline if d.neckline != "na" else _COARSE_NECK.get(coarse_neck, "crew"),
         "placket": d.placket, "placket_buttons": d.placket_buttons if d.placket != "none" else None,
         "cuff": d.cuff, "sleeve_construction": d.sleeve_construction,
         "pockets": d.pockets,
         "hem": d.hem if d.hem != "na" else "straight", **cloth,
         "length": s.top_length or ("long" if tags.category == "coat" else "regular")}
    p, more, notes = top_drawing(g)
    if "v_insert" in d.features:
        p["neck_detail"] = "v-insert"
    return "top", p, {**extras, **more}, notes


def silhouette_params(tags: ItemTags) -> tuple[str, dict]:
    """Map tags to an illustration template and its parameters."""
    return drawing_for(tags)[:2]


def drawing_extras(tags: ItemTags) -> dict:
    """The parts of the drawing that are colours and surfaces, not shape (keyword arguments of `Spec`)."""
    return drawing_for(tags)[2]
