import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { api, ApiError, connection } from '../api';
import { ChevronLeftIcon, HangerIcon, MoreIcon, SuitcaseIcon, WarnIcon } from '../components/Icons';
import { loadGridView, type GridView } from '../drawing';
import { label } from '../labels';
import { Link, navigate } from '../router';
import { useCloset } from '../store';
import { longDate, occasionLabel, OCCASIONS, placeLabel, shortPlace, wornOrder, type Outfit } from '../today';
import {
  addDays, basicLine, checkDates, dateRange, dayRain, dayTemps, groupPacked, itemLine, progress, shortDay, sourceRuns, tripDays,
  loadSavedTrips, saveTrips, tripTitle, upcomingFirst, wornWords, type PlannedTrip, type Trip, type TripDay, type TripPatch,
  type TripRequest, type TripSummary,
} from '../trips';
import type { ItemSummary, Place } from '../types';
import { localDay } from '../wears';
import { TilePicture } from './Closet';
import './Today.css';
import './Trips.css';

const OFFLINE_TITLE = 'Needs Closet on your computer to be reachable';

export function TripsScreen({ tripId }: { tripId: string | null }) {
  const { items, loadItems } = useCloset();
  useEffect(() => {
    if (items.active === null) void loadItems('active');
  }, [items.active, loadItems]);
  if (tripId === 'new') return <PlanTrip />;
  if (tripId) return <SavedTrip key={tripId} id={tripId} />;
  return <TripList />;
}

function useItems() {
  const { items } = useCloset();
  return useMemo(() => new Map((items.active ?? []).map((i) => [i.id, i])), [items.active]);
}

function useTripItems() {
  const { items, loadItems } = useCloset();
  useEffect(() => {
    if (items.archived === null) void loadItems('archived');
  }, [items.archived, loadItems]);
  return useMemo(() => new Map([...(items.active ?? []), ...(items.archived ?? [])].map((i) => [i.id, i])),
    [items.active, items.archived]);
}

function itemName(item: ItemSummary | undefined): string {
  if (!item) return 'no longer in your closet';
  return item.name || label('category', item.category) || 'An item';
}

function keepTrip(profile: string, trip: Trip) {
  const saved = loadSavedTrips(profile);
  const summary: TripSummary = {
    id: trip.id, place: trip.place, first_day: trip.first_day, last_day: trip.last_day, occasion: trip.occasion,
    can_wash: trip.can_wash, lines: trip.lines.length, packed: trip.packed.length,
    uncovered: trip.plan.uncovered.length, warnings: trip.plan.warnings?.length ?? 0, past: trip.last_day < localDay(),
  };
  const list = saved?.list?.some((t) => t.id === trip.id)
    ? saved.list.map((t) => t.id === trip.id ? { ...t, ...summary } : t)
    : [...(saved?.list ?? []), summary];
  saveTrips(profile, { list, details: { ...(saved?.details ?? {}), [trip.id]: trip } });
}

function forgetTrip(profile: string, id: string) {
  const saved = loadSavedTrips(profile);
  if (!saved) return;
  const details = { ...saved.details };
  delete details[id];
  saveTrips(profile, { list: saved.list?.filter((t) => t.id !== id) ?? null, details });
}

function BackToTrips() {
  return (
    <div className="detail-top">
      <Link to="/trips" className="btn btn-ghost back-link"><ChevronLeftIcon /> Trips</Link>
    </div>
  );
}

// ------------------------------------------------------------------ the list

