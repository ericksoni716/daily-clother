import { useEffect, useRef } from 'react';

/**
 * Saves that are waiting (an edit still being typed, trip ticks in line behind another) are sent
 * at once when the page is closed, reloaded or hidden. The requests themselves are sent with
 * `keepalive` (see api.ts), so they reach Closet even though the page is gone.
 */
type Flush = () => void;

const flushers = new Set<Flush>();

/** Runs every registered flush now. One that fails does not stop the others. */
export function flushSaves(): void {
  for (const flush of [...flushers]) {
    try {
      flush();
    } catch {
      /* the page is going away: nothing to tell the owner */
    }
  }
}

/** Registers something to run when the page goes away; returns a function that removes it. */
export function whenLeaving(flush: Flush): () => void {
  flushers.add(flush);
  return () => void flushers.delete(flush);
}

type Target = Pick<EventTarget, 'addEventListener' | 'removeEventListener'>;

/**
 * Flushes on `pagehide` (closed or reloaded) and when the page becomes hidden (a phone may end a
 * hidden page without `pagehide`). Called once when the app starts; returns a function that stops it.
 */
export function listenForLeaving(win: Target, doc: Target & { visibilityState: string }): () => void {
  const onHide = () => flushSaves();
  const onVisibility = () => {
    if (doc.visibilityState === 'hidden') flushSaves();
  };
  win.addEventListener('pagehide', onHide);
  doc.addEventListener('visibilitychange', onVisibility);
  return () => {
    win.removeEventListener('pagehide', onHide);
    doc.removeEventListener('visibilitychange', onVisibility);
  };
}

/** Runs the latest `flush` given when the page goes away, for as long as the component is shown. */
export function useWhenLeaving(flush: Flush): void {
  const latest = useRef(flush);
  useEffect(() => {
    latest.current = flush;
  });
  useEffect(() => whenLeaving(() => latest.current()), []);
}

/**
 * Sends saves one at a time, in the order they were made (each waits for the one before). When
 * the page goes away, `flush` starts the ones still waiting at once, in order, so none is lost.
 */
export class SaveLine {
  private tail: Promise<unknown> = Promise.resolve();
  private waiting: (() => unknown)[] = [];

  add<T>(send: () => Promise<T>): Promise<T> {
    let started: Promise<T> | null = null;
    const start = () => (started ??= send());
    this.waiting.push(start);
    const run = this.tail.then(() => {
      this.waiting = this.waiting.filter((s) => s !== start);
      return start();
    });
    this.tail = run.catch(() => undefined);
    return run;
  }

  flush(): void {
    const waiting = this.waiting;
    this.waiting = [];
    waiting.forEach((start) => start());
  }
}
