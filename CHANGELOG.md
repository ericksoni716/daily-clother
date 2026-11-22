# Changelog

What changed for the person using Nines, newest first. Releases are on the
[Releases page](https://github.com/ericksoni716/daily-clother/releases); versions before
0.9.0 are described there only.

Every change the owner can see gets a line under **Unreleased** in the pull request that
makes it: a sentence in plain words about what is different, not about the code. A change
nobody using the app would notice (a refactor, a test, a doc) gets none.

## Unreleased

### Added

- **Shades**, on an item's page: under **Details**, the Colour row now offers the shades of the
  piece's colour under the colours, each with its swatch (Green has Sage, Mint, Forest green,
  Hunter green and Teal; Navy has Navy, Midnight and Raw indigo), 55 in all. Choosing a colour keeps the
  choices open on its shades; choosing a shade saves it with its colour, and the drawing is drawn
  in it. The colour itself stays what Today, What's missing and Would this work? go by. A shade
  you choose is yours: describing the piece again keeps it, and choosing another colour puts it
  aside. Fix the details no longer lists the shade, since it is chosen with the colour.
- **Five new shades**: Mint, French blue, Taupe, Salmon and Mauve, which Claude can also name when
  it describes a photo.
- **Formality between two levels.** A piece that could be either, like penny loafers, can now be
  smart casual and business at once. On the item page, open **Formality**, choose its level, then
  under **It can also be** choose the level next to it; the row then reads "Smart casual to
  business". Choosing a level again makes it one level. Today, trips, What's missing and **Would
  this work?** count such a piece as either level, whichever suits the day, and Claude is told it
  can be either when it chooses your outfits. When Claude describes a photo it may give two
  levels itself for a piece that sits between them; a formality you chose stays as you chose it
  when the item is described again.

### Fixed

- **Check now** says what it found, under the button on Advanced: "Nines 0.15.0 is out." with
  **Install now** beside it, or "You have the latest version." Before, only "Last checked"
  changed there, so a new version looked as though it had not been found. When it finds one in
  **Ask me first**, Nines starts getting it ready at once, so the banner offers it within a
  minute or two instead of up to half an hour later.

## 0.15.0

### Added

- **Swim trunks** are a kind of their own, under Trousers & shorts in **What is it?**, and Claude
  recognises them when it describes a photo. They are drawn as short shorts with a drawstring
  waist and swim fabric's slight sheen. Today never puts them in an outfit (unless you build one
  around them), and What's missing does not count them as everyday shorts. A trip has a new
  choice, **Swimming or the beach**, which turns on by itself when a day of the trip reaches 27°C
  and which you can turn on or off; your choice is kept when the trip is planned again. While it
  is on, your swim trunks are packed under **For swimming**, one pair for a trip of up to a week
  and two for a longer one, never in a day's outfit, and if you have none the trip says so.

## 0.14.0

### Added

- **Add a link**, on your wishlist: paste the address of a product's page and Nines makes a wish
  from it, named after the product, with its price. Nines reads the page itself first, from your
  computer; only when the page doesn't give its price is Claude asked to read it, the same way as
  **Check prices**. On a wish's page, **Add a link** adds another product to that wish. The pages
  you send are checked once a day with the rest, and when a price goes down the wish's row in the
  wishlist says so ("Down from $68.00 to $54.40"). On an Android phone, or in Chrome on a
  computer, you can share a page to Nines from the share sheet; on an iPhone, a Shortcut does it
  (the README says how). Either way the link waits in the box until you tap **Add to the list**.
  In the demo closet a page is read, but Claude is never asked.

- **Add to the drawing**, in Fix the details: for what no detail shows (a patch, a panel, a
  tab, a line of stitching), write one line, such as "a small red patch on the left sleeve", and
  Claude draws it onto the piece's drawing, using the drawing as it is as its guide and keeping
  the rest, then checks it against the photo. It takes a minute or two, and you can leave the
  page meanwhile. What Claude added shows on the closet picture and on the outfit figure, where
  it moves with the garment (a patch on a sleeve stays on the sleeve). The sheet lists what was
  added, with how long it took and what it cost, and **Go back to the drawing before** and
  **Take Claude's additions off** undo it. When Claude can't turn a sentence in "What's wrong
  with it?" into a detail, **Have Claude draw it onto the drawing instead** moves it to the new
  box for you to send. Not for shoes, which have their own note under their drawing, and never
  in the demo closet.

