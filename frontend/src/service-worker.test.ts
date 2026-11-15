import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { describe, expect, it, vi } from 'vitest';

const source = readFileSync(new URL('../sw/sw.js', import.meta.url), 'utf8');

describe('the offline drawing cache', () => {
  it.each([
    ['no-store', false],
    ['private, no-store', false],
    ['private, max-age=31536000, immutable', true],
  ])('respects Cache-Control: %s', async (control, keep) => {
    const cache = { match: vi.fn().mockResolvedValue(undefined), put: vi.fn().mockResolvedValue(undefined) };
    const response = new Response('<svg/>', { headers: { 'Cache-Control': control } });
    const fetch = vi.fn().mockResolvedValue(response);
    const handlers = new Map<string, (event: unknown) => void>();
    runInNewContext(source, {
      self: {
        __VERSION__: 'test', __PRECACHE__: [], location: { origin: 'http://localhost' },
        addEventListener: (name: string, handler: (event: unknown) => void) => handlers.set(name, handler),
      },
      caches: { open: vi.fn().mockResolvedValue(cache) },
      fetch, URL,
    });
    const request = new Request('http://localhost/api/items/example/illustration.svg?v=old');
    let result: Promise<Response> | undefined;
    handlers.get('fetch')!({ request, respondWith: (pending: Promise<Response>) => { result = pending; } });
    expect(await result).toBe(response);
    expect(fetch).toHaveBeenCalledWith(request);
    expect(cache.put).toHaveBeenCalledTimes(keep ? 1 : 0);
  });
});
