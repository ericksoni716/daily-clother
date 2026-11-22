import { describe, expect, it } from 'vitest';
import {
  backLabel, canCorrect, canSayOutside, changedLine, dollars, DRAWN_DEMO, drawingShoe, drawnLine, drawnOffer, drawnTime,
  drawQuestion, extraPhotos, NOTE_MAX, NO_SIDE, noSidePhoto,
  MAX_EXTRA_PHOTOS, MAX_PHOTOS, noteChoices, NUDGE_CM, NUDGES, nudgeLabel, outsideQuestion, photoRoom, sentAs,
  shoeAddedLine, shoeFixMode, sideChangedLine, sideLine, sideMadeLine, sortingViews, tooManyPhotos, traceNotice, tracing, VIEW_WORDS, viewLabel,
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

  it('leaves a trace being made to the item\'s progress', () => {
    expect(traceNotice(trace('working', 'Tracing the shoe from its photo…'))).toBeNull();
    expect(traceNotice(trace('waiting', 'The shoe will be traced from its photo in a moment.'))).toBeNull();
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

  it('says nothing about the photo once the drawing is Claude\'s side: it is not drawn from its details then', () => {
    expect(traceNotice(trace('refused', 'The photo shows the pair.'), true)).toBeNull();
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

describe('a shoe added in one step', () => {
  it('says plainly when more than six photos were chosen', () => {
    expect(tooManyPhotos(1)).toBe('A shoe can have up to 6 photos, so one photo was not added.');
    expect(tooManyPhotos(3)).toBe('A shoe can have up to 6 photos, so 3 photos were not added.');
  });

  it('says what was added, all of it or part of it', () => {
    expect(shoeAddedLine(1, 1)).toBe('The shoe is added. In a moment Nines removes the background and describes it.');
    expect(shoeAddedLine(4, 4)).toBe(
      'The shoe is added with its 4 photos. In a moment Nines removes the background and works out which photo is which.');
    expect(shoeAddedLine(2, 4)).toBe('The shoe is added with 2 of its 4 photos.');
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
    expect(MAX_PHOTOS).toBe(6);
    expect(photoRoom(item)).toBe(3);
    expect(photoRoom({ photos: [photo('m', 'front'), ...'abcde'.split('').map((id) => photo(id, 'detail'))] })).toBe(0);
  });

  it('says a photo from the side would help only once the photos are sorted and none is a side view', () => {
    const none = [photo('m', 'front', 'top', true, 'model'), photo('a', 'detail', 'front', true, 'model')];
    expect(noSidePhoto({ photos: none, views: views('sorted') })).toBe(true);
    expect(NO_SIDE).toBe('None of these photos shows the shoe from the side. A photo of its side would help the drawing.');
    for (const side of ['outer', 'inner'] as const) {
      expect(noSidePhoto({ photos: [...none, photo('b', 'detail', side, false, 'model')], views: views('sorted') })).toBe(false);
    }
    for (const state of ['waiting', 'sorting', 'asking', 'failed', null] as const) {
      expect(noSidePhoto({ photos: none, views: views(state) })).toBe(false);   // not sorted yet, or never
    }
    expect(noSidePhoto({ photos: none, views: null })).toBe(false);
    expect(noSidePhoto({ photos: [], views: views('sorted') })).toBe(false);
  });

  it('lets you say which photo shows the outside at any time once the photos are sorted', () => {
    // 22 November: only an unsure answer was asked about, so a swap Claude was sure of could not be put right
    const sure = [photo('m', 'front', 'outer', true, 'model'), photo('a', 'detail', 'inner', true, 'model')];
    expect(canSayOutside({ photos: sure, views: views('sorted') })).toBe(true);
    expect(canSayOutside({ photos: sure.slice(0, 1), views: views('sorted') })).toBe(true);
    for (const state of ['waiting', 'sorting', 'asking', 'failed', null] as const) {
      expect(canSayOutside({ photos: sure, views: views(state) })).toBe(false);   // being sorted, asked already, or never sorted
    }
    expect(canSayOutside({ photos: [], views: views('sorted') })).toBe(false);
    expect(canSayOutside({ photos: sure, views: null })).toBe(false);
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
  against_photos: null, has_previous: false, previous_newer: false, side: null, side_shown: false,
  correcting_side: false, side_corrected: false, side_note: null, side_changed: null, side_against_photos: null, ...over,
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

  it('asks before drawing, saying it replaces the drawing, takes four to ten minutes and roughly what it costs', () => {
    const again = drawQuestion(done({ about_usd: 0.61 }), true);
    expect(again).toContain('replaces this one when it is done');
    expect(again).toContain('four to ten minutes');
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

describe("a shoe's side drawn by Claude", () => {
  const side = { url: '/api/items/x/drawn/side.svg?v=1', features: ['Perforated toe box', 'orange mark on the side.'] };

  it('says what makes the shoe itself from the side, in one line', () => {
    expect(sideLine(done({ side }))).toBe('From the side: perforated toe box; orange mark on the side.');
    expect(sideLine(done({ side: { ...side, features: ['', ' '] } }))).toBeNull();
    expect(sideLine(done())).toBeNull();
    expect(sideLine(null)).toBeNull();
  });

  it("offers the trace's fixes only while the trace is the picture", () => {
    const traced = trace('done', null);
    expect(shoeFixMode({ trace: traced, drawn: done() })).toBe('trace');
    expect(shoeFixMode({ trace: traced, drawn: done({ side, side_shown: true }) })).toBe('side');
    expect(shoeFixMode({ trace: { ...traced, plain: true }, drawn: done({ side }) })).toBe('plain');
    expect(shoeFixMode({ trace: traced, drawn: null })).toBe('trace');
  });

  it('offers the choice of the front or the side only once there is a side, the front first', () => {
    expect(noteChoices(done({ side })).map((c) => [c.value, c.label])).toEqual([['front', 'The front'], ['side', 'The side']]);
    expect(noteChoices(done())).toEqual([]);
    expect(noteChoices(null)).toEqual([]);
    expect(sentAs('side')).toBe('Changing the side drawing as you asked');
    expect(sentAs('front')).toBe('Changing the drawing as you asked');
  });

  it('says what changed in the side, with the side, and only when the last change was to it', () => {
    const changedSide = done({
      side: { ...side, rounds: 1, seconds: 37, cost_usd: 0.09, route: 'plan' }, side_corrected: true,
      side_note: 'the heel is taller', side_changed: 'The heel counter is taller.',
      side_against_photos: 'The side photo shows a lower heel; drawn as you asked.',
      corrected: true, note: 'black laces', changed: 'The laces are black.',   // an earlier change to the front
    });
    expect(sideChangedLine(changedSide)).toBe('Changed as you asked: “the heel is taller”. The heel counter is taller.');
    expect(changedLine(changedSide)).toBeNull();   // the line sits with the side, not the front
    expect(drawnLine(changedSide)).toBeNull();   // one line about how the last change went, the side's
    expect(sideMadeLine(changedSide)).toBe(
      'Changed in 37 s on your Claude plan, checked once against the photos · about $0.09 if changed on the API key');
    expect(sideMadeLine(done({ ...changedSide, side: { ...changedSide.side!, route: 'api' } })))
      .toBe('Changed in 37 s, checked once against the photos · $0.09 on the API key');
    // the front changed last: its own line again, none with the side
    const front = done({ ...changedSide, side_corrected: false, side_note: null, side_changed: null });
    expect(sideChangedLine(front)).toBeNull();
    expect(sideMadeLine(front)).toBeNull();
    expect(changedLine(front)).toBe('Changed as you asked: “black laces”. The laces are black.');
    expect(drawnLine(front)).toContain('Changed in 1 min 52 s');
    // while a note waits or is made, neither
    expect(sideChangedLine({ ...changedSide, correcting: true, correcting_side: true, state: 'waiting' })).toBeNull();
    expect(sideChangedLine(done({ side, side_corrected: true, side_note: 'x', side_changed: null })))
      .toBe('Changed as you asked: “x”.');
    expect(sideMadeLine(done({ side, side_corrected: true, side_note: 'x' }))).toBeNull();   // no time kept
  });
});
