import { axeViolations } from './a11y';
import { expect, goToCloset, test } from './fixtures';

// A restore cut short is put right when Nines starts (backend/tests/test_backup.py); the page then says what was
// done, once. The shared server has had no such restore, so its answer is stood in for here.

test('a restore put right at start-up is told once, on every screen, until OK', async ({ page }) => {
  const message = 'A restore was interrupted; your closet was put back as it was before the restore.';
  let notice: { at: string; outcome: string; message: string } | null = { at: '2026-11-15T03:00:00Z', outcome: 'undone', message };
  let dismissed = 0;
  await page.route('**/api/restore-notice', (route) => {
    if (route.request().method() === 'DELETE') {
      dismissed += 1;
      notice = null;
      return route.fulfill({ status: 204 });
    }
    return route.fulfill({ json: { notice } });
  });
  await goToCloset(page);
  const banner = page.getByTestId('restore-notice');
  // told after the closet was drawn, it waits for the next screen rather than pushing this one down
  await page.locator('nav.sidebar').getByRole('link', { name: 'Settings' }).click();
  await expect(banner).toContainText(message);
  await page.locator('nav.sidebar').getByRole('link', { name: 'Closet' }).click();
  await expect(banner).toBeVisible();
  expect(await axeViolations(page)).toEqual([]);

  await banner.getByRole('button', { name: 'OK' }).click();
  await expect(banner).toHaveCount(0);
  expect(dismissed).toBe(1);
  const askedAgain = page.waitForResponse('**/api/restore-notice');
  await page.reload();
  await askedAgain;
  await expect(banner).toHaveCount(0);
});

test('without an interrupted restore there is no notice', async ({ page }) => {
  await goToCloset(page);
  expect((await (await page.request.get('/api/restore-notice')).json()).notice).toBeNull();
  await expect(page.getByTestId('restore-notice')).toHaveCount(0);
});
