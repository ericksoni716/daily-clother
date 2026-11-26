# Changelog

What changed for the person using Nines, newest first. Releases are on the
[Releases page](https://github.com/ericksoni716/daily-clother/releases); versions before
0.9.0 are described there only.

Every change the owner can see gets a line under **Unreleased** in the pull request that
makes it: a sentence in plain words about what is different, not about the code. A change
nobody using the app would notice (a refactor, a test, a doc) gets none.

## Unreleased

### Changed

- **The day before a trip.** What you ticked as packed for a trip that starts tomorrow is left out of
  Today's outfits, and one line over them says so and opens the trip. Building an outfit around a packed
  piece still works. To have a piece back, untick it in the trip.
- **A laundry day while you are away.** A laundry day that falls on a day of a trip you saved now washes
  nothing: what you left in the laundry at home waits, like your suitcase, for the first laundry day after
  the trip. If you did the laundry on another day, **All clean** in the closet's laundry view says so.
- **More like this on a pick you saved.** In You might like, Save on a pick now turns into **✓ Saved** in
  the same place, and More like this stays beside it. Press ✓ Saved to take the pick off your wishlist again.
  Both buttons are on one line on every phone, and nothing moves when you save.

### Fixed

- **A page that could not be read is no longer "Sold out".** When a shop turns Nines away and Claude
  cannot read the page either, the wish keeps the last price it read and says whether it could be
  bought then; "Check now" ends saying how many pages could not be read and that their last prices are
  shown. A price is only marked sold out when the page itself says so.
- **A link from a shop that turns programs away is read all the same.** When Nines cannot read a
  product's name, Claude is asked once to read the whole page: its name, shop, picture, price and
  description, so the wish is named after the product and checked against your closet. A link whose
  name Nines read before is described from that name when the shop later turns Nines away.
- **Coats and jackets look like coats and jackets.** Claude now says what kind of garment a product is
  (a chore coat, an overcoat, a field jacket), and "See it with your clothes" draws that kind, worn
  open over your sweater and shirt. A coat or jacket of no known kind is drawn as one worn open, not as
  a closed tunic. The "Claude saw" line says "grey chore coat" rather than "grey coat". A link you sent
  before this is described once more, at its next price check, to learn its kind.
- **Find more finds menswear, and not what you already watch.** A search leaves out women's and
  children's products (the same coat's page in a shop's women's section among them), and the pages
  already on the wish. For a wish you made from a link, it looks for the same product at other shops
  first, then for pieces much like it. A wish still called by the shop's address asks for a name first
  instead of searching for the address.
- **A brand keeps its capital in a sentence.** A piece whose name starts with its brand (as you saved it on
  the piece's page) is now written as you wrote it after "your" or "the", so a find's card and Today's
  lines say "your Northfield sneaker", not "your northfield sneaker".

## 0.16.0

### Added

- **Wearing while the computer is off.** When your phone can't reach Nines (the computer is asleep
  or off), "I'm wearing this", how an outfit went and a tick on a packing list still work: each shows
  as done at once, is kept on this phone (through a reload or the app being closed), and is sent in
  the order you made it, once, when Nines answers again. The offline banner says so while they wait,
  and you can take one back before then. A wear or a rating counts for the day you tapped. If Nines
  turns one down when it gets it (a piece archived meanwhile, another outfit recorded for that day,
  the trip deleted), a message says what was not recorded and why. Everything else still waits for
  Nines, as before.
- **A trip covers today.** On a day inside a trip you saved in Trips, Today knows you are away without a
  note: the weather is where the trip is, the trip's own outfit for the day comes first, and the other
  outfits come only from what you packed. One line over the outfits says which day of the trip it is
  ("Day 3 of 7 of your trip to Lisbon.") and opens the trip, where today is marked. What you wear counts
  on the trip, so a shirt worn today is not offered again before a wash. **Not on this trip today**,
  under Change, dresses you from your whole closet at home for the rest of the day, on the phone and the
  computer alike; Undo is beside the line that says so. On a trip day Nines' own rules choose the outfits,
  as for a day ahead; Claude is not asked.
- **From a piece to an outfit.** On a piece's page, under Wearing and washing, **Build an outfit
  around it** opens Today built around that piece, in place of any piece built around before (the
  pieces you left out stay left out); Back returns to the piece. When Today could not (the piece is
  in the laundry, away, or not described yet) one line says when it can instead. Under it, **When you
  wore it** shows the outfits you wore the piece in, each with its pieces, the day and how it went;
  the same outfit worn on several days is shown once ("3 times, last on 12 Nov"), and a day you wore
  the piece without recording an outfit is a plain line. The first three are on the page, the rest
  behind "All 5 outfits". Each one's ⋯ offers **Wear this again**, as on Worn, and removing a wear,
  which used to be the Remove links under Recent wears. Today no longer says "nothing else suited as
  well" of a piece you wore lately when it is in the outfit because you asked for it.
