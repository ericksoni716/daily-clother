import { useQuery } from '@tanstack/react-query';
import { useEffect, useId, useMemo, useRef, useState, type ChangeEvent, type ReactNode, type Ref, type RefObject } from 'react';
import { api, type ApiError } from '../api';
import { Card, ChipGroup, EmptyState, Failed, ItemThumb, PageHeader, SegmentedControl, Sheet, type FailedRead } from '../components/ui';
import { CameraIcon, CheckIcon, HangerIcon, ImagesIcon, PlusIcon, WarnIcon } from '../components/Icons';
import { FormalityChips } from '../components/FormalityChips';
import { itemName, Pieces } from '../components/ItemPic';
import { WornOutfit } from '../components/WornWith';
import { useTodayView, VIEW_OPTIONS } from '../figure';
import type { Wish } from '../gaps';
import { navigate } from '../router';
import { vocabQuery } from '../queries';
import { queryKeys } from '../queryKeys';
import { useApp } from '../store';
import { placeLabel, wornOrder } from '../today';
import { localDay } from '../wears';
import type { ItemSummary, Vocab } from '../types';
import {
  CANDIDATE_ID, type Check, checkKey, checkKinds, checkPoll, drawnFromWords, fillNote, fillWords, isDone, nextCheck, noteFor, pieceFromWish, pieceLine,
  keptCheck, pieceToSend, stillToChoose, untoldWords, verdictTone, waitingWords, WEIGHTS, weightLabel, wishFrom, type WouldAnswer, type WouldPiece, wornWords,
} from '../wouldwork';
import './WouldWork.css';

export const OFFLINE_TITLE = 'Needs Nines on your computer to be reachable';
const DEMO_PHOTO = "The demo closet never sends anything to Claude, so a photo can't be described here. Describe it by hand below.";

type Stage =
  | { kind: 'form'; error: string | null }
  | { kind: 'sending' }
  | { kind: 'check'; check: Check };

/** What the screen holds: the description, where the check is, the description last sent by hand (`checked`) and the
 * last answer to one (shown, dimmed, while the next one is worked out). */
interface Held { profile: string; wishId: string | null; draft: Partial<WouldPiece>; stage: Stage; checked: string | null; lastReady: Check | null }

/** Kept while the app is open, so opening an item from the answer and coming back shows the answer again. */
let memory: Held | null = null;
/** A check being sent: leaving the screen does not lose it, and coming back picks it up when the server answers. */
let sending: { profile: string; wishId: string | null; result: Promise<Stage> } | null = null;
/** The checks whose answer was already put on the wishlist (or into the wish's note), by check id. */
const wishedChecks = new Set<string>();

/** Where a send left off: a check (its id known) or the form again; stored before any screen hears of it. */
function settle(profile: string, wishId: string | null, stage: Stage): Stage {
  if (memory && memory.profile === profile && memory.wishId === wishId && memory.stage.kind === 'sending') {
    memory = { ...memory, stage };
  }
  return stage;
}

/** The stage a screen opens on: a send that never got an id goes back to the form. */
function openingStage(remembered: typeof memory): Stage {
  if (!remembered) return { kind: 'form', error: null };
  if (remembered.stage.kind === 'sending' && !(sending && sending.profile === remembered.profile && sending.wishId === remembered.wishId)) {
    return { kind: 'form', error: null };
  }
  return remembered.stage;
}

export interface WouldWorkProps {
  /** The wish it was started from ("Would it go with my clothes?"), if any. */
  wish: Wish | null;
  wishId: string | null;
  byId: Map<string, ItemSummary>;
  locked: boolean;
  busy: boolean;
  onWish(name: string, note: string): Promise<boolean>;
  /** Writes the answer into the note of the wish the check was started from. */
  onNote(wish: Wish, note: string): Promise<boolean>;
  onBought(wish: Wish): Promise<unknown>;
  /** A computer's screen: what the piece is on the left, the answer on the right. */
  wide?: boolean;
}

