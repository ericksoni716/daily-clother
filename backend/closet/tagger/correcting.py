"""Turn the owner's sentence about an item ("it has three buttons") into changes to its description.

The same two routes as tagging, tried the same way: the Claude plan through
`claude -p` first, the API key only when the caller allows it, every call
counted by the caller's meter and every API request checked against the
monthly limit before it is made (`spend.Meter`, purpose "correct_item"). Claude is sent
the sentence, the item's current description and the values each part may
take; the item's photo only when the caller passes it (the caller first tries
without it). The answer is a list of changes and what could not be understood;
the caller checks every value against the vocabulary, and nothing is applied
here.
"""
from __future__ import annotations

import functools
import json
import math
import os
import re
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from pydantic import BaseModel, Field

from .. import apikey
from . import claude_cli
from .surfaceform import Lettering, Surface
from .tagging import (
    CACHED,
    CONFIG,
    ApiRefused,
    CapReached,
    Meter,
    PlanSignIn,
    RouteUnavailable,
    TaggingError,
    Unreachable,
    cached_tokens,
    encode_image,
    send,
)

MODEL = CONFIG["roles"]["tagging"]
MAX_TOKENS = 2000    # the longest answer asked for: a few changes and a sentence (`spend.CORRECT_MAX_TOKENS`)
MAX_ATTEMPTS = 2
CLI_TIMEOUT = 120    # seconds a call through the plan may take, unless the caller says otherwise
# The most `max_tokens` the SDK lets a request ask for without streaming: `messages.parse` refuses ("Streaming is
# required for operations that may take longer than 10 minutes") when 3,600 s x max_tokens / 128,000 is over 600 s
# (anthropic 2.8.0, `_base_client._calculate_nonstreaming_timeout`). Larger answers are streamed instead.
NONSTREAMING_MAX_TOKENS = 128_000 * 600 // 3600
# How far into a streamed answer's text the place to cut it short is looked for (`CutShort`); past it, the answer is
# read to its end as usual. A check's `good` and `problems` take a few hundred characters.
CUT_LOOK_CHARS = 20_000
# The output of a request cut short is not reported (it comes in the last `message_delta`, never read), so it is
# estimated from the time the request had: a model cannot have written more tokens than its writing speed allows in
# that time. 200 tokens a second is well above what the drawing model writes at, so the estimate errs high as long as
# that holds; it is still an estimate, not a count, and never more than the request's `max_tokens`.
CUT_TOKENS_PER_SECOND = 200
clock = time.monotonic   # the clock that times a request cut short (tests replace it)
IMAGE_NAME = re.compile(r"[a-z0-9][a-z0-9-]*\.(jpg|png)")   # the names a caller may give the images it sends
SYSTEM = ("You correct the description of one item of clothing in a private wardrobe app, following what its owner "
          "says. If an image file is named in the request, look at it with the Read tool. Answer in the required JSON "
          "format. Do nothing else.")


class Change(BaseModel):
    name: str = Field(description="The name of the part of the description to change, exactly as listed.")
    value: str = Field(description="Its new value, exactly one of the values listed for that name.")


class CorrectionAnswer(BaseModel):
    changes: list[Change]
    not_understood: str = Field(description="What in the sentence could not be turned into the listed values, in a "
                                            "short plain sentence addressed to the owner; empty when everything was understood.")
    needs_photo: bool = Field(description="True when the sentence can only be understood by looking at the item.")
    # the cloth and its lettering, rewritten whole when the sentence is about them (`corrections.understand`)
    cloth: Surface | None = Field(default=None, description=(
        "Null unless the owner's words are about the cloth: its colours, its stripes or checks, parts or sleeves in "
        "another colour, a band across it. Then the whole cloth again, as `cloth` in the description, changed only "
        "as they say."))
    lettering: list[Lettering] | None = Field(default=None, description=(
        "Null unless the owner's words are about letters or words on the item. Then the whole lettering again, as "
        "`lettering` in the description, changed only as they say ([] when they say there is none)."))


