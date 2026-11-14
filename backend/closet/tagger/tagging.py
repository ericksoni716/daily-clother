"""Ask Claude for an item's attributes and get back validated data.

One function, one call shape. The answer is constrained to the schema by the
API and validated again here; a call that cannot produce a valid answer fails
loudly instead of returning a guess.
"""
from __future__ import annotations

import base64
import io
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PIL import Image

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
- other_features: distinctive things no field covers, in a few words each. Do not repeat what the fields already say.
- Shoes: name the kind of shoe in other_features with its taxonomy id when you can tell (penny_loafer, tassel_loafer, horsebit_loafer, plain_toe_oxford, cap_toe_oxford, wholecut, brogue, derby, monk_strap, sandal, slide, flip_flop, chukka, ...), and on a brogue its toe (wingtip or medallion); on a laced dress shoe the number of eyelets, e.g. '5 eyelets'; on a sandal 'ankle strap' if it has one.
- Brand, size and material: only what you can actually read in a photo. Otherwise null.
- needs_shot: leave null unless one more photo would settle something that matters for choosing outfits."""


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


class CapReached(RouteUnavailable):
    """The call was not made: it could take this month's API spending past the owner's limit."""


class Meter(Protocol):
    """Counts calls to Claude and may stop a billed one before it is made (the app's spend cap).

    Given only token counts and model names: never a photo, the prompt or an answer.
    """

    def before_api_call(self, model: str, images: int) -> None:
        """Raise `CapReached` if the API call about to be made could go over the limit."""

    def record(self, route: str, model: str, input_tokens: int, output_tokens: int) -> None:
        """One call was made (on the API route: one request, whatever came back)."""

    def api_refused(self, reason: str) -> None:
        """The API refused the key ("credit" or "key")."""


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


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    price = CONFIG["models"][model]
    return (input_tokens * price["input"] + output_tokens * price["output"]) / 1_000_000


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


def tag_item(client, model: str, images: list[Image.Image], max_attempts: int = 3, meter: Meter | None = None) -> TagResult:
    """Tag one item. `client` is an `anthropic.Anthropic` (or a stand-in with the same `messages.parse`).

    With a `meter`, every request is checked against it before it is sent and counted once it comes back.
    """
    import anthropic

    content = [encode_image(im) for im in images] + [{"type": "text", "text": PROMPT}]
    effort = CONFIG["models"][model].get("effort", "low")
    t0 = time.time()
    tokens_in = tokens_out = 0
    last: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        if meter:
            meter.before_api_call(model, len(images))
        try:
            resp = client.messages.parse(
                model=model,
                max_tokens=MAX_TOKENS,
                messages=[{"role": "user", "content": content}],
                output_format=ItemTags,
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
        if meter:
            meter.record("api", model, resp.usage.input_tokens, resp.usage.output_tokens)
        if resp.stop_reason == "refusal":
            raise TaggingError(f"{model} declined to tag this photo")
        if resp.stop_reason == "max_tokens" or resp.parsed_output is None:
            last = TaggingError(f"{model} returned an incomplete answer (stop_reason={resp.stop_reason})")
            continue
        return TagResult(resp.parsed_output, model, time.time() - t0, tokens_in, tokens_out,
                         cost_usd(model, tokens_in, tokens_out), attempt)
    raise TaggingError(f"{model} gave no valid answer after {max_attempts} attempts: {last}")