- **Give it an outing.** Now and then, Today builds its last outfit around a piece you love or like and
  have not worn in a while, and says so in one sentence under its button ("An outing for your tweed
  jacket: you love it and have not worn it since 2 Oct."). The best outfit for the day stays first. It
  comes at most once every five days, never offers the same piece again for three weeks, and only on a
  day the piece suits. "Not this piece" on it gives you an ordinary outfit back for the day.
- **Smaller pictures in the closet.** Under **Show** in the Filter sheet, **Smaller** puts three
  pieces across on a phone (and more to a row on a computer); **Larger** goes back to two. This
  device remembers your choice. A small tile shows the picture and the name on two short lines,
  cut after a whole word when it is long.
- **Where a piece is.** On a piece's page, under Wearing and washing, one row says where it is: in
  your closet, at the cleaner's, at the tailor's or lent out, with the day you expect it back and a
  note of your own if you like (the note stays on your computer; Claude never reads it). **Change**
  opens the choices; while it is away the row offers **It's back**. Back from the cleaner's it is
  clean; back from the tailor's it no longer needs mending; you can undo either. A piece that needs
  mending has **Take it to the tailor's** in one tap. While a piece is away, Today does not offer it,
  a trip packs it only if you expect it back before you leave (and says it counts on that), and
  "not worn" leaves it alone; What's missing and Would this work? still count it as yours. The
  closet's line says how many are away ("2 away"); tapping it lists them, soonest
  back first, with **It's back** beside each. Wearing a piece that is away today brings it back.
- **Your nines, in the Wardrobe.** The nine pieces you wore most, as a square of three by three
  of their pictures (photos or drawings, as Settings says), each with how many times you wore it
  and opening the piece. Choose the last 30 days, 90 days or all time. It takes the place of the
  Worn most list. With fewer than nine it shows what there is and says how many.
- **What your clothes cost you.** One line in the Wardrobe says what you spent this year and on
  how many pieces, once a few pieces have a price and a date bought; until then it says how many
  have no price yet and opens the piece you wear most to add one. Under More numbers: what you
  spent each year, the pieces that have earned their price and those that have not yet, and what
  your wishlist would cost at today's prices (said per currency when shops price in more than one,
  never added up).
- **On sale now, on the You might like card.** A switch on the card, **For you** and **On
  sale**, remembered on your device. On sale shows three things marked down now that suit you,
  from the shops you like, the brands you wear, shops you have found things at before and
  smaller makers you may not know. Nines opens each shop's page itself before showing it: the
  price is the page's, a sale that has ended or is sold out is not shown, and anything under
  15% off is left out. Each row says the prices in the wishlist's words ("Was $120.00, now
  $84.00 (30% less)"), "Your size is in stock." when the page says so, and when only Claude read
  the earlier price. Save keeps the earlier price on the wish, so its page shows the drop. Once
  you have looked for sales once, Nines looks once a week under the same switch, on a different
  day from the other look, and checks each sale's page again daily: one that ended leaves the
  card.
- **Shops you like, in Settings, Everyday.** Up to 12 shop names or sites, where a look for
  things on sale starts. They are sent to Claude with that look.
