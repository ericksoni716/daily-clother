import { defineConfig } from '@playwright/test';

const executablePath = process.env.PLAYWRIGHT_CHROMIUM_PATH || undefined;

export default defineConfig({
  testDir: './e2e',
  // One backend is shared by the suite and its state (passphrase, profile) carries over, so run in order.
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [['list']],
  globalSetup: './e2e/global-setup.ts',
  use: {
    browserName: 'chromium',
    launchOptions: executablePath ? { executablePath } : {},
    trace: 'off',
    viewport: { width: 1440, height: 900 },
  },
});
