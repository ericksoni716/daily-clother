"""Synthetic side-on shoe photos for the tracing tests (never real photos).

A shoe is built in centimetres, in the coordinates `closet.drawing.frontshoe` and the traced data use: u is the
share of the length from the heel (0) to the toe (1), heights are in cm above the ground, and the shoe is the
29.5 cm reference shoe. It is then drawn toe to the left at `px_per_cm` on a plain background, so what the
tracing recovers can be compared with what was drawn.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from closet.drawing import frontshoe

L = frontshoe.LENGTH
NAVY, WHITE, GREY, TAN, RED = (34, 52, 120), (242, 240, 234), (92, 92, 96), (196, 150, 98), (176, 40, 44)
SILVER, CREAM, GROUND = (196, 198, 204), (238, 226, 190), (206, 200, 190)


@dataclass
class Shoe:
    """What to draw. Colours are RGB; a part left as None is drawn in the upper's colour (or not at all)."""
    upper: tuple = NAVY
    midsole: tuple = WHITE
    outsole: tuple | None = GREY
    toe_cap: tuple | None = None
    heel_counter: tuple | None = None
    collar: tuple | None = None           # a padded collar: a band this colour along the top from the heel to the throat
    mudguard: tuple | None = None         # a panel along the upper's foot from u 0.55 round the toe, 40% of its height
    vamp: tuple | None = None             # the front of the upper, from u 0.45 to the toe, this colour (a two-colour upper)
    camo: tuple = ()                      # a busy upper: blotches of these colours scattered over it (the same every time)
    camo_count: int = 70                  # ... this many
    stripes: tuple | None = None          # three slanted stripes on the quarter
    stripe_cm: float = 0.85               # ... this wide
    stripe_gap: float = 0.055             # ... this far apart (a share of the length)
    stripe_taper: float = 0.0             # ... narrower at the top by this share (a real stripe tapers to the lacing)
    stripe_top_cm: float = 1.6            # ... ending this far below the top line
    laces: tuple | None = None
    eyelets: tuple | None = None
    stitching: tuple | None = None        # a dashed line along the toe cap's edge
    top: list = field(default_factory=lambda: list(frontshoe._LOW))   # (u, cm above the sole), as frontshoe's
    shaft_cm: float = 0.0                 # a boot's collar height above the ground (0 = a low shoe)
    sole_cm: float = 3.0                  # the sole's thickness at the heel ...
    sole_toe_cm: float = 2.2              # ... and at the toe
    outsole_cm: float = 0.9
    toe_spring_cm: float = 0.0            # how far the toe tip lifts off the ground
    rocker_cm: float = 0.0                # how far a curved outsole rises between heel and ball (a convex sole)
    heel_bevel_cm: float = 0.5            # how far the back of the heel lifts off the ground
    heel_tab_cm: float = 0.0              # a pull tab standing up and back from the heel's top, this tall
    window: tuple | None = None           # a see-through window in the midsole at the heel (an air unit), this colour
    lugs_cm: float = 0.0                  # a lug sole: the gaps between the lugs this deep
    gloss: bool = False                   # glossy leather: a highlight along the top edge
    lace_style: str = "bars"              # bars: one bar per lace; cross: the laces criss-cross, touching
    lace_count: int = 5
    toe_mark: tuple | None = None         # a round mark on the toe box, seen only from the front (`front_photo`)

    def bottom(self, u):
        """The sole's underside, cm above the ground."""
        u = np.asarray(u, float)
        b = np.zeros_like(u)
        b += np.where(u < 0.07, self.heel_bevel_cm * ((0.07 - u) / 0.07) ** 2, 0.0)
        b += np.where(u > 0.7, self.toe_spring_cm * ((u - 0.7) / 0.3) ** 2, 0.0)
        # a convex outsole: it sags lowest at u 0.4 and rises towards the heel and the ball
        b += np.where(u <= 0.7, self.rocker_cm * ((u - 0.4) / 0.3) ** 2, self.rocker_cm)
        return b - b[np.argmin(b)] if b.ndim else b

    def sole(self, u):
        return self.sole_cm + (self.sole_toe_cm - self.sole_cm) * np.asarray(u, float)

    def top_line(self, u):
        """The upper's top edge, cm above the ground."""
        u = np.asarray(u, float)
        t = np.array([frontshoe._interp(self.top, x) for x in np.atleast_1d(u)])
        out = self.bottom(u) + self.sole(u) + t
        if self.shaft_cm:
            out = np.maximum(out, np.where(u < 0.42, self.shaft_cm - 1.5 * u, 0.0))
        return out


