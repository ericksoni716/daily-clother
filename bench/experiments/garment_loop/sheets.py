"""Result sheets for the owner (PLAN.md "What to hand back"): per garment, the photo and every arm's drawing with its
judged scores, under bench/private/garment_loop/results/<half>/ (private: they hold the photos).

  python sheets.py [--half tuning]"""
from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyse as A  # noqa: E402
import harness as H  # noqa: E402
import judge as J  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

SHOWN = [("A", "A  the app today"), ("B", "B  Haiku, one description"), ("C-sonnet", "C1  Sonnet, one description"),
         ("C-opus", "C2  Opus, one description"), ("D3", "D  the loop, 3 corrections"),
         ("E", "E  best of 3 loops"), ("D-small3", "D-small  Haiku corrects")]
COLS, COL_W, TILE_H, GAP = 3, 430, 330, 24


def _notes(gid: str, arm: str, name: str) -> str:
    """What the owner needs to read a drawing right: a loop that kept its start, how E was picked."""
    if arm in ("D3", "D-small3") and name.startswith("B_run"):
        return "kept its start: no correction scored better"
    if arm == "E":
        return "picked by the loop's own score"
    return ""


def sheet(gid: str, R: dict, out: Path) -> Path:
    big, font = J._font(28), J._font(18)

    def fit(im, h=TILE_H, w=COL_W):
        k = min(h / im.height, w / im.width)
        return im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
    s_ = A.sheet(gid) or {}
    placed = "; ".join(p.get("what", "") for p in s_.get("placed") or [])
    title = f"{gid}: {s_.get('garment', '')}"
    sub = (f"the reference sheet: {s_.get('kind', '')} cloth, ground {s_.get('ground', {}).get('name', '')}"
           + (f", {s_.get('count')} repeats across" if s_.get("count") else "") + (f"; placed: {placed}" if placed else ""))
    tiles = []
    for arm, label in SHOWN:
        name = J.drawing_of(gid, arm)
        if name is None:
            continue
        s = R.get((gid, arm))
        score = (f"{sum(s[k] for k in A.LINES):.1f} of 15 (ground {s['ground']:.1f}, colours {s['colours']:.1f}, "
                 f"scale {s['scale']:.1f}, structure {s['structure']:.1f}, pick {s['pick']:.1f})") if s else "not judged"
        text = [label] + textwrap.wrap(score, 44) + textwrap.wrap("fault: " + ((s or {}).get("fault") or "none"), 44)
        note = _notes(gid, arm, name)
        if note:
            text += textwrap.wrap("(" + note + ")", 44)
        tiles.append((text, fit(J._carded(J._png(gid, name)))))
    head_h = 26 * max(len(t) for t, _ in tiles) + 8
    rows = (len(tiles) + COLS - 1) // COLS
    W = COLS * (COL_W + GAP) + GAP
    top = 110
    photo = fit(H.photo(gid).convert("RGBA"), h=TILE_H + 120, w=W - 2 * GAP)
    H_ = top + photo.height + GAP + rows * (head_h + TILE_H + GAP) + 60
    img = Image.new("RGB", (W, H_), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((GAP, 14), title, fill=(20, 20, 20), font=big)
    for i, line in enumerate(textwrap.wrap(sub, 120)[:2]):
        d.text((GAP, 54 + 24 * i), line, fill=(80, 80, 80), font=font)
    img.paste(photo, (GAP, top), photo)
    y0 = top + photo.height + GAP
    for i, (text, t) in enumerate(tiles):
        x = GAP + (i % COLS) * (COL_W + GAP)
        y = y0 + (i // COLS) * (head_h + TILE_H + GAP)
        for j, line in enumerate(text):
            colour = (20, 20, 20) if j == 0 else (150, 40, 40) if line.startswith("fault") or (j > 1 and not line[0].isdigit() and "fault" in " ".join(text[1:j + 1])) and not line.startswith("(") else (90, 90, 90)
            d.text((x, y + 26 * j), line, fill=colour, font=font)
        img.paste(t, (x, y + head_h), t)
    d.text((GAP, H_ - 40), "Scores: two blind judges averaged (a third where they differed by 2 or more); the fault line is "
           "the first judge's.", fill=(90, 90, 90), font=font)
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
