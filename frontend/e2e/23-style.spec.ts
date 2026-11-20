import { axeViolations, sideways, smallTargets } from './a11y';
import { expect, PASS, test } from './fixtures';
import { startBackend, type Backend } from './server';

const MINE = 'I run warm, so one layer fewer than most people.\nNo ties unless it is a wedding.';

// Its own backend, so the style profile starts as the starting text whatever other tests did. The owner's closet
// starts as a copy of the demo closet, so there are pieces to open.
test.describe('your style and how I wear it', () => {
  let backend: Backend;

  test.beforeAll(async () => {
    backend = await startBackend({ fakes: true, seed: 'demo' });
  });
  test.afterAll(async () => {
    await backend?.stop();
  });

  test('the style profile is written, kept, and taken back to the starting text; a piece keeps how I wear it', async ({ page }) => {
    test.setTimeout(120_000);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(backend.url + '/');
    await page.getByLabel('Passphrase', { exact: true }).fill(PASS);
    await page.getByLabel('Type it again').fill(PASS);
    await page.getByRole('button', { name: 'Set passphrase' }).click();
    await page.getByRole('button', { name: 'Start with my own closet' }).click();
    const starting = (await (await page.request.get(backend.url + '/api/style/profile')).json()).default_text as string;

    // Settings → Your style, the first group: the starting text, short, with the whole of it to edit in a sheet
    await page.goto(backend.url + '/settings');
    const section = page.locator('section[aria-labelledby="s-style"]');
    await expect(section.getByRole('heading', { name: 'Your style' })).toBeVisible();
    const headings = await page.locator('.settings-section h2').allTextContents();
    expect(headings[0]).toBe('Your style');
    await expect(section.getByTestId('style-summary')).toHaveText(starting);
    expect(await section.getByTestId('style-summary').evaluate((el) => getComputedStyle(el).webkitLineClamp)).toBe('3');
    const edit = section.getByRole('button', { name: 'Edit the text' });
    const box = section.getByRole('textbox', { name: 'About how I dress' });
    await expect(box).toHaveCount(0);
    await edit.click();
    await expect(box).toHaveValue(starting);
    const save = section.getByRole('button', { name: 'Save', exact: true });
    const back = section.getByRole('button', { name: 'Back to the starting text' });
    await expect(save).toBeDisabled();
    await expect(back).toHaveCount(0);
    await expect(section.locator('.settings-style-count')).toContainText(`${starting.length} / 4000`);

    // typing makes it a change; Save keeps it through a reload
    await box.fill(MINE);
    await expect(save).toBeEnabled();
    await expect(section.locator('.settings-style-count')).toContainText(`${MINE.length} / 4000`);
    await save.click();
    await expect(page.locator('.toast').filter({ hasText: 'Saved' })).toBeVisible();
    await expect(save).toBeDisabled();
    await expect(back).toBeVisible();
    await page.reload();
    await expect(section.getByTestId('style-summary')).toHaveText(MINE);
    await edit.click();
    await expect(box).toHaveValue(MINE);
    await expect(back).toBeVisible();

    // near the longest text allowed the count turns to the warning colour
    await box.fill('x'.repeat(3900));
    await expect(section.locator('.settings-style-count')).toHaveClass(/is-warn/);
    await box.fill(MINE);
    await expect(save).toBeDisabled();

    // checked and pictured on a phone, with the owner's own words in it
    await section.scrollIntoViewIfNeeded();
    await expect(page.locator('.toast')).toHaveCount(0, { timeout: 15_000 });
    expect(await axeViolations(page, 'section[aria-labelledby="s-style"]')).toEqual([]);
    expect(await sideways(page)).toEqual([]);
    expect((await smallTargets(page)).filter((t) => /settings-style|Save|starting text|About how/.test(t))).toEqual([]);
    const boxSize = (await box.boundingBox())!;
    const sectionSize = (await section.boundingBox())!;
    expect(boxSize.width).toBeGreaterThan(sectionSize.width - 2 * 24);   // the full width of the card, inside its padding
    await box.blur();
    await page.evaluate(() => document.querySelector('[data-testid="style-sheet"]')!.scrollIntoView({ block: 'start' }));
    await page.screenshot({ path: test.info().outputPath('settings-style.png') });

    // Back to the starting text: the starting words again, kept
    await back.click();
    await expect(box).toHaveValue(starting);
    await expect(back).toHaveCount(0);
    await page.reload();
    await expect(section.getByTestId('style-summary')).toHaveText(starting);
    await edit.click();
    await expect(box).toHaveValue(starting);

    // a piece: its one notes box, under About it, kept through a reload
    await page.goto(backend.url + '/');
    await page.getByTestId('tile').filter({ hasText: 'Oatmeal henley' }).click();
    const wear = page.getByRole('textbox', { name: 'Notes for you and Claude' });
    await expect(wear).toHaveAttribute('placeholder', 'e.g. only with the navy suit; runs small in the shoulders; great for dinners out');
    await expect(page.getByText('Claude reads these when it chooses your outfits.')).toBeVisible();
    await wear.fill('Under the navy blazer, for dinners out');
    await wear.blur();
    await expect(page.locator('.toast').filter({ hasText: /could|error/i })).toHaveCount(0);
    const id = new URL(page.url()).pathname.split('/').at(-1)!;
    await expect.poll(async () => (await (await page.request.get(`${backend.url}/api/items/${id}`)).json()).wear_notes)
      .toBe('Under the navy blazer, for dinners out');
    await page.reload();
    await expect(page.getByRole('textbox', { name: 'Notes for you and Claude' })).toHaveValue('Under the navy blazer, for dinners out');
    await expect(page.locator('.detail textarea:not([aria-label="Name"])')).toHaveCount(1);   // one box for notes, not four
  });
});
