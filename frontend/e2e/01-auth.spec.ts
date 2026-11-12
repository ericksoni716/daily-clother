import { expect, PASS, test } from './fixtures';

test('first run: set a passphrase and land in the app', async ({ page }) => {
  const s = await (await page.request.get('/api/session')).json();
  test.skip(!s.setup_required, 'The passphrase was already set (spec run out of order).');

  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Welcome to Closet' })).toBeVisible();

  // too short, then mismatched
  await page.getByLabel('Passphrase', { exact: true }).fill('short');
  await page.getByLabel('Type it again').fill('short');
  await page.getByRole('button', { name: 'Set passphrase' }).click();
  await expect(page.getByRole('alert')).toContainText('at least 8 characters');
  await page.getByLabel('Passphrase', { exact: true }).fill(PASS);
  await page.getByLabel('Type it again').fill(PASS + 'x');
  await page.getByRole('button', { name: 'Set passphrase' }).click();
  await expect(page.getByRole('alert')).toContainText("don't match");

  await page.getByLabel('Type it again').fill(PASS);
  await page.getByRole('button', { name: 'Set passphrase' }).click();
  await expect(page.getByRole('heading', { name: "You're set" })).toBeVisible();
  await expect(page.getByText('tailscale serve --bg')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Open the demo closet' })).toBeVisible();

  await page.getByRole('button', { name: 'Start with my own closet' }).click();
  await expect(page.getByRole('heading', { name: 'Your closet' })).toBeVisible();
  await expect(page.getByText('Your closet is empty')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Add your first item' })).toBeVisible();
});

test('the server refuses a second setup and shows why', async ({ page }) => {
  const r = await page.request.post('/api/setup', { data: { passphrase: 'another passphrase' } });
  expect(r.status()).toBe(409);
});

test('log out, a wrong passphrase is refused, the right one logs in', async ({ page }) => {
  await page.goto('/');
  // a fresh context has no cookie
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
  await page.getByLabel('Passphrase').fill('not the passphrase');
  await page.getByRole('button', { name: 'Open my closet' }).click();
  await expect(page.getByRole('alert')).toHaveText('That passphrase is not right.');

  await page.getByLabel('Passphrase').fill(PASS);
  await page.getByRole('button', { name: 'Open my closet' }).click();
  await expect(page.locator('#closet-title')).toBeVisible();

  await page.locator('nav.sidebar').getByRole('link', { name: 'Settings' }).click();
  await page.getByRole('button', { name: 'Log out' }).click();
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
  // the session really ended on the server
  expect((await page.request.get('/api/items')).status()).toBe(401);
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
});
