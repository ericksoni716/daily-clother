"""Outfits chosen by Claude (the owner, 17 November: "we could make this so much better by inserting real
intelligence into it"; "outfit should be considered in totality"; "rules become preferences").

One question, text only: Claude is given the brief `closet/styling.py` writes (the guide as preferences, the owner's
style profile, every piece that can be worn today on a numbered line, the day hour by hour and in the owner's
words, what was worn lately and what the owner said, and the rules engine's shortlist) and answers with whole
outfits, best first, each with why it works today in a sentence or two for the owner. `styling.check` keeps the
ones that can be worn.

The conversation (the owner: "having a convo might result in better outfits if i can say specifically why i like or
dont like a combination"): when the owner writes about the outfits on their screen, the brief carries `say` (their
message) and `talk` (the outfits shown and what was said today), and the answer is a `Reply`: Claude's words back,
the outfits again when something changes (none when they only asked a question), and at most two things worth
remembering for other days, which the owner is asked about before anything is kept. A plain question later the
same day still carries `talk`, so what the owner said holds for the rest of the day.

The look (the owner's plan, 17 November: "it also looks at the drawn figure of each before offering it"): after
choosing, Claude is shown each outfit drawn on the figure as worn (`closet/drawing/figure.py`) and asked to look
at it as the owner would in a mirror, and at the set side by side; it keeps an outfit exactly or changes it
(`look`, answered as a `Seen`). A second, shorter question: the day, the profile, the closet and the outfits
chosen, without the guide and the history that the choice was already made with.

Asked on the model of the `styling` role (Opus), through the API key first when that is switched on, else the plan,
as the day's note is (`tagger/dayread.py`), under the monthly limit (`closet/stylejobs.py` asks; `closet/app.py`
wires it). `tools/style_demo_days.py` runs it on the demo closet to judge it and to measure a call.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from . import correcting
from .tagging import CONFIG, Meter

MODEL = CONFIG["roles"]["styling"]
COUNT = 3              # outfits asked for
MAX_TOKENS = 3000      # the longest answer: three outfits with their sentences, and a line about the day
TALK_MAX_TOKENS = 3600  # the same with words back to the owner and things to remember
EFFORT = "medium"      # how hard Claude thinks about it (tools/style_demo_days.py tries the others)
LOOK_MAX_TOKENS = 2500  # the look's longest answer: the outfits again and a sentence on what was seen
LOOK_EFFORT = "low"    # the look is a check of a choice already thought through
LOOK_TIMEOUT = 90      # seconds the look may take through the plan (it usually takes about 15)
PICTURE_WIDTH = 360    # how wide each outfit's picture is, in pixels (about 1,000 tall)
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


class Keep(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    about: int = Field(description="0 when it is about the owner's style in general, else the number of the piece "
                                   "it is about.")
    text: str = Field(description="One short sentence in the owner's own voice (\"I don't wear...\", \"Runs warm; "
                                  "not above 15 degrees\"), saying only what they said.")


class Reply(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    reply: str = Field(description="One to three plain sentences to the owner, answering what they just wrote.")
    outfits: list[Look] = Field(description="The outfits again, best first, when something changes; empty when the "
                                            "outfits on the owner's screen stand.")
    remember: list[Keep] = Field(description="Things worth keeping for other days, to offer the owner; usually empty.")


RULES = """- Each outfit has a base top, a bottom and shoes. Add a mid layer, an outer layer and accessories only as the day and the look call for them. Use only numbers from the closet list, and put each piece in a place its line allows.
- Judge each outfit as a whole, the way a person with a good eye would look at it in a mirror: do the colours, textures, proportions and how dressed-up each piece is read as one idea? Would it be comfortable through the hours dressed for, in what the weather does in them, for what the owner is doing?
- Dress for what it feels like in the hours given, not for a number alone: think about wind, rain and when it falls, sun, humidity, time spent outside, and whether a layer can come off indoors.
- Learn from what the owner wore and said: lean towards what they loved, away from what they did not, and never offer again an outfit they said "not again" to. Avoid tops worn in the last couple of days unless there is a reason.
- `why`: speak to the owner plainly, in one or two sentences, about this outfit as a whole today. No piece numbers; name pieces the way their lines do. Do not recite the weather back unless it shaped the choice.
- `watch`: only a real caution, otherwise empty."""


def _give(brief: dict[str, str], count: int) -> str:
    """The last part of the question: what Claude gives back. One of two: outfits for the day, or an answer to
    what the owner just wrote."""
    must = f"\n{brief['must']}\n" if brief.get("must") else ""
    if brief.get("say"):
        return f"""# What to give
The owner has just written to you about the outfits on their screen (the last line of the conversation above). Answer them.

