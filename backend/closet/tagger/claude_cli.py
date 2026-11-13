"""Reach Claude through the Claude Code command-line tool (`claude -p`).

This uses the owner's Claude plan instead of an API key: nothing is billed
per call, and usage counts against the plan's limits. The same prompt and
the same schema are used as on the API route, and the answer is validated the
same way.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image

from .schema import ItemTags
from .tagging import CONFIG, PROMPT, PlanSignIn, RouteUnavailable, TaggingError, TagResult

SYSTEM = ("You tag photos of clothes for a private wardrobe app. Look at the image file or files named in the "
          "request with the Read tool, then answer in the required JSON format. Do nothing else.")
# never let a plan call fall through to a paid API key by accident
_SCRUB = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
_LIMIT_WORDS = ("hit your", "usage limit", "limit reached", "out of extra usage")
_LOGIN_WORDS = ("not logged in", "please run /login", "authentication")
# Claude Code using an API key (a Console login, or a key in its own settings) that Anthropic refuses, e.g.
# "API Error: 400 Not a valid API key for this workspace" or "Invalid API key · Fix external API key"
_KEY_WORDS = ("not a valid api key", "invalid api key", "invalid x-api-key", "external api key", "api error: 401")
NOT_SIGNED_IN = "Claude Code is not signed in on this computer (run `claude` once and log in)"
KEY_REFUSED = ("Claude Code on this computer is signed in with an API key that Anthropic turns down, "
               "not with your Claude plan (run `claude`, type /login and choose your Claude subscription)")


def sign_in_problem(text: str) -> str | None:
    """Why Claude Code's sign-in does not work, from what a failed call said (lower case), or None."""
    if any(w in text for w in _KEY_WORDS):
        return KEY_REFUSED
    if any(w in text for w in _LOGIN_WORDS):
        return NOT_SIGNED_IN
    return None


def find_claude() -> str | None:
    found = shutil.which("claude")
    if found:
        return found
    candidate = Path.home() / ".local" / "bin" / ("claude.exe" if sys.platform == "win32" else "claude")
    return str(candidate) if candidate.exists() else None


STATUS_TIMEOUT = 5.0   # seconds; `claude auth status` only reads the local login


def plan_status(exe: str | None = None, timeout: float | None = None) -> tuple[bool, str]:
    """Whether the plan route can be used now, and if not, why, in a sentence the owner can read.

    Runs `claude auth status`, which exits 0 when signed in and asks Claude nothing,
    so it costs nothing. Its output names the account and folders, so it is not even
    read (only the exit code is). The API key is removed from its environment, as for a real
    call, so a key cannot make the plan look signed in.
    """
    exe = exe or find_claude()
    if not exe:
        return False, "Claude Code is not installed on this computer."
    env = {k: v for k, v in os.environ.items() if k not in _SCRUB}
    kwargs = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
    try:   # the output is never read, so no pipes: a grandchild left holding one can't outlast the timeout (Windows)
        proc = subprocess.run([exe, "auth", "status"], env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=STATUS_TIMEOUT if timeout is None else timeout, **kwargs)
    except subprocess.TimeoutExpired:
        return False, "Claude Code did not answer in time. Try again in a moment."
    except OSError:
        return False, "Claude Code is installed but could not be started."
    if proc.returncode != 0:
        return False, "Claude Code is installed but not signed in."
    return True, ""


def strict_schema() -> dict:
    """The answer schema with the same adjustments the API route sends."""
    from anthropic.lib._parse._transform import transform_schema
    return transform_schema(ItemTags)


def _save(img: Image.Image, path: Path, max_edge: int = 1024) -> None:
    im = img.copy()
    im.thumbnail((max_edge, max_edge), Image.LANCZOS)
    if im.mode == "RGBA":
        bg = Image.new("RGB", im.size, (236, 233, 227))
        bg.paste(im, (0, 0), im)
        im = bg
    im.convert("RGB").save(path, "JPEG", quality=88)


def tag_item_cli(model: str, images: list[Image.Image], exe: str | None = None, timeout: float = 240,
                 max_attempts: int = 2) -> TagResult:
    exe = exe or find_claude()
    if not exe:
        raise RouteUnavailable("Claude Code is not installed on this computer (no `claude` command found)")
    effort = CONFIG["models"].get(model, {}).get("effort", "low")
    env = {k: v for k, v in os.environ.items() if k not in _SCRUB}
    t0 = time.time()
    last: Exception | None = None
    with tempfile.TemporaryDirectory(prefix="closet-tag-") as tmp:
        names = []
        for i, im in enumerate(images, 1):
            name = f"photo-{i}.jpg"
            _save(im, Path(tmp) / name)
            names.append(name)
        listing = ", ".join(names)
        prompt = (f"{PROMPT}\n\nThe image file{'s are' if len(names) > 1 else ' is'} in the current folder: {listing}. "
                  "Open each with the Read tool, then give your answer.")
        cmd = [exe, "-p", prompt, "--model", model, "--effort", effort, "--output-format", "json",
               "--json-schema", json.dumps(strict_schema()), "--tools", "Read", "--allowedTools", "Read",
               "--strict-mcp-config", "--no-session-persistence", "--system-prompt", SYSTEM]
        kwargs = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
        for attempt in range(1, max_attempts + 1):
            try:
                proc = subprocess.run(cmd, cwd=tmp, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                      timeout=timeout, **kwargs)
            except subprocess.TimeoutExpired:
                last = TaggingError(f"{model} through Claude Code did not answer within {timeout:.0f} seconds")
                continue
            except OSError as e:
                raise RouteUnavailable(f"Claude Code could not be started: {e}") from e
            try:
                out = json.loads(proc.stdout)
            except ValueError:
                out = {}
            text = f"{out.get('result') or ''} {proc.stderr or ''} {proc.stdout if not out else ''}".lower()
            if any(w in text for w in _LIMIT_WORDS):
                raise RouteUnavailable("the Claude plan's usage limit has been reached: "
                                       + (out.get("result") or proc.stderr or "").strip()[:200])
            problem = sign_in_problem(text) if (proc.returncode != 0 or out.get("is_error")) else None
            if problem:
                raise PlanSignIn(problem)
            answer = out.get("structured_output")
            if proc.returncode != 0 or out.get("is_error") or answer is None:
                detail = (out.get("result") or proc.stderr or "no output").strip()[:200]
                last = TaggingError(f"{model} through Claude Code gave no usable answer (exit {proc.returncode}): {detail}")
                continue
            try:
                tags = ItemTags.model_validate(answer)
            except ValueError as e:
                last = TaggingError(f"{model} through Claude Code answered outside the schema: {e}")
                continue
            usage = out.get("usage") or {}
            tokens_in = sum(int(usage.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
            return TagResult(tags, model, time.time() - t0, tokens_in, int(usage.get("output_tokens") or 0),
                             float(out.get("total_cost_usd") or 0.0), attempt, route="plan")
    raise last or TaggingError(f"{model} through Claude Code gave no answer")
