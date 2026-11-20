"""Draw shoes from folders of photos with the app's own drawing and checks (developer tool; not shipped).

    python tools/draw_shoe_photos.py --photos DIR [--routes plan|api] [--out bench/out/draw_shoe_photos]
                                     [--shoes 1,3] [--jobs 1] [--model isnet-general-use.onnx]
                                     [--side-only] [--measure]

DIR holds one folder per shoe, `shoe-N/`, with its photos named for their views: side.jpg (the outer side, sent first,
as the app's main photo), above.jpg, front.jpg, back.jpg and inner.jpg (any of them may be missing). The views are
taken from the names, so the photos are not sorted first. A folder may also hold `style.txt`, one word from
`closet/drawing/turned.py`'s STYLES (runner, oxford, chelsea_boot, ...), standing in for the item's description;
without it the drawing's own sheet says what kind of shoe it is. Each shoe is drawn exactly as in the app
(`closet/tagger/shoedrawing.py`: two drawings straight on, the better chosen against the photos, turned out with the 3D
shoe, two turned drawings, the best chosen and its faults fixed, and its side beside the turns), and written to OUT:

- `shoe-N.json`: the sheet, the drawings, the rounds, the seconds, each call's tokens and what the API key would
  charge (as kept with an item);
- `shoe-N.svg`: the pair on two legs, as the item page shows it;
- `shoe-N.png`: the check image, the pair large and at phone size, as Claude was last shown it;
- `shoe-N.straight.png`: the drawing straight on that it was turned from;
- `shoe-N.side.svg` and `shoe-N.side.png`: the side drawing on its card, and its check image (large and at a closet
  tile's size), when it could be made;
- `summary.txt`: a table of rounds, seconds, tokens and the API-key cost per shoe, and the average (also printed).

`--side-only` draws just the side, as the app draws it for a shoe drawn before sides were (`shoedrawing.draw_side`,
with no front drawing to agree with), so a folder holding only `side.jpg` works; it writes `shoe-N.side.svg`,
`shoe-N.side.png` and `shoe-N.side.json` (the side as kept with an item: its SVG, what makes the shoe itself from the
side, the proportions, the rounds, each call's tokens and the API-key cost). `--measure` traces `side.jpg` first with
the app's tracer (the background model with `--model`, else GrabCut) and, when the photo passes its gate, gives the
side its measures, as the app does for a traced shoe.

`--routes plan` goes through Claude Code on this computer (the Claude plan); `--routes api` through the API key in
ANTHROPIC_API_KEY, billed. Nothing is counted against the app's monthly limit. `--model` is the app's background model
file (isnet-general-use.onnx, in the app's models folder): with it each photo is cut to the shoe and the drawing's
light material is measured against the front photo, as in the app; without it the photos are sent whole and that check
is left out. Each shoe runs up to three Claude Code processes at once, so keep `--jobs` low on the plan route. OUT is
git-ignored by default: the photos and what is drawn from them never go into the repository.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from PIL import Image  # noqa: E402

from closet.drawing import drawn, drawnside  # noqa: E402
from closet.tagger import shoedrawing  # noqa: E402

VIEWS = (("side", "outer"), ("above", "top"), ("front", "front"), ("back", "back"), ("inner", "inner"))


def photos_of(folder: Path) -> list[shoedrawing.Photo]:
    out = []
    for name, view in VIEWS:
        path = folder / f"{name}.jpg"
        if path.exists():
            with Image.open(path) as im:
                out.append(shoedrawing.Photo(im.convert("RGB"), view, True))
    if not out:
        raise SystemExit(f"{folder}: no photos (side.jpg, above.jpg, front.jpg, back.jpg, inner.jpg)")
    return out


def mask_maker(model: Path | None):
    """The app's background model as a photo -> mask function, or None."""
    if model is None:
        return None
    import numpy as np

    from closet.cutout import predict_mask
    from closet.modelstore import MODEL
    return lambda img: np.asarray(predict_mask(img, MODEL, model))


