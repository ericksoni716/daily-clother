"""Let Claude choose outfits for made-up days from the demo closet, to judge the stylist and to measure what one
call takes (developer tool; not shipped).

    python tools/style_demo_days.py [--routes plan|api] [--effort low|medium|high] [--days cold,mild,hot,dinner]
                                    [--model claude-opus-5-5] [--show-brief]

For each day it builds what the app would give the stylist (`closet/styling.py`: the guide, the profile, the demo
closet's wearable pieces, the day hour by hour, what was worn lately, the rules' shortlist), asks Claude once
(`closet/tagger/stylist.py`) and prints: Claude's line about the day, each outfit by its pieces' names with why and
anything to watch, what `styling.check` left out, the seconds, the tokens, and what the call would cost through
the API key at the prices in `tagger/models.json` (worked out from the size of the brief and the answer, since
through the plan Claude Code adds its own context to the count). The rules' own first outfit is printed beside
it, to compare.

`--routes plan` goes through Claude Code on this computer (the Claude plan, nothing billed); `--routes api` through
the API key in ANTHROPIC_API_KEY, billed. Only the demo closet is used: made-up clothes, no photos, nothing of the
owner's. Nothing is written to disk but a temporary copy of the demo closet, and nothing counts against the app's
monthly limit.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from closet import day as dayparts  # noqa: E402
from closet import db, demo, outfits, spend, styling, today, worn  # noqa: E402
from closet.config import Config  # noqa: E402
from closet.tagger import stylist  # noqa: E402
from closet.tagger.tagging import TaggingError  # noqa: E402

CHARS_PER_TOKEN = 3.6   # about what English prose and short lists come to


def hours(temps: dict[int, tuple[float, float]], **at: dict) -> list[dict]:
    """A day hour by hour from (temperature, feels like) at a few hours, held until the next one given."""
    out, now = [], None
    for h in range(24):
        now = temps.get(h, now) or next(iter(temps.values()))
        hour = {"hour": h, "temp_c": now[0], "feels_c": now[1], "rain_chance": 5, "rain_mm": 0.0, "wind_kmh": 8.0,
                "gust_kmh": 15.0, "humidity": 55.0, "uv": 2.0, "summary": "cloudy"}
        hour.update(at.get(f"h{h}", {}))
        out.append(hour)
    return out


WET = {"rain_chance": 80, "rain_mm": 2.5, "summary": "rain"}
DAYS = {
    "cold": {"words": "a cold, wet, windy weekday", "occasion": "smart_casual", "note": None,
             "hours": hours({0: (2, -2), 9: (5, 1), 13: (8, 4), 18: (5, 0)},
                            **{f"h{h}": {**WET, "wind_kmh": 38.0, "gust_kmh": 55.0} for h in (15, 16, 17)},
                            **{f"h{h}": {"wind_kmh": 36.0, "gust_kmh": 50.0} for h in (9, 10, 11, 12, 13, 14)})},
    "mild": {"words": "a mild, dry Saturday", "occasion": "casual", "note": None,
             "hours": hours({0: (11, 11), 10: (16, 16), 14: (19, 19), 19: (15, 15)}, h13={"uv": 5.0}, h14={"uv": 5.0})},
    "hot": {"words": "a hot, humid day spent outside", "occasion": "casual",
            "note": {"active": True, "text": "At a street fair all afternoon, outside from noon to six",
                     "words": ["today", "outside noon to 6pm", "at a street fair"], "outside": [12, 18]},
            "hours": hours({0: (23, 24), 11: (29, 33), 15: (31, 36), 20: (26, 28)},
                           **{f"h{h}": {"humidity": 78.0, "uv": 9.0} for h in range(11, 17)})},
    "dinner": {"words": "a cool evening, dinner out", "occasion": "smart_casual",
               "note": {"active": True, "text": "Dinner with my partner's parents tonight at a nice restaurant",
                        "words": ["today", "dinner with partner's parents"], "outside": None},
               "hours": hours({0: (8, 7), 12: (13, 13), 18: (10, 9), 21: (8, 6)})},
}


def name_of(names: dict[str, str], pieces: dict) -> str:
    ids = [pieces.get(pl) for pl in outfits.PLACES] + list(pieces.get("accessories") or [])
    return ", ".join(names[i] for i in ids if i)


def run(key: str, conn, routes: tuple[str, ...], effort: str, model: str, show: bool) -> dict:
    spec = DAYS[key]
    outside = tuple(spec["note"]["outside"]) if spec["note"] and spec["note"].get("outside") else None
    detail = dayparts.read(spec["hours"], outside, now_hour=7)
    rows = today.closet_rows(conn)
    ctx, _ = outfits.parse_request({"low_c": detail["feels_low_c"], "high_c": detail["feels_high_c"], "rain": detail["wet"],
                                    "occasion": spec["occasion"], "worn_days_ago": today.worn_days_ago(conn)})
    feedback = outfits.feedback_from(worn.rated(conn), rows, ctx)
    engine = outfits.suggest(rows, ctx, styling.SHORTLIST, feedback)["outfits"]
    context = {"place": "New York, United States", "source": "forecast", "detail": detail, "note": spec["note"]}
    brief, listing = styling.brief(rows, context, ctx, date.today(), worn.list_outfits(conn, 30)["outfits"], engine)
    text = stylist.prompt(brief)
    names = dict(listing.names)
    print(f"\n=== {key}: {spec['words']} ({', '.join(detail['words'])}; {spec['occasion'].replace('_', ' ')}) ===")
    if show:
        print(text, "\n")
    if engine:
        print(f"The rules' first outfit: {name_of(names, engine[0]['pieces'])}")
    t0 = time.monotonic()
    try:
        result = stylist.ask(brief, routes, effort=effort, model=model)
    except TaggingError as e:
        print(f"No answer: {type(e).__name__}: {e}")
        return {"day": key, "ok": False}
    seconds = time.monotonic() - t0
    kept, problems = styling.check(stylist.looks(result.answer), listing, ctx, feedback.not_again)
    print(f"Claude on the day: {result.answer.read}")
    for i, o in enumerate(kept, 1):
        print(f"  {i}. {name_of(names, o['pieces'])}\n     Why: {' '.join(o['reasons'])}"
              + (f"\n     Watch: {' '.join(o['warnings'])}" if o["warnings"] else ""))
    for p in problems:
        print(f"  ! {p}")
    tokens_in = round((len(text) + len(stylist.SYSTEM)) / CHARS_PER_TOKEN) + 700   # the answer's form is about 700
    cost = spend.cost_usd(model, tokens_in, result.output_tokens)
    print(f"  {seconds:.1f} s through {result.route}; brief about {tokens_in:,} tokens, answer {result.output_tokens:,} tokens "
          f"(thinking counted); about ${cost:.3f} through the API key")
    return {"day": key, "ok": True, "seconds": seconds, "kept": len(kept), "problems": len(problems), "cost": cost,
            "tokens_in": tokens_in, "tokens_out": result.output_tokens}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--routes", default="plan", choices=("plan", "api"))
    ap.add_argument("--effort", default=stylist.EFFORT, choices=("low", "medium", "high"))
    ap.add_argument("--days", default=",".join(DAYS))
    ap.add_argument("--model", default=stylist.MODEL)
    ap.add_argument("--show-brief", action="store_true", help="print everything Claude is told")
    a = ap.parse_args(argv)
    keys = [k.strip() for k in a.days.split(",") if k.strip()]
    unknown = [k for k in keys if k not in DAYS]
    if unknown or not keys:
        raise SystemExit(f"unknown day {', '.join(unknown)}; choose from {', '.join(DAYS)}")
    with tempfile.TemporaryDirectory(prefix="closet-style-", ignore_cleanup_errors=True) as tmp:
        cfg = Config(data_dir=Path(tmp), auto_download_model=False)
        demo.ensure(cfg)
        conn = db.connect(cfg.db_path("demo"))
        try:
            print(f"{a.model}, effort {a.effort}, through the {a.routes} route; the demo closet")
            done = [run(k, conn, (a.routes,), a.effort, a.model, a.show_brief) for k in keys]
        finally:
            conn.close()
    good = [d for d in done if d["ok"]]
    if good:
        n = len(good)
        print(f"\n{n} of {len(done)} answered. On average: {sum(d['seconds'] for d in good) / n:.1f} s, "
              f"{sum(d['kept'] for d in good) / n:.1f} outfits kept, {sum(d['problems'] for d in good)} left out in all, "
              f"about ${sum(d['cost'] for d in good) / n:.3f} a call through the API key.")
    return 0 if len(good) == len(done) else 1


if __name__ == "__main__":
    raise SystemExit(main())
