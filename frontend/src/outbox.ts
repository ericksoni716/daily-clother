/**
 * What is kept on this phone while Nines cannot be reached, to be sent when it answers again: the three things done
 * away from the computer. Wearing an outfit (Today's "I'm wearing this"), how a worn outfit went (on Worn and in
 * Today's question) and a tick on a trip's packing list. Nothing else is ever kept here: every other control stays
 * off offline and says why. Why it is this way: docs/DECISIONS.md, "Wearing while the computer is off".
 *
 * An action is kept only when Nines cannot be reached (no answer: the request could not connect or timed out, or
 * the page already knows it is offline). An answer from Nines, even a refusal, is an answer: the screen shows it as
 * before and nothing is kept. Kept actions are sent one at a time, in the order they were made; each call is safe to
 * repeat on the server, so one sent again after its answer was lost is not recorded twice. One that Nines refuses when
 * it finally gets it leaves the list and the owner is told once, in plain words.
 *
 * The list is kept per closet in this browser's storage, under Today's prefix, so it survives a reload and the app
 * being closed and is forgotten with this device's other saved copies. The class is pure apart from what is given to
 * it, so it is tested without a browser; `outboxFor` gives each closet its one list, sending through `api.ts`.
 */
import { api, connection } from './api';
import { SAVED_PREFIX } from './today';
import type { Trip, TripSummary } from './trips';
import { whenWorn } from './wears';
import type { OutfitSent, Rating, Reason, WornOutfit, WornPage } from './worn';

interface Base {
  /** Made on this phone; also names the action in Today's memory of what is worn. */
  id: string;
  /** When the owner tapped (ISO), sent with a wear or a rating sent later. */
  at: string;
  /** Times Nines answered with a fault of its own while it was being sent (it is given up after `MAX_FAULTS`). */
  faults?: number;
}

/** "I'm wearing this": the outfit's wears and the outfit, for the day the owner tapped on this phone. */
export interface WearAction extends Base {
  kind: 'wear';
  day: string;
  item_ids: string[];
  outfit: OutfitSent;
}

/** How it went, as the three answers, the reasons and the note give it. */
export interface RatingValue {
  rating: Rating | null;
  reasons: Reason[];
  note: string | null;
}

/** How a worn outfit went. `before` is what Nines had, so changing it back takes the action out instead. */
export interface RateAction extends Base, RatingValue {
  kind: 'rate';
  outfit_id: string;
  /** The day the outfit was worn, to say which one when Nines refuses it. */
  worn_on: string;
  before: RatingValue;
}

/** A line of a trip's packing list ticked or unticked. `before` is whether Nines had it ticked. */
export interface TickAction extends Base {
  kind: 'tick';
  trip_id: string;
  line: string;
  on: boolean;
  before: boolean;
  /** The piece's name and the trip's place, to say which when Nines refuses it. */
  name: string;
  place: string;
}

export type KeptAction = WearAction | RateAction | TickAction;

/** What is sent for an action: the answer when Nines took it, or that it is kept on this phone. */
export type Sent<T = unknown> = { kept: false; answer: T } | { kept: true };

/** Told to whoever follows the list once an action that was kept has reached Nines, or Nines refused it. */
export type OutboxEvent =
  | { type: 'sent'; action: KeptAction; answer: unknown }
  | { type: 'refused'; action: KeptAction; message: string };

/** After this many faults of Nines' own, an action is given up and the owner told (never an endless retry). */
export const MAX_FAULTS = 3;

/** One kept action per thing it changes: a day's wear, an outfit's rating, a line of a trip. */
export function keyOf(a: KeptAction): string {
  if (a.kind === 'wear') return `wear:${a.day}`;
  if (a.kind === 'rate') return `rate:${a.outfit_id}`;
  return `tick:${a.trip_id}:${a.line}`;
}

