import { hashKey, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type FormEvent, type ReactNode, type RefObject } from 'react';
import { api, ApiError } from '../api';
import { CheckIcon, ChevronIcon, ChevronLeftIcon, HangerIcon, MoreIcon, SuitcaseIcon, WarnIcon } from '../components/Icons';
import { itemName, Pic } from '../components/ItemPic';
import { OutfitFigure } from '../components/OutfitFigure';
import { Talk, type TalkProps, type TalkWords } from '../components/Talk';
import { BackLink, Button, Card, EmptyState, Failed, Fold, HowItWorks, ItemThumb, Notice, PageHeader, SegmentedControl, Sheet } from '../components/ui';
import { DaySheet } from '../components/DaySheet';
import { WhereYouAre } from '../components/WhereYouAre';
import { figureVersion, useTodayView, VIEW_OPTIONS, type TodayView } from '../figure';
import { label } from '../labels';
import { keptToast, keptWith } from '../kept';
import { awayClause, countsOnLine, heldLine, heldOfferedLine, MAX_AHEAD_DAYS, planFor, planLine, plannedFor, plannedToast, plansSoon, swapLine, TOO_FAR, tripLine, wearOn, type Plan } from '../plans';
import { newActionId, outboxFor, type WearAction } from '../outbox';
import { keptQuery, plansQuery, touch, useAllItems, useEdit, useItems, writeItem } from '../queries';
import { queryKeys } from '../queryKeys';
import { Link, navigate } from '../router';
import { settingsQuery } from '../settings';
import { useApp, useKept } from '../store';
import {
  addFirstTitle, askedOf, buildAroundPiece, canDress, occasionShown, chosenBy, closetKey, dayName, dayParts, daysAhead, joinWords, longDate, weekdayOf, keptFor, loadChoice, lookingAt, moodLabel, MOODS, newestOn, occasionLabel,
  OCCASIONS, outfitIds, outingLine, parseTemp, placeLabel, readFor, sameOutfit, sameOutfits, shortDate, saveChoice, stylistView, STYLIST_SLOW_S, talkOf,
  timeOf, TRIP_OUTFIT_LINE, TRIP_PIECE_HINT, packedForLine, tripSheetLine, tripTodayLine, waitingLine, whatToAddFirst, withThing, withWorn, wornNow, wornOrder,
  type Choice, type DayAnswer, type DayNote, type OnTrip, type Outfit, type Place, type RememberHow,
  type StylistState, type TodayAnswer, type TodayRequest, type TypedDay, type WearManyAnswer, type WornToday,
} from '../today';
import type { ItemSummary } from '../types';
import { dayAndDate, dayMonth, localDay } from '../wears';
import { localDay as dayNow } from '../wears';
import { dismiss, loadDismissed, pendingQuestion, pieceName, questionFor, withoutOutfit, wornDay, type WornOutfit } from '../worn';
import { tripComingUp } from '../trips';
import { ItemDetail } from './ItemDetail';
import { tripsQuery } from './Trips';
import { changePages, RateOutfit, RecentOutfits, wornQuery } from './Worn';
import { OutfitPics } from '../components/OutfitPics';
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
  /** The occasion was tapped today: the chip is the owner's choice, sent as such (see `occasionShown`). */
  tapped: boolean;
}

let memory: Memory | null = null;

