# Menswear Reference, Part 2: activewear, loungewear, footwear, color, bottoms, accessories, outfits

Continues `menswear-reference.md` (sections 0–10) with sections 11–17. The same rendering vocabulary applies (section 0.2: drape, sheen, texture scale, halo, opacity, wrinkle behaviour, edge thickness, color depth). The machine-readable side is in `menswear-taxonomy.json` under the new top-level blocks listed in section 17.

---

## 11. Activewear and loungewear

### 11.1 Performance fabrics

Activewear is mostly synthetic knits. They read differently from cotton: smoother, more uniform, a soft even sheen, close-fitting drape, and small sharp wrinkles instead of soft rumples.

| Fabric | Visual signature | Typical garments |
|---|---|---|
| **Performance jersey** (polyester or nylon, often with elastane) | Smooth, uniform, **faint even sheen**, thin; clings and shows the body; very small sharp creases | Training tees, running tops |
| **Cotton-poly blend jersey** | Between cotton and performance: matte-soft, slight heather | Gym tees, everyday athletic tees |
| **Mesh / birdseye / eyelet knit** | Visible pattern of small holes, often as **side or back panels** in a different texture from the body | Jersey panels, basketball jerseys, vents |
| **Interlock / double knit (poly)** | Thicker, smooth both sides, holds shape; the classic **track-suit fabric** with a soft sheen | Track jackets, track pants |
| **Tricot** | Smooth, shiny face, retro; slight crinkle | 70s–90s track tops |
| **Grid fleece** | Smooth face, **raised grid of squares on the back**, light and warm | Running mid-layers, half-zips |
| **Brushed-back performance fleece** | Smooth face, fuzzy back, thin | Running long-sleeves, tights |
| **Spacer / scuba knit** | Thick, springy, smooth, holds a crisp shape | Fashion-athletic hoodies, sweatshirts |
| **Compression knit** (high elastane) | Skin-tight, slight sheen, **no folds at all**; seams and panels visible | Compression tops, tights |
| **4-way-stretch woven** | Woven but stretchy; matte to soft sheen; smooth, technical; fewer wrinkles than cotton | Running shorts, training pants, "tech" chinos |
| **Nylon taffeta / ripstop (light)** | Thin, crinkly, crisp creases, slight sheen, rustles | Windbreakers, running jackets, shorts |
| **Softshell** | Stretchy woven face, light brushed back; matte; smooth panels | Trail and cycling jackets |
| **Waterproof membrane shell (2.5/3-layer)** | Smooth, slightly stiff, crisp angular folds; **taped seams** visible inside; matte or slight sheen | Rain shells |
| **Merino performance jersey** | Matte, fine, soft, drapes close; no plastic sheen | Base layers, hiking tees |
| **Swim / board-short fabric** (poly or nylon, often stretch) | Smooth, quick-dry, slight sheen; wet = darker and clinging | Swim trunks, boardshorts |

Rendering rules for performance fabrics:
- Colors are **cleaner and more saturated** than on cotton; neon and "volt" colors exist only on synthetics.
- Prints are crisp (sublimated) and can run all over without texture.
- Panels in a second fabric (mesh under the arms, contrast side panels) are common and often in a contrast color.
- Reflective details read as **silver-grey strips or dots** in daylight and bright white in flash photos.

### 11.2 Activewear details

| Detail | Description |
|---|---|
| **Flatlock seams** | Flat, raised, zigzag-stitched seams that look like a ladder of stitches; often in contrast thread |
| **Bonded / laser-cut hems** | No visible stitching; a clean cut edge, sometimes with a thin glued tape |
| **Raglan or saddle sleeves** | Diagonal seams for movement; the default on running tops |
| **Mesh vent panels** | Under arms, across the upper back, down the sides |
| **Thumbholes** | A slot at the sleeve end; the cuff extends over the back of the hand |
| **Zip pockets** | Small zipped pocket at the back waist (runners), on the hip or thigh, or a stash pocket in the waistband |
| **Reflective trims** | Strips, logos or dots in silver |
| **Drop tail / scooped hem** | Back hem longer than the front |
| **Side stripes** | One, two or three contrast stripes down the arm and leg (track suits) |
| **Piping** | Contrast cord along the raglan seams or yoke of track jackets |
| **Elastic waistband with drawcord** | Wide flat elastic, cord exiting through eyelets or grommets |
| **Built-in brief / liner** | Mesh or compression liner inside shorts ("2-in-1": visible longer liner under a short outer) |
| **Split / notched hem** | A slit or curved notch at the outer leg of running shorts |
| **Leg zips** | Zips at the ankle (tapered track pants) or full-length side zips (tear-away pants with snaps) |
| **Ribbed or elastic cuffs at the ankle** | Joggers |
| **Hood with a brim / helmet-compatible hood** | Technical shells |
| **Pit zips** | Zips under the arms for venting (shells) |
| **Storm flap / chin guard** | A fabric strip behind or over the front zip, a soft guard at the chin |
| **Two-way zip** | A zip that opens from the bottom too (longer jackets) |

### 11.3 Activewear garments