@dataclass
class CorrectionResult:
    answer: BaseModel   # a CorrectionAnswer, or another question's answer
    route: str     # "plan" or "api"
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0   # of input_tokens, those read back from a cache: Claude Code's own (the plan route),
                                 # or the prompt cache (the API route, `cache_photos`)
    cache_write_tokens: int = 0  # of input_tokens, those written to the prompt cache (the API route)
    cut_short: bool = False      # the answer stopped being read early (`CutShort`): output_tokens is then not a count
                                 # but an estimate that errs high, from the seconds the request had at
                                 # CUT_TOKENS_PER_SECOND, at most max_tokens (`cut_output`)


@dataclass
class CutShort:
    """The caller's word that a streamed answer may be cut short (`ask`'s `cut_short`; only on the API route, and only
    when the answer is streamed). Once the answer's text has reached its top-level key `at`, `answer` is given the
    fields before it, each read whole, and returns the whole answer to use in its place, or None to read the answer to
    its end as usual. Given an answer, the stream is closed and the rest is never read. The request itself is the
    same, byte for byte: only the reading stops."""
    at: str
    answer: Callable[[dict], BaseModel | None]


_JSON = json.JSONDecoder()
_SPACE = re.compile(r"[ \t\n\r]*")


def fields_before(text: str, key: str) -> dict | None:
    """The top-level fields that come before `key` in a JSON object of which `text` is the beginning, each value read
    whole by the JSON decoder; None while the text has not reached `key` yet. A value counts only once the comma after
    it has come, so a number or a string cut in the middle is never taken for a whole one. Raises `ValueError` when
    the text is not the beginning of an object, or the object ends without `key`."""
    def skip(i: int) -> int:
        return _SPACE.match(text, i).end()
    i = skip(0)
    if i == len(text):
        return None
    if text[i] != "{":
        raise ValueError("not a JSON object")
    fields: dict = {}
    i = skip(i + 1)
    while True:
        if i == len(text):
            return None
        if fields or text[i] in ",}":   # after a field: a comma, or the end of the object
            if text[i] == "}":
                raise ValueError(f"the object ends before {key!r}")
            if text[i] != ",":
                raise ValueError("not a JSON object")
            i = skip(i + 1)
            if i == len(text):
                return None
        if text[i] != '"':
            raise ValueError("not a JSON object")
        try:
            name, i = _JSON.raw_decode(text, i)
        except ValueError:   # the key is still being written
            return None
        i = skip(i)
        if i == len(text):
            return None
        if text[i] != ":":
            raise ValueError("not a JSON object")
        if name == key:
            return fields
        i = skip(i + 1)
        if i == len(text):
            return None
        try:
            value, j = _JSON.raw_decode(text, i)
        except ValueError:   # the value is still being written
            return None
        fields[name] = value
        i = skip(j)


@dataclass
class _Cut:
    """A streamed answer cut short: the answer the caller made, the usage `message_start` gave, and the seconds from
    the request being sent to the stream being closed."""
    answer: BaseModel
    usage: object
    seconds: float


def cut_output(seconds: float, max_tokens: int) -> int:
    """The output tokens a request cut short after `seconds` is counted at: the most it could have written in that
    time at `CUT_TOKENS_PER_SECOND`, rounded up, and never more than its `max_tokens`. An estimate, not a count."""
    return min(max_tokens, math.ceil(max(0.0, seconds) * CUT_TOKENS_PER_SECOND))
