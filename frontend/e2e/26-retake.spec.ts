import { readFileSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { expect, PHOTOS, test } from './fixtures';
import { startBackend, type Backend } from './server';

// "Retake the photo" for clothes. The browser tests' backend measures no patterns (its stand-in for Claude leaves the
// pattern worker off) and its stand-in cutout never fails, so the item page is shown one answer in which the
// checks could not be measured, or the background could not be removed; the new photo then goes to the real
// backend, which cuts it out and describes it again with its stand-ins.
test.use({ serviceWorkers: 'block' });

const PLAID_FAILED = 'Nines could not measure the checks from this photo, so the drawing shows only the colour.';

test.describe('a new photo of a piece of clothing', () => {
  let backend: Backend;

  test.beforeAll(async () => {
    backend = await startBackend({ fakes: true });
  });
  test.afterAll(async () => {
    await backend?.stop();
  });

  /** The item page, shown once with `change` laid over what the backend says about the item. */
  async function showWith(page: Page, id: string, change: Record<string, unknown>) {
    await page.goto('about:blank');   // a page still following the item would take the changed answer instead
    await page.route(`**/api/items/${id}`, async (route) => {
      if (route.request().method() !== 'GET') return route.fallback();
      const response = await route.fetch();
      await route.fulfill({ response, json: { ...(await response.json()), ...change } });
    }, { times: 1 });
    await page.goto(`${backend.url}/item/${id}`);
  }

  async function item(page: Page, id: string) {
    return (await page.request.get(`${backend.url}/api/items/${id}`)).json();
  }

  test('beside the note that the checks could not be measured, and when the background could not be removed', async ({ page }) => {
    test.setTimeout(120_000);
    await page.goto(backend.url + '/');
    await expect(page.locator('#closet-title')).toBeVisible();

    const sent = await page.request.post(`${backend.url}/api/items`, {
      multipart: {
        photo: { name: 'plaid.jpg', mimeType: 'image/jpeg', buffer: readFileSync(`${PHOTOS}plaid-flannel.jpg`) },
        client_key: 'retake-1',
      },
    });
    expect(sent.status()).toBe(201);
    const id = (await sent.json()).id as string;
    await expect.poll(async () => (await item(page, id)).tag_state, { timeout: 60_000 }).toBe('done');
    const before = await item(page, id);
    await page.request.post(`${backend.url}/api/items/${id}/wears`);

    // the checks could not be measured: one note, one button
    await showWith(page, id, { pattern: 'plaid', pattern_state: 'failed', pattern_error: PLAID_FAILED });
    const note = page.getByTestId('pattern-failed');
    await expect(note).toHaveCount(1);
    await expect(note).toContainText('could not measure the checks');
    await expect(page.getByRole('button', { name: 'Retake the photo' })).toHaveCount(1);
    await note.getByTestId('retake-input').setInputFiles(`${PHOTOS}plaid-madras.jpg`);
    await expect(page.locator('.toast').filter({ hasText: 'New photo added.' })).toContainText(
      'Nines removes its background, Claude describes it again, then its pattern is measured again');
    await expect(note).toHaveCount(0);   // the old note was about the old photo

    // cut out and described again, its wear kept
    await expect.poll(async () => (await item(page, id)).tagged_at, { timeout: 60_000 }).not.toBe(before.tagged_at);
    const after = await item(page, id);
    expect(after.id).toBe(id);
    expect(after.photos[0].id).not.toBe(before.photos[0].id);
    expect(after.wear_count).toBe(1);

    // the background could not be removed: the button is beside "Try the cutout again", and only there
    // (the page reads the failure from the item's progress, which the server works out from these fields)
    await showWith(page, id, { cutout_state: 'failed', cutout_error: 'The background could not be removed from this photo.',
      pattern: 'plaid', pattern_state: 'failed', pattern_error: PLAID_FAILED,
      progress: { stage: 'cutout', step: 1, of: 3, state: 'failed', title: 'Cutting out', words: "The background couldn't be removed",
        about: '', waiting_for: null, why: null, error: 'The background could not be removed from this photo.', can_retry: true,
        retry: 'cutout' } });
    const notice = page.locator('.notice-warn').filter({ hasText: "The background couldn't be removed." });
    await expect(notice.getByRole('button', { name: 'Try the cutout again' })).toBeVisible();
    await expect(notice.getByRole('button', { name: 'Retake the photo' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Retake the photo' })).toHaveCount(1);
    await expect(page.getByTestId('pattern-failed')).toHaveCount(1);
  });
});
