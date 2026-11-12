"""The attribute vocabulary and the shape of a tagging answer.

Deliberately small and coarse: these are the fields that drive outfits and
gaps. Every field carries the model's confidence so the review queue can show
only what is uncertain. Every property is required (nullable where it may not
apply): the API's schema-constrained output is at its most dependable with no
optional properties, and the answer then never silently omits a field.
"""
from __future__ import annotations

from typing import Literal, Optional

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

FIELDS = ("category", "color", "pattern", "formality", "season")
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
    brand: Optional[str] = Field(description="Only if legible in a photo; never guessed. Otherwise null.")
    size: Optional[str] = Field(description="Only if legible on a tag. Otherwise null.")
    material: Optional[str] = Field(description="Only if legible on a tag. Otherwise null.")
    needs_shot: Optional[ShotRequest] = Field(description="Null unless one more photo would settle something that matters and cannot be told from these.")


def silhouette_params(tags: ItemTags) -> tuple[str, dict]:
    """Map tags to an illustration template and its parameters."""
    s = tags.silhouette
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
    if tags.category == "shirt":
        p.update(front="buttons", hem="curved", cuffs="button" if p["sleeve"] == "long" else "plain")
    elif tags.category in ("sweater", "hoodie"):
        p.update(hem="rib", cuffs="rib" if p["sleeve"] == "long" else "plain")
    elif tags.category in ("jacket", "coat"):
        p.update(front="zip" if p["neck"] == "hood" else "buttons", pockets="low")
    return "top", p
