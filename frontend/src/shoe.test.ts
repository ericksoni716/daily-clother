import { describe, expect, it } from 'vitest';
import {
  backLabel, canCorrect, changedLine, checkHeadline, dollars, DRAWN_DEMO, drawingShoe, drawnLine, drawnOffer, drawnTime,
  drawQuestion, extraPhotos, FRONT_VIEWS, NOTE_MAX,
  frontPreviewUrl, MAX_EXTRA_PHOTOS, NUDGE_CM, NUDGES, nudgeLabel, outsideQuestion, photoRoom, sortingViews, traceNotice,
  tracing, VIEW_WORDS, viewLabel,
} from './shoe';
import type { Photo, ShoeDrawn, ShoeTrace, ShoeViews } from './types';

const trace = (state: ShoeTrace['state'], message: string | null): ShoeTrace => ({
  state, message, drawn: false, plain: false, fixed: false, parts: [], marks: [],
});

describe('the item page about a shoe trace', () => {
  it('says nothing for anything that is not a shoe, or a shoe traced well', () => {
    expect(traceNotice(null)).toBeNull();
    expect(traceNotice(undefined)).toBeNull();
    expect(traceNotice(trace('done', null))).toBeNull();
  });

  it('says it is being traced, without offering a retake', () => {
    expect(traceNotice(trace('working', 'Drawing the shoe from its photo…'))).toEqual(
      { tone: 'info', text: 'Drawing the shoe from its photo…', retake: false });
    expect(tracing(trace('waiting', 'x'))).toBe(true);
    expect(tracing(trace('working', 'x'))).toBe(true);
    expect(tracing(trace('done', null))).toBe(false);
    expect(tracing(null)).toBe(false);
  });

  it('explains a refused or failed photo and offers to retake it', () => {
    const why = "The photo shows the shoe from the front, so it's drawn from its details instead.";
    expect(traceNotice(trace('refused', why))).toEqual({ tone: 'warn', text: why, retake: true });
    expect(traceNotice(trace('failed', 'It could not be traced.'))?.retake).toBe(true);
  });
});

describe('fixing the marks', () => {
  it('moves a mark half a centimetre each way, in plain words', () => {
    expect(NUDGES.map((n) => n.step)).toEqual([[NUDGE_CM, 0], [0, NUDGE_CM], [0, -NUDGE_CM], [-NUDGE_CM, 0]]);
    expect(NUDGE_CM).toBe(0.5);
    expect(nudgeLabel('stripe', 'toe')).toBe('Move the stripe towards the toe');
    expect(nudgeLabel('logo', 'down')).toBe('Move the logo down');
  });
});

describe("Add's instant check", () => {
  it('heads the answer in one sentence', () => {
    expect(checkHeadline({ ok: true, reasons: [] })).toBe('This photo should trace well.');
    expect(checkHeadline({ ok: false, reasons: ['x'] })).toBe('This photo may not trace well.');
  });
});

describe("a traced shoe's front view on the figure", () => {
  it('offers the two views in plain words, the shape first', () => {
    expect(FRONT_VIEWS.map((v) => v.kind)).toEqual(['shape', 'photo']);
    expect(FRONT_VIEWS.map((v) => v.title)).toEqual(["From the shoe's shape", 'From your photo']);
  });

  it('asks for each preview anew when the item changes', () => {
    const item = { id: 'a b', updated_at: '2026-11-15T06:00:00+00:00' };
    expect(frontPreviewUrl(item, 'shape')).toBe('/api/items/a%20b/trace/front.svg?kind=shape&v=2026-11-15T06%3A00%3A00%2B00%3A00');
    expect(frontPreviewUrl({ ...item, updated_at: 'later' }, 'photo')).toBe('/api/items/a%20b/trace/front.svg?kind=photo&v=later');
  });
});

const photo = (id: string, kind: string, view: Photo['view'] = null, sure: boolean | null = null,
  by: Photo['view_by'] = null): Photo => ({
  id, kind, view, view_sure: sure, view_by: by, url: `/media/${id}.webp`, thumb_url: `/media/${id}-t.webp`,
  cutout_url: null, cutout_thumb_url: null, width: 10, height: 10,
});
const views = (state: ShoeViews['state'], asking: string[] | null = null): ShoeViews => ({ state, message: null, asking });

