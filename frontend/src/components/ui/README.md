# The shared pieces

Every screen is built from these and the tokens in `src/styles.css`. Before writing a new
piece, a new class or a new value, look here: if something close exists, use it or change it
here, once, for every screen. A new colour, size, radius, button style or motion value is a
change to the design system, written down in `docs/DECISIONS.md` ("The design system"), not
something a screen brings with it. `src/design.test.ts` fails on a size, radius, colour or
motion value that is not a token; `e2e/17-accessibility.spec.ts` runs axe over the screens.

All of them are exported from `index.ts`. They style themselves with `:where()` (no weight),
so a screen's own class can still set size and spacing.

## Pieces

| Piece | What it is for |
| --- | --- |
| `PageHeader` | The top of every screen: the title, an optional count beside it, at most one line under it, a back link (`back={{ to, label }}`, drawn as "‹ Label" and going Back in history), and at most one main button. Use it rather than a hand-made header. |
| `BackLink` | A "‹ Somewhere" link outside a header (the item page's). It goes Back when the page before is the one it names, otherwise it takes this page's place. |
| `Section` and `Card` | A surface with the app's one depth; `Section` adds a heading, a one-line hint and an action beside the heading. |
| `Button`, `buttonClass` | Every button, and a link that looks like one. Variants: primary, secondary (the default), ghost, link, danger-quiet; `small`, `block`. |
| `ItemThumb` | An item's small picture on its light card, optionally a link to the item. Every list of pieces uses it, at the size the screen's class gives it. |
| `ChipGroup` | A row of chips for one detail, with colour swatches where they help (the colour words' own, or a colour given for each option, as for a colour's shades). |
| `SegmentedControl` | Two to four choices of which one is on (Pieces / As worn, Photos / Drawings). |
| `Sheet` (and `PHONE`) | Choices that do not fit in place: a sheet from the bottom on a phone, a popover or in place on a computer. Never a panel put in above the content. Escape closes the latest one open wherever focus is (call `preventDefault` on an Escape you take for yourself inside it), and a phone sheet holds the page behind it still. Its title and Done stay at its top while its body scrolls. Its button beside the title says Done, or `closeLabel="Cancel"` over a form that saves only with its own button. Opened from inside something that clips what it holds (a carousel's slide, a card), give it `anchor` (the button that opened it): it is put at the end of the page and floats beside that button on a computer. |
| `Notice` | A message set apart: information, a warning or an error, with an optional action. |
| `EmptyState` | What a screen shows with nothing yet: an icon, a title, one sentence, one button. |
| `Fold` | Something closed until it is wanted ("More numbers", "Hidden (2)"). `lazy` draws its insides only once opened. Use it instead of a bare `<details>`. |
| `ShowMore` | A list that shows its first few on a phone (`first`; `wide` on a computer), then "See all N", which opens the rest in place or goes to a page with the whole list (`to`). |
| `HowItWorks` | The one closed-by-default explanation on a screen ("How this works", "Changing an outfit"). It replaces hint paragraphs that would otherwise be read on every visit. |
| `SaveStatus` and `useSaveStatus` | "Saving… / Saved / Didn't save · Try again" beside something that saves as it is changed. The line keeps its height, so nothing moves when it speaks. `useSaveStatus().run(save)` drives it; `retry` runs the last save again. |
| `Markdown` | A small, safe part of Markdown (the release notes), drawn as elements, never as HTML. |
| `Failed` | What a screen shows when a read fails: give it the query and what it reads (`what="your closet"`). With nothing read before, "Couldn't load your closet." with why in plain words (the computer can't be reached, it answered with a fault) and Try again; with an earlier answer, one line above it saying it is from earlier. Draws nothing until the read fails, so put it where the content goes. A screen that waits for two reads gives it both as one, `readsOf(a, b)`, so Try again asks again for each. Never print a read's `error.message` yourself. |
| `ErrorBoundary` | The message in place of a screen that failed to draw, with Try again and Reload Nines. |
| `trapTab`, `confirmKeys`, `useConfirmFocus` | Keeping Tab inside what is open, Escape to close, focus back to what opened it. |

## Tokens (`src/styles.css`, `:root`, with the dark values below them)

- **Text:** `--ink`, `--ink-2`, `--ink-3` for words; `--ink-4` for decoration only (too faint
  for words). `--label-ink` with `--font-label` for the small capital labels; `--ink-tone`
  for Today's date.
- **Surfaces:** `--bg`, `--surface`, `--surface-raised`, `--surface-2`, `--inset`; item
  pictures sit on `--card` (light in both themes). Borders are see-through ink:
  `--line-soft`, `--line`, `--line-strong`.
- **Meaning:** `--accent` (and `--accent-bg`, `--accent-ink`, `--accent-soft`), `--danger`
  (`--danger-soft`), `--warn` (`--warn-soft`). Tints (`--tint-green`, `--tint-sand`,
  `--tint-coral`) are for a few sections that mean something (Why this works, the question
  about yesterday), not for decoration.
- **Type:** in rem, so the browser's text size scales it; at the default size `--text-xs` 12,
  `--text-sm` 14, `--text-md` 16, `--text-lg` 20, `--text-xl` 25, `--text-2xl` 31, `--text-3xl` 39
  (page titles on a computer); `--weight-body`,
  `--weight-label`, `--weight-heading`.
- **Space and shape:** `--space-1` to `--space-8` (4, 8, 12, 16, 20, 24, 32, 48);
  `--radius-sm` 8, `--radius-md` 14, `--radius-lg` 20, `--radius-pill`; `--tap` 44px, the
  least anything tappable is on a phone; `--content-w` for a one-column page.
- **Motion:** `--ease-out`, `--dur-quick` (a press, a small change), `--dur-move` (something
  arriving); a press dims to `--press-dim` after `--press-delay`. Nothing moves when the
  device asks for reduced motion.

## Shared classes worth knowing

`.hint` (one line under a heading), `.muted`, `.chip` and `.chips`, `.chip-group-title` (a
small capital label), `.btn-link`, `.notice`, `.spinner`, `.tile-skeleton`, `.visually-hidden`,
`.master-detail` and `.detail-panel` (a list with a panel beside it on a computer).
