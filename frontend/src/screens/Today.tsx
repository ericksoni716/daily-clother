import { useEffect, useRef, useState, type FormEvent } from 'react';
import { api } from '../api';
import { BackIcon, CheckIcon, ChevronIcon, HangerIcon, WarnIcon } from '../components/Icons';
import { label } from '../labels';
import { Link } from '../router';
import { useCloset } from '../store';
import type { ItemSummary, WeatherLookup } from '../types';
import {
  dayWeather, lastChoices, missingBasics, outfitPieces, pieceName, readTodayValue, savedToday, swipeDirection, todayDataVersion, writeTodayValue,
  type TodayChoices, type TodayResult, type WearReceipt,
} from '../today';
import { localDay } from '../wears';
import { ItemDetail } from './ItemDetail';
import './Today.css';

const EMPTY_ITEMS: ItemSummary[] = [];

export function TodayScreen({ itemId }: { itemId: string | null }) {
  const [day, setDay] = useState(localDay);
  useEffect(() => {
    const timer = window.setInterval(() => setDay(localDay()), 30_000);
    return () => window.clearInterval(timer);
  }, []);
  return (
    <>
      <div hidden={!!itemId}><TodayDay key={day} day={day} /></div>
      {itemId && <section className="today-detail">
        <Link to="/today" className="btn btn-ghost"><BackIcon /> Back to today's outfit</Link>
        <ItemDetail key={itemId} id={itemId} status="active" inPanel />
      </section>}
    </>
  );
}

