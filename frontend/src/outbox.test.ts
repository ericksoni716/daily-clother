import { describe, expect, it } from 'vitest';
import {
  afterFailure, cannotReach, keyOf, MAX_FAULTS, Outbox, outboxKey, refusedLine, withKept, withKeptCounts, withKeptRatings, withKeptTicks,
  type KeptAction, type OutboxDeps, type OutboxEvent, type RateAction, type TickAction, type WearAction,
} from './outbox';
import { forgetSaved } from './today';
import type { Trip, TripSummary } from './trips';
import type { WornOutfit, WornPage } from './worn';

/** A stand-in for this browser's storage, as `localStorage` behaves. */
function memoryStorage() {
  const map = new Map<string, string>();
  return {
    map,
    get length() { return map.size; },
    key: (i: number) => [...map.keys()][i] ?? null,
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => void map.set(k, v),
    removeItem: (k: string) => void map.delete(k),
  };
}

const unreachable = Object.assign(new Error("Can't reach Nines."), { status: 0 });
const refusal = (message: string, status = 409) => Object.assign(new Error(message), { status });

let n = 0;
const wear = (day = '2026-11-23', extra: Partial<WearAction> = {}): WearAction => ({
  kind: 'wear', id: `w${++n}`, at: `${day}T08:15:00.000Z`, day, item_ids: ['a', 'b', 'c'],
  outfit: { pieces: { base: 'a', bottom: 'b', shoes: 'c', mid: null, outer: null, accessories: [] }, context: {}, score: 70, reasons: [], warnings: [] },
  ...extra,
});
const rate = (outfit: string, rating: RateAction['rating'], before: RateAction['rating'] = null): RateAction => ({
  kind: 'rate', id: `r${++n}`, at: '2026-11-23T08:20:00.000Z', outfit_id: outfit, worn_on: '2026-11-22', rating, reasons: [], note: null,
  before: { rating: before, reasons: [], note: null },
});
const tick = (line: string, on: boolean, before = !on, trip = 't1'): TickAction => ({
  kind: 'tick', id: `k${++n}`, at: '2026-11-23T08:30:00.000Z', trip_id: trip, line, on, before, name: 'Navy polo', place: 'Harbour Town',
});

/** An outbox over a stand-in storage, sending through `send`, with what it told kept in `events`. */
function makeBox(send: OutboxDeps['send'], extra: Partial<OutboxDeps> & { offline?: () => boolean } = {}) {
  const kv = extra.kv === undefined ? memoryStorage() : extra.kv;
  const events: OutboxEvent[] = [];
  const sent: { id: string; late: boolean }[] = [];
  const box = new Outbox({
    offline: () => false, kv, key: outboxKey('main'), ...extra,
    send: async (a, late) => {
      sent.push({ id: a.id, late });
      return send(a, late);
    },
  });
  box.onEvent((e) => events.push(e));
  return { box, kv, events, sent };
}

describe('keeping an action', () => {
  it('sends at once when Nines answers, and keeps nothing', async () => {
    const { box, sent } = makeBox(async () => ({ ok: true }));
    const a = wear();
    expect(await box.send(a)).toEqual({ kept: false, answer: { ok: true } });
    expect(box.list).toEqual([]);
    expect(sent).toEqual([{ id: a.id, late: false }]);
  });

  it('keeps an action Nines cannot be reached for, and one made while the page knows it is offline', async () => {
    const { box, sent } = makeBox(async () => { throw unreachable; });
    const a = wear('2026-11-23');
    expect(await box.send(a)).toEqual({ kept: true });
    expect(box.list.map((x) => x.id)).toEqual([a.id]);

    let offline = true;
    const quiet = makeBox(async () => ({}), { offline: () => offline });
    const b = rate('o1', 'loved');
    expect(await quiet.box.send(b)).toEqual({ kept: true });
    expect(quiet.sent).toEqual([]);   // not even tried
    offline = false;
    expect(sent.length).toBe(1);
  });

  it('an answer from Nines, even a refusal, is an answer: it is thrown and nothing is kept', async () => {
    const { box } = makeBox(async () => { throw refusal('That outfit is not in your list of worn outfits.', 404); });
    await expect(box.send(rate('gone', 'fine'))).rejects.toThrow('not in your list');
    expect(box.list).toEqual([]);
    const fault = makeBox(async () => { throw refusal('Something went wrong on the computer running Nines.', 500); });
    await expect(fault.box.send(tick('basic:socks', true))).rejects.toThrow('Something went wrong');
    expect(fault.box.list).toEqual([]);
  });

  it('says what counts as Nines not being reached', () => {
    expect(cannotReach({ status: 0 }, false)).toBe(true);
    expect(cannotReach({ status: 409 }, true)).toBe(true);   // the page already knows
    for (const status of [400, 401, 404, 409, 422, 500, 503]) expect(cannotReach({ status }, false)).toBe(false);
  });
});

