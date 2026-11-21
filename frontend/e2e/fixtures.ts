import { test as base, expect, type APIRequestContext, type Locator, type Page } from '@playwright/test';
import { startBackend, type Backend } from './server';

export const PASS = 'a calm green closet';

/** The header Closet's own page sends on every call (src/api.ts); the server refuses a change without it. */
export const CLIENT = { 'X-Closet-Client': '1' };

/**
 * The tests' own calls (`page.request`, `request`) send the page's header, so they are let in as the page is. Only
 * those calls: the page itself is never given it, so a call the page makes without it fails the test.
 */
export function asThePage(request: APIRequestContext): APIRequestContext {
  const calls = new Set(['get', 'head', 'post', 'put', 'patch', 'delete', 'fetch']);
  return new Proxy(request, {
    get(target, prop) {
      const value = Reflect.get(target, prop);
      if (typeof value !== 'function') return value;
      if (typeof prop !== 'string' || !calls.has(prop)) return value.bind(target);
      return (url: unknown, options: { headers?: Record<string, string> } = {}) =>
        value.call(target, url, { ...options, headers: { ...CLIENT, ...options.headers } });
    },
  });
}

/**
 * The backends of one worker, one spec file at a time. Each worker runs whole files, one after another; the first
 * test of a file stops the backend the previous file used and starts a fresh one (its own port, an empty data
 * folder), so a file starts from a first run whichever worker runs it and whatever ran before. Starting one takes
 * about a second. The last one is stopped when the worker ends.
 */
class FileBackends {
  private current?: { file: string; backend: Promise<Backend> };

  async forFile(file: string): Promise<Backend> {   // `file`: which run of which spec file
    if (this.current?.file !== file) {
      await this.stop();
      this.current = { file, backend: startBackend() };
    }
    return this.current.backend;
  }

  async stop() {
    const was = this.current;
    this.current = undefined;
    if (was) await (await was.backend.catch(() => undefined))?.stop();
  }
}

export const test = base.extend<{ backend: Backend }, { fileBackends: FileBackends }>({
  // eslint-disable-next-line no-empty-pattern -- Playwright fixtures take their dependencies as a pattern
  fileBackends: [async ({}, use) => {
    const backends = new FileBackends();
    await use(backends);
    await backends.stop();
  }, { scope: 'worker' }],
  /** This spec file's own backend (see FileBackends); `baseURL` points at it. */
  backend: async ({ fileBackends }, use, testInfo) => {
    // each repeat of a file (`--repeat-each`) counts as a file of its own
    await use(await fileBackends.forFile(`${testInfo.project.name}:${testInfo.file}#${testInfo.repeatEachIndex}`));
  },
  baseURL: async ({ backend }, use) => {
    await use(backend.url);
  },
  page: async ({ page }, use) => {
    Object.defineProperty(page, 'request', { value: asThePage(page.request), configurable: true });
    await use(page);
  },
  request: async ({ request }, use) => {
    await use(asThePage(request));
  },
});
export { expect };

/**
 * Gets `request` past the login through the API: on a first run it sets the passphrase, otherwise it logs in. Either
 * way the session cookie lands in `request`, so a page sharing it (`page.request`) is logged in too. `origin` is for
 * a request that has no base URL of its own. The one place the tests know how to log in (01-auth.spec.ts tests the
 * screens themselves): change it here when the login changes.
 */
export async function signIn(request: APIRequestContext, origin = '') {
  const s = await (await request.get(`${origin}/api/session`)).json();
  const r = await request.post(`${origin}/api/${s.setup_required ? 'setup' : 'login'}`, { data: { passphrase: PASS }, headers: CLIENT });
  expect(r.status()).toBe(204);
}

/** Makes sure a passphrase exists (so a test can show the login screen), and logs the page in. */
export async function ensureSetUp(page: Page) {
  await signIn(page.request);
}

/** Logs the page in (signIn) and waits for the closet. */
export async function login(page: Page) {
  await signIn(page.request);
  await page.goto('/');
  const title = page.locator('#closet-title');
  // A closet that can dress the owner opens on Today; these tests start from the closet itself.
  // The closet's title shows before its list has arrived, and only the list decides whether to move to Today
  // (src/landing.ts, once per tab). Wait for that decision: otherwise it is made on a later page load in this
  // tab (after useProfile, say), and the page leaves the closet while the test is using it.
  const today = page.locator('#today-title');
  await expect(title.or(today)).toBeVisible();
  await page.waitForFunction(() => sessionStorage.getItem('closet-landed') !== null);
  if (new URL(page.url()).pathname === '/today') await page.goto('/');
  await expect(title).toBeVisible();
}

/** Switches the server to the real or demo closet (needs a logged-in page) and reloads. */
export async function useProfile(page: Page, profile: 'main' | 'demo') {
  const r = await page.request.post('/api/profile', { data: { profile } });
  expect(r.ok()).toBeTruthy();
  await page.goto('/');
  await expect(page.locator('#closet-title')).toBeVisible();
}

/**
 * Loads the page again with the service worker in charge of it from the start, so everything the page reads from
 * here on is saved for offline. The worker is registered once the first page has loaded (src/main.tsx) and takes
 * charge of open pages as it starts (`clients.claim()` in sw/sw.js), but what such a page read before then was not
 * saved, and on a busy computer (several tests at once) a page loaded just after the worker started can still be
 * outside it: so this waits for the worker, then reloads until a page loads inside it.
 */
export async function serviceWorkerInCharge(page: Page) {
  await page.addInitScript(() => {
    (window as { closetSwFromStart?: boolean }).closetSwFromStart = navigator.serviceWorker?.controller != null;
  });
  await page.waitForFunction(() => navigator.serviceWorker.getRegistration().then((r) => r?.active?.state === 'activated'),
    null, { timeout: 15_000, polling: 100 });
  const deadline = Date.now() + 30_000;
  for (;;) {
    await page.reload();
    if (await page.evaluate(() => (window as { closetSwFromStart?: boolean }).closetSwFromStart === true)) return;
    if (Date.now() > deadline) throw new Error('The service worker did not take charge of the page within 30 seconds.');
    await page.waitForFunction(() => navigator.serviceWorker.controller != null, null, { timeout: 2_000 }).catch(() => undefined);
  }
}

export const PHOTOS = new URL('../../bench/hardcases/photos/', import.meta.url).pathname;

/** Opens one of the item page's folds (Details, Shopping facts, History, the last one) by its title, if it is closed. */
export async function openFold(scope: Page | Locator, title: string | RegExp) {
  const page = 'goto' in scope ? scope : scope.page();
  const fold = scope.locator('details.more').filter({ has: page.locator('summary', { hasText: title }) }).first();
  if ((await fold.getAttribute('open')) === null) await fold.locator('summary').first().click();
  await expect(fold).toHaveAttribute('open', '');
  return fold;
}
