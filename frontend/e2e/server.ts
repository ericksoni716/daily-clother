import { spawn, type ChildProcess } from 'node:child_process';
import { copyFileSync, mkdirSync, mkdtempSync, rmSync } from 'node:fs';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

export const BACKEND_DIR = resolve(import.meta.dirname, '..', '..', 'backend');

export function freePort(): Promise<number> {
  return new Promise((res, rej) => {
    const srv = createServer();
    srv.unref();
    srv.on('error', rej);
    srv.listen(0, '127.0.0.1', () => {
      const addr = srv.address();
      const port = typeof addr === 'object' && addr ? addr.port : 0;
      srv.close(() => res(port));
    });
  });
}

export interface Backend {
  url: string;
  dataDir: string;
  stop(): Promise<void>;
}

/**
 * Starts the Closet backend on a free port with a fresh, empty data folder.
 * `fakes`: stand-ins for the model and for Claude (backend/tests/e2e_backend.py), so an item is cut out and described;
 * 'api': the plan cannot be used and the API key route talks to a stand-in that reports what each request used.
 * `tagFails`: with `fakes`, the first that many descriptions fail (see e2e_backend.py).
 */
export async function startBackend(opts: { model?: string; fakes?: boolean | 'api'; tagFails?: number } = {}): Promise<Backend> {
  const port = await freePort();
  const dataDir = mkdtempSync(join(process.env.CLOSET_E2E_TMP || tmpdir(), 'closet-e2e-'));
  if (opts.model) {
    mkdirSync(join(dataDir, 'models'), { recursive: true });
    copyFileSync(opts.model, join(dataDir, 'models', 'isnet-general-use.onnx'));
  }
  const python = process.env.CLOSET_PYTHON || 'python';
  const module = opts.fakes ? 'tests.e2e_backend' : 'closet';
  const child: ChildProcess = spawn(python, ['-m', module, '--no-browser', '--no-tray', '--port', String(port)], {
    cwd: BACKEND_DIR,
    env: {
      ...process.env, CLOSET_DATA_DIR: dataDir, CLOSET_PORT: String(port), CLOSET_NO_AUTO_DOWNLOAD: '1',
      CLOSET_E2E_ROUTES: opts.fakes === 'api' ? 'api' : '', CLOSET_E2E_TAG_FAILS: String(opts.tagFails ?? 0),
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let log = '';
  child.stdout?.on('data', (d) => (log += d));
  child.stderr?.on('data', (d) => (log += d));
  const url = `http://127.0.0.1:${port}`;
  const deadline = Date.now() + 60_000;
  for (;;) {
    if (child.exitCode !== null) throw new Error(`The backend exited early:\n${log}`);
    try {
      const r = await fetch(`${url}/api/health`);
      if (r.ok) break;
    } catch {
      /* not up yet */
    }
    if (Date.now() > deadline) {
      child.kill();
      throw new Error(`The backend did not start within 60 s:\n${log}`);
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  return {
    url,
    dataDir,
    async stop() {
      if (child.exitCode === null) {
        const exited = new Promise((r) => child.once('exit', r));
        child.kill('SIGTERM');
        await Promise.race([exited, new Promise((r) => setTimeout(r, 5000))]);
        if (child.exitCode === null) child.kill('SIGKILL');
      }
      rmSync(dataDir, { recursive: true, force: true });
    },
  };
}