| Garment | Anatomy and variants | Valid fabrics |
|---|---|---|
| **Performance / training tee** | Crew or V; set-in or raglan; often mesh panels and flatlock seams; slim or regular | Performance jersey, cotton-poly, merino |
| **Performance long-sleeve / running top** | Crew or half-zip; thumbholes; reflective trims; drop tail | Performance jersey, brushed-back, grid fleece, merino |
| **Running singlet / tank** | Wide or narrow armholes; very light; often mesh | Performance jersey, mesh |
| **Compression top** | Skin-tight; short or long sleeve; panel seams; mock neck possible | Compression knit |
| **Base layer** | Crew or zip-neck; slim; long sleeves; flatlock seams | Merino, synthetic jersey, waffle |
| **Half-zip / quarter-zip athletic top** | Stand collar with short zip, chin guard; slim; thumbholes | Grid fleece, brushed-back, performance jersey |
| **Track jacket** | **Full zip, stand collar**, ribbed or elastic cuffs and hem; zip hand pockets; side stripes or color-blocked panels; piping | Interlock / double knit, tricot, nylon |
| **Windbreaker / running jacket** | Light; hood optional; packable; reflective details; elastic cuffs | Nylon taffeta, light ripstop |
| **Softshell / trail jacket** | Fitted; stand collar; chest zip pocket | Softshell |
| **Rain shell / hard shell** | Hood with brim and adjusters; storm flap; pit zips; taped seams; drop tail | Waterproof membrane shell |
| **Fleece pullover / zip** | Full, half or quarter zip; contrast nylon chest pocket and panels; stand collar | Polar fleece, sherpa, grid fleece |
| **Sports jersey** | Soccer: V or crew, sometimes a collar, sublimated pattern, crest on the chest, number on the back. Basketball: sleeveless, deep armholes, mesh, numbers front and back. Hockey: very loose, laced V-neck, striped arms and hem. Baseball: button front with piping, script across the chest. American football: shoulder-pad cut, numbers on shoulders | Mesh, performance jersey, double knit |
| **Cycling jersey** | Slim; full or half zip; **three rear pockets** at the lower back; elastic hem gripper | Performance jersey |
| **Running shorts** | 3–7 in inseam; **split or notched hem**; built-in brief; back zip pocket; elastic waistband with drawcord | 4-way-stretch woven, light nylon |
| **2-in-1 shorts** | Short outer with a longer compression liner visible beneath | Woven outer, compression liner |
| **Training shorts** | 7–9 in inseam; side pockets, zip pocket; straight hem | 4-way-stretch woven, cotton-poly |
| **Basketball shorts** | Long (9–11 in), loose, mesh, wide waistband, side stripes | Mesh, double knit |
| **Compression tights / shorts** | Skin-tight to ankle or mid-thigh; panel seams | Compression knit |
| **Track pants** | Straight or tapered; side stripes; ankle zips; elastic waist with drawcord; zip hand pockets. Tear-away version has snaps down the outer seam | Interlock, tricot, nylon |
| **Training pants / tech pants** | Slim tapered; zip pockets; ankle cuffs or a clean hem | 4-way-stretch woven |
| **Joggers** | Tapered, **ribbed cuffs at the ankle**, elastic waist with drawcord, slant pockets | French terry, fleece-back, 4-way-stretch woven |
| **Sweatpants (open hem)** | Straight leg, no cuff; elastic waist | French terry, fleece-back |
| **Running / athletic socks** | Crew, quarter or no-show; cushioned sole; arch band | Synthetic blend, merino |

Footwear for sport is in section 12 (running shoes, trainers, court shoes, cleats, hiking boots, slides).

### 11.4 Loungewear and sleepwear

| Garment | Anatomy and variants | Valid fabrics |
|---|---|---|
| **Pajama set (woven)** | **Notched-lapel collar** (camp-like, no stand), button front, **contrast piping** along collar, placket, cuffs and pocket; one chest patch pocket; matching drawstring or elastic-waist trousers; long or short (short sleeves + shorts) | Cotton poplin, flannel, seersucker, silk, linen, modal |
| **Pajama set (knit)** | Crew or henley top with matching pants or shorts | Jersey, waffle, modal |
| **Sleep / lounge shorts** | Boxer-like, elastic waist, short inseam; may have a button fly | Poplin, flannel, jersey |
| **Lounge pants** | Straight, relaxed, elastic waist with drawcord; no pockets or side pockets | Flannel (often plaid), jersey, waffle, cashmere |
| **Lounge knits** | Relaxed crew sweater and matching knit jogger | Cashmere, merino, cotton |
| **Lounge sweatsuit** | Matching sweatshirt or hoodie and sweatpants, same color | French terry, fleece-back |
| **Robe** | Wrap front with a **belt** through loops; **shawl collar** (or kimono-style straight collar band); patch pockets at the hip; knee to ankle length; turned-back cuffs | Terry towelling (looped pile), waffle weave, cotton flannel, wool, silk, velour, fleece |
| **Kimono-style robe** | Straight collar band running down the front, wide sleeves, sash belt, no buttons | Cotton, linen, silk |
| **Smoking jacket** | Short robe-like jacket with a **quilted or satin shawl collar**, frog or toggle closures, cuffs in contrast | Velvet, silk |
| **Undershirt / sleep tee** | Plain crew or V; thin | Jersey |
| **Slippers and house shoes** | See section 12.6 | |

Rendering cues for loungewear: relaxed fit, soft collapsed folds, **matching top and bottom** (same color or the same pattern), piping in a contrast color on woven pajamas, terry robes look thick with a loopy matte surface and rounded edges.

### 11.5 Validity for activewear and loungewear

- Compression and performance garments are never linen, wool flannel, tweed, corduroy or raw denim.
- Track jackets use a **stand collar with zip**, never a shirt collar or lapel.
- Pajama tops use a notched-lapel or camp-style collar with piping; a pajama top in Oxford cloth with a button-down collar is a shirt.
- Robes close with a belt (sash), never a zip or a full button front.
- Joggers have cuffed ankles; open-hem sweatpants do not.
- Neon colors, sublimated all-over prints and reflective trims belong to synthetics.
- Athletic formality: activewear is **athletic**, loungewear is **lounge** (below casual): neither belongs in smart-casual outfits except deliberate exceptions (a clean knit jogger with a sweater, or a track jacket over a tee in streetwear).

---

## 12. Footwear

### 12.1 Shoe anatomy

```
toe ── vamp ── (tongue, lacing / eyelets) ── quarter ── heel counter ── collar (top line)
 └── toe cap / toe box                                                    └── pull tab
sole stack: insole ─ midsole ─ outsole; welt (if any) joins upper to sole; heel block
```