def prompt(sentence: str, description: dict, allowed: dict[str, list], with_photo: bool) -> str:
    lines = "\n".join(f"- {name}: {', '.join(str(v) for v in vals)}" for name, vals in allowed.items())
    return f"""The owner of this item says its description is wrong. Their words:

\"\"\"{sentence}\"\"\"

The item's description now (JSON):
{json.dumps(description, indent=1, sort_keys=True)}

The parts of the description that can be changed, each with the only values it can take:
{lines}

Turn what the owner says into changes: each change is one name from the list and one of its values, exactly as written.
- Change only what the owner's words say or plainly imply (for example "it's a henley, not a tee" sets the neckline to henley and the front to a henley placket; "three buttons" sets placket_buttons to 3). Do not change anything else.
- Never guess. If part of what they say does not fit any listed value, or you cannot tell which value they mean, leave it out of the changes and say so in not_understood, in one short plain sentence to the owner.
- Features are "yes" (it has it) or "no" (it does not).
- trim_color is the colour the collar, the cuffs and any ribbing are drawn in, and a strip binding the edges; same draws them in the body's own cloth. "The collar is the same colour as the rest" or "the cuffs match" sets trim_color to same; a collar, cuffs or ribbing in a colour of their own set it to that colour. It is not the cloth.
- fabric plain is a plain weave, a woven cloth. A smooth knit (a T-shirt, a sweatshirt) is jersey or french_terry, never plain.
- The cloth and its lettering (`cloth` and `lettering` in the description) are not in the list: when the owner's words are about them, give the whole new cloth in `cloth` or the whole new lettering in `lettering`, keeping all they do not mention; otherwise leave both null. Lettering is only letters or words they give or you can read; a logo that is a picture or a symbol cannot be drawn, so say so in not_understood.
- {"The image is the item with its background removed." if with_photo else "You have not been shown the item. If the sentence cannot be understood without seeing it (for example \"the colour is wrong\"), set needs_photo to true and give no changes."}"""


def _checked_names(names: list[str] | None, images: list[Image.Image]) -> list[str] | None:
    if names is not None and (len(names) != len(images) or len(set(names)) != len(names)
                              or not all(isinstance(n, str) and IMAGE_NAME.fullmatch(n) for n in names)):
        raise ValueError("give one plain, different file name (like photo-1.jpg or drawing.png) for every image")
    return names


def _png_block(img: Image.Image, max_edge: int = 1024) -> dict:
    """An image content block in PNG, for a drawing: line art is blurred by JPEG."""
    import base64
    import io

    im = img.copy()
    im.thumbnail((max_edge, max_edge), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                        "data": base64.standard_b64encode(buf.getvalue()).decode()}}


def _streamed(client, cut_short: CutShort | None = None, **kwargs):
    """One request streamed, as the SDK requires for a long answer; the whole message once it has come. With
    `cut_short`, the answer's text is looked at as it arrives, and once the caller gives an answer in its place the
    stream is closed and that answer comes back (`_Cut`) with the usage `message_start` gave and the seconds the
    request had (timed by `clock`, from just before it is sent)."""
    sent = clock()
    with client.messages.stream(**kwargs) as stream:
        if cut_short is None:
            return stream.get_final_message()
        text, looking, mark = "", True, f'"{cut_short.at}"'
        for event in stream:
            if not looking or getattr(event, "type", None) != "text":
                continue
            text += event.text
            if len(text) > CUT_LOOK_CHARS:
                looking = False
                continue
            if mark not in text:
                continue
            try:
                fields = fields_before(text, cut_short.at)
            except ValueError:   # not the answer expected: it is read to its end
                looking = False
                continue
            if fields is None:
                continue
            looking = False   # decided once, here
            try:
                answer = cut_short.answer(fields)
            except Exception:   # anything unexpected: read to its end
                answer = None
            if answer is not None:
                return _Cut(answer, stream.current_message_snapshot.usage, clock() - sent)   # leaving closes it
        return stream.get_final_message()


def _parsed(resp, answer_model):
    """The answer in a streamed message, read against its shape; None when it is cut short or does not fit."""
    text = "".join(getattr(block, "text", "") for block in resp.content if getattr(block, "type", None) == "text")
    try:
        return answer_model.model_validate_json(text)
    except ValueError:
        return None


