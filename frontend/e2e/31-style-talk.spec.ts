import type { Page } from '@playwright/test';
import { axeViolations, sideways } from './a11y';
import { expect, stayOnCloset, test } from './fixtures';
import { startBackend, type Backend } from './server';

const section = (page: Page) => page.locator('section[aria-labelledby="s-style"]');
const talkSheet = (page: Page) => page.getByTestId('style-talk-sheet');
const box = (page: Page) => page.getByRole('textbox', { name: 'Tell Claude about your style' });
const thread = (page: Page) => page.getByRole('list', { name: 'Your conversation with Claude about your style' });
const KEPT = 'I run warm, so one layer fewer than most people.';

// Its own backend, with the stand-in for Claude in the style conversation (tests/e2e_backend.py, `fake_chat`): it
// answers after 1.5 seconds, and a message about running warm is answered with a line to keep. The owner's closet
// starts as a copy of the demo closet.
test.describe('talking to Claude about your style', () => {
  let backend: Backend;

  test.beforeAll(async () => {
    backend = await startBackend({ fakes: true, seed: 'demo' });
  });
  test.afterAll(async () => {
    await backend?.stop();
  });

  test('a question, then talk, a line offered and saved, shown in Settings with where it came from, and removed', async ({ page }) => {
    test.setTimeout(120_000);
    await page.setViewportSize({ width: 390, height: 844 });
    await stayOnCloset(page, backend.url);
    await expect(page.locator('#closet-title, #today-title').first()).toBeVisible();

    // Settings, Your style: the starting lines, each marked as one
    await page.goto(backend.url + '/settings');
    const summary = section(page).getByTestId('style-summary-line');
    await expect(summary.first()).toContainText('I carry an umbrella');
    await expect(summary.first()).toContainText('Starting rule');

    // with nothing said today, the conversation opens on a question the stylist can't infer; skip it, then undo
    await section(page).getByRole('button', { name: 'Talk to Claude about your style' }).click();
    const sheet = talkSheet(page);
    const question = sheet.getByTestId('style-question');
    await expect(question.getByRole('heading', { name: 'Do you tend to feel the cold, or run warm?' })).toBeVisible();
    await question.getByRole('button', { name: 'Skip' }).click();
    await expect(sheet.getByTestId('style-answered')).toContainText('Skipped.');
    await expect(question.getByRole('heading', { name: 'What do you wear for work?' })).toBeVisible();
    await sheet.getByTestId('style-answered').getByRole('button', { name: 'Undo' }).click();
    await expect(question.getByRole('heading', { name: 'Do you tend to feel the cold, or run warm?' })).toBeVisible();
    expect(await axeViolations(page, '[data-testid="style-talk-sheet"]')).toEqual([]);
    expect(await sideways(page)).toEqual([]);
    await page.screenshot({ path: test.info().outputPath('style-question.png') });

    // say something in your own words: Claude answers and offers a line, which is not kept until saved
    await box(page).fill('I always feel warm on the bus');
    await sheet.getByRole('button', { name: 'Send', exact: true }).click();
    const turn = thread(page).getByTestId('talk-turn').first();
    await expect(turn.getByRole('status')).toHaveText('Claude is answering…');
    await expect(turn).toContainText("Noted. I'll dress you a little lighter than the weather suggests.", { timeout: 20_000 });
    await expect(sheet.getByTestId('style-question')).toHaveCount(0);   // once something is said, no question
    const keep = turn.getByRole('group', { name: 'Keep this for other days?' });
    await expect(keep).toContainText(KEPT);
    expect((await (await page.request.get(backend.url + '/api/style/profile')).json()).text).not.toContain(KEPT);
    expect(await axeViolations(page, '[data-testid="style-talk-sheet"]')).toEqual([]);
    expect(await sideways(page)).toEqual([]);
    await page.screenshot({ path: test.info().outputPath('style-talk.png') });

    // saved: the line is in Settings with where it came from; Undo takes it out and offers it again
    await keep.getByRole('button', { name: 'Save to Your style' }).click();
    await expect(turn.getByTestId('talk-kept')).toHaveText('Saved to Your style.');
    await turn.getByRole('button', { name: 'Undo' }).click();
    await expect(keep).toBeVisible();
    expect((await (await page.request.get(backend.url + '/api/style/profile')).json()).is_default).toBe(true);
    await keep.getByRole('button', { name: 'Save to Your style' }).click();
    await expect(turn.getByTestId('talk-kept')).toHaveText('Saved to Your style.');
    await sheet.getByRole('button', { name: 'Done' }).click();
    const line = summary.filter({ hasText: KEPT });
    await expect(line).toContainText('From a conversation today');
    await page.reload();
    await expect(line).toContainText('From a conversation today');

    // every line, to change or remove: removing it takes it out of what Claude reads, with Undo
    await section(page).getByRole('button', { name: 'Change the lines' }).click();
    const lines = page.getByTestId('style-lines-sheet');
    await expect(lines.getByTestId('style-line')).toHaveCount(2);
    await lines.getByRole('button', { name: `Remove “${KEPT}”` }).click();
    await expect(lines.getByTestId('style-line')).toHaveCount(1);
    await expect(lines.getByRole('status')).toContainText(`Removed “${KEPT}”`);
    expect((await (await page.request.get(backend.url + '/api/style/profile')).json()).text).not.toContain(KEPT);
    expect(await axeViolations(page, '[data-testid="style-lines-sheet"]')).toEqual([]);
    await page.screenshot({ path: test.info().outputPath('style-lines.png') });
    await lines.getByRole('button', { name: 'Done' }).click();
    await expect(summary.filter({ hasText: KEPT })).toHaveCount(0);
  });

  // The review of the shared parts left the conversation saying a failed read in the server's own words, with no way to
  // ask again but closing the sheet (BACKLOG, "The review of the shared parts"): it says it as every screen does.
  test('a conversation that cannot be read says so in the words every screen uses, and Try again opens it', async ({ page }) => {
    let fail = true;
    await page.route('**/api/style/talk', (route) => (fail && route.request().method() === 'GET'
      ? route.fulfill({ status: 500, json: { detail: 'Internal Server Error' } }) : route.fallback()));
    await page.setViewportSize({ width: 390, height: 844 });
    await stayOnCloset(page, backend.url);
    await page.goto(backend.url + '/settings');
    await section(page).getByRole('button', { name: 'Talk to Claude about your style' }).click();
    const failed = talkSheet(page).getByTestId('failed-style-talk');
    await expect(failed).toContainText("Couldn't load the conversation about your style.");
    await expect(failed).toContainText('Nines on your computer answered with a fault. Trying again usually helps.');
    await expect(talkSheet(page)).not.toContainText('Internal Server Error');
    fail = false;
    await failed.getByRole('button', { name: 'Try again' }).click();
    await expect(failed).toHaveCount(0);
    await expect(box(page)).toBeVisible();
  });
});
