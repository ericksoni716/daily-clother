# Landmarks from Claude (experiment)

Asked of each cutout (on a plain background, at most 1024 px), with a JSON schema for the answer:

> Look at the image NAME.jpg with the Read tool. It is a shirt photographed from the front. Give pixel
> coordinates in that image (x from the left, y from the top) of: the centre of each visible front button
> (button_line, top to bottom); the centre of the neckline where the collar meets at the front (neck_center);
> the centre of the front hem, the bottom edge below the buttons (hem_center). Be as precise as you can.

Schema: `{button_line: [{x, y}], neck_center: {x, y}, hem_center: {x, y}}`.

On five test shirts (crumpled flannel, a plaid on a bed, a dress shirt with its front folded back, a
pinstripe), both the larger model and the tagging model put every button on the button strip; the two agree
on the button line within 0.3% of the width. Neck and hem are less steady with the tagging model (up to about
13% of the neck-to-hem length apart on a small photo), so the height of a placed pattern is better anchored
on a button.

Image-only ways to find the button line were tried and dropped: the column where the flattened plaid is most
interrupted (finds pocket edges), and round shapes in a row (patterned cloth is full of them).

## Sleeves

A second question asks for the underarm points (where each sleeve's lower seam meets the side seam) and the
shoulder points. A sleeve is the garment beyond the line from shoulder to underarm, and beyond the side line
below the underarm. An underarm point must lie on the outline (within 6% of the garment's width of the
edge) or the answer is not used. On a 250 px polo photo the tagging model put the underarms on the chest;
the larger model got them right; both were right on a 1000 px photo. Whether placed bands continue onto the
sleeves (`stripes.sleeves_carry_bands`): the sleeves must carry at least 60% of the body's share of band
colours. Real polo: 4.9% against 18.7% on the body (plain sleeves, correct; 8.1% with the tagging model's
rougher points, still correct); the same polo with its band copied across the sleeves: 30% (continues, correct).