describe('the list of what is kept', () => {
  it('keeps one action per thing it changes, in the order of the taps', () => {
    const a = tick('item:1', true);
    const b = rate('o1', 'fine');
    const c = tick('item:2', true);
    let list = [a, b, c].reduce<KeptAction[]>((l, x) => withKept(l, x), []);
    expect(list.map(keyOf)).toEqual(['tick:t1:item:1', 'rate:o1', 'tick:t1:item:2']);
    // the rating changed: the new one replaces it, at the end, still against what Nines had
    const b2 = rate('o1', 'loved', 'fine');
    list = withKept(list, b2);
    expect(list.map((x) => x.id)).toEqual([a.id, c.id, b2.id]);
    expect((list[2] as RateAction).before.rating).toBeNull();
  });

  it('an undo before sending simply takes the action out: untick, a rating put back, the same tick twice', () => {
    let list = withKept([], tick('item:1', true, false));
    list = withKept(list, tick('item:1', false, true));
    expect(list).toEqual([]);
    list = withKept([], rate('o1', 'loved', 'fine'));
    list = withKept(list, rate('o1', 'fine', 'loved'));
    expect(list).toEqual([]);
    // another outfit worn the same day replaces the first; a wear on another day is kept beside it
    const first = wear('2026-11-23');
    const second = wear('2026-11-23');
    list = withKept(withKept([wear('2026-11-22')], first), second);
    expect(list.map((x) => x.id)).not.toContain(first.id);
    expect(list).toHaveLength(2);
  });

  it('never takes back the action on its way to Nines: what changes it is kept after it', () => {
    const on = tick('item:1', true, false);
    const off = tick('item:1', false, true);
    expect(withKept([on], off, on.id).map((x) => x.id)).toEqual([on.id, off.id]);
  });

  it('survives a reload: the list is read back from storage, per closet', async () => {
    const kv = memoryStorage();
    const first = makeBox(async () => { throw unreachable; }, { kv });
    const a = wear();
    await first.box.send(a);
    const again = new Outbox({ send: async () => ({}), offline: () => true, kv, key: outboxKey('main') });
    expect(again.list.map((x) => x.id)).toEqual([a.id]);
    const demo = new Outbox({ send: async () => ({}), offline: () => true, kv, key: outboxKey('demo') });
    expect(demo.list).toEqual([]);
    expect([...kv.map.keys()]).toEqual(['closet-today-saved:outbox:main']);
  });

  it("is forgotten with this device's other saved copies", async () => {
    const kv = memoryStorage();
    const { box } = makeBox(async () => { throw unreachable; }, { kv });
    await box.send(wear());
    await box.send(tick('item:1', true));
    forgetSaved(kv);
    expect(box.list).toEqual([]);
    expect(kv.map.size).toBe(0);
  });

  it('keeps only the actions themselves when what is stored is not a list of them', () => {
    const kv = memoryStorage();
    kv.setItem(outboxKey('main'), JSON.stringify({ actions: [{ kind: 'laundry', id: 'x', at: 'y' }, wear()] }));
    const box = new Outbox({ send: async () => ({}), offline: () => true, kv, key: outboxKey('main') });
    expect(box.list.map((x) => x.kind)).toEqual(['wear']);
    kv.setItem(outboxKey('main'), 'not json');
    expect(box.list).toEqual([]);
  });

  it('a wear taken back before it is sent leaves the list', async () => {
    const { box } = makeBox(async () => { throw unreachable; });
    const a = wear();
    await box.send(a);
    expect(box.drop(a.id)).toBe(true);
    expect(box.drop(a.id)).toBe(false);
    expect(box.list).toEqual([]);
  });
});

