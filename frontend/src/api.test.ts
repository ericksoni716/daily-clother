import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, KEEPALIVE_BUDGET, keepaliveSize } from './api';

afterEach(() => vi.unstubAllGlobals());

function answering() {
  const calls: RequestInit[] = [];
  vi.stubGlobal('fetch', vi.fn(async (_path: string, init: RequestInit) => {
    calls.push(init);
    return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } });
  }));
  return calls;
}

describe('saves outlive the page', () => {
  it('sends a save with keepalive and the login cookie', async () => {
    const calls = answering();
    await api.patch('abc', { notes: 'soft' });
    expect(calls[0]).toMatchObject({ method: 'PATCH', keepalive: true, credentials: 'same-origin' });
    await api.rateOutfit('o1', 'loved');
    await api.putSettings({ autostart: true });
    await api.patchTrip('t1', { ticks: { 'Navy polo': true } });
    expect(calls.slice(1).map((c) => c.keepalive)).toEqual([true, true, true]);
  });

  it('does not use keepalive for reading, for photos or for questions that can be called off', async () => {
    const calls = answering();
    await api.items();
    await api.upload(new Blob(['x']), 'x.jpg', 'k');
    await api.today({} as never, new AbortController().signal);
    expect(calls.map((c) => c.keepalive)).toEqual([undefined, undefined, undefined]);
  });

  it('stays within the browser allowance for bodies on their way together', () => {
    const post = { method: 'POST' };
    expect(keepaliveSize('PUT', '{"a":1}', post, 0)).toBe(7);
    expect(keepaliveSize('PUT', 'é', post, 0)).toBe(2);
    expect(keepaliveSize('PUT', 'x'.repeat(10), post, KEEPALIVE_BUDGET - 10)).toBe(10);
    expect(keepaliveSize('PUT', 'x'.repeat(11), post, KEEPALIVE_BUDGET - 10)).toBeNull();
    expect(keepaliveSize('POST', undefined, post, 0)).toBe(0);
    expect(KEEPALIVE_BUDGET).toBeLessThan(64 * 1024);
  });

  it('a save sent while others use up the allowance goes as a normal request', async () => {
    const calls: RequestInit[] = [];
    const waiting: (() => void)[] = [];
    vi.stubGlobal('fetch', vi.fn((_path: string, init: RequestInit) => {
      calls.push(init);
      return new Promise<Response>((res) => waiting.push(() => res(new Response(null, { status: 204 }))));
    }));
    const big = 'x'.repeat(30 * 1024);
    const first = api.patch('a', { notes: big });
    const second = api.patch('b', { notes: big });
    expect(calls.map((c) => c.keepalive)).toEqual([true, undefined]);
    waiting.forEach((w) => w());
    await Promise.all([first, second]);
    // once answered, the allowance is free again
    void api.patch('c', { notes: big });
    expect(calls[2].keepalive).toBe(true);
    waiting[2]();
  });
});
