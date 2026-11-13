import sys; sys.path.insert(0, ".")
import numpy as np, cv2
from PIL import Image
import dewarp

P, Q = 40, 48
def truth_tile():
    t = np.zeros((Q, P, 3), np.float32)
    warp = np.zeros(P, int); weft = np.zeros(Q, int)
    warp[:14] = 1; warp[14:16] = 2; warp[22:30] = 3; warp[33] = 2      # bands across: navy, white, burgundy
    weft[:12] = 1; weft[12:14] = 2; weft[20:32] = 3; weft[40] = 2
    cols = np.array([[120, 120, 120], [35, 45, 75], [240, 240, 235], [110, 30, 45]], np.float32)
    return (cols[warp][None, :, :] + cols[weft][:, None, :]) / 2
T = truth_tile()
H, W = 700, 600
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
ang = np.radians(4)                                       # a slight turn, plus slow waves (crumpling)
u = (np.cos(ang) * xx + np.sin(ang) * yy) + 6 * np.sin(yy / 90) + 4 * np.sin(xx / 130)
v = (-np.sin(ang) * xx + np.cos(ang) * yy) + 5 * np.sin(xx / 110) + 3 * np.cos(yy / 70)
big = np.tile(T, (H // Q + 40, W // P + 40, 1))
off = 20
img = np.dstack([cv2.remap(big[..., c], (u % P + off * P).astype(np.float32), (v % Q + off * Q).astype(np.float32), cv2.INTER_LINEAR) for c in range(3)])
img += np.random.default_rng(0).normal(0, 6, img.shape)    # noise
alpha = np.zeros((H, W), np.uint8); alpha[40:660, 60:540] = 255
cut = Image.fromarray(np.dstack([np.clip(img, 0, 255).astype(np.uint8), alpha]), "RGBA")
cut.save("synthetic-crumpled.png")
res = dewarp.rectify(cut, P, Q)
tile_lab, info = res
rec = dewarp.lab_to_rgb(tile_lab)
rec_small = cv2.resize(rec, (P, Q), interpolation=cv2.INTER_AREA).astype(np.float32)
# compare to truth at the best cyclic shift
best = min(((np.abs(np.roll(np.roll(rec_small, dy, 0), dx, 1) - T).mean(), dy, dx) for dy in range(Q) for dx in range(P)))
naive = np.asarray(cut.convert("RGB"))[300:300 + Q, 250:250 + P].astype(np.float32)
best_naive = min(((np.abs(np.roll(np.roll(naive, dy, 0), dx, 1) - T).mean(), dy, dx) for dy in range(Q) for dx in range(P)))
print(f"mean colour error vs the true repeat: flattened {best[0]:.1f}, a square cut straight from the photo {best_naive[0]:.1f} (0-255 scale)")
Image.fromarray(np.hstack([cv2.resize(T.astype(np.uint8), (P*6, Q*6), interpolation=cv2.INTER_NEAREST),
                           np.full((Q*6, 8, 3), 255, np.uint8),
                           cv2.resize(np.roll(np.roll(rec_small, best[1], 0), best[2], 1).clip(0,255).astype(np.uint8), (P*6, Q*6), interpolation=cv2.INTER_NEAREST),
                           np.full((Q*6, 8, 3), 255, np.uint8),
                           cv2.resize(np.roll(np.roll(naive, best_naive[1], 0), best_naive[2], 1).clip(0,255).astype(np.uint8), (P*6, Q*6), interpolation=cv2.INTER_NEAREST)])).save("synthetic-check.png")
