import { useCallback, useEffect, useRef, useState } from 'react';
import { cls } from './cls';

export type SaveState = 'idle' | 'saving' | 'saved' | 'failed';

/** What a save says while it runs and after: the same words everywhere a change saves as it is made. */
export const SAVE_WORDS: Record<Exclude<SaveState, 'idle'>, string> = {
  saving: 'Saving…',
  saved: 'Saved',
  failed: "Didn't save",
};

/** How long "Saved" stays before the line goes quiet again. */
const SAVED_MS = 3000;

/**
 * "Saving… / Saved / Didn't save · Try again" beside what was changed. The line keeps its height when it is quiet,
 * so nothing moves when it speaks.
 */
export function SaveStatus({ state, onRetry, className, testId }: {
  state: SaveState; onRetry?(): void; className?: string; testId?: string;
}) {
  return (
    <span className={cls('save-status', state === 'failed' && 'is-failed', className)} role="status" data-testid={testId}>
      {state !== 'idle' && SAVE_WORDS[state]}
      {state === 'failed' && onRetry && <> · <button type="button" className="btn btn-link btn-small" onClick={onRetry}>Try again</button></>}
    </span>
  );
}

/**
 * Runs a save and keeps what `SaveStatus` should say about it. `retry` runs the last save again. A save that fails
 * gives back false, so the screen can keep what was typed.
 */
export function useSaveStatus(): { state: SaveState; run(save: () => Promise<unknown>): Promise<boolean>; retry(): void } {
  const [state, setState] = useState<SaveState>('idle');
  const last = useRef<(() => Promise<unknown>) | null>(null);
  const timer = useRef(0);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const run = useCallback(async (save: () => Promise<unknown>) => {
    last.current = save;
    window.clearTimeout(timer.current);
    setState('saving');
    try {
      await save();
      setState('saved');
      timer.current = window.setTimeout(() => setState('idle'), SAVED_MS);
      return true;
    } catch {
      setState('failed');
      return false;
    }
  }, []);
  const retry = useCallback(() => {
    if (last.current) void run(last.current);
  }, [run]);
  return { state, run, retry };
}