function TripList() {
  const { offline, profile } = useCloset();
  const [trips, setTrips] = useState<TripSummary[] | null>(() => loadSavedTrips(profile)?.list ?? null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    api.trips().then(
      (t) => {
        if (!current) return;
        setTrips(t);
        setError(null);
        if (!connection.offline) saveTrips(profile, { list: t });
      },
      (e) => {
        if (!current) return;
        const saved = loadSavedTrips(profile)?.list;
        if ((e as ApiError).status === 0 && saved) {
          setTrips(saved);
          setError(null);
        }
        else setError((e as ApiError).status === 0
          ? "You're offline, and the list of trips was not saved on this device. It shows here once Closet on your computer can be reached."
          : (e as Error).message);
      },
    );
    return () => {
      current = false;
    };
  }, [offline, profile]);

  const planButton = offline
    ? <span className="btn btn-primary is-disabled" aria-disabled="true" title={OFFLINE_TITLE}>Plan a trip</span>
    : <Link to="/trips/new" className="btn btn-primary">Plan a trip</Link>;

  const { upcoming, past } = upcomingFirst(trips ?? []);
  return (
    <div className="trips">
      <header className="page-header">
        <div className="page-title-row"><h1 id="trips-title">Trips</h1></div>
        {trips && trips.length > 0 && planButton}
      </header>
      <p className="hint trips-intro">Closet says what to pack: the fewest pieces from your closet that dress every day of a trip, for the weather there.</p>
      {error && <p className={trips ? 'form-error' : 'notice'} role="alert">{error}</p>}
      {!trips && !error && <p className="muted"><span className="spinner" aria-hidden="true" /> Loading your trips…</p>}
      {trips && trips.length === 0 && (
        <div className="empty empty-big">
          <div className="empty-art"><SuitcaseIcon /></div>
          <p className="empty-title">No trips yet</p>
          <p className="muted">Choose where you're going and when, and Closet works out what to take.</p>
          {planButton}
        </div>
      )}
      {upcoming.length > 0 && <TripCards title="Coming up" trips={upcoming} />}
      {past.length > 0 && <TripCards title="Past trips" trips={past} />}
    </div>
  );
}