function requestFor(choice: Choice, buildAround: string | null, leaveOut: string[], typed: TypedDay | null, again: string | null = null,
  ahead: string | null = null, otherOutfits = false, tapped = true): TodayRequest {
  const r: TodayRequest = { occasion: choice.occasion, mood: choice.mood };
  // the occasion kept on this device, not tapped today: on a trip day the server dresses for the trip's instead
  if (!tapped && !ahead) r.occasion_kept = true;
  if (ahead) r.day = ahead;
  if (otherOutfits) r.planned = false;
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

export function TodayScreen({ itemId, wide, day: forDay = null }: { itemId: string | null; wide: boolean; day?: string | null }) {
  const { profile, offline, toast } = useApp();
  const qc = useQueryClient();
  const itemsRead = useItems('active');
  const items = itemsRead.data ?? null;
  const [today, setToday] = useState(localDay);
  // Dress for another day: the day ahead this screen shows, or null for today (a day that has come is today's)
  const ahead = forDay && daysAhead(today, forDay) >= 1 ? forDay : null;
  // further ahead than a day can be dressed (an address kept from before, or typed): said, never asked
  const tooFar = !!ahead && daysAhead(today, ahead) > MAX_AHEAD_DAYS;
  const kept = useMemo(() => keptFor(profile), [profile]);
  const remembered = !ahead && memory && memory.profile === profile && memory.day === today ? memory : null;

  const [choice, setChoice] = useState<Choice>(() => loadChoice());
  const [tapped, setTapped] = useState(remembered?.tapped ?? false);
  // the outfits changed today: kept while the app is open, and on this device for the rest of the day
  const keptChanges = remembered || ahead ? null : kept.changes(today);
  // what the address asks as Today opens: an outfit to wear again (Worn), or a piece to build around (its page), which
  // takes the place of the piece built around before, as "Build around this piece" does
  const [asked] = useState(() => askedOf(window.location.search));
  const [buildAround, setBuildAround] = useState<string | null>(
    (!ahead && asked.around) || (remembered?.buildAround ?? keptChanges?.build_around ?? null));
  const [leaveOut, setLeaveOut] = useState<string[]>(() => {
    const left = remembered?.leaveOut ?? keptChanges?.leave_out ?? [];
    return !ahead && asked.around ? buildAroundPiece(left, asked.around).leaveOut : left;
  });
  const [typedOnDay, setTyped] = useState<TypedDay | null>(() => kept.typed(today));
  const typed = typedOnDay?.day === today && !ahead ? typedOnDay : null;
  // The outfits saved on this device earlier today, shown while Nines cannot be reached; nothing is asked meanwhile.
  const [saved, setSaved] = useState<{ answer: TodayAnswer; savedAt: string } | null>(null);
  const [index, setIndex] = useState(remembered?.index ?? 0);
  const [wornOnDay, setWorn] = useState<WornToday | null>(() => kept.worn(today));
  // "I'm wearing this": the outfits on the page when it was tapped stay there, the card tapped turned into what you wear,
  // the others behind the dots to wear instead, while Today is asked the same question (the wear changes the closet, so
  // the outfits are asked for again). Building around a piece ended by the wear is not a new question here (`key`).
  const [pinned, setPinned] = useState<{ outfits: Outfit[]; day: string; key: string } | null>(null);
  // "See other outfits": the day's plan set aside for this visit
  const [otherOutfits, setOtherOutfits] = useState(false);
  // what Undo puts back after a plan was removed or replaced on this screen, with the line saying so
  const [undoPlan, setUndoPlan] = useState<{ words: string; before: Plan | null; day: string } | null>(null);
  const [choosingDay, setChoosingDay] = useState(false);
  const dayButton = useRef<HTMLButtonElement>(null);
  const [busy, setBusy] = useState(false);
  const [editDay, setEditDay] = useState(false);
  // "Change" beside the weather: where the sheet of where you are and today's temperatures floats from on a computer
  const changeButton = useRef<HTMLButtonElement>(null);
  const [again, setAgain] = useState<string | null>(asked.again);
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

  // The address asks once, then is tidied. Today stays open under a piece's page on a phone (`/today/item/<id>`) and
  // beside it on a computer, so what the address asks as that page closes is taken then.
  const opened = useRef(false);
  useEffect(() => {
    const first = !opened.current;
    opened.current = true;
    if (itemId) return;
    if (!first) {
      const now = askedOf(window.location.search);
      if (now.again) setAgain(now.again);
      if (now.around && !ahead) {
        const around = now.around;
        setBuildAround(around);
        setLeaveOut((l) => buildAroundPiece(l, around).leaveOut);
      }
    }
    if (window.location.search) navigate(window.location.pathname, { replace: true });
  }, [itemId, ahead]);
  // a day that has come while the screen was open is today's
  useEffect(() => {
    if (forDay && !ahead) navigate('/today', { replace: true });
  }, [forDay, ahead]);

  // the days planned ahead, and the outfits kept (kept on this device for offline, the plans)
  const plansRead = useQuery(plansQuery(profile));
  const plans = plansRead.data ?? null;
  // a failed read of the plans says so (the shared Failed) where the plan's line or the week's plans go; offline with
  // nothing kept on this device, the offline banner says it once
  const plansFailed = !!plansRead.error && plansRead.data === undefined && (plansRead.error as ApiError).status !== 0;
  const keptOutfits = useQuery({ ...keptQuery(), enabled: !offline }).data ?? null;
  // a planned day opens on the occasion the outfit was planned for (this visit only; the choice kept is not changed)
  const dayPlan = planFor(plans, ahead ?? today);
  const tookPlanOccasion = useRef(false);
  useEffect(() => {
    if (tookPlanOccasion.current || !dayPlan?.occasion) return;
    tookPlanOccasion.current = true;
    const occasion = dayPlan.occasion;
    if ((OCCASIONS as readonly string[]).includes(occasion)) setChoice((c) => (c.occasion === occasion ? c : { ...c, occasion }));
  }, [dayPlan]);

  // the same first page of worn outfits as the Worn screen, read once for both (and kept for offline)
  const recentRead = useQuery(wornQuery(profile)).data;
  const recent = recentRead?.page.outfits ?? null;
  // the same list of trips as the Trips screen, read once for both: a trip near enough to pack for gets a row
  const tripsRead = useQuery(tripsQuery(profile)).data;
  const coming = tripComingUp(tripsRead, today);
  const question = rated ?? pendingQuestion(recent, dismissed, dayNow());
  // what is worn today: this device's memory, put right by the server's list (another device, the Worn screen)
  const worn = useMemo(() => (ahead ? null : wornNow(wornOnDay?.day === today ? wornOnDay : null, offline ? null : recent, recentRead?.at ?? null, today)),
    [wornOnDay, recent, recentRead, today, offline, ahead]);
  // An outfit worn while Nines could not be reached is kept on this phone until it is sent (`outbox.ts`); once it has
  // gone (or Nines refused it), this device's memory of it is read again, as the closet's own handler left it.
  const box = useMemo(() => outboxFor(profile), [profile]);
  const keptActions = useKept(box);
  useEffect(() => {
    if (wornOnDay?.kept && !keptActions.some((a) => a.id === wornOnDay.kept)) setWorn(kept.worn(wornOnDay.day));
  }, [keptActions, wornOnDay, kept]);
  // Offline, "I'm wearing this" is kept on this phone when nothing is worn today yet, or only an outfit kept here: one
  // Nines already has can only be changed while it can be reached.
  const canKeep = !ahead && (!worn || !!worn.kept);

  // Today's outfits: asked when the question changes (the choices, the day, or the closet's places, availability and
  // ratings), and again only when this screen asks (see `ask`). Never by itself: coming back to the screen, to the app
  // or online shows the answer kept, since asking can ask Claude, which costs money.
  const request = useMemo(() => requestFor(choice, buildAround, leaveOut, typed, again, ahead, otherOutfits, tapped),
    [choice, buildAround, leaveOut, typed, again, ahead, otherOutfits, tapped]);
  const closet = useMemo(() => closetKey(items), [items]);
  const key = queryKeys.today(request, ahead ?? today, closet ?? '');
  const answer = useQuery({
    queryKey: key,
    queryFn: async () => {
      const ask = askAgain.current;
      askAgain.current = false;
      const got = await api.today(ask ? { ...request, ask_again: true } : request);
      if (!ahead) kept.setOutfits({ day: localDay(), saved_at: new Date().toISOString(), request, answer: got });
      return got;
    },
    // once the closet's list has been read (or could not be: offline, the question is asked all the same)
    enabled: itemsRead.status !== 'pending' && !saved && !tooFar,
    staleTime: 'static',
    gcTime: Infinity,
    placeholderData: (before) => before ?? keptAnswer(qc, ahead ?? today),
  });
  const { refetch } = answer;
  /** Asks the same question again now (Try again, a new place or note, Claude done choosing, Ask Claude again). */
  const ask = useCallback(() => void refetch(), [refetch]);
  const asking = answer.isFetching;
  const failed = answer.error as ApiError | null;

  const pinKey = useMemo(() => JSON.stringify({ ...request, build_around: undefined }), [request]);
  const pin = pinned && !ahead && pinned.day === today && pinned.key === pinKey ? pinned : null;
  let phase: Phase;
  if (saved) phase = { kind: 'ready', answer: saved.answer, savedAt: saved.savedAt };
  else if (answer.data) phase = { kind: 'ready', answer: answer.data, savedAt: null };
  else if (failed?.status === 0) {
    phase = { kind: 'error', offline: true, message: ahead
      ? "You're offline, so the outfits for that day can't be chosen. They show here once Nines on your computer can be reached."
      : "You're offline, and no outfits were saved on this device today. They show here once Nines on your computer can be reached." };
  } else if (failed) {
    phase = failed.status === 422 && request.low_c === undefined && !ahead ? { kind: 'needs-day', message: failed.message } : { kind: 'error', message: failed.message, offline: false };
  } else phase = { kind: 'loading' };
  // an outfit worn today is always on a card that says so: in its place among the outfits shown, or first
  const asked0 = phase.kind === 'ready' ? phase.answer.outfits : null;
  const shownList = useMemo(() => (asked0 ? withWorn(pin?.outfits ?? asked0, worn) : null), [asked0, pin, worn]);
  if (phase.kind === 'ready' && shownList && shownList !== phase.answer.outfits) phase = { ...phase, answer: { ...phase.answer, outfits: shownList } };
  // the occasion the chips show: on a trip day the answer to the occasion kept is for the trip's, shown without
  // asking again (`occasionShown`); a tap is the owner's own
  const occasion = occasionShown(choice.occasion, !tapped && !ahead, phase.kind === 'ready' ? phase.answer.context.occasion : null);

  // Offline: the outfits saved on this device earlier today, with the choices they were for.
  useEffect(() => {
    if (!failed) return;
    askAgain.current = false;
    followUp.current = false;
    if (failed.status !== 0 || ahead) return;
    const copy = kept.outfits(localDay());
    if (!copy) return;
    const r = copy.request;
    setSaved({ answer: copy.answer, savedAt: copy.saved_at });
    setChoice({ occasion: r.occasion, mood: r.mood });
    setBuildAround(r.build_around ?? null);
    setLeaveOut(r.leave_out ?? []);
    setIndex(0);
  }, [failed, kept, ahead]);

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
    forgetOtherAnswers(qc, hash);
    if (pin) {
      // asked again after a wear: the worn card stays where it is; once the wear is undone, the new outfits show
      if (worn) return;
      setPinned(null);
      if (!sameOutfits(pin.outfits, outfits)) setIndex(0);
      return;
    }
    const keepPlace = followUp.current && !!shownBefore.current && sameOutfits(shownBefore.current, outfits);
    followUp.current = false;
    if (!keepPlace) setIndex(0);
  }, [fresh, answeredAt, hash, qc, pin, worn]);
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
    if (!ahead) memory = { profile, day: today, index, buildAround, leaveOut, tapped };
  }, [profile, today, index, buildAround, leaveOut, ahead, tapped]);
  useEffect(() => {
    if (!ahead) kept.setChanges(buildAround || leaveOut.length ? { day: today, build_around: buildAround, leave_out: leaveOut } : null);
  }, [kept, today, buildAround, leaveOut, ahead]);

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
    if (next.occasion !== occasion) setTapped(true);   // the owner's own choice from now on, sent as such
    setChoice(next);
    saveChoice(next);
  };

  const byId = useMemo(() => new Map((items ?? []).map((i) => [i.id, i])), [items]);
  const allById = useAllItems();
  const nameOf = (id: string) => pieceName(allById.get(id), false, (c) => label('category', c));
  // a piece named in a sentence, with its brand, so a name that starts with it keeps the brand's capital
  const named = (id: string) => ({ name: nameOf(id), brand: allById.get(id)?.brand ?? null });
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

  /** "Wear this on Saturday": keeps the outfit for the day ahead (a plan, not a wear), in place of the plan there was. */
  async function planIt(o: Outfit) {
    if (!ahead) return;
    setBusy(true);
    try {
      const saved = await api.savePlan(ahead, o.pieces, choice.occasion, choice.mood);
      qc.setQueryData<Plan[]>(queryKeys.plans(), (list) => [...(list ?? []).filter((p) => p.day !== ahead), saved.plan]
        .sort((a, b) => a.day.localeCompare(b.day)));
      void touch(qc, 'plan', ['plans']);
      void refetch();   // the day opens on its plan: one Remove the plan, on the outfit
      setUndoPlan(saved.replaced ? { words: 'The last plan was replaced.', before: saved.replaced, day: ahead } : null);
      toast(plannedToast(ahead, today));
    } catch (e) {
      toast((e as Error).message, 'error');
    } finally {
      setBusy(false);
    }
  }

  /** Takes the day's plan away; the line in its place offers Undo. */
  async function unplan(day: string) {
    setBusy(true);
    try {
      const { removed } = await api.removePlan(day);
      qc.setQueryData<Plan[]>(queryKeys.plans(), (list) => (list ?? []).filter((p) => p.day !== day));
      void touch(qc, 'plan', ['plans']);
      if (ahead) void refetch();   // the day's own outfits again (Claude never chooses ahead)
      setUndoPlan({ words: `The plan for ${sayDay(day, today)} is gone.`, before: removed, day });
    } catch (e) {
      toast((e as Error).message, 'error');
    } finally {
      setBusy(false);
    }
  }

  /** Undo: the plan there was before is put back (or, when there was none, the new one taken away). */
  async function undoPlanChange() {
    if (!undoPlan) return;
    const { before, day } = undoPlan;
    setBusy(true);
    try {
      if (before) await api.savePlan(day, before.pieces, before.occasion, before.mood);
      else await api.removePlan(day);
      setUndoPlan(null);
      await touch(qc, 'plan');
      if (ahead) void refetch();
      if (day === today && !ahead) ask();
    } catch (e) {
      toast((e as Error).message, 'error');
    } finally {
      setBusy(false);
    }
  }

  /** "Keep this outfit": kept under Worn, said when it was kept already. */
  async function keepIt(o: Outfit) {
    try {
      const answer = await api.keepOutfit(o.pieces);
      void touch(qc, 'kept');
      toast(keptToast(answer));
    } catch (e) {
      toast((e as Error).message, 'error');
    }
  }

  async function wear(o: Outfit) {
    if (ahead) return planIt(o);
    // one of the rules' outfits worn while Claude was still choosing: that is the owner's choice for today
    if (claudeView === 'waiting') setChoseOwn(true);
    const day = localDay();
    setToday(day);
    const ids = outfitIds(o.pieces);
    if (phase.kind === 'ready') setPinned({ outfits: phase.answer.outfits, day, key: pinKey });
    setBusy(true);
    let changed = false;
    try {
      // what is worn now, as it stands once anything this phone kept has been sent
      await box.idle();
      const now = worn?.kept ? kept.worn(worn.day) : worn;
      if (now?.kept && now.day === day && box.drop(now.kept)) {
        // only kept on this phone so far: the other outfit simply takes its place
        kept.setWorn(null);
        setWorn(null);
      } else if (now && now.day === day && !sameOutfit(now.ids, ids) && (now.recorded.length || now.outfit_id)) {
        const undone = await api.unwearMany(now.recorded, now.worn_on, now.outfit_id);
        changed = true;
        undone.items.forEach((i) => writeItem(qc, i));
        kept.setWorn(null);
        setWorn(null);
      }
      const ctx = phase.kind === 'ready' ? phase.answer.context : null;
      const action: WearAction = {
        kind: 'wear', id: newActionId(), at: new Date().toISOString(), day, item_ids: ids,
        outfit: {
          pieces: o.pieces, score: o.score, reasons: o.reasons, warnings: o.warnings,
          context: { low_c: ctx?.low_c ?? null, high_c: ctx?.high_c ?? null, rain: ctx?.rain ?? null, occasion, mood: choice.mood },
        },
      };
      const sent = await box.send<WearManyAnswer>(action);
      if (sent.kept) {
        // Nines cannot be reached: kept on this phone, and shown as worn exactly as if it had been sent
        const record: WornToday = { day, worn_on: day, ids, recorded: [], outfit: o, at: Date.now(), kept: action.id };
        kept.setWorn(record);
        setWorn(record);
        if (buildAround) setBuildAround(null);
        toast("Noted: you're wearing this today");
        return;
      }
      const r = sent.answer;
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
      await box.idle();
      const now = worn.kept ? kept.worn(worn.day) : worn;
      if (!now) {
        setWorn(null);   // Nines refused it meanwhile, and that was said: there is nothing to take back
        return;
      }
      if (now.kept && box.drop(now.kept)) {
        // kept on this phone and not sent yet: taking it back is only forgetting it here
        kept.setWorn(null);
        setWorn(null);
        toast('Wear undone');
        return;
      }
      if (now.recorded.length || now.outfit_id) (await api.unwearMany(now.recorded, now.worn_on, now.outfit_id)).items.forEach((i) => writeItem(qc, i));
      const gone = now.outfit_id;
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
    onTrip: phase.kind === 'ready' && !ahead && !!phase.answer.context.on_trip && !phase.answer.context.on_trip.aside,
    held: (phase.kind === 'ready' ? phase.answer.context.held : null) ?? {},
    today,
    leaveOut: (id) => {
      setLeaveOut((l) => (l.includes(id) ? l : [...l, id]));
      if (buildAround === id) setBuildAround(null);
    },
    startFrom: (id) => {
      setPinned(null);
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

  // "Another day", beside the heading: the sheet of days to dress for
  const anotherDay = (
    <button ref={dayButton} type="button" className="btn btn-link today-another" aria-haspopup="dialog" aria-expanded={choosingDay}
      onClick={() => setChoosingDay(!choosingDay)} data-testid="another-day">
      Another day
    </button>
  );
  const headerWith = (secondary: ReactNode) => (ahead ? (
    // on a phone, one row: ‹, "Wed 25 Nov" and Another day, so the day's outfit and its button stay on the first screen
    <PageHeader className="today-header today-ahead-header" titleId="today-title"
      title={<><span className="date-long">{weekdayOf(ahead)}</span><span className="date-short">{weekdayOf(ahead).slice(0, 3)}</span></>}
      back={{ to: '/today', label: 'Today' }} secondary={secondary}
      count={dayMonth(ahead, today)} />
  ) : (
    <PageHeader className="today-header" title="Today" titleId="today-title" secondary={secondary}
      count={<><span className="date-long">{longDate(today)}</span><span className="date-short">{shortDate(today)}</span></>} />
  ));
  const header = headerWith(anotherDay);
  const daySheet = choosingDay && (
    <DaySheet today={today} plans={plans} trips={tripsRead} anchor={dayButton} onClose={() => setChoosingDay(false)}
      onChoose={(d) => {
        setChoosingDay(false);
        navigate(`/today/day/${d}`);
      }} />
  );

  // An empty closet: nothing to dress, so no weather or choices either, only what to add (named once, in the headline),
  // and no other day to dress.
  if (items !== null && !canDress(items)) {
    return (
      <div className="today">
        {headerWith(null)}
        <EmptyState big icon={<HangerIcon />} className="today-empty" testId="today-empty"
          title={addFirstTitle(items)}
          action={offline
            ? <span className="btn btn-primary is-disabled" aria-disabled="true" title={OFFLINE_TITLE}>Add clothes</span>
            : <Link to="/add" className="btn btn-primary">Add clothes</Link>} />
      </div>
    );
  }

  // A day further ahead than Nines dresses: one sentence and the way back (finding 24)
  if (tooFar) {
    return (
      <div className="today today-ahead">
        {header}
        {daySheet}
        <EmptyState icon={<WarnIcon />} className="today-too-far" testId="too-far" title={TOO_FAR}
          action={<Link to="/today" className="btn btn-primary">Back to Today</Link>} />
      </div>
    );
  }

  const ctx = phase.kind === 'ready' ? phase.answer.context : null;
  // a trip covers today: its line over the outfits, and the way home for the day behind Change
  const onTrip = !ahead ? ctx?.on_trip ?? null : null;
  // the day before a trip: what you packed for it is left out, said once over the outfits (untick it there to have it)
  const packedFor = !ahead && !onTrip ? ctx?.packed_for ?? null : null;
  const setDay = (t: Omit<TypedDay, 'day'> | null) => {
    const value = t ? { ...t, day: localDay() } : null;
    kept.setTyped(value);
    setTyped(value);
    setEditDay(false);
  };
  /** "Not on this trip today", or its Undo: kept on the server for the day, then Today is asked again. */
  async function setTripAside(trip: OnTrip, on: boolean) {
    setBusy(true);
    try {
      await api.tripAside(trip.id, on);
      setEditDay(false);
      ask();
    } catch (e) {
      toast((e as Error).message, 'error');
    } finally {
      setBusy(false);
    }
  }
  const dayPanel: DayPanelProps = {
    phase, typed, locked, offline, toast,
    trip: onTrip && !onTrip.aside ? { line: tripSheetLine(onTrip), busy, onAside: () => void setTripAside(onTrip, true) } : null,
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

  // Dress for another day: the plan for the day shown (from what the server and this device keep), and the plans of
  // the coming week, said in one line on today's page
  const planNow = ahead ? planFor(plans, ahead) : null;
  const soon = ahead ? [] : plansSoon(plans, today);
  const tripDay = ctx?.trip ?? null;
  const planned = ctx?.plan ?? null;
  const dayWord = ahead ? sayDay(ahead, today) : 'today';
  const ctxPlan = phase.kind === 'ready' && !otherOutfits ? phase.answer.context.plan ?? null : null;
  const expected = phase.kind === 'ready' ? phase.answer.context.expected ?? [] : [];
  const firstIds = phase.kind === 'ready' && phase.answer.outfits[0] ? outfitIds(phase.answer.outfits[0].pieces) : [];
  // a piece the day counts on being back is said under the button of each outfit it is in, not only the first's
  const countsOn = (o: Outfit) => countsOnLine(expected.filter((id) => outfitIds(o.pieces).includes(id)).map(named));
  const tripPlanned = onTrip && !onTrip.aside ? onTrip.planned : null;
  const planNote = {
    swapped: ctxPlan ? swapLine(ctxPlan.unavailable.map((id) => ({ ...named(id), away: ctxPlan.away?.[id] })), ctxPlan.day, today)
      : tripPlanned ? swapLine(tripPlanned.unavailable.map((id) => ({ ...named(id), away: tripPlanned.away?.[id] })), today, today) ?? TRIP_OUTFIT_LINE
        : null,
    heldOffered: phase.kind === 'ready'
      ? heldOfferedLine((phase.answer.context.held_offered ?? []).filter((id) => firstIds.includes(id))
        .map((id) => ({ ...named(id), day: phase.answer.context.held?.[id] ?? '' })), today)
      : null,
  };

  // what was changed ("Built around …", "Without …"), said under the outfits beside "Changing an outfit", where it moves
  // no outfit, each with the way to undo it (finding 8)
  const changes = (buildAround || leaveOut.length > 0) && (
    <div className="chips today-changes" role="group" aria-label="Your changes">
      {buildAround && (
        <button className="chip chip-change" disabled={locked} title={locked ? OFFLINE_TITLE : undefined}
          aria-label={`Stop building around ${nameOf(buildAround)}`} onClick={() => setBuildAround(null)}>
          Built around {nameOf(buildAround)} <span aria-hidden="true">×</span>
        </button>
      )}
      {leaveOut.map((id) => (
        <button key={id} className="chip chip-change" disabled={locked} title={locked ? OFFLINE_TITLE : undefined}
          aria-label={`Without ${nameOf(id)}, put it back`} onClick={() => setLeaveOut((l) => l.filter((x) => x !== id))}>
          Without {nameOf(id)} <span aria-hidden="true">×</span>
        </button>
      ))}
      {(buildAround ? 1 : 0) + leaveOut.length > 1 && (
        <button className="btn btn-link" disabled={locked} onClick={() => { setBuildAround(null); setLeaveOut([]); }}>Clear all</button>
      )}
    </div>
  );

  /** Try again, once for everything Today waits for: the closet's list, the plans and the outfits. */
  const retryAll = () => {
    if (itemsRead.error) void itemsRead.refetch();
    if (plansRead.error) void plansRead.refetch();
    ask();
  };

  const main = (
    <div className={ahead ? 'today today-ahead' : 'today'} aria-busy={asking || phase.kind === 'loading'}>
      {header}
      {daySheet}

      {tripDay ? null : <DayLine phase={phase} editing={editDay} locked={locked} changeRef={changeButton} onEdit={() => setEditDay(!editDay)}
        asking={asking} onRetry={ask} />}
      {ahead ? editDay && ctx && (
        <Sheet title={`About ${dayWord}`} anchor={changeButton} onClose={() => setEditDay(false)}
          className="today-day-sheet" testId="day-sheet">
          <div className="today-day-panel-body">
            <DayNoteForm note={ctx.note ?? null} locked={locked} day={ahead} onNote={dayPanel.onNote} />
          </div>
        </Sheet>
      ) : phase.kind === 'needs-day' ? <DayPanel {...dayPanel} /> : editDay && (
        <Sheet title="Where you are" anchor={changeButton} onClose={() => setEditDay(false)} className="today-day-sheet" testId="day-sheet">
          <DayPanel {...dayPanel} inSheet />
        </Sheet>
      )}

      {!tripDay && <div className="today-choices chips-scroll">
        <ChoiceGroup title="Occasion" options={OCCASIONS} value={occasion} labelOf={occasionLabel} locked={locked}
          onChange={(o) => choose({ ...choice, occasion: o })} />
        <span className="today-choices-sep" aria-hidden="true" />
        <ChoiceGroup title="Mood" options={MOODS} value={choice.mood} labelOf={moodLabel} locked={locked}
          onChange={(mood) => choose({ ...choice, mood })} />
      </div>}

      {ctx?.source === 'mild' && !ahead && !locked && (
        // today's temperatures are typed behind Change, on the weather line above
        <p className="today-no-weather" role="status" data-testid="no-weather">
          <WarnIcon className="inline-icon" /> No forecast.{' '}
          <button className="btn btn-link today-inline-action" disabled={asking} onClick={ask}>Try again</button>
        </p>
      )}

      {onTrip && (
        // a trip covers today: one line of fixed height over the outfits, the trip's or, set aside, the way back to it
        <p className="today-plan today-trip-line" role="status" data-testid="trip-line" title={tripTodayLine(onTrip)}>
          {onTrip.aside ? (
            <>{tripTodayLine(onTrip)}{' '}
              <button className="btn btn-link today-inline-action" disabled={busy || locked} title={locked ? OFFLINE_TITLE : undefined}
                onClick={() => void setTripAside(onTrip, false)}>Undo</button></>
          ) : (
            <Link to={`/trips/${encodeURIComponent(onTrip.id)}`} className="today-trip-line-link">
              <SuitcaseIcon className="inline-icon" /> {tripTodayLine(onTrip)}
            </Link>
          )}
        </p>
      )}

      {packedFor && (
        // the day before a trip: one line of fixed height over the outfits, as on a day the trip covers, leading to it
        <p className="today-plan today-trip-line" role="status" data-testid="packed-line" title={packedForLine(packedFor)}>
          <Link to={`/trips/${encodeURIComponent(packedFor.id)}`} className="today-trip-line-link">
            <SuitcaseIcon className="inline-icon" /> {packedForLine(packedFor)}
          </Link>
        </p>
      )}

      {plansFailed && !tripDay && phase.kind !== 'error' && <Failed query={plansRead} what="your plans" />}
      {!plansFailed && (ahead || planned || undoPlan || (otherOutfits && !ahead)) && !tripDay && (
        <PlanLine ahead={ahead} today={today} planned={otherOutfits ? null : planned} planNow={planNow} undo={undoPlan} other={otherOutfits}
          busy={busy} locked={locked}
          onOther={(v) => setOtherOutfits(v)} onRemove={() => ahead && void unplan(ahead)} onUndo={() => void undoPlanChange()} />
      )}

      {again && (
        <div className="chips today-changes today-again" role="group" aria-label="Wearing again">
          <button className="chip chip-change" disabled={locked} title={locked ? OFFLINE_TITLE : undefined} onClick={() => setAgain(null)}>
            {phase.kind === 'ready' && phase.answer.context.again && phase.answer.context.again.worn_on === null ? 'Starting from an outfit you kept'
              : `Starting from an outfit you wore${phase.kind === 'ready' && phase.answer.context.again?.worn_on ? ` ${wornDay({ worn_on: phase.answer.context.again.worn_on })}` : ''}`} <span aria-hidden="true">×</span>
          </button>
          {phase.kind === 'ready' && (phase.answer.context.again?.unavailable.length ?? 0) > 0 && (
            <span className="muted">{againGone(phase.answer.context.again!, nameOf)}</span>
          )}
        </div>
      )}

      {tripDay ? (
        <Notice tone="info" className="today-trip-day" testId="trip-day"
          action={<Link to={`/trips/${encodeURIComponent(tripDay.id)}`} className="btn btn-small">See the trip</Link>}>
          <p>{tripLine(tripDay.place)}</p>
        </Notice>
      ) : ahead && phase.kind === 'error' && phase.offline && planNow ? (
        <PlannedOffline plan={planNow} byId={byId} day={ahead} today={today} />
      ) : <Body phase={phase} asking={asking} stylist={claudeView === 'none' ? null : stylist}
        waiting={claudeView === 'waiting' && !choseOwn} meanwhile={!!stylist?.id && meanwhileFor === stylist.id}
        before={covering ? settled : null}
        onMeanwhile={() => setMeanwhileFor(stylist?.id ?? null)}
        onAskAgain={() => {
          askAgain.current = true;
          setChoseOwn(false);
          ask();
        }}
        index={index} setIndex={setIndex} byId={byId} worn={worn} busy={busy}
        actions={pieceActions} items={items} onWear={wear} onUndo={undo} offline={offline} canKeep={canKeep}
        changed={!!buildAround || leaveOut.length > 0}
        onClear={() => { setBuildAround(null); setLeaveOut([]); }}
        onRetry={retryAll} failure={failed} failedWhat={ahead ? `the outfits for ${sayDay(ahead, today)}` : "today's outfits"} changes={changes || null}
        countsOn={countsOn}
        talk={{ turns: talk, answering, onSay: say, onSettle: (id, at, save) => settle(id, at, { save }), onUndo: (id, at) => settle(id, at, { undo: true }) }}
        ahead={ahead} today={today} plan={planNow} planNote={planNote} onUnplan={() => ahead && void unplan(ahead)} onKeep={(o) => void keepIt(o)}
        isKept={(ids) => !!keptWith(keptOutfits, ids)} />}

      {soon.length === 1 && (
        <p className="today-soon" data-testid="plans-soon">
          <Link to={`/today/day/${soon[0].day}`}>{dayName(soon[0].day, today)} is planned.</Link>
        </p>
      )}
      {soon.length > 1 && (
        <p className="today-soon" data-testid="plans-soon">
          {soon.map((p, i) => (
            <span key={p.day}>
              {i > 0 && (i === soon.length - 1 ? ' and ' : ', ')}
              <Link to={`/today/day/${p.day}`}>{dayName(p.day, today)}</Link>
            </span>
          ))}
          {' are planned.'}
        </p>
      )}

      {!ahead && coming && !onTrip && !(packedFor && packedFor.id === coming.trip.id) && (
        <Link to={`/trips/${encodeURIComponent(coming.trip.id)}`} className="today-trip" data-testid="today-trip">
          <SuitcaseIcon />
          <span>{coming.words}</span>
          <ChevronIcon className="today-trip-chevron" />
        </Link>
      )}

      {!ahead && recent && (
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

      {!ahead && !coming && !onTrip && <p className="today-more"><Link to="/trips">Going away? Trips says what to pack.</Link></p>}
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

function DayLine({ phase, editing, locked, changeRef, onEdit, asking = false, onRetry }: {
  phase: Phase; editing: boolean; locked: boolean; changeRef: RefObject<HTMLButtonElement | null>; onEdit(): void;
  asking?: boolean; onRetry?(): void;
}) {
  const c = phase.kind === 'ready' ? phase.answer.context : null;
  return (
    <section className="today-day" aria-label="The day">
      <p className="today-day-line" data-testid="day-line" title={c?.place ?? undefined}>
        {/* the dot goes before each part, and the one before a part that starts a line is outside the line (Today.css) */}
        <span className="today-day-parts">
          <span className="today-day-parts-in">
            {c ? dayParts(c).map((part, i) => <span key={i}>{part}</span>)
              : <span className="muted">{phase.kind === 'loading' ? 'Looking up the weather…' : "The weather isn't known yet."}</span>}
          </span>
        </span>
        {phase.kind === 'ready' && phase.savedAt ? (
          // offline, the outfits saved earlier today: when, in a few words where Change is (it waits for Nines; the
          // banner says offline, once)
          <span className="today-day-change today-saved-at" data-testid="saved-at">{timeOf(phase.savedAt) ? `saved at ${timeOf(phase.savedAt)}` : 'saved earlier today'}</span>
        ) : phase.kind !== 'needs-day' && (
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
      {c?.ahead && c.source === 'mild' && c.message && (
        // a day ahead with no weather: one short line, with the way to try again when there is one (the weather line
        // already says the outfits are for a mild day)
        <p className="today-no-weather today-ahead-no-weather" role="status" data-testid="ahead-no-weather">
          <WarnIcon className="inline-icon" /> {c.message}
          {c.retry && onRetry && <>{' '}<button className="btn btn-link today-inline-action" disabled={locked || asking}
            title={locked ? OFFLINE_TITLE : undefined} onClick={onRetry}>Try again</button></>}
        </p>
      )}
    </section>
  );
}

const DAY_NOTE_MAX = 300;

/**
 * The day in the owner's words, first behind "Change": one sentence ("In Lisbon until Friday", "at a match today,
 * outside from noon to six") that Claude reads for the place, the days and the hours outside. What Nines took from
 * it is shown back under the weather line; here it can be said another way or cleared.
 */
function DayNoteForm({ note, locked, onNote, day = null }: { note: DayNote | null; locked: boolean; onNote(answer: DayAnswer): void; day?: string | null }) {
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
    if (text.trim()) void run(() => api.saveDay(text.trim(), day));
  }

  return (
    <form className="today-note-form" onSubmit={submit}>
      <label className="field">
        <span>Say it in a sentence</span>
        <input type="text" value={text} maxLength={DAY_NOTE_MAX} disabled={busy || locked} data-testid="day-note-text"
          placeholder={day ? 'Dinner at eight. Or: outside all afternoon.' : 'In Lisbon until Friday. Or: at a match today, outside from noon to six.'}
          onChange={(e) => setText(e.target.value)} />
      </label>
      <p className="hint">Claude reads this one sentence to find the place and the hours. Nothing from your closet is sent. Your home place stays as it is.</p>
      {note && <p className="today-note-now" data-testid="day-note-now">Now: {note.active ? '' : 'coming up, '}{note.words.join(' · ')}</p>}
      <div className="today-note-actions">
        <Button variant="primary" small type="submit" disabled={busy || locked || !text.trim()}>{busy ? 'Reading…' : 'Save'}</Button>
        {note && <Button small disabled={busy || locked} onClick={() => void run(() => api.clearDay(day))}>Clear the note</Button>}
      </div>
      {message && <p className="today-note-message" role="status" data-testid="day-note-message">{message}</p>}
    </form>
  );
}

interface DayPanelProps {
  phase: Phase; typed: TypedDay | null; locked: boolean; offline: boolean; toast: (m: string, k?: 'ok' | 'error') => void;
  onTyped(t: Omit<TypedDay, 'day'> | null): void; onPlace(): void; onNote(answer: DayAnswer): void;
  /** A trip covers today: why Today looks as it does, and "Not on this trip today", first in the sheet. */
  trip?: { line: string; busy: boolean; onAside(): void } | null;
}

/**
 * Behind "Change": where you are (search or the browser's location), or today's temperatures typed by hand, in a sheet
 * (`inSheet`, whose title names it). In the page itself only when there is no day to dress for until one is chosen.
 */
function DayPanel({ phase, typed, locked, offline, toast, onTyped, onPlace, onNote, inSheet, trip = null }: DayPanelProps & { inSheet?: boolean }) {
  // the same settings as the Settings screen, read once for both; a place chosen is written in by WhereYouAre
  const settings = useQuery({ ...settingsQuery(), enabled: !offline }).data ?? null;

  const body = (
    <>
      {trip && (
        <div className="today-trip-aside" data-testid="trip-aside">
          <p>{trip.line}</p>
          <Button block disabled={locked || trip.busy} title={locked ? OFFLINE_TITLE : undefined} onClick={trip.onAside}>Not on this trip today</Button>
        </div>
      )}
      <WhereYouAre inline place={settings ? settings.place : undefined} home={settings?.home_place} offline={offline} toast={toast}
        onChange={onPlace} trip={!!trip} />
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
  /** Planned pieces Today does not offer now (wearing them leaves them in the laundry on their day): id -> that day. */
  held: Record<string, string>;
  /** A trip covers today: another piece comes from what is in the bag. */
  onTrip: boolean;
  today: string;
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
  /** While Nines cannot be reached, wearing (and taking back an outfit worn here) is kept on this phone. */
  canKeep: boolean;
  onClear(): void;
  /** Try again after a failed read: asks again for everything Today waits for. */
  onRetry(): void;
  /** What could not be read, for the failed state: "today's outfits", "the outfits for tomorrow"; and the error. */
  failedWhat: string;
  failure: unknown;
  /** What was changed (built around, left out), said under the outfits with the way to undo it; null for nothing. */
  changes: ReactNode;
  /** The line under an outfit's button when it counts on a piece being back by then, or null. */
  countsOn(o: Outfit): string | null;
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
  /** Another day dressed ahead (its main button plans the outfit), or null for today. */
  ahead: string | null;
  today: string;
  /** The plan of the day ahead shown, if any: its outfit says so, with a way to take the plan away. */
  plan: Plan | null;
  onUnplan(): void;
  /** Under the first outfit's button, when it starts from the day's plan: the piece swapped and where it is, and a
   * planned piece it uses. */
  planNote?: { swapped: string | null; heldOffered: string | null };
  /** "Keep this outfit", and whether an outfit is kept already. */
  onKeep(o: Outfit): void;
  isKept(ids: string[]): boolean;
}

function Body(props: BodyProps) {
  const { phase, asking, items, offline, changed, onClear, onRetry, stylist, waiting, meanwhile, onMeanwhile, onAskAgain, failedWhat } = props;
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
      // the waiting shape is as tall as an outfit with its reasons and "Changing an outfit" under it, so what is under it
      // is already where it will be when the outfits arrive
      <div className="today-loading" role="status">
        <p className="muted"><span className="spinner" aria-hidden="true" /> {props.ahead ? `Choosing outfits for ${sayDay(props.ahead, props.today)}…` : "Choosing today's outfits…"}</p>
        <div className="today-slide">
          <Card className="today-card" aria-hidden="true">
            <div className="today-card-pieces">
              <div className="today-pieces">{Array.from({ length: 5 }, (_, i) => <div key={i} className="tile-skeleton" />)}</div>
            </div>
            <div className="today-wear">
              <div className="tile-skeleton today-wear-skeleton" />
              <div className="today-more-skeleton" />
            </div>
            <div className="today-card-why today-why-skeleton" />
          </Card>
        </div>
        <div className="today-how-skeleton" />
      </div>
    );
  }
  if (phase.kind === 'needs-day') return null;
  if (phase.kind === 'error' && phase.offline) {
    return <div className="notice" role="alert"><p>{phase.message}</p></div>;
  }
  if (phase.kind === 'error') {
    // the shared words for a failed read, once, with one Try again for everything Today waits for
    return (
      <>
        <Failed query={{ error: props.failure, refetch: onRetry, isFetching: asking }} what={failedWhat} />
        {changed && <div className="row today-error-clear"><Button small onClick={onClear}>Clear your changes</Button></div>}
      </>
    );
  }
  const { answer } = phase;
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
      {/* while Claude chooses, the outfits on the page stay where they are, dimmed under the waiting card, so nothing
          below them moves; "Show Nines' own picks meanwhile" lets them be used, and the card moves under them */}
      <Carousel {...props} outfits={props.before ?? answer.outfits} />
      {props.changes}
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
  const planShown = !!rest.ahead && !!rest.plan && !!outfits[current] && sameOutfit(outfitIds(rest.plan.pieces), outfitIds(outfits[current].pieces));

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
        <div className="today-outfits-title">
          <h2 aria-live="polite">
            {/* a day ahead: "Best for Wed", no longer than "Best for today", so the words stay whole down to 320; a planned
                day's outfit is the plan ("Your plan for Wed"), the other outfits one tap away over it */}
            {current === 0 ? `${planShown ? 'Your plan' : 'Best'} for ${rest.ahead ? dayAndDate(rest.ahead).weekday : 'today'}` : `Another idea`}
            {/* the dots say which outfit is in front; a screen reader hears it with the heading */}
            {count > 1 && <span className="visually-hidden">, {current + 1} of {count}</span>}
          </h2>
          {/* the way to the other outfits, a swipe or a dot for each: in the heading, so it holds still whatever the
              height of the outfit in front */}
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
        </div>
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
              <OutfitCard outfit={o} view={view} {...rest} planNote={i === 0 ? rest.planNote : undefined} countsOn={rest.countsOn(o)} by={chosenBy(o, stylist)}
                read={readFor(o, stylist)} menuFor={menuFor}
                onMore={(id, el) => {
                  anchor.current = el;
                  setMenuFor(menuFor === id ? null : id);
                }}
                next={count > 1 ? { label: i < count - 1 ? 'See another idea' : 'The best one', go: () => go(i < count - 1 ? i + 1 : 0) } : undefined} />
            </article>
          ))}
        </div>
        {covered ? <StylistWaiting key={stylist?.id ?? ''} meanwhile={false} onMeanwhile={onMeanwhile} />
          : asking && <p className="today-asking" role="status"><span className="spinner" aria-hidden="true" /> Asking again…</p>}
      </div>

      {menuFor && view === 'pieces' && (
        <Sheet title={itemName(byId.get(menuFor))} anchor={anchor} onClose={() => setMenuFor(null)} className="today-piece-sheet" testId="piece-sheet">
          <div className="today-piece-choices">
            <Button block disabled={locked} title={title} onClick={() => { setMenuFor(null); actions.leaveOut(menuFor); }}>Not this piece</Button>
            {actions.onTrip && <p className="hint today-held" data-testid="trip-piece-hint">{TRIP_PIECE_HINT}</p>}
            {actions.held[menuFor] && actions.buildAround !== menuFor && (
              <p className="hint today-held" data-testid="held-line">{heldLine(actions.held[menuFor], actions.today)}</p>
            )}
            <Button block disabled={locked} title={title} onClick={() => { setMenuFor(null); actions.startFrom(menuFor); }}>
              {actions.buildAround === menuFor ? 'Stop building around it' : actions.held[menuFor] ? 'Build around it anyway' : 'Build around this piece'}
            </Button>
          </div>
        </Sheet>
      )}
    </section>
  );
}

function OutfitCard({ outfit, view, byId, worn, busy, actions, onWear, onUndo, canKeep, next, by, read, menuFor, onMore, ahead, today, plan, onUnplan, onKeep, isKept, planNote, countsOn, still = false }: Pick<BodyProps,
  'byId' | 'worn' | 'busy' | 'actions' | 'onWear' | 'onUndo' | 'canKeep' | 'ahead' | 'today' | 'plan' | 'onUnplan' | 'onKeep' | 'isKept' | 'planNote'> & {
  outfit: Outfit; view: TodayView;
  /** The line under its button when it counts on a piece being back by then, or null. */
  countsOn: string | null;
  /** Shown as kept on this device (offline): its pieces open, nothing else to choose on them. */
  still?: boolean;
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
  const isPlanned = !!ahead && !!plan && sameOutfit(outfitIds(plan.pieces), ids);
  const locked = actions.locked;
  const title = locked ? OFFLINE_TITLE : undefined;
  // offline, wearing is kept on this phone (see `canKeep`); everything else on the outfit waits
  const wearOff = locked && !canKeep;
  const wearTitle = wearOff ? OFFLINE_TITLE : undefined;
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
                open={menuFor === p.id} onMore={still ? null : (el) => onMore(p.id, el)} />
            </li>
          ))}
        </ul>
      </div>

      <div className="today-wear">
        {isWorn ? (
          <>
            <p className="today-worn" data-testid="worn-today"><CheckIcon />You're wearing this today</p>
            <button className="btn" disabled={busy || wearOff} title={wearTitle} onClick={() => onUndo()}>Undo</button>
          </>
        ) : isPlanned && ahead ? (
          <>
            {/* the heading names the day: "Planned", with Remove the plan beside it on one row */}
            <p className="today-worn today-planned" data-testid="planned-day"><CheckIcon /> Planned</p>
            <button className="btn" disabled={busy || locked} title={title} onClick={() => onUnplan()}>Remove the plan</button>
          </>
        ) : (
          <button className="btn btn-primary btn-block today-wear-button" disabled={busy || (ahead ? locked : wearOff)} title={ahead ? title : wearTitle}
            onClick={() => onWear(outfit)}>
            {ahead ? wearOn(ahead, today) : worn ? 'Wear this instead' : "I'm wearing this"}
          </button>
        )}
        <div className="today-wear-more">
          {isKept(ids) ? <Link to="/today/worn/kept" className="btn btn-link today-keep" data-testid="kept-mark">Kept under Worn</Link>
            : <button className="btn btn-link today-keep" disabled={locked} title={title} onClick={() => onKeep(outfit)}>Keep this outfit</button>}
          {next && <button className="btn btn-link today-next" onClick={next.go}>{next.label} <ChevronIcon /></button>}
        </div>
        {planNote?.swapped && <p className="today-plan-note" data-testid="plan-swapped">{planNote.swapped}</p>}
        {countsOn && <p className="today-plan-note" data-testid="counts-on">{countsOn}</p>}
        {planNote?.heldOffered && <p className="today-plan-note" data-testid="held-offered">{planNote.heldOffered}</p>}
        {/* Give it an outing: one sentence, under the button where the day's other lines about an outfit go */}
        {outfit.outing && (
          <p className="today-plan-note" data-testid="outing-line">{outingLine(outfit.outing, itemName(byId.get(outfit.outing.item_id)), today, byId.get(outfit.outing.item_id)?.brand)}</p>
        )}
      </div>

      {(by || read || outfit.warnings.length > 0 || outfit.reasons.length > 0) && <div className="today-card-why">
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
      </div>}
    </Card>
  );
}