- **Settings → Advanced settings → Background removal** now says what it has: a line for each of
  the two models, the main one that cuts out every photo and the second one asked as well for
  stripes and checks, each saying whether it is ready, how far its download has got, or why it
  didn't download, with **Download** or **Try again** beside one that is missing or failed.

- On **Check the pieces** (a photo of several pieces), a slip can be taken back. After each
  change a line says what it was, with **Undo**. A box Claude found that you moved or reshaped
  has **As Claude found it**, one you removed is listed with **Put back**, and **Back to what
  Claude found** puts every box back as Claude found it. Claude is not asked again for this.
  It works for photos added from this version on.

### Changed

- The last places where the program still called itself Closet now say Nines. You may notice
  three things after updating:
  - Your backups go into a **Nines backup** folder inside the backup folder you chose. The
    first backup after the update renames the **Closet backup** folder there to **Nines
    backup**, with everything in it, so nothing is copied twice and every earlier backup can
    still be restored. If you sync that folder (OneDrive, iCloud Drive), the sync app sees one
    folder renamed. If another program has a file in it open, that backup goes into **Closet
    backup** as before and the next one tries again. If you have both folders, Nines uses
    **Nines backup** and leaves **Closet backup** as it is.
  - An API key you saved is now kept in the keychain (Windows Credential Manager, or the Mac's
    keychain) under the name **Nines** instead of **Closet**. The first start after the update
    moves it there by itself and removes the old entry; if it cannot, the key stays under
    Closet and is still used, and the next start tries again.
  - The log in the data folder is now `logs\nines.log` (it was `closet.log`; the first start
    renames it), and its lines and the program's command-line help say Nines.

- In **Fix the details**, the detail that colours a top's collar, cuffs and ribbing is now called
  **collar and cuff colour** (it was "trim colour"), under Collar and neck. Choose **same as the
  body** when the drawing shows the collar in a colour it does not have. Telling Claude "the collar
  is the same colour as the rest" now changes it too.

### Fixed

- **Today** said "Couldn't choose today's outfits" whenever Claude chose your outfits in the
  installed program: the guide Claude is given (your outfit notes from the menswear taxonomy)
  was looked for where it is only found in the source code, not where the program keeps it.
  Asking for the day's outfits ahead of your first look failed the same way, every two minutes.
  Both work again.

- On the outfit figure, a fuzzy top (flannel, fleece, sherpa, mohair) had a thick band in a shade
  of its cloth down the edges of its sleeves instead of its outline. Its sleeves now have the same
  dark outline and soft fuzz as its own drawing.

- Ribbed cuffs on trousers can be set and seen. In Fix the details, a pair of trousers' hem is
  under **Hem and cuffs**, and every choice there now changes the drawing: a ribbed cuff on track
  pants, tech pants or lounge pants is drawn, and joggers can be given a turn-up or a split hem
  instead of their ribbed cuffs. Joggers, sweatpants and a knit set's trousers say "ribbed cuff"
  for their hem, as their drawing shows. A ribbed cuff now looks knitted, with its ribs and the
  leg gathered into it, on the item's drawing and on the figure as worn.

- The ribbed cuffs, hem band and neck of a sweatshirt, sweater, hoodie or polo are drawn in the
  same colour as the rest of it, with fine ribs. Before, they were drawn a shade lighter or darker,
  so a black sweatshirt looked as if it had grey cuffs, and nothing you told Claude could change it.
  A contrast colour Claude saw, or you chose, still shows.

- A knitted top that Claude described as "plain" (a plain weave, a woven cloth) is drawn as plain
  cloth, not with a woven check. Claude is now told that plain means a woven cloth, and Fix the
  details calls it **plain weave**. Your clothes are drawn again the next time you open them.

## 0.13.0

### Added

- **Settings → Everyday → Show drawings instead of photos** shows your clothes' drawings
  wherever they are shown small: the closet, Today, Worn, trips and the Wardrobe, and an item's
  page opens on its drawing. It is kept on the computer, so it holds on every device. A piece
  with no drawing yet shows its photo. The Photos / Drawings switch over the closet starts from
  it and no longer remembers its choice on the device: to keep drawings, turn the setting on.

### Changed

