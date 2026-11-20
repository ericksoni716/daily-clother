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
/* global document, window */
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readdirSync, rmSync } from 'node:fs';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium, devices, request } from '@playwright/test';

const BACKEND_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', 'backend');
const OUT = resolve(process.argv[2] || 'phone-shots');
const PASS = 'a long and quiet phone check';
// 375 is the narrowest the app supports; 402 and 440 are the iPhone 17 Pro and Pro Max (Playwright has
// both; if an older Playwright doesn't, the 15 Pro and Pro Max at 402×874 and 440×956 stand in).
const at = (name, fallback, width, height) => devices[name] ?? { ...devices[fallback], viewport: { width, height: height - 193 }, screen: { width, height } };
const PHONES = [
  ['375', devices['iPhone 13 Mini']],
  ['393', devices['iPhone 15']],
  ['402', at('iPhone 17 Pro', 'iPhone 15 Pro', 402, 874)],
  ['430', devices['iPhone 15 Pro Max']],
  ['440', at('iPhone 17 Pro Max', 'iPhone 15 Pro Max', 440, 956)],
];
// Made-up names, long on purpose.
const LONG = {
  item: 'Heavyweight brushed cotton flannel overshirt in faded forest green and charcoal buffalo check',
  place: 'Upper Wickhamstead-under-Lyme-on-the-Marsh, Greater Fenwold Coastal District, Nowhereshire',
  wish: 'A lightweight packable waterproof shell jacket with a hood that folds into the collar',
};
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

/** Sets the passphrase (which logs in), gives things long names, and returns the login to reuse in every browser. */
async function setUp(base) {
  const api = await request.newContext({ baseURL: base });
  try {
    const call = async (route, method = 'GET', data) => {
      const res = await api.fetch(route, { method, data });
      if (!res.ok()) throw new Error(`${method} ${route}: ${res.status()} ${await res.text()}`);
      return res.status() === 204 ? null : res.json();
    };
    await call('/api/setup', 'POST', { passphrase: PASS });
    const { items } = await call('/api/items?status=active');
    if (!items.length) throw new Error('The closet copied from the demo has no clothes.');
    const item = items[0];
    await call(`/api/items/${encodeURIComponent(item.id)}`, 'PATCH', { name: LONG.item });
    // A trip asks the weather service for its forecast unless the weather is given, so it is given: mild and dry.
    const first = localDay(10), last = localDay(13);
    const weather = [];
    for (let i = 10; i <= 13; i++) weather.push({ date: localDay(i), low_c: 9, high_c: 17, rain: false });
    const trip = await call('/api/trips', 'POST', { place: PLACE, first_day: first, last_day: last, weather });
    // A wish by name needs neither the weather nor Claude.
    await call('/api/wishlist', 'POST', { name: LONG.wish });
    return { state: await api.storageState(), itemId: item.id, tripId: trip.id };
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

async function check(base, { state, itemId, tripId }) {
  const pages = ['/today', '/today/worn', '/', `/item/${encodeURIComponent(itemId)}`, '/archived', '/add', '/review',
    '/trips', `/trips/${encodeURIComponent(tripId)}`, '/missing', '/missing/check', '/insights', '/settings'];
  const executablePath = process.env.PLAYWRIGHT_CHROMIUM_PATH || undefined;
  const browser = await chromium.launch(executablePath ? { executablePath } : {});
  const failures = [];
  try {
    for (const [size, device] of PHONES) {
      for (const scheme of size === '393' ? ['light', 'dark'] : ['light']) {
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
          if (await page.getByLabel('Passphrase').isVisible()) {
            failures.push(`${route} at ${size}px shows the login instead of the screen`);
          }
          await scrollThrough(page);
          const name = `${size}-${scheme}-${route.replace(/[/?=]/g, '_').replace(/^_/, '').slice(0, 40) || 'closet'}`;
          await page.screenshot({ path: join(OUT, `${name}.png`), fullPage: true });
          const { extra, culprits } = await page.evaluate(overflow);
          if (extra > 1) failures.push(`${route} at ${size}px ${scheme} is ${extra}px wider than the screen: ${culprits.join(', ')}`);
          if (errors.length) failures.push(`${route} at ${size}px ${scheme} threw: ${errors.join(' | ')}`);
          await page.close();
        }
        await context.close();
      }
    }
  } finally {
    await browser.close();
  }
  return failures;
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
    failures = await check(backend.url, await setUp(backend.url));
  } finally {
    await backend.stop();
  }
  const shots = readdirSync(OUT).filter((f) => f.endsWith('.png')).length;
  if (failures.length) {
    for (const f of failures) console.log(`::error title=Phone layout::${f}`);
    console.log(`${failures.length} phone layout problem(s); ${shots} screenshots in ${OUT}`);
    return 1;
  }
  console.log(`Every screen fits at 375, 393, 402, 430 and 440px wide; ${shots} screenshots in ${OUT}`);
  return 0;
}

main().then(
  (code) => process.exit(code),
  (e) => {
    console.error(e);
    process.exit(1);
  },
);