# shoes the front view from a trace once got wrong (#205): their words for `Shoe`
BLACK, SUEDE, WHEAT, DARK_BROWN = (24, 24, 26), (150, 110, 75), (196, 150, 80), (50, 34, 24)
# black quarters, a red front, a black mudguard round the toe; a white midsole on a red outsole, a red air window
RED_BLACK_RUNNER = dict(upper=BLACK, vamp=RED, mudguard=BLACK, heel_counter=BLACK, laces=RED, midsole=WHITE, outsole=RED,
                        window=RED, sole_cm=3.6, sole_toe_cm=2.4, toe_spring_cm=1.0)
# a suede chukka whose collar stands a little lower than the tracing's boot threshold
LOW_CHUKKA = dict(upper=SUEDE, midsole=(70, 50, 35), outsole=None, top=list(frontshoe._BOOT), shaft_cm=11.5, sole_cm=1.8,
                  sole_toe_cm=1.5, laces=DARK_BROWN, eyelets=DARK_BROWN, lace_count=3)
# a wheat work boot with a dark padded collar and a lug sole
WORK_BOOT = dict(upper=WHEAT, midsole=(40, 34, 30), outsole=None, collar=DARK_BROWN, top=list(frontshoe._BOOT),
                 shaft_cm=16.5, sole_cm=3.0, sole_toe_cm=2.6, lugs_cm=0.5, laces=DARK_BROWN, eyelets=(180, 170, 150))
# a red and black runner on a thin white midsole, a red air window in it, over a thick black outsole
AIR_RUNNER = dict(upper=BLACK, vamp=RED, mudguard=BLACK, heel_counter=BLACK, laces=RED, midsole=WHITE, outsole=BLACK,
                  window=RED, sole_cm=3.6, sole_toe_cm=2.8, outsole_cm=2.6, toe_spring_cm=1.0)
# a navy derby sneaker, its laces navy too (they do not stand out in the photo, its eyelets do), a brown heel and collar
NAVY_DERBY = dict(upper=NAVY, heel_counter=(120, 80, 45), collar=(120, 80, 45), midsole=WHITE, outsole=(120, 80, 45),
                  laces=NAVY, eyelets=(120, 80, 45), sole_cm=2.6, sole_toe_cm=2.0, lace_count=4)
# a six-inch service boot laced to the top: its traced front stands as high as its collar (the tongue)
SERVICE_BOOT = dict(WORK_BOOT, shaft_cm=0.0, top=[(0.0, 15.0), (0.12, 15.2), (0.3, 15.2), (0.45, 16.4), (0.56, 15.8),
                                                  (0.63, 12.4), (0.7, 8.4), (0.85, 4.6), (0.95, 3.1), (1.0, 1.1)])
# a grey camouflage runner: many small blotches in three greys
BUSY_RUNNER = dict(upper=(128, 128, 130), camo=((70, 70, 72), (176, 176, 178), (32, 32, 34)), midsole=WHITE,
                   outsole=(40, 40, 42), laces=(30, 30, 32), sole_cm=3.4, sole_toe_cm=2.3)

# a light leather sneaker with a black heel counter and a black padded collar running along the top to the throat
DARK_COLLAR = dict(upper=(226, 226, 222), heel_counter=BLACK, collar=BLACK, laces=WHITE, midsole=WHITE,
                   outsole=(60, 60, 60), sole_cm=2.6, sole_toe_cm=2.2)
# a white court shoe with three red stripes and white laces: the stripes' ends cross the lacing's row in the photo
STRIPED_COURT = dict(upper=WHITE, midsole=WHITE, outsole=(214, 210, 200), stripes=(196, 30, 40), laces=WHITE,
                     sole_cm=2.6, sole_toe_cm=2.2)
