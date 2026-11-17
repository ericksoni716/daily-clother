"""Time the plan route (`claude -p`) several ways, to see where the seconds go (developer tool; not shipped).

    python tools/time_plan_route.py [--photos FILE_OR_DIR ...] [--runs 3] [--ways today,inline,lean,ready]
                                    [--ready-wait 10] [--model claude-haiku-5-5]

Each run describes the same photos with the app's own tagging prompt and answer form, once per way, the ways taken
in turn so a slow minute on Anthropic's side falls on all of them alike:

- `today`: exactly what the app does now (`claude_cli.tag_item_cli`): the photos written to a folder, and Claude
  opens them with its Read tool, which costs a second trip to Claude.
- `inline`: the photos sent inside the message (`--input-format stream-json`), with no tools at all.
- `lean`: as `inline`, and Claude Code loads none of this computer's settings, skills or slash commands
  (`--setting-sources ""`, `--disable-slash-commands`).
- `ready`: as `lean`, but Claude Code was started `--ready-wait` seconds before the photos were sent, as a server
  that keeps one waiting would do. Only the time from sending to the answer is counted. A fresh Claude Code is used
  for each call, so one item's photos never reach another item's answer.

It prints, for each way, the middle and the fastest time in seconds and how many answers fitted the form, then what
each change saves. `lean` minus `ready` is about how long Claude Code takes to start. Nothing else is printed: no
answers, no account, no photos. Uses the Claude plan through Claude Code on this computer (no API key, nothing
billed; it counts against the plan's usage like any description). The default photos are the demo closet's.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from PIL import Image  # noqa: E402

from closet.tagger import claude_cli  # noqa: E402
from closet.tagger.tagging import CONFIG, PROMPT, TaggingError, fitted  # noqa: E402

WAYS = ("today", "inline", "lean", "ready")
DEMO = ROOT / "backend" / "closet" / "demo_data" / "images"
SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
INLINE_SYSTEM = ("You tag photos of clothes for a private wardrobe app. Look at the photo or photos in the request, "
                 "then answer in the required JSON format. Do nothing else.")
LEAN = ["--setting-sources", "", "--disable-slash-commands"]


def photo_paths(given: list[str]) -> list[Path]:
    if not given:
        return sorted(p for p in DEMO.iterdir() if p.suffix in SUFFIXES and ".cut." not in p.name)[:1]
    out: list[Path] = []
    for g in given:
        p = Path(g)
        out += sorted(q for q in p.iterdir() if q.suffix.lower() in SUFFIXES) if p.is_dir() else [p]
    if not out:
        raise SystemExit("no photos found (.jpg, .jpeg, .png or .webp)")
    return out


def jpeg_b64(im: Image.Image) -> str:
    """The photo as the app sends it on the plan route today: at most 1024 px, JPEG."""
    buf = io.BytesIO()
    im = im.copy()
    im.thumbnail((1024, 1024), Image.LANCZOS)
    if im.mode == "RGBA":
        bg = Image.new("RGB", im.size, (236, 233, 227))
        bg.paste(im, (0, 0), im)
        im = bg
    im.convert("RGB").save(buf, "JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def message(images: list[Image.Image]) -> str:
    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": jpeg_b64(im)}}
               for im in images]
    content.append({"type": "text", "text": PROMPT})
    return json.dumps({"type": "user", "message": {"role": "user", "content": content}}) + "\n"


def stream_command(exe: str, model: str, lean: bool) -> list[str]:
    effort = CONFIG["models"].get(model, {}).get("effort", "low")
    cmd = claude_cli.print_command(exe, model, effort, claude_cli.strict_schema(), "", INLINE_SYSTEM)
    i = cmd.index("--output-format")
    cmd[i + 1] = "stream-json"
    cmd[1:1] = ["--input-format", "stream-json", "--verbose"]   # stream-json output needs --verbose with -p
    return cmd + (LEAN if lean else [])


def stream_call(cmd: list[str], msg: str, ready_wait: float | None, timeout: float) -> tuple[float, bool, float | None]:
    """One description through a Claude Code reading messages on standard input. With `ready_wait`, Claude Code is
    started that long before the message is sent, and only the time after sending counts. Started in an empty
    folder, as the app's calls are, so no project's settings are picked up. Also returns the seconds Claude Code
    says it spent waiting on Anthropic."""
    env = {k: v for k, v in os.environ.items() if k not in claude_cli._SCRUB}
    with tempfile.TemporaryDirectory(prefix="closet-time-", ignore_cleanup_errors=True) as tmp:
        return _stream_call(cmd, msg, ready_wait, timeout, env, tmp)


def _stream_call(cmd, msg, ready_wait, timeout, env, cwd) -> tuple[float, bool, float | None]:
    t0 = time.monotonic()
    proc = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            env=env, **claude_cli.run_options())
    timer = threading.Timer(timeout + (ready_wait or 0), proc.kill)
    timer.start()
    try:
        if ready_wait:
            time.sleep(ready_wait)
            t0 = time.monotonic()
        proc.stdin.write(msg)
        proc.stdin.flush()
        for line in proc.stdout:
            try:
                out = json.loads(line)
            except ValueError:
                continue
            if out.get("type") == "result":
                seconds = time.monotonic() - t0
                api = out.get("duration_api_ms")
                good = usable(out.get("structured_output")) and not out.get("is_error")
                return seconds, good, (api / 1000 if isinstance(api, (int, float)) else None)
        return time.monotonic() - t0, False, None
    finally:
        timer.cancel()
        try:
            proc.stdin.close()
        except OSError:
            pass
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def usable(answer) -> bool:
    if answer is None:
        return False
    try:
        fitted(answer)
        return True
    except ValueError:
        return False


def today_call(exe: str, model: str, images: list[Image.Image], timeout: float) -> tuple[float, bool, float | None]:
    """The app's own call, unchanged; Claude Code's report is read on the way past for the seconds spent waiting on
    Anthropic (the app does not keep them)."""
    seen: list = []
    run = subprocess.run

    def watched(*args, **kwargs):
        proc = run(*args, **kwargs)
        seen.append(proc)
        return proc

    t0 = time.monotonic()
    subprocess.run = watched   # claude_cli calls subprocess.run; only this tool's own process is changed
    try:
        claude_cli.tag_item_cli(model, images, exe=exe, timeout=timeout, max_attempts=1)
        good = True
    except TaggingError:
        good = False
    finally:
        subprocess.run = run
    seconds = time.monotonic() - t0
    try:
        api = json.loads(seen[-1].stdout).get("duration_api_ms")
    except (IndexError, ValueError, TypeError, AttributeError):
        api = None
    return seconds, good, (api / 1000 if isinstance(api, (int, float)) else None)


def summary(times: dict[str, list[float]], ok: dict[str, int], runs: int,
            claude: dict[str, list[float | None]] | None = None) -> list[str]:
    """The table and what each change saves. `claude`: per way and run, the seconds Claude Code said it waited on
    Anthropic (None where it did not say). The rest of a call is Claude Code itself: starting, reading its settings,
    the Read tool's own work. Claude's seconds swing by several from call to call, so each change is judged on
    both parts apart."""
    claude = claude or {}
    lines = [f"{'way':<8}{'total':>8}{'fastest':>9}{'Claude':>8}{'itself':>8}  answers"]
    total, api, own = {}, {}, {}
    for way, ts in times.items():
        total[way] = statistics.median(ts)
        pairs = [(t, c) for t, c in zip(ts, claude.get(way, []), strict=False) if c is not None]
        if pairs:
            api[way] = statistics.median(c for _, c in pairs)
            own[way] = statistics.median(t - c for t, c in pairs)
        a = f"{api[way]:>7.1f}s" if way in api else f"{'-':>8}"
        o = f"{own[way]:>7.1f}s" if way in own else f"{'-':>8}"
        lines.append(f"{way:<8}{total[way]:>7.1f}s{min(ts):>8.1f}s{a}{o}  {ok[way]} of {runs} fitted the form")
    lines.append("")
    said = (("today", "inline", "Photos in the message instead of the Read tool"),
            ("inline", "lean", "Not loading this computer's settings and slash commands"),
            ("lean", "ready", "Claude Code started ahead of the call"))
    for a, b, words in said:
        if a in total and b in total:
            parts = [f"{total[a] - total[b]:+.1f}s in all"]
            if a in api and b in api:
                parts.append(f"{api[a] - api[b]:+.1f}s of Claude's time")
            if a in own and b in own:
                parts.append(f"{own[a] - own[b]:+.1f}s of Claude Code's own")
            lines.append(f"{words}: saves {', '.join(parts)}")
    if "today" in own:
        lines.append(f"Today Claude Code's own part is {own['today']:.1f}s of {total['today']:.1f}s: the most a faster "
                     "start could save.")
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--photos", nargs="*", default=[], help="photo files or folders (default: one demo photo)")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--ways", default=",".join(WAYS))
    ap.add_argument("--ready-wait", type=float, default=10.0, help="seconds Claude Code waits before the photos come")
    ap.add_argument("--model", default=CONFIG["roles"]["tagging"])
    ap.add_argument("--timeout", type=float, default=240.0)
    a = ap.parse_args(argv)
    ways = [w.strip() for w in a.ways.split(",") if w.strip()]
    unknown = [w for w in ways if w not in WAYS]
    if unknown or not ways:
        raise SystemExit(f"unknown way {', '.join(unknown)}; choose from {', '.join(WAYS)}")
    exe = claude_cli.find_claude()
    if not exe:
        raise SystemExit("Claude Code is not installed on this computer")
    signed_in, why = claude_cli.plan_status(exe)
    if not signed_in:
        raise SystemExit(why)
    images = []
    for p in photo_paths(a.photos):
        with Image.open(p) as im:
            images.append(im.convert("RGBA") if im.mode in ("RGBA", "LA", "P") else im.convert("RGB"))
    msg = message(images)
    commands = {"inline": stream_command(exe, a.model, lean=False), "lean": stream_command(exe, a.model, lean=True)}
    times: dict[str, list[float]] = {w: [] for w in ways}
    claude: dict[str, list[float | None]] = {w: [] for w in ways}
    ok = dict.fromkeys(ways, 0)
    print(f"{len(images)} photo(s), {a.runs} run(s), {a.model}, Claude Code at {exe}")
    for run in range(1, a.runs + 1):
        for way in ways:
            if way == "today":
                seconds, good, api = today_call(exe, a.model, images, a.timeout)
            else:
                cmd = commands["inline" if way == "inline" else "lean"]
                seconds, good, api = stream_call(cmd, msg, a.ready_wait if way == "ready" else None, a.timeout)
            times[way].append(seconds)
            claude[way].append(api)
            ok[way] += good
            own = f" (itself {seconds - api:.1f}s)" if api is not None else ""
            print(f"  run {run} {way:<7}{seconds:6.1f}s{own} {'ok' if good else 'no usable answer'}", flush=True)
    print()
    print("\n".join(summary(times, ok, a.runs, claude)))
    print("(Claude: the seconds Claude Code says it waited on Anthropic. itself: the rest, Claude Code's own work.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
