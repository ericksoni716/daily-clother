import { useEffect, useState, type FormEvent } from 'react';
import { api, ApiError } from '../api';
import { HangerIcon } from '../components/Icons';
import { loadGridView } from '../drawing';
import { Link, navigate } from '../router';
import { useCloset } from '../store';
import { longDate, occasionLabel, OCCASIONS, shortPlace, temps, wornOrder } from '../today';
import { keepTrips, packingProgress, readTrips, type Trip, type TripChoices, type TripPatch, type TripPreview } from '../trips';
import type { ItemSummary, Place } from '../types';
import { localDay } from '../wears';
import './Trips.css';

const OFFLINE_TITLE = 'Needs Closet on your computer to be reachable';
const GROUPS: Record<string, string> = { tops: 'Tops', layers: 'Layers', bottoms: 'Bottoms', shoes: 'Shoes', outer: 'Outer layers', accessories: 'Accessories' };

export function TripsScreen({ tripId }: { tripId: string | null }) {
  const { profile, offline, items } = useCloset();
  const [list, setList] = useState<Trip[]>(() => readTrips(profile));
  const [preview, setPreview] = useState<TripPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [pin, setPin] = useState('');
  const [editing, setEditing] = useState(false);
  const saved = list.find((t) => t.id === tripId);
  const selected = tripId === 'new' ? preview : saved;
  const disabled = busy || offline || loading;
  const byId = new Map((items.active ?? []).map((i) => [i.id, i]));

  useEffect(() => {
    let current = true;
    async function load() {
      try {
        let next = await api.trips();
        if (tripId && tripId !== 'new') {
          const opened = await api.trip(tripId);
          next = next.map((t) => t.id === tripId ? opened : t);
        }
        if (current) { setList(next); keepTrips(profile, next); }
      } catch (e) {
        if (current && (!(e instanceof ApiError) || e.status !== 0)) setError((e as Error).message);
      } finally {
        if (current) setLoading(false);
      }
    }
    void load();
    return () => { current = false; };
  }, [profile, tripId, offline]);

  function remember(trip: Trip) {
    const next = [trip, ...list.filter((t) => t.id !== trip.id)];
    setList(next);
    keepTrips(profile, next);
  }

  async function act(work: () => Promise<void>) {
    if (disabled) return;
    setBusy(true); setError('');
    try { await work(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  async function change(changes: TripPatch) {
    if (!selected) return;
    await act(async () => {
      if (saved) remember(await api.patchTrip(saved.id, { ...changes, revision: saved.revision }));
      else setPreview(await api.planTrip({ ...selected.choices, ...changes }));
    });
  }

  const progress = selected ? packingProgress(saved ?? selected) : null;
  const name = selected ? shortPlace(selected.choices.place.name) : 'Trips';
  return (
    <div className="trips-page">
      <header className="page-header">
        <div>
          {tripId && <Link to="/trips" className="trip-back">← All trips</Link>}
          <h1>{tripId === 'new' && !preview ? 'Plan a trip' : name}</h1>
          {selected && <p className="muted">{longDate(selected.choices.first_day)} – {longDate(selected.choices.last_day)} · {occasionLabel(selected.choices.occasion)}</p>}
          {!tripId && <p className="muted">A small suitcase. An outfit for every day.</p>}
        </div>
        {!tripId && <Link to="/trips/new" className="btn btn-primary">Plan a trip</Link>}
      </header>
      {error && <div role="alert" className="form-error">{error} <button className="btn" onClick={() => window.location.reload()}>Open again</button></div>}
      {offline && <p className="hint">Needs Closet on your computer to be reachable. You can read your saved trips; changes have to wait.</p>}
      {loading && !selected && <p role="status">Opening your trips…</p>}
      {!tripId && <div className="trip-list">
        {!loading && list.length === 0 && <p>No trips yet. Choose a place and dates to start packing.</p>}
        {list.map((t) => {
          const p = packingProgress(t);
          return <Link key={t.id} to={`/trips/${t.id}`} className="trip-card">
            <strong>{shortPlace(t.choices.place.name)}</strong>
            <span>{longDate(t.choices.first_day)} – {longDate(t.choices.last_day)}</span>
            <span className="muted">{t.plan.piece_count} pieces · {p.packed} of {p.total} packed</span>
          </Link>;
        })}
      </div>}
      {((tripId === 'new' && !preview) || editing) && <TripForm disabled={disabled} initial={selected?.choices} onPlan={async (choices) => {
        await act(async () => {
          if (saved) remember(await api.patchTrip(saved.id, { ...choices, revision: saved.revision }));
          else setPreview(await api.planTrip(choices));
          setEditing(false);
        });
      }} />}
      {tripId && tripId !== 'new' && !selected && !loading && <p>This trip is not saved on this device. Open it while your computer is reachable.</p>}
      {selected && !editing && <>
        <div className="trip-actions">
          {!saved && <button className="btn btn-primary" disabled={disabled} onClick={() => void act(async () => {
            const trip = await api.saveTrip(selected.choices);
            remember(trip); navigate(`/trips/${trip.id}`);
          })}>Save trip</button>}
          <button className="btn" disabled={disabled} onClick={() => setEditing(true)}>Change trip</button>
          {saved && <button className="btn" disabled={disabled} onClick={() => void change({ replan: true })}>Plan again</button>}
          {busy && <span role="status">Saving…</span>}
        </div>
        {saved?.weather_changed && <div className="trip-notice" role="status">
          <strong>The forecast has changed, plan again</strong>
          <p>Your packing list and ticks have not changed.</p>
          <button className="btn" disabled={disabled} onClick={() => void change({ replan: true })}>Use the new forecast</button>
        </div>}
        <section aria-label="Weather for the trip" className="trip-weather-section">
          <h2>Weather there</h2>
          <div className="trip-weather">
            {selected.plan.days.map(({ date, weather: w }) => <div className="trip-weather-day" key={date}>
              <span>{longDate(date).split(' ').slice(1).join(' ')}</span>
              <strong>{w.low_c === null || w.high_c === null ? 'Unknown' : temps(w.low_c, w.high_c)}</strong>
              <span>{w.rain === null ? 'Check again later' : w.rain ? 'Rain likely' : 'Mostly dry'}</span>
              <small>{w.source === 'forecast' ? 'Forecast' : 'Usually, on these dates'}</small>
              {w.message && <small>{w.message}</small>}
            </div>)}
          </div>
        </section>
        {selected.plan.uncovered.length > 0 && <div className="trip-notice" role="note">
          <strong>{selected.plan.uncovered.length} {selected.plan.uncovered.length === 1 ? 'day still needs' : 'days still need'} an outfit</strong>
          <p>Check “Day by day” below before you pack. Closet has not filled these days with unsuitable clothes.</p>
        </div>}
        <div className="trip-columns">
          <section aria-label="What to pack" className="trip-packing">
            <div className="trip-progress">
              <h2>What to pack <span className="muted">· {selected.plan.piece_count} pieces</span></h2>
              <p aria-live="polite">{progress!.packed} of {progress!.total} packed</p>
              <progress max={progress!.total} value={progress!.packed} aria-label="Packing progress" />
              {!saved && <small>Save this trip to tick things off on your phone.</small>}
            </div>
            {Object.entries(selected.plan.packing).filter(([, ps]) => ps.length).map(([g, ps]) => <div className="trip-group" key={g}>
              <h3>{GROUPS[g]}</h3>
              {ps.map((p) => <div className={`packing-line${saved?.checked[`item:${p.id}`] ? ' is-packed' : ''}`} key={p.id} data-testid="packing-piece">
                <label className="packing-check" title={offline ? OFFLINE_TITLE : undefined}>
                  <input type="checkbox" checked={!!saved?.checked[`item:${p.id}`]} disabled={disabled || !saved}
                    onChange={(e) => void change({ checked: { [`item:${p.id}`]: e.target.checked } })} />
                  <TripImage item={byId.get(p.id)} />
                  <span><strong>{p.name}</strong><small>{p.days_worn} {p.days_worn === 1 ? 'day' : 'days'} worn{p.pinned ? ' · Pinned to take' : ''}</small></span>
                </label>
                <button className="btn btn-ghost" disabled={disabled} aria-label={`Not this piece: ${p.name}`}
                  onClick={() => void change({ leave_out: [...selected.choices.leave_out, p.id], pins: selected.choices.pins.filter((id) => id !== p.id) })}>Not this one</button>
              </div>)}
            </div>)}
            <div className="trip-group">
              <h3>Basics</h3><p className="hint">Counts only, not pieces from your closet.</p>
              {selected.plan.basics.map((b) => <label className="packing-check basic-line" key={b.id}>
                <input type="checkbox" checked={!!saved?.checked[`basic:${b.id}`]} disabled={disabled || !saved}
                  onChange={(e) => void change({ checked: { [`basic:${b.id}`]: e.target.checked } })} />
                <span><strong>{b.name}</strong><small>{b.count}{b.id === 'underwear' || b.id === 'socks' ? ' · one for each day, plus a spare' : ''}</small></span>
              </label>)}
            </div>
            <details className="trip-options">
              <summary>Take a particular piece, or undo a swap</summary>
              <label className="field"><span>I want to take this</span><select value={pin} disabled={disabled} onChange={(e) => setPin(e.target.value)}>
                <option value="">Choose a piece</option>
                {(items.active ?? []).filter((i) => i.laundry === 'clean' && i.rating !== 'dislike').map((i) => <option key={i.id} value={i.id}>{i.name || i.category}</option>)}
              </select></label>
              <button className="btn" disabled={disabled || !pin} onClick={() => void change({
                pins: [...new Set([...selected.choices.pins, pin])], leave_out: selected.choices.leave_out.filter((id) => id !== pin),
              })}>Pin to take</button>
              {selected.choices.pins.map((id) => <button key={id} className="btn btn-ghost" disabled={disabled} onClick={() => void change({ pins: selected.choices.pins.filter((p) => p !== id) })}>
                Unpin {byId.get(id)?.name || 'piece'}
              </button>)}
              {selected.choices.leave_out.map((id) => <button key={id} className="btn btn-ghost" disabled={disabled} onClick={() => void change({ leave_out: selected.choices.leave_out.filter((p) => p !== id) })}>
                Allow {byId.get(id)?.name || 'piece'} again
              </button>)}
            </details>
          </section>
          <section aria-label="Day by day" className="trip-days">
            <h2>Day by day</h2>
            {selected.plan.days.map((d, i) => <article className="trip-day" key={d.date}>
              <header><span className="trip-day-number">{i + 1}</span><div><h3>{longDate(d.date)}</h3><span className="muted">{occasionLabel(d.occasion)}</span></div></header>
              {!d.outfit ? <div className="trip-notice"><strong>No suitable outfit</strong>{d.missing.map((m) => <p key={m}>{m}</p>)}</div> : <>
                <div className="trip-outfit">{wornOrder(d.outfit.pieces).map(({ id }) => <div key={id}>
                  <TripImage item={byId.get(id)} /><small>{byId.get(id)?.name || Object.values(selected.plan.packing).flat().find((p) => p.id === id)?.name || 'Piece no longer in closet'}</small>
                </div>)}</div>
                {d.outfit.warnings.length > 0 && <div className="trip-notice">{d.outfit.warnings.map((w) => <p key={w}>{w}</p>)}</div>}
                <details><summary>Why this works</summary><ul>{d.outfit.reasons.map((r) => <li key={r}>{r}</li>)}</ul></details>
              </>}
            </article>)}
          </section>
        </div>
        <aside className="trip-footnotes">{selected.plan.notes.map((n) => <p className="hint" key={n}>{n}</p>)}</aside>
        {saved && <button className="btn btn-danger" disabled={disabled} onClick={() => {
          if (window.confirm('Delete this trip and its packing list?')) void act(async () => {
            await api.deleteTrip(saved.id);
            keepTrips(profile, list.filter((t) => t.id !== saved.id)); navigate('/trips');
          });
        }}>Delete trip</button>}
      </>}
    </div>
  );
}

function TripImage({ item }: { item: ItemSummary | undefined }) {
  const src = loadGridView() === 'drawings' ? item?.illustration_url || item?.thumb_url : item?.thumb_url || item?.illustration_url;
  return <span className="trip-image">{src ? <img src={src} alt="" loading="lazy" /> : <HangerIcon />}</span>;
}

function TripForm({ disabled, initial, onPlan }: { disabled: boolean; initial?: TripChoices; onPlan(c: TripChoices): Promise<void> }) {
  const [query, setQuery] = useState('');
  const [places, setPlaces] = useState<Place[]>([]);
  const [place, setPlace] = useState<Place | null>(initial?.place ?? null);
  const [first, setFirst] = useState(initial?.first_day ?? localDay());
  const [last, setLast] = useState(initial?.last_day ?? localDay());
  const [occasion, setOccasion] = useState(initial?.occasion ?? 'casual');
  const [wash, setWash] = useState(initial?.can_wash ?? false);
  const [overrides, setOverrides] = useState(initial?.overrides ?? []);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState('');
  async function search(e: FormEvent) {
    e.preventDefault(); setSearching(true); setError('');
    try { setPlaces(await api.places(query)); }
    catch (e) { setError((e as Error).message); }
    finally { setSearching(false); }
  }
  return <div className="trip-form">
    <h2>Where are you going?</h2>
    <p className="hint">Only your place search, location, time zone and dates go to Open-Meteo. Nothing about your clothes.</p>
    <form className="field-row field-row-inline" onSubmit={(e) => void search(e)}>
      <label className="field"><span>Search for a place</span><input value={query} onChange={(e) => setQuery(e.target.value)} disabled={disabled || searching} placeholder="Town or city" /></label>
      <button className="btn" disabled={disabled || searching || query.trim().length < 2}>{searching ? 'Searching…' : 'Search'}</button>
    </form>
    {error && <p role="alert" className="form-error">{error}</p>}
    {places.length > 0 && <ul className="route-list" aria-label="Places found">{places.map((p) => <li key={`${p.latitude}:${p.longitude}`}>
      <button className="btn btn-block" disabled={disabled} onClick={() => { setPlace(p); setPlaces([]); }}>{p.name}</button>
    </li>)}</ul>}
    {place && <p className="state-line">Going to <strong>{place.name}</strong></p>}
    <form onSubmit={(e) => { e.preventDefault(); if (place) void onPlan({
      place, first_day: first, last_day: last, occasion, can_wash: wash, overrides,
      pins: initial?.pins ?? [], leave_out: initial?.leave_out ?? [],
    }); }}>
      <fieldset disabled={disabled}>
        <div className="trip-date-fields">
          <label className="field"><span>First day</span><input type="date" required min={initial ? undefined : localDay()} value={first} onChange={(e) => setFirst(e.target.value)} /></label>
          <label className="field"><span>Last day</span><input type="date" required min={first} value={last} onChange={(e) => setLast(e.target.value)} /></label>
        </div>
        <p className="hint">Up to 30 days. Nearer days use the forecast; later days use what these dates were like over the last five years.</p>
        <label className="field"><span>What is the trip for?</span><Occasion value={occasion} onChange={setOccasion} /></label>
        <label className="packing-check"><input type="checkbox" checked={wash} onChange={(e) => setWash(e.target.checked)} /><span>I can wash there</span></label>
        <details className="trip-options">
          <summary>Some days are different</summary>
          {overrides.map((o, i) => <div className="trip-override" key={i}>
            <label className="field"><span>Different day {i + 1}</span><input type="date" required min={first} max={last} value={o.date} onChange={(e) => setOverrides(overrides.map((d, j) => i === j ? { ...d, date: e.target.value } : d))} /></label>
            <label className="field"><span>Occasion {i + 1}</span><Occasion value={o.occasion} onChange={(v) => setOverrides(overrides.map((d, j) => i === j ? { ...d, occasion: v } : d))} /></label>
            <button type="button" className="btn" onClick={() => setOverrides(overrides.filter((_, j) => i !== j))}>Remove day</button>
          </div>)}
          <button type="button" className="btn" disabled={overrides.length >= 30} onClick={() => setOverrides([...overrides, { date: first, occasion: 'business' }])}>Add a different day</button>
        </details>
        <button className="btn btn-primary" disabled={!place}>{disabled ? 'Working out your packing…' : 'Work out what to pack'}</button>
      </fieldset>
    </form>
  </div>;
}

function Occasion({ value, onChange }: { value: string; onChange(v: string): void }) {
  return <select value={value} onChange={(e) => onChange(e.target.value)}>{OCCASIONS.map((o) => <option key={o} value={o}>{occasionLabel(o)}</option>)}</select>;
}
