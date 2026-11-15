"""Shared by the shoe-front experiment (see README.md): real photos, the app's own tracer and figure.
Everything it reads and writes is under WORK (bench/private/shoe_front by default, git-ignored)."""
import os, sys, pickle, dataclasses, re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
WORK = Path(os.environ.get("SHOE_FRONT_WORK", ROOT / "bench" / "private" / "shoe_front"))
MODELS = Path(os.environ.get("SHOE_FRONT_MODELS", ROOT / "bench" / "models"))
for p in ("backend", "tools", "bench"):
    sys.path.insert(0, str(ROOT / p))
from PIL import Image
import numpy as np
from closet.drawing import frontlook, frontshoe, traced
from closet.drawing import trace as T
from closet.drawing.figure import K_PX, Piece, figure, plan
from closet_bench import trace_shoes as B
import make_traced_front_sheet as M

PHOTOS = WORK / "photos"
CUT = B.cutters("model", "isnet-general-use", MODELS)
# key: (label, category, style, colour, details)
SHOES = {
    "stan_navy": ("white court shoe, navy heel", "sneakers", "low_sneaker", "#f4f4f2", {}),
    "clubc": ("cream court shoe, green mark", "sneakers", "low_sneaker", "#efeadc", {}),
    "oldskool": ("black skate shoe, white stripe", "sneakers", "low_sneaker", "#1c1c1e", {}),
    "samba": ("black trainer, three stripes, gum sole", "sneakers", "low_sneaker", "#1a1a1c", {}),
    "kswiss": ("black skate shoe, big white logo", "sneakers", "low_sneaker", "#1c1c1e", {}),
    "nb574": ("grey suede runner", "sneakers", "runner", "#a8a39a", {}),
    "runner_black": ("black runner, purple sole", "sneakers", "runner", "#2a2a30", {}),
    "runner_colour": ("mint runner", "sneakers", "runner", "#a8e0d0", {}),
    "af1": ("grey mesh runner", "sneakers", "runner", "#8a9096", {}),
    "grandpro": ("navy leather sneaker", "sneakers", "low_sneaker", "#2a3a5a", {}),
    "desert": ("brown desert boot", "boots", "boot", "#7a4a2a", {}),
    "oxford": ("tan cap-toe oxford", "dress_shoes", "oxford", "#b06a30", {"toe_cap": "stitched"}),
    "loafer": ("black penny loafer", "dress_shoes", "loafer", "#1a1a1a", {}),
    "timberland": ("wheat work boot A", "boots", "boot", "#d39a3e", {"shoe_height": "high", "tread": "lug"}),
    "boot_wheat": ("wheat work boot B", "boots", "boot", "#d39a3e", {"shoe_height": "high", "tread": "lug"}),
    "blundstone": ("brown chelsea boot", "boots", "chelsea_boot", "#3a2a24", {}),
}

def side_trace(key):
    f = WORK / "cache" / f"{key}.pkl"
    if f.exists():
        return pickle.loads(f.read_bytes())
    img = Image.open(PHOTOS / key / "LEFT.jpg").convert("RGB")
    t = traced.traced_shoe(T.trace_photo(img, CUT))
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(pickle.dumps(t))
    return t

def piece(key):
    _, cat, style, colour, details = SHOES[key]
    return Piece(cat, M.answer(cat, style, **details), colour)
