import { execSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { BACKEND_DIR, startBackend } from './server';

/** Builds the web page into the backend (unless E2E_SKIP_BUILD=1) and starts one backend for the suite. */
export default async function globalSetup() {
  const built = existsSync(resolve(BACKEND_DIR, 'closet', 'web', 'index.html'));
  if (process.env.E2E_SKIP_BUILD !== '1' || !built) {
    execSync('npx vite build --logLevel warn', { cwd: resolve(import.meta.dirname, '..'), stdio: 'inherit' });
  }
  const backend = await startBackend();
  process.env.E2E_BASE_URL = backend.url;
  return async () => {
    await backend.stop();
  };
}
