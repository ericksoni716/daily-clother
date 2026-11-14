import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { api, ApiError } from '../api';
import { CheckIcon, ChevronIcon, ChevronLeftIcon, HangerIcon, HistoryIcon, MoreIcon, SuitcaseIcon, WarnIcon } from '../components/Icons';
import { OutfitFigure } from '../components/OutfitFigure';
import { Button, buttonClass, Card, EmptyState, ItemThumb, Notice, PageHeader, SegmentedControl } from '../components/ui';
import { WhereYouAre } from '../components/WhereYouAre';
import { useTodayView, VIEW_OPTIONS, type TodayView } from '../figure';
import { label } from '../labels';
import { Link, navigate } from '../router';
import { useCloset } from '../store';
import {
  canDress, dayParts, joinWords, longDate, keptFor, loadChoice, moodLabel, MOODS, occasionLabel, OCCASIONS, outfitIds, parseTemp, placeLabel,
  saveChoice, sameOutfit, timeOf, whatToAddFirst, wornOrder, type Choice, type Outfit, type Place, type TodayAnswer,
  type TodayRequest, type TypedDay, type WornToday,
} from '../today';
import type { ItemSummary, Settings } from '../types';
import { localDay } from '../wears';
import { localDay as dayNow } from '../wears';
import { dismiss, loadDismissed, pendingQuestion, pieceName, questionFor, wornDay, type WornOutfit } from '../worn';
import { ItemDetail } from './ItemDetail';
import { OutfitPics, RateOutfit, refreshSaved, useAllItems } from './Worn';
import './Today.css';

const OFFLINE_TITLE = 'Needs Closet on your computer to be reachable';

type Phase =
  | { kind: 'loading' }
  | { kind: 'ready'; answer: TodayAnswer; savedAt: string | null }
  | { kind: 'needs-day'; message: string }
  | { kind: 'error'; message: string; offline: boolean };

interface Memory {
  profile: string;
  day: string;
  key: string;
  phase: Phase;
  index: number;
  buildAround: string | null;
  leaveOut: string[];
}

/** Kept while the app is open, so coming back from an item (or another tab) shows the same outfit without asking again. */
let memory: Memory | null = null;

function typedOf(r: TodayRequest): TypedDay | null {
  return r.low_c === undefined || r.high_c === undefined ? null : { day: '', low_c: r.low_c, high_c: r.high_c, rain: !!r.rain };
}

function requestFor(choice: Choice, buildAround: string | null, leaveOut: string[], typed: TypedDay | null, again: string | null = null): TodayRequest {
  const r: TodayRequest = { occasion: choice.occasion, mood: choice.mood };
  if (again) r.again = again;
  if (buildAround) r.build_around = buildAround;
  if (leaveOut.length) r.leave_out = leaveOut;
  if (typed) Object.assign(r, { low_c: typed.low_c, high_c: typed.high_c, rain: typed.rain });
  return r;
}

