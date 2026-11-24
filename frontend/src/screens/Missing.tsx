/**
 * The parts of the Wardrobe page about buying: the things worth buying (found by rule), what they are based on, the row
 * that opens the wishlist, and the wishlist's and a wish's own pages. The page itself, which reads the lists, is
 * Wardrobe.tsx.
 */
import { useId, useState, type FormEvent, type ReactNode } from 'react';
import { CheckIcon, ChevronIcon, HangerIcon, LinkIcon, PlusIcon } from '../components/Icons';
import { Pieces } from '../components/ItemPic';
import {
  colorWords, type Gap, type GapsAnswer, groupReasons, helpOf, HIDE_REASONS, type HideReason, loadSavedGaps, lookForLines,
  type LookFor, reasonLabel, shortWhy, type Wish,
} from '../gaps';
import { Button, buttonClass, Card, EmptyState, Fold, SaveStatus, ShowMore, useSaveStatus } from '../components/ui';
import { swatchOf } from '../labels';
import { Link, navigate, WISHLIST_PATH, wishPath } from '../router';
import type { ItemSummary } from '../types';
import { activeSituations, lifeSummary, situationLabel, type SituationId } from '../life';
import { downWords, googleShoppingLink, linkWords, wishlistWords, withinWords } from '../shop';
import { LinkForm, WishShop } from './Shop';

export const OFFLINE_TITLE = 'Needs Nines on your computer to be reachable';

export type Lists = { gaps: GapsAnswer; wishes: Wish[] };

/** How many things worth buying show before "See all": the few most worth it (DESIGN, "Lead with the answer"). */
export const TOP_GAPS = 3;

/** The copy of both lists kept on this device, for when Nines cannot be reached. */
export function savedLists(profile: string): { data: Lists; savedAt: string } | null {
  const saved = loadSavedGaps(profile);
  return saved?.gaps ? { data: { gaps: saved.gaps, wishes: saved.wishes ?? [] }, savedAt: saved.saved_at } : null;
}

/** The copy of the wishlist kept on this device, for its own page when Nines cannot be reached. */
export function savedWishes(profile: string): { data: Wish[]; savedAt: string } | null {
  const saved = loadSavedGaps(profile);
  return saved?.wishes ? { data: saved.wishes, savedAt: saved.saved_at } : null;
}

function basisWords(context: NonNullable<GapsAnswer['context']>): string {
  const { life, climate, taste } = context;
  const answers = lifeSummary(life);
  return [...(answers.length ? answers : ['your closet']),
    ...(climate.used ? [`weather${climate.place ? ` in ${climate.place}` : ' where you live'}`] : []),
    ...(taste.used ? ['what you wear and rate'] : [])].join(' · ');
}

/** The "Based on" row: one tap opens How you live, where the whole of it can be read and changed. */
export function LifeBasis({ context, locked, busy, invite = true, onOpen, onDismiss }: {
  context: GapsAnswer['context']; locked: boolean; busy: boolean;
  /** Offer the questions as well: only once the closet has enough in it to suggest from (asking first is out of order). */
  invite?: boolean;
  onOpen(): void; onDismiss(): void;
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
      {invite && !life && !context.prompt_dismissed && !demo && !locked && (
        <div className="life-invitation">
          <h2>Tell it how you live <span>· 1 minute</span></h2>
          <div className="row">
            <Button variant="primary" small onClick={onOpen}>Answer a few questions</Button>
            <Button variant="ghost" small disabled={busy} onClick={onDismiss}>Not now</Button>
          </div>
        </div>
      )}
    </section>
  );
}