def measures_of(folder: Path, mask_of) -> dict | None:
    """The side's measures from the app's trace of `side.jpg`, when it passes the tracing's gate; else None."""
    from closet import tracejobs

    path = folder / "side.jpg"
    if not path.exists():
        return None
    with Image.open(path) as im:
        shoe, reasons = tracejobs.tracer(mask_of)(im.convert("RGB"), {})
    if shoe is None or not shoe.gate.get("ok"):
        print(f"{folder.name}: the side photo did not trace well ({'; '.join(reasons) or 'no reason given'}): no "
              "measures", flush=True)
        return None
    m = drawnside.measures(shoe.profile)
    return m.to_json() if m else None


def write_side(out: Path, name: str, side) -> None:
    (out / f"{name}.side.svg").write_text(drawnside.card_svg(side.svg), encoding="utf-8")
    (out / f"{name}.side.png").write_bytes(drawnside.check_png(side.svg))


def side_one(folder: Path, out: Path, routes: tuple[str, ...], client, mask_of, measure: bool) -> dict:
    """Only the side of the shoe in `folder`, written to OUT."""
    name = folder.name
    t0 = time.monotonic()
    try:
        measures = measures_of(folder, mask_of) if measure else None
        side = shoedrawing.draw_side(photos_of(folder), routes, client=client, measures=measures, mask_of=mask_of)
    except Exception as e:   # one shoe failing does not stop the others
        print(f"{name}: failed after {time.monotonic() - t0:.0f} s: {type(e).__name__}: {e}", flush=True)
        return {"shoe": name, "error": f"{type(e).__name__}: {e}"}
    kept = {**side.to_json(datetime.now(UTC).isoformat(timespec="seconds")), "measures": measures}
    (out / f"{name}.side.json").write_text(json.dumps(kept, indent=1), encoding="utf-8")
    write_side(out, name, side)
    print(f"{name}: side | {side.rounds} checks | {side.seconds:.0f} s | ${kept['cost_usd']:.2f} | "
          f"{'good' if side.good else 'not said good'} | {'; '.join(side.problems) or 'no automatic problems'}",
          flush=True)
    return {"shoe": name, "kind": "side: " + "; ".join(side.features[:2]), "rounds": side.rounds,
            "seconds": side.seconds, "input_tokens": kept["input_tokens"],
            "cache_read_tokens": kept["cache_read_tokens"], "output_tokens": kept["output_tokens"],
            "cost_usd": kept["cost_usd"], "good": side.good, "problems": len(side.problems), "route": side.route}


def draw_one(folder: Path, out: Path, routes: tuple[str, ...], client, mask_of, measure: bool = False) -> dict:
    name = folder.name
    t0 = time.monotonic()
    style_file = folder / "style.txt"
    style = style_file.read_text(encoding="utf-8").strip() or None if style_file.exists() else None
    try:
        measures = measures_of(folder, mask_of) if measure else None
        made = shoedrawing.draw(photos_of(folder), routes, client=client, style=style, mask_of=mask_of,
                                measures=measures)
    except Exception as e:   # one shoe failing does not stop the others
        print(f"{name}: failed after {time.monotonic() - t0:.0f} s: {type(e).__name__}: {e}", flush=True)
        return {"shoe": name, "error": f"{type(e).__name__}: {e}"}
    kept = made.to_json([f"{name}/{v}" for v, _ in VIEWS], datetime.now(UTC).isoformat(timespec="seconds"))
    (out / f"{name}.json").write_text(json.dumps(kept, indent=1), encoding="utf-8")
    view = drawn.VIEWS[made.view]
    (out / f"{name}.svg").write_text(drawn.preview_svg(made.left, made.right, view=view), encoding="utf-8")
    (out / f"{name}.png").write_bytes(drawn.check_png(made.left, made.right, view=view))
    if made.straight:
        (out / f"{name}.straight.png").write_bytes(drawn.check_png(made.straight["left"], made.straight.get("right")))
    if made.side:
        write_side(out, name, made.side)
    print(f"{name}: {made.sheet.get('archetype')} | {made.view}, {made.style or 'not turned'} | {made.rounds} drawings | "
          f"{made.seconds:.0f} s | "
          f"${kept['cost_usd']:.2f} | {'good' if made.good else 'not said good'} | "
          f"{'; '.join(made.problems) or 'no automatic problems'} | "
          f"{'side drawn' if made.side else 'no side'}", flush=True)
    return {"shoe": name, "kind": made.sheet.get("archetype"), "rounds": made.rounds, "seconds": made.seconds,
            "input_tokens": kept["input_tokens"], "cache_read_tokens": kept["cache_read_tokens"],
            "output_tokens": kept["output_tokens"], "cost_usd": kept["cost_usd"], "good": made.good,
            "problems": len(made.problems), "route": made.route}


