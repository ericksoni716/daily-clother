# Changelog

What changed for the person using Closet, newest first. Releases are on the
[Releases page](https://github.com/ericksoni716/daily-clother/releases); versions before
0.9.0 are described there only.

Every change the owner can see gets a line under **Unreleased** in the pull request that
makes it: a sentence in plain words about what is different, not about the code. A change
nobody using the app would notice (a refactor, a test, a doc) gets none.

## Unreleased

### Added

- Today shows your **Recent outfits** under the outfits: the last few you wore, each rated with
  a tap and saying "Saved" as it saves, with yesterday's question first and **See all** for
  every outfit you wore. When a trip starts within two weeks, a **Packing for a trip?** row
  opens it, and a link at the foot of Today opens Trips.
- The closet's line at the top, "5 to check · 4 in the laundry", shows only those pieces when
  you tap a part: **Needs a check** then offers **Check them one at a time**, and the laundry
  offers **All clean**.
- You can talk to Claude about your style from Settings: Your style, Talk to Claude about your
  style. With nothing said yet that day it asks one question it can't tell from your clothes
  (whether you run warm, what you wear for work, colours you never wear…), answered with a tap
  or in your own words, or skipped. Claude answers what you write and may offer a line to keep,
  which goes into Your style only when you save it.
- Your style is now a list of lines, each saying where it came from: a starting rule, something
  you said, a line kept from a conversation, or your answer to a question, with the day. Each
  line can be changed or removed (with Undo), and you can add one by hand. What Claude reads is
  the same as before until you change a line.
- A line you kept from a conversation, on Today or in Settings, can be taken back with Undo.

### Changed

- The app has four places and Add: **Today**, **Closet**, **Wardrobe** and **Settings**, in
  the bar at the bottom of a phone and in the menu on a computer. Worn and Trips are now in
  Today, the review in the closet, and What's missing and Insights are one page, **Wardrobe**.
  Old bookmarks and the Home Screen app still open the right place.
- The Wardrobe leads with the three things most worth buying (**See all** shows the rest),
  then **Thinking of buying something?** with Would this work? and your wishlist, then what you
  have not worn and what you wear most. The other figures, cost per wear among them, are under
  **More numbers**. "Also worth knowing" is gone, since it repeated the rest.
- A wish opens on a page of its own, with its note (which says when it is saved), shopping
  and prices.
- Today is shorter above the outfit: the Worn and Trips buttons, the arrows and the strip of
  small outfits under the outfits are gone (swipe, or tap the dots), "Tap a piece to see it"
  is said once under **Changing an outfit** instead of in every outfit, Claude's reading of
  the day is in "Why this works", and the note about the day is folded under **Change**.
- The notice about the files that cut clothes out of photos is shown on Add, not on the
  closet. The review shows its keyboard keys only on a computer, and has **‹ Closet**.
- The screen after choosing a passphrase no longer shows the Tailscale command: it says that
  Settings, Phone, has the steps.
- Settings is a short page in eight groups: Your style, Everyday (the weather's place, how you
  live, the laundry), Claude, Updates, Phone, This device, Your data, then Log out. Claude,
  Updates and your backups each say how they stand in one line, in red with the one thing to
  do when something is wrong. Your style shows the start of what Claude reads, with the whole
  text a tap away under Edit the text. The place, and what is sent where to look up the
  weather, open under Change.
- Everything you set once is on a screen of its own, Advanced settings, at the foot of
  Settings and under Manage beside Claude: the demo closet, start at login, the API key, which
  way to Claude is tried first, the monthly limit and spending, how updates are fetched, the
  backup folder and Back up now, storage, where the background-removal files come from, the
  data folder and the version. The Settings link on the closet's background-removal notice
  opens it.
- On your phone, Settings no longer offers Quit Closet, starting Closet at login, typing a
  backup folder, or the background-removal files to put in place by hand: they are about the
  computer.
- Gone from Settings: the Plan a trip link (Trips is on Today), "No items are waiting to be
  described", the token counts under the spending, the second list of months, and the
  sentence that a copy run from source can't replace itself. How you live no longer asks for
  your style in a few words, which nothing used; Your style is where Claude reads it.
- Settings on the computer checks for a phone share every half minute instead of every few
  seconds while Tailscale is not installed, and looks the weather up only when you open
  Change.
- Closet says how far it has got with each new piece in one set of words, in one place each:
  a strip over the bottom of the piece's picture with its three steps (cutting out, describing
  and drawing, and for patterned clothes and shoes finishing the drawing), a small mark with
  the step on its closet tile, and one line, "Working on 3 items", above the closet that lists
  them. On Add, a row shows the upload until the photo is in, then the piece's progress
  instead of both at once. Short steps are no longer skipped: Closet checks every 2 seconds
  while anything is being done, measuring a pattern and drawing a shoe included, and asks
  only for the pieces being worked on.
- A shoe on the dressed figure wears the plain front view until Claude's drawing of it is
  ready. The front view traced from your photo is gone, and with it the front view picker
  and "Add a front photo" in Fix the details. Tracing a shoe from its side photo for the
  closet picture is unchanged.
- "‹ Closet" and the other back links go back to the page you came from, where you left it,
  instead of opening it afresh at the top. Back and Forward bring each page back to where you
  had scrolled it, even after a reload.
- A pressed button dims for a moment instead of shrinking, and Safari on the iPhone no longer
  zooms in when you tap a field.
- Fix the details opens over the page instead of pushing it down, and starts with a box to
  say what is wrong with the piece. The details one by one are a tap away in the same sheet.
  The demo closet, and times Claude can't be reached, open straight on the details and say
  why.
- Settings on your phone no longer shows the QR code and the commands for connecting the
  phone. It says how to add Closet to your Home Screen, and nothing once you open it from
  there.
- The Background removal card is gone from Settings. Closet downloads both files by itself
  when it starts, and a download that fails is tried again a minute later, ten minutes
  later, then every hour. The notice on the closet still says when something is wrong.
- Settings > Updates shows what is new in a release, folded under "What's new in" and the
  version, with its headings and lists set out properly instead of as raw text. A release
  made before this one shows no notes there.
- Settings opens all at once. It no longer waits for Tailscale, and its cards no longer
  appear one by one and push each other down. A phone share you have just set up shows a few
  seconds later without reloading the page or restarting Closet.
- Going back to a screen you have already opened (Worn, Trips, a trip, What's missing,
  Insights, As worn) shows what was there at once and refreshes behind it, instead of
  loading it again. While As worn draws a changed outfit, the last figure stays on screen.
- An item's page opens at once on what the closet already knows about it, instead of a blank
  picture, and fills in when the rest arrives.
- Changing an item no longer holds up the rest of the app while its drawing is redone, and a
  check for progress that finds nothing new no longer redraws the screen. The closet now
  follows a pattern being measured or a shoe being traced without a reload.
- In the demo closet, the seven pieces that have a photo are now drawn the way your own
  pieces are, so they look a little different: the jeans show their denim, the turtleneck
  its flecks, and the leather sneakers a thinner sole.

### Fixed

- If a screen fails to draw, it says so and offers Try again and Reload Closet, instead of
  leaving a blank page. The tab bar stays, so you can go elsewhere.
- A pinstripe keeps its thin line when it is drawn, instead of losing it at the pattern's seam.
- When a piece's cutout is made again, Claude describes the piece again from the new cutout.

## 0.9.0

See the [release](https://github.com/ericksoni716/daily-clother/releases/tag/v0.9.0).