export function WouldWork({ wish, wishId, byId, locked, busy, onWish, onNote, onBought, wide = false }: WouldWorkProps) {
  const { profile, toast } = useApp();
  const vocabRead = useQuery(vocabQuery());
  const vocab = vocabRead.data ?? null;
  const remembered = memory && memory.profile === profile && memory.wishId === wishId ? memory : null;
  // after a reload (or iOS closing the app), what this device kept today: what was typed and the last answer
  const [kept] = useState(() => (remembered ? null : keptCheck(profile).get(localDay(), wishId)));
  const [draft, setDraft] = useState<Partial<WouldPiece>>(remembered?.draft ?? kept?.draft ?? pieceFromWish(wish));
  const [held, setStage] = useState<Stage>(() => (kept?.shown ? { kind: 'check', check: kept.shown } : openingStage(remembered)));
  const [wished, setWished] = useState(() => held.kind === 'check' && wishedChecks.has(held.check.id));
  // by hand: the description last sent, the last answer to one, and whether a sheet of choices is open
  const [checked, setChecked] = useState<string | null>(remembered?.checked ?? kept?.checked ?? null);
  const [lastReady, setLastReady] = useState<Check | null>(remembered?.lastReady ?? (kept?.shown?.way === 'by_hand' ? kept.shown : null));
  // the sheet of choices open (what it is, or more about it): the next answer is asked for once it is closed
  const [sheet, setSheet] = useState<Choosing>(null);
  const choosing = sheet !== null;
  const moreButton = useRef<HTMLButtonElement>(null);
  const changeButton = useRef<HTMLButtonElement>(null);
  const [answered, setAnswered] = useState<string | null>(kept?.checked ?? null);

  // How the check is getting on: asked every moment until it is answered (more slowly while Nines cannot be reached
  // for a moment), never while the page is hidden, and never again once answered. The check the server sent back
  // when it started is what shows first. Reading never starts a check: only the owner does, below.
  const started = held.kind === 'check' ? held.check : null;
  const followed = useQuery({
    queryKey: queryKeys.wouldWork(started?.id ?? ''),
    queryFn: ({ signal }) => api.check(started!.id, signal),
    enabled: started !== null,
    initialData: started ?? undefined,
    staleTime: Infinity,   // asked again only by the poll
    refetchInterval: (q) => checkPoll(q.state.data, q.state.error as ApiError | null),
  });
  const latest = followed.data;
  const stage = useMemo<Stage>(() => (started && latest?.id === started.id ? { kind: 'check', check: latest } : held), [started, latest, held]);
  // the server has forgotten the check (Nines was restarted): back to the form, saying so
  const forgotten = started && (followed.error as ApiError | null)?.status === 404 ? followed.error!.message : null;
  useEffect(() => {
    if (forgotten) setStage({ kind: 'form', error: forgotten });
  }, [forgotten]);
  const titleId = useId();
  const demo = profile === 'demo';

  // a wish loaded after the panel opened fills in the form, unless the owner has started on it
  const filledFrom = useRef<string | null>(remembered || kept || !wish ? wishId : null);
  useEffect(() => {
    if (wish && filledFrom.current !== wish.id) {
      filledFrom.current = wish.id;
      setDraft((d) => (Object.keys(pieceToSend(d)).length ? d : pieceFromWish(wish)));
    }
  }, [wish]);

  useEffect(() => {
    memory = { profile, wishId, draft, stage, checked, lastReady };
  }, [profile, wishId, draft, stage, checked, lastReady]);

  // kept on this device for the rest of the day too, as Today keeps its changes: a reload shows the same
  const keptReady = stage.kind === 'check' && stage.check.state === 'ready' ? stage.check : lastReady;
  useEffect(() => {
    if (!Object.keys(pieceToSend(draft)).length && !keptReady) return;
    // the description the kept answer is for: a newer one still on its way is sent again after a reload
    keptCheck(profile).set({ day: localDay(), wish_id: wishId, draft, checked: answered, shown: keptReady });
  }, [profile, wishId, draft, answered, keptReady]);

  // the last answer to a description by hand, kept on screen while a newer one is worked out
  const readyByHand = stage.kind === 'check' && stage.check.state === 'ready' && stage.check.way === 'by_hand' ? stage.check : null;
  // and the description that answer is for (one check runs at a time, so it is the one sent last)
  useEffect(() => {
    if (!readyByHand) return;
    setLastReady(readyByHand);
    setAnswered(checked);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per answer
  }, [readyByHand]);

  // came back while a check was being sent: pick it up when the server answers
  useEffect(() => {
    if (stage.kind !== 'sending' || !sending || sending.profile !== profile || sending.wishId !== wishId) return;
    let live = true;
    void sending.result.then((next) => {
      if (live) setStage(next);
    });
    return () => {
      live = false;
    };
  }, [stage.kind, profile, wishId]);

  function start(run: () => Promise<Check>) {
    const result = run().then(
      (check): Stage => settle(profile, wishId, { kind: 'check', check }),
      (e): Stage => settle(profile, wishId, { kind: 'form', error: (e as Error).message }),
    );
    sending = { profile, wishId, result };
    void result.then(() => {
      if (sending?.result === result) sending = null;
    });
    memory = { profile, wishId, draft, stage: { kind: 'sending' }, checked, lastReady };
    setStage({ kind: 'sending' });
    setWished(false);
  }

  // By hand, the answer comes as soon as the kind and the colour are known, and again each time more is said: no
  // button to press. One check at a time; the next follows once it is answered.
  const running = stage.kind === 'sending' || (stage.kind === 'check' && !isDone(stage.check.state));
  const next = nextCheck(draft, { checked, busy: running, choosing, locked });
  const nextKeyed = next ? checkKey(next) : null;
  useEffect(() => {
    if (!nextKeyed) return;
    const piece = JSON.parse(nextKeyed) as Partial<WouldPiece>;
    setChecked(nextKeyed);
    start(() => api.checkByHand(piece));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once for each new description, as `start` reads the rest
  }, [nextKeyed]);

  function photo(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (file) start(() => api.checkPhoto(file, file.name || 'photo.jpg'));
  }

  function again(keep: boolean) {
    if (!keep) {   // a new one: what was kept of the last is forgotten
      keptCheck(profile).set(null);
      setDraft(pieceFromWish(wish));
      setLastReady(null);
      setAnswered(null);
    }
    setChecked(null);
    setStage({ kind: 'form', error: null });
    setWished(false);
  }

  async function putOnWishlist(check: Check) {
    const { name, note } = wishFrom(check);
    if (wishedChecks.has(check.id)) return;
    if (await (wish ? onNote(wish, noteFor(wish, note)) : onWish(name, note))) {
      wishedChecks.add(check.id);
      setWished(true);
    }
  }

  async function bought(check: Check) {
    if (wish) {
      await onBought(wish);
      return;
    }
    toast(`Add a photo of your new ${wishFrom(check).name.toLowerCase()}.`);
    navigate('/add');
  }

  // described by hand and sent: the description is one line, with the rest in sheets, and the answer under it
  const compact = checked !== null && !stillToChoose(draft);
  const readyCheck = stage.kind === 'check' && stage.check.state === 'ready' && stage.check.answer ? stage.check : null;
  const shown = readyCheck ?? (compact ? lastReady : null);
  const refreshing = shown !== null && shown !== readyCheck;
  const untold = compact && shown ? untoldWords(JSON.parse(checked ?? '{}') as Partial<WouldPiece>, shown.answer?.piece ?? null, vocab?.formality ?? []) : null;

  const describe = (stage.kind === 'form' || wide || compact) && (
    <Describe draft={draft} setDraft={setDraft} error={stage.kind === 'form' ? stage.error : null} demo={demo} locked={locked}
      kinds={checkKinds(vocab?.category ?? [])} vocab={vocab} vocabRead={vocabRead} onPhoto={photo}
      compact={compact} again={compact && running && shown !== null} sheet={sheet} onSheet={setSheet}
      moreButton={moreButton} changeButton={changeButton} />
  );

  // Led by the answer: under the verdict, what was taken as usual and the two ways to say more (before it while it is
  // still on its way)
  const controls = compact && vocab && (
    <div className="wouldwork-said" data-testid="would-work-said">
      {untold && <p className="muted wouldwork-small" data-testid="would-work-untold">{untold}</p>}
      <div className="row">
        <button ref={changeButton} type="button" className="btn btn-small" aria-haspopup="dialog" aria-expanded={sheet === 'what'}
          disabled={locked} title={locked ? OFFLINE_TITLE : undefined} onClick={() => setSheet(sheet === 'what' ? null : 'what')}>
          Change what it is
        </button>
        <MoreButton ref={moreButton} open={sheet === 'more'} disabled={locked} onClick={() => setSheet(sheet === 'more' ? null : 'more')} />
      </div>
    </div>
  );

  const answer = (
    <>
      {!shown && stage.kind === 'form' && wide && (
        <EmptyState className="wouldwork-empty" icon={<HangerIcon />} title="The answer shows here"
          body="Whether it fills a gap, what it goes with in your closet, and what you have like it already." />
      )}

      {!shown && stage.kind === 'sending' && <Waiting words="Sending…" />}

      {!shown && stage.kind === 'check' && !isDone(stage.check.state) && <Waiting words={waitingWords(stage.check)} />}

      {!shown && controls}

      {stage.kind === 'check' && stage.check.state === 'failed' && (
        <div className="form-error wouldwork-failed" role="alert">
          <p>{stage.check.message}</p>
          <div className="row">
            {stage.check.by_hand
              ? <button className="btn btn-small btn-primary" onClick={() => {
                if (stage.check.piece) setDraft(stage.check.piece);
                again(true);
              }}>Describe it by hand</button>
              : <button className="btn btn-small" onClick={() => again(true)}>Try again</button>}
          </div>
        </div>
      )}

      {shown && shown.answer && (
        <div className={refreshing ? 'wouldwork-shown is-stale' : 'wouldwork-shown'} aria-busy={refreshing || undefined}>
          <Answer check={shown} answer={shown.answer} byId={byId} afterVerdict={controls} />
          <div className="row wouldwork-actions">
            <button className="btn btn-primary" disabled={locked || busy || wished || refreshing} title={locked ? OFFLINE_TITLE : undefined}
              onClick={() => void putOnWishlist(shown)}>
              {wish
                ? (wished ? <><CheckIcon /> In the wish's note</> : <><PlusIcon /> Add it to the wish's note</>)
                : (wished ? <><CheckIcon /> On your wishlist</> : <><PlusIcon /> Put it on my wishlist</>)}
            </button>
            <button className="btn" disabled={locked || busy} title={locked ? OFFLINE_TITLE : 'Opens Add, to photograph it'}
              onClick={() => void bought(shown)}>I bought it</button>
            <button className="btn btn-ghost" onClick={() => again(false)}>Check another piece</button>
          </div>
        </div>
      )}
    </>
  );

  return (
    <section className={`wouldwork${wide ? ' is-wide' : ''}`} aria-labelledby={titleId} data-testid="would-work">
      <PageHeader className="wouldwork-head" title="Would this work?" titleId={titleId}
        back={{ to: '/wardrobe', label: 'Wardrobe', className: 'wouldwork-back' }}
        subtitle={wish ? <>Checking a find for <strong>{wish.name}</strong> against your closet.</> : 'Check a piece against your closet before you buy it.'} />
      {wide ? (
        <div className="wouldwork-columns">
          <Card as="section" className="wouldwork-left" aria-label="The piece">{describe}</Card>
          <section className="wouldwork-right" aria-label="The answer">{answer}</section>
        </div>
      ) : <>{describe}{answer}</>}
    </section>
  );
}