function TripCards({ title, trips }: { title: string; trips: TripSummary[] }) {
  return (
    <section className="trips-section" aria-label={title}>
      <h2 className="chip-group-title">{title}</h2>
      <ul className="trip-cards">
        {trips.map((t) => {
          const done = t.packed === t.lines && t.lines > 0;
          return (
            <li key={t.id}>
              <Link to={`/trips/${encodeURIComponent(t.id)}`} className={`trip-card${t.past ? ' is-past' : ''}`} data-testid="trip-card">
                <span className="trip-card-icon"><SuitcaseIcon /></span>
                <span className="trip-card-text">
                  <strong>{tripTitle(t)}</strong>
                  <span className="muted">
                    {occasionLabel(t.occasion)} · {done ? `All ${t.lines} packed` : `${t.packed} of ${t.lines} packed`}
                    {t.uncovered > 0 && <> · <span className="trip-card-warn">{t.uncovered === 1 ? '1 day without an outfit' : `${t.uncovered} days without an outfit`}</span></>}
                    {t.warnings > 0 && <> · <span className="trip-card-warn">{t.warnings === 1 ? '1 day dressed with a warning' : `${t.warnings} days dressed with warnings`}</span></>}
                  </span>
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// ------------------------------------------------------------------ planning a new trip

interface Draft {
  place: Place | null;
  first: string;
  last: string;
  occasion: string;
  differ: Record<string, string>;
  canWash: boolean;
}

function requestOf(d: Draft, leaveOut: string[], pin: string[]): TripRequest | null {
  if (!d.place) return null;
  const days = new Set(tripDays(d.first, d.last));
  const differ = Object.fromEntries(Object.entries(d.differ).filter(([day, occ]) => days.has(day) && occ !== d.occasion));
  return { place: d.place, first_day: d.first, last_day: d.last, occasion: d.occasion, day_occasions: differ, can_wash: d.canWash,
    leave_out: leaveOut, pin };
}

function PlanTrip() {
  const { offline, toast } = useCloset();
  const byId = useItems();
  const today = localDay();
  const [draft, setDraft] = useState<Draft>({ place: null, first: addDays(today, 7), last: addDays(today, 11), occasion: 'casual', differ: {}, canWash: false });
  const [leaveOut, setLeaveOut] = useState<string[]>([]);
  const [pin, setPin] = useState<string[]>([]);
  const [planned, setPlanned] = useState<PlannedTrip | null>(null);
  const [asking, setAsking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ctrl = useRef<AbortController | null>(null);

  const ask = useCallback(async (d: Draft, out: string[], take: string[]) => {
    const problem = d.place ? checkDates(d.first, d.last, localDay()) : 'Choose where the trip is.';
    if (problem) return setError(problem);
    ctrl.current?.abort();
    const c = new AbortController();
    ctrl.current = c;
    setAsking(true);
    setError(null);
    try {
      setPlanned(await api.planTrip(requestOf(d, out, take)!, c.signal));
      setLeaveOut(out);
      setPin(take);
    } catch (e) {
      if ((e as Error)?.name === 'AbortError') return;
      setError((e as Error).message);
    } finally {
      if (ctrl.current === c) setAsking(false);
    }
  }, []);

  useEffect(() => () => ctrl.current?.abort(), []);

  function submit(e: FormEvent) {
    e.preventDefault();
    void ask(draft, leaveOut, pin);
  }

  async function save() {
    const req = requestOf(draft, leaveOut, pin);
    if (!req) return;
    setSaving(true);
    try {
      const trip = await api.saveTrip(req);
      toast('Trip saved');
      navigate(`/trips/${encodeURIComponent(trip.id)}`, { replace: true });
    } catch (e) {
      toast((e as Error).message, 'error');
      setSaving(false);
    }
  }

  const changes: Changes = {
    locked: offline || asking,
    leaveOut, pin,
    swap: (id) => void ask(draft, [...leaveOut.filter((x) => x !== id), id], pin.filter((x) => x !== id)),
    unswap: (id) => void ask(draft, leaveOut.filter((x) => x !== id), pin),
    pinIn: (id) => void ask(draft, leaveOut.filter((x) => x !== id), [...pin.filter((x) => x !== id), id]),
    unpin: (id) => void ask(draft, leaveOut, pin.filter((x) => x !== id)),
  };

  return (
    <div className="trips trip-planning" aria-busy={asking}>
      <BackToTrips />
      <header className="page-header"><h1 id="trips-title">Plan a trip</h1></header>
      {offline && <p className="notice" role="status">You're offline. Planning a trip needs Closet on your computer to be reachable.</p>}
      <TripForm draft={draft} setDraft={(d) => { setDraft(d); setPlanned(null); }} today={today} locked={offline} asking={asking} onSubmit={submit} />
      {error && <p className="form-error" role="alert">{error}</p>}
      {planned && (
        <>
          <PlanView trip={planned} byId={byId} changes={changes} asking={asking} />
          <div className="trip-save">
            <button className="btn btn-primary btn-block trip-big-button" disabled={offline || asking || saving} title={offline ? OFFLINE_TITLE : undefined}
              onClick={() => void save()}>{saving ? 'Saving…' : 'Save this trip'}</button>
            <p className="hint">Saved trips can be ticked off as you pack, on this device or your phone.</p>
          </div>
        </>
      )}
    </div>
  );
}

function TripForm({ draft, setDraft, today, locked, asking, onSubmit }: {
  draft: Draft; setDraft(d: Draft): void; today: string; locked: boolean; asking: boolean; onSubmit(e: FormEvent): void;
}) {
  const days = tripDays(draft.first, draft.last);
  const differing = Object.entries(draft.differ).filter(([d, o]) => days.includes(d) && o !== draft.occasion).length;
  return (
    <section className="trip-form" aria-label="The trip">
      <PlacePicker place={draft.place} locked={locked} onChoose={(place) => setDraft({ ...draft, place })} />
      <form onSubmit={onSubmit} noValidate>
        <div className="trip-dates">
          <label className="field">
            <span>First day</span>
            <input type="date" value={draft.first} min={today} disabled={locked}
              onChange={(e) => {
                const first = e.target.value;
                const last = draft.last < first ? first : draft.last;
                setDraft({ ...draft, first, last });
              }} />
          </label>
          <label className="field">
            <span>Last day</span>
            <input type="date" value={draft.last} min={draft.first || today} disabled={locked} onChange={(e) => setDraft({ ...draft, last: e.target.value })} />
          </label>
        </div>
        <div className="today-choice trip-occasion" role="group" aria-label="Occasion">
          <span className="chip-group-title" aria-hidden="true">Occasion</span>
          <div className="chips chips-scroll">
            {OCCASIONS.map((o) => (
              <button key={o} type="button" className={`chip${draft.occasion === o ? ' is-on' : ''}`} aria-pressed={draft.occasion === o}
                disabled={locked} onClick={() => setDraft({ ...draft, occasion: o })}>{occasionLabel(o)}</button>
            ))}
          </div>
        </div>
        {days.length > 1 && days.length <= 30 && (
          <details className="trip-differ">
            <summary>Some days are different{differing ? ` (${differing})` : ''}</summary>
            <p className="hint">For example a business meeting on two of the days.</p>
            <ul>
              {days.map((d) => (
                <li key={d}>
                  <label>
                    <span>{longDate(d)}</span>
                    <select value={draft.differ[d] ?? draft.occasion} disabled={locked}
                      onChange={(e) => setDraft({ ...draft, differ: { ...draft.differ, [d]: e.target.value } })}>
                      {OCCASIONS.map((o) => <option key={o} value={o}>{occasionLabel(o)}{o === draft.occasion ? ' (as the trip)' : ''}</option>)}
                    </select>
                  </label>
                </li>
              ))}
            </ul>
          </details>
        )}
        <label className="toggle trip-wash">
          <span className="toggle-text">
            <span className="toggle-label">I can wash there</span>
            <span className="hint">Pieces can be worn more often, so fewer are packed.</span>
          </span>
          <input type="checkbox" role="switch" checked={draft.canWash} disabled={locked} onChange={(e) => setDraft({ ...draft, canWash: e.target.checked })} />
          <span className="toggle-track" aria-hidden="true"><span className="toggle-thumb" /></span>
        </label>
        <button className="btn btn-primary trip-big-button" type="submit" disabled={locked || asking || !draft.place}
          title={locked ? OFFLINE_TITLE : undefined}>
          {asking ? <><span className="spinner" aria-hidden="true" /> Working it out…</> : 'Work out what to pack'}
        </button>
      </form>
    </section>
  );
}

function PlacePicker({ place, locked, onChoose }: { place: Place | null; locked: boolean; onChoose(p: Place | null): void }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Place[] | null>(null);
  const [searched, setSearched] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function search(e: FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    setBusy(true);
    setError(null);
    try {
      setResults(await api.places(q));
      setSearched(q);
    } catch (err) {
      setResults(null);
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (place) {
    return (
      <div className="trip-place-chosen">
        <p><span className="muted">Going to</span> <strong data-testid="trip-place">{place.name}</strong></p>
        <button className="btn btn-small btn-ghost" disabled={locked} onClick={() => onChoose(null)}>Change</button>
      </div>
    );
  }
  return (
    <div className="trip-place">
      <form className="field-row field-row-inline" onSubmit={search}>
        <label className="field">
          <span>Where are you going?</span>
          <input value={query} placeholder="e.g. Lisbon" onChange={(e) => setQuery(e.target.value)} autoComplete="off" disabled={locked} />
        </label>
        <button className="btn" type="submit" disabled={locked || busy || !query.trim()}>{busy ? 'Searching…' : 'Search'}</button>
      </form>
      <p className="hint">To look up the weather there, Closet sends Open-Meteo (open-meteo.com) only the place name you search for, then its location and the dates; nothing about your clothes.</p>
      {error && <p className="form-error" role="alert">{error}</p>}
      {results && results.length === 0 && <p className="hint">No places found for “{searched}”. Try the name of a nearby town or city.</p>}
      {results && results.length > 0 && (
        <ul className="route-list" aria-label="Places found">
          {results.map((p) => (
            <li key={`${p.latitude},${p.longitude},${p.name}`}>
              <button className="btn btn-block" onClick={() => { onChoose(p); setResults(null); setQuery(''); }}>{p.name}</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ a saved trip

function SavedTrip({ id }: { id: string }) {
  const { offline, profile, toast, items } = useCloset();
  const byId = useTripItems();
  // A piece missing from the closet is called archived or gone, so the plan waits until both lists are here:
  // shown a moment too early, every piece read "no longer in your closet". Offline there may be nothing to wait for.
  const itemsReady = offline || (items.active !== null && items.archived !== null);
  const [trip, setTrip] = useState<Trip | null>(() => loadSavedTrips(profile)?.details[id] ?? null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [newWeather, setNewWeather] = useState(false);
  const pending = useRef(0);
  const queue = useRef<Promise<unknown>>(Promise.resolve());

  useEffect(() => {
    let current = true;
    api.trip(id).then(
      (t) => {
        if (!current) return;
        setTrip(t);
        if (!connection.offline) keepTrip(profile, t);
      },
      (e) => {
        if (!current) return;
        const err = e as ApiError;
        const saved = loadSavedTrips(profile)?.details[id];
        if (err.status === 0 && saved) setTrip(saved);
        else setError(err.status === 0
          ? "You're offline, and this trip was not saved on this device. It shows here once Closet on your computer can be reached."
          : err.message);
      },
    );
    return () => {
      current = false;
    };
  }, [id, offline, profile]);

  // Its days may have come into the forecast since it was planned: say so, but never change the plan by itself.
  useEffect(() => {
    if (offline) return;
    let current = true;
    api.tripWeather(id).then((w) => current && setNewWeather(w.checked && w.changed), () => undefined);
    return () => {
      current = false;
    };
  }, [id, offline]);

  const locked = offline;

  function tick(line: string, on: boolean) {
    if (!trip || locked) return;
    setTrip((t) => t && { ...t, packed: on ? [...t.packed.filter((x) => x !== line), line] : t.packed.filter((x) => x !== line) });
    pending.current += 1;
    // one at a time, in the order they were tapped
    queue.current = queue.current.then(() => api.patchTrip(id, { ticks: { [line]: on } })).then(
      (t) => {
        pending.current -= 1;
        if (pending.current === 0) {
          setTrip(t);
          keepTrip(profile, t);
          void api.trip(id).then((fresh) => keepTrip(profile, fresh)).catch(() => undefined);
        }
      },
      (e) => {
        pending.current -= 1;
        toast((e as Error).message, 'error');
        void api.trip(id).then((t) => pending.current === 0 && setTrip(t), () => undefined);
      },
    );
  }

  async function change(patch: TripPatch, done?: string) {
    setBusy(true);
    try {
      const updated = await api.patchTrip(id, patch);
      setTrip(updated);
      keepTrip(profile, updated);
      if (patch.replan) setNewWeather(false);
      if (done) toast(done);
      void api.trip(id).catch(() => undefined);
    } catch (e) {
      toast((e as Error).message, 'error');
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!trip || !window.confirm(`Delete the trip to ${shortPlace(trip.place.name)}? Nothing in your closet changes.`)) return;
    setBusy(true);
    try {
      await api.removeTrip(id);
      forgetTrip(profile, id);
      toast('Trip deleted');
      navigate('/trips', { replace: true });
    } catch (e) {
      toast((e as Error).message, 'error');
      setBusy(false);
    }
  }

  if (!trip || !itemsReady) {
    return (
      <div className="trips">
        <BackToTrips />
        {error && !trip ? <p className={offline ? 'notice' : 'form-error'} role="alert">{error}</p>
          : <p className="muted"><span className="spinner" aria-hidden="true" /> Loading the trip…</p>}
      </div>
    );
  }

  const p = progress(trip.lines, trip.packed);
  const changes: Changes = {
    locked: locked || busy,
    leaveOut: trip.leave_out, pin: trip.pin,
    planAgain: () => void change({ replan: true }, 'Planned again'),
    swap: (x) => void change({ leave_out: [...trip.leave_out.filter((y) => y !== x), x], pin: trip.pin.filter((y) => y !== x) }),
    unswap: (x) => void change({ leave_out: trip.leave_out.filter((y) => y !== x) }),
    pinIn: (x) => void change({ pin: [...trip.pin.filter((y) => y !== x), x], leave_out: trip.leave_out.filter((y) => y !== x) }),
    unpin: (x) => void change({ pin: trip.pin.filter((y) => y !== x) }),
  };
  const title = locked ? OFFLINE_TITLE : undefined;

  return (
    <div className="trips trip-saved" aria-busy={busy}>
      <BackToTrips />
      <header className="page-header trip-header">
        <div>
          <h1 id="trips-title">{shortPlace(trip.place.name)}</h1>
          <p className="muted trip-sub">{dateRange(trip.first_day, trip.last_day)} · {occasionLabel(trip.occasion)}{trip.can_wash ? ' · Can wash there' : ''}</p>
        </div>
      </header>

      {locked && (
        <p className="notice notice-warn" role="status">
          <WarnIcon />
          <span>You're offline: this is the copy saved on this device. Ticking and changes wait until Closet on your computer can be reached.</span>
        </p>
      )}
      {newWeather && !locked && (
        <div className="notice notice-warn trip-new-weather" role="status">
          <WarnIcon />
          <div>
            <p><strong>The forecast has changed.</strong> The plan was made for different weather.</p>
            <button className="btn btn-small" disabled={busy} onClick={() => void change({ replan: true }, 'Planned again for the new forecast')}>Plan again</button>
          </div>
        </div>
      )}

      <div className="trip-progress" data-testid="trip-progress">
        <strong aria-live="polite">{p.words}</strong>
        <progress className="progress" max={p.total || 1} value={p.done} aria-label="Packed" />
      </div>

      <PlanView trip={trip} byId={byId} changes={changes} asking={busy}
        ticks={{ packed: new Set(trip.packed), locked, onTick: tick }} />

      <section className="trip-options" aria-label="Change the trip">
        <h2 className="chip-group-title">Change the trip</h2>
        <div className="today-choice" role="group" aria-label="Occasion">
          <span className="chip-group-title" aria-hidden="true">Occasion</span>
          <div className="chips chips-scroll">
            {OCCASIONS.map((o) => (
              <button key={o} type="button" className={`chip${trip.occasion === o ? ' is-on' : ''}`} aria-pressed={trip.occasion === o}
                disabled={locked || busy} title={title} onClick={() => trip.occasion !== o && void change({ occasion: o, day_occasions: dropSame(trip.day_occasions, o) })}>
                {occasionLabel(o)}
              </button>
            ))}
          </div>
        </div>
        <label className="toggle trip-wash">
          <span className="toggle-text"><span className="toggle-label">I can wash there</span></span>
          <input type="checkbox" role="switch" checked={trip.can_wash} disabled={locked || busy} onChange={(e) => void change({ can_wash: e.target.checked })} />
          <span className="toggle-track" aria-hidden="true"><span className="toggle-thumb" /></span>
        </label>
        <div className="row">
          <button className="btn" disabled={locked || busy} title={title} onClick={() => void change({ replan: true }, 'Planned again')}>Plan again</button>
          <button className="btn btn-danger-quiet" disabled={locked || busy} title={title} onClick={() => void remove()}>Delete this trip</button>
        </div>
      </section>
    </div>
  );
}

function dropSame(days: Record<string, string>, occasion: string): Record<string, string> {
  return Object.fromEntries(Object.entries(days).filter(([, o]) => o !== occasion));
}

// ------------------------------------------------------------------ the plan

interface Changes {
  locked: boolean;
  leaveOut: string[];
  pin: string[];
  planAgain?(): void;
  swap(id: string): void;
  unswap(id: string): void;
  pinIn(id: string): void;
  unpin(id: string): void;
}

interface Ticks {
  packed: Set<string>;
  locked: boolean;
  onTick(line: string, on: boolean): void;
}

function PlanView({ trip, byId, changes, asking, ticks }: {
  trip: PlannedTrip; byId: Map<string, ItemSummary>; changes: Changes; asking: boolean; ticks?: Ticks;
}) {
  const view = useMemo<GridView>(loadGridView, []);
  const plan = trip.plan;
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const packedIds = new Set(plan.packed.map((x) => x.id));
  const title = changes.locked ? OFFLINE_TITLE : undefined;

  return (
    <div className={`trip-plan${asking ? ' is-asking' : ''}`}>
      <WeatherStrip days={trip.weather} />
      {trip.weather_message && <p className="notice notice-warn" role="note"><WarnIcon /><span>{trip.weather_message}</span></p>}

      {plan.uncovered.length > 0 && (
        <div className="today-warnings trip-uncovered" role="note" aria-label="Not covered">
          <WarnIcon />
          <ul>
            {plan.uncovered.map((u) => <li key={u.date}><strong>{longDate(u.date)}:</strong> {u.reason}</li>)}
          </ul>
        </div>
      )}
      {plan.warnings.length > 0 && (
        <div className="notice notice-warn trip-uncovered" role="note" aria-label="Days dressed with warnings">
          <WarnIcon />
          <div>
            <strong>These days have an outfit with something to watch out for:</strong>
            <ul>{plan.warnings.map((w) => <li key={w.date}><strong>{longDate(w.date)}:</strong> {w.reason}</li>)}</ul>
          </div>
        </div>
      )}

      {(changes.leaveOut.length > 0 || changes.pin.length > 0) && (
        <div className="chips today-changes" role="group" aria-label="Your changes">
          {changes.pin.map((x) => (
            <button key={x} className="chip chip-change" disabled={changes.locked} title={title} aria-label={`Stop insisting on ${itemName(byId.get(x))}`}
              onClick={() => changes.unpin(x)}>Taking {itemName(byId.get(x))} <span aria-hidden="true">×</span></button>
          ))}
          {changes.leaveOut.map((x) => (
            <button key={x} className="chip chip-change" disabled={changes.locked} title={title} aria-label={`Put back ${itemName(byId.get(x))}`}
              onClick={() => changes.unswap(x)}>Without {itemName(byId.get(x))} <span aria-hidden="true">×</span></button>
          ))}
        </div>
      )}

      <div className="trip-columns">
        <section className="trip-pack" aria-labelledby="pack-title">
          <h2 id="pack-title">What to pack <span className="count">· {plan.packed.length === 1 ? '1 piece' : `${plan.packed.length} pieces`}</span></h2>
          {plan.packed.length === 0 && <p className="muted">Nothing from the closet: no day could be dressed.</p>}
          {groupPacked(plan.packed).map((g) => (
            <div key={g.group} className="trip-group">
              <h3 className="chip-group-title">{g.label}</h3>
              <ul className="trip-lines" aria-label={g.label}>
                {g.pieces.map((piece) => {
                  const item = byId.get(piece.id);
                  const name = itemName(item);
                  const unavailable = !item || item.status === 'archived';
                  const line = itemLine(piece.id);
                  return (
                    <li key={piece.id} className={`trip-line${ticks?.packed.has(line) ? ' is-ticked' : ''}`} data-testid="pack-line">
                      <Line ticks={ticks} line={line} name={name}>
                        <span className="trip-thumb">{item ? <TilePicture item={item} view={view} /> : <span className="pic-placeholder"><HangerIcon /></span>}</span>
                        <span className="trip-line-text">
                          <span className="trip-line-name">{name}</span>
                          <span className="trip-line-sub">
                            {wornWords(piece.days)}{piece.pinned ? ' · You chose this' : ''}
                            {item?.status === 'archived' ? ' · Archived' : !item ? ' · No longer in your closet' : ''}
                          </span>
                        </span>
                      </Line>
                      <button className="trip-more" aria-label={`Choices for ${name}`} aria-expanded={menuFor === piece.id}
                        onClick={() => setMenuFor(menuFor === piece.id ? null : piece.id)}><MoreIcon /></button>
                      {menuFor === piece.id && (
                        <div className="today-piece-menu trip-menu" role="group" aria-label={`Choices for ${name}`}>
                          <div className="row">
                            <button className="btn btn-small" disabled={changes.locked} title={title} onClick={() => { setMenuFor(null); changes.swap(piece.id); }}>Not this one</button>
                            {piece.pinned && <button className="btn btn-small" disabled={changes.locked} title={title} onClick={() => { setMenuFor(null); changes.unpin(piece.id); }}>Let Closet choose</button>}
                            <Link className="btn btn-small btn-ghost" to={`/item/${encodeURIComponent(piece.id)}`}>See it</Link>
                            <button className="btn btn-small btn-ghost" onClick={() => setMenuFor(null)}>Close</button>
                          </div>
                        </div>
                      )}
                      {unavailable && changes.planAgain && (
                        <button className="btn btn-small trip-line-replan" disabled={changes.locked} title={title}
                          onClick={changes.planAgain}>Plan again</button>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
          <TakeSomethingElse byId={byId} packed={packedIds} changes={changes} />

          <div className="trip-group">
            <h3 className="chip-group-title">Basics</h3>
            <ul className="trip-lines" aria-label="Basics">
              {plan.basics.map((b) => {
                const line = basicLine(b.key);
                return (
                  <li key={b.key} className={`trip-line trip-basic${ticks?.packed.has(line) ? ' is-ticked' : ''}`} data-testid="pack-line">
                    <Line ticks={ticks} line={line} name={b.name}>
                      <span className="trip-count" aria-hidden="true">{b.count}×</span>
                      <span className="trip-line-text"><span className="trip-line-name">{b.name}</span><span className="visually-hidden">: {b.count}</span></span>
                    </Line>
                  </li>
                );
              })}
            </ul>
          </div>
          {plan.notes.length > 0 && <ul className="hint trip-notes">{plan.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
        </section>

        <section className="trip-days" aria-labelledby="days-title">
          <h2 id="days-title">Day by day</h2>
          <ol className="trip-day-list">
            {plan.days.map((d) => <DayCard key={d.date} day={d} tripOccasion={trip.occasion} byId={byId} view={view} />)}
          </ol>
        </section>
      </div>
    </div>
  );
}

function Line({ ticks, line, name, children }: { ticks?: Ticks; line: string; name: string; children: ReactNode }) {
  if (!ticks) return <div className="trip-line-body">{children}</div>;
  const on = ticks.packed.has(line);
  return (
    <label className="trip-line-body trip-tick" title={ticks.locked ? OFFLINE_TITLE : undefined}>
      <input type="checkbox" checked={on} disabled={ticks.locked} aria-label={`Packed: ${name}`} onChange={(e) => ticks.onTick(line, e.target.checked)} />
      {children}
    </label>
  );
}

function TakeSomethingElse({ byId, packed, changes }: { byId: Map<string, ItemSummary>; packed: Set<string>; changes: Changes }) {
  const [choice, setChoice] = useState('');
  const options = [...byId.values()]
    .filter((i) => i.category && !packed.has(i.id) && i.rating !== 'dislike')
    .sort((a, b) => (a.category ?? '').localeCompare(b.category ?? '') || itemName(a).localeCompare(itemName(b)));
  if (!options.length) return null;
  return (
    <details className="trip-take">
      <summary>Take something else</summary>
      <p className="hint">Choose a piece you want to bring; the plan is worked out again with it.</p>
      <div className="field-row field-row-inline">
        <label className="field">
          <span>Piece</span>
          <select value={choice} onChange={(e) => setChoice(e.target.value)} disabled={changes.locked}>
            <option value="">Choose…</option>
            {options.map((i) => (
              <option key={i.id} value={i.id}>{itemName(i)}{i.laundry === 'laundry' ? ' (in the laundry)' : ''}</option>
            ))}
          </select>
        </label>
        <button className="btn" disabled={!choice || changes.locked} title={changes.locked ? OFFLINE_TITLE : undefined}
          onClick={() => { changes.pinIn(choice); setChoice(''); }}>I want to take this</button>
      </div>
    </details>
  );
}

function WeatherStrip({ days }: { days: TripDay[] }) {
  return (
    <section className="trip-weather" aria-label="The weather">
      {sourceRuns(days).map((run) => (
        <div key={run.days[0].date} className={`trip-weather-run is-${run.source}`}>
          <h2 className="trip-weather-source" data-testid="weather-source">{run.label}</h2>
          <ol>
            {run.days.map((d) => {
              const s = shortDay(d.date);
              return (
                <li key={d.date} className={`trip-weather-day${d.rain ? ' is-rainy' : ''}`} aria-label={`${longDate(d.date)}: ${dayTemps(d)}${d.rain !== null ? `, ${dayRain(d)}` : ''}`}>
                  <span className="trip-weather-date"><strong>{s.weekday}</strong> {s.date}</span>
                  <span className="trip-weather-temps">{d.low_c === null || d.high_c === null ? '?' : `${Math.round(d.low_c)}° / ${Math.round(d.high_c)}°`}</span>
                  <span className="trip-weather-rain">{d.rain === null ? 'Unknown' : d.rain ? 'Rain' : 'Dry'}</span>
                </li>
              );
            })}
          </ol>
        </div>
      ))}
    </section>
  );
}

function DayCard({ day, tripOccasion, byId, view }: {
  day: PlannedTrip['plan']['days'][number]; tripOccasion: string; byId: Map<string, ItemSummary>; view: GridView;
}) {
  const o: Outfit | null = day.outfit;
  return (
    <li className={`trip-day${day.problem || day.warning ? ' has-problem' : ''}`} data-testid="trip-day">
      <div className="trip-day-head">
        <strong>{longDate(day.date)}</strong>
        <span className="muted">{dayTemps(day.weather)}{day.weather.rain ? ' · Rain' : ''}</span>
        {day.occasion !== tripOccasion && <span className="trip-day-occasion">{occasionLabel(day.occasion)}</span>}
      </div>
      {day.problem && <p className="trip-day-problem"><WarnIcon className="inline-icon" /> {day.problem}</p>}
      {day.warning && !o?.warnings.includes(day.warning) && <p className="trip-day-problem"><WarnIcon className="inline-icon" /> {day.warning}</p>}
      {o && (
        <>
          <ul className="trip-day-pieces" aria-label={`What to wear on ${longDate(day.date)}`}>
            {wornOrder(o.pieces).map((p) => {
              const item = byId.get(p.id);
              return (
                <li key={p.id} title={`${placeLabel(p.place)}: ${itemName(item)}`}>
                  <span className="trip-day-pic">{item ? <TilePicture item={item} view={view} /> : <span className="pic-placeholder"><HangerIcon /></span>}</span>
                  <span className="trip-day-name">
                    {itemName(item)}{item?.status === 'archived' ? ' · Archived' : !item ? ' · No longer in your closet' : ''}
                  </span>
                </li>
              );
            })}
          </ul>
          {o.warnings.length > 0 && <ul className="trip-day-warnings">{o.warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
          {o.reasons.length > 0 && (
            <details className="trip-day-why">
              <summary>Why this works</summary>
              <ul>{o.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
            </details>
          )}
        </>
      )}
    </li>
  );
}
