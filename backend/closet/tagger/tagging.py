"""Ask Claude for an item's attributes and get back validated data.

One function, one call shape. On the API route the answer comes back as a call
of a plain tool holding the whole form, and is checked against the form here
(the plan route's form is enforced by Claude Code, and checked here too); a call
that cannot produce a valid answer fails loudly instead of returning a guess.
"""
from __future__ import annotations

import base64
import io
import json
import time
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, Union, get_args, get_origin

from PIL import Image
from pydantic import BaseModel, Field, ValidationError, create_model
from pydantic.fields import FieldInfo

from . import surfaceform
from .schema import ItemTags

CONFIG = json.loads((Path(__file__).parent / "models.json").read_text())
MAX_TOKENS = 4000   # the longest answer asked for; also the most output a single call can be billed for

PROMPT = """You are cataloguing one item from a man's wardrobe for a private closet app.

The first image is the item with its background removed. Any further images are extra shots of the same item (a care or brand tag, a close-up, or the back).

Fill in the attributes. Guidance:
- Choose the closest value from each list; do not invent values.
- Each confidence is your honest chance of being right, from 0 to 1. Use the whole range: 0.95 when it is plain to see, about 0.5 when it is a coin flip. An over-confident wrong answer costs the owner more than an honest low number.
- Judge the true colour of the cloth, allowing for shadows and warm indoor light.
- Silhouette: fill in only the fields that apply to this kind of item and leave the rest null.
- Details are what make the drawing this particular garment, so look closely and report what is there, not what is usual for the category: count the buttons you can see; say whether a long-sleeved knit top has a buttoned placket (a henley) or none (a plain tee); name the collar (button_down, spread, camp, band ...), the cuff, the pockets and the hem; name the cloth when its structure shows (corduroy, cable, pique, flannel, denim). Where a detail does not apply use "na", "none", "same", "unknown" or 0. details_confidence covers the details as a whole.
- Weight and fibre matter as much as shape: a fleece shirt is far thicker than a linen one, and a wool flannel more substantial than a thin cotton one. Judge weight from how the cloth holds its shape, how thick its edges, cuffs and collar are, and how it folds.
- Say what you see even when it is unusual for the category: a front that closes with snaps is placket "snap"; pockets at the hip are not chest pockets. A placket that stops partway down the chest (a polo, a rugby shirt, a popover) is "polo", "henley" or "half_placket_popover", never "front_placket", which opens all the way to the hem. A slit pocket edged in a contrast piping is a pocket, not a contrast trim: trim_color is for a collar, cuffs or ribbing in a colour of their own. When a features flag fits (a rubber toe bumper is toe_cap), set the flag; do not describe it in other_features as well.
- garment: the kind of clothing in the owner's taxonomy when one plainly fits, else "unknown". It decides when the item is suggested (sportswear for exercise, loungewear at home), so choose a sportswear or loungewear kind only for clothes clearly made for that. Their categories: a fleece_pullover or athletic_half_zip is "sweater" (a warm mid layer, not outerwear); a performance_tee, base_layer or sports jersey is "tee"; a track_jacket, windbreaker or rain_shell is "jacket"; track_pants, joggers, sweatpants, tech_pants, compression_tights and lounge_pants are "trousers"; running, training, basketball and sleep shorts are "shorts". Sportswear is formality "athletic"; loungewear and fleece "casual".
- A garment cut in two colours (a yoke and sleeves in one, the body in another): color is the body's, and the other colour comes first in secondary_colors. A strip in a contrasting colour bound over the edges (collar, placket, cuffs, hem) is trim_color.
- Accessories (a bag, belt, hat or scarf, and a tie, pocket square, gloves, glasses, watch or socks, which are category "other"): say which one it is in accessory and its kind in accessory_kind (a hat is a fedora, a beanie, a trucker_cap ...; a bag a tote, a daypack, a messenger ...). For clothes and shoes both are "na".
- other_features: distinctive things no field covers, in a few words each. Do not repeat what the fields already say.
- Shoes: set footwear to the kind of shoe or boot when you can tell (penny_loafer, cap_toe_oxford, brogue, chukka, desert_boot, service_boot, moc_toe_boot, logger_boot, western_boot, duck_boot, canvas_high_top, retro_runner, trail_runner, boat_shoe, ...), and fill in what shows: the toe shape and treatment (a brogue's wingtip or medallion), the lacing (speed_hooks on a hiking or logger boot, elastic_gussets on a chelsea, monk straps), the eyelets you can count on one side, the sole (lug_commando, crepe, wedge, cupsole, vulcanized ...), the heel, the height and the upper. On a sandal say 'ankle strap' in other_features if it has one. Also say how many shoes the first image shows (shoes_in_photo: one, or pair when both shoes of the pair are in it, even overlapping or one behind the other) and where it sees the shoe from (shoe_view: side only when the whole side shows square on, toe to heel; otherwise front, back, top or angled).
- Trousers, jeans and shorts: fill in the waistband, the fly, the front (flat or pleated, and which way the pleats open), the rise, the leg, the break, the hem finish, the crease and the pockets you can see; on denim the wash, any fades (whiskers, stacks, train_tracks ...) and distressing; on shorts the inseam in inches.
- shade: the owner's name for the main colour's shade (charcoal or slate for a grey, khaki or stone for a tan, raw_indigo for unwashed denim, oxblood for a deep burgundy ...), one of the shades of the colour you chose; 'unknown' when none is close.
- Brand, size and material: only what you can actually read in a photo. Otherwise null.
- needs_shot: leave null unless one more photo would settle something that matters for choosing outfits."""
# the cloth's surface, as the garment loop test asked for it (bench/experiments/garment_loop, arm F)
PROMPT = PROMPT + "\n" + surfaceform.GUIDANCE


