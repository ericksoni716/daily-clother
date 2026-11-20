import { axeViolations } from './a11y';
import { expect, PASS, test } from './fixtures';
import { startBackend, type Backend } from './server';


// Its own backend: reading the day in the owner's words is a stand-in for Claude, and Lisbon is the one place on the
// stand-in map, with a forecast hour by hour (tests/e2e_backend.py). The owner's closet starts as a copy of the demo
// closet, because the demo closet itself never asks Claude.
test.describe('the day in your words', () => {
  let backend: Backend;

  test.beforeAll(async () => {
    backend = await startBackend({ fakes: true, seed: 'demo' });
  });
  test.afterAll(async () => {
    await backend?.stop();
  });

  test('a day somewhere else: the note is read, Today dresses for that place and its hours, and Clear goes home', async ({ page }) => {
    test.setTimeout(120_000);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(backend.url + '/');
    await page.getByLabel('Passphrase', { exact: true }).fill(PASS);
    await page.getByLabel('Type it again').fill(PASS);
    await page.getByRole('button', { name: 'Set passphrase' }).click();
    await page.getByRole('button', { name: 'Start with my own closet' }).click();

    await page.goto(backend.url + '/today');
    const day = page.getByTestId('day-line');
    await expect(day).toContainText('a mild day');   // home's forecast is out of reach in a test
    await expect(page.getByTestId('current-outfit').getByTestId('piece').first()).toBeVisible();
    await expect(page.getByTestId('day-note')).toHaveCount(0);

    // the way in is behind Change, so an ordinary day's first screen is as it was
    const change = page.getByTestId('day-line').getByRole('button', { name: 'Change', exact: true });
    await change.click();
    // and inside it, folded under where you are, until it is opened (or a note is already kept)
    const fold = page.getByTestId('day-note-fold');
    await expect(fold).not.toHaveAttribute('open', '');
    await fold.getByText('Somewhere else, or out all day?').click();
    const box = page.getByLabel('Say it in a sentence');
    await expect(page.getByText('Nothing from your closet is sent.')).toBeVisible();

    // a sentence with nothing in it is said so, and nothing is kept
    await box.fill('Hello there');
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    await expect(page.getByTestId('day-note-message')).toContainText("couldn't find anything about your day");
    await expect(page.getByTestId('day-note')).toHaveCount(0);

    await box.fill('In Lisbon for four days, outside walking the city from noon to six');
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    const note = page.getByTestId('day-note');
    await expect(note).toContainText('outside noon to 6pm');
    await expect(note).not.toContainText('Lisbon');   // the weather line names the place
    await expect(note).toContainText('until ');
    await expect(note).toHaveAttribute('title', 'In Lisbon for four days, outside walking the city from noon to six');
    await expect(box).toHaveCount(0);   // the panel closed

    // Today now dresses for Lisbon: what its hours feel like, the rain and the wind
    await expect(day).toContainText('Lisbon');
    await expect(day).toContainText('feels like about 13°C');
    await expect(day).toContainText('rain');
    await expect(day).toContainText('windy');
    await expect(page.getByTestId('no-weather')).toHaveCount(0);
    await expect(page.getByTestId('current-outfit').getByTestId('piece').first()).toBeVisible();
    // the note is one line, however long: it never pushes the outfit down by more than that
    expect((await note.boundingBox())!.height).toBeLessThanOrEqual(24);
    expect(await axeViolations(page)).toEqual([]);
    await page.screenshot({ path: test.info().outputPath('today-day-note.png') });

    // it is still there after a reload, and home's place in Settings is untouched
    await page.reload();
    await expect(page.getByTestId('day-note')).toContainText('outside noon to 6pm');
    await expect(day).toContainText('Lisbon');
    const settings = await (await page.request.get(backend.url + '/api/settings')).json();
    expect(settings.place.name).toContain('New York');

    // Change opens the sentence again with what Closet took from it; a wedding makes the day formal
    await change.click();
    await expect(box).toHaveValue('In Lisbon for four days, outside walking the city from noon to six');
    await expect(page.getByTestId('day-note-now')).toContainText('Lisbon, Portugal');
    await expect(page.getByTestId('day-note-now')).toContainText('walking the city');
    expect(await axeViolations(page)).toEqual([]);
    await page.screenshot({ path: test.info().outputPath('today-day-note-change.png') });
    await box.fill('A wedding in Lisbon today');
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    await expect(page.getByTestId('day-note')).toContainText('a wedding');
    await expect(page.getByRole('group', { name: 'Occasion' }).getByRole('button', { name: 'Formal', pressed: true })).toBeVisible();

    await change.click();
    await page.getByRole('button', { name: 'Clear the note' }).click();
    await expect(page.getByTestId('day-note')).toHaveCount(0);
    await expect(day).toContainText('a mild day');
  });
});