| Part | Options and visual cues |
|---|---|
| **Toe shape** | **Round** (casual, boots, sneakers); **almond** (slightly tapered, dress); **chisel / square-ish** (sharp flat front, fashion dress); **pointed** (rare, fashion); **moc toe** (U-shaped stitched apron on top) |
| **Toe treatment** | Plain; **cap toe** (straight seam across the toe); **wingtip** (W-shaped cap whose wings run down the sides); **medallion** (punched pattern on the toe); **apron / moc stitch**; **split toe** (seam down the centre); rubber **toe cap** (sneakers) |
| **Lacing system** | **Closed lacing (Oxford / balmoral)**: eyelet tabs stitched under the vamp, the V closes neatly; **open lacing (Derby / blucher)**: eyelet tabs sit on top of the vamp and flap open; **speed hooks** (metal hooks at the top of boots); **D-rings**; **ghillie** (loops, no tongue); slip-on; **elastic side gussets** (Chelsea); **monk strap(s)** with buckles; **hook-and-loop** straps; **toggle / speed lace** (runners) |
| **Eyelet count** | Dress shoes 4–6; sneakers 6–8; ankle boots 5–7 + hooks; work boots 6–10 |
| **Laces** | Flat or round waxed (dress), flat cotton (sneakers), round rope (boots, boat shoes), rawhide (boat shoes, moccasins); laces may contrast |
| **Sole type** | **Leather sole** (thin, flat, tan or dark edge, dress); **rubber city sole** (thin rubber, dress); **Dainite-style studded rubber**; **commando / lug sole** (deep chunky tread, boots); **crepe sole** (honey-colored, wavy, slightly translucent: desert boots); **wedge sole** (flat white or off-white, no heel: moc-toe work boots); **cupsole** (stitched rubber cup around the shoe: court sneakers); **vulcanized sole** (thin rubber band around the shoe with foxing tape: canvas sneakers); **EVA / foam midsole** (thick, sculpted, often white: runners); **siped deck sole** (wavy cuts: boat shoes); **cleats / studs** |
| **Construction** (visible clues) | **Goodyear / storm welt**: a visible strip of leather around the sole with stitching on top; thick sole edge. **Blake**: close-trimmed, sleek sole edge, no welt. **Stitchdown**: upper flares out over the sole and is stitched on top. **Cemented**: no visible stitching. **Vulcanized**: rubber foxing band |
| **Height** | No-show/low (below ankle), mid (at ankle), high (above ankle), **boot heights**: ankle (4–5 in shaft), 6 in, 8 in+, knee (riding, wellingtons) |
| **Heel** | Flat (sneakers), low stacked leather heel (dress, ~1 in), block heel (boots, 1–1.5 in), Cuban/raised heel (western boots, angled) |
| **Upper material** | **Smooth calf** (polished sheen, creases across the vamp); **pebble grain** (dotted texture, matte); **suede** (matte, napped, color shifts with direction); **roughout** (suede side out, rugged); **nubuck** (fine short nap); **shell cordovan** (deep gloss, rolling creases rather than sharp ones); **patent** (mirror gloss, formal); **oiled / pull-up leather** (lightens where it flexes); **canvas**; **knit mesh** (runners); **synthetic leather**; **waxed canvas** |
| **Colorways** (leather) | Black, dark brown, mid brown, tan, cognac, oxblood / burgundy, walnut, snuff suede, sand suede, navy suede, grey suede |
| **Colorways** (sneakers) | White / off-white, black, grey, navy, cream with gum sole, multi-color panels; **gum sole** (translucent tan rubber) |

### 12.2 Dress shoes (formality high to lower)

| Style | Defining features | App style |
|---|---|---|
| **Patent Oxford / opera pump** | Mirror-gloss black, closed lacing or slipper with a grosgrain bow; black tie | `oxford` / `slip_on` |
| **Plain-toe Oxford** | Closed lacing, no cap; sleek | `oxford` |
| **Cap-toe Oxford** | Closed lacing, straight toe cap; the business classic (black or dark brown) | `oxford` |
| **Wholecut** | Cut from one piece, no seams except the heel; closed lacing | `oxford` |
| **Semi-brogue / quarter-brogue** | Cap toe with punched edges (broguing) and a medallion | `oxford` |
| **Full brogue / wingtip** | Wingtip cap with broguing along all edges; Oxford or Derby | `oxford` / `derby` |
| **Derby / blucher** | Open lacing; plain toe or cap toe; slightly more casual and sturdier | `derby` |
| **Monk strap** | One (single) or two (double) buckled straps instead of laces | `derby` |
| **Loafers** | Slip-on, no laces: **penny** (strap across the vamp with a slot), **tassel** (tassels on laces at the front), **horsebit** (metal snaffle across the vamp), **Belgian / venetian** (plain, low), **driving moc** (rubber nubs on the sole and heel) | `loafer` |
| **Dress boots** | **Chelsea** (elastic side gussets, pull tabs); **jodhpur** (strap wrapping the ankle); **balmoral boot** (Oxford-laced dress boot) | `chelsea_boot` / `boot` |

### 12.3 Casual and work boots

| Style | Defining features | App style |
|---|---|---|
| **Chukka** | Ankle height, 2–3 eyelets, open lacing; suede or leather; leather or rubber sole | `boot` |
| **Desert boot** | Chukka with a **crepe sole**, unlined suede (sand is the classic) | `boot` |
| **Chelsea (casual)** | Suede or roughout, lug or crepe sole | `chelsea_boot` |
| **Service / roughout boot** | 6 in, plain toe or cap toe, Goodyear welt, leather or rubber sole | `boot` |
| **Moc-toe work boot** | 6 in, moc toe, **white wedge sole**, oiled leather (orange-tan classic) | `boot` |
| **Engineer boot** | Pull-on, no laces, **buckled straps** at the instep and top of shaft | `boot` |
| **Logger boot** | Tall (8 in+), raised heel, lug sole, many eyelets | `boot` |
| **Hiking boot** | Mid height, padded collar, **speed hooks**, lug sole, mixed suede and nylon or mesh | `boot` |
| **Duck boot** | Rubber lower (often brown), leather or nylon upper, chain-tread sole | `boot` |
| **Wellingtons / rain boots** | Knee-high rubber, pull-on | `boot` |
| **Western boot** | Pointed or square toe, **Cuban heel**, decorative stitching on the shaft, pull holes | `boot` |
| **Combat / jump boot** | 8–10 in, lug sole, speed hooks | `boot` |
| **Snow boot** | Insulated, padded, often fleece or shearling cuff, chunky rubber shell | `boot` |

### 12.4 Sneakers and athletic shoes

