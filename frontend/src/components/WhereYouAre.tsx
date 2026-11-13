import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { api } from '../api';
import { formatDateTime } from '../labels';
import type { Place, Settings, WeatherLookup } from '../types';
import { weatherLine } from '../weather';

type Toast = (m: string, k?: 'ok' | 'error') => void;

/** Settings → Where you are: search for a place, choose one, see today's weather for it, remove it. */
export function WhereYouAre({ place, offline, onChange, toast }: { place: Place | null | undefined; offline: boolean; onChange(s: Settings): void; toast: Toast }) {
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

  async function save(next: Place | null) {
    setBusy(true);
    setError(null);
    try {
      onChange(await api.putSettings({ place: next }));
      setResults(null);
      setQuery('');
      toast(next ? 'Saved' : 'Removed');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  let saved: ReactNode;
  if (offline) saved = <p className="hint">Where you are can't be seen or changed while you're offline.</p>;
  else if (place === undefined) saved = null;
  else if (place === null) saved = <p className="hint">No place saved yet. Until you choose one, today's outfits need the day's temperatures given by hand.</p>;
  else {
    saved = (
      <>
        <p className="state-line state-ready">
          <span className="state-dot" aria-hidden="true" />
          <span>Saved: <strong data-testid="saved-place">{place.name}</strong></span>
        </p>
        <TodaysWeather place={place} />
        <button className="btn btn-ghost" disabled={busy} onClick={() => void save(null)}>Remove this place</button>
      </>
    );
  }

  return (
    <>
      <p className="hint">
        Closet uses today's weather to choose outfits. To look it up it sends Open-Meteo (open-meteo.com) only the place name you search for here and the saved place's location; nothing about your clothes.
      </p>
      {saved}
      {!offline && (
        <>
          <form className="field-row field-row-inline" onSubmit={search}>
            <label className="field">
              <span>{place ? 'Choose another place' : 'Search for a place'}</span>
              <input value={query} placeholder="e.g. Brooklyn" onChange={(e) => setQuery(e.target.value)} autoComplete="off" />
            </label>
            <button className="btn" type="submit" disabled={busy || !query.trim()}>{busy && !results ? 'Searching…' : 'Search'}</button>
          </form>
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
    </>
  );
}

function TodaysWeather({ place }: { place: Place }) {
  const [lookup, setLookup] = useState<WeatherLookup | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const key = `${place.latitude},${place.longitude},${place.timezone}`;

  useEffect(() => {
    let current = true;
    setLookup(null);
    setError(null);
    api.weather().then(
      (w) => current && setLookup(w),
      (e) => current && setError((e as Error).message),
    );
    return () => {
      current = false;
    };
  }, [key, attempt]);

  const again = <button className="btn" onClick={() => setAttempt((n) => n + 1)}>Try again</button>;
  if (error) return <><p className="form-error" role="alert">Couldn't look up today's weather: {error}</p>{again}</>;
  if (!lookup) return <p className="hint">Looking up today's weather…</p>;
  const w = lookup.weather;
  if (!w) return <><p className="hint">{lookup.message}</p>{again}</>;
  return (
    <>
      <p data-testid="weather-today">{lookup.is_today ? 'Today' : `Forecast for ${w.date}`}: {weatherLine(w)}</p>
      {lookup.old && (
        <>
          <p className="hint">{lookup.message} Looked up {formatDateTime(w.fetched_at)}.</p>
          {again}
        </>
      )}
    </>
  );
}