describe('sending what was kept', () => {
  it('sends in order, once each, as sent later, and tells each one sent', async () => {
    let reachable = false;
    const { box, sent, events } = makeBox(async (a) => {
      if (!reachable) throw unreachable;
      return { id: a.id };
    });
    const a = wear();
    const b = rate('o1', 'loved');
    const c = tick('item:1', true);
    for (const x of [a, b, c]) await box.send(x);
    expect(box.list).toHaveLength(3);
    reachable = true;
    sent.length = 0;
    await Promise.all([box.flush(), box.flush()]);   // two reasons to send at once: one run
    expect(sent).toEqual([a, b, c].map((x) => ({ id: x.id, late: true })));
    expect(events.map((e) => e.type === 'sent' && e.action.id)).toEqual([a.id, b.id, c.id]);
    expect(box.list).toEqual([]);
    await box.flush();
    expect(sent).toHaveLength(3);
  });

  it('what is kept goes before a new action, so the order stays that of the taps', async () => {
    let reachable = false;
    const { box, sent } = makeBox(async () => {
      if (!reachable) throw unreachable;
      return {};
    });
    const a = tick('item:1', true);
    await box.send(a);
    reachable = true;
    sent.length = 0;
    const b = tick('item:2', true);
    expect(await box.send(b)).toEqual({ kept: false, answer: {} });
    expect(sent).toEqual([{ id: a.id, late: true }, { id: b.id, late: false }]);
  });

  it('stops at the first that cannot reach Nines and keeps the rest, then carries on from there', async () => {
    let calls = 0;
    const { box, sent } = makeBox(async () => {
      calls++;
      if (calls === 2 || calls <= 0) throw unreachable;
      return {};
    }, { offline: () => false });
    calls = -100;
    const a = wear();
    const b = rate('o1', 'loved');
    await box.send(a);
    await box.send(b);
    calls = 0;
    sent.length = 0;
    await box.flush();   // a goes, b's answer is lost
    expect(box.list.map((x) => x.id)).toEqual([b.id]);
    await box.flush();   // b again, the server takes the same rating twice as one
    expect(box.list).toEqual([]);
    expect(sent.map((x) => x.id)).toEqual([a.id, b.id, b.id]);
  });

  it('a refusal on the way is told once, in plain words, and the action leaves the list; the next ones still go', async () => {
    let reachable = false;
    const { box, events } = makeBox(async (a) => {
      if (!reachable) throw unreachable;
      if (a.kind === 'wear') throw refusal('Another outfit was recorded for that day in the meantime.');
      return {};
    });
    const a = wear('2026-11-22');
    const b = tick('item:1', true);
    await box.send(a);
    await box.send(b);
    reachable = true;
    await box.flush();
    expect(events.map((e) => e.type)).toEqual(['refused', 'sent']);
    const told = events[0] as Extract<OutboxEvent, { type: 'refused' }>;
    expect(refusedLine(told.action, told.message, '2026-11-23'))
      .toBe('The outfit you wore yesterday was not recorded. Another outfit was recorded for that day in the meantime.');
    expect(box.list).toEqual([]);
    await box.flush();
    expect(events).toHaveLength(2);
  });

  it("a fault of Nines' own is tried again a few times, then given up and told; never endlessly", async () => {
    let reachable = false;
    const { box, events, sent } = makeBox(async () => {
      if (!reachable) throw unreachable;
      throw refusal('Something went wrong on the computer running Nines. Try again in a moment.', 500);
    });
    await box.send(rate('o1', 'loved'));
    reachable = true;
    sent.length = 0;
    for (let i = 0; i < MAX_FAULTS + 2; i++) await box.flush();
    expect(sent).toHaveLength(MAX_FAULTS);
    expect(events.map((e) => e.type)).toEqual(['refused']);
    expect(box.list).toEqual([]);
  });

  it('waits when the door turns this device away, or Nines answers for the other closet', async () => {
    expect(afterFailure({ status: 401 }, 0)).toBe('wait');
    expect(afterFailure({ status: 0 }, 5)).toBe('wait');
    expect(afterFailure({ status: 503 }, 0)).toBe('retry');
    expect(afterFailure({ status: 503 }, MAX_FAULTS - 1)).toBe('refused');
    expect(afterFailure({ status: 404 }, 0)).toBe('refused');
    let closet = 'demo';
    const { box, sent } = makeBox(async () => ({}), { ready: async () => closet === 'main', offline: () => false });
    box.keep(wear());
    await box.flush();
    expect(sent).toEqual([]);
    closet = 'main';
    await box.flush();
    expect(sent).toHaveLength(1);
  });

  it('a wear taken back while it is on its way is not taken back (it went)', async () => {
    let release: () => void = () => undefined;
    const { box } = makeBox(() => new Promise((done) => { release = () => done({}); }));
    const a = wear();
    box.keep(a);
    const going = box.flush();
    await Promise.resolve();
    expect(box.drop(a.id)).toBe(false);
    release();
    await going;
    expect(box.list).toEqual([]);
  });
});

