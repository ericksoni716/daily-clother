import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useId, useMemo, useRef, useState, type FormEvent, type SVGProps } from 'react';
import { api } from '../api';
import { CheckIcon, ChevronIcon, ChevronLeftIcon, HangerIcon, PlusIcon, WarnIcon } from '../components/Icons';
import { LifeQuestions } from '../components/LifeQuestions';
import { Pieces } from '../components/ItemPic';
import {
  colorWords, type Gap, type GapsAnswer, groupReasons, helpOf, HIDE_REASONS, type HideReason, loadSavedGaps, lookForLines,
  type LookFor, otherFindings, reasonLabel, saveGaps, type Wish,
} from '../gaps';
import { BackLink, Button, Card, Notice, PageHeader, SegmentedControl } from '../components/ui';
import { swatchOf } from '../labels';
import { Link, navigate } from '../router';
import { touch, useItems } from '../queries';
import { queryKeys, type EditKind, type KeyName } from '../queryKeys';
import { shownWithCopy, useTellFailure } from '../savedCopy';
import { useApp } from '../store';
import { timeOf } from '../today';
import { wishById } from '../wouldwork';
import type { ItemSummary } from '../types';
import { activeSituations, lifeSummary, situationLabel, type SituationId } from '../life';
import { ItemDetail } from './ItemDetail';
import { WishShop } from './Shop';
import { WouldWork } from './WouldWork';
import './Missing.css';

const OFFLINE_TITLE = 'Needs Closet on your computer to be reachable';

/** A shopping bag: the What's missing screen in the navigation. */
export const BagIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg width={24} height={24} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round"
    strokeLinejoin="round" aria-hidden="true" {...p}>
    <path d="M5 8h14l-1 12H6z" /><path d="M9 10V7a3 3 0 0 1 6 0v3" />
  </svg>
);

type Lists = { gaps: GapsAnswer; wishes: Wish[] };

type Phase =
  | { kind: 'loading' }
  | { kind: 'ready'; gaps: GapsAnswer; wishes: Wish[]; savedAt: string | null }
  | { kind: 'error'; message: string; offline: boolean };

const OFFLINE_EMPTY = "You're offline, and nothing was saved on this device yet. What's missing shows here once Closet on your computer can be reached.";

/** Wish edits that cannot change any wish's finds (a new wish's finds are read when its card shows). */
const NOT_FINDS = ['finds'] as const;

/** The tab chosen, kept while the app is open (the lists themselves are kept by the query cache). */
let memory: { profile: string; tab: Tab } | null = null;

type Tab = 'gaps' | 'wishlist';

/** The copy of both lists kept on this device, for when Closet cannot be reached. */
function savedLists(profile: string): { data: Lists; savedAt: string } | null {
  const saved = loadSavedGaps(profile);
  return saved?.gaps ? { data: { gaps: saved.gaps, wishes: saved.wishes ?? [] }, savedAt: saved.saved_at } : null;
}

