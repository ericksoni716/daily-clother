"""One sheet of every variant for the ten pairs: WORK/out/all.png (and its two halves)."""
from drape import *
TEN = ["stan_navy", "clubc", "oldskool", "samba", "kswiss", "nb574", "runner_black", "grandpro", "desert", "timberland"]
W, H, pad = 130, 110, 6
LIMITS = (frontshoe.MIN_PANEL_CM2, frontshoe.MIN_BLOCK_CELLS)
def limits(small):
    frontshoe.MIN_PANEL_CM2, frontshoe.MIN_BLOCK_CELLS = (4.5, 8) if small else LIMITS
# (title, variant, turn, small limits)
COLS = [("today: from the shape", "A", 11, False), ("today: from the photo", "B", 11, False), ("smaller limits", "B", 11, True),
        ("top photo laid on", "D", 11, False), ("turned 20°, side only", "B", 20, False), ("turned 20°, top photo", "D", 20, False),
        ("turned 30°, top photo", "D", 30, False)]
def cell(k, v, turn, small, case="shorts", uid="x"):
    set_turn(turn); limits(small)
    try:
        return feet(k, v, case, W, H, uid=uid)
    finally:
        set_turn(11); limits(False)
if __name__ == "__main__":
    out = []
    for r, k in enumerate(TEN):
        for c, (_, v, turn, small) in enumerate(COLS):
            out.append(f'<g transform="translate({c * (W + pad) + pad} {r * (H + pad) + pad})"><rect width="{W}" height="{H}" rx="5" fill="#f1eee8"/>{cell(k, v, turn, small, uid=f"r{r}c{c}")}</g>')
    TW, TH = len(COLS) * (W + pad) + pad, len(TEN) * (H + pad) + pad
    (WORK / "out").mkdir(parents=True, exist_ok=True)
    p = WORK / "out" / "all.svg"
    p.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {TW} {TH}" width="{TW * 2:.0f}" height="{TH * 2:.0f}"><rect width="{TW}" height="{TH}" fill="#fbfaf7"/>{"".join(out)}</svg>')
    M.to_png(p, p.with_suffix(".png"), (int(TW * 2), int(TH * 2)))
    im = Image.open(p.with_suffix(".png")); w, h = im.size
    im.crop((0, 0, w, h // 2)).save(WORK / "out" / "all1.png"); im.crop((0, h // 2, w, h)).save(WORK / "out" / "all2.png")
