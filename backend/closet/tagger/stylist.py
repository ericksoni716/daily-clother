"""Outfits chosen by Claude (the owner, 17 November: "we could make this so much better by inserting real
intelligence into it"; "outfit should be considered in totality"; "rules become preferences").

One question, text only: Claude is given the brief `closet/styling.py` writes (the guide as preferences, the owner's
style profile, every piece that can be worn today on a numbered line, the day hour by hour and in the owner's
words, what was worn lately and what the owner said, and the rules engine's shortlist) and answers with whole
outfits, best first, each with why it works today in a sentence or two for the owner. `styling.check` keeps the
ones that can be worn.

Asked on the model of the `styling` role (Opus). Not yet part of Today: `tools/style_demo_days.py` runs it on the
demo closet to judge it and to measure a call. When it is wired in, it goes through the API key first when that is
switched on, else the plan, as the day's note does (`tagger/dayread.py`), under the monthly limit.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from . import correcting
from .tagging import CONFIG, Meter

MODEL = CONFIG["roles"]["styling"]
COUNT = 3              # outfits asked for
MAX_TOKENS = 3000      # the longest answer: three outfits with their sentences, and a line about the day
EFFORT = "medium"      # how hard Claude thinks about it (tools/style_demo_days.py tries the others)
SYSTEM = ("You are the personal stylist inside a private wardrobe app. You choose what its owner wears today from "
          "their own clothes. Answer in the required JSON format. Do nothing else.")


class Look(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    base: int = Field(description="The number of the top worn next to the skin (a tee, shirt, polo or the like).")
    mid: int = Field(description="The number of the mid layer over it (a sweater, cardigan, overshirt), or 0 for none.")
    outer: int = Field(description="The number of the outer layer (a jacket or coat), or 0 for none.")
    bottom: int = Field(description="The number of the trousers, jeans or shorts.")
    shoes: int = Field(description="The number of the shoes.")
    accessories: list[int] = Field(description="The numbers of the accessories worn with it (belt, scarf, hat, bag "
                                               "and so on), at most one of each kind; empty for none.")
    why: str = Field(description="One or two plain sentences to the owner: why this outfit works today, as a whole.")
    watch: str = Field(description="One short sentence on anything to watch out for (for example a suede shoe on a "
                                   "wet day), or empty when there is nothing.")


class Looks(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    read: str = Field(description="One plain sentence to the owner on what about today shaped the choices.")
    outfits: list[Look] = Field(description="The outfits, best first.")


def prompt(brief: dict[str, str], count: int = COUNT) -> str:
    must = f"\n{brief['must']}\n" if brief.get("must") else ""
    return f"""Choose what the owner wears today.

# How the owner dresses (their style profile)
This is the owner speaking. It wins over the guide below.
{brief["profile"]}

# The guide
General menswear notes the owner collected. They are preferences to weigh, never rules: break one whenever the outfit as a whole is better for it.
{brief["guide"]}

# The closet: what can be worn today
One piece per line: its number, name, kind and the place or places it can take in an outfit, colour, cloth and weight, how dressed-up it is, its cut, how the owner rated it, when it was last worn, and the owner's own notes on it in quotes. A note on a piece is the owner's word about that piece and wins over everything else. Pieces in the laundry or otherwise not wearable today are not listed.
{brief["closet"]}

# Today
{brief["day"]}

# What the owner wore lately, and what they said about it
{brief["worn"]}

# A start from the app's rules
The app's own rules would offer these today. Use them only so that nothing obvious is missed; choose better where you can.
{brief["shortlist"]}

# What to give
{count} outfits for today, the best first, each one clearly different from the others (at least two pieces apart where the closet allows).
{must}
- Each outfit has a base top, a bottom and shoes. Add a mid layer, an outer layer and accessories only as the day and the look call for them. Use only numbers from the closet list, and put each piece in a place its line allows.
- Judge each outfit as a whole, the way a person with a good eye would look at it in a mirror: do the colours, textures, proportions and how dressed-up each piece is read as one idea? Would it be comfortable through the hours dressed for, in what the weather does in them, for what the owner is doing?
- Dress for what it feels like in the hours given, not for a number alone: think about wind, rain and when it falls, sun, humidity, time spent outside, and whether a layer can come off indoors.
- Learn from what the owner wore and said: lean towards what they loved, away from what they did not, and never offer again an outfit they said "not again" to. Avoid tops worn in the last couple of days unless there is a reason.
- `why`: speak to the owner plainly, in one or two sentences, about this outfit as a whole today. No piece numbers; name pieces the way their lines do. Do not recite the weather back unless it shaped the choice.
- `watch`: only a real caution, otherwise empty.
- `read`: one sentence on what about today shaped your choices."""


def ask(brief: dict[str, str], routes: tuple[str, ...], client=None, exe: str | None = None,
        meter: Meter | None = None, model: str = MODEL, effort: str | None = EFFORT, count: int = COUNT):
    """Claude's answer to the brief: a `correcting.CorrectionResult` whose `answer` is a `Looks`. Raises
    `RouteUnavailable` (or `CapReached`) when Claude cannot be asked, `Unreachable` when it cannot be reached,
    `TaggingError` when it gives no usable answer."""
    return correcting.ask(prompt(brief, count), [], routes, client=client, exe=exe, meter=meter, answer_model=Looks,
                          system=SYSTEM, model=model, max_tokens=MAX_TOKENS, effort=effort)


def looks(answer: Looks) -> list[dict]:
    """The answer's outfits as plain dictionaries, for `styling.check`."""
    return [look.model_dump() for look in answer.outfits]
