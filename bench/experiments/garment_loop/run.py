"""Run the garment loop test's steps (DESIGN.md). Everything kept under bench/private/garment_loop/work/<id>/.

  python run.py prep [ids]                      cutout, the app's description, the ruler
  python run.py arm-a [ids]                     the app today: measured where it passes its check, else its colour
  python run.py describe B|C-sonnet|C-opus [ids] [--runs 1,2,3]
  python run.py loop D|D-small [ids] [--chains 1,2,3]
  python run.py status

ids default to the tuning half (`--half held-out` for the other). Three calls run at a time; when the Claude plan's
usage limit is reached everything stops, and running the same step again carries on where it stopped."""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness as H  # noqa: E402
from closet.patterns import surface  # noqa: E402
from closet.tagger.schema import NAMED_HEX  # noqa: E402

ARM_MODEL = {"B": H.TAGGING, "C-sonnet": H.SORTING, "C-opus": H.DRAWING, "F": H.SORTING}   # F: the second form
LOOP_MODEL = {"D": H.DRAWING, "D-small": H.TAGGING}
ROUNDS = 3
WORKERS = 3


# ---- one drawing --------------------------------------------------------------------------------------------

def _drawings(gid: str) -> dict:
    return H.load_json(H.wdir(gid) / "drawings.json") or {}


def _keep_drawing(gid: str, name: str, rec: dict) -> None:
    with _lock:
        all_ = _drawings(gid)
        all_[name] = rec
        H.save_json(H.wdir(gid) / "drawings.json", all_)


_lock = __import__("threading").Lock()


def _fallback(gid: str) -> dict:
    """No usable surface: the cloth in the colour the app's description names."""
    word = H.base_description(gid)["answer"].get("color")
    return {"kind": "plain", "bands": [], "direction": None, "size": None, "blocks": [],
            "colors": [(NAMED_HEX.get(word, "#888888"), 1.0)], "fell": "no usable surface"}


def surface_drawing(gid: str, name: str, raw, scale: float = 1.0, second: bool = False) -> dict:
    """Read, draw, render and score one described surface; kept as `name`."""
    have = _drawings(gid).get(name)
    if have is not None:
        return have
    cut, points = H.cut_of(gid), H.ruler(gid)
    base = H.base_description(gid)["answer"]
    bottom = base["category"] if base["category"] in H.BOTTOMS else None
    desc = surface.read(raw) if raw is not None else None
    desc = desc or _fallback(gid)
    extra = {}
    if second:
        extra = {"second": True, "aspect": H.aspect(gid) if desc.get("panels") else None,
                 "pieced": H.pieced(gid) if desc["kind"] == "other" else None}
    d = surface.drawn(desc, cut, points, bottom=bottom, scale=scale, **extra)
    png = H.draw(gid, name, H.svg_surface(base, d, name.replace("_", "")[:24]))
    score = H.loop_score(cut, png, d, points)
    rec = {"raw": raw, "kind": desc["kind"], "fell": desc.get("fell"), "repeats": d["repeats"], "second": second,
           "scale_how": d["scale_how"], "widths": d["widths"], "scale": scale, "not_drawn": d["not_drawn"],
           "patterned": d["kept"] is not None or bool(d["blocks"]), "score": score}
    _keep_drawing(gid, name, rec)
    return rec


# ---- the steps ----------------------------------------------------------------------------------------------

def prep(gid: str) -> str:
    t0 = time.time()
    H.make_cutout(gid)
    base = H.base_description(gid)
    H.ruler(gid)
    return f"{base['answer']['category']} {base['answer']['pattern']} ({time.time() - t0:.0f} s)"


def arm_a(gid: str) -> str:
    have = _drawings(gid).get("A")
    if have is not None:
        return "kept"
    from closet import palette
    from closet.patterns import measure
    base = H.base_description(gid)["answer"]
    cut = H.cut_of(gid)
    pattern = base["pattern"]
    name = (base.get("details") or {}).get("pattern_name")
    how = "graphic" if base["category"] in H.TOPS and (pattern == "graphic" or (pattern == "other" and name == "novelty")) \
        else pattern if pattern in ("plaid", "stripe", "floral", "camo", "other") else None
    kept, seconds, error = None, 0.0, None
    if how is not None:
        marks = H.ruler(gid) if base["category"] in H.TOPS and how != "graphic" else None
        words = list(dict.fromkeys([base.get("color")] + list(base.get("secondary_colors") or [])))
        t0 = time.time()
        try:
            kept = palette.keep(measure.measure(cut, how, [w for w in words if w], marks), pattern)
        except Exception as e:      # the app keeps the item in its colour with a note
            error = f"{type(e).__name__}: {e}"[:200]
        seconds = round(time.time() - t0, 1)
    png = H.draw(gid, "A", H.svg_measured(base, kept, "A"))
    d = {"tile": None, "repeats": None}
    score = H.loop_score(cut, png, d, H.ruler(gid))
    rec = {"how": how, "kept": None if kept is None else {k: v for k, v in kept.items() if k not in ("image",)},
           "measured": kept is not None, "error": error, "seconds": seconds,
           "patterned": kept is not None and kept.get("kind") != "plain", "score": score}
    _keep_drawing(gid, "A", rec)
    (H.wdir(gid) / "armA_kept.json").write_text(json.dumps(kept))
    return f"{how or 'nothing to measure'}: {'kept ' + str(kept.get('kind')) if kept else 'plain colour'}"


