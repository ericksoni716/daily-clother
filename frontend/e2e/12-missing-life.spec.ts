import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import type { Page } from '@playwright/test';
import type { Gap, GapsAnswer } from '../src/gaps';
import type { Life, SituationId } from '../src/life';
import { expect, login, test, useProfile } from './fixtures';

const example: Life = {
  situations: { work: 4, everyday: 4, going_out: 1, lounging: 0, exercise: 0, vacation: .25 },
  work_dress: 'smart_casual', vacation_climate: 'warm', vacation_weeks: 3, style_words: 'Relaxed, simple, a little colour',
};

function suggestion(id: string, name: string, situation: SituationId, situationName: string): Gap {
  return {
    id, name, state: 'open', hidden_reason: null, wish_id: null, score: 65,
    why: [situation === 'work'
      ? 'For your work days, another pair of trousers would give your shirts more ways to be worn.'
      : 'A light shirt would give you more choice for warm days away.'],
    found_by: ['days'], evidence: { days: [], items: [] },
    look_for: {
      category: situation === 'work' ? 'trousers' : 'shirt', formality: 'smart_casual', season: 'warm',
      weight_class: 'lightweight', colors: ['navy', 'tan'], pattern: 'solid', material: null,
      fit: 'regular', avoid_patterns: ['graphic'], avoid_fits: ['slim'],
    },
    situations: [{ id: situation, label: situationName, days_per_week: situation === 'work' ? 4 : .25,
      share: .3, days_per_year: situation === 'work' ? 196 : 21 }],
  };
}

/** Synthetic answers only: no photos, real place, or changes to the server's settings. */
async function mockLife(page: Page, initial: Life | null = null, demo = false) {
  const state = {
    life: initial ? structuredClone(initial) : null,
    dismissed: false,
    failSave: false,
    offline: false,
    legacy: false,
    writes: [] as Record<string, unknown>[],
    suppressed: [{ gap_id: 'formal-shoes', name: 'Formal leather shoes', situations: ['going_out'] }],
  };
  await page.route('**/api/settings', async (route) => {
    const request = route.request();
    if (request.method() === 'PUT') {
      if (state.failSave) {
        await route.fulfill({ status: 422, json: { detail: 'These answers could not be saved. Try again.' } });
        return;
      }
      const body = request.postDataJSON();
      state.writes.push(body);
      if ('life' in body) state.life = body.life;
      if ('life_prompt_dismissed' in body) state.dismissed = body.life_prompt_dismissed;
    }
    const original = await page.request.get('/api/settings');
    await route.fulfill({ json: { ...await original.json(), life: state.life, life_prompt_dismissed: state.dismissed } });
  });
  await page.route('**/api/gaps', async (route) => {
    if (state.offline) { await route.abort(); return; }
    const gaps = [suggestion('trousers-smart_casual', 'Light trousers for work', 'work', 'Work'),
      suggestion('shirt-smart_casual', 'A shirt for days away', 'vacation', 'Vacation')];
    if (state.legacy) gaps.forEach((g) => { delete g.situations; });
    const answer: GapsAnswer = {
      enough: true, message: null, gaps, checked: { items: 28, wears: 42, days: 48 }, notes: [],
      ...(!state.legacy ? { context: {
        life: state.life, prompt_dismissed: state.dismissed, demo,
        climate: { used: false, place: null, shares: null, years: [], old: false,
          message: 'No home climate yet. Using a general mix of weather.' },
        taste: { used: true, summary: 'Your liked clothes lean towards plain patterns and a regular fit.' },
        suppressed: state.suppressed,
      } } : {}),
    };
    await route.fulfill({ json: answer });
  });
  await page.route('**/api/wishlist', async (route) => {
    if (state.offline) await route.abort();
    else await route.fulfill({ json: { wishes: [] } });
  });
  await page.route('**/api/gaps/formal-shoes/hide', async (route) => {
    expect(route.request().method()).toBe('DELETE');
    state.suppressed = [];
    await route.fulfill({ status: 204 });
  });
  return state;
}

