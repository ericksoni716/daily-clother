import numpy as np, cv2
from PIL import Image

def seal(mask, k_frac=0.035, lo=40):
    """Fill the see-through holes a background model leaves in a patterned garment. The mask is thickened and
    thinned back by about a check's size (a closing), which seals the grid of holes without moving the
    outline; every hole the closed garment then encloses is made solid. A real gap (between an arm and the body)
    wider than that stays open."""
    m = np.asarray(mask)
    b = (m > lo).astype(np.uint8)
    k = max(3, int(max(m.shape) * k_frac) | 1)
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    closed = cv2.morphologyEx(b, cv2.MORPH_CLOSE, ker)
    # fill what the closed garment encloses
    h, w = closed.shape
    flood = closed.copy()
    ff = np.zeros((h + 2, w + 2), np.uint8)
    pad = np.pad(flood, 1)
    cv2.floodFill(pad, np.zeros((h + 4, w + 4), np.uint8), (0, 0), 2)
    inside = pad[1:-1, 1:-1] != 2
    # only add where the closing worked from both sides: inside the closed shape, and not past the outline
    outline = cv2.erode(inside.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))).astype(bool)
    return Image.fromarray(np.where(outline, np.maximum(m, 255), m).astype(np.uint8), "L")


def seal2(mask, k_frac=0.035, lo=40, max_hole=0.004):
    """As seal, but only the small holes are filled: inside the closed garment, each separate patch the model
    left out is filled if it is smaller than `max_hole` of the garment (one check of a plaid), never a large
    one (the gap between an arm and the body)."""
    m = np.asarray(mask)
    b = (m > lo).astype(np.uint8)
    k = max(3, int(max(m.shape) * k_frac) | 1)
    closed = cv2.morphologyEx(b, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    h, w = closed.shape
    pad = np.pad(closed, 1)
    cv2.floodFill(pad, np.zeros((h + 4, w + 4), np.uint8), (0, 0), 2)
    inside = pad[1:-1, 1:-1] != 2
    left_out = (inside & (b == 0)).astype(np.uint8)
    n, lbl, stats, _ = cv2.connectedComponentsWithStats(left_out, connectivity=4)
    area = max(1, int(inside.sum()))
    small = np.zeros(n, bool)
    small[1:] = stats[1:, cv2.CC_STAT_AREA] < max_hole * area
    fill = small[lbl]
    return Image.fromarray(np.where(fill, 255, m).astype(np.uint8), "L")


def see_through(mask, k_frac=0.035, lo=40):
    """How much of the garment's closed outline the model left out (0 = solid)."""
    m = np.asarray(mask)
    b = (m > lo).astype(np.uint8)
    k = max(3, int(max(m.shape) * k_frac) | 1)
    closed = cv2.morphologyEx(b, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    h, w = closed.shape
    pad = np.pad(closed, 1)
    cv2.floodFill(pad, np.zeros((h + 4, w + 4), np.uint8), (0, 0), 2)
    inside = pad[1:-1, 1:-1] != 2
    return float((inside & (m < 200)).sum() / max(1, inside.sum()))
