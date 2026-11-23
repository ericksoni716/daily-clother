# The two reviews of 23 November 2026

On 23 November two reviews looked at `main` without changing it: one of the rules Today, trips,
the laundry, What's missing and Insights follow, one of the screens. This page is their index; the
detail is in the tests and in `docs/DECISIONS.md` (search for "logic review" or "the review of the
screens").

## How they were made

**The rules.** Each of 30 faults was shown by a failing test. Sweeps ran on the demo closet and on
small closets built by hand: 420 days of weather, occasion and mood, every piece built around and
left out, trips of 1 to 30 days. Spending, backups, History and shopping were not reviewed.

**The screens.** The phone check, then the app driven by hand at phone and computer width, on the
demo closet, with Claude stood in for and the weather out of reach. It found 35 faults. It could
not see a real iPhone, real Claude or a working forecast.

## The short version

- Filling in last week's outfits put clean clothes in the laundry.
- A trip on its third day always said the weather had changed, and Plan again repacked the days
  gone.
- What's missing counted lounge pants, pyjamas and a robe as everyday clothes, and asked for
  more trousers like the lounge pants.
- Wearing an outfit built around a piece left Today saying "No outfit today yet".
- A piece's choices opened under the tab bar; asking Claude again took the outfits off the page.
- Today's reasons contradicted their own card ("a single layer is enough" beside "this will be
  cold").
- A price typed with a decimal comma was saved a hundred times too high.
- A failed call showed the server's raw words with no Try again.

All are fixed.

## What was done

The fixes: #316 the outfit rules, #317 what to buy and Not worn, #318 Today, Worn, Trips and the
wear, laundry and trip rules, #319 the Wardrobe, #322 the shared parts of the screens (failed
states, dates, toasts, prices, banners, sheets and keys), #324 the closet (its panel on a
computer, All clean's Undo, one list in Filter, the search). Still to come are the item page
and "Would this work? by hand". Each rule's test is in its module's own test file.

### The rules

| Finding | What was done | Where |
|---|---|---|
| 1. A trip under way says the weather changed each time, and Plan again repacks days gone | Days gone keep their weather and outfits; the days to come are dressed from the bag | #318 |
| 2. An outfit recorded for an earlier day sends clean clothes to the laundry | A wear for a day the piece has been washed since is kept but not counted | #318 |
| 3. Lounge pants ask for "another pair of trousers" | Clothes for home count for nothing in What's missing (one rule with swim trunks and sport shoes) | #317 |
| 4. Lounge pants count as a second pair of trousers to change into | As 3 | #317 |
| 5. A bath robe is "your warmest outer layer" | As 3 | #317 |
| 6. A coat waiting to be mended brings "A warm winter coat" | Counts as owned, as one in the wash does | #317 |
| 7. Lounge pants shown as a piece a suggestion is based on | As 3 | #317 |
| 8. Pyjamas count as owning a plain tee | As 3 | #317 |
| 9. Would this work? says "you have it already" because of lounge pants | As 3 | #317 |
| 10. Wear this again shows no outfit when a piece is waiting to be mended | Asks the same list as the outfits; the place is filled | #316 |
| 11. Wear this again shows no outfit for what was worn to tennis | Pieces Nines never offers come back with their outfit | #316 |
| 12. Record an outfit refuses a tie, a watch, gloves or socks | Other pieces go with the accessories | #318 |
| 13. "A single layer is enough" on a day the card says is too cold | Said only when the outfit is warm enough | #316 |
| 14. Suede boots "stand up to the rain" beside "the rain spoils" them | No reason where the warning applies | #316 |
| 15. "All neutral colours" with a mustard beanie | Colour sentences count the hat and scarf | #316 |
| 16. "The warmest you have" once the parka is set aside | "The warmest you can wear today", on Today and a trip | #316, #318 |
| 17. On a freezing wet day the thin mac replaces the parka | Rain-proof only when one is warm enough; otherwise an umbrella | #316 |
| 18. A coat worn all week asks for a second coat | Only tops, middle layers and bottoms ask, never while one of the kind is unworn | #317 |
| 19. A sport day in jeans and an oxford, "right for sport" | Such pieces are a makeshift, said so | #316 |
| 20. The scarf stays home at -8°C because its colour competes | On a cold day the warmer accessory comes first, whatever its colour | #316 |
| 21. After a break from recording, the whole closet is "not worn" | Says when nothing was recorded since | #317 |
| 22. A heavy puffer is not a "warm winter coat" | It counts | #317 |
| 23. A leather belt on joggers | No belt with a drawstring or elastic waist | #316 |
| 24. Swim trunks and tennis shoes listed under Not worn | Left out | #317 |
| 25. "The jeans is…" | Pairs spoken of as plural | #316 |
| 26. "The only boots you have", "only one outfit that differ", stored dates | Corrected; dates in words | #317 |
| 27. The Wardrobe speaks of "the engine" | Gone | #317 |
| 28. From a phone a time zone ahead, today's outfit is "in the future" | The computer's tomorrow is accepted | #318 |
| 29. Changing a trip under way unpacks what was worn yesterday | What the saved plan packed stays packable | #318 |
| 30. A month away with one early wash takes one set of sleepwear | One set per week of the longest stretch between washes | #318 |

