/**
 * What a screen shows when it reads through the query cache and keeps a copy on this device for when Nines cannot
 * be reached (What's missing, Insights). The choices are pure, so they are tested here.
 */
import { useEffect, useRef } from 'react';

export type Shown<T> =
  | { kind: 'loading' }
  /** `savedAt` is set when what shows is the copy kept on this device, and nothing can be changed. */
  | { kind: 'ready'; data: T; savedAt: string | null }
  | { kind: 'error'; message: string; offline: boolean };

/** A read that failed because Nines could not be reached at all (no answer), not because it said no. */
export const unreachable = (error: unknown): boolean => (error as { status?: number } | null)?.status === 0;

/**
 * What to show from a query's `data` and `error`. Nines cannot be reached: this device's copy (with when it was
 * kept), or `offlineMessage` when there is none. Nines answered with an error: what was read before stays (the
 * screen says what went wrong in a toast), or the error, with a way to try again, when nothing was read yet.
 */
export function shownWithCopy<T>(data: T | undefined, error: unknown, copy: () => { data: T; savedAt: string } | null,
  offlineMessage: string): Shown<T> {
  if (error && unreachable(error)) {
    const saved = copy();
    if (saved) return { kind: 'ready', data: saved.data, savedAt: saved.savedAt };
    if (data !== undefined) return { kind: 'ready', data, savedAt: null };
    return { kind: 'error', offline: true, message: offlineMessage };
  }
  if (data !== undefined) return { kind: 'ready', data, savedAt: null };
  if (error) return { kind: 'error', offline: false, message: (error as Error).message };
  return { kind: 'loading' };
}

/**
 * Whether a failed read should be said in a toast: Nines answered with an error (not unreachable), the screen still
 * shows what it read before, and this failure is newer than the last one said (`errorAt` against `toldAt`).
 */
export function tellFailure(error: unknown, hasData: boolean, errorAt: number, toldAt: number): boolean {
  return !!error && !unreachable(error) && hasData && errorAt > toldAt;
}

/** Says in a toast a read that failed while the screen still shows what it read before (see `tellFailure`). A failure
 * from before the screen opened is not said again. */
export function useTellFailure(error: Error | null, hasData: boolean, errorAt: number, toast: (message: string, kind: 'error') => void) {
  const told = useRef(errorAt);
  useEffect(() => {
    if (tellFailure(error, hasData, errorAt, told.current)) toast(error!.message, 'error');
    told.current = Math.max(told.current, errorAt);
  }, [error, hasData, errorAt, toast]);
}