describe("a shoe's photos sorted into views", () => {
  it('names every view in plain words', () => {
    expect(Object.values(VIEW_WORDS)).toEqual(['outer side', 'inner side', 'from above', 'front', 'back', 'sole', 'other']);
  });

  it('labels each photo with its view, unsure ones with a question mark, and says sorting while they are sorted', () => {
    expect(viewLabel(photo('a', 'front', 'outer', true, 'model'), views('sorted'))).toBe('outer side');
    expect(viewLabel(photo('a', 'front', 'inner', false, 'model'), views('asking'))).toBe('inner side?');
    expect(viewLabel(photo('a', 'detail', 'top', true, 'model'), views('waiting'))).toBe('sorting…');
    expect(viewLabel(photo('a', 'detail', null), views('sorting'))).toBe('sorting…');
    expect(viewLabel(photo('a', 'detail', 'front', true, 'owner'), views('sorting'))).toBe('front');   // the owner's stays
    expect(viewLabel(photo('a', 'detail', null), views(null))).toBeNull();
    expect(viewLabel(photo('a', 'detail', null), views('failed'))).toBeNull();
  });

  it('follows the sorting until it is done', () => {
    expect(sortingViews(views('waiting'))).toBe(true);
    expect(sortingViews(views('sorting'))).toBe(true);
    for (const state of ['asking', 'sorted', 'failed', null] as const) expect(sortingViews(views(state))).toBe(false);
    expect(sortingViews(null)).toBe(false);
  });

  it('has room for five photos besides the main one', () => {
    const item = { photos: [photo('m', 'front'), photo('a', 'detail'), photo('b', 'detail')] };
    expect(extraPhotos(item).map((p) => p.id)).toEqual(['a', 'b']);
    expect(MAX_EXTRA_PHOTOS).toBe(5);
    expect(photoRoom(item)).toBe(3);
    expect(photoRoom({ photos: [photo('m', 'front'), ...'abcde'.split('').map((id) => photo(id, 'detail'))] })).toBe(0);
  });

  it('asks which photo shows the outside, or about the one photo, numbered as in the row', () => {
    const photos = [photo('m', 'front', 'outer', false, 'model'), photo('a', 'detail', 'top', true, 'model'),
      photo('b', 'detail', 'inner', false, 'model')];
    const several = outsideQuestion({ photos, views: views('asking', ['m', 'b']) });
    expect(several?.one).toBe(false);
    expect(several?.photos.map(({ photo: p, n }) => [p.id, n])).toEqual([['m', 1], ['b', 3]]);
    const one = outsideQuestion({ photos, views: views('asking', ['b']) });
    expect(one?.one).toBe(true);
    expect(one?.photos[0].n).toBe(3);
    expect(outsideQuestion({ photos, views: views('sorted', ['m']) })).toBeNull();
    expect(outsideQuestion({ photos, views: views('asking', ['gone']) })).toBeNull();
    expect(outsideQuestion({ photos, views: null })).toBeNull();
  });
});

const drawn = (state: ShoeDrawn['state'], over: Partial<ShoeDrawn> = {}): ShoeDrawn => ({
  state, message: null, url: null, rounds: null, seconds: null, cost_usd: null, route: null, made_at: null,
  photos_changed: false, about_usd: 0.6, correcting: false, note: null, corrected: false, changed: null,
  against_photos: null, has_previous: false, previous_newer: false, ...over,
});
const done = (over: Partial<ShoeDrawn> = {}) => drawn('done', {
  url: '/api/items/x/drawn.svg?v=1', rounds: 2, seconds: 112.4, cost_usd: 0.6149, route: 'plan', ...over,
});

