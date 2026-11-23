import { hashKey, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type FormEvent, type ReactNode, type RefObject } from 'react';
import { api, ApiError } from '../api';
import { CheckIcon, ChevronIcon, ChevronLeftIcon, HangerIcon, MoreIcon, SuitcaseIcon, WarnIcon } from '../components/Icons';
import { itemName, Pic } from '../components/ItemPic';
import { OutfitFigure } from '../components/OutfitFigure';
import { Talk, type TalkProps, type TalkWords } from '../components/Talk';
import { BackLink, Button, Card, EmptyState, Fold, HowItWorks, ItemThumb, Notice, PageHeader, SegmentedControl, Sheet } from '../components/ui';
import { WhereYouAre } from '../components/WhereYouAre';
import { figureVersion, useTodayView, VIEW_OPTIONS, type TodayView } from '../figure';
import { label } from '../labels';
import { touch, useEdit, useItems, writeItem } from '../queries';
import { queryKeys } from '../queryKeys';
import { Link, navigate } from '../router';
import { settingsQuery } from '../settings';
import { useApp } from '../store';
import {
  canDress, chosenBy, closetKey, dayParts, joinWords, longDate, keptFor, loadChoice, lookingAt, moodLabel, MOODS, newestOn, occasionLabel,
  OCCASIONS, outfitIds, parseTemp, placeLabel, readFor, sameOutfit, sameOutfits, shortDate, saveChoice, stylistView, STYLIST_SLOW_S, talkOf,
  timeOf, waitingLine, whatToAddFirst, withThing, wornNow, wornOrder, type Choice, type DayAnswer, type DayNote, type Outfit, type Place, type RememberHow,
  type StylistState, type TodayAnswer, type TodayRequest, type TypedDay, type WornToday,
} from '../today';
import type { ItemSummary } from '../types';
import { localDay } from '../wears';
import { localDay as dayNow } from '../wears';
import { dismiss, loadDismissed, pendingQuestion, pieceName, questionFor, withoutOutfit, wornDay, type WornOutfit } from '../worn';
import { tripComingUp } from '../trips';
import { ItemDetail } from './ItemDetail';
import { tripsQuery } from './Trips';
import { changePages, OutfitPics, RateOutfit, RecentOutfits, useAllItems, wornQuery } from './Worn';
import './Today.css';

const OFFLINE_TITLE = 'Needs Nines on your computer to be reachable';
const TODAY_TALK: TalkWords = {
  list: 'Your conversation with Claude today', box: 'Tell Claude what you think',
  placeholder: 'Too dressy? Swap the boots? Ask why…', id: 'today-say-text',
};
/** How often to ask how Claude stands while it chooses or answers a message. */
const STYLE_POLL_MS = 2000;

type Phase =
  | { kind: 'loading' }
  | { kind: 'ready'; answer: TodayAnswer; savedAt: string | null }
  | { kind: 'needs-day'; message: string }
  | { kind: 'error'; message: string; offline: boolean };

/** What the owner changed on the screen today, kept while the app is open, so coming back from an item (or another tab)
 * asks the same question, whose answer the query cache keeps. */
interface Memory {
  profile: string;
  day: string;
  index: number;
  buildAround: string | null;
  leaveOut: string[];
}

let memory: Memory | null = null;

function requestFor(choice: Choice, buildAround: string | null, leaveOut: string[], typed: TypedDay | null, again: string | null = null): TodayRequest {
  const r: TodayRequest = { occasion: choice.occasion, mood: choice.mood };
  if (again) r.again = again;
  if (buildAround) r.build_around = buildAround;
  if (leaveOut.length) r.leave_out = leaveOut;
  if (typed) Object.assign(r, { low_c: typed.low_c, high_c: typed.high_c, rain: typed.rain });
  return r;
}

const TODAY = [queryKeys.today({ occasion: '', mood: '' })[0]];

/** The newest answer kept for today (any choices), shown while the outfits for the choices now made are asked for. */
function keptAnswer(qc: QueryClient, day: string): TodayAnswer | undefined {
  return newestOn(qc.getQueryCache().findAll({ queryKey: TODAY }).map(
    (q) => [String(q.queryKey[2]), q.state.dataUpdatedAt, q.state.data as TodayAnswer | undefined] as const,
  ), day);
}

/** Only the answer to the question now asked is kept, as before: going back to earlier choices asks again. */
function forgetOtherAnswers(qc: QueryClient, hash: string): void {
  for (const q of qc.getQueryCache().findAll({ queryKey: TODAY })) {
    if (q.queryHash !== hash && q.getObserversCount() === 0) qc.getQueryCache().remove(q);
  }
}

