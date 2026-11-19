"""Arm F through the app's own code, after its adoption: each garment's stored Sonnet answer (F run 1, a whole
description with its surface) taken as the app takes a new description (`tagging.fitted`, `tagjobs.color_hex`,
`patjobs.method`), its pattern kept as the pattern job keeps it (`patterns.surface.kept_for_item`, or the app's own
measuring for a graphic, then `palette.keep`), and drawn as the closet tile and on the As worn figure. No calls to
Claude: the stored answers and landmarks are reused. Sheets under bench/private/garment_loop/app_path/ (private:
they hold the photos), one row per garment: the photo, the drawing the judges scored, the app's tile, the figure.

  python app_path.py [--only g01,g02]"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness as H
import judge as J
from closet import palette, patjobs, tagjobs
from closet.drawing import item as I
from closet.drawing import stored
from closet.drawing.figure import Piece, figure
from closet.tagger import surfaceform, tagging
from PIL import Image, ImageDraw

OUT = H.PRIV / "app_path"
OUTER = ("jacket", "coat", "blazer", "vest")


def kept_for(gid: str, tags, answer: dict) -> tuple[str | None, dict | None, str | None]:
    """(how the pattern job takes it, what it keeps, why it failed) as the app's pattern job would, with the stored
    landmarks standing in for the landmarks call."""
    row = {"category": tags.category, "pattern": tags.pattern, "tag_answer": json.dumps(answer)}
    how = patjobs.method(row)
    if how is None:
        return None, None, None
    cut = H.cut_of(gid)
    ruler = H.load_json(H.wdir(gid) / "ruler.json") or {}
    marks = ruler.get("points") if ruler.get("how") == "landmarks" else None
    surface = answer.get("surface") if how == patjobs.SURFACE else None
    if tags.category not in patjobs.TOPS or how == patjobs.GRAPHIC or (surface is not None
                                                                      and not surfaceform.needs_ruler(surface)):
        marks = None
    try:
        if how == patjobs.SURFACE:
            from closet.patterns.surface import kept_for_item
            raw = kept_for_item(cut, surface, marks, tags.category)
        else:
            from closet.patterns.measure import measure
            raw = measure(cut, how, [tags.color, *tags.secondary_colors], marks)
        return how, palette.keep(raw, tags.pattern), None if raw else "nothing kept"
    except Exception as e:  # noqa: BLE001 -- as the app: kept in its colour, saying why
        return how, None, type(e).__name__


def draw_one(gid: str) -> dict:
    rec = H.load_json(H.wdir(gid) / "calls" / "F_run1.json")
    tags = tagging.fitted(rec["answer"])
    answer = tags.model_dump(mode="json")
    hex_ = tagjobs.color_hex(tags)
    how, kept, failed = kept_for(gid, tags, answer)
    if kept and kept.get("colors") and tags.pattern != "solid":   # `palette.settle`: the colour from what was kept
        main = palette.main_colour(palette.named(kept["colors"], [tags.color, *tags.secondary_colors]), tags.color)
        hex_ = main["hex"] if main else hex_
    fill = stored.fill_from(kept, hex_) if kept else None
    graphic = stored.graphic_from(kept) if kept else None
    flat = I.drawing_from_answer(answer, hex_, uid=f"t{gid}", fill=fill, graphic=graphic).svg
    place = "bottom" if tags.category in ("jeans", "trousers", "shorts") else \
        "outer" if tags.category in OUTER else "base"
    piece = Piece(tags.category, answer, hex_, tags.color, tags.pattern, None, fill=fill, graphic=graphic)
    worn = figure({place: piece}, uid=f"w{gid}")
    OUT.mkdir(parents=True, exist_ok=True)
    pairs = []
    for name, svg in (("flat", flat), ("worn", worn)):
        s = OUT / f"{gid}_{name}.svg"
        s.write_text(svg)
        pairs.append((s, OUT / f"{gid}_{name}.png"))
    H.rasterise(pairs)
    kind = surfaceform.kind_of(answer.get("surface"))
    return {"gid": gid, "category": tags.category, "pattern": tags.pattern, "kind": kind, "how": how,
            "kept": (kept or {}).get("how") or (kept or {}).get("kind"), "scale": (kept or {}).get("scale"),
            "failed": failed, "colour": hex_}


def sheet(rows: list[dict], out: Path) -> None:
    font, small = J._font(20), J._font(16)
    W, H_, PAD = 300, 300, 12
    heads = ["photo", "judged (F run 1)", "the app: tile", "the app: As worn"]
    canvas = Image.new("RGB", (PAD + 4 * (W + PAD), 40 + len(rows) * (H_ + 50)), "white")
    d = ImageDraw.Draw(canvas)
    for i, h in enumerate(heads):
        d.text((PAD + i * (W + PAD), 10), h, fill="black", font=font)
    for r, row in enumerate(rows):
        y = 40 + r * (H_ + 50)
        gid = row["gid"]
        ims = [H.cut_of(gid), Image.open(H.wdir(gid) / "draw" / "F_run1.png") if (H.wdir(gid) / "draw" / "F_run1.png").exists()
               else Image.new("RGBA", (10, 10)), Image.open(OUT / f"{gid}_flat.png"), Image.open(OUT / f"{gid}_worn.png")]
        for i, im in enumerate(ims):
            im = im.convert("RGBA")
            bb = im.getchannel("A").getbbox()
            if bb:
                im = im.crop(bb)
            k = min(W / im.width, H_ / im.height)
            im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
            canvas.paste(im, (PAD + i * (W + PAD) + (W - im.width) // 2, y + (H_ - im.height) // 2), im)
        note = (f"{gid}  {row['category']}  pattern {row['pattern']}  surface {row['kind']}  job {row['how']}  "
                f"kept {row['kept']}  scale {row['scale']}" + (f"  FAILED {row['failed']}" if row["failed"] else ""))
        d.text((PAD, y + H_ + 8), note, fill="black", font=small)
    canvas.save(out, quality=90)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    split = json.loads((H.PRIV / "split.json").read_text())
    gids = [g for half in ("tuning", "held-out") for g in split[half]]
    if a.only:
        gids = [g for g in gids if g in a.only.split(",")]
    rows = [draw_one(g) for g in gids]
    (OUT / "rows.json").write_text(json.dumps(rows, indent=1))
    for k in range(0, len(rows), 6):
        sheet(rows[k:k + 6], OUT / f"sheet_{k // 6 + 1:02d}.jpg")
    print(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
