import { type Page } from '@playwright/test';
import { axeViolations } from './a11y';
import { expect, login, test } from './fixtures';

// GitHub is never asked from a test: the shared server runs from source (it never checks by itself), and the
// test that installs answers /api/updates and /api/health with a stand-in.

test.afterEach(async ({ page }) => {
  await page.request.put('/api/updates', { data: { mode: 'ask' } });
});

async function openUpdates(page: Page) {
  await page.locator('nav.sidebar').getByRole('link', { name: 'Settings' }).click();
  return page.getByRole('region', { name: 'Updates' });
}

test('settings: Updates is one line with this version; the choice is on Advanced and is kept', async ({ page }) => {
  await login(page);
  const version = (await (await page.request.get('/api/updates')).json()).version;
  const line = (await openUpdates(page)).getByTestId('update-line');
  await expect(line).toHaveText(new RegExp(`^Closet ${version.replace(/\./g, '\\.')}`));
  await page.getByRole('link', { name: 'Advanced settings' }).click();
  const section = page.getByRole('region', { name: 'Updates' });
  await expect(section.getByTestId('update-version')).toHaveText(version);
  const choice = section.getByRole('group', { name: 'When a new version is out' });
  await expect(choice.getByRole('button', { name: 'Ask first' })).toHaveAttribute('aria-pressed', 'true');
  await expect(section.getByTestId('update-mode-hint')).toContainText('asks before installing');
  await expect(page.getByTestId('update-banner')).toHaveCount(0);

  await choice.getByRole('button', { name: 'Never', exact: true }).click();
  await expect(page.getByText('Saved', { exact: true })).toBeVisible();
  expect((await (await page.request.get('/api/updates')).json()).mode).toBe('never');
  await page.reload();
  await expect(choice.getByRole('button', { name: 'Never', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(section.getByTestId('update-checked')).toHaveText(/never to check/);
  await page.goto('/settings');
  await expect(line).toHaveText(`Closet ${version} · not looking for new versions`);
});

const RELEASE = {
  version: '0.3.0',
  // what the server sends: the release's "## What's new" section, as Markdown (backend/closet/updates.py)
  notes: '### Changed\n\n- Trips pack **better**, and the list\n  wraps onto a second line.\n- <b>Not bold</b>\n\n### Fixed\n\n1. A sock no longer goes missing.',
  page: 'https://github.com/ericksoni716/daily-clother/releases/tag/v0.3.0',
  published_at: '2026-11-12T10:00:00Z',
};

function standIn(over: Record<string, unknown> = {}) {
  return {
    version: '0.2.1', mode: 'ask', can_install: true, checked_at: '2026-11-13T09:00:00Z', check_error: null, latest: '0.3.0',
    available: RELEASE, download_size: 52_000_000, ready: true, problem: null, busy: null, last_install: null,
    releases_page: 'https://github.com/ericksoni716/daily-clother/releases', ...over,
  };
}

/** Settings bring the updates' status with them (GET /api/settings), so the stand-in is put there too. */
async function standInSettings(page: Page, answer: () => Record<string, unknown>) {
  await page.route('**/api/settings', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback();
    const response = await route.fetch();
    return route.fulfill({ response, json: { ...(await response.json()), updates: answer() } });
  });
}

test('updates (stand-in): the banner offers the new version, Install restarts Closet and the page reconnects', async ({ page }) => {
  let phase: 'ready' | 'installing' | 'done' = 'ready';
  let health = 0;
  let checks = 0;
  const answer = () => {
    if (phase === 'ready') return standIn();
    if (phase === 'installing') return standIn({ busy: 'restarting' });
    return standIn({
      version: '0.3.0', latest: '0.3.0', available: null, ready: false, download_size: null,
      last_install: { at: '2026-11-13T09:05:00Z', from: '0.2.1', to: '0.3.0', ok: true, note: null },
    });
  };
  await page.route('**/api/updates', (route) => route.fulfill({ json: answer() }));
  await standInSettings(page, answer);
  await page.route('**/api/updates/check', (route) => {
    checks += 1;
    return route.fulfill({ json: standIn() });
  });
  await page.route('**/api/updates/install', (route) => {
    phase = 'installing';
    return route.fulfill({ status: 202, json: standIn({ busy: 'restarting' }) });
  });
  await page.route('**/api/health', (route) => {
    if (phase !== 'installing') return route.continue();
    health += 1;
    // the old Closet answers, then goes away, then the new one answers
    if (health <= 1) return route.fulfill({ json: { ok: true, version: '0.2.1' } });
    if (health <= 3) return route.abort('connectionrefused');
    phase = 'done';
    return route.fulfill({ json: { ok: true, version: '0.3.0' } });
  });

  await login(page);
  const banner = page.getByTestId('update-banner');
  await expect(banner).toContainText('Closet 0.3.0 is ready');

  const section = await openUpdates(page);
  await expect(section.getByTestId('update-available')).toHaveText('Closet 0.3.0 is ready to install.');
  // the notes start folded; opened, their headings, lists and bold are drawn, and HTML in them stays text
  const notes = section.getByTestId('update-notes');
  const whatsNew = notes.getByText("What's new in 0.3.0", { exact: true });
  await expect(whatsNew).toBeVisible();
  await expect(notes.getByRole('heading', { name: 'Changed' })).toBeHidden();
  await whatsNew.click();
  await expect(notes.getByRole('heading', { name: 'Changed', level: 3 })).toBeVisible();
  await expect(notes.getByRole('heading', { name: 'Fixed', level: 3 })).toBeVisible();
  await expect(notes.getByRole('listitem').first()).toHaveText('Trips pack better, and the list wraps onto a second line.');
  await expect(notes.locator('strong')).toHaveText('better');
  await expect(notes.locator('ol > li')).toHaveText('A sock no longer goes missing.');
  await expect(notes.getByText('<b>Not bold</b>', { exact: true })).toBeVisible();
  await expect(notes.locator('b')).toHaveCount(0);
  await expect(section).not.toContainText('##');
  await expect(section).not.toContainText('**');
  expect(await axeViolations(page, '[data-testid="update-notes"]')).toEqual([]);
  await expect(section.getByRole('button', { name: 'Install now' })).toBeVisible();

  // how updates are fetched, Check now and the release page are on Advanced
  await page.getByRole('link', { name: 'Advanced settings' }).click();
  const manage = page.getByRole('region', { name: 'Updates' });
  await expect(manage.getByRole('link', { name: 'The release page' })).toHaveAttribute('href', RELEASE.page);
  await manage.getByRole('button', { name: 'Check now' }).click();
  await expect.poll(() => checks).toBe(1);

  await banner.getByRole('button', { name: 'Install' }).click();
  await expect(page.getByRole('alertdialog', { name: 'Closet is restarting' })).toBeVisible();
  await expect(page.getByText('Installing Closet 0.3.0')).toBeVisible();

  // once the new Closet answers, the page reloads by itself
  await expect(page.getByRole('alertdialog')).toHaveCount(0, { timeout: 15_000 });
  await expect(manage.getByTestId('update-version')).toHaveText('0.3.0');
  await expect(manage.getByTestId('update-last')).toHaveText(/Updated from 0.2.1 to 0.3.0/);
  await page.goto('/settings');
  await expect(section.getByTestId('update-line')).toHaveText('Closet 0.3.0 · up to date');
  await expect(banner).toHaveCount(0);
});

test('updates (stand-in): a problem before restarting is shown and Closet keeps running', async ({ page }) => {
  let phase: 'ready' | 'failed' = 'ready';
  // a release from before the notes had a What's new section: the server sends no notes
  const available = { ...RELEASE, notes: '' };
  const answer = () => (phase === 'ready' ? standIn({ available })
    : standIn({ available, ready: false, problem: "Closet couldn't back up your closets, so it didn't install the update." }));
  await page.route('**/api/updates', (route) => route.fulfill({ json: answer() }));
  await standInSettings(page, answer);
  await page.route('**/api/updates/install', (route) => {
    phase = 'failed';
    return route.fulfill({ status: 202, json: standIn({ busy: 'backing-up' }) });
  });
  await page.route('**/api/health', (route) => route.fulfill({ json: { ok: true, version: '0.2.1' } }));
  await login(page);
  const section = await openUpdates(page);
  await expect(section.getByTestId('update-available')).toBeVisible();
  await expect(section.getByTestId('update-notes')).toHaveCount(0);   // no notes, nothing to open
  await section.getByRole('button', { name: 'Install now' }).click();
  await expect(section.getByTestId('update-problem')).toHaveText(/couldn't back up/);
  await expect(page.getByRole('alertdialog')).toHaveCount(0);
  await expect(page.getByTestId('update-banner')).toHaveCount(0);
});