export function MissingScreen({ itemId, check, wishId, wide }: { itemId: string | null; check: boolean; wishId: string | null; wide: boolean }) {
  const { profile, offline, toast } = useApp();
  const qc = useQueryClient();
  const items = useItems('active').data;
  const [tab, setTab] = useState<Tab>(memory && memory.profile === profile ? memory.tab : 'gaps');
  const [busy, setBusy] = useState<string | null>(null);
  const [lifeOpen, setLifeOpen] = useState(false);
  const [situation, setSituation] = useState<SituationId | 'all'>('all');

  // Both lists are read through the cache, and each answer is kept on this device for when Closet cannot be reached.
  // Coming back shows them at once; coming back online asks again for both (ClosetProvider).
  const gapsQ = useQuery({
    queryKey: queryKeys.gaps(),
    queryFn: async () => {
      const gaps = await api.gaps();
      saveGaps(profile, { gaps });
      return gaps;
    },
  });
  const wishesQ = useQuery({
    queryKey: queryKeys.wishlist(),
    queryFn: async () => {
      const wishes = await api.wishlist();
      saveGaps(profile, { wishes });
      return wishes;
    },
  });
  const lists = useMemo<Lists | undefined>(
    () => (gapsQ.data && wishesQ.data ? { gaps: gapsQ.data, wishes: wishesQ.data } : undefined), [gapsQ.data, wishesQ.data]);
  const failed = gapsQ.error ?? wishesQ.error;
  const shown = shownWithCopy(lists, failed, () => savedLists(profile), OFFLINE_EMPTY);
  const phase: Phase = shown.kind === 'ready' ? { kind: 'ready', ...shown.data, savedAt: shown.savedAt } : shown;
  const asking = gapsQ.isFetching || wishesQ.isFetching;
  useTellFailure(failed, !!lists, Math.max(gapsQ.errorUpdatedAt, wishesQ.errorUpdatedAt), toast);
  const retry = () => {
    void gapsQ.refetch();
    void wishesQ.refetch();
  };

  useEffect(() => {
    memory = { profile, tab };
  }, [profile, tab]);

  // back from a check (the wish it was started from may have changed meanwhile): ask for the lists again
  const wasChecking = useRef(check);
  useEffect(() => {
    if (wasChecking.current && !check) {
      void qc.invalidateQueries({ queryKey: queryKeys.gaps() });
      void qc.invalidateQueries({ queryKey: queryKeys.wishlist() });
    }
    wasChecking.current = check;
  }, [check, qc]);

  const byId = useMemo(() => new Map((items ?? []).map((i) => [i.id, i])), [items]);
  const locked = offline || (phase.kind === 'ready' && phase.savedAt !== null);

  /** Runs a change on the server, then asks again for what it changed (the analysis is kept on the server, so it is
   * quick) before the buttons are given back. */
  async function change(key: string, kind: EditKind, run: () => Promise<unknown>, done?: string, written: readonly KeyName[] = []): Promise<boolean> {
    setBusy(key);
    try {
      await run();
      if (done) toast(done);
      await touch(qc, kind, written);
      return true;
    } catch (e) {
      toast((e as Error).message, 'error');
      return false;
    } finally {
      setBusy(null);
    }
  }

  const wishChange = (key: string, run: () => Promise<unknown>, done: string) => change(key, 'wish', run, done, NOT_FINDS);
  const actions: Actions = {
    locked,
    busy,
    wish: (g) => wishChange(g.id, () => api.addWish({ gap_id: g.id }), 'On your wishlist'),
    hide: (g, reason) => change(g.id, 'gap', () => api.hideGap(g.id, reason), 'Hidden. You can bring it back below.'),
    unhide: (id) => change(id, 'gap', () => api.unhideGap(id), 'Brought back'),
    undoHolds: (g) => change(g.id, 'gap', async () => {
      for (const id of new Set(g.held_back_by?.map((hold) => hold.gap_id))) await api.unhideGap(id);
    }, 'Brought back'),
    confirmHide: (id) => change(id, 'gap', () => api.hideGap(id, 'never_wear'), 'Applied to similar suggestions'),
    addByHand: (name, note) => wishChange('new-wish', () => api.addWish({ name, note }), 'On your wishlist'),
    saveNote: (w, note) => wishChange(w.id, () => api.changeWish(w.id, { note }), 'Note saved'),
    savePrice: (w, changes) => wishChange(w.id, () => api.changeWish(w.id, changes), 'Price range saved'),
    bought: async (w) => {
      if (await wishChange(w.id, () => api.wishBought(w.id), `Taken off the list. Add a photo of your new ${w.name.replace(/^(A|An) /, '').toLowerCase()}.`)) navigate('/add');
    },
    remove: (w) => wishChange(w.id, () => api.removeWish(w.id), 'Removed from the list'),
  };

  const wishes = phase.kind === 'ready' ? phase.wishes : null;
  const wouldWork = check && (
    <WouldWork key={`${profile}-${wishId ?? ''}`} wish={wishById(wishes, wishId)} wishId={wishId} byId={byId} locked={locked}
      busy={busy === 'new-wish' || (wishId !== null && busy === wishId)}
      onWish={(name, note) => actions.addByHand(name, note)} onNote={(w, note) => actions.saveNote(w, note)}
      onBought={(w) => actions.bought(w)} wide={wide} />
  );

  // its own page, on a phone and on a computer: what it is on the left, the answer on the right
  if (check) return <div className="missing-check">{wouldWork}</div>;

  if (itemId && !wide) {
    return (
      <div className="missing-item">
        <div className="detail-top">
          <BackLink to="/missing" className="btn btn-ghost back-link"><ChevronLeftIcon /> What's missing</BackLink>
        </div>
        <ItemDetail key={itemId} id={itemId} status="active" inPanel />
      </div>
    );
  }

  const wishlist = <Wishlist wishes={wishes} actions={actions} failed={phase.kind === 'error'} />;

  const main = (
    <div className="missing-main" aria-busy={asking || phase.kind === 'loading'}>
      <PageHeader className="missing-header" title="What's missing" titleId="missing-title"
        count={phase.kind === 'ready' && phase.gaps.enough && `${phase.gaps.checked.items} pieces, ${phase.gaps.checked.wears} wears looked at`}
        secondary={<>
          {asking && phase.kind === 'ready' && <span className="missing-asking muted"><span className="spinner" aria-hidden="true" /> Looking again…</span>}
          {locked
            ? <span className="btn is-disabled" aria-disabled="true" title={OFFLINE_TITLE}>Would this work?</span>
            : <Link to="/missing/check" className="btn" data-testid="would-work-open">Would this work?</Link>}
        </>} />
      {!wide && (
        <SegmentedControl label="Show" className="missing-tabs" value={tab}
          options={[
            { value: 'gaps', label: 'Suggestions' },
            { value: 'wishlist', label: `Wishlist${wishes && wishes.length > 0 ? ` · ${wishes.length}` : ''}` },
          ]}
          onChange={setTab} />
      )}
      {phase.kind === 'ready' && phase.savedAt && (
        <Notice as="p" tone="warning" className="missing-saved" role="status" icon={<WarnIcon />}>
          <span>Saved earlier{savedWhen(phase.savedAt)}. You're offline, so nothing here can be changed until Closet on your computer can be reached.</span>
        </Notice>
      )}
      {phase.kind === 'ready' && (wide || tab === 'gaps') && <>
        {!lifeOpen && <LifeBasis context={phase.gaps.context} locked={locked} busy={busy !== null} onOpen={() => setLifeOpen(true)}
          onDismiss={() => void change('life-dismiss', 'settings', () => api.putSettings({ life_prompt_dismissed: true }))} />}
        {lifeOpen && <LifeQuestions initial={phase.gaps.context?.life ?? null} locked={locked}
          about={phase.gaps.context && <LifeAbout context={phase.gaps.context} />}
          demo={profile === 'demo'} onSaved={async () => { setSituation('all'); await touch(qc, 'settings'); toast('Your answers are saved'); }}
          onClose={() => setLifeOpen(false)} />}
      </>}
      {wide || tab === 'gaps'
        ? <Body phase={phase} byId={byId} actions={actions} offline={offline} onRetry={retry}
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
              <BackLink to="/missing" className="btn btn-ghost btn-small back-link"><ChevronLeftIcon /> Back to the wishlist</BackLink>
            </div>
            <ItemDetail key={itemId} id={itemId} status="active" inPanel />
          </>
        ) : wishlist}
      </aside>
    </div>
  );
}

