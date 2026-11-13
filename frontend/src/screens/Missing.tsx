import { useCallback, useEffect, useId, useMemo, useRef, useState, type FormEvent, type ReactNode, type SVGProps } from 'react';
import { api, ApiError } from '../api';
import { CheckIcon, ChevronLeftIcon, HangerIcon, PlusIcon, WarnIcon } from '../components/Icons';
import { LifeQuestions } from '../components/LifeQuestions';
import {
  colorWords, type Gap, type GapsAnswer, HELP_LEVELS, helpOf, HIDE_REASONS, type HideReason, loadSavedGaps, lookForLines,
  type LookFor, otherFindings, reasonLabel, saveGaps, type Wish,
} from '../gaps';
import { label, SWATCH } from '../labels';
import { Link, navigate } from '../router';
import { useCloset } from '../store';
import { timeOf } from '../today';
import type { ItemSummary } from '../types';
import { activeSituations, lifeSummary, situationLabel, type SituationId } from '../life';
import { ItemDetail } from './ItemDetail';
import './Missing.css';

const OFFLINE_TITLE = 'Needs Closet on your computer to be reachable';

/** A shopping bag: the What's missing screen in the navigation. */
export const BagIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg width={24} height={24} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round"
    strokeLinejoin="round" aria-hidden="true" {...p}>
    <path d="M5 8h14l-1 12H6z" /><path d="M9 10V7a3 3 0 0 1 6 0v3" />
  </svg>
);

type Phase =
  | { kind: 'loading' }
  | { kind: 'ready'; gaps: GapsAnswer; wishes: Wish[]; savedAt: string | null }
  | { kind: 'error'; message: string; offline: boolean };

/** Kept while the app is open, so coming back from an item shows the list at once (it is asked again quietly). */
let memory: { profile: string; phase: Phase; tab: Tab } | null = null;

type Tab = 'gaps' | 'wishlist';

