"""The ceiling variant: a top-down photo, flattened to a few colours, laid over the front of the app's own shoe
shape (inside its outline). A stand-in made for the line-up: it hooks into frontshoe by replacing three of its
functions while it runs, and changes nothing in the app."""
from common import *
import math, cv2
import top as TOP
# where the opening's front edge (the top of the tongue) is, as a share of the length from the heel, read off the photos
THROAT = {"af1": 0.32, "boot_wheat": 0.30, "clubc": 0.35, "desert": 0.45, "grandpro": 0.36, "kswiss": 0.27, "loafer": 0.42,
          "nb574": 0.33, "oldskool": 0.32, "oxford": 0.42, "runner_black": 0.27, "runner_colour": 0.30, "samba": 0.33,
          "stan_navy": 0.33, "timberland": 0.30}
K = 6

def texture(key, k=K):
    f = WORK / "cache" / f"tex-{key}-{k}.npz"
    if f.exists():
        z = np.load(f); return z["img"], z["left"], z["right"], bool(z["medial_right"])
    rgb, mask, _ = TOP.norm(key)
    s = 520 / rgb.shape[0]
    rgb = cv2.resize(rgb, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    mask = cv2.resize(mask, (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_NEAREST)
    a = T.Approach("x", "x", "meanshift", k, 0.003, 1.2, 14, 26)
    inside = mask > 0
    real, lab = T.to_lab(rgb), T.to_lab(T.prefilter(rgb, mask, a))
    # plain k-means on the smoothed photo, no merging of shades (the tracer's merging made grey suede white)
    feat = lab[inside].astype(np.float32)
    _, labels, centres = cv2.kmeans(feat, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.5), 4, cv2.KMEANS_PP_CENTERS)
    labels = labels.ravel()
    lmap = np.full(mask.shape, -1, np.int32); lmap[inside] = labels
    lmap = T.smooth_labels(lmap, mask, k, 2.2)
    lmap = T.remove_specks(lmap, mask, max(6, int(0.0015 * inside.sum())))
    pal = np.zeros((k, 3), np.uint8)
    for i in range(k):
        sel = lmap == i
        if sel.any():
            pal[i] = np.median(rgb[sel], axis=0)
    img = np.zeros_like(rgb); img[inside] = pal[np.clip(lmap[inside], 0, len(pal) - 1)]
    H, W = mask.shape
    left = np.array([np.argmax(r) if r.any() else W // 2 for r in mask])
    right = np.array([W - 1 - np.argmax(r[::-1]) if r.any() else W // 2 for r in mask])
    # the toe's tip leans to the big toe's side: compare the last rows' middle with the widest row's
    wide = int(np.argmax(right - left)); tip = slice(int(H * 0.965), int(H * 0.99))
    medial_right = ((left[tip] + right[tip]) / 2).mean() > (left[wide] + right[wide]) / 2
    np.savez(f, img=img, left=left, right=right, medial_right=medial_right)
    return img, left, right, bool(medial_right)

STATE = {"key": None, "flip": {}}
_paint, _details, _lacing = frontshoe._Traced.paint, frontshoe._details, frontshoe._Traced.lacing
U0, NU, NA = frontshoe.INSTEP_U, 170, 52

def drape(tr, view, key):
    img, left, right, medial_right = texture(key)
    if STATE["flip"].get(key):
        medial_right = not medial_right
    H = img.shape[0]; t = THROAT[key]
    hw, inset, table, sole_t = tr.hw, tr.inset, tr.table, tr.sole_t
    def pt(u, a):
        return view(hw(u) * inset * math.cos(a), u, sole_t + frontshoe._interp(table, u) * math.sin(a))
    def colour(u, a):
        f = t + (u - U0) / (1 - U0) * (0.975 - t)
        y = min(H - 1, max(0, int(f * H)))
        c = math.cos(a) * 0.9 * (1 if medial_right else -1)      # +x on the shoe is its inner side
        x = int(round(left[y] + (c + 1) / 2 * (right[y] - left[y])))
        r, g, b = img[y, min(img.shape[1] - 1, max(0, x))]
        return f"#{r:02x}{g:02x}{b:02x}"
    us = [U0 + (1 - U0) * i / NU for i in range(NU + 1)]
    as_ = [math.pi * j / NA for j in range(NA + 1)]
    by: dict = {}
    order = []
    for i in range(NU):
        for j in range(NA):
            q = [pt(us[i], as_[j]), pt(us[i], as_[j + 1]), pt(us[i + 1], as_[j + 1]), pt(us[i + 1], as_[j])]
            area = sum(q[n][0] * q[(n + 1) % 4][1] - q[(n + 1) % 4][0] * q[n][1] for n in range(4))
            if area >= 0:     # turned away from the viewer
                continue
            c = colour((us[i] + us[i + 1]) / 2, (as_[j] + as_[j + 1]) / 2)
            order.append((c, "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in q) + "Z"))
    out, run_c, run = [], None, []
    for c, d in order + [(None, "")]:
        if c != run_c and run:
            out.append(f'<path d="{" ".join(run)}" fill="{run_c}" stroke="{run_c}" stroke-width=".5" stroke-linejoin="round"/>')
            run = []
        run_c = c; run.append(d)
    return out

def paint(self, view, line_c):
    out = _paint(self, view, line_c)
    if STATE["key"]:
        out += drape(self, view, STATE["key"])
    return out
def details(p, style, view, hw, inset, table, sole_t, shaft, base, line_c, ln, fill, traced=False):
    if STATE["key"]:
        return []
    return _details(p, style, view, hw, inset, table, sole_t, shaft, base, line_c, ln, fill, traced=traced)
def lacing(self, *a, **k):
    return [] if STATE["key"] else _lacing(self, *a, **k)
frontshoe._Traced.paint, frontshoe._details, frontshoe._Traced.lacing = paint, details, lacing

def set_turn(deg):
    frontshoe.TURN = deg
    frontshoe.SEE = frontshoe._see()

def feet(key, variant, case="shorts", w=130, h=110, uid="f"):
    """The figure's feet for one shoe: variant 'A', 'B', 'D' (the top photo draped on B)."""
    t = side_trace(key)
    kind = frontshoe.FROM_SHAPE if variant == "A" else frontshoe.FROM_PHOTO
    STATE["key"] = key if variant == "D" else None
    try:
        worn = dataclasses.replace(piece(key), traced=frontshoe.Chosen(t, kind, None))
        return M.feet_svg(M.outfit(worn, case), uid, 0, 0, w, h)
    finally:
        STATE["key"] = None
