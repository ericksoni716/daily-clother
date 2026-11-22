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
// PHONE_CHECK_SIZES=393 (a comma list) pictures only those widths, for a quicker look while working.
const ONLY = (process.env.PHONE_CHECK_SIZES || '').split(',').map((s) => s.trim()).filter(Boolean);
const PHONES = ONLY.length ? ALL_PHONES.filter(([size]) => ONLY.includes(size)) : ALL_PHONES;
// The reading budget in docs/DESIGN.md ("Reading load is a budget"): about 150 words in the first phone screen, about
// 350 on the whole screen. Counted at 393px in light; a screen over either is listed, but does not fail the check yet.
const BUDGET = { screen: 150, page: 350 };
const COUNTED_AT = '393';
// Made-up names, long on purpose.
const LONG = {
  item: 'Heavyweight brushed cotton flannel overshirt in faded forest green and charcoal buffalo check',
  place: 'Upper Wickhamstead-under-Lyme-on-the-Marsh, Greater Fenwold Coastal District, Nowhereshire',
  wish: 'A lightweight packable waterproof shell jacket with a hood that folds into the collar',
  line: 'Never anything double-breasted, never anything with a crest or a logo-embroidered-chest-pocket-of-any-kind',
};
// Sheets opened by a button on a screen, pictured as well: the style conversation and every line of Your style.
const SHEETS = [
  { route: '/settings', button: 'Talk to Claude about your style', sheet: 'style-talk-sheet', name: 'settings-style-talk' },
  { route: '/settings', button: /^(See all lines|Change the lines)$/, sheet: 'style-lines-sheet', name: 'settings-style-lines' },
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
    // a shoe's page as well: its photos and drawings make it the longest item page
    const shoe = items.find((i) => ['sneakers', 'boots', 'dress_shoes', 'sandals'].includes(i.category)) ?? item;
    // A trip asks the weather service for its forecast unless the weather is given, so it is given: mild and dry.
    const first = localDay(10), last = localDay(13);
    const weather = [];
    for (let i = 10; i <= 13; i++) weather.push({ date: localDay(i), low_c: 9, high_c: 17, rain: false });
    const trip = await call('/api/trips', 'POST', { place: PLACE, first_day: first, last_day: last, weather });
    // A wish by name needs neither the weather nor Claude.
    const wish = await call('/api/wishlist', 'POST', { name: LONG.wish });
    // A wish from a link: the backend's made-up shop page with a long name (tests/e2e_backend.py, ShopPages, never the
    // web), read once and then again a little cheaper, so the wishlist's row says the price went down.
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
    await call(`/api/wishlist/${encodeURIComponent(linked.id)}/prices`, 'POST');
    await settled();
    // Your style: an answer to a question, a long line of your own, and a message to Claude (the stand-in answers it in
    // a second and a half, with a line to keep), so Settings and the conversation show each kind of line
    await call('/api/style/questions/warmth', 'POST', { choice: 'I run warm' });
    await call('/api/style/lines', 'POST', { text: LONG.line });
    await call('/api/style/talk', 'POST', { say: 'I always feel warm on the bus, even in winter' });
    for (let i = 0; i < 40 && (await call('/api/style/talk')).answering; i++) await new Promise((r) => setTimeout(r, 250));
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
 * How much there is to read on the screen: the words in the page (not the tab bar or the sidebar), the words in the
 * first phone screen (what shows above the tab bar before scrolling), and the page's height. Runs inside the page.
 */
function measure() {
  const root = document.querySelector('main') ?? document.body;
  const tabbar = document.querySelector('nav.tabbar');
  const fold = tabbar ? tabbar.getBoundingClientRect().top : window.innerHeight;
  const count = (text) => (text.match(/[\p{L}\p{N}][\p{L}\p{N}'’.-]*/gu) ?? []).length;
  let first = 0;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const el = node.parentElement;
    if (!el || !node.textContent?.trim()) continue;
    const style = window.getComputedStyle(el);
    if (style.visibility === 'hidden' || style.display === 'none' || el.closest('[hidden], [aria-hidden="true"], .visually-hidden')) continue;
    const range = document.createRange();
    range.selectNodeContents(node);
    const r = range.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    if (r.top + window.scrollY < fold) first += count(node.textContent);
  }
  return { words: count(root.innerText || ''), first, height: document.documentElement.scrollHeight };
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
  const pages = ['/today', '/today/worn', '/trips', `/trips/${encodeURIComponent(tripId)}`,
    '/', `/item/${encodeURIComponent(itemId)}`, `/item/${encodeURIComponent(shoeId)}`, '/archived', '/review',
    '/add',
    '/wardrobe', '/wardrobe/check', `/wardrobe/wish/${encodeURIComponent(wishId)}`,
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
          const name = `${size}-${scheme}-${route.replace(/[/?=]/g, '_').replace(/^_/, '').slice(0, 40) || 'closet'}`;
          await page.screenshot({ path: join(OUT, `${name}.png`), fullPage: true });
          const { extra, culprits } = await page.evaluate(overflow);
          if (extra > 1) failures.push(`${route} at ${size}px ${scheme} is ${extra}px wider than the screen: ${culprits.join(', ')}`);
          if (errors.length) failures.push(`${route} at ${size}px ${scheme} threw: ${errors.join(' | ')}`);
          await page.close();
        }
        for (const { route, button, sheet, name } of SHEETS) {
          const page = await context.newPage();
          const errors = [];
          page.on('pageerror', (e) => errors.push(e.message));
          await page.goto(base + route);
          await settle(page);
          await page.getByRole('button', { name: button }).first().click();
          await page.getByTestId(sheet).waitFor({ state: 'visible', timeout: 10_000 }).catch(() => failures.push(`${name} at ${size}px did not open`));
          await page.waitForTimeout(600);
          await page.screenshot({ path: join(OUT, `${size}-${scheme}-${name}.png`) });
          const { extra, culprits } = await page.evaluate(overflow);
          if (extra > 1) failures.push(`${name} at ${size}px ${scheme} is ${extra}px wider than the screen: ${culprits.join(', ')}`);
          if (errors.length) failures.push(`${name} at ${size}px ${scheme} threw: ${errors.join(' | ')}`);
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