export function TodayScreen({ itemId, wide }: { itemId: string | null; wide: boolean }) {
  const { profile, items, loadItems, offline, upsert, toast } = useCloset();
  const today = localDay();
  const kept = useMemo(() => keptFor(profile), [profile]);
  const remembered = memory && memory.profile === profile && memory.day === today ? memory : null;

  const [choice, setChoice] = useState<Choice>(() => loadChoice());
  const [buildAround, setBuildAround] = useState<string | null>(remembered?.buildAround ?? null);
  const [leaveOut, setLeaveOut] = useState<string[]>(remembered?.leaveOut ?? []);
  const [typed, setTyped] = useState<TypedDay | null>(() => kept.typed(today));
  const [phase, setPhase] = useState<Phase>(remembered?.phase ?? { kind: 'loading' });
  const [asking, setAsking] = useState(false);
  const [index, setIndex] = useState(remembered?.index ?? 0);
  const [worn, setWorn] = useState<WornToday | null>(() => kept.worn(today));
  const [busy, setBusy] = useState(false);
  const [editDay, setEditDay] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [again, setAgain] = useState<string | null>(() => new URLSearchParams(window.location.search).get('again'));
  const [recent, setRecent] = useState<WornOutfit[] | null>(null);
  const [dismissed, setDismissed] = useState<string[]>(() => loadDismissed(profile));
  const [rated, setRated] = useState<WornOutfit | null>(null);

  useEffect(() => {
    if (window.location.search) navigate('/today', { replace: true });
  }, []);

  const loadRecent = useCallback(() => {
    // the same first page as the Worn screen, so both read (and refresh) one saved copy for offline
    void refreshSaved(profile).then((p) => setRecent(p ? p.outfits : null));
  }, [profile]);
  useEffect(() => {
    loadRecent();
  }, [loadRecent, profile]);
  const question = rated ?? pendingQuestion(recent, dismissed, dayNow());

  const request = useMemo(() => requestFor(choice, buildAround, leaveOut, typed, again), [choice, buildAround, leaveOut, typed, again]);
  const key = JSON.stringify(request);
  const requestRef = useRef(request);
  requestRef.current = request;
  // What was last asked: the same choices are not asked again when coming back to the screen.
  const answeredKey = remembered && remembered.phase.kind === 'ready' ? remembered.key : '';
  const asked = useRef<{ key: string; attempt: number }>({ key: answeredKey, attempt: 0 });
  // The choices the outfits on screen answer (kept in `memory` with them).
  const answered = useRef(answeredKey);

  useEffect(() => {
    if (items.active === null) void loadItems('active');
  }, [items.active, loadItems]);

  useEffect(() => {
    if (asked.current.key === key && asked.current.attempt === attempt) return;
    asked.current = { key, attempt };
    const req = requestRef.current;
    const ctrl = new AbortController();
    let done = false;
    setAsking(true);
    api.today(req, ctrl.signal).then(
      (answer) => {
        done = true;
        answered.current = key;
        kept.setOutfits({ day: localDay(), saved_at: new Date().toISOString(), request: req, answer });
        setPhase({ kind: 'ready', answer, savedAt: null });
        setIndex(0);
        setEditDay(false);
        setAsking(false);
      },
      (e) => {
        if ((e as Error)?.name === 'AbortError') return;
        done = true;
        const err = e as ApiError;
        setAsking(false);
        if (err.status === 0) {
          const saved = kept.outfits(localDay());
          if (saved) {
            const r = saved.request;
            const savedKey = JSON.stringify(requestFor({ occasion: r.occasion, mood: r.mood }, r.build_around ?? null, r.leave_out ?? [], typedOf(r)));
            asked.current = { key: savedKey, attempt };
            answered.current = savedKey;
            setPhase({ kind: 'ready', answer: saved.answer, savedAt: saved.saved_at });
            setChoice({ occasion: r.occasion, mood: r.mood });
            setBuildAround(r.build_around ?? null);
            setLeaveOut(r.leave_out ?? []);
            setIndex(0);
          } else {
            setPhase({ kind: 'error', offline: true, message: "You're offline, and no outfits were saved on this device today. They show here once Closet on your computer can be reached." });
          }
          return;
        }
        asked.current = { key: '', attempt };
        answered.current = '';
        if (err.status === 422 && req.low_c === undefined) setPhase({ kind: 'needs-day', message: err.message });
        else setPhase({ kind: 'error', message: err.message, offline: false });
      },
    );
    return () => {
      ctrl.abort();
      setAsking(false);
      // not answered: ask again when the screen shows these choices next
      if (!done) asked.current = { key: '', attempt: -1 };
    };
  }, [key, attempt, kept]);

  // Back online after showing a saved copy (or nothing): ask again.
  const showingSaved = (phase.kind === 'ready' && phase.savedAt !== null) || (phase.kind === 'error' && phase.offline);
  const wasOffline = useRef(offline);
  useEffect(() => {
    if (wasOffline.current && !offline && showingSaved) setAttempt((n) => n + 1);
    wasOffline.current = offline;
  }, [offline, showingSaved]);

  useEffect(() => {
    memory = { profile, day: today, key: answered.current, phase, index, buildAround, leaveOut };
  }, [profile, today, phase, index, buildAround, leaveOut]);

  const choose = (next: Choice) => {
    setChoice(next);
    saveChoice(next);
  };

  const byId = useMemo(() => new Map((items.active ?? []).map((i) => [i.id, i])), [items.active]);
  const allById = useAllItems();
  const nameOf = (id: string) => pieceName(allById.get(id), false, (c) => label('category', c));
  const locked = offline || (phase.kind === 'ready' && phase.savedAt !== null);

  async function wear(o: Outfit) {
    const ids = outfitIds(o.pieces);
    setBusy(true);
    try {
      if (worn && !sameOutfit(worn.ids, ids) && (worn.recorded.length || worn.outfit_id)) {
        const undone = await api.unwearMany(worn.recorded, worn.worn_on, worn.outfit_id);
        undone.items.forEach(upsert);
        kept.setWorn(null);
        setWorn(null);
      }
      const ctx = phase.kind === 'ready' ? phase.answer.context : null;
      const r = await api.wearMany(ids, {
        pieces: o.pieces, score: o.score, reasons: o.reasons, warnings: o.warnings,
        context: { low_c: ctx?.low_c ?? null, high_c: ctx?.high_c ?? null, rain: ctx?.rain ?? null, occasion: choice.occasion, mood: choice.mood },
      });
      r.items.forEach(upsert);
      const record: WornToday = { day: localDay(), worn_on: r.worn_on, ids, recorded: r.recorded ?? [], outfit: o, outfit_id: r.outfit?.id };
      loadRecent();
      kept.setWorn(record);
      setWorn(record);
      toast("Noted: you're wearing this today");
    } catch (e) {
      toast((e as Error).message, 'error');
    } finally {
      setBusy(false);
    }
  }

  async function undo() {
    if (!worn) return;
    setBusy(true);
    try {
      if (worn.recorded.length || worn.outfit_id) (await api.unwearMany(worn.recorded, worn.worn_on, worn.outfit_id)).items.forEach(upsert);
      loadRecent();
      kept.setWorn(null);
      setWorn(null);
      toast('Wear undone');
    } catch (e) {
      toast((e as Error).message, 'error');
    } finally {
      setBusy(false);
    }
  }

  const pieceActions: PieceActions = {
    locked,
    buildAround,
    leaveOut: (id) => {
      setLeaveOut((l) => (l.includes(id) ? l : [...l, id]));
      if (buildAround === id) setBuildAround(null);
    },
    startFrom: (id) => {
      setBuildAround(buildAround === id ? null : id);
      setLeaveOut((l) => l.filter((x) => x !== id));
    },
  };

  if (itemId && !wide) {
    return (
      <div className="today-item">
        <div className="detail-top">
          <Link to="/today" className="btn btn-ghost back-link"><ChevronLeftIcon /> Today</Link>
        </div>
        <ItemDetail key={itemId} id={itemId} status="active" inPanel />
      </div>
    );
  }

  const header = (
    <PageHeader className="today-header" title="Today" titleId="today-title" count={longDate(today)}
      secondary={(
        <div className="today-links">
          <Link to="/today/worn" className={buttonClass({ small: true })}><HistoryIcon /> Worn</Link>
          <Link to="/trips" className={buttonClass({ small: true })}><SuitcaseIcon /> Trips</Link>
        </div>
      )} />
  );

  // An empty closet: nothing to dress, so no weather or choices either, only what to add.
  if (items.active !== null && !canDress(items.active)) {
    return (
      <div className="today">
        {header}
        <EmptyState big icon={<HangerIcon />} className="today-empty" testId="today-empty"
          title="Add a top, something for your legs and shoes, and Today can dress you"
          action={offline
            ? <span className="btn btn-primary is-disabled" aria-disabled="true" title={OFFLINE_TITLE}>Add clothes</span>
            : <Link to="/add" className="btn btn-primary">Add clothes</Link>}>
          <p className="muted" data-testid="add-first">Still to add: {joinWords(whatToAddFirst(items.active))}.</p>
        </EmptyState>
      </div>
    );
  }

  const ctx = phase.kind === 'ready' ? phase.answer.context : null;
  const setDay = (t: Omit<TypedDay, 'day'> | null) => {
    const value = t ? { ...t, day: localDay() } : null;
    kept.setTyped(value);
    setTyped(value);
    setEditDay(false);
  };

  const main = (
    <div className="today" aria-busy={asking || phase.kind === 'loading'}>
      {header}

      <DayLine phase={phase} editing={editDay} locked={locked} onEdit={() => setEditDay(!editDay)} />
      {(editDay || phase.kind === 'needs-day') && (
        <DayPanel phase={phase} typed={typed} locked={locked} offline={offline} toast={toast}
          onTyped={setDay}
          onClose={phase.kind === 'needs-day' ? undefined : () => setEditDay(false)}
          onPlace={() => {
            // a place chosen now wins over temperatures typed earlier today
            kept.setTyped(null);
            setTyped(null);
            setEditDay(false);
            setAttempt((n) => n + 1);
          }} />
      )}

      <div className="today-choices chips-scroll">
        <ChoiceGroup title="Occasion" options={OCCASIONS} value={choice.occasion} labelOf={occasionLabel} locked={locked}
          onChange={(occasion) => choose({ ...choice, occasion })} />
        <span className="today-choices-sep" aria-hidden="true" />
        <ChoiceGroup title="Mood" options={MOODS} value={choice.mood} labelOf={moodLabel} locked={locked}
          onChange={(mood) => choose({ ...choice, mood })} />
      </div>

      {ctx?.source === 'mild' && !editDay && (
        <Notice tone="warning" icon={<WarnIcon />} className="today-no-weather" role="status" testId="no-weather"
          action={(
            <>
              <Button small disabled={locked || asking} onClick={() => setAttempt((n) => n + 1)}>Try again</Button>
              <Button small disabled={locked} onClick={() => setEditDay(true)}>Type temperatures</Button>
            </>
          )}>
          <p><strong>The weather could not be fetched</strong>, so these outfits are for a mild day.</p>
          {ctx.message && <p className="today-no-weather-why">{ctx.message}</p>}
        </Notice>
      )}

      {again && (
        <div className="chips today-changes" role="group" aria-label="Wearing again">
          <button className="chip chip-change" disabled={locked} title={locked ? OFFLINE_TITLE : undefined} onClick={() => setAgain(null)}>
            Starting from an outfit you wore{phase.kind === 'ready' && phase.answer.context.again ? ` ${wornDay(phase.answer.context.again)}` : ''} <span aria-hidden="true">×</span>
          </button>
          {phase.kind === 'ready' && (phase.answer.context.again?.unavailable.length ?? 0) > 0 && (
            <span className="muted">Not clean or not available today: {joinWords(phase.answer.context.again!.unavailable.map(nameOf))}.</span>
          )}
        </div>
      )}

      {(buildAround || leaveOut.length > 0) && (
        <div className="chips today-changes" role="group" aria-label="Your changes">
          {buildAround && (
            <button className="chip chip-change" disabled={locked} title={locked ? OFFLINE_TITLE : undefined}
              aria-label={`Stop building around ${nameOf(buildAround)}`} onClick={() => setBuildAround(null)}>
              Built around {nameOf(buildAround)} <span aria-hidden="true">×</span>
            </button>
          )}
          {leaveOut.map((id) => (
            <button key={id} className="chip chip-change" disabled={locked} title={locked ? OFFLINE_TITLE : undefined}
              aria-label={`Put back ${nameOf(id)}`} onClick={() => setLeaveOut((l) => l.filter((x) => x !== id))}>
              Without {nameOf(id)} <span aria-hidden="true">×</span>
            </button>
          ))}
          {(buildAround ? 1 : 0) + leaveOut.length > 1 && (
            <button className="btn btn-link" disabled={locked} onClick={() => { setBuildAround(null); setLeaveOut([]); }}>Clear all</button>
          )}
        </div>
      )}

      {question && (
        <Card as="section" className="worn-question" aria-label={questionFor(question, dayNow())} data-testid="worn-question">
          <div className="worn-question-head">
            <h2>{questionFor(question, dayNow())}</h2>
            <OutfitPics outfit={question} byId={allById} linked={false} />
            <button className="btn btn-icon btn-ghost worn-question-close" aria-label="Not now"
              onClick={() => { setDismissed(dismiss(profile, question.id)); setRated(null); }}>×</button>
          </div>
          <RateOutfit outfit={question} offline={offline} compact onRated={(o) => {
            setRated(o);
            setRecent((l) => (l ?? []).map((x) => (x.id === o.id ? o : x)));
            void refreshSaved(profile);
          }} />
          {rated && (
            <div className="row">
              <button className="btn btn-small" onClick={() => { setDismissed(dismiss(profile, rated.id)); setRated(null); }}>Done</button>
            </div>
          )}
        </Card>
      )}

      {worn && phase.kind === 'ready' && !phase.answer.outfits.some((o) => sameOutfit(outfitIds(o.pieces), worn.ids)) && (
        <div className="notice today-worn-note" role="status">
          <CheckIcon />
          <div>
            <p><strong>You're wearing this today:</strong> {joinWords(worn.ids.map(nameOf))}.</p>
            <button className="btn btn-small" disabled={busy || locked} title={locked ? OFFLINE_TITLE : undefined} onClick={() => void undo()}>Undo</button>
          </div>
        </div>
      )}

      <Body phase={phase} asking={asking} index={index} setIndex={setIndex} byId={byId} worn={worn} busy={busy}
        actions={pieceActions} items={items.active} onWear={wear} onUndo={undo} offline={offline}
        changed={!!buildAround || leaveOut.length > 0}
        onClear={() => { setBuildAround(null); setLeaveOut([]); }}
        onRetry={() => setAttempt((n) => n + 1)} />
    </div>
  );

  if (!wide) return main;
  return (
    <div className={itemId ? 'master-detail today-with-item' : undefined}>
      {main}
      {itemId && (
        <aside className="detail-panel" aria-label="Item details">
          <div className="today-panel-top">
            <Link to="/today" className="btn btn-ghost btn-small back-link"><ChevronLeftIcon /> Back to the outfit</Link>
          </div>
          <ItemDetail key={itemId} id={itemId} status="active" inPanel />
        </aside>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ the day

function DayLine({ phase, editing, locked, onEdit }: { phase: Phase; editing: boolean; locked: boolean; onEdit(): void }) {
  const c = phase.kind === 'ready' ? phase.answer.context : null;
  return (
    <section className="today-day" aria-label="The day">
      <p className="today-day-line" data-testid="day-line" title={c?.place ?? undefined}>
        {c ? dayParts(c).map((part, i) => <span key={i}>{part}</span>)
          : <span className="muted">{phase.kind === 'loading' ? 'Looking up the weather…' : 'The weather'}</span>}
        {phase.kind !== 'needs-day' && (
          <span className="today-day-change">
            <button className="btn btn-link" aria-expanded={editing} aria-controls="today-day-panel" disabled={locked}
              title={locked ? OFFLINE_TITLE : undefined} onClick={onEdit}>
              Change
            </button>
          </span>
        )}
      </p>
      {c?.old && <p className="today-day-old" role="note">{c.message || 'This is an older forecast: the weather service could not be reached.'}</p>}
    </section>
  );
}

/** Behind "Change": where you are (search or the browser's location), or today's temperatures typed by hand. */
function DayPanel({ phase, typed, locked, offline, toast, onTyped, onClose, onPlace }: {
  phase: Phase; typed: TypedDay | null; locked: boolean; offline: boolean; toast: (m: string, k?: 'ok' | 'error') => void;
  onTyped(t: Omit<TypedDay, 'day'> | null): void; onClose?: () => void; onPlace(): void;
}) {
  const [settings, setSettings] = useState<Settings | null>(null);
  useEffect(() => {
    if (offline) return;
    let current = true;
    api.settings().then((s) => current && setSettings(s), () => undefined);
    return () => {
      current = false;
    };
  }, [offline]);

  return (
    <Card as="section" className="today-day-panel" id="today-day-panel" aria-labelledby="day-title">
      {phase.kind === 'needs-day' && <p className="today-day-why">{phase.message}</p>}
      <h2 id="day-title">Where are you?</h2>
      <WhereYouAre inline place={settings ? settings.place : undefined} home={settings?.home_place} offline={offline} toast={toast}
        onChange={(s) => {
          setSettings(s);
          onPlace();
        }} />
      <h3 className="today-typed-title">Or type today's temperatures</h3>
      <TypedForm typed={typed} locked={locked} onTyped={onTyped} onCancel={onClose} />
      {typed && (
        <p className="hint">
          You typed today's temperatures. <button className="btn btn-link" disabled={locked} onClick={() => onTyped(null)}>Use the forecast again</button>
        </p>
      )}
    </Card>
  );
}

function TypedForm({ typed, locked, onTyped, onCancel }: {
  typed: TypedDay | null; locked: boolean; onTyped(t: Omit<TypedDay, 'day'>): void; onCancel?: () => void;
}) {
  const [low, setLow] = useState(typed ? String(typed.low_c) : '');
  const [high, setHigh] = useState(typed ? String(typed.high_c) : '');
  const [rain, setRain] = useState(typed?.rain ?? false);
  const [error, setError] = useState<string | null>(null);

  function submit(e: FormEvent) {
    e.preventDefault();
    const l = parseTemp(low);
    const h = parseTemp(high.trim() ? high : low);
    if (l === null || h === null) return setError('Type each temperature as a number of degrees, like 8 or -2.');
    if (l > h) return setError('The low is above the high.');
    setError(null);
    onTyped({ low_c: l, high_c: h, rain });
  }

  return (
    <form className="today-typed" onSubmit={submit} noValidate>
      <label className="field">
        <span>Low °C</span>
        <input inputMode="decimal" value={low} onChange={(e) => setLow(e.target.value)} placeholder="e.g. 4" disabled={locked} />
      </label>
      <label className="field">
        <span>High °C</span>
        <input inputMode="decimal" value={high} onChange={(e) => setHigh(e.target.value)} placeholder="e.g. 11" disabled={locked} />
      </label>
      <label className="today-rain">
        <input type="checkbox" checked={rain} onChange={(e) => setRain(e.target.checked)} disabled={locked} />
        <span>Rain expected</span>
      </label>
      <div className="row today-typed-actions">
        <button className="btn btn-primary" type="submit" disabled={locked || !low.trim()} title={locked ? OFFLINE_TITLE : undefined}>Dress me for this</button>
        {onCancel && <button className="btn btn-ghost" type="button" onClick={onCancel}>Close</button>}
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
    </form>
  );
}

function ChoiceGroup({ title, options, value, labelOf, locked, onChange }: {
  title: string; options: readonly string[]; value: string; labelOf(v: string): string; locked: boolean;
  onChange(v: string): void;
}) {
  return (
    <div className="today-choice" role="group" aria-label={title}>
      {options.map((opt) => (
        <button key={opt} type="button" className={`chip${value === opt ? ' is-on' : ''}`} aria-pressed={value === opt}
          disabled={locked} title={locked ? OFFLINE_TITLE : undefined} onClick={() => value !== opt && onChange(opt)}>
          {labelOf(opt)}
        </button>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ the outfits

interface PieceActions {
  locked: boolean;
  buildAround: string | null;
  leaveOut(id: string): void;
  startFrom(id: string): void;
}

interface BodyProps {
  phase: Phase;
  asking: boolean;
  index: number;
  setIndex(i: number): void;
  byId: Map<string, ItemSummary>;
  items: ItemSummary[] | null;
  worn: WornToday | null;
  busy: boolean;
  offline: boolean;
  changed: boolean;
  actions: PieceActions;
  onWear(o: Outfit): void;
  onUndo(): void;
  onClear(): void;
  onRetry(): void;
}

function Body(props: BodyProps) {
  const { phase, asking, items, offline, changed, onClear, onRetry } = props;
  if (phase.kind === 'loading') {
    return (
      <div className="today-loading" role="status">
        <div className="today-pieces" aria-hidden="true">{Array.from({ length: 5 }, (_, i) => <div key={i} className="tile-skeleton" />)}</div>
        <p className="muted"><span className="spinner" aria-hidden="true" /> Choosing today's outfits…</p>
      </div>
    );
  }
  if (phase.kind === 'needs-day') return null;
  if (phase.kind === 'error') {
    return (
      <div className={phase.offline ? 'notice' : 'form-error today-error'} role="alert">
        <p>{phase.offline ? phase.message : `Couldn't choose today's outfits: ${phase.message}`}</p>
        {!phase.offline && (
          <div className="row">
            <button className="btn btn-small" onClick={onRetry}>Try again</button>
            {changed && <button className="btn btn-small" onClick={onClear}>Clear your changes</button>}
          </div>
        )}
      </div>
    );
  }
  const { answer, savedAt } = phase;
  if (answer.outfits.length === 0) {
    const toAdd = whatToAddFirst(items);
    return (
      <div className="today-missing" aria-busy={asking}>
        <div className="empty-art"><HangerIcon /></div>
        <p className="empty-title">No outfit today yet</p>
        <ul className="today-missing-list" aria-label="Why not">
          {answer.missing.map((m) => <li key={m}>{m}</li>)}
        </ul>
        {items && toAdd.length > 0 && (
          <p className="muted" data-testid="add-first">Add first: {joinWords(toAdd)}.</p>
        )}
        <div className="row today-missing-actions">
          {offline
            ? <span className="btn btn-primary is-disabled" aria-disabled="true" title={OFFLINE_TITLE}>Add clothes</span>
            : <Link to="/add" className="btn btn-primary">Add clothes</Link>}
          {changed && <button className="btn" disabled={offline} onClick={onClear}>Clear your changes</button>}
        </div>
      </div>
    );
  }
  return (
    <>
      {savedAt && (
        <Notice as="p" tone="warning" className="today-saved" role="status" icon={<WarnIcon />}>
          <span>Saved earlier today{timeOf(savedAt) ? `, at ${timeOf(savedAt)}` : ''}. You're offline, so these can't be changed or worn until Closet on your computer can be reached.</span>
        </Notice>
      )}
      <Carousel {...props} outfits={answer.outfits} />
    </>
  );
}

function Carousel({ outfits, index, setIndex, asking, ...rest }: BodyProps & { outfits: Outfit[] }) {
  const track = useRef<HTMLDivElement>(null);
  const count = outfits.length;
  const current = Math.min(index, count - 1);

  // Show the remembered outfit straight away (coming back from an item), without animating there.
  useLayoutEffect(() => {
    const el = track.current;
    if (el) el.scrollLeft = current * el.clientWidth;
    // only when the list of outfits changes or the carousel appears
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [outfits]);

  const go = useCallback((i: number) => {
    const el = track.current;
    const next = Math.max(0, Math.min(count - 1, i));
    setIndex(next);
    if (!el) return;
    const smooth = !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    el.scrollTo({ left: next * el.clientWidth, behavior: smooth ? 'smooth' : 'auto' });
  }, [count, setIndex]);

  const onScroll = () => {
    const el = track.current;
    if (!el || !el.clientWidth) return;
    const i = Math.round(el.scrollLeft / el.clientWidth);
    if (i !== current && i >= 0 && i < count) setIndex(i);
  };

  const [view, setView] = useTodayView();

  return (
    <section className={`today-outfits${asking ? ' is-asking' : ''}`} aria-label="Today's outfits" aria-roledescription="carousel">
      <div className="today-outfits-head">
        <h2 aria-live="polite">
          {current === 0 ? 'Best for today' : `Another idea`}
          <span className="count"> · {count === 1 ? 'the only outfit' : `${current + 1} of ${count}`}</span>
        </h2>
        {asking && <span className="today-asking muted"><span className="spinner" aria-hidden="true" /><span className="visually-hidden">Asking again…</span></span>}
        <SegmentedControl label="Show the outfit" small className="today-view" value={view}
          options={VIEW_OPTIONS} onChange={setView} />
      </div>

      <div className="today-track" ref={track} onScroll={onScroll} tabIndex={-1}>
        {outfits.map((o, i) => (
          <article key={outfitIds(o.pieces).join(',')} className="today-slide" aria-roledescription="slide"
            aria-label={`Outfit ${i + 1} of ${count}`} aria-hidden={i !== current} inert={i !== current}
            data-testid={i === current ? 'current-outfit' : undefined}>
            <OutfitCard outfit={o} view={view} {...rest} />
          </article>
        ))}
      </div>

      {count > 1 && (
        <div className="today-nav">
          <button className="btn btn-icon today-arrow" aria-label="Previous outfit" disabled={current === 0} onClick={() => go(current - 1)}><ChevronLeftIcon /></button>
          <div className="today-thumbs" role="group" aria-label="Choose an outfit">
            {outfits.map((o, i) => (
              <button key={i} className={`today-thumb${i === current ? ' is-on' : ''}`} aria-label={`Outfit ${i + 1}`}
                aria-pressed={i === current} onClick={() => go(i)}>
                <span className="today-thumb-pics" aria-hidden="true">
                  {wornOrder(o.pieces).slice(0, 4).map((p) => <Pic key={p.id} item={rest.byId.get(p.id)} />)}
                </span>
                <span className="today-dot" aria-hidden="true" />
              </button>
            ))}
          </div>
          <button className="btn btn-icon today-arrow" aria-label="Next outfit" disabled={current === count - 1} onClick={() => go(current + 1)}><ChevronIcon /></button>
        </div>
      )}
    </section>
  );
}

function OutfitCard({ outfit, view, byId, worn, busy, actions, onWear, onUndo }: Omit<BodyProps, 'phase' | 'asking' | 'index' | 'setIndex'> & {
  outfit: Outfit; view: TodayView;
}) {
  const ids = outfitIds(outfit.pieces);
  const isWorn = !!worn && sameOutfit(worn.ids, ids);
  const locked = actions.locked;
  const title = locked ? OFFLINE_TITLE : undefined;
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const menuItem = menuFor ? byId.get(menuFor) : undefined;
  useEffect(() => {
    if (!menuFor) return;
    const close = (e: KeyboardEvent) => e.key === 'Escape' && setMenuFor(null);
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, [menuFor]);
  return (
    <Card className="today-card">
      <div className="today-card-pieces">
        {view === 'worn' && (
          <OutfitFigure pieces={outfit.pieces} alt={`The outfit as worn: ${joinWords(wornOrder(outfit.pieces).map((p) => itemName(byId.get(p.id))))}`}
            version={ids.map((id) => byId.get(id)?.illustration_url ?? '').join(' ')} />
        )}
        <ul className="today-pieces" hidden={view === 'worn'} aria-label="Pieces, in the order they are put on">
          {wornOrder(outfit.pieces).map((p) => (
            <li key={p.id}>
              <Piece id={p.id} place={p.place} item={byId.get(p.id)} isBase={actions.buildAround === p.id}
                open={menuFor === p.id} onMore={() => setMenuFor(menuFor === p.id ? null : p.id)} />
            </li>
          ))}
        </ul>
        {menuFor && view === 'pieces' && (
          <div className="today-piece-menu" role="group" aria-label={`Choices for ${itemName(menuItem)}`}>
            <p><strong>{itemName(menuItem)}</strong></p>
            <div className="row">
              <button className="btn btn-small" disabled={locked} title={title} onClick={() => { setMenuFor(null); actions.leaveOut(menuFor); }}>Not this piece</button>
              <button className="btn btn-small" disabled={locked} title={title} onClick={() => { setMenuFor(null); actions.startFrom(menuFor); }}>
                {actions.buildAround === menuFor ? 'Stop starting from it' : 'Start from this piece'}
              </button>
              <button className="btn btn-small btn-ghost" onClick={() => setMenuFor(null)}>Close</button>
            </div>
          </div>
        )}
      </div>

      <div className="today-wear">
        {isWorn ? (
          <>
            <p className="today-worn" data-testid="worn-today"><CheckIcon /> You're wearing this today</p>
            <button className="btn" disabled={busy || locked} title={title} onClick={() => onUndo()}>Undo</button>
          </>
        ) : (
          <button className="btn btn-primary btn-block today-wear-button" disabled={busy || locked} title={title} onClick={() => onWear(outfit)}>
            {worn ? 'Wear this instead' : "I'm wearing this"}
          </button>
        )}
      </div>

      <div className="today-card-why">
        {outfit.warnings.length > 0 && (
          <div className="today-warnings" role="note" aria-label="Be aware">
            <WarnIcon />
            <ul>{outfit.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
          </div>
        )}
        <h3 className="chip-group-title">Why this works</h3>
        <ul className="today-reasons" aria-label="Why this works">
          {outfit.reasons.map((r) => <li key={r}><CheckIcon /><span>{r}</span></li>)}
        </ul>
        <p className="hint today-hint">{view === 'worn' ? 'Drawn as worn, from the pieces\' own drawings. Choose Pieces to see one, leave it out or build around it.' : (
          <>Tap a piece to see it. Its <MoreIcon className="inline-icon" /> button leaves it out or builds every outfit around it.</>
        )}</p>
      </div>
    </Card>
  );
}

function Piece({ id, place, item, isBase, open, onMore }: {
  id: string; place: Place; item: ItemSummary | undefined; isBase: boolean; open: boolean; onMore(): void;
}) {
  const name = itemName(item);
  return (
    <div className={`today-piece${isBase ? ' is-base' : ''}${open ? ' is-open' : ''}`}>
      <Link to={`/today/item/${encodeURIComponent(id)}`} className="today-piece-link" data-testid="piece">
        <ItemThumb className="today-piece-card" picture={<Pic item={item} />} />
        <span className="today-piece-place">{isBase ? 'Built around' : placeLabel(place)}</span>
        <span className="today-piece-name">{name}</span>
      </Link>
      <button className="today-piece-more" aria-label={`Choices for ${name}`} aria-expanded={open} onClick={onMore}>
        <MoreIcon />
      </button>
    </div>
  );
}

function Pic({ item }: { item: ItemSummary | undefined }): ReactNode {
  const alt = itemName(item);
  if (!item) return <span className="pic-placeholder" role="img" aria-label={alt}><HangerIcon /></span>;
  if (item.cutout_state === 'ready' && item.thumb_url) return <img className="pic-cutout" src={item.thumb_url} alt={alt} />;
  if (item.illustration_url) return <img className="pic-illustration" src={item.illustration_url} alt={alt} />;
  if (item.thumb_url) return <img className="pic-photo" src={item.thumb_url} alt={alt} />;
  return <span className="pic-placeholder" role="img" aria-label={alt}><HangerIcon /></span>;
}

function itemName(item: ItemSummary | undefined): string {
  if (!item) return 'An item';
  return item.name || label('category', item.category) || 'An item';
}