function TodayDay({ day }: { day: string }) {
  const { profile, items, vocab, offline, upsert } = useCloset();
  const [dataVersion] = useState(todayDataVersion);
  const [initial] = useState(() => savedToday(profile, day));
  const [choices, setChoices] = useState<TodayChoices>(() => initial?.choices ?? lastChoices());
  const [result, setResult] = useState<TodayResult | null>(initial?.result ?? null);
  const [weather, setWeather] = useState<WeatherLookup | null>(initial?.weather ?? null);
  const [selected, setSelected] = useState(initial?.selected ?? 0);
  const [busy, setBusy] = useState(!initial);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');
  const [earlier, setEarlier] = useState(!!initial);
  const [refresh, setRefresh] = useState(0);
  const [editing, setEditing] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<(WearReceipt & { day: string }) | null>(() => {
    const saved = readTodayValue<WearReceipt & { day: string }>(`${profile}-wear`);
    return saved?.day === day ? saved : null;
  });
  const loaded = useRef(initial ? `0:${JSON.stringify(initial.choices)}` : '');
  const touch = useRef<{ x: number; y: number } | null>(null);
  const alive = useRef(true);
  const list = items.active ?? initial?.items ?? EMPTY_ITEMS;
  const outfit = result?.outfits[selected] ?? result?.outfits[0];
  const blocked = offline || busy || saving;
  const basics = missingBasics(list);
  const needsWeather = weather && (!weather.weather || !weather.is_today) && choices.low_c === undefined;

  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  useEffect(() => {
    if (!offline) return;
    const saved = savedToday(profile, day);
    if (saved) {
      setResult(saved.result);
      setChoices(saved.choices);
      setWeather(saved.weather);
      setSelected(saved.selected);
      setEarlier(true);
    }
  }, [offline, profile, day]);

  useEffect(() => {
    if (offline) {
      loaded.current = '';
      setBusy(false);
      return;
    }
    const key = `${refresh}:${JSON.stringify(choices)}`;
    if (loaded.current === key) return;
    const controller = new AbortController();
    let active = true;
    setBusy(true);
    setError('');
    void (async () => {
      try {
        const found = await api.weather();
        if (!active || dataVersion !== todayDataVersion()) return;
        setWeather(found);
        if ((!found.weather || !found.is_today) && choices.low_c === undefined) {
          setResult(null);
          loaded.current = key;
          return;
        }
        const answer = await api.today(choices, controller.signal);
        if (!active || dataVersion !== todayDataVersion()) return;
        setResult(answer);
        setSelected(0);
        setEarlier(false);
        loaded.current = key;
      } catch (e) {
        if (active) setError((e as Error).message);
      } finally {
        if (active) setBusy(false);
      }
    })();
    return () => { active = false; controller.abort(); };
  }, [choices, refresh, offline, dataVersion]);

  useEffect(() => {
    writeTodayValue('choices', { occasion: choices.occasion, mood: choices.mood });
  }, [choices.occasion, choices.mood]);

  useEffect(() => {
    if (result && !busy && dataVersion === todayDataVersion()) writeTodayValue(profile, { day, choices, result, weather, items: list, selected });
  }, [result, busy, profile, day, choices, weather, list, selected, dataVersion]);

  function change(patch: Partial<TodayChoices>) {
    setChoices((previous) => ({ ...previous, ...patch }));
    setResult(null);
    setSelected(0);
    setEditing(null);
    setActionError('');
  }

  function choose(index: number) {
    if (!result) return;
    setSelected(Math.max(0, Math.min(result.outfits.length - 1, index)));
    setEditing(null);
  }

  async function wear() {
    if (!outfit || blocked || receipt) return;
    setSaving(true);
    setActionError('');
    try {
      const item_ids = outfitPieces(outfit).map((p) => p.id);
      const saved = await api.wearOutfit(item_ids);
      if (!alive.current || dataVersion !== todayDataVersion()) return;
      saved.items.forEach(upsert);
      const next = { day, item_ids, worn_on: saved.worn_on, created_ids: saved.created_ids };
      setReceipt(next);
      writeTodayValue(`${profile}-wear`, next);
    } catch (e) {
      if (alive.current) setActionError(`${(e as Error).message} If the connection dropped, check the pieces' wear logs before trying again.`);
    } finally { if (alive.current) setSaving(false); }
  }

  async function undo() {
    if (!receipt || blocked) return;
    setSaving(true);
    setActionError('');
    try {
      if (receipt.created_ids.length) {
        const saved = await api.undoOutfit(receipt.created_ids, receipt.worn_on);
        if (!alive.current || dataVersion !== todayDataVersion()) return;
        saved.items.forEach(upsert);
      }
      setReceipt(null);
      writeTodayValue(`${profile}-wear`, null);
    } catch (e) { if (alive.current) setActionError((e as Error).message); }
    finally { if (alive.current) setSaving(false); }
  }

  const context = result?.context ?? (weather?.is_today && weather.weather ? weather.weather : null);
  const place = weather?.place?.name ?? result?.context.place;
  const wearingThis = outfit && receipt && outfitPieces(outfit).every((p) => receipt.item_ids.includes(p.id))
    && outfitPieces(outfit).length === receipt.item_ids.length;

  return (
    <section className="today" aria-labelledby="today-title">
      <div className="today-day">
      <header className="today-heading">
        <div>
          <p className="today-eyebrow">{new Date(`${day}T12:00:00`).toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })}</p>
          <h1 id="today-title">Today, put together.</h1>
          <p className="today-subtitle">A little less deciding. A little more you.</p>
        </div>
        <button className="btn btn-ghost today-refresh" disabled={blocked} onClick={() => setRefresh((n) => n + 1)}>Refresh</button>
      </header>

      <div className="today-weather">
        <span className="today-weather-symbol" aria-hidden="true">{context?.rain ? '☂' : '☀'}</span>
        <div>
          <strong>{place || 'Your day'}</strong>
          {context ? <p>{dayWeather(context)}</p> : <p className="muted">Today's temperatures help us choose your layers.</p>}
          {choices.low_c !== undefined && <span className="small muted">Using the weather you entered.</span>}
        </div>
      </div>
      </div>
      {weather?.message && <p className={weather.old ? 'today-warning' : 'hint'}>{weather.message}</p>}
      {needsWeather && <ManualWeather choices={choices} disabled={blocked} onChange={change} hasForecast={false} />}
      {choices.low_c !== undefined && <details className="today-weather-edit">
        <summary>Change today's temperatures</summary>
        <ManualWeather choices={choices} disabled={blocked} onChange={change} hasForecast={!!weather?.weather && weather.is_today} />
      </details>}

      <div className="today-choices">
        <fieldset disabled={blocked}>
          <legend>What kind of day?</legend>
          <div className="today-chips">
            {(vocab?.formality ?? ['athletic', 'casual', 'smart_casual', 'business', 'formal']).map((value) =>
              <button key={value} className={`chip${choices.occasion === value ? ' is-on' : ''}`} aria-pressed={choices.occasion === value}
                onClick={() => change({ occasion: value })}>{label('formality', value)}</button>)}
          </div>
        </fieldset>
        <fieldset disabled={blocked}>
          <legend>How do you feel?</legend>
          <div className="today-chips">
            {(['usual', 'sharp', 'relaxed'] as const).map((value) =>
              <button key={value} className={`chip${choices.mood === value ? ' is-on' : ''}`} aria-pressed={choices.mood === value}
                onClick={() => change({ mood: value })}>{label('mood', value)}</button>)}
          </div>
        </fieldset>
      </div>

      {(choices.build_around || choices.leave_out.length > 0) && <div className="today-adjustments">
        {choices.build_around && <span>Starting with <strong>{pieceName(list.find((i) => i.id === choices.build_around))}</strong>.
          <button className="btn btn-link" disabled={blocked} onClick={() => change({ build_around: undefined })}>Clear starting piece</button></span>}
        {choices.leave_out.length > 0 && <span>Leaving out {choices.leave_out.map((id) => pieceName(list.find((i) => i.id === id))).join(', ')}.
          <button className="btn btn-link" disabled={blocked} onClick={() => change({ leave_out: [] })}>Clear left-out pieces</button></span>}
      </div>}

      {(offline || earlier) && <p className="today-saved" role="status">
        {result ? 'Saved earlier today.' : 'No outfits saved for today yet.'}
        {offline ? ' Offline: choosing new outfits and recording wears need Closet on your computer.' : ' Refresh when you want a new suggestion.'}
      </p>}
      {receipt && <div className="today-recorded" role="status"><CheckIcon /><span>Today's wear is recorded for {receipt.item_ids.length} pieces.</span>
        <button className="btn btn-link" disabled={blocked} onClick={() => void undo()}>{saving ? 'Saving…' : 'Undo'}</button>
      </div>}
      {actionError && <p className="form-error" role="alert">{actionError}</p>}
      {busy && <div className="today-loading" role="status"><span className="spinner" /> Putting your outfit together…</div>}
      {error && <div className="form-error" role="alert">{error} <button className="btn" disabled={blocked} onClick={() => setRefresh((n) => n + 1)}>Try again</button></div>}

      {!busy && outfit && result && <>
        <div className="today-outfit-heading">
          <div><p className="today-eyebrow">{selected === 0 ? 'Our first pick' : 'Another way to wear the day'}</p><h2>Your outfit</h2></div>
          <div className="today-paging">
            <button className="btn" aria-label="Previous outfit" disabled={selected === 0} onClick={() => choose(selected - 1)}><BackIcon /></button>
            <span aria-live="polite">{selected + 1} / {result.outfits.length}</span>
            <button className="btn" aria-label="Next outfit" disabled={selected >= result.outfits.length - 1} onClick={() => choose(selected + 1)}><ChevronIcon /></button>
          </div>
        </div>
        <div className="today-outfit" data-testid="today-outfit"
          onTouchStart={(e) => { touch.current = { x: e.touches[0].clientX, y: e.touches[0].clientY }; }}
          onTouchEnd={(e) => {
            if (touch.current) {
              const direction = swipeDirection(e.changedTouches[0].clientX - touch.current.x, e.changedTouches[0].clientY - touch.current.y);
              if (direction) choose(selected + direction);
            }
            touch.current = null;
          }}>
          <div className="today-flatlay">
            <ul className="today-pieces" data-count={outfitPieces(outfit).length} aria-label="Outfit pieces">
              {outfitPieces(outfit).map(({ id, place: position }) => {
                const item = list.find((i) => i.id === id);
                const src = item?.cutout_state === 'ready' ? item.thumb_url : item?.illustration_url || item?.thumb_url;
                return <li key={id} className="today-piece" data-item-id={id}>
                  <Link className="today-piece-link" to={`/today/item/${encodeURIComponent(id)}`}>
                    <span className="today-piece-place">{position}</span>
                    <span className="today-piece-image">{src ? <img src={src} alt="" /> : <HangerIcon />}</span>
                    <span className="today-piece-name">{pieceName(item)}</span>
                  </Link>
                  <button className="today-piece-more" aria-label={`Change ${pieceName(item)}`} aria-expanded={editing === id}
                    disabled={blocked} onClick={() => setEditing(editing === id ? null : id)}>•••</button>
                </li>;
              })}
            </ul>
            {editing && <div className="today-piece-actions" role="group" aria-label={`Choices for ${pieceName(list.find((i) => i.id === editing))}`}>
              <strong>{pieceName(list.find((i) => i.id === editing))}</strong>
              <button className="btn" disabled={blocked} onClick={() => change({ leave_out: [...new Set([...choices.leave_out, editing])], build_around: choices.build_around === editing ? undefined : choices.build_around })}>Not this piece</button>
              <button className="btn" disabled={blocked} onClick={() => change({ build_around: editing, leave_out: choices.leave_out.filter((id) => id !== editing) })}>Start from this piece</button>
              <button className="btn btn-ghost" onClick={() => setEditing(null)}>Close</button>
            </div>}
            <div className="today-flatlay-foot"><span>Tap a piece to see its details</span><span>{outfit.score}/100 match</span></div>
          </div>
          <aside className="today-why" aria-label="Why this outfit">
            <h3>Why this works</h3>
            <ul className="today-reasons">{outfit.reasons.map((reason) => <li key={reason}><CheckIcon /><span>{reason}</span></li>)}</ul>
            {outfit.warnings.length > 0 && <div className="today-warning" role="note">
              <h3><WarnIcon /> Before you head out</h3>
              {outfit.warnings.map((warning) => <p key={warning}>{warning}</p>)}
            </div>}
            <button className="btn btn-primary btn-block today-wear" disabled={blocked || !!receipt} onClick={() => void wear()}>
              <CheckIcon />{saving ? 'Saving…' : wearingThis ? 'Wearing this today' : "I'm wearing this"}
            </button>
            <p className="small muted">{receipt ? 'Undo your recorded choice to choose another outfit.' : 'Records a wear for every piece. You can undo it.'}</p>
          </aside>
        </div>
        {result.outfits.length > 1 && <div className="today-alternatives" role="group" aria-label="Choose an outfit">
          {result.outfits.map((alternative, index) => <button key={index} className={`today-alternative${selected === index ? ' is-on' : ''}`}
            aria-pressed={selected === index} onClick={() => choose(index)}>
            <span>{index === 0 ? 'First pick' : `Option ${index + 1}`}</span>
            <span className="today-swatches" aria-hidden="true">{outfitPieces(alternative).map(({ id }) =>
              <i key={id} style={{ backgroundColor: list.find((i) => i.id === id)?.color_hex || 'var(--line)' }} />)}</span>
          </button>)}
        </div>}
      </>}

      {!busy && result && !result.outfits.length && <div className="today-empty">
        <HangerIcon /><h2>A few pieces short</h2>
        {result.missing.map((sentence) => <p key={sentence}>{sentence}</p>)}
        <Link to="/add" className="btn btn-primary" aria-disabled={offline} onClick={(e) => { if (offline) e.preventDefault(); }}>Add clothes</Link>
      </div>}
      {!busy && !result && items.active && basics.length > 0 && <div className="today-empty">
        <HangerIcon /><h2>Let's give your day a starting point</h2>
        {basics.map((sentence) => <p key={sentence}>{sentence}</p>)}
        <Link to="/add" className="btn btn-primary" aria-disabled={offline} onClick={(e) => { if (offline) e.preventDefault(); }}>Add clothes</Link>
      </div>}
      <details className="today-start">
        <summary>Have a piece in mind?</summary>
        <label className="field"><span>Start every outfit from this piece</span>
          <select value={choices.build_around ?? ''} disabled={blocked} onChange={(e) => change({ build_around: e.target.value || undefined, leave_out: choices.leave_out.filter((id) => id !== e.target.value) })}>
            <option value="">Let Closet choose</option>
            {list.filter((i) => i.status === 'active' && i.laundry === 'clean').map((item) => <option key={item.id} value={item.id}>{pieceName(item)}</option>)}
          </select>
        </label>
      </details>
    </section>
  );
}

