import { describe, expect, it, vi } from 'vitest';
import { LAST_RELOAD_KEY, RELOAD_GAP_MS, mayReload, recoverSignIn, signInAddress, signInRanOut, withoutSignIn, type Page } from './signin';

const NOW = 1_800_000_000_000;

function page(over: Partial<Page> = {}, answer: Pick<Response, 'type' | 'status'> | Error = { type: 'opaqueredirect', status: 0 }) {
  const kept = new Map<string, string>();
  const go = vi.fn();
  const fetch = vi.fn(() => (answer instanceof Error ? Promise.reject(answer) : Promise.resolve(answer)));
  const p: Page = {
    hostname: 'closet.example.com', href: 'https://closet.example.com/today?x=1', fetch, go, now: () => NOW,
    storage: { getItem: (k) => kept.get(k) ?? null, setItem: (k, v) => void kept.set(k, v) },
    ...over,
  };
  return { p, go, fetch, kept };
}

describe("what the health check says when Cloudflare's sign-in ran out", () => {
  it.each([
    [{ type: 'opaqueredirect', status: 0 }, true],    // Cloudflare's redirect to its sign-in, not followed
    [{ type: 'basic', status: 401 }, true],           // Closet's own: Cloudflare's sign-in missing
    [{ type: 'basic', status: 200 }, false],          // reachable and signed in: offline was something else
    [{ type: 'basic', status: 502 }, false],          // Cloudflare cannot reach the computer
    [{ type: 'basic', status: 403 }, false],          // not allowed: a full load would not change that
    [null, false],                                    // the network itself is gone
  ] as const)('%o → %s', (answer, ranOut) => {
    expect(signInRanOut(answer as Pick<Response, 'type' | 'status'> | null)).toBe(ranOut);
  });
});

describe('a full load, at most once every two minutes', () => {
  it('is allowed the first time, after the gap, and when the note is from the future or unreadable', () => {
    expect(mayReload(NOW, null)).toBe(true);
    expect(mayReload(NOW, NOW - RELOAD_GAP_MS)).toBe(true);
    expect(mayReload(NOW, NOW - RELOAD_GAP_MS + 1)).toBe(false);
    expect(mayReload(NOW, NOW + 60_000)).toBe(true);
    expect(mayReload(NOW, Number.NaN)).toBe(true);
  });

  it('goes to the same address with ?signin= added, which is taken out again afterwards', () => {
    const address = signInAddress('https://closet.example.com/today?x=1#top', NOW);
    expect(address).toBe(`https://closet.example.com/today?x=1&signin=${NOW}#top`);
    expect(withoutSignIn(address)).toBe('/today?x=1#top');
    expect(withoutSignIn('https://closet.example.com/today?x=1')).toBeNull();
  });
});

describe('recoverSignIn', () => {
  it("loads the page again in full when Cloudflare's sign-in ran out, asking the health check without following", async () => {
    const { p, go, fetch, kept } = page();
    expect(await recoverSignIn(p)).toBe(true);
    expect(fetch).toHaveBeenCalledWith('/api/health', { redirect: 'manual', cache: 'no-store', credentials: 'same-origin' });
    expect(go).toHaveBeenCalledWith(`https://closet.example.com/today?x=1&signin=${NOW}`);
    expect(kept.get(LAST_RELOAD_KEY)).toBe(String(NOW));
  });

  it('does not loop: a second time within two minutes does nothing', async () => {
    const { p, go } = page();
    await recoverSignIn(p);
    expect(await recoverSignIn(p)).toBe(false);
    expect(await recoverSignIn({ ...p, now: () => NOW + RELOAD_GAP_MS - 1 })).toBe(false);
    expect(go).toHaveBeenCalledTimes(1);
    expect(await recoverSignIn({ ...p, now: () => NOW + RELOAD_GAP_MS })).toBe(true);
  });

  it('does nothing when the network itself is gone, or the computer answers', async () => {
    for (const answer of [new TypeError('Failed to fetch'), { type: 'basic', status: 200 } as const, { type: 'basic', status: 502 } as const]) {
      const { p, go } = page({}, answer);
      expect(await recoverSignIn(p)).toBe(false);
      expect(go).not.toHaveBeenCalled();
    }
  });

  it('never runs on this computer or through Tailscale, where offline means offline', async () => {
    for (const hostname of ['127.0.0.1', 'localhost', 'closet-pc.example-tailnet.ts.net']) {
      const { p, go, fetch } = page({ hostname });
      expect(await recoverSignIn(p)).toBe(false);
      expect(fetch).not.toHaveBeenCalled();
      expect(go).not.toHaveBeenCalled();
    }
  });

  it('does nothing without storage to keep a note of the last try, so it cannot loop', async () => {
    const { p, go } = page({ storage: null });
    expect(await recoverSignIn(p)).toBe(false);
    const broken = page({ storage: { getItem: () => { throw new Error('blocked'); }, setItem: () => undefined } });
    expect(await recoverSignIn(broken.p)).toBe(false);
    expect(go).not.toHaveBeenCalled();
    expect(broken.go).not.toHaveBeenCalled();
  });
});
