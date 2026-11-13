import { useEffect, useId, useRef, useState, type ChangeEvent, type FormEvent } from 'react';
import { api, ApiError } from '../api';
import { ChipGroup } from '../components/Chips';
import { CameraIcon, CheckIcon, HangerIcon, ImagesIcon, PlusIcon, WarnIcon } from '../components/Icons';
import { itemName, Pic, Pieces } from '../components/ItemPic';
import type { Wish } from '../gaps';
import { Link, navigate } from '../router';
import { useCloset } from '../store';
import { placeLabel, wornOrder } from '../today';
import type { ItemSummary } from '../types';
import {
  CANDIDATE_ID, type Check, checkKinds, isDone, pieceFromLook, pieceToSend, POLL_MS, stillToChoose, verdictTone, waitingWords,
  WEIGHTS, weightLabel, wishFrom, type WouldAnswer, type WouldPiece, wornWords,
} from '../wouldwork';
import './WouldWork.css';

export const OFFLINE_TITLE = 'Needs Closet on your computer to be reachable';
const DEMO_PHOTO = "The demo closet never sends anything to Claude, so a photo can't be described here. Describe it by hand below.";

type Stage =
  | { kind: 'form'; error: string | null }
  | { kind: 'sending' }
  | { kind: 'check'; check: Check };

/** Kept while the app is open, so opening an item from the answer and coming back shows the answer again. */
let memory: { profile: string; wishId: string | null; draft: Partial<WouldPiece>; stage: Stage } | null = null;

export interface WouldWorkProps {
  /** The wish it was started from ("I found one: would it work?"), if any. */
  wish: Wish | null;
  wishId: string | null;
  byId: Map<string, ItemSummary>;
  locked: boolean;
  busy: boolean;
  onWish(name: string, note: string): Promise<boolean>;
  onBought(wish: Wish): Promise<unknown>;
}

