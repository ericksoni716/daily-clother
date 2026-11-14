import { expect, login, test, useProfile } from './fixtures';

test.afterEach(async ({ page }) => {
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

test.describe('phone', () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test('bottom tab bar, two-column grid, detail as its own screen', async ({ page }) => {
    await login(page);
    await useProfile(page, 'demo');
    const tabbar = page.locator('nav.tabbar');
    await expect(tabbar).toBeVisible();
    await expect(page.locator('nav.sidebar')).toBeHidden();
    for (const name of ['Today', 'Closet', 'Add', 'Missing', 'Settings']) await expect(tabbar.getByRole('link', { name })).toBeVisible();
    const bar = (await tabbar.boundingBox())!;
    expect(bar.y + bar.height).toBeCloseTo(844, 0);

    const tiles = page.getByTestId('tile');
    const a = (await tiles.nth(0).boundingBox())!;
    const b = (await tiles.nth(1).boundingBox())!;
    const c = (await tiles.nth(2).boundingBox())!;
    expect(b.y).toBeCloseTo(a.y, 0);
    expect(c.y).toBeGreaterThan(a.y + a.height - 1);
    expect(a.height).toBeCloseTo(b.height, 0);

    // no horizontal page scroll
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);

    await tiles.filter({ hasText: 'Navy polo' }).click();
    await expect(page.getByRole('link', { name: 'Closet' }).first()).toBeVisible();
    await expect(page.locator('.detail-panel')).toHaveCount(0);
    await expect(page.getByTestId('tile')).toHaveCount(0);
    // a detail opens its choices in a sheet from the bottom of the screen
    await page.getByRole('button', { name: /^What is it\?:/ }).click();
    const picker = page.getByRole('dialog', { name: 'What is it?' });
    await expect(picker.getByRole('searchbox')).toBeVisible();
    await expect(picker.getByRole('group', { name: 'Groups' })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await picker.getByRole('button', { name: 'Done' }).click();

    await tabbar.getByRole('link', { name: 'Add' }).click();
    await expect(page.getByRole('button', { name: 'Take photo' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Choose from library' })).toBeVisible();
    await expect(page.getByTestId('camera-input')).toHaveAttribute('capture', 'environment');
  });

  test('five slots with Add in the middle; Review is reached from the closet; Add stays, disabled, offline', async ({ page, context }) => {
    await login(page);
    await useProfile(page, 'demo');
    const tabbar = page.locator('nav.tabbar');
    const links = tabbar.getByRole('link');
    await expect(links).toHaveCount(5);
    expect((await links.allInnerTexts()).map((t) => t.split('\n')[0])).toEqual(['Today', 'Closet', 'Add', 'Missing', 'Settings']);
    await expect(tabbar.getByRole('link', { name: 'Review', exact: true })).toHaveCount(0);
    await expect(tabbar.getByRole('link', { name: 'Trips' })).toHaveCount(0);

    // the demo closet has pieces to check: a dot on Closet and a notice at the top of the closet that leads to Review
    await expect(tabbar.getByTestId('review-dot')).toBeVisible();
    await expect(tabbar.getByRole('link', { name: /Closet/ })).toHaveAccessibleName(/Closet \(\d+ items to review\)/);
    const notice = page.getByTestId('review-notice');
    await expect(notice).toContainText('need a quick check');
    await notice.getByRole('link', { name: 'Review' }).click();
    await expect(page).toHaveURL(/\/review$/);
    await expect(tabbar.getByRole('link', { name: /Closet/ })).toHaveAttribute('aria-current', 'page');

    // the demo strip is one slim line
    const strip = (await page.locator('.ribbon').boundingBox())!;
    expect(strip.height).toBeLessThanOrEqual(32);
    await expect(page.locator('.ribbon').getByRole('button', { name: 'Leave the demo closet' })).toHaveText('Leave');

    // offline: Add keeps its place as a disabled button
    await page.goto('/');
    await page.waitForFunction(() => navigator.serviceWorker?.controller != null, null, { timeout: 15_000 });
    await page.reload();
    await expect(page.getByTestId('tile').first()).toBeVisible();
    await page.waitForLoadState('networkidle');
    await context.setOffline(true);
    try {
      await page.reload();
      await expect(page.getByText('Offline: showing your saved closet')).toBeVisible();
      await expect(links).toHaveCount(4);
      const add = tabbar.getByRole('button', { name: 'Add' });
      await expect(add).toBeDisabled();
      await expect(add).toHaveAttribute('title', /needs Closet on your computer/);
      expect((await tabbar.locator('> *').allInnerTexts()).map((t) => t.split('\n')[0])).toEqual(['Today', 'Closet', 'Add', 'Missing', 'Settings']);
    } finally {
      await context.setOffline(false);
    }
  });
});

// Every route lights exactly one link in the sidebar and one tab on the phone.
const ROUTES: [path: string, sidebar: string, tab: string][] = [
  ['/', 'Closet', 'Closet'],
  ['/archived', 'Closet', 'Closet'],
  ['/insights', 'Closet', 'Closet'],
  ['/review', 'Review', 'Closet'],
  ['/today', 'Today', 'Today'],
  ['/today/worn', 'Today', 'Today'],
  ['/trips', 'Trips', 'Today'],
  ['/missing', "What's missing", 'Missing'],
  ['/missing/check', "What's missing", 'Missing'],
  ['/add', 'Add clothes', 'Add'],
  ['/settings', 'Settings', 'Settings'],
];

test('aria-current marks the right link on every route, on a computer and a phone', async ({ page }) => {
  await login(page);
  for (const [layout, viewport, nav, column] of [
    ['computer', { width: 1440, height: 900 }, 'nav.sidebar', 1],
    ['phone', { width: 390, height: 844 }, 'nav.tabbar', 2],
  ] as const) {
    await page.setViewportSize(viewport);
    for (const route of ROUTES) {
      await page.goto(route[0]);
      const current = page.locator(`${nav} [aria-current="page"]`);
      await expect(current, `${layout} ${route[0]}`).toHaveCount(1);
      expect((await current.innerText()).split('\n')[0].trim(), `${layout} ${route[0]}`).toBe(route[column]);
    }
  }
});

test.describe('desktop', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('sidebar, grid and detail panel side by side', async ({ page }) => {
    await login(page);
    await useProfile(page, 'demo');
    await expect(page.locator('nav.tabbar')).toBeHidden();
    const sidebar = page.locator('nav.sidebar');
    await expect(sidebar).toBeVisible();
    // Add clothes first, Settings at the foot, Archived only from the closet's own switch
    await expect(sidebar.getByRole('link', { name: 'Review' })).toBeVisible();   // the demo closet has pieces to check
    const names = (await sidebar.getByRole('link').allInnerTexts()).map((t) => t.split('\n')[0].trim());
    expect(names).toEqual(['Add clothes', 'Today', 'Closet', 'Review', 'Trips', "What's missing", 'Settings']);
    const settings = (await sidebar.getByRole('link', { name: 'Settings' }).boundingBox())!;
    expect(settings.y + settings.height).toBeGreaterThan(900 - 60);
    await page.getByTestId('tile').filter({ hasText: 'Navy polo' }).click();
    await expect(page).toHaveURL(/\/item\//);
    const panel = page.locator('aside.detail-panel');
    await panel.getByRole('button', { name: /^What is it\?:/ }).click();
    await expect(panel.getByRole('dialog', { name: 'What is it?' }).getByRole('group', { name: 'Groups' })).toBeVisible();

    const s = (await sidebar.boundingBox())!;
    const g = (await page.locator('section.closet-main').boundingBox())!;
    const p = (await panel.boundingBox())!;
    expect(s.x + s.width).toBeLessThanOrEqual(g.x);
    expect(g.x + g.width).toBeLessThanOrEqual(p.x);
    expect(p.x + p.width).toBeLessThanOrEqual(1440);
    // all three share the top of the screen
    expect(Math.abs(g.y - p.y)).toBeLessThan(40);
    expect(s.y).toBeLessThan(10);

    // keyboard: the selected tile and the panel's chips are reachable
    await expect(page.getByTestId('tile').filter({ hasText: 'Navy polo' })).toHaveAttribute('aria-current', 'true');
    await page.keyboard.press('Tab');
    await expect(page.locator(':focus')).toBeVisible();

    await sidebar.getByRole('link', { name: 'Add' }).click();
    await expect(page.getByTestId('dropzone')).toBeVisible();
  });
});
