"""For each shoe: the measured solid seen as the figure sees it (from the front, 24 degrees above), in the drawing
frame's own units, as an outline to draw over. Writes draw/shoe-N/guide.svg, guide.png and guide.json."""
import json, subprocess
import numpy as np, cv2
import shape as S
DRAW = S.W.parent / "draw"
U = 16.0   # frame units per cm
S.LOOK = 15.0   # the view the owner liked: from the front and a little above
import math
for n in range(1, 6):
    sd = S.Solid(n)
    part, _ = sd.render(px=U, ss=2, turn=0.0, w=200, h=420, ground=390, leg_x=100)
    shoe = cv2.morphologyEx((part == 1).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    sd.with_leg = False
    full, _ = sd.render(px=U, ss=2, turn=0.0, w=200, h=420, ground=390, leg_x=100)   # without the leg: the whole shoe
    sd.with_leg = True
    whole = cv2.morphologyEx((full == 1).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    def path(mask):
        cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        c = cv2.approxPolyDP(max(cs, key=cv2.contourArea), 2.0, True)[:, 0, :] / 2.0
        c[:, 1] -= 150
        return "M" + " L".join(f"{x:.0f},{y:.0f}" for x, y in c) + " Z", c
    d_whole, cw = path(whole); d_vis, cv_ = path(shoe)
    ys, xs = np.nonzero(whole); y_top = ys.min() / 2 - 150
    boot = sd.top.max() * S.LENGTH_CM > 15
    zf = 0.33 if boot else 0.47                          # where the leg comes out: a boot's shaft front, a low shoe's tongue top
    hf = (sd.top.max() if boot else sd.top[int(zf * S.L)]) * S.LENGTH_CM + (0 if boot else 1.2)
    open_front = 240 + ((zf - 1) * S.LENGTH_CM * math.sin(math.radians(S.LOOK)) - hf * math.cos(math.radians(S.LOOK))) * U
    rows = np.nonzero(whole.any(1))[0]
    widths = [(whole[r].nonzero()[0].max() - whole[r].nonzero()[0].min()) / 2 for r in rows]
    k = int(np.argmax(widths))
    info = {"units_per_cm": U, "ground_y": 240, "shoe_top_y": round(float(y_top)), "opening_front_y": round(float(open_front)) if open_front is not None else None,
            "widest": {"width": round(float(widths[k])), "at_y": round(float(rows[k] / 2 - 150))},
            "x_min": round(float(xs.min() / 2)), "x_max": round(float(xs.max() / 2)),
            "height_cm": round(float(sd.top.max() * S.LENGTH_CM), 1), "width_cm": round(float(2 * sd.w.max() * S.LENGTH_CM), 1)}
    d = DRAW / f"shoe-{n}"
    svg = (f'<path d="{d_whole}" fill="#e9e4d8" stroke="#b05a2a" stroke-width="1.5" stroke-dasharray="5 4"/>'
           f'<path d="M40,{open_front:.0f} Q100,{open_front + 14:.0f} 160,{open_front:.0f}" fill="none" stroke="#b05a2a" stroke-width="2"/>')
    (d / "guide.svg").write_text(svg); (d / "guide.json").write_text(json.dumps(info, indent=1))
    full_svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-20 -160 240 420" width="480" height="840"><rect x="-20" y="-160" width="240" height="420" fill="#fff"/>'
                f'<path d="M62,-150 L138,-150 L138,60 L62,60 Z" fill="#cfe3d6" stroke="#7a9" stroke-width="1"/>{svg}'
                f'<line x1="-20" y1="240" x2="220" y2="240" stroke="#999" stroke-width="1"/></svg>')
    (d / "guide.full.svg").write_text(full_svg)
    print(n, info)
