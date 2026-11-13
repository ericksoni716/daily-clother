import { type Page } from '@playwright/test';
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

test('settings: the Updates section shows this version and keeps the choice', async ({ page }) => {
  await login(page);
  const section = await openUpdates(page);
  await expect(section.getByTestId('update-version')).toHaveText((await (await page.request.get('/api/updates')).json()).version);
  await expect(section.getByRole('radio', { name: /Ask me first/ })).toBeChecked();
  // run from source, Closet only reports new versions
  await expect(section.getByText(/can't replace itself/)).toBeVisible();
  await expect(page.getByTestId('update-banner')).toHaveCount(0);

  await section.getByRole('radio', { name: /Never check/ }).check();
  await expect(page.getByText('Saved', { exact: true })).toBeVisible();
  expect((await (await page.request.get('/api/updates')).json()).mode).toBe('never');
  await page.reload();
  await expect(section.getByRole('radio', { name: /Never check/ })).toBeChecked();
  await expect(section.getByTestId('update-checked')).toHaveText(/never to check/);
});

const RELEASE = {
  version: '0.3.0',
  notes: 'Trips pack better.\n<b>Not bold</b>',
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

test('updates (stand-in): the banner offers the new version, Install restarts Closet and the page reconnects', async ({ page }) => {
  let phase: 'ready' | 'installing' | 'done' = 'ready';
  let health = 0;
  let checks = 0;
  await page.route('**/api/updates', (route) => {
    if (phase === 'ready') return route.fulfill({ json: standIn() });
    if (phase === 'installing') return route.fulfill({ json: standIn({ busy: 'restarting' }) });
    return route.fulfill({
      json: standIn({
        version: '0.3.0', latest: '0.3.0', available: null, ready: false, download_size: null,
        last_install: { at: '2026-11-13T09:05:00Z', from: '0.2.1', to: '0.3.0', ok: true, note: null },
      }),
    });
  });
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
  // the notes are text, never HTML
  await expect(section.getByLabel("What's new in 0.3.0")).toHaveText(/Trips pack better\.\s*<b>Not bold<\/b>/);
  await expect(section.locator('.update-notes b')).toHaveCount(0);
  await expect(section.getByRole('link', { name: 'The release page' })).toHaveAttribute('href', RELEASE.page);
  await section.getByRole('button', { name: 'Check now' }).click();
  await expect.poll(() => checks).toBe(1);

  await banner.getByRole('button', { name: 'Install' }).click();
  await expect(page.getByRole('alertdialog', { name: 'Closet is restarting' })).toBeVisible();
  await expect(page.getByText('Installing Closet 0.3.0')).toBeVisible();

  // once the new Closet answers, the page reloads by itself
  await expect(page.getByRole('alertdialog')).toHaveCount(0, { timeout: 15_000 });
  await expect(section.getByTestId('update-version')).toHaveText('0.3.0');
  await expect(section.getByTestId('update-last')).toHaveText(/Updated from 0.2.1 to 0.3.0/);
  await expect(banner).toHaveCount(0);
});

test('updates (stand-in): a problem before restarting is shown and Closet keeps running', async ({ page }) => {
  let phase: 'ready' | 'failed' = 'ready';
  await page.route('**/api/updates', (route) => route.fulfill({
    json: phase === 'ready' ? standIn() : standIn({ ready: false, problem: "Closet couldn't back up your closets, so it didn't install the update." }),
  }));
  await page.route('**/api/updates/install', (route) => {
    phase = 'failed';
    return route.fulfill({ status: 202, json: standIn({ busy: 'backing-up' }) });
  });
  await page.route('**/api/health', (route) => route.fulfill({ json: { ok: true, version: '0.2.1' } }));
  await login(page);
  const section = await openUpdates(page);
  await section.getByRole('button', { name: 'Install now' }).click();
  await expect(section.getByTestId('update-problem')).toHaveText(/couldn't back up/);
  await expect(page.getByRole('alertdialog')).toHaveCount(0);
  await expect(page.getByTestId('update-banner')).toHaveCount(0);
});
