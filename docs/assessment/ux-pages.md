# Closet: design review of the pages outside Settings, Add, Item detail and transitions

Read-only review, 19 Nov 2026. The repo was not modified. To run the app, I copied `backend/` and `frontend/` into the scratchpad, installed the pinned requirements in a scratch venv and built the frontend there.

## How it was run, and what could not be observed

- **Backend:** `python -m tests.e2e_backend` (the e2e test server) with `CLOSET_E2E_FAKES=1 CLOSET_E2E_SEED=demo CLOSET_E2E_STYLIST=1`. The owner's own closet started as a copy of the demo closet (49 items, 16 worn outfits, 2 wishes, a Lisbon trip). Claude, the shop search, the weather service and the model download were all stand-ins. Nothing was sent outside.
- **Empty and first-run states:** a second backend with a fresh data folder.
- **Weather:** faked in the browser, as the e2e tests do (6–14 °C, Brooklyn). I also captured the "weather could not be fetched" state.
- **Not observable:**
  - Claude's real wording on Today and in the chat. The screens show stand-in text such as "Chosen by the stand-in…".
  - The real wait while Claude chooses outfits. The stand-in takes 1.5 s; the README says real choosing takes "under a minute".
  - Real shop finds.
  - Real latency over Tailscale. Everything here ran on localhost.
  - iOS Safari specifics: the notch, the home indicator, the PWA standalone mode. Chromium was used at 390×844 with isMobile.
- **Screenshots:** `shots-pages/`, named `phone-*` and `desk-*`. `*-top.png` is the first screen only, `e-*` is the empty closet, and `phone-00-setup`, `phone-01-ready` and `phone-02-login` are the first run. Crops are in `pages-audit/crops/`.
- **Scripts:** `pages-audit/shoot-full.cjs` and `pages-audit/reqs.cjs`.
- **Shared scratchpad:** another agent overwrote `scratchpad/shoot.cjs` and stopped my first backend on port 8801. The numbers below come from my runs on ports 8801 and 8931 (the same seeded closet).

## 1. Route inventory

Source: `frontend/src/router.tsx` (`parseRoute`), `Shell.tsx`, `App.tsx`, `nav.ts`.

| Route | Screen (file) | Purpose | Reached from (phone) |
|---|---|---|---|
| (before the shell) Setup | `screens/Setup.tsx` | Choose a passphrase | First launch |
| Ready ("You're set") | `screens/Setup.tsx` | Tailscale hint, then "Start with my own closet" or "Open the demo closet" | After setup |
| Login | `screens/Login.tsx` | Passphrase | Any 401 |
| Loading / Unreachable / Closed | `screens/Static.tsx` | Connection states | Automatic |
| `/today` | `screens/Today.tsx` (1199 lines) | Weather, occasion and mood, Claude's outfits (carousel), "I'm wearing this", rate yesterday, chat with Claude | Tab "Today". Landing page once the closet can dress you (`landing.ts`) |
| `/today/item/:id` | ItemDetail inside Today | A piece of the outfit | Tap a piece |
| `/today/worn` | `screens/Worn.tsx` | History of worn outfits, ratings, record by hand, wear again | "Worn" pill in the Today header |
| `/` | `screens/Closet.tsx` | The grid, search, Filter sheet, Photos/Drawings, review and laundry notes | Tab "Closet" |
| `/item/:id`, `/archived/item/:id` | ItemDetail | (out of scope) | Tile |
| `/archived` | Closet (archived) | Archived items | Filter sheet: "Archived" |
| `/insights` | `screens/Insights.tsx` | Usage statistics: unworn, worn most, spread, make-up, cost per wear | Small "Insights" text link in the closet header |
| `/review` | `screens/Review.tsx` | Confirm fields Claude was unsure of | "5 pieces need a quick check · Review" note on the closet; dot on the Closet tab |
| `/missing` | `screens/Missing.tsx` (698 lines) | Gaps by rule (Suggestions) and Wishlist (segmented), the "How you live" questionnaire, "Also worth knowing" | Tab "Missing" |
| `/missing/item/:id` | ItemDetail inside Missing | | |
| `/missing/check`, `/missing/check/wish/:id` | `screens/WouldWork.tsx` | "Would this work?": check a piece before buying it, from a photo or described by hand | "Would this work?" pill on Missing |
| (inside Wishlist) | `screens/Shop.tsx` | Shop finds for a wish, price range, price checks | Wishlist tab |
| `/trips` | `screens/Trips.tsx` (883 lines) | Trip list | "Trips" pill in the Today header, or Settings |
| `/trips/new` | Trips: PlanTrip | Plan form | "Plan a trip" |
| `/trips/:id` | Trips: SavedTrip | Weather strip, warnings, packing checklist, basics, "Why these counts", day by day | Trip card |
| `/add`, `/add/several/:id` | (out of scope) | | Tab "Add" |
| `/settings` | (out of scope) | | Tab "Settings" |

