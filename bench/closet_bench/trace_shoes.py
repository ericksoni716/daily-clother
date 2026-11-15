"""Trace shoe photos into the flat drawing style, and find out whether it works (#192, stage 1).

    python -m closet_bench.trace_shoes [--photos private/shoes] [--out out/trace_shoes]
                                       [--cutout auto|model|grabcut] [--model isnet-general-use] [--no-png]

For every photo in the folder (side-on photos of one shoe each; `private/` is git-ignored):

1. Cut the shoe out with the app's own background removal (`closet.cutout`) when its model file is in
   `models/`, otherwise with OpenCV's GrabCut.
2. Turn it so it lies the way the templates draw a shoe: sole level, toe to the left.
3. Trace it with each approach in `APPROACHES` (k-means colours; mean-shift then k-means; bilateral
   filter then k-means; two settings each): the silhouette, colour regions in the shoe's measured colours,
   marks (logos, stripes, panels) as paths, the sole as its own region, specks removed and curves smoothed,
   drawn with the app's outline weight.
4. Score each trace (silhouette IoU against the cut-out, colour error of its regions against the photo,
   how many colours and paths, whether the high-contrast marks survived) and combine the scores.
5. Check the photo against a quality gate made of measured signals (`GATE`), so that the app can later fall
   back to its template drawing on its own when a photo is too poor to trace.

It writes one comparison sheet per photo (`shoe-NN.sheet.svg`, and `.png` when Chrome or Chromium is on the
PATH): the photo, the cut-out, every trace and today's template drawing, at item size and at grid-tile
size; an `index.html` with the scores, the gate and the recommended approach; and `results.json`.

The template drawing is drawn from a tagger answer saved beside the photo as `<photo name>.json`, when
there is one; otherwise from the measured colour and a sneaker of the measured height. Photos are listed
by number in name order, never by file name.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from closet.drawing.trace import (  # noqa: F401  (the tracing lives in the app; these names are the bench's too)
    APPROACH,
    CARD_H,
    CARD_W,
    GATE,
    SHOE_G,
    SHOE_L,
    SHOE_X0,
    WORK,
    Approach,
    Gate,
    Oriented,
    Scores,
    Trace,
    clean_mask,
    delta_e,
    gate,
    grabcut_mask,
    mark_mask,
    orient,
    placement,
    raster,
    remove_specks,
    score,
    to_lab,
    to_svg,
    trace,
)
from closet.drawing.trace import trace_photo as read_photo
from PIL import Image

from . import cutout as C
from . import fills
from .illustrate import CARD

ROOT = Path(__file__).resolve().parent.parent
PHOTO_TYPES = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif")
ITEM_PX, TILE_PX = 400, 160     # the item page shows a drawing about 400 px wide; a closet grid tile about 160

APPROACHES = (
    Approach("kmeans-4", "k-means, 4 colours", "none", 4, 0.004, 1.5),
    Approach("kmeans-6", "k-means, 6 colours, light smoothing", "none", 6, 0.0025, 1.0),
    Approach("meanshift-soft", "mean-shift (8/16), then 5 colours", "meanshift", 5, 0.003, 1.2, 8, 16),
    Approach("meanshift-strong", "mean-shift (16/32), then 5 colours", "meanshift", 5, 0.005, 2.0, 16, 32),
    APPROACH,
    Approach("bilateral-5-smooth", "bilateral filter, 5 colours, strong smoothing", "bilateral", 5, 0.007, 2.5),
)


def model_mask(img: Image.Image, model: str, models_dir: Path) -> np.ndarray | None:
    """The app's own background removal, when its model file is already in `models_dir` (never downloaded here)."""
    if not (models_dir / f"{model}.onnx").exists():
        return None
    from closet import cutout as app_cutout
    path = C.ensure_model(model, models_dir)   # checks the pinned checksum
    return np.asarray(app_cutout.predict_mask(img, model, path))


# ------------------------------------------------------------------ one photo

@dataclass
class Variant:
    approach: Approach
    trace: Trace
    scores: Scores
    svg: str


@dataclass
class Result:
    photo: Image.Image
    cutout: Image.Image | None
    cutout_by: str
    oriented: Oriented | None
    variants: list[Variant]
    gate: Gate
    template_svg: str | None
    seconds: float
    best: str | None = None
    answer: bool = False                                          # the template was drawn from a saved tagger answer
    mask: np.ndarray | None = field(default=None, repr=False)   # the cleaned cut-out mask, the photo's size


