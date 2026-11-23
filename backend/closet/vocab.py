"""The small, coarse vocabulary items are described with.

Kept short on purpose: these are the words that drive outfits and gaps. The
tagger (`closet/tagger/schema.py`) uses the same lists (a test keeps the two in step).
"""
from __future__ import annotations

from datetime import date

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


# An item's formality may span two neighbouring levels (a penny loafer that is smart casual or business): it keeps its
# formality, the level it sits at most, and `formality_also`, the level right above or below that it can also be worn
# at (null for one level).
FIRST_FORMALITY = "Choose its formality first, then the level it can also be."
NOT_NEXT = ("A piece can count as two levels only when they are next to each other, such as smart casual and "
            "business.")


def formality_span(level: str | None, also: str | None) -> tuple[str | None, str | None]:
    """A formality and the level it can also be, as they are kept: `also` None for one level (the level itself counts
    as one). Raises ValueError, in words the owner can read, when `also` is not right above or below `level`."""
    if also is None or also == level:
        return level, None
    if level is None:
        raise ValueError(FIRST_FORMALITY)
    if abs(FORMALITY.index(level) - FORMALITY.index(also)) != 1:
        raise ValueError(NOT_NEXT)
    return level, also


def formality_words(level: str | None, also: str | None = None) -> str:
    """The formality in plain words, the lower level first: "smart casual", "smart casual to business"."""
    levels = sorted({w for w in (level, also) if w in FORMALITY}, key=FORMALITY.index)
    return " to ".join(w.replace("_", " ") for w in levels)


MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")


def day_words(d: date) -> str:
    """A day as the server writes it in a sentence for the owner: "3 November 2026" (Not worn, What's missing)."""
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def days_words(first: date, last: date) -> str:
    """Two days in a few words: "3 and 22 November 2026", "28 October and 4 November 2026", "3 November 2026" (one
    day), or both in full across a year end."""
    if first == last:
        return day_words(first)
    if first.year != last.year:
        return f"{day_words(first)} and {day_words(last)}"
    start = str(first.day) if first.month == last.month else f"{first.day} {MONTHS[first.month - 1]}"
    return f"{start} and {day_words(last)}"
