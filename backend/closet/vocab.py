"""The small, coarse vocabulary items are described with.

Kept short on purpose: these are the words that drive outfits and gaps. The
tagging bench uses the same lists (a test keeps the two in step).
"""
from __future__ import annotations

CATEGORY = ["tee", "shirt", "polo", "sweater", "hoodie", "jacket", "coat", "jeans", "trousers", "shorts",
            "sneakers", "boots", "dress_shoes", "sandals", "bag", "belt", "hat", "scarf", "other"]
COLOR = ["black", "white", "grey", "navy", "blue", "light_blue", "green", "olive", "tan", "brown", "cream",
         "red", "burgundy", "pink", "orange", "yellow", "purple", "multi"]
PATTERN = ["solid", "stripe", "plaid", "floral", "camo", "graphic", "other"]
FORMALITY = ["athletic", "casual", "smart_casual", "business", "formal"]
SEASON = ["warm", "cool", "all"]
LOCATION = ["closet", "drawer", "storage"]  # where an item lives when clean; the laundry is its own state (wears.py)
CONDITION = ["new", "good", "worn", "needs_repair"]
RATING = ["love", "like", "meh", "dislike"]
SILHOUETTE = {
    "sleeve": ["none", "short", "long"],
    "neck": ["crew", "v", "collar", "hood", "turtle"],
    "top_length": ["cropped", "regular", "long"],
    "fit": ["slim", "regular", "oversized"],
    "leg": ["tapered", "straight", "wide"],
    "pant_length": ["short", "ankle", "full"],
    "shoe_height": ["low", "high"],
}

ENUM_FIELDS = {"category": CATEGORY, "color": COLOR, "pattern": PATTERN, "formality": FORMALITY,
               "season": SEASON, "location": LOCATION, "condition": CONDITION, "rating": RATING}


def as_dict() -> dict:
    return {**ENUM_FIELDS, "silhouette": SILHOUETTE}
