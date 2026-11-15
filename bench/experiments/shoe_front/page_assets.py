"""Assets for the line-up page: feet (three variants x ten shoes), side tiles, whole figures, the look-over sheet."""
from sheets import *
import json
A = WORK / "page" / "assets"; A.mkdir(parents=True, exist_ok=True)
K = 3 * 0.8     # a phone shows the figure at 0.8 px a unit; drawn three times as sharp
VAR = {"today": ("A", 11), "top": ("D", 11), "turn": ("D", 20)}
def png(svg_body, w, h, name, k=K):
    p = A / f"{name}.svg"
    p.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w * k:.0f}" height="{h * k:.0f}"><rect width="{w}" height="{h}" fill="#f1eee8"/>{svg_body}</svg>')
    M.to_png(p, p.with_suffix(".png"), (int(w * k), int(h * k))); p.unlink()
for i, key in enumerate(TEN):
    for name, (v, turn) in VAR.items():
        png(cell(key, v, turn, False, uid=f"{name}{i}"), W, H, f"feet-{name}-{i}")
        png(cell(key, v, turn, False, case="trousers", uid=f"{name}{i}t"), W, H, f"hem-{name}-{i}")
    png(M.side_svg(side_trace(key), 0, 0, M.SIDE_W, M.SIDE_H), M.SIDE_W, M.SIDE_H, f"tile-{i}", k=2.4)
# whole figures, for judging the stance
for turn in (11, 20):
    set_turn(turn)
    for case in ("shorts", "trousers"):
        worn = dataclasses.replace(piece("oldskool"), traced=frontshoe.Chosen(side_trace("oldskool"), frontshoe.FROM_PHOTO, None))
        STATE["key"] = "oldskool"
        svg = figure(M.outfit(worn, case), uid=f"w{turn}{case}")
        STATE["key"] = None
        (A / f"whole-{turn}-{case}.svg").write_text(svg)
        m = re.search(r'viewBox="([\d. -]+)"', svg); vb = [float(x) for x in m.group(1).split()]
        M.to_png(A / f"whole-{turn}-{case}.svg", A / f"whole-{turn}-{case}.png", (int(vb[2] * 1.6), int(vb[3] * 1.6)))
        (A / f"whole-{turn}-{case}.svg").unlink()
        print("whole", turn, case, vb)
set_turn(11)
print(len(list(A.glob("*.png"))))
