# Closet

A private, single-user wardrobe app. It runs as a small program on your own
computer; you use it in a browser there and as a home-screen app on your
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
Starting takes a few seconds; there is no window, only a coat-hanger icon near
the clock.

**Mac (Apple Silicon):** unzip `Closet-mac-arm64.zip` and double-click
**Closet**. The first time, macOS says it cannot verify the app: click **Done**,
open **System Settings → Privacy & Security**, scroll down to the message about
Closet, click **Open Anyway**, confirm with your password, then **Open**. The
icon appears in the menu bar. Requires macOS 14 or later.

Your browser then opens the app:

1. Choose a passphrase (at least 8 characters). This is the only login.
2. The background-removal model (about 170 MB) downloads once, with progress
   shown at the top of the closet and in Settings. You can add photos
   straight away; they are processed when the download finishes.

After you add a photo, Closet removes its background, then asks Claude to
describe the item (see "Installing Claude Code" below). The name, category,
colour, pattern, formality, season, shape and material fill in by themselves a
little later; the item page says "Suggested by Claude" and you can change
anything that's wrong. Claude never changes something you set yourself.
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

To stop the program use **Quit Closet** in the icon's menu or in Settings.
Double-clicking the program while it is already running just opens the app.
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
outfit as it is worn instead (the shirt under the open jacket, the trousers
below, the shoes at the bottom); **Pieces** goes back, and your choice is
remembered on that device. With no place saved, type today's low and
high temperatures there instead. Offline, Today shows the outfits it last
found that day.

Closet remembers what you wore together. The morning after, Today asks **How
was yesterday's outfit?** under the outfits: tap **Loved it**, **Fine** or
**Not again**, and if you like say why (**Too warm**, **Too cold**, **Too
dressed up**, **Got compliments** and a few more); **Not now** puts the
question away. Your answers shape what Today offers: pieces you loved together
come up together a little more, an outfit you said **Not again** to is not
offered again, and if you were cold on a day like today you are dressed a
little warmer. The outfit says when a rating played a part ("You loved these
together on 3 November"). **Worn** at the top of Today lists the outfits you
wore, newest first: rate one or change its rating, **Wear this again** (Today
starts from it, with what is clean), **Remove** it (the wears it recorded go
too), or **Record an outfit** for a day you got dressed without Closet. Offline,
the list shows what it last saw, and rating waits until Closet on your computer
can be reached.

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
What's missing, or **Settings → How you live**. Tap **Based on…** to open the
weather note, explanation and your style words. With every situation set to
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

To record a single item: open it and tap **Wore it today** (tap **Undo** if
that was a mistake). The item shows how often it has been worn and when last, and lists
the recent days, each of which can be removed. **Put in the laundry** and
**It's clean** keep track of the wash; in the closet, items in the laundry
carry a small mark, and the **Clean** and **In the laundry** buttons show only
those.

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

Open **Add**. One piece of clothing per photo works best.

- **On the computer:** click **Choose photos** and pick as many as you like,
  click **Choose a folder**, or drag photos or whole folders onto the page.
  Folders inside folders are included. Files that are not photos are skipped,
  and the page says which.
- **On the iPhone:** **Take photo**, or **Choose from library** and pick many
  at once.

The list underneath shows how many are waiting, uploading, added, already in
your closet, or did not work. Two photos go up at a time. **Pause** stops new
ones starting; **Cancel the rest** drops the ones not started yet. A photo that
did not work says why and has a **Retry** button.

A photo that is already in your closet (the same file, even under another name,
even if that item is archived) is not added again; its row says **Already in
your closet**. A photo of an item you deleted can be added again.

If the page is closed or the computer restarts during an import, open **Add**
again: it says how many photos were not added yet. Choose the same photos or
folder again and it carries on; the ones that already went in are not added
twice.

After an import, open **Review**: it shows, one item at a time, only what
Claude was unsure about. Tap another value if its guess is wrong, then
**That's right**, or **Skip for now**. The number on **Review** says how many
items are left.

## Use it from your iPhone

The phone reaches your computer privately over Tailscale; the app is never on
the public internet.

1. On the computer, make sure Tailscale is running and signed in. In the
   Tailscale admin console, under **DNS**, turn on **MagicDNS** and **HTTPS
   certificates** (once per account).
2. Open a terminal (PowerShell on Windows) and run this once:
   `tailscale serve --bg 8765`
   It prints an address like `https://your-pc.your-tailnet.ts.net`. Closet's
   Settings page shows the same address under **Phone access**.
3. On the iPhone, with Tailscale connected, open that address in Safari and
   log in with your passphrase.
4. Tap **Share → Add to Home Screen**. Open Closet from the new icon.

`tailscale serve` shares only inside your own Tailscale network. Do not use
`tailscale funnel`, which would publish the address to the internet. To stop
sharing: `tailscale serve reset`.

The computer must be on and Closet running for the phone to add or change
anything. When it is not, the phone still shows your closet from its last
visit, read-only.

## Installing Claude Code

Closet will ask Claude to describe your clothes (what kind of garment, colour,
collar, buttons and so on). It does this through **Claude Code**, a free
program from Anthropic that uses your Claude plan, so nothing extra is charged
per photo. An API key can be used instead, but it is billed per photo by
Anthropic, is only used when the plan can't be, and only if you turn on
**Allow the API key** in **Settings → Tagging**. It is off until you do.
**Settings → Tagging** shows which of the two Closet can use right now and how
many items are waiting to be described.

**Adding an API key.** Make a key in your Anthropic account (console.anthropic.com,
**API keys**), copy it, and paste it into **Paste your API key** in **Settings →
Tagging**, then **Save key**. Closet asks Anthropic whether it accepts the key
(this costs nothing) and keeps it in your computer's own keychain (the Mac's
keychain, or Windows Credential Manager), never in a file. It is never shown
again; **Replace key** and **Remove key** are there when you need them. Then turn
on **Allow the API key** and set a monthly limit. A key saved here is used instead
of one set as `ANTHROPIC_API_KEY`.

