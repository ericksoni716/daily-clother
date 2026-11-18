"""Blind judging packs for the garment loop test (DESIGN.md section 7), and reading the judges' answers back.

  python judge.py packs [--half tuning]      the rubric (two passes), pairwise and steadiness images
  python judge.py collect [--half tuning]    the judges' answers joined back to arms (judge/scores.json)

Every image goes under bench/private/garment_loop/judge/<half>/ with a random name; which arm made it is only in
key.json beside them, which no judge is shown. A drawing that two arms share (the loop kept its start, say) is
judged once and its scores given to both."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness as H  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

JUDGE = H.PRIV / "judge"
RUBRIC_ARMS = ["A", "B", "C-sonnet", "C-opus", "D1", "D2", "D3", "E", "D-small3"]
PAIR_ARMS = ["A", "B", "C-sonnet", "C-opus", "D3", "E", "D-small3"]
STEADY_ARMS = ["B", "C-sonnet", "C-opus", "D3", "D-small3"]


def drawing_of(gid: str, arm: str, run: int = 1) -> str | None:
    """The name of the drawing an arm shows for a garment (run or chain `run`), or None when it was not made.
    D1..D3: what chain `run` of the loop keeps after one to three corrections; E: the best of the three chains."""
    w = H.wdir(gid)
    if arm in ("A",):
        return "A" if (w / "draw" / "A.png").exists() else None
    if arm in ("B", "C-sonnet", "C-opus"):
        name = f"{arm}_run{run}"
        return name if (w / "draw" / f"{name}.png").exists() else None
    for tag in ("D-small", "D"):
        if arm.startswith(tag) and arm[len(tag):].isdigit():
            chain = H.load_json(w / f"{tag}_chain{run}.json")
            if chain is None:
                return None
            k = int(arm[len(tag):])
            return chain["rounds"][k]["kept_after"]
    if arm == "E":
        best = None
        drawings = H.load_json(w / "drawings.json") or {}
        for c in (1, 2, 3):
            chain = H.load_json(w / f"D_chain{c}.json")
            if chain is None:
                return None
            name = chain["kept"]
            s = drawings[name]["score"]["score"]
            if best is None or s > best[0]:
                best = (s, name)
        return best[1]
    return None


def _png(gid: str, name: str) -> Image.Image:
    return Image.open(H.wdir(gid) / "draw" / f"{name}.png").convert("RGBA")


def _token(*parts) -> str:
    return hashlib.sha256("/".join(map(str, parts)).encode()).hexdigest()[:10]


def _font(size: int):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _carded(img: Image.Image) -> Image.Image:
    card = Image.new("RGBA", img.size, H.CARD + (255,))
    card.alpha_composite(img)
    return card


def packs(half: str) -> None:
    ids = json.loads((H.PRIV / "split.json").read_text())[half]
    out = JUDGE / half
    salt = random.Random(f"{half}-salt").random()
    key = {"rubric": {}, "pairwise": {}, "steady": {}}
    # the rubric: one image per distinct drawing, each pass its own names and order
    distinct = {}
    for gid in ids:
        for arm in RUBRIC_ARMS:
            name = drawing_of(gid, arm)
            if name is not None:
                distinct.setdefault((gid, name), []).append(arm)
    for p in (1, 2):
        folder = out / f"rubric{p}"
        folder.mkdir(parents=True, exist_ok=True)
        order = sorted(distinct, key=lambda k: _token(salt, p, *k))
        listing = []
        for gid, name in order:
            tok = _token(salt, "r", p, gid, name)
            H.judge_image(gid, _png(gid, name)).save(folder / f"{tok}.jpg", quality=90)
            key["rubric"][tok] = {"pass": p, "gid": gid, "drawing": name, "arms": distinct[(gid, name)]}
            listing.append(f"{tok}.jpg")
        (folder / "order.txt").write_text("\n".join(listing))
    # pairwise: the photo and every arm's drawing under random letters
    folder = out / "pairwise"
    folder.mkdir(parents=True, exist_ok=True)
    for gid in ids:
        shown = {}
        for arm in PAIR_ARMS:
            name = drawing_of(gid, arm)
            if name is not None:
                shown.setdefault(name, []).append(arm)
        names = sorted(shown, key=lambda n: _token(salt, "p", gid, n))
        letters = "ABCDEFGH"[:len(names)]
        tok = _token(salt, "pw", gid)
        _sheet(gid, [(letters[i], _png(gid, n)) for i, n in enumerate(names)]).save(folder / f"{tok}.jpg", quality=90)
        key["pairwise"][tok] = {"gid": gid, "letters": {letters[i]: {"drawing": n, "arms": shown[n]} for i, n in enumerate(names)}}
    # steadiness: the photo and an arm's three runs
    folder = out / "steady"
    folder.mkdir(parents=True, exist_ok=True)
    for gid in ids:
        for arm in STEADY_ARMS:
            names = [drawing_of(gid, arm, r) for r in (1, 2, 3)]
            if None in names:
                continue
            order = sorted(range(3), key=lambda i: _token(salt, "s", gid, arm, i))
            tok = _token(salt, "st", gid, arm)
            _sheet(gid, [("123"[j], _png(gid, names[i])) for j, i in enumerate(order)]).save(folder / f"{tok}.jpg", quality=90)
            key["steady"][tok] = {"gid": gid, "arm": arm, "drawings": {"123"[j]: names[i] for j, i in enumerate(order)}}
    H.save_json(out / "key.json", key)
    print(half, {k: len(v) for k, v in key.items()})


def _sheet(gid: str, labelled: list[tuple[str, Image.Image]], height: int = 520) -> Image.Image:
    """The photo, then drawings each under a big letter or number, in rows of four."""
    def fit(im):
        return im.resize((max(1, round(im.width * height / im.height)), height), Image.LANCZOS)
    photo = fit(H.photo(gid).convert("RGBA"))
    tiles = [(lab, fit(_carded(im))) for lab, im in labelled]
    cols = min(4, len(tiles))
    tw = max(t.width for _, t in tiles)
    rows = (len(tiles) + cols - 1) // cols
    gap, head = 24, 64
    W = max(photo.width + 2 * gap, cols * (tw + gap) + gap)
    out = Image.new("RGB", (W, gap + height + head + rows * (height + head + gap)), (255, 255, 255))
    d = ImageDraw.Draw(out)
    font = _font(44)
    d.text((gap, gap // 2), "Photo", fill=(30, 30, 30), font=font)
    out.paste(photo, (gap, head), photo)
    for i, (lab, t) in enumerate(tiles):
        x = gap + (i % cols) * (tw + gap)
        y = head + height + gap + (i // cols) * (height + head + gap)
        d.text((x, y), lab, fill=(30, 30, 30), font=font)
        out.paste(t, (x, y + head - 8), t)
    return out


def collect(half: str) -> None:
    """Join the judges' answer files (rubric<p>/answers.json, pairwise/answers.json, steady/answers.json) to arms."""
    out = JUDGE / half
    key = H.load_json(out / "key.json")
    scores = {"rubric": [], "pairwise": [], "steady": []}
    for p in (1, 2, 3):
        ans = H.load_json(out / f"rubric{p}" / "answers.json") or {}
        for tok, a in ans.items():
            k = key["rubric"].get(tok.removesuffix(".jpg"))
            if k is None:
                k = (H.load_json(out / "rejudge" / "key.json") or {}).get(tok.removesuffix(".jpg"))
            if k is not None:
                scores["rubric"].append({**k, "pass": k.get("pass", p), "scores": a})
    for tok, a in (H.load_json(out / "pairwise" / "answers.json") or {}).items():
        k = key["pairwise"].get(tok.removesuffix(".jpg"))
        if k is not None:
            scores["pairwise"].append({**k, "answer": a})
    for tok, a in (H.load_json(out / "steady" / "answers.json") or {}).items():
        k = key["steady"].get(tok.removesuffix(".jpg"))
        if k is not None:
            scores["steady"].append({**k, "answer": a})
    H.save_json(out / "scores.json", scores)
    print(half, {k: len(v) for k, v in scores.items()})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("step")
    ap.add_argument("--half", default="tuning")
    args = ap.parse_args()
    {"packs": packs, "collect": collect}[args.step](args.half)