**Sheets, dialogs and overlays:**
- Closet Filter sheet: In use/Archived, category, group, kind, laundry.
- Today: the piece "⋯" menu (Not this piece / Start from this piece), the DayPanel (change place, type temperatures, a note on the day), the yesterday-rating card, the stylist waiting card with "Show Closet's own picks meanwhile".
- Worn: the outfit "⋯" menu (wear again, laundry, remove), the "Record an outfit" form.
- Missing: the LifeQuestions dialog (full-screen on a phone), the hide form ("Not for me" with a reason), Add a wish by hand.
- Item sheets (out of scope).
- Global: toasts, the update banner, the restore notice, the offline banner, the demo ribbon, the model banner.

**Navigation:**
- **Phone tab bar:** Today · Closet · (Add) · Missing · Settings.
- **Desktop sidebar:** Add clothes · Today · Closet (with Review under it while there is anything to review) · Trips · What's missing · Settings.
- **Hidden second-level places:**
  - Worn and Trips: pills in the Today header. On a phone, Trips is otherwise only in Settings.
  - Insights: a text link in the closet header.
  - Review: a note on the closet.
  - Archived: inside the Filter sheet.
  - Would this work?: a pill on Missing.
  - Wishlist: a segment on Missing.
- **Lit tab vs page:** Trips lights the "Today" tab and Review lights "Closet" (`nav.ts`), so the lit tab and the page you are on disagree.

**Core loop:** open the app, see today's outfit, tap "I'm wearing this", and the next day rate yesterday's outfit.
- With a closet that can dress you, launch lands on Today, so it is **0 taps to the outfit and 1 tap to record it**.
- On a phone, "I'm wearing this" is just inside the first screen (y≈720 of 844) even with the yesterday card above it.
- That is good, but it holds only because `useLanding` redirects once per tab. A cold open with the item list not yet loaded briefly shows the closet first.
- Changing the occasion or mood, or "Ask Claude again", costs a Claude round trip: "under a minute" per the README.

## 2. Measurements (seeded closet; Today with the stand-in stylist)

| Page | Phone height (px) | Words (whole page) | Words in first phone screen | Controls | Requests on load (API + SVG) |
|---|---|---|---|---|---|
| Today | 1789 (2163 after a chat turn) | 361 | 151 | 73 | 32 (phone) / 31 (desk) |
| Closet | 7028 | 296 | 60 | 65 | 40 (phone) / 61 (desk) |
| Closet + Filter sheet | n/a | 369 | 109 | 115 | n/a |
| Archived (empty) | 844 | 35 | 35 | 8 | 12 |
| Worn | 4654 | 391 | 104 | 119 | 52 / 52 |
| What's missing | 5897 | 733 (1141 on desk) | 159 | 82 (105 desk) | 36 / 38 |
| Would this work? | 1639 | 170 | 104 | 67 | 14 |
| Trips list | 844 | 53 | 53 | 8 | 13 |
| Trip (Lisbon) | 4464 | 481 | 139 | 54 | 26 |
| Plan a trip | 844 | 98 | 98 | 26 | 12 |
| Insights | 3940 | 483 | 132 | 79 | 30 |
| Review | 1317 | 73 | 54 | 29 | 13 |
| Empty Insights | 1091 | 159 | n/a | 10 | 12 |
| Setup / Ready / Login | 844 | 36 / 54 / 33 | n/a | 3 / 2 / 2 | n/a |

