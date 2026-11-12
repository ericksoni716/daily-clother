# Menswear Reference for Rendering

A field guide to men's clothing for a system that must **name, describe, combine and draw** garments. It is written to work without internet access: everything the renderer needs to know about what a garment *is* and what it *looks like* lives here.

The companion file `menswear-taxonomy.json` holds the same axes as enums plus validity rules, so code can enumerate permutations and reject impossible ones.

---

## 0. How to read this guide

### 0.1 The attribute model

Every garment is a stack of independent axes. Most permutation errors come from collapsing two axes into one ("flannel" is a fabric finish, not a pattern; "Oxford" is a weave, not a collar).

```
Garment
├── category          shirt, polo, t-shirt, sweater, jacket, trouser …
├── type              dress shirt, camp-collar shirt, henley, cardigan …
├── silhouette / fit  slim, regular, relaxed, boxy, cropped, oversized
├── sleeve & length   short, long, 3/4, sleeveless; cropped, regular, longline
├── construction      collar, placket, cuffs, pockets, yoke, pleats, hem, closures
├── fabric
│   ├── fiber         cotton, linen, wool (merino, lambswool, shetland…), yak, cashmere, silk, synthetics
│   ├── structure     weave (plain, twill, oxford, satin…) or knit (jersey, piqué, rib, cable…)
│   ├── weight        gsm / oz / gauge / wale count
│   └── finish        brushed, garment-dyed, enzyme-washed, waxed, mercerised…
├── color             base color, heathering, two-tone yarns, fade/wash
├── pattern           stripe, check, plaid, print, knitted motif — with scale & orientation
├── surface graphics  screenprint, embroidery, patch, appliqué, puff print …
└── condition         crisp/new, worn-in, faded, distressed, wrinkled
```

### 0.2 Rendering vocabulary

Every fabric entry below describes these visual properties. Use them as the "physics" of the image.

| Property | Meaning | Low end | High end |
|---|---|---|---|
| **Drape** | How it falls under gravity | Stiff, holds shape, tents (canvas, raw denim) | Fluid, clings, pools (silk, viscose, fine jersey) |
| **Sheen** | Specular highlight | Dead matte (brushed flannel, moleskin) | Lustrous (satin, sateen, silk, mercerised cotton) |
| **Texture scale** | Size of visible surface structure | Invisible at arm's length (poplin) | Bold relief (chunky cable, wide-wale cord) |
| **Halo / fuzz** | Fibers standing proud of the surface | Clean edge (worsted wool, poplin) | Soft blurred silhouette (mohair, brushed alpaca, yak) |
| **Opacity** | See-through-ness | Fully opaque (heavy flannel) | Semi-sheer (voile, light linen, fine jersey under light) |
| **Wrinkle behavior** | How creases form | Few soft folds (knits, wool) | Sharp, many crumples (linen, poplin) |
| **Edge thickness** | Visible thickness at hems, collars, cuffs | Paper thin (voile) | Chunky (shawl-collar cardigan, heavyweight sweatshirt rib) |
| **Color depth** | How color sits in the fabric | Flat solid | Heathered, slubby, two-tone (warp/weft), faded |

**Rule of thumb:** the heavier and more textured the fabric, the more it (a) holds its own shape, (b) shows thicker edges, (c) has softer, rounder folds, and (d) reads matte.

---

## 1. Fibers

What the fabric is made from. Fiber sets sheen, halo, color character and wrinkling. Structure (section 2–3) sets texture.

### Plant fibers
| Fiber | Visual signature | Notes for rendering |
|---|---|---|
| **Cotton** | Matte to soft sheen, clean surface | The default. Mercerised cotton gains a silky luster and richer color. Brushed cotton goes matte and soft-edged. |
| **Linen** | Visible **slubs** (thick-thin irregular yarns), dry matte luster, **heavy crumpled wrinkling**, slightly crisp drape | Colors look slightly chalky/washed. Natural undyed linen = oatmeal/flax beige. Almost always plain weave. Summer fabric. |
| **Cotton-linen blend** | Linen look with fewer, softer wrinkles | Good "polished summer" default. |
| **Hemp** | Like a coarser, stiffer linen | Rare; rustic. |
| **Ramie** | Like linen with more luster | Rare. |

### Animal fibers
| Fiber | Visual signature | Notes |
|---|---|---|
| **Merino wool** | Smooth, fine, **matte with a faint soft sheen**, clean stitch definition, drapes close to body | Used for fine-gauge knits (12–18gg) and fine suiting. Thin, light-reflecting. Never fuzzy unless brushed. |
| **Lambswool** | Soft, light fuzz, slightly fuller than merino | Mid-gauge everyday sweaters. |
| **Shetland wool** | **Hairy, rustic**, slight scratchiness visible as stray fibers, often **heathered** (multi-tone flecks) | Classic crewneck in heathered greens, oatmeal, navy. Often "shaggy" (brushed) version. |
| **Cashmere** | Very soft, **fine downy halo**, rich color, slight luster | Drapes softly; edges slightly blurred. Usually fine to mid gauge. |
| **Yak** | **Soft halo**, warm matte, natural colors are **brown, taupe, grey**; slight hairiness | Often in chunky or mid-weight knits. Feels like cashmere, looks a bit more rustic. |
| **Camel hair** | Golden-tan natural color, soft sheen, slight nap | Coats and sport coats more than sweaters. |
| **Alpaca** | Silky with a **strong halo**; "brushed alpaca" is very fuzzy and airy | Fuzzy cardigans, loose knits. |
| **Mohair** | **Long shiny hairs**, pronounced glowing halo, often semi-sheer in loose knits | In suiting (mohair blends) it gives a crisp, slightly shiny, iridescent look instead. |
| **Angora** | Extremely fuzzy halo | Rare in menswear. |
| **Worsted wool** | Smooth, clean, flat, fine — combed long fibers | Suiting, dress trousers. Crisp edges, sharp creases. |
| **Woolen-spun wool** | Fuzzier, fuller, matte | Tweed, flannel, most rustic knitwear. |
| **Silk** | High luster, fluid drape, rich color | Ties, pocket squares, some shirts; noil/raw silk is matte and nubby. |

### Synthetics & regenerated
| Fiber | Visual signature |
|---|---|
| **Polyester** | Uniform, slight plasticky sheen, smooth; in fleece = puffy matte pile |
| **Nylon** | Smooth, often shiny; technical shells, puffer jackets, windbreakers, ripstop |
| **Acrylic** | Imitates wool; slightly too uniform/shiny; pills |
| **Elastane / spandex** | Invisible; makes garments cling and stretch (stretch chinos, stretch denim) |
| **Viscose / rayon / lyocell (Tencel) / modal** | Fluid drape, soft sheen, cool hand. Rayon is common in camp-collar and Hawaiian shirts — prints look vivid and the fabric drapes and swings. |

---

## 2. Woven fabrics

Woven = warp and weft yarns interlaced at right angles. Shirts, trousers, jackets, suits.

### 2.1 Basic weave structures

| Weave | Structure | Visual |
|---|---|---|
| **Plain weave** | Over 1, under 1 | Flat, even grid; no diagonal. |
| **Basketweave** | Pairs of yarns as one | Tiny checkerboard texture (the basis of Oxford cloth). |
| **Twill** | Each pass shifts one thread → **diagonal ribs** | Diagonal lines visible up close; drapes and resists wrinkles better than plain weave. |
| **Herringbone** | Twill that reverses direction in columns | **Vertical columns of V / zigzag**. |
| **Satin / sateen** | Long floats | Smooth, lustrous face. |
| **Dobby** | Small geometric woven figures | Tiny dots, diamonds, or micro-checks woven in (not printed). |
| **Jacquard** | Complex woven pictures/figures | Large woven motifs; brocade, damask. |
| **Leno / gauze** | Twisted warp pairs | Open, airy, see-through. |

