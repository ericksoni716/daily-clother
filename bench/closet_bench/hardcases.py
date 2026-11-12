"""Run the illustration hard cases and write a side-by-side HTML report.

    python -m closet_bench.hardcases [--model isnet-general-use] [--only ID ...]
"""
from __future__ import annotations

import argparse
import html
import json
import time
from pathlib import Path

from PIL import Image

from . import cutout as C
from . import fills
from .illustrate import STYLES, Fill, Spec, render

ROOT = Path(__file__).resolve().parent.parent
STYLE_NAMES = {"flat": "A · Flat", "line": "B · Outline", "soft": "C · Soft shaded", "traced": "D · Traced from photo"}


def build_spec(case: dict, cut: Image.Image) -> tuple[Spec, dict]:
    info: dict = {}
    palette = fills.dominant_colors(cut)
    info["palette"] = palette
    base = fills.snap_to_named(palette[0][0], case.get("color_name"))
    info["base"] = base
    fill = Fill("solid", base)
    kind = case.get("fill", "solid")
    if kind == "swatch":
        try:
            sw = fills.pick_swatch(cut, avoid_center=case.get("params", {}).get("front") in ("buttons", "zip"),
                                   organic=case.get("pattern") in ("floral", "camo", "texture"))
            fill = Fill("swatch", base, swatch=sw)
            info["swatch"] = {"method": sw.method, "period": sw.period, "box": sw.box, "width_frac": round(sw.width_frac, 3)}
            info["swatch_img"] = sw.image
        except ValueError as e:
            info["swatch_error"] = str(e)
    elif kind == "stripes":
        st = fills.measure_stripes(cut, case.get("orientation", "horizontal"), case.get("stripe_colors", 2))
        fill = Fill("stripes", st.bands[0][0], stripes=st)
        info["stripes"] = [(c, round(w, 4)) for c, w in st.bands]
    graphic = None
    if case.get("graphic"):
        graphic = fills.extract_graphic(cut)
        info["graphic"] = None if graphic is None else {"box": graphic.box, "width": round(graphic.width, 3)}
        if graphic is not None:
            info["graphic_img"] = graphic.image
    return Spec(case["template"], case.get("params", {}), fill, graphic, case.get("sole_color")), info


def run(model: str, only: list[str] | None, out: Path, models_dir: Path) -> Path:
    cfg = json.loads((ROOT / "hardcases" / "cases.json").read_text())
    notes = {}
    notes_path = ROOT / "hardcases" / "notes.json"
    if notes_path.exists():
        notes = json.loads(notes_path.read_text())
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for case in cfg["cases"]:
        if only and case["id"] not in only:
            continue
        photo = C.load_photo(ROOT / "hardcases" / "photos" / case["photo"])
        t0 = time.time()
        mask = C.predict_mask(photo, model, models_dir)
        cut, _ = C.make_cutout(photo, mask)
        t_cut = time.time() - t0
        size = C.save_cutout_webp(cut, out / f"{case['id']}.webp")
        t0 = time.time()
        spec, info = build_spec(case, cut)
        svgs = {}
        for st in STYLES:
            svg = render(spec, st, cutout=cut, uid=f"{case['id'].replace('-', '')}{st}")
            (out / f"{case['id']}.{st}.svg").write_text(svg)
            svgs[st] = svg
        t_ill = time.time() - t0
        print(f"{case['id']:16s} cutout {t_cut:.2f}s {size // 1024} KB  illustrate {t_ill:.2f}s  "
              f"svg {len(svgs['flat']) // 1024}-{len(svgs['soft']) // 1024} KB  "
              f"{ {k: v for k, v in info.items() if not k.endswith('_img')} }")
        rows.append((case, photo, cut, svgs, info, dict(t_cut=t_cut, t_ill=t_ill, size=size)))
    report = out / "report.html"
    report.write_text(_report(rows, cfg.get("_note", ""), notes, model))
    return report


