import { expect, test } from './fixtures';
import { startBackend, type Backend } from './server';

const KEY = 'sk-ant-api03-' + 'r'.repeat(80);

// Its own backend: the plan can't be used, and the API key goes to a stand-in keychain and a stand-in check.
// Nothing here reaches Anthropic or the computer's keychain, and nothing is described, so nothing is spent.
test.describe('choosing which route to Claude is tried first', () => {
  let backend: Backend;

  test.beforeAll(async () => {
    backend = await startBackend({ fakes: 'api' });
  });
  test.afterAll(async () => {
    await backend?.stop();
  });

  test('the choice comes with a key, the first line follows it, and removing the key resets it', async ({ page }) => {
    await page.goto(backend.url + '/');
    await expect(page.locator('#closet-title')).toBeVisible();

    await page.goto(backend.url + '/settings/advanced');
    const section = page.getByRole('region', { name: 'Claude' });
    const lead = section.getByTestId('claude-lead');
    const choice = section.getByLabel('Which to use');
    // with no key there is nothing to choose between: the choice comes with a key (the default is the plan first)
    await expect(section.getByTestId('api-key')).toContainText('No API key yet.');
    await expect(section.getByTestId('route-order')).toHaveCount(0);
    expect((await (await page.request.get(backend.url + '/api/settings')).json()).tagging_route_order).toBe('auto');
    await expect(lead).toHaveText(/^Nines can't reach Claude yet\./, { timeout: 20_000 });

    // with a key saved, the key can go first, but it is only tried once allowed with a limit
    const box = section.getByTestId('api-key');
    await box.getByLabel('Paste your API key').fill(KEY);
    await box.getByRole('button', { name: 'Save key' }).click();
    await expect(box).toContainText("Your API key is saved in this Mac's keychain.");
    await expect(choice).toHaveValue('auto');
    await expect(choice.locator('option')).toHaveText(['Your plan first, then the key', 'The key first, then your plan', 'Only your plan', 'Only the key']);
    for (const value of ['api-first', 'api']) await expect(choice.locator(`option[value="${value}"]`)).toBeEnabled();
    await choice.selectOption('api-first');
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();
    await expect(choice).toHaveValue('api-first');
    // the plan isn't set up and the key isn't allowed yet: one cause, and what below puts it right
    await expect(lead).toHaveText(/^Nines can't reach Claude yet: your API key is saved but not allowed\. Allow it below, or use your Claude plan\./, { timeout: 20_000 });
    await section.getByLabel('Monthly limit (US dollars)').fill('2');   // in view, nothing to open
    await section.getByText('Allow the API key', { exact: true }).click();
    await expect(lead).toHaveText('Using your API key.', { timeout: 20_000 });

    // kept after a reload
    await page.reload();
    await expect(choice).toHaveValue('api-first');

    // only the plan: the key is not used, and can still be replaced or removed
    await choice.selectOption('plan');
    await expect(choice).toHaveValue('plan');
    await expect(lead).toHaveText(/^Nines can't reach Claude yet\./, { timeout: 20_000 });
    await expect(box).toContainText("Your API key is saved in this Mac's keychain.");
    await expect(box.getByRole('button', { name: 'Replace key' })).toBeVisible();

    // only the key, then remove the key: back to the plan first, and no choice to make
    await choice.selectOption('api');
    await expect(choice).toHaveValue('api');
    await expect(lead).toHaveText('Using your API key.', { timeout: 20_000 });
    await box.getByRole('button', { name: 'Remove key' }).click();
    await box.getByRole('button', { name: 'Remove', exact: true }).click();
    await expect(box).toContainText('No API key yet.');
    await expect(section.getByTestId('route-order')).toHaveCount(0);
    await expect.poll(async () => (await (await page.request.get(backend.url + '/api/settings')).json()).tagging_route_order).toBe('auto');
  });
});
