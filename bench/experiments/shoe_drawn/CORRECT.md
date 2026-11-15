# Correction step: redraw one shoe from the owner's note

Work only in this folder. First read BRIEF3.md (the frame, the view, the style and the build order all still apply)
and look at the three liked examples in EXAMPLES/ and your shoe's photos in `shoe-N/`.

You are given: a shoe number N, a STARTING drawing (an .svg in this folder, with its .json feature sheet and .png),
the owner's NOTE, and an output name OUT.

1. Read the starting drawing's .png, .svg and .json, and the photos.
2. Copy the feature sheet to `OUT.json`, adding a field "owner_notes": [the note] and changing whatever the note changes.
3. Redraw: write `OUT.left.svg` (the viewer's-left shoe, in the frame). Change ONLY what the note asks for and what
   must change with it; keep everything else of the starting drawing as it is (same shapes where possible).
   If the shoe has a logo or mark on one side only, also write `OUT.right.svg`: the viewer's-right shoe drawn in the
   same frame (x 0 to 200, centred on 100), NOT a mirror image where that would flip the mark: on a real pair the
   mark is on the OUTER side of each shoe and reads the right way round on both. If there is no such mark, write no
   right file (the preview mirrors the left one).
4. Check: `node render3.js OUT` then Read `OUT.png`. Compare with the starting .png and the photos: is the note
   answered, and is everything else unchanged? At most three rounds.

Report back ONE short line: `what changed | rounds | anything the note asked for that you could not do`.
