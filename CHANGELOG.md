# Changelog

What changed for the person using Closet, newest first. Releases are on the
[Releases page](https://github.com/ericksoni716/daily-clother/releases); versions before
0.9.0 are described there only.

Every change the owner can see gets a line under **Unreleased** in the pull request that
makes it: a sentence in plain words about what is different, not about the code. A change
nobody using the app would notice (a refactor, a test, a doc) gets none.

## Unreleased

### Changed

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