const sameRating = (a: RatingValue, b: RatingValue) =>
  a.rating === b.rating && (a.note ?? null) === (b.note ?? null) && a.reasons.length === b.reasons.length && a.reasons.every((r) => b.reasons.includes(r));

/** Whether the action puts back what Nines already has (then there is nothing to send). */
function backToBefore(a: KeptAction): boolean {
  if (a.kind === 'rate') return sameRating(a, a.before);
  if (a.kind === 'tick') return a.on === a.before;
  return false;
}

/**
 * The list with `a` kept: an earlier action on the same thing is replaced (a new rating, a tick taken off, another
 * outfit worn that day), and one that puts back what Nines has leaves the list instead. `sending` is the action on its
 * way to Nines: it can no longer be taken back, so a later one on the same thing is kept after it as it is.
 */
export function withKept(list: KeptAction[], a: KeptAction, sending: string | null = null): KeptAction[] {
  const key = keyOf(a);
  const inFlight = list.find((x) => x.id === sending && keyOf(x) === key);
  if (inFlight) return [...list.filter((x) => x.id === sending || keyOf(x) !== key), a];
  const earlier = list.find((x) => keyOf(x) === key);
  const next = earlier && 'before' in earlier && 'before' in a ? { ...a, before: earlier.before } as KeptAction : a;
  const rest = list.filter((x) => keyOf(x) !== key);
  return backToBefore(next) ? rest : [...rest, next];
}

interface ErrorLike {
  status?: number;
  message?: string;
}

/** A call that Nines did not answer at all: it could not be reached, or the page already knows it is offline. */
export function cannotReach(err: unknown, offline: boolean): boolean {
  return offline || (err as ErrorLike | null)?.status === 0;
}

/**
 * What to do with a kept action whose sending failed: wait (Nines out of reach again, or the door turned this device
 * away, which is not Nines saying no), try again later (a fault of Nines' own, up to `MAX_FAULTS`), or give it up as
 * refused (any other answer).
 */
export function afterFailure(err: unknown, faults: number): 'wait' | 'retry' | 'refused' {
  const s = (err as ErrorLike | null)?.status ?? 0;
  if (s === 0 || s === 401) return 'wait';
  if ((s >= 500 || s === 408 || s === 429) && faults + 1 < MAX_FAULTS) return 'retry';
  return 'refused';
}

/** The one sentence that tells the owner what was not recorded, and why (Nines' own words). */
export function refusedLine(a: KeptAction, why: string, today?: string): string {
  const reason = why.trim() ? ` ${why.trim()}` : '';
  if (a.kind === 'wear') return `The outfit you wore ${whenWorn(a.day, today)} was not recorded.${reason}`;
  if (a.kind === 'rate') return `How the outfit you wore ${whenWorn(a.worn_on, today)} went was not recorded.${reason}`;
  return a.on ? `${a.name} was not ticked as packed for ${a.place}.${reason}` : `${a.name} was not unticked on the list for ${a.place}.${reason}`;
}

/** A page of worn outfits as it shows with the ratings kept on this phone. */
export function withKeptRatings(page: WornPage, list: KeptAction[]): WornPage {
  const rates = list.filter((a): a is RateAction => a.kind === 'rate');
  if (!rates.length || !page.outfits.some((o) => rates.some((r) => r.outfit_id === o.id))) return page;
  return { ...page, outfits: page.outfits.map((o) => keptRating(o, rates)) };
}

function keptRating(o: WornOutfit, rates: RateAction[]): WornOutfit {
  const r = [...rates].reverse().find((x) => x.outfit_id === o.id);
  return r ? { ...o, rating: r.rating, rating_reasons: r.reasons, rating_note: r.note, rated_at: r.rating ? r.at : null } : o;
}

