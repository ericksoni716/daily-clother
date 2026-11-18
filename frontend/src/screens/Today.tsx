import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { api, ApiError } from '../api';
import { CheckIcon, ChevronIcon, ChevronLeftIcon, HangerIcon, HistoryIcon, MoreIcon, SuitcaseIcon, WarnIcon } from '../components/Icons';
import { OutfitFigure } from '../components/OutfitFigure';
import { Button, buttonClass, Card, EmptyState, ItemThumb, Notice, PageHeader, SegmentedControl } from '../components/ui';
import { WhereYouAre } from '../components/WhereYouAre';
import { figureVersion, useTodayView, VIEW_OPTIONS, type TodayView } from '../figure';
import { label } from '../labels';
import { Link, navigate } from '../router';
import { useCloset } from '../store';
import {
  canDress, canSay, chosenBy, dayParts, joinWords, longDate, keptFor, loadChoice, lookingAt, MAX_SAY, moodLabel, MOODS, occasionLabel, OCCASIONS, outfitIds, parseTemp,
  placeLabel, rememberWords, sameOutfit, sameOutfits, savedLine, shortDate, saveChoice, stylistView, STYLIST_SLOW_S, talkOf, timeOf, waitingLine, whatToAddFirst, withThing,
  wornNow, wornOrder, type Choice, type DayAnswer, type DayNote, type Outfit, type Place, type RememberThing, type StylistState, type TalkTurn, type TodayAnswer,
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
  const [today, setToday] = useState(localDay);
  const kept = useMemo(() => keptFor(profile), [profile]);
  const remembered = memory && memory.profile === profile && memory.day === today ? memory : null;

  const [choice, setChoice] = useState<Choice>(() => loadChoice());
  const [buildAround, setBuildAround] = useState<string | null>(remembered?.buildAround ?? null);
  const [leaveOut, setLeaveOut] = useState<string[]>(remembered?.leaveOut ?? []);
  const [typedOnDay, setTyped] = useState<TypedDay | null>(() => kept.typed(today));
  const typed = typedOnDay?.day === today ? typedOnDay : null;
  const [phase, setPhase] = useState<Phase>(remembered?.phase ?? { kind: 'loading' });
  const [asking, setAsking] = useState(false);
  const [index, setIndex] = useState(remembered?.index ?? 0);
  const [wornOnDay, setWorn] = useState<WornToday | null>(() => kept.worn(today));
  const [busy, setBusy] = useState(false);
  const [editDay, setEditDay] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [again, setAgain] = useState<string | null>(() => new URLSearchParams(window.location.search).get('again'));
  const [recent, setRecent] = useState<WornOutfit[] | null>(null);
  const [dismissed, setDismissed] = useState<string[]>(() => loadDismissed(profile));
  const [rated, setRated] = useState<WornOutfit | null>(null);
  const [loadingItems, setLoadingItems] = useState(items.active === null);
  // Claude choosing: the question whose rules' outfits are shown meanwhile, and whether the owner chose one of them
  // while Claude was still choosing (then the waiting card stays away for the rest of this visit)
  const [meanwhileFor, setMeanwhileFor] = useState<string | null>(null);
  const [choseOwn, setChoseOwn] = useState(false);
  // "Ask Claude again": the next request carries ask_again, once (never kept with the request or in the saved copy)
  const askAgain = useRef(false);
  // The next answer is the one after Claude answered a message: it keeps the outfit in front of the owner when the
  // outfits did not change, and shows the first when they did
  const followUp = useRef(false);
  const shown = useRef<Outfit[] | null>(null);
  shown.current = phase.kind === 'ready' ? phase.answer.outfits : null;

  useEffect(() => {
    const updateDay = () => setToday(localDay());
    const timer = window.setInterval(updateDay, 60_000);
    window.addEventListener('focus', updateDay);
    document.addEventListener('visibilitychange', updateDay);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener('focus', updateDay);
      document.removeEventListener('visibilitychange', updateDay);
    };
  }, []);

  useEffect(() => {
    if (window.location.search) navigate('/today', { replace: true });
  }, []);

  const [recentAt, setRecentAt] = useState<number | null>(null);
  const loadRecent = useCallback(() => {
    // the same first page as the Worn screen, so both read (and refresh) one saved copy for offline
    const started = Date.now();
    void refreshSaved(profile).then((p) => {
      setRecent(p ? p.outfits : null);
      setRecentAt(p && navigator.onLine !== false ? started : null);
    });
  }, [profile]);
  useEffect(() => {
    loadRecent();
  }, [loadRecent, profile]);
  const question = rated ?? pendingQuestion(recent, dismissed, dayNow());
  // what is worn today: this device's memory, put right by the server's list (another device, the Worn screen)
  const worn = useMemo(() => wornNow(wornOnDay?.day === today ? wornOnDay : null, offline ? null : recent, recentAt, today),
    [wornOnDay, recent, recentAt, today, offline]);

  const request = useMemo(() => requestFor(choice, buildAround, leaveOut, typed, again), [choice, buildAround, leaveOut, typed, again]);
  // Returning from an item keeps the outfit only if its pieces still have the same places and availability.
  const closetKey = useMemo(() => items.active === null ? null : JSON.stringify(items.active.map(
    (i) => JSON.stringify([i.id, i.category, i.status, i.laundry, i.rating]),
  ).sort()), [items.active]);
  const key = JSON.stringify([today, request, closetKey]);
  const requestRef = useRef(request);
  requestRef.current = request;
  // What was last asked: the same choices are not asked again when coming back to the screen.
  const answeredKey = remembered && remembered.phase.kind === 'ready' ? remembered.key : '';
  const asked = useRef<{ key: string; attempt: number }>({ key: answeredKey, attempt: 0 });
  // The choices the outfits on screen answer (kept in `memory` with them).
  const answered = useRef(answeredKey);

  useEffect(() => {
    if (items.active === null) void loadItems('active').finally(() => setLoadingItems(false));
  }, [items.active, loadItems]);

  useEffect(() => {
    if (loadingItems) return;
    if (asked.current.key === key && asked.current.attempt === attempt) return;
    asked.current = { key, attempt };
    const req = requestRef.current;
    const ctrl = new AbortController();
    let done = false;
    setAsking(true);
    api.today(askAgain.current ? { ...req, ask_again: true } : req, ctrl.signal).then(
      (answer) => {
        done = true;
        askAgain.current = false;
        answered.current = key;
        kept.setOutfits({ day: localDay(), saved_at: new Date().toISOString(), request: req, answer });
        const keepPlace = followUp.current && !!shown.current && sameOutfits(shown.current, answer.outfits);
        followUp.current = false;
        setPhase({ kind: 'ready', answer, savedAt: null });
        if (!keepPlace) setIndex(0);
        setEditDay(false);
        setAsking(false);
      },
      (e) => {
        if ((e as Error)?.name === 'AbortError') return;
        done = true;
        askAgain.current = false;
        followUp.current = false;
        const err = e as ApiError;
        setAsking(false);
        if (err.status === 0) {
          const saved = kept.outfits(localDay());
          if (saved) {
            const r = saved.request;
            const savedKey = JSON.stringify([today, requestFor({ occasion: r.occasion, mood: r.mood }, r.build_around ?? null, r.leave_out ?? [], typedOf(r)), closetKey]);
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
  }, [key, attempt, kept, closetKey, today, loadingItems]);

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

  // While Claude is choosing, or answering a message of the owner's, ask every 2 seconds how it stands (cheap); once
  // it is done, ask Today again with the same choices so Claude's outfits (or the rules', with why) and its answer
  // arrive by themselves.
  const stylist = phase.kind === 'ready' ? phase.answer.context.stylist ?? null : null;
  const claudeView = phase.kind === 'ready' ? stylistView(stylist, phase.savedAt !== null) : 'none';
  const { talk, answering } = talkOf(stylist);
  const waitingFor = offline ? null
    : claudeView === 'waiting' ? (!choseOwn && stylist?.id ? stylist.id : null)
      : claudeView === 'read' && phase.kind === 'ready' && phase.savedAt === null ? answering : null;
  const talking = claudeView === 'read';
  const waitingOn = useMemo(() => (waitingFor ? { id: waitingFor, talking, phase } : null), [waitingFor, talking, phase]);
  const gone = useRef(new Set<string>());
  useEffect(() => {
    if (!waitingOn) return;
    const { id } = waitingOn;
    const ctrl = new AbortController();
    let stopped = false;
    const stop = () => {
      stopped = true;
      window.clearInterval(timer);
    };
    const timer = window.setInterval(() => {
      if (stopped) return;
      api.styleAnswer(id, ctrl.signal).then(
        (a) => {
          if (stopped || a.state === 'working') return;
          stop();
          if (waitingOn.talking) followUp.current = true;
          setAttempt((n) => n + 1);
        },
        (e) => {
          if (stopped || (e as Error)?.name === 'AbortError') return;
          stop();
          // the question is gone (the closet changed, the program restarted): ask Today again, once
          if ((e as ApiError).status === 404 && !gone.current.has(id)) {
            gone.current.add(id);
            if (waitingOn.talking) followUp.current = true;
            setAttempt((n) => n + 1);
          }
          // anything else (offline, a network error): stop quietly; the outfits shown stand
        },
      );
    }, 2000);
    return () => {
      stop();
      ctrl.abort();
    };
  }, [waitingOn]);

  const choose = (next: Choice) => {
    setChoice(next);
    saveChoice(next);
  };

  const byId = useMemo(() => new Map((items.active ?? []).map((i) => [i.id, i])), [items.active]);
  const allById = useAllItems();
  const nameOf = (id: string) => pieceName(allById.get(id), false, (c) => label('category', c));
  const locked = offline || (phase.kind === 'ready' && phase.savedAt !== null);

  /** Sends the owner's message about the outfits on the page; gives back why it was not sent, or null. */
  async function say(text: string): Promise<string | null> {
    if (phase.kind !== 'ready') return null;
    const req = requestRef.current;
    // the carousel shows one outfit at a time: the one at its place is the one in front of the owner
    const looking = lookingAt(index, phase.answer.outfits.length);
    try {
      const answer = await api.today({ ...req, say: text, ...(looking === null ? {} : { looking_at: looking }) });
      kept.setOutfits({ day: localDay(), saved_at: new Date().toISOString(), request: req, answer });
      setPhase({ kind: 'ready', answer, savedAt: null });
      return null;
    } catch (e) {
      return (e as Error).message || "Your message wasn't sent. Try again.";
    }
  }

  /** Keeps (or not) a thing Claude offered to remember; gives back why it could not, or null. */
  async function settle(turnId: string, at: number, save: boolean): Promise<string | null> {
    try {
      const thing = await api.remember(turnId, at, save);
      setPhase((p) => (p.kind === 'ready' ? { ...p, answer: withThing(p.answer, turnId, at, thing) } : p));
      const saved = kept.outfits(localDay());
      if (saved) kept.setOutfits({ ...saved, answer: withThing(saved.answer, turnId, at, thing) });
      return null;
    } catch (e) {
      return (e as Error).message || 'That could not be saved. Try again.';
    }
  }

  async function wear(o: Outfit) {
    // one of the rules' outfits worn while Claude was still choosing: that is the owner's choice for today
    if (claudeView === 'waiting') setChoseOwn(true);
    const day = localDay();
    setToday(day);
    const ids = outfitIds(o.pieces);
    setBusy(true);
    try {
      if (worn && worn.day === day && !sameOutfit(worn.ids, ids) && (worn.recorded.length || worn.outfit_id)) {
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
      setToday(localDay());
      const record: WornToday = { day, worn_on: r.worn_on, ids, recorded: r.recorded ?? [], outfit: o, outfit_id: r.outfit?.id, at: Date.now() };
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
    if (worn.day !== localDay()) {
      setToday(localDay());
      return;
    }
    setBusy(true);
    try {
      if (worn.recorded.length || worn.outfit_id) (await api.unwearMany(worn.recorded, worn.worn_on, worn.outfit_id)).items.forEach(upsert);
      const gone = worn.outfit_id;
      setRecent((l) => l && l.filter((o) => o.id !== gone));
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
    <PageHeader className="today-header" title="Today" titleId="today-title" count={<><span className="date-long">{longDate(today)}</span><span className="date-short">{shortDate(today)}</span></>}
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
          onNote={(answer) => {
            // a place in the note wins over temperatures typed earlier today, as a place chosen here does
            if (answer.note?.active && answer.note.place) {
              kept.setTyped(null);
              setTyped(null);
            }
            const occasion = answer.note?.active ? answer.note.occasion : null;
            if (occasion && (OCCASIONS as readonly string[]).includes(occasion)) choose({ ...choice, occasion });
            if (answer.message) toast(answer.message);
            setEditDay(false);
            setAttempt((n) => n + 1);
          }}
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

      <Body phase={phase} asking={asking} stylist={claudeView === 'none' ? null : stylist}
        waiting={claudeView === 'waiting' && !choseOwn} meanwhile={!!stylist?.id && meanwhileFor === stylist.id}
        onMeanwhile={() => setMeanwhileFor(stylist?.id ?? null)}
        onAskAgain={() => {
          askAgain.current = true;
          setChoseOwn(false);
          setAttempt((n) => n + 1);
        }}
        index={index} setIndex={setIndex} byId={byId} worn={worn} busy={busy}
        actions={pieceActions} items={items.active} onWear={wear} onUndo={undo} offline={offline}
        changed={!!buildAround || leaveOut.length > 0}
        onClear={() => { setBuildAround(null); setLeaveOut([]); }}
        onRetry={() => setAttempt((n) => n + 1)}
        talk={{ turns: talk, answering, onSay: say, onSettle: settle }} />
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
      {c?.note && (
        <p className="today-note-line" data-testid="day-note" title={c.note.text}>
          {!c.note.active && <span className="muted">Coming up: </span>}
          {/* the weather line already names an active note's place */}
          {(c.note.active && c.note.place && c.place ? c.note.words.slice(1) : c.note.words).join(' · ')}
        </p>
      )}
      {c?.old && <p className="today-day-old" role="note">{c.message || 'This is an older forecast: the weather service could not be reached.'}</p>}
    </section>
  );
}

const DAY_NOTE_MAX = 300;

/**
 * The day in the owner's words, first behind "Change": one sentence ("In Lisbon until Friday", "at a match today,
 * outside from noon to six") that Claude reads for the place, the days and the hours outside. What Closet took from
 * it is shown back under the weather line; here it can be said another way or cleared.
 */
function DayNoteForm({ note, locked, onNote }: { note: DayNote | null; locked: boolean; onNote(answer: DayAnswer): void }) {
  const [text, setText] = useState(note?.text ?? '');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function run(call: () => Promise<DayAnswer>) {
    setBusy(true);
    setMessage(null);
    try {
      const answer = await call();
      if (answer.saved === false) setMessage(answer.message);
      else onNote(answer);
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    if (text.trim()) void run(() => api.saveDay(text.trim()));
  }

  return (
    <form className="today-note-form" onSubmit={submit}>
      <label className="field">
        <span>Say it in a sentence</span>
        <input type="text" value={text} maxLength={DAY_NOTE_MAX} disabled={busy || locked} data-testid="day-note-text"
          placeholder="In Lisbon until Friday. Or: at a match today, outside from noon to six."
          onChange={(e) => setText(e.target.value)} />
      </label>
      <p className="hint">Claude reads this one sentence to find the place and the hours. Nothing from your closet is sent. Your home place stays as it is.</p>
      {note && <p className="today-note-now" data-testid="day-note-now">Now: {note.active ? '' : 'coming up, '}{note.words.join(' · ')}</p>}
      <div className="today-note-actions">
        <Button variant="primary" small type="submit" disabled={busy || locked || !text.trim()}>{busy ? 'Reading…' : 'Save'}</Button>
        {note && <Button small disabled={busy || locked} onClick={() => void run(api.clearDay)}>Clear the note</Button>}
      </div>
      {message && <p className="today-note-message" role="status" data-testid="day-note-message">{message}</p>}
    </form>
  );
}

/** Behind "Change": where you are (search or the browser's location), or today's temperatures typed by hand. */
function DayPanel({ phase, typed, locked, offline, toast, onTyped, onClose, onPlace, onNote }: {
  phase: Phase; typed: TypedDay | null; locked: boolean; offline: boolean; toast: (m: string, k?: 'ok' | 'error') => void;
  onTyped(t: Omit<TypedDay, 'day'> | null): void; onClose?: () => void; onPlace(): void; onNote(answer: DayAnswer): void;
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
      {phase.kind === 'ready' && (
        <>
          <h2 id="day-note-title">Somewhere else, or out all day?</h2>
          <DayNoteForm note={phase.answer.context.note ?? null} locked={locked} onNote={onNote} />
        </>
      )}
      <h2 id="day-title" className={phase.kind === 'ready' ? 'today-day-next' : undefined}>Where are you?</h2>
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
  /** Claude choosing, as shown (null: nothing about Claude is shown). */
  stylist: StylistState | null;
  /** Claude is still choosing: the waiting card stands in for the outfits. */
  waiting: boolean;
  /** The owner asked to see the rules' outfits while Claude chooses. */
  meanwhile: boolean;
  onMeanwhile(): void;
  onAskAgain(): void;
  /** The day's conversation with Claude about the outfits, shown under them once Claude's are on the page. */
  talk: TalkProps;
}

interface TalkProps {
  turns: TalkTurn[];
  /** The message Claude is answering now, or null. */
  answering: string | null;
  /** Sends a message; resolves to why it was not sent, or null. */
  onSay(text: string): Promise<string | null>;
  /** Keeps (`save`) or not a thing Claude offered to remember; resolves to why it could not, or null. */
  onSettle(turnId: string, index: number, save: boolean): Promise<string | null>;
}

function Body(props: BodyProps) {
  const { phase, asking, items, offline, changed, onClear, onRetry, stylist, waiting, meanwhile, onMeanwhile, onAskAgain } = props;
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
      {waiting && <StylistWaiting key={stylist?.id ?? ''} meanwhile={meanwhile} onMeanwhile={onMeanwhile} />}
      {(!waiting || meanwhile) && <Carousel {...props} outfits={answer.outfits} />}
      {!waiting && stylist?.state === 'ready' && (
        <div className="today-stylist" data-testid="stylist-read">
          {stylist.read && <p>Claude on today: {stylist.read}</p>}
          {stylist.message && <p className="today-stylist-note muted" data-testid="stylist-note">{stylist.message}</p>}
          <StylistAgain locked={props.actions.locked} busy={asking || !!props.talk.answering} onClick={onAskAgain}>Ask Claude again</StylistAgain>
          <Conversation {...props.talk} locked={props.actions.locked} busy={asking} />
        </div>
      )}
      {!waiting && stylist?.state === 'failed' && (
        <div className="today-stylist" data-testid="stylist-failed">
          {stylist.message && <p>{stylist.message}</p>}
          <StylistAgain locked={props.actions.locked} busy={asking} onClick={onAskAgain}>Try again</StylistAgain>
        </div>
      )}
    </>
  );
}

/** In place of the outfits while Claude chooses them: what is happening, and the rules' outfits on request. */
function StylistWaiting({ meanwhile, onMeanwhile }: { meanwhile: boolean; onMeanwhile(): void }) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => setSlow(true), STYLIST_SLOW_S * 1000);
    return () => window.clearTimeout(timer);
  }, []);
  return (
    <Card className="today-stylist-wait" role="status" aria-labelledby="stylist-wait-title" data-testid="stylist-waiting">
      <span className="today-stylist-mark" aria-hidden="true"><span /><span /><span /></span>
      <div>
        <h2 id="stylist-wait-title">Claude is choosing today's outfits…</h2>
        <p className="muted">{waitingLine(slow ? STYLIST_SLOW_S : 0)}</p>
        {!meanwhile && <Button small onClick={onMeanwhile}>Show Closet's own picks meanwhile</Button>}
      </div>
    </Card>
  );
}

/**
 * Talking to Claude about the outfits on the page: the day's messages and Claude's answers, the things it offered to
 * remember, and the box to write in. Read-only when the page is locked (offline, or a copy saved earlier).
 */
function Conversation({ turns, answering, onSay, onSettle, locked, busy }: TalkProps & { locked: boolean; busy: boolean }) {
  const [text, setText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const box = useRef<HTMLTextAreaElement>(null);
  // while a message is sent or answered (or the outfits are being asked for) nothing more can be sent; the box is
  // read-only rather than disabled then, so it keeps the focus for the next message
  const held = sending || busy || !!answering || turns.some((t) => t.state === 'working');
  const title = locked ? OFFLINE_TITLE : undefined;

  async function send(what: string, fromBox: boolean) {
    if (!canSay(what) || held || locked) return;
    // the focus stays in the box (it is read-only, not disabled, while Claude answers), ready for the next message
    if (fromBox) box.current?.focus();
    setSending(true);
    setError(null);
    const problem = await onSay(what.trim());
    setSending(false);
    if (problem) setError(problem);
    else if (fromBox) setText('');
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    void send(text, true);
  }

  return (
    <div className="today-talk">
      <div aria-live="polite">
        {turns.length > 0 && (
          <ol className="today-talk-list" aria-label="Your conversation with Claude today" data-testid="talk">
            {turns.map((t, at) => (
              <li key={t.id} className="today-turn" data-testid="talk-turn">
                <div className="today-said">
                  <span className="today-who">You</span>
                  <p>{t.said}</p>
                </div>
                {t.state === 'working' && !locked && (
                  <p className="today-answering muted" role="status">
                    <span className="today-stylist-mark" aria-hidden="true"><span /><span /><span /></span>
                    Claude is answering…
                  </p>
                )}
                {t.state === 'ready' && t.reply && (
                  <div className="today-reply">
                    <span className="today-who">Claude</span>
                    <p>{t.reply}</p>
                  </div>
                )}
                {t.state === 'ready' && t.remember.map((thing, i) => (
                  <Keep key={i} thing={thing} locked={locked} onSettle={(save) => onSettle(t.id, i, save)} />
                ))}
                {t.state === 'failed' && (
                  <div className="today-talk-failed">
                    <p>{t.message}</p>
                    {/* only the newest message can be sent again: an earlier one has been followed by another */}
                    {at === turns.length - 1 && (
                      <Button small disabled={locked || held} title={title} onClick={() => void send(t.said, false)}>Send again</Button>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ol>
        )}
      </div>
      <form className="today-say" onSubmit={submit}>
        <label className="today-say-label" htmlFor="today-say-text">Tell Claude what you think</label>
        <div className="today-say-row">
          <textarea id="today-say-text" ref={box} rows={2} maxLength={MAX_SAY} value={text}
            placeholder="Too dressy? Swap the boots? Ask why…" disabled={locked} title={title}
            readOnly={!locked && held} aria-disabled={!locked && held ? true : undefined}
            aria-invalid={error ? true : undefined} aria-describedby={error ? 'today-say-error' : undefined}
            onChange={(e) => {
              setText(e.target.value);
              if (error) setError(null);
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                void send(text, true);
              }
            }} />
          <Button variant="primary" type="submit" disabled={locked || held || !canSay(text)} title={title}>Send</Button>
        </div>
        {error && <p className="form-error today-say-error" id="today-say-error" role="alert">{error}</p>}
      </form>
    </div>
  );
}

/** A thing Claude offered to remember: kept only when the owner says so. */
function Keep({ thing, locked, onSettle }: { thing: RememberThing; locked: boolean; onSettle(save: boolean): Promise<string | null> }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (thing.state === 'dismissed') return null;
  if (thing.state === 'saved') {
    return <p className="today-kept" data-testid="talk-kept"><CheckIcon />{savedLine(thing)}</p>;
  }
  const words = rememberWords(thing);
  const title = locked ? OFFLINE_TITLE : undefined;
  async function answer(save: boolean) {
    setBusy(true);
    setError(null);
    const problem = await onSettle(save);
    setBusy(false);
    if (problem) setError(problem);
  }
  return (
    <div className="today-keep" role="group" aria-label={words.question} data-testid="talk-keep">
      <p className="today-keep-question">{words.question}</p>
      <p className="today-keep-text"><q>{thing.text}</q></p>
      <div className="today-keep-actions">
        <Button small disabled={busy || locked} title={title} onClick={() => void answer(true)}>{words.save}</Button>
        <Button small variant="ghost" disabled={busy || locked} title={title} onClick={() => void answer(false)}>No thanks</Button>
      </div>
      {error && <p className="form-error today-keep-error" role="alert">{error}</p>}
    </div>
  );
}

function StylistAgain({ locked, busy, onClick, children }: { locked: boolean; busy: boolean; onClick(): void; children: ReactNode }) {
  return (
    <button className="btn btn-link" disabled={locked || busy} title={locked ? OFFLINE_TITLE : undefined} onClick={onClick}>{children}</button>
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
            <OutfitCard outfit={o} view={view} {...rest} by={chosenBy(o, rest.stylist)}
              next={count > 1 ? { label: i < count - 1 ? 'See another idea' : 'Back to the best one', go: () => go(i < count - 1 ? i + 1 : 0) } : undefined} />
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

function OutfitCard({ outfit, view, byId, worn, busy, actions, onWear, onUndo, next, by }: Omit<BodyProps, 'phase' | 'asking' | 'index' | 'setIndex'> & {
  outfit: Outfit; view: TodayView;
  /** Who chose it ("Chosen by Claude"), once Claude has answered; null otherwise. */
  by: string | null;
  /** The next outfit, one tap from the main button: the arrows sit below the reasons, far down a phone's screen. */
  next?: { label: string; go(): void };
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
            version={figureVersion(ids, byId)} dress />
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
        {next && <button className="btn btn-link today-next" onClick={next.go}>{next.label} <ChevronIcon /></button>}
      </div>

      <div className="today-card-why">
        {by && <p className="today-by muted" data-testid="outfit-by">{by}</p>}
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