- **Dress for another day.** **Another day**, beside Today's heading, opens the next days by name
  and a date of your choice, with the days you planned marked. A day shows in Today's own layout,
  with its weather (the forecast where it reaches, otherwise what those dates are usually like) and
  a word about the day if you give one ("dinner at eight"). **Wear this on Saturday** keeps the
  outfit for that day: nothing is worn and nothing goes in the laundry until you wear it. That
  morning Today opens on it, and a piece that cannot be worn by then is swapped and named. On the
  days before, a planned piece that would still be in the wash on its day is not offered. A plan can
  be changed or taken away with Undo, and the plans of the coming week are one line on Today. A day
  inside a saved trip points to the trip, which has that day's outfit. A day leads with its outfit:
  on the smallest phone five pieces and **Wear this on Saturday** are on the first screen, with one
  short line when its weather is not known ("No forecast for that day. Try again"). A piece away is
  offered for a day ahead only when you expect it back before that day; a planned piece still away
  on the morning is swapped and named with where it is ("Your navy blazer is at the cleaner's until
  Friday 27 November"), and so is one in a kept outfit you wear; an outfit for a day ahead that counts on
  a piece coming back says so in one line. Right after you plan a day it opens on the plan, with one
  Remove the plan. On a phone the outfit's heading keeps its words whole ("Best for today", "Best for
  Sat") with the count on its own small line. When your plans or the outfits you keep can't be read,
  the page says so with Try again. The demo's plan is now an outfit the rules have nothing to warn
  about.

- **Outfits you keep.** **Keep this outfit** under any outfit on Today, and in a worn outfit's
  choices, saves it without wearing it. Worn has a second half, **Outfits you keep**: name one in
  place, **Wear this** (Today starts from it, filling a piece you cannot wear today), **Wear this on
  another day**, or remove it with Undo. Keeping the same pieces twice is said, not kept twice, and
  an outfit whose piece has left your closet stays and says so.

- **You might like, in the Wardrobe.** A small card with three things on sale that Claude found
  from what you wear and love, not from something missing: each with its picture, price and how
  many of your pieces it goes with, and **Save** (onto the wishlist, its price watched),
  **More like this** and **Not for me** (with Undo). Nothing that only repeats what you have,
  and never the same product twice. Tap **Look now** the first time; after that Nines looks by
  itself once a week while it is running, which you can turn off under **How Nines looks**. A
  few "Not for me" alike may offer a line for Your style, kept only when you say so. The demo
  closet never searches.

- **See it with your clothes.** A find on a wish's page that has been checked against your closet
  (one Claude found, or a link you sent) has a **See it with your clothes** button. It opens up to
  three outfits made with it and your own pieces, each drawn as worn, with the shop's picture beside
  the drawing and the names of your pieces (tap one to open it). The new piece is drawn from the
  shop's description, so the sheet says once that it shows roughly its shape and colour, not how it
  really looks. **Would this work?** shows its example outfits the same way when you switch them to
  **As worn**. Nothing is sent to Claude for this, and it works in the demo closet.
- **Find some knows who it is shopping for.** Besides the wish, a search now tells Claude the
  lines of Your style, the colours, patterns and fits you wear most in that kind of piece and a
  few of the pieces you love or wear most (said in plain words, never their photos, names or
  notes), the brands on your clothes, and your size. Claude ranks what matches the wish by them;
  the wish and the most you'd pay still come first. One sentence under **Find some** says what
  is sent. The demo closet still sends nothing.
- **Your sizes**, in Settings under Everyday: one line with the sizes you saved ("Your sizes: M
  tops · 32x32 trousers · 10.5 shoes") and **Change**, which opens a short box for tops,
  knitwear, trousers and jeans, jackets and coats, and shoes, each saved as you leave it. When
  you have saved none for a kind, the size most of your own pieces of that kind carry is offered
  with **Use it**. **A brand that fits differently** keeps a brand's own size ("In Example
  Brand, L"). A search prefers products in stock in your size, when the shop lists sizes.
- **A link you send to your wishlist is checked against your closet.** Once Nines has read the
  product's name from its page, Claude describes it from what the page says (nothing about your
  closet is sent), and the wish shows it as it shows what Claude finds: whether it would work, what
  it goes with, what it repeats and which gap it would fill, with the shop's picture. When Claude
  can't be reached, the limit is reached or the demo closet is open, the card says it isn't checked
  yet, and Nines describes it at the next price check.
- **Search Google Shopping**, on each thing worth buying and on each wish, opens Google Shopping in
  your browser, searching for the kind of piece and its first colour (or the wish's name). Nothing
  else about you or your closet goes into the search.
- **Nines tells you when a price on your wishlist goes down.** A banner at the top of every
  screen says "A tan rain coat is down to $150.00 at Example Shop, from $177.00.", with **See it**
  (opens the wish) and **Got it**; when several went down it counts them, and **See them** opens
  your wishlist. It says so once: opening the wish or tapping Got it is enough, on your phone or
  your computer alike. It needs Nines to be running, and the demo closet never shows it.
- **Codes at checkout count on your wishlist.** When a shop's page says something like "40% off
  with code TEST40" in its text, Nines picks the code up and the find says "$106.20 with code
  TEST40 at checkout (40% off)" under its price, with "Nines saw this code on the page."; Claude
  reports a code too when it reads a page for a price anyway. You can type one you saw with **Add
  a code** on the find (a percent or an amount off), and remove it there. The price after the
  code is what a price drop, the banner, the wishlist row and "within your price" count, so a code
  that brings the price down is news, and one that goes away is not. A code read from the page
  goes once the page stops showing it; one you typed stays until you remove it. Offers only for
  some people (a first order, new customers, signing up, the app, members) are left out.
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
- **Tennis shoes** and **golf shoes** are kinds of their own, under Shoes & boots in **What is
  it?** and as the kind of shoe in Fix the details, and Claude recognises them when it describes
  a photo. Tennis shoes are drawn as a low court shoe with a rubber guard over the toe and a
  padded collar; golf shoes as a low sneaker on small rubber nubs, or on spikes, and as a derby
  or an oxford when they are cut like one. Like studded boots, they are for their sport: Today
  never puts them in an outfit, not even on an athletic day, and What's missing does not count
  them as everyday sneakers. On a trip they are packed only when you choose to take them, and are
  worn on no day.
- **Tennis or golf on a trip.** Beside "Swimming or the beach", **Playing on the trip** has Tennis
  and Golf. Choose one and a pair of your tennis or golf shoes is packed with the shoes, worn on no
  day, without "I want to take this"; with none that can go, the trip says why.
- **Follow the forecast again.** Once you have turned "Swimming or the beach" on or off, a link
  under it gives the choice back to the forecast.

### Changed

- **Today reads shorter.** The outfit's count ("1 of 3") is gone: the dots, now beside the outfit's heading,
  say it. The line about no forecast keeps only **Try again**; today's temperatures are typed behind
  **Change**. The row about a coming trip names the place, the days and how much is packed, without
  "Packing for a trip?", and the line at the foot about Trips shows only when no trip is coming. A day
  inside a saved trip no longer shows the occasion and mood, which had nothing to change there.
- **Settings, tidied.** **Check now** is back on the main Settings page, under **Updates**, beside
  when Nines last looked, with what it found coming in under the button and **Install now** when
  there is a new version; the version is shown there once, and the separate "This copy of Nines"
  group on Advanced is gone (where your closet is stored is now under **Storage**). Advanced keeps
  only the choice of when updates are installed. **Background removal** no longer shows one
  download address in the open when there are two sets of files: both addresses, each with
  **Save** and **Use default**, and on the computer where each file goes, are in one fold, **If a
  download keeps failing**. **Claude** on Advanced is much shorter: one line saying how Nines
  reaches Claude with **Check again** beside it, a line for your plan and one for the key. With no
  key there is only the box to paste one; with a key, the monthly limit (a short box with Save limit
  beside it) and this month's spending in a few words are in view instead of folded, then **Allow the API key** and **Which to use** as one short
  choice.
- **"Would this work?", a search and a look answer sooner.** Checking a piece against your
  closet takes about a quarter of the time it took, with exactly the same answers. Today's outfits,
  What's missing and a trip's plan are worked out sooner too.
- **Photos or drawings, in words.** The closet's switch between photos and drawings was two small
  pictures. It is now a choice of **Photos** or **Drawings**, in words, at the top of the Filter
  sheet under **Show**.
- **The top of the closet is shorter, and its search finds more.** The line over the grid is one
  line of text that wraps ("5 to check · 4 in the laundry · 2 away"; the away list says which are
  past their day), the search shares its row with Filter without ever shrinking below its word, and
  the filters you have on get a row of their own only when there are any, so a small phone shows two
  rows of smaller pictures at once. The Filter sheet is called "Show and filter". The search finds a piece by its shade
  ("navy"), brand, material ("linen") or a word of your own notes, as well as by its name, what it
  is and its colour; every word you type has to match, in any of those, and accents and capitals
  make no difference.
- **The closet's Filter asks once what a piece is.** Category, Group and Kind were three lists for
  the same question that could be combined into "Nothing matches". Now there is one list, **What it
  is**: choose a group (Trousers & shorts, say) and it opens to what is in it (Jeans, Trousers,
  Shorts, and the kinds your pieces are said to be). One chip says what you chose.
- **Would this work? by hand answers at once.** Choose what kind of piece it is and its main colour,
  and the answer comes straight away, with no long form first and no button to press. Everything else
  (formality, season, how heavy, pattern, rain, a name) is under **More about it**, which opens over
  the page; the answer is worked out again when you close it, and the last one stays on screen,
  dimmed, meanwhile. The answer comes straight under the piece's name, which is said once; under the
  verdict, a line says what it took as usual until you say more ("checked as a plain smart casual
  piece for any time of year").
- **A piece's page says "Saved" beside what you changed.** Changing a piece's name, what it is, its
  brand, price, rating, notes, a detail or its size used to raise a "Saved" message for every change,
  over what you tapped next. Now "Saved" shows for a moment beside the box or row you changed, and
  nothing moves. A message at the top is kept for what went wrong (with "Didn't save" beside the
  box too) and for archiving.
- **A striped or plaid find is drawn striped or plaid.** In **See it with your clothes** and in
  **Would this work?**'s outfits drawn **As worn**, a piece described as striped or plaid is now
  drawn with a plain, typical stripe or plaid in its colour and a quieter shade of it, instead of
  one flat colour. It is a sketch of the pattern, not the product's own, and the line above the
  drawing now says it shows roughly its shape, colour and pattern. Florals, camouflage and prints
  are still drawn in their colour. Your own pieces keep the pattern measured from their photo.

- **A layer under an open coat shows as itself.** On Today's As worn, a cardigan, zip hoodie,
  knit vest, chore jacket or blazer you wear under an open jacket or coat is drawn buttoned or
  zipped, as you would wear it, so its colour, neckline and buttons show between the coat's fronts
  instead of only a strip at the hem. A shirt worn open over a tee stays open, and the coat now
  opens wider over it so you see the shirt inside the coat's fronts. Worn on its own, a cardigan
  or overshirt is still drawn open.
- **The Wardrobe is about half as long.** Each thing worth buying is a closed card: its name, how
  much it helps and one line of why. Tap it to open it in place with everything it showed before.
  "I'll look for this" no longer folds the card and moves the page: the card stays where it is and
  says it is on your wishlist, with Undo. "Tell it how you live" is its title and its two buttons, without a sentence. How
  your clothes are used says each fact once: no heading over a label that repeats it, how long
  you have been recording what you wear said once, and in those words rather than "the wear log".
- **Today's first screen holds the outfit and its button** on the smallest iPhone, with five
  pieces: the pieces are four to a row on a phone, the date sits beside "Today", and when the
  weather cannot be fetched that is one line, "No forecast.", with **Try again** and **Type
  temperatures** instead of a box that said it twice. The weather line keeps **Change** at its
  end instead of moving it to a line of its own when the font is wide.
- **A piece's choices open in a sheet** over the page, from the bottom on a phone (beside the
  piece on a computer), on Today, Worn and a trip, instead of under the pieces where the tab bar
  hid them. On Today the choice is now **Build around this piece** (was Start from this piece),
  the name the page already used everywhere else.
- **Change, beside the weather, opens a sheet** titled Where you are, as in Settings, instead of
  a panel above the outfits. The controls come first; what is sent to look up the weather is one
  tap away. Escape closes it.
- **While Claude chooses again, the outfits stay on the page**, dimmed under "Claude is choosing
  today's outfits…", and keep their space until Claude's are in. Asking again says "Asking
  again…" over the outfits instead of beside the heading.
- **Record an outfit opens a sheet** with the day, a search, and your pieces in four groups (tops,
  bottoms, shoes and extras), the ones worn most recently first, instead of every piece in a long
  panel above the list.
- **A trip leads with what to pack.** The days with something to watch for are one line that
  opens, with days that share a sentence said together, and a forecast that could not be had is
  said once rather than for every day. A day's outfit fits five pieces in one row on a phone.
- **"Not this piece" and "Build around" are kept for the rest of the day**, a reload included.
- **Temperatures are written one way** on Today, Worn and a trip: "9–16°C".
- **The reasons offered after a rating follow it**: after "Loved it" only Got compliments and
  Other, after "Not again" no Got compliments.
- Offline, why rating has to wait is said once above the outfits, not on every one.

- **The wishlist has a page of its own**, one tap from the Wardrobe. Under **Thinking of buying
  something?**, next to **Would this work?**, the **Wishlist** row says how many things are on it
  and how many prices went down, and opens the list with **Add a link** and **Add by hand**. A
  wish's page, and the page a link shared from another app opens, go back to it with
  **‹ Wishlist**, and **Remove from the list** ends there. The Wardrobe page is shorter for it.
  The list, and each wish, now show as soon as the wishes are in, without waiting for what is
  worth buying.
- **A wish's page leads with what you are watching**: the pages you sent first, then what Claude
  found, then one sentence saying Nines checks the price once a day and tells you when it goes
  down, with when it last checked and **Check now** (was Check prices). Find more and Add a link
  come after, then the note. **I found one: would it work?** is now **Would it go with my
  clothes?**, and for a page you sent it starts with the product's name; **Remove** is now
  **Remove from the list**, and a find's **Remove** is **Stop watching**. A find whose price
  changed says what it was and when.
- **One price instead of a range.** A wish's From and To are gone: **Set the most you'd pay**
  opens a sheet with one amount. Nines then tells you only when a price goes down to it or less,
  and Claude's searches stay under it. On the wishlist, a drop to that price or less says "That's
  within your price."
- A shoe now shows the kind Claude named for it under **What is it?** (a chukka boot, a running
  shoe), where before only the kind you chose showed.

### Fixed

- **"I'm wearing this" leaves the outfit where it is.** The card you tapped now says you are wearing it,
  with Undo where the button was, and the other outfits stay behind the dots to wear instead. Nothing
  is put in above the outfits any more, and the page no longer moves under your finger, online or not.
- **Changing an outfit leaves it in place.** "Built around …" and "Without …" (with **Clear all**) are
  said under the outfits, beside "Changing an outfit", instead of in rows put in above the outfit that
  pushed it and its button down.
- **The dots hold still.** The dots that choose an outfit sit in the outfits' heading, so they no longer
  move when the outfit in front is taller or shorter.
- **Offline, Today says it once.** The banner says you are offline; the time the outfits were saved is a
  few words beside the weather, and the line about no forecast is not shown while offline. **I'm wearing
  this** is on the first screen again on a small phone.
- **One message when Today can't be read.** A failed read says so once, in the words every screen uses,
  with one **Try again** that asks again for everything Today waits for. A day ahead names its day
  ("Couldn't load the outfits for tomorrow."). Where the weather goes, it says "The weather isn't known
  yet." rather than a bare label.
- **A day too far ahead says so.** A day more than 60 days ahead, opened from an old address, says "Nines
  dresses days up to 60 days ahead." with the way back to Today, and the days sheet says the same under
  its date box when the date is too far, instead of leaving its button off without a word.
- **Every outfit that counts on a piece says so.** On a day ahead, any outfit that counts on a piece
  being back by then says so under its button, not only the first.
- **A planned day reads as one.** Its heading is "Your plan for Fri", without "the only outfit" under it,
  and offline it is laid out as it is online (four to a row on a phone, "Planned" with Remove the plan).
- **Small fixes on Today.** The row under the button stays on one line on the last outfit ("The best
  one") and once an outfit is kept. The weather line no longer leaves a dot at the end of a line. Try
  again, "Friday is planned.", the line about Trips, the trip's line and the arrow back from a day ahead
  each take a full 44 points to tap. On the narrowest phones "Another day" stays beside the date and the
  weather on one line, so the button is on the first screen. While the outfits are being chosen, what is
  under them already sits where it will be. With too few clothes, Today names only what is still
  missing, once, and offers no other day.
- **The reasons read better.** "The madras plaid shirt is the only pattern." and "The madras plaid shirt
  brings the colour; the rest is neutral." instead of naming the piece's pattern or colour twice, and a
  date in a reason reads as the rest of the app writes one ("on Saturday 14 Nov"). In More numbers on
  the Wardrobe, names in the middle of a sentence start with a small letter.
- **A change made just as a screen opens is no longer shown undone.** A screen that was still
  reading when you changed something (a wish opened from a link and removed at once, say) could
  take the answer it had asked for before the change as the new one: the Wardrobe went on saying
  "On your wishlist" about a wish you had just removed, for up to a minute. A read still on its
  way when a change is made is now dropped and asked again.
- **A copy of Nines that has just started is not taken for the one before it.** After Nines was
  ended without a goodbye (the computer lost power, Windows ended it) and started again, there was
  a moment in which opening Nines could read the new copy as the old one and fail to reach it. A
  copy now says it is running only once the note it keeps about itself is its own.
- **Removing a wish can be undone.** "Remove from the list" on a wish's page takes you back to the
  wishlist, where the wish's place says "You removed …" with **Undo**, which puts it back as it was:
  its finds with their prices and codes, the most you'd pay and its note. It stays until you leave
  the wishlist (and while Nines keeps running).
- **Three more places say a failed read as every screen does.** How much space Nines uses (Advanced,
  Storage), the conversation about your style and a piece's History now say what could not be loaded
  and why in plain words, with **Try again**, instead of the computer's own words (in a toast, for
  History).
- **Would this work?, opened from a wish, goes back to the wish.** Its back link says "‹ Wish" and
  takes you to the wish's page, where you were, instead of to the Wardrobe.
- **A long name heads a wish's page in smaller type.** A wish named after a product's whole name took
  six lines of the largest type on a phone; a long name is now set a size or two smaller, so it keeps to
  about four lines and never runs off the screen.
- **A wish's page holds still and names its find once.** **Check now** says "Checking the price…" in
  place of "Last checked …" instead of putting a line in under it that moved **Find more** and said
  Claude was checking. What a later search finds comes after the finds you have already read. A wish
  made from one product has that product's whole name as its heading, and the find under it starts at
  its shop and price. "See it with your clothes", "Add a code", **Find more**, **I bought it** and
  **Remove from the list** are all 44 pixels high, and so are the periods of **Your nines**.
- **The wishlist's forms open over the list.** **Add a link** and **Add by hand** open in a sheet (a
  small window under the button on a computer) instead of pushing the wishes down; Escape closes it.
- **You might like.** After **Save**, the pick says "On your wishlist" with **Undo** on one line, as
  a suggestion's card does, instead of stacking its buttons. A name beside a hanger has three lines,
  so the kind of piece is not cut off. While it looks, the card keeps the room of three picks, so the
  rest of the Wardrobe does not move down as they come. With an empty closet the card is not shown.
- **Would this work? says what it repeats once, in plain words.** The piece you have like it is said in
  the reasons and shown by its picture, not again under "What it repeats"; "worn three times", not
  "worn three times in the log"; "a good outfit on most kinds of day", not "on 22 of the 40 kinds of
  day the closet is tried on". The same goes for each find on a wish.
- **Offline is said once.** The banner at the top says Nines can't be reached; a trip, the Wardrobe,
  the wishlist, a piece, Settings and Add no longer say it again under it. A trip says "You can still
  tick what you pack.", the Wardrobe and the wishlist "Saved earlier today, at 20:06.", and Add, only
  when photos are still to go, that they carry on by themselves.
- **Trips.** A saved trip's "What to pack" counts what its bar counts ("9 pieces and 3 basics" beside
  "0 of 12 packed"). In Day by day on a phone each day shows its pictures alone (a tap opens a sheet
  that names the piece), with the names whole where there is room, and no longer repeats each day's
  temperature from the strip at the top. "Why these counts" is closed until you open it. The list of
  trips says "1 day has something to watch for", as the trip does. Plan a trip keeps what is sent to
  look up the weather behind "What is sent to look up the weather". When the weather can't be looked
  up for any day, a new trip says so once, with **Try again** and **Type the temperatures** (one low,
  high and rain for each day), and offers neither a packing list of nothing nor Save. A trip's dates
  are written as every other date in the app.