- An item's page now reads in the order you go through a new piece: the picture and the name,
  then what it is, its brand and its price, straight under the name and changed in place; then
  wearing and washing and About it; then how it looks (the line about it, Fix the details and a
  shoe's drawings by Claude); a shoe's photos come near the end. Size, material, the date you got
  it and its condition are under **Size, material and more**.

- Every piece you add now comes to the review once, besides those Claude was unsure of: one at a
  time, with its picture, its name to type over, what Claude thinks it is, and boxes for the brand
  and the price. **That's right** saves it all at once. When a piece you just added has been
  described, Add offers **Check them one at a time**. Pieces already in your closet count as
  checked, and changing the name, kind, brand or price on an item's page counts too.

- On a shoe's page, **Change which photo shows the outside** under its photos puts right a swap
  Claude was sure of. Before, you could only say so when Claude was unsure.

- A shoe's photo in the closet is now the photo of its outer side whenever one of its photos
  shows it, so the photo and the side drawing show the same side. Before, a first photo of the
  inner side stayed as the shoe's photo. Shoes already in your closet are put right by
  themselves, without Claude looking at them again.

- The **Phone** group in Settings is now called **Other devices**, and its sentences speak of your
  phone or another computer, since another computer on your Tailscale reaches Nines the same way.

- Nines no longer has a passphrase. Who can open it is decided by the way in: on this computer,
  Nines' own window; through Tailscale, anyone Tailscale names as signed in to your Tailscale
  network (a device it does not name is turned away, with a page saying what to check); through
  Cloudflare, Cloudflare's sign-in with your email. Nothing is asked when you open Nines, on any
  device. **Log out** is gone from Settings; what it also did, forgetting the copy of your closet a
  device keeps for when Nines can't be reached, is now **Forget saved copies** under **Settings →
  This device**. `Nines.exe reset-passphrase` is gone too. A page left open from an older
  version opens your closet as it is, or says to reload.

## 0.12.0

### Added

- On Windows, Nines can keep running for your phone: in **Settings → Other devices**, press **Keep Nines
  running** and say Yes when Windows asks. Windows then starts Nines when the computer turns on,
  before you sign in (or when you sign in, where Windows will not do that), and starts it again
  within a few minutes if it stops. Opening Nines opens its window onto that copy, the port it
  answers on stops changing, updates come back the same way, and a newer `Nines.exe` you open by
  hand offers to move it to the new version. It replaces **Start Nines when I log in**, and
  **Turn this off** in the same place puts things back as they were, keeping the newest version
  of the program. Settings also says which port
  Nines answers on, for setting up Tailscale and Cloudflare.

- You can correct a shoe's side drawing with a one-line note, as you could its drawing for the
  figure: under **What's wrong with the drawing?**, choose **The side**, and Claude changes only
  the side, checks the change against the photos and says when your note goes against them.
  The front stays as it was, **Go back to the drawing before** undoes the change, and your notes
  on the side are kept for every later side drawing of that shoe.

### Changed

- The program is now called Nines too: `Nines.exe` on Windows, and `Nines.app` in
  `Nines-mac-arm64.zip` on a Mac. If you have `Closet.exe`, it cannot install this version by
  itself and says there is no download for this computer. Download `Nines.exe` once from the
  release page, put it where `Closet.exe` was, start it (if the old one is still running, Nines
  offers to close it) and delete `Closet.exe`. If Nines started when you logged in, it still
  does. Later versions install themselves again.

- The folder your closet is kept in is now called Nines too. The first time Nines starts, it
  renames the Closet folder in your user folder to Nines, with everything in it; nothing is
  copied or deleted. If the old program is still running, or the folder cannot be renamed, Nines
  uses the Closet folder as it is and tries again at its next start. If both folders exist,
  Nines uses the Nines folder and leaves Closet alone. Anything of your own that points at the
  folder, such as a backup or sync program, needs pointing at Nines.

## 0.11.0

### Added

- AVIF photos work wherever you add a photo: on Add, when you take a piece's photo again, as
  a shoe's other photos and in Would this work?. Many shops save their pictures as AVIF, so a
  photo saved from a shop's page now goes in like any other.
- Claude now draws each shoe from its side too, from its photos, in the same clean style as
  your other drawings, with its own panels, marks and sole. That drawing becomes the shoe's
  picture in the closet, and the shoe's page shows it beside the drawing for the figure, with a
  line on what makes the shoe itself. It is made alongside the drawing for the figure, sharing
  its calls to Claude, so it adds little wait; shoes drawn before get theirs by themselves. Until it exists, or
  if it can't be made, the picture is traced from the side photo as before, and that trace now
  also gives Claude the shoe's proportions.
- Nines can have an address of its own through Cloudflare, for a browser that cannot use
  Tailscale: set it up with the README's steps, then fill in the three values under **Settings →
  Phone → Without Tailscale, through Cloudflare** on the computer. Cloudflare asks for a code sent
  to your email, Nines checks Cloudflare's sign-in on every request, and your passphrase is still
  asked. It is off until you set it up, and those values can never be changed from a browser
  that came in through Cloudflare.
- On a phone or a browser that came in from outside, **Settings → This device** says how: through
  Tailscale and as whom (or that Tailscale did not say), or through Cloudflare and with which
  email.

### Changed

- The app is called Nines now, as in "dressed to the nines", with a new icon: an empty dinner
  jacket in the air. Your clothes, your closet and the place called Closet are as they were.
  On your iPhone the home-screen icon and name change once you add the app to the Home Screen
  again. The program on your computer is still called Closet for now; its new name follows in
  a later version.
- Two shoes are drawn from their photos at the same time instead of one after another, so a
  shoe you add while another is being drawn no longer waits for it. Each drawing is made
  exactly as before.
- With the API key, a check of a shoe's drawing that finds nothing wrong now finishes sooner:
  the app stops reading Claude's answer once it says the drawing is good, instead of waiting
  for the whole drawing to be written out again. What is drawn is the same. Such a check is
  counted at the most Claude could have written in the time it took, so the cost shown for a
  drawing, and the month's spending, can be a little higher than what was billed.
- While a shoe's picture is Claude's side drawing, Fix the details no longer offers the traced
  drawing's colours, marks and Re-trace, which would not change it; Use the plain drawing stays,
  and Use Claude's drawing brings it back.
- On a phone, the "Add" label in the bar at the bottom sits on the same line as Today, Closet,
  Wardrobe and Settings, and its round button rises a little above the bar instead of pushing
  the label down to the edge.
- **Show the demo closet** is now the last thing on Advanced settings, in a group of its own,
  instead of the first. While the demo closet shows, the strip at the top of every screen
  still has Leave.
- On the computer, Nines now opens only from its own icon. An old bookmark to
  `http://127.0.0.1:8765`, or the address typed into a browser, shows a page asking you to
  open Nines from its icon; once you do, Nines' window (or the browser it opens) works as
  before, also after a restart. This keeps websites you visit from reaching your closet.
  Your phone, through Tailscale, and your passphrase work as before.
- If a phone or a browser tab still shows the page from before this update, saving something
  there says the page is from an older Nines and asks you to reload it.
- Nines no longer answers through Tailscale Funnel, Tailscale's way of putting an address on
  the open internet; the phone through Tailscale works as before.

### Fixed

- On Windows, when Claude Code was installed through npm (a `claude.cmd`, not a `claude.exe`),
  describing an item through your Claude plan could never start, because Windows cannot pass
  that long a request to it, and the error only said the command line was too long. The app
  now says why, suggests Claude Code's PowerShell installer, and uses your API key instead when
  you have one.

## 0.10.0

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
- An item's page is shorter and says each thing once. Under the name, one line says what it
  is, its colour and how it sits, read from the same description the drawing is made from, so
  the words and the drawing always agree; "Something wrong? Tell Claude" under it opens Fix the
  details. Then Wearing and washing, and About it: how you feel about it and one box, Notes
  for you and Claude, which shows every note you had kept in the older boxes. The rest is
  folded: Details, Shopping facts, History, and describing again, archiving or deleting.
- What Claude saw is gone from the item page: the details one by one in Fix the details show
  the same values, marked when you set them, with when Claude described it. What the drawing
  leaves out is a small mark on the drawing. The shape (sleeves, neckline, length, fit) is no
  longer asked among the Details; you change it in Fix the details.
- Outfits, the stylist, what's missing and packing now read a piece's sleeves, fit and the
  weight of its cloth as you corrected them in Fix the details, as the drawing does. Searching
  the closet also finds words in a piece's notes, whichever box they were kept in.
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