describe('a shoe drawn from its photos', () => {
  it('follows the drawing while it waits and while it is drawn', () => {
    expect(drawingShoe(drawn('waiting'))).toBe(true);
    expect(drawingShoe(drawn('drawing'))).toBe(true);
    for (const state of ['done', 'failed', null] as const) expect(drawingShoe(drawn(state))).toBe(false);
    expect(drawingShoe(null)).toBe(false);
    expect(drawingShoe(undefined)).toBe(false);
  });

  it('says how long it took, how often it was checked and what it costs, by the way it was drawn', () => {
    expect(drawnTime(48.4)).toBe('48 s');
    expect(drawnTime(112.4)).toBe('1 min 52 s');
    expect(drawnTime(60)).toBe('1 min 0 s');
    expect(dollars(0.6149)).toBe('$0.61');
    expect(drawnLine(done())).toBe(
      'Drawn in 1 min 52 s on your Claude plan, checked 2 times against the photos · about $0.61 if drawn on the API key');
    expect(drawnLine(done({ route: 'api', rounds: 1 }))).toBe(
      'Drawn in 1 min 52 s, checked once against the photos · $0.61 on the API key');
    expect(drawnLine(done({ rounds: 0 }))).toContain('not checked against the photos');
    expect(drawnLine(drawn('waiting'))).toBeNull();
    expect(drawnLine(null)).toBeNull();
  });

  it('offers to draw it, draw it again or try again, never while it is drawn or in the demo closet', () => {
    const sorted = views('sorted');
    expect(drawnOffer({ drawn: drawn(null), views: null }, false)).toBe('draw');
    expect(drawnOffer({ drawn: drawn(null), views: sorted }, false)).toBe('draw');
    expect(drawnOffer({ drawn: drawn(null), views: views('waiting') }, false)).toBeNull();   // drawn by itself once sorted
    expect(drawnOffer({ drawn: done(), views: sorted }, false)).toBe('again');
    expect(drawnOffer({ drawn: drawn('failed'), views: sorted }, false)).toBe('retry');
    expect(drawnOffer({ drawn: drawn('failed', { url: '/x' }), views: sorted }, false)).toBe('retry');
    expect(drawnOffer({ drawn: drawn('waiting', { url: '/x' }), views: sorted }, false)).toBeNull();
    expect(drawnOffer({ drawn: drawn('drawing'), views: sorted }, false)).toBeNull();
    expect(drawnOffer({ drawn: done(), views: sorted }, true)).toBeNull();
    expect(drawnOffer({ drawn: null, views: null }, false)).toBeNull();
    expect(DRAWN_DEMO).toContain('never sent to Claude');
  });

  it('asks before drawing, saying it replaces the drawing, takes about two minutes and roughly what it costs', () => {
    const again = drawQuestion(done({ about_usd: 0.61 }), true);
    expect(again).toContain('replaces this one when it is done');
    expect(again).toContain('about two minutes');
    expect(again).toContain('roughly $0.61 on the API key');
    expect(again).toContain('nothing extra on your Claude plan');
    expect(drawQuestion(drawn(null), false)).toContain('roughly $0.60');
    expect(drawQuestion(drawn(null), false)).not.toContain('replaces');
  });
});

describe("the owner's note on a shoe's drawing", () => {
  const note = 'the elastic sides should be wider';
  const corrected = (over: Partial<ShoeDrawn> = {}) => done({
    corrected: true, note, changed: 'The elastic side panels are wider.', has_previous: true, seconds: 41, rounds: 1,
    cost_usd: 0.12, ...over,
  });

  it('follows a correction as it follows a drawing, and offers nothing else meanwhile', () => {
    const working = drawn('correcting', { url: '/x', correcting: true, note, has_previous: true });
    expect(drawingShoe(working)).toBe(true);
    expect(drawingShoe(drawn('waiting', { url: '/x', correcting: true, note }))).toBe(true);
    expect(drawnOffer({ drawn: working, views: views('sorted') }, false)).toBeNull();
    expect(canCorrect(working, false)).toBe(false);
    expect(backLabel(working)).toBeNull();
    expect(changedLine(working)).toBeNull();
  });

  it('offers the note box once there is a drawing, never in the demo closet', () => {
    expect(canCorrect(done(), false)).toBe(true);
    expect(canCorrect(done(), true)).toBe(false);
    expect(canCorrect(drawn(null), false)).toBe(false);
    expect(canCorrect(drawn('failed', { url: '/x' }), false)).toBe(true);   // a redraw failed: the old one can be fixed
    expect(canCorrect(null, false)).toBe(false);
    expect(NOTE_MAX).toBe(200);
  });

  it('says what changed, and the time and cost of the change, by the way it was made', () => {
    expect(changedLine(corrected())).toBe(`Changed as you asked: “${note}”. The elastic side panels are wider.`);
    expect(changedLine(corrected({ changed: null }))).toBe(`Changed as you asked: “${note}”.`);
    expect(changedLine(done())).toBeNull();
    expect(drawnLine(corrected())).toBe(
      'Changed in 41 s on your Claude plan, checked once against the photos · about $0.12 if changed on the API key');
    expect(drawnLine(corrected({ route: 'api' }))).toBe('Changed in 41 s, checked once against the photos · $0.12 on the API key');
  });

  it('swaps back to the drawing before in one tap, and offers the newer one again', () => {
    expect(backLabel(corrected())).toBe('Go back to the drawing before');
    expect(backLabel(done({ has_previous: true, previous_newer: true }))).toBe('Go to the newer drawing');
    expect(backLabel(done())).toBeNull();
    expect(backLabel(drawn('waiting', { url: '/x', has_previous: true }))).toBeNull();
  });
});
