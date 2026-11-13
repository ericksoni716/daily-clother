import { test as base, expect, type Page } from '@playwright/test';

export const PASS = 'a calm green closet';

export const test = base.extend({
  // eslint-disable-next-line no-empty-pattern -- Playwright fixtures take their dependencies as a pattern
  baseURL: async ({}, use) => {
    await use(process.env.E2E_BASE_URL);
  },
});
export { expect };

/** Makes sure a passphrase exists (so a single spec can run on its own). */
export async function ensureSetUp(page: Page) {
  const s = await (await page.request.get('/api/session')).json();
  if (s.setup_required) {
    const r = await page.request.post('/api/setup', { data: { passphrase: PASS } });
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
  const today = page.locator('#today-title');
  await expect(title.or(today)).toBeVisible();
  if (await today.isVisible()) await page.goto('/');
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