**What the API key costs.** At the prices Closet knows (written down on
3 November 2026 — prices change, so check Anthropic's pricing page), one photo
costs well under 1¢, about $0.003 at most. To allow the API key you set a
**monthly limit** in US dollars; $5 is suggested, enough for well over a
thousand photos. Before every request Closet adds what this month has cost so
far to the most that request could cost, and if that would pass the limit it
does not ask: the item waits and says the monthly limit was reached. Your plan
is still used whenever it can be. Settings shows what this month has cost, how
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
Tagging** in Closet and press **Check again**: "Your Claude plan, through
Claude Code" should say **ready**. If it says Claude Code is not installed,
quit Closet and start it again so it sees the new program.

**If an item says Anthropic turned down the account Claude Code is signed in
to:** Claude Code on your computer is signed in to an account that no longer
works, for example a work account that has been turned off, instead of your
own Claude plan. In Terminal (or PowerShell) type `claude`, then `/logout`,
then `/login`, sign in with your own Claude subscription, then `/exit`. Your items are described by
themselves within a minute or two; an item that already says Claude couldn't
describe it needs **Try again**.

## Your data

Everything lives in a folder called `Closet` in your home folder (for example
`C:\Users\you\Closet`): the database, images, settings, logs and the
downloaded model. Updating means replacing the program file; this folder is
not touched. If an update changes the database, a copy is saved in
`Closet\backups` first. An older program refuses to open a closet written by a
newer one instead of damaging it.

**Settings → Storage** shows how much space this folder takes: photos,
cutouts, thumbnails, backups kept on this computer and the background-removal
model, plus how much free space the disk has left.

### Backups

In **Settings → Backups**, choose a folder (a cloud-synced folder is ideal).
Closet backs up there once a day while it is running, catches up at the next
start if the computer was off, and shows the date of the last good backup. It
keeps the 14 most recent database snapshots and one copy of every image. The
settings file with your passphrase is not included.

### Restore

Quit Closet, then in a terminal:

```
Closet.exe restore "D:\path\to\your backup folder"
```

(On a Mac: `Closet.app/Contents/MacOS/Closet restore "/path/to/folder"`.) The
closet that was there before is moved aside into a `replaced-…` folder, not
deleted.

### Forgotten passphrase

Quit Closet and run `Closet.exe reset-passphrase`. The next start asks for a
new one. Your closet is untouched.

### Placing the model by hand

If the computer cannot download the model, download
`isnet-general-use.onnx` on another machine from the address shown in
**Settings → Background removal**, and put it in `Closet\models`. Closet
checks the file and starts using it. The address can be changed in Settings.

### Where you are

In **Settings → Where you are**, search for your town or city and choose it
from the list, so Closet can look up today's weather when it suggests outfits.
Only the name you search for and the chosen place's location are sent, to the
free weather service Open-Meteo; nothing about your clothes is.
After you answer **How you live**, the same place is also used for long-term
weather on What's missing. That lookup sends only the coordinates and keeps
the result for six months. Your life answers and style words stay on your
computer, in its settings; they are not in closet backups.

## Demo closet

**Settings → Demo closet** opens a sample closet of 30 items so you can try
everything without your own photos, with a few outfits worn in the last two
weeks (yesterday's not rated yet, so Today asks about it). It is kept separate from your real closet
and is never backed up. Photo credits are in
`backend/closet/demo_data/CREDITS.md`.
What's missing uses fixed example life answers and seasons in the demo,
unaffected by your own answers or place. Switch back to your own closet to
save your answers.

## For development

- `backend/` — FastAPI + SQLite. `pip install -r backend/requirements-dev.txt`,
  then `python -m closet` from `backend/` (tests: `python -m pytest`).
- `frontend/` — React + TypeScript + Vite; see `frontend/README.md`.
- `packaging/` — the PyInstaller build and its smoke test; see its README.
- `bench/` — tagging and illustration experiments from phase 0.
- `docs/` — `DECISIONS.md` (what and why), `BACKLOG.md` (what is left),
  `API.md`, `PHASE0.md`.

## Planning a trip

Open **Trips** (in the sidebar; on the phone, the "Trips" link on Today or in Settings) and choose **Plan a trip**. Search for where you are going, pick the first and last day (up to 30 days), the occasion, and whether you can wash there. Closet shows the weather (the forecast, or what those dates are usually like), what to pack with how many days each piece is worn, basics like socks, and an outfit for each day. Use "Not this one" to swap a piece out and "Take something else" to insist on one. Save the trip, then tick things off as you pack, on the computer or the phone.