export function MissingScreen({ itemId, wide }: { itemId: string | null; wide: boolean }) {
  const { profile, items, loadItems, offline, toast } = useCloset();
  const remembered = memory && memory.profile === profile ? memory : null;
  const [phase, setPhase] = useState<Phase>(remembered?.phase ?? { kind: 'loading' });
  const [tab, setTab] = useState<Tab>(remembered?.tab ?? 'gaps');
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [lifeOpen, setLifeOpen] = useState(false);
  const [situation, setSituation] = useState<SituationId | 'all'>('all');
  const shown = useRef(phase);
  useEffect(() => {
    shown.current = phase;
  }, [phase]);

  useEffect(() => {
    if (items.active === null) void loadItems('active');
  }, [items.active, loadItems]);

  const load = useCallback(async (signal?: { cancelled: boolean }) => {
    setAsking(true);
    try {
      const [gaps, wishes] = await Promise.all([api.gaps(), api.wishlist()]);
      if (signal?.cancelled) return;
      saveGaps(profile, { gaps, wishes });
      setPhase({ kind: 'ready', gaps, wishes, savedAt: null });
    } catch (e) {
      if (signal?.cancelled) return;
      const err = e as ApiError;
      if (err.status === 0) {
        const saved = loadSavedGaps(profile);
        if (saved?.gaps) setPhase({ kind: 'ready', gaps: saved.gaps, wishes: saved.wishes ?? [], savedAt: saved.saved_at });
        else setPhase({ kind: 'error', offline: true, message: "You're offline, and nothing was saved on this device yet. What's missing shows here once Closet on your computer can be reached." });
      } else if (shown.current.kind === 'ready' && shown.current.savedAt === null) {
        toast(err.message, 'error');
      } else {
        setPhase({ kind: 'error', offline: false, message: err.message });
      }
    } finally {
      if (!signal?.cancelled) setAsking(false);
    }
  }, [profile, toast]);

  useEffect(() => {
    const signal = { cancelled: false };
    void load(signal);
    return () => {
      signal.cancelled = true;
    };
  }, [load, attempt]);

  // Back online after showing a saved copy (or nothing): ask again.
  const showingSaved = (phase.kind === 'ready' && phase.savedAt !== null) || (phase.kind === 'error' && phase.offline);
  const wasOffline = useRef(offline);
  useEffect(() => {
    if (wasOffline.current && !offline && showingSaved) setAttempt((n) => n + 1);
    wasOffline.current = offline;
  }, [offline, showingSaved]);

  useEffect(() => {
    memory = { profile, phase, tab };
  }, [profile, phase, tab]);

  const byId = useMemo(() => new Map((items.active ?? []).map((i) => [i.id, i])), [items.active]);
  const locked = offline || (phase.kind === 'ready' && phase.savedAt !== null);

  /** Runs a change on the server, then asks for the list again (the analysis is kept on the server, so it is quick). */
  async function change(key: string, run: () => Promise<unknown>, done?: string): Promise<boolean> {
    setBusy(key);
    try {
      await run();
      if (done) toast(done);
      await load();
      return true;
    } catch (e) {
      toast((e as Error).message, 'error');
      return false;
    } finally {
      setBusy(null);
    }
  }

  const actions: Actions = {
    locked,
    busy,
    wish: (g) => change(g.id, () => api.addWish({ gap_id: g.id }), 'On your wishlist'),
    hide: (g, reason) => change(g.id, () => api.hideGap(g.id, reason), 'Hidden. You can bring it back below.'),
    unhide: (id) => change(id, () => api.unhideGap(id), 'Brought back'),
    undoHolds: (g) => change(g.id, async () => {
      for (const id of new Set(g.held_back_by?.map((hold) => hold.gap_id))) await api.unhideGap(id);
    }, 'Brought back'),
    confirmHide: (id) => change(id, () => api.hideGap(id, 'never_wear'), 'Applied to similar suggestions'),
    addByHand: (name, note) => change('new-wish', () => api.addWish({ name, note }), 'On your wishlist'),
    saveNote: (w, note) => change(w.id, () => api.changeWish(w.id, { note }), 'Note saved'),
    bought: async (w) => {
      if (await change(w.id, () => api.wishBought(w.id), `Taken off the list. Add a photo of your new ${w.name.replace(/^(A|An) /, '').toLowerCase()}.`)) navigate('/add');
    },
    remove: (w) => change(w.id, () => api.removeWish(w.id), 'Removed from the list'),
  };

  if (itemId && !wide) {
    return (
      <div className="missing-item">
        <div className="detail-top">
          <Link to="/missing" className="btn btn-ghost back-link"><ChevronLeftIcon /> What's missing</Link>
        </div>
        <ItemDetail key={itemId} id={itemId} status="active" inPanel />
      </div>
    );
  }

  const wishes = phase.kind === 'ready' ? phase.wishes : null;
  const wishlist = <Wishlist wishes={wishes} actions={actions} failed={phase.kind === 'error'} />;

  const main = (
    <div className="missing-main" aria-busy={asking || phase.kind === 'loading'}>
      <header className="page-header missing-header">
        <div className="page-title-row">
          <h1 id="missing-title">What's missing</h1>
          {phase.kind === 'ready' && phase.gaps.enough && (
            <span className="count">{phase.gaps.checked.items} pieces, {phase.gaps.checked.wears} wears looked at</span>
          )}
        </div>
        {asking && phase.kind === 'ready' && <span className="missing-asking muted"><span className="spinner" aria-hidden="true" /> Looking again…</span>}
      </header>
      {!wide && (
        <div className="segmented missing-tabs" role="group" aria-label="Show">
          <button className={tab === 'gaps' ? 'is-on' : ''} aria-pressed={tab === 'gaps'} onClick={() => setTab('gaps')}>Suggestions</button>
          <button className={tab === 'wishlist' ? 'is-on' : ''} aria-pressed={tab === 'wishlist'} onClick={() => setTab('wishlist')}>
            Wishlist{wishes && wishes.length > 0 ? ` · ${wishes.length}` : ''}
          </button>
        </div>
      )}
      {phase.kind === 'ready' && phase.savedAt && (
        <p className="notice notice-warn missing-saved" role="status">
          <WarnIcon />
          <span>Saved earlier{savedWhen(phase.savedAt)}. You're offline, so nothing here can be changed until Closet on your computer can be reached.</span>
        </p>
      )}
      {phase.kind === 'ready' && (wide || tab === 'gaps') && <>
        {!lifeOpen && <LifeBasis context={phase.gaps.context} locked={locked} busy={busy !== null} onOpen={() => setLifeOpen(true)}
          onDismiss={() => void change('life-dismiss', () => api.putSettings({ life_prompt_dismissed: true }))} />}
        {lifeOpen && <LifeQuestions initial={phase.gaps.context?.life ?? null} locked={locked}
          demo={profile === 'demo'} onSaved={async () => { setSituation('all'); await load(); toast('Your answers are saved'); }}
          onClose={() => setLifeOpen(false)} />}
      </>}
      {wide || tab === 'gaps'
        ? <Body phase={phase} byId={byId} actions={actions} offline={offline} onRetry={() => setAttempt((n) => n + 1)}
          situation={situation} onSituation={setSituation} onLife={() => setLifeOpen(true)} />
        : wishlist}
    </div>
  );

  if (!wide) return main;
  return (
    <div className="master-detail missing">
      {main}
      <aside className="detail-panel missing-side" aria-label={itemId ? 'Item details' : 'Your wishlist'}>
        {itemId ? (
          <>
            <div className="missing-panel-top">
              <Link to="/missing" className="btn btn-ghost btn-small back-link"><ChevronLeftIcon /> Back to the wishlist</Link>
            </div>
            <ItemDetail key={itemId} id={itemId} status="active" inPanel />
          </>
        ) : wishlist}
      </aside>
    </div>
  );
}

