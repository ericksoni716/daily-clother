import { describe, expect, it } from 'vitest';
import { availableLine, busyLine, checkedLine, followInstall, lastInstallLine, MODES, showBanner, type FollowDeps, type UpdateStatus } from './updates';

const status = (over: Partial<UpdateStatus> = {}): UpdateStatus => ({
  version: '0.2.1', mode: 'ask', can_install: true, checked_at: '2026-11-13T09:00:00Z', check_error: null, latest: '0.2.1',
  available: null, download_size: null, ready: false, problem: null, busy: null, last_install: null,
  releases_page: 'https://github.com/ericksoni716/daily-clother/releases', ...over,
});

const release = { version: '0.3.0', notes: 'Better outfits', page: 'https://github.com/ericksoni716/daily-clother/releases/tag/v0.3.0', published_at: null };

describe('update wording', () => {
  it('offers the three choices, asking first by default', () => {
    expect(MODES.map((m) => m.label)).toEqual(['Install updates by themselves', 'Ask me first', 'Never check']);
  });

  it('says when it last checked', () => {
    expect(checkedLine(status({ checked_at: null }))).toBe('Not checked yet.');
    expect(checkedLine(status({ checked_at: null, mode: 'never' }))).toMatch(/never to check/);
    expect(checkedLine(status())).toMatch(/^Last checked /);
  });

  it('says whether a new version is out and ready', () => {
    expect(availableLine(status())).toBe('You have the latest version.');
    expect(availableLine(status({ checked_at: null, latest: null }))).toBe('');
    expect(availableLine(status({ available: release, latest: '0.3.0' }))).toBe('Closet 0.3.0 is out.');
    expect(availableLine(status({ available: release, latest: '0.3.0', ready: true }))).toBe('Closet 0.3.0 is ready to install.');
    expect(availableLine(status({ available: release, latest: '0.3.0', can_install: false }))).toMatch(/by hand/);
  });

  it('shows the banner only in "Ask me first" once the new version is ready', () => {
    const ready = status({ available: release, latest: '0.3.0', ready: true });
    expect(showBanner(ready)).toBe(true);
    expect(showBanner(null)).toBe(false);
    expect(showBanner({ ...ready, mode: 'auto' })).toBe(false);
    expect(showBanner({ ...ready, mode: 'never' })).toBe(false);
    expect(showBanner({ ...ready, ready: false })).toBe(false);
    expect(showBanner({ ...ready, can_install: false })).toBe(false);
    expect(showBanner({ ...ready, busy: 'backing-up' })).toBe(false);
  });

  it('says what it is doing and how the last update went', () => {
    expect(busyLine(null)).toBe('');
    expect(busyLine('backing-up')).toMatch(/Backing up/);
    expect(lastInstallLine(status())).toBe('');
    const ok = { at: '2026-11-13T09:00:00Z', from: '0.2.0', to: '0.2.1', ok: true, note: null };
    expect(lastInstallLine(status({ last_install: ok }))).toMatch(/^Updated from 0.2.0 to 0.2.1/);
    expect(lastInstallLine(status({ last_install: { ...ok, ok: false, note: null } }))).toMatch(/was put back/);
    expect(lastInstallLine(status({ last_install: { ...ok, ok: false, note: 'It did not answer.' } }))).toBe('It did not answer.');
  });
});

/** A pretend Closet: each step of the clock answers health and status from a script. */
function pretend(script: (t: number) => { health?: string; status?: Partial<UpdateStatus> }): FollowDeps {
  let t = 0;
  return {
    now: () => t,
    sleep: async (ms) => { t += ms; },
    health: async () => {
      const v = script(t).health;
      if (!v) throw new Error('offline');
      return { version: v };
    },
    status: async () => {
      const s = script(t).status;
      if (!s) throw new Error('offline');
      return status(s);
    },
  };
}

describe('following an update', () => {
  it('reloads once the new Closet answers after the old one went away', async () => {
    const deps = pretend((t) => (t < 3000 ? { health: '0.2.1', status: { busy: 'restarting' } } : t < 6000 ? {} : { health: '0.3.0' }));
    expect((await followInstall('0.2.1', deps)).outcome).toBe('back');
  });

  it('reloads when the old Closet comes back after a rollback', async () => {
    const deps = pretend((t) => (t < 2000 ? { health: '0.2.1', status: { busy: 'restarting' } } : t < 5000 ? {} : { health: '0.2.1', status: {} }));
    expect((await followInstall('0.2.1', deps)).outcome).toBe('back');
  });

  it('stops with the problem when the update stopped before restarting', async () => {
    const deps = pretend(() => ({ health: '0.2.1', status: { problem: "Closet couldn't back up your closets." } }));
    const r = await followInstall('0.2.1', deps);
    expect(r.outcome).toBe('stopped');
    expect(r.problem).toMatch(/back up/);
  });

  it('gives up waiting after the time limit', async () => {
    const deps = pretend((t) => (t < 1000 ? { health: '0.2.1', status: { busy: 'restarting' } } : {}));
    expect((await followInstall('0.2.1', deps, 10_000)).outcome).toBe('timeout');
  });
});