/** A trip as it shows with the ticks kept on this phone. */
export function withKeptTicks(trip: Trip, list: KeptAction[]): Trip {
  const ticks = list.filter((a): a is TickAction => a.kind === 'tick' && a.trip_id === trip.id);
  if (!ticks.length) return trip;
  let packed = trip.packed;
  for (const t of ticks) packed = t.on ? (packed.includes(t.line) ? packed : [...packed, t.line]) : packed.filter((x) => x !== t.line);
  return { ...trip, packed };
}

/** The list of trips, each counting the ticks kept on this phone. */
export function withKeptCounts(trips: TripSummary[], list: KeptAction[]): TripSummary[] {
  const ticks = list.filter((a): a is TickAction => a.kind === 'tick');
  if (!ticks.length) return trips;
  return trips.map((t) => {
    const change = ticks.filter((x) => x.trip_id === t.id).reduce((n, x) => n + (x.on === x.before ? 0 : x.on ? 1 : -1), 0);
    return change ? { ...t, packed: Math.max(0, Math.min(t.lines, t.packed + change)) } : t;
  });
}

type KV = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

export interface OutboxDeps {
  /** Sends one action; `late` when it was kept and is sent now (a wear or a rating then carries when it was tapped). */
  send(a: KeptAction, late: boolean): Promise<unknown>;
  /** Whether the page already knows Nines cannot be reached. */
  offline(): boolean;
  /** Before sending what was kept: whether Nines answers for this closet (another device may have switched it). */
  ready?(): Promise<boolean>;
  /** Where the list is kept, and under which key; none keeps it in memory only. */
  kv?: KV | null;
  key?: string;
}

/** Only these fields are kept: the action and nothing else (DECISIONS: what the list holds). */
function valid(a: unknown): a is KeptAction {
  const x = a as KeptAction | null;
  return !!x && typeof x.id === 'string' && typeof x.at === 'string' && (x.kind === 'wear' || x.kind === 'rate' || x.kind === 'tick');
}

export class Outbox {
  private raw: string | null = null;
  private cached: KeptAction[] = [];
  private listeners = new Set<(list: KeptAction[]) => void>();
  private events = new Set<(e: OutboxEvent) => void>();
  private running: Promise<void> | null = null;
  private sending: string | null = null;
  private memory: KeptAction[] = [];

  constructor(private deps: OutboxDeps) {}

  /** What is kept, oldest first. Read from storage each time, so a list forgotten there is forgotten here too. */
  get list(): KeptAction[] {
    const { kv, key } = this.deps;
    if (!kv || !key) return this.memory;
    let raw: string | null;
    try {
      raw = kv.getItem(key);
    } catch {
      raw = null;
    }
    if (raw !== this.raw) {
      this.raw = raw;
      try {
        const parsed = raw ? JSON.parse(raw) as { actions?: unknown } : null;
        this.cached = Array.isArray(parsed?.actions) ? parsed.actions.filter(valid) : [];
      } catch {
        this.cached = [];
      }
    }
    return this.cached;
  }

  has(id: string): boolean {
    return this.list.some((a) => a.id === id);
  }

  subscribe(l: (list: KeptAction[]) => void): () => void {
    this.listeners.add(l);
    return () => void this.listeners.delete(l);
  }

  /** Told when a kept action reaches Nines or is refused, before it leaves the list. */
  onEvent(l: (e: OutboxEvent) => void): () => void {
    this.events.add(l);
    return () => void this.events.delete(l);
  }

  /**
   * Sends an action now, or keeps it when Nines cannot be reached. Anything kept already goes first, so the order
   * stays the order of the taps. A refusal from Nines is thrown, as a call made directly would be.
   */
  async send<T>(a: KeptAction): Promise<Sent<T>> {
    if (this.list.length && !this.deps.offline()) await this.flush();
    if (this.list.length || this.deps.offline()) {
      this.keep(a);
      return { kept: true };
    }
    try {
      return { kept: false, answer: await this.deps.send(a, false) as T };
    } catch (e) {
      if (!cannotReach(e, this.deps.offline())) throw e;
      this.keep(a);
      return { kept: true };
    }
  }

