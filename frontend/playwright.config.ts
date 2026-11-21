import { availableParallelism } from 'node:os';
import { defineConfig } from '@playwright/test';

const executablePath = process.env.PLAYWRIGHT_CHROMIUM_PATH || undefined;

/**
 * How many spec files run at once. Each worker has a browser and its own backend (e2e/fixtures.ts), so a worker needs
 * about a core: half the cores, at most 4, on a computer; 4 in CI (GitHub's runner for a public repository has 4
 * cores). E2E_WORKERS sets it, and `npm run e2e -- --workers=1` runs one file at a time (for debugging).
 */
function workers(): number {
  const asked = Number(process.env.E2E_WORKERS);
  if (Number.isInteger(asked) && asked > 0) return asked;
  if (process.env.CI) return 4;
  return Math.max(1, Math.min(4, Math.floor(availableParallelism() / 2)));
}

export default defineConfig({
  testDir: './e2e',
  // Files run side by side, each on a backend of its own; the tests inside a file run in order, on the same backend.
  fullyParallel: false,
  workers: workers(),
  // Room for a busy computer: with several files at once, each on a backend that has just started (nothing drawn or
  // worked out yet), a first answer can take well over the few seconds it takes alone. A wait only lasts this long
  // when the test is about to fail.
  timeout: 90_000,
  expect: { timeout: 20_000 },
  reporter: [['list']],
  globalSetup: './e2e/global-setup.ts',
  use: {
    browserName: 'chromium',
    launchOptions: executablePath ? { executablePath } : {},
    trace: 'off',
    viewport: { width: 1440, height: 900 },
  },
});
