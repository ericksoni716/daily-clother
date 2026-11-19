"""Freeze the test set and split it, once, as DESIGN.md section 2 says. Reads the private manifest
(bench/private/garment_loop/manifest.json), writes set.json and split.json beside it, and prints the counts table
(counts only, nothing that identifies a private photo)."""
from __future__ import annotations

import collections
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PRIV = ROOT / "bench" / "private" / "garment_loop"
DEMO = ROOT / "backend" / "closet" / "demo_data" / "images"
SEED = 20261118

GROUPS = ["gingham/tiny check", "small check/windowpane/tattersall", "medium plaid", "buffalo/huge check",
          "tartan with overchecks", "madras", "fine stripes", "medium/wide stripes", "uneven stripes", "colour block",
          "logo on patterned cloth", "placed detail", "solid", "print (cannot be expressed)"]
FAMILY = {g: "plaid and check" for g in GROUPS[:6]}
FAMILY.update({g: "stripes" for g in GROUPS[6:9]})
FAMILY.update({"colour block": "colour block", "logo on patterned cloth": "logo on pattern",
               "placed detail": "placed detail", "solid": "solid", "print (cannot be expressed)": "print"})
KIND = {"shirt": "top", "tee/polo": "top", "knit/sweatshirt": "knit", "jacket/outer": "outer", "trousers": "bottom",
        "shorts": "bottom"}
ORDER = ["top", "knit", "outer", "bottom"]

# the demo closet's garment photos: tidy controls (its shoes are not garments)
DEMO_ITEMS = [
    {"id": "demo-flannel", "file": "plaid-flannel.webp", "group": "medium plaid", "garment": "shirt", "tuning_only": True},
    {"id": "demo-madras", "file": "plaid-madras.webp", "group": "madras", "garment": "shirt", "tuning_only": True},
    {"id": "demo-jeans", "file": "jeans.webp", "group": "solid", "garment": "trousers"},
    {"id": "demo-marl", "file": "marl-sweater.webp", "group": "solid", "garment": "knit/sweatshirt"},
    {"id": "demo-graphic", "file": "graphic-tee.webp", "group": "placed detail", "garment": "tee/polo"},
]
# decided from the contact sheet before any run (see README): three wavy bands with no repeat are colour blocking
REGROUPED = {"g54": "colour block"}
# the owner's decision (18 November, before any arm ran): studio and catalogue photos are in the set, reported as
# their own row too, because the owner may well import online photos of their garments
STUDIO_IN = True


def main() -> None:
    if (PRIV / "split.json").exists() and "--again" not in sys.argv:
        sys.exit("already frozen (split.json exists)")
    manifest = json.loads((PRIV / "manifest.json").read_text())
    kept, left_out = [], []
    for r in manifest:
        group = REGROUPED.get(r["id"], r["group"])
        rec = {"id": r["id"], "path": str(PRIV / "photos" / Path(r["file"]).name), "source": "owner", "group": group,
               "family": FAMILY[group], "garment": r["garment"], "kind": KIND[r["garment"]],
               "conditions": r["conditions"], "size": [r["width"], r["height"]], "hard_case": r.get("hard_case"),
               "tuning_only": False, "studio": r["bar"] != "pass"}
        ok = r["bar"] == "pass" or (STUDIO_IN and "studio/catalogue" in r["conditions"])
        (kept if ok else left_out).append(rec | {"bar_reason": r.get("bar_reason")})
    for d in DEMO_ITEMS:
        kept.append({"id": d["id"], "path": str(DEMO / d["file"]), "source": "demo", "group": d["group"],
                     "family": FAMILY[d["group"]], "garment": d["garment"], "kind": KIND[d["garment"]],
                     "conditions": ["tidy (demo closet)"], "size": None, "hard_case": None,
                     "tuning_only": d.get("tuning_only", False), "studio": False})
    rng = random.Random(SEED)
    split = {"tuning": [], "held-out": []}
    by_id = {r["id"]: r for r in kept}
    for r in kept:
        r["hard"] = bool(r["hard_case"])

    def count(half, key, value):
        return sum(by_id[i][key] == value for i in split[half])
    # The balancing deal (DESIGN.md, log of changes): the first rule, dealt alternately within each group after
    # sorting by garment kind, sent all five jackets to the tuning half. Each photo, in its group's seeded shuffle,
    # goes to the half with fewer of its group so far, then fewer of its garment kind, then (a studio photo) fewer
    # studio photos, then (a known hard case) fewer hard cases, then fewer overall, then the held-out half.
    for group in GROUPS:
        members = [r for r in kept if r["group"] == group]
        split["tuning"] += [r["id"] for r in members if r["tuning_only"]]
        rest = sorted((r for r in members if not r["tuning_only"]), key=lambda r: r["id"])
        rng.shuffle(rest)
        for r in rest:
            half = min(("held-out", "tuning"), key=lambda h: (count(h, "group", group), count(h, "kind", r["kind"]),
                                                               count(h, "studio", True) if r["studio"] else 0,
                                                               count(h, "hard", True) if r["hard"] else 0,
                                                               len(split[h]), h != "held-out"))
            split[half].append(r["id"])
    for r in kept:
        r.pop("hard", None)
        r["half"] = "tuning" if r["id"] in split["tuning"] else "held-out"
    (PRIV / "set.json").write_text(json.dumps(kept, indent=1))
    (PRIV / "split.json").write_text(json.dumps(split | {"seed": SEED, "left_out": [
        {"id": r["id"], "group": r["group"], "garment": r["garment"], "reason": r["bar_reason"]} for r in left_out]}, indent=1))
    table(kept, left_out)


def table(kept: list[dict], left_out: list[dict]) -> None:
    halves = ("tuning", "held-out")
    print(f"{len(kept)} garments ({sum(r['source'] == 'owner' for r in kept)} of the owner's, "
          f"{sum(r['source'] == 'demo' for r in kept)} demo), {len(left_out)} left out")
    for title, key in (("group", "group"), ("family", "family"), ("garment", "garment")):
        print(f"\n| {title} | tuning | held-out | all |\n|---|---|---|---|")
        names = GROUPS if key == "group" else sorted({r[key] for r in kept})
        for n in names:
            c = [sum(r[key] == n and r["half"] == h for r in kept) for h in halves]
            print(f"| {n} | {c[0]} | {c[1]} | {sum(c)} |")
    conds = collections.Counter(c for r in kept for c in r["conditions"])
    print("\n| photo condition | tuning | held-out | all |\n|---|---|---|---|")
    for c, _ in conds.most_common():
        n = [sum(c in r["conditions"] and r["half"] == h for r in kept) for h in halves]
        print(f"| {c} | {n[0]} | {n[1]} | {sum(n)} |")
    print("\nleft out:", dict(collections.Counter(r["group"] for r in left_out)))


if __name__ == "__main__":
    main()
