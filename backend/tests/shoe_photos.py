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
    stripes: tuple | None = None          # three slanted stripes on the quarter
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


def _ground_rest(shoe: Shoe, us):
    """The bottom line shifted so its lowest point touches the ground."""
    b = shoe.bottom(us)
    return b - b.min()


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
    top = shoe.top_line(us) - shoe.bottom(us) + bot
    sole_top = bot + shoe.sole(us)
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
        md.polygon(outline, fill=255)
        d.polygon(outline, fill=c(shoe.upper))
        if shoe.heel_counter:
            band = [p(u, s + 0.62 * (t - s)) for u, s, t in zip(us, sole_top, top, strict=True) if u <= 0.2]
            d.polygon([p(0, sole_top[0])] + band + [p(0.2, sole_top[48])], fill=c(shoe.heel_counter))
        if shoe.toe_cap:
            d.polygon([p(u, t + 0.5) for u, t in zip(us, top, strict=True) if u >= 0.82] + [p(1.0, 0), p(0.82, 0)],
                      fill=c(shoe.toe_cap))
        if shoe.stitching:
            j = np.argmin(abs(us - 0.79))
            for hh in np.arange(sole_top[j] + 0.3, top[j] - 0.3, 0.55):
                d.line([p(0.79, hh), p(0.79, min(hh + 0.32, top[j] - 0.3))], fill=c(shoe.stitching), width=max(1, int(0.13 * k)))
        if shoe.stripes:
            for i in range(3):
                u0 = 0.25 + i * 0.055
                d.line([p(u0, sole_top[int(u0 * 240)] + 0.2), p(u0 + 0.09, top[int((u0 + 0.09) * 240)] - 1.6)],
                       fill=c(shoe.stripes), width=int(0.85 * k))
        if shoe.laces:
            for i in range(5):
                u0 = 0.47 + i * 0.07
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
