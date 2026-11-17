# Closet

A private, single-user wardrobe app. It runs as a small program on your own
computer; you use it in its own window there and as a home-screen app on your
iPhone. Your closet never leaves your computer.

**Status: stop A (the first of the app's try-it stops; see `docs/BACKLOG.md`).**
You can capture items with one photo each, get the background removed, browse
the closet on phone and desktop, try a 30-item demo closet, and back up and
restore. New items are described by Claude through your Claude plan.
Every item gets a drawing, which you can show instead of photos in the
closet. Outfits and shopping come at later stops. No
API key is needed.

## Install and first run

Download the program for your computer from the repository's **Releases**
page. There is nothing else to install.

**Windows:** double-click `Closet.exe`. The first time, Windows shows
"Windows protected your PC": click **More info**, then **Run anyway**.
Starting takes a few seconds; then Closet opens in a window of its own. Setting up a Windows PC to be the hub your phone reaches, step by
step, is in "Setting up Closet on a Windows PC (the hub)" below.

**Mac (Apple Silicon):** unzip `Closet-mac-arm64.zip` and double-click
**Closet**. The first time, macOS says it cannot verify the app: click **Done**,
open **System Settings → Privacy & Security**, scroll down to the message about
Closet, click **Open Anyway**, confirm with your password, then **Open**.
Requires macOS 14 or later.

Closet then opens in its own window, titled **Closet**:

1. Choose a passphrase (at least 8 characters). This is the only login.
2. The background-removal model (about 170 MB) downloads once, with progress
   shown at the top of the closet and in Settings. You can add photos
   straight away; they are processed when the download finishes.

After you add a photo, Closet removes its background, then asks Claude to
describe the item (see "Installing Claude Code" below). The name, category,
colour, pattern, formality, season, shape and material fill in by themselves a
little later; the item page says "Suggested by Claude" and you can change
anything that's wrong. Claude never changes something you set yourself.
**What is it?**, at the top of the item's details, says what kind of garment
it is in the words of your menswear guide (an oxford shirt, a fleece pullover, a
chelsea boot). Tap it to search ("chelsea", "jogger", "snap") or look through
the groups, and choose another; the drawing follows, details that kind doesn't
have are hidden, and the history can undo it. The closet's **Filter** can show
one group or one kind.
Once it is described the item gets its drawing: switch between **Drawing**,
**Cutout** and **Photo** above the item. Beside the drawing, **Not in the
drawing** lists what it can't show yet (for example a logo, or stripes drawn as
plain colour). For stripes, plaid and prints, Closet measures the pattern from the photo after Claude has described the item (it says **Measuring the plaid from the photo** meanwhile; it can take a minute or two) and the drawing shows it: a plaid straightened and lined up with the buttons, stripes where they really are, a print pieced from the cloth. Change the pattern on the item and it is measured again. The drawing follows your changes: pick another colour or sleeve
length and it is drawn again. **Photos | Drawings** above the closet shows the
whole closet either way; this device remembers your choice.
**What Claude saw**, at the bottom of the item page, lists the details it
noticed, including those the drawing can't show yet. If Claude can't be
reached, items wait and are described as soon as it can; if describing fails,
the item says why and offers **Try again**. **Describe it again** asks once
more, for example for items added before this version, which are not described
by themselves. The demo closet is never sent to Claude: its descriptions were
made in advance.

When a detail is wrong (how many buttons, which collar, a white collar on a
blue shirt), tap **Fix the details** under the picture. The details are grouped
(collar and neck, front, sleeves and cuffs, pockets, hem, cloth); tap one to see
its choices, drawn as small pictures of the item where the drawing would change,
and pick one: the drawing changes at once. Or type what's wrong in **Or say
what's wrong** ("it has three buttons", "it's a henley, not a tee") and tap
**Ask Claude**: it lists the changes it understood, and nothing changes until
you tap **Make these changes**. Your sentence and the item's description are
sent; the photo (with its background removed) only if Claude can't understand
the sentence without it, and it says so. Through the API key this counts towards
your monthly spending limit like describing items; when the limit is reached,
pick the details instead. What you fix stays when Claude describes the item again. **History**,
lower on the item page, lists every change to the description, newest first;
**Undo** puts one back, as long as nothing changed the same thing since. In the
demo closet you can pick and undo, but sentences are not sent to Claude.

Closing Closet's window does not stop Closet: it keeps running in the
background, with no icon, so your phone can still reach it and the nightly
backup still runs. Opening the program again (double-clicking it) brings the
window back. To stop the program use **Quit** at the bottom of Settings (on a
Mac, **Quit** in the Closet menu, ⌘Q, quits it too). If you would rather have an
icon near the clock (in the menu bar on a Mac), start Closet with `--tray`. The window remembers your login
the way a browser does; links to shops and other sites open in your usual
browser. If the window cannot open on your computer, Closet opens in your
browser instead, as it used to; on Windows that happens if the Microsoft Edge
WebView2 Runtime is missing (it comes with Windows 11 and current Windows 10).
If the copy that is running is an older version (you downloaded an update but
the old one was still open), Closet says so and asks whether to close the old
one and use the new one; your closet is the same either way. On Windows the
window has **Yes** (use the new one) and **No** (keep the old one). If start at
login was on, it now starts the new program.