class TaggingError(RuntimeError):
    pass


class RouteUnavailable(TaggingError):
    """This way of reaching Claude cannot be used right now (no credits, no login, not installed).

    The caller may try the other route; nothing was wrong with the photo or the prompt.
    """


class ApiRefused(RouteUnavailable):
    """The API turned the key away: `reason` is "credit" (no credit left) or "key" (the key was not accepted)."""

    def __init__(self, message: str, reason: str):
        super().__init__(message)
        self.reason = reason


class PlanSignIn(RouteUnavailable):
    """Claude Code is installed but its sign-in does not work: not signed in, or signed in with an API key
    that Anthropic turns down. The owner has to sign in again; nothing was wrong with the photo or the prompt."""


class Unreachable(TaggingError):
    """Claude could not be reached just now: no network, a connection cut, or Anthropic overloaded or rate
    limiting. Nothing was wrong with the photo or the route's sign-in, so the item waits and is tried again
    later without losing an attempt. Not a `RouteUnavailable`: the other route would most likely be out of reach
    too, and a plan call must never move to the paid route for this."""


class CapReached(RouteUnavailable):
    """The call was not made: it could take this month's API spending past the owner's limit."""


class Meter(Protocol):
    """Counts calls to Claude and may stop a billed one before it is made (the app's spend cap).

    Given only token counts and model names: never a photo, the prompt or an answer.
    """

    def before_api_call(self, model: str, images: int) -> None:
        """Raise `CapReached` if the API call about to be made could go over the limit."""

    def record(self, route: str, model: str, input_tokens: int, output_tokens: int, **cached: int) -> None:
        """One call was made (on the API route: one request, whatever came back). `cached`: `cache_write` and
        `cache_read`, the prompt's tokens written to or read from the cache, when there were any."""

    def api_refused(self, reason: str) -> None:
        """The API refused the key ("credit" or "key")."""

    def release(self) -> None:
        """The request checked last did not come back (optional: `send` calls it when the meter has it)."""


def send(meter: Meter | None, request, **kwargs):
    """Make one API request, `request(**kwargs)`. When it does not come back (an error, no connection), the meter lets
    go of what was held against the limit for it, as no answer is billed."""
    try:
        return request(**kwargs)
    except BaseException:
        if meter is not None and hasattr(meter, "release"):
            meter.release()
        raise


@dataclass
class TagResult:
    tags: ItemTags
    model: str
    seconds: float
    input_tokens: int
    output_tokens: int
    cost_usd: float          # on the plan route: what the call would have cost at API prices; nothing is billed
    attempts: int
    route: str = "api"       # "api" (API key, billed) or "plan" (Claude plan through `claude -p`)


