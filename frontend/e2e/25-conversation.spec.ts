import { resolve } from 'node:path';
import type { Page, Request, Route } from '@playwright/test';
import { axeViolations, sideways } from './a11y';
import { expect, PASS, test } from './fixtures';
import { startBackend, type Backend } from './server';

// set CONVERSATION_SHOTS to a folder to also save the conversation on a phone and a computer, light and dark, to look at
const REVIEW = process.env.CONVERSATION_SHOTS;

const current = (page: Page) => page.getByTestId('current-outfit');
const read = (page: Page) => page.getByTestId('stylist-read');
const thread = (page: Page) => page.getByRole('list', { name: 'Your conversation with Claude today' });
const turns = (page: Page) => page.getByTestId('talk-turn');
const box = (page: Page) => page.getByRole('textbox', { name: 'Tell Claude what you think' });
const send = (page: Page) => read(page).getByRole('button', { name: 'Send', exact: true });
const pieces = (page: Page) => current(page).getByTestId('piece').allTextContents();

const REPLY = 'Done: the stand-in turned the outfits around.';
const NOT_ANSWERED = "Claude couldn't be reached, so this wasn't answered. The outfits are as they were.";
const DAY = { low_c: 3.2, high_c: 9.8, rain: true };

/** A message sent from Today (a POST to /api/outfits/today that carries `say`). */
const said = (r: Request) => r.url().endsWith('/api/outfits/today') && r.method() === 'POST' && !!(r.postDataJSON() as { say?: string })?.say;

/** Sets the passphrase the first time, logs in after that, and opens Today on a phone with a forecast (as 24-stylist). */
async function open(page: Page, url: string) {
  await page.setViewportSize({ width: 390, height: 844 });
  const session = await (await page.request.get(url + '/api/session')).json();
  // The day is set before the first page opens: logging in can show Today for a moment, and a request of its own
  // without this day would reach Closet late, look like the weather moving and make Claude choose afresh just as a
  // test sends a message (which is then refused: seen once on GitHub).
  await page.route('**/api/outfits/today', async (route: Route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    const response = await route.fetch({ postData: { ...body, ...DAY } });
    const json = await response.json();
    if (response.ok()) {
      Object.assign(json.context, { source: 'forecast', place: 'Brooklyn, New York, United States', rain_chance: 70, summary: 'rain', old: false, message: null });
    }
    await route.fulfill({ response, json });
  });
  await page.goto(url + '/');
  if (session.setup_required) {
    await page.getByLabel('Passphrase', { exact: true }).fill(PASS);
    await page.getByLabel('Type it again').fill(PASS);
    await page.getByRole('button', { name: 'Set passphrase' }).click();
    await page.getByRole('button', { name: 'Start with my own closet' }).click();
  } else {
    await page.getByLabel('Passphrase', { exact: true }).fill(PASS);
    await page.getByRole('button', { name: 'Open my closet' }).click();
  }
  // logged in: the closet or Today opens (before that, leaving the page would lose the login)
  await expect(page.locator('#closet-title, #today-title').first()).toBeVisible();
  await page.goto(url + '/today');
  await expect(read(page)).toBeVisible({ timeout: 20_000 });
  await expect(current(page).getByTestId('outfit-by')).toHaveText('Chosen by Claude');
}

/** Waits until the last message has Claude's answer (or why it has none) and Today has asked again. */
async function answered(page: Page, words: string) {
  await expect(turns(page).last()).toContainText(words, { timeout: 20_000 });
  await expect(turns(page).last().getByRole('status')).toHaveCount(0);
  await expect(page.locator('.today-outfits.is-asking')).toHaveCount(0);
}

/** The carousel shows the outfit at `index` and has finished sliding there (scrolling the page while it slides,
 * as typing in the box does, would stop it part way and show another outfit). */
