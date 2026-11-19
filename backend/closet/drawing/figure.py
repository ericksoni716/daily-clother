"""An outfit drawn as worn: the layered figure.

One front view of a whole outfit, worn by a person drawn in the garments' own
flat style (`_body`): head, neck, arms, hands, legs and feet, about 7.5 heads
tall (HEAD_CM), an average, healthy build (the shoulder points 2.7 head widths
apart, the hips 2, the neck six tenths as wide as the head and flaring into
sloping shoulders), standing front-on. The arms hang as a standing man's do
(`_arm_points`): from a round shoulder the upper arm goes a little out from the
body to the elbow, the forearm straight down from there, the arm tapers all the
way, the wrists are level with the crotch and the fingertips at mid-thigh. A
regular top's body stands just behind them, and a soft roomy one goes round
behind them; a stiff roomy one (a jacket, a coat) holds the elbows and hands a
little off it (`_spread`, ARM_OUT, at most ARM_OUT_MAX_CM), and what is on its
front lies nearer the middle (FRONT_IN), so its pockets are in front of them. A
bare foot (in a sandal, or with no shoes) is one shape with its leg. The skin is
one colour, SKIN, read from this one place; it is drawn first, behind every
garment, so it shows only where nothing covers it: the face and neck, the hands
below the cuffs, the forearms below short sleeves, the legs below shorts, the
ankles in low shoes and the feet in sandals. The head has a simple face (eyes,
brows, a hint of nose and mouth).

The body sets the proportions, and each garment is fitted to it here only.
Every piece is drawn by the same templates and renderer as the item drawings,
from the same description, but the item drawings are fashion flats (long
sleeves, a wide body), so the shape the template builds is moved point by point
onto the wearer (`fitting.warp`) before it is drawn (`illustrate._draw(...,
shape=)`); the item drawings themselves do not change:

- A top (`_fit_top`): its body is scaled about the middle so a regular top's
  shoulder seam lands on his shoulder point (SHOULDER_HALF_CM), and its hem
  lands on the body landmark its length goes to (HEM_AT: a cropped top at the
  waist, still over the waistband; a regular one at the hip; a longline one
  below it; a coat at the hip, just above the knee when long, or the knee), a boxy one a little
  shorter and an oversized one longer (FIT_LONGER_CM). A fuller fit stays
  fuller (FIT_GAIN), comes in high on the chest to fall straight
  (FULLER_ROOM_PER_FIT, STIFF_ROOM_PER_FIT, FULL_IN: what is on its front keeps
  its shape), and its
  shoulder rounds over the top of the arm (DROP_ROUND_CM), the sleeve hanging
  from the seam with no puff (DROP_EASE_SHARE); a regular or relaxed one falls straight from the chest
  with room at the sides (FIT_ROOM_CM); a slim or tailored one is shaped in at the waist
  (SHAPED_EASE), but no top is narrower than he is (BODY_EASE_CM,
  MIN_HIP_EASE_CM). Each sleeve goes round the arm and bends with it
  (`_on_arm`), its top rounding off the shoulder's slope (CAP_CM), with ease by
  its fit (SLEEVE_EASE), narrowing to the cuff; it ends where its length goes
  (SLEEVE_ENDS: short halfway down the upper arm, elbow, three-quarter, long
  round the wrist, a jacket's or coat's PAST_WRIST_CM past it). Where a sleeve
  hangs against the body's side the two share one line (SLEEVE_SHARE_CM), and
  part quickly where they part (APART_RAMP); where the body lies against the
  arm the sleeve's cloth between them is pressed flat (PRESSED_EASE_CM). An oversized top
  with a ribbed hem and cuffs falls straight, its hem band and cuffs gathering
  it in. A hood lies on the shoulders behind the neck. The base top is closed. A mid or outer layer
  that opens all the way down the front is worn open over what is under it;
  one that does not (a pullover, a hoodie) is worn closed, and of what is under
  it only what would really show is drawn: below its hem, above its neck,
  inside its neck opening, and the under sleeves where its own sleeves are
  shorter. Three layers nest the same way.
- Trousers (`_fit_bottom`): scaled across to his waist (BOTTOM_SX), the waist on
  his waist, the crotch at his crotch, and the hem placed on the shoe in 3D
  (`_hem`): a leg whose opening is narrower than the shoe round its opening
  rests on top of it (just in front of a low shoe's opening, or on top of a
  boot's shaft, bunching out to cover it), by its break; a wider one
  (OVER_SHOE) drops over it, but its front is held up behind the vamp; an
  ankle length stops above the shoe, the ankle or sock showing. With no shoe a
  full-length hem rests BREAK_CM above the ground, dipping DIP_CM. Each leg is
  narrowed or widened about its middle by its shape (LEG_EASE): a slim leg
  tapers to the hem, a straight one falls straight, a wide one stays wide.
- The shoes stand on the ground as a pair, seen from the front (`frontshoe`),
  toes forward and a little out, each ankle centred under its trouser leg (the
  viewer's right one mirrored); a hem dropping over the shoe hides what is
  under it, and nothing of the shoe shows beside the leg above the hem.
- A shoe Claude drew from its photos (`drawn`, step D) is drawn in place of that
  front view, placed by it (`_drawn_place`): the drawing's frame scaled so its
  leg is as wide as the figure's ankle, its middle on each ankle, its ground on
  the front view's lowest point, its ink lines as thick as the figure's
  (`drawn.thicken`). The toe turns out as far as the front view's does, by
  sliding the part below a hinge sideways (a shear; a low shoe's opening front,
  a boot's instep), so the collar or the shaft stays upright round the leg. The
  viewer's right shoe is the left one mirrored, unless there is a right drawing.
  Its part behind the leg is drawn before the wearer, so the leg covers it; its
  part in front where the front view would be. The hem rests on the drawing's
  own opening (`_on_drawing`), and full-length trousers keep their own length:
  never longer than to just meet an ordinary sneaker's collar (SNEAKER_RIM), so
  above a lower shoe the sock shows (drawn under them for that).
- Accessories (`pieces["accessories"]`, a list) go by the point each template is
  drawn about, at K_PX: a belt is worn round the trousers' waistband, and the
  first top is then worn tucked in (its body cut off at the belt, its sleeves
  kept), so the belt shows over it and under any layer worn over it; a scarf at the neck point,
  over every top, a long one wrapped round the neck at its depths. A hat goes on his head and a bag is carried as its kind is
  (in the hand, over the shoulder, on the back): `worn.place` places them, and
  `worn` draws the bag with its straps; with no wearer drawn, a hat's band is at
  HAT_Y and a bag beside the figure on the viewer's right, its handle at the
  height of a hand. One of each is drawn (the first given). A tie, a
  pocket square, a watch, glasses and socks are drawn by `worn`, which `_svg`
  calls once; gloves, jewellery and other accessories are not drawn in the figure.

Every garment is a shell round him, seen from the front and flattened, so it is
painted in depth order, back to front (`_svg`): the back of the garments where
it shows (a hood, the inside back of an open layer, the back of a scarf's loop);
the body, the shoes and the trousers (a drawn shoe's part behind the leg before
the body); the tops from the inside out, each one
whole; then the arms again (`_arms_over`), over what of a loose body stands out
past his sides (it is at his side or back, behind the arm hanging beside him),
from below the lowest sleeve opening and never inside a sleeve; each top's
sleeves are drawn again over its own body (`_sleeves_over`), tubes round the
arm, the arm coming out of the opening, a wide opening showing a little of its
inside (TUBE_INSIDE_CM); the neck and head; the bag's straps; a wrapped scarf's
hanging ends and the band across the throat (`templates.SCARF_LAYERS`); the hat.
Between an open layer's fronts is what is in front of its back: he is drawn
again within its outline (and his trousers and shoes), then the layers under it.

`figure(pieces)` never raises: a missing place is not drawn, a piece of the
wrong kind for its place is left out, a piece that cannot be drawn falls back
to the plainest drawing of its category, and if even that fails it is left out.
"""
from __future__ import annotations

import logging
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from . import drawn, fitting, item, templates, worn
from .fills import Graphic
from .frontshoe import FrontShoe, bare_feet, front_shoe
from .illustrate import CARD, INK, Fill, Spec, _draw, luminance, shade
from .templates import CX, K_PX, LEG_WIDTHS, PX_CM, TOP_DEFAULTS, Shape, _block_for, build

log = logging.getLogger("closet.drawing")

PLACES = ("base", "mid", "outer", "bottom", "shoes")
ACCESSORY_PLACE = {"belt": "belt", "scarf": "scarf", "bag": "bag", "cap": "hat", "beanie": "hat", "brimmed_hat": "hat"}
ACCESSORY_ORDER = ("belt", "scarf", "hat", "bag")
WRAPPED_SCARVES = ("woven", "knit", "silk")   # drawn wrapped round the neck (templates.SCARF_LAYERS); others as flat
TOP_PLACES = ("base", "mid", "outer")
PLACE_TEMPLATE = {"base": "top", "mid": "top", "outer": "top", "bottom": "pants", "shoes": "sneaker"}
PLACE_CATEGORIES = {"base": item.TOPS, "mid": item.TOPS, "outer": item.TOPS, "bottom": item.BOTTOMS, "shoes": item.SHOES}
# fronts that open all the way down; worn as a mid or outer layer they are drawn open
OPENS = ("buttons", "french", "hidden", "double", "zip")
SLEEVE_RANK = {"none": 0, "short": 1, "elbow": 2, "three-quarter": 3, "long": 4}

# the wearer: an adult man 7.5 heads tall, standing front-on, drawn in the garments' own line and flat fills. He
# sets the proportions: every garment is fitted to him (`_fit_top`, `_fit_bottom`). Heights are in cm below the
# top of the head, widths in cm either side of the middle; the figure is drawn at K_PX pixels per cm.
SKIN = "#c68e6a"              # the skin's colour: the one place it is read from (a Settings choice can set it later)
SKIN_LINE = shade(SKIN, -0.32)   # the lines drawn on skin: fingers, ears, toes, nose and mouth
TOE_LINE = SKIN_LINE
HAIR = "#3b2e27"
EYE = "#2b211c"
LINE = 3.8                    # the body's outline, as wide as a garment's (illustrate's "line" style)
HEAD_CM = 24.0                # the top of the head to the chin: one head, of the 7.5
HEADS = 7.5
NECK_CM = 30.0                # the base of the neck, where a top's neckline sits (its "neck" anchor)
# an average, healthy build: the head is 16 cm wide, the neck six tenths of that, the shoulder points 2.7 head widths
# apart and the hips 2, so he is clearly broader at the shoulders than the hips, with a chest between
NECK_HALF_CM = 4.8
SHOULDER_CM, SHOULDER_HALF_CM = 36.5, 21.5   # the shoulder points, where a top's shoulder seam lands; they slope
CHEST_CM, CHEST_HALF_CM = 49.0, 14.6         # the chest under the arms: inside the slimmest top
WAIST_CM, WAIST_HALF_CM = 71.0, 14.5         # where trousers' waistband sits
HIP_CM, HIP_HALF_CM = 84.0, 15.8
CROTCH_CM = 94.0
KNEE_CM = 132.0
GROUND_CM = HEADS * HEAD_CM   # 180 cm
# the arms hang as a standing man's do: from a round shoulder the upper arm goes a little out from the body to the
# elbow, at the waist; the forearm goes straight down from there to the wrist, level with the crotch; the fingertips
# reach the middle of the thigh. The arm is thickest at the shoulder and tapers to the wrist.
WRIST_CM = 96.0
ELBOW_CM = 68.0
ARM_IN_CM, ARM_DOWN_CM = 2.0, 5.0   # the shoulder joint (the top of the arm's middle): in from the shoulder point, under it
UPPER_ARM_DEG = 5.0          # the upper arm hangs this far out from straight down: close to a relaxed hang
FOREARM_DEG = 0.0             # and the forearm this far: it comes back in, to straight down, so the hands clear the hips
ELBOW_BEND_CM = 8.0           # the bend at the elbow is rounded over this much of the arm either side of it
# how thick the arm is (half its width), by how far down it from the shoulder joint (cm): the shoulder cap, the
# round of the shoulder, the upper arm, the elbow, the thick of the forearm, the wrist
ARM_HALVES = [(0.0, 4.6), (7.0, 4.9), (13.0, 4.8), (27.5, 3.9), (34.0, 4.1), (54.0, 2.8)]
ARMPIT_CM = 55.0              # where a sleeve's underarm sits on him (a flat drawing's armhole is deeper)
ARM_OUT, ARM_OUT_MAX_CM = 1.0, 2.0   # a stiff top (a jacket, a coat, a heavy overshirt) roomier than a regular one
                              # holds the elbows (and the hands) off it by this much for each cm its body reaches past a
                              # regular top's, up to this much; soft cloth does not, and its roomy sides go round behind
                              # the arms
HAND_SCALE = 0.9              # the hand (HAND, drawn 16.5 cm long) is drawn as long as his face, chin to hairline
LEG_TOP_HALF_CM = 8.2         # the top of each leg (inside the trousers), from the middle
THIGH_HALF_CM, KNEE_HALF_CM, CALF_HALF_CM = 7.6, 5.6, 5.8
CALF_CM = 146.0
LEG_INTO_CM = 1.5             # the leg runs this far on past the ankle, into the foot or the shoe drawn there

# fitting a garment's flat drawing onto him
WORN_W = 0.68                 # a garment's front, worn, is this share of its flat width (the rest wraps round)
# a sleeve's width is the arm's and some ease, by the top's fit (not the width its flat drawing has): how far it
# stands off the arm either side (cm) at the upper arm, and at a long sleeve's cuff; it tapers from one to the other
# (the fuller of the two: by its fit, and for a jacket or coat by the layers it goes over)
SLEEVE_EASE = {"slim": (0.45, 0.5), "regular": (1.2, 0.65), "relaxed": (2.0, 0.85), "boxy": (2.3, 0.9),
               "outer": (1.8, 1.0), "coat": (2.3, 1.3), "roomy": (2.8, 1.0)}
SLEEVE_FIT = {"slim": "slim", "tailored": "slim", "relaxed": "relaxed", "boxy": "boxy", "oversized": "roomy"}
# where a sleeve ends on him, by its length (cm below the crown): a short sleeve halfway down the upper arm (from the
# underarm to the elbow), an elbow sleeve at the elbow, a three-quarter one halfway down the forearm, a long one round
# the wrist
SLEEVE_ENDS = {"short": 61.0, "elbow": ELBOW_CM + 1.5, "three-quarter": 82.0, "long": WRIST_CM}
ROOMY_SHORT_CM = ELBOW_CM - 0.5   # an oversized top's short sleeve: a wide tube down to just above the elbow
SHORT_SLEEVE_MORE_CM = 0.4    # a short sleeve's opening stands this much further off the arm than its top
SHORT_SHARE = 0.55            # a sleeve shorter than this share of a long one is a short sleeve: it stops where it stops
CUFF_FROM, CUFF_TO = 0.8, 0.9   # a roomy sleeve is gathered in between these shares of its length; the cuff is below
SLEEVE_SHARE_CM = 2.4         # a sleeve closer to the body's side than this is drawn on it: one line, not two (0: never)
APART_RAMP = 0.4              # ...and once further, it is drawn where it is within this share of that again: no long
                              # narrow sliver between the two lines
SEAM_W = 1.4                  # a sleeve's armhole seam on the figure: a thin line, as the seams on a garment
UNDERARM_EASE_CM = 14.0       # a sleeve's inner edge has no ease at the underarm (the cloth is held between the arm and
                              # his side): it comes to its full ease this far down the sleeve, or at its opening if sooner
PRESSED_EASE_CM = 0.3         # ...and where the top's body lies against the arm, its cloth is pressed flat between them:
                              # the sleeve's inner edge stands only this far off the arm, beside the body's side