def cost_usd(model: str, input_tokens: int, output_tokens: int, cache_write: int = 0, cache_read: int = 0) -> float:
    price = CONFIG["models"][model]
    return (input_tokens * price["input"] + output_tokens * price["output"]
            + cache_write * price.get("cache_write", price["input"] * 1.25) + cache_read * price.get("cache_read", price["input"])) / 1_000_000


# The prompt's long, unchanging part is marked for Anthropic's prompt cache: describing a closet's worth of photos
# one after another reads the form from the cache at a tenth of the price after the first (5 minutes, renewed by use)
CACHED = {"type": "ephemeral"}


def cached_tokens(usage) -> dict:
    """The prompt's tokens written to and read from the cache, as `Meter.record`'s keywords (none when there were
    none, so a stand-in meter that does not know them still works)."""
    write = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    return {"cache_write": write, "cache_read": read} if write or read else {}


def encode_image(img: Image.Image, max_edge: int = 1024) -> dict:
    """An image content block. Transparent cutouts are flattened onto grey."""
    im = img.copy()
    im.thumbnail((max_edge, max_edge), Image.LANCZOS)
    if im.mode == "RGBA":
        bg = Image.new("RGB", im.size, (236, 233, 227))
        bg.paste(im, (0, 0), im)
        im = bg
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=88)
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.standard_b64encode(buf.getvalue()).decode()}}


# The plan route's form (`SENT`, passed to `claude -p --json-schema`). It lists every word of the main fields
# (category, colour, pattern ...: what the closet sorts and builds outfits by) and, in the details and the silhouette,
# only lists of up to ENUM_IN_GRAMMAR words; a longer list there is plain text, its words named in the field's
# description, and Closet checks the answer against the full form itself (`fitted`). It was made for the API route,
# whose structured output compiles the form into a grammar and refuses one that is too large ("The compiled grammar
# is too large", 400): the full form passed that limit at 939 listed words (schema version 5). The API route no
# longer sends a compiled form at all (`answer_tool`, below). (Tried loosening the main fields too: a boat shoe came
# back as category "other", a word outside the list made to fit.)
ENUM_IN_GRAMMAR = 12
NO_ANSWER = ("unknown", "na", "none", "other")   # what a word outside its list becomes, the first the field allows


def _sent_type(t, keep: bool = False):
    """`t` with every list of more than ENUM_IN_GRAMMAR words made plain text (none when `keep`, as for the main
    fields), and those words, for the description."""
    origin = get_origin(t)
    if isinstance(t, type) and issubclass(t, BaseModel):
        return sent_form(t, keep_main=False), ""
    if origin is Literal:
        words = get_args(t)
        if len(words) > ENUM_IN_GRAMMAR and not keep:
            return str, " One of: " + ", ".join(map(str, words)) + "."
        return t, ""
    if origin in (Union, types.UnionType):
        parts = [_sent_type(a, keep) for a in get_args(t)]
        return Union[tuple(p[0] for p in parts)], "".join(p[1] for p in parts)
    if origin is list:
        inner, words = _sent_type(get_args(t)[0], keep)
        return list[inner], words
    return t, ""


def sent_form(model: type[BaseModel], keep_main: bool = True) -> type[BaseModel]:
    """The form sent for `model`: the same fields; with `keep_main` its own word lists all kept, the long ones of the
    models inside it (the details, the silhouette) as plain text (`_sent_type`)."""
    fields = {}
    for name, f in model.model_fields.items():
        t, words = _sent_type(f.annotation, keep=keep_main)
        info = FieldInfo.merge_field_infos(f, description=(f.description or "") + words) if words else f
        fields[name] = (t, info)
    return create_model(model.__name__ + "Sent", __config__=model.model_config, **fields)


# The form asked for: `ItemTags` with the surface required (null allowed) and the lettering required (empty or null allowed), so
# every new description gives both; the stored form keeps them optional so answers from before stay valid.
ASKED = create_model("ItemTags", __base__=ItemTags, __doc__=ItemTags.__doc__,
                     surface=(surfaceform.Surface | None, Field(description=surfaceform.FIELD_TEXT["surface"])),
                     lettering=(list[surfaceform.Lettering] | None, Field(description=surfaceform.FIELD_TEXT["lettering"])))
SENT = sent_form(ASKED)


