import { describe, expect, it } from 'vitest';
import { shownWithCopy, tellFailure } from './savedCopy';

const OFFLINE = 'Nothing was saved on this device yet.';
const gone = Object.assign(new Error("Can't reach Closet."), { status: 0 });
const refused = Object.assign(new Error('Something went wrong.'), { status: 500 });
const copy = () => ({ data: 'kept', savedAt: '2026-11-20T08:00:00Z' });
const none = () => null;

describe('what a screen with a copy on this device shows', () => {
  it('waits until the first read is in', () => {
    expect(shownWithCopy(undefined, null, copy, OFFLINE)).toEqual({ kind: 'loading' });
  });

  it('shows what was read, and does not look at the copy', () => {
    expect(shownWithCopy('read', null, () => { throw new Error('not asked'); }, OFFLINE))
      .toEqual({ kind: 'ready', data: 'read', savedAt: null });
  });

  it('shows the copy, saying when it was kept, when Closet cannot be reached', () => {
    expect(shownWithCopy(undefined, gone, copy, OFFLINE)).toEqual({ kind: 'ready', data: 'kept', savedAt: '2026-11-20T08:00:00Z' });
    // also when something was read before: the copy says it is from earlier, and nothing can be changed
    expect(shownWithCopy('read', gone, copy, OFFLINE)).toEqual({ kind: 'ready', data: 'kept', savedAt: '2026-11-20T08:00:00Z' });
  });

  it('says nothing was saved when Closet cannot be reached and there is no copy', () => {
    expect(shownWithCopy(undefined, gone, none, OFFLINE)).toEqual({ kind: 'error', offline: true, message: OFFLINE });
    expect(shownWithCopy('read', gone, none, OFFLINE)).toEqual({ kind: 'ready', data: 'read', savedAt: null });
  });

  it('keeps what was read when Closet answers with an error, and shows the error when nothing was', () => {
    expect(shownWithCopy('read', refused, copy, OFFLINE)).toEqual({ kind: 'ready', data: 'read', savedAt: null });
    expect(shownWithCopy(undefined, refused, copy, OFFLINE)).toEqual({ kind: 'error', offline: false, message: 'Something went wrong.' });
  });
});

describe('saying a failed read in a toast', () => {
  it('says a new failure while what was read before still shows', () => {
    expect(tellFailure(refused, true, 2, 1)).toBe(true);
  });
  it('says it once, and not when the screen already shows the error or Closet could not be reached', () => {
    expect(tellFailure(refused, true, 2, 2)).toBe(false);
    expect(tellFailure(refused, false, 2, 1)).toBe(false);
    expect(tellFailure(gone, true, 2, 1)).toBe(false);
    expect(tellFailure(null, true, 2, 1)).toBe(false);
  });
});
