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
- [Settings](#settings) · [Things that work the same everywhere](#things-that-work-the-same-everywhere)

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
only when you tap it. In the evening, or the next day, Today asks how the outfit went.
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
switch between Photos and Drawings. A tile shows the piece's picture and name, and says when
its background is still being removed or could not be. Notes at the top say how many pieces
need a quick check and how many are in the laundry. On a computer, choosing a piece opens it
in a panel beside the grid; on a phone it opens as its own page.

## An item

`/item/<id>`. The picture (photo, cutout or drawing, and for some pieces the back), the name,
and "Wearing and washing": Wore it today, put in the laundry or mark clean, and recent wears.
Then Details as rows of a label and a value; tapping a row opens its choices (a sheet on a
phone). "What is it?" changes the kind, and the last row is how you feel about it, with an
optional why. "Fix the details", under the picture, opens a sheet over the page (on
a computer, a box under the picture) with the drawing and a box, "What's wrong with it?":
Claude reads your sentence, says what it understood, and nothing changes until you choose
Make these changes. "Change the details one by one" shows every detail the drawing is made
from, by group, in the same sheet. In the demo closet, or when Claude could not be reached,
it opens on the details one by one and says why. Three folds follow, closed until opened: More details (How
I wear it, fit notes, notes, brand, size, material, date acquired), What Claude saw (its
description, what was seen but is not drawn yet, and Describe it again) and History (every
change, each of which can be undone). Archive and Delete are at the bottom; a new photo can
be taken in place of the old one, and a cutout that failed can be tried again.

A shoe also shows its photos sorted into views, its traced side drawing with its own fixes,
and the drawing Claude makes for the figure, which takes several minutes and can be
corrected with a note.

While a piece is being cut out, described, measured or drawn, notices on the page say so.

*Headed for:* one description of the piece's look from one source; one rating and one notes
box (assessment, step 7).

## Add

`/add`. One place for everything. Take photos with the camera on the page, choose them from
the library, choose a folder, or drop them on the page. Closet asks Claude what each photo
shows (one piece, several pieces, or a view of a shoe) and sorts them; a shoe's photos are
gathered into one shoe. Photos are made smaller in the browser and sent two at a time; a
list shows each one's progress and what it became, can be paused, retried and cleared, and
survives closing the tab. The same photo is not added twice. After that the piece is cut
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

`/settings`. One column of groups, all open:

- **Your closet**: the demo closet switch, start with the computer, laundry (worn clothes go to
  the laundry by themselves, and laundry day), how many wears each kind of clothing takes
  before washing, backups (a folder on the computer, the last good backup, Back up now) and
  storage.
- **Where you are**: the place the weather is for.
- **How you live**: the questions What's missing uses.
- **Look**: light, dark or the same as the device, kept on this device.
- **Your style**: whether Claude chooses your outfits, and your style in your own words,
  which Claude reads every time. Lines kept from the conversation on Today are added to it.
- **Describing clothes**: how Claude is reached (your Claude plan, an API key, and which is
  tried first), the key itself, and the key's monthly limit and spending.
- **Updates**: the version, when it last checked, whether to install by itself, ask first or
  never check, Check now, what is new in a release (folded until you open it), and Install.
- **Phone access**: on the computer, the address to open on the iPhone and its QR code,
  once Tailscale is sharing Closet. On the phone, one line on adding Closet to the Home
  Screen, and nothing when it is opened from there.
- **Advanced** (closed until opened): where the background-removal files come from and
  where to put them by hand, the data folder, the version.
- Log out, and Quit Closet.

*Headed for:* seven short groups with an Advanced screen, shown all at once (assessment,
"Proposed Settings").

## Things that work the same everywhere

- **Saving.** Changes save as you make them; a toast says so or says what went wrong. A save
  still waiting when the page closes is sent as it closes.
- **Offline.** On a phone that cannot reach the computer, the saved closet, trips and
  suggestions are shown and nothing can be changed or added until it is back.
- **The demo closet.** About 40 sample pieces in a closet of its own, opened and left from
  Settings, with a strip at the top while it is open. It is never backed up and never sent
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
  searches go through your Claude plan or your API key, in the order chosen in Settings. The
  key has a monthly limit; when it is reached, pieces wait and the page says so.