def _fit(value, t):
    """`value` made to fit type `t`: a word outside its list becomes the first of NO_ANSWER the list has (unchanged
    when it has none, so the check below refuses it), list entries outside their list are dropped."""
    origin = get_origin(t)
    if isinstance(t, type) and issubclass(t, BaseModel):
        if isinstance(value, dict):
            return {k: _fit(v, t.model_fields[k].annotation) if k in t.model_fields else v for k, v in value.items()}
        return value
    if origin is Literal:
        words = get_args(t)
        if value in words:
            return value
        return next((w for w in NO_ANSWER if w in words), value)
    if origin in (Union, types.UnionType):
        args = get_args(t)
        if value is None and type(None) in args:
            return None
        literal = next((a for a in args if get_origin(a) is Literal), None)
        if literal is not None and isinstance(value, str):
            if value in get_args(literal):
                return value
            fallback = next((w for w in NO_ANSWER if w in get_args(literal)), None)
            return fallback if fallback is not None else (None if type(None) in args else value)
        model = next((a for a in args if isinstance(a, type) and issubclass(a, BaseModel)), None)
        return _fit(value, model) if model is not None and isinstance(value, dict) else value
    if origin is list and isinstance(value, list):
        inner = get_args(t)[0]
        if get_origin(inner) is Literal:
            return [v for v in value if v in get_args(inner)]
        return [_fit(v, inner) for v in value]
    return value


def fitted(answer) -> ItemTags:
    """The API's answer (on the form sent, `SENT`) checked against the full form; raises ValidationError when it
    cannot be made to fit."""
    data = answer.model_dump(mode="json") if isinstance(answer, BaseModel) else answer
    return ItemTags.model_validate(_fit(data, ItemTags))


# ---- the API route: the whole form as a plain tool
#
# Sent as structured output (or as a strict tool), the form is compiled by the API into a grammar, and the API refuses
# a grammar over a size it does not publish: the 939-word form was refused in v0.5.0, #235 cut it to 327 words without
# a way to try that against the API, and the owner reported a description through the API key failing the same way
# again (16 November). A tool that is not strict is not compiled, so its form has no size limit: the API route sends
# the full form (every word of every list) as one and asks for it to be called; Closet checks the answer itself, asks
# again in the same conversation when a main field is outside its list, then fits what is left (`fitted`).
ANSWER_TOOL = "describe_item"
ASK_FOR_TOOL = "Give your answer by calling the describe_item tool once, with every field filled in."
MAIN_FIELDS = ("category", "color", "secondary_colors", "pattern", "formality", "season")   # what the closet sorts by


