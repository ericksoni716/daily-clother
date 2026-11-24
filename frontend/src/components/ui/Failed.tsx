import { WarnIcon } from '../Icons';
import { Button } from './Button';
import { EmptyState } from './EmptyState';
import { Notice } from './Notice';

/** What a read gives a screen (a TanStack query's result has all of it). */
export interface FailedRead {
  error: unknown;
  /** What was read before, if anything: it stays on screen, marked as from earlier. */
  data?: unknown;
  refetch(): unknown;
  isFetching?: boolean;
}

/**
 * The reads a screen waits for, as one (the piece and the words that describe it, say): failed when any of them failed,
 * with an earlier answer only when each has one, and Try again asking again for every read that failed or has nothing
 * yet, so the screen does not wait for ever on one that was never asked again.
 */
export function readsOf(...reads: FailedRead[]): FailedRead {
  const missing = reads.filter((r) => r.error || r.data === undefined);
  return {
    error: reads.find((r) => r.error)?.error ?? null,
    data: reads.every((r) => r.data !== undefined) ? reads.map((r) => r.data) : undefined,
    refetch: () => Promise.all(missing.map((r) => r.refetch())),
    isFetching: reads.some((r) => r.isFetching),
  };
}

/** The words, in one place (exported for their test). */
export const FAILED = {
  unreachable: "Nines on your computer can't be reached. Check that the computer is on and Nines is running.",
  fault: 'Nines on your computer answered with a fault. Trying again usually helps.',
  unreadable: "Nines on your computer sent an answer this page couldn't read. Trying again usually helps.",
  retry: 'Try again',
  retrying: 'Trying again…',
};

/** Why a read failed, in a sentence: the computer can't be reached, it answered with a fault, or what it said (a
 * sentence of its own, never a status text or code: `api.ts` sees to that). */
export function failedReason(error: unknown): string {
  const status = (error as { status?: unknown } | null)?.status;
  if (typeof status !== 'number') return FAILED.unreadable;
  if (status === 0) return FAILED.unreachable;
  if (status >= 500) return FAILED.fault;
  const said = (error as Error).message;
  return said && /[.?]$/.test(said.trim()) ? said : FAILED.fault;
}

/** The title over a screen that has nothing to show: "Couldn't load your closet." */
export const failedTitle = (what: string) => `Couldn't load ${what}.`;

/** The line above what a screen read before: "This is your closet as it was earlier. Nines on your computer …" */
export const earlierLine = (what: string, error: unknown) => `This is ${what} as it was earlier. ${failedReason(error)}`;

/**
 * What a screen shows when a read fails (`what` names what could not be read: "your closet", "this trip"). With
 * nothing read before: a title, why (in plain words) and Try again, in place of the screen's content. With an
 * earlier answer: that answer stays, and this is the line above it saying it is from earlier, with Try again. When the
 * computer cannot be reached and there is an earlier answer, nothing is added: the offline banner says it, once.
 * Draws nothing while the read has not failed, so a screen can put it where its content goes and forget about it.
 */
export function Failed({ query, what, testId = 'failed' }: { query: FailedRead; what: string; testId?: string }) {
  const { error, data, isFetching } = query;
  if (!error) return null;
  const retry = (
    <Button variant={data === undefined ? 'primary' : 'ghost'} small disabled={isFetching} onClick={() => void query.refetch()}>
      {isFetching ? FAILED.retrying : FAILED.retry}
    </Button>
  );
  if (data !== undefined) {
    if ((error as { status?: number }).status === 0) return null;
    return <Notice tone="warning" role="status" className="failed-earlier" testId={`${testId}-earlier`} action={retry}>{earlierLine(what, error)}</Notice>;
  }
  return (
    <div className="failed" role="alert" data-testid={testId}>
      <EmptyState icon={<WarnIcon />} title={failedTitle(what)} body={failedReason(error)} action={retry} />
    </div>
  );
}
