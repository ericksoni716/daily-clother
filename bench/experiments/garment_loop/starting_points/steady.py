"""Run-to-run steadiness of the described tile, per configuration: for each pair of runs on the same photo, the
mean colour difference (CIE76) between the two woven repeats after the best cyclic alignment, and the
difference in their colour make-up (half the L1 distance between coarse Lab histograms, 0 = same mixture)."""
import itertools
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent / "r2"))
import render as R  # noqa: E402
from closet.patterns import described  # noqa: E402

CONFIGS = {
    "round2 (widths as said)": dict(widths=False),
    "cap by gain": dict(widths=True),
    "cap by gain + hues 0.5": dict(widths=True, hues=0.5),
    "cap by gain + hues 1.0": dict(widths=True, hues=1.0),
    "round2 at strength 0.8": dict(widths=False, strength=0.8),
    "cap by gain, strength 0.8": dict(widths=True, strength=0.8),
}


def prepared(raw, cut, cfg):
    desc = described.read(raw)
    if not cfg.get("widths"):
        return desc, None
    got = described.photo_widths(desc, cut, hues=cfg.get("hues", 0.0))
    return (got[0], got[1]) if got else (desc, None)


def cie(img):
    lab = cv2.cvtColor(cv2.resize(img, (90, 90), interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2LAB).astype(np.float32)
    return lab * np.array([100 / 255, 1, 1], np.float32) - np.array([0, 128, 128], np.float32)


def apart(a, b):
    best = min(float(np.linalg.norm(a - np.roll(b, (s, s), (0, 1)), axis=2).mean()) for s in range(90))
    # the colour make-up, whatever the arrangement: per channel, the mean gap between the two sorted pixel lists
    # (an earth mover's distance), added over L, a and b
    make = sum(float(np.abs(np.sort(a[..., c].ravel()) - np.sort(b[..., c].ravel())).mean()) for c in range(3))
    return best, make


if __name__ == "__main__":
    stems = R.STEMS + ["demo_flannel", "demo_madras"]
    out = {}
    for name, cfg in CONFIGS.items():
        rows = {}
        for stem in stems:
            cut = Image.open(R.CUTS[stem])
            tiles = {}
            for run in ("1", "2", "3"):
                try:
                    raw = R.answer("f2", stem, "cut", run)["plaid"]
                except FileNotFoundError:
                    continue
                desc, info = prepared(raw, cut, cfg)
                tiles[run] = cie(described.weave(described.softened(desc, cfg.get("strength", 1.0))))
            pairs = [apart(tiles[a], tiles[b]) for a, b in itertools.combinations(sorted(tiles), 2)]
            rows[stem] = (round(float(np.mean([p[0] for p in pairs])), 1), round(float(np.mean([p[1] for p in pairs])), 1), len(tiles))
        out[name] = rows
        de = np.mean([v[0] for v in rows.values()])
        mk = np.mean([v[1] for v in rows.values()])
        print(f"{name:28s} aligned dE {de:5.1f}  make-up {mk:5.1f}   " + "  ".join(f"{s[2:]}:{v[0]}/{v[1]}" for s, v in rows.items()), flush=True)
    (Path(__file__).parent / "steady.json").write_text(json.dumps(out, indent=1))
