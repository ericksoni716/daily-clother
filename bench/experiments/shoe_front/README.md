# The front of a traced shoe: the line-up experiment

The work this belongs to is in `docs/BACKLOG.md` (Track 1, "A traced shoe's front, from a front photo") and what
was decided with the owner is in `docs/DECISIONS.md` ("A traced shoe's front on the figure"). Read both first.

This folder is the throwaway code behind steps 1 and 2 of that plan. It is not app code and nothing imports it.
It holds no photos: everything it downloads or draws goes under `bench/private/shoe_front/` (git-ignored).

## Where it stands

- **Step 1, what shops show: done.** The numbers are in the backlog. In short: a photo from above is nearly
  always there, a true front view for about a third of shoes, and the shop's own "front" label cannot be trusted.
- **Step 2, the line-up: done, and it failed** (today 8/10, top 3/10, turn 2/10, stance natural; see the backlog for what follows). As it was set up:
- **The line-up page.** The page is a private artifact,
  <https://claude.ai/artifact/CXwKaVTA3c9capeQ5c4KQG> (only the owner can open it). The owner matches 30 pictures
  of feet to ten side drawings and pastes back a short result, for example:

  ```
  Shoe line-up result
  today: 4/10; missed shoe 2 taken for 1, ...
  top: 8/10; missed shoe 1 taken for 2, ...
  turn: 9/10; ...
  stance at 20: natural
  ```

  `today` is today's default drawing ("From the shoe's shape"), `top` is the photo from above laid on, `turn` is
  the same with the toes turned out 20°.

## The owner's notes on each shoe's outline

After the line-up the owner said the problem is the outline of the shoes on the figure's feet. Their notes on each
of the ten pairs (ticks such as "Too narrow" or "Sole too thin", and a line of text) are kept by a second private
page, <https://claude.ai/artifact/MqwpSvwgm9LEzDZ4pwwUYE>, in its collection `notes` (documents `shoe-1` to
`shoe-10`: `shoe`, `name`, `ticks`, `text`, `at`). Read them from there before measuring anything. The shoes are
numbered as on the line-up page: the order of `TEN` in `sheets.py`.

## What to do with the result

- **Pass** (`top` at least 8 of 10 and at least 3 more than `today`): go on to steps 3 to 5 of the plan, as
  issues, and replace the "read, not traced" row in DECISIONS as that section says.
- **Fail:** the front-view work stops. Record the result in BACKLOG and DECISIONS.
- **The turn** is taken up (step 6) only if the owner says the stance looks natural and `turn` is higher than
  `top`.
- The misses say which pairs were confused. If only the white pair is missed, the gap is drawn laces and seams
  on a shoe of one colour, which the stand-in does not draw (see below), not the method.

## How to run it again

```
python -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
# the cut-out model (about 170 MB) into bench/models/: its address and checksum are in backend/closet/cutout.py
cd bench/experiments/shoe_front
python fetch.py          # photos into bench/private/shoe_front/photos/<key>/<VIEW>.jpg, and report.json
python top.py            # each photo from above cut out, one shoe kept, turned toe down: top/_contact.png
python sheets.py         # every variant for the ten pairs: out/all.png
python page_assets.py    # the page's pictures: page/assets/*.png
```

PNGs are made with Chromium (`tools/make_figure_sheet.to_png`). To publish the page again, put `lineup.html`
next to the `assets` folder and publish both; passing the artifact's link updates the same page.

`SHOE_FRONT_WORK` and `SHOE_FRONT_MODELS` move the working folder and the model folder.

## What each file does

| File | What it does |
|---|---|
| `fetch.py` | Searches one shop for each shoe, reads which view each photo is from the page, downloads side, front, top and pair photos. The shoe found is whatever the shop lists first, so some keys name a shoe that is not the one found (`af1` is a grey mesh runner, `kswiss` a black skate shoe). |
| `common.py` | The shoes' tags (category, style, colour) as the tagger would give them, and the side trace of each, made by the app's own tracer and cached. |
| `top.py` | A photo from above: cut out, one shoe of a pair kept, turned so the toe points down, cropped. |
| `drape.py` | The stand-in for step 4. Flattens the photo from above to six colours and paints it over the upper's top surface from the top of the tongue to the toe, inside the template's outline, on top of "From your photo". `THROAT` is where the tongue's top is on each photo, read off by eye. `set_turn` changes the toe-out angle. |
| `sheets.py` | One sheet of all variants: the two views of today, smaller clean-up limits, the photo laid on, and turns of 20° and 30°. |
| `page_assets.py` | The pictures for the line-up page, at three times phone sharpness. |
| `lineup.html` | The page: 30 shuffled pictures, the score against the pass mark, the stance question, a result to copy. |

## What is rough about the stand-in

- It replaces three functions of `frontshoe` while it runs (`_Traced.paint`, `_details`, `_Traced.lacing`). A real
  build would not do that.
- No laces, seams or toe-cap lines are drawn over the photo, so a shoe of one colour (white laces on a white
  shoe) shows almost nothing.
- A boot's shaft is left as today's drawing; only its vamp takes the photo.
- The photo is laid on by its share of the length and its share of the width at each step. A single shoe
  photographed a little from the side (half the photos) is therefore slightly skewed.
- Which side of the photo is the inner side is guessed from where the toe's tip leans.
- The tracer's own colour flattening (`trace.quantise`) joins a colour with its shade, which turned grey suede
  white on these photos; `drape.py` uses plain k-means instead. Step 4 needs a flattening of its own.

## Found on the way, not fixed

- A penny loafer whose trace was taken for a derby is drawn with laces in "From your photo".
- Today's reader of the second photo (`drawing/frontlook.py`) returned nothing for photos from above, and read
  white laces on a black shoe as the vamp's colour.