### 2.2 Shirting fabrics

Ordered roughly from dressiest to most casual.

| Fabric | Structure | Weight | Visual signature | Typical garments |
|---|---|---|---|---|
| **Poplin / broadcloth** | Fine plain weave | Light (90–120 gsm) | Smooth, crisp, **slight sheen**, almost no visible texture; wrinkles sharply | Dress shirts, business shirts |
| **Twill shirting** | Fine twill | Light-mid | Soft subtle diagonal, slight sheen, drapes better than poplin | Dress shirts |
| **Herringbone shirting** | Fine herringbone | Light-mid | Subtle vertical zigzag visible on close-up | Dress shirts |
| **Pinpoint oxford** | Fine basketweave | Mid | Smooth with a very fine dotted texture; between poplin and Oxford | Business-casual shirts |
| **Royal oxford** | Basketweave with dobby figure | Mid | Pronounced, shiny, textured; dressy | Dress shirts |
| **Oxford cloth** | 2-over-1 basketweave, **colored warp + white weft** | Mid (120–160 gsm) | **Visible pebbly texture**, soft matte, slightly **heathered/two-tone** look (blue Oxford is pale blue speckled with white). Collar rolls softly. | **OCBD** (Oxford cloth button-down), casual shirts |
| **End-on-end** | Plain weave, alternating colored and white warp | Light-mid | **Fine micro-heather** — reads solid from afar, flecked up close | Business shirts |
| **Chambray** | Plain weave, colored warp + white weft | Light-mid | **Denim-like color with a softer, lighter, flatter look**; mottled blue; inside looks similar to outside | Work/casual shirts |
| **Denim (shirting)** | Twill, indigo warp + white weft | Mid (6–8 oz) | Diagonal twill, **inside is noticeably lighter/whiter**, fades at seams and edges | Western, work shirts |
| **Linen** | Plain weave, slubby yarns | Light (100–180 gsm) | Slubs, translucency in light weights, crumpled wrinkles, dry luster | Summer shirts, camp collar, popovers |
| **Seersucker** | Slack-tension plain weave | Light | **Puckered stripes alternating with flat stripes**, usually blue/white; doesn't need ironing — never looks crisp | Summer shirts, suits, shorts |
| **Madras** | Light plain weave, hand-loomed | Very light | **Irregular, slightly bleeding bright plaids**, soft, often semi-sheer | Summer short-sleeve shirts, shorts |
| **Voile / batiste** | Very fine plain weave | Very light | Semi-sheer, soft, airy | Summer shirts |
| **Cotton flannel** | Plain or twill, **brushed (napped)** | Mid-heavy (150–250+ gsm) | **Fuzzy matte surface, soft edges, blurred pattern lines**, no sheen; drapes heavier; soft rounded folds | Flannel shirts (usually plaid but also solid) |
| **Wool flannel (shirting)** | Brushed wool | Mid-heavy | Matte, dense, soft, often **solid or heathered grey/brown**; warmer, more refined than cotton flannel | Wool shirts, overshirts |
| **Brushed twill / brushed cotton** | Twill, lightly brushed | Mid | Diagonal barely visible under a peachy soft surface | Casual shirts |
| **Corduroy (shirting)** | Cut-pile ridges ("wales") | Mid | Vertical velvety ridges; **pinwale** for shirts | Cord shirts, overshirts |
| **Canvas / duck** | Dense plain weave | Heavy | Stiff, matte, holds shape, angular creases | Work shirts, chore coats |
| **Waffle / honeycomb weave** | Woven grid relief | Mid | 3D square cells | Overshirts, robes |
| **Crepe / seersucker-crinkle** | Crinkled | Light | Fine pebbly crinkle | Summer shirts |
| **Rayon / viscose challis** | Smooth plain weave | Light | **Fluid drape, vivid prints, soft sheen** | Hawaiian/aloha, camp-collar shirts |
| **Cuban/guayabera linen or cotton** | Plain | Light | With vertical pleated panels (see guayabera) | Guayabera |

### 2.3 Bottom-weight & jacket fabrics

| Fabric | Visual signature | Typical garments |
|---|---|---|
| **Chino twill** | Clean, fine diagonal twill, slight sheen, crisp; khaki/stone/olive/navy | Chinos |
| **Gabardine** | Tight, steep twill, smooth, slight sheen, very clean | Dress trousers, trench coats |
| **Denim (bottom-weight)** | 11–16 oz twill; indigo warp, white weft; fades (whiskers at hips, honeycombs behind knees, stacking at hem) | Jeans, jackets |
| **Selvedge denim** | Same, plus **clean finished edge with a colored line (often red/white) visible at the outseam cuff when rolled** | Premium jeans |
| **Raw / dry denim** | Unwashed: deep dark uniform indigo, stiff, slight sheen, sharp creases | Jeans |
| **Corduroy** | Ridges of cut pile; see 2.4 | Trousers, jackets, shirts |
| **Moleskin** | Dense cotton, **sueded, peach-like, dead matte**, slightly darker in folds | Trousers, jackets |
| **Canvas / duck** | Heavy, stiff, matte; brown "duck" is the workwear classic; ages with fades on edges | Chore coats, work pants |
| **Ripstop** | **Small square grid** of thicker yarns | Cargo, military, technical |
| **Sateen (cotton)** | Smooth, lustrous | Trousers, fatigues |
| **Worsted wool (suiting)** | Smooth, clean, crisp creases, slight sheen | Suits, dress trousers |
| **Wool flannel (suiting)** | Brushed, matte, soft, often mid-grey; pattern lines blurred | Trousers, suits, sport coats |
| **Tweed** | Rough, hairy, multi-colored flecks; heavy; holds shape | Sport coats, caps, overcoats |
| — Harris tweed | Hand-woven, deeply **heathered** with many flecked colors | |
| — Donegal tweed | Base color with **colored slubs/nubs ("neps")** scattered randomly | |
| — Herringbone tweed | Bold herringbone in tweed yarns | |
| — Barleycorn / bird's-eye | Small textured repeating dot/grain | |
| **Hopsack** | Open basketweave, breathable, small grid texture | Summer blazers |
| **Fresco** | High-twist open plain weave, crisp, slightly grainy | Summer suits |
| **Cavalry twill** | Steep, **pronounced double diagonal ribs** | Trousers |
| **Whipcord** | Steep pronounced diagonal cords | Trousers, riding wear |
| **Velvet / velveteen** | Short dense pile, deep color, light catches as bright highlights | Dinner jackets, slippers |
| **Melton** | Dense, felted, smooth, no visible weave | Peacoats, overcoats, varsity bodies |
| **Boiled wool** | Felted knit, dense, slight texture | Jackets |
| **Waxed cotton** | Dark, slightly **mottled oily sheen**, crinkly creases that lighten at folds | Waxed field jackets |
| **Nylon (shell)** | Smooth, can be shiny or matte; puffy if insulated | Puffers, windbreakers, parkas |
| **Leather** | Grain visible; smooth sheen or matte; creases at elbows | Jackets |
| **Suede** | Matte, napped, color shifts when brushed | Jackets, shoes |
| **Shearling** | Suede exterior, **woolly curly fleece** at collar/lining | Jackets, coats |
| **Polar fleece** | Puffy matte pile, soft rounded edges | Fleece jackets |
| **Sherpa / high-pile fleece** | Curly, nubby, cloud-like | Jackets, linings |

### 2.4 Corduroy wale guide

Wale = one ridge. Measured in wales per inch (wpi). **Fewer wales = wider ridges = chunkier, more casual.**