/** What the suggestions are based on, in full: shown inside How you live when it is opened from the Wardrobe. */
export function LifeAbout({ context }: { context: NonNullable<GapsAnswer['context']> }) {
  const { climate, taste } = context;
  return (
    <section className="life-about" aria-label="What the suggestions are based on" data-testid="life-about">
      <p className="life-context-note">Based on: {basisWords(context)}.</p>
      {climate.message && <p className="life-context-note">{climate.message} <Link to="/settings">Where you are in Settings</Link></p>}
      {!climate.used && !climate.message && <p className="life-context-note">Using a general mix of weather. <Link to="/settings">Set where you are in Settings</Link></p>}
      {climate.used && climate.old && !climate.message && <p className="life-context-note">Using the last saved climate for this place.</p>}
      <div className="life-context-note">
        <p>How these suggestions work</p>
        {taste.used && taste.summary && <p>{taste.summary}</p>}
        <p>Lounging means relaxed clothes at home; Nines can't identify sleepwear. Exercise suggestions are general, not specific to a sport.</p>
      </div>
    </section>
  );
}

// ------------------------------------------------------------------ the gaps

export interface Actions {
  locked: boolean;
  busy: string | null;
  wish(g: Gap): Promise<unknown>;
  /** Undo for "I'll look for this": the wish made from the gap is taken off the list again. */
  unwish(g: Gap): Promise<unknown>;
  hide(g: Gap, reason: HideReason | null): Promise<unknown>;
  unhide(id: string): Promise<unknown>;
  undoHolds(g: Gap): Promise<unknown>;
  confirmHide(id: string): Promise<unknown>;
  addByHand(name: string, note: string): Promise<boolean>;
  /** A new wish made from a product's page, then its page opened; the sentence to show when the link was not taken. */
  addLink(url: string): Promise<string | null>;
  saveNote(w: Wish, note: string): Promise<boolean>;
  savePrice(w: Wish, changes: { price_min: number | null; price_max: number | null; price_currency: string | null }): Promise<boolean>;
  bought(w: Wish): Promise<unknown>;
  remove(w: Wish): Promise<boolean>;
}

/**
 * The things worth buying: the few that would help most, then "See all N"; the situations they are for when the owner
 * has said how they live; and, folded, the decisions that hold suggestions back or hide them.
 */
