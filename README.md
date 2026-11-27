# Nines

Nines is a wardrobe app for one person. It runs as a small program on your own computer, and
you use it in its own window there and as an app on your iPhone's home screen. Your closet
stays on your computer.

You photograph your clothes. Nines cuts each piece out of its photo, has Claude describe it,
and draws it. Each day it suggests what to wear for the weather and the occasion, and it keeps
track of what you wore, the laundry, trips to pack for, and what is worth buying next.

Nines was called Closet until November 2026. If you still have `Closet.exe`, see
[Moving from Closet.exe to Nines.exe](#moving-from-closetexe-to-ninesexe).

**Contents**

- [Install](#install)
- [Installing Claude Code](#installing-claude-code)
- [Using the app](#using-the-app)
- [Setting up a Windows PC as the hub](#setting-up-a-windows-pc-as-the-hub)
- [Use it from your iPhone or another computer](#use-it-from-your-iphone-or-another-computer)
- [Use it without Tailscale, through Cloudflare](#use-it-without-tailscale-through-cloudflare)
- [Who can open your closet](#who-can-open-your-closet)
- [Updates](#updates)
- [Your data](#your-data)
- [What leaves your computer](#what-leaves-your-computer)
- [For development](#for-development)

## Install

Download the program for your computer from the
[Releases page](https://github.com/ericksoni716/daily-clother/releases). There is nothing else
to install.

**Windows.** Double-click `Nines.exe`. The first time, Windows shows "Windows protected your
PC": click **More info**, then **Run anyway**. If your phone will reach Nines on this PC,
follow [Setting up a Windows PC as the hub](#setting-up-a-windows-pc-as-the-hub) instead.

**Mac (Apple Silicon, macOS 14 or later).** Unzip `Nines-mac-arm64.zip` and double-click
**Nines**. The first time, macOS says it cannot verify the app. Click **Done**, open **System
Settings → Privacy & Security**, scroll down to the message about Nines, click **Open
Anyway**, confirm with your password, then click **Open**.

Nines opens in its own window on your empty closet. There is no password to choose (see
[Who can open your closet](#who-can-open-your-closet)). The first time, it downloads the
files that cut your clothes out of their photos, about 170 MB, and shows the progress at the
top of the closet. You can add photos straight away; they are cut out once the download
finishes.

Next, [install Claude Code](#installing-claude-code) so Claude can describe your clothes. To
look around before adding your own, turn on **Show the demo closet** in **Settings → Advanced
settings**.

### The window, and Nines in the background

Closing the window does not stop Nines. It keeps running in the background, so your phone can
still reach it. Open the program again to bring the window back. To stop it, press **Quit
Nines** at the bottom of Settings (on a Mac, ⌘Q works too). To have an icon near the clock (in
the menu bar on a Mac), start Nines with `--tray`.

While it runs, Nines backs up your closet once a day (once you have chosen a backup folder),
and checks for updates and for wishlist prices once a day. Each morning from five o'clock it asks Claude for the day's outfits, so they
are ready when you open Today. It skips this when you have not opened Today for more than
three days.

- Links to shops and other sites open in your usual browser.
- If the window cannot open, Nines opens in your browser instead. On Windows this happens when
  the Microsoft Edge WebView2 Runtime is missing; it comes with Windows 11 and current
  Windows 10.
- Typing Nines' address (`http://127.0.0.1:8765`) into a browser on this computer shows a page
  asking you to open Nines from its icon. That keeps the websites you visit out of your
  closet.
- If you open a newer version while an older one is still running, Nines asks whether to close
  the old one and use the new one. Your closet is the same either way.

## Installing Claude Code

Nines asks Claude to describe your clothes, choose your outfits and answer what you write to
it. It does this through Claude Code, a free program from Anthropic that uses your Claude plan
(Pro or Max), so nothing extra is charged per photo. You install it once and sign in once.

**Windows**

1. Open the Start menu, type **PowerShell** and open **Windows PowerShell**.
2. Paste this line and press Enter:

   ```
   irm https://claude.ai/install.ps1 | iex
   ```

   Use this line (or `winget install Anthropic.ClaudeCode`) rather than `npm`: Nines looks for
   `claude.exe`, which these install.
3. When it has finished, close PowerShell and open it again.

**Mac**

1. Open **Terminal** (press Command-Space, type **Terminal**, press Enter).
2. Paste this line and press Enter:

   ```
   curl -fsSL https://claude.ai/install.sh | bash
   ```

3. When it has finished, close Terminal and open it again.

**Sign in.** In the same window, type `claude` and press Enter. It opens your browser. Choose
your **Claude account with subscription**, not an Anthropic Console account, which is billed
per use. Then come back and type `/exit`. The sign-in is remembered.

**Check it.** Type `claude auth status` and press Enter. It should say you are logged in, with
your own email address. Then open **Settings** in Nines: under **Claude** it should say
**Using your Claude plan.** If it says Claude Code is not installed, quit Nines and open it
again so it sees the new program. If it says Claude Code is not signed in, sign in as above and
press **Check again**.

**If an item says Anthropic turned down the account.** Claude Code is signed in to an account
that no longer works, such as a work account that was turned off. In Terminal or PowerShell,
type `claude`, then `/logout`, then `/login`, sign in with your own Claude plan, then `/exit`.
Waiting items are described within a minute or two; an item that already says Claude couldn't
describe it needs **Try again**.

### Using an API key as well

You can also give Nines an Anthropic API key. Anthropic bills a key per use, so Nines does not
use it until you turn it on, and never spends past a monthly limit you set.

1. Make a key in your Anthropic account (console.anthropic.com, under **API keys**).
2. In Nines, open **Settings → Advanced settings → Claude**, paste the key into **Paste your
   API key** and press **Save key**. Nines checks it with Anthropic, which costs nothing, and
   keeps it in your computer's keychain (the Mac's keychain, or Windows Credential Manager),
   never in a file. It is never shown again.
3. Type a limit in **Monthly limit (US dollars)**. $5 is suggested, which is enough for about
   200 photos.
4. Turn on **Allow the API key**.

**Which to use**, in the same place, sets the order: your plan first, then the key (the usual
choice); the key first, then your plan; only your plan; or only the key. The order applies to
everything Nines asks Claude.

What the key costs, roughly, at the prices Nines knows (prices change; your Anthropic account
shows what was really charged):

| What Nines asks | About |
|---|---|
| Describing one photo | 2¢. Nines counts up to 10¢ before it asks, to be sure of staying under your limit |
| Choosing the day's outfits | 8¢ each time |
| Drawing a shoe for the outfit figure | $2 a shoe |
| Searching shops for a wish | The wish says the most a search could cost before you start one |

Before every request, Nines adds what this month has cost so far to the most the request could
cost. If that would pass your limit, it does not ask, and the item waits. **Spending so far**
shows this month's requests and the earlier months. If Anthropic refuses the key or says the
account is out of credit, Nines turns the key off and says why in Settings. A key saved in
Nines is used instead of one set as `ANTHROPIC_API_KEY`.

## Using the app

The app has four places, in the bar at the bottom of a phone (with **Add** in the middle) and in
the menu on a computer.

- **Today** suggests outfits for the day's weather, your occasion and your mood. Claude chooses
  them from your clothes, what you wrote in **Your style**, and what you wore lately and said
  about it. Tap **I'm wearing this** to record the outfit. Today also leads to **Worn**, every
  outfit you wore, and to **Trips**, which plans what to pack and an outfit for each day away.
- **Closet** shows every piece, as photos or as drawings. Open a piece to correct its details,
  record a wear or put it in the laundry.
- **Add** takes your photos (see below).
- **Wardrobe** suggests what is worth buying, keeps your wishlist and watches its prices,
  checks a piece before you buy it (**Would this work?**), and shows what you wear most and
  least.
- **Settings** holds your style, your place for the weather, your sizes, the laundry day, your
  other devices and your backups.

What each screen does, in detail, is in [docs/USING.md](docs/USING.md).

### Taking photos that work well

- **One piece per photo** is the usual way. You can choose many photos at once; on a computer
  you can also choose a whole folder, or drag photos onto the page.
- **Stripes, plaid and checks** are measured from the photo. If Nines can't measure them, the
  item says so and offers **Retake the photo**. A photo of the piece laid flat on a plain
  surface, taken from straight above, usually works.
- **Several pieces in one photo**: lay them out with a little space between them. Claude draws
  a box round each piece, you check the boxes, and each becomes an item of its own.
- **Shoes**: photograph one shoe on its own, not the pair, from the outer side, the front and
  the inner side, against a plain floor or wall in even light. Add all its photos in one go.
  Nines gathers them into one shoe and works out which side each photo shows. Up to six photos
  are kept.

JPEG, PNG, WebP, HEIC and AVIF photos all work, so a photo saved from a shop's page goes in
too. The same photo is never added twice.

## Setting up a Windows PC as the hub

The hub is the PC that keeps your closet and that your phone reaches. Do these steps once, in
this order.

1. **Install Claude Code and sign in** with your Claude plan, as in
   [Installing Claude Code](#installing-claude-code).
2. **Put Nines in a folder of its own.** Download `Nines.exe` and move it into a folder such as
   `C:\Users\you\Apps\Nines`. Not in **Program Files**, where Windows would not let Nines
   replace itself when it updates, and not in **Downloads**, where it might be tidied away.
3. **Open it the first time.** Double-click `Nines.exe`.
   - If your browser said "Nines.exe isn't commonly downloaded", click **⋯** beside it, then
     **Keep**, then **Show more → Keep anyway**.
   - When Windows says "Windows protected your PC", click **More info**, then **Run anyway**.
     It asks only once. The message means only that Nines is not signed with a paid
     certificate.
   - If Windows says **Smart App Control** blocked it, there is no **Run anyway**. Tell
     whoever looks after Nines rather than turning Smart App Control off.
   - If a "Windows Security" window asks about **Private** or **Public** networks, click
     **Cancel**. Nines listens only on this PC, never on the network; your phone comes in
     through Tailscale.
4. **Check that Claude can be reached.** Under **Claude** in Settings it should say **Using your
   Claude plan.**
5. **Keep Nines running.** In **Settings → Other devices**, press **Keep Nines running**.
   Windows asks whether to let **Windows PowerShell** make changes: choose **Yes**. Nines'
   window closes and opens again a few seconds later. From then on, Windows starts Nines when
   the computer turns on, before anyone signs in, and starts it again within a few minutes if
   it ever stops. If Windows won't do that for your account, it starts Nines when you sign in
   instead, and the card says so.
6. **Keep the PC awake.** Windows can only run Nines while the computer is on and awake. Keep
   it plugged in, and in Windows' **Settings → System → Power & battery**, set sleep to
   **Never** when plugged in. On a laptop, in **Control Panel → Power Options → Choose what
   closing the lid does**, choose **Do nothing** when plugged in. Locking the screen is fine.
7. **Reach it from your iPhone**, as in
   [Use it from your iPhone or another computer](#use-it-from-your-iphone-or-another-computer).
8. **Choose a backup folder** in **Settings → Advanced settings → Backups**. A OneDrive folder
   is ideal.

What **Keep Nines running** changes:

- Nines keeps a copy of itself in `%LOCALAPPDATA%\Nines`, and Windows runs that copy.
  Double-click your `Nines.exe` to open the window as before. Updates go to that copy, so your own
  `Nines.exe` may fall behind it; that does no harm.
- It replaces **Start Nines when I log in**, which Nines turns off. On a Mac, keep using
  **Start Nines when I log in**.
- The card shows **Nines answers on port** and a number. That is the port Tailscale and
  Cloudflare point at, and it no longer changes.
- To stop it, press **Turn this off** in the same card. Windows asks again, on the computer's
  screen, so this can't be done from the phone. Your closet is not touched. If the copy Windows
  ran is newer than your `Nines.exe`, it takes your file's place.

## Use it from your iPhone or another computer

Your phone reaches your computer privately over [Tailscale](https://tailscale.com), so Nines is
not on the public internet.

1. Install Tailscale on the computer and on the iPhone (from the App Store), and sign in to
   both with the same account.
2. In the Tailscale admin console, under **DNS**, turn on **MagicDNS** and **HTTPS
   certificates**. You do this once per account.
3. In Nines on the computer, open **Settings → Other devices**. It shows a command to run once,
   usually `tailscale serve --bg 8765`. Run it in a terminal (PowerShell on Windows). Within
   half a minute, Settings shows Nines' address, such as
   `https://your-pc.your-tailnet.ts.net`.
4. On the iPhone, with Tailscale connected, point the Camera at the QR code under **Show the QR
   code** in Settings and tap the link, or type the address into Safari. Your closet opens;
   there is nothing to type.
5. Tap **Share → Add to Home Screen**, and open Nines from that icon from then on.

Another computer signed in to your Tailscale opens the same address in its browser.

The computer must be on and Nines running for the phone to add or change anything. When it is
not, the phone shows your closet from its last visit. You can still record what you wear, rate
an outfit and tick a packing list; these are sent when Nines answers again.

**If something is not right**

- **Another app already uses Tailscale Serve.** Only one app can have the computer's usual
  Tailscale address. Nines notices and suggests a command that gives it its own port instead,
  such as `tailscale serve --bg --https=8443 8765`; its address then ends in `:8443`. Always
  use the address **Settings → Other devices** shows.
- **The address changed.** The icon on the home screen still opens the old one. Delete the
  icon, open the new address in Safari and add it to the home screen again.
- **The phone says "Nines could not tell who you are".** Tailscale did not say who was asking.
  Check that the phone is signed in to your Tailscale, then check **Settings → Other devices**
  on the computer. On the phone, Settings says under **This device** how it came in.
- **To see what this computer shares**, run `tailscale serve status`. Nines' line points to
  `http://127.0.0.1:` and Nines' port.
- **To stop sharing Nines**, run the command shown under **Show the QR code**, such as
  `tailscale serve --https=443 off`. Don't use `tailscale serve reset`, which stops every other
  app's share too. Never use `tailscale funnel`, which would publish Nines to the internet;
  Nines turns such visits away.

### Send a product's page to your wishlist

On an Android phone, or in Chrome on a computer, install Nines from the browser (**Add to Home
screen** or **Install**). Nines is then in the share sheet: on a product's page, tap **Share**,
then **Nines**. The link waits in the **Add a link** box until you tap **Add to the list**.

An iPhone does not put web apps in its share sheet, so a Shortcut does it. Make it once:

1. In the **Shortcuts** app, tap **+** and name the shortcut **Add to Nines**.
2. Open its details (the **ⓘ** button) and turn on **Show in Share Sheet**. Where it says what
   the shortcut receives, choose **URLs** and **Safari web pages** only.
3. Add the action **URL Encode**, with **Shortcut Input** in it.
4. Add the action **Text**. Type Nines' address from **Settings → Other devices**, then
   `/wardrobe/link?url=`, and right after that put the **URL Encoded Text** from step 3.
5. Add the action **Open URLs**, with the **Text** in it, and tap **Done**.

Then, on a product's page in Safari or a shop's app, tap **Share → Add to Nines**. Nines opens
in Safari with the link in the box; tap **Add to the list**. The iPhone must be connected to
your Tailscale.

## Use it without Tailscale, through Cloudflare

Tailscale is enough for an iPhone. For a browser that cannot run Tailscale, such as a work
computer, Nines can also have an address on a domain you own, through Cloudflare. Know what
that means first:

- Nines then has an address on the public internet, and anyone can find it. Cloudflare asks
  whoever opens it for a code sent to your email and lets only your email through. Nines checks
  Cloudflare's sign-in on every request and asks nothing else.
- Cloudflare carries everything between that browser and your computer, so it can read what
  passes through, your photos included.

Tailscale stays the private way in. Until you do the steps below, Nines has no such address.
You need a free Cloudflare account with a domain you own on it; the domain is the only cost.
The names below are examples.

1. **A tunnel to this computer.** In Cloudflare, open **Zero Trust → Networks → Tunnels** and
   create a tunnel. Run the command Cloudflare shows (it installs `cloudflared`) on the
   computer Nines runs on. Add a public hostname (or route), such as `nines.example.com`,
   pointing at `http://127.0.0.1:` followed by Nines' port. Read the port from Nines rather
   than guess it, since another app may use the usual one. On Windows, turn on **Keep Nines
   running** first so the port stays the same, then read **Nines answers on port** in
   **Settings → Other devices**. On a Mac, the port is the last number of the `tailscale serve`
   command shown there.
2. **A sign-in in front of it.** In Zero Trust, open **Access → Applications** and add a
   self-hosted application for the same name. Give it a policy that allows only your own email
   address, with the one-time code sign-in. In the application's overview, copy its
   **Application Audience (AUD) tag**, and note your team's domain, which looks like
   `yourteam.cloudflareaccess.com` (in Zero Trust's settings).
3. **Tell Nines.** On the computer, open **Settings → Other devices → Without Tailscale, through
   Cloudflare**. Fill in your team's domain, the audience tag and the address, and press
   **Save**. It then says **Also through Cloudflare, at nines.example.com**.
4. **Try it.** In a browser that is not on Tailscale, open `https://nines.example.com`.
   Cloudflare emails you a code, and after it your closet opens.

The three values can be changed on the computer, or from your phone through Tailscale, but
never from a browser that came in through Cloudflare. To turn the address off, empty any of
them and press **Save**, or delete the tunnel's public hostname in Cloudflare. If Nines shows
"Sign in through Cloudflare first" at that address, the Access application does not cover it:
check step 2. When Cloudflare's sign-in runs out, the page reloads by itself so Cloudflare can
ask for a new code.

## Who can open your closet

Nines has no password of its own. Who can open it depends on the way in:

- **On this computer**, only Nines' own window, or the browser it opens for you. It carries a
  key Nines made for it; a website you visit, or another program that only knows the address,
  is turned away.
- **Through Tailscale**, anyone signed in to your Tailscale network, and anyone you share this
  computer with there. A visit that Tailscale does not name, or one through Tailscale Funnel,
  is turned away.
- **Through Cloudflare**, if you set it up, only after Cloudflare's sign-in with the email you
  allowed.

A closet is not worth a second password. It does mean that if someone takes over your
Tailscale or Cloudflare account, or one of them is set up more widely than you meant, Nines has
nothing more to ask. Keep those two accounts to yourself.

## Updates

Nines updates itself. Once a day while it runs, it asks GitHub whether a newer version is out;
it sends nothing about you or your clothes. **Settings → Updates** shows your version and has
**Check now**. In **Settings → Advanced settings → Updates** you choose:

- **Ask me first** (the standard choice). Nines downloads and checks the new version, then a
  bar at the top offers **Install**. Nothing changes until you press it.
- **Install updates by themselves.** The same, without asking.
- **Never check.** Nines looks only when you press **Check now**.

Installing backs up every closet first, replaces the program and starts the new version; the
page reconnects by itself. If the new version does not start within a minute, the old one is
put back and Settings says why. A download that does not match GitHub's checksum is never
installed. On Linux, or when Nines runs from source, it only tells you a new version is out.

While Windows keeps Nines running, the copy Windows runs updates itself the same way. If you
download a newer `Nines.exe` by hand and open it, Nines asks whether to move the copy Windows
runs to that version; choose the new version.

### Moving from Closet.exe to Nines.exe

Up to version 0.11.0 the program was called `Closet.exe`, and it cannot install `Nines.exe` by
itself. Do this once:

1. Quit `Closet.exe` (**Quit** at the bottom of Settings, or from its icon).
2. Download `Nines.exe` and put it where you kept `Closet.exe`.
3. Double-click `Nines.exe`. If the old one is still running, Nines asks whether to close it:
   choose the new version.
4. Delete `Closet.exe` and don't start it again. It would make a new, empty `Closet` folder.

The first time it starts, `Nines.exe` renames the `Closet` folder in your user folder to
`Nines`, with everything in it; nothing is copied or deleted. If it can't yet, because
`Closet.exe` was still running, it uses the `Closet` folder as it is and tries again at a later
start. It also takes over **Start Nines when I log in** if that was on, and your saved API key
and backups move to the new name by themselves. If a backup or sync program of your own points
at the folder, point it at `Nines` afterwards.

## Your data

Everything is in a folder called `Nines` in your user folder: the closet, photos, settings,
logs and the downloaded files. On Windows that is `C:\Users\you\Nines`; to open it, press
Windows+R, type `%USERPROFILE%\Nines` and press Enter. If something goes wrong,
`logs\nines.log` in that folder is the file to send. **Settings → Advanced settings →
Storage** shows where the folder is and what takes the space.

Updating replaces only the program, not this folder. If an update changes the database, a copy
is saved in `Nines\backups` first. An older program refuses to open a closet written by a newer
one rather than damage it.

An API key, if you save one, is kept in your computer's keychain, not in this folder. While
Windows keeps Nines running, it is also kept in `api-key.sealed` in this folder, locked by
Windows to this computer, because Nines started before you sign in cannot read Credential
Manager. Backups never include it, and it is removed when you turn **Keep Nines running** off.

### Backups

In **Settings → Advanced settings → Backups**, choose a folder: one your computer copies to the
cloud is ideal, or a USB drive. Nines backs up there once a day while it runs, catches up at
the next start if the computer was off, and shows the date of the last good backup. It keeps
the 14 most recent copies of your closet, each with its photos; a picture that did not change
is stored only once. The backups go into a `Nines backup` folder inside the one you chose.

What you wrote in **Your style** and in a piece's notes is in your closet, so it is backed up.
The settings file, with your answers to **How you live** and the key of Nines' own window, is
not. The demo closet is never backed up.

### Restore

Quit Nines, then in a terminal (PowerShell on Windows) run:

```
Nines.exe restore "D:\path\to\your backup folder"
```

On a Mac, run `Nines.app/Contents/MacOS/Nines restore "/path/to/folder"`. The closet that was
there before is moved aside into a `replaced-…` folder, not deleted. If the computer loses
power during a restore, the next start finishes it or puts your closet back as it was, never
half of each, and a message says which.

### Placing the model by hand

Nines downloads two files that cut clothes out of photos: `isnet-general-use.onnx`, about
170 MB, and `u2net.onnx`, about the same size, which fixes cutouts the first gets wrong (a
striped shirt whose darker stripes were taken for background, or the bed a piece lies on). Both
download by themselves and are tried again after a failure.

If your computer cannot download them, open **Settings → Advanced settings → Background
removal → If a download keeps failing**. It shows the address each file comes from and, on the
computer, where each one goes. Download the file on another machine from that address and put
it there (the first goes in `Nines\models`). Nines checks the file and starts using it. Photos
cut out before the second file arrived are looked at again, and the ones it would do better are
cut out again.

## What leaves your computer

Your closet stays on your computer. Nines sends only this:

- **To Claude**, through your plan or your API key: your clothes' photos and descriptions, to
  describe and draw them and to choose your outfits, and what you type to Claude. A shop search sends the wish, your style, what you tend to wear, the brands
  you own and your size, never a photo or a note. The demo closet never sends anything to
  Claude.
- **To Open-Meteo**, the free weather service: the name of the place you search for and the
  chosen place's location. **Use my location** sends your position, rounded to about a
  kilometre, to OpenStreetMap to find your town's name, and only when you tap it. On a phone
  over Tailscale the browser may not share its position; search by name there instead.
- **To shops**: Nines opens product pages from your computer to read their prices: the links
  you add to your wishlist, once a day, and the sales Claude finds, before showing them.
- **To GitHub**: the daily check for a new version, which carries nothing about you.

## For development

- `backend/`: FastAPI and SQLite. `pip install -r backend/requirements-dev.txt`, then
  `python -m closet` from `backend/`. Tests: `python -m pytest`.
- `frontend/`: React, TypeScript and Vite; see [frontend/README.md](frontend/README.md).
- `packaging/`: the PyInstaller build and its smoke test; see its README.
- `bench/`: the shoe tracing bench, run by hand, and the open-licence photos of the demo
  closet; see its README.
- `tools/`: developer scripts, never shipped.

Start with [AGENTS.md](AGENTS.md), which has the rules and the checks to run before a pull
request. Then, in `docs/`: [DEVELOPING.md](docs/DEVELOPING.md) (where each thing lives and how
to add to it), [DESIGN.md](docs/DESIGN.md) (the principles, and a checklist for any change),
[USING.md](docs/USING.md) (what each screen does), [DECISIONS.md](docs/DECISIONS.md) (what was
decided and why), [BACKLOG.md](docs/BACKLOG.md) (what is left),
[assessment/](docs/assessment/README.md) (the November review and its order of work) and
[API.md](docs/API.md). [CHANGELOG.md](CHANGELOG.md) lists what changed for the person using
Nines, newest first.
