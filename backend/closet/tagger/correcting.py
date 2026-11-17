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
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from pydantic import BaseModel, Field

from .. import apikey
from . import claude_cli
from .tagging import CONFIG, ApiRefused, CapReached, Meter, PlanSignIn, RouteUnavailable, TaggingError, encode_image, send

MODEL = CONFIG["roles"]["tagging"]
MAX_TOKENS = 2000    # the longest answer asked for: a few changes and a sentence (`spend.CORRECT_MAX_TOKENS`)
MAX_ATTEMPTS = 2
CLI_TIMEOUT = 120    # seconds a call through the plan may take, unless the caller says otherwise
# The most `max_tokens` the SDK lets a request ask for without streaming: `messages.parse` refuses ("Streaming is
# required for operations that may take longer than 10 minutes") when 3,600 s x max_tokens / 128,000 is over 600 s
# (anthropic 2.8.0, `_base_client._calculate_nonstreaming_timeout`). Larger answers are streamed instead.
NONSTREAMING_MAX_TOKENS = 128_000 * 600 // 3600
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


@dataclass
class CorrectionResult:
    answer: BaseModel   # a CorrectionAnswer, or another question's answer
    route: str     # "plan" or "api"
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0   # of input_tokens, those Claude Code read again from its cache (the plan route)


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


def _streamed(client, **kwargs):
    """One request streamed, as the SDK requires for a long answer; the whole message once it has come."""
    with client.messages.stream(**kwargs) as stream:
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
                effort: str | None = None) -> CorrectionResult:
    """Through the API key. With a `meter`, every request is checked against it before it is sent and counted
    once it comes back, as for tagging. `answer_model` is the shape of the answer (another short question to
    Claude, such as the landmarks, uses the same way in). `names`: what to call each image, put just before it (a
    name ending in .png is sent as PNG). `max_tokens` above what the SDK allows without streaming
    (`NONSTREAMING_MAX_TOKENS`) is streamed: the answer's schema goes in `output_config.format`, as `messages.stream`
    does with `output_format` itself, and the whole text is read against it once it has come, so an answer cut short
    is still counted at what it cost. `effort` overrides the model's effort in `models.json`."""
    import anthropic
    from anthropic.lib._parse._transform import transform_schema

    names = _checked_names(names, images)
    content: list[dict] = []
    for i, im in enumerate(images):
        if names:
            content.append({"type": "text", "text": f"{names[i]}:"})
        content.append(_png_block(im) if names and names[i].endswith(".png") else encode_image(im))
    content.append({"type": "text", "text": text})
    effort = effort or CONFIG["models"][model].get("effort", "low")
    streamed = max_tokens > NONSTREAMING_MAX_TOKENS
    tokens_in = tokens_out = 0
    last: Exception | None = None
    for _ in range(MAX_ATTEMPTS):
        if meter:
            meter.before_api_call(model, len(images))
        try:
            if streamed:
                resp = send(meter, functools.partial(_streamed, client), model=model, max_tokens=max_tokens,
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
        tokens_in += resp.usage.input_tokens
        tokens_out += resp.usage.output_tokens
        if meter:
            meter.record("api", model, resp.usage.input_tokens, resp.usage.output_tokens)
        if resp.stop_reason == "refusal":
            raise TaggingError(f"{model} declined to answer")
        parsed = _parsed(resp, answer_model) if streamed else resp.parsed_output
        if parsed is None or (streamed and resp.stop_reason == "max_tokens"):
            last = TaggingError(f"{model} returned an incomplete answer")
            continue
        return CorrectionResult(parsed, "api", model, tokens_in, tokens_out)
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
    `models.json`."""
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
        timeout: float | None = None, effort: str | None = None) -> CorrectionResult:
    """A question to Claude with an answer of the given shape, through `routes` in order, as `correct`. `names`: a
    file name for each image, which the prompt can refer to (else `item.jpg`, or `photo-1.jpg`, ... on the plan route);
    `max_tokens`: the longest answer the API route allows (streamed when the SDK requires it); `timeout`: how long a
    call through the plan may take, in seconds; `effort`: instead of the model's effort in `models.json`."""
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
                                   max_tokens=max_tokens or MAX_TOKENS, effort=effort)
        except RouteUnavailable as e:
            skipped.append(f"{route}: {e}")
            capped = capped or isinstance(e, CapReached)
            if isinstance(e, ApiRefused) and meter:
                meter.api_refused(e.reason)
    reasons = "; ".join(skipped) or "no route can be used"
    raise (CapReached if capped else RouteUnavailable)(f"Claude cannot be reached right now. {reasons}")
