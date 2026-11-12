"""Measure tagging on real photos against an answer key.

    python -m closet_bench.bench --photos private/photos --key private/key.csv

By default it reaches Claude through the Claude plan (`claude -p`, nothing
billed) and uses the API key only if the plan cannot be used; see `--route`.

Reports, per field: accuracy, whether stated confidence matches reality,
cost per item and time, for each model, with and without the optional extra
shot. Photos and results stay in git-ignored folders; nothing printed to the
console names a file.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

from . import cutout as C
from . import fills
from .illustrate import Fill, Spec, render
from .schema import DETAIL_FIELDS, FIELDS, SILHOUETTE_FIELDS, Details, ItemTags, drawing_for, silhouette_params
from .routes import ORDERS, Router
from .tagging import CONFIG, TaggingError, TagResult

ROOT = Path(__file__).resolve().parent.parent
BINS = ((0.0, 0.6), (0.6, 0.8), (0.8, 0.9), (0.9, 1.01))


def load_key(path: Path) -> dict[str, dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = {}
        for row in csv.DictReader(f):
            name = (row.get("file") or "").strip()
            if name:
                rows[name] = {k: (v or "").strip().lower().replace(" ", "_") for k, v in row.items() if k != "file"}
        return rows


def compare(tags: ItemTags, truth: dict) -> dict[str, dict]:
    """Per-field outcome for one item: {field: {correct, confidence, got, want}}; blank key cells are skipped."""
    out = {}
    for f in FIELDS:
        want = truth.get(f)
        if want:
            out[f] = dict(correct=getattr(tags, f) == want, confidence=getattr(tags, f"{f}_confidence"),
                          got=getattr(tags, f), want=want)
    for f in SILHOUETTE_FIELDS:
        want = truth.get(f)
        if want:
            got = getattr(tags.silhouette, f)
            out[f] = dict(correct=got == want, confidence=tags.silhouette_confidence, got=got, want=want)
    for f in DETAIL_FIELDS:
        want = truth.get(f)
        if want:
            got = str(getattr(tags.details, f))
            out[f] = dict(correct=got == want, confidence=tags.details_confidence, got=got, want=want)
    return out


def summarize(outcomes: list[dict[str, dict]]) -> dict:
    """Accuracy and calibration per field over many items."""
    per_field: dict[str, list[dict]] = defaultdict(list)
    for item in outcomes:
        for f, o in item.items():
            per_field[f].append(o)
    summary = {}
    for f, rows in per_field.items():
        n = len(rows)
        bins = []
        ece = 0.0
        for lo, hi in BINS:
            sel = [r for r in rows if lo <= r["confidence"] < hi]
            if not sel:
                bins.append(dict(range=[lo, min(hi, 1.0)], n=0, accuracy=None, mean_confidence=None))
                continue
            acc = sum(r["correct"] for r in sel) / len(sel)
            conf = sum(r["confidence"] for r in sel) / len(sel)
            ece += len(sel) / n * abs(acc - conf)
            bins.append(dict(range=[lo, min(hi, 1.0)], n=len(sel), accuracy=acc, mean_confidence=conf))
        summary[f] = dict(n=n, accuracy=sum(r["correct"] for r in rows) / n, calibration_gap=ece, bins=bins)
    return summary


def recorded_tagger(folder: Path):
    """Score answers saved earlier as `<folder>/<model>/<photo name>.json` instead of calling the API.

    Used to try the prompt and schema with answers produced some other way
    (for example by Claude subagents). Cost and time are not measured.
    """
    def tag(model: str, name: str, images: list) -> TagResult:
        try:
            raw = json.loads((folder / model / (Path(name).stem + ".json")).read_text())
            # answers written by hand or by a subagent may leave out null fields; the API never does
            if isinstance(raw, dict):
                for k in ("brand", "size", "material", "needs_shot"):
                    raw.setdefault(k, None)
                raw.setdefault("secondary_colors", [])
                if isinstance(raw.get("silhouette"), dict):
                    for k in SILHOUETTE_FIELDS:
                        raw["silhouette"].setdefault(k, None)
                # answers recorded before the details existed
                raw["details"] = {**Details.plain().model_dump(), **(raw.get("details") or {})}
                raw.setdefault("details_confidence", 0.0)
            tags = ItemTags.model_validate(raw)
        except OSError as e:
            raise TaggingError("no recorded answer for this item") from e
        except ValueError as e:
            raise TaggingError(f"recorded answer does not fit the schema: {e}") from e
        return TagResult(tags, model, 0.0, 0, 0, 0.0, 1)
    return tag


def run(photos: Path, key_path: Path, models: list[str], out: Path, models_dir: Path, cutout_model: str,
        client=None, recorded: Path | None = None, route: str = "auto") -> Path:
    if recorded is not None:
        tagger = recorded_tagger(recorded)
    else:
        router = Router(route, client=client)

        def tagger(model, name, images):
            return router.tag(model, images)
    key = load_key(key_path)
    out.mkdir(parents=True, exist_ok=True)
    results: dict = {"runs": {}, "items": {}}
    cuts = {}
    for i, (name, truth) in enumerate(sorted(key.items()), 1):
        photo = C.load_photo(photos / name)
        cut, _ = C.make_cutout(photo, C.predict_mask(photo, cutout_model, models_dir))
        extras = [C.load_photo(photos / e.strip()) for e in (truth.get("extra_shots") or "").split(";") if e.strip()]
        cuts[name] = (cut, extras)
        print(f"item {i}/{len(key)}: cutout ready, {len(extras)} extra shot(s)")
    for model in models:
        for variant in ("photo_only", "with_extra_shot"):
            outcomes, cost, secs, failures, n, used = [], 0.0, 0.0, 0, 0, set()
            for name, truth in sorted(key.items()):
                cut, extras = cuts[name]
                if variant == "with_extra_shot" and not extras:
                    continue
                n += 1
                try:
                    r = tagger(model, name, [cut] + (extras if variant == "with_extra_shot" else []))
                except TaggingError as e:
                    failures += 1
                    results["items"].setdefault(name, {})[f"{model}/{variant}"] = {"error": str(e)}
                    continue
                cmp_ = compare(r.tags, truth)
                outcomes.append(cmp_)
                cost += r.cost_usd
                secs += r.seconds
                used.add(r.route)
                results["items"].setdefault(name, {})[f"{model}/{variant}"] = dict(
                    tags=r.tags.model_dump(), outcome=cmp_, cost_usd=r.cost_usd, seconds=r.seconds)
            if n == 0:
                continue
            done = max(1, n - failures)
            results["runs"][f"{model}/{variant}"] = dict(
                items=n, failures=failures, cost_per_item_usd=cost / done, seconds_per_item=secs / done,
                routes=sorted(used), fields=summarize(outcomes))
            print(f"{model} / {variant}: {n} items, {failures} failed, ${cost / done:.5f} per item, {secs / done:.1f}s per item")
    (out / "results.json").write_text(json.dumps(results, indent=1))
    report = out / "report.html"
    show = CONFIG["roles"]["tagging"] if CONFIG["roles"]["tagging"] in models else models[0]
    report.write_text(_report(results, cuts, show, measured=recorded is None))
    return report


def _report(results: dict, cuts: dict, show_model: str, measured: bool = True) -> str:
    h = ["<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
         "<title>Closet tagging bench</title><style>body{font:15px/1.45 system-ui,sans-serif;margin:16px;max-width:1200px}"
         "table{border-collapse:collapse;margin:8px 0 20px}td,th{border:1px solid #ccc;padding:4px 8px;text-align:right}"
         "th:first-child,td:first-child{text-align:left}.bad{background:#f6d5d1}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}"
         ".card{border:1px solid #ccc;border-radius:10px;padding:8px}.pair{display:flex;gap:6px}.pair>*{width:50%;height:auto}"
         "img{background:#eee;border-radius:8px}</style><h1>Tagging bench</h1>"]
    for run_name, r in results["runs"].items():
        if not measured:
            spend = "recorded answers: cost and time not measured"
        elif r.get("routes") == ["plan"]:
            spend = (f"through the Claude plan (nothing billed) · {r['seconds_per_item']:.1f}s per item · "
                     f"would cost about ${r['cost_per_item_usd']:.4f} per item at API prices, including Claude Code's own overhead")
        else:
            spend = (f"${r['cost_per_item_usd']:.5f} per item · {r['seconds_per_item']:.1f}s per item"
                     + (" · some calls went through the Claude plan" if "plan" in (r.get("routes") or []) else ""))
        h.append(f"<h2>{html.escape(run_name)}</h2><p>{r['items']} items · {r['failures']} failed · {spend}</p>")
        h.append("<table><tr><th>Field</th><th>Items</th><th>Accuracy</th><th>Calibration gap</th>"
                 + "".join(f"<th>conf {lo:.1f}–{min(hi, 1.0):.1f}</th>" for lo, hi in BINS) + "</tr>")
        for f, s in r["fields"].items():
            cells = "".join("<td>–</td>" if b["n"] == 0 else f"<td>{b['accuracy']:.0%} right of {b['n']}</td>" for b in s["bins"])
            h.append(f"<tr><td>{f}</td><td>{s['n']}</td><td>{s['accuracy']:.0%}</td><td>{s['calibration_gap']:.2f}</td>{cells}</tr>")
        h.append("</table>")
    h.append(f"<h2>Illustrations from {html.escape(show_model)} tags, beside the cutouts</h2><div class='grid'>")
    for i, (name, runs) in enumerate(sorted(results["items"].items())):
        r = runs.get(f"{show_model}/photo_only")
        if not r or "tags" not in r:
            continue
        tags = ItemTags.model_validate(r["tags"])
        cut = cuts[name][0]
        template, params = silhouette_params(tags)
        base = fills.snap_to_named(fills.dominant_colors(cut)[0][0], tags.color)
        fill = Fill("solid", base)
        if tags.pattern in ("plaid", "floral", "camo", "other"):
            try:
                fill = Fill("swatch", base, swatch=fills.pick_swatch(cut, avoid_center=params.get("front") in ("buttons", "zip"),
                                                                 organic=tags.pattern != "plaid"))
            except ValueError:
                pass
        elif tags.pattern == "stripe":
            st = fills.measure_stripes(cut, "vertical" if tags.details.pattern_orientation == "vertical" else "horizontal")
            fill = Fill("stripes", st.bands[0][0], stripes=st)
        graphic = fills.extract_graphic(cut) if tags.pattern == "graphic" else None
        _, _, extras, approximated = drawing_for(tags)
        if fill.kind == "swatch":   # the photo's own cloth already carries its surface
            extras["texture"] = None
        svg = render(Spec(template, params, fill, graphic, **extras), "line", uid=f"b{i}")
        wrong = [f"{f}: said {o['got']}, key says {o['want']}" for f, o in r["outcome"].items() if not o["correct"]]
        d = tags.details
        seen = [f"{k.replace('_', ' ')} {str(getattr(d, k)).replace('_', ' ')}" for k in DETAIL_FIELDS
                if getattr(d, k) not in ("na", "none", "same", "unknown", "solid", "all_over", "regular", 0)]
        seen += [f.replace("_", " ") for f in d.features]
        not_drawn = ("<br><b>Seen but not drawn:</b> " + html.escape("; ".join(d.other_features + approximated))) if (d.other_features or approximated) else ""
        h.append(f"<div class='card{' bad' if wrong else ''}'><div class='pair'><img src='{fills.data_uri(cut, 300, 'WEBP')}'>{svg}</div>"
                 f"<p>{html.escape(name)}<br>{html.escape('; '.join(wrong) or 'all keyed fields right')}"
                 f"<br><b>Details:</b> {html.escape('; '.join(seen))}{not_drawn}</p></div>")
    h.append("</div>")
    return "".join(h)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--photos", type=Path, default=ROOT / "private" / "photos")
    ap.add_argument("--key", type=Path, default=ROOT / "private" / "key.csv")
    ap.add_argument("--models", nargs="*", default=CONFIG["bench_models"])
    ap.add_argument("--cutout-model", default="isnet-general-use", choices=list(C.MODELS))
    ap.add_argument("--out", type=Path, default=ROOT / "out" / "bench")
    ap.add_argument("--models-dir", type=Path, default=ROOT / "models")
    ap.add_argument("--recorded", type=Path, help="score saved answers in this folder instead of calling Claude")
    ap.add_argument("--route", default="auto", choices=list(ORDERS),
                    help="how to reach Claude: auto = the Claude plan first, the API key only if the plan cannot be used")
    a = ap.parse_args()
    print("report:", run(a.photos, a.key, a.models, a.out, a.models_dir, a.cutout_model, recorded=a.recorded, route=a.route))


if __name__ == "__main__":
    main()
