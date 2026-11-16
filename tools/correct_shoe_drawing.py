"""Change one shoe's drawing from a one-line note with the app's own correction and checks (developer tool; not shipped).

    python tools/correct_shoe_drawing.py --photos DIR/shoe-N --drawing RUN/shoe-N.json --note "..."
                                         [--routes plan|api] [--out bench/out/correct_shoe_drawing] [--name NAME]
                                         [--figure boots/chelsea_boot]

`--photos` is one shoe's folder of photos named for their views, as `tools/draw_shoe_photos.py` reads them (side.jpg,
the outer side, first; above.jpg, front.jpg, back.jpg, inner.jpg); `--drawing` is a drawing that tool wrote
(`shoe-N.json`, as kept with an item: version 1 or 2). The drawing is changed and checked exactly as in the app
(`closet/tagger/shoedrawing.py`, `correct`: Claude changes only what the note asks, then at most two checks compare the
change with the photos and with the drawing before it, and say when the note asks for something the photos do not
show), and written to OUT as:

- `NAME.json`: the drawing changed, as the app keeps it (the note in its notes, `corrected`, this change's rounds,
  seconds, each call's tokens and what the API key would charge);
- `NAME.svg`: the pair on two legs, as the item page shows it; `NAME.png`: the check image, the pair large and at phone
  size, as Claude was last shown it; `NAME.before.png`: the same for the drawing before the note;
- `NAME.txt`: what changed, whether the note goes against the photos, and the numbers (also printed);
- with `--figure CATEGORY/STYLE` (today's drawing of the shoe, for example `boots/chelsea_boot`): the drawing before and
  after on the app's As worn figure, as `tools/make_drawn_figure_sheet.py` lays them (`NAME-figure-closeup.png` and
  `NAME-figure-phone.png`; they need Chrome or Chromium on the PATH).

`--routes plan` goes through Claude Code on this computer (the Claude plan); `--routes api` through the API key in
ANTHROPIC_API_KEY, billed. Nothing is counted against the app's monthly limit. OUT is git-ignored by default: the
photos and what is drawn from them never go into the repository.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tools"))

from draw_shoe_photos import VIEWS, photos_of  # noqa: E402

from closet.drawing import drawn  # noqa: E402
from closet.tagger import shoedrawing  # noqa: E402


def numbers(made: shoedrawing.Corrected, kept: dict) -> str:
    calls = "\n".join(f"  {c.kind:<8} {c.seconds:>6.0f} s  {c.input_tokens:>8,} in ({c.cache_read_tokens:,} re-read)  "
                      f"{c.output_tokens:>7,} out  ${c.cost_usd:.2f}" for c in made.calls)
    return (f"note: {made.note}\n"
            f"changed: {made.changed or '(not said)'}\n"
            f"against the photos: {made.against_photos or 'no'}\n"
            f"checks: {made.rounds} | {'said good' if made.good else 'not said good'} | "
            f"{'; '.join(made.problems) or 'no automatic problems'}\n"
            f"seconds: {made.seconds:.0f} | route: {made.route} | tokens in {kept['input_tokens']:,} "
            f"({kept['cache_read_tokens']:,} re-read by Claude Code), out {kept['output_tokens']:,} | "
            f"API-key cost ${kept['cost_usd']:.2f}\n"
            f"calls:\n{calls}\n\n"
            "re-read: tokens Claude Code read again from its cache on the plan route, left out of the API cost (the "
            "API route sends everything once). API cost: what the API key would charge at the prices in "
            "backend/closet/tagger/models.json.")


def figure(before: dict, after: dict, kind: str, out: Path, name: str) -> tuple[Path, Path]:
    from make_drawn_figure_sheet import Shoe, sheets

    category, _, style = kind.partition("/")
    palette = (after.get("sheet") or {}).get("palette") or [{}]
    colour = palette[0].get("hex") or "#6e5a3f"
    today = (category, style, colour, {})
    return sheets([Shoe(f"{name}, before the note", today, before), Shoe(f"{name}, after it", today, after)], out,
                  f"{name}-figure")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--photos", type=Path, required=True, help="the shoe's folder of photos (side.jpg, above.jpg, ...)")
    ap.add_argument("--drawing", type=Path, required=True, help="a drawing tools/draw_shoe_photos.py wrote (.json)")
    ap.add_argument("--note", required=True, help="the owner's one-line note")
    ap.add_argument("--routes", choices=("plan", "api"), default="plan")
    ap.add_argument("--out", type=Path, default=ROOT / "bench" / "out" / "correct_shoe_drawing")
    ap.add_argument("--name", default="", help="the output files' name (the drawing's name with -corrected by default)")
    ap.add_argument("--figure", default="", help="CATEGORY/STYLE of today's drawing, for the As worn figure sheets")
    args = ap.parse_args()
    kept = json.loads(args.drawing.read_text(encoding="utf-8"))
    name = args.name or f"{args.drawing.stem}-corrected"
    args.out.mkdir(parents=True, exist_ok=True)
    client = None
    if args.routes == "api":
        import anthropic
        client = anthropic.Anthropic()
    made = shoedrawing.correct(photos_of(args.photos), kept, args.note, (args.routes,), client=client)
    result = made.to_json([f"{args.photos.name}/{v}" for v, _ in VIEWS],
                          datetime.now(UTC).isoformat(timespec="seconds"), shoedrawing.notes_of(kept))
    (args.out / f"{name}.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    (args.out / f"{name}.svg").write_text(drawn.preview_svg(made.left, made.right), encoding="utf-8")
    (args.out / f"{name}.png").write_bytes(drawn.check_png(made.left, made.right))
    (args.out / f"{name}.before.png").write_bytes(drawn.check_png(kept["left"], kept.get("right")))
    text = numbers(made, result)
    (args.out / f"{name}.txt").write_text(text + "\n", encoding="utf-8")
    print(text)
    if args.figure:
        for path in figure(kept, result, args.figure, args.out, name):
            print(f"wrote {path}")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
