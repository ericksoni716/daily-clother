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

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from pydantic import BaseModel, Field

from . import claude_cli
from .tagging import CONFIG, ApiRefused, CapReached, Meter, RouteUnavailable, TaggingError, encode_image

MODEL = CONFIG["roles"]["tagging"]
MAX_TOKENS = 2000    # the longest answer asked for: a few changes and a sentence (`spend.CORRECT_MAX_TOKENS`)
MAX_ATTEMPTS = 2
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
    answer: CorrectionAnswer
    route: str     # "plan" or "api"
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


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


def correct_api(client, model: str, text: str, images: list[Image.Image], meter: Meter | None = None) -> CorrectionResult:
    """Through the API key. With a `meter`, every request is checked against it before it is sent and counted
    once it comes back, as for tagging."""
    import anthropic

    content = [encode_image(im) for im in images] + [{"type": "text", "text": text}]
    effort = CONFIG["models"][model].get("effort", "low")
    tokens_in = tokens_out = 0
    last: Exception | None = None
    for _ in range(MAX_ATTEMPTS):
        if meter:
            meter.before_api_call(model, len(images))
        try:
            resp = client.messages.parse(model=model, max_tokens=MAX_TOKENS, messages=[{"role": "user", "content": content}],
                                         output_format=CorrectionAnswer, output_config={"effort": effort})
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
        if resp.parsed_output is None:
            last = TaggingError(f"{model} returned an incomplete answer")
            continue
        return CorrectionResult(resp.parsed_output, "api", model, tokens_in, tokens_out)
    raise TaggingError(f"{model} gave no valid answer: {type(last).__name__ if last else 'none'}")


def correct_cli(model: str, text: str, images: list[Image.Image], exe: str | None = None, timeout: float = 120) -> CorrectionResult:
    """Through the Claude plan (`claude -p`); the photo, if any, is saved in a folder of its own for it to read."""
    from anthropic.lib._parse._transform import transform_schema

    exe = exe or claude_cli.find_claude()
    if not exe:
        raise RouteUnavailable("Claude Code is not installed on this computer")
    effort = CONFIG["models"].get(model, {}).get("effort", "low")
    env = {k: v for k, v in os.environ.items() if k not in claude_cli._SCRUB}
    last: Exception | None = None
    with tempfile.TemporaryDirectory(prefix="closet-correct-") as tmp:
        if images:
            claude_cli._save(images[0], Path(tmp) / "item.jpg")
            text += "\n\nThe image file is in the current folder: item.jpg. Open it with the Read tool, then answer."
        cmd = [exe, "-p", text, "--model", model, "--effort", effort, "--output-format", "json",
               "--json-schema", json.dumps(transform_schema(CorrectionAnswer)), "--tools", "Read", "--allowedTools", "Read",
               "--strict-mcp-config", "--no-session-persistence", "--system-prompt", SYSTEM]
        kwargs = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
        for _ in range(MAX_ATTEMPTS):
            try:
                proc = subprocess.run(cmd, cwd=tmp, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                      timeout=timeout, **kwargs)
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
            if any(w in said for w in claude_cli._LIMIT_WORDS):
                raise RouteUnavailable("the Claude plan's usage limit has been reached")
            if (proc.returncode != 0 or out.get("is_error")) and any(w in said for w in claude_cli._LOGIN_WORDS):
                raise RouteUnavailable("Claude Code is not signed in on this computer")
            answer = out.get("structured_output")
            if proc.returncode != 0 or out.get("is_error") or answer is None:
                last = TaggingError(f"{model} through Claude Code gave no usable answer (exit {proc.returncode})")
                continue
            try:
                parsed = CorrectionAnswer.model_validate(answer)
            except ValueError:
                last = TaggingError(f"{model} through Claude Code answered outside the schema")
                continue
            usage = out.get("usage") or {}
            tokens_in = sum(int(usage.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
            return CorrectionResult(parsed, "plan", model, tokens_in, int(usage.get("output_tokens") or 0))
    raise last or TaggingError(f"{model} through Claude Code gave no answer")


def correct(sentence: str, description: dict, allowed: dict[str, list], images: list[Image.Image],
            routes: tuple[str, ...], client=None, exe: str | None = None, meter: Meter | None = None) -> CorrectionResult:
    """Ask Claude, trying `routes` in order ("plan", "api"), as tagging does (`routes.Router`): `meter` records every
    call and keeps the API key under its limit, and is told when the API refuses the key. Raises `CapReached` when
    only the limit stood in the way, `RouteUnavailable` when no route could be used for another reason."""
    text = prompt(sentence, description, allowed, bool(images))
    skipped, capped = [], False
    for route in routes:
        try:
            if route == "plan":
                result = correct_cli(MODEL, text, images, exe=exe)
                if meter:
                    meter.record("plan", result.model, result.input_tokens, result.output_tokens)
                return result
            if route == "api":
                if client is None:
                    if not os.environ.get("ANTHROPIC_API_KEY"):
                        raise RouteUnavailable("no API key is set")
                    import anthropic
                    client = anthropic.Anthropic()
                return correct_api(client, MODEL, text, images, meter=meter)
        except RouteUnavailable as e:
            skipped.append(f"{route}: {e}")
            capped = capped or isinstance(e, CapReached)
            if isinstance(e, ApiRefused) and meter:
                meter.api_refused(e.reason)
    reasons = "; ".join(skipped) or "no route can be used"
    raise (CapReached if capped else RouteUnavailable)(f"Claude cannot be reached right now. {reasons}")