function basisWords(context: NonNullable<GapsAnswer['context']>): string {
  const { life, climate, taste } = context;
  const answers = lifeSummary(life);
  return [...(answers.length ? answers : ['your closet']),
    ...(climate.used ? [`weather${climate.place ? ` in ${climate.place}` : ' where you live'}`] : []),
    ...(taste.used ? ['what you wear and rate'] : [])].join(' · ');
}

/** The "Based on" row: one tap opens How you live, where the whole of it can be read and changed. */
function LifeBasis({ context, locked, busy, onOpen, onDismiss }: {
  context: GapsAnswer['context']; locked: boolean; busy: boolean; onOpen(): void; onDismiss(): void;
}) {
  if (!context) return null;
  const { life, demo } = context;
  // the row can show two lines of it at most, so its name says it all
  const openWord = demo ? 'Example answers' : locked ? 'Saved answers' : life ? 'Edit' : 'Your answers';
  return (
    <section className="life-basis" aria-label="What these suggestions are based on">
      <button type="button" className="life-basis-row" data-testid="life-basis" onClick={onOpen}
        aria-label={`Based on ${basisWords(context)}. ${openWord}: How you live`}>
        <span className="life-basis-text"><span className="life-basis-label">Based on</span> {basisWords(context)}.</span>
        {' '}<span className="life-basis-open">{openWord}<ChevronIcon /></span>
      </button>
      {!life && !context.prompt_dismissed && !demo && !locked && (
        <div className="life-invitation">
          <div><h2>Tell it how you live <span>· 1 minute</span></h2>
            <p>More for your everyday. Less for days you never dress for.</p></div>
          <div className="row">
            <Button variant="primary" small onClick={onOpen}>Answer a few questions</Button>
            <Button variant="ghost" small disabled={busy} onClick={onDismiss}>Not now</Button>
          </div>
        </div>
      )}
    </section>
  );
}

