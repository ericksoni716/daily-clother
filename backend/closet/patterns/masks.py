"""Checks on a background-removal mask, and on what a cutout holds.

The app's default background-removal model can treat a plaid's dark checks as background, leaving the
cutout see-through in the shape of its own pattern. `see_through` measures how much of the garment's closed
outline the model left out; above about 20% (a plaid's checks, bold stripes) a second model is worth asking
and the two masks combined.

It can also keep what the garment lies on: a white duvet behind a dark jacket. `doubtful` says when a mask
looks like more than one garment (see-through, running out of the photo's frame, or two kinds of surface), and
`settle` then takes what the two models agree on and keeps what only one of them saw unless it is another
surface that runs out of the frame. `doubtful_cutout` asks `doubtful` of a cutout the first model made alone,
while the second was not there yet. `surfaces` is the same idea for a cutout already made, used when a pattern
is measured.
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


SEE_THROUGH = 0.2   # a mask this see-through inside its outline is asked of the second model as well
APART = 40.0        # two surfaces whose overall colours differ by this much (delta E) are not one cloth
OUT_OF_FRAME = 0.08  # a mask on this much of the photo's edge runs out of the frame: a bed or a floor does, a garment rarely
SMALL = 300         # these checks look at the photo this many pixels across


def _small(rgb, mask):
    """The photo (RGB array) in Lab and the mask (0-255) as true/false, both SMALL px across."""
    f = max(1, max(mask.shape[:2]) // SMALL)
    size = (max(1, mask.shape[1] // f), max(1, mask.shape[0] // f))
    lab = cv2.cvtColor(cv2.resize(np.ascontiguousarray(rgb), size, interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2LAB)
    return lab.astype(np.float32) * (100 / 255, 1, 1), cv2.resize(mask, size, interpolation=cv2.INTER_AREA) > 128


def _from_afar(lab, m):
    """The colours inside `m` seen from far enough that a pattern blurs into its overall colour."""
    w = m.astype(np.float32)
    far = 0.04 * max(m.shape)
    den = np.maximum(cv2.GaussianBlur(w, (0, 0), far), 1e-3)
    return np.dstack([cv2.GaussianBlur(lab[..., c].astype(np.float32) * w, (0, 0), far) / den for c in range(3)])


def _two(lab, m):
    """The mask's pixels sorted into two overall colours: (which of the two each pixel is, -1 outside; how far
    apart the two are in delta E; each one's share), or None when the mask holds too little."""
    if m.sum() < 200:
        return None
    cv2.setRNGSeed(0)
    _, labels, centres = cv2.kmeans(_from_afar(lab, m)[m].astype(np.float32), 2, None,
                                    (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5), 3,
                                    cv2.KMEANS_PP_CENTERS)
    which = np.full(m.shape, -1, np.int32)
    which[m] = labels.ravel()
    share = np.bincount(labels.ravel(), minlength=2) / len(labels)
    return which, float(np.linalg.norm(centres[0] - centres[1])), share


def _on_frame(m):
    """The share of the photo's edge the mask lies on."""
    edge = np.r_[m[0], m[-1], m[1:-1, 0], m[1:-1, -1]]
    return float(edge.mean())


def _two_kinds(lab, m) -> bool:
    """Does the mask hold two kinds of surface, each a fair share of it?"""
    two = _two(lab, m)
    return two is not None and two[1] >= APART and two[2].min() >= 0.12


def doubtful(img, mask) -> bool:
    """Does the first model's mask look like more or less than one garment? See-through inside its outline (a
    plaid's dark checks left out), running out of the photo's frame, or holding two kinds of surface (a dark
    jacket and the white duvet under it). Then the second model is worth asking (`settle`)."""
    mask = np.asarray(mask)
    if see_through(mask) > SEE_THROUGH:
        return True
    lab, m = _small(np.asarray(img.convert("RGB")), mask)
    if _on_frame(m) > OUT_OF_FRAME:
        return True
    return _two_kinds(lab, m)


def doubtful_cutout(cut, photo_size) -> bool:
    """`doubtful` for a cutout already made by the first model alone (an RGBA image, cropped from a photo
    `photo_size` = (width, height) across): would the second model have been asked? Its transparency is the
    first model's mask. The cutout is cropped with a margin, so where the garment touches the cutout's edge it
    touches the photo's: how far it runs out of the frame is that, against the photo's whole edge."""
    arr = np.asarray(cut.convert("RGBA"))
    alpha = arr[..., 3]
    if see_through(alpha) > SEE_THROUGH:
        return True
    touching = int((np.r_[alpha[0], alpha[-1], alpha[1:-1, 0], alpha[1:-1, -1]] > 128).sum())
    if touching / max(1, 2 * (photo_size[0] + photo_size[1]) - 4) > OUT_OF_FRAME:
        return True
    lab, m = _small(arr[..., :3], alpha)
    return _two_kinds(lab, m)


