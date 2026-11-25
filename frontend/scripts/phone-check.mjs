// Opens every screen at five iPhone sizes, fails if any is wider than the screen or throws,
// and saves screenshots to look through.
//
//   node frontend/scripts/phone-check.mjs [out-dir]        (or `npm run phone-check` in frontend/)
//
// It starts its own backend with a fresh, empty data folder on a free port, so it never
// touches a real closet: the owner's closet starts as a copy of the demo closet, and the
// folder is removed at the end. It needs the built page (`npm run build` in frontend/).
// Long names are given first, because long real names are what break phone layouts.

// overflow(), scrollThrough() and the start-up script run inside the page, where these exist.
/* global document, window, NodeFilter */
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readdirSync, rmSync } from 'node:fs';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium, devices, request } from '@playwright/test';

const BACKEND_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', 'backend');
const OUT = resolve(process.argv[2] || 'phone-shots');
// 375 is the narrowest the app supports; 402 and 440 are the iPhone 17 Pro and Pro Max (Playwright has
// both; if an older Playwright doesn't, the 15 Pro and Pro Max at 402×874 and 440×956 stand in).
const at = (name, fallback, width, height) => devices[name] ?? { ...devices[fallback], viewport: { width, height: height - 193 }, screen: { width, height } };
const ALL_PHONES = [
  ['375', devices['iPhone 13 Mini']],
  ['393', devices['iPhone 15']],
  ['402', at('iPhone 17 Pro', 'iPhone 15 Pro', 402, 874)],
  ['430', devices['iPhone 15 Pro Max']],
  ['440', at('iPhone 17 Pro Max', 'iPhone 15 Pro Max', 440, 956)],
];
// PHONE_CHECK_SIZES=393 (a comma list) pictures only those widths, for a quicker look while working. 320 (the first
// iPhone SE) is pictured only when named: narrower than the 375 the app is made for, it shows what gives way first.
const ONLY = (process.env.PHONE_CHECK_SIZES || '').split(',').map((s) => s.trim()).filter(Boolean);
const NARROW = [['320', devices['iPhone SE']]];
const PHONES = ONLY.length ? [...NARROW, ...ALL_PHONES].filter(([size]) => ONLY.includes(size)) : ALL_PHONES;
// PHONE_CHECK_TEXT=125 sets the page's text size to 125% (as a larger text size in the browser does), to check that
// the type scale, which is in rem, still fits every screen; its pictures are named t125-….
const TEXT = Number(process.env.PHONE_CHECK_TEXT || 100);
const PREFIX = TEXT === 100 ? '' : `t${TEXT}-`;
// The reading budget in docs/DESIGN.md ("Reading load is a budget"): about 150 words in the first phone screen, about
// 350 on the whole screen. Counted at 393px in light; a screen over either is listed, but does not fail the check yet.
// What is counted is what a phone shows when the page opens, scrolled through: not what is out of reach by design
// (`inert`, `aria-hidden`, `hidden`, a closed fold, words for a screen reader only, words a phone hides). Today's two
// outfits behind the dots are not counted; the one in front is.
const BUDGET = { screen: 150, page: 350 };
const COUNTED_AT = '393';
// Made-up names, long on purpose.
const LONG = {
  item: 'Heavyweight brushed cotton flannel overshirt in faded forest green and charcoal buffalo check',
  place: 'Upper Wickhamstead-under-Lyme-on-the-Marsh, Greater Fenwold Coastal District, Nowhereshire',
  wish: 'A lightweight packable waterproof shell jacket with a hood that folds into the collar',
  line: 'Never anything double-breasted, never anything with a crest or a logo-embroidered-chest-pocket-of-any-kind',
};
// Sheets opened by a button on a screen, pictured as well: the style conversation, every line of Your style, an
// item's colours with the shades of its colour, a wish's most you'd pay, its find's checkout code, a find seen with
// your clothes, and on Today, Worn and a trip: a piece's choices, where you are and today's temperatures, the days to
// dress for (Another day), a worn or kept
// outfit's choices, Record an outfit, and a packed piece's choices. `route` can be worked out from the ids `setUp` gives; `fold` is opened first when the button is inside
// one; `wait` is what to wait for inside the sheet before its picture is taken.
const SHEETS = [
  { route: '/settings', button: 'Talk to Claude about your style', sheet: 'style-talk-sheet', name: 'settings-style-talk' },
  { route: '/settings', button: /^(See all lines|Change the lines)$/, sheet: 'style-lines-sheet', name: 'settings-style-lines' },
  { route: '/settings', button: 'Change your sizes', sheet: 'sizes-sheet', name: 'settings-sizes' },
  { route: '/settings', button: 'Change the shops you like', sheet: 'shops-sheet', name: 'settings-shops' },
  { route: ({ itemId }) => `/item/${encodeURIComponent(itemId)}`, fold: 'Details', button: /^Colour:/,
    sheet: 'detail-editor-color', name: 'item-colour' },
  { route: ({ linkedId }) => `/wardrobe/wish/${encodeURIComponent(linkedId)}`, button: "Set the most you'd pay",
    sheet: 'price-sheet', name: 'wish-price' },
  { route: ({ linkedId }) => `/wardrobe/wish/${encodeURIComponent(linkedId)}`, button: 'Change the code',
    sheet: 'code-sheet', name: 'wish-code' },
  { route: ({ linkedId }) => `/wardrobe/wish/${encodeURIComponent(linkedId)}`, button: 'See it with your clothes',
    sheet: 'worn-sheet', name: 'wish-worn', wait: '[data-testid="outfit-figure"] img' },
  { route: ({ itemId }) => `/item/${encodeURIComponent(itemId)}`, button: 'Change where it is', sheet: 'where-sheet', name: 'item-where' },
  { route: '/', button: /^\d+ away/, sheet: 'away-view', name: 'closet-away' },
  { route: '/', button: /^Filter/, sheet: 'filter-sheet', name: 'closet-filter' },
  { route: '/today', button: /^Choices for/, sheet: 'piece-sheet', name: 'today-piece' },
  { route: '/today', button: /^Change$/, sheet: 'day-sheet', name: 'today-day' },
  { route: '/today', button: 'Another day', sheet: 'another-day-sheet', name: 'today-another-day' },
  { route: '/today/worn', button: 'More for this outfit', sheet: 'worn-menu', name: 'worn-menu' },
  { route: '/today/worn/kept', button: 'More for this outfit', sheet: 'kept-menu', name: 'kept-menu' },
  { route: '/today/worn', button: 'Record an outfit', sheet: 'record-sheet', name: 'worn-record' },
  { route: ({ tripId }) => `/trips/${encodeURIComponent(tripId)}`, button: /^Choices for/, sheet: 'trip-menu', name: 'trip-piece' },
  { route: '/settings', button: /^(Tell it how you live|Edit my answers|See example answers)$/, sheet: 'life-sheet', name: 'settings-life' },
];
// Screens whose read fails (Nines answers with a fault), pictured with what they say: the closet with nothing read
// before, and a trip, which has the copy kept on this device to show as from earlier.
const FAILED = [
  { route: '/', fail: '**/api/items?*', name: 'failed-closet' },
  { route: ({ tripId }) => `/trips/${encodeURIComponent(tripId)}`, fail: '**/api/trips/*', name: 'failed-trip' },
];
// Views switched on a screen, pictured as the part that changes: You might like's On sale.
const VIEWS = [
  { route: '/wardrobe', button: 'On sale', part: 'section.picks', wait: '[data-testid="pick-price"]', name: 'wardrobe-on-sale' },
];
// A made-up shop's page with a long product name, which the backend's stand-in serves (never the web).
const SHOP_PAGE = 'https://shop.example/long-name';
// A made-up place: the weather is given with the trip, so its coordinates are never looked up.
const PLACE = { name: LONG.place, latitude: 50, longitude: 0, timezone: 'Europe/London' };

