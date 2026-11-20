# What each screen does

A paragraph per screen, saying what it does today and what it already says, so a change has
one place to check before it adds a second copy. Installing, the iPhone, backups and the rest
of what the owner does outside the screens are in the [README](../README.md). Why a screen is
the way it is, is in [DECISIONS.md](DECISIONS.md).

Keep this short and true: when a screen's behavior changes, change its paragraph in the same
pull request. It describes the app as it is, not as the assessment wants it; where the two
differ, the last line of a section says where the screen is headed.

- Getting around: [Navigation](#navigation) · [First run and login](#first-run-and-login)
- Every day: [Today](#today) · [Worn](#worn)
- Your clothes: [Closet](#closet) · [An item](#an-item) · [Add](#add) · [Several pieces in one photo](#several-pieces-in-one-photo) · [Review](#review)
- Buying and packing: [What's missing](#whats-missing) · [Would this work?](#would-this-work) · [Insights](#insights) · [Trips](#trips)
- [Settings](#settings) · [Advanced settings](#advanced-settings) · [Things that work the same everywhere](#things-that-work-the-same-everywhere)

## Navigation

On a phone the bar at the bottom has five places: Today, Closet, Add (the round button in
the middle), Missing and Settings. Worn and Trips are buttons at the top of Today; Insights
is a link at the top of the closet; Review is a note at the top of the closet, with a dot on
the Closet tab, while anything waits to be checked. On a computer the sidebar starts with
Add clothes, then Today, Closet (with Review under it while there is something to review),
Trips and What's missing, with Settings at the foot.

The app opens on Today once the closet has enough clothes to dress from, and on the closet
before that. A back link ("‹ Closet") goes back to the page you came from, where you left
it; on a page opened straight from its address it opens the page it names. Back and Forward
bring a page back to where you had scrolled it. Routes are in `frontend/src/router.tsx`.

*Headed for:* four places and Add (assessment, "Proposed structure").

## First run and login

The first launch asks for a passphrase, then offers "Start with my own closet" or "Open the
demo closet". After that every device logs in with the passphrase. If the computer cannot be
reached, a screen says so and keeps trying; on a phone that has been used before, the saved
closet is shown with an offline banner and nothing can be changed.

## Today

`/today`. The day's weather for the place saved in Settings, an occasion and a mood to
choose, and outfits to swipe through, each drawn as worn (or laid out as pieces) with "Why
this works" and, when there is something to watch for, "Be aware". The rules choose outfits
at once; when Claude may choose, its outfits replace them when they arrive, and a card says
it is choosing. "I'm wearing this" records the outfit and its wears. "Not this piece" swaps
a piece out, and a piece can be chosen to build around. A note about the day ("In Lisbon
until Friday") changes what is dressed for. Under the outfits you can write to Claude about
them; it answers, may change the outfits, and may offer something to remember, which is kept
only when you tap it, with Undo beside it once kept. In the evening, or the next day, Today asks how the outfit went.
Tapping a piece opens it (`/today/item/<id>`).

Temperatures can be typed when the forecast cannot be fetched. The demo closet's outfits are
the rules' alone; nothing about it is sent to Claude.

## Worn

`/today/worn`, from the Worn button on Today. The outfits you wore, newest first, each with
its pieces, how it went (a rating and a note), "Wearing again" and a way to put its pieces in
the laundry. "Record an outfit" adds one by hand from pieces.

*Headed for:* part of Today, as the last few outfits with "See all".

## Closet

`/` (and `/archived`). A grid of your clothes with search, one Filter button (kind,
category, group, laundry, and In use or Archived) whose choices stay visible as chips, and a
switch between Photos and Drawings. A tile shows the piece's picture and name, and, while
Closet is working on it, a small round mark with the step it is at (1 cutting out, 2
describing and drawing, 3 finishing the drawing): turning while it is being done, dashed while
it waits, a warning sign when a step failed. While anything is being worked on, one line,
"Working on 3 items", floats above the grid and the tab bar; tapping it lists those pieces,
each with what is happening to it, and says once why they wait when it is something you can
see to in Settings. Notes at the top say how many pieces need a quick check and how many are
in the laundry. On a computer, choosing a piece opens it
in a panel beside the grid; on a phone it opens as its own page.

## An item

`/item/<id>`. The picture (photo, cutout or drawing, and for some pieces the back), with a small
mark on the drawing that lists what it leaves out. Under the name, one line says what the piece
is, its colour and how it sits ("Polo · Navy · Regular fit · Short sleeves"). It is read from the
same description the drawing is made from, with your corrections over it, so it never says
something the drawing does not show; each word of how it sits opens its detail to fix.
"Something wrong? Tell Claude" opens Fix the details: a sheet over the page (on a computer, a
box under the button) with the drawing and a box, "What's wrong with it?". Claude reads your
sentence, says what it understood, and nothing changes until you choose Make these changes.
"Change the details one by one" shows every detail the drawing is made from, by group, marked
when you set it, with when Claude described the piece. In the demo closet, or when Claude could
not be reached, the button says "Something wrong? Change the details" and the sheet opens on the
details one by one, saying why.

Then "Wearing and washing": Wore it today, put in the laundry or mark clean, and recent wears.
About it holds how you feel about it and one box, Notes for you and Claude, which Claude reads
when it chooses your outfits; it shows every note kept about the piece, and once you change it
the whole text is kept there. Four folds follow, closed until opened: Details (what it is,
colour, pattern, where it lives, formality, season, each a row that opens its choices, a sheet
on a phone), Shopping facts (brand, size, material, price, date acquired, condition), History
(every change, each of which can be undone), and the last one, with Describe it again, Archive
and Delete. A new photo can be taken in place of the old one, and a cutout that failed can be
tried again.

A shoe also shows its photos sorted into views, its traced side drawing with its own fixes,
and the drawing Claude makes for the figure, which takes several minutes and can be
corrected with a note.

While Closet is working on a piece, one strip over the bottom of its picture says how far it
has got: three dots for the three steps (cutting out, on the computer; describing and drawing,
by Claude, after which the drawing appears at once; and, for patterned clothes and shoes,
finishing the drawing: measuring the pattern, or sorting a shoe's photos, tracing it and
Claude drawing it), what is happening now, and where it runs and how long it takes, or what it
waits for (with Open Settings when that is where to see to it). The strip goes when the work
is done, and nothing on the page moves when it comes or goes. A cutout or a description that
failed says so under the picture, with Try again. A shoe's photos and its drawing for the
figure say the same words while their part is under way.

## Add

`/add`. One place for everything. Take photos with the camera on the page, choose them from
the library, choose a folder, or drop them on the page. Closet asks Claude what each photo
shows (one piece, several pieces, or a view of a shoe) and sorts them; a shoe's photos are
gathered into one shoe. Photos are made smaller in the browser and sent two at a time; a
list shows each one's upload until it is in, then, in the same row, how far Closet has got
with the piece (with the step's mark) and, once described, what Claude called it; it can be
paused, retried and cleared, and survives closing the tab. Why pieces wait, when it is
something you can see to in Settings, is said once above the rows. The same photo is not added twice. After that the piece is cut
out, described and drawn in the background; you do not have to wait on this screen.

## Several pieces in one photo

`/add/several/<id>`. For a photo of pieces laid out together: Claude draws a box round each
piece, you move, add, join or remove boxes (or draw them yourself), and each box becomes an
item of its own.

## Review

`/review`. After Claude describes a piece, only the details it was unsure of come here, one
piece at a time: "That's right", pick the right value, or "Skip for now".

*Headed for:* a way of looking at the closet rather than a place of its own.

## What's missing

`/missing`. Two views. Suggestions: what the closet lacks, found by rule from the clothes,
the wears, where you live and how you live, each with why, what it would be useful for, and
"Not for me" (hide it, and optionally similar ones) or add it to the list. "How these
suggestions work" and "What these suggestions are based on" explain them, and "Tell it how
you live" opens the same questions as Settings. Wishlist: what you decided to look for,
added from a suggestion or by hand, each with a note, "Find some" (Claude searches shops;
each find is checked against the closet and its price can be checked again later), and "I
bought it".

## Would this work?

`/missing/check`, from What's missing or from a find. A piece you might buy, from a photo or
described by hand, checked against the closet by rule: what it goes with, what it repeats,
what it would fill, what would hold it back, when you would wear it, and example outfits.

## Insights

`/insights`, from the link at the top of the closet. How the closet is used over a period
you choose: what is not worn, what is worn most, how wears are spread, what the closet is
made up of, and cost per wear for pieces with a price.

*Headed for:* one screen with What's missing.

## Trips

`/trips`, `/trips/new`, `/trips/<id>`. Plan a trip: where, the first and last day, the
occasion, and laundry on the trip. Closet shows the weather for the dates (the forecast
where it reaches, otherwise what those dates are usually like), what to pack with how many
days each piece is worn, basics, an outfit for each day, and "Why these counts". "Not this
one" swaps a piece and "I want to take this" insists on one. A saved trip is a packing list
to tick off, on the computer or the phone.

*Headed for:* reached from Today.

## Settings

`/settings`. A short page, shown all at once when the settings are in, in eight groups:

- **Your style**: what Claude reads about how you dress, as lines. The first three show, each
  with where it came from underneath ("Starting rule", "You said this on 12 Nov", "From a
  conversation yesterday", "Your answer today"), and "And 2 more lines." when there are more.
  **Talk to Claude about your style** opens the conversation in a sheet: with nothing said yet
  that day it asks one question the stylist can't tell from your clothes (whether you run warm,
  what you wear for work, colours you never wear, how dressed-up you like weekends, how you
  like things to fit, anything you never wear), answered with a tap, in your own words, or
  skipped, each with Undo, and never asked twice. Anything you write gets a short answer, and
  Claude may offer a line to keep: it goes into Your style only when you tap **Save to Your
  style**, and Undo takes it out again. When Claude can't be reached, or in the demo closet,
  the sheet says so and the box is closed. **See all lines** (or **Change the lines**) opens
  every line, each with **Change** and **Remove** (with Undo), and **Add a line** at the end.
  **Edit the text** opens the whole of it as one text in a sheet. Then the switch **Let Claude
  choose my outfits**. Lines kept from the conversation on Today are added to it too.
- **Everyday**: "Weather for New York" with **Change**, which opens the place search, Use my
  location, today's weather and what is sent where (the weather is only looked up then); How
  you live with **Edit my answers**; the laundry switch and laundry day, and **Wears between
  washes** folded under them.
- **Claude**: one line saying how Closet reaches Claude ("Using your Claude plan"), or one red
  sentence and Check again when it can't; **Manage** opens Advanced.
- **Updates**: one line ("Closet 0.9.0 · up to date", or "Closet 0.9.1 is ready to install."
  with what is new folded under it and **Install now**).
- **Phone**: on the computer only. Until Tailscale shares Closet, the command to run once;
  after that one line with the address and **Show the QR code** folded under it. While Settings
  is open and the phone is not connected, it checks again every few seconds (every half
  minute when Tailscale is not installed). On the phone in Safari, one line on adding Closet to
  the Home Screen; nothing once it is opened from there.
- **This device**: light, dark or the same as the device, kept on this device.
- **Your data**: one line on the backups (where they go and the last good one), or that there
  are none yet, with **Choose a backup folder** on the computer.
- **Advanced settings** (a link), then Log out, and Quit Closet on the computer only.

## Advanced settings

`/settings/advanced`, from the foot of Settings or Manage beside Claude; "‹ Settings" goes
back. Its code loads only when it is opened. In order:

- **Your closet**: the demo closet switch, and Start Closet when I log in (computer only).
- **Claude**: the plan and the API key in the order they are tried, each with its state; the
  key box (paste, replace, remove); which to use; Allow the API key; the monthly limit and the
  month's spending, folded; how many items wait to be described, only when some do.
- **Updates**: the version, when it last checked, whether to install by itself, ask first or
  never check, Check now, and how the last install went.
- **Backups**: the backup line, the folder (typed on the computer only) and Back up now.
- **Storage**: one line ("Closet uses 2.9 MB for 49 items · 59 GB free on this disk"), with
  what takes the space folded under it.
- **Background removal**: the download address, and on the computer where to put the files
  by hand, folded.
- **This copy of Closet**: the data folder (computer only) and the version.

## Things that work the same everywhere

- **Saving.** Changes save as you make them; a toast says so or says what went wrong. A save
  still waiting when the page closes is sent as it closes.
- **Offline.** On a phone that cannot reach the computer, the saved closet, trips and
  suggestions are shown and nothing can be changed or added until it is back.
- **The demo closet.** About 50 sample pieces in a closet of its own, opened and left from
  Advanced settings, with a strip at the top while it is open. It is never backed up and never sent
  to Claude.
- **Background removal.** The two files that cut clothes out of photos download by
  themselves when Closet starts, and again after a failure (a minute later, ten minutes
  later, then every hour). A notice on the closet says when they are missing or failed.
- **When a screen fails.** It says so, with Try again and Reload Closet, and the tab bar
  stays so you can go elsewhere.
- **Work in the background.** Cutting out, describing, measuring a pattern and drawing a
  shoe carry on with the page closed and are picked up again after a restart. Add, the
  closet's tiles and the item page each say what is happening in their own words today
  (*headed for:* one progress line and one set of words).
- **Claude.** Describing, sorting photos, corrections in your words, the stylist and shop
  searches go through your Claude plan or your API key, in the order chosen in Advanced
  settings. The key has a monthly limit; when it is reached, pieces wait and the page says so.