- **Worn, Add and the demo closet.** Removing an outfit you keep counts down under the heading ("2
  kept", back to 3 with Undo). Add no longer says "3 photos are going into your closet." over the list
  headed "Going into your closet". In the demo closet, Add names the strip's own button ("Use Leave,
  above, to add to your own."), and Leave is 44 pixels high.
- **Settings.** "Where you are" opens on its controls, with what is sent to look up the weather
  folded at the end as on Today, and a forecast out of reach no longer offers temperatures the sheet
  has no box for. Backups suggest "a folder your computer copies to the cloud, or a USB drive".
- **The closet no longer opens on an empty laundry or "Needs a check" view.** Left showing the laundry
  after **All clean**, or "Needs a check" after you answered the last check, the closet opened on that
  view with nothing in it ("0 of 49") until you noticed the chip. Like the Away view, it now opens on
  all your clothes, keeping your search and the other filters; "Needs a check" waits for its count to
  arrive before deciding. While you are in the view nothing changes: after **All clean** the line with
  **Undo** stays until you leave. The closet's line no longer says "0 to check".
- **"It's back" no longer moves the rows in the Away view.** The row you tapped changes in place to
  "Back in your closet" with **Undo**, keeping its height, so the next piece's **It's back** stays
  where it was. The list is put in order again when you come back to the view.
- **A long name in the Away view takes two lines,** as on the closet's tiles, and a tap anywhere on a
  row (not only on its small name) opens the piece.
- **Tapping a part of the closet's line shows those pieces.** With a search typed or a kind chosen,
  "2 away" or "4 in the laundry" said "Nothing matches" beside its own count. A tap on the line now
  clears the search and the kind, and shows the pieces it counts.
- **Try again on a piece's page shows the piece.** After a fault, **Try again** asked again only for
  the piece and not for the words the page describes it with, and left an empty grey card. It now asks
  again for both.
- **"When you wore it" is easier to tap.** A tap anywhere on a row, its small pictures included, opens
  that outfit's choices (Wear this again, the days you wore it), as its ⋯ does. The pictures no longer
  open each piece.
- **A piece that is away says where it is first.** On its page, while it is at the cleaner's, at the
  tailor's or lent out, where it is leads the card; "Clean" and **Put in the laundry** are not shown
  until it is back. **Wore it today** stays, and brings it back.
- **A sheet's title and Done stay in sight.** In a long sheet (Filter with a group open, say) the title
  and **Done** stay at the top while what is under them scrolls, in every sheet of the app.
- **Names beside a piece's panel are whole.** On a computer with a piece open beside the closet, the
  narrower tiles show a name on two lines, cut only after a whole word, instead of one line cut in the
  middle of a word.
- **The laundry day leaves your suitcase alone.** What you wear on a trip goes in your suitcase, so the
  laundry day at home no longer marks it clean while the trip is under way. It stays in the laundry
  until the first laundry day after the trip, or until you say it is clean.
- **A wear on a trip that reaches Nines late still counts.** An outfit you marked on the phone on a day
  of a trip, sent once Nines could be reached after a laundry day of that trip, was taken as worn
  before that wash, so it put nothing in the laundry. The laundry day did not wash what was in your
  suitcase, so the wear now counts as any other.
- **A trip packs a piece due back from the cleaner's.** A piece at the cleaner's that you expect back
  before you leave is packed clean, as Dress for another day already counts it, and the plan says it
  counts on it being back. It used to be left out as still in the laundry when the trip was a day or two
  away.
- **Removing an old wear leaves a piece where it is.** Wearing a piece that is away brings it back, and
  removing that wear the same day still sends it away again. Removing it on a later day no longer sends
  it back to the cleaner's.
- **A plan no longer empties Today.** When keeping a piece out of the laundry's way for a planned day
  would leave Today with no outfit, Today offers the outfit anyway and says under it that it uses the
  piece you planned ("This outfit uses your white tee, which you planned for Saturday."). It no longer
  says the piece was left out today.
- **A price check is asked once a day, whatever happens to the answer.** When Claude had answered the
  day's price check or the week's look and Nines then could not keep the answer, Claude was asked the
  same again at every hourly round. Once Claude has answered, the round counts as made.
- **A rating you took away stays away.** A rating your phone kept while Nines was out of reach is turned
  down when you changed the rating on the computer since, also when the change was taking it away.
- **A price that came down while sold out is news once you can buy it.** It used to count as seen if you
  had opened the wish in between.
- **On a trip that packed nothing, Today gives the real reason.** It no longer says nothing you packed
  makes an outfit; it says why nothing in your closet can be worn (everything in the laundry, say).
- **"Blue jeans are back in your closet."** Recording an outfit that brings a pair of jeans, trousers or
  shoes back now says "are", as the rest of Nines does.
- **"Your size is in stock" only while it is said.** On a sale you might like, it goes when the shop's
  page stops listing your size in stock and only the page had said so.
- **Undoing a return keeps the wears since.** Undoing "It's back" for a piece you wore after it came
  back keeps that wear in its count of wears since its last wash.
- **A piece of today's trip that is away at home can be built around.** Its page no longer says "Once
  it's back" for a piece in your bag, which Today on the trip already offers.
- **A day you set the trip aside is not a day of the trip.** Planning a trip again on a day you chose
  "Not on this trip today" no longer takes what you wore at home as the trip's outfit for that day, nor
  puts a piece you left at home on the packing list.
- **A find you stop watching stays put.** On a wish you sent as a link, stopping its find and then
  saving a note (or a price check ending) no longer puts "Added by hand" in above the find and pushes
  it down a line. The wish still came from a link, and says so until you leave the page. After
  **Undo**, its row in the wishlist shows its link and its drop again.
- **The closet no longer opens on an empty Away view.** When you left the closet showing what is
  away and everything has come back since, it opened on that view with "0 away" and "Everything is
  in your closet." until you tapped it off. It now opens on all your clothes, keeping your search
  and the other filters. While you are in the Away view nothing changes: a piece you bring back
  there keeps its row with **Undo**.
- **The closet remembers where you were.** Reloading the page, coming back from a piece (also after
  reloading the piece's page) or coming back from another place keeps the closet's search, its
  filters and your place in the list. The search and filters are in the closet's address.
- **All clean can be undone.** After **All clean** the closet says how many pieces you marked clean,
  with **Undo**, which puts each one back in the laundry as it was (with the wears it had since its
  wash, so the laundry day still washes it when it would have). With the laundry shown and nothing
  in it, the closet now says "Your laundry is empty." instead of "Nothing matches". Showing the
  laundry no longer puts a line in above the search: what to do with those pieces is said under it.
- **Opening a piece on a computer keeps the closet still.** The grid keeps as many pieces to a row
  as before and the piece you chose stays where it was on the screen, instead of the grid folding to
  three across and showing other clothes. The panel has **Close**, Escape closes it, and Back closes
  it too; focus goes into the panel as it opens and back to the piece when it closes.
- **"You might like" and Fix the details say when they could not be read.** In the Wardrobe, "You
  might like" no longer disappears when Nines cannot read it and nothing is kept on this device: it
  says why, with Try again. Fix the details says the same, in the same words, when its details or a
  detail's choices could not be read, instead of a message of its own.
- **Stop watching can be undone.** On a wish's page, a find you stop watching no longer vanishes at
  once: it stays in its place saying so, with **Undo**, which puts it back with its price history and
  its code.
- **Would this work? remembers.** A reload, or your phone closing the app, no longer forgets what you
  described and the answer: they are kept on this device for the rest of the day, until you tap
  **Check another piece**.
- **Choosing a colour no longer chooses a shade for you.** On a piece's page, Colour → Blue used to
  light up "French blue" by itself. Now a colour chosen alone is just that colour: no shade is lit,
  the row says "Blue", and the piece is drawn in plain blue until you choose a shade. What Claude
  described keeps its shade until you change the colour. The swatch on the chosen colour now shows
  on its dark chip.
- **A piece is called one thing on its page.** Until you choose its exact kind, "What is it?" says
  what the line under its name says ("Polo · Tees & polos"), on the piece's page and in the review,
  instead of "Kind not said yet" beside a piece the page calls a polo. On a phone the row's label
  sits above, so the kind and its group have the width (two lines at most), and who said it names
  Claude once ("Claude's guess · 100% sure").
- **A wish made from a link is named at once.** It shows the product's name as soon as Nines has read
  its page, not only when Claude has finished describing it.
- **A trip under way stays as it is.** Opening a trip on its third day no longer says the forecast
  changed when only the days already gone have left the forecast, and "Plan again" no longer dresses
  those days again for "usual" weather they never had. The days gone keep their outfits, the days
  to come are dressed from what you packed, and what you have ticked stays on the list: a tee worn
  yesterday that went in the laundry by itself is still in your suitcase, not swapped for one at
  home.
- **Filling in an outfit from last week leaves the closet alone.** An outfit recorded for a day the
  pieces have been washed since (before Sunday's laundry, or before you marked them clean) goes in
  the log, but no longer sends clean clothes to the laundry as if worn today.
- **Record an outfit takes a tie, a watch, gloves or socks.** Pieces of category Other go with the
  outfit's accessories instead of being refused for having "no category an outfit can use".
- **Record an outfit works from a phone in a later time zone.** When your phone's today is already
  the computer's tomorrow, it is taken as today instead of "That date is in the future".
- **A month away with one wash takes enough sleepwear**: one set for every week of the longest
  stretch between washes, not one set as soon as there is any laundry.
- **Lounge pants you take on a trip stay for the evenings.** "I want to take this" on loungewear
  packs it beside the days, as for tennis shoes, instead of wearing it as the trousers of a day out.
- **A trip day says "the warmest you have" only when it is.** With a warmer coat in the wash at
  home, the jacket is "the warmest you can wear today". Would this work? and a trip's notes speak of
  jeans and shoes as "they".
- Opening a new piece, or one of category Other, no longer writes an error to the log each time.
- **A price typed with a decimal comma is the price you meant.** "45,50" was saved as 4,550 (and a
  wish's most you'd pay "99,50" as 9,950.00) while the page said Saved. Every box that takes a
  price (an item's price, the review card, a wish's most you'd pay, a code's amount off and the
  monthly limit) now reads 45.50, 45,50, 1,234.50, 1.234,50, $45 and spaces alike, and says
  "Type the price as a number, like 45 or 45.50." under the box for what it cannot read, saving
  nothing. On the item page what you typed stays in the box.
- **When Nines on your computer doesn't answer, the screen says so in plain words.** Closet, a
  piece, Worn, Trips, a trip, the wishlist, a wish, Review, Settings and Would this work? used to
  show only "Internal Server Error" (or shimmer for ever). Each now says what couldn't be loaded and
  why (the computer can't be reached, or it answered with a fault), with **Try again**; a screen
  that already showed something keeps it, with one line saying it is from earlier.
- **The banners at the top no longer push the page down.** Price news, an update ready to install
  and what a restore did, when they arrive after a screen has opened, wait for the next screen you
  open. Price news you were already told shows as the page opens. On Add, the two buttons come
  first, the explanation is folded under **What to photograph**, and the notice about cutting the
  clothes out of photos comes after them, so nothing moves the buttons.
- **Dates and times read the same everywhere**: a day as "Mon 23 Nov", a moment as "today at
  04:49" or "yesterday at 21:00", a list's time as "Today, 04:40". History says a shade's name
  ("the shade from navy to hunter green"), never a colour code.
- **Toasts cover less.** They sit at the top of the screen, clear of a sheet's choices and the row
  above the tab bar, and several faults in a row are one toast, not a pile.
- **Keys and sheets.** Escape closes an in-place editor and Today's sheets wherever focus is; in
  Your style it drops only the line you were changing. After Ask Claude in Fix the details, and
  after That's right or Skip for now in the review, focus goes to what comes next. Dragging on the
  dimmed part behind a phone sheet no longer scrolls the page. **How you live** opens as the same
  sheet as everything else, with Cancel beside its title.
- **Smaller things.** The price banner says "Tan suede chukka boots are down…"; Add says "3 photos
  are going into your closet" under "Going into your closet"; Advanced no longer says "model" (the
  files for cutting the clothes out) or "this Mac's keychain" on the phone; a long size in Your sizes
  shows whole on a phone; a trip's weather strip can be scrolled from the keyboard; a screen reader
  hears the Filter button as "Filter, 1 on" and a left-out piece as "Without …, put it back".
- **Text size.** The app's type follows the browser's text size setting (it was fixed in pixels);
  at the default size nothing looks different.
- **Wearing an outfit built around a piece** no longer leaves Today saying "No outfit today yet"
  and offering Add clothes when the piece went in the laundry. Wearing it ends building around the
  piece, and Today shows what you are wearing. When your own changes are why no outfit can be made,
  the button is **Clear your changes**, not Add clothes.
- **The ⋯ button on each Worn card** is drawn at its size again; it was squeezed to a speck.
- **A piece opened from Worn goes back to Worn** with **‹ Worn**, where you left it, instead of
  to Today.
- **"How was yesterday's outfit?"** shows every piece of the outfit on a phone, under the question,
  instead of cutting the last ones off.
- **The outfit card ends with its reasons**: it no longer keeps the height of the tallest outfit,
  which left a blank band of up to 340px.
- A trip's **Why this works** rows are a whole tap high.
- **What you wear at home is no longer a reason to buy.** Worth buying asked for "Another pair of
  trousers like your tartan lounge pants", showed the lounge pants among the pieces a suggestion is
  based on, called a bath robe "your warmest outer layer", let pyjamas stand in for a plain tee, and
  Would this work? said "you have it already" because of lounge pants. Pyjamas, lounge pants and
  robes now count for nothing there, as swim trunks and sport shoes already did, and a search is no
  longer told you love them as everyday clothes. A coat waiting to be mended counts as yours, as one
  in the wash does, instead of bringing "A warm winter coat" onto the list.
- **No second coat or third pair of boots for wearing what you have.** A coat or a pair of shoes
  worn every day of a week no longer asks for "Another coat like your…", and nothing asks for
  another of a kind while one of that kind sits unworn. A heavy down puffer now counts as a warm
  winter coat.
- **Not worn after a break from recording.** If you stop recording what you wear for a few months,
  Not worn no longer lists your whole closet with Archive beside each piece; it says "Nothing has
  been recorded as worn since 20 July 2026." Swim trunks, tennis and golf shoes and what you wear at
  home are no longer listed as not worn.
- **The Wardrobe's sentences read better.** No more "the engine", "it is the only boots you have",
  "only one outfit that differ" or "the only top that suit", and dates read "between 3 and 22
  November 2026" instead of "between 2026-11-03 and 2026-11-22". "Saved earlier" says the day the
  way the rest of the page does ("on 3 Nov").
- **Today's reasons are true of the outfit shown.** On a day the card warns is too cold it no longer
  also says "A single layer on top is enough", nor asks for a middle layer when you own none; suede
  boots are no longer said to "stand up to the rain" beside a warning that the rain spoils them; the
  colour sentence now counts the hat and the scarf, so a mustard beanie is no longer "All neutral
  colours"; and once you set the parka aside, or it is waiting to be mended, the bomber is "the
  warmest you can wear today", not "the warmest you have".
- **Jeans, trousers and shoes are spoken of as a pair**: "The dark jeans are more casual than a
  formal occasion calls for", not "is", on Today and wherever those sentences reach.
- **Cold and wet days dress like a person would.** On a freezing wet day you get the parka and the
  fleece and are told to take an umbrella, where before the thin mac replaced both. At -8°C the
  scarf comes along with the beanie, even when their colours compete, and the card says they are
  for the cold.
- **A sport day is not dressed in jeans and called right for sport.** When nothing made for sport is
  clean, Today says the jeans or the oxford shirt are a makeshift, and puts a tee before a shirt.
  A leather belt is no longer added to joggers, sweatpants or lounge pants.
- **Wear this again works when a piece is waiting to be mended**: the rest of the outfit is kept and
  the place filled, as for a piece in the wash. It also brings back what you wore to tennis, to
  swim or at home, where before it showed no outfit at all.
- **A day that starts cold and gets hot carries one light layer.** Out from 5°C to 28°C, Today no
  longer leaves you in a tee while telling you to take another layer: it adds a light jacket,
  overshirt or thin sweater "for the cool morning", to take off as it warms up.
- **A hot day says when the jeans are too warm.** From a high of 30°C, heavy jeans and trousers say
  so under Be aware and come after the shorts and lighter trousers you have, however much you love
  them.
- A slim shirt with tapered trousers no longer "fights a little": a tapered leg counts as a slim
  one.
- **Check now** says what it found, under the button on Advanced: "Nines 0.15.0 is out." with
  **Install now** beside it, or "You have the latest version." Before, only "Last checked"
  changed there, so a new version looked as though it had not been found. When it finds one in
  **Ask me first**, Nines starts getting it ready at once, so the banner offers it within a
  minute or two instead of up to half an hour later.
- **What's missing comes sooner** when you open the Wardrobe again, or reload it, while Nines is
  still working the list out: it waits for that list instead of starting another beside it, which
  made each one slower. Until you have said how you live, **Find some**, **Check prices** and
  **Would this work?** no longer work the list out again for every search or check; they use the
  one the Wardrobe has, so each is a few seconds quicker.

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
