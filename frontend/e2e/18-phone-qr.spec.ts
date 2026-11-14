import { resolve } from 'node:path';
import jsQR from 'jsqr';
import type { Page } from '@playwright/test';
import { axeViolations } from './a11y';
import { expect, login, test } from './fixtures';

/** Phone access: a QR code of the address that reaches Closet, only when there is one. Tailscale is faked. */

const SHOTS = resolve(import.meta.dirname, '../../docs/screenshots');
const ADDRESS = 'https://closet-pc.example-tailnet.ts.net:8443';

async function fakePhone(page: Page, address: string | null) {
  await page.route('**/api/settings', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback();
    const original = await (await page.request.get('/api/settings')).json();
    await route.fulfill({
      json: {
        ...original,
        phone: address
          ? { tailscale_installed: true, running: true, address, command: 'tailscale serve --bg --https=8443 8765',
            stop_command: 'tailscale serve --https=8443 off', others_share: true }
          : { tailscale_installed: true, running: true, address: null, command: 'tailscale serve --bg --https=8443 8765',
            stop_command: null, others_share: true },
      },
    });
  });
}

/** Reads the code as it is drawn on screen, the way a camera would. */
async function readCode(page: Page): Promise<string | undefined> {
  const png = await page.locator('.phone-qr').screenshot();
  const { width, height, data } = await page.evaluate(async (src) => {
    const img = new Image();
    img.src = src;
    await img.decode();
    const canvas = document.createElement('canvas');
    canvas.width = img.width;
    canvas.height = img.height;
    const ctx = canvas.getContext('2d')!;
    ctx.drawImage(img, 0, 0);
    // a margin of the page's own background around it, as the camera sees it
    return { width: img.width, height: img.height, data: Array.from(ctx.getImageData(0, 0, img.width, img.height).data) };
  }, `data:image/png;base64,${png.toString('base64')}`);
  return jsQR(Uint8ClampedArray.from(data), width, height)?.data;
}

for (const theme of ['light', 'dark'] as const) {
  test(`phone access in ${theme}: a QR code of Closet's address, readable, with the address as text below`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme });
    await fakePhone(page, ADDRESS);
    await login(page);
    await page.goto('/settings');
    const section = page.getByRole('region', { name: 'Phone access', exact: true });
    const code = section.getByRole('img', { name: `QR code of ${ADDRESS}` });
    await expect(code).toBeVisible();
    await expect(code).toHaveAttribute('data-payload', ADDRESS);
    const box = (await code.boundingBox())!;
    expect(box.width).toBeGreaterThanOrEqual(180);
    expect(box.width).toBeLessThanOrEqual(220);
    expect(box.height).toBeCloseTo(box.width, 0);
    expect(await readCode(page)).toBe(ADDRESS);
    // the address stays copyable text, below the code
    const link = section.getByRole('link', { name: ADDRESS });
    await expect(link).toBeVisible();
    const [drawn, text] = [(await code.boundingBox())!, (await link.boundingBox())!];
    expect(text.y).toBeGreaterThan(drawn.y + drawn.height);
    expect(await axeViolations(page)).toEqual([]);
  });
}

test('phone access: no code when no share reaches Closet, only the plain explanation', async ({ page }) => {
  await fakePhone(page, null);
  await login(page);
  await page.goto('/settings');
  const section = page.getByRole('region', { name: 'Phone access', exact: true });
  await expect(section.getByText('Closet is not shared with your phone yet.')).toBeVisible();
  await expect(section.getByText('tailscale serve --bg --https=8443 8765')).toBeVisible();
  await expect(section.locator('.phone-qr')).toHaveCount(0);
  await expect(section.getByRole('img')).toHaveCount(0);
});

test.describe('pictures', () => {
  for (const [layout, viewport] of [['phone', { width: 390, height: 844 }], ['computer', { width: 1440, height: 900 }]] as const) {
    test(`phone access with its code, on a ${layout}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await fakePhone(page, ADDRESS);
      await login(page);
      await page.goto('/settings');
      const section = page.getByRole('region', { name: 'Phone access', exact: true });
      await section.scrollIntoViewIfNeeded();
      await expect(section.locator('.phone-qr')).toBeVisible();
      await page.evaluate(() => document.getElementById('s-phone')?.scrollIntoView({ block: 'start' }));
      // the code and the address under it are both in the picture, above the phone's tab bar
      const bar = await page.locator('nav.tabbar').boundingBox();
      const link = (await section.getByRole('link', { name: ADDRESS }).boundingBox())!;
      expect(link.y + link.height).toBeLessThanOrEqual(bar && bar.height ? bar.y : viewport.height);
      expect((await section.locator('.phone-qr').boundingBox())!.y).toBeGreaterThanOrEqual(0);
      await page.screenshot({ path: `${SHOTS}/phone-access-qr-${layout}.png` });
    });
  }
});