def template_svg(answer, color_hex: str, aspect: float, uid: str) -> str | None:
    """Today's template drawing for the shoe: from its tagger answer when there is one, else a sneaker of its height."""
    from closet.drawing import item
    if answer is not None:
        svg = item.svg_from_answer(answer, color_hex, uid=uid)
        if svg:
            return svg
    return item.svg_from_fields("sneakers", color_hex, silhouette={"shoe_height": "high" if aspect < 1.8 else "low"}, uid=uid)


def cutters(cutout: str = "auto", model: str = "isnet-general-use", models_dir: Path = ROOT / "models"):
    """The ways to cut a photo out, in the order to try them: the app's model when its file is in `models_dir`
    (`auto`, `model`), and GrabCut (`auto`, `grabcut`)."""
    out = []
    if cutout in ("auto", "model"):
        if cutout == "model" and not (models_dir / f"{model}.onnx").exists():
            raise SystemExit(f"the cut-out model is not in {models_dir}: run the hard cases once, or use --cutout grabcut")
        out.append((model, lambda img: model_mask(img, model, models_dir)))
    if cutout in ("auto", "grabcut"):
        out.append(("grabcut", grabcut_mask))
    return out


def trace_photo(img: Image.Image, cutout: str = "auto", model: str = "isnet-general-use",
                models_dir: Path = ROOT / "models", answer=None, uid: str = "s",
                approaches: tuple[Approach, ...] = APPROACHES) -> Result:
    rd = read_photo(img, cutters(cutout, model, models_dir), approaches)
    if rd.oriented is None:
        return Result(img, None, rd.cutout_by, None, [], rd.gate, None, rd.seconds, mask=rd.mask)
    cut, _ = C.make_cutout(img, Image.fromarray(rd.mask * 255))
    variants = [Variant(v.approach, v.trace, v.scores, to_svg(v.trace, f"{uid}v{n}")) for n, v in enumerate(rd.variants)]
    best = next(v for v in variants if v.approach.name == rd.best)
    tmpl = template_svg(answer, best.trace.regions[0].color, rd.oriented.aspect, f"{uid}t")
    return Result(img, cut, rd.cutout_by, rd.oriented, variants, rd.gate, tmpl, rd.seconds, rd.best, answer is not None, rd.mask)


# ------------------------------------------------------------------ the sheet

def _place(svg: str, x: float, y: float, w: float, h: float) -> str:
    """A drawing's own <svg> placed in a cell of the sheet."""
    head = re.match(r"<svg\b[^>]*>", svg).group(0)
    new = re.sub(r'\s(width|height|x|y)="[^"]*"', "", head)[:-1] + f' x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}">'
    return new + svg[len(head):]


def _prefix_ids(svg: str, p: str) -> str:
    """The same drawing twice on one sheet: its ids made different."""
    return svg.replace(' id="', f' id="{p}').replace("url(#", f"url(#{p}").replace('href="#', f'href="#{p}')


def _image_cell(img: Image.Image, x: float, y: float, w: float, h: float, checker: bool, fmt: str) -> str:
    uri = fills.data_uri(img, 640, fmt, 80)
    bg = 'fill="url(#chk)"' if checker else f'fill="{CARD}"'
    return (f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" rx="{w * 0.045:.0f}" {bg}/>'
            f'<image href="{uri}" x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" preserveAspectRatio="xMidYMid meet"/>')


def _text(x: float, y: float, s: str, size: int = 15, weight: str = "normal", color: str = "#26231f") -> str:
    return (f'<text x="{x:.0f}" y="{y:.0f}" font-family="system-ui,sans-serif" font-size="{size}" font-weight="{weight}" '
            f'fill="{color}">{html.escape(s, quote=False)}</text>')