async function settled(page: Page, index: number) {
  await expect(page.getByRole('heading', { name: new RegExp(`${index + 1} of`) })).toBeVisible();
  await expect.poll(() => page.locator('.today-track').evaluate((el) => Math.round((el.scrollLeft / el.clientWidth) * 100))).toBe(index * 100);
}

async function look(page: Page, name: string) {
  if (!REVIEW) return;
  await page.getByTestId('talk').evaluate((el) => el.scrollIntoView({ block: 'start' }));
  await page.screenshot({ path: resolve(REVIEW, `${name}.png`) });
  await page.screenshot({ path: resolve(REVIEW, `${name}-full.png`), fullPage: true });
}

// Its own backend, with the stand-in for Claude (tests/e2e_backend.py): it chooses after 1.5 seconds, and answers a
// message after 1.5 seconds too (6.5 when it says "slow"), from words in the message: "why" is a question answered in
// words; "fail" cannot be reached; anything else turns the outfits around, and "never", "always" and "fits" offer
// something to keep. The tests run in order on the one closet, so the day's conversation grows from one to the next.
test.describe('talking to Claude about the outfits', () => {
  let backend: Backend;

  test.beforeAll(async () => {
    backend = await startBackend({ fakes: true, seed: 'demo', stylist: true });
  });
  test.afterAll(async () => {
    await backend?.stop();
  });
  // A request still on its way when a test ends is not that test's failure. The page is emptied first, so that it
  // asks nothing more once the day is no longer set for its requests: one request without the day, reaching Closet
  // late, looks like the weather moving and makes Claude choose afresh while the next test sends a message, which
  // is then refused (seen once on GitHub).
  test.afterEach(async ({ page }) => {
    await page.goto('about:blank').catch(() => undefined);
    await page.unrouteAll({ behavior: 'ignoreErrors' });
  });

  test('a message is shown, Claude answers it, and the first outfit changes', async ({ page }) => {
    test.setTimeout(120_000);
    await open(page, backend.url);
    // nothing said yet: no conversation, only the box, and nothing to send
    await expect(thread(page)).toHaveCount(0);
    await expect(box(page)).toBeEnabled();
    await expect(box(page)).toHaveAttribute('placeholder', 'Too dressy? Swap the boots? Ask why…');
    await expect(box(page)).toHaveAttribute('maxlength', '500');
    await expect(send(page)).toBeDisabled();
    await box(page).fill('   ');
    await expect(send(page)).toBeDisabled();

    const before = await pieces(page);
    await box(page).fill('Too dressy for today');
    const request = page.waitForRequest(said);
    await send(page).click();
    // the carousel shows one outfit at a time, so the one in front of the owner is sent with the message
    expect((await request).postDataJSON()).toMatchObject({ say: 'Too dressy for today', looking_at: 0, occasion: 'casual', mood: 'usual' });

    await expect(turns(page)).toHaveCount(1);
    const turn = turns(page).first();
    await expect(turn).toContainText('You');
    await expect(turn).toContainText('Too dressy for today');
    await expect(turn.getByRole('status')).toHaveText('Claude is answering…');
    await expect(box(page)).toHaveValue('');
    await expect(box(page)).toBeFocused();
    // while it is answered the outfits stay
    expect(await pieces(page)).toEqual(before);

    await answered(page, REPLY);
    await expect(turn).toContainText('Claude');
    await expect(box(page)).toBeFocused();
    await expect(page.getByRole('heading', { name: /Best for today/ })).toBeVisible();
    await expect.poll(() => pieces(page)).not.toEqual(before);
    await expect(current(page).getByRole('list', { name: 'Why this works' })).toContainText('Turned around by the stand-in, as you asked.');
    expect(await axeViolations(page)).toEqual([]);
  });

  test('what Claude offers to keep is kept only when saved: in Your style, or in a piece\'s "How I wear it"', async ({ page }) => {
    test.setTimeout(150_000);
    let lastAnswer: { context: { stylist: { talk: { id: string; remember: { kind: string; item_id: string | null; name: string | null }[] }[] } } } | null = null;
    page.on('response', async (r) => {
      if (r.url().endsWith('/api/outfits/today') && r.request().method() === 'POST' && r.ok()) lastAnswer = await r.json().catch(() => lastAnswer);
    });
    await open(page, backend.url);
    // the closet copied from the demo asks about yesterday's outfit: not now (so the picture shows Today as it is)
    await page.getByTestId('worn-question').getByRole('button', { name: 'Not now' }).click();

    await box(page).fill('I never wear shorts in town');
    await box(page).press('Enter');
    await answered(page, REPLY);
    const keep = turns(page).last().getByRole('group', { name: 'Keep this for other days?' });
    await expect(keep).toContainText('I never wear shorts in town');
    await expect(keep.getByRole('button', { name: 'Save to Your style' })).toBeEnabled();
    await expect(keep.getByRole('button', { name: 'No thanks' })).toBeEnabled();
    // offered is not kept
    expect((await (await page.request.get(backend.url + '/api/style/profile')).json()).text).not.toContain('I never wear shorts in town');
    expect(await axeViolations(page)).toEqual([]);
    expect(await sideways(page)).toEqual([]);
    await keep.evaluate((el) => el.scrollIntoView({ block: 'center' }));
    await page.screenshot({ path: test.info().outputPath('today-conversation.png') });
    await look(page, 'phone-light');

    // asking about the outfits does not wait on saving: Today is not asked again
    let asked = 0;
    page.on('request', (r) => r.url().endsWith('/api/outfits/today') && asked++);
    await keep.getByRole('button', { name: 'Save to Your style' }).click();
    await expect(turns(page).last().getByTestId('talk-kept')).toHaveText('Saved to Your style.');
    await expect(keep).toHaveCount(0);
    expect((await (await page.request.get(backend.url + '/api/style/profile')).json()).text).toContain('I never wear shorts in town');
    expect(asked).toBe(0);

    // one message, two offers: one about your style (not kept) and one about the first outfit's top (kept)
    await box(page).fill('Always roll the sleeves when it fits');
    await box(page).press('Enter');
    await answered(page, REPLY);
    const last = turns(page).last();
    await expect(last.getByTestId('talk-keep')).toHaveCount(2);
    await expect.poll(() => lastAnswer?.context.stylist.talk.at(-1)?.remember.length).toBe(2);
    const turnId = lastAnswer!.context.stylist.talk.at(-1)!.id;
    const thing = lastAnswer!.context.stylist.talk.at(-1)!.remember.find((r) => r.kind === 'piece')!;
    expect(thing.item_id).toBeTruthy();
    expect(turnId).toBeTruthy();
    const style = last.getByRole('group', { name: 'Keep this for other days?' });
    await expect(style).toContainText('Always roll the sleeves when it fits');
    await style.getByRole('button', { name: 'No thanks' }).click();
    await expect(style).toHaveCount(0);
    const piece = last.getByRole('group', { name: `Keep this on ${thing.name}?` });
    await expect(piece).toContainText('Fits well under a jacket.');
    await piece.getByRole('button', { name: 'Save to its notes' }).click();
    await expect(last.getByTestId('talk-kept')).toHaveText(`Saved to ${thing.name}'s notes.`);
    await expect(last.getByTestId('talk-keep')).toHaveCount(0);
    expect((await (await page.request.get(backend.url + `/api/items/${thing.item_id}`)).json()).wear_notes).toContain('Fits well under a jacket.');
    expect((await (await page.request.get(backend.url + '/api/style/profile')).json()).text).not.toContain('Always roll the sleeves');

    // the item page shows it in the item's one notes box
    await page.goto(backend.url + `/today/item/${encodeURIComponent(thing.item_id!)}`);
    await expect(page.getByRole('textbox', { name: 'Notes for you and Claude' })).toHaveValue(/Fits well under a jacket\./);
  });

  test('Enter sends and Shift+Enter does not; a question is answered and the outfits and the place stay', async ({ page }) => {
    test.setTimeout(120_000);
    await open(page, backend.url);
    const before = await turns(page).count();
    const sent: unknown[] = [];
    page.on('request', (r) => said(r) && sent.push(r.postDataJSON()));

    // Shift+Enter is a new line
    await box(page).fill('Swap the boots');
    await box(page).press('Shift+Enter');
    await box(page).pressSequentially('or not');
    await expect(box(page)).toHaveValue('Swap the boots\nor not');
    expect(sent).toEqual([]);

    // the second outfit is in front of the owner: that is the one sent
    await page.getByRole('button', { name: 'Outfit 2', exact: true }).click();
    await settled(page, 1);
    const second = await pieces(page);
    await box(page).fill('Why not the navy blazer?');
    const request = page.waitForRequest(said);
    await box(page).press('Enter');
    expect((await request).postDataJSON()).toMatchObject({ say: 'Why not the navy blazer?', looking_at: 1 });
    await expect(box(page)).toHaveValue('');
    await answered(page, 'Because the stand-in chose by number.');
    await expect(turns(page)).toHaveCount(before + 1);
    // a question changes nothing: the same outfit is still in front of the owner
    await expect(page.getByRole('heading', { name: /2 of/ })).toBeVisible();
    expect(await pieces(page)).toEqual(second);
  });

  test('a message that is not answered says why, Send again sends it again (the stand-in fails it again), and the next is answered', async ({ page }) => {
    test.setTimeout(120_000);
    await open(page, backend.url);
    await box(page).fill('Please fail at this');
    await box(page).press('Enter');
    await answered(page, NOT_ANSWERED);
    const failed = turns(page).last();
    await expect(failed).toContainText('Please fail at this');
    await expect(failed).not.toContainText(REPLY);
    const again = failed.getByRole('button', { name: 'Send again' });
    await expect(again).toBeEnabled();

    const count = await turns(page).count();
    const request = page.waitForRequest(said);
    await again.click();
    expect((await request).postDataJSON()).toMatchObject({ say: 'Please fail at this' });
    await expect(turns(page)).toHaveCount(count + 1);
    await answered(page, NOT_ANSWERED);
    await expect(turns(page).last()).toContainText('Please fail at this');
    // only the newest message that was not answered can be sent again
    await expect(thread(page).getByRole('button', { name: 'Send again' })).toHaveCount(1);
    await expect(turns(page).last().getByRole('button', { name: 'Send again' })).toBeEnabled();

    // the conversation goes on: a message without "fail" is answered
    await box(page).fill('Something warmer please');
    await box(page).press('Enter');
    await answered(page, REPLY);
    await expect(turns(page)).toHaveCount(count + 2);
    await expect(thread(page).getByRole('button', { name: 'Send again' })).toHaveCount(0);   // it has been followed

    // the whole conversation is still there after a reload, as it stood
    await page.reload();
    await expect(read(page)).toBeVisible({ timeout: 20_000 });
    await expect(turns(page).first()).toContainText('Too dressy for today');
    await expect(thread(page)).toContainText('Because the stand-in chose by number.');
    await expect(thread(page)).toContainText(NOT_ANSWERED);
    await expect(thread(page).getByTestId('talk-kept')).toHaveText(['Saved to Your style.', /^Saved to .+'s notes\.$/]);
    await expect(thread(page).getByTestId('talk-keep')).toHaveCount(0);
  });

  test('the box waits while Claude answers, and a message refused by the server keeps its text and says why', async ({ page }) => {
    test.setTimeout(120_000);
    await open(page, backend.url);
    await box(page).fill('Answer this slowly please');
    await box(page).press('Enter');
    await expect(turns(page).last().getByRole('status')).toHaveText('Claude is answering…');
    await expect(box(page)).toBeDisabled();
    await expect(box(page)).toHaveAttribute('readonly', '');
    await expect(box(page)).toBeFocused();
    await expect(send(page)).toBeDisabled();
    await expect(thread(page).getByRole('button', { name: 'Send again' })).toHaveCount(0);
    // Claude starts nothing else meanwhile, so "Ask Claude again" waits too
    await expect(read(page).getByRole('button', { name: 'Ask Claude again' })).toBeDisabled();
    await answered(page, REPLY);
    await expect(box(page)).toBeEnabled();
    await expect(box(page)).toBeFocused();
    await expect(read(page).getByRole('button', { name: 'Ask Claude again' })).toBeEnabled();

    // another occasion while a message is answered: Today waits on that message with its usual card (asking how it
    // stands one question at a time, never twice over), then Claude chooses for the new occasion
    const polls: { id: string; at: number }[] = [];
    page.on('request', (r) => {
      if (r.method() === 'GET' && r.url().includes('/api/style/answers/')) polls.push({ id: r.url().split('/').pop()!, at: Date.now() });
    });
    const message = page.waitForResponse((r) => said(r.request()));
    await box(page).fill('Slowly now, something lighter');
    await box(page).press('Enter');
    const messageId = (await (await message).json()).context.stylist.answering as string;
    expect(messageId).toBeTruthy();
    const occasion = page.getByRole('group', { name: 'Occasion' });
    await occasion.getByRole('button', { name: 'Smart casual' }).click();
    await expect(page.getByTestId('stylist-waiting')).toBeVisible();
    await expect(read(page)).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId('stylist-waiting')).toHaveCount(0);
    expect(polls.some((p) => p.id === messageId)).toBe(true);
    for (let i = 1; i < polls.length; i++) expect(polls[i].at - polls[i - 1].at, 'one poll at a time').toBeGreaterThan(1000);
    await occasion.getByRole('button', { name: 'Casual', exact: true }).click();
    await expect(read(page)).toBeVisible({ timeout: 30_000 });
    await expect(turns(page).last()).toContainText('Slowly now, something lighter');
    await expect(turns(page).last()).toContainText(REPLY);

    // another device (here: a request of the test's own) sends a message Claude is slow to answer; this page does
    // not know, and the server refuses its message meanwhile
    const other = await page.request.post(backend.url + '/api/outfits/today', { data: { occasion: 'casual', mood: 'usual', ...DAY, say: 'Another slow one' } });
    expect(other.status()).toBe(200);
    await box(page).fill('Swap the boots');
    await box(page).press('Enter');
    const alert = read(page).getByRole('alert');
    await expect(alert).toHaveText('Claude is still answering your last message.');
    await expect(alert).toHaveClass(/form-error/);
    await expect(box(page)).toHaveValue('Swap the boots');
    await expect(box(page)).toBeEnabled();
    expect(await axeViolations(page)).toEqual([]);

    // once that is answered, the page shows it and the kept text can be sent
    await expect.poll(async () => (await (await page.request.get(backend.url + `/api/style/answers/${(await other.json()).context.stylist.answering}`)).json()).state, { timeout: 20_000 }).not.toBe('working');
    await page.reload();
    await expect(read(page)).toBeVisible({ timeout: 20_000 });
    await expect(turns(page).last()).toContainText('Another slow one');
    await expect(turns(page).last()).toContainText(REPLY);
  });

  test('after a look at the closet that changed meanwhile, Today is asked again and a message waits for that answer, then is sent', async ({ page }) => {
    test.setTimeout(120_000);
    await open(page, backend.url);
    const count = await turns(page).count();
    // on another device, a piece that is in none of the outfits goes in the laundry: the closet differs, the outfits do not
    const shown = await (await page.request.post(backend.url + '/api/outfits/today', { data: { occasion: 'casual', mood: 'usual', ...DAY } })).json();
    const worn = new Set<string>(shown.outfits.flatMap((o: { pieces: Record<string, string | string[] | null> }) => Object.values(o.pieces).flat()));
    const { items } = await (await page.request.get(backend.url + '/api/items?status=active&laundry=clean')).json();
    const spare = items.find((i: { id: string; category: string }) => !worn.has(i.id) && i.category === 'shorts') ?? items.find((i: { id: string }) => !worn.has(i.id));
    expect((await page.request.post(backend.url + `/api/items/${spare.id}/laundry`, { data: { state: 'laundry' } })).status()).toBe(200);
    // the next time Today is asked (without a message), the answer takes three seconds
    let hold = true;
    await page.route('**/api/outfits/today', async (route: Route) => {
      if (hold && !(route.request().postDataJSON() as { say?: string }).say) {
        hold = false;
        await new Promise((r) => setTimeout(r, 3000));
      }
      await route.fallback();
    });
    // a look at the closet reads it again; back on Today the outfits are there as they were, and Today is asked again
    const tabbar = page.locator('nav.tabbar');
    await tabbar.getByRole('link', { name: 'Closet' }).click();
    await expect(page.locator('#closet-title')).toBeVisible();
    await page.waitForLoadState('networkidle');
    await tabbar.getByRole('link', { name: 'Today' }).click();
    await expect(page.locator('.today-outfits.is-asking')).toHaveCount(1, { timeout: 15_000 });
    const sent = page.waitForResponse((r) => said(r.request()));
    await box(page).fill('Lighter shoes please');
    await box(page).press('Enter');
    const response = await sent;
    expect(response.status(), await response.text()).toBe(200);
    await expect(turns(page)).toHaveCount(count + 1, { timeout: 15_000 });
    await expect(turns(page).last()).toContainText('Lighter shoes please');
    await answered(page, REPLY);
    await expect(box(page)).toHaveValue('');
    expect((await page.request.post(backend.url + `/api/items/${spare.id}/laundry`, { data: { state: 'clean' } })).status()).toBe(200);
  });

  test('a long unbroken message stays on a phone screen, and the conversation passes the checks on a phone and a computer, light and dark', async ({ page }) => {
    test.setTimeout(150_000);
    await open(page, backend.url);
    const long = 'Z'.repeat(400);
    const count = await turns(page).count();
    const sent = page.waitForResponse((r) => said(r.request()));
    await box(page).fill(long);
    await box(page).press('Enter');
    const response = await sent;
    expect(response.status(), await response.text()).toBe(200);
    await expect(turns(page)).toHaveCount(count + 1);
    await expect(turns(page).last()).toContainText(long);
    await answered(page, REPLY);
    expect(await sideways(page)).toEqual([]);
    expect(await axeViolations(page)).toEqual([]);
    await look(page, 'phone-light-long');

    await page.emulateMedia({ colorScheme: 'dark' }); // Closet follows the device until a theme is chosen
    expect(await axeViolations(page)).toEqual([]);
    expect(await sideways(page)).toEqual([]);
    await look(page, 'phone-dark');

    await page.setViewportSize({ width: 1440, height: 900 });
    expect(await axeViolations(page)).toEqual([]);
    await look(page, 'computer-dark');
    await page.emulateMedia({ colorScheme: 'light' });
    expect(await axeViolations(page)).toEqual([]);
    await page.getByTestId('talk').evaluate((el) => el.scrollIntoView({ block: 'start' }));
    await page.screenshot({ path: test.info().outputPath('today-conversation-computer.png') });
    await look(page, 'computer-light');

    // on a computer the carousel still shows one outfit at a time: the one in front of the owner is sent
    await page.getByRole('button', { name: 'Outfit 3', exact: true }).click();
    await settled(page, 2);
    await box(page).fill('Why the third?');
    const request = page.waitForRequest(said);
    await send(page).click();
    expect((await request).postDataJSON()).toMatchObject({ looking_at: 2 });
    await answered(page, 'Because the stand-in chose by number.');
  });
});
