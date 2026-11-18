"""Result sheets for the owner (PLAN.md "What to hand back"): per garment, the photo and every arm's drawing with its
judged scores, under bench/private/garment_loop/results/<half>/ (private: they hold the photos).

  python sheets.py [--half tuning]"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyse as A  # noqa: E402
import harness as H  # noqa: E402
import judge as J  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

SHOWN = [("A", "A: the app today"), ("B", "B: small model, one shot"), ("C-sonnet", "C: Sonnet, one shot"),
         ("C-opus", "C: Opus, one shot"), ("D3", "D: loop, 3 corrections"), ("E", "E: best of 3 loops"),
         ("D-small3", "D-small: small model corrects")]


def sheet(gid: str, R: dict, out: Path, height: int = 360) -> Path:
    font, small = J._font(26), J._font(19)

    def fit(im):
        return im.resize((max(1, round(im.width * height / im.height)), height), Image.LANCZOS)
    photo = fit(H.photo(gid).convert("RGBA"))
    tiles = []
    for arm, title in SHOWN:
        name = J.drawing_of(gid, arm)
        if name is None:
            continue
        s = R.get((gid, arm))
        line = (f"{sum(s[k] for k in A.LINES):.1f}/15  g{s['ground']:.1f} c{s['colours']:.1f} s{s['scale']:.1f} "
                f"st{s['structure']:.1f} p{s['pick']:.1f}") if s else "not judged"
        tiles.append((title, line, (s or {}).get("fault") or "", fit(J._carded(J._png(gid, name)))))
    cols, gap, head = 4, 20, 92
    tw = max(t[3].width for t in tiles)
    rows = 1 + (len(tiles) + cols - 1) // cols
    W = cols * (tw + gap) + gap
    img = Image.new("RGB", (W, rows * (height + head + gap) + gap), (255, 255, 255))
    d = ImageDraw.Draw(img)
    s_ = A.sheet(gid) or {}
    d.text((gap, gap), f"{gid}: {s_.get('garment', '')}, {s_.get('kind', '')}", fill=(20, 20, 20), font=font)
    d.text((gap, gap + 34), f"sheet: ground {s_.get('ground', {}).get('name', '')}, count {s_.get('count')}", fill=(80, 80, 80), font=small)
    img.paste(photo, (gap, gap + head - 20), photo)
    for i, (title, line, fault, t) in enumerate(tiles):
        x = gap + (i % cols) * (tw + gap)
        y = gap + (1 + i // cols) * (height + head + gap)
        d.text((x, y), title, fill=(20, 20, 20), font=small)
        d.text((x, y + 24), line, fill=(60, 60, 60), font=small)
        d.text((x, y + 48), fault[:46], fill=(150, 40, 40), font=small)
        img.paste(t, (x, y + head - 18), t)
    path = out / f"{gid}.jpg"
    img.save(path, quality=88)
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--half", default="tuning")
    half = ap.parse_args().half
    out = H.PRIV / "results" / half
    out.mkdir(parents=True, exist_ok=True)
    R = A.rubric(half)["scores"]
    for gid in json.loads((H.PRIV / "split.json").read_text())[half]:
        print(sheet(gid, R, out))