def sheet(r: Result, number: int) -> str:
    """The comparison sheet: photo | cut-out | each trace | today's template, at item size and at tile size."""
    m, gap = 24, 16
    cw, ch = ITEM_PX, ITEM_PX * CARD_H // CARD_W
    tw, th = TILE_PX, TILE_PX * CARD_H // CARD_W
    found = f"by {r.cutout_by}" + ("" if r.cutout is not None else ": no shoe found")
    cols: list[tuple[str, list[str], str]] = [("Photo", [], "photo"), ("Cut-out", [found], "cut")]
    for v in r.variants:
        sc = v.scores
        lines = [f"IoU {sc.iou:.3f} · ΔE {sc.delta_e:.1f}", f"{sc.colors} colours · {sc.paths} paths",
                 ("marks " + ("none in photo" if sc.marks is None else f"{sc.marks:.2f}")) + f" · score {sc.score:.3f}"]
        cols.append(((" ★ " if v.approach.name == r.best else "") + v.approach.name, lines, v.approach.name))
    if r.template_svg:
        cols.append(("Today's template", ["drawn from tags" if r.answer else "from the measured colour and height"], "template"))
    width = 2 * m + len(cols) * (cw + gap) - gap
    head_h = 70 + 20 * len(r.gate.reasons)
    y_item = m + head_h
    y_cap = y_item + ch + 22
    y_tile = y_cap + 3 * 19 + 26
    height = y_tile + th + m
    verdict = "passes the quality gate" if r.gate.ok else "fails the quality gate"
    o = r.oriented
    turned = f"turned {o.angle:+.1f}°" + (", mirrored (toe to the left)" if o.flipped else "") if o else "not traced"
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">',
           '<defs><pattern id="chk" width="16" height="16" patternUnits="userSpaceOnUse">'
           '<rect width="16" height="16" fill="#f4f1ea"/><rect width="8" height="8" fill="#d9d5cc"/>'
           '<rect x="8" y="8" width="8" height="8" fill="#d9d5cc"/></pattern></defs>',
           f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
           _text(m, m + 24, f"Shoe {number}: {verdict}", 24, "600", "#2e7d4f" if r.gate.ok else "#b3372f"),
           _text(m, m + 50, f"{turned} · {r.seconds:.1f} s · top row at item size ({ITEM_PX} px), "
                            f"bottom row at grid-tile size ({TILE_PX} px)", 15, color="#6d675d")]
    for i, why in enumerate(r.gate.reasons):
        out.append(_text(m, m + 72 + 20 * i, "• " + why, 15, color="#b3372f"))
    for i, (title, lines, key) in enumerate(cols):
        x = m + i * (cw + gap)
        for y, w, h in ((y_item, cw, ch), (y_tile, tw, th)):
            if key == "photo":
                out.append(_image_cell(r.photo, x, y, w, h, False, "JPEG"))
            elif key == "cut":
                if r.cutout is not None:
                    out.append(_image_cell(r.cutout, x, y, w, h, True, "PNG"))
            elif key == "template":
                if r.template_svg:
                    out.append(_place(_prefix_ids(r.template_svg, "i" if h == ch else "s"), x, y, w, h))
            else:
                v = next(v for v in r.variants if v.approach.name == key)
                out.append(_place(_prefix_ids(v.svg, "i" if h == ch else "s"), x, y, w, h))
        out.append(_text(x, y_cap, title, 16, "600"))
        for j, line in enumerate(lines):
            out.append(_text(x, y_cap + 20 + 19 * j, line, 14, color="#6d675d"))
    out.append("</svg>")
    return "".join(out)


def to_png(svg_path: Path, png_path: Path) -> bool:
    """The sheet as a picture, through a Chrome or Chromium found on this computer (as tools/make_figure_sheet.py)."""
    chrome = next((shutil.which(c) for c in ("google-chrome", "chromium", "chromium-browser", "chrome") if shutil.which(c)), None)
    if not chrome:
        return False
    svg = svg_path.read_text(encoding="utf-8")
    w, h = (int(v) for v in re.search(r'width="(\d+)" height="(\d+)"', svg).groups())
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "sheet.html"
        page.write_text(f'<html><body style="margin:0">{svg}</body></html>', encoding="utf-8")
        subprocess.run([chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                        f"--window-size={w},{h}", f"--screenshot={png_path.resolve()}", page.as_uri()],
                       check=True, capture_output=True, timeout=120)
    return png_path.exists()


# ------------------------------------------------------------------ the command

