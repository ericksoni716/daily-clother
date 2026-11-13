"""Checks on a background-removal mask for patterned items.

The app's default background-removal model can treat a plaid's dark checks as background, leaving the
cutout see-through in the shape of its own pattern. `see_through` measures how much of the garment's closed
outline the model left out; above about 20% (a plaid's checks, bold stripes) a second model is worth asking
and the two masks combined.
"""
import cv2
import numpy as np


def see_through(mask, k_frac=0.035, lo=40):
    """How much of the garment's closed outline the model left out (0 = solid). `mask` is the model's
    mask (0-255, a PIL "L" image or an array)."""
    m = np.asarray(mask)
    b = (m > lo).astype(np.uint8)
    k = max(3, int(max(m.shape) * k_frac) | 1)
    closed = cv2.morphologyEx(b, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    h, w = closed.shape
    pad = np.pad(closed, 1)
    cv2.floodFill(pad, np.zeros((h + 4, w + 4), np.uint8), (0, 0), 2)
    inside = pad[1:-1, 1:-1] != 2
    return float((inside & (m < 200)).sum() / max(1, inside.sum()))