### The screens

| Finding | What was done | Where |
|---|---|---|
| B1. Wearing an outfit built around a piece leaves "No outfit today yet" | Wearing ends building around | #318 |
| B2. Asking Claude again takes the outfits off the page | They stay, dimmed, keeping their space | #318 |
| B3. A piece's choices open under the tab bar (Today, Worn, a trip) | They open in a sheet | #318 |
| B4. A price with a decimal comma is saved a hundred times too high | One reader for every price box; what it cannot read is refused | #322 |
| B5. Worn's ⋯ button drawn 6px wide | Drawn at its size | #318 |
| A1. The price banner arrives late and pushes every screen down | A banner that arrives late waits for the next screen | #322 |
| A2. Add: a late notice moves the buttons; instructions before buttons | The buttons first, the explanation folded, the notice after them | #322 |
| A3. Today's Change puts a tall panel above the outfits | A sheet, "Where you are" | #318 |
| A4. "I'll look for this" folds the card and the page jumps | The card stays, with Undo | #319 |
| A5. On a computer, opening an item rearranges the grid; no Close | The grid keeps its rows and the piece its place; Close, Escape and Back close the panel, and focus goes into it | #324 |
| A6. A failed call shows raw words and no Try again | Every screen named says what failed, with Try again | #322 |
| A7. "All clean" has no Undo and leaves a wrong empty screen | Undo in the line under the search puts each piece back as it was; an empty laundry says so; showing the laundry moves nothing | #324 |
| A8. "Stop watching" removes a find at once | The find stays in its place with Undo, which puts it back with its price history | this batch |
| A9. Record an outfit is a very long panel of every piece | A sheet with search and groups | #318 |
| A10. A piece opened from Worn goes back to Today | Goes back to Worn | #318 |
| A11. A trip leads with warnings; a failed forecast said eleven times | Leads with what to pack; said once | #318 |
| A12. The outfit card has a blank band | As tall as the outfit in front | #318 |
| A13. Filter has three lists for what a piece is | One list, What it is: the groups, opening to their categories and kinds; one chip | #324 |
| P1. Dates and colour codes in History and Advanced | One way to write dates; History names the shade | #322 |
| P2. "Kind not said yet" on a piece called a polo | One word for what it is, from its kind or else its category, on the row and the line under the name | this batch |
| P3. Words: grammar, things said twice, one thing named two ways | Partly: the Wardrobe's words (#317, #319), "Build around", "Where you are" (#318), the banner, Add and Advanced (#322). Left: "wears looked at", "the kinds of day the closet is tried on", names capitalised mid-sentence, Would this work? saying a thing twice | #317, #318, #319, #322 |
| P4. "How was yesterday's outfit?" cuts its pieces off | Every piece shows | #318 |
| P5. The "Saved" toast covers what you use next | Toasts at the top; faults in a row are one toast | #322 |
| P6. A trip's "Why this works" rows are 36px | A whole tap high | #318 |
| P7. Keyboard: Escape and focus in a few places | Escape closes Change (#318), editors and Today's sheets; focus moves on; Your style keeps the sheet (#322) | #318, #322 |
| P8. "How you live" is a third kind of overlay | The same sheet as the rest | #322 |
| P9. The search box shrinks to "S" | Never narrower than its word; it also finds a shade, brand, material or note | #324 |
| P10. The page behind a phone sheet scrolls | Held still | #322 |
| P11. Reasons after a rating do not follow it | They follow it | #318 |
| P12. Reload forgets | Partly: Today's changes kept (#318); the closet's search, filters and place in the list kept in its address (#324); Would this work? keeps what was typed and the answer for the day (this batch) | #318, #324, this batch |
| P13. "Asking again…" wraps the heading | Said over the outfits | #318 |
| P14. Offline, the same sentence on each card | Said once | #318 |
| P15. Choosing a colour chooses a shade | A colour alone is kept as the colour, with no shade lit until you choose one; the chosen chip's swatch shows | this batch |
| P16. Smaller things the accessibility check reports | Heading level, the weather strip by keyboard, spoken names fixed | #322 |
| P17. Text sizes ignore the browser's text size | Type follows the browser's text size (not yet the iPhone's own setting) | #322 |

The rules: 30 fixed. The screens: 30 fixed, 2 partly, 3 in the next batch, 0 open.

## Decided against, or narrower than asked

- Finding 2: wears carried over from earlier weeks are not followed (DECISIONS, Stop C).
- A11: a trip's temperatures cannot be typed by hand (BACKLOG, left over).
- Your nines counts lounge pants and swim trunks, since they were worn (DECISIONS, "The Wardrobe
  made short").
- Of the rules review's "worth a second look", four were acted on in #316 and #318 (a cold
  morning before a hot day, heavy jeans when hot, tapered legs, loungewear pinned on a trip). The
  rest stand as decided.