export function TodayScreen({ itemId, wide }: { itemId: string | null; wide: boolean }) {
  const { profile, offline, toast } = useApp();
  const qc = useQueryClient();
  const itemsRead = useItems('active');
  const items = itemsRead.data ?? null;
  const [today, setToday] = useState(localDay);
  const kept = useMemo(() => keptFor(profile), [profile]);
  const remembered = memory && memory.profile === profile && memory.day === today ? memory : null;

  const [choice, setChoice] = useState<Choice>(() => loadChoice());
  // the outfits changed today: kept while the app is open, and on this device for the rest of the day
  const keptChanges = remembered ? null : kept.changes(today);
  const [buildAround, setBuildAround] = useState<string | null>(remembered?.buildAround ?? keptChanges?.build_around ?? null);
  const [leaveOut, setLeaveOut] = useState<string[]>(remembered?.leaveOut ?? keptChanges?.leave_out ?? []);
  const [typedOnDay, setTyped] = useState<TypedDay | null>(() => kept.typed(today));
  const typed = typedOnDay?.day === today ? typedOnDay : null;
  // The outfits saved on this device earlier today, shown while Nines cannot be reached; nothing is asked meanwhile.
  const [saved, setSaved] = useState<{ answer: TodayAnswer; savedAt: string } | null>(null);
  const [index, setIndex] = useState(remembered?.index ?? 0);
  const [wornOnDay, setWorn] = useState<WornToday | null>(() => kept.worn(today));
  const [busy, setBusy] = useState(false);
  const [editDay, setEditDay] = useState(false);
  // "Change" beside the weather: where the sheet of where you are and today's temperatures floats from on a computer
  const changeButton = useRef<HTMLButtonElement>(null);
  const [again, setAgain] = useState<string | null>(() => new URLSearchParams(window.location.search).get('again'));
  const [dismissed, setDismissed] = useState<string[]>(() => loadDismissed(profile));
  const [rated, setRated] = useState<WornOutfit | null>(null);
  // Claude choosing: the question whose rules' outfits are shown meanwhile, and whether the owner chose one of them
  // while Claude was still choosing (then the waiting card stays away for the rest of this visit)
  const [meanwhileFor, setMeanwhileFor] = useState<string | null>(null);
  const [choseOwn, setChoseOwn] = useState(false);
  // "Ask Claude again": the next request carries ask_again, once (never kept with the request or in the saved copy)
  const askAgain = useRef(false);
  // The next answer is the one after Claude answered a message: it keeps the outfit in front of the owner when the
  // outfits did not change, and shows the first when they did
  const followUp = useRef(false);

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

  // the same first page of worn outfits as the Worn screen, read once for both (and kept for offline)
  const recentRead = useQuery(wornQuery(profile)).data;
  const recent = recentRead?.page.outfits ?? null;
  // the same list of trips as the Trips screen, read once for both: a trip near enough to pack for gets a row
  const coming = tripComingUp(useQuery(tripsQuery(profile)).data, today);
  const question = rated ?? pendingQuestion(recent, dismissed, dayNow());
  // what is worn today: this device's memory, put right by the server's list (another device, the Worn screen)
  const worn = useMemo(() => wornNow(wornOnDay?.day === today ? wornOnDay : null, offline ? null : recent, recentRead?.at ?? null, today),
    [wornOnDay, recent, recentRead, today, offline]);

  // Today's outfits: asked when the question changes (the choices, the day, or the closet's places, availability and
  // ratings), and again only when this screen asks (see `ask`). Never by itself: coming back to the screen, to the app
  // or online shows the answer kept, since asking can ask Claude, which costs money.
  const request = useMemo(() => requestFor(choice, buildAround, leaveOut, typed, again), [choice, buildAround, leaveOut, typed, again]);
  const closet = useMemo(() => closetKey(items), [items]);
  const key = queryKeys.today(request, today, closet ?? '');
  const answer = useQuery({
    queryKey: key,
    queryFn: async () => {
      const ask = askAgain.current;
      askAgain.current = false;
      const got = await api.today(ask ? { ...request, ask_again: true } : request);
      kept.setOutfits({ day: localDay(), saved_at: new Date().toISOString(), request, answer: got });
      return got;
    },
    // once the closet's list has been read (or could not be: offline, the question is asked all the same)
    enabled: itemsRead.status !== 'pending' && !saved,
    staleTime: 'static',
    gcTime: Infinity,
    placeholderData: (before) => before ?? keptAnswer(qc, today),
  });
  const { refetch } = answer;
  /** Asks the same question again now (Try again, a new place or note, Claude done choosing, Ask Claude again). */
  const ask = useCallback(() => void refetch(), [refetch]);
  const asking = answer.isFetching;
  const failed = answer.error as ApiError | null;

  let phase: Phase;
  if (saved) phase = { kind: 'ready', answer: saved.answer, savedAt: saved.savedAt };
  else if (answer.data) phase = { kind: 'ready', answer: answer.data, savedAt: null };
  else if (failed?.status === 0) {
    phase = { kind: 'error', offline: true, message: "You're offline, and no outfits were saved on this device today. They show here once Nines on your computer can be reached." };
  } else if (failed) {
    phase = failed.status === 422 && request.low_c === undefined ? { kind: 'needs-day', message: failed.message } : { kind: 'error', message: failed.message, offline: false };
  } else phase = { kind: 'loading' };

  // Offline: the outfits saved on this device earlier today, with the choices they were for.
  useEffect(() => {
    if (!failed) return;
    askAgain.current = false;
    followUp.current = false;
    if (failed.status !== 0) return;
    const copy = kept.outfits(localDay());
    if (!copy) return;
    const r = copy.request;
    setSaved({ answer: copy.answer, savedAt: copy.saved_at });
    setChoice({ occasion: r.occasion, mood: r.mood });
    setBuildAround(r.build_around ?? null);
    setLeaveOut(r.leave_out ?? []);
    setIndex(0);
  }, [failed, kept]);

  // A new answer (not one kept from before, nor a message's answer written in): the first outfit, unless Claude only
  // answered a message and the outfits stayed the same. Only this answer is kept from then on.
  const fresh = answer.data && !answer.isPlaceholderData ? answer.data : null;
  const answeredAt = fresh ? answer.dataUpdatedAt : 0;
  const seenAt = useRef(answeredAt);
  const shownBefore = useRef<Outfit[] | null>(null);
  const hash = hashKey(key);
  useEffect(() => {
    if (!fresh || !answeredAt || answeredAt === seenAt.current) return;
    seenAt.current = answeredAt;
    const outfits = fresh.outfits;
    const keepPlace = followUp.current && !!shownBefore.current && sameOutfits(shownBefore.current, outfits);
    followUp.current = false;
    if (!keepPlace) setIndex(0);
    forgetOtherAnswers(qc, hash);
  }, [fresh, answeredAt, hash, qc]);
  const shownNow = phase.kind === 'ready' ? phase.answer.outfits : null;
  useEffect(() => {
    shownBefore.current = shownNow;
  }, [shownNow]);

  // Back online after showing a saved copy (or nothing): ask again.
  const showingSaved = saved !== null || (phase.kind === 'error' && phase.offline);
  const wasOffline = useRef(offline);
  useEffect(() => {
    if (wasOffline.current && !offline && showingSaved) {
      setSaved(null);
      ask();
    }
    wasOffline.current = offline;
  }, [offline, showingSaved, ask]);

  useEffect(() => {
    memory = { profile, day: today, index, buildAround, leaveOut };
  }, [profile, today, index, buildAround, leaveOut]);
  useEffect(() => {
    kept.setChanges(buildAround || leaveOut.length ? { day: today, build_around: buildAround, leave_out: leaveOut } : null);
  }, [kept, today, buildAround, leaveOut]);

  // While Claude is choosing, or answering a message of the owner's, ask every 2 seconds how it stands (cheap); once
  // it is done, ask Today again with the same choices so Claude's outfits (or the rules', with why) and its answer
  // arrive by themselves. Not while Today is being asked already.
  const stylist = phase.kind === 'ready' ? phase.answer.context.stylist ?? null : null;
  const claudeView = phase.kind === 'ready' ? stylistView(stylist, phase.savedAt !== null) : 'none';
  const { talk, answering } = talkOf(stylist);
  const waitingFor = offline ? null
    : claudeView === 'waiting' ? (!choseOwn && stylist?.id ? stylist.id : null)
      : claudeView === 'read' && phase.kind === 'ready' && phase.savedAt === null ? answering : null;
  const talking = claudeView === 'read';
  // While Claude chooses again, the outfits that were on the page stay there, dimmed under the waiting card, until
  // Claude's are in (or the rules' are asked for meanwhile): so the page keeps its length and you stay where you were.
  const covering = claudeView === 'waiting' && !choseOwn && !(stylist?.id && meanwhileFor === stylist.id);
  const [settled, setSettled] = useState<Outfit[] | null>(null);
  const shownOutfits = phase.kind === 'ready' ? phase.answer.outfits : null;
  if (!covering && shownOutfits && shownOutfits !== settled) setSettled(shownOutfits);
  const styleAnswer = useQuery({
    queryKey: queryKeys.styleAnswer(waitingFor ?? ''),
    // each question 2 seconds after the last one (or after Today's answer), as the server needs the time; a wait
    // or a question still on its way is called off when there is nothing to wait for any more
    queryFn: async ({ signal }) => {
      await new Promise<void>((done, stop) => {
        const t = window.setTimeout(done, STYLE_POLL_MS);
        signal.addEventListener('abort', () => {
          window.clearTimeout(t);
          stop(new DOMException('Stopped', 'AbortError'));
        });
      });
      return api.styleAnswer(waitingFor!, signal);
    },
    enabled: !!waitingFor && !asking,
    staleTime: 0,
    gcTime: 0,
    // the wait is in the question itself, so the next one starts soon after the last answer
    refetchInterval: (q) => (q.state.status === 'error' ? false : 250),
  });
  const gone = useRef(new Set<string>());
  const styleDone = styleAnswer.data && styleAnswer.data.state !== 'working' && !styleAnswer.isFetching ? styleAnswer.dataUpdatedAt : 0;
  const styleGone = (styleAnswer.error as ApiError | null)?.status === 404 ? styleAnswer.errorUpdatedAt : 0;
  const lastStyle = useRef(0);
  useEffect(() => {
    const at = Math.max(styleDone, styleGone);
    if (!waitingFor || !at || at === lastStyle.current) return;
    lastStyle.current = at;
    // the question is gone (the closet changed, the program restarted): ask Today again, once
    if (at === styleGone) {
      if (gone.current.has(waitingFor)) return;
      gone.current.add(waitingFor);
    }
    if (talking) followUp.current = true;
    ask();
    // anything else (offline, a network error): the polling stops quietly; the outfits shown stand
  }, [styleDone, styleGone, waitingFor, talking, ask]);

  const choose = (next: Choice) => {
    setChoice(next);
    saveChoice(next);
  };

  const byId = useMemo(() => new Map((items ?? []).map((i) => [i.id, i])), [items]);
  const allById = useAllItems();
  const nameOf = (id: string) => pieceName(allById.get(id), false, (c) => label('category', c));
  const locked = offline || (phase.kind === 'ready' && phase.savedAt !== null);

  /** Puts an answer written here (a message's, a thing kept) in place of the one kept, as the same answer. */
  const writeAnswer = (update: (a: TodayAnswer) => TodayAnswer) => {
    qc.setQueryData<TodayAnswer>(key, (a) => (a ? update(a) : a), { updatedAt: answer.dataUpdatedAt });
  };

  /** Sends the owner's message about the outfits on the page; gives back why it was not sent, or null. */
  async function say(text: string): Promise<string | null> {
    if (phase.kind !== 'ready') return null;
    const req = request;
    // the carousel shows one outfit at a time: the one at its place is the one in front of the owner
    const looking = lookingAt(index, phase.answer.outfits.length);
    try {
      const got = await api.today({ ...req, say: text, ...(looking === null ? {} : { looking_at: looking }) });
      kept.setOutfits({ day: localDay(), saved_at: new Date().toISOString(), request: req, answer: got });
      if (qc.getQueryData(key)) writeAnswer(() => got);
      else qc.setQueryData(key, got);
      return null;
    } catch (e) {
      return (e as Error).message || "Your message wasn't sent. Try again.";
    }
  }

  /** Keeps (or not) a thing Claude offered to remember, or takes one back; gives back why it could not, or null. */
  async function settle(turnId: string, at: number, how: RememberHow): Promise<string | null> {
    try {
      const thing = await api.remember(turnId, at, how);
      writeAnswer((a) => withThing(a, turnId, at, thing));
      const copy = kept.outfits(localDay());
      if (copy) kept.setOutfits({ ...copy, answer: withThing(copy.answer, turnId, at, thing) });
      // kept in Your style, or in a piece's "How I wear it" (which draws the piece again), or taken back out
      if (how.save || how.undo) {
        void touch(qc, 'styleProfile');
        void touch(qc, 'item');
      }
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
    let changed = false;
    try {
      if (worn && worn.day === day && !sameOutfit(worn.ids, ids) && (worn.recorded.length || worn.outfit_id)) {
        const undone = await api.unwearMany(worn.recorded, worn.worn_on, worn.outfit_id);
        changed = true;
        undone.items.forEach((i) => writeItem(qc, i));
        kept.setWorn(null);
        setWorn(null);
      }
      const ctx = phase.kind === 'ready' ? phase.answer.context : null;
      const r = await api.wearMany(ids, {
        pieces: o.pieces, score: o.score, reasons: o.reasons, warnings: o.warnings,
        context: { low_c: ctx?.low_c ?? null, high_c: ctx?.high_c ?? null, rain: ctx?.rain ?? null, occasion: choice.occasion, mood: choice.mood },
      });
      changed = true;
      r.items.forEach((i) => writeItem(qc, i));
      setToday(localDay());
      const record: WornToday = { day, worn_on: r.worn_on, ids, recorded: r.recorded ?? [], outfit: o, outfit_id: r.outfit?.id, at: Date.now() };
      kept.setWorn(record);
      setWorn(record);
      // wearing the outfit ends building around a piece: that piece may be in the laundry now, and nothing could be
      // built around it, so the next answer is asked without it and the page keeps showing what you are wearing
      if (buildAround) setBuildAround(null);
      toast("Noted: you're wearing this today");
    } catch (e) {
      toast((e as Error).message, 'error');
    } finally {
      setBusy(false);
      // the worn outfits (Worn, and the list above), the items' wears and insights are read again
      if (changed) void touch(qc, 'wear', ['items', 'item']);
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
      if (worn.recorded.length || worn.outfit_id) (await api.unwearMany(worn.recorded, worn.worn_on, worn.outfit_id)).items.forEach((i) => writeItem(qc, i));
      const gone = worn.outfit_id;
      if (gone) changePages(qc, (page) => withoutOutfit(page, gone));
      void touch(qc, 'wear', ['items', 'item']);
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
          <BackLink to="/today" className="btn btn-ghost back-link"><ChevronLeftIcon /> Today</BackLink>
        </div>
        <ItemDetail key={itemId} id={itemId} status="active" inPanel />
      </div>
    );
  }

  const header = (
    <PageHeader className="today-header" title="Today" titleId="today-title" count={<><span className="date-long">{longDate(today)}</span><span className="date-short">{shortDate(today)}</span></>} />
  );

  // An empty closet: nothing to dress, so no weather or choices either, only what to add.
  if (items !== null && !canDress(items)) {
    return (
      <div className="today">
        {header}
        <EmptyState big icon={<HangerIcon />} className="today-empty" testId="today-empty"
          title="Add a top, something for your legs and shoes, and Today can dress you"
          action={offline
            ? <span className="btn btn-primary is-disabled" aria-disabled="true" title={OFFLINE_TITLE}>Add clothes</span>
            : <Link to="/add" className="btn btn-primary">Add clothes</Link>}>
          <p className="muted" data-testid="add-first">Still to add: {joinWords(whatToAddFirst(items))}.</p>
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
  const dayPanel: DayPanelProps = {
    phase, typed, locked, offline, toast,
    onNote: (answer) => {
      // a place in the note wins over temperatures typed earlier today, as a place chosen here does
      if (answer.note?.active && answer.note.place) {
        kept.setTyped(null);
        setTyped(null);
      }
      const occasion = answer.note?.active ? answer.note.occasion : null;
      if (occasion && (OCCASIONS as readonly string[]).includes(occasion)) choose({ ...choice, occasion });
      if (answer.message) toast(answer.message);
      setEditDay(false);
      ask();
    },
    onTyped: setDay,
    onPlace: () => {
      // a place chosen now wins over temperatures typed earlier today
      kept.setTyped(null);
      setTyped(null);
      setEditDay(false);
      ask();
    },
  };

  const main = (
    <div className="today" aria-busy={asking || phase.kind === 'loading'}>
      {header}

      <DayLine phase={phase} editing={editDay} locked={locked} changeRef={changeButton} onEdit={() => setEditDay(!editDay)} />
      {phase.kind === 'needs-day' ? <DayPanel {...dayPanel} /> : editDay && (
        <Sheet title="Where you are" anchor={changeButton} onClose={() => setEditDay(false)} className="today-day-sheet" testId="day-sheet">
          <DayPanel {...dayPanel} inSheet />
        </Sheet>
      )}

      <div className="today-choices chips-scroll">
        <ChoiceGroup title="Occasion" options={OCCASIONS} value={choice.occasion} labelOf={occasionLabel} locked={locked}
          onChange={(occasion) => choose({ ...choice, occasion })} />
        <span className="today-choices-sep" aria-hidden="true" />
        <ChoiceGroup title="Mood" options={MOODS} value={choice.mood} labelOf={moodLabel} locked={locked}
          onChange={(mood) => choose({ ...choice, mood })} />
      </div>

      {ctx?.source === 'mild' && (
        <p className="today-no-weather" role="status" data-testid="no-weather">
          <WarnIcon className="inline-icon" /> The weather could not be fetched.{' '}
          <button className="btn btn-link today-inline-action" disabled={locked || asking} title={locked ? OFFLINE_TITLE : undefined} onClick={ask}>Try again</button>
          <span aria-hidden="true"> · </span>
          <button className="btn btn-link today-inline-action" disabled={locked} title={locked ? OFFLINE_TITLE : undefined} onClick={() => setEditDay(true)}>Type temperatures</button>
        </p>
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
        before={covering ? settled : null}
        onMeanwhile={() => setMeanwhileFor(stylist?.id ?? null)}
        onAskAgain={() => {
          askAgain.current = true;
          setChoseOwn(false);
          ask();
        }}
        index={index} setIndex={setIndex} byId={byId} worn={worn} busy={busy}
        actions={pieceActions} items={items} onWear={wear} onUndo={undo} offline={offline}
        changed={!!buildAround || leaveOut.length > 0}
        onClear={() => { setBuildAround(null); setLeaveOut([]); }}
        onRetry={ask}
        talk={{ turns: talk, answering, onSay: say, onSettle: (id, at, save) => settle(id, at, { save }), onUndo: (id, at) => settle(id, at, { undo: true }) }} />

      {coming && (
        <Link to={`/trips/${encodeURIComponent(coming.trip.id)}`} className="today-trip" data-testid="today-trip">
          <SuitcaseIcon />
          <span><strong>Packing for a trip?</strong> <span className="muted">{coming.words}</span></span>
          <ChevronIcon className="today-trip-chevron" />
        </Link>
      )}

      {recent && (
        <RecentOutfits outfits={recent.filter((o) => o.id !== question?.id)} byId={allById} offline={offline}>
          {question && (
            <Card as="section" className="worn-question" aria-label={questionFor(question, dayNow())} data-testid="worn-question">
              <div className="worn-question-head">
                <h3>{questionFor(question, dayNow())}</h3>
                <OutfitPics outfit={question} byId={allById} linked={false} />
                <button className="btn btn-icon btn-ghost worn-question-close" aria-label="Not now"
                  onClick={() => { setDismissed(dismiss(profile, question.id)); setRated(null); }}>×</button>
              </div>
              <RateOutfit outfit={question} offline={offline} compact onRated={setRated} />
              {rated && (
                <div className="row">
                  <button className="btn btn-small" onClick={() => { setDismissed(dismiss(profile, rated.id)); setRated(null); }}>Done</button>
                </div>
              )}
            </Card>
          )}
        </RecentOutfits>
      )}

      <p className="today-more">Going away? <Link to="/trips">Trips</Link> says what to pack.</p>
    </div>
  );

  if (!wide) return main;
  return (
    <div className={itemId ? 'master-detail today-with-item' : undefined}>
      {main}
      {itemId && (
        <aside className="detail-panel" aria-label="Item details">
          <div className="today-panel-top">
            <BackLink to="/today" className="btn btn-ghost btn-small back-link"><ChevronLeftIcon /> Back to the outfit</BackLink>
          </div>
          <ItemDetail key={itemId} id={itemId} status="active" inPanel />
        </aside>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ the day

function DayLine({ phase, editing, locked, changeRef, onEdit }: {
  phase: Phase; editing: boolean; locked: boolean; changeRef: RefObject<HTMLButtonElement | null>; onEdit(): void;
}) {
  const c = phase.kind === 'ready' ? phase.answer.context : null;
  return (
    <section className="today-day" aria-label="The day">
      <p className="today-day-line" data-testid="day-line" title={c?.place ?? undefined}>
        {c ? dayParts(c).map((part, i) => <span key={i}>{part}</span>)
          : <span className="muted">{phase.kind === 'loading' ? 'Looking up the weather…' : 'The weather'}</span>}
        {phase.kind !== 'needs-day' && (
          <span className="today-day-change">
            <button ref={changeRef} className="btn btn-link" aria-haspopup="dialog" aria-expanded={editing} disabled={locked}
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
 * outside from noon to six") that Claude reads for the place, the days and the hours outside. What Nines took from
 * it is shown back under the weather line; here it can be said another way or cleared.
 */
function DayNoteForm({ note, locked, onNote }: { note: DayNote | null; locked: boolean; onNote(answer: DayAnswer): void }) {
  const [text, setText] = useState(note?.text ?? '');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const saveDay = useEdit('day');

  async function run(call: () => Promise<DayAnswer>) {
    setBusy(true);
    setMessage(null);
    try {
      const answer = await saveDay(call);
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

interface DayPanelProps {
  phase: Phase; typed: TypedDay | null; locked: boolean; offline: boolean; toast: (m: string, k?: 'ok' | 'error') => void;
  onTyped(t: Omit<TypedDay, 'day'> | null): void; onPlace(): void; onNote(answer: DayAnswer): void;
}

/**
 * Behind "Change": where you are (search or the browser's location), or today's temperatures typed by hand, in a sheet
 * (`inSheet`, whose title names it). In the page itself only when there is no day to dress for until one is chosen.
 */
function DayPanel({ phase, typed, locked, offline, toast, onTyped, onPlace, onNote, inSheet }: DayPanelProps & { inSheet?: boolean }) {
  // the same settings as the Settings screen, read once for both; a place chosen is written in by WhereYouAre
  const settings = useQuery({ ...settingsQuery(), enabled: !offline }).data ?? null;

  const body = (
    <>
      <WhereYouAre inline place={settings ? settings.place : undefined} home={settings?.home_place} offline={offline} toast={toast}
        onChange={onPlace} />
      <h3 className="today-typed-title">Or type today's temperatures</h3>
      <TypedForm typed={typed} locked={locked} onTyped={onTyped} />
      {typed && (
        <p className="hint">
          You typed today's temperatures. <button className="btn btn-link" disabled={locked} onClick={() => onTyped(null)}>Use the forecast again</button>
        </p>
      )}
      {phase.kind === 'ready' && (
        <Fold title="Somewhere else, or out all day?" className="today-note-fold" testId="day-note-fold" open={!!phase.answer.context.note}>
          <DayNoteForm note={phase.answer.context.note ?? null} locked={locked} onNote={onNote} />
        </Fold>
      )}
    </>
  );
  if (inSheet) return <div className="today-day-panel-body">{body}</div>;
  return (
    <Card as="section" className="today-day-panel" aria-labelledby="day-title">
      {phase.kind === 'needs-day' && <p className="today-day-why">{phase.message}</p>}
      <h2 id="day-title">Where you are</h2>
      {body}
    </Card>
  );
}

function TypedForm({ typed, locked, onTyped }: { typed: TypedDay | null; locked: boolean; onTyped(t: Omit<TypedDay, 'day'>): void }) {
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
  /** While Claude chooses: the outfits that were on the page before, shown (dimmed) in their place; null for none. */
  before: Outfit[] | null;
  onMeanwhile(): void;
  onAskAgain(): void;
  /** The day's conversation with Claude about the outfits, shown under them once Claude's are on the page. */
  talk: TalkProps;
}

function Body(props: BodyProps) {
  const { phase, asking, items, offline, changed, onClear, onRetry, stylist, waiting, meanwhile, onMeanwhile, onAskAgain } = props;
  // What is under the outfits (Claude's line and the conversation) goes while Claude chooses again; its space is kept
  // until it is back, so Recent outfits below it does not jump up and then down again.
  const after = useRef<HTMLDivElement>(null);
  const [keptHeight, setKeptHeight] = useState(0);
  useLayoutEffect(() => {
    const el = after.current;
    if (waiting || !el || typeof ResizeObserver === 'undefined') return;
    const watch = new ResizeObserver(() => setKeptHeight(el.offsetHeight));
    watch.observe(el);
    return () => watch.disconnect();
  }, [waiting, phase.kind]);
  if (phase.kind === 'loading') {
    return (
      <div className="today-loading" role="status">
        <p className="muted"><span className="spinner" aria-hidden="true" /> Choosing today's outfits…</p>
        <Card className="today-card" aria-hidden="true">
          <div className="today-pieces">{Array.from({ length: 5 }, (_, i) => <div key={i} className="tile-skeleton" />)}</div>
          <div className="tile-skeleton today-wear-skeleton" />
        </Card>
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
        {items && toAdd.length > 0 && !changed && (
          <p className="muted" data-testid="add-first">Add first: {joinWords(toAdd)}.</p>
        )}
        <div className="row today-missing-actions">
          {/* your own changes are why: undoing them is the answer, not adding clothes */}
          {changed ? <Button variant="primary" disabled={offline} title={offline ? OFFLINE_TITLE : undefined} onClick={onClear}>Clear your changes</Button>
            : offline ? <span className="btn btn-primary is-disabled" aria-disabled="true" title={OFFLINE_TITLE}>Add clothes</span>
              : <Link to="/add" className="btn btn-primary">Add clothes</Link>}
        </div>
      </div>
    );
  }
  return (
    <>
      {savedAt && (
        <Notice as="p" tone="warning" className="today-saved" role="status" icon={<WarnIcon />}>
          <span>Saved earlier today{timeOf(savedAt) ? `, at ${timeOf(savedAt)}` : ''}. You're offline, so these can't be changed or worn until Nines on your computer can be reached.</span>
        </Notice>
      )}
      {/* while Claude chooses, the outfits on the page stay where they are, dimmed under the waiting card, so nothing
          below them moves; "Show Nines' own picks meanwhile" lets them be used, and the card moves under them */}
      <Carousel {...props} outfits={props.before ?? answer.outfits} />
      <HowItWorks title="Changing an outfit" className="today-how" testId="today-how">
        <p>Tap a piece to see it. Its <MoreIcon className="inline-icon" aria-label="more" /> button leaves it out, or builds every outfit around it.</p>
        <p>As worn draws the outfit from the pieces' own drawings; choose Pieces to change one.</p>
      </HowItWorks>
      <div ref={after} style={waiting && keptHeight ? { minHeight: keptHeight } : undefined}>
        {waiting && meanwhile && <StylistWaiting key={stylist?.id ?? ''} meanwhile onMeanwhile={onMeanwhile} />}
        {!waiting && stylist?.state === 'ready' && (
          <div className="today-stylist" data-testid="stylist-read">
            {stylist.message && <p className="today-stylist-note muted" data-testid="stylist-note">{stylist.message}</p>}
            <StylistAgain locked={props.actions.locked} busy={asking || !!props.talk.answering} onClick={onAskAgain}>Ask Claude again</StylistAgain>
            <Talk {...props.talk} locked={props.actions.locked} busy={asking} words={TODAY_TALK} lockedTitle={OFFLINE_TITLE} />
          </div>
        )}
        {!waiting && stylist?.state === 'failed' && (
          <div className="today-stylist" data-testid="stylist-failed">
            {stylist.message && <p>{stylist.message}</p>}
            <StylistAgain locked={props.actions.locked} busy={asking} onClick={onAskAgain}>Try again</StylistAgain>
          </div>
        )}
      </div>
    </>
  );
}

/** Over the outfits while Claude chooses them (under them once the rules' outfits are shown meanwhile): what is
 * happening, and the rules' outfits on request. */
function StylistWaiting({ meanwhile, onMeanwhile }: { meanwhile: boolean; onMeanwhile(): void }) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => setSlow(true), STYLIST_SLOW_S * 1000);
    return () => window.clearTimeout(timer);
  }, []);
  return (
    <Card className={`today-stylist-wait${meanwhile ? '' : ' is-over'}`} role="status" aria-labelledby="stylist-wait-title" data-testid="stylist-waiting">
      <span className="today-stylist-mark" aria-hidden="true"><span /><span /><span /></span>
      <div>
        <h2 id="stylist-wait-title">Claude is choosing today's outfits…</h2>
        <p className="muted">{waitingLine(slow ? STYLIST_SLOW_S : 0)}</p>
        {!meanwhile && <Button small onClick={onMeanwhile}>Show Nines' own picks meanwhile</Button>}
      </div>
    </Card>
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
  const { waiting, meanwhile, stylist, onMeanwhile, actions, byId } = rest;
  // Claude is choosing: the outfits stay on the page, dimmed and out of reach, under the waiting card
  const covered = waiting && !meanwhile;

  // Show the remembered outfit straight away (coming back from an item), without animating there.
  useLayoutEffect(() => {
    const el = track.current;
    if (el) el.scrollLeft = current * el.clientWidth;
    // only when the list of outfits changes or the carousel appears
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [outfits]);

  // The track is as tall as the outfit in front, not the tallest of them, so no blank band ends the card.
  const [height, setHeight] = useState<number | null>(null);
  useLayoutEffect(() => {
    const slide = track.current?.children[current] as HTMLElement | undefined;
    if (!slide || typeof ResizeObserver === 'undefined') return;
    const watch = new ResizeObserver(() => setHeight(slide.offsetHeight));
    watch.observe(slide);
    return () => watch.disconnect();
  }, [current, outfits]);

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
  // a piece's choices, in a sheet over the page (from the bottom on a phone, beside the piece on a computer)
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const anchor = useRef<HTMLElement | null>(null);
  const locked = actions.locked;
  const title = locked ? OFFLINE_TITLE : undefined;

  return (
    <section className={`today-outfits${asking || covered ? ' is-asking' : ''}`} aria-label="Today's outfits" aria-roledescription="carousel">
      <div className="today-outfits-head">
        <h2 aria-live="polite">
          {current === 0 ? 'Best for today' : `Another idea`}
          <span className="count"> · {count === 1 ? 'the only outfit' : `${current + 1} of ${count}`}</span>
        </h2>
        <SegmentedControl label="Show the outfit" small className="today-view" value={view}
          options={VIEW_OPTIONS} onChange={setView} />
      </div>

      <div className="today-stage">
        <div className="today-track" ref={track} onScroll={onScroll} tabIndex={-1} inert={covered}
          style={height ? { height } : undefined}>
          {outfits.map((o, i) => (
            <article key={outfitIds(o.pieces).join(',')} className="today-slide" aria-roledescription="slide"
              aria-label={`Outfit ${i + 1} of ${count}`} aria-hidden={i !== current} inert={i !== current}
              data-testid={i === current ? 'current-outfit' : undefined}>
              <OutfitCard outfit={o} view={view} {...rest} by={chosenBy(o, stylist)}
                read={readFor(o, stylist)} menuFor={menuFor}
                onMore={(id, el) => {
                  anchor.current = el;
                  setMenuFor(menuFor === id ? null : id);
                }}
                next={count > 1 ? { label: i < count - 1 ? 'See another idea' : 'Back to the best one', go: () => go(i < count - 1 ? i + 1 : 0) } : undefined} />
            </article>
          ))}
        </div>
        {covered ? <StylistWaiting key={stylist?.id ?? ''} meanwhile={false} onMeanwhile={onMeanwhile} />
          : asking && <p className="today-asking" role="status"><span className="spinner" aria-hidden="true" /> Asking again…</p>}
      </div>

      {count > 1 && (
        <div className="today-nav" role="group" aria-label="Choose an outfit" inert={covered}>
          {outfits.map((_, i) => (
            <button key={i} className={`today-thumb${i === current ? ' is-on' : ''}`} aria-label={`Outfit ${i + 1}`}
              aria-pressed={i === current} onClick={() => go(i)}>
              <span className="today-dot" aria-hidden="true" />
            </button>
          ))}
        </div>
      )}

      {menuFor && view === 'pieces' && (
        <Sheet title={itemName(byId.get(menuFor))} anchor={anchor} onClose={() => setMenuFor(null)} className="today-piece-sheet" testId="piece-sheet">
          <div className="today-piece-choices">
            <Button block disabled={locked} title={title} onClick={() => { setMenuFor(null); actions.leaveOut(menuFor); }}>Not this piece</Button>
            <Button block disabled={locked} title={title} onClick={() => { setMenuFor(null); actions.startFrom(menuFor); }}>
              {actions.buildAround === menuFor ? 'Stop building around it' : 'Build around this piece'}
            </Button>
          </div>
        </Sheet>
      )}
    </section>
  );
}

function OutfitCard({ outfit, view, byId, worn, busy, actions, onWear, onUndo, next, by, read, menuFor, onMore }: Omit<BodyProps, 'phase' | 'asking' | 'index' | 'setIndex'> & {
  outfit: Outfit; view: TodayView;
  /** The piece whose choices are open (the sheet itself is the carousel's), and how they are opened. */
  menuFor: string | null;
  onMore(id: string, button: HTMLElement): void;
  /** Who chose it ("Chosen by Claude"), once Claude has answered; null otherwise. */
  by: string | null;
  /** Claude's reading of the day, under who chose it, for an outfit Claude chose. */
  read: string | null;
  /** The next outfit, one tap from the main button: the arrows sit below the reasons, far down a phone's screen. */
  next?: { label: string; go(): void };
}) {
  const ids = outfitIds(outfit.pieces);
  const isWorn = !!worn && sameOutfit(worn.ids, ids);
  const locked = actions.locked;
  const title = locked ? OFFLINE_TITLE : undefined;
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
                open={menuFor === p.id} onMore={(el) => onMore(p.id, el)} />
            </li>
          ))}
        </ul>
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
        {read && <p className="today-read" data-testid="outfit-read">{read}</p>}
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
      </div>
    </Card>
  );
}

function Piece({ id, place, item, isBase, open, onMore }: {
  id: string; place: Place; item: ItemSummary | undefined; isBase: boolean; open: boolean; onMore(button: HTMLElement): void;
}) {
  const name = itemName(item);
  return (
    <div className={`today-piece${isBase ? ' is-base' : ''}${open ? ' is-open' : ''}`}>
      <Link to={`/today/item/${encodeURIComponent(id)}`} className="today-piece-link" data-testid="piece">
        <ItemThumb className="today-piece-card" picture={<Pic item={item} />} />
        <span className="today-piece-place">{isBase ? 'Built around' : placeLabel(place)}</span>
        <span className="today-piece-name">{name}</span>
      </Link>
      <button className="today-piece-more" aria-label={`Choices for ${name}`} aria-haspopup="dialog" aria-expanded={open}
        onClick={(e) => onMore(e.currentTarget)}>
        <MoreIcon />
      </button>
    </div>
  );
}
