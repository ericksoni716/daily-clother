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

describe('when the computer does not answer', () => {
  function load(fetch: ReturnType<typeof vi.fn>, saved: Response | undefined) {
    const cache = { match: vi.fn().mockResolvedValue(saved), put: vi.fn().mockResolvedValue(undefined) };
    const handlers = new Map<string, (event: unknown) => void>();
    runInNewContext(source, {
      self: {
        __VERSION__: 'test', __PRECACHE__: [], location: { origin: 'http://localhost' },
        addEventListener: (name: string, handler: (event: unknown) => void) => handlers.set(name, handler),
      },
      caches: { open: vi.fn().mockResolvedValue(cache) },
      fetch, URL, Headers, Response, setTimeout, clearTimeout, Promise,
    });
    return (request: Request) => {
      let result: Promise<Response> | undefined;
      handlers.get('fetch')!({ request, respondWith: (pending: Promise<Response>) => { result = pending; } });
      return result!;
    };
  }

  it('answers the closet from the saved copy after a few seconds instead of waiting for ever', async () => {
    vi.useFakeTimers();
    try {
      const never = vi.fn().mockReturnValue(new Promise(() => undefined));
      const answer = load(never, new Response('{"items":[]}'))(new Request('http://localhost/api/items'));
      await vi.advanceTimersByTimeAsync(6000);
      const response = await answer;
      expect(await response.text()).toBe('{"items":[]}');
      expect(response.headers.get('x-closet-from-cache')).toBe('1');
    } finally {
      vi.useRealTimers();
    }
  });

  it('opens the app from the saved page after a few seconds', async () => {
    vi.useFakeTimers();
    try {
      const never = vi.fn().mockReturnValue(new Promise(() => undefined));
      const request = new Request('http://localhost/today');
      Object.defineProperty(request, 'mode', { value: 'navigate' });
      const answer = load(never, new Response('<html>shell</html>'))(request);
      await vi.advanceTimersByTimeAsync(4000);
      expect(await (await answer).text()).toBe('<html>shell</html>');
    } finally {
      vi.useRealTimers();
    }
  });

  it('still uses a quick answer from the computer', async () => {
    const fresh = new Response('{"items":[1]}');
    const answer = load(vi.fn().mockResolvedValue(fresh), new Response('{"items":[]}'))(new Request('http://localhost/api/items'));
    expect(await answer).toBe(fresh);
  });
});