function Piece({ id, place, item, isBase, open, onMore }: {
  id: string; place: Place; item: ItemSummary | undefined; isBase: boolean; open: boolean; onMore: ((button: HTMLElement) => void) | null;
}) {
  const name = itemName(item);
  return (
    <div className={`today-piece${isBase ? ' is-base' : ''}${open ? ' is-open' : ''}`}>
      <Link to={`/today/item/${encodeURIComponent(id)}`} className="today-piece-link" data-testid="piece">
        <ItemThumb className="today-piece-card" picture={<Pic item={item} />} />
        <span className="today-piece-place">{isBase ? 'Built around' : placeLabel(place)}</span>
        <span className="today-piece-name">{name}</span>
      </Link>
      {onMore && (
        <button className="today-piece-more" aria-label={`Choices for ${name}`} aria-haspopup="dialog" aria-expanded={open}
          onClick={(e) => onMore(e.currentTarget)}>
          <MoreIcon />
        </button>
      )}
    </div>
  );
}

/** Under "Starting from an outfit you kept": the pieces that could not come back, a piece away named with where it is
 * ("Your navy blazer is at the cleaner's until Friday 27 November."), the rest as before. */
function againGone(again: NonNullable<TodayAnswer['context']['again']>, nameOf: (id: string) => string): string {
  const away = again.unavailable.filter((id) => again.away?.[id]).map((id) => ({ name: nameOf(id), away: again.away![id] }));
  const rest = again.unavailable.filter((id) => !again.away?.[id]).map(nameOf);
  return [away.length ? `${awayClause(away)}.` : '', rest.length ? `Not clean or not available today: ${joinWords(rest)}.` : '']
    .filter(Boolean).join(' ');
}

