import { describe, expect, it } from 'vitest';
import {
  checkHeadline, extraPhotos, FRONT_VIEWS, frontPreviewUrl, MAX_EXTRA_PHOTOS, NUDGE_CM, NUDGES, nudgeLabel, outsideQuestion,
  photoRoom, sortingViews, traceNotice, tracing, VIEW_WORDS, viewLabel,
} from './shoe';
import type { Photo, ShoeTrace, ShoeViews } from './types';

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