DROP_EASE_SHARE, DROP_EASE_CM = 0.25, 12.0   # a dropped shoulder's sleeve hangs from its seam: its outer edge stands
                              # this share of its ease off the arm there, and all of it this far down the sleeve (no
                              # puff out past the seam)
CAP_CM = 7.0                  # a sleeve's outer edge rounds from the shoulder's slope onto the arm over this much of it
SHOULDER_SLOPE_DEG = 20.0     # the slope of a top's shoulder line, out from the neck, where it meets the sleeve
HEAD_SHARE = 0.25             # the round of a sleeve's head, wider than the sleeve, is kept this share of the way down
SHARE_IN = 0.6                # ...just inside it (px), so nothing shows between the two
FIT_GAIN = 1.0                # a fuller fit than regular is drawn this much fuller again (as a power of how much fuller)
HIP_EASE_CM = 1.8             # how far a regular top's body stands off his hips at its hem
EASE_PER_FIT = 13.0           # ...less by this for each unit narrower its fit is on the flat drawing, to MIN_HIP_EASE_CM
FULLER_ROOM_PER_FIT = 27.0    # a fuller top's body falls straight, as far off his chest as a regular one's (FIT_ROOM_CM)
                              # and this much further for each unit fuller its fit is on the flat drawing (soft cloth,
                              # its sides behind the arms)
STIFF_ROOM_PER_FIT = 13.0     # ...a stiff one's this much further: it keeps its shape, and the arms rest on its sides
FRONT_IN, FRONT_KEEP = 0.9, 0.88   # on a stiff top roomier than a regular one, what is on the front (a pocket) lies this
                              # much nearer the middle, as its front curves round toward his sides; the last of each
                              # side (past this share of the way out) is drawn out to the side, behind the sleeve
FULL_IN = 0.7                 # a fuller top's body comes in to that from its shoulders, by this share of the way down to
                              # its underarm, and falls straight from there: what is on its front (a pocket) keeps its shape
MIN_HIP_EASE_CM = 1.2          # (the slimmest top still hangs over the trousers' hips)
HOOD_ABOVE = 0.42             # a hood worn down stands this much as high above the neck as on its flat drawing
HOOD_SHOWS = 80.0             # how far either side of the middle a hood shows above a layer worn over it (flat px)
HOOD_WIDE = 1.25              # ...and lies this much wider, out over the shoulders behind the neck
HEM_GATHER = 0.07             # a roomy top's ribbed hem band draws its body in this much
HEM_GATHER_CM = 7.0           # ...over this much of its length above the band (and the band is this deep)
UNDERARM_IN = 0.86            # a top's body, from the underarm down, is drawn this much narrower than its shoulders
BODY_EASE_CM = 1.0            # the least a top's sides stand off his, below the underarm
FIT_ROOM_CM = {"regular": 4.5, "relaxed": 6.5}   # a regular or relaxed top falls straight from the chest, its sides
#                                                  this far off his chest all the way down
DROP_ACROSS, DROP_DOWN = 0.55, 0.8   # a shoulder seam past his shoulder point: this much of the way out, and down
DROP_ROUND_CM = 5.0           # ...rounding over his shoulder point from the shoulder's slope into that drop over this much
PAST_WRIST_CM = 1.5           # a jacket's or coat's sleeve runs this far past the wrist
SLEEVE_SPLIT = 7.0            # a top's straight edges are cut into pieces this long (px), so a sleeve bends at the elbow
OUTER_BLOCKS = ("outer", "bomber", "jacket", "coat")
# a top's length: cm below the neck on the flat drawing -> on him. Only where its underarm lands is taken from this
# (a regular top's), so every top's chest sits alike; its hem is put on HEM_AT.
TOP_LENGTH = [(0.0, 0.0), (55.0, WAIST_CM - NECK_CM + 10.0), (78.0, 61.0), (113.0, KNEE_CM - NECK_CM + 2.0)]
# where a top's hem lands on him (cm below the crown), by the body landmark its length goes to: a cropped top just
# below the waist (still over the trousers' waistband, so no skin shows), a regular one at the hip (below its widest),
# a longline one below the hip, over the seat; a long coat at the thigh, a knee-length one at the knee
HEM_AT = {"waist": WAIST_CM + 11.0, "hip": HIP_CM + 5.0, "below_hip": CROTCH_CM + 7.0,
          "thigh": (CROTCH_CM + KNEE_CM) / 2, "above_knee": KNEE_CM - 6.0, "knee": KNEE_CM + 2.0}
TOP_REACHES = {"cropped": "waist", "regular": "hip", "long": "below_hip", "knee": "knee"}
JACKET_REACHES = {"cropped": "waist", "regular": "hip", "long": "thigh", "knee": "knee"}   # a jacket
COAT_REACHES = {**JACKET_REACHES, "long": "above_knee"}   # a coat: a long (longline) one well down the thigh
FIT_LONGER_CM = {"boxy": -4.0, "oversized": 6.0}   # a boxy top is a little shorter, an oversized one longer
# a slim or tailored top is shaped at the waist: how far its sides stand off his (cm), at the underarm, the waist and
# the hips
SHAPED_EASE = [(ARMPIT_CM, 2.4), (WAIST_CM, 0.4), (HIP_CM, 1.2)]
# a trouser leg, scaled across about its own middle by its leg shape: by this at the knee and at the hem (from none
# at the crotch), so a slim leg narrows to its hem, a straight one falls straight and a wide one stays wide. Taken
# from the trousers template's own knee and opening widths for each shape (templates.LEG_WIDTHS), against a
# straight leg's, to these powers (at the knee, at the hem): the figure shows the same shapes, more strongly than the
# flat drawing, and more at the hem, so a slim leg tapers more than a straight one
LEG_GAIN = (0.35, 0.55)
LEG_MIN_HALF_CM = 4.6         # ...but never narrowed to less than this either side of its middle: room for his ankle
LEG_EASE = {leg: ((kn / LEG_WIDTHS["straight"][0]) ** LEG_GAIN[0], (op / LEG_WIDTHS["straight"][1]) ** LEG_GAIN[1])
            for leg, (kn, op) in LEG_WIDTHS.items()}
TROUSER_WAIST_HALF_CM = 15.5  # a regular trouser waist, worn (a 41 cm flat waist): his waist and a little ease
TROUSER_HIP_HALF_CM = 16.8    # and its hips (50 cm flat), over his, from the hips down
FLAT_HIP_CM, FLAT_HIP_HALF_CM = 18.8, 25.0   # the trousers template's regular hips: below the waist, and half wide
BREAK_CM = 5.0                # a full-length trouser hem rests this far above the ground, on the shoe
DIP_CM = 2.0                  # the break: a full-length hem falls this much lower over the instep than at its sides
TOE_CM = 7.0                  # seen a little from above, the toes stand forward of the legs: lower on the page by this
RISE_CM, INSEAM_CM = 27.0, 81.0   # the trousers template's regular front rise and full inseam
# where a full-length hem meets the shoe (`_hem`), from the two as solids: a leg whose opening (flat) is at least
# this many times as wide as the shoe round its opening (a low shoe's collar, a boot's shaft) drops over it; a
# narrower one rests on top of it: relaxed, bootcut and wide legs go over a low shoe, only bootcut and wide over a boot
OVER_SHOE = 2.35
# how far the hem's front edge comes down past the shoe's opening (or a wide leg's past the instep), by the break:
# no break ends at the opening, a slight break just touches the shoe, a full one rests on it with a fold
HEM_FRONT_CM = {"none": 0.3, "slight": 0.8, "full": 1.3, "stacked": 1.3}
STACK = {"none": "slight", "slight": "full", "full": "stacked"}   # a leg resting on top of a boot's shaft bunches there
ARCH_CM = 3.0                 # a leg dropping over the shoe: its sides fall up to this much lower than its front
CROP_GAP_CM = 3.0             # a cropped hem stops at least this far above the back of the shoe's opening
REST_DIP_CM = 1.2             # resting on the shoe, a hem's front is this much lower than its sides (its opening's tilt)
BUNCH_EASE_CM, BUNCH_CM = 0.5, 7.0   # a leg resting on a boot's shaft is this much wider than it, over this much above its hem
DRAWN_ABOVE = 30.0            # a drawn shoe's frame: how far above the back of its opening something may still show (a
#                               pull tab, the collar's sides), for the canvas only
SNEAKER_RIM = 50.0            # a drawn shoe's frame: an ordinary low sneaker's collar front is at this y; full-length
#                               trousers over a drawn shoe are never longer than to just meet it, so a lower shoe shows
#                               the sock (the frame's leg is drawn.LEG, its ground drawn.GROUND)
MARGIN = 18.0                 # the same space on every side of the figure

NECK_Y = 82.0                 # the base of the neck, in the figure
CROWN_Y = NECK_Y - NECK_CM * K_PX


def _y(cm: float) -> float:
    """A height on him, in the figure."""
    return CROWN_Y + cm * K_PX


SHOULDER_Y, WAIST_Y, CROTCH_Y, GROUND_Y = _y(SHOULDER_CM), _y(WAIST_CM), _y(CROTCH_CM), _y(GROUND_CM)
HEM_Y = GROUND_Y - BREAK_CM * K_PX
CHIN_Y = _y(HEAD_CM)
BOTTOM_SX = TROUSER_WAIST_HALF_CM * K_PX / (20.5 * PX_CM)   # trousers' flat drawing to the figure, across, at the waist
HIP_SX = TROUSER_HIP_HALF_CM * K_PX / (FLAT_HIP_HALF_CM * PX_CM)   # ...and from the hips down
LEG_CM = 12.5 * PX_CM * HIP_SX / K_PX   # the middle of each leg, from the middle: where a straight leg's hem is
BELT_HALF_CM = TROUSER_WAIST_HALF_CM - 0.3   # a worn belt, either side of its buckle: the trousers' waist as drawn
BELT_Y = WAIST_Y + 1.7 * K_PX   # the middle of the waistband
HAT_Y = CROWN_Y + 9.0 * K_PX  # where a hat's crown meets its brim, on the head
BAG_GAP_CM = 5.0              # between the bag and the figure
TUBE_INSIDE_CM = 0.9          # how deep the inside of a sleeve shows below its opening, beside the arm
EDGE = 2.5                    # half the drawn outline's width, in pixels: a body's edge is drawn this far outside it
TUCK_CM = 9.0                 # a top tucked in is drawn in to the belt's width over this much above the belt
NECK_IN_CM = 4.5              # how far the neck is drawn on down inside a top's neck opening, over its back


def _arm_points(side: int = -1, spread: float = 0.0) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
    """The middle of an arm, in the figure: the shoulder joint, the elbow and the wrist. `side` -1 is the viewer's
    left. `spread` (cm) is how much further out the elbow is held, by a full top's body (`_spread`)."""
    k = K_PX
    j = (CX + side * (SHOULDER_HALF_CM - ARM_IN_CM) * k, _y(SHOULDER_CM + ARM_DOWN_CM))
    e = (j[0] + side * (math.tan(math.radians(UPPER_ARM_DEG)) * (_y(ELBOW_CM) - j[1]) + spread * k), _y(ELBOW_CM))
    w = (e[0] + side * math.tan(math.radians(FOREARM_DEG)) * (_y(WRIST_CM) - e[1]), _y(WRIST_CM))
    return j, e, w


def _arm_length(side: int = -1, spread: float = 0.0) -> float:
    """From the shoulder joint down the arm to the wrist (px)."""
    j, e, w = _arm_points(side, spread)
    return math.dist(j, e) + math.dist(e, w)


def _arm_at(side: int, s: float, spread: float = 0.0) -> tuple[tuple[float, float], tuple[float, float]]:
    """The point `s` px down the middle of the arm from the shoulder joint, and which way the arm runs there. The
    bend at the elbow is rounded; above the joint and past the wrist the arm's line is carried straight on."""
    j, e, w = _arm_points(side, spread)
    l1 = math.dist(j, e)
    d1, d2 = _unit(e[0] - j[0], e[1] - j[1]), _unit(w[0] - e[0], w[1] - e[1])
    r = ELBOW_BEND_CM * K_PX
    if s <= l1 - r:
        return (j[0] + d1[0] * s, j[1] + d1[1] * s), d1
    if s >= l1 + r:
        return (e[0] + d2[0] * (s - l1), e[1] + d2[1] * (s - l1)), d2
    t = (s - l1 + r) / (2 * r)
    a, b = (e[0] - d1[0] * r, e[1] - d1[1] * r), (e[0] + d2[0] * r, e[1] + d2[1] * r)
    p = tuple((1 - t) ** 2 * a[i] + 2 * t * (1 - t) * e[i] + t * t * b[i] for i in (0, 1))
    return p, _unit((1 - t) * d1[0] + t * d2[0], (1 - t) * d1[1] + t * d2[1])


def _arm_half(s: float) -> float:
    """Half the arm's width `s` px down it from the shoulder joint (px): ARM_HALVES, eased between."""
    cm = s / K_PX
    if cm <= ARM_HALVES[0][0]:
        return ARM_HALVES[0][1] * K_PX
    for (a0, h0), (a1, h1) in zip(ARM_HALVES, ARM_HALVES[1:], strict=False):
        if cm <= a1:
            t = (cm - a0) / (a1 - a0)
            return (h0 + (h1 - h0) * t * t * (3 - 2 * t)) * K_PX
    return ARM_HALVES[-1][1] * K_PX


def _arm_line(side: int = -1, spread: float = 0.0) -> tuple[tuple[float, float], tuple[float, float], float]:
    """The forearm's middle: where it starts (the elbow), which way it hangs, and how long it is to the wrist (in
    px). A sleeve's opening is measured along it. `side` -1 is the viewer's left."""
    _, e, w = _arm_points(side, spread)
    return e, _unit(w[0] - e[0], w[1] - e[1]), math.dist(e, w)


@dataclass(frozen=True)
class Piece:
    """One item, described as its own drawing is: the stored tagger answer when there is one (with the
    owner's corrections already in it), otherwise the closet's coarse fields."""
    category: str | None = None
    answer: object = None
    color_hex: str | None = None
    color: str | None = None
    pattern: str | None = None
    silhouette: dict | None = None
    fill: Fill | None = None     # the item's pattern measured from its photo, as its own drawing uses it
    graphic: Graphic | None = None   # a print lifted from its photo (tops only), as its own drawing uses it
    traced: object = None        # shoes: the shoe traced from its photo (`traced.TracedShoe` or its JSON), drawn from the front
    drawn: object = None         # shoes: the shoe Claude drew from its photos, as kept (`shoedraw`; read by `drawn.stored`),
    #                              drawn on the figure in place of the front view


@dataclass
class Placed:
    """A piece as it is drawn in the figure. `transforms` map the template's canvas into the figure, one per
    copy drawn (two for the shoes), as SVG matrices (a, b, c, d, e, f). Tops and trousers are fitted to the wearer:
    their `shape` is already in the figure (one identity transform), and `scale` is how much narrower it is drawn
    than flat."""
    place: str
    spec: Spec
    shape: Shape
    transforms: list[tuple[float, float, float, float, float, float]]
    px_per_cm: float
    open: bool = False
    front: FrontShoe | None = None    # the shoes: one shoe seen from the front, in its own coordinates
    scale: float = 1.0
    holds: float = 0.0                # a top: how much further out (cm) it holds the elbows (`_fit_top`)
    traced: object = None             # the shoes: their trace, when there is one (`frontshoe.usable_trace` decides)
    drawn: drawn.Stored | None = None  # the shoes: Claude's drawing of them, drawn in place of `front`

    def point(self, p, copy: int = 0) -> tuple[float, float]:
        a, b, c, d, e, f = self.transforms[copy]
        return a * p[0] + c * p[1] + e, b * p[0] + d * p[1] + f

    def box(self, box=None) -> tuple[float, float, float, float]:
        """A box of the template (its drawn extent by default) in the figure, over every copy."""
        x0, y0, x1, y1 = box or self.shape.bbox
        pts = [self.point(q, i) for i in range(len(self.transforms)) for q in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))]
        return min(x for x, _ in pts), min(y for _, y in pts), max(x for x, _ in pts), max(y for _, y in pts)