function LifeBasis({ context, locked, busy, onOpen, onDismiss }: {
  context: GapsAnswer['context']; locked: boolean; busy: boolean; onOpen(): void; onDismiss(): void;
}) {
  const [expanded, setExpanded] = useState(false);
  const detailsId = useId();
  if (!context) return null;
  const { life, climate, taste, demo } = context;
  const answers = lifeSummary(life);
  const basis = [...(answers.length ? answers : ['your closet']),
    ...(climate.used ? [`weather${climate.place ? ` in ${climate.place}` : ' where you live'}`] : []),
    ...(taste.used ? ['what you wear and rate'] : [])];
  return (
    <section className="life-basis" aria-label="What these suggestions are based on">
      <div className="life-basis-line">
        <button className="life-basis-summary" onClick={() => setExpanded(!expanded)}
          aria-expanded={expanded} aria-controls={detailsId} aria-label="See the answers behind these suggestions">
          Based on: {basis.join(' · ')}.
        </button>
      </div>
      <div id={detailsId} hidden={!expanded}>
        <p className="life-context-note">Based on: {basis.join(' · ')}.</p>
        <button className="btn btn-ghost btn-small" onClick={onOpen}>
          {demo ? 'Example answers' : locked ? 'Saved answers' : life ? 'Edit answers' : 'Your answers'}
        </button>
        {climate.message && <p className="life-context-note">{climate.message} <Link to="/settings">Where you are in Settings</Link></p>}
        {!climate.used && !climate.message && <p className="life-context-note">Using a general mix of weather. <Link to="/settings">Set where you are in Settings</Link></p>}
        {climate.used && climate.old && !climate.message && <p className="life-context-note">Using the last saved climate for this place.</p>}
        <div className="life-context-note">
          <p>How these suggestions work</p>
          {taste.used && taste.summary && <p>{taste.summary}</p>}
          <p>Lounging means relaxed clothes at home; Closet can't identify sleepwear. Exercise suggestions are general, not specific to a sport.</p>
        </div>
        {life?.style_words && <p className="life-style-echo">Your words: <q>{life.style_words}</q> <span>Kept as a note, not used to rank suggestions.</span></p>}
      </div>
      {!life && !context.prompt_dismissed && !demo && !locked && (
        <div className="life-invitation">
          <div><h2>Tell it how you live <span>· 1 minute</span></h2>
            <p>More for your everyday. Less for days you never dress for.</p></div>
          <div className="row">
            <button className="btn btn-primary btn-small" onClick={onOpen}>Answer a few questions</button>
            <button className="btn btn-ghost btn-small" disabled={busy} onClick={onDismiss}>Not now</button>
          </div>
        </div>
      )}
    </section>
  );
}