def table(rows: list[dict]) -> str:
    head = (f"{'shoe':<8} {'rounds':>6} {'seconds':>8} {'input':>9} {'re-read':>9} {'output':>8} {'API cost':>9}  "
            "good  kind")
    lines = [head, "-" * len(head)]
    done = [r for r in rows if "error" not in r]
    for r in rows:
        if "error" in r:
            lines.append(f"{r['shoe']:<8} failed: {r['error']}")
            continue
        lines.append(f"{r['shoe']:<8} {r['rounds']:>6} {r['seconds']:>8.0f} {r['input_tokens']:>9,} "
                     f"{r['cache_read_tokens']:>9,} {r['output_tokens']:>8,} {'$' + format(r['cost_usd'], '.2f'):>9}  "
                     f"{'yes' if r['good'] else 'no ':<4}  {r['kind']}")
    if done:
        n = len(done)
        lines.append("-" * len(head))
        lines.append(f"{'average':<8} {sum(r['rounds'] for r in done) / n:>6.1f} "
                     f"{sum(r['seconds'] for r in done) / n:>8.0f} {sum(r['input_tokens'] for r in done) // n:>9,} "
                     f"{sum(r['cache_read_tokens'] for r in done) // n:>9,} {sum(r['output_tokens'] for r in done) // n:>8,} "
                     f"{'$' + format(sum(r['cost_usd'] for r in done) / n, '.2f'):>9}")
    lines.append("")
    lines.append("input: tokens read, as the route reports them; re-read: of those, read again from the cache by Claude "
                 "Code on the plan route, left out of the API cost (the API route sends everything once). API cost: "
                 "what the API key would charge at the prices in backend/closet/tagger/models.json.")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--photos", type=Path, required=True, help="the folder holding shoe-N/ folders of photos")
    ap.add_argument("--routes", choices=("plan", "api"), default="plan")
    ap.add_argument("--out", type=Path, default=ROOT / "bench" / "out" / "draw_shoe_photos")
    ap.add_argument("--shoes", default="", help="which shoes, by number (for example 1,3); all by default")
    ap.add_argument("--jobs", type=int, default=1, help="shoes drawn at the same time (default 1)")
    ap.add_argument("--model", type=Path, default=None, help="the app's background model file (isnet-general-use.onnx)")
    ap.add_argument("--side-only", action="store_true", help="draw only the side, from side.jpg and any other photos")
    ap.add_argument("--measure", action="store_true", help="trace side.jpg first and give the side its measures")
    args = ap.parse_args()
    folders = sorted((p for p in args.photos.iterdir() if p.is_dir() and p.name.startswith("shoe-")),
                     key=lambda p: (len(p.name), p.name))
    if args.shoes:
        wanted = {f"shoe-{n.strip()}" for n in args.shoes.split(",") if n.strip()}
        folders = [f for f in folders if f.name in wanted]
    if not folders:
        raise SystemExit(f"no shoe-N folders in {args.photos}")
    args.out.mkdir(parents=True, exist_ok=True)
    client = None
    if args.routes == "api":
        import anthropic
        client = anthropic.Anthropic()
    routes = (args.routes,)
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        mask_of = mask_maker(args.model)
        one = side_one if args.side_only else draw_one
        rows = list(pool.map(lambda f: one(f, args.out, routes, client, mask_of, args.measure), folders))
    text = table(rows)
    (args.out / "summary.txt").write_text(text + "\n", encoding="utf-8")
    print()
    print(text)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