function ManualWeather({ choices, disabled, onChange, hasForecast }: {
  choices: TodayChoices; disabled: boolean; onChange(patch: Partial<TodayChoices>): void; hasForecast: boolean;
}) {
  const [low, setLow] = useState(choices.low_c?.toString() ?? '');
  const [high, setHigh] = useState(choices.high_c?.toString() ?? '');
  const [rain, setRain] = useState(choices.rain ?? false);
  const [error, setError] = useState('');
  function submit(e: FormEvent) {
    e.preventDefault();
    if (!low.trim() || !high.trim() || !Number.isFinite(Number(low)) || !Number.isFinite(Number(high)) || Number(low) > Number(high)) {
      setError('Enter a low and high temperature, with the low no higher than the high.');
      return;
    }
    setError('');
    onChange({ low_c: Number(low), high_c: Number(high), rain });
  }
  return <form className="today-manual" onSubmit={submit}>
    <div className="today-temperatures">
      <label className="field"><span>Low (°C)</span><input type="number" step="any" min="-60" max="60" required value={low} disabled={disabled} onChange={(e) => setLow(e.target.value)} /></label>
      <label className="field"><span>High (°C)</span><input type="number" step="any" min="-60" max="60" required value={high} disabled={disabled} onChange={(e) => setHigh(e.target.value)} /></label>
      <label className="today-rain"><input type="checkbox" checked={rain} disabled={disabled} onChange={(e) => setRain(e.target.checked)} /> Rain expected</label>
      <button className="btn" disabled={disabled}>Use these temperatures</button>
    </div>
    {error && <p className="form-error" role="alert">{error}</p>}
    <p className="small muted">Just for today. Or save your place in <Link to="/settings#s-place"
      onClick={() => requestAnimationFrame(() => document.getElementById('s-place')?.scrollIntoView())}>Where you are in Settings</Link>.</p>
    {hasForecast && <button className="btn btn-link" type="button" disabled={disabled} onClick={() => onChange({ low_c: undefined, high_c: undefined, rain: undefined })}>Use the forecast instead</button>}
  </form>;
}