def _report(rows, note: str, notes: dict, model: str) -> str:
    css = """
    :root{color-scheme:light dark;--bg:#fbfaf7;--fg:#22201c;--mut:#6d675d;--card:#fff;--line:#e3ded4}
    @media(prefers-color-scheme:dark){:root{--bg:#191816;--fg:#ece8df;--mut:#a39c8e;--card:#23211e;--line:#3a3732}}
    body{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,sans-serif}
    h1{font-size:22px;margin:4px 0 6px}h2{font-size:17px;margin:0 0 8px}
    p{margin:6px 0;max-width:75ch}.mut{color:var(--mut);font-size:13px}
    section{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;margin:16px 0}
    .grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:10px}
    @media(max-width:900px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
    figure{margin:0}figcaption{font-size:12px;color:var(--mut);margin-top:4px}
    figure img,figure svg{width:100%;height:auto;display:block;border-radius:10px}
    .cut{background:repeating-conic-gradient(#d9d5cc 0 25%,#f4f1ea 0 50%) 0 0/16px 16px}
    .extras{display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap;margin-top:10px}
    .extras img{height:90px;width:auto;border-radius:6px;border:1px solid var(--line)}
    .verdict{font-weight:600}.ok{color:#2e7d4f}.meh{color:#a8730c}.bad{color:#b3372f}
    ul{margin:6px 0 0 18px;padding:0}
    """
    parts = [f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
             f"<title>Closet hard cases</title><style>{css}</style></head><body>",
             "<h1>Illustration hard cases</h1>",
             f"<p class='mut'>{html.escape(note)} Background removal model: {html.escape(model)}.</p>"]
    if notes.get("_summary"):
        parts.append("<section><h2>Summary</h2>" + notes["_summary"] + "</section>")
    for case, photo, cut, svgs, info, tm in rows:
        n = notes.get(case["id"], {})
        verdict = n.get("verdict", "")
        cls = {"works": "ok", "partly": "meh", "fails": "bad"}.get(verdict.split(":")[0].strip().lower(), "")
        parts.append(f"<section><h2>{html.escape(case['label'])}</h2>")
        if verdict:
            parts.append(f"<p class='verdict {cls}'>{html.escape(verdict)}</p>")
        parts.append("<div class='grid'>")
        parts.append(f"<figure><img src='{fills.data_uri(photo, 420, 'JPEG', 78)}'><figcaption>Photo</figcaption></figure>")
        parts.append(f"<figure><img class='cut' src='{fills.data_uri(cut, 420, 'WEBP', 80)}'>"
                     f"<figcaption>Cutout · {tm['size'] // 1024} KB at full size · {tm['t_cut']:.1f}s</figcaption></figure>")
        for st in STYLES:
            parts.append(f"<figure>{svgs[st]}<figcaption>{STYLE_NAMES[st]}</figcaption></figure>")
        parts.append("</div>")
        extras = []
        if "swatch_img" in info:
            extras.append(f"<figure><img src='{fills.data_uri(info['swatch_img'], 180, 'JPEG')}'>"
                          f"<figcaption>Fabric tile ({info['swatch']['method']})</figcaption></figure>")
        if "graphic_img" in info:
            extras.append(f"<figure><img class='cut' src='{fills.data_uri(info['graphic_img'], 240, 'PNG')}'>"
                          "<figcaption>Print lifted from the photo</figcaption></figure>")
        if "palette" in info:
            sw = "".join(f"<span title='{c} {s:.0%}' style='display:inline-block;width:{max(10, int(s * 160))}px;height:22px;background:{c}'></span>"
                         for c, s in info["palette"])
            extras.append(f"<figure><div style='border-radius:6px;overflow:hidden;border:1px solid var(--line);line-height:0'>{sw}</div>"
                          "<figcaption>Measured colours</figcaption></figure>")
        parts.append("<div class='extras'>" + "".join(extras) + "</div>")
        if n.get("points"):
            parts.append("<ul>" + "".join(f"<li>{html.escape(pt)}</li>" for pt in n["points"]) + "</ul>")
        parts.append(f"<p class='mut'>Attributes used: {html.escape(json.dumps(case.get('params', {})))} · fill: {html.escape(case.get('fill', 'solid'))}</p>")
        parts.append("</section>")
    credits = ROOT / "hardcases" / "ATTRIBUTION.md"
    if credits.exists():
        parts.append("<section><h2>Photo credits</h2><p class='mut'>" + html.escape(credits.read_text()).replace("\n", "<br>") + "</p></section>")
    parts.append("</body></html>")
    return "".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="isnet-general-use", choices=list(C.MODELS))
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--out", type=Path, default=ROOT / "out" / "hardcases")
    ap.add_argument("--models-dir", type=Path, default=ROOT / "models")
    a = ap.parse_args()
    print("report:", run(a.model, a.only, a.out, a.models_dir))


if __name__ == "__main__":
    main()