  /** Keeps an action (see `withKept`). */
  keep(a: KeptAction): void {
    this.write(withKept(this.list, a, this.sending));
  }

  /** Takes a kept action back before it is sent (a wear taken back). False when it is not kept (any more). */
  drop(id: string): boolean {
    if (id === this.sending || !this.has(id)) return false;
    this.write(this.list.filter((a) => a.id !== id));
    return true;
  }

  /** Forgets everything kept (this device's saved copies forgotten). */
  clear(): void {
    this.write([]);
  }

  /** Resolves once nothing is being sent. */
  async idle(): Promise<void> {
    await this.running;
  }

  /** Sends what is kept, in order, one at a time; stops at the first that cannot reach Nines. One run at a time. */
  flush(): Promise<void> {
    if (this.running) return this.running;
    if (!this.list.length) return Promise.resolve();
    this.running = this.run().finally(() => {
      this.running = null;
      this.sending = null;
    });
    return this.running;
  }

  private async run(): Promise<void> {
    if (this.deps.ready && !(await this.deps.ready().catch(() => false))) return;
    for (;;) {
      const a = this.list[0];
      if (!a) return;
      this.sending = a.id;
      try {
        const answer = await this.deps.send(a, true);
        this.sending = null;
        this.tell({ type: 'sent', action: a, answer });
        this.write(this.list.filter((x) => x.id !== a.id));
      } catch (e) {
        this.sending = null;
        const next = afterFailure(e, a.faults ?? 0);
        if (next === 'wait') return;
        if (next === 'retry') {
          this.write(this.list.map((x) => (x.id === a.id ? { ...x, faults: (x.faults ?? 0) + 1 } : x)));
          return;
        }
        this.tell({ type: 'refused', action: a, message: (e as ErrorLike)?.message ?? '' });
        this.write(this.list.filter((x) => x.id !== a.id));
      }
    }
  }

  private tell(e: OutboxEvent) {
    for (const l of this.events) {
      try {
        l(e);
      } catch {
        /* one listener failing does not stop the list */
      }
    }
  }

  private write(list: KeptAction[]) {
    const { kv, key } = this.deps;
    if (!kv || !key) this.memory = list;
    else {
      try {
        if (list.length) kv.setItem(key, JSON.stringify({ actions: list }));
        else kv.removeItem(key);
      } catch {
        /* private mode or full: kept for as long as the page is open */
        this.memory = list;
      }
    }
    const now = this.list;
    for (const l of this.listeners) l(now);
  }
}

// --------------------------------------------------------------------- the list of each closet

/** Under Today's prefix, so it is forgotten with this device's other saved copies (`clearSavedData`). */
export const outboxKey = (profile: string) => `${SAVED_PREFIX}:outbox:${profile}`;

function local(): KV | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function newActionId(): string {
  return typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID() : `k${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
}

/** The call each action is, as the page makes it when Nines answers. */
function sendAction(a: KeptAction, late: boolean): Promise<unknown> {
  if (a.kind === 'wear') return api.wearMany(a.item_ids, a.outfit, { worn_on: a.day, tapped_at: late ? a.at : undefined });
  if (a.kind === 'rate') return api.rateOutfit(a.outfit_id, a.rating, a.reasons, a.note, late ? a.at : undefined);
  return api.patchTrip(a.trip_id, { ticks: { [a.line]: a.on } });
}

const boxes = new Map<string, Outbox>();

/** The list of this closet (`main` or `demo`); one for the page. */
export function outboxFor(profile: string): Outbox {
  let box = boxes.get(profile);
  if (!box) {
    box = new Outbox({
      send: sendAction,
      offline: () => connection.offline,
      ready: async () => (await api.session()).profile === profile,
      kv: local(),
      key: outboxKey(profile),
    });
    boxes.set(profile, box);
  }
  return box;
}
