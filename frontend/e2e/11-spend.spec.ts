import { expect, PASS, PHOTOS, test } from './fixtures';
import { startBackend, type Backend } from './server';

// Its own backend: the plan can't be used and the API key route talks to a stand-in that reports what each
// request used ($0.008 each at the prices written down), so nothing here reaches Anthropic or costs anything.
test.describe('the API key with a monthly limit', () => {
  let backend: Backend;

  test.beforeAll(async () => {
    backend = await startBackend({ fakes: 'api' });
  });
  test.afterAll(async () => {
    await backend?.stop();
  });

  test('set a limit, see what the month cost, and see an item wait for the limit', async ({ page }) => {
    test.setTimeout(150_000);
    await page.goto(backend.url + '/');
    await page.getByLabel('Passphrase', { exact: true }).fill(PASS);
    await page.getByLabel('Type it again').fill(PASS);
    await page.getByRole('button', { name: 'Set passphrase' }).click();
    await page.getByRole('button', { name: 'Start with my own closet' }).click();

    await page.goto(backend.url + '/settings');
    const section = page.getByRole('region', { name: 'Tagging' });
    await expect(section.getByTestId('route-plan')).toContainText('not installed', { timeout: 20_000 });
    const allow = section.getByRole('switch', { name: /Allow the API key/ });
    await expect(allow).not.toBeChecked();
    await expect(section.getByText(/^We suggest \$5\.00 a month\. At the prices written down on 3 Nov 2026/)).toBeVisible();

    // the limit is asked for with the switch, and kept
    const limit = section.getByLabel('Monthly limit for the API key (US dollars)');
    await limit.fill('0.01');
    await section.getByText('Allow the API key', { exact: true }).click();
    await expect(allow).toBeChecked();
    await expect(page.getByText('The API key may be used, up to $0.01 a month')).toBeVisible();
    await expect(section.getByTestId('spend-month')).toContainText('$0.00 of your $0.01 limit spent; nothing sent with the API key.');

    // the first photo is described with the API key
    await page.goto(backend.url + '/add');
    await page.getByTestId('library-input').setInputFiles(`${PHOTOS}graphic-tee.jpg`);
    await expect(page.getByTestId('queue-status')).toHaveText('Done', { timeout: 30_000 });
    await page.getByRole('link', { name: 'See them in your closet' }).click();
    await expect(page.getByTestId('tile').first()).toContainText('Navy polo', { timeout: 60_000 });

    await page.goto(backend.url + '/settings');
    await expect(section.getByTestId('spend-month')).toContainText('$0.01 of your $0.01 limit spent; 1 request to Claude with the API key.');
    await expect(section.getByTestId('spend-history')).toContainText('$0.01');
    await expect(section.getByText(/^Costs are worked out from Anthropic's prices as written down on 3 Nov 2026\. Prices change/)).toBeVisible();
    await expect(section.getByText('20,000', { exact: true })).toBeHidden();   // token counts only in the details fold
    await section.getByText('Details', { exact: true }).click();
    await expect(section.getByText('20,000', { exact: true })).toBeVisible();

    // the next one would pass the limit: it is not sent, and it says why
    await page.goto(backend.url + '/add');
    await page.getByRole('button', { name: 'Clear list' }).click();
    await page.getByTestId('library-input').setInputFiles(`${PHOTOS}jeans.jpg`);
    await expect(page.getByTestId('queue-status')).toHaveText('Done', { timeout: 30_000 });
    let waitingId = '';
    await expect.poll(async () => {
      const items = (await (await page.request.get(backend.url + '/api/items')).json()).items as { id: string; tag_state: string }[];
      const waiting = items.find((i) => i.tag_state === 'waiting');
      if (!waiting) return null;
      waitingId = waiting.id;
      return (await (await page.request.get(`${backend.url}/api/items/${waiting.id}`)).json()).tag_error;
    }, { timeout: 30_000 }).toMatch(/spending limit for the API key has been reached/);

    await page.goto(`${backend.url}/item/${waitingId}`);
    const notice = page.getByRole('status').filter({ hasText: 'Waiting to be described by Claude' });
    await expect(notice).toContainText("This month's spending limit for the API key has been reached, and your Claude plan can't be used right now.");
    await notice.getByRole('link', { name: 'Open Settings' }).click();
    await expect(page).toHaveURL(/\/settings$/);
    await expect(section.getByText(/This month's limit is reached/)).toBeVisible();
    await expect(section.getByTestId('spend-waiting')).toHaveText(
      "If your plan can't be used, describing the item waiting with the API key would cost under 1¢ at most.");
    await expect(section.getByTestId('tags-waiting')).toHaveText('1 item is waiting to be described.');
  });
});
