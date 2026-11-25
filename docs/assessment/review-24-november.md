# The two reviews of 24 November 2026

On 24 November two more reviews looked at `main` without changing it: one of the rules, one of the
screens. Each covered what had been added since the reviews of 23 November (`review-23-november.md`)
and the parts those left out, and repeated none of their findings. This page is their index; the
detail is in the tests and in `docs/DECISIONS.md` (search for "the second logic review" or "the second
review of the screens").

## How they were made

**The rules.** Each rule was read, then tried on small closets built by hand, through the rules
themselves and through the app's own routes with the clock moved. A sweep ran four closets through 48
days each across the year end (18 December to 3 February): Today asked every day, seven days ahead
dressed, outfits worn, pieces sent away and brought back, trips saved, plans and kept outfits made.
The edges were tried too: an empty closet, one piece, everything in the laundry or away, a one-day
trip, a trip over a month end and over the year end. It found 9 faults, each shown by a failing test,
and seven suspicions it did not show. The screens, the restore of a backup and the real services
(Claude, the weather, shops' pages) were not reviewed.

**The screens.** The phone check, then every journey driven by hand at 375 and 320 wide and at 1280,
light and dark, on the demo closet with Claude and the weather stood in for. It found 59 faults (10 it
called P2, 49 P3) and counted the words of Today, a day ahead and a trip day. It left out the four
parts of Settings that were being reworked, and could not see a real iPhone, real Claude, a working
forecast or a trip past its first day.

## The short version

- The laundry day at home washed what you wore on a trip still under way.
- A trip a day or two off left out a piece due back from the cleaner's; removing an old wear sent a
  piece back to the cleaner's.
- A plan for a day ahead could leave Today with nothing to wear, and said a piece was "left out
  today" that you had not left out.
- When keeping Claude's answer failed, the same price check was asked again every hour.
- "I'm wearing this" took away the outfit you tapped; changing an outfit pushed it and its button
  down; the dots under the outfits moved.
- The closet opened on an empty laundry or "Needs a check" view; in the Away view a second tap on
  "It's back" brought back the wrong piece.
- Removing a wish could not be undone.
- Today read 550 words by the phone check's old count, against a budget of 350.

All are fixed. Of the screens' 59 findings, 57 are done and 2 were decided against.

## What was done

The fixes: #335 the rules (the nine faults and four of the suspicions, migration 0054), #336 the
closet and a piece's page (ten findings), #337 the Wardrobe, the wishlist, Trips, Worn, Add and the demo
closet (twenty-three findings), and #TODAY Today, a day ahead and a trip day (twenty-four findings).
On the way CI found two faults, neither a finding of either review, both fixed in #337: an answer asked
for just before a change was taken as the new one (it was on `main` already), and, on CI's Windows job, a
copy of Nines just started could be taken for the one before it. #338, merged after #337, finishes that
second fix: the check for a running copy reads its lock again after the copy answers. #334 (Settings tidied) answered the owner's own four complaints that day and is not a
finding of either review. Each rule's test is in its module's own test file.

### The rules

| Finding | What was done | Where |
|---|---|---|
| 1. The laundry day at home washes what you wore on a trip still under way | What is in the suitcase waits for the first laundry day after the trip | #335 |
| 2. A trip in the next two days leaves out a piece due back from the cleaner's | Packed clean, by the same rule as a day ahead, and the plan says it counts on it | #335 |
| 3. Removing an older wear sends a piece back to the cleaner's | Only on the day of the return, as its Undo lasts; later the piece stays where it is | #335 |
| 4. A plan leaves Today with nothing to wear, and says "left out today" | Today asks again without holding the planned piece, and one sentence names the plan it uses | #335 |
| 5. When keeping Claude's answer fails, it is asked again every hour | The check or the weekly look counts as made once Claude has answered | #335 |
| 6. A rating taken away on the computer comes back from the phone | The phone's older tap is refused, as for a changed rating | #335 |
| 7. A price that came down while sold out is never news | News once it can be bought | #335 |
| 8. On a trip that packed nothing, Today blames the bag | The real reason, straight away | #335 |
| 9. "Blue jeans is back in your closet." | "are back" | #335 |
| Suspicion: "Your size is in stock" stays once it was true | Goes when only the page said it and stops saying it | #335 |
| Suspicion: undoing a return after a wear loses that wear from the count | The wears since stay counted | #335 |
| Suspicion: an away piece in today's trip bag "can be built around once it's back" | Its page builds an outfit around it | #335 |
| Suspicion: a day the trip was set aside counts as the trip's when it is planned again | Not when it is planned again that day; on a later day it still does (BACKLOG) | #335 |

### The screens

| Finding | What was done | Where |
|---|---|---|
| 1. "I'm wearing this" takes away the outfit and puts a notice above | The card stays, says you are wearing it, with Undo where the button was | #TODAY |
| 2. The closet opens on an empty laundry view | It opens on all your clothes, keeping the search and filters; Undo after All clean stays while you are in the view | #336 |
| 3. The closet opens on an empty "Needs a check" view; "0 to check" | The same, decided once its count arrives; "0 to check" is never said | #336 |
| 4. "It's back" moves the rows | The row changes in place and keeps its place and height | #336 |
| 5. "Remove from the list" with no Undo | Undo in the wish's place on the wishlist puts it back whole, while Nines keeps running | #337 |
| 6. Try again on a piece leaves an empty card | Asks again for everything the page waits for | #336 |
| 7. A day ahead says a piece must be back only under the first outfit | Under every outfit that counts on it | #TODAY |
| 8. Not this piece and Build around put rows of chips above the outfit | Said under the outfits, with Clear all | #TODAY |
| 9. Offline, Today says it twice and pushes the button off the first screen | The banner says it; the time saved is a few words beside the weather | #TODAY |
| 10. The demo closet's Add names a button that is not there | "Use Leave, above" | #337 |
| 11. The dots move when the outfit changes | In the outfits' heading; "1 of 3" gone | #TODAY |
| 12. The row under the button wraps | One line in every state | #TODAY |
| 13. With a trip coming, Today points to Trips twice | The foot line only when no trip is coming | #TODAY |
| 14. On a trip day, "Going away?" at the foot | Not on a trip day | #TODAY |
| 15. The same sentence under each of three outfits | Not done (below) | |
| 16. Reasons read badly with a name in them | "The madras plaid shirt is the only pattern." | #TODAY |
| 17. The reasons write dates a third way | "on Saturday 14 Nov" | #TODAY |
| 18. Small things to tap on Today | Try again, a planned day's link, the trip's line and the arrow back are 44 points | #TODAY |
| 19. A planned day says "the only outfit" | Headed "Your plan for Fri" | #TODAY |
| 20. A day inside a trip shows the occasion and mood | Not there | #TODAY |
| 21. A failed read said twice, two Try again | One message in the shared words, one Try again for both | #TODAY |
| 22. A day ahead that fails says "today's outfits" | It names its day | #TODAY |
| 23. "The weather" alone as a label | "The weather isn't known yet." | #TODAY |
| 24. A day past 60 days offers a Try again that cannot work | One sentence and the way back; the days sheet says it under its date box | #TODAY |
| 25. The weather line leaves a dot at the end of a line | No dot at a line's end | #TODAY |
| 26. At 320 the first screen loses the button | "Another day" stays beside the date | #TODAY |
| 27. With Claude choosing, the page under the outfit moves twice | What is under the outfits sits where it will be while they are chosen (partly: below) | #TODAY |
| 28. Offline, a planned day is laid out differently | Laid out as online | #TODAY |
| 29. Names keep their capitals mid-sentence | A small letter in More numbers; Today's notice that had them is gone (1) | #TODAY |
| 30. Offline, each screen adds its own sentence | The banner says it once; a screen adds only what is its own | #337 |
| 31. "When you wore it": pictures 40 by 46 to tap | The whole row opens the outfit's choices | #336 |
| 32. One list writes its days two ways | Not done (below) | |
| 33. A piece at the cleaner's reads "Clean" and offers the laundry | Where it is leads; the laundry line waits until it is back | #336 |
| 34. A part of the closet's line with a search on says "Nothing matches" | A tap on the line clears the search and the kind | #336 |
| 35. Away: a long name cut to one line | Two lines, and the whole row opens the piece | #336 |
| 36. Filter: the title and Done scroll away | A sheet's head stays at its top, in every sheet | #336 |
| 37. On a computer, names cut beside a piece's panel | Two lines, cut after a whole word | #336 |
| 38. A wish says its name twice, the first time cut | Headed by the whole name; the find starts at its shop and price | #337 |
| 39. Would this work? says the repeat twice, "in the log", "kinds of day the closet is tried on" | Said once, in plain words ("most kinds of day") | #337 |
| 40. "Check now" names Claude and moves Find more | "Checking the price…" in place of "Last checked" | #337 |
| 41. Find more puts the new finds above the button | After the ones already there | #337 |
| 42. "Add by hand" and "Add a link" open a form in the page | In a sheet; Escape closes it | #337 |
| 43. You might like: after Save the buttons stack, no Undo | "On your wishlist" and Undo on one line | #337 |
| 44. You might like: a name cut beside a hanger | Three lines | #337 |
| 45. You might like: results push the Wardrobe down | The card keeps the room of three picks while it looks | #337 |
| 46. Small things to tap in the Wardrobe | 44px | #337 |
| 47. "0 of 12 packed" above "9 pieces" | "9 pieces and 3 basics" | #337 |
| 48. Day by day: every name cut | Pictures alone on a phone, each opening a sheet that names it | #337 |
| 49. The list and the trip name warnings two ways | One way, the trip's | #337 |
| 50. Plan a trip: 30 words about the weather service in the form | Behind "What is sent to look up the weather" | #337 |
| 51. A plan with no weather says so four ways and offers Save | Said once, with Try again and Type the temperatures; no Save until a day is dressed | #337 |
| 52. Outfits you keep: the count stays after Remove | It counts down, and back up with Undo | #337 |
| 53. Add says "going into your closet" twice | Once | #337 |
| 54. Too few clothes: what is missing said twice, Another day offered | One headline naming what is still missing; no other day | #TODAY |
| 55. An empty closet asks you to "wear and rate a few more pieces" | No You might like card until there are clothes | #337 |
| 56. The demo strip's Leave is small | 44px | #337 |
| 57. Settings' Where you are leads with 70 words | Controls first, the words folded | #337 |
| 58. Backups name the folder in a word you may not know | "a folder your computer copies to the cloud" | #337 |
| 59. The guide describes "Why this works" as the page does not show it | `docs/USING.md` says what is on the screen | #TODAY |

The rules: 9 fixed, and 4 of the 7 suspicions. The screens: 57 fixed, 2 decided against.

### Today's reading load

The phone check counted 550 words for Today, 434 for a day ahead. More than half of that was never in
view: the two outfits behind the dots, layer words hidden on a phone, and what is folded. The phone
check now counts what a phone shows, scrolled through (DECISIONS, "Today and a day ahead, the second
review of the screens"), and four cuts were made ("1 of 3", Type temperatures, the trip row's
question, the foot line). By that count Today is 219 words, a day ahead 174, a trip day 260: all inside
the budget of 350 in `docs/DESIGN.md`.

## Decided against, or narrower than asked

- "Why this works" stays open under each outfit, as decided earlier. Folding it would take about
  another hundred words off Today; that is the owner's choice (DECISIONS has the row).
- Recent outfits stays on Today, and so do the occasion and mood chips.
- Finding 15: one outfit is in view at a time, by design, so a sentence under each is read once.
- Finding 32: the family of dates is decided ("One way to write a date").
- Finding 27: what is under the outfits still moves a little for a closet whose reasons are much
  shorter or longer than the demo's, and once when Claude's outfits replace the rules' (BACKLOG, left
  over).
- You might like: after Save a pick shows "On your wishlist" and Undo, without More like this, so the
  row keeps to one line at 320 wide; More like this is one tap away from the wish's Find more.
- Of the rules review's suspicions, three were not acted on: pieces ticked for a trip that starts
  tomorrow are still offered today; a link whose page words change every day is asked about every
  day; an outing naming a piece worn earlier today could not be made to happen.
- Of its "worth a second look", the laundry day while you are away is the owner's question (below).
  The rest stand as decided.

## Left for the owner

- Whether "Why this works" should be folded on Today.
- Whether a laundry day during a trip should wash what was left in the basket at home. It still does;
  only the suitcase waits.
- Whether pieces ticked for a trip that starts tomorrow should be held back from Today.
- What each fix left undone is in `docs/BACKLOG.md`, under "Left over from finished work".
- Neither review could see a real iPhone, real Claude or a working forecast: those are for the owner
  to try after the next release.