describe('what the screens show', () => {
  const outfit = (id: string, rating: WornOutfit['rating'] = null) => ({ id, worn_on: '2026-11-22', rating, rating_reasons: [], rating_note: null, rated_at: null }) as unknown as WornOutfit;

  it('a page of worn outfits shows the ratings kept on this phone, the last one for each', () => {
    const page: WornPage = { outfits: [outfit('o1'), outfit('o2', 'fine')], next: null };
    expect(withKeptRatings(page, [])).toBe(page);
    const shown = withKeptRatings(page, [rate('o2', 'not_again', 'fine'), rate('o1', 'fine'), rate('o1', 'loved')]);
    expect(shown.outfits.map((o) => o.rating)).toEqual(['loved', 'not_again']);
    expect(shown.outfits[0].rated_at).toBe('2026-11-23T08:20:00.000Z');
  });

  it('a trip shows the ticks kept on this phone, and the list of trips counts them', () => {
    const trip = { id: 't1', packed: ['item:1'] } as Trip;
    expect(withKeptTicks(trip, [tick('item:1', false, true), tick('item:2', true), tick('item:3', true, false, 't2')]).packed).toEqual(['item:2']);
    const list = [{ id: 't1', packed: 1, lines: 4 }, { id: 't2', packed: 0, lines: 2 }] as TripSummary[];
    expect(withKeptCounts(list, [tick('item:2', true), tick('item:3', true, false, 't2')]).map((t) => t.packed)).toEqual([2, 1]);
  });

  it('says what was not recorded, for each kind', () => {
    expect(refusedLine(rate('o1', 'loved'), 'That outfit is not in your list of worn outfits.', '2026-11-23'))
      .toBe('How the outfit you wore yesterday went was not recorded. That outfit is not in your list of worn outfits.');
    expect(refusedLine(tick('item:1', true), "That line is not in this trip's plan any more.", '2026-11-23'))
      .toBe("Navy polo was not ticked as packed for Harbour Town. That line is not in this trip's plan any more.");
    expect(refusedLine(tick('item:1', false), '', '2026-11-23')).toBe('Navy polo was not unticked on the list for Harbour Town.');
  });
});