- **Overhead on every page.** Every page load makes the same 8–10 API calls before its own: `session`, `restore-notice`, `updates`, `vocab`, `model`, `review` ×2 and `items` ×2 or ×3.
  - `items` and `review` are fetched twice, or three times on Today and Worn. Sources: `store.tsx:79`; `useReviewCount` in `Review.tsx:30` and again on the screen.
  - Then one request per item drawing (`/api/items/:id/illustration.svg`): 22–42 on the closet, 33 on Worn.
  - The drawings are versioned and `immutable`, so repeat visits are cheap. A cold load over Tailscale (HTTP/1.1, about 6 connections, a 50–150 ms round trip) has to queue 40–60 requests, which fits the owner's "laggy" impression.
- **Horizontal overflow:** none at 390 px. The chip rows on Today and Plan a trip are deliberate side-scrollers that clip their last chip; see the findings below.
- **Tap targets:** the 36 px pills (Worn, Trips, the Today piece menu items) rely on the invisible 44 px `::after` hit area described in DECISIONS (Design system, Accessibility). My script could not confirm that hit area, so I make no claim that these targets fail.

## 3. Findings per page

Severity: **H** = hurts the main use or looks broken; **M** = clutter or confusion; **L** = polish.

### Today (`screens/Today.tsx`, `Today.css`, `today.ts`)
1. **H. On a phone the outfit card is far taller than its content.** Each carousel slide takes the height of the tallest slide, or the card stretches beside "Why this works". Phone: about 300–450 px of blank card under "Why this works" (`phone-today.png`, `phone-today-asworn.png`). Desktop: the card is about 680 px tall with roughly 350 px of white under "See another idea" (`desk-today.png`). It looks unfinished and pushes the chat far down. Look at the `Carousel`/`OutfitCard` layout, line 1012 on.
2. **H. As worn shows an empty grey box while the figure is drawn.** There is no skeleton, spinner or words. After a chat turn changed the outfits, the figure frame stayed empty for more than 4 s (`phone-today-chat.png`). The figure is drawn one layer per request (DECISIONS, "dressed a layer at a time"), so on a slow link this stays blank longest exactly where it matters.
3. **H. Contradictory weather.** When the forecast fails, the day line still reads "14–20°C · no rain · a mild day" as if it were real. Directly below it a yellow box says the weather could not be fetched (`phone-today-noweather.png`). Say it once, in the day line ("No forecast: dressing you for a mild day · Change").
4. **M. Too many decisions are stacked above the outfit.**
   - The title row has 2 pills (Worn, Trips). Then come the day line with Change, then 5 occasion chips (a side-scroll that clips "Business"; "Formal" is off screen) plus 3 mood chips (on a phone the moods are further along the same scroller, invisible). Then the coral "How was yesterday's outfit?" card with 3 buttons and ×. Then "Best for today · 1 of 3" with the Pieces/As worn switch.
   - That is about 17 controls before the first garment. Occasion and mood are habits the README itself says are remembered; they could collapse to one line ("Casual · As usual ▾").
5. **M. Three ways to page through the outfits.**
   - On a phone: swipe, the dots with arrow buttons (the disabled left arrow is a dashed circle that looks broken), and the "See another idea" link inside the card.
   - On a desktop: a 4th, the thumbnail strip.
   - Keep the swipe with the dots, or "See another idea"; not all of them.
