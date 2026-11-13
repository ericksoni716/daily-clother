import { expect, PASS, test } from './fixtures';
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

  test('the key-first choices wait for a key, the list follows the choice, and removing the key resets it', async ({ page }) => {
    await page.goto(backend.url + '/');
    await page.getByLabel('Passphrase', { exact: true }).fill(PASS);
    await page.getByLabel('Type it again').fill(PASS);
    await page.getByRole('button', { name: 'Set passphrase' }).click();
    await page.getByRole('button', { name: 'Start with my own closet' }).click();

    await page.goto(backend.url + '/settings');
    const section = page.getByRole('region', { name: 'Describing clothes' });
    const choice = section.getByTestId('route-order');
    const planFirst = choice.getByRole('radio', { name: "Use my Claude plan first, the key only if the plan can't" });
    const keyFirst = choice.getByRole('radio', { name: /^Use the API key first/ });
    const onlyPlan = choice.getByRole('radio', { name: 'Only my Claude plan' });
    const onlyKey = choice.getByRole('radio', { name: /^Only the API key/ });
    await expect(planFirst).toBeChecked();   // the default
    await expect(keyFirst).toBeDisabled();
    await expect(onlyKey).toBeDisabled();
    await expect(choice).toContainText('Use the API key first (save an API key first)');
    await expect(choice).toContainText('The API key is only used once you turn on Allow the API key below and set a monthly limit.');
    const routes = section.getByRole('listitem');
    await expect(routes.nth(0)).toContainText('Your Claude plan', { timeout: 20_000 });

    // with a key saved, the key can go first: the list follows, but the key is only tried once allowed with a limit
    const box = section.getByTestId('api-key');
    await box.getByLabel('Paste your API key').fill(KEY);
    await box.getByRole('button', { name: 'Save key' }).click();
    await expect(box).toContainText("Your API key is saved in this Mac's keychain.");
    await expect(keyFirst).toBeEnabled();
    await keyFirst.click();
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();
    await expect(keyFirst).toBeChecked();
    await expect(routes.nth(0)).toContainText('An API key', { timeout: 20_000 });
    await expect(routes.nth(1)).toContainText('Your Claude plan');
    await expect(section.getByTestId('route-first')).toHaveCount(0);   // the plan isn't set up and the key isn't allowed yet
    await section.getByText('Monthly limit and spending').click();   // the limit sits under its own disclosure
    await section.getByLabel('Monthly limit for the API key (US dollars)').fill('2');
    await section.getByText('Allow the API key', { exact: true }).click();
    await expect(section.getByTestId('route-first')).toHaveText('Closet will try your API key first.', { timeout: 20_000 });

    // kept after a reload
    await page.reload();
    await expect(keyFirst).toBeChecked();

    // only the plan: the key is not in the list
    await onlyPlan.click();
    await expect(onlyPlan).toBeChecked();
    await expect(routes).toHaveCount(1, { timeout: 20_000 });
    await expect(routes.nth(0)).toContainText('Your Claude plan');
    await expect(section.getByTestId('route-api-unused')).toContainText('Not used: you chose to use only your Claude plan.');
    await expect(box).toContainText("Your API key is saved in this Mac's keychain.");   // the key can still be replaced or removed

    // only the key, then remove the key: back to the plan first
    await onlyKey.click();
    await expect(routes).toHaveCount(1, { timeout: 20_000 });
    await expect(routes.nth(0)).toContainText('An API key');
    await box.getByRole('button', { name: 'Remove key' }).click();
    await box.getByRole('button', { name: 'Remove', exact: true }).click();
    await expect(box).toContainText('No API key yet.');
    await expect(planFirst).toBeChecked();
    await expect(onlyKey).toBeDisabled();
  });
});