@dataclass
class Body:
    """The wearer, in the figure's coordinates: paths for the torso (with the neck, up under the chin), the arms,
    the hands, the legs (down into the shoes), the ears, the head and the hair, and the detail lines (fingers, ears,
    and the face's features). Garments are drawn over it from the same anchors, so skin shows only where none
    covers it. `feet` are bare feet, when there are trousers but no shoes."""
    torso: str
    arms: list[str] = field(default_factory=list)
    hands: list[str] = field(default_factory=list)
    fingers: list[str] = field(default_factory=list)
    legs: list[str] = field(default_factory=list)
    ears: list[str] = field(default_factory=list)
    ear_lines: list[str] = field(default_factory=list)
    head: str = ""
    hair: str = ""
    hair_lines: list[str] = field(default_factory=list)
    face: list[tuple[str, str, float]] = field(default_factory=list)   # (path, colour, width); eyes are filled
    eyes: list[str] = field(default_factory=list)
    cut: float | None = None    # with no trousers, the torso is not drawn below this
    feet: tuple[FrontShoe, list] | None = None
    foot_paths: list[str] = field(default_factory=list)   # bare feet (in sandals, or with no shoes), one shape with the legs
    toe_lines: list[str] = field(default_factory=list)
    box: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)


@dataclass
class Layout:
    pieces: list[Placed] = field(default_factory=list)
    view: tuple[float, float, float, float] = (0.0, 0.0, 400.0, 600.0)   # x, y, width, height
    body: Body | None = None
    accessories: list = field(default_factory=list)   # every accessory given: `worn` draws the small ones
    spread: float = 0.0   # how much further out the elbows are held (cm), by the fullest top's body (`_spread`)

    def fit(self) -> None:
        """The canvas: everything drawn, with MARGIN on every side."""
        boxes = [p.box() for p in self.pieces] + ([self.body.box] if self.body else [])
        boxes = boxes or [(CX - 100, NECK_Y, CX + 100, GROUND_Y)]
        x0, y0 = min(b[0] for b in boxes) - MARGIN, min(b[1] for b in boxes) - MARGIN
        x1, y1 = max(b[2] for b in boxes) + MARGIN, max(b[3] for b in boxes) + MARGIN
        self.view = (x0, y0, x1 - x0, y1 - y0)

    def get(self, place: str) -> Placed | None:
        return next((p for p in self.pieces if p.place == place), None)


def figure(pieces: Mapping[str, Piece | None] | None, *, uid: str = "f") -> str:
    """The outfit as worn, as one SVG. `pieces` maps places (base, mid, outer, bottom, shoes) to pieces, and
    "accessories" to a list of pieces; a place that is missing or None is not drawn. Never raises."""
    uid = item._uid(uid)
    try:
        return _svg(plan(pieces), uid)
    except Exception:
        log.exception("could not draw an outfit as worn")
        return _empty()


def plan(pieces: Mapping[str, Piece | None] | None) -> Layout:
    """Where each piece goes: the figure's geometry, without drawing it."""
    out = Layout()
    pieces = pieces if isinstance(pieces, Mapping) else {}
    shoes = _placed("shoes", pieces.get("shoes"))   # first: the trousers' hem is put on them
    for place in PLACES:
        if place == "shoes":
            continue
        made = _placed(place, pieces.get(place), shoes)
        if made is not None:
            out.pieces.append(made)
    out.spread = _spread([p for p in out.pieces if p.place in TOP_PLACES])
    if out.spread:   # every sleeve goes round the same arm: the tops again, round arms held out by the fullest
        out.pieces = [(_placed(p.place, pieces.get(p.place), shoes, out.spread) or p) if p.place in TOP_PLACES else p
                      for p in out.pieces]
    if shoes is not None:
        try:
            out.pieces.append(_stand(shoes, out))
        except Exception:
            log.exception("placing the shoes for an outfit failed")
    if any(p.place in TOP_PLACES or p.place == "bottom" for p in out.pieces):
        try:
            out.body = _body(out)
        except Exception:
            log.exception("placing the wearer for an outfit failed")
    accessories = pieces.get("accessories")
    if isinstance(accessories, (list, tuple)):
        out.accessories = list(accessories)
        for made in _accessories(out, accessories):
            out.pieces.append(made)
    out.fit()
    return out


# ------------------------------------------------------------------ pieces

def _spec(piece: Piece) -> Spec:
    """The piece's drawing as its own item drawing would be made: from its answer, else from its fields."""
    tags = item._tags(piece.answer) if piece.answer is not None else None
    if tags is None or tags.category != piece.category:
        word = piece.color if isinstance(piece.color, str) and piece.color in item.NAMED_HEX else "grey"
        tags = item._plain(piece.category, item._known_silhouette(piece.silhouette), {}, word)
    template, params, extras, _ = item.drawing_for(tags)
    return Spec(template, dict(params), piece.fill or Fill("solid", item._color(piece.color_hex, tags.color)),
                graphic=piece.graphic if template == "top" else None, **extras)


def as_worn(piece: Piece) -> list[dict]:
    """How the piece sits on the wearer, in the words the item page shows under its name: for a top its fit, the
    landmark its hem goes to (a key of HEM_AT) and its sleeve length; for trousers their leg and their length. Each
    is {"part", "value", "field"}, `field` being the detail the owner corrects it with in "Fix the details". A part
    nothing was told about is left out (it is drawn regular). Never raises."""
    try:
        spec = _spec(piece)
        tags = item._tags(piece.answer) if piece.answer is not None else None
        if tags is not None and tags.category != piece.category:
            tags = None
        s = tags.silhouette if tags else item._plain(piece.category, item._known_silhouette(piece.silhouette), {}).silhouette
        d = tags.details if tags else None
        p, out = spec.params, []
        if spec.template == "top":
            fit = d.fit_detail if d else None
            if d or s.fit:
                out.append({"part": "fit", "value": p.get("fit", "regular"), "field": "fit_detail"})
            if s.top_length or fit in ("cropped", "longline") or p.get("length", "regular") != "regular":
                out.append({"part": "length", "value": reaches(p, None, piece.category), "field": "fit_detail"})
            if (d and d.sleeve_length != "na") or s.sleeve:
                out.append({"part": "sleeve", "value": p.get("sleeve", "long"), "field": "sleeve_length"})
        elif spec.template == "pants":
            if (d and d.leg_shape != "na") or s.leg:
                out.append({"part": "leg", "value": p.get("leg", "straight"), "field": "leg_shape"})
            short = p.get("length") in ("short", "brief")
            if (short and d and d.inseam) or (not short and ((d and d.trouser_break != "na") or s.pant_length)):
                out.append({"part": "length", "value": p.get("length", "full"), "field": "inseam" if short else "trouser_break"})
        return out
    except Exception:
        log.exception("telling how a %s is worn failed", piece.category)
        return []


def _plainest(piece: Piece) -> Spec:
    template, params, extras, _ = item.drawing_for(item._plain(piece.category, {}, {}))
    return Spec(template, dict(params), Fill("solid", item._color(piece.color_hex, piece.color)), **extras)


def _shape(spec: Spec) -> Shape:
    params = spec.params if not spec.weight or "weight" in spec.params else {**spec.params, "weight": spec.weight}
    return build(spec.template, params)


def _spread(tops: list[Placed]) -> float:
    """How much further out (cm) the elbows are held: as far as the top that holds them furthest does (a stiff, roomy
    one: ARM_OUT); none for soft cloth or a regular top."""
    return round(max([0.0] + [p.holds for p in tops]), 2)


def _placed(place: str, piece, shoes: Placed | None = None, spread: float = 0.0) -> Placed | None:
    """The piece placed in the figure; the plainest drawing of its category if its own cannot be drawn;
    None if it is not something this place shows, or nothing can be drawn. Trousers are put on `shoes`."""
    if not isinstance(piece, Piece) or piece.category not in PLACE_CATEGORIES[place]:
        return None
    for make in (_spec, _plainest):
        try:
            spec = make(piece)
            if spec.template == PLACE_TEMPLATE[place]:
                return _place(place, spec, piece.category, piece.traced if make is _spec else None,
                              shoes.front if shoes is not None else None, made=_drawing_of(piece) if place == "shoes" else None,
                              spread=spread)
        except Exception:
            log.exception("drawing a %s for an outfit failed", piece.category)
    return None


def _drawing_of(piece: Piece) -> drawn.Stored | None:
    """The shoe's drawing by Claude, read for the figure; None when it has none or it cannot be drawn (the front view
    is drawn then, as for a shoe never drawn)."""
    if piece.drawn is None:
        return None
    try:
        return drawn.stored(piece.drawn)
    except Exception:
        log.exception("a shoe's drawing could not be read for an outfit; its front view is drawn instead")
        return None


def _place(place: str, spec: Spec, category: str | None = None, traced=None, shoe: FrontShoe | None = None,
           made: drawn.Stored | None = None, spread: float = 0.0) -> Placed:
    if spec.template == "top":
        spec.params.pop("state", None)
        opened = False
        if place != "base" and spec.params.get("front") in OPENS:
            worn_open = replace(spec, params={**spec.params, "state": "open"})
            shape = _shape(worn_open)
            if shape.fronts:
                spec, opened = worn_open, True
        shape, sx, holds = _fit_top(spec, _shape(spec), place, category, spread)
        _draw(spec, "line", "probe", dy=0.0, shape=shape)   # fails here, not halfway through the figure
        return Placed(place, spec, shape, [IDENTITY], K_PX, opened, scale=sx, holds=holds)
    if spec.template == "pants":
        if _on_shoe(spec.params, shoe) == "on":   # its length bunches on top of a boot's shaft
            spec.params["break"] = STACK.get(spec.params.get("break", "none"), "stacked")
        shape = _fit_bottom(_shape(spec), spec.params.get("leg", "straight"), spec.params, shoe)
        _draw(spec, "line", "probe", dy=0.0, shape=shape)
        return Placed(place, spec, shape, [IDENTITY], K_PX, scale=BOTTOM_SX)
    shape = _shape(spec)
    _draw(spec, "line", "probe", dy=0.0)
    # the shoes: the item's drawing is a side view; the figure draws the same shoe from the front (frontshoe), and
    # `_stand` puts the pair under the legs once the trousers are placed. The side view's sole colour is kept.
    front = front_shoe(spec, K_PX, sole_default=shape.sole_default, traced=traced)
    if made is not None:   # Claude's drawing is drawn instead: the hem rests on its opening
        _on_drawing(front, made)
    box = _drawn_box(front, made) if made is not None else front.bbox
    flat = Shape(outline=front.outline, bbox=box, body_box=front.bbox, anchors=dict(front.anchors),
                 sole_default=shape.sole_default)
    return Placed(place, spec, flat, [(1.0, 0.0, 0.0, 1.0, CX - LEG_CM * K_PX, GROUND_Y),
                                      (-1.0, 0.0, 0.0, 1.0, CX + LEG_CM * K_PX, GROUND_Y)], K_PX, front=front, traced=traced,
                  drawn=made)


IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _between(table: list[tuple[float, float]], v: float) -> float:
    """`v` looked up in a table of (from, to) pairs, straight between them and on past either end."""
    for (a0, b0), (a1, b1) in zip(table, table[1:], strict=False):
        if v <= a1 or (a1, b1) == table[-1]:
            return b0 + (v - a0) * (b1 - b0) / (a1 - a0)
    return v


