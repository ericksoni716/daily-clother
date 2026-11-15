# Archetype first: draw one shoe from its photos

Work only in this folder. Read BRIEF3.md and follow it (frame, view, style, build order, feature sheet, the liked
examples in EXAMPLES/), with these changes. You are given a shoe number N and an output name OUT. Do not read any
other drawing of this shoe.

1. In the feature sheet (`OUT.json`) add "archetype": the most specific kind of shoe a footwear designer would call
   this (for example "max-cushion recovery running shoe with a thick foam midsole", "plain-toe chukka", "court
   sneaker"), and "archetype_front": three or four sentences describing how THAT KIND of shoe looks from the front
   and a little above, from what you know: its outline, how the sole relates to the upper, where its bulk is.
2. Draw the archetype's front silhouette first, from that knowledge. Then fit it to this shoe: its colours, parts
   and proportions from the photos. The silhouette should be the archetype's, corrected by the photos, never a
   generic rounded blob. Keep the toe box broad but not bulbous: check its outline against above.jpg.
3. Write `OUT.left.svg` (the viewer's-left shoe). If the shoe has a logo or mark on one side only, also write
   `OUT.right.svg`: the viewer's-right shoe in the same frame (x 0 to 200, centred on 100), with the mark on its
   OUTER side and reading the right way round, not mirrored. Draw a letter-shaped logo so the letter can be read.
4. Check: `node render3.js OUT` then Read `OUT.png`; compare with front.jpg, above.jpg and the liked examples. At
   most three rounds.

Report back ONE short line: `archetype | rounds | the worst thing still wrong`.