def summary(results: list[Result]) -> dict:
    """Mean scores per approach over the photos that pass the gate (all photos, when none does), and the pick."""
    usable = [r for r in results if r.gate.ok and r.variants] or [r for r in results if r.variants]
    table = {}
    for a in APPROACHES:
        vs = [v.scores for r in usable for v in r.variants if v.approach.name == a.name]
        if not vs:
            continue
        marks = [s.marks for s in vs if s.marks is not None]
        table[a.name] = {"label": a.label, "score": float(np.mean([s.score for s in vs])),
                         "iou": float(np.mean([s.iou for s in vs])), "delta_e": float(np.mean([s.delta_e for s in vs])),
                         "colors": float(np.mean([s.colors for s in vs])), "paths": float(np.mean([s.paths for s in vs])),
                         "marks": float(np.mean(marks)) if marks else None,
                         "best_on": sum(1 for r in usable if r.best == a.name)}
    pick = max(table, key=lambda k: table[k]["score"]) if table else None
    return {"photos": len(results), "passed": sum(1 for r in results if r.gate.ok), "scored_on": len(usable),
            "approaches": table, "recommended": pick}


def _index(results: list[Result], files: list[str], summ: dict, note: str) -> str:
    css = """
    :root{color-scheme:light dark;--bg:#fbfaf7;--fg:#22201c;--mut:#6d675d;--card:#fff;--line:#e3ded4}
    @media(prefers-color-scheme:dark){:root{--bg:#191816;--fg:#ece8df;--mut:#a39c8e;--card:#23211e;--line:#3a3732}}
    body{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,sans-serif}
    h1{font-size:22px;margin:4px 0 6px}h2{font-size:17px;margin:0 0 8px}p{margin:6px 0;max-width:80ch}
    .mut{color:var(--mut);font-size:13px}.ok{color:#2e7d4f}.bad{color:#b3372f}
    section{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;margin:16px 0;overflow-x:auto}
    table{border-collapse:collapse;font-size:14px}td,th{padding:3px 10px;border-bottom:1px solid var(--line);text-align:left}
    img.sheet{width:100%;min-width:900px;height:auto;display:block;border-radius:8px;background:#fff}
    """
    rec = summ["recommended"]
    p = [f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>Shoe tracing bench</title><style>{css}</style></head><body><h1>Shoe tracing bench</h1>",
         f"<p class='mut'>{html.escape(note)}</p>",
         "<section><h2>Summary</h2>",
         f"<p>{summ['photos']} photos; {summ['passed']} pass the quality gate. Mean scores over "
         f"{summ['scored_on']} photos{'' if summ['passed'] else ' (none passed, so all are shown)'}. "
         f"Recommended approach: <b>{html.escape(rec or 'none')}</b>.</p>",
         "<table><tr><th>Approach</th><th>Score</th><th>IoU</th><th>ΔE</th><th>Colours</th><th>Paths</th><th>Marks kept</th>"
         "<th>Best on</th></tr>"]
    for name, row in summ["approaches"].items():
        marks = "–" if row["marks"] is None else f"{row['marks']:.2f}"
        p.append(f"<tr><td>{'★ ' if name == rec else ''}{html.escape(name)} <span class='mut'>{html.escape(row['label'])}</span></td>"
                 f"<td>{row['score']:.3f}</td><td>{row['iou']:.3f}</td><td>{row['delta_e']:.1f}</td><td>{row['colors']:.1f}</td>"
                 f"<td>{row['paths']:.1f}</td><td>{marks}</td><td>{row['best_on']}</td></tr>")
    p.append("</table><p class='mut'>Score = 0.35 × silhouette IoU (0.8 → 0, 1 → 1) + 0.25 × colour (ΔE 25 → 0, 0 → 1) "
             "+ 0.2 × cleanliness (3 paths → 1, 28 → 0) + 0.2 × marks kept; without marks in the photo the other weights "
             "are scaled up.</p></section>")
    p.append("<section><h2>Quality gate</h2><table><tr><th>Shoe</th><th>Verdict</th><th>Why</th></tr>")
    for n, r in enumerate(results, 1):
        why = "<br>".join(html.escape(x) for x in r.gate.reasons) or "–"
        p.append(f"<tr><td>{n}</td><td class='{'ok' if r.gate.ok else 'bad'}'>{'traceable' if r.gate.ok else 'too poor'}</td>"
                 f"<td>{why}</td></tr>")
    p.append("</table><p class='mut'>Signals and limits: " + html.escape("; ".join(
        f"{k} {'≥' if way == 'below' else '≤'} {lim:g}" for k, (lim, way, _) in GATE.items())) + "</p></section>")
    for n, (r, f) in enumerate(zip(results, files, strict=True), 1):
        p.append(f"<section><h2>Shoe {n} <span class='{'ok' if r.gate.ok else 'bad'}'>"
                 f"{'traceable' if r.gate.ok else 'too poor to trace'}</span></h2>")
        p.append(f"<a href='{html.escape(f)}'><img class='sheet' src='{html.escape(f)}' alt='comparison sheet for shoe {n}'></a>")
        sig = " · ".join(f"{k} {v:.3g}" for k, v in r.gate.signals.items())
        p.append(f"<p class='mut'>{html.escape(sig)}</p></section>")
    p.append("</body></html>")
    return "".join(p)