def describe(gid: str, arm: str, run: int) -> str:
    second = arm == "F"
    rec = H.describe2(gid, run) if second else H.describe(gid, ARM_MODEL[arm], run)
    d = surface_drawing(gid, f"{arm}_run{run}", rec.get("surface"), second=second)
    return f"{arm} run {run}: {d['kind']} score {d['score']['score']} ({rec['seconds']} s)"


def loop(gid: str, tag: str, chain: int) -> str:
    """One chain of the loop, from B's answer of the same run, corrected ROUNDS times."""
    model = LOOP_MODEL[tag]
    start = H.describe(gid, H.TAGGING, chain)
    current = start.get("surface")
    first = surface_drawing(gid, f"B_run{chain}", current)
    cut = H.cut_of(gid)
    rounds = [{"round": 0, "drawing": f"B_run{chain}", "score": first["score"]["score"], "kind": first["kind"]}]
    best = (first["score"]["score"], f"B_run{chain}")
    scale = 1.0
    prev_png = H.wdir(gid) / "draw" / f"B_run{chain}.png"
    for r in range(1, ROUNDS + 1):
        from PIL import Image
        compare = H.compare_image(cut, Image.open(prev_png).convert("RGBA"))
        rec = H.correct(gid, tag, chain, r, current if current is not None else {}, compare, model)
        patch = rec["answer"] or {}
        scale *= surface.scale_of(patch)
        current = surface.patched(current or {}, patch)
        name = f"{tag}_chain{chain}_round{r}"
        d = surface_drawing(gid, name, current, scale=scale)
        if d["score"]["score"] > best[0]:
            best = (d["score"]["score"], name)
        rounds.append({"round": r, "drawing": name, "score": d["score"]["score"], "kind": d["kind"],
                       "seen": patch.get("seen"), "changed": [k for k in ("kind", "bands", "direction", "blocks", "colors")
                                                              if patch.get(k) is not None] + (["scale"] if patch.get("scale") not in (None, 1, 1.0) else []),
                       "kept_after": best[1], "seconds": rec["seconds"]})
        prev_png = H.wdir(gid) / "draw" / f"{name}.png"
    H.save_json(H.wdir(gid) / f"{tag}_chain{chain}.json", {"rounds": rounds, "kept": best[1]})
    return f"{tag} chain {chain}: " + " -> ".join(f"{x['score']:.3f}" for x in rounds) + f", kept {best[1]}"


# ---- running many ---------------------------------------------------------------------------------------------

def ids_for(args) -> list[str]:
    if args.ids:
        return args.ids
    split = json.loads((H.PRIV / "split.json").read_text())
    return split[args.half]


def run_all(jobs: list[tuple], fn) -> None:
    stop = False
    with ThreadPoolExecutor(WORKERS) as pool:
        futures = {pool.submit(fn, *job): job for job in jobs}
        for f in as_completed(futures):
            job = futures[f]
            try:
                print(*job, "->", f.result(), flush=True)
            except H.PlanLimit as e:
                if not stop:
                    print("THE PLAN'S USAGE LIMIT:", e, flush=True)
                stop = True
                for other in futures:
                    other.cancel()
            except Exception as e:
                print(*job, "FAILED", type(e).__name__, str(e)[:300], flush=True)
                traceback.print_exc(limit=3)
    if stop:
        sys.exit(3)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("step")
    ap.add_argument("arm", nargs="?")
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--half", default="tuning")
    ap.add_argument("--runs", default="1,2,3")
    ap.add_argument("--chains", default="1,2,3")
    args = ap.parse_args()
    if args.step in ("prep", "arm-a") and args.arm:
        args.ids = [args.arm] + args.ids
    if args.step == "prep":
        run_all([(g,) for g in ids_for(args)], prep)
    elif args.step == "arm-a":
        run_all([(g,) for g in ids_for(args)], arm_a)
    elif args.step == "describe":
        runs = [int(x) for x in args.runs.split(",")]
        run_all([(g, args.arm, r) for r in runs for g in ids_for(args)], describe)
    elif args.step == "loop":
        chains = [int(x) for x in args.chains.split(",")]
        run_all([(g, args.arm, c) for c in chains for g in ids_for(args)], loop)
    elif args.step == "status":
        for g in ids_for(args):
            have = sorted(_drawings(g))
            print(g, len(have), " ".join(have))
    else:
        ap.error(f"unknown step {args.step}")


if __name__ == "__main__":
    main()