| Name | Wales/inch | Visual | Typical use |
|---|---|---|---|
| **Needlecord / pinwale / babycord** | 16–21+ | Ridges barely visible; reads almost like velvet or moleskin; drapes softly | Shirts, lightweight trousers |
| **Fine / standard** | 11–15 | Clearly visible thin ridges | Trousers, jackets |
| **Mid** | 8–10 | Pronounced ridges | Trousers, jackets |
| **Wide wale** | 6–8 | **Bold ridges** with deep grooves, very tactile | Trousers, jackets, overshirts |
| **Jumbo / elephant cord** | 1.5–5 | **Chunky rope-like ridges**, very visible from afar | Statement trousers, jackets |

"Thin corduroy" and "pincord" are everyday names for needlecord/pinwale.

Rendering notes: ridges run **vertically** on almost all garments. Pile catches light → each ridge has a bright crest and a dark groove, and the color shifts lighter or darker depending on the viewing angle (looking along the pile vs against it). Wear shows as shiny, flattened pile at knees and seat.

---

## 3. Knit fabrics

Knit = one yarn looped into interlocking rows. Stretchy, softer folds, curling edges.

### 3.1 Cut-and-sew knits (tees, polos, sweats)

| Knit | Visual signature | Typical garments |
|---|---|---|
| **Single jersey** | Smooth face with fine "V" columns; slightly rougher back; edges curl | T-shirts, henleys |
| **Slub jersey** | Jersey with irregular thick/thin streaks — **subtly mottled, vintage** | Tees, henleys |
| **Interlock** | Double-faced, smooth both sides, heavier, less curling | Premium tees, polos |
| **Piqué** | **Honeycomb / waffle-dot texture**, breathable, matte | **Classic polo** |
| **Waffle / thermal** | **Small grid of square cells** (larger than piqué) | Thermals, henleys |
| **Rib (1x1, 2x2)** | **Vertical ribs**, very stretchy, clings | Neckbands, cuffs, hems, ribbed tanks, ribbed tees |
| **French terry / loopback** | Smooth face, **small loops on back** | Sweatshirts, hoodies, sweatshorts |
| **Fleece-back (brushed)** | Smooth face, **fuzzy brushed back** | Heavy sweatshirts, hoodies |
| **Ottoman / ottoman rib** | Horizontal ridges | Fashion tops |
| **Mesh / eyelet knit** | Visible holes | Athletic jerseys, retro polos |
| **Velour / terry towelling** | Plush pile | 70s polos, resort shirts |

#### T-shirt / jersey weight scale
| Class | gsm | Visual |
|---|---|---|
| Lightweight | 120–160 | Thin, drapey, clings, can be slightly see-through in white, collar may ripple |
| Midweight | 160–200 | Standard; soft folds |
| Heavyweight | 200–260 | Holds shape, boxier, thicker neckband, fewer small wrinkles |
| Super-heavy | 260–320+ | Almost stiff, **structured boxy silhouette**, thick rib collar, "vintage workwear" look |

### 3.2 Sweater knits (fully fashioned / knitwear)

**Gauge** = needles per inch on the knitting machine. Higher gauge = finer, thinner, smoother.

| Gauge | Name | Visual | Typical fibers |
|---|---|---|---|
| 14–18gg+ | Extra fine | Smooth, thin, near-woven look; individual stitches invisible from afar; lies flat under a blazer | Merino, cashmere, silk blends |
| 12gg | Fine | Thin, clean, visible fine stitch | Merino, cotton, cashmere |
| 7–9gg | Medium | Classic everyday sweater; visible stitches; moderate thickness | Lambswool, cashmere, cotton |
| 5gg | Chunky | Pronounced stitches, thick edges | Lambswool, yak, Shetland |
| 1.5–3gg | Super chunky | Huge loops, very thick, bulky silhouette | Yak, chunky wool, alpaca |

### 3.3 Sweater stitches & knitted patterns

| Stitch / pattern | Visual |
|---|---|
| **Jersey stitch (flat knit)** | Smooth face of small V's — default sweater |
| **Rib knit (1x1, 2x2, 3x3)** | Vertical ribs throughout; clingy; often used on trims |
| **Fisherman's rib** | Plump, deep, spongy rib; thick, lofty |
| **Shaker stitch** | Very thick, **pronounced vertical ribs, chunky**; nautical/Americana |
| **Cable knit** | **Twisted rope-like columns** raised from the surface |
| **Aran / fisherman sweater** | Dense combination of cables, honeycomb, diamonds, moss stitch; traditionally **undyed cream (bainin) wool**; crewneck |
| **Moss / seed stitch** | Bumpy rice-grain texture |
| **Waffle knit (sweater)** | Square cells, thermal look |
| **Basketweave knit** | Woven-looking blocks |
| **Garter stitch** | Horizontal ridges |
| **Brioche** | Plush, two-tone ribs |
| **Pointelle** | Small decorative holes |
| **Fair Isle** | **Multiple colors, small repeating bands of motifs**, often concentrated at a **circular yoke** around the shoulders, or all-over |
| **Nordic / Norwegian** | Two-color (often navy/red + white) **snowflake/star motifs**, lice-pattern dots, yoke bands |
| **Argyle** | **Diamonds with thin diagonal overcheck lines** (intarsia) — golf/prep |
| **Intarsia** | Blocks or pictures of solid color (no floats inside) — logos, motifs, argyle |
| **Jacquard knit** | All-over multi-color patterns, floats inside |
| **Guernsey / gansey** | Dense, tightly knit navy wool, subtle textured yoke, small side vents |
| **Cowichan** | Very chunky, **graphic motifs (eagles, geometric bands)** in natural cream/brown/charcoal, often **shawl collar + zip** |
| **Marled / melange** | Two different-color plies twisted together → **speckled/barber-pole tweedy look** |
| **Heathered** | Pre-dyed fibers blended → **soft multi-tone flecking** |
| **Donegal knit** | Base color with **colored flecks/nubs** |
| **Brushed** | Fuzzy halo, blurred stitches (brushed Shetland, brushed mohair, brushed alpaca) |

---

## 4. Garment types

Each entry: **anatomy** (what defines it), **variants**, **valid fabrics**, and **render cues**.

### 4.1 T-shirts and knit tops

**T-shirt**
- Anatomy: no collar, no placket; rib neckband; set-in sleeves; straight hem.
- Necklines: **crew** (round, close), **V-neck**, **scoop**, **mock neck**, **boat neck**.
- Sleeves: short, long (long-sleeve tee), 3/4 (raglan baseball tee), sleeveless (tank).
- Fits: slim, regular, relaxed, **boxy** (wide, cropped body, dropped shoulders), oversized.
- Variants:
  - **Pocket tee** — single chest patch pocket on the left.
  - **Ringer tee** — contrasting color rib at neck and sleeve hems.
  - **Raglan / baseball tee** — sleeves in contrast color, diagonal seams from neck to underarm, usually 3/4 sleeve.
  - **Henley** — see below.
  - **Breton / mariniere** — boat neck, **horizontal navy stripes on white (or ecru)**, often long or 3/4 sleeve, stripes stop above the chest/below the shoulder on classic versions.
  - **Graphic tee** — any tee with print (see section 7).
  - **Thermal** — waffle knit, long sleeve, often a henley placket.
  - **Muscle / tank** — sleeveless; wide armholes.
- Fabrics: jersey (all weights), slub jersey, interlock, waffle, rib, piqué (rare), linen jersey.
- Render cues: neckband thickness scales with weight. Light tees show body; heavyweight tees stand away and look boxy. Shoulder seam sits on shoulder (regular) or drops onto the arm (boxy/oversized).