def _fit_top(spec: Spec, shape: Shape, place: str = "base", category: str | None = None,
             spread: float = 0.0) -> tuple[Shape, float, float]:
    """The top fitted to the wearer, how much narrower its neck and shoulders are drawn, and how much further out
    (cm) it holds his elbows (ARM_OUT). Its arms' elbows are held `spread` cm further out. Its body is scaled
    about the middle so a regular top's shoulder seam lands on his shoulder point and its underarm UNDERARM_IN
    narrower (a fuller or slimmer fit stays fuller or slimmer by as much as it is on its flat drawing, and none is
    narrower than he is), and moved down him by TOP_LENGTH. Each sleeve goes round the arm (`_on_arm`), from the
    shoulder point and the underarm (ARMPIT_CM) to its opening, bent at the elbow as the arm is: a long sleeve
    ends round the wrist (a jacket's or coat's PAST_WRIST_CM past it), a shorter one as far down the arm as it is
    down a long one. A sleeve is as wide as the arm and some ease (SLEEVE_EASE), by the top's fit and, for an outer
    layer, by what it is (`category`) and where it is worn (`place`); the width of the sleeve on the flat drawing is not used."""
    params = spec.params if not spec.weight or "weight" in spec.params else {**spec.params, "weight": spec.weight}
    params = {k: v for k, v in params.items() if k != "state"}
    block = _block_for({**TOP_DEFAULTS, **params})
    ref = build("top", {**params, "block": block, "fit": "regular", "shoulder": "set-in", "sleeve": "long"})
    ref_sleeves = {s.side: s for s in fitting.sleeves(ref)}
    nx, ny = ref.anchors["neck"]
    right = ref_sleeves.get(1)
    sh = right.shoulder if right else (CX + 23 * K_PX, ny + 22.0)
    pit_y = right.armpit[1] if right else sh[1] + 90.0
    sx = SHOULDER_HALF_CM * K_PX / (sh[0] - CX)
    own_sleeves = fitting.sleeves(shape)
    own_half = shape.body_box[2] - CX
    fuller = own_half / (ref.body_box[2] - CX)   # 1 for a regular fit, below for slim, above for oversized
    sx *= max(1.0, fuller) ** FIT_GAIN   # a fuller fit, fuller still on him
    # below the underarm the body stands off his hips by some ease, less for a slimmer fit (never none, so no skin
    # shows beside it)
    full = fuller > 1.02 and block != "coat"   # a fuller fit: wider than him at the shoulders, and falling straight
    # a jacket, a coat or a heavy overshirt: stiff enough to keep its shape and hold the arms off it
    stiff = block in OUTER_BLOCKS or category in ("coat", "jacket") or params.get("weight") == "heavyweight"
    word = params.get("fit", "regular")
    room = HIP_HALF_CM + max(MIN_HIP_EASE_CM, HIP_EASE_CM + (fuller - 1.0) * EASE_PER_FIT)
    if full:
        room = CHEST_HALF_CM + FIT_ROOM_CM["regular"] + (fuller - 1.0) * (STIFF_ROOM_PER_FIT if stiff else FULLER_ROOM_PER_FIT)
    front_in = stiff and (full or word == "relaxed")   # its front details drawn on the front in front of the arms
    ease = room * K_PX / (own_half * sx * UNDERARM_IN)
    if block == "coat":   # a coat to the knee hangs straight down from the chest
        ease = max(1.0, ease)
    hem_y = shape.anchors.get("hem", (CX, shape.body_box[3]))[1]
    # the body's side on the flat drawing, by height (a sleeve hanging clear of it is not its side)
    flat = fitting.points(shape.outline)

    def flat_side(y: float) -> float:
        xs = [x0 + (y - y0) * (x1 - x0) / (y1 - y0) for (x0, y0), (x1, y1) in zip(flat, flat[1:] + flat[:1], strict=True)
              if (y0 > y) != (y1 > y)]
        return min((x for x in xs if x > CX + 20), default=shape.body_box[2])

    sides = [(y, flat_side(y) - CX) for y in (pit_y + (hem_y - pit_y) * i / 24 for i in range(25))]

    def flat_half(y: float) -> float:
        return max(20.0, _between(sides, min(max(y, pit_y), hem_y)))

    hood = params.get("neck") == "hood"
    # a hood lies back on the shoulders (a rain shell's is drawn lying down already: as it is drawn)
    above = (0.7 if params.get("hood") == "down" else HOOD_ABOVE) if hood else 0.85
    roomy = full   # an oversized top: its ribbed hem and cuffs gather it in
    # how full its sleeves are: by its fit, and for an outer layer by what it is
    fit = SLEEVE_FIT.get(word, "roomy" if roomy else "regular")
    if block == "coat" or category == "coat" or (place == "outer" and (block in OUTER_BLOCKS or category == "jacket")):
        layer = "coat"      # worn over other layers
    elif block in OUTER_BLOCKS or category == "jacket" or params.get("weight") == "heavyweight":
        layer = "outer"     # a jacket, a chore coat, an overshirt
    else:
        layer = None
    if layer and SLEEVE_EASE[layer][0] > SLEEVE_EASE[fit][0]:
        fit = layer
    gather = HEM_GATHER if roomy and params.get("hem") == "rib" else 0.0
    old = [(-40.0, -40.0 * above), (0.0, 0.0), ((sh[1] - ny) / K_PX, SHOULDER_CM - NECK_CM)] + TOP_LENGTH[1:]
    pit_cm = _between(old, (pit_y - ny) / K_PX)   # where a regular top's underarm lands: the same for every top
    hem_cm = max(_hem_cm(params, block, category), HEM_AT["waist"]) - NECK_CM
    table = old[:3] + [((pit_y - ny) / K_PX, pit_cm), ((hem_y - ny) / K_PX, max(hem_cm, pit_cm + 5.0))]
    shaped = word in ("slim", "tailored") and block not in ("coat",)

    seam_y = min(max([sh[1]] + [sl.shoulder[1] for sl in own_sleeves]), pit_y - 1.0)   # its own shoulder seams' height

    def body(q):
        t = max(0.0, min(1.0, (q[1] - sh[1]) / (pit_y - sh[1])))
        low = max(0.0, min(1.0, (q[1] - pit_y) / ((hem_y - pit_y) or 1.0)))
        cm = NECK_CM + _between(table, (q[1] - ny) / K_PX)
        across = sx * (1 - (1 - UNDERARM_IN) * t) * (1 + (ease - 1) * low)
        w = max(0.0, min(1.0, (q[1] - seam_y) / ((pit_y - seam_y) * FULL_IN)))
        w = w * w * (3 - 2 * w)   # from its own shoulder seams to high on the chest
        if full:   # to its room high on the chest, then straight down
            across = sx + (room * K_PX / own_half - sx) * w
        if cm > ARMPIT_CM:   # never narrower than him: its sides stand off his by BODY_EASE_CM at least
            across = max(across, (_torso_half(cm) + BODY_EASE_CM) * K_PX / own_half)
            if word in FIT_ROOM_CM:   # room at its sides, falling straight from the chest
                w = min(1.0, (cm - ARMPIT_CM) / 2.0)
                across = max(across, w * (CHEST_HALF_CM + FIT_ROOM_CM[word]) * K_PX / own_half)
            if shaped:   # in at the waist and out again over the hips, from just under the underarm
                w = min(1.0, (cm - ARMPIT_CM) / 2.0)
                across += w * ((_torso_half(cm) + _between(SHAPED_EASE, min(cm, HIP_CM))) * K_PX / flat_half(q[1]) - across)
        if gather:   # falls straight to the hem band, which draws it in
            g = max(0.0, min(1.0, (q[1] - hem_y) / (HEM_GATHER_CM * K_PX) + 2.0))
            across *= 1 - gather * g * g * (3 - 2 * g)
        if hood and q[1] < ny:   # a hood worn down spreads over the shoulders
            across *= 1 + (HOOD_WIDE - 1) * min(1.0, (ny - q[1]) / (6.0 * K_PX))
        x, y = (q[0] - CX) * across, _y(cm)
        if front_in and w > 0:   # what is on its front nearer the middle, its sides drawn out behind the sleeves
            half = flat_half(q[1])
            u = abs(q[0] - CX) / half
            g = FRONT_IN * u if u <= FRONT_KEEP else (
                FRONT_IN * u + (1 - FRONT_IN) * ((u - FRONT_KEEP) / (1 - FRONT_KEEP)) ** 2 if u < 1 else u)
            x = math.copysign(half * across * (u + (g - u) * w), x)
        over = abs(x) - SHOULDER_HALF_CM * K_PX
        # all along its shoulder line (down to its own seams), and less below them, to none at the underarm
        fade = 1 - max(0.0, min(1.0, (q[1] - seam_y) / (pit_y - seam_y)))
        if over > 0 and fade > 0:   # a shoulder wider than his falls over the top of his arm
            x -= math.copysign(over * (1 - DROP_ACROSS) * fade, x)
            r = DROP_ROUND_CM * K_PX   # round over his shoulder point, no corner where the drop begins
            y += (over * over / (2 * r) if over < r else over - r / 2) * DROP_DOWN * fade
        return CX + x, y

    under = max([pit_y] + [sl.armpit[1] for sl in own_sleeves]) + 4.0   # just under the underarm, on the flat drawing
    edge = [body((flat_side(y), y)) for y in (under + (hem_y - 3.0 - under) * i / 32 for i in range(33))]
    edge = [(y, abs(x - CX)) for x, y in edge]
    usual = sorted(h for _, h in edge)[len(edge) // 2]
    edge = [(y, h) for y, h in edge if h < 1.25 * usual] or edge   # (a height where the flat drawing has no side is left out)

    def beside(y: float) -> float | None:
        return _between(edge, max(y, edge[0][0])) if y <= edge[-1][0] else None

    parts = []
    angle = UPPER_ARM_DEG
    for own in own_sleeves:
        r = ref_sleeves.get(own.side)
        if r is None:
            continue
        side = own.side
        length = _arm_length(side, spread)
        share = math.dist(own.shoulder, own.outer) / (math.dist(r.shoulder, r.outer) or 1.0)
        # to the point on the arm its length goes to; rolled up, as far down the arm as it is down a long sleeve
        end = SLEEVE_ENDS.get(params.get("sleeve", "long"))
        if roomy and params.get("sleeve") == "short":
            end = ROOMY_SHORT_CM
        reach = length * min(share, 1.15) if end is None or params.get("cuffs") in ("rolled", "roll-tab") else _down_arm(side, end, spread)
        reach += PAST_WRIST_CM * K_PX if share >= SHORT_SHARE and block in OUTER_BLOCKS else 0.0
        s2, a2 = body(own.shoulder), body(own.armpit)
        a2 = (a2[0], min(a2[1], _y(ARMPIT_CM)))
        upper, cuff = (v * K_PX for v in SLEEVE_EASE[fit])
        if share < SHORT_SHARE:
            cuff = upper + SHORT_SLEEVE_MORE_CM * K_PX
        gathered = roomy and share >= SHORT_SHARE and params.get("cuffs") == "rib"
        if gathered:   # its cuff holds it at the wrist, however long or short it is on the flat drawing
            reach = length
        on = _on_arm(side, s2, a2, reach, upper, cuff, gathered, beside, spread)
        parts.append((own.poly, fitting.sleeve_map(own, on)))
        c = on(1.0, 0.5)
        angle = math.degrees(math.atan2(abs(c[0] - s2[0]), c[1] - s2[1]))
    fn = fitting.blend(body, parts, 10.0) if parts else body
    fitted = fitting.warp(shape, fn, lambda a: math.copysign(angle, a), radius=0.85, box=body, split=SLEEVE_SPLIT)
    past = usual / K_PX - (CHEST_HALF_CM + FIT_ROOM_CM["regular"])   # how far its body reaches past a regular top's
    return fitted, sx, min(ARM_OUT_MAX_CM, max(0.0, past) * ARM_OUT) if stiff else 0.0


def _on_arm(side: int, shoulder, armpit, reach: float, upper: float, cuff: float, gathered: bool = False, beside=None,
            spread: float = 0.0):
    """Where a sleeve's cloth goes on the arm: a point `u` of the way from its armhole (0) to its opening (1) and
    `v` across it from its outer edge (0) to its inner one (1). The sleeve goes round the arm, bent at the elbow as
    the arm is: its opening is `reach` px down the arm from the shoulder joint and square to the arm; its outer
    edge starts on the shoulder point and its inner one at the underarm. It stands `upper` px off the arm either
    side at its top and `cuff` px at its opening, narrowing from one to the other as the arm itself does; a
    `gathered` sleeve stays as full as at its top all the way down, and its cuff gathers it in. `beside(y)` is how
    far the top's body reaches from the middle at a height (None below its hem): a sleeve close to the body's side
    is drawn on it, never inside it. The elbows are held `spread` cm out (`_spread`)."""
    e0, e1 = upper, cuff
    j, e, _ = _arm_points(side, spread)
    d = _unit(e[0] - j[0], e[1] - j[1])
    pit = max(0.0, min(reach * 0.8, (armpit[0] - j[0]) * d[0] + (armpit[1] - j[1]) * d[1]))   # the underarm, down the arm

    def ease(u: float) -> float:
        u = max(0.0, min(1.0, u))
        if not gathered:
            return e0 + (e1 - e0) * u
        t = max(0.0, min(1.0, (u - CUFF_FROM) / (CUFF_TO - CUFF_FROM)))   # roomy down to the cuff, which gathers it in
        return e0 + (e1 - e0) * t * t * (3 - 2 * t)

    over = min(1.0, UNDERARM_EASE_CM * K_PX / max(1.0, reach - pit))

    def held(u: float) -> float:
        t = max(0.0, min(1.0, u / over))   # no ease at the underarm, all of it UNDERARM_EASE_CM down the sleeve
        return t * t * (3 - 2 * t)

    dropped = side * (shoulder[0] - CX) > (SHOULDER_HALF_CM + 1.0) * K_PX   # its seam is out on his arm

    def hung(s: float) -> float:   # a dropped shoulder's sleeve hangs from its seam: its outer ease grows down from it
        if not dropped:
            return 1.0
        w = max(0.0, min(1.0, (s - up) / (DROP_EASE_CM * K_PX)))
        return DROP_EASE_SHARE + (1 - DROP_EASE_SHARE) * w * w * (3 - 2 * w)

    def inner(u: float, x: float, y: float, half: float) -> float:
        e = ease(u) * held(u)
        out = beside(y) if beside is not None else None
        if out is None or e <= 0:
            return e
        # how far the body's side reaches toward the bare arm: none where it is clear of the sleeve's free edge,
        # all of it once it is at the arm (behind it): the cloth between them is pressed flat
        bare = side * (x - CX) - half
        p = max(0.0, min(1.0, (out - (bare - e)) / e))
        return e + (min(e, PRESSED_EASE_CM * K_PX) - e) * p

    def edge(s: float, u: float, out: int):
        (x, y), t = _arm_at(side, s, spread)
        a = _arm_half(s)
        h = a + (ease(u) * hung(s) if out > 0 else inner(u, x, y, a))
        return (x + out * side * t[1] * h, y - out * side * t[0] * h)

    # the outer edge starts beside the shoulder point: above the joint, or below it for a dropped shoulder
    up = min(reach * 0.5, (shoulder[0] - j[0]) * d[0] + (shoulder[1] - j[1]) * d[1])
    o0, i0 = edge(up, 0.0, 1), edge(pit, 0.0, -1)
    cap = min(0.5, CAP_CM * K_PX / max(1.0, reach - up))
    p2 = edge(up + cap * (reach - up), cap, 1)
    # the shoulder line, coming into the shoulder point: a top's slope, or over his shoulder for a dropped one
    his = (CX + side * SHOULDER_HALF_CM * K_PX, _y(SHOULDER_CM))
    slope = (_unit(shoulder[0] - his[0], shoulder[1] - his[1]) if math.dist(shoulder, his) > K_PX
             else (side * math.cos(math.radians(SHOULDER_SLOPE_DEG)), math.sin(math.radians(SHOULDER_SLOPE_DEG))))
    bend = _meet(shoulder, slope, p2, d)
    if bend is None:
        bend = ((shoulder[0] + p2[0]) / 2, (shoulder[1] + p2[1]) / 2)

    def fn(u: float, v: float):
        if v > 1:   # past the inner edge is the body beside the underarm: it stays close to the sleeve's edge there
            v = 1 + (v - 1) * 0.25
        elif v < 0:   # past the outer edge is the round of the sleeve's head on the flat drawing: only at its top
            v *= max(0.0, 1 - max(0.0, u) / HEAD_SHARE)
        o, i = edge(up + u * (reach - up), u, 1), edge(pit + u * (reach - pit), u, -1)
        f = (1 - max(0.0, u)) ** 2 if u < 1 else 0.0   # from the shoulder point and the underarm onto the arm
        if u < cap:   # ...sooner on the outside: round over the shoulder's cap, on from the shoulder's slope
            w = u / cap   # (above the armhole, on up the arm from the shoulder point)
            o = (tuple((1 - w) ** 2 * a + 2 * w * (1 - w) * b + w * w * c for a, b, c in zip(shoulder, bend, p2, strict=True))
                 if w >= 0 else (o[0] + shoulder[0] - o0[0], o[1] + shoulder[1] - o0[1]))
        y = i[1] + (armpit[1] - i0[1]) * f
        if side * (armpit[0] - i0[0]) > 0:   # a full body's underarm is out past the arm
            out = beside(y) if beside is not None and (u < 1 or SLEEVE_SHARE_CM) else None
            if u <= 0:
                out = side * (armpit[0] - CX)
            i = (i[0] if out is None else CX + side * (out - SHARE_IN + _apart(side * (i[0] - CX) - out)), y)
        else:
            i = (i[0] + (armpit[0] - i0[0]) * f, y)
            out = beside(y) if beside is not None and SLEEVE_SHARE_CM and u > 0 else None
            if out is not None:
                i = (CX + side * (out - SHARE_IN + _apart(side * (i[0] - CX) - out)), y)
        return (o[0] + (i[0] - o[0]) * v, o[1] + (i[1] - o[1]) * v)
    return fn


def _apart(gap: float) -> float:
    """How far a sleeve's inner edge is drawn from the body's side, when it would be `gap` px from it: on it (one
    line for both, not two heavy ones side by side) until they are SLEEVE_SHARE_CM apart, then quickly (APART_RAMP)
    out to where it is, so no long narrow sliver shows between them. Inside the body's side (a negative gap: the
    body's side stands out past the arm, behind it) the sleeve stays a tube round the arm, drawn over the body."""
    share = SLEEVE_SHARE_CM * K_PX
    if gap < 0:
        return gap
    return 0.0 if gap <= share else gap * min(1.0, (gap - share) / (APART_RAMP * share))


def _meet(p, d, q, e):
    """Where the line through `p` along `d` meets the one through `q` along `e`, ahead of `p` and behind `q` (the
    corner a rounded join goes about), or None."""
    det = d[0] * e[1] - d[1] * e[0]
    if abs(det) < 1e-6:
        return None
    a = ((q[0] - p[0]) * e[1] - (q[1] - p[1]) * e[0]) / det
    b = ((q[0] - p[0]) * d[1] - (q[1] - p[1]) * d[0]) / det
    if a <= 0 or b >= 0 or a > 2 * math.dist(p, q):
        return None
    return p[0] + a * d[0], p[1] + a * d[1]


def _down_arm(side: int, cm: float, spread: float = 0.0) -> float:
    """How far down the arm from the shoulder joint (px) it reaches a height on him."""
    lo, hi, y = 0.0, _arm_length(side, spread), _y(cm)
    for _ in range(30):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if _arm_at(side, mid, spread)[0][1] < y else (lo, mid)
    return (lo + hi) / 2


def _hem_cm(params: dict, block: str, category: str | None) -> float:
    """Where a top's hem lands on him (cm below the crown): at the landmark its length goes to (`reaches`), a boxy
    one a little shorter and an oversized one longer."""
    return HEM_AT[reaches(params, block, category)] + FIT_LONGER_CM.get(params.get("fit", "regular"), 0.0)


def reaches(params: dict, block: str | None = None, category: str | None = None) -> str:
    """The body landmark a top's length goes to (a key of HEM_AT): a jacket or a coat by COAT_REACHES, any other
    top by TOP_REACHES. An unknown length is a regular one."""
    if block is None:
        block = _block_for({**TOP_DEFAULTS, **params})
    table = (COAT_REACHES if category == "coat" or block == "coat" else
             JACKET_REACHES if category == "jacket" or block in OUTER_BLOCKS else TOP_REACHES)
    return table.get(params.get("length", "regular"), "hip")


def _torso_half(cm: float) -> float:
    """Half his width (cm) at a height below the chest: straight between the chest, the waist and the hips."""
    return _between([(CHEST_CM, CHEST_HALF_CM), (WAIST_CM, WAIST_HALF_CM), (HIP_CM, HIP_HALF_CM), (HIP_CM + 1.0, HIP_HALF_CM)],
                    max(CHEST_CM, min(HIP_CM + 1.0, cm)))


def _fit_bottom(shape: Shape, leg: str = "straight", params: Mapping | None = None, shoe: FrontShoe | None = None) -> Shape:
    """The trousers fitted to the wearer: scaled across about the middle, the waist on his waist, the crotch at his
    crotch, and the hem where `_hem` puts it on the shoe (a full-length hem with no shoe BREAK_CM above the ground,
    dipping DIP_CM over the instep); shorter legs fall in proportion. Below the crotch each leg is scaled across
    about its own middle by its shape (LEG_EASE)."""
    wx, wy = shape.anchors["waist"]
    table = [(wy, WAIST_Y), (wy + RISE_CM * PX_CM, CROTCH_Y), (wy + (RISE_CM + INSEAM_CM) * PX_CM, HEM_Y)]
    a = shape.anchors
    fy = a.get("hem_out", a.get("hem", (CX, table[-1][0])))[1]
    params = {**(params or {}), "leg": leg}
    side, drop = _hem(params, shoe, _between(table, fy))
    table[-1] = (fy, side)
    legs = []
    if all(k in a for k in ("leg_l", "leg_r", "hem_out", "hem_in")):
        half = abs(a["hem_out"][0] - a["hem_in"][0]) / 2
        legs = [(a["leg_l"][0], half), (a["leg_r"][0], half)]
    knee, hem = LEG_EASE.get(leg, (1.0, 1.0))
    cy, hy = a.get("crotch", (CX, 0.0))[1], a.get("leg_l", (CX, 0.0))[1]
    shaped = legs and (knee, hem) != (1.0, 1.0) and hy > cy + 1.0
    if shaped:   # the middle of each leg at the crotch (halfway out to the outer seam) and at the hem
        flat = fitting.points(shape.outline)
        out = min((x0 + (cy - y0) * (x1 - x0) / (y1 - y0) for (x0, y0), (x1, y1) in zip(flat, flat[1:] + flat[:1], strict=True)
                   if (y0 > cy) != (y1 > cy)), default=shape.body_box[0])
        c0, kt = (CX + out) / 2, (KNEE_CM - CROTCH_CM) / (GROUND_CM - BREAK_CM - CROTCH_CM)
    ramp = max(8 * K_PX, 3 * abs(drop))   # the hem's front is moved this far up the leg, less and less
    # the hem's front is lowest (or, dropping over the shoe, highest) in front of the shoe's opening, which is a
    # little toward the toe of the ankle the leg is centred on
    toward, reach = 0.0, 0.0
    if shoe is not None and "opening" in shoe.anchors and drop:
        toward = (shoe.anchors["opening"][0] - shoe.anchors["ankle"][0]) / HIP_SX
        if drop > 0:   # resting on the shoe, the hem dips over all of its opening, however narrow the leg
            reach = shoe.width / 2 * K_PX / HIP_SX

    def across(q) -> float:
        x = q[0]
        if shaped and q[1] > cy:
            t = min(1.0, (q[1] - cy) / (hy - cy))
            f = 1 + (knee - 1) * t / kt if t < kt else knee + (hem - knee) * (t - kt) / (1 - kt)
            c = CX + math.copysign(abs(CX - c0) + (abs(CX - legs[0][0]) - abs(CX - c0)) * t, x - CX)
            least = min(abs(x - c), LEG_MIN_HALF_CM * K_PX / HIP_SX)
            x = c + math.copysign(max(abs(x - c) * f, least), x - c)
        return x
    bunch = 1.0   # resting on top of a boot's shaft, the leg bunches out to cover it (BUNCH_EASE_CM)
    if legs and _on_shoe(params, shoe) == "on":
        now = abs(across(a["hem_out"]) - legs[0][0])
        bunch = max(1.0, (shoe.width / 2 + BUNCH_EASE_CM) * K_PX / HIP_SX / (now or 1.0))

    def fn(q):
        x, y = across(q), _between(table, q[1])
        t = min(1.0, max(0.0, (y - side + ramp) / ramp))   # only near the hem
        if bunch > 1.0 and q[1] > cy:
            c = legs[0][0] if x < CX else legs[1][0]
            b = min(1.0, max(0.0, (y - side + BUNCH_CM * K_PX) / (BUNCH_CM * K_PX)))
            x = c + (x - c) * (1 + (bunch - 1) * b * b * (3 - 2 * b))
        for n, (c, h) in enumerate(legs):
            s = max(0.0, 1 - abs(x - c - (toward if n == 0 else -toward)) / max(h, reach)) if h else 0.0
            y += drop * t * t * math.sin(math.pi / 2 * s)
        t = min(1.0, max(0.0, (q[1] - wy) / (FLAT_HIP_CM * PX_CM)))
        return CX + (x - wx) * (BOTTOM_SX + (HIP_SX - BOTTOM_SX) * t), y
    return fitting.warp(shape, fn, radius=0.85, split=4.0 if legs else None)


def _on_shoe(params: Mapping, shoe: FrontShoe | None) -> str | None:
    """How a trouser leg meets the shoe, from the two as solids: "over" when its opening is wide enough to drop
    over the shoe round the shoe's opening (OVER_SHOE), "on" when it is not and the shoe has a shaft (it rests on
    top of the shaft, its length bunched there), "at" when it rests at a low shoe's opening; None when it does not
    reach the shoe (cropped, shorts) or there is no shoe with an opening (bare feet, sandals)."""
    if params.get("length", "full") != "full" or shoe is None or not shoe.width or "opening" not in shoe.anchors:
        return None
    if LEG_WIDTHS.get(params.get("leg", "straight"), LEG_WIDTHS["straight"])[1] >= OVER_SHOE * shoe.width:
        return "over"
    return "on" if shoe.anchors["opening"][1] < shoe.anchors["instep"][1] else "at"


def _hem(params: Mapping, shoe: FrontShoe | None, natural: float) -> tuple[float, float]:
    """Where the hem goes, in the figure: the height of its sides, and how much lower its front is (negative: higher,
    the sides falling past it). `natural` is where its length puts its sides with no shoe to meet.
    - A full-length leg narrower than the shoe round its opening rests on it: its front edge just in front of a low
      shoe's opening, or on top of a boot's shaft, by its break (HEM_FRONT_CM), dipping REST_DIP_CM over it.
    - A wider one drops over the shoe, but from the front covers no more than what is behind the vamp (the instep,
      or a boot's shaft): its front is held up there and its sides fall up to ARCH_CM lower.
    - A cropped (ankle) leg stops above the shoe, level, at least CROP_GAP_CM above the back of its opening.
    Never lower than its length takes it."""
    length = params.get("length", "full")
    if length in ("short", "brief"):
        return natural, 0.0
    dip = DIP_CM * K_PX if length == "full" else 0.0
    dy = _pair(0.0, 0.0, 0.0)[0][5]   # the shoe's own coordinates, down into the figure
    if length == "full" and shoe is not None and "sneaker_rim" in shoe.anchors:
        # over a drawn shoe, trousers keep their own length: as long as it takes for their front to just meet an
        # ordinary sneaker's collar (the drawings are larger than the front views, and the figure's own length would
        # bury a low one), so above a lower shoe the sock shows
        meets = shoe.anchors["sneaker_rim"][1] + dy + HEM_FRONT_CM.get(params.get("break", "none"), 0.3) * K_PX
        natural = min(natural, meets - DIP_CM * K_PX)
    if shoe is None or not shoe.width or "opening" not in shoe.anchors:
        return natural, dip
    rim, instep = shoe.anchors["opening"][1] + dy, shoe.anchors["instep"][1] + dy
    how = _on_shoe(params, shoe)
    if how is None:   # cropped: above the shoe, with the ankle (or a sock) between
        return min(natural, shoe.anchors["opening_back"][1] + dy - CROP_GAP_CM * K_PX), 0.0
    front = min((max(rim, instep) if how == "over" else rim) + HEM_FRONT_CM.get(params.get("break", "none"), 0.3) * K_PX,
                natural + dip)
    if how != "over":
        return front - REST_DIP_CM * K_PX, REST_DIP_CM * K_PX
    wider = LEG_WIDTHS.get(params.get("leg", "straight"), LEG_WIDTHS["straight"])[1] / shoe.width - OVER_SHOE
    side = min(front + ARCH_CM * K_PX * min(1.0, 0.3 + wider), max(natural, front))
    return side, front - side


def _legs(layout: Layout) -> tuple[float, float, bool]:
    """Where the middle of each leg is (the viewer's left, then right) at the ground, and whether the trousers
    reach the shoes. Full-length and ankle trousers: under the middle of each leg's opening. Shorts, or no
    trousers: under the wearer's legs, where a straight leg's hem would be."""
    b = layout.get("bottom")
    left, right = CX - LEG_CM * K_PX, CX + LEG_CM * K_PX
    if b is None or b.spec.params.get("length", "full") not in ("full", "ankle"):
        return left, right, False
    if "leg_l" in b.shape.anchors and "leg_r" in b.shape.anchors:
        left, right = b.point(b.shape.anchors["leg_l"])[0], b.point(b.shape.anchors["leg_r"])[0]
    return left, right, b.spec.params.get("length", "full") == "full"


def _inside_legs(layout: Layout) -> str:
    """Under full-length trousers that drop over the shoes, where the shoes may be seen: below the hem, and above it
    only within the legs (as rectangles for a clip path); empty otherwise (a hem resting on the shoe hides nothing
    beside it)."""
    b, shoes = layout.get("bottom"), layout.get("shoes")
    if b is None or not _legs(layout)[2] or "hem_out" not in b.shape.anchors:
        return ""
    if shoes is not None and _on_shoe(b.spec.params, shoes.front) in ("on", "at"):   # resting on the shoe: all of it shows
        return ""
    (xo, hy), (xi, _) = b.point(b.shape.anchors["hem_out"]), b.point(b.shape.anchors["hem_in"])
    xo, xi = min(xo, xi), max(xo, xi)
    rects = [(-4000.0, hy, 8000.0, 4000.0), (xo, -4000.0, xi - xo, 4000.0 + hy), (2 * CX - xi, -4000.0, xi - xo, 4000.0 + hy)]
    return "".join(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}"/>' for x, y, w, h in rects)


def _stand(shoes: Placed, layout: Layout) -> Placed:
    """The pair, each ankle centred under its leg, the toes on the ground and turned out; the viewer's right shoe
    is the left one mirrored. With trousers on, the wearer's ankle stands in each shoe (a bare foot in a sandal)."""
    left, right, _ = _legs(layout)
    if layout.get("bottom") is not None:
        shoes.front = front_shoe(shoes.spec, K_PX, sole_default=shoes.shape.sole_default, ankle=_ankle(), toes=TOE_LINE,
                                 traced=shoes.traced)
        if shoes.drawn is not None:
            _on_drawing(shoes.front, shoes.drawn)
        shoes.shape = Shape(outline=shoes.front.outline, body_box=shoes.front.bbox,
                            bbox=_drawn_box(shoes.front, shoes.drawn) if shoes.drawn is not None else shoes.front.bbox,
                            anchors=dict(shoes.front.anchors), sole_default=shoes.shape.sole_default)
    shoes.transforms = _pair(shoes.front.anchors["ankle"][0], left, right)
    return shoes


def _pair(ankle_x: float, left: float, right: float) -> list[tuple[float, float, float, float, float, float]]:
    """Each foot's ankle in the middle of its leg (the toes turn out from it), the toes on the ground."""
    bx = ankle_x
    y = GROUND_Y + TOE_CM * K_PX
    return [(1.0, 0.0, 0.0, 1.0, left - bx, y), (-1.0, 0.0, 0.0, 1.0, right + bx, y)]


@dataclass
class DrawnPlace:
    """How a drawn shoe's frame lands in the front view's own coordinates (`_drawn_place`): `k` px a frame unit, the
    frame's middle (x = 100) at `x`, its ground at `ground`, and how far the toe slides sideways for each unit below
    the hinge (`shear`, for the viewer's left shoe)."""
    k: float
    x: float
    ground: float
    shear: float

    def y(self, v: float) -> float:
        """A height in the frame, in the front view's coordinates."""
        return self.ground + self.k * (v - drawn.GROUND)


def _drawn_place(front: FrontShoe, made: drawn.Stored | None = None) -> DrawnPlace:
    """Where a drawn shoe goes, from the front view it is drawn in place of: the frame's leg as wide as its ankle
    (the frame's leg is narrow for its shoe, so the drawing comes out larger than the front view, which the owner
    chose), the frame's middle on the ankle, its ground on the front view's lowest point, and the toe turned out as far
    as the front view's (the slope from its ankle to its toe tip). A drawing in the turned view (`made.view`) is
    turned already: it slides nothing."""
    a = front.anchors
    k = 2 * (a["ankle_r"][0] - a["ankle"][0]) / (drawn.LEG[1] - drawn.LEG[0])
    turned = made is not None and made.view is drawn.TURNED
    shear = 0.0 if turned else (a["toe"][0] - a["ankle"][0]) / (a["toe"][1] - a["ankle"][1])
    return DrawnPlace(k, a["ankle"][0], front.bbox[3] - 2.0, shear)


def _on_drawing(front: FrontShoe, made: drawn.Stored) -> None:
    """The front view's opening as the drawing's, so the hem rests on the drawing: the front of the opening, the
    instep and the back of the opening from its sheet (`drawn.Stored`), and where an ordinary sneaker's
    collar front would be (`sneaker_rim`: full-length trousers are never longer than to meet it). Its ankle, the
    width round its opening and its toe stay the front view's."""
    f = _drawn_place(front, made)
    front.anchors.update(opening=(f.x, f.y(made.opening)), instep=(f.x, f.y(made.instep)),
                         opening_back=(f.x, f.y(made.top)), sneaker_rim=(f.x, f.y(SNEAKER_RIM)))


def _drawn_box(front: FrontShoe, made: drawn.Stored) -> tuple[float, float, float, float]:
    """The front view's box, made to take in the drawing drawn in its place (for the canvas): the frame's width, the
    toe turned out, and up to DRAWN_ABOVE above the back of its opening."""
    f = _drawn_place(front, made)
    out = abs(f.shear) * (drawn.GROUND - made.hinge) * f.k
    half = (made.view.frame[1] - made.view.frame[0]) / 2 * f.k
    x0, y0, x1, y1 = front.bbox
    return (min(x0, f.x - half - out), min(y0, f.y(min(made.top, made.opening) - DRAWN_ABOVE)),
            max(x1, f.x + half + out), y1)


def _turned(body: str, uid: str, shear: float, hinge: float) -> str:
    """A drawing (in its frame) with its toe turned out: above the hinge as it is, below it slid sideways by `shear`
    frame units for each unit below the hinge (the clip paths `uid`u and `uid`d, in the frame). The two meet at the
    hinge, where the slide is nothing, so the collar or a boot's shaft stays upright round the leg."""
    if not body or not shear:
        return body
    return (f'<g clip-path="url(#{uid}u)">{body}</g><g clip-path="url(#{uid}d)">'
            f'<g transform="matrix(1 0 {shear:.4f} 1 {-shear * hinge:.3f} 0)">{body}</g></g>')


def _drawn_pair(shoes: Placed, uid: str, defs: list[str]) -> tuple[str, str]:
    """A drawn shoe on each foot, placed as `_drawn_place` says, in the same copies as the front view (`transforms`):
    (what is behind the legs, what is in front of them). The viewer's right shoe is the left one mirrored, or the
    right drawing as drawn (not mirrored, so its toe turns the other way). The ink lines are as thick as the
    figure's; the toes turn out below the hinge (`_turned`)."""
    made = shoes.drawn
    f = _drawn_place(shoes.front, made)
    hinge = made.hinge
    defs.append(f'<clipPath id="{uid}u"><rect x="-1000" y="-1000" width="3000" height="{1000 + hinge + 0.6:.1f}"/>'
                f'</clipPath><clipPath id="{uid}d"><rect x="-1000" y="{hinge:.1f}" width="3000" height="2000"/>'
                "</clipPath>")
    behind, front = [], []
    for copy, t in enumerate(shoes.transforms):
        side, sx, shear = made.left, 1.0, f.shear
        if copy == 1 and made.right is not None:   # inside the mirrored copy, mirrored back: drawn as is
            side, sx, shear = made.right, -1.0, -f.shear
        place = (f"translate({f.x:.2f} {f.ground:.2f}) scale({sx * f.k:.4f} {f.k:.4f}) "
                 f"translate({-(made.view.frame[0] + made.view.frame[1]) / 2:g} {-drawn.GROUND:g})")
        for part, out in ((side.behind, behind), (side.front, front)):
            if part:
                out.append(f'<g transform="{_matrix(t)}"><g transform="{place}">'
                           f'{_turned(drawn.thicken(part), uid, shear, hinge)}</g></g>')
    return "".join(behind), "".join(front)


def _ankle() -> str:
    """Skin in a shoe, drawn as the body is: its outline under its fill."""
    return (f'<path d="{{d}}" fill="none" stroke="{INK}" stroke-width="{2 * LINE}" stroke-linejoin="round"/>'
            f'<path d="{{d}}" fill="{SKIN}"/>')


# ------------------------------------------------------------------ the wearer

def _f(v: float) -> str:
    return f"{v:.1f}"


def _pt(q) -> str:
    return f"{_f(q[0])},{_f(q[1])}"


def _torso(top: float, short: bool = False) -> str:
    """The torso, from the neck (cut at `top`, under the chin) to the hips. The neck is six tenths as wide as the head; it
    flares into the slope of the shoulders, which fall to the shoulder points (the arms' round tops make the
    shoulder caps). The chest is narrower than any top fitted to him, and the torso ends just above the crotch,
    inside the trousers. `short`: it ends at the waist, for a figure with no trousers."""
    k, n = K_PX, NECK_Y
    nw = NECK_HALF_CM * k

    def at(x, cm):
        return (CX + x * k, _y(cm))
    tip = (SHOULDER_HALF_CM - 2.5, SHOULDER_CM + 1.0)
    right = [("C", at(NECK_HALF_CM, NECK_CM - 0.5), at(NECK_HALF_CM + 4.5, NECK_CM + 1.6), at(*tip)),
             ("C", at(tip[0] + 1.5, tip[1] + 0.6), at(CHEST_HALF_CM + 3.0, CHEST_CM - 8), at(CHEST_HALF_CM, CHEST_CM)),
             ("C", at(CHEST_HALF_CM - 0.3, CHEST_CM + 9), at(WAIST_HALF_CM, WAIST_CM - 9), at(WAIST_HALF_CM, WAIST_CM)),
             ("C", at(WAIST_HALF_CM, WAIST_CM + 5), at(HIP_HALF_CM, HIP_CM - 6), at(HIP_HALF_CM, HIP_CM)),
             ("C", at(HIP_HALF_CM, HIP_CM + 5), at(9, CROTCH_CM - 2), at(0, CROTCH_CM - 2))]
    if short:
        right = right[:3]

    def mirror(q):
        return (2 * CX - q[0], q[1])

    start = (CX + nw, n - 4.0 * k)   # where the neck begins to flare
    d = f"M {_f(CX + nw)},{_f(top)} L {_pt(start)} "
    d += " ".join(f"C {_pt(a)} {_pt(b)} {_pt(c)}" for _, a, b, c in right)
    d += f" L {_pt(mirror(right[-1][3]))}"
    starts = [start] + [seg[3] for seg in right[:-1]]
    for (_, a, b, _c), st in zip(reversed(right), reversed(starts), strict=True):
        a, b, st = mirror(b), mirror(a), mirror(st)
        d += f" C {_pt(a)} {_pt(b)} {_pt(st)}"
    return d + f" L {_f(CX - nw)},{_f(top)} Z"


def _ellipse(cx: float, cy: float, rx: float, ry: float, deg: float = 0.0) -> str:
    pts = []
    c, s_ = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    for i in range(24):
        a = 2 * math.pi * i / 24
        x, y = rx * math.cos(a), ry * math.sin(a)
        pts.append((cx + x * c - y * s_, cy + x * s_ + y * c))
    return "M " + " L ".join(_pt(q) for q in pts) + " Z"


def _numbers(d: str) -> list[tuple[float, float]]:
    return [(float(x), float(y)) for x, y in re.findall(r"(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)", d)]


def _mirror(d: str) -> str:
    """A path of absolute points, mirrored about the middle of the figure."""
    return re.sub(r"(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)", lambda m: f"{_f(2 * CX - float(m[1]))},{m[2]}", d)


def _moved(d: str, t) -> str:
    """A path of absolute points, moved by the matrix `t` (as the shoes are placed: mirrored or not, and shifted)."""
    return re.sub(r"(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)",
                  lambda m: f"{_f(t[0] * float(m[1]) + t[4])},{_f(t[3] * float(m[2]) + t[5])}", d)


def _curve(pts, closed: bool = False) -> str:
    """A smooth curve through the points (Catmull-Rom, as cubic Béziers)."""
    n = len(pts)
    out = f"M {_pt(pts[0])}"
    for i in range(n if closed else n - 1):
        p0, p1 = pts[(i - 1) % n if closed else max(i - 1, 0)], pts[i]
        p2, p3 = pts[(i + 1) % n], pts[(i + 2) % n if closed else min(i + 2, n - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        out += f" C {_pt(c1)} {_pt(c2)} {_pt(p2)}"
    return out + (" Z" if closed else "")


def _tube(centres, halves, steps: int = 8) -> str:
    """A limb along the points `centres`, `halves` wide either side of them, rounded at its start (which is hidden
    in a garment or the torso) and cut straight across at its end (a hand or a shoe covers it)."""
    pts, hs = [], []
    for i in range(len(centres) - 1):
        (x0, y0), (x1, y1) = centres[i], centres[i + 1]
        for j in range(steps):
            t = j / steps
            pts.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
            hs.append(halves[i] + (halves[i + 1] - halves[i]) * t)
    pts.append(centres[-1])
    hs.append(halves[-1])
    left, right, normals = [], [], []
    for j, (x, y) in enumerate(pts):
        a, b = pts[max(j - 1, 0)], pts[min(j + 1, len(pts) - 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        m = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / m, dx / m
        normals.append((nx, ny, dx / m, dy / m))
        left.append((x + nx * hs[j], y + ny * hs[j]))
        right.append((x - nx * hs[j], y - ny * hs[j]))
    nx, ny, dx, dy = normals[0]
    (x, y), h = pts[0], hs[0]
    cap = [(x + h * (-nx * math.cos(a) - dx * math.sin(a)), y + h * (-ny * math.cos(a) - dy * math.sin(a)))
           for a in (math.pi * i / 8 for i in range(1, 8))]
    return "M " + " L ".join(_pt(q) for q in left + right[::-1] + cap) + " Z"


def _unit(dx: float, dy: float) -> tuple[float, float]:
    m = math.hypot(dx, dy) or 1.0
    return dx / m, dy / m


# a relaxed hand hanging from the wrist (0, 0) down its length (+y), its thumb towards the body (+x), in cm
HAND = [(-2.5, 0.0), (-3.0, 3.0), (-3.4, 6.4), (-3.3, 10.0), (-2.8, 13.8), (-1.3, 15.9), (0.7, 16.0), (2.1, 14.2),
        (2.6, 11.4), (3.2, 11.2), (3.7, 10.0), (3.5, 7.6), (2.9, 5.0), (2.5, 2.6), (2.5, 0.0)]
FINGERS = [[(-1.3, 10.6), (-1.4, 13.0), (-1.2, 15.2)], [(0.6, 10.8), (0.6, 13.1), (0.8, 15.3)], [(1.9, 7.8), (2.3, 9.6), (2.6, 11.3)]]


def _rank(p: Placed) -> int:
    return SLEEVE_RANK.get(p.spec.params.get("sleeve", "long"), 4)


def _arm(layout: Layout) -> tuple[str, str, list[str]]:
    """The viewer's left arm with its hand, and the hand's finger lines: from the shoulder joint, the upper arm a
    little out from the body to the elbow, the forearm straight down to the wrist, tapering all the way; every
    sleeve is fitted round this arm. Under a long sleeve the arm stops just inside the cuff, and the hand comes out
    of it."""
    k = K_PX
    length = _arm_length(-1, layout.spread)
    tops = [p for p in layout.pieces if p.place in TOP_PLACES]
    end = length
    if max((_rank(p) for p in tops), default=0) >= SLEEVE_RANK["long"]:
        end = length - (LINE + 2.0)
    n = 28
    cs = [_arm_at(-1, end * i / n, layout.spread)[0] for i in range(n + 1)]
    arm = _tube(cs, [_arm_half(end * i / n) for i in range(n + 1)], steps=1)
    w, d = _arm_at(-1, length, layout.spread)
    h = _unit(d[0] * 0.6, d[1] * 0.6 + 0.4)        # the hand hangs a little straighter than the arm
    p = (h[1], -h[0])

    def put(q):
        kh = k * HAND_SCALE
        return (w[0] + (q[0] * p[0] + q[1] * h[0]) * kh, w[1] + (q[0] * p[1] + q[1] * h[1]) * kh)

    hand = _curve([put(q) for q in HAND], closed=True)
    fingers = [_curve([put(q) for q in line]) for line in FINGERS]
    return arm, hand, fingers


def _room(layout: Layout, y: float, x: float) -> float | None:
    """How far the trousers' leg reaches either side of `x` at height `y` (the nearer side), or None where there is
    no trouser leg."""
    b = layout.get("bottom")
    if b is None:
        return None
    poly = fitting.points(b.shape.outline)
    xs = sorted(x0 + (y - y0) * (x1 - x0) / (y1 - y0) for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1], strict=True)
                if (y0 > y) != (y1 > y))
    left = [v for v in xs if v < x]
    right = [v for v in xs if v > x]
    if not left or not right:
        return None
    return min(x - left[-1], right[0] - x)


def _leg_paths(ends, layout: Layout) -> list[str]:
    """The legs, from the hips (inside the trousers) down to each ankle in its shoe: `ends` are the ankles' middles
    and half widths, the viewer's left one first. Inside trousers a leg is never wider than the trouser leg."""
    k = K_PX
    out = []
    shoes = layout.get("shoes")
    into = 6.0 if shoes is not None and shoes.front is not None and (not shoes.front.foot or shoes.drawn is not None) \
        else LEG_INTO_CM

    def edge(points):
        # Interpolate x by height: uneven calf/ankle spacing must not make the curve double back.
        slopes = [(x1 - x0) / (y1 - y0) for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False)]
        tangents = [slopes[0]] + [0.0 if a * b <= 0 else 2 * a * b / (a + b)
                                  for a, b in zip(slopes, slopes[1:], strict=False)] + [slopes[-1]]
        path = f"M {_pt(points[0])}"
        for i, ((x0, y0), (x1, y1)) in enumerate(zip(points, points[1:], strict=False)):
            third = (y1 - y0) / 3
            path += f" C {_pt((x0 + tangents[i] * third, y0 + third))}"
            path += f" {_pt((x1 - tangents[i + 1] * third, y1 - third))} {_pt((x1, y1))}"
        return path

    for side, (end, rend) in zip((-1, 1), ends, strict=True):
        top = (CX + side * LEG_TOP_HALF_CM * k, _y(HIP_CM - 2))

        def at(y, top=top, end=end):
            t = (y - top[1]) / ((end[1] - top[1]) or 1.0)
            return (top[0] + (end[0] - top[0]) * t, y)

        low = end[1] - 2 * k
        cs, hs = [top], [THIGH_HALF_CM * k]
        for y, r in ((_y(CROTCH_CM + 6), THIGH_HALF_CM * k), (_y(KNEE_CM), KNEE_HALF_CM * k),
                     (_y(CALF_CM), CALF_HALF_CM * k), (low, rend * 1.04)):
            if top[1] < y < end[1] and y > cs[-1][1]:
                cs.append(at(y))
                hs.append(r)
        for i, c in enumerate(cs):
            room = _room(layout, c[1], c[0])
            if room is not None and i > 0:
                hs[i] = max(min(hs[i], room - LINE - 1.5), rend)
        # The cut end is below the collar's front in a closed shoe, or inside the bare foot in a sandal.
        cs += [end, (end[0], end[1] + into * k)]
        hs += [rend, rend]
        left = [(x - h, y) for (x, y), h in zip(cs, hs, strict=True)]
        right = [(x + h, y) for (x, y), h in zip(cs, hs, strict=True)]
        out.append(edge(left) + " L " + edge(right[::-1])[2:] + " Z")
    return out


# the head, in cm from its middle (y down): its shape, the hair, the ears and the face's features
HEAD = [(0.0, -11.75), (5.4, -10.4), (7.5, -6.2), (7.8, -1.5), (7.4, 3.0), (6.3, 6.9), (4.3, 9.9), (1.9, 11.6)]
HAIR_TOP = [(7.7, -2.2), (8.3, -5.6), (7.8, -9.6), (4.9, -12.7), (0.4, -13.7), (-4.6, -13.0), (-7.9, -9.9),
            (-8.4, -5.6), (-7.7, -2.2)]
HAIRLINE = [(-7.0, -2.6), (-6.8, -5.6), (-4.6, -7.4), (-1.6, -7.9), (0.9, -7.0), (3.4, -7.8), (6.0, -7.0),
            (7.0, -5.4), (7.0, -2.6)]
HAIR_LINES = [[(-1.6, -7.9), (-2.6, -10.2), (-2.2, -12.6)], [(0.9, -7.0), (1.6, -9.6), (3.4, -12.0)],
              [(-4.6, -7.4), (-6.0, -9.4), (-6.2, -11.0)]]


def _head(body: Body, chin: float) -> None:
    k = K_PX * HEAD_CM / 23.5     # the drawing below is of a head 23.5 cm from crown to chin
    cy = chin - 11.75 * k

    def at(q):
        return (CX + q[0] * k, cy + q[1] * k)

    shape = HEAD + [(-x, y) for x, y in reversed(HEAD[1:])]
    shape = [q for q in shape if q != (0.0, 11.75)]
    body.head = _curve([at(q) for q in shape], closed=True)
    body.hair = _curve([at(q) for q in HAIR_TOP]) + " L" + _curve([at(q) for q in HAIRLINE])[1:] + " Z"
    body.hair_lines = [_curve([at(q) for q in line]) for line in HAIR_LINES]
    for s in (-1, 1):
        ex, ey = at((s * 7.5, 0.6))
        body.ears.append(_ellipse(ex, ey, 1.25 * k, 2.7 * k, -s * 8))
        body.ear_lines.append(_curve([at((s * 7.8, -1.0)), at((s * 8.3, 0.5)), at((s * 7.8, 2.2))]))
        x, y = at((s * 3.0, -0.3))
        body.eyes.append(_ellipse(x, y, 0.55 * k, 0.75 * k))
        body.face.append((_curve([at((s * 1.7, -2.5)), at((s * 3.0, -3.1)), at((s * 4.5, -2.6))]), HAIR, 2.2))
    body.face.append((_curve([at((0.3, 0.9)), at((0.9, 3.3)), at((0.4, 4.0)), at((-0.7, 4.0))]), SKIN_LINE, 1.5))
    body.face.append((_curve([at((-2.1, 6.6)), at((0.0, 7.3)), at((2.1, 6.6))]), SKIN_LINE, 1.8))


def _body(layout: Layout) -> Body:
    """The wearer, placed from the same points as the clothes."""
    k = K_PX
    chin = CHIN_Y
    bottom = layout.get("bottom")
    body = Body(_torso(chin - 2 * k, short=bottom is None))
    arm, hand, fingers = _arm(layout)
    body.arms, body.hands = [arm, _mirror(arm)], [hand, _mirror(hand)]
    body.fingers = fingers + [_mirror(d) for d in fingers]
    _head(body, chin)
    pts = []
    if bottom is not None:
        shoes = layout.get("shoes")
        if shoes is not None and shoes.front is not None:
            fs, tr = shoes.front, shoes.transforms
        else:   # no shoes: bare feet
            fs = bare_feet(k, ankle=_ankle(), toes=TOE_LINE)
            tr = _pair(fs.anchors["ankle"][0], *_legs(layout)[:2])
            body.feet = (fs, tr)
            x0, y0, x1, y1 = fs.bbox
            pts += [(t[0] * x + t[4], y + t[5]) for t in tr for x in (x0, x1) for y in (y0, y1)]
        if fs.foot and (shoes is None or shoes.drawn is None):   # a bare foot: drawn with the legs, as one shape with them
            body.foot_paths = [_moved(fs.foot, t) for t in tr]
            if body.feet is not None:
                body.toe_lines = [_moved(d, t) for t in tr for d in fs.toes]
        half = abs(fs.anchors["ankle_r"][0] - fs.anchors["ankle"][0])
        ends = []
        for t in tr:
            x, y = fs.anchors["ankle"]
            ends.append(((t[0] * x + t[4], y + t[5]), half))
        body.legs = _leg_paths(ends, layout)
    for d in [body.torso, body.head, body.hair] + body.arms + body.hands + body.legs + body.ears + body.foot_paths:
        pts += _numbers(d)
    body.box = (min(x for x, _ in pts) - LINE, min(y for _, y in pts) - LINE,
                max(x for x, _ in pts) + LINE, max(y for _, y in pts) + LINE)
    return body


def _skin(paths: list[str]) -> str:
    """Skin, as one outline round all of `paths` together: every outline first, then every fill over them."""
    return ("".join(f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="{2 * LINE}" stroke-linejoin="round"/>' for d in paths)
            + "".join(f'<path d="{d}" fill="{SKIN}"/>' for d in paths))


def _lines(paths: list[str], colour: str = SKIN_LINE, width: float = 1.5) -> str:
    return "".join(f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="{width}" stroke-linecap="round"/>' for d in paths)


def _body_markup(body: Body) -> str:
    """Everything of the wearer but the head, drawn before the clothes: the legs, the arms and hands, the torso;
    and bare feet."""
    out = _skin(body.legs + body.foot_paths + body.arms + body.hands + [body.torso]) + _lines(body.fingers)
    return out + "".join(f'<path d="{d}" fill="none" stroke="{TOE_LINE}" stroke-width="1" stroke-linecap="round" opacity=".4"/>'
                         for d in body.toe_lines)


def _head_markup(body: Body) -> str:
    """The head, drawn over the clothes (a hood or a collar at the back is behind it): ears, head, hair, and a
    simple face: eyes, brows, a hint of nose and mouth."""
    out = _skin(body.ears + [body.head]) + _lines(body.ear_lines, width=1.4)
    out += f'<path d="{body.hair}" fill="{HAIR}" stroke="{INK}" stroke-width="2.4" stroke-linejoin="round"/>'
    out += _lines(body.hair_lines, shade(HAIR, 0.3), 1.3)
    out += "".join(f'<path d="{d}" fill="{EYE}"/>' for d in body.eyes)
    out += "".join(_lines([d], c, w) for d, c, w in body.face)
    return out


def _neck_front(body: Body, first: Placed, cid: str, defs: list[str]) -> str:
    """The neck again over the tops, no wider than the neck (with its outline): above the innermost top's neck
    opening, and on down inside the opening a little way. What is drawn there is the back of a neckline or of a
    collar's band, which is behind the neck. The two places overlap, and are drawn one after the other: a browser
    may leave out where two shapes of one clip path overlap."""
    holes = [part.d for part in first.shape.parts if part.role == "hole"]
    if not holes:
        return ""
    cut = min(first.point(q)[1] for d in holes for q in _numbers(d)) + LINE + 1.0
    nw = NECK_HALF_CM * K_PX + LINE + 0.5
    top = CHIN_Y - 4 * K_PX
    if cut <= top:
        return ""
    low = cut + NECK_IN_CM * K_PX
    defs.append(f'<clipPath id="{cid}"><rect x="{CX - nw:.1f}" y="{top:.1f}" width="{2 * nw:.1f}" height="{low - top:.1f}"/></clipPath>')
    defs.append(f'<clipPath id="{cid}a"><rect x="{CX - nw:.1f}" y="{top:.1f}" width="{2 * nw:.1f}" height="{cut - top:.1f}"/></clipPath>')
    defs.append(f'<clipPath id="{cid}h">' + "".join(f'<path d="{d}" transform="{_matrix(first.transforms[0])}"/>' for d in holes)
                + "</clipPath>")
    skin = _skin([body.torso])
    return f'<g clip-path="url(#{cid})"><g clip-path="url(#{cid}h)">{skin}</g><g clip-path="url(#{cid}a)">{skin}</g></g>'


def _accessories(out: Layout, given) -> list[Placed]:
    """The first belt, scarf, hat and bag among `given`, placed on the figure."""
    specs: dict[str, Spec] = {}
    for piece in given:
        if not isinstance(piece, Piece) or piece.category not in item.ACCESSORIES:
            continue
        for make in (_spec, _plainest):
            try:
                spec = make(piece)
            except Exception:
                log.exception("drawing a %s for an outfit failed", piece.category)
                continue
            place = ACCESSORY_PLACE.get(spec.template)
            if place is not None:
                specs.setdefault(place, spec)
                break
    placed = []
    for place in ACCESSORY_ORDER:
        if place not in specs:
            continue
        try:
            placed.append(_place_accessory(place, specs[place], out))
        except Exception:
            log.exception("placing a %s in an outfit failed", place)
    return placed


def _place_accessory(place: str, spec: Spec, out: Layout) -> Placed:
    on = worn.place(place, spec, out)   # a hat on his head, a bag carried: `worn` places them on him
    if on is not None:
        return on
    params = {**spec.params, "px": K_PX}
    if place == "belt":
        params.update(worn=True, half=BELT_HALF_CM)
    spec = replace(spec, params=params)
    shape = _shape(spec)
    _draw(spec, "line", "probe", dy=0.0)
    if place == "belt":
        x, y = CX, BELT_Y
    elif place == "scarf":
        x, y = CX, NECK_Y
    elif place == "hat":
        x, y = CX, HAT_Y
    else:
        boxes = [p.box() for p in out.pieces] or [(CX - 25 * K_PX, NECK_Y, CX + 25 * K_PX, GROUND_Y)]
        x = max(b[2] for b in boxes) + BAG_GAP_CM * K_PX + (CX - shape.bbox[0])
        y = _y(WRIST_CM + 4)
    return Placed(place, spec, shape, [(1.0, 0.0, 0.0, 1.0, x - CX, y)], K_PX)


# ------------------------------------------------------------------ drawing

def _matrix(t) -> str:
    return "matrix(" + " ".join(f"{v:.4f}".rstrip("0").rstrip(".") for v in t) + ")"


def _shows(p: Placed, under: list[Placed]) -> list[str] | None:
    """Where the layers under a top can be seen (paths in the template's canvas), or None for everywhere.
    Inside the top's outline (its fronts and sleeves cover most of that), below its hem as wide as its body,
    and above its collar as wide as a neck. When its sleeves are shorter than one underneath (a vest, a
    short-sleeved overshirt), nothing underneath is hidden but what it covers."""
    rank = SLEEVE_RANK.get(p.spec.params.get("sleeve", "long"), 4)
    if any(SLEEVE_RANK.get(u.spec.params.get("sleeve", "long"), 4) > rank for u in under):
        return None
    sh = p.shape
    half = (sh.body_box[2] - sh.body_box[0]) / 2
    hem_y, sh_y = sh.body_box[3], sh.anchors.get("shoulder_l", (0, 80.0))[1]
    far = 2000.0

    def poly(pts):
        return "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts) + " Z"

    # a hood underneath lies out over this one's shoulders: it shows wherever this does not cover it
    hood = any(u.spec.params.get("neck") == "hood" for u in under)
    neck = max(HOOD_SHOWS * p.scale, half) if hood else 48 * p.scale
    return [sh.outline,
            poly([(CX - half, hem_y - 2), (CX + half, hem_y - 2), (CX + half, far), (CX - half, far)]),
            poly([(CX - neck, -far), (CX + neck, -far), (CX + neck, sh_y + 12), (CX - neck, sh_y + 12)])]


def _tucked(p: Placed) -> tuple[list[str], str]:
    """A top worn tucked in: where it shows (paths in the figure: above the belt, its body drawn in from the width
    of its body to the belt's over the last TUCK_CM, and beside its body, where the sleeves hang), and the
    drawn-in sides as ink lines. Beside the body is taken from just past its drawn edge, so the body's own sides do
    not show below the belt."""
    ty = BELT_Y - TUCK_CM * K_PX
    x0, _, x1, _ = p.box(p.shape.body_box)
    poly = [p.point(q) for q in fitting.points(p.shape.outline)]
    sides = [abs(xa + (ty - ya) * (xb - xa) / (yb - ya) - CX) for (xa, ya), (xb, yb) in zip(poly, poly[1:] + poly[:1], strict=True)
             if (ya > ty) != (yb > ty)]
    if sides and min(sides) < x1 - CX:   # the body's own sides where the tuck starts (it may be drawn in at the waist)
        x0, x1 = CX - min(sides), CX + min(sides)
    bx0, bx1 = CX - BELT_HALF_CM * K_PX, CX + BELT_HALF_CM * K_PX
    far = 4000.0
    shows = [f"M {-far:.1f},{-far:.1f} L {far:.1f},{-far:.1f} L {far:.1f},{ty:.1f} L {x1:.1f},{ty:.1f} "
             f"Q {x1:.1f},{BELT_Y - 2 * K_PX:.1f} {bx1:.1f},{BELT_Y:.1f} L {bx0:.1f},{BELT_Y:.1f} "
             f"Q {x0:.1f},{BELT_Y - 2 * K_PX:.1f} {x0:.1f},{ty:.1f} L {-far:.1f},{ty:.1f} Z",
             f"M {-far:.1f},{ty:.1f} L {x0 - EDGE:.1f},{ty:.1f} L {x0 - EDGE:.1f},{far:.1f} L {-far:.1f},{far:.1f} Z",
             f"M {x1 + EDGE:.1f},{ty:.1f} L {far:.1f},{ty:.1f} L {far:.1f},{far:.1f} L {x1 + EDGE:.1f},{far:.1f} Z"]
    sides = "".join(f'<path d="M {x:.1f},{ty:.1f} Q {x:.1f},{BELT_Y - 2 * K_PX:.1f} {bx:.1f},{BELT_Y:.1f}" fill="none" '
                    f'stroke="{INK}" stroke-width="2.6" stroke-linecap="round"/>' for x, bx in ((x0, bx0), (x1, bx1)))
    return shows, sides


def _arms_over(wearer: Body, layout: Layout, uid: str, defs: list[str]) -> str:
    """The arms and hands again, in front of the clothes' sides (the depth order's arms and hands): a garment's
    body is a shell round his torso, and what of it reaches out past his sides is at his side or back, behind the
    arm hanging beside him. They are drawn over every garment below the lowest underarm (above it a top's
    shoulders lie over the top of the arm), except inside any sleeve: a sleeve is a tube round the arm, in front
    of it, and the arm comes out of its opening."""
    tops = [p for p in layout.pieces if p.place in TOP_PLACES]
    far = 4000.0
    below = []
    for side in (-1, 1):   # on each side, below the opening of the longest sleeve over that arm
        ends = [(p.point(s.outer), p.point(s.inner)) for p in tops for s in fitting.sleeves(p.shape) if s.side == side]
        if ends:
            (ox, oy), (ix, iy) = max(ends, key=lambda e: e[0][1] + e[1][1])
            slope = (iy - oy) / (ix - ox) if abs(ix - ox) > 1e-6 else 0.0
            at_cx, at_far = oy + slope * (CX - ox), oy + slope * (CX + side * 200 - ox)
            pts = [(CX, at_cx), (CX + side * 200, at_far), (CX + side * 200, far), (CX, far)]
        else:
            cut = _y(ARMPIT_CM)
            pts = [(CX, cut), (CX + side * far, cut), (CX + side * far, far), (CX, far)]
        below.append("M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + " Z")
    white = "".join(f'<path d="{d}" fill="#fff" stroke="#fff" stroke-width="{2 * LINE}" stroke-linejoin="round"/>'
                    for d in wearer.arms + wearer.hands)
    black = "".join(f'<path d="{d}" transform="{_matrix(p.transforms[0])}" fill="#000" stroke="#000" '
                    f'stroke-width="{2 * EDGE + 1.5:.1f}" stroke-linejoin="round"/>'
                    for p in tops for d, _ in p.shape.sleeves)
    defs.append(f'<clipPath id="{uid}rb"><path d="{" ".join(below)}"/></clipPath>'
                f'<mask id="{uid}r" maskUnits="userSpaceOnUse" x="{-far:.0f}" y="{-far:.0f}" width="{2 * far:.0f}" '
                f'height="{2 * far:.0f}"><g clip-path="url(#{uid}rb)">{white}</g>{black}</mask>')
    return f'<g id="{uid}a" mask="url(#{uid}r)">{_skin(wearer.arms + wearer.hands)}{_lines(wearer.fingers)}</g>'


ON_SLEEVE = 0.75   # a part of a top lies on a sleeve (a cuff, a button at the wrist) when this share of it is in one


def _spaced(d: str, step: float = 2.0) -> list[tuple[float, float]]:
    """Points along a path, evenly spaced along its length (`step` px apart), whatever points it is written with."""
    pts = fitting.points(d)
    if "Z" in d.upper() and pts:
        pts = pts + pts[:1]
    out = pts[:1]
    for a, b in zip(pts, pts[1:], strict=False):
        n = max(1, math.ceil(math.dist(a, b) / step))
        out += [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(1, n + 1)]
    return out


def _within(pt: tuple[float, float], poly: list[tuple[float, float]]) -> bool:
    """Whether a point is inside a polygon (its corners, a path's points taken as one)."""
    x, y = pt
    inside = False
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1], strict=True):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            inside = not inside
    return inside


ARMHOLE_COVER_PX = 12.0   # how far into the body a sleeve's cloth is drawn past its armhole, under the seam


def _past_armhole(path: str) -> str:
    """A sleeve's path ("... L underarm C c1 c2 shoulder Z") with its armhole moved ARMHOLE_COVER_PX in towards the
    body's middle: drawn with this for its outline, the sleeve's cloth covers the armhole and its edge falls on the
    body, outside what is kept of the sleeve."""
    i = path.rfind(" C ")
    if i < 0:
        return path
    head, under = path[:i], path[:i].split()[-1]
    pts = _numbers(path[i + 1:])
    if len(pts) < 3:
        return path
    side = 1.0 if pts[-1][0] < CX else -1.0   # the left sleeve moves right, the right one left
    moved = [(x + side * ARMHOLE_COVER_PX, y) for x, y in pts]
    ux, uy = _numbers(under)[0]
    shoulder = pts[-1]
    return (f"{head} L {ux + side * ARMHOLE_COVER_PX:.1f},{uy:.1f} C "
            + " ".join(f"{x:.1f},{y:.1f}" for x, y in moved) + f" L {shoulder[0]:.1f},{shoulder[1]:.1f} Z")


def _sleeve_only(shape: Shape) -> Shape:
    """The top with only its sleeves: their outline, and of all that is drawn on the top, only what lies on a sleeve
    (a cuff, the buttons at the wrist, a seam down the arm). The arm is in front of the body, so what of the body lies
    where a sleeve hangs (the corner of a pocket, the hem, the edge of an open front) is behind the sleeve, hidden."""
    polys = [fitting.points(d) for d, _ in shape.sleeves]

    def on(d: str) -> bool:   # judged along its length: a band whose short ends lie on the sleeves is still the body's
        pts = _spaced(d)
        return bool(pts) and sum(any(_within(q, poly) for poly in polys) for q in pts) >= ON_SLEEVE * len(pts)

    def dot_on(t) -> bool:
        return any(_within((t[0], t[1]), poly) for poly in polys)
    return replace(shape, outline=" ".join(_past_armhole(d) for d, _ in shape.sleeves), parts=[q for q in shape.parts if on(q.d)],
                   lines=[d for d in shape.lines if on(d)], dots=[t for t in shape.dots if dot_on(t)],
                   snaps=[t for t in shape.snaps if dot_on(t)], seams=[d for d in shape.seams if on(d)],
                   folds=[d for d in shape.folds if on(d)], blocks=[d for d in shape.blocks if on(d)], behind=[],
                   fronts=None)


def _sleeves_over(p: Placed, tid: str, defs: list[str]) -> str:
    """A top's sleeves again, over its own body: a sleeve is a tube round the arm, in front of the body panel, and
    what of a loose body reaches out past his sides (its side seam, from the underarm out) is behind the sleeve.
    Drawn as the top with only its sleeves (`_sleeve_only`), cut to them: the cloth, the cuffs and the seams on them,
    and the sleeve's own edges, its inner one over the body. Its armhole is a seam on the body, not an edge: a thin
    line from the shoulder round to the underarm where the seam marks something (`templates.seam_shows`: a dropped,
    raglan or saddle shoulder, a sleeve in another colour), else no line."""
    paths = [d for d, _ in p.shape.sleeves]
    only = _sleeve_only(p.shape)
    d, b, _, _ = _draw(replace(p.spec, graphic=None), "line", f"{tid}v", layered=True, dy=0.0,   # a print: on the body
                       shape=only)
    # its edge is drawn along the sleeve, not along the outline drawn past its armhole (`_past_armhole`)
    stroke = re.search(rf'<path d="{re.escape(only.outline)}" fill="none"( stroke="[^"]*" stroke-width="[^"]*")[^>]*/>', b)
    if stroke:
        b = b.replace(stroke.group(0), "")
        b += "".join(f'<path d="{q[:q.rfind(" C ")] if " C " in q else q}" fill="none"{stroke.group(1)} '
                     'stroke-linejoin="round" stroke-linecap="round"/>' for q in paths)
    t, far = _matrix(p.transforms[0]), 4000
    keep = seams = ""
    base = p.spec.fill.color if p.spec.fill is not None and p.spec.fill.color else "#888888"
    seam = shade(base, 0.32 if luminance(base) < 0.3 else -0.38)   # as the seams of a garment drawn on its own
    shows_seam = templates.seam_shows(p.spec.params.get("shoulder", "set-in"), tuple(p.spec.params.get("colorblock") or ()))
    for path in paths:   # each sleeve path ends in its armhole: "... L underarm C . . shoulder Z"
        i = path.rfind(" C ")
        keep += f'<path d="{path}" transform="{t}" fill="#fff"/>'
        if i < 0:
            continue
        keep += (f'<path d="{path[:i]}" transform="{t}" fill="none" stroke="#fff" stroke-width="{2 * EDGE + 2:.1f}" '
                 'stroke-linejoin="round"/>')
        # not its armhole: a seam on the body, not an edge (a dropped one runs across the top of the arm). The
        # sleeve's cloth is kept a little past it, over whatever edge lies under it, and its outline falls further in
        armhole = f"M {path[:i].split()[-1]} {path[i + 1:].rstrip(' Z')}"
        keep += f'<path d="{armhole}" transform="{t}" fill="none" stroke="#fff" stroke-width="{2 * EDGE + 2:.1f}"/>'
        if shows_seam:   # only where it marks something (`templates.seam_shows`, the owner's 16 November rule)
            seams += (f'<path data-part="armhole" d="{armhole}" transform="{t}" fill="none" stroke="{seam}" '
                      f'stroke-width="{SEAM_W}" stroke-linecap="round" opacity=".85"/>')
    # its own prefix: the garment's drawing has a "q" group of its own when it is worn open
    defs += [d, f'<mask id="sl{tid}" maskUnits="userSpaceOnUse" x="{-far}" y="{-far}" width="{2 * far}" '
                f'height="{2 * far}">{keep}</mask>']
    inside = ""
    for sl in fitting.sleeves(p.shape):   # the inside of the tube at the back of its opening, round the arm
        (ox, oy), (ix, iy) = p.point(sl.outer), p.point(sl.inner)
        nx, ny = _unit(iy - oy, ox - ix)
        if ny < 0:
            nx, ny = -nx, -ny
        if math.dist((ox, oy), (ix, iy)) < 2 * TUBE_INSIDE_CM * K_PX:
            continue
        mx, my = (ox + ix) / 2 + nx * TUBE_INSIDE_CM * K_PX, (oy + iy) / 2 + ny * TUBE_INSIDE_CM * K_PX
        inside += (f'<path d="M {ox:.1f},{oy:.1f} Q {2 * mx - (ox + ix) / 2:.1f},{2 * my - (oy + iy) / 2:.1f} '
                   f'{ix:.1f},{iy:.1f} Z" fill="{INK}" opacity=".45"/>')
    return f'<g mask="url(#sl{tid})">{b}</g>{seams}{inside}'


def _clip(cid: str, paths: list[str], t) -> str:
    return f'<clipPath id="{cid}">' + "".join(f'<path d="{d}" transform="{_matrix(t)}"/>' for d in paths) + "</clipPath>"


def _svg(layout: Layout, uid: str) -> str:
    defs: list[str] = []
    body: list[str] = []
    wearer = layout.body
    # the small accessories (a tie, a pocket square, a watch, glasses, socks): `worn` draws them, each put in below
    dressed = worn.dress(layout, layout.accessories, uid)
    defs += dressed.defs
    shoes, bottom = layout.get("shoes"), layout.get("bottom")
    behind = pair = ""
    # under full-length trousers that drop over the shoes: nothing of a shoe shows beside the leg above the hem
    legs = _inside_legs(layout) if shoes is not None else ""
    if shoes is not None and shoes.drawn is not None:   # Claude's drawing: its part behind the legs goes behind him
        behind, pair = _drawn_pair(shoes, f"{uid}j", defs)
        if legs:
            defs.append(f'<clipPath id="{uid}k">{legs}</clipPath>')
    if behind:
        body.append(f'<g id="{uid}q">' + (f'<g clip-path="url(#{uid}k)">{behind}</g>' if legs else behind) + "</g>")
    if wearer is not None:   # the wearer first, behind everything
        body.append(f'<g id="{uid}m">{_body_markup(wearer)}</g>{dressed.legs}')
    if shoes is not None and shoes.drawn is None:
        ankle_path = None
        if wearer is not None and wearer.legs:
            t = shoes.transforms[0]
            ankle_path = _moved(wearer.legs[0], (t[0], 0.0, 0.0, 1.0, -t[0] * t[4], -t[5]))
        front = front_shoe(shoes.spec, K_PX, sole_default=shoes.shape.sole_default, uid=f"{uid}s",
                           ankle=(dressed.ankle or _ankle()) if shoes.front is not None and shoes.front.ankle else None,
                           ankle_path=ankle_path, toes=TOE_LINE, traced=shoes.traced)
        defs.append(front.defs)
        pair = "".join(f'<g transform="{_matrix(t)}">{front.body}</g>' for t in shoes.transforms)
        if legs:
            defs.append(f'<clipPath id="{uid}k">{legs}</clipPath>')
    if shoes is not None:
        if legs:
            pair = f'<g clip-path="url(#{uid}k)">{pair}</g>'
        body.append(f'<g id="{uid}p">{pair}</g>')
    lower = ""
    if bottom is not None:
        d, b, _, _ = _draw(bottom.spec, "line", f"{uid}b", dy=0.0, shape=bottom.shape)
        defs.append(d)
        lower = "".join(f'<g transform="{_matrix(t)}">{b}</g>' for t in bottom.transforms)
    # the tops, from the inside out: each one over everything under it
    extra = {}
    for p in layout.pieces:
        if p.place == "scarf" and p.spec.params.get("style", "woven") in WRAPPED_SCARVES:
            # wrapped round his neck: the part behind it, its ends and the band in front, each at its own depth
            for layer in templates.SCARF_LAYERS:
                spec = replace(p.spec, params={**p.spec.params, "worn": True, "layer": layer})
                d, b, _, _ = _draw(spec, "line", f"{uid}c{layer[0]}", dy=0.0)
                defs.append(d)
                extra[f"scarf_{layer}"] = f'<g transform="{_matrix(p.transforms[0])}">{b}</g>'
        elif p.place in ACCESSORY_ORDER:
            d, b, _, _ = _draw(p.spec, "line", f"{uid}{p.place[0]}", dy=0.0)
            defs.append(d)
            extra[p.place] = f'<g transform="{_matrix(p.transforms[0])}">{b}</g>'
    belt = extra.get("belt", "")
    first = next((q for q in layout.pieces if q.place in TOP_PLACES), None)
    if belt and (first is None or first.open):   # nothing to tuck in: the belt is seen on the trousers
        lower += belt
        belt = ""
    if lower:
        body.append(f'<g id="{uid}w">{lower}</g>')
    # what the wearer shows inside the neck of the innermost top: the neck and the top of the chest, in the top's
    # own coordinates
    neck = chest = torso = ""
    if wearer is not None:
        torso = _skin([wearer.torso])
        cut = f"{uid}c"
        defs.append(f'<clipPath id="{cut}"><rect x="-4000" y="-4000" width="8000" '
                    f'height="{4000 + NECK_Y + 30 * K_PX:.1f}"/></clipPath>')
        chest = f'<g clip-path="url(#{cut})">{torso}</g>'
        neck = chest
    stack, under = "", []
    for n, p in enumerate(q for q in layout.pieces if q.place in TOP_PLACES):
        tid = f"{uid}t{n}"
        d, b, _, _ = _draw(p.spec, "line", tid, layered=True, dy=0.0, inside=neck if not stack and not p.open else None,
                           shape=p.shape)
        defs.append(d)
        if belt and isinstance(b, str):   # tucked in: its body ends at the belt, its sleeves hang beside it
            shows, sides = _tucked(p)
            defs.append(_clip(f"k{tid}", shows, (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)))
            b = f'<g clip-path="url(#k{tid})">{b}</g>' + sides + belt
            belt = ""
        if isinstance(b, str) and p.shape.sleeves:
            b += _sleeves_over(p, tid, defs)
        shows = _shows(p, under) if stack else None
        seen = stack
        if stack and shows is not None:
            # one clip path for each place, the layers underneath drawn once in each: the places overlap, and a
            # browser may leave out where two shapes of one clip path do
            ids = [f"v{tid}" + "abc"[k - 1:k] for k in range(len(shows))]
            defs.extend(_clip(i, [d], p.transforms[0]) for i, d in zip(ids, shows, strict=True))
            seen = (f'<g clip-path="url(#{ids[0]})"><g id="u{tid}">{stack}</g></g>'
                    + "".join(f'<g clip-path="url(#{i})"><use href="#u{tid}"/></g>' for i in ids[1:]))
        if p.open and isinstance(b, tuple):
            back, fronts = b
            # its back is behind him: within its outline he is drawn again over it (the torso, the arms, the legs
            # and the trousers), so between its fronts what is in front of its back shows, and its lining only at
            # the edges, past him
            inner = ""
            if wearer is not None:
                defs.append(_clip(f"o{tid}", [p.shape.outline], p.transforms[0]))
                inner = (f'<g clip-path="url(#o{tid})">' + (f'<use href="#{uid}q"/>' if behind else "") + f'<use href="#{uid}m"/>'
                         + (f'<use href="#{uid}p"/>' if shoes is not None else "")
                         + (f'<use href="#{uid}w"/>' if lower else "") + "</g>")
            if stack:   # the neck stands in front of this one's collar at the back, behind what is under it
                seen = chest + seen
            # its sleeves, with the arms in them, hang in front of its fronts: a pocket or a front's edge where a
            # sleeve hangs is behind the sleeve
            stack = back + inner + seen + fronts + (_sleeves_over(p, tid, defs) if p.shape.sleeves else "")
        else:
            stack = seen + b
            holes = [part.d for part in p.shape.parts if part.role == "hole"]
            if seen and holes:   # what is underneath shows inside the neck opening (a shirt collar in a V)
                defs.append(_clip(f"n{tid}", holes, p.transforms[0]))
                stack += f'<g clip-path="url(#n{tid})">{chest}{seen}</g>'
        if n == 0:
            stack += dressed.tie
        under.append(p)
    body.append(stack)
    if wearer is not None:
        body.append(_arms_over(wearer, layout, uid, defs))
    body.append(extra.get("scarf_back", ""))   # round the back of his neck: behind the neck and the head
    if wearer is not None:
        if first is not None:
            body.append(_neck_front(wearer, first, f"{uid}f", defs))
        body.append(_head_markup(wearer))
    body.append(dressed.over)
    # a bag's straps on his chest under the scarf's hanging ends; the scarf's under end, its band, then the end over it
    body += [dressed.carry or extra.get("bag", "")]
    body += [extra[k] for k in ("scarf", "scarf_under", "scarf_front", "scarf_over", "hat") if k in extra]
    x, y, w, h = layout.view
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x:.1f} {y:.1f} {w:.1f} {h:.1f}" '
            f'width="{w:.0f}" height="{h:.0f}"><defs>{"".join(defs)}</defs>'
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="18" fill="{CARD}"/>'
            f'{"".join(body)}</svg>')


def _empty() -> str:
    w, h = 400.0, 600.0
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" width="{w:.0f}" height="{h:.0f}">'
            f'<rect width="{w:.0f}" height="{h:.0f}" rx="18" fill="{CARD}"/></svg>')
