import { test as base, expect, type APIRequestContext, type Locator, type Page } from '@playwright/test';

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

export const test = base.extend({
  // eslint-disable-next-line no-empty-pattern -- Playwright fixtures take their dependencies as a pattern
  baseURL: async ({}, use) => {
    await use(process.env.E2E_BASE_URL);
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

/** Makes sure a passphrase exists (so a single spec can run on its own). */
export async function ensureSetUp(page: Page) {
  const s = await (await page.request.get('/api/session')).json();
  if (s.setup_required) {
    const r = await page.request.post('/api/setup', { data: { passphrase: PASS }, headers: CLIENT });   // any page, ours or not
    expect(r.status()).toBe(204);
  }
}

/** Logs in through the page and waits for the closet. */
export async function login(page: Page) {
  await ensureSetUp(page);
  await page.goto('/');
  const field = page.getByLabel('Passphrase');
  const title = page.locator('#closet-title');
  await expect(field.or(title)).toBeVisible();
  if (await field.isVisible()) {
    await field.fill(PASS);
    await page.getByRole('button', { name: 'Open my closet' }).click();
  }
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

export const PHOTOS = new URL('../../bench/hardcases/photos/', import.meta.url).pathname;

/** Opens one of the item page's folds (Details, Shopping facts, History, the last one) by its title, if it is closed. */
export async function openFold(scope: Page | Locator, title: string | RegExp) {
  const page = 'goto' in scope ? scope : scope.page();
  const fold = scope.locator('details.more').filter({ has: page.locator('summary', { hasText: title }) }).first();
  if ((await fold.getAttribute('open')) === null) await fold.locator('summary').first().click();
  await expect(fold).toHaveAttribute('open', '');
  return fold;
}
