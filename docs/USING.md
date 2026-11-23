# What each screen does

A paragraph per screen, saying what it does today and what it already says, so a change has
one place to check before it adds a second copy. Installing, the iPhone, backups and the rest
of what the owner does outside the screens are in the [README](../README.md). Why a screen is
the way it is, is in [DECISIONS.md](DECISIONS.md).

Keep this short and true: when a screen's behavior changes, change its paragraph in the same
pull request. It describes the app as it is, not as the assessment wants it; where the two
differ, the last line of a section says where the screen is headed.

- Getting around: [The four places](#the-four-places) · [First run and the ways in](#first-run-and-the-ways-in)
- **Today**: [Today](#today) · [Worn](#worn) · [Trips](#trips)
- **Closet**: [Closet](#closet) · [An item](#an-item) · [Review](#review)
- **Add**: [Add](#add) · [Several pieces in one photo](#several-pieces-in-one-photo)
- **Wardrobe**: [Wardrobe](#wardrobe) · [Wishlist](#wishlist) · [A wish](#a-wish) · [Add a link](#add-a-link) · [Would this work?](#would-this-work)
- **Settings**: [Settings](#settings) · [Advanced settings](#advanced-settings)
- [Things that work the same everywhere](#things-that-work-the-same-everywhere)

## The four places

On a phone the bar at the bottom has the four places and Add: Today, Closet, Add (the round
button in the middle), Wardrobe and Settings. On a computer the sidebar starts with the app's
name, Nines, beside its mark (the empty dinner jacket of the icon), then Add clothes, then
Today, Closet and Wardrobe, with Settings at the foot. Everything else is one level down in the place it belongs to, and that place stays lit there: Worn and Trips in
Today, the review and Archived in the closet, Would this work?, the wishlist and a wish in the
Wardrobe, Advanced in Settings. While anything waits to be checked, Closet carries a dot (on a phone) or
the number (on a computer).

The app opens on Today once the closet has enough clothes to dress from, and on the closet
before that. A back link ("‹ Today", "‹ Closet", "‹ Wardrobe", "‹ Wishlist") goes back to the
page you came from, where you left it; on a page opened straight from its address it opens the
page it names. Back and Forward bring a page back to where you had scrolled it. The addresses of
the places that were merged (`/missing`, `/missing/check`, `/missing/item/<id>`, `/insights`,
and `/worn`, `/would-work`, `/wishlist`) open the page that holds them now and take its
address. Routes are in `frontend/src/router.tsx`, the places and the moved addresses in
`frontend/src/places.ts`.

## First run and the ways in

There is no passphrase: the first launch opens straight on the empty closet, which offers to
add a first item or to look around the demo closet. Who may come in is decided by the way in
(README, "Who can open your closet"). While Nines opens, the mark, the empty dinner jacket of
the icon, shows over "Opening your closet…". If the computer cannot be reached, a screen says so ("Nines isn't answering") and keeps trying; on a phone that has been used before, the saved closet is
shown with an offline banner and nothing can be changed.

On the computer, Nines opens from its icon: its window, or the browser it opens, comes in
with the window's key and nothing else is asked. The address typed into a
browser, or an old bookmark to it, shows only a page titled "Open Nines from its icon" (any
other address that leads to Nines says "Nines is not at this address"). A page left open
from before an update that tries to save says "This page is from an older Nines. Reload the
page, then try again." At the Cloudflare address (README, "Use it without Tailscale, through
Cloudflare"), Cloudflare asks for its emailed code first; a visit that reaches Nines without
Cloudflare's sign-in shows "Sign in through Cloudflare first". Through Tailscale, a visit that
Tailscale does not say who is making shows "Nines could not tell who you are" (be signed in to
your Tailscale; if you are, check on the computer that Tailscale is set up there), and
Tailscale's public Funnel shows "Nines is not on the open internet". These come from the server
(`backend/closet/gate.py`), not the page. A page already open, or kept on the device for offline, that the
server then turns away shows "Nines didn't let this device in" with the server's sentence and
**Reload**. When Cloudflare's sign-in runs out while the page is
open there, the page loads itself again in full so Cloudflare can ask for a new code, at most
once every two minutes (`frontend/src/signin.ts`); on the computer and through Tailscale,
losing the connection shows the offline banner as before.

## Today

`/today`. The day's weather for the place saved in Settings, an occasion and a mood to
choose, and outfits to swipe through (or reach by the dots under them), each drawn as worn (or
laid out as pieces, four to a row on a phone) with "I'm wearing this" under it, then "Why this
works", which starts with who chose it and, for Claude's, its reading of the day, and, when
there is something to watch for, "Be aware". On the smallest iPhone the first screen holds an
outfit of five pieces and its button. As worn, a jacket or coat that opens is drawn open, and what you wear
under it that buttons or zips (a cardigan, a zip hoodie, a knit vest, a blazer) is drawn
fastened, its front showing between the coat's; a shirt worn open over a tee stays open inside
the coat's fronts. The rules choose outfits at once; when Claude may choose,
the outfits on the page stay there, dimmed, under a card saying Claude is choosing, until its
outfits replace them ("Show Nines' own picks meanwhile" lets you use the rules' outfits). "I'm
wearing this" records the outfit and its wears, and ends building around a piece. A piece's ⋯
opens a sheet with "Not this piece", which swaps it out, and "Build around this piece"; both
are kept for the rest of the day, and how is said once, under the outfits, behind "Changing an
outfit". When the weather cannot be fetched, one line says "No forecast.", with Try again
and Type temperatures. Change, beside the weather, opens a sheet, Where you are, with today's
temperatures and "Somewhere else, or out all day?" folded under them: a note about the day
("In Lisbon until Friday") changes what is dressed for. Under the outfits you can write to
Claude about them; it answers, may change the outfits, and may offer something to remember,
which is kept only when you tap it, with Undo beside it once kept.

Below that, when a trip starts within two weeks (or is under way), a "Packing for a trip?"
row opens it. Then Recent outfits: in the evening, or the next day, it asks first how the
outfit went, with every piece of it under the question; then the last outfits you wore (three
on a phone, a week's worth on a computer), each with its pieces and how it went, rated in place,
saying "Saving…" and "Saved" as it saves; the reasons offered follow the rating. "See all" opens
Worn. The page ends with a link to Trips. Tapping a
piece opens it (`/today/item/<id>`).

Temperatures can be typed when the forecast cannot be fetched. The demo closet's outfits are
the rules' alone; nothing about it is sent to Claude. A piece away (at the cleaner's, at the tailor's, lent out) is
not offered, and building around it says where it is ("at the cleaner's until Friday 27 November").
Swim trunks (and what you wear at home)
are never in the day's outfits, by the rules or by Claude, unless you build an outfit around
them or wear again an outfit they were in; a trip packs them for swimming. Shoes made for one sport (tennis shoes, golf shoes and
studded boots) are left out in the same way, even on an athletic day; when nothing made for
sport is clean, an athletic day's outfit says which pieces are a makeshift.

## Worn

`/today/worn`, from "See all" under Recent outfits; "‹ Today" goes back. The outfits you
wore, newest first, each with its pieces, how it went (a rating and a note), and, behind ⋯ in
a sheet, "Wear this again" (Today keeps the pieces you can wear today, and fills the place of one
in the wash or waiting to be mended), a way to put its pieces in the laundry, and Remove. A piece
opens at `/today/worn/item/<id>`, and "‹ Worn" goes back to where you were. "Record an outfit"
opens a sheet with the day (today or an earlier day), a search, and your pieces in four groups
(tops, bottoms, shoes and extras), the ones worn most recently first; a tie, a watch or anything
else of category Other is among the extras and goes with the outfit's accessories. Choose two or
more and record them; a piece away that you record for today is back in your closet, and the
message says so. A day your phone calls today is taken even when the computer at home is a
time zone behind. An outfit for a day the pieces have been washed since (before the last laundry
day, or before you marked them clean) goes in the log but does not put them in the laundry again.

## Trips

`/trips`, `/trips/new`, `/trips/<id>`, from the link at the foot of Today or its trip row;
"‹ Today" goes back from the list. Plan a trip: where, the first and last day, the
occasion, laundry on the trip, **Swimming or the beach**, and **Playing on the trip** (Tennis, Golf).
Nines shows the weather for the
dates (the forecast where it reaches, otherwise what those dates are usually like), what to
pack with how many days each piece is worn, basics, an outfit for each day, and "Why these
counts". "Not this one" swaps a piece and "I want to take this" insists on one. Swimming or
the beach turns on by itself when a day of the trip reaches 27°C; you can turn it on or off,
and your choice is kept when the trip is planned again, until you tap "Follow the forecast
again". While it is on, your swim trunks are
packed under **For swimming**, one pair for a trip of up to a week and two for a longer one,
never worn in a day's outfit; with none in your closet the trip says so there. Choosing Tennis
or Golf packs one pair of your tennis or golf shoes with the shoes, worn on no day; with none
that can go, the trip says so. Shoes for a sport and what you wear at home (lounge pants, a robe)
are otherwise packed only when you choose "I want to take this", beside the days, and are worn
on no day. A piece away is packed only when you expect it back before the first day, and the trip
then says it counts on it being back. What to pack comes first, under the weather: the days with something to watch for are
one line that opens, and a forecast that could not be had is said once. A packed piece's ⋯ opens
a sheet with "Not this one" and "See it". Each day's outfit shows up to five pieces in a row. A
saved trip is a packing list to tick off, on the computer or the phone, with its choices under
"Change the trip". What you have ticked stays on the list when the trip is planned again, and can
be worn whatever the laundry at home says. Once the trip has begun, the days already gone keep
their outfits and their weather, the days to come are dressed only from what you packed, and the
trip says the forecast changed only when it changed for the days still to come.

## Closet

`/` (and `/archived`). A grid of your clothes with search, one Filter button (what it is, laundry and away,
and In use or Archived) whose choices stay visible as chips; **What it is** lists the groups your pieces are
in, and the one you choose opens to what is in it (Jeans, Trousers, Shorts, then the kinds), and a
switch between Photos and Drawings. The switch starts from Settings' **Show drawings instead of
photos** each time Nines is opened, and changing it shows the other kind in the grid only, until
then. One line over the grid says what wants seeing to: "5 to
check · 4 in the laundry" (to check: the pieces added and not checked yet, and those with a
detail Claude was unsure of). Each part shows only those pieces, as a chip that removes
itself: "Needs a check" then offers "Check them one at a time" (the review), and "In the
laundry" offers "All clean", each in a line under the search. After "All clean" that line says how
many you marked clean, with **Undo**, which puts each piece back in the laundry as it was; the
grid then says "Your laundry is empty." When pieces are away (at the cleaner's, at the tailor's, lent out), the
line says how many, and how many are past the day you expected them back ("2 away, 1 expected
back"); on a phone that part has a line of its own under the others. It shows those pieces as a
list, soonest back first, each saying where it is and when it is expected ("Expected back on Friday
20 Nov" once the day has gone by), with **It's back** beside it; a piece brought back stays in the
list with Undo until you leave it. A piece in the laundry while it is away is counted as away, not
in the laundry. A tile shows the piece's picture and name, and, while
Nines is working on it, a small round mark with the step it is at (1 cutting out, 2
describing and drawing, 3 finishing the drawing): turning while it is being done, dashed while
it waits, a warning sign when a step failed. A piece away has a small round mark in the other
corner. While anything is being worked on, one line,
"Working on 3 items", floats above the grid and the tab bar; tapping it lists those pieces,
each with what is happening to it, and says once why they wait when it is something you can
see to in Settings. On a computer, choosing a piece opens it in a panel beside the grid; the grid keeps
as many pieces to a row and the piece stays where it was, and **Close**, Escape or Back closes the
panel. On a phone it opens as its own page.

## An item

`/item/<id>`. It reads in the order you go through a new piece. First the picture (photo, cutout
or drawing, and for some pieces the back), with a small mark on the drawing that lists what it
leaves out, and the name, which you type over in place. Straight under the name: **What is it?**
(the kind, with who said it, a sheet of kinds on a phone; for a shoe, the kind of shoe set in
Fix the details counts too), the brand and the price, each saved as you leave it. Changing any of these counts as having checked the piece, so it leaves the review.

Then "Wearing and washing": Wore it today, put in the laundry or mark clean, where the piece is,
and recent wears. Where it is is one sentence ("In your closet", "At the cleaner's until Friday 27
Nov", "Lent out since 3 Nov") with your note under it; **Change** opens a sheet with In your closet,
At the cleaner's, At the tailor's and Lent out, the day you expect it back and a short note (it stays
on your computer and is never sent to Claude). While it is away the row's button is **It's back**:
back from the cleaner's it is marked clean, back from the tailor's it is no longer marked as needing
mending, and back from being lent nothing else changes. The row then says what coming back did, with
Undo, for the rest of the day. A piece marked as needing mending reads "In your closet, waiting to be
mended", with **Take it to the tailor's**. Wearing an away piece today (Wore it today, or an outfit
recorded for today) brings it back, and undoing that wear sends it away again. The History fold says
when it went and came back.
About it holds how you feel about it and one box, Notes for you and Claude, which Claude reads
when it chooses your outfits; it shows every note kept about the piece, and once you change it
the whole text is kept there.

Then how it looks. One line says what the piece is, its colour and how it sits ("Polo · Navy ·
Regular fit · Short sleeves"). It is read from the same description the drawing is made from,
with your corrections over it, so it never says something the drawing does not show; each word
of how it sits opens its detail to fix. "Something wrong? Tell Claude" opens Fix the details: a
sheet over the page (on a computer, a box under the button) with the drawing and a box, "What's
wrong with it?". Claude reads your sentence, says what it understood, and nothing changes until
you choose Make these changes. "Change the details one by one" shows every detail the drawing is
made from, by group, marked when you set it, with when Claude described the piece (a pair of
trousers' cuffs, turned up, rolled or ribbed, are under Hem and cuffs). Under the box, "Add to
the drawing" takes one line for what no detail shows (a patch, a panel, a tab, a line of
stitching): Claude draws it onto the drawing as it is, keeping the rest, and checks it against
the photo, in a minute or two, while you can close the sheet; the picture's strip says it is
being done. What Claude added shows on the closet picture and on the outfit figure, moving with
the garment. The sheet then lists what was added, how long it took and what it cost, with "Go
back to the drawing before" (and then "Go to the newer drawing") and "Take Claude's additions
off"; it says so when a detail changed the shape under them since. When Claude can't turn a
sentence in the box into a detail, "Have Claude draw it onto the drawing instead" moves it to
the line for you to send. Shoes don't have it: their drawing by Claude has its own note. In the
demo closet, or when Claude could not be reached, the button says "Something wrong? Change the
details" and the sheet opens on the details one by one, saying why.

Folds follow, closed until opened: Details (colour, pattern, where it lives, formality, season,
each a row that opens its choices, a sheet on a phone), Size, material and more (size, material,
date acquired, condition), then a shoe's photos, then History (every change, each of which can
be undone), and the last one, with Describe it again, Archive and Delete. A new photo can be
taken in place of the old one, and a cutout that failed can be tried again. Formality can be
one level or two next to each other, for a piece that could be either: under the levels, "It
can also be" offers the level below and the level above the one chosen, and the row then reads
"Smart casual to business". Choosing a level makes it one level again. Claude may give two
levels when it describes a photo; a formality you chose is never changed by describing it again.

The colour's choices end with the shades of the piece's colour, each with its swatch ("Shades of
green": Sage, Mint, Forest green, Hunter green, Teal). Choosing a colour keeps the choices open on its
shades; choosing a shade saves it with its colour and draws the piece in it. A shade you choose
stays yours when Claude describes the piece again, and choosing another colour puts it aside. It
is chosen only there: Fix the details does not list it.

A shoe also shows its photos sorted into views, near the end of the page. Once they are sorted,
the photo of the outer side is its photo in the closet, so the photo and the side drawing show
the same side (the inner side when no photo shows the outer one). When Claude could not tell the
outside from the inside, the photos ask which one shows the outside; at any other time, "Change
which photo shows the outside" under them puts right a swap Claude was sure of. Under "How it
looks", "Drawn by Claude from its photos" holds
the two drawings Claude makes from them: the shoe from the side, which is its picture in the
closet when it shows drawings, with a line on what makes it itself, and the drawing for the figure. Both are made
together, in several minutes. Either can be corrected with a one-line note: once there is a
side drawing, you choose whether the note is about the front or the side (the front unless you
choose), Claude changes only that drawing, and the line on what changed sits under it. Go back
to the drawing before undoes either kind of change. Until Claude's side drawing exists, or when
it cannot be made, the picture is traced from the side photo, with its own fixes in Fix the
details; once it exists, Fix the details offers only the plain drawing, and says how to correct
the side instead. Two shoes are drawn at the same time; a third waits for one of them. A shoe
drawn before gets its side drawn by itself, in the background.

While Nines is working on a piece, one strip over the bottom of its picture says how far it
has got: three dots for the three steps (cutting out, on the computer; describing and drawing,
by Claude, after which the drawing appears at once; and, for patterned clothes and shoes,
finishing the drawing: measuring the pattern, or sorting a shoe's photos, tracing it and
Claude drawing it), what is happening now, and where it runs and how long it takes, or what it
waits for (with Open Settings when that is where to see to it). The strip goes when the work
is done, and nothing on the page moves when it comes or goes. A cutout or a description that
failed says so under the picture, with Try again. A shoe's photos and its drawing for the
figure say the same words while their part is under way.

## Review

`/review`, from "Check them one at a time" when the closet shows the pieces that need a
check, or on Add once a piece just added has been described; "‹ Closet" goes back. Every piece
you add comes here once, new pieces first, and so does any piece with a detail Claude was unsure
of. One piece at a time: its picture, its name to type over, **What is it?** (Claude's guess,
with how sure it was, to change in a sheet), the brand and the price, and under them the details
Claude was unsure of, its guess chosen. "That's right" (or Enter in a box) saves it all at once,
makes what it is your word, and moves to the next; "Skip for now" leaves it for next time. A
price that is not a price is said and nothing is saved. On a computer with a mouse it also says
which keys do the same; on a phone it does not. Pieces kept before 22 November count as checked.

## Add

`/add`. One place for everything. When the files that cut clothes out of photos are not set
up, or did not download, a notice at the top says so (only here: new photos keep their
background until they are in). Take photos with the camera on the page, choose them from
the library, choose a folder, or drop them on the page. JPEG, PNG, WebP, HEIC and AVIF photos
all work, so a photo saved from a shop's page goes in too. Nines asks Claude what each photo
shows (one piece, several pieces, or a view of a shoe) and sorts them; a shoe's photos are
gathered into one shoe. Photos are made smaller in the browser and sent two at a time; a
list shows each one's upload until it is in, then, in the same row, how far Nines has got
with the piece (with the step's mark) and, once described, what Claude called it; it can be
paused, retried and cleared, and survives closing the tab. Why pieces wait, when it is
something you can see to in Settings, is said once above the rows. The same photo is not added twice. After that the piece is cut
out, described and drawn in the background; you do not have to wait on this screen. Once the
uploads are done and a piece has been described, "Check them one at a time" leads to the review,
to say what each is and give its name, brand and price.

## Several pieces in one photo

`/add/several/<id>`. For a photo of pieces laid out together: Claude draws a box round each
piece, you move, add, join or remove boxes (or draw them yourself), and each box becomes an
item of its own. After each change a line says what it was, with **Undo** (it goes back
through the changes one at a time). A box of Claude's you moved, reshaped or joined has **As
Claude found it**; one you removed is listed under the pieces with **Put back**; and **Back to
what Claude found** puts every box back as Claude found it, dropping boxes you drew. These
appear only once something differs from Claude's answer, and stay after the page is opened
again (Undo does not), until the pieces are added.

## Wardrobe

`/wardrobe`. What to buy and how your clothes are used, on one page. **Worth buying**: what
the closet lacks, found by rule from the clothes, the wears, where you live and how you live,
the three most helpful first and "See all N" for the rest. Each is a closed card: its name, how
much it helps ("Helps a lot") and one line of why. A tap anywhere on its head opens it in place
(nothing above it moves) to every reason (one sentence, then "Why, day by day"), what to look
for with its colours, your pieces it is based on, "Search Google Shopping" (opens Google Shopping
in your browser, searching for "men's", the first colour and the kind of piece, nothing else),
"I'll look for this" and "Not for me" (hide it, and optionally similar ones). "I'll look for
this" puts it on the wishlist and leaves the card where it is, saying "On your wishlist" with
**Undo** (closed, the card says "On your wishlist" instead of its line of why). "Based on…" opens
How you live, the same questions as Settings; once the closet has enough to suggest from and they
are not answered, "Tell it how you live · 1 minute" offers them, with Not now. What holds
suggestions back, the days you ruled out and what you hid are folded at the end of the section.
Swim trunks, shoes made for one sport (tennis, golf, studded boots) and what you wear at home
(pyjamas, lounge pants, robes) are not counted there: a pair of tennis shoes never stands in for
everyday sneakers, nor lounge pants for trousers. **You might like**: three things Claude found on sale from what you wear and love,
not from a gap, each with the shop's picture (a hanger until there is one), its name (which
opens the shop's page in your browser), the shop and price, one line from the closet ("Goes
with 6 of your pieces."), **Save** (onto the wishlist, with the product as its first find, so
its price is checked once a day), **More like this** (a look for more like it, which joins
the card) and **×**, Not for me (gone for good, with Undo in its place; after three alike,
such as three bright colours, it may offer a line for Your style, kept only when you tap Save
to Your style, with Undo). The newest three show, older ones behind "See earlier ones". Before
the first look it says what it does, with **Look now** (and what a look costs through the API
key, when that is on); with too little to go on it says to wear and rate a few more pieces
and does not search; the demo closet never searches. **How Nines looks**, folded, says what a
look sends and holds **Look for me each week**, on once you have tapped Look now, off before:
then Nines looks by itself once a week while it is running. Nothing it shows is a product Claude
made up; a week with nothing new says so. The card has two views, **For you** and **On sale**
(remembered on this device), each with its own three, its own Look now and its own sentence for
each state. **On sale** shows things marked down now: Claude starts from the shops you like
(Settings), the brands you wear and rate well, shops you have found things at before, then
smaller makers you may not know, and Nines opens each shop's page itself before showing it (the
price is the page's; a sale that ended, a sold-out product or less than 15% off is left out).
A sale row says its shop, then its prices in the wishlist's words ("Was $120.00, now $84.00 (30%
less)"), the line from the closet, and "Your size is in stock." when the page says so, or
"Claude read the earlier price from the page." when only Claude did. Save keeps the earlier price
on the wish, so its page shows the drop. Before the first look, with no shops named, it offers
"Name a few shops you like and Nines starts there.", which opens Shops you like in Settings.
**Look for me each week** covers both: once you have looked for sales, Nines looks once a week
for them too, on another day than the other look, and reads each sale's page again once a day; a
sale that ended leaves the card. **Thinking of buying something?** (beside the rest on a computer): Would this work?,
and a **Wishlist** row that opens the wishlist, saying how many things are on it ("3 things", or
"Nothing on it yet") and, when prices went down, how many ("2 prices went down"). **Your nines**: the
nine pieces you wore most over the last 30 days, 90 days or all time (it opens on the first with
nine), as a square of three by three of their pictures (photos or drawings, as Settings says),
each with how many times you wore it and opening the piece. Everything you wore counts, lounge
pants and tennis shoes too. With fewer than nine it shows those and says how many; with nothing
recorded it says so. **Not worn**: pieces never worn, each to Archive or Keep, under one sentence
that says how many and since when; pieces not worn for a long time in their season are listed
under it only when there are some (never swim trunks, sport shoes or what you wear at home; after
months with nothing recorded it says so instead of listing everything). Then one line on what
your clothes cost you: what you spent this year and on how many pieces, from each piece's price
and date bought, once at least three pieces have both; until then how many pieces have no price
yet (or a price and no date bought), with a link to the piece you wear most, where both are
filled in. **More numbers**, folded: how wears are spread in each kind of clothing, what the
closet is made of, and **What your clothes cost you**: what you spent each year, the closet's cost
per wear, the pieces that have earned their price (worn three times or more, the least per wear
first) and those that have not yet (a price and fewer than three wears), and what the wishlist
would cost at today's prices, said separately for each currency when shops price in more than
one. A piece opens in the Wardrobe
(`/wardrobe/item/<id>`; beside the page on a computer), with "‹ Wardrobe". Offline, it shows
what it last found, marked as saved earlier.

## Wishlist

`/wardrobe/wishlist`, from the Wishlist row on the Wardrobe or the price banner's "See them";
"‹ Wardrobe" goes back. "Add a link" (a product's page: a new wish made from it, then its page
opens) and "Add by hand" (what you are looking for, and a note), then a row per wish that opens
its page. A row shows the note, what to look for, or the page it was sent as ("$68.00 at Example
Shop"), and "Down from $68.00 to $54.40" when a price went down, with "That's within your price."
when it is no more than the most you'd pay. With nothing on it: "Your wishlist is empty", "Things
you'd like to buy wait here, and Nines tells you when their price goes down.", and "See what's
worth buying", which opens the Wardrobe. It shows once the wishes are in, without waiting for what
is worth buying. Offline, it shows the copy saved on this device, marked as saved earlier, and
nothing can be added.

## A wish

`/wardrobe/wish/<id>`, from its row on the wishlist; "‹ Wishlist" goes back. Top to bottom: what to
look for (or "Added by hand"); what is watched, the pages you sent first ("You sent this link", and
"Claude read its price from the page" when it did), then what Claude found, each checked against the
closet (a page you sent too, once Claude has described it from the page's words: its verdict, what it
goes with, what it repeats and what gap it would fill, with the shop's picture; until then one sentence
says why it is not checked, such as "Nines checks it against your closet once Claude can describe
it."), with "See it with your clothes" on a judged find that an outfit can be made with (a sheet over the
page with up to three outfits of your own pieces and the find, each drawn as worn, to step or swipe through; the
shop's picture beside the drawing; the names of your pieces, each opening the piece; and one line saying the find is
drawn from the shop's description, so it shows roughly its shape and colour, not how it really looks, or its shape,
colour and pattern when it is striped or plaid, which is drawn as a plain, typical stripe or plaid; nothing is sent
to Claude), "Open in shop", "Stop watching" (it goes, and with it its daily check) and, when its
price changed from one day to another, "The price was … on 3 Nov and … yesterday.". A find with a
code at checkout says the price after it under its price ("$106.20 with code TEST40 at checkout (40%
off)") and who saw it ("Nines saw this code on the page." or "Claude saw this code on the page.";
nothing when you typed it); **Add a code** (or "Change the code") opens a sheet with the code and
either "% off" or an amount off, Save, "Remove the code" and Cancel. The price after the code is what
the drop, the banner, the wishlist row and "within your price" count; a code read from the page goes
when the page stops showing it, and one you typed stays until you remove it. Under the finds one
sentence, "Nines checks the price once a day while it's running and tells you when it goes down."
(with a price, "…when it goes down to $150.00 or less."), with "Set the most you'd pay" or
"Change", then when it was last checked and "Check now" (the pages you sent read by Nines, the rest
by Claude, and a page you sent that is not described yet described by Claude). Then looking for
more: "Find some" or "Find more" (Claude searches shops; under them, "A search sends Claude the
wish, your style, what you tend to wear, the brands you own and your size, never a photo or a
note.", except in the demo closet) and "Add a link" (a product's page added as
a find: Nines reads its name and price from the page, asks Claude only when the page gives no price,
then asks Claude once to describe it from what the page says), and "Search Google Shopping" (as on
Worth buying, from what to look for, or the wish's name when it has none); with nothing watched yet, the price is offered here
("Claude looks at any price." or "Claude looks for ones up to $150.00."). Then the note (saved when
you leave the box or tap Save note, saying "Saving…", "Saved" or "Didn't save" with Try again), and
"Would it go with my clothes?" (Would this work? for this wish; for a page you sent it starts with
the product's name), "I bought it" (it leaves the list and Add opens) and "Remove from the list"
(back to the wishlist). **The most you'd pay** opens in a sheet: one amount and its currency, with
Save, Clear and Cancel; Nines tells you when a price goes down to it or less, and Claude's searches
stay under it. A wish that still has a lowest price from
before says so until it is changed. While a page is read the wish says who is reading it ("Claude
is describing it…" while Claude describes a page you sent). Opening
the page counts as seeing its price news. Like the wishlist, it waits only for the wishes.

## Add a link

`/wardrobe/link?url=<a product's page>` (or `text=` or `title=`, whichever holds the link),
which the share sheet opens on Android and in Chrome on a computer, and an iPhone Shortcut
opens (README). "‹ Wishlist" goes to the wishlist. The wishlist's "Add a link" box, filled in with
the link; nothing is added until you tap "Add to the list", which makes the wish and opens its page.
When what was shared holds no link, it says so and the box is empty.

## Would this work?

`/wardrobe/check` (and `/wardrobe/check/wish/<id>` from a wish), from the Wardrobe;
"‹ Wardrobe" goes back. A piece you might buy, from a photo or described by hand, checked
against the closet by rule: what it goes with, what it repeats, what it would fill, what
would hold it back, when you would wear it, and example outfits. The example outfits have the
**Pieces / As worn** switch of Today and Trips (the same remembered choice): As worn draws each one
on the figure with the new piece among your own, its pieces named under it, and one line saying the
new piece is drawn from your description (or Claude's description of your photo), so it shows roughly
its shape and colour (and its pattern, when it is striped or plaid: a plain, typical one). Described by hand, its formality can be two levels next to each other, as on
the item page.

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
  you live with **Edit my answers**; the switch **Show drawings instead of photos**, kept on the
  computer so it holds on every device: the closet, Today, Worn, trips, the Wardrobe and an
  item's page then show a piece's drawing (a piece with no drawing yet shows its photo); the
  laundry switch and laundry day, and **Wears between washes** folded under them. Before the
  drawings switch, **Your sizes**: one line with the sizes saved ("Your sizes: M tops · 32x32
  trousers · 10.5 shoes", or "Your sizes are not saved yet.") and **Change**, which opens a sheet
  with a short box for Tops, Knitwear, Trousers and jeans, Jackets and coats, and Shoes, each saved
  as you leave it ("Saving…", "Saved" or "Didn't save" with Try again). Under an empty box, "The
  size on most of your tops is M." with **Use it**, when your own pieces of that kind say a size.
  **A brand that fits differently** opens a small form (the kind, the brand, your size in it, Save
  and Cancel); each brand kept shows under its kind ("In Example Brand, L") with **Remove**.
  "Find some" tells Claude the size for the wish's kind. After it, **Shops you like**: one line
  naming them ("Shops you like: Example Shop · shop.example", or that you have named none) and
  **Change**, which opens a sheet: a sentence saying Nines starts there when it looks for things on
  sale and tells Claude the names, each shop with **Remove**, and a box with **Add** (a pasted link
  keeps only its site), saved as you go ("Saving…", "Saved" or "Didn't save" with Try again, and
  Nines' sentence when it does not take one). Up to 12. The Wardrobe's On sale view opens it with
  `/settings?open=shops`.
- **Claude**: one line saying how Nines reaches Claude ("Using your Claude plan"), or one red
  sentence and Check again when it can't; **Manage** opens Advanced.
- **Updates**: one line ("Nines 0.9.0 · up to date", or "Nines 0.9.1 is ready to install."
  with what is new folded under it and **Install now**).
- **Other devices** (your phone, or another computer): on the computer. Until Tailscale shares
  Nines, the command to run once; after that one line with the address ("Your phone or another
  computer can open Nines at …") and **Show the QR code** folded under it. While Settings
  is open and the phone is not connected, it checks again every few seconds (every half
  minute when Tailscale is not installed). Under it, on the computer, **Without Tailscale,
  through Cloudflare** is folded: what an address through Cloudflare means, a link to the
  README's steps, the three boxes (your Cloudflare team, the Access application's audience tag,
  Nines' address on Cloudflare) and **Save**, with a sentence saying it is off until all three
  are filled in. Once they are, the fold is titled "Also through Cloudflare, at
  closet.example.com". A wrong value shows the server's sentence under the boxes. Between the two,
  on Windows in the downloaded program, **Keep Nines running**: one line saying whether Windows
  keeps Nines running, whether it starts when the computer turns on or when you sign in, and
  whether it is running now (or why turning it off did not work); while it is off, what it does
  in a few sentences, including that it replaces Start Nines when I log in and that updates then go to the
  copy Windows runs; "Nines answers on port
  N on this computer", and once it is on, that the port no longer changes; then **Keep Nines
  running**, or **Turn this off** (and **Start it again** when it is on but not running). Turning
  it on or off, Windows asks for permission on the computer's screen; turning it on, the window
  closes and opens again onto the copy Windows runs. Turning it off, when that copy had updated itself past
  your program, one sentence says your program is now that version (or, when it could not be replaced, to open
  Nines from Nines' own folder). On a Mac or run from source there is no such
  part. On the phone in Safari, one line on adding Nines to the Home Screen; on Windows, one
  sentence on whether the computer keeps Nines running, and that it is changed on the computer.
  Opened from the Home Screen, only that sentence, or nothing where it does not apply.
- **This device**: on a device that came in from outside, one sentence on how: "This device
  came in through Tailscale as you@example.com" or "…through Cloudflare, signed in as
  you@example.com". Then light, dark or the same as the device, kept on this device. Then a
  closed fold, **Saved copies on this device**: one sentence (this device keeps a copy of your
  closet to show when Nines can't be reached; forgetting it leaves the closet on the computer as
  it is) and **Forget saved copies**, which clears what the screens kept for offline and the
  saved answers and pictures, but not photos waiting to be sent. Not while offline.
- **Your data**: one line on the backups (where they go and the last good one), or that there
  are none yet, with **Choose a backup folder** on the computer.
- **Advanced settings** (a link), then Quit Nines on the computer only.

## Advanced settings

`/settings/advanced`, from the foot of Settings or Manage beside Claude; "‹ Settings" goes
back. Its code loads only when it is opened. In order:

- **Starting Nines**: Start Nines when I log in (computer only; the group is not there on a
  phone).
- **Claude**: the plan and the API key in the order they are tried, each with its state; the
  key box (paste, replace, remove); which to use; Allow the API key; the monthly limit and the
  month's spending, folded; how many items wait to be described, only when some do.
- **Updates**: the version, when it last checked, whether to install by itself, ask first or
  never check, Check now with what it found under it ("Nines 0.15.0 is out." and **Install
  now**, or "You have the latest version."), and how the last install went.
- **Backups**: the backup line, the folder (typed on the computer only) and Back up now.
- **Storage**: one line ("Nines uses 2.9 MB for 49 items · 59 GB free on this disk"), with
  what takes the space folded under it.
- **Background removal**: a line for each of the two models, saying what it is for (the main
  one cuts out every photo; the second is asked as well for stripes and checks) and how it
  stands: ready, downloading and how far, not downloaded yet, or didn't download and why.
  One that is missing or failed has Download or Try again beside it. Under them, the download
  address, and on the computer where to put the files by hand, folded.
- **This copy of Nines**: the data folder (computer only) and the version.
- **The demo closet**: the switch that shows the sample closet instead of yours, last because
  it is rarely wanted once your own clothes are in. While the demo closet shows, the strip at
  the top of every screen has Leave, so the way back is always in sight.

## Things that work the same everywhere

- **When Nines doesn't answer.** A screen whose read fails says what it couldn't load and why, in
  plain words: Nines on your computer can't be reached, or it answered with a fault. **Try again**
  asks once more. A screen that was already showing something keeps it, under one line saying it
  is from earlier; while the computer can't be reached at all, the offline banner says it once.
- **Dates.** Every date reads the same way: a day as "Thursday 12 Nov" (or "Thu 12 Nov" where room
  is short), a moment as "today at 14:05", "yesterday at 09:41" or "on 3 Nov at 08:00", a line in a
  list as "Today, 14:05", a date on its own as "3 Nov 2026". Times are on the 24-hour clock. The
  date picker's own words are your phone's.
- **Banners.** What is said at the top of every screen (price news, an update ready, what a restore
  did) holds still: when it arrives after a screen has opened, it shows from the next screen on.
- **Saving.** Changes save as you make them; a toast at the top of the screen says so or says what
  went wrong (one of each at a time), or,
  beside a rating or a wish's note, a line saying "Saving…", "Saved" or "Didn't save" with
  Try again. A save
  still waiting when the page closes is sent as it closes.
- **Offline.** On a phone that cannot reach the computer, the saved closet, trips and
  suggestions are shown and nothing can be changed or added until it is back.
- **Price news.** When a price on your wishlist goes down (to the most you'd pay or less, when you
  set one), a banner at the top of every screen says so once: "A tan rain coat is down to $150.00
  at Example Shop, from $177.00." with See it and Got it, or for several "Prices went down for 3
  things on your wishlist." with See them (the Wardrobe) and Got it. Opening the wish or Got it ends
  it, on every device. News that comes in while you read a screen shows from the next one, and the
  news last told on this device shows as the page opens. It is asked for when the page opens, every half hour and when you come back
  to it; never offline or in the demo closet. The update banner and the offline line sit beside it.
- **The demo closet.** About 50 sample pieces in a closet of its own, opened and left from
  Advanced settings, with a strip at the top while it is open. It is never backed up and never sent
  to Claude.
- **Background removal.** The two files that cut clothes out of photos download by
  themselves when Nines starts, and again after a failure (a minute later, ten minutes
  later, then every hour). A notice on Add says when they are missing or failed, and
  Advanced settings shows how each one stands.
- **When a screen fails.** It says so, with Try again and Reload Nines, and the tab bar
  stays so you can go elsewhere.
- **Work in the background.** Cutting out, describing, measuring a pattern and drawing a
  shoe carry on with the page closed and are picked up again after a restart. Add, the
  closet's tiles and the item page each say what is happening in their own words today
  (*headed for:* one progress line and one set of words).
- **Claude.** Describing, sorting photos, corrections in your words, the stylist and shop
  searches go through your Claude plan or your API key, in the order chosen in Advanced
  settings. The key has a monthly limit; when it is reached, pieces wait and the page says so.