function savedWhen(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const today = new Date().toDateString() === d.toDateString();
  const time = timeOf(iso);
  if (today) return time ? ` today, at ${time}` : ' today';
  return `, on ${d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}`;
}

// ------------------------------------------------------------------ the gaps

interface Actions {
  locked: boolean;
  busy: string | null;
  wish(g: Gap): Promise<unknown>;
  hide(g: Gap, reason: HideReason | null): Promise<unknown>;
  unhide(id: string): Promise<unknown>;
  undoHolds(g: Gap): Promise<unknown>;
  confirmHide(id: string): Promise<unknown>;
  addByHand(name: string, note: string): Promise<boolean>;
  saveNote(w: Wish, note: string): Promise<boolean>;
  bought(w: Wish): Promise<unknown>;
  remove(w: Wish): Promise<unknown>;
}

function Body({ phase, byId, actions, offline, onRetry, situation, onSituation, onLife }: {
  phase: Phase; byId: Map<string, ItemSummary>; actions: Actions; offline: boolean; onRetry(): void;
  situation: SituationId | 'all'; onSituation(id: SituationId | 'all'): void;
  onLife(): void;
}) {
  if (phase.kind === 'loading') {
    return (
      <div className="missing-loading" role="status">
        {Array.from({ length: 3 }, (_, i) => <div key={i} className="missing-skeleton" aria-hidden="true" />)}
        <p className="muted"><span className="spinner" aria-hidden="true" /> Looking at your closet. This can take a few seconds…</p>
      </div>
    );
  }
  if (phase.kind === 'error') {
    return (
      <div className={phase.offline ? 'notice' : 'form-error missing-error'} role="alert">
        <p>{phase.offline ? phase.message : `Couldn't work out what's missing: ${phase.message}`}</p>
        {!phase.offline && <div className="row"><button className="btn btn-small" onClick={onRetry}>Try again</button></div>}
      </div>
    );
  }
  const { gaps } = phase;
  if (!gaps.enough) {
    return (
      <div className="missing-small" data-testid="too-small">
        <div className="empty-art"><HangerIcon /></div>
        <p className="empty-title">Not enough to go on yet</p>
        <p>{gaps.message}</p>
        {offline
          ? <span className="btn btn-primary is-disabled" aria-disabled="true" title={OFFLINE_TITLE}>Add clothes</span>
          : <Link to="/add" className="btn btn-primary">Add clothes</Link>}
      </div>
    );
  }
  const active = activeSituations(gaps.context?.life);
  const selected = active.some((s) => s.id === situation) ? situation : 'all';
  const shown = gaps.gaps.filter((g) => (g.state === 'open' || g.state === 'wished') && (selected === 'all' || g.situations?.some((s) => s.id === selected)));
  const hidden = gaps.gaps.filter((g) => g.state === 'hidden');
  const heldBack = gaps.gaps.filter((g) => g.state === 'held_back' || g.held_back_by?.length);
  const suppressed = gaps.context?.suppressed ?? [];
  const open = shown.filter((g) => g.state === 'open').length;
  const others = otherFindings(gaps);
  return (
    <>
      <section aria-labelledby="gaps-title">
        {gaps.context?.life && <div className="life-filters" role="group" aria-label="Suggestions for">
          <button className={`chip${selected === 'all' ? ' is-on' : ''}`} aria-pressed={selected === 'all'} onClick={() => onSituation('all')}>All</button>
          {active.map((s) => <button key={s.id} className={`chip${selected === s.id ? ' is-on' : ''}`}
            aria-pressed={selected === s.id} onClick={() => onSituation(s.id)}>{s.label}</button>)}
        </div>}
        <h2 id="gaps-title" className="missing-section-title">
          {open ? 'Worth looking for, most helpful first' : 'Worth looking for'}
        </h2>
        {shown.length === 0 && gaps.context?.life && active.length === 0 ? (
          <div className="notice">
            <p>No situations chosen. Choose the days you dress for to get suggestions.</p>
            <button className="btn btn-small" onClick={onLife}>Choose my situations</button>
          </div>
        ) : shown.length === 0 && (
          <p className="notice">{selected !== 'all' ? `Nothing to look for just for ${situationLabel(selected).toLowerCase()} right now.` : hidden.length
            ? "You've hidden every suggestion. They are below if you change your mind."
            : heldBack.length ? 'Your decisions are holding back suggestions. They are below if you change your mind.'
            : 'Nothing is missing that the rules can find. Your closet covers every kind of day they try.'}</p>
        )}
        {shown.length > 0 && open === 0 && <p className="notice">You've decided on every suggestion. New ones show here when your closet changes.</p>}
        <ol className="gap-list">
          {shown.map((g) => (
            <li key={g.id}>
              {g.state === 'wished' ? <WishedGap gap={g} /> : <GapCard gap={g} byId={byId} actions={actions} />}
            </li>
          ))}
        </ol>
      </section>

      {heldBack.length > 0 && <details className="more missing-hidden" data-testid="held-back-gaps">
        <summary>Suggestions held back ({heldBack.length})</summary>
        <p className="hint">These suggestions match something you said you never dress for. Undo brings them back for the days listed.</p>
        <ul className="missing-hidden-list">
          {heldBack.map((g) => <li key={g.id}>
            <div><strong>{g.name}</strong>
              {g.held_back_by?.map((hold) => <p className="hint" key={hold.gap_id}>
                Held back for {hold.situations.map(situationLabel).join(', ')} by your decision about {hold.name}.
              </p>)}
            </div>
            {!!g.held_back_by?.length && <button className="btn btn-small" disabled={actions.locked || actions.busy !== null}
              title={actions.locked ? OFFLINE_TITLE : undefined} aria-label={`Undo holds on ${g.name}`}
              onClick={() => void actions.undoHolds(g)}>Undo</button>}
          </li>)}
        </ul>
      </details>}

      {suppressed.length > 0 && <details className="more missing-hidden" data-testid="suppressed-gaps">
        <summary>Days you've ruled out ({suppressed.length})</summary>
        <p className="hint">You said “I never dress like that”. Review or undo those decisions here.</p>
        <ul className="missing-hidden-list">
          {suppressed.map((s) => <li key={s.gap_id}>
            <div><strong>{s.name}</strong><span className="muted"> · {s.situations.map(situationLabel).join(', ')}</span>
              <p className="hint">{s.needs_confirmation
                ? 'This was hidden before you answered. It is not holding back similar suggestions.'
                : 'Holding back similar suggestions for these situations, even if the original suggestion is no longer in the list.'}</p>
            </div>
            {s.needs_confirmation && <button className="btn btn-small" disabled={actions.locked || actions.busy !== null}
              title={actions.locked ? OFFLINE_TITLE : undefined} onClick={() => void actions.confirmHide(s.gap_id)}>Apply to similar suggestions</button>}
            <button className="btn btn-small" disabled={actions.locked || actions.busy !== null} title={actions.locked ? OFFLINE_TITLE : undefined}
              aria-label={`Undo decision about ${s.name}`} onClick={() => void actions.unhide(s.gap_id)}>Undo</button>
          </li>)}
        </ul>
      </details>}

      {hidden.length > 0 && (
        <details className="more missing-hidden" data-testid="hidden-gaps">
          <summary>Hidden ({hidden.length})</summary>
          <ul className="missing-hidden-list">
            {hidden.map((g) => (
              <li key={g.id}>
                <div>
                  <strong>{g.name}</strong>
                  {g.hidden_reason && <span className="muted"> · {reasonLabel(g.hidden_reason)}</span>}
                </div>
                <button className="btn btn-small" disabled={actions.locked || actions.busy === g.id} title={actions.locked ? OFFLINE_TITLE : undefined}
                  aria-label={`Bring back ${g.name}`} onClick={() => void actions.unhide(g.id)}>Bring back</button>
              </li>
            ))}
          </ul>
        </details>
      )}

      {others.length > 0 && (
        <section className="missing-others" aria-labelledby="others-title">
          <h2 id="others-title" className="chip-group-title">Also worth knowing</h2>
          {others.map((f, i) => (
            <div key={`${f.kind}-${i}`} className="missing-other">
              <h3>{f.title}</h3>
              <p>{f.text}</p>
              {f.items.length > 0 && <Pieces ids={f.items} byId={byId} max={8} label={f.title} />}
            </div>
          ))}
        </section>
      )}
    </>
  );
}

function HelpMeter({ score }: { score: number }) {
  const help = helpOf(score);
  return (
    <span className={`help help-${help.level}`} data-testid="help" data-level={help.level}>
      <span className="help-bars" aria-hidden="true">
        {Array.from({ length: HELP_LEVELS }, (_, i) => <span key={i} className={i < help.level ? 'is-on' : ''} />)}
      </span>
      <span className="help-words">{help.words}</span>
    </span>
  );
}

function GapCard({ gap, byId, actions }: { gap: Gap; byId: Map<string, ItemSummary>; actions: Actions }) {
  const [asking, setAsking] = useState(false);
  const titleId = useId();
  const busy = actions.busy === gap.id;
  const title = actions.locked ? OFFLINE_TITLE : undefined;
  return (
    <article className="gap-card" data-testid="gap" data-gap={gap.id} aria-labelledby={titleId}>
      <header className="gap-head">
        <h3 id={titleId}>{gap.name}</h3>
        <HelpMeter score={gap.score} />
      </header>
      <SituationLabels gap={gap} />
      <div className="gap-body">
        <ul className="gap-why" aria-label="Why">
          {gap.why.map((w) => <li key={w}>{w}</li>)}
        </ul>
        <LookForBox look={gap.look_for} />
      </div>
      {gap.evidence.items.length > 0 && (
        <div className="gap-pieces">
          <h4 className="gap-label">From your closet</h4>
          <Pieces ids={gap.evidence.items} byId={byId} max={6} label={`Your pieces for ${gap.name}`} />
        </div>
      )}
      {asking ? (
        <HideForm name={gap.name} locked={actions.locked} busy={busy} onCancel={() => setAsking(false)}
          onHide={async (reason) => {
            await actions.hide(gap, reason);
          }} />
      ) : (
        <div className="row gap-actions">
          <button className="btn btn-primary" disabled={actions.locked || busy} title={title} onClick={() => void actions.wish(gap)}>
            <CheckIcon /> I'll look for this
          </button>
          <button className="btn btn-ghost" disabled={actions.locked || busy} title={title} onClick={() => setAsking(true)}>Not for me</button>
        </div>
      )}
    </article>
  );
}

function WishedGap({ gap }: { gap: Gap }) {
  return (
    <article className="gap-card is-wished" data-testid="gap" data-gap={gap.id} aria-label={gap.name}>
      <header className="gap-head">
        <h3>{gap.name}</h3>
        <HelpMeter score={gap.score} />
      </header>
      <p className="gap-wished"><CheckIcon /> On your wishlist</p>
      <SituationLabels gap={gap} />
    </article>
  );
}

function SituationLabels({ gap }: { gap: Gap }) {
  if (!gap.situations?.length) return null;
  return <ul className="gap-situations" aria-label="Useful for">
    {gap.situations.map((s) => <li key={s.id}>{s.label}</li>)}
  </ul>;
}

function HideForm({ name, locked, busy, onHide, onCancel }: {
  name: string; locked: boolean; busy: boolean; onHide(reason: HideReason | null): Promise<void>; onCancel(): void;
}) {
  const [reason, setReason] = useState<HideReason | null>(null);
  const group = useId();
  return (
    <form className="gap-hide" onSubmit={(e) => { e.preventDefault(); void onHide(reason); }}>
      <fieldset>
        <legend>Why isn't it for you? <span className="muted">(you don't have to say)</span></legend>
        <div className="gap-reasons">
          {HIDE_REASONS.map((r) => (
            <label key={r.value} className={`chip${reason === r.value ? ' is-on' : ''}`}>
              <input type="radio" name={group} value={r.value} checked={reason === r.value} onChange={() => setReason(r.value)} />
              {r.label}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="row">
        <button className="btn btn-primary btn-small" type="submit" disabled={locked || busy} aria-label={`Hide ${name}`}>Hide it</button>
        <button className="btn btn-ghost btn-small" type="button" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

function LookForBox({ look }: { look: LookFor | null }) {
  const lines = lookForLines(look);
  if (!look || !lines.length) return null;
  const colors = colorWords(look.colors);
  return (
    <div className="look-for" data-testid="look-for">
      <h4 className="gap-label">Look for</h4>
      <ul>
        {lines.map((l) => <li key={l}>{l}</li>)}
      </ul>
      {colors && (
        <p className="look-colors">
          <span className="look-swatches" aria-hidden="true">
            {look.colors.map((c) => <span key={c} className="swatch" style={{ background: SWATCH[c] ?? '#ccc' }} />)}
          </span>
          <span>{colors}: these go with what you have</span>
        </p>
      )}
    </div>
  );
}

function Pieces({ ids, byId, max, label: groupLabel }: { ids: string[]; byId: Map<string, ItemSummary>; max: number; label: string }) {
  const shown = ids.slice(0, max);
  const more = ids.length - shown.length;
  return (
    <ul className="gap-thumbs" aria-label={groupLabel}>
      {shown.map((id) => {
        const item = byId.get(id);
        return (
          <li key={id}>
            <Link to={`/missing/item/${encodeURIComponent(id)}`} className="gap-thumb" title={itemName(item)} data-testid="gap-piece">
              <Pic item={item} />
            </Link>
          </li>
        );
      })}
      {more > 0 && <li className="gap-thumb-more muted">and {more} more</li>}
    </ul>
  );
}

// ------------------------------------------------------------------ the wishlist

function Wishlist({ wishes, actions, failed }: { wishes: Wish[] | null; actions: Actions; failed: boolean }) {
  const [adding, setAdding] = useState(false);
  return (
    <section className="wishlist" aria-labelledby="wishlist-title" data-testid="wishlist">
      <div className="wishlist-head">
        <h2 id="wishlist-title">Wishlist{wishes && wishes.length > 0 && <span className="count"> · {wishes.length}</span>}</h2>
        {!adding && (
          <button className="btn btn-small" disabled={actions.locked || wishes === null} title={actions.locked ? OFFLINE_TITLE : undefined}
            onClick={() => setAdding(true)}><PlusIcon /> Add by hand</button>
        )}
      </div>
      {adding && <AddWish actions={actions} onClose={() => setAdding(false)} />}
      {wishes === null && !failed && <div className="missing-skeleton missing-skeleton-small" aria-hidden="true" />}
      {wishes !== null && wishes.length === 0 && !adding && (
        <p className="muted wishlist-empty">Nothing on it yet. Choose “I'll look for this” on a suggestion, or add something by hand.</p>
      )}
      {wishes && wishes.length > 0 && (
        <ul className="wish-list">
          {wishes.map((w) => <li key={w.id}><WishCard wish={w} actions={actions} /></li>)}
        </ul>
      )}
    </section>
  );
}

function AddWish({ actions, onClose }: { actions: Actions; onClose(): void }) {
  const [name, setName] = useState('');
  const [note, setNote] = useState('');
  const busy = actions.busy === 'new-wish';
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    if (await actions.addByHand(name.trim(), note.trim())) onClose();
  }
  return (
    <form className="wish-add" onSubmit={submit} aria-label="Add a wish by hand">
      <label className="field">
        <span>What are you looking for?</span>
        <input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} placeholder="e.g. Brown suede loafers" autoFocus />
      </label>
      <label className="field">
        <span>Note <span className="muted">(optional)</span></span>
        <textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000} rows={2} placeholder="Size, shop, budget…" />
      </label>
      <div className="row">
        <button className="btn btn-primary btn-small" type="submit" disabled={busy || actions.locked || !name.trim()}>Add to the list</button>
        <button className="btn btn-ghost btn-small" type="button" onClick={onClose}>Cancel</button>
      </div>
    </form>
  );
}

function WishCard({ wish, actions }: { wish: Wish; actions: Actions }) {
  const [note, setNote] = useState(wish.note);
  const [saved, setSaved] = useState(wish.note);
  if (saved !== wish.note) {
    // the server's copy changed (saved here or elsewhere): show it
    setSaved(wish.note);
    setNote(wish.note);
  }
  const busy = actions.busy === wish.id;
  const title = actions.locked ? OFFLINE_TITLE : undefined;
  const lines = lookForLines(wish.look_for);
  const colors = colorWords(wish.look_for?.colors);
  const noteId = useId();
  return (
    <article className="wish-card" data-testid="wish" aria-label={wish.name}>
      <h3>{wish.name}</h3>
      {lines.length > 0 && (
        <p className="wish-look">
          {lines.join(' · ')}
          {colors && <><br /><span className="look-swatches" aria-hidden="true">
            {wish.look_for!.colors.map((c) => <span key={c} className="swatch" style={{ background: SWATCH[c] ?? '#ccc' }} />)}
          </span> {colors}</>}
        </p>
      )}
      {!wish.gap_id && <p className="wish-look muted">Added by hand</p>}
      <div className="field wish-note">
        <label htmlFor={noteId}>Note</label>
        <textarea id={noteId} value={note} rows={2} maxLength={1000} disabled={actions.locked} placeholder="Size, shop, budget…"
          onChange={(e) => setNote(e.target.value)} />
        {note.trim() !== wish.note && (
          <div className="row">
            <button className="btn btn-small" disabled={busy || actions.locked} onClick={() => void actions.saveNote(wish, note.trim())}>Save note</button>
            <button className="btn btn-small btn-ghost" onClick={() => setNote(wish.note)}>Undo</button>
          </div>
        )}
      </div>
      <div className="row wish-actions">
        <button className="btn btn-small btn-primary" disabled={busy || actions.locked} title={title ?? 'Takes it off the list and opens Add, to photograph it'}
          onClick={() => void actions.bought(wish)}>I bought it</button>
        <button className="btn btn-small btn-ghost" disabled={busy || actions.locked} title={title} onClick={() => void actions.remove(wish)}>Remove</button>
      </div>
    </article>
  );
}

// ------------------------------------------------------------------ pictures

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
