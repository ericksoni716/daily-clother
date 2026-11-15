import type { Item, Photo, ShoeCheck, ShoeDrawn, ShoeTrace, ShoeView, ShoeViews } from './types';

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

/** A shoe can have this many photos besides its main one (6 in all). */
export const MAX_EXTRA_PHOTOS = 5;

/** The words under a photo of a shoe for the view it shows. */
export const VIEW_WORDS: Record<ShoeView, string> = {
  outer: 'outer side', inner: 'inner side', top: 'from above', front: 'front', back: 'back', sole: 'sole', other: 'other',
};

/** The photos are being sorted into views, or wait to be: the item page asks again until they are. */
export const sortingViews = (views: ShoeViews | null | undefined) => views?.state === 'waiting' || views?.state === 'sorting';

/** The short label under one of a shoe's photos: its view ("outer side?" when Claude was not sure), "sorting…"
 * while the photos are sorted (a view the owner gave stays), or null when it has none. */
export function viewLabel(photo: Photo, views: ShoeViews | null | undefined): string | null {
  if (photo.view && photo.view_by === 'owner') return VIEW_WORDS[photo.view];
  if (sortingViews(views)) return 'sorting…';
  if (!photo.view) return null;
  return photo.view_sure === false ? `${VIEW_WORDS[photo.view]}?` : VIEW_WORDS[photo.view];
}

/** The shoe's photos besides its main one. */
export const extraPhotos = (item: Pick<Item, 'photos'>) => item.photos.filter((p) => p.kind !== 'front');

/** How many more photos the shoe has room for. */
export const photoRoom = (item: Pick<Item, 'photos'>) => Math.max(0, MAX_EXTRA_PHOTOS - extraPhotos(item).length);

export const OUTSIDE_QUESTION = 'Which photo shows the outside of the shoe?';
export const ONE_SIDE_QUESTION = 'Is this the outside or the inside of the shoe?';
export const OUTSIDE_HINT = 'When you wear them, the outside faces away from the other shoe.';

/** What the item page asks while Closet cannot tell the outside of the shoe from the inside: about one photo (outside
 * or inside?), or which of several shows the outside. Each photo comes with its number in the row of photos. */
export function outsideQuestion(item: Pick<Item, 'photos' | 'views'>):
  { one: true; photos: [{ photo: Photo; n: number }] } | { one: false; photos: { photo: Photo; n: number }[] } | null {
  const ids = item.views?.state === 'asking' ? item.views.asking : null;
  if (!ids?.length) return null;
  const photos = ids.flatMap((id) => {
    const at = item.photos.findIndex((p) => p.id === id);
    return at < 0 ? [] : [{ photo: item.photos[at], n: at + 1 }];
  });
  if (!photos.length) return null;
  return photos.length === 1 ? { one: true, photos: [photos[0]] } : { one: false, photos };
}

/** The shoe is waiting to be drawn from its photos, being drawn, or its drawing is being changed from the owner's
 * note: the item page asks again until it is done. */
export const drawingShoe = (drawn: ShoeDrawn | null | undefined) =>
  drawn?.state === 'waiting' || drawn?.state === 'drawing' || drawn?.state === 'correcting';

/** A drawing's time in words: "48 s", "1 min 52 s". */
export function drawnTime(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${s % 60} s`;
}

/** Dollars in words: "$0.61". */
export const dollars = (usd: number) => `$${usd.toFixed(2)}`;

/** The line under a shoe's drawing: how long it took, how often it was checked against the photos, and what it cost
 * (or would cost) on the API key. Null when there is no drawing. */
export function drawnLine(drawn: ShoeDrawn | null | undefined): string | null {
  if (!drawn?.url || drawn.seconds == null) return null;
  const n = drawn.rounds ?? 0;
  const checked = n === 0 ? 'not checked against the photos' : n === 1 ? 'checked once against the photos'
    : `checked ${n} times against the photos`;
  const cost = dollars(drawn.cost_usd ?? 0);
  const [made, done] = drawn.corrected ? ['Changed', 'changed'] : ['Drawn', 'drawn'];
  if (drawn.route === 'api') return `${made} in ${drawnTime(drawn.seconds)}, ${checked} · ${cost} on the API key`;
  return `${made} in ${drawnTime(drawn.seconds)} on your Claude plan, ${checked} · about ${cost} if ${done} on the API key`;
}

/** The longest note on a drawing the app takes, in characters. */
export const NOTE_MAX = 200;

/** The line under a drawing changed from the owner's note: the note and what Claude says it changed. Null when the
 * drawing was not changed from a note, or while a change is being made. */
export function changedLine(drawn: ShoeDrawn | null | undefined): string | null {
  if (!drawn?.url || !drawn.corrected || drawn.correcting || !drawn.note) return null;
  return `Changed as you asked: “${drawn.note}”.${drawn.changed ? ` ${drawn.changed}` : ''}`;
}

/** What the button that swaps the drawing and the one kept before it says, or null when none is kept (or while the
 * shoe is drawn or changed). */
export function backLabel(drawn: ShoeDrawn | null | undefined): string | null {
  if (!drawn?.url || !drawn.has_previous || drawingShoe(drawn)) return null;
  return drawn.previous_newer ? 'Go to the newer drawing' : 'Go back to the drawing before';
}

/** The note box is offered once the shoe has a drawing, unless it is being drawn or changed, or in the demo closet. */
export const canCorrect = (drawn: ShoeDrawn | null | undefined, demo: boolean) =>
  Boolean(drawn?.url) && !demo && !drawingShoe(drawn);

export const DRAWN_DEMO = 'The demo closet is never sent to Claude, so its shoes are not drawn from their photos.';

/** What the item page offers for a shoe's drawing: draw it (never drawn), draw it again (it has one), try again (it
 * failed), or nothing (waiting, being drawn, its photos being sorted for the first time, or the demo closet). */
export function drawnOffer(item: Pick<Item, 'drawn' | 'views'>, demo: boolean): 'draw' | 'again' | 'retry' | null {
  const drawn = item.drawn;
  if (!drawn || demo || drawingShoe(drawn)) return null;
  if (drawn.state === 'failed') return 'retry';
  if (drawn.url) return 'again';
  if (sortingViews(item.views)) return null;   // drawn by itself once the photos are sorted
  return 'draw';
}

/** The question before drawing a shoe (again): what happens, how long it takes and roughly what it costs. */
export function drawQuestion(drawn: ShoeDrawn, again: boolean): string {
  const cost = `roughly ${dollars(drawn.about_usd)} on the API key, and nothing extra on your Claude plan`;
  return again
    ? `The new drawing replaces this one when it is done, in about two minutes. It costs ${cost}.`
    : `It takes about two minutes and costs ${cost}.`;
}
