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

test('a second model that did not download is shown, in the closet and in Settings, and can be tried again', async ({ page }) => {
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

  await page.locator('nav.sidebar').getByRole('link', { name: 'Settings' }).click();
  const section = page.getByRole('region', { name: 'Background removal' });
  await expect(section).toContainText('Ready. New photos get their background removed automatically.');
  const line = section.getByTestId('second-model');
  await expect(line).toContainText("The second model, which fixes cutouts the first one gets wrong");
  await expect(line).toContainText("didn't download");
  await line.getByRole('button', { name: 'Try the download again' }).click();
  await expect(line).toContainText('Also downloading a second model');
  await expect(line.getByLabel('Model download progress')).toBeVisible();
  expect(asked).toBe(1);

  // where to put it by hand, under Advanced
  await page.locator('details#s-advanced').getByText('Advanced', { exact: true }).click();
  const address = page.getByRole('region', { name: 'Background-removal model' });
  await expect(address).toContainText('https://example.com/u2net.onnx');
  await expect(address).toContainText('/data/models/u2net.onnx');

  now = second();   // it has come: the line goes
  await page.reload();
  await expect(page.getByRole('region', { name: 'Background removal' }).getByTestId('second-model')).toHaveCount(0);
  await page.goto('/');
  await expect(page.getByTestId('model-banner')).toHaveCount(0);
});
