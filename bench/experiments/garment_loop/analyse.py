"""Every measure of DESIGN.md section 7, per arm, for one half. Reads what the runs, the reference sheets and the
judges left under bench/private/garment_loop/; writes results/<half>.json there and prints the tables (counts and
rates only, nothing that identifies a private photo).

  python analyse.py [--half tuning]"""
from __future__ import annotations

import argparse
import itertools
import json
import statistics
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness as H  # noqa: E402
import judge as J  # noqa: E402
from closet.patterns import described  # noqa: E402
from PIL import Image  # noqa: E402

LINES = ("ground", "colours", "scale", "structure", "pick")
ARMS = ["A", "B", "C-sonnet", "C-opus", "D1", "D2", "D3", "E", "D-small3"]


def sheet(gid: str) -> dict | None:
    return H.load_json(H.PRIV / "sheets" / f"{gid}.json")


def rubric(half: str) -> dict:
    """{(gid, arm): {line: score}}: the two passes averaged; where they differ by 2 or more on a line and a third
    pass exists, the median of the three. Also the agreement between passes."""
    scores = H.load_json(J.JUDGE / half / "scores.json") or {"rubric": []}
    by = {}
    for r in scores["rubric"]:
        by.setdefault((r["gid"], r["drawing"]), {})[r["pass"]] = r
    out, agree, far = {}, [], 0
    for (gid, _name), passes in by.items():
        if 1 not in passes or 2 not in passes:
            continue
        a, b = passes[1]["scores"], passes[2]["scores"]
        merged = {}
        for line in LINES:
            x, y = float(a[line]), float(b[line])
            agree.append(abs(x - y))
            if abs(x - y) >= 2:
                far += 1
                if 3 in passes:
                    merged[line] = statistics.median([x, y, float(passes[3]["scores"][line])])
                    continue
            merged[line] = (x + y) / 2
        merged["fault"] = a.get("fault")
        for arm in passes[1]["arms"]:
            out[(gid, arm)] = merged
    return {"scores": out, "agreement": {"exact": float(np.mean([d == 0 for d in agree])) if agree else None,
                                         "within_one": float(np.mean([d <= 1 for d in agree])) if agree else None,
                                         "lines_two_apart": far}}


def drawn_repeats(gid: str, arm: str) -> float | None:
    name = J.drawing_of(gid, arm)
    if name is None:
        return None
    rec = (H.load_json(H.wdir(gid) / "drawings.json") or {}).get(name, {})
    if arm == "A":
        return _measured_repeats(gid)
    return rec.get("repeats")


