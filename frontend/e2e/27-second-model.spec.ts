import type { Page } from '@playwright/test';
import { expect, login, test } from './fixtures';

// The second background model, asked as well when the first takes stripes or checks for background. The owner's
// striped shirt was cut out by the first model alone because the second wasn't there, and nothing said so. Stand-ins
// for the model's state: the first model is ready, the second's download didn't work, then it is tried again.

const model = (over: Record<string, unknown> = {}) => ({
  state: 'ready', downloaded_bytes: 178_648_008, total_bytes: 178_648_008, error: null,
  url: 'https://example.com/isnet-general-use.onnx', path: '/data/models/isnet-general-use.onnx', sha256: 'a'.repeat(64),
  name: 'isnet-general-use', ...over,
});
const second = (over: Record<string, unknown> = {}) => model({
  url: 'https://example.com/u2net.onnx', path: '/data/models/u2net.onnx', name: 'u2net', ...over,
});
const FAILED = second({ state: 'failed', downloaded_bytes: 0, total_bytes: null,
  error: 'Could not reach the download server. Check the internet connection and try again.' });
const DOWNLOADING = second({ state: 'downloading', downloaded_bytes: 44_000_000, total_bytes: 175_997_641 });

/** Settings bring the model's state with them (GET /api/settings), so the stand-in is put there too. */
async function standInSettings(page: Page, answer: () => Record<string, unknown>) {
  await page.route('**/api/settings', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback();
    const response = await route.fetch();
    return route.fulfill({ response, json: { ...(await response.json()), model: answer() } });
  });
}

test('a second model that did not download is shown on Add and can be tried again from there', async ({ page }) => {
  let now = FAILED;
  let asked = 0;
  await page.route('**/api/model', (route) => route.fulfill({ json: model({ second: now }) }));
  await standInSettings(page, () => model({ second: now }));
  await page.route('**/api/model/download', (route) => {
    asked += 1;
    now = DOWNLOADING;
    return route.fulfill({ status: 202, json: model({ second: now }) });
  });
  await login(page);
  await page.goto('/add');

  const banner = page.getByTestId('model-banner');
  await expect(banner).toContainText("the second model didn't download");
  await expect(banner).toContainText('Could not reach the download server');
  await banner.getByRole('button', { name: 'Try again' }).click();
  await expect(page.getByText('Downloading the background-removal model')).toBeVisible();
  await expect(banner).toHaveCount(0);   // downloading again: nothing to do
  expect(asked).toBe(1);

  // Settings has no card of its own for it (the program downloads both models and tries again by itself); where to
  // get the files and put them by hand is under Advanced
  await page.locator('nav.sidebar').getByRole('link', { name: 'Settings' }).click();
  await expect(page.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Updates', exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Background removal', exact: true })).toHaveCount(0);
  for (const name of ['Download the model', 'Download the second model', 'Try the download again']) {
    await expect(page.getByRole('button', { name })).toHaveCount(0);
  }
  await page.getByRole('link', { name: 'Advanced settings' }).click();
  const address = page.getByRole('region', { name: 'Background removal' });
  await expect(address.getByLabel('Download address')).toHaveValue('https://example.com/isnet-general-use.onnx');
  await address.getByText('Put the files in place by hand').click();
  await expect(address).toContainText('https://example.com/u2net.onnx');
  await expect(address).toContainText('/data/models/u2net.onnx');

  now = second();   // it has come: nothing is shown on Add
  await page.goto('/add');
  await expect(page.locator('#add-title')).toBeVisible();
  await expect(page.getByTestId('model-banner')).toHaveCount(0);
});

test('a first model that did not download says why on Add, and Try again starts it', async ({ page }) => {
  let now = model({ state: 'failed', downloaded_bytes: 0, total_bytes: null, second: second({ state: 'missing', downloaded_bytes: 0, total_bytes: null }),
    error: 'Could not reach the download server. Check the internet connection and try again.' });
  let asked = 0;
  await page.route('**/api/model', (route) => route.fulfill({ json: now }));
  await page.route('**/api/model/download', (route) => {
    asked += 1;
    now = model({ state: 'downloading', downloaded_bytes: 1_000_000, total_bytes: 178_648_008, second: second({ state: 'missing', downloaded_bytes: 0, total_bytes: null }) });
    return route.fulfill({ status: 202, json: now });
  });
  await login(page);
  await page.goto('/add');
  const banner = page.getByTestId('model-banner');
  await expect(banner).toContainText("the model download didn't work");
  await expect(banner).toContainText('Could not reach the download server');
  // its link goes where the model's address and files are: the Advanced settings
  await expect(banner.getByRole('link', { name: 'Background removal settings' })).toHaveAttribute('href', '/settings/advanced');
  await banner.getByRole('button', { name: 'Try again' }).click();
  await expect(banner).toHaveCount(0);
  expect(asked).toBe(1);
});