/** What the suggestions are based on, in full: shown inside How you live when it is opened from What's missing. */
function LifeAbout({ context }: { context: NonNullable<GapsAnswer['context']> }) {
  const { life, climate, taste } = context;
  return (
    <section className="life-about" aria-label="What the suggestions are based on" data-testid="life-about">
      <p className="life-context-note">Based on: {basisWords(context)}.</p>
      {climate.message && <p className="life-context-note">{climate.message} <Link to="/settings">Where you are in Settings</Link></p>}
      {!climate.used && !climate.message && <p className="life-context-note">Using a general mix of weather. <Link to="/settings">Set where you are in Settings</Link></p>}
      {climate.used && climate.old && !climate.message && <p className="life-context-note">Using the last saved climate for this place.</p>}
      <div className="life-context-note">
        <p>How these suggestions work</p>
        {taste.used && taste.summary && <p>{taste.summary}</p>}
        <p>Lounging means relaxed clothes at home; Closet can't identify sleepwear. Exercise suggestions are general, not specific to a sport.</p>
      </div>
      {life?.style_words && <p className="life-style-echo">Your words: <q>{life.style_words}</q> <span>Kept as a note, not used to rank suggestions.</span></p>}
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
  savePrice(w: Wish, changes: { price_min: number | null; price_max: number | null; price_currency: string | null }): Promise<boolean>;
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

/** How much a gap would help, as a labelled pill: never a number to read. */
function HelpPill({ score }: { score: number }) {
  const help = helpOf(score);
  return <span className={`help-pill help-${help.level}`} data-testid="help" data-level={help.level}>{help.words}</span>;
}

/** One sentence for why, then every reason once with the kinds of day it was given for, behind a disclosure. */
function GapWhy({ why }: { why: string[] }) {
  const groups = groupReasons(why);
  if (!groups.length) return null;
  const more = groups.length > 1 || groups[0].days.length > 0;
  return (
    <div className="gap-why-box">
      <p className="gap-summary" data-testid="gap-summary">{groups[0].text}</p>
      {more && (
        <details className="gap-days" data-testid="gap-why">
          <summary>Why, day by day ({why.length})</summary>
          <ul className="gap-why" aria-label="Why">
            {groups.map((g) => (
              <li key={g.text}>
                <p>{g.text}</p>
                {g.days.length > 0 && (
                  <ul className="gap-when" aria-label="For">
                    {g.days.map((d, i) => <li key={`${d.occasion}-${i}`}><strong>{d.occasion}</strong>: {d.when}</li>)}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function GapCard({ gap, byId, actions }: { gap: Gap; byId: Map<string, ItemSummary>; actions: Actions }) {
  const [asking, setAsking] = useState(false);
  const titleId = useId();
  const busy = actions.busy === gap.id;
  const title = actions.locked ? OFFLINE_TITLE : undefined;
  return (
    <Card as="article" className="gap-card" data-testid="gap" data-gap={gap.id} aria-labelledby={titleId}>
      <header className="gap-head">
        <h3 id={titleId}>{gap.name}</h3>
        <HelpPill score={gap.score} />
      </header>
      <SituationLabels gap={gap} />
      <div className="gap-body">
        <GapWhy why={gap.why} />
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
          <Button variant="primary" disabled={actions.locked || busy} title={title} onClick={() => void actions.wish(gap)}>
            <CheckIcon /> I'll look for this
          </Button>
          <Button variant="ghost" disabled={actions.locked || busy} title={title} onClick={() => setAsking(true)}>Not for me</Button>
        </div>
      )}
    </Card>
  );
}

function WishedGap({ gap }: { gap: Gap }) {
  return (
    <Card as="article" className="gap-card is-wished" data-testid="gap" data-gap={gap.id} aria-label={gap.name}>
      <header className="gap-head">
        <h3>{gap.name}</h3>
        <HelpPill score={gap.score} />
      </header>
      <p className="gap-wished"><CheckIcon /> On your wishlist</p>
      <SituationLabels gap={gap} />
    </Card>
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
            {look.colors.map((c) => <span key={c} className="swatch" style={{ background: swatchOf(c) }} />)}
          </span>
          <span>{colors}: these go with what you have</span>
        </p>
      )}
    </div>
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
    <Card as="article" className="wish-card" data-testid="wish" aria-label={wish.name}>
      <h3>{wish.name}</h3>
      {lines.length > 0 && (
        <p className="wish-look">
          {lines.join(' · ')}
          {colors && <><br /><span className="look-swatches" aria-hidden="true">
            {wish.look_for!.colors.map((c) => <span key={c} className="swatch" style={{ background: swatchOf(c) }} />)}
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
      <WishShop wish={wish} locked={actions.locked} onPrice={(w, changes) => actions.savePrice(w, changes)} />
      <div className="row wish-actions">
        <button className="btn btn-small" disabled={busy || actions.locked} title={title}
          onClick={() => navigate(`/missing/check/wish/${encodeURIComponent(wish.id)}`)}>I found one: would it work?</button>
        <button className="btn btn-small btn-primary" disabled={busy || actions.locked} title={title ?? 'Takes it off the list and opens Add, to photograph it'}
          onClick={() => void actions.bought(wish)}>I bought it</button>
        <button className="btn btn-small btn-ghost" disabled={busy || actions.locked} title={title} onClick={() => void actions.remove(wish)}>Remove</button>
      </div>
    </Card>
  );
}