export function WorthBuying({ gaps, byId, actions, offline, situation, onSituation, onLife, basis }: {
  gaps: GapsAnswer; byId: Map<string, ItemSummary>; actions: Actions; offline: boolean;
  situation: SituationId | 'all'; onSituation(id: SituationId | 'all'): void;
  onLife(): void;
  /** What the suggestions are based on, at the top of the section. */
  basis: ReactNode;
}) {
  if (!gaps.enough) {
    return (
      <section className="missing-small" data-testid="too-small" aria-labelledby="gaps-title">
        {basis}
        <div className="empty-art"><HangerIcon /></div>
        <h2 id="gaps-title" className="empty-title">Not enough to go on yet</h2>
        <p>{gaps.message}</p>
        {offline
          ? <span className="btn btn-primary is-disabled" aria-disabled="true" title={OFFLINE_TITLE}>Add clothes</span>
          : <Link to="/add" className="btn btn-primary">Add clothes</Link>}
      </section>
    );
  }
  const active = activeSituations(gaps.context?.life);
  const selected = active.some((s) => s.id === situation) ? situation : 'all';
  const shown = gaps.gaps.filter((g) => (g.state === 'open' || g.state === 'wished') && (selected === 'all' || g.situations?.some((s) => s.id === selected)));
  const hidden = gaps.gaps.filter((g) => g.state === 'hidden');
  const heldBack = gaps.gaps.filter((g) => g.state === 'held_back' || g.held_back_by?.length);
  const suppressed = gaps.context?.suppressed ?? [];
  const open = shown.filter((g) => g.state === 'open').length;
  return (
    <section className="wardrobe-section" aria-labelledby="gaps-title">
      <h2 id="gaps-title" className="missing-section-title">Worth buying</h2>
      {basis}
      {gaps.context?.life && <div className="life-filters" role="group" aria-label="Suggestions for">
        <button className={`chip${selected === 'all' ? ' is-on' : ''}`} aria-pressed={selected === 'all'} onClick={() => onSituation('all')}>All</button>
        {active.map((s) => <button key={s.id} className={`chip${selected === s.id ? ' is-on' : ''}`}
          aria-pressed={selected === s.id} onClick={() => onSituation(s.id)}>{s.label}</button>)}
      </div>}
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
      <ShowMore items={shown} first={TOP_GAPS} wide={TOP_GAPS} as="ol" className="gap-list" label="Worth buying, most helpful first"
        keyOf={(g) => g.id}
        render={(g) => <GapCard gap={g} byId={byId} actions={actions} />} />

      {heldBack.length > 0 && <Fold className="missing-hidden" testId="held-back-gaps" title={`Suggestions held back (${heldBack.length})`}>
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
      </Fold>}

      {suppressed.length > 0 && <Fold className="missing-hidden" testId="suppressed-gaps" title={`Days you've ruled out (${suppressed.length})`}>
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
      </Fold>}

      {hidden.length > 0 && (
        <Fold className="missing-hidden" testId="hidden-gaps" title={`Hidden (${hidden.length})`}>
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
        </Fold>
      )}
    </section>
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

/**
 * A thing worth buying, as a card that opens in place: closed, its name, how much it helps and one line of why; open,
 * what it showed before (every reason, what to look for, your pieces, the search and the two buttons). Its name is the
 * button; the whole head is the place to tap. "I'll look for this" leaves the card where it is and says so in place,
 * with Undo, so nothing on the page moves (DESIGN, "The page holds still"). The same card draws a wished gap, so it
 * keeps whether it is open when its state changes.
 */
function GapCard({ gap, byId, actions, startOpen = false }: { gap: Gap; byId: Map<string, ItemSummary>; actions: Actions; startOpen?: boolean }) {
  const [open, setOpen] = useState(startOpen);
  const [asking, setAsking] = useState(false);
  const titleId = useId();
  const bodyId = useId();
  const busy = actions.busy === gap.id;
  const title = actions.locked ? OFFLINE_TITLE : undefined;
  const wished = gap.state === 'wished';
  return (
    <Card as="article" className={`gap-card${open ? ' is-open' : ''}${wished ? ' is-wished' : ''}`} data-testid="gap" data-gap={gap.id}
      aria-labelledby={titleId}>
      <header className="gap-head">
        <h3 id={titleId}>
          <button type="button" className="gap-toggle" aria-expanded={open} aria-controls={bodyId} onClick={() => setOpen(!open)}>
            {gap.name}
          </button>
        </h3>
        <ChevronIcon className="gap-chevron" aria-hidden="true" />
        <p className="gap-line">
          <HelpPill score={gap.score} />
          {!open && (wished
            ? <span className="gap-wished"><CheckIcon /> On your wishlist</span>
            : <span className="gap-summary gap-short" data-testid="gap-summary">{shortWhy(gap.why)}</span>)}
        </p>
      </header>
      <div id={bodyId} className="gap-open" hidden={!open}>
        {open && (
          <>
            <SituationLabels gap={gap} />
            <div className="gap-body">
              <GapWhy why={gap.why} />
              <LookForBox look={gap.look_for} />
            </div>
            <p className="gap-search">
              <a className={buttonClass({ variant: 'link', small: true, className: 'wish-inline-button' })} data-testid="google-shopping"
                href={googleShoppingLink(gap)} target="_blank" rel="noopener noreferrer">Search Google Shopping</a>
            </p>
            {gap.evidence.items.length > 0 && (
              <div className="gap-pieces">
                <h4 className="gap-label">From your closet</h4>
                <Pieces ids={gap.evidence.items} byId={byId} max={6} label={`Your pieces for ${gap.name}`} />
              </div>
            )}
            {wished ? (
              <div className="row gap-actions gap-wished-row" role="status">
                <span className="gap-wished"><CheckIcon /> On your wishlist</span>
                <Button variant="ghost" disabled={actions.locked || busy} title={title} aria-label={`Undo: take ${gap.name} off your wishlist`}
                  onClick={() => void actions.unwish(gap)}>Undo</Button>
              </div>
            ) : asking ? (
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
          </>
        )}
      </div>
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

/**
 * "Thinking of buying something?" on the Wardrobe: Would this work? for a piece you have in mind, and one row that opens
 * the wishlist's own page, saying how many things are on it and how many of their prices went down.
 */
export function Thinking({ wishes, locked }: { wishes: Wish[] | null; locked: boolean }) {
  return (
    <section className="wardrobe-section thinking" aria-labelledby="thinking-title">
      <h2 id="thinking-title" className="missing-section-title">Thinking of buying something?</h2>
      <div className="thinking-check">
        <p>See how a piece would go with your closet before you buy it.</p>
        {locked
          ? <span className="btn is-disabled" aria-disabled="true" title={OFFLINE_TITLE}>Would this work?</span>
          : <Link to="/wardrobe/check" className="btn" data-testid="would-work-open">Would this work?</Link>}
      </div>
      <WishlistRow wishes={wishes} />
    </section>
  );
}

/** The row that opens the wishlist. Until the list is known its second line is kept empty, so nothing moves. */
function WishlistRow({ wishes }: { wishes: Wish[] | null }) {
  const words = wishes ? wishlistWords(wishes) : null;
  return (
    <Link to={WISHLIST_PATH} className="wish-row" data-testid="wishlist-open">
      <span className="wish-row-text">
        <span className="wish-row-name">Wishlist</span>
        <span className="wish-row-more muted">{words?.count ?? '\u00a0'}</span>
        {words?.down && (
          <span className="wish-row-news">
            <span className="wish-row-drop" data-testid="wishlist-down">{words.down}</span>
          </span>
        )}
      </span>
      <ChevronIcon aria-hidden="true" />
    </Link>
  );
}

/**
 * The wishlist's own page (`/wardrobe/wishlist`): "Add a link" and "Add by hand", then a row per wish that opens its
 * page (its note, shop finds and prices), or, with nothing on it, what a wishlist is for.
 */
export function Wishlist({ wishes, actions }: { wishes: Wish[]; actions: Actions }) {
  const [adding, setAdding] = useState(false);
  const [linking, setLinking] = useState(false);
  const offTitle = actions.locked ? OFFLINE_TITLE : undefined;
  return (
    <div className="wishlist" data-testid="wishlist">
      {!adding && !linking && (
        <div className="row wishlist-adds">
          <Button small disabled={actions.locked} title={offTitle} onClick={() => setLinking(true)}><LinkIcon /> Add a link</Button>
          <Button small disabled={actions.locked} title={offTitle} onClick={() => setAdding(true)}><PlusIcon /> Add by hand</Button>
        </div>
      )}
      {linking && (
        <LinkForm submit="Add to the list" busy={actions.busy === 'new-link'} locked={actions.locked} lockedTitle={OFFLINE_TITLE}
          onSubmit={actions.addLink} onCancel={() => setLinking(false)} />
      )}
      {adding && <AddWish actions={actions} onClose={() => setAdding(false)} />}
      {wishes.length === 0 && !adding && !linking && (
        <EmptyState testId="wishlist-empty" title="Your wishlist is empty"
          body="Things you'd like to buy wait here, and Nines tells you when their price goes down."
          action={<Link to="/wardrobe" className={buttonClass()}>See what's worth buying</Link>} />
      )}
      {wishes.length > 0 && (
        <ul className="wish-list">
          {wishes.map((w) => <li key={w.id}><WishRow wish={w} /></li>)}
        </ul>
      )}
    </div>
  );
}

/** A wish in the list: what it is and its note (or the page it was sent as), and a price that went down, opening its
 * page. */
function WishRow({ wish }: { wish: Wish }) {
  const lines = lookForLines(wish.look_for);
  const more = wish.note || (lines.length ? lines.join(' · ') : wish.link ? linkWords(wish.link) : wish.gap_id ? '' : 'Added by hand');
  return (
    <Link to={wishPath(wish.id)} className="wish-row" data-testid="wish-row">
      <span className="wish-row-text">
        <span className="wish-row-name">{wish.name}</span>
        <span className="wish-row-more muted">{more}</span>
        {wish.drop && (
          <span className="wish-row-news">
            <span className="wish-row-drop" data-testid="wish-drop">{downWords(wish.drop)}</span>
            {withinWords(wish) && <span className="wish-row-within">{withinWords(wish)}</span>}
          </span>
        )}
      </span>
      <ChevronIcon aria-hidden="true" />
    </Link>
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

/** A wish on its own page: what to look for, what is watched and its price (`WishShop`), looking for more, its note
 * (saved as you leave the box), and what to do with it. */
export function WishCard({ wish, actions, onNote, onRemoved }: {
  wish: Wish; actions: Actions;
  /** Saves the note; throws when it could not. */
  onNote(w: Wish, note: string): Promise<unknown>;
  onRemoved(): void;
}) {
  const [note, setNote] = useState(wish.note);
  const [saved, setSaved] = useState(wish.note);
  if (saved !== wish.note) {
    // the server's copy changed (saved here or elsewhere): show it
    setSaved(wish.note);
    setNote(wish.note);
  }
  const status = useSaveStatus();
  const busy = actions.busy === wish.id;
  const title = actions.locked ? OFFLINE_TITLE : undefined;
  const lines = lookForLines(wish.look_for);
  const colors = colorWords(wish.look_for?.colors);
  const noteId = useId();
  const saveNote = () => {
    if (note.trim() !== wish.note) void status.run(() => onNote(wish, note.trim()));
  };
  return (
    <Card as="article" className="wish-card" data-testid="wish" aria-label={wish.name}>
      {lines.length > 0 && (
        <p className="wish-look">
          {lines.join(' · ')}
          {colors && <><br /><span className="look-swatches" aria-hidden="true">
            {wish.look_for!.colors.map((c) => <span key={c} className="swatch" style={{ background: swatchOf(c) }} />)}
          </span> {colors}</>}
        </p>
      )}
      <WishShop wish={wish} locked={actions.locked} onPrice={(w, changes) => actions.savePrice(w, changes)} />
      <div className="field wish-note">
        <label htmlFor={noteId}>Note</label>
        <textarea id={noteId} value={note} rows={2} maxLength={1000} disabled={actions.locked} placeholder="Size, shop, budget…"
          onChange={(e) => setNote(e.target.value)} onBlur={saveNote} />
        <div className="row wish-note-row">
          {note.trim() !== wish.note && (
            <>
              <button className="btn btn-small" disabled={busy || actions.locked || status.state === 'saving'} onClick={saveNote}>Save note</button>
              <button className="btn btn-small btn-ghost" onClick={() => setNote(wish.note)}>Undo</button>
            </>
          )}
          <SaveStatus state={status.state} onRetry={status.retry} testId="wish-note-status" />
        </div>
      </div>
      <div className="row wish-actions">
        <button className="btn btn-small" disabled={busy || actions.locked} title={title ?? 'Checks a piece against your closet before you buy it'}
          onClick={() => navigate(`/wardrobe/check/wish/${encodeURIComponent(wish.id)}`)}>Would it go with my clothes?</button>
        <button className="btn btn-small btn-primary" disabled={busy || actions.locked} title={title ?? 'Takes it off the list and opens Add, to photograph it'}
          onClick={() => void actions.bought(wish)}>I bought it</button>
        <button className="btn btn-small btn-ghost" disabled={busy || actions.locked} title={title}
          onClick={async () => { if (await actions.remove(wish)) onRemoved(); }}>Remove from the list</button>
      </div>
    </Card>
  );
}