| Style | Defining features | App style |
|---|---|---|
| **Minimal leather court sneaker** | Clean white or black leather, cupsole, few seams, flat laces | `low_sneaker` |
| **Canvas low-top** | Canvas upper, **vulcanized** rubber sole with foxing stripe, toe cap; white, black or colors | `low_sneaker` |
| **Canvas high-top** | Same, above the ankle, round ankle patch on the inner side | `high_top` |
| **Court / tennis shoe (retro)** | Leather, perforated toe, side stripes or panels, cupsole | `low_sneaker` |
| **Basketball shoe** | Mid or high, padded collar, chunky cupsole, panels, sometimes ankle strap | `high_top` |
| **Skate shoe** | Suede or canvas, padded tongue and collar, flat vulcanized or cupsole | `low_sneaker` |
| **Retro runner** | Suede and nylon panels, **EVA wedge midsole**, side logo stripes, gum or rubber outsole | `runner` |
| **Modern running shoe** | **Knit mesh upper**, thick sculpted foam midsole, rocker shape, heel pull tab | `runner` |
| **Trail runner** | Running shoe with aggressive lug outsole, toe bumper, toggle laces | `runner` |
| **Trainer / cross-trainer** | Flat stable sole, mesh and synthetic overlays | `runner` |
| **Slip-on canvas** | Elastic gussets, no laces, vulcanized sole (often checkerboard prints) | `slip_on` |
| **Cleats** | Molded studs, low or mid collar | `low_sneaker` |
| **Platform / chunky "dad" sneaker** | Very thick layered midsole, many overlays | `runner` |

### 12.5 Summer and casual shoes

| Style | Defining features | App style |
|---|---|---|
| **Boat shoe / deck shoe** | Moccasin construction with stitched apron, **rawhide laces threaded around the collar**, siped white sole | `loafer` |
| **Camp moc** | Boat-shoe-like with 2 eyelets and a lug sole | `loafer` |
| **Penny loafer (casual)** | Suede or unlined, rubber sole | `loafer` |
| **Espadrille** | Canvas upper, **braided jute rope sole** | `slip_on` |
| **Sandal** | Fisherman (closed woven straps), two-strap cork footbed (buckled straps), sport sandal (hook-and-loop straps, thick rubber sole), huarache (woven leather) | `sandals` category |
| **Slide** | Single wide strap, molded sole (pool slides, cork-bed slides) | `sandals` category |
| **Flip-flop** | Thong between toes | `sandals` category |

### 12.6 Slippers and house shoes

- **Moccasin slipper**: soft suede, apron toe, shearling lining, soft or rubber sole.
- **Slipper with shearling collar**: closed back, fleece lining showing at the collar.
- **Open-back / scuff slipper**: slip-in mule.
- **Velvet slipper (Albert slipper)**: velvet upper, quilted lining, often embroidered motif on the vamp; formal-lounge.
- **Felt / wool clog**: boiled wool upper, cork or rubber sole.

### 12.7 Rendering and validity for footwear

- Polished calf shows a **bright specular highlight** on the toe and creases across the vamp; suede shows no highlight and slight color shift; patent shows a mirror highlight.
- Gum soles are **translucent caramel**; crepe soles are lighter honey with a wavy surface; wedge soles are flat white blocks.
- White sneakers yellow at the sole edge and crease across the toe with wear.
- Closed vs open lacing is the single most visible dress-shoe difference: draw the eyelet tabs **under** the vamp for Oxford and **on top** for Derby.
- Validity: crepe soles go with suede chukkas, desert boots and some Chelseas, not with patent or business Oxfords. Leather soles are for dress shoes. Speed hooks appear on boots, not on Oxfords. Brogueing increases casualness: full brogues are less formal than plain or cap toes. Patent leather is for black tie only.
- Formality: patent > plain/cap-toe Oxford > wholecut > brogues and Derbies > monk straps > loafers > dress boots (Chelsea, chukka) > casual boots > leather sneakers > canvas sneakers > runners > sandals and slides.

---

## 13. Color

The app's coarse color list (`backend/closet/vocab.py`: black, white, grey, navy, blue, light_blue, green, olive, tan, brown, cream, red, burgundy, pink, orange, yellow, purple, multi) is enough for outfit logic. Menswear names and draws colors more finely; the named shades below each map to one app color. Hex values are a typical swatch on matte cotton under daylight, not a standard.

### 13.1 Named shades

| Shade | Hex | App color | Where it shows up |
|---|---|---|---|
| Black | #1a1a1a | black | Everything; real black cloth is never pure #000 |
| Jet / off-black (faded black) | #2b2b2b | black | Washed black tees and jeans |
| Charcoal | #36393d | grey | Suits, trousers, knits, overcoats |
| Slate | #5a6470 | grey | Knits, outerwear |
| Mid grey | #8a8d91 | grey | Flannel trousers, sweatshirts |
| Heather grey | #a3a6a8 | grey | Sweatshirts, tees (flecked) |
| Light grey / dove | #c9cacc | grey | Knits, suits |
| Stone | #c9bfae | tan | Chinos, outerwear |
| Khaki | #c3b091 | tan | Chinos, field jackets |
| Sand | #d6c4a2 | tan | Suede, linen, chinos |
| Camel | #b5875a | tan | Overcoats, knits |
| Tobacco | #7a5230 | brown | Suede, cord, knits |
| Chocolate / dark brown | #4a3121 | brown | Leather, cord, knits |
| Mid brown | #7b5536 | brown | Leather shoes, belts |
| Cognac / tan leather | #9a5a2c | brown | Leather shoes, belts, bags |
| Rust | #a4492a | orange | Cord, knits, flannels |
| Oxblood | #4e1a1d | burgundy | Leather shoes, knits |
| Burgundy | #6d1f2a | burgundy | Knits, ties, cord |
| Brick | #9c3d2e | red | Knits, cord |
| Red | #b22a2a | red | Flannels, knits, accents |
| Coral | #e5735c | orange | Summer shirts, shorts |
| Mustard | #c9a227 | yellow | Knits, cord |
| Pale yellow / butter | #f0e3a1 | yellow | Shirts, knits |
| Olive | #5f6b3a | olive | Chinos, field jackets, knits |
| Army / OD green | #4b5320 | olive | Military outerwear, fatigues |
| Sage | #a3ad8f | green | Linen, knits |
| Forest / bottle green | #22422c | green | Knits, cord, flannel |
| Hunter green | #355e3b | green | Outerwear, knits |
| Teal | #2a6f74 | green | Knits, accents |
| Navy | #1f2a44 | navy | Blazers, knits, chinos, suits |
| Midnight | #191d2e | navy | Formalwear, outerwear (reads near-black) |
| Indigo (raw) | #23304a | navy | Raw and dark denim |
| Royal blue | #2a4ea0 | blue | Knits, sportswear |
| Cobalt | #1e4fb8 | blue | Accents |
| Mid-wash denim | #5b7aa3 | blue | Jeans |
| Chambray blue | #8ca5c7 | light_blue | Shirts |
| Oxford blue (light) | #a9c4e0 | light_blue | OCBDs, dress shirts |
| Sky / powder blue | #bcd4ea | light_blue | Shirts, knits |
| Light-wash denim | #9bb2cf | light_blue | Jeans |
| Pink (shirting) | #f1c8cf | pink | Dress shirts, OCBDs |
| Dusty rose | #c99a9a | pink | Knits, linen |
| Lavender | #c8bfe0 | purple | Dress shirts |
| Plum / aubergine | #4b2a45 | purple | Knits, ties |
| White (optic) | #f7f7f5 | white | Dress shirts, sneakers |
| Off-white | #f1eee6 | cream | Knits, tees |
| Ecru | #e8e0cc | cream | Undyed cotton, denim, knits |
| Cream | #efe6d2 | cream | Knits, Aran, trousers |
| Oatmeal | #d9ccb4 | cream | Heathered knits, linen |
| Natural / flax | #cbbd9f | tan | Undyed linen |
| Bone | #e3dccb | cream | Chinos, sneakers |

