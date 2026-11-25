import type { Page } from '@playwright/test';
import { expect, goToCloset, openFold, serviceWorkerInCharge, test, useProfile } from './fixtures';
import { startBackend, type Backend } from './server';


test.afterEach(async ({ page }) => {
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

type Options = { groups: { details: { name: string; value: unknown; words: string }[] }[] };

test('in the demo closet: pick the number of buttons, see the drawing change, undo it from the history', async ({ page }) => {
  await goToCloset(page);
  await useProfile(page, 'demo');
  const listed = (await (await page.request.get('/api/items')).json()).items as { id: string; name: string }[];
  const polo = listed.find((i) => i.name === 'Navy polo')!;
  const options = (await (await page.request.get(`/api/items/${polo.id}/details`)).json()) as Options;
  const buttons = options.groups.flatMap((g) => g.details).find((d) => d.name === 'placket_buttons')!;
  const now = buttons.words;
  const want = buttons.value === 3 ? '4' : '3';

  await page.getByTestId('tile').filter({ hasText: 'Navy polo' }).click();
  const detail = page.locator('.detail-panel');
  await detail.getByRole('button', { name: 'Something wrong? Change the details' }).click();
  // the demo closet is never sent to Claude: the sheet opens on the details one by one, says why, and has no box
  const sheet = page.getByRole('dialog', { name: 'Fix the details' });
  await expect(sheet.getByText('The demo closet is never sent to Claude, so you change its details one by one here.')).toBeVisible();
  await expect(sheet.getByRole('textbox')).toHaveCount(0);
  await expect(sheet.getByRole('button', { name: "Say what's wrong instead" })).toHaveCount(0);
  const drawing = sheet.getByRole('img', { name: 'Navy polo, drawing as it is now' });
  await expect(drawing).toBeVisible();
  const before = (await drawing.getAttribute('src'))!;
  await expect(sheet.getByRole('region', { name: 'Collar and neck' })).toBeVisible();

  await sheet.getByRole('button', { name: `Number of buttons: ${now}` }).click();
  const choices = sheet.getByRole('group', { name: 'Choices for the number of buttons' });
  await expect(choices.getByRole('button', { name: now, exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(choices.locator('img').nth(1)).toBeVisible();   // the choices are small drawings of this polo
  await choices.getByRole('button', { name: want, exact: true }).click();
  await expect(drawing).not.toHaveAttribute('src', before);
  await expect(sheet.getByRole('button', { name: `Number of buttons: ${want} (set by you)` })).toBeVisible();
  await sheet.getByRole('button', { name: 'Done' }).click();
  await expect(sheet).toHaveCount(0);

  // the history says what changed, and it can be undone
  await detail.locator('summary', { hasText: 'History' }).click();
  const line = `You changed the number of buttons from ${now} to ${want}`;
  await expect(detail.getByText(line)).toBeVisible();
  await detail.getByRole('button', { name: `Undo: ${line}` }).click();
  await expect(detail.getByText(`You put the number of buttons back to ${now}`)).toBeVisible();
  await expect(detail.getByText(`${line} (undone)`)).toBeVisible();
  await detail.getByRole('button', { name: 'Something wrong? Change the details' }).click();
  await expect(drawing).toHaveAttribute('src', before);
  await expect(sheet.getByRole('button', { name: `Number of buttons: ${now}` })).toBeVisible();
});

test('in the demo closet: say what it is with the kind picker, see the drawing change, and undo it', async ({ page }) => {
  await goToCloset(page);
  await useProfile(page, 'demo');
  await page.getByTestId('tile').filter({ hasText: 'Grey hoodie' }).click();
  const detail = page.locator('.detail-panel');
  const drawing = detail.getByRole('img', { name: 'Grey hoodie, drawing' });
  await expect(drawing).toBeVisible();
  const before = (await drawing.getAttribute('src'))!;
  await openFold(detail, 'Details');
  const row = detail.getByTestId('what-is-it');
  const was = (await row.getAttribute('aria-label'))!;
  // with no kind chosen the row says what the summary line says (its category), not "Kind not said yet" (P2)
  await expect(row).toHaveAccessibleName(/^What is it\?: Hoodie · [^.]+$/);

  await row.click();
  const picker = page.getByRole('dialog', { name: 'What is it?' });
  await expect(picker.getByRole('group', { name: 'Groups' })).toBeVisible();
  await picker.getByRole('searchbox').fill('fleece');
  const found = picker.getByRole('region', { name: 'Kinds found' });
  await expect(found.getByRole('button', { name: 'Joggers' })).toHaveCount(0);
  await expect(found.locator('img').first()).toBeVisible();
  await page.waitForLoadState('networkidle');
  await page.screenshot({ path: test.info().outputPath(`kind-picker-computer.png`) });
  await found.getByRole('button', { name: 'Fleece pullover', exact: true }).click();

  await expect(picker).toHaveCount(0);
  await expect(row).toHaveAccessibleName('What is it?: Fleece pullover · Activewear. Set by you');
  await expect(detail.getByTestId('look-line')).toHaveText(/^Fleece pullover · /);   // the line under the name follows
  await expect(detail.getByTestId('kind-pic')).toBeVisible();
  await expect(drawing).not.toHaveAttribute('src', before);
  await page.waitForLoadState('networkidle');
  await page.screenshot({ path: test.info().outputPath(`kind-chosen-computer.png`) });

  // the picker marks the kind it is now
  await row.click();
  await picker.getByRole('searchbox').fill('fleece');
  await expect(picker.getByRole('button', { name: 'Fleece pullover', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await picker.getByRole('button', { name: 'Done' }).click();

  // the Closet can be filtered by what a piece is: the hoodie said to be a fleece pullover is in Activewear now
  await page.locator('.closet-toolbar').getByRole('button', { name: /^Filter/ }).click();
  const filters = page.getByRole('dialog', { name: 'Filter' });
  await filters.getByRole('group', { name: 'What it is' }).getByRole('button', { name: 'Activewear' }).click();
  await filters.getByRole('group', { name: 'Kinds of Activewear' }).getByRole('button', { name: 'Fleece pullover' }).click();
  await filters.getByRole('button', { name: 'Done' }).click();
  // the demo's own fleece pullover, and the hoodie now said to be one
  await expect(page.getByTestId('tile')).toHaveCount(2);
  await expect(page.getByTestId('tile').filter({ hasText: 'Grey hoodie' })).toHaveCount(1);
  await expect(page.getByTestId('tile').filter({ hasText: 'Forest fleece pullover' })).toHaveCount(1);
  // one chip says what is chosen; removing it shows every piece again
  await page.getByRole('button', { name: 'Remove filter: Fleece pullover' }).click();
  await expect(page.getByRole('button', { name: /^Remove filter/ })).toHaveCount(0);

  await detail.locator('summary', { hasText: 'History' }).click();
  const line = 'You changed the kind from not said to fleece pullover';
  await detail.getByRole('button', { name: `Undo: ${line}` }).click();
  await expect(detail.getByText(`${line} (undone)`)).toBeVisible();
  await expect(row).toHaveAttribute('aria-label', was);
  await expect(drawing).toHaveAttribute('src', before);
});

// The review of the shared parts left the History fold saying a failed read in a toast, in the server's own words
// (BACKLOG, "The review of the shared parts"): it says it inside the fold, as every screen does, with Try again.
test('in the demo closet: a history that cannot be read says so in its fold, and Try again reads it', async ({ page }) => {
  let fail = true;
  await page.route('**/api/items/*/history', (route) => (fail && route.request().method() === 'GET'
    ? route.fulfill({ status: 500, json: { detail: 'Internal Server Error' } }) : route.fallback()));
  await goToCloset(page);
  await useProfile(page, 'demo');
  await page.getByTestId('tile').filter({ hasText: 'Navy polo' }).click();
  const detail = page.locator('.detail-panel');
  await detail.locator('summary', { hasText: 'History' }).click();
  const failed = detail.getByTestId('failed-history');
  await expect(failed).toContainText("Couldn't load its history.");
  await expect(failed).toContainText('Nines on your computer answered with a fault. Trying again usually helps.');
  await expect(page.getByText('Internal Server Error')).toHaveCount(0);
  fail = false;
  await failed.getByRole('button', { name: 'Try again' }).click();
  await expect(failed).toHaveCount(0);
  await expect(detail.locator('.fix-history .tag-body')).toContainText(/No changes to its description yet\.|You /);
});

test('on a phone the details fit the screen', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await goToCloset(page);
  await useProfile(page, 'demo');
  await page.getByTestId('tile').filter({ hasText: 'Blue oxford shirt' }).click();
  await page.getByRole('button', { name: 'Something wrong? Change the details' }).click();
  const sheet = page.getByRole('dialog', { name: 'Fix the details' });
  await sheet.getByRole('button', { name: /^Collar:/ }).click();
  const choices = sheet.getByRole('group', { name: 'Choices for the collar' });
  await expect(choices.locator('img').nth(1)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  expect(await sheet.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
});

test('offline: fixing the details and undoing are off, and say why', async ({ page, context }) => {
  await goToCloset(page);
  await useProfile(page, 'demo');
  await serviceWorkerInCharge(page);
  await page.reload();
  await page.getByTestId('tile').filter({ hasText: 'Navy polo' }).click();
  const panel = page.locator('.detail-panel');
  await expect(panel.getByRole('button', { name: 'Something wrong? Change the details' })).toBeEnabled();
  await page.waitForLoadState('networkidle');

  await context.setOffline(true);
  await page.reload();
  await expect(page.getByText('Offline: showing your saved closet')).toBeVisible();
  const fix = panel.getByRole('button', { name: 'Something wrong? Change the details' });
  await expect(fix).toBeDisabled();
  await expect(fix).toHaveAttribute('title', /needs Nines on your computer/i);
  await panel.locator('summary', { hasText: 'History' }).click();
  await expect(panel.getByText("You're offline, so the history can't be shown or undone right now.")).toBeVisible();
  await context.setOffline(false);
});

test('in the demo closet: the line under the name says how it sits, and a word opens its detail to fix', async ({ page }) => {
  await goToCloset(page);
  await useProfile(page, 'demo');
  const listed = (await (await page.request.get('/api/items')).json()).items as { id: string; name: string }[];
  const polo = listed.find((i) => i.name === 'Navy polo')!;
  const worn = (await (await page.request.get(`/api/items/${polo.id}`)).json()).as_worn as { part: string; value: string }[];
  expect(worn).toContainEqual(expect.objectContaining({ part: 'sleeve', value: 'short' }));

  await page.getByTestId('tile').filter({ hasText: 'Navy polo' }).click();
  const detail = page.locator('.detail-panel');
  const line = detail.getByTestId('look-line');
  await expect(line).toHaveText(/ · Navy.* · Regular fit · Short sleeves$/);
  await line.getByRole('button', { name: 'Short sleeves' }).click();

  // "Fix the details" opens on the details one by one, at the sleeve length, with its choices
  const sheet = page.getByRole('dialog', { name: 'Fix the details' });
  await expect(detail.getByRole('button', { name: 'Something wrong? Change the details' })).toHaveAttribute('aria-expanded', 'true');
  const choices = sheet.getByRole('group', { name: 'Choices for the sleeve length' });
  await expect(choices).toBeVisible();
  await choices.getByRole('button', { name: 'long', exact: true }).click();
  await expect(line).toHaveText(/ · Navy.* · Regular fit · Long sleeves$/);
  await sheet.getByRole('button', { name: 'Done' }).click();

  // put it back for the specs after this one
  await detail.locator('summary', { hasText: 'History' }).click();
  await detail.getByRole('button', { name: /^Undo: You changed the sleeve length/ }).click();
  await expect(line).toHaveText(/ · Navy.* · Regular fit · Short sleeves$/);
});

// Its own backend: the owner's closet starts as a copy of the demo closet, and sentences are read by a stand-in for
// Claude (tests/e2e_backend.py, conftest.SENTENCES), so nothing here reaches the real Claude.
test.describe('saying what is wrong, with a stand-in for Claude', () => {
  let backend: Backend;

  test.beforeAll(async () => {
    backend = await startBackend({ fakes: true, seed: 'demo' });
  });
  test.afterAll(async () => {
    await backend?.stop();
  });

  /** Opens the owner's own closet on this backend. */
  async function enter(page: Page) {
    await page.goto(backend.url + '/');
    await expect(page.locator('#closet-title, #today-title').first()).toBeVisible();
  }

  async function polo(page: Page) {
    const listed = (await (await page.request.get(`${backend.url}/api/items`)).json()).items as { id: string; name: string }[];
    const id = listed.find((i) => i.name === 'Navy polo')!.id;
    const options = (await (await page.request.get(`${backend.url}/api/items/${id}/details`)).json()) as Options;
    const buttons = options.groups.flatMap((g) => g.details).find((d) => d.name === 'placket_buttons')!;
    return { id, buttons };
  }

  test('the sheet opens on the box, Claude says what it understood, and the change is made', async ({ page }) => {
    await enter(page);
    const { id, buttons } = await polo(page);
    const [sentence, want] = buttons.value === 2 ? ['it has three buttons', '3'] : ['it has two buttons', '2'];
    await page.goto(`${backend.url}/item/${id}`);
    const fix = page.getByRole('button', { name: 'Something wrong? Tell Claude' });
    await fix.click();
    const sheet = page.getByRole('dialog', { name: 'Fix the details' });
    await expect(sheet.getByRole('img', { name: 'Navy polo, drawing as it is now' })).toBeVisible();
    const box = sheet.getByLabel("What's wrong with it?");
    await expect(box).toBeFocused();   // on a computer, ready to type
    await expect(box).toHaveAttribute('placeholder', 'e.g. it has three buttons');
    await expect(fix).toHaveText('Something wrong? Tell Claude');   // the button keeps its words while the sheet is open

    await box.fill(sentence);
    await sheet.getByRole('button', { name: 'Ask Claude' }).click();
    await expect(sheet.getByText('Claude understood:')).toBeVisible();
    await expect(sheet.getByText(`Number of buttons: ${buttons.words} → ${want}`)).toBeVisible();
    await sheet.getByRole('button', { name: 'Make these changes' }).click();
    await expect(sheet).toHaveCount(0);
    await expect(page.locator('.toast', { hasText: 'Changed as you said' })).toBeVisible();

    // the details one by one, in the same sheet, and back to the box
    await fix.click();
    await sheet.getByRole('button', { name: 'Change the details one by one' }).click();
    await expect(sheet.getByRole('button', { name: new RegExp(`^Number of buttons: ${want}`) })).toBeVisible();
    await expect(sheet.getByRole('textbox')).toHaveCount(0);
    await sheet.getByRole('button', { name: "Say what's wrong instead" }).click();
    await expect(sheet.getByLabel("What's wrong with it?")).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(sheet).toHaveCount(0);
  });

  test('what no detail shows is handed to Claude to draw on, kept on the drawing, and can be taken back', async ({ page }) => {
    await enter(page);
    const { id } = await polo(page);
    await page.goto(`${backend.url}/item/${id}`);
    await page.getByRole('button', { name: 'Something wrong? Tell Claude' }).click();
    const sheet = page.getByRole('dialog', { name: 'Fix the details' });
    const drawing = sheet.getByRole('img', { name: 'Navy polo, drawing as it is now' });
    const before = (await drawing.getAttribute('src'))!;

    // a sentence no detail can show: Claude says so, and it can be handed to "Add to the drawing"
    await sheet.getByLabel("What's wrong with it?").fill('it has a red patch on the chest');
    await sheet.getByRole('button', { name: 'Ask Claude' }).click();
    await expect(sheet.getByText(/^Nothing was changed\./)).toBeVisible();
    await sheet.getByRole('button', { name: 'Have Claude draw it onto the drawing instead' }).click();
    const line = sheet.getByLabel('What should Claude add?');
    await expect(line).toHaveValue('it has a red patch on the chest');
    await expect(line).toBeFocused();
    await sheet.getByRole('button', { name: 'Draw it on', exact: true }).click();
    await expect(page.locator('.toast', { hasText: 'Claude is drawing it on' })).toBeVisible();

    // drawn in the background: the page is read again once it is done
    await expect(sheet.getByText('Added by Claude: red patch on the chest.')).toBeVisible();
    // the copied demo closet keeps no photo to read, so Claude drew from the words alone, and says so
    await expect(sheet.getByText(/^Drew a red patch on the chest\. The photo could not be read/)).toBeVisible();
    await expect(sheet.getByText(/^Drawn in 31 s on your Claude plan, checked once · about \$0\.18/)).toBeVisible();
    await expect(drawing).not.toHaveAttribute('src', before);
    const svg = await (await page.request.get(backend.url + (await drawing.getAttribute('src'))!)).text();
    expect(svg).toContain('#c0392b');
    await expect(line).toHaveValue('');

    // one tap back, and forward again; then every addition taken off, kept to go back to
    await sheet.getByRole('button', { name: 'Go back to the drawing before' }).click();
    await expect(drawing).toHaveAttribute('src', before);
    await sheet.getByRole('button', { name: 'Go to the newer drawing' }).click();
    await expect(sheet.getByText('Added by Claude: red patch on the chest.')).toBeVisible();
    await sheet.getByRole('button', { name: "Take Claude's additions off" }).click();
    await expect(drawing).toHaveAttribute('src', before);
    await expect(sheet.getByTestId('added-parts')).toHaveCount(0);
    await expect(sheet.getByRole('button', { name: 'Go back to the drawing before' })).toBeVisible();
  });

  test('on a phone the sheet opens over the page: nothing moves, and the box shows without scrolling', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await enter(page);
    const { id } = await polo(page);
    await page.goto(`${backend.url}/item/${id}`);
    const name = page.locator('.detail-title');
    await expect(name).toBeVisible();
    await page.waitForLoadState('networkidle');
    const where = async () => ({ y: (await name.boundingBox())!.y, scrollY: await page.evaluate(() => window.scrollY) });
    // The button sits near the foot of a small phone's first screen, where the tab bar can cover it. Bring it to
    // the middle first, as a thumb would, so the tap itself has no reason to scroll and any move is the sheet's.
    const tell = page.getByRole('button', { name: 'Something wrong? Tell Claude' });
    await tell.evaluate((el) => el.scrollIntoView({ block: 'center' }));
    const before = await where();

    await tell.click();
    const box = page.getByRole('dialog', { name: 'Fix the details' }).getByLabel("What's wrong with it?");
    await expect(box).toBeInViewport({ ratio: 1 });
    await expect(box).not.toBeFocused();   // on a phone, focus would open the keyboard over everything
    expect(await where()).toEqual(before);
    await page.waitForLoadState('networkidle');   // the details arrive behind the box: still nothing moves
    expect(await where()).toEqual(before);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  });
});
