import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushSaves, listenForLeaving, SaveLine, whenLeaving } from './leave';

function page() {
  const win = new EventTarget();
  const doc = Object.assign(new EventTarget(), { visibilityState: 'visible' });
  const hide = (state: string) => {
    doc.visibilityState = state;
    doc.dispatchEvent(new Event('visibilitychange'));
  };
  return { win, doc, hide };
}

const cleanups: (() => void)[] = [];
afterEach(() => cleanups.splice(0).forEach((c) => c()));

describe('flushing waiting saves when the page goes away', () => {
  it('runs every registered save on pagehide', () => {
    const { win, doc } = page();
    cleanups.push(listenForLeaving(win, doc));
    const a = vi.fn();
    const b = vi.fn();
    cleanups.push(whenLeaving(a), whenLeaving(b));
    win.dispatchEvent(new Event('pagehide'));
    expect(a).toHaveBeenCalledTimes(1);
    expect(b).toHaveBeenCalledTimes(1);
  });

  it('runs them when the page becomes hidden, not when it shows again', () => {
    const { win, doc, hide } = page();
    cleanups.push(listenForLeaving(win, doc));
    const save = vi.fn();
    cleanups.push(whenLeaving(save));
    hide('visible');
    expect(save).not.toHaveBeenCalled();
    hide('hidden');
    expect(save).toHaveBeenCalledTimes(1);
  });

  it('a removed save is not run, and one that throws does not stop the others', () => {
    const { win, doc } = page();
    cleanups.push(listenForLeaving(win, doc));
    const gone = vi.fn();
    const after = vi.fn();
    whenLeaving(gone)();
    cleanups.push(whenLeaving(() => { throw new Error('boom'); }), whenLeaving(after));
    win.dispatchEvent(new Event('pagehide'));
    expect(gone).not.toHaveBeenCalled();
    expect(after).toHaveBeenCalledTimes(1);
  });

  it('stops listening when told to', () => {
    const { win, doc } = page();
    const stop = listenForLeaving(win, doc);
    const save = vi.fn();
    cleanups.push(whenLeaving(save));
    stop();
    win.dispatchEvent(new Event('pagehide'));
    expect(save).not.toHaveBeenCalled();
    flushSaves();
    expect(save).toHaveBeenCalledTimes(1);
  });
});

function held() {
  let release!: (v: string) => void;
  let refuse!: (e: Error) => void;
  const promise = new Promise<string>((res, rej) => {
    release = res;
    refuse = rej;
  });
  return { promise, release, refuse };
}

describe('SaveLine', () => {
  it('sends one at a time, in order', async () => {
    const line = new SaveLine();
    const sent: string[] = [];
    const first = held();
    const a = line.add(() => (sent.push('a'), first.promise));
    const b = line.add(async () => (sent.push('b'), 'B'));
    await Promise.resolve();
    expect(sent).toEqual(['a']);
    first.release('A');
    expect(await a).toBe('A');
    expect(await b).toBe('B');
    expect(sent).toEqual(['a', 'b']);
  });

  it('a failed save does not hold up the next', async () => {
    const line = new SaveLine();
    const a = line.add(() => Promise.reject(new Error('no')));
    const b = line.add(async () => 'B');
    await expect(a).rejects.toThrow('no');
    expect(await b).toBe('B');
  });

  it('on pagehide, starts the saves still waiting at once, in order, and sends each only once', async () => {
    const { win, doc } = page();
    cleanups.push(listenForLeaving(win, doc));
    const line = new SaveLine();
    cleanups.push(whenLeaving(() => line.flush()));
    const sent: string[] = [];
    const first = held();
    const a = line.add(() => (sent.push('a'), first.promise));
    const b = line.add(async () => (sent.push('b'), 'B'));
    const c = line.add(async () => (sent.push('c'), 'C'));
    await Promise.resolve();
    expect(sent).toEqual(['a']);

    win.dispatchEvent(new Event('pagehide'));
    expect(sent).toEqual(['a', 'b', 'c']);

    // the page stayed (it was only hidden): the line finishes without sending anything twice
    first.release('A');
    expect([await a, await b, await c]).toEqual(['A', 'B', 'C']);
    expect(sent).toEqual(['a', 'b', 'c']);
  });
});