### 13.2 How fabric changes a color

| Fabric or finish | What happens to the color |
|---|---|
| **Indigo denim** | Starts near-navy (raw); fades toward mid and light blue with whiskers, honeycombs and paler seams; inside is white-ish |
| **Black cotton** | Fades to charcoal-brown or charcoal-grey; pigment-dyed black looks grey from the start |
| **Linen** | Colors look **chalky and slightly lighter**; whites look creamy; deep colors look washed |
| **Brushed fabrics** (flannel, moleskin, brushed cotton) | Colors look **deeper and softer**, no highlights; patterns blur |
| **Corduroy and velvet** | Color shifts between the light crest and dark groove; looks richer and darker in folds |
| **Suede** | Color shifts with nap direction; brushed areas lighter |
| **Wool (worsted)** | Clean, true color, slight sheen |
| **Heathered / marled yarns** | Reads as a lighter, softer version of the base color, flecked |
| **Garment-dyed / pigment-dyed** | Muted, uneven; **darker at seams and stitching**, lighter at edges |
| **Mercerised cotton, silk, satin** | Richer, more saturated, bright highlights |
| **Synthetics (performance)** | Cleaner, brighter, more saturated; neons possible |
| **Leather** | Smooth leather has highlights; pull-up and oiled leather lighten where flexed; patina darkens tan leather with age |
| **Sun fade** | Shoulders, collar and upper back lighter than the rest |

### 13.3 Color families for outfit logic

- **Neutrals**: black, white, grey family, navy, tan/stone/khaki, cream/ecru/oatmeal, brown family, olive. Pair with anything.
- **Earth tones**: olive, rust, tobacco, mustard, brown, forest green, burgundy, oatmeal. Pair with each other and with navy, cream and grey.
- **Cool colors**: blues, light blues, teal, lavender, grey.
- **Warm colors**: red, orange, coral, rust, mustard, yellow, pink.
- **Brights**: royal blue, cobalt, red, coral, yellow, pink, purple: one per outfit is the usual limit outside sportswear.

---

## 14. Bottoms in depth

### 14.1 Anatomy

```
waistband (belt loops / side adjusters / elastic) ─ fly (zip or buttons) ─ front (flat or pleated)
 ─ front pockets ─ seat ─ back pockets ─ inseam / outseam ─ knee ─ leg opening ─ hem (plain, cuffed, ribbed)
```

### 14.2 Waistband and closure

| Option | Description | Typical on |
|---|---|---|
| **Belt loops** | 5–7 loops; the default | Jeans, chinos, cords, dress trousers |
| **Side adjusters** | Buckle tabs or button tabs at the side seams; no belt loops | Tailored trousers |
| **Extended waistband tab** | A tab that extends past the fly with a hook-and-bar or button | Dress trousers |
| **Gurkha waistband** | Wide folded-over band with double buckle straps at the front | Tailored, high-waisted trousers |
| **Elastic waist with drawcord** | Gathered elastic, cord at the front | Joggers, sweats, track, lounge, shorts |
| **Half-elastic** | Flat front, elastic at the back or sides | Easy pants, shorts |
| **Drawstring only** | Fabric tie | Linen trousers, beach pants |
| **Brace (suspender) buttons** | Buttons inside or outside the waistband | Formal and high-rise trousers |
| **Zip fly / button fly** | Zip is the default; **button fly** on many jeans and military trousers | |

### 14.3 Front, rise and leg

