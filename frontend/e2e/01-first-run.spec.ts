import { expect, test } from './fixtures';

test('a first run opens straight on the empty closet: there is no passphrase to choose', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Your closet' })).toBeVisible();
  await expect(page.getByText('Your closet is empty')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Add your first item' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'or look around the demo closet' })).toBeVisible();
  await expect(page.getByLabel('Passphrase')).toHaveCount(0);
});

test('when the door turns this device away, the page says why and offers to reload', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('#closet-title')).toBeVisible();
  // as when Cloudflare's sign-in has run out, or the window's key is missing: every call is answered 401
  const why = 'Sign in through Cloudflare to use Nines at this address.';
  await page.route('**/api/**', (route) => route.fulfill({ status: 401, json: { detail: why } }));
  await page.locator('nav.sidebar').getByRole('link', { name: 'Settings' }).click();
  await expect(page.getByRole('heading', { name: "Nines didn't let this device in" })).toBeVisible();
  await expect(page.getByTestId('refused')).toHaveText(why);
  await page.unroute('**/api/**');
  await page.getByRole('button', { name: 'Reload' }).click();
  await expect(page.getByRole('heading', { name: 'Settings', level: 1 })).toBeVisible();   // back where it was
});

test("the passphrase's old calls tell a page from an older Nines to reload", async ({ page }) => {
  for (const path of ['/api/setup', '/api/login', '/api/logout']) {
    const r = await page.request.post(path, { data: { passphrase: 'a calm green closet' } });
    expect(r.status()).toBe(410);
    expect(await r.json()).toEqual({ detail: 'This page is from an older Nines. Reload the page, then try again.' });
  }
});