/** A day in a sentence: "today", "tomorrow", "Saturday", "Sat 12 Dec". */
function sayDay(day: string, today: string): string {
  if (day === today) return 'today';
  const name = dayName(day, today);
  return name === 'Tomorrow' ? 'tomorrow' : name;
}

/**
 * The one line about the day's plan, over the outfits: that you planned the outfit they start from (with the word about
 * the day; a piece swapped is said under the outfit), or, on a day ahead, that one is planned or not yet; with Undo once a plan was taken
 * away or replaced here. Always one short paragraph, so the outfits under it do not move when it changes.
 */
function PlanLine({ ahead, today, planned, planNow, undo, other, busy, locked, onOther, onRemove, onUndo }: {
  ahead: string | null; today: string; planned: NonNullable<TodayAnswer['context']['plan']> | null; planNow: Plan | null;
  undo: { words: string } | null; other: boolean; busy: boolean; locked: boolean;
  onOther(on: boolean): void; onRemove(): void; onUndo(): void;
}) {
  const title = locked ? OFFLINE_TITLE : undefined;
  const link = (label: string, act: () => void) => (
    <button className="btn btn-link today-inline-action" disabled={busy || locked} title={title} onClick={act}>{label}</button>
  );
  let body: ReactNode;
  if (undo) body = <>{undo.words} {link('Undo', onUndo)}</>;
  else if (planned) {
    // a day ahead: the heading names the day and the outfit says "Planned", so the line is the way out; the morning
    // says whose outfit it is, with the word about the day. A swapped piece is said under the outfit's button
    // (`planNote`), where a longer sentence moves nothing.
    body = ahead && planned.day === ahead
      ? link('See other outfits', () => onOther(true))
      : <>{planLine(planned.day, today, planned.note)} {link('See other outfits', () => onOther(true))}</>;
  } else if (other) body = <>{ahead ? 'Other outfits than your plan.' : 'These are other outfits than the one you planned.'} {link('Back to your plan', () => onOther(false))}</>;
  else if (planNow && ahead) body = <>{plannedFor(ahead, today)}. {link('Remove the plan', onRemove)}</>;
  else if (ahead) body = <span className="muted">Nothing planned yet.</span>;   // the heading names the day
  else return null;
  // on a day ahead, one line of fixed height over the outfit, whatever it says, so the outfit holds still under it
  return <p className={ahead ? 'today-plan today-plan-ahead' : 'today-plan'} role="status" data-testid="plan-line">{body}</p>;
}