def _result_json(r: Result) -> dict:
    o = r.oriented
    return {"gate": {"ok": r.gate.ok, "reasons": r.gate.reasons, "signals": r.gate.signals},
            "cutout_by": r.cutout_by, "seconds": round(r.seconds, 2), "best": r.best,
            "turned": None if o is None else {"angle": round(o.angle, 2), "flipped": o.flipped},
            "variants": {v.approach.name: {"iou": v.scores.iou, "delta_e": v.scores.delta_e, "colors": v.scores.colors,
                                           "paths": v.scores.paths, "marks": v.scores.marks, "score": v.scores.score,
                                           "palette": [rg.color for rg in v.trace.regions]} for v in r.variants}}


def photos_in(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in PHOTO_TYPES and p.is_file())


def run(photos: Path, out: Path, cutout: str = "auto", model: str = "isnet-general-use",
        models_dir: Path = ROOT / "models", png: bool = True, quiet: bool = False) -> Path:
    try:   # phones' HEIC photos, when pillow-heif is installed (the app has it; the bench does not need it)
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except ImportError:
        pass
    paths = photos_in(photos)
    if not paths:
        raise SystemExit(f"no photos in {photos}")
    out.mkdir(parents=True, exist_ok=True)
    results, files = [], []
    for n, path in enumerate(paths, 1):
        side = path.with_suffix(".json")
        answer = json.loads(side.read_text(encoding="utf-8")) if side.exists() else None
        r = trace_photo(C.load_photo(path), cutout, model, models_dir, answer, uid=f"s{n}")
        results.append(r)
        svg_path = out / f"shoe-{n:02d}.sheet.svg"
        svg_path.write_text(sheet(r, n), encoding="utf-8")
        png_path = svg_path.with_suffix(".png")
        made = png and to_png(svg_path, png_path)
        files.append(png_path.name if made else svg_path.name)
        if not quiet:
            print(f"shoe {n:2d}: {'traceable ' if r.gate.ok else 'too poor  '} best {r.best or '-':20s} "
                  f"{r.seconds:5.1f}s  " + ("; ".join(r.gate.reasons) or ""))
    summ = summary(results)
    (out / "results.json").write_text(json.dumps({"summary": summ, "shoes": [_result_json(r) for r in results]},
                                                 indent=2, default=float), encoding="utf-8")
    note = (f"Photos from {photos.name}/, listed by number in name order. Cut-outs by "
            f"{', '.join(sorted({r.cutout_by for r in results}))}.")
    (out / "index.html").write_text(_index(results, files, summ, note), encoding="utf-8")
    if not quiet:
        print(f"recommended approach: {summ['recommended']}"
              + ("" if summ["passed"] else " (no photo passed the gate: scored on all of them)"))
    return out / "index.html"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--photos", type=Path, default=ROOT / "private" / "shoes")
    ap.add_argument("--out", type=Path, default=ROOT / "out" / "trace_shoes")
    ap.add_argument("--cutout", choices=("auto", "model", "grabcut"), default="auto",
                    help="auto: the app's model when its file is in --models-dir, else GrabCut")
    ap.add_argument("--model", default="isnet-general-use", choices=list(C.MODELS))
    ap.add_argument("--models-dir", type=Path, default=ROOT / "models")
    ap.add_argument("--no-png", action="store_true", help="write the sheets as SVG only")
    a = ap.parse_args()
    print("report:", run(a.photos, a.out, a.cutout, a.model, a.models_dir, png=not a.no_png))


if __name__ == "__main__":
    main()
