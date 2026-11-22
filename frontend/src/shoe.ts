import type { Item, Photo, ShoeDrawn, ShoeTrace, ShoeView, ShoeViews } from './types';

/** What the item page says about a shoe's trace once it is done: why it is drawn from its details, with a retake.
 * While it is traced the item's progress says so (progress.ts). Nothing once the shoe's drawing is Claude's side
 * (`sideShown`): it is not drawn from its details then. */
export function traceNotice(trace: ShoeTrace | null | undefined, sideShown = false):
  { tone: 'warn'; text: string; retake: boolean } | null {
  if (!trace?.message || sideShown) return null;
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

/** A shoe can have this many photos besides its main one (6 in all). */
export const MAX_EXTRA_PHOTOS = 5;
/** A shoe's photos in all, as Add takes them at once. */
export const MAX_PHOTOS = MAX_EXTRA_PHOTOS + 1;

/** Add's sentence for photos that did not fit in the row. */
export const tooManyPhotos = (left: number) =>
  `A shoe can have up to ${MAX_PHOTOS} photos, so ${left === 1 ? 'one photo was' : `${left} photos were`} not added.`;

/** What Add says once it has sent a shoe's photos: `added` of the `total` chosen went in (the first made the shoe). */
export function shoeAddedLine(added: number, total: number): string {
  if (total <= 1) return 'The shoe is added. In a moment Nines removes the background and describes it.';
  if (added >= total) {
    return `The shoe is added with its ${total} photos. In a moment Nines removes the background and works out which photo is which.`;
  }
  return `The shoe is added with ${added} of its ${total} photos.`;
}

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

/** Once the photos are sorted, none shows the shoe from the side (the outer or inner side): the item page says that
 * a photo of its side would help. */
export function noSidePhoto(item: Pick<Item, 'photos' | 'views'>): boolean {
  return item.views?.state === 'sorted' && item.photos.length > 0
    && !item.photos.some((p) => p.view === 'outer' || p.view === 'inner');
}
export const NO_SIDE = 'None of these photos shows the shoe from the side. A photo of its side would help the drawing.';

/** The shoe's photos besides its main one. */
export const extraPhotos = (item: Pick<Item, 'photos'>) => item.photos.filter((p) => p.kind !== 'front');

/** How many more photos the shoe has room for. */
export const photoRoom = (item: Pick<Item, 'photos'>) => Math.max(0, MAX_EXTRA_PHOTOS - extraPhotos(item).length);

export const OUTSIDE_QUESTION = 'Which photo shows the outside of the shoe?';
export const ONE_SIDE_QUESTION = 'Is this the outside or the inside of the shoe?';
export const OUTSIDE_HINT = 'When you wear them, the outside faces away from the other shoe.';

/** Once a shoe's photos are sorted and nothing is being asked, the owner can still say which photo shows the outside
 * (a swap Claude was sure of would otherwise stay). Not while they are sorted, nor for a shoe never sorted (the demo
 * closet's, or one kept from before), whose main photo would not follow the answer. */
export function canSayOutside(item: Pick<Item, 'photos' | 'views'>): boolean {
  return item.views?.state === 'sorted' && item.photos.length > 0;
}

/** What the item page asks while Nines cannot tell the outside of the shoe from the inside: about one photo (outside
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
 * (or would cost) on the API key. Null when there is no drawing, or when the last change was to the side (the side's
 * own line says how that change went, `sideMadeLine`, and one such line is enough). */
export function drawnLine(drawn: ShoeDrawn | null | undefined): string | null {
  if (!drawn?.url || drawn.seconds == null || sideMadeLine(drawn)) return null;   // the side's change says its own
  return madeLine(drawn.corrected, drawn.seconds, drawn.rounds, drawn.cost_usd, drawn.route);
}

function madeLine(changed: boolean, seconds: number, rounds: number | null | undefined, usd: number | null | undefined,
  route: string | null | undefined): string {
  const n = rounds ?? 0;
  const checked = n === 0 ? 'not checked against the photos' : n === 1 ? 'checked once against the photos'
    : `checked ${n} times against the photos`;
  const cost = dollars(usd ?? 0);
  const [made, done] = changed ? ['Changed', 'changed'] : ['Drawn', 'drawn'];
  if (route === 'api') return `${made} in ${drawnTime(seconds)}, ${checked} · ${cost} on the API key`;
  return `${made} in ${drawnTime(seconds)} on your Claude plan, ${checked} · about ${cost} if ${done} on the API key`;
}

/** The longest note on a drawing the app takes, in characters. */
export const NOTE_MAX = 200;

/** The line under a drawing changed from the owner's note: the note and what Claude says it changed. Null when the
 * drawing was not changed from a note, while a change is being made, or when the last change was to the side (its
 * own line says so, `sideChangedLine`). */
export function changedLine(drawn: ShoeDrawn | null | undefined): string | null {
  if (!drawn?.url || !drawn.corrected || drawn.correcting || drawn.side_corrected || !drawn.note) return null;
  return `Changed as you asked: “${drawn.note}”.${drawn.changed ? ` ${drawn.changed}` : ''}`;
}

/** The line under the side drawing when the last change was to it, from the owner's note: the note and what Claude
 * says it changed. Null otherwise, and while a change is being made. */
export function sideChangedLine(drawn: ShoeDrawn | null | undefined): string | null {
  if (!drawn?.side || !drawn.side_corrected || drawn.correcting || !drawn.side_note) return null;
  return `Changed as you asked: “${drawn.side_note}”.${drawn.side_changed ? ` ${drawn.side_changed}` : ''}`;
}

/** How long the change to the side took, how often it was checked and what it cost, under the side drawing once the
 * last change was to it. Null otherwise. */
export function sideMadeLine(drawn: ShoeDrawn | null | undefined): string | null {
  const side = drawn?.side;
  if (!side || !sideChangedLine(drawn) || side.seconds == null) return null;
  return madeLine(true, side.seconds, side.rounds, side.cost_usd, side.route);
}

/** Which drawing a note is about. */
export type NoteAbout = 'front' | 'side';

/** The choices of which drawing a note is about: the front and the side, once the shoe has a side; none otherwise
 * (the note is about the front, as it always was). */
export function noteChoices(drawn: ShoeDrawn | null | undefined): { value: NoteAbout; label: string }[] {
  return drawn?.side ? [{ value: 'front', label: 'The front' }, { value: 'side', label: 'The side' }] : [];
}

/** What the page says once a note is sent: which drawing is being changed. */
export const sentAs = (about: NoteAbout) =>
  about === 'side' ? 'Changing the side drawing as you asked' : 'Changing the drawing as you asked';

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
    ? `The new drawing replaces this one when it is done, in four to ten minutes. It costs ${cost}.`
    : `It takes four to ten minutes and costs ${cost}.`;
}

/** The line under a shoe's side drawn by Claude: what makes it itself from the side. Null without a side, or when
 * Claude named nothing. */
export function sideLine(drawn: ShoeDrawn | null | undefined): string | null {
  const features = drawn?.side?.features.filter((f) => f.trim()) ?? [];
  if (!features.length) return null;
  const said = features.join('; ');
  return `From the side: ${said.charAt(0).toLowerCase()}${said.slice(1)}.`.replace(/\.\.$/, '.');
}

/** What "The shoe's drawing" in Fix the details says and offers: the traced drawing with its fixes ('trace'), Claude's
 * side drawing, which the trace's fixes do not change ('side'), or the plain drawing the owner chose ('plain'). */
export function shoeFixMode(item: Pick<Item, 'drawn' | 'trace'>): 'trace' | 'side' | 'plain' {
  if (item.trace?.plain) return 'plain';
  return item.drawn?.side_shown ? 'side' : 'trace';
}
export const SIDE_FIX = "The picture is Claude's drawing of the shoe, so the traced colours and marks are not used. To " +
  'change it, write what is wrong under “Drawn by Claude from its photos” and choose the side.';
