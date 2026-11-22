import type { Page } from '@playwright/test';
import { axeViolations, sideways } from './a11y';
import { expect, PHOTOS, test } from './fixtures';
import { startBackend, type Backend } from './server';

const PHONE = { width: 375, height: 812 };

/** Opens a backend of its own, on the owner's own closet. */
async function openCloset(page: Page, url: string) {
  await page.goto(url + '/');
  await expect(page.locator('#closet-title')).toBeVisible();
}

// Its own backend, with stand-ins for the model and for Claude that take seconds over each step (a cutout, a
// description that says plaid, the plaid measured and not found), so each step can be seen as the owner would.
test.describe('the work on a new item, step by step', () => {
  let backend: Backend;

  test.beforeAll(async () => {
    backend = await startBackend({ fakes: true, stages: true });
  });
  test.afterAll(async () => {
    await backend?.stop();
  });

  test('the tile, the strip and the one line follow each step, then go', async ({ page }) => {
    test.setTimeout(120_000);
    await openCloset(page, backend.url);

    // On Add, the row shows the upload until the item is there, then the item's progress instead, never both
    await page.goto(backend.url + '/add');
    await page.getByTestId('library-input').setInputFiles(`${PHOTOS}graphic-tee.jpg`);
    const row = page.getByTestId('queue-row');
    await expect(row.getByTestId('queue-title')).toHaveText('Removing the background', { timeout: 15_000 });
    await expect(row.getByTestId('queue-status')).toHaveCount(0);

    await page.getByRole('link', { name: 'See them in your closet' }).click();
    const tile = page.getByTestId('tile').first();
    const mark = tile.getByTestId('step-mark');
    const line = page.getByTestId('working-line');
    await tile.click();
    const strip = page.locator('.detail-panel').getByTestId('progress-strip');

    // 1: cutting out, on this computer
    await expect(line).toHaveText('Working on 1 item');
    await expect(mark).toContainText('Step 1 of 3. Removing the background.');
    await expect(strip).toContainText('Step 1 of 3');
    await expect(strip.getByTestId('progress-words')).toHaveText('Removing the background');
    await expect(strip).toContainText('On this computer, in a few seconds.');
    const controls = page.locator('.detail-panel .picture-controls');
    const top = (await controls.boundingBox())!.y;

    // 2: describing and drawing, by Claude; the drawing comes with the description
    await expect(strip.getByTestId('progress-words')).toHaveText('Claude is describing it', { timeout: 10_000 });
    await expect(strip).toContainText('Step 2 of 3');
    await expect(strip).toContainText('The drawing appears as soon as it is described.');
    await expect(mark).toContainText('Step 2 of 3. Claude is describing it.');
    // the one line opens the list of what is being worked on
    await line.click();
    const sheet = page.getByTestId('working-sheet');
    await expect(sheet.getByTestId('working-item')).toHaveCount(1);
    await expect(sheet.getByTestId('working-item')).toContainText('Describing and drawing');
    expect(await axeViolations(page)).toEqual([]);
    await page.screenshot({ path: test.info().outputPath('progress-computer.png') });
    await page.keyboard.press('Escape');
    await expect(sheet).toHaveCount(0);

    // 3: finishing the drawing, the plaid measured from the photo
    await expect(strip.getByTestId('progress-words')).toHaveText('Measuring the plaid from the photo', { timeout: 10_000 });
    await expect(strip).toContainText('Step 3 of 3');
    await expect(mark).toContainText('Step 3 of 3. Measuring the plaid from the photo.');
    await expect(tile).toContainText('Navy plaid polo');   // described by now: the grid has its name
    expect((await controls.boundingBox())!.y).toBe(top);
    expect(await sideways(page)).toEqual([]);

    // done: the strip, the mark and the line go; the page did not move while they came and went
    await expect(strip).toHaveCount(0, { timeout: 10_000 });
    await expect(mark).toHaveCount(0);
    await expect(line).toHaveCount(0);
    await expect(page.getByTestId('pattern-failed')).toBeVisible();   // the stand-in found no plaid, and the page says so
    expect((await controls.boundingBox())!.y).toBe(top);   // the strip lay over the picture
  });

  test.describe('on a phone', () => {
    test.use({ viewport: PHONE, hasTouch: true, isMobile: true });

    test('the step mark, the line and the strip fit the phone', async ({ page }) => {
      test.setTimeout(90_000);
      await openCloset(page, backend.url);
      await page.goto(backend.url + '/add');
      await page.getByTestId('library-input').setInputFiles(`${PHOTOS}marl-sweater.jpg`);
      await expect(page.getByTestId('queue-title').first()).toHaveText('Removing the background', { timeout: 15_000 });
      await page.goto(backend.url + '/');
      const line = page.getByTestId('working-line');
      await expect(line).toHaveText('Working on 1 item');
      await expect(page.getByTestId('step-mark')).toHaveCount(1);
      expect(await sideways(page)).toEqual([]);
      await page.screenshot({ path: test.info().outputPath('progress-closet-phone.png') });
      // the line sits above the tab bar, clear of it
      const bar = (await page.locator('.tabbar').boundingBox())!;
      const pill = (await line.boundingBox())!;
      expect(pill.y + pill.height).toBeLessThanOrEqual(bar.y);

      await page.getByTestId('tile').first().click();
      const strip = page.getByTestId('progress-strip');
      await expect(strip.getByTestId('progress-words')).toHaveText('Claude is describing it', { timeout: 15_000 });
      expect(await sideways(page)).toEqual([]);
      await page.screenshot({ path: test.info().outputPath('progress-item-phone.png') });
      await expect(strip).toHaveCount(0, { timeout: 20_000 });
    });
  });
});
