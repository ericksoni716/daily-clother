# Brief: draw one shoe as flat clip art from its photos (round 3)

Work only in this folder (DIR = the folder this file is in). No web, no installs. Do not read any other run's files
(`shoe-*-r*.*`, `shoe-*-v*.*`, `shoe-N.svg`, `shoe-N.png`). You are given a shoe number N and a run number R; your
files are `shoe-N-vR.json`, `shoe-N-vR.svg`, `shoe-N-vR.png`.

## Look first
1. The three drawings the owner liked, in `EXAMPLES/`: `trainer.png`, `dress-shoe.png`, `boat-shoe.png` (Read them),
   and their sources `trainer-full.svg`, `dress-shoe.svg`, `boat-shoe.svg` (Read them to see how few shapes they use
   and in what order). They are examples of the STYLE and the CONSTRUCTION, not of your shoe: do not copy their shapes.
2. Your shoe's photos, cropped: `shoe-N/side.jpg` (outer side), `above.jpg`, `front.jpg`, `back.jpg`, `inner.jpg`.
   (Shoe 5's side.jpg runs off the frame at the toe: use inner.jpg for the profile.) Ignore dirt, wear, shade,
   highlights and the floor.
3. `shoe-N/guide.json`: numbers measured from the photos: `height_cm` (ground to the highest point) and `width_cm`.

## Step 1: the feature sheet -> `shoe-N-vR.json`
- "kind": what it is; name the model or style family if you recognise it, and how sure you are.
- "silhouette": toe (round / almond / pointed / wide), bulk (slim / regular / chunky), height (low / ankle / boot),
  sole (thin / medium / thick; flat / wedge / rocker / heeled / lug).
- "proportions": by eye from front.jpg and above.jpg: how thick the sole's front edge is compared with the toe box
  above it; whether the sole stands out past the upper and by how much; how the toe's outline runs seen from above.
- "palette": 2 to 6 entries {"name", "hex", "role"}: the shoe's few TRUE colours. One material is one colour.
- "parts": each {"part", "colour", "where", "seen_from_front"}.
- "signature": the 2 to 4 things that make it recognisable from the FRONT at small size.

## Step 2: the drawing -> `shoe-N-vR.svg` (bare SVG elements only: no <svg> wrapper, no header)
ONE shoe, the viewer's left, pointing straight at the viewer, seen from the front and a little above.

### The view, as a 3D object flattened
The toe is nearest the viewer, so it is the lowest and the largest thing in the picture. Everything further back
sits higher and is partly hidden by what is in front of it:
- at the bottom, the sole's front edge: a band that follows the toe's outline;
- above it, the TOE BOX: its front face and its top surface, a broad dome. This is the biggest shape;
- above that, the vamp and the lacing (or the plain instep) sloping up and away, getting narrower;
- then the tongue top or the collar's front edge, where the leg goes in;
- a boot is NOT a tube: it is the same toe box and instep in front, with the shaft rising BEHIND them, narrower than
  the toe box, starting where the instep meets the leg. From the front you see the toe box below and the shaft above,
  with a clear break (the instep's slope, a crease or seam line) between them.

### The frame (about 17 units per cm)
- x 0 to 200, centred on x = 100; the shoe at most about 180 wide. Ground: y = 240 (the sole's lowest point).
- A leg (x = 62 to 138, in a sock) is drawn behind your shoe by the preview script, down to y = 60.
- A low shoe: the whole shoe sits between about y = 40 and y = 240; the tongue top or collar front crosses the leg at
  about y = 40 to 60 (a very low shoe such as a boat shoe or loafer: nearer 60). Do not make a low shoe taller than
  this: the liked examples are about as tall as they are wide.
- An ankle boot: the toe box and instep fill about y = 110 to 240; the shaft rises behind them to a top edge at about
  y = -30 to -50 (use `height_cm`: 18 cm is about -40), a little wider than the leg, narrower than the toe box.
- Where the leg goes in, draw the opening's front edge as a curve dipping across the leg, and bring the collar's or
  shaft's sides up a little higher at each side of the leg than at the middle, so the leg sits IN the shoe.

### How to build it (the order the liked examples use)
1. The sole's front edge: one crescent band along the bottom, in the sole's colour, with the bold outline.
2. The upper's whole silhouette on top of it, in the main colour, with the bold outline.
3. The few panels of another colour, each one closed shape with a thin outline, lying inside the silhouette.
4. Seams that define the shoe (a toe cap line, a moccasin seam, a boot's instep seam): thin lines.
5. The tongue and the lacing, last, in front of the leg.
6. The upper's bold outline once more over everything.

### Style (strict)
- Flat fills in the palette's hex values. No gradients, shadows, textures or highlights. No lettering.
- Bold outline: stroke #26221f, width 4, round joins. Inner lines: width 1.6.
- Few shapes: draw a detail only if it shows from the front AND helps someone recognise the shoe.
- Keep to what the photos show. The sole's front edge is as thick as it looks in front.jpg, no thicker. A sole stands
  out past the upper only as far as it does in above.jpg. Outsole rubber is drawn climbing the toe only as far as
  front.jpg shows it.
- It must still read at 45 px tall. Every id starts with `sN-vR-`.

## Check by looking (at most three rounds)
`cd DIR && node render.js shoe-N-vR.svg shoe-N-vR.png`, then Read the PNG. Compare with front.jpg and with the liked
examples. Ask: does it have the examples' simplicity? Is the toe box the biggest, nearest shape? Would a stranger
name the same shoe from the photo and the drawing? Fix and render again.

## Report back: ONE short line only
`kind | rounds used | the worst thing still wrong`. Nothing else.
