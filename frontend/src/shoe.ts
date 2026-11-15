import type { ShoeCheck, ShoeTrace } from './types';

/** What the item page says about a shoe's trace: while it is traced, or why it is drawn from its details. */
export function traceNotice(trace: ShoeTrace | null | undefined): { tone: 'info' | 'warn'; text: string; retake: boolean } | null {
  if (!trace?.message) return null;
  if (trace.state === 'waiting' || trace.state === 'working') return { tone: 'info', text: trace.message, retake: false };
  if (trace.state === 'refused' || trace.state === 'failed') return { tone: 'warn', text: trace.message, retake: true };
  return null;
}

/** The trace is still being made: the item page asks again until it is done. */
export const tracing = (trace: ShoeTrace | null | undefined) => trace?.state === 'waiting' || trace?.state === 'working';

export type Nudge = 'toe' | 'heel' | 'up' | 'down';
/** How far one tap moves a mark, in cm: towards the toe, and up. */
export const NUDGE_CM = 0.5;
export const NUDGES: { dir: Nudge; step: [number, number]; arrow: string }[] = [
  { dir: 'toe', step: [NUDGE_CM, 0], arrow: '←' },
  { dir: 'up', step: [0, NUDGE_CM], arrow: '↑' },
  { dir: 'down', step: [0, -NUDGE_CM], arrow: '↓' },
  { dir: 'heel', step: [-NUDGE_CM, 0], arrow: '→' },
];
const TOWARDS: Record<Nudge, string> = { toe: 'towards the toe', heel: 'towards the heel', up: 'up', down: 'down' };

export function nudgeLabel(title: string, dir: Nudge): string {
  return `Move the ${title} ${TOWARDS[dir]}`;
}

/** Add's instant check, in a sentence for the top of the result. */
export function checkHeadline(check: ShoeCheck): string {
  return check.ok ? 'This photo should trace well.' : 'This photo may not trace well.';
}

export type FrontKind = 'shape' | 'photo';
/** The two front views of a traced shoe on the outfit figure, in the owner's words. */
export const FRONT_VIEWS: { kind: FrontKind; title: string; about: string }[] = [
  { kind: 'shape', title: "From the shoe's shape", about: 'Its style, in the colours from your photo. Always neat.' },
  { kind: 'photo', title: 'From your photo', about: 'Turned from your photo, so it looks more like your shoe.' },
];

/** The small drawing of a traced shoe from the front, as the figure would draw it with `kind`. */
export function frontPreviewUrl(item: { id: string; updated_at: string }, kind: FrontKind): string {
  return `/api/items/${encodeURIComponent(item.id)}/trace/front.svg?kind=${kind}&v=${encodeURIComponent(item.updated_at)}`;
}
