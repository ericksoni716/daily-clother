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
plain colour). The drawing follows your changes: pick another colour or sleeve
length and it is drawn again. **Photos | Drawings** above the closet shows the
whole closet either way; this device remembers your choice.
**What Claude saw**, at the bottom of the item page, lists the details it
noticed, including those the drawing can't show yet. If Claude can't be
reached, items wait and are described as soon as it can; if describing fails,
the item says why and offers **Try again**. **Describe it again** asks once
more, for example for items added before this version, which are not described
by themselves. The demo closet is never sent to Claude: its descriptions were
made in advance.

To stop the program use **Quit Closet** in the icon's menu or in Settings.
Double-clicking the program while it is already running just opens the app.

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

To record a single item: open it and tap **Wore it today** (tap **Undo** if
that was a mistake). The item shows how often it has been worn and when last, and lists
the recent days, each of which can be removed. **Put in the laundry** and
**It's clean** keep track of the wash; in the closet, items in the laundry
carry a small mark, and the **Clean** and **In the laundry** buttons show only
those.

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
per photo. An API key can be used instead, but it is billed per photo, is only
used when the plan can't be, and only if you turn on **Allow the API key** in
**Settings → Tagging** (it is off, because there is no spending limit yet).
**Settings → Tagging** shows which of the two Closet can use right now and how
many items are waiting to be described.

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

## Demo closet

**Settings → Demo closet** opens a sample closet of 30 items so you can try
everything without your own photos. It is kept separate from your real closet
and is never backed up. Photo credits are in
`backend/closet/demo_data/CREDITS.md`.

## For development

- `backend/` — FastAPI + SQLite. `pip install -r backend/requirements-dev.txt`,
  then `python -m closet` from `backend/` (tests: `python -m pytest`).
- `frontend/` — React + TypeScript + Vite; see `frontend/README.md`.
- `packaging/` — the PyInstaller build and its smoke test; see its README.
- `bench/` — tagging and illustration experiments from phase 0.
- `docs/` — `DECISIONS.md` (what and why), `BACKLOG.md` (what is left),
  `API.md`, `PHASE0.md`.