def settle(img, first, second, log=lambda s: None):
    """One mask from the two models' masks of the same photo (PIL "L" images; returns one).

    What both models keep is the garment. What only one of them keeps stays as it did before (the first model's
    always; the second's too when the first is see-through, which is how a plaid's missing checks are filled
    in), unless it is a different surface from the garment that runs out of the photo's frame: bedding, a
    floor, a wall. A sleeve only one model found is the garment's own cloth and stays; so does a part in
    another colour that lies inside the photo (a varsity jacket's sleeves)."""
    from PIL import Image
    a, b = np.asarray(first), np.asarray(second)
    base = np.maximum(a, b) if see_through(a) > SEE_THROUGH else a
    lab, ma = _small(np.asarray(img.convert("RGB")), a)
    _, mb = _small(np.asarray(img.convert("RGB")), b)
    core = ma & mb
    if core.sum() < 0.3 * min(ma.sum(), mb.sum()) or core.sum() < 200:
        return Image.fromarray(base, "L")       # the models found different things: nothing to go by
    k = max(3, int(0.03 * max(core.shape)) | 1)
    round_ = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    inside = cv2.morphologyEx(core.astype(np.uint8), cv2.MORPH_CLOSE, round_)
    near = cv2.dilate(inside, round_) > 0
    extra = ((ma | mb) & ~near).astype(np.uint8)
    extra = cv2.morphologyEx(extra, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, parts = cv2.connectedComponents(extra)
    afar = _from_afar(lab, ma | mb)
    garment = np.median(afar[core], 0)
    frame = np.zeros(core.shape, bool)
    frame[0], frame[-1], frame[:, 0], frame[:, -1] = True, True, True, True
    drop = np.zeros(core.shape, bool)
    for i in range(1, n):
        part = parts == i
        if part.sum() < 0.03 * core.sum():
            continue
        unlike = float(np.linalg.norm(np.median(afar[part], 0) - garment))
        out = float((part & frame).sum() / frame.sum())
        if unlike >= APART and out >= 0.03:
            log(f"left out a surface the garment lies on: {part.sum() / core.sum():.0%} of the garment's size, "
                f"{unlike:.0f} from its colour, on {out:.0%} of the photo's edge")
            drop |= part
    if not drop.any():
        return Image.fromarray(base, "L")
    # the dropped surface, and the thin band between it and the garment where only it reached
    drop = (cv2.dilate(drop.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1))) > 0)
    drop &= inside == 0
    full = cv2.resize(drop.astype(np.uint8) * 255, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_LINEAR)
    keep = cv2.GaussianBlur(255 - full, (0, 0), 1.5).astype(np.float32) / 255
    agreed = np.minimum(a, b).astype(np.float32)
    return Image.fromarray(np.clip(base * keep + agreed * (1 - keep), 0, 255).astype(np.uint8), "L")


def surfaces(cut, log=lambda s: None):
    """A cutout that holds two kinds of surface (a dark plaid jacket and the white duvet it lies on, kept by the
    background model), split into the two: each as the cutout with the other made see-through, the busier one
    (more edges: the patterned cloth) first. A cutout of one cloth comes back as it is, alone.

    Looked at from far enough that a pattern blurs into its overall colour, a plaid is one colour all over and
    a garment on bedding is two, in two places. Checks, stripes and prints do not split; nor does a shadow."""
    from PIL import Image
    arr = np.asarray(cut.convert("RGBA"))
    lab, m = _small(arr[..., :3], arr[..., 3])
    two = _two(lab, m)
    if two is None or two[1] < APART or two[2].min() < 0.12:
        return [cut]
    which, apart, share = two
    g = cv2.GaussianBlur(lab[..., 0].astype(np.float32), (0, 0), 1.0)
    edges = np.hypot(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1))
    order = sorted((0, 1), key=lambda i: -float(edges[which == i].mean()))
    log(f"the cutout holds two kinds of surface ({share[order[0]]:.0%} and {share[order[1]]:.0%} of it, "
        f"{apart:.0f} apart in colour): each is measured on its own, the busier first")
    f = max(1, max(arr.shape[:2]) // SMALL)
    out = []
    for i in order:
        part = cv2.resize((which == i).astype(np.uint8), (arr.shape[1], arr.shape[0]), interpolation=cv2.INTER_NEAREST)
        part = cv2.morphologyEx(part, cv2.MORPH_OPEN, np.ones((2 * f + 1, 2 * f + 1), np.uint8))
        one = arr.copy()
        one[..., 3] = np.where(part > 0, arr[..., 3], 0)
        out.append(Image.fromarray(one, "RGBA"))
    return out