def correct_api(client, model: str, text: str, images: list[Image.Image], meter: Meter | None = None,
                answer_model=CorrectionAnswer, names: list[str] | None = None, max_tokens: int = MAX_TOKENS,
                effort: str | None = None, cache_photos: bool | int = False,
                cut_short: CutShort | None = None) -> CorrectionResult:
    """Through the API key. With a `meter`, every request is checked against it before it is sent and counted
    once it comes back, as for tagging. `answer_model` is the shape of the answer (another short question to
    Claude, such as the landmarks, uses the same way in). `names`: what to call each image, put just before it (a
    name ending in .png is sent as PNG). `max_tokens` above what the SDK allows without streaming
    (`NONSTREAMING_MAX_TOKENS`) is streamed: the answer's schema goes in `output_config.format`, as `messages.stream`
    does with `output_format` itself, and the whole text is read against it once it has come, so an answer cut short
    is still counted at what it cost. `effort` overrides the model's effort in `models.json`. `cut_short`: the answer
    may stop being read early (`CutShort`), when it is streamed; ignored when it is not.

    A request cut short is counted once, as any other: its prompt's tokens (plain, written to the cache, read from it)
    exactly as `message_start` gave them, and its output estimated (`cut_output`). The output's true count only comes
    in the last `message_delta`, after the whole answer, and part of it is thinking that is never shown (the drawing
    model streams its thinking as empty blocks), so it cannot be counted from what arrived. It is estimated as the
    most the model could have written in the seconds from the request being sent to the stream being closed, at
    `CUT_TOKENS_PER_SECOND`, at most `max_tokens`: high, as long as the model writes slower than that
    (`CorrectionResult.cut_short`). The meter held this request at its `max_tokens`, as any other."""
    import anthropic
    from anthropic.lib._parse._transform import transform_schema

    names = _checked_names(names, images)
    content: list[dict] = []
    for i, im in enumerate(images):
        if names:
            content.append({"type": "text", "text": f"{names[i]}:"})
        content.append(_png_block(im) if names and names[i].endswith(".png") else encode_image(im))
    if cache_photos and content:
        # the photos come first and are sent again by the calls that follow (a shoe's drawing, then its checks): read
        # back from Anthropic's prompt cache at a tenth of the price, or less, instead of paying for them each time.
        # A number says how many of the first images are the photos: the marker goes on the last of them, the end of
        # what every call shares, not on a render that changes from call to call (a cache is only read back by a
        # request the same up to where an earlier one was marked)
        photos = len(images) if cache_photos is True else min(int(cache_photos), len(images))
        last = 2 * photos - 1 if names else photos - 1   # with names, each image follows its name
        content[last] = {**content[last], "cache_control": CACHED}
    content.append({"type": "text", "text": text})
    effort = effort or CONFIG["models"][model].get("effort", "low")
    streamed = max_tokens > NONSTREAMING_MAX_TOKENS
    tokens_in = tokens_out = cache_write = cache_read = 0
    last: Exception | None = None
    for _ in range(MAX_ATTEMPTS):
        if meter:
            meter.before_api_call(model, len(images))
        try:
            if streamed:
                resp = send(meter, functools.partial(_streamed, client, cut_short), model=model, max_tokens=max_tokens,
                            messages=[{"role": "user", "content": content}],
                            output_config={"effort": effort, "format": {"type": "json_schema",
                                                                        "schema": transform_schema(answer_model)}})
            else:
                resp = send(meter, client.messages.parse, model=model, max_tokens=max_tokens,
                            messages=[{"role": "user", "content": content}], output_format=answer_model,
                            output_config={"effort": effort})
        except (anthropic.RateLimitError, anthropic.APIConnectionError) as e:
            last = e
            continue
        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                last = e
                continue
            message = str(getattr(e, "message", e))
            if e.status_code in (401, 403) or "credit balance" in message.lower() or "billing" in message.lower():
                reason = "key" if e.status_code in (401, 403) else "credit"
                raise ApiRefused(f"the API key cannot be used right now ({e.status_code})", reason) from e
            raise TaggingError(f"{model} rejected the request ({e.status_code})") from e
        cut = isinstance(resp, _Cut)
        out = cut_output(resp.seconds, max_tokens) if cut else resp.usage.output_tokens   # cut short: estimated
        tokens_in += resp.usage.input_tokens
        tokens_out += out
        cached = cached_tokens(resp.usage)
        cache_write += cached.get("cache_write", 0)
        cache_read += cached.get("cache_read", 0)
        if meter:
            meter.record("api", model, resp.usage.input_tokens, out, **cached)
        if cut:
            return CorrectionResult(resp.answer, "api", model, tokens_in + cache_write + cache_read, tokens_out,
                                    cache_read, cache_write, cut_short=True)
        if resp.stop_reason == "refusal":
            raise TaggingError(f"{model} declined to answer")
        parsed = _parsed(resp, answer_model) if streamed else resp.parsed_output
        if parsed is None or (streamed and resp.stop_reason == "max_tokens"):
            last = TaggingError(f"{model} returned an incomplete answer")
            continue
        return CorrectionResult(parsed, "api", model, tokens_in + cache_write + cache_read, tokens_out, cache_read,
                                cache_write)
    if isinstance(last, (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.APIStatusError)):
        # every try failed to reach Claude (a 4xx is raised above): out of reach, not a bad answer
        raise Unreachable(f"{model} could not be reached: {type(last).__name__}") from last
    raise TaggingError(f"{model} gave no valid answer: {type(last).__name__ if last else 'none'}")


