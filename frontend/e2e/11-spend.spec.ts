import { expect, PHOTOS, test } from './fixtures';
import { startBackend, type Backend } from './server';

// Its own backend: the plan can't be used and the API key route talks to a stand-in that reports what each
// request used ($0.16 each on the describing model, Sonnet, at the prices written down; $0.0965 is kept back for each
// photo before it is sent), so nothing here reaches Anthropic or costs anything. A limit of $0.20 lets one photo through
// and stops the next.
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
    await expect(page.locator('#closet-title')).toBeVisible();

    // Settings says in one red line that Claude can't be reached; the key and its limit are on Advanced
    await page.goto(backend.url + '/settings');
    await expect(page.getByTestId('claude-line')).toContainText("Nines can't reach Claude yet.", { timeout: 20_000 });
    await page.goto(backend.url + '/settings/advanced');
    const section = page.getByRole('region', { name: 'Claude' });
    await expect(section.getByTestId('route-plan')).toContainText('not installed', { timeout: 20_000 });
    // the limit, the switch and the spending come with a key; the stand-in check accepts any well-formed key
    await expect(section.getByRole('switch', { name: /Allow the API key/ })).toHaveCount(0);
    const box = section.getByTestId('api-key');
    await box.getByLabel('Paste your API key').fill('sk-ant-api03-' + 's'.repeat(80));
    await box.getByRole('button', { name: 'Save key' }).click();
    await expect(box).toContainText("Your API key is saved in this Mac's keychain.");
    const allow = section.getByRole('switch', { name: /Allow the API key/ });
    await expect(allow).not.toBeChecked();

    // the limit and the month's spending are in view without opening anything; the switch asks for a limit, and keeps it
    const limit = section.getByLabel('Monthly limit (US dollars)');
    await expect(limit).toBeVisible();
    await expect(section.getByTestId('spend-month')).toHaveText(/^[A-Z][a-z]+: nothing spent yet, and no limit set\.$/);
    await section.getByText('Allow the API key', { exact: true }).click();
    await expect(section.getByRole('alert')).toHaveText('Type a monthly limit in dollars, such as 5 or 2.50.');
    await expect(allow).not.toBeChecked();
    // the month's requests, why the suggested limit and how costs are worked out are folded under "Spending so far"
    const more = section.getByTestId('spend-more');
    await more.getByText('Spending so far').click();
    await expect(more.getByTestId('spend-requests')).toHaveText('Nothing was sent with the API key this month.');
    await expect(more.getByText(/^We suggest \$5\.00 a month\. At the prices written down on 3 Nov 2026/)).toBeVisible();
    await limit.fill('0.20');
    await section.getByText('Allow the API key', { exact: true }).click();
    await expect(allow).toBeChecked();
    await expect(page.getByText('The API key may be used, up to $0.20 a month')).toBeVisible();
    await expect(section.getByTestId('spend-month')).toHaveText(/^[A-Z][a-z]+: nothing spent yet of \$0\.20\.$/);

    // the first photo is described with the API key
    await page.goto(backend.url + '/add');
    await page.getByTestId('library-input').setInputFiles(`${PHOTOS}graphic-tee.jpg`);
    await expect(page.getByTestId('queue-item')).toBeVisible({ timeout: 30_000 });
    await page.getByRole('link', { name: 'See them in your closet' }).click();
    await expect(page.getByTestId('tile').first()).toContainText('Navy polo', { timeout: 60_000 });

    await page.goto(backend.url + '/settings');
    // $0.04 is left, less than one more photo could cost: the key can't be used again this month
    await expect(page.getByTestId('claude-line')).toHaveText("This month's limit for the API key is reached, and your Claude plan can't be used.", { timeout: 20_000 });
    await page.goto(backend.url + '/settings/advanced');
    await expect(limit).toHaveValue('0.2');
    await expect(section.getByTestId('spend-month')).toHaveText(/^[A-Z][a-z]+: \$0\.16 of \$0\.20 spent\.$/);
    await expect(section.locator('dd', { hasText: '$0.16' })).toHaveCount(0);   // this month is said once, in its sentence
    await more.getByText('Spending so far').click();
    await expect(more.getByTestId('spend-requests')).toHaveText('This month 1 request went to Claude with the API key.');
    await expect(section.getByTestId('spend-history')).toHaveCount(0);
    await expect(more.getByText(/^Costs are worked out from Anthropic's prices as written down on 3 Nov 2026\. Your Anthropic account shows what was really charged/)).toBeVisible();
    // the token counts are no longer shown (the assessment's step 6 removed the Details table)
    await expect(section.getByText('20,000', { exact: true })).toHaveCount(0);

    // the next one would pass the limit: it is not sent, and it says why
    await page.goto(backend.url + '/add');
    await page.getByRole('button', { name: 'Clear list' }).click();
    await page.getByTestId('library-input').setInputFiles(`${PHOTOS}jeans.jpg`);
    await expect(page.getByTestId('queue-item')).toBeVisible({ timeout: 30_000 });
    let waitingId = '';
    await expect.poll(async () => {
      const items = (await (await page.request.get(backend.url + '/api/items')).json()).items as { id: string; tag_state: string }[];
      const waiting = items.find((i) => i.tag_state === 'waiting');
      if (!waiting) return null;
      waitingId = waiting.id;
      return (await (await page.request.get(`${backend.url}/api/items/${waiting.id}`)).json()).tag_error;
    }, { timeout: 30_000 }).toMatch(/spending limit for the API key has been reached/);

    // the import list says it too: the row waits, and why is said once above the rows
    const row = page.getByTestId('queue-row').filter({ hasText: 'jeans.jpg' });
    await expect(row.getByTestId('queue-title')).toHaveText("Waiting for this month's limit to allow it", { timeout: 30_000 });
    const why = page.getByTestId('import-waiting');
    await expect(why).toContainText("This month's spending limit for the API key has been reached");
    await expect(why.getByRole('link', { name: 'Open Settings' })).toHaveAttribute('href', '/settings');
    await expect(row.getByTestId('queue-item')).toHaveAttribute('href', `/item/${waitingId}`);

    await page.goto(`${backend.url}/item/${waitingId}`);
    const notice = page.getByTestId('progress-strip');
    // the strip on the picture says what it waits for, and where to see to it
    await expect(notice).toContainText("Waiting for this month's limit to allow it");
    await expect(notice).toContainText('You can see to it in Settings.');
    await notice.getByRole('link', { name: 'Open Settings' }).click();
    await expect(page).toHaveURL(/\/settings$/);
    const line = page.getByTestId('claude-line');
    await expect(line).toHaveText("This month's limit for the API key is reached, and your Claude plan can't be used.", { timeout: 20_000 });
    await page.getByRole('link', { name: 'Manage how Nines reaches Claude' }).click();
    await expect(section.getByText(/This month's limit is reached/)).toBeVisible();
    await expect(section.getByTestId('spend-waiting')).toHaveText(
      "If your plan can't be used, describing the item waiting with the API key would cost about $0.10 at most.");
    await expect(section.getByTestId('tags-waiting')).toHaveText('1 item is waiting to be described.');
  });
});