/** Offline, a day ahead with a plan: the planned outfit as this device kept it, laid out as the same day online (the
 * outfit's own card, "Planned" with Remove the plan, off until Nines can be reached; the banner says offline). */
function PlannedOffline({ plan, byId, day, today }: { plan: Plan; byId: Map<string, ItemSummary>; day: string; today: string }) {
  const outfit: Outfit = { pieces: plan.pieces, score: 0, reasons: [], warnings: [] };
  const nothing = () => undefined;
  return (
    <section className="today-outfits" aria-label="Today's outfits">
      <div className="today-outfits-head">
        <div className="today-outfits-title"><h2>Your plan for {dayAndDate(day).weekday}</h2></div>
      </div>
      <div className="today-slide" data-testid="planned-offline">
        <OutfitCard outfit={outfit} view="pieces" byId={byId} worn={null} busy={false} canKeep={false} still
          actions={{ locked: true, buildAround: null, held: {}, onTrip: false, today, leaveOut: nothing, startFrom: nothing }}
          onWear={nothing} onUndo={nothing} by={null} read={null} menuFor={null} onMore={nothing} ahead={day} today={today}
          plan={plan} onUnplan={nothing} onKeep={nothing} isKept={() => false} countsOn={null} />
      </div>
    </section>
  );
}