def _inline(node, defs: dict):
    """`node` with every `{"$ref": "#/$defs/X"}` replaced by X itself (the form has no loops)."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            return _inline(defs[ref.split("/")[-1]], defs)
        return {k: _inline(v, defs) for k, v in node.items() if k != "$defs"}
    if isinstance(node, list):
        return [_inline(v, defs) for v in node]
    return node


def answer_tool() -> dict:
    """The full form as a tool that is not strict (no `strict`): the API does not compile it into a grammar. Its
    parts are written out in place, so it is one schema with no references."""
    from anthropic.lib._parse._transform import transform_schema
    schema = transform_schema(ASKED)
    return {"name": ANSWER_TOOL,
            "description": "Record what the photos show about the item. For a field with a list, use only its words.",
            "input_schema": _inline(schema, schema.get("$defs", {}))}


def _words(name: str) -> tuple:
    t = ItemTags.model_fields[name].annotation
    return get_args(get_args(t)[0]) if get_origin(t) is list else get_args(t)


def main_strays(data) -> dict:
    """The main fields whose answer is not one of their words (for a list, the words that are not)."""
    if not isinstance(data, dict):
        return {name: None for name in MAIN_FIELDS}
    out = {}
    for name in MAIN_FIELDS:
        value, words = data.get(name), _words(name)
        if get_origin(ItemTags.model_fields[name].annotation) is list:
            bad = [v for v in value if v not in words] if isinstance(value, list) else ([] if value is None else [value])
            if bad:
                out[name] = bad
        elif value not in words:
            out[name] = value
    return out


def stray_note(off: dict) -> str:
    """What is said back when main fields are outside their lists: each field, what came, and the words it allows."""
    parts = [f"{name}: {value!r} is not one of its words ({', '.join(_words(name))})" for name, value in off.items()]
    return "Some fields are not in their lists. " + "; ".join(parts) + ". Call describe_item again with the whole answer."


def tag_item(client, model: str, images: list[Image.Image], max_attempts: int = 3, meter: Meter | None = None) -> TagResult:
    """Tag one item. `client` is an `anthropic.Anthropic` (or a stand-in with the same `messages.create`).

    With a `meter`, every request is checked against it before it is sent and counted once it comes back.
    """
    import anthropic

    content = [encode_image(im) for im in images] + [{"type": "text", "text": PROMPT + "\n\n" + ASK_FOR_TOOL}]
    first = [{"role": "user", "content": content}]
    tool = {**answer_tool(), "cache_control": CACHED}   # the form comes first in the prompt and is the same every time
    effort = CONFIG["models"][model].get("effort", "low")
    t0 = time.time()
    cache_write = cache_read = 0
    tokens_in = tokens_out = 0
    last: Exception | None = None
    messages = first
    for attempt in range(1, max_attempts + 1):
        if meter:
            meter.before_api_call(model, len(images))
        try:
            resp = send(
                meter, client.messages.create,
                model=model,
                max_tokens=MAX_TOKENS,
                messages=messages,
                tools=[tool],
                # "auto": forcing the tool is refused by some models (Opus 5.5, Sonnet 5.5); the prompt asks for it
                tool_choice={"type": "auto", "disable_parallel_tool_use": True},
                output_config={"effort": effort},
            )
        except anthropic.RateLimitError as e:
            last = e
            time.sleep(min(30, 2 ** attempt))
            continue
        except anthropic.APIConnectionError as e:
            last = e
            time.sleep(min(30, 2 ** attempt))
            continue
        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                last = e
                time.sleep(min(30, 2 ** attempt))
                continue
            message = str(getattr(e, "message", e))
            if e.status_code in (401, 403) or "credit balance" in message.lower() or "billing" in message.lower():
                reason = "key" if e.status_code in (401, 403) else "credit"
                raise ApiRefused(f"the API key cannot be used right now ({e.status_code}): {message}", reason) from e
            raise TaggingError(f"{model} rejected the request ({e.status_code}): {message}") from e
        tokens_in += resp.usage.input_tokens
        tokens_out += resp.usage.output_tokens
        cached = cached_tokens(resp.usage)
        cache_write += cached.get("cache_write", 0)
        cache_read += cached.get("cache_read", 0)
        if meter:
            meter.record("api", model, resp.usage.input_tokens, resp.usage.output_tokens, **cached)
        if resp.stop_reason == "refusal":
            raise TaggingError(f"{model} declined to tag this photo")
        call = next((b for b in resp.content if getattr(b, "type", None) == "tool_use" and b.name == ANSWER_TOOL), None)
        if resp.stop_reason == "max_tokens" or call is None:
            last = TaggingError(f"{model} returned an incomplete answer (stop_reason={resp.stop_reason})"
                                if resp.stop_reason == "max_tokens" else f"{model} did not answer with the form")
            messages = first   # asked again from the start
            continue
        off = main_strays(call.input)
        if off and attempt < max_attempts:   # said back in the same conversation, so it can put them right
            last = TaggingError(f"{model} answered outside the lists: {off}")
            messages = messages + [
                {"role": "assistant", "content": resp.content},
                {"role": "user", "content": [{"type": "tool_result", "tool_use_id": call.id, "is_error": True,
                                              "content": stray_note(off)}]}]
            continue
        try:
            tags = fitted(call.input)
        except ValidationError as e:
            last = TaggingError(f"{model} answered outside the form: {e.error_count()} problems")
            messages = first
            continue
        return TagResult(tags, model, time.time() - t0, tokens_in + cache_write + cache_read, tokens_out,
                         cost_usd(model, tokens_in, tokens_out, cache_write, cache_read), attempt)
    if isinstance(last, (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.APIStatusError)):
        # every attempt failed to reach Claude (the 4xx answers were raised above): out of reach, not a bad answer
        raise Unreachable(f"{model} could not be reached after {max_attempts} attempts: {type(last).__name__}") from last
    raise TaggingError(f"{model} gave no valid answer after {max_attempts} attempts: {last}")
