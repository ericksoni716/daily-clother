import { type Page } from '@playwright/test';
import { axeViolations } from './a11y';
import { expect, goToCloset, test } from './fixtures';

// A product's page is never fetched from the web: tests/e2e_backend.py's ShopPages serves made-up pages for
// shop.example, read by Nines itself ($68.00 the first time each is read). The banner of code-shirt shows a made-up
// checkout code, 40% off.

/** Sends a product's page as a link, waits for Nines to read it, and gives the new wish's id. */
async function sendLink(page: Page, url: string): Promise<string> {
  const wish = await (await page.request.post('/api/wishlist/link', { data: { url } })).json();
  await expect.poll(async () => (await (await page.request.get(`/api/wishlist/${wish.id}/finds`)).json()).run?.state,
    { timeout: 30_000 }).toBe('done');
  return wish.id;
}

test('a page sent with a code in its text shows the price with the code, and that Nines saw it', async ({ page }) => {
  await goToCloset(page);
  const id = await sendLink(page, 'https://shop.example/code-shirt');
  await page.goto(`/wardrobe/wish/${id}`);
  const find = page.getByTestId('wish').getByTestId('find');
  await expect(find).toContainText('Example Shop · $68.00');
  await expect(find.getByTestId('find-code')).toHaveText('$40.80 with code TEST40 at checkout (40% off)');
  // who saw it, and the button to change it, in the find's fold
  await find.getByTestId('find-more').locator('summary').click();
  await expect(find.getByTestId('find-code-from')).toHaveText('Nines saw this code on the page.');
  await expect(find.getByRole('button', { name: 'Change the code' })).toBeVisible();
  expect(await axeViolations(page, '[data-testid="find"]')).toEqual([]);

  // the wishlist's row says the price with the code too
  await page.goto('/wardrobe/wishlist');
  const row = page.getByTestId('wishlist').getByTestId('wish-row').filter({ hasText: 'Linen shirt with a code' });
  await expect(row).toContainText('$40.80 with code TEST40 at Example Shop', { timeout: 30_000 });
});

test('add a code by hand and see the price with it, change it to an amount off, then remove it', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await goToCloset(page);
  const id = await sendLink(page, 'https://shop.example/linen-shirt');
  await page.goto(`/wardrobe/wish/${id}`);
  const find = page.getByTestId('wish').getByTestId('find');
  await expect(find).toContainText('Example Shop · $68.00');
  await expect(find.getByTestId('find-code')).toHaveCount(0);

  await find.getByTestId('find-more').locator('summary').click();   // in the find's fold
  await find.getByRole('button', { name: 'Add a code' }).click();
  const sheet = page.getByTestId('code-sheet');
  await expect(sheet.getByRole('heading', { name: 'A code at checkout' })).toBeVisible();
  await expect(sheet.getByRole('button', { name: 'Remove the code' })).toHaveCount(0);   // nothing to remove yet
  const code = sheet.getByLabel('Code', { exact: true });
  await code.fill('test20');
  await sheet.getByRole('button', { name: 'Save' }).click();
  await expect(sheet.getByRole('alert')).toHaveText('Type the percent off as a number, like 40.');
  // what does not fit, Nines says
  await sheet.getByLabel('Percent off', { exact: true }).fill('95');
  await sheet.getByRole('button', { name: 'Save' }).click();
  await expect(sheet.getByRole('alert')).toHaveText('The percent off is a number from 1 to 90.');
  await sheet.getByLabel('Percent off', { exact: true }).fill('20');
  expect(await axeViolations(page, '[data-testid="code-sheet"]')).toEqual([]);
  await sheet.getByRole('button', { name: 'Save' }).click();
  await expect(sheet).toHaveCount(0);
  await expect(find.getByTestId('find-code')).toHaveText('$54.40 with code TEST20 at checkout (20% off)');
  await expect(find.getByTestId('find-code-from')).toHaveCount(0);   // you typed it: nothing to say who saw it
  await expect(find.getByTestId('find-drop')).toHaveText('Was $68.00, now $54.40 with code TEST20 (20% less)');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  // a code you add is not news to you
  await expect.poll(async () => (await (await page.request.get('/api/wishlist/news')).json()).news).toEqual([]);

  // an amount off instead, in the find's currency
  await find.getByRole('button', { name: 'Change the code' }).click();
  await expect(code).toHaveValue('TEST20');
  await sheet.getByRole('button', { name: 'Amount off' }).click();
  await sheet.getByLabel('Amount off, in USD', { exact: true }).fill('10');
  await sheet.getByRole('button', { name: 'Save' }).click();
  await expect(find.getByTestId('find-code')).toHaveText('$58.00 with code TEST20 at checkout ($10.00 off)');

  // removed: the price is the shop's again
  await find.getByRole('button', { name: 'Change the code' }).click();
  await sheet.getByRole('button', { name: 'Remove the code' }).click();
  await expect(sheet).toHaveCount(0);
  await expect(find.getByTestId('find-code')).toHaveCount(0);
  await expect(find.getByTestId('find-drop')).toHaveCount(0);
  await expect(find.getByRole('button', { name: 'Add a code' })).toBeVisible();
});
