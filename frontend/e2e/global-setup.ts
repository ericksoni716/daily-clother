import { execSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { BACKEND_DIR } from './server';

/**
 * Builds the web page into the backend (unless E2E_SKIP_BUILD=1), once for the whole run. The backends are started by
 * the workers, one per spec file (fixtures.ts).
 */
export default async function globalSetup() {
  const built = existsSync(resolve(BACKEND_DIR, 'closet', 'web', 'index.html'));
  if (process.env.E2E_SKIP_BUILD !== '1' || !built) {
    execSync('npx vite build --logLevel warn', { cwd: resolve(import.meta.dirname, '..'), stdio: 'inherit' });
  }
}
