import { expect, PASS, test } from './fixtures';
import { startBackend, type Backend } from './server';

const KEY = 'sk-ant-api03-' + 'k'.repeat(80);
const REFUSED = 'sk-ant-api03-' + 'x'.repeat(73) + 'refused';

// Its own backend with a stand-in keychain and a stand-in check: a key ending in "refused" is turned down.
// Nothing here reaches Anthropic or the computer's keychain.
test.describe('the API key box in Settings', () => {
  let backend: Backend;

  test.beforeAll(async () => {
    backend = await startBackend({ fakes: 'api' });
  });
  test.afterAll(async () => {
    await backend?.stop();
  });

  test('paste a key, see it accepted but never shown, replace it, and remove it', async ({ page }) => {
    await page.goto(backend.url + '/');
    await page.getByLabel('Passphrase', { exact: true }).fill(PASS);
    await page.getByLabel('Type it again').fill(PASS);
    await page.getByRole('button', { name: 'Set passphrase' }).click();
    await page.getByRole('button', { name: 'Start with my own closet' }).click();

    await page.goto(backend.url + '/settings');
    const section = page.getByRole('region', { name: 'Describing clothes' });
    const box = section.getByTestId('api-key');
    await expect(box).toContainText('No API key yet.');
    // the key is described once, in its own row of the list of routes
    await expect(section.getByTestId('route-api').getByTestId('api-key')).toBeVisible();
    await expect(section.getByText(/No API key/)).toHaveCount(1);
    const input = box.getByLabel('Paste your API key');
    await expect(input).toHaveAttribute('type', 'password');

    // something that is not a key, then a key Anthropic turns down: neither is kept
    await input.fill('hello');
    await box.getByRole('button', { name: 'Save key' }).click();
    await expect(box.getByRole('alert')).toContainText('Keys start with sk-ant-');
    await input.fill(REFUSED);
    await box.getByRole('button', { name: 'Save key' }).click();
    await expect(box.getByRole('alert')).toContainText('Anthropic did not accept that key');
    await expect(box).toContainText('No API key yet.');

    // a good key: saved, the box says where, and the key appears nowhere on the page
    await input.fill(KEY);
    await box.getByRole('button', { name: 'Save key' }).click();
    await expect(page.getByText('Key saved. Anthropic accepted it. Turn on Allow the API key below to use it.')).toBeVisible();
    await expect(box).toContainText("Your API key is saved in this Mac's keychain.");
    await expect(box.getByLabel('Paste your API key')).toHaveCount(0);
    await page.reload();
    await expect(box).toContainText("Your API key is saved in this Mac's keychain.");
    expect(await page.content()).not.toContain(KEY.slice(-30));

    // replace it, then remove it
    await box.getByRole('button', { name: 'Replace key' }).click();
    await box.getByLabel('New API key').fill('sk-ant-api03-' + 'n'.repeat(80));
    await box.getByRole('button', { name: 'Save key' }).click();
    await expect(box).toContainText("Your API key is saved in this Mac's keychain.");
    await box.getByRole('button', { name: 'Remove key' }).click();
    await box.getByRole('button', { name: 'Remove', exact: true }).click();
    await expect(page.getByText('Key removed', { exact: true })).toBeVisible();
    await expect(box).toContainText('No API key yet.');
  });
});