def _save_named(img: Image.Image, path: Path, max_edge: int = 1024) -> None:
    if path.suffix == ".png":   # a drawing: kept sharp
        im = img.copy()
        im.thumbnail((max_edge, max_edge), Image.LANCZOS)
        im.save(path, "PNG")
    else:
        claude_cli._save(img, path, max_edge)


def correct_cli(model: str, text: str, images: list[Image.Image], exe: str | None = None, timeout: float = CLI_TIMEOUT,
                answer_model=CorrectionAnswer, system: str = SYSTEM, tools: str = "Read",
                names: list[str] | None = None, effort: str | None = None) -> CorrectionResult:
    """Through the Claude plan (`claude -p`); the photos, if any, are saved in a folder of its own for it to read:
    one photo as `item.jpg`, several as `photo-1.jpg`, `photo-2.jpg`, ... in their order, and the prompt says
    their names; or, given `names`, each image under its own name (a .png kept as PNG). `tools`: the only Claude Code
    tools it may use, comma-separated (searching shops allows the web ones). `effort` overrides the model's effort in
    `models.json`. Its answer is always read whole: a caller's `CutShort` never reaches this route."""
    from anthropic.lib._parse._transform import transform_schema

    names = _checked_names(names, images)
    exe = exe or claude_cli.find_claude()
    if not exe:
        raise RouteUnavailable("Claude Code is not installed on this computer")
    effort = effort or CONFIG["models"].get(model, {}).get("effort", "low")
    env = {k: v for k, v in os.environ.items() if k not in claude_cli._SCRUB}
    last: Exception | None = None
    with tempfile.TemporaryDirectory(prefix="closet-correct-", ignore_cleanup_errors=True) as tmp:
        if names:
            for im, name in zip(images, names, strict=True):
                _save_named(im, Path(tmp) / name)
            text += (f"\n\nThe image files are in the current folder: {', '.join(names)}. Open each with the Read tool, "
                     "then answer.")
        elif len(images) == 1:
            claude_cli._save(images[0], Path(tmp) / "item.jpg")
            text += "\n\nThe image file is in the current folder: item.jpg. Open it with the Read tool, then answer."
        elif images:
            names = [f"photo-{i}.jpg" for i in range(1, len(images) + 1)]
            for im, name in zip(images, names, strict=True):
                claude_cli._save(im, Path(tmp) / name)
            text += (f"\n\nThe image files are in the current folder, in order: {', '.join(names)} (photo-1.jpg is "
                     "photo 1, and so on). Open each with the Read tool, then answer.")
        # the owner's words go on standard input, never on a command line
        cmd = claude_cli.print_command(exe, model, effort, transform_schema(answer_model), tools, system)
        for _ in range(MAX_ATTEMPTS):
            try:
                with claude_cli.prompt_file(text) as stdin:
                    proc = subprocess.run(cmd, cwd=tmp, env=env, stdin=stdin, capture_output=True, timeout=timeout,
                                          **claude_cli.run_options())
            except subprocess.TimeoutExpired:
                last = TaggingError(f"{model} through Claude Code did not answer within {timeout:.0f} seconds")
                continue
            except OSError as e:
                raise RouteUnavailable("Claude Code could not be started") from e
            try:
                out = json.loads(proc.stdout)
            except ValueError:
                out = {}
            said = f"{out.get('result') or ''} {proc.stderr or ''} {proc.stdout if not out else ''}".lower()
            failed = proc.returncode != 0 or bool(out.get("is_error")) or out.get("structured_output") is None
            if failed and any(w in said for w in claude_cli._LIMIT_WORDS):   # a good answer may use the words
                raise RouteUnavailable("the Claude plan's usage limit has been reached")
            problem = claude_cli.sign_in_problem(said) if (proc.returncode != 0 or out.get("is_error")) else None
            if problem:
                raise PlanSignIn(problem)
            answer = out.get("structured_output")
            if proc.returncode != 0 or out.get("is_error") or answer is None:
                if (proc.returncode != 0 or out.get("is_error")) and any(w in said for w in claude_cli._UNREACHABLE_WORDS):
                    last = Unreachable(f"{model} through Claude Code could not reach Anthropic")
                    continue
                last = TaggingError(f"{model} through Claude Code gave no usable answer (exit {proc.returncode})")
                continue
            try:
                parsed = answer_model.model_validate(answer)
            except ValueError:
                last = TaggingError(f"{model} through Claude Code answered outside the schema")
                continue
            usage = out.get("usage") or {}
            tokens_in = sum(int(usage.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
            return CorrectionResult(parsed, "plan", model, tokens_in, int(usage.get("output_tokens") or 0),
                                    int(usage.get("cache_read_input_tokens") or 0))
    raise last or TaggingError(f"{model} through Claude Code gave no answer")


def correct(sentence: str, description: dict, allowed: dict[str, list], images: list[Image.Image],
            routes: tuple[str, ...], client=None, exe: str | None = None, meter: Meter | None = None) -> CorrectionResult:
    """Ask Claude, trying `routes` in order ("plan", "api"), as tagging does (`routes.Router`): `meter` records every
    call and keeps the API key under its limit, and is told when the API refuses the key. Raises `CapReached` when
    only the limit stood in the way, `RouteUnavailable` when no route could be used for another reason."""
    return ask(prompt(sentence, description, allowed, bool(images)), images, routes, client=client, exe=exe, meter=meter)


def ask(text: str, images: list[Image.Image], routes: tuple[str, ...], client=None, exe: str | None = None,
        meter: Meter | None = None, answer_model=CorrectionAnswer, system: str = SYSTEM,
        model: str = MODEL, names: list[str] | None = None, max_tokens: int | None = None,
        timeout: float | None = None, effort: str | None = None, cache_photos: bool | int = False,
        cut_short: CutShort | None = None) -> CorrectionResult:
    """A question to Claude with an answer of the given shape, through `routes` in order, as `correct`. `names`: a
    file name for each image, which the prompt can refer to (else `item.jpg`, or `photo-1.jpg`, ... on the plan route);
    `max_tokens`: the longest answer the API route allows (streamed when the SDK requires it); `timeout`: how long a
    call through the plan may take, in seconds; `effort`: instead of the model's effort in `models.json`;
    `cache_photos`: mark the photos for the API's prompt cache, for a question asked again about the same photos
    (True: every image is a photo; a number: how many of the first images are); `cut_short`: the answer may stop
    being read early (`CutShort`), on the API route when the answer is streamed. The plan route ignores it and reads
    the whole answer."""
    skipped, capped = [], False
    for route in routes:
        try:
            if route == "plan":
                result = correct_cli(model, text, images, exe=exe, timeout=timeout or CLI_TIMEOUT,
                                     answer_model=answer_model, system=system, names=names, effort=effort)
                if meter:
                    meter.record("plan", result.model, result.input_tokens, result.output_tokens)
                return result
            if route == "api":
                if client is None:
                    if not apikey.get():
                        raise RouteUnavailable("no API key is set")
                    client = apikey.client()
                return correct_api(client, model, text, images, meter=meter, answer_model=answer_model, names=names,
                                   max_tokens=max_tokens or MAX_TOKENS, effort=effort, cache_photos=cache_photos,
                                   cut_short=cut_short)
        except RouteUnavailable as e:
            skipped.append(f"{route}: {e}")
            capped = capped or isinstance(e, CapReached)
            if isinstance(e, ApiRefused) and meter:
                meter.api_refused(e.reason)
    reasons = "; ".join(skipped) or "no route can be used"
    raise (CapReached if capped else RouteUnavailable)(f"Claude cannot be reached right now. {reasons}")