**Henley**
- Anatomy: collarless round neck with a **short buttoned placket** (2–5 buttons; 3 most common).
- Variants: short or long sleeve; jersey, slub, **waffle/thermal**, rib; sweater-knit henley (knitwear version); **rugged heavyweight henley**.
- Buttons: plastic, horn, or metal (workwear look), sometimes left unbuttoned.
- Render cues: placket is about 4–6 in long; top button often undone; neckband continues around placket.

**Polo shirt**
- Anatomy: **knit**, **flat-knit (rib) collar**, **2–3 button placket**, short sleeves with **ribbed armbands** (classic) or hemmed sleeves; often **"tennis tail"** (back hem longer than front) and side vents.
- Variants:
  - **Piqué polo** — the classic; honeycomb texture.
  - **Jersey polo** — smoother, drapier.
  - **Long-sleeve polo** — ribbed cuffs.
  - **Knit polo / sweater polo** — knitwear-gauge (often 12gg merino/cotton), can have a **knit collar that spreads open**, ribbed waistband or straight hem.
  - **Johnny-collar polo** — **no buttons**, open V-shaped placket with a spread collar.
  - **Open-knit / textured knit polo** — visible stitch patterns, retro 50s-60s look.
  - **Rugby-style polo** — woven collar (see rugby).
  - **Zip polo** — short zip instead of buttons.
  - **Camp-collar knit / resort polo** — flat spread collar without a stand.
  - **Terry towelling polo** — looped pile, retro resort.
- Logos: small embroidered chest logo on the left is classic.
- Render cues: collar is soft and can curl; sleeves end mid-bicep with a snug rib band; buttons usually 2–3 with the top undone.

**Rugby shirt**
- Anatomy: **heavy cotton jersey** body, **white woven twill collar** (contrasting), **rubber or plastic buttons** on a reinforced placket, long sleeves, often reinforced shoulders.
- Patterns: **wide horizontal "hoops" (stripes)**, or solid with chest panel ("quartered"/"halved").
- Render cues: thick, structured, slightly boxy; collar stiffer than a polo.

**Tank top / singlet**: sleeveless; rib or jersey; wide or narrow straps.

### 4.2 Woven shirts

#### Shirt anatomy (applies to all button-ups)
```
collar (leaf + stand)
├── yoke (shoulder panel; back yoke single or split)
├── front placket (or French front / hidden)
├── chest pocket(s) (optional)
├── sleeves: set-in; sleeve placket ("gauntlet") with small button
├── cuffs (long sleeve) or hemmed sleeves (short sleeve)
├── back: plain, box pleat, side pleats, locker loop
└── hem: curved shirt-tail (tucked) or straight with side vents (untucked)
```

**Dress shirt (business / formal)**
- Collars: **point, spread, semi-spread, cutaway**, club, tab, pin, wing (formal); **collar stays** keep points flat and sharp.
- Cuffs: **barrel** (1–2 buttons), **French/double cuff** (folded back, cufflinks), convertible, mitred (angled corners).
- Fabrics: poplin, broadcloth, twill, herringbone, pinpoint, royal oxford, end-on-end, dobby, fine stripes and checks.
- Colors/patterns: white, light blue, pink, lavender; bengal/pencil/hairline stripes; small checks, tattersall.
- Fit: slim, regular/classic, tailored; long curved tail for tucking.
- Render cues: crisp, smooth, slight sheen; sharp collar points; tucked; often worn with tie.

**Oxford cloth button-down (OCBD)**
- Anatomy: Oxford cloth, **button-down collar** (small buttons fasten collar points), chest pocket, **box pleat + locker loop** at back (traditional), long curved tail.
- Signature: **collar roll** — a soft S-curve where the collar meets the buttoned point.
- Colors: white, blue, pink, ecru, university stripe (blue/white or red/white bold stripes).
- Render cues: slightly rumpled, soft, textured; works tucked or untucked; sleeves often rolled.

**Casual button-up shirt**
- Collar: point, button-down, spread, **band collar** (grandad, just the stand).
- Hem: straight or slightly curved for untucked wear; shorter body.
- Fabrics: Oxford, chambray, linen, flannel, cord, twill, poplin, seersucker, madras, printed cotton.
- Short-sleeve version: sleeves end mid-bicep, hemmed (no cuff) or with a **small turned-back cuff**.

**Flannel shirt**
- Fabric-defined: brushed cotton flannel (or wool flannel). Usually **plaid** (buffalo check, tartan, multi-color tartan) but solids and heathers exist.
- Details: two chest flap pockets common (one or both), button-down or point collar, barrel cuffs, sometimes **elbow patches**.
- Weight: lightweight (130–160 gsm) → heavyweight (220+ gsm "work flannel").
- Render cues: **fuzzy, matte, plaid lines softly blurred**; rounded, heavier folds; collar softer.

**Chambray / denim work shirt**
- Two chest pockets (flap or patch), sometimes pencil slot; **triple-needle stitching**; contrasting tan/yellow thread on denim.
- Render cues: mottled blue, lighter at seams and fold lines, utilitarian.

**Western shirt**
- Anatomy: **pointed front and back yokes** (often in contrasting fabric or piped), **pearl snap** closures (mother-of-pearl look), **flap pockets with sawtooth or "smile" pocket openings** (curved, arrow-tipped), **multi-snap cuffs** (3 snaps), slim fit, curved hem.
- Fabrics: denim, chambray, plaid, gingham, embroidered (rose/floral), satin (rodeo).
- Render cues: decorative yoke lines draw a V/wing shape across chest and back.

**Camp-collar shirt (Cuban collar / revere collar / bowling / resort)**
- Anatomy: **one-piece open collar with no collar stand**, lies flat and spreads out like a lapel; **straight hem** meant to be untucked; boxy/relaxed fit; short sleeves; often no back pleat.
- Fabrics: rayon/viscose, linen, cotton, Tencel, silk, seersucker.
- Patterns: solids, **Hawaiian/aloha prints**, florals, geometric, retro novelty prints, vertical-panel bowling stripes.
- **Bowling shirt**: camp collar + contrast vertical panels, chain-stitch name embroidery.
- **Hawaiian / aloha shirt**: camp collar, **large tropical prints** (hibiscus, palms, surf), coconut buttons, **pattern matched across the chest pocket**.
- Render cues: collar lies open and flat; fluid fabrics swing; boxy straight hem.

**Popover shirt**
- Pullover style: **half-placket** (3–4 buttons partway down), no full button front. Linen and Oxford common.

**Band collar shirt (grandad / mandarin)**
- Collar is only the stand — no leaf. Linen and cotton.

**Guayabera**
- Four patch pockets (two chest, two lower), **two vertical rows of fine pleats ("alforzas") down front and back**, buttons along pleats, side vents with buttons, straight hem.
- Fabrics: linen, cotton. Colors: white, cream, pastels.

**Overshirt / shirt jacket ("shacket")**
- Heavier than a shirt, worn as a light layer. Two chest pockets (flap or patch), sometimes lower hand pockets; straight hem; shank or snap buttons.
- Fabrics: wool flannel, melton, cord (wide wale), moleskin, canvas, quilted, plaid wool.
- **CPO shirt** — navy-origin overshirt: **wool**, two **flap patch chest pockets**, plain-colored or plaid, shank buttons.

**Work shirt**
- Durable twill or canvas, two flap chest pockets, pencil slot, triple stitching, often in khaki/navy/grey/green; name patch.

**Tuxedo / formal shirt**
- Pleated or **piqué bib front**, **wing or turndown collar**, French cuffs, studs instead of buttons.

### 4.3 Sweatshirts and hoodies

**Crewneck sweatshirt**
- French terry or fleece-back. Ribbed neckband, cuffs and waistband.
- Details: **"V-insert" / "dorito"** triangle below the neckline (one or both sides), **raglan sleeves** (diagonal seams) or set-in, **side gussets** (rib panels down the sides — "reverse weave" style), **flatlock stitching** (raised seams).
- Graphics: college arch print, flocked letters, screenprint, embroidered logos.
- Heather grey is the canonical color.
- Render cues: soft, thick folds; rib bands gather the cuffs and hem; slightly boxy.

