import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, CLIENT_HEADER, connection, KEEPALIVE_BUDGET, keepaliveSize, OPEN_TIMEOUT_MS, UNREACHABLE } from './api';

afterEach(() => {
  vi.unstubAllGlobals();
  connection.set(false);
});

function answering() {
  const calls: RequestInit[] = [];
  vi.stubGlobal('fetch', vi.fn(async (_path: string, init: RequestInit) => {
    calls.push(init);
    return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } });
  }));
  return calls;
}

describe('interrupted responses', () => {
  it('reports a connection lost while reading the body as offline', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(new ReadableStream({
      start(controller) {
        controller.error(new TypeError('connection closed'));
      },
    }))));

    await expect(api.session()).rejects.toMatchObject({ status: 0, message: UNREACHABLE });
    expect(connection.offline).toBe(true);

    answering();
    await api.session();
    expect(connection.offline).toBe(false);
  });

  it('does not treat cancelling a response body as a connection failure', async () => {
    const aborted = new DOMException('Cancelled', 'AbortError');
    vi.stubGlobal('fetch', vi.fn(async () => new Response(new ReadableStream({
      start(controller) {
        controller.error(aborted);
      },
    }))));

    await expect(api.today({} as never, new AbortController().signal)).rejects.toBe(aborted);
    expect(connection.offline).toBe(false);
  });
});

describe("Closet's own page", () => {
  it('says so on every call, with a body, a photo or nothing', async () => {
    const calls = answering();
    await api.session();
    await api.patch('abc', { notes: 'soft' });
    await api.upload(new Blob(['x']), 'x.jpg', 'k');
    await api.retag('abc');
    expect(calls.map((c) => (c.headers as Record<string, string>)[CLIENT_HEADER])).toEqual(['1', '1', '1', '1']);
    expect((calls[1].headers as Record<string, string>)['Content-Type']).toBe('application/json');
    expect((calls[2].headers as Record<string, string>)['Content-Type']).toBeUndefined();   // the browser sets the form's
  });
});

describe('saves outlive the page', () => {
  it('sends a save with keepalive and its cookies', async () => {
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

describe("a shoe's photos", () => {
  function recording() {
    const calls: { path: string; init: RequestInit }[] = [];
    vi.stubGlobal('fetch', vi.fn(async (path: string, init: RequestInit) => {
      calls.push({ path, init });
      return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } });
    }));
    return calls;
  }

  it('marks a shoe added from "A shoe", so its photos are sorted into views', async () => {
    const calls = recording();
    await api.upload(new Blob(['x']), 'x.jpg', 'k', null, undefined, true);
    await api.upload(new Blob(['x']), 'x.jpg', 'k2');
    expect((calls[0].init.body as FormData).get('shoe')).toBe('true');
    expect((calls[1].init.body as FormData).get('shoe')).toBeNull();
  });

  it('adds a photo without saying its view, removes one, and gives the owner\'s answer', async () => {
    const calls = recording();
    await api.addShoePhoto('a b', new Blob(['x']), 'x.jpg', 'f'.repeat(64));
    await api.removeShoePhoto('a b', 'p/1');
    await api.setPhotoView('a b', 'p1', 'outer');
    expect(calls.map((c) => [c.init.method, c.path])).toEqual([
      ['POST', '/api/items/a%20b/photos'], ['DELETE', '/api/items/a%20b/photos/p%2F1'], ['PUT', '/api/items/a%20b/photos/p1/view']]);
    const form = calls[0].init.body as FormData;
    expect(form.get('view')).toBeNull();
    expect(form.get('photo_sha256')).toBe('f'.repeat(64));
    expect(JSON.parse(calls[2].init.body as string)).toEqual({ view: 'outer' });
  });

  it('asks for a shoe to be drawn from its photos again', async () => {
    const calls = recording();
    await api.drawShoe('a b');
    expect(calls.map((c) => [c.init.method, c.path])).toEqual([['POST', '/api/items/a%20b/drawn']]);
  });

  it("sends the owner's note on a shoe's drawing, and goes back to the drawing before", async () => {
    const calls = recording();
    await api.correctDrawing('a b', 'the laces are black');
    await api.drawingBack('a b');
    await api.correctDrawing('a b', 'the heel is taller', 'side');
    expect(calls.map((c) => [c.init.method, c.path])).toEqual([
      ['POST', '/api/items/a%20b/drawn/correct'], ['POST', '/api/items/a%20b/drawn/back'],
      ['POST', '/api/items/a%20b/drawn/correct']]);
    expect(JSON.parse(calls[0].init.body as string)).toEqual({ note: 'the laces are black', about: 'front' });
    expect(JSON.parse(calls[2].init.body as string)).toEqual({ note: 'the heel is taller', about: 'side' });
  });
});

describe('a computer that does not answer', () => {
  it('gives up on the opening questions after a while and shows Nines as out of reach', async () => {
    vi.useFakeTimers();
    try {
      vi.stubGlobal('fetch', vi.fn((_path: string, init: RequestInit) => new Promise((_resolve, reject) => {
        init.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
      })));
      const asking = expect(api.session()).rejects.toMatchObject({ status: 0, message: UNREACHABLE });
      await vi.advanceTimersByTimeAsync(OPEN_TIMEOUT_MS);
      await asking;
      expect(connection.offline).toBe(true);
    } finally {
      vi.useRealTimers();
    }
  });
});
