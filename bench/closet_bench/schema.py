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

# ---- details: what makes the drawing this garment
ColorOrSame = Literal[("same",) + get_args(Color)]          # "same" = matches the body, or does not apply
Closure = Literal["none", "half_placket", "full_buttons", "full_zip", "quarter_zip"]
Pockets = Literal["none", "chest", "two_chest", "low", "chest_and_low", "kangaroo", "cargo"]
Hem = Literal["plain", "curved", "ribbed", "turn_up"]
Cuffs = Literal["na", "plain", "ribbed", "buttoned"]
Texture = Literal["smooth", "corduroy", "rib_knit", "cable_knit", "waffle", "fleece", "denim", "suede", "leather", "canvas", "other"]
Waist = Literal["na", "belt_loops", "drawstring", "elastic"]
ShoeStyle = Literal["na", "low_sneaker", "high_top", "runner", "boot", "chelsea_boot", "loafer", "derby", "sandal"]
Feature = Literal["v_insert", "raglan_sleeves", "pleats", "toe_cap", "side_stripe"]

FIELDS = ("category", "color", "pattern", "formality", "season")
DETAIL_FIELDS = ("closure", "button_count", "button_color", "pockets", "hem", "cuffs", "texture", "trim_color",
                 "waist", "shoe_style", "sole_color", "lace_color")
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
    closure: Closure = Field(description="How the front opens. A polo or henley has a half_placket; a plain tee, sweatshirt or pullover has none; trousers and shoes: none.")
    button_count: int = Field(description="Buttons you can count on the front opening, including one on a collar stand. 0 when there are none or it does not apply.")
    button_color: ColorOrSame = Field(description="Colour of the buttons; 'same' when they match the cloth or there are none.")
    pockets: Pockets = Field(description="Visible front pockets. two_chest = one on each side of the chest; cargo = pockets on the thighs.")
    hem: Hem = Field(description="Bottom edge. ribbed = a knitted band; curved = a shirt tail; turn_up = trousers with a turned-up cuff.")
    cuffs: Cuffs = Field(description="Sleeve ends; 'na' for anything without long sleeves.")
    texture: Texture = Field(description="The surface of the cloth where it is plain to see; smooth when unremarkable.")
    trim_color: ColorOrSame = Field(description="Colour of a contrasting collar, cuffs or ribbing; 'same' when they match the body.")
    waist: Waist = Field(description="Trousers and shorts only; 'na' otherwise.")
    shoe_style: ShoeStyle = Field(description="Shoes only; 'na' otherwise.")
    sole_color: ColorOrSame = Field(description="Shoes: colour of the sole; 'same' otherwise.")
    lace_color: ColorOrSame = Field(description="Shoes: colour of the laces; 'same' when they match the upper, there are none, or it is not a shoe.")
    features: list[Feature] = Field(description="Any of these that are present; empty if none. v_insert = the stitched triangle under a sweatshirt's neck.")
    other_features: list[str] = Field(description="Up to four distinctive details nothing above covers, a few words each, e.g. 'embroidered chest logo', 'elbow patches'. Empty if none.")

    @classmethod
    def plain(cls, **known) -> "Details":
        """Nothing distinctive, plus whatever is known."""
        base = dict(closure="none", button_count=0, button_color="same", pockets="none", hem="plain", cuffs="na",
                    texture="smooth", trim_color="same", waist="na", shoe_style="na", sole_color="same",
                    lace_color="same", features=[], other_features=[])
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
DRAWN_TEXTURES = ("corduroy", "rib_knit", "cable_knit", "waffle")


def silhouette_params(tags: ItemTags) -> tuple[str, dict]:
    """Map tags to an illustration template and its parameters."""
    s, d = tags.silhouette, tags.details
    if tags.category in ("jeans", "trousers", "shorts"):
        return "pants", {"leg": s.leg or "straight",
                         "length": "short" if tags.category == "shorts" else (s.pant_length or "full"),
                         "jeans": tags.category == "jeans"}
    if tags.category in ("sneakers", "boots", "dress_shoes", "sandals"):
        return "sneaker", {"height": s.shoe_height or ("high" if tags.category == "boots" else "low")}
    p = {"sleeve": s.sleeve or ("short" if tags.category in ("tee", "polo") else "long"),
         "neck": s.neck or {"shirt": "collar", "polo": "collar", "hoodie": "hood", "jacket": "collar", "coat": "collar"}.get(tags.category, "crew"),
         "length": s.top_length or ("long" if tags.category == "coat" else "regular"),
         "fit": s.fit or "regular"}
    # what the tagger saw decides the details; the category is not allowed to guess them
    p["front"] = {"none": "none", "half_placket": "half", "full_buttons": "buttons", "full_zip": "zip",
                  "quarter_zip": "quarter-zip"}[d.closure]
    if d.closure in ("half_placket", "full_buttons"):
        p["buttons"] = d.button_count
    p["pockets"] = {"chest": "chest", "two_chest": "chest-two", "low": "low", "chest_and_low": "chest-low",
                    "kangaroo": "kangaroo"}.get(d.pockets, "none")
    p["hem"] = {"curved": "curved", "ribbed": "rib"}.get(d.hem, "straight")
    p["cuffs"] = {"ribbed": "rib", "buttoned": "button"}.get(d.cuffs, "plain") if p["sleeve"] == "long" else "plain"
    if "v_insert" in d.features:
        p["neck_detail"] = "v-insert"
    if "raglan_sleeves" in d.features:
        p["shoulder"] = "raglan"
    return "top", p


def drawing_extras(tags: ItemTags) -> dict:
    """The parts of the drawing that are colours and surfaces, not shape (keyword arguments of `Spec`)."""
    d = tags.details
    return {"button_color": NAMED_HEX.get(d.button_color), "trim_color": NAMED_HEX.get(d.trim_color),
            "texture": d.texture if d.texture in DRAWN_TEXTURES else None,
            "sole_color": NAMED_HEX.get(d.sole_color)}