**Hoodie**
- Pullover with **kangaroo pocket** or zip-up with two side pockets; drawcord hood, metal or tipped aglets; lined or unlined hood.
- Render cues: hood lies on the back in folds; drawcords hang; thick rib cuffs.

**Quarter-zip / half-zip**: high collar with short zip; in fleece, sweatshirt, or knitwear.

### 4.4 Knitwear (sweaters)

**Necklines**
| Name | Description |
|---|---|
| **Crewneck** | Round, close to base of neck, ribbed |
| **V-neck** | Deep or shallow V; shows shirt collar underneath |
| **Turtleneck / rollneck** | Tall tube folded over (rollneck) |
| **Mock neck / funnel neck** | Short stand, not folded |
| **Shawl collar** | Wide rolled collar continuing down a V or cardigan front |
| **Boat neck** | Wide, shallow across collarbones |
| **Half-zip / quarter-zip** | Zip at the neck, collar stands |
| **Polo collar** | Knitted shirt collar (see knit polo) |
| **Henley** | Button placket at neck |
| **Mock henley / funnel with buttons** | Stand collar with buttons |

**Types**
- **Pullover sweater** — any of the necklines above.
- **Cardigan** — opens down the front; 5–6 buttons; **V-neck or shawl collar**; ribbed button band; optional patch pockets; leather-knot or horn buttons.
- **Zip cardigan / zip-up sweater** — full zip, often with stand collar.
- **Sweater vest / slipover** — sleeveless, V-neck usually; cable or argyle; ribbed armholes.
- **Tennis / cricket sweater** — cream cable-knit V-neck with **contrasting stripe trim** at neck and waist.
- **Varsity cardigan / letterman cardigan** — shawl collar, chenille letter patch.
- **Army sweater / commando** — rib knit, **shoulder and elbow patches** (twill), epaulettes.
- **Ski sweater** — Nordic patterns.

**Construction details**
- **Saddle shoulder** — a strip of the sleeve extends across the top of the shoulder to the neck.
- **Raglan** — diagonal seams from underarm to neck.
- **Set-in sleeve** — conventional shoulder seam.
- **Fully-fashioned** — shaped panels with visible **decrease marks** at the armholes (dressier).
- **Ribbed trims** — cuffs, hem, neckband (1x1 or 2x2); can contrast in color.
- **Elbow patches** — suede/leather ovals.
- **Tipping** — thin contrasting stripes at trims.

**Render cues by fiber+gauge**
| Example | Look |
|---|---|
| Fine merino crewneck | Thin, smooth, lies close, faint sheen; no visible stitch from afar |
| Lambswool crewneck (9gg) | Soft matte with mild fuzz; visible stitches up close |
| Shetland crewneck | Heathered colors, hairy surface, slightly rumpled, rustic |
| Cashmere crewneck | Soft halo, rich deep color, slight drape |
| Thick yak shawl cardigan | **Chunky** knit, thick shawl collar, softly hairy halo, natural brown/oatmeal, weighty drape |
| Cotton cable crewneck | Crisp stitch definition, no halo, summer weight |
| Mohair cardigan | Fuzzy glowing halo, airy, semi-sheer |
| Aran sweater | Cream, dense deep cables, heavy |

### 4.5 Outerwear

| Garment | Defining features |
|---|---|
| **Chore coat** | Canvas/twill/moleskin/cord; boxy; **three patch pockets** (one chest, two lower); corozo or metal buttons; often French-blue or brown duck |
| **Trucker / denim jacket** | **Type I**: one chest pocket, pleats down front; **Type II**: two chest pockets, pleats; **Type III**: pointed front yokes, V-seams down front, two flap pockets — the classic. Waist band with adjustment tabs |
| **Sherpa trucker** | Trucker with sherpa lining and collar |
| **Bomber (MA-1)** | Nylon, ribbed collar/cuffs/hem, **orange lining**, utility sleeve pocket with zips |
| **Varsity / letterman** | Wool melton body, **leather sleeves**, striped rib trims, snap front, **chenille letter patches** |
| **Harrington** | Short, zip front, **check (tartan) lining**, umbrella back yoke, stand collar with throat tab |
| **Field jacket (M-65)** | Four bellows/flap pockets, stand collar with hidden hood, drawstring waist, cotton sateen, olive |
| **Waxed field jacket** | Waxed cotton, corduroy collar, bellows pockets, tartan lining |
| **Peacoat** | Navy wool melton, **double-breasted**, wide lapels, anchor buttons, slash hand pockets |
| **Topcoat / overcoat** | Knee-length; single or double-breasted; wool, camel, tweed |
| **Chesterfield** | Overcoat with **velvet collar** |
| **Trench coat** | Gabardine, double-breasted, storm flap, epaulettes, belt with D-rings, raglan sleeves |
| **Mac / raincoat** | Single-breasted, concealed placket, rubberised cotton |
| **Parka** | Long, hooded (often fur-trimmed), many pockets |
| **Puffer / down jacket** | Horizontal **baffles** (quilted channels), puffy, nylon shell |
| **Quilted jacket / liner** | Thin, **diamond or box quilting**, corduroy collar trim |
| **Fleece jacket** | Polar or sherpa fleece; full zip or quarter zip; often contrasting nylon pockets/panels |
| **Windbreaker / anorak** | Light nylon; anorak is pull-over with half zip and kangaroo pocket |
| **Leather jacket** | Café racer (minimal, band collar), **double-rider / biker** (asymmetric zip, wide lapels, belt), A-2 flight jacket (ribbed cuffs, shirt collar, flap pockets) |
| **Suede jacket** | Trucker or harrington cuts |
| **Shearling / B-3** | Sheepskin with woolly lining and wide collar |
| **Overshirt** | See 4.2 |
| **Gilet / vest** | Sleeveless puffer, fleece or quilted |
| **Barn jacket** | Canvas, **corduroy collar**, plaid flannel lining |

### 4.6 Tailoring

- **Suit**: jacket + trousers in the same cloth. Single-breasted (1/2/3 buttons) or double-breasted (6x2, 4x2...).
- **Sport coat**: odd jacket in textured cloth (tweed, hopsack, cord, linen).
- **Blazer**: odd jacket, solid (navy), often metal buttons, patch pockets.
- **Lapels**: notch, peak, shawl (tuxedo).
- **Pockets**: flap, jetted (no flap), patch; ticket pocket; breast welt pocket.
- **Vents**: single, double (side vents), ventless.
- **Shoulder**: structured (padded, roped), natural, unstructured (soft, "spalla camicia" shirt-shoulder).
- **Buttons**: horn, corozo, metal (blazer), covered (tuxedo).
- **Waistcoat**: 5–6 buttons, V-neck; can be double-breasted.
- **Tuxedo**: satin or grosgrain lapels, satin-striped trousers, bow tie.

### 4.7 Trousers & shorts

| Type | Features |
|---|---|
| **Chinos** | Cotton twill; slant side pockets, welt back pockets; flat-front or pleated |
| **Dress trousers** | Wool; creased; pleated or flat; side adjusters or belt loops; cuffs (turn-ups) optional |
| **Jeans** | **5-pocket**: two front scoop pockets, a coin (watch) pocket, two back patch pockets; rivets; leather or paper back patch; leg shapes **skinny, slim, straight, tapered, relaxed, bootcut, wide**; washes **raw, rinse, dark, mid, light, bleached, black, grey, white**; fade features — whiskers, honeycombs, stacks, train tracks |
| **Corduroys** | 5-pocket or chino cut; any wale |
| **Fatigues / army trousers** | Back sateen or ripstop; patch hip pockets; 4-pocket |
| **Cargo** | Bellows pockets on the thighs |
| **Carpenter / work pants** | Hammer loop, utility pockets, canvas/duck, **double knee** panels |
| **Drawstring / easy pants** | Elastic waist |
| **Sweatpants / joggers** | Fleece or terry; cuffed (jogger) or open hem |
| **Shorts** | Chino (5–9 in inseam), denim, cargo, swim, athletic, linen, seersucker, madras |