async function open(page: Page, life: Life | null = null, demo = false) {
  await login(page);
  await useProfile(page, demo ? 'demo' : 'main');
  const state = await mockLife(page, life, demo);
  await page.goto('/missing');
  await expect(page.getByTestId('gap')).toHaveCount(2);
  return state;
}

test.afterEach(async ({ page }) => {
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

for (const [layout, viewport] of [
  ['desktop', { width: 1280, height: 800 }], ['phone', { width: 390, height: 844 }],
] as const) {
  test(`life questions save, filters, Settings reuse and screenshots on ${layout}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const state = await open(page);
    await expect(page.getByRole('heading', { name: /Tell it how you live/ })).toBeVisible();
    await page.getByRole('button', { name: 'Answer a few questions' }).click();
    const questions = page.getByRole('form', { name: 'How you live' });
    await expect(questions).toContainText('For vacation, count days per week while away, not across the whole year.');
    await questions.getByLabel('Work frequency').selectOption('4');
    await questions.getByLabel('At work, you dress').selectOption('smart_casual');
    await questions.getByLabel('Going out frequency').selectOption('1');
    await questions.getByLabel('Vacation frequency').selectOption('0.25');
    await questions.getByLabel('Vacation weeks per year').fill('3');
    await questions.getByLabel('Vacation weather').selectOption('warm');
    await questions.getByLabel('My style in a few words').fill(example.style_words);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width);
    const screenshots = resolve(import.meta.dirname, '../../docs/screenshots');
    mkdirSync(screenshots, { recursive: true });
    await page.evaluate(() => window.scrollTo(0, 0));
    if (layout === 'phone') {
      const dialog = page.getByRole('dialog', { name: 'How you live' });
      await dialog.evaluate((el) => { el.scrollTop = 0; });
      const save = await questions.getByRole('button', { name: 'Save my answers' }).boundingBox();
      expect(save).not.toBeNull();
      expect(save!.y + save!.height).toBeLessThanOrEqual(viewport.height);
      expect(save!.height).toBeGreaterThanOrEqual(44);
      const selects = await questions.getByRole('combobox').evaluateAll((els) => els.map((el) => el.getBoundingClientRect().height));
      expect(selects.every((height) => height >= 44)).toBe(true);
      const controls = await questions.locator('input:enabled, select:enabled, button:enabled').evaluateAll((els) =>
        els.map((el) => {
          const box = el.getBoundingClientRect();
          return { name: el.getAttribute('aria-label') ?? el.textContent, top: box.top, bottom: box.bottom,
            left: box.left, right: box.right, height: box.height };
        }));
      for (const control of controls) {
        expect(control.top, `${control.name} fits above the bottom edge`).toBeGreaterThanOrEqual(0);
        expect(control.bottom, `${control.name} fits in one screenful`).toBeLessThanOrEqual(viewport.height);
        expect(control.left).toBeGreaterThanOrEqual(0);
        expect(control.right).toBeLessThanOrEqual(viewport.width);
        expect(control.height).toBeGreaterThanOrEqual(44);
      }
    }
    await page.screenshot({ path: resolve(screenshots, `missing-life-questions-${layout}.png`) });
    await questions.getByRole('button', { name: 'Save my answers' }).click();
    await expect(questions).toHaveCount(0);
    expect(state.life).toEqual(example);
    expect(state.writes).toEqual([{ life: example, life_prompt_dismissed: true }]);
    await expect(page.getByText('Your words:', { exact: false })).toContainText(example.style_words);
    await expect(page.getByText('Kept as a note, not used to rank suggestions.')).toBeVisible();
    await expect(page.getByRole('link', { name: 'Where you are in Settings' })).toBeVisible();
    const basis = page.getByRole('button', { name: 'See the answers behind these suggestions' });
    await expect(basis).toContainText('work 4 days a week, smart casual');
    await expect(basis).toContainText('everyday 4 days a week');
    await expect(basis).toContainText('vacation 3 weeks a year, warm');
    await expect(basis).toContainText('what you wear and rate');
    await expect(basis).not.toContainText('exercise');
    const filters = page.getByRole('group', { name: 'Suggestions for' });
    await expect(filters.getByRole('button')).toHaveText(['All', 'Work', 'Everyday', 'Going out', 'Vacation']);
    await expect(page.getByTestId('gap').first().getByRole('list', { name: 'Useful for' })).toHaveText('Work');
    await expect(page.getByText('Your answers are saved', { exact: true })).toHaveCount(0, { timeout: 10_000 });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: resolve(screenshots, `missing-life-list-${layout}.png`) });
    await filters.getByRole('button', { name: 'Vacation' }).click();
    await expect(page.getByTestId('gap')).toHaveCount(1);
    await expect(page.getByTestId('gap')).toContainText('A shirt for days away');
    await filters.getByRole('button', { name: 'Everyday' }).click();
    await expect(page.getByText('Nothing to look for just for everyday right now.')).toBeVisible();
    await filters.getByRole('button', { name: 'All', exact: true }).click();
    await expect(page.getByTestId('gap')).toHaveCount(2);
    await page.getByRole('link', { name: 'Where you are in Settings' }).click();
    await page.getByRole('button', { name: 'Edit my answers' }).click();
    await expect(questions.getByLabel('Work frequency')).toHaveValue('4');
    await expect(questions.getByLabel('Vacation weeks per year')).toHaveValue('3');
    await questions.getByLabel('Work frequency').selectOption('0');
    await expect(questions.getByLabel('At work, you dress')).toHaveCount(0);
    await questions.getByRole('button', { name: 'Save my answers' }).click();
    await page.goto('/missing');
    await expect(filters.getByRole('button', { name: 'Work', exact: true })).toHaveCount(0);
    await page.getByText('How these suggestions work', { exact: true }).click();
    await expect(page.getByText(/Closet can't identify sleepwear/)).toBeVisible();
    await expect(page.getByText(/not specific to a sport/)).toBeVisible();
    if (layout === 'phone') {
      await basis.click();
      await expect(page.getByRole('dialog')).toBeVisible();
      await page.keyboard.press('Escape');
      await expect(page.getByRole('dialog')).toHaveCount(0);
      expect(state.writes).toHaveLength(2);
    }
  });
}

test('Not now is persisted; questions remain available, including after reload', async ({ page }) => {
  const state = await open(page);
  await page.getByRole('button', { name: 'Not now' }).click();
  await expect(page.getByRole('heading', { name: /Tell it how you live/ })).toHaveCount(0);
  expect(state.writes).toEqual([{ life_prompt_dismissed: true }]);
  expect(state.life).toBeNull();
  await page.reload();
  await expect(page.getByRole('button', { name: 'Not now' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Your answers' }).click();
  await expect(page.getByRole('form', { name: 'How you live' })).toBeVisible();
});

test('non-preset frequencies survive edits; failed saves retain answers and can be retried', async ({ page }) => {
  const life = structuredClone(example);
  life.situations.work = 3.5;
  const state = await open(page, life);
  await page.getByRole('button', { name: 'Edit answers' }).click();
  const form = page.getByRole('form', { name: 'How you live' });
  await expect(form.getByLabel('Work frequency')).toHaveValue('3.5');
  await form.getByLabel('My style in a few words').fill('Quiet and comfortable');
  state.failSave = true;
  await form.getByRole('button', { name: 'Save my answers' }).click();
  await expect(form.getByRole('alert')).toHaveText('These answers could not be saved. Try again.');
  await expect(form.getByLabel('My style in a few words')).toHaveValue('Quiet and comfortable');
  state.failSave = false;
  await form.getByLabel('Vacation weeks per year').fill('53');
  await form.getByRole('button', { name: 'Save my answers' }).click();
  expect(state.writes).toEqual([]);
  await form.getByLabel('Vacation weeks per year').fill('0');
  await form.getByRole('button', { name: 'Save my answers' }).click();
  await expect(form).toHaveCount(0);
  expect(state.life?.situations.work).toBe(3.5);
  expect(state.life?.vacation_weeks).toBe(0);
});

test('suppressed never-wear decisions remain visible and can be undone', async ({ page }) => {
  const state = await open(page, example);
  const decisions = page.getByTestId('suppressed-gaps');
  await decisions.getByText("Days you've ruled out (1)").click();
  await expect(decisions).toContainText('Formal leather shoes');
  await expect(decisions).toContainText('Going out');
  await decisions.getByRole('button', { name: 'Undo decision about Formal leather shoes' }).click();
  await expect(decisions).toHaveCount(0);
  expect(state.suppressed).toEqual([]);
});

test('demo questions explain the fixed example and cannot edit either closet', async ({ page }) => {
  const state = await open(page, example, true);
  await page.getByRole('button', { name: 'Example answers' }).click();
  await expect(page.getByText(/The demo uses fixed example answers/)).toBeVisible();
  await expect(page.getByLabel('Work frequency')).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Save my answers' })).toHaveCount(0);
  expect(state.writes).toEqual([]);
  await page.goto('/settings');
  await page.getByRole('button', { name: 'See example answers' }).click();
  await expect(page.getByLabel('Vacation weather')).toBeDisabled();
  expect(state.writes).toEqual([]);
});

test('saved life answers are read-only offline; old saved answers still render', async ({ page }) => {
  const state = await open(page, example);
  state.offline = true;
  await page.reload();
  await expect(page.getByText(/^Saved earlier/)).toBeVisible();
  await page.getByRole('button', { name: 'Saved answers' }).click();
  await expect(page.getByLabel('Work frequency')).toHaveValue('4');
  await expect(page.getByLabel('Work frequency')).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Save my answers' })).toBeDisabled();
  await page.getByRole('button', { name: 'Close', exact: true }).click();
  await page.getByTestId('suppressed-gaps').getByText("Days you've ruled out (1)").click();
  await expect(page.getByRole('button', { name: 'Undo decision about Formal leather shoes' })).toBeDisabled();
  expect(state.writes).toEqual([]);
  state.offline = false;
  state.legacy = true;
  await page.reload();
  await expect(page.getByTestId('gap')).toHaveCount(2);
  await expect(page.getByRole('group', { name: 'Suggestions for' })).toHaveCount(0);
  state.offline = true;
  await page.reload();
  await expect(page.getByText(/^Saved earlier/)).toBeVisible();
  await expect(page.getByTestId('gap')).toHaveCount(2);
  await expect(page.getByTestId('gap').first().getByRole('button', { name: "I'll look for this" })).toBeDisabled();
});

test('real settings and gaps endpoints keep the same answers across screens and a reload', async ({ page }) => {
  await login(page);
  await useProfile(page, 'main');
  const before = await (await page.request.get('/api/settings')).json();
  try {
    const reset = await page.request.put('/api/settings', { data: { life: null, life_prompt_dismissed: false, place: null } });
    expect(reset.ok()).toBeTruthy();
    await page.goto('/missing');
    await page.getByRole('button', { name: 'Answer a few questions' }).click();
    const form = page.getByRole('form', { name: 'How you live' });
    await form.getByLabel('Work frequency').selectOption('4');
    await form.getByLabel('At work, you dress').selectOption('business');
    await form.getByLabel('Vacation frequency').selectOption('1');
    await form.getByLabel('Vacation weeks per year').fill('1.5');
    await form.getByLabel('Vacation weather').selectOption('cold');
    await form.getByLabel('My style in a few words').fill('Simple layers');
    await form.getByRole('button', { name: 'Save my answers' }).click();
    await expect(form).toHaveCount(0);
    const settings = await (await page.request.get('/api/settings')).json();
    expect(settings.life.vacation_weeks).toBe(1.5);
    expect(settings.life.work_dress).toBe('business');
    expect(settings.life.style_words).toBe('Simple layers');
    const gaps = await (await page.request.get('/api/gaps')).json();
    expect(gaps.context.life).toEqual(settings.life);
    await page.reload();
    await page.getByRole('button', { name: 'Edit answers' }).click();
    await expect(form.getByLabel('Vacation weeks per year')).toHaveValue('1.5');
    await page.goto('/settings');
    await page.getByRole('button', { name: 'Edit my answers' }).click();
    await expect(form.getByLabel('Vacation weather')).toHaveValue('cold');
  } finally {
    const restored = await page.request.put('/api/settings', {
      data: { life: before.life ?? null, life_prompt_dismissed: before.life_prompt_dismissed ?? false, place: before.place ?? null },
    });
    expect(restored.ok()).toBeTruthy();
  }
});
