# Design principles

What makes a change to Nines feel like the rest of it. Read this before adding a screen, a
card or a sentence, and use the checklist at the end on every change. What each screen does
today is in [USING.md](USING.md); how the code is laid out is in
[DEVELOPING.md](DEVELOPING.md); the review these principles come from is
[assessment/README.md](assessment/README.md).

## Who it's for

One person, with their own wardrobe, who opens the app on an iPhone most days and on the
computer it runs on now and then. They photograph what they own once, want to type as little
as possible, dislike long pages and repeated text, and never see Python or a terminal.

The jobs, in order of how often each comes up:

1. What do I wear today? (ten seconds, on the phone)
2. I wore this, and this is how it went. (one tap; a rating later)
3. Get new clothes in. (a few photos; the rest happens by itself)
4. Find a piece, look at it, put right what the app got wrong.
5. What should I buy, and would this one work?
6. What do I pack?
7. Keep it running. (updates, backups, the phone's address, Claude: invisible when they work)

Every screen answers one of these. Something that answers none is a report, and a report is
folded into the screen whose job it serves.

## Principles

1. **Lead with the answer.** Today opens on an outfit, not on the controls that shape it.
   What's missing opens on the few things most worth buying. A screen's first phone screen
   holds what it is for; the reasons and the figures are one tap away.
2. **One thing, one home.** A fact is stored once, shown in one place and edited there.
   Anywhere else that needs it links to it. The same sentence on two screens means one of
   them should go. A setting is in Settings or beside what it changes, not both.
3. **The page holds still.** Nothing arrives and pushes down what you were reading or about
   to tap. A screen waits for what it needs and then shows everything at once. Something
   that comes later has its space kept for it. Choices that do not fit in place open in a
   `Sheet` over the page, never as a panel put in above the content.
4. **Work in the background is said once, in one place.** A photo is cut out, described and
   drawn without being watched. One line says how much is still being worked on; each item
   carries one state in one set of words. A wait of minutes says so before it starts.
5. **Reading load is a budget.** A phone screen of text is about 150 words; a whole screen
   stays under about 350 on a phone. A hint under a heading is one line. An explanation goes
   behind one closed thing to open, not into the page. Something that is true every day
   ("your closet is safe") is not said every day.
6. **Ask in conversation, not in forms.** What the app cannot learn from the clothes and the
   wears, it asks when it matters, one question at a time, and remembers the answer. What you
   tell Claude about your style is kept as lines you can read and remove. A long form is the
   last resort.
7. **Say what the app doesn't know.** A guess is marked as one and can be put right in a tap.
   "Nothing to compare with yet" beats a wrong number. When the weather, Claude or the
   computer cannot be reached, the screen says which, once, and still shows what it has.
8. **The phone is the app; the computer is where it lives.** Every screen fits at 375px with
   long names in it. What only makes sense on the computer (the phone's QR code, start at
   login, folders, Quit) is not offered on the phone.
9. **Nothing is lost by a slip.** Changes save as you make them and say so. What removes
   something can be undone or asks first. Claude offers and the owner decides: something to
   remember is kept on a tap, never by itself.
10. **One system.** Sizes, colours, radii, spacing and motion are the tokens in
    `frontend/src/styles.css`; shared pieces come from `frontend/src/components/ui/`;
    `design.test.ts` and the accessibility test fail on anything else. A new colour, size,
    button style or motion value is a change to the system, decided once and written down in
    DECISIONS ("The design system"), not something a screen brings with it.

## Writing

Plain words, second person. A sentence rather than a label with a colon. No exclamation
marks. No word the owner has not been shown: "background removal" needs "cutting the clothes
out of the photo" beside it the first time, and "model", "route", "token" and "tag" stay out
of the page.

Name things the way the page already names them. Before writing a status or a button, search
`frontend/src/` for the one in use: it is "Claude is describing it", not a new phrase for the
same step.

To make something shorter, drop a sentence rather than squeeze one into a fragment. A line
has to make sense to someone reading it cold.

Amounts, dates and counts go through the helper that already formats them (`spend.ts` for
money, `wears.ts` for days, `labels.ts` for the vocabulary), so "3 wears" and "Thursday" read
the same everywhere.

## Screens

A screen is a `PageHeader` (a title, at most one main button), then `Section`s in the order
they are used, and an `EmptyState` when there is nothing yet: an icon, a title, one sentence,
one button.

The app has four places and Add: Today (with Worn and Trips one level down), Closet (with
the review and Archived), Wardrobe (what to buy and how the closet is used, with Would this
work?, the wishlist and each wish one level down) and Settings (with Advanced). Everything is
two taps or fewer from the tab bar. A new thing is first a card, a fold or a sheet on the
screen whose job it serves; a page one level down comes next, inside its place (lit as that
place, with a "‹ Place" back link). A new place in the tab bar needs a reason none of the four
can hold.

On a page that has grown, the shared pieces keep it short: `ShowMore` shows the first few on
a phone, `Fold` keeps what is occasional closed ("More numbers"), and `HowItWorks` holds the
one explanation a screen needs, closed by default. `components/ui/README.md` lists them all.

Moving between screens has no animation of its own; the phone's swipe back already has one.
Going back returns to where you were, at the scroll position you left.

## Motion and touch

One curve and two lengths (`--ease-out`, `--dur-quick`, `--dur-move`), only where they
explain a change: something arriving or leaving. Nothing moves when the device asks for
reduced motion, except the spinner. A press is shown by a change of tone, not of size: on a
touch screen what you pressed dims a moment after your finger lands.
Anything tappable is at least 44px on a phone, with an invisible hit area if it looks
smaller.

## Drawings

The drawing rules are in `AGENTS.md`, "Drawing in 3D". A drawing is checked by looking at
the render at phone size and close up, not by its tests.

## The review loop

```
cd frontend && npm run build && npm run phone-check
```

Then open the pictures in `frontend/phone-shots/` with this file beside them. See "The phone
check" in [DEVELOPING.md](DEVELOPING.md).

## Checklist for any change

- Which job does it serve, and on which screen? If it is a new screen, why not a card or a
  sheet on an existing one?
- What is in the first phone screen, and is that the answer?
- Is each fact shown once and edited in one place? Did you search for the sentence, the
  status word and the helper before writing a new one?
- Does anything arrive late and move the page? Does a tap put anything in above the content?
- What does it show while it waits, when there is nothing yet, when the answer is a guess,
  and when the weather, Claude or the computer cannot be reached?
- Is it under the word budget? Is each hint one line? (The phone check prints each screen's
  words and lists the ones over.)
- Does it make sense on the phone, and is anything computer-only hidden there?
- Can it be undone, or does it ask first?
- Tokens and `components/ui/` only? At least 44px to tap?
- Does it fit at 375px with long names? Did you look at the phone check's pictures, light
  and dark?
- `USING.md` and `CHANGELOG.md` updated; `README.md` if what the owner does changed;
  `DECISIONS.md` if you made a choice someone could have made differently; the checks in
  `AGENTS.md` pass?

Some screens do not meet these principles yet. The assessment lists where, and its order of
work is how they get there; a change should leave its screen closer, not further.
