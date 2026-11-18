"""The app's own landmarks call (plan route) for each cutout, as the app makes it for a patterned top."""
import json
import sys
from pathlib import Path

from PIL import Image

from closet.tagger import landmarks

R2 = Path(__file__).parent
S = R2.parent
CUTS = {"0_jacket": S / "desc_out/0_jacket.cut.png", **{k: S / f"more_out/{k}.cut.png" for k in
        ("1_floor", "2_purple", "3_window", "4_rust", "5_dark")},
        "demo_flannel": Path("/home/user/daily-clother/.claude/worktrees/agent-a896f14d6a33e0528/backend/closet/demo_data/images/plaid-flannel.cut.webp"), "demo_madras": Path("/home/user/daily-clother/.claude/worktrees/agent-a896f14d6a33e0528/backend/closet/demo_data/images/plaid-madras.cut.webp")}
(R2 / "landmarks").mkdir(exist_ok=True)
for stem in sys.argv[1:] or CUTS:
    marks = landmarks.ask(Image.open(CUTS[stem]), ("plan",))
    (R2 / "landmarks" / f"{stem}.json").write_text(json.dumps(marks))
    print(stem, {k: v for k, v in marks.items() if k.startswith(("underarm", "neck", "hem"))}, flush=True)
