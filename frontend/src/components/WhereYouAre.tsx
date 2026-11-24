import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent, type ReactNode } from 'react';
import { api } from '../api';
import { whenAt } from '../wears';
import { locate } from '../location';
import { settingsSaved, weatherQuery } from '../settings';
import type { Place, Settings } from '../types';
import { weatherLine, withoutTyping } from '../weather';
import { Fold } from './ui';

type Toast = (m: string, k?: 'ok' | 'error') => void;

const samePlace = (a: Place | null | undefined, b: Place | null | undefined) =>
  !!a && !!b && a.latitude === b.latitude && a.longitude === b.longitude && a.name === b.name;

/**
 * Where you are: search for a place by name or use the browser's location (only on a tap), choose one, see today's
 * weather for it, go back to New York. In Settings, and inline on Today (`inline`: without the weather and the way back).
 * A place chosen is written into the settings kept by the page (and the weather asked again); `onChange` also gets them.
 */
export function WhereYouAre({ place, home, offline, onChange, toast, inline, trip = false }: {
  place: Place | null | undefined; home?: Place | null; offline: boolean; onChange?(s: Settings): void; toast: Toast; inline?: boolean;
  /** On a day a trip covers (Today's sheet): the place saved is home's, and changing it does not move the trip. */
  trip?: boolean;
}) {
  const qc = useQueryClient();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Place[] | null>(null);
  const [searched, setSearched] = useState('');
  const [busy, setBusy] = useState(false);
  const [locating, setLocating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [locError, setLocError] = useState<string | null>(null);

  async function fromBrowser() {
    setLocating(true);
    setError(null);
    setLocError(null);
    const found = await locate({
      secure: window.isSecureContext, geolocation: 'geolocation' in navigator ? navigator.geolocation : undefined, near: api.placeNear,
    });
    setLocating(false);
    if (found.kind === 'found') await save(found.place);
    else setLocError(found.message);
  }

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

  async function save(next: Place | null) {
    setBusy(true);
    setError(null);
    try {
      const saved = await api.putSettings({ place: next });
      settingsSaved(qc, saved, 'settings', { place: next });
      onChange?.(saved);
      setResults(null);
      setQuery('');
      toast(next ? `Saved: ${saved.place?.name ?? next.name}` : `Back to ${saved.place?.name ?? 'New York'}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  let saved: ReactNode;
  if (offline) saved = <p className="hint">Where you are can't be seen or changed while you're offline.</p>;
  else if (place === undefined) saved = null;
  else if (place === null) saved = <p className="hint">{trip ? 'No home place saved yet, so home is New York.' : 'No place saved yet, so Nines uses New York.'}</p>;
  else {
    const isHome = samePlace(place, home);
    saved = (
      <>
        <p className="state-line state-ready">
          <span className="state-dot" aria-hidden="true" />
          <span>{trip ? 'At home' : isHome ? 'Using' : 'Saved'}: <strong data-testid="saved-place">{place.name}</strong></span>
        </p>
        {isHome && !inline && <p className="hint">New York until you choose a place.</p>}
        {!inline && <TodaysWeather place={place} offline={offline} />}
        {!inline && home && !isHome && (
          <button className="btn btn-ghost" disabled={busy} onClick={() => void save(null)}>Back to {home.name.split(',')[0]}</button>
        )}
      </>
    );
  }

  const sent = (
    <p className="hint">
      Nines uses today's weather to choose outfits. To look it up it sends Open-Meteo (open-meteo.com) only the place name you search for here and the saved place's location; nothing about your clothes.
      {' '}"Use my location" asks your browser where you are, only when you tap it, and sends OpenStreetMap only that position, rounded to about a kilometre, to name the town.
    </p>
  );
  return (
    <>
      {/* the controls come first, in Settings as on Today, and what is sent is one tap away at the end */}
      {saved}
      {!offline && (
        <>
          <form className="field-row field-row-inline" onSubmit={search}>
            <label className="field">
              <span>{trip ? 'Change where home is' : place ? 'Choose another place' : 'Search for a place'}</span>
              <input value={query} placeholder="e.g. Brooklyn" onChange={(e) => setQuery(e.target.value)} autoComplete="off" />
            </label>
            <button className="btn" type="submit" disabled={busy || locating || !query.trim()}>{busy && !results ? 'Searching…' : 'Search'}</button>
            <button className="btn" type="button" disabled={busy || locating} onClick={() => void fromBrowser()}>
              {locating ? 'Finding you…' : 'Use my location'}
            </button>
          </form>
          {locError && <p className="hint" role="status" data-testid="location-note">{locError}</p>}
          {error && <p className="form-error" role="alert">{error}</p>}
          {results && results.length === 0 && <p className="hint">No places found for “{searched}”. Try the name of a nearby town or city.</p>}
          {results && results.length > 0 && (
            <>
              <p className="hint">Choose one:</p>
              <ul className="route-list" aria-label="Places found">
                {results.map((p) => (
                  <li key={`${p.latitude},${p.longitude},${p.name}`}>
                    <button className="btn btn-block" disabled={busy} onClick={() => void save(p)}>{p.name}</button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
      <WeatherSent>{sent}</WeatherSent>
    </>
  );
}

/** What is sent to look up the weather, behind one closed thing to open: under where you are (Settings and Today) and
 * under where a trip is going. */
export function WeatherSent({ children }: { children: ReactNode }) {
  return <Fold title="What is sent to look up the weather" className="where-sent">{children}</Fold>;
}

/** Today's weather for the saved place, in one row. A slow lookup of its own; while the place just chosen is looked
 * up, the weather of the one before is not shown beside it. */
function TodaysWeather({ place, offline }: { place: Place; offline: boolean }) {
  const { data, error, refetch, isFetching } = useQuery({ ...weatherQuery(), enabled: !offline });
  const lookup = data && (!data.place || samePlace(data.place, place) || !isFetching) ? data : null;

  const again = <button className="btn" disabled={isFetching} onClick={() => void refetch()}>Try again</button>;
  if (error && !isFetching) return <><p className="form-error" role="alert">Couldn't look up today's weather: {error.message}</p>{again}</>;
  if (!lookup) return <p className="hint" aria-busy="true">Looking up today's weather…</p>;
  const w = lookup.weather;
  // no box for temperatures here (Today has one): the sentence without the clause that offers it
  if (!w) return <><p className="hint">{withoutTyping(lookup.message ?? '')}</p>{again}</>;
  return (
    <>
      <p data-testid="weather-today">{lookup.is_today ? 'Today' : `Forecast for ${w.date}`}: {weatherLine(w)}</p>
      {lookup.old && (
        <>
          <p className="hint">{lookup.message} Looked up {whenAt(w.fetched_at)}.</p>
          {again}
        </>
      )}
    </>
  );
}
