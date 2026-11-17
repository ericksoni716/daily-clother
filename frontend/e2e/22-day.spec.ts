import { resolve } from 'node:path';
import { axeViolations } from './a11y';
import { expect, PASS, test } from './fixtures';
import { startBackend, type Backend } from './server';

const SHOTS = resolve(import.meta.dirname, '..', '..', 'docs', 'screenshots');

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

    // a sentence with nothing in it is said so, and nothing is kept
    await page.getByRole('button', { name: 'Somewhere else, or out all day? Tell Closet' }).click();
    const box = page.getByLabel("What's different about today, or the days ahead?");
    await expect(box).toBeFocused();
    await expect(page.getByText('Nothing from your closet is sent.')).toBeVisible();
    await box.fill('Hello there');
    await page.getByRole('button', { name: 'Save' }).click();
    await expect(page.getByTestId('day-note-message')).toContainText("couldn't find anything about your day");
    await expect(page.getByTestId('day-note')).toHaveCount(0);

    await box.fill('In Lisbon for four days, outside walking the city from noon to six');
    await page.getByRole('button', { name: 'Save' }).click();
    const note = page.getByTestId('day-note');
    await expect(note).toContainText('Lisbon, Portugal');
    await expect(note).toContainText('outside noon to 6pm');
    await expect(note).toContainText('walking the city');
    await expect(note).toContainText('until ');
    await expect(page.getByTestId('day-note-message')).toHaveCount(0);

    // Today now dresses for Lisbon: what its hours feel like, the rain and the wind
    await expect(day).toContainText('Lisbon');
    await expect(day).toContainText('feels like about 13°C');
    await expect(day).toContainText('rain');
    await expect(day).toContainText('windy');
    await expect(page.getByTestId('no-weather')).toHaveCount(0);
    await expect(page.getByTestId('current-outfit').getByTestId('piece').first()).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);
    await page.screenshot({ path: resolve(SHOTS, 'today-day-note.png') });

    // it is still there after a reload, and home's place in Settings is untouched
    await page.reload();
    await expect(page.getByTestId('day-note')).toContainText('Lisbon, Portugal');
    const settings = await (await page.request.get(backend.url + '/api/settings')).json();
    expect(settings.place.name).toContain('New York');

    // Change opens the sentence again; a wedding makes the day formal
    await page.getByTestId('day-note').getByRole('button', { name: 'Change' }).click();
    await expect(box).toHaveValue('In Lisbon for four days, outside walking the city from noon to six');
    await box.fill('A wedding in Lisbon today');
    await page.getByRole('button', { name: 'Save' }).click();
    await expect(page.getByTestId('day-note')).toContainText('a wedding');
    await expect(page.getByRole('group', { name: 'Occasion' }).getByRole('button', { name: 'Formal', pressed: true })).toBeVisible();

    await page.getByRole('button', { name: 'Clear the note about your day' }).click();
    await expect(page.getByTestId('day-note')).toHaveCount(0);
    await expect(day).toContainText('a mild day');
  });
});