Rise: low, mid, high. Fit: skinny, slim, straight, relaxed, wide, tapered. Break: none, slight, full; turn-ups/cuffs.

### 4.8 Footwear (summary)

Sneakers (low/high-top, canvas/leather, minimalist white, retro runners), loafers (penny, tassel, horsebit), boots (chukka, desert, Chelsea, work/moc-toe, service, hiking, engineer), oxfords and derbies (cap-toe, plain-toe, wingtip/brogue), boat shoes, espadrilles, sandals, slippers. Materials: calf leather (smooth, polished), suede (matte, napped), pebble grain, roughout, shell cordovan (glossy, rolling creases), canvas, nubuck.

### 4.9 Accessories (summary)

Ties (silk, knit — square end, wool, grenadine, repp stripe, foulard, paisley), bow ties, pocket squares, belts (leather, woven, canvas D-ring), hats (baseball cap, 5-panel, beanie, watch cap, flat cap, bucket hat, fedora), scarves, socks, bags, watches, eyewear.

---

## 5. Construction details (catalog)

### 5.1 Collars (woven shirts)
| Collar | Shape | Formality |
|---|---|---|
| **Point** | Narrow angle, long points pointing down | Classic business |
| **Semi-spread** | Medium angle | Business |
| **Spread** | Wide angle between points | Business, ties with bigger knots |
| **Cutaway** | Points sweep almost horizontal | Fashion-forward formal |
| **Button-down** | Points buttoned to the shirt | Casual/business-casual, OCBD |
| **Hidden button-down** | Button concealed under collar points | Clean business |
| **Club** | Rounded points | Vintage |
| **Tab** | Small tab connects the points beneath the tie | Formal/vintage |
| **Pin** | Collar bar or pin through points | Formal/vintage |
| **Band / grandad / mandarin** | No collar leaf, just stand | Casual |
| **Camp / Cuban / revere** | One-piece, lies flat, no stand | Casual/resort |
| **Wing** | Short stand with folded tips | Black tie |
| **Western** | Long pointed spread, sometimes with tips | Western |
| **Johnny collar** | Knit spread with V placket | Polo |
| **Flat-knit collar** | Knitted rib collar | Polo |
| **Woven twill collar** | Stiffer contrast collar | Rugby |

### 5.2 Plackets
- **Front placket** — folded strip with visible stitching on both sides.
- **French front** — no placket, just a clean edge (dressy).
- **Hidden / fly front** — buttons concealed by a flap.
- **Half-placket (popover)** — buttons only partway down.
- **Henley placket** — short, collarless.
- **Polo placket** — 2–3 buttons, knit or woven.
- **Snap placket** — pearl snaps (western) or metal snaps (workwear).
- **Zip placket** — quarter/half/full.

### 5.3 Cuffs & sleeves
- Barrel cuff (1 or 2 buttons), French/double cuff, convertible, mitred, snap cuffs (3 snaps western), ribbed knit cuff, open hem, rolled-up, button tab (roll-tab sleeve holds rolled sleeves).
- Sleeve construction: set-in, raglan, drop shoulder (seam falls below shoulder), saddle shoulder, dolman/batwing.
- Short sleeve lengths: above elbow (standard), mid-bicep (shorter, modern), elbow length (boxy/oversized).

### 5.4 Pockets
| Pocket | Description |
|---|---|
| **Patch** | Sewn on top, visible edges |
| **Flap patch** | Patch with a buttoned flap |
| **Bellows** | Pleated sides that expand |
| **Welt / jetted** | Slit pocket with narrow lip |
| **Pencil slot** | Narrow divided section at side of chest pocket |
| **Smile / sawtooth** | Western curved slit pocket with arrow ends |
| **Kangaroo** | Wide front pouch on hoodies |
| **Slash / hand-warmer** | Diagonal or vertical slit |
| **Utility sleeve pocket** | Zip pocket on upper sleeve (bomber) |
| **Coin/watch pocket** | Small pocket inside right front jeans pocket |
| **Ticket pocket** | Small extra flap above right hip pocket on a jacket |
| **Double chest pockets** | Work, western, chambray, safari |
| **Chest pocket shapes** | Square, pointed (chevron) bottom, rounded, mitred corners |

### 5.5 Buttons & closures
| Closure | Visual |
|---|---|
| Plastic (shirt) | Small, 4-hole, white/clear/colored, glossy |
| **Mother-of-pearl (MOP)** | Iridescent shimmer, thin; premium dress shirts |
| **Trocas / shell** | Similar to MOP, mottled |
| **Horn** | Mottled brown/black/beige, organic; sport coats, cardigans |
| **Corozo** | Matte, slightly textured, nut-based; workwear and quality knits |
| **Metal shank** | Domed, often stamped; jeans, chore coats |
| **Pearl snaps** | Round snap with pearly/colored dome center, metal ring; western |
| **Rubber buttons** | Rugby shirts |
| **Coconut / wood** | Hawaiian, resort |
| **Leather knot / football** | Woven leather dome; cardigans, tweed |
| **Toggle** | Wood or horn peg with rope loop; duffle coat |
| **Cufflinks / studs** | French cuffs / tuxedo shirts |
| **Zip** | Metal (brass/nickel) or plastic coil, exposed or hidden |
| **Hook-and-eye / snap** | Workwear |

Button details: 2-hole vs 4-hole, **contrast thread**, cross-stitch vs parallel, **shanked** (stands off fabric). Count on standard dress shirt: 7–8 front buttons plus collar band.

### 5.6 Back details
- **Box pleat** (center back below yoke) — OCBD, ivy.
- **Side pleats** — two pleats near each shoulder blade; mobility.
- **Locker loop** — fabric loop at center back below yoke.
- **Split yoke** — back yoke made of two pieces meeting at center (bespoke).
- **Darts** — vertical tapering seams at back waist (slim fit).
- **Pointed western yoke**.
- **Umbrella yoke** — harrington.

### 5.7 Hems
- **Curved shirt-tail** — longer front and back, high sides; tucked.
- **Straight hem with side vents/slits** — untucked.
- **Tennis tail** — back longer than front (polo).
- **Side gussets** — triangular reinforcement at side seams (workwear, OCBD).
- **Ribbed waistband** — sweaters, sweatshirts, bombers.
- **Raw / cut edge** — fashion, distressed.

### 5.8 Stitching & trims
Single-needle (fine, dress shirts), double/triple-needle (workwear), chain stitch (jeans hem, embroidery), contrast topstitching (yellow/orange on denim), bar tacks, rivets, piping (contrast trim along seams/yokes), tipping (thin stripes at knit trims), selvedge ID.

---

## 6. Patterns

### 6.1 Pattern parameters
Every pattern needs: **type**, **colors (ground + pattern)**, **scale** (micro / small / medium / large / bold), **orientation** (vertical / horizontal / bias / all-over), and **placement** (all-over, chest band, yoke, panel, sleeve only). Woven vs printed vs knitted changes the look: woven patterns are identical on both sides and have soft edges; prints are sharper on the face and paler on the inside.