function Waiting({ words }: { words: string }) {
  return (
    <div className="wouldwork-waiting" role="status" data-testid="would-work-waiting">
      <span className="spinner" aria-hidden="true" />
      <p>{words}</p>
    </div>
  );
}

// ------------------------------------------------------------------ describing the piece

type Choosing = 'more' | 'what' | null;

/** "More about it": the formality, season, weight, pattern, rain and name, in a sheet. */
function MoreButton({ ref, open, disabled, onClick }: { ref: Ref<HTMLButtonElement>; open: boolean; disabled: boolean; onClick(): void }) {
  return (
    <button ref={ref} type="button" className="btn btn-small" aria-haspopup="dialog" aria-expanded={open}
      disabled={disabled} title={disabled ? OFFLINE_TITLE : undefined} onClick={onClick}>
      More about it
    </button>
  );
}

function Describe({ draft, setDraft, error, demo, locked, kinds, vocab, vocabRead, onPhoto, compact, again, sheet, onSheet, moreButton, changeButton }: {
  draft: Partial<WouldPiece>; setDraft(d: Partial<WouldPiece>): void; error: string | null; demo: boolean; locked: boolean;
  kinds: string[]; vocab: Vocab | null; vocabRead: FailedRead; onPhoto(e: ChangeEvent<HTMLInputElement>): void;
  /** described by hand and sent: one line, with what it is and the rest each in a sheet */
  compact: boolean;
  /** a newer answer is being worked out */
  again: boolean;
  /** the sheet open, and the buttons that open them (the page puts them under the verdict once there is one) */
  sheet: Choosing;
  onSheet(which: Choosing): void;
  moreButton: RefObject<HTMLButtonElement | null>;
  changeButton: RefObject<HTMLButtonElement | null>;
}) {
  const camera = useRef<HTMLInputElement>(null);
  const library = useRef<HTMLInputElement>(null);
  const missing = stillToChoose(draft);
  const set = (key: keyof WouldPiece) => (v: string | null) => setDraft({ ...draft, [key]: v });
  const photoOff = demo || locked;
  const open = onSheet;
  const what = vocab && (
    <>
      <ChipGroup field="category" title="What kind of piece" options={kinds} value={draft.category} disabled={locked} onChange={set('category')} />
      <ChipGroup field="color" title="Main colour" options={vocab.color} value={draft.color} disabled={locked} swatches onChange={set('color')} />
    </>
  );
  const more = <MoreButton ref={moreButton} open={sheet === 'more'} disabled={locked || !vocab} onClick={() => open(sheet === 'more' ? null : 'more')} />;
  return (
    <div className="wouldwork-describe">
      {error && <p className="form-error" role="alert">{error}</p>}
      {!compact && (
        <div className="wouldwork-photo">
          <h3 className="chip-group-title">From a photo</h3>
          <div className="row">
            <button type="button" className="btn" disabled={photoOff} title={locked ? OFFLINE_TITLE : undefined} onClick={() => camera.current?.click()}>
              <CameraIcon /> Take a photo
            </button>
            <button type="button" className="btn" disabled={photoOff} title={locked ? OFFLINE_TITLE : undefined} onClick={() => library.current?.click()}>
              <ImagesIcon /> Choose a photo
            </button>
          </div>
          <input ref={camera} type="file" accept="image/*" capture="environment" hidden onChange={onPhoto} data-testid="would-work-camera" />
          <input ref={library} type="file" accept="image/*,.heic,.heif,.avif" hidden onChange={onPhoto} data-testid="would-work-photo" />
          <p className="muted wouldwork-small">
            {demo ? DEMO_PHOTO : 'Claude describes it, as it does a new item. The photo is not added to your closet and is deleted once the answer is ready.'}
          </p>
        </div>
      )}

      <form className="wouldwork-hand" onSubmit={(e) => e.preventDefault()} aria-label="Describe it by hand">
        {!vocab ? (vocabRead.error ? <Failed query={vocabRead} what="the words to describe a piece" />
          : <div className="missing-skeleton missing-skeleton-small" aria-hidden="true" />)
          : compact ? (
            <div className="wouldwork-line" data-testid="would-work-piece">
              <p className="wouldwork-line-what">
                <strong>{pieceLine(draft)}</strong>
                {again && <span className="wouldwork-again" role="status"><span className="spinner" aria-hidden="true" /> Checking again…</span>}
              </p>
            </div>
          ) : (
            <>
              <h3 className="wouldwork-or">Or describe it by hand</h3>
              {what}
              <div className="row wouldwork-hand-end">
                {more}
                {missing && <span className="muted wouldwork-small">{missing}</span>}
              </div>
            </>
          )}
      </form>

      {sheet === 'what' && vocab && (
        <Sheet title="What it is" popover keep={changeButton} className="wouldwork-sheet" testId="would-work-what" onClose={() => open(null)}>
          {what}
        </Sheet>
      )}
      {sheet === 'more' && vocab && (
        <Sheet title="More about it" popover keep={moreButton} className="wouldwork-sheet" testId="would-work-more" onClose={() => open(null)}>
          <FormalityChips levels={vocab.formality} value={draft.formality} also={draft.formality_also} disabled={locked}
            onLevel={(v) => setDraft({ ...draft, formality: v, formality_also: null })} onAlso={set('formality_also')} />
          <ChipGroup field="season" options={vocab.season} value={draft.season} disabled={locked} onChange={set('season')} />
          <ChipGroup field="weight" title="How heavy the cloth is" options={[...WEIGHTS]} value={draft.weight_class} disabled={locked}
            labelOf={weightLabel} onChange={set('weight_class')} />
          <ChipGroup field="pattern" options={vocab.pattern} value={draft.pattern} disabled={locked} onChange={set('pattern')} />
          <label className="toggle wouldwork-rain">
            <span className="toggle-text">
              <span className="toggle-label">It keeps the rain off</span>
              <span className="hint">A mac, a trench, waxed cotton, a shell…</span>
            </span>
            <input type="checkbox" role="switch" checked={!!draft.rain_proof} disabled={locked}
              onChange={(e) => setDraft({ ...draft, rain_proof: e.target.checked })} />
            <span className="toggle-track" aria-hidden="true"><span className="toggle-thumb" /></span>
          </label>
          <label className="field">
            <span>Name <span className="muted">(optional)</span></span>
            <input value={draft.name ?? ''} maxLength={120} disabled={locked} placeholder="e.g. Tan trench coat"
              onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
          </label>
        </Sheet>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ the answer

function Answer({ check, answer, byId, afterVerdict }: {
  check: Check; answer: WouldAnswer; byId: Map<string, ItemSummary>;
  /** by hand: what was taken as usual and the ways to say more, straight under the verdict */
  afterVerdict?: ReactNode;
}) {
  const tone = verdictTone(answer.verdict);
  const [view, setView] = useTodayView();
  const counted = answer.fills.filter((f) => f.found_by.some((w) => w !== 'worn_most'));
  return (
    <div className="wouldwork-answer" data-testid="would-work-answer" data-verdict={answer.verdict} data-piece={check.piece_words ?? undefined}>
      <div className={`wouldwork-verdict is-${tone}`}>
        {tone === 'caution' ? <WarnIcon /> : tone === 'good' ? <CheckIcon /> : <HangerIcon />}
        <div>
          <h3 data-testid="verdict">{answer.verdict_words}</h3>
          {/* by hand, the line above already names the piece; from a photo, what Claude saw is said here once */}
          {check.piece_words && check.way === 'photo' && <p className="wouldwork-piece">Claude saw: {check.piece_words}</p>}
        </div>
      </div>
      {afterVerdict}
      <ul className="gap-why wouldwork-reasons" aria-label="Why">
        {answer.reasons.map((r) => <li key={r}>{r}</li>)}
      </ul>

      {answer.enough && (
        <>
          {counted.length > 0 && (
            <section className="wouldwork-part" aria-label="What it would fill">
              <h4 className="gap-label">What it would fill</h4>
              <ul className="wouldwork-list">
                {counted.map((f) => (
                  <li key={f.gap_id}><strong>{f.name}</strong>: {fillWords(f)}
                    {fillNote(f) && <span className="muted"> · {fillNote(f)}</span>}
                    {f.days.length > 0 && <span className="muted"> · {f.days.length} kind{f.days.length === 1 ? '' : 's'} of day nothing covers now</span>}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {answer.situations_text && (
            <section className="wouldwork-part" aria-label="When you would wear it">
              <h4 className="gap-label">When you would wear it</h4>
              <p data-testid="would-work-situations">{answer.situations_text}</p>
            </section>
          )}

          {answer.goes_with.items.length > 0 && (
            <section className="wouldwork-part" aria-label="What it goes with">
              <h4 className="gap-label">What it goes with</h4>
              {answer.goes_with.text && !answer.reasons.includes(answer.goes_with.text) && <p>{answer.goes_with.text}</p>}
              <Pieces ids={answer.goes_with.items} byId={byId} max={6} label="Your pieces it pairs with best" />
            </section>
          )}

          {answer.goes_with.examples.length > 0 && (
            <section className="wouldwork-part" aria-label="Example outfits">
              <div className="wouldwork-example-head">
                <h4 className="gap-label">For example</h4>
                <SegmentedControl label="Show the example outfits" small className="today-view" value={view} options={VIEW_OPTIONS} onChange={setView} />
              </div>
              {view === 'worn' && <p className="hint wouldwork-drawn">{drawnFromWords(check.way === 'photo' ? 'photo' : 'by_hand', answer.piece?.pattern)}</p>}
              <ul className="wouldwork-outfits">
                {answer.goes_with.examples.map((ex) => (
                  <li key={ex.day.words} data-testid="would-work-outfit">
                    <p className="wouldwork-day">{ex.day.words.charAt(0).toUpperCase() + ex.day.words.slice(1)}</p>
                    {view === 'worn' ? <WornOutfit example={ex} piece={answer.piece} byId={byId} compact /> : (
                    <ul className="gap-thumbs" aria-label={`An outfit for ${ex.day.words}`}>
                      {wornOrder(ex.pieces).map(({ place, id }) => (
                        <li key={`${place}-${id}`}>
                          {id === CANDIDATE_ID ? (
                            <ItemThumb className="gap-thumb wouldwork-this" title={`This piece (${placeLabel(place).toLowerCase()})`}
                              picture={<span>This piece</span>} />
                          ) : (
                            <ItemThumb item={byId.get(id)} to={`/wardrobe/item/${encodeURIComponent(id)}`} className="gap-thumb" title={itemName(byId.get(id))} />
                          )}
                        </li>
                      ))}
                    </ul>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {answer.repeats.items.length > 0 && (
            <section className="wouldwork-part" aria-label="What it repeats">
              <h4 className="gap-label">What it repeats</h4>
              <p>{answer.repeats.text}</p>
              <ul className="gap-thumbs" aria-label="Pieces you have like it">
                {answer.repeats.items.map((r) => (
                  <li key={r.id} className="wouldwork-repeat">
                    <ItemThumb item={byId.get(r.id)} to={`/wardrobe/item/${encodeURIComponent(r.id)}`} className="gap-thumb"
                      title={`${itemName(byId.get(r.id))}: ${wornWords(r.worn).toLowerCase()}`} />
                    <span className={r.hardly_worn ? 'wouldwork-worn is-hardly' : 'wouldwork-worn'}>{wornWords(r.worn)}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {answer.holds_back.length > 0 && (
            <section className="wouldwork-part" aria-label="What would hold it back">
              <h4 className="gap-label">What would hold it back</h4>
              <ul className="gap-why">
                {answer.holds_back.map((h) => <li key={h}>{h}</li>)}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  );
}