# the same with three bold stripes, each just under a panel's size but together much of the side
BOLD_STRIPES = dict(STRIPED_COURT, stripe_cm=1.8, stripe_gap=0.105)
# as a real one is: a light grey court shoe, three thin stripes tapering up to the lacing, a black heel tab, laces
# in the upper's colour (drawn with noise, the stripes' edges blending into the upper)
REAL_STRIPES = dict(upper=(217, 217, 221), midsole=(210, 211, 213), outsole=(196, 196, 200), stripes=(177, 57, 67),
                    stripe_cm=0.8, stripe_taper=0.35, stripe_gap=0.06, stripe_top_cm=0.9, heel_counter=(40, 40, 43),
                    laces=(217, 217, 221), sole_cm=2.6, sole_toe_cm=2.2)


def _ground_rest(shoe: Shoe, us):
    """The bottom line shifted so its lowest point touches the ground (the lugs' gaps raised above it)."""
    b = shoe.bottom(us)
    b = b - b.min()
    if shoe.lugs_cm:
        phase = (us * L / 1.6) % 1.0
        b = b + np.where((phase > 0.55) & (us > 0.04) & (us < 0.96), shoe.lugs_cm, 0.0)
    return b


def draw(shoe: Shoe | None = None, *, px_per_cm: float = 26.0, size=(1000, 560), ground=GROUND, toe="left",
         tilt: float = 0.0, blur: float = 0.0, noise: float = 0.0, shade_edge: float = 0.0, gradient: bool = True,
         pair: tuple[float, float] | None = None, at: tuple[float, float] | None = None, ss: int = 3):
    """The shoe drawn on a plain background. `pair` (dx, dy as shares of the length and the height) draws a second
    shoe behind it, shifted back and up; `at` puts the toe tip and the ground (as shares of the photo).
    Returns the photo and the true mask (0/1) of everything that is shoe."""
    shoe = shoe or Shoe()
    w, h = size[0] * ss, size[1] * ss
    k = px_per_cm * ss
    us = np.linspace(0, 1, 241)
    bot = _ground_rest(shoe, us)
    base = shoe.bottom(us) - shoe.bottom(us).min()   # the bottom line without the lugs' gaps
    top = shoe.top_line(us) - shoe.bottom(us) + base
    sole_top = base + shoe.sole(us)
    tallest = float(top.max())
    tx, gy = at if at else ((size[0] - L * px_per_cm) / (2 * size[0]), (size[1] / 2 + tallest * px_per_cm / 2) / size[1])
    x_toe, y_ground = tx * w, gy * h
    bg = np.empty((h, w, 3), np.float32)
    bg[:] = ground
    if gradient:
        bg *= np.linspace(1.03, 0.96, h)[:, None, None]
    img = Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8))
    mask = Image.new("L", (w, h), 0)

    def one(dx_cm: float, dy_cm: float, dim: float):
        def p(u, hcm):
            return (x_toe + ((1 - u) * L + dx_cm) * k, y_ground - (hcm + dy_cm) * k)

        def c(col):
            return tuple(int(v * dim) for v in col)

        layer = Image.new("RGB", (w, h))
        lm = Image.new("L", (w, h), 0)
        d, md = ImageDraw.Draw(layer), ImageDraw.Draw(lm)
        outline = [p(u, t) for u, t in zip(us, top, strict=True)] + [p(u, b) for u, b in zip(us[::-1], bot[::-1], strict=True)]
        if shoe.heel_tab_cm:   # a pull tab: up from the heel's top, leaning back past the heel
            t0 = float(top[0])
            tab = [p(0.0, t0 - 1.6), p(-0.025, t0 + shoe.heel_tab_cm), p(0.035, t0 + shoe.heel_tab_cm + 0.1), p(0.07, t0 - 0.4)]
            md.polygon(tab, fill=255)
            d.polygon(tab, fill=c(shoe.upper))
        md.polygon(outline, fill=255)
        d.polygon(outline, fill=c(shoe.upper))
        if shoe.vamp:
            d.polygon([p(u, t + 0.1) for u, t in zip(us, top, strict=True) if u >= 0.45]
                      + [p(1.0, 0), p(0.45, sole_top[int(0.45 * 240)])], fill=c(shoe.vamp))
        if shoe.camo:   # blotches 1-3 cm across, each a few overlapping blobs, kept inside the upper by the mask
            rng = np.random.default_rng(11)
            for i in range(shoe.camo_count):
                u0 = float(rng.uniform(0.02, 0.97))
                h0 = float(rng.uniform(np.interp(u0, us, sole_top), np.interp(u0, us, top)))
                for _ in range(3):
                    du, dh, r = rng.normal(0, 0.5, 2).tolist() + [float(rng.uniform(0.5, 1.2))]
                    (xa, ya), (xb, yb) = p(u0 + (du - r) / L, h0 + dh + r * 0.7), p(u0 + (du + r) / L, h0 + dh - r * 0.7)
                    d.ellipse((min(xa, xb), ya, max(xa, xb), yb), fill=c(shoe.camo[i % len(shoe.camo)]))
        if shoe.heel_counter:
            band = [p(u, s + 0.62 * (t - s)) for u, s, t in zip(us, sole_top, top, strict=True) if u <= 0.2]
            d.polygon([p(0, sole_top[0])] + band + [p(0.2, sole_top[48])], fill=c(shoe.heel_counter))
        if shoe.collar:   # 1.8 cm deep, following the top line, so its lower edge runs parallel to the top
            band = [(u, t) for u, t in zip(us, top, strict=True) if u <= 0.5]
            d.polygon([p(u, t + 0.1) for u, t in band] + [p(u, t - 1.8) for u, t in band[::-1]], fill=c(shoe.collar))
        if shoe.mudguard:
            band = [p(u, s + 0.4 * (t - s)) for u, s, t in zip(us, sole_top, top, strict=True) if u >= 0.55]
            d.polygon(band + [p(1.0, 0), p(0.55, sole_top[int(np.argmin(abs(us - 0.55)))])], fill=c(shoe.mudguard))
        if shoe.toe_cap:
            d.polygon([p(u, t + 0.5) for u, t in zip(us, top, strict=True) if u >= 0.82] + [p(1.0, 0), p(0.82, 0)],
                      fill=c(shoe.toe_cap))
        if shoe.stitching:
            j = np.argmin(abs(us - 0.79))
            for hh in np.arange(sole_top[j] + 0.3, top[j] - 0.3, 0.55):
                d.line([p(0.79, hh), p(0.79, min(hh + 0.32, top[j] - 0.3))], fill=c(shoe.stitching), width=max(1, int(0.13 * k)))
        if shoe.stripes:
            for i in range(3):
                u0 = 0.25 + i * shoe.stripe_gap
                a, b = p(u0, sole_top[int(u0 * 240)] + 0.2), p(u0 + 0.09, top[int((u0 + 0.09) * 240)] - shoe.stripe_top_cm)
                if not shoe.stripe_taper:
                    d.line([a, b], fill=c(shoe.stripes), width=int(shoe.stripe_cm * k))
                    continue
                n = np.array([b[1] - a[1], a[0] - b[0]]) / np.hypot(b[0] - a[0], b[1] - a[1])
                wa, wb = shoe.stripe_cm * k / 2, shoe.stripe_cm * (1 - shoe.stripe_taper) * k / 2
                d.polygon([tuple(np.add(a, n * wa)), tuple(np.add(b, n * wb)), tuple(np.subtract(b, n * wb)),
                           tuple(np.subtract(a, n * wa))], fill=c(shoe.stripes))
        if shoe.laces and shoe.lace_style == "cross":   # each crossing an X, the Xs touching end to end
            step = 0.3 / shoe.lace_count
            for i in range(shoe.lace_count):
                ua, ub = 0.46 + i * step, 0.46 + (i + 1) * step
                ta, tb = float(np.interp(ua, us, top)), float(np.interp(ub, us, top))
                d.line([p(ua, ta - 1.7), p(ub, tb - 0.3)], fill=c(shoe.laces), width=int(0.3 * k))
                d.line([p(ua, ta - 0.3), p(ub, tb - 1.7)], fill=c(shoe.laces), width=int(0.3 * k))
        elif shoe.laces:
            for i in range(shoe.lace_count):
                u0 = 0.47 + i * 0.07 * 5 / shoe.lace_count
                t0 = float(np.interp(u0, us, top))
                d.line([p(u0 - 0.018, t0 - 0.35), p(u0 + 0.018, t0 - 1.5)], fill=c(shoe.laces), width=int(0.42 * k))
        if shoe.eyelets:
            r = 0.26 * k
            for i in range(6):
                u0 = 0.46 + i * 0.06
                x, y = p(u0, float(np.interp(u0, us, top)) - 2.2)
                d.ellipse((x - r, y - r, x + r, y + r), fill=c(shoe.eyelets))
        sole_poly = [p(u, s) for u, s in zip(us, sole_top, strict=True)] + [p(u, b) for u, b in zip(us[::-1], bot[::-1], strict=True)]
        d.polygon(sole_poly, fill=c(shoe.midsole))
        if shoe.outsole:
            d.polygon([p(u, b + shoe.outsole_cm) for u, b in zip(us, bot, strict=True)]
                      + [p(u, b) for u, b in zip(us[::-1], bot[::-1], strict=True)], fill=c(shoe.outsole))
        if shoe.window:   # an air unit: a rounded window in the midsole, rimmed in the midsole's colour
            j0, j1 = int(0.07 * 240), int(0.3 * 240)
            lo = float(bot[j0:j1].max()) + (shoe.outsole_cm if shoe.outsole else 0.0) + 0.35
            hi = float(sole_top[j0:j1].min()) - 0.4
            (xa, ya), (xb, yb) = p(0.3, hi), p(0.07, lo)
            d.rounded_rectangle((xa, ya, xb, yb), radius=0.4 * k, fill=c(shoe.window))
            d.line([(xa + 0.3 * k, ya + 0.25 * k), (xb - 0.3 * k, ya + 0.25 * k)], fill=c((235, 238, 242)), width=max(1, int(0.12 * k)))
        if shoe.gloss:   # a highlight along the top edge, where glossy leather turns towards the light
            line = [p(u, t - 0.32) for u, t in zip(us, top, strict=True) if 0.01 < u < 0.97]
            d.line(line, fill=c(tuple(min(255, v + 90) for v in shoe.upper)), width=max(1, int(0.18 * k)))
        # round the corners as a real shoe's are: the mask is smoothed and the layer kept inside it
        lm = lm.filter(ImageFilter.GaussianBlur(0.35 * k)).point(lambda v: 255 if v > 127 else 0)
        return layer, lm

    if pair:
        dx, dy = pair[0] * L, pair[1] * tallest
        layer, lm = one(dx, dy, 0.88)
        img.paste(layer, (0, 0), lm)
        mask.paste(255, (0, 0), lm)
    layer, lm = one(0.0, 0.0, 1.0)
    img.paste(layer, (0, 0), lm)
    mask.paste(255, (0, 0), lm)
    arr = np.asarray(img).astype(np.float32)
    if shade_edge:   # a rounded surface turns away from the light at its silhouette: darker just inside the edge
        inside = np.asarray(mask) > 0
        import cv2
        dist = cv2.distanceTransform(inside.astype(np.uint8), cv2.DIST_L2, 5)
        fall = np.clip(1 - dist / (0.45 * k), 0, 1) * shade_edge
        arr -= fall[..., None]
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).resize(size, Image.LANCZOS)
    mask = mask.resize(size, Image.LANCZOS)
    if toe == "right":
        img, mask = img.transpose(Image.FLIP_LEFT_RIGHT), mask.transpose(Image.FLIP_LEFT_RIGHT)
    if tilt:
        img = img.rotate(tilt, resample=Image.BICUBIC, fillcolor=ground)
        mask = mask.rotate(tilt, resample=Image.BILINEAR, fillcolor=0)
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    if noise:
        rng = np.random.default_rng(7)
        a = np.asarray(img).astype(np.float32) + rng.normal(0, noise, (size[1], size[0], 3))
        img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    return img, (np.asarray(mask) > 127).astype(np.uint8)