def _measured_repeats(gid: str) -> float | None:
    """Arm A's repeats across the ruler, in the photo's own terms: a measured tile's width is its repeat as a share
    of the garment's width in the cutout (`measure._garment_width`); measured stripes run over the whole garment,
    so their period is read off the band sequence (its strongest clear self-match). A whole-garment tile has no
    repeat."""
    kept = H.load_json(H.wdir(gid) / "armA_kept.json")
    length = H.ruler_px(H.ruler(gid))
    if not kept or not length:
        return None
    cut = H.cut_of(gid)
    from closet.patterns.measure import _garment_width
    if kept.get("kind") == "tile" and kept.get("width_frac") and kept.get("how") in ("repeat", "straightened"):
        return length / (float(kept["width_frac"]) * _garment_width(cut))
    if kept.get("kind") == "stripes" and kept.get("bands"):
        n = 2000
        seq = np.zeros((n, 3))
        edges = np.cumsum([0.0] + [float(f) for _, f in kept["bands"]])
        edges = edges / edges[-1] * n
        for (hex_, _), a, b in zip(kept["bands"], edges[:-1], edges[1:], strict=True):
            seq[int(a):int(np.ceil(b))] = H._cie(np.array([[int(hex_[i:i + 2], 16) for i in (1, 3, 5)]], np.uint8))[0]
        x = seq - seq.mean(0)
        ac = np.array([(x[:-k] * x[k:]).sum() / max(1e-6, (x * x).sum()) for k in range(1, n // 2)])
        # the strongest clear self-match beyond the finest detail, then the shortest one nearly as strong (so a
        # multiple of the repeat is not taken for it)
        least = int(0.01 * n)
        peaks = [(k + 1, ac[k]) for k in range(least, len(ac) - 1) if ac[k] > ac[k - 1] and ac[k] >= ac[k + 1] and ac[k] > 0.3]
        if not peaks:
            return None
        top = max(v for _, v in peaks)
        peaks = [min(k for k, v in peaks if v >= 0.85 * top)]
        a = np.asarray(cut)[..., 3] > 128
        ys, xs = np.where(a)
        extent = (ys.max() - ys.min()) if kept.get("orientation") == "horizontal" else (xs.max() - xs.min())
        return length / (peaks[0] / n * extent)
    return None


def _sheet_pixels(s: dict, n: int = 4000) -> np.ndarray:
    cols = [s["ground"]] + list(s.get("colours") or [])
    hexes = [c["hex"] for c in cols if described._hex(c.get("hex"))]
    shares = np.array([max(0.0, float(c.get("share") or 0)) for c in cols if described._hex(c.get("hex"))])
    shares = shares / shares.sum() if shares.sum() > 0 else np.ones(len(hexes)) / len(hexes)
    counts = np.maximum(1, np.round(shares * n)).astype(int)
    rgb = np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in (described._hex(x) for x in hexes)], np.uint8)
    return H._cie(np.repeat(rgb, counts, 0))


def colour_share_distance(gid: str, arm: str, s: dict) -> float | None:
    """The sheet's colours and shares against the drawing's cloth, as the loop's colour measure (lightness half)."""
    name = J.drawing_of(gid, arm)
    if name is None:
        return None
    a = H._quantiles(_sheet_pixels(s))
    b = H._quantiles(H.drawing_pixels(Image.open(H.wdir(gid) / "draw" / f"{name}.png")))
    gap = np.abs(a - b).mean(0)
    return float(0.5 * gap[0] + gap[1] + gap[2])


def run_to_run(gid: str, arm: str) -> tuple[float, float] | None:
    """steady.py's two numbers over an arm's three runs, on the drawings: the colour make-up apart (sorted pixel
    lists, as the loop's colour measure) and, where both runs drew a repeat, the repeats' mean colour difference
    after the best alignment; averaged over the three pairs."""
    names = [J.drawing_of(gid, arm, r) for r in (1, 2, 3)]
    if None in names:
        return None
    pix = [H._quantiles(H.drawing_pixels(Image.open(H.wdir(gid) / "draw" / f"{n}.png"))) for n in names]
    make = [float((np.abs(a - b).mean(0) * [0.5, 1, 1]).sum()) for a, b in itertools.combinations(pix, 2)]
    return float(np.mean(make)), float(len(set(names)) == 1)


def cost(gid: str, arm: str) -> dict:
    """Calls, tokens, seconds and dollars at models.json's prices for one garment and arm (the shared cutout,
    description and ruler not counted; arm A's measuring time counted as seconds)."""
    calls = H.wdir(gid) / "calls"

    def recs(pattern):
        return [json.loads(p.read_text()) for p in sorted(calls.glob(pattern))]
    if arm == "A":
        rec = (H.load_json(H.wdir(gid) / "drawings.json") or {}).get("A", {})
        return {"calls": 0, "in": 0, "out": 0, "seconds": rec.get("seconds", 0.0), "usd": 0.0}
    if arm in ("B", "C-sonnet", "C-opus"):
        rs = recs(f"{arm}_run1.json")
    elif arm.startswith("D-small"):
        rs = recs("B_run1.json") + recs("D-small_chain1_round*.json")
    elif arm.startswith("D"):
        k = int(arm[1:])
        rs = recs("B_run1.json") + [r for r in (H.load_json(calls / f"D_chain1_round{i}.json") for i in range(1, k + 1)) if r]
    elif arm == "E":
        rs = recs("B_run*.json") + recs("D_chain*_round*.json")
    else:
        rs = []
    return {"calls": len(rs), "in": sum(sum(v for k, v in r["usage"].items() if k != "output_tokens") for r in rs),
            "out": sum(r["usage"]["output_tokens"] for r in rs), "seconds": sum(r["seconds"] for r in rs),
            "usd": sum(r["price_usd"] for r in rs)}


def main(half: str) -> None:
    ids = json.loads((H.PRIV / "split.json").read_text())[half]
    s_of = {g: sheet(g) for g in ids}
    rub = rubric(half)
    R = rub["scores"]
    steady_judge = {}
    for r in (H.load_json(J.JUDGE / half / "scores.json") or {}).get("steady", []):
        steady_judge[(r["gid"], r["arm"])] = bool(r["answer"].get("all_same"))
    table = {}
    for arm in ARMS:
        rows = [g for g in ids if (g, arm) in R]
        patterned = [g for g in rows if s_of[g] and s_of[g]["kind"] != "plain"]
        repeat = [g for g in rows if s_of[g] and s_of[g]["kind"] in ("stripes", "plaid") and s_of[g].get("count")]
        say_less = [g for g in rows if s_of[g] and s_of[g]["kind"] in ("plain", "other")]

        def shows(g, arm=arm):
            name = J.drawing_of(g, arm)
            rec = (H.load_json(H.wdir(g) / "drawings.json") or {}).get(name, {})
            return bool(rec.get("patterned"))
        totals = [sum(R[(g, arm)][x] for x in LINES) for g in rows]
        scale_ok = []
        for g in repeat:
            got = drawn_repeats(g, arm)
            scale_ok.append(got is not None and abs(got - s_of[g]["count"]) <= 0.25 * s_of[g]["count"])
        wrong = [g for g in patterned if shows(g) and (R[(g, arm)]["ground"] == 0 or R[(g, arm)]["pick"] == 0)]
        csd = [d for d in (colour_share_distance(g, arm, s_of[g]) for g in rows if s_of[g]) if d is not None]
        steady_arm = {"D3": "D3", "D-small3": "D-small3"}.get(arm, arm)
        rr = [x for x in (run_to_run(g, steady_arm) for g in rows) if x is not None] if arm in J.STEADY_ARMS else []
        same = [steady_judge[(g, steady_arm)] for g in rows if (g, steady_arm) in steady_judge]
        costs = [cost(g, arm) for g in rows]
        table[arm] = {
            "n": len(rows),
            "median_total": statistics.median(totals) if totals else None,
            "pick_2plus_patterned": np.mean([R[(g, arm)]["pick"] >= 2 for g in patterned]) if patterned else None,
            "ground_2plus_patterned": np.mean([R[(g, arm)]["ground"] >= 2 for g in patterned]) if patterned else None,
            "scale_within_25": np.mean(scale_ok) if scale_ok else None, "with_repeat": len(scale_ok),
            "confidently_wrong": len(wrong) / len(patterned) if patterned else None,
            "pattern_on_plain_or_print": np.mean([shows(g) for g in say_less]) if say_less else None,
            "colour_share_distance": float(np.median(csd)) if csd else None,
            "judge_all_same": np.mean(same) if same else None,
            "run_to_run_makeup": float(np.mean([x[0] for x in rr])) if rr else None,
            "cost_per_garment": {k: float(np.mean([c[k] for c in costs])) for k in ("calls", "in", "out", "seconds", "usd")} if costs else None,
            "by_family": {}, "by_garment": {},
        }
        for key, field in (("by_family", "family"), ("by_garment", "garment")):
            sets = {}
            for g in rows:
                sets.setdefault(H.item(g)[field], []).append(sum(R[(g, arm)][x] for x in LINES))
            table[arm][key] = {k: float(np.mean(v)) for k, v in sorted(sets.items())}
    out = {"half": half, "agreement": rub["agreement"], "arms": table}
    (H.PRIV / "results").mkdir(exist_ok=True)
    H.save_json(H.PRIV / "results" / f"{half}.json", json.loads(json.dumps(out, default=float)))
    print(json.dumps(out, indent=1, default=lambda x: round(float(x), 3)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--half", default="tuning")
    main(ap.parse_args().half)
