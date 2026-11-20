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

test('a second model that did not download is shown in the closet and can be tried again from there', async ({ page }) => {
  let now = FAILED;
  let asked = 0;
  await page.route('**/api/model', (route) => route.fulfill({ json: model({ second: now }) }));
  await page.route('**/api/model/download', (route) => {
    asked += 1;
    now = DOWNLOADING;
    return route.fulfill({ status: 202, json: model({ second: now }) });
  });
  await login(page);

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
  await page.locator('details#s-advanced').getByText('Advanced', { exact: true }).click();
  const address = page.getByRole('region', { name: 'Background-removal model' });
  await expect(address).toContainText('https://example.com/u2net.onnx');
  await expect(address).toContainText('/data/models/u2net.onnx');

  now = second();   // it has come: nothing is shown in the closet
  await page.goto('/');
  await expect(page.locator('#closet-title')).toBeVisible();
  await expect(page.getByTestId('model-banner')).toHaveCount(0);
});

test('a first model that did not download says why in the closet, and Try again starts it', async ({ page }) => {
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
  const banner = page.getByTestId('model-banner');
  await expect(banner).toContainText("the model download didn't work");
  await expect(banner).toContainText('Could not reach the download server');
  await banner.getByRole('button', { name: 'Try again' }).click();
  await expect(banner).toHaveCount(0);
  expect(asked).toBe(1);
});