def front_view(size=(600, 600)) -> Image.Image:
    """A shoe seen from the front: about as tall as wide, toe and heel alike."""
    img = Image.new("RGB", size, GROUND)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((220, 150, 380, 470), 60, fill=NAVY)
    d.rectangle((210, 440, 390, 480), fill=WHITE)
    return img


def front_photo(shoe: Shoe | None = None, *, px_per_cm: float = 30.0, size=(600, 640), ground=GROUND):
    """The same shoe seen from the front, toe nearest the camera (a second photo, #205): its sole across the
    bottom, the toe box rounded over it, the instep and its lacing rising behind to the opening (or a boot's
    shaft). Returns the photo and its true mask (0/1)."""
    shoe = shoe or Shoe()
    img = Image.new("RGB", size, ground)
    mask = Image.new("L", size, 0)
    d, m = ImageDraw.Draw(img), ImageDraw.Draw(mask)
    k, cx, yg = px_per_cm, size[0] / 2, size[1] - 70
    w = 5.0 * k
    sole_top = yg - shoe.sole_toe_cm * k
    upper = shoe.vamp or shoe.upper
    throat = sole_top - (shoe.shaft_cm - shoe.sole_cm if shoe.shaft_cm else 8.0) * k
    neck = 3.4 * k

    def both(kind, xy, colour, **kw):
        getattr(d, kind)(xy, fill=colour, **kw)
        getattr(m, kind)(xy, fill=255, **kw)

    # the instep and the shaft, behind the toe box; the opening at its top
    both("polygon", [(cx - w + 0.5 * k, sole_top), (cx - neck, throat), (cx + neck, throat), (cx + w - 0.5 * k, sole_top)],
         shoe.upper if shoe.shaft_cm else upper)
    if shoe.collar:
        both("rounded_rectangle", (cx - neck, throat - 0.6 * k, cx + neck, throat + 1.2 * k), shoe.collar, radius=0.6 * k)
    both("ellipse", (cx - neck + 0.5 * k, throat - 0.6 * k, cx + neck - 0.5 * k, throat + 0.9 * k), (40, 34, 30))
    # the lacing up the middle of the instep
    lace_top, lace_bottom = throat + 1.6 * k, sole_top - 4.2 * k
    if shoe.laces and lace_bottom > lace_top:
        n = shoe.lace_count
        for i in range(n):
            y = lace_top + (lace_bottom - lace_top) * i / max(1, n - 1)
            d.rectangle((cx - 1.3 * k, y - 0.22 * k, cx + 1.3 * k, y + 0.22 * k), fill=shoe.laces)
    # the toe box, nearest: its lower band a mudguard's colour, when it has one
    box = (cx - w + 0.3 * k, sole_top - 5.0 * k, cx + w - 0.3 * k, sole_top + 4.0 * k)
    both("ellipse", box, shoe.toe_cap or upper)
    if shoe.mudguard:
        band = Image.new("L", size, 0)
        ImageDraw.Draw(band).rectangle((0, sole_top - 1.6 * k, size[0], size[1]), fill=255)
        toe = Image.new("L", size, 0)
        ImageDraw.Draw(toe).ellipse(box, fill=255)
        img.paste(shoe.mudguard, (0, 0), Image.fromarray(np.minimum(np.asarray(band), np.asarray(toe))))
    if shoe.toe_mark:   # a round mark on the toe box, a little to one side
        d.ellipse((cx + 0.6 * k, sole_top - 3.0 * k, cx + 2.2 * k, sole_top - 1.9 * k), fill=shoe.toe_mark)
    if shoe.stripes:   # three slanted stripes on each side of the front, near its edges
        for side in (-1, 1):
            for j in range(3):
                x = cx + side * (w - 1.3 * k - j * 0.7 * k)
                d.polygon([(x - 0.2 * k, sole_top - 0.3 * k), (x + 0.2 * k, sole_top - 0.3 * k),
                           (x + 0.2 * k + side * 0.6 * k, sole_top - 3.2 * k), (x - 0.2 * k + side * 0.6 * k, sole_top - 3.2 * k)],
                          fill=shoe.stripes)
    # the sole across the bottom: the outsole under the midsole
    both("rounded_rectangle", (cx - w, sole_top, cx + w, yg), shoe.midsole, radius=0.8 * k)
    if shoe.outsole is not None:
        d.rounded_rectangle((cx - w, yg - shoe.outsole_cm * k, cx + w, yg), fill=shoe.outsole, radius=0.6 * k)
    return img, (np.asarray(mask) > 127).astype(np.uint8)