6. **M. Who chose the outfit is said three times.** "Chosen by Claude" sits in the green box. "Claude on today: …" sits under the carousel. "Ask Claude again" is a separate link, and the chat box below that. The narration under the carousel ("It is a made-up day…" with the stand-in; in real use, Claude's reading of the day) floats between the card and the chat with no visual home.
7. **M. A teaching line in every card.** "Tap a piece to see it. Its ••• button leaves it out or builds every outfit around it." is repeated in every card's "Why this works" box, and "Drawn as worn… Choose Pieces to see one…" in As worn. Show it once (first use), not as permanent content.
8. **M. The chat is a bare form at the bottom of a long page.** The phone page grows from 1789 to 2163 px with one exchange. The "YOU / CLAUDE" turns use the terracotta mono label style meant for small section heads. Typing in it, you can no longer see the outfit it is about.
9. **L. A ⋯ button on every piece tile** (6 per outfit) adds visual noise. It sits on the top-right corner and overlaps the garment drawing (the jeans' waistband on `phone-today-top.png`).
10. **L.** On a desktop the first piece labels ("OUTER LAYER", "MID LAYER"…) use the mono label style. On a phone they are dropped, so the two layouts differ.

### Worn (`screens/Worn.tsx`)
1. **M. Every card lists each piece twice:** a row of thumbnails, then the same names as a comma list. 391 words, 119 controls, 4654 px.
2. **M. Rating is duplicated.** Rating yesterday appears both on Today (coral card) and here ("Not rated yet" + Loved it / Fine / Not again).
3. **M. Recording a wear has four entry points:** Today's "I'm wearing this", Worn's "Record an outfit", the item page's "Wore it today" (referenced in the Insights empty text), and Worn's ⋯ "wear again". The header button "Record an outfit" competes with the page's purpose (reviewing).
4. **L.** The per-card ⋯ is drawn as a tiny 3-dot glyph (`phone-worn-top.png`), visually much smaller than the ⋯ on Today's tiles: two different "more" buttons.
5. **L.** Reached only from a pill on Today. Its back link says "‹ Today", while the tab bar also lights Today.

### Closet (`screens/Closet.tsx`)
1. **M. Three stacked notes before any clothes.**
   - "5 pieces need a quick check · Review", "4 pieces are in the laundry · Show", and "Background removal: not set up yet… Download · Settings · ×".
   - With the header and toolbar, the first garment starts at about y=390 of 844, and only about 1.5 rows of tiles show (`phone-closet-top.png`).
   - Each note has its own action wording (Review / Show / Download + Settings + ×).
   - Could be one line ("5 to check · 4 in the laundry") or chips in the toolbar.
2. **M. The Photos/Drawings switch is two unlabeled icons on a phone** (a picture and a pencil). The pencil reads as "edit". On a desktop it has labels.
3. **M. The Filter sheet is a long chip wall:** In use/Archived, then 17 category chips, 8 group chips, kinds and laundry. 115 controls with it open, and the sheet's full-page capture shows it is the entire screen. Category and group overlap ("Shirts" appears as a category and "Tees & polos" as a group).
4. **L. Insights hangs off the closet header** as a quiet text button (a ghost button with no icon). It is easy to miss and is not a closet function.
5. **L. Empty closet:** the toolbar shows Filter with no clothes to filter. The model banner sits above the empty state, so a new owner's very first screen is a technical warning about background removal (`phone-e-closet.png`).
6. **L. Desktop:** the sidebar's background stops at the first viewport height (900 px). Below that the page background shows under the menu on every long page (`desk-today.png`, `desk-missing.png`).

### What's missing (`screens/Missing.tsx`, `Missing.css`, backend wording in `backend/closet/gaps.py`)
1. **H. The longest page in the app:** 5897 px and 733 words on a phone; 1141 words on a desktop.
   - It holds 9 suggestion cards, each with a title, a "Helps some" pill, a paragraph, "Why, day by day", a LOOK FOR box with colour dots, FROM YOUR CLOSET thumbnails, "I'll look for this" and "Not for me".
   - Then "Also worth knowing".
   - Nine "helpful" cards is not a priority list. Show the top 2–3 and a "more" link.
2. **H. Developer-facing and robotic wording, generated in `gaps.py`:**
   - "on cold, cool or mild rainy days **the engine** can only say 'take an umbrella'" (`gaps.py:646`, `:650`).
   - "between **2026-10-30 and 2026-11-18**" (ISO dates).
   - "it is the only boots you have" (grammar).
   - "Not worn since **the log began (2026-10-30)**".
   - "Every outfit for cool business and formal days rests on your black overcoat… If it is in the wash or being mended, there is nothing to change to" (repeated almost verbatim in 4 cards).
   - It also suggests buying "Another pair of trousers like your tartan lounge pants": loungewear counted as trousers.
3. **H. Duplicated content.**
   - "Also worth knowing → Worn far more than the rest" repeats the boots and tartan-trousers suggestion cards word for word.
   - "Not worn yet" duplicates Insights' first card.
   - The same statistics live on two pages.
4. **M. Four layers of controls before the first suggestion:**
   - the "Would this work?" pill;
   - the Suggestions/Wishlist switch;
   - a "Based on your closet. · Your answers ›" bar;
   - a "Tell it how you live · 1 minute" promo with two buttons.
   - The promo shows even when the closet is empty (`phone-e-missing.png`). Asking about your life before you own anything is out of order.
5. **M. The desktop wishlist is a fixed-height inner scroller** in the right column. It cuts off the second wish mid-card with no scroll cue, while the page itself scrolls 4250 px (`desk-missing.png`).
6. **L.** The "Helps a lot" (filled) vs "Helps some" (tint) pill is the only ranking cue; all 8 lower cards are "Helps some".

### Would this work? (`screens/WouldWork.tsx`)
1. **M. The "describe by hand" form is a 67-control wall:** 18 kinds, 18 colours, 5 formalities, 3 seasons, 4 weights, 7 patterns, a rain switch and a name. The primary action "Would it work?" stays disabled (dashed) until a kind and a colour are chosen, and the only hint is a line below the button.
   - Of all of this, the photo route is the natural one. The by-hand form could start with kind and colour only, with the rest under "More details".
2. **L.** The kind list here (T-shirt, Shirt, Polo…) differs from the closet's category chips and the item's "What is it?" kinds. That is three vocabularies for the same thing.

### Trips (`screens/Trips.tsx`, `Trips.css`)
1. **M. Hard to find on a phone:** not in the tab bar; only a pill on Today or a link in Settings. On a phone, opening it lights the Today tab.
2. **M. Plan a trip:**
   - The occasion chips overflow off the right edge (Smart casual clipped; Business and Formal invisible) (`phone-trip-plan.png`).
   - A privacy paragraph about Open-Meteo sits between the place field and the dates.
   - "Some days are different" is a green heading with nothing under it until something is tapped; it reads like a stray title.
   - The laundry switch's three labels wrap onto two lines each.
   - The primary button is dashed (disabled) with no hint until a place is searched, and the place needs a separate "Search" button.
3. **M. The saved trip runs 4464 px:** a weather strip that side-scrolls with a clipped 5th day, a warnings box listing the same "proportions fight a little" sentence twice, the packing list, the basics, "Why these counts" and "Day by day" with its own Pieces/As worn switch. The header "4 of 15 packed" vs "What to pack · 11 pieces" is two counts that don't obviously agree (the 4 basics make up the difference).
4. **L.** The list subtitle "the fewest pieces from your closet that dress every day of a trip" is good. The "3 days dressed with warnings" in orange on the trip card is alarming for "proportions fight a little".

### Insights (`screens/Insights.tsx`)
1. **M. Six tinted cards cycling green/sand/coral**, 483 words and 3940 px, using statistical framing: "How the wearing is shared · 2 of 7 kinds · a few do the work"; "What your closet is made of · 41 of 49 worn" with 4 tabs (Kind / Colour / Formality / Season) and 20 bar rows; and cost per wear. Interesting once; not an everyday screen.
2. **M. The empty state repeats one sentence four times** ("Nothing has been recorded as worn yet. Use 'Wore it today'…"), one per card, and shows a 30/90/All-time switch over nothing (`phone-e-insights.png`). One empty state for the page would do.
3. **M. Overlap:** with What's missing ("Not worn yet", "Worn most") and with Worn.
4. **L.** "The wear log goes back 20 days" is internal terminology ("wear log").

### Review (`screens/Review.tsx`, `Review.css`)
1. **M. The sticky "That's right / Skip for now" bar sits above the tab bar** and covers a row of colour chips (Blue, Light blue, Green, Olive… are hidden behind it in `phone-review.png`). The full chip list never shows at once.
2. **M. Developer-ish text:**
   - "Claude was 50% sure" / "65% sure" under each field.
   - "Its guess is chosen; tap another if it's wrong".
   - A keyboard-shortcut legend ("On a computer: ← → or 1–9…") shown on a phone too.
3. **L.** A large photo (about 310 px tall on a phone) pushes the question below the fold.

### Onboarding and first run (`screens/Setup.tsx`, `Login.tsx`, `landing.ts`)
1. **M. "You're set" shows `tailscale serve --bg 8802`** (the port, in a code box) and "The README has the steps": a developer instruction on the first screen after choosing a passphrase. On an iPhone over Tailscale it is irrelevant (you are already there).
2. **M. No guided first run.** After "Start with my own closet" the owner lands on an empty closet whose first element is the background-removal warning (above). Other first-run states:
   - Today's empty state is good: it says exactly what to add.
   - Missing asks life questions.
   - Insights repeats its empty sentence 4×.
3. **L. The Setup and Login cards** are clean: 36 and 33 words. Good.

### Error, loading and empty states (cross-page)
- **H. There is no error boundary anywhere** (`grep ErrorBoundary` finds nothing). A response of an unexpected shape on Today (I passed a place object instead of a string in my weather fake) rendered a **completely blank cream page**, with no tab bar, no message and no way out but reloading (`phone-today.png` from the first run, since overwritten). Any render exception does the same.
- **M. Loading states differ per page.**
  - As worn: blank grey box.
  - Today while Claude is choosing: a waiting card with "Show Closet's own picks meanwhile".
  - Missing: about 3 s on a cold phone load.
  - There is no shared skeleton. On the slow link the owner uses, pages assemble piece by piece.
- **M. The offline banner wording is long** (two sentences) and sits on every page.
- **Good:** the Today empty state; the closet empty state with its demo offer; Archived empty.

## 4. Cross-cutting inconsistencies

1. **Item thumbnails come in at least six sizes and treatments:**
   - Today: large tiles with names under them and a ⋯.
   - Closet: tiles with name and "Kind · Colour".
   - Worn: medium tiles with no names, then the names as text.
   - Trip: small tiles with truncated names ("White canvas…").
   - Missing: small tiles with no names.
   - Insights: rows with bars.
   - Some tiles have a border (photo items), some don't (drawings): see the yesterday strip and the Worn rows.
2. **Segmented controls everywhere, each doing something different:**
   - Pieces/As worn (Today, and again inside a trip);
   - Photos/Drawings (Closet; icons only on a phone);
   - Suggestions/Wishlist (Missing);
   - Last 30/90/All time and Kind/Colour/Formality/Season (Insights);
   - No laundry/On one day/Every few days (Plan a trip).
3. **Card surfaces:**
   - White cards with a ring (Missing, Worn, Trips).
   - Tinted cards: coral (yesterday's outfit), green (Why this works, "Tell it how you live"), sand (notes, wishlist), and Insights cycling all three.
   - Yellow warning boxes (Today weather, trip warnings).
   - Tints are used both as decoration (Insights) and as meaning (warnings), so colour carries no reliable signal.
4. **Headers:**
   - Today: title + date + 2 pills.
   - Closet: title + count + a ghost text button.
   - Missing: title + a pill on its own line.
   - Worn: back link + title + count + outlined button with icon.
   - Trips: title + filled primary button.
   - Insights and Review: back link + title + subtitle paragraph, or none.
   - Five header patterns for the same job.
5. **Primary actions:**
   - Filled pill: I'm wearing this, I'll look for this, Plan a trip, Answer a few questions.
   - Outlined pill: Record an outfit, Would this work?, Download.
   - Underlined text link: See another idea, Ask Claude again, Review, Show, Change, Settings.
   - Bare bold text: Not for me, Not now, Take something else.
   - Disabled primaries are dashed outlines (Search, Work out what to pack, Would it work?, Send). They look like empty placeholders rather than buttons waiting for input.
6. **Labels:** the terracotta monospace capitals ("WHY THIS WORKS", "LOOK FOR", "FROM YOUR CLOSET", "YOU", "CLAUDE", "COMING UP" at 31 px on Trips) are used for section heads, for chat speaker names and for a page-level heading. "COMING UP" on Trips is far larger than any other label.
7. **Back links:** some pages have a "‹ Parent" link (Worn, Insights, Would this work?, Trips sub-pages); peers such as Review have none. The tab bar lights a different section than the page's own name (Trips → Today, Review → Closet).
8. **Vocabulary:**
   - The page "What's missing" is labelled "Missing" in the tab bar. "Missing" reads as "lost items".
   - "Closet" is both the app's name and a tab, and the app refers to itself in the third person ("Closet says what to pack", "Closet's own picks").
   - Claude is credited by name in about 10 places on Today.
9. **The same facts appear on two or three pages:**
   - unworn items: Insights, Missing;
   - worn most: Insights, Missing ×2;
   - rating yesterday: Today, Worn;
   - recording a wear: Today, Worn, Item;
   - weather / place: Today's "Change", Settings "Where you are", the trip form;
   - "How you live": Missing, Settings.

## 5. Information architecture: what to merge, remove, keep

**What the app is for** (README, DECISIONS: "Every day starts on Today"): dress me today, from what I own, and learn from what I wore. Everything else supports that or is occasional.

**Merge:**
- **Worn into Today**, as a "Recent" strip or a section below the outfit. That gives one place to record and rate wears, and the coral yesterday card and Worn's rating become the same thing. Recording by hand becomes a small link.
- **Insights into What's missing**, retitled, for example, "Your wardrobe". It covers the gaps (top 3), unworn pieces (one list, offering Archive) and worn-most (one list). Drop the "how the wearing is shared" and "made of" charts, or put them behind "More numbers". This removes the duplicated "Also worth knowing".
- **Would this work? and the Wishlist** become two actions inside that same page ("Thinking of buying something?"), not a header pill plus a segment.
- **Review** becomes a filter of the closet ("Needs a check") and a one-at-a-time flow launched from it, not its own sidebar link.
- **Archived** stays as a filter (already the case).

**Remove or hide by default:**
- The weather/day "note" form.
- The thumbnail strip and the arrows on Today; keep the swipe with the dots.
- The repeated teaching lines.
- The "Claude on today" line (fold it into "Why this works").
- Keyboard hints on touch devices.
- The Tailscale command on the Ready screen (keep it in Settings → Phone access).
- The model banner on the closet: say it once on Add, where it matters.
- Cost-per-wear and the price-check/shop-search features in the Wishlist read as experiments built ahead of need, and DECISIONS shows the owner never asked for them. Park them behind the wish card's own page.

**Proposed minimal structure (phone tab bar: 4 places plus Add):**

| Tab | Contains |
|---|---|
| **Today** | The day line (weather + place, with occasion and mood as one compact control) → one outfit card at a time (swipe), with I'm wearing this → a short "Why" → "Tell Claude" (opens a sheet over the outfit so the outfit stays visible) → *Recent outfits* (the last 7, rate inline; "See all" opens the history). Trips: a "Packing for a trip?" row when one is coming up, plus an entry in a ⋯ menu. |
| **Closet** | The grid with search, one Filter button and a single status line ("5 to check · 4 in the laundry"). Item detail. Review as a mode of the closet. |
| **(Add)** | Unchanged (separate audit). |
| **Wardrobe** (was Missing + Insights) | The top 3 things worth buying, wishlist, "Would this work?", and unworn and worn-most lists. "How you live" is asked here only once the closet can dress you. |
| **Settings** | Unchanged (separate audit), keeping Trips' laundry counts and "How you live" in one place each. |

- **Desktop:** the same four items in the sidebar. Trips stays a full page reached from Today, or as a fifth sidebar item on desktop only.
- **Result:** 11 top-level destinations (Today, Worn, Trips, Closet, Archived, Review, Insights, Missing, Would this work?, Wishlist, Settings) become 4, with every current feature still reachable in two taps or fewer.

## 6. The ten most important findings
1. **H.** No error boundary: any render error blanks the whole app with no way back (app-wide; `App.tsx`, `Shell.tsx`).
2. **H.** Today's outfit card has large blank areas: about 300–450 px on a phone and about 350 px on a desktop (`Today.tsx` Carousel/OutfitCard).
3. **H.** As worn shows an empty grey box with no progress while the layers load, worst over Tailscale (`Today.tsx`, `OutfitFigure.tsx`).
4. **H.** What's missing is 5.9k px and 733 words, with 9 cards of near-identical prose, an "Also worth knowing" section that repeats the cards, and "the engine", ISO dates and grammar errors from `backend/closet/gaps.py`.
5. **H.** Today shows a made-up forecast ("14–20°C · no rain") right above "The weather could not be fetched".
6. **M.** Each page fires 8–10 identical bootstrap calls (`items` and `review` fetched 2–3×) plus one request per drawing (40–60 on the closet): that explains much of the lag on the phone.
7. **M.** Duplicated features: wears are recorded in 4 places, yesterday is rated in 2, unworn and worn-most stats appear on 2 pages, and where you are is set in 3.
8. **M.** Too many controls above the content: about 17 on Today before the first garment, and 3 notes plus a toolbar on the closet before the first tile.
9. **M.** Inconsistent building blocks: 6 thumbnail styles, 5 header patterns, 6 segmented controls, tint colours used both as decoration and as warnings, and dashed "disabled" primary buttons that look like placeholders.
10. **M.** Hidden or misfiled places: Trips is off the phone tab bar and lights "Today", Insights is a ghost link on the closet, and the Review action bar hides chips behind the tab bar. Developer text is shown to the owner: the Tailscale command on Ready, "Claude was 50% sure", keyboard legends on a phone, "wear log".
