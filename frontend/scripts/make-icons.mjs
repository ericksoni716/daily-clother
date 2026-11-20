// Renders the app icon (nines-icon.svg: an empty dinner jacket in the air, on cream) as PNGs, with the Chromium the
// browser tests already use. Run with `npm run icons`; the output is committed: the web app's icons in public/icons,
// and the icon of the tray and the packaged program in backend/closet/icon.png (closet/tray.py reads it).
// PLAYWRIGHT_CHROMIUM_PATH picks another Chromium, as for the browser tests.
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';

const here = dirname(fileURLToPath(import.meta.url));
const web = join(here, '..', 'public', 'icons');
const program = join(here, '..', '..', 'backend', 'closet');
mkdirSync(web, { recursive: true });

const source = readFileSync(join(here, 'nines-icon.svg'), 'utf8');

// The middle of the jacket and its shadow, in the 512 square (measured from the drawing), so the tab can frame the
// jacket closer.
const FIGURE_CENTRE = [258, 303];

/**
 * The icon at `size` px. `rounded`: the corners cut round and transparent, as the drawing has them; otherwise a full
 * cream square, which is what a phone wants (it rounds the corners itself). `scale`: the jacket and shadow made
 * smaller (to sit inside a maskable icon's safe zone) or larger (for the tab), about the middle of the square.
 */
function svg(size, { rounded = false, scale = 1 } = {}) {
  let s = source.replace(/<!--[\s\S]*?-->/g, '').replace('<svg ', `<svg width="${size}" height="${size}" `);
  if (!rounded) s = s.replace('rx="114"', 'rx="0"');
  if (scale !== 1) {
    // smaller: about the middle of the square; larger: the jacket's own middle moved to the middle of the square
    const [cx, cy] = scale < 1 ? [256, 256] : FIGURE_CENTRE;
    s = s.replace('<g id="figure">', `<g id="figure" transform="translate(256 256) scale(${scale}) translate(${-cx} ${-cy})">`);
  }
  return s;
}

const files = [
  [join(web, 'apple-touch-icon.png'), 180, {}],
  [join(web, 'icon-192.png'), 192, {}],
  [join(web, 'icon-512.png'), 512, {}],
  // the safe zone is the middle 80%: the jacket and its shadow stay inside it whatever shape the phone cuts
  [join(web, 'maskable-512.png'), 512, { scale: 0.84 }],
  // a tab is small: the jacket drawn as large as the rounded square allows
  [join(web, 'favicon-32.png'), 32, { rounded: true, scale: 1.3 }],
  [join(program, 'icon.png'), 1024, { rounded: true }],
];

const executablePath = process.env.PLAYWRIGHT_CHROMIUM_PATH || undefined;
const browser = await chromium.launch(executablePath ? { executablePath } : {});
try {
  const page = await browser.newPage();
  for (const [path, size, options] of files) {
    await page.setViewportSize({ width: size, height: size });
    await page.setContent(`<!doctype html><style>html,body{margin:0;background:transparent}svg{display:block}</style>${svg(size, options)}`);
    writeFileSync(path, await page.screenshot({ omitBackground: true, clip: { x: 0, y: 0, width: size, height: size } }));
  }
} finally {
  await browser.close();
}
console.log(`wrote ${files.length} icons`);