### 6.2 Stripes
| Stripe | Description |
|---|---|
| **Hairline** | Ultra-thin single-thread lines, reads almost solid |
| **Pencil** | Thin lines with wider spaces |
| **Pinstripe** | Thin dotted/fine lines (suiting) |
| **Chalk stripe** | Soft, slightly blurred lines (on flannel suiting) |
| **Bengal** | **Equal-width** bold stripes (~1/4 in) of color and white |
| **Candy stripe** | Narrow bright stripes (often red/white, pink/white), equal width |
| **University stripe** | Bold, even, slightly wider stripes (OCBD) |
| **Butcher stripe** | Wide, bold, equal stripes (aprons, work shirts) |
| **Awning** | Very wide bold stripes |
| **Multi / regimental / repp** | Multi-colored stripes; on ties, run diagonally |
| **Breton** | Horizontal navy-on-white, with gap at the shoulder |
| **Hoops** | Wide horizontal bands (rugby) |
| **Shadow stripe** | Tone-on-tone woven stripe visible only in light |
| **Seersucker stripe** | Puckered/flat alternating |
| **Bowling panels** | Vertical contrasting panels down the front |
| **Racing / tipping stripes** | Stripes on sleeves or trims only |

### 6.3 Checks & plaids
| Check | Description |
|---|---|
| **Gingham** | Even checks of one color + white; the overlap squares are darker → three tones |
| **Micro check / mini gingham** | Same at tiny scale |
| **Graph check** | Thin lines forming squares on white |
| **Windowpane** | Thin lines forming **large** squares on a solid ground |
| **Tattersall** | Two alternating colors of thin lines on light ground (often horse-country red/blue/green on cream) |
| **Shepherd's check** | Small black-and-white check with diagonal fill |
| **Houndstooth** | Broken checks with **jagged four-pointed shapes**; dogtooth = large; puppytooth = small |
| **Glen check / Prince of Wales** | Complex check combining small houndstooth and hairline blocks; often with colored overcheck |
| **Buffalo check** | **Large two-color blocks** (red/black classic) |
| **Tartan** | Multi-colored stripes crossing at right angles, specific "setts" — e.g. dark green/navy "Black Watch", red "Royal Stewart" style |
| **Madras plaid** | Bright, irregular, slightly bleeding, summer |
| **Flannel plaid** | Tartan-like but softened by brushing |
| **Overcheck** | Thin lines in a contrast color over a base pattern or solid |
| **Gun club check** | Two-color check on a light ground |
| **Argyle** | Diamonds with diagonal lines (knitwear, socks) |
| **Harlequin** | Diamond grid of solid color |

### 6.4 Prints & motifs
| Pattern | Description |
|---|---|
| **Polka dots / pin dots** | Regular dots; pin dot = tiny |
| **Paisley** | Teardrop/boteh motifs with intricate detail |
| **Foulard** | Small repeating geometric motifs (ties, shirts) |
| **Floral** | Flowers; **ditsy** (small scattered), **large-scale**, **Hawaiian/tropical** |
| **Aloha/Hawaiian** | Hibiscus, palm leaves, surfboards, sunsets; vivid |
| **Camouflage** | Woodland (green/brown/black blobs), desert (tan), tiger stripe, duck camo, digital/pixel |
| **Geometric** | Abstract shapes, retro 60s/70s |
| **Conversational / novelty** | Small repeated objects (anchors, ducks, cars) |
| **Ikat** | Blurred-edge designs from resist-dyed yarns |
| **Batik** | Wax resist, crackle lines |
| **Indigo / shibori** | Japanese resist dye in indigo |
| **Tie-dye** | Spirals, crumple, bullseye |
| **Animal** | Leopard, zebra, snake |
| **Abstract / brushstroke** | Painterly |
| **Nautical** | Anchors, flags, ropes |
| **Toile** | Monochrome pastoral scenes |
| **Stripes as print** | Printed stripes have crisper edges than woven |

### 6.5 Color texture (no explicit pattern)
- **Solid** — uniform.
- **Heathered / melange** — mixed fiber colors, flecked.
- **Marled** — two-color twisted yarns, speckled.
- **Slub** — irregular thick spots in yarn.
- **Two-tone / iridescent (shot)** — warp and weft different colors (chambray, Oxford, end-on-end; shot silk).
- **Garment-dyed** — slightly uneven, deeper color at seams and stitching.
- **Pigment-dyed** — chalky, faded, vintage; darker at seams.
- **Overdyed** — muted, dusty.
- **Sun-faded / washed** — lighter on shoulders and edges.
- **Acid wash / stone wash** — mottled bleaching (denim).
- **Ombré** — gradient.
- **Space-dyed** — randomly varying color along yarn.

### 6.6 Pattern-on-garment rules
- **Pattern matching**: quality shirts align stripes/checks across the **placket, pocket, yoke and sleeve plackets**; cheap ones don't.
- **Bias cutting**: yokes and pockets on plaid shirts are often cut on the diagonal for contrast.
- **Scale vs garment**: large buffalo check on a jacket; micro-check on a dress shirt.
- **Engineered prints** (placed specifically): border prints, chest bands, panel prints.
- **Knit motifs**: Fair Isle on yoke, Nordic bands across chest, intarsia logo on chest.

---

## 7. Graphics, embellishment & surface treatments

| Technique | Visual signature | Typical use |
|---|---|---|
| **Plastisol screenprint** | Opaque, **thick, slightly glossy ink layer sitting on top** of fabric; cracks with age | Graphic tees, sweatshirts |
| **Water-based screenprint** | Soft, **sinks into fabric**, matte, slightly translucent | Premium tees |
| **Discharge print** | Bleaches the dye out → **vintage, soft, faded** | Vintage-style tees on dark fabric |
| **Halftone** | Dot-pattern shading in print | Vintage band/photo graphics |
| **Puff print** | **Raised, 3D, spongy** ink | Logos, streetwear |
| **Flock print** | **Velvety raised** surface | College sweats, retro |
| **DTG (direct-to-garment)** | Photographic, full-color, soft, slightly faded | Photo tees |
| **Heat transfer / vinyl** | Smooth, shiny, sharp-edged film | Athletic numbers |
| **Sublimation** | All-over color in polyester, no texture | Sports jerseys, all-over prints |
| **Embroidery (satin stitch)** | Raised, glossy thread with directional sheen | Chest logos (polo, OCBD) |
| **Chain stitch embroidery** | Looping lines, rope-like | Western, bowling names, vintage |
| **Cross-stitch / folk embroidery** | Small X stitches, patterns | Ethnic/folk shirts |
| **Appliqué** | Fabric shapes sewn on with visible edges | Patches, varsity |
| **Chenille patch** | **Fuzzy terry-like** letters with felt border | Varsity jackets, cardigans |
| **Woven label / patch** | Small flat woven tag | Branding |
| **Leather patch** | Embossed leather at jeans waistband or chest | Workwear |
| **Felt letters / tackle twill** | Stitched twill letters with zigzag edges | Athletic jerseys, college sweats |
| **Rhinestones / studs** | Glittering points | Western, fashion |
| **Distressing** | Holes, frays, raw hems, faded patches | Denim, vintage tees |
| **Cracked print** | Fine crackle in ink | Vintage |

**Graphic placements**: left chest (small logo), center chest, full front, back (large), across the shoulders (yoke), sleeve (vertical text down the arm), hem (small), nape/neck (small text), pocket.

**Common graphic genres**: college/university arch lettering, sports team (generic), band/tour (back list of dates), souvenir/tourist, brand logo, typographic slogan, vintage illustration, surf/skate, national park/outdoors, abstract art.

---

## 8. Fit & silhouette

| Fit | Description |
|---|---|
| **Slim / tailored** | Tapered at waist, narrow sleeves, close to body |
| **Regular / classic** | Straight from chest to hem, room through body |
| **Relaxed** | Extra room, softer drape |
| **Boxy** | Wide and short body, dropped shoulders, straight hem |
| **Oversized** | Intentionally large, dropped shoulders, longer sleeves |
| **Cropped** | Short body (hits at or above waistband) |
| **Longline** | Extended length |
| **Muscle fit** | Tight through chest and arms |