// The next three are what frontend/e2e/server.ts (startBackend) does. That file is TypeScript and a
// plain .mjs cannot import it, so the little that is needed is repeated here.
function freePort() {
  return new Promise((res, rej) => {
    const srv = createServer();
    srv.unref();
    srv.on('error', rej);
    srv.listen(0, '127.0.0.1', () => {
      const addr = srv.address();
      srv.close(() => res(typeof addr === 'object' && addr ? addr.port : 0));
    });
  });
}

/** The backend the browser tests use (backend/tests/e2e_backend.py): the weather service and Claude are out of reach or stand-ins. */
async function startBackend() {
  const port = await freePort();
  const dataDir = mkdtempSync(join(tmpdir(), 'closet-phone-'));
  const child = spawn(process.env.CLOSET_PYTHON || 'python', ['-m', 'tests.e2e_backend', '--no-browser', '--no-tray', '--port', String(port)], {
    cwd: BACKEND_DIR,
    env: {
      ...process.env, CLOSET_DATA_DIR: dataDir, CLOSET_PORT: String(port), CLOSET_NO_AUTO_DOWNLOAD: '1',
      CLOSET_E2E_FAKES: '1', CLOSET_E2E_SEED: 'demo',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let log = '';
  child.stdout.on('data', (d) => (log += d));
  child.stderr.on('data', (d) => (log += d));
  const backend = {
    url: `http://127.0.0.1:${port}`,
    async stop() {
      if (child.exitCode === null && child.signalCode === null) {
        const exited = new Promise((r) => child.once('exit', r));
        child.kill('SIGTERM');
        await Promise.race([exited, new Promise((r) => setTimeout(r, 5000))]);
        if (child.exitCode === null && child.signalCode === null) child.kill('SIGKILL');
      }
      rmSync(dataDir, { recursive: true, force: true });
    },
  };
  const deadline = Date.now() + 60_000;
  for (;;) {
    if (child.exitCode !== null) {
      await backend.stop();
      throw new Error(`The backend exited early:\n${log}`);
    }
    try {
      if ((await fetch(`${backend.url}/api/health`)).ok) return backend;
    } catch {
      /* not up yet */
    }
    if (Date.now() > deadline) {
      await backend.stop();
      throw new Error(`The backend did not start within 60 s:\n${log}`);
    }
    await new Promise((r) => setTimeout(r, 250));
  }
}

function localDay(offset) {
  const day = new Date();
  day.setDate(day.getDate() + offset);
  return `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`;
}

/** Gives things long names, and returns the browser state to reuse in every browser. */
async function setUp(base) {
  const api = await request.newContext({ baseURL: base, extraHTTPHeaders: { 'X-Closet-Client': '1' } });   // as the page's own calls
  try {
    const call = async (route, method = 'GET', data) => {
      const res = await api.fetch(route, { method, data });
      if (!res.ok()) throw new Error(`${method} ${route}: ${res.status()} ${await res.text()}`);
      return res.status() === 204 ? null : res.json();
    };
    const { items } = await call('/api/items?status=active');
    if (!items.length) throw new Error('The closet copied from the demo has no clothes.');
    const item = items[0];
    await call(`/api/items/${encodeURIComponent(item.id)}`, 'PATCH', { name: LONG.item });
    // Where a piece is: the long-named one at the cleaner's with a long note, and another lent out and past its day, so
    // its page, the closet's line and the away view show each kind of sentence
    await call(`/api/items/${encodeURIComponent(item.id)}/away`, 'PUT',
      { place: 'cleaner', until: localDay(4), note: 'Ask them to look at the small stain near the left cuff, and the hem' });
    const lent = items.find((i) => i.id !== item.id && i.category === 'jacket') ?? items[1];
    await call(`/api/items/${encodeURIComponent(lent.id)}/away`, 'PUT', { place: 'lent', since: localDay(-12), until: localDay(-3) });
    // a shoe's page as well: its photos and drawings make it the longest item page
    const shoe = items.find((i) => ['sneakers', 'boots', 'dress_shoes', 'sandals'].includes(i.category)) ?? item;
    // Made-up prices and dates bought on a few pieces (the demo closet has prices and no dates), so the Wardrobe's line
    // on what your clothes cost has a year to tell
    const year = new Date().getFullYear();
    const bought = [[18900, `${year}-02-14`], [6500, `${year}-05-03`], [12000, `${year}-09-21`], [24500, `${year - 1}-10-30`],
      [4500, `${year - 1}-04-12`]];
    for (const [i, [cents, day]] of bought.entries()) {
      const piece = items[i + 1];
      if (piece) await call(`/api/items/${encodeURIComponent(piece.id)}`, 'PATCH', { price_cents: cents, acquired_on: day });
    }
    // A trip asks the weather service for its forecast unless the weather is given, so it is given: mild and dry.
    const first = localDay(10), last = localDay(13);
    const weather = [];
    for (let i = 10; i <= 13; i++) weather.push({ date: localDay(i), low_c: 9, high_c: 17, rain: false });
    const trip = await call('/api/trips', 'POST', { place: PLACE, first_day: first, last_day: last, weather });
    // A wish by name needs neither the weather nor Claude.
    const wish = await call('/api/wishlist', 'POST', { name: LONG.wish });
    // A wish from a link: the backend's made-up shop page with a long name and a checkout code in its banner
    // (tests/e2e_backend.py, ShopPages, never the web), read once and then again a little cheaper, so the wishlist's row
    // says the price went down, with the code.
    const linked = await call('/api/wishlist/link', 'POST', { url: SHOP_PAGE });
    const settled = async () => {
      for (let i = 0; i < 80; i++) {
        const { run } = await call(`/api/wishlist/${encodeURIComponent(linked.id)}/finds`);
        if (run && run.state !== 'running') return;
        await new Promise((r) => setTimeout(r, 250));
      }
      throw new Error('The link was not read.');
    };
    await settled();
    // The demo closet's own drops are news in a copy of it: marked seen, so the banner tells only the link's drop. It
    // shows on the first screens pictured until the link's page is opened (which marks it seen), and the reading is
    // counted without it.
    const { news } = await call('/api/wishlist/news');
    await call('/api/wishlist/news/seen', 'POST', { wish_ids: news.map((n) => n.wish_id) });
    await call(`/api/wishlist/${encodeURIComponent(linked.id)}/prices`, 'POST');
    await settled();
    // Your style: an answer to a question, a long line of your own, and a message to Claude (the stand-in answers it in
    // a second and a half, with a line to keep), so Settings and the conversation show each kind of line
    await call('/api/style/questions/warmth', 'POST', { choice: 'I run warm' });
    await call('/api/style/lines', 'POST', { text: LONG.line });
    await call('/api/style/talk', 'POST', { say: 'I always feel warm on the bus, even in winter' });
    for (let i = 0; i < 40 && (await call('/api/style/talk')).answering; i++) await new Promise((r) => setTimeout(r, 250));
    // You might like: one look (the backend's stand-in answers in a second, with long names), so the Wardrobe's card
    // shows its three picks
    await call('/api/picks/look', 'POST');
    for (let i = 0; i < 400 && (await call('/api/picks')).run?.state === 'running'; i++) await new Promise((r) => setTimeout(r, 250));
    // ...and one look for things on sale (its made-up pages read by the real reader), so its view shows three, and
    // shops you like with long names
    await call('/api/picks/look?kind=sale', 'POST');
    for (let i = 0; i < 400 && (await call('/api/picks')).run?.state === 'running'; i++) await new Promise((r) => setTimeout(r, 250));
    for (const name of ['Example Outfitters of Unreasonably Long Names', 'small-maker-with-a-long-site.example', 'Example Shop']) {
      await call('/api/shops', 'POST', { name });
    }
    // Your sizes: each kind's as long as a size may be but one (the rest is offered from the closet's own), and a brand
    // with a long name that fits differently
    await call('/api/sizes/tops', 'PUT', { size: 'XL Tall (EU 54/56)' });
    await call('/api/sizes/trousers', 'PUT', { size: '34W x 32L, relaxed' });
    await call('/api/sizes/shoes', 'PUT', { size: '10.5 US / 44 EU wide' });
    await call('/api/sizes/tops/brand', 'PUT', { brand: 'Example Brand of Long-Named Outerwear', size: 'XXL Tall (EU 58)' });
    return { state: await api.storageState(), itemId: item.id, shoeId: shoe.id, tripId: trip.id, wishId: wish.id, linkedId: linked.id };
  } finally {
    await api.dispose();
  }
}

/** How much wider than the screen the page is, and which elements stick out. */
function overflow() {
  // The page clips sideways (styles.css, body { overflow-x: hidden }), which would hide what sticks out: lift it to measure.
  const roots = [document.documentElement, document.body];
  roots.forEach((el) => el.style.setProperty('overflow-x', 'visible'));
  const width = document.documentElement.clientWidth;
  const extra = document.documentElement.scrollWidth - width;
  const culprits = [];
  if (extra > 1) {
    for (const el of document.querySelectorAll('body *')) {
      const r = el.getBoundingClientRect();
      if (r.right > width + 1 && r.width > 0 && !el.closest('svg')) {
        const cls = typeof el.className === 'string' ? el.className.split(' ').slice(0, 6).join(' ') : '';
        culprits.push(`${el.tagName.toLowerCase()}.${cls} (${Math.round(r.right)}px)`);
        if (culprits.length >= 5) break;
      }
    }
  }
  roots.forEach((el) => el.style.removeProperty('overflow-x'));
  return { extra, culprits };
}

/**
 * How much there is to read on the screen: the words a phone shows in the page (not the tab bar or the sidebar), the
 * words in the first phone screen (what shows above the tab bar before scrolling), and the page's height. A word is
 * counted when it is drawn: not inside something `inert`, `aria-hidden` or `hidden`, not in a box of a pixel or less
 * (words for a screen reader only, a layer's name a phone hides), not in a closed fold. Runs inside the page.
 */
function measure() {
  const root = document.querySelector('main') ?? document.body;
  const tabbar = document.querySelector('nav.tabbar');
  const fold = tabbar ? tabbar.getBoundingClientRect().top : window.innerHeight;
  const count = (text) => (text.match(/[\p{L}\p{N}][\p{L}\p{N}'’.-]*/gu) ?? []).length;
  let words = 0;
  let first = 0;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const el = node.parentElement;
    if (!el || !node.textContent?.trim()) continue;
    const style = window.getComputedStyle(el);
    if (style.visibility === 'hidden' || style.display === 'none' || el.closest('[hidden], [inert], [aria-hidden="true"], .visually-hidden')) continue;
    const box = el.getBoundingClientRect();
    if (box.width <= 1 || box.height <= 1) continue;
    // inside a closed fold (but not its summary, the line you tap to open it): the browser still lays it out
    let folded = false;
    for (let at = el; at && at !== root; at = at.parentElement) {
      const fold = at.parentElement;
      if (fold && fold.tagName === 'DETAILS' && !fold.open && at.tagName !== 'SUMMARY') folded = true;
    }
    if (folded) continue;
    const range = document.createRange();
    range.selectNodeContents(node);
    const r = range.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    const n = count(node.textContent);
    words += n;
    if (r.top + window.scrollY < fold) first += n;
  }
  return { words, first, height: document.documentElement.scrollHeight };
}

/** Waits until the screen has its heading and has stopped fetching, up to a few seconds each. */
async function settle(page) {
  await page.locator('h1').first().waitFor({ state: 'visible', timeout: 10_000 }).catch(() => undefined);
  // The app keeps polling a few things, so the network is not always quiet; don't wait for it forever.
  await page.waitForLoadState('networkidle', { timeout: 6_000 }).catch(() => undefined);
  await page.waitForTimeout(400);
}

/** Scroll to the bottom and back, so cards that animate in as you scroll are showing. */
async function scrollThrough(page) {
  await page.evaluate(async () => {
    for (let y = 0; y < document.documentElement.scrollHeight; y += 300) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 40));
    }
    window.scrollTo(0, 0);
  });
  await page.waitForTimeout(600);
}

async function check(base, { state, itemId, shoeId, tripId, wishId, linkedId }) {
  // the four places and Add, then what each holds one level down
  // another day: the demo's day planned three days ahead, and a day with nothing planned yet
  const pages = ['/today', `/today/day/${localDay(3)}`, `/today/day/${localDay(1)}`, '/today/worn', '/today/worn/kept', '/trips', `/trips/${encodeURIComponent(tripId)}`,
    '/', `/item/${encodeURIComponent(itemId)}`, `/item/${encodeURIComponent(shoeId)}`, '/archived', '/review',
    '/add',
    '/wardrobe', '/wardrobe/wishlist', '/wardrobe/check', `/wardrobe/wish/${encodeURIComponent(wishId)}`,
    `/wardrobe/wish/${encodeURIComponent(linkedId)}`, `/wardrobe/link?url=${encodeURIComponent(SHOP_PAGE)}`,
    '/settings', '/settings/advanced'];
  const executablePath = process.env.PLAYWRIGHT_CHROMIUM_PATH || undefined;
  const browser = await chromium.launch(executablePath ? { executablePath } : {});
  const failures = [];
  const reading = [];
  try {
    for (const [size, device] of PHONES) {
      for (const scheme of ['375', '393'].includes(size) ? ['light', 'dark'] : ['light']) {
        // No service worker, so every screen comes from this backend and not a cache.
        const context = await browser.newContext({ ...device, colorScheme: scheme, storageState: state, serviceWorkers: 'block' });
        // A closet with enough clothes opens on Today the first time a tab opens / (src/landing.ts); this check wants the closet there.
        await context.addInitScript(() => sessionStorage.setItem('closet-landed', '1'));
        if (TEXT !== 100) {
          await context.addInitScript((pct) => {
            // the script runs before the page has its <html>: set the size as soon as it does
            const set = () => document.documentElement?.style.setProperty('font-size', `${pct}%`);
            if (document.documentElement) set();
            else new globalThis.MutationObserver((_, watch) => { if (document.documentElement) { set(); watch.disconnect(); } }).observe(document, { childList: true });
          }, TEXT);
        }
        for (const route of pages) {
          const page = await context.newPage();
          const errors = [];
          page.on('pageerror', (e) => errors.push(e.message));
          await page.goto(base + route);
          await settle(page);
          if (await page.getByTestId('refused').isVisible()) {
            failures.push(`${route} at ${size}px says the device was not let in instead of showing the screen`);
          }
          if (size === COUNTED_AT && scheme === 'light') reading.push({ route, ...(await page.evaluate(measure)) });
          await scrollThrough(page);
          const name = `${PREFIX}${size}-${scheme}-${route.replace(/[/?=]/g, '_').replace(/^_/, '').slice(0, 40) || 'closet'}`;
          await page.screenshot({ path: join(OUT, `${name}.png`), fullPage: true });
          const { extra, culprits } = await page.evaluate(overflow);
          if (extra > 1) failures.push(`${route} at ${size}px ${scheme} is ${extra}px wider than the screen: ${culprits.join(', ')}`);
          if (errors.length) failures.push(`${route} at ${size}px ${scheme} threw: ${errors.join(' | ')}`);
          await page.close();
        }
        {
          // Today on a day of a trip: a trip that starts today (its weather given), for this picture only
          const page = await context.newPage();
          const errors = [];
          page.on('pageerror', (e) => errors.push(e.message));
          const weather = [0, 1, 2, 3].map((i) => ({ date: localDay(i), low_c: 12, high_c: 19, rain: i === 0 }));
          const made = await page.request.post(base + '/api/trips', { headers: { 'X-Closet-Client': '1' },
            data: { place: PLACE, first_day: localDay(0), last_day: localDay(3), weather } });
          const trip = await made.json();
          try {
            await page.goto(base + '/today');
            await settle(page);
            if (size === COUNTED_AT && scheme === 'light') reading.push({ route: '/today (a trip day)', ...(await page.evaluate(measure)) });
            await scrollThrough(page);
            await page.screenshot({ path: join(OUT, `${PREFIX}${size}-${scheme}-today-trip-day.png`), fullPage: true });
            const { extra, culprits } = await page.evaluate(overflow);
            if (extra > 1) failures.push(`today on a trip day at ${size}px ${scheme} is ${extra}px wider than the screen: ${culprits.join(', ')}`);
            if (errors.length) failures.push(`today on a trip day at ${size}px ${scheme} threw: ${errors.join(' | ')}`);
          } finally {
            await page.request.delete(base + `/api/trips/${encodeURIComponent(trip.id)}`, { headers: { 'X-Closet-Client': '1' } });
            await page.close();
          }
        }
        {
          // the closet with Smaller pictures (three across on a phone), chosen in its Filter sheet and kept on the device
          const page = await context.newPage();
          await page.goto(base + '/');
          await page.evaluate(() => localStorage.setItem('closet.tileSize', 'smaller'));
          await page.reload();
          await settle(page);
          await page.screenshot({ path: join(OUT, `${PREFIX}${size}-${scheme}-closet-smaller.png`) });
          const { extra, culprits } = await page.evaluate(overflow);
          if (extra > 1) failures.push(`closet-smaller at ${size}px ${scheme} is ${extra}px wider than the screen: ${culprits.join(', ')}`);
          await page.evaluate(() => localStorage.removeItem('closet.tileSize'));
          await page.close();
        }
        for (const { route, fold, button, sheet, name, wait } of SHEETS) {
          const page = await context.newPage();
          const errors = [];
          page.on('pageerror', (e) => errors.push(e.message));
          await page.goto(base + (typeof route === 'function' ? route({ itemId, shoeId, tripId, wishId, linkedId }) : route));
          await settle(page);
          if (fold) await page.locator('details.more > summary', { hasText: fold }).first().click();
          await page.getByRole('button', { name: button }).first().click();
          await page.getByTestId(sheet).waitFor({ state: 'visible', timeout: 10_000 }).catch(() => failures.push(`${name} at ${size}px did not open`));
          if (wait) await page.getByTestId(sheet).locator(wait).first().waitFor({ timeout: 20_000 }).catch(() => failures.push(`${name} at ${size}px showed no ${wait}`));
          await page.waitForTimeout(600);
          await page.screenshot({ path: join(OUT, `${PREFIX}${size}-${scheme}-${name}.png`) });
          const { extra, culprits } = await page.evaluate(overflow);
          if (extra > 1) failures.push(`${name} at ${size}px ${scheme} is ${extra}px wider than the screen: ${culprits.join(', ')}`);
          if (errors.length) failures.push(`${name} at ${size}px ${scheme} threw: ${errors.join(' | ')}`);
          await page.close();
        }
        for (const { route, button, part, wait, name } of VIEWS) {
          const page = await context.newPage();
          const errors = [];
          page.on('pageerror', (e) => errors.push(e.message));
          await page.goto(base + route);
          await settle(page);
          await page.locator(part).getByRole('button', { name: button }).click();
          await page.locator(part).locator(wait).first().waitFor({ timeout: 10_000 }).catch(() => failures.push(`${name} at ${size}px showed no ${wait}`));
          await page.waitForTimeout(300);
          await page.locator(part).screenshot({ path: join(OUT, `${PREFIX}${size}-${scheme}-${name}.png`) });
          const { extra, culprits } = await page.evaluate(overflow);
          if (extra > 1) failures.push(`${name} at ${size}px ${scheme} is ${extra}px wider than the screen: ${culprits.join(', ')}`);
          if (errors.length) failures.push(`${name} at ${size}px ${scheme} threw: ${errors.join(' | ')}`);
          await page.close();
        }
        for (const { route, fail, name } of FAILED) {
          const page = await context.newPage();
          await page.route(fail, (r) => r.fulfill({ status: 500, json: { detail: 'Internal Server Error' } }));
          await page.goto(base + (typeof route === 'function' ? route({ itemId, shoeId, tripId, wishId, linkedId }) : route));
          await settle(page);
          await page.locator('[data-testid="failed"], [data-testid="failed-earlier"]').first()
            .waitFor({ timeout: 10_000 }).catch(() => failures.push(`${name} at ${size}px said nothing about the failed read`));
          const said = await page.locator('main').innerText();
          if (/Internal Server Error|\b500\b/.test(said)) failures.push(`${name} at ${size}px shows a status text or code`);
          await page.screenshot({ path: join(OUT, `${PREFIX}${size}-${scheme}-${name}.png`) });
          const { extra, culprits } = await page.evaluate(overflow);
          if (extra > 1) failures.push(`${name} at ${size}px ${scheme} is ${extra}px wider than the screen: ${culprits.join(', ')}`);
          await page.close();
        }
        await context.close();
      }
    }
  } finally {
    await browser.close();
  }
  return { failures, reading };
}

/** Prints how much each screen asks you to read, and the screens over the budget (a warning only, for now). */
function report(reading) {
  if (!reading.length) return;
  console.log(`\nReading load at ${COUNTED_AT}px (budget: ${BUDGET.screen} words in the first screen, ${BUDGET.page} on the page)`);
  console.log('words  first  height  screen');
  for (const r of reading) {
    console.log(`${String(r.words).padStart(5)}  ${String(r.first).padStart(5)}  ${String(r.height).padStart(6)}  ${r.route}`);
  }
  const over = reading.filter((r) => r.words > BUDGET.page || r.first > BUDGET.screen);
  for (const r of over) {
    const why = [r.words > BUDGET.page && `${r.words} words on the page`, r.first > BUDGET.screen && `${r.first} in the first screen`].filter(Boolean);
    console.log(`::warning title=Reading load::${r.route} has ${why.join(' and ')}`);
  }
  if (!over.length) console.log('Every screen is within the reading budget.');
}

async function main() {
  if (!existsSync(join(BACKEND_DIR, 'closet', 'web', 'index.html'))) {
    console.error('The built page is missing from backend/closet/web: run `npm run build` in frontend/ first.');
    return 1;
  }
  mkdirSync(OUT, { recursive: true });
  const backend = await startBackend();
  const stop = () => backend.stop().finally(() => process.exit(130));
  process.once('SIGINT', stop);
  process.once('SIGTERM', stop);
  let failures;
  try {
    const checked = await check(backend.url, await setUp(backend.url));
    failures = checked.failures;
    report(checked.reading);
  } finally {
    await backend.stop();
  }
  const shots = readdirSync(OUT).filter((f) => f.endsWith('.png')).length;
  if (failures.length) {
    for (const f of failures) console.log(`::error title=Phone layout::${f}`);
    console.log(`${failures.length} phone layout problem(s); ${shots} screenshots in ${OUT}`);
    return 1;
  }
  console.log(`Every screen fits at ${PHONES.map(([size]) => size).join(', ')}px wide; ${shots} screenshots in ${OUT}`);
  return 0;
}

main().then(
  (code) => process.exit(code),
  (e) => {
    console.error(e);
    process.exit(1);
  },
);