- `reply`: one to three plain sentences to the owner: what you changed and why, or the answer to what they asked. Be straight: when the closet has nothing that does what they ask, say so and offer the nearest thing. No piece numbers; name pieces the way their lines do.
- `outfits`: when they ask for a change, or fault an outfit or a piece, give {count} outfits again, the best first, each clearly different from the others. What they said holds for every one of them when it is about the day or their taste; an outfit they did not fault may stay as it was. When they only ask a question and the outfits can stand, give an empty list: their screen then keeps what it shows.
{must}
{RULES}
- `remember`: usually empty. When what the owner wrote shows something that will hold on other days too (a taste, a rule of theirs, how a piece fits or how they wear it), offer to keep it: `about` is 0 for their style in general, or the number of the piece it is about; `text` is one short sentence in the owner's own voice, saying only what they said. At most two. Nothing that is only about today, and nothing their style profile or the piece's notes already say. The owner is asked before anything is kept."""
    held = ("\n- What the owner told you earlier today (the conversation above) still holds: keep to it."
            if brief.get("talk") else "")
    return f"""# What to give
{count} outfits for today, the best first, each one clearly different from the others (at least two pieces apart where the closet allows).
{must}
{RULES}{held}
- `read`: one sentence on what about today shaped your choices."""


def prompt(brief: dict[str, str], count: int = COUNT) -> str:
    talk = f"\n\n# The conversation with the owner today\n{brief['talk']}" if brief.get("talk") else ""
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
{brief["shortlist"]}{talk}

{_give(brief, count)}"""