**Wear states**: tucked / untucked / half-tucked (French tuck), sleeves rolled (to elbow or above), collar popped, buttons undone (top 1–2), layered (over a tee, under a sweater, collar peeking out of crewneck).

---

## 9. Validity: what combinations make sense

### 9.1 Common naming confusions to avoid
- **Flannel ≠ plaid.** Flannel is a brushed fabric; plaid/tartan is a pattern. A flannel can be solid; a plaid can be poplin.
- **Oxford ≠ button-down.** Oxford is a weave; button-down is a collar. OCBD = both together.
- **Chambray ≠ denim.** Chambray is plain weave (lighter, flatter); denim is twill (diagonal, heavier, lighter inside).
- **Corduroy describes ridges; wale describes ridge size.**
- **Merino is fine wool** — it rarely appears as a super-chunky hairy knit; yak and alpaca rarely appear as ultra-fine gauge.
- **Polo shirts are knit**; a woven short-sleeve shirt with a button collar is a short-sleeve button-up, not a polo.
- **Henley has no collar**; with a collar it becomes a polo.
- **Camp collar has no collar stand** and is not a spread collar.
- **Cardigan opens**; a pullover does not.
- **Breton stripes are horizontal**; vertical stripes on a tee is a different look.

### 9.2 Plausible fabric by garment
| Garment | Plausible | Implausible |
|---|---|---|
| Dress shirt | poplin, broadcloth, twill, pinpoint, royal oxford, end-on-end, fine herringbone, dobby | flannel (cotton), wide-wale cord, canvas, jersey |
| OCBD | Oxford cloth | anything else (then it's just a "button-down shirt") |
| Casual button-up | Oxford, chambray, linen, flannel, pinwale cord, poplin, seersucker, madras, twill, denim | heavy canvas, tweed |
| Camp-collar shirt | rayon, linen, cotton poplin, Tencel, silk, seersucker, terry | flannel (rare), cord (rare), wool |
| Flannel shirt | cotton flannel, wool flannel | — (by definition) |
| Overshirt | wool flannel, melton, wide cord, moleskin, canvas, plaid wool, quilted, denim | poplin, voile |
| T-shirt | jersey, slub jersey, interlock, rib, waffle | woven fabrics |
| Polo | piqué, jersey, fine knit, terry | woven poplin |
| Henley | jersey, slub, waffle, rib, sweater knit | woven |
| Sweater | any knit fiber | woven fabrics |
| Chinos | cotton twill | denim (→ jeans), wool flannel (→ trousers) |

### 9.3 Plausible weight / season pairings
- **Summer**: linen, seersucker, madras, voile, poplin, lightweight jersey, rayon, fine cotton knit, fresco, hopsack.
- **Spring/fall**: Oxford, chambray, twill, pinwale cord, light flannel, merino, cotton cable knit, chore coats, truckers.
- **Winter**: heavy flannel, wool flannel, wide-wale cord, moleskin, tweed, Shetland, yak, chunky cable, Aran, melton, shearling, puffers.

### 9.4 Plausible fiber / gauge pairings
| Fiber | Common gauges |
|---|---|
| Merino | 12–18gg (sometimes 7gg) |
| Cashmere | 7–16gg |
| Lambswool | 7–12gg |
| Shetland | 5–9gg |
| Cotton | 7–14gg |
| Yak | 3–9gg |
| Alpaca / mohair | 3–7gg, often loose and brushed |
| Chunky wool | 1.5–5gg |

### 9.5 Detail compatibilities
- Button-down collar → casual/business-casual; rarely with French cuffs.
- French cuffs → dress shirt with point/spread/cutaway collar.
- Pearl snaps → western, work; not dress shirts.
- Camp collar → straight hem, untucked, usually short sleeves.
- Ribbed sleeve bands → polos; hemmed sleeves → tees, woven short-sleeve shirts.
- Kangaroo pocket → pullover hoodie; zip hoodies get split pockets.
- Shawl collar → cardigans, heavy pullovers, tuxedo jackets.

---

## 10. Rendering recipe

### 10.1 Descriptor order
When turning a garment record into an image prompt or render spec, describe **from big to small**:

```
[fit] [color + color texture] [pattern (scale, colors)] [fiber] [fabric/weave + weight] [garment type]
with [collar], [placket/closure + button material], [pockets], [cuffs/sleeves], [back/hem details],
[graphic/embellishment + placement], [wear state], [condition]
```

### 10.2 Worked examples

1. **Linen camp shirt**
   "Relaxed-fit, short-sleeve, sage green **linen** camp-collar shirt; open flat one-piece collar without stand; straight hem; coconut buttons; visible slubs, soft crumpled wrinkles, slightly translucent in sunlight; untucked."

2. **Cotton flannel shirt**
   "Regular-fit **red and black buffalo check** heavyweight **brushed cotton flannel** shirt; button-down collar; two flap chest pockets cut on the bias; barrel cuffs; fuzzy matte surface with softly blurred check edges; sleeves rolled to forearm."

3. **Wool flannel overshirt**
   "Boxy **charcoal heathered wool flannel** overshirt; point collar; two flap patch chest pockets; horn buttons; dense matte surface with fine heathered flecks; worn open over a white tee."

4. **Thin corduroy vs wide wale**
   - "Slim **navy needlecord (21-wale)** shirt — ridges barely visible, velvety, drapes like a soft cotton."
   - "Relaxed **tobacco brown wide-wale (8-wale) corduroy** overshirt — bold ridges catching light, deep grooves, holds a structured shape."

5. **Merino vs yak sweater**
   - "Slim **fine-gauge (14gg) merino** crewneck in navy — smooth, thin, faint sheen, sits flat under a blazer, ribbed cuffs and hem."
   - "Relaxed **chunky (3gg) yak wool** shawl-collar cardigan in natural taupe brown — thick rolled collar, soft hairy halo, pronounced knit stitches, horn toggle buttons, heavy drape."

6. **Oxford button-down**
   "Classic-fit **light blue Oxford cloth button-down** (OCBD); soft collar roll; single chest pocket; box pleat and locker loop at back; long curved shirt-tail; pebbly two-tone texture; slightly rumpled."

7. **Heavyweight pocket tee**
   "Boxy **heavyweight (280 gsm) cotton jersey** pocket tee in ecru; thick 1-inch rib crewneck; dropped shoulders; left chest patch pocket; structured body that stands away from the torso."

8. **Graphic sweatshirt**
   "Relaxed **heather grey fleece-back** crewneck sweatshirt; V-insert below neckline; raglan sleeves; ribbed cuffs and waistband; **cracked, faded navy college-arch screenprint** across the chest."

9. **Western shirt**
   "Slim **mid-wash denim** western shirt; pointed front and back yokes with contrast piping; **pearl snap** closures; two flap pockets with smile-shaped openings; three-snap cuffs; fading along seams."

10. **Knit polo**
    "Regular-fit **12-gauge cotton knit polo** in cream; spread **Johnny collar** with no buttons; ribbed hem and cuffs; subtle vertical rib texture on the placket; slightly retro."

### 10.3 Checks before rendering
1. Is the fabric plausible for the garment? (section 9.2)
2. Is the weight plausible for the season and the fiber? (9.3, 9.4)
3. Are construction details compatible? (9.5)
4. Does the pattern have a scale and orientation?
5. Is the fabric's visual signature (drape, sheen, texture, halo, wrinkle) stated?
6. Are there distinctive signature details (collar roll, Breton gap, smile pockets) that make the garment recognizable?