Every day starts on **Today**, which the app opens on once your closet has at
least a top, something for your legs and a pair of shoes. It shows today's
weather where you are, lets you say what kind of day it is (the occasion, such
as **Casual** or **Business**, and the mood: **As usual**, **Sharp** or
**Relaxed**) and suggests outfits, best first: swipe (or use the arrows) to see
the others. Each outfit lists why it works and, set apart, anything to watch
out for, such as rain. Tap **I'm wearing this** to record a wear for every
piece at once (**Undo** takes it back). The **⋯** on a piece leaves it out
(**Not this piece**) or builds every outfit around it (**Start from this
piece**); tap a piece to open it. **As worn**, above the pieces, draws the
outfit as it is worn by a drawn person instead (the shirt under the open
jacket, the trousers below, the shoes under them); **Pieces** goes back, and your choice is
remembered on that device. Today uses the forecast for New York until you
choose your place: tap **Change** beside the weather to search for it or tap
**Use my location**, or to type today's low and high temperatures yourself.
When the weather cannot be fetched, Today still dresses you, for a mild day,
and says so. Offline, Today shows the outfits it last found that day.

Closet remembers what you wore together. The morning after, Today asks **How
was yesterday's outfit?** above the outfits: tap **Loved it**, **Fine** or
**Not again**, and if you like say why (**Too warm**, **Too cold**, **Too
dressed up**, **Got compliments** and a few more); **Not now** puts the
question away. Your answers shape what Today offers: pieces you loved together
come up together a little more, an outfit you said **Not again** to is not
offered again, and if you were cold on a day like today you are dressed a
little warmer. The outfit says when a rating played a part ("You loved these
together on 3 November"). **Worn** at the top of Today lists the outfits you
wore, newest first: rate one, or tap its rating to change it; under **⋯** are
**Wear this again** (Today starts from it, with what is clean) and **Remove**
(the wears it recorded go too). **Record an outfit** is for a day you got
dressed without Closet. Offline, the list shows what it last saw, and rating
waits until Closet on your computer can be reached.

**What's missing** (**Missing** in the bar at the bottom of a phone) looks at
your closet and what you wear and suggests what to buy, the most helpful
first. Each suggestion says why, in sentences about your own clothes, what to
look for (the kind of piece, the season, the colours that go with what you
have) and shows the pieces it is based on; tap one to open it. Tap **I'll look
for this** to put it on your **Wishlist**, or **Not for me** to hide it (you can
say why, but you don't have to; **Hidden** at the bottom brings it back). On
the wishlist, keep a note (size, shop, budget), add something by hand with
**Add by hand**, and when you have it tap **I bought it**: it leaves the list
and **Add** opens so you can photograph it. Your decisions are kept when the
suggestions are worked out again, and the demo closet keeps its own. Offline,
the screen shows what it last found, and nothing can be changed until Closet on
your computer can be reached again. A closet with fewer than 8 pieces is too
small to judge yet.

**Tell it how you live: 1 minute**, at the top of What's missing, asks how often
you dress for work, everyday life, going out, lounging at home, exercise and
vacation. Say how people dress at work, and roughly how many weeks you spend
away and whether those places are warm or cold. Days can overlap: work and
exercise can happen on the same day. **Not now** leaves the original suggestions
unchanged. You can answer later or change your answers from **Based on…** on
What's missing, or **Settings → How you live**. Tapping **Based on…** opens
your answers, with the weather note, explanation and your style words under them. With every situation set to
**Never**, choose some situations before asking what is missing.

Once answered, common days matter more than rare ones. A saved place lets
Closet use the last four full years of weather there; with no place or no
weather available it says so and gives each season equal weight. Vacation
uses your warm/cold answer, not the weather at home. The situation buttons
show just the suggestions for that part of your life.

With enough recorded wears or ratings, suggestions put your favourite colours
first among those that go with your clothes, separately for each kind of
clothing, and avoid fits and patterns you consistently dislike. A winter coat
is not treated as avoided just because your log covers summer.
**I never dress like that** also holds back similar suggestions for those
situations, but never other coats or jackets. The closed held-back section lists
each affected suggestion, what holds it back and how to bring it back. Older
hides only affect themselves until you agree to apply them more broadly.
The optional **My style in a few words** line is kept and shown back to you,
but is not interpreted yet. Lounging is only a guess from relaxed tops and
soft trousers, not a way to recognise sleepwear; exercise cannot yet tell
running gear from gym clothes or judge sports performance.

**Would this work?** at the top of What's missing (or **I found one: would it
work?** on a wish) checks a piece before you buy it. Take or choose a photo of
it (in a shop, or a picture saved from a shop's page) and Claude describes it,
or describe it by hand: the kind, the colour, how dressy, the season, how heavy
the cloth is and whether it keeps the rain off. Closet then tries it with your
clothes and answers in a few words, **Fills a gap**, **Works, and adds
something**, **Works, but you have it already** or **Hard to wear with what you
have**, with the reasons: the gap it would fill, the pieces of yours it goes
with (tap one to open it) and example outfits, the pieces you already have that
do the same job and how often you wear them, and what would make it hard to
wear. From the answer, **Put it on my wishlist** keeps it with its description
in the note (from a wish, **Add it to the wish's note** writes the answer into
that wish instead), and **I bought it** opens Add. The photo is not added to
your closet and is never saved on your computer: it is let go as soon as the
answer is ready, and a photo is described
the same way as a new item (your Claude plan first, the API key only when you
have switched it on, within its monthly limit). In the demo closet only
**describe it by hand** works, since the demo closet never sends anything to
Claude. Checks are kept only while Closet is running.

**Find some** on a wish asks Claude to search the web for up to 8 things on
sale now that match it: what the suggestion says to look for, your note, and
the **Price range** if you set one on the wish. It takes a minute or two. Each
one found shows its picture, shop and price, and how it would work with your
clothes, with the same answers and reasons as **Would this work?**. **Open in
shop** opens the shop's page in a new tab (from Closet's own window, in your
usual browser); nothing is ever bought or opened for
you, and **Remove** takes one off. **Check prices** looks at their prices again,
and while Closet is running it does so by itself once a day; when a price has
gone down the wish shows it ("Was $180.00, now $144.00"). Searching goes the
same way as describing an item: your Claude plan first, the API key only when
you have switched it on, and never past its monthly limit (when only the key
can be used, the wish says what a search could cost at most). The demo closet
never searches.

To record a single item: open it and tap **Wore it today** (tap **Undo** if
that was a mistake). The item shows how often it has been worn and when last, and lists
the recent days, each of which can be removed. **Put in the laundry** and
**It's clean** keep track of the wash; in the closet, items in the laundry
carry a small mark, and the **Clean** and **In the laundry** buttons show only
those.

The laundry mostly keeps itself. When you record a wear, a piece goes in the
laundry by itself once it has been worn as often as **Before it needs
washing** says (a shirt or tee after one wear, a sweater or trousers after
three; shoes, jackets, coats and accessories never). On your **laundry day**
everything in the laundry is clean again. Undo a wear and a piece it put in
comes back out. To change the day, or turn it off, open **Settings → Your
closet → Laundry**. To catch up after a wash on another day, the closet says
how many pieces are in the laundry: tap **Show**, then **All clean**. On an
outfit in **Worn**, **⋯ → Put these in the laundry** does it by hand.

**Insights** (the button at the top of your closet) turns what you have
recorded as worn into a few plain sentences: what each piece with a price has
cost per wear (type the price on the item, in dollars), what you have never
worn, what has not been worn for a long time in its season, what you wear most
over the last 30 and 90 days and all time, whether a few pieces do all the work
in each kind of clothing, and what your closet is made of. Tap a picture to open
the piece. A piece you never wear can be archived from there with one tap, or
kept: **Keep** stops it being listed for 90 days, remembered on that device
only. Until enough wears are recorded, each card says so instead of showing
numbers.

## Adding your clothes

Open **Add** (the round button in the middle of the bar at the bottom of a
phone; **Add clothes** at the top of the menu on a computer) and add any photos
at all: one piece of clothing per photo (the usual way, below), several pieces
laid out together, or a shoe from a few sides (both further down). Closet asks
Claude what each photo shows, a fraction of a cent with the API key, and which
photos are the same shoe:

- When every photo is one piece, they go straight in.
- When there is a photo of several pieces or a shoe, the photos wait in a list
  under **Your photos**, each saying what Closet made of it (**One piece**,
  **Several pieces**, **Shoe 1**, **Another shoe**). Change any that are wrong,
  remove one with **×**, and tap **Add these**.
- When Claude can't be asked (and always in the demo closet), the list says so
  and you sort them yourself the same way.
- More than 60 photos at once (a folder, say) go in one piece per photo without
  waiting to be sorted: add photos of several pieces or of shoes a few at a
  time.

- **On the computer:** click **Choose photos** and pick as many as you like,
  click **Choose a folder**, or drag photos or whole folders onto the page.
  Folders inside folders are included. Files that are not photos are skipped,
  and the page says which.
- **On the iPhone:** **Take photos** (the camera stays open between photos), or **Choose from library** and pick many
  at once.

The list underneath shows how many are waiting, uploading, added, already in
your closet, or did not work. Two photos go up at a time. **Pause** stops new
ones starting; **Cancel the rest** drops the ones not started yet. A photo that
did not work says why and has a **Retry** button.

Once a photo is in, its row shows what it became: the piece with its
background removed (the photo until then) and, once Claude has described it,
what Claude called it ("Navy crew-neck tee"). Until then the row says how far
it has got: **Removing background…**, **Waiting to be described by Claude** or
**Claude is describing it…**. Tap the row to open the item and fix anything
that's wrong. The file's name stays underneath, small, after **Added**. If the
items wait because of something you can change (the API key's monthly limit,
say), the page says so once, above the list, with **Open Settings**.

A photo that is already in your closet (the same file, even under another name,
even if that item is archived) is not added again; its row says **Already in
your closet** and opens the item it already is. A photo of an item you deleted
can be added again.

### Shoes

For the closest drawing of a shoe, add all of its photos in one go on **Add**:
one shoe on its own (not the pair), photographed from **the outer side, the
front and the inner side**, against a plain floor or wall in even light. Those
three are what the drawing needs; up to six are kept. **Choose photos** picks
several at once. **Take photos** opens the camera on the page, which stays open
so you can take one after another (tap **Take the photo** for each, then
**Close the camera**); where the page can't show the camera, your phone's
camera app takes one photo each time.

Closet groups the photos of the same shoe as **Shoe 1** (a second shoe is
**Shoe 2**) and shows each shoe as a checklist (**✓ Outer side · ✓ Front ·
Inner side**). It says when one is missing; the shoe can still be added, but the
drawing is better with all three. A photo that shows the pair is held back:
remove it and take one of a single shoe, or tap **It's one shoe** if Closet got
it wrong. Nothing is sent until you tap **Add these**; a seventh photo of one
shoe is left out, and the page says so.
Once it is added, the page shows the shoe the same way as the list of photos
above:
its picture and, once Claude has described it, what Claude called it; tap it
(or **See the shoe**) to open it.

You don't have to say which photo is which: Closet sorts them itself a few
seconds after the last one, and shows what each photo is under it on the shoe's
page (outer side, inner side, from above, front, back, sole). The outer side
then becomes the shoe's picture in the closet (or the inner side, if no photo
shows the outer one); the first photo you added stays the picture when it
already shows a side, or when none does. If none of the photos shows the shoe
from the side, the shoe's page says a photo of its side would help the drawing.
If a shoe has a logo or stripe on one side only and Closet can't tell the
outside from the inside, the shoe's page asks you which photo shows the outside
(the outside is the side that faces away from the other shoe when you wear
them); tap it, and the outside becomes the picture. On the shoe's page you can
also add more photos (**Add photos**) or remove one with its **×**; the main
photo (the picture, shown first) is replaced with **Retake** instead.