| Feature | Values and visual cues |
|---|---|
| **Front** | **Flat front** (clean); **single pleat** (one fold per side); **double pleat** (two folds); **reverse pleat** (fold opens toward the pocket) vs **forward pleat** (opens toward the fly) |
| **Rise** | **Low** (sits at the hip), **mid** (just below the navel), **high** (at or above the navel); higher rise = longer distance waistband to crotch |
| **Leg shape** | **Skinny** (tight throughout), **slim** (close but not tight), **tapered** (roomy thigh narrowing to the ankle), **straight** (same width knee to hem), **relaxed / loose** (roomy throughout), **wide** (wide from hip to hem), **bootcut** (slight flare below the knee), **flare** (strong flare), **barrel / balloon** (curved outward at the knee, narrowing at the hem) |
| **Leg opening** (typical, men's size 32) | Skinny 12–13 in circumference, slim 14–15, straight 15.5–17, wide 18–22+ |
| **Length / break** | **No break** (hem just touches the shoe), **slight / quarter break** (one soft dent), **full break** (a clear fold over the shoe), **cropped / ankle** (above the ankle bone), **stacked** (bunched folds above the shoe, common on jeans) |
| **Hem finish** | **Plain**; **turn-up / cuff** (folded band 1.25–2 in, tailored trousers); **rolled cuff** (casual folded jeans or chinos; selvedge line visible on selvedge denim); **ribbed cuff** (joggers); **raw / frayed**; **chain-stitched hem** (jeans: slight rope twist when worn) |
| **Crease** | Pressed centre crease (dress trousers, some chinos) vs none |

### 14.4 Pockets and back details

| Feature | Description |
|---|---|
| **Slant (on-seam angled) pockets** | Chinos, dress trousers |
| **Vertical on-seam pockets** | Dress trousers |
| **Scoop / frog-mouth pockets** | Curved openings: jeans (scoop), some western or vintage trousers (frog-mouth) |
| **Coin / watch pocket** | Small pocket inside the right front pocket (jeans) |
| **Back welt pockets** | Single or double welt (piping), with or without a button: chinos, dress trousers |
| **Back patch pockets** | Jeans (often with decorative stitching, an "arcuate"), work pants |
| **Back flap pockets** | Military, work, cargo |
| **Cargo pockets** | Bellows pockets on the outer thigh, with flaps |
| **Utility / hammer loop and rule pocket** | Carpenter pants |
| **Double knee** | Second layer of fabric over the knees (work pants) |
| **Gusseted crotch** | Diamond-shaped insert (outdoor, work, climbing pants) |
| **Back yoke** | V-shaped seam above the back pockets on jeans |
| **Rivets** | Metal studs at pocket corners (jeans) |
| **Leather / paper back patch** | Label on the back waistband (jeans) |
| **Darts** | Small tapering seams under the waistband at the back (tailored) |
| **Belt-loop styles** | Narrow, wide, double, or a centre-back V loop |

### 14.5 Jeans: washes and wear

| Wash | Look |
|---|---|
| **Raw / dry** | Uniform deep indigo, slightly stiff, faint sheen, sharp creases, no fades |
| **Rinse / one-wash** | Deep, even indigo, softened, no fades |
| **Dark wash** | Dark indigo with very slight fading |
| **Mid wash** | Classic blue with visible fading at thighs and seat, whiskers |
| **Light wash** | Pale blue, heavy fading, high contrast |
| **Bleached / super light** | Near white-blue |
| **Stone wash** | Even, slightly mottled lightening |
| **Acid wash** | **Marbled**, high-contrast white blotches |
| **Black / washed black** | Black that fades to charcoal; grey seams |
| **Grey** | Grey denim (black warp washed down, or grey warp) |
| **Ecru / natural** | Undyed off-white |
| **White** | Clean optic or soft white |
| **Overdyed** | Tinted (brown, green) over indigo |

**Fade features** (where wear lightens indigo): **whiskers** (horizontal streaks radiating from the crotch at the front hips), **honeycombs** (hexagonal creases behind the knees), **stacks** (rings above the hem), **train tracks** (light lines along the outseam on selvedge denim), **roping** (twisted fade on the hem chain stitch), **pocket fades** (wallet or phone outline), **knee fades**.

**Distressing**: knee rips, frayed hems, abrasions on thighs, repaired / patched areas (sashiko-style stitching).

### 14.6 Shorts by style and inseam

| Style | Typical inseam | Features |
|---|---|---|
| **Running shorts** | 3–5 in | Split hem, liner |
| **Short chino / "above-knee" shorts** | 5–7 in | Flat front, slant pockets, welt back pockets |
| **Classic chino shorts** | 7–9 in | As above |
| **Denim shorts / cut-offs** | 7–10 in | 5-pocket, rolled or frayed hem |
| **Cargo shorts** | 9–11 in | Thigh bellows pockets |
| **Basketball shorts** | 9–11 in | Mesh, elastic waist, stripes |
| **Boardshorts** | 7–20 in | Fly with laces or hook-and-loop, no elastic waist, side pocket, prints |
| **Swim trunks** | 3–7 in | Elastic waist with drawcord, mesh liner |
| **Linen / pull-on shorts** | 6–8 in | Drawstring |
| **Pleated / tailored shorts** | 6–8 in | Pleats, side adjusters |
| **Sweat shorts** | 6–9 in | French terry, elastic waist |

### 14.7 Validity for bottoms

- **Side adjusters** and **belt loops** rarely appear together; side adjusters mean no belt.
- **Pleats** go with mid or high rise and straight, tapered or wide legs; pleats on low-rise skinny trousers look wrong.
- **Turn-ups (cuffs)** go on tailored and casual trousers with straight or tapered legs; not on very slim trousers or joggers.
- **Scoop pockets + coin pocket + back patch pockets + rivets** = jeans (5-pocket), whatever the fabric (cord and canvas 5-pockets exist).
- **Ribbed ankle cuffs** = joggers; **elastic waists** do not take belts.
- Washes and fades apply only to denim (and some canvas/duck); chinos fade gently and evenly.
- Formality: worsted dress trousers > flannel trousers > chinos (pressed) > cords and moleskins > dark jeans > chinos (washed) > lighter jeans > cargo/work pants > joggers and track pants > shorts (athletic shorts lowest).

---

## 15. Accessories

| Group | Types and defining features | Materials and visual cues |
|---|---|---|
| **Hats** | **Baseball cap** (structured 6-panel with a front buckram; or unstructured "dad cap"; curved or flat brim; snapback, strapback or fitted); **5-panel / camp cap** (flat front panel, short brim); **trucker cap** (foam front, mesh back); **beanie / watch cap** (ribbed knit, cuffed; fisherman beanie sits high above the ears); **flat cap** (rounded, short brim snapped to the crown); **newsboy** (fuller 8-panel with a button on top); **bucket hat** (downward brim all round); **fedora** (pinched crown, medium brim, ribbon band); **trilby** (narrower brim snapped down); **panama** (woven straw fedora, summer); **boater** (flat-topped stiff straw); **wide-brim / cowboy hat**; **beret**; **trapper / earflap hat** | Wool felt, straw, cotton twill, canvas, corduroy, knit wool, acrylic, waxed cotton, tweed |
| **Belts** | **Dress belt** (narrow 1–1.25 in, smooth leather, small polished buckle; matches shoes); **casual leather belt** (1.25–1.5 in, thicker, larger buckle; brass or nickel); **braided / woven leather**; **canvas web belt** (with slide or D-ring buckle); **woven elastic belt**; **western belt** (tooled leather, large buckle); **reversible belt** | Leather colors as shoes (section 12.1); buckles brass, nickel, gunmetal, matte black |
| **Ties** | **Silk tie** (woven or printed; patterns: solid, repp stripes running diagonally, foulard, paisley, dots, club motif); **knit tie** (square bottom, textured); **wool / cashmere tie** (matte, textured, winter); **grenadine** (open silk weave, textured); **bow tie** (self-tie or pre-tied; butterfly or batwing shape); width 2.5–3.5 in | Silk sheen, knit texture, wool matte |
| **Pocket square** | Folds: flat / TV fold, one point, puff, crown | Silk, linen (white linen flat fold is the classic), cotton |
| **Scarves** | **Long knit scarf**, **woven wool scarf** (plain, tartan, herringbone), **cashmere scarf** (soft halo), **silk scarf** (light, glossy prints), **bandana** (square cotton, paisley print), **snood / neck gaiter** | Wool, cashmere, cotton, silk, fleece |
| **Gloves** | Leather dress gloves (lined), knit gloves, mittens, fingerless, work gloves, touch-screen | Leather, suede, wool, fleece |
| **Bags** | **Tote** (canvas or leather, two handles); **backpack** (daypack, rucksack with flap and straps, roll-top); **messenger** (flap, cross-body strap); **briefcase** (structured, top handle); **duffel / weekender** (barrel shape, two handles and strap); **crossbody / sling bag** (small, worn across the chest); **belt bag / waist bag**; **dopp kit** | Canvas, waxed canvas, nylon, leather, ballistic nylon |
| **Eyewear** | Frame shapes: **wayfarer** (trapezoid, thick acetate), **aviator** (teardrop metal, double bridge), **round**, **clubmaster / browline** (thick top, metal bottom), **rectangular**, **sport wrap**; lens colors (dark grey, green, brown, mirrored, gradient) | Acetate (tortoiseshell, black, clear), metal (gold, silver, gunmetal) |
| **Watches** | **Dress watch** (thin, small, leather strap, simple dial); **dive watch** (rotating bezel, lume, steel bracelet or rubber strap); **field watch** (legible numerals, canvas or leather strap); **chronograph** (sub-dials); **digital / sport watch**; straps: leather, steel bracelet, NATO nylon (striped), rubber | Steel, gold, titanium, resin |
| **Socks** (visible between trouser hem and shoe) | **Dress socks** (thin, over-the-calf or mid-calf, solid, pin-dot, clocks, birdseye); **casual crew socks** (thicker, ribbed, stripes, argyle, colors); **athletic crew** (white or black, ribbed, cushioned); **no-show** (invisible with loafers, sneakers); **boot socks** (thick wool, ragg marled, often cuffed over the boot) | Merino, cotton, wool, synthetic blends |
| **Jewelry** | Signet ring, wedding band, chain necklace, beaded bracelet, cuff bracelet, cufflinks, tie bar, lapel pin | Gold, silver, steel, beads, leather |
| **Suspenders / braces** | Button-on (formal) or clip-on; X or Y back | Elastic, leather ends |
| **Umbrellas** | Long stick umbrella, compact folding | Canopy colors, wood or hook handles |

Rendering and validity for accessories:
- **Belt and shoe leather match** in color and finish for smart and business outfits (black with black, brown with brown); canvas or braided belts with casual shoes.
- Dress belts and leather-soled shoes go with dress trousers; web belts with chinos, shorts, jeans.
- A **tie** goes with a collared shirt (point, spread, cutaway, button-down) under a jacket or sweater; never with a camp collar, band collar, polo or tee.
- **Knit ties and wool ties** are smart-casual; silk solids, repp stripes and foulards span business; black silk bow tie = black tie.
- Pocket squares belong with a tailored jacket; they echo, not match, the tie.
- Beanies and bucket hats are casual; fedoras and trilbies are smart; caps are casual and athletic.
- Socks: no-show with loafers and sneakers in warm weather, dress socks in a color between trousers and shoes for business, white athletic socks with sneakers and athletic outfits only.

---

## 16. Layering and outfit rules

This section is the reasoning for the outfit builder (`backend/closet/outfits.py`), which works in places: `base`, `mid`, `outer`, `bottom`, `shoes`, `accessories`.

### 16.1 What goes in each place

| Place | What belongs | Notes |
|---|---|---|
| **base** | Tee, polo, shirt (any), henley, tank, long-sleeve tee, turtleneck (fine knit), base layer | The layer against the body |
| **mid** | Sweater, cardigan, sweatshirt, hoodie, sweater vest, overshirt, shirt over a tee, fleece, light jacket under a coat | Optional; adds warmth |
| **outer** | Jacket, coat, blazer/sport coat, overshirt (as the last layer), shell, puffer | Optional; protects |
| **bottom** | Trousers, jeans, chinos, cords, shorts, joggers | Exactly one |
| **shoes** | Exactly one pair | Formality of shoes anchors the outfit |
| **accessories** | Belt, hat, scarf, bag, watch, eyewear, gloves | Any number; weather drives hats, scarves, gloves |

### 16.2 Layering order and what shows

- Layer from **thin to thick and from fitted to roomy**: each layer must fit over the one beneath (a slim blazer over a chunky shawl cardigan fails).
- **Collars**: a shirt collar sits **outside** a crewneck or V-neck sweater; it goes **inside** a turtleneck (no shirt under a turtleneck as a rule). A polo collar inside a crewneck is unusual; a button-down collar under a crewneck is the classic preppy layer.
- **Hems**: a sweater worn over a tucked shirt usually covers the waistband; an untucked shirt hem showing 1–2 in below a sweater is a casual look; a shirt tail far below a jacket hem looks wrong.
- **Sleeves**: shirt cuffs show ~0.5 in past a jacket sleeve in tailoring; with sweaters, sleeves are often pushed up together.
- **Hoods**: a hoodie under a jacket puts the hood **outside** the jacket collar; a hoodie under a blazer is streetwear, not smart-casual.
- **Overshirts** act as mid (over a tee, under a coat) or outer (over a tee or knit).
- **Tucking**: dress shirts and long-tail shirts are tucked; camp-collar, straight-hem casual shirts, polos with a tennis tail, tees and knitwear are usually untucked. **Tucking means a belt** if the trousers have loops.
- **Turtlenecks** work under blazers, overcoats and suede jackets as a smart replacement for a shirt and tie.
- **Vests** (sweater vest) go over a shirt; never over a hoodie.
- **Max useful layers**: base + mid + outer; a fourth (shirt over tee under sweater under coat) is fine in cold weather if each layer is thin enough.

### 16.3 Temperature to layers (rough guide, °C)

| High of the day | Typical outfit |
|---|---|
| ≥ 27 | Base only: tee, polo, linen or camp shirt; shorts or light trousers; sneakers, loafers, sandals |
| 21–26 | Base; light trousers or shorts; optional light overshirt or unlined jacket in the evening |
| 16–20 | Base + light mid (shirt over tee, light knit) or light outer (trucker, chore coat, harrington, bomber) |
| 10–15 | Base + mid (sweater, sweatshirt) + light outer, or base + medium outer (field jacket, waxed jacket, blazer) |
| 4–9 | Base + mid + warm outer (wool overcoat, peacoat, quilted jacket); heavier fabrics (flannel, cord, wool) |
| ≤ 3 | Base (often a warm base: flannel, merino) + warm mid + insulated outer (puffer, parka, heavy overcoat); hat, scarf, gloves; boots |
| Rain at any temperature | Outer must be water-resistant (shell, waxed jacket, trench, mac); avoid suede shoes; boots or rubber-soled shoes |

### 16.4 Formality matching

Ordered formality levels (app values: `athletic`, `casual`, `smart_casual`, `business`, `formal`; this guide adds `lounge` below `athletic` for home wear):

| Level | Typical pieces |
|---|---|
| **formal** | Tuxedo or dark suit, white dress shirt, silk tie or bow tie, black Oxfords or patent |
| **business** | Suit or blazer and trousers, dress shirt, tie optional, Oxfords, Derbies, loafers, dress boots, leather belt |
| **smart_casual** | Blazer or sport coat, chinos, wool trousers or dark jeans, OCBD, polo, fine knit, turtleneck, loafers, chukkas, Chelsea boots, clean leather sneakers |
| **casual** | Tees, flannels, camp shirts, sweatshirts, jeans, chinos, cords, shorts, sneakers, casual boots |
| **athletic** | Performance tees, track and running gear, joggers, shorts, runners, trainers |
| **lounge** | Pajamas, robes, lounge sets, slippers |

Rules:
- All pieces should be **within one level** of the outfit's target; **shoes and outer layer** set the impression most strongly.
- Mixing **up** in one piece is fine and intentional (a blazer over a tee and jeans = smart casual). Mixing **down** in shoes only works in casual and smart-casual (clean sneakers with a suit is a fashion choice, not business).
- Athletic pieces only mix with casual pieces in streetwear (hoodie under a topcoat, track jacket with jeans), never with business pieces.
- Fabric texture tracks formality: smooth and fine (worsted, poplin, calf) is dressier; rough and textured (tweed, flannel, cord, suede, canvas) is more casual.

### 16.5 Color pairing

- **Neutrals anchor**: build most outfits on two neutrals (navy + grey, olive + cream, brown + blue) and add at most **one accent** color.
- **Tonal outfits** (shades of one color, e.g. cream + oatmeal + tan) work best with **texture contrast** (knit vs twill vs suede).
- **Contrast** comes from value (light vs dark): light top + dark bottom is the default; dark top + light bottom is fine in summer.
- **Classic pairings**: navy + grey; navy + tan/khaki; navy + white; olive + navy; olive + cream; brown + blue; brown + olive; grey + burgundy; charcoal + light blue; black + white + grey; cream + brown; rust + navy; forest green + tan.
- **Avoid by default**: two different near-identical shades in adjacent pieces (navy jacket with not-quite-matching navy trousers reads as a mismatched suit; black with navy is acceptable today but should be distinct in value); more than one bright color; brown shoes with a black belt.
- **Denim counts as a neutral** blue; double denim works when the two washes differ clearly (light shirt + dark jeans).
- **Black** pairs with grey, white, and bright accents; it fights warm browns and tans in leather (keep black shoes with black or grey trousers, brown shoes with everything except black).
- **Shoes**: brown leather goes with blue, grey, olive, tan, cream; black leather with grey, black, navy (business); white sneakers with almost anything casual.

### 16.6 Pattern mixing

- **One pattern** per outfit is always safe; everything else solid.
- **Two patterns** work if they differ in **scale** (a micro-check shirt with a bold windowpane jacket) or in **type** (stripe + check), and share a color.
- **Three patterns** (tie, shirt, jacket) need three different scales and a common color; avoid outside tailoring.
- Never mix two patterns of the **same type and similar scale** next to each other (two medium stripes, two similar plaids).
- Textured solids (tweed, cable knit, cord) count as half a pattern: they add interest without clashing.
- Loud prints (aloha, camo, large florals, graphic tees) are the outfit's focus: keep everything else solid and neutral.

### 16.7 Proportion and fit

- **Slim top + slim or straight bottom**, or **roomy top + straight or wide bottom**; very roomy top on skinny bottoms gives a "lollipop" silhouette, a deliberate fashion choice.
- **Boxy cropped tops** pair with higher-rise, straighter trousers.
- **Long outer layers** (overcoats, parkas) go over anything; **short jackets** (truckers, bombers) should end near the waistband with tops not hanging far below.
- **Chunky shoes** (boots, chunky sneakers) balance wider legs; **sleek shoes** (loafers, low Oxfords) suit slim and tapered legs and short breaks.
- Trouser **break** should fit the shoe: no break with loafers and sneakers, slight break with dress shoes, stacked jeans with boots.

---

## 17. Notes for the code

The taxonomy JSON gains these **new top-level blocks**. None of them changes an existing block, so `backend/closet/tagger/taxonomy.py` (`AXES`, weights) and its tests stay as they are:

| JSON block | What it holds |
|---|---|
| `performance_fabrics` | Section 11.1 fabrics with visual signatures (not yet in `axes.knit_structure` / `axes.woven_structure`) |
| `activewear_details` | Section 11.2 details |
| `footwear` | Section 12: anatomy axes (toe shape, toe treatment, lacing, sole, construction, height, heel, upper material, colorways) and formality order |
| `colors` | Section 13: named shades with hex, the app color each maps to, fabric color behaviour, color families |
| `bottoms` | Section 14: waistband, front, rise, leg, break, hem finish, pockets, washes, fades, distressing, shorts inseams |
| `accessories` | Section 15: types per group |
| `outfit` | Section 16: places, layering rules, temperature bands, formality levels, color pairings, pattern-mixing rules, proportion rules |

New `garments` entries use the categories `activewear`, `loungewear`, `footwear` and `accessory`, and the bottoms entries gain detail fields. None of these categories is one that `bench/tests/test_taxonomy.py` draws (`knit_top`, `woven_shirt`, `sweatshirt`, `knitwear`), so no drawing test changes. Each footwear garment has `app_style`, a value of `SHOE_STYLES` in `backend/closet/tagger/taxonomy.py` (or the app category `sandals`), so the drawing can pick its template.

Promoting any of these values into `axes` (for example adding `performance_jersey` to `knit_structure`) is a deliberate step: update `AXES` and `COVERAGE` in `backend/closet/tagger/taxonomy.py` in the same change, as `AGENTS.md` describes.