export function WouldWork({ wish, wishId, byId, locked, busy, onWish, onBought }: WouldWorkProps) {
  const { profile, vocab, toast } = useCloset();
  const remembered = memory && memory.profile === profile && memory.wishId === wishId ? memory : null;
  const [draft, setDraft] = useState<Partial<WouldPiece>>(remembered?.draft ?? pieceFromLook(wish?.look_for));
  const [stage, setStage] = useState<Stage>(remembered?.stage ?? { kind: 'form', error: null });
  const [wished, setWished] = useState(false);
  const titleId = useId();
  const demo = profile === 'demo';

  // a wish loaded after the panel opened fills in the form, unless the owner has started on it
  const filledFrom = useRef<string | null>(remembered || !wish ? wishId : null);
  useEffect(() => {
    if (wish && filledFrom.current !== wish.id) {
      filledFrom.current = wish.id;
      setDraft((d) => (Object.keys(pieceToSend(d)).length ? d : pieceFromLook(wish.look_for)));
    }
  }, [wish]);

  useEffect(() => {
    memory = { profile, wishId, draft, stage };
  }, [profile, wishId, draft, stage]);

  // ask how the check is getting on until it is answered
  const checkId = stage.kind === 'check' && !isDone(stage.check.state) ? stage.check.id : null;
  useEffect(() => {
    if (!checkId) return;
    const ctrl = new AbortController();
    let timer = 0;
    const ask = async () => {
      try {
        const check = await api.check(checkId, ctrl.signal);
        setStage((s) => (s.kind === 'check' && s.check.id === checkId ? { kind: 'check', check } : s));
        if (!isDone(check.state)) timer = window.setTimeout(ask, POLL_MS);
      } catch (e) {
        if ((e as Error)?.name === 'AbortError') return;
        const err = e as ApiError;
        if (err.status === 404) setStage({ kind: 'form', error: err.message });
        else timer = window.setTimeout(ask, POLL_MS * 2);   // unreachable for a moment: keep asking
      }
    };
    timer = window.setTimeout(ask, POLL_MS);
    return () => {
      ctrl.abort();
      window.clearTimeout(timer);
    };
  }, [checkId]);

  async function start(run: () => Promise<Check>) {
    setStage({ kind: 'sending' });
    setWished(false);
    try {
      setStage({ kind: 'check', check: await run() });
    } catch (e) {
      setStage({ kind: 'form', error: (e as Error).message });
    }
  }

  function byHand(e: FormEvent) {
    e.preventDefault();
    if (stillToChoose(draft)) return;
    void start(() => api.checkByHand(pieceToSend(draft)));
  }

  function photo(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (file) void start(() => api.checkPhoto(file, file.name || 'photo.jpg'));
  }

  function again(keep: boolean) {
    if (!keep) setDraft(pieceFromLook(wish?.look_for));
    setStage({ kind: 'form', error: null });
    setWished(false);
  }

  async function putOnWishlist(check: Check) {
    const { name, note } = wishFrom(check);
    if (await onWish(name, note)) setWished(true);
  }

  async function bought(check: Check) {
    if (wish) {
      await onBought(wish);
      return;
    }
    toast(`Add a photo of your new ${wishFrom(check).name.toLowerCase()}.`);
    navigate('/add');
  }

  return (
    <section className="wouldwork" aria-labelledby={titleId} data-testid="would-work">
      <header className="wouldwork-head">
        <h2 id={titleId}>Would this work?</h2>
        <p className="muted">
          {wish ? <>Checking a find for <strong>{wish.name}</strong> against your closet.</> : 'Check a piece against your closet before you buy it.'}
        </p>
      </header>

      {stage.kind === 'form' && (
        <Describe draft={draft} setDraft={setDraft} error={stage.error} demo={demo} locked={locked}
          kinds={checkKinds(vocab?.category ?? [])} vocab={vocab} onPhoto={photo} onSubmit={byHand} />
      )}

      {stage.kind === 'sending' && <Waiting words="Sending…" />}

      {stage.kind === 'check' && !isDone(stage.check.state) && <Waiting words={waitingWords(stage.check)} />}

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

      {stage.kind === 'check' && stage.check.state === 'ready' && stage.check.answer && (
        <>
          <Answer check={stage.check} answer={stage.check.answer} byId={byId} />
          <div className="row wouldwork-actions">
            <button className="btn btn-primary" disabled={locked || busy || wished} title={locked ? OFFLINE_TITLE : undefined}
              onClick={() => void putOnWishlist(stage.check)}>
              {wished ? <><CheckIcon /> On your wishlist</> : <><PlusIcon /> Put it on my wishlist</>}
            </button>
            <button className="btn" disabled={locked || busy} title={locked ? OFFLINE_TITLE : 'Opens Add, to photograph it'}
              onClick={() => void bought(stage.check)}>I bought it</button>
            <button className="btn btn-ghost" onClick={() => again(false)}>Check another piece</button>
          </div>
        </>
      )}
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

function Describe({ draft, setDraft, error, demo, locked, kinds, vocab, onPhoto, onSubmit }: {
  draft: Partial<WouldPiece>; setDraft(d: Partial<WouldPiece>): void; error: string | null; demo: boolean; locked: boolean;
  kinds: string[]; vocab: ReturnType<typeof useCloset>['vocab']; onPhoto(e: ChangeEvent<HTMLInputElement>): void; onSubmit(e: FormEvent): void;
}) {
  const camera = useRef<HTMLInputElement>(null);
  const library = useRef<HTMLInputElement>(null);
  const missing = stillToChoose(draft);
  const set = (key: keyof WouldPiece) => (v: string | null) => setDraft({ ...draft, [key]: v });
  const photoOff = demo || locked;
  return (
    <div className="wouldwork-describe">
      {error && <p className="form-error" role="alert">{error}</p>}
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
        <input ref={library} type="file" accept="image/*,.heic,.heif" hidden onChange={onPhoto} data-testid="would-work-photo" />
        <p className="muted wouldwork-small">
          {demo ? DEMO_PHOTO : 'Claude describes it, as it does a new item. The photo is not added to your closet and is deleted once the answer is ready.'}
        </p>
      </div>

      <form className="wouldwork-hand" onSubmit={onSubmit} aria-label="Describe it by hand">
        <h3 className="wouldwork-or">Or describe it by hand</h3>
        {vocab ? (
          <>
            <ChipGroup field="category" title="What kind of piece" options={kinds} value={draft.category} disabled={locked} onChange={set('category')} />
            <ChipGroup field="color" title="Main colour" options={vocab.color} value={draft.color} disabled={locked} swatches onChange={set('color')} />
            <ChipGroup field="formality" options={vocab.formality} value={draft.formality} disabled={locked} onChange={set('formality')} />
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
          </>
        ) : <div className="missing-skeleton missing-skeleton-small" aria-hidden="true" />}
        <div className="row">
          <button className="btn btn-primary" type="submit" disabled={locked || !!missing || !vocab} title={locked ? OFFLINE_TITLE : undefined}>
            Would it work?
          </button>
          {missing && <span className="muted wouldwork-small">{missing}</span>}
        </div>
      </form>
    </div>
  );
}

// ------------------------------------------------------------------ the answer

function Answer({ check, answer, byId }: { check: Check; answer: WouldAnswer; byId: Map<string, ItemSummary> }) {
  const tone = verdictTone(answer.verdict);
  const counted = answer.fills.filter((f) => f.found_by.some((w) => w !== 'worn_most'));
  return (
    <div className="wouldwork-answer" data-testid="would-work-answer" data-verdict={answer.verdict}>
      <div className={`wouldwork-verdict is-${tone}`}>
        {tone === 'caution' ? <WarnIcon /> : tone === 'good' ? <CheckIcon /> : <HangerIcon />}
        <div>
          <h3 data-testid="verdict">{answer.verdict_words}</h3>
          {check.piece_words && <p className="wouldwork-piece">{check.way === 'photo' ? 'Claude saw: ' : ''}{check.piece_words}</p>}
        </div>
      </div>
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
                  <li key={f.gap_id}><strong>{f.name}</strong>: {f.gone ? 'no longer missing' : 'less of a gap'}
                    {f.days.length > 0 && <span className="muted"> · {f.days.length} kind{f.days.length === 1 ? '' : 's'} of day nothing covers now</span>}
                  </li>
                ))}
              </ul>
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
              <h4 className="gap-label">For example</h4>
              <ul className="wouldwork-outfits">
                {answer.goes_with.examples.map((ex) => (
                  <li key={ex.day.words} data-testid="would-work-outfit">
                    <p className="wouldwork-day">{ex.day.words.charAt(0).toUpperCase() + ex.day.words.slice(1)}</p>
                    <ul className="gap-thumbs" aria-label={`An outfit for ${ex.day.words}`}>
                      {wornOrder(ex.pieces).map(({ place, id }) => (
                        <li key={`${place}-${id}`}>
                          {id === CANDIDATE_ID ? (
                            <span className="gap-thumb wouldwork-this" title={`This piece (${placeLabel(place).toLowerCase()})`}>
                              <span>This piece</span>
                            </span>
                          ) : (
                            <Link to={`/missing/item/${encodeURIComponent(id)}`} className="gap-thumb" title={itemName(byId.get(id))}>
                              <Pic item={byId.get(id)} />
                            </Link>
                          )}
                        </li>
                      ))}
                    </ul>
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
                    <Link to={`/missing/item/${encodeURIComponent(r.id)}`} className="gap-thumb" title={`${itemName(byId.get(r.id))}: ${wornWords(r.worn).toLowerCase()}`}>
                      <Pic item={byId.get(r.id)} />
                    </Link>
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