class Seen(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    saw: str = Field(description="One or two plain sentences on what the pictures showed that the list did not, and "
                                 "what you changed; empty when nothing needed changing.")
    outfits: list[Look] = Field(description="The final outfits, best first.")


def look_prompt(brief: dict[str, str], count: int) -> str:
    """The question for the look: `brief` is what the choice was made from, with `chosen` (`styling.chosen_words`)."""
    talk = (f"\n\n# The conversation with the owner today\n{brief['talk']}\nWhat the owner told you today still "
            "holds: do not undo it.") if brief.get("talk") else ""
    return f"""You chose the outfits below for the owner to wear today. Each is now drawn on a figure, as worn: outfit-1.png is outfit 1, and so on. The drawings are made from what the app knows about each piece (its colour, pattern, cut, length and weight), so they show the colours side by side, the proportions and where each layer ends. They do not show texture, and the shades are approximate.

Look at each picture the way the owner would look in a mirror before leaving, then at the pictures side by side:
- Colours and patterns as they sit together on the body: does anything fight, or is the whole thing one flat tone?
- Proportions and lengths: where each layer ends against the next, how the trousers meet the shoes, how much of each layer shows.
- The set: are the outfits clearly different to the eye, or nearly the same picture?

Change an outfit only where the picture shows something you would really fix before going out. Otherwise keep it exactly as it is, with the same numbers. Do not change anything for the sake of it, and do not undo what the day needs (warmth, rain, the occasion).

# Today
{brief["day"]}

# How the owner dresses (their style profile)
{brief["profile"]}

# The closet: what can be worn today
{brief["closet"]}

# The outfits you chose
{brief["chosen"]}{talk}

# What to give
- `outfits`: the final {count} outfits, best first. An outfit you keep has the same numbers and may keep its `why`; one you change has a `why` for the outfit as it now is, in one or two plain sentences to the owner (no piece numbers, and no talk of pictures or drawings). `watch`: only a real caution, otherwise empty. Each outfit has a base top, a bottom and shoes; use only numbers from the closet list, each piece in a place its line allows.
- `saw`: one or two plain sentences on what the pictures showed that the list did not and what you changed; empty when you changed nothing."""


def look(brief: dict[str, str], pictures: list, routes: tuple[str, ...], client=None, exe: str | None = None,
         meter: Meter | None = None, model: str = MODEL, effort: str | None = LOOK_EFFORT):
    """Claude's look at the outfits it chose, drawn as worn: `pictures` are the drawings, one for each line of
    `brief["chosen"]`, in order. A `correcting.CorrectionResult` whose `answer` is a `Seen`. Raises as `ask` does."""
    names = [f"outfit-{i}.png" for i in range(1, len(pictures) + 1)]
    return correcting.ask(look_prompt(brief, len(pictures)), pictures, routes, client=client, exe=exe, meter=meter,
                          answer_model=Seen, system=SYSTEM, model=model, names=names, max_tokens=LOOK_MAX_TOKENS,
                          timeout=LOOK_TIMEOUT, effort=effort)


def seen(result) -> dict:
    """A look's answer as `closet/stylejobs.py` takes it: {looks, saw, route, model, input_tokens, output_tokens}."""
    return {"looks": looks(result.answer), "saw": result.answer.saw, "route": result.route, "model": result.model,
            "input_tokens": result.input_tokens, "output_tokens": result.output_tokens}


def ask(brief: dict[str, str], routes: tuple[str, ...], client=None, exe: str | None = None,
        meter: Meter | None = None, model: str = MODEL, effort: str | None = EFFORT, count: int = COUNT):
    """Claude's answer to the brief: a `correcting.CorrectionResult` whose `answer` is a `Looks`, or a `Reply` when
    the brief carries the owner's message (`say`). Raises `RouteUnavailable` (or `CapReached`) when Claude cannot be
    asked, `Unreachable` when it cannot be reached, `TaggingError` when it gives no usable answer."""
    talking = bool(brief.get("say"))
    return correcting.ask(prompt(brief, count), [], routes, client=client, exe=exe, meter=meter,
                          answer_model=Reply if talking else Looks, system=SYSTEM, model=model,
                          max_tokens=TALK_MAX_TOKENS if talking else MAX_TOKENS, effort=effort)


def looks(answer: Looks | Reply | Seen) -> list[dict]:
    """The answer's outfits as plain dictionaries, for `styling.check`."""
    return [look.model_dump() for look in answer.outfits]


def given(result) -> dict:
    """An answer as `closet/stylejobs.py` takes it: {looks, read, reply, remember, route, model, input_tokens,
    output_tokens}. `read` is None for a `Reply`; `reply` is None and `remember` empty for a `Looks`."""
    a = result.answer
    return {"looks": looks(a), "read": getattr(a, "read", None), "reply": getattr(a, "reply", None),
            "remember": [k.model_dump() for k in getattr(a, "remember", [])], "route": result.route,
            "model": result.model, "input_tokens": result.input_tokens, "output_tokens": result.output_tokens}


# ------------------------------------------------------------------ the style conversation
# Settings, Your style, "Talk to Claude about your style" (`closet/stylechat.py`): the owner writes about how they
# dress, not about a day's outfits. A short question, text only: the style profile, the conversation so far that day
# and the owner's message; no closet, no guide, no day. Claude answers in a few sentences and may offer lines to keep in
# the profile, which the owner is asked about before anything is kept. Kept cheap on purpose (the assessment's "Do not
# copy": no streaming, no tools): low effort and a short answer.
CHAT_MAX_TOKENS = 1200   # the longest answer: a few sentences and two short lines to keep
CHAT_EFFORT = "low"      # a conversation, not a choice to think through
CHAT_SYSTEM = ("You are the personal stylist inside a private wardrobe app. You talk with its owner about how they "
               "like to dress, so that you choose their outfits better on other days. Answer in the required JSON "
               "format. Do nothing else.")


class ChatReply(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    reply: str = Field(description="One to three plain sentences to the owner, answering what they just wrote.")
    remember: list[str] = Field(description="Lines worth adding to the owner's style profile, each one short sentence "
                                            "in the owner's own voice; usually empty.")


def chat_prompt(brief: dict[str, str]) -> str:
    """The question for the style conversation: `brief` has `profile` (the profile in force), `talk` (the day's
    conversation before this message, or empty) and `say` (the owner's message)."""
    talk = f"\n\n# The conversation so far today\n{brief['talk']}" if brief.get("talk") else ""
    return f"""Talk with the owner about how they like to dress.

# How the owner dresses (their style profile)
These are the lines you read every time you choose the owner's outfits. This is the owner speaking.
{brief["profile"]}{talk}

# What the owner just wrote
{brief["say"]}

# What to give
- `reply`: one to three plain sentences to the owner. Answer what they wrote, the way a good personal stylist would: straight, warm and specific. When what they said is unclear, or leaves out something that would change what you choose for them (the weather, an occasion, a fit), ask one short question back. Do not list rules, and do not repeat their profile back to them.
- `remember`: usually empty. When what the owner wrote shows something that will hold on other days (a taste, a rule of theirs, how they like things to fit, what they wear for work or at weekends), offer to add it to their profile: one short sentence in the owner's own voice ("I run warm, so one layer fewer than most people"), saying only what they said. At most two. Nothing that is only about one day, and nothing the profile already says. The owner is asked before anything is kept."""


def chat(brief: dict[str, str], routes: tuple[str, ...], client=None, exe: str | None = None,
         meter: Meter | None = None, model: str = MODEL, effort: str | None = CHAT_EFFORT):
    """Claude's answer in the style conversation: a `correcting.CorrectionResult` whose `answer` is a `ChatReply`.
    Raises as `ask` does."""
    return correcting.ask(chat_prompt(brief), [], routes, client=client, exe=exe, meter=meter, answer_model=ChatReply,
                          system=CHAT_SYSTEM, model=model, max_tokens=CHAT_MAX_TOKENS, effort=effort)


def chatted(result) -> dict:
    """A style conversation's answer as `closet/stylechat.py` takes it: {reply, remember, route, model, input_tokens,
    output_tokens}, `remember` as a list of sentences."""
    a = result.answer
    return {"reply": a.reply, "remember": list(a.remember), "route": result.route, "model": result.model,
            "input_tokens": result.input_tokens, "output_tokens": result.output_tokens}