Closet draws the shoe's side from its main photo a moment after the photos are
sorted. If that photo does not work for that (it shows the pair, or the shoe
from the front, say), the item page says so and the shoe keeps its plain
drawing; **Retake** replaces the photo. In **Fix the details** you can change a colour of the drawing,
remove or move a stripe or logo, **Re-trace** it, or **Use the plain drawing**.
Your fixes stay when the shoe is drawn again. Fix the details also shows the
shoe from the front, as the outfit figure wears it, in two ways side by side:
**From the shoe's shape** and **From your photo**. Tap the one that looks more
like your shoe. **Add a front photo** there helps **From your photo** get the
toe, laces and logos right; once you add one, that view is used unless you
chose otherwise.

Once the photos are sorted (and you have answered the question about the
outside, if Closet asked it), Claude also draws the shoe from them for the
outfit figure, its toe turned out a little, as you stand. It notes what kind of
shoe it is, its colours and parts, and draws it straight on twice, checking
each against your photos; it then compares the two with your photos and keeps
the closer. Closet turns that drawing with its own 3D shoe, so every
panel and stitch turns the right way, and Claude draws the turned shoe twice
from it, keeps the better one and fixes what still differs from your photos.
This takes four to ten minutes and happens once, by itself. **Drawn for the
outfit figure** on the shoe's page shows the drawing on two legs, how long it
took, how often it was checked, and what it cost (on your Claude plan nothing
is billed; the page says what it would cost on the API key, about $2 a shoe).
The outfit figure (**As worn** on Today and on a trip's days) then wears that
drawing, the leg going into the shoe; a shoe with no drawing keeps its plain
one. Full-length
trousers just meet an ordinary sneaker, so over a low shoe like a boat shoe
the sock shows. A shoe drawn before this version is shown as it was, straight
on, with the figure turning its toe out; tap **Draw again** for the turned
drawing. If something at the back of an older drawing, such as a pull tab at
the heel, sits over the sock, **Draw again** puts what is behind the leg behind
it, or say so in the box below the drawing (next paragraph). Adding or
removing photos never draws the shoe
again: the page says **The photos changed since this drawing**. To draw it
again, tap **Draw again**; it asks first, and the old drawing stays until the
new one is done. A shoe added before this version is drawn when you tap **Draw
it** (its photos are sorted first if they never were), or by itself once you
add or remove one of its photos. If drawing fails, the
page says why and offers **Try again**. The demo closet's shoes are never sent
to Claude; its brown boots come with a drawing made in advance, so you can see
a drawn shoe on the figure there.

If one thing about the drawing is wrong, type it in **What's wrong with the
drawing?** under it, in one line (for example "the elastic sides should be
wider"), and tap **Send**. Claude changes only that, keeping the rest of the
drawing as it is, then checks the change against your photos. This takes
about a minute; the page says **Changing the drawing** and keeps showing the
old drawing until the new one is done. The new drawing comes with a line
saying what changed. If your photos do not show what the note asks (say, the
toe rubber is lower in the photos than you asked), the shoe is still drawn as
you asked, and the page says so in one line, so you can check. **Go back to
the drawing before** swaps back to the drawing you had, in one tap, and the
same button then offers the newer one again. Only the drawing before the last
change is kept (a new drawing from **Draw again** keeps the one before it the
same way). Your notes stay with the drawing they made: when you later tap
**Draw again**, Claude is given them, so a new drawing keeps to them. If
Claude cannot change it after three tries, the drawing stays as it was and
the page says so; send the note again, or say it another way.

### Several pieces in one photo

To add a pile at once, lay the pieces out with a little space between them (on
the bed or the floor), and take or choose the photo on **Add**. Closet sorts it
as **Several pieces**; tap **Add it**. Claude draws a numbered box around each
piece; this takes a few seconds, and goes through your Claude plan or the API
key exactly as describing does (the page says what one photo can cost with the
key). Then check the boxes, with each piece's cutout beside its box:

- **Remove** a box that is not a piece of clothing.
- **Join with…** puts two boxes together when one piece was split in two (a
  suit's jacket and trousers stay two items).
- Tap a box to choose it, then drag it or its round corners to fit the piece
  (by finger on the phone, or the arrow keys on a computer). **Add a box** adds
  one for a piece Claude missed.

**Add these N items** adds them: each becomes an item of its own, cut out,
described and drawn like any other photo. Photos still to check are listed on
**Add** until you add their pieces or **Forget this photo**. The same photo is not added twice. The
demo closet never sends photos to Claude, so there you draw the boxes yourself.

If the page is closed or the computer restarts during an import, open **Add**
again: it says how many photos were not added yet. Choose the same photos or
folder again and it carries on; the ones that already went in are not added
twice.

After an import, a note at the top of your closet says how many pieces need a
quick check (on a phone, a dot on **Closet** says so too); tap **Review** in it.
On a computer, **Review** also sits under **Closet** in the menu while there is
anything to check, with the number beside **Closet**. It shows, one item at a
time, only what Claude was unsure about. Tap another value if its guess is
wrong, then **That's right**, or **Skip for now**.

## Setting up Closet on a Windows PC (the hub)

The PC that keeps your closet and that the phone reaches is the "hub". Do these
steps once, in this order. Each says what you should see.

**1. Install Claude Code and sign in with your plan.** Follow "Installing
Claude Code" below (the PowerShell line). When `claude` asks how to sign in,
choose your **Claude account with subscription** (your Pro or Max plan), not an
Anthropic Console account: the Console one is billed per use. Then type
`claude auth status` and press Enter: it should say you are logged in, with your
own e-mail address. Use the PowerShell line rather than `npm`: Closet looks for
`claude.exe`, which that line (and `winget`) installs.

**2. Put Closet in a folder of its own.** Download `Closet.exe` from the
**Releases** page. In File Explorer make a folder such as
`C:\Users\you\Apps\Closet` and move `Closet.exe` into it. Not in **Program
Files**: Closet replaces itself when it updates, and Windows only lets it do that
in a folder of your own. Not in **Downloads** either, so it is not tidied away.

**3. Open it the first time.** Double-click `Closet.exe`.
- If your browser said "Closet.exe isn't commonly downloaded", click **⋯** beside
  it, then **Keep**, then **Show more → Keep anyway**.
- Windows then shows "Windows protected your PC" ("unknown publisher"): click
  **More info**, then **Run anyway**. It asks only this once. (Closet is not
  signed with a paid certificate, which is all this message means.)
- If Windows says **Smart App Control** blocked it, there is no **Run anyway**:
  Smart App Control only allows signed programs. Tell whoever looks after Closet
  rather than turning it off.

A few seconds later Closet opens in its own window (it is the page at
`http://127.0.0.1:8765`, which also works in a browser). Choose your
passphrase; the background-removal model starts downloading. Closing the
window leaves Closet running in the background; double-click `Closet.exe` to
bring it back.

**4. The firewall.** Closet only listens on this PC itself (127.0.0.1), never on
the network, so Windows normally asks nothing. If a "Windows Security" window
about Closet and **Private** or **Public** networks appears anyway, click
**Cancel**: nothing needs to be let through. The phone comes in through
Tailscale, which runs on this PC and passes the phone's requests to Closet here.

**5. Check that Claude can be reached.** In Closet open **Settings → Describing
clothes**. Under **Your Claude plan, through Claude Code** it should say **Ready
to use.** If it says Claude Code is not installed, quit Closet (**Quit** at the
bottom of Settings) and open it again so it sees the new program; if it says
installed but not signed in, do step 1's `claude` sign-in again, then press
**Check again**.

**6. Start at login.** In Closet's **Settings → Your closet**, turn on **Start
Closet when I log in**. From then on Closet starts by itself when you sign in to
Windows, with no window (double-click `Closet.exe` to open it). If you ever move
`Closet.exe`, turn it off and on again so it points to the new place.

**7. Reach it from the iPhone.** Install Tailscale on the PC (tailscale.com,
**Download**, Windows) and on the iPhone (App Store), and sign in to both with
the same account. Then follow "Use it from your iPhone" below: run the
PowerShell command **Settings → Phone access** shows (usually
`tailscale serve --bg 8765`), then open the address Settings shows in Safari on
the phone.

**8. Where your closet is kept.** Everything is in the `Closet` folder in your
user folder, `C:\Users\you\Closet` (to open it: press Windows+R, type
`%USERPROFILE%\Closet` and press Enter). Its `logs\closet.log` is what to send if
something goes wrong. Choose a backup folder in **Settings → Your closet →
Backups** (a OneDrive folder is ideal). An API key, if you save one, is kept in
**Windows Credential Manager** (Control Panel → Credential Manager → Windows
Credentials, as `Closet/anthropic-api-key`), not in that folder.

## Use it from your iPhone

The phone reaches your computer privately over Tailscale; the app is never on
the public internet.

1. On the computer, make sure Tailscale is running and signed in. In the
   Tailscale admin console, under **DNS**, turn on **MagicDNS** and **HTTPS
   certificates** (once per account).
2. Open Closet's **Settings → Phone access**. It shows the command to run on
   this computer, usually `tailscale serve --bg 8765`. Open a terminal
   (PowerShell on Windows) and run it once. Open Settings again (it can take
   half a minute to notice): **Phone access** now shows Closet's address, like
   `https://your-pc.your-tailnet.ts.net`.
3. On the iPhone, with Tailscale connected, point the Camera app at the QR
   code under the address in Settings and tap the link it shows (or type the
   address into Safari). Log in with your passphrase.
4. Tap **Share → Add to Home Screen**. Open Closet from the new icon.

**If another app on this computer already uses Tailscale Serve.** Tailscale
gives each computer one usual address, and only one app can have it. If another
app already has it, `tailscale serve --bg 8765` would clash with it, and the
plain address would open that other app instead of Closet. Closet notices this
and suggests a command that gives Closet its own port instead, such as
`tailscale serve --bg --https=8443 8765`. Closet's address then ends in that
port, like `https://your-pc.your-tailnet.ts.net:8443`. Always use the address
**Settings → Phone access** shows: it is the one that really reaches Closet.
If it says Closet is not shared yet, run the command it shows.

To see what this computer shares, run `tailscale serve status`. Closet's share
is the line that points to `http://127.0.0.1:8765`.

**If Closet's address changes** (for example it moved to `:8443`), the icon on
the iPhone's home screen still opens the old one. Press and hold that icon
and delete it, then open the new address in Safari, log in, and add it to
the home screen again.

`tailscale serve` shares only inside your own Tailscale network. Do not use
`tailscale funnel`, which would publish the address to the internet. To stop
sharing Closet, run the command under **Settings → Phone access**, such as
`tailscale serve --https=443 off` (or `--https=8443`, the port in Closet's
address). It stops only Closet's share. Do not use `tailscale serve reset`: it
also stops every other app's share on this computer.

The computer must be on and Closet running for the phone to add or change
anything. When it is not, the phone still shows your closet from its last
visit, read-only.

## Installing Claude Code

Closet will ask Claude to describe your clothes (what kind of garment, colour,
collar, buttons and so on). It does this through **Claude Code**, a free
program from Anthropic that uses your Claude plan, so nothing extra is charged
per photo. An API key can be used instead, but it is billed per photo by
Anthropic, is only used when the plan can't be, and only if you turn on
**Allow the API key** in **Settings → Describing clothes**. It is off until you do.
**Settings → Describing clothes** shows each of the two once, with one line
saying whether Closet can use it right now, which it will try first, and how
many items are waiting to be described.

**Which to use.** Under the API key box in **Settings → Describing clothes** you choose the
order: **Use my Claude plan first, the key only if the plan can't** (the
usual one), **Use the API key first** (if you would rather pay per photo than use
up your plan), **Only my Claude plan**, or **Only the API key**. The two that put
the key first can only be chosen once a key is saved, and removing the key puts
you back on the plan first. Whatever you choose, the key is still only used once
**Allow the API key** is on with a monthly limit. The choice applies to everything
Closet asks Claude: describing clothes, finding where a patterned top's seams are,
corrections you type, and "Would this work?".

**Adding an API key.** Make a key in your Anthropic account (console.anthropic.com,
**API keys**), copy it, and paste it into **Paste your API key** in **Settings →
Describing clothes**, then **Save key**. Closet asks Anthropic whether it accepts the key
(this costs nothing) and keeps it in your computer's own keychain (the Mac's
keychain, or Windows Credential Manager), never in a file. It is never shown
again; **Replace key** and **Remove key** are there when you need them. Then turn
on **Allow the API key** and set a monthly limit (under **Monthly limit and
spending**, just below the switch). A key saved here is used instead
of one set as `ANTHROPIC_API_KEY`.

**What the API key costs.** At the prices Closet knows (written down on
3 November 2026 — prices change, so check Anthropic's pricing page), one photo
costs well under 1¢, about $0.003 at most. To allow the API key you set a
**monthly limit** in US dollars; $5 is suggested, enough for well over a
thousand photos. Before every request Closet adds what this month has cost so
far to the most that request could cost, and if that would pass the limit it
does not ask: the item waits and says the monthly limit was reached. Your plan
is still used whenever it can be. **Monthly limit and spending** shows what this month has cost, how
many requests were made, what the waiting items would cost at most and the
last few months. If Anthropic refuses the key or says the account is out of
credit, Closet turns the API key off and says why in Settings. What Closet
shows is worked out from its own price list; your Anthropic account shows what
was really charged.

You install Claude Code once and sign in once. You need to type two short
commands; copy and paste them exactly.

**Windows:**

1. Open the Start menu, type **PowerShell** and open **Windows PowerShell**.
2. Paste this line and press Enter:
   `irm https://claude.ai/install.ps1 | iex`
   (or, if you prefer the Windows package manager: `winget install Anthropic.ClaudeCode`).
3. When it has finished, close PowerShell and open it again.

**Mac:**

1. Open **Terminal** (press Command-Space, type **Terminal**, press Enter).
2. Paste this line and press Enter:
   `curl -fsSL https://claude.ai/install.sh | bash`
3. When it has finished, close Terminal and open it again.

**Sign in (both):** in the same window type `claude` and press Enter. It opens
your browser; sign in with your Claude account, then come back and type
`/exit` to close it. This sign-in is remembered.

**Check it:** type `claude auth status` and press Enter. It says you are logged
in (and which account) when everything is ready. Then open **Settings →
Describing clothes** in Closet and press **Check again**: "Your Claude plan, through
Claude Code" should say **Ready to use**. If it says Claude Code is not installed,
quit Closet and start it again so it sees the new program.

**If an item says Anthropic turned down the account Claude Code is signed in
to:** Claude Code on your computer is signed in to an account that no longer
works, for example a work account that has been turned off, instead of your
own Claude plan. In Terminal (or PowerShell) type `claude`, then `/logout`,
then `/login`, sign in with your own Claude subscription, then `/exit`. Your items are described by
themselves within a minute or two; an item that already says Claude couldn't
describe it needs **Try again**.

### Updates

From the version after the one that added this, Closet updates itself. Once a
day while it runs (and whenever you press **Check now** in **Settings →
Updates**) it asks GitHub whether a newer release is out; it sends nothing
about you or your clothes. In **Settings → Updates** choose:

- **Ask me first** (the standard choice): Closet downloads the new version and
  checks it, then a slim bar at the top says "Closet 0.3.0 is ready ·
  Install". Settings shows the version and what's new. Nothing changes until
  you press **Install**.
- **Install updates by themselves**: the same, without asking.
- **Never check**: Closet only looks when you press **Check now**.

Installing backs up every closet first (into `Closet\backups`, and into your
backup folder if you chose one), replaces the program, and starts the new
version on the same address; the page says Closet is restarting and
reconnects by itself. If the new version does not start within a minute, the
old one is put back and Settings says why. A download that does not match
GitHub's checksum is never installed.

The version that first has this has to be installed by hand, as before: quit
Closet, replace the program, open it. On Linux, or when Closet runs from
source, it only tells you a new version is out, with a link.

## Your data

Everything lives in a folder called `Closet` in your home folder (for example
`C:\Users\you\Closet`): the database, images, settings, logs and the
downloaded model. Updating replaces only the program file (see "Updates"
above); this folder is not touched. If an update changes the database, a copy is saved in
`Closet\backups` first. An older program refuses to open a closet written by a
newer one instead of damaging it.

**Settings → Your closet → Storage** shows how much space this folder takes: photos,
cutouts, thumbnails, backups kept on this computer and the background-removal
model, plus how much free space the disk has left.

### Backups

In **Settings → Your closet → Backups**, choose a folder (a cloud-synced folder is ideal).
Closet backs up there once a day while it is running, catches up at the next
start if the computer was off, and shows the date of the last good backup. It
keeps the 14 most recent database snapshots, each with the photos and cutouts
it had; a picture that did not change is stored only once. The settings file
with your passphrase is not included.

### Restore

Quit Closet, then in a terminal:

```
Closet.exe restore "D:\path\to\your backup folder"
```

(On a Mac: `Closet.app/Contents/MacOS/Closet restore "/path/to/folder"`.) The
closet that was there before is moved aside into a `replaced-…` folder, not
deleted.

If the computer loses power or Closet is stopped while a restore is putting
files in place, the next start finishes the restore, or puts your closet back as
it was before it, never half of each. A message at the top of the screen says
which, until you press **OK**.

### Forgotten passphrase

Quit Closet and run `Closet.exe reset-passphrase`. The next start asks for a
new one. Your closet is untouched.

### Placing the model by hand

If the computer cannot download the model, download
`isnet-general-use.onnx` on another machine from the address shown in
**Settings → Advanced** (open it near the bottom of the page), and put it in
`Closet\models`. Closet checks the file and starts using it. The address can be
changed there too. **Settings → Your closet → Background removal** says whether
the model is ready. **Advanced** also shows where your closet is stored and the
version of Closet.

### Where you are

Closet uses New York's weather until you choose your place. In **Settings →
Where you are** (or **Change** on Today), search for your town or city and
choose it from the list, or tap **Use my location**. Only the name you search
for and the chosen place's location are sent, to the free weather service
Open-Meteo; nothing about your clothes is. **Use my location** asks your
browser (or, in Closet's window, your computer) where you are only when you tap it, and sends that position, rounded
to about a kilometre, to OpenStreetMap to find the town's name. On the phone
over Tailscale the browser may not share its position (the address is not
https); search by name there instead. **Back to New York** forgets your place.
After you answer **How you live**, the same place is also used for long-term
weather on What's missing. That lookup sends only the coordinates and keeps
the result for six months. Your life answers and style words stay on your
computer, in its settings; they are not in closet backups.

### Light or dark

Closet follows your computer's or phone's light or dark setting. To choose
one yourself, go to **Settings → Look** and pick **Light** or **Dark**; pick
**Same as this device** to follow the device again. The choice is remembered
on each device separately. Clothing pictures stay on a light background in
dark mode, so their colours look right.

## Demo closet

**Show the demo closet** in **Settings → Your closet** opens a sample closet of about 40 items (with worn outfits, two wishes with made-up shop finds and a saved trip) so you can try
everything without your own photos, with a few outfits worn in the last two
weeks (yesterday's not rated yet, so Today asks about it). It is kept separate from your real closet
and is never backed up. A slim strip at the top of every screen says you are
in it; **Leave** takes you back to your own closet. Photo credits are in
`backend/closet/demo_data/CREDITS.md`.
What's missing uses fixed example life answers and seasons in the demo,
unaffected by your own answers or place. Switch back to your own closet to
save your answers. The grey runners and the brown boots are drawn as a shoe
photographed from the side is, so you can try **Fix the details** on them.

## For development

- `backend/` — FastAPI + SQLite. `pip install -r backend/requirements-dev.txt`,
  then `python -m closet` from `backend/` (tests: `python -m pytest`).
- `frontend/` — React + TypeScript + Vite; see `frontend/README.md`.
- `packaging/` — the PyInstaller build and its smoke test; see its README.
- `bench/` — tagging and illustration experiments from phase 0.
- `docs/` — `DECISIONS.md` (what and why), `BACKLOG.md` (what is left),
  `API.md`, `PHASE0.md`.

## Planning a trip

Open **Trips** (in the sidebar; on the phone, the **Trips** button at the top of Today or in Settings) and choose **Plan a trip**. Search for where you are going, pick the first and last day (up to 30 days), the occasion, and whether you can do laundry there (on one day of the trip, or every few days). Closet shows the weather (the forecast, or what those dates are usually like), what to pack with how many days each piece is worn, basics like socks, and an outfit for each day. Use "Not this one" to swap a piece out and "Take something else" to insist on one. Save the trip, then tick things off as you pack, on the computer or the phone. Under the list, "Why these counts" says how each count was worked out ("5 shirts: one a day, laundry on day 4") and where each wash falls. How many times you wear each kind of clothing before it needs washing is set in **Settings → Your closet → Before it needs washing** (a shirt once, a sweater or trousers three times, a jacket the whole trip, to start with); on a hot or humid day, what you wear next to the skin is counted as worn once.
