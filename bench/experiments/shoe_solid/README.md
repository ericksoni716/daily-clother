# A shoe's solid measured from its photos: tried and dropped

Part of the work in `docs/BACKLOG.md` (Track 1, "Shoes on the figure drawn from understanding"); why it was dropped
is in `docs/DECISIONS.md` ("A shoe on the figure's feet: drawn from understanding, not traced"). What replaced it is
in `../shoe_drawn/`. Tried with the owner on 15 November 2026, on five photos (outer side, above, front, back, inner
side) of each of five of the owner's own pairs. Throwaway code, not app code; it holds no photos.

## What was tried

The owner's idea: rebuild each shoe in 3D from several photos and flatten it into the figure's view.

- Each photo was cut out with the app's own cut-out model. It was clean on 25 of 25.
- A solid was built from the side photo (the profile along the length) and the photo from above (the plan), its
  cross-sections rounded to fit the front and back photos.
- Its colours were sampled from the photos, and it was drawn from the figure's view (24° down, toes out 11°).
- Then the same solid was painted only in the few colours a vision model named for that shoe.

Assumed, not measured: a worn shoe stands flat (the toe's lift was removed), every shoe is 29.5 cm long, and the
sole's edge height was not measured.

## The result, and why it was dropped

- Each solid had its shoe's proportions (the boat shoe 9.7 cm tall, the boot 18.6 cm, the runner widest at 11.5 cm),
  but on the feet they read as blobs.
- Colours came out as camouflage: every shade and dirt patch became a colour of its own. Side photos reduced to
  panels well, photos from above badly. The front and back photos barely changed anything.
- Painting only in the named colours fixed the number of colours (the dress shoe became one brown), but the feet were
  still blobs.
- A research pass found the same: grouping pixels by colour will always turn shade into panels; the fix is a palette
  that comes from outside the image. No ready-made tool goes from a few photos to a flat drawing on an ordinary
  laptop.
- An outline of the solid was made for the drawing work to draw over (`guide.py`) and dropped before use: seen from
  the figure's real angle (24° down) the outlines were nearly twice as tall as wide and would have made the shoes
  tall again. Only the height and width were passed on. (`guide.py` is left set to 15° above, the view the drawings
  use.)

## What it is still good for

- The cut-outs: the app's cut-out model handled all 25 photos of these pairs.
- The measured height and width of each shoe (`guide.json`), which the drawing work was given.
- Faults found in the photos, for a later photo check: which end is the toe in the photo from above was guessed
  wrong on 1 of 5 (shoe 2 is flipped by hand, `FLIP_ABOVE`); one side photo ran off the frame at the toe.

## What each file does

| File | What it does |
|---|---|
| `masks.py` | Cuts every photo out with the app's own model (`closet.cutout`) and keeps the masks; run alone, writes a sheet of all 25 cut-outs. |
| `shape.py` | The solid: profile from the side photo, plan from above, cross-sections from front and back, colours from all photos reduced together; draws the feet and prints each shoe's measured sole, height and width. |
| `named.py` | The same solid painted only in the colours a feature sheet names (`draw/shoe-N.json` from `../shoe_drawn/`). |
| `guide.py` | The solid's outline in the drawing frame's units (about 16 units per cm), and its height and width: `guide.svg`, `guide.png` and `guide.json` for each shoe. |

## To run it again

- It needs a small `photos.py` beside the scripts (not kept here, since it pointed at the owner's photos):
  `SHOES` (shoe number to a name and the five photos), `VIEWS = ["side", "above", "front", "back", "inner"]` and
  `path(n, view)` giving each photo's path, for example `bench/private/shoe_drawn/shoe-N/<view>.jpg`.
- The paths inside the scripts point at a scratch folder: `masks.py` sets the repository's place and a work folder
  (`hull-work`) next to the scripts' folder, and `named.py` and `guide.py` read and write a `draw` folder beside it.
  Change them to folders under `bench/private/` before running, so nothing made from the photos lands in the
  repository.
- The cut-out model goes in `bench/models/` (its address and checksum are in `backend/closet/cutout.py`), with the
  backend's requirements installed. Then `python masks.py`, `python shape.py`, `python named.py`, `python guide.py`.
