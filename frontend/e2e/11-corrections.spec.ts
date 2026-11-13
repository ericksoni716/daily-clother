import { expect, login, test, useProfile } from './fixtures';

test.afterEach(async ({ page }) => {
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

type Options = { groups: { details: { name: string; value: unknown; words: string }[] }[] };

test('in the demo closet: pick the number of buttons, see the drawing change, undo it from the history', async ({ page }) => {
  await login(page);
  await useProfile(page, 'demo');
  const listed = (await (await page.request.get('/api/items')).json()).items as { id: string; name: string }[];
  const polo = listed.find((i) => i.name === 'Navy polo')!;
  const options = (await (await page.request.get(`/api/items/${polo.id}/details`)).json()) as Options;
  const buttons = options.groups.flatMap((g) => g.details).find((d) => d.name === 'placket_buttons')!;
  const now = buttons.words;
  const want = buttons.value === 3 ? '4' : '3';

  await page.getByTestId('tile').filter({ hasText: 'Navy polo' }).click();
  const detail = page.locator('.detail-panel');
  await detail.getByRole('button', { name: 'Fix the details' }).click();
  const drawing = detail.getByRole('img', { name: 'Navy polo, drawing as it is now' });
  await expect(drawing).toBeVisible();
  const before = (await drawing.getAttribute('src'))!;
  await expect(detail.getByRole('region', { name: 'Collar and neck' })).toBeVisible();

  await detail.getByRole('button', { name: `Number of buttons: ${now}` }).click();
  const choices = detail.getByRole('group', { name: 'Choices for the number of buttons' });
  await expect(choices.getByRole('button', { name: now, exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(choices.locator('img').nth(1)).toBeVisible();   // the choices are small drawings of this polo
  await choices.getByRole('button', { name: want, exact: true }).click();
  await expect(drawing).not.toHaveAttribute('src', before);
  await expect(detail.getByRole('button', { name: `Number of buttons: ${want} (set by you)` })).toBeVisible();

  // the history says what changed, and it can be undone
  await detail.locator('summary', { hasText: 'History' }).click();
  const line = `You changed the number of buttons from ${now} to ${want}`;
  await expect(detail.getByText(line)).toBeVisible();
  await detail.getByRole('button', { name: `Undo: ${line}` }).click();
  await expect(drawing).toHaveAttribute('src', before);
  await expect(detail.getByText(`You put the number of buttons back to ${now}`)).toBeVisible();
  await expect(detail.getByText(`${line} (undone)`)).toBeVisible();

  // saying what is wrong: the demo closet is never sent to Claude
  await detail.getByLabel("Or say what's wrong").fill('it has three buttons');
  await detail.getByRole('button', { name: 'Ask Claude' }).click();
  await expect(detail.getByRole('alert')).toContainText('never sent to Claude');
});

test('on a phone the details fit the screen', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await useProfile(page, 'demo');
  await page.getByTestId('tile').filter({ hasText: 'Blue oxford shirt' }).click();
  await page.getByRole('button', { name: 'Fix the details' }).click();
  await page.getByRole('button', { name: /^Collar:/ }).click();
  const choices = page.getByRole('group', { name: 'Choices for the collar' });
  await expect(choices.locator('img').nth(1)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test('offline: fixing the details and undoing are off, and say why', async ({ page, context }) => {
  await login(page);
  await useProfile(page, 'demo');
  await page.waitForFunction(() => navigator.serviceWorker?.controller != null, null, { timeout: 15_000 });
  await page.reload();
  await page.getByTestId('tile').filter({ hasText: 'Navy polo' }).click();
  const panel = page.locator('.detail-panel');
  await expect(panel.getByRole('button', { name: 'Fix the details' })).toBeEnabled();
  await page.waitForLoadState('networkidle');

  await context.setOffline(true);
  await page.reload();
  await expect(page.getByText('Offline: showing your saved closet')).toBeVisible();
  const fix = panel.getByRole('button', { name: 'Fix the details' });
  await expect(fix).toBeDisabled();
  await expect(fix).toHaveAttribute('title', /needs Closet on your computer/i);
  await panel.locator('summary', { hasText: 'History' }).click();
  await expect(panel.getByText("You're offline, so the history can't be shown or undone right now.")).toBeVisible();
  await context.setOffline(false);
});
